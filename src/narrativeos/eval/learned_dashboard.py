from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .artifact_registry import (
    default_learned_evaluator_artifact_dir,
    default_learned_reranker_artifact_dir,
    load_published_artifact_state,
)


def _lowest_metric_entries(metric_map: Dict[str, Any], *, limit: int = 5, descending: bool = False) -> list[Dict[str, Any]]:
    items = []
    for key, value in metric_map.items():
        try:
            items.append((str(key), float(value)))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda item: item[1], reverse=descending)
    return [{"key": key, "value": value} for key, value in items[:limit]]


def _coverage_by_world(examples: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for example in examples:
        world_id = str(example.get("world_id") or "")
        if not world_id:
            continue
        counts[world_id] = counts.get(world_id, 0) + 1
    return counts


def _low_coverage_worlds(examples: Sequence[Dict[str, Any]], *, threshold: int) -> list[Dict[str, Any]]:
    counts = _coverage_by_world(examples)
    return [
        {"world_id": world_id, "count": count}
        for world_id, count in sorted(counts.items(), key=lambda item: (item[1], item[0]))
        if count < threshold
    ]


def _evaluator_analysis(bundle: Dict[str, Any], artifact_state: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = artifact_state.get("training_manifest", {})
    metrics = artifact_state.get("metrics", {})
    examples = bundle.get("evaluator_examples", [])
    per_world = _lowest_metric_entries(metrics.get("per_world_accuracy", {}), limit=5, descending=False)
    per_issue = _lowest_metric_entries(metrics.get("per_issue_code_error_rate", {}), limit=5, descending=True)
    return {
        "available": artifact_state["available"],
        "artifact_present": artifact_state["artifact_present"],
        "artifact_dir": artifact_state["artifact_dir"],
        "published_at": artifact_state.get("published_at"),
        "trained_at": artifact_state.get("trained_at"),
        "source_output_dir": artifact_state.get("source_output_dir"),
        "artifact_files": artifact_state.get("artifact_files", []),
        "train_count": int(training_manifest.get("train_count", 0) or 0),
        "val_count": int(training_manifest.get("val_count", 0) or 0),
        "test_count": int(training_manifest.get("test_count", 0) or 0),
        "agreement_rate": metrics.get("test_accuracy")
        if metrics.get("test_accuracy") is not None
        else (metrics.get("val_accuracy") if metrics.get("val_accuracy") is not None else metrics.get("train_accuracy")),
        "top_mismatch_worlds": [{"world_id": item["key"], "value": item["value"]} for item in per_world],
        "top_mismatch_issue_codes": [{"issue_code": item["key"], "value": item["value"]} for item in per_issue],
        "low_coverage_worlds": _low_coverage_worlds(examples, threshold=5),
        "warnings": list(dict.fromkeys(artifact_state.get("warnings", []))),
    }


def _reranker_analysis(bundle: Dict[str, Any], artifact_state: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = artifact_state.get("training_manifest", {})
    metrics = artifact_state.get("metrics", {})
    examples = bundle.get("reranker_examples", [])
    per_world_accuracy = {str(key): float(value) for key, value in metrics.get("per_world_accuracy", {}).items()}
    per_issue_error = {str(key): float(value) for key, value in metrics.get("per_issue_code_error_rate", {}).items()}
    return {
        "available": artifact_state["available"],
        "artifact_present": artifact_state["artifact_present"],
        "artifact_dir": artifact_state["artifact_dir"],
        "published_at": artifact_state.get("published_at"),
        "trained_at": artifact_state.get("trained_at"),
        "source_output_dir": artifact_state.get("source_output_dir"),
        "artifact_files": artifact_state.get("artifact_files", []),
        "train_count": int(training_manifest.get("train_count", 0) or 0),
        "val_count": int(training_manifest.get("val_count", 0) or 0),
        "test_count": int(training_manifest.get("test_count", 0) or 0),
        "per_world_accuracy": per_world_accuracy,
        "per_issue_code_error_rate": per_issue_error,
        "low_pair_coverage_worlds": _low_coverage_worlds(examples, threshold=3),
        "warnings": list(dict.fromkeys(artifact_state.get("warnings", []))),
    }


def _cross_model_findings(evaluator_analysis: Dict[str, Any], reranker_analysis: Dict[str, Any]) -> Dict[str, Any]:
    evaluator_weak_worlds = {item["world_id"] for item in evaluator_analysis.get("low_coverage_worlds", [])}
    evaluator_weak_worlds.update(item["world_id"] for item in evaluator_analysis.get("top_mismatch_worlds", []) if item.get("value") is not None and item["value"] < 0.8)
    reranker_weak_worlds = {item["world_id"] for item in reranker_analysis.get("low_pair_coverage_worlds", [])}
    reranker_weak_worlds.update(
        world_id for world_id, value in reranker_analysis.get("per_world_accuracy", {}).items() if value < 0.8
    )
    shared_weak_worlds = sorted(evaluator_weak_worlds & reranker_weak_worlds)

    evaluator_issue_codes = {
        item["issue_code"]
        for item in evaluator_analysis.get("top_mismatch_issue_codes", [])
        if item.get("value") is not None and item["value"] > 0.2
    }
    reranker_issue_codes = {
        issue_code
        for issue_code, value in reranker_analysis.get("per_issue_code_error_rate", {}).items()
        if value > 0.2
    }
    shared_weak_issue_codes = sorted(evaluator_issue_codes & reranker_issue_codes)

    if shared_weak_worlds:
        recommended_next_focus = f"world::{shared_weak_worlds[0]}"
    elif evaluator_issue_codes and (not reranker_issue_codes or "insufficient_reranker_pairs" in reranker_analysis.get("warnings", [])):
        recommended_next_focus = "expand_review_and_pair_data"
    elif "insufficient_reranker_pairs" in reranker_analysis.get("warnings", []):
        recommended_next_focus = "expand_issue_fix_pairs"
    else:
        recommended_next_focus = "consider_shadow_candidate_evaluator"

    return {
        "shared_weak_worlds": shared_weak_worlds,
        "shared_weak_issue_codes": shared_weak_issue_codes,
        "recommended_next_focus": recommended_next_focus,
    }


def _issue_world_maps(
    *,
    chapter_review_samples: Sequence[Dict[str, Any]],
    issue_fix_pairs: Sequence[Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, int]]]:
    evaluator_world_issues: Dict[str, Dict[str, int]] = {}
    for sample in chapter_review_samples:
        world_bucket = evaluator_world_issues.setdefault(str(sample.get("world_id") or ""), {})
        for issue_code in sample.get("linked_issue_codes") or sample.get("issue_codes") or []:
            world_bucket[issue_code] = world_bucket.get(issue_code, 0) + 1

    reranker_world_issues: Dict[str, Dict[str, int]] = {}
    for pair in issue_fix_pairs:
        world_bucket = reranker_world_issues.setdefault(str(pair.get("world_id") or ""), {})
        for issue_code in pair.get("linked_issue_codes") or []:
            world_bucket[issue_code] = world_bucket.get(issue_code, 0) + 1

    return evaluator_world_issues, reranker_world_issues


def _top_issue_codes(issue_counter: Dict[str, int], *, limit: int = 3) -> list[str]:
    return [
        issue_code
        for issue_code, _count in sorted(issue_counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _world_recommended_action(
    *,
    world_id: str,
    evaluator_analysis: Dict[str, Any],
    reranker_analysis: Dict[str, Any],
    evaluator_low_coverage: bool,
    reranker_low_coverage: bool,
    evaluator_agreement_rate: Optional[float],
    reranker_accuracy: Optional[float],
) -> str:
    if not evaluator_analysis.get("artifact_present"):
        return "train_baseline_artifact"
    if evaluator_agreement_rate is not None and evaluator_agreement_rate < 0.8:
        if reranker_accuracy is not None and reranker_accuracy < 0.75:
            return "expand_review_and_pair_data"
        return "inspect_top_mismatches"
    if not reranker_analysis.get("artifact_present"):
        return "collect_more_fix_pairs"
    if reranker_accuracy is not None and reranker_accuracy < 0.75:
        return "inspect_low_accuracy_worlds"
    if evaluator_low_coverage and reranker_low_coverage:
        return "expand_review_and_pair_data"
    if reranker_low_coverage:
        return "collect_more_fix_pairs"
    if evaluator_low_coverage:
        return "inspect_top_mismatches"
    return "monitor_shadow_candidate"


def _issue_recommended_action(
    *,
    evaluator_error_rate: Optional[float],
    reranker_error_rate: Optional[float],
) -> str:
    if evaluator_error_rate is not None and evaluator_error_rate > 0.2 and reranker_error_rate is None:
        return "add_human_review_samples"
    if reranker_error_rate is not None and reranker_error_rate > 0.2 and (evaluator_error_rate is None or evaluator_error_rate <= 0.2):
        return "expand_issue_fix_pairs"
    if evaluator_error_rate is not None and evaluator_error_rate > 0.2 and reranker_error_rate is not None and reranker_error_rate > 0.2:
        return "world_or_issue_drilldown_required"
    return "monitor_issue"


def _world_details(
    *,
    evaluator_analysis: Dict[str, Any],
    reranker_analysis: Dict[str, Any],
    chapter_review_samples: Sequence[Dict[str, Any]],
    issue_fix_pairs: Sequence[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    evaluator_issue_map, reranker_issue_map = _issue_world_maps(
        chapter_review_samples=chapter_review_samples,
        issue_fix_pairs=issue_fix_pairs,
    )
    evaluator_low = {item["world_id"] for item in evaluator_analysis.get("low_coverage_worlds", [])}
    reranker_low = {item["world_id"] for item in reranker_analysis.get("low_pair_coverage_worlds", [])}
    evaluator_world_accuracy = {
        item["world_id"]: item.get("value")
        for item in evaluator_analysis.get("top_mismatch_worlds", [])
    }
    reranker_world_accuracy = dict(reranker_analysis.get("per_world_accuracy", {}))

    world_ids = sorted(
        {
            *evaluator_issue_map.keys(),
            *reranker_issue_map.keys(),
            *evaluator_low,
            *reranker_low,
            *evaluator_world_accuracy.keys(),
            *reranker_world_accuracy.keys(),
        }
        - {""}
    )
    details = []
    for world_id in world_ids:
        evaluator_agreement_rate = evaluator_world_accuracy.get(world_id)
        reranker_accuracy = reranker_world_accuracy.get(world_id)
        evaluator_low_coverage = world_id in evaluator_low
        reranker_low_coverage = world_id in reranker_low
        details.append(
            {
                "world_id": world_id,
                "evaluator_artifact_available": bool(evaluator_analysis.get("available")),
                "reranker_artifact_available": bool(reranker_analysis.get("available")),
                "evaluator_agreement_rate": evaluator_agreement_rate,
                "reranker_accuracy": reranker_accuracy,
                "evaluator_low_coverage": evaluator_low_coverage,
                "reranker_low_coverage": reranker_low_coverage,
                "evaluator_top_issues": _top_issue_codes(evaluator_issue_map.get(world_id, {})),
                "reranker_top_issues": _top_issue_codes(reranker_issue_map.get(world_id, {})),
                "recommended_action": _world_recommended_action(
                    world_id=world_id,
                    evaluator_analysis=evaluator_analysis,
                    reranker_analysis=reranker_analysis,
                    evaluator_low_coverage=evaluator_low_coverage,
                    reranker_low_coverage=reranker_low_coverage,
                    evaluator_agreement_rate=evaluator_agreement_rate,
                    reranker_accuracy=reranker_accuracy,
                ),
            }
        )
    return details


def _issue_details(
    *,
    evaluator_analysis: Dict[str, Any],
    reranker_analysis: Dict[str, Any],
    chapter_review_samples: Sequence[Dict[str, Any]],
    issue_fix_pairs: Sequence[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    affected_worlds: Dict[str, set[str]] = {}
    for sample in chapter_review_samples:
        for issue_code in sample.get("linked_issue_codes") or sample.get("issue_codes") or []:
            affected_worlds.setdefault(issue_code, set()).add(sample.get("world_id"))
    for pair in issue_fix_pairs:
        for issue_code in pair.get("linked_issue_codes") or []:
            affected_worlds.setdefault(issue_code, set()).add(pair.get("world_id"))

    evaluator_error_map = {
        item["issue_code"]: item.get("value")
        for item in evaluator_analysis.get("top_mismatch_issue_codes", [])
    }
    reranker_error_map = dict(reranker_analysis.get("per_issue_code_error_rate", {}))
    issue_codes = sorted(set(evaluator_error_map) | set(reranker_error_map) | set(affected_worlds))

    details = []
    for issue_code in issue_codes:
        evaluator_error_rate = evaluator_error_map.get(issue_code)
        reranker_error_rate = reranker_error_map.get(issue_code)
        details.append(
            {
                "issue_code": issue_code,
                "evaluator_error_rate": evaluator_error_rate,
                "reranker_error_rate": reranker_error_rate,
                "affected_worlds": sorted(affected_worlds.get(issue_code, set()) - {None, ""}),
                "recommended_action": _issue_recommended_action(
                    evaluator_error_rate=evaluator_error_rate,
                    reranker_error_rate=reranker_error_rate,
                ),
            }
        )
    return details


def build_learned_dashboard_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    training_signal = TrainingSignalService(repository)
    evaluator_bundle = training_signal.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view="evaluator",
    )
    reranker_bundle = training_signal.export_bundle(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        dataset_view="reranker",
    )

    base_dir = Path(__file__).resolve().parents[3]
    evaluator_dir = Path(evaluator_artifact_dir or default_learned_evaluator_artifact_dir(base_dir))
    reranker_dir = Path(reranker_artifact_dir or default_learned_reranker_artifact_dir(base_dir))

    evaluator_state = load_published_artifact_state(
        artifact_dir=evaluator_dir,
        required_files=["model.joblib", "label_encoder.json", "feature_manifest.json", "metrics.json", "training_manifest.json"],
        metrics_name="metrics.json",
        manifest_name="training_manifest.json",
    )
    reranker_state = load_published_artifact_state(
        artifact_dir=reranker_dir,
        required_files=["reranker_model.joblib", "reranker_metrics.json", "reranker_feature_manifest.json", "reranker_training_manifest.json"],
        metrics_name="reranker_metrics.json",
        manifest_name="reranker_training_manifest.json",
    )

    evaluator_analysis = _evaluator_analysis(evaluator_bundle, evaluator_state)
    reranker_analysis = _reranker_analysis(reranker_bundle, reranker_state)
    cross_model_findings = _cross_model_findings(evaluator_analysis, reranker_analysis)

    warnings = list(
        dict.fromkeys(
            list(evaluator_analysis.get("warnings", []))
            + list(reranker_analysis.get("warnings", []))
        )
    )
    summary = {
        "generated_at": evaluator_bundle["generated_at"],
        "filters": evaluator_bundle["filters"],
        "artifact_status": {
            "evaluator": {
                "available": evaluator_analysis["available"],
                "artifact_present": evaluator_analysis["artifact_present"],
                "artifact_dir": evaluator_analysis["artifact_dir"],
                "published_at": evaluator_analysis.get("published_at"),
                "trained_at": evaluator_analysis.get("trained_at"),
                "source_output_dir": evaluator_analysis.get("source_output_dir"),
                "artifact_files": evaluator_analysis.get("artifact_files", []),
            },
            "reranker": {
                "available": reranker_analysis["available"],
                "artifact_present": reranker_analysis["artifact_present"],
                "artifact_dir": reranker_analysis["artifact_dir"],
                "published_at": reranker_analysis.get("published_at"),
                "trained_at": reranker_analysis.get("trained_at"),
                "source_output_dir": reranker_analysis.get("source_output_dir"),
                "artifact_files": reranker_analysis.get("artifact_files", []),
            },
        },
        "evaluator_shadow_summary": evaluator_analysis,
        "reranker_shadow_summary": reranker_analysis,
        "shared_weak_worlds": cross_model_findings["shared_weak_worlds"],
        "shared_weak_issue_codes": cross_model_findings["shared_weak_issue_codes"],
        "coverage_summary": {
            "evaluator_low_coverage_worlds": evaluator_analysis.get("low_coverage_worlds", []),
            "reranker_low_pair_coverage_worlds": reranker_analysis.get("low_pair_coverage_worlds", []),
        },
        "world_details": _world_details(
            evaluator_analysis=evaluator_analysis,
            reranker_analysis=reranker_analysis,
            chapter_review_samples=evaluator_bundle.get("chapter_review_samples", []),
            issue_fix_pairs=reranker_bundle.get("issue_fix_pairs", []),
        ),
        "issue_details": _issue_details(
            evaluator_analysis=evaluator_analysis,
            reranker_analysis=reranker_analysis,
            chapter_review_samples=evaluator_bundle.get("chapter_review_samples", []),
            issue_fix_pairs=reranker_bundle.get("issue_fix_pairs", []),
        ),
        "recommended_next_focus": cross_model_findings["recommended_next_focus"],
        "warnings": warnings,
    }
    return summary
