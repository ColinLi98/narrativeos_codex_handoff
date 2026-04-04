from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Sequence

from ..models import EvaluationIssue, EvaluationReport, EvaluationScores
from .gating import decide_evaluation
from .taxonomy import ISSUE_TAXONOMY


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_issues(issues: Sequence[EvaluationIssue]) -> str:
    if not issues:
        return "该章节通过当前 NarrativeEval 守卫。"
    return "；".join("%s %s" % (issue.issue_code, issue.summary) for issue in issues[:4])


def build_evaluation_report(
    *,
    chapter_id: str,
    world_version_id: str,
    session_id: str,
    issues: Sequence[EvaluationIssue],
    scores: EvaluationScores,
    hard_validator_results: Dict[str, object],
) -> EvaluationReport:
    decision = decide_evaluation(
        hard_failed=bool(hard_validator_results.get("failed")),
        issues=issues,
        scores=scores,
    )
    return EvaluationReport(
        chapter_id=chapter_id,
        world_version_id=world_version_id,
        session_id=session_id,
        decision=decision,
        issues=list(issues),
        scores=scores,
        hard_validator_results=dict(hard_validator_results),
        summary=summarize_issues(issues),
        created_at=_utcnow(),
    )


def aggregate_reports(reports: Iterable[EvaluationReport]) -> Dict[str, object]:
    report_list = list(reports)
    if not report_list:
        return {
            "pass_rate": 0.0,
            "rewrite_rate": 0.0,
            "block_rate": 0.0,
            "top_issue_categories": [],
        }
    total = float(len(report_list))
    pass_count = sum(1 for report in report_list if report.decision.decision == "pass")
    rewrite_count = sum(1 for report in report_list if report.decision.decision == "rewrite")
    block_count = sum(1 for report in report_list if report.decision.decision == "block")
    issue_counter: Dict[str, int] = {}
    for report in report_list:
        for issue in report.issues:
            issue_counter[issue.issue_code] = issue_counter.get(issue.issue_code, 0) + 1
    top_issues = sorted(issue_counter.items(), key=lambda item: (-item[1], item[0]))
    next_actions = [
        {
            "issue_code": code,
            "owning_module": ISSUE_TAXONOMY.get(code, {}).get("owning_module", ""),
            "fix_hint": ISSUE_TAXONOMY.get(code, {}).get("fix_hint", ""),
        }
        for code, _count in top_issues[:3]
    ]
    return {
        "pass_rate": pass_count / total,
        "rewrite_rate": rewrite_count / total,
        "block_rate": block_count / total,
        "top_issue_categories": [
            {
                "issue_code": code,
                "count": count,
                "owning_module": ISSUE_TAXONOMY.get(code, {}).get("owning_module", ""),
                "fix_hint": ISSUE_TAXONOMY.get(code, {}).get("fix_hint", ""),
            }
            for code, count in top_issues[:5]
        ],
        "next_actions": next_actions,
    }
