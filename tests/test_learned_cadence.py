from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_cadence import (
    build_learned_cadence_summary,
    build_learned_cadence_track_detail,
)
from src.narrativeos.eval.learned_promotion_workflow import (
    build_evaluator_promotion_workflow_summary,
    save_evaluator_promotion_decision,
)
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.eval.learned_rollout import activate_learned_rollout
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService
from tests.test_learned_reranker_baseline import _seed_reranker_world


def _seed_cadence_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_cadence.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    evaluator_artifact_dir = tmp_path / "evaluator_artifacts"
    reranker_artifact_dir = tmp_path / "reranker_artifacts"
    return repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir


def test_learned_cadence_summary_collects_data_when_examples_missing(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_cadence_empty.db"))
    summary = build_learned_cadence_summary(
        repository=repository,
        evaluator_artifact_dir=tmp_path / "missing_eval",
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )

    stages = {item["track"]: item["cadence_stage"] for item in summary["track_summaries"]}
    assert stages == {"evaluator": "collect_data", "reranker": "collect_data"}
    assert summary["cadence_summary"]["training_queue"] == []
    assert summary["cadence_summary"]["collection_queue"] == ["evaluator", "reranker"]


def test_learned_cadence_progresses_from_training_to_promotion_to_active(tmp_path: Path):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_cadence_artifacts(tmp_path)

    before_training = build_learned_cadence_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    assert before_training["track_summaries"][0]["cadence_stage"] in {"train_candidate", "collect_data"}
    assert before_training["track_summaries"][1]["cadence_stage"] in {"train_candidate", "collect_data"}

    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_version_id=world_version_id,
    )
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )

    after_training = build_learned_cadence_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    evaluator_after_training = next(item for item in after_training["track_summaries"] if item["track"] == "evaluator")
    assert evaluator_after_training["cadence_stage"] in {"validate_shadow", "request_promotion"}
    assert evaluator_after_training["promotion_summary"]["approval_status"] == "unapproved"

    workflow = build_evaluator_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_evaluator_promotion_decision(
        repository=repository,
        reviewer_id="ops_promoter",
        reason="允许 evaluator 进入下一阶段。",
        status="approved",
        recommendation_summary=workflow,
    )
    after_approval = build_learned_cadence_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    evaluator_after_approval = next(item for item in after_approval["track_summaries"] if item["track"] == "evaluator")
    assert evaluator_after_approval["cadence_stage"] in {"validate_shadow", "ready_to_activate"}

    activate_learned_rollout(
        repository=repository,
        track="evaluator",
        reviewer_id="ops_promoter",
        reason="启动 evaluator 灰度。",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    after_activate = build_learned_cadence_track_detail(
        repository=repository,
        track="evaluator",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    assert after_activate["track_summary"]["cadence_stage"] == "monitor_active"
    assert after_activate["track_summary"]["rollout_summary"]["rollout_status"] == "active"


def test_learned_cadence_endpoints_return_summary_and_track_detail(tmp_path: Path, monkeypatch):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_cadence_artifacts(tmp_path)
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_version_id=world_version_id,
    )
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )

    import src.narrativeos.eval.learned_cadence as learned_cadence_module

    monkeypatch.setattr(
        learned_cadence_module,
        "default_learned_evaluator_artifact_dir",
        lambda _base_dir: evaluator_artifact_dir,
    )
    monkeypatch.setattr(
        learned_cadence_module,
        "default_learned_reranker_artifact_dir",
        lambda _base_dir: reranker_artifact_dir,
    )

    client = TestClient(create_app(repository=repository))
    summary = client.get("/v1/ops/learned-cadence", params={"world_version_id": world_version_id, "limit": 5})
    detail = client.get("/v1/ops/learned-cadence/evaluator", params={"world_version_id": world_version_id, "limit": 5})

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert summary.json()["cadence_summary"]["recommended_next_action"]
    assert {item["track"] for item in summary.json()["track_summaries"]} == {"evaluator", "reranker"}
    assert detail.json()["track"] == "evaluator"
    assert "track_summary" in detail.json()


def test_learned_cadence_surfaces_stale_reasons_and_recent_events(tmp_path: Path):
    repository, world_version_id, evaluator_artifact_dir, reranker_artifact_dir = _seed_cadence_artifacts(tmp_path)
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_version_id=world_version_id,
    )
    TrainingSignalService(repository).save_review_sample(
        {
            "chapter_id": "cadence_new_sample",
            "world_id": "urban_mystery_lotus_lane",
            "world_version_id": world_version_id,
            "reviewer_id": "ops_reviewer",
            "score_overall": 0.68,
            "issue_codes": ["Q04"],
            "linked_issue_codes": ["Q04"],
            "freeform_notes": "new sample after training",
            "would_continue": True,
            "would_pay": False,
        }
    )

    detail = build_learned_cadence_track_detail(
        repository=repository,
        track="evaluator",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    track_summary = detail["track_summary"]

    assert track_summary["freshness"]["data_newer_than_artifact"] is True
    assert "artifact_stale_vs_samples" in track_summary["stale_reasons"]
    assert track_summary["checkpoint_summary"]["split_status"] in {"ready", "validation_incomplete", "train_empty"}
    assert track_summary["recent_events"]
