from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _make_app(tmp_path: Path, name: str):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / name))
    app = create_app(repository=repository)
    return app, repository


def _seed_ops_alert_data(app, *, account_id: str = "acct_ops_alert") -> dict:
    billing = app.state.billing_service
    analytics = app.state.analytics_service
    observability = app.state.observability_service
    governance = app.state.governance_service
    authoring = app.state.authoring_service
    async_jobs = app.state.async_job_service
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.5"
    pack["manifest"]["author_id"] = account_id
    draft = authoring.save_draft(pack)
    world_version_id = draft["world_version_id"]
    world_id = draft["world_id"]

    checkout = billing.start_checkout(account_id=account_id, tier_id="creator_pass", provider="web_stub")
    billing.ingest_checkout_webhook(
        {
            "provider": "web_stub",
            "provider_event_id": f"evt_alert_complete_{account_id}",
            "event_type": "checkout_session_completed",
            "account_id": account_id,
            "checkout_session_id": checkout["checkout_session_id"],
            "payload": {"source": "ops_alert_test"},
        }
    )
    billing.ingest_checkout_webhook(
        {
            "provider": "web_stub",
            "provider_event_id": f"evt_alert_failed_{account_id}",
            "event_type": "subscription_payment_failed",
            "account_id": account_id,
            "subscription_id": checkout.get("subscription_id"),
            "payload": {"source": "ops_alert_test"},
        }
    )
    analytics.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_id=world_id,
        world_version_id=world_version_id,
        payload_json={"reason": "subscription_required"},
    )
    analytics.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_id=world_id,
        world_version_id=world_version_id,
        payload_json={"reason": "subscription_required"},
    )
    observability.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="fallback",
        world_id=world_id,
        world_version_id=world_version_id,
        session_id=f"session_{account_id}",
        account_id=account_id,
        candidate_batch={
            "debug": {
                "provider": "llm",
                "backend_error": "provider_down",
                "backend_routing": {"selected_provider": "local", "fallback_used": True},
            }
        },
        reader_view={"body": "ops alert runtime sample"},
    )
    case = governance.apply_restriction(
        {
            "restriction_type": "checkout_block",
            "account_id": account_id,
            "case_type": "rights",
            "severity": "high",
            "summary": "ops alert governance restriction",
            "reviewer_id": "ops_alert",
            "world_version_id": world_version_id,
        }
    )
    async_jobs.enqueue_job(
        job_type="runtime_backup",
        payload={"label": "ops_alert_queue"},
        requested_by="ops_alert",
        account_id=account_id,
    )
    return {
        "account_id": account_id,
        "world_version_id": world_version_id,
        "world_id": world_id,
        "case_id": case["case_id"],
    }


def test_ops_alert_feed_includes_runtime_support_governance_and_async_signals(tmp_path: Path):
    app, _repository = _make_app(tmp_path, "ops_alert_feed.db")
    seeded = _seed_ops_alert_data(app)

    payload = app.state.ops_alerting_service.list_alerts(account_id=seeded["account_id"], limit=20)

    assert payload["summary"]["actionable_alert_count"] >= 4
    categories = {item["category"] for item in payload["alerts"]}
    assert {"runtime", "support", "governance", "async_jobs"} <= categories
    assert all(item["recommended_actions"] for item in payload["alerts"])
    assert all("standard_operating_path" in item for item in payload["alerts"])


def test_ops_alert_detail_and_status_update_are_persisted(tmp_path: Path):
    app, _repository = _make_app(tmp_path, "ops_alert_detail.db")
    seeded = _seed_ops_alert_data(app, account_id="acct_alert_status")

    feed = app.state.ops_alerting_service.list_alerts(account_id=seeded["account_id"], limit=20)
    support_alert = next(item for item in feed["alerts"] if item["category"] == "support")

    detail = app.state.ops_alerting_service.alert_detail(support_alert["alert_id"], account_id=seeded["account_id"])
    assert detail["alert"]["investigation_ref"]["account_id"] == seeded["account_id"]
    assert detail["standard_response_bundle"]["support_issue"]["issue_id"]
    assert detail["investigation_bundle"]["filters"]["account_id"] == seeded["account_id"]

    updated = app.state.ops_alerting_service.update_alert_status(
        support_alert["alert_id"],
        status="acknowledged",
        reviewer_id="ops_alert",
        note="triaging support alert",
        account_id=seeded["account_id"],
    )
    assert updated["alert"]["status"] == "acknowledged"
    assert updated["alert"]["state"]["note"] == "triaging support alert"


def test_ops_alert_endpoints_and_shell(tmp_path: Path):
    app, _repository = _make_app(tmp_path, "ops_alert_api.db")
    client = TestClient(app)
    seeded = _seed_ops_alert_data(app, account_id="acct_alert_api")

    shell = client.get("/app")
    assert shell.status_code == 200
    assert "Alert Center" in shell.text
    assert "主动告警与标准处置" in shell.text
    assert "Refresh Alerts" in shell.text
    assert "Acknowledge Alert" in shell.text
    assert "Resolve Alert" in shell.text

    feed = client.get("/v1/ops/alerts", params={"account_id": seeded["account_id"], "limit": 20})
    assert feed.status_code == 200
    assert feed.json()["alerts"]
    alert_id = feed.json()["alerts"][0]["alert_id"]

    detail = client.get(f"/v1/ops/alerts/{alert_id}", params={"account_id": seeded["account_id"]})
    assert detail.status_code == 200
    assert "alert" in detail.json()
    assert "standard_response_bundle" in detail.json()

    updated = client.post(
        f"/v1/ops/alerts/{alert_id}/status",
        json={
            "account_id": seeded["account_id"],
            "status": "resolved",
            "reviewer_id": "ops_alert",
            "note": "resolved in test",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["alert"]["status"] == "resolved"
