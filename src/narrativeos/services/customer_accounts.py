from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..commercialization.config import load_commercial_plans
from ..commercialization.models import BillingProfile, CommercialPlan, CustomerAccount
from ..persistence.repositories import SQLAlchemyPlatformRepository


COMMERCIAL_CUSTOMER_ROLES = frozenset({"customer", "reviewer", "ops", "admin"})


class CustomerAccountService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: Optional[Any] = None,
    ) -> None:
        self.repository = repository
        self.billing = billing_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _plan_bundle(self) -> Dict[str, Any]:
        return load_commercial_plans()

    def sync_configured_plans(self) -> Dict[str, Any]:
        bundle = self._plan_bundle()
        synced: List[Dict[str, Any]] = []
        for plan in bundle["plans"]:
            synced.append(
                self.repository.save_plan(
                    {
                        **plan.to_dict(),
                        "plan_payload": plan.to_dict(),
                    }
                )
            )
        return {
            "config_version": bundle["config_version"],
            "plans": synced,
            "plan_map": {item["plan_id"]: item for item in synced},
        }

    def _plan_for_id(self, plan_id: str) -> CommercialPlan:
        bundle = self._plan_bundle()
        plan = bundle["plan_map"].get(str(plan_id) or "")
        if plan is None:
            raise KeyError("unknown_commercial_plan:%s" % plan_id)
        return plan

    def ensure_customer_account(
        self,
        *,
        account_id: str,
        display_name: Optional[str] = None,
        plan_id: str = "play_pass",
        status: str = "trial",
    ) -> Dict[str, Any]:
        resolved_account_id = str(account_id or "").strip()
        if not resolved_account_id:
            raise ValueError("customer_account_id_required")
        self.sync_configured_plans()
        plan = self._plan_for_id(plan_id)
        existing = self.repository.get_customer_account_by_account_id(resolved_account_id, default=None)
        if existing is not None:
            updates = {
                **existing,
                "display_name": display_name if display_name is not None else existing.get("display_name"),
                "plan_id": existing.get("plan_id") or plan.plan_id,
                "seat_limit": int(existing.get("seat_limit") or plan.seat_limit),
                "workspace_limit": int(existing.get("workspace_limit") or plan.workspace_limit),
                "campaign_limit": int(existing.get("campaign_limit") or plan.campaign_limit),
                "metadata_json": dict(existing.get("metadata_json") or existing.get("metadata") or {}),
            }
            return self.repository.save_customer_account(updates)
        customer = CustomerAccount(
            customer_account_id="cust_%s" % resolved_account_id.replace("@", "_").replace(".", "_"),
            account_id=resolved_account_id,
            display_name=display_name,
            status=status,
            plan_id=plan.plan_id,
            seat_limit=plan.seat_limit,
            workspace_limit=plan.workspace_limit,
            campaign_limit=plan.campaign_limit,
            renewal_due_at=(datetime.now(timezone.utc) + timedelta(days=14)).isoformat() if status in {"trial", "renewal_due"} else None,
            metadata={"config_version": self._plan_bundle()["config_version"]},
        )
        return self.repository.save_customer_account(
            {
                **customer.to_dict(),
                "metadata_json": customer.metadata,
            }
        )

    def upsert_billing_profile(
        self,
        *,
        customer_account_id: str,
        account_id: str,
        provider: str = "internal_preview",
        invoice_email: Optional[str] = None,
        legal_name: Optional[str] = None,
        billing_country: Optional[str] = None,
        tax_status: Optional[str] = None,
        provider_customer_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = next(
            iter(self.repository.list_billing_profiles(customer_account_id=customer_account_id, limit=1)),
            None,
        )
        profile = BillingProfile(
            billing_profile_id=str(existing.get("billing_profile_id")) if existing else "billing_profile_%s" % customer_account_id,
            customer_account_id=customer_account_id,
            account_id=account_id,
            provider=provider,
            status="active",
            invoice_email=invoice_email,
            legal_name=legal_name,
            billing_country=billing_country,
            tax_status=tax_status,
            provider_customer_ref=provider_customer_ref,
            profile_payload={},
        )
        return self.repository.save_billing_profile(
            {
                **profile.to_dict(),
                "profile_payload_json": profile.profile_payload,
            }
        )

    def list_customer_accounts(self, *, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        self.sync_configured_plans()
        customers = self.repository.list_customer_accounts(status=status, limit=limit)
        counts: Dict[str, int] = {}
        for item in customers:
            resolved_status = str(item.get("status") or "unknown")
            counts[resolved_status] = counts.get(resolved_status, 0) + 1
        return {
            "customers": [self.customer_account_detail(customer_account_id=item["customer_account_id"]) for item in customers],
            "summary": {
                "total_customers": len(customers),
                "status_counts": counts,
            },
        }

    def customer_account_detail(
        self,
        *,
        customer_account_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.sync_configured_plans()
        customer = (
            self.repository.get_customer_account(customer_account_id)
            if customer_account_id
            else self.repository.get_customer_account_by_account_id(str(account_id or "").strip())
        )
        plan = self.repository.get_plan(customer["plan_id"])
        billing_profile = next(
            iter(self.repository.list_billing_profiles(customer_account_id=customer["customer_account_id"], limit=1)),
            None,
        )
        subscription_snapshot = self.billing.subscription_status(account_id=customer["account_id"]) if self.billing else None
        entitlements = self.repository.list_entitlements(account_id=customer["account_id"]) if customer.get("account_id") else []
        limit_posture = {
            "seat_limit": int(customer.get("seat_limit") or 0),
            "seat_count": int(customer.get("seat_count") or 0),
            "workspace_limit": int(customer.get("workspace_limit") or 0),
            "workspace_count": int(customer.get("workspace_count") or 0),
            "campaign_limit": int(customer.get("campaign_limit") or 0),
            "campaign_count": int(customer.get("campaign_count") or 0),
            "is_over_limit": any(
                int(customer.get(count_key) or 0) > int(customer.get(limit_key) or 0)
                for limit_key, count_key in (
                    ("seat_limit", "seat_count"),
                    ("workspace_limit", "workspace_count"),
                    ("campaign_limit", "campaign_count"),
                )
            ),
        }
        metadata = dict(customer.get("metadata_json") or {})
        renewal_risk = "due_soon" if customer.get("status") == "renewal_due" else "stable"
        return {
            "customer_account": customer,
            "plan": plan,
            "billing_profile": billing_profile,
            "subscription": dict((subscription_snapshot or {}).get("subscription") or {}),
            "wallets": dict((subscription_snapshot or {}).get("wallets") or {}),
            "entitlement_count": len(entitlements),
            "lifecycle_summary": {
                "status": customer.get("status"),
                "plan_id": plan.get("plan_id"),
                "plan_display_name": plan.get("display_name"),
                "renewal_due_at": customer.get("renewal_due_at"),
                "renewal_risk": renewal_risk,
                "renewal_tracker_status": metadata.get("renewal_tracker_status", "stable"),
                "dunning_status": metadata.get("dunning_status", "clear"),
                "pilot_conversion_status": metadata.get("pilot_conversion_status", "watch"),
                "expansion_status": metadata.get("expansion_status", "clear"),
                "upgrade_recommendation_plan_id": metadata.get("upgrade_recommendation_plan_id"),
                "churn_risk_status": metadata.get("churn_risk_status", "stable"),
                "churn_risk_level": metadata.get("churn_risk_level", "low"),
            },
            "limit_posture": limit_posture,
        }
