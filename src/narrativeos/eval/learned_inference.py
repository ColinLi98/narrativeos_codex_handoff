from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def default_learned_artifact_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "artifacts" / "learned_evaluator_baseline"


class LearnedInferenceService:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._cached_bundle: Optional[Dict[str, Any]] = None
        self._cached_signature: Optional[tuple] = None

    def _artifact_paths(self) -> Dict[str, Path]:
        return {
            "model": self.artifact_dir / "model.joblib",
            "label_encoder": self.artifact_dir / "label_encoder.json",
            "feature_manifest": self.artifact_dir / "feature_manifest.json",
        }

    def _signature(self) -> Optional[tuple]:
        paths = self._artifact_paths()
        if not all(path.exists() for path in paths.values()):
            return None
        return tuple(path.stat().st_mtime_ns for path in paths.values())

    def _load_bundle(self) -> Dict[str, Any]:
        signature = self._signature()
        if signature is None:
            raise FileNotFoundError("learned_artifact_missing")
        if self._cached_bundle is not None and self._cached_signature == signature:
            return self._cached_bundle

        from joblib import load

        paths = self._artifact_paths()
        model_bundle = load(paths["model"])
        label_encoder_payload = json.loads(paths["label_encoder"].read_text(encoding="utf-8"))
        feature_manifest = json.loads(paths["feature_manifest"].read_text(encoding="utf-8"))
        bundle = {
            **model_bundle,
            "classes": list(label_encoder_payload.get("classes", [])),
            "feature_manifest": feature_manifest,
        }
        self._cached_bundle = bundle
        self._cached_signature = signature
        return bundle

    def availability(self) -> Dict[str, Any]:
        try:
            bundle = self._load_bundle()
        except FileNotFoundError:
            return {
                "available": False,
                "artifact_dir": str(self.artifact_dir),
                "reason": "artifact_missing",
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "available": False,
                "artifact_dir": str(self.artifact_dir),
                "reason": "artifact_load_failed",
                "error": str(exc),
            }
        return {
            "available": True,
            "artifact_dir": str(self.artifact_dir),
            "classes": list(bundle.get("classes", [])),
        }

    def _normalize_text(self, value: Any, empty_token: str) -> str:
        return str(value or "").strip() or empty_token

    def _vectorize(self, bundle: Dict[str, Any], example: Dict[str, Any]):
        from scipy.sparse import hstack

        notes = [self._normalize_text(example.get("freeform_notes"), "__empty_note__")]
        issues = [self._normalize_text(" ".join(example.get("linked_issue_codes") or example.get("issue_codes") or []), "__empty_issue__")]
        structured = [
            {
                "score_overall": float(example.get("score_overall", 0.0)),
                "would_continue": int(bool(example.get("would_continue"))),
                "would_pay": int(bool(example.get("would_pay"))),
                "review_source": str(example.get("review_source", "")),
                "world_id": str(example.get("world_id", "")),
            }
        ]
        x_notes = bundle["notes_vectorizer"].transform(notes)
        x_issues = bundle["issues_vectorizer"].transform(issues)
        x_struct = bundle["struct_vectorizer"].transform(structured)
        return hstack([x_notes, x_issues, x_struct])

    def predict_example(self, example: Dict[str, Any]) -> Dict[str, Any]:
        for field in ["chapter_id", "world_id", "world_version_id", "label_decision"]:
            if not example.get(field):
                return {
                    "available": False,
                    "predicted_decision": None,
                    "confidence": None,
                    "reason": f"missing_field:{field}",
                }
        availability = self.availability()
        if not availability["available"]:
            return {
                "available": False,
                "predicted_decision": None,
                "confidence": None,
                "reason": availability["reason"],
            }
        bundle = self._load_bundle()
        features = self._vectorize(bundle, example)
        classifier = bundle["classifier"]
        classes = list(bundle.get("classes", []))
        prediction = classifier.predict(features)[0]
        predicted_decision = classes[int(prediction)]
        confidence = 1.0
        if hasattr(classifier, "predict_proba"):
            probabilities = classifier.predict_proba(features)[0]
            confidence = float(max(probabilities))
        return {
            "available": True,
            "predicted_decision": predicted_decision,
            "confidence": confidence,
        }

    def summarize_examples(self, examples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        availability = self.availability()
        if not availability["available"]:
            return {
                "available": False,
                "predicted_distribution": {},
                "agreement_rate": None,
                "mismatch_examples": [],
                "top_mismatch_worlds": [],
                "top_mismatch_issue_codes": [],
                "reason": availability["reason"],
            }
        if not examples:
            return {
                "available": True,
                "predicted_distribution": {},
                "agreement_rate": None,
                "mismatch_examples": [],
                "top_mismatch_worlds": [],
                "top_mismatch_issue_codes": [],
            }

        predictions = []
        for example in examples:
            prediction = self.predict_example(example)
            predictions.append({**example, **prediction})

        predicted_distribution_counter = Counter(
            item["predicted_decision"] for item in predictions if item.get("predicted_decision")
        )
        comparable = [item for item in predictions if item.get("predicted_decision") and item.get("label_decision")]
        agreement_count = sum(1 for item in comparable if item["predicted_decision"] == item["label_decision"])
        mismatch_examples = [
            {
                "chapter_id": item["chapter_id"],
                "rule_decision": item["label_decision"],
                "learned_decision": item["predicted_decision"],
                "world_id": item["world_id"],
                "issue_codes": list(item.get("linked_issue_codes") or item.get("issue_codes") or []),
                "confidence": item.get("confidence"),
            }
            for item in comparable
            if item["predicted_decision"] != item["label_decision"]
        ]
        world_counter = Counter(item["world_id"] for item in mismatch_examples)
        issue_counter = Counter(
            issue_code
            for item in mismatch_examples
            for issue_code in item.get("issue_codes", [])
        )
        total = float(max(1, len(comparable)))
        return {
            "available": True,
            "predicted_distribution": dict(predicted_distribution_counter),
            "agreement_rate": agreement_count / total if comparable else None,
            "mismatch_examples": mismatch_examples[:10],
            "top_mismatch_worlds": [
                {"world_id": world_id, "count": count}
                for world_id, count in world_counter.most_common(5)
            ],
            "top_mismatch_issue_codes": [
                {"issue_code": issue_code, "count": count}
                for issue_code, count in issue_counter.most_common(5)
            ],
        }
