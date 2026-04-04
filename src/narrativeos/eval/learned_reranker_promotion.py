from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .learned_compare import build_learned_compare_from_dashboard
from .learned_dashboard import build_learned_dashboard_summary
from .learned_data_ops import build_learned_data_ops_summary


CRITICAL_RERANKER_WARNINGS = {
    "artifact_missing",
    "artifact_present_but_incomplete",
    "artifact_load_failed",
    "single_class_train_fallback_dummy",
    "insufficient_reranker_pairs",
}


def _reason(ok: bool, success_reason: str, failure_reason: str) -> str:
    return success_reason if ok else failure_reason


def build_reranker_promotion_from_summaries(
    *,
    dashboard_summary: Dict[str, Any],
    compare_summary: Dict[str, Any],
    data_ops_summary: Dict[str, Any],
) -> Dict[str, Any]:
    reranker_shadow = dict(dashboard_summary.get("reranker_shadow_summary", {}))
    reranker_scorecard = dict(compare_summary.get("reranker_scorecard", {}))
    artifact_present = bool(reranker_shadow.get("artifact_present"))
    reranker_status = str(reranker_shadow.get("status") or "unavailable")
    preferred_shadow_candidate = str(compare_summary.get("preferred_shadow_candidate") or "neither")
    reranker_warnings = list(reranker_shadow.get("warnings", []))
    critical_warnings = sorted(set(reranker_warnings) & CRITICAL_RERANKER_WARNINGS)

    review_backlog_count = int(data_ops_summary.get("coverage_gaps", {}).get("review_sample_backlog_count", 0) or 0)
    pair_backlog_count = int(data_ops_summary.get("coverage_gaps", {}).get("pair_coverage_backlog_count", 0) or 0)
    disagreement_world_count = int(data_ops_summary.get("coverage_gaps", {}).get("disagreement_world_count", 0) or 0)
    disagreement_issue_count = int(data_ops_summary.get("coverage_gaps", {}).get("disagreement_issue_count", 0) or 0)
    shared_weak_worlds = list(data_ops_summary.get("coverage_gaps", {}).get("shared_weak_worlds", []))

    blockers = []
    if not artifact_present:
        blockers.append("artifact_not_ready")
    if reranker_status != "candidate":
        blockers.append(f"shadow_status_{reranker_status}")
    if preferred_shadow_candidate != "reranker":
        blockers.append(f"compare_prefers_{preferred_shadow_candidate}")
    if critical_warnings:
        blockers.extend(f"critical_warning::{warning}" for warning in critical_warnings)

    advisories = []
    if pair_backlog_count > 0:
        advisories.append("pair_backlog_remaining")
    if disagreement_issue_count > 0:
        advisories.append("disagreement_issues_remaining")
    if shared_weak_worlds:
        advisories.append("shared_weak_worlds_remaining")

    if blockers:
        status = "blocked"
    elif advisories:
        status = "watching"
    else:
        status = "eligible"

    if status == "eligible":
        recommended_action = "promote_reranker_shadow_candidate"
    elif status == "watching":
        recommended_action = "clear_remaining_pair_backlog"
    elif not artifact_present or any(warning.startswith("critical_warning::artifact_") for warning in blockers):
        recommended_action = "repair_reranker_artifact"
    elif reranker_status == "warming_up":
        recommended_action = "expand_issue_fix_pairs"
    else:
        recommended_action = "inspect_low_accuracy_worlds"

    checklist = [
        {
            "key": "artifact_ready",
            "ok": artifact_present,
            "reason": _reason(artifact_present, "artifact_present", "artifact_missing_or_incomplete"),
        },
        {
            "key": "shadow_status_candidate",
            "ok": reranker_status == "candidate",
            "reason": _reason(reranker_status == "candidate", "status_candidate", f"status_{reranker_status}"),
        },
        {
            "key": "compare_prefers_reranker",
            "ok": preferred_shadow_candidate == "reranker",
            "reason": _reason(
                preferred_shadow_candidate == "reranker",
                "compare_prefers_reranker",
                f"compare_prefers_{preferred_shadow_candidate}",
            ),
        },
        {
            "key": "critical_warnings_cleared",
            "ok": not critical_warnings,
            "reason": _reason(not critical_warnings, "no_critical_warnings", ",".join(critical_warnings) or "critical_warning_present"),
        },
        {
            "key": "pair_backlog_cleared",
            "ok": pair_backlog_count == 0,
            "reason": _reason(pair_backlog_count == 0, "pair_backlog_cleared", f"pair_backlog_count_{pair_backlog_count}"),
        },
        {
            "key": "disagreement_issues_cleared",
            "ok": disagreement_issue_count == 0,
            "reason": _reason(
                disagreement_issue_count == 0,
                "disagreement_issues_cleared",
                f"disagreement_issue_count_{disagreement_issue_count}",
            ),
        },
    ]

    evidence = {
        "average_world_accuracy": reranker_scorecard.get("average_world_accuracy"),
        "low_error_world_count": int(reranker_scorecard.get("low_error_world_count", 0) or 0),
        "train_count": int(reranker_shadow.get("train_count", 0) or 0),
        "val_count": int(reranker_shadow.get("val_count", 0) or 0),
        "test_count": int(reranker_shadow.get("test_count", 0) or 0),
        "preferred_shadow_candidate": preferred_shadow_candidate,
        "review_backlog_count": review_backlog_count,
        "pair_backlog_count": pair_backlog_count,
        "disagreement_world_count": disagreement_world_count,
        "disagreement_issue_count": disagreement_issue_count,
    }

    return {
        "generated_at": dashboard_summary.get("generated_at"),
        "filters": dashboard_summary.get("filters", {}),
        "track": "reranker",
        "scope": "global",
        "mode": "recommend_only",
        "status": status,
        "recommended_action": recommended_action,
        "blockers": blockers,
        "advisories": advisories,
        "checklist": checklist,
        "evidence": evidence,
    }


def build_reranker_promotion_summary(
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
    compare_summary = build_learned_compare_from_dashboard(dashboard_summary)
    data_ops_summary = build_learned_data_ops_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    return build_reranker_promotion_from_summaries(
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
        data_ops_summary=data_ops_summary,
    )
