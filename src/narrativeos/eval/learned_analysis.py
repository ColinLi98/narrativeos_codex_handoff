from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .learned_dashboard import build_learned_dashboard_summary


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_learned_analysis(
    *,
    repository: SQLAlchemyPlatformRepository,
    output_dir: Path,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_learned_dashboard_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    report = {
        **summary,
        "evaluator_analysis": summary["evaluator_shadow_summary"],
        "reranker_analysis": summary["reranker_shadow_summary"],
        "cross_model_findings": {
            "shared_weak_worlds": summary["shared_weak_worlds"],
            "shared_weak_issue_codes": summary["shared_weak_issue_codes"],
            "recommended_next_focus": summary["recommended_next_focus"],
        },
    }
    manifest = {
        "generated_at": report["generated_at"],
        "filters": report["filters"],
        "artifact_status": report["artifact_status"],
        "recommended_next_focus": report["recommended_next_focus"],
    }
    _write_json(output_dir / "learned_analysis.json", report)
    _write_json(output_dir / "learned_analysis_manifest.json", manifest)
    return {
        "output_dir": str(output_dir),
        "artifacts": {
            "analysis": str(output_dir / "learned_analysis.json"),
            "manifest": str(output_dir / "learned_analysis_manifest.json"),
        },
        "report": report,
        "manifest": manifest,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run shared offline analysis for learned evaluator and reranker baselines.")
    parser.add_argument("--database-url", default="sqlite:///narrativeos_beta.db")
    parser.add_argument("--world-id")
    parser.add_argument("--world-version-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--evaluator-artifact-dir")
    parser.add_argument("--reranker-artifact-dir")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    result = run_learned_analysis(
        repository=repository,
        output_dir=Path(args.output_dir),
        world_id=args.world_id,
        world_version_id=args.world_version_id,
        limit=args.limit,
        evaluator_artifact_dir=Path(args.evaluator_artifact_dir) if args.evaluator_artifact_dir else None,
        reranker_artifact_dir=Path(args.reranker_artifact_dir) if args.reranker_artifact_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
