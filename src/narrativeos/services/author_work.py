from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..core.linter import lint_chapter_draft, story_text_unit_count
from ..eval.service import (
    CHAPTER_QUALITY_GUARD_FAILURE_CODE,
    ChapterQualityGuardError,
    apply_quality_gate_to_report,
    evaluate_chapter,
    evaluate_persisted_chapter,
)
from ..eval.reporting import aggregate_reports
from ..eval.taxonomy import ISSUE_TAXONOMY
from ..models import EvaluationReport
from ..longform import apply_steering_directive, configure_interactive_longform_runtime, configure_longform_runtime
from ..models import NarrativeState
from ..pipeline import plan_next_turn
from ..providers import StaticCandidateProvider
from ..quality.adapter import persist_guardrail_records
from ..rendering import TemplateRenderer
from ..sanitizer import sanitize_reader_visible_payload
from ..worldpacks.registry import FileSystemWorldRegistry
from .authoring import (
    AuthoringService,
    _default_memory_compression_policy,
    _default_steering_guardrails,
    _resolve_longform_structure,
)
from .choice_semantics import build_choice_impacts
from .provider_routing import ProviderRoutingService
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .analytics import AnalyticsService


VALID_AUTHOR_WORK_STATUSES = {"draft", "review_ready", "submitted", "approved", "needs_changes"}
VALID_AUTHOR_WORK_CHAPTER_STATUSES = {"generated", "edited", "needs_review"}
VALID_AUTHOR_WORK_GENERATION_MODES = {"first", "next", "arc"}


def _trim_generated_author_work_body(
    body: str,
    *,
    min_units: int = 1800,
    max_units: int = 2200,
) -> str:
    paragraphs = [str(item).strip() for item in str(body or "").split("\n\n") if str(item).strip()]
    if not paragraphs:
        return str(body or "")
    current_body = "\n\n".join(paragraphs)
    current_units = story_text_unit_count(current_body)
    if current_units <= max_units:
        return current_body
    while len(paragraphs) > 2 and current_units > max_units:
        trimmed = False
        for index in range(len(paragraphs) - 2, 0, -1):
            candidate_paragraphs = paragraphs[:index] + paragraphs[index + 1 :]
            candidate_body = "\n\n".join(candidate_paragraphs)
            candidate_units = story_text_unit_count(candidate_body)
            if candidate_units < min_units:
                continue
            paragraphs = candidate_paragraphs
            current_body = candidate_body
            current_units = candidate_units
            trimmed = True
            if current_units <= max_units:
                return current_body
            break
        if not trimmed:
            break
    return current_body


class AuthorWorkService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        registry: Optional[FileSystemWorldRegistry] = None,
        provider_routing_service: Optional[ProviderRoutingService] = None,
        analytics_service: Optional[AnalyticsService] = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or FileSystemWorldRegistry()
        self.provider_routing = provider_routing_service
        self.analytics = analytics_service or AnalyticsService(repository)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _work_title(self, worldpack: Dict[str, Any], world_version_id: str) -> str:
        return str(worldpack.get("title") or worldpack.get("world_id") or world_version_id)

    def _target_chapter_count(self, worldpack: Dict[str, Any]) -> int:
        return int(((worldpack.get("series_plan") or {}).get("total_chapter_target")) or 0)

    def _normalized_work_branch(self, work: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(work or {})
        work_id = str(payload.get("work_id") or "")
        root_work_id = str(payload.get("root_work_id") or work_id)
        return {
            **payload,
            "branch_id": str(payload.get("branch_id") or work_id),
            "root_work_id": root_work_id,
            "parent_work_id": payload.get("parent_work_id"),
            "branch_name": str(payload.get("branch_name") or ("主线" if root_work_id == work_id else "平行宇宙")),
            "branch_kind": str(payload.get("branch_kind") or ("mainline" if root_work_id == work_id else "parallel_universe")),
            "branch_origin_label": payload.get("branch_origin_label"),
            "fork_after_chapter_index": int(payload.get("fork_after_chapter_index", 0) or 0),
            "is_active_line": bool(payload.get("is_active_line", root_work_id == work_id)),
        }

    def _ensure_work_branch_metadata(self, work: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalized_work_branch(work)
        if (
            work.get("branch_id") == normalized["branch_id"]
            and work.get("root_work_id") == normalized["root_work_id"]
            and work.get("parent_work_id") == normalized["parent_work_id"]
            and work.get("branch_name") == normalized["branch_name"]
            and work.get("branch_kind") == normalized["branch_kind"]
            and work.get("branch_origin_label") == normalized["branch_origin_label"]
            and int(work.get("fork_after_chapter_index", 0) or 0) == normalized["fork_after_chapter_index"]
            and bool(work.get("is_active_line")) == normalized["is_active_line"]
        ):
            return normalized
        persisted = self.repository.save_author_work({**work, **normalized})
        return self._normalized_work_branch(persisted)

    def _branch_family(self, work: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized = self._normalized_work_branch(work)
        family = self.repository.list_author_works(root_work_id=normalized["root_work_id"], limit=100)
        ordered = sorted(
            [self._normalized_work_branch(item) for item in family],
            key=lambda item: (
                0 if item["branch_kind"] == "mainline" else 1,
                0 if item["is_active_line"] else 1,
                item["fork_after_chapter_index"],
                item.get("created_at") or "",
            ),
        )
        return [
            {
                "work_id": item["work_id"],
                "branch_id": item["branch_id"],
                "root_work_id": item["root_work_id"],
                "parent_work_id": item.get("parent_work_id"),
                "branch_name": item["branch_name"],
                "branch_kind": item["branch_kind"],
                "branch_origin_label": item.get("branch_origin_label"),
                "fork_after_chapter_index": item["fork_after_chapter_index"],
                "is_active_line": item["is_active_line"],
                "chapter_count": item.get("chapter_count", 0),
                "target_chapter_count": item.get("target_chapter_count", 0),
                "status": item.get("status"),
                "updated_at": item.get("updated_at"),
            }
            for item in ordered
        ]

    def _work_snapshot(self, work: Dict[str, Any], chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_work = self._normalized_work_branch(work)
        return {
            "work": {
                "work_id": normalized_work.get("work_id"),
                "world_version_id": normalized_work.get("world_version_id"),
                "account_id": normalized_work.get("account_id"),
                "title": normalized_work.get("title"),
                "status": normalized_work.get("status"),
                "current_revision": normalized_work.get("current_revision"),
                "chapter_count": normalized_work.get("chapter_count"),
                "target_chapter_count": normalized_work.get("target_chapter_count"),
                "branch_id": normalized_work.get("branch_id"),
                "root_work_id": normalized_work.get("root_work_id"),
                "parent_work_id": normalized_work.get("parent_work_id"),
                "branch_name": normalized_work.get("branch_name"),
                "branch_kind": normalized_work.get("branch_kind"),
                "branch_origin_label": normalized_work.get("branch_origin_label"),
                "fork_after_chapter_index": normalized_work.get("fork_after_chapter_index"),
                "is_active_line": normalized_work.get("is_active_line"),
                "diagnostics_summary_json": dict(normalized_work.get("diagnostics_summary_json") or {}),
            },
            "chapters": [
                {
                    "chapter_index": item.get("chapter_index"),
                    "chapter_title": item.get("chapter_title"),
                    "status": item.get("status"),
                    "source_type": item.get("source_type"),
                    "summary": item.get("summary"),
                }
                for item in chapters
            ],
        }

    def _revision(self, *, work: Dict[str, Any], chapters: List[Dict[str, Any]], revision_type: str, summary: str) -> Dict[str, Any]:
        revision = self.repository.save_author_work_revision(
            {
                "work_id": work["work_id"],
                "revision_type": revision_type,
                "summary": summary,
                "snapshot_json": self._work_snapshot(work, chapters),
            }
        )
        updated = self.repository.save_author_work(
            {
                **work,
                "current_revision": revision["revision_id"],
            }
        )
        return updated

    def _quality_gate_min_target_words(self, runtime_context: Dict[str, Any]) -> Optional[int]:
        chapter_budget_policy = dict((runtime_context.get("longform_structure") or {}).get("chapter_budget_policy") or {})
        if chapter_budget_policy.get("min_target_words") is None:
            return None
        return int(chapter_budget_policy.get("min_target_words") or 0)

    def _record_quality_guard_failure(
        self,
        *,
        work: Dict[str, Any],
        chapters: List[Dict[str, Any]],
        chapter_index: int,
        surface: str,
        quality_gate: Dict[str, Any],
    ) -> None:
        self.repository.save_author_work_revision(
            {
                "work_id": work["work_id"],
                "revision_type": "quality_guard_blocked",
                "summary": f"章节硬约束拦截 · 第 {chapter_index} 章 · {surface}",
                "snapshot_json": {
                    **self._work_snapshot(work, chapters),
                    "quality_gate": dict(quality_gate or {}),
                    "surface": surface,
                    "chapter_index": chapter_index,
                    "repair_loop_context": {
                        "issue_code": str(quality_gate.get("primary_issue_group") or ""),
                        "issue_label": str(
                            ISSUE_TAXONOMY.get(str(quality_gate.get("primary_issue_group") or ""), {}).get("label")
                            or quality_gate.get("primary_issue_group")
                            or ""
                        ),
                        "asset_type": str((quality_gate.get("primary_asset_target") or {}).get("asset_type") or ""),
                        "asset_label": str((quality_gate.get("primary_asset_target") or {}).get("asset_label") or ""),
                        "target_label": str((quality_gate.get("primary_asset_target") or {}).get("asset_type") or ""),
                        "validation_panel": str((quality_gate.get("primary_asset_target") or {}).get("validation_panel") or ""),
                        "validation_panel_label": str((quality_gate.get("primary_asset_target") or {}).get("validation_panel_label") or ""),
                        "window_breach_kind": str(quality_gate.get("window_breach_kind") or ""),
                        "chapter_index": chapter_index,
                        "targeted_chapter_indices": [chapter_index],
                    },
                },
            }
        )

    def _runtime_context(self, *, world_version_id: str) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        runtime = self.repository.get_runtime_bundle(world_version_id)
        worldpack_payload = dict(version.worldpack_json or {})
        longform_structure = _resolve_longform_structure(
            worldpack_payload=worldpack_payload,
            runtime_world_title=runtime.world_record.world.title,
            max_chapters=max(24, self._target_chapter_count(worldpack_payload) or 24),
        )
        return {
            "version": version,
            "runtime": runtime,
            "worldpack": worldpack_payload,
            "longform_structure": longform_structure,
        }

    def _configured_state(self, *, work: Dict[str, Any], runtime_context: Dict[str, Any]) -> NarrativeState:
        runtime = runtime_context["runtime"]
        worldpack = runtime_context["worldpack"]
        longform = runtime_context["longform_structure"]
        state_payload = dict(work.get("narrative_state_json") or {})
        if state_payload:
            state = NarrativeState.from_dict(state_payload)
        else:
            state = NarrativeState.from_dict(runtime.initial_state.to_dict())
        configure_longform_runtime(
            state,
            series_plan=dict(longform.get("series_plan") or {}),
            volume_plans=list(longform.get("volume_plans") or []),
            arc_plans=list(longform.get("arc_plans") or []),
            chapter_budget_policy=dict(longform.get("chapter_budget_policy") or {}),
            memory_compression_policy=dict(
                worldpack.get("memory_compression_policy")
                or _default_memory_compression_policy(len(longform.get("volume_plans") or []))
            ),
            world=runtime.world_record.world,
        )
        configure_interactive_longform_runtime(
            state,
            series_storyline_contract=dict(worldpack.get("series_storyline_contract") or {}),
            character_memory_profiles=dict(worldpack.get("character_memory_profiles") or {}),
            steering_guardrails={
                **_default_steering_guardrails(),
                **dict(worldpack.get("steering_guardrails") or {}),
            },
        )
        state.metadata = {
            **dict(state.metadata or {}),
            "authoring_surface": "author_work_generation",
        }
        return state

    def _chapter_reports(self, chapters: List[Dict[str, Any]], *, world_version_id: str, work_id: str) -> List[Dict[str, Any]]:
        runtime_context = self._runtime_context(world_version_id=world_version_id)
        min_target_words = self._quality_gate_min_target_words(runtime_context)
        target_chapters = int(
            ((runtime_context.get("longform_structure") or {}).get("series_plan") or {}).get("total_chapter_target")
            or 0
        )
        reports = []
        for chapter in chapters:
            body = str(chapter.get("body") or "")
            if not body.strip():
                continue
            lint = lint_chapter_draft(body)
            state_after_payload = dict(chapter.get("state_snapshot_json") or {})
            if state_after_payload:
                coverage_context = dict((state_after_payload.get("metadata") or {}).get("coverage_context") or {})
                state_after = NarrativeState.from_dict(state_after_payload)
            else:
                coverage_context = {}
                state_after = NarrativeState.from_dict(
                    {
                        "state_id": f"{work_id}::diagnostic::{chapter['chapter_index']}",
                        "world_id": world_version_id,
                        "turn_index": int(chapter.get("chapter_index") or 0),
                        "story_phase": "setup",
                        "chapter_index": int(chapter.get("chapter_index") or 0),
                        "min_end_turn": max(8, int(chapter.get("chapter_index") or 0)),
                        "fate_pressure": 0.1,
                        "karmic_weather": {},
                        "unresolved_debts": [],
                        "world_facts": [],
                        "timeline": [],
                        "characters": {},
                        "relationship_graph": [],
                        "open_promises": [],
                        "tension": 0.0,
                        "themes": {},
                        "player_intent": {},
                        "recent_scene_functions": [],
                        "visited_event_ids": [],
                        "route_fingerprint": [],
                        "rating_ceiling": "PG13",
                    }
                )
            report_bundle = evaluate_persisted_chapter(
                chapter_id=f"{work_id}::{chapter['chapter_index']}",
                world_version_id=world_version_id,
                session_id=f"author_work:{work_id}",
                body=body,
                paragraphs=body.split("\n\n"),
                dialogue_count=int(lint["dialogue_count"]),
                action_count=int(lint["action_count"]),
                detail_count=int(lint["detail_count"]),
                character_fidelity_score=0.75,
                state_after=state_after,
                ending_ready=False,
                chapter_title=chapter.get("chapter_title"),
                choices=list(chapter.get("choices_json") or []),
                paywall_required=False,
                coverage_context={
                    **coverage_context,
                    "chapter_task": dict(chapter.get("chapter_task_json") or {}),
                },
                target_words=(chapter.get("chapter_task_json") or {}).get("target_words"),
                min_target_words=min_target_words,
                chapter_index=int(chapter.get("chapter_index") or 0),
                target_chapters=target_chapters,
                story_phase=str(state_after.story_phase or ""),
                rolling_quality_window=list((state_after.metadata or {}).get("quality_contract_window", [])),
                enforcement_scope="author_work_diagnostics",
            )
            reports.append(apply_quality_gate_to_report(report_bundle["report"], report_bundle["quality_gate"]))
        return reports

    def list_works(self, *, account_id: Optional[str] = None, world_version_id: Optional[str] = None) -> Dict[str, Any]:
        works = self.repository.list_author_works(account_id=account_id, world_version_id=world_version_id)
        return {
            "works": [self._work_detail_payload(item, include_chapters=False) for item in works],
        }

    def list_branches(self, *, work_id: str) -> Dict[str, Any]:
        work = self._ensure_work_branch_metadata(self.repository.get_author_work(work_id))
        return {
            "work_id": work["work_id"],
            "branch_family": self._branch_family(work),
        }

    def activate_branch(self, *, work_id: str) -> Dict[str, Any]:
        work = self._ensure_work_branch_metadata(self.repository.get_author_work(work_id))
        self.repository.set_author_work_active_line(
            root_work_id=work["root_work_id"],
            active_work_id=work["work_id"],
        )
        return self.get_work(work["work_id"])

    def delete_work_family(self, *, work_id: str) -> Dict[str, Any]:
        work = self._ensure_work_branch_metadata(self.repository.get_author_work(work_id))
        deleted = self.repository.delete_author_work_family(root_work_id=work["root_work_id"] or work["work_id"])
        self.analytics.track(
            "author_work_deleted",
            reader_id=work.get("account_id"),
            account_id=work.get("account_id"),
            world_version_id=work.get("world_version_id"),
            payload_json={
                "work_id": work_id,
                "root_work_id": work.get("root_work_id") or work.get("work_id"),
                "deleted_work_count": deleted.get("deleted_work_count"),
            },
        )
        return {
            **deleted,
            "deleted_title": work.get("title") or work.get("branch_name") or work.get("work_id"),
            "deleted_root_work_id": work["root_work_id"] or work["work_id"],
        }

    def _next_parallel_branch_name(self, *, root_work_id: str) -> str:
        family = self.repository.list_author_works(root_work_id=root_work_id, limit=100)
        parallel_count = sum(
            1 for item in family if str(item.get("branch_kind") or "") == "parallel_universe"
        )
        return f"平行宇宙 {parallel_count + 1}"

    def create_branch(
        self,
        *,
        work_id: str,
        source_chapter_index: int,
        label: Optional[str] = None,
        steering_directive: Optional[Dict[str, Any]] = None,
        choice_source: Optional[Any] = None,
    ) -> Dict[str, Any]:
        source_work = self._ensure_work_branch_metadata(self.repository.get_author_work(work_id))
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        max_chapter_index = max((int(item.get("chapter_index") or 0) for item in chapters), default=0)
        fork_after_chapter_index = int(source_chapter_index or 0)
        if fork_after_chapter_index < 0:
            raise ValueError("invalid_branch_source_chapter_index")
        if max_chapter_index and fork_after_chapter_index == 0:
            raise ValueError("branch_requires_existing_chapter_context")
        if fork_after_chapter_index > max_chapter_index:
            raise ValueError("branch_source_chapter_out_of_range")

        runtime_context = self._runtime_context(world_version_id=source_work["world_version_id"])
        if fork_after_chapter_index > 0:
            source_chapter = self.repository.get_author_work_chapter(work_id=work_id, chapter_index=fork_after_chapter_index)
            branch_state = NarrativeState.from_dict(dict(source_chapter.get("state_snapshot_json") or {}))
        else:
            branch_state = self._configured_state(work=source_work, runtime_context=runtime_context)

        directive = dict(steering_directive or {})
        if directive:
            directive.setdefault("summary", str(label or "").strip() or str(choice_source or "").strip() or "平行宇宙引导")
            directive.setdefault("current_user_intent", directive.get("summary"))
            apply_steering_directive(
                branch_state,
                directive,
                world=runtime_context["runtime"].world_record.world,
            )

        branch_name = str(label or "").strip() or self._next_parallel_branch_name(root_work_id=source_work["root_work_id"])
        branch_origin_label = str(choice_source or directive.get("summary") or label or "").strip() or None
        new_work = self.repository.save_author_work(
            {
                "world_version_id": source_work["world_version_id"],
                "account_id": source_work["account_id"],
                "title": source_work["title"],
                "status": "draft",
                "chapter_count": fork_after_chapter_index,
                "target_chapter_count": source_work.get("target_chapter_count", 0),
                "branch_id": f"branch_{uuid4().hex[:12]}",
                "root_work_id": source_work["root_work_id"],
                "parent_work_id": source_work["work_id"],
                "branch_name": branch_name,
                "branch_kind": "parallel_universe",
                "branch_origin_label": branch_origin_label,
                "fork_after_chapter_index": fork_after_chapter_index,
                "is_active_line": True,
                "narrative_state_json": branch_state.to_dict(),
                "diagnostics_summary_json": {},
            }
        )

        for chapter in chapters:
            if int(chapter.get("chapter_index") or 0) > fork_after_chapter_index:
                continue
            self.repository.save_author_work_chapter(
                {
                    **chapter,
                    "chapter_record_id": None,
                    "work_id": new_work["work_id"],
                }
            )

        self.repository.set_author_work_active_line(
            root_work_id=source_work["root_work_id"],
            active_work_id=new_work["work_id"],
        )

        branch_snapshot = self.repository.get_author_work(new_work["work_id"])
        branch_snapshot = self._ensure_work_branch_metadata(branch_snapshot)
        copied_chapters = self.repository.list_author_work_chapters(work_id=new_work["work_id"])
        branch_snapshot = self._revision(
            work=branch_snapshot,
            chapters=copied_chapters,
            revision_type="branch_create",
            summary=f"从第 {fork_after_chapter_index} 章后创建 {branch_name}",
        )
        self.analytics.track(
            "author_work_branch_created",
            reader_id=source_work.get("account_id"),
            account_id=source_work.get("account_id"),
            world_version_id=source_work.get("world_version_id"),
            payload_json={
                "work_id": branch_snapshot.get("work_id"),
                "root_work_id": source_work.get("root_work_id"),
                "parent_work_id": source_work.get("work_id"),
            },
        )
        return self.get_work(branch_snapshot["work_id"])

    def create_work(self, *, world_version_id: str, account_id: str) -> Dict[str, Any]:
        existing = self.repository.list_author_works(account_id=account_id, world_version_id=world_version_id, limit=20)
        reusable = next(
            (
                item
                for item in existing
                if item.get("status") in {"draft", "review_ready", "needs_changes"} and bool(item.get("is_active_line", True))
            ),
            None,
        ) or next((item for item in existing if item.get("status") in {"draft", "review_ready", "needs_changes"}), None)
        if reusable:
            return self.get_work(reusable["work_id"])
        runtime_context = self._runtime_context(world_version_id=world_version_id)
        worldpack = runtime_context["worldpack"]
        state = self._configured_state(
            work={
                "narrative_state_json": dict(runtime_context["runtime"].initial_state.to_dict()),
            },
            runtime_context=runtime_context,
        )
        work = self.repository.save_author_work(
            {
                "world_version_id": world_version_id,
                "account_id": account_id,
                "title": self._work_title(worldpack, world_version_id),
                "status": "draft",
                "chapter_count": 0,
                "target_chapter_count": self._target_chapter_count(worldpack),
                "branch_name": "主线",
                "branch_kind": "mainline",
                "fork_after_chapter_index": 0,
                "is_active_line": True,
                "narrative_state_json": state.to_dict(),
            }
        )
        work = self.repository.save_author_work({**work, "root_work_id": work["work_id"], "branch_id": work["work_id"], "is_active_line": True})
        work = self._revision(work=work, chapters=[], revision_type="initialized", summary="初始化作品稿")
        self.analytics.track(
            "author_work_created",
            reader_id=account_id,
            account_id=account_id,
            world_version_id=world_version_id,
            payload_json={
                "work_id": work.get("work_id"),
                "root_work_id": work.get("root_work_id") or work.get("work_id"),
            },
        )
        return self.get_work(work["work_id"])

    def _normalized_work_diagnostics(self, diagnostics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(diagnostics or {})
        evaluation_summary = dict(payload.get("evaluation_summary") or {})
        latest_decision = payload.get("latest_decision")
        chapter_count = int(payload.get("chapter_count") or 0)
        next_actions: List[str] = []
        for item in payload.get("reports") or []:
            decision = dict((item or {}).get("decision") or {})
            recommendation = str(decision.get("recommended_action") or "").strip()
            if recommendation and recommendation not in next_actions:
                next_actions.append(recommendation)
        if not next_actions:
            next_actions = list(payload.get("next_actions") or evaluation_summary.get("next_actions") or [])
        return {
            "chapter_count": chapter_count,
            "latest_decision": latest_decision,
            "evaluation_summary": evaluation_summary,
            "next_actions": next_actions,
            "raw": payload,
        }

    def _aggregate_work_decision(self, aggregated: Dict[str, Any]) -> str:
        if float(aggregated.get("block_rate", 0.0) or 0.0) > 0.0:
            return "block"
        if float(aggregated.get("rewrite_rate", 0.0) or 0.0) > 0.0:
            return "rewrite"
        return "pass"

    def _normalized_chapter_diagnostics(self, diagnostic_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(diagnostic_summary or {})
        decision = dict(payload.get("decision") or {})
        issues = list(payload.get("issues") or [])
        issue_codes = [
            str(item.get("issue_code"))
            for item in issues
            if isinstance(item, dict) and str(item.get("issue_code") or "").strip()
        ]
        return {
            "decision": decision.get("decision"),
            "recommended_action": decision.get("recommended_action") or decision.get("reason"),
            "issue_count": len(issues),
            "issue_codes": issue_codes,
            "issues": issues,
            "raw": payload,
        }

    def _collect_issue_codes(self, *, work: Dict[str, Any], chapters: List[Dict[str, Any]]) -> List[str]:
        issue_codes: List[str] = []
        for item in list((work.get("diagnostics_summary_json") or {}).get("reports") or []):
            for issue in list((item or {}).get("issues") or []):
                code = str((issue or {}).get("issue_code") or "").strip()
                if code:
                    issue_codes.append(code)
        for chapter in chapters:
            for issue in list((chapter.get("diagnostic_summary_json") or {}).get("issues") or []):
                code = str((issue or {}).get("issue_code") or "").strip()
                if code:
                    issue_codes.append(code)
        return issue_codes

    def _product_quality_summary(self, *, work: Dict[str, Any], chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
        issue_codes = set(self._collect_issue_codes(work=work, chapters=chapters))
        return {
            "重复感": "需留意" if "Q03" in issue_codes else "良好",
            "场景细节": "需补强" if "Q05" in issue_codes else "充足",
            "节奏": "需调整" if "Q09" in issue_codes else "稳定",
            "结尾风险": "偏高" if "Q09" in issue_codes else "正常",
        }

    def _route_display_name(self, branch: Dict[str, Any], index: int) -> str:
        branch_kind = str(branch.get("branch_kind") or "")
        if branch_kind == "mainline" or index == 0:
            return "主线"
        origin = str(branch.get("branch_origin_label") or branch.get("branch_name") or "").strip()
        letter = chr(ord("A") + max(0, index - 1))
        return f"路线 {letter}：{origin or '新的走向'}"

    def _branch_map_payload(self, *, work: Dict[str, Any], export_work_id: str) -> List[Dict[str, Any]]:
        family = self._branch_family(work)
        branch_map: List[Dict[str, Any]] = []
        for index, branch in enumerate(family):
            try:
                branch_work = self.repository.get_author_work(branch["work_id"])
                branch_chapters = self.repository.list_author_work_chapters(work_id=branch["work_id"])
                issue_codes = set(self._collect_issue_codes(work=branch_work, chapters=branch_chapters))
            except KeyError:
                branch_chapters = []
                issue_codes = set()
            branch_map.append(
                {
                    "route_name": self._route_display_name(branch, index),
                    "current_chapter_count": int(branch.get("chapter_count") or len(branch_chapters) or 0),
                    "recent_choice": branch.get("branch_origin_label") or ("主线推进" if index == 0 else "新的走向"),
                    "quality_status": "需关注" if issue_codes else "稳定",
                    "is_export_main_route": bool(branch.get("work_id") == export_work_id),
                    "fork_after_chapter_index": int(branch.get("fork_after_chapter_index") or 0),
                }
            )
        return branch_map

    def _work_content_quality_repair_workbench(
        self,
        *,
        work: Dict[str, Any],
        chapters: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        diagnostic_payloads = [dict(item.get("diagnostic_summary_json") or {}) for item in chapters if dict(item.get("diagnostic_summary_json") or {})]
        if not diagnostic_payloads:
            return {"available": False, "windows": {}, "default_campaign": {}, "campaigns": [], "next_actions": []}
        runtime_context = self._runtime_context(world_version_id=work["world_version_id"])
        worldpack = dict(runtime_context.get("worldpack") or {})
        scene_by_function: Dict[str, Dict[str, Any]] = {}
        for scene in list(worldpack.get("scene_blueprints") or []):
            payload = dict(scene or {})
            scene_function = str(payload.get("scene_function") or "")
            if scene_function and scene_function not in scene_by_function:
                scene_by_function[scene_function] = payload
        role_to_character_ids: Dict[str, List[str]] = {}
        for character in list(worldpack.get("characters") or []):
            payload = dict(character or {})
            role = str(payload.get("role") or "")
            character_id = str(payload.get("character_id") or "")
            if role and character_id:
                role_to_character_ids.setdefault(role, []).append(character_id)
        chapter_heatmap = []
        for chapter in chapters:
            diagnostic = dict(chapter.get("diagnostic_summary_json") or {})
            if not diagnostic:
                continue
            issue_codes = [
                str(item.get("issue_code") or "")
                for item in list(diagnostic.get("issues") or [])
                if str(item.get("issue_code") or "")
            ]
            state_snapshot = dict(chapter.get("state_snapshot_json") or {})
            coverage_context = dict((state_snapshot.get("metadata") or {}).get("coverage_context") or {})
            first_beat = dict((coverage_context.get("scene_beats") or [{}])[0] or {})
            event = dict(first_beat.get("event") or {})
            scene_function = str(event.get("scene_function") or "")
            matched_scene = dict(scene_by_function.get(scene_function) or {})
            chapter_task = dict(chapter.get("chapter_task_json") or {})
            chapter_task_id = str(chapter_task.get("chapter_task_id") or "")
            arc_id = chapter_task_id.rsplit("::task_", 1)[0] if "::task_" in chapter_task_id else ""
            volume_id = arc_id.rsplit("::arc_", 1)[0] if "::arc_" in arc_id else ""
            related_character_ids = [
                character_id
                for role in list((matched_scene.get("required_roles") or []))
                for character_id in role_to_character_ids.get(str(role), [])
            ]
            chapter_heatmap.append(
                {
                    "chapter_index": int(chapter.get("chapter_index", 0) or 0),
                    "chapter_title": str(chapter.get("chapter_title") or ""),
                    "decision": str((diagnostic.get("decision") or {}).get("decision") or "rewrite"),
                    "severity": "critical" if str((diagnostic.get("decision") or {}).get("decision") or "") == "block" else ("watch" if str((diagnostic.get("decision") or {}).get("decision") or "") == "rewrite" else "stable"),
                    "overall_score": float((diagnostic.get("scores") or {}).get("overall_score", 0.0) or 0.0),
                    "issue_count": len(issue_codes),
                    "issue_codes": issue_codes,
                    "scene_function": scene_function,
                    "scene_id": str(matched_scene.get("scene_id") or ""),
                    "chapter_task_id": chapter_task_id,
                    "arc_id": arc_id,
                    "volume_id": volume_id,
                    "related_character_ids": related_character_ids,
                    "related_characters": related_character_ids,
                }
            )
        helper = AuthoringService(self.repository, registry=self.registry)
        simulation_like = {
            "chapter_evaluations": diagnostic_payloads,
            "creative_cockpit": {
                "chapter_heatmap": {
                    "chapters": chapter_heatmap,
                    "issue_priority_groups": helper._build_issue_priority_groups(chapter_heatmap),
                }
            },
            "longform_plan_snapshot": runtime_context.get("longform_structure") or {},
        }
        return helper._build_content_quality_repair_workbench(worldpack, simulation_like)

    def _chapter_payload(self, chapter: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(chapter or {})
        choices = list(payload.get("choices_json") or [])
        return {
            **payload,
            "chapter_task": dict(payload.get("chapter_task_json") or {}),
            "choices": choices,
            "choice_impacts": build_choice_impacts(
                choices,
                chapter_index=int(payload.get("chapter_index") or 0),
            ),
            "latest_diagnostic_summary": self._normalized_chapter_diagnostics(payload.get("diagnostic_summary_json")),
        }

    def _work_detail_payload(self, work: Dict[str, Any], *, include_chapters: bool = True) -> Dict[str, Any]:
        normalized_work = self._ensure_work_branch_metadata(work)
        chapters = self.repository.list_author_work_chapters(work_id=normalized_work["work_id"]) if include_chapters else []
        revisions = self.repository.list_author_work_revisions(work_id=normalized_work["work_id"], limit=20)
        normalized_chapters = [self._chapter_payload(item) for item in chapters]
        latest_guard = dict(((revisions[0].get("snapshot_json") or {}).get("quality_gate") or {})) if revisions else {}
        repair_workbench = self._work_content_quality_repair_workbench(work=normalized_work, chapters=chapters) if include_chapters else {"available": False, "windows": {}, "default_campaign": {}, "campaigns": [], "next_actions": []}
        default_campaign = dict(repair_workbench.get("default_campaign") or {})
        return {
            **normalized_work,
            "chapters": normalized_chapters,
            "revisions": revisions,
            "latest_revision": revisions[0] if revisions else None,
            "active_chapter_index": normalized_chapters[-1]["chapter_index"] if normalized_chapters else None,
            "diagnostics_summary": self._normalized_work_diagnostics(normalized_work.get("diagnostics_summary_json")),
            "hard_constraint_status": "blocked" if latest_guard.get("failed_checks") or default_campaign.get("issue_code") else "clear",
            "blocking_dimension": str(latest_guard.get("blocking_dimension") or latest_guard.get("primary_issue_group") or default_campaign.get("issue_code") or ""),
            "window_breach_kind": str(latest_guard.get("window_breach_kind") or default_campaign.get("breach_kind") or ""),
            "ready_for_validation": False if latest_guard.get("failed_checks") else not bool(default_campaign),
            "content_quality_repair_workbench": repair_workbench,
            "branch_family": self._branch_family(normalized_work),
        }

    def get_work(self, work_id: str) -> Dict[str, Any]:
        work = self.repository.get_author_work(work_id)
        return self._work_detail_payload(work)

    def get_work_chapter(self, *, work_id: str, chapter_index: int) -> Dict[str, Any]:
        work = self.repository.get_author_work(work_id)
        chapter = self.repository.get_author_work_chapter(work_id=work_id, chapter_index=chapter_index)
        return {
            "work": self._work_detail_payload(work, include_chapters=False),
            "chapter": self._chapter_payload(chapter),
        }

    def _resolve_export_work(self, *, work_id: str, route: str) -> Dict[str, Any]:
        requested_work = self._ensure_work_branch_metadata(self.repository.get_author_work(work_id))
        normalized_route = str(route or "active").strip()
        family = self._branch_family(requested_work)
        selected = None
        if normalized_route in {"active", ""}:
            selected = next((item for item in family if item.get("is_active_line")), None)
        elif normalized_route in {"main", "mainline"}:
            selected = next((item for item in family if item.get("branch_kind") == "mainline"), None)
        else:
            selected = next(
                (
                    item
                    for item in family
                    if str(item.get("work_id")) == normalized_route
                    or str(item.get("branch_name")) == normalized_route
                    or str(item.get("branch_origin_label")) == normalized_route
                ),
                None,
            )
        return self._ensure_work_branch_metadata(
            self.repository.get_author_work((selected or requested_work)["work_id"])
        )

    def export_work_nosbook(self, *, work_id: str, route: str = "active") -> Dict[str, Any]:
        export_work = self._resolve_export_work(work_id=work_id, route=route)
        chapters = self.repository.list_author_work_chapters(work_id=export_work["work_id"])
        family = self._branch_family(export_work)
        route_index = next(
            (index for index, item in enumerate(family) if item.get("work_id") == export_work["work_id"]),
            0,
        )
        route_name = self._route_display_name(export_work, route_index)
        exported_chapters = []
        for chapter in chapters:
            choices = list(chapter.get("choices_json") or [])
            exported_chapters.append(
                {
                    "chapter_index": int(chapter.get("chapter_index") or 0),
                    "chapter_title": chapter.get("chapter_title"),
                    "body": chapter.get("body") or "",
                    "summary": chapter.get("summary") or "",
                    "choices": choices,
                    "choice_impacts": build_choice_impacts(
                        choices,
                        chapter_index=int(chapter.get("chapter_index") or 0),
                    ),
                }
            )
        choice_history = []
        for index, branch in enumerate(family):
            if not branch.get("branch_origin_label"):
                continue
            choice_history.append(
                {
                    "route_name": self._route_display_name(branch, index),
                    "chapter_index": int(branch.get("fork_after_chapter_index") or 0),
                    "selected_choice": branch.get("branch_origin_label"),
                    "selected_at": branch.get("updated_at"),
                    "expected_effect": "从这一章后开启新的路线",
                }
            )
        title = str(export_work.get("title") or "NarrativeOS Work").strip() or "NarrativeOS Work"
        safe_name = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in title).strip("-") or "narrativeos-work"
        return {
            "schema_version": "nosbook/v1",
            "content_type": "application/vnd.narrativeos.nosbook+json",
            "filename": f"{safe_name}.nosbook",
            "work": {
                "title": title,
                "world_version_id": export_work.get("world_version_id"),
                "route_name": route_name,
                "chapter_count": len(exported_chapters),
                "target_chapter_count": int(export_work.get("target_chapter_count") or 0),
            },
            "export_route": {
                "route": route or "active",
                "route_name": route_name,
                "is_active_line": bool(export_work.get("is_active_line")),
            },
            "chapters": exported_chapters,
            "branch_map": self._branch_map_payload(work=export_work, export_work_id=export_work["work_id"]),
            "choice_history": choice_history,
            "quality_summary": self._product_quality_summary(work=export_work, chapters=chapters),
            "cover": {
                "mode": "default",
                "source": "agent_studio_default_cover",
                "metadata": {},
            },
        }

    def _generate_target_count(self, *, mode: str, existing_count: int, state: NarrativeState) -> int:
        if mode == "first":
            return 1 if existing_count == 0 else 0
        if mode == "next":
            return 1
        if mode == "arc":
            current_arc_target = int((state.metadata or {}).get("longform_progression", {}).get("arc_target_chapters", 0) or 0)
            current_arc_index = int((state.metadata or {}).get("longform_progression", {}).get("arc_chapter_index", 0) or 0)
            remaining = max(1, current_arc_target - current_arc_index) if current_arc_target else 3
            return min(remaining, 6)
        return 1

    def generate_chapters(self, *, work_id: str, mode: str) -> Dict[str, Any]:
        normalized_mode = str(mode or "").strip() or "next"
        if normalized_mode not in VALID_AUTHOR_WORK_GENERATION_MODES:
            raise ValueError("invalid_author_work_generation_mode")
        work = self.repository.get_author_work(work_id)
        runtime_context = self._runtime_context(world_version_id=work["world_version_id"])
        min_target_words = self._quality_gate_min_target_words(runtime_context)
        target_chapters = int(
            work.get("target_chapter_count")
            or (((runtime_context.get("longform_structure") or {}).get("series_plan") or {}).get("total_chapter_target") or 0)
        )
        state = self._configured_state(work=work, runtime_context=runtime_context)
        last_persisted_state = NarrativeState.from_dict(state.to_dict())
        runtime = runtime_context["runtime"]
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        generated_any = False
        generate_count = self._generate_target_count(mode=normalized_mode, existing_count=len(chapters), state=state)
        if generate_count <= 0:
            return self.get_work(work_id)
        for _ in range(generate_count):
            candidate_provider = (
                self.provider_routing.build_candidate_provider(
                    runtime.event_atoms,
                    surface="author_work_generation",
                    account_id=work["account_id"],
                    session_id=f"author_work:{work_id}",
                    world_id=runtime.worldpack.world_id,
                    world_version_id=work["world_version_id"],
                )
                if self.provider_routing
                else StaticCandidateProvider(runtime.event_atoms)
            )
            renderer = (
                self.provider_routing.build_renderer(
                    surface="author_work_generation",
                    account_id=work["account_id"],
                    session_id=f"author_work:{work_id}",
                    world_id=runtime.worldpack.world_id,
                    world_version_id=work["world_version_id"],
                )
                if self.provider_routing
                else TemplateRenderer()
            )
            result = plan_next_turn(
                state,
                world=runtime.world_record.world,
                candidate_provider=candidate_provider,
                renderer=renderer,
                debug=False,
            )
            if result.get("status") != "ok":
                break
            if isinstance(result.get("reader_view"), dict):
                sanitized_reader_view, reader_visible_language_debug = sanitize_reader_visible_payload(dict(result["reader_view"] or {}))
                result["reader_view"] = sanitized_reader_view
                if isinstance(result.get("rendered_scene"), dict):
                    rendered_debug = dict((result["rendered_scene"].get("debug") or {}))
                    rendered_debug["reader_visible_language_debug"] = reader_visible_language_debug
                    result["rendered_scene"] = {
                        **dict(result["rendered_scene"] or {}),
                        "debug": rendered_debug,
                    }
            state = NarrativeState.from_dict(result["updated_state"])
            chapter_index = int((result.get("updated_state_summary") or {}).get("chapter_index") or state.chapter_index or (len(chapters) + 1))
            state_snapshot = state.to_dict()
            coverage_metadata = dict(state_snapshot.get("metadata") or {})
            chapter_task = dict((result.get("chapter_plan") or {}).get("chapter_task") or {})
            coverage_metadata["coverage_context"] = {
                "selected_event_ids": list((result.get("chapter_plan") or {}).get("selected_event_ids", [])),
                "scene_beats": list(result.get("scene_beats") or []),
                "chapter_task": dict(chapter_task),
            }
            coverage_metadata["reader_visible_language_debug"] = dict(
                ((result.get("rendered_scene") or {}).get("debug") or {}).get("reader_visible_language_debug") or {}
            )
            state_snapshot["metadata"] = coverage_metadata
            body = _trim_generated_author_work_body(
                str(result["reader_view"].get("body") or ""),
                min_units=1800,
                max_units=2200,
            )
            lint = lint_chapter_draft(body)
            quality_bundle = evaluate_persisted_chapter(
                chapter_id=f"{work_id}::{chapter_index}",
                world_version_id=work["world_version_id"],
                session_id=f"author_work:{work_id}",
                body=body,
                paragraphs=body.split("\n\n"),
                dialogue_count=int(lint["dialogue_count"]),
                action_count=int(lint["action_count"]),
                detail_count=int(lint["detail_count"]),
                character_fidelity_score=max(
                    [item["components"].get("character_fidelity", 0.0) for item in result.get("scored_candidates", [])],
                    default=0.75,
                ),
                state_after=state,
                ending_ready=bool((result.get("chapter_plan") or {}).get("ending_ready")),
                chapter_title=result["reader_view"].get("chapter_title"),
                recap=result["reader_view"].get("recap"),
                relationship_hints=list(result["reader_view"].get("relationship_hints") or []),
                choices=list(result["reader_view"].get("choices") or []),
                paywall_required=False,
                coverage_context=coverage_metadata["coverage_context"],
                target_words=chapter_task.get("target_words"),
                min_target_words=min_target_words,
                chapter_index=chapter_index,
                target_chapters=target_chapters,
                story_phase=str(state.story_phase or ""),
                rolling_quality_window=list((last_persisted_state.metadata or {}).get("quality_contract_window", [])),
                enforcement_scope="author_work_generation",
            )
            try:
                persist_guardrail_records(
                    self.repository,
                    quality_bundle=quality_bundle,
                    scenario_id="author_generate_chapter",
                    source_surface="author",
                    source_ref={
                        "kind": "author_work_chapter",
                        "work_id": work_id,
                        "chapter_id": f"{work_id}::{chapter_index}",
                        "rendered_text": body,
                    },
                    world_version_id=work["world_version_id"],
                    session_id=f"author_work:{work_id}",
                    chapter_id=f"{work_id}::{chapter_index}",
                    coverage_context=coverage_metadata["coverage_context"],
                    state_after=state,
                    worldpack_payload=runtime.worldpack.to_dict() if hasattr(runtime.worldpack, "to_dict") else None,
                )
            except Exception:
                pass
            if not quality_bundle["quality_gate"]["ok"]:
                if generated_any:
                    chapters = sorted(chapters, key=lambda item: int(item["chapter_index"]))
                    work = self.repository.save_author_work(
                        {
                            **work,
                            "chapter_count": len(chapters),
                            "narrative_state_json": last_persisted_state.to_dict(),
                            "status": "draft",
                        }
                    )
                    work = self._revision(
                        work=work,
                        chapters=chapters,
                        revision_type="generation",
                        summary=f"生成章节 · mode={normalized_mode} · partial_before_quality_guard_failure",
                    )
                self._record_quality_guard_failure(
                    work=work,
                    chapters=chapters,
                    chapter_index=chapter_index,
                    surface="author_work_generation",
                    quality_gate=quality_bundle["quality_gate"],
                )
                raise ChapterQualityGuardError(quality_bundle["quality_gate"])
            quality_contract_window = list(quality_bundle["quality_gate"].get("quality_contract_window") or [])
            state.metadata = {
                **dict(state.metadata or {}),
                "quality_contract_window": quality_contract_window,
            }
            coverage_metadata["quality_contract_window"] = quality_contract_window
            state_snapshot["metadata"] = coverage_metadata
            saved = self.repository.save_author_work_chapter(
                {
                    "work_id": work_id,
                    "chapter_index": chapter_index,
                    "chapter_title": result["reader_view"].get("chapter_title") or f"第 {chapter_index} 章",
                    "body": body,
                    "status": "generated",
                    "source_type": "generated" if not chapters else "regenerated" if any(item["chapter_index"] == chapter_index for item in chapters) else "generated",
                    "summary": body[:120],
                    "chapter_task_json": chapter_task,
                    "choices_json": list(result["reader_view"].get("choices") or []),
                    "state_snapshot_json": state_snapshot,
                }
            )
            chapters = [item for item in chapters if item["chapter_index"] != chapter_index] + [saved]
            generated_any = True
            last_persisted_state = NarrativeState.from_dict(state.to_dict())
        chapters = sorted(chapters, key=lambda item: int(item["chapter_index"]))
        work = self.repository.save_author_work(
            {
                **work,
                "chapter_count": len(chapters),
                "narrative_state_json": state.to_dict(),
                "status": "draft",
            }
        )
        work = self._revision(work=work, chapters=chapters, revision_type="generation", summary=f"生成章节 · mode={normalized_mode}")
        return self.get_work(work["work_id"])

    def edit_chapter(
        self,
        *,
        work_id: str,
        chapter_index: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        work = self.repository.get_author_work(work_id)
        chapter = self.repository.get_author_work_chapter(work_id=work_id, chapter_index=chapter_index)
        runtime_context = self._runtime_context(world_version_id=work["world_version_id"])
        min_target_words = self._quality_gate_min_target_words(runtime_context)
        target_chapters = int(
            work.get("target_chapter_count")
            or (((runtime_context.get("longform_structure") or {}).get("series_plan") or {}).get("total_chapter_target") or 0)
        )
        next_title = title or chapter["chapter_title"]
        next_body = body if body is not None else chapter["body"]
        next_summary = summary if summary is not None else chapter.get("summary")
        state_after_payload = dict(chapter.get("state_snapshot_json") or {})
        state_after = (
            NarrativeState.from_dict(state_after_payload)
            if state_after_payload
            else NarrativeState.from_dict(
                {
                    "state_id": f"{work_id}::edit::{chapter_index}",
                    "world_id": work["world_version_id"],
                    "turn_index": int(chapter_index),
                    "story_phase": "setup",
                    "chapter_index": int(chapter_index),
                    "min_end_turn": max(8, int(chapter_index)),
                    "fate_pressure": 0.0,
                    "karmic_weather": {},
                    "unresolved_debts": [],
                    "world_facts": [],
                    "timeline": [],
                    "characters": {},
                    "relationship_graph": [],
                    "open_promises": [],
                    "tension": 0.0,
                    "themes": {},
                    "player_intent": {},
                    "recent_scene_functions": [],
                    "visited_event_ids": [],
                    "route_fingerprint": [],
                    "rating_ceiling": "PG13",
                }
            )
        )
        coverage_context = dict((state_after_payload.get("metadata") or {}).get("coverage_context") or {})
        coverage_context["chapter_task"] = dict(chapter.get("chapter_task_json") or {})
        lint = lint_chapter_draft(next_body)
        quality_bundle = evaluate_persisted_chapter(
            chapter_id=f"{work_id}::{chapter_index}",
            world_version_id=work["world_version_id"],
            session_id=f"author_work:{work_id}",
            body=next_body,
            paragraphs=next_body.split("\n\n"),
            dialogue_count=int(lint["dialogue_count"]),
            action_count=int(lint["action_count"]),
            detail_count=int(lint["detail_count"]),
            character_fidelity_score=float(
                (((chapter.get("diagnostic_summary_json") or {}).get("scores") or {}).get("character_fidelity", 1.0) or 1.0)
            ),
            state_after=state_after,
            ending_ready=bool((chapter.get("chapter_task_json") or {}).get("allow_terminal")),
            chapter_title=next_title,
            choices=list(chapter.get("choices_json") or []),
            paywall_required=False,
            coverage_context=coverage_context,
            target_words=(chapter.get("chapter_task_json") or {}).get("target_words"),
            min_target_words=min_target_words,
            chapter_index=chapter_index,
            target_chapters=target_chapters,
            story_phase=str(state_after.story_phase or ""),
            rolling_quality_window=list((state_after.metadata or {}).get("quality_contract_window", [])),
            enforcement_scope="author_work_manual_edit",
        )
        try:
            persist_guardrail_records(
                self.repository,
                quality_bundle=quality_bundle,
                scenario_id="author_manual_edit",
                source_surface="author",
                source_ref={
                    "kind": "author_work_chapter",
                    "work_id": work_id,
                    "chapter_id": f"{work_id}::{chapter_index}",
                    "rendered_text": next_body,
                },
                world_version_id=work["world_version_id"],
                session_id=f"author_work:{work_id}",
                chapter_id=f"{work_id}::{chapter_index}",
                coverage_context=coverage_context,
                state_after=state_after,
                worldpack_payload=(runtime_context.get("runtime").worldpack.to_dict() if hasattr(runtime_context.get("runtime").worldpack, "to_dict") else None),
            )
        except Exception:
            pass
        if not quality_bundle["quality_gate"]["ok"]:
            chapters = self.repository.list_author_work_chapters(work_id=work_id)
            self._record_quality_guard_failure(
                work=work,
                chapters=chapters,
                chapter_index=chapter_index,
                surface="author_work_manual_edit",
                quality_gate=quality_bundle["quality_gate"],
            )
            raise ChapterQualityGuardError(quality_bundle["quality_gate"])
        state_after.metadata = {
            **dict(state_after.metadata or {}),
            "quality_contract_window": list(quality_bundle["quality_gate"].get("quality_contract_window") or []),
        }
        state_after_payload["metadata"] = dict(state_after.metadata or {})
        updated_chapter = self.repository.save_author_work_chapter(
            {
                **chapter,
                "chapter_title": next_title,
                "body": next_body,
                "summary": next_summary,
                "status": "edited",
                "source_type": "manual_edit",
                "state_snapshot_json": state_after.to_dict(),
            }
        )
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        work = self.repository.save_author_work(
            {
                **work,
                "status": "draft",
            }
        )
        work = self._revision(work=work, chapters=chapters, revision_type="chapter_edit", summary=f"编辑第 {chapter_index} 章")
        return {
            "work": self.get_work(work_id),
            "chapter": updated_chapter,
        }

    def run_diagnostics(self, *, work_id: str) -> Dict[str, Any]:
        work = self.repository.get_author_work(work_id)
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        reports = self._chapter_reports(chapters, world_version_id=work["world_version_id"], work_id=work_id)
        aggregated = aggregate_reports(EvaluationReport.from_dict(item) for item in reports)
        revisions = self.repository.list_author_work_revisions(work_id=work_id, limit=1)
        chapter_map = {item["chapter_index"]: item for item in chapters}
        for report in reports:
            chapter_index = int(str(report["chapter_id"]).rsplit("::", 1)[-1] or 0)
            chapter = chapter_map.get(chapter_index)
            if chapter:
                self.repository.save_author_work_chapter(
                    {
                        **chapter,
                        "diagnostic_summary_json": report,
                    }
                )
        latest_decision = self._aggregate_work_decision(aggregated)
        if revisions and str(revisions[0].get("revision_type") or "") == "quality_guard_blocked" and latest_decision == "pass":
            latest_decision = "rewrite"
        next_status = "review_ready" if latest_decision == "pass" else "needs_changes"
        work = self.repository.save_author_work(
            {
                **work,
                "diagnostics_summary_json": {
                    "chapter_count": len(chapters),
                    "evaluation_summary": aggregated,
                    "latest_decision": latest_decision,
                },
                "status": next_status,
            }
        )
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        work = self._revision(work=work, chapters=chapters, revision_type="diagnostics", summary="运行作品稿诊断")
        return {
            "work": self.get_work(work_id),
            "reports": reports,
            "evaluation_summary": aggregated,
        }

    def submit_work(self, *, work_id: str) -> Dict[str, Any]:
        work = self.repository.get_author_work(work_id)
        diagnostics = dict(work.get("diagnostics_summary_json") or {})
        evaluation = dict(diagnostics.get("evaluation_summary") or {})
        if not diagnostics:
            raise ValueError("author_work_requires_diagnostics")
        if str(diagnostics.get("latest_decision") or "") != "pass":
            raise ValueError("author_work_blocked_by_diagnostics")
        if float(evaluation.get("block_rate", 0.0) or 0.0) > 0.0:
            raise ValueError("author_work_blocked_by_diagnostics")
        chapters = self.repository.list_author_work_chapters(work_id=work_id)
        work = self.repository.save_author_work(
            {
                **work,
                "status": "submitted",
            }
        )
        work = self._revision(work=work, chapters=chapters, revision_type="submit", summary="作品稿送审")
        self.repository.save_review_record(
            {
                "asset_type": "author_work",
                "asset_id": work_id,
                "status": "submitted",
                "reviewer_id": None,
                "risk_rating": "PG-13",
                "notes": f"author_work::{work_id}::{work['world_version_id']}",
            }
        )
        return self.get_work(work_id)
