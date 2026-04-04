from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.providers import BudgetedLLMBackend, InlineJSONLLMBackend
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.observability import ObservabilityService


def test_observability_service_records_receipts_and_incident_snapshot(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "observability_service.db"))
    service = ObservabilityService(repository)

    service.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="ok",
        world_id="jade_court_exam",
        world_version_id="jade_court_exam@1.0.0",
        session_id="session_obs_1",
        account_id="acct_obs",
        reader_id="acct_obs",
        candidate_batch={
            "debug": {
                "provider": "llm",
                "backend_error": "route_down",
                "backend_routing": {
                    "selected_provider": "local",
                    "fallback_used": True,
                    "budget_blocked": False,
                    "cache_hit": False,
                },
            }
        },
        reader_view={"body": "短文本"},
        estimated_cost=0.12,
    )
    service.record_runtime_receipt(
        surface="session_api",
        action="step_session",
        response_status="ok",
        world_id="jade_court_exam",
        world_version_id="jade_court_exam@1.0.0",
        session_id="session_obs_2",
        account_id="acct_obs",
        reader_id="acct_obs",
        candidate_batch={
            "debug": {
                "provider": "llm",
                "backend_routing": {
                    "selected_provider": "openai",
                    "fallback_used": False,
                    "budget_blocked": True,
                    "cache_hit": True,
                },
            }
        },
        reader_view={"body": "另一个文本"},
        estimated_cost=0.05,
    )

    receipts = service.list_runtime_receipts(account_id="acct_obs", limit=10)
    assert len(receipts) == 2
    incidents = service.list_runtime_receipts(account_id="acct_obs", incident_only=True, limit=10)
    assert len(incidents) == 2
    snapshot = service.runtime_incident_snapshot(account_id="acct_obs", limit=10)
    assert snapshot["incident_count"] == 2
    assert snapshot["by_incident_type"]["provider_error"] >= 1
    assert snapshot["by_incident_type"]["budget_blocked"] >= 1
    assert snapshot["latest_budget_blocks"]
    assert snapshot["latest_backend_errors"]
    metrics = service.provider_runtime_metrics(account_id="acct_obs", limit=10)
    assert metrics["provider_summary"]
    assert metrics["cost_trend"]
    assert metrics["total_estimated_cost"] > 0
    metrics = service.provider_runtime_metrics(account_id="acct_obs", limit=10)
    assert metrics["provider_summary"]
    assert metrics["cost_trend"]
    assert metrics["total_estimated_cost"] > 0


def test_runtime_observability_endpoints_return_receipts_and_snapshot(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "observability_api.db"))
    llm_backend = BudgetedLLMBackend(
        InlineJSONLLMBackend({"candidate_events": []}),
        max_prompt_chars=10,
        estimated_cost_per_1k_chars=0.002,
    )
    app = create_app(repository=repository, llm_backend=llm_backend)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_obs_api"})
    assert session.status_code == 200
    session_id = session.json()["session_id"]

    step = client.post(
        f"/v1/sessions/{session_id}/step?debug=true",
        json={"player_input": "我先顺着礼法把这一幕走下去。", "metadata": {"reader_id": "acct_obs_api"}},
    )
    assert step.status_code == 200
    assert step.json()["status"] == "ok"

    receipts = client.get("/v1/ops/runtime-receipts", params={"account_id": "acct_obs_api"})
    assert receipts.status_code == 200
    assert receipts.json()["runtime_receipts"]
    assert receipts.json()["runtime_receipts"][0]["budget_blocked"] is True

    snapshot = client.get("/v1/ops/runtime-incident-snapshot", params={"account_id": "acct_obs_api"})
    assert snapshot.status_code == 200
    assert snapshot.json()["incident_count"] >= 1
    assert snapshot.json()["latest_budget_blocks"]
    metrics = client.get("/v1/ops/provider-runtime-metrics", params={"account_id": "acct_obs_api"})
    assert metrics.status_code == 200
    assert metrics.json()["provider_summary"]
    assert metrics.json()["cost_trend"]
    metrics = client.get("/v1/ops/provider-runtime-metrics", params={"account_id": "acct_obs_api"})
    assert metrics.status_code == 200
    assert metrics.json()["provider_summary"]
    assert metrics.json()["cost_trend"]
