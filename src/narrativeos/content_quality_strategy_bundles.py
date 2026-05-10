from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_CONTENT_QUALITY_STRATEGY_BUNDLES_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "content_quality_strategy_bundles.json"
)

DEFAULT_CONTENT_QUALITY_STRATEGY_BUNDLES: Dict[str, Any] = {
    "config_version": "content_quality_strategy_bundles_v1",
    "bundles": {},
}


def load_content_quality_strategy_bundles(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_CONTENT_QUALITY_STRATEGY_BUNDLES_PATH
    payload = dict(DEFAULT_CONTENT_QUALITY_STRATEGY_BUNDLES)
    if config_path.exists():
        try:
            file_payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return payload
        if isinstance(file_payload, dict):
            payload.update(file_payload)
    return payload


def _bundle_id_for_issue_codes(issue_codes: Sequence[str]) -> str:
    normalized = {str(item or "") for item in issue_codes if str(item or "")}
    if {"Q03", "Q04"} <= normalized:
        return "q03_q04_scene_dialogue_cadence_task_coupling"
    if "Q09" in normalized:
        return "q09_continuation_runway"
    if "Q04" in normalized:
        return "q04_scene_dialogue_cadence"
    if "Q03" in normalized:
        return "q03_scene_dialogue_cadence"
    if "Q05" in normalized:
        return "q05_scene_grounding_detail"
    return ""


def _asset_type_from_path(path: str) -> str:
    if path.startswith("scene_blueprints["):
        return "scene_blueprint"
    if path.startswith('scene_realization_contracts["default"]'):
        return "scene_realization_contracts"
    if path.startswith('emotion_action_policies["default"]'):
        return "emotion_action_policies"
    if path.startswith('voice_profiles["'):
        return "voice_profiles"
    if path.startswith('response_cadence_profiles["'):
        return "response_cadence_profiles"
    if path.startswith('characters[character_id="'):
        return "character_card"
    if path.startswith('arc_plans['):
        return "chapter_task_coupling" if ".chapter_tasks[" in path else "arc_plan"
    return ""


def _metric_direction(metric_name: str) -> str:
    increasing = {
        "dialogue_ratio",
        "scene_detail_density",
        "late_arc_pass_rate",
        "mid_arc_pass_rate",
        "pass_rate",
    }
    return "increase" if metric_name in increasing else "decrease"


def _stop_condition_payload(rule_id: str) -> Dict[str, Any]:
    mapping = {
        "upgrade_to_planner_or_pack_contract_if_two_reruns_flat": {
            "description": "如果连续两次 full rerun 主要窗口指标持平或回退，就升级到 planner / pack-level contract。",
            "tripwire": "two_reruns_flat_or_regressed",
        },
        "upgrade_to_task_coupling_if_flat": {
            "description": "如果 scene/dialogue/cadence 修完后窗口仍持平，就升级到 task coupling。",
            "tripwire": "scene_dialogue_cadence_flat",
        },
        "upgrade_to_budget_and_task_balance_if_flat": {
            "description": "如果 grounding/detail 修完后仍持平，就升级到 budget/task balance。",
            "tripwire": "detail_bundle_flat",
        },
        "upgrade_to_planner_contract_if_flat": {
            "description": "如果 continuation runway 修完后仍持平，就升级到 planner contract。",
            "tripwire": "continuation_bundle_flat",
        },
    }
    payload = dict(mapping.get(rule_id, {}))
    return {
        "rule_id": rule_id,
        "description": payload.get("description", ""),
        "tripwire": payload.get("tripwire", ""),
    }


def _bundle_step_planning(
    *,
    bundle_id: str,
    bundle_label: str,
    asset_sequence: Sequence[str],
    target_by_type: Dict[str, Dict[str, Any]],
    edits_by_asset: Dict[str, List[Dict[str, Any]]],
    validation_sequence: Sequence[str],
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for index, asset_type in enumerate(list(asset_sequence or []), start=1):
        target = dict(target_by_type.get(asset_type) or {})
        step_edits = list(edits_by_asset.get(asset_type, []))
        if not target and not step_edits:
            continue
        steps.append(
            {
                "step_id": f"{bundle_id}::step_{index}",
                "bundle_label": bundle_label,
                "apply_order": len(steps) + 1,
                "step_kind": "asset_apply",
                "asset_type": asset_type,
                "target": target,
                "validation_panel": str(target.get("validation_panel") or ""),
                "validation_panel_label": str(target.get("validation_panel_label") or ""),
                "suggested_field_edits": step_edits,
                "post_apply_validation": (
                    list(validation_sequence or [])
                    if asset_type in {"chapter_task", "chapter_task_coupling", "arc_plan"}
                    else [str(target.get("validation_panel") or "compare")]
                ),
            }
        )
    return steps


def _rerun_attribution_payload(
    *,
    window_label: str,
    success_metrics: Sequence[str],
) -> Dict[str, Any]:
    return {
        "rerun_scope": "full_100_rerun",
        "compare_scope": "window_slice",
        "window_label": window_label,
        "metrics_to_watch": [
            {
                "metric": str(metric_name),
                "direction": _metric_direction(str(metric_name)),
            }
            for metric_name in list(success_metrics or [])
        ],
        "attribution_rule": "first_compare_bundle_metrics_then_window_metrics_then_global_quality",
        "result_receipt_fields": [
            "baseline_window_issue_count",
            "current_window_issue_count",
            "baseline_window_worst_decision",
            "current_window_worst_decision",
            "ready_for_validation",
        ],
    }


def build_strategy_bundle(
    *,
    issue_codes: Sequence[str],
    window_label: str,
    primary_asset_target: Dict[str, Any],
    secondary_asset_targets: Sequence[Dict[str, Any]],
    suggested_actions: Sequence[Dict[str, Any]],
    suggested_field_edits: Sequence[Dict[str, Any]],
    targeted_chapter_indices: Sequence[int],
) -> Dict[str, Any]:
    config = load_content_quality_strategy_bundles()
    bundle_id = _bundle_id_for_issue_codes(issue_codes)
    bundle_payload = dict((config.get("bundles") or {}).get(bundle_id, {}) or {})
    if not bundle_id:
        return {}

    asset_targets: List[Dict[str, Any]] = [dict(primary_asset_target or {})] + [dict(item or {}) for item in list(secondary_asset_targets or [])]
    target_by_type = {
        str(item.get("asset_type") or ""): dict(item)
        for item in asset_targets
        if str(item.get("asset_type") or "")
    }
    edits_by_asset: Dict[str, List[Dict[str, Any]]] = {}
    for item in list(suggested_field_edits or []):
        path = str(item.get("path") or "")
        asset_type = _asset_type_from_path(path)
        if not asset_type:
            continue
        edits_by_asset.setdefault(asset_type, []).append(dict(item))
    actions = [dict(item or {}) for item in list(suggested_actions or [])]
    if "chapter_task_coupling" in list(bundle_payload.get("asset_sequence") or []) and "chapter_task_coupling" not in target_by_type:
        target_by_type["chapter_task_coupling"] = {
            "asset_type": "chapter_task_coupling",
            "asset_label": "章节任务耦合",
            "validation_panel": "task_linking",
            "validation_panel_label": "Task Linking",
            "target_label": ",".join(str(item) for item in list(targeted_chapter_indices or [])[:6]),
        }
    step_planning = _bundle_step_planning(
        bundle_id=bundle_id,
        bundle_label=str(bundle_payload.get("label") or bundle_id),
        asset_sequence=list(bundle_payload.get("asset_sequence") or []),
        target_by_type=target_by_type,
        edits_by_asset=edits_by_asset,
        validation_sequence=list(bundle_payload.get("validation_sequence") or []),
    )
    rerun_attribution = _rerun_attribution_payload(
        window_label=window_label,
        success_metrics=list(bundle_payload.get("success_metrics") or []),
    )
    stop_condition = _stop_condition_payload(str(bundle_payload.get("stop_condition") or ""))
    return {
        "strategy_bundle_id": bundle_id,
        "strategy_bundle_label": str(bundle_payload.get("label") or bundle_id),
        "window_label": window_label,
        "issue_codes": list(dict.fromkeys(str(item) for item in issue_codes if str(item))),
        "asset_sequence": list(bundle_payload.get("asset_sequence") or []),
        "validation_sequence": list(bundle_payload.get("validation_sequence") or []),
        "success_metrics": list(bundle_payload.get("success_metrics") or []),
        "stop_condition": stop_condition,
        "steps": step_planning,
        "bundle_step_planning": step_planning,
        "step_level_apply_order": [dict(item) for item in step_planning],
        "rerun_attribution": rerun_attribution,
        "execution_protocol_enabled": True,
        "suggested_actions": actions,
        "config_version": str(config.get("config_version") or ""),
    }


def infer_strategy_bundles_for_diagnostic(diagnostic: Dict[str, Any]) -> List[Dict[str, Any]]:
    window_breach_attribution = [dict(item or {}) for item in list(diagnostic.get("window_breach_attribution") or [])]
    issue_codes = [str(item.get("issue_code") or "") for item in list(diagnostic.get("issue_category_distribution") or []) if str(item.get("issue_code") or "")]
    bundles: List[Dict[str, Any]] = []
    seen: set[str] = set()
    if window_breach_attribution:
        for item in window_breach_attribution:
            bundle_id = _bundle_id_for_issue_codes(list(item.get("issue_codes") or []))
            if not bundle_id or bundle_id in seen:
                continue
            seen.add(bundle_id)
            bundle = build_strategy_bundle(
                issue_codes=list(item.get("issue_codes") or []),
                window_label=str(item.get("window_label") or ""),
                primary_asset_target={
                    "asset_type": item.get("asset"),
                    "asset_label": item.get("asset"),
                    "validation_panel": "compare" if item.get("asset") != "chapter_tasks" else "task_linking",
                    "validation_panel_label": "Compare" if item.get("asset") != "chapter_tasks" else "Task Linking",
                    "target_label": item.get("asset"),
                },
                secondary_asset_targets=[],
                suggested_actions=[],
                suggested_field_edits=[],
                targeted_chapter_indices=[],
            )
            if bundle:
                bundle["world_id"] = diagnostic.get("world_id", "")
                bundles.append(bundle)
    for issue_code in issue_codes:
        bundle_id = _bundle_id_for_issue_codes([issue_code])
        if not bundle_id or bundle_id in seen:
            continue
        seen.add(bundle_id)
        bundle = build_strategy_bundle(
            issue_codes=[issue_code],
            window_label="general",
            primary_asset_target={"asset_type": "", "target_label": ""},
            secondary_asset_targets=[],
            suggested_actions=[],
            suggested_field_edits=[],
            targeted_chapter_indices=[],
        )
        if bundle:
            bundle["world_id"] = diagnostic.get("world_id", "")
            bundles.append(bundle)
    return bundles


def build_strategy_validation_summary(weakest_pack_diagnostics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for diagnostic in list(weakest_pack_diagnostics or []):
        for bundle in infer_strategy_bundles_for_diagnostic(dict(diagnostic or {})):
            bundle_id = str(bundle.get("strategy_bundle_id") or "")
            if not bundle_id:
                continue
            entry = grouped.setdefault(
                bundle_id,
                {
                    "strategy_bundle_id": bundle_id,
                    "strategy_bundle_label": bundle.get("strategy_bundle_label", bundle_id),
                    "world_ids": [],
                    "window_labels": [],
                    "success_metrics": list(bundle.get("success_metrics") or []),
                },
            )
            world_id = str(bundle.get("world_id") or "")
            if world_id and world_id not in entry["world_ids"]:
                entry["world_ids"].append(world_id)
            window_label = str(bundle.get("window_label") or "")
            if window_label and window_label not in entry["window_labels"]:
                entry["window_labels"].append(window_label)
    return {
        "available": bool(grouped),
        "bundle_groups": sorted(grouped.values(), key=lambda item: (-len(item["world_ids"]), item["strategy_bundle_id"])),
        "bundle_count": len(grouped),
    }
