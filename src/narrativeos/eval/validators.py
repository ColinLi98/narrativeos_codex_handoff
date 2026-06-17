from __future__ import annotations

from typing import Dict, Iterable, List

from ..meta_leak_detector import detect_meta_leaks
from ..models import EvaluationIssue, NarrativeState
from ..prose_linter import extract_latin_token_hits, story_text_unit_count
from ..repetition_detector import repetition_signal_bundle
from ..style_sanitizer import style_sanitize
from .taxonomy import ISSUE_TAXONOMY


LONGFORM_Q03_SIGNAL_THRESHOLDS = {
    "semantic_paragraph_similarity_score": 0.84,
    "event_coverage_gap_score": 0.5,
    "beat_coverage_gap_score": 0.42,
    "uncovered_beat_count": 1,
    "overcovered_beat_count": 2,
    "hard_paragraph_similarity_score": 0.93,
    "hard_n_gram_repetition_score": 0.65,
    "hard_suspicious_refrain_count": 5,
}

SHORTFORM_Q03_SIGNAL_THRESHOLDS = {
    "lexical_repetition_score": 0.16,
    "paragraph_similarity_score": 0.88,
    "n_gram_repetition_score": 0.15,
    "beat_structure_repetition_score": 0.7,
    "suspicious_refrain_count": 2,
}


def _issue(code: str, severity: str, summary: str, evidence: List[str]) -> EvaluationIssue:
    return EvaluationIssue(
        issue_code=code,
        severity=severity,
        summary=summary,
        owning_module=ISSUE_TAXONOMY[code]["owning_module"],
        evidence=evidence,
    )


def engineering_leak_validator(text: str) -> List[EvaluationIssue]:
    leaks = detect_meta_leaks(text)
    engineering_hits = [hit for hit in leaks if "event_id" in hit or "_" in hit or "->" in hit]
    if not engineering_hits:
        return []
    return [_issue("Q01", "high", "正文出现工程化字段或路由表达。", engineering_hits)]


def meta_narration_validator(text: str) -> List[EvaluationIssue]:
    leaks = detect_meta_leaks(text)
    meta_hits = [hit for hit in leaks if "第" in hit or "这一章" in hit or "从这里起" in hit or "放远一点看" in hit]
    if not meta_hits:
        return []
    return [_issue("Q02", "high", "正文仍然带有策划/元叙事口吻。", meta_hits)]


def paragraph_repetition_validator(
    paragraphs: Iterable[str],
    *,
    text_unit_count_value: int,
    coverage_context: Dict[str, object] | None = None,
    precomputed_bundle: Dict[str, object] | None = None,
) -> List[EvaluationIssue]:
    bundle = dict(precomputed_bundle or repetition_signal_bundle(paragraphs, coverage_context=coverage_context))
    context = dict(coverage_context or {})
    chapter_task = dict(context.get("chapter_task") or {})
    longform_context = bool(chapter_task) and int(chapter_task.get("target_words", 0) or 0) >= 1500
    if text_unit_count_value >= 1800 or (text_unit_count_value >= 1500 and longform_context):
        medium_hits: List[str] = []
        repetition_hits: List[str] = []
        coverage_hits: List[str] = []
        if float(bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["semantic_paragraph_similarity_score"]:
            medium_hits.append("semantic_paragraph_similarity")
            repetition_hits.append("semantic_paragraph_similarity")
        if float(bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["event_coverage_gap_score"]:
            medium_hits.append("event_coverage_gap")
            coverage_hits.append("event_coverage_gap")
        if float(bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["beat_coverage_gap_score"]:
            medium_hits.append("beat_coverage_gap")
            coverage_hits.append("beat_coverage_gap")
        if int(bundle.get("uncovered_beat_count", 0) or 0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["uncovered_beat_count"]:
            medium_hits.append("uncovered_beat")
            coverage_hits.append("uncovered_beat")
        if int(bundle.get("overcovered_beat_count", 0) or 0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["overcovered_beat_count"]:
            medium_hits.append("overcovered_beat")
            coverage_hits.append("overcovered_beat")
        if int(bundle.get("suspicious_refrain_count", 0) or 0) >= 2:
            medium_hits.append("suspicious_refrain")
            repetition_hits.append("suspicious_refrain")
        hard_hit = (
            float(bundle.get("paragraph_similarity_score", 0.0) or 0.0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["hard_paragraph_similarity_score"]
            or (
                float(bundle.get("n_gram_repetition_score", 0.0) or 0.0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["hard_n_gram_repetition_score"]
                and int(bundle.get("suspicious_refrain_count", 0) or 0) >= LONGFORM_Q03_SIGNAL_THRESHOLDS["hard_suspicious_refrain_count"]
            )
        )
        coverage_only = bool(coverage_hits) and not repetition_hits
        if coverage_only and not hard_hit:
            return []
        if not hard_hit and len(medium_hits) < 2:
            return []
        evidence = [
            "lexical_repetition_score=%.3f" % float(bundle.get("lexical_repetition_score", 0.0) or 0.0),
            "semantic_paragraph_similarity_score=%.3f" % float(bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0),
            "paragraph_similarity_score=%.3f" % float(bundle.get("paragraph_similarity_score", 0.0) or 0.0),
            "n_gram_repetition_score=%.3f" % float(bundle.get("n_gram_repetition_score", 0.0) or 0.0),
            "beat_structure_repetition_score=%.3f" % float(bundle.get("beat_structure_repetition_score", 0.0) or 0.0),
            "event_coverage_gap_score=%.3f" % float(bundle.get("event_coverage_gap_score", 0.0) or 0.0),
            "beat_coverage_gap_score=%.3f" % float(bundle.get("beat_coverage_gap_score", 0.0) or 0.0),
            "uncovered_event_count=%s" % int(bundle.get("uncovered_event_count", 0) or 0),
            "uncovered_beat_count=%s" % int(bundle.get("uncovered_beat_count", 0) or 0),
            "overcovered_beat_count=%s" % int(bundle.get("overcovered_beat_count", 0) or 0),
            "suspicious_refrain_count=%s" % int(bundle.get("suspicious_refrain_count", 0) or 0),
            "trigger_signals=%s" % (",".join(medium_hits) or "hard_signal"),
            "selected_event_ids=%s" % ",".join(str(item) for item in bundle.get("selected_event_ids", [])[:6]),
            "coverage_gap_examples=%s" % str(bundle.get("coverage_gap_examples", [])[:3]),
        ]
        return [_issue("Q03", "medium", "章节存在结构性回环，疑似靠重复扩写撑长。", evidence)]
    if (
        float(bundle.get("lexical_repetition_score", 0.0) or 0.0) <= SHORTFORM_Q03_SIGNAL_THRESHOLDS["lexical_repetition_score"]
        and float(bundle.get("paragraph_similarity_score", 0.0) or 0.0) <= SHORTFORM_Q03_SIGNAL_THRESHOLDS["paragraph_similarity_score"]
        and float(bundle.get("n_gram_repetition_score", 0.0) or 0.0) <= SHORTFORM_Q03_SIGNAL_THRESHOLDS["n_gram_repetition_score"]
        and float(bundle.get("beat_structure_repetition_score", 0.0) or 0.0) <= SHORTFORM_Q03_SIGNAL_THRESHOLDS["beat_structure_repetition_score"]
        and int(bundle.get("suspicious_refrain_count", 0) or 0) < SHORTFORM_Q03_SIGNAL_THRESHOLDS["suspicious_refrain_count"]
    ):
        return []
    return [
        _issue(
            "Q03",
            "medium",
            "章节段落重复感偏高。",
            [
                "lexical_repetition_score=%.3f" % float(bundle.get("lexical_repetition_score", 0.0) or 0.0),
                "paragraph_similarity_score=%.3f" % float(bundle.get("paragraph_similarity_score", 0.0) or 0.0),
                "n_gram_repetition_score=%.3f" % float(bundle.get("n_gram_repetition_score", 0.0) or 0.0),
                "beat_structure_repetition_score=%.3f" % float(bundle.get("beat_structure_repetition_score", 0.0) or 0.0),
                "suspicious_refrain_count=%s" % int(bundle.get("suspicious_refrain_count", 0) or 0),
            ],
        )
    ]


def chapter_structure_validator(
    *,
    text: str,
    paragraphs: List[str],
    dialogue_count: int,
    action_count: int,
    detail_count: int,
) -> List[EvaluationIssue]:
    issues: List[EvaluationIssue] = []
    if len(text) < 650:
        issues.append(_issue("Q04", "medium", "章节篇幅过短，容易只剩说明。", ["chars=%s" % len(text)]))
    if dialogue_count < 1:
        issues.append(_issue("Q05", "medium", "章节缺少对白。", ["dialogue_count=%s" % dialogue_count]))
    if action_count < 2 or detail_count < 2:
        issues.append(_issue("Q05", "medium", "章节缺少动作或场景细节。", ["action_count=%s" % action_count, "detail_count=%s" % detail_count]))
    if len(paragraphs) <= 1:
        issues.append(_issue("Q04", "medium", "章节结构过薄。", ["paragraphs=%s" % len(paragraphs)]))
    return issues


def premature_ending_validator(
    *,
    state_after: NarrativeState,
    ending_ready: bool,
    body: str,
) -> List[EvaluationIssue]:
    if not ending_ready:
        return []
    issues: List[EvaluationIssue] = []
    if state_after.chapter_index < state_after.min_end_turn:
        issues.append(_issue("Q09", "high", "章节过早触发结局。", ["chapter_index=%s" % state_after.chapter_index, "min_end_turn=%s" % state_after.min_end_turn]))
    hook_line = body.split("\n\n")[-1] if body else ""
    if not hook_line.strip():
        issues.append(_issue("Q09", "medium", "章节结尾缺少继续阅读钩子。", []))
    return issues


def run_hard_validators(
    *,
    text: str,
    paragraphs: List[str],
    dialogue_count: int,
    action_count: int,
    detail_count: int,
    state_after: NarrativeState,
    ending_ready: bool,
    coverage_context: Dict[str, object] | None = None,
) -> Dict[str, object]:
    issues: List[EvaluationIssue] = []
    unit_count = story_text_unit_count(text)
    repetition_bundle = repetition_signal_bundle(paragraphs, coverage_context=coverage_context)
    latin_token_hits = extract_latin_token_hits(text, field="body")
    issues.extend(engineering_leak_validator(text))
    issues.extend(meta_narration_validator(text))
    issues.extend(
        paragraph_repetition_validator(
            paragraphs,
            text_unit_count_value=unit_count,
            coverage_context=coverage_context,
            precomputed_bundle=repetition_bundle,
        )
    )
    issues.extend(
        chapter_structure_validator(
            text=text,
            paragraphs=paragraphs,
            dialogue_count=dialogue_count,
            action_count=action_count,
            detail_count=detail_count,
        )
    )
    issues.extend(
        premature_ending_validator(
            state_after=state_after,
            ending_ready=ending_ready,
            body=text,
        )
    )
    return {
        "issues": [issue.to_dict() for issue in issues],
        "failed": any(issue.severity == "high" for issue in issues),
        "repetition_signal_bundle": repetition_bundle,
        "latin_token_hits": latin_token_hits,
        "disallowed_latin_token_hits": [item for item in latin_token_hits if not item["allowed"]],
    }
