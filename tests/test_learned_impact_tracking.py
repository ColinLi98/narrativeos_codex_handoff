from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_assisted_gate import evaluate_assisted_gate_decision, save_assisted_gate_config
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_impact import build_learned_impact_summary
from src.narrativeos.eval.learned_promotion_workflow import (
    build_evaluator_promotion_workflow_summary,
    save_evaluator_promotion_decision,
)
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.eval.learned_reranker_promotion_workflow import build_reranker_promotion_workflow_summary
from src.narrativeos.eval.learned_rollout import activate_learned_rollout
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from tests.test_eval_metrics_correlation import _seed_reader_chapter
from tests.test_learned_reranker_baseline import _seed_reranker_world


class _AlwaysBlockInference:
    def availability(self):
        return {"available": True}

    def predict_example(self, _example):
        return {"available": True, "predicted_decision": "block", "confidence": 0.99}


def _seed_learned_impact_context(tmp_path: Path) -> tuple[SQLAlchemyRepository, str, Path, Path]:
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_impact.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    runtime = repository.get_runtime_bundle(world_version_id)
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=48)).isoformat()
    session_record = repository.create_session_record(
        world_version_id=world_version_id,
        initial_state=runtime.initial_state,
        reader_id="reader_impact",
        session_id="session_impact",
        entitlements_snapshot={},
    )
    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=runtime.worldpack.world_id,
        world_version_id=world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=1,
        overall_score=0.92,
        created_at=old_time,
    )
    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=runtime.worldpack.world_id,
        world_version_id=world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=2,
        overall_score=0.24,
        created_at=old_time,
    )
    with repository.SessionLocal() as session:
        row = session.get(SessionRow, session_record.session_id)
        assert row is not None
        row.updated_at = old_time
        session.commit()

    analytics = AnalyticsService(repository)
    world_id = runtime.worldpack.world_id
    common_payload = {
        "reader_id": "reader_impact",
        "account_id": "reader_impact",
        "session_id": session_record.session_id,
        "world_id": world_id,
        "world_version_id": world_version_id,
    }
    analytics.track("payment_required", payload_json={"reason": "subscription_required"}, **common_payload)
    analytics.track("checkout_started", access_tier="play_pass", payload_json={"tier_id": "play_pass"}, **common_payload)
    analytics.track("subscription_activated", access_tier="play_pass", payload_json={"tier_id": "play_pass"}, **common_payload)
    analytics.track("subscription_state_changed", access_tier="play_pass", payload_json={"status": "active"}, **common_payload)
    analytics.track("story_credits_consumed", access_tier="play_pass", payload_json={"balance": 2}, **common_payload)
    analytics.track("studio_credits_consumed", access_tier="creator_pass", payload_json={"balance": 5}, **common_payload)
    analytics.track("entitlement_granted", access_tier="play_pass", payload_json={"tier_id": "play_pass"}, **common_payload)

    evaluator_artifact_dir = tmp_path / "evaluator_artifacts"
    reranker_artifact_dir = tmp_path / "reranker_artifacts"
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_id=world_id,
    )
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )
    return repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir


def _seed_assisted_gate_receipt(
    repository: SQLAlchemyRepository,
    *,
    world_version_id: str,
    evaluator_artifact_dir: Path,
    reranker_artifact_dir: Path,
) -> None:
    workflow = build_evaluator_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_evaluator_promotion_decision(
        repository=repository,
        reviewer_id="ops_promoter",
        reason="impact tracking test approval",
        status="approved",
        recommendation_summary=workflow,
    )
    activate_learned_rollout(
        repository=repository,
        track="evaluator",
        reviewer_id="ops_promoter",
        reason="impact tracking rollout",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_assisted_gate_config(
        repository=repository,
        reviewer_id="ops_web",
        reason="impact tracking experiment",
        enabled=True,
        mode="assisted_gate",
        bucket_percentage=100,
        confidence_threshold=0.9,
        min_example_count=2,
        min_high_confidence_blocks=2,
        required_block_share=0.5,
        world_allowlist=[],
    )
    evaluate_assisted_gate_decision(
        repository=repository,
        world_version_id=world_version_id,
        simulation=repository.get_world_version(world_version_id).simulation_report_json,
        rule_gate_errors=[],
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
        learned_inference_service=_AlwaysBlockInference(),
        persist_receipt=True,
    )


def test_learned_impact_summary_reports_insufficient_data_without_samples(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_impact_empty.db"))
    summary = build_learned_impact_summary(repository=repository)

    assert {item["track"] for item in summary["track_summaries"]} == {"evaluator", "reranker"}
    assert all(item["impact_status"] == "insufficient_data" for item in summary["track_summaries"])
    assert summary["retention_proxies"]["continuation_signal_summary"]["sample_count"] == 0
    assert summary["monetization_proxies"]["sample_count"] == 0
    assert summary["experiment_summaries"]["assisted_gate"]["impact_status"] == "insufficient_data"
    assert "insufficient_monetization_proxy_samples" in summary["warnings"]


def test_learned_impact_summary_separates_retention_and_monetization_proxies(tmp_path: Path):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_learned_impact_context(tmp_path)
    _seed_assisted_gate_receipt(
        repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    summary = build_learned_impact_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    assert {item["track"] for item in summary["track_summaries"]} == {"evaluator", "reranker"}
    evaluator = next(item for item in summary["track_summaries"] if item["track"] == "evaluator")
    reranker = next(item for item in summary["track_summaries"] if item["track"] == "reranker")
    assert evaluator["sample_count"] >= 1
    assert reranker["sample_count"] >= 1
    assert summary["retention_proxies"]["continuation_signal_summary"]["sample_count"] >= 2
    assert summary["monetization_proxies"]["payment_required_count"] >= 1
    assert summary["monetization_proxies"]["checkout_started_count"] >= 1
    assert summary["monetization_proxies"]["subscription_activated_count"] >= 1
    assert summary["monetization_proxies"]["story_credit_consumed_count"] >= 1
    assert summary["monetization_proxies"]["studio_credit_consumed_count"] >= 1
    assert "retention" in summary["quality_correlations"]
    assert "monetization" in summary["quality_correlations"]
    assert "experiments" in summary["quality_correlations"]
    assert summary["experiment_summaries"]["assisted_gate"]["decision_count"] >= 1
    assert summary["retention_proxies"]["assisted_gate_experiment"]["decision_count"] >= 1
    assert summary["monetization_proxies"]["assisted_gate_experiment"]["decision_count"] >= 1
    assert summary["world_impact_details"][0]["assisted_gate_decision_count"] >= 1
    assert summary["world_impact_details"]
    assert summary["issue_impact_details"]


def test_learned_impact_does_not_change_promotion_workflow_status(tmp_path: Path):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_learned_impact_context(tmp_path)

    evaluator_before = build_evaluator_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    reranker_before = build_reranker_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    _summary = build_learned_impact_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    evaluator_after = build_evaluator_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    reranker_after = build_reranker_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    assert evaluator_before["approval_status"] == evaluator_after["approval_status"]
    assert evaluator_before["status"] == evaluator_after["status"]
    assert reranker_before["approval_status"] == reranker_after["approval_status"]
    assert reranker_before["status"] == reranker_after["status"]


def test_learned_impact_endpoints_return_summary_and_drilldowns(tmp_path: Path, monkeypatch):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_learned_impact_context(tmp_path)
    app = create_app(repository=repository)
    client = TestClient(app)

    import src.narrativeos.eval.learned_dashboard as learned_dashboard_module

    monkeypatch.setattr(
        learned_dashboard_module,
        "default_learned_evaluator_artifact_dir",
        lambda _base_dir: evaluator_artifact_dir,
    )
    monkeypatch.setattr(
        learned_dashboard_module,
        "default_learned_reranker_artifact_dir",
        lambda _base_dir: reranker_artifact_dir,
    )

    summary = client.get("/v1/ops/learned-impact", params={"world_version_id": world_version_id, "limit": 5})
    world_detail = client.get("/v1/ops/learned-impact/worlds/urban_mystery_lotus_lane", params={"world_version_id": world_version_id})
    issue_detail = client.get("/v1/ops/learned-impact/issues/Q04", params={"world_version_id": world_version_id})

    assert summary.status_code == 200
    assert world_detail.status_code == 200
    assert issue_detail.status_code == 200
    assert summary.json()["track_summaries"]
    assert "retention_proxies" in summary.json()
    assert "monetization_proxies" in summary.json()
    assert world_detail.json()["world_id"] == "urban_mystery_lotus_lane"
    assert issue_detail.json()["issue_code"] == "Q04"
