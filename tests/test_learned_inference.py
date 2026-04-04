from pathlib import Path

from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_inference import LearnedInferenceService
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_learned_inference_reports_unavailable_when_artifact_missing(tmp_path: Path):
    service = LearnedInferenceService(tmp_path / "missing_artifacts")
    status = service.availability()
    prediction = service.predict_example(
        {
            "chapter_id": "chapter_demo",
            "world_id": "urban_mystery_lotus_lane",
            "world_version_id": "urban_mystery_lotus_lane@0.1.0",
            "label_decision": "pass",
        }
    )
    assert status["available"] is False
    assert prediction["available"] is False


def test_learned_inference_can_load_artifact_and_predict(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_inference.db"))
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.7.0"
    pack["manifest"]["author_id"] = "learned_inference_test"
    draft = authoring.save_draft(pack)
    simulation = authoring.run_simulation_for_world_version(draft["world_version_id"])

    artifact_dir = tmp_path / "artifacts"
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )

    service = LearnedInferenceService(artifact_dir)
    summary = simulation["learned_evaluation_summary"]
    assert service.availability()["available"] is True
    assert "available" in summary

    report = simulation["chapter_evaluations"][0]
    example = {
        "chapter_id": report["chapter_id"],
        "world_id": simulation["world_id"],
        "world_version_id": simulation["world_version_id"],
        "review_source": "evaluation_report_auto",
        "score_overall": report["scores"]["overall_score"],
        "issue_codes": [item["issue_code"] for item in report["issues"]],
        "linked_issue_codes": [item["issue_code"] for item in report["issues"]],
        "would_continue": report["decision"]["decision"] in {"pass", "rewrite"},
        "would_pay": report["decision"]["decision"] == "pass",
        "label_decision": report["decision"]["decision"],
        "freeform_notes": report["summary"],
    }
    prediction = service.predict_example(example)
    assert prediction["available"] is True
    assert prediction["predicted_decision"] in {"pass", "rewrite", "block"}
