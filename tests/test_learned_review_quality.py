from pathlib import Path

from fastapi.testclient import TestClient
import json

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_review_quality import (
    build_learned_review_quality_summary,
    build_learned_review_quality_world_detail,
)
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService
from tests.test_learned_data_ops import _seed_ops_data


def test_learned_review_quality_summary_reports_missing_human_reviews(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_review_quality_empty.db"))
    summary = build_learned_review_quality_summary(repository=repository)

    assert summary["quality_summary"]["sample_count"] == 0
    assert summary["coverage_summary"]["worlds_below_target_count"] == 0
    assert "missing_human_review_samples" in summary["warnings"]


def test_learned_review_quality_summary_surfaces_gaps_and_quality_warnings(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_review_quality.db"))
    world_version_id = _seed_ops_data(repository)
    training_signal = TrainingSignalService(repository)
    training_signal.save_review_sample(
        {
            "chapter_id": "chapter_ops_data_1",
            "world_id": "jade_court_romance",
            "world_version_id": world_version_id,
            "reviewer_id": "ops_reviewer_a",
            "score_overall": 0.61,
            "issue_codes": ["Q04"],
            "linked_issue_codes": [],
            "freeform_notes": "少一条 linked issue code，看看质量审计能不能抓到。",
            "would_continue": True,
            "would_pay": False,
        }
    )
    repository.save_review_record(
        {
            "review_id": "legacy_missing_linked_issue_codes",
            "asset_type": "review_sample",
            "asset_id": "chapter_ops_data_legacy",
            "status": "human_review",
                "reviewer_id": "ops_reviewer_a",
                "notes": json.dumps(
                    {
                        "sample_id": "sample_legacy_missing_linked",
                    "chapter_id": "chapter_ops_data_legacy",
                    "world_id": "jade_court_romance",
                    "world_version_id": world_version_id,
                    "session_id": None,
                        "reviewer_id": "ops_reviewer_a",
                    "score_overall": 0.55,
                    "issue_codes": ["Q04"],
                    "linked_issue_codes": [],
                    "freeform_notes": "legacy sample without linked issue codes",
                    "would_continue": False,
                    "would_pay": False,
                    "created_at": "2026-04-01T00:00:00+00:00",
                    "source": "human_review",
                    "source_ref": {"kind": "manual_entry", "chapter_id": "chapter_ops_data_legacy"},
                    "ingestion_meta": {
                        "ingestion_key": "legacy_missing_linked",
                        "reference_status": "unknown",
                        "ingested_at": "2026-04-01T00:00:00+00:00",
                        "storage_mode": "legacy",
                        "ingestion_warnings": ["missing_linked_issue_codes"],
                    },
                },
                ensure_ascii=False,
            ),
        }
    )
    training_signal.save_review_sample(
        {
            "chapter_id": "chapter_ops_data_2",
            "world_id": "jade_court_romance",
            "world_version_id": world_version_id,
            "reviewer_id": "ops_reviewer_a",
            "score_overall": 0.72,
            "issue_codes": ["Q05"],
            "linked_issue_codes": ["Q05"],
            "freeform_notes": "同一个 reviewer，再制造 reviewer diversity gap。",
            "would_continue": True,
            "would_pay": False,
        }
    )

    summary = build_learned_review_quality_summary(
        repository=repository,
        world_id="jade_court_romance",
    )

    assert summary["quality_summary"]["sample_count"] >= 2
    assert summary["quality_summary"]["warning_sample_count"] >= 1
    assert summary["quality_summary"]["missing_session_context_count"] >= 1
    assert summary["quality_summary"]["missing_linked_issue_codes_count"] >= 1
    assert summary["coverage_summary"]["worlds_below_target_count"] >= 1
    assert summary["replenishment_backlog"]
    assert summary["flagged_samples"]
    assert summary["replenishment_backlog"][0]["world_id"] == "jade_court_romance"
    assert "reviewer_diversity_count" in summary["replenishment_backlog"][0]


def test_learned_review_quality_endpoints_return_summary_and_world_detail(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_review_quality_api.db"))
    world_version_id = _seed_ops_data(repository)
    TrainingSignalService(repository).save_review_sample(
        {
            "chapter_id": "chapter_ops_data_1",
            "world_id": "jade_court_romance",
            "world_version_id": world_version_id,
            "reviewer_id": "ops_reviewer_a",
            "score_overall": 0.63,
            "issue_codes": ["Q04"],
            "linked_issue_codes": ["Q04"],
            "freeform_notes": "给 endpoint 一个最小 human review。",
            "would_continue": True,
            "would_pay": False,
        }
    )

    client = TestClient(create_app(repository=repository))
    summary = client.get("/v1/ops/learned-review-quality", params={"world_id": "jade_court_romance"})
    detail = client.get("/v1/ops/learned-review-quality/worlds/jade_court_romance")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert "coverage_summary" in summary.json()
    assert "quality_summary" in summary.json()
    assert "replenishment_backlog" in summary.json()
    assert detail.json()["world_id"] == "jade_court_romance"
    assert "world_detail" in detail.json()
