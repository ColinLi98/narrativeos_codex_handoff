from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .artifact_registry import (
    build_artifact_manifest,
    default_learned_evaluator_artifact_dir,
    publish_artifact_bundle,
    write_artifact_manifest,
)


def _require_sklearn():
    try:
        from joblib import dump  # noqa: F401
        from sklearn.dummy import DummyClassifier  # noqa: F401
        from sklearn.feature_extraction import DictVectorizer  # noqa: F401
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401
        from sklearn.linear_model import LogisticRegression  # noqa: F401
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support  # noqa: F401
        from sklearn.preprocessing import LabelEncoder  # noqa: F401
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("scikit_learn_required:%s" % exc)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalized_examples(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    samples_by_chapter: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for sample in bundle.get("chapter_review_samples", []):
        samples_by_chapter.setdefault((sample["chapter_id"], sample["world_version_id"]), []).append(sample)

    normalized: List[Dict[str, Any]] = []
    for example in bundle.get("evaluator_examples", []):
        sample_candidates = samples_by_chapter.get((example["chapter_id"], example["world_version_id"]), [])
        sample_candidates = sorted(
            sample_candidates,
            key=lambda item: (
                0 if item.get("source") == "human_review" else 1,
                item.get("created_at", ""),
            ),
            reverse=True,
        )
        selected = sample_candidates[0] if sample_candidates else {}
        normalized.append(
            {
                **example,
                "freeform_notes": selected.get("freeform_notes", ""),
                "issue_text": " ".join(list(example.get("linked_issue_codes") or []) + list(example.get("issue_codes") or [])),
                "stable_id": example["chapter_id"],
            }
        )
    return normalized


def _split_examples(examples: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets = {"train": [], "val": [], "test": []}
    for example in examples:
        split = example.get("split", "train")
        buckets.setdefault(split, []).append(example)
    return buckets


def _feature_payloads(examples: Sequence[Dict[str, Any]]) -> Tuple[List[str], List[str], List[Dict[str, Any]], List[str]]:
    notes = [str(example.get("freeform_notes", "")).strip() or "__empty_note__" for example in examples]
    issues = [str(example.get("issue_text", "")).strip() or "__empty_issue__" for example in examples]
    structured = [
        {
            "score_overall": float(example.get("score_overall", 0.0)),
            "would_continue": int(bool(example.get("would_continue"))),
            "would_pay": int(bool(example.get("would_pay"))),
            "review_source": str(example.get("review_source", "")),
            "world_id": str(example.get("world_id", "")),
        }
        for example in examples
    ]
    labels = [str(example.get("label_decision", "rewrite")) for example in examples]
    return notes, issues, structured, labels


def _fit_model(train_examples: Sequence[Dict[str, Any]], warnings: List[str], label_encoder) -> Dict[str, Any]:
    _require_sklearn()
    from sklearn.dummy import DummyClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from scipy.sparse import hstack

    notes, issues, structured, labels = _feature_payloads(train_examples)

    y_train = label_encoder.transform(labels)

    notes_vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), min_df=1)
    issues_vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
    struct_vectorizer = DictVectorizer(sparse=True)

    x_notes = notes_vectorizer.fit_transform(notes)
    x_issues = issues_vectorizer.fit_transform(issues)
    x_struct = struct_vectorizer.fit_transform(structured)
    x_train = hstack([x_notes, x_issues, x_struct])

    if len(set(labels)) < 2:
        warnings.append("single_class_train_fallback_dummy")
        classifier = DummyClassifier(strategy="most_frequent")
    else:
        classifier = LogisticRegression(max_iter=1000, class_weight="balanced")
    classifier.fit(x_train, y_train)

    return {
        "classifier": classifier,
        "label_encoder": label_encoder,
        "notes_vectorizer": notes_vectorizer,
        "issues_vectorizer": issues_vectorizer,
        "struct_vectorizer": struct_vectorizer,
        "feature_dims": {
            "notes": int(x_notes.shape[1]),
            "issues": int(x_issues.shape[1]),
            "structured": int(x_struct.shape[1]),
            "total": int(x_train.shape[1]),
        },
    }


def _transform_examples(model_bundle: Dict[str, Any], examples: Sequence[Dict[str, Any]]):
    from scipy.sparse import hstack

    notes, issues, structured, labels = _feature_payloads(examples)
    x_notes = model_bundle["notes_vectorizer"].transform(notes)
    x_issues = model_bundle["issues_vectorizer"].transform(issues)
    x_struct = model_bundle["struct_vectorizer"].transform(structured)
    x = hstack([x_notes, x_issues, x_struct])
    y = model_bundle["label_encoder"].transform(labels) if labels else []
    return x, y, labels


def _split_metrics(model_bundle: Dict[str, Any], examples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    _require_sklearn()
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    labels = list(model_bundle["label_encoder"].classes_)
    if not examples:
        return {
            "count": 0,
            "accuracy": None,
            "macro_f1": None,
            "per_label_precision": {label: None for label in labels},
            "per_label_recall": {label: None for label in labels},
            "per_label_f1": {label: None for label in labels},
            "confusion_matrix": [],
            "predictions": [],
        }
    x, y_true, raw_labels = _transform_examples(model_bundle, examples)
    y_pred = model_bundle["classifier"].predict(x)
    if len(labels) == 1:
        precision = recall = f1 = [1.0 if all(item == y_pred[0] for item in y_pred) else 0.0]
        cm = [[len(y_true)]]
    else:
        precision, recall, f1, _support = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=list(range(len(labels))),
            zero_division=0,
        )
        cm = confusion_matrix(y_true, y_pred, labels=list(range(len(labels))))

    return {
        "count": len(examples),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "per_label_precision": {label: float(precision[index]) for index, label in enumerate(labels)},
        "per_label_recall": {label: float(recall[index]) for index, label in enumerate(labels)},
        "per_label_f1": {label: float(f1[index]) for index, label in enumerate(labels)},
        "confusion_matrix": cm.tolist() if hasattr(cm, "tolist") else cm,
        "predictions": [
            {
                "example_id": example["example_id"],
                "world_id": example["world_id"],
                "label_true": raw_labels[index],
                "label_pred": labels[int(y_pred[index])],
                "issue_codes": list(example.get("linked_issue_codes") or example.get("issue_codes") or []),
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


def train_learned_evaluator_baseline(
    *,
    repository: SQLAlchemyPlatformRepository,
    output_dir: Path,
    dataset_view: str = "evaluator",
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    if dataset_view != "evaluator":
        raise ValueError("baseline_requires_dataset_view_evaluator")
    output_dir.mkdir(parents=True, exist_ok=True)

    exporter = TrainingSignalService(repository)
    bundle = exporter.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view=dataset_view,
    )
    examples = _normalized_examples(bundle)
    if not examples:
        raise ValueError("no_evaluator_examples_available")

    _require_sklearn()
    from sklearn.preprocessing import LabelEncoder

    split_examples = _split_examples(examples)
    warnings = list(bundle.get("manifest", {}).get("warnings", []))
    train_examples = list(split_examples.get("train", []))
    if not train_examples:
        warnings.append("train_split_empty_fallback_all")
        train_examples = list(examples)
    label_encoder = LabelEncoder()
    label_encoder.fit([str(example.get("label_decision", "rewrite")) for example in examples])

    model_bundle = _fit_model(train_examples, warnings, label_encoder)
    split_metrics = {
        "train": _split_metrics(model_bundle, train_examples),
        "val": _split_metrics(model_bundle, split_examples.get("val", [])),
        "test": _split_metrics(model_bundle, split_examples.get("test", [])),
    }

    canonical = split_metrics["test"] if split_metrics["test"]["count"] else (split_metrics["val"] if split_metrics["val"]["count"] else split_metrics["train"])
    comparison = _comparison_summary(split_metrics)

    from joblib import dump

    model_artifact = {
        "classifier": model_bundle["classifier"],
        "label_encoder": model_bundle["label_encoder"],
        "notes_vectorizer": model_bundle["notes_vectorizer"],
        "issues_vectorizer": model_bundle["issues_vectorizer"],
        "struct_vectorizer": model_bundle["struct_vectorizer"],
    }
    dump(model_artifact, output_dir / "model.joblib")

    label_encoder_payload = {"classes": list(model_bundle["label_encoder"].classes_)}
    feature_manifest = {
        "dataset_view": dataset_view,
        "text_features": ["freeform_notes", "linked_issue_codes", "issue_codes"],
        "structured_features": ["score_overall", "would_continue", "would_pay", "review_source", "world_id"],
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

    _write_json(output_dir / "label_encoder.json", label_encoder_payload)
    _write_json(output_dir / "feature_manifest.json", feature_manifest)
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(output_dir / "training_manifest.json", training_manifest)
    local_manifest = build_artifact_manifest(
        artifact_type="learned_evaluator_baseline",
        dataset_view=dataset_view,
        source_output_dir=output_dir,
        trained_at=training_manifest["generated_at"],
        warnings=training_manifest["warnings"],
        available_files=[
            "model.joblib",
            "label_encoder.json",
            "metrics.json",
            "feature_manifest.json",
            "training_manifest.json",
        ],
        published_at=training_manifest["generated_at"],
    )
    write_artifact_manifest(output_dir, local_manifest)
    base_dir = Path(__file__).resolve().parents[3]
    published_manifest = publish_artifact_bundle(
        artifact_type="learned_evaluator_baseline",
        dataset_view=dataset_view,
        source_output_dir=output_dir,
        target_dir=default_learned_evaluator_artifact_dir(base_dir),
        trained_at=training_manifest["generated_at"],
        warnings=training_manifest["warnings"],
        required_files=[
            "model.joblib",
            "label_encoder.json",
            "metrics.json",
            "feature_manifest.json",
            "training_manifest.json",
        ],
    )

    return {
        "output_dir": str(output_dir),
        "artifacts": {
            "model": str(output_dir / "model.joblib"),
            "label_encoder": str(output_dir / "label_encoder.json"),
            "metrics": str(output_dir / "metrics.json"),
            "feature_manifest": str(output_dir / "feature_manifest.json"),
            "training_manifest": str(output_dir / "training_manifest.json"),
        },
        "published_artifact_manifest": published_manifest,
        "training_manifest": training_manifest,
        "metrics": metrics,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train a learned evaluator baseline from NarrativeOS training-signal exports.")
    parser.add_argument("--dataset-view", default="evaluator")
    parser.add_argument("--world-id")
    parser.add_argument("--world-version-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--database-url", default="sqlite:///narrativeos_beta.db")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    result = train_learned_evaluator_baseline(
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
