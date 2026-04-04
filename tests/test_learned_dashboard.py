from pathlib import Path

from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_dashboard import build_learned_dashboard_summary
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.repository import SQLAlchemyRepository
from tests.test_learned_reranker_baseline import _seed_reranker_world


def test_learned_dashboard_handles_missing_artifacts(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_dashboard_missing.db"))
    summary = build_learned_dashboard_summary(
        repository=repository,
        evaluator_artifact_dir=tmp_path / "missing_eval",
        reranker_artifact_dir=tmp_path / "missing_rerank",
    )
    assert "artifact_status" in summary
    assert summary["artifact_status"]["evaluator"]["available"] is False
    assert summary["artifact_status"]["reranker"]["available"] is False
    assert "published_at" in summary["artifact_status"]["evaluator"]
    assert "source_output_dir" in summary["artifact_status"]["reranker"]
    assert "world_details" in summary
    assert "issue_details" in summary
    assert "recommended_next_focus" in summary


def test_learned_dashboard_can_unify_evaluator_and_reranker_shadow_data(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_dashboard.db"))
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

    summary = build_learned_dashboard_summary(
        repository=repository,
        world_id="urban_mystery_lotus_lane",
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    assert summary["artifact_status"]["evaluator"]["available"] is True
    assert summary["artifact_status"]["reranker"]["available"] is True
    assert summary["artifact_status"]["evaluator"]["published_at"]
    assert summary["artifact_status"]["reranker"]["source_output_dir"]
    assert summary["artifact_status"]["evaluator"]["artifact_files"]
    assert summary["artifact_status"]["reranker"]["artifact_files"]
    assert "evaluator_shadow_summary" in summary
    assert "reranker_shadow_summary" in summary
    assert "coverage_summary" in summary
    assert "warnings" in summary
    assert "world_details" in summary
    assert "issue_details" in summary
