from src.narrativeos.eval.learned_promotion import build_evaluator_promotion_from_summaries


def _summary_fixture(
    *,
    evaluator_status: str,
    preferred_shadow_candidate: str,
    warnings=None,
    review_backlog_count: int = 0,
    pair_backlog_count: int = 0,
    disagreement_world_count: int = 0,
    disagreement_issue_count: int = 0,
    shared_weak_worlds=None,
):
    warnings = list(warnings or [])
    shared_weak_worlds = list(shared_weak_worlds or [])
    dashboard_summary = {
        "generated_at": "2026-04-01T00:00:00+00:00",
        "filters": {},
        "evaluator_shadow_summary": {
            "artifact_present": True,
            "status": evaluator_status,
            "agreement_rate": 0.88,
            "train_count": 8,
            "val_count": 4,
            "test_count": 4,
            "warnings": warnings,
        },
    }
    compare_summary = {
        "preferred_shadow_candidate": preferred_shadow_candidate,
    }
    data_ops_summary = {
        "coverage_gaps": {
            "review_sample_backlog_count": review_backlog_count,
            "pair_coverage_backlog_count": pair_backlog_count,
            "disagreement_world_count": disagreement_world_count,
            "disagreement_issue_count": disagreement_issue_count,
            "shared_weak_worlds": shared_weak_worlds,
        },
    }
    return dashboard_summary, compare_summary, data_ops_summary


def test_evaluator_promotion_eligible_without_blockers_or_advisories():
    dashboard_summary, compare_summary, data_ops_summary = _summary_fixture(
        evaluator_status="candidate",
        preferred_shadow_candidate="evaluator",
    )
    summary = build_evaluator_promotion_from_summaries(
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
        data_ops_summary=data_ops_summary,
    )
    assert summary["status"] == "eligible"
    assert summary["recommended_action"] == "promote_evaluator_shadow_candidate"
    assert summary["blockers"] == []
    assert summary["advisories"] == []


def test_evaluator_promotion_watching_when_only_backlog_and_disagreement_remain():
    dashboard_summary, compare_summary, data_ops_summary = _summary_fixture(
        evaluator_status="candidate",
        preferred_shadow_candidate="evaluator",
        review_backlog_count=2,
        disagreement_issue_count=1,
        shared_weak_worlds=["jade_court_romance"],
    )
    summary = build_evaluator_promotion_from_summaries(
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
        data_ops_summary=data_ops_summary,
    )
    assert summary["status"] == "watching"
    assert summary["recommended_action"] == "clear_remaining_eval_backlog"
    assert "review_backlog_remaining" in summary["advisories"]
    assert "disagreement_issues_remaining" in summary["advisories"]
    assert "shared_weak_worlds_remaining" in summary["advisories"]


def test_evaluator_promotion_blocked_by_status_compare_and_critical_warning():
    dashboard_summary, compare_summary, data_ops_summary = _summary_fixture(
        evaluator_status="warming_up",
        preferred_shadow_candidate="neither",
        warnings=["single_class_train_fallback_dummy"],
    )
    summary = build_evaluator_promotion_from_summaries(
        dashboard_summary=dashboard_summary,
        compare_summary=compare_summary,
        data_ops_summary=data_ops_summary,
    )
    assert summary["status"] == "blocked"
    assert summary["recommended_action"] == "expand_eval_dataset"
    assert "shadow_status_warming_up" in summary["blockers"]
    assert "compare_prefers_neither" in summary["blockers"]
    assert "critical_warning::single_class_train_fallback_dummy" in summary["blockers"]
