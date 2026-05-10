from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .commercial_audit import CommercialAuditService
from .customer_workspace import CustomerWorkspaceService
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


class ProductionAcceptanceService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_workspace_service: CustomerWorkspaceService,
        production_signoff_service: ProductionSignoffService,
        audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.customer_workspace = customer_workspace_service
        self.production_signoff = production_signoff_service
        self.audit = audit_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _current_signoff(self, signoff_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if signoff_id:
            try:
                return self.production_signoff.signoff_detail(signoff_id=signoff_id)
            except KeyError:
                return None
        current = self.production_signoff.list_signoffs(limit=1).get("current_signoff")
        if not current:
            return None
        return self.production_signoff.signoff_detail(signoff_id=current["signoff_id"])

    def _section(self, *, status: str, summary: str, blockers: Optional[List[str]] = None, refs: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "status": status,
            "summary": summary,
            "blockers": list(blockers or []),
            "refs": list(refs or []),
        }

    def _workspace_readiness(self, payload: Dict[str, Any], *, signoff_detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        customer = dict(payload.get("customer_account") or {})
        billing_profile = dict(payload.get("billing_profile") or {})
        invoice_preview = dict(payload.get("invoice_preview") or {})
        campaign_summary = dict(payload.get("campaign_summary") or {})
        partner_perf = dict(payload.get("channel_partner_performance") or {})
        receipt_summary = dict(payload.get("receipt_summary") or {})
        handoff_summary = dict(payload.get("handoff_conversion_summary") or {})
        support_summary = dict(payload.get("support_summary") or {})
        dispute_summary = dict(payload.get("dispute_summary") or {})
        signoff = dict((signoff_detail or {}).get("signoff") or {})

        billing_blockers: List[str] = []
        if not billing_profile.get("billing_profile_id"):
            billing_blockers.append("billing_profile_missing")
        if invoice_preview.get("total_due_usd") is None:
            billing_blockers.append("invoice_preview_missing")
        billing_status = "ready" if not billing_blockers else "blocked"

        campaign_counts = dict(campaign_summary.get("status_counts") or {})
        campaign_blockers: List[str] = []
        if int(campaign_summary.get("campaign_count") or 0) <= 0:
            campaign_blockers.append("campaign_missing")
        elif int(campaign_counts.get("active") or 0) <= 0 and int(campaign_counts.get("approved") or 0) <= 0:
            campaign_blockers.append("campaign_not_approved")
        campaign_status = "ready" if not campaign_blockers else ("warning" if campaign_counts else "blocked")

        partner_blockers: List[str] = []
        if not list(partner_perf.get("allowlisted_channels") or []):
            partner_blockers.append("allowlisted_channel_missing")
        partner_status = "ready" if not partner_blockers else "blocked"

        receipt_blockers: List[str] = []
        if int(receipt_summary.get("receipt_count") or 0) <= 0 and int(handoff_summary.get("validated_handoff_count") or 0) <= 0:
            receipt_blockers.append("receipt_signal_missing")
        receipt_status = "ready" if not receipt_blockers else "blocked"

        support_issues = int(support_summary.get("status_counts", {}).get("open") or 0) + int(support_summary.get("status_counts", {}).get("in_progress") or 0)
        dispute_issues = int(dispute_summary.get("status_counts", {}).get("open") or 0) + int(dispute_summary.get("status_counts", {}).get("under_review") or 0) + int(dispute_summary.get("status_counts", {}).get("approved") or 0)
        support_status = "warning" if (support_issues or dispute_issues) else "ready"

        signoff_status = str(signoff.get("status") or "missing")
        signoff_blockers = [] if signoff_status == "fully_signed" else ["production_signoff_not_fully_signed"]
        signoff_section_status = "ready" if not signoff_blockers else "blocked"

        sections = {
            "billing": self._section(
                status=billing_status,
                summary=f"billing_profile {billing_profile.get('provider') or '-'} · invoice_due {invoice_preview.get('total_due_usd') or 0}",
                blockers=billing_blockers,
                refs=[billing_profile.get("billing_profile_id"), invoice_preview.get("invoice_preview_id")],
            ),
            "campaign": self._section(
                status=campaign_status,
                summary=f"campaign_count {campaign_summary.get('campaign_count') or 0} · active {campaign_counts.get('active') or 0} · approved {campaign_counts.get('approved') or 0}",
                blockers=campaign_blockers,
                refs=[customer.get("account_id")],
            ),
            "partner": self._section(
                status=partner_status,
                summary=f"allowlisted_channels {len(partner_perf.get('allowlisted_channels') or [])}",
                blockers=partner_blockers,
                refs=list(partner_perf.get("allowlisted_channels") or []),
            ),
            "receipt": self._section(
                status=receipt_status,
                summary=f"receipt_count {receipt_summary.get('receipt_count') or 0} · handoff {handoff_summary.get('validated_handoff_count') or 0} · conversion {handoff_summary.get('validated_conversion_count') or 0}",
                blockers=receipt_blockers,
                refs=[item.get("trace_id") for item in list(payload.get("linked_traces") or [])[:5] if item.get("trace_id")],
            ),
            "support": self._section(
                status=support_status,
                summary=f"support_open {support_issues} · dispute_open {dispute_issues}",
                blockers=[],
                refs=[customer.get("account_id")],
            ),
            "signoff": self._section(
                status=signoff_section_status,
                summary=f"production_signoff {signoff_status}",
                blockers=signoff_blockers,
                refs=[signoff.get("signoff_id")],
            ),
        }
        blocked_sections = [key for key, value in sections.items() if value["status"] == "blocked"]
        warning_sections = [key for key, value in sections.items() if value["status"] == "warning"]
        overall_status = "ready"
        if blocked_sections:
            overall_status = "blocked"
        elif warning_sections:
            overall_status = "candidate"
        return {
            "overall_status": overall_status,
            "blocked_sections": blocked_sections,
            "warning_sections": warning_sections,
            "sections": sections,
        }

    def _sync_launch_wave(self, *, launch_wave: str) -> Dict[str, Any]:
        ready_accounts = self.repository.list_go_live_ready_accounts(launch_wave=launch_wave, limit=500)
        existing = next(iter(self.repository.list_launch_wave_statuses(launch_wave=launch_wave, limit=1)), None)
        status_counts: Dict[str, int] = {}
        account_ids: List[str] = []
        for item in ready_accounts:
            status = str(item.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            if item.get("account_id"):
                account_ids.append(str(item["account_id"]))
        current_status = "planned"
        existing_status = str((existing or {}).get("status") or "")
        if existing_status in {"armed", "active", "rollback_watch"}:
            current_status = existing_status
        if status_counts.get("launched"):
            current_status = "active"
        elif status_counts.get("blocked") and existing_status not in {"armed", "active", "rollback_watch"}:
            current_status = "blocked"
        elif status_counts.get("ready") and existing_status not in {"armed", "active", "rollback_watch"}:
            current_status = "planned"
        return self.repository.save_launch_wave_status(
            {
                "launch_wave_status_id": (existing or {}).get("launch_wave_status_id"),
                "launch_wave": launch_wave,
                "status": current_status,
                "target_environment": "production",
                "wave_payload": {
                    "account_count": len(ready_accounts),
                    "status_counts": status_counts,
                    "account_ids": account_ids[:25],
                },
            }
        )

    def generate_acceptance_record(
        self,
        *,
        actor_id: str,
        actor_role: str,
        account_id: str,
        launch_wave: str = "wave_1",
        signoff_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        workspace = self.customer_workspace.workspace(account_id=account_id)
        customer = dict(workspace.get("customer_account") or {})
        signoff_detail = self._current_signoff(signoff_id=signoff_id)
        readiness = self._workspace_readiness(workspace, signoff_detail=signoff_detail)
        record = self.repository.save_production_customer_acceptance_record(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "signoff_id": (signoff_detail or {}).get("signoff", {}).get("signoff_id"),
                "launch_wave": launch_wave,
                "status": readiness["overall_status"],
                "readiness_summary": readiness,
                "acceptance_payload": {
                    "customer_account": customer,
                    "plan": workspace.get("plan"),
                    "billing_profile": workspace.get("billing_profile"),
                    "campaign_summary": workspace.get("campaign_summary"),
                    "channel_partner_performance": workspace.get("channel_partner_performance"),
                    "receipt_summary": workspace.get("receipt_summary"),
                    "handoff_conversion_summary": workspace.get("handoff_conversion_summary"),
                    "support_summary": workspace.get("support_summary"),
                    "dispute_summary": workspace.get("dispute_summary"),
                },
            }
        )
        ready_status = "ready" if readiness["overall_status"] == "ready" else ("blocked" if readiness["overall_status"] == "blocked" else "candidate")
        ready_account = self.repository.save_go_live_ready_account(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "acceptance_record_id": record["acceptance_record_id"],
                "launch_wave": launch_wave,
                "status": ready_status,
                "readiness_payload": readiness,
            }
        )
        wave_status = self._sync_launch_wave(launch_wave=launch_wave)
        result = {
            "acceptance_record": record,
            "go_live_ready_account": ready_account,
            "launch_wave_status": wave_status,
        }
        self.audit.record_audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=account_id,
            object_type="production_customer_acceptance",
            object_id=record["acceptance_record_id"],
            action_type="production_acceptance_generated",
            source_surface="ops",
            customer_visible_payload={},
            internal_payload=result,
        )
        return result

    def acceptance_record_detail(self, *, acceptance_record_id: str) -> Dict[str, Any]:
        record = self.repository.get_production_customer_acceptance_record(acceptance_record_id)
        ready = next(
            (item for item in self.repository.list_go_live_ready_accounts(account_id=record["account_id"], launch_wave=record["launch_wave"], limit=50) if item.get("acceptance_record_id") == acceptance_record_id),
            None,
        )
        launch_wave_status = next(
            iter(self.repository.list_launch_wave_statuses(launch_wave=record["launch_wave"], limit=1)),
            None,
        )
        signoff = None
        if record.get("signoff_id"):
            try:
                signoff = self.production_signoff.signoff_detail(signoff_id=record["signoff_id"])
            except KeyError:
                signoff = None
        return {
            "acceptance_record": record,
            "go_live_ready_account": ready,
            "launch_wave_status": launch_wave_status,
            "production_signoff": signoff,
        }

    def list_acceptance_records(
        self,
        *,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        records = self.repository.list_production_customer_acceptance_records(launch_wave=launch_wave, status=status, limit=limit)
        waves = self.repository.list_launch_wave_statuses(limit=25)
        ready_accounts = self.repository.list_go_live_ready_accounts(launch_wave=launch_wave, status=status if status in {"ready", "candidate", "blocked", "launched"} else None, limit=100)
        return {
            "acceptance_records": records,
            "go_live_ready_accounts": ready_accounts,
            "launch_waves": waves,
            "summary": {
                "acceptance_record_count": len(records),
                "go_live_ready_count": len([item for item in ready_accounts if str(item.get("status") or "") == "ready"]),
                "blocked_go_live_count": len([item for item in ready_accounts if str(item.get("status") or "") == "blocked"]),
                "launch_wave_count": len(waves),
            },
        }

    def update_launch_wave_status(
        self,
        *,
        actor_id: str,
        actor_role: str,
        launch_wave: str,
        status: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = next(iter(self.repository.list_launch_wave_statuses(launch_wave=launch_wave, limit=1)), None)
        current_payload = dict((existing or {}).get("wave_payload_json") or {})
        current_payload["note"] = note
        row = self.repository.save_launch_wave_status(
            {
                "launch_wave_status_id": (existing or {}).get("launch_wave_status_id"),
                "launch_wave": launch_wave,
                "status": status,
                "target_environment": (existing or {}).get("target_environment") or "production",
                "wave_payload": current_payload,
            }
        )
        self.audit.record_audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=None,
            object_type="launch_wave_status",
            object_id=row["launch_wave_status_id"],
            action_type="launch_wave_status_updated",
            source_surface="ops",
            customer_visible_payload={},
            internal_payload={"launch_wave": launch_wave, "status": status, "note": note},
        )
        return {"launch_wave_status": row}
