from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .auth import AuthService
from .commercial_billing import CommercialBillingService
from .customer_accounts import CustomerAccountService
from .customer_campaigns import CustomerCampaignService
from .observability import ObservabilityService
from .partner_readiness import PartnerReadinessService
from .production_acceptance import ProductionAcceptanceService
from .production_handshake_pack import ProductionHandshakePackService
from .production_launch_week_pack import ProductionLaunchWeekPackService
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]

OWNER_ASSIGNMENTS = {
    "billing_005": {"owner_actor_id": "ops_stripe_owner", "actor_role": "ops", "display_name": "Stripe Owner"},
    "webhook_001": {"owner_actor_id": "ops_infra_owner", "actor_role": "ops", "display_name": "Infra Owner"},
    "security_003": {"owner_actor_id": "ops_security_owner", "actor_role": "ops", "display_name": "Security Owner"},
    "operations_003": {"owner_actor_id": "ops_support_finance_owner", "actor_role": "ops", "display_name": "Support Finance Owner"},
    "deploy_002": {"owner_actor_id": "ops_db_owner", "actor_role": "ops", "display_name": "DB Owner"},
}

MANUAL_EVIDENCE_MAP = {
    "billing_005": {
        "paths": [
            "artifacts/production_cutover_pack/latest/checks/stripe_connectivity_check.json",
            "artifacts/production_cutover_pack/latest/checks/invoice_issuance_smoke.json",
            "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
        ],
        "summary": "launch_execution_prep:billing_005",
        "note": "Launch prep attached current billing/provider evidence; live key confirmation still requires human signoff.",
    },
    "webhook_001": {
        "paths": [
            "artifacts/production_cutover_pack/latest/checks/webhook_health_check.json",
            "artifacts/production_cutover_pack/latest/checks/payment_sync_smoke.json",
            "docs/webhook_replay_runbook.md",
        ],
        "summary": "launch_execution_prep:webhook_001",
        "note": "Launch prep attached webhook and replay evidence; production endpoint registration still requires human signoff.",
    },
    "security_003": {
        "paths": [
            "artifacts/production_go_live_checklist/latest/go_live_checklist.json",
            "docs/production_go_live_checklist.md",
            "artifacts/production_manual_signoff/latest/manual_signoff_sheet.json",
        ],
        "summary": "launch_execution_prep:security_003",
        "note": "Launch prep attached customer-safe logging / retention review evidence pointers; production sink review still requires human signoff.",
    },
    "operations_003": {
        "paths": [
            "artifacts/production_launch_week_pack/latest/docs/support_triage_matrix.md",
            "artifacts/production_launch_week_pack/latest/docs/incident_escalation_matrix.md",
            "artifacts/production_launch_week_pack/latest/docs/week_1_ops_board.md",
        ],
        "summary": "launch_execution_prep:operations_003",
        "note": "Launch prep attached support / finance / escalation operating docs; named staffing still requires human signoff.",
    },
    "deploy_002": {
        "paths": [
            "artifacts/production_cutover_pack/latest/checks/backup_restore_verification_hooks.json",
            "docs/rollback_runbook.md",
            "docs/cutover_runbook.md",
        ],
        "summary": "launch_execution_prep:deploy_002",
        "note": "Launch prep attached rollback and backup/restore evidence; operator access still requires human signoff.",
    },
}


class LaunchExecutionPrepService:
    def __init__(
        self,
        *,
        repository: SQLAlchemyPlatformRepository,
        auth_service: AuthService,
        customer_account_service: CustomerAccountService,
        customer_campaign_service: CustomerCampaignService,
        partner_readiness_service: PartnerReadinessService,
        commercial_billing_service: CommercialBillingService,
        observability_service: ObservabilityService,
        production_signoff_service: ProductionSignoffService,
        production_acceptance_service: ProductionAcceptanceService,
        production_launch_week_pack_service: ProductionLaunchWeekPackService,
        production_handshake_pack_service: ProductionHandshakePackService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.auth = auth_service
        self.customer_accounts = customer_account_service
        self.customer_campaigns = customer_campaign_service
        self.partner_readiness = partner_readiness_service
        self.commercial_billing = commercial_billing_service
        self.observability = observability_service
        self.production_signoff = production_signoff_service
        self.production_acceptance = production_acceptance_service
        self.production_launch_week_pack = production_launch_week_pack_service
        self.production_handshake_pack = production_handshake_pack_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_identity(self, *, actor_id: str, actor_role: str, display_name: str) -> Dict[str, Any]:
        return self.auth.register_identity(
            actor_id=actor_id,
            actor_role=actor_role,
            password="secret123",
            account_id=actor_id if actor_role in {"reader", "customer"} else None,
            display_name=display_name,
        )["identity"]

    def _ensure_launch_candidate(self, *, account_id: str) -> Dict[str, Any]:
        self.customer_accounts.ensure_customer_account(
            account_id=account_id,
            display_name="Launch Candidate Wave 1",
            plan_id="creator_pass",
            status="active",
        )
        self.customer_accounts.upsert_billing_profile(
            customer_account_id=f"cust_{account_id}",
            account_id=account_id,
            provider="internal_preview",
            invoice_email="launch-ops@example.test",
            legal_name="Launch Candidate Ltd",
            billing_country="GB",
            tax_status="pending",
        )
        self.partner_readiness.upsert_partner(
            {
                "partner_id": "partner_launch_candidate",
                "name": "Launch Candidate Partner",
                "lifecycle_status": "active",
                "sla_status": "gold",
                "receipt_capability": "ready",
                "disclosure_readiness": "ready",
                "billing_readiness": "ready",
                "allowlisted_channels": ["email"],
                "endpoint_health_status": "healthy",
                "capabilities": [],
            }
        )
        self.customer_campaigns.create_or_update_campaign(
            account_id=account_id,
            payload={
                "title": "Launch Candidate Campaign",
                "target_icp_vertical": "B2B SaaS",
                "cta_text": "book demo",
                "disclosure_text": "Sponsored production pilot outreach.",
                "selected_channels": ["email"],
                "selected_partner_refs": ["partner_launch_candidate"],
                "proof_points": ["validated handoff", "validated conversion"],
                "proof_source_urls": ["https://example.test/proof/launch"],
                "proof_artifact_refs": ["artifact://launch-proof"],
                "activation_status": "active",
            },
        )
        self.repository.save_quality_event(
            {
                "event_id": f"quality_event_launch_{account_id}",
                "trace_id": f"trace_launch_{account_id}",
                "event_type": "chapter_quality_evaluated",
                "source_surface": "reader",
                "status": "passed",
                "world_version_id": "urban_mystery_lotus_lane@0.1.0",
                "session_id": f"session_launch_{account_id}",
                "source_ref": {"kind": "chapter", "account_id": account_id},
                "payload": {"reason_codes": ["supported"]},
            }
        )
        self.observability.record_runtime_receipt(
            surface="reader",
            action="continue_story",
            response_status="ok",
            world_id="urban_mystery_lotus_lane",
            world_version_id="urban_mystery_lotus_lane@0.1.0",
            session_id=f"session_launch_{account_id}",
            account_id=account_id,
            reader_id=account_id,
            candidate_batch={"debug": {}},
            rendered_scene={"debug": {}},
            reader_view={"body": "Launch execution prep canonical reader output."},
            estimated_cost=0.01,
            runtime_latency_ms=10.0,
            trace_id=f"trace_launch_{account_id}",
            quality_event_id=f"quality_event_launch_{account_id}",
        )
        self.repository.save_quality_feedback_item(
            {
                "feedback_item_id": f"feedback_launch_{account_id}",
                "feedback_type": "explicit_user_feedback",
                "signal": "explicit_positive",
                "source_surface": "reader",
                "trace_id": f"trace_launch_{account_id}",
                "account_id": account_id,
                "world_version_id": "urban_mystery_lotus_lane@0.1.0",
                "session_id": f"session_launch_{account_id}",
                "source_ref": {"kind": "session", "account_id": account_id},
                "payload": {"reason_code": "useful"},
            }
        )
        preview = self.commercial_billing.invoice_preview(account_id=account_id)
        return {
            "account_id": account_id,
            "customer_account": self.customer_accounts.customer_account_detail(account_id=account_id)["customer_account"],
            "invoice_preview": preview,
        }

    def _ensure_signoff(self, *, actor_id: str, actor_role: str, launch_label: str, due_in_days: int) -> Dict[str, Any]:
        current = self.production_signoff.current_signoff_summary()
        if current and current.get("signoff_id"):
            return self.production_signoff.signoff_detail(signoff_id=current["signoff_id"])
        created = self.production_signoff.initialize_signoff_run(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_label=launch_label,
            due_in_days=due_in_days,
        )
        return self.production_signoff.signoff_detail(signoff_id=created["signoff"]["signoff_id"])

    def _maybe_attach_manual_prep(self, *, actor_id: str, actor_role: str, detail: Dict[str, Any]) -> Dict[str, Any]:
        evidence_rows = list(detail.get("evidence") or [])
        by_item_id: Dict[str, List[Dict[str, Any]]] = {}
        for row in evidence_rows:
            by_item_id.setdefault(str(row.get("signoff_item_id") or ""), []).append(row)
        prepared_items: List[Dict[str, Any]] = []
        for item in list(detail.get("items") or []):
            item_code = str(item.get("item_code") or "")
            if item_code not in OWNER_ASSIGNMENTS:
                continue
            assignment = OWNER_ASSIGNMENTS[item_code]
            if str(item.get("owner_actor_id") or "") != assignment["owner_actor_id"]:
                updated = self.production_signoff.assign_signoff_item_owner(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    signoff_item_id=item["signoff_item_id"],
                    owner_actor_id=assignment["owner_actor_id"],
                )
                item = updated["item"]
            evidence_spec = MANUAL_EVIDENCE_MAP[item_code]
            existing_summaries = {str(row.get("summary") or "") for row in by_item_id.get(str(item["signoff_item_id"]), [])}
            if evidence_spec["summary"] not in existing_summaries:
                self.production_signoff.append_signoff_evidence(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    signoff_item_id=item["signoff_item_id"],
                    evidence_type="artifact_ref",
                    summary=evidence_spec["summary"],
                    source_ref={"paths": evidence_spec["paths"]},
                    payload={"note": evidence_spec["note"], "paths": evidence_spec["paths"]},
                    customer_safe=False,
                )
            if str(item.get("status") or "") == "pending":
                self.production_signoff.decide_signoff_item(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    signoff_item_id=item["signoff_item_id"],
                    decision="ready_for_review",
                    note="launch_execution_prep_attached_current_evidence_awaiting_human_confirmation",
                )
            prepared_items.append({"item_code": item_code, "owner_actor_id": assignment["owner_actor_id"]})
        refreshed = self.production_signoff.signoff_detail(signoff_id=detail["signoff"]["signoff_id"])
        return {"detail": refreshed, "prepared_items": prepared_items}

    def _ensure_cutover_window(self, *, actor_id: str, actor_role: str, detail: Dict[str, Any], launch_wave: str) -> Dict[str, Any]:
        existing = list(detail.get("cutover_windows") or [])
        if existing:
            return existing[0]
        starts_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0).isoformat()
        ends_at = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
        window = self.production_signoff.mark_cutover_window(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_id=detail["signoff"]["signoff_id"],
            launch_wave=launch_wave,
            target_environment="production",
            starts_at=starts_at,
            ends_at=ends_at,
            rollback_owner_role="db_owner",
            status="planned",
            payload={"source": "launch_execution_prep", "cutover_pack": "artifacts/production_cutover_pack/latest/summary.json"},
        )
        return window["cutover_window"]

    def _prep_report(self, summary: Dict[str, Any]) -> str:
        signoff = summary["signoff"]["signoff"]
        acceptance = summary["acceptance"]["acceptance_record"]
        wave = summary["acceptance"]["launch_wave_status"]
        lines = [
            "# Launch Execution Prep",
            "",
            f"- generated_at: {summary['generated_at']}",
            f"- account_id: {summary['seeded_launch_customer']['account_id']}",
            f"- signoff_id: {signoff['signoff_id']}",
            f"- signoff_status: {signoff['status']}",
            f"- acceptance_record_id: {acceptance['acceptance_record_id']}",
            f"- acceptance_status: {acceptance['status']}",
            f"- launch_wave: {wave['launch_wave']}",
            f"- launch_wave_status: {wave['status']}",
            f"- handshake_bundle: {summary['handshake_pack']['bundle_id']}",
            "",
            "## Manual Signoff Prep",
        ]
        for item in summary["prepared_items"]:
            lines.append(f"- {item['item_code']} -> {item['owner_actor_id']}")
        lines.extend(
            [
                "",
                "## Notes",
                "- Manual items were moved to `ready_for_review` when evidence was attached.",
                "- No manual item was auto-approved.",
                "- Launch acceptance may remain blocked until human signoff completes.",
            ]
        )
        return "\n".join(lines)

    def run(
        self,
        *,
        actor_id: str = "ops_launch_executor",
        actor_role: str = "reviewer",
        launch_label: str = "production_launch_prep",
        account_id: str = "acct_launch_customer_wave1",
        launch_wave: str = "wave_1",
        due_in_days: int = 2,
        output_root: str | Path | None = None,
    ) -> Dict[str, Any]:
        self._ensure_identity(actor_id=actor_id, actor_role=actor_role, display_name="Launch Executor")
        for assignment in OWNER_ASSIGNMENTS.values():
            self._ensure_identity(
                actor_id=assignment["owner_actor_id"],
                actor_role=assignment["actor_role"],
                display_name=assignment["display_name"],
            )

        seeded_launch_customer = self._ensure_launch_candidate(account_id=account_id)
        signoff_detail = self._ensure_signoff(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_label=launch_label,
            due_in_days=due_in_days,
        )
        cutover_window = self._ensure_cutover_window(
            actor_id=actor_id,
            actor_role=actor_role,
            detail=signoff_detail,
            launch_wave=launch_wave,
        )

        acceptance = self.production_acceptance.generate_acceptance_record(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=account_id,
            launch_wave=launch_wave,
            signoff_id=signoff_detail["signoff"]["signoff_id"],
        )
        self.production_acceptance.update_launch_wave_status(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_wave=launch_wave,
            status=str(acceptance["launch_wave_status"].get("status") or "blocked"),
            note="launch execution prep seeded; awaiting human production signoff",
        )
        launch_week_pack = self.production_launch_week_pack.build_pack()
        prepared = self._maybe_attach_manual_prep(actor_id=actor_id, actor_role=actor_role, detail=signoff_detail)
        signoff_detail = prepared["detail"]
        signoff_export = self.production_signoff.export_signoff_record(signoff_id=signoff_detail["signoff"]["signoff_id"])
        handshake_pack = self.production_handshake_pack.build_pack()

        summary = {
            "generated_at": self._utcnow(),
            "seeded_launch_customer": seeded_launch_customer,
            "signoff": self.production_signoff.signoff_detail(signoff_id=signoff_detail["signoff"]["signoff_id"]),
            "prepared_items": prepared["prepared_items"],
            "cutover_window": cutover_window,
            "acceptance": acceptance,
            "launch_week_pack": launch_week_pack,
            "signoff_export": signoff_export,
            "handshake_pack": handshake_pack,
        }

        run_id = f"launch_execution_prep_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = Path(output_root) if output_root else (self._artifacts_root() / "launch_execution_prep" / run_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(bundle_dir / "summary.json", summary)
        self._write_text(bundle_dir / "report.md", self._prep_report(summary))
        latest_dir = self._artifacts_root() / "launch_execution_prep" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "run_id": run_id,
            "bundle_dir": str(bundle_dir),
            "latest_dir": str(latest_dir),
            **summary,
        }
