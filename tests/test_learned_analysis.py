from pathlib import Path

from src.narrativeos.eval.learned_analysis import main, run_learned_analysis
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.repository import SQLAlchemyRepository
from tests.test_learned_reranker_baseline import _seed_reranker_world


def test_learned_analysis_handles_missing_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_analysis_missing.db"))
    output_dir = tmp_path / "analysis_output"
    result = run_learned_analysis(
        repository=repository,
        output_dir=output_dir,
        evaluator_artifact_dir=tmp_path / "missing_eval",
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )

    assert (output_dir / "learned_analysis.json").exists()
    assert (output_dir / "learned_analysis_manifest.json").exists()
    assert result["report"]["evaluator_analysis"]["available"] is False
    assert result["report"]["reranker_analysis"]["available"] is False
    assert result["report"]["cross_model_findings"]["recommended_next_focus"]


def test_learned_analysis_can_unify_evaluator_and_reranker_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_analysis.db"))
    world_version_id = _seed_reranker_world(repository)
    evaluator_artifact_dir = tmp_path / "eval_artifacts"
    reranker_artifact_dir = tmp_path / "rerank_artifacts"

    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )

    output_dir = tmp_path / "analysis_output"
    result = run_learned_analysis(
        repository=repository,
        output_dir=output_dir,
        world_id="urban_mystery_lotus_lane",
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )

    assert result["report"]["evaluator_analysis"]["available"] is True
    assert result["report"]["reranker_analysis"]["available"] is True
    assert "shared_weak_worlds" in result["report"]["cross_model_findings"]
    assert "recommended_next_focus" in result["report"]["cross_model_findings"]
    assert (output_dir / "learned_analysis.json").exists()
    assert (output_dir / "learned_analysis_manifest.json").exists()


def test_learned_analysis_cli_runs_with_output_dir(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_analysis_cli.db"))
    world_version_id = _seed_reranker_world(repository)
    evaluator_artifact_dir = tmp_path / "eval_cli_artifacts"
    reranker_artifact_dir = tmp_path / "rerank_cli_artifacts"

    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=evaluator_artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )

    output_dir = tmp_path / "analysis_cli_output"
    exit_code = main(
        [
            "--world-id",
            "urban_mystery_lotus_lane",
            "--database-url",
            "sqlite:///%s" % (tmp_path / "learned_analysis_cli.db"),
            "--evaluator-artifact-dir",
            str(evaluator_artifact_dir),
            "--reranker-artifact-dir",
            str(reranker_artifact_dir),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert exit_code == 0
    assert (output_dir / "learned_analysis.json").exists()
