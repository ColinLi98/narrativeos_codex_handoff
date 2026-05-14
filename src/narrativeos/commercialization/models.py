from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


COMMERCIAL_ACCOUNT_STATUSES = {"trial", "active", "paused", "canceled", "renewal_due"}
COMMERCIAL_PLAN_STATUSES = {"active", "paused", "retired"}
BILLING_PROFILE_STATUSES = {"active", "paused", "disabled"}


def _validate_enum(value: str, *, name: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError("%s_invalid:%s" % (name, normalized or ""))
    return normalized


def _non_negative_int(value: Any, *, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s_invalid:%s" % (name, value)) from exc
    if normalized < 0:
        raise ValueError("%s_negative:%s" % (name, normalized))
    return normalized


@dataclass
class CommercialPlan:
    plan_id: str
    display_name: str
    subscription_tier: str
    monthly_price_usd: float
    status: str
    seat_limit: int
    workspace_limit: int
    campaign_limit: int
    features: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="commercial_plan_status", allowed=COMMERCIAL_PLAN_STATUSES)
        self.seat_limit = _non_negative_int(self.seat_limit, name="seat_limit")
        self.workspace_limit = _non_negative_int(self.workspace_limit, name="workspace_limit")
        self.campaign_limit = _non_negative_int(self.campaign_limit, name="campaign_limit")
        self.monthly_price_usd = float(self.monthly_price_usd)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommercialPlan":
        payload = dict(data or {})
        return cls(
            plan_id=str(payload.get("plan_id") or ""),
            display_name=str(payload.get("display_name") or ""),
            subscription_tier=str(payload.get("subscription_tier") or ""),
            monthly_price_usd=float(payload.get("monthly_price_usd", 0.0) or 0.0),
            status=str(payload.get("status") or ""),
            seat_limit=payload.get("seat_limit", 0),
            workspace_limit=payload.get("workspace_limit", 0),
            campaign_limit=payload.get("campaign_limit", 0),
            features=dict(payload.get("features") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerAccount:
    customer_account_id: str
    account_id: str
    status: str
    plan_id: str
    seat_limit: int
    workspace_limit: int
    campaign_limit: int
    seat_count: int = 0
    workspace_count: int = 0
    campaign_count: int = 0
    display_name: Optional[str] = None
    renewal_due_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="customer_account_status", allowed=COMMERCIAL_ACCOUNT_STATUSES)
        self.seat_limit = _non_negative_int(self.seat_limit, name="seat_limit")
        self.workspace_limit = _non_negative_int(self.workspace_limit, name="workspace_limit")
        self.campaign_limit = _non_negative_int(self.campaign_limit, name="campaign_limit")
        self.seat_count = _non_negative_int(self.seat_count, name="seat_count")
        self.workspace_count = _non_negative_int(self.workspace_count, name="workspace_count")
        self.campaign_count = _non_negative_int(self.campaign_count, name="campaign_count")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomerAccount":
        payload = dict(data or {})
        display_name = payload.get("display_name")
        return cls(
            customer_account_id=str(payload.get("customer_account_id") or ""),
            account_id=str(payload.get("account_id") or ""),
            status=str(payload.get("status") or ""),
            plan_id=str(payload.get("plan_id") or ""),
            seat_limit=payload.get("seat_limit", 0),
            workspace_limit=payload.get("workspace_limit", 0),
            campaign_limit=payload.get("campaign_limit", 0),
            seat_count=payload.get("seat_count", 0),
            workspace_count=payload.get("workspace_count", 0),
            campaign_count=payload.get("campaign_count", 0),
            display_name=str(display_name) if display_name is not None else None,
            renewal_due_at=str(payload.get("renewal_due_at")) if payload.get("renewal_due_at") is not None else None,
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BillingProfile:
    billing_profile_id: str
    customer_account_id: str
    account_id: str
    provider: str
    status: str
    invoice_email: Optional[str] = None
    legal_name: Optional[str] = None
    billing_country: Optional[str] = None
    tax_status: Optional[str] = None
    provider_customer_ref: Optional[str] = None
    profile_payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="billing_profile_status", allowed=BILLING_PROFILE_STATUSES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BillingProfile":
        payload = dict(data or {})
        return cls(
            billing_profile_id=str(payload.get("billing_profile_id") or ""),
            customer_account_id=str(payload.get("customer_account_id") or ""),
            account_id=str(payload.get("account_id") or ""),
            provider=str(payload.get("provider") or ""),
            status=str(payload.get("status") or ""),
            invoice_email=str(payload.get("invoice_email")) if payload.get("invoice_email") is not None else None,
            legal_name=str(payload.get("legal_name")) if payload.get("legal_name") is not None else None,
            billing_country=str(payload.get("billing_country")) if payload.get("billing_country") is not None else None,
            tax_status=str(payload.get("tax_status")) if payload.get("tax_status") is not None else None,
            provider_customer_ref=str(payload.get("provider_customer_ref")) if payload.get("provider_customer_ref") is not None else None,
            profile_payload=dict(payload.get("profile_payload") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
