from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.persistence.db import AnalyticsEventRow, SessionRow
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.schemas import validate_payload
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.training_signal import TrainingSignalService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_phase4_schema_roundtrip_examples_validate():
    review_sample = {
        "sample_id": "sample_demo",
        "chapter_id": "chapter_demo",
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "session_id": "session_demo",
        "reviewer_id": "narrative_eval_auto",
        "score_overall": 0.81,
        "issue_codes": ["Q04"],
        "freeform_notes": "自动映射样本",
        "would_continue": True,
        "would_pay": True,
        "created_at": "2026-04-01T00:00:00+00:00",
        "source": "evaluation_report_auto",
        "revision_id": None,
        "linked_issue_codes": ["Q04"],
        "source_ref": {"kind": "evaluation_report", "chapter_id": "chapter_demo"},
    }
    revision_log = {
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "revision_id": "rev_demo",
        "source": "character_editor",
        "label": "保存角色卡",
        "changed_sections": ["characters"],
        "summary": "角色卡 1 处改动",
        "simulation_delta": {"pass_rate_delta": 0.1},
        "timestamp": "2026-04-01T00:00:00+00:00",
    }
    continue_event = {
        "event_name": "session_abandoned",
        "reader_id": "reader_demo",
        "session_id": "session_demo",
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "chapter_index": 0,
        "access_tier": "trial",
        "occurred_at": "2026-04-01T00:00:00+00:00",
        "payload_json": {"inferred": True},
    }
    fix_pair = {
        "pair_id": "pair_demo",
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "before_revision_id": "rev_before",
        "after_revision_id": "rev_after",
        "changed_sections": ["characters"],
        "before_summary": "角色卡 1 处改动",
        "after_summary": "角色卡 1 处改动；scene blueprint 1 处改动",
        "simulation_delta": {"pass_rate_delta": 0.1},
        "improved": True,
        "linked_review_sample_ids": ["sample_demo"],
        "linked_issue_codes": ["Q04"],
        "timestamp": "2026-04-01T00:00:00+00:00",
    }
    preference_sample = {
        "preference_id": "pref_demo",
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "chapter_id": "chapter_demo",
        "session_id": "session_demo",
        "reviewer_id": "ops_pref",
        "left_revision_id": "rev_before",
        "right_revision_id": "rev_after",
        "preferred_revision_id": "rev_after",
        "freeform_notes": "更偏好后一个版本。",
        "linked_issue_codes": ["Q04"],
        "preference_strength": "strong",
        "created_at": "2026-04-01T00:00:00+00:00",
        "source": "human_preference",
    }
    ranking_sample = {
        "ranking_id": "rank_demo",
        "world_id": "demo_world",
        "world_version_id": "demo_world@0.1.0",
        "chapter_id": "chapter_demo",
        "session_id": "session_demo",
        "reviewer_id": "ops_rank",
        "ranked_revision_ids": ["rev_after", "rev_before"],
        "top_revision_id": "rev_after",
        "freeform_notes": "排序确认。",
        "linked_issue_codes": ["Q04"],
        "created_at": "2026-04-01T00:00:00+00:00",
        "source": "human_ranking",
    }
    bundle = {
        "chapter_review_samples": [review_sample],
        "preference_samples": [preference_sample],
        "ranking_samples": [ranking_sample],
        "author_revision_logs": [revision_log],
        "continue_churn_events": [continue_event],
        "issue_fix_pairs": [fix_pair],
        "manifest": {
            "bundle_id": "bundle_demo",
            "generated_at": "2026-04-01T00:00:00+00:00",
            "filters": {
                "world_id": "demo_world",
                "world_version_id": None,
                "limit": 10,
                "since": None,
                "cursor": None,
                "include_inferred": True,
                "include_fix_pairs": True
            },
            "counts": {
                "chapter_review_samples": 1,
                "preference_samples": 1,
                "ranking_samples": 1,
                "author_revision_logs": 1,
                "continue_churn_events": 1,
                "issue_fix_pairs": 1
            },
            "source_breakdown": {
                "evaluation_report_auto": 1,
                "human_review": 0,
                "human_preference": 1,
                "human_ranking": 1,
                "inferred_session_abandoned": 1
            },
            "issue_code_histogram": {"Q04": 1},
            "inferred_event_count": 1,
            "warnings": []
        },
        "pack_quality_trends": [
            {
                "world_id": "demo_world",
                "world_version_id": "demo_world@0.1.0",
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "cross_pack_pass_rate": 0.9,
                "updated_at": "2026-04-01T00:00:00+00:00"
            }
        ],
        "evaluator_examples": [
            {
                "example_id": "eval_sample_demo",
                "chapter_id": "chapter_demo",
                "world_id": "demo_world",
                "world_version_id": "demo_world@0.1.0",
                "review_source": "evaluation_report_auto",
                "score_overall": 0.81,
                "issue_codes": ["Q04"],
                "linked_issue_codes": ["Q04"],
                "would_continue": True,
                "would_pay": True,
                "label_decision": "pass",
                "split": "train",
                "text_source_ref": {
                    "chapter_id": "chapter_demo",
                    "world_version_id": "demo_world@0.1.0"
                }
            }
        ],
        "reranker_examples": [
            {
                "example_id": "rerank_pair_demo",
                "world_id": "demo_world",
                "world_version_id": "demo_world@0.1.0",
                "before_revision_id": "rev_before",
                "after_revision_id": "rev_after",
                "changed_sections": ["characters"],
                "linked_issue_codes": ["Q04"],
                "preferred_revision_id": "rev_after",
                "preference_strength": "strong",
                "example_source": "issue_fix_pair",
                "split": "train"
            }
        ],
        "analytics_examples": [
            {
                "example_id": "analytics_session_demo",
                "reader_id": "reader_demo",
                "session_id": "session_demo",
                "world_id": "demo_world",
                "world_version_id": "demo_world@0.1.0",
                "chapter_index": 0,
                "access_tier": "trial",
                "label_continue": 0,
                "label_churn": 1,
                "event_source": "session_abandoned",
                "split": "train"
            }
        ],
        "generated_at": "2026-04-01T00:00:00+00:00",
        "filters": {
            "world_id": "demo_world",
            "world_version_id": None,
            "limit": 10,
            "since": None,
            "cursor": None,
            "include_inferred": True,
            "include_fix_pairs": True,
            "dataset_view": "raw",
        },
        "next_cursor": "2026-04-01T00:00:00+00:00|pair_demo",
    }

    validate_payload(review_sample, "review_sample.schema.json")
    validate_payload(preference_sample, "preference_sample.schema.json")
    validate_payload(ranking_sample, "ranking_sample.schema.json")
    validate_payload(revision_log, "author_revision_log.schema.json")
    validate_payload(continue_event, "continue_churn_event.schema.json")
    validate_payload(fix_pair, "issue_fix_pair.schema.json")
    validate_payload(bundle, "training_signal_bundle.schema.json")


def test_training_signal_service_exports_review_samples_revision_logs_and_churn(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "phase4_export.db"))
    app = create_app(repository=repository)
    authoring = AuthoringService(repository)
    exporter = TrainingSignalService(repository)
    client = TestClient(app)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.4.0"
    pack["manifest"]["author_id"] = "phase4_export"
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

    human_review = exporter.save_review_sample(
        {
            "chapter_id": "manual_chapter_1",
            "world_id": "urban_mystery_lotus_lane",
            "world_version_id": draft["world_version_id"],
            "reviewer_id": "ops_reviewer",
            "score_overall": 0.74,
            "issue_codes": ["Q04"],
            "freeform_notes": "这一章需要更少解释句。",
            "would_continue": True,
            "would_pay": False,
        }
    )
    assert human_review["source"] == "human_review"
    duplicate_review = exporter.save_review_sample(
        {
            "chapter_id": "manual_chapter_1",
            "world_id": "urban_mystery_lotus_lane",
            "world_version_id": draft["world_version_id"],
            "reviewer_id": "ops_reviewer",
            "score_overall": 0.78,
            "issue_codes": ["Q04", "q05"],
            "freeform_notes": "第二次录入，应该覆盖同一 logical sample。",
            "would_continue": True,
            "would_pay": False,
        }
    )
    assert duplicate_review["sample_id"] == human_review["sample_id"]

    active = client.post(
        "/v1/reader/sessions",
        json={"world_id": "urban_mystery_lotus_lane", "reader_id": "reader_phase4_active"},
    ).json()
    client.post(
        "/v1/reader/continue",
        json={"session_id": active["session_id"], "reader_id": "reader_phase4_active", "freeform_intent": "我先顺着这条旧巷再往前走一步。"},
    )
    client.post(
        "/v1/reader/sessions",
        json={"world_id": "urban_mystery_lotus_lane", "reader_id": "reader_phase4_abandoned"},
    )
    with repository.SessionLocal() as db:
        abandoned_session = db.get(SessionRow, active["session_id"])
        assert abandoned_session is not None
        created_event = (
            db.query(AnalyticsEventRow)
            .filter(AnalyticsEventRow.reader_id == "reader_phase4_abandoned")
            .filter(AnalyticsEventRow.event_name == "session_created")
            .order_by(AnalyticsEventRow.event_id.desc())
            .first()
        )
        abandoned_row = (
            db.query(SessionRow)
            .filter(SessionRow.reader_id == "reader_phase4_abandoned")
            .order_by(SessionRow.created_at.desc())
            .first()
        )
        assert abandoned_row is not None
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        abandoned_row.created_at = old_time
        abandoned_row.updated_at = old_time
        if created_event is not None:
            created_event.occurred_at = old_time
        db.commit()

    bundle = exporter.export_bundle(world_id="urban_mystery_lotus_lane")

    assert bundle["chapter_review_samples"]
    assert "preference_samples" in bundle
    assert "ranking_samples" in bundle
    assert bundle["author_revision_logs"]
    assert bundle["continue_churn_events"]
    assert bundle["issue_fix_pairs"]
    assert "next_cursor" in bundle
    assert any(item["source"] == "evaluation_report_auto" for item in bundle["chapter_review_samples"])
    assert any(item["source"] == "human_review" for item in bundle["chapter_review_samples"])
    assert any(item["source"] == "character_editor" for item in bundle["author_revision_logs"])
    assert any(item["event_name"] == "continue_story" for item in bundle["continue_churn_events"])
    assert any(item["event_name"] == "session_abandoned" for item in bundle["continue_churn_events"])
    abandoned = next(item for item in bundle["continue_churn_events"] if item["event_name"] == "session_abandoned")
    assert abandoned["payload_json"]["abandon_window_hours"] == 24
    assert bundle["manifest"]["counts"]["chapter_review_samples"] == len(bundle["chapter_review_samples"])
    assert bundle["manifest"]["counts"]["preference_samples"] == len(bundle["preference_samples"])
    assert bundle["manifest"]["counts"]["ranking_samples"] == len(bundle["ranking_samples"])
    assert bundle["manifest"]["counts"]["issue_fix_pairs"] == len(bundle["issue_fix_pairs"])
    assert bundle["pack_quality_trends"]
    assert any(item["linked_review_sample_ids"] for item in bundle["issue_fix_pairs"])
    assert any(item["linked_issue_codes"] for item in bundle["issue_fix_pairs"])
    assert any(item["pair_quality"] in {"strong", "medium", "weak"} for item in bundle["issue_fix_pairs"])
    assert any("review_coverage_count" in item for item in bundle["issue_fix_pairs"])
    assert any("ingestion_meta" in item for item in bundle["chapter_review_samples"])
    assert "warnings" in bundle["manifest"]
    validate_payload(bundle, "training_signal_bundle.schema.json")

    no_inferred = exporter.export_bundle(world_id="urban_mystery_lotus_lane", include_inferred=False)
    assert all(item["event_name"] != "session_abandoned" for item in no_inferred["continue_churn_events"])

    filtered_since = exporter.export_bundle(
        world_id="urban_mystery_lotus_lane",
        since=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )
    assert all(item["source"] != "human_review" or item["created_at"] >= filtered_since["filters"]["since"] for item in filtered_since["chapter_review_samples"])

    cursor = bundle["next_cursor"]
    paged = exporter.export_bundle(world_id="urban_mystery_lotus_lane", limit=1, cursor=cursor)
    assert paged["filters"]["cursor"] == cursor

    evaluator = exporter.export_bundle(world_id="urban_mystery_lotus_lane", dataset_view="evaluator")
    reranker = exporter.export_bundle(world_id="urban_mystery_lotus_lane", dataset_view="reranker")
    analytics = exporter.export_bundle(world_id="urban_mystery_lotus_lane", dataset_view="analytics")
    raw = exporter.export_bundle(world_id="urban_mystery_lotus_lane", dataset_view="raw")
    assert evaluator["evaluator_examples"]
    assert analytics["analytics_examples"]
    assert raw["evaluator_examples"] == []
    assert isinstance(reranker["reranker_examples"], list)
    assert raw["reranker_examples"] == []
    assert raw["analytics_examples"] == []
    assert "preference_samples" in raw
    assert "ranking_samples" in raw
    assert evaluator["filters"]["dataset_view"] == "evaluator"
    assert reranker["filters"]["dataset_view"] == "reranker"
    assert analytics["filters"]["dataset_view"] == "analytics"
    assert all(item["split"] in {"train", "val", "test"} for item in evaluator["evaluator_examples"])
    assert all(item["split"] in {"train", "val", "test"} for item in reranker["reranker_examples"])
    assert all(item["split"] in {"train", "val", "test"} for item in analytics["analytics_examples"])


def test_ops_export_training_signal_endpoint_supports_filters(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "phase4_export_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    authoring = AuthoringService(repository)

    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "实验导出",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "一个用于导出 training signal 的最小世界。",
            "life_theme": "如何在压力里作出决定",
            "locations": "中庭\n长廊\n窗边",
        }
    )
    authoring.run_simulation_for_world_version(draft["world_version_id"])

    payload = client.get(
        "/v1/ops/export/training-signal",
        params={"world_version_id": draft["world_version_id"], "limit": 1, "include_fix_pairs": "true", "include_inferred": "false", "dataset_view": "evaluator"},
    )
    assert payload.status_code == 200
    data = payload.json()
    assert set(data.keys()) == {"chapter_review_samples", "preference_samples", "ranking_samples", "author_revision_logs", "continue_churn_events", "issue_fix_pairs", "manifest", "pack_quality_trends", "evaluator_examples", "reranker_examples", "analytics_examples", "generated_at", "filters", "next_cursor"}
    assert data["filters"]["world_version_id"] == draft["world_version_id"]
    assert data["filters"]["include_fix_pairs"] is True
    assert data["filters"]["include_inferred"] is False
    assert data["filters"]["dataset_view"] == "evaluator"
    assert len(data["chapter_review_samples"]) <= 1
    assert len(data["preference_samples"]) <= 1
    assert len(data["ranking_samples"]) <= 1
    assert len(data["author_revision_logs"]) <= 1
    assert len(data["continue_churn_events"]) <= 1
    assert len(data["issue_fix_pairs"]) <= 1
    assert data["manifest"]["counts"]["chapter_review_samples"] == len(data["chapter_review_samples"])
    assert data["manifest"]["counts"]["preference_samples"] == len(data["preference_samples"])
    assert data["manifest"]["counts"]["ranking_samples"] == len(data["ranking_samples"])
    assert data["pack_quality_trends"]
    assert "warnings" in data["manifest"]
    validate_payload(data, "training_signal_bundle.schema.json")


def test_ops_review_samples_api_supports_write_and_filters(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "phase4_review_sample_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    create = client.post(
        "/v1/ops/review-samples",
        json={
            "chapter_id": "chapter_human_1",
            "world_id": "jade_court_exam",
            "world_version_id": "jade_court_exam@0.1.0",
            "reviewer_id": "human_ops",
            "score_overall": 0.68,
            "issue_codes": ["Q05"],
            "freeform_notes": "还需要更多场景细节。",
            "would_continue": True,
            "would_pay": False,
        },
    )
    assert create.status_code == 200
    assert create.json()["review_sample"]["source"] == "human_review"
    assert "impact_receipt" in create.json()
    assert create.json()["impact_receipt"]["review_sample_id"] == create.json()["review_sample"]["sample_id"]

    listed = client.get(
        "/v1/ops/review-samples",
        params={"world_id": "jade_court_exam", "reviewer_id": "human_ops"},
    )
    assert listed.status_code == 200
    assert listed.json()["review_samples"]
    assert listed.json()["review_samples"][0]["reviewer_id"] == "human_ops"
    assert listed.json()["review_samples"][0]["linked_issue_codes"] == ["Q05"]
    assert "ingestion_meta" in listed.json()["review_samples"][0]

    invalid = client.post(
        "/v1/ops/review-samples",
        json={
            "chapter_id": "chapter_invalid",
            "world_id": "jade_court_exam",
            "world_version_id": "missing@0.1.0",
            "reviewer_id": "human_ops",
            "score_overall": 0.5,
            "issue_codes": ["Q05"],
            "freeform_notes": "invalid world version",
            "would_continue": False,
            "would_pay": False,
        },
    )
    assert invalid.status_code == 404


def test_review_sample_backlog_prioritizes_unreviewed_auto_reports(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "phase4_backlog.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    authoring = AuthoringService(repository)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("jade_court_romance")["worldpack"]
    pack["version"] = "0.3.0"
    pack["manifest"]["author_id"] = "phase4_backlog"
    draft = authoring.save_draft(pack)
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": False,
        "world_version_id": draft["world_version_id"],
        "world_id": version.world_id,
        "evaluation_summary": {"pass_rate": 0.0, "rewrite_rate": 1.0, "block_rate": 0.0},
        "cross_pack_summary": {"cross_pack_pass_rate": 0.4},
        "chapter_evaluations": [
            {
                "chapter_id": "chapter_backlog_1",
                "world_version_id": draft["world_version_id"],
                "session_id": "session_backlog",
                "decision": {"decision": "rewrite", "reason": "rewrite_needed"},
                "issues": [{"issue_code": "Q04", "severity": "medium", "summary": "解释句偏多", "owning_module": "writer", "evidence": []}],
                "scores": {
                    "readability": 0.7,
                    "scene_density": 0.4,
                    "character_fidelity": 0.6,
                    "causal_continuity": 0.8,
                    "pacing": 0.5,
                    "choice_distinctness": 0.7,
                    "hook_quality": 0.5,
                    "monetize_ready": 0.5,
                    "overall_score": 0.58
                },
                "hard_validator_results": {},
                "summary": "Q04 解释句偏多",
                "created_at": "2026-04-01T00:00:00+00:00"
            }
        ],
    }
    repository.save_world_version(version, publish=False)

    backlog = client.get("/v1/ops/review-sample-backlog", params={"world_id": "jade_court_romance"})
    assert backlog.status_code == 200
    assert backlog.json()["backlog"]
    assert backlog.json()["backlog"][0]["priority"] in {"high", "medium", "low"}
    assert "recommended_action" in backlog.json()["backlog"][0]
    assert "shadow_context" in backlog.json()["backlog"][0]
    assert "world_compare_signal" in backlog.json()["backlog"][0]
    assert "issue_compare_signal" in backlog.json()["backlog"][0]

    pair_backlog = client.get("/v1/ops/issue-fix-pair-backlog", params={"world_id": "jade_court_romance"})
    assert pair_backlog.status_code == 200
    assert "backlog" in pair_backlog.json()
    if pair_backlog.json()["backlog"]:
        assert "effective_coverage_count" in pair_backlog.json()["backlog"][0]

    response = client.post(
        "/v1/ops/review-samples",
        json={
            "chapter_id": "chapter_backlog_1",
            "world_id": "jade_court_romance",
            "world_version_id": draft["world_version_id"],
            "reviewer_id": "human_ops",
            "score_overall": 0.55,
            "issue_codes": ["Q04"],
            "freeform_notes": "人工确认需要压解释句。",
            "would_continue": True,
            "would_pay": False,
        },
    )
    assert response.status_code == 200
    assert "impact_receipt" in response.json()
    assert response.json()["impact_receipt"]["world_id"] == "jade_court_romance"
    assert response.json()["impact_receipt"]["chapter_id"] == "chapter_backlog_1"
    assert response.json()["impact_receipt"]["review_sample_id"] == response.json()["review_sample"]["sample_id"]
    assert response.json()["impact_receipt"]["cleared_backlog_target"] is True
    backlog_after = client.get("/v1/ops/review-sample-backlog", params={"world_id": "jade_court_romance"})
    assert backlog_after.status_code == 200
    assert all(item["chapter_id"] != "chapter_backlog_1" for item in backlog_after.json()["backlog"])

    pairs = client.get("/v1/ops/issue-fix-pairs", params={"world_id": "jade_court_romance"})
    assert pairs.status_code == 200
    if pairs.json()["issue_fix_pairs"]:
        assert "pair_quality" in pairs.json()["issue_fix_pairs"][0]
        assert "pair_source" in pairs.json()["issue_fix_pairs"][0]
