import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.billing import BillingService
from src.narrativeos.services.governance import GovernanceService
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_inference import LearnedInferenceService
from src.narrativeos.eval.learned_shadow import LearnedShadowService
from src.narrativeos.services.review import ReviewService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_runtime_asset_inventory_doc_exists():
    inventory_path = Path(__file__).resolve().parents[1] / "docs" / "runtime_asset_inventory.md"
    assert inventory_path.exists()
    content = inventory_path.read_text(encoding="utf-8")
    assert "demo/romance" in content or "demo" in content
    assert "单作品" in content


def test_worldpack_registry_loads_multiple_published_packs():
    registry = FileSystemWorldRegistry()
    worlds = registry.list_worldpacks()
    assert len(worlds) >= 3
    world_ids = {item["world_id"] for item in worlds}
    assert "jade_court_exam" in world_ids
    assert "urban_mystery_lotus_lane" in world_ids
    runtime = registry.get_runtime_bundle("urban_mystery_lotus_lane@0.1.0")
    assert runtime.event_atoms
    assert runtime.initial_state.world_id == "urban_mystery_lotus_lane"


def test_repository_default_database_url_honors_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env_override_beta.db")
    from importlib import reload
    import src.narrativeos.persistence.repositories as repositories

    reloaded = reload(repositories)
    assert reloaded.DEFAULT_DATABASE_URL == "sqlite:///env_override_beta.db"


def test_postgres_url_and_schema_loader_helpers():
    from src.narrativeos.persistence.db import (
        POSTGRES_SCHEMA_PATH,
        _split_sql_statements,
        is_postgres_url,
        load_postgres_schema_sql,
    )

    assert is_postgres_url("postgresql://user:pass@localhost/db")
    assert is_postgres_url("postgres://user:pass@localhost/db")
    assert not is_postgres_url("sqlite:///beta.db")
    sql_text = load_postgres_schema_sql(POSTGRES_SCHEMA_PATH)
    statements = _split_sql_statements(sql_text)
    assert any("create table if not exists worlds" in statement for statement in statements)
    assert any("create table if not exists world_versions" in statement for statement in statements)


def test_migration_files_are_discoverable():
    from src.narrativeos.persistence.migrations import MIGRATIONS_DIR, list_migration_files

    files = list_migration_files(MIGRATIONS_DIR)
    assert files
    assert files[0].name.startswith("0001_")


def test_schema_fingerprints_match_repo_schema_and_migrations():
    from src.narrativeos.persistence.db import POSTGRES_SCHEMA_PATH
    from src.narrativeos.persistence.migrations import MIGRATIONS_DIR, migrations_fingerprint, schema_file_fingerprint

    assert schema_file_fingerprint(POSTGRES_SCHEMA_PATH) == migrations_fingerprint(MIGRATIONS_DIR)


def test_repo_alembic_scaffold_is_discoverable_and_stampable(tmp_path: Path):
    from sqlalchemy import create_engine

    from src.narrativeos.persistence.migrations import (
        ALEMBIC_INI_PATH,
        ALEMBIC_SCRIPT_LOCATION,
        alembic_history,
        inspect_alembic_state,
        stamp_alembic_head,
    )

    assert ALEMBIC_INI_PATH.exists()
    assert ALEMBIC_SCRIPT_LOCATION.exists()

    history = alembic_history()
    assert history["enabled"] is True
    assert history["head_revision"] == "20260404_0012"
    assert history["history"]

    engine = create_engine(f"sqlite:///{tmp_path / 'alembic_lifecycle.db'}", future=True)
    before = inspect_alembic_state(engine)
    assert before["head_revision"] == "20260404_0012"
    assert before["status"] == "not_stamped"

    stamped = stamp_alembic_head(str(engine.url))
    assert stamped["enabled"] is True
    assert stamped["target_revision"] == "20260404_0012"

    after = inspect_alembic_state(engine)
    assert after["status"] == "at_head"
    assert after["current_revision"] == "20260404_0012"


def test_schema_lifecycle_can_report_pending_and_apply_temp_migrations(tmp_path: Path):
    from sqlalchemy import create_engine

    from src.narrativeos.persistence.migrations import bootstrap_schema_lifecycle, inspect_schema_lifecycle

    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_init.sql").write_text(
        "create table if not exists demo_table (id integer primary key, name text);",
        encoding="utf-8",
    )
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text(
        "create table if not exists demo_table (id integer primary key, name text);",
        encoding="utf-8",
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}", future=True)

    before = inspect_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path)
    assert before["status"] == "pending_migrations"
    assert before["pending_versions"] == ["0001_init"]
    assert "alembic" in before

    dry_run = bootstrap_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path, apply=False)
    assert dry_run["dry_run"] is True
    assert dry_run["applied_migrations"] == []

    applied = bootstrap_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path, apply=True)
    assert applied["applied_migrations"] == ["0001_init"]
    assert applied["after"]["status"] == "up_to_date"


def test_authoring_service_can_save_validate_simulate_and_submit(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_authoring.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.2.0"
    pack["manifest"]["author_id"] = "author_test"

    draft = authoring.save_draft(pack)
    assert draft["status"] == "draft"
    assert draft["validation_report"]["ok"]

    simulation = authoring.run_simulation("urban_mystery_lotus_lane")
    assert "completed_chapters" in simulation
    assert "evaluation_summary" in simulation
    assert "cross_pack_summary" in simulation
    assert "metric_deltas" in simulation
    assert "top_failing_packs" in simulation
    submit = authoring.submit_for_review(draft["world_version_id"])
    assert submit["status"] == "submitted"


def test_authoring_service_can_create_draft_from_brief(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_author_brief.db"))
    authoring = AuthoringService(repository)
    template = authoring.get_brief_template()
    assert template["genre_presets"]

    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "xianxia",
            "world_title": "霜灯旧誓",
            "lead_name": "沈照",
            "counterpart_name": "叶青烛",
            "core_premise": "旧誓反噬时，两个人不得不重新决定谁来承担后果。",
            "life_theme": "誓愿与私心能否同时被承担",
            "locations": "偏殿\n石阶\n山门",
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    assert draft["status"] == "draft"
    assert detail["worldpack"]["title"] == "霜灯旧誓"
    assert detail["worldpack"]["manifest"]["genres"]
    assert len(detail["worldpack"]["characters"]) >= 2
    assert detail["revision_history"][0]["source"] == "brief_create"
    assert detail["latest_diff_summary"]["summary_text"]
    assert "validation_drilldown" in detail


def test_authoring_service_can_update_character_and_scene_then_resimulate(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_author_detail.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "urban_mystery",
            "world_title": "旧巷回声",
            "lead_name": "江屹",
            "counterpart_name": "周岚",
            "core_premise": "一条旧巷里，越想压住的真相越会回来收债。",
            "life_theme": "真话是否值得承担失去",
            "locations": "旧巷\n便利店门口\n天桥下",
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["characters"][0]["display_name"] = "江屿"
    worldpack["characters"][0]["wound_profile"]["core_wound"] = "被误解"
    worldpack["scene_blueprints"][0]["beats_template"] = ["夜巷相遇", "停顿", "逼问", "留下回响"]
    updated = authoring.update_draft(draft["world_version_id"], worldpack)
    simulation = authoring.run_simulation_for_world_version(draft["world_version_id"])

    assert updated["worldpack"]["characters"][0]["display_name"] == "江屿"
    assert updated["worldpack"]["scene_blueprints"][0]["beats_template"][1] == "停顿"
    assert updated["revision_history"]
    assert updated["latest_diff_summary"]["changed_sections"]
    assert "diff_drilldown" in updated
    assert updated["diff_drilldown"]["revisions"]
    assert "characters" in updated["latest_diff_summary"]["changed_sections"] or "scene_blueprints" in updated["latest_diff_summary"]["changed_sections"]
    assert "metric_deltas" in simulation
    assert "cross_pack_summary" in simulation
    assert "chapter_trace" in simulation
    assert "simulation_drilldown" in simulation
    assert simulation["simulation_drilldown"]["chapter_breakdown"]
    assert simulation["simulation_drilldown"]["weakest_chapters"]
    assert "issue_focus_queue" in simulation["simulation_drilldown"]


def test_authoring_service_tracks_capability_revision_history(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_author_history.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "实验草稿",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "一个用于测试版本历史的最小世界。",
            "life_theme": "如何在压力里说真话",
            "locations": "中庭\n长廊\n窗边",
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["voice_profiles"]["lead"]["directness"] = 0.72
    updated = authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "capability_editor", "label": "保存能力配置"},
    )
    assert updated["revision_history"][-1]["source"] == "capability_editor"
    assert "voice_profiles" in updated["latest_diff_summary"]["changed_sections"]
    assert updated["diff_drilldown"]["recommended_next_actions"]
    assert updated["diff_drilldown"]["simulation_freshness"]["status"] in {"missing", "fresh", "stale"}


def test_long_route_simulation_can_extend_beyond_minimal_static_pool(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_long_route_continuation.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)

    report = authoring.run_simulation_for_world_version(
        registry.get_published_world("synthetic_min_pack")["world_version_id"],
        include_cross_pack=False,
        max_chapters=12,
        min_end_turn_override=12,
    )

    assert report["completed_chapters"] >= 3
    assert report["chapter_trace"]


def test_long_route_simulation_can_extend_jade_court_romance_past_route_exhaustion(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_long_route_romance.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)

    report = authoring.run_simulation_for_world_version(
        registry.get_published_world("jade_court_romance")["world_version_id"],
        include_cross_pack=False,
        max_chapters=12,
        min_end_turn_override=12,
    )

    assert report["completed_chapters"] >= 6
    assert report["stop_reason"] == "chapter_budget_reached"


def test_authoring_service_can_persist_style_pacing_hook_controls(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_author_style_panel.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "urban_mystery",
            "world_title": "旧巷风格面板",
            "lead_name": "江屹",
            "counterpart_name": "周岚",
            "core_premise": "把风格 / 节奏 / hook 控制直接暴露给 Author。",
            "life_theme": "真话是否值得承担失去",
            "locations": "旧巷\n便利店门口\n天桥下",
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["narrative_style_pack"]["tonal_lexicon"] = ["旧账", "回声", "逼问"]
    worldpack["narrative_style_pack"]["hook_templates"] = ["夜色先退了一步，可真正追上来的，是那句还没说完的话。"]
    worldpack["narrative_style_pack"]["thematic_axis_labels"] = {"truth": "真相与揭露", "suspense": "悬疑与压迫"}
    worldpack["dialogue_realism_policy"]["min_turns"] = 3
    worldpack["dialogue_realism_policy"]["max_turns"] = 4
    worldpack["dialogue_realism_policy"]["minimum_exchanges"] = 2
    worldpack["dialogue_realism_policy"]["turn_pattern"] = ["speaker", "reaction", "reply", "echo"]
    default_contract_key = next(iter(worldpack["scene_realization_contracts"]))
    worldpack["scene_realization_contracts"][default_contract_key]["scene_hooks"] = {
        "truth_trial": ["等这场话停下来时，真正要追上来的，是那句没说尽的话。"]
    }

    updated = authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "capability_editor", "label": "保存风格 / 节奏 / Hook"},
    )
    assert updated["worldpack"]["narrative_style_pack"]["tonal_lexicon"][0] == "旧账"
    assert updated["worldpack"]["narrative_style_pack"]["hook_templates"][0].startswith("夜色先退了一步")
    assert updated["worldpack"]["dialogue_realism_policy"]["min_turns"] == 3
    assert updated["worldpack"]["dialogue_realism_policy"]["turn_pattern"][-1] == "echo"
    assert "scene_realization_contracts" in updated["latest_diff_summary"]["changed_sections"]


def test_billing_service_quotes_and_meters_continue(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_billing.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam"}).json()
    quote = client.get(f"/v1/reader/sessions/{session['session_id']}/quote")
    assert quote.status_code == 200
    assert "access_tier" in quote.json()

    billing = BillingService(repository)
    meter = billing.meter(
        {
            "session_id": session["session_id"],
            "world_version_id": session["world_version_id"],
            "action_type": "continue_story",
            "usage_units": 1.0,
            "estimated_cost": 0.25,
            "model_policy_version": "beta-test",
        }
    )
    assert meter["action_type"] == "continue_story"


def test_billing_service_can_grant_and_consume_credits(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_billing_consume.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "reader_id": "reader_test"}).json()
    billing = BillingService(repository)
    granted = billing.grant_entitlement(
        {
            "reader_id": "reader_test",
            "world_id": "jade_court_exam",
            "entitlement_type": "credits",
            "balance": 3,
        }
    )
    assert granted["balance"] == 3

    with repository.SessionLocal() as db:
        row = db.get(SessionRow, session["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()

    access = billing.access_check(session["session_id"], reader_id="reader_test")
    assert access["reason"] == "credits_balance"
    assert access["status"] == "active"
    consumed = billing.consume_entitlement(session["session_id"], reader_id="reader_test", access=access)
    assert consumed["reason"] == "credits_consumed"
    assert consumed["balance"] == 2.0
    assert consumed["status"] == "active"


def test_billing_service_marks_expired_and_exhausted_entitlements(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_billing_expired.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "reader_id": "reader_expired"}).json()
    with repository.SessionLocal() as db:
        row = db.get(SessionRow, session["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()

    billing = BillingService(repository)
    billing.grant_entitlement(
        {
            "reader_id": "reader_expired",
            "world_id": "jade_court_exam",
            "entitlement_type": "credits",
            "balance": 0,
        }
    )
    exhausted = billing.access_check(session["session_id"], reader_id="reader_expired")
    assert exhausted["required"] is True
    assert exhausted["reason"] == "credits_exhausted"
    assert exhausted["status"] == "exhausted"

    billing.grant_entitlement(
        {
            "reader_id": "reader_expired",
            "world_id": "jade_court_exam",
            "entitlement_type": "world_pass",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
    )
    expired = billing.access_check(session["session_id"], reader_id="reader_expired")
    assert expired["required"] is True
    assert expired["reason"] in {"entitlement_expired", "credits_exhausted"}
    entitlements = billing.list_entitlements_for_reader("reader_expired", world_id="jade_court_exam")["entitlements"]
    assert any(item["status"] == "expired" for item in entitlements)
    assert any(item["status"] == "exhausted" for item in entitlements)


def test_billing_service_honors_world_pass_and_subscriber(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_billing_entitlements.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "reader_id": "reader_sub"}).json()
    with repository.SessionLocal() as db:
        row = db.get(SessionRow, session["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()

    billing = BillingService(repository)
    billing.grant_entitlement({"reader_id": "reader_sub", "world_id": "jade_court_exam", "entitlement_type": "world_pass"})
    access = billing.access_check(session["session_id"], reader_id="reader_sub")
    assert access["required"] is False
    assert access["entitlement_type"] == "world_pass"

    other = client.post("/v1/reader/sessions", json={"world_id": "jade_court_romance", "reader_id": "reader_sub"}).json()
    with repository.SessionLocal() as db:
        row = db.get(SessionRow, other["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()
    blocked = billing.access_check(other["session_id"], reader_id="reader_sub")
    assert blocked["required"] is True

    billing.grant_entitlement({"reader_id": "reader_sub", "entitlement_type": "subscriber"})
    subscriber_access = billing.access_check(other["session_id"], reader_id="reader_sub")
    assert subscriber_access["required"] is False
    assert subscriber_access["entitlement_type"] == "subscriber"


def test_review_publish_and_rollback_flow(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_review.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository)

    pack = registry.get_published_world("xianxia_forgotten_vow")["worldpack"]
    pack["version"] = "0.2.1"
    pack["manifest"]["author_id"] = "ops_test"
    draft = authoring.save_draft(pack)
    authoring.run_simulation("xianxia_forgotten_vow")
    submitted = authoring.submit_for_review(draft["world_version_id"])

    queue = review.queue()
    assert any(item["asset_id"] == draft["world_version_id"] for item in queue)

    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": True,
        "latest_decision": "pass",
        "evaluation_summary": {"pass_rate": 1.0, "rewrite_rate": 0.0, "block_rate": 0.0},
        "cross_pack_summary": {
            "cross_pack_pass_rate": 0.5,
            "top_failing_packs": [],
            "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": [], "world_deltas": {}},
            "worlds": [],
        },
    }
    repository.save_world_version(version, publish=False)

    published = review.publish(draft["world_version_id"], reviewer_id="reviewer_1")
    assert published["status"] == "published"

    history = review.world_history("xianxia_forgotten_vow")
    assert history["review_history"]
    assert any(item["status"] == "published" for item in history["review_history"])
    assert history["review_timeline"]
    assert history["review_summary"]["latest_published_world_version_id"] == draft["world_version_id"]
    assert history["quality_trend_summary"]["latest_world_version_id"] == draft["world_version_id"]

    rollback = review.rollback("xianxia_forgotten_vow", "xianxia_forgotten_vow@0.1.0", reviewer_id="reviewer_1")
    assert rollback["latest_version"] == "xianxia_forgotten_vow@0.1.0"
    history = review.world_history("xianxia_forgotten_vow")
    assert history["rollback_history"]
    assert any(item["status"] == "rolled_back" for item in history["rollback_history"])
    assert any(item["timeline_group"] == "rollback" for item in history["review_timeline"])
    assert history["review_summary"]["latest_rollback_target_world_version_id"] == "xianxia_forgotten_vow@0.1.0"
    assert history["rollback_drilldown"]
    assert history["rollback_summary"]["latest_target_world_version_id"] == "xianxia_forgotten_vow@0.1.0"
    assert "delta_vs_previous" in history["quality_trend"][0]


def test_publish_can_be_blocked_by_eval_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_review_block.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository)

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.9"
    pack["manifest"]["author_id"] = "ops_test"
    draft = authoring.save_draft(pack)
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": False,
        "latest_decision": "block",
        "evaluation_summary": {"block_rate": 1.0},
    }
    repository.save_world_version(version, publish=False)

    import pytest

    with pytest.raises(ValueError):
        review.publish(draft["world_version_id"], reviewer_id="reviewer_1")
    history = review.world_history("urban_mystery_lotus_lane")
    assert any(item["status"] == "publish_blocked" for item in history["review_history"])
    blocked_entry = next(item for item in history["review_timeline"] if item["status"] == "publish_blocked")
    assert blocked_entry["publish_gate_errors"]
    assert draft["world_version_id"] in history["quality_trend_summary"]["blocked_version_ids"]


def test_publish_can_be_blocked_without_cross_pack_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_review_no_cross_pack.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository)

    pack = registry.get_published_world("jade_court_exam")["worldpack"]
    pack["version"] = "0.9.8"
    pack["manifest"]["author_id"] = "ops_test"
    draft = authoring.save_draft(pack)
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": True,
        "latest_decision": "pass",
        "evaluation_summary": {"pass_rate": 1.0, "rewrite_rate": 0.0, "block_rate": 0.0},
    }
    repository.save_world_version(version, publish=False)

    import pytest

    with pytest.raises(ValueError):
        review.publish(draft["world_version_id"], reviewer_id="reviewer_1")


def test_world_status_contains_recent_reviews_and_checklist_reason(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_ops_status.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository, analytics_service=AnalyticsService(repository))
    analytics = AnalyticsService(repository)
    pack = registry.get_published_world("jade_court_exam")["worldpack"]
    pack["version"] = "0.9.7"
    pack["manifest"]["author_id"] = "ops_test"
    draft = authoring.save_draft(pack)
    authoring.run_simulation("jade_court_exam")
    authoring.submit_for_review(draft["world_version_id"])
    analytics.track(
        "payment_required",
        reader_id="reader_ops",
        session_id="session_ops",
        world_id="jade_court_exam",
        world_version_id=draft["world_version_id"],
        access_tier="paid",
        payload_json={"reason": "credits_exhausted"},
    )
    status = review.world_status("jade_court_exam")
    assert status["recent_reviews"]
    assert status["publish_checklist"]
    assert "reason" in status["publish_checklist"][0]
    assert "owner" in status["publish_checklist"][0]
    assert "evidence" in status["publish_checklist"][0]
    assert "next_action" in status["publish_checklist"][0]
    assert "publish_checklist_summary" in status
    assert "recent_reviews_drilldown" in status
    assert "risk_summary" in status
    assert "publish_gate_errors" in status["risk_summary"]
    assert status["recent_entitlement_events"]
    assert status["publish_checklist_summary"]["total"] == len(status["publish_checklist"])


def test_governance_service_can_create_update_and_summarize_cases(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_governance.db"))
    billing = BillingService(repository)
    governance = GovernanceService(repository, billing_service=billing)

    billing.grant_subscription(
        {
            "account_id": "acct_governance",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
        }
    )

    created = governance.create_case(
        {
            "case_type": "rights",
            "target_type": "account",
            "target_id": "acct_governance",
            "account_id": "acct_governance",
            "severity": "high",
            "summary": "账号投诉无法继续阅读",
            "description": "需要检查 subscription lifecycle。",
            "reviewer_id": "ops_1",
        }
    )
    assert created["case_type"] == "rights"
    assert created["status"] == "open"

    updated = governance.update_case_status(
        created["case_id"],
        status="escalated",
        reviewer_id="ops_2",
        resolution_notes="升级到 rights queue 继续处理。",
    )
    assert updated["status"] == "escalated"
    assert updated["latest_transition"]["status"] == "escalated"

    listing = governance.list_cases(account_id="acct_governance")
    assert listing["cases"]
    assert listing["governance_summary"]["escalated_case_count"] == 1

    snapshot = governance.account_snapshot(account_id="acct_governance")
    assert snapshot["governance_cases"]
    assert snapshot["recommended_case_prefills"]


def test_governance_restrictions_can_block_access_and_export(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_governance_restrictions.db"))
    billing = BillingService(repository)
    governance = GovernanceService(repository, billing_service=billing)

    billing.grant_subscription(
        {
            "account_id": "acct_restricted",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )

    restricted_case = governance.apply_restriction(
        {
            "restriction_type": "author_access_block",
            "account_id": "acct_restricted",
            "case_type": "abuse",
            "severity": "high",
            "summary": "临时冻结 author access",
            "reviewer_id": "ops_lock",
        }
    )
    restriction = restricted_case["restriction"]
    assert restriction["status"] == "active"
    assert billing.access_check_author(account_id="acct_restricted", action_name="simulate")["reason"] == "manual_restriction_active"

    checkout_case = governance.apply_restriction(
        {
            "restriction_type": "checkout_block",
            "account_id": "acct_restricted",
            "case_type": "rights",
            "severity": "medium",
            "summary": "暂停 checkout",
            "reviewer_id": "ops_lock",
        }
    )
    import pytest

    with pytest.raises(ValueError):
        billing.start_checkout(account_id="acct_restricted", tier_id="play_pass", provider="web_stub")

    export_payload = governance.governance_audit_export(account_id="acct_restricted")
    assert export_payload["cases"]
    assert export_payload["restrictions"]

    released = governance.release_restriction(
        checkout_case["restriction"]["restriction_id"],
        reviewer_id="ops_unlock",
        release_reason="问题已处理",
    )
    assert released["restriction"]["status"] == "released"


def test_governance_service_can_escalate_support_issue_and_return_case_detail(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_governance_escalation.db"))
    billing = BillingService(repository)
    governance = GovernanceService(repository, billing_service=billing)

    support_issue = {
        "issue_id": "missing_subscription_123",
        "issue_type": "missing_subscription",
        "severity": "high",
        "title": "No active subscription for blocked account",
        "summary": "账号没有有效订阅。",
        "reason": "subscription_required",
        "detected_at": "2026-04-01T10:00:00+00:00",
        "surfaces": ["reader"],
        "evidence": {},
        "related_objects": {},
        "suggested_operator_actions": [],
    }

    original_lookup = governance.billing.support_issue_lookup
    governance.billing.support_issue_lookup = lambda account_id, limit=50: {"support_issues": [support_issue], "support_summary": {}}
    try:
        detail = governance.escalate_support_issue(
            account_id="acct_escalate",
            issue_id="missing_subscription_123",
            reviewer_id="ops_escalate",
        )
        assert detail["support_issue_ids"] == ["missing_subscription_123"]
        assert detail["linked_support_issues"][0]["issue_id"] == "missing_subscription_123"
        again = governance.escalate_support_issue(
            account_id="acct_escalate",
            issue_id="missing_subscription_123",
            reviewer_id="ops_escalate",
        )
        assert again["case_id"] == detail["case_id"]
        case_detail = governance.case_detail(detail["case_id"])
        assert case_detail["detail_summary"]["linked_support_issue_count"] == 1
    finally:
        governance.billing.support_issue_lookup = original_lookup


def test_unified_investigation_trace_can_link_account_world_and_case(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_ops_investigation.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.6"
    pack["manifest"]["author_id"] = "acct_investigation"
    draft = app.state.authoring_service.save_draft(pack)
    world_version_id = draft["world_version_id"]
    app.state.authoring_service.run_simulation_for_world_version(world_version_id)
    app.state.authoring_service.submit_for_review(world_version_id)

    checkout = app.state.billing_service.start_checkout(
        account_id="acct_investigation",
        tier_id="creator_pass",
        provider="web_stub",
    )
    app.state.billing_service.ingest_checkout_webhook(
        {
            "provider": "web_stub",
            "provider_event_id": "evt_unified_trace_complete",
            "event_type": "checkout_session_completed",
            "account_id": "acct_investigation",
            "checkout_session_id": checkout["checkout_session_id"],
            "payload": {"source": "beta_platform"},
        }
    )
    app.state.analytics_service.track(
        "payment_required",
        reader_id="acct_investigation",
        account_id="acct_investigation",
        session_id="session_investigation",
        world_id=draft["world_id"],
        world_version_id=world_version_id,
        payload_json={"reason": "subscription_required"},
    )
    app.state.observability_service.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="fallback",
        world_id=draft["world_id"],
        world_version_id=world_version_id,
        session_id="session_investigation",
        account_id="acct_investigation",
        candidate_batch={"debug": {"provider": "llm", "backend_error": "timeout", "backend_routing": {"selected_provider": "local"}}},
        reader_view={"body": "runtime trace"},
    )
    case = app.state.governance_service.create_case(
        {
            "case_type": "rights",
            "target_type": "world_version",
            "target_id": world_version_id,
            "account_id": "acct_investigation",
            "world_id": draft["world_id"],
            "world_version_id": world_version_id,
            "severity": "high",
            "summary": "统一排查需要串起 world/account/case",
            "reviewer_id": "ops_trace",
            "description": "traceability integration",
        }
    )
    repository.save_review_record(
        {
            "asset_type": "world_version",
            "asset_id": world_version_id,
            "status": "publish_blocked",
            "reviewer_id": "ops_trace",
            "notes": json.dumps(
                {
                    "world_id": draft["world_id"],
                    "world_version_id": world_version_id,
                    "latest_decision": "block",
                    "publish_gate_errors": ["traceability_test_gate"],
                    "risk_summary": {"publish_gate_errors": ["traceability_test_gate"]},
                }
            ),
        }
    )

    payload = client.get(
        f"/v1/ops/investigations/accounts/acct_investigation",
        params={"world_version_id": world_version_id, "case_id": case["case_id"], "limit": 50},
    )
    assert payload.status_code == 200
    bundle = payload.json()
    assert bundle["filters"]["account_id"] == "acct_investigation"
    assert bundle["filters"]["world_version_id"] == world_version_id
    assert bundle["filters"]["case_id"] == case["case_id"]
    assert world_version_id in bundle["linked_entities"]["world_version_ids"]
    assert case["case_id"] in bundle["linked_entities"]["governance_case_ids"]
    source_types = {item["source_type"] for item in bundle["trace_timeline"]}
    assert {"billing_lifecycle_event", "governance_case", "review_timeline", "runtime_receipt"} <= source_types
    assert all(item["account_id"] == "acct_investigation" for item in bundle["trace_timeline"])
    assert any(item.get("world_version_id") == world_version_id for item in bundle["trace_timeline"])
    assert any(item.get("case_id") == case["case_id"] for item in bundle["trace_timeline"])


def test_authoring_simulation_can_include_learned_evaluation_summary_when_artifact_exists(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_learned_shadow.db"))
    artifact_dir = tmp_path / "artifacts"
    registry = FileSystemWorldRegistry()

    trainer_authoring = AuthoringService(repository, registry=registry)
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.8.0"
    pack["manifest"]["author_id"] = "shadow_train"
    draft = trainer_authoring.save_draft(pack)
    trainer_authoring.run_simulation_for_world_version(draft["world_version_id"])
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )

    authoring = AuthoringService(
        repository,
        registry=registry,
        learned_inference_service=LearnedInferenceService(artifact_dir),
        learned_shadow_service=LearnedShadowService(artifact_dir, learned_inference_service=LearnedInferenceService(artifact_dir)),
    )
    simulation = authoring.run_simulation_for_world_version(draft["world_version_id"])
    assert "learned_evaluation_summary" in simulation
    assert simulation["learned_evaluation_summary"]["available"] is True
    assert "agreement_rate" in simulation["learned_evaluation_summary"]
    assert "learned_shadow_summary" in simulation
    assert simulation["learned_shadow_summary"]["status"] in {"warming_up", "candidate", "not_ready"}
