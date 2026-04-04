from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .artifact_registry import (
    default_learned_evaluator_artifact_dir,
    default_learned_reranker_artifact_dir,
    load_published_artifact_state,
)
from .learned_compare import build_learned_compare_summary
from .learned_data_ops import build_learned_data_ops_summary
from .learned_impact import build_learned_impact_summary
from .learned_promotion_workflow import build_evaluator_promotion_workflow_summary
from .learned_reranker_promotion_workflow import build_reranker_promotion_workflow_summary
from .learned_rollout import build_learned_rollout_summary


VALID_TRACKS = {"evaluator", "reranker"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _artifact_dirs(
    *,
    base_dir: Path,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    return {
        "evaluator": Path(evaluator_artifact_dir) if evaluator_artifact_dir else default_learned_evaluator_artifact_dir(base_dir),
        "reranker": Path(reranker_artifact_dir) if reranker_artifact_dir else default_learned_reranker_artifact_dir(base_dir),
    }


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _track_training_runs(*, base_dir: Path, track: str) -> List[Dict[str, Any]]:
    root = Path(base_dir) / "artifacts" / "learned_training_runs"
    if not root.exists():
        return []
    runs: List[Dict[str, Any]] = []
    for summary_path in sorted(root.glob("run_*/learned_training_automation_summary.json")):
        payload = _safe_load_json(summary_path)
        summary = dict(payload.get("summary") or {})
        training_payload = dict((payload.get("training_results") or {}).get(track) or {})
        if not training_payload:
            continue
        result = dict(training_payload.get("result") or {})
        training_manifest = dict(result.get("training_manifest") or {})
        published_manifest = dict(result.get("published_artifact_manifest") or {})
        evidence_payload = dict((payload.get("evidence_results") or {}).get(track) or {})
        generated_at = (
            training_manifest.get("generated_at")
            or published_manifest.get("published_at")
            or summary.get("generated_at")
        )
        runs.append(
            {
                "track": track,
                "run_id": summary.get("run_id") or summary_path.parent.name,
                "status": training_payload.get("status") or "unknown",
                "generated_at": generated_at,
                "output_dir": result.get("output_dir") or str(summary_path.parent / track),
                "dataset_view": training_manifest.get("dataset_view") or published_manifest.get("dataset_view"),
                "train_count": int(training_manifest.get("train_count", 0) or 0),
                "val_count": int(training_manifest.get("val_count", 0) or 0),
                "test_count": int(training_manifest.get("test_count", 0) or 0),
                "warnings": list(training_manifest.get("warnings", []) or training_payload.get("warnings", [])),
                "error": training_payload.get("error"),
                "evidence_path": evidence_payload.get("evidence_path"),
            }
        )
    runs.sort(
        key=lambda item: (
            _parse_timestamp(item.get("generated_at")) or datetime.min.replace(tzinfo=timezone.utc),
            item.get("run_id") or "",
        ),
        reverse=True,
    )
    return runs


def _latest_timestamp(values: Sequence[Optional[str]]) -> Optional[str]:
    parsed = [item for item in (_parse_timestamp(value) for value in values) if item is not None]
    if not parsed:
        return None
    return max(parsed).isoformat()


def _hours_since(value: Optional[str]) -> Optional[float]:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    delta = datetime.now(timezone.utc) - parsed
    return round(max(delta.total_seconds(), 0.0) / 3600.0, 2)


def _count_unique(items: Sequence[Dict[str, Any]], key: str) -> int:
    return len({str(item.get(key) or "") for item in items if str(item.get(key) or "")})


def _count_issue_coverage(items: Sequence[Dict[str, Any]], key: str = "linked_issue_codes") -> int:
    issue_codes = set()
    for item in items:
        for issue_code in item.get(key) or []:
            issue_codes.add(str(issue_code))
    return len(issue_codes)


def _freshness_summary(*, latest_sample_at: Optional[str], trained_at: Optional[str], artifact_present: bool) -> Dict[str, Any]:
    if not artifact_present:
        return {
            "status": "artifact_missing",
            "latest_sample_at": latest_sample_at,
            "trained_at": trained_at,
            "data_newer_than_artifact": bool(latest_sample_at),
        }
    latest_sample_dt = _parse_timestamp(latest_sample_at)
    trained_dt = _parse_timestamp(trained_at)
    if latest_sample_dt is None or trained_dt is None:
        return {
            "status": "freshness_unknown",
            "latest_sample_at": latest_sample_at,
            "trained_at": trained_at,
            "data_newer_than_artifact": False,
        }
    data_newer = latest_sample_dt > trained_dt
    return {
        "status": "stale_vs_samples" if data_newer else "fresh_vs_samples",
        "latest_sample_at": latest_sample_at,
        "trained_at": trained_at,
        "data_newer_than_artifact": data_newer,
    }


def _track_stage(
    *,
    relevant_example_count: int,
    artifact_present: bool,
    freshness: Dict[str, Any],
    latest_training_run: Optional[Dict[str, Any]],
    shadow_status: str,
    recommendation_status: str,
    approval_status: str,
    rollout_status: str,
    safe_to_rollout: bool,
    candidate_ready: bool,
) -> str:
    if rollout_status == "active":
        return "monitor_active"
    if rollout_status == "rolled_back" or approval_status == "revoked":
        return "rebuild_readiness"
    if relevant_example_count <= 0:
        return "collect_data"
    if (latest_training_run or {}).get("status") == "failed":
        return "train_candidate"
    if not artifact_present or freshness.get("data_newer_than_artifact"):
        return "train_candidate"
    if shadow_status != "candidate":
        return "validate_shadow"
    if safe_to_rollout and candidate_ready:
        return "ready_to_activate"
    if recommendation_status == "eligible" and approval_status in {"unapproved", "stale"}:
        return "request_promotion"
    return "validate_shadow"


def _track_next_action(
    *,
    track: str,
    stage: str,
    review_backlog_count: int,
    pair_backlog_count: int,
    promotion_workflow: Dict[str, Any],
    rollout_track: Dict[str, Any],
) -> str:
    if stage == "collect_data":
        if track == "evaluator":
            return "capture_human_review_priority" if review_backlog_count else "add_review_samples"
        return "expand_issue_fix_pairs" if pair_backlog_count else "capture_preference_rankings"
    if stage == "train_candidate":
        return f"run_{track}_training"
    if stage == "request_promotion":
        if promotion_workflow.get("approval_status") == "stale":
            return promotion_workflow.get("recommended_action") or f"reconfirm_{track}_promotion"
        return f"approve_{track}_promotion"
    if stage == "ready_to_activate":
        return f"activate_{track}_rollout"
    if stage == "monitor_active":
        return rollout_track.get("recommended_action") or "monitor_active_rollout"
    if stage == "rebuild_readiness":
        return promotion_workflow.get("recommended_action") or "rebuild_readiness"
    return promotion_workflow.get("recommended_action") or rollout_track.get("recommended_action") or "inspect_shadow_candidate"


def _split_health(*, artifact_state: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = dict(artifact_state.get("training_manifest") or {})
    train_count = int(training_manifest.get("train_count", 0) or 0)
    val_count = int(training_manifest.get("val_count", 0) or 0)
    test_count = int(training_manifest.get("test_count", 0) or 0)
    if train_count <= 0:
        status = "train_empty"
    elif val_count <= 0 or test_count <= 0:
        status = "validation_incomplete"
    else:
        status = "ready"
    return {
        "status": status,
        "train_count": train_count,
        "val_count": val_count,
        "test_count": test_count,
    }


def _recent_events(
    *,
    latest_sample_at: Optional[str],
    latest_training_run: Optional[Dict[str, Any]],
    recent_training_runs: Sequence[Dict[str, Any]],
    promotion_workflow: Dict[str, Any],
    rollout_track: Dict[str, Any],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if latest_sample_at:
        events.append(
            {
                "event_type": "sample_ingested",
                "occurred_at": latest_sample_at,
                "status": "captured",
                "headline": "Latest sample captured",
                "summary": latest_sample_at,
            }
        )
    for item in list(recent_training_runs)[:3]:
        events.append(
            {
                "event_type": "training_run",
                "occurred_at": item.get("generated_at"),
                "status": item.get("status"),
                "headline": f"Training {item.get('status')}",
                "summary": f"{item.get('run_id') or '-'} · {item.get('train_count', 0)}/{item.get('val_count', 0)}/{item.get('test_count', 0)}",
            }
        )
    latest_approval = dict(promotion_workflow.get("latest_approval_record") or {})
    if latest_approval:
        events.append(
            {
                "event_type": "promotion_decision",
                "occurred_at": latest_approval.get("updated_at"),
                "status": latest_approval.get("status"),
                "headline": f"Promotion {latest_approval.get('status')}",
                "summary": latest_approval.get("reason") or latest_approval.get("reviewer_id") or "-",
            }
        )
    latest_rollout = dict(rollout_track.get("latest_rollout_record") or {})
    if latest_rollout:
        events.append(
            {
                "event_type": "rollout_event",
                "occurred_at": latest_rollout.get("updated_at"),
                "status": latest_rollout.get("status"),
                "headline": f"Rollout {latest_rollout.get('status')}",
                "summary": latest_rollout.get("reason") or latest_rollout.get("reviewer_id") or "-",
            }
        )
    events.sort(
        key=lambda item: _parse_timestamp(item.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return events[:5]


def _cadence_health(
    *,
    cadence_stage: str,
    freshness: Dict[str, Any],
    latest_training_run: Optional[Dict[str, Any]],
    promotion_workflow: Dict[str, Any],
    rollout_track: Dict[str, Any],
) -> Dict[str, Any]:
    stale_reasons: List[str] = []
    if freshness.get("data_newer_than_artifact"):
        stale_reasons.append("artifact_stale_vs_samples")
    if latest_training_run and latest_training_run.get("status") == "failed":
        stale_reasons.append("latest_training_failed")
    if promotion_workflow.get("approval_status") == "stale":
        stale_reasons.append("promotion_approval_stale")
    if rollout_track.get("rollout_status") == "rolled_back":
        stale_reasons.append("rollout_rolled_back")
    if cadence_stage == "collect_data":
        health = "needs_data"
    elif stale_reasons:
        health = "attention"
    elif cadence_stage in {"ready_to_activate", "monitor_active"}:
        health = "ready"
    else:
        health = "in_progress"
    return {
        "status": health,
        "stale_reasons": stale_reasons,
    }


def _track_summary(
    *,
    track: str,
    trainable_examples: Sequence[Dict[str, Any]],
    latest_sample_at: Optional[str],
    source_sample_counts: Dict[str, int],
    data_ops_summary: Dict[str, Any],
    impact_track_summary: Dict[str, Any],
    artifact_state: Dict[str, Any],
    latest_training_run: Optional[Dict[str, Any]],
    recent_training_runs: Sequence[Dict[str, Any]],
    promotion_workflow: Dict[str, Any],
    rollout_track: Dict[str, Any],
    compare_summary: Dict[str, Any],
) -> Dict[str, Any]:
    coverage_gaps = dict(data_ops_summary.get("coverage_gaps", {}))
    relevant_backlog_count = (
        int(coverage_gaps.get("review_sample_backlog_count", 0) or 0)
        if track == "evaluator"
        else int(coverage_gaps.get("pair_coverage_backlog_count", 0) or 0)
    )
    shadow_metric = (
        promotion_workflow.get("evidence", {}).get("agreement_rate")
        if track == "evaluator"
        else promotion_workflow.get("evidence", {}).get("average_world_accuracy")
    )
    shadow_status = (
        "candidate" if rollout_track.get("candidate_ready") else (
            "unavailable" if not artifact_state.get("artifact_present") else promotion_workflow.get("recommendation_status", "blocked")
        )
    )
    freshness = _freshness_summary(
        latest_sample_at=latest_sample_at,
        trained_at=artifact_state.get("trained_at"),
        artifact_present=bool(artifact_state.get("artifact_present")),
    )
    cadence_stage = _track_stage(
        relevant_example_count=len(trainable_examples),
        artifact_present=bool(artifact_state.get("artifact_present")),
        freshness=freshness,
        latest_training_run=latest_training_run,
        shadow_status=shadow_status,
        recommendation_status=str(promotion_workflow.get("recommendation_status") or "blocked"),
        approval_status=str(promotion_workflow.get("approval_status") or "unapproved"),
        rollout_status=str(rollout_track.get("rollout_status") or "shadow"),
        safe_to_rollout=bool(rollout_track.get("safe_to_rollout")),
        candidate_ready=bool(rollout_track.get("candidate_ready")),
    )
    recommended_next_action = _track_next_action(
        track=track,
        stage=cadence_stage,
        review_backlog_count=int(coverage_gaps.get("review_sample_backlog_count", 0) or 0),
        pair_backlog_count=int(coverage_gaps.get("pair_coverage_backlog_count", 0) or 0),
        promotion_workflow=promotion_workflow,
        rollout_track=rollout_track,
    )
    split_health = _split_health(artifact_state=artifact_state)
    cadence_health = _cadence_health(
        cadence_stage=cadence_stage,
        freshness=freshness,
        latest_training_run=latest_training_run,
        promotion_workflow=promotion_workflow,
        rollout_track=rollout_track,
    )
    approval_record = dict(promotion_workflow.get("latest_approval_record") or {})
    rollout_record = dict(rollout_track.get("latest_rollout_record") or {})
    warnings = list(
        dict.fromkeys(
            list(artifact_state.get("warnings", []))
            + list(impact_track_summary.get("warnings", []))
            + ([f"latest_training_failed::{latest_training_run.get('error')}"] if latest_training_run and latest_training_run.get("status") == "failed" and latest_training_run.get("error") else [])
        )
    )
    return {
        "track": track,
        "dataset_view": "evaluator" if track == "evaluator" else "reranker",
        "cadence_stage": cadence_stage,
        "recommended_next_action": recommended_next_action,
        "relevant_example_count": len(trainable_examples),
        "world_coverage_count": _count_unique(trainable_examples, "world_id"),
        "issue_coverage_count": _count_issue_coverage(trainable_examples),
        "latest_sample_at": latest_sample_at,
        "source_sample_counts": source_sample_counts,
        "latest_training_run": latest_training_run,
        "recent_training_runs": list(recent_training_runs),
        "artifact_state": {
            "available": bool(artifact_state.get("available")),
            "artifact_present": bool(artifact_state.get("artifact_present")),
            "published_at": artifact_state.get("published_at"),
            "trained_at": artifact_state.get("trained_at"),
            "reason": artifact_state.get("reason"),
            "warnings": list(artifact_state.get("warnings", [])),
        },
        "freshness": freshness,
        "cadence_health": cadence_health["status"],
        "stale_reasons": cadence_health["stale_reasons"],
        "validation_summary": {
            "shadow_status": shadow_status,
            "shadow_agreement_or_accuracy": shadow_metric,
            "preferred_shadow_candidate": compare_summary.get("preferred_shadow_candidate"),
            "impact_status": impact_track_summary.get("impact_status"),
            "evidence_sufficiency": impact_track_summary.get("evidence_sufficiency"),
        },
        "checkpoint_summary": {
            "split_status": split_health["status"],
            "train_count": split_health["train_count"],
            "val_count": split_health["val_count"],
            "test_count": split_health["test_count"],
            "freshness_status": freshness.get("status"),
            "approval_status": promotion_workflow.get("approval_status"),
            "rollout_status": rollout_track.get("rollout_status"),
        },
        "promotion_summary": {
            "recommendation_status": promotion_workflow.get("recommendation_status"),
            "approval_status": promotion_workflow.get("approval_status"),
            "reconfirm_required": bool(promotion_workflow.get("reconfirm_required")),
            "recommended_action": promotion_workflow.get("recommended_action"),
            "latest_approval_at": approval_record.get("updated_at"),
            "hours_since_approval": _hours_since(approval_record.get("updated_at")),
        },
        "rollout_summary": {
            "rollout_status": rollout_track.get("rollout_status"),
            "safe_to_rollout": bool(rollout_track.get("safe_to_rollout")),
            "candidate_ready": bool(rollout_track.get("candidate_ready")),
            "latest_approval_status": rollout_track.get("latest_approval_status"),
            "recommended_action": rollout_track.get("recommended_action"),
            "latest_rollout_at": rollout_record.get("updated_at"),
            "hours_since_rollout": _hours_since(rollout_record.get("updated_at")),
        },
        "coverage_gaps": {
            "review_sample_backlog_count": int(coverage_gaps.get("review_sample_backlog_count", 0) or 0),
            "pair_coverage_backlog_count": int(coverage_gaps.get("pair_coverage_backlog_count", 0) or 0),
            "disagreement_world_count": int(coverage_gaps.get("disagreement_world_count", 0) or 0),
            "disagreement_issue_count": int(coverage_gaps.get("disagreement_issue_count", 0) or 0),
            "relevant_backlog_count": relevant_backlog_count,
        },
        "recent_events": _recent_events(
            latest_sample_at=latest_sample_at,
            latest_training_run=latest_training_run,
            recent_training_runs=recent_training_runs,
            promotion_workflow=promotion_workflow,
            rollout_track=rollout_track,
        ),
        "warnings": warnings,
    }


def build_learned_cadence_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    base_dir = Path(__file__).resolve().parents[3]
    artifact_dirs = _artifact_dirs(
        base_dir=base_dir,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    training_signal = TrainingSignalService(repository)
    review_samples = training_signal.chapter_review_samples(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
    )
    preference_samples = training_signal.list_preference_samples(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
    )
    ranking_samples = training_signal.list_ranking_samples(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
    )
    issue_fix_pairs = training_signal.issue_fix_pairs(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
    )
    evaluator_examples = training_signal.evaluator_examples(review_samples)
    reranker_examples = training_signal.reranker_examples(
        issue_fix_pairs,
        preference_samples=preference_samples,
        ranking_samples=ranking_samples,
    )

    compare_summary = build_learned_compare_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    data_ops_summary = build_learned_data_ops_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    impact_summary = build_learned_impact_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    rollout_summary = build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    impact_track_map = {
        item["track"]: item
        for item in impact_summary.get("track_summaries", [])
    }
    promotion_workflows = {
        "evaluator": build_evaluator_promotion_workflow_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        ),
        "reranker": build_reranker_promotion_workflow_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        ),
    }
    artifact_states = {
        "evaluator": load_published_artifact_state(
            artifact_dir=artifact_dirs["evaluator"],
            required_files=["model.joblib", "label_encoder.json", "metrics.json", "feature_manifest.json", "training_manifest.json"],
            metrics_name="metrics.json",
            manifest_name="training_manifest.json",
        ),
        "reranker": load_published_artifact_state(
            artifact_dir=artifact_dirs["reranker"],
            required_files=["reranker_model.joblib", "reranker_metrics.json", "reranker_feature_manifest.json", "reranker_training_manifest.json"],
            metrics_name="reranker_metrics.json",
            manifest_name="reranker_training_manifest.json",
        ),
    }

    evaluator_runs = _track_training_runs(base_dir=base_dir, track="evaluator")
    reranker_runs = _track_training_runs(base_dir=base_dir, track="reranker")
    track_summaries = [
        _track_summary(
            track="evaluator",
            trainable_examples=evaluator_examples,
            latest_sample_at=_latest_timestamp([item.get("created_at") for item in review_samples]),
            source_sample_counts={
                "review_samples": len(review_samples),
                "human_review_samples": sum(1 for item in review_samples if item.get("source") == "human_review"),
            },
            data_ops_summary=data_ops_summary,
            impact_track_summary=impact_track_map.get("evaluator", {}),
            artifact_state=artifact_states["evaluator"],
            latest_training_run=evaluator_runs[0] if evaluator_runs else None,
            recent_training_runs=evaluator_runs[:5],
            promotion_workflow=promotion_workflows["evaluator"],
            rollout_track=dict(rollout_summary.get("tracks", {}).get("evaluator", {})),
            compare_summary=compare_summary,
        ),
        _track_summary(
            track="reranker",
            trainable_examples=reranker_examples,
            latest_sample_at=_latest_timestamp(
                [
                    *(item.get("timestamp") for item in issue_fix_pairs),
                    *(item.get("created_at") for item in preference_samples),
                    *(item.get("created_at") for item in ranking_samples),
                ]
            ),
            source_sample_counts={
                "issue_fix_pairs": len(issue_fix_pairs),
                "preference_samples": len(preference_samples),
                "ranking_samples": len(ranking_samples),
            },
            data_ops_summary=data_ops_summary,
            impact_track_summary=impact_track_map.get("reranker", {}),
            artifact_state=artifact_states["reranker"],
            latest_training_run=reranker_runs[0] if reranker_runs else None,
            recent_training_runs=reranker_runs[:5],
            promotion_workflow=promotion_workflows["reranker"],
            rollout_track=dict(rollout_summary.get("tracks", {}).get("reranker", {})),
            compare_summary=compare_summary,
        ),
    ]

    activation_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "ready_to_activate"]
    promotion_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "request_promotion"]
    validation_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "validate_shadow"]
    training_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "train_candidate"]
    collection_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "collect_data"]
    rebuild_queue = [item["track"] for item in track_summaries if item.get("cadence_stage") == "rebuild_readiness"]
    attention_queue = [item["track"] for item in track_summaries if item.get("cadence_health") == "attention"]
    ready_queue = [item["track"] for item in track_summaries if item.get("cadence_health") == "ready"]

    if activation_queue:
        recommended_next_action = f"activate_{activation_queue[0]}_rollout"
    elif promotion_queue:
        recommended_next_action = track_summaries[[item["track"] for item in track_summaries].index(promotion_queue[0])]["recommended_next_action"]
    elif validation_queue:
        recommended_next_action = track_summaries[[item["track"] for item in track_summaries].index(validation_queue[0])]["recommended_next_action"]
    elif training_queue:
        recommended_next_action = f"run_{training_queue[0]}_training"
    elif collection_queue:
        recommended_next_action = track_summaries[[item["track"] for item in track_summaries].index(collection_queue[0])]["recommended_next_action"]
    elif rebuild_queue:
        recommended_next_action = track_summaries[[item["track"] for item in track_summaries].index(rebuild_queue[0])]["recommended_next_action"]
    else:
        recommended_next_action = compare_summary.get("recommended_next_action") or "monitor_learned_tracks"

    warnings = list(
        dict.fromkeys(
            list(compare_summary.get("warnings", []))
            + list(data_ops_summary.get("warnings", []))
            + list(impact_summary.get("warnings", []))
            + [warning for item in track_summaries for warning in item.get("warnings", [])]
        )
    )

    return {
        "generated_at": _utcnow(),
        "filters": {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "limit": limit,
        },
        "cadence_summary": {
            "recommended_next_action": recommended_next_action,
            "active_tracks": list(rollout_summary.get("active_tracks", [])),
            "activation_queue": activation_queue,
            "promotion_queue": promotion_queue,
            "validation_queue": validation_queue,
            "training_queue": training_queue,
            "collection_queue": collection_queue,
            "rebuild_queue": rebuild_queue,
            "attention_queue": attention_queue,
            "ready_queue": ready_queue,
        },
        "track_summaries": track_summaries,
        "warnings": warnings,
    }


def build_learned_cadence_track_detail(
    *,
    repository: SQLAlchemyPlatformRepository,
    track: str,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track not in VALID_TRACKS:
        raise ValueError("invalid_learned_cadence_track")
    summary = build_learned_cadence_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    detail = next((item for item in summary.get("track_summaries", []) if item.get("track") == track), None)
    if detail is None:
        raise KeyError(f"unknown_learned_cadence_track:{track}")
    return {
        "generated_at": summary.get("generated_at"),
        "filters": summary.get("filters", {}),
        "track": track,
        "track_summary": detail,
        "cadence_summary": summary.get("cadence_summary", {}),
        "warnings": summary.get("warnings", []),
    }
