from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .commercial_billing import CommercialBillingService
from .commercial_audit import CommercialAuditService
from .customer_accounts import CustomerAccountService
from ..persistence.repositories import SQLAlchemyPlatformRepository


DISPUTE_STATUSES = {"open", "under_review", "approved", "rejected", "credited", "reversed", "refunded", "resolved"}
REFUND_STATUSES = {"requested", "approved", "rejected", "paid"}
SUPPORT_CASE_STATUSES = {"open", "in_progress", "resolved", "dismissed"}
SETTLEMENT_RUN_STATUSES = {"draft", "finalized"}
MANUAL_ADJUSTMENT_TYPES = {"credit", "reversal", "refund", "writeoff"}
BILLABLE_EVENT_MUTATION_STATUSES = {"recorded", "approved", "disputed", "credited", "reversed", "refunded"}


class CommercialSupportService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_account_service: CustomerAccountService,
        commercial_billing_service: CommercialBillingService,
        audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.customer_accounts = customer_account_service
        self.commercial_billing = commercial_billing_service
        self.audit = audit_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_status(self, value: str, allowed: set[str], *, name: str) -> str:
        normalized = str(value or "").strip()
        if normalized not in allowed:
            raise ValueError(f"{name}_invalid:{normalized}")
        return normalized

    def _customer_context(self, *, account_id: str) -> Dict[str, Any]:
        return self.customer_accounts.customer_account_detail(account_id=account_id)

    def create_dispute(
        self,
        *,
        account_id: str,
        requested_by: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer = self._customer_context(account_id=account_id)["customer_account"]
        billable_event_id = payload.get("billable_event_id")
        billable_event = self.repository.get_billable_event(billable_event_id) if billable_event_id else None
        invoice_preview_id = payload.get("invoice_preview_id") or (billable_event or {}).get("event_payload_json", {}).get("invoice_preview_id")
        dispute = self.repository.save_dispute(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "campaign_id": payload.get("campaign_id"),
                "invoice_preview_id": invoice_preview_id,
                "billable_event_id": billable_event_id,
                "quality_event_id": payload.get("quality_event_id") or (billable_event or {}).get("quality_event_id"),
                "trace_id": payload.get("trace_id") or (billable_event or {}).get("trace_id"),
                "dispute_reason_code": payload["dispute_reason_code"],
                "note": payload.get("note"),
                "status": "open",
                "requested_amount_usd": float(payload.get("requested_amount_usd") or (billable_event or {}).get("amount_usd") or 0.0),
                "resolved_amount_usd": 0.0,
                "requested_by": requested_by,
                "dispute_payload": {
                    "billable_event": billable_event or {},
                    "request_source": "customer_workspace",
                },
            }
        )
        self.audit.record_audit_log(
            actor_id=requested_by,
            actor_role="customer",
            account_id=account_id,
            object_type="dispute",
            object_id=dispute["dispute_id"],
            action_type="dispute_created",
            source_surface="customer",
            customer_visible_payload={"dispute": dispute},
            internal_payload={"payload": payload},
        )
        return dispute

    def list_disputes(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        disputes = self.repository.list_disputes(account_id=account_id, status=status, limit=limit)
        return {
            "disputes": disputes,
            "summary": {
                "dispute_count": len(disputes),
                "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in disputes)),
            },
        }

    def _set_billable_event_status(self, *, billable_event_id: Optional[str], status: str) -> Optional[Dict[str, Any]]:
        if not billable_event_id:
            return None
        normalized = self._validate_status(status, BILLABLE_EVENT_MUTATION_STATUSES, name="billable_event_status")
        return self.commercial_billing.update_billable_event_status(billable_event_id=billable_event_id, status=normalized)

    def decide_dispute(
        self,
        *,
        dispute_id: str,
        reviewer_id: str,
        decision: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip()
        if normalized_decision not in {"approve", "reject", "credit", "reverse", "refund", "resolve"}:
            raise ValueError("dispute_decision_invalid")
        dispute = self.repository.get_dispute(dispute_id)
        updated_status = {
            "approve": "approved",
            "reject": "rejected",
            "credit": "credited",
            "reverse": "reversed",
            "refund": "refunded",
            "resolve": "resolved",
        }[normalized_decision]
        billable_event = None
        refund_request = None
        adjustment = None
        if normalized_decision == "approve":
            billable_event = self._set_billable_event_status(billable_event_id=dispute.get("billable_event_id"), status="disputed")
        elif normalized_decision == "credit":
            billable_event = self._set_billable_event_status(billable_event_id=dispute.get("billable_event_id"), status="credited")
            adjustment = self.repository.save_manual_adjustment(
                {
                    "customer_account_id": dispute["customer_account_id"],
                    "account_id": dispute["account_id"],
                    "dispute_id": dispute["dispute_id"],
                    "invoice_preview_id": dispute.get("invoice_preview_id"),
                    "billable_event_id": dispute.get("billable_event_id"),
                    "adjustment_type": "credit",
                    "amount_usd": float(dispute.get("requested_amount_usd") or 0.0),
                    "requested_by": reviewer_id,
                    "reviewer_id": reviewer_id,
                    "adjustment_payload": {"note": note},
                }
            )
        elif normalized_decision == "reverse":
            billable_event = self._set_billable_event_status(billable_event_id=dispute.get("billable_event_id"), status="reversed")
            adjustment = self.repository.save_manual_adjustment(
                {
                    "customer_account_id": dispute["customer_account_id"],
                    "account_id": dispute["account_id"],
                    "dispute_id": dispute["dispute_id"],
                    "invoice_preview_id": dispute.get("invoice_preview_id"),
                    "billable_event_id": dispute.get("billable_event_id"),
                    "adjustment_type": "reversal",
                    "amount_usd": float(dispute.get("requested_amount_usd") or 0.0),
                    "requested_by": reviewer_id,
                    "reviewer_id": reviewer_id,
                    "adjustment_payload": {"note": note},
                }
            )
        elif normalized_decision == "refund":
            billable_event = self._set_billable_event_status(billable_event_id=dispute.get("billable_event_id"), status="refunded")
            refund_request = self.repository.save_refund_request(
                {
                    "dispute_id": dispute["dispute_id"],
                    "customer_account_id": dispute["customer_account_id"],
                    "account_id": dispute["account_id"],
                    "invoice_preview_id": dispute.get("invoice_preview_id"),
                    "billable_event_id": dispute.get("billable_event_id"),
                    "trace_id": dispute.get("trace_id"),
                    "status": "approved",
                    "requested_amount_usd": float(dispute.get("requested_amount_usd") or 0.0),
                    "approved_amount_usd": float(dispute.get("requested_amount_usd") or 0.0),
                    "requested_by": dispute.get("requested_by") or reviewer_id,
                    "reviewer_id": reviewer_id,
                    "refund_payload": {"note": note},
                }
            )
        saved = self.repository.save_dispute(
            {
                **dispute,
                "status": self._validate_status(updated_status, DISPUTE_STATUSES, name="dispute_status"),
                "resolved_amount_usd": float(dispute.get("requested_amount_usd") or 0.0),
                "reviewer_id": reviewer_id,
                "resolution_note": note,
                "dispute_payload_json": dispute.get("dispute_payload_json", {}),
            }
        )
        result = {
            "dispute": saved,
            "billable_event": billable_event,
            "refund_request": refund_request,
            "manual_adjustment": adjustment,
        }
        self.audit.record_audit_log(
            actor_id=reviewer_id,
            actor_role="reviewer",
            account_id=dispute.get("account_id"),
            object_type="dispute",
            object_id=dispute_id,
            action_type="dispute_decided",
            source_surface="ops",
            customer_visible_payload={"dispute": saved},
            internal_payload={**result, "decision": normalized_decision, "note": note},
        )
        return result

    def create_support_case(
        self,
        *,
        account_id: str,
        requested_by: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer = self._customer_context(account_id=account_id)["customer_account"]
        support_case = self.repository.save_support_case(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "campaign_id": payload.get("campaign_id"),
                "invoice_preview_id": payload.get("invoice_preview_id"),
                "billable_event_id": payload.get("billable_event_id"),
                "quality_event_id": payload.get("quality_event_id"),
                "trace_id": payload.get("trace_id"),
                "case_type": payload.get("case_type", "general"),
                "subject": payload["subject"],
                "description": payload["description"],
                "status": "open",
                "priority": payload.get("priority", "medium"),
                "requested_by": requested_by,
                "support_payload": {"request_source": "customer_workspace"},
            }
        )
        self.audit.record_audit_log(
            actor_id=requested_by,
            actor_role="customer",
            account_id=account_id,
            object_type="support_case",
            object_id=support_case["support_case_id"],
            action_type="support_case_created",
            source_surface="customer",
            customer_visible_payload={"support_case": support_case},
            internal_payload={"payload": payload},
        )
        return support_case

    def list_support_cases(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        cases = self.repository.list_support_cases(account_id=account_id, status=status, limit=limit)
        return {
            "support_cases": cases,
            "summary": {
                "case_count": len(cases),
                "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in cases)),
            },
        }

    def update_support_case_status(
        self,
        *,
        support_case_id: str,
        reviewer_id: str,
        status: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        case = self.repository.get_support_case(support_case_id)
        saved = self.repository.save_support_case(
            {
                **case,
                "status": self._validate_status(status, SUPPORT_CASE_STATUSES, name="support_case_status"),
                "owner_id": reviewer_id if status in {"in_progress", "resolved"} else case.get("owner_id"),
                "resolution_note": note,
                "support_payload_json": case.get("support_payload_json", {}),
            }
        )
        self.audit.record_audit_log(
            actor_id=reviewer_id,
            actor_role="reviewer",
            account_id=case.get("account_id"),
            object_type="support_case",
            object_id=support_case_id,
            action_type="support_case_status_changed",
            source_surface="ops",
            customer_visible_payload={"support_case": saved},
            internal_payload={"status": status, "note": note},
        )
        return saved

    def create_manual_adjustment(
        self,
        *,
        account_id: str,
        reviewer_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer = self._customer_context(account_id=account_id)["customer_account"]
        adjustment = self.repository.save_manual_adjustment(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "dispute_id": payload.get("dispute_id"),
                "refund_request_id": payload.get("refund_request_id"),
                "invoice_preview_id": payload.get("invoice_preview_id"),
                "billable_event_id": payload.get("billable_event_id"),
                "adjustment_type": payload["adjustment_type"],
                "amount_usd": float(payload.get("amount_usd") or 0.0),
                "requested_by": reviewer_id,
                "reviewer_id": reviewer_id,
                "adjustment_payload": dict(payload.get("adjustment_payload") or {}),
            }
        )
        if payload.get("billable_event_id") and payload.get("target_billable_status"):
            self._set_billable_event_status(
                billable_event_id=payload.get("billable_event_id"),
                status=payload.get("target_billable_status"),
            )
        self.audit.record_audit_log(
            actor_id=reviewer_id,
            actor_role="reviewer",
            account_id=account_id,
            object_type="manual_adjustment",
            object_id=adjustment["adjustment_id"],
            action_type="manual_adjustment_created",
            source_surface="ops",
            customer_visible_payload={"manual_adjustment": adjustment},
            internal_payload={"payload": payload},
        )
        return adjustment

    def generate_settlement_run(
        self,
        *,
        account_id: str,
        reviewer_id: str,
    ) -> Dict[str, Any]:
        invoice_preview = self.commercial_billing.invoice_preview(account_id=account_id)
        customer = self._customer_context(account_id=account_id)["customer_account"]
        run = self.repository.save_settlement_run(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "billing_period_start": (invoice_preview.get("usage_ledger") or {}).get("billing_period_start"),
                "billing_period_end": (invoice_preview.get("usage_ledger") or {}).get("billing_period_end"),
                "status": "finalized",
                "subtotal_amount_usd": (invoice_preview.get("invoice_preview") or {}).get("subtotal_amount_usd") or 0.0,
                "disputed_amount_usd": (invoice_preview.get("invoice_preview") or {}).get("disputed_amount_usd") or 0.0,
                "credited_amount_usd": (invoice_preview.get("invoice_preview") or {}).get("credited_amount_usd") or 0.0,
                "reversed_amount_usd": (invoice_preview.get("invoice_preview") or {}).get("reversed_amount_usd") or 0.0,
                "refunded_amount_usd": 0.0,
                "net_amount_usd": (invoice_preview.get("invoice_preview") or {}).get("total_due_usd") or 0.0,
                "run_payload": {"generated_by": reviewer_id},
            }
        )
        items: List[Dict[str, Any]] = []
        for event in self.repository.list_billable_events(account_id=account_id, limit=500):
            status = str(event.get("status") or "recorded")
            if status == "recorded":
                event = self.commercial_billing.update_billable_event_status(
                    billable_event_id=event["billable_event_id"],
                    status="approved",
                )
                status = "approved"
            items.append(
                self.repository.save_settlement_item(
                    {
                        "settlement_run_id": run["settlement_run_id"],
                        "billable_event_id": event.get("billable_event_id"),
                        "invoice_preview_id": invoice_preview.get("invoice_preview", {}).get("invoice_preview_id"),
                        "status": status,
                        "amount_usd": event.get("amount_usd") or 0.0,
                        "item_payload": {"trace_id": event.get("trace_id"), "billable_metric": event.get("billable_metric")},
                    }
                )
            )
        return {
            "settlement_run": run,
            "settlement_items": items,
        }
