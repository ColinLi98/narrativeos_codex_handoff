from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .artifact_registry import default_learned_reranker_artifact_dir, load_published_artifact_state


class LearnedRerankerShadowService:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = Path(artifact_dir)

    def _artifact_payloads(self) -> Dict[str, Any]:
        return load_published_artifact_state(
            artifact_dir=self.artifact_dir,
            required_files=[
                "reranker_model.joblib",
                "reranker_metrics.json",
                "reranker_feature_manifest.json",
                "reranker_training_manifest.json",
            ],
            metrics_name="reranker_metrics.json",
            manifest_name="reranker_training_manifest.json",
        )

    def _low_pair_coverage_worlds(self, reranker_examples: Sequence[Dict[str, Any]], *, threshold: int = 3) -> list[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for example in reranker_examples:
            world_id = str(example.get("world_id") or "")
            if not world_id:
                continue
            counts[world_id] = counts.get(world_id, 0) + 1
        return [
            {"world_id": world_id, "count": count}
            for world_id, count in sorted(counts.items(), key=lambda item: (item[1], item[0]))
            if count < threshold
        ]

    def summarize(self, reranker_bundle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        reranker_bundle = dict(reranker_bundle or {})
        reranker_examples = list(reranker_bundle.get("reranker_examples", []))
        artifact_state = self._artifact_payloads()

        low_pair_coverage_worlds = self._low_pair_coverage_worlds(reranker_examples)
        if not artifact_state["artifact_present"]:
            return {
                "available": False,
                "artifact_present": False,
                "artifact_dir": artifact_state["artifact_dir"],
                "status": "unavailable",
                "train_count": 0,
                "val_count": 0,
                "test_count": 0,
                "published_at": None,
                "trained_at": None,
                "source_output_dir": None,
                "artifact_files": [],
                "per_world_accuracy": {},
                "per_issue_code_error_rate": {},
                "low_pair_coverage_worlds": low_pair_coverage_worlds,
                "warnings": [artifact_state["reason"]],
                "recommended_next_action": "train_reranker_artifact",
            }

        training_manifest = dict(artifact_state.get("training_manifest", {}))
        metrics = dict(artifact_state.get("metrics", {}))
        warnings = list(dict.fromkeys(list(training_manifest.get("warnings", []))))
        train_count = int(training_manifest.get("train_count", 0) or 0)
        val_count = int(training_manifest.get("val_count", 0) or 0)
        test_count = int(training_manifest.get("test_count", 0) or 0)
        per_world_accuracy = {
            str(key): float(value)
            for key, value in dict(metrics.get("per_world_accuracy", {})).items()
        }
        per_issue_code_error_rate = {
            str(key): float(value)
            for key, value in dict(metrics.get("per_issue_code_error_rate", {})).items()
        }

        if not artifact_state["available"]:
            status = "unavailable"
        elif val_count == 0 or test_count == 0:
            status = "warming_up"
        elif "single_class_train_fallback_dummy" not in warnings and per_world_accuracy and min(per_world_accuracy.values()) >= 0.75:
            status = "candidate"
        else:
            status = "not_ready"

        if not artifact_state["available"]:
            recommended_next_action = "train_reranker_artifact"
        elif status == "warming_up":
            recommended_next_action = "expand_issue_fix_pairs"
        elif status == "candidate":
            recommended_next_action = "consider_shadow_candidate_reranker"
        elif any(value < 0.75 for value in per_world_accuracy.values()):
            recommended_next_action = "inspect_low_accuracy_worlds"
        elif "insufficient_reranker_pairs" in warnings or low_pair_coverage_worlds:
            recommended_next_action = "collect_more_fix_pairs"
        else:
            recommended_next_action = "inspect_low_accuracy_worlds"

        return {
            "available": bool(artifact_state["available"]),
            "artifact_present": bool(artifact_state["artifact_present"]),
            "artifact_dir": artifact_state["artifact_dir"],
            "status": status,
            "train_count": train_count,
            "val_count": val_count,
            "test_count": test_count,
            "published_at": artifact_state.get("published_at"),
            "trained_at": artifact_state.get("trained_at"),
            "source_output_dir": artifact_state.get("source_output_dir"),
            "artifact_files": artifact_state.get("artifact_files", []),
            "per_world_accuracy": per_world_accuracy,
            "per_issue_code_error_rate": per_issue_code_error_rate,
            "low_pair_coverage_worlds": low_pair_coverage_worlds,
            "warnings": warnings,
            "recommended_next_action": recommended_next_action,
        }


def default_learned_reranker_shadow_service(base_dir: Path) -> LearnedRerankerShadowService:
    return LearnedRerankerShadowService(default_learned_reranker_artifact_dir(base_dir))
