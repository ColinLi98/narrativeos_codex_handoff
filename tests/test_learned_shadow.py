import json
from pathlib import Path

from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_shadow import LearnedShadowService
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _trained_artifact_dir(tmp_path: Path) -> Path:
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "shadow_artifact.db"))
    authoring = AuthoringService(repository)
    pack = FileSystemWorldRegistry().get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.2"
    pack["manifest"]["author_id"] = "shadow_status"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    artifact_dir = tmp_path / "artifacts"
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )
    return artifact_dir


def test_learned_shadow_status_unavailable_when_artifact_missing(tmp_path: Path):
    service = LearnedShadowService(tmp_path / "missing")
    summary = service.summarize({})
    assert summary["status"] == "unavailable"
    assert summary["recommended_next_action"] == "train_baseline_artifact"


def test_learned_shadow_status_warming_up_with_zero_val_or_test(tmp_path: Path):
    artifact_dir = _trained_artifact_dir(tmp_path)
    service = LearnedShadowService(artifact_dir)
    summary = service.summarize({"agreement_rate": 0.9, "top_mismatch_worlds": [], "top_mismatch_issue_codes": []})
    assert summary["status"] == "warming_up"
    assert summary["recommended_next_action"] == "expand_eval_dataset"


def test_learned_shadow_status_candidate_and_not_ready(tmp_path: Path):
    artifact_dir = _trained_artifact_dir(tmp_path)
    training_manifest_path = artifact_dir / "training_manifest.json"
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    training_manifest["val_count"] = 5
    training_manifest["test_count"] = 5
    training_manifest["warnings"] = []
    training_manifest_path.write_text(json.dumps(training_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    service = LearnedShadowService(artifact_dir)
    candidate = service.summarize({"agreement_rate": 0.85, "top_mismatch_worlds": [], "top_mismatch_issue_codes": []})
    assert candidate["status"] == "candidate"
    assert candidate["recommended_next_action"] == "consider_stricter_shadow_candidate"

    not_ready = service.summarize({"agreement_rate": 0.45, "top_mismatch_worlds": [], "top_mismatch_issue_codes": []})
    assert not_ready["status"] == "not_ready"
    assert not_ready["recommended_next_action"] == "inspect_top_mismatches"
