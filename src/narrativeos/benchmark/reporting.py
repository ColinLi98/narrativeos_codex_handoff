from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

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
    return {
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
        "asset_snapshot": attribution["asset_snapshot"],
        "next_fix_candidates": attribution["next_fix_candidates"],
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
        }
    target = int(worlds[0].get("route_longevity_target", 0))
    stop_reason_counts: Dict[str, int] = {}
    for item in worlds:
        stop_reason = str(item.get("stop_reason", "unknown"))
        stop_reason_counts[stop_reason] = stop_reason_counts.get(stop_reason, 0) + 1
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
            and float(current_world.get("avg_repetition_score", 0.0)) <= 0.08
            and abs(float(delta.get("avg_repetition_score_delta", 0.0))) <= 0.04
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
    strongest_packs = list(summary.get("strongest_packs", []))
    long_route_summary = dict(summary.get("long_route_summary", {}))
    delta_summary = dict(summary.get("delta_summary", {}))
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
        "## Strongest Packs",
    ]
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
    else:
        lines.append("- none")
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
