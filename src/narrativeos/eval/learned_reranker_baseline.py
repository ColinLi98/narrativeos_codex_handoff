from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .artifact_registry import (
    build_artifact_manifest,
    default_learned_reranker_artifact_dir,
    publish_artifact_bundle,
    write_artifact_manifest,
)
from .learned_baseline import _require_sklearn, _write_json


def _split_examples(examples: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets = {"train": [], "val": [], "test": []}
    for example in examples:
        buckets.setdefault(example.get("split", "train"), []).append(example)
    return buckets


def _build_binary_examples(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    pairs_by_id = {item["pair_id"]: item for item in bundle.get("issue_fix_pairs", [])}
    examples: List[Dict[str, Any]] = []
    for example in bundle.get("reranker_examples", []):
        pair_id = str(example["example_id"]).replace("rerank_", "", 1)
        pair = pairs_by_id.get(pair_id)
        if pair is None:
            continue
        simulation_delta = dict(pair.get("simulation_delta") or {})
        metric_deltas = {
            key: float(value)
            for key, value in dict(simulation_delta.get("metric_deltas") or {}).items()
            if isinstance(value, (int, float))
        }
        base = {
            "stable_id": pair["pair_id"],
            "pair_id": pair["pair_id"],
            "world_id": example["world_id"],
            "world_version_id": example["world_version_id"],
            "before_revision_id": example["before_revision_id"],
            "after_revision_id": example["after_revision_id"],
            "changed_sections": list(example.get("changed_sections", [])),
            "linked_issue_codes": list(example.get("linked_issue_codes", [])),
            "preference_strength": example.get("preference_strength", "medium"),
            "split": example.get("split", "train"),
            "pass_rate_delta": float(simulation_delta.get("pass_rate_delta") or 0.0),
            "rewrite_rate_delta": float(simulation_delta.get("rewrite_rate_delta") or 0.0),
            "block_rate_delta": float(simulation_delta.get("block_rate_delta") or 0.0),
            "metric_deltas": metric_deltas,
        }
        examples.append(
            {
                **base,
                "example_id": f"{example['example_id']}_after",
                "preferred_revision_id": example["after_revision_id"],
                "label_after_preferred": 1,
            }
        )
        examples.append(
            {
                **base,
                "example_id": f"{example['example_id']}_before",
                "preferred_revision_id": example["before_revision_id"],
                "label_after_preferred": 0,
                "pass_rate_delta": -base["pass_rate_delta"],
                "rewrite_rate_delta": -base["rewrite_rate_delta"],
                "block_rate_delta": -base["block_rate_delta"],
                "metric_deltas": {key: -value for key, value in metric_deltas.items()},
            }
        )
    return examples


def _feature_payloads(examples: Sequence[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[int]]:
    features: List[Dict[str, Any]] = []
    labels: List[int] = []
    for example in examples:
        payload: Dict[str, Any] = {
            "world_id": str(example.get("world_id", "")),
            "preference_strength": str(example.get("preference_strength", "")),
            "pass_rate_delta": float(example.get("pass_rate_delta", 0.0)),
            "rewrite_rate_delta": float(example.get("rewrite_rate_delta", 0.0)),
            "block_rate_delta": float(example.get("block_rate_delta", 0.0)),
        }
        for section in example.get("changed_sections", []):
            payload[f"changed_section::{section}"] = 1
        for issue_code in example.get("linked_issue_codes", []):
            payload[f"issue_code::{issue_code}"] = 1
        for metric_name, metric_value in dict(example.get("metric_deltas") or {}).items():
            if isinstance(metric_value, (int, float)):
                payload[f"metric_delta::{metric_name}"] = float(metric_value)
        features.append(payload)
        labels.append(int(example.get("label_after_preferred", 0)))
    return features, labels


def _fit_model(train_examples: Sequence[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
    _require_sklearn()
    from sklearn.dummy import DummyClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression

    features, labels = _feature_payloads(train_examples)
    vectorizer = DictVectorizer(sparse=True)
    x_train = vectorizer.fit_transform(features)
    if len(set(labels)) < 2:
        warnings.append("single_class_train_fallback_dummy")
        classifier = DummyClassifier(strategy="most_frequent")
    else:
        classifier = LogisticRegression(max_iter=1000, class_weight="balanced")
    classifier.fit(x_train, labels)
    return {
        "classifier": classifier,
        "vectorizer": vectorizer,
        "feature_dims": int(x_train.shape[1]),
    }


def _transform_examples(model_bundle: Dict[str, Any], examples: Sequence[Dict[str, Any]]):
    features, labels = _feature_payloads(examples)
    x = model_bundle["vectorizer"].transform(features)
    return x, labels


def _split_metrics(model_bundle: Dict[str, Any], examples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    _require_sklearn()
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    if not examples:
        return {
            "count": 0,
            "accuracy": None,
            "macro_f1": None,
            "per_label_precision": {"0": None, "1": None},
            "per_label_recall": {"0": None, "1": None},
            "per_label_f1": {"0": None, "1": None},
            "confusion_matrix": [],
            "predictions": [],
        }
    x, y_true = _transform_examples(model_bundle, examples)
    y_pred = model_bundle["classifier"].predict(x)
    labels = [0, 1]
    if len(set(y_true)) < 2 and len(set(y_pred)) < 2:
        precision = recall = f1 = [1.0 if y_pred[0] == 0 else 0.0, 1.0 if y_pred[0] == 1 else 0.0]
        cm = [[sum(1 for value in y_true if value == 0), 0], [0, sum(1 for value in y_true if value == 1)]]
    else:
        precision, recall, f1, _support = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=labels,
            zero_division=0,
        )
        cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "count": len(examples),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "per_label_precision": {str(label): float(precision[index]) for index, label in enumerate(labels)},
        "per_label_recall": {str(label): float(recall[index]) for index, label in enumerate(labels)},
        "per_label_f1": {str(label): float(f1[index]) for index, label in enumerate(labels)},
        "confusion_matrix": cm.tolist() if hasattr(cm, "tolist") else cm,
        "predictions": [
            {
                "example_id": example["example_id"],
                "world_id": example["world_id"],
                "label_true": int(y_true[index]),
                "label_pred": int(y_pred[index]),
                "issue_codes": list(example.get("linked_issue_codes") or []),
            }
            for index, example in enumerate(examples)
        ],
    }


def _comparison_summary(split_metrics: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    predictions = []
    for item in split_metrics.values():
        predictions.extend(item.get("predictions", []))
    per_world: Dict[str, Dict[str, int]] = {}
    per_issue: Dict[str, Dict[str, int]] = {}
    for prediction in predictions:
        world_bucket = per_world.setdefault(prediction["world_id"], {"total": 0, "errors": 0})
        world_bucket["total"] += 1
        if prediction["label_true"] != prediction["label_pred"]:
            world_bucket["errors"] += 1
        for issue_code in prediction.get("issue_codes", []):
            issue_bucket = per_issue.setdefault(issue_code, {"total": 0, "errors": 0})
            issue_bucket["total"] += 1
            if prediction["label_true"] != prediction["label_pred"]:
                issue_bucket["errors"] += 1
    return {
        "per_world_accuracy": {
            key: round(1.0 - (value["errors"] / float(max(1, value["total"]))), 4)
            for key, value in per_world.items()
        },
        "per_issue_code_error_rate": {
            key: round(value["errors"] / float(max(1, value["total"])), 4)
            for key, value in per_issue.items()
        },
    }


def train_learned_reranker_baseline(
    *,
    repository: SQLAlchemyPlatformRepository,
    output_dir: Path,
    dataset_view: str = "reranker",
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    if dataset_view != "reranker":
        raise ValueError("baseline_requires_dataset_view_reranker")
    output_dir.mkdir(parents=True, exist_ok=True)

    exporter = TrainingSignalService(repository)
    bundle = exporter.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view=dataset_view,
    )
    examples = _build_binary_examples(bundle)
    if not examples:
        raise ValueError("no_reranker_examples_available")

    split_examples = _split_examples(examples)
    warnings = list(bundle.get("manifest", {}).get("warnings", []))
    train_examples = list(split_examples.get("train", []))
    if not train_examples:
        warnings.append("train_split_empty_fallback_all")
        train_examples = list(examples)

    model_bundle = _fit_model(train_examples, warnings)
    split_metrics = {
        "train": _split_metrics(model_bundle, train_examples),
        "val": _split_metrics(model_bundle, split_examples.get("val", [])),
        "test": _split_metrics(model_bundle, split_examples.get("test", [])),
    }
    canonical = split_metrics["test"] if split_metrics["test"]["count"] else (split_metrics["val"] if split_metrics["val"]["count"] else split_metrics["train"])
    comparison = _comparison_summary(split_metrics)

    from joblib import dump

    dump({"classifier": model_bundle["classifier"], "vectorizer": model_bundle["vectorizer"]}, output_dir / "reranker_model.joblib")
    feature_manifest = {
        "dataset_view": dataset_view,
        "categorical_features": ["world_id", "preference_strength", "changed_sections", "linked_issue_codes"],
        "numeric_features": ["pass_rate_delta", "rewrite_rate_delta", "block_rate_delta", "metric_deltas.*"],
        "model_type": type(model_bundle["classifier"]).__name__,
        "feature_dims": model_bundle["feature_dims"],
    }
    metrics = {
        "train_accuracy": split_metrics["train"]["accuracy"],
        "val_accuracy": split_metrics["val"]["accuracy"],
        "test_accuracy": split_metrics["test"]["accuracy"],
        "macro_f1": canonical["macro_f1"],
        "per_label_precision": canonical["per_label_precision"],
        "per_label_recall": canonical["per_label_recall"],
        "per_label_f1": canonical["per_label_f1"],
        "confusion_matrix": canonical["confusion_matrix"],
        "per_split": {
            key: {
                "count": value["count"],
                "accuracy": value["accuracy"],
                "macro_f1": value["macro_f1"],
            }
            for key, value in split_metrics.items()
        },
        **comparison,
    }
    training_manifest = {
        "generated_at": bundle["generated_at"],
        "filters": bundle["filters"],
        "dataset_view": dataset_view,
        "train_count": split_metrics["train"]["count"],
        "val_count": split_metrics["val"]["count"],
        "test_count": split_metrics["test"]["count"],
        "warnings": warnings,
        "source_bundle_manifest": bundle["manifest"],
    }

    _write_json(output_dir / "reranker_feature_manifest.json", feature_manifest)
    _write_json(output_dir / "reranker_metrics.json", metrics)
    _write_json(output_dir / "reranker_training_manifest.json", training_manifest)
    local_manifest = build_artifact_manifest(
        artifact_type="learned_reranker_baseline",
        dataset_view=dataset_view,
        source_output_dir=output_dir,
        trained_at=training_manifest["generated_at"],
        warnings=training_manifest["warnings"],
        available_files=[
            "reranker_model.joblib",
            "reranker_metrics.json",
            "reranker_feature_manifest.json",
            "reranker_training_manifest.json",
        ],
        published_at=training_manifest["generated_at"],
    )
    write_artifact_manifest(output_dir, local_manifest)
    base_dir = Path(__file__).resolve().parents[3]
    published_manifest = publish_artifact_bundle(
        artifact_type="learned_reranker_baseline",
        dataset_view=dataset_view,
        source_output_dir=output_dir,
        target_dir=default_learned_reranker_artifact_dir(base_dir),
        trained_at=training_manifest["generated_at"],
        warnings=training_manifest["warnings"],
        required_files=[
            "reranker_model.joblib",
            "reranker_metrics.json",
            "reranker_feature_manifest.json",
            "reranker_training_manifest.json",
        ],
    )

    return {
        "output_dir": str(output_dir),
        "artifacts": {
            "model": str(output_dir / "reranker_model.joblib"),
            "metrics": str(output_dir / "reranker_metrics.json"),
            "feature_manifest": str(output_dir / "reranker_feature_manifest.json"),
            "training_manifest": str(output_dir / "reranker_training_manifest.json"),
        },
        "published_artifact_manifest": published_manifest,
        "training_manifest": training_manifest,
        "metrics": metrics,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train a learned reranker baseline from NarrativeOS training-signal exports.")
    parser.add_argument("--dataset-view", default="reranker")
    parser.add_argument("--world-id")
    parser.add_argument("--world-version-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--database-url", default="sqlite:///narrativeos_beta.db")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    result = train_learned_reranker_baseline(
        repository=repository,
        output_dir=Path(args.output_dir),
        dataset_view=args.dataset_view,
        world_id=args.world_id,
        world_version_id=args.world_version_id,
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
