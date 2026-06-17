from pathlib import Path

from src.narrativeos.repository import SQLAlchemyRepository


def test_quality_repository_round_trip_for_policies_events_scores_and_cases(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "quality_repository.db"))

    policy = repository.save_quality_policy(
        {
            "policy_id": "qp_reader_continue_v1",
            "version": "v1",
            "scenario_id": "reader_continue",
            "risk_tier": "L2",
            "mode": "observe",
            "rule_ids": ["chapter_quality_gate", "runtime_grounding_placeholder"],
            "policy_payload": {"source": "tests"},
        }
    )
    assert policy["policy_id"] == "qp_reader_continue_v1"
    assert repository.list_quality_policies(scenario_id="reader_continue")[0]["policy_id"] == "qp_reader_continue_v1"

    event = repository.save_quality_event(
        {
            "event_id": "quality_event_1",
            "trace_id": "trace_1",
            "event_type": "guardrail_decision",
            "source_surface": "reader",
            "status": "review_required",
            "world_version_id": "jade_court_exam@0.1.0",
            "session_id": "session_1",
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "payload": {"status": "review_required"},
        }
    )
    assert event["trace_id"] == "trace_1"
    assert repository.list_quality_events(trace_id="trace_1")[0]["event_id"] == "quality_event_1"

    score = repository.save_content_quality_score(
        {
            "score_id": "quality_score_1",
            "trace_id": "trace_1",
            "source_surface": "reader",
            "status": "review_required",
            "world_version_id": "jade_court_exam@0.1.0",
            "session_id": "session_1",
            "chapter_id": "chapter_session_1_1",
            "rubric_version": "content_quality_rubric_v1",
            "overall_score": 3.5,
            "veto": False,
            "dimension_scores": {"readability": 4, "executability": 3},
            "reason_codes": ["Q05"],
            "evidence_refs": [{"kind": "quality_event", "ref_id": "quality_event_1"}],
            "score_payload": {"source": "tests"},
        }
    )
    assert repository.get_content_quality_score("quality_score_1")["overall_score"] == 3.5
    assert repository.list_content_quality_scores(trace_id="trace_1")[0]["score_id"] == "quality_score_1"

    case = repository.save_review_case(
        {
            "case_id": "review_case_1",
            "trace_id": "trace_1",
            "case_type": "runtime_quality",
            "status": "open",
            "owner_id": None,
            "source_surface": "reader",
            "world_version_id": "jade_court_exam@0.1.0",
            "session_id": "session_1",
            "score_id": "quality_score_1",
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "reason_codes": ["chapter_quality_guard_failed"],
            "evidence_refs": [{"kind": "content_quality_score", "ref_id": "quality_score_1"}],
            "case_payload": {"source": "tests"},
        }
    )
    assert case["case_id"] == "review_case_1"
    updated = repository.update_review_case_status(
        "review_case_1",
        status="in_review",
        owner_id="ops_web",
        reason_codes=["chapter_quality_guard_failed", "quality_review_required"],
    )
    assert updated["status"] == "in_review"
    assert updated["owner_id"] == "ops_web"
    assert repository.get_review_case("review_case_1")["status"] == "in_review"
    assert repository.list_review_cases(trace_id="trace_1")[0]["case_id"] == "review_case_1"

    feedback = repository.save_quality_feedback_item(
        {
            "feedback_item_id": "quality_feedback_1",
            "trace_id": "trace_1",
            "source_event_id": "analytics_1",
            "feedback_type": "retry_after_quality_guard",
            "signal": "retry",
            "source_surface": "reader",
            "account_id": "acct_1",
            "world_version_id": "jade_court_exam@0.1.0",
            "session_id": "session_1",
            "chapter_id": "chapter_session_1_1",
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "payload": {"result_status": "ok"},
        }
    )
    assert feedback["feedback_item_id"] == "quality_feedback_1"
    assert repository.list_quality_feedback_items(trace_id="trace_1")[0]["signal"] == "retry"
