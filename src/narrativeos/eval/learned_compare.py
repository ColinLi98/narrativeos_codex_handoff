from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .learned_dashboard import build_learned_dashboard_summary


CRITICAL_EVALUATOR_ROLLOUT_WARNINGS = {
    "artifact_missing",
    "artifact_present_but_incomplete",
    "artifact_load_failed",
    "single_class_train_fallback_dummy",
}

CRITICAL_RERANKER_ROLLOUT_WARNINGS = {
    "artifact_missing",
    "artifact_present_but_incomplete",
    "artifact_load_failed",
    "single_class_train_fallback_dummy",
    "insufficient_reranker_pairs",
}


def _average_metric(values: list[float]) -> Optional[float]:
    cleaned = [float(value) for value in values]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _evaluator_world_is_stable(detail: Dict[str, Any]) -> bool:
    agreement_rate = detail.get("evaluator_agreement_rate")
    return bool(
        detail.get("evaluator_artifact_available")
        and not detail.get("evaluator_low_coverage")
        and agreement_rate is not None
        and float(agreement_rate) >= 0.8
    )


def _reranker_world_is_stable(detail: Dict[str, Any]) -> bool:
    accuracy = detail.get("reranker_accuracy")
    return bool(
        detail.get("reranker_artifact_available")
        and not detail.get("reranker_low_coverage")
        and accuracy is not None
        and float(accuracy) >= 0.75
    )


def _evaluator_scorecard(summary: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(summary.get("evaluator_shadow_summary", {}))
    warnings = list(payload.get("warnings", []))
    agreement_rate = payload.get("agreement_rate")
    if payload.get("status"):
        status = payload.get("status", "unavailable")
    elif not payload.get("artifact_present"):
        status = "unavailable"
    elif int(payload.get("val_count", 0) or 0) == 0 or int(payload.get("test_count", 0) or 0) == 0:
        status = "warming_up"
    elif "single_class_train_fallback_dummy" not in warnings and agreement_rate is not None and float(agreement_rate) >= 0.8:
        status = "candidate"
    else:
        status = "not_ready"
    return {
        "status": status,
        "agreement_rate": agreement_rate,
        "train_count": int(payload.get("train_count", 0) or 0),
        "val_count": int(payload.get("val_count", 0) or 0),
        "test_count": int(payload.get("test_count", 0) or 0),
        "warnings": warnings,
    }


def _reranker_scorecard(summary: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(summary.get("reranker_shadow_summary", {}))
    warnings = list(payload.get("warnings", []))
    per_world_accuracy = {
        str(key): float(value)
        for key, value in dict(payload.get("per_world_accuracy", {})).items()
    }
    average_world_accuracy = _average_metric(list(per_world_accuracy.values()))
    low_error_world_count = sum(1 for value in per_world_accuracy.values() if value >= 0.75)
    if payload.get("status"):
        status = payload.get("status", "unavailable")
    elif not payload.get("artifact_present"):
        status = "unavailable"
    elif int(payload.get("val_count", 0) or 0) == 0 or int(payload.get("test_count", 0) or 0) == 0:
        status = "warming_up"
    elif "single_class_train_fallback_dummy" not in warnings and per_world_accuracy and min(per_world_accuracy.values()) >= 0.75:
        status = "candidate"
    else:
        status = "not_ready"
    return {
        "status": status,
        "per_world_accuracy": per_world_accuracy,
        "average_world_accuracy": average_world_accuracy,
        "low_error_world_count": low_error_world_count,
        "train_count": int(payload.get("train_count", 0) or 0),
        "val_count": int(payload.get("val_count", 0) or 0),
        "test_count": int(payload.get("test_count", 0) or 0),
        "warnings": warnings,
    }


def _disagreement_worlds(summary: Dict[str, Any]) -> list[Dict[str, Any]]:
    items = []
    for detail in summary.get("world_details", []):
        evaluator_stable = _evaluator_world_is_stable(detail)
        reranker_stable = _reranker_world_is_stable(detail)
        if evaluator_stable == reranker_stable:
            continue
        items.append(
            {
                "world_id": detail["world_id"],
                "evaluator_signal": "stable" if evaluator_stable else "weak",
                "reranker_signal": "stable" if reranker_stable else "weak",
                "evaluator_agreement_rate": detail.get("evaluator_agreement_rate"),
                "reranker_accuracy": detail.get("reranker_accuracy"),
                "recommended_action": detail.get("recommended_action"),
            }
        )
    items.sort(
        key=lambda item: (
            0 if item["evaluator_signal"] == "stable" else 1,
            -(float(item["evaluator_agreement_rate"]) if item.get("evaluator_agreement_rate") is not None else -1.0),
            item["world_id"],
        )
    )
    return items[:5]


def _disagreement_issue_codes(summary: Dict[str, Any]) -> list[Dict[str, Any]]:
    items = []
    for detail in summary.get("issue_details", []):
        evaluator_error_rate = detail.get("evaluator_error_rate")
        reranker_error_rate = detail.get("reranker_error_rate")
        evaluator_high_error = evaluator_error_rate is not None and float(evaluator_error_rate) > 0.2
        reranker_high_error = reranker_error_rate is not None and float(reranker_error_rate) > 0.2
        if evaluator_high_error == reranker_high_error:
            continue
        items.append(
            {
                "issue_code": detail["issue_code"],
                "evaluator_error_rate": evaluator_error_rate,
                "reranker_error_rate": reranker_error_rate,
                "affected_worlds": list(detail.get("affected_worlds", [])),
                "recommended_action": detail.get("recommended_action"),
            }
        )
    items.sort(
        key=lambda item: (
            -max(
                float(item["evaluator_error_rate"]) if item.get("evaluator_error_rate") is not None else 0.0,
                float(item["reranker_error_rate"]) if item.get("reranker_error_rate") is not None else 0.0,
            ),
            item["issue_code"],
        )
    )
    return items[:5]


def _preferred_shadow_candidate(
    *,
    evaluator_scorecard: Dict[str, Any],
    reranker_scorecard: Dict[str, Any],
    world_details: list[Dict[str, Any]],
) -> str:
    evaluator_status = evaluator_scorecard.get("status")
    reranker_status = reranker_scorecard.get("status")

    if evaluator_status == "candidate" and reranker_status != "candidate":
        return "evaluator"
    if reranker_status == "candidate" and evaluator_status != "candidate":
        return "reranker"
    if evaluator_status != "candidate" and reranker_status != "candidate":
        return "neither"

    evaluator_ready_worlds = sum(1 for detail in world_details if _evaluator_world_is_stable(detail))
    reranker_ready_worlds = sum(1 for detail in world_details if _reranker_world_is_stable(detail))
    evaluator_agreement = float(evaluator_scorecard.get("agreement_rate") or 0.0)
    reranker_accuracy = float(reranker_scorecard.get("average_world_accuracy") or 0.0)

    if reranker_accuracy > evaluator_agreement and reranker_ready_worlds >= evaluator_ready_worlds:
        return "reranker"
    return "evaluator"


def build_learned_compare_from_dashboard(summary: Dict[str, Any]) -> Dict[str, Any]:
    evaluator_scorecard = _evaluator_scorecard(summary)
    reranker_scorecard = _reranker_scorecard(summary)
    disagreement_worlds = _disagreement_worlds(summary)
    disagreement_issue_codes = _disagreement_issue_codes(summary)
    preferred_shadow_candidate = _preferred_shadow_candidate(
        evaluator_scorecard=evaluator_scorecard,
        reranker_scorecard=reranker_scorecard,
        world_details=list(summary.get("world_details", [])),
    )

    if preferred_shadow_candidate == "evaluator":
        recommended_next_action = "advance_evaluator_shadow_candidate"
    elif preferred_shadow_candidate == "reranker":
        recommended_next_action = "advance_reranker_shadow_candidate"
    else:
        recommended_next_action = "expand_review_and_pair_data"

    evaluator_blocking_warnings = [
        warning for warning in evaluator_scorecard.get("warnings", [])
        if warning in CRITICAL_EVALUATOR_ROLLOUT_WARNINGS
    ]
    reranker_blocking_warnings = [
        warning for warning in reranker_scorecard.get("warnings", [])
        if warning in CRITICAL_RERANKER_ROLLOUT_WARNINGS
    ]
    rollout_readiness = {
        "evaluator": {
            "track": "evaluator",
            "candidate_ready": evaluator_scorecard["status"] == "candidate" and not evaluator_blocking_warnings,
            "blocking_warnings": evaluator_blocking_warnings,
            "approval_hint": "safe_to_rollout" if evaluator_scorecard["status"] == "candidate" and not evaluator_blocking_warnings else "stabilize_shadow_first",
        },
        "reranker": {
            "track": "reranker",
            "candidate_ready": reranker_scorecard["status"] == "candidate" and not reranker_blocking_warnings,
            "blocking_warnings": reranker_blocking_warnings,
            "approval_hint": "safe_to_rollout" if reranker_scorecard["status"] == "candidate" and not reranker_blocking_warnings else "stabilize_shadow_first",
        },
    }
    safe_rollout_candidates = [
        track
        for track, payload in rollout_readiness.items()
        if payload.get("candidate_ready")
    ]

    warnings = list(
        dict.fromkeys(
            list(summary.get("warnings", []))
            + list(evaluator_scorecard.get("warnings", []))
            + list(reranker_scorecard.get("warnings", []))
        )
    )

    return {
        "generated_at": summary.get("generated_at"),
        "filters": summary.get("filters", {}),
        "evaluator_status": evaluator_scorecard["status"],
        "reranker_status": reranker_scorecard["status"],
        "evaluator_scorecard": evaluator_scorecard,
        "reranker_scorecard": reranker_scorecard,
        "shared_weak_worlds": list(summary.get("shared_weak_worlds", [])),
        "shared_weak_issue_codes": list(summary.get("shared_weak_issue_codes", [])),
        "disagreement_worlds": disagreement_worlds,
        "disagreement_issue_codes": disagreement_issue_codes,
        "preferred_shadow_candidate": preferred_shadow_candidate,
        "recommended_next_action": recommended_next_action,
        "rollout_readiness": rollout_readiness,
        "safe_rollout_candidates": safe_rollout_candidates,
        "warnings": warnings,
    }


def build_learned_compare_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    dashboard_summary = build_learned_dashboard_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    return build_learned_compare_from_dashboard(dashboard_summary)
