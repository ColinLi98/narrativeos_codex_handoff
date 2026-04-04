from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List

from ..models import NarrativeState
from ..pipeline import plan_next_turn_from_events
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.authoring import AuthoringService
from ..worldpacks.registry import FileSystemWorldRegistry


def run_regression_for_worldpack(world_id: str, *, repository: SQLAlchemyPlatformRepository) -> Dict[str, object]:
    authoring = AuthoringService(repository, registry=FileSystemWorldRegistry())
    simulation = authoring.run_simulation(world_id)
    return {
        "world_id": world_id,
        "simulation_report": simulation,
    }


def run_regression(worldpack: str, *, golden_dir: Path, repository: SQLAlchemyPlatformRepository) -> Dict[str, object]:
    registry = FileSystemWorldRegistry()
    world_ids = (
        [item["world_id"] for item in registry.list_benchmark_worldpacks()]
        if worldpack == "all"
        else [worldpack]
    )
    results = [run_regression_for_worldpack(world_id, repository=repository) for world_id in world_ids]
    summary = {
        "worldpacks": results,
        "golden_dir": str(golden_dir),
    }
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NarrativeEval nightly regression against golden world packs.")
    parser.add_argument("--worldpack", default="all")
    parser.add_argument("--golden-dir", default="tests/golden_routes")
    parser.add_argument("--database-url", default="sqlite:///narrativeos_beta.db")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    summary = run_regression(
        args.worldpack,
        golden_dir=Path(args.golden_dir),
        repository=repository,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
