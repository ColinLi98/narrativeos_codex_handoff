from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .artifact_registry import (
    default_learned_evaluator_artifact_dir,
    default_learned_reranker_artifact_dir,
    load_published_artifact_state,
)
from .learned_analysis import run_learned_analysis
from .learned_baseline import train_learned_evaluator_baseline
from .learned_cadence import build_learned_cadence_track_detail
from .learned_dashboard import build_learned_dashboard_summary
from .learned_compare import build_learned_compare_from_dashboard
from .learned_data_ops import build_learned_data_ops_summary
from .learned_promotion import build_evaluator_promotion_summary
from .learned_promotion_workflow import build_evaluator_promotion_workflow_summary
from .learned_reranker_baseline import train_learned_reranker_baseline
from .learned_reranker_promotion import build_reranker_promotion_summary
from .learned_reranker_promotion_workflow import build_reranker_promotion_workflow_summary


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def build_promotion_evidence_pack(
    *,
    track: str,
    repository: SQLAlchemyPlatformRepository,
    output_dir: Path,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if track not in {"evaluator", "reranker"}:
        raise ValueError("invalid_evidence_track")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_dir = Path(__file__).resolve().parents[3]
    artifact_dirs = _artifact_dirs(
        base_dir=base_dir,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    dashboard_summary = build_learned_dashboard_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    compare_summary = build_learned_compare_from_dashboard(dashboard_summary)
    data_ops_summary = build_learned_data_ops_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    analysis_result = run_learned_analysis(
        repository=repository,
        output_dir=output_dir / f"{track}_analysis",
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    if track == "evaluator":
        promotion_summary = build_evaluator_promotion_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        )
        promotion_workflow = build_evaluator_promotion_workflow_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        )
        artifact_state = load_published_artifact_state(
            artifact_dir=artifact_dirs["evaluator"],
            required_files=["model.joblib", "label_encoder.json", "metrics.json", "feature_manifest.json", "training_manifest.json"],
            metrics_name="metrics.json",
            manifest_name="training_manifest.json",
        )
        track_shadow = dashboard_summary.get("evaluator_shadow_summary", {})
    else:
        promotion_summary = build_reranker_promotion_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        )
        promotion_workflow = build_reranker_promotion_workflow_summary(
            repository=repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
            evaluator_artifact_dir=artifact_dirs["evaluator"],
            reranker_artifact_dir=artifact_dirs["reranker"],
        )
        artifact_state = load_published_artifact_state(
            artifact_dir=artifact_dirs["reranker"],
            required_files=["reranker_model.joblib", "reranker_metrics.json", "reranker_feature_manifest.json", "reranker_training_manifest.json"],
            metrics_name="reranker_metrics.json",
            manifest_name="reranker_training_manifest.json",
        )
        track_shadow = dashboard_summary.get("reranker_shadow_summary", {})

    evidence_pack = {
        "generated_at": _utcnow(),
        "track": track,
        "filters": {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "limit": limit,
        },
        "artifact_state": artifact_state,
        "shadow_summary": track_shadow,
        "dashboard_summary": {
            "recommended_next_focus": dashboard_summary.get("recommended_next_focus"),
            "shared_weak_worlds": dashboard_summary.get("shared_weak_worlds", []),
            "shared_weak_issue_codes": dashboard_summary.get("shared_weak_issue_codes", []),
            "artifact_status": dashboard_summary.get("artifact_status", {}),
            "warnings": dashboard_summary.get("warnings", []),
        },
        "compare_summary": compare_summary,
        "data_ops_summary": data_ops_summary,
        "promotion_summary": promotion_summary,
        "promotion_workflow": promotion_workflow,
        "analysis_report": analysis_result.get("report", {}),
        "evidence_summary": {
            "status": promotion_summary.get("status"),
            "recommended_action": promotion_summary.get("recommended_action"),
            "approval_status": promotion_workflow.get("approval_status"),
            "blocker_count": len(promotion_summary.get("blockers", [])),
            "advisory_count": len(promotion_summary.get("advisories", [])),
            "warning_count": len(artifact_state.get("warnings", [])),
        },
    }
    evidence_pack["cadence_snapshot"] = build_learned_cadence_track_detail(
        repository=repository,
        track=track,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=artifact_dirs["evaluator"],
        reranker_artifact_dir=artifact_dirs["reranker"],
    )
    evidence_path = output_dir / f"{track}_promotion_evidence.json"
    _write_json(evidence_path, evidence_pack)
    return {
        "track": track,
        "output_dir": str(output_dir),
        "evidence_path": str(evidence_path),
        "evidence_pack": evidence_pack,
    }


def run_learned_training_automation(
    *,
    repository: SQLAlchemyPlatformRepository,
    output_dir: Path,
    tracks: Sequence[str],
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    selected_tracks = [track for track in tracks if track in {"evaluator", "reranker"}]
    if not selected_tracks:
        raise ValueError("no_valid_tracks_selected")

    training_results: Dict[str, Dict[str, Any]] = {}
    artifact_dirs: Dict[str, Optional[Path]] = {"evaluator": None, "reranker": None}
    for track in selected_tracks:
        track_dir = run_dir / track
        track_dir.mkdir(parents=True, exist_ok=True)
        artifact_dirs[track] = track_dir
        try:
            if track == "evaluator":
                result = train_learned_evaluator_baseline(
                    repository=repository,
                    output_dir=track_dir,
                    dataset_view="evaluator",
                    world_id=world_id,
                    world_version_id=world_version_id,
                    limit=limit,
                )
            else:
                result = train_learned_reranker_baseline(
                    repository=repository,
                    output_dir=track_dir,
                    dataset_view="reranker",
                    world_id=world_id,
                    world_version_id=world_version_id,
                    limit=limit,
                )
            training_results[track] = {
                "status": "succeeded",
                "result": result,
            }
        except Exception as exc:  # pragma: no cover - exercised via automation failure handling
            training_results[track] = {
                "status": "failed",
                "error": str(exc),
            }

    evidence_results: Dict[str, Dict[str, Any]] = {}
    cadence_results: Dict[str, Dict[str, Any]] = {}
    for track in selected_tracks:
        track_output_dir = run_dir / f"{track}_evidence"
        try:
            evidence_results[track] = build_promotion_evidence_pack(
                track=track,
                repository=repository,
                output_dir=track_output_dir,
                world_id=world_id,
                world_version_id=world_version_id,
                limit=limit,
                evaluator_artifact_dir=artifact_dirs["evaluator"],
                reranker_artifact_dir=artifact_dirs["reranker"],
            )
        except Exception as exc:  # pragma: no cover - defensive
            evidence_results[track] = {
                "track": track,
                "output_dir": str(track_output_dir),
                "error": str(exc),
            }
        try:
            cadence_results[track] = build_learned_cadence_track_detail(
                repository=repository,
                track=track,
                world_id=world_id,
                world_version_id=world_version_id,
                limit=limit,
                evaluator_artifact_dir=artifact_dirs["evaluator"],
                reranker_artifact_dir=artifact_dirs["reranker"],
            )
        except Exception as exc:  # pragma: no cover - defensive
            cadence_results[track] = {
                "track": track,
                "error": str(exc),
            }

    summary = {
        "run_id": run_id,
        "generated_at": _utcnow(),
        "tracks_requested": list(selected_tracks),
        "tracks_succeeded": [track for track, payload in training_results.items() if payload.get("status") == "succeeded"],
        "tracks_failed": [track for track, payload in training_results.items() if payload.get("status") != "succeeded"],
        "output_dir": str(run_dir),
    }
    summary_path = run_dir / "learned_training_automation_summary.json"
    _write_json(
        summary_path,
        {
            "summary": summary,
            "training_results": training_results,
            "evidence_results": evidence_results,
            "cadence_results": cadence_results,
        },
    )
    return {
        "summary": summary,
        "training_results": training_results,
        "evidence_results": evidence_results,
        "cadence_results": cadence_results,
        "artifacts": {
            "summary": str(summary_path),
        },
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run learned evaluator/reranker training automation and generate promotion evidence packs.")
    parser.add_argument("--database-url", default="sqlite:///narrativeos_beta.db")
    parser.add_argument("--world-id")
    parser.add_argument("--world-version-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--tracks", default="evaluator,reranker")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    tracks = [item.strip() for item in str(args.tracks).split(",") if item.strip()]
    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    result = run_learned_training_automation(
        repository=repository,
        output_dir=Path(args.output_dir),
        tracks=tracks,
        world_id=args.world_id,
        world_version_id=args.world_version_id,
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
