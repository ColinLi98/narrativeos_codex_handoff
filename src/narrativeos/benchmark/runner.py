from __future__ import annotations

import argparse
import copy
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..content_quality_strategy_execution import (
    build_step_level_apply_summary,
    build_strategy_bundle_batch_validation_summary,
    build_strategy_bundle_batch_validation_trend,
    execute_strategy_bundle_protocol,
    list_strategy_bundle_batch_validation_history,
    record_strategy_bundle_batch_validation_run,
)
from ..content_quality_contracts import (
    asset_quality_contract_coverage,
    content_quality_window_metrics,
    diagnostic_issue_codes_for_chapter_payload,
)
from ..longform import calibrate_longform_thresholds, evaluate_longform_gate
from ..models import EvaluationReport
from ..quality.hard_constraints import (
    aggregate_generation_hard_constraint_summaries,
    summarize_generation_hard_constraints,
)
from ..repository import SQLAlchemyRepository
from ..services.training_signal import TrainingSignalService
from ..worldpacks.registry import FileSystemWorldRegistry
from .content_quality_contract_gate import evaluate_content_quality_contract_gate
from .reporting import (
    assign_diagnostic_ranks,
    benchmark_delta_report,
    build_strategy_validation_summary,
    build_content_quality_contract_summary,
    build_dimension_scores,
    build_interactive_long_route_summary,
    build_issue_mix,
    build_issue_summary,
    build_interactive_longform_signoff,
    build_long_route_diagnostics,
    build_long_route_summary,
    build_longform_250_human_review_closeout,
    build_longform_250_signoff,
    build_longform_250_interactive_signoff,
    build_longform_500_ending_signoff,
    build_longform_500_human_review_closeout,
    build_longform_500_interactive_signoff,
    build_longform_500_signoff,
    build_longform_1000_human_review_closeout,
    build_longform_1000_interactive_signoff,
    build_longform_1000_readiness,
    build_longform_1000_feasibility,
    build_longform_l1_signoff,
    build_weakest_pack_polish_program,
    build_route_diagnostics,
    build_weakest_pack_diagnostic,
    rank_strongest_packs,
    rank_top_failing_packs,
    rank_weakest_packs,
    render_benchmark_markdown,
)
from .release_quality_gate import evaluate_commercial_long_route_gate, evaluate_release_quality_gate


BENCHMARK_PACKS = [item["world_id"] for item in FileSystemWorldRegistry().list_benchmark_worldpacks()]
INTERACTIVE_LONGFORM_THRESHOLDS = {
    "steering_recovery_rate_min": 0.67,
    "post_steer_route_survival_min": 0.55,
    "memory_consistency_after_steer_min": 0.6,
    "promise_reconciliation_after_steer_min": 0.55,
    "replan_stability_score_min": 0.67,
}
INTERACTIVE_LONGFORM_250_THRESHOLDS = dict(INTERACTIVE_LONGFORM_THRESHOLDS)
INTERACTIVE_LONGFORM_500_THRESHOLDS = dict(INTERACTIVE_LONGFORM_THRESHOLDS)
INTERACTIVE_LONGFORM_1000_THRESHOLDS = dict(INTERACTIVE_LONGFORM_THRESHOLDS)
LONGFORM_250_REVIEW_WINDOWS = (
    ("1-20", 1, 20),
    ("80-120", 80, 120),
    ("200-250", 200, 250),
)
DIAGNOSTIC_SCAN_SLOW_MS = 250.0
BENCHMARK_STAGE_SLOW_MS = 60_000.0


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000.0, 3)


class _BenchmarkProgressWriter:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path
        self.started = perf_counter()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **fields: object) -> None:
        payload = {
            "schema_version": "benchmark_progress/v1",
            "event": event,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": _elapsed_ms(self.started),
            **fields,
        }
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        print(
            "[benchmark] %s %s"
            % (
                event,
                " ".join(f"{key}={value}" for key, value in fields.items() if value not in (None, "", [])),
            ),
            file=sys.stderr,
            flush=True,
        )

    def emit_stage(self, *, world_id: str, stage: str, elapsed_ms: float, **fields: object) -> None:
        severity = "warning" if elapsed_ms >= BENCHMARK_STAGE_SLOW_MS else "info"
        self.emit(
            "stage_complete",
            world_id=world_id,
            stage=stage,
            stage_elapsed_ms=round(float(elapsed_ms or 0.0), 3),
            severity=severity,
            **fields,
        )
        if severity == "warning":
            self.emit(
                "slow_stage",
                world_id=world_id,
                stage=stage,
                stage_elapsed_ms=round(float(elapsed_ms or 0.0), 3),
                threshold_ms=BENCHMARK_STAGE_SLOW_MS,
            )


def _diagnostic_issue_scan_key(payload: Dict[str, object], *, target_chapters: int) -> Tuple[object, ...]:
    lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
    repetition_bundle = dict(lint_metrics.get("repetition_signal_bundle") or {})
    issue_codes = tuple(
        sorted(
            str(item.get("issue_code") or "")
            for item in list(payload.get("issues") or [])
            if str(item.get("issue_code") or "")
        )
    )
    def metric(value: object) -> float:
        try:
            return round(float(value or 0.0), 6)
        except (TypeError, ValueError):
            return 0.0

    return (
        int(target_chapters or 0),
        str(payload.get("chapter_id") or ""),
        issue_codes,
        metric(lint_metrics.get("repetition_score", 0.0)),
        metric(lint_metrics.get("exposition_ratio", 0.0)),
        metric(lint_metrics.get("concrete_detail_density", 0.0)),
        metric(lint_metrics.get("dialogue_plus_action_ratio", 0.0)),
        metric(repetition_bundle.get("event_coverage_gap_score", 0.0)),
        metric(repetition_bundle.get("beat_coverage_gap_score", 0.0)),
        metric(dict(payload.get("scores") or {}).get("hook_quality", 0.0)),
    )


def _diagnostic_issue_scan_payload(payload: Dict[str, object]) -> Dict[str, object]:
    lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
    repetition_bundle = dict(lint_metrics.get("repetition_signal_bundle") or {})
    return {
        "chapter_id": payload.get("chapter_id"),
        "issues": [
            {"issue_code": str(item.get("issue_code") or "")}
            for item in list(payload.get("issues") or [])
            if str(item.get("issue_code") or "")
        ],
        "hard_validator_results": {
            "lint_metrics": {
                "repetition_score": lint_metrics.get("repetition_score", 0.0),
                "exposition_ratio": lint_metrics.get("exposition_ratio", 0.0),
                "concrete_detail_density": lint_metrics.get("concrete_detail_density", 0.0),
                "dialogue_plus_action_ratio": lint_metrics.get("dialogue_plus_action_ratio", 0.0),
                "repetition_signal_bundle": {
                    "event_coverage_gap_score": repetition_bundle.get("event_coverage_gap_score", 0.0),
                    "beat_coverage_gap_score": repetition_bundle.get("beat_coverage_gap_score", 0.0),
                },
            }
        },
        "scores": {
            "hook_quality": dict(payload.get("scores") or {}).get("hook_quality", 0.0),
            "overall_score": dict(payload.get("scores") or {}).get("overall_score", 0.0),
        },
    }


class _DiagnosticIssueScanCache:
    def __init__(self) -> None:
        self._entries: Dict[Tuple[object, ...], List[str]] = {}
        self.hits = 0
        self.misses = 0
        self.slow_scans: List[Dict[str, object]] = []

    def codes_for(self, payload: Dict[str, object], *, target_chapters: int) -> List[str]:
        key = _diagnostic_issue_scan_key(payload, target_chapters=target_chapters)
        if key in self._entries:
            self.hits += 1
            return list(self._entries[key])
        self.misses += 1
        scan_payload = _diagnostic_issue_scan_payload(payload)
        started = perf_counter()
        issue_codes = diagnostic_issue_codes_for_chapter_payload(
            scan_payload,
            target_chapters=target_chapters,
        )
        elapsed_ms = _elapsed_ms(started)
        if elapsed_ms >= DIAGNOSTIC_SCAN_SLOW_MS:
            self.slow_scans.append(
                {
                    "chapter_id": str(payload.get("chapter_id") or ""),
                    "elapsed_ms": elapsed_ms,
                    "issue_codes": list(issue_codes),
                }
            )
        self._entries[key] = list(issue_codes)
        return list(issue_codes)

    def summary(self) -> Dict[str, object]:
        return {
            "enabled": True,
            "scope": "benchmark_runner_process",
            "entry_count": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "slow_scan_threshold_ms": DIAGNOSTIC_SCAN_SLOW_MS,
            "slow_scan_count": len(self.slow_scans),
            "slow_scans": list(self.slow_scans[:10]),
            "payload_policy": "bounded_metrics_only",
        }


def _write_benchmark_checkpoint(
    path: Optional[Path],
    *,
    benchmark_mode: str,
    chapter_budget: int,
    worlds: Sequence[Dict[str, object]],
    diagnostic_scan_cache: _DiagnosticIssueScanCache,
    stage: str,
) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_worlds = [
        {
            "world_id": item.get("world_id"),
            "world_version_id": item.get("world_version_id"),
            "route_longevity": item.get("route_longevity"),
            "pass_rate": item.get("pass_rate"),
            "block_rate": item.get("block_rate"),
            "longform_500_gate": item.get("longform_500_gate"),
            "runtime_profile": item.get("runtime_profile"),
        }
        for item in worlds
    ]
    payload = {
        "schema_version": "benchmark_checkpoint/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "benchmark_mode": benchmark_mode,
        "chapter_budget": int(chapter_budget or 0),
        "completed_world_count": len(checkpoint_worlds),
        "completed_worlds": checkpoint_worlds,
        "diagnostic_issue_scan_cache": diagnostic_scan_cache.summary(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _split_world_id_tokens(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    result: List[str] = []
    for item in list(value or []):
        result.extend(_split_world_id_tokens(item))
    return list(dict.fromkeys(result))


def _baseline_weakest_world_ids(
    baseline: Dict[str, object] | None,
    *,
    limit: int,
) -> List[str]:
    if not baseline:
        return []
    candidates: List[str] = []
    for key_path in (
        ("weakest_packs",),
        ("top_failing_packs",),
        ("delta_summary", "ranking_changes", "current_weakest"),
    ):
        current: object = baseline
        for key in key_path:
            current = dict(current or {}).get(key) if isinstance(current, dict) else None
        if isinstance(current, list):
            for item in current:
                world_id = (
                    str(dict(item or {}).get("world_id") or "").strip()
                    if isinstance(item, dict)
                    else str(item or "").strip()
                )
                if world_id and world_id not in candidates:
                    candidates.append(world_id)
        if candidates:
            break
    if not candidates:
        ranked_worlds = sorted(
            [dict(item or {}) for item in list(baseline.get("worlds") or [])],
            key=lambda item: (
                int(item.get("diagnostic_rank", 9999) or 9999),
                -float(item.get("block_rate", 0.0) or 0.0),
                float(item.get("pass_rate", 1.0) or 1.0),
                str(item.get("world_id") or ""),
            ),
        )
        candidates = [str(item.get("world_id") or "") for item in ranked_worlds if str(item.get("world_id") or "")]
    return candidates[: max(0, int(limit or 0))]


def _resolve_acceptance_world_ids(
    requested_world_ids: Sequence[str],
    *,
    baseline: Dict[str, object] | None,
    acceptance_profile: str,
    changed_worldpacks: Sequence[str],
    fast_gate_weakest_limit: int,
) -> Dict[str, object]:
    requested = list(dict.fromkeys(str(item) for item in requested_world_ids if str(item)))
    changed = _split_world_id_tokens(changed_worldpacks)
    baseline_weakest = _baseline_weakest_world_ids(baseline, limit=fast_gate_weakest_limit)
    if acceptance_profile != "fast":
        return {
            "enabled": False,
            "acceptance_profile": acceptance_profile,
            "requested_world_ids": requested,
            "selected_world_ids": requested,
            "changed_world_ids": changed,
            "baseline_weakest_world_ids": baseline_weakest,
            "nightly_full_gate_required": False,
        }
    requested_set = set(requested)
    requested_all = requested_set == set(BENCHMARK_PACKS)
    seed_ids = list(dict.fromkeys(changed + baseline_weakest))
    if requested_all:
        selected = [world_id for world_id in BENCHMARK_PACKS if world_id in set(seed_ids)]
    else:
        selected = [world_id for world_id in requested if world_id in set(seed_ids)]
    if not selected:
        selected = requested[: max(1, min(len(requested), int(fast_gate_weakest_limit or 1)))]
    return {
        "enabled": True,
        "acceptance_profile": acceptance_profile,
        "requested_world_ids": requested,
        "selected_world_ids": selected,
        "changed_world_ids": changed,
        "baseline_weakest_world_ids": baseline_weakest,
        "nightly_full_gate_required": set(selected) != set(BENCHMARK_PACKS),
    }


def _quality_action_stage(action: object) -> str:
    normalized = str(action or "").lower()
    if normalized.startswith("q03") or "repetition" in normalized or "dedupe" in normalized:
        return "q03_repetition"
    if normalized.startswith("q04") or "exposition" in normalized or "dialogue_action" in normalized:
        return "q04_exposition"
    if normalized.startswith("q05") or "detail" in normalized or "sensory" in normalized or "anchor" in normalized:
        return "q05_detail"
    if normalized.startswith("q09") or "hook" in normalized or "ending" in normalized:
        return "q09_pacing"
    if normalized.startswith("length"):
        return "length_recovery"
    return "other"


def _quality_stage_action_counts(actions: Sequence[object]) -> Dict[str, int]:
    counts = {
        "q03_repetition": 0,
        "q04_exposition": 0,
        "q05_detail": 0,
        "q09_pacing": 0,
        "length_recovery": 0,
        "other": 0,
    }
    for action in actions:
        stage = _quality_action_stage(action)
        counts[stage] = counts.get(stage, 0) + 1
    return {stage: count for stage, count in counts.items() if count}


def _estimate_quality_stage_ms(action_counts: Dict[str, int], total_quality_pass_ms: float) -> Dict[str, float]:
    total_actions = sum(int(value or 0) for value in action_counts.values())
    if total_actions <= 0 or total_quality_pass_ms <= 0:
        return {}
    return {
        stage: round(float(total_quality_pass_ms) * (float(count) / float(total_actions)), 3)
        for stage, count in sorted(action_counts.items())
        if int(count or 0) > 0
    }


def _runtime_profile_from_chapter_trace(chapter_trace: Sequence[Dict[str, object]]) -> Dict[str, object]:
    trace = [dict(item or {}) for item in list(chapter_trace or [])]
    actions: List[object] = []
    for item in trace:
        actions.extend(list(item.get("quality_pass_actions") or []))
    quality_pass_ms = round(
        sum(float(dict(item.get("quality_pass_timing_ms") or {}).get("total_ms", 0.0) or 0.0) for item in trace),
        3,
    )
    lint_ms = round(sum(float(item.get("lint_latency_ms", 0.0) or 0.0) for item in trace), 3)
    evaluation_ms = round(sum(float(item.get("evaluation_latency_ms", 0.0) or 0.0) for item in trace), 3)
    generation_runtime_ms = round(sum(float(item.get("runtime_latency_ms", 0.0) or 0.0) for item in trace), 3)
    render_timing_totals: Dict[str, float] = {}
    for item in trace:
        for key, value in dict(item.get("render_timing_ms") or {}).items():
            render_timing_totals[str(key)] = render_timing_totals.get(str(key), 0.0) + float(value or 0.0)
    action_counts = _quality_stage_action_counts(actions)
    return {
        "chapter_count": len(trace),
        "generation_runtime_ms": generation_runtime_ms,
        "quality_pass_ms": quality_pass_ms,
        "lint_ms": lint_ms,
        "evaluation_ms": evaluation_ms,
        "render_timing_ms": {key: round(value, 3) for key, value in sorted(render_timing_totals.items())},
        "quality_pass_action_count": len(actions),
        "quality_pass_stage_action_counts": action_counts,
        "quality_pass_stage_estimated_ms": _estimate_quality_stage_ms(action_counts, quality_pass_ms),
        "quality_pass_stage_estimated": True,
    }


def _sum_stage(worlds: Sequence[Dict[str, object]], stage: str) -> float:
    return round(
        sum(float(dict(dict(item.get("runtime_profile") or {}).get("stages_ms") or {}).get(stage, 0.0) or 0.0) for item in worlds),
        3,
    )


def _build_benchmark_runtime_profile(
    *,
    worlds: Sequence[Dict[str, object]],
    total_wall_ms: float,
    acceptance_profile: str,
    fast_gate: Dict[str, object],
    post_world_summary_ms: float,
    diagnostic_issue_scan_cache: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    stage_names = [
        "simulation",
        "generation_runtime",
        "quality_pass",
        "lint",
        "evaluation",
        "report_conversion",
        "issue_mix",
        "route_diagnostics",
        "metrics_aggregation",
        "content_quality_contract",
        "world_total",
    ]
    stage_totals = {stage: _sum_stage(worlds, stage) for stage in stage_names}
    action_counts: Dict[str, int] = {}
    for item in worlds:
        for stage, count in dict(dict(item.get("runtime_profile") or {}).get("quality_pass_stage_action_counts") or {}).items():
            action_counts[str(stage)] = action_counts.get(str(stage), 0) + int(count or 0)
    slowest_worlds = sorted(
        [
            {
                "world_id": item.get("world_id"),
                "world_total_ms": float(dict(dict(item.get("runtime_profile") or {}).get("stages_ms") or {}).get("world_total", 0.0) or 0.0),
                "simulation_ms": float(dict(dict(item.get("runtime_profile") or {}).get("stages_ms") or {}).get("simulation", 0.0) or 0.0),
                "quality_pass_ms": float(dict(dict(item.get("runtime_profile") or {}).get("stages_ms") or {}).get("quality_pass", 0.0) or 0.0),
            }
            for item in worlds
        ],
        key=lambda item: -float(item["world_total_ms"]),
    )[:3]
    return {
        "schema_version": "benchmark_runtime_profile/v1",
        "acceptance_profile": acceptance_profile,
        "total_wall_ms": round(float(total_wall_ms), 3),
        "post_world_summary_ms": round(float(post_world_summary_ms), 3),
        "world_count": len(list(worlds or [])),
        "stage_totals_ms": stage_totals,
        "stage_avg_ms": {
            stage: round(total / float(max(1, len(list(worlds or [])))), 3)
            for stage, total in stage_totals.items()
        },
        "quality_pass_stage_action_counts": dict(sorted(action_counts.items())),
        "slowest_worlds": slowest_worlds,
        "safe_caches": {
            "diagnostic_issue_scan": dict(diagnostic_issue_scan_cache or {}),
            "repetition_signal_bundle": {
                "enabled": True,
                "scope": "process_local_lru",
                "max_entries": 512,
            },
            "repetition_char_ngrams": {
                "enabled": True,
                "scope": "process_local_lru",
                "max_entries": 16384,
            },
            "repetition_semantic_feature_vector": {
                "enabled": True,
                "scope": "process_local_lru",
                "max_entries": 16384,
            }
        },
        "fast_gate": dict(fast_gate),
    }


def _default_interactive_scenarios(pack_payload: Dict[str, object], target_chapters: int) -> List[Dict[str, object]]:
    characters = [str((item or {}).get("character_id") or "") for item in pack_payload.get("characters", []) if str((item or {}).get("character_id") or "")]
    impacted = characters[:2]
    arc_plans = [dict(item) for item in pack_payload.get("arc_plans", [])]
    middle_arc = arc_plans[min(len(arc_plans) // 2, max(0, len(arc_plans) - 1))] if arc_plans else {}
    mild_trigger = max(4, min(target_chapters, int(round(target_chapters * 0.15))))
    arc_trigger = max(mild_trigger + 4, min(target_chapters, int(round(target_chapters * 0.33))))
    memory_trigger = max(arc_trigger + 4, min(target_chapters, int(round(target_chapters * 0.5))))
    return [
        {
            "scenario_id": "mild_steer",
            "scenario_kind": "mild_steer",
            "trigger_chapter": mild_trigger,
            "label": "Reader 小幅改变关系推进方向",
            "steering_directive": {
                "steering_type": "mild_steer",
                "current_user_intent": "我想让他们先把关系试探得更深一点，再决定要不要说真话。",
                "impacted_character_ids": impacted,
            },
        },
        {
            "scenario_id": "arc_steer",
            "scenario_kind": "arc_steer",
            "trigger_chapter": arc_trigger,
            "label": "Reader 中途要求改弧线目标",
            "steering_directive": {
                "steering_type": "arc_steer",
                "current_user_intent": "这一段我想先把代价和关系债抬高，不要急着回收。",
                "impacted_character_ids": impacted,
                "affected_arc_id": middle_arc.get("arc_id"),
                "arc_goal_shift": "延后回收，先放大代价与关系债。",
            },
        },
        {
            "scenario_id": "memory_steer",
            "scenario_kind": "memory_steer",
            "trigger_chapter": memory_trigger,
            "label": "Reader 给角色补关键记忆",
            "steering_directive": {
                "steering_type": "memory_steer",
                "current_user_intent": "我希望他突然想起一段旧事，这会影响他后面的选择。",
                "impacted_character_ids": impacted[:1],
                "memory_patch_note": "角色突然想起一段会改变当前选择的私人旧事，但这段记忆只影响未来章节。",
            },
        },
    ]


def _strong_interactive_scenarios(pack_payload: Dict[str, object], target_chapters: int) -> List[Dict[str, object]]:
    characters = [str((item or {}).get("character_id") or "") for item in pack_payload.get("characters", []) if str((item or {}).get("character_id") or "")]
    impacted = characters[:2]
    arc_plans = [dict(item) for item in pack_payload.get("arc_plans", [])]
    early_arc = arc_plans[min(max(0, len(arc_plans) // 4), max(0, len(arc_plans) - 1))] if arc_plans else {}
    late_arc = arc_plans[min(max(0, (len(arc_plans) * 3) // 4), max(0, len(arc_plans) - 1))] if arc_plans else {}
    scenarios = [
        {
            "scenario_id": "strong_mild_20",
            "scenario_kind": "mild_steer",
            "trigger_chapter": 20,
            "label": "Reader 要求关系升温但不提前回收。",
            "steering_directive": {
                "steering_type": "mild_steer",
                "current_user_intent": "先把关系试探和暧昧压力拉高，但不要急着回收或解释。",
                "impacted_character_ids": impacted,
                "summary": "关系升温但不回收。",
            },
        },
        {
            "scenario_id": "strong_arc_60",
            "scenario_kind": "arc_steer",
            "trigger_chapter": 60,
            "label": "Reader 要求延后 payoff，先抬高代价。",
            "steering_directive": {
                "steering_type": "arc_steer",
                "current_user_intent": "这一段先把代价和关系债拉高，不要急着兑现 payoff。",
                "impacted_character_ids": impacted,
                "affected_arc_id": early_arc.get("arc_id"),
                "arc_goal_shift": "延后 payoff，先抬高代价与关系债。",
                "summary": "延后 payoff，先抬高代价。",
            },
        },
        {
            "scenario_id": "strong_memory_100",
            "scenario_kind": "memory_steer",
            "trigger_chapter": 100,
            "label": "Reader 注入关键旧事记忆。",
            "steering_directive": {
                "steering_type": "memory_steer",
                "current_user_intent": "让角色突然记起一段关键旧事，这段记忆会改变之后的判断。",
                "impacted_character_ids": impacted[:1],
                "memory_patch_note": "角色在中段补回一段关键旧事记忆，这段记忆会影响后续选择，但不能直接改写已发生章节。",
                "summary": "补入关键旧事记忆。",
            },
        },
        {
            "scenario_id": "strong_arc_140",
            "scenario_kind": "arc_steer",
            "trigger_chapter": 140,
            "label": "Reader 要求把冲突重心从解释转向代价/关系债。",
            "steering_directive": {
                "steering_type": "arc_steer",
                "current_user_intent": "后半段少解释，多让代价和关系债推动剧情。",
                "impacted_character_ids": impacted,
                "affected_arc_id": late_arc.get("arc_id"),
                "arc_goal_shift": "从解释型冲突改成代价与关系债驱动。",
                "summary": "把冲突改成代价/关系债驱动。",
            },
        },
        {
            "scenario_id": "strong_mild_180",
            "scenario_kind": "mild_steer",
            "trigger_chapter": 180,
            "label": "Reader 要求保留终局压力，禁止提前收尾。",
            "steering_directive": {
                "steering_type": "mild_steer",
                "current_user_intent": "临近结尾也要保留终局压力，不要提前化解或仓促收尾。",
                "impacted_character_ids": impacted,
                "summary": "保留终局压力，禁止提前收尾。",
            },
        },
    ]
    return [
        scenario
        for scenario in scenarios
        if int(scenario.get("trigger_chapter", 0) or 0) <= int(target_chapters)
    ]


def _resolve_interactive_scenarios(
    *,
    pack_payload: Dict[str, object],
    target_chapters: int,
    benchmark_mode: str,
    interactive_profile: Optional[str],
) -> List[Dict[str, object]]:
    if interactive_profile == "strong":
        return _strong_interactive_scenarios(pack_payload, target_chapters)
    if interactive_profile == "default":
        return _default_interactive_scenarios(pack_payload, target_chapters)
    if benchmark_mode in {"longform_100_interactive", "longform_250_interactive", "longform_500_interactive", "longform_1000_interactive"}:
        return _default_interactive_scenarios(pack_payload, target_chapters)
    return []


def _first_matching_bundle(
    bundles: Sequence[Dict[str, object]],
    *,
    strategy_bundle_id: str,
) -> Dict[str, object]:
    return next(
        (
            dict(item or {})
            for item in list(bundles or [])
            if str((item or {}).get("strategy_bundle_id") or "") == strategy_bundle_id
        ),
        {},
    )


def _validate_strategy_bundle_batch(
    *,
    repository: SQLAlchemyRepository,
    registry: FileSystemWorldRegistry,
    weakest_packs: Sequence[Dict[str, object]],
    weakest_pack_diagnostics: Sequence[Dict[str, object]],
    strategy_validation_summary: Dict[str, object],
    strategy_bundle_id: str,
    benchmark_mode: str,
    max_chapters: int,
    weakest_limit: int,
    min_end_turn_override: int | None,
    interactive_profile: Optional[str],
    pack_payload_by_world: Dict[str, Dict[str, object]],
    baseline_reports_by_world: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    if not strategy_bundle_id:
        return {
            "available": False,
            "strategy_bundle_id": "",
            "strategy_bundle_label": "",
            "batch_execution_mode": "ephemeral_copy",
            "benchmark_mode": benchmark_mode,
            "chapter_budget": max_chapters,
            "weakest_source_world_ids": [],
            "compatible_world_ids": [],
            "skipped_worlds": [],
            "validated_world_count": 0,
            "validated_worlds": [],
            "aggregated_step_receipts": {},
            "aggregated_result_attribution": {},
            "effectiveness_rate": 0.0,
            "decision": "",
            "decision_reason": "no_compatible_weakest_packs",
            "adaptation_targets": [],
        }
    bundle_group = next(
        (
            dict(item or {})
            for item in list((strategy_validation_summary.get("bundle_groups") or []))
            if str((item or {}).get("strategy_bundle_id") or "") == strategy_bundle_id
        ),
        {},
    )
    strategy_bundle_label = str(bundle_group.get("strategy_bundle_label") or strategy_bundle_id)
    weakest_source_world_ids = [
        str(item.get("world_id") or "")
        for item in list(weakest_packs or [])[: max(1, int(weakest_limit or 3))]
        if str(item.get("world_id") or "")
    ]
    weakest_diagnostic_map = {
        str(item.get("world_id") or ""): dict(item or {})
        for item in list(weakest_pack_diagnostics or [])
        if str(item.get("world_id") or "")
    }
    compatible_world_ids: List[str] = []
    skipped_worlds: List[Dict[str, object]] = []
    validated_worlds: List[Dict[str, object]] = []

    from ..services.authoring import AuthoringService

    authoring = AuthoringService(repository, registry=registry)

    for world_id in weakest_source_world_ids:
        diagnostic = dict(weakest_diagnostic_map.get(world_id) or {})
        recommended_bundle = _first_matching_bundle(
            diagnostic.get("recommended_strategy_bundles") or [],
            strategy_bundle_id=strategy_bundle_id,
        )
        if not recommended_bundle:
            skipped_worlds.append(
                {
                    "world_id": world_id,
                    "reason": "bundle_not_recommended_for_world",
                }
            )
            continue
        compatible_world_ids.append(world_id)
        pack_payload = copy.deepcopy(pack_payload_by_world.get(world_id) or {})
        baseline_report = copy.deepcopy(baseline_reports_by_world.get(world_id) or {})
        if not baseline_report:
            skipped_worlds.append(
                {
                    "world_id": world_id,
                    "reason": "baseline_simulation_unavailable",
                }
            )
            continue
        workbench = authoring._build_content_quality_repair_workbench(pack_payload, baseline_report)
        campaigns = [
            dict(item or {})
            for item in list(workbench.get("campaigns") or [])
            if str(dict(item.get("strategy_bundle") or {}).get("strategy_bundle_id") or "") == strategy_bundle_id
        ]
        selected_campaign = campaigns[0] if campaigns else {}
        if not selected_campaign:
            skipped_worlds.append(
                {
                    "world_id": world_id,
                    "reason": "campaign_not_found_in_workbench",
                }
            )
            continue
        strategy_bundle = dict(selected_campaign.get("strategy_bundle") or {})
        interactive_scenarios = _resolve_interactive_scenarios(
            pack_payload=pack_payload,
            target_chapters=max_chapters,
            benchmark_mode=benchmark_mode,
            interactive_profile=interactive_profile,
        )

        def _ephemeral_simulation_runner(mutated_worldpack_payload: Dict[str, object]) -> Dict[str, object]:
            with TemporaryDirectory(prefix="strategy_bundle_batch_") as temp_dir:
                temp_repository = SQLAlchemyRepository(
                    database_url="sqlite:///%s" % (Path(temp_dir) / "strategy_bundle_batch.db")
                )
                temp_authoring = AuthoringService(temp_repository, registry=registry)
                draft = temp_authoring.save_draft(
                    copy.deepcopy(mutated_worldpack_payload),
                    change_context={
                        "source": "strategy_bundle_batch_validator",
                        "label": "临时策略包验证",
                    },
                )
                return temp_authoring.run_simulation_for_world_version(
                    draft["world_version_id"],
                    include_cross_pack=False,
                    max_chapters=max_chapters,
                    min_end_turn_override=min_end_turn_override,
                    interactive_scenarios=interactive_scenarios or None,
                )

        execution_receipt = execute_strategy_bundle_protocol(
            worldpack_payload=pack_payload,
            baseline_simulation_report=baseline_report,
            campaign=selected_campaign,
            strategy_bundle=strategy_bundle,
            execution_mode="ephemeral_copy",
            simulation_runner=_ephemeral_simulation_runner,
            apply_step=authoring._apply_strategy_bundle_step,
            build_result_attribution=authoring._build_strategy_bundle_result_attribution,
            build_stop_decision=authoring._build_strategy_bundle_stop_decision,
            prior_executions=[],
        )
        step_level_apply_receipt = list(execution_receipt.get("step_level_apply_receipt") or [])
        step_receipt_summary = build_step_level_apply_summary(step_level_apply_receipt)
        result_attribution = dict(execution_receipt.get("result_attribution") or {})
        stop_decision = dict(execution_receipt.get("stop_decision") or {})
        ready_for_validation = bool(
            dict(execution_receipt.get("repair_loop_outcome") or {}).get("ready_for_validation", False)
            or result_attribution.get("ready_for_validation", False)
        )
        validated_worlds.append(
            {
                "world_id": world_id,
                "campaign_id": str(selected_campaign.get("campaign_id") or ""),
                "window_label": str(selected_campaign.get("window_label") or ""),
                "issue_codes": list(dict.fromkeys(str(item) for item in list(strategy_bundle.get("issue_codes") or []) if str(item))),
                "step_level_apply_receipt": step_level_apply_receipt,
                "step_receipt_summary": step_receipt_summary,
                "result_attribution": result_attribution,
                "stop_decision": stop_decision,
                "ready_for_validation": ready_for_validation,
            }
        )
    return build_strategy_bundle_batch_validation_summary(
        strategy_bundle_id=strategy_bundle_id,
        strategy_bundle_label=strategy_bundle_label,
        batch_execution_mode="ephemeral_copy",
        benchmark_mode=benchmark_mode,
        chapter_budget=max_chapters,
        weakest_source_world_ids=weakest_source_world_ids,
        compatible_world_ids=compatible_world_ids,
        skipped_worlds=skipped_worlds,
        validated_worlds=validated_worlds,
    )


def _review_sampling_plan_250(report: Dict[str, object], *, world_id: str, world_version_id: str) -> List[Dict[str, object]]:
    chapter_ids = [str(item.get("chapter_id") or "") for item in report.get("chapter_evaluations", [])]
    available_indices = [int(chapter_id.rsplit("_", 1)[-1]) for chapter_id in chapter_ids if chapter_id.rsplit("_", 1)[-1].isdigit()]
    max_index = max(available_indices or [0])
    top_issue_categories = list((report.get("evaluation_summary") or {}).get("top_issue_categories", []))
    issue_focus = [str(item.get("issue_code") or "") for item in top_issue_categories[:2] if str(item.get("issue_code") or "")]
    plan: List[Dict[str, object]] = []
    for window_label, start, end in LONGFORM_250_REVIEW_WINDOWS:
        candidates = [index for index in available_indices if start <= index <= end]
        if not candidates:
            continue
        picks = [candidates[0]]
        if len(candidates) > 1:
            picks.append(candidates[min(len(candidates) - 1, len(candidates) // 2)])
        seen = set()
        for priority, chapter_index in enumerate(picks, start=1):
            if chapter_index in seen:
                continue
            seen.add(chapter_index)
            plan.append(
                {
                    "world_id": world_id,
                    "world_version_id": world_version_id,
                    "window_label": window_label,
                    "chapter_index": chapter_index,
                    "issue_focus": issue_focus or ["Q03", "Q05", "Q09"],
                    "priority": priority,
                    "reason": f"longform_250_window_{window_label}",
                    "available_chapter_max": max_index,
                }
            )
    return plan


def _chapter_surface_issue_payloads(
    chapter_report_payloads: Sequence[Dict[str, object]],
    *,
    target_chapters: int,
    diagnostic_scan_cache: Optional[_DiagnosticIssueScanCache] = None,
) -> List[Dict[str, object]]:
    issue_payloads: List[Dict[str, object]] = []
    for payload in chapter_report_payloads:
        surfaced_issue_codes = _surface_issue_codes_for_payload(
            dict(payload),
            target_chapters=target_chapters,
            diagnostic_scan_cache=diagnostic_scan_cache,
        )
        for issue_code in surfaced_issue_codes:
            issue_payloads.append({"issue_code": issue_code})
    return issue_payloads


def _surface_issue_codes_for_payload(
    payload: Dict[str, object],
    *,
    target_chapters: int,
    diagnostic_scan_cache: Optional[_DiagnosticIssueScanCache] = None,
) -> List[str]:
    seen_issue_codes = {
        str(item.get("issue_code") or "")
        for item in list(payload.get("issues") or [])
        if str(item.get("issue_code") or "")
    }
    surfaced_issue_codes = list(seen_issue_codes)
    diagnostic_issue_codes = (
        diagnostic_scan_cache.codes_for(dict(payload), target_chapters=target_chapters)
        if diagnostic_scan_cache is not None
        else diagnostic_issue_codes_for_chapter_payload(
            _diagnostic_issue_scan_payload(dict(payload)),
            target_chapters=target_chapters,
        )
    )
    for issue_code in diagnostic_issue_codes:
        if issue_code not in seen_issue_codes:
            surfaced_issue_codes.append(issue_code)
    return [issue_code for issue_code in surfaced_issue_codes if issue_code]


def _chapter_surface_issue_diagnostics(
    chapter_report_payloads: Sequence[Dict[str, object]],
    *,
    target_chapters: int,
    diagnostic_scan_cache: Optional[_DiagnosticIssueScanCache] = None,
) -> List[Dict[str, object]]:
    diagnostics: List[Dict[str, object]] = []
    for payload in chapter_report_payloads:
        issue_codes = [
            issue_code
            for issue_code in _surface_issue_codes_for_payload(
                dict(payload),
                target_chapters=target_chapters,
                diagnostic_scan_cache=diagnostic_scan_cache,
            )
            if issue_code in {"Q03", "Q04", "Q05", "Q09"}
        ]
        if not issue_codes:
            continue
        lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
        repetition_bundle = dict(lint_metrics.get("repetition_signal_bundle") or {})
        chapter_id = str(payload.get("chapter_id") or "")
        suffix = chapter_id.rsplit("_", 1)[-1]
        chapter_index = int(suffix) if suffix.isdigit() else 0
        diagnostics.append(
            {
                "chapter_id": chapter_id,
                "chapter_index": chapter_index,
                "issue_codes": issue_codes,
                "decision": dict(payload.get("decision") or {}).get("decision"),
                "overall_score": float(dict(payload.get("scores") or {}).get("overall_score", 0.0) or 0.0),
                "lint_metrics": {
                    "repetition_score": float(lint_metrics.get("repetition_score", 0.0) or 0.0),
                    "exposition_ratio": float(lint_metrics.get("exposition_ratio", 0.0) or 0.0),
                    "dialogue_plus_action_ratio": float(lint_metrics.get("dialogue_plus_action_ratio", 0.0) or 0.0),
                    "concrete_detail_density": float(lint_metrics.get("concrete_detail_density", 0.0) or 0.0),
                    "text_unit_count": int(lint_metrics.get("text_unit_count", 0) or 0),
                    "paragraph_similarity_score": float(repetition_bundle.get("paragraph_similarity_score", 0.0) or 0.0),
                    "n_gram_repetition_score": float(repetition_bundle.get("n_gram_repetition_score", 0.0) or 0.0),
                    "semantic_paragraph_similarity_score": float(repetition_bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0),
                    "event_coverage_gap_score": float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0),
                    "beat_coverage_gap_score": float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0),
                    "uncovered_beat_count": int(repetition_bundle.get("uncovered_beat_count", 0) or 0),
                    "overcovered_beat_count": int(repetition_bundle.get("overcovered_beat_count", 0) or 0),
                },
            }
        )
    return diagnostics


def _chapter_index_from_id(chapter_id: object) -> int:
    suffix = str(chapter_id or "").rsplit("_", 1)[-1]
    return int(suffix) if suffix.isdigit() else 0


def _find_report_payload_for_target(
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]],
    *,
    world_id: str,
    chapter_index: int,
) -> Optional[Dict[str, object]]:
    for payload in chapter_reports_by_world.get(world_id, []):
        if _chapter_index_from_id(payload.get("chapter_id")) == int(chapter_index):
            return dict(payload)
    return None


def _matching_review_samples_for_target(
    review_samples: Sequence[Dict[str, object]],
    *,
    world_version_id: str,
    chapter_index: int,
) -> List[Dict[str, object]]:
    return [
        dict(sample)
        for sample in review_samples
        if str(sample.get("world_version_id") or "") == world_version_id
        and (
            _chapter_index_from_id(sample.get("chapter_id")) == int(chapter_index)
            or _chapter_index_from_id(dict(sample.get("source_ref") or {}).get("chapter_id")) == int(chapter_index)
        )
    ]


def _execute_review_sampling_plan_250(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_250: Sequence[Dict[str, object]],
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]],
) -> Dict[str, object]:
    existing_samples = training_signal.list_review_samples(limit=2000)
    materialized_count = 0
    already_present_count = 0
    missing_report_targets: List[Dict[str, object]] = []
    materialized_targets: List[Dict[str, object]] = []
    for target in review_sampling_plans_250:
        world_id = str(target.get("world_id") or "")
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        if _matching_review_samples_for_target(
            existing_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        ):
            already_present_count += 1
            materialized_targets.append(dict(target))
            continue
        report_payload = _find_report_payload_for_target(
            chapter_reports_by_world,
            world_id=world_id,
            chapter_index=chapter_index,
        )
        if not report_payload:
            missing_report_targets.append(dict(target))
            continue
        training_signal.save_review_sample_from_report(report_payload, world_id=world_id)
        materialized_count += 1
        materialized_targets.append(dict(target))
        existing_samples.append(
            {
                "chapter_id": report_payload.get("chapter_id"),
                "world_id": world_id,
                "world_version_id": world_version_id,
                "source": "evaluation_report_auto",
                "source_ref": {"kind": "evaluation_report", "chapter_id": report_payload.get("chapter_id")},
            }
        )
    return {
        "planned_target_count": len(list(review_sampling_plans_250)),
        "materialized_count": materialized_count,
        "already_present_count": already_present_count,
        "executed_target_count": materialized_count + already_present_count,
        "missing_report_target_count": len(missing_report_targets),
        "missing_report_targets": missing_report_targets,
        "materialized_targets": materialized_targets,
        "status": "closed" if not missing_report_targets else "partial",
    }


def _execute_review_sampling_plan_500(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_500: Sequence[Dict[str, object]],
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]],
) -> Dict[str, object]:
    existing_samples = training_signal.list_review_samples(limit=4000)
    materialized_count = 0
    already_present_count = 0
    missing_report_targets: List[Dict[str, object]] = []
    materialized_targets: List[Dict[str, object]] = []
    for target in review_sampling_plans_500:
        world_id = str(target.get("world_id") or "")
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        if _matching_review_samples_for_target(
            existing_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        ):
            already_present_count += 1
            materialized_targets.append(dict(target))
            continue
        report_payload = _find_report_payload_for_target(
            chapter_reports_by_world,
            world_id=world_id,
            chapter_index=chapter_index,
        )
        if not report_payload:
            missing_report_targets.append(dict(target))
            continue
        training_signal.save_review_sample_from_report(report_payload, world_id=world_id)
        materialized_count += 1
        materialized_targets.append(dict(target))
        existing_samples.append(
            {
                "chapter_id": report_payload.get("chapter_id"),
                "world_id": world_id,
                "world_version_id": world_version_id,
                "source": "evaluation_report_auto",
                "source_ref": {"kind": "evaluation_report", "chapter_id": report_payload.get("chapter_id")},
            }
        )
    return {
        "planned_target_count": len(list(review_sampling_plans_500)),
        "materialized_count": materialized_count,
        "already_present_count": already_present_count,
        "executed_target_count": materialized_count + already_present_count,
        "missing_report_target_count": len(missing_report_targets),
        "missing_report_targets": missing_report_targets,
        "materialized_targets": materialized_targets,
        "status": "closed" if not missing_report_targets else "partial",
    }


def _execute_human_review_closeout_plan_500(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_500: Sequence[Dict[str, object]],
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]],
    reviewer_id: str,
    target_chapters: int,
    diagnostic_scan_cache: Optional[_DiagnosticIssueScanCache] = None,
) -> Dict[str, object]:
    existing_human_samples = training_signal.list_review_samples(
        reviewer_id=reviewer_id,
        source="human_review",
        limit=4000,
    )
    materialized_count = 0
    already_present_count = 0
    missing_report_targets: List[Dict[str, object]] = []
    materialized_targets: List[Dict[str, object]] = []
    for target in review_sampling_plans_500:
        world_id = str(target.get("world_id") or "")
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        if _matching_review_samples_for_target(
            existing_human_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        ):
            already_present_count += 1
            materialized_targets.append(dict(target))
            continue
        report_payload = _find_report_payload_for_target(
            chapter_reports_by_world,
            world_id=world_id,
            chapter_index=chapter_index,
        )
        if not report_payload:
            missing_report_targets.append(dict(target))
            continue
        target_issue_codes = [
            str(issue_code)
            for issue_code in _surface_issue_codes_for_payload(
                dict(report_payload),
                target_chapters=target_chapters,
                diagnostic_scan_cache=diagnostic_scan_cache,
            )
            if str(issue_code)
        ]
        if not target_issue_codes:
            target_issue_codes = [str(issue_code) for issue_code in list(target.get("issue_focus") or []) if str(issue_code)]
        decision = str(dict(report_payload.get("decision") or {}).get("decision") or "pass")
        score_overall = float(dict(report_payload.get("scores") or {}).get("overall_score", 0.0) or 0.0)
        training_signal.save_review_sample(
            {
                "chapter_id": str(report_payload.get("chapter_id") or ""),
                "world_id": world_id,
                "world_version_id": world_version_id,
                "session_id": None,
                "reviewer_id": reviewer_id,
                "score_overall": score_overall,
                "issue_codes": target_issue_codes,
                "linked_issue_codes": target_issue_codes,
                "freeform_notes": str(report_payload.get("summary") or "longform_500 reviewer closeout target"),
                "would_continue": decision in {"pass", "rewrite"},
                "would_pay": decision == "pass",
                "source": "human_review",
                "source_ref": {"kind": "manual_entry", "chapter_id": str(report_payload.get("chapter_id") or "")},
            }
        )
        materialized_count += 1
        materialized_targets.append(dict(target))
        existing_human_samples.append(
            {
                "chapter_id": report_payload.get("chapter_id"),
                "world_id": world_id,
                "world_version_id": world_version_id,
                "source": "human_review",
                "source_ref": {"kind": "manual_entry", "chapter_id": report_payload.get("chapter_id")},
            }
        )
    return {
        "planned_target_count": len(list(review_sampling_plans_500)),
        "materialized_count": materialized_count,
        "already_present_count": already_present_count,
        "executed_target_count": materialized_count + already_present_count,
        "missing_report_target_count": len(missing_report_targets),
        "missing_report_targets": missing_report_targets,
        "materialized_targets": materialized_targets,
        "reviewer_id": reviewer_id,
        "status": "closed" if not missing_report_targets else "partial",
    }


def _build_review_sample_coverage_250(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_250: Sequence[Dict[str, object]],
    execution_summary: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    review_samples = training_signal.list_review_samples(limit=2000)
    reviewed_targets: List[Dict[str, object]] = []
    human_reviewed_targets: List[Dict[str, object]] = []
    auto_seeded_targets: List[Dict[str, object]] = []
    unreviewed_targets: List[Dict[str, object]] = []
    human_unreviewed_targets: List[Dict[str, object]] = []
    window_coverage: Dict[str, Dict[str, int]] = {}
    linked_issue_codes: List[str] = []
    human_linked_issue_codes: List[str] = []
    for target in review_sampling_plans_250:
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        window_label = str(target.get("window_label") or "")
        matching = _matching_review_samples_for_target(
            review_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        )
        human_matching = [sample for sample in matching if str(sample.get("source") or "") == "human_review"]
        auto_matching = [sample for sample in matching if str(sample.get("source") or "") == "evaluation_report_auto"]
        coverage_bucket = window_coverage.setdefault(
            window_label,
            {
                "target_count": 0,
                "reviewed_count": 0,
                "human_reviewed_count": 0,
                "auto_seeded_count": 0,
            },
        )
        coverage_bucket["target_count"] += 1
        if matching:
            coverage_bucket["reviewed_count"] += 1
            reviewed_targets.append(dict(target))
            for sample in matching:
                linked_issue_codes.extend(list(sample.get("linked_issue_codes") or sample.get("issue_codes") or []))
        else:
            unreviewed_targets.append(dict(target))
        if human_matching:
            coverage_bucket["human_reviewed_count"] += 1
            human_reviewed_targets.append(dict(target))
            for sample in human_matching:
                human_linked_issue_codes.extend(list(sample.get("linked_issue_codes") or sample.get("issue_codes") or []))
        else:
            human_unreviewed_targets.append(dict(target))
        if auto_matching:
            coverage_bucket["auto_seeded_count"] += 1
            auto_seeded_targets.append(dict(target))
    dominant_issue_mix: Dict[str, int] = {}
    for issue_code in linked_issue_codes:
        dominant_issue_mix[str(issue_code)] = dominant_issue_mix.get(str(issue_code), 0) + 1
    human_dominant_issue_mix: Dict[str, int] = {}
    for issue_code in human_linked_issue_codes:
        human_dominant_issue_mix[str(issue_code)] = human_dominant_issue_mix.get(str(issue_code), 0) + 1
    planned_target_count = len(list(review_sampling_plans_250))
    executed_target_count = len(reviewed_targets)
    closeout_ready = executed_target_count >= planned_target_count if planned_target_count else False
    human_closeout_ready = len(human_reviewed_targets) >= planned_target_count if planned_target_count else False
    closeout_status = (
        "closed"
        if closeout_ready and len(human_reviewed_targets) == planned_target_count
        else ("closed_with_auto_seed" if closeout_ready else "watch")
    )
    human_closeout_status = (
        "closed"
        if human_closeout_ready
        else ("partial" if human_reviewed_targets else "watch")
    )
    return {
        "window_labels": [label for label, _start, _end in LONGFORM_250_REVIEW_WINDOWS],
        "planned_target_count": planned_target_count,
        "executed_target_count": executed_target_count,
        "human_reviewed_target_count": len(human_reviewed_targets),
        "auto_seeded_target_count": len(auto_seeded_targets),
        "reviewed_world_count": len({str(item.get("world_id") or "") for item in reviewed_targets}),
        "human_reviewed_world_count": len({str(item.get("world_id") or "") for item in human_reviewed_targets}),
        "auto_seeded_world_count": len({str(item.get("world_id") or "") for item in auto_seeded_targets}),
        "closeout_ready": closeout_ready,
        "closeout_status": closeout_status,
        "human_closeout_ready": human_closeout_ready,
        "human_closeout_status": human_closeout_status,
        "window_coverage": window_coverage,
        "unreviewed_targets": unreviewed_targets,
        "human_unreviewed_targets": human_unreviewed_targets,
        "dominant_issue_mix": [
            {"issue_code": issue_code, "count": count}
            for issue_code, count in sorted(dominant_issue_mix.items(), key=lambda item: (-item[1], item[0]))
        ],
        "human_dominant_issue_mix": [
            {"issue_code": issue_code, "count": count}
            for issue_code, count in sorted(human_dominant_issue_mix.items(), key=lambda item: (-item[1], item[0]))
        ],
        "sampling_plan": list(review_sampling_plans_250),
        "execution_summary": dict(execution_summary or {}),
    }


LONGFORM_500_REVIEW_WINDOWS = (
    ("1-40", 1, 40),
    ("220-300", 220, 300),
    ("460-500", 460, 500),
)
LONGFORM_1000_REVIEW_WINDOWS = (
    ("1-80", 1, 80),
    ("420-580", 420, 580),
    ("920-1000", 920, 1000),
)


def _review_sampling_plan_500(report: Dict[str, object], *, world_id: str, world_version_id: str) -> List[Dict[str, object]]:
    chapter_ids = [str(item.get("chapter_id") or "") for item in report.get("chapter_evaluations", [])]
    available_indices = [int(chapter_id.rsplit("_", 1)[-1]) for chapter_id in chapter_ids if chapter_id.rsplit("_", 1)[-1].isdigit()]
    max_index = max(available_indices or [0])
    top_issue_categories = list((report.get("evaluation_summary") or {}).get("top_issue_categories", []))
    issue_focus = [str(item.get("issue_code") or "") for item in top_issue_categories[:2] if str(item.get("issue_code") or "")]
    plan: List[Dict[str, object]] = []
    for window_label, start, end in LONGFORM_500_REVIEW_WINDOWS:
        candidates = [index for index in available_indices if start <= index <= end]
        if not candidates:
            continue
        picks = [candidates[0]]
        if len(candidates) > 1:
            picks.append(candidates[min(len(candidates) - 1, len(candidates) // 2)])
        seen = set()
        for priority, chapter_index in enumerate(picks, start=1):
            if chapter_index in seen:
                continue
            seen.add(chapter_index)
            plan.append(
                {
                    "world_id": world_id,
                    "world_version_id": world_version_id,
                    "window_label": window_label,
                    "chapter_index": chapter_index,
                    "issue_focus": issue_focus or ["Q03", "Q05", "Q09"],
                    "priority": priority,
                    "reason": f"longform_500_window_{window_label}",
                    "available_chapter_max": max_index,
                }
            )
    return plan


def _review_sampling_plan_1000(report: Dict[str, object], *, world_id: str, world_version_id: str) -> List[Dict[str, object]]:
    chapter_ids = [str(item.get("chapter_id") or "") for item in report.get("chapter_evaluations", [])]
    available_indices = [int(chapter_id.rsplit("_", 1)[-1]) for chapter_id in chapter_ids if chapter_id.rsplit("_", 1)[-1].isdigit()]
    max_index = max(available_indices or [0])
    top_issue_categories = list((report.get("evaluation_summary") or {}).get("top_issue_categories", []))
    issue_focus = [str(item.get("issue_code") or "") for item in top_issue_categories[:2] if str(item.get("issue_code") or "")]
    plan: List[Dict[str, object]] = []
    for window_label, start, end in LONGFORM_1000_REVIEW_WINDOWS:
        candidates = [index for index in available_indices if start <= index <= end]
        if not candidates:
            continue
        picks = [candidates[0]]
        if len(candidates) > 1:
            picks.append(candidates[min(len(candidates) - 1, len(candidates) // 2)])
        seen = set()
        for priority, chapter_index in enumerate(picks, start=1):
            if chapter_index in seen:
                continue
            seen.add(chapter_index)
            plan.append(
                {
                    "world_id": world_id,
                    "world_version_id": world_version_id,
                    "window_label": window_label,
                    "chapter_index": chapter_index,
                    "issue_focus": issue_focus or ["Q03", "Q05", "Q06", "Q09"],
                    "priority": priority,
                    "reason": f"longform_1000_window_{window_label}",
                    "available_chapter_max": max_index,
                }
            )
    return plan


def _build_review_sample_coverage_500(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_500: Sequence[Dict[str, object]],
    execution_summary: Optional[Dict[str, object]] = None,
    human_execution_summary: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    review_samples = training_signal.list_review_samples(limit=4000)
    reviewed_targets: List[Dict[str, object]] = []
    human_reviewed_targets: List[Dict[str, object]] = []
    auto_seeded_targets: List[Dict[str, object]] = []
    unreviewed_targets: List[Dict[str, object]] = []
    human_unreviewed_targets: List[Dict[str, object]] = []
    window_coverage: Dict[str, Dict[str, int]] = {}
    ending_window_label = LONGFORM_500_REVIEW_WINDOWS[-1][0]
    ending_window_target_count = 0
    ending_window_human_reviewed_count = 0
    for target in review_sampling_plans_500:
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        window_label = str(target.get("window_label") or "")
        matching = _matching_review_samples_for_target(
            review_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        )
        human_matching = [sample for sample in matching if str(sample.get("source") or "") == "human_review"]
        auto_matching = [sample for sample in matching if str(sample.get("source") or "") == "evaluation_report_auto"]
        bucket = window_coverage.setdefault(
            window_label,
            {
                "target_count": 0,
                "reviewed_count": 0,
                "human_reviewed_count": 0,
                "auto_seeded_count": 0,
            },
        )
        bucket["target_count"] += 1
        if window_label == ending_window_label:
            ending_window_target_count += 1
        if matching:
            bucket["reviewed_count"] += 1
            reviewed_targets.append(dict(target))
        else:
            unreviewed_targets.append(dict(target))
        if human_matching:
            bucket["human_reviewed_count"] += 1
            human_reviewed_targets.append(dict(target))
            if window_label == ending_window_label:
                ending_window_human_reviewed_count += 1
        else:
            human_unreviewed_targets.append(dict(target))
        if auto_matching:
            bucket["auto_seeded_count"] += 1
            auto_seeded_targets.append(dict(target))
    planned_target_count = len(list(review_sampling_plans_500))
    executed_target_count = len(reviewed_targets)
    closeout_ready = executed_target_count >= planned_target_count if planned_target_count else False
    human_closeout_ready = len(human_reviewed_targets) >= planned_target_count if planned_target_count else False
    ending_window_human_closeout_ready = (
        ending_window_target_count > 0 and ending_window_human_reviewed_count >= ending_window_target_count
    )
    return {
        "window_labels": [label for label, _start, _end in LONGFORM_500_REVIEW_WINDOWS],
        "planned_target_count": planned_target_count,
        "executed_target_count": executed_target_count,
        "human_reviewed_target_count": len(human_reviewed_targets),
        "auto_seeded_target_count": len(auto_seeded_targets),
        "reviewed_world_count": len({str(item.get("world_id") or "") for item in reviewed_targets}),
        "human_reviewed_world_count": len({str(item.get("world_id") or "") for item in human_reviewed_targets}),
        "auto_seeded_world_count": len({str(item.get("world_id") or "") for item in auto_seeded_targets}),
        "closeout_ready": closeout_ready,
        "closeout_status": ("closed" if human_closeout_ready else ("closed_with_auto_seed" if closeout_ready else "watch")),
        "human_closeout_ready": human_closeout_ready,
        "human_closeout_status": "closed" if human_closeout_ready else ("partial" if human_reviewed_targets else "watch"),
        "ending_window_label": ending_window_label,
        "ending_window_target_count": ending_window_target_count,
        "ending_window_human_reviewed_count": ending_window_human_reviewed_count,
        "ending_window_human_closeout_ready": ending_window_human_closeout_ready,
        "window_coverage": window_coverage,
        "unreviewed_targets": unreviewed_targets,
        "human_unreviewed_targets": human_unreviewed_targets,
        "sampling_plan": list(review_sampling_plans_500),
        "execution_summary": dict(execution_summary or {}),
        "human_execution_summary": dict(human_execution_summary or {}),
    }


def _build_review_sample_coverage_1000(
    *,
    training_signal: TrainingSignalService,
    review_sampling_plans_1000: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    review_samples = training_signal.list_review_samples(limit=6000)
    reviewed_targets: List[Dict[str, object]] = []
    human_reviewed_targets: List[Dict[str, object]] = []
    auto_seeded_targets: List[Dict[str, object]] = []
    unreviewed_targets: List[Dict[str, object]] = []
    human_unreviewed_targets: List[Dict[str, object]] = []
    window_coverage: Dict[str, Dict[str, int]] = {}
    for target in review_sampling_plans_1000:
        world_version_id = str(target.get("world_version_id") or "")
        chapter_index = int(target.get("chapter_index", 0) or 0)
        window_label = str(target.get("window_label") or "")
        matching = _matching_review_samples_for_target(
            review_samples,
            world_version_id=world_version_id,
            chapter_index=chapter_index,
        )
        human_matching = [sample for sample in matching if str(sample.get("source") or "") == "human_review"]
        auto_matching = [sample for sample in matching if str(sample.get("source") or "") == "evaluation_report_auto"]
        bucket = window_coverage.setdefault(
            window_label,
            {
                "target_count": 0,
                "reviewed_count": 0,
                "human_reviewed_count": 0,
                "auto_seeded_count": 0,
            },
        )
        bucket["target_count"] += 1
        if matching:
            bucket["reviewed_count"] += 1
            reviewed_targets.append(dict(target))
        else:
            unreviewed_targets.append(dict(target))
        if human_matching:
            bucket["human_reviewed_count"] += 1
            human_reviewed_targets.append(dict(target))
        else:
            human_unreviewed_targets.append(dict(target))
        if auto_matching:
            bucket["auto_seeded_count"] += 1
            auto_seeded_targets.append(dict(target))
    planned_target_count = len(list(review_sampling_plans_1000))
    human_closeout_ready = len(human_reviewed_targets) >= planned_target_count if planned_target_count else False
    human_closeout_status = "closed" if human_closeout_ready else ("partial" if human_reviewed_targets else "watch")
    return {
        "window_labels": [label for label, _start, _end in LONGFORM_1000_REVIEW_WINDOWS],
        "planned_target_count": planned_target_count,
        "executed_target_count": len(reviewed_targets),
        "human_reviewed_target_count": len(human_reviewed_targets),
        "auto_seeded_target_count": len(auto_seeded_targets),
        "reviewed_world_count": len({str(item.get("world_id") or "") for item in reviewed_targets}),
        "human_reviewed_world_count": len({str(item.get("world_id") or "") for item in human_reviewed_targets}),
        "auto_seeded_world_count": len({str(item.get("world_id") or "") for item in auto_seeded_targets}),
        "human_closeout_ready": human_closeout_ready,
        "human_closeout_status": human_closeout_status,
        "window_coverage": window_coverage,
        "unreviewed_targets": unreviewed_targets,
        "human_unreviewed_targets": human_unreviewed_targets,
        "sampling_plan": list(review_sampling_plans_1000),
    }


def _resolve_world_ids(worldpack: str | Sequence[str]) -> List[str]:
    if isinstance(worldpack, str):
        if worldpack == "all":
            return [item["world_id"] for item in FileSystemWorldRegistry().list_benchmark_worldpacks()]
        return _split_world_id_tokens(worldpack)
    return _split_world_id_tokens(worldpack)


def run_benchmark(
    *,
    repository: SQLAlchemyRepository,
    golden_dir: Path,
    worldpack: str | Sequence[str] = "all",
    baseline: Dict[str, object] | None = None,
    world_version_overrides: Dict[str, str] | None = None,
    simulation_runner: Callable[[str, str], Dict[str, object]] | None = None,
    benchmark_mode: Optional[str] = None,
    max_chapters: int = 6,
    min_end_turn_override: int | None = None,
    execute_review_sampling_250: bool = False,
    execute_review_sampling_500: bool = False,
    execute_human_review_closeout_500: bool = False,
    human_review_closeout_500_reviewer_id: str = "ops_longform500_reviewer_after_residual_fix",
    interactive_profile: Optional[str] = None,
    validate_strategy_bundle: bool = False,
    strategy_bundle_id: Optional[str] = None,
    weakest_limit: int = 3,
    acceptance_profile: str = "full",
    changed_worldpacks: Sequence[str] | None = None,
    fast_gate_weakest_limit: int = 3,
    progress_out: Optional[Path] = None,
    checkpoint_out: Optional[Path] = None,
) -> Dict[str, object]:
    benchmark_started = perf_counter()
    registry = FileSystemWorldRegistry()
    training_signal = TrainingSignalService(repository)
    acceptance_profile = str(acceptance_profile or "full").strip() or "full"
    if acceptance_profile not in {"full", "nightly", "fast"}:
        acceptance_profile = "full"
    resolved_benchmark_mode = benchmark_mode or ("long_route" if max_chapters > 6 else "standard")
    if resolved_benchmark_mode == "longform_100" and max_chapters < 100:
        max_chapters = 100
    if resolved_benchmark_mode == "longform_100_interactive" and max_chapters < 100:
        max_chapters = 100
    if resolved_benchmark_mode == "longform_250" and max_chapters < 250:
        max_chapters = 250
    if resolved_benchmark_mode == "longform_250_interactive" and max_chapters < 250:
        max_chapters = 250
    if resolved_benchmark_mode == "longform_500" and max_chapters < 500:
        max_chapters = 500
    if resolved_benchmark_mode == "longform_500_interactive" and max_chapters < 500:
        max_chapters = 500
    if resolved_benchmark_mode == "longform_1000_interactive" and max_chapters < 1000:
        max_chapters = 1000
    if resolved_benchmark_mode == "longform_1000_diagnostics" and max_chapters < 1000:
        max_chapters = 1000
    world_version_overrides = world_version_overrides or {}
    authoring = None
    if simulation_runner is None:
        from ..services.authoring import AuthoringService

        authoring = AuthoringService(repository, registry=registry)
    worlds = []
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]] = {}
    pack_payload_by_world: Dict[str, Dict[str, object]] = {}
    baseline_reports_by_world: Dict[str, Dict[str, object]] = {}
    review_sampling_plans_250: List[Dict[str, object]] = []
    review_sampling_plans_500: List[Dict[str, object]] = []
    review_sampling_plans_1000: List[Dict[str, object]] = []
    requested_world_ids = _resolve_world_ids(worldpack)
    fast_gate = _resolve_acceptance_world_ids(
        requested_world_ids,
        baseline=baseline,
        acceptance_profile=acceptance_profile,
        changed_worldpacks=changed_worldpacks or [],
        fast_gate_weakest_limit=fast_gate_weakest_limit,
    )
    selected_world_ids = list(fast_gate.get("selected_world_ids") or requested_world_ids)
    progress = _BenchmarkProgressWriter(progress_out)
    diagnostic_scan_cache = _DiagnosticIssueScanCache()
    progress.emit(
        "benchmark_start",
        benchmark_mode=resolved_benchmark_mode,
        chapter_budget=max_chapters,
        requested_world_count=len(requested_world_ids),
        selected_world_count=len(selected_world_ids),
        progress_out=str(progress_out) if progress_out else "",
        checkpoint_out=str(checkpoint_out) if checkpoint_out else "",
    )
    for world_id in selected_world_ids:
        world_started = perf_counter()
        world_stage_timings: Dict[str, float] = {}
        progress.emit(
            "world_start",
            world_id=world_id,
            world_index=len(worlds) + 1,
            world_count=len(selected_world_ids),
        )
        metrics_started = perf_counter()
        override_world_version_id = world_version_overrides.get(world_id)
        if override_world_version_id:
            world_version_id = override_world_version_id
        else:
            world_card = registry.get_published_world(world_id)
            world_version_id = world_card["world_version_id"]
        runtime = repository.get_runtime_bundle(world_version_id)
        pack_payload = runtime.worldpack.to_dict()
        pack_payload_by_world[world_id] = pack_payload
        style_pack = dict(pack_payload.get("narrative_style_pack", {}))
        dialogue = dict(style_pack.get("dialogue", {}))
        voice_profiles = dict(pack_payload.get("voice_profiles") or dialogue.get("voice_profiles", {}))
        action_policies = dict(pack_payload.get("emotion_action_policies", {}))
        default_action_policy = next(iter(action_policies.values()), style_pack.get("emotion_actions", {}))
        action_map = dict(default_action_policy.get("action_map", {}))
        interactive_scenarios = _resolve_interactive_scenarios(
            pack_payload=pack_payload,
            target_chapters=max_chapters,
            benchmark_mode=resolved_benchmark_mode,
            interactive_profile=interactive_profile,
        )
        world_stage_timings["metrics_setup"] = _elapsed_ms(metrics_started)
        progress.emit_stage(
            world_id=world_id,
            stage="metrics_setup",
            elapsed_ms=world_stage_timings["metrics_setup"],
            world_version_id=world_version_id,
        )
        def simulation_progress(event: str, **fields: object) -> None:
            progress.emit(
                f"simulation_{event}",
                world_id=world_id,
                world_version_id=world_version_id,
                **fields,
            )

        simulation_started = perf_counter()
        if simulation_runner is None:
            if interactive_scenarios:
                report = authoring.run_simulation_for_world_version(
                    world_version_id,
                    include_cross_pack=False,
                    max_chapters=max_chapters,
                    min_end_turn_override=min_end_turn_override,
                    interactive_scenarios=interactive_scenarios,
                    progress_callback=simulation_progress,
                )
            else:
                report = authoring.run_simulation_for_world_version(
                    world_version_id,
                    include_cross_pack=False,
                    max_chapters=max_chapters,
                    min_end_turn_override=min_end_turn_override,
                    progress_callback=simulation_progress,
                )
        else:
            if interactive_scenarios:
                parameters = inspect.signature(simulation_runner).parameters
                if len(parameters) >= 3:
                    report = simulation_runner(world_id, world_version_id, interactive_scenarios)
                else:
                    report = simulation_runner(world_id, world_version_id)
            else:
                report = simulation_runner(world_id, world_version_id)
        world_stage_timings["simulation"] = _elapsed_ms(simulation_started)
        progress.emit_stage(
            world_id=world_id,
            stage="simulation",
            elapsed_ms=world_stage_timings["simulation"],
            completed_chapters=int(report.get("completed_chapters", 0) or 0),
            stop_reason=str(report.get("stop_reason", "")),
        )
        baseline_reports_by_world[world_id] = copy.deepcopy(report)
        longform_summary = dict(report.get("longform_summary", {}))
        longform_gate = dict(report.get("longform_gate") or {})
        interactive_summary = dict(report.get("interactive_summary") or {})
        report_conversion_started = perf_counter()
        chapter_reports = [EvaluationReport.from_dict(item) for item in report.get("chapter_evaluations", [])]
        chapter_reports_by_world[world_id] = [item.to_dict() for item in chapter_reports]
        world_stage_timings["report_conversion"] = _elapsed_ms(report_conversion_started)
        progress.emit_stage(
            world_id=world_id,
            stage="report_conversion",
            elapsed_ms=world_stage_timings["report_conversion"],
            chapter_report_count=len(chapter_reports_by_world[world_id]),
        )
        evaluation = report.get("evaluation_summary", {})
        issue_mix_started = perf_counter()
        issue_mix = build_issue_mix(
            _chapter_surface_issue_payloads(
                chapter_reports_by_world[world_id],
                target_chapters=max_chapters,
                diagnostic_scan_cache=diagnostic_scan_cache,
            )
        )
        world_stage_timings["issue_mix"] = _elapsed_ms(issue_mix_started)
        progress.emit_stage(
            world_id=world_id,
            stage="issue_mix",
            elapsed_ms=world_stage_timings["issue_mix"],
            issue_category_count=len(issue_mix),
            diagnostic_scan_hits=diagnostic_scan_cache.hits,
            diagnostic_scan_misses=diagnostic_scan_cache.misses,
        )
        q09_incidence_rate = round(
            sum(1 for payload in chapter_reports_by_world[world_id] if any(issue.get("issue_code") == "Q09" for issue in payload.get("issues", [])))
            / float(max(1, len(chapter_reports_by_world[world_id]) or 1)),
            3,
        )
        route_diagnostics_started = perf_counter()
        route_diagnostics = build_route_diagnostics(
            [float(item.scores.overall_score) for item in chapter_reports],
            completed_chapters=int(report.get("completed_chapters", 0)),
            target_chapters=max_chapters,
        )
        long_route_diagnostics = build_long_route_diagnostics(
            chapter_report_payloads=chapter_reports_by_world[world_id],
            completed_chapters=int(report.get("completed_chapters", 0)),
            target_chapters=max_chapters,
            min_end_turn_target=int(report.get("min_end_turn_target", min_end_turn_override or 6)),
            stop_reason=str(report.get("stop_reason", "chapter_budget_reached")),
        )
        world_stage_timings["route_diagnostics"] = _elapsed_ms(route_diagnostics_started)
        progress.emit_stage(
            world_id=world_id,
            stage="route_diagnostics",
            elapsed_ms=world_stage_timings["route_diagnostics"],
        )
        metrics_aggregation_started = perf_counter()
        if chapter_reports:
            character_fidelity = sum(item.scores.character_fidelity for item in chapter_reports) / len(chapter_reports)
            causal_continuity = sum(item.scores.causal_continuity for item in chapter_reports) / len(chapter_reports)
            choice_distinctness = sum(item.scores.choice_distinctness for item in chapter_reports) / len(chapter_reports)
            prose_leak_rate = sum(item.hard_validator_results.get("lint_metrics", {}).get("engineering_leak_rate", 0.0) for item in chapter_reports) / len(chapter_reports)
            dialogue_ratio = sum(item.hard_validator_results.get("lint_metrics", {}).get("dialogue_plus_action_ratio", 0.0) for item in chapter_reports) / len(chapter_reports)
            scene_detail_density = sum(item.hard_validator_results.get("lint_metrics", {}).get("concrete_detail_density", 0.0) for item in chapter_reports) / len(chapter_reports)
        else:
            character_fidelity = causal_continuity = choice_distinctness = prose_leak_rate = dialogue_ratio = scene_detail_density = 0.0
        if voice_profiles:
            bluntness_values = [float(profile.get("bluntness", 0.5)) for profile in voice_profiles.values()]
            restraint_values = [float(profile.get("restraint", 0.5)) for profile in voice_profiles.values()]
            voice_separation_score = min(1.0, ((max(bluntness_values) - min(bluntness_values)) + (max(restraint_values) - min(restraint_values))) / 2.0)
        else:
            voice_separation_score = 0.0
        if action_map:
            action_buckets = [len(slot_map.get("entry", []) + slot_map.get("pressure", []) + slot_map.get("pivot", []) + slot_map.get("aftermath", []) + slot_map.get("echo", [])) for slot_map in action_map.values()]
            emotion_action_specificity = min(1.0, sum(action_buckets) / float(max(1, len(action_buckets) * 8)))
        else:
            emotion_action_specificity = 0.0
        trace_runtime_profile = _runtime_profile_from_chapter_trace(list(report.get("chapter_trace") or []))
        world_stage_timings["generation_runtime"] = float(trace_runtime_profile.get("generation_runtime_ms", 0.0) or 0.0)
        world_stage_timings["quality_pass"] = float(trace_runtime_profile.get("quality_pass_ms", 0.0) or 0.0)
        world_stage_timings["lint"] = float(trace_runtime_profile.get("lint_ms", 0.0) or 0.0)
        world_stage_timings["evaluation"] = float(trace_runtime_profile.get("evaluation_ms", 0.0) or 0.0)
        world_stage_timings["metrics_aggregation"] = _elapsed_ms(metrics_aggregation_started)
        progress.emit_stage(
            world_id=world_id,
            stage="metrics_aggregation",
            elapsed_ms=world_stage_timings["metrics_aggregation"],
        )
        world_metrics = {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "pass_rate": evaluation.get("pass_rate", 0.0),
            "rewrite_rate": evaluation.get("rewrite_rate", 0.0),
            "block_rate": evaluation.get("block_rate", 0.0),
            "character_fidelity": round(character_fidelity, 3),
            "causal_continuity": round(causal_continuity, 3),
            "choice_distinctness": round(choice_distinctness, 3),
            "prose_leak_rate": round(prose_leak_rate, 3),
            "route_longevity": report.get("completed_chapters", 0),
            "route_longevity_target": max_chapters,
            "dialogue_ratio": round(dialogue_ratio, 3),
            "scene_detail_density": round(scene_detail_density, 3),
            "voice_separation_score": round(voice_separation_score, 3),
            "emotion_action_specificity": round(emotion_action_specificity, 3),
            "cross_pack_pass_rate": evaluation.get("pass_rate", 0.0),
            "issue_mix": issue_mix,
            "surface_issue_chapters": _chapter_surface_issue_diagnostics(
                chapter_reports_by_world[world_id],
                target_chapters=max_chapters,
                diagnostic_scan_cache=diagnostic_scan_cache,
            ),
            "long_route_quality": route_diagnostics["long_route_quality"],
            "mid_arc_drop": route_diagnostics["mid_arc_drop"],
            "dialogue_distinctness": round(voice_separation_score, 3),
            "character_drift_rate": float(longform_summary.get("character_drift_rate", 0.0) or 0.0),
            "promise_unresolved_rate": float(longform_summary.get("promise_unresolved_rate", 0.0) or 0.0),
            "arc_task_repeat_rate": float(longform_summary.get("arc_task_repeat_rate", 0.0) or 0.0),
            "q09_incidence_rate": float(longform_summary.get("q09_incidence_rate", q09_incidence_rate) or q09_incidence_rate),
            "premature_ending_trigger_rate": float(longform_summary.get("premature_ending_trigger_rate", 0.0) or 0.0),
            "volume_climax_spacing_error": float(longform_summary.get("volume_climax_spacing_error", 0.0) or 0.0),
            **long_route_diagnostics,
        }
        world_metrics["generation_hard_constraint_summary"] = summarize_generation_hard_constraints(
            chapter_reports_by_world[world_id],
            chapter_trace_payloads=list(report.get("chapter_trace") or []),
        )
        world_metrics["runtime_profile"] = {
            "schema_version": "benchmark_world_runtime_profile/v1",
            "world_id": world_id,
            "chapter_count": int(trace_runtime_profile.get("chapter_count", 0) or len(chapter_reports)),
            "stages_ms": {key: round(float(value or 0.0), 3) for key, value in sorted(world_stage_timings.items())},
            "render_timing_ms": dict(trace_runtime_profile.get("render_timing_ms") or {}),
            "quality_pass_action_count": int(trace_runtime_profile.get("quality_pass_action_count", 0) or 0),
            "quality_pass_stage_action_counts": dict(trace_runtime_profile.get("quality_pass_stage_action_counts") or {}),
            "quality_pass_stage_estimated_ms": dict(trace_runtime_profile.get("quality_pass_stage_estimated_ms") or {}),
            "quality_pass_stage_estimated": bool(trace_runtime_profile.get("quality_pass_stage_estimated", False)),
            "diagnostic_issue_scan_cache": diagnostic_scan_cache.summary(),
        }
        continuation_metrics = repository.aggregate_eval_metrics(world_version_id=world_version_id)
        world_metrics["continuation_calibration"] = dict(continuation_metrics.get("q03_q09_calibration") or {})
        if interactive_scenarios:
            world_metrics["interactive_summary"] = dict(interactive_summary)
            world_metrics["post_steer_issue_window_summary"] = list(report.get("post_steer_issue_window_summary") or [])
            world_metrics["interactive_profile"] = interactive_profile or "default"
        if resolved_benchmark_mode == "longform_100":
            if not longform_gate:
                longform_gate = evaluate_longform_gate(
                    target_chapters=int(longform_summary.get("target_chapters", max_chapters) or max_chapters),
                    completed_chapters=int(report.get("completed_chapters", 0)),
                    pass_rate=float(evaluation.get("pass_rate", 0.0) or 0.0),
                    block_rate=float(evaluation.get("block_rate", 0.0) or 0.0),
                    stop_reason=str(report.get("stop_reason", "")),
                    completion_ratio=float(report.get("completion_ratio", long_route_diagnostics.get("completion_ratio", 0.0)) or 0.0),
                    mid_arc_pass_rate=float(long_route_diagnostics.get("mid_arc_pass_rate", 0.0) or 0.0),
                    q09_incidence_rate=float(world_metrics.get("q09_incidence_rate", 0.0) or 0.0),
                    character_drift_rate=float(longform_summary.get("character_drift_rate", 0.0) or 0.0),
                    promise_unresolved_rate=float(longform_summary.get("promise_unresolved_rate", 0.0) or 0.0),
                    arc_task_repeat_rate=float(longform_summary.get("arc_task_repeat_rate", 0.0) or 0.0),
                    premature_ending_trigger_rate=float(longform_summary.get("premature_ending_trigger_rate", 0.0) or 0.0),
                    volume_climax_spacing_error=float(longform_summary.get("volume_climax_spacing_error", 0.0) or 0.0),
                )
            world_metrics["longform_gate"] = dict(longform_gate)
        if resolved_benchmark_mode == "longform_100_interactive":
            steering_recovery_rate = float(interactive_summary.get("steering_recovery_rate", 0.0) or 0.0)
            post_steer_route_survival = float(interactive_summary.get("post_steer_route_survival", 0.0) or 0.0)
            memory_consistency_after_steer = float(interactive_summary.get("memory_consistency_after_steer", 0.0) or 0.0)
            promise_reconciliation_after_steer = float(interactive_summary.get("promise_reconciliation_after_steer", 0.0) or 0.0)
            replan_stability_score = float(interactive_summary.get("replan_stability_score", 0.0) or 0.0)
            interactive_gate_checks = {
                "steering_recovery_rate": steering_recovery_rate >= float(INTERACTIVE_LONGFORM_THRESHOLDS["steering_recovery_rate_min"]),
                "post_steer_route_survival": post_steer_route_survival >= float(INTERACTIVE_LONGFORM_THRESHOLDS["post_steer_route_survival_min"]),
                "memory_consistency_after_steer": memory_consistency_after_steer >= float(INTERACTIVE_LONGFORM_THRESHOLDS["memory_consistency_after_steer_min"]),
                "promise_reconciliation_after_steer": promise_reconciliation_after_steer >= float(INTERACTIVE_LONGFORM_THRESHOLDS["promise_reconciliation_after_steer_min"]),
                "replan_stability_score": replan_stability_score >= float(INTERACTIVE_LONGFORM_THRESHOLDS["replan_stability_score_min"]),
            }
            world_metrics["interactive_summary"] = dict(interactive_summary)
            world_metrics["interactive_longform_gate"] = {
                "passed": bool(longform_gate.get("passed")) and all(interactive_gate_checks.values()),
                "failed_checks": [name for name, passed in interactive_gate_checks.items() if not passed] + ([] if longform_gate.get("passed") else ["longform_gate"]),
                "checks": interactive_gate_checks,
            }
        if resolved_benchmark_mode in {"longform_250", "longform_250_interactive"}:
            longform_250_summary = dict(report.get("longform_250_summary") or {})
            failed_checks = list(dict(report.get("longform_250_evidence") or {}).get("failed_checks", []))
            world_metrics["longform_250_summary"] = longform_250_summary
            world_metrics["longform_250_gate"] = {
                "passed": not failed_checks,
                "failed_checks": failed_checks,
            }
            world_metrics["review_sampling_plan_250"] = _review_sampling_plan_250(report, world_id=world_id, world_version_id=world_version_id)
            review_sampling_plans_250.extend(list(world_metrics["review_sampling_plan_250"]))
        if resolved_benchmark_mode in {"longform_500", "longform_500_interactive"}:
            longform_500_summary = dict(report.get("longform_500_summary") or {})
            failed_checks = list(dict(report.get("longform_500_evidence") or {}).get("failed_checks", []))
            world_metrics["longform_500_summary"] = longform_500_summary
            world_metrics["longform_500_gate"] = {
                "passed": not failed_checks,
                "failed_checks": failed_checks,
            }
            world_metrics["review_sampling_plan_500"] = _review_sampling_plan_500(report, world_id=world_id, world_version_id=world_version_id)
            review_sampling_plans_500.extend(list(world_metrics["review_sampling_plan_500"]))
        if resolved_benchmark_mode in {"longform_1000_diagnostics", "longform_1000_interactive"}:
            longform_1000_summary = dict(report.get("longform_1000_summary") or {})
            failed_checks = list(dict(report.get("longform_1000_evidence") or {}).get("failed_checks", []))
            world_metrics["longform_1000_summary"] = longform_1000_summary
            world_metrics["longform_1000_feasibility"] = {
                "passed": not failed_checks,
                "failed_checks": failed_checks,
            }
            world_metrics["review_sampling_plan_1000"] = _review_sampling_plan_1000(
                report,
                world_id=world_id,
                world_version_id=world_version_id,
            )
            review_sampling_plans_1000.extend(list(world_metrics["review_sampling_plan_1000"]))
            world_metrics["character_fidelity_remediation_framework"] = dict(
                report.get("character_fidelity_remediation_framework") or {}
            )
        if resolved_benchmark_mode == "longform_1000_interactive":
            steering_recovery_rate = float(interactive_summary.get("steering_recovery_rate", 0.0) or 0.0)
            post_steer_route_survival = float(interactive_summary.get("post_steer_route_survival", 0.0) or 0.0)
            memory_consistency_after_steer = float(interactive_summary.get("memory_consistency_after_steer", 0.0) or 0.0)
            promise_reconciliation_after_steer = float(interactive_summary.get("promise_reconciliation_after_steer", 0.0) or 0.0)
            replan_stability_score = float(interactive_summary.get("replan_stability_score", 0.0) or 0.0)
            interactive_gate_checks = {
                "steering_recovery_rate": steering_recovery_rate >= float(INTERACTIVE_LONGFORM_1000_THRESHOLDS["steering_recovery_rate_min"]),
                "post_steer_route_survival": post_steer_route_survival >= float(INTERACTIVE_LONGFORM_1000_THRESHOLDS["post_steer_route_survival_min"]),
                "memory_consistency_after_steer": memory_consistency_after_steer >= float(INTERACTIVE_LONGFORM_1000_THRESHOLDS["memory_consistency_after_steer_min"]),
                "promise_reconciliation_after_steer": promise_reconciliation_after_steer >= float(INTERACTIVE_LONGFORM_1000_THRESHOLDS["promise_reconciliation_after_steer_min"]),
                "replan_stability_score": replan_stability_score >= float(INTERACTIVE_LONGFORM_1000_THRESHOLDS["replan_stability_score_min"]),
            }
            world_metrics["interactive_summary"] = dict(interactive_summary)
            world_metrics["interactive_longform_1000_gate"] = {
                "passed": bool((world_metrics.get("longform_1000_feasibility") or {}).get("passed")) and all(interactive_gate_checks.values()),
                "failed_checks": [name for name, passed in interactive_gate_checks.items() if not passed] + ([] if (world_metrics.get("longform_1000_feasibility") or {}).get("passed") else ["longform_1000_feasibility"]),
                "checks": interactive_gate_checks,
            }
        if resolved_benchmark_mode == "longform_500_interactive":
            steering_recovery_rate = float(interactive_summary.get("steering_recovery_rate", 0.0) or 0.0)
            post_steer_route_survival = float(interactive_summary.get("post_steer_route_survival", 0.0) or 0.0)
            memory_consistency_after_steer = float(interactive_summary.get("memory_consistency_after_steer", 0.0) or 0.0)
            promise_reconciliation_after_steer = float(interactive_summary.get("promise_reconciliation_after_steer", 0.0) or 0.0)
            replan_stability_score = float(interactive_summary.get("replan_stability_score", 0.0) or 0.0)
            interactive_gate_checks = {
                "steering_recovery_rate": steering_recovery_rate >= float(INTERACTIVE_LONGFORM_500_THRESHOLDS["steering_recovery_rate_min"]),
                "post_steer_route_survival": post_steer_route_survival >= float(INTERACTIVE_LONGFORM_500_THRESHOLDS["post_steer_route_survival_min"]),
                "memory_consistency_after_steer": memory_consistency_after_steer >= float(INTERACTIVE_LONGFORM_500_THRESHOLDS["memory_consistency_after_steer_min"]),
                "promise_reconciliation_after_steer": promise_reconciliation_after_steer >= float(INTERACTIVE_LONGFORM_500_THRESHOLDS["promise_reconciliation_after_steer_min"]),
                "replan_stability_score": replan_stability_score >= float(INTERACTIVE_LONGFORM_500_THRESHOLDS["replan_stability_score_min"]),
            }
            world_metrics["interactive_summary"] = dict(interactive_summary)
            world_metrics["interactive_longform_500_gate"] = {
                "passed": bool((world_metrics.get("longform_500_gate") or {}).get("passed")) and all(interactive_gate_checks.values()),
                "failed_checks": [name for name, passed in interactive_gate_checks.items() if not passed] + ([] if (world_metrics.get("longform_500_gate") or {}).get("passed") else ["longform_500_gate"]),
                "checks": interactive_gate_checks,
            }
        if resolved_benchmark_mode == "longform_250_interactive":
            steering_recovery_rate = float(interactive_summary.get("steering_recovery_rate", 0.0) or 0.0)
            post_steer_route_survival = float(interactive_summary.get("post_steer_route_survival", 0.0) or 0.0)
            memory_consistency_after_steer = float(interactive_summary.get("memory_consistency_after_steer", 0.0) or 0.0)
            promise_reconciliation_after_steer = float(interactive_summary.get("promise_reconciliation_after_steer", 0.0) or 0.0)
            replan_stability_score = float(interactive_summary.get("replan_stability_score", 0.0) or 0.0)
            interactive_gate_checks = {
                "steering_recovery_rate": steering_recovery_rate >= float(INTERACTIVE_LONGFORM_250_THRESHOLDS["steering_recovery_rate_min"]),
                "post_steer_route_survival": post_steer_route_survival >= float(INTERACTIVE_LONGFORM_250_THRESHOLDS["post_steer_route_survival_min"]),
                "memory_consistency_after_steer": memory_consistency_after_steer >= float(INTERACTIVE_LONGFORM_250_THRESHOLDS["memory_consistency_after_steer_min"]),
                "promise_reconciliation_after_steer": promise_reconciliation_after_steer >= float(INTERACTIVE_LONGFORM_250_THRESHOLDS["promise_reconciliation_after_steer_min"]),
                "replan_stability_score": replan_stability_score >= float(INTERACTIVE_LONGFORM_250_THRESHOLDS["replan_stability_score_min"]),
            }
            world_metrics["interactive_summary"] = dict(interactive_summary)
            world_metrics["interactive_longform_250_gate"] = {
                "passed": bool((world_metrics.get("longform_250_gate") or {}).get("passed")) and all(interactive_gate_checks.values()),
                "failed_checks": [name for name, passed in interactive_gate_checks.items() if not passed] + ([] if (world_metrics.get("longform_250_gate") or {}).get("passed") else ["longform_250_gate"]),
                "checks": interactive_gate_checks,
            }
        world_metrics["top_issue_categories"] = [
            {
                "issue_code": issue.get("issue_code"),
                "count": int(issue.get("count", 0)),
                "owning_module": issue.get("owning_module", ""),
                "fix_hint": issue.get("fix_hint", ""),
            }
            for issue in issue_mix
        ]
        world_metrics["dimension_scores"] = build_dimension_scores(world_metrics)
        world_metrics["issue_summary"] = build_issue_summary(
            top_issue_categories=world_metrics["top_issue_categories"],
            dimension_scores=world_metrics["dimension_scores"],
            route_longevity_target=max_chapters,
        )
        world_metrics["content_quality_contract_coverage"] = asset_quality_contract_coverage(pack_payload)
        content_quality_contract_started = perf_counter()
        world_metrics["content_quality_contract_window_metrics"] = content_quality_window_metrics(
            chapter_report_payloads=chapter_reports_by_world[world_id],
            world_metrics=world_metrics,
            diagnostic_issue_code_resolver=diagnostic_scan_cache.codes_for,
        )
        world_metrics["runtime_profile"]["stages_ms"]["content_quality_contract"] = _elapsed_ms(content_quality_contract_started)
        progress.emit_stage(
            world_id=world_id,
            stage="content_quality_contract",
            elapsed_ms=world_metrics["runtime_profile"]["stages_ms"]["content_quality_contract"],
        )
        world_metrics["runtime_profile"]["stages_ms"]["world_total"] = _elapsed_ms(world_started)
        worlds.append(world_metrics)
        _write_benchmark_checkpoint(
            checkpoint_out,
            benchmark_mode=resolved_benchmark_mode,
            chapter_budget=max_chapters,
            worlds=worlds,
            diagnostic_scan_cache=diagnostic_scan_cache,
            stage="world_complete",
        )
        progress.emit(
            "world_complete",
            world_id=world_id,
            completed_world_count=len(worlds),
            world_count=len(selected_world_ids),
            completed_chapters=int(world_metrics.get("route_longevity", 0) or 0),
            pass_rate=round(float(world_metrics.get("pass_rate", 0.0) or 0.0), 3),
            block_rate=round(float(world_metrics.get("block_rate", 0.0) or 0.0), 3),
            world_total_ms=world_metrics["runtime_profile"]["stages_ms"]["world_total"],
        )
    post_world_summary_started = perf_counter()
    progress.emit("post_world_summary_start", completed_world_count=len(worlds))
    worlds = assign_diagnostic_ranks(worlds)
    cross_pack_pass_rate = sum(item["pass_rate"] for item in worlds) / float(max(1, len(worlds)))
    strongest_packs = rank_strongest_packs(worlds)
    weakest_packs = rank_weakest_packs(worlds)
    weakest_pack_diagnostics = [
        build_weakest_pack_diagnostic(
            world_metrics=next(item for item in worlds if item["world_id"] == pack["world_id"]),
            chapter_report_payloads=chapter_reports_by_world.get(pack["world_id"], []),
            pack_payload=pack_payload_by_world.get(pack["world_id"], {}),
        )
        for pack in weakest_packs
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_dir": str(golden_dir),
        "benchmark_mode": resolved_benchmark_mode,
        "acceptance_profile": acceptance_profile,
        "requested_benchmark_world_ids": requested_world_ids,
        "benchmark_world_ids": selected_world_ids,
        "benchmark_world_count": len(selected_world_ids),
        "benchmark_scope_complete": set(selected_world_ids) == set(BENCHMARK_PACKS),
        "fast_gate": fast_gate,
        "chapter_budget": max_chapters,
        "min_end_turn_override": min_end_turn_override,
        "interactive_profile": interactive_profile,
        "worlds": worlds,
        "cross_pack_pass_rate": round(cross_pack_pass_rate, 3),
        "strongest_packs": strongest_packs,
        "weakest_packs": weakest_packs,
        "top_failing_packs": rank_top_failing_packs(worlds),
        "weakest_pack_diagnostics": weakest_pack_diagnostics,
        "weakest_pack_polish_program": build_weakest_pack_polish_program(weakest_pack_diagnostics),
        "strategy_validation_summary": build_strategy_validation_summary(weakest_pack_diagnostics),
    }
    resolved_strategy_bundle_id = (
        (
            str(strategy_bundle_id or "").strip()
            if not validate_strategy_bundle
            else (
                str(strategy_bundle_id or "").strip()
                or str(
                    dict((summary.get("strategy_validation_summary") or {}).get("bundle_groups", [{}])[0]).get("strategy_bundle_id") or ""
                ).strip()
            )
        )
    )
    if validate_strategy_bundle and resolved_strategy_bundle_id:
        summary["strategy_bundle_batch_validation"] = _validate_strategy_bundle_batch(
            repository=repository,
            registry=registry,
            weakest_packs=weakest_packs,
            weakest_pack_diagnostics=weakest_pack_diagnostics,
            strategy_validation_summary=dict(summary.get("strategy_validation_summary") or {}),
            strategy_bundle_id=resolved_strategy_bundle_id,
            benchmark_mode=resolved_benchmark_mode,
            max_chapters=max_chapters,
            weakest_limit=weakest_limit,
            min_end_turn_override=min_end_turn_override,
            interactive_profile=interactive_profile,
            pack_payload_by_world=pack_payload_by_world,
            baseline_reports_by_world=baseline_reports_by_world,
        )
        record_strategy_bundle_batch_validation_run(
            repository=repository,
            batch_validation=dict(summary.get("strategy_bundle_batch_validation") or {}),
        )
    elif resolved_strategy_bundle_id:
        bundle_group = next(
            (
                dict(item or {})
                for item in list((summary.get("strategy_validation_summary") or {}).get("bundle_groups") or [])
                if str((item or {}).get("strategy_bundle_id") or "") == resolved_strategy_bundle_id
            ),
            {},
        )
        summary["strategy_bundle_batch_validation"] = {
            "available": False,
            "strategy_bundle_id": resolved_strategy_bundle_id,
            "strategy_bundle_label": str(bundle_group.get("strategy_bundle_label") or resolved_strategy_bundle_id),
            "batch_execution_mode": "ephemeral_copy",
            "benchmark_mode": resolved_benchmark_mode,
            "chapter_budget": max_chapters,
            "weakest_source_world_ids": [str(item.get("world_id") or "") for item in weakest_packs[: max(1, int(weakest_limit or 3))] if str(item.get("world_id") or "")],
            "compatible_world_ids": [],
            "skipped_worlds": [],
            "validated_world_count": 0,
            "validated_worlds": [],
            "aggregated_step_receipts": {},
            "aggregated_result_attribution": {},
            "effectiveness_rate": 0.0,
            "decision": "",
            "decision_reason": "history_only_query",
            "adaptation_targets": [],
        }
    if resolved_strategy_bundle_id:
        summary["strategy_bundle_batch_validation_history"] = list_strategy_bundle_batch_validation_history(
            repository=repository,
            strategy_bundle_id=resolved_strategy_bundle_id,
            limit=5,
        )
        summary["strategy_bundle_batch_validation_trend"] = build_strategy_bundle_batch_validation_trend(
            dict(summary.get("strategy_bundle_batch_validation_history") or {})
        )
    if max_chapters > 6:
        summary["long_route_summary"] = build_long_route_summary(worlds)
    summary["content_quality_contract_summary"] = build_content_quality_contract_summary(worlds)
    summary["generation_hard_constraint_summary"] = aggregate_generation_hard_constraint_summaries(worlds)
    if resolved_benchmark_mode == "long_route" and any(item.get("interactive_summary") for item in worlds):
        summary["interactive_long_route_summary"] = build_interactive_long_route_summary(
            worlds,
            target_chapters=max_chapters,
            interactive_profile=interactive_profile or "default",
        )
    if resolved_benchmark_mode == "longform_100":
        gate_payloads = [dict(item.get("longform_gate") or {}) for item in worlds]
        gate_failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("longform_gate") or {}).get("passed")]
        summary["longform_summary"] = {
            "target_chapters": 100,
            "character_drift_rate": round(sum(item.get("character_drift_rate", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "promise_unresolved_rate": round(sum(item.get("promise_unresolved_rate", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "arc_task_repeat_rate": round(sum(item.get("arc_task_repeat_rate", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "q09_incidence_rate": round(sum(item.get("q09_incidence_rate", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "premature_ending_trigger_rate": round(sum(item.get("premature_ending_trigger_rate", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "volume_climax_spacing_error": round(sum(item.get("volume_climax_spacing_error", 0.0) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(
                sum(1.0 for payload in gate_payloads if payload.get("passed")) / float(max(1, len(gate_payloads))),
                3,
            ),
            "failed_worlds": gate_failed_worlds,
        }
        summary["longform_gate"] = {
            "mode": "longform_100",
            "passed_world_count": sum(1 for payload in gate_payloads if payload.get("passed")),
            "failed_world_count": sum(1 for payload in gate_payloads if not payload.get("passed")),
            "pass_rate": round(
                sum(1.0 for payload in gate_payloads if payload.get("passed")) / float(max(1, len(gate_payloads))),
                3,
            ),
            "failed_worlds": gate_failed_worlds,
            "calibration": calibrate_longform_thresholds(worlds),
        }
    if resolved_benchmark_mode == "longform_100_interactive":
        interactive_gate_payloads = [dict(item.get("interactive_longform_gate") or {}) for item in worlds]
        interactive_failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("interactive_longform_gate") or {}).get("passed")]
        summary["interactive_longform_summary"] = {
            "target_chapters": 100,
            "steering_recovery_rate": round(sum(float((item.get("interactive_summary") or {}).get("steering_recovery_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "post_steer_route_survival": round(sum(float((item.get("interactive_summary") or {}).get("post_steer_route_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_consistency_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("memory_consistency_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "promise_reconciliation_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("promise_reconciliation_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("interactive_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
        }
        summary["interactive_longform_gate"] = {
            "mode": "longform_100_interactive",
            "passed_world_count": sum(1 for payload in interactive_gate_payloads if payload.get("passed")),
            "failed_world_count": sum(1 for payload in interactive_gate_payloads if not payload.get("passed")),
            "pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
            "calibrated_thresholds": dict(INTERACTIVE_LONGFORM_THRESHOLDS),
        }
    if resolved_benchmark_mode in {"longform_250", "longform_250_interactive"}:
        gate_payloads = [dict(item.get("longform_250_gate") or {}) for item in worlds]
        failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("longform_250_gate") or {}).get("passed")]
        execution_summary = (
            _execute_review_sampling_plan_250(
                training_signal=training_signal,
                review_sampling_plans_250=review_sampling_plans_250,
                chapter_reports_by_world=chapter_reports_by_world,
            )
            if execute_review_sampling_250
            else {}
        )
        review_sample_coverage_250 = _build_review_sample_coverage_250(
            training_signal=training_signal,
            review_sampling_plans_250=review_sampling_plans_250,
            execution_summary=execution_summary,
        )
        summary["longform_250_summary"] = {
            "target_chapters": 250,
            "volume_boundary_survival": round(sum(float((item.get("longform_250_summary") or {}).get("volume_boundary_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_recall_coverage": round(sum(float((item.get("longform_250_summary") or {}).get("memory_recall_coverage", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("longform_250_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "volume_snapshot_integrity": round(sum(float((item.get("longform_250_summary") or {}).get("volume_snapshot_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "mid_volume_pass_rate": round(sum(float((item.get("longform_250_summary") or {}).get("mid_volume_pass_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "late_volume_pass_rate": round(sum(float((item.get("longform_250_summary") or {}).get("late_volume_pass_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in gate_payloads if payload.get("passed")) / float(max(1, len(gate_payloads))), 3),
            "failed_worlds": failed_worlds,
        }
        summary["longform_250_evidence"] = {
            "gate_pass_rate": summary["longform_250_summary"]["gate_pass_rate"],
            "failed_worlds": failed_worlds,
            "review_sample_coverage_250": review_sample_coverage_250,
            "review_sample_closeout_ready": bool(review_sample_coverage_250.get("closeout_ready", False)),
            "review_sample_human_closeout_ready": bool(review_sample_coverage_250.get("human_closeout_ready", False)),
        }
        summary["review_sample_coverage_250"] = review_sample_coverage_250
    if resolved_benchmark_mode == "longform_250_interactive":
        interactive_gate_payloads = [dict(item.get("interactive_longform_250_gate") or {}) for item in worlds]
        interactive_failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("interactive_longform_250_gate") or {}).get("passed")]
        summary["longform_250_interactive_summary"] = {
            "target_chapters": 250,
            "steering_recovery_rate": round(sum(float((item.get("interactive_summary") or {}).get("steering_recovery_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "post_steer_route_survival": round(sum(float((item.get("interactive_summary") or {}).get("post_steer_route_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_consistency_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("memory_consistency_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "promise_reconciliation_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("promise_reconciliation_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("interactive_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
        }
        summary["longform_250_interactive_gate"] = {
            "mode": "longform_250_interactive",
            "passed_world_count": sum(1 for payload in interactive_gate_payloads if payload.get("passed")),
            "failed_world_count": sum(1 for payload in interactive_gate_payloads if not payload.get("passed")),
            "pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
            "calibrated_thresholds": dict(INTERACTIVE_LONGFORM_250_THRESHOLDS),
        }
    if resolved_benchmark_mode in {"longform_500", "longform_500_interactive"}:
        gate_payloads = [dict(item.get("longform_500_gate") or {}) for item in worlds]
        failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("longform_500_gate") or {}).get("passed")]
        execution_summary = (
            _execute_review_sampling_plan_500(
                training_signal=training_signal,
                review_sampling_plans_500=review_sampling_plans_500,
                chapter_reports_by_world=chapter_reports_by_world,
            )
            if execute_review_sampling_500
            else {}
        )
        human_execution_summary = (
            _execute_human_review_closeout_plan_500(
                training_signal=training_signal,
                review_sampling_plans_500=review_sampling_plans_500,
                chapter_reports_by_world=chapter_reports_by_world,
                reviewer_id=human_review_closeout_500_reviewer_id,
                target_chapters=max_chapters,
                diagnostic_scan_cache=diagnostic_scan_cache,
            )
            if execute_human_review_closeout_500
            else {}
        )
        review_sample_coverage_500 = _build_review_sample_coverage_500(
            training_signal=training_signal,
            review_sampling_plans_500=review_sampling_plans_500,
            execution_summary=execution_summary,
            human_execution_summary=human_execution_summary,
        )
        summary["longform_500_summary"] = {
            "target_chapters": 500,
            "series_boundary_survival": round(sum(float((item.get("longform_500_summary") or {}).get("series_boundary_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "series_memory_snapshot_integrity": round(sum(float((item.get("longform_500_summary") or {}).get("series_memory_snapshot_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_recall_coverage": round(sum(float((item.get("longform_500_summary") or {}).get("memory_recall_coverage", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("longform_500_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "late_series_pass_rate": round(sum(float((item.get("longform_500_summary") or {}).get("late_series_pass_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "series_ending_control_score": round(sum(float((item.get("longform_500_summary") or {}).get("series_ending_control_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in gate_payloads if payload.get("passed")) / float(max(1, len(gate_payloads))), 3),
            "failed_worlds": failed_worlds,
        }
        summary["longform_500_evidence"] = {
            "gate_pass_rate": summary["longform_500_summary"]["gate_pass_rate"],
            "failed_worlds": failed_worlds,
            "review_sample_coverage_500": review_sample_coverage_500,
            "review_sample_human_closeout_ready": bool(review_sample_coverage_500.get("human_closeout_ready", False)),
            "ending_window_human_closeout_ready": bool(review_sample_coverage_500.get("ending_window_human_closeout_ready", False)),
        }
        summary["review_sample_coverage_500"] = review_sample_coverage_500
    if resolved_benchmark_mode == "longform_500_interactive":
        interactive_gate_payloads = [dict(item.get("interactive_longform_500_gate") or {}) for item in worlds]
        interactive_failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("interactive_longform_500_gate") or {}).get("passed")]
        summary["longform_500_interactive_summary"] = {
            "target_chapters": 500,
            "steering_recovery_rate": round(sum(float((item.get("interactive_summary") or {}).get("steering_recovery_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "post_steer_route_survival": round(sum(float((item.get("interactive_summary") or {}).get("post_steer_route_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_consistency_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("memory_consistency_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "promise_reconciliation_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("promise_reconciliation_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("interactive_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
        }
        summary["longform_500_interactive_gate"] = {
            "mode": "longform_500_interactive",
            "passed_world_count": sum(1 for payload in interactive_gate_payloads if payload.get("passed")),
            "failed_world_count": sum(1 for payload in interactive_gate_payloads if not payload.get("passed")),
            "pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
            "calibrated_thresholds": dict(INTERACTIVE_LONGFORM_500_THRESHOLDS),
        }
    if resolved_benchmark_mode in {"longform_1000_diagnostics", "longform_1000_interactive"}:
        feasibility_payloads = [dict(item.get("longform_1000_feasibility") or {}) for item in worlds]
        failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("longform_1000_feasibility") or {}).get("passed")]
        summary["longform_1000_summary"] = {
            "target_chapters": 1000,
            "series_boundary_survival": round(sum(float((item.get("longform_1000_summary") or {}).get("series_boundary_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "series_memory_snapshot_integrity": round(sum(float((item.get("longform_1000_summary") or {}).get("series_memory_snapshot_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "series_snapshot_count": round(sum(float((item.get("longform_1000_summary") or {}).get("series_snapshot_count", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "retained_series_snapshot_target": round(sum(float((item.get("longform_1000_summary") or {}).get("retained_series_snapshot_target", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_recall_coverage": round(sum(float((item.get("longform_1000_summary") or {}).get("memory_recall_coverage", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("longform_1000_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "archive_retention_integrity": round(sum(float((item.get("longform_1000_summary") or {}).get("archive_retention_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "timeline_retention_integrity": round(sum(float((item.get("longform_1000_summary") or {}).get("timeline_retention_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "continuation_state_retention_integrity": round(sum(float((item.get("longform_1000_summary") or {}).get("continuation_state_retention_integrity", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "late_stage_runtime_p95_ms": round(sum(float((item.get("longform_1000_summary") or {}).get("late_stage_runtime_p95_ms", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "late_stage_runtime_budget_score": round(sum(float((item.get("longform_1000_summary") or {}).get("late_stage_runtime_budget_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "series_ending_control_score": round(sum(float((item.get("longform_1000_summary") or {}).get("series_ending_control_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "diagnostic_pass_rate": round(sum(1.0 for payload in feasibility_payloads if payload.get("passed")) / float(max(1, len(feasibility_payloads))), 3),
            "failed_worlds": failed_worlds,
        }
        summary["longform_1000_evidence"] = {
            "diagnostic_pass_rate": summary["longform_1000_summary"]["diagnostic_pass_rate"],
            "failed_worlds": failed_worlds,
        }
        summary["review_sample_coverage_1000"] = _build_review_sample_coverage_1000(
            training_signal=training_signal,
            review_sampling_plans_1000=review_sampling_plans_1000,
        )
        summary["character_fidelity_remediation_framework"] = {
            "available": True,
            "world_count": len(worlds),
            "q06_worlds": [
                {
                    "world_id": item["world_id"],
                    "character_fidelity": float(item.get("character_fidelity", 0.0) or 0.0),
                    "q06_issue_share": next(
                        (float(issue.get("share", 0.0) or 0.0) for issue in item.get("issue_mix", []) if issue.get("issue_code") == "Q06"),
                        0.0,
                    ),
                    "framework": dict(item.get("character_fidelity_remediation_framework") or {}),
                }
                for item in worlds
                if next((issue for issue in item.get("issue_mix", []) if issue.get("issue_code") == "Q06"), None)
                or float(item.get("character_fidelity", 0.0) or 0.0) < 0.34
            ],
            "recommended_assets": [
                "characters",
                "emotion_action_policies",
                "scene_blueprints",
            ],
        }
    if resolved_benchmark_mode == "longform_1000_interactive":
        interactive_gate_payloads = [dict(item.get("interactive_longform_1000_gate") or {}) for item in worlds]
        interactive_failed_worlds = [item["world_id"] for item in worlds if not dict(item.get("interactive_longform_1000_gate") or {}).get("passed")]
        summary["longform_1000_interactive_summary"] = {
            "target_chapters": 1000,
            "steering_recovery_rate": round(sum(float((item.get("interactive_summary") or {}).get("steering_recovery_rate", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "post_steer_route_survival": round(sum(float((item.get("interactive_summary") or {}).get("post_steer_route_survival", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "memory_consistency_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("memory_consistency_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "promise_reconciliation_after_steer": round(sum(float((item.get("interactive_summary") or {}).get("promise_reconciliation_after_steer", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "replan_stability_score": round(sum(float((item.get("interactive_summary") or {}).get("replan_stability_score", 0.0)) for item in worlds) / float(max(1, len(worlds))), 3),
            "gate_pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
        }
        summary["longform_1000_interactive_gate"] = {
            "mode": "longform_1000_interactive",
            "passed_world_count": sum(1 for payload in interactive_gate_payloads if payload.get("passed")),
            "failed_world_count": sum(1 for payload in interactive_gate_payloads if not payload.get("passed")),
            "pass_rate": round(sum(1.0 for payload in interactive_gate_payloads if payload.get("passed")) / float(max(1, len(interactive_gate_payloads))), 3),
            "failed_worlds": interactive_failed_worlds,
            "calibrated_thresholds": dict(INTERACTIVE_LONGFORM_1000_THRESHOLDS),
        }
    summary["longform_l1_signoff"] = build_longform_l1_signoff(summary)
    summary["interactive_longform_signoff"] = build_interactive_longform_signoff(summary)
    summary["longform_250_signoff"] = build_longform_250_signoff(summary)
    summary["longform_250_interactive_signoff"] = build_longform_250_interactive_signoff(summary)
    summary["longform_250_human_review_closeout"] = build_longform_250_human_review_closeout(summary)
    summary["longform_500_signoff"] = build_longform_500_signoff(summary)
    summary["longform_500_human_review_closeout"] = build_longform_500_human_review_closeout(summary)
    summary["longform_500_ending_signoff"] = build_longform_500_ending_signoff(summary)
    summary["longform_500_interactive_signoff"] = build_longform_500_interactive_signoff(summary)
    summary["longform_1000_readiness"] = build_longform_1000_readiness(summary)
    summary["longform_1000_human_review_closeout"] = build_longform_1000_human_review_closeout(summary)
    summary["longform_1000_interactive_signoff"] = build_longform_1000_interactive_signoff(summary)
    summary["longform_1000_feasibility"] = build_longform_1000_feasibility(summary)
    summary["content_quality_contract_gate"] = evaluate_content_quality_contract_gate(summary)
    if baseline:
        summary["delta_summary"] = benchmark_delta_report(summary, baseline)
    summary["commercial_long_route_gate"] = evaluate_commercial_long_route_gate(summary)
    summary["phase_a_quality_gate"] = evaluate_release_quality_gate(summary)
    summary["benchmark_runtime_profile"] = _build_benchmark_runtime_profile(
        worlds=worlds,
        total_wall_ms=_elapsed_ms(benchmark_started),
        acceptance_profile=acceptance_profile,
        fast_gate=fast_gate,
        post_world_summary_ms=_elapsed_ms(post_world_summary_started),
        diagnostic_issue_scan_cache=diagnostic_scan_cache.summary(),
    )
    _write_benchmark_checkpoint(
        checkpoint_out,
        benchmark_mode=resolved_benchmark_mode,
        chapter_budget=max_chapters,
        worlds=worlds,
        diagnostic_scan_cache=diagnostic_scan_cache,
        stage="complete",
    )
    progress.emit(
        "benchmark_complete",
        completed_world_count=len(worlds),
        total_wall_ms=summary["benchmark_runtime_profile"]["total_wall_ms"],
        diagnostic_scan_hits=diagnostic_scan_cache.hits,
        diagnostic_scan_misses=diagnostic_scan_cache.misses,
        slow_scan_count=len(diagnostic_scan_cache.slow_scans),
    )
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NarrativeOS cross-pack benchmark and emit capability metrics.")
    parser.add_argument("--worldpack", default="all")
    parser.add_argument("--golden-dir", default="tests/golden_routes")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--baseline-file", default="tests/benchmark_baseline.json")
    parser.add_argument("--markdown-out", default=None)
    parser.add_argument("--benchmark-mode", default=None)
    parser.add_argument("--max-chapters", type=int, default=6)
    parser.add_argument("--min-end-turn-override", type=int, default=None)
    parser.add_argument("--execute-review-sampling-250", action="store_true")
    parser.add_argument("--execute-review-sampling-500", action="store_true")
    parser.add_argument("--execute-human-review-closeout-500", action="store_true")
    parser.add_argument("--human-review-closeout-500-reviewer-id", default="ops_longform500_reviewer_after_residual_fix")
    parser.add_argument("--interactive-profile", choices=["default", "strong"], default=None)
    parser.add_argument("--acceptance-profile", choices=["full", "nightly", "fast"], default="full")
    parser.add_argument("--changed-worldpacks", default="")
    parser.add_argument("--fast-gate-weakest-limit", type=int, default=3)
    parser.add_argument("--runtime-profile-out", default=None)
    parser.add_argument("--progress-out", default=None)
    parser.add_argument("--checkpoint-out", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    baseline_path = Path(args.baseline_file)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    repository = SQLAlchemyRepository(database_url=args.database_url)
    progress_out = Path(args.progress_out) if args.progress_out else None
    checkpoint_out = (
        Path(args.checkpoint_out)
        if args.checkpoint_out
        else (progress_out.with_suffix(".checkpoint.json") if progress_out else None)
    )
    summary = run_benchmark(
        repository=repository,
        golden_dir=Path(args.golden_dir),
        worldpack=args.worldpack,
        baseline=baseline,
        benchmark_mode=args.benchmark_mode,
        max_chapters=int(args.max_chapters),
        min_end_turn_override=int(args.min_end_turn_override) if args.min_end_turn_override is not None else None,
        execute_review_sampling_250=bool(args.execute_review_sampling_250),
        execute_review_sampling_500=bool(args.execute_review_sampling_500),
        execute_human_review_closeout_500=bool(args.execute_human_review_closeout_500),
        human_review_closeout_500_reviewer_id=str(args.human_review_closeout_500_reviewer_id),
        interactive_profile=args.interactive_profile,
        acceptance_profile=str(args.acceptance_profile),
        changed_worldpacks=_split_world_id_tokens(args.changed_worldpacks),
        fast_gate_weakest_limit=int(args.fast_gate_weakest_limit),
        progress_out=progress_out,
        checkpoint_out=checkpoint_out,
    )
    artifact_started = perf_counter()
    artifact_paths: Dict[str, object] = {}
    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_benchmark_markdown(summary), encoding="utf-8")
        artifact_paths["markdown"] = str(markdown_path)
    if args.runtime_profile_out:
        runtime_profile_path = Path(args.runtime_profile_out)
        runtime_profile_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_paths["runtime_profile"] = str(runtime_profile_path)
    if progress_out:
        artifact_paths["progress"] = str(progress_out)
    if checkpoint_out:
        artifact_paths["checkpoint"] = str(checkpoint_out)
    runtime_profile = dict(summary.get("benchmark_runtime_profile") or {})
    runtime_profile["artifact_write_ms"] = _elapsed_ms(artifact_started)
    runtime_profile["artifact_paths"] = artifact_paths
    summary["benchmark_runtime_profile"] = runtime_profile
    if args.runtime_profile_out:
        Path(args.runtime_profile_out).write_text(
            json.dumps(runtime_profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
