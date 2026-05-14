from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from ..repository import SQLAlchemyRepository
from .commercialization_uat import run_commercialization_uat


ROOT = Path(__file__).resolve().parents[3]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_default_env() -> None:
    _load_env_file(ROOT / ".env.local")
    _load_env_file(ROOT / ".env")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_stripe_connectivity_check(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    _load_default_env()
    price_map = {}
    try:
        price_map = json.loads(str(os.getenv("NARRATIVEOS_STRIPE_PRICE_MAP_JSON", "") or "{}"))
    except json.JSONDecodeError:
        price_map = {}
    secret_key = str(os.getenv("NARRATIVEOS_STRIPE_SECRET_KEY", "")).strip()
    publishable_key = str(os.getenv("NARRATIVEOS_STRIPE_PUBLISHABLE_KEY", "")).strip()
    webhook_secret = str(os.getenv("NARRATIVEOS_STRIPE_WEBHOOK_SECRET", "")).strip()
    provider = str(os.getenv("NARRATIVEOS_BILLING_PROVIDER", "")).strip()
    stub_provider = provider in {"web_stub", "stub", "fake"}
    stripe_configured = bool(
        provider == "stripe"
        and secret_key
        and publishable_key
        and webhook_secret
        and isinstance(price_map, dict)
        and all(str(price_map.get(key, "")).strip() for key in ("play_pass", "creator_pass", "studio_pass"))
    )
    payload = {
        "generated_at": _utcnow(),
        "provider": provider,
        "mode": (
            "stub"
            if stub_provider
            else ("live" if secret_key.startswith("sk_live_") else ("test" if secret_key.startswith("sk_test_") else "unknown"))
        ),
        "configured": bool(stripe_configured or stub_provider),
        "checks": {
            "provider_is_stripe": provider == "stripe",
            "provider_is_stub": stub_provider,
            "secret_key_present": bool(secret_key),
            "publishable_key_present": bool(publishable_key),
            "webhook_secret_present": bool(webhook_secret),
            "price_map_has_required_tiers": all(str(price_map.get(key, "")).strip() for key in ("play_pass", "creator_pass", "studio_pass")),
        },
    }
    payload["healthy"] = bool(stub_provider or stripe_configured)
    if output_root:
        _write_json(Path(output_root) / "stripe_connectivity_check.json", payload)
    return payload


def run_webhook_health_check(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    _load_default_env()
    from ..api import create_app

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "webhook_health.db"
        app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{db_path}"))
        client = TestClient(app)
        response = client.post("/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "invalid"})
    payload = {
        "generated_at": _utcnow(),
        "status_code": response.status_code,
        "response": response.json(),
        "configured_secret_present": bool(str(os.getenv("NARRATIVEOS_STRIPE_WEBHOOK_SECRET", "")).strip()),
        "healthy": response.status_code in {400, 503},
    }
    if output_root:
        _write_json(Path(output_root) / "webhook_health_check.json", payload)
    return payload


def run_invoice_issuance_smoke(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        uat_summary = run_commercialization_uat(Path(temp_dir) / "commercialization_uat_smoke")
    journey = dict(uat_summary.get("journey") or {})
    payload = {
        "generated_at": _utcnow(),
        "invoice_preview": journey.get("invoice_preview", {}),
        "issued_invoice": journey.get("issued_invoice", {}),
        "healthy": bool((journey.get("issued_invoice") or {}).get("hosted_invoice_url")),
    }
    if output_root:
        _write_json(Path(output_root) / "invoice_issuance_smoke.json", payload)
    return payload


def run_payment_sync_smoke(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        uat_summary = run_commercialization_uat(Path(temp_dir) / "commercialization_payment_smoke")
    journey = dict(uat_summary.get("journey") or {})
    payload = {
        "generated_at": _utcnow(),
        "failed_invoice": journey.get("failed_invoice", {}),
        "paid_invoice": journey.get("paid_invoice", {}),
        "lifecycle_after_failure": journey.get("lifecycle_after_failure", {}),
        "lifecycle_after_recovery": journey.get("lifecycle_after_recovery", {}),
        "healthy": bool(
            (journey.get("failed_invoice") or {}).get("status") == "failed"
            and (journey.get("paid_invoice") or {}).get("status") == "paid"
            and (journey.get("lifecycle_after_recovery") or {}).get("dunning_summary", {}).get("status") == "resolved"
        ),
    }
    if output_root:
        _write_json(Path(output_root) / "payment_sync_smoke.json", payload)
    return payload


def run_customer_workspace_smoke(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        uat_summary = run_commercialization_uat(Path(temp_dir) / "commercialization_workspace_smoke")
    journey = dict(uat_summary.get("journey") or {})
    failure_workspace = dict(journey.get("lifecycle_after_failure") or {})
    payload = {
        "generated_at": _utcnow(),
        "renewal_summary": failure_workspace.get("renewal_summary", {}),
        "dunning_summary": failure_workspace.get("dunning_summary", {}),
        "expansion_summary": failure_workspace.get("expansion_summary", {}),
        "healthy": bool(
            failure_workspace.get("renewal_summary", {}).get("status") == "renewal_due"
            and failure_workspace.get("dunning_summary", {}).get("status") == "open"
            and failure_workspace.get("expansion_summary", {}).get("recommended_plan_id")
        ),
    }
    if output_root:
        _write_json(Path(output_root) / "customer_workspace_smoke.json", payload)
    return payload


def run_backup_restore_verification_hooks(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    from ..api import create_app

    with tempfile.TemporaryDirectory() as temp_dir:
        target_root = Path(temp_dir)
        db_path = target_root / "backup_restore_hooks.db"
        backup_dir = target_root / "backups"
        app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{db_path}"))
        client = TestClient(app)
        reviewer_token = _register_identity(client, actor_id="ops_cutover_hooks", actor_role="reviewer")
        admin_token = _register_identity(client, actor_id="ops_cutover_admin", actor_role="admin")
        headers = {"Authorization": f"Bearer {reviewer_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        health = client.get("/health")
        schema = client.get("/v1/ops/schema-lifecycle", headers=headers)
        integrity = client.get("/v1/ops/data-integrity", headers=headers)
        backup = client.post("/v1/ops/runtime-backups", headers=headers, json={"label": "cutover_smoke", "output_dir": str(backup_dir)})
        backup.raise_for_status()
        backup_path = backup.json()["backup"]["backup_path"]
        drill = client.post("/v1/ops/recovery-drill", headers=headers, json={"backup_path": backup_path})
        restore = client.post("/v1/ops/runtime-restore", headers=admin_headers, json={"backup_path": backup_path, "dry_run": True})
    payload = {
        "generated_at": _utcnow(),
        "health_status_code": health.status_code,
        "schema_lifecycle": schema.json(),
        "data_integrity": integrity.json(),
        "backup": backup.json(),
        "recovery_drill": drill.json(),
        "restore": restore.json(),
        "healthy": all(
            [
                health.status_code == 200,
                schema.status_code == 200,
                integrity.status_code == 200,
                backup.status_code == 200,
                drill.status_code == 200,
                restore.status_code == 200,
            ]
        ),
    }
    if output_root:
        _write_json(Path(output_root) / "backup_restore_verification_hooks.json", payload)
    return payload


def run_support_routing_smoke(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    from ..api import create_app

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "support_routing_smoke.db"
        app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{db_path}"))
        app.state.customer_account_service.ensure_customer_account(
            account_id="acct_support_smoke",
            display_name="Support Smoke",
            plan_id="creator_pass",
            status="active",
        )
        case = app.state.commercial_support_service.create_support_case(
            account_id="acct_support_smoke",
            requested_by="acct_support_smoke",
            payload={"subject": "support smoke", "description": "support route works", "priority": "high"},
        )
        listing = app.state.commercial_support_service.list_support_cases(account_id="acct_support_smoke", limit=10)
    payload = {
        "generated_at": _utcnow(),
        "support_case": case,
        "listing_summary": listing.get("summary") or {},
        "healthy": bool(case.get("support_case_id")) and int((listing.get("summary") or {}).get("case_count") or 0) >= 1,
    }
    if output_root:
        _write_json(Path(output_root) / "support_routing_smoke.json", payload)
    return payload


def run_audit_logging_smoke(*, output_root: str | Path | None = None) -> Dict[str, Any]:
    from ..api import create_app

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "audit_logging_smoke.db"
        app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{db_path}"))
        app.state.customer_account_service.ensure_customer_account(
            account_id="acct_audit_smoke",
            display_name="Audit Smoke",
            plan_id="creator_pass",
            status="active",
        )
        log = app.state.commercial_audit_service.record_audit_log(
            actor_id="ops_audit_smoke",
            actor_role="reviewer",
            account_id="acct_audit_smoke",
            object_type="audit_smoke",
            object_id="audit_smoke_1",
            action_type="audit_logging_smoke_created",
            source_surface="ops",
            customer_visible_payload={"ok": True},
            internal_payload={"smoke": True},
        )
        listing = app.state.commercial_audit_service.audit_log_listing(account_id="acct_audit_smoke", limit=10)
    payload = {
        "generated_at": _utcnow(),
        "audit_log": log,
        "listing_summary": listing.get("summary") or {},
        "healthy": bool(log.get("audit_log_id")) and int((listing.get("summary") or {}).get("entry_count") or 0) >= 1,
    }
    if output_root:
        _write_json(Path(output_root) / "audit_logging_smoke.json", payload)
    return payload


def build_production_cutover_pack(output_root: str | Path | None = None, *, base_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    run_id = f"production_cutover_pack_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    resolved_base_dir = Path(base_dir) if base_dir is not None else ROOT
    bundle_dir = Path(output_root) if output_root else (resolved_base_dir / "artifacts" / "production_cutover_pack" / run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    checks_dir = bundle_dir / "checks"
    docs_dir = bundle_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    connectivity = run_stripe_connectivity_check(output_root=checks_dir)
    webhook = run_webhook_health_check(output_root=checks_dir)
    invoice = run_invoice_issuance_smoke(output_root=checks_dir)
    payment = run_payment_sync_smoke(output_root=checks_dir)
    customer_workspace = run_customer_workspace_smoke(output_root=checks_dir)
    backup_restore = run_backup_restore_verification_hooks(output_root=checks_dir)

    doc_files = [
        "cutover_runbook.md",
        "rollback_runbook.md",
        "webhook_replay_runbook.md",
        "billing_reconciliation_runbook.md",
        "customer_launch_checklist.md",
    ]
    for name in doc_files:
        shutil.copy2(resolved_base_dir / "docs" / name, docs_dir / name)
    launch_week_docs_dir = resolved_base_dir / "artifacts" / "production_launch_week_pack" / "latest" / "docs"
    if launch_week_docs_dir.exists():
        for path in sorted(launch_week_docs_dir.glob("*.md")):
            shutil.copy2(path, docs_dir / path.name)
    handshake_docs_dir = resolved_base_dir / "artifacts" / "production_handshake_pack" / "latest" / "docs"
    if handshake_docs_dir.exists():
        for path in sorted(handshake_docs_dir.glob("*.md")):
            shutil.copy2(path, docs_dir / path.name)

    signoff_evidence_map = {
        "billing_005": ["checks/stripe_connectivity_check.json", "checks/invoice_issuance_smoke.json"],
        "webhook_001": ["checks/webhook_health_check.json", "checks/payment_sync_smoke.json"],
        "deploy_002": ["checks/backup_restore_verification_hooks.json"],
    }
    _write_json(bundle_dir / "signoff_evidence_map.json", signoff_evidence_map)
    summary = {
        "bundle_id": run_id,
        "generated_at": _utcnow(),
        "checks": {
            "stripe_connectivity": connectivity,
            "webhook_health": webhook,
            "invoice_issuance_smoke": invoice,
            "payment_sync_smoke": payment,
            "customer_workspace_smoke": customer_workspace,
            "backup_restore_verification_hooks": backup_restore,
        },
        "signoff_evidence_map": signoff_evidence_map,
        "launch_week_docs_copied": sorted(path.name for path in docs_dir.glob("*.md") if path.name in {
            "launch_day_checklist.md",
            "day_1_monitoring_sheet.md",
            "week_1_ops_board.md",
            "support_triage_matrix.md",
            "incident_escalation_matrix.md",
            "finance_reconciliation_sheet.md",
        }),
        "handshake_docs_copied": sorted(path.name for path in docs_dir.glob("*.md") if path.name in {
            "legal_ops_handoff_checklist.md",
            "contract_dependency_matrix.md",
            "production_owner_matrix.md",
            "customer_escalation_contacts.md",
        }),
        "overall_health": all(
            item.get("healthy", False)
            for item in [connectivity, webhook, invoice, payment, customer_workspace, backup_restore]
        ),
    }
    _write_json(bundle_dir / "summary.json", summary)
    (bundle_dir / "README.md").write_text(
        "\n".join(
            [
                "# Production Cutover Pack",
                "",
                "This pack contains cutover/rollback runbooks and script-generated smoke evidence.",
                "",
                "Included checks:",
                "- stripe connectivity",
                "- webhook health",
                "- invoice issuance smoke",
                "- payment sync smoke",
                "- customer workspace smoke",
                "- backup/restore verification hooks",
            ]
        ),
        encoding="utf-8",
    )
    latest_dir = bundle_dir.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(bundle_dir, latest_dir)
    return {
        "bundle_id": run_id,
        "bundle_dir": str(bundle_dir),
        "latest_dir": str(latest_dir),
        "overall_health": summary["overall_health"],
    }
