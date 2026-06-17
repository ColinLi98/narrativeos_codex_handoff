from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..content_quality_contracts import (
    evaluate_chapter_quality_contract,
    resolve_chapter_task_quality_contract_from_coverage,
    resolve_scene_function_from_coverage,
    resolve_scene_quality_contract_from_coverage,
)
from ..core.linter import lint_chapter_draft
from ..models import EvaluationIssue, EvaluationReport, NarrativeState, SceneBeat
from ..prose_linter import extract_latin_token_hits
from .reporting import build_evaluation_report
from .scorers import derive_scoring_issues, score_chapter
from .validators import run_hard_validators


CHAPTER_QUALITY_GUARD_FAILURE_CODE = "chapter_quality_guard_failed"


class ChapterQualityGuardError(ValueError):
    def __init__(self, quality_gate: Dict[str, Any]) -> None:
        self.quality_gate = dict(quality_gate)
        super().__init__(CHAPTER_QUALITY_GUARD_FAILURE_CODE)


def _required_text_units_for_persistence(
    *,
    target_words: Optional[int] = None,
    min_target_words: Optional[int] = None,
) -> int:
    if min_target_words is not None:
        try:
            return max(0, int(min_target_words))
        except (TypeError, ValueError):
            return 0
    if target_words is not None:
        try:
            return max(0, int(round(float(target_words) * 0.9)))
        except (TypeError, ValueError):
            return 0
    return 0


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_chapter_quality_gate(
    *,
    report: EvaluationReport,
    target_words: Optional[int] = None,
    min_target_words: Optional[int] = None,
    latin_token_hits: Optional[Sequence[Dict[str, Any]]] = None,
    chapter_index: Optional[int] = None,
    target_chapters: Optional[int] = None,
    story_phase: Optional[str] = None,
    scene_quality_contract: Optional[Dict[str, Any]] = None,
    chapter_task_quality_contract: Optional[Dict[str, Any]] = None,
    rolling_quality_window: Optional[Sequence[Dict[str, Any]]] = None,
    scene_function: str = "",
    chapter_task_id: str = "",
    ending_ready: bool = False,
    enforcement_scope: str = "persisted_chapter",
) -> Dict[str, Any]:
    lint_metrics = dict((report.hard_validator_results or {}).get("lint_metrics") or {})
    actual_text_units = int(lint_metrics.get("text_unit_count") or 0)
    required_text_units = _required_text_units_for_persistence(
        target_words=target_words,
        min_target_words=min_target_words,
    )
    decision = str((report.decision or {}).decision if report.decision else "")
    latin_hits = [dict(item or {}) for item in list(latin_token_hits or [])]
    disallowed_latin_hits = [item for item in latin_hits if not bool(item.get("allowed"))]
    failed_checks = []
    if required_text_units and actual_text_units < required_text_units:
        failed_checks.append("text_unit_floor_not_met")
    if disallowed_latin_hits:
        failed_checks.append("disallowed_latin_token_detected")
    if decision != "pass":
        failed_checks.append("decision_not_pass")
    issues = [issue.to_dict() for issue in list(report.issues or [])]
    owning_modules = sorted(
        {
            str(item.get("owning_module") or "").strip()
            for item in issues
            if isinstance(item, dict) and str(item.get("owning_module") or "").strip()
        }
    )
    if "text_unit_floor_not_met" in failed_checks and "writer" not in owning_modules:
        owning_modules.append("writer")
    if "disallowed_latin_token_detected" in failed_checks and "writer" not in owning_modules:
        owning_modules.append("writer")
    contract_gate = evaluate_chapter_quality_contract(
        report=report,
        chapter_index=int(chapter_index or 0),
        target_chapters=int(target_chapters or 0),
        story_phase=str(story_phase or ""),
        scene_quality_contract=scene_quality_contract,
        chapter_task_quality_contract=chapter_task_quality_contract,
        rolling_quality_window=rolling_quality_window,
        scene_function=scene_function,
        chapter_task_id=chapter_task_id,
        ending_ready=ending_ready,
        enforcement_scope=enforcement_scope,
    )
    failed_contract_checks = list(contract_gate.get("failed_contract_checks") or [])
    all_failed_checks = list(failed_checks) + failed_contract_checks
    primary_issue_group = str(contract_gate.get("primary_issue_group") or "")
    disallowed_fields = sorted({str(item.get("field") or "") for item in disallowed_latin_hits if str(item.get("field") or "").strip()})
    disallowed_tokens = list(dict.fromkeys(str(item.get("token") or "") for item in disallowed_latin_hits if str(item.get("token") or "").strip()))
    summary = report.summary
    if disallowed_tokens:
        summary = "reader 可见文本包含未允许的英文 token：%s" % " / ".join(disallowed_tokens[:5])
    elif failed_contract_checks:
        summary = "章节未通过共享内容质量 contract：%s" % " / ".join(failed_contract_checks[:3])
    enforced_decision = decision
    if decision == "block":
        enforced_decision = "block"
    elif all_failed_checks:
        should_block = primary_issue_group == "Q09" and float(contract_gate.get("completion_ratio", 1.0) or 1.0) < 0.96
        should_block = should_block or any(
            item in failed_contract_checks for item in ("rolling_window_repeat_breach", "rolling_window_exposition_breach")
        )
        enforced_decision = "block" if should_block else "rewrite"
    return {
        "ok": not all_failed_checks,
        "code": CHAPTER_QUALITY_GUARD_FAILURE_CODE,
        "decision": decision,
        "enforced_decision": enforced_decision,
        "target_words": _safe_int(target_words),
        "min_target_words": _safe_int(min_target_words),
        "required_text_units": required_text_units,
        "actual_text_units": actual_text_units,
        "issues": issues,
        "scores": report.scores.to_dict(),
        "owning_modules": owning_modules,
        "failed_checks": all_failed_checks,
        "summary": summary,
        "latin_token_hits": latin_hits,
        "disallowed_latin_token_hits": disallowed_latin_hits,
        "latin_token_fields": disallowed_fields,
        "latin_token_tokens": disallowed_tokens,
        "latin_token_whitelist_rule": "uppercase_acronyms_only",
        "contract_checks": list(contract_gate.get("contract_checks") or []),
        "contract_thresholds": dict(contract_gate.get("contract_thresholds") or {}),
        "primary_issue_group": primary_issue_group,
        "primary_asset_target": dict(contract_gate.get("primary_asset_target") or {}),
        "window_breach_kind": str(contract_gate.get("window_breach_kind") or ""),
        "blocking_dimension": str(contract_gate.get("blocking_dimension") or primary_issue_group),
        "enforcement_scope": str(contract_gate.get("enforcement_scope") or enforcement_scope),
        "quality_contract_window": list(contract_gate.get("quality_contract_window") or []),
    }


def evaluate_persisted_chapter(
    *,
    chapter_id: str,
    world_version_id: str,
    session_id: str,
    body: str,
    paragraphs: Sequence[str],
    dialogue_count: int,
    action_count: int,
    detail_count: int,
    character_fidelity_score: float,
    state_after: NarrativeState,
    ending_ready: bool,
    chapter_title: Optional[str] = None,
    recap: Optional[str] = None,
    relationship_hints: Optional[Sequence[str]] = None,
    choices: Sequence[str],
    paywall_required: bool,
    coverage_context: Optional[Dict[str, Any]] = None,
    target_words: Optional[int] = None,
    min_target_words: Optional[int] = None,
    chapter_index: Optional[int] = None,
    target_chapters: Optional[int] = None,
    story_phase: Optional[str] = None,
    scene_quality_contract: Optional[Dict[str, Any]] = None,
    chapter_task_quality_contract: Optional[Dict[str, Any]] = None,
    rolling_quality_window: Optional[Sequence[Dict[str, Any]]] = None,
    enforcement_scope: str = "persisted_chapter",
) -> Dict[str, Any]:
    report = evaluate_chapter(
        chapter_id=chapter_id,
        world_version_id=world_version_id,
        session_id=session_id,
        body=body,
        paragraphs=paragraphs,
        dialogue_count=dialogue_count,
        action_count=action_count,
        detail_count=detail_count,
        character_fidelity_score=character_fidelity_score,
        state_after=state_after,
        ending_ready=ending_ready,
        choices=choices,
        paywall_required=paywall_required,
        coverage_context=coverage_context,
    )
    latin_token_hits = extract_latin_token_hits(body, field="body")
    if chapter_title:
        latin_token_hits.extend(extract_latin_token_hits(chapter_title, field="chapter_title"))
    if recap:
        latin_token_hits.extend(extract_latin_token_hits(recap, field="recap"))
    for index, relationship_hint in enumerate(list(relationship_hints or []), start=1):
        latin_token_hits.extend(extract_latin_token_hits(str(relationship_hint or ""), field=f"relationship_hint_{index}"))
    for index, choice in enumerate(list(choices or []), start=1):
        latin_token_hits.extend(extract_latin_token_hits(str(choice or ""), field=f"choice_{index}"))
    quality_gate = build_chapter_quality_gate(
        report=report,
        target_words=target_words,
        min_target_words=min_target_words,
        latin_token_hits=latin_token_hits,
        chapter_index=chapter_index if chapter_index is not None else int(state_after.chapter_index or 0),
        target_chapters=target_chapters,
        story_phase=story_phase if story_phase is not None else str(state_after.story_phase or ""),
        scene_quality_contract=scene_quality_contract or resolve_scene_quality_contract_from_coverage(coverage_context),
        chapter_task_quality_contract=chapter_task_quality_contract or resolve_chapter_task_quality_contract_from_coverage(coverage_context),
        rolling_quality_window=rolling_quality_window or list((state_after.metadata or {}).get("quality_contract_window", [])),
        scene_function=resolve_scene_function_from_coverage(coverage_context),
        chapter_task_id=str(dict((coverage_context or {}).get("chapter_task") or {}).get("chapter_task_id") or ""),
        ending_ready=ending_ready,
        enforcement_scope=enforcement_scope,
    )
    return {
        "report": report,
        "quality_gate": quality_gate,
    }


def apply_quality_gate_to_report(report: EvaluationReport, quality_gate: Dict[str, Any]) -> Dict[str, Any]:
    payload = report.to_dict()
    payload["quality_gate"] = dict(quality_gate or {})
    if not quality_gate.get("ok", False):
        payload["decision"] = {
            **dict(payload.get("decision") or {}),
            "decision": quality_gate.get("enforced_decision") or "rewrite",
            "reason": CHAPTER_QUALITY_GUARD_FAILURE_CODE,
        }
        payload["summary"] = str(quality_gate.get("summary") or "章节未通过持久化硬约束。")
    return payload


def evaluate_chapter(
    *,
    chapter_id: str,
    world_version_id: str,
    session_id: str,
    body: str,
    paragraphs: Sequence[str],
    dialogue_count: int,
    action_count: int,
    detail_count: int,
    character_fidelity_score: float,
    state_after: NarrativeState,
    ending_ready: bool,
    choices: Sequence[str],
    paywall_required: bool,
    coverage_context: Optional[Dict[str, Any]] = None,
) -> EvaluationReport:
    lint_report = lint_chapter_draft(body)
    hard = run_hard_validators(
        text=body,
        paragraphs=list(paragraphs or lint_report["paragraphs"]),
        dialogue_count=dialogue_count or int(lint_report["dialogue_count"]),
        action_count=action_count or int(lint_report["action_count"]),
        detail_count=detail_count or int(lint_report["detail_count"]),
        state_after=state_after,
        ending_ready=ending_ready,
        coverage_context=coverage_context,
    )
    issues: list[EvaluationIssue] = [EvaluationIssue.from_dict(item) for item in hard["issues"]]
    scores = score_chapter(
        body=body,
        dialogue_count=dialogue_count or int(lint_report["dialogue_count"]),
        action_count=action_count or int(lint_report["action_count"]),
        detail_count=detail_count or int(lint_report["detail_count"]),
        character_fidelity_score=character_fidelity_score,
        issues=issues,
        state_after=state_after,
        ending_ready=ending_ready,
        choices=choices,
        paywall_required=paywall_required,
    )
    soft_issues = derive_scoring_issues(
        scores=scores,
        exposition_ratio=float(lint_report["exposition_ratio"]),
        concrete_detail_density=float(lint_report["concrete_detail_density"]),
        text_unit_count=int(lint_report.get("text_unit_count") or 0),
        ending_ready=ending_ready,
        state_after=state_after,
    )
    issues.extend(soft_issues)
    return build_evaluation_report(
        chapter_id=chapter_id,
        world_version_id=world_version_id,
        session_id=session_id,
        issues=issues,
        scores=scores,
        hard_validator_results={
            **hard,
            "issues": [issue.to_dict() for issue in issues],
            "lint_metrics": {
                "meta_sentence_rate": lint_report["meta_sentence_rate"],
                "engineering_leak_rate": lint_report["engineering_leak_rate"],
                "repetition_score": lint_report["repetition_score"],
                "repetition_signal_bundle": {
                    **dict(lint_report.get("repetition_signal_bundle") or {}),
                    **dict(hard.get("repetition_signal_bundle") or {}),
                },
                "lexical_repetition_score": (hard.get("repetition_signal_bundle") or {}).get("lexical_repetition_score", lint_report.get("lexical_repetition_score", 0.0)),
                "paragraph_similarity_score": (hard.get("repetition_signal_bundle") or {}).get("paragraph_similarity_score", lint_report.get("paragraph_similarity_score", 0.0)),
                "semantic_paragraph_similarity_score": (hard.get("repetition_signal_bundle") or {}).get("semantic_paragraph_similarity_score", 0.0),
                "n_gram_repetition_score": (hard.get("repetition_signal_bundle") or {}).get("n_gram_repetition_score", lint_report.get("n_gram_repetition_score", 0.0)),
                "beat_structure_repetition_score": (hard.get("repetition_signal_bundle") or {}).get("beat_structure_repetition_score", lint_report.get("beat_structure_repetition_score", 0.0)),
                "suspicious_refrain_count": (hard.get("repetition_signal_bundle") or {}).get("suspicious_refrain_count", lint_report.get("suspicious_refrain_count", 0)),
                "event_coverage_gap_score": (hard.get("repetition_signal_bundle") or {}).get("event_coverage_gap_score", 0.0),
                "beat_coverage_gap_score": (hard.get("repetition_signal_bundle") or {}).get("beat_coverage_gap_score", 0.0),
                "uncovered_event_count": (hard.get("repetition_signal_bundle") or {}).get("uncovered_event_count", 0),
                "uncovered_beat_count": (hard.get("repetition_signal_bundle") or {}).get("uncovered_beat_count", 0),
                "overcovered_beat_count": (hard.get("repetition_signal_bundle") or {}).get("overcovered_beat_count", 0),
                "semantic_paragraph_similarity_pairs": (hard.get("repetition_signal_bundle") or {}).get("semantic_paragraph_similarity_pairs", []),
                "coverage_gap_examples": (hard.get("repetition_signal_bundle") or {}).get("coverage_gap_examples", []),
                "exposition_ratio": lint_report["exposition_ratio"],
                "dialogue_plus_action_ratio": lint_report["dialogue_plus_action_ratio"],
                "concrete_detail_density": lint_report["concrete_detail_density"],
                "text_unit_count": lint_report.get("text_unit_count", 0),
                "latin_token_hits": lint_report.get("latin_token_hits", []),
                "disallowed_latin_token_hits": lint_report.get("disallowed_latin_token_hits", []),
            },
        },
    )
