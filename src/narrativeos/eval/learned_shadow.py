from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .artifact_registry import default_learned_evaluator_artifact_dir, load_published_artifact_state
from .learned_inference import LearnedInferenceService


class LearnedShadowService:
    def __init__(
        self,
        artifact_dir: Path,
        *,
        learned_inference_service: Optional[LearnedInferenceService] = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.learned_inference = learned_inference_service or LearnedInferenceService(self.artifact_dir)

    def _artifact_payloads(self) -> Dict[str, Any]:
        payload = load_published_artifact_state(
            artifact_dir=self.artifact_dir,
            required_files=[
                "model.joblib",
                "label_encoder.json",
                "metrics.json",
                "feature_manifest.json",
                "training_manifest.json",
            ],
            metrics_name="metrics.json",
            manifest_name="training_manifest.json",
        )
        availability = self.learned_inference.availability()
        payload["available"] = bool(payload["available"] and availability.get("available", False))
        if payload["reason"] is None and not availability.get("available", False):
            payload["reason"] = availability.get("reason", "artifact_load_failed")
            payload["warnings"] = list(dict.fromkeys(list(payload.get("warnings", [])) + [payload["reason"]]))
        return payload

    def summarize(self, learned_evaluation_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        learned_evaluation_summary = dict(learned_evaluation_summary or {})
        artifact_state = self._artifact_payloads()
        if not artifact_state["artifact_present"]:
            return {
                "available": False,
                "artifact_present": False,
                "artifact_dir": artifact_state["artifact_dir"],
                "status": "unavailable",
                "agreement_rate": None,
                "train_count": 0,
                "val_count": 0,
                "test_count": 0,
                "published_at": None,
                "trained_at": None,
                "source_output_dir": None,
                "artifact_files": [],
                "warnings": [artifact_state["reason"] or "artifact_missing"],
                "top_mismatch_worlds": [],
                "top_mismatch_issue_codes": [],
                "recommended_next_action": "train_baseline_artifact",
            }

        training_manifest = dict(artifact_state["training_manifest"] or {})
        metrics = dict(artifact_state["metrics"] or {})
        warnings = list(dict.fromkeys(list(training_manifest.get("warnings", []))))

        agreement_rate = learned_evaluation_summary.get("agreement_rate")
        if agreement_rate is None:
            agreement_rate = metrics.get("test_accuracy")
        if agreement_rate is None:
            agreement_rate = metrics.get("val_accuracy")
        if agreement_rate is None:
            agreement_rate = metrics.get("train_accuracy")

        top_mismatch_worlds = list(learned_evaluation_summary.get("top_mismatch_worlds", []))
        if not top_mismatch_worlds:
            top_mismatch_worlds = [
                {"world_id": world_id, "value": value}
                for world_id, value in sorted(
                    dict(metrics.get("per_world_accuracy", {})).items(),
                    key=lambda item: float(item[1]),
                )[:5]
            ]

        top_mismatch_issue_codes = list(learned_evaluation_summary.get("top_mismatch_issue_codes", []))
        if not top_mismatch_issue_codes:
            top_mismatch_issue_codes = [
                {"issue_code": issue_code, "value": value}
                for issue_code, value in sorted(
                    dict(metrics.get("per_issue_code_error_rate", {})).items(),
                    key=lambda item: float(item[1]),
                    reverse=True,
                )[:5]
            ]

        train_count = int(training_manifest.get("train_count", 0) or 0)
        val_count = int(training_manifest.get("val_count", 0) or 0)
        test_count = int(training_manifest.get("test_count", 0) or 0)

        if not artifact_state["available"]:
            status = "unavailable"
        elif val_count == 0 or test_count == 0:
            status = "warming_up"
        elif "single_class_train_fallback_dummy" not in warnings and agreement_rate is not None and float(agreement_rate) >= 0.8:
            status = "candidate"
        else:
            status = "not_ready"

        if not artifact_state["available"]:
            recommended_next_action = "train_baseline_artifact"
        elif status == "warming_up":
            recommended_next_action = "expand_eval_dataset"
        elif "missing_human_review_coverage" in warnings:
            recommended_next_action = "add_human_review_samples"
        elif agreement_rate is not None and float(agreement_rate) < 0.8:
            recommended_next_action = "inspect_top_mismatches"
        elif status == "candidate":
            recommended_next_action = "consider_stricter_shadow_candidate"
        else:
            recommended_next_action = "inspect_top_mismatches"

        return {
            "available": bool(artifact_state["available"]),
            "artifact_present": bool(artifact_state["artifact_present"]),
            "artifact_dir": artifact_state["artifact_dir"],
            "status": status,
            "agreement_rate": agreement_rate,
            "train_count": train_count,
            "val_count": val_count,
            "test_count": test_count,
            "published_at": artifact_state.get("published_at"),
            "trained_at": artifact_state.get("trained_at"),
            "source_output_dir": artifact_state.get("source_output_dir"),
            "artifact_files": artifact_state.get("artifact_files", []),
            "warnings": warnings,
            "top_mismatch_worlds": top_mismatch_worlds,
            "top_mismatch_issue_codes": top_mismatch_issue_codes,
            "recommended_next_action": recommended_next_action,
        }


def default_learned_shadow_service(base_dir: Path) -> LearnedShadowService:
    artifact_dir = default_learned_evaluator_artifact_dir(base_dir)
    return LearnedShadowService(
        artifact_dir,
        learned_inference_service=LearnedInferenceService(artifact_dir),
    )
