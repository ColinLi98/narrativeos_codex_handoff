from __future__ import annotations

from typing import Dict, Iterable, List

from ..meta_leak_detector import detect_meta_leaks
from ..models import EvaluationIssue, NarrativeState
from ..repetition_detector import repetition_score
from ..style_sanitizer import style_sanitize
from .taxonomy import ISSUE_TAXONOMY


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


def paragraph_repetition_validator(paragraphs: Iterable[str]) -> List[EvaluationIssue]:
    score = repetition_score(paragraphs)
    if score <= 0.16:
        return []
    return [_issue("Q03", "medium", "章节段落重复感偏高。", ["repetition_score=%.3f" % score])]


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
) -> Dict[str, object]:
    issues: List[EvaluationIssue] = []
    issues.extend(engineering_leak_validator(text))
    issues.extend(meta_narration_validator(text))
    issues.extend(paragraph_repetition_validator(paragraphs))
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
    }
