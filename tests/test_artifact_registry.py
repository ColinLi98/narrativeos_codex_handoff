from pathlib import Path

from src.narrativeos.eval.artifact_registry import (
    default_learned_evaluator_artifact_dir,
    default_learned_reranker_artifact_dir,
)
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry
from tests.test_learned_reranker_baseline import _seed_reranker_world


def test_evaluator_training_publishes_default_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "artifact_eval.db"))
    authoring = AuthoringService(repository)
    pack = FileSystemWorldRegistry().get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "1.0.0"
    pack["manifest"]["author_id"] = "artifact_eval"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])

    output_dir = tmp_path / "eval_artifacts"
    result = train_learned_evaluator_baseline(
        repository=repository,
        output_dir=output_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )
    default_dir = default_learned_evaluator_artifact_dir(Path(__file__).resolve().parents[1])
    assert (default_dir / "artifact_manifest.json").exists()
    assert result["published_artifact_manifest"]["artifact_type"] == "learned_evaluator_baseline"


def test_reranker_training_publishes_default_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "artifact_rerank.db"))
    world_version_id = _seed_reranker_world(repository)

    output_dir = tmp_path / "rerank_artifacts"
    result = train_learned_reranker_baseline(
        repository=repository,
        output_dir=output_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )
    default_dir = default_learned_reranker_artifact_dir(Path(__file__).resolve().parents[1])
    assert (default_dir / "artifact_manifest.json").exists()
    assert result["published_artifact_manifest"]["artifact_type"] == "learned_reranker_baseline"
