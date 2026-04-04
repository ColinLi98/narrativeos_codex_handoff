from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.billing import BillingService


def _force_paid_chapter(repository, session_id: str) -> None:
    with repository.SessionLocal() as db:
        row = db.get(SessionRow, session_id)
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()


def test_subscription_grant_creates_dual_wallets_and_checkout_stub(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_subscriptions.db"))
    billing = BillingService(repository)

    subscription = billing.grant_subscription(
        {
            "account_id": "acct_demo",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    assert subscription["tier_id"] == "creator_pass"
    status = billing.subscription_status(account_id="acct_demo")
    assert status["subscription"]["tier_id"] == "creator_pass"
    assert status["config_version"] == "entitlement_matrix_v1"
    assert status["entitlement_matrix"]["author"]["simulate"]["required_tier"] == "creator_pass"
    assert status["tiers"][1]["display_name"] == "Creator Pass"
    assert status["tiers"][1]["capabilities"]["author_simulate"] is True
    assert status["wallets"]["story_credits"]["balance"] == 60
    assert status["wallets"]["studio_credits"]["balance"] == 40

    checkout = billing.start_checkout(account_id="acct_demo", tier_id="studio_pass", provider="web_stub")
    assert checkout["provider"] == "web_stub"
    assert checkout["tier_id"] == "studio_pass"
    assert checkout["checkout_url"]


def test_subscription_lifecycle_reconciles_past_due_and_expired(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_lifecycle.db"))
    billing = BillingService(repository)

    past_due = billing.grant_subscription(
        {
            "account_id": "acct_lifecycle_due",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
        }
    )
    expired = billing.grant_subscription(
        {
            "account_id": "acct_lifecycle_expired",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
            "cancel_at_period_end": True,
        }
    )

    past_due_status = billing.subscription_status(account_id="acct_lifecycle_due")
    expired_status = billing.subscription_status(account_id="acct_lifecycle_expired")

    assert past_due_status["subscription"]["status"] == "past_due"
    assert past_due_status["subscription"]["next_action"] == "retry_payment"
    assert past_due_status["subscription"]["period_end_passed"] is True
    assert expired_status["subscription"]["status"] == "expired"
    assert expired_status["subscription"]["next_action"] == "renew_subscription"
    assert expired_status["subscription"]["lifecycle_reason"] == "cancel_at_period_end_reached"


def test_subscription_lifecycle_reactivation_renews_period_and_refills_wallets(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_reactivate.db"))
    billing = BillingService(repository)

    granted = billing.grant_subscription(
        {
            "account_id": "acct_reactivate",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
        }
    )
    stale_wallet = billing.debit_wallet_credits(account_id="acct_reactivate", wallet_type="studio_credits", amount=39)
    assert stale_wallet["balance"] == 1.0

    past_due = billing.subscription_status(account_id="acct_reactivate")["subscription"]
    assert past_due["status"] == "past_due"

    renewed = billing.change_subscription_state(granted["subscription_id"], status="active", cancel_at_period_end=False)
    assert renewed["status"] == "active"
    assert renewed["period_end"] != "2025-01-31T00:00:00+00:00"
    status = billing.subscription_status(account_id="acct_reactivate")
    assert status["wallets"]["studio_credits"]["balance"] == 40
    assert status["subscription"]["next_action"] == "none"


def test_reader_subscription_and_checkout_api_shapes(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_reader_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_reader_api",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    subscription = client.get("/v1/reader/subscription", params={"account_id": "acct_reader_api"})
    assert subscription.status_code == 200
    assert subscription.json()["subscription"]["tier_id"] == "play_pass"
    assert "entitlement_matrix" in subscription.json()
    assert subscription.json()["entitlement_matrix"]["reader"]["continue_story"]["wallet_type"] == "story_credits"
    checkout = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "acct_reader_api", "tier_id": "creator_pass", "provider": "web_stub"},
    )
    assert checkout.status_code == 200
    assert checkout.json()["checkout"]["provider"] == "web_stub"
    assert "checkout_url" in checkout.json()["checkout"]
    assert "expires_at" in checkout.json()["checkout"]


def test_checkout_webhook_lifecycle_retry_cancel_reconcile_and_replay(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_lifecycle_closure.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    checkout = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "acct_lifecycle_flow", "tier_id": "creator_pass", "provider": "web_stub"},
    )
    assert checkout.status_code == 200
    checkout_payload = checkout.json()["checkout"]

    completed = client.post(
        "/v1/reader/checkout/webhook",
        json={
            "provider": "web_stub",
            "provider_event_id": "evt_checkout_complete_1",
            "event_type": "checkout_session_completed",
            "account_id": "acct_lifecycle_flow",
            "checkout_session_id": checkout_payload["checkout_session_id"],
            "payload": {"source": "test"},
        },
    )
    assert completed.status_code == 200
    subscription_id = completed.json()["event"]["processing_result"]["subscription_id"]

    status = client.get("/v1/reader/subscription", params={"account_id": "acct_lifecycle_flow"})
    assert status.status_code == 200
    assert status.json()["subscription"]["status"] == "active"
    assert status.json()["checkout_session"]["status"] == "completed"
    assert status.json()["lifecycle_history_summary"]["event_count"] >= 1

    failed = client.post(
        "/v1/reader/checkout/webhook",
        json={
            "provider": "web_stub",
            "provider_event_id": "evt_payment_failed_1",
            "event_type": "subscription_payment_failed",
            "account_id": "acct_lifecycle_flow",
            "subscription_id": subscription_id,
            "payload": {"source": "test"},
        },
    )
    assert failed.status_code == 200
    status = client.get("/v1/reader/subscription", params={"account_id": "acct_lifecycle_flow"})
    assert status.json()["subscription"]["status"] == "past_due"
    assert status.json()["retryable"] is True
    assert status.json()["recommended_action"] == "retry_payment"

    retried = client.post("/v1/reader/subscription/acct_lifecycle_flow/retry-payment")
    assert retried.status_code == 200
    status = client.get("/v1/reader/subscription", params={"account_id": "acct_lifecycle_flow"})
    assert status.json()["subscription"]["status"] == "active"

    canceled = client.post("/v1/reader/subscription/acct_lifecycle_flow/cancel")
    assert canceled.status_code == 200
    status = client.get("/v1/reader/subscription", params={"account_id": "acct_lifecycle_flow"})
    assert status.json()["subscription"]["status"] == "canceled"
    assert status.json()["renewable"] is True

    subscription = repository.get_subscription(subscription_id)
    repository.save_subscription({**subscription, "period_end": "2025-01-31T00:00:00+00:00"})
    reconciled = client.post(f"/v1/ops/subscriptions/{subscription_id}/reconcile", json={"requested_by": "ops_web"})
    assert reconciled.status_code == 200
    assert reconciled.json()["subscription"]["status"] == "expired"

    replay = client.post(
        f"/v1/ops/billing-events/{completed.json()['event']['event_id']}/replay",
        json={"requested_by": "ops_web"},
    )
    assert replay.status_code == 200
    subscriptions = repository.list_subscriptions(account_id="acct_lifecycle_flow")
    assert len(subscriptions) == 1

    monetization_events = client.get("/v1/ops/monetization-events", params={"account_id": "acct_lifecycle_flow"})
    assert monetization_events.status_code == 200
    assert monetization_events.json()["lifecycle_events"]
    assert monetization_events.json()["retry_attempts"]


def test_reader_continue_honors_subscription_tier_without_consuming_story_credits(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_reader.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_reader"}).json()
    _force_paid_chapter(repository, session["session_id"])

    client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_reader",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    before = client.get("/v1/reader/entitlements", params={"account_id": "acct_reader", "world_id": "jade_court_exam"}).json()
    result = client.post(
        "/v1/reader/continue",
        json={"session_id": session["session_id"], "account_id": "acct_reader", "freeform_intent": "继续往前。"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "ok"
    after = client.get("/v1/reader/entitlements", params={"account_id": "acct_reader", "world_id": "jade_court_exam"}).json()
    assert before["wallets"]["story_credits"]["balance"] == after["wallets"]["story_credits"]["balance"]
    meters = repository.list_usage_meters(account_id="acct_reader", session_id=session["session_id"])
    assert meters[0]["action_type"] == "continue_story"
    assert meters[0]["usage_units"] == 0.0
    assert meters[0]["wallet_type"] is None
    assert meters[0]["subscription_tier"] == "play_pass"
    assert meters[0]["model_policy_version"] == "entitlement_matrix_v1:reader_continue_story_credits"


def test_reader_gating_payload_exposes_required_display_name_and_capability(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_reader_gating.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_reader_gate"}).json()
    _force_paid_chapter(repository, session["session_id"])
    result = client.post(
        "/v1/reader/continue",
        json={"session_id": session["session_id"], "account_id": "acct_reader_gate", "freeform_intent": "继续往前。"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "payment_required"
    paywall = result.json()["paywall"]
    assert paywall["required_display_name"] == "Play Pass"
    assert paywall["required_capability"] == "reader_continue"
    assert paywall["suggested_checkout_tier"] == "play_pass"
    assert paywall["config_version"] == "entitlement_matrix_v1"


def test_reader_story_credits_metering_consumes_wallet_and_records_credit_units(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_story_metering.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_story_meter"}).json()
    _force_paid_chapter(repository, session["session_id"])

    client.post(
        "/v1/reader/entitlements/grant",
        json={
            "account_id": "acct_story_meter",
            "reader_id": "acct_story_meter",
            "entitlement_type": "credits",
            "wallet_type": "story_credits",
            "balance": 3,
        },
    )
    before = client.get("/v1/reader/entitlements", params={"account_id": "acct_story_meter", "world_id": "jade_court_exam"}).json()
    result = client.post(
        "/v1/reader/continue",
        json={"session_id": session["session_id"], "account_id": "acct_story_meter", "freeform_intent": "继续往前。"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "ok"
    after = client.get("/v1/reader/entitlements", params={"account_id": "acct_story_meter", "world_id": "jade_court_exam"}).json()
    assert after["wallets"]["story_credits"]["balance"] == before["wallets"]["story_credits"]["balance"] - 1
    meters = repository.list_usage_meters(account_id="acct_story_meter", session_id=session["session_id"])
    assert meters[0]["action_type"] == "continue_story"
    assert meters[0]["usage_units"] == 1.0
    assert meters[0]["wallet_type"] == "story_credits"
    assert meters[0]["subscription_tier"] is None
    assert meters[0]["model_policy_version"] == "entitlement_matrix_v1:reader_continue_story_credits"


def test_support_issue_lookup_flags_payment_required_and_credit_exhaustion(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_support_reader.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_support"}).json()
    _force_paid_chapter(repository, session["session_id"])
    blocked = client.post(
        "/v1/reader/continue",
        json={"session_id": session["session_id"], "account_id": "acct_support", "freeform_intent": "继续往前。"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "payment_required"

    issues = client.get("/v1/ops/accounts/acct_support/issues")
    assert issues.status_code == 200
    payload = issues.json()
    issue_types = {item["issue_type"] for item in payload["support_issues"]}
    assert "missing_subscription" in issue_types
    assert "reader_payment_required_recent" in issue_types
    assert "story_credits_exhausted" in issue_types
    assert payload["support_summary"]["open_issue_count"] >= 3
    assert any(action["prefill"]["tier_id"] == "play_pass" for action in payload["support_tooling"]["recommended_actions"] if action["action_type"] == "grant_subscription")


def test_support_issue_lookup_flags_subscription_lifecycle_and_author_credit_problems(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_support_author.db"))
    billing = BillingService(repository)

    billing.grant_subscription(
        {
            "account_id": "acct_support_author",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2025-01-01T00:00:00+00:00",
            "period_end": "2025-01-31T00:00:00+00:00",
        }
    )
    billing.debit_wallet_credits(account_id="acct_support_author", wallet_type="studio_credits", amount=40)

    payload = billing.support_issue_lookup(account_id="acct_support_author")
    issue_types = {item["issue_type"] for item in payload["support_issues"]}
    assert "subscription_lifecycle_issue" in issue_types
    assert "studio_credits_exhausted" in issue_types
    assert "author_access_blocked" in issue_types
    assert payload["support_summary"]["high_priority_issue_count"] >= 1


def test_author_from_brief_and_simulate_require_creator_pass_and_consume_studio_credits(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_author.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    blocked = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "account_id": "acct_author",
            "brief": {
                "author_id": "acct_author",
                "genre_preset": "urban_mystery",
                "world_title": "深巷回声",
                "lead_name": "江屹",
                "counterpart_name": "周岚",
                "core_premise": "测试 creator gating。",
                "life_theme": "真话是否值得承担失去",
                "locations": "旧巷\n便利店门口",
            },
        },
    )
    assert blocked.status_code == 402

    client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_author",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    before = client.get("/v1/reader/entitlements", params={"account_id": "acct_author"}).json()
    created = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "account_id": "acct_author",
            "brief": {
                "author_id": "acct_author",
                "genre_preset": "urban_mystery",
                "world_title": "深巷回声",
                "lead_name": "江屹",
                "counterpart_name": "周岚",
                "core_premise": "测试 creator gating。",
                "life_theme": "真话是否值得承担失去",
                "locations": "旧巷\n便利店门口",
            },
        },
    )
    assert created.status_code == 200
    draft_id = created.json()["world_version_id"]
    after_create = client.get("/v1/reader/entitlements", params={"account_id": "acct_author"}).json()
    assert after_create["wallets"]["studio_credits"]["balance"] == before["wallets"]["studio_credits"]["balance"] - 2

    simulated = client.post(f"/v1/author/drafts/{draft_id}/simulate?account_id=acct_author")
    assert simulated.status_code == 200
    after_sim = client.get("/v1/reader/entitlements", params={"account_id": "acct_author"}).json()
    assert after_sim["wallets"]["studio_credits"]["balance"] == after_create["wallets"]["studio_credits"]["balance"] - 1
    meters = repository.list_usage_meters(account_id="acct_author")
    action_map = {item["action_type"]: item for item in meters}
    assert action_map["author_from_brief"]["usage_units"] == 2.0
    assert action_map["author_from_brief"]["wallet_type"] == "studio_credits"
    assert action_map["author_from_brief"]["subscription_tier"] == "creator_pass"
    assert action_map["author_from_brief"]["model_policy_version"] == "entitlement_matrix_v1:author_from_brief_studio_credits"
    assert action_map["author_simulate"]["usage_units"] == 1.0
    assert action_map["author_simulate"]["wallet_type"] == "studio_credits"
    assert action_map["author_simulate"]["subscription_tier"] == "creator_pass"
    assert action_map["author_simulate"]["model_policy_version"] == "entitlement_matrix_v1:author_simulate_studio_credits"
    account_detail = client.get("/v1/ops/accounts/acct_author")
    assert account_detail.status_code == 200
    audit_actions = [item["action"] for item in account_detail.json()["audit_trail"]]
    assert "author_draft_created_from_brief" in audit_actions
    assert "author_draft_simulated" in audit_actions
    assert account_detail.json()["audit_breakdown"]["by_category"]["author"] >= 2


def test_author_access_reflects_subscription_lifecycle_block_and_renew(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_author_lifecycle_access.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_author_lifecycle",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    allowed = client.get("/v1/author/access", params={"account_id": "acct_author_lifecycle"})
    assert allowed.status_code == 200
    assert allowed.json()["actions"]["simulate"]["allowed"] is True

    subscription_id = client.get("/v1/ops/subscriptions", params={"account_id": "acct_author_lifecycle"}).json()["subscriptions"][0]["subscription_id"]
    failed = client.post(
        "/v1/reader/checkout/webhook",
        json={
            "provider": "web_stub",
            "provider_event_id": "evt_author_failed_1",
            "event_type": "subscription_payment_failed",
            "account_id": "acct_author_lifecycle",
            "subscription_id": subscription_id,
            "payload": {"source": "test"},
        },
    )
    assert failed.status_code == 200
    blocked = client.get("/v1/author/access", params={"account_id": "acct_author_lifecycle"})
    assert blocked.status_code == 200
    assert blocked.json()["actions"]["simulate"]["allowed"] is False
    assert blocked.json()["subscription"]["status"] == "past_due"

    renewed = client.post("/v1/reader/subscription/acct_author_lifecycle/renew")
    assert renewed.status_code == 200
    restored = client.get("/v1/author/access", params={"account_id": "acct_author_lifecycle"})
    assert restored.status_code == 200
    assert restored.json()["actions"]["simulate"]["allowed"] is True


def test_ops_can_audit_and_mutate_subscription_and_wallet_state(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_ops.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    granted = client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_ops",
            "tier_id": "studio_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    assert granted.status_code == 200
    subscription_id = granted.json()["subscription"]["subscription_id"]

    listed = client.get("/v1/ops/subscriptions", params={"account_id": "acct_ops"})
    assert listed.status_code == 200
    assert listed.json()["subscriptions"]

    entitlements = client.get("/v1/ops/entitlements", params={"account_id": "acct_ops"})
    assert entitlements.status_code == 200
    assert entitlements.json()["wallets"]["studio_credits"]["balance"] == 150
    assert entitlements.json()["entitlement_matrix"]["author"]["draft_from_brief"]["wallet_type"] == "studio_credits"
    assert "audit_summary" in entitlements.json()
    assert "audit_timeline" in entitlements.json()
    assert "audit_trail" in entitlements.json()
    assert "audit_breakdown" in entitlements.json()
    assert "timeline_cursor" in entitlements.json()
    assert entitlements.json()["audit_summary"]["entitlement_count"] >= 2
    wallet_entitlement_id = entitlements.json()["wallets"]["studio_credits"]["entitlement_id"]

    topped_up = client.post(
        "/v1/ops/wallets/grant",
        json={"account_id": "acct_ops", "wallet_type": "studio_credits", "amount": 10},
    )
    assert topped_up.status_code == 200
    debited = client.post(
        "/v1/ops/wallets/debit",
        json={"account_id": "acct_ops", "wallet_type": "studio_credits", "amount": 5},
    )
    assert debited.status_code == 200
    changed = client.post(
        "/v1/ops/subscriptions/state",
        json={"subscription_id": subscription_id, "status": "canceled"},
    )
    assert changed.status_code == 200
    assert changed.json()["subscription"]["status"] == "canceled"
    revoked = client.post(
        "/v1/ops/entitlements/revoke",
        json={"entitlement_id": wallet_entitlement_id, "reason": "manual_entitlement_revoke"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["entitlement"]["status"] == "revoked"
    events = client.get("/v1/ops/monetization-events", params={"account_id": "acct_ops"})
    assert events.status_code == 200
    assert "events" in events.json()
    assert any(item["event_name"] == "entitlement_revoked" for item in events.json()["events"])
    account_detail = client.get("/v1/ops/accounts/acct_ops")
    assert account_detail.status_code == 200
    assert account_detail.json()["account_id"] == "acct_ops"
    assert "activity_summary" in account_detail.json()
    assert "recent_meters" in account_detail.json()
    assert "recent_events" in account_detail.json()
    assert "recent_drafts" in account_detail.json()
    assert "recent_sessions" in account_detail.json()
    assert "author_access" in account_detail.json()
    assert "audit_trail" in account_detail.json()
    assert "audit_breakdown" in account_detail.json()
    assert "timeline_cursor" in account_detail.json()
    assert account_detail.json()["audit_breakdown"]["by_category"]["subscription"] >= 1
    assert account_detail.json()["audit_breakdown"]["by_source_type"]["analytics_event"] >= 1
    assert any(item["action"] == "subscription_state_changed" for item in account_detail.json()["audit_trail"])


def test_author_access_check_uses_entitlement_matrix_requirements(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_matrix_access.db"))
    billing = BillingService(repository)

    billing.grant_subscription(
        {
            "account_id": "acct_matrix",
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    blocked = billing.access_check_author(account_id="acct_matrix", action_name="simulate")
    assert blocked["allowed"] is False
    assert blocked["required_tier"] == "creator_pass"
    assert blocked["wallet_type"] == "studio_credits"

    billing.change_subscription_state(
        billing.repository.get_active_subscription_for_account("acct_matrix")["subscription_id"],
        status="canceled",
    )
    billing.grant_subscription(
        {
            "account_id": "acct_matrix",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    allowed = billing.access_check_author(account_id="acct_matrix", action_name="draft_from_brief")
    assert allowed["required_tier"] == "creator_pass"
    assert allowed["required_display_name"] == "Creator Pass"
    assert allowed["wallet_type"] == "studio_credits"
    assert allowed["minimum_author_access"] == "basic"


def test_author_access_snapshot_exposes_action_gating(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_author_access_snapshot.db"))
    billing = BillingService(repository)
    snapshot = billing.author_access_snapshot(account_id="acct_author_snapshot")
    assert snapshot["config_version"] == "entitlement_matrix_v1"
    assert snapshot["actions"]["draft_from_brief"]["required_display_name"] == "Creator Pass"
    assert snapshot["actions"]["simulate"]["required_capability"] == "author_simulate"


def test_monetization_analytics_events_are_recorded(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "monetization_analytics.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "acct_events",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "acct_events", "tier_id": "studio_pass", "provider": "web_stub"},
    )
    draft = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "account_id": "acct_events",
            "brief": {
                "author_id": "acct_events",
                "genre_preset": "urban_mystery",
                "world_title": "深巷回声",
                "lead_name": "江屹",
                "counterpart_name": "周岚",
                "core_premise": "测试 monetization events。",
                "life_theme": "真话是否值得承担失去",
                "locations": "旧巷\n便利店门口",
            },
        },
    )
    assert draft.status_code == 200
    draft_id = draft.json()["world_version_id"]
    simulate = client.post(f"/v1/author/drafts/{draft_id}/simulate?account_id=acct_events")
    assert simulate.status_code == 200
    client.post(
        "/v1/ops/wallets/grant",
        json={"account_id": "acct_reader_events", "wallet_type": "story_credits", "amount": 3},
    )
    session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_reader_events"}).json()
    _force_paid_chapter(repository, session["session_id"])
    continue_result = client.post(
        "/v1/reader/continue",
        json={"session_id": session["session_id"], "account_id": "acct_reader_events", "freeform_intent": "继续往前。"},
    )
    assert continue_result.status_code == 200

    author_events = repository.list_analytics_events(reader_id="acct_events")
    author_event_names = {event["event_name"] for event in author_events}
    assert "subscription_activated" in author_event_names
    assert "checkout_started" in author_event_names
    assert "studio_credits_consumed" in author_event_names

    reader_events = repository.list_analytics_events(reader_id="acct_reader_events")
    reader_event_names = {event["event_name"] for event in reader_events}
    assert "story_credits_consumed" in reader_event_names
