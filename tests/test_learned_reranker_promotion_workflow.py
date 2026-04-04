from src.narrativeos.eval.learned_reranker_promotion_workflow import (
    build_reranker_promotion_workflow_from_recommendation,
    save_reranker_promotion_decision,
)
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.review import parse_review_notes


def _recommendation(status: str = "eligible"):
    return {
        "generated_at": "2026-04-01T00:00:00+00:00",
        "filters": {},
        "status": status,
        "recommended_action": "promote_reranker_shadow_candidate" if status == "eligible" else "clear_remaining_pair_backlog",
        "blockers": [] if status == "eligible" else ["shadow_status_warming_up"],
        "advisories": [] if status == "eligible" else ["pair_backlog_remaining"],
        "checklist": [],
        "evidence": {
            "average_world_accuracy": 0.86,
            "low_error_world_count": 3,
            "train_count": 8,
            "val_count": 4,
            "test_count": 4,
            "preferred_shadow_candidate": "reranker",
            "review_backlog_count": 0,
            "pair_backlog_count": 0 if status == "eligible" else 1,
            "disagreement_world_count": 0,
            "disagreement_issue_count": 0,
        },
    }


def test_reranker_promotion_workflow_unapproved_approved_stale_and_revoked_states():
    eligible = _recommendation("eligible")

    unapproved = build_reranker_promotion_workflow_from_recommendation(
        recommendation=eligible,
        latest_record=None,
    )
    assert unapproved["approval_status"] == "unapproved"

    approved = build_reranker_promotion_workflow_from_recommendation(
        recommendation=eligible,
        latest_record={"status": "approved", "reviewer_id": "ops_b"},
    )
    assert approved["approval_status"] == "approved"
    assert approved["recommended_action"] == "monitor_promoted_reranker"

    stale = build_reranker_promotion_workflow_from_recommendation(
        recommendation=_recommendation("watching"),
        latest_record={"status": "approved", "reviewer_id": "ops_b"},
    )
    assert stale["approval_status"] == "stale"
    assert stale["reconfirm_required"] is True
    assert stale["recommended_action"] == "reconfirm_reranker_promotion"

    revoked = build_reranker_promotion_workflow_from_recommendation(
        recommendation=eligible,
        latest_record={"status": "revoked", "reviewer_id": "ops_b"},
    )
    assert revoked["approval_status"] == "revoked"
    assert revoked["recommended_action"] == "rebuild_reranker_readiness"


def test_save_reranker_promotion_decision_reuses_review_records(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reranker_promotion_workflow.db"))
    record = save_reranker_promotion_decision(
        repository=repository,
        reviewer_id="ops_reviewer",
        reason="准入 reranker promotion。",
        status="approved",
        recommendation_summary=build_reranker_promotion_workflow_from_recommendation(
            recommendation=_recommendation("eligible"),
            latest_record=None,
        ),
    )
    assert record["asset_type"] == "learned_promotion"
    assert record["asset_id"] == "reranker"
    assert record["status"] == "approved"

    saved = repository.list_review_records(asset_type="learned_promotion", asset_id="reranker")[0]
    notes = parse_review_notes(saved["notes"])
    assert notes["track"] == "reranker"
    assert notes["scope"] == "global"
    assert notes["reviewer_id"] == "ops_reviewer"
    assert notes["reason"] == "准入 reranker promotion。"
