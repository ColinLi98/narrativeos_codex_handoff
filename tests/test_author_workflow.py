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

    draft = client.post("/v1/author/drafts/from-brief", json={"brief": _brief_payload("acct_author")})
    assert draft.status_code == 200
    draft_id = draft.json()["world_version_id"]

    validated = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}")
    assert validated.status_code == 200
    payload = validated.json()
    for key in (
        "account_id",
        "world_version_id",
        "world_id",
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
    ready = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}")
    assert ready.status_code == 200
    assert ready.json()["recommended_action"] == "submit"

    submitted = client.post(f"/v1/author/drafts/{draft_id}/submit?account_id=acct_author")
    assert submitted.status_code == 200
    waiting = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}")
    assert waiting.status_code == 200
    assert waiting.json()["recommended_action"] == "wait_for_review"
