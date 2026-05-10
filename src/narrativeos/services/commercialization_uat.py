from __future__ import annotations

import json
import os
import shutil
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from ..repository import SQLAlchemyRepository

_STRIPE_ENV_KEYS = (
    "NARRATIVEOS_BILLING_PROVIDER",
    "NARRATIVEOS_STRIPE_SECRET_KEY",
    "NARRATIVEOS_STRIPE_PUBLISHABLE_KEY",
    "NARRATIVEOS_STRIPE_WEBHOOK_SECRET",
    "NARRATIVEOS_STRIPE_PRICE_MAP_JSON",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return f"commercialization_uat_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _register_identity(client: TestClient, *, actor_id: str, actor_role: str) -> str:
    client.post(
        "/v1/auth/register",
        json={
            "actor_id": actor_id,
            "actor_role": actor_role,
            "password": "secret123",
            "account_id": actor_id,
            "display_name": actor_id,
        },
    )
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": "secret123"})
    if login.status_code != 200:
        raise RuntimeError(f"identity_login_failed:{actor_id}:{login.status_code}")
    return login.json()["token"]["access_token"]


def _install_fake_stripe() -> Dict[str, Any]:
    snapshot = {
        "stripe_module_present": "stripe" in sys.modules,
        "stripe_module": sys.modules.get("stripe"),
        "env": {key: os.environ.get(key) for key in _STRIPE_ENV_KEYS},
    }

    class FakeCustomer:
        @staticmethod
        def create(**kwargs):
            return {"id": "cus_uat_123", **kwargs}

        @staticmethod
        def retrieve(customer_id):
            return {"id": customer_id}

    class FakeInvoiceItem:
        @staticmethod
        def create(**kwargs):
            return {"id": "ii_uat_123", **kwargs}

    class FakeInvoice:
        @staticmethod
        def create(**kwargs):
            return {"id": "in_uat_123", "status": "draft", **kwargs}

        @staticmethod
        def finalize_invoice(invoice_id):
            return {
                "id": invoice_id,
                "status": "open",
                "hosted_invoice_url": f"https://invoice.stripe.test/{invoice_id}",
                "invoice_pdf": f"https://invoice.stripe.test/{invoice_id}.pdf",
                "payment_intent": "pi_uat_123",
            }

        @staticmethod
        def retrieve(invoice_id):
            return {
                "id": invoice_id,
                "status": "open",
                "hosted_invoice_url": f"https://invoice.stripe.test/{invoice_id}",
                "invoice_pdf": f"https://invoice.stripe.test/{invoice_id}.pdf",
            }

    class FakeCreditNote:
        @staticmethod
        def create(**kwargs):
            return {"id": "cn_uat_123", **kwargs}

    class FakeWebhook:
        current_event: Dict[str, Any] = {}

        @staticmethod
        def construct_event(payload, sig_header, secret):
            return FakeWebhook.current_event

    fake_stripe = types.SimpleNamespace(
        Customer=FakeCustomer,
        InvoiceItem=FakeInvoiceItem,
        Invoice=FakeInvoice,
        CreditNote=FakeCreditNote,
        Webhook=FakeWebhook,
        api_key=None,
        api_version=None,
    )
    sys.modules["stripe"] = fake_stripe
    os.environ["NARRATIVEOS_BILLING_PROVIDER"] = "stripe"
    os.environ["NARRATIVEOS_STRIPE_SECRET_KEY"] = "sk_test_uat"
    os.environ["NARRATIVEOS_STRIPE_PUBLISHABLE_KEY"] = "pk_test_uat"
    os.environ["NARRATIVEOS_STRIPE_WEBHOOK_SECRET"] = "whsec_uat"
    os.environ["NARRATIVEOS_STRIPE_PRICE_MAP_JSON"] = json.dumps(
        {"play_pass": "price_play", "creator_pass": "price_creator", "studio_pass": "price_studio"}
    )
    return snapshot


def _restore_fake_stripe(snapshot: Dict[str, Any]) -> None:
    if snapshot.get("stripe_module_present"):
        sys.modules["stripe"] = snapshot.get("stripe_module")
    else:
        sys.modules.pop("stripe", None)
    env_snapshot = dict(snapshot.get("env") or {})
    for key in _STRIPE_ENV_KEYS:
        value = env_snapshot.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _seed_quality_and_billing_bundle(app, *, account_id: str) -> Dict[str, Any]:
    app.state.customer_account_service.ensure_customer_account(
        account_id=account_id,
        display_name="Commercial UAT Customer",
        plan_id="play_pass",
        status="renewal_due",
    )
    customer_detail = app.state.customer_account_service.customer_account_detail(account_id=account_id)
    customer_account = customer_detail["customer_account"]
    app.state.customer_account_service.upsert_billing_profile(
        customer_account_id=customer_account["customer_account_id"],
        account_id=account_id,
        provider="stripe",
        invoice_email="billing@uat.test",
        legal_name="Commercial UAT Ltd",
        billing_country="GB",
        tax_status="pending",
    )
    app.state.billing_service.grant_subscription(
        {
            "account_id": account_id,
            "tier_id": "play_pass",
            "provider": "ops_manual",
            "status": "active",
            "period_start": "2026-04-01T00:00:00+00:00",
            "period_end": "2026-05-01T00:00:00+00:00",
        }
    )
    app.state.repository.save_quality_event(
        {
            "event_id": "quality_event_uat_presented",
            "trace_id": "trace_uat_presented",
            "event_type": "chapter_quality_evaluated",
            "source_surface": "reader",
            "status": "passed",
            "world_version_id": "urban_mystery_lotus_lane@0.1.0",
            "session_id": "session_uat_presented",
            "source_ref": {"kind": "chapter", "account_id": account_id},
            "payload": {"reason_codes": ["supported"]},
        }
    )
    app.state.observability_service.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="ok",
        world_id="urban_mystery_lotus_lane",
        world_version_id="urban_mystery_lotus_lane@0.1.0",
        session_id="session_uat_presented",
        account_id=account_id,
        reader_id=account_id,
        candidate_batch={"debug": {}},
        rendered_scene={"debug": {}},
        reader_view={"body": "一段商业化 UAT 正文。"},
        estimated_cost=0.02,
        runtime_latency_ms=12.0,
        trace_id="trace_uat_presented",
        quality_event_id="quality_event_uat_presented",
    )
    app.state.repository.save_quality_event(
        {
            "event_id": "quality_event_uat_handoff",
            "trace_id": "trace_uat_handoff",
            "event_type": "publish_preflight",
            "source_surface": "publish",
            "status": "passed",
            "world_version_id": "urban_mystery_lotus_lane@0.1.0",
            "session_id": None,
            "source_ref": {"kind": "world_version", "account_id": account_id},
            "payload": {"reason_codes": ["publish_ready"]},
        }
    )
    app.state.repository.save_quality_feedback_item(
        {
            "feedback_item_id": "feedback_uat_positive",
            "feedback_type": "explicit_user_feedback",
            "signal": "explicit_positive",
            "source_surface": "reader",
            "trace_id": "trace_uat_presented",
            "account_id": account_id,
            "world_version_id": "urban_mystery_lotus_lane@0.1.0",
            "session_id": "session_uat_presented",
            "source_ref": {"kind": "session", "account_id": account_id},
            "payload": {"reason_code": "not_useful"},
        }
    )
    campaign_bundle = app.state.customer_campaign_service.create_or_update_campaign(
        account_id=account_id,
        payload={
            "title": "Commercial UAT Campaign",
            "target_icp_vertical": "B2B SaaS",
            "cta_text": "book a pilot",
            "disclosure_text": "Sponsored pilot outreach with attribution.",
            "selected_channels": ["email"],
            "selected_partner_refs": ["partner_uat"],
            "proof_points": ["1 validated handoff", "1 validated conversion"],
            "proof_source_urls": ["https://example.test/proof/uat"],
            "proof_artifact_refs": ["artifact://proof-uat"],
        },
    )
    campaign = dict(campaign_bundle.get("campaign") or {})
    app.state.repository.save_campaign(
        {
            **campaign,
            "activation_status": "active",
            "selected_channels_json": campaign.get("selected_channels_json") or ["email"],
            "selected_partner_refs_json": campaign.get("selected_partner_refs_json") or ["partner_uat"],
            "campaign_payload_json": dict(campaign.get("campaign_payload_json") or {}),
        }
    )
    app.state.repository.save_overage_flag(
        {
            "overage_flag_id": "overage_uat_handoff",
            "account_id": account_id,
            "customer_account_id": customer_account["customer_account_id"],
            "plan_id": customer_account["plan_id"],
            "metric_type": "validated_handoff",
            "status": "active",
            "observed_units": 2,
            "included_units": 0,
            "overage_units": 2,
            "flag_payload": {"reason": "demo_upgrade_prompt"},
        }
    )
    return {"customer_account": customer_account}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _summary_markdown(summary: Dict[str, Any]) -> str:
    journey = summary["journey"]
    acceptance = summary["acceptance"]
    return "\n".join(
        [
            "# Commercialization UAT",
            "",
            f"- run_id: {summary['run_id']}",
            f"- generated_at: {summary['generated_at']}",
            f"- account_id: {summary['account_id']}",
            f"- customer_account_id: {summary['customer_account_id']}",
            "",
            "## Journey",
            f"- invoice_preview_total_due_usd: {journey['invoice_preview']['total_due_usd']}",
            f"- issued_invoice_status: {journey['issued_invoice']['status']}",
            f"- failed_invoice_status: {journey['failed_invoice']['status']}",
            f"- dunning_status_after_failure: {journey['lifecycle_after_failure']['dunning_summary']['status']}",
            f"- renewal_status: {journey['lifecycle_after_failure']['renewal_summary']['status']}",
            f"- upgrade_recommendation: {journey['lifecycle_after_failure']['expansion_summary']['recommended_plan_id']}",
            f"- paid_invoice_status: {journey['paid_invoice']['status']}",
            f"- dunning_status_after_recovery: {journey['lifecycle_after_recovery']['dunning_summary']['status']}",
            "",
            "## Acceptance",
            f"- all_passed: {acceptance['all_passed']}",
            *[f"- {item['label']}: {'pass' if item['passed'] else 'fail'}" for item in acceptance["checkpoints"]],
        ]
    )


def _delivery_packet_markdown(summary: Dict[str, Any]) -> str:
    journey = summary["journey"]
    return "\n".join(
        [
            "# Commercial Delivery Packet",
            "",
            "## Scope Included",
            "- customer account / billing profile lifecycle",
            "- invoice preview -> issued invoice -> provider payment status sync",
            "- dispute / refund / support core",
            "- audit export / tenant isolation / customer-safe payloads",
            "- customer workspace reporting and commercialization Ops dashboard",
            "- renewal / dunning / pilot conversion / expansion / churn risk automation",
            "",
            "## UAT Evidence",
            f"- invoice preview due: {journey['invoice_preview']['total_due_usd']}",
            f"- issued invoice link: {journey['issued_invoice']['hosted_invoice_url']}",
            f"- failed payment status: {journey['failed_invoice']['status']}",
            f"- paid recovery status: {journey['paid_invoice']['status']}",
            f"- dunning after failure: {journey['lifecycle_after_failure']['dunning_summary']['status']}",
            f"- renewal posture: {journey['lifecycle_after_failure']['renewal_summary']['status']}",
            f"- upgrade suggestion: {journey['lifecycle_after_failure']['expansion_summary']['recommended_plan_id']}",
            "",
            "## Customer Acceptance Checklist",
            "- can view invoice preview in `/app/customer`",
            "- ops can issue a formal invoice from preview",
            "- provider webhook can mark invoice failed and then paid",
            "- failed payment opens dunning posture",
            "- renewal due is visible to customer and ops",
            "- overage triggers an upgrade recommendation",
            "- support / disputes / audit export remain available",
            "",
            "## Operational Notes",
            "- billing provider: Stripe",
            "- currency: USD",
            "- customer-safe logs only on customer routes",
            "- disputes and manual adjustments remain canonical and auditable",
            "",
            "## Artifacts",
            "- `artifacts/commercialization_uat/latest/summary.json`",
            "- `artifacts/commercialization_uat/latest/report.md`",
            "- `artifacts/commercialization_uat/latest/customer_signoff_packet.md`",
        ]
    )


def run_commercialization_uat(output_root: str | Path | None = None) -> Dict[str, Any]:
    from ..api import create_app

    fake_stripe_snapshot = _install_fake_stripe()
    try:
        root = Path(__file__).resolve().parents[3]
        run_id = _run_id()
        base_dir = Path(output_root) if output_root else (root / "artifacts" / "commercialization_uat" / run_id)
        base_dir.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{base_dir / 'commercialization_uat.db'}"
        app = create_app(repository=SQLAlchemyRepository(database_url=database_url))
        client = TestClient(app)

        customer_actor_id = "customer_commercial_uat"
        reviewer_actor_id = "ops_commercial_uat"
        customer_token = _register_identity(client, actor_id=customer_actor_id, actor_role="customer")
        reviewer_token = _register_identity(client, actor_id=reviewer_actor_id, actor_role="reviewer")
        seeded = _seed_quality_and_billing_bundle(app, account_id=customer_actor_id)
        customer_account = seeded["customer_account"]

        preview_response = client.get("/v1/customer/invoice-preview", headers={"Authorization": f"Bearer {customer_token}"})
        if preview_response.status_code != 200:
            raise RuntimeError(f"invoice_preview_failed:{preview_response.status_code}")
        preview_payload = preview_response.json()
        invoice_preview = dict(preview_payload["invoice_preview"])

        issue_response = client.post(
            f"/v1/ops/invoices/{invoice_preview['invoice_preview_id']}/issue",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={},
        )
        if issue_response.status_code != 200:
            raise RuntimeError(f"invoice_issue_failed:{issue_response.status_code}")
        issued_invoice = dict(issue_response.json()["invoice"])

        fake_stripe = sys.modules["stripe"]
        fake_stripe.Webhook.current_event = {
            "id": "evt_uat_failed",
            "type": "invoice.payment_failed",
            "data": {"object": {"id": issued_invoice["provider_invoice_ref"], "payment_intent": "pi_failed_uat"}},
        }
        failed_response = client.post("/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "sig_uat"})
        if failed_response.status_code != 200:
            raise RuntimeError(f"failed_webhook_failed:{failed_response.status_code}")
        failed_payload = failed_response.json()

        lifecycle_failure = client.post(
            "/v1/ops/lifecycle-automation/sync",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"account_id": customer_actor_id},
        )
        if lifecycle_failure.status_code != 200:
            raise RuntimeError(f"lifecycle_sync_failed:{lifecycle_failure.status_code}")

        workspace_after_failure = client.get("/v1/customer/workspace", headers={"Authorization": f"Bearer {customer_token}"})
        if workspace_after_failure.status_code != 200:
            raise RuntimeError(f"customer_workspace_failed:{workspace_after_failure.status_code}")
        workspace_failure_payload = workspace_after_failure.json()

        retry_response = client.post(
            f"/v1/ops/invoices/{issued_invoice['invoice_id']}/retry-payment",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={},
        )
        if retry_response.status_code != 200:
            raise RuntimeError(f"invoice_retry_failed:{retry_response.status_code}")

        fake_stripe.Webhook.current_event = {
            "id": "evt_uat_paid",
            "type": "invoice.paid",
            "data": {"object": {"id": issued_invoice["provider_invoice_ref"], "payment_intent": "pi_paid_uat"}},
        }
        paid_response = client.post("/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "sig_uat"})
        if paid_response.status_code != 200:
            raise RuntimeError(f"paid_webhook_failed:{paid_response.status_code}")
        paid_payload = paid_response.json()

        lifecycle_recovery = client.post(
            "/v1/ops/lifecycle-automation/sync",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"account_id": customer_actor_id},
        )
        if lifecycle_recovery.status_code != 200:
            raise RuntimeError(f"lifecycle_sync_recovery_failed:{lifecycle_recovery.status_code}")

        customer_invoice = client.get(
            f"/v1/customer/invoices/{issued_invoice['invoice_id']}",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        if customer_invoice.status_code != 200:
            raise RuntimeError(f"customer_invoice_detail_failed:{customer_invoice.status_code}")

        workspace_after_recovery = client.get("/v1/customer/workspace", headers={"Authorization": f"Bearer {customer_token}"})
        ops_summary = client.get("/v1/ops/commercialization-summary", headers={"Authorization": f"Bearer {reviewer_token}"})
        if workspace_after_recovery.status_code != 200 or ops_summary.status_code != 200:
            raise RuntimeError("commercialization_projection_failed")

        workspace_recovery_payload = workspace_after_recovery.json()
        ops_summary_payload = ops_summary.json()

        checkpoints = [
        {
            "label": "invoice_preview_available",
            "passed": float(invoice_preview.get("total_due_usd") or 0.0) > 0.0,
        },
        {
            "label": "formal_invoice_issued",
            "passed": str(issued_invoice.get("status") or "") == "issued" and bool(issued_invoice.get("hosted_invoice_url")),
        },
        {
            "label": "payment_failure_recorded",
            "passed": str((failed_payload.get("invoice") or {}).get("status") or "") == "failed",
        },
        {
            "label": "dunning_open_after_failure",
            "passed": str((workspace_failure_payload.get("dunning_summary") or {}).get("status") or "") == "open",
        },
        {
            "label": "renewal_due_visible",
            "passed": str((workspace_failure_payload.get("renewal_summary") or {}).get("status") or "") == "renewal_due",
        },
        {
            "label": "upgrade_recommendation_visible",
            "passed": bool((workspace_failure_payload.get("expansion_summary") or {}).get("recommended_plan_id")),
        },
        {
            "label": "payment_recovery_recorded",
            "passed": str((paid_payload.get("invoice") or {}).get("status") or "") == "paid",
        },
        {
            "label": "customer_invoice_paid_view",
            "passed": str((customer_invoice.json().get("invoice") or {}).get("status") or "") == "paid",
        },
        {
            "label": "ops_summary_contains_lifecycle_counts",
            "passed": all(
                key in ops_summary_payload
                for key in ("renewal_due_accounts", "dunning_runs", "pilot_conversion", "expansion_candidates", "churn_risk_accounts")
            ),
        },
    ]

        summary = {
        "run_id": run_id,
        "generated_at": _utcnow(),
        "environment": "mock_stripe_local",
        "account_id": customer_actor_id,
        "customer_account_id": customer_account["customer_account_id"],
        "journey": {
            "invoice_preview": {
                "invoice_preview_id": invoice_preview.get("invoice_preview_id"),
                "status_counts": preview_payload.get("summary", {}).get("status_counts", {}),
                "total_due_usd": invoice_preview.get("total_due_usd"),
                "line_items": invoice_preview.get("line_items_json", []),
            },
            "issued_invoice": dict(issue_response.json()["invoice"]),
            "failed_invoice": dict(failed_payload.get("invoice") or {}),
            "retry_attempt": dict(retry_response.json().get("payment_retry_attempt") or {}),
            "paid_invoice": dict(paid_payload.get("invoice") or {}),
            "lifecycle_after_failure": {
                "renewal_summary": workspace_failure_payload.get("renewal_summary", {}),
                "dunning_summary": workspace_failure_payload.get("dunning_summary", {}),
                "pilot_conversion_summary": workspace_failure_payload.get("pilot_conversion_summary", {}),
                "expansion_summary": workspace_failure_payload.get("expansion_summary", {}),
                "churn_risk_summary": workspace_failure_payload.get("churn_risk_summary", {}),
            },
            "lifecycle_after_recovery": {
                "renewal_summary": workspace_recovery_payload.get("renewal_summary", {}),
                "dunning_summary": workspace_recovery_payload.get("dunning_summary", {}),
                "pilot_conversion_summary": workspace_recovery_payload.get("pilot_conversion_summary", {}),
                "expansion_summary": workspace_recovery_payload.get("expansion_summary", {}),
                "churn_risk_summary": workspace_recovery_payload.get("churn_risk_summary", {}),
            },
            "ops_summary_excerpt": {
                "renewal_due_accounts": ops_summary_payload.get("renewal_due_accounts", {}),
                "dunning_runs": ops_summary_payload.get("dunning_runs", {}),
                "pilot_conversion": ops_summary_payload.get("pilot_conversion", {}),
                "expansion_candidates": ops_summary_payload.get("expansion_candidates", {}),
                "churn_risk_accounts": ops_summary_payload.get("churn_risk_accounts", {}),
            },
        },
        "acceptance": {
            "all_passed": all(item["passed"] for item in checkpoints),
            "checkpoint_count": len(checkpoints),
            "checkpoints": checkpoints,
        },
    }

        _write(base_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        _write(base_dir / "report.md", _summary_markdown(summary))
        _write(base_dir / "customer_signoff_packet.md", _delivery_packet_markdown(summary))

        latest_dir = base_dir.parent / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(base_dir, latest_dir)
        return summary
    finally:
        _restore_fake_stripe(fake_stripe_snapshot)
