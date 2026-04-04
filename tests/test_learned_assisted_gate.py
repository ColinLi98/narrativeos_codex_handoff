from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_assisted_gate import (
    build_assisted_gate_summary,
    evaluate_assisted_gate_decision,
    save_assisted_gate_config,
)
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_promotion_workflow import (
    build_evaluator_promotion_workflow_summary,
    save_evaluator_promotion_decision,
)
from src.narrativeos.eval.learned_rollout import activate_learned_rollout
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.review import ReviewService, parse_review_notes
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry
from tests.test_learned_reranker_baseline import _seed_reranker_world


class _AlwaysBlockInference:
    def availability(self):
        return {"available": True}

    def predict_example(self, _example):
        return {"available": True, "predicted_decision": "block", "confidence": 0.99}


def _pass_simulation(version):
    simulation = dict(version.simulation_report_json or {})
    simulation["world_id"] = version.world_id
    simulation["latest_decision"] = "pass"
    simulation["evaluation_summary"] = {
        **dict(simulation.get("evaluation_summary", {})),
        "pass_rate": 1.0,
        "rewrite_rate": 0.0,
        "block_rate": 0.0,
    }
    simulation["cross_pack_summary"] = simulation.get("cross_pack_summary") or {
        "cross_pack_pass_rate": 1.0,
        "top_failing_packs": [],
        "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": [], "world_deltas": {}},
        "worlds": [],
    }
    version.simulation_report_json = simulation
    return version


def _seed_publishable_world(repository: SQLAlchemyRepository, *, world_id: str = "urban_mystery_lotus_lane") -> str:
    authoring = AuthoringService(repository, registry=FileSystemWorldRegistry())
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world(world_id)["worldpack"]
    pack["version"] = "1.0.3"
    pack["manifest"]["author_id"] = "assist_gate"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    version = repository.get_world_version(draft["world_version_id"])
    repository.save_world_version(_pass_simulation(version), publish=False)
    return draft["world_version_id"]


def test_assisted_gate_summary_defaults_to_disabled_shadow_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_gate_empty.db"))
    summary = build_assisted_gate_summary(repository=repository)

    assert summary["config"]["config"]["enabled"] is False
    assert summary["config"]["config"]["mode"] == "shadow_only"
    assert summary["recommended_next_action"] == "enable_shadow_only_capture"


def test_assisted_gate_shadow_only_receipt_never_blocks_publish(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_gate_shadow.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    version = repository.get_world_version(world_version_id)
    repository.save_world_version(_pass_simulation(version), publish=False)

    save_assisted_gate_config(
        repository=repository,
        reviewer_id="ops_web",
        reason="先只跑 shadow。",
        enabled=True,
        mode="shadow_only",
        bucket_percentage=100,
        confidence_threshold=0.9,
        min_example_count=3,
        min_high_confidence_blocks=2,
        required_block_share=0.5,
        world_allowlist=[],
    )
    receipt = evaluate_assisted_gate_decision(
        repository=repository,
        world_version_id=world_version_id,
        simulation=repository.get_world_version(world_version_id).simulation_report_json,
        rule_gate_errors=[],
        learned_inference_service=_AlwaysBlockInference(),
        persist_receipt=False,
    )

    assert receipt["mode"] == "shadow_only"
    assert receipt["would_block"] is True
    assert receipt["assisted_action"] == "none"
    assert receipt["final_gate_errors"] == []


def test_assisted_gate_can_block_publish_only_after_rollout_and_enablement(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_gate_active.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    version = repository.get_world_version(world_version_id)
    repository.save_world_version(_pass_simulation(version), publish=False)
    evaluator_artifact_dir = tmp_path / "eval_artifacts"
    reranker_artifact_dir = tmp_path / "rerank_artifacts"

    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_version_id=world_version_id,
    )
    workflow = build_evaluator_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_evaluator_promotion_decision(
        repository=repository,
        reviewer_id="ops_promoter",
        reason="允许实验前置 rollout。",
        status="approved",
        recommendation_summary=workflow,
    )
    activate_learned_rollout(
        repository=repository,
        track="evaluator",
        reviewer_id="ops_promoter",
        reason="先激活 evaluator rollout。",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_assisted_gate_config(
        repository=repository,
        reviewer_id="ops_web",
        reason="开启 assisted gate。",
        enabled=True,
        mode="assisted_gate",
        bucket_percentage=100,
        confidence_threshold=0.9,
        min_example_count=3,
        min_high_confidence_blocks=2,
        required_block_share=0.5,
        world_allowlist=[],
    )

    receipt = evaluate_assisted_gate_decision(
        repository=repository,
        world_version_id=world_version_id,
        simulation=repository.get_world_version(world_version_id).simulation_report_json,
        rule_gate_errors=[],
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
        learned_inference_service=_AlwaysBlockInference(),
        persist_receipt=False,
    )

    assert receipt["guardrail_status"] == "eligible"
    assert receipt["assisted_action"] == "block_publish"
    assert "assisted_learned_gate_block" in receipt["final_gate_errors"]


def test_review_publish_can_be_assisted_blocked(tmp_path: Path, monkeypatch):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_gate_publish.db"))
    world_version_id = _seed_publishable_world(repository)
    review = ReviewService(repository)

    def _receipt(**_kwargs):
        return {
            "mode": "assisted_gate",
            "bucket_match": True,
            "guardrail_status": "eligible",
            "assisted_action": "block_publish",
            "would_block": True,
            "final_gate_errors": ["assisted_learned_gate_block"],
        }

    monkeypatch.setattr("src.narrativeos.eval.learned_assisted_gate.evaluate_assisted_gate_decision", _receipt)

    with pytest.raises(ValueError, match="assisted_learned_gate_block"):
        review.publish(world_version_id, reviewer_id="reviewer_1")

    blocked = repository.list_review_records(status="publish_blocked", asset_type="world_version", asset_id=world_version_id)[0]
    payload = parse_review_notes(blocked["notes"])
    assert payload["assisted_gate_receipt"]["assisted_action"] == "block_publish"


def test_assisted_gate_endpoints_can_configure_and_report_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_gate_api.db"))
    client = TestClient(create_app(repository=repository))

    initial = client.get("/v1/ops/learned-assisted-gate")
    assert initial.status_code == 200
    assert initial.json()["config"]["config"]["mode"] == "shadow_only"

    configured = client.post(
        "/v1/ops/learned-assisted-gate/configure",
        json={
            "reviewer_id": "ops_web",
            "reason": "先开 shadow 实验。",
            "enabled": True,
            "mode": "shadow_only",
            "bucket_percentage": 10,
            "confidence_threshold": 0.9,
            "min_example_count": 3,
            "min_high_confidence_blocks": 2,
            "required_block_share": 0.5,
            "world_allowlist": ["urban_mystery_lotus_lane"],
        },
    )
    assert configured.status_code == 200
    assert configured.json()["config"]["config"]["enabled"] is True
    assert configured.json()["config"]["config"]["bucket_percentage"] == 10
