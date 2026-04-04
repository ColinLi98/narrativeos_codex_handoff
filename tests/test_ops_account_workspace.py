from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository


def _seed_workspace_account(app, *, account_id: str = "acct_workspace") -> None:
    billing = app.state.billing_service
    analytics = app.state.analytics_service
    governance = app.state.governance_service

    billing.grant_subscription(
        {
            "account_id": account_id,
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
        }
    )
    analytics.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_version_id="urban_mystery_lotus_lane@0.1.0",
        payload_json={"reason": "subscription_required"},
    )
    governance.apply_restriction(
        {
            "restriction_type": "author_access_block",
            "account_id": account_id,
            "case_type": "abuse",
            "severity": "high",
            "summary": "workspace restriction",
            "reviewer_id": "ops_workspace",
        }
    )


def test_ops_account_workspace_summarizes_blockers_and_actions(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_workspace.db"))
    app = create_app(repository=repository)
    _seed_workspace_account(app)

    payload = app.state.ops_account_workspace_service.account_workspace(account_id="acct_workspace", limit=12)

    assert payload["workspace_summary"]["health_status"] == "critical"
    assert payload["workspace_summary"]["active_restriction_count"] >= 1
    assert payload["workspace_summary"]["support_issue_count"] >= 1
    assert payload["top_blockers"]
    action_handlers = {item["handler"] for item in payload["action_pack"]}
    assert "run_investigation" in action_handlers
    assert "retry_subscription_payment" in action_handlers or "grant_subscription" in action_handlers
    assert payload["operator_timeline"]
    assert payload["linked_context"]["governance_case_ids"]


def test_ops_account_workspace_endpoint_and_shell(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_workspace_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    _seed_workspace_account(app, account_id="acct_workspace_api")

    shell = client.get("/app")
    assert shell.status_code == 200
    assert "账户详情 / 权益 / 订阅 / 钱包统一排查页" in shell.text
    assert "operator workspace summary" in shell.text
    assert "quick actions" in shell.text

    payload = client.get("/v1/ops/accounts/acct_workspace_api/workspace")
    assert payload.status_code == 200
    json_payload = payload.json()
    assert "workspace_summary" in json_payload
    assert "wallet_posture" in json_payload
    assert "entitlement_posture" in json_payload
    assert "action_pack" in json_payload
    assert "operator_timeline" in json_payload
