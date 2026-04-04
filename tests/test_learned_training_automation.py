from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_training_automation import (
    build_promotion_evidence_pack,
    run_learned_training_automation,
)
from src.narrativeos.repository import SQLAlchemyRepository
from tests.test_learned_reranker_baseline import _seed_reranker_world


def test_learned_training_automation_runs_tracks_and_writes_evidence(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_training_automation.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")

    output_dir = tmp_path / "automation_output"
    result = run_learned_training_automation(
        repository=repository,
        output_dir=output_dir,
        tracks=["evaluator", "reranker"],
        world_id="urban_mystery_lotus_lane",
        world_version_id=world_version_id,
    )

    assert set(result["summary"]["tracks_succeeded"]) == {"evaluator", "reranker"}
    assert (Path(result["artifacts"]["summary"])).exists()
    assert Path(result["evidence_results"]["evaluator"]["evidence_path"]).exists()
    assert Path(result["evidence_results"]["reranker"]["evidence_path"]).exists()
    assert "promotion_summary" in result["evidence_results"]["evaluator"]["evidence_pack"]
    assert "promotion_workflow" in result["evidence_results"]["reranker"]["evidence_pack"]
    assert result["cadence_results"]["evaluator"]["track_summary"]["track"] == "evaluator"
    assert result["evidence_results"]["evaluator"]["evidence_pack"]["cadence_snapshot"]["track"] == "evaluator"


def test_build_promotion_evidence_pack_handles_missing_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_training_missing.db"))
    output_dir = tmp_path / "evidence_output"

    result = build_promotion_evidence_pack(
        track="evaluator",
        repository=repository,
        output_dir=output_dir,
        evaluator_artifact_dir=tmp_path / "missing_eval",
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )
    assert Path(result["evidence_path"]).exists()
    assert result["evidence_pack"]["artifact_state"]["available"] is False
    assert "promotion_summary" in result["evidence_pack"]


def test_ops_learned_training_and_evidence_endpoints(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_training_api.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    app = create_app(repository=repository)
    client = TestClient(app)

    training = client.post(
        "/v1/ops/learned-training/run",
        json={
            "tracks": ["evaluator"],
            "world_id": "urban_mystery_lotus_lane",
            "world_version_id": world_version_id,
        },
    )
    assert training.status_code == 200
    assert set(training.json()["summary"]["tracks_succeeded"]) == {"evaluator"}

    evaluator_evidence = client.get(
        "/v1/ops/learned-promotion-evidence",
        params={"track": "evaluator", "world_id": "urban_mystery_lotus_lane", "world_version_id": world_version_id},
    )
    assert evaluator_evidence.status_code == 200
    assert "evidence_pack" in evaluator_evidence.json()
    assert evaluator_evidence.json()["evidence_pack"]["promotion_summary"]["track"] == "evaluator"
    assert evaluator_evidence.json()["evidence_pack"]["cadence_snapshot"]["track"] == "evaluator"

    approve = client.post(
        "/v1/ops/learned-promotion/approve",
        json={"reviewer_id": "ops_rollout", "reason": "准许 evaluator rollout。"},
    )
    assert approve.status_code == 200
    rollout = client.post(
        "/v1/ops/learned-rollout/evaluator/activate",
        json={"reviewer_id": "ops_rollout", "reason": "激活 evaluator rollout。"},
    )
    assert rollout.status_code == 200
    assert rollout.json()["tracks"]["evaluator"]["rollout_status"] == "active"

    rollout_summary = client.get("/v1/ops/learned-rollout")
    assert rollout_summary.status_code == 200
    assert "evaluator" in rollout_summary.json()["active_tracks"]

    rolled_back = client.post(
        "/v1/ops/learned-rollout/evaluator/rollback",
        json={"reviewer_id": "ops_rollout", "reason": "安全回滚 evaluator。"},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["tracks"]["evaluator"]["rollout_status"] == "rolled_back"

    reranker_evidence = client.get(
        "/v1/ops/learned-promotion-evidence",
        params={"track": "reranker", "world_id": "urban_mystery_lotus_lane", "world_version_id": world_version_id},
    )
    assert reranker_evidence.status_code == 200
    assert reranker_evidence.json()["evidence_pack"]["promotion_summary"]["track"] == "reranker"
