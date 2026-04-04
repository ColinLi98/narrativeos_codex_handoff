from __future__ import annotations

from typing import Iterable, List, Sequence

from ..models import EvaluationIssue, EvaluationScores, NarrativeState, SceneBeat
from ..repetition_detector import repetition_score
from .taxonomy import ISSUE_TAXONOMY


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


CHOICE_STOP_CHARS = set("的一了是不再会把着也就都还要先去与和给到过来个这那将能得在里上让后会吗呢吧啊")


def readability(text: str) -> float:
    if not text:
        return 0.0
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    avg_paragraph = len(text) / float(max(1, len(paragraphs)))
    sentence_count = max(1, text.count("。") + text.count("！") + text.count("？"))
    avg_sentence = len(text) / float(sentence_count)
    paragraph_score = 1.0 - abs(avg_paragraph - 220.0) / 360.0
    sentence_score = 1.0 - abs(avg_sentence - 38.0) / 60.0
    return _clamp(0.55 * paragraph_score + 0.45 * sentence_score)


def scene_density(dialogue_count: int, action_count: int, detail_count: int, body: str) -> float:
    if not body:
        return 0.0
    ratio = (dialogue_count * 26 + action_count * 12 + detail_count * 14) / float(max(1, len(body)))
    return _clamp(ratio * 7.2)


def character_fidelity(existing_score: float) -> float:
    if existing_score <= 0.0:
        return 0.0
    return _clamp(0.28 + existing_score * 3.4)


def causal_continuity(issues: Sequence[EvaluationIssue]) -> float:
    if any(issue.issue_code == "Q07" for issue in issues):
        return 0.25
    return 0.88


def pacing(ending_ready: bool, state_after: NarrativeState, repetition: float) -> float:
    score = 0.82 - repetition
    if len(state_after.open_promises) == 0 and not ending_ready and state_after.chapter_index < state_after.min_end_turn:
        score -= 0.18
    if ending_ready and state_after.chapter_index < state_after.min_end_turn:
        score -= 0.45
    return _clamp(score)


def choice_distinctness(choices: Sequence[str]) -> float:
    if not choices:
        return 0.0
    normalized = [choice.strip() for choice in choices if choice.strip()]
    unique = len(set(normalized))
    if unique <= 1:
        return 0.2
    pair_scores: List[float] = []
    for index, left in enumerate(normalized):
        left_tokens = {char for char in left if char not in CHOICE_STOP_CHARS and char.strip()}
        for right in normalized[index + 1 :]:
            right_tokens = {char for char in right if char not in CHOICE_STOP_CHARS and char.strip()}
            overlap = len(left_tokens & right_tokens) / float(max(1, len(left_tokens | right_tokens)))
            prefix_penalty = 0.15 if left[:6] == right[:6] else 0.0
            pair_scores.append(max(0.0, 1.0 - overlap - prefix_penalty))
    if not pair_scores:
        return 0.3
    return _clamp(sum(pair_scores) / float(len(pair_scores)))


def hook_quality(body: str) -> float:
    if not body:
        return 0.0
    tail = body.split("\n\n")[-1]
    if any(token in tail for token in ["总结", "完成", "这一章", "从这里起", "放远一点看"]):
        return 0.22
    if any(token in tail for token in ["下一次", "还会", "还没", "追上来", "没有散", "未说尽"]):
        return 0.9
    return 0.45


def monetize_ready(choice_score: float, body: str, paywall_required: bool) -> float:
    base = 0.58 if len(body) >= 650 else 0.32
    if paywall_required:
        base += 0.08
    base += 0.22 * choice_score
    return _clamp(base)


def derive_scoring_issues(
    *,
    scores: EvaluationScores,
    exposition_ratio: float,
    concrete_detail_density: float,
    ending_ready: bool,
    state_after: NarrativeState,
) -> List[EvaluationIssue]:
    issues: List[EvaluationIssue] = []
    if exposition_ratio > 0.44:
        issues.append(
            EvaluationIssue(
                issue_code="Q04",
                severity="medium",
                summary="解释句比例偏高，场面推进感不足。",
                owning_module=ISSUE_TAXONOMY["Q04"]["owning_module"],
                evidence=["exposition_ratio=%.3f" % exposition_ratio],
            )
        )
    if scores.scene_density < 0.42 or concrete_detail_density < (1.0 / 180.0):
        issues.append(
            EvaluationIssue(
                issue_code="Q05",
                severity="medium",
                summary="场景细节和动作密度不足，读感更像摘要而不是场景。",
                owning_module=ISSUE_TAXONOMY["Q05"]["owning_module"],
                evidence=[
                    "scene_density=%.3f" % scores.scene_density,
                    "detail_density=%.4f" % concrete_detail_density,
                ],
            )
        )
    if scores.choice_distinctness < 0.48:
        issues.append(
            EvaluationIssue(
                issue_code="Q08",
                severity="medium",
                summary="选项之间的差异度不足，下一步选择的命运感不够明确。",
                owning_module=ISSUE_TAXONOMY["Q08"]["owning_module"],
                evidence=["choice_distinctness=%.3f" % scores.choice_distinctness],
            )
        )
    if scores.pacing < 0.45 or scores.hook_quality < 0.45 or (ending_ready and state_after.chapter_index < state_after.min_end_turn):
        severity = "high" if ending_ready and state_after.chapter_index < state_after.min_end_turn else "medium"
        issues.append(
            EvaluationIssue(
                issue_code="Q09",
                severity=severity,
                summary="章节节奏或结尾钩子不足，容易削弱继续阅读动力。",
                owning_module=ISSUE_TAXONOMY["Q09"]["owning_module"],
                evidence=[
                    "pacing=%.3f" % scores.pacing,
                    "hook_quality=%.3f" % scores.hook_quality,
                    "chapter_index=%s" % state_after.chapter_index,
                ],
            )
        )
    if scores.character_fidelity < 0.34:
        issues.append(
            EvaluationIssue(
                issue_code="Q06",
                severity="medium",
                summary="角色说话和行动的拉力还不够贴近当前人物状态。",
                owning_module=ISSUE_TAXONOMY["Q06"]["owning_module"],
                evidence=["character_fidelity=%.3f" % scores.character_fidelity],
            )
        )
    if scores.causal_continuity < 0.4:
        issues.append(
            EvaluationIssue(
                issue_code="Q07",
                severity="high",
                summary="当前章节与既有因果链衔接不足。",
                owning_module=ISSUE_TAXONOMY["Q07"]["owning_module"],
                evidence=["causal_continuity=%.3f" % scores.causal_continuity],
            )
        )
    return issues


def score_chapter(
    *,
    body: str,
    dialogue_count: int,
    action_count: int,
    detail_count: int,
    character_fidelity_score: float,
    issues: Sequence[EvaluationIssue],
    state_after: NarrativeState,
    ending_ready: bool,
    choices: Sequence[str],
    paywall_required: bool,
) -> EvaluationScores:
    repetition = repetition_score(body.split("\n\n"))
    readability_score = readability(body)
    scene_density_score = scene_density(dialogue_count, action_count, detail_count, body)
    fidelity_score = character_fidelity(character_fidelity_score)
    continuity_score = causal_continuity(issues)
    pacing_score = pacing(ending_ready, state_after, repetition)
    choice_score = choice_distinctness(choices)
    hook_score = hook_quality(body)
    monetize_score = monetize_ready(choice_score, body, paywall_required)
    overall = (
        readability_score * 0.14
        + scene_density_score * 0.14
        + fidelity_score * 0.16
        + continuity_score * 0.15
        + pacing_score * 0.13
        + choice_score * 0.10
        + hook_score * 0.10
        + monetize_score * 0.08
    )
    return EvaluationScores(
        readability=readability_score,
        scene_density=scene_density_score,
        character_fidelity=fidelity_score,
        causal_continuity=continuity_score,
        pacing=pacing_score,
        choice_distinctness=choice_score,
        hook_quality=hook_score,
        monetize_ready=monetize_score,
        overall_score=_clamp(overall),
    )
