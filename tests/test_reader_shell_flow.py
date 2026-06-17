from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository


def test_reader_only_api_flow_supports_checkout_and_resume(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_shell_flow.db"))
    app = create_app(repository=repository)
    app.state.reader_generation_job_scheduler = None
    client = TestClient(app)

    account_id = "reader_shell_flow"
    created = client.post(
        "/v1/reader/sessions",
        json={
            "world_id": "jade_court_exam",
            "account_id": account_id,
            "longform_setup": {
                "series_storyline_contract": {
                    "core_storyline": "两人必须在长线误解和真话之间持续推进到 200 章。",
                    "protected_themes": ["真话", "代价", "关系债"],
                },
                "steering_guardrails": {"no_early_ending": True},
            },
        },
    )
    assert created.status_code == 200
    session_payload = created.json()
    session_id = session_payload["session_id"]
    assert session_payload["steering_checkpoint"]["core_storyline"]

    prefill = client.get(f"/v1/reader/sessions/{session_id}/prefill")
    assert prefill.status_code == 200
    assert prefill.json()["suggested_prefill"]

    quote = client.get(f"/v1/reader/sessions/{session_id}/quote")
    assert quote.status_code == 200
    assert "access_tier" in quote.json()

    stepped = client.post(
        "/v1/reader/continue",
        json={
            "session_id": session_id,
            "account_id": account_id,
            "freeform_intent": "我先试探一下眼前这条路会把我带到哪里。",
            "steering_directive": {
                "steering_type": "mild_steer",
                "current_user_intent": "先升温，但不要立刻回收。",
                "impacted_character_ids": ["lead", "counterpart"],
            },
        },
    )
    assert stepped.status_code == 200
    stepped_payload = stepped.json()
    assert stepped_payload["status"] == "queued"
    app.state.async_job_service.run_job(stepped_payload["job"]["jobId"])
    stepped_status = client.get(f"/v1/reader/jobs/{stepped_payload['job']['jobId']}")
    assert stepped_status.status_code == 200
    stepped_result = stepped_status.json()["job"]["result"]
    assert stepped_result["reader_status"] in {"ok", "payment_required", "quality_guard_failed"}
    assert stepped_result["continuity_contract"]["preserve_workspace"] == "read"
    assert stepped_result["continuity_contract"]["preserve_session_context"] is True

    with repository.SessionLocal() as db:
        row = db.get(SessionRow, session_id)
        assert row is not None
        state = dict(row.narrative_state_json or {})
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()

    gated = client.post(
        "/v1/reader/continue",
        json={
            "session_id": session_id,
            "account_id": account_id,
            "freeform_intent": "我还想继续读下去。",
        },
    )
    assert gated.status_code == 200
    gated_payload = gated.json()
    assert gated_payload["status"] == "payment_required"
    assert gated_payload["paywall"]["reason"] in {"credits_exhausted", "payment_required", "subscription_required"}
    assert gated_payload["paywall"]["suggested_checkout_tier"]
    assert gated_payload["continuity_contract"]["primary_action"] == "unlock_and_resume"
    assert gated_payload["continuity_contract"]["chapter_context_retained"] is True

    checkout = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": account_id, "tier_id": "play_pass", "provider": "web_stub"},
    )
    assert checkout.status_code == 200
    checkout_payload = checkout.json()["checkout"]
    checkout_session_id = checkout_payload["checkout_session_id"]

    webhook = client.post(
        "/v1/reader/checkout/webhook",
        json={
            "provider": checkout_payload["provider"],
            "provider_event_id": "evt_reader_shell_flow",
            "event_type": "checkout_session_completed",
            "account_id": account_id,
            "checkout_session_id": checkout_session_id,
            "payload": {"source": "test_reader_shell_flow"},
        },
    )
    assert webhook.status_code == 200

    subscription = client.get("/v1/reader/subscription", params={"account_id": account_id})
    assert subscription.status_code == 200
    assert subscription.json()["subscription"]["status"] == "active"

    resumed = client.post(
        "/v1/reader/continue",
        json={
            "session_id": session_id,
            "account_id": account_id,
            "freeform_intent": "现在继续往前推这条命运。",
        },
    )
    assert resumed.status_code == 200
    resumed_payload = resumed.json()
    assert resumed_payload.get("status") == "queued"
    app.state.async_job_service.run_job(resumed_payload["job"]["jobId"])
    resumed_status = client.get(f"/v1/reader/jobs/{resumed_payload['job']['jobId']}")
    assert resumed_status.status_code == 200
    resumed_result = resumed_status.json()["job"]["result"]
    assert resumed_result.get("reader_status") != "payment_required"
    assert resumed_result["continuity_contract"]["preserve_workspace"] == "read"
    if resumed_result.get("reader_status") == "quality_guard_failed":
        assert resumed_result["quality_gate"]["code"] == "chapter_quality_guard_failed"
        assert resumed_result["continuity_contract"]["primary_action"] == "retry_current_chapter"
    else:
        assert resumed_result["chapter"]["chapter_title"]

    replay = client.get(f"/v1/reader/sessions/{session_id}/replay")
    assert replay.status_code == 200
    if stepped_payload.get("status") == "quality_guard_failed" and resumed_payload.get("status") == "quality_guard_failed":
        assert replay.json()["reader_views"] == []
    else:
        assert replay.json()["reader_views"]


def test_reader_generation_job_ignores_transient_heartbeat_race(tmp_path: Path, monkeypatch):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_job_heartbeat_race.db"))
    app = create_app(repository=repository)
    app.state.reader_generation_job_scheduler = None
    client = TestClient(app)

    account_id = "reader_job_heartbeat_race"
    app.state.billing_service.grant_subscription(
        {
            "account_id": account_id,
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    created = client.post(
        "/v1/reader/sessions",
        json={"world_id": "synthetic_min_pack", "account_id": account_id},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    queued = client.post(
        "/v1/reader/continue",
        json={"session_id": session_id, "account_id": account_id, "freeform_intent": "继续往前。"},
    )
    assert queued.status_code == 200
    job_id = queued.json()["job"]["jobId"]

    def heartbeat_race(*_args, **_kwargs):
        raise ValueError("async_job_not_running")

    monkeypatch.setattr(app.state.async_job_service, "heartbeat_job", heartbeat_race)
    completed = app.state.async_job_service.run_job(job_id)

    assert completed["status"] == "succeeded"
    assert completed.get("error") is None
    status = client.get(f"/v1/reader/jobs/{job_id}")
    assert status.status_code == 200
    status_payload = status.json()["job"]
    assert status_payload["status"] == "succeeded"
    assert status_payload["error"] is None
    assert status_payload["readerStatus"] in {"ok", "quality_guard_failed"}


def test_reader_checkout_can_be_invite_only_for_paid_pilot(tmp_path: Path, monkeypatch):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_invite_checkout.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    monkeypatch.setenv("NARRATIVEOS_PAID_PILOT_INVITE_ONLY", "1")
    monkeypatch.setenv("NARRATIVEOS_PAID_PILOT_INVITED_ACCOUNTS", "reader_invited")

    blocked = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "reader_not_invited", "tier_id": "play_pass", "provider": "web_stub"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "checkout_invite_required"

    allowed = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "reader_invited", "tier_id": "play_pass", "provider": "web_stub"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["checkout"]["account_id"] == "reader_invited"
