import json
from pathlib import Path

from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.eval.learned_reranker_shadow import LearnedRerankerShadowService
from src.narrativeos.repository import SQLAlchemyRepository
from tests.test_learned_reranker_baseline import _seed_reranker_world
from src.narrativeos.services.training_signal import TrainingSignalService


def _trained_reranker_artifact_dir(tmp_path: Path) -> tuple[Path, SQLAlchemyRepository]:
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reranker_shadow.db"))
    _seed_reranker_world(repository)
    artifact_dir = tmp_path / "artifacts"
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=artifact_dir,
        dataset_view="reranker",
        world_id="urban_mystery_lotus_lane",
    )
    return artifact_dir, repository


def test_learned_reranker_shadow_status_unavailable_when_artifact_missing(tmp_path: Path):
    service = LearnedRerankerShadowService(tmp_path / "missing")
    summary = service.summarize({})
    assert summary["status"] == "unavailable"
    assert summary["recommended_next_action"] == "train_reranker_artifact"


def test_learned_reranker_shadow_status_warming_up_candidate_and_not_ready(tmp_path: Path):
    artifact_dir, repository = _trained_reranker_artifact_dir(tmp_path)
    bundle = TrainingSignalService(repository).export_bundle(world_id="urban_mystery_lotus_lane", dataset_view="reranker")
    service = LearnedRerankerShadowService(artifact_dir)

    warming_up = service.summarize(bundle)
    assert warming_up["status"] == "warming_up"
    assert warming_up["recommended_next_action"] in {"expand_issue_fix_pairs", "collect_more_fix_pairs"}

    manifest_path = artifact_dir / "reranker_training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["val_count"] = 5
    manifest["test_count"] = 5
    manifest["warnings"] = []
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics_path = artifact_dir / "reranker_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["per_world_accuracy"] = {"urban_mystery_lotus_lane": 0.8}
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    candidate = service.summarize(bundle)
    assert candidate["status"] == "candidate"
    assert candidate["recommended_next_action"] == "consider_shadow_candidate_reranker"

    metrics["per_world_accuracy"] = {"urban_mystery_lotus_lane": 0.4}
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    not_ready = service.summarize(bundle)
    assert not_ready["status"] == "not_ready"
    assert not_ready["recommended_next_action"] == "inspect_low_accuracy_worlds"
