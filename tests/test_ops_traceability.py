import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _create_app(tmp_path: Path, name: str):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / name))
    app = create_app(repository=repository)
    return app, repository


def _seed_release_trace(app, *, account_id: str, version: str = "0.9.9") -> dict:
    authoring = app.state.authoring_service
    repository = app.state.repository
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = version
    pack["manifest"]["author_id"] = account_id

    draft = authoring.save_draft(pack)
    world_version_id = draft["world_version_id"]
    world_id = draft["world_id"]
    authoring.run_simulation_for_world_version(world_version_id)
    authoring.submit_for_review(world_version_id)
    repository.save_review_record(
        {
            "asset_type": "world_version",
            "asset_id": world_version_id,
            "status": "publish_blocked",
            "reviewer_id": "ops_trace",
            "notes": json.dumps(
                {
                    "world_id": world_id,
                    "world_version_id": world_version_id,
                    "latest_decision": "block",
                    "publish_gate_errors": ["cross_pack_regression"],
                    "risk_summary": {"publish_gate_errors": ["cross_pack_regression"]},
                }
            ),
        }
    )
    return {"world_id": world_id, "world_version_id": world_version_id}


def _seed_traceability_bundle(app, *, account_id: str = "acct_traceability", include_governance: bool = True) -> dict:
    billing = app.state.billing_service
    governance = app.state.governance_service
    analytics = app.state.analytics_service
    observability = app.state.observability_service
    release = _seed_release_trace(app, account_id=account_id)

    checkout = billing.start_checkout(account_id=account_id, tier_id="creator_pass", provider="web_stub")
    completed = billing.ingest_checkout_webhook(
        {
            "provider": "web_stub",
            "provider_event_id": f"evt_complete_{account_id}",
            "event_type": "checkout_session_completed",
            "account_id": account_id,
            "checkout_session_id": checkout["checkout_session_id"],
            "payload": {"source": "trace_test"},
        }
    )
    subscription_id = completed["event"]["processing_result"]["subscription_id"]
    billing.ingest_checkout_webhook(
        {
            "provider": "web_stub",
            "provider_event_id": f"evt_failed_{account_id}",
            "event_type": "subscription_payment_failed",
            "account_id": account_id,
            "subscription_id": subscription_id,
            "payload": {"source": "trace_test"},
        }
    )
    analytics.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_id=release["world_id"],
        world_version_id=release["world_version_id"],
        payload_json={"reason": "subscription_required", "subscription_id": subscription_id},
    )
    billing.meter_action(
        surface="reader",
        action_name="continue_story",
        account_id=account_id,
        reader_id=account_id,
        session_id=f"session_{account_id}",
        world_version_id=release["world_version_id"],
        subscription_tier="creator_pass",
        charged_units=1.0,
        estimated_cost=0.22,
    )
    observability.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="fallback",
        world_id=release["world_id"],
        world_version_id=release["world_version_id"],
        session_id=f"session_{account_id}",
        account_id=account_id,
        candidate_batch={
            "debug": {
                "provider": "llm",
                "backend_error": "provider_down",
                "backend_routing": {"selected_provider": "local", "fallback_used": True},
            }
        },
        reader_view={"body": "traceability runtime sample"},
    )
    case = None
    if include_governance:
        case = governance.apply_restriction(
            {
                "restriction_type": "author_access_block",
                "account_id": account_id,
                "case_type": "abuse",
                "severity": "high",
                "summary": "统一排查测试：冻结 author access",
                "reviewer_id": "ops_trace",
                "world_version_id": release["world_version_id"],
            }
        )
    return {
        "account_id": account_id,
        "world_id": release["world_id"],
        "world_version_id": release["world_version_id"],
        "case_id": case["case_id"] if case else None,
        "restriction_id": case["restriction"]["restriction_id"] if case else None,
        "subscription_id": subscription_id,
    }


def test_ops_traceability_aggregates_billing_governance_review_and_runtime(tmp_path: Path):
    app, _repository = _create_app(tmp_path, "ops_traceability_aggregate.db")
    seeded = _seed_traceability_bundle(app)

    bundle = app.state.ops_traceability_service.investigate_account(account_id=seeded["account_id"], limit=50)

    assert bundle["filters"]["account_id"] == seeded["account_id"]
    assert bundle["investigation_summary"]["trace_count"] >= 6
    source_types = {item["source_type"] for item in bundle["trace_timeline"]}
    assert "billing_lifecycle_event" in source_types
    assert "support_issue" in source_types
    assert "governance_case" in source_types
    assert "governance_restriction" in source_types
    assert "review_timeline" in source_types
    assert "publish_checklist" in source_types
    assert "runtime_receipt" in source_types
    assert "analytics_event" in source_types
    assert "usage_meter" in source_types
    assert bundle["recommended_paths"]
    timeline_times = [item["occurred_at"] for item in bundle["trace_timeline"] if item.get("occurred_at")]
    assert timeline_times == sorted(timeline_times, reverse=True)
    assert any(item["related_trace_ids"] for item in bundle["trace_timeline"])
    assert bundle["evidence_index"]
    assert all(item["preview"] for item in bundle["evidence_index"])


def test_ops_traceability_recommended_paths_follow_dominant_signal(tmp_path: Path):
    billing_app, _ = _create_app(tmp_path, "ops_traceability_billing.db")
    billing_seed = _seed_traceability_bundle(
        billing_app,
        account_id="acct_trace_billing",
        include_governance=False,
    )
    billing_bundle = billing_app.state.ops_traceability_service.investigate_account(account_id=billing_seed["account_id"], limit=30)
    assert billing_bundle["recommended_paths"][0]["path_id"] == "billing_first"

    governance_app, _ = _create_app(tmp_path, "ops_traceability_governance.db")
    governance = governance_app.state.governance_service
    governance_app.state.billing_service.grant_subscription(
        {
            "account_id": "acct_trace_governance",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    governance.apply_restriction(
        {
            "restriction_type": "checkout_block",
            "account_id": "acct_trace_governance",
            "case_type": "abuse",
            "severity": "high",
            "summary": "高优先级治理限制",
            "reviewer_id": "ops_trace",
        }
    )
    governance_bundle = governance_app.state.ops_traceability_service.investigate_account(
        account_id="acct_trace_governance",
        limit=20,
    )
    assert governance_bundle["recommended_paths"][0]["path_id"] == "governance_first"

    release_app, repository = _create_app(tmp_path, "ops_traceability_release.db")
    release_seed = _seed_release_trace(release_app, account_id="acct_trace_release", version="0.9.8")
    repository.save_review_record(
        {
            "asset_type": "world",
            "asset_id": release_seed["world_id"],
            "status": "rolled_back",
            "reviewer_id": "ops_trace",
            "notes": json.dumps(
                {
                    "world_id": release_seed["world_id"],
                    "target_world_version_id": release_seed["world_version_id"],
                    "previous_world_version_id": "urban_mystery_lotus_lane@0.1.0",
                    "entitlement_reason": "operator_requested_rollback",
                    "risk_summary": {"publish_gate_errors": ["quality_regression"]},
                }
            ),
        }
    )
    release_bundle = release_app.state.ops_traceability_service.investigate_account(
        account_id="acct_trace_release",
        limit=20,
    )
    assert release_bundle["recommended_paths"][0]["path_id"] == "content_release_first"


def test_ops_traceability_endpoints_support_account_case_world_and_export(tmp_path: Path):
    app, _repository = _create_app(tmp_path, "ops_traceability_api.db")
    client = TestClient(app)
    seeded = _seed_traceability_bundle(app, account_id="acct_trace_api")

    account = client.get(f"/v1/ops/investigations/accounts/{seeded['account_id']}", params={"limit": 40})
    assert account.status_code == 200
    assert account.json()["filters"]["account_id"] == seeded["account_id"]
    assert account.json()["trace_timeline"]

    case = client.get(f"/v1/ops/investigations/cases/{seeded['case_id']}", params={"limit": 40})
    assert case.status_code == 200
    assert case.json()["filters"]["case_id"] == seeded["case_id"]
    assert any(item.get("case_id") == seeded["case_id"] for item in case.json()["trace_timeline"])

    world = client.get(f"/v1/ops/investigations/world-versions/{seeded['world_version_id']}", params={"limit": 40})
    assert world.status_code == 200
    assert world.json()["filters"]["world_version_id"] == seeded["world_version_id"]
    assert any(item.get("world_version_id") == seeded["world_version_id"] for item in world.json()["trace_timeline"])

    exported = client.get("/v1/ops/export/investigation-trace", params={"account_id": seeded["account_id"], "limit": 40})
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["generated_at"]
    assert payload["filters"]["account_id"] == seeded["account_id"]
    assert payload["recommended_paths"]
    assert payload["evidence_index"]
