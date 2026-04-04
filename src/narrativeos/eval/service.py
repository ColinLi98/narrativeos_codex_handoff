from __future__ import annotations

from typing import Sequence

from ..core.linter import lint_chapter_draft
from ..models import EvaluationIssue, EvaluationReport, NarrativeState, SceneBeat
from .reporting import build_evaluation_report
from .scorers import derive_scoring_issues, score_chapter
from .validators import run_hard_validators


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
                "exposition_ratio": lint_report["exposition_ratio"],
                "dialogue_plus_action_ratio": lint_report["dialogue_plus_action_ratio"],
                "concrete_detail_density": lint_report["concrete_detail_density"],
            },
        },
    )
