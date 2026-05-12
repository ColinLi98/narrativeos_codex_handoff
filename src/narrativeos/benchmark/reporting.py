from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

from ..content_quality_strategy_bundles import (
    build_strategy_validation_summary,
    infer_strategy_bundles_for_diagnostic,
)
from ..eval.taxonomy import ISSUE_TAXONOMY


DELTA_METRICS = (
    "pass_rate",
    "rewrite_rate",
    "block_rate",
    "character_fidelity",
    "causal_continuity",
    "choice_distinctness",
    "prose_leak_rate",
    "route_longevity",
    "dialogue_ratio",
    "scene_detail_density",
    "voice_separation_score",
    "emotion_action_specificity",
    "long_route_quality",
    "mid_arc_drop",
    "dialogue_distinctness",
    "completion_ratio",
    "avg_overall_score",
    "mid_arc_pass_rate",
    "late_arc_pass_rate",
    "avg_repetition_score",
    "avg_exposition_ratio",
    "avg_hook_quality",
    "diagnostic_score",
)

DIAGNOSIS_DIMENSIONS = (
    "character_fidelity",
    "causal_continuity",
    "choice_distinctness",
    "prose_leak_rate",
    "route_longevity",
    "dialogue_ratio",
    "scene_detail_density",
    "voice_separation_score",
    "emotion_action_specificity",
)

ISSUE_TARGET_MAP = {
    "Q04": "writer / sensory / scene realization",
    "Q05": "writer / sensory / scene realization",
    "Q03": "writer / dialogue/action variation",
    "Q08": "presenter / choice generation",
    "Q09": "planner / scene pacing / hook",
    "Q06": "planner / evaluator / world pack asset",
    "Q07": "planner / evaluator / world pack asset",
}

CHAPTER_DECISION_ORDER = {
    "block": 0,
    "rewrite": 1,
    "pass": 2,
}

ISSUE_DIAGNOSTIC_PLAYBOOK = {
    "Q03": {
        "module": "writer",
        "asset": "voice_profiles",
        "policy": "dialogue_realism_policy",
        "action": "expand differentiated voice beats and reduce repeated line/action patterns.",
    },
    "Q04": {
        "module": "writer",
        "asset": "scene_blueprints",
        "policy": "scene_realization_contracts",
        "action": "shift explanation into beats, reactions, and concrete scene realization.",
    },
    "Q05": {
        "module": "writer",
        "asset": "sensory_grounding_policies",
        "policy": "scene_realization_contracts",
        "action": "add concrete object, sound, motion, and body-detail grounding in weakest chapters.",
    },
    "Q06": {
        "module": "planner",
        "asset": "characters",
        "policy": "emotion_action_policies",
        "action": "tighten character wound/vow/action alignment before more prose iteration.",
    },
    "Q07": {
        "module": "planner",
        "asset": "world_bible",
        "policy": "scene_realization_contracts",
        "action": "reconnect promises, debts, and world facts to scene-level consequences.",
    },
    "Q08": {
        "module": "presenter",
        "asset": "scene_blueprints",
        "policy": "dialogue_realism_policy",
        "action": "increase choice divergence in motive, cost, and risk rather than wording only.",
    },
    "Q09": {
        "module": "planner",
        "asset": "scene_blueprints",
        "policy": "scene_realization_contracts",
        "action": "strengthen hook cadence, scene escalation, and ending gates for mid-route survival.",
    },
}

DIMENSION_DIAGNOSTIC_PLAYBOOK = {
    "scene_detail_density": {
        "module": "writer",
        "asset": "sensory_grounding_policies",
        "policy": "scene_realization_contracts",
        "action": "expand sensory grounding coverage where weakest chapters are visually thin.",
    },
    "voice_separation_score": {
        "module": "writer",
        "asset": "voice_profiles",
        "policy": "dialogue_realism_policy",
        "action": "increase per-role contrast in directness, restraint, and response cadence.",
    },
    "route_longevity": {
        "module": "planner",
        "asset": "scene_blueprints",
        "policy": "scene_realization_contracts",
        "action": "add more durable mid-route beats and stronger continuation gates.",
    },
    "dialogue_ratio": {
        "module": "writer",
        "asset": "voice_profiles",
        "policy": "dialogue_realism_policy",
        "action": "rebalance dialogue/action cadence so scenes move through turns instead of exposition.",
    },
    "character_fidelity": {
        "module": "planner",
        "asset": "characters",
        "policy": "emotion_action_policies",
        "action": "tighten character-state alignment and emotional action defaults.",
    },
    "causal_continuity": {
        "module": "planner",
        "asset": "world_bible",
        "policy": "scene_realization_contracts",
        "action": "link consequences back to promises, debts, and prior scene outcomes.",
    },
    "emotion_action_specificity": {
        "module": "writer",
        "asset": "emotion_action_policies",
        "policy": "scene_realization_contracts",
        "action": "add more entry/pressure/pivot/aftermath variations to action policy maps.",
    },
    "choice_distinctness": {
        "module": "presenter",
        "asset": "scene_blueprints",
        "policy": "dialogue_realism_policy",
        "action": "separate choice branches by consequence and intent, not surface phrasing.",
    },
}

POLISH_STOP_THRESHOLDS = {
    "pass_rate_min": 0.99,
    "block_rate_max": 0.0,
    "long_route_quality_min": 0.85,
    "scene_detail_density_min": 0.03,
    "dialogue_distinctness_min": 0.55,
    "dialogue_ratio_min": 0.55,
    "diagnostic_score_max": 0.08,
}
LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS = 24 * 7
INTERACTIVE_LONG_ROUTE_ISSUE_CODES = ("Q03", "Q04", "Q05", "Q09")


def _metric_delta(current: Dict[str, Any], baseline: Dict[str, Any], key: str) -> float:
    return round(float(current.get(key, 0.0)) - float(baseline.get(key, 0.0)), 3)


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _dimension_weakness(name: str, value: float, *, route_longevity_target: int = 6) -> float:
    if name == "prose_leak_rate":
        return value
    if name == "route_longevity":
        return max(0.0, 1.0 - min(value / float(max(1, route_longevity_target)), 1.0))
    return max(0.0, 1.0 - value)


def _scene_detail_density_weakness(value: float) -> float:
    return max(0.0, 1.0 - min(value / 0.02, 1.0))


def _fallback_long_route_quality(world_metrics: Dict[str, Any]) -> float:
    route_longevity = float(world_metrics.get("route_longevity", 0.0))
    pass_rate = float(world_metrics.get("pass_rate", 0.0))
    target = int(world_metrics.get("route_longevity_target", 6))
    return round(pass_rate * min(route_longevity / float(max(1, target)), 1.0), 3)


def _segment(values: Sequence[float], start: int, end: int) -> List[float]:
    return list(values[start:end])


def build_asset_snapshot(pack_payload: Dict[str, Any]) -> Dict[str, int]:
    style_pack = dict(pack_payload.get("narrative_style_pack", {}))
    dialogue = dict(style_pack.get("dialogue", {}))
    return {
        "characters": len(pack_payload.get("characters", [])),
        "scene_blueprints": len(pack_payload.get("scene_blueprints", [])),
        "world_bible": len(pack_payload.get("world_bible", {})),
        "voice_profiles": len(pack_payload.get("voice_profiles") or dialogue.get("voice_profiles", {})),
        "emotion_action_policies": len(pack_payload.get("emotion_action_policies", {})),
        "sensory_grounding_policies": len(pack_payload.get("sensory_grounding_policies", {})),
        "scene_realization_contracts": len(pack_payload.get("scene_realization_contracts", {})),
        "dialogue_realism_policy": 1 if pack_payload.get("dialogue_realism_policy") else 0,
    }


def build_issue_mix(issue_payloads: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not issue_payloads:
        return []
    totals: Dict[str, Dict[str, Any]] = {}
    total_issues = float(len(issue_payloads))
    for issue in issue_payloads:
        issue_code = str(issue.get("issue_code", "")).strip()
        if not issue_code:
            continue
        record = totals.setdefault(
            issue_code,
            {
                "issue_code": issue_code,
                "count": 0,
                "owning_module": issue.get("owning_module", "")
                or ISSUE_TAXONOMY.get(issue_code, {}).get("owning_module", ""),
                "fix_hint": ISSUE_TAXONOMY.get(issue_code, {}).get("fix_hint", ""),
            },
        )
        record["count"] += 1
        if not record.get("owning_module") and issue.get("owning_module"):
            record["owning_module"] = issue.get("owning_module", "")
    ranked = sorted(
        totals.values(),
        key=lambda item: (-int(item.get("count", 0)), str(item.get("issue_code", ""))),
    )
    return [
        {
            "issue_code": item["issue_code"],
            "count": int(item["count"]),
            "share": round(int(item["count"]) / total_issues, 3),
            "owning_module": item.get("owning_module", ""),
            "fix_hint": item.get("fix_hint", ""),
        }
        for item in ranked
    ]


def build_route_diagnostics(
    overall_scores: Sequence[float],
    *,
    completed_chapters: int,
    target_chapters: int = 6,
) -> Dict[str, float]:
    if not overall_scores:
        return {
            "long_route_quality": 0.0,
            "mid_arc_drop": 0.0,
        }
    normalized_length = min(float(completed_chapters) / float(max(1, target_chapters)), 1.0)
    average_score = _average(overall_scores)
    first_window_end = max(1, len(overall_scores) // 3)
    mid_window_start = first_window_end
    mid_window_end = max(mid_window_start + 1, (2 * len(overall_scores)) // 3)
    first_window = list(overall_scores[:first_window_end])
    mid_window = list(overall_scores[mid_window_start:mid_window_end]) or [overall_scores[-1]]
    return {
        "long_route_quality": round(average_score * normalized_length, 3),
        "mid_arc_drop": round(max(0.0, _average(first_window) - _average(mid_window)), 3),
    }


def build_long_route_diagnostics(
    *,
    chapter_report_payloads: Sequence[Dict[str, Any]],
    completed_chapters: int,
    target_chapters: int,
    min_end_turn_target: int,
    stop_reason: str,
) -> Dict[str, Any]:
    if not chapter_report_payloads:
        return {
            "target_chapters": int(target_chapters),
            "min_end_turn_target": int(min_end_turn_target),
            "completion_ratio": 0.0,
            "stop_reason": stop_reason,
            "premature_ending": True,
            "avg_overall_score": 0.0,
            "mid_arc_pass_rate": 0.0,
            "late_arc_pass_rate": 0.0,
            "avg_repetition_score": 0.0,
            "mid_arc_repetition_score": 0.0,
            "late_arc_repetition_score": 0.0,
            "avg_exposition_ratio": 0.0,
            "mid_arc_exposition_ratio": 0.0,
            "late_arc_exposition_ratio": 0.0,
            "avg_hook_quality": 0.0,
            "mid_arc_hook_quality": 0.0,
            "late_arc_hook_quality": 0.0,
        }
    scores = [dict(item.get("scores", {})) for item in chapter_report_payloads]
    lint_metrics = [dict(item.get("hard_validator_results", {}).get("lint_metrics", {})) for item in chapter_report_payloads]
    decisions = [str(item.get("decision", {}).get("decision", "rewrite")) for item in chapter_report_payloads]
    overall_scores = [float(item.get("overall_score", 0.0)) for item in scores]
    hook_scores = [float(item.get("hook_quality", 0.0)) for item in scores]
    repetition_scores = [float(item.get("repetition_score", 0.0)) for item in lint_metrics]
    exposition_ratios = [float(item.get("exposition_ratio", 0.0)) for item in lint_metrics]
    first_end = max(1, len(chapter_report_payloads) // 3)
    mid_end = max(first_end + 1, (2 * len(chapter_report_payloads)) // 3)
    middle_decisions = decisions[first_end:mid_end] or decisions[-1:]
    late_decisions = decisions[mid_end:] or decisions[-1:]
    middle_repetition = _segment(repetition_scores, first_end, mid_end) or repetition_scores[-1:]
    late_repetition = repetition_scores[mid_end:] or repetition_scores[-1:]
    middle_exposition = _segment(exposition_ratios, first_end, mid_end) or exposition_ratios[-1:]
    late_exposition = exposition_ratios[mid_end:] or exposition_ratios[-1:]
    middle_hook = _segment(hook_scores, first_end, mid_end) or hook_scores[-1:]
    late_hook = hook_scores[mid_end:] or hook_scores[-1:]
    return {
        "target_chapters": int(target_chapters),
        "min_end_turn_target": int(min_end_turn_target),
        "completion_ratio": round(completed_chapters / float(max(1, target_chapters)), 3),
        "stop_reason": stop_reason,
        "premature_ending": completed_chapters < int(min_end_turn_target),
        "avg_overall_score": round(_average(overall_scores), 3),
        "mid_arc_pass_rate": round(
            sum(1 for decision in middle_decisions if decision == "pass") / float(max(1, len(middle_decisions))),
            3,
        ),
        "late_arc_pass_rate": round(
            sum(1 for decision in late_decisions if decision == "pass") / float(max(1, len(late_decisions))),
            3,
        ),
        "avg_repetition_score": round(_average(repetition_scores), 3),
        "mid_arc_repetition_score": round(_average(middle_repetition), 3),
        "late_arc_repetition_score": round(_average(late_repetition), 3),
        "avg_exposition_ratio": round(_average(exposition_ratios), 3),
        "mid_arc_exposition_ratio": round(_average(middle_exposition), 3),
        "late_arc_exposition_ratio": round(_average(late_exposition), 3),
        "avg_hook_quality": round(_average(hook_scores), 3),
        "mid_arc_hook_quality": round(_average(middle_hook), 3),
        "late_arc_hook_quality": round(_average(late_hook), 3),
    }


def build_dimension_scores(world_metrics: Dict[str, Any]) -> Dict[str, float]:
    return {name: float(world_metrics.get(name, 0.0)) for name in DIAGNOSIS_DIMENSIONS}


def build_issue_summary(
    *,
    top_issue_categories: Sequence[Dict[str, Any]],
    dimension_scores: Dict[str, float],
    route_longevity_target: int = 6,
) -> Dict[str, Any]:
    dominant_issue = top_issue_categories[0]["issue_code"] if top_issue_categories else ""
    weakest_dimensions = [
        {
            "name": name,
            "value": round(float(value), 3),
            "weakness": round(
                _dimension_weakness(name, float(value), route_longevity_target=route_longevity_target),
                3,
            ),
        }
        for name, value in sorted(
            dimension_scores.items(),
            key=lambda item: (
                -_dimension_weakness(
                    item[0],
                    float(item[1]),
                    route_longevity_target=route_longevity_target,
                ),
                item[0],
            ),
        )[:3]
    ]
    return {
        "dominant_issue": dominant_issue,
        "weakest_dimensions": weakest_dimensions,
        "recommended_target": ISSUE_TARGET_MAP.get(dominant_issue, "writer / planner / world pack asset"),
    }


def compute_diagnostic_score(world_metrics: Dict[str, Any]) -> float:
    pass_rate = float(world_metrics.get("pass_rate", 0.0))
    block_rate = float(world_metrics.get("block_rate", 0.0))
    long_route_quality = float(
        world_metrics.get("long_route_quality", _fallback_long_route_quality(world_metrics))
    )
    mid_arc_drop = float(world_metrics.get("mid_arc_drop", 0.0))
    dialogue_distinctness = float(
        world_metrics.get("dialogue_distinctness", world_metrics.get("voice_separation_score", 0.0))
    )
    scene_detail_density = float(world_metrics.get("scene_detail_density", 0.0))
    prose_leak_rate = float(world_metrics.get("prose_leak_rate", 0.0))
    return round(
        (0.30 * (1.0 - pass_rate))
        + (0.10 * block_rate)
        + (0.15 * (1.0 - long_route_quality))
        + (0.15 * mid_arc_drop)
        + (0.10 * (1.0 - dialogue_distinctness))
        + (0.10 * _scene_detail_density_weakness(scene_detail_density))
        + (0.10 * prose_leak_rate),
        3,
    )


def _enrich_world_metrics(world_metrics: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(world_metrics)
    enriched["long_route_quality"] = round(
        float(enriched.get("long_route_quality", _fallback_long_route_quality(enriched))),
        3,
    )
    enriched["mid_arc_drop"] = round(float(enriched.get("mid_arc_drop", 0.0)), 3)
    enriched["dialogue_distinctness"] = round(
        float(enriched.get("dialogue_distinctness", enriched.get("voice_separation_score", 0.0))),
        3,
    )
    enriched["diagnostic_score"] = compute_diagnostic_score(enriched)
    return enriched


def assign_diagnostic_ranks(worlds: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = [_enrich_world_metrics(item) for item in worlds]
    ranked = sorted(
        enriched,
        key=lambda item: (
            -float(item.get("diagnostic_score", 0.0)),
            float(item.get("pass_rate", 0.0)),
            -float(item.get("block_rate", 0.0)),
            float(item.get("long_route_quality", 0.0)),
            -float(item.get("mid_arc_drop", 0.0)),
            float(item.get("dialogue_distinctness", 0.0)),
            str(item.get("world_id", "")),
        ),
    )
    rank_map = {item["world_id"]: index + 1 for index, item in enumerate(ranked)}
    for item in enriched:
        item["diagnostic_rank"] = rank_map[item["world_id"]]
    return enriched


def _pack_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "world_id": item["world_id"],
        "pass_rate": item.get("pass_rate", 0.0),
        "rewrite_rate": item.get("rewrite_rate", 0.0),
        "block_rate": item.get("block_rate", 0.0),
        "voice_separation_score": item.get("voice_separation_score", 0.0),
        "emotion_action_specificity": item.get("emotion_action_specificity", 0.0),
        "prose_leak_rate": item.get("prose_leak_rate", 0.0),
        "long_route_quality": item.get("long_route_quality", 0.0),
        "mid_arc_drop": item.get("mid_arc_drop", 0.0),
        "dialogue_distinctness": item.get("dialogue_distinctness", 0.0),
        "completion_ratio": item.get("completion_ratio"),
        "stop_reason": item.get("stop_reason"),
        "diagnostic_score": item.get("diagnostic_score", 0.0),
        "diagnostic_rank": item.get("diagnostic_rank"),
        "top_issue_categories": list(item.get("top_issue_categories", [])),
        "issue_mix": list(item.get("issue_mix", [])),
        "weakest_dimensions": list(item.get("issue_summary", {}).get("weakest_dimensions", [])),
        "recommended_target": item.get("issue_summary", {}).get("recommended_target", ""),
        "dimension_scores": dict(item.get("dimension_scores", {})),
    }


def build_worst_chapters(chapter_report_payloads: Sequence[Dict[str, Any]], *, limit: int = 3) -> List[Dict[str, Any]]:
    chapters = []
    for payload in chapter_report_payloads:
        scores = dict(payload.get("scores", {}))
        issues = list(payload.get("issues", []))
        lint_metrics = dict(payload.get("hard_validator_results", {}).get("lint_metrics", {}))
        issue_codes = [str(issue.get("issue_code", "")) for issue in issues if issue.get("issue_code")]
        module_focus = sorted(
            {
                ISSUE_TAXONOMY.get(issue_code, {}).get("owning_module", "")
                for issue_code in issue_codes
                if ISSUE_TAXONOMY.get(issue_code, {}).get("owning_module", "")
            }
        )
        chapters.append(
            {
                "chapter_id": payload.get("chapter_id", ""),
                "decision": payload.get("decision", {}).get("decision", "rewrite"),
                "overall_score": round(float(scores.get("overall_score", 0.0)), 3),
                "issue_codes": issue_codes,
                "issue_count": len(issue_codes),
                "summary": payload.get("summary", ""),
                "module_focus": module_focus,
                "signal_snapshot": {
                    "engineering_leak_rate": round(float(lint_metrics.get("engineering_leak_rate", 0.0)), 3),
                    "repetition_score": round(float(lint_metrics.get("repetition_score", 0.0)), 3),
                    "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0)), 3),
                    "dialogue_plus_action_ratio": round(float(lint_metrics.get("dialogue_plus_action_ratio", 0.0)), 3),
                    "concrete_detail_density": round(float(lint_metrics.get("concrete_detail_density", 0.0)), 3),
                },
            }
        )
    ranked = sorted(
        chapters,
        key=lambda item: (
            CHAPTER_DECISION_ORDER.get(str(item.get("decision", "rewrite")), 3),
            float(item.get("overall_score", 0.0)),
            -int(item.get("issue_count", 0)),
            -float(item.get("signal_snapshot", {}).get("exposition_ratio", 0.0)),
            float(item.get("signal_snapshot", {}).get("concrete_detail_density", 0.0)),
            str(item.get("chapter_id", "")),
        ),
    )
    return ranked[:limit]


def build_attribution_diagnostics(
    *,
    issue_mix: Sequence[Dict[str, Any]],
    weakest_dimensions: Sequence[Dict[str, Any]],
    pack_payload: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot = build_asset_snapshot(pack_payload)
    candidate_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    def register(*, module: str, asset: str, policy: str, weight: float, issue_code: str = "", dimension: str = "", action: str = "") -> None:
        key = (module, asset, policy)
        entry = candidate_map.setdefault(
            key,
            {
                "module": module,
                "asset": asset,
                "policy": policy,
                "signal_score": 0.0,
                "issue_codes": set(),
                "weakest_dimensions": set(),
                "suggested_action": action,
            },
        )
        entry["signal_score"] += weight
        if issue_code:
            entry["issue_codes"].add(issue_code)
        if dimension:
            entry["weakest_dimensions"].add(dimension)
        if action and not entry.get("suggested_action"):
            entry["suggested_action"] = action

    for issue in issue_mix:
        issue_code = str(issue.get("issue_code", ""))
        playbook = ISSUE_DIAGNOSTIC_PLAYBOOK.get(issue_code)
        if not playbook:
            continue
        register(
            module=playbook["module"],
            asset=playbook["asset"],
            policy=playbook["policy"],
            weight=float(issue.get("count", 0)),
            issue_code=issue_code,
            action=playbook["action"],
        )
    for dimension in weakest_dimensions:
        name = str(dimension.get("name", ""))
        playbook = DIMENSION_DIAGNOSTIC_PLAYBOOK.get(name)
        if not playbook:
            continue
        register(
            module=playbook["module"],
            asset=playbook["asset"],
            policy=playbook["policy"],
            weight=float(dimension.get("weakness", 0.0)),
            dimension=name,
            action=playbook["action"],
        )

    ranked_candidates = sorted(
        candidate_map.values(),
        key=lambda item: (
            -float(item.get("signal_score", 0.0)),
            str(item.get("module", "")),
            str(item.get("asset", "")),
            str(item.get("policy", "")),
        ),
    )

    def aggregate_by(field: str) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for candidate in ranked_candidates:
            value = str(candidate.get(field, ""))
            if not value:
                continue
            entry = grouped.setdefault(
                value,
                {
                    field: value,
                    "signal_score": 0.0,
                    "issue_codes": set(),
                    "weakest_dimensions": set(),
                    "coverage": snapshot.get(value, 0),
                },
            )
            entry["signal_score"] += float(candidate.get("signal_score", 0.0))
            entry["issue_codes"].update(candidate.get("issue_codes", set()))
            entry["weakest_dimensions"].update(candidate.get("weakest_dimensions", set()))
        return [
            {
                field: key,
                "signal_score": round(float(value.get("signal_score", 0.0)), 3),
                "issue_codes": sorted(value.get("issue_codes", set())),
                "weakest_dimensions": sorted(value.get("weakest_dimensions", set())),
                "coverage": int(value.get("coverage", 0)),
            }
            for key, value in sorted(
                grouped.items(),
                key=lambda item: (-float(item[1].get("signal_score", 0.0)), item[0]),
            )
        ]

    next_fix_candidates = []
    for index, candidate in enumerate(ranked_candidates[:3], start=1):
        next_fix_candidates.append(
            {
                "priority": index,
                "module": candidate["module"],
                "asset": candidate["asset"],
                "policy": candidate["policy"],
                "issue_codes": sorted(candidate.get("issue_codes", set())),
                "weakest_dimensions": sorted(candidate.get("weakest_dimensions", set())),
                "signal_score": round(float(candidate.get("signal_score", 0.0)), 3),
                "asset_coverage": int(snapshot.get(candidate["asset"], 0)),
                "policy_coverage": int(snapshot.get(candidate["policy"], 0)),
                "suggested_action": candidate.get("suggested_action", ""),
            }
        )

    return {
        "asset_snapshot": snapshot,
        "modules": aggregate_by("module"),
        "assets": aggregate_by("asset"),
        "policies": aggregate_by("policy"),
        "next_fix_candidates": next_fix_candidates,
    }


WINDOW_BREACH_PLAYBOOK = {
    "early_window_q03_q04_share": {
        "issue_codes": ["Q03", "Q04"],
        "module": "writer",
        "asset": "scene_blueprints",
        "policy": "scene_realization_contracts",
        "window_label": "early",
        "summary": "早期窗口的 Q03/Q04 复合 breach 偏高。",
    },
    "mid_window_repeat_breach_rate": {
        "issue_codes": ["Q03"],
        "module": "writer",
        "asset": "scene_blueprints",
        "policy": "dialogue_realism_policy",
        "window_label": "mid",
        "summary": "中段窗口重复 breach 偏高。",
    },
    "mid_window_exposition_breach_rate": {
        "issue_codes": ["Q04"],
        "module": "writer",
        "asset": "scene_blueprints",
        "policy": "scene_realization_contracts",
        "window_label": "mid",
        "summary": "中段窗口解释比例 breach 偏高。",
    },
    "mid_window_detail_breach_rate": {
        "issue_codes": ["Q05"],
        "module": "writer",
        "asset": "sensory_grounding_policies",
        "policy": "scene_realization_contracts",
        "window_label": "mid",
        "summary": "中段窗口 detail breach 偏高。",
    },
    "late_window_q09_breach_rate": {
        "issue_codes": ["Q09"],
        "module": "planner",
        "asset": "chapter_tasks",
        "policy": "scene_realization_contracts",
        "window_label": "late",
        "summary": "后段窗口节奏/终局 breach 偏高。",
    },
    "late_window_detail_breach_rate": {
        "issue_codes": ["Q05"],
        "module": "writer",
        "asset": "sensory_grounding_policies",
        "policy": "scene_realization_contracts",
        "window_label": "late",
        "summary": "后段窗口 detail breach 偏高。",
    },
}


def build_window_breach_attribution(window_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    thresholds = dict(window_metrics.get("thresholds") or {})
    attributions: List[Dict[str, Any]] = []
    for metric_name, config in WINDOW_BREACH_PLAYBOOK.items():
        actual = float(window_metrics.get(metric_name, 0.0) or 0.0)
        threshold_key = f"{metric_name}_max"
        threshold = float(thresholds.get(threshold_key, 0.0) or 0.0)
        if actual <= threshold:
            continue
        attributions.append(
            {
                "metric": metric_name,
                "window_label": config["window_label"],
                "issue_codes": list(config["issue_codes"]),
                "actual": round(actual, 3),
                "threshold": round(threshold, 3),
                "module": config["module"],
                "asset": config["asset"],
                "policy": config["policy"],
                "summary": config["summary"],
            }
        )
    return attributions


def build_weakest_pack_diagnostic(
    *,
    world_metrics: Dict[str, Any],
    chapter_report_payloads: Sequence[Dict[str, Any]],
    pack_payload: Dict[str, Any],
) -> Dict[str, Any]:
    issue_mix = list(world_metrics.get("issue_mix", []))
    weakest_dimensions = list(world_metrics.get("issue_summary", {}).get("weakest_dimensions", []))
    attribution = build_attribution_diagnostics(
        issue_mix=issue_mix,
        weakest_dimensions=weakest_dimensions,
        pack_payload=pack_payload,
    )
    diagnostic = {
        "world_id": world_metrics.get("world_id", ""),
        "diagnostic_rank": world_metrics.get("diagnostic_rank"),
        "diagnostic_score": world_metrics.get("diagnostic_score", 0.0),
        "completion_ratio": world_metrics.get("completion_ratio"),
        "stop_reason": world_metrics.get("stop_reason"),
        "issue_category_distribution": issue_mix,
        "worst_chapters": build_worst_chapters(chapter_report_payloads),
        "attribution_map": {
            "modules": attribution["modules"],
            "assets": attribution["assets"],
            "policies": attribution["policies"],
        },
        "window_breach_attribution": build_window_breach_attribution(
            dict(world_metrics.get("content_quality_contract_window_metrics") or {})
        ),
        "asset_snapshot": attribution["asset_snapshot"],
        "next_fix_candidates": attribution["next_fix_candidates"],
    }
    diagnostic["recommended_strategy_bundles"] = infer_strategy_bundles_for_diagnostic(diagnostic)
    stop_condition = build_weakest_pack_stop_condition(
        world_metrics=world_metrics,
        issue_mix=issue_mix,
        weakest_dimensions=weakest_dimensions,
    )
    diagnostic["stop_condition"] = stop_condition
    diagnostic["polish_bundle"] = build_weakest_pack_polish_bundle(
        diagnostic=diagnostic,
        stop_condition=stop_condition,
    )
    return diagnostic


def build_weakest_pack_stop_condition(
    *,
    world_metrics: Dict[str, Any],
    issue_mix: Sequence[Dict[str, Any]],
    weakest_dimensions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    total_issue_count = sum(int(item.get("count", 0)) for item in issue_mix)
    checks = [
        {
            "name": "issue_mix_clean",
            "passed": total_issue_count == 0,
            "actual": int(total_issue_count),
            "target": 0,
        },
        {
            "name": "pass_rate",
            "passed": float(world_metrics.get("pass_rate", 0.0)) >= float(POLISH_STOP_THRESHOLDS["pass_rate_min"]),
            "actual": round(float(world_metrics.get("pass_rate", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["pass_rate_min"]),
        },
        {
            "name": "block_rate",
            "passed": float(world_metrics.get("block_rate", 0.0)) <= float(POLISH_STOP_THRESHOLDS["block_rate_max"]),
            "actual": round(float(world_metrics.get("block_rate", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["block_rate_max"]),
        },
        {
            "name": "long_route_quality",
            "passed": float(world_metrics.get("long_route_quality", 0.0)) >= float(POLISH_STOP_THRESHOLDS["long_route_quality_min"]),
            "actual": round(float(world_metrics.get("long_route_quality", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["long_route_quality_min"]),
        },
        {
            "name": "scene_detail_density",
            "passed": float(world_metrics.get("scene_detail_density", 0.0)) >= float(POLISH_STOP_THRESHOLDS["scene_detail_density_min"]),
            "actual": round(float(world_metrics.get("scene_detail_density", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["scene_detail_density_min"]),
        },
        {
            "name": "dialogue_distinctness",
            "passed": float(world_metrics.get("dialogue_distinctness", 0.0)) >= float(POLISH_STOP_THRESHOLDS["dialogue_distinctness_min"]),
            "actual": round(float(world_metrics.get("dialogue_distinctness", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["dialogue_distinctness_min"]),
        },
        {
            "name": "dialogue_ratio",
            "passed": float(world_metrics.get("dialogue_ratio", 0.0)) >= float(POLISH_STOP_THRESHOLDS["dialogue_ratio_min"]),
            "actual": round(float(world_metrics.get("dialogue_ratio", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["dialogue_ratio_min"]),
        },
        {
            "name": "diagnostic_score",
            "passed": float(world_metrics.get("diagnostic_score", 0.0)) <= float(POLISH_STOP_THRESHOLDS["diagnostic_score_max"]),
            "actual": round(float(world_metrics.get("diagnostic_score", 0.0)), 3),
            "target": float(POLISH_STOP_THRESHOLDS["diagnostic_score_max"]),
        },
    ]
    failed_checks = [item["name"] for item in checks if not item["passed"]]
    status = "stop_ready" if not failed_checks else "continue_polish"
    rationale = (
        "当前 weakest-pack polish 已达到可暂停观察状态。"
        if status == "stop_ready"
        else "当前 weakest-pack 仍有结构性或指标性缺口，建议继续 polish。"
    )
    return {
        "status": status,
        "failed_checks": failed_checks,
        "checks": checks,
        "thresholds": dict(POLISH_STOP_THRESHOLDS),
        "rationale": rationale,
        "weakest_dimensions": [str(item.get("name", "")) for item in weakest_dimensions],
    }


def build_weakest_pack_polish_bundle(
    *,
    diagnostic: Dict[str, Any],
    stop_condition: Dict[str, Any],
) -> Dict[str, Any]:
    next_fix_candidates = list(diagnostic.get("next_fix_candidates", []))
    asset_snapshot = dict(diagnostic.get("asset_snapshot", {}))
    target_dimensions = list(stop_condition.get("weakest_dimensions", []))
    bundle_items = [
        {
            "priority": int(item.get("priority", 0)),
            "module": item.get("module", ""),
            "asset": item.get("asset", ""),
            "policy": item.get("policy", ""),
            "signal_score": item.get("signal_score", 0.0),
            "suggested_action": item.get("suggested_action", ""),
        }
        for item in next_fix_candidates[:3]
    ]
    return {
        "bundle_status": stop_condition.get("status"),
        "world_id": diagnostic.get("world_id", ""),
        "target_dimensions": target_dimensions,
        "primary_module": bundle_items[0]["module"] if bundle_items else "",
        "primary_assets": [item["asset"] for item in bundle_items if item.get("asset")],
        "primary_policies": [item["policy"] for item in bundle_items if item.get("policy")],
        "bundle_items": bundle_items,
        "asset_snapshot": asset_snapshot,
        "recommended_action": (
            "pause_and_watch"
            if stop_condition.get("status") == "stop_ready"
            else "continue_targeted_polish"
        ),
    }


def build_weakest_pack_polish_program(weakest_pack_diagnostics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    diagnostics = [dict(item) for item in weakest_pack_diagnostics]
    stop_ready_worlds = [
        item.get("world_id", "")
        for item in diagnostics
        if dict(item.get("stop_condition", {})).get("status") == "stop_ready"
    ]
    continue_worlds = [
        item.get("world_id", "")
        for item in diagnostics
        if dict(item.get("stop_condition", {})).get("status") != "stop_ready"
    ]
    return {
        "status": "stop_ready" if not continue_worlds else "continue_polish",
        "stop_ready_worlds": stop_ready_worlds,
        "continue_worlds": continue_worlds,
        "recommended_action": "pause_lane_a_weakest_pack_polish" if not continue_worlds else "continue_lane_a_weakest_pack_polish",
        "bundles": [dict(item.get("polish_bundle", {})) for item in diagnostics],
    }


def build_longform_l1_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    longform_gate = dict(summary.get("longform_gate", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))

    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None

    if benchmark_mode != "longform_100":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_100",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_100_benchmark",
                "confirm_weakest_pack_polish_program",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not generated_at:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_generated_at_missing",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "benchmark_generated_at",
                "fresh_longform_100_benchmark",
            ],
            "generated_at": None,
            "evidence_age_hours": None,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if evidence_age_hours is not None and evidence_age_hours > LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_signoff_stale",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "fresh_longform_100_benchmark",
                "reconfirm_weakest_pack_polish_program",
            ],
            "generated_at": generated_at,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_benchmark_worldpack_all",
                "confirm_all_benchmark_worlds_covered",
            ],
            "generated_at": generated_at,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    failed_gate_worlds = list(longform_gate.get("failed_worlds", []))
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    blocking_worlds = sorted({world_id for world_id in failed_gate_worlds + continue_worlds if world_id})
    ready = not blocking_worlds and float(longform_gate.get("pass_rate", 0.0)) >= 1.0
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "reason": "longform_l1_signoff_ready" if ready else "longform_l1_signoff_blocked",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "longform_100_gate_pass_rate=1.0",
            "weakest_pack_polish_program.stop_ready",
            "no_blocking_worlds",
        ],
        "generated_at": generated_at,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_interactive_longform_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    interactive_gate = dict(summary.get("interactive_longform_gate", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_100_interactive":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_100_interactive",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_100_interactive_benchmark",
                "confirm_interactive_gate",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if evidence_age_hours is not None and evidence_age_hours > LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS:
        return {
            "status": "watch",
            "ready": False,
            "reason": "interactive_benchmark_signoff_stale",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "fresh_longform_100_interactive_benchmark",
                "reconfirm_interactive_gate",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "interactive_benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_interactive_benchmark_worldpack_all",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    failed_gate_worlds = list(interactive_gate.get("failed_worlds", []))
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    blocking_worlds = sorted({world_id for world_id in failed_gate_worlds + continue_worlds if world_id})
    ready = not blocking_worlds and float(interactive_gate.get("pass_rate", 0.0)) >= 1.0
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "reason": "interactive_longform_signoff_ready" if ready else "interactive_longform_signoff_blocked",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "interactive_longform_gate_pass_rate=1.0",
            "weakest_pack_polish_program.stop_ready",
            "interactive_no_blocking_worlds",
        ],
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_250_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    longform_250_evidence = dict(summary.get("longform_250_evidence", {}))
    review_sample_coverage_250 = dict(summary.get("review_sample_coverage_250", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_250":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_250",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_250_benchmark",
                "review_sample_coverage_250",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    evidence_failed_worlds = list(longform_250_evidence.get("failed_worlds", []))
    blocking_worlds = sorted({world_id for world_id in continue_worlds + evidence_failed_worlds if world_id})
    review_closeout_ready = bool(
        longform_250_evidence.get("review_sample_closeout_ready", review_sample_coverage_250.get("closeout_ready", False))
    )
    ready = (
        not blocking_worlds
        and float(longform_250_evidence.get("gate_pass_rate", 0.0) or 0.0) >= 1.0
        and review_closeout_ready
    )
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_250_signoff_ready" if ready else "longform_250_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "fresh_longform_250_benchmark",
            "review_sample_coverage_250",
            "weakest_pack_polish_program.stop_ready",
        ],
        "review_sample_closeout_ready": review_closeout_ready,
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_250_interactive_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    longform_250_evidence = dict(summary.get("longform_250_evidence", {}))
    interactive_gate = dict(summary.get("longform_250_interactive_gate", {}))
    review_sample_coverage_250 = dict(summary.get("review_sample_coverage_250", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_250_interactive":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_250_interactive",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_250_interactive_benchmark",
                "review_sample_coverage_250",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "interactive_benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_interactive_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    static_failed_worlds = list(longform_250_evidence.get("failed_worlds", []))
    interactive_failed_worlds = list(interactive_gate.get("failed_worlds", []))
    blocking_worlds = sorted({world_id for world_id in continue_worlds + static_failed_worlds + interactive_failed_worlds if world_id})
    review_closeout_ready = bool(
        longform_250_evidence.get("review_sample_closeout_ready", review_sample_coverage_250.get("closeout_ready", False))
    )
    ready = (
        not blocking_worlds
        and float(longform_250_evidence.get("gate_pass_rate", 0.0) or 0.0) >= 1.0
        and float(interactive_gate.get("pass_rate", 0.0) or 0.0) >= 1.0
        and review_closeout_ready
    )
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_250_interactive_signoff_ready" if ready else "longform_250_interactive_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "fresh_longform_250_interactive_benchmark",
            "longform_250_gate_pass_rate=1.0",
            "longform_250_interactive_gate_pass_rate=1.0",
            "review_sample_coverage_250",
            "weakest_pack_polish_program.stop_ready",
        ],
        "review_sample_closeout_ready": review_closeout_ready,
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_250_human_review_closeout(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    review_sample_coverage_250 = dict(summary.get("review_sample_coverage_250", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode not in {"longform_250", "longform_250_interactive"}:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_250_family",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_250_benchmark",
                "submit_human_review_samples_for_250_windows",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    human_closeout_ready = bool(review_sample_coverage_250.get("human_closeout_ready", False))
    human_unreviewed_targets = list(review_sample_coverage_250.get("human_unreviewed_targets", []))
    blocking_worlds = sorted(
        {
            str(item.get("world_id") or "")
            for item in human_unreviewed_targets
            if str(item.get("world_id") or "")
        }
    )
    return {
        "status": "ready" if human_closeout_ready else "watch",
        "ready": human_closeout_ready,
        "reason": "longform_250_human_review_closeout_ready" if human_closeout_ready else "longform_250_human_review_closeout_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if human_closeout_ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "review_sample_coverage_250.human_closeout_ready",
            "30_human_review_targets_closed",
        ],
        "human_closeout_status": review_sample_coverage_250.get("human_closeout_status"),
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_500_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    longform_500_evidence = dict(summary.get("longform_500_evidence", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_500":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_500",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_500_benchmark",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    failed_worlds = list(longform_500_evidence.get("failed_worlds", []))
    blocking_worlds = sorted({world_id for world_id in continue_worlds + failed_worlds if world_id})
    ready = not blocking_worlds and float(longform_500_evidence.get("gate_pass_rate", 0.0) or 0.0) >= 1.0
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_500_signoff_ready" if ready else "longform_500_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "fresh_longform_500_benchmark",
            "weakest_pack_polish_program.stop_ready",
        ],
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_500_human_review_closeout(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    review_sample_coverage_500 = dict(summary.get("review_sample_coverage_500", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode not in {"longform_500", "longform_500_interactive"}:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_500_family",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_500_benchmark",
                "submit_human_review_samples_for_500_windows",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    human_closeout_ready = bool(review_sample_coverage_500.get("human_closeout_ready", False))
    human_unreviewed_targets = list(review_sample_coverage_500.get("human_unreviewed_targets", []))
    blocking_worlds = sorted(
        {
            str(item.get("world_id") or "")
            for item in human_unreviewed_targets
            if str(item.get("world_id") or "")
        }
    )
    return {
        "status": "ready" if human_closeout_ready else "watch",
        "ready": human_closeout_ready,
        "reason": "longform_500_human_review_closeout_ready" if human_closeout_ready else "longform_500_human_review_closeout_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if human_closeout_ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "review_sample_coverage_500.human_closeout_ready",
            "30_human_review_targets_closed",
        ],
        "human_closeout_status": review_sample_coverage_500.get("human_closeout_status"),
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_500_ending_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    longform_500_evidence = dict(summary.get("longform_500_evidence", {}))
    review_sample_coverage_500 = dict(summary.get("review_sample_coverage_500", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode not in {"longform_500", "longform_500_interactive"}:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_500_family",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_500_benchmark",
                "review_sample_coverage_500.ending_window_human_closeout_ready",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    ready = bool(
        float(longform_500_evidence.get("gate_pass_rate", 0.0) or 0.0) >= 1.0
        and bool(review_sample_coverage_500.get("ending_window_human_closeout_ready", False))
    )
    blocking_worlds = [] if ready else sorted(
        {
            str(item.get("world_id") or "")
            for item in review_sample_coverage_500.get("human_unreviewed_targets", [])
            if str(item.get("world_id") or "") and str(item.get("window_label") or "") == str(review_sample_coverage_500.get("ending_window_label") or "")
        }
    )
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_500_ending_signoff_ready" if ready else "longform_500_ending_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "longform_500_signoff.ready",
            "review_sample_coverage_500.ending_window_human_closeout_ready",
            "series_ending_control_score=1.0",
        ],
        "ending_window_label": review_sample_coverage_500.get("ending_window_label"),
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_500_interactive_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    weakest_program = dict(summary.get("weakest_pack_polish_program", {}))
    longform_500_evidence = dict(summary.get("longform_500_evidence", {}))
    interactive_gate = dict(summary.get("longform_500_interactive_gate", {}))
    review_sample_coverage_500 = dict(summary.get("review_sample_coverage_500", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_500_interactive":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_500_interactive",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_500_interactive_benchmark",
                "review_sample_coverage_500",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "interactive_benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_interactive_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    continue_worlds = list(weakest_program.get("continue_worlds", []))
    static_failed_worlds = list(longform_500_evidence.get("failed_worlds", []))
    interactive_failed_worlds = list(interactive_gate.get("failed_worlds", []))
    blocking_worlds = sorted({world_id for world_id in continue_worlds + static_failed_worlds + interactive_failed_worlds if world_id})
    review_closeout_ready = bool(review_sample_coverage_500.get("human_closeout_ready", False))
    ending_closeout_ready = bool(review_sample_coverage_500.get("ending_window_human_closeout_ready", False))
    ready = (
        not blocking_worlds
        and float(longform_500_evidence.get("gate_pass_rate", 0.0) or 0.0) >= 1.0
        and float(interactive_gate.get("pass_rate", 0.0) or 0.0) >= 1.0
        and review_closeout_ready
        and ending_closeout_ready
    )
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_500_interactive_signoff_ready" if ready else "longform_500_interactive_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "fresh_longform_500_interactive_benchmark",
            "longform_500_gate_pass_rate=1.0",
            "longform_500_interactive_gate_pass_rate=1.0",
            "review_sample_coverage_500.human_closeout_ready",
            "review_sample_coverage_500.ending_window_human_closeout_ready",
            "weakest_pack_polish_program.stop_ready",
        ],
        "human_closeout_ready": review_closeout_ready,
        "ending_window_human_closeout_ready": ending_closeout_ready,
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_1000_feasibility(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    longform_1000_evidence = dict(summary.get("longform_1000_evidence", {}))
    longform_1000_summary = dict(summary.get("longform_1000_summary", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode not in {"longform_1000_diagnostics", "longform_1000_interactive"}:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_1000_family",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_1000_diagnostics_benchmark",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    failed_worlds = list(longform_1000_evidence.get("failed_worlds", []))
    promising = not failed_worlds and float(longform_1000_evidence.get("diagnostic_pass_rate", 0.0) or 0.0) >= 1.0
    return {
        "status": "promising" if promising else "watch",
        "ready": promising,
        "reason": "longform_1000_feasibility_promising" if promising else "longform_1000_feasibility_watch",
        "blocking_worlds": list(failed_worlds),
        "watch_worlds": [] if promising else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in failed_worlds],
        "required_evidence": [
            "series_memory_snapshot_integrity=1.0",
            "archive_retention_integrity=1.0",
            "continuation_state_retention_integrity=1.0",
            "late_stage_runtime_budget_score>=0.67",
        ],
        "diagnostic_pass_rate": longform_1000_summary.get("diagnostic_pass_rate"),
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_1000_readiness(summary: Dict[str, Any]) -> Dict[str, Any]:
    feasibility = dict(build_longform_1000_feasibility(summary))
    generated_at = str(summary.get("generated_at") or "")
    evidence_age_hours = feasibility.get("evidence_age_hours")
    if str(feasibility.get("status") or "watch") == "watch" and not feasibility.get("ready", False):
        return {
            "status": "watch",
            "ready": False,
            "reason": "longform_1000_readiness_watch",
            "blocking_worlds": list(feasibility.get("blocking_worlds", [])),
            "watch_worlds": list(feasibility.get("watch_worlds", [])),
            "required_evidence": [
                "longform_1000_feasibility.ready",
                "fresh_longform_1000_diagnostics_benchmark",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    return {
        "status": "ready",
        "ready": True,
        "reason": "longform_1000_readiness_ready",
        "blocking_worlds": [],
        "watch_worlds": [],
        "required_evidence": [
            "longform_1000_feasibility.ready",
            "diagnostic_pass_rate=1.0",
        ],
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_1000_human_review_closeout(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    review_sample_coverage_1000 = dict(summary.get("review_sample_coverage_1000", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode not in {"longform_1000_diagnostics", "longform_1000_interactive"}:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_1000_family",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_1000_diagnostics_benchmark",
                "submit_human_review_samples_for_1000_windows",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    human_closeout_ready = bool(review_sample_coverage_1000.get("human_closeout_ready", False))
    human_unreviewed_targets = list(review_sample_coverage_1000.get("human_unreviewed_targets", []))
    blocking_worlds = sorted(
        {
            str(item.get("world_id") or "")
            for item in human_unreviewed_targets
            if str(item.get("world_id") or "")
        }
    )
    return {
        "status": "ready" if human_closeout_ready else "watch",
        "ready": human_closeout_ready,
        "reason": "longform_1000_human_review_closeout_ready" if human_closeout_ready else "longform_1000_human_review_closeout_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if human_closeout_ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "review_sample_coverage_1000.human_closeout_ready",
            "6_human_review_targets_closed",
        ],
        "human_closeout_status": review_sample_coverage_1000.get("human_closeout_status"),
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_longform_1000_interactive_signoff(summary: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_mode = str(summary.get("benchmark_mode", "standard") or "standard")
    readiness = dict(summary.get("longform_1000_readiness") or build_longform_1000_readiness(summary))
    interactive_gate = dict(summary.get("longform_1000_interactive_gate", {}))
    weakest_packs = list(summary.get("weakest_packs", []))
    generated_at = str(summary.get("generated_at") or "")
    benchmark_scope_complete = bool(summary.get("benchmark_scope_complete", False))
    evidence_age_hours = None
    if generated_at:
        try:
            evidence_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            evidence_age_hours = round((datetime.now(timezone.utc) - evidence_time).total_seconds() / 3600.0, 3)
        except ValueError:
            evidence_age_hours = None
    if benchmark_mode != "longform_1000_interactive":
        return {
            "status": "watch",
            "ready": False,
            "reason": "benchmark_mode_not_longform_1000_interactive",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": [
                "run_longform_1000_interactive_benchmark",
                "longform_1000_readiness.ready",
            ],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    if not benchmark_scope_complete:
        return {
            "status": "watch",
            "ready": False,
            "reason": "interactive_benchmark_scope_incomplete",
            "blocking_worlds": [],
            "watch_worlds": [item.get("world_id", "") for item in weakest_packs],
            "required_evidence": ["run_interactive_benchmark_worldpack_all"],
            "generated_at": generated_at or None,
            "evidence_age_hours": evidence_age_hours,
            "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
        }
    failed_worlds = list(interactive_gate.get("failed_worlds", []))
    blocking_worlds = sorted({world_id for world_id in list(readiness.get("blocking_worlds", [])) + failed_worlds if world_id})
    ready = bool(readiness.get("ready", False)) and float(interactive_gate.get("pass_rate", 0.0) or 0.0) >= 1.0 and not blocking_worlds
    return {
        "status": "ready" if ready else "watch",
        "ready": ready,
        "reason": "longform_1000_interactive_signoff_ready" if ready else "longform_1000_interactive_signoff_watch",
        "blocking_worlds": blocking_worlds,
        "watch_worlds": [] if ready else [item.get("world_id", "") for item in weakest_packs if item.get("world_id") not in blocking_worlds],
        "required_evidence": [
            "longform_1000_readiness.ready",
            "fresh_longform_1000_interactive_benchmark",
            "longform_1000_interactive_gate_pass_rate=1.0",
        ],
        "generated_at": generated_at or None,
        "evidence_age_hours": evidence_age_hours,
        "freshness_threshold_hours": LONGFORM_L1_SIGNOFF_MAX_AGE_HOURS,
    }


def build_character_fidelity_remediation_framework(summary: Dict[str, Any]) -> Dict[str, Any]:
    framework = dict(summary.get("character_fidelity_remediation_framework", {}))
    worlds = list(framework.get("q06_worlds", []))
    if not worlds:
        return {
            "available": False,
            "status": "clear",
            "q06_world_count": 0,
            "top_worlds": [],
            "top_characters": [],
            "top_duties": [],
            "recommended_assets": [],
            "next_actions": ["character_fidelity_stable"],
        }

    character_counts: Dict[str, Dict[str, Any]] = {}
    duty_counts: Dict[str, Dict[str, Any]] = {}
    for world_payload in worlds:
        world_id = str(world_payload.get("world_id") or "")
        world_framework = dict(world_payload.get("framework") or {})
        for item in world_framework.get("top_character_hotspots", []):
            character_id = str(item.get("character_id") or "")
            if not character_id:
                continue
            entry = character_counts.setdefault(
                character_id,
                {"character_id": character_id, "world_ids": set(), "count": 0, "lowest_fidelity": 1.0},
            )
            entry["world_ids"].add(world_id)
            entry["count"] += int(item.get("count", 0) or 0)
            entry["lowest_fidelity"] = min(float(entry["lowest_fidelity"]), float(item.get("lowest_fidelity", 1.0) or 1.0))
        for item in world_framework.get("top_duty_hotspots", []):
            duty_type = str(item.get("duty_type") or "")
            if not duty_type:
                continue
            entry = duty_counts.setdefault(
                duty_type,
                {"duty_type": duty_type, "world_ids": set(), "count": 0, "lowest_fidelity": 1.0},
            )
            entry["world_ids"].add(world_id)
            entry["count"] += int(item.get("count", 0) or 0)
            entry["lowest_fidelity"] = min(float(entry["lowest_fidelity"]), float(item.get("lowest_fidelity", 1.0) or 1.0))

    ranked_worlds = sorted(
        worlds,
        key=lambda item: (
            -float(item.get("q06_issue_share", 0.0) or 0.0),
            float(item.get("character_fidelity", 1.0) or 1.0),
            str(item.get("world_id") or ""),
        ),
    )
    ranked_characters = sorted(
        character_counts.values(),
        key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["character_id"])),
    )
    ranked_duties = sorted(
        duty_counts.values(),
        key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["duty_type"])),
    )
    return {
        "available": True,
        "status": "active",
        "q06_world_count": len(worlds),
        "top_worlds": ranked_worlds[:5],
        "top_characters": [
            {
                "character_id": item["character_id"],
                "count": int(item["count"]),
                "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                "world_ids": sorted(item["world_ids"]),
            }
            for item in ranked_characters[:8]
        ],
        "top_duties": [
            {
                "duty_type": item["duty_type"],
                "count": int(item["count"]),
                "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                "world_ids": sorted(item["world_ids"]),
            }
            for item in ranked_duties[:8]
        ],
        "recommended_assets": list(framework.get("recommended_assets", [])),
        "next_actions": [
            "tighten_character_cards",
            "tighten_emotion_action_policies",
            "inspect_q06_priority_chapters",
        ],
    }


def build_character_fidelity_remediation_framework(summary: Dict[str, Any]) -> Dict[str, Any]:
    framework = dict(summary.get("character_fidelity_remediation_framework", {}))
    worlds = list(framework.get("q06_worlds", []))
    if not worlds:
        return {
            "available": False,
            "status": "clear",
            "q06_world_count": 0,
            "top_worlds": [],
            "top_characters": [],
            "top_duties": [],
            "recommended_assets": [],
            "next_actions": ["character_fidelity_stable"],
        }

    character_counts: Dict[str, Dict[str, Any]] = {}
    duty_counts: Dict[str, Dict[str, Any]] = {}
    for world_payload in worlds:
        world_id = str(world_payload.get("world_id") or "")
        world_framework = dict(world_payload.get("framework") or {})
        for item in world_framework.get("top_character_hotspots", []):
            character_id = str(item.get("character_id") or "")
            if not character_id:
                continue
            entry = character_counts.setdefault(
                character_id,
                {"character_id": character_id, "world_ids": set(), "count": 0, "lowest_fidelity": 1.0},
            )
            entry["world_ids"].add(world_id)
            entry["count"] += int(item.get("count", 0) or 0)
            entry["lowest_fidelity"] = min(float(entry["lowest_fidelity"]), float(item.get("lowest_fidelity", 1.0) or 1.0))
        for item in world_framework.get("top_duty_hotspots", []):
            duty_type = str(item.get("duty_type") or "")
            if not duty_type:
                continue
            entry = duty_counts.setdefault(
                duty_type,
                {"duty_type": duty_type, "world_ids": set(), "count": 0, "lowest_fidelity": 1.0},
            )
            entry["world_ids"].add(world_id)
            entry["count"] += int(item.get("count", 0) or 0)
            entry["lowest_fidelity"] = min(float(entry["lowest_fidelity"]), float(item.get("lowest_fidelity", 1.0) or 1.0))

    ranked_worlds = sorted(
        worlds,
        key=lambda item: (
            -float(item.get("q06_issue_share", 0.0) or 0.0),
            float(item.get("character_fidelity", 1.0) or 1.0),
            str(item.get("world_id") or ""),
        ),
    )
    ranked_characters = sorted(
        character_counts.values(),
        key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["character_id"])),
    )
    ranked_duties = sorted(
        duty_counts.values(),
        key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["duty_type"])),
    )
    return {
        "available": True,
        "status": "active",
        "q06_world_count": len(worlds),
        "top_worlds": ranked_worlds[:5],
        "top_characters": [
            {
                "character_id": item["character_id"],
                "count": int(item["count"]),
                "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                "world_ids": sorted(item["world_ids"]),
            }
            for item in ranked_characters[:8]
        ],
        "top_duties": [
            {
                "duty_type": item["duty_type"],
                "count": int(item["count"]),
                "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                "world_ids": sorted(item["world_ids"]),
            }
            for item in ranked_duties[:8]
        ],
        "recommended_assets": list(framework.get("recommended_assets", [])),
        "next_actions": [
            "tighten_character_cards",
            "tighten_emotion_action_policies",
            "inspect_q06_priority_chapters",
        ],
    }


def build_long_route_summary(worlds: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not worlds:
        return {
            "target_chapters": 0,
            "avg_completion_ratio": 0.0,
            "avg_mid_arc_drop": 0.0,
            "avg_repetition_score": 0.0,
            "avg_exposition_ratio": 0.0,
            "packs_reaching_target": [],
            "premature_ending_packs": [],
            "stop_reason_counts": {},
            "q03_q09_calibration": {},
        }
    target = int(worlds[0].get("route_longevity_target", 0))
    stop_reason_counts: Dict[str, int] = {}
    q03_recommendation_counts: Dict[str, int] = {}
    q09_recommendation_counts: Dict[str, int] = {}
    q03_correlations: List[float] = []
    q09_correlations: List[float] = []
    coverage_insufficient_worlds: List[str] = []
    for item in worlds:
        stop_reason = str(item.get("stop_reason", "unknown"))
        stop_reason_counts[stop_reason] = stop_reason_counts.get(stop_reason, 0) + 1
        calibration = dict(item.get("continuation_calibration") or {})
        if calibration:
            q03 = dict(calibration.get("q03") or {})
            q09 = dict(calibration.get("q09") or {})
            q03_recommendation = str(q03.get("recommendation") or "")
            q09_recommendation = str(q09.get("recommendation") or "")
            if q03_recommendation:
                q03_recommendation_counts[q03_recommendation] = q03_recommendation_counts.get(q03_recommendation, 0) + 1
            if q09_recommendation:
                q09_recommendation_counts[q09_recommendation] = q09_recommendation_counts.get(q09_recommendation, 0) + 1
            if q03.get("primary_correlation") is not None:
                q03_correlations.append(float(q03.get("primary_correlation") or 0.0))
            if q09.get("primary_correlation") is not None:
                q09_correlations.append(float(q09.get("primary_correlation") or 0.0))
            if str(calibration.get("coverage_status") or "") == "insufficient_coverage":
                coverage_insufficient_worlds.append(str(item.get("world_id") or "-"))
    return {
        "target_chapters": target,
        "avg_completion_ratio": round(_average([float(item.get("completion_ratio", 0.0)) for item in worlds]), 3),
        "avg_mid_arc_drop": round(_average([float(item.get("mid_arc_drop", 0.0)) for item in worlds]), 3),
        "avg_repetition_score": round(
            _average([float(item.get("avg_repetition_score", 0.0)) for item in worlds]),
            3,
        ),
        "avg_exposition_ratio": round(
            _average([float(item.get("avg_exposition_ratio", 0.0)) for item in worlds]),
            3,
        ),
        "packs_reaching_target": [
            item.get("world_id", "-")
            for item in worlds
            if int(item.get("route_longevity", 0)) >= target
        ],
        "premature_ending_packs": [
            item.get("world_id", "-")
            for item in worlds
            if bool(item.get("premature_ending", False))
        ],
        "stop_reason_counts": stop_reason_counts,
        "q03_q09_calibration": {
            "coverage_insufficient_worlds": coverage_insufficient_worlds,
            "q03_recommendation_counts": q03_recommendation_counts,
            "q09_recommendation_counts": q09_recommendation_counts,
            "avg_q03_primary_correlation": round(_average(q03_correlations), 3) if q03_correlations else 0.0,
            "avg_q09_primary_correlation": round(_average(q09_correlations), 3) if q09_correlations else 0.0,
        },
    }


def _interactive_issue_rate_average(
    worlds: Sequence[Dict[str, Any]],
    *,
    window_key: str,
    issue_code: str,
) -> float:
    values: List[float] = []
    for item in worlds:
        for scenario in item.get("post_steer_issue_window_summary", []) or []:
            window = dict(scenario.get(window_key) or {})
            rates = dict(window.get("issue_rates") or {})
            if issue_code in rates:
                values.append(float(rates.get(issue_code, 0.0) or 0.0))
    return round(_average(values), 3) if values else 0.0


def build_interactive_long_route_summary(
    worlds: Sequence[Dict[str, Any]],
    *,
    target_chapters: int,
    interactive_profile: str,
) -> Dict[str, Any]:
    if not worlds:
        return {
            "target_chapters": int(target_chapters),
            "interactive_profile": interactive_profile,
            "scenario_count": 0,
            "steering_recovery_rate": 0.0,
            "post_steer_route_survival": 0.0,
            "memory_consistency_after_steer": 0.0,
            "promise_reconciliation_after_steer": 0.0,
            "replan_stability_score": 0.0,
            "avg_short_window_issue_rates": {
                issue_code: 0.0 for issue_code in INTERACTIVE_LONG_ROUTE_ISSUE_CODES
            },
            "avg_long_window_issue_rates": {
                issue_code: 0.0 for issue_code in INTERACTIVE_LONG_ROUTE_ISSUE_CODES
            },
            "worlds_with_interactive_data": [],
        }
    interactive_worlds = [item for item in worlds if item.get("interactive_summary")]
    source_worlds = interactive_worlds or list(worlds)
    return {
        "target_chapters": int(target_chapters),
        "interactive_profile": interactive_profile,
        "scenario_count": int(
            round(
                _average(
                    [
                        float((item.get("interactive_summary") or {}).get("scenario_count", 0) or 0)
                        for item in source_worlds
                    ]
                )
            )
        ),
        "steering_recovery_rate": round(
            _average([float((item.get("interactive_summary") or {}).get("steering_recovery_rate", 0.0) or 0.0) for item in source_worlds]),
            3,
        ),
        "post_steer_route_survival": round(
            _average([float((item.get("interactive_summary") or {}).get("post_steer_route_survival", 0.0) or 0.0) for item in source_worlds]),
            3,
        ),
        "memory_consistency_after_steer": round(
            _average([float((item.get("interactive_summary") or {}).get("memory_consistency_after_steer", 0.0) or 0.0) for item in source_worlds]),
            3,
        ),
        "promise_reconciliation_after_steer": round(
            _average([float((item.get("interactive_summary") or {}).get("promise_reconciliation_after_steer", 0.0) or 0.0) for item in source_worlds]),
            3,
        ),
        "replan_stability_score": round(
            _average([float((item.get("interactive_summary") or {}).get("replan_stability_score", 0.0) or 0.0) for item in source_worlds]),
            3,
        ),
        "avg_short_window_issue_rates": {
            issue_code: _interactive_issue_rate_average(source_worlds, window_key="short_window", issue_code=issue_code)
            for issue_code in INTERACTIVE_LONG_ROUTE_ISSUE_CODES
        },
        "avg_long_window_issue_rates": {
            issue_code: _interactive_issue_rate_average(source_worlds, window_key="long_window", issue_code=issue_code)
            for issue_code in INTERACTIVE_LONG_ROUTE_ISSUE_CODES
        },
        "worlds_with_interactive_data": [
            str(item.get("world_id") or "-")
            for item in source_worlds
            if item.get("interactive_summary")
        ],
    }


def build_content_quality_contract_summary(worlds: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    enabled_worlds = [
        dict(item)
        for item in worlds
        if dict(item.get("content_quality_contract_window_metrics") or {}).get("enabled")
    ]
    if not enabled_worlds:
        return {}
    first_coverage = dict(enabled_worlds[0].get("content_quality_contract_coverage") or {})
    first_window_metrics = dict(enabled_worlds[0].get("content_quality_contract_window_metrics") or {})
    inferred_gate_enforced = bool(first_window_metrics.get("gate_enforced", first_coverage.get("gate_enforced", False)))
    inferred_diagnostic_enabled = (
        bool(first_window_metrics["diagnostic_enabled"])
        if "diagnostic_enabled" in first_window_metrics
        else (
            bool(first_coverage["diagnostic_enabled"])
            if "diagnostic_enabled" in first_coverage and first_coverage.get("applicable")
            else bool((first_window_metrics.get("band") or first_coverage.get("band")) and not inferred_gate_enforced)
        )
    )
    return {
        "band": first_window_metrics.get("band") or first_coverage.get("band"),
        "config_version": first_window_metrics.get("config_version") or first_coverage.get("config_version"),
        "gate_enforced": inferred_gate_enforced,
        "diagnostic_enabled": inferred_diagnostic_enabled,
        "applicable_world_count": len(enabled_worlds),
        "avg_early_window_q03_q04_share": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("early_window_q03_q04_share", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
        "avg_mid_window_repeat_breach_rate": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("mid_window_repeat_breach_rate", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
        "avg_mid_window_exposition_breach_rate": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("mid_window_exposition_breach_rate", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
        "avg_mid_window_detail_breach_rate": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("mid_window_detail_breach_rate", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
        "avg_late_window_q09_breach_rate": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("late_window_q09_breach_rate", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
        "avg_late_window_detail_breach_rate": round(
            _average(
                [
                    float((item.get("content_quality_contract_window_metrics") or {}).get("late_window_detail_breach_rate", 0.0) or 0.0)
                    for item in enabled_worlds
                ]
            ),
            3,
        ),
    }


def rank_weakest_packs(worlds: Iterable[Dict[str, Any]], *, limit: int = 3) -> List[Dict[str, Any]]:
    ranked = sorted(
        assign_diagnostic_ranks(worlds),
        key=lambda item: (
            int(item.get("diagnostic_rank", 0)),
            str(item.get("world_id", "")),
        ),
    )
    return [_pack_summary(item) for item in ranked[:limit]]


def rank_strongest_packs(worlds: Iterable[Dict[str, Any]], *, limit: int = 2) -> List[Dict[str, Any]]:
    ranked = sorted(
        assign_diagnostic_ranks(worlds),
        key=lambda item: (
            float(item.get("diagnostic_score", 0.0)),
            -float(item.get("pass_rate", 0.0)),
            float(item.get("block_rate", 0.0)),
            -float(item.get("long_route_quality", 0.0)),
            float(item.get("mid_arc_drop", 0.0)),
            -float(item.get("dialogue_distinctness", 0.0)),
            str(item.get("world_id", "")),
        ),
    )
    return [_pack_summary(item) for item in ranked[:limit]]


def benchmark_delta_report(current: Dict[str, object], baseline: Dict[str, object]) -> Dict[str, object]:
    current_worlds = {
        item["world_id"]: _enrich_world_metrics(item) for item in current.get("worlds", [])
    }
    baseline_worlds = {
        item["world_id"]: _enrich_world_metrics(item) for item in baseline.get("worlds", [])
    }
    world_deltas = {
        world_id: {f"{metric}_delta": _metric_delta(current_worlds.get(world_id, {}), baseline_worlds.get(world_id, {}), metric) for metric in DELTA_METRICS}
        for world_id in sorted(set(current_worlds) | set(baseline_worlds))
    }
    regressions: List[Dict[str, object]] = []
    for world_id, delta in world_deltas.items():
        if world_id not in current_worlds or world_id not in baseline_worlds:
            continue
        current_world = current_worlds.get(world_id, {})
        baseline_world = baseline_worlds.get(world_id, {})
        regressed_metrics = [
            metric_name.removesuffix("_delta")
            for metric_name, value in delta.items()
            if metric_name.removesuffix("_delta") in baseline_world
            if (metric_name in {"pass_rate_delta", "character_fidelity_delta", "causal_continuity_delta", "choice_distinctness_delta", "route_longevity_delta", "dialogue_ratio_delta", "scene_detail_density_delta", "voice_separation_score_delta", "emotion_action_specificity_delta"} and value < 0)
            or (metric_name == "prose_leak_rate_delta" and value > 0)
            or (metric_name == "block_rate_delta" and value > 0)
            or (metric_name == "long_route_quality_delta" and value < 0)
            or (metric_name == "mid_arc_drop_delta" and value > 0)
            or (metric_name == "dialogue_distinctness_delta" and value < 0)
            or (metric_name == "completion_ratio_delta" and value < 0)
            or (metric_name == "avg_overall_score_delta" and value < 0)
            or (metric_name == "mid_arc_pass_rate_delta" and value < 0)
            or (metric_name == "late_arc_pass_rate_delta" and value < 0)
            or (metric_name == "avg_repetition_score_delta" and value > 0)
            or (metric_name == "avg_exposition_ratio_delta" and value > 0)
            or (metric_name == "avg_hook_quality_delta" and value < 0)
            or (metric_name == "diagnostic_score_delta" and value > 0)
        ]
        if "choice_distinctness" in regressed_metrics and float(current_world.get("choice_distinctness", 0.0)) >= 0.8:
            regressed_metrics.remove("choice_distinctness")
        if "scene_detail_density" in regressed_metrics and abs(float(delta.get("scene_detail_density_delta", 0.0))) <= 0.002:
            regressed_metrics.remove("scene_detail_density")
        if "dialogue_ratio" in regressed_metrics and float(current_world.get("dialogue_ratio", 0.0)) >= 0.3 and abs(float(delta.get("dialogue_ratio_delta", 0.0))) <= 0.05:
            regressed_metrics.remove("dialogue_ratio")
        if "long_route_quality" in regressed_metrics and abs(float(delta.get("long_route_quality_delta", 0.0))) <= 0.01:
            regressed_metrics.remove("long_route_quality")
        if "avg_overall_score" in regressed_metrics and abs(float(delta.get("avg_overall_score_delta", 0.0))) <= 0.01:
            regressed_metrics.remove("avg_overall_score")
        if (
            "avg_repetition_score" in regressed_metrics
            and float(current_world.get("avg_repetition_score", 0.0)) <= 0.1
            and abs(float(delta.get("avg_repetition_score_delta", 0.0))) <= 0.06
        ):
            regressed_metrics.remove("avg_repetition_score")
        if (
            "avg_exposition_ratio" in regressed_metrics
            and float(current_world.get("avg_exposition_ratio", 0.0)) <= 0.5
            and abs(float(delta.get("avg_exposition_ratio_delta", 0.0))) <= 0.05
        ):
            regressed_metrics.remove("avg_exposition_ratio")
        if (
            "avg_hook_quality" in regressed_metrics
            and float(current_world.get("avg_hook_quality", 0.0)) >= 0.7
            and abs(float(delta.get("avg_hook_quality_delta", 0.0))) <= 0.05
        ):
            regressed_metrics.remove("avg_hook_quality")
        if (
            "diagnostic_score" in regressed_metrics
            and abs(float(delta.get("diagnostic_score_delta", 0.0))) <= 0.01
        ):
            regressed_metrics.remove("diagnostic_score")
        if regressed_metrics:
            regressions.append(
                {
                    "world_id": world_id,
                    "metrics": regressed_metrics,
                }
            )
    current_ranked = assign_diagnostic_ranks(current_worlds.values())
    baseline_ranked = assign_diagnostic_ranks(baseline_worlds.values())
    current_rank_map = {item["world_id"]: int(item.get("diagnostic_rank", 0)) for item in current_ranked}
    baseline_rank_map = {item["world_id"]: int(item.get("diagnostic_rank", 0)) for item in baseline_ranked}
    current_strongest = [item["world_id"] for item in rank_strongest_packs(current_worlds.values())]
    baseline_strongest = [item["world_id"] for item in rank_strongest_packs(baseline_worlds.values())]
    current_weakest = [item["world_id"] for item in rank_weakest_packs(current_worlds.values())]
    baseline_weakest = [item["world_id"] for item in rank_weakest_packs(baseline_worlds.values())]
    return {
        "cross_pack_pass_rate_delta": round(float(current.get("cross_pack_pass_rate", 0.0)) - float(baseline.get("cross_pack_pass_rate", 0.0)), 3),
        "world_deltas": world_deltas,
        "regressions": regressions,
        "ranking_changes": {
            "current_strongest": current_strongest,
            "baseline_strongest": baseline_strongest,
            "entered_strongest": [world_id for world_id in current_strongest if world_id not in baseline_strongest],
            "exited_strongest": [world_id for world_id in baseline_strongest if world_id not in current_strongest],
            "current_weakest": current_weakest,
            "baseline_weakest": baseline_weakest,
            "entered_weakest": [world_id for world_id in current_weakest if world_id not in baseline_weakest],
            "exited_weakest": [world_id for world_id in baseline_weakest if world_id not in current_weakest],
            "rank_deltas": {
                world_id: {
                    "current_rank": current_rank_map.get(world_id),
                    "baseline_rank": baseline_rank_map.get(world_id),
                    "diagnostic_rank_delta": (
                        current_rank_map.get(world_id) - baseline_rank_map.get(world_id)
                        if world_id in current_rank_map and world_id in baseline_rank_map
                        else None
                    ),
                }
                for world_id in sorted(set(current_rank_map) | set(baseline_rank_map))
            },
        },
    }


def rank_top_failing_packs(worlds: Iterable[Dict[str, Any]], *, limit: int = 3) -> List[Dict[str, Any]]:
    return rank_weakest_packs(worlds, limit=limit)


def render_benchmark_markdown(summary: Dict[str, Any]) -> str:
    weakest_packs = list(summary.get("weakest_packs", []))
    weakest_pack_diagnostics = list(summary.get("weakest_pack_diagnostics", []))
    weakest_pack_polish_program = dict(summary.get("weakest_pack_polish_program", {}))
    strategy_bundle_batch_validation = dict(summary.get("strategy_bundle_batch_validation") or {})
    strategy_bundle_batch_validation_history = dict(summary.get("strategy_bundle_batch_validation_history") or {})
    strategy_bundle_batch_validation_trend = dict(summary.get("strategy_bundle_batch_validation_trend") or {})
    longform_l1_signoff = dict(summary.get("longform_l1_signoff", {}))
    interactive_longform_signoff = dict(summary.get("interactive_longform_signoff", {}))
    longform_250_summary = dict(summary.get("longform_250_summary", {}))
    longform_250_signoff = dict(summary.get("longform_250_signoff", {}))
    longform_250_interactive_summary = dict(summary.get("longform_250_interactive_summary", {}))
    longform_250_interactive_signoff = dict(summary.get("longform_250_interactive_signoff", {}))
    longform_250_human_review_closeout = dict(summary.get("longform_250_human_review_closeout", {}))
    longform_500_summary = dict(summary.get("longform_500_summary", {}))
    longform_500_signoff = dict(summary.get("longform_500_signoff", {}))
    longform_500_human_review_closeout = dict(summary.get("longform_500_human_review_closeout", {}))
    longform_500_ending_signoff = dict(summary.get("longform_500_ending_signoff", {}))
    longform_500_interactive_summary = dict(summary.get("longform_500_interactive_summary", {}))
    longform_500_interactive_signoff = dict(summary.get("longform_500_interactive_signoff", {}))
    longform_1000_summary = dict(summary.get("longform_1000_summary", {}))
    longform_1000_readiness = dict(summary.get("longform_1000_readiness", {}))
    longform_1000_interactive_summary = dict(summary.get("longform_1000_interactive_summary", {}))
    longform_1000_interactive_signoff = dict(summary.get("longform_1000_interactive_signoff", {}))
    longform_1000_human_review_closeout = dict(summary.get("longform_1000_human_review_closeout", {}))
    longform_1000_feasibility = dict(summary.get("longform_1000_feasibility", {}))
    character_fidelity_remediation_framework = build_character_fidelity_remediation_framework(summary)
    review_sample_coverage_250 = dict(summary.get("review_sample_coverage_250", {}))
    review_sample_coverage_500 = dict(summary.get("review_sample_coverage_500", {}))
    review_sample_coverage_1000 = dict(summary.get("review_sample_coverage_1000", {}))
    strongest_packs = list(summary.get("strongest_packs", []))
    long_route_summary = dict(summary.get("long_route_summary", {}))
    interactive_long_route_summary = dict(summary.get("interactive_long_route_summary", {}))
    content_quality_contract_summary = dict(summary.get("content_quality_contract_summary", {}))
    generation_hard_constraint_summary = dict(summary.get("generation_hard_constraint_summary", {}))
    longform_summary = dict(summary.get("longform_summary", {}))
    longform_gate = dict(summary.get("longform_gate", {}))
    delta_summary = dict(summary.get("delta_summary", {}))
    phase_a_quality_gate = dict(summary.get("phase_a_quality_gate") or {})
    commercial_long_route_gate = dict(summary.get("commercial_long_route_gate") or {})
    benchmark_runtime_profile = dict(summary.get("benchmark_runtime_profile") or {})
    ranking_changes = dict(delta_summary.get("ranking_changes", {}))
    current_strongest = list(ranking_changes.get("current_strongest", [])) or [
        item.get("world_id", "-") for item in strongest_packs
    ]
    current_weakest = list(ranking_changes.get("current_weakest", [])) or [
        item.get("world_id", "-") for item in weakest_packs
    ]
    lines = [
        "# Cross-Pack Benchmark Summary",
        "",
        "## Overview",
        "- benchmark mode: %s" % (summary.get("benchmark_mode", "standard")),
        "- cross-pack pass rate: %.3f" % float(summary.get("cross_pack_pass_rate", 0.0)),
        "- benchmark delta: %+.3f" % float(delta_summary.get("cross_pack_pass_rate_delta", 0.0)),
        "- packs covered: %s" % len(summary.get("worlds", [])),
        "- regressions: %s" % len(delta_summary.get("regressions", [])),
        "",
        "## Benchmark Runtime Profile",
        "- profile: %s" % (benchmark_runtime_profile.get("acceptance_profile", summary.get("acceptance_profile", "full")) or "full"),
        "- total wall ms: %.3f" % float(benchmark_runtime_profile.get("total_wall_ms", 0.0) or 0.0),
        "- slowest worlds: %s"
        % (
            ", ".join(
                "%s %.3fms" % (
                    item.get("world_id", "-"),
                    float(item.get("world_total_ms", 0.0) or 0.0),
                )
                for item in list(benchmark_runtime_profile.get("slowest_worlds") or [])
            )
            or "-"
        ),
        "- stage totals: %s"
        % (
            ", ".join(
                "%s=%.3fms" % (key, float(value or 0.0))
                for key, value in dict(benchmark_runtime_profile.get("stage_totals_ms") or {}).items()
                if key in {"simulation", "generation_runtime", "quality_pass", "lint", "evaluation", "world_total"}
            )
            or "-"
        ),
        "- quality-pass stage actions: %s"
        % (
            ", ".join(
                "%s=%s" % (key, value)
                for key, value in dict(benchmark_runtime_profile.get("quality_pass_stage_action_counts") or {}).items()
            )
            or "-"
        ),
        "- fast gate: %s"
        % (
            "selected %s / nightly required %s"
            % (
                ", ".join(dict(benchmark_runtime_profile.get("fast_gate") or {}).get("selected_world_ids", [])) or "-",
                "yes" if dict(benchmark_runtime_profile.get("fast_gate") or {}).get("nightly_full_gate_required") else "no",
            )
        ),
        "",
        "## Phase A Quality Gate",
        "- status: %s" % ("pass" if phase_a_quality_gate.get("ok") else "blocked"),
        "- config version: %s" % (phase_a_quality_gate.get("config_version", "-") or "-"),
        "- failed checks: %s" % (", ".join(phase_a_quality_gate.get("failed_checks", [])) or "none"),
        "- weakest packs evaluated: %s" % (", ".join(phase_a_quality_gate.get("evaluated_weakest_world_ids", [])) or "-"),
        "",
        "## Commercial Long-Route 50 Gate",
        "- applicable: %s" % ("yes" if commercial_long_route_gate.get("applicable") else "no"),
        "- status: %s" % ("pass" if commercial_long_route_gate.get("ok", True) else "blocked"),
        "- failed checks: %s" % (", ".join(commercial_long_route_gate.get("failed_checks", [])) or "none"),
        "- evidence command: python -m src.narrativeos.benchmark.runner --worldpack all --database-url sqlite:///artifacts/commercial_long_route_50.db --benchmark-mode long_route --max-chapters 50 --markdown-out artifacts/commercial_long_route_50.md",
        "",
        "### Commercial Weakest-Pack Evidence",
    ]
    commercial_weakest = weakest_packs[:3]
    if commercial_weakest:
        for item in commercial_weakest:
            focus_mix = [
                issue
                for issue in list(item.get("issue_mix") or [])
                if str(issue.get("issue_code") or "") in {"Q03", "Q04", "Q05", "Q09"}
            ]
            lines.extend(
                [
                    "- %s: long-route %.3f · mid-arc drop %.3f · completion %.3f · stop %s" % (
                        item.get("world_id", "-"),
                        float(item.get("long_route_quality", 0.0) or 0.0),
                        float(item.get("mid_arc_drop", 0.0) or 0.0),
                        float(item.get("completion_ratio", 0.0) or 0.0),
                        item.get("stop_reason", "-") or "-",
                    ),
                    "  focus issues: %s"
                    % (
                        ", ".join(
                            "%s x%s (%.3f)"
                            % (
                                issue.get("issue_code", "-"),
                                int(issue.get("count", 0) or 0),
                                float(issue.get("share", 0.0) or 0.0),
                            )
                            for issue in focus_mix
                        )
                        or "clean"
                    ),
                ]
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
        "## Strongest Packs",
        ]
    )
    if strongest_packs:
        for item in strongest_packs:
            lines.extend(
                [
                    "- %s: pass %.3f · long-route %.3f · mid-arc drop %.3f · dialogue distinctness %.3f · diagnostic %.3f" % (
                        item.get("world_id", "-"),
                        float(item.get("pass_rate", 0.0)),
                        float(item.get("long_route_quality", 0.0)),
                        float(item.get("mid_arc_drop", 0.0)),
                        float(item.get("dialogue_distinctness", 0.0)),
                        float(item.get("diagnostic_score", 0.0)),
                    ),
                    "  issue mix: %s"
                    % (
                        ", ".join(
                            "%s x%s (%.3f)"
                            % (
                                issue.get("issue_code", "-"),
                                int(issue.get("count", 0)),
                                float(issue.get("share", 0.0)),
                            )
                            for issue in item.get("issue_mix", [])
                        )
                        or "clean"
                    ),
                ]
            )
    else:
        lines.append("- none")
    if long_route_summary:
        calibration = dict(long_route_summary.get("q03_q09_calibration") or {})
        lines.extend(
            [
                "",
                "## Long-Route Summary",
                "- target chapters: %s" % long_route_summary.get("target_chapters", 0),
                "- avg completion ratio: %.3f" % float(long_route_summary.get("avg_completion_ratio", 0.0)),
                "- avg mid-arc drop: %.3f" % float(long_route_summary.get("avg_mid_arc_drop", 0.0)),
                "- avg repetition score: %.3f" % float(long_route_summary.get("avg_repetition_score", 0.0)),
                "- avg exposition ratio: %.3f" % float(long_route_summary.get("avg_exposition_ratio", 0.0)),
                "- packs reaching target: %s"
                % (", ".join(long_route_summary.get("packs_reaching_target", [])) or "-"),
                "- premature ending packs: %s"
                % (", ".join(long_route_summary.get("premature_ending_packs", [])) or "-"),
                "- stop reasons: %s"
                % (
                    ", ".join(
                        "%s=%s" % (key, value)
                        for key, value in sorted(long_route_summary.get("stop_reason_counts", {}).items())
                    )
                    or "-"
                ),
            ]
        )
        if calibration:
            lines.extend(
                [
                    "- q03 calibration recommendations: %s"
                    % (
                        ", ".join(
                            "%s=%s" % (key, value)
                            for key, value in sorted(dict(calibration.get("q03_recommendation_counts") or {}).items())
                        )
                        or "-"
                    ),
                    "- q09 calibration recommendations: %s"
                    % (
                        ", ".join(
                            "%s=%s" % (key, value)
                            for key, value in sorted(dict(calibration.get("q09_recommendation_counts") or {}).items())
                        )
                        or "-"
                    ),
                    "- avg q03 primary correlation: %.3f" % float(calibration.get("avg_q03_primary_correlation", 0.0)),
                    "- avg q09 primary correlation: %.3f" % float(calibration.get("avg_q09_primary_correlation", 0.0)),
                    "- calibration coverage insufficient worlds: %s"
                    % (", ".join(calibration.get("coverage_insufficient_worlds", [])) or "-"),
                ]
            )
    if interactive_long_route_summary:
        lines.extend(
            [
                "",
                "## Interactive Long-Route Summary",
                "- profile: %s" % (interactive_long_route_summary.get("interactive_profile", summary.get("interactive_profile", "-")) or "-"),
                "- target chapters: %s" % interactive_long_route_summary.get("target_chapters", summary.get("chapter_budget", 0)),
                "- scenario count: %s" % interactive_long_route_summary.get("scenario_count", 0),
                "- steering recovery rate: %.3f" % float(interactive_long_route_summary.get("steering_recovery_rate", 0.0)),
                "- post-steer route survival: %.3f" % float(interactive_long_route_summary.get("post_steer_route_survival", 0.0)),
                "- memory consistency after steer: %.3f" % float(interactive_long_route_summary.get("memory_consistency_after_steer", 0.0)),
                "- promise reconciliation after steer: %.3f" % float(interactive_long_route_summary.get("promise_reconciliation_after_steer", 0.0)),
                "- replan stability score: %.3f" % float(interactive_long_route_summary.get("replan_stability_score", 0.0)),
                "- avg short-window issue rates: %s"
                % (
                    ", ".join(
                        "%s=%.3f" % (issue_code, float(rate))
                        for issue_code, rate in dict(interactive_long_route_summary.get("avg_short_window_issue_rates") or {}).items()
                    )
                    or "-"
                ),
                "- avg long-window issue rates: %s"
                % (
                    ", ".join(
                        "%s=%.3f" % (issue_code, float(rate))
                        for issue_code, rate in dict(interactive_long_route_summary.get("avg_long_window_issue_rates") or {}).items()
                    )
                    or "-"
                ),
                "- worlds with interactive data: %s"
                % (", ".join(interactive_long_route_summary.get("worlds_with_interactive_data", [])) or "-"),
            ]
        )
        lines.extend(["", "## Post-Steer Issue Windows"])
        post_steer_worlds = [
            item for item in summary.get("worlds", [])
            if item.get("post_steer_issue_window_summary")
        ]
        if not post_steer_worlds:
            lines.append("- none")
        for item in post_steer_worlds:
            lines.append("- %s" % (item.get("world_id", "-") or "-"))
            for scenario in item.get("post_steer_issue_window_summary", [])[:5]:
                short_window = dict(scenario.get("short_window") or {})
                long_window = dict(scenario.get("long_window") or {})
                short_rates = ", ".join(
                    "%s=%.3f" % (issue_code, float(rate))
                    for issue_code, rate in dict(short_window.get("issue_rates") or {}).items()
                ) or "-"
                long_rates = ", ".join(
                    "%s=%.3f" % (issue_code, float(rate))
                    for issue_code, rate in dict(long_window.get("issue_rates") or {}).items()
                ) or "-"
                lines.append(
                    "  chapter %s %s · short[%s] · long[%s]"
                    % (
                        scenario.get("chapter_index", 0),
                        scenario.get("scenario_kind", "-"),
                        short_rates,
                        long_rates,
                    )
                )
    if content_quality_contract_summary:
        lines.extend(
            [
                "",
                "## Content Quality Contract Summary",
                "- band: %s" % (content_quality_contract_summary.get("band", "-") or "-"),
                "- config version: %s" % (content_quality_contract_summary.get("config_version", "-") or "-"),
                "- gate enforced: %s" % ("yes" if content_quality_contract_summary.get("gate_enforced") else "no"),
                "- diagnostic enabled: %s" % ("yes" if content_quality_contract_summary.get("diagnostic_enabled") else "no"),
                "- applicable worlds: %s" % content_quality_contract_summary.get("applicable_world_count", 0),
                "- avg early-window Q03/Q04 share: %.3f" % float(content_quality_contract_summary.get("avg_early_window_q03_q04_share", 0.0)),
                "- avg mid-window repeat breach rate: %.3f" % float(content_quality_contract_summary.get("avg_mid_window_repeat_breach_rate", 0.0)),
                "- avg mid-window exposition breach rate: %.3f" % float(content_quality_contract_summary.get("avg_mid_window_exposition_breach_rate", 0.0)),
                "- avg mid-window detail breach rate: %.3f" % float(content_quality_contract_summary.get("avg_mid_window_detail_breach_rate", 0.0)),
                "- avg late-window Q09 breach rate: %.3f" % float(content_quality_contract_summary.get("avg_late_window_q09_breach_rate", 0.0)),
                "- avg late-window detail breach rate: %.3f" % float(content_quality_contract_summary.get("avg_late_window_detail_breach_rate", 0.0)),
            ]
        )
    if generation_hard_constraint_summary:
        violation_lines = [
            "- `%s`: %s (share %.3f)"
            % (item.get("rule_id", "-"), int(item.get("count", 0) or 0), float(item.get("share", 0.0) or 0.0))
            for item in list(generation_hard_constraint_summary.get("violation_mix") or [])[:8]
        ] or ["- none"]
        scene_card_audit = dict(generation_hard_constraint_summary.get("scene_card_visible_text_audit") or {})
        scene_card_lines = [
            "- `%s`: %s" % (item.get("rule_id", "-"), int(item.get("count", 0) or 0))
            for item in list(scene_card_audit.get("failed_rule_mix") or [])[:6]
        ] or ["- none"]
        lines.extend(
            [
                "",
                "## Generation Hard Constraint Summary",
                "- chapters: %s" % generation_hard_constraint_summary.get("chapter_count", 0),
                "- hard fail count: %s" % generation_hard_constraint_summary.get("hard_fail_count", 0),
                "- hard fail rate: %.3f" % float(generation_hard_constraint_summary.get("hard_fail_rate", 0.0)),
                "- repair attempts: %s" % generation_hard_constraint_summary.get("repair_attempt_count", 0),
                "- repair success rate: %.3f" % float(generation_hard_constraint_summary.get("repair_success_rate", 0.0)),
                "- scene-card visible text violations: %s" % int(scene_card_audit.get("violation_count", 0) or 0),
                "",
                "### Hard Constraint Violation Mix",
                *violation_lines,
                "",
                "### Scene-Card Visible Text Audit",
                *scene_card_lines,
            ]
        )
    if longform_gate:
        calibration = dict(longform_gate.get("calibration") or {})
        observed = dict(calibration.get("observed_metrics") or {})
        recommended_thresholds = dict(calibration.get("recommended_thresholds") or {})
        lines.extend(
            [
                "",
                "## Longform 100 Gate",
                "- pass rate: %.3f" % float(longform_gate.get("pass_rate", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_gate.get("failed_worlds", [])) or "-"),
                "- avg q09 incidence: %.3f" % float(longform_summary.get("q09_incidence_rate", 0.0)),
                "- avg promise unresolved: %.3f" % float(longform_summary.get("promise_unresolved_rate", 0.0)),
                "- avg arc task repeat: %.3f" % float(longform_summary.get("arc_task_repeat_rate", 0.0)),
            ]
        )
        if observed:
            lines.extend(
                [
                    "  observed completion ratio p75/max: %.3f / %.3f"
                    % (
                        float(dict(observed.get("completion_ratio") or {}).get("p75", 0.0)),
                        float(dict(observed.get("completion_ratio") or {}).get("max", 0.0)),
                    ),
                    "  observed q09 incidence p75/max: %.3f / %.3f"
                    % (
                        float(dict(observed.get("q09_incidence_rate") or {}).get("p75", 0.0)),
                        float(dict(observed.get("q09_incidence_rate") or {}).get("max", 0.0)),
                    ),
                    "  observed arc repeat p75/max: %.3f / %.3f"
                    % (
                        float(dict(observed.get("arc_task_repeat_rate") or {}).get("p75", 0.0)),
                        float(dict(observed.get("arc_task_repeat_rate") or {}).get("max", 0.0)),
                    ),
                ]
            )
    if longform_250_summary:
        lines.extend(
            [
                "",
                "## Longform 250 Evidence",
                "- gate pass rate: %.3f" % float(longform_250_summary.get("gate_pass_rate", 0.0)),
                "- volume boundary survival: %.3f" % float(longform_250_summary.get("volume_boundary_survival", 0.0)),
                "- memory recall coverage: %.3f" % float(longform_250_summary.get("memory_recall_coverage", 0.0)),
                "- replan stability score: %.3f" % float(longform_250_summary.get("replan_stability_score", 0.0)),
                "- volume snapshot integrity: %.3f" % float(longform_250_summary.get("volume_snapshot_integrity", 0.0)),
                "- mid-volume pass: %.3f" % float(longform_250_summary.get("mid_volume_pass_rate", 0.0)),
                "- late-volume pass: %.3f" % float(longform_250_summary.get("late_volume_pass_rate", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_250_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_250_interactive_summary:
        lines.extend(
            [
                "",
                "## Longform 250 Interactive Gate",
                "- gate pass rate: %.3f" % float(longform_250_interactive_summary.get("gate_pass_rate", 0.0)),
                "- steering recovery rate: %.3f" % float(longform_250_interactive_summary.get("steering_recovery_rate", 0.0)),
                "- post-steer route survival: %.3f" % float(longform_250_interactive_summary.get("post_steer_route_survival", 0.0)),
                "- memory consistency after steer: %.3f" % float(longform_250_interactive_summary.get("memory_consistency_after_steer", 0.0)),
                "- promise reconciliation after steer: %.3f" % float(longform_250_interactive_summary.get("promise_reconciliation_after_steer", 0.0)),
                "- replan stability score: %.3f" % float(longform_250_interactive_summary.get("replan_stability_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_250_interactive_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_500_summary:
        lines.extend(
            [
                "",
                "## Longform 500 Evidence",
                "- gate pass rate: %.3f" % float(longform_500_summary.get("gate_pass_rate", 0.0)),
                "- series boundary survival: %.3f" % float(longform_500_summary.get("series_boundary_survival", 0.0)),
                "- series memory snapshot integrity: %.3f" % float(longform_500_summary.get("series_memory_snapshot_integrity", 0.0)),
                "- memory recall coverage: %.3f" % float(longform_500_summary.get("memory_recall_coverage", 0.0)),
                "- replan stability score: %.3f" % float(longform_500_summary.get("replan_stability_score", 0.0)),
                "- late-series pass: %.3f" % float(longform_500_summary.get("late_series_pass_rate", 0.0)),
                "- series ending control score: %.3f" % float(longform_500_summary.get("series_ending_control_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_500_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_500_interactive_summary:
        lines.extend(
            [
                "",
                "## Longform 500 Interactive Gate",
                "- gate pass rate: %.3f" % float(longform_500_interactive_summary.get("gate_pass_rate", 0.0)),
                "- steering recovery rate: %.3f" % float(longform_500_interactive_summary.get("steering_recovery_rate", 0.0)),
                "- post-steer route survival: %.3f" % float(longform_500_interactive_summary.get("post_steer_route_survival", 0.0)),
                "- memory consistency after steer: %.3f" % float(longform_500_interactive_summary.get("memory_consistency_after_steer", 0.0)),
                "- promise reconciliation after steer: %.3f" % float(longform_500_interactive_summary.get("promise_reconciliation_after_steer", 0.0)),
                "- replan stability score: %.3f" % float(longform_500_interactive_summary.get("replan_stability_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_500_interactive_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_1000_summary:
        lines.extend(
            [
                "",
                "## Longform 1000 Diagnostics",
                "- diagnostic pass rate: %.3f" % float(longform_1000_summary.get("diagnostic_pass_rate", 0.0)),
                "- series boundary survival: %.3f" % float(longform_1000_summary.get("series_boundary_survival", 0.0)),
                "- series memory snapshot integrity: %.3f" % float(longform_1000_summary.get("series_memory_snapshot_integrity", 0.0)),
                "- series snapshot count / target: %.3f / %.3f"
                % (
                    float(longform_1000_summary.get("series_snapshot_count", 0.0)),
                    float(longform_1000_summary.get("retained_series_snapshot_target", 0.0)),
                ),
                "- archive retention integrity: %.3f" % float(longform_1000_summary.get("archive_retention_integrity", 0.0)),
                "- timeline retention integrity: %.3f" % float(longform_1000_summary.get("timeline_retention_integrity", 0.0)),
                "- continuation-state retention integrity: %.3f" % float(longform_1000_summary.get("continuation_state_retention_integrity", 0.0)),
                "- late-stage runtime p95 ms: %.3f" % float(longform_1000_summary.get("late_stage_runtime_p95_ms", 0.0)),
                "- late-stage runtime budget score: %.3f" % float(longform_1000_summary.get("late_stage_runtime_budget_score", 0.0)),
                "- series ending control score: %.3f" % float(longform_1000_summary.get("series_ending_control_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_1000_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if character_fidelity_remediation_framework.get("available"):
        lines.extend(
            [
                "",
                "## Q06 Character Fidelity Framework",
                "- q06 worlds: %s" % int(character_fidelity_remediation_framework.get("q06_world_count", 0) or 0),
                "- top worlds: %s"
                % (
                    ", ".join(
                        "%s(share=%.3f,fidelity=%.3f)"
                        % (
                            item.get("world_id", "-"),
                            float(item.get("q06_issue_share", 0.0)),
                            float(item.get("character_fidelity", 0.0)),
                        )
                        for item in character_fidelity_remediation_framework.get("top_worlds", [])
                    )
                    or "-"
                ),
                "- top characters: %s"
                % (
                    ", ".join(
                        "%s x%s"
                        % (
                            item.get("character_id", "-"),
                            int(item.get("count", 0)),
                        )
                        for item in character_fidelity_remediation_framework.get("top_characters", [])
                    )
                    or "-"
                ),
                "- top duties: %s"
                % (
                    ", ".join(
                        "%s x%s"
                        % (
                            item.get("duty_type", "-"),
                            int(item.get("count", 0)),
                        )
                        for item in character_fidelity_remediation_framework.get("top_duties", [])
                    )
                    or "-"
                ),
                "- recommended assets: %s" % (", ".join(character_fidelity_remediation_framework.get("recommended_assets", [])) or "-"),
            ]
        )
    if review_sample_coverage_250:
        lines.extend(
            [
                "",
                "## Longform 250 Review Sampling",
                "- closeout status: %s" % (review_sample_coverage_250.get("closeout_status", "-") or "-"),
                "- closeout ready: %s" % ("yes" if review_sample_coverage_250.get("closeout_ready") else "no"),
                "- reviewed worlds: %s" % int(review_sample_coverage_250.get("reviewed_world_count", 0) or 0),
                "- human-reviewed worlds: %s" % int(review_sample_coverage_250.get("human_reviewed_world_count", 0) or 0),
                "- auto-seeded worlds: %s" % int(review_sample_coverage_250.get("auto_seeded_world_count", 0) or 0),
                "- human closeout status: %s" % (review_sample_coverage_250.get("human_closeout_status", "-") or "-"),
                "- human closeout ready: %s" % ("yes" if review_sample_coverage_250.get("human_closeout_ready") else "no"),
                "- executed targets: %s/%s"
                % (
                    int(review_sample_coverage_250.get("executed_target_count", 0) or 0),
                    int(review_sample_coverage_250.get("planned_target_count", 0) or 0),
                ),
                "- unreviewed targets: %s" % len(review_sample_coverage_250.get("unreviewed_targets", [])),
                "- human-unreviewed targets: %s" % len(review_sample_coverage_250.get("human_unreviewed_targets", [])),
                "- window coverage: %s"
                % (
                    " / ".join(
                        "%s=%s/%s (human %s · auto %s)"
                        % (
                            label,
                            int(dict(payload).get("reviewed_count", 0)),
                            int(dict(payload).get("target_count", 0)),
                            int(dict(payload).get("human_reviewed_count", 0)),
                            int(dict(payload).get("auto_seeded_count", 0)),
                        )
                        for label, payload in dict(review_sample_coverage_250.get("window_coverage", {})).items()
                    )
                    or "-"
                ),
            ]
        )
    if review_sample_coverage_500:
        lines.extend(
            [
                "",
                "## Longform 500 Review Sampling",
                "- closeout status: %s" % (review_sample_coverage_500.get("closeout_status", "-") or "-"),
                "- closeout ready: %s" % ("yes" if review_sample_coverage_500.get("closeout_ready") else "no"),
                "- human closeout status: %s" % (review_sample_coverage_500.get("human_closeout_status", "-") or "-"),
                "- human closeout ready: %s" % ("yes" if review_sample_coverage_500.get("human_closeout_ready") else "no"),
                "- ending window: %s" % (review_sample_coverage_500.get("ending_window_label", "-") or "-"),
                "- ending window human reviewed: %s/%s"
                % (
                    int(review_sample_coverage_500.get("ending_window_human_reviewed_count", 0) or 0),
                    int(review_sample_coverage_500.get("ending_window_target_count", 0) or 0),
                ),
                "- human-unreviewed targets: %s" % len(review_sample_coverage_500.get("human_unreviewed_targets", [])),
            ]
        )
    lines.extend(["", "## Weakest Packs"])
    if weakest_packs:
        for item in weakest_packs:
            lines.extend(
                [
                    "- %s: pass %.3f · long-route %.3f · mid-arc drop %.3f · dialogue distinctness %.3f · diagnostic %.3f" % (
                        item.get("world_id", "-"),
                        float(item.get("pass_rate", 0.0)),
                        float(item.get("long_route_quality", 0.0)),
                        float(item.get("mid_arc_drop", 0.0)),
                        float(item.get("dialogue_distinctness", 0.0)),
                        float(item.get("diagnostic_score", 0.0)),
                    ),
                    "  completion ratio: %s · stop reason: %s"
                    % (
                        (
                            "%.3f" % float(item.get("completion_ratio", 0.0))
                            if item.get("completion_ratio") is not None
                            else "-"
                        ),
                        item.get("stop_reason", "-") or "-",
                    ),
                    "  issue mix: %s"
                    % (
                        ", ".join(
                            "%s x%s (%.3f)"
                            % (
                                issue.get("issue_code", "-"),
                                int(issue.get("count", 0)),
                                float(issue.get("share", 0.0)),
                            )
                            for issue in item.get("issue_mix", [])
                        )
                        or "clean"
                    ),
                    "  weakest dimensions: %s"
                    % (
                        " / ".join(
                            "%s=%.3f"
                            % (
                                dimension.get("name", "-"),
                                float(dimension.get("value", 0.0)),
                            )
                            for dimension in item.get("weakest_dimensions", [])
                        )
                        or "-"
                    ),
                    "  recommended target: %s" % (item.get("recommended_target", "-") or "-"),
                ]
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Weakest Pack Diagnostics"])
    if weakest_pack_diagnostics:
        for item in weakest_pack_diagnostics:
            lines.append(
                "- %s: diagnostic rank %s · diagnostic %.3f · completion %s · stop %s"
                % (
                    item.get("world_id", "-"),
                    item.get("diagnostic_rank", "-"),
                    float(item.get("diagnostic_score", 0.0)),
                    (
                        "%.3f" % float(item.get("completion_ratio", 0.0))
                        if item.get("completion_ratio") is not None
                        else "-"
                    ),
                    item.get("stop_reason", "-") or "-",
                )
            )
            worst_chapters = list(item.get("worst_chapters", []))
            if worst_chapters:
                lines.append(
                    "  worst chapters: %s"
                    % (
                        " | ".join(
                            "%s %s %.3f [%s]"
                            % (
                                chapter.get("chapter_id", "-"),
                                chapter.get("decision", "-"),
                                float(chapter.get("overall_score", 0.0)),
                                ", ".join(chapter.get("issue_codes", [])) or "clean",
                            )
                            for chapter in worst_chapters[:2]
                        )
                    )
                )
            attribution_map = dict(item.get("attribution_map", {}))
            lines.append(
                "  module / asset / policy: %s / %s / %s"
                % (
                    (attribution_map.get("modules", [{}])[0] or {}).get("module", "-")
                    if attribution_map.get("modules")
                    else "-",
                    (attribution_map.get("assets", [{}])[0] or {}).get("asset", "-")
                    if attribution_map.get("assets")
                    else "-",
                    (attribution_map.get("policies", [{}])[0] or {}).get("policy", "-")
                    if attribution_map.get("policies")
                    else "-",
                )
            )
            fix_candidates = list(item.get("next_fix_candidates", []))
            if fix_candidates:
                lines.append(
                    "  next fixes: %s"
                    % (
                        " | ".join(
                            "%s x %s x %s"
                            % (
                                candidate.get("module", "-"),
                                candidate.get("asset", "-"),
                                candidate.get("policy", "-"),
                            )
                            for candidate in fix_candidates[:2]
                        )
                    )
                )
            window_breaches = list(item.get("window_breach_attribution", []))
            if window_breaches:
                lines.append(
                    "  window breaches: %s"
                    % (
                        " | ".join(
                            "%s:%s %.3f>%.3f"
                            % (
                                breach.get("window_label", "-"),
                                "/".join(breach.get("issue_codes", [])) or "-",
                                float(breach.get("actual", 0.0)),
                                float(breach.get("threshold", 0.0)),
                            )
                            for breach in window_breaches[:3]
                        )
                    )
                )
            stop_condition = dict(item.get("stop_condition", {}))
            if stop_condition:
                lines.append(
                    "  stop condition: %s"
                    % (
                        "%s (%s)"
                        % (
                            stop_condition.get("status", "-"),
                            ", ".join(stop_condition.get("failed_checks", [])) or "all_checks_passed",
                        )
                    )
                )
    else:
        lines.append("- none")
    if weakest_pack_polish_program:
        lines.extend(["", "## Weakest Pack Polish Program"])
        lines.extend(
            [
                "- program status: %s" % (weakest_pack_polish_program.get("status", "-") or "-"),
                "- stop-ready worlds: %s" % (", ".join(weakest_pack_polish_program.get("stop_ready_worlds", [])) or "-"),
                "- continue worlds: %s" % (", ".join(weakest_pack_polish_program.get("continue_worlds", [])) or "-"),
                "- recommended action: %s" % (weakest_pack_polish_program.get("recommended_action", "-") or "-"),
            ]
        )
        for bundle in weakest_pack_polish_program.get("bundles", [])[:3]:
            lines.append(
                "- %s · %s · dimensions %s"
                % (
                    bundle.get("world_id", "-"),
                    bundle.get("bundle_status", "-"),
                    ", ".join(bundle.get("target_dimensions", [])) or "-",
                )
            )
            if bundle.get("bundle_items"):
                lines.append(
                    "  bundle: %s"
                    % (
                        " | ".join(
                            "%s x %s x %s"
                            % (
                                item.get("module", "-"),
                                item.get("asset", "-"),
                                item.get("policy", "-"),
                            )
                            for item in bundle.get("bundle_items", [])[:2]
                )
                    )
                )
    if strategy_bundle_batch_validation:
        validation_available = bool(strategy_bundle_batch_validation.get("available"))
        skipped_worlds = list(strategy_bundle_batch_validation.get("skipped_worlds", []))
        lines.extend(["", "## Strategy Bundle Batch Validation"])
        lines.extend(
            [
                "- status: %s"
                % (
                    "ready" if validation_available else "not_run"
                ),
                "- strategy bundle: %s (%s)"
                % (
                    strategy_bundle_batch_validation.get("strategy_bundle_label", "-") or "-",
                    strategy_bundle_batch_validation.get("strategy_bundle_id", "-") or "-",
                ),
                "- execution mode: %s"
                % (strategy_bundle_batch_validation.get("batch_execution_mode", "-") or "-"),
                "- weakest source worlds: %s"
                % (", ".join(strategy_bundle_batch_validation.get("weakest_source_world_ids", [])) or "-"),
                "- compatible worlds: %s"
                % (", ".join(strategy_bundle_batch_validation.get("compatible_world_ids", [])) or "-"),
                "- validated world count: %s"
                % int(strategy_bundle_batch_validation.get("validated_world_count", 0) or 0),
                "- effectiveness rate: %.3f"
                % float(strategy_bundle_batch_validation.get("effectiveness_rate", 0.0) or 0.0),
                "- decision: %s" % (strategy_bundle_batch_validation.get("decision", "-") or "-"),
                "- decision reason: %s"
                % (strategy_bundle_batch_validation.get("decision_reason", "-") or "-"),
                "- overall status counts: %s"
                % (
                    ", ".join(
                        "%s=%s" % (key, value)
                        for key, value in sorted(
                            dict(
                                dict(
                                    strategy_bundle_batch_validation.get("aggregated_result_attribution", {})
                                ).get("overall_status_counts", {})
                            ).items()
                        )
                    )
                    or "-"
                ),
                "- stop decision counts: %s"
                % (
                    ", ".join(
                        "%s=%s" % (key, value)
                        for key, value in sorted(
                            dict(
                                dict(
                                    strategy_bundle_batch_validation.get("aggregated_result_attribution", {})
                                ).get("stop_decision_counts", {})
                            ).items()
                        )
                    )
                    or "-"
                ),
                "- skipped worlds: %s"
                % (
                    " | ".join(
                        "%s(%s)"
                        % (
                            item.get("world_id", "-"),
                            item.get("reason", "-"),
                        )
                        for item in skipped_worlds[:5]
                    )
                    or "-"
                ),
                "- adaptation targets: %s"
                % (
                    " | ".join(
                        "%s:%s=%s"
                        % (
                            item.get("kind", "-"),
                            item.get("name", "-"),
                            item.get("count", 0),
                        )
                        for item in strategy_bundle_batch_validation.get("adaptation_targets", [])[:5]
                    )
                    or "-"
                ),
            ]
        )
    if strategy_bundle_batch_validation_history or strategy_bundle_batch_validation_trend:
        history_entries = list(strategy_bundle_batch_validation_history.get("entries", []) or [])
        first_history_entry = history_entries[0] if history_entries else {}
        lines.extend(["", "## Strategy Bundle Batch Validation History"])
        lines.extend(
            [
                "- strategy bundle: %s (%s)"
                % (
                    first_history_entry.get("strategy_bundle_label", "")
                    or strategy_bundle_batch_validation.get("strategy_bundle_label", "-")
                    or strategy_bundle_batch_validation_trend.get("strategy_bundle_id", "-")
                    or "-",
                    strategy_bundle_batch_validation_trend.get("strategy_bundle_id", "-") or "-",
                ),
                "- trend status: %s" % (strategy_bundle_batch_validation_trend.get("trend_status", "-") or "-"),
                "- trend reason: %s" % (strategy_bundle_batch_validation_trend.get("trend_reason", "-") or "-"),
                "- recent run count: %s" % int(strategy_bundle_batch_validation_trend.get("recent_run_count", 0) or 0),
                "- latest decision: %s" % (strategy_bundle_batch_validation_trend.get("latest_decision", "-") or "-"),
                "- latest effectiveness rate: %.3f" % float(strategy_bundle_batch_validation_trend.get("latest_effectiveness_rate", 0.0) or 0.0),
                "- delta effectiveness rate: %+.3f" % float(strategy_bundle_batch_validation_trend.get("delta_effectiveness_rate", 0.0) or 0.0),
                "- retire recommended: %s" % ("yes" if strategy_bundle_batch_validation_trend.get("retire_recommended") else "no"),
                "- recent runs: %s"
                % (
                    " | ".join(
                        "%s %s eff=%.3f worlds=%s"
                        % (
                            item.get("generated_at", "-"),
                            item.get("decision", "-") or "-",
                            float(item.get("effectiveness_rate", 0.0) or 0.0),
                            int(item.get("validated_world_count", 0) or 0),
                        )
                        for item in history_entries[:5]
                    )
                    or "-"
                ),
            ]
        )
    if longform_l1_signoff:
        lines.extend(["", "## Longform L1 Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_l1_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_l1_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_l1_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_l1_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_l1_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_l1_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if interactive_longform_signoff:
        lines.extend(["", "## Interactive Longform Sign-off"])
        lines.extend(
            [
                "- status: %s" % (interactive_longform_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if interactive_longform_signoff.get("ready") else "no"),
                "- reason: %s" % (interactive_longform_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(interactive_longform_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(interactive_longform_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(interactive_longform_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_250_signoff:
        lines.extend(["", "## Longform 250 Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_250_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_250_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_250_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_250_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_250_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_250_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_250_interactive_signoff:
        lines.extend(["", "## Longform 250 Interactive Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_250_interactive_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_250_interactive_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_250_interactive_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_250_interactive_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_250_interactive_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_250_interactive_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_250_human_review_closeout:
        lines.extend(["", "## Longform 250 Human Review Closeout"])
        lines.extend(
            [
                "- status: %s" % (longform_250_human_review_closeout.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_250_human_review_closeout.get("ready") else "no"),
                "- reason: %s" % (longform_250_human_review_closeout.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_250_human_review_closeout.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_250_human_review_closeout.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_250_human_review_closeout.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_500_signoff:
        lines.extend(["", "## Longform 500 Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_500_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_500_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_500_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_500_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_500_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_500_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_500_human_review_closeout:
        lines.extend(["", "## Longform 500 Human Review Closeout"])
        lines.extend(
            [
                "- status: %s" % (longform_500_human_review_closeout.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_500_human_review_closeout.get("ready") else "no"),
                "- reason: %s" % (longform_500_human_review_closeout.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_500_human_review_closeout.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_500_human_review_closeout.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_500_human_review_closeout.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_500_ending_signoff:
        lines.extend(["", "## Longform 500 Ending Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_500_ending_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_500_ending_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_500_ending_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_500_ending_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_500_ending_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_500_ending_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_500_interactive_signoff:
        lines.extend(["", "## Longform 500 Interactive Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_500_interactive_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_500_interactive_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_500_interactive_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_500_interactive_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_500_interactive_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_500_interactive_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_1000_summary:
        lines.extend(["", "## Longform 1000 Evidence"])
        lines.extend(
            [
                "- diagnostic pass rate: %.3f" % float(longform_1000_summary.get("diagnostic_pass_rate", 0.0)),
                "- series boundary survival: %.3f" % float(longform_1000_summary.get("series_boundary_survival", 0.0)),
                "- series memory snapshot integrity: %.3f" % float(longform_1000_summary.get("series_memory_snapshot_integrity", 0.0)),
                "- memory recall coverage: %.3f" % float(longform_1000_summary.get("memory_recall_coverage", 0.0)),
                "- replan stability score: %.3f" % float(longform_1000_summary.get("replan_stability_score", 0.0)),
                "- late stage runtime p95 ms: %.3f" % float(longform_1000_summary.get("late_stage_runtime_p95_ms", 0.0)),
                "- late stage runtime budget score: %.3f" % float(longform_1000_summary.get("late_stage_runtime_budget_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_1000_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_1000_readiness:
        lines.extend(["", "## Longform 1000 Readiness"])
        lines.extend(
            [
                "- status: %s" % (longform_1000_readiness.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_1000_readiness.get("ready") else "no"),
                "- reason: %s" % (longform_1000_readiness.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_1000_readiness.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_1000_readiness.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_1000_readiness.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_1000_interactive_summary:
        lines.extend(["", "## Longform 1000 Interactive Evidence"])
        lines.extend(
            [
                "- gate pass rate: %.3f" % float(longform_1000_interactive_summary.get("gate_pass_rate", 0.0)),
                "- steering recovery rate: %.3f" % float(longform_1000_interactive_summary.get("steering_recovery_rate", 0.0)),
                "- post-steer route survival: %.3f" % float(longform_1000_interactive_summary.get("post_steer_route_survival", 0.0)),
                "- memory consistency after steer: %.3f" % float(longform_1000_interactive_summary.get("memory_consistency_after_steer", 0.0)),
                "- promise reconciliation after steer: %.3f" % float(longform_1000_interactive_summary.get("promise_reconciliation_after_steer", 0.0)),
                "- replan stability score: %.3f" % float(longform_1000_interactive_summary.get("replan_stability_score", 0.0)),
                "- failed worlds: %s" % (", ".join(longform_1000_interactive_summary.get("failed_worlds", [])) or "-"),
            ]
        )
    if longform_1000_interactive_signoff:
        lines.extend(["", "## Longform 1000 Interactive Sign-off"])
        lines.extend(
            [
                "- status: %s" % (longform_1000_interactive_signoff.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_1000_interactive_signoff.get("ready") else "no"),
                "- reason: %s" % (longform_1000_interactive_signoff.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_1000_interactive_signoff.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_1000_interactive_signoff.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_1000_interactive_signoff.get("required_evidence", [])) or "-"),
            ]
        )
    if longform_1000_human_review_closeout:
        lines.extend(["", "## Longform 1000 Human Review Closeout"])
        lines.extend(
            [
                "- status: %s" % (longform_1000_human_review_closeout.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_1000_human_review_closeout.get("ready") else "no"),
                "- reason: %s" % (longform_1000_human_review_closeout.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_1000_human_review_closeout.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_1000_human_review_closeout.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_1000_human_review_closeout.get("required_evidence", [])) or "-"),
                "- human reviewed target count: %s" % int(review_sample_coverage_1000.get("human_reviewed_target_count", 0) or 0),
                "- planned target count: %s" % int(review_sample_coverage_1000.get("planned_target_count", 0) or 0),
            ]
        )
    if longform_1000_feasibility:
        lines.extend(["", "## Longform 1000 Feasibility"])
        lines.extend(
            [
                "- status: %s" % (longform_1000_feasibility.get("status", "-") or "-"),
                "- ready: %s" % ("yes" if longform_1000_feasibility.get("ready") else "no"),
                "- reason: %s" % (longform_1000_feasibility.get("reason", "-") or "-"),
                "- blocking worlds: %s" % (", ".join(longform_1000_feasibility.get("blocking_worlds", [])) or "-"),
                "- watch worlds: %s" % (", ".join(longform_1000_feasibility.get("watch_worlds", [])) or "-"),
                "- required evidence: %s" % (", ".join(longform_1000_feasibility.get("required_evidence", [])) or "-"),
            ]
        )
    lines.extend(
        [
            "",
            "## Ranking and Metric Delta",
            "- strongest packs changed: entered [%s] · exited [%s]"
            % (
                ", ".join(ranking_changes.get("entered_strongest", [])) or "-",
                ", ".join(ranking_changes.get("exited_strongest", [])) or "-",
            ),
            "- weakest packs changed: entered [%s] · exited [%s]"
            % (
                ", ".join(ranking_changes.get("entered_weakest", [])) or "-",
                ", ".join(ranking_changes.get("exited_weakest", [])) or "-",
            ),
            "- current strongest: %s" % (", ".join(current_strongest) or "-"),
            "- current weakest: %s" % (", ".join(current_weakest) or "-"),
            "- regressions: %s"
            % (
                "; ".join(
                    "%s [%s]" % (item.get("world_id", "-"), ", ".join(item.get("metrics", [])))
                    for item in delta_summary.get("regressions", [])
                )
                or "none"
            ),
        ]
    )
    return "\n".join(lines).strip() + "\n"
