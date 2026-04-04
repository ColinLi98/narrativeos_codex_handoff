from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _seed_navigation_context(app, *, account_id: str = "acct_nav") -> dict:
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.3"
    pack["manifest"]["author_id"] = account_id
    draft = app.state.authoring_service.save_draft(pack)
    world_version_id = draft["world_version_id"]
    world_id = draft["world_id"]
    app.state.authoring_service.run_simulation_for_world_version(world_version_id)
    app.state.authoring_service.submit_for_review(world_version_id)
    app.state.analytics_service.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_id=world_id,
        world_version_id=world_version_id,
        payload_json={"reason": "subscription_required"},
    )
    case = app.state.governance_service.create_case(
        {
            "case_type": "rights",
            "target_type": "world_version",
            "target_id": world_version_id,
            "account_id": account_id,
            "world_id": world_id,
            "world_version_id": world_version_id,
            "severity": "high",
            "summary": "navigation case",
            "reviewer_id": "ops_nav",
            "owner_id": "ops_nav",
        }
    )
    alerts = app.state.ops_alerting_service.list_alerts(account_id=account_id, limit=20)
    alert_id = alerts["alerts"][0]["alert_id"]
    return {
        "account_id": account_id,
        "world_id": world_id,
        "world_version_id": world_version_id,
        "case_id": case["case_id"],
        "alert_id": alert_id,
    }


def test_ops_navigation_model_resolves_context_and_targets(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation.db"))
    app = create_app(repository=repository)
    seeded = _seed_navigation_context(app)

    payload = app.state.ops_navigation_service.navigation_model(
        account_id=seeded["account_id"],
        world_id=seeded["world_id"],
        case_id=seeded["case_id"],
        alert_id=seeded["alert_id"],
    )
    assert payload["active_context"]["account_id"] == seeded["account_id"]
    assert payload["active_context"]["world_id"] == seeded["world_id"]
    assert payload["active_context"]["case_id"] == seeded["case_id"]
    assert payload["active_context"]["alert_id"] == seeded["alert_id"]
    target_ids = {item["target_id"] for item in payload["navigation_targets"]}
    assert {"account_workspace", "release_workspace", "governance_case", "alert_detail", "investigation"} <= target_ids
    assert payload["escalation_summary"]["recommended_target"] in target_ids
    assert payload["follow_up_actions"]


def test_ops_navigation_endpoint_and_shell(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    seeded = _seed_navigation_context(app, account_id="acct_nav_api")

    shell = client.get("/app")
    assert shell.status_code == 200
    assert "统一导航 / 升级路径" in shell.text
    assert "Sync Context" in shell.text
    assert "Follow Recommendation" in shell.text

    payload = client.get(
        "/v1/ops/navigation-model",
        params={
            "account_id": seeded["account_id"],
            "world_id": seeded["world_id"],
            "case_id": seeded["case_id"],
            "alert_id": seeded["alert_id"],
        },
    )
    assert payload.status_code == 200
    json_payload = payload.json()
    assert "active_context" in json_payload
    assert "escalation_summary" in json_payload
    assert "navigation_targets" in json_payload
    assert "follow_up_actions" in json_payload


def test_ops_navigation_soft_fails_stale_alert_id(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_stale_alert.db"))
    app = create_app(repository=repository)
    seeded = _seed_navigation_context(app, account_id="acct_nav_stale")

    payload = app.state.ops_navigation_service.navigation_model(
        account_id=seeded["account_id"],
        world_id=seeded["world_id"],
        case_id=seeded["case_id"],
        alert_id="support_issue::acct_nav_stale::author_access_blocked_stale",
    )

    assert payload["active_context"]["account_id"] == seeded["account_id"]
    assert payload["active_context"]["world_id"] == seeded["world_id"]
    assert payload["active_context"]["case_id"] == seeded["case_id"]
    assert payload["active_context"]["alert_id"] is None
    assert any(item.startswith("stale_alert_ref:") for item in payload["context_warnings"])
    assert payload["linked_context"]["stale_refs"]["alert"]["status"] == "stale_or_unknown"
    handlers = {item["handler"] for item in payload["follow_up_actions"]}
    assert {"clear_stale_refs", "resync_navigation_context"} <= handlers
    target_ids = {item["target_id"] for item in payload["navigation_targets"]}
    assert "alert_detail" not in target_ids
    assert {"account_workspace", "release_workspace", "governance_case", "investigation"} <= target_ids


def test_ops_navigation_endpoint_soft_fails_stale_alert_id(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_stale_alert_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    seeded = _seed_navigation_context(app, account_id="acct_nav_stale_api")

    payload = client.get(
        "/v1/ops/navigation-model",
        params={
            "account_id": seeded["account_id"],
            "world_id": seeded["world_id"],
            "case_id": seeded["case_id"],
            "alert_id": "support_issue::acct_nav_stale_api::stale_alert",
        },
    )
    assert payload.status_code == 200
    json_payload = payload.json()
    assert json_payload["active_context"]["alert_id"] is None
    assert any(item.startswith("stale_alert_ref:") for item in json_payload["context_warnings"])
    assert json_payload["linked_context"]["stale_refs"]["alert"]["status"] == "stale_or_unknown"


def test_ops_navigation_soft_fails_stale_case_id(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_stale_case.db"))
    app = create_app(repository=repository)
    seeded = _seed_navigation_context(app, account_id="acct_nav_case")

    payload = app.state.ops_navigation_service.navigation_model(
        account_id=seeded["account_id"],
        world_id=seeded["world_id"],
        case_id="govcase_missing_case",
    )

    assert payload["active_context"]["account_id"] == seeded["account_id"]
    assert payload["active_context"]["world_id"] == seeded["world_id"]
    assert payload["active_context"]["case_id"] is None
    assert any(item.startswith("stale_case_ref:") for item in payload["context_warnings"])
    assert payload["linked_context"]["stale_refs"]["case"]["status"] == "stale_or_unknown"
    handlers = {item["handler"] for item in payload["follow_up_actions"]}
    assert {"clear_stale_refs", "resync_navigation_context"} <= handlers
    target_ids = {item["target_id"] for item in payload["navigation_targets"]}
    assert "governance_case" not in target_ids
    assert {"account_workspace", "release_workspace", "investigation"} <= target_ids


def test_ops_navigation_recovers_from_stale_world_id_using_case_context(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_stale_world.db"))
    app = create_app(repository=repository)
    seeded = _seed_navigation_context(app, account_id="acct_nav_world")

    payload = app.state.ops_navigation_service.navigation_model(
        account_id=seeded["account_id"],
        world_id="missing_world_id",
        case_id=seeded["case_id"],
    )

    assert payload["active_context"]["account_id"] == seeded["account_id"]
    assert payload["active_context"]["case_id"] == seeded["case_id"]
    assert payload["active_context"]["world_id"] == seeded["world_id"]
    assert payload["active_context"]["world_version_id"] == seeded["world_version_id"]
    assert any(item.startswith("stale_world_ref:") for item in payload["context_warnings"])
    assert payload["linked_context"]["stale_refs"]["world"]["status"] == "stale_or_unknown"
    handlers = {item["handler"] for item in payload["follow_up_actions"]}
    assert {"clear_stale_refs", "resync_navigation_context"} <= handlers
    target_ids = {item["target_id"] for item in payload["navigation_targets"]}
    assert {"account_workspace", "release_workspace", "governance_case", "investigation"} <= target_ids


def test_ops_navigation_soft_fails_stale_world_version_from_case(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_navigation_stale_world_version.db"))
    app = create_app(repository=repository)

    case = app.state.governance_service.create_case(
        {
            "case_type": "rights",
            "target_type": "world_version",
            "target_id": "missing_world@9.9.9",
            "account_id": "acct_nav_world_version",
            "world_version_id": "missing_world@9.9.9",
            "severity": "high",
            "summary": "stale world version case",
            "reviewer_id": "ops_nav",
            "owner_id": "ops_nav",
        }
    )

    payload = app.state.ops_navigation_service.navigation_model(
        account_id="acct_nav_world_version",
        case_id=case["case_id"],
    )

    assert payload["active_context"]["account_id"] == "acct_nav_world_version"
    assert payload["active_context"]["case_id"] == case["case_id"]
    assert payload["active_context"]["world_version_id"] is None
    assert payload["active_context"]["world_id"] is None
    assert any(item.startswith("stale_world_version_ref:") for item in payload["context_warnings"])
    assert payload["linked_context"]["stale_refs"]["world_version"]["status"] == "stale_or_unknown"
    handlers = {item["handler"] for item in payload["follow_up_actions"]}
    assert {"clear_stale_refs", "resync_navigation_context"} <= handlers
