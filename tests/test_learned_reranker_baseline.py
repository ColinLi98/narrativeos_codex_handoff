from pathlib import Path

from src.narrativeos.eval.learned_reranker_baseline import main, train_learned_reranker_baseline
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.training_signal import TrainingSignalService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _seed_reranker_world(repository: SQLAlchemyRepository, *, world_id: str = "urban_mystery_lotus_lane") -> str:
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world(world_id)["worldpack"]
    pack["version"] = "0.9.1"
    pack["manifest"]["author_id"] = "reranker_test"
    draft = authoring.save_draft(pack)
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["characters"][0]["display_name"] = "江屿"
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "character_editor", "label": "保存角色卡"},
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["scene_blueprints"][0]["beats_template"] = ["夜巷相遇", "停顿", "逼问", "留下回响"]
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "scene_editor", "label": "保存场景蓝图"},
    )
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    version = repository.get_world_version(draft["world_version_id"])
    metadata = dict((version.worldpack_json or {}).get("metadata", {}))
    revision_history = list(metadata.get("revision_history", []))
    if revision_history:
        revision_history[-1]["simulation_delta"] = {
            "pass_rate_delta": 0.25,
            "rewrite_rate_delta": -0.25,
            "block_rate_delta": 0.0,
            "metric_deltas": {
                "pass_rate_delta": 0.25,
                "rewrite_rate_delta": -0.25,
                "block_rate_delta": 0.0,
            },
        }
        metadata["revision_history"] = revision_history
        version.worldpack_json["metadata"] = metadata
        repository.save_world_version(version, publish=False)
    TrainingSignalService(repository).save_review_sample(
        {
            "chapter_id": "manual_chapter_reranker",
            "world_id": world_id,
            "world_version_id": draft["world_version_id"],
            "reviewer_id": "ops_reviewer",
            "score_overall": 0.76,
            "issue_codes": ["Q04"],
            "linked_issue_codes": ["Q04"],
            "freeform_notes": "这一章需要更少解释句。",
            "would_continue": True,
            "would_pay": False,
        }
    )
    return draft["world_version_id"]


def test_learned_reranker_baseline_trains_and_writes_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_reranker.db"))
    world_version_id = _seed_reranker_world(repository)

    output_dir = tmp_path / "reranker_artifacts"
    result = train_learned_reranker_baseline(
        repository=repository,
        output_dir=output_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )

    assert (output_dir / "reranker_model.joblib").exists()
    assert (output_dir / "reranker_metrics.json").exists()
    assert (output_dir / "reranker_feature_manifest.json").exists()
    assert (output_dir / "reranker_training_manifest.json").exists()
    assert "macro_f1" in result["metrics"]
    assert "train_count" in result["training_manifest"]


def test_learned_reranker_cli_runs_with_output_dir(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_reranker_cli.db"))
    world_version_id = _seed_reranker_world(repository, world_id="synthetic_min_pack")

    output_dir = tmp_path / "reranker_cli_artifacts"
    exit_code = main(
        [
            "--dataset-view",
            "reranker",
            "--world-version-id",
            world_version_id,
            "--output-dir",
            str(output_dir),
            "--database-url",
            "sqlite:///%s" % (tmp_path / "learned_reranker_cli.db"),
        ]
    )
    assert exit_code == 0
    assert (output_dir / "reranker_training_manifest.json").exists()
