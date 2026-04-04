from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def default_learned_evaluator_artifact_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "artifacts" / "learned_evaluator_baseline"


def default_learned_reranker_artifact_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "artifacts" / "learned_reranker_baseline"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_artifact_manifest(
    *,
    artifact_type: str,
    dataset_view: str,
    source_output_dir: Path,
    trained_at: str,
    warnings: Sequence[str],
    available_files: Sequence[str],
    published_at: str | None = None,
) -> Dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "published_at": published_at or _utcnow(),
        "trained_at": trained_at,
        "source_output_dir": str(source_output_dir),
        "dataset_view": dataset_view,
        "warnings": list(warnings),
        "available_files": list(available_files),
    }


def write_artifact_manifest(target_dir: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_json(target_dir / "artifact_manifest.json", manifest)
    return manifest


def publish_artifact_bundle(
    *,
    artifact_type: str,
    dataset_view: str,
    source_output_dir: Path,
    target_dir: Path,
    trained_at: str,
    warnings: Sequence[str],
    required_files: Sequence[str],
) -> Dict[str, Any]:
    source_output_dir = Path(source_output_dir)
    target_dir = Path(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    available_files: List[str] = []
    for filename in required_files:
        source = source_output_dir / filename
        if not source.exists():
            raise FileNotFoundError(f"missing_artifact_file:{filename}")
        shutil.copy2(source, target_dir / filename)
        available_files.append(filename)

    manifest = build_artifact_manifest(
        artifact_type=artifact_type,
        dataset_view=dataset_view,
        source_output_dir=source_output_dir,
        trained_at=trained_at,
        warnings=warnings,
        available_files=available_files,
    )
    write_artifact_manifest(target_dir, manifest)
    return manifest


def load_published_artifact_state(
    *,
    artifact_dir: Path,
    required_files: Sequence[str],
    metrics_name: str,
    manifest_name: str,
) -> Dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    manifest_path = artifact_dir / "artifact_manifest.json"
    required_paths = [artifact_dir / name for name in required_files]
    if not manifest_path.exists():
        return {
            "available": False,
            "artifact_present": False,
            "artifact_dir": str(artifact_dir),
            "metrics": {},
            "training_manifest": {},
            "published_at": None,
            "trained_at": None,
            "source_output_dir": None,
            "artifact_files": [],
            "reason": "artifact_missing",
            "warnings": ["artifact_missing"],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "artifact_present": False,
            "artifact_dir": str(artifact_dir),
            "metrics": {},
            "training_manifest": {},
            "published_at": None,
            "trained_at": None,
            "source_output_dir": None,
            "artifact_files": [],
            "reason": f"artifact_load_failed:{exc}",
            "warnings": [f"artifact_load_failed:{exc}"],
        }

    if not all(path.exists() for path in required_paths):
        return {
            "available": False,
            "artifact_present": False,
            "artifact_dir": str(artifact_dir),
            "metrics": {},
            "training_manifest": {},
            "published_at": manifest.get("published_at"),
            "trained_at": manifest.get("trained_at"),
            "source_output_dir": manifest.get("source_output_dir"),
            "artifact_files": list(manifest.get("available_files", [])),
            "reason": "artifact_present_but_incomplete",
            "warnings": list(dict.fromkeys(list(manifest.get("warnings", [])) + ["artifact_present_but_incomplete"])),
        }

    try:
        metrics = json.loads((artifact_dir / metrics_name).read_text(encoding="utf-8"))
        training_manifest = json.loads((artifact_dir / manifest_name).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "artifact_present": False,
            "artifact_dir": str(artifact_dir),
            "metrics": {},
            "training_manifest": {},
            "published_at": manifest.get("published_at"),
            "trained_at": manifest.get("trained_at"),
            "source_output_dir": manifest.get("source_output_dir"),
            "artifact_files": list(manifest.get("available_files", [])),
            "reason": f"artifact_load_failed:{exc}",
            "warnings": list(dict.fromkeys(list(manifest.get("warnings", [])) + [f"artifact_load_failed:{exc}"])),
        }

    return {
        "available": True,
        "artifact_present": True,
        "artifact_dir": str(artifact_dir),
        "metrics": metrics,
        "training_manifest": training_manifest,
        "published_at": manifest.get("published_at"),
        "trained_at": manifest.get("trained_at"),
        "source_output_dir": manifest.get("source_output_dir"),
        "artifact_files": list(manifest.get("available_files", [])),
        "reason": None,
        "warnings": list(dict.fromkeys(manifest.get("warnings", []))),
    }
