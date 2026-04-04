from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .learned_compare import build_learned_compare_from_dashboard
from .learned_dashboard import build_learned_dashboard_summary


TARGET_HUMAN_REVIEW_SAMPLES_PER_WORLD = 5
TARGET_REVIEWER_DIVERSITY_PER_WORLD = 2
FOCUS_ISSUE_CODES = {"Q03", "Q04", "Q05", "Q09"}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / float(denominator), 3)


def _sample_quality_flags(sample: Dict[str, Any]) -> Dict[str, Any]:
    ingestion_meta = dict(sample.get("ingestion_meta") or {})
    ingestion_warnings = list(ingestion_meta.get("ingestion_warnings") or [])
    reference_status = str(ingestion_meta.get("reference_status") or "unknown")
    linked_issue_codes = list(sample.get("linked_issue_codes") or sample.get("issue_codes") or [])
    return {
        "sample_id": sample.get("sample_id"),
        "chapter_id": sample.get("chapter_id"),
        "world_id": sample.get("world_id"),
        "world_version_id": sample.get("world_version_id"),
        "reviewer_id": sample.get("reviewer_id"),
        "created_at": sample.get("created_at"),
        "reference_status": reference_status,
        "ingestion_warnings": ingestion_warnings,
        "missing_session_context": "missing_session_context" in ingestion_warnings,
        "missing_linked_issue_codes": "missing_linked_issue_codes" in ingestion_warnings or not linked_issue_codes,
        "reference_not_validated": reference_status != "validated",
        "has_quality_warning": bool(ingestion_warnings) or reference_status != "validated" or not linked_issue_codes,
        "linked_issue_codes": linked_issue_codes,
        "freeform_notes": sample.get("freeform_notes", ""),
    }


def _world_replenishment_priority(
    *,
    shared_weak_world: bool,
    disagreement_issue_hits: int,
    coverage_gap: int,
    reviewer_diversity_gap: int,
    warning_sample_count: int,
    candidate_backlog_count: int,
) -> str:
    if shared_weak_world or disagreement_issue_hits > 0 or coverage_gap >= 3:
        return "high"
    if reviewer_diversity_gap > 0 or candidate_backlog_count > 0 or warning_sample_count > 0:
        return "medium"
    return "low"


def _world_recommended_action(
    *,
    coverage_gap: int,
    reviewer_diversity_gap: int,
    warning_sample_count: int,
    focus_issue_gaps: Sequence[str],
    shared_weak_world: bool,
    disagreement_issue_hits: Sequence[str],
) -> str:
    if coverage_gap > 0 and (shared_weak_world or disagreement_issue_hits):
        return "capture_human_review_priority"
    if coverage_gap > 0:
        return "increase_human_review_coverage"
    if reviewer_diversity_gap > 0:
        return "expand_reviewer_diversity"
    if warning_sample_count > 0:
        return "repair_review_sample_quality"
    if focus_issue_gaps:
        return "fill_focus_issue_gaps"
    return "coverage_sufficient"


def build_learned_review_quality_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    training_signal = TrainingSignalService(repository)
    human_review_samples = training_signal.list_review_samples(
        world_id=world_id,
        world_version_id=world_version_id,
        source="human_review",
        limit=None,
    )
    quality_flags = [_sample_quality_flags(sample) for sample in human_review_samples]
    dashboard_summary = build_learned_dashboard_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    compare_summary = build_learned_compare_from_dashboard(dashboard_summary)
    review_backlog = training_signal.review_sample_backlog(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
    )

    samples_by_world: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    backlog_by_world: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for sample in quality_flags:
        samples_by_world[str(sample.get("world_id") or "")].append(sample)
    for item in review_backlog:
        backlog_by_world[str(item.get("world_id") or "")].append(item)

    disagreement_issue_map: Dict[str, List[str]] = defaultdict(list)
    for item in compare_summary.get("disagreement_worlds", []):
        disagreement_issue_map[str(item.get("world_id") or "")] = [
            str(code) for code in item.get("issue_codes", []) if str(code).strip()
        ]
    disagreement_issue_codes = {
        str(item.get("issue_code") or "")
        for item in compare_summary.get("disagreement_issue_codes", [])
        if str(item.get("issue_code") or "").strip()
    }
    shared_weak_worlds = set(dashboard_summary.get("shared_weak_worlds", []))

    all_world_ids = sorted(
        {
            *[str(item.get("world_id") or "") for item in quality_flags],
            *[str(item.get("world_id") or "") for item in review_backlog],
            *[str(item) for item in shared_weak_worlds],
        }
        - {""}
    )

    world_details: List[Dict[str, Any]] = []
    replenishment_backlog: List[Dict[str, Any]] = []
    for current_world_id in all_world_ids:
        samples = samples_by_world.get(current_world_id, [])
        backlog_items = backlog_by_world.get(current_world_id, [])
        reviewer_ids = {
            str(item.get("reviewer_id") or "")
            for item in samples
            if str(item.get("reviewer_id") or "").strip()
        }
        issue_counter = Counter(
            issue_code
            for sample in samples
            for issue_code in list(sample.get("linked_issue_codes") or [])
            if issue_code
        )
        backlog_issue_codes = {
            issue_code
            for item in backlog_items
            for issue_code in list(item.get("issue_codes") or [])
            if issue_code in FOCUS_ISSUE_CODES
        }
        disagreement_issue_hits = sorted(
            {
                issue_code
                for issue_code in backlog_issue_codes | disagreement_issue_codes
                if issue_counter.get(issue_code, 0) <= 0 and any(
                    issue_code in list(item.get("issue_codes") or [])
                    for item in backlog_items
                )
            }
        )
        focus_issue_gaps = sorted(
            {
                issue_code
                for issue_code in backlog_issue_codes
                if issue_counter.get(issue_code, 0) <= 0
            }
        )
        sample_count = len(samples)
        chapter_coverage_count = len({str(item.get("chapter_id") or "") for item in samples if str(item.get("chapter_id") or "")})
        reviewer_diversity_count = len(reviewer_ids)
        warning_sample_count = sum(1 for item in samples if item.get("has_quality_warning"))
        validated_reference_count = sum(1 for item in samples if not item.get("reference_not_validated"))
        coverage_gap = max(0, TARGET_HUMAN_REVIEW_SAMPLES_PER_WORLD - sample_count)
        reviewer_diversity_gap = max(0, TARGET_REVIEWER_DIVERSITY_PER_WORLD - reviewer_diversity_count)
        shared_weak_world = current_world_id in shared_weak_worlds
        recommended_action = _world_recommended_action(
            coverage_gap=coverage_gap,
            reviewer_diversity_gap=reviewer_diversity_gap,
            warning_sample_count=warning_sample_count,
            focus_issue_gaps=focus_issue_gaps,
            shared_weak_world=shared_weak_world,
            disagreement_issue_hits=disagreement_issue_hits,
        )
        detail = {
            "world_id": current_world_id,
            "world_version_ids": sorted(
                {
                    str(item.get("world_version_id") or "")
                    for item in samples + backlog_items
                    if str(item.get("world_version_id") or "")
                }
            ),
            "human_review_count": sample_count,
            "chapter_coverage_count": chapter_coverage_count,
            "reviewer_diversity_count": reviewer_diversity_count,
            "warning_sample_count": warning_sample_count,
            "validated_reference_rate": _safe_ratio(validated_reference_count, sample_count),
            "coverage_gap": coverage_gap,
            "reviewer_diversity_gap": reviewer_diversity_gap,
            "focus_issue_gaps": focus_issue_gaps,
            "shared_weak_world": shared_weak_world,
            "disagreement_issue_hits": disagreement_issue_hits,
            "candidate_backlog_chapters": [item.get("chapter_id") for item in backlog_items[:3]],
            "recommended_action": recommended_action,
            "priority": _world_replenishment_priority(
                shared_weak_world=shared_weak_world,
                disagreement_issue_hits=len(disagreement_issue_hits),
                coverage_gap=coverage_gap,
                reviewer_diversity_gap=reviewer_diversity_gap,
                warning_sample_count=warning_sample_count,
                candidate_backlog_count=len(backlog_items),
            ),
        }
        world_details.append(detail)
        if recommended_action != "coverage_sufficient":
            replenishment_backlog.append(detail)

    world_details.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["priority"], 3),
            -int(item.get("coverage_gap", 0) or 0),
            -int(item.get("warning_sample_count", 0) or 0),
            str(item.get("world_id") or ""),
        )
    )
    replenishment_backlog.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["priority"], 3),
            -int(item.get("coverage_gap", 0) or 0),
            -int(item.get("reviewer_diversity_gap", 0) or 0),
            str(item.get("world_id") or ""),
        )
    )

    warnings = []
    if not human_review_samples:
        warnings.append("missing_human_review_samples")
    if any(item.get("warning_sample_count", 0) > 0 for item in world_details):
        warnings.append("human_review_quality_warnings_present")
    if any(item.get("coverage_gap", 0) > 0 for item in world_details):
        warnings.append("human_review_coverage_below_target")
    if any(item.get("reviewer_diversity_gap", 0) > 0 for item in world_details):
        warnings.append("reviewer_diversity_below_target")
    if any(item.get("focus_issue_gaps") for item in world_details):
        warnings.append("focus_issue_review_gaps_present")

    quality_summary = {
        "sample_count": len(human_review_samples),
        "world_coverage_count": len({item["world_id"] for item in world_details}),
        "version_coverage_count": len(
            {
                version_id
                for item in world_details
                for version_id in item.get("world_version_ids", [])
            }
        ),
        "warning_sample_count": sum(1 for item in quality_flags if item.get("has_quality_warning")),
        "missing_session_context_count": sum(1 for item in quality_flags if item.get("missing_session_context")),
        "missing_linked_issue_codes_count": sum(1 for item in quality_flags if item.get("missing_linked_issue_codes")),
        "reference_not_validated_count": sum(1 for item in quality_flags if item.get("reference_not_validated")),
        "validated_reference_rate": _safe_ratio(
            sum(1 for item in quality_flags if not item.get("reference_not_validated")),
            len(quality_flags),
        ),
    }
    coverage_summary = {
        "target_sample_count_per_world": TARGET_HUMAN_REVIEW_SAMPLES_PER_WORLD,
        "target_reviewer_diversity_per_world": TARGET_REVIEWER_DIVERSITY_PER_WORLD,
        "worlds_below_target_count": sum(1 for item in world_details if item.get("coverage_gap", 0) > 0),
        "low_diversity_world_count": sum(1 for item in world_details if item.get("reviewer_diversity_gap", 0) > 0),
        "focus_issue_gap_world_count": sum(1 for item in world_details if item.get("focus_issue_gaps")),
        "shared_weak_worlds": list(dashboard_summary.get("shared_weak_worlds", [])),
        "disagreement_issue_codes": list(
            str(item.get("issue_code") or "")
            for item in compare_summary.get("disagreement_issue_codes", [])
            if str(item.get("issue_code") or "").strip()
        ),
    }

    flagged_samples = [item for item in quality_flags if item.get("has_quality_warning")]
    flagged_samples.sort(
        key=lambda item: (
            0 if item.get("missing_linked_issue_codes") else 1,
            0 if item.get("missing_session_context") else 1,
            0 if item.get("reference_not_validated") else 1,
            str(item.get("world_id") or ""),
        )
    )

    return {
        "generated_at": dashboard_summary.get("generated_at"),
        "filters": {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "limit": limit,
        },
        "coverage_summary": coverage_summary,
        "quality_summary": quality_summary,
        "replenishment_backlog": replenishment_backlog[:limit] if limit is not None else replenishment_backlog,
        "world_details": world_details[:limit] if limit is not None else world_details,
        "flagged_samples": flagged_samples[:limit] if limit is not None else flagged_samples,
        "warnings": warnings,
    }


def build_learned_review_quality_world_detail(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: str,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = build_learned_review_quality_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=None,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    detail = next((item for item in summary.get("world_details", []) if item.get("world_id") == world_id), None)
    if detail is None:
        raise KeyError(f"unknown_learned_review_quality_world:{world_id}")
    return {
        "generated_at": summary.get("generated_at"),
        "filters": summary.get("filters", {}),
        "world_id": world_id,
        "world_detail": detail,
        "flagged_samples": [
            item for item in summary.get("flagged_samples", [])
            if item.get("world_id") == world_id
        ][:limit] if limit is not None else [
            item for item in summary.get("flagged_samples", [])
            if item.get("world_id") == world_id
        ],
        "warnings": summary.get("warnings", []),
    }
