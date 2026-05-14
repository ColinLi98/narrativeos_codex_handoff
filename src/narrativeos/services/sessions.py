from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Optional

from ..core.linter import lint_chapter_draft
from ..intent import SimpleIntentParser
from ..longform import (
    apply_steering_directive,
    configure_interactive_longform_runtime,
    configure_longform_runtime,
    record_replan_debt,
)
from .authoring import _default_memory_compression_policy, _resolve_longform_structure
from ..models import CandidateBatch, NarrativeState, StepRecord
from ..pipeline import plan_next_turn
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..providers import StaticCandidateProvider
from ..long_route_quality import apply_long_route_quality_controls
from ..quality.adapter import enforce_grounding_quality_gate, persist_guardrail_records
from ..quality.hard_constraints import enforce_generation_hard_constraints
from ..quality.grounding import build_grounding_check
from ..rendering import TemplateRenderer
from ..sanitizer import sanitize_reader_visible_payload
from ..eval.service import evaluate_persisted_chapter
from .analytics import AnalyticsService
from .billing import BillingService
from .choice_semantics import build_choice_impacts, merge_choice_impacts_into_reader_view
from .illustration import IllustrationService
from .observability import ObservabilityService
from .provider_routing import ProviderRoutingService


class ReaderContinueCommand:
    def __init__(
        self,
        session_id: str,
        choice_id: str | None = None,
        freeform_intent: str | None = None,
        steering_directive: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session_id = session_id
        self.choice_id = choice_id
        self.freeform_intent = freeform_intent
        self.steering_directive = dict(steering_directive or {})


def build_reader_continuity_contract(
    *,
    status: str,
    session_id: str,
    paywall: Optional[Dict[str, Any]] = None,
    quality_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_status = str(status or "ok")
    message = "这一章已经推进完成，可以继续阅读。"
    primary_action = "continue_reading"
    retryable = False
    chapter_context_retained = normalized_status in {"payment_required", "quality_guard_failed", "restricted"}
    if normalized_status == "payment_required":
        tier_name = str((paywall or {}).get("required_display_name") or (paywall or {}).get("suggested_checkout_tier") or "推荐档位")
        message = f"继续前需要先解锁，当前 session 和阅读位置已保留；完成支付后会直接回到这一章。"
        if tier_name:
            message = f"{message} 推荐使用 {tier_name} 继续。"
        primary_action = "unlock_and_resume"
    elif normalized_status == "restricted":
        message = "当前章节因限制策略被拦下，但阅读位置已保留；需要先处理限制原因后再继续。"
        primary_action = "resolve_restriction"
    elif normalized_status == "quality_guard_failed":
        quality_payload = dict(quality_gate or {})
        issues = [str(item.get("issue_code") or "") for item in list(quality_payload.get("issues") or []) if str(item.get("issue_code") or "")]
        required_units = int(quality_payload.get("required_text_units", 0) or 0)
        actual_units = int(quality_payload.get("actual_text_units", 0) or 0)
        message = "本章未入库，但当前 session、阅读位置和上一章内容都已保留；可直接重试当前章。"
        if required_units or actual_units:
            message += f" 当前文本 {actual_units}/{required_units or '-'}。"
        if issues:
            message += f" 主要问题：{' / '.join(issues[:3])}。"
        primary_action = "retry_current_chapter"
        retryable = True
    return {
        "status": normalized_status,
        "resume_session_id": session_id,
        "preserve_session_context": True,
        "preserve_workspace": "read",
        "preserve_view": "previous_reader_view",
        "chapter_context_retained": chapter_context_retained,
        "primary_action": primary_action,
        "retryable": retryable,
        "message": message,
    }


class SessionService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        intent_parser: Optional[SimpleIntentParser] = None,
        renderer: Optional[TemplateRenderer] = None,
        billing_service: Optional[BillingService] = None,
        analytics_service: Optional[AnalyticsService] = None,
        observability_service: Optional[ObservabilityService] = None,
        provider_routing_service: Optional[ProviderRoutingService] = None,
        illustration_service: Optional[IllustrationService] = None,
    ) -> None:
        self.repository = repository
        self.intent_parser = intent_parser or SimpleIntentParser()
        self.renderer = renderer or TemplateRenderer()
        self.billing = billing_service or BillingService(repository)
        self.analytics = analytics_service or AnalyticsService(repository)
        self.observability = observability_service or ObservabilityService(repository)
        self.provider_routing = provider_routing_service
        self.illustration = illustration_service

    def _candidate_reranker(self, *, world_id: str, world_version_id: str):
        def _rerank(**context: Any) -> Dict[str, Any]:
            from ..eval.learned_assisted_rerank import evaluate_assisted_rerank_candidates

            return evaluate_assisted_rerank_candidates(
                repository=self.repository,
                world_id=world_id,
                world_version_id=world_version_id,
                ranked_candidates=context.get("ranked_candidates") or [],
                beat_index=int(context.get("beat_index") or 1),
                persist_receipt=True,
            )

        return _rerank

    def _entitlement_snapshot(self, access: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "access_tier": access.get("access_tier"),
            "reason": access.get("reason"),
            "quote": access.get("quote"),
            "entitlement_type": access.get("entitlement_type"),
            "account_id": access.get("account_id"),
            "tier_id": access.get("tier_id"),
            "wallet_type": access.get("wallet_type"),
            "balance": access.get("balance"),
            "status": access.get("status"),
        }

    def _prepare_longform_state(
        self,
        *,
        runtime: Any,
        state: NarrativeState,
        longform_setup: Optional[Dict[str, Any]] = None,
    ) -> NarrativeState:
        worldpack = runtime.worldpack
        longform_structure = None
        if worldpack.series_plan and worldpack.volume_plans and worldpack.arc_plans:
            longform_structure = {
                "series_plan": worldpack.series_plan.to_dict(),
                "volume_plans": [item.to_dict() for item in worldpack.volume_plans],
                "arc_plans": [item.to_dict() for item in worldpack.arc_plans],
                "chapter_budget_policy": worldpack.chapter_budget_policy.to_dict() if worldpack.chapter_budget_policy else {},
            }
        elif getattr(worldpack, "scene_blueprints", None):
            longform_structure = _resolve_longform_structure(
                worldpack_payload=worldpack.to_dict(),
                runtime_world_title=runtime.world_record.world.title,
                max_chapters=100,
            )
        if longform_structure:
            configure_longform_runtime(
                state,
                series_plan=dict(longform_structure.get("series_plan") or {}),
                volume_plans=[dict(item) for item in longform_structure.get("volume_plans", [])],
                arc_plans=[dict(item) for item in longform_structure.get("arc_plans", [])],
                chapter_budget_policy=dict(longform_structure.get("chapter_budget_policy") or {}),
                memory_compression_policy=dict(
                    getattr(worldpack, "memory_compression_policy", {})
                    or _default_memory_compression_policy(
                        len(list(longform_structure.get("volume_plans") or []))
                    )
                ),
                world=runtime.world_record.world,
            )
        setup = dict(longform_setup or {})
        configure_interactive_longform_runtime(
            state,
            series_storyline_contract={
                **dict(getattr(worldpack, "series_storyline_contract", {}) or {}),
                **dict(setup.get("series_storyline_contract") or {}),
            },
            character_memory_profiles={
                **dict(getattr(worldpack, "character_memory_profiles", {}) or {}),
                **dict(setup.get("character_memory_profiles") or {}),
            },
            steering_guardrails={
                **dict(getattr(worldpack, "steering_guardrails", {}) or {}),
                **dict(setup.get("steering_guardrails") or {}),
            },
        )
        return state

    def _runtime_min_target_words(self, runtime: Any) -> Optional[int]:
        chapter_budget_policy = getattr(runtime.worldpack, "chapter_budget_policy", None)
        if chapter_budget_policy is None:
            return None
        if hasattr(chapter_budget_policy, "to_dict"):
            payload = dict(chapter_budget_policy.to_dict() or {})
        else:
            payload = dict(chapter_budget_policy or {})
        if payload.get("min_target_words") is None:
            return None
        return int(payload.get("min_target_words") or 0)

    def _effective_min_target_words(
        self,
        runtime: Any,
        *,
        chapter_index: int = 0,
        story_phase: str = "",
    ) -> Optional[int]:
        base = self._runtime_min_target_words(runtime)
        if base is None:
            return None
        normalized_phase = str(story_phase or "").strip()
        normalized_chapter_index = int(chapter_index or 0)
        if normalized_phase == "setup" or normalized_chapter_index <= 1:
            return min(base, 900)
        if normalized_phase == "early_rising":
            return min(base, 1200)
        return base

    def _effective_target_words(
        self,
        target_words: Any,
        *,
        chapter_index: int = 0,
        story_phase: str = "",
    ) -> Optional[int]:
        try:
            base = int(target_words or 0)
        except (TypeError, ValueError):
            return None
        if base <= 0:
            return None
        normalized_phase = str(story_phase or "").strip()
        normalized_chapter_index = int(chapter_index or 0)
        if normalized_phase == "setup" or normalized_chapter_index <= 1:
            return min(base, 1100)
        if normalized_phase == "early_rising":
            return min(base, 1400)
        return base

    def _latest_non_pass_quality_trace_id(self, session_id: str) -> Optional[str]:
        for item in self.repository.list_quality_events(session_id=session_id, limit=20):
            if str(item.get("status") or "") in {"blocked", "review_required"}:
                trace_id = str(item.get("trace_id") or "").strip()
                if trace_id:
                    return trace_id
        return None

    def _record_quality_feedback_item(
        self,
        *,
        feedback_type: str,
        signal: str,
        source_surface: str,
        account_id: Optional[str],
        world_version_id: Optional[str],
        session_id: Optional[str],
        chapter_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        source_ref: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.repository.save_quality_feedback_item(
            {
                "feedback_type": feedback_type,
                "signal": signal,
                "source_surface": source_surface,
                "account_id": account_id,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "chapter_id": chapter_id,
                "trace_id": trace_id,
                "source_event_id": source_event_id,
                "source_ref": dict(source_ref or {}),
                "payload": dict(payload or {}),
            }
        )

    def create_session(self, world_id: str, reader_id: str | None = None, longform_setup: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        world = next((item for item in self.repository.list_worlds() if item["world_id"] == world_id), None)
        if world is None:
            raise KeyError("unknown_world:%s" % world_id)
        runtime = self.repository.get_runtime_bundle(world["latest_version"])
        account_id = self.billing.resolve_account_id(reader_id=reader_id)
        initial_state = self._prepare_longform_state(
            runtime=runtime,
            state=NarrativeState.from_dict(runtime.initial_state.to_dict()),
            longform_setup=longform_setup,
        )
        session = self.repository.create_session_record(
            world_version_id=runtime.world_version_id,
            initial_state=initial_state,
            reader_id=reader_id,
            metadata={
                "source": "beta_reader",
                "account_id": account_id,
                "longform_setup_present": bool(longform_setup),
            },
            entitlements_snapshot={"access_tier": "trial"},
        )
        access = self.billing.access_check(
            session.session_id,
            reader_id=reader_id,
            account_id=account_id,
        )
        snapshot = self._entitlement_snapshot(access)
        self.repository.update_session_entitlements_snapshot(session.session_id, snapshot)
        self.analytics.track(
            "session_created",
            reader_id=reader_id,
            session_id=session.session_id,
            world_id=world_id,
            world_version_id=runtime.world_version_id,
            access_tier=access.get("access_tier"),
            payload_json=snapshot,
        )
        if self.illustration is not None:
            self.illustration.ensure_session_cover(
                session_id=session.session_id,
                reader_id=reader_id,
                world_version_id=runtime.world_version_id,
            )
            self.illustration.ensure_world_cover(world_version_id=runtime.world_version_id)
        return {
            "session_id": session.session_id,
            "reader_id": reader_id,
            "account_id": account_id,
            "world_id": world_id,
            "world_version_id": runtime.world_version_id,
            "current_state": session.current_state.to_dict(),
            "paywall": access,
            "steering_checkpoint": dict(initial_state.storyline_checkpoint or {}),
        }

    def continue_story(self, command: ReaderContinueCommand, *, reader_id: str | None = None) -> dict[str, Any]:
        session_record = self.repository.get_session(command.session_id)
        reader_id = reader_id or session_record.metadata.get("reader_id") or session_record.player_profile.get("reader_id")
        account_id = self.billing.resolve_account_id(
            account_id=session_record.metadata.get("account_id"),
            reader_id=reader_id,
        )
        world_version_id = str(session_record.metadata.get("world_version_id"))
        runtime = self.repository.get_runtime_bundle(world_version_id)
        prior_quality_trace_id = self._latest_non_pass_quality_trace_id(command.session_id)
        access = self.billing.access_check(command.session_id, reader_id=reader_id, account_id=account_id)
        if access["required"]:
            latest_step = self.repository.get_latest_step(command.session_id)
            snapshot = self._entitlement_snapshot(access)
            self.repository.update_session_entitlements_snapshot(command.session_id, snapshot)
            blocked_status = "restricted" if access.get("reason") == "manual_restriction_active" else "payment_required"
            blocked_event = "governance_restriction_blocked" if blocked_status == "restricted" else "payment_required"
            self.analytics.track(
                blocked_event,
                reader_id=reader_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                access_tier=access.get("access_tier"),
                payload_json=snapshot,
            )
            self.observability.record_runtime_receipt(
                surface="reader",
                action="continue_story",
                response_status=blocked_status,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                session_id=command.session_id,
                account_id=account_id,
                reader_id=reader_id,
                estimated_cost=0.0,
            )
            try:
                self._record_quality_feedback_item(
                    feedback_type=blocked_status,
                    signal="negative_proxy",
                    source_surface="reader",
                    account_id=account_id,
                    world_version_id=runtime.world_version_id,
                    session_id=command.session_id,
                    trace_id=prior_quality_trace_id,
                    source_ref={"kind": "session", "session_id": command.session_id, "account_id": account_id},
                    payload={"blocked_status": blocked_status, "access_reason": access.get("reason")},
                )
            except Exception:
                pass
            return {
                "session_id": command.session_id,
                "world_id": runtime.worldpack.world_id,
                "world_version_id": runtime.world_version_id,
                "chapter_view": latest_step.reader_view.to_dict() if latest_step and latest_step.reader_view else None,
                "reader_view": latest_step.reader_view.to_dict() if latest_step and latest_step.reader_view else None,
                "updated_state_summary": None,
                "replay_preview": None,
                "paywall": access,
                "status": blocked_status,
                "continuity_contract": build_reader_continuity_contract(
                    status=blocked_status,
                    session_id=command.session_id,
                    paywall=access,
                ),
            }

        source_chapter_index = int(session_record.current_state.chapter_index or 0)
        state_before = NarrativeState.from_dict(session_record.current_state.to_dict())
        self._prepare_longform_state(runtime=runtime, state=state_before)
        player_input = command.freeform_intent or command.choice_id or "继续读下去。"
        state_before.player_intent = self.intent_parser.parse(player_input)
        steering_checkpoint: Dict[str, Any] = {}
        if command.steering_directive:
            steering_directive = dict(command.steering_directive or {})
            steering_directive.setdefault("current_user_intent", player_input)
            steering_result = apply_steering_directive(
                state_before,
                steering_directive,
                world=runtime.world_record.world,
            )
            steering_checkpoint = dict(steering_result.get("replan_checkpoint") or {})
        candidate_provider = (
            self.provider_routing.build_candidate_provider(
                runtime.event_atoms,
                surface="reader",
                account_id=account_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
            )
            if self.provider_routing
            else StaticCandidateProvider(runtime.event_atoms)
        )
        active_renderer = (
            self.provider_routing.build_renderer(
                surface="reader",
                account_id=account_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
            )
            if self.provider_routing
            else self.renderer
        )
        started = perf_counter()
        result = plan_next_turn(
            state_before,
            world=runtime.world_record.world,
            candidate_provider=candidate_provider,
            renderer=active_renderer,
            candidate_reranker=self._candidate_reranker(
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
            ),
            debug=True,
        )
        runtime_latency_ms = round((perf_counter() - started) * 1000.0, 3)
        if result.get("status") == "ok" and isinstance(result.get("reader_view"), dict):
            sanitized_reader_view, reader_visible_language_debug = sanitize_reader_visible_payload(dict(result["reader_view"] or {}))
            result["reader_view"] = sanitized_reader_view
            if isinstance(result.get("rendered_scene"), dict):
                rendered_debug = dict((result["rendered_scene"].get("debug") or {}))
                rendered_debug["reader_visible_language_debug"] = reader_visible_language_debug
                result["rendered_scene"] = {
                    **dict(result["rendered_scene"] or {}),
                    "debug": rendered_debug,
                }
        if result["status"] != "ok":
            self.observability.record_runtime_receipt(
                surface="reader",
                action="continue_story",
                response_status=str(result["status"]),
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                session_id=command.session_id,
                account_id=account_id,
                reader_id=reader_id,
                candidate_batch=result.get("candidate_batch"),
                rendered_scene=result.get("rendered_scene"),
                reader_view=result.get("reader_view"),
                estimated_cost=0.0,
                runtime_latency_ms=runtime_latency_ms,
            )
            if prior_quality_trace_id:
                try:
                    self._record_quality_feedback_item(
                        feedback_type="retry_after_quality_guard",
                        signal="retry",
                        source_surface="reader",
                        account_id=account_id,
                        world_version_id=runtime.world_version_id,
                        session_id=command.session_id,
                        trace_id=prior_quality_trace_id,
                        source_ref={"kind": "session", "session_id": command.session_id, "account_id": account_id},
                        payload={"result_status": str(result["status"]), "retry_trigger": "continue_story"},
                    )
                except Exception:
                    pass
            return {
                "session_id": command.session_id,
                "world_id": runtime.worldpack.world_id,
                "world_version_id": runtime.world_version_id,
                "status": result["status"],
                "paywall": access,
                "continuity_contract": build_reader_continuity_contract(
                    status=str(result["status"]),
                    session_id=command.session_id,
                    paywall=access,
                ),
            }

        updated_state = NarrativeState.from_dict(result["updated_state"])
        chapter_task = dict((result.get("chapter_plan") or {}).get("chapter_task") or {})
        coverage_context = {
            "selected_event_ids": list((result.get("chapter_plan") or {}).get("selected_event_ids", [])),
            "scene_beats": list(result.get("scene_beats") or []),
            "chapter_task": chapter_task,
        }
        repaired_reader_view, updated_state, long_route_quality_debug = apply_long_route_quality_controls(
            dict(result.get("reader_view") or {}),
            state_before=state_before,
            state_after=updated_state,
            coverage_context=coverage_context,
        )
        repaired_reader_view = merge_choice_impacts_into_reader_view(
            repaired_reader_view,
            routes=result.get("routes") or [],
            chapter_index=int(updated_state.chapter_index or 0),
        )
        result["reader_view"] = repaired_reader_view
        result["updated_state"] = updated_state.to_dict()
        if isinstance(result.get("rendered_scene"), dict):
            rendered_debug = dict((result["rendered_scene"].get("debug") or {}))
            rendered_debug["long_route_quality_controls"] = long_route_quality_debug
            result["rendered_scene"] = {
                **dict(result["rendered_scene"] or {}),
                "debug": rendered_debug,
            }
        body = str(result["reader_view"].get("body") or "")
        lint_report = lint_chapter_draft(body)
        target_chapters = int(getattr(getattr(runtime.worldpack, "series_plan", None), "total_chapter_target", 0) or 100)
        quality_bundle = evaluate_persisted_chapter(
            chapter_id="chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
            world_version_id=runtime.world_version_id,
            session_id=command.session_id,
            body=body,
            paragraphs=body.split("\n\n"),
            dialogue_count=int(lint_report["dialogue_count"]),
            action_count=int(lint_report["action_count"]),
            detail_count=int(lint_report["detail_count"]),
            character_fidelity_score=max(
                [item["components"].get("character_fidelity", 0.0) for item in result["scored_candidates"]],
                default=0.0,
            ),
            state_after=updated_state,
            ending_ready=bool((result.get("chapter_plan") or {}).get("ending_ready")),
            chapter_title=result["reader_view"].get("chapter_title"),
            recap=result["reader_view"].get("recap"),
            relationship_hints=list(result["reader_view"].get("relationship_hints") or []),
            choices=result["reader_view"]["choices"],
            paywall_required=bool(access["required"]),
            coverage_context=coverage_context,
            target_words=self._effective_target_words(
                chapter_task.get("target_words"),
                chapter_index=int(updated_state.chapter_index or 0),
                story_phase=str(updated_state.story_phase or ""),
            ),
            min_target_words=self._effective_min_target_words(
                runtime,
                chapter_index=int(updated_state.chapter_index or 0),
                story_phase=str(updated_state.story_phase or ""),
            ),
            chapter_index=int(updated_state.chapter_index or 0),
            target_chapters=target_chapters,
            story_phase=str(updated_state.story_phase or ""),
            rolling_quality_window=list((state_before.metadata or {}).get("quality_contract_window", [])),
            enforcement_scope="reader_session_generation",
        )
        grounding_check = build_grounding_check(
            scenario_id="reader_continue",
            text=body,
            source_surface="reader",
            world_version_id=runtime.world_version_id,
            session_id=command.session_id,
            chapter_id="chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
            coverage_context=coverage_context,
            state_after=updated_state,
            worldpack_payload=runtime.worldpack.to_dict() if hasattr(runtime.worldpack, "to_dict") else None,
        )
        quality_bundle = enforce_grounding_quality_gate(
            quality_bundle,
            grounding_check=grounding_check,
            source_surface="reader",
        )
        worldpack_payload = runtime.worldpack.to_dict() if hasattr(runtime.worldpack, "to_dict") else None
        quality_bundle = enforce_generation_hard_constraints(
            quality_bundle,
            reader_view=dict(result.get("reader_view") or {}),
            grounding_check=grounding_check,
            source_surface="reader",
            target_chapters=target_chapters,
            worldpack_payload=worldpack_payload,
            repair_report=long_route_quality_debug,
        )
        quality_records = {}
        try:
            quality_records = persist_guardrail_records(
                self.repository,
                quality_bundle=quality_bundle,
                scenario_id="reader_continue",
                source_surface="reader",
                source_ref={
                    "kind": "chapter",
                    "chapter_id": "chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
                    "session_id": command.session_id,
                    "rendered_text": body,
                },
                world_version_id=runtime.world_version_id,
                session_id=command.session_id,
                chapter_id="chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
                coverage_context=coverage_context,
                state_after=updated_state,
                worldpack_payload=worldpack_payload,
            )
        except Exception:
            quality_records = {}
        record_replan_debt(
            updated_state,
            chapter_index=int(updated_state.chapter_index or 0),
            issue_codes=[issue.issue_code for issue in quality_bundle["report"].issues],
        )
        if not quality_bundle["quality_gate"]["ok"]:
            self.analytics.track(
                "chapter_quality_guard_failed",
                reader_id=reader_id,
                account_id=account_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                chapter_index=updated_state.chapter_index,
                access_tier=access.get("access_tier"),
                payload_json={
                    "surface": "reader_session_generation",
                    "quality_gate": quality_bundle["quality_gate"],
                },
            )
            self.observability.record_runtime_receipt(
                surface="reader",
                action="continue_story",
                response_status="quality_guard_failed",
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                session_id=command.session_id,
                account_id=account_id,
                reader_id=reader_id,
                candidate_batch=result.get("candidate_batch"),
                rendered_scene=result.get("rendered_scene"),
                reader_view=None,
                estimated_cost=0.0,
                runtime_latency_ms=runtime_latency_ms,
                trace_id=quality_records.get("trace_id"),
                quality_event_id=(quality_records.get("event") or {}).get("event_id"),
            )
            try:
                self._record_quality_feedback_item(
                    feedback_type="quality_guard_failed",
                    signal="negative_proxy",
                    source_surface="reader",
                    account_id=account_id,
                    world_version_id=runtime.world_version_id,
                    session_id=command.session_id,
                    chapter_id="chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
                    trace_id=quality_records.get("trace_id"),
                    source_ref={
                        "kind": "chapter",
                        "chapter_id": "chapter_%s_%s" % (command.session_id, updated_state.chapter_index),
                        "session_id": command.session_id,
                        "account_id": account_id,
                    },
                    payload={
                        "result_status": "quality_guard_failed",
                        "enforced_decision": quality_bundle["quality_gate"].get("enforced_decision"),
                    },
                )
                if prior_quality_trace_id:
                    self._record_quality_feedback_item(
                        feedback_type="retry_after_quality_guard",
                        signal="retry",
                        source_surface="reader",
                        account_id=account_id,
                        world_version_id=runtime.world_version_id,
                        session_id=command.session_id,
                        trace_id=prior_quality_trace_id,
                        source_ref={"kind": "session", "session_id": command.session_id, "account_id": account_id},
                        payload={"result_status": "quality_guard_failed", "retry_trigger": "continue_story"},
                    )
            except Exception:
                pass
            return {
                "session_id": command.session_id,
                "world_id": runtime.worldpack.world_id,
                "world_version_id": runtime.world_version_id,
                "status": "quality_guard_failed",
                "code": quality_bundle["quality_gate"]["code"],
                "quality_gate": quality_bundle["quality_gate"],
                "paywall": access,
                "reader_view": None,
                "updated_state_summary": None,
                "replay_preview": result.get("replay_preview"),
                "quality_trace_id": quality_records.get("trace_id"),
                "continuity_contract": build_reader_continuity_contract(
                    status="quality_guard_failed",
                    session_id=command.session_id,
                    paywall=access,
                    quality_gate=quality_bundle["quality_gate"],
                ),
            }
        updated_state.metadata = {
            **dict(updated_state.metadata or {}),
            "quality_contract_window": list(quality_bundle["quality_gate"].get("quality_contract_window") or []),
        }
        step_record = StepRecord.from_dict(
            {
                "session_id": command.session_id,
                "step_index": updated_state.chapter_index,
                "player_input": player_input,
                "intent_vector": dict(state_before.player_intent),
                "candidate_batch": result["candidate_batch"],
                "scored_candidates": result["scored_candidates"],
                "routes": result["routes"],
                "chosen_event": result["chosen_event"],
                "chapter_plan": result["chapter_plan"],
                "scene_beats": result["scene_beats"],
                "scene_render_spec": result["scene_render_spec"],
                "rendered_scene": result["rendered_scene"],
                "reader_view": result["reader_view"],
                "state_before": state_before.to_dict(),
                "state_after": updated_state.to_dict(),
                "critic_trace": result["critic_trace"],
                "promise_ledger_snapshot": [promise.to_dict() for promise in updated_state.open_promises],
                "metadata": {
                    "access_tier": access["access_tier"],
                    "assisted_rerank_receipts": list(result.get("assisted_rerank_receipts") or []),
                    "steering_directive": dict(command.steering_directive or {}),
                    "steering_checkpoint": steering_checkpoint,
                    "reader_visible_language_debug": dict(
                        ((result.get("rendered_scene") or {}).get("debug") or {}).get("reader_visible_language_debug") or {}
                    ),
                },
            }
        )
        chapter_id = "chapter_%s_%s" % (command.session_id, updated_state.chapter_index)
        consumed_access = self.billing.consume_entitlement(
            command.session_id,
            reader_id=reader_id,
            account_id=account_id,
            access=access,
        )
        snapshot = self._entitlement_snapshot(consumed_access)
        self.repository.save_step(
            step_record,
            world_version_id=runtime.world_version_id,
            entitlements_snapshot=snapshot,
            cost_estimate=round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3),
        )
        if (command.choice_id or command.freeform_intent or command.steering_directive) and source_chapter_index > 0:
            source_chapter_id = "chapter_%s_%s" % (command.session_id, source_chapter_index)
            try:
                self.repository.save_route_choice(
                    session_id=command.session_id,
                    chapter_id=source_chapter_id,
                    choice_id=command.choice_id or "director_intent",
                    payload_json={
                        "choice_id": command.choice_id,
                        "freeform_intent": command.freeform_intent,
                        "steering_directive": dict(command.steering_directive or {}),
                        "source_chapter_index": source_chapter_index,
                        "generated_chapter_index": int(updated_state.chapter_index or 0),
                    },
                )
            except Exception:
                pass
        self.repository.update_session_entitlements_snapshot(command.session_id, snapshot)
        self.repository.save_evaluation_report(chapter_id, quality_bundle["report"])
        self.billing.meter_action(
            surface="reader",
            action_name="continue_story",
            account_id=account_id,
            reader_id=reader_id,
            session_id=command.session_id,
            chapter_id=chapter_id,
            world_version_id=runtime.world_version_id,
            access=consumed_access,
            charged_units=None if consumed_access.get("reason") == "credits_consumed" else 0.0,
            estimated_cost=0.0,
        )
        self.analytics.track(
            "continue_story",
            reader_id=reader_id,
            session_id=command.session_id,
            world_id=runtime.worldpack.world_id,
            world_version_id=runtime.world_version_id,
            chapter_index=updated_state.chapter_index,
            access_tier=consumed_access.get("access_tier"),
            payload_json=snapshot,
        )
        if consumed_access.get("reason") == "credits_consumed":
            self.analytics.track(
                "story_credits_consumed",
                reader_id=reader_id,
                account_id=account_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                chapter_index=updated_state.chapter_index,
                access_tier=consumed_access.get("access_tier"),
                payload_json=snapshot,
            )
            self.analytics.track(
                "credits_consumed",
                reader_id=reader_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                chapter_index=updated_state.chapter_index,
                access_tier=consumed_access.get("access_tier"),
                payload_json=snapshot,
            )
        self.analytics.track(
            "chapter_rendered",
            reader_id=reader_id,
            session_id=command.session_id,
            world_id=runtime.worldpack.world_id,
            world_version_id=runtime.world_version_id,
            chapter_index=updated_state.chapter_index,
            access_tier=consumed_access.get("access_tier"),
        )
        self.analytics.track(
            "chapter_evaluated",
            reader_id=reader_id,
            session_id=command.session_id,
            world_id=runtime.worldpack.world_id,
            world_version_id=runtime.world_version_id,
            chapter_id=chapter_id,
            decision=quality_bundle["report"].decision.decision,
            overall_score=quality_bundle["report"].scores.overall_score,
            access_tier=consumed_access.get("access_tier"),
        )
        for receipt in result.get("assisted_rerank_receipts") or []:
            self.analytics.track(
                "learned_assisted_rerank_evaluated",
                reader_id=reader_id,
                account_id=account_id,
                session_id=command.session_id,
                world_id=runtime.worldpack.world_id,
                world_version_id=runtime.world_version_id,
                chapter_index=updated_state.chapter_index,
                access_tier=consumed_access.get("access_tier"),
                payload_json=receipt,
            )
            if receipt.get("assisted_action") == "rerank_top_candidate":
                self.analytics.track(
                    "learned_assisted_rerank_applied",
                    reader_id=reader_id,
                    account_id=account_id,
                    session_id=command.session_id,
                    world_id=runtime.worldpack.world_id,
                    world_version_id=runtime.world_version_id,
                    chapter_index=updated_state.chapter_index,
                    access_tier=consumed_access.get("access_tier"),
                    payload_json=receipt,
                )
        if self.illustration is not None:
            self.illustration.ensure_chapter_hero(
                session_id=command.session_id,
                reader_id=reader_id,
                world_version_id=runtime.world_version_id,
                chapter_index=int(updated_state.chapter_index or 0),
                rendered_scene=dict(result.get("rendered_scene") or {}),
            )
        runtime_cost = round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3)
        self.observability.record_runtime_receipt(
            surface="reader",
            action="continue_story",
            response_status="ok",
            world_id=runtime.worldpack.world_id,
            world_version_id=runtime.world_version_id,
            session_id=command.session_id,
            account_id=account_id,
            reader_id=reader_id,
            candidate_batch=result.get("candidate_batch"),
            rendered_scene=result.get("rendered_scene"),
            reader_view=result.get("reader_view"),
            estimated_cost=runtime_cost,
            runtime_latency_ms=runtime_latency_ms,
            trace_id=quality_records.get("trace_id"),
            quality_event_id=(quality_records.get("event") or {}).get("event_id"),
        )
        if prior_quality_trace_id:
            try:
                self._record_quality_feedback_item(
                    feedback_type="retry_after_quality_guard",
                    signal="retry",
                    source_surface="reader",
                    account_id=account_id,
                    world_version_id=runtime.world_version_id,
                    session_id=command.session_id,
                    trace_id=prior_quality_trace_id,
                    source_ref={"kind": "session", "session_id": command.session_id, "account_id": account_id},
                    payload={"result_status": "ok", "retry_trigger": "continue_story"},
                )
            except Exception:
                pass
        choice_impacts = build_choice_impacts(
            result["reader_view"].get("choices") or [],
            reader_view=result["reader_view"],
            routes=result.get("routes") or [],
            chapter_index=int(updated_state.chapter_index or 0),
        )
        impact_by_id = {str(item.get("choice_id")): item for item in choice_impacts}
        chapter_view = {
            "sessionId": command.session_id,
            "worldId": runtime.worldpack.world_id,
            "worldVersionId": runtime.world_version_id,
            "quality_trace_id": quality_records.get("trace_id"),
            "chapterId": chapter_id,
            "chapterIndex": updated_state.chapter_index,
            "chapterTitle": result["reader_view"]["chapter_title"],
            "recap": result["reader_view"]["recap"],
            "body": result["reader_view"]["body"],
            "relationshipHints": result["reader_view"]["relationship_hints"],
            "choice_impacts": choice_impacts,
            "choices": [
                {
                    "choiceId": "choice_%s_%s" % (updated_state.chapter_index, index),
                    "text": choice_text,
                    "motive": result["reader_view"]["scene_card"].get("summary", ""),
                    "emotionalCost": "命运继续收紧",
                    "accessTier": "free" if consumed_access["access_tier"] == "free" else ("subscriber" if consumed_access["access_tier"] == "subscriber" else "paid"),
                    "priceHint": 0 if consumed_access["access_tier"] in {"free", "subscriber"} else consumed_access["quote"],
                    "impact": impact_by_id.get("choice_%s_%s" % (updated_state.chapter_index, index), {}),
                }
                for index, choice_text in enumerate(result["reader_view"]["choices"], start=1)
            ],
            "canContinue": result["reader_view"]["can_continue"],
            "paywall": {
                "required": False,
                "reason": consumed_access["reason"],
                "quote": consumed_access["quote"],
                "access_tier": consumed_access["access_tier"],
                "balance": consumed_access.get("balance"),
                "entitlement_type": consumed_access.get("entitlement_type"),
                "status": consumed_access.get("status"),
            },
        }
        return {
            "session_id": command.session_id,
            "reader_id": reader_id,
            "world_id": runtime.worldpack.world_id,
            "world_version_id": runtime.world_version_id,
            "quality_trace_id": quality_records.get("trace_id"),
            "chapter_view": chapter_view,
            "reader_view": result["reader_view"],
            "chosen_event": result.get("chosen_event"),
            "updated_state": updated_state.to_dict(),
            "updated_state_summary": result["updated_state_summary"],
            "replay_preview": result.get("replay_preview"),
            "paywall": {
                "required": False,
                "access_tier": consumed_access["access_tier"],
                "quote": consumed_access["quote"],
                "reason": consumed_access["reason"],
                "balance": consumed_access.get("balance"),
                "entitlement_type": consumed_access.get("entitlement_type"),
                "status": consumed_access.get("status"),
            },
            "candidate_batch": result.get("candidate_batch"),
            "scored_candidates": result.get("scored_candidates"),
            "critic_trace": result.get("critic_trace"),
            "rendered_scene": result.get("rendered_scene"),
            "routes": result.get("routes"),
            "chapter_plan": result.get("chapter_plan"),
            "scene_beats": result.get("scene_beats"),
            "scene_render_spec": result.get("scene_render_spec"),
            "status": "ok",
            "steering_checkpoint": steering_checkpoint or dict(updated_state.storyline_checkpoint or {}),
            "replan_checkpoint": dict(updated_state.replan_checkpoint or {}),
            "continuity_contract": build_reader_continuity_contract(
                status="ok",
                session_id=command.session_id,
                paywall={
                    "required": False,
                    "access_tier": consumed_access.get("access_tier"),
                },
            ),
        }
