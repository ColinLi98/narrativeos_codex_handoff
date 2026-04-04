from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService
from tests.test_learned_reranker_baseline import _seed_reranker_world


def _seed_context(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "preference_ranking_pipeline.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    version = repository.get_world_version(world_version_id)
    revision_ids = [
        item["revision_id"]
        for item in (version.worldpack_json.get("metadata", {}) or {}).get("revision_history", [])
        if item.get("revision_id")
    ]
    assert len(revision_ids) >= 2
    return repository, world_version_id, version.world_id, revision_ids


def test_training_signal_service_can_save_and_list_preference_and_ranking_samples(tmp_path: Path):
    repository, world_version_id, world_id, revision_ids = _seed_context(tmp_path)
    service = TrainingSignalService(repository)

    preference = service.save_preference_sample(
        {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_pref",
            "left_revision_id": revision_ids[0],
            "right_revision_id": revision_ids[1],
            "preferred_revision_id": revision_ids[1],
            "freeform_notes": "右侧 revision 的节奏更顺。",
            "linked_issue_codes": ["Q04"],
            "preference_strength": "strong",
        }
    )
    ranking = service.save_ranking_sample(
        {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_rank",
            "ranked_revision_ids": revision_ids[:2],
            "freeform_notes": "后一版更像最终成稿。",
            "linked_issue_codes": ["Q04"],
        }
    )

    assert preference["preference_id"]
    assert ranking["ranking_id"]
    assert service.list_preference_samples(world_version_id=world_version_id)[0]["preferred_revision_id"] == revision_ids[1]
    assert service.list_ranking_samples(world_version_id=world_version_id)[0]["top_revision_id"] == revision_ids[0]


def test_training_signal_bundle_exports_preference_and_ranking_and_feeds_reranker_examples(tmp_path: Path):
    repository, world_version_id, world_id, revision_ids = _seed_context(tmp_path)
    service = TrainingSignalService(repository)
    service.save_preference_sample(
        {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_pref",
            "left_revision_id": revision_ids[0],
            "right_revision_id": revision_ids[1],
            "preferred_revision_id": revision_ids[1],
            "freeform_notes": "pairwise preference",
            "linked_issue_codes": ["Q04"],
            "preference_strength": "medium",
        }
    )
    service.save_ranking_sample(
        {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_rank",
            "ranked_revision_ids": revision_ids[:2],
            "freeform_notes": "ranking preference",
            "linked_issue_codes": ["Q04"],
        }
    )

    bundle = service.export_bundle(world_version_id=world_version_id, dataset_view="reranker")

    assert bundle["preference_samples"]
    assert bundle["ranking_samples"]
    assert bundle["manifest"]["counts"]["preference_samples"] == len(bundle["preference_samples"])
    assert bundle["manifest"]["counts"]["ranking_samples"] == len(bundle["ranking_samples"])
    assert bundle["manifest"]["source_breakdown"]["human_preference"] >= 1
    assert bundle["manifest"]["source_breakdown"]["human_ranking"] >= 1
    assert any(item["example_source"] == "preference_sample" for item in bundle["reranker_examples"])
    assert any(item["example_source"] == "ranking_sample" for item in bundle["reranker_examples"])


def test_ops_preference_and_ranking_sample_endpoints_work(tmp_path: Path):
    repository, world_version_id, world_id, revision_ids = _seed_context(tmp_path)
    app = create_app(repository=repository)
    client = TestClient(app)

    preference = client.post(
        "/v1/ops/preference-samples",
        json={
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_pref_api",
            "left_revision_id": revision_ids[0],
            "right_revision_id": revision_ids[1],
            "preferred_revision_id": revision_ids[0],
            "freeform_notes": "更偏好左侧 revision。",
            "linked_issue_codes": ["Q04"],
            "preference_strength": "medium",
        },
    )
    ranking = client.post(
        "/v1/ops/ranking-samples",
        json={
            "world_id": world_id,
            "world_version_id": world_version_id,
            "reviewer_id": "ops_rank_api",
            "ranked_revision_ids": revision_ids[:2],
            "freeform_notes": "排序确认。",
            "linked_issue_codes": ["Q04"],
        },
    )

    assert preference.status_code == 200
    assert ranking.status_code == 200
    preference_list = client.get("/v1/ops/preference-samples", params={"world_version_id": world_version_id})
    ranking_list = client.get("/v1/ops/ranking-samples", params={"world_version_id": world_version_id})
    assert preference_list.status_code == 200
    assert ranking_list.status_code == 200
    assert preference_list.json()["preference_samples"]
    assert ranking_list.json()["ranking_samples"]
