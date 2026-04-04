from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Optional

from ..core.linter import lint_chapter_draft
from ..intent import SimpleIntentParser
from ..models import CandidateBatch, NarrativeState, StepRecord
from ..pipeline import plan_next_turn
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..providers import StaticCandidateProvider
from ..rendering import TemplateRenderer
from ..eval.service import evaluate_chapter
from .analytics import AnalyticsService
from .billing import BillingService
from .observability import ObservabilityService
from .provider_routing import ProviderRoutingService


class ReaderContinueCommand:
    def __init__(self, session_id: str, choice_id: str | None = None, freeform_intent: str | None = None) -> None:
        self.session_id = session_id
        self.choice_id = choice_id
        self.freeform_intent = freeform_intent


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
    ) -> None:
        self.repository = repository
        self.intent_parser = intent_parser or SimpleIntentParser()
        self.renderer = renderer or TemplateRenderer()
        self.billing = billing_service or BillingService(repository)
        self.analytics = analytics_service or AnalyticsService(repository)
        self.observability = observability_service or ObservabilityService(repository)
        self.provider_routing = provider_routing_service

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

    def create_session(self, world_id: str, reader_id: str | None = None) -> dict[str, Any]:
        world = next((item for item in self.repository.list_worlds() if item["world_id"] == world_id), None)
        if world is None:
            raise KeyError("unknown_world:%s" % world_id)
        runtime = self.repository.get_runtime_bundle(world["latest_version"])
        session = self.repository.create_session_record(
            world_version_id=runtime.world_version_id,
            initial_state=runtime.initial_state,
            reader_id=reader_id,
            metadata={
                "source": "beta_reader",
                "account_id": self.billing.resolve_account_id(reader_id=reader_id),
            },
            entitlements_snapshot={"access_tier": "trial"},
        )
        access = self.billing.access_check(
            session.session_id,
            reader_id=reader_id,
            account_id=self.billing.resolve_account_id(reader_id=reader_id),
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
        return {
            "session_id": session.session_id,
            "reader_id": reader_id,
            "account_id": self.billing.resolve_account_id(reader_id=reader_id),
            "world_id": world_id,
            "world_version_id": runtime.world_version_id,
            "current_state": session.current_state.to_dict(),
            "paywall": access,
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
            return {
                "session_id": command.session_id,
                "world_id": runtime.worldpack.world_id,
                "world_version_id": runtime.world_version_id,
                "chapter_view": latest_step.reader_view.to_dict() if latest_step and latest_step.reader_view else None,
                "paywall": access,
                "status": blocked_status,
            }

        state_before = NarrativeState.from_dict(session_record.current_state.to_dict())
        player_input = command.freeform_intent or command.choice_id or "继续读下去。"
        state_before.player_intent = self.intent_parser.parse(player_input)
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
            return {
                "session_id": command.session_id,
                "world_id": runtime.worldpack.world_id,
                "world_version_id": runtime.world_version_id,
                "status": result["status"],
                "paywall": access,
            }

        updated_state = NarrativeState.from_dict(result["updated_state"])
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
        self.repository.update_session_entitlements_snapshot(command.session_id, snapshot)
        lint_report = lint_chapter_draft(result["reader_view"]["body"])
        evaluation_report = evaluate_chapter(
            chapter_id=chapter_id,
            world_version_id=runtime.world_version_id,
            session_id=command.session_id,
            body=result["reader_view"]["body"],
            paragraphs=result["reader_view"]["body"].split("\n\n"),
            dialogue_count=int(lint_report["dialogue_count"]),
            action_count=int(lint_report["action_count"]),
            detail_count=int(lint_report["detail_count"]),
            character_fidelity_score=max(
                [item["components"].get("character_fidelity", 0.0) for item in result["scored_candidates"]],
                default=0.0,
            ),
            state_after=updated_state,
            ending_ready=bool(result["chapter_plan"]["ending_ready"]) if result.get("chapter_plan") else False,
            choices=result["reader_view"]["choices"],
            paywall_required=bool(access["required"]),
        )
        self.repository.save_evaluation_report(chapter_id, evaluation_report)
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
            decision=evaluation_report.decision.decision,
            overall_score=evaluation_report.scores.overall_score,
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
        )
        chapter_view = {
            "sessionId": command.session_id,
            "worldId": runtime.worldpack.world_id,
            "worldVersionId": runtime.world_version_id,
            "chapterId": chapter_id,
            "chapterIndex": updated_state.chapter_index,
            "chapterTitle": result["reader_view"]["chapter_title"],
            "recap": result["reader_view"]["recap"],
            "body": result["reader_view"]["body"],
            "relationshipHints": result["reader_view"]["relationship_hints"],
            "choices": [
                {
                    "choiceId": "choice_%s_%s" % (updated_state.chapter_index, index),
                    "text": choice_text,
                    "motive": result["reader_view"]["scene_card"].get("summary", ""),
                    "emotionalCost": "命运继续收紧",
                    "accessTier": "free" if consumed_access["access_tier"] == "free" else ("subscriber" if consumed_access["access_tier"] == "subscriber" else "paid"),
                    "priceHint": 0 if consumed_access["access_tier"] in {"free", "subscriber"} else consumed_access["quote"],
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
            "chapter_view": chapter_view,
            "reader_view": result["reader_view"],
            "updated_state_summary": result["updated_state_summary"],
            "paywall": {
                "required": False,
                "access_tier": consumed_access["access_tier"],
                "quote": consumed_access["quote"],
                "reason": consumed_access["reason"],
                "balance": consumed_access.get("balance"),
                "entitlement_type": consumed_access.get("entitlement_type"),
                "status": consumed_access.get("status"),
            },
            "status": "ok",
        }
