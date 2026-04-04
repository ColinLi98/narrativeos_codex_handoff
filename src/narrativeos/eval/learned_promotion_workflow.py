from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.review import parse_review_notes
from .learned_promotion import build_evaluator_promotion_summary


PROMOTION_ASSET_TYPE = "learned_promotion"
PROMOTION_ASSET_ID = "evaluator"


def _latest_approval_record(repository: SQLAlchemyPlatformRepository) -> Optional[Dict[str, Any]]:
    records = repository.list_review_records(asset_type=PROMOTION_ASSET_TYPE, asset_id=PROMOTION_ASSET_ID)
    if not records:
        return None
    record = dict(records[0])
    payload = parse_review_notes(record.get("notes"))
    return {
        "review_id": record.get("review_id"),
        "status": record.get("status"),
        "reviewer_id": record.get("reviewer_id"),
        "updated_at": record.get("updated_at"),
        "track": payload.get("track", "evaluator"),
        "scope": payload.get("scope", "global"),
        "reason": payload.get("reason"),
        "recommendation_snapshot": payload.get("recommendation_snapshot", {}),
        "blockers_at_decision": list(payload.get("blockers_at_decision", [])),
        "advisories_at_decision": list(payload.get("advisories_at_decision", [])),
    }


def _approval_status(
    latest_record: Optional[Dict[str, Any]],
    *,
    recommendation_status: str,
) -> tuple[str, bool]:
    if latest_record is None:
        return "unapproved", False
    record_status = str(latest_record.get("status") or "")
    if record_status == "revoked":
        return "revoked", False
    if record_status != "approved":
        return "unapproved", False
    if recommendation_status == "eligible":
        return "approved", False
    return "stale", True


def build_evaluator_promotion_workflow_from_recommendation(
    *,
    recommendation: Dict[str, Any],
    latest_record: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    recommendation_status = str(recommendation.get("status") or "blocked")
    approval_status, reconfirm_required = _approval_status(
        latest_record,
        recommendation_status=recommendation_status,
    )

    if approval_status == "approved":
        recommended_action = "monitor_promoted_evaluator"
    elif approval_status == "stale":
        recommended_action = "reconfirm_evaluator_promotion"
    elif approval_status == "revoked":
        recommended_action = "rebuild_evaluator_readiness"
    else:
        recommended_action = recommendation.get("recommended_action")

    return {
        "generated_at": recommendation.get("generated_at"),
        "filters": recommendation.get("filters", {}),
        "track": "evaluator",
        "scope": "global",
        "mode": "manual_approval",
        "recommendation_status": recommendation_status,
        "status": recommendation_status,
        "recommended_action": recommended_action,
        "approval_status": approval_status,
        "reconfirm_required": reconfirm_required,
        "latest_approval_record": latest_record,
        "blockers": list(recommendation.get("blockers", [])),
        "advisories": list(recommendation.get("advisories", [])),
        "checklist": list(recommendation.get("checklist", [])),
        "evidence": dict(recommendation.get("evidence", {})),
    }


def build_evaluator_promotion_workflow_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    recommendation = build_evaluator_promotion_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    latest_record = _latest_approval_record(repository)
    return build_evaluator_promotion_workflow_from_recommendation(
        recommendation=recommendation,
        latest_record=latest_record,
    )


def save_evaluator_promotion_decision(
    *,
    repository: SQLAlchemyPlatformRepository,
    reviewer_id: str,
    reason: str,
    status: str,
    recommendation_summary: Dict[str, Any],
) -> Dict[str, Any]:
    notes = json.dumps(
        {
            "track": "evaluator",
            "scope": "global",
            "reviewer_id": reviewer_id,
            "reason": reason,
            "recommendation_snapshot": {
                "recommendation_status": recommendation_summary.get("recommendation_status"),
                "recommended_action": recommendation_summary.get("recommended_action"),
                "checklist": recommendation_summary.get("checklist", []),
                "evidence": recommendation_summary.get("evidence", {}),
            },
            "blockers_at_decision": recommendation_summary.get("blockers", []),
            "advisories_at_decision": recommendation_summary.get("advisories", []),
        },
        ensure_ascii=False,
    )
    return repository.save_review_record(
        {
            "asset_type": PROMOTION_ASSET_TYPE,
            "asset_id": PROMOTION_ASSET_ID,
            "status": status,
            "reviewer_id": reviewer_id,
            "notes": notes,
        }
    )
