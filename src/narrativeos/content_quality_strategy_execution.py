from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Sequence
from uuid import uuid4


def execute_strategy_bundle_protocol(
    *,
    worldpack_payload: Dict[str, Any],
    baseline_simulation_report: Dict[str, Any],
    campaign: Dict[str, Any],
    strategy_bundle: Dict[str, Any],
    execution_mode: str,
    simulation_runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    apply_step: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    build_result_attribution: Callable[..., Dict[str, Any]],
    build_stop_decision: Callable[..., Dict[str, Any]],
    prior_executions: Sequence[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    mutated_worldpack_payload = copy.deepcopy(worldpack_payload)
    step_plan = sorted(
        [dict(item or {}) for item in list(strategy_bundle.get("step_level_apply_order") or [])],
        key=lambda item: int(item.get("apply_order", 0) or 0),
    )
    step_receipts = [apply_step(mutated_worldpack_payload, step) for step in step_plan]
    rerun_report = copy.deepcopy(simulation_runner(mutated_worldpack_payload))
    latest_repair_loop_outcome = dict(rerun_report.get("latest_repair_loop_outcome") or {})
    result_attribution = build_result_attribution(
        strategy_bundle=strategy_bundle,
        baseline_report=baseline_simulation_report,
        rerun_report=rerun_report,
        step_receipts=step_receipts,
        latest_repair_loop_outcome=latest_repair_loop_outcome,
    )
    stop_decision = build_stop_decision(
        stop_condition=dict(strategy_bundle.get("stop_condition") or {}),
        result_attribution=result_attribution,
        prior_executions=[dict(item or {}) for item in list(prior_executions or [])],
        latest_repair_loop_outcome=latest_repair_loop_outcome,
    )
    return {
        "execution_id": f"bundle_exec_{uuid4().hex[:10]}",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": execution_mode,
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "strategy_bundle_id": str(strategy_bundle.get("strategy_bundle_id") or ""),
        "strategy_bundle_label": str(
            strategy_bundle.get("strategy_bundle_label")
            or strategy_bundle.get("label")
            or strategy_bundle.get("strategy_bundle_id")
            or ""
        ),
        "window_label": str(campaign.get("window_label") or ""),
        "issue_code": str(campaign.get("issue_code") or ""),
        "issue_codes": list(
            dict.fromkeys(
                str(item)
                for item in list(strategy_bundle.get("issue_codes") or [campaign.get("issue_code")])
                if str(item)
            )
        ),
        "bundle_step_planning": step_plan,
        "step_level_apply_order": step_plan,
        "step_level_apply_receipt": step_receipts,
        "applied_step_count": sum(1 for item in step_receipts if str(item.get("status") or "") == "applied"),
        "applied_edit_count": sum(int(item.get("applied_edit_count", 0) or 0) for item in step_receipts),
        "rerun_attribution": dict(strategy_bundle.get("rerun_attribution") or {}),
        "result_attribution": result_attribution,
        "stop_condition": dict(strategy_bundle.get("stop_condition") or {}),
        "stop_decision": stop_decision,
        "repair_loop_outcome": {
            "ready_for_validation": bool(latest_repair_loop_outcome.get("ready_for_validation", False)),
            "severity_trend": str(latest_repair_loop_outcome.get("severity_trend") or ""),
            "window_label": str(latest_repair_loop_outcome.get("window_label") or ""),
            "window_breach_kind": str(latest_repair_loop_outcome.get("window_breach_kind") or ""),
            "baseline_window_issue_count": int(latest_repair_loop_outcome.get("baseline_window_issue_count", 0) or 0),
            "current_window_issue_count": int(latest_repair_loop_outcome.get("current_window_issue_count", 0) or 0),
        },
        "execution_status": "completed",
        "mutated_worldpack_payload": mutated_worldpack_payload,
        "rerun_report": rerun_report,
    }


def build_step_level_apply_summary(step_receipts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts = Counter()
    asset_type_counts = Counter()
    operation_counts = Counter()
    applied_step_count = 0
    applied_edit_count = 0
    for step in list(step_receipts or []):
        status = str(step.get("status") or "")
        asset_type = str(step.get("asset_type") or "")
        if status:
            status_counts[status] += 1
        if asset_type:
            asset_type_counts[asset_type] += 1
        if status == "applied":
            applied_step_count += 1
        applied_edit_count += int(step.get("applied_edit_count", 0) or 0)
        for edit in list(step.get("edit_receipts") or []):
            operation = str(edit.get("operation") or "")
            if operation:
                operation_counts[operation] += 1
    return {
        "step_status_counts": dict(status_counts),
        "asset_type_counts": dict(asset_type_counts),
        "operation_counts": dict(operation_counts),
        "applied_step_count": applied_step_count,
        "applied_edit_count": applied_edit_count,
    }


def _top_counter_items(counter: Counter, *, limit: int = 3) -> List[Dict[str, Any]]:
    return [
        {"name": name, "count": int(count)}
        for name, count in counter.most_common(limit)
        if str(name)
    ]


def build_strategy_bundle_batch_validation_summary(
    *,
    strategy_bundle_id: str,
    strategy_bundle_label: str,
    batch_execution_mode: str,
    benchmark_mode: str,
    chapter_budget: int,
    weakest_source_world_ids: Sequence[str],
    compatible_world_ids: Sequence[str],
    skipped_worlds: Sequence[Dict[str, Any]],
    validated_worlds: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    validated = [dict(item or {}) for item in list(validated_worlds or [])]
    skipped = [dict(item or {}) for item in list(skipped_worlds or [])]
    aggregated_step_statuses = Counter()
    aggregated_asset_types = Counter()
    aggregated_operations = Counter()
    aggregated_result_statuses = Counter()
    improved_metric_counts = Counter()
    regressed_metric_counts = Counter()
    flat_metric_counts = Counter()
    stop_decision_counts = Counter()
    adaptation_metric_counts = Counter()
    adaptation_asset_counts = Counter()
    ready_for_validation_count = 0
    effective_count = 0

    for world in validated:
        step_summary = dict(world.get("step_receipt_summary") or {})
        result_attribution = dict(world.get("result_attribution") or {})
        stop_decision = dict(world.get("stop_decision") or {})
        for name, count in dict(step_summary.get("step_status_counts") or {}).items():
            aggregated_step_statuses[str(name)] += int(count or 0)
        for name, count in dict(step_summary.get("asset_type_counts") or {}).items():
            aggregated_asset_types[str(name)] += int(count or 0)
        for name, count in dict(step_summary.get("operation_counts") or {}).items():
            aggregated_operations[str(name)] += int(count or 0)
        overall_status = str(result_attribution.get("overall_status") or "")
        if overall_status:
            aggregated_result_statuses[overall_status] += 1
        for metric_name in list(result_attribution.get("improved_metrics") or []):
            improved_metric_counts[str(metric_name)] += 1
        for metric_name in list(result_attribution.get("regressed_metrics") or []):
            regressed_metric_counts[str(metric_name)] += 1
            adaptation_metric_counts[str(metric_name)] += 1
        for metric_name in list(result_attribution.get("flat_metrics") or []):
            flat_metric_counts[str(metric_name)] += 1
        stop_name = str(stop_decision.get("decision") or "")
        if stop_name:
            stop_decision_counts[stop_name] += 1
        if bool(world.get("ready_for_validation")):
            ready_for_validation_count += 1
        if overall_status == "improved" or bool(world.get("ready_for_validation")):
            effective_count += 1
        for step in list(world.get("step_level_apply_receipt") or []):
            step_status = str(step.get("status") or "")
            asset_type = str(step.get("asset_type") or "")
            if step_status in {"noop", "skipped"} and asset_type:
                adaptation_asset_counts[asset_type] += 1

    validated_world_count = len(validated)
    effectiveness_rate = round(
        effective_count / float(max(1, validated_world_count)),
        3,
    ) if validated_world_count else 0.0
    regressed_count = int(aggregated_result_statuses.get("regressed", 0))
    escalate_count = int(stop_decision_counts.get("escalate", 0))

    if validated_world_count == 0:
        decision = ""
        decision_reason = "no_compatible_weakest_packs"
        available = False
    elif (
        validated_world_count >= 2
        and effectiveness_rate >= 0.67
        and (regressed_count / float(validated_world_count)) < 0.34
        and (escalate_count / float(validated_world_count)) < 0.34
    ):
        decision = "continue"
        decision_reason = "bundle_effective_across_weakest_packs"
        available = True
    elif (
        validated_world_count >= 2
        and (
            effectiveness_rate < 0.34
            or (regressed_count / float(validated_world_count)) >= 0.5
        )
    ):
        decision = "retire"
        decision_reason = "bundle_low_effectiveness_or_high_regression"
        available = True
    else:
        decision = "adapt"
        decision_reason = "bundle_mixed_signal_requires_adjustment"
        available = True

    adaptation_targets: List[Dict[str, Any]] = []
    for item in _top_counter_items(adaptation_metric_counts):
        adaptation_targets.append({"kind": "metric", **item})
    for item in _top_counter_items(adaptation_asset_counts):
        adaptation_targets.append({"kind": "asset_step", **item})

    return {
        "available": available,
        "strategy_bundle_id": strategy_bundle_id,
        "strategy_bundle_label": strategy_bundle_label,
        "batch_execution_mode": batch_execution_mode,
        "benchmark_mode": benchmark_mode,
        "chapter_budget": int(chapter_budget or 0),
        "weakest_source_world_ids": list(weakest_source_world_ids or []),
        "compatible_world_ids": list(compatible_world_ids or []),
        "skipped_worlds": skipped,
        "validated_world_count": validated_world_count,
        "validated_worlds": validated,
        "aggregated_step_receipts": {
            "step_status_counts": dict(aggregated_step_statuses),
            "asset_type_counts": dict(aggregated_asset_types),
            "operation_counts": dict(aggregated_operations),
            "applied_step_count": sum(int(item.get("step_receipt_summary", {}).get("applied_step_count", 0) or 0) for item in validated),
            "applied_edit_count": sum(int(item.get("step_receipt_summary", {}).get("applied_edit_count", 0) or 0) for item in validated),
        },
        "aggregated_result_attribution": {
            "overall_status_counts": dict(aggregated_result_statuses),
            "improved_metric_counts": dict(improved_metric_counts),
            "regressed_metric_counts": dict(regressed_metric_counts),
            "flat_metric_counts": dict(flat_metric_counts),
            "stop_decision_counts": dict(stop_decision_counts),
            "ready_for_validation_count": ready_for_validation_count,
        },
        "effectiveness_rate": effectiveness_rate,
        "decision": decision,
        "decision_reason": decision_reason,
        "adaptation_targets": adaptation_targets[:6],
    }


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_history_notes(notes: Any) -> Dict[str, Any]:
    if isinstance(notes, dict):
        return dict(notes)
    if not isinstance(notes, str) or not notes:
        return {}
    try:
        payload = json.loads(notes)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _strategy_bundle_history_note_payload(batch_validation: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(batch_validation or {})
    return {
        "generated_at": str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()),
        "strategy_bundle_id": str(payload.get("strategy_bundle_id") or ""),
        "strategy_bundle_label": str(payload.get("strategy_bundle_label") or ""),
        "benchmark_mode": str(payload.get("benchmark_mode") or ""),
        "chapter_budget": int(payload.get("chapter_budget", 0) or 0),
        "weakest_source_world_ids": [str(item) for item in list(payload.get("weakest_source_world_ids") or []) if str(item)],
        "compatible_world_ids": [str(item) for item in list(payload.get("compatible_world_ids") or []) if str(item)],
        "validated_world_count": int(payload.get("validated_world_count", 0) or 0),
        "effectiveness_rate": _safe_float(payload.get("effectiveness_rate")),
        "decision": str(payload.get("decision") or ""),
        "decision_reason": str(payload.get("decision_reason") or ""),
        "aggregated_result_attribution": {
            "overall_status_counts": dict(
                dict(payload.get("aggregated_result_attribution") or {}).get("overall_status_counts") or {}
            ),
            "stop_decision_counts": dict(
                dict(payload.get("aggregated_result_attribution") or {}).get("stop_decision_counts") or {}
            ),
        },
        "adaptation_targets": [dict(item or {}) for item in list(payload.get("adaptation_targets") or [])[:6]],
    }


def record_strategy_bundle_batch_validation_run(
    *,
    repository: Any,
    batch_validation: Dict[str, Any],
    reviewer_id: str = "system_batch_validator",
) -> Dict[str, Any]:
    payload = _strategy_bundle_history_note_payload(batch_validation)
    strategy_bundle_id = str(payload.get("strategy_bundle_id") or "")
    if not strategy_bundle_id:
        return {}
    decision = str(payload.get("decision") or "").strip() or "not_run"
    return repository.save_review_record(
        {
            "asset_type": "strategy_bundle_batch_validation",
            "asset_id": strategy_bundle_id,
            "status": decision,
            "reviewer_id": reviewer_id,
            "notes": json.dumps(payload, ensure_ascii=False),
        }
    )


def list_strategy_bundle_batch_validation_history(
    *,
    repository: Any,
    strategy_bundle_id: str,
    limit: int = 5,
) -> Dict[str, Any]:
    if not str(strategy_bundle_id or "").strip():
        return {
            "available": False,
            "strategy_bundle_id": "",
            "entry_count": 0,
            "entries": [],
        }
    rows = list(
        repository.list_review_records(
            asset_type="strategy_bundle_batch_validation",
            asset_id=strategy_bundle_id,
        )
        or []
    )
    entries: List[Dict[str, Any]] = []
    for row in rows[: max(1, int(limit or 5))]:
        notes_payload = _parse_history_notes(row.get("notes"))
        decision = str(notes_payload.get("decision") or row.get("status") or "")
        entries.append(
            {
                "review_id": row.get("review_id"),
                "generated_at": str(notes_payload.get("generated_at") or row.get("updated_at") or ""),
                "strategy_bundle_id": str(notes_payload.get("strategy_bundle_id") or strategy_bundle_id),
                "strategy_bundle_label": str(notes_payload.get("strategy_bundle_label") or ""),
                "benchmark_mode": str(notes_payload.get("benchmark_mode") or ""),
                "chapter_budget": int(notes_payload.get("chapter_budget", 0) or 0),
                "validated_world_count": int(notes_payload.get("validated_world_count", 0) or 0),
                "effectiveness_rate": _safe_float(notes_payload.get("effectiveness_rate")),
                "decision": decision,
                "decision_reason": str(notes_payload.get("decision_reason") or ""),
                "compatible_world_ids": [
                    str(item) for item in list(notes_payload.get("compatible_world_ids") or []) if str(item)
                ],
                "top_adaptation_targets": [
                    dict(item or {}) for item in list(notes_payload.get("adaptation_targets") or [])[:3]
                ],
            }
        )
    return {
        "available": bool(entries),
        "strategy_bundle_id": str(strategy_bundle_id),
        "entry_count": len(entries),
        "entries": entries,
    }


def build_strategy_bundle_batch_validation_trend(
    history_payload: Dict[str, Any],
) -> Dict[str, Any]:
    history = dict(history_payload or {})
    entries = [dict(item or {}) for item in list(history.get("entries") or [])]
    comparable_entries = [item for item in entries if str(item.get("decision") or "") != "not_run"]
    if not entries:
        return {
            "available": False,
            "strategy_bundle_id": str(history.get("strategy_bundle_id") or ""),
            "recent_run_count": 0,
            "latest_decision": "",
            "latest_effectiveness_rate": 0.0,
            "previous_effectiveness_rate": 0.0,
            "delta_effectiveness_rate": 0.0,
            "trend_status": "insufficient_history",
            "trend_reason": "no_saved_batch_validation_runs",
            "retire_recommended": False,
        }
    latest_entry = dict(comparable_entries[0] if comparable_entries else entries[0])
    previous_entry = dict(comparable_entries[1] if len(comparable_entries) > 1 else {})
    latest_decision = str(latest_entry.get("decision") or "")
    latest_effectiveness_rate = _safe_float(latest_entry.get("effectiveness_rate"))
    previous_effectiveness_rate = _safe_float(previous_entry.get("effectiveness_rate"))
    delta_effectiveness_rate = round(latest_effectiveness_rate - previous_effectiveness_rate, 3)
    recent_run_count = len(comparable_entries)
    if latest_decision == "retire" or (
        len(comparable_entries) >= 2
        and str(comparable_entries[0].get("decision") or "") == "retire"
        and str(comparable_entries[1].get("decision") or "") == "retire"
    ):
        trend_status = "retire_watch"
        trend_reason = "latest_or_recent_runs_recommend_retire"
    elif recent_run_count < 2:
        trend_status = "insufficient_history"
        trend_reason = "fewer_than_two_comparable_runs"
    elif delta_effectiveness_rate >= 0.10:
        trend_status = "improving"
        trend_reason = "effectiveness_rate_up_by_0_10_or_more"
    elif delta_effectiveness_rate <= -0.10:
        trend_status = "deteriorating"
        trend_reason = "effectiveness_rate_down_by_0_10_or_more"
    else:
        trend_status = "flat"
        trend_reason = "effectiveness_rate_change_within_flat_band"
    recent_three = comparable_entries[:3]
    retire_recommended = bool(
        trend_status == "retire_watch"
        or (
            recent_three
            and round(
                sum(_safe_float(item.get("effectiveness_rate")) for item in recent_three)
                / float(len(recent_three)),
                3,
            ) < 0.34
            and latest_decision in {"adapt", "retire"}
        )
    )
    return {
        "available": True,
        "strategy_bundle_id": str(history.get("strategy_bundle_id") or latest_entry.get("strategy_bundle_id") or ""),
        "recent_run_count": recent_run_count,
        "latest_decision": latest_decision,
        "latest_effectiveness_rate": latest_effectiveness_rate,
        "previous_effectiveness_rate": previous_effectiveness_rate,
        "delta_effectiveness_rate": delta_effectiveness_rate,
        "trend_status": trend_status,
        "trend_reason": trend_reason,
        "retire_recommended": retire_recommended,
    }
