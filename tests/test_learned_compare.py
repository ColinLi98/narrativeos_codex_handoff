from typing import Optional

from src.narrativeos.eval.learned_compare import build_learned_compare_from_dashboard


def _dashboard_summary(
    *,
    evaluator_status: str,
    reranker_status: str,
    evaluator_agreement: Optional[float],
    reranker_accuracy: Optional[float],
):
    return {
        "generated_at": "2026-04-01T10:00:00+00:00",
        "filters": {},
        "warnings": [],
        "shared_weak_worlds": ["urban_mystery_lotus_lane"] if evaluator_status != "candidate" and reranker_status != "candidate" else [],
        "shared_weak_issue_codes": ["Q04"] if evaluator_status != "candidate" and reranker_status != "candidate" else [],
        "evaluator_shadow_summary": {
            "status": evaluator_status,
            "agreement_rate": evaluator_agreement,
            "train_count": 8,
            "val_count": 3,
            "test_count": 3,
            "warnings": [],
        },
        "reranker_shadow_summary": {
            "status": reranker_status,
            "per_world_accuracy": {"urban_mystery_lotus_lane": reranker_accuracy} if reranker_accuracy is not None else {},
            "train_count": 8,
            "val_count": 3,
            "test_count": 3,
            "warnings": [],
        },
        "world_details": [
            {
                "world_id": "urban_mystery_lotus_lane",
                "evaluator_artifact_available": True,
                "reranker_artifact_available": True,
                "evaluator_agreement_rate": evaluator_agreement,
                "reranker_accuracy": reranker_accuracy,
                "evaluator_low_coverage": False,
                "reranker_low_coverage": False,
                "evaluator_top_issues": ["Q04"],
                "reranker_top_issues": ["Q04"],
                "recommended_action": "inspect_top_mismatches",
            }
        ],
        "issue_details": [
            {
                "issue_code": "Q04",
                "evaluator_error_rate": 0.35 if evaluator_agreement is not None and evaluator_agreement < 0.8 else 0.05,
                "reranker_error_rate": 0.35 if reranker_accuracy is not None and reranker_accuracy < 0.75 else 0.05,
                "affected_worlds": ["urban_mystery_lotus_lane"],
                "recommended_action": "world_or_issue_drilldown_required",
            }
        ],
    }


def test_compare_prefers_evaluator_when_evaluator_is_candidate_and_reranker_is_not():
    summary = _dashboard_summary(
        evaluator_status="candidate",
        reranker_status="warming_up",
        evaluator_agreement=0.91,
        reranker_accuracy=0.62,
    )
    compare = build_learned_compare_from_dashboard(summary)
    assert compare["preferred_shadow_candidate"] == "evaluator"
    assert compare["recommended_next_action"] == "advance_evaluator_shadow_candidate"
    assert compare["rollout_readiness"]["evaluator"]["candidate_ready"] is True
    assert compare["disagreement_worlds"][0]["world_id"] == "urban_mystery_lotus_lane"


def test_compare_prefers_reranker_when_reranker_is_candidate_and_evaluator_is_not():
    summary = _dashboard_summary(
        evaluator_status="not_ready",
        reranker_status="candidate",
        evaluator_agreement=0.63,
        reranker_accuracy=0.88,
    )
    compare = build_learned_compare_from_dashboard(summary)
    assert compare["preferred_shadow_candidate"] == "reranker"
    assert compare["recommended_next_action"] == "advance_reranker_shadow_candidate"
    assert compare["rollout_readiness"]["reranker"]["candidate_ready"] is True
    assert compare["disagreement_issue_codes"][0]["issue_code"] == "Q04"


def test_compare_returns_neither_when_both_tracks_are_not_ready():
    summary = _dashboard_summary(
        evaluator_status="warming_up",
        reranker_status="not_ready",
        evaluator_agreement=0.61,
        reranker_accuracy=0.52,
    )
    compare = build_learned_compare_from_dashboard(summary)
    assert compare["preferred_shadow_candidate"] == "neither"
    assert compare["recommended_next_action"] == "expand_review_and_pair_data"
    assert compare["safe_rollout_candidates"] == []
    assert compare["shared_weak_worlds"] == ["urban_mystery_lotus_lane"]
