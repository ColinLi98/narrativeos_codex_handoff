from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository


class WebCheckoutProvider:
    provider_id = "web_stub"

    def start_checkout(self, *, account_id: str, tier_id: str) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "tier_id": tier_id,
            "checkout_url": f"https://stub.local/checkout/{tier_id}?account_id={account_id}",
            "session_id": f"checkout_{account_id}_{tier_id}",
            "status": "created",
        }


class AppStoreProviderStub:
    provider_id = "app_store_stub"


class GooglePlayProviderStub:
    provider_id = "google_play_stub"


class MonetizationService:
    def __init__(self, repository: SQLAlchemyPlatformRepository, *, base_dir: Optional[Path] = None) -> None:
        self.repository = repository
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[3])
        self.tier_config = self._load_tier_config()
        self.web_checkout = WebCheckoutProvider()
        self.app_store = AppStoreProviderStub()
        self.google_play = GooglePlayProviderStub()

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    def _load_tier_config(self) -> Dict[str, Any]:
        path = self.base_dir / "configs" / "monetization_tiers.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def config_version(self) -> str:
        return str(self.tier_config.get("config_version", "unknown"))

    def tiers(self) -> List[Dict[str, Any]]:
        return list(self.tier_config.get("tiers", []))

    def get_tier(self, tier_id: str) -> Dict[str, Any]:
        for tier in self.tiers():
            if tier["tier_id"] == tier_id:
                return dict(tier)
        raise KeyError("unknown_tier:%s" % tier_id)

    def metering_rules(self) -> Dict[str, Any]:
        return dict(self.tier_config.get("metering", {}))

    def credit_policy(self) -> Dict[str, Any]:
        return dict(self.tier_config.get("credit_policy", {}))

    def author_access_levels(self) -> Dict[str, int]:
        return {
            key: int(value)
            for key, value in dict(self.tier_config.get("author_access_levels", {})).items()
        }

    def entitlement_matrix(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self.tier_config.get("entitlement_matrix", {})))

    def entitlement_rule(self, surface: str, action: str) -> Dict[str, Any]:
        matrix = self.entitlement_matrix()
        return dict(matrix.get(surface, {}).get(action, {}))

    def tier_capabilities(self, tier_id: str) -> Dict[str, bool]:
        tier = self.get_tier(tier_id)
        return {
            key: bool(value)
            for key, value in dict(tier.get("capabilities", {})).items()
        }

    def config_snapshot(self) -> Dict[str, Any]:
        return {
            "config_version": self.config_version(),
            "tiers": self.tiers(),
            "credit_policy": self.credit_policy(),
            "metering": self.metering_rules(),
            "entitlement_matrix": self.entitlement_matrix(),
            "author_access_levels": self.author_access_levels(),
        }

    def resolve_account_id(
        self,
        *,
        account_id: Optional[str] = None,
        reader_id: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> str:
        return str(account_id or reader_id or author_id or "")

    def active_subscription(self, *, account_id: str) -> Optional[Dict[str, Any]]:
        if not account_id:
            return None
        subscriptions = self.list_subscriptions(account_id=account_id)
        return next(
            (item for item in subscriptions if item["status"] in {"trialing", "active"}),
            None,
        )

    def _lifecycle_reason(self, subscription: Dict[str, Any]) -> str:
        status = subscription.get("status")
        if status == "past_due":
            return "payment_retry_required"
        if status == "paused":
            return "paused_by_operator"
        if status == "canceled":
            return "subscription_canceled"
        if status == "expired":
            if subscription.get("cancel_at_period_end"):
                return "cancel_at_period_end_reached"
            return "subscription_expired"
        if status == "trialing":
            return "trial_active"
        return "subscription_active"

    def _lifecycle_next_action(self, subscription: Dict[str, Any]) -> str:
        return {
            "trialing": "activate_subscription",
            "active": "none",
            "past_due": "retry_payment",
            "paused": "resume_subscription",
            "canceled": "renew_subscription",
            "expired": "renew_subscription",
        }.get(subscription.get("status"), "none")

    def _augment_subscription_snapshot(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = dict(subscription)
        period_end = self._parse_datetime(snapshot.get("period_end"))
        now = self._utcnow()
        snapshot["period_end_passed"] = bool(period_end and period_end <= now)
        snapshot["renewable"] = snapshot.get("status") in {"past_due", "canceled", "expired"}
        snapshot["lifecycle_reason"] = self._lifecycle_reason(snapshot)
        snapshot["next_action"] = self._lifecycle_next_action(snapshot)
        snapshot["config_version"] = self.config_version()
        return snapshot

    def reconcile_subscription_lifecycle(self, subscription_id: str) -> Dict[str, Any]:
        subscription = self.repository.get_subscription(subscription_id)
        status = subscription.get("status")
        period_end = self._parse_datetime(subscription.get("period_end"))
        now = self._utcnow()
        if status == "expired":
            return self._augment_subscription_snapshot(subscription)
        if status in {"canceled", "past_due"} and period_end and period_end <= now:
            subscription = self.repository.save_subscription(
                {
                    **subscription,
                    "status": "expired",
                    "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
                }
            )
            return self._augment_subscription_snapshot(subscription)
        if period_end and period_end <= now and status in {"trialing", "active"}:
            next_status = "expired" if subscription.get("cancel_at_period_end") or status == "trialing" else "past_due"
            subscription = self.repository.save_subscription(
                {
                    **subscription,
                    "status": next_status,
                    "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
                }
            )
        return self._augment_subscription_snapshot(subscription)

    def list_subscriptions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        raw = self.repository.list_subscriptions(account_id=account_id)
        reconciled = [self.reconcile_subscription_lifecycle(item["subscription_id"]) for item in raw]
        if status is not None:
            reconciled = [item for item in reconciled if item.get("status") == status]
        return reconciled

    def create_subscription(
        self,
        *,
        account_id: str,
        tier_id: str,
        provider: str = "web_stub",
        provider_ref: Optional[str] = None,
        status: str = "active",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        cancel_at_period_end: bool = False,
    ) -> Dict[str, Any]:
        now = self._utcnow()
        start = period_start or now.isoformat()
        end = period_end or (now + timedelta(days=30)).isoformat()
        subscription = self.repository.save_subscription(
            {
                "account_id": account_id,
                "tier_id": tier_id,
                "provider": provider,
                "provider_ref": provider_ref,
                "status": status,
                "period_start": start,
                "period_end": end,
                "cancel_at_period_end": cancel_at_period_end,
            }
        )
        if status in {"trialing", "active"}:
            self.refill_subscription_wallets(subscription["subscription_id"])
        return subscription

    def change_subscription_state(self, subscription_id: str, *, status: str, cancel_at_period_end: Optional[bool] = None) -> Dict[str, Any]:
        current = self.repository.get_subscription(subscription_id)
        now = self._utcnow()
        next_period_start = current.get("period_start")
        next_period_end = current.get("period_end")
        if status in {"trialing", "active"} and current.get("status") not in {"trialing", "active"}:
            next_period_start = now.isoformat()
            next_period_end = (now + timedelta(days=30)).isoformat()
        updated = self.repository.save_subscription(
            {
                **current,
                "status": status,
                "period_start": next_period_start,
                "period_end": next_period_end,
                "cancel_at_period_end": current["cancel_at_period_end"] if cancel_at_period_end is None else cancel_at_period_end,
            }
        )
        if status in {"trialing", "active"}:
            self.refill_subscription_wallets(updated["subscription_id"])
        return self._augment_subscription_snapshot(updated)

    def renew_subscription(
        self,
        subscription_id: str,
        *,
        status: str = "active",
        cancel_at_period_end: bool = False,
    ) -> Dict[str, Any]:
        current = self.repository.get_subscription(subscription_id)
        now = self._utcnow()
        updated = self.repository.save_subscription(
            {
                **current,
                "status": status,
                "period_start": now.isoformat(),
                "period_end": (now + timedelta(days=30)).isoformat(),
                "cancel_at_period_end": cancel_at_period_end,
            }
        )
        self.refill_subscription_wallets(updated["subscription_id"])
        return self._augment_subscription_snapshot(updated)

    def refill_subscription_wallets(self, subscription_id: str) -> Dict[str, Any]:
        subscription = self.repository.get_subscription(subscription_id)
        tier = self.get_tier(subscription["tier_id"])
        account_id = subscription["account_id"]
        now = self._utcnow().isoformat()
        story_wallet = self.repository.save_entitlement(
            {
                "account_id": account_id,
                "reader_id": account_id,
                "entitlement_id": "wallet_story_%s" % account_id,
                "entitlement_type": "credits",
                "wallet_type": "story_credits",
                "tier_id": tier["tier_id"],
                "status": "active",
                "balance": tier["monthly_story_credits"],
                "expires_at": subscription["period_end"],
            }
        )
        studio_wallet = self.repository.save_entitlement(
            {
                "account_id": account_id,
                "reader_id": account_id,
                "entitlement_id": "wallet_studio_%s" % account_id,
                "entitlement_type": "credits",
                "wallet_type": "studio_credits",
                "tier_id": tier["tier_id"],
                "status": "active",
                "balance": tier["monthly_studio_credits"],
                "expires_at": subscription["period_end"],
            }
        )
        return {
            "subscription_id": subscription_id,
            "account_id": account_id,
            "tier_id": tier["tier_id"],
            "refilled_at": now,
            "story_wallet": story_wallet,
            "studio_wallet": studio_wallet,
        }

    def start_checkout(self, *, account_id: str, tier_id: str, provider: str = "web_stub") -> Dict[str, Any]:
        if provider != self.web_checkout.provider_id:
            raise ValueError("unsupported_checkout_provider")
        return self.web_checkout.start_checkout(account_id=account_id, tier_id=tier_id)
