from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .learned_compare import build_learned_compare_from_dashboard
from .learned_dashboard import build_learned_dashboard_summary


def _review_backlog_with_context(
    review_backlog: List[Dict[str, Any]],
    *,
    dashboard_summary: Dict[str, Any],
    compare_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    shared_weak_worlds = set(dashboard_summary.get("shared_weak_worlds", []))
    disagreement_issue_codes = {
        item["issue_code"] for item in compare_summary.get("disagreement_issue_codes", [])
    }
    disagreement_worlds = {
        item["world_id"]: item for item in compare_summary.get("disagreement_worlds", [])
    }
    focus_issue_codes = {"Q03", "Q04", "Q05", "Q09"}

    enriched: List[Dict[str, Any]] = []
    for item in review_backlog:
        issue_codes = list(item.get("issue_codes", []))
        issue_hits = sorted(set(issue_codes) & disagreement_issue_codes)
        world_compare_signal = disagreement_worlds.get(item["world_id"], {}).get("evaluator_signal")
        if item["world_id"] in shared_weak_worlds:
            recommended_action = "capture_human_review_priority"
        elif issue_hits:
            recommended_action = "resolve_evaluator_disagreement"
        elif item.get("decision") in {"block", "rewrite"} and set(issue_codes) & focus_issue_codes:
            recommended_action = "capture_human_review_now"
        else:
            recommended_action = "capture_human_review_now"
        enriched.append(
            {
                **item,
                "recommended_action": recommended_action,
                "shadow_context": {
                    "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
                    "recommended_next_action": compare_summary.get("recommended_next_action"),
                    "evaluator_status": compare_summary.get("evaluator_status"),
                    "reranker_status": compare_summary.get("reranker_status"),
                },
                "world_compare_signal": world_compare_signal or ("shared_weak_world" if item["world_id"] in shared_weak_worlds else "stable"),
                "issue_compare_signal": issue_hits or [],
                "compare_context": {
                    "shared_weak_world": item["world_id"] in shared_weak_worlds,
                    "disagreement_issue_codes": issue_hits,
                },
            }
        )
    return enriched


def _pair_backlog_with_context(
    pair_coverage_backlog: List[Dict[str, Any]],
    *,
    dashboard_summary: Dict[str, Any],
    compare_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    shared_weak_worlds = set(dashboard_summary.get("shared_weak_worlds", []))
    issue_details = {
        item["issue_code"]: item for item in dashboard_summary.get("issue_details", [])
    }
    enriched: List[Dict[str, Any]] = []
    for item in pair_coverage_backlog:
        issue_detail = issue_details.get(item["issue_code"], {})
        evaluator_error = issue_detail.get("evaluator_error_rate")
        reranker_error = issue_detail.get("reranker_error_rate")
        if item["world_id"] in shared_weak_worlds and item.get("coverage_count", 0) < 3:
            recommended_action = "expand_review_and_revision_coverage"
        elif reranker_error is not None and float(reranker_error) > 0.2 and (evaluator_error is None or float(evaluator_error) <= 0.2):
            recommended_action = "expand_issue_fix_pairs"
        elif item.get("coverage_count", 0) <= 0:
            recommended_action = "request_more_revisions"
        else:
            recommended_action = item.get("recommended_action", "expand_issue_fix_pairs")
        enriched.append(
            {
                **item,
                "recommended_action": recommended_action,
                "shadow_context": {
                    "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
                    "recommended_next_action": compare_summary.get("recommended_next_action"),
                },
            }
        )
    return enriched


def _action_queue(
    *,
    review_backlog: List[Dict[str, Any]],
    pair_coverage_backlog: List[Dict[str, Any]],
    dashboard_summary: Dict[str, Any],
    compare_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    shared_weak_worlds = set(dashboard_summary.get("shared_weak_worlds", []))
    disagreement_issue_codes = {
        item["issue_code"] for item in compare_summary.get("disagreement_issue_codes", [])
    }
    review_priority_rank = {"high": 0, "medium": 1, "low": 2}
    queue: List[Dict[str, Any]] = []

    for item in review_backlog:
        priority_bucket = 0 if item["world_id"] in shared_weak_worlds else 2
        if set(item.get("issue_codes", [])) & disagreement_issue_codes:
            priority_bucket = min(priority_bucket, 1)
        queue.append(
            {
                "action_type": "review_sample",
                "world_id": item["world_id"],
                "world_version_id": item["world_version_id"],
                "chapter_id": item["chapter_id"],
                "issue_codes": list(item.get("issue_codes", [])),
                "recommended_action": item["recommended_action"],
                "priority": item["priority"],
                "_sort": (
                    priority_bucket,
                    review_priority_rank.get(item["priority"], 3),
                    item["world_id"],
                    item["chapter_id"],
                ),
            }
        )

    for item in pair_coverage_backlog:
        priority_bucket = 0 if item["world_id"] in shared_weak_worlds else 3
        if item["issue_code"] in disagreement_issue_codes:
            priority_bucket = min(priority_bucket, 1)
        queue.append(
            {
                "action_type": "pair_coverage",
                "world_id": item["world_id"],
                "world_version_id": item["world_version_id"],
                "issue_code": item["issue_code"],
                "coverage_count": item["coverage_count"],
                "recommended_action": item["recommended_action"],
                "_sort": (
                    priority_bucket,
                    item["coverage_count"],
                    item["world_id"],
                    item["issue_code"],
                ),
            }
        )

    queue.sort(key=lambda item: item["_sort"])
    return [{key: value for key, value in item.items() if key != "_sort"} for item in queue]


def build_learned_data_ops_summary(
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
    training_signal = TrainingSignalService(repository)
    review_backlog = _review_backlog_with_context(
        training_signal.review_sample_backlog(
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        ),
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
    )
    pair_coverage_backlog = _pair_backlog_with_context(
        training_signal.issue_fix_pair_backlog(
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        ),
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
    )
    action_queue = _action_queue(
        review_backlog=review_backlog,
        pair_coverage_backlog=pair_coverage_backlog,
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
    )
    warnings = list(
        dict.fromkeys(
            list(dashboard_summary.get("warnings", []))
            + list(compare_summary.get("warnings", []))
        )
    )
    return {
        "generated_at": dashboard_summary.get("generated_at"),
        "filters": dashboard_summary.get("filters", {}),
        "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
        "recommended_next_action": compare_summary.get("recommended_next_action"),
        "review_sample_backlog": review_backlog,
        "pair_coverage_backlog": pair_coverage_backlog,
        "coverage_gaps": {
            "review_sample_backlog_count": len(review_backlog),
            "pair_coverage_backlog_count": len(pair_coverage_backlog),
            "shared_weak_worlds": list(dashboard_summary.get("shared_weak_worlds", [])),
            "shared_weak_issue_codes": list(dashboard_summary.get("shared_weak_issue_codes", [])),
            "disagreement_world_count": len(compare_summary.get("disagreement_worlds", [])),
            "disagreement_issue_count": len(compare_summary.get("disagreement_issue_codes", [])),
        },
        "action_queue": action_queue[:limit] if limit is not None else action_queue,
        "warnings": warnings,
    }
