from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.review import parse_review_notes
from .learned_compare import build_learned_compare_summary
from .learned_promotion_workflow import build_evaluator_promotion_workflow_summary
from .learned_reranker_promotion_workflow import build_reranker_promotion_workflow_summary


ROLLOUT_ASSET_TYPE = "learned_rollout"
VALID_TRACKS = {"evaluator", "reranker"}


def _track_promotion_workflow(
    *,
    track: str,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track == "evaluator":
        return build_evaluator_promotion_workflow_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=evaluator_artifact_dir,
            reranker_artifact_dir=reranker_artifact_dir,
        )
    return build_reranker_promotion_workflow_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )


def _latest_rollout_record(repository: SQLAlchemyPlatformRepository, *, track: str) -> Optional[Dict[str, Any]]:
    records = repository.list_review_records(asset_type=ROLLOUT_ASSET_TYPE, asset_id=track)
    if not records:
        return None
    record = dict(records[0])
    notes = parse_review_notes(record.get("notes"))
    return {
        "review_id": record.get("review_id"),
        "track": track,
        "status": record.get("status"),
        "reviewer_id": record.get("reviewer_id"),
        "updated_at": record.get("updated_at"),
        "reason": notes.get("reason"),
        "artifact_state": dict(notes.get("artifact_state", {})),
        "promotion_snapshot": dict(notes.get("promotion_snapshot", {})),
        "compare_snapshot": dict(notes.get("compare_snapshot", {})),
        "previous_status": notes.get("previous_status"),
        "rollback_target": notes.get("rollback_target"),
        "notes": notes,
    }


def _normalize_rollout_status(record: Optional[Dict[str, Any]]) -> str:
    if record is None:
        return "shadow"
    status = str(record.get("status") or "shadow")
    return status if status in {"shadow", "active", "rolled_back"} else "shadow"


def build_learned_rollout_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    compare_summary = build_learned_compare_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    tracks: Dict[str, Dict[str, Any]] = {}
    active_tracks = []
    rollback_watchlist = []
    safe_rollout_candidates = []

    for track in sorted(VALID_TRACKS):
        promotion_workflow = _track_promotion_workflow(
            track=track,
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=evaluator_artifact_dir,
            reranker_artifact_dir=reranker_artifact_dir,
        )
        latest_record = _latest_rollout_record(repository, track=track)
        rollout_status = _normalize_rollout_status(latest_record)
        candidate_ready = bool(compare_summary.get("rollout_readiness", {}).get(track, {}).get("candidate_ready"))
        approval_status = promotion_workflow.get("approval_status")
        latest_approval_status = (promotion_workflow.get("latest_approval_record") or {}).get("status")
        recommendation_status = promotion_workflow.get("recommendation_status")
        artifact_present = bool(promotion_workflow.get("evidence", {}))
        safe_to_rollout = artifact_present and latest_approval_status == "approved"

        if rollout_status == "active":
            active_tracks.append(track)
            if approval_status in {"stale", "revoked"} or not candidate_ready:
                rollback_watchlist.append(track)

        if safe_to_rollout:
            safe_rollout_candidates.append(track)

        if rollout_status == "active":
            recommended_action = "monitor_active_rollout"
        elif safe_to_rollout:
            recommended_action = "promote_shadow_candidate" if candidate_ready else "activate_with_watchlist"
        elif track in rollback_watchlist:
            recommended_action = "rollback_active_rollout"
        else:
            recommended_action = promotion_workflow.get("recommended_action")

        tracks[track] = {
            "track": track,
            "rollout_status": rollout_status,
            "promotion_workflow": promotion_workflow,
            "latest_rollout_record": latest_record,
            "safe_to_rollout": safe_to_rollout,
            "candidate_ready": candidate_ready,
            "latest_approval_status": latest_approval_status,
            "artifact_present": artifact_present,
            "recommended_action": recommended_action,
        }

    if rollback_watchlist:
        recommended_next_action = "rollback_active_rollout"
    elif compare_summary.get("preferred_shadow_candidate") in safe_rollout_candidates:
        recommended_next_action = "promote_preferred_shadow_candidate"
    elif safe_rollout_candidates:
        recommended_next_action = "promote_available_shadow_candidate"
    else:
        recommended_next_action = compare_summary.get("recommended_next_action")

    return {
        "generated_at": compare_summary.get("generated_at"),
        "filters": compare_summary.get("filters", {}),
        "tracks": tracks,
        "active_tracks": active_tracks,
        "safe_rollout_candidates": safe_rollout_candidates,
        "rollback_watchlist": rollback_watchlist,
        "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
        "recommended_next_action": recommended_next_action,
    }


def _save_rollout_record(
    *,
    repository: SQLAlchemyPlatformRepository,
    track: str,
    status: str,
    reviewer_id: str,
    reason: str,
    promotion_workflow: Dict[str, Any],
    compare_summary: Dict[str, Any],
    previous_status: Optional[str] = None,
    rollback_target: Optional[str] = None,
) -> Dict[str, Any]:
    notes = json.dumps(
        {
            "track": track,
            "reason": reason,
            "artifact_state": dict(promotion_workflow.get("evidence", {})),
            "promotion_snapshot": {
                "recommendation_status": promotion_workflow.get("recommendation_status"),
                "approval_status": promotion_workflow.get("approval_status"),
                "recommended_action": promotion_workflow.get("recommended_action"),
                "checklist": promotion_workflow.get("checklist", []),
                "evidence": promotion_workflow.get("evidence", {}),
            },
            "compare_snapshot": {
                "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
                "recommended_next_action": compare_summary.get("recommended_next_action"),
                "safe_rollout_candidates": compare_summary.get("safe_rollout_candidates", []),
            },
            "previous_status": previous_status,
            "rollback_target": rollback_target,
        },
        ensure_ascii=False,
    )
    return repository.save_review_record(
        {
            "asset_type": ROLLOUT_ASSET_TYPE,
            "asset_id": track,
            "status": status,
            "reviewer_id": reviewer_id,
            "notes": notes,
        }
    )


def activate_learned_rollout(
    *,
    repository: SQLAlchemyPlatformRepository,
    track: str,
    reviewer_id: str,
    reason: str,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track not in VALID_TRACKS:
        raise ValueError("invalid_rollout_track")
    summary = build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    track_summary = summary["tracks"][track]
    if not track_summary.get("safe_to_rollout"):
        raise ValueError("rollout_not_safe")
    latest_record = track_summary.get("latest_rollout_record")
    _save_rollout_record(
        repository=repository,
        track=track,
        status="active",
        reviewer_id=reviewer_id,
        reason=reason,
        promotion_workflow=track_summary["promotion_workflow"],
        compare_summary=summary,
        previous_status=latest_record.get("status") if latest_record else "shadow",
        rollback_target=latest_record.get("status") if latest_record else "shadow",
    )
    return build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )


def rollback_learned_rollout(
    *,
    repository: SQLAlchemyPlatformRepository,
    track: str,
    reviewer_id: str,
    reason: str,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track not in VALID_TRACKS:
        raise ValueError("invalid_rollout_track")
    summary = build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    track_summary = summary["tracks"][track]
    latest_record = track_summary.get("latest_rollout_record")
    if not latest_record or track_summary.get("rollout_status") != "active":
        raise ValueError("rollout_not_active")
    _save_rollout_record(
        repository=repository,
        track=track,
        status="rolled_back",
        reviewer_id=reviewer_id,
        reason=reason,
        promotion_workflow=track_summary["promotion_workflow"],
        compare_summary=summary,
        previous_status="active",
        rollback_target=latest_record.get("status"),
    )
    return build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
