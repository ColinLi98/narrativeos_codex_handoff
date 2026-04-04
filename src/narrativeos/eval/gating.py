from __future__ import annotations

from typing import Sequence

from ..models import EvaluationDecision, EvaluationIssue, EvaluationScores


PASS_THRESHOLD = 0.72


def decide_evaluation(
    *,
    hard_failed: bool,
    issues: Sequence[EvaluationIssue],
    scores: EvaluationScores,
) -> EvaluationDecision:
    if hard_failed:
        return EvaluationDecision(decision="block", reason="hard_validator_failed")
    severe = [issue for issue in issues if issue.severity == "high"]
    medium = [issue for issue in issues if issue.severity == "medium"]
    if any(issue.issue_code in {"Q01", "Q02", "Q07", "Q09", "Q10"} for issue in severe):
        return EvaluationDecision(decision="block", reason="high_severity_issue")
    if scores.overall_score < PASS_THRESHOLD or len(medium) >= 2:
        return EvaluationDecision(decision="rewrite", reason="quality_below_threshold")
    return EvaluationDecision(decision="pass", reason="quality_threshold_met")
