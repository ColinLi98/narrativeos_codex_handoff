from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .customer_accounts import CustomerAccountService
from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .commercial_billing import CommercialBillingService


DEFAULT_RETENTION_POLICIES = (
    {"retention_policy_id": "retention_audit_logs_v1", "scope": "audit_logs", "retention_days": 365, "deletion_mode": "customer_request_review", "status": "active"},
    {"retention_policy_id": "retention_customer_exports_v1", "scope": "customer_audit_exports", "retention_days": 90, "deletion_mode": "customer_request_review", "status": "active"},
    {"retention_policy_id": "retention_deletion_requests_v1", "scope": "data_deletion_requests", "retention_days": 365, "deletion_mode": "manual_request", "status": "active"},
)


class CommercialAuditService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_account_service: CustomerAccountService,
        commercial_billing_service: Optional["CommercialBillingService"] = None,
    ) -> None:
        self.repository = repository
        self.customer_accounts = customer_account_service
        self.commercial_billing = commercial_billing_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def sync_default_retention_policies(self) -> Dict[str, Any]:
        policies = [self.repository.save_data_retention_policy(item) for item in DEFAULT_RETENTION_POLICIES]
        return {
            "policies": policies,
            "summary": {
                "policy_count": len(policies),
            },
        }

    def _customer_context(self, *, account_id: str) -> Dict[str, Any]:
        return self.customer_accounts.customer_account_detail(account_id=account_id)

    def customer_safe_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            safe: Dict[str, Any] = {}
            for key, value in payload.items():
                if key in {"reviewer_id", "owner_id", "internal_payload_json", "support_payload_json", "dispute_payload_json", "adjustment_payload_json", "refund_payload_json", "resolution_note", "requested_by", "requested_by_actor", "raw_evidence", "internal_reason_codes", "top_reason_codes"}:
                    continue
                if key == "latest_quality_events":
                    continue
                if key == "reason_codes":
                    continue
                safe[key] = self.customer_safe_payload(value)
            return safe
        if isinstance(payload, list):
            return [self.customer_safe_payload(item) for item in payload]
        return payload

    def record_audit_log(
        self,
        *,
        actor_id: str,
        actor_role: str,
        account_id: Optional[str],
        object_type: str,
        object_id: str,
        action_type: str,
        source_surface: str,
        customer_visible_payload: Optional[Dict[str, Any]] = None,
        internal_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        customer_account_id = None
        if account_id:
            customer = self.repository.get_customer_account_by_account_id(account_id, default=None)
            customer_account_id = (customer or {}).get("customer_account_id")
        return self.repository.save_audit_log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "account_id": account_id,
                "customer_account_id": customer_account_id,
                "object_type": object_type,
                "object_id": object_id,
                "action_type": action_type,
                "source_surface": source_surface,
                "customer_visible_payload": self.customer_safe_payload(customer_visible_payload or {}),
                "internal_payload": dict(internal_payload or {}),
            }
        )

    def audit_log_listing(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        entries = self.repository.list_audit_logs(
            account_id=account_id,
            customer_account_id=customer_account_id,
            action_type=action_type,
            limit=limit,
        )
        return {
            "audit_logs": entries,
            "summary": {
                "entry_count": len(entries),
                "by_action_type": dict(Counter(str(item.get("action_type") or "unknown") for item in entries)),
            },
        }

    def customer_audit_export(
        self,
        *,
        account_id: str,
        requested_by: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        customer = self._customer_context(account_id=account_id)["customer_account"]
        entries = self.repository.list_audit_logs(account_id=account_id, limit=500)
        safe_entries = [
            {
                **item,
                "internal_payload_json": {},
                "customer_visible_payload_json": self.customer_safe_payload(item.get("customer_visible_payload_json") or {}),
            }
            for item in entries
        ]
        export_payload = {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "customer_account_id": customer["customer_account_id"],
            "period_start": period_start,
            "period_end": period_end,
            "audit_logs": safe_entries,
            "summary": {
                "entry_count": len(safe_entries),
                "by_action_type": dict(Counter(str(item.get("action_type") or "unknown") for item in safe_entries)),
            },
        }
        saved = self.repository.save_customer_audit_export(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "requested_by": requested_by,
                "period_start": period_start,
                "period_end": period_end,
                "export_payload": export_payload,
            }
        )
        return {
            "audit_export": saved,
            "export_payload": export_payload,
        }

    def create_data_deletion_request(
        self,
        *,
        account_id: str,
        requested_by: str,
        scope: str,
        requested_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        customer = self._customer_context(account_id=account_id)["customer_account"]
        if self.commercial_billing is not None:
            try:
                self.commercial_billing.invoice_preview(account_id=account_id)
            except Exception:
                pass
        affected_counts = {
            "campaigns": len(self.repository.list_campaigns(account_id=account_id, limit=500)),
            "invoice_previews": len(self.repository.list_invoice_previews(account_id=account_id, limit=500)),
            "disputes": len(self.repository.list_disputes(account_id=account_id, limit=500)),
            "support_cases": len(self.repository.list_support_cases(account_id=account_id, limit=500)),
            "audit_logs": len(self.repository.list_audit_logs(account_id=account_id, limit=500)),
        }
        return self.repository.save_data_deletion_request(
            {
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "requested_by": requested_by,
                "scope": scope,
                "status": "requested",
                "requested_payload": dict(requested_payload or {}),
                "affected_object_counts": affected_counts,
            }
        )
