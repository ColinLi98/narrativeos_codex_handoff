from src.narrativeos.eval.gating import decide_evaluation
from src.narrativeos.eval.taxonomy import ISSUE_TAXONOMY
from src.narrativeos.models import EvaluationIssue, EvaluationScores


def test_issue_taxonomy_and_owning_modules_are_complete():
    assert set(ISSUE_TAXONOMY.keys()) == {"Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10"}
    assert ISSUE_TAXONOMY["Q01"]["owning_module"] == "linter"
    assert ISSUE_TAXONOMY["Q10"]["owning_module"] == "reader_ui"


def test_gating_decision_rules():
    scores = EvaluationScores(
        readability=0.9,
        scene_density=0.9,
        character_fidelity=0.9,
        causal_continuity=0.9,
        pacing=0.9,
        choice_distinctness=0.8,
        hook_quality=0.8,
        monetize_ready=0.8,
        overall_score=0.8,
    )
    decision = decide_evaluation(hard_failed=False, issues=[], scores=scores)
    assert decision.decision == "pass"

    rewrite = decide_evaluation(
        hard_failed=False,
        issues=[
            EvaluationIssue("Q03", "medium", "重复", "writer"),
            EvaluationIssue("Q04", "medium", "解释过多", "writer"),
        ],
        scores=EvaluationScores.from_dict({**scores.to_dict(), "overall_score": 0.68}),
    )
    assert rewrite.decision == "rewrite"

    block = decide_evaluation(
        hard_failed=True,
        issues=[EvaluationIssue("Q01", "high", "工程泄漏", "linter")],
        scores=scores,
    )
    assert block.decision == "block"
