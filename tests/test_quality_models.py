from src.narrativeos.quality.models import (
    ContentQualityScore,
    GuardrailDecision,
    QualityFeedbackItem,
    QualityEvent,
    QualityPolicy,
    QualityRule,
    ReviewCase,
)


def test_quality_domain_objects_round_trip():
    policy = QualityPolicy.from_dict(
        {
            "policy_id": "qp_reader_continue_v1",
            "version": "v1",
            "scenario_id": "reader_continue",
            "risk_tier": "L2",
            "rule_ids": ["chapter_quality_gate"],
            "mode": "observe",
            "metadata": {"surface": "reader"},
        }
    )
    rule = QualityRule.from_dict(
        {
            "rule_id": "chapter_quality_gate",
            "rule_type": "evaluator",
            "severity": "high",
            "blocking": True,
            "config_ref": "src.narrativeos.eval.service:evaluate_persisted_chapter",
            "reason_code": "chapter_quality_guard_failed",
        }
    )
    decision = GuardrailDecision.from_dict(
        {
            "trace_id": "trace_1",
            "status": "review_required",
            "scenario_id": "reader_continue",
            "risk_tier": "L2",
            "rule_hits": [{"rule_id": "chapter_quality_gate"}],
            "scores_ref": "score_1",
            "grounding_result": {"status": "not_evaluated"},
            "review_required": True,
            "review_case_id": "review_case_1",
        }
    )
    score = ContentQualityScore.from_dict(
        {
            "score_id": "score_1",
            "rubric_version": "content_quality_rubric_v1",
            "overall_score": 3.6,
            "dimension_scores": {"readability": 4, "executability": 3},
            "veto": False,
            "reason_codes": ["Q05"],
            "evidence_refs": [{"kind": "evaluation_report", "ref_id": "chapter_1"}],
        }
    )
    review_case = ReviewCase.from_dict(
        {
            "case_id": "review_case_1",
            "case_type": "runtime_quality",
            "status": "open",
            "owner_id": None,
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "reason_codes": ["chapter_quality_guard_failed"],
            "evidence_refs": [{"kind": "quality_event", "ref_id": "event_1"}],
        }
    )
    event = QualityEvent.from_dict(
        {
            "event_id": "event_1",
            "trace_id": "trace_1",
            "event_type": "guardrail_decision",
            "source_surface": "reader",
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "payload": {"status": "review_required"},
            "created_at": "2026-04-13T12:00:00+00:00",
        }
    )
    feedback = QualityFeedbackItem.from_dict(
        {
            "feedback_item_id": "feedback_1",
            "trace_id": "trace_1",
            "source_event_id": "analytics_1",
            "feedback_type": "retry_after_quality_guard",
            "signal": "retry",
            "source_surface": "reader",
            "account_id": "acct_1",
            "world_version_id": "jade_court_exam@0.1.0",
            "session_id": "session_1",
            "chapter_id": "chapter_1",
            "source_ref": {"kind": "session", "session_id": "session_1"},
            "payload": {"result_status": "ok"},
            "created_at": "2026-04-14T10:00:00+00:00",
        }
    )

    assert QualityPolicy.from_dict(policy.to_dict()) == policy
    assert QualityRule.from_dict(rule.to_dict()) == rule
    assert GuardrailDecision.from_dict(decision.to_dict()) == decision
    assert ContentQualityScore.from_dict(score.to_dict()) == score
    assert ReviewCase.from_dict(review_case.to_dict()) == review_case
    assert QualityEvent.from_dict(event.to_dict()) == event
    assert QualityFeedbackItem.from_dict(feedback.to_dict()) == feedback


def test_quality_domain_objects_validate_enums():
    try:
        QualityRule.from_dict(
            {
                "rule_id": "rule_1",
                "rule_type": "bad_type",
                "severity": "high",
                "blocking": True,
                "config_ref": "config",
                "reason_code": "bad",
            }
        )
    except ValueError as exc:
        assert "quality_rule_type_invalid" in str(exc)
    else:
        raise AssertionError("invalid rule_type should raise")

    try:
        GuardrailDecision.from_dict(
            {
                "trace_id": "trace_1",
                "status": "unexpected",
                "scenario_id": "reader_continue",
                "risk_tier": "L2",
                "rule_hits": [],
            }
        )
    except ValueError as exc:
        assert "guardrail_status_invalid" in str(exc)
    else:
        raise AssertionError("invalid guardrail status should raise")
