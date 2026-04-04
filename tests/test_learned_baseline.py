from pathlib import Path

from src.narrativeos.eval.learned_baseline import main, train_learned_evaluator_baseline
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_learned_evaluator_baseline_trains_and_writes_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_eval.db"))
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.5.0"
    pack["manifest"]["author_id"] = "learned_eval_test"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])

    output_dir = tmp_path / "artifacts"
    result = train_learned_evaluator_baseline(
        repository=repository,
        output_dir=output_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )

    assert (output_dir / "model.joblib").exists()
    assert (output_dir / "label_encoder.json").exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "feature_manifest.json").exists()
    assert (output_dir / "training_manifest.json").exists()
    assert "macro_f1" in result["metrics"]
    assert "train_count" in result["training_manifest"]


def test_learned_evaluator_cli_runs_with_output_dir(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_eval_cli.db"))
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("synthetic_min_pack")["worldpack"]
    pack["version"] = "0.2.0"
    pack["manifest"]["author_id"] = "learned_eval_cli"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])

    output_dir = tmp_path / "cli_artifacts"
    exit_code = main(
        [
            "--dataset-view",
            "evaluator",
            "--world-version-id",
            draft["world_version_id"],
            "--output-dir",
            str(output_dir),
            "--database-url",
            "sqlite:///%s" % (tmp_path / "learned_eval_cli.db"),
        ]
    )
    assert exit_code == 0
    assert (output_dir / "training_manifest.json").exists()
