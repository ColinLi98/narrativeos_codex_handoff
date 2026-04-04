from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_learned_data_impact_receipt(
    *,
    before_summary: Dict[str, Any],
    after_summary: Dict[str, Any],
    review_sample: Dict[str, Any],
) -> Dict[str, Any]:
    chapter_id = str(review_sample.get("chapter_id") or "")
    review_backlog_before = list(before_summary.get("review_sample_backlog", []))
    review_backlog_after = list(after_summary.get("review_sample_backlog", []))
    pair_backlog_before = list(before_summary.get("pair_coverage_backlog", []))
    pair_backlog_after = list(after_summary.get("pair_coverage_backlog", []))
    action_queue_before = list(before_summary.get("action_queue", []))
    action_queue_after = list(after_summary.get("action_queue", []))

    return {
        "generated_at": _utcnow(),
        "world_id": review_sample.get("world_id"),
        "world_version_id": review_sample.get("world_version_id"),
        "chapter_id": chapter_id,
        "action_type": "review_sample",
        "review_sample_id": review_sample.get("sample_id"),
        "preferred_shadow_candidate_before": before_summary.get("preferred_shadow_candidate"),
        "preferred_shadow_candidate_after": after_summary.get("preferred_shadow_candidate"),
        "recommended_next_action_before": before_summary.get("recommended_next_action"),
        "recommended_next_action_after": after_summary.get("recommended_next_action"),
        "review_backlog_count_before": len(review_backlog_before),
        "review_backlog_count_after": len(review_backlog_after),
        "pair_backlog_count_before": len(pair_backlog_before),
        "pair_backlog_count_after": len(pair_backlog_after),
        "action_queue_count_before": len(action_queue_before),
        "action_queue_count_after": len(action_queue_after),
        "cleared_backlog_target": any(item.get("chapter_id") == chapter_id for item in review_backlog_before)
        and all(item.get("chapter_id") != chapter_id for item in review_backlog_after),
        "warnings_before": list(before_summary.get("warnings", [])),
        "warnings_after": list(after_summary.get("warnings", [])),
    }
