from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.billing import BillingService


def _grant_author_access(repository: SQLAlchemyRepository, *, account_id: str = "acct_author") -> BillingService:
    billing = BillingService(repository)
    billing.grant_subscription(
        {
            "account_id": account_id,
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    billing.grant_wallet_credits(
        account_id=account_id,
        wallet_type="studio_credits",
        amount=20,
        tier_id="creator_pass",
    )
    return billing


def _auth_headers(client: TestClient, *, actor_id: str, actor_role: str = "author") -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={
            "actor_id": actor_id,
            "actor_role": actor_role,
            "password": "secret123",
            "account_id": actor_id,
        },
    )
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": "secret123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']['access_token']}"}


def _brief_payload(account_id: str, *, preset: str = "synthetic") -> dict:
    return {
        "genre_preset": preset,
        "world_title": f"{preset}_workflow_world",
        "lead_name": "甲",
        "counterpart_name": "乙",
        "core_premise": "用于验证 author workflow 的最小故事。",
        "life_theme": "如何在压力里继续推进创作流程",
        "locations": "中庭\n长廊\n窗边",
        "author_id": account_id,
        "account_id": account_id,
    }


def _mark_simulation_fresh(repository: SQLAlchemyRepository, world_version_id: str, *, decision: str = "pass") -> None:
    version = repository.get_world_version(world_version_id)
    version.simulation_report_json = {
        "ok": decision == "pass",
        "latest_decision": decision,
        "completed_chapters": 6,
        "stop_reason": "chapter_budget_reached",
        "evaluation_summary": {
            "pass_rate": 1.0 if decision == "pass" else 0.5,
            "rewrite_rate": 0.0 if decision == "pass" else 0.5,
            "block_rate": 0.0,
            "next_actions": [],
        },
    }
    metadata = dict((version.worldpack_json or {}).get("metadata", {}))
    revisions = list(metadata.get("revision_history", []))
    if revisions:
        revisions[-1]["simulation_delta"] = {"metric_deltas": {}}
        metadata["revision_history"] = revisions
        version.worldpack_json["metadata"] = metadata
    repository.save_world_version(version, publish=False)


def test_author_workflow_summary_blocks_create_from_brief_without_access(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_blocked.db"))
    authoring = AuthoringService(repository)

    summary = authoring.workflow_summary(account_id="acct_blocked")

    assert summary["stage"] == "brief"
    assert summary["recommended_action"] == "create_from_brief"
    assert summary["cta_actions"][0]["action_id"] == "create_from_brief"
    assert summary["cta_actions"][0]["enabled"] is False
    assert summary["blockers"]


def test_author_workflow_summary_recommends_simulate_for_auto_validated_draft(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_simulate.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(_brief_payload("acct_author"))
    summary = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])

    assert summary["stage"] == "validated"
    assert summary["recommended_action"] == "simulate"
    assert summary["validation_summary"]["ok"] is True


def test_author_draft_backfills_dialogue_assets_for_new_characters(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_asset_coverage.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(_brief_payload("acct_author"))
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    new_character = dict(worldpack["characters"][0])
    new_character["character_id"] = "supporting_new"
    new_character["display_name"] = "新角色"
    new_character["role"] = "supporting"
    worldpack["characters"].append(new_character)
    worldpack["character_memory_profiles"].pop("supporting_new", None)

    updated = authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "character_editor", "label": "补角色"},
    )

    assert updated["validation_report"]["ok"] is True
    assert "supporting_new" in updated["worldpack"]["character_memory_profiles"]


def test_author_brief_auto_enriches_100_band_structure(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_band100.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(
        {
            **_brief_payload("acct_author", preset="xianxia"),
            "target_total_chapters": 100,
            "target_total_volumes": 10,
            "target_word_count": 220000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])

    assert detail["entry_mode"] == "quick_brief"
    assert detail["requested_target_band"] == "100"
    assert detail["supported_target_band"] == "100"
    assert detail["claim_safe_band"] == "100"
    assert detail["requires_structured_longform"] is False
    assert detail["longform_readiness"]["status"] == "ready"
    assert detail["longform_structure_counts"]["character_count"] >= 8
    assert detail["longform_structure_counts"]["scene_blueprint_count"] >= 8
    assert detail["longform_structure_counts"]["location_count"] >= 6
    assert detail["longform_structure_counts"]["scene_family_count"] >= 6
    assert detail["longform_structure_counts"]["distinct_role_pair_count"] >= 6
    assert detail["quick_brief_runway_summary"]["status"] == "ready"
    assert detail["quick_brief_runway_summary"]["scene_family_count"] >= 6
    assert detail["quick_brief_runway_summary"]["distinct_role_pair_count"] >= 6
    assert detail["worldpack"]["series_plan"]["series_promises"]
    assert detail["worldpack"]["volume_plans"][0]["volume_promises"]
    assert detail["worldpack"]["arc_plans"][0]["arc_promises"]
    assert all(task["promise_targets"] for arc in detail["worldpack"]["arc_plans"] for task in arc["chapter_tasks"] if not task.get("bridge_only"))


def test_author_brief_over_100_blocks_until_structured_longform(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_band1000_blocked.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(
        {
            **_brief_payload("acct_author", preset="xianxia"),
            "target_total_chapters": 1000,
            "target_total_volumes": 18,
            "target_word_count": 2000000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    summary = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])

    assert detail["entry_mode"] == "quick_brief"
    assert detail["requested_target_band"] == "1000"
    assert detail["requires_structured_longform"] is True
    assert detail["longform_readiness"]["status"] == "blocked"
    assert any(item["key"] == "structured_longform_required" for item in detail["longform_readiness"]["blockers"])
    assert summary["recommended_action"] == "bootstrap_structured_longform"
    assert summary["longform_readiness"]["status"] == "blocked"


def test_structured_longform_bootstrap_can_raise_safe_band_to_1000(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_band1000_ready.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(
        {
            **_brief_payload("acct_author", preset="xianxia"),
            "target_total_chapters": 1000,
            "target_total_volumes": 18,
            "target_word_count": 2000000,
        }
    )
    structured = authoring.bootstrap_longform_workbench(
        draft["world_version_id"],
        mode="structured_longform",
        target_band="1000",
    )

    assert structured["entry_mode"] == "structured_longform"
    assert structured["requested_target_band"] == "1000"
    assert structured["supported_target_band"] == "1000"
    assert structured["claim_safe_band"] == "1000"
    assert structured["requires_structured_longform"] is False
    assert structured["longform_readiness"]["status"] == "ready"
    assert structured["longform_structure_counts"]["character_count"] >= 24
    assert structured["longform_structure_counts"]["scene_blueprint_count"] >= 24
    assert structured["longform_structure_counts"]["location_count"] >= 16
    assert structured["longform_structure_counts"]["scene_family_count"] >= 12
    assert structured["longform_structure_counts"]["distinct_role_pair_count"] >= 12


def test_author_workflow_summary_recommends_validate_when_validation_missing(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_validate.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(_brief_payload("acct_author"))
    version = repository.get_world_version(draft["world_version_id"])
    version.validation_report_json = {}
    repository.save_world_version(version, publish=False)

    summary = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])

    assert summary["stage"] == "draft_created"
    assert summary["recommended_action"] == "validate"


def test_author_workflow_summary_marks_stale_simulation_after_revision(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_stale.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(_brief_payload("acct_author"))
    _mark_simulation_fresh(repository, draft["world_version_id"])
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["characters"][0]["display_name"] = "改过的主角"
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "character_editor", "label": "保存角色卡"},
    )

    summary = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])

    assert summary["stage"] == "revised_after_simulation"
    assert summary["recommended_action"] == "re_simulate"
    assert summary["simulation_freshness"]["status"] == "stale"


def test_author_workflow_summary_reaches_submit_and_submitted_states(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_submit.db"))
    billing = _grant_author_access(repository, account_id="acct_author")
    authoring = AuthoringService(repository, billing_service=billing)

    draft = authoring.create_draft_from_brief(_brief_payload("acct_author"))
    _mark_simulation_fresh(repository, draft["world_version_id"], decision="pass")

    ready = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])
    assert ready["stage"] == "ready_to_submit"
    assert ready["recommended_action"] == "submit"

    authoring.submit_for_review(draft["world_version_id"])
    submitted = authoring.workflow_summary(account_id="acct_author", world_version_id=draft["world_version_id"])
    assert submitted["stage"] == "submitted"
    assert submitted["recommended_action"] == "wait_for_review"


def test_author_workflow_api_returns_expected_fields_and_stage_transitions(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_api.db"))
    _grant_author_access(repository, account_id="acct_author")
    app = create_app(repository=repository)
    client = TestClient(app)
    author_headers = _auth_headers(client, actor_id="acct_author")
    reviewer_headers = _auth_headers(client, actor_id="workflow_reviewer", actor_role="reviewer")

    draft = client.post("/v1/author/drafts/from-brief", headers=author_headers, json={"brief": _brief_payload("acct_author")})
    assert draft.status_code == 200
    draft_id = draft.json()["world_version_id"]

    validated = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}", headers=author_headers)
    assert validated.status_code == 200
    payload = validated.json()
    for key in (
        "account_id",
        "world_version_id",
        "world_id",
        "entry_mode",
        "requested_target_chapters",
        "requested_target_band",
        "supported_target_band",
        "claim_safe_band",
        "requires_structured_longform",
        "longform_readiness",
        "longform_structure_counts",
        "quick_brief_runway_summary",
        "promise_runway_summary",
        "stage",
        "recommended_action",
        "blockers",
        "stages",
        "access",
        "validation_summary",
        "simulation_summary",
        "simulation_freshness",
        "cta_actions",
    ):
        assert key in payload
    assert payload["recommended_action"] == "simulate"

    _mark_simulation_fresh(repository, draft_id, decision="pass")
    ready = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}", headers=author_headers)
    assert ready.status_code == 200
    assert ready.json()["recommended_action"] == "submit"

    submitted = client.post(f"/v1/author/drafts/{draft_id}/submit?account_id=acct_author", headers=author_headers)
    assert submitted.status_code == 200
    author_audit = client.get("/v1/ops/audit", headers=author_headers, params={"account_id": "acct_author", "limit": 20})
    assert author_audit.status_code == 403
    audit = client.get("/v1/ops/audit", headers=reviewer_headers, params={"account_id": "acct_author", "limit": 20})
    assert audit.status_code == 200
    assert any(item["action_type"] == "author_draft_submitted" for item in audit.json()["audit_logs"])
    waiting = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}", headers=author_headers)
    assert waiting.status_code == 200
    assert waiting.json()["recommended_action"] == "wait_for_review"


def test_author_simulate_api_accepts_serverless_safe_scope(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_simulate_scope.db"))
    _grant_author_access(repository, account_id="acct_author")
    app = create_app(repository=repository)
    client = TestClient(app)
    author_headers = _auth_headers(client, actor_id="acct_author")

    draft = client.post("/v1/author/drafts/from-brief", headers=author_headers, json={"brief": _brief_payload("acct_author")})
    assert draft.status_code == 200
    draft_id = draft.json()["world_version_id"]

    captured = {}

    def fake_run_simulation(world_version_id, **kwargs):
        captured.update({"world_version_id": world_version_id, **kwargs})
        return {
            "ok": True,
            "latest_decision": "pass",
            "completed_chapters": kwargs.get("max_chapters"),
            "stop_reason": "chapter_budget_reached",
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "next_actions": [],
            },
        }

    app.state.authoring_service.run_simulation_for_world_version = fake_run_simulation

    simulated = client.post(
        f"/v1/author/drafts/{draft_id}/simulate",
        headers=author_headers,
        json={"include_cross_pack": False, "max_chapters": 2},
    )

    assert simulated.status_code == 200
    assert captured["world_version_id"] == draft_id
    assert captured["include_cross_pack"] is False
    assert captured["max_chapters"] == 2
    assert simulated.json()["completed_chapters"] == 2


def test_author_longform_bootstrap_api_supports_structured_target_band(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_workflow_bootstrap_api.db"))
    _grant_author_access(repository, account_id="acct_author")
    app = create_app(repository=repository)
    client = TestClient(app)
    author_headers = _auth_headers(client, actor_id="acct_author")

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                **_brief_payload("acct_author", preset="xianxia"),
                "target_total_chapters": 1000,
                "target_total_volumes": 18,
                "target_word_count": 2000000,
            }
        },
    )
    assert draft.status_code == 200
    draft_id = draft.json()["world_version_id"]
    assert draft.json()["requires_structured_longform"] is True

    bootstrapped = client.post(
        f"/v1/author/drafts/{draft_id}/longform-bootstrap",
        headers=author_headers,
        json={"account_id": "acct_author", "mode": "structured_longform", "target_band": "1000"},
    )
    assert bootstrapped.status_code == 200
    payload = bootstrapped.json()
    assert payload["entry_mode"] == "structured_longform"
    assert payload["supported_target_band"] == "1000"
    assert payload["claim_safe_band"] == "1000"
    assert payload["longform_readiness"]["status"] == "ready"
