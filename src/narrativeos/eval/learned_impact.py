from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..models import EvaluationReport
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .learned_assisted_gate import list_assisted_gate_decisions, load_assisted_gate_config
from .learned_compare import build_learned_compare_from_dashboard
from .learned_data_ops import build_learned_data_ops_summary
from .learned_dashboard import build_learned_dashboard_summary


VALID_TRACKS = {"evaluator", "reranker"}
EVALUATOR_TARGET_SAMPLES_PER_WORLD = 5
RERANKER_TARGET_SAMPLES_PER_WORLD = 3
MONETIZATION_PROXY_EVENTS = [
    "payment_required",
    "checkout_started",
    "subscription_activated",
    "subscription_state_changed",
    "story_credits_consumed",
    "studio_credits_consumed",
    "entitlement_granted",
]
ASSISTED_GATE_TARGET_DECISIONS = 5


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _average(values: Sequence[float]) -> Optional[float]:
    cleaned = [float(value) for value in values]
    if not cleaned:
        return None
    return round(sum(cleaned) / float(len(cleaned)), 3)


def _pearson_correlation(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / float(len(xs))
    mean_y = sum(ys) / float(len(ys))
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = (denom_x * denom_y) ** 0.5
    if denominator == 0.0:
        return 0.0
    return round(numerator / denominator, 3)


def _selected_versions(
    repository: SQLAlchemyPlatformRepository,
    *,
    world_id: Optional[str],
    world_version_id: Optional[str],
) -> List[Dict[str, str]]:
    if world_version_id:
        version = repository.get_world_version(world_version_id)
        return [{"world_id": version.world_id, "world_version_id": version.world_version_id}]
    if world_id:
        return [
            {"world_id": world_id, "world_version_id": item["world_version_id"]}
            for item in repository.list_world_versions(world_id=world_id)
        ]
    versions: List[Dict[str, str]] = []
    for world in repository.list_worlds():
        versions.extend(
            {
                "world_id": world["world_id"],
                "world_version_id": item["world_version_id"],
            }
            for item in repository.list_world_versions(world_id=world["world_id"])
        )
    return versions


def _version_quality_rows(
    repository: SQLAlchemyPlatformRepository,
    *,
    selected_versions: Sequence[Dict[str, str]],
) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for item in selected_versions:
        version_id = item["world_version_id"]
        payloads = repository.list_evaluation_reports(world_version_id=version_id)
        reports = [EvaluationReport.from_dict(payload) for payload in payloads]
        if not reports:
            continue
        rows[version_id] = {
            "world_id": item["world_id"],
            "world_version_id": version_id,
            "quality_score": round(
                sum(report.scores.overall_score for report in reports) / float(max(1, len(reports))),
                3,
            ),
            "sample_count": len(reports),
        }
    return rows


def _event_key(event_name: str) -> str:
    return {
        "payment_required": "payment_required_count",
        "checkout_started": "checkout_started_count",
        "subscription_activated": "subscription_activated_count",
        "subscription_state_changed": "subscription_state_changed_count",
        "story_credits_consumed": "story_credit_consumed_count",
        "studio_credits_consumed": "studio_credit_consumed_count",
        "entitlement_granted": "entitlement_granted_count",
    }[event_name]


def _build_monetization_proxy_summary(
    repository: SQLAlchemyPlatformRepository,
    *,
    selected_versions: Sequence[Dict[str, str]],
    quality_rows: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    version_lookup = {item["world_version_id"]: item["world_id"] for item in selected_versions}
    version_event_rows = {
        version_id: {
            "world_id": payload["world_id"],
            "world_version_id": version_id,
            "quality_score": payload["quality_score"],
            "sample_count": payload["sample_count"],
            "payment_required_count": 0,
            "checkout_started_count": 0,
            "subscription_activated_count": 0,
            "subscription_state_changed_count": 0,
            "story_credit_consumed_count": 0,
            "studio_credit_consumed_count": 0,
            "entitlement_granted_count": 0,
        }
        for version_id, payload in quality_rows.items()
    }
    selected_version_ids = list(version_lookup) if version_lookup else None
    analytics_rows = repository.list_analytics_events(
        event_names=MONETIZATION_PROXY_EVENTS,
        world_version_ids=selected_version_ids,
    ) if selected_version_ids is not None else repository.list_analytics_events(event_names=MONETIZATION_PROXY_EVENTS)

    total_counts = {field: 0 for field in [
        "payment_required_count",
        "checkout_started_count",
        "subscription_activated_count",
        "subscription_state_changed_count",
        "story_credit_consumed_count",
        "studio_credit_consumed_count",
        "entitlement_granted_count",
    ]}
    unattributed_counts = dict(total_counts)

    for event in analytics_rows:
        event_name = str(event.get("event_name") or "")
        if event_name not in MONETIZATION_PROXY_EVENTS:
            continue
        metric_key = _event_key(event_name)
        total_counts[metric_key] += 1
        payload_json = dict(event.get("payload_json") or {})
        version_id = event.get("world_version_id") or payload_json.get("world_version_id")
        if version_id in version_event_rows:
            version_event_rows[version_id][metric_key] += 1
        else:
            unattributed_counts[metric_key] += 1

    version_rows = list(version_event_rows.values())

    def _corr(metric_key: str) -> float:
        return _pearson_correlation(
            [
                (float(item["quality_score"]), 1.0 if int(item.get(metric_key, 0) or 0) > 0 else 0.0)
                for item in version_rows
            ]
        )

    quality_signal_correlations = [
        {
            "metric": "checkout_started",
            "correlation": _corr("checkout_started_count"),
            "sample_count": len(version_rows),
            "positive_direction": True,
        },
        {
            "metric": "subscription_activated",
            "correlation": _corr("subscription_activated_count"),
            "sample_count": len(version_rows),
            "positive_direction": True,
        },
        {
            "metric": "payment_required",
            "correlation": _corr("payment_required_count"),
            "sample_count": len(version_rows),
            "positive_direction": False,
        },
    ]

    return {
        "sample_count": len(version_rows),
        **total_counts,
        "quality_to_checkout_correlation": quality_signal_correlations[0]["correlation"],
        "quality_to_subscription_correlation": quality_signal_correlations[1]["correlation"],
        "quality_to_paywall_correlation": quality_signal_correlations[2]["correlation"],
        "quality_signal_correlations": quality_signal_correlations,
        "version_rows": version_rows,
        "unattributed_counts": unattributed_counts,
    }


def _track_coverage(
    *,
    track: str,
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    if track == "evaluator":
        examples = list(bundle.get("evaluator_examples", []))
        issue_codes = sorted(
            {
                issue_code
                for sample in bundle.get("chapter_review_samples", [])
                for issue_code in list(sample.get("linked_issue_codes") or sample.get("issue_codes") or [])
                if issue_code
            }
        )
    else:
        examples = list(bundle.get("reranker_examples", []))
        issue_codes = sorted(
            {
                issue_code
                for pair in bundle.get("issue_fix_pairs", [])
                for issue_code in list(pair.get("linked_issue_codes") or [])
                if issue_code
            }
        )
    world_counts: Dict[str, int] = {}
    for item in examples:
        world_id = str(item.get("world_id") or "")
        if not world_id:
            continue
        world_counts[world_id] = world_counts.get(world_id, 0) + 1
    return {
        "sample_count": len(examples),
        "world_counts": world_counts,
        "issue_codes": issue_codes,
    }


def _weighted_world_average(
    *,
    world_counts: Dict[str, int],
    world_map: Dict[str, Dict[str, Any]],
    field: str,
) -> Optional[float]:
    weighted_points: List[tuple[float, int]] = []
    for world_id, count in world_counts.items():
        payload = world_map.get(world_id)
        if not payload or payload.get(field) is None:
            continue
        weighted_points.append((float(payload[field]), int(count)))
    if not weighted_points:
        return None
    numerator = sum(value * weight for value, weight in weighted_points)
    denominator = sum(weight for _value, weight in weighted_points)
    if denominator <= 0:
        return None
    return round(numerator / float(denominator), 3)


def _monetization_signal_score(world_payload: Dict[str, Any]) -> Optional[float]:
    values: List[float] = []
    checkout = world_payload.get("quality_to_checkout_correlation")
    subscription = world_payload.get("quality_to_subscription_correlation")
    paywall = world_payload.get("quality_to_paywall_correlation")
    if checkout is not None:
        values.append(float(checkout))
    if subscription is not None:
        values.append(float(subscription))
    if paywall is not None:
        values.append(float(-paywall))
    return round(sum(values) / float(len(values)), 3) if values else None


def _evidence_sufficiency(
    *,
    sample_count: int,
    world_coverage_count: int,
    track: str,
) -> str:
    target = EVALUATOR_TARGET_SAMPLES_PER_WORLD if track == "evaluator" else RERANKER_TARGET_SAMPLES_PER_WORLD
    if sample_count <= 0 or world_coverage_count <= 0:
        return "insufficient"
    if sample_count < target or world_coverage_count < 2:
        return "partial"
    return "sufficient"


def _impact_status(
    *,
    evidence_sufficiency: str,
    continuation_correlation: Optional[float],
    monetization_correlation: Optional[float],
) -> str:
    if evidence_sufficiency != "sufficient" or continuation_correlation is None:
        return "insufficient_data"
    monetization_correlation = float(monetization_correlation or 0.0)
    if continuation_correlation >= 0.25 and monetization_correlation >= 0.0:
        return "promising"
    if continuation_correlation <= 0.0 and monetization_correlation < 0.0:
        return "weak_signal"
    return "mixed"


def _track_recommended_action(track: str, *, evidence_sufficiency: str, impact_status: str) -> str:
    if evidence_sufficiency == "insufficient":
        return "expand_review_coverage" if track == "evaluator" else "expand_pair_coverage"
    if evidence_sufficiency == "partial":
        return "increase_world_coverage"
    if impact_status == "weak_signal":
        return "inspect_low_signal_worlds"
    if impact_status == "mixed":
        return "inspect_world_issue_mismatch"
    return "continue_shadow_validation"


def _assisted_gate_version_rows(
    repository: SQLAlchemyPlatformRepository,
    *,
    selected_versions: Sequence[Dict[str, str]],
) -> Dict[str, Dict[str, Any]]:
    version_lookup = {item["world_version_id"]: item["world_id"] for item in selected_versions}
    decision_rows = {
        version_id: {
            "world_id": world_id,
            "world_version_id": version_id,
            "decision_count": 0,
            "in_bucket_count": 0,
            "eligible_count": 0,
            "shadow_count": 0,
            "would_block_count": 0,
            "assisted_block_count": 0,
        }
        for version_id, world_id in version_lookup.items()
    }
    for item in list_assisted_gate_decisions(repository, limit=None):
        version_id = str(item.get("world_version_id") or "")
        if not version_id or version_id not in decision_rows:
            continue
        row = decision_rows[version_id]
        row["decision_count"] += 1
        row["in_bucket_count"] += 1 if item.get("bucket_match") else 0
        row["eligible_count"] += 1 if item.get("guardrail_status") == "eligible" else 0
        row["shadow_count"] += 1 if item.get("mode") == "shadow_only" else 0
        row["would_block_count"] += 1 if item.get("would_block") else 0
        row["assisted_block_count"] += 1 if item.get("assisted_action") == "block_publish" else 0
    return decision_rows


def _assisted_gate_signal_score(row: Dict[str, Any]) -> Optional[float]:
    decision_count = int(row.get("decision_count", 0) or 0)
    if decision_count <= 0:
        return None
    return round(
        (
            float(int(row.get("in_bucket_count", 0) or 0)) / float(decision_count)
            + float(int(row.get("would_block_count", 0) or 0)) / float(decision_count)
            + float(int(row.get("assisted_block_count", 0) or 0)) / float(decision_count)
        )
        / 3.0,
        3,
    )


def _experiment_evidence_sufficiency(*, sample_count: int, world_coverage_count: int) -> str:
    if sample_count <= 0 or world_coverage_count <= 0:
        return "insufficient"
    if sample_count < ASSISTED_GATE_TARGET_DECISIONS or world_coverage_count < 2:
        return "partial"
    return "sufficient"


def _assisted_gate_experiment_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    selected_versions: Sequence[Dict[str, str]],
    continuation_metrics: Dict[str, Any],
    monetization_summary: Dict[str, Any],
) -> Dict[str, Any]:
    config_payload = load_assisted_gate_config(repository)
    version_decisions = _assisted_gate_version_rows(repository, selected_versions=selected_versions)
    version_rows = list(version_decisions.values())
    continuation_version_map = {
        item["world_version_id"]: item
        for item in continuation_metrics.get("continuation_version_details", [])
    }
    monetization_version_map = {
        item["world_version_id"]: item
        for item in monetization_summary.get("version_rows", [])
    }
    continuation_points = [
        (
            1.0 if int(item.get("assisted_block_count", 0) or 0) > 0 else 0.0,
            float(continuation_version_map[item["world_version_id"]]["continuation_rate"]),
        )
        for item in version_rows
        if item["world_version_id"] in continuation_version_map
    ]
    checkout_points = [
        (
            1.0 if int(item.get("assisted_block_count", 0) or 0) > 0 else 0.0,
            1.0 if int(monetization_version_map[item["world_version_id"]].get("checkout_started_count", 0) or 0) > 0 else 0.0,
        )
        for item in version_rows
        if item["world_version_id"] in monetization_version_map
    ]
    subscription_points = [
        (
            1.0 if int(item.get("assisted_block_count", 0) or 0) > 0 else 0.0,
            1.0 if int(monetization_version_map[item["world_version_id"]].get("subscription_activated_count", 0) or 0) > 0 else 0.0,
        )
        for item in version_rows
        if item["world_version_id"] in monetization_version_map
    ]
    paywall_points = [
        (
            1.0 if int(item.get("assisted_block_count", 0) or 0) > 0 else 0.0,
            1.0 if int(monetization_version_map[item["world_version_id"]].get("payment_required_count", 0) or 0) > 0 else 0.0,
        )
        for item in version_rows
        if item["world_version_id"] in monetization_version_map
    ]
    decision_count = sum(int(item.get("decision_count", 0) or 0) for item in version_rows)
    world_count = len({item["world_id"] for item in version_rows if int(item.get("decision_count", 0) or 0) > 0})
    evidence_sufficiency = _experiment_evidence_sufficiency(sample_count=decision_count, world_coverage_count=world_count)
    continuation_correlation = _pearson_correlation(continuation_points)
    monetization_correlation = _average(
        [
            _pearson_correlation(checkout_points),
            _pearson_correlation(subscription_points),
            _pearson_correlation([(x, 1.0 - y) for x, y in paywall_points]) if paywall_points else 0.0,
        ]
    )
    if evidence_sufficiency != "sufficient":
        impact_status = "insufficient_data"
    elif continuation_correlation >= 0.1 and float(monetization_correlation or 0.0) >= 0.0:
        impact_status = "promising"
    elif continuation_correlation <= 0.0 and float(monetization_correlation or 0.0) < 0.0:
        impact_status = "weak_signal"
    else:
        impact_status = "mixed"
    if not config_payload["config"].get("enabled"):
        recommended_next_action = "enable_shadow_only_capture"
    elif config_payload["config"].get("mode") == "shadow_only":
        recommended_next_action = "compare_shadow_receipts_against_outcomes"
    elif evidence_sufficiency != "sufficient":
        recommended_next_action = "collect_more_assisted_gate_decisions"
    else:
        recommended_next_action = "monitor_assisted_gate_business_impact"
    return {
        "experiment_name": "assisted_gate",
        "track": "evaluator",
        "enabled": bool(config_payload["config"].get("enabled")),
        "mode": config_payload["config"].get("mode"),
        "bucket_percentage": int(config_payload["config"].get("bucket_percentage", 0) or 0),
        "decision_count": decision_count,
        "world_coverage_count": world_count,
        "in_bucket_count": sum(int(item.get("in_bucket_count", 0) or 0) for item in version_rows),
        "eligible_count": sum(int(item.get("eligible_count", 0) or 0) for item in version_rows),
        "shadow_count": sum(int(item.get("shadow_count", 0) or 0) for item in version_rows),
        "would_block_count": sum(int(item.get("would_block_count", 0) or 0) for item in version_rows),
        "assisted_block_count": sum(int(item.get("assisted_block_count", 0) or 0) for item in version_rows),
        "continuation_correlation": continuation_correlation,
        "monetization_correlation": monetization_correlation,
        "assisted_block_to_checkout_correlation": _pearson_correlation(checkout_points),
        "assisted_block_to_subscription_correlation": _pearson_correlation(subscription_points),
        "assisted_block_to_paywall_correlation": _pearson_correlation(paywall_points),
        "impact_status": impact_status,
        "evidence_sufficiency": evidence_sufficiency,
        "recommended_next_action": recommended_next_action,
        "version_rows": version_rows,
    }


def _build_track_summary(
    *,
    track: str,
    coverage: Dict[str, Any],
    dashboard_summary: Dict[str, Any],
    compare_summary: Dict[str, Any],
    world_impact_map: Dict[str, Dict[str, Any]],
    experiment_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    world_counts = dict(coverage.get("world_counts", {}))
    continuation_correlation = _weighted_world_average(
        world_counts=world_counts,
        world_map=world_impact_map,
        field="continuation_correlation",
    )
    monetization_correlation = _weighted_world_average(
        world_counts=world_counts,
        world_map=world_impact_map,
        field="monetization_signal_score",
    )
    evidence_sufficiency = _evidence_sufficiency(
        sample_count=int(coverage.get("sample_count", 0)),
        world_coverage_count=len(world_counts),
        track=track,
    )
    impact_status = _impact_status(
        evidence_sufficiency=evidence_sufficiency,
        continuation_correlation=continuation_correlation,
        monetization_correlation=monetization_correlation,
    )
    if track == "evaluator":
        shadow_metric = dashboard_summary.get("evaluator_shadow_summary", {}).get("agreement_rate")
    else:
        shadow_metric = compare_summary.get("reranker_scorecard", {}).get("average_world_accuracy")
    summary = {
        "track": track,
        "impact_status": impact_status,
        "sample_count": int(coverage.get("sample_count", 0)),
        "world_coverage_count": len(world_counts),
        "issue_coverage_count": len(coverage.get("issue_codes", [])),
        "continuation_correlation": continuation_correlation,
        "monetization_correlation": monetization_correlation,
        "shadow_agreement_or_accuracy": shadow_metric,
        "recommended_next_action": _track_recommended_action(
            track,
            evidence_sufficiency=evidence_sufficiency,
            impact_status=impact_status,
        ),
        "evidence_sufficiency": evidence_sufficiency,
    }
    if track == "evaluator" and experiment_summary:
        summary["assisted_experiment"] = {
            "decision_count": experiment_summary.get("decision_count", 0),
            "assisted_block_count": experiment_summary.get("assisted_block_count", 0),
            "impact_status": experiment_summary.get("impact_status"),
            "evidence_sufficiency": experiment_summary.get("evidence_sufficiency"),
            "continuation_correlation": experiment_summary.get("continuation_correlation"),
            "monetization_correlation": experiment_summary.get("monetization_correlation"),
        }
    return summary


def _sample_accumulation(
    *,
    retention_summary: Dict[str, Any],
    evaluator_coverage: Dict[str, Any],
    reranker_coverage: Dict[str, Any],
) -> Dict[str, Any]:
    def _track_accumulation(track: str, coverage: Dict[str, Any]) -> Dict[str, Any]:
        target = EVALUATOR_TARGET_SAMPLES_PER_WORLD if track == "evaluator" else RERANKER_TARGET_SAMPLES_PER_WORLD
        prioritized_worlds = []
        for world_id, count in sorted(coverage.get("world_counts", {}).items(), key=lambda item: (item[1], item[0])):
            sample_gap = max(0, target - int(count))
            if sample_gap <= 0:
                continue
            prioritized_worlds.append(
                {
                    "world_id": world_id,
                    "sample_count": int(count),
                    "sample_gap": sample_gap,
                }
            )
        return {
            "target_sample_count_per_world": target,
            "worlds_below_target_count": len(prioritized_worlds),
            "prioritized_worlds": prioritized_worlds[:5],
        }

    return {
        "retention": retention_summary,
        "evaluator": _track_accumulation("evaluator", evaluator_coverage),
        "reranker": _track_accumulation("reranker", reranker_coverage),
    }


def _world_impact_details(
    *,
    dashboard_summary: Dict[str, Any],
    continuation_metrics: Dict[str, Any],
    monetization_summary: Dict[str, Any],
    evaluator_coverage: Dict[str, Any],
    reranker_coverage: Dict[str, Any],
    experiment_version_rows: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    dashboard_world_map = {item["world_id"]: item for item in dashboard_summary.get("world_details", [])}
    continuation_world_map = {item["world_id"]: item for item in continuation_metrics.get("continuation_world_details", [])}
    world_version_rows = list(monetization_summary.get("version_rows", []))
    world_ids = sorted(
        {
            *dashboard_world_map.keys(),
            *continuation_world_map.keys(),
            *[item.get("world_id") for item in world_version_rows if item.get("world_id")],
            *evaluator_coverage.get("world_counts", {}).keys(),
            *reranker_coverage.get("world_counts", {}).keys(),
        }
        - {None, ""}
    )

    details: List[Dict[str, Any]] = []
    for world_id in world_ids:
        dashboard_world = dashboard_world_map.get(world_id, {})
        continuation_world = continuation_world_map.get(world_id, {})
        version_rows = [item for item in world_version_rows if item.get("world_id") == world_id]
        experiment_rows = [
            item
            for item in (experiment_version_rows or {}).values()
            if item.get("world_id") == world_id
        ]
        checkout_corr = _pearson_correlation([(float(item["quality_score"]), 1.0 if int(item["checkout_started_count"]) > 0 else 0.0) for item in version_rows])
        subscription_corr = _pearson_correlation([(float(item["quality_score"]), 1.0 if int(item["subscription_activated_count"]) > 0 else 0.0) for item in version_rows])
        paywall_corr = _pearson_correlation([(float(item["quality_score"]), 1.0 if int(item["payment_required_count"]) > 0 else 0.0) for item in version_rows])
        payload = {
            "world_id": world_id,
            "continuation_correlation": continuation_world.get("online_continuation_correlation"),
            "continuation_sample_count": continuation_world.get("sample_count", 0),
            "continuation_rate": continuation_world.get("continuation_rate"),
            "continuation_sample_gap": continuation_world.get("sample_gap", 0),
            "monetization_sample_count": len(version_rows),
            "checkout_started_count": sum(int(item.get("checkout_started_count", 0) or 0) for item in version_rows),
            "subscription_activated_count": sum(int(item.get("subscription_activated_count", 0) or 0) for item in version_rows),
            "payment_required_count": sum(int(item.get("payment_required_count", 0) or 0) for item in version_rows),
            "story_credit_consumed_count": sum(int(item.get("story_credit_consumed_count", 0) or 0) for item in version_rows),
            "studio_credit_consumed_count": sum(int(item.get("studio_credit_consumed_count", 0) or 0) for item in version_rows),
            "assisted_gate_decision_count": sum(int(item.get("decision_count", 0) or 0) for item in experiment_rows),
            "assisted_gate_in_bucket_count": sum(int(item.get("in_bucket_count", 0) or 0) for item in experiment_rows),
            "assisted_gate_would_block_count": sum(int(item.get("would_block_count", 0) or 0) for item in experiment_rows),
            "assisted_gate_assisted_block_count": sum(int(item.get("assisted_block_count", 0) or 0) for item in experiment_rows),
            "quality_to_checkout_correlation": checkout_corr,
            "quality_to_subscription_correlation": subscription_corr,
            "quality_to_paywall_correlation": paywall_corr,
            "evaluator_agreement_rate": dashboard_world.get("evaluator_agreement_rate"),
            "reranker_accuracy": dashboard_world.get("reranker_accuracy"),
            "evaluator_sample_count": int(evaluator_coverage.get("world_counts", {}).get(world_id, 0)),
            "reranker_sample_count": int(reranker_coverage.get("world_counts", {}).get(world_id, 0)),
            "evaluator_issue_coverage_count": len(dashboard_world.get("evaluator_top_issues", [])),
            "reranker_issue_coverage_count": len(dashboard_world.get("reranker_top_issues", [])),
            "recommended_next_action": dashboard_world.get("recommended_action") or continuation_world.get("recommended_action"),
        }
        payload["monetization_signal_score"] = _monetization_signal_score(payload)
        details.append(payload)
    details.sort(
        key=lambda item: (
            item.get("recommended_next_action") == "monitor_shadow_candidate",
            _safe_float(item.get("continuation_sample_gap")),
            str(item.get("world_id")),
        )
    )
    return details


def _issue_impact_details(
    *,
    dashboard_summary: Dict[str, Any],
    world_impact_map: Dict[str, Dict[str, Any]],
    evaluator_bundle: Dict[str, Any],
    reranker_bundle: Dict[str, Any],
) -> List[Dict[str, Any]]:
    evaluator_issue_counts: Dict[str, int] = {}
    for sample in evaluator_bundle.get("chapter_review_samples", []):
        for issue_code in list(sample.get("linked_issue_codes") or sample.get("issue_codes") or []):
            evaluator_issue_counts[issue_code] = evaluator_issue_counts.get(issue_code, 0) + 1
    reranker_issue_counts: Dict[str, int] = {}
    for pair in reranker_bundle.get("issue_fix_pairs", []):
        for issue_code in list(pair.get("linked_issue_codes") or []):
            reranker_issue_counts[issue_code] = reranker_issue_counts.get(issue_code, 0) + 1

    details: List[Dict[str, Any]] = []
    for issue_detail in dashboard_summary.get("issue_details", []):
        affected_worlds = [world_impact_map[world_id] for world_id in issue_detail.get("affected_worlds", []) if world_id in world_impact_map]
        details.append(
            {
                "issue_code": issue_detail["issue_code"],
                "affected_worlds": issue_detail.get("affected_worlds", []),
                "affected_world_count": len(issue_detail.get("affected_worlds", [])),
                "evaluator_error_rate": issue_detail.get("evaluator_error_rate"),
                "reranker_error_rate": issue_detail.get("reranker_error_rate"),
                "evaluator_sample_count": int(evaluator_issue_counts.get(issue_detail["issue_code"], 0)),
                "reranker_sample_count": int(reranker_issue_counts.get(issue_detail["issue_code"], 0)),
                "continuation_correlation": _average([
                    _safe_float(item.get("continuation_correlation")) for item in affected_worlds if item.get("continuation_correlation") is not None
                ]),
                "monetization_correlation": _average([
                    _safe_float(item.get("monetization_signal_score")) for item in affected_worlds if item.get("monetization_signal_score") is not None
                ]),
                "payment_required_count": sum(int(item.get("payment_required_count", 0) or 0) for item in affected_worlds),
                "checkout_started_count": sum(int(item.get("checkout_started_count", 0) or 0) for item in affected_worlds),
                "subscription_activated_count": sum(int(item.get("subscription_activated_count", 0) or 0) for item in affected_worlds),
                "assisted_gate_decision_count": sum(int(item.get("assisted_gate_decision_count", 0) or 0) for item in affected_worlds),
                "assisted_gate_assisted_block_count": sum(int(item.get("assisted_gate_assisted_block_count", 0) or 0) for item in affected_worlds),
                "recommended_next_action": issue_detail.get("recommended_action"),
            }
        )
    details.sort(
        key=lambda item: (
            -int(item.get("evaluator_sample_count", 0) or 0) - int(item.get("reranker_sample_count", 0) or 0),
            str(item.get("issue_code")),
        )
    )
    return details


def build_learned_impact_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track is not None and track not in VALID_TRACKS:
        raise ValueError("invalid_learned_impact_track")

    dashboard_summary = build_learned_dashboard_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    compare_summary = build_learned_compare_from_dashboard(dashboard_summary)
    data_ops_summary = build_learned_data_ops_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    continuation_metrics = repository.aggregate_eval_metrics(
        world_id=world_id,
        world_version_id=world_version_id,
    )
    training_signal = TrainingSignalService(repository)
    evaluator_bundle = training_signal.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view="evaluator",
    )
    reranker_bundle = training_signal.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view="reranker",
    )
    selected_versions = _selected_versions(repository, world_id=world_id, world_version_id=world_version_id)
    quality_rows = _version_quality_rows(repository, selected_versions=selected_versions)
    monetization_summary = _build_monetization_proxy_summary(
        repository,
        selected_versions=selected_versions,
        quality_rows=quality_rows,
    )
    experiment_summary = _assisted_gate_experiment_summary(
        repository=repository,
        selected_versions=selected_versions,
        continuation_metrics=continuation_metrics,
        monetization_summary=monetization_summary,
    )
    evaluator_coverage = _track_coverage(track="evaluator", bundle=evaluator_bundle)
    reranker_coverage = _track_coverage(track="reranker", bundle=reranker_bundle)
    world_impact_details = _world_impact_details(
        dashboard_summary=dashboard_summary,
        continuation_metrics=continuation_metrics,
        monetization_summary=monetization_summary,
        evaluator_coverage=evaluator_coverage,
        reranker_coverage=reranker_coverage,
        experiment_version_rows={item["world_version_id"]: item for item in experiment_summary.get("version_rows", [])},
    )
    world_impact_map = {item["world_id"]: item for item in world_impact_details}
    issue_impact_details = _issue_impact_details(
        dashboard_summary=dashboard_summary,
        world_impact_map=world_impact_map,
        evaluator_bundle=evaluator_bundle,
        reranker_bundle=reranker_bundle,
    )
    track_summaries = [
        _build_track_summary(
            track="evaluator",
            coverage=evaluator_coverage,
            dashboard_summary=dashboard_summary,
            compare_summary=compare_summary,
            world_impact_map=world_impact_map,
            experiment_summary=experiment_summary,
        ),
        _build_track_summary(
            track="reranker",
            coverage=reranker_coverage,
            dashboard_summary=dashboard_summary,
            compare_summary=compare_summary,
            world_impact_map=world_impact_map,
        ),
    ]
    if track is not None:
        track_summaries = [item for item in track_summaries if item["track"] == track]

    warnings = list(
        dict.fromkeys(
            list(dashboard_summary.get("warnings", []))
            + list(compare_summary.get("warnings", []))
            + list(data_ops_summary.get("warnings", []))
            + [
                "insufficient_monetization_proxy_samples"
                if int(monetization_summary.get("sample_count", 0) or 0) < 2
                else "",
                "insufficient_assisted_gate_receipts"
                if int(experiment_summary.get("decision_count", 0) or 0) < 2
                else "",
            ]
        )
    )
    warnings = [item for item in warnings if item]

    return {
        "generated_at": dashboard_summary.get("generated_at"),
        "filters": {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "track": track,
            "limit": limit,
        },
        "track_summaries": track_summaries,
        "retention_proxies": {
            "online_continuation_correlation": continuation_metrics.get("online_continuation_correlation"),
            "continuation_signal_summary": continuation_metrics.get("continuation_signal_summary", {}),
            "assisted_gate_experiment": {
                "decision_count": experiment_summary.get("decision_count", 0),
                "world_coverage_count": experiment_summary.get("world_coverage_count", 0),
                "continuation_correlation": experiment_summary.get("continuation_correlation"),
                "impact_status": experiment_summary.get("impact_status"),
                "evidence_sufficiency": experiment_summary.get("evidence_sufficiency"),
            },
            "strongest_worlds": sorted(
                world_impact_details,
                key=lambda item: _safe_float(item.get("continuation_correlation")),
                reverse=True,
            )[:3],
            "weakest_worlds": sorted(
                world_impact_details,
                key=lambda item: _safe_float(item.get("continuation_correlation")),
            )[:3],
        },
        "monetization_proxies": {
            "sample_count": monetization_summary.get("sample_count", 0),
            "checkout_started_count": monetization_summary.get("checkout_started_count", 0),
            "subscription_activated_count": monetization_summary.get("subscription_activated_count", 0),
            "payment_required_count": monetization_summary.get("payment_required_count", 0),
            "story_credit_consumed_count": monetization_summary.get("story_credit_consumed_count", 0),
            "studio_credit_consumed_count": monetization_summary.get("studio_credit_consumed_count", 0),
            "quality_to_checkout_correlation": monetization_summary.get("quality_to_checkout_correlation"),
            "quality_to_subscription_correlation": monetization_summary.get("quality_to_subscription_correlation"),
            "quality_to_paywall_correlation": monetization_summary.get("quality_to_paywall_correlation"),
            "assisted_gate_experiment": {
                "decision_count": experiment_summary.get("decision_count", 0),
                "assisted_block_count": experiment_summary.get("assisted_block_count", 0),
                "monetization_correlation": experiment_summary.get("monetization_correlation"),
                "assisted_block_to_checkout_correlation": experiment_summary.get("assisted_block_to_checkout_correlation"),
                "assisted_block_to_subscription_correlation": experiment_summary.get("assisted_block_to_subscription_correlation"),
                "assisted_block_to_paywall_correlation": experiment_summary.get("assisted_block_to_paywall_correlation"),
            },
        },
        "quality_correlations": {
            "retention": continuation_metrics.get("quality_signal_correlations", []),
            "monetization": monetization_summary.get("quality_signal_correlations", []),
            "experiments": [
                {
                    "metric": "assisted_gate_to_continuation",
                    "correlation": experiment_summary.get("continuation_correlation"),
                    "sample_count": experiment_summary.get("decision_count", 0),
                    "positive_direction": True,
                },
                {
                    "metric": "assisted_gate_to_monetization",
                    "correlation": experiment_summary.get("monetization_correlation"),
                    "sample_count": experiment_summary.get("decision_count", 0),
                    "positive_direction": True,
                },
            ],
        },
        "experiment_summaries": {
            "assisted_gate": {
                key: value
                for key, value in experiment_summary.items()
                if key != "version_rows"
            }
        },
        "world_impact_details": world_impact_details[:limit] if limit is not None else world_impact_details,
        "issue_impact_details": issue_impact_details[:limit] if limit is not None else issue_impact_details,
        "sample_accumulation": _sample_accumulation(
            retention_summary=continuation_metrics.get("continuation_sample_accumulation", {}),
            evaluator_coverage=evaluator_coverage,
            reranker_coverage=reranker_coverage,
        ),
        "warnings": warnings,
    }


def build_learned_impact_world_detail(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: str,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = build_learned_impact_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        track=track,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    detail = next((item for item in summary.get("world_impact_details", []) if item["world_id"] == world_id), None)
    if detail is None:
        raise KeyError(f"unknown_learned_impact_world:{world_id}")
    return detail


def build_learned_impact_issue_detail(
    *,
    repository: SQLAlchemyPlatformRepository,
    issue_code: str,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = build_learned_impact_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        track=track,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    normalized_issue_code = issue_code.upper()
    detail = next(
        (item for item in summary.get("issue_impact_details", []) if item["issue_code"] == normalized_issue_code),
        None,
    )
    if detail is None:
        raise KeyError(f"unknown_learned_impact_issue:{normalized_issue_code}")
    return detail
