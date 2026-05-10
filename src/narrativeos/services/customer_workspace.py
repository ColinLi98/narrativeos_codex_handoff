from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .commercial_billing import CommercialBillingService
from .commercial_audit import CommercialAuditService
from .commercial_lifecycle_automation import CommercialLifecycleAutomationService
from .commercial_support import CommercialSupportService
from .customer_accounts import CustomerAccountService
from .customer_campaigns import CustomerCampaignService
from .observability import ObservabilityService
from .ops_quality_projection import OpsQualityProjectionService
from .partner_readiness import PartnerReadinessService


class CustomerWorkspaceService:
    def __init__(
        self,
        *,
        customer_account_service: CustomerAccountService,
        customer_campaign_service: CustomerCampaignService,
        partner_readiness_service: PartnerReadinessService,
        commercial_billing_service: CommercialBillingService,
        commercial_audit_service: CommercialAuditService,
        commercial_support_service: CommercialSupportService,
        commercial_lifecycle_automation_service: CommercialLifecycleAutomationService,
        quality_projection_service: OpsQualityProjectionService,
        observability_service: ObservabilityService,
    ) -> None:
        self.customer_accounts = customer_account_service
        self.customer_campaigns = customer_campaign_service
        self.partner_readiness = partner_readiness_service
        self.commercial_billing = commercial_billing_service
        self.commercial_audit = commercial_audit_service
        self.commercial_support = commercial_support_service
        self.commercial_lifecycle = commercial_lifecycle_automation_service
        self.quality_projection = quality_projection_service
        self.observability = observability_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _workspace_payload(self, *, account_id: str, period_start: Optional[str] = None) -> Dict[str, Any]:
        account_detail = self.customer_accounts.customer_account_detail(account_id=account_id)
        campaign_bundle = self.customer_campaigns.list_campaigns(account_id=account_id, limit=20)
        invoice_preview = self.commercial_billing.invoice_preview(account_id=account_id, period_start=period_start)
        disputes = self.commercial_support.list_disputes(account_id=account_id, limit=25)
        support_cases = self.commercial_support.list_support_cases(account_id=account_id, limit=25)
        lifecycle_state = self.commercial_lifecycle.sync_account(account_id=account_id)
        quality_summary = self.quality_projection.quality_summary(account_id=account_id, limit=25)
        receipts = self.observability.list_runtime_receipts(account_id=account_id, limit=25)
        receipt_summary = self.observability.runtime_incident_snapshot(account_id=account_id, limit=10)
        latest_quality_events = list((quality_summary.get("events") or [])[:5])
        latest_receipts = receipts[:5]
        line_items = list((invoice_preview.get("invoice_preview") or {}).get("line_items_json") or [])
        lifecycle_summary = account_detail.get("lifecycle_summary") or {}
        lifecycle_automation_summary = dict((lifecycle_state.get("summary") or {}))
        renewal_tracker = dict(lifecycle_state.get("renewal_tracker") or {})
        dunning_run = dict(lifecycle_state.get("dunning_run") or {})
        pilot_track = dict(lifecycle_state.get("pilot_conversion_track") or {})
        expansion_candidate = dict(lifecycle_state.get("expansion_candidate") or {})
        churn_flag = dict(lifecycle_state.get("churn_risk_flag") or {})
        partner_mix: Dict[str, int] = {}
        allowlisted_channels = set()
        for detail in campaign_bundle.get("campaigns") or []:
            for target in detail.get("channel_targets") or []:
                partner_ref = str(target.get("partner_ref") or "").strip()
                if partner_ref:
                    try:
                        partner_detail = self.partner_readiness.partner_detail(partner_ref)
                        lifecycle = str((partner_detail.get("partner") or {}).get("lifecycle_status") or "unknown")
                        partner_mix[lifecycle] = partner_mix.get(lifecycle, 0) + 1
                        allowlisted_channels.update(list((partner_detail.get("partner") or {}).get("allowlisted_channels_json") or []))
                    except KeyError:
                        partner_mix["unknown"] = partner_mix.get("unknown", 0) + 1
        channel_partner_performance = {
            "channel_mix": dict((receipt_summary.get("by_surface") or {})),
            "partner_mix": partner_mix,
            "provider_mix": dict((receipt_summary.get("by_provider") or {})),
            "allowlisted_channels": sorted(allowlisted_channels),
        }
        handoff_conversion_summary = {
            "validated_presented_count": int((invoice_preview.get("usage_ledger") or {}).get("presented_count") or 0),
            "validated_handoff_count": int((invoice_preview.get("usage_ledger") or {}).get("handoff_count") or 0),
            "validated_conversion_count": int((invoice_preview.get("usage_ledger") or {}).get("conversion_count") or 0),
            "line_items": line_items,
        }
        dunning_payload = dict(dunning_run.get("dunning_payload_json") or {})
        expansion_payload = dict(expansion_candidate.get("candidate_payload_json") or {})
        churn_payload = dict(churn_flag.get("flag_payload_json") or {})
        renewal_summary = {
            "status": renewal_tracker.get("status") or lifecycle_automation_summary.get("renewal_status") or lifecycle_summary.get("renewal_tracker_status") or "stable",
            "renewal_due_at": lifecycle_summary.get("renewal_due_at"),
            "renewal_risk": lifecycle_summary.get("renewal_risk"),
            "customer_status": (account_detail.get("customer_account") or {}).get("status"),
        }
        dunning_summary = {
            "status": lifecycle_automation_summary.get("dunning_status") or lifecycle_summary.get("dunning_status") or "clear",
            "current_step": dunning_run.get("current_step"),
            "invoice_id": dunning_run.get("invoice_id"),
            "invoice_due_usd": dunning_payload.get("total_due_usd") or (invoice_preview.get("invoice_preview") or {}).get("total_due_usd") or 0.0,
            "retry_count": dunning_payload.get("retry_count") or 0,
            "hosted_invoice_url": dunning_payload.get("hosted_invoice_url"),
            "invoice_pdf_url": dunning_payload.get("invoice_pdf_url"),
        }
        pilot_conversion_summary = {
            "status": pilot_track.get("status") or lifecycle_automation_summary.get("pilot_conversion_status") or lifecycle_summary.get("pilot_conversion_status") or "watch",
            "active_campaign_count": (dict(pilot_track.get("track_payload_json") or {})).get("active_campaign_count") or 0,
            "validated_billable_count": (dict(pilot_track.get("track_payload_json") or {})).get("validated_billable_count") or 0,
        }
        expansion_summary = {
            "status": expansion_candidate.get("status") or lifecycle_automation_summary.get("expansion_status") or lifecycle_summary.get("expansion_status") or "clear",
            "trigger_type": expansion_candidate.get("trigger_type"),
            "recommended_plan_id": expansion_payload.get("recommended_plan_id") or lifecycle_automation_summary.get("recommended_plan_id") or lifecycle_summary.get("upgrade_recommendation_plan_id"),
            "active_overage_flag_count": expansion_payload.get("active_overage_flag_count") or 0,
            "invoice_due_usd": expansion_payload.get("invoice_due_usd") or 0.0,
        }
        churn_risk_summary = {
            "status": churn_flag.get("status") or lifecycle_automation_summary.get("churn_risk_status") or lifecycle_summary.get("churn_risk_status") or "stable",
            "risk_level": churn_flag.get("risk_level") or lifecycle_automation_summary.get("churn_risk_level") or lifecycle_summary.get("churn_risk_level") or "low",
            "open_disputes": churn_payload.get("open_disputes") or 0,
            "open_support_cases": churn_payload.get("open_support_cases") or 0,
            "latest_invoice_status": churn_payload.get("latest_invoice_status"),
        }
        campaign_summary = {
            "campaign_count": int((account_detail.get("customer_account") or {}).get("campaign_count") or 0),
            "campaign_limit": int((account_detail.get("customer_account") or {}).get("campaign_limit") or 0),
            "status_counts": dict((campaign_bundle.get("summary") or {}).get("status_counts") or {}),
            "activation_status": "active" if dict((campaign_bundle.get("summary") or {}).get("status_counts") or {}).get("active") else "campaign_workflow_pending",
        }
        return {
            "generated_at": self._utcnow(),
            "customer_account": account_detail.get("customer_account"),
            "plan": account_detail.get("plan"),
            "billing_profile": account_detail.get("billing_profile"),
            "lifecycle_summary": account_detail.get("lifecycle_summary"),
            "limit_posture": account_detail.get("limit_posture"),
            "campaign_summary": campaign_summary,
            "campaigns": [item.get("campaign") for item in campaign_bundle.get("campaigns") or []],
            "campaign_details": campaign_bundle.get("campaigns") or [],
            "channel_partner_performance": channel_partner_performance,
            "quality_summary": quality_summary.get("summary", {}),
            "groundedness_summary": quality_summary.get("groundedness_summary", {}),
            "feedback_summary": quality_summary.get("feedback_summary", {}),
            "receipt_summary": {
                "receipt_count": receipt_summary.get("receipt_count"),
                "incident_count": receipt_summary.get("incident_count"),
                "by_provider": receipt_summary.get("by_provider", {}),
                "by_surface": receipt_summary.get("by_surface", {}),
                "latency_summary": receipt_summary.get("latency_summary", {}),
                "latest_receipts": latest_receipts,
            },
            "handoff_conversion_summary": handoff_conversion_summary,
            "invoice_preview": invoice_preview.get("invoice_preview"),
            "credit_balance": invoice_preview.get("credit_balance"),
            "overage_flags": invoice_preview.get("overage_flags", []),
            "dispute_summary": disputes.get("summary", {}),
            "disputes": disputes.get("disputes", []),
            "support_summary": support_cases.get("summary", {}),
            "support_cases": support_cases.get("support_cases", []),
            "renewal_summary": renewal_summary,
            "dunning_summary": dunning_summary,
            "pilot_conversion_summary": pilot_conversion_summary,
            "expansion_summary": expansion_summary,
            "churn_risk_summary": churn_risk_summary,
            "lifecycle_automation": lifecycle_state,
            "latest_quality_events": latest_quality_events,
            "exports": {
                "available_reports": [
                    "workspace_json",
                    "workspace_csv",
                    "workspace_pdf",
                    "invoice_csv",
                ]
            },
        }

    def workspace(self, *, account_id: str, period_start: Optional[str] = None) -> Dict[str, Any]:
        payload = self._workspace_payload(account_id=account_id, period_start=period_start)
        payload["linked_traces"] = [
            {
                "trace_id": item.get("trace_id"),
                "status": item.get("status"),
                "source_surface": item.get("source_surface"),
                "overall_score": item.get("overall_score"),
                "grounding_status": item.get("grounding_status"),
            }
            for item in list(payload.get("latest_quality_events") or [])[:5]
            if item.get("trace_id")
        ]
        return payload

    def campaign_report(
        self,
        *,
        account_id: str,
        campaign_id: str,
        period_start: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self.workspace(account_id=account_id, period_start=period_start)
        bundle = self.customer_campaigns.campaign_detail(account_id=account_id, campaign_id=campaign_id)
        payload["campaign_summary"] = {
            **dict(payload.get("campaign_summary") or {}),
            "requested_campaign_id": campaign_id,
            "campaign_available": True,
            "activation_status": (bundle.get("campaign") or {}).get("activation_status"),
        }
        payload["selected_campaign"] = bundle
        return payload

    def _csv_rows(self, payload: Dict[str, Any]) -> List[str]:
        rows = [
            "section,key,value",
            f"account,account_id,{(payload.get('customer_account') or {}).get('account_id') or ''}",
            f"account,status,{(payload.get('lifecycle_summary') or {}).get('status') or ''}",
            f"plan,plan_id,{(payload.get('plan') or {}).get('plan_id') or ''}",
            f"plan,display_name,{(payload.get('plan') or {}).get('display_name') or ''}",
            f"lifecycle,renewal_status,{(payload.get('renewal_summary') or {}).get('status') or ''}",
            f"lifecycle,dunning_status,{(payload.get('dunning_summary') or {}).get('status') or ''}",
            f"lifecycle,pilot_conversion_status,{(payload.get('pilot_conversion_summary') or {}).get('status') or ''}",
            f"lifecycle,expansion_status,{(payload.get('expansion_summary') or {}).get('status') or ''}",
            f"lifecycle,churn_risk_level,{(payload.get('churn_risk_summary') or {}).get('risk_level') or ''}",
            f"quality,event_count,{(payload.get('quality_summary') or {}).get('event_count') or 0}",
            f"quality,open_review_case_count,{(payload.get('quality_summary') or {}).get('open_review_case_count') or 0}",
            f"groundedness,pass_rate,{(payload.get('groundedness_summary') or {}).get('pass_rate') or 0}",
            f"groundedness,failed_count,{(payload.get('groundedness_summary') or {}).get('failed_count') or 0}",
            f"receipts,receipt_count,{(payload.get('receipt_summary') or {}).get('receipt_count') or 0}",
            f"handoff,validated_handoff_count,{(payload.get('handoff_conversion_summary') or {}).get('validated_handoff_count') or 0}",
            f"conversion,validated_conversion_count,{(payload.get('handoff_conversion_summary') or {}).get('validated_conversion_count') or 0}",
            f"invoice,total_due_usd,{(payload.get('invoice_preview') or {}).get('total_due_usd') or 0}",
        ]
        return rows

    def _pdf_bytes(self, *, title: str, lines: List[str]) -> bytes:
        def _escape(value: str) -> str:
            return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        y = 760
        content_lines = ["BT", "/F1 12 Tf"]
        for line in [title, *lines]:
            content_lines.append(f"50 {y} Td ({_escape(line)}) Tj")
            y -= 18
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("utf-8")
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            f"5 0 obj << /Length {len(content)} >> stream\n".encode("utf-8") + content + b"\nendstream endobj\n",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf))
            pdf.extend(obj)
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects)+1}\n".encode("utf-8"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
        pdf.extend(
            f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("utf-8")
        )
        return bytes(pdf)

    def export_payload(self, *, account_id: str, report_type: str, period_start: Optional[str] = None) -> Dict[str, Any]:
        payload = self.workspace(account_id=account_id, period_start=period_start)
        if report_type == "workspace_json":
            return {
                "report_type": report_type,
                "filename": f"customer_workspace_{account_id}.json",
                "content_type": "application/json",
                "content": payload,
            }
        if report_type == "workspace_csv":
            return {
                "report_type": report_type,
                "filename": f"customer_workspace_{account_id}.csv",
                "content_type": "text/csv",
                "content": "\n".join(self._csv_rows(payload)),
            }
        if report_type == "invoice_csv":
            invoice = self.commercial_billing.invoice_preview(account_id=account_id, period_start=period_start)
            return {
                "report_type": report_type,
                "filename": f"invoice_preview_{account_id}.csv",
                "content_type": "text/csv",
                "content": str((invoice.get("export_artifacts") or {}).get("csv_preview") or ""),
            }
        if report_type == "workspace_pdf":
            pdf_bytes = self._pdf_bytes(
                title=f"Customer Workspace Report - {account_id}",
                lines=[
                    f"Plan: {(payload.get('plan') or {}).get('display_name') or '-'}",
                    f"Status: {(payload.get('lifecycle_summary') or {}).get('status') or '-'}",
                    f"Renewal: {(payload.get('renewal_summary') or {}).get('status') or '-'}",
                    f"Dunning: {(payload.get('dunning_summary') or {}).get('status') or '-'}",
                    f"Pilot conversion: {(payload.get('pilot_conversion_summary') or {}).get('status') or '-'}",
                    f"Upgrade recommendation: {(payload.get('expansion_summary') or {}).get('recommended_plan_id') or '-'}",
                    f"Quality events: {(payload.get('quality_summary') or {}).get('event_count') or 0}",
                    f"Groundedness pass rate: {(payload.get('groundedness_summary') or {}).get('pass_rate') or 0}",
                    f"Receipts: {(payload.get('receipt_summary') or {}).get('receipt_count') or 0}",
                    f"Validated handoff: {(payload.get('handoff_conversion_summary') or {}).get('validated_handoff_count') or 0}",
                    f"Validated conversion: {(payload.get('handoff_conversion_summary') or {}).get('validated_conversion_count') or 0}",
                    f"Invoice due: {(payload.get('invoice_preview') or {}).get('total_due_usd') or 0}",
                ],
            )
            return {
                "report_type": report_type,
                "filename": f"customer_workspace_{account_id}.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        raise KeyError("unknown_customer_export:%s" % report_type)
