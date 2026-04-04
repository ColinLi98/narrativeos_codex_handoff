from pathlib import Path

import pytest

from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_promotion_workflow import (
    build_evaluator_promotion_workflow_summary,
    save_evaluator_promotion_decision,
)
from src.narrativeos.eval.learned_rollout import (
    activate_learned_rollout,
    build_learned_rollout_summary,
    rollback_learned_rollout,
)
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _seed_evaluator_world(repository: SQLAlchemyRepository) -> str:
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "1.1.0"
    pack["manifest"]["author_id"] = "rollout_eval"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    return draft["world_version_id"]


def test_learned_rollout_requires_approved_candidate_before_activate(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_rollout_blocked.db"))
    world_version_id = _seed_evaluator_world(repository)
    evaluator_artifact_dir = tmp_path / "eval_artifacts"
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_version_id=world_version_id,
    )

    with pytest.raises(ValueError):
        activate_learned_rollout(
            repository=repository,
            track="evaluator",
            reviewer_id="ops_rollout",
            reason="还没审批，不允许激活。",
            evaluator_artifact_dir=evaluator_artifact_dir,
            reranker_artifact_dir=tmp_path / "missing_rerank",
        )


def test_learned_rollout_can_activate_and_rollback_after_approval(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_rollout.db"))
    world_version_id = _seed_evaluator_world(repository)
    evaluator_artifact_dir = tmp_path / "eval_artifacts"
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
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )
    save_evaluator_promotion_decision(
        repository=repository,
        reviewer_id="ops_rollout",
        reason="允许进入 safe rollout。",
        status="approved",
        recommendation_summary=workflow,
    )

    activated = activate_learned_rollout(
        repository=repository,
        track="evaluator",
        reviewer_id="ops_rollout",
        reason="开始灰度。",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )
    assert activated["tracks"]["evaluator"]["rollout_status"] == "active"
    assert "evaluator" in activated["active_tracks"]

    rolled_back = rollback_learned_rollout(
        repository=repository,
        track="evaluator",
        reviewer_id="ops_rollout",
        reason="需要安全回滚。",
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )
    assert rolled_back["tracks"]["evaluator"]["rollout_status"] == "rolled_back"
