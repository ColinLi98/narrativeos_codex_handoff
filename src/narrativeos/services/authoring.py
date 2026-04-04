from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..benchmark.runner import run_benchmark
from ..core.linter import lint_chapter_draft
from ..eval.learned_inference import LearnedInferenceService, default_learned_artifact_dir
from ..eval.learned_shadow import LearnedShadowService
from ..eval.reporting import aggregate_reports
from ..eval.service import evaluate_chapter
from ..eval.taxonomy import ISSUE_TAXONOMY
from ..models import NarrativeState
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..pipeline import plan_next_turn
from ..providers import StaticCandidateProvider
from ..rendering import TemplateRenderer
from .billing import BillingService
from .observability import ObservabilityService
from .provider_routing import ProviderRoutingService
from .training_signal import TrainingSignalService
from ..worldpacks.models import WorldPack, WorldVersion
from ..worldpacks.registry import FileSystemWorldRegistry
from ..worldpacks.validator import validate_worldpack_payload


class AuthoringService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        registry: Optional[FileSystemWorldRegistry] = None,
        training_signal_service: Optional[TrainingSignalService] = None,
        learned_inference_service: Optional[LearnedInferenceService] = None,
        learned_shadow_service: Optional[LearnedShadowService] = None,
        billing_service: Optional[BillingService] = None,
        provider_routing_service: Optional[ProviderRoutingService] = None,
        observability_service: Optional[ObservabilityService] = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or FileSystemWorldRegistry()
        self.base_dir = Path(__file__).resolve().parents[3]
        self.training_signal = training_signal_service or TrainingSignalService(repository)
        self.billing = billing_service or BillingService(repository)
        self.learned_inference = learned_inference_service or LearnedInferenceService(default_learned_artifact_dir(self.base_dir))
        self.learned_shadow = learned_shadow_service or LearnedShadowService(
            default_learned_artifact_dir(self.base_dir),
            learned_inference_service=self.learned_inference,
        )
        self.provider_routing = provider_routing_service
        self.observability = observability_service

    def _normalize_change_context(self, change_context: Optional[Dict[str, Any]], *, default_source: str, default_label: str) -> Dict[str, str]:
        payload = dict(change_context or {})
        return {
            "source": str(payload.get("source") or default_source),
            "label": str(payload.get("label") or default_label),
        }

    def _revision_history(self, worldpack_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list((worldpack_payload.get("metadata") or {}).get("revision_history", []))

    def _ensure_metadata(self, worldpack_payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(worldpack_payload.get("metadata", {}))
        worldpack_payload["metadata"] = metadata
        return metadata

    def _snapshot_summary(self, snapshot: Dict[str, Any]) -> str:
        characters = len(snapshot.get("characters", []))
        scenes = len(snapshot.get("scene_blueprints", []))
        genres = "/".join((snapshot.get("manifest") or {}).get("genres", []))
        return f"{snapshot.get('title', snapshot.get('world_id', '-'))} · {genres or '-'} · 角色 {characters} · 场景 {scenes}"

    def _diff_sections(self, previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        sections = [
            "manifest",
            "world_bible",
            "characters",
            "scene_blueprints",
            "voice_profiles",
            "response_cadence_profiles",
            "emotion_action_policies",
            "sensory_grounding_policies",
            "scene_realization_contracts",
        ]
        changed_sections = [section for section in sections if previous.get(section) != current.get(section)]

        character_changes = []
        previous_characters = {item.get("character_id"): item for item in previous.get("characters", [])}
        current_characters = {item.get("character_id"): item for item in current.get("characters", [])}
        for character_id in sorted(set(previous_characters) | set(current_characters)):
            before = previous_characters.get(character_id)
            after = current_characters.get(character_id)
            if before != after:
                changed_fields = []
                if (before or {}).get("display_name") != (after or {}).get("display_name"):
                    changed_fields.append("display_name")
                if (before or {}).get("role") != (after or {}).get("role"):
                    changed_fields.append("role")
                if ((before or {}).get("destiny_contract") or {}).get("life_theme") != ((after or {}).get("destiny_contract") or {}).get("life_theme"):
                    changed_fields.append("life_theme")
                if ((before or {}).get("wound_profile") or {}).get("core_wound") != ((after or {}).get("wound_profile") or {}).get("core_wound"):
                    changed_fields.append("core_wound")
                if ((before or {}).get("wound_profile") or {}).get("public_self") != ((after or {}).get("wound_profile") or {}).get("public_self"):
                    changed_fields.append("public_self")
                if ((before or {}).get("wound_profile") or {}).get("shadow_desire") != ((after or {}).get("wound_profile") or {}).get("shadow_desire"):
                    changed_fields.append("shadow_desire")
                if ((before or {}).get("vow_profile") or {}).get("vows") != ((after or {}).get("vow_profile") or {}).get("vows"):
                    changed_fields.append("vows")
                character_changes.append({"character_id": character_id, "changed_fields": changed_fields or ["structure"]})

        scene_changes = []
        previous_scenes = {item.get("scene_id"): item for item in previous.get("scene_blueprints", [])}
        current_scenes = {item.get("scene_id"): item for item in current.get("scene_blueprints", [])}
        for scene_id in sorted(set(previous_scenes) | set(current_scenes)):
            before = previous_scenes.get(scene_id)
            after = current_scenes.get(scene_id)
            if before != after:
                changed_fields = []
                if (before or {}).get("scene_function") != (after or {}).get("scene_function"):
                    changed_fields.append("scene_function")
                if (before or {}).get("required_roles") != (after or {}).get("required_roles"):
                    changed_fields.append("required_roles")
                if (before or {}).get("beats_template") != (after or {}).get("beats_template"):
                    changed_fields.append("beats_template")
                scene_changes.append({"scene_id": scene_id, "changed_fields": changed_fields or ["structure"]})

        capability_sections = [
            "voice_profiles",
            "response_cadence_profiles",
            "emotion_action_policies",
            "sensory_grounding_policies",
            "scene_realization_contracts",
        ]
        capability_changes = [section for section in capability_sections if previous.get(section) != current.get(section)]
        summary_parts = []
        if character_changes:
            summary_parts.append(f"角色卡 {len(character_changes)} 处改动")
        if scene_changes:
            summary_parts.append(f"scene blueprint {len(scene_changes)} 处改动")
        if capability_changes:
            summary_parts.append(f"{'/'.join(capability_changes)} 已更新")
        if not summary_parts and changed_sections:
            summary_parts.append(f"{len(changed_sections)} 个 section 发生变化")
        if not summary_parts:
            summary_parts.append("未检测到结构差异")
        return {
            "changed_sections": changed_sections,
            "character_changes": character_changes,
            "scene_changes": scene_changes,
            "capability_changes": capability_changes,
            "summary_text": "；".join(summary_parts),
        }

    def _append_revision(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        change_context: Dict[str, str],
        diff_summary: Dict[str, Any],
        simulation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = self._ensure_metadata(worldpack_payload)
        revision_history = list(metadata.get("revision_history", []))
        revision_history.append(
            {
                "revision_id": "rev_%s" % uuid4().hex[:10],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": change_context["source"],
                "label": change_context["label"],
                "summary": diff_summary["summary_text"],
                "changed_sections": list(diff_summary.get("changed_sections", [])),
                "diff_summary": copy.deepcopy(diff_summary),
                "worldpack_snapshot": copy.deepcopy(worldpack_payload),
                "simulation_delta": dict(simulation_delta or {}),
            }
        )
        metadata["revision_history"] = revision_history[-10:]
        metadata["latest_diff_summary"] = dict(diff_summary)

    def _build_diff_drilldown(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        drilldown: List[Dict[str, Any]] = []
        previous_snapshot: Dict[str, Any] = {}
        for index, revision in enumerate(revisions):
            snapshot = dict(revision.get("worldpack_snapshot") or {})
            if revision.get("diff_summary"):
                diff_summary = dict(revision.get("diff_summary") or {})
            elif index == 0:
                diff_summary = {
                    "changed_sections": list(revision.get("changed_sections", [])),
                    "character_changes": [],
                    "scene_changes": [],
                    "capability_changes": [],
                    "summary_text": revision.get("summary", ""),
                }
            else:
                diff_summary = self._diff_sections(previous_snapshot, snapshot)
                if not diff_summary.get("summary_text"):
                    diff_summary["summary_text"] = revision.get("summary", "")
            drilldown.append(
                {
                    "revision_id": revision.get("revision_id"),
                    "created_at": revision.get("created_at"),
                    "source": revision.get("source"),
                    "label": revision.get("label"),
                    "summary": revision.get("summary"),
                    "snapshot_summary": self._snapshot_summary(snapshot) if snapshot else "-",
                    "character_count": len(snapshot.get("characters", [])),
                    "scene_count": len(snapshot.get("scene_blueprints", [])),
                    "diff_summary": diff_summary,
                    "simulation_delta": dict(revision.get("simulation_delta") or {}),
                }
            )
            previous_snapshot = snapshot
        current_diff = dict(metadata.get("latest_diff_summary", {}))
        if not current_diff and drilldown:
            current_diff = dict(drilldown[-1].get("diff_summary") or {})
        section_change_counts = {
            "sections": len(current_diff.get("changed_sections", [])),
            "characters": len(current_diff.get("character_changes", [])),
            "scenes": len(current_diff.get("scene_changes", [])),
            "capabilities": len(current_diff.get("capability_changes", [])),
        }
        recommended_next_actions: List[str] = []
        if current_diff.get("character_changes"):
            recommended_next_actions.append("re_simulate_for_character_consistency")
        if current_diff.get("scene_changes"):
            recommended_next_actions.append("re_simulate_for_pacing_and_chapter_shape")
        if current_diff.get("capability_changes"):
            recommended_next_actions.append("re_simulate_for_voice_action_sensory_regression_check")
        if not recommended_next_actions and current_diff.get("changed_sections"):
            recommended_next_actions.append("review_structural_diff_before_next_step")
        return {
            "current_diff": current_diff,
            "section_change_counts": section_change_counts,
            "recommended_next_actions": recommended_next_actions,
            "revisions": drilldown,
        }

    def _build_validation_drilldown(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not validation_report:
            return {}
        guidance = {
            "schema": ("schema", "high", "修正 worldpack 顶层 schema 字段"),
            "runtime_world_bible": ("runtime_world_bible", "high", "检查 runtime_world_bible 与世界设定"),
            "runtime_initial_state": ("runtime_initial_state", "high", "检查 runtime_initial_state 与状态 schema"),
            "runtime_event_atoms": ("runtime_event_atoms", "high", "检查 runtime_event_atoms 与 event atom schema"),
            "scene_blueprints_missing": ("scene_blueprints", "high", "至少补一个 scene blueprint"),
            "characters_missing": ("characters", "high", "至少补一个角色"),
            "runtime_world_bible_missing": ("runtime_world_bible", "medium", "可选补 runtime_world_bible，减少 synthesize 偏差"),
            "runtime_initial_state_missing": ("runtime_initial_state", "medium", "可选补 runtime_initial_state，减少 synthesize 偏差"),
            "runtime_event_atoms_missing": ("runtime_event_atoms", "medium", "可选补 runtime_event_atoms，减少 synthesize 偏差"),
        }
        blockers = []
        warning_groups = []
        next_actions: List[str] = []
        for entry in list(validation_report.get("errors", [])):
            key = str(entry).split(":", 1)[0]
            category, severity, action = guidance.get(key, ("unknown", "high", "检查 validation error 并修正对应结构"))
            blockers.append(
                {
                    "key": key,
                    "category": category,
                    "severity": severity,
                    "message": str(entry),
                    "recommended_action": action,
                }
            )
            if action not in next_actions:
                next_actions.append(action)
        for entry in list(validation_report.get("warnings", [])):
            key = str(entry).split(":", 1)[0]
            category, severity, action = guidance.get(key, ("unknown", "medium", "按需补齐 runtime 资产"))
            warning_groups.append(
                {
                    "key": key,
                    "category": category,
                    "severity": severity,
                    "message": str(entry),
                    "recommended_action": action,
                }
            )
            if action not in next_actions:
                next_actions.append(action)
        return {
            "ok": bool(validation_report.get("ok")),
            "error_count": len(validation_report.get("errors", [])),
            "warning_count": len(validation_report.get("warnings", [])),
            "blockers": blockers,
            "warning_groups": warning_groups,
            "next_actions": next_actions,
        }

    def _build_simulation_drilldown(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_evaluations = list(simulation_report.get("chapter_evaluations", []))
        chapter_trace_map = {
            item.get("chapter_id"): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if item.get("chapter_id")
        }
        issue_counts: Dict[str, Dict[str, Any]] = {}
        module_counts: Dict[str, Dict[str, Any]] = {}
        chapter_breakdown: List[Dict[str, Any]] = []
        quality_actions: Dict[str, int] = {}
        for index, payload in enumerate(chapter_evaluations, start=1):
            scores = dict(payload.get("scores") or {})
            issues = list(payload.get("issues") or [])
            lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            trace = chapter_trace_map.get(chapter_id, {})
            issue_codes = []
            for issue in issues:
                issue_code = str(issue.get("issue_code") or "")
                if not issue_code:
                    continue
                issue_codes.append(issue_code)
                issue_entry = issue_counts.setdefault(
                    issue_code,
                    {
                        "issue_code": issue_code,
                        "count": 0,
                        "owning_module": issue.get("owning_module", ""),
                    },
                )
                issue_entry["count"] += 1
                module_name = str(issue.get("owning_module") or "unknown")
                module_entry = module_counts.setdefault(
                    module_name,
                    {
                        "owning_module": module_name,
                        "count": 0,
                        "issue_codes": set(),
                    },
                )
                module_entry["count"] += 1
                module_entry["issue_codes"].add(issue_code)
            for action in trace.get("quality_pass_actions", []):
                quality_actions[action] = quality_actions.get(action, 0) + 1
            chapter_breakdown.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_index": index,
                    "chapter_title": trace.get("chapter_title") or chapter_id,
                    "scene_function": trace.get("scene_function", ""),
                    "decision": payload.get("decision", {}).get("decision", "rewrite"),
                    "overall_score": round(float(scores.get("overall_score", 0.0)), 3),
                    "issue_codes": issue_codes,
                    "summary": payload.get("summary", ""),
                    "quality_pass_applied": bool(trace.get("quality_pass_applied", False)),
                    "quality_pass_actions": list(trace.get("quality_pass_actions", [])),
                    "signal_snapshot": {
                        "pacing": round(float(scores.get("pacing", 0.0)), 3),
                        "hook_quality": round(float(scores.get("hook_quality", 0.0)), 3),
                        "scene_density": round(float(scores.get("scene_density", 0.0)), 3),
                        "choice_distinctness": round(float(scores.get("choice_distinctness", 0.0)), 3),
                        "repetition_score": round(float(lint_metrics.get("repetition_score", 0.0)), 3),
                        "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0)), 3),
                        "dialogue_plus_action_ratio": round(float(lint_metrics.get("dialogue_plus_action_ratio", 0.0)), 3),
                        "concrete_detail_density": round(float(lint_metrics.get("concrete_detail_density", 0.0)), 3),
                    },
                    "choices_preview": list(trace.get("choices_preview", [])),
                    "critic_signal_count": int(trace.get("critic_signal_count", 0)),
                }
            )
        weakest_chapters = sorted(
            chapter_breakdown,
            key=lambda item: (
                {"block": 0, "rewrite": 1, "pass": 2}.get(str(item.get("decision")), 3),
                float(item.get("overall_score", 0.0)),
                -len(item.get("issue_codes", [])),
                -float(item.get("signal_snapshot", {}).get("exposition_ratio", 0.0)),
            ),
        )[:3]
        issue_histogram = sorted(
            issue_counts.values(),
            key=lambda item: (-int(item.get("count", 0)), str(item.get("issue_code", ""))),
        )
        module_histogram = [
            {
                "owning_module": key,
                "count": int(value.get("count", 0)),
                "issue_codes": sorted(value.get("issue_codes", set())),
            }
            for key, value in sorted(
                module_counts.items(),
                key=lambda item: (-int(item[1].get("count", 0)), item[0]),
            )
        ]
        decision_histogram: Dict[str, int] = {}
        story_phase_histogram: Dict[str, int] = {}
        scene_function_histogram: Dict[str, int] = {}
        for item in chapter_breakdown:
            decision = str(item.get("decision") or "unknown")
            decision_histogram[decision] = decision_histogram.get(decision, 0) + 1
            story_phase = str(chapter_trace_map.get(item["chapter_id"], {}).get("story_phase") or "unknown")
            story_phase_histogram[story_phase] = story_phase_histogram.get(story_phase, 0) + 1
            scene_function = str(item.get("scene_function") or "unknown")
            scene_function_histogram[scene_function] = scene_function_histogram.get(scene_function, 0) + 1
        issue_focus_queue = []
        for item in issue_histogram[:4]:
            impacted = [
                chapter
                for chapter in chapter_breakdown
                if item["issue_code"] in chapter.get("issue_codes", [])
            ][:3]
            issue_focus_queue.append(
                {
                    "issue_code": item["issue_code"],
                    "count": item["count"],
                    "owning_module": item.get("owning_module", ""),
                    "fix_hint": ISSUE_TAXONOMY.get(item["issue_code"], {}).get("fix_hint", ""),
                    "chapter_targets": [
                        {
                            "chapter_index": chapter["chapter_index"],
                            "chapter_title": chapter["chapter_title"],
                            "scene_function": chapter.get("scene_function"),
                            "decision": chapter.get("decision"),
                        }
                        for chapter in impacted
                    ],
                }
            )
        return {
            "chapter_budget": simulation_report.get("chapter_budget"),
            "completed_chapters": simulation_report.get("completed_chapters", 0),
            "completion_ratio": simulation_report.get("completion_ratio"),
            "stop_reason": simulation_report.get("stop_reason"),
            "latest_decision": simulation_report.get("latest_decision"),
            "issue_histogram": issue_histogram,
            "module_histogram": module_histogram,
            "decision_histogram": decision_histogram,
            "story_phase_histogram": story_phase_histogram,
            "scene_function_histogram": scene_function_histogram,
            "issue_focus_queue": issue_focus_queue,
            "weakest_chapters": weakest_chapters,
            "chapter_breakdown": chapter_breakdown,
            "quality_pass_summary": {
                "chapters_touched": sum(1 for item in chapter_breakdown if item.get("quality_pass_applied")),
                "action_histogram": [
                    {"action": action, "count": count}
                    for action, count in sorted(quality_actions.items(), key=lambda item: (-item[1], item[0]))
                ],
            },
            "next_actions": list((simulation_report.get("evaluation_summary") or {}).get("next_actions", [])),
        }

    def _decorate_draft_payload(self, version: WorldVersion) -> dict[str, Any]:
        metadata = dict((version.worldpack_json or {}).get("metadata", {}))
        return {
            "world_version_id": version.world_version_id,
            "world_id": version.world_id,
            "status": version.status,
            "worldpack": version.worldpack_json,
            "validation_report": version.validation_report_json,
            "validation_drilldown": self._build_validation_drilldown(dict(version.validation_report_json or {})),
            "simulation_report": version.simulation_report_json,
            "revision_history": list(metadata.get("revision_history", [])),
            "latest_diff_summary": dict(metadata.get("latest_diff_summary", {})),
            "diff_drilldown": {
                **self._build_diff_drilldown(metadata),
                "simulation_freshness": self._simulation_freshness(metadata, dict(version.simulation_report_json or {})),
            },
            "simulation_drilldown": self._build_simulation_drilldown(dict(version.simulation_report_json or {})),
            "revision_compare": self._build_revision_compare(metadata, dict(version.simulation_report_json or {})),
            "before_after_chapter_compare": self._build_before_after_chapter_compare(metadata),
        }

    def _workflow_target_version(self, *, account_id: Optional[str], world_version_id: Optional[str]) -> Optional[WorldVersion]:
        if world_version_id:
            return self.repository.get_world_version(world_version_id)
        if not account_id:
            return None
        for status in ("draft", "submitted"):
            for item in self.repository.list_world_versions(status=status):
                version = self.repository.get_world_version(item["world_version_id"])
                if version.author_id == account_id:
                    return version
        return None

    def _simulation_freshness(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        if not simulation_report:
            return {
                "status": "missing",
                "is_fresh": False,
                "latest_revision_id": revisions[-1].get("revision_id") if revisions else None,
                "latest_revision_at": revisions[-1].get("created_at") if revisions else None,
                "last_simulated_revision_id": None,
                "last_simulated_at": None,
            }
        latest_revision = revisions[-1] if revisions else {}
        last_simulated = next(
            (
                revision
                for revision in reversed(revisions)
                if dict(revision.get("simulation_delta") or {})
            ),
            None,
        )
        is_fresh = bool(last_simulated and latest_revision and last_simulated.get("revision_id") == latest_revision.get("revision_id"))
        return {
            "status": "fresh" if is_fresh else "stale",
            "is_fresh": is_fresh,
            "latest_revision_id": latest_revision.get("revision_id"),
            "latest_revision_at": latest_revision.get("created_at"),
            "last_simulated_revision_id": last_simulated.get("revision_id") if last_simulated else None,
            "last_simulated_at": last_simulated.get("created_at") if last_simulated else None,
        }

    def _validation_summary(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not validation_report:
            return {
                "available": False,
                "ok": False,
                "status": "missing",
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
            }
        return {
            "available": True,
            "ok": bool(validation_report.get("ok")),
            "status": "ok" if validation_report.get("ok") else "blocked",
            "error_count": len(validation_report.get("errors", [])),
            "warning_count": len(validation_report.get("warnings", [])),
            "errors": list(validation_report.get("errors", [])),
            "warnings": list(validation_report.get("warnings", [])),
        }

    def _simulation_summary(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {
                "available": False,
                "ok": False,
                "latest_decision": None,
                "completed_chapters": 0,
                "pass_rate": 0.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "stop_reason": None,
                "next_actions": [],
            }
        evaluation = dict(simulation_report.get("evaluation_summary") or {})
        return {
            "available": True,
            "ok": bool(simulation_report.get("ok")),
            "latest_decision": simulation_report.get("latest_decision"),
            "completed_chapters": int(simulation_report.get("completed_chapters", 0)),
            "pass_rate": float(evaluation.get("pass_rate", 0.0)),
            "rewrite_rate": float(evaluation.get("rewrite_rate", 0.0)),
            "block_rate": float(evaluation.get("block_rate", 0.0)),
            "stop_reason": simulation_report.get("stop_reason"),
            "next_actions": list(evaluation.get("next_actions", [])),
        }

    def _workflow_blockers(
        self,
        *,
        version: Optional[WorldVersion],
        access: Dict[str, Any],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        blockers: List[Dict[str, Any]] = []
        actions = dict(access.get("actions", {}))
        if version is None:
            create_access = actions.get("draft_from_brief", {})
            if create_access and not create_access.get("allowed", True):
                blockers.append(
                    {
                        "key": "draft_from_brief_access",
                        "severity": "high",
                        "message": f"根据 Brief 生成 Draft 当前被阻止：{create_access.get('reason') or 'author_access_blocked'}",
                    }
                )
            return blockers
        if validation_summary.get("available") and not validation_summary.get("ok", False):
            blockers.append(
                {
                    "key": "validation_errors",
                    "severity": "high",
                    "message": f"当前 Draft 仍有 {validation_summary.get('error_count', 0)} 个 validation errors。",
                }
            )
        if simulation_freshness.get("status") == "stale":
            blockers.append(
                {
                    "key": "stale_simulation",
                    "severity": "medium",
                    "message": "当前 simulation 已过期，最新 revision 还没有重新模拟。",
                }
            )
        if simulation_summary.get("available") and simulation_summary.get("latest_decision") not in {None, "pass"}:
            blockers.append(
                {
                    "key": "simulation_requires_revision",
                    "severity": "medium",
                    "message": f"当前 simulation 最新结论为 {simulation_summary.get('latest_decision')}，建议先修后再送审。",
                }
            )
        for action_name in ("simulate", "submit_draft", "update_draft"):
            action_access = actions.get(action_name, {})
            if action_access and not action_access.get("allowed", True):
                blockers.append(
                    {
                        "key": f"{action_name}_access",
                        "severity": "high",
                        "message": f"{action_name} 当前被阻止：{action_access.get('reason') or 'author_access_blocked'}",
                    }
                )
        return blockers

    def _workflow_stage_and_action(
        self,
        *,
        version: Optional[WorldVersion],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
    ) -> tuple[str, str]:
        if version is None:
            return "brief", "create_from_brief"
        if version.status == "submitted":
            return "submitted", "wait_for_review"
        if not validation_summary.get("available"):
            return "draft_created", "validate"
        if not validation_summary.get("ok"):
            return "draft_created", "fix_validation"
        if not simulation_summary.get("available"):
            return "validated", "simulate"
        if simulation_freshness.get("status") == "stale":
            return "revised_after_simulation", "re_simulate"
        if simulation_summary.get("latest_decision") != "pass" or simulation_summary.get("rewrite_rate", 0.0) > 0 or simulation_summary.get("block_rate", 0.0) > 0:
            return "simulated", "revise"
        return "ready_to_submit", "submit"

    def _workflow_stages(
        self,
        *,
        stage: str,
        version: Optional[WorldVersion],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        stage_defs = [
            ("brief", "写 Brief"),
            ("draft_created", "创建 Draft"),
            ("validated", "校验通过"),
            ("simulated", "完成 Simulation"),
            ("revised_after_simulation", "修改后待重跑"),
            ("review_requested", "已请求内部审批"),
            ("changes_requested", "需要先处理修改意见"),
            ("approved_for_submit", "内部已批准，可送审"),
            ("ready_to_submit", "准备送审"),
            ("submitted", "已提交审核"),
        ]
        statuses: Dict[str, str] = {key: "pending" for key, _label in stage_defs}
        if version is None:
            statuses["brief"] = "current"
        else:
            statuses["brief"] = "complete"
            statuses["draft_created"] = "complete"
            if validation_summary.get("available") and validation_summary.get("ok"):
                statuses["validated"] = "complete"
            elif validation_summary.get("available"):
                statuses["validated"] = "blocked"
            if simulation_summary.get("available"):
                statuses["simulated"] = "complete"
            if simulation_freshness.get("status") == "stale":
                statuses["revised_after_simulation"] = "current"
            if stage == "ready_to_submit":
                statuses["ready_to_submit"] = "current"
            if version.status == "submitted":
                statuses["ready_to_submit"] = "complete"
                statuses["submitted"] = "current"
            elif stage == "simulated":
                statuses["simulated"] = "current"
            elif stage == "validated":
                statuses["validated"] = "current"
            elif stage == "draft_created":
                statuses["draft_created"] = "current"
        if stage == "brief":
            statuses["brief"] = "current"
        return [{"key": key, "label": label, "status": statuses[key]} for key, label in stage_defs]

    def _workflow_cta_actions(
        self,
        *,
        recommended_action: str,
        access: Dict[str, Any],
        version: Optional[WorldVersion],
    ) -> List[Dict[str, Any]]:
        actions = dict(access.get("actions", {}))

        def _access_enabled(action_key: str) -> tuple[bool, Optional[str]]:
            action_access = actions.get(action_key, {})
            return bool(action_access.get("allowed", True)), action_access.get("reason")

        ctas: List[Dict[str, Any]] = []
        if recommended_action == "create_from_brief":
            allowed, reason = _access_enabled("draft_from_brief")
            ctas.append({"action_id": "create_from_brief", "label": "根据 Brief 生成 Draft", "primary": True, "enabled": allowed, "reason": reason})
            save_allowed, save_reason = _access_enabled("save_draft")
            ctas.append({"action_id": "copy_current_world", "label": "从当前世界复制 Draft", "primary": False, "enabled": save_allowed, "reason": save_reason})
        elif recommended_action == "validate":
            allowed, reason = _access_enabled("validate_draft")
            ctas.append({"action_id": "validate_draft", "label": "运行校验", "primary": True, "enabled": allowed, "reason": reason})
        elif recommended_action == "fix_validation":
            ctas.append({"action_id": "focus_validation", "label": "查看校验问题", "primary": True, "enabled": True, "reason": None})
            ctas.append({"action_id": "focus_revision", "label": "跳到编辑区", "primary": False, "enabled": True, "reason": None})
        elif recommended_action in {"simulate", "re_simulate"}:
            allowed, reason = _access_enabled("simulate")
            ctas.append({"action_id": "simulate_draft", "label": "重新运行 Simulation" if recommended_action == "re_simulate" else "运行 Simulation", "primary": True, "enabled": allowed, "reason": reason})
            if recommended_action == "re_simulate":
                ctas.append({"action_id": "focus_diff", "label": "查看最近改动", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "revise":
            ctas.append({"action_id": "focus_simulation", "label": "查看模拟问题", "primary": True, "enabled": True, "reason": None})
            ctas.append({"action_id": "focus_diff", "label": "查看最近改动", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "submit":
            allowed, reason = _access_enabled("submit_draft")
            ctas.append({"action_id": "submit_draft", "label": "送审", "primary": True, "enabled": allowed, "reason": reason})
            ctas.append({"action_id": "focus_version_history", "label": "查看版本轨迹", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "wait_for_review":
            ctas.append({"action_id": "focus_version_history", "label": "查看审核状态", "primary": True, "enabled": True, "reason": None})
        if version is not None:
            ctas.append({"action_id": "focus_draft_detail", "label": "查看当前 Draft", "primary": False, "enabled": True, "reason": None})
        return ctas

    def _approval_summary(self, world_version_id: str) -> Dict[str, Any]:
        records = self.repository.list_author_approval_records(world_version_id=world_version_id)
        latest = records[0] if records else None
        return {
            "available": bool(records),
            "latest_status": latest.get("status") if latest else None,
            "latest_record": latest,
            "history": records,
        }

    def _collaboration_summary(self, world_version_id: str) -> Dict[str, Any]:
        threads = self.repository.list_author_comment_threads(world_version_id=world_version_id)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in threads:
            key = f"{item.get('anchor_type')}:{item.get('anchor_key')}"
            grouped.setdefault(key, []).append(item)
        threads_by_anchor = [
            {
                "anchor": key,
                "anchor_type": key.split(":", 1)[0],
                "anchor_key": key.split(":", 1)[1] if ":" in key else "",
                "thread_count": len(items),
                "open_count": sum(1 for thread in items if thread.get("status") == "open"),
                "blocking_count": sum(1 for thread in items if thread.get("status") == "open" and thread.get("severity") in {"blocker", "high"}),
                "threads": items,
            }
            for key, items in sorted(grouped.items())
        ]
        open_thread_count = sum(1 for item in threads if item.get("status") == "open")
        blocking_thread_count = sum(1 for item in threads if item.get("status") == "open" and item.get("severity") in {"blocker", "high"})
        return {
            "open_thread_count": open_thread_count,
            "blocking_thread_count": blocking_thread_count,
            "queue_summary": {
                "open_thread_count": open_thread_count,
                "blocking_thread_count": blocking_thread_count,
                "status_counts": {
                    status: sum(1 for item in threads if item.get("status") == status)
                    for status in sorted({str(item.get("status") or "unknown") for item in threads})
                },
            },
            "threads": threads,
            "threads_by_anchor": threads_by_anchor,
        }

    def _simulation_snapshot(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        chapter_trace_map = {
            item.get("chapter_id"): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if item.get("chapter_id")
        }
        chapter_snapshots = []
        for index, payload in enumerate(simulation_report.get("chapter_evaluations", []), start=1):
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            scores = dict(payload.get("scores") or {})
            lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
            trace = chapter_trace_map.get(chapter_id, {})
            chapter_snapshots.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_index": index,
                    "chapter_title": trace.get("chapter_title") or chapter_id,
                    "decision": payload.get("decision", {}).get("decision", "rewrite"),
                    "overall_score": round(float(scores.get("overall_score", 0.0)), 3),
                    "issue_codes": [issue.get("issue_code") for issue in payload.get("issues", []) if issue.get("issue_code")],
                    "signal_snapshot": {
                        "pacing": round(float(scores.get("pacing", 0.0)), 3),
                        "hook_quality": round(float(scores.get("hook_quality", 0.0)), 3),
                        "scene_density": round(float(scores.get("scene_density", 0.0)), 3),
                        "repetition_score": round(float(lint_metrics.get("repetition_score", 0.0)), 3),
                        "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0)), 3),
                        "concrete_detail_density": round(float(lint_metrics.get("concrete_detail_density", 0.0)), 3),
                    },
                    "body_excerpt": trace.get("body_excerpt", ""),
                }
            )
        return {
            "completed_chapters": simulation_report.get("completed_chapters", 0),
            "latest_decision": simulation_report.get("latest_decision"),
            "chapter_snapshots": chapter_snapshots,
        }

    def _build_revision_compare(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        if len(revisions) < 2:
            return {"available": False}
        before = revisions[-2]
        after = revisions[-1]
        return {
            "available": True,
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
            "before_label": before.get("label"),
            "after_label": after.get("label"),
            "before_summary": before.get("summary"),
            "after_summary": after.get("summary"),
            "after_diff_summary": dict(after.get("diff_summary") or {}),
            "section_counts": {
                "before_changed_sections": len((before.get("diff_summary") or {}).get("changed_sections", [])),
                "after_changed_sections": len((after.get("diff_summary") or {}).get("changed_sections", [])),
            },
            "simulation_delta": dict(after.get("simulation_delta") or {}),
            "simulation_freshness": self._simulation_freshness(metadata, simulation_report),
        }

    def _build_before_after_chapter_compare(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        simulated_revisions = [
            revision
            for revision in metadata.get("revision_history", [])
            if dict(revision.get("simulation_snapshot") or {})
        ]
        if len(simulated_revisions) < 2:
            return {"available": False}
        before = simulated_revisions[-2]
        after = simulated_revisions[-1]
        before_map = {
            int(item.get("chapter_index")): dict(item)
            for item in (before.get("simulation_snapshot") or {}).get("chapter_snapshots", [])
        }
        after_map = {
            int(item.get("chapter_index")): dict(item)
            for item in (after.get("simulation_snapshot") or {}).get("chapter_snapshots", [])
        }
        compares = []
        for chapter_index in sorted(set(before_map) & set(after_map)):
            left = before_map[chapter_index]
            right = after_map[chapter_index]
            left_issues = set(left.get("issue_codes", []))
            right_issues = set(right.get("issue_codes", []))
            left_signals = dict(left.get("signal_snapshot") or {})
            right_signals = dict(right.get("signal_snapshot") or {})
            compares.append(
                {
                    "chapter_index": chapter_index,
                    "before_title": left.get("chapter_title"),
                    "after_title": right.get("chapter_title"),
                    "before_decision": left.get("decision"),
                    "after_decision": right.get("decision"),
                    "overall_score_delta": round(float(right.get("overall_score", 0.0)) - float(left.get("overall_score", 0.0)), 3),
                    "issue_codes_added": sorted(right_issues - left_issues),
                    "issue_codes_removed": sorted(left_issues - right_issues),
                    "signal_deltas": {
                        key: round(float(right_signals.get(key, 0.0)) - float(left_signals.get(key, 0.0)), 3)
                        for key in {"pacing", "hook_quality", "scene_density", "repetition_score", "exposition_ratio", "concrete_detail_density"}
                    },
                    "before_excerpt": left.get("body_excerpt", ""),
                    "after_excerpt": right.get("body_excerpt", ""),
                }
            )
        compares.sort(key=lambda item: (-abs(float(item.get("overall_score_delta", 0.0))), item["chapter_index"]))
        return {
            "available": bool(compares),
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
            "chapter_compares": compares,
            "top_changed_chapters": compares[:5],
        }

    def workflow_summary(
        self,
        *,
        account_id: Optional[str],
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_account_id = self.billing.resolve_account_id(account_id=account_id) or account_id
        version = self._workflow_target_version(account_id=resolved_account_id, world_version_id=world_version_id)
        if not resolved_account_id and version is not None:
            resolved_account_id = version.author_id
        resolved_account_id = resolved_account_id or "web_author"
        selected_world_version_id = version.world_version_id if version else world_version_id
        access = self.billing.author_access_snapshot(
            account_id=resolved_account_id,
            world_version_id=selected_world_version_id,
        )
        validation_report = dict(version.validation_report_json or {}) if version else {}
        simulation_report = dict(version.simulation_report_json or {}) if version else {}
        metadata = dict((version.worldpack_json or {}).get("metadata", {})) if version else {}
        validation_summary = self._validation_summary(validation_report)
        simulation_summary = self._simulation_summary(simulation_report)
        simulation_freshness = self._simulation_freshness(metadata, simulation_report)
        collaboration_summary = self._collaboration_summary(version.world_version_id) if version else {
            "open_thread_count": 0,
            "blocking_thread_count": 0,
            "threads": [],
            "threads_by_anchor": [],
        }
        approval_summary = self._approval_summary(version.world_version_id) if version else {
            "available": False,
            "latest_status": None,
            "latest_record": None,
            "history": [],
        }
        stage, recommended_action = self._workflow_stage_and_action(
            version=version,
            validation_summary=validation_summary,
            simulation_summary=simulation_summary,
            simulation_freshness=simulation_freshness,
        )
        latest_approval_status = approval_summary.get("latest_status")
        if collaboration_summary.get("blocking_thread_count", 0) > 0:
            stage = "changes_requested"
            recommended_action = "revise"
        elif latest_approval_status == "requested":
            stage = "review_requested"
            recommended_action = "wait_for_review"
        elif latest_approval_status == "changes_requested":
            stage = "changes_requested"
            recommended_action = "revise"
        elif latest_approval_status == "approved" and simulation_freshness.get("status") == "fresh" and stage == "ready_to_submit":
            stage = "approved_for_submit"
            recommended_action = "submit"
        blockers = self._workflow_blockers(
            version=version,
            access=access,
            validation_summary=validation_summary,
            simulation_summary=simulation_summary,
            simulation_freshness=simulation_freshness,
        )
        return {
            "account_id": resolved_account_id,
            "world_version_id": version.world_version_id if version else None,
            "world_id": version.world_id if version else None,
            "draft_title": (version.worldpack_json or {}).get("title") if version else None,
            "status": version.status if version else "no_draft",
            "stage": stage,
            "recommended_action": recommended_action,
            "blockers": blockers,
            "stages": self._workflow_stages(
                stage=stage,
                version=version,
                validation_summary=validation_summary,
                simulation_summary=simulation_summary,
                simulation_freshness=simulation_freshness,
            ),
            "access": access,
            "collaboration_summary": collaboration_summary,
            "approval_summary": approval_summary,
            "open_blocking_threads": collaboration_summary.get("blocking_thread_count", 0),
            "can_request_approval": bool(version and validation_summary.get("ok") and simulation_summary.get("available") and version.status != "submitted"),
            "can_submit": bool(
                version
                and version.status != "submitted"
                and simulation_freshness.get("status") == "fresh"
                and latest_approval_status not in {"requested", "changes_requested"}
                and collaboration_summary.get("blocking_thread_count", 0) == 0
                and recommended_action == "submit"
            ),
            "validation_summary": validation_summary,
            "simulation_summary": simulation_summary,
            "simulation_freshness": simulation_freshness,
            "cta_actions": self._workflow_cta_actions(
                recommended_action=recommended_action,
                access=access,
                version=version,
            ),
        }

    def save_draft(self, worldpack: dict[str, Any], *, change_context: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        pack = WorldPack.from_dict(worldpack)
        pack_payload = pack.to_dict()
        context = self._normalize_change_context(change_context, default_source="manual_update", default_label="创建 draft")
        self._append_revision(
            worldpack_payload=pack_payload,
            change_context=context,
            diff_summary={
                "changed_sections": ["manifest", "world_bible", "characters", "scene_blueprints"],
                "character_changes": [],
                "scene_changes": [],
                "capability_changes": [],
                "summary_text": context["label"],
            },
        )
        pack = WorldPack.from_dict(pack_payload)
        report = validate_worldpack_payload(pack.to_dict())
        world_version_id = "%s@%s" % (pack.world_id, pack.version)
        version = WorldVersion.from_worldpack(
            worldpack=pack,
            world_version_id=world_version_id,
            status="draft",
            validation_report_json=report,
        )
        self.repository.save_world_version(version, publish=False)
        return {
            "world_version_id": world_version_id,
            "world_id": pack.world_id,
            "status": "draft",
            "validation_report": report,
        }

    def get_brief_template(self) -> dict[str, Any]:
        template_path = self.base_dir / "examples" / "worldpacks" / "author_brief_template.yaml"
        template_text = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        preset_ids = ["jade_court", "urban_mystery", "xianxia", "synthetic"]
        return {
            "template_text": template_text,
            "defaults": {
                "world_title": "",
                "genre_preset": "urban_mystery",
                "target_audience": "喜欢连续阅读型章节故事的读者",
                "genres": [],
                "core_premise": "",
                "life_theme": "",
                "lead_name": "主角",
                "counterpart_name": "对手",
                "supporting_name": "",
                "locations": "",
                "trial_chapters": 2,
                "paid_after": 3,
                "risk_rating": "PG-13",
                "author_id": "web_author",
            },
            "genre_presets": [
                {"id": "jade_court", "label": "权门伦理", "description": "家门、体面、师长压力与真心拉扯。"},
                {"id": "urban_mystery", "label": "都市情感悬疑", "description": "旧巷、隐瞒、关系债与真相回潮。"},
                {"id": "xianxia", "label": "仙侠誓愿", "description": "旧誓、反噬、修行与天命的取舍。"},
                {"id": "synthetic", "label": "极简实验", "description": "最小世界，用于快速试验 narrative kernel。"},
            ],
            "preset_defaults": {
                preset_id: {
                    "world_title": _genre_preset(preset_id)["title"],
                    "genre_preset": preset_id,
                    "core_premise": _genre_preset(preset_id)["premise"],
                    "life_theme": _genre_preset(preset_id)["life_theme"],
                    "lead_name": _genre_preset(preset_id)["lead_name"],
                    "counterpart_name": _genre_preset(preset_id)["counterpart_name"],
                    "supporting_name": _genre_preset(preset_id).get("supporting_name", ""),
                    "locations": "\n".join(_genre_preset(preset_id)["locations"]),
                }
                for preset_id in preset_ids
            },
        }

    def create_draft_from_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        pack = WorldPack.from_dict(self._worldpack_from_brief(brief))
        return self.save_draft(
            pack.to_dict(),
            change_context={"source": "brief_create", "label": "从 brief 生成 draft"},
        )

    def _worldpack_from_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        template_path = self.base_dir / "examples" / "worldpacks" / "world_template_minimal.json"
        payload = json.loads(template_path.read_text(encoding="utf-8"))
        preset_id = str(brief.get("genre_preset") or "urban_mystery")
        preset = _genre_preset(preset_id)
        world_title = str(brief.get("world_title") or preset["title"])
        lead_name = str(brief.get("lead_name") or preset["lead_name"])
        counterpart_name = str(brief.get("counterpart_name") or preset["counterpart_name"])
        supporting_name = str(brief.get("supporting_name") or preset.get("supporting_name") or "").strip()
        locations = [line.strip() for line in str(brief.get("locations") or "").splitlines() if line.strip()] or list(preset["locations"])
        version = "0.1.0-draft-%s" % uuid4().hex[:6]
        world_id = _slugify_world_id(world_title)
        genres = list(brief.get("genres") or []) or list(preset["genres"])
        core_premise = str(brief.get("core_premise") or preset["premise"])
        life_theme = str(brief.get("life_theme") or preset["life_theme"])
        risk_rating = str(brief.get("risk_rating") or "PG-13")
        trial_chapters = int(brief.get("trial_chapters") or 2)
        paid_after = int(brief.get("paid_after") or 3)
        author_id = str(brief.get("author_id") or "web_author")

        payload["world_id"] = world_id
        payload["title"] = world_title
        payload["version"] = version
        payload["manifest"]["author_id"] = author_id
        payload["manifest"]["genres"] = genres
        payload["manifest"]["risk_rating"] = risk_rating
        payload["manifest"]["monetization_policy"] = {
            "trial_chapters": trial_chapters,
            "paid_after": paid_after,
        }
        payload["world_bible"] = {
            "premise": core_premise,
            "canon_rules": list(preset["canon_rules"]),
            "forbidden_moves": list(preset["forbidden_moves"]),
            "locations": locations,
        }
        payload["style_pack"] = dict(preset["style_pack"])
        payload["risk_policy"] = {
            "shareable": True,
            "requires_manual_review": False,
        }
        payload["characters"] = _build_characters_for_preset(
            preset_id=preset_id,
            lead_name=lead_name,
            counterpart_name=counterpart_name,
            supporting_name=supporting_name,
            life_theme=life_theme,
        )
        payload["scene_blueprints"] = _build_scene_blueprints_for_preset(preset_id)
        payload["dialogue_realism_policy"] = dict(preset["dialogue_realism_policy"])
        payload["voice_profiles"] = _build_voice_profiles_for_preset(preset_id)
        payload["response_cadence_profiles"] = _build_response_profiles_for_preset(preset_id)
        payload["pressure_response_styles"] = _build_pressure_styles_for_preset(preset_id)
        payload["emotion_action_policies"] = _build_action_policies_for_preset(preset_id)
        payload["sensory_grounding_policies"] = _build_sensory_policies_for_preset(preset_id, locations)
        payload["scene_realization_contracts"] = _build_scene_realization_for_preset(preset_id)
        payload["metadata"] = {
            "author_brief": dict(brief),
            "generated_from_brief": True,
        }
        payload["narrative_style_pack"] = {
            "style_pack_id": "%s_style" % preset_id,
            "tonal_lexicon": list(preset["tonal_lexicon"]),
            "thematic_axis_labels": dict(preset["thematic_axis_labels"]),
            "hook_templates": list(preset["hook_templates"]),
            "goal_labels": {},
            "tag_labels": {genre: preset["thematic_axis_labels"].get(genre, genre.replace("_", " ")) for genre in genres},
            "dialogue": {
                **payload["dialogue_realism_policy"],
                "voice_profiles": payload["voice_profiles"],
                "response_profiles": payload["response_cadence_profiles"],
                "pressure_styles": payload["pressure_response_styles"],
            },
            "emotion_actions": payload["emotion_action_policies"]["default"],
            "sensory_grounding": payload["sensory_grounding_policies"]["default"],
            "scene_realization": payload["scene_realization_contracts"]["default"],
        }
        return payload

    def get_draft(self, world_version_id: str) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        return self._decorate_draft_payload(version)

    def update_draft(self, world_version_id: str, worldpack: dict[str, Any], *, change_context: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        previous_worldpack = copy.deepcopy(version.worldpack_json)
        pack = WorldPack.from_dict(worldpack)
        next_payload = pack.to_dict()
        context = self._normalize_change_context(change_context, default_source="manual_update", default_label="手动更新 draft")
        diff_summary = self._diff_sections(previous_worldpack, next_payload)
        self._append_revision(
            worldpack_payload=next_payload,
            change_context=context,
            diff_summary=diff_summary,
        )
        version.worldpack_json = next_payload
        version.manifest_json = pack.manifest.to_dict()
        version.validation_report_json = validate_worldpack_payload(pack.to_dict())
        version.status = "draft"
        self.repository.save_world_version(version, publish=False)
        return self.get_draft(world_version_id)

    def _select_candidate_world_version_id(self, world_id: str) -> str:
        versions = self.repository.list_world_versions(world_id=world_id)
        candidate = next((item for item in versions if item["status"] == "draft"), None) or (versions[0] if versions else None)
        if candidate is None:
            raise KeyError("unknown_world:%s" % world_id)
        return candidate["world_version_id"]

    def _baseline(self) -> Dict[str, Any] | None:
        baseline_path = self.base_dir / "tests" / "benchmark_baseline.json"
        if baseline_path.exists():
            return json.loads(baseline_path.read_text(encoding="utf-8"))
        return None

    def _build_cross_pack_summary(self, world_id: str, world_version_id: str) -> Dict[str, Any]:
        summary = run_benchmark(
            repository=self.repository,
            golden_dir=self.base_dir / "tests" / "golden_routes",
            worldpack="all",
            baseline=self._baseline(),
            world_version_overrides={world_id: world_version_id},
            simulation_runner=lambda benchmark_world_id, benchmark_world_version_id: self.run_simulation_for_world_version(
                benchmark_world_version_id,
                include_cross_pack=False,
            ),
        )
        return {
            "cross_pack_pass_rate": summary.get("cross_pack_pass_rate", 0.0),
            "top_failing_packs": summary.get("top_failing_packs", []),
            "delta_summary": summary.get("delta_summary", {}),
            "worlds": summary.get("worlds", []),
        }

    def run_simulation_for_world_version(
        self,
        world_version_id: str,
        *,
        include_cross_pack: bool = True,
        max_chapters: int = 6,
        min_end_turn_override: int | None = None,
    ) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        runtime = self.repository.get_runtime_bundle(world_version_id)
        state = NarrativeState.from_dict(runtime.initial_state.to_dict())
        if min_end_turn_override is not None:
            state.min_end_turn = max(int(min_end_turn_override), int(state.min_end_turn))
        completed_chapters = 0
        leak_detected = False
        latest_title = None
        reports = []
        chapter_trace = []
        stop_reason = "chapter_budget_reached"

        for _ in range(max_chapters):
            candidate_provider = (
                self.provider_routing.build_candidate_provider(
                    runtime.event_atoms,
                    surface="authoring_simulation",
                    account_id=str((version.worldpack_json or {}).get("manifest", {}).get("author_id") or "") or None,
                    session_id="simulation:%s" % version.world_id,
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                )
                if self.provider_routing
                else StaticCandidateProvider(runtime.event_atoms)
            )
            active_renderer = (
                self.provider_routing.build_renderer(
                    surface="authoring_simulation",
                    account_id=str((version.worldpack_json or {}).get("manifest", {}).get("author_id") or "") or None,
                    session_id="simulation:%s" % version.world_id,
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                )
                if self.provider_routing
                else TemplateRenderer()
            )
            started = perf_counter()
            result = plan_next_turn(
                state,
                world=runtime.world_record.world,
                candidate_provider=candidate_provider,
                renderer=active_renderer,
                debug=True,
            )
            runtime_latency_ms = round((perf_counter() - started) * 1000.0, 3)
            if result["status"] != "ok":
                stop_reason = str(result.get("status", "stopped"))
                break
            completed_chapters += 1
            latest_title = result["reader_view"]["chapter_title"]
            leak_detected = leak_detected or ("event_id" in result["reader_view"]["body"] or "seed_id" in result["reader_view"]["body"])
            state = NarrativeState.from_dict(result["updated_state"])
            lint_report = lint_chapter_draft(result["reader_view"]["body"])
            report = evaluate_chapter(
                chapter_id="simulation_%s_%s" % (world_version_id, completed_chapters),
                world_version_id=world_version_id,
                session_id="simulation:%s" % version.world_id,
                body=result["reader_view"]["body"],
                paragraphs=result["reader_view"]["body"].split("\n\n"),
                dialogue_count=int(lint_report["dialogue_count"]),
                action_count=int(lint_report["action_count"]),
                detail_count=int(lint_report["detail_count"]),
                character_fidelity_score=max(
                    [item["components"].get("character_fidelity", 0.0) for item in result["scored_candidates"]],
                    default=0.0,
                ),
                state_after=state,
                ending_ready=bool(result["chapter_plan"]["ending_ready"]) if result.get("chapter_plan") else False,
                choices=result["reader_view"]["choices"],
                paywall_required=False,
            )
            reports.append(report)
            rendered_debug = dict((result.get("rendered_scene") or {}).get("debug") or {})
            draft_metadata = dict(rendered_debug.get("draft_metadata") or {})
            chapter_trace.append(
                {
                    "chapter_id": "simulation_%s_%s" % (world_version_id, completed_chapters),
                    "chapter_title": result["reader_view"].get("chapter_title"),
                    "scene_function": (result.get("chosen_event") or {}).get("scene_function", ""),
                    "chosen_event_title": (result.get("chosen_event") or {}).get("title", ""),
                    "body_excerpt": (result.get("reader_view") or {}).get("body", "")[:280],
                    "beat_count": (result.get("chapter_plan") or {}).get("beat_count", 0),
                    "story_phase": (result.get("updated_state_summary") or {}).get("story_phase"),
                    "choices_preview": list((result.get("reader_view") or {}).get("choices", []))[:3],
                    "quality_pass_applied": bool(draft_metadata.get("quality_pass_applied", False)),
                    "quality_pass_actions": list(draft_metadata.get("quality_pass_actions", [])),
                    "critic_signal_count": len(result.get("critic_trace") or []),
                    "candidate_backend_routing": dict((result.get("candidate_batch") or {}).get("debug", {}).get("backend_routing") or {}),
                    "renderer_backend_routing": dict((result.get("rendered_scene") or {}).get("debug", {}).get("backend_routing") or {}),
                }
            )
            if self.observability is not None:
                manifest = dict((version.worldpack_json or {}).get("manifest", {}))
                author_account_id = str(manifest.get("author_id") or "") or None
                self.observability.record_runtime_receipt(
                    surface="authoring_simulation",
                    action="run_simulation",
                    response_status="ok",
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                    session_id="simulation:%s" % version.world_id,
                    account_id=author_account_id,
                    reader_id=author_account_id,
                    candidate_batch=result.get("candidate_batch"),
                    rendered_scene=result.get("rendered_scene"),
                    reader_view=result.get("reader_view"),
                    estimated_cost=round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3),
                    runtime_latency_ms=runtime_latency_ms,
                )

        aggregate = aggregate_reports(reports)
        simulation_report = {
            "ok": completed_chapters >= 3 and not leak_detected and aggregate["block_rate"] == 0.0,
            "world_version_id": world_version_id,
            "world_id": version.world_id,
            "completed_chapters": completed_chapters,
            "chapter_budget": max_chapters,
            "completion_ratio": round(completed_chapters / float(max(1, max_chapters)), 3),
            "min_end_turn_target": state.min_end_turn,
            "stop_reason": stop_reason if completed_chapters < max_chapters else "chapter_budget_reached",
            "terminated_by_budget": completed_chapters >= max_chapters,
            "latest_title": latest_title,
            "early_ending": completed_chapters < 3,
            "reader_leak_detected": leak_detected,
            "risk_flags": [] if not leak_detected else ["reader_leak"],
            "cost_estimate": round(0.18 * completed_chapters, 2),
            "evaluation_summary": aggregate,
            "latest_decision": reports[-1].decision.decision if reports else "rewrite",
            "chapter_evaluations": [report_item.to_dict() for report_item in reports],
            "chapter_trace": chapter_trace,
        }

        if include_cross_pack:
            cross_pack_summary = self._build_cross_pack_summary(version.world_id, world_version_id)
            simulation_report["cross_pack_summary"] = cross_pack_summary
            simulation_report["top_failing_packs"] = cross_pack_summary.get("top_failing_packs", [])
            simulation_report["metric_deltas"] = (
                cross_pack_summary.get("delta_summary", {})
                .get("world_deltas", {})
                .get(version.world_id, {})
            )

        evaluator_examples = self.training_signal.evaluator_examples_from_reports(
            simulation_report["chapter_evaluations"],
            world_id=version.world_id,
        )
        simulation_report["learned_evaluation_summary"] = self.learned_inference.summarize_examples(evaluator_examples)
        simulation_report["learned_shadow_summary"] = self.learned_shadow.summarize(
            simulation_report["learned_evaluation_summary"]
        )
        simulation_report["simulation_drilldown"] = self._build_simulation_drilldown(simulation_report)

        metadata = dict((version.worldpack_json or {}).get("metadata", {}))
        revision_history = list(metadata.get("revision_history", []))
        if revision_history:
            revision_history[-1]["simulation_delta"] = {
                "pass_rate_delta": simulation_report.get("metric_deltas", {}).get("pass_rate_delta"),
                "rewrite_rate_delta": simulation_report.get("metric_deltas", {}).get("rewrite_rate_delta"),
                "block_rate_delta": simulation_report.get("metric_deltas", {}).get("block_rate_delta"),
                "metric_deltas": dict(simulation_report.get("metric_deltas", {})),
            }
            revision_history[-1]["simulation_snapshot"] = self._simulation_snapshot(simulation_report)
            metadata["revision_history"] = revision_history[-10:]
            version.worldpack_json["metadata"] = metadata

        version.simulation_report_json = simulation_report
        self.repository.save_world_version(version, publish=False)
        return simulation_report

    def run_simulation(self, world_id: str) -> dict[str, Any]:
        return self.run_simulation_for_world_version(self._select_candidate_world_version_id(world_id))

    def submit_for_review(self, world_version_id: str) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        if not version.validation_report_json:
            version.validation_report_json = validate_worldpack_payload(version.worldpack_json)
            self.repository.save_world_version(version, publish=False)
        if not version.simulation_report_json:
            self.run_simulation_for_world_version(world_version_id)
            version = self.repository.get_world_version(world_version_id)
        version.status = "submitted"
        self.repository.save_world_version(version, publish=False)
        from .review import ReviewService

        review = ReviewService(self.repository).submit_world_version(world_version_id)
        return {
            "world_version_id": world_version_id,
            "status": "submitted",
            "review": review,
        }


def _slugify_world_id(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in title.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "custom_world"


def _genre_preset(preset_id: str) -> Dict[str, Any]:
    presets: Dict[str, Dict[str, Any]] = {
        "jade_court": {
            "title": "新门第试炼",
            "genres": ["duty", "love", "reputation"],
            "premise": "家门和情意互相牵扯，越想守住体面，越容易把真心逼到墙角。",
            "life_theme": "责任与真心能否同时被承担",
            "lead_name": "谢临",
            "counterpart_name": "沈霁",
            "supporting_name": "老夫人",
            "locations": ["花厅", "书房", "回廊"],
            "canon_rules": ["任何靠体面压下去的话，都会在更难看的时候回来。", "关系推进必须伴随代价。"],
            "forbidden_moves": ["无代价圆满", "一句话立刻化解所有误解"],
            "style_pack": {"mode": "novel_lush", "pov": "limited_third", "dialogue_density": "medium_high"},
            "tonal_lexicon": ["门第", "体面", "牵连", "旧账"],
            "thematic_axis_labels": {"duty": "责任与牵引", "love": "情意与靠近", "reputation": "名声与体面"},
            "hook_templates": ["这层体面先撑住了，可真正会追上来的，是那句被压回去的心里话。"],
            "dialogue_realism_policy": {"policy_id": "jade_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 2, "max_turns": 3, "turn_pattern": ["speaker", "reaction", "reply"], "minimum_exchanges": 1},
        },
        "urban_mystery": {
            "title": "旧巷回潮",
            "genres": ["urban_mystery", "truth", "suspense"],
            "premise": "一条旧巷里，越想压住的真相，越会换一种方式回来收债。",
            "life_theme": "真话是否值得承担失去",
            "lead_name": "江屹",
            "counterpart_name": "周岚",
            "supporting_name": "",
            "locations": ["旧巷", "便利店门口", "天桥下"],
            "canon_rules": ["任何隐瞒都会留下因果种子。", "关系推进必须伴随代价或误解。"],
            "forbidden_moves": ["神力直接解决问题", "无根由的完美和解"],
            "style_pack": {"mode": "novel_lush", "pov": "limited_third", "dialogue_density": "medium_high"},
            "tonal_lexicon": ["旧账", "巷口", "回声", "试探"],
            "thematic_axis_labels": {"urban_mystery": "真相与羞耻", "truth": "真相与揭露", "suspense": "悬疑与压迫"},
            "hook_templates": ["夜色先退了一步，可真正让人睡不着的，是下一次见面时还要不要继续问下去。"],
            "dialogue_realism_policy": {"policy_id": "urban_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 2, "max_turns": 3, "turn_pattern": ["speaker", "reaction", "reply"], "minimum_exchanges": 1},
        },
        "xianxia": {
            "title": "旧誓照骨",
            "genres": ["xianxia", "destiny", "truth"],
            "premise": "修行不是增添力量，而是看见自己到底愿意舍弃什么。",
            "life_theme": "旧誓与私心能否被同时承担",
            "lead_name": "沈照",
            "counterpart_name": "叶青烛",
            "supporting_name": "",
            "locations": ["偏殿", "石阶", "山门"],
            "canon_rules": ["每次逆天改命都会失去某种人间牵引。", "誓言可以护人也可以反噬。"],
            "forbidden_moves": ["主角毫无代价地逆天成功", "所有人都被一句话点悟"],
            "style_pack": {"mode": "manhua_drama", "pov": "limited_third", "dialogue_density": "medium"},
            "tonal_lexicon": ["旧誓", "反噬", "灵息", "山门"],
            "thematic_axis_labels": {"xianxia": "誓愿与天命", "destiny": "命运的去向", "truth": "真相与揭露"},
            "hook_templates": ["这一句先落在这里，可真正会逼人回头的，是下一次相见时还要不要认这层旧誓。"],
            "dialogue_realism_policy": {"policy_id": "xianxia_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 2, "max_turns": 3, "turn_pattern": ["speaker", "reaction", "reply"], "minimum_exchanges": 1},
        },
        "synthetic": {
            "title": "最小实验世界",
            "genres": ["synthetic", "truth", "selfhood"],
            "premise": "用于快速验证 narrative kernel 是否真的能承载不同的人和冲突。",
            "life_theme": "如何在压力里说真话",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "supporting_name": "",
            "locations": ["中庭", "长廊", "窗边"],
            "canon_rules": ["所有能力都应依赖 contract 与 pack assets，而不是角色名。", "推进必须伴随明确选择。"],
            "forbidden_moves": ["依赖特定礼法与家门语汇", "无差异模板化对白"],
            "style_pack": {"mode": "novel_light", "pov": "limited_third", "dialogue_density": "medium"},
            "tonal_lexicon": ["试探", "回声", "选择", "停顿"],
            "thematic_axis_labels": {"synthetic": "试探与选择", "truth": "真相与揭露", "selfhood": "自我与抉择"},
            "hook_templates": ["这层平静先撑住了，可真正要追上来的，是那句被按回去的真话。"],
            "dialogue_realism_policy": {"policy_id": "synthetic_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 2, "max_turns": 3, "turn_pattern": ["speaker", "reaction", "reply"], "minimum_exchanges": 1},
        },
    }
    return dict(presets.get(preset_id, presets["urban_mystery"]))


def _build_characters_for_preset(
    *,
    preset_id: str,
    lead_name: str,
    counterpart_name: str,
    supporting_name: str,
    life_theme: str,
) -> List[Dict[str, Any]]:
    shared = {
        "jade_court": {
            "lead": {
                "core_wound": "总在体面和真心之间被迫二选一",
                "public_self": "我能撑住全局",
                "shadow_desire": "有人先替我认一次真心",
                "defense_style": "克制与硬撑",
                "vows": ["不再只替所有人考虑"],
                "poisons": {"greed": 0.2, "anger": 0.18, "delusion": 0.34, "pride": 0.62, "doubt": 0.42},
            },
            "counterpart": {
                "core_wound": "被体面和规矩替自己做决定",
                "public_self": "我不在乎",
                "shadow_desire": "被平等地选一次",
                "defense_style": "冷问",
                "vows": ["不再接收半真半假的温柔"],
                "poisons": {"greed": 0.12, "anger": 0.24, "delusion": 0.22, "pride": 0.48, "doubt": 0.5},
            },
        },
        "urban_mystery": {
            "lead": {
                "core_wound": "被误解与被抛下",
                "public_self": "我能把残局收干净",
                "shadow_desire": "有人先站在我这边一次",
                "defense_style": "嘴硬与拖延",
                "vows": ["不再让重要的人从别人那里知道真相"],
                "poisons": {"greed": 0.28, "anger": 0.22, "delusion": 0.46, "pride": 0.52, "doubt": 0.61},
            },
            "counterpart": {
                "core_wound": "被替自己决定命运",
                "public_self": "我不在乎",
                "shadow_desire": "被平等对待",
                "defense_style": "冷问与收口",
                "vows": ["不再被半真半假的温柔说服"],
                "poisons": {"greed": 0.12, "anger": 0.24, "delusion": 0.28, "pride": 0.48, "doubt": 0.54},
            },
        },
        "xianxia": {
            "lead": {
                "core_wound": "守不住最想守的人",
                "public_self": "我只讲大道",
                "shadow_desire": "哪怕一回，只为一人偏路",
                "defense_style": "克制与自罚",
                "vows": ["我当年既许众生，便不能只为一人"],
                "poisons": {"greed": 0.34, "anger": 0.18, "delusion": 0.36, "pride": 0.68, "doubt": 0.22},
            },
            "counterpart": {
                "core_wound": "被大道放弃在身后",
                "public_self": "我只是来问一句旧话",
                "shadow_desire": "他能为我偏一次路",
                "defense_style": "冷问与不肯退",
                "vows": ["若旧誓真要反噬，也该有人与你同担"],
                "poisons": {"greed": 0.16, "anger": 0.24, "delusion": 0.22, "pride": 0.44, "doubt": 0.48},
            },
        },
        "synthetic": {
            "lead": {
                "core_wound": "被替自己决定",
                "public_self": "我很稳",
                "shadow_desire": "被认真听见",
                "defense_style": "迟疑",
                "vows": ["不再退后"],
                "poisons": {"greed": 0.2, "anger": 0.2, "delusion": 0.4, "pride": 0.5, "doubt": 0.4},
            },
            "counterpart": {
                "core_wound": "被隐瞒",
                "public_self": "我不在乎",
                "shadow_desire": "被平等对待",
                "defense_style": "冷处理",
                "vows": ["不替别人圆谎"],
                "poisons": {"greed": 0.1, "anger": 0.3, "delusion": 0.3, "pride": 0.5, "doubt": 0.5},
            },
        },
    }[preset_id]

    def _character(character_id: str, display_name: str, role: str, template: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "character_id": character_id,
            "display_name": display_name,
            "role": role,
            "destiny_contract": {"life_theme": life_theme or "面对真正的代价时，是否还敢继续往前。"},
            "poison_vector": template["poisons"],
            "vow_profile": {
                "vows": list(template["vows"]),
                "sacrifice_capacity": 0.68 if role == "lead" else 0.52,
                "truth_tolerance": 0.48 if role == "lead" else 0.72,
            },
            "wound_profile": {
                "core_wound": template["core_wound"],
                "public_self": template["public_self"],
                "shadow_desire": template["shadow_desire"],
                "defense_style": template["defense_style"],
            },
            "awakening_profile": {
                "clarity": 0.34 if role == "lead" else 0.46,
                "reflection_capacity": 0.62 if role == "lead" else 0.66,
                "repentance_threshold": 0.76 if role == "lead" else 0.68,
                "transformation_paths": ["坦白", "承担", "改口"],
            },
            "speech_traits": [template["defense_style"]],
            "action_traits": ["试探", "逼问" if role == "counterpart" else "强撑"],
        }

    characters = [
        _character("lead", lead_name, "lead", shared["lead"]),
        _character("counterpart", counterpart_name, "counterpart", shared["counterpart"]),
    ]
    if supporting_name:
        characters.append(
            {
                "character_id": "supporting",
                "display_name": supporting_name,
                "role": "supporting",
                "destiny_contract": {"life_theme": "在局势逼近时守住自己的分寸"},
                "poison_vector": {"greed": 0.1, "anger": 0.15, "delusion": 0.2, "pride": 0.4, "doubt": 0.35},
                "vow_profile": {"vows": ["先稳住局势"], "sacrifice_capacity": 0.45, "truth_tolerance": 0.55},
                "wound_profile": {"core_wound": "总在残局里收拾他人后果", "public_self": "我只看局面", "shadow_desire": "有人也替我考虑一次", "defense_style": "稳住场面"},
                "awakening_profile": {"clarity": 0.42, "reflection_capacity": 0.58, "repentance_threshold": 0.7, "transformation_paths": ["松手", "转身"]},
                "speech_traits": ["稳着说"],
                "action_traits": ["压场"],
            }
        )
    return characters


def _build_scene_blueprints_for_preset(preset_id: str) -> List[Dict[str, Any]]:
    variants = {
        "jade_court": [
            ("family_pressure", "setup", ["lead", "counterpart"], ["当众应下", "目光试探", "师长压来", "留下钩子"]),
            ("truth_trial", "trust_test", ["lead", "counterpart"], ["追问", "回避", "局面升级", "沉默余波"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["嘴硬", "旧伤碰响", "体面裂口", "各自收声"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["夜深相见", "一句真话", "不肯退让", "再留后患"]),
        ],
        "urban_mystery": [
            ("alley_meet", "setup", ["lead", "counterpart"], ["夜巷相遇", "试探", "藏而不说", "留下钩子"]),
            ("truth_request", "trust_test", ["lead", "counterpart"], ["追问", "回避", "情绪升级", "沉默余波"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["嘴硬", "旧伤碰响", "假平静裂开", "各自退半步"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["夜深重提旧事", "有人松口", "代价浮上来", "留下更重的问题"]),
        ],
        "xianxia": [
            ("lamp_awakens", "setup", ["lead", "counterpart"], ["古灯异动", "旧誓回响", "心意压下", "不祥预兆"]),
            ("vow_trial", "temptation", ["lead", "counterpart"], ["旧人现身", "誓言动摇", "代价显形", "强行压下"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["大道失守", "旧伤揭开", "私心露口", "不欢而散"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["偏殿对峙", "旧誓说破", "天命压下", "留下反噬"]),
        ],
        "synthetic": [
            ("synthetic_setup", "setup", ["lead", "counterpart"], ["入场", "试探", "沉默余波"]),
            ("synthetic_truth", "trust_test", ["lead", "counterpart"], ["追问", "回避", "硬着头皮开口"]),
            ("synthetic_mask", "reversal", ["lead", "counterpart"], ["嘴硬", "露怯", "裂口落地"]),
            ("synthetic_confession", "discovery", ["lead", "counterpart"], ["抓住窗口", "说半句真话", "留下更重后果"]),
        ],
    }
    return [
        {
            "scene_id": scene_id,
            "scene_function": scene_function,
            "phase_support": ["setup", "early_rising", "midpoint"],
            "required_roles": required_roles,
            "beats_template": beats,
        }
        for scene_id, scene_function, required_roles, beats in variants[preset_id]
    ]


def _build_voice_profiles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    if preset_id == "xianxia":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.54, "bluntness": 0.33, "restraint": 0.84, "social_rank_awareness": 0.72,
                "opening_style": ["旧誓若真要追上来，也该先由我自己接住。"],
                "pressure_style": ["你若非逼我开口，我也不愿让这层反噬先落到你身上。"],
                "pivot_style": ["大道我没有忘，只是这一次我也不能再把你留在身后。"],
                "aftermath_style": ["这一句先落在这里，后面的天罚我自己去领。"],
                "echo_style": ["等下一次再见时，我不会只带着一身沉默回来。"],
                "signature_replies": ["你先别替我断，我还想亲手把这句誓补完整。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "cool", "directness": 0.78, "bluntness": 0.61, "restraint": 0.46, "social_rank_awareness": 0.58,
                "opening_style": ["誓既然是你亲口许下的，就别总拿大道当成回避我的借口。"],
                "pressure_style": ["我来不是求你回头，是要你承认这道伤到底落在谁身上。"],
                "pivot_style": ["你若总想一个人把天命背完，那我偏要把这句话逼到明处。"],
                "aftermath_style": ["我先不替你收场，等你自己把这句旧誓认清。"],
                "echo_style": ["下次再见时，你最好带着真话，不是带着更圆的道理。"],
                "signature_replies": ["我不是来听你讲大道的，我是来问你到底还肯不肯看我。"],
            },
        }
    if preset_id == "jade_court":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.62, "bluntness": 0.41, "restraint": 0.74, "social_rank_awareness": 0.82,
                "opening_style": ["我知道这一步迟早得走，只是没想到会压得这样快。"],
                "pressure_style": ["你若真要逼我回答，我也不能再把自己缩回去。"],
                "pivot_style": ["真正难的不是选路，而是承认自己早就被逼到了墙角。"],
                "aftermath_style": ["我先把话放在这里，后面该担的我自己担。"],
                "echo_style": ["等下一次再开口时，我不会再只带着体面过来。"],
                "signature_replies": ["我先把话放在这里，剩下的路我自己认。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "cool", "directness": 0.8, "bluntness": 0.58, "restraint": 0.52, "social_rank_awareness": 0.76,
                "opening_style": ["你总可以继续讲体面，但我更想听你到底肯不肯认心里那一句。"],
                "pressure_style": ["我不怕难听，只怕你又拿规矩替自己找台阶。"],
                "pivot_style": ["再绕半步，这件事只会在更坏的时候追上来。"],
                "aftermath_style": ["我先记着，等你想清楚了再来把后半句补上。"],
                "echo_style": ["下次见我时，别再只带着更圆的话。"],
                "signature_replies": ["你最好别再只给我半句真话。"],
            },
        }
    if preset_id == "synthetic":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.56, "bluntness": 0.34, "restraint": 0.66, "social_rank_awareness": 0.18,
                "opening_style": ["我不是没想退，只是退到这里已经不算没选。"],
                "pressure_style": ["你要我认，我可以认，但别逼我装作从没动摇过。"],
                "pivot_style": ["既然已经看见这一层，我就不想再把它塞回去。"],
                "aftermath_style": ["这句话先落在这里，后面的代价我自己接。"],
                "echo_style": ["等下一次再说时，我不会再只带着沉默过来。"],
                "signature_replies": ["我先把这句认下，剩下的我不再推给局势。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "tight", "directness": 0.81, "bluntness": 0.63, "restraint": 0.44, "social_rank_awareness": 0.12,
                "opening_style": ["你要是不肯把话说明白，我就只能把它一路追到最里面。"],
                "pressure_style": ["我可以听难听的话，但不会再替你把裂口遮回去。"],
                "pivot_style": ["再绕半步，这件事只会换个地方继续裂。"],
                "aftermath_style": ["我先不替你收场，等你自己把后半句带回来。"],
                "echo_style": ["下次再来时，别只带着更圆的借口。"],
                "signature_replies": ["我可以先不走，但你别指望我继续替你圆这层假平静。"],
            },
        }
    return {
        "lead": {
            "profile_id": "lead", "cadence": "measured", "directness": 0.58, "bluntness": 0.37, "restraint": 0.71, "social_rank_awareness": 0.28,
            "opening_style": ["这条路我不是没想退过，只是退到这里已经来不及了。"],
            "pressure_style": ["你要我认，我可以认，可别逼我装作这一切从没发生。"],
            "pivot_style": ["我不是不怕失去，只是不想再靠沉默把人推远。"],
            "aftermath_style": ["话先落在这里，后面的亏欠我自己去补。"],
            "echo_style": ["等我下次再来，就不会只带着一句半真半假的话。"],
            "signature_replies": ["我先把这句认下，剩下的账我不会再赖给局势。"],
        },
        "counterpart": {
            "profile_id": "counterpart", "cadence": "cool", "directness": 0.82, "bluntness": 0.69, "restraint": 0.48, "social_rank_awareness": 0.22,
            "opening_style": ["你要是不肯把话说透，我就只能把它一层层逼出来。"],
            "pressure_style": ["我不怕难听，只怕你又拿沉默当成温柔。"],
            "pivot_style": ["再绕半步，这件事只会在更坏的时候反咬回来。"],
            "aftermath_style": ["我先记着，等你想清楚了再来把剩下那句说完。"],
            "echo_style": ["下次见我时，别再拿旧说辞来试探我的耐心。"],
            "signature_replies": ["我可以先不走，但你别指望我继续替你圆这层假平静。"],
        },
    }


def _build_response_profiles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    if preset_id == "xianxia":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["他先垂了垂眼，像把翻起来的灵息又一点点按回骨血里。"], "pressure": ["袍袖下的手指轻轻一蜷，连呼吸都像先被他自己截断了一截。"], "pivot": ["他这才抬眼，眼底那点动摇没有散尽，语气却已经不肯再退。"], "aftermath": ["收声时他反倒更静，静得像把更重的代价先压回自己身上。"], "echo": ["他不再追着解释，可那层未尽之意仍在周身灵息里发紧。"]},
                "reply_lines": {"entry": ["你既然追到这里，我便不想再把这句话藏回去。"], "pressure": ["我不是不肯认，只是不想让反噬先顺着你落下来。"], "pivot": ["若连这一句我都不敢承，后面的天命我也担不起。"], "aftermath": ["这层代价先记在我身上，你不必替我接。"], "echo": ["等我再回来时，我会把那句欠你的话一并补完。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["她并未立刻近前，只把目光钉在他脸上，像先把旧伤一寸寸照亮。"], "pressure": ["她指尖搭在剑穗上，没真碰响，那点停顿反而更像逼问。"], "pivot": ["她这才开口，语气清冷，却把最不肯听的那句推到了面前。"], "aftermath": ["她先收住了势，可那点不肯退的锋芒还停在原处。"], "echo": ["她不再多说，可檐下那声铃响倒像替她把余话追了回来。"]},
                "reply_lines": {"entry": ["你若还肯认这层旧誓，就别再拿沉默替自己挡。"], "pressure": ["我不怕反噬，只怕你又把我留在你那套大道之外。"], "pivot": ["你若总往后退，我就只好把这句真话追到山门外。"], "aftermath": ["先把这句放下，回头你还是得自己来接。"], "echo": ["下一回再见，我要听的是你的真心，不是更漂亮的道理。"]},
            },
        }
    if preset_id == "jade_court":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["他没有立刻接话，只让那句意思先在心里过了一遍。"], "pressure": ["他手上的细小动作先停住了，像终于不打算再替谁留余地。"], "pivot": ["他这才抬起眼来，语气仍不见急，可越平，越像逼人。"], "aftermath": ["他临到收声时反而更轻了些，可那点轻偏偏更重。"], "echo": ["他没有再追，可沉默已经替下一次相见留了一道裂口。"]},
                "reply_lines": {"entry": ["这句话既然出口，就别再往回收。"], "pressure": ["你总得先替自己承认一次。"], "pivot": ["再退半步，也只是让伤口换个地方继续裂。"], "aftermath": ["这事不会就这样过去。"], "echo": ["等你再来，就别只带着半句真话。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["她没立刻接，只把那点迟疑先压在眼底。"], "pressure": ["她先收了动作，反倒把那层分寸逼得更紧。"], "pivot": ["她这才开口，语气不急，却把每个字都落得很实。"], "aftermath": ["她没有继续追问，可那层不肯退的意思还停在原地。"], "echo": ["她先收了声，留下来的却是更重的一道边界。"]},
                "reply_lines": {"entry": ["既然你肯开口，就别只给我半句。"], "pressure": ["你要真想护谁，就别总拿规矩来替自己找退路。"], "pivot": ["我可以听难听的话，但不会替你把代价咽回去。"], "aftermath": ["这句先放在这里，回头你还是得自己来认。"], "echo": ["下一次见我时，最好带着真话来。"]},
            },
        }
    if preset_id == "synthetic":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["没有立刻接，只把那点迟疑在心里又压了一遍。"], "pressure": ["呼吸很轻地顿了一下，像解释已经挤到喉间却又被他自己按住。"], "pivot": ["这才抬眼，明明还在犹豫，语气却已经不想再退。"], "aftermath": ["到收声时反而更慢，像是在替后面的代价先让出位置。"], "echo": ["没再追着补话，可那点未尽之意还挂在肩背上。"]},
                "reply_lines": {"entry": ["既然都走到这里了，我不想再把这句收回去。"], "pressure": ["我不是不肯认，只是不想再拿沉默糊弄过去。"], "pivot": ["再往后退，我也还是得自己把这句真话接住。"], "aftermath": ["这层后果先记在我这里。"], "echo": ["等下一次再说时，我会把后半句一起带来。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["没有立刻发作，只把那句没说透的话牢牢按在视线里。"], "pressure": ["指尖在桌沿轻轻一停，像先替那句真话占了个位置。"], "pivot": ["这才开口，字不多，却每个都卡在最难回避的地方。"], "aftermath": ["没有继续逼，可那种不肯圆谎的态度反而更重。"], "echo": ["先收了声，留下来的却是更明确的一层边界。"]},
                "reply_lines": {"entry": ["既然要说，就别只给我半句。"], "pressure": ["你要是真想往前走，就别总把退路藏在沉默后面。"], "pivot": ["我可以听真话，但不会再替你把代价吞回去。"], "aftermath": ["这句先放在这里，回头你还是得自己来认。"], "echo": ["下次见我时，最好带着真相来。"]},
            },
        }
    return {
        "lead": {
            "cadence_id": "lead", "reaction_tempo": "measured",
            "reaction_lines": {"entry": ["没有立刻接话，只先把手机扣回掌心，像在替自己压住那点慌。"], "pressure": ["喉结很轻地动了一下，像那些解释已经挤到了嘴边，却又被他硬压回去。"], "pivot": ["这才抬起眼来，眼底的迟疑没退干净，语气却已经不肯再软。"], "aftermath": ["到收声时，他反而把呼吸放慢了，像是在替后面的代价腾位置。"], "echo": ["他没再追着解释，可那点没说完的话还在肩背上绷着。"]},
            "reply_lines": {"entry": ["你先别急着定我，我至少得把这一层说完。"], "pressure": ["我不是不敢认，只是不想再把你拖进同一个坑里。"], "pivot": ["既然已经走到这里，我就不想再装作什么都没看见。"], "aftermath": ["这句先算在我头上，后面的我不会再躲。"], "echo": ["等我再来时，我会把那句真正该说的带过来。"]},
        },
        "counterpart": {
            "cadence_id": "counterpart", "reaction_tempo": "tight",
            "reaction_lines": {"entry": ["她没立刻接，只把视线钉在他脸上，像先看穿那层没说出口的退路。"], "pressure": ["指尖在杯盖上轻敲了两下，脆响短得很，却把场面一下子敲紧了。"], "pivot": ["她这才开口，语气不高，反而像把每个字都压到了最难回避的位置。"], "aftermath": ["她没有继续逼，可那种不肯替人圆谎的态度反而更重。"], "echo": ["她先收了声，留下来的却是更明确的一层边界。"]},
            "reply_lines": {"entry": ["既然你肯开口，就别只给我半句。"], "pressure": ["你要真想护谁，就别总拿沉默来替自己找台阶。"], "pivot": ["我可以听真话，但不会再替你把后果咽回去。"], "aftermath": ["这句先放在这，迟早还要回来算清。"], "echo": ["下次见我时，你最好带着真相，不是带着更圆的借口。"]},
        },
    }


def _build_pressure_styles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    return {
        "lead": {
            "style_id": "lead",
            "under_pressure": "先压住动作，再把更难听的话轻一点说出来",
            "when_cornered": "沉默半拍后承认真正的裂口",
            "when_softening": "语气微松，但不立刻退让",
            "when_deflecting": "把心里最重的一句往旁边挪半寸",
        },
        "counterpart": {
            "style_id": "counterpart",
            "under_pressure": "先稳住目光，再把问题压到最难回避的位置",
            "when_cornered": "不替别人补台阶，只把真话逼到明处",
            "when_softening": "暂时收声，但不撤掉边界",
            "when_deflecting": "用更短的句子把退路堵回去",
        },
    }


def _build_action_policies_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    presets = {
        "jade_court": {
            "false_peace": {
                "entry": ["袖角拂过案沿，只一点轻响，厅里的分寸就全绷紧了。"],
                "pressure": ["茶盏还温着，谁也没先碰，倒像先把规矩摆到了人心上。"],
                "pivot": ["纸页一翘，连停顿都像在替谁把体面先挑开一线。"],
                "aftermath": ["人没立刻散，屋里的静却比刚才更沉。"],
                "echo": ["越到后面，灯火下那点没说完的话越像要回身索账。"],
                "repeat": ["动作不大，可谁都知道事情已经换了味道。"],
            },
            "truth_trial": {
                "entry": ["先动的不是声音，而是目光沿着席间一寸寸压过去。"],
                "pressure": ["灯影压在杯沿上，连换气都像先过了一道门槛。"],
                "pivot": ["最轻的一点改口，都像把场面推向了不得不认的那边。"],
                "aftermath": ["茶香渐淡，场里的气却更不肯散。"],
                "echo": ["等人散尽以后，空下来的位置还像留着刚才那句重话。"],
                "repeat": ["再往下走时，谁都回不到还能装作若无其事的一侧。"],
            },
            "mask_crack": {
                "entry": ["嘴上还稳着，真正先露出来的是指尖那一点不肯承认的迟疑。"],
                "pressure": ["对面的人不再追问，反而把那层遮掩衬得更薄。"],
                "pivot": ["一句话没能绕开，连站姿都跟着露了怯。"],
                "aftermath": ["表面上谁都没失态，可真正的裂口已经落在心里。"],
                "echo": ["等下一次再开口时，谁也回不到还能把体面讲圆的那边。"],
            },
            "confession_window": {
                "entry": ["回廊忽然静下来，像连风声都给这句真话让了一步。"],
                "pressure": ["那口气被人压了又压，最后还是没能把话咽回去。"],
                "pivot": ["对面的人没有补台阶，只把空白留成最逼人的催促。"],
                "aftermath": ["真话一落下来，连站在原地都更像一种表态。"],
                "echo": ["这一回先说到这里，可真正决定关系走向的，是谁会带着后半句回来。"],
            },
        },
        "urban_mystery": {},  # filled by current pack assets at runtime
        "xianxia": {},        # filled by current pack assets at runtime
        "synthetic": {},      # filled by current pack assets at runtime
    }
    action_map = presets.get(preset_id) or {
        "false_peace": {"entry": ["桌上的器物轻轻一碰，谁都知道这一步已经走出去，很难再收回来。"]},
        "truth_trial": {"entry": ["先动的不是声音，而是视线和手指那一点收紧。"]},
        "mask_crack": {"entry": ["嘴上还稳着，可真正先露出来的是那一点没藏住的停顿。"]},
        "confession_window": {"entry": ["屋里忽然安静下来，像所有杂音都先给这句真话让了地方。"]},
    }
    return {"default": {"policy_id": "%s_default_action" % preset_id, "action_map": action_map}}


def _build_sensory_policies_for_preset(preset_id: str, locations: List[str]) -> Dict[str, Dict[str, Any]]:
    if preset_id == "jade_court":
        slot_defaults = {
            "花厅": ("花厅里檀香还没散尽，窗外的天色却已经压低下来。", "杯沿上一点冷光轻轻一闪，把谁都不肯退的那层心思照了出来。", "灯火更低一寸，屋里的静反而比刚才更重。"),
            "书房": ("书房里纸香和墨气压得很稳，越稳，越显得谁都不肯先退。", "案角压着的纸页微微一翘，像替谁先揭开了遮掩。", "越到后面，纸页翻动的轻响越像把旧话重新翻出来。"),
            "回廊": ("回廊里的风比屋内更直，把灯影吹得一晃一晃。", "脚步踩过木板时，回声轻得像不肯认输的心跳。", "风声轻轻翻过去，连沉默都像被擦亮了一层。"),
        }
    elif preset_id == "xianxia":
        slot_defaults = {
            "偏殿": ("偏殿里灯焰不稳，薄薄一层金光把每个人心里的动摇都映得无处可藏。", "案上香灰斜斜坠下来，殿角风过时，铜铃只轻轻响了一声。", "越到后面，偏殿里那一点灯火越像把旧誓从灰里重新照了出来。"),
            "石阶": ("石阶上寒意贴着足底往上爬，连衣角擦过风声都显得格外冷。", "夜露落在阶边，月光从裂石里渗下来，把影子压得又细又长。", "风再过一遍石阶时，连沉默都像带了薄刃。"),
            "山门": ("山门外的风空得很，像专为那些说不出口的旧誓留出回响。", "远处云气压低，门前长阶只剩一点冷白，照得人连退路都看得太清。", "越靠近山门，越能听见那些没补完的誓言在风里一层层逼近。"),
        }
    elif preset_id == "synthetic":
        slot_defaults = {
            "中庭": ("中庭空得发亮，连人说话前那口气都像会先落在地上。", "风从廊檐底下穿过去，把纸页角和衣摆都掀起一点轻响。", "越到后面，中庭里那点回声越像把没说完的话一遍遍推回来。"),
            "长廊": ("长廊里脚步声拖得很长，像任何迟疑都会被放大。", "窗纸上挂着一点灰白的亮，连转身时衣料摩擦都显得分外清楚。", "长廊越静，那点不肯说透的心思就越像贴在身后。"),
            "窗边": ("窗边的光线斜斜落下来，把每个人脸上的犹豫都照得更薄。", "风碰着空杯边沿，发出一下极轻的响，倒像替谁先开了口。", "越靠近窗边，那点停不下来的回响越像逼人把话说完。"),
        }
    else:
        slot_defaults = {
            "旧巷": ("旧巷里潮气很重，墙面返出来的凉意像先替人把心口压窄了一圈。", "路灯把积水照出一层发灰的亮，连鞋底蹭过地面的声音都显得格外清。", "越到后面，巷子里的回声越像把那些没说完的话一遍遍弹回来。"),
            "便利店门口": ("便利店门口的白光太直，把每个人脸上的迟疑都照得无处可躲。", "冰柜的低鸣贴着耳边过去，塑料门帘轻轻一摆，带出一股凉得过分的甜味。", "门口那点白光不动声色，却把场面里的退路照得越来越窄。"),
            "天桥下": ("天桥下风声空荡，连一句压低的话都像会被钢梁重新弹回来。", "桥洞阴影压在肩头，远处车流从缝里掠过去，只留下短促的亮和噪音。", "越往后，桥下那种空空的回响越像把每个人心里的亏欠放大。"),
        }
    location_slots = {}
    for location in locations:
        atmosphere, detail, repeat_detail = slot_defaults.get(location, next(iter(slot_defaults.values())))
        location_slots[location] = {
            "atmosphere": [atmosphere],
            "detail": [detail],
            "repeat_detail": [repeat_detail],
        }
    generic = {
        "jade_court": {
            "atmosphere": ["屋里没有真正的安静，连空气都像在替谁压住一句没说完的话。"],
            "detail": ["最细小的灯影、纸页和杯沿冷光，都把场里的情绪衬得更清。"],
            "repeat_detail": ["等沉默拖长以后，最轻的一点响动反而更像回身索账。"],
        },
        "urban_mystery": {
            "atmosphere": ["这座城的夜里没有真正的安静，连空气都像替谁记着一笔旧账。"],
            "detail": ["最细小的光线和声响都在提醒人，这里没有一句话会白白落下去。"],
            "repeat_detail": ["等沉默拉长以后，城市里最轻的一点回声反而把情绪照得更明。"],
        },
        "xianxia": {
            "atmosphere": ["灵息与风声缠在一起，像谁都不肯先把那句真话放下。"],
            "detail": ["最轻的一点铃响和灯影，都把场里的取舍照得更锋利。"],
            "repeat_detail": ["等沉默拖长以后，连周身灵息都像替旧誓回了一次身。"],
        },
        "synthetic": {
            "atmosphere": ["屋里没有真正的安静，连空气都像在替人记着一句没说完的话。"],
            "detail": ["最轻的一点光线和声响，都把场里的试探照得更清。"],
            "repeat_detail": ["等沉默拖长以后，最小的动静反而成了最重的提醒。"],
        },
    }[preset_id]
    return {"default": {"policy_id": "%s_sensory" % preset_id, "location_slots": location_slots, "generic_slots": generic}}


def _build_scene_realization_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    presets = {
        "jade_court": {
            "scene_openings": {
                "false_peace": ["家门与体面先压下来。屋里的静稳得过分，像每一句真话都得先过一道门槛。"],
                "truth_trial": ["真正开始逼近的不是答案，而是那句谁都不肯先认下来的真话。"],
                "mask_crack": ["表面还稳着，可真正先裂开的，往往是那一点不肯承认的迟疑。"],
                "confession_window": ["有些话只有在风声也退开的时候，才会自己浮到嘴边。"],
            },
            "scene_hooks": {
                "false_peace": ["这层平静撑不了太久，真正要追上来的，是那句被按回去的心里话。"],
                "truth_trial": ["话先停在这里，可下一次见面时还要不要继续问下去，才是更难的那一步。"],
                "mask_crack": ["等下一次再开口时，谁都回不到还能把体面讲圆的那一边。"],
                "confession_window": ["这一回先说到这里，可真正决定走向的，是谁会带着后半句回来。"],
            },
        },
        "urban_mystery": {
            "scene_openings": {
                "false_peace": ["表面平静下的暗潮。旧巷的凉意先贴上来，像把每个人真正不肯承认的心思都逼到了嘴边。"],
                "truth_trial": ["真相开始逼近的时候，场面反而先静了一下，像谁都知道下一句会更难听。"],
                "mask_crack": ["嘴上还稳着，可真正先裂开的往往不是语气，而是那一点藏不住的停顿。"],
                "confession_window": ["有些真话只有在最安静的时候才会自己浮上来，像谁也压不回去。"],
            },
            "scene_hooks": {
                "false_peace": ["这层表面上的平静撑不过太久，真正会追上来的，是旧巷里那句没说尽的话。"],
                "truth_trial": ["话先落在这里，可真正让人睡不着的，往往是下一次见面时还要不要继续问下去。"],
                "mask_crack": ["等下一次再开口时，谁也回不到刚才那副还能装作没事的样子。"],
                "confession_window": ["这一回先说到这里，可真正决定关系走向的，是谁会先带着真相回来。"],
            },
        },
        "xianxia": {
            "scene_openings": {
                "false_peace": ["誓愿与天命先压下来。偏殿里的灯火不稳，像连空气都在替这层旧誓发颤。"],
                "temptation": ["真正先动摇的不是人，而是那一点被旧誓照亮以后再也压不住的执念。"],
                "mask_crack": ["大道还挂在嘴边，可真正先裂开的，是那一点再也讲不圆的私心。"],
                "confession_window": ["有些真话只有在灵息都静下来的时候才会自己浮上来，像谁也按不回去。"],
            },
            "scene_hooks": {
                "false_peace": ["这一层表面上的平静撑不过太久，真正要追上来的，是照骨灯里那句没人敢补完的旧誓。"],
                "temptation": ["话先停在这里，可真正难的，是下一次见面时谁还肯先认这层执念。"],
                "mask_crack": ["等下一次再开口时，谁都回不到还能把大道说得毫无裂缝的那边。"],
                "confession_window": ["这一回先说到这里，可真正决定命数的，是谁会带着那句真话回来。"],
            },
        },
        "synthetic": {
            "scene_openings": {
                "false_peace": ["表面平静下的暗潮。中庭里空得过分，像连空气都在等谁先把真话放下来。"],
                "truth_trial": ["真正开始逼近的不是答案，而是那句谁都不肯先认下来的真话。"],
                "mask_crack": ["表面还稳着，可真正先裂开的，往往是那一点不肯承认的迟疑。"],
                "confession_window": ["有些话只有在所有杂音都退开以后，才会自己浮到嘴边。"],
            },
            "scene_hooks": {
                "false_peace": ["这层平静撑不了太久，真正要追上来的，是那句被按回去的真话。"],
                "truth_trial": ["话先停在这里，可真正让人退不回去的，是下一次见面时还要不要继续问下去。"],
                "mask_crack": ["等下一次再开口时，谁都回不到刚才还能装稳的那一侧。"],
                "confession_window": ["这一回先说到这里，可真正决定走向的，是谁会带着后半句回来。"],
            },
        },
    }
    return {"default": {"contract_id": "%s_scene_realization" % preset_id, **presets[preset_id]}}
