from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .commercial_audit import CommercialAuditService
from .commercial_billing import CommercialBillingService
from .commercial_support import CommercialSupportService
from .customer_accounts import CustomerAccountService
from .customer_campaigns import CustomerCampaignService
from ..persistence.repositories import SQLAlchemyPlatformRepository


class CommercialLifecycleAutomationService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_account_service: CustomerAccountService,
        customer_campaign_service: CustomerCampaignService,
        commercial_billing_service: CommercialBillingService,
        commercial_support_service: CommercialSupportService,
        audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.customer_accounts = customer_account_service
        self.customer_campaigns = customer_campaign_service
        self.commercial_billing = commercial_billing_service
        self.commercial_support = commercial_support_service
        self.audit = audit_service

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _next_upgrade_plan_id(self, plan_id: Optional[str]) -> Optional[str]:
        normalized = str(plan_id or "").strip()
        if normalized == "play_pass":
            return "creator_pass"
        if normalized == "creator_pass":
            return "studio_pass"
        return None

    def sync_account(self, *, account_id: str) -> Dict[str, Any]:
        account_detail = self.customer_accounts.customer_account_detail(account_id=account_id)
        customer = dict(account_detail.get("customer_account") or {})
        plan = dict(account_detail.get("plan") or {})
        invoice_preview = self.commercial_billing.invoice_preview(account_id=account_id)
        invoices = self.repository.list_invoice_issuances(account_id=account_id, limit=100)
        payment_transactions = self.repository.list_payment_transactions(account_id=account_id, limit=200)
        payment_retry_attempts = self.repository.list_payment_retry_attempts(account_id=account_id, limit=200)
        campaigns = self.customer_campaigns.list_campaigns(account_id=account_id, limit=100).get("campaigns", [])
        active_overages = [item for item in self.repository.list_overage_flags(account_id=account_id, limit=100) if str(item.get("status") or "") == "active"]
        support_cases = self.repository.list_support_cases(account_id=account_id, limit=100)
        disputes = self.repository.list_disputes(account_id=account_id, limit=100)
        billable_events = self.repository.list_billable_events(account_id=account_id, limit=500)
        now = self._utcnow()
        customer_status = str(customer.get("status") or "trial")
        metadata_json = dict(customer.get("metadata_json") or {})

        renewal_due_at = self._parse_dt(customer.get("renewal_due_at"))
        renewal_status = "stable"
        if customer_status == "renewal_due" or (renewal_due_at and renewal_due_at <= now + timedelta(days=14)):
            renewal_status = "renewal_due"
        if renewal_status == "renewal_due" and customer_status in {"active", "renewal_due"}:
            customer_status = "renewal_due"
        elif renewal_status == "stable" and customer_status == "renewal_due":
            customer_status = "active"
        renewal_tracker = self.repository.save_renewal_tracker(
            {
                "renewal_tracker_id": f"renewal_{account_id}",
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "status": renewal_status,
                "renewal_due_at": customer.get("renewal_due_at"),
                "tracker_payload": {
                    "customer_status": customer_status,
                    "plan_id": plan.get("plan_id"),
                    "renewal_window_days": 14,
                },
            }
        )

        latest_invoice = invoices[0] if invoices else None
        dunning_run = None
        open_invoice_statuses = {"issued", "failed"}
        failed_invoice_count = sum(1 for item in invoices if str(item.get("status") or "") == "failed")
        failed_payment_count = sum(1 for item in payment_transactions if str(item.get("status") or "") == "failed")
        retry_count = len([item for item in payment_retry_attempts if str(item.get("invoice_id") or "") == str((latest_invoice or {}).get("invoice_id") or "")])
        dunning_status = "clear"
        if latest_invoice and str(latest_invoice.get("status") or "") in open_invoice_statuses and float(latest_invoice.get("total_due_usd") or 0.0) > 0.0:
            current_step = "payment_failed_followup" if str(latest_invoice.get("status") or "") == "failed" else "invoice_open_notice"
            if retry_count > 0:
                current_step = "retry_scheduled"
            dunning_run = self.repository.save_dunning_run(
                {
                    "dunning_run_id": f"dunning_run_{latest_invoice['invoice_id']}",
                    "customer_account_id": customer["customer_account_id"],
                    "account_id": account_id,
                    "invoice_id": latest_invoice["invoice_id"],
                    "status": "open",
                    "current_step": current_step,
                    "dunning_payload": {
                        "invoice_status": latest_invoice.get("status"),
                        "total_due_usd": latest_invoice.get("total_due_usd"),
                        "retry_count": retry_count,
                        "hosted_invoice_url": latest_invoice.get("hosted_invoice_url"),
                        "invoice_pdf_url": latest_invoice.get("invoice_pdf_url"),
                    },
                }
            )
            dunning_status = "open"
        elif latest_invoice and str(latest_invoice.get("status") or "") == "paid":
            dunning_run = self.repository.save_dunning_run(
                {
                    "dunning_run_id": f"dunning_run_{latest_invoice['invoice_id']}",
                    "customer_account_id": customer["customer_account_id"],
                    "account_id": account_id,
                    "invoice_id": latest_invoice["invoice_id"],
                    "status": "resolved",
                    "current_step": "paid",
                    "dunning_payload": {
                        "invoice_status": latest_invoice.get("status"),
                        "total_due_usd": latest_invoice.get("total_due_usd"),
                    },
                }
            )
            dunning_status = "resolved"

        active_campaigns = [item for item in campaigns if str((item.get("campaign") or {}).get("activation_status") or "") == "active"]
        validated_billable_count = len([item for item in billable_events if str(item.get("status") or "") in {"recorded", "approved"}])
        pilot_status = "watch"
        if customer_status == "trial" and active_campaigns and validated_billable_count >= 3:
            pilot_status = "ready_for_conversion"
        elif customer_status in {"active", "renewal_due"} and validated_billable_count > 0:
            pilot_status = "converted"
        pilot_track = self.repository.save_pilot_conversion_track(
            {
                "pilot_conversion_track_id": f"pilot_conversion_{account_id}",
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "status": pilot_status,
                "track_payload": {
                    "active_campaign_count": len(active_campaigns),
                    "billable_event_count": len(billable_events),
                    "validated_billable_count": validated_billable_count,
                },
            }
        )

        expansion_candidate = None
        next_upgrade_plan_id = self._next_upgrade_plan_id(plan.get("plan_id"))
        active_overage_units = sum(float(item.get("overage_units") or 0.0) for item in active_overages)
        if active_overages and next_upgrade_plan_id:
            expansion_candidate = self.repository.save_expansion_candidate(
                {
                    "expansion_candidate_id": f"expansion_{account_id}",
                    "customer_account_id": customer["customer_account_id"],
                    "account_id": account_id,
                    "status": "recommended",
                    "trigger_type": "overage_to_upgrade",
                    "candidate_payload": {
                        "active_overage_flag_count": len(active_overages),
                        "active_overage_units": active_overage_units,
                        "invoice_due_usd": (invoice_preview.get("invoice_preview") or {}).get("total_due_usd") or 0.0,
                        "current_plan_id": plan.get("plan_id"),
                        "recommended_plan_id": next_upgrade_plan_id,
                    },
                }
            )

        risk_level = "low"
        no_recent_paid_invoice = customer_status in {"active", "paused", "renewal_due"} and not any(
            str(item.get("status") or "") == "paid" for item in invoices
        )
        open_dispute_count = sum(1 for item in disputes if str(item.get("status") or "") in {"open", "under_review", "approved"})
        open_support_count = sum(1 for item in support_cases if str(item.get("status") or "") in {"open", "in_progress"})
        if customer_status in {"paused", "renewal_due"} or open_dispute_count > 0 or failed_invoice_count >= 2 or failed_payment_count >= 2:
            risk_level = "high"
        elif failed_invoice_count > 0 or failed_payment_count > 0 or open_support_count > 0 or no_recent_paid_invoice:
            risk_level = "medium"
        churn_flag = self.repository.save_churn_risk_flag(
            {
                "churn_risk_flag_id": f"churn_{account_id}",
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "status": "watch" if risk_level != "low" else "stable",
                "risk_level": risk_level,
                "flag_payload": {
                    "open_disputes": open_dispute_count,
                    "open_support_cases": open_support_count,
                    "latest_invoice_status": (latest_invoice or {}).get("status"),
                    "failed_invoice_count": failed_invoice_count,
                    "failed_payment_count": failed_payment_count,
                    "no_recent_paid_invoice": no_recent_paid_invoice,
                },
            }
        )

        metadata_json["renewal_tracker_status"] = renewal_tracker.get("status")
        metadata_json["dunning_status"] = dunning_status
        metadata_json["pilot_conversion_status"] = pilot_track.get("status")
        metadata_json["expansion_status"] = expansion_candidate.get("status") if expansion_candidate else "clear"
        metadata_json["upgrade_recommendation_plan_id"] = (
            ((expansion_candidate or {}).get("candidate_payload_json") or {}).get("recommended_plan_id")
            if expansion_candidate
            else None
        )
        metadata_json["churn_risk_status"] = churn_flag.get("status")
        metadata_json["churn_risk_level"] = churn_flag.get("risk_level")
        metadata_json["dunning_invoice_id"] = (dunning_run or {}).get("invoice_id")
        self.repository.save_customer_account({**customer, "status": customer_status, "metadata_json": metadata_json})

        result = {
            "renewal_tracker": renewal_tracker,
            "dunning_run": dunning_run,
            "pilot_conversion_track": pilot_track,
            "expansion_candidate": expansion_candidate,
            "churn_risk_flag": churn_flag,
            "summary": {
                "renewal_status": renewal_tracker.get("status"),
                "dunning_status": dunning_status,
                "pilot_conversion_status": pilot_track.get("status"),
                "expansion_status": expansion_candidate.get("status") if expansion_candidate else "clear",
                "churn_risk_level": churn_flag.get("risk_level"),
                "churn_risk_status": churn_flag.get("status"),
                "recommended_plan_id": next_upgrade_plan_id if expansion_candidate else None,
                "open_dispute_count": open_dispute_count,
                "open_support_case_count": open_support_count,
            },
        }
        self.audit.record_audit_log(
            actor_id="automation_sync",
            actor_role="ops",
            account_id=account_id,
            object_type="commercial_lifecycle",
            object_id=account_id,
            action_type="lifecycle_automation_synced",
            source_surface="ops",
            customer_visible_payload={"summary": result["summary"], "renewal_tracker": renewal_tracker, "dunning_run": dunning_run},
            internal_payload={
                "invoice_count": len(invoices),
                "campaign_count": len(campaigns),
                "billable_event_count": len(billable_events),
            },
        )
        return result

    def list_account_state(self, *, account_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        return {
            "renewal_trackers": self.repository.list_renewal_trackers(account_id=account_id, limit=limit),
            "dunning_runs": self.repository.list_dunning_runs(account_id=account_id, limit=limit),
            "pilot_conversion_tracks": self.repository.list_pilot_conversion_tracks(account_id=account_id, limit=limit),
            "expansion_candidates": self.repository.list_expansion_candidates(account_id=account_id, limit=limit),
            "churn_risk_flags": self.repository.list_churn_risk_flags(account_id=account_id, limit=limit),
        }
