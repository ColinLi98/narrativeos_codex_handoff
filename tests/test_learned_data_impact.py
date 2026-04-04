from src.narrativeos.eval.learned_data_impact import build_learned_data_impact_receipt


def test_learned_data_impact_receipt_tracks_before_after_counts_and_actions():
    before_summary = {
        "preferred_shadow_candidate": "neither",
        "recommended_next_action": "expand_review_and_pair_data",
        "review_sample_backlog": [{"chapter_id": "chapter_1"}],
        "pair_coverage_backlog": [{"issue_code": "Q04"}],
        "action_queue": [{"action_type": "review_sample"}],
        "warnings": ["missing_human_review_coverage"],
    }
    after_summary = {
        "preferred_shadow_candidate": "evaluator",
        "recommended_next_action": "advance_evaluator_shadow_candidate",
        "review_sample_backlog": [],
        "pair_coverage_backlog": [{"issue_code": "Q04"}],
        "action_queue": [],
        "warnings": [],
    }
    review_sample = {
        "sample_id": "sample_1",
        "chapter_id": "chapter_1",
        "world_id": "jade_court_romance",
        "world_version_id": "jade_court_romance@0.3.0",
    }

    receipt = build_learned_data_impact_receipt(
        before_summary=before_summary,
        after_summary=after_summary,
        review_sample=review_sample,
    )

    assert receipt["preferred_shadow_candidate_before"] == "neither"
    assert receipt["preferred_shadow_candidate_after"] == "evaluator"
    assert receipt["recommended_next_action_before"] == "expand_review_and_pair_data"
    assert receipt["recommended_next_action_after"] == "advance_evaluator_shadow_candidate"
    assert receipt["review_backlog_count_before"] == 1
    assert receipt["review_backlog_count_after"] == 0
    assert receipt["pair_backlog_count_before"] == 1
    assert receipt["pair_backlog_count_after"] == 1
    assert receipt["action_queue_count_before"] == 1
    assert receipt["action_queue_count_after"] == 0
    assert receipt["cleared_backlog_target"] is True


def test_learned_data_impact_receipt_handles_no_delta_case():
    summary = {
        "preferred_shadow_candidate": "neither",
        "recommended_next_action": "expand_review_and_pair_data",
        "review_sample_backlog": [],
        "pair_coverage_backlog": [],
        "action_queue": [],
        "warnings": ["artifact_missing"],
    }
    review_sample = {
        "sample_id": "sample_2",
        "chapter_id": "chapter_2",
        "world_id": "jade_court_exam",
        "world_version_id": "jade_court_exam@0.1.0",
    }

    receipt = build_learned_data_impact_receipt(
        before_summary=summary,
        after_summary=summary,
        review_sample=review_sample,
    )

    assert receipt["review_backlog_count_before"] == receipt["review_backlog_count_after"] == 0
    assert receipt["pair_backlog_count_before"] == receipt["pair_backlog_count_after"] == 0
    assert receipt["action_queue_count_before"] == receipt["action_queue_count_after"] == 0
    assert receipt["cleared_backlog_target"] is False
