from __future__ import annotations

from decimal import Decimal
import json
import os
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

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

    def start_one_time_checkout(
        self,
        *,
        account_id: str,
        package_id: str,
        amount: float,
        bonus: float,
        price_usd: float,
    ) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "package_id": package_id,
            "checkout_url": f"https://stub.local/checkout/story-credits/{package_id}?account_id={account_id}&amount={int(amount)}&bonus={int(bonus)}&price={price_usd}",
            "session_id": f"checkout_{account_id}_{package_id}",
            "status": "created",
        }

    def start_one_time_checkout(
        self,
        *,
        account_id: str,
        package_id: str,
        amount: float,
        bonus: float,
        price_usd: float,
    ) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "package_id": package_id,
            "checkout_url": f"https://stub.local/checkout/story-credits/{package_id}?account_id={account_id}&amount={int(amount)}&bonus={int(bonus)}&price={price_usd}",
            "session_id": f"checkout_{account_id}_{package_id}",
            "status": "created",
        }


class AppStoreProviderStub:
    provider_id = "app_store_stub"


class GooglePlayProviderStub:
    provider_id = "google_play_stub"


def _decode_jwt_payload(value: str) -> Dict[str, Any]:
    parts = str(value or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class AppStoreProvider:
    provider_id = "app_store"

    def __init__(self) -> None:
        self.bearer_token = str(os.getenv("NARRATIVEOS_APPLE_BILLING_BEARER_TOKEN", "")).strip() or None
        self.default_environment = str(os.getenv("NARRATIVEOS_APPLE_BILLING_ENV", "sandbox")).strip() or "sandbox"
        self.tier_map = self._tier_map(os.getenv("NARRATIVEOS_APPLE_TIER_MAP_JSON", ""))

    def _tier_map(self, raw: str) -> Dict[str, str]:
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if str(key) and str(value)}

    def configured(self) -> bool:
        return bool(self.bearer_token)

    def _environment(self, value: Optional[str] = None) -> str:
        environment = str(value or self.default_environment or "sandbox").lower()
        return "production" if environment in {"production", "prod", "live"} else "sandbox"

    def _base_url(self, environment: str) -> str:
        if environment == "production":
            return "https://api.storekit.itunes.apple.com"
        return "https://api.storekit-sandbox.itunes.apple.com"

    def verify_purchase(
        self,
        *,
        original_transaction_id: Optional[str] = None,
        signed_transaction_info: Optional[str] = None,
        tier_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        env_name = self._environment(environment)
        decoded = _decode_jwt_payload(signed_transaction_info or "")
        if original_transaction_id and self.configured():
            response = httpx.get(
                f"{self._base_url(env_name)}/inApps/v1/subscriptions/{original_transaction_id}",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            last_transactions = list(payload.get("data") or [])
            transaction_info = decoded
            if last_transactions:
                last_transactions = list((last_transactions[0] or {}).get("lastTransactions") or [])
                if last_transactions:
                    transaction_info = _decode_jwt_payload(last_transactions[0].get("signedTransactionInfo", ""))
            product_id = str(transaction_info.get("productId") or "").strip()
            resolved_tier = self.tier_map.get(product_id) or tier_id or product_id or "play_pass"
            return {
                "provider": self.provider_id,
                "provider_ref": str(transaction_info.get("originalTransactionId") or original_transaction_id or ""),
                "provider_order_id": str(transaction_info.get("transactionId") or ""),
                "provider_customer_id": None,
                "provider_checkout_session_id": None,
                "tier_id": resolved_tier,
                "status": "active" if str(transaction_info.get("expiresDate") or "") else "trialing",
                "period_start": None,
                "period_end": None,
                "cancel_at_period_end": False,
                "environment": env_name,
                "verification_status": "verified",
                "payload_json": {"apple_response": payload, "transaction_info": transaction_info},
            }
        if decoded:
            product_id = str(decoded.get("productId") or "").strip()
            expires_ms = decoded.get("expiresDate")
            purchase_ms = decoded.get("purchaseDate")
            return {
                "provider": self.provider_id,
                "provider_ref": str(decoded.get("originalTransactionId") or original_transaction_id or ""),
                "provider_order_id": str(decoded.get("transactionId") or ""),
                "provider_customer_id": None,
                "provider_checkout_session_id": None,
                "tier_id": self.tier_map.get(product_id) or tier_id or product_id or "play_pass",
                "status": "active" if expires_ms else "trialing",
                "period_start": datetime.fromtimestamp(int(purchase_ms) / 1000.0, tz=timezone.utc).isoformat() if purchase_ms else None,
                "period_end": datetime.fromtimestamp(int(expires_ms) / 1000.0, tz=timezone.utc).isoformat() if expires_ms else None,
                "cancel_at_period_end": False,
                "environment": str(decoded.get("environment") or env_name),
                "verification_status": "decoded_unverified",
                "payload_json": {"transaction_info": decoded},
            }
        raise RuntimeError("app_store_not_configured")

    def parse_server_notification(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        signed_payload = str(payload.get("signedPayload") or "")
        decoded = _decode_jwt_payload(signed_payload)
        data = dict(decoded.get("data") or {})
        signed_transaction_info = data.get("signedTransactionInfo")
        verified = self.verify_purchase(
            original_transaction_id=(data.get("originalTransactionId") or payload.get("originalTransactionId")),
            signed_transaction_info=signed_transaction_info,
            environment=decoded.get("environment"),
        )
        verified["payload_json"] = {
            **dict(verified.get("payload_json") or {}),
            "notification": payload,
            "signed_payload_decoded": decoded,
        }
        verified["provider_event_type"] = str(decoded.get("notificationType") or payload.get("notificationType") or "apple_notification")
        return verified


class GooglePlayProvider:
    provider_id = "google_play"

    def __init__(self) -> None:
        self.access_token = str(os.getenv("NARRATIVEOS_GOOGLE_PLAY_ACCESS_TOKEN", "")).strip() or None
        self.package_name = str(os.getenv("NARRATIVEOS_GOOGLE_PLAY_PACKAGE_NAME", "")).strip() or None
        self.default_environment = str(os.getenv("NARRATIVEOS_GOOGLE_PLAY_ENV", "production")).strip() or "production"
        self.tier_map = self._tier_map(os.getenv("NARRATIVEOS_GOOGLE_PLAY_TIER_MAP_JSON", ""))

    def _tier_map(self, raw: str) -> Dict[str, str]:
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if str(key) and str(value)}

    def configured(self) -> bool:
        return bool(self.access_token and self.package_name)

    def verify_purchase(
        self,
        *,
        purchase_token: str,
        subscription_id: Optional[str] = None,
        package_name: Optional[str] = None,
        tier_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_package_name = str(package_name or self.package_name or "").strip()
        if not resolved_package_name or not purchase_token or not self.configured():
            raise RuntimeError("google_play_not_configured")
        resolved_subscription_id = str(subscription_id or "").strip()
        response = httpx.get(
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{resolved_package_name}/purchases/subscriptionsv2/tokens/{purchase_token}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        line_items = list(payload.get("lineItems") or [])
        latest_item = line_items[0] if line_items else {}
        product_id = str(latest_item.get("productId") or resolved_subscription_id or "").strip()
        expiry_time = latest_item.get("expiryTime")
        start_time = latest_item.get("startTime")
        return {
            "provider": self.provider_id,
            "provider_ref": purchase_token,
            "provider_order_id": str(payload.get("latestOrderId") or ""),
            "provider_customer_id": str(payload.get("obfuscatedExternalAccountId") or ""),
            "provider_checkout_session_id": None,
            "tier_id": self.tier_map.get(product_id) or tier_id or product_id or "play_pass",
            "status": "active" if str(payload.get("subscriptionState") or "").upper() in {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"} else "canceled",
            "period_start": start_time,
            "period_end": expiry_time,
            "cancel_at_period_end": str(payload.get("subscriptionState") or "").upper() in {"SUBSCRIPTION_STATE_CANCELED", "SUBSCRIPTION_STATE_EXPIRED"},
            "environment": str(environment or self.default_environment or "production"),
            "verification_status": "verified",
            "payload_json": payload,
        }

    def parse_notification(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = dict(payload.get("message") or {})
        notification = dict(payload.get("subscriptionNotification") or message.get("subscriptionNotification") or payload.get("subscription_notification") or {})
        purchase_token = str(notification.get("purchaseToken") or payload.get("purchaseToken") or "")
        subscription_id = str(notification.get("subscriptionId") or payload.get("subscriptionId") or "")
        verified = self.verify_purchase(
            purchase_token=purchase_token,
            subscription_id=subscription_id,
            package_name=payload.get("packageName") or message.get("packageName"),
        )
        verified["payload_json"] = {
            **dict(verified.get("payload_json") or {}),
            "notification": payload,
        }
        verified["provider_event_type"] = str(notification.get("notificationType") or payload.get("notificationType") or "google_notification")
        return verified


class StripeCheckoutProvider:
    provider_id = "stripe"
    api_version = "2026-02-25.clover"

    def __init__(
        self,
        *,
        subscription_price_map: Dict[str, str],
        ink_price_map: Dict[str, str],
        app_base_url: str,
        secret_key: Optional[str],
        publishable_key: Optional[str],
    ) -> None:
        self.subscription_price_map = {str(key): str(value) for key, value in dict(subscription_price_map or {}).items() if str(key) and str(value)}
        self.ink_price_map = {str(key): str(value) for key, value in dict(ink_price_map or {}).items() if str(key) and str(value)}
        self.app_base_url = str(app_base_url or "http://127.0.0.1:8000/app").rstrip("/")
        self.secret_key = str(secret_key or "").strip() or None
        self.publishable_key = str(publishable_key or "").strip() or None

    def configured(self) -> bool:
        return bool(self.secret_key and (self.subscription_price_map or self.ink_price_map))

    def subscription_prices_configured(self) -> bool:
        return bool(self.secret_key and self.subscription_price_map)

    def ink_prices_configured(self) -> bool:
        return bool(self.secret_key and self.ink_price_map)

    def _stripe_module(self):
        try:
            import stripe  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("stripe_sdk_missing") from exc
        stripe.api_key = self.secret_key
        if hasattr(stripe, "api_version"):
            stripe.api_version = self.api_version
        return stripe

    def _payload(self, value: Any) -> Dict[str, Any]:
        def _normalize(item: Any) -> Any:
            if isinstance(item, Decimal):
                return float(item)
            if isinstance(item, dict):
                return {str(key): _normalize(val) for key, val in item.items()}
            if isinstance(item, (list, tuple)):
                return [_normalize(entry) for entry in item]
            return item

        if hasattr(value, "to_dict"):
            return _normalize(dict(value.to_dict()))
        return _normalize(dict(value))

    def start_checkout(
        self,
        *,
        account_id: str,
        tier_id: str,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.subscription_prices_configured():
            raise RuntimeError("stripe_not_configured")
        price_id = self.subscription_price_map.get(tier_id)
        if not price_id:
            raise ValueError("stripe_price_not_configured_for_tier:%s" % tier_id)
        stripe = self._stripe_module()
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url or f"{self.app_base_url}?checkout=success&checkout_session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=cancel_url or f"{self.app_base_url}?checkout=cancel",
            client_reference_id=account_id,
            customer_email=customer_email or None,
            metadata={
                "account_id": account_id,
                "tier_id": tier_id,
                **{str(key): str(value) for key, value in dict(metadata or {}).items()},
            },
            subscription_data={
                "metadata": {
                    "account_id": account_id,
                    "tier_id": tier_id,
                }
            },
        )
        payload = self._payload(session)
        return {
            "provider": self.provider_id,
            "tier_id": tier_id,
            "checkout_url": payload.get("url"),
            "session_id": payload.get("id"),
            "status": payload.get("status", "created"),
            "provider_ref": payload.get("id"),
            "price_id": price_id,
        }

    def start_one_time_checkout(
        self,
        *,
        account_id: str,
        package_id: str,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.ink_prices_configured():
            raise RuntimeError("stripe_not_configured")
        price_id = self.ink_price_map.get(package_id)
        if not price_id:
            raise ValueError("stripe_price_not_configured_for_package:%s" % package_id)
        stripe = self._stripe_module()
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url or f"{self.app_base_url}?checkout=success&checkout_session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=cancel_url or f"{self.app_base_url}?checkout=cancel",
            client_reference_id=account_id,
            customer_email=customer_email or None,
            metadata={
                "account_id": account_id,
                "package_id": package_id,
                "checkout_kind": "ink",
                "wallet_type": "story_credits",
                **{str(key): str(value) for key, value in dict(metadata or {}).items()},
            },
        )
        payload = self._payload(session)
        return {
            "provider": self.provider_id,
            "package_id": package_id,
            "checkout_url": payload.get("url"),
            "session_id": payload.get("id"),
            "status": payload.get("status", "created"),
            "provider_ref": payload.get("id"),
            "price_id": price_id,
        }

    def retrieve_checkout_session(self, *, session_id: str) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        session = stripe.checkout.Session.retrieve(session_id)
        return self._payload(session)

    def retrieve_subscription(self, *, subscription_id: str) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        subscription = stripe.Subscription.retrieve(subscription_id)
        return self._payload(subscription)

    def start_customer_portal(
        self,
        *,
        customer_id: str,
        return_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url or self.app_base_url,
        )
        payload = self._payload(session)
        return {
            "provider": self.provider_id,
            "customer_id": customer_id,
            "portal_url": payload.get("url"),
            "session_id": payload.get("id"),
        }

    def ensure_customer(
        self,
        *,
        customer_email: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
        else:
            customer = stripe.Customer.create(
                email=customer_email or None,
                metadata={str(key): str(value) for key, value in dict(metadata or {}).items()},
            )
        return self._payload(customer)

    def create_invoice(
        self,
        *,
        customer_id: str,
        currency: str,
        line_items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        days_until_due: int = 30,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        for item in line_items:
            amount_cents = int(round(float(item.get("amount_usd") or 0.0) * 100))
            stripe.InvoiceItem.create(
                customer=customer_id,
                currency=currency.lower(),
                amount=amount_cents,
                description=str(item.get("description") or item.get("metric_type") or "usage_charge"),
                metadata={str(key): str(value) for key, value in dict(metadata or {}).items()},
            )
        invoice = stripe.Invoice.create(
            customer=customer_id,
            collection_method="send_invoice",
            days_until_due=days_until_due,
            # Stripe defaults pending_invoice_items_behavior to "exclude".
            # We stage invoice items before invoice creation, so opt in to
            # including those pending items on the generated invoice draft.
            pending_invoice_items_behavior="include",
            metadata={str(key): str(value) for key, value in dict(metadata or {}).items()},
        )
        finalized = stripe.Invoice.finalize_invoice(invoice["id"] if isinstance(invoice, dict) else getattr(invoice, "id"))
        return self._payload(finalized)

    def retrieve_invoice(self, *, invoice_id: str) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        invoice = stripe.Invoice.retrieve(invoice_id)
        return self._payload(invoice)

    def create_credit_note(
        self,
        *,
        invoice_id: str,
        amount_usd: float,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("stripe_not_configured")
        stripe = self._stripe_module()
        credit_note = stripe.CreditNote.create(
            invoice=invoice_id,
            amount=int(round(float(amount_usd or 0.0) * 100)),
            reason=reason or None,
        )
        return self._payload(credit_note)


class MonetizationService:
    def __init__(self, repository: SQLAlchemyPlatformRepository, *, base_dir: Optional[Path] = None) -> None:
        self.repository = repository
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[3])
        self.tier_config = self._load_tier_config()
        self.web_checkout = WebCheckoutProvider()
        self.stripe_checkout = StripeCheckoutProvider(
            subscription_price_map=self._stripe_price_map(),
            ink_price_map=self._stripe_ink_price_map(),
            app_base_url=self._app_base_url(),
            secret_key=os.getenv("NARRATIVEOS_STRIPE_SECRET_KEY"),
            publishable_key=os.getenv("NARRATIVEOS_STRIPE_PUBLISHABLE_KEY"),
        )
        self.app_store = AppStoreProvider()
        self.google_play = GooglePlayProvider()

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        try:
            normalized = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    def _load_tier_config(self) -> Dict[str, Any]:
        path = self.base_dir / "configs" / "monetization_tiers.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _app_base_url(self) -> str:
        return str(os.getenv("NARRATIVEOS_APP_BASE_URL", "http://127.0.0.1:8000/app"))

    def _stripe_price_map(self) -> Dict[str, str]:
        raw = os.getenv("NARRATIVEOS_STRIPE_PRICE_MAP_JSON", "")
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if str(key) and str(value)}

    def _stripe_ink_price_map(self) -> Dict[str, str]:
        raw = os.getenv("NARRATIVEOS_STRIPE_INK_PRICE_MAP_JSON", "")
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if str(key) and str(value)}

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

    def ink_packages(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in list(self.tier_config.get("ink_packages") or [])]

    def get_ink_package(self, package_id: str) -> Dict[str, Any]:
        normalized = str(package_id or "").strip()
        for package in self.ink_packages():
            if normalized in {
                str(package.get("package_id") or ""),
                str(package.get("amount") or ""),
                str(int(float(package.get("amount") or 0.0) + float(package.get("bonus") or 0.0))),
            }:
                return dict(package)
        raise KeyError("unknown_ink_package:%s" % normalized)

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
            "ink_packages": self.ink_packages(),
            "metering": self.metering_rules(),
            "entitlement_matrix": self.entitlement_matrix(),
            "author_access_levels": self.author_access_levels(),
            "checkout_provider_status": self.checkout_provider_status(),
        }

    def checkout_provider_status(self, provider: Optional[str] = None) -> Dict[str, Any]:
        resolved_provider = str(provider or os.getenv("NARRATIVEOS_BILLING_PROVIDER", "web_stub"))
        if resolved_provider == self.web_checkout.provider_id:
            return {
                "provider": resolved_provider,
                "configured": True,
                "publishable_key": None,
            }
        if resolved_provider == self.stripe_checkout.provider_id:
            return {
                "provider": resolved_provider,
                "configured": self.stripe_checkout.configured(),
                "publishable_key": self.stripe_checkout.publishable_key,
                "subscription_prices_configured": self.stripe_checkout.subscription_prices_configured(),
                "ink_prices_configured": self.stripe_checkout.ink_prices_configured(),
            }
        if resolved_provider == self.app_store.provider_id:
            return {
                "provider": resolved_provider,
                "configured": self.app_store.configured(),
                "publishable_key": None,
            }
        if resolved_provider == self.google_play.provider_id:
            return {
                "provider": resolved_provider,
                "configured": self.google_play.configured(),
                "publishable_key": None,
            }
        return {
            "provider": resolved_provider,
            "configured": False,
            "publishable_key": None,
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

    def start_checkout(
        self,
        *,
        account_id: str,
        tier_id: str,
        provider: str = "web_stub",
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if provider == self.web_checkout.provider_id:
            return self.web_checkout.start_checkout(account_id=account_id, tier_id=tier_id)
        if provider == self.stripe_checkout.provider_id:
            return self.stripe_checkout.start_checkout(
                account_id=account_id,
                tier_id=tier_id,
                customer_email=customer_email,
                metadata=metadata,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        raise ValueError("unsupported_checkout_provider")

    def start_ink_checkout(
        self,
        *,
        account_id: str,
        package_id: str,
        provider: str = "web_stub",
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        package = self.get_ink_package(package_id)
        resolved_package_id = str(package.get("package_id") or package_id)
        if provider == self.web_checkout.provider_id:
            return self.web_checkout.start_one_time_checkout(
                account_id=account_id,
                package_id=resolved_package_id,
                amount=float(package.get("amount") or 0.0),
                bonus=float(package.get("bonus") or 0.0),
                price_usd=float(package.get("price_usd") or 0.0),
            )
        if provider == self.stripe_checkout.provider_id:
            return self.stripe_checkout.start_one_time_checkout(
                account_id=account_id,
                package_id=resolved_package_id,
                customer_email=customer_email,
                metadata=metadata,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        raise ValueError("unsupported_checkout_provider")

    def start_customer_portal(
        self,
        *,
        account_id: str,
        customer_id: str,
        provider: Optional[str] = None,
        return_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_provider = str(provider or os.getenv("NARRATIVEOS_BILLING_PROVIDER", "web_stub"))
        if resolved_provider == self.web_checkout.provider_id:
            return {
                "provider": resolved_provider,
                "customer_id": customer_id,
                "portal_url": f"https://stub.local/customer-portal/{account_id}",
                "session_id": f"portal_{account_id}",
            }
        if resolved_provider == self.stripe_checkout.provider_id:
            return self.stripe_checkout.start_customer_portal(
                customer_id=customer_id,
                return_url=return_url,
            )
        raise ValueError("unsupported_checkout_provider")

    def ensure_stripe_customer(
        self,
        *,
        customer_email: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.stripe_checkout.ensure_customer(
            customer_email=customer_email,
            metadata=metadata,
            customer_id=customer_id,
        )

    def issue_stripe_invoice(
        self,
        *,
        customer_id: str,
        currency: str,
        line_items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        days_until_due: int = 30,
    ) -> Dict[str, Any]:
        return self.stripe_checkout.create_invoice(
            customer_id=customer_id,
            currency=currency,
            line_items=line_items,
            metadata=metadata,
            days_until_due=days_until_due,
        )

    def retrieve_stripe_invoice(self, *, invoice_id: str) -> Dict[str, Any]:
        return self.stripe_checkout.retrieve_invoice(invoice_id=invoice_id)

    def create_stripe_credit_note(self, *, invoice_id: str, amount_usd: float, reason: Optional[str] = None) -> Dict[str, Any]:
        return self.stripe_checkout.create_credit_note(invoice_id=invoice_id, amount_usd=amount_usd, reason=reason)

    def retrieve_checkout_session(
        self,
        *,
        checkout_session_id: str,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_provider = str(provider or os.getenv("NARRATIVEOS_BILLING_PROVIDER", "web_stub"))
        if resolved_provider == self.stripe_checkout.provider_id:
            return self.stripe_checkout.retrieve_checkout_session(session_id=checkout_session_id)
        raise ValueError("unsupported_checkout_provider")

    def retrieve_subscription(
        self,
        *,
        subscription_ref: str,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_provider = str(provider or os.getenv("NARRATIVEOS_BILLING_PROVIDER", "web_stub"))
        if resolved_provider == self.stripe_checkout.provider_id:
            return self.stripe_checkout.retrieve_subscription(subscription_id=subscription_ref)
        raise ValueError("unsupported_checkout_provider")

    def verify_mobile_purchase(self, *, provider: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if provider == self.app_store.provider_id:
            return self.app_store.verify_purchase(
                original_transaction_id=payload.get("original_transaction_id"),
                signed_transaction_info=payload.get("signed_transaction_info"),
                tier_id=payload.get("tier_id"),
                environment=payload.get("environment"),
            )
        if provider == self.google_play.provider_id:
            return self.google_play.verify_purchase(
                purchase_token=payload["purchase_token"],
                subscription_id=payload.get("subscription_id"),
                package_name=payload.get("package_name"),
                tier_id=payload.get("tier_id"),
                environment=payload.get("environment"),
            )
        raise ValueError("unsupported_mobile_purchase_provider")

    def ingest_store_notification(self, *, provider: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if provider == self.app_store.provider_id:
            return self.app_store.parse_server_notification(payload)
        if provider == self.google_play.provider_id:
            return self.google_play.parse_notification(payload)
        raise ValueError("unsupported_store_notification_provider")
