from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .governance import parse_governance_notes
from .monetization import MonetizationService


class BillingService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        monetization_service: Optional[MonetizationService] = None,
    ) -> None:
        self.repository = repository
        self.monetization = monetization_service or MonetizationService(repository)

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _billing_provider(self) -> str:
        return str(os.getenv("NARRATIVEOS_BILLING_PROVIDER", "web_stub"))

    def _checkout_session_ttl_minutes(self) -> int:
        try:
            return max(5, int(os.getenv("NARRATIVEOS_CHECKOUT_SESSION_TTL_MINUTES", "60")))
        except ValueError:
            return 60

    def _retry_max_attempts(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_BILLING_RETRY_MAX_ATTEMPTS", "3")))
        except ValueError:
            return 3

    def _retry_backoff_minutes(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_BILLING_RETRY_BACKOFF_MINUTES", "30")))
        except ValueError:
            return 30

    def _parse_expires_at(self, value: Optional[str]) -> Optional[datetime]:
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

    def resolve_account_id(
        self,
        *,
        account_id: Optional[str] = None,
        reader_id: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> str:
        return self.monetization.resolve_account_id(
            account_id=account_id,
            reader_id=reader_id,
            author_id=author_id,
        )

    def _normalize_entitlement(self, entitlement: Dict[str, Any], *, world_id: Optional[str] = None) -> Dict[str, Any]:
        payload = dict(entitlement)
        balance = payload.get("balance")
        payload["balance"] = float(balance) if balance is not None else None
        expires_at = self._parse_expires_at(payload.get("expires_at"))
        status = payload.get("status") or "active"
        reason = "active_entitlement"
        if status == "revoked":
            reason = "entitlement_revoked"
        elif expires_at and expires_at <= datetime.now(timezone.utc):
            status = "expired"
            reason = "entitlement_expired"
        elif payload.get("entitlement_type") == "credits" and float(payload.get("balance") or 0.0) < 1.0:
            status = "exhausted"
            wallet_type = payload.get("wallet_type")
            reason = "studio_credits_exhausted" if wallet_type == "studio_credits" else "credits_exhausted"
        elif payload.get("entitlement_type") == "subscriber":
            reason = "subscriber_active"
        elif payload.get("entitlement_type") == "world_pass":
            reason = "world_pass_active"
        elif payload.get("entitlement_type") == "credits":
            wallet_type = payload.get("wallet_type")
            reason = "studio_credits_balance" if wallet_type == "studio_credits" else "credits_balance"
        payload["status"] = status
        payload["reason"] = reason
        payload["world_unlocked"] = bool(
            payload.get("entitlement_type") in {"subscriber", "world_pass"} and (
                payload.get("entitlement_type") == "subscriber"
                or world_id is None
                or payload.get("world_id") in {None, world_id}
            )
        )
        return payload

    def revoke_entitlement(self, entitlement_id: str) -> Dict[str, Any]:
        entitlement = self.repository.get_entitlement(entitlement_id)
        return self._normalize_entitlement(
            self.repository.save_entitlement(
                {
                    **entitlement,
                    "status": "revoked",
                    "balance": 0.0 if entitlement.get("entitlement_type") == "credits" else entitlement.get("balance"),
                }
            ),
            world_id=entitlement.get("world_id"),
        )

    def _subscription_snapshot(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        tier = self.monetization.get_tier(subscription["tier_id"])
        snapshot = {
            "subscription_id": subscription["subscription_id"],
            "account_id": subscription["account_id"],
            "tier_id": subscription["tier_id"],
            "display_name": tier.get("display_name", subscription["tier_id"]),
            "description": tier.get("description", ""),
            "price_usd_monthly": tier.get("price_usd_monthly"),
            "status": subscription["status"],
            "provider": subscription["provider"],
            "period_start": subscription.get("period_start"),
            "period_end": subscription.get("period_end"),
            "cancel_at_period_end": bool(subscription.get("cancel_at_period_end")),
            "reader_access": bool(tier.get("reader_access")),
            "author_access": tier.get("author_access", "none"),
            "capabilities": dict(tier.get("capabilities", {})),
        }
        for key in ("period_end_passed", "renewable", "lifecycle_reason", "next_action", "config_version"):
            if key in subscription:
                snapshot[key] = subscription.get(key)
        return snapshot

    def _config_snapshot(self) -> Dict[str, Any]:
        return self.monetization.config_snapshot()

    def _author_access_rank(self, level: str) -> int:
        return self.monetization.author_access_levels().get(level, 0)

    def _required_tier_snapshot(self, tier_id: Optional[str]) -> Dict[str, Any]:
        if not tier_id:
            return {
                "required_tier": None,
                "required_display_name": None,
                "required_description": None,
            }
        tier = self.monetization.get_tier(tier_id)
        return {
            "required_tier": tier_id,
            "required_display_name": tier.get("display_name", tier_id),
            "required_description": tier.get("description", ""),
        }

    def _wallets_for_account(self, account_id: str) -> Dict[str, Dict[str, Any]]:
        entitlements = self.repository.list_entitlements(account_id=account_id)
        wallets = {}
        for entitlement in entitlements:
            if entitlement.get("entitlement_type") != "credits":
                continue
            wallet_type = entitlement.get("wallet_type") or "story_credits"
            wallets[wallet_type] = self._normalize_entitlement(entitlement)
        wallets.setdefault(
            "story_credits",
            {
                "account_id": account_id,
                "entitlement_type": "credits",
                "wallet_type": "story_credits",
                "status": "exhausted",
                "balance": 0.0,
                "reason": "credits_exhausted",
            },
        )
        wallets.setdefault(
            "studio_credits",
            {
                "account_id": account_id,
                "entitlement_type": "credits",
                "wallet_type": "studio_credits",
                "status": "exhausted",
                "balance": 0.0,
                "reason": "studio_credits_exhausted",
            },
        )
        return wallets

    def _set_wallet_status(
        self,
        *,
        account_id: str,
        wallet_type: str,
        status: str,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        wallet = self._wallets_for_account(account_id).get(wallet_type, {})
        return self.repository.save_entitlement(
            {
                "account_id": account_id,
                "reader_id": account_id,
                "entitlement_id": wallet.get("entitlement_id") or f"wallet_{wallet_type}_{account_id}",
                "entitlement_type": "credits",
                "wallet_type": wallet_type,
                "tier_id": wallet.get("tier_id"),
                "balance": wallet.get("balance"),
                "expires_at": expires_at if expires_at is not None else wallet.get("expires_at"),
                "status": status,
            }
        )

    def _deactivate_subscription_wallets(self, *, account_id: str, expires_at: Optional[str] = None) -> Dict[str, Any]:
        resolved_expires_at = expires_at or self._utcnow().isoformat()
        return {
            "story_wallet": self._normalize_entitlement(
                self._set_wallet_status(
                    account_id=account_id,
                    wallet_type="story_credits",
                    status="expired",
                    expires_at=resolved_expires_at,
                )
            ),
            "studio_wallet": self._normalize_entitlement(
                self._set_wallet_status(
                    account_id=account_id,
                    wallet_type="studio_credits",
                    status="expired",
                    expires_at=resolved_expires_at,
                )
            ),
        }

    def _record_lifecycle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.save_billing_lifecycle_event(payload)

    def _find_subscription_for_event(self, *, account_id: Optional[str], subscription_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if subscription_id:
            try:
                return self.repository.get_subscription(subscription_id)
            except KeyError:
                return None
        if not account_id:
            return None
        subscriptions = self.monetization.list_subscriptions(account_id=account_id)
        return subscriptions[0] if subscriptions else None

    def _checkout_session_summary(self, account_id: str) -> Dict[str, Any]:
        latest = self.repository.latest_billing_checkout_session(account_id=account_id)
        sessions = self.repository.list_billing_checkout_sessions(account_id=account_id, limit=10)
        return {
            "checkout_session": latest,
            "latest_checkout_session": latest,
            "recent_checkout_sessions": sessions,
        }

    def _lifecycle_history_summary(self, account_id: str) -> Dict[str, Any]:
        events = self.repository.list_billing_lifecycle_events(account_id=account_id, limit=20)
        retries = self.repository.list_billing_retry_attempts(account_id=account_id, limit=20)
        by_event_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for item in events:
            event_type = str(item.get("event_type") or "unknown")
            status = str(item.get("status") or "unknown")
            by_event_type[event_type] = by_event_type.get(event_type, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "event_count": len(events),
            "retry_attempt_count": len(retries),
            "by_event_type": by_event_type,
            "by_status": by_status,
            "latest_events": events[:10],
            "latest_retry_attempts": retries[:10],
        }

    def _recommended_subscription_action(self, subscription: Optional[Dict[str, Any]]) -> str:
        if not subscription:
            return "start_checkout"
        status = str(subscription.get("status") or "")
        if status == "past_due":
            return "retry_payment"
        if status in {"canceled", "expired"}:
            return "renew_subscription"
        return "none"

    def _access_snapshot(
        self,
        *,
        required: bool,
        access_tier: str,
        quote: float,
        reason: str,
        entitlement_type: Optional[str],
        balance: Optional[float],
        status: Optional[str],
        account_id: Optional[str] = None,
        tier_id: Optional[str] = None,
        wallet_type: Optional[str] = None,
        provider: Optional[str] = None,
        entitlement_id: Optional[str] = None,
        metering_rule: Optional[str] = None,
    ) -> Dict[str, Any]:
        snapshot = {
            "required": required,
            "access_tier": access_tier,
            "quote": float(quote),
            "reason": reason,
            "entitlement_type": entitlement_type,
            "balance": float(balance) if balance is not None else None,
            "status": status,
            "account_id": account_id,
            "tier_id": tier_id,
            "wallet_type": wallet_type,
            "provider": provider,
            "metering_rule": metering_rule,
            "config_version": self.monetization.config_version(),
        }
        if entitlement_id is not None:
            snapshot["entitlement_id"] = entitlement_id
        return snapshot

    def _metering_rule_units(self, metering_rule: Optional[str]) -> float:
        if not metering_rule:
            return 0.0
        return float(self.monetization.metering_rules().get(metering_rule, 0.0))

    def _required_units_for_rule(self, rule: Dict[str, Any]) -> float:
        return self._metering_rule_units(rule.get("metering_rule"))

    def _account_restrictions(self, account_id: str) -> List[Dict[str, Any]]:
        restrictions: List[Dict[str, Any]] = []
        records = self.repository.list_review_records(asset_type="governance_case")
        now = datetime.now(timezone.utc)
        for record in records:
            notes = parse_governance_notes(record.get("notes"))
            restriction = dict(notes.get("restriction") or {})
            if not restriction:
                continue
            record_account_id = notes.get("account_id") or (notes.get("target_id") if notes.get("target_type") == "account" else None)
            if record_account_id != account_id:
                continue
            status = str(restriction.get("status") or "active")
            expires_at = self._parse_expires_at(restriction.get("expires_at"))
            if status == "active" and expires_at and expires_at <= now:
                status = "expired"
            restrictions.append(
                {
                    "restriction_id": restriction.get("restriction_id"),
                    "restriction_type": restriction.get("restriction_type"),
                    "scope": restriction.get("scope") or "account",
                    "status": status,
                    "reason": restriction.get("reason"),
                    "expires_at": restriction.get("expires_at"),
                    "case_id": record.get("asset_id"),
                }
            )
        return restrictions

    def _active_restriction_for_scope(self, account_id: str, *, scope: str) -> Optional[Dict[str, Any]]:
        scopes = {scope, "account"}
        return next(
            (
                item
                for item in self._account_restrictions(account_id)
                if item.get("status") == "active" and item.get("scope") in scopes
            ),
            None,
        )

    def _authored_world_version_ids(self, account_id: str, *, limit: int = 50) -> List[str]:
        authored: List[str] = []
        for item in self.repository.list_world_versions():
            try:
                version = self.repository.get_world_version(item["world_version_id"])
            except KeyError:
                continue
            if version.author_id != account_id:
                continue
            authored.append(version.world_version_id)
            if len(authored) >= limit:
                break
        return authored

    def _audit_category_for_event(self, event_name: str) -> str:
        if event_name in {"checkout_started", "subscription_activated", "subscription_state_changed", "subscription_canceled"}:
            return "subscription"
        if event_name in {"entitlement_granted", "entitlement_revoked", "story_credits_consumed", "studio_credits_consumed", "credits_consumed"}:
            return "entitlement"
        if event_name.startswith("governance_case_"):
            return "ops"
        if event_name.startswith("governance_restriction_"):
            return "ops"
        if event_name.startswith("author_draft_"):
            return "author"
        if event_name in {"session_created", "payment_required", "continue_story", "chapter_rendered", "chapter_evaluated"}:
            return "reader"
        if event_name in {"publish_blocked", "rollback_performed"}:
            return "ops"
        return "activity"

    def _audit_surface_for_event(self, event_name: str) -> str:
        if event_name.startswith("author_draft_"):
            return "author"
        if event_name.startswith("governance_case_"):
            return "ops"
        if event_name.startswith("governance_restriction_"):
            return "ops"
        if event_name in {"session_created", "payment_required", "continue_story", "chapter_rendered", "chapter_evaluated", "story_credits_consumed", "credits_consumed"}:
            return "reader"
        if event_name in {"checkout_started", "subscription_activated", "subscription_state_changed", "subscription_canceled", "entitlement_granted", "entitlement_revoked", "studio_credits_consumed"}:
            return "ops"
        return "system"

    def _audit_surface_for_meter(self, meter: Dict[str, Any]) -> str:
        action_type = str(meter.get("action_type") or "")
        if action_type.startswith("author_") or meter.get("wallet_type") == "studio_credits":
            return "author"
        return "reader"

    def _normalize_audit_event(self, event: Dict[str, Any], *, account_id: str) -> Dict[str, Any]:
        payload = dict(event.get("payload_json") or {})
        event_name = str(event.get("event_name") or "unknown_event")
        object_type = "account"
        object_id = account_id
        if payload.get("subscription_id"):
            object_type = "subscription"
            object_id = payload.get("subscription_id")
        elif payload.get("entitlement_id"):
            object_type = "entitlement"
            object_id = payload.get("entitlement_id")
        elif event.get("session_id"):
            object_type = "session"
            object_id = event.get("session_id")
        elif event.get("world_version_id"):
            object_type = "world_version"
            object_id = event.get("world_version_id")
        return {
            "trail_id": "event_%s" % event.get("event_id"),
            "source_type": "analytics_event",
            "category": self._audit_category_for_event(event_name),
            "surface": self._audit_surface_for_event(event_name),
            "action": event_name,
            "occurred_at": event.get("occurred_at"),
            "actor_id": payload.get("reviewer_id") or payload.get("account_id") or event.get("reader_id"),
            "target_account_id": account_id,
            "object_type": object_type,
            "object_id": object_id,
            "status": payload.get("status"),
            "reason": payload.get("reason"),
            "wallet_type": payload.get("wallet_type"),
            "tier_id": payload.get("tier_id") or payload.get("access_tier"),
            "balance": payload.get("balance"),
            "usage_units": None,
            "session_id": event.get("session_id"),
            "reader_id": event.get("reader_id"),
            "world_id": payload.get("world_id"),
            "world_version_id": event.get("world_version_id") or payload.get("world_version_id"),
            "headline": event_name.replace("_", " "),
            "details": payload,
        }

    def _normalize_audit_meter(self, meter: Dict[str, Any], *, account_id: str) -> Dict[str, Any]:
        return {
            "trail_id": str(meter.get("meter_id")),
            "source_type": "usage_meter",
            "category": "meter",
            "surface": self._audit_surface_for_meter(meter),
            "action": meter.get("action_type"),
            "occurred_at": meter.get("created_at"),
            "actor_id": meter.get("account_id") or meter.get("reader_id"),
            "target_account_id": account_id,
            "object_type": "usage_meter",
            "object_id": meter.get("meter_id"),
            "status": "recorded",
            "reason": meter.get("model_policy_version"),
            "wallet_type": meter.get("wallet_type"),
            "tier_id": meter.get("subscription_tier"),
            "balance": None,
            "usage_units": float(meter.get("usage_units") or 0.0),
            "session_id": meter.get("session_id"),
            "reader_id": meter.get("reader_id"),
            "world_id": None,
            "world_version_id": meter.get("world_version_id"),
            "headline": "%s meter" % (meter.get("action_type") or "usage"),
            "details": {
                "estimated_cost": meter.get("estimated_cost"),
                "provider": meter.get("provider"),
                "chapter_id": meter.get("chapter_id"),
                "model_policy_version": meter.get("model_policy_version"),
            },
        }

    def full_audit_trail(self, *, account_id: str, limit: int = 50) -> Dict[str, Any]:
        authored_world_version_ids = self._authored_world_version_ids(account_id, limit=max(limit, 10))
        analytics_events = self.repository.list_analytics_events(reader_id=account_id, limit=max(limit * 4, 20))
        if authored_world_version_ids:
            authored_events = self.repository.list_analytics_events(
                world_version_ids=authored_world_version_ids,
                limit=max(limit * 4, 20),
            )
            deduped = {str(item.get("event_id")): item for item in analytics_events}
            for item in authored_events:
                deduped.setdefault(str(item.get("event_id")), item)
            analytics_events = list(deduped.values())
        meters = self.repository.list_usage_meters(account_id=account_id)[: max(limit * 2, 20)]
        trail = [
            *[self._normalize_audit_event(item, account_id=account_id) for item in analytics_events],
            *[self._normalize_audit_meter(item, account_id=account_id) for item in meters],
        ]
        trail.sort(key=lambda item: (str(item.get("occurred_at") or ""), str(item.get("trail_id") or "")), reverse=True)
        has_more = len(trail) > limit
        trail = trail[:limit]

        by_category: Dict[str, int] = {}
        by_surface: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_source_type: Dict[str, int] = {}
        actions: Dict[str, Dict[str, Any]] = {}
        for item in trail:
            category = str(item.get("category") or "unknown")
            surface = str(item.get("surface") or "unknown")
            status = str(item.get("status") or "unknown")
            source_type = str(item.get("source_type") or "unknown")
            action = str(item.get("action") or "unknown")
            by_category[category] = by_category.get(category, 0) + 1
            by_surface[surface] = by_surface.get(surface, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            by_source_type[source_type] = by_source_type.get(source_type, 0) + 1
            entry = actions.setdefault(action, {"action": action, "count": 0, "latest_at": None})
            entry["count"] += 1
            latest_at = str(item.get("occurred_at") or "")
            if not entry["latest_at"] or latest_at > str(entry["latest_at"]):
                entry["latest_at"] = item.get("occurred_at")

        return {
            "audit_trail": trail,
            "audit_breakdown": {
                "total_entries": len(trail),
                "latest_at": trail[0]["occurred_at"] if trail else None,
                "by_category": by_category,
                "by_surface": by_surface,
                "by_status": by_status,
                "by_source_type": by_source_type,
                "top_actions": sorted(actions.values(), key=lambda item: (-item["count"], item["action"]))[:8],
                "sources": {
                    "analytics_events": len(analytics_events),
                    "usage_meters": len(meters),
                    "authored_world_versions": len(authored_world_version_ids),
                },
            },
            "timeline_cursor": {
                "limit": limit,
                "returned": len(trail),
                "has_more": has_more,
            },
        }

    def wallet_balance(self, *, account_id: str, wallet_type: str) -> float:
        wallet = self._wallets_for_account(account_id).get(wallet_type, {})
        return float(wallet.get("balance") or 0.0)

    def meter_action(
        self,
        *,
        surface: str,
        action_name: str,
        account_id: str,
        reader_id: Optional[str] = None,
        session_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        access: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
        subscription_tier: Optional[str] = None,
        charged_units: Optional[float] = None,
        estimated_cost: float = 0.0,
    ) -> Dict[str, Any]:
        rule = self.monetization.entitlement_rule(surface, action_name)
        metering_rule = rule.get("metering_rule")
        return self.meter(
            {
                "account_id": account_id,
                "reader_id": reader_id,
                "session_id": session_id,
                "chapter_id": chapter_id,
                "world_version_id": world_version_id,
                "action_type": rule.get("meter_action_type", action_name),
                "usage_units": self._metering_rule_units(metering_rule) if charged_units is None else float(charged_units),
                "estimated_cost": float(estimated_cost),
                "wallet_type": access.get("wallet_type") if access else rule.get("wallet_type"),
                "subscription_tier": subscription_tier or (access.get("tier_id") if access else None),
                "provider": provider or (access.get("provider") if access else None),
                "model_policy_version": "%s:%s" % (
                    self.monetization.config_version(),
                    metering_rule or action_name,
                ),
            }
        )

    def quote_continue(self, session_id: str, action: str = "continue") -> Dict[str, Any]:
        session_record = self.repository.get_session(session_id)
        world_version_id = str(session_record.metadata.get("world_version_id"))
        world_version = self.repository.get_world_version(world_version_id)
        policy = dict((world_version.manifest_json or {}).get("monetization_policy", {}))
        trial_chapters = int(policy.get("trial_chapters", 1))
        paid_after = int(policy.get("paid_after", max(2, trial_chapters + 1)))
        chapter_index = session_record.current_state.chapter_index
        if chapter_index < trial_chapters:
            return {"required": False, "access_tier": "free", "quote": 0.0, "reason": "trial_chapter", "tier_id": None}
        if chapter_index + 1 < paid_after:
            return {"required": False, "access_tier": "free", "quote": 0.0, "reason": "grace_window", "tier_id": None}
        rule = self.monetization.entitlement_rule("reader", "continue_story")
        quote_tier = self.monetization.get_tier(rule.get("quote_tier_id", "play_pass"))
        return {
            "required": True,
            "access_tier": "paid",
            "quote": float(quote_tier["price_usd_monthly"]),
            "reason": "%s_requires_entitlement" % action,
            "tier_id": rule.get("required_tier", "play_pass"),
            "wallet_type": rule.get("wallet_type"),
            "metering_rule": rule.get("metering_rule"),
            "required_capability": rule.get("subscription_capability"),
            "config_version": self.monetization.config_version(),
            "required_units": self._required_units_for_rule(rule),
        }

    def list_entitlements_for_account(self, account_id: str, *, world_id: Optional[str] = None) -> Dict[str, Any]:
        raw_entitlements = [
            self._normalize_entitlement(item, world_id=world_id)
            for item in self.repository.list_entitlements(account_id=account_id, world_id=world_id)
        ]
        subscriptions = self.monetization.list_subscriptions(account_id=account_id)
        subscription = next((item for item in subscriptions if item["status"] in {"trialing", "active"}), None) or (subscriptions[0] if subscriptions else None)
        return {
            "account_id": account_id,
            "reader_id": account_id,
            "world_id": world_id,
            "subscription": self._subscription_snapshot(subscription) if subscription else None,
            "wallets": self._wallets_for_account(account_id),
            **self._checkout_session_summary(account_id),
            "lifecycle_history_summary": self._lifecycle_history_summary(account_id),
            "entitlements": raw_entitlements,
            **self._config_snapshot(),
        }

    def entitlement_audit(self, *, account_id: str, world_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        snapshot = self.list_entitlements_for_account(account_id, world_id=world_id)
        entitlements = list(snapshot.get("entitlements", []))
        status_counts: Dict[str, int] = {}
        entitlement_type_counts: Dict[str, int] = {}
        for item in entitlements:
            status = str(item.get("status", "unknown"))
            entitlement_type = str(item.get("entitlement_type", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
            entitlement_type_counts[entitlement_type] = entitlement_type_counts.get(entitlement_type, 0) + 1
        events = self.repository.list_analytics_events(
            reader_id=account_id,
            event_names=[
                "checkout_started",
                "subscription_activated",
                "subscription_state_changed",
                "subscription_canceled",
                "entitlement_granted",
                "entitlement_revoked",
                "story_credits_consumed",
                "studio_credits_consumed",
            ],
            limit=limit,
        )
        audit_timeline = [
            {
                "event_id": item.get("event_id"),
                "event_name": item.get("event_name"),
                "occurred_at": item.get("occurred_at"),
                "entitlement_id": item.get("payload_json", {}).get("entitlement_id"),
                "subscription_id": item.get("payload_json", {}).get("subscription_id"),
                "wallet_type": item.get("payload_json", {}).get("wallet_type"),
                "tier_id": item.get("payload_json", {}).get("tier_id"),
                "status": item.get("payload_json", {}).get("status"),
                "reason": item.get("payload_json", {}).get("reason"),
                "balance": item.get("payload_json", {}).get("balance"),
            }
            for item in events
        ]
        snapshot["audit_summary"] = {
            "entitlement_count": len(entitlements),
            "status_counts": status_counts,
            "entitlement_type_counts": entitlement_type_counts,
            "active_wallets": {
                wallet_type: {
                    "balance": float(value.get("balance") or 0.0),
                    "status": value.get("status"),
                }
                for wallet_type, value in dict(snapshot.get("wallets", {})).items()
            },
            "latest_event_at": audit_timeline[0]["occurred_at"] if audit_timeline else None,
        }
        snapshot["audit_timeline"] = audit_timeline
        snapshot["revoke_candidates"] = [
            {
                "entitlement_id": item.get("entitlement_id"),
                "entitlement_type": item.get("entitlement_type"),
                "wallet_type": item.get("wallet_type"),
                "tier_id": item.get("tier_id"),
                "status": item.get("status"),
                "reason": item.get("reason"),
            }
            for item in entitlements
            if item.get("status") not in {"revoked", "expired"}
        ]
        snapshot.update(self.full_audit_trail(account_id=account_id, limit=limit))
        return snapshot

    def list_entitlements_for_reader(self, reader_id: str, *, world_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = self.resolve_account_id(reader_id=reader_id)
        return self.list_entitlements_for_account(account_id, world_id=world_id)

    def list_subscriptions(self, *, account_id: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        subscriptions = [self._subscription_snapshot(item) for item in self.monetization.list_subscriptions(account_id=account_id, status=status)]
        return {
            "subscriptions": [
                {
                    **item,
                    **self._checkout_session_summary(item["account_id"]),
                    "lifecycle_history_summary": self._lifecycle_history_summary(item["account_id"]),
                    "retryable": item.get("status") == "past_due",
                    "recommended_action": self._recommended_subscription_action(item),
                }
                for item in subscriptions
            ]
        }

    def subscription_status(self, *, account_id: str) -> Dict[str, Any]:
        subscriptions = self.monetization.list_subscriptions(account_id=account_id)
        active = next((item for item in subscriptions if item["status"] in {"trialing", "active"}), None) or (subscriptions[0] if subscriptions else None)
        return {
            "account_id": account_id,
            "subscription": self._subscription_snapshot(active) if active else None,
            "wallets": self._wallets_for_account(account_id),
            **self._checkout_session_summary(account_id),
            "lifecycle_history_summary": self._lifecycle_history_summary(account_id),
            "retryable": bool(active and active.get("status") == "past_due"),
            "renewable": bool(active and active.get("status") in {"past_due", "canceled", "expired"}) if active else False,
            "recommended_action": self._recommended_subscription_action(active),
            **self._config_snapshot(),
        }

    def start_checkout(self, *, account_id: str, tier_id: str, provider: str = "web_stub") -> Dict[str, Any]:
        restriction = self._active_restriction_for_scope(account_id, scope="checkout")
        if restriction:
            raise ValueError("checkout_restricted")
        checkout = self.monetization.start_checkout(account_id=account_id, tier_id=tier_id, provider=provider)
        expires_at = (self._utcnow() + timedelta(minutes=self._checkout_session_ttl_minutes())).isoformat()
        checkout_session = self.repository.save_billing_checkout_session(
            {
                "checkout_session_id": checkout["session_id"],
                "account_id": account_id,
                "tier_id": tier_id,
                "provider": provider,
                "provider_ref": checkout["session_id"],
                "status": "created",
                "checkout_url": checkout.get("checkout_url"),
                "idempotency_key": f"{provider}:{account_id}:{tier_id}:{checkout['session_id']}",
                "expires_at": expires_at,
            }
        )
        self._record_lifecycle_event(
            {
                "event_type": "checkout_session_created",
                "provider": provider,
                "provider_event_id": f"{provider}:{checkout['session_id']}:created",
                "account_id": account_id,
                "checkout_session_id": checkout_session["checkout_session_id"],
                "status": "processed",
                "payload_json": checkout_session,
                "processing_result": {"checkout_session_status": checkout_session["status"]},
                "occurred_at": self._utcnow().isoformat(),
                "processed_at": self._utcnow().isoformat(),
            }
        )
        return {
            **checkout_session,
            "session_id": checkout_session["checkout_session_id"],
        }

    def _process_lifecycle_event(self, event: Dict[str, Any], *, replay: bool = False) -> Dict[str, Any]:
        existing = self.repository.get_billing_lifecycle_event_by_provider_ref(
            provider=event["provider"],
            provider_event_id=event["provider_event_id"],
            default=None,
        )
        if existing and existing.get("status") == "processed" and not replay:
            return existing

        event_record = self._record_lifecycle_event(
            {
                **(existing or {}),
                **event,
                "status": existing.get("status") if existing and existing.get("status") == "processed" and replay else "processing",
            }
        )

        event_type = str(event_record.get("event_type") or "")
        account_id = event_record.get("account_id")
        checkout_session_id = event_record.get("checkout_session_id")
        subscription = self._find_subscription_for_event(
            account_id=account_id,
            subscription_id=event_record.get("subscription_id"),
        )
        processing_result: Dict[str, Any] = {"applied": False}

        if event_type == "checkout_session_created":
            processing_result = {
                "applied": False,
                "checkout_session_status": "created",
            }
        elif event_type == "checkout_session_completed":
            checkout_session = self.repository.get_billing_checkout_session(str(checkout_session_id))
            if checkout_session.get("subscription_id"):
                subscription = self.repository.get_subscription(checkout_session["subscription_id"])
            elif existing and existing.get("processing_result", {}).get("subscription_id"):
                subscription = self.repository.get_subscription(existing["processing_result"]["subscription_id"])
            else:
                subscription = self.monetization.create_subscription(
                    account_id=checkout_session["account_id"],
                    tier_id=checkout_session["tier_id"],
                    provider=checkout_session["provider"],
                    provider_ref=checkout_session["provider_ref"],
                    status="active",
                )
            checkout_session = self.repository.save_billing_checkout_session(
                {
                    **checkout_session,
                    "subscription_id": subscription["subscription_id"],
                    "status": "completed",
                }
            )
            processing_result = {
                "applied": True,
                "subscription_id": subscription["subscription_id"],
                "checkout_session_status": checkout_session["status"],
            }
        elif event_type == "checkout_session_expired":
            checkout_session = self.repository.get_billing_checkout_session(str(checkout_session_id))
            checkout_session = self.repository.save_billing_checkout_session(
                {
                    **checkout_session,
                    "status": "expired",
                }
            )
            processing_result = {
                "applied": True,
                "checkout_session_status": checkout_session["status"],
            }
        elif event_type in {"subscription_payment_failed", "subscription_past_due"}:
            if subscription is None:
                raise KeyError("subscription_required_for_payment_failure")
            updated = self.monetization.change_subscription_state(subscription["subscription_id"], status="past_due")
            wallet_snapshot = self._deactivate_subscription_wallets(
                account_id=updated["account_id"],
                expires_at=self._utcnow().isoformat(),
            )
            processing_result = {
                "applied": True,
                "subscription_id": updated["subscription_id"],
                "subscription_status": updated["status"],
                "wallet_snapshot": wallet_snapshot,
            }
        elif event_type == "subscription_canceled":
            if subscription is None:
                raise KeyError("subscription_required_for_cancel")
            updated = self.monetization.change_subscription_state(
                subscription["subscription_id"],
                status="canceled",
                cancel_at_period_end=True,
            )
            wallet_snapshot = self._deactivate_subscription_wallets(
                account_id=updated["account_id"],
                expires_at=updated.get("period_end"),
            )
            processing_result = {
                "applied": True,
                "subscription_id": updated["subscription_id"],
                "subscription_status": updated["status"],
                "wallet_snapshot": wallet_snapshot,
            }
        elif event_type == "subscription_payment_succeeded":
            if subscription is None:
                raise KeyError("subscription_required_for_payment_success")
            updated = self.monetization.change_subscription_state(
                subscription["subscription_id"],
                status="active",
                cancel_at_period_end=False,
            )
            processing_result = {
                "applied": True,
                "subscription_id": updated["subscription_id"],
                "subscription_status": updated["status"],
            }
        elif event_type in {"subscription_renewed", "subscription_reactivated"}:
            if subscription is None:
                raise KeyError("subscription_required_for_renewal")
            updated = self.monetization.renew_subscription(
                subscription["subscription_id"],
                status="active",
                cancel_at_period_end=False,
            )
            processing_result = {
                "applied": True,
                "subscription_id": updated["subscription_id"],
                "subscription_status": updated["status"],
                "period_end": updated.get("period_end"),
            }
        elif event_type == "subscription_renewal_due":
            if subscription is None:
                raise KeyError("subscription_required_for_renewal_due")
            processing_result = {
                "applied": False,
                "subscription_id": subscription["subscription_id"],
                "subscription_status": subscription["status"],
            }
        else:
            raise ValueError("unsupported_billing_event_type")

        return self.repository.save_billing_lifecycle_event(
            {
                **event_record,
                "status": "processed",
                "processing_result": processing_result,
                "processed_at": self._utcnow().isoformat(),
            }
        )

    def ingest_checkout_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(payload.get("provider") or self._billing_provider())
        event = {
            "event_type": payload["event_type"],
            "provider": provider,
            "provider_event_id": payload["provider_event_id"],
            "account_id": payload.get("account_id"),
            "subscription_id": payload.get("subscription_id"),
            "checkout_session_id": payload.get("checkout_session_id"),
            "payload_json": dict(payload.get("payload") or {}),
            "occurred_at": payload.get("occurred_at") or self._utcnow().isoformat(),
        }
        processed = self._process_lifecycle_event(event)
        return {"event": processed}

    def retry_subscription_payment(self, *, account_id: Optional[str] = None, subscription_id: Optional[str] = None) -> Dict[str, Any]:
        subscription = self._find_subscription_for_event(account_id=account_id, subscription_id=subscription_id)
        if subscription is None:
            raise KeyError("subscription_required_for_retry")
        latest_attempt = self.repository.latest_billing_retry_attempt(subscription_id=subscription["subscription_id"])
        attempt_count = int(latest_attempt.get("attempt_count") or 0) + 1 if latest_attempt else 1
        retry = self.repository.save_billing_retry_attempt(
            {
                "account_id": subscription["account_id"],
                "subscription_id": subscription["subscription_id"],
                "status": "processing",
                "retry_reason": "retry_payment",
                "attempt_count": attempt_count,
                "next_retry_at": (self._utcnow() + timedelta(minutes=self._retry_backoff_minutes())).isoformat(),
                "payload_json": {"source": "manual_retry"},
            }
        )
        processed = self._process_lifecycle_event(
            {
                "event_type": "subscription_payment_succeeded",
                "provider": subscription.get("provider") or self._billing_provider(),
                "provider_event_id": f"retry:{subscription['subscription_id']}:{attempt_count}",
                "account_id": subscription["account_id"],
                "subscription_id": subscription["subscription_id"],
                "payload_json": {"retry_attempt_id": retry["retry_attempt_id"]},
                "occurred_at": self._utcnow().isoformat(),
            }
        )
        retry = self.repository.save_billing_retry_attempt(
            {
                **retry,
                "status": "succeeded",
                "payload_json": {"event_id": processed["event_id"]},
            }
        )
        return {"retry_attempt": retry, "event": processed}

    def renew_subscription(self, *, account_id: str) -> Dict[str, Any]:
        subscription = self._find_subscription_for_event(account_id=account_id, subscription_id=None)
        if subscription is None:
            raise KeyError("subscription_required_for_renew")
        event_type = "subscription_reactivated" if subscription.get("status") == "past_due" else "subscription_renewed"
        processed = self._process_lifecycle_event(
            {
                "event_type": event_type,
                "provider": subscription.get("provider") or self._billing_provider(),
                "provider_event_id": f"renew:{subscription['subscription_id']}:{int(self._utcnow().timestamp())}",
                "account_id": subscription["account_id"],
                "subscription_id": subscription["subscription_id"],
                "payload_json": {"source": "manual_renew"},
                "occurred_at": self._utcnow().isoformat(),
            }
        )
        return {"event": processed}

    def cancel_subscription(self, *, account_id: str) -> Dict[str, Any]:
        subscription = self._find_subscription_for_event(account_id=account_id, subscription_id=None)
        if subscription is None:
            raise KeyError("subscription_required_for_cancel")
        processed = self._process_lifecycle_event(
            {
                "event_type": "subscription_canceled",
                "provider": subscription.get("provider") or self._billing_provider(),
                "provider_event_id": f"cancel:{subscription['subscription_id']}:{int(self._utcnow().timestamp())}",
                "account_id": subscription["account_id"],
                "subscription_id": subscription["subscription_id"],
                "payload_json": {"source": "manual_cancel", "cancel_at_period_end": True},
                "occurred_at": self._utcnow().isoformat(),
            }
        )
        return {"event": processed}

    def reconcile_subscription(self, subscription_id: str) -> Dict[str, Any]:
        reconciled = self.monetization.reconcile_subscription_lifecycle(subscription_id)
        if reconciled.get("status") in {"past_due", "canceled", "expired"}:
            wallet_snapshot = self._deactivate_subscription_wallets(
                account_id=reconciled["account_id"],
                expires_at=reconciled.get("period_end") if reconciled.get("status") == "canceled" else self._utcnow().isoformat(),
            )
        else:
            wallet_snapshot = {
                "story_wallet": self._wallets_for_account(reconciled["account_id"]).get("story_credits"),
                "studio_wallet": self._wallets_for_account(reconciled["account_id"]).get("studio_credits"),
            }
        event = self._record_lifecycle_event(
            {
                "event_type": "subscription_reconcile",
                "provider": reconciled.get("provider") or self._billing_provider(),
                "provider_event_id": f"reconcile:{subscription_id}:{int(self._utcnow().timestamp())}",
                "account_id": reconciled["account_id"],
                "subscription_id": subscription_id,
                "status": "processed",
                "payload_json": {"source": "manual_reconcile"},
                "processing_result": {
                    "subscription_status": reconciled["status"],
                    "wallet_snapshot": wallet_snapshot,
                },
                "occurred_at": self._utcnow().isoformat(),
                "processed_at": self._utcnow().isoformat(),
            }
        )
        return {"subscription": self._subscription_snapshot(reconciled), "event": event}

    def replay_lifecycle_event(self, event_id: str) -> Dict[str, Any]:
        event = self.repository.get_billing_lifecycle_event(event_id)
        replayed = self._process_lifecycle_event(
            {
                "event_type": event["event_type"],
                "provider": event["provider"],
                "provider_event_id": event["provider_event_id"],
                "account_id": event.get("account_id"),
                "subscription_id": event.get("subscription_id"),
                "checkout_session_id": event.get("checkout_session_id"),
                "payload_json": dict(event.get("payload_json") or {}),
                "occurred_at": event.get("occurred_at"),
                "event_id": event["event_id"],
            },
            replay=True,
        )
        return {"event": replayed}

    def grant_subscription(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        account_id = self.resolve_account_id(
            account_id=payload.get("account_id"),
            reader_id=payload.get("reader_id"),
        )
        tier_id = payload.get("tier_id") or ("play_pass" if payload.get("entitlement_type") == "subscriber" else None)
        if not account_id or not tier_id:
            raise ValueError("account_id_and_tier_id_required")
        subscription = self.monetization.create_subscription(
            account_id=account_id,
            tier_id=tier_id,
            provider=payload.get("provider", "web_stub"),
            provider_ref=payload.get("provider_ref"),
            status=payload.get("status", "active"),
            period_start=payload.get("period_start"),
            period_end=payload.get("period_end"),
            cancel_at_period_end=bool(payload.get("cancel_at_period_end")),
        )
        return self._subscription_snapshot(subscription)

    def change_subscription_state(self, subscription_id: str, *, status: str, cancel_at_period_end: Optional[bool] = None) -> Dict[str, Any]:
        updated = self.monetization.change_subscription_state(
            subscription_id,
            status=status,
            cancel_at_period_end=cancel_at_period_end,
        )
        return self._subscription_snapshot(updated)

    def grant_entitlement(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        entitlement_type = payload["entitlement_type"]
        if entitlement_type in {"subscriber", "play_pass", "creator_pass", "studio_pass"}:
            tier_id = payload.get("tier_id") or ("play_pass" if entitlement_type == "subscriber" else entitlement_type)
            subscription = self.grant_subscription(
                {
                    "account_id": payload.get("account_id"),
                    "reader_id": payload.get("reader_id"),
                    "tier_id": tier_id,
                    "provider": payload.get("provider", "ops_manual"),
                    "status": payload.get("status", "active"),
                    "period_start": payload.get("period_start"),
                    "period_end": payload.get("period_end"),
                }
            )
            return {
                "account_id": subscription["account_id"],
                "reader_id": subscription["account_id"],
                "entitlement_type": "subscriber",
                "tier_id": subscription["tier_id"],
                "status": subscription["status"],
                "reason": "subscriber_active",
            }

        wallet_type = payload.get("wallet_type") or ("story_credits" if entitlement_type == "credits" else None)
        if entitlement_type == "credits" and payload.get("balance") is None:
            raise ValueError("credits_balance_required")
        account_id = self.resolve_account_id(
            account_id=payload.get("account_id"),
            reader_id=payload.get("reader_id"),
        )
        record = self.repository.save_entitlement(
            {
                **payload,
                "account_id": account_id,
                "reader_id": payload.get("reader_id") or account_id,
                "wallet_type": wallet_type,
                "tier_id": payload.get("tier_id"),
            }
        )
        return self._normalize_entitlement(record, world_id=payload.get("world_id"))

    def grant_wallet_credits(self, *, account_id: str, wallet_type: str, amount: float, tier_id: Optional[str] = None, expires_at: Optional[str] = None) -> Dict[str, Any]:
        wallet = self._wallets_for_account(account_id).get(wallet_type, {})
        balance = float(wallet.get("balance") or 0.0) + float(amount)
        return self.grant_entitlement(
            {
                "account_id": account_id,
                "reader_id": account_id,
                "entitlement_id": wallet.get("entitlement_id") or "wallet_%s_%s" % (wallet_type, account_id),
                "entitlement_type": "credits",
                "wallet_type": wallet_type,
                "tier_id": tier_id or wallet.get("tier_id"),
                "balance": balance,
                "expires_at": expires_at or wallet.get("expires_at"),
                "status": "active",
            }
        )

    def debit_wallet_credits(self, *, account_id: str, wallet_type: str, amount: float) -> Dict[str, Any]:
        wallet = self._wallets_for_account(account_id).get(wallet_type, {})
        new_balance = max(0.0, float(wallet.get("balance") or 0.0) - float(amount))
        return self.grant_entitlement(
            {
                "account_id": account_id,
                "reader_id": account_id,
                "entitlement_id": wallet.get("entitlement_id") or "wallet_%s_%s" % (wallet_type, account_id),
                "entitlement_type": "credits",
                "wallet_type": wallet_type,
                "tier_id": wallet.get("tier_id"),
                "balance": new_balance,
                "expires_at": wallet.get("expires_at"),
                "status": "active" if new_balance >= 1.0 else "exhausted",
            }
        )

    def access_check_reader(
        self,
        session_id: str,
        *,
        account_id: Optional[str] = None,
        reader_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        quote = self.quote_continue(session_id)
        rule = self.monetization.entitlement_rule("reader", "continue_story")
        if not quote["required"]:
            required_tier = self._required_tier_snapshot(rule.get("required_tier"))
            return self._access_snapshot(
                required=False,
                access_tier=quote["access_tier"],
                quote=quote["quote"],
                reason=quote["reason"],
                entitlement_type="trial",
                balance=None,
                status="active",
                account_id=self.resolve_account_id(account_id=account_id, reader_id=reader_id),
                metering_rule=rule.get("metering_rule"),
                tier_id=required_tier["required_tier"],
            )

        resolved_account_id = self.resolve_account_id(account_id=account_id, reader_id=reader_id)
        required_tier_snapshot = self._required_tier_snapshot(rule.get("required_tier", quote.get("tier_id", "play_pass")))
        if not resolved_account_id:
            required_tier = required_tier_snapshot["required_tier"] or "play_pass"
            checkout = self.start_checkout(account_id="guest", tier_id=required_tier)
            snapshot = self._access_snapshot(
                required=True,
                access_tier=quote["access_tier"],
                quote=quote["quote"],
                reason=quote["reason"],
                entitlement_type=None,
                balance=None,
                status="missing_reader",
                account_id=None,
                tier_id=required_tier,
                wallet_type=rule.get("wallet_type"),
                provider=checkout["provider"],
                metering_rule=rule.get("metering_rule"),
            )
            snapshot.update(required_tier_snapshot)
            snapshot["required_capability"] = rule.get("subscription_capability")
            snapshot["suggested_checkout_tier"] = required_tier
            snapshot["required_units"] = self._required_units_for_rule(rule)
            return snapshot

        session_record = self.repository.get_session(session_id)
        world_id = session_record.world_id
        restriction = self._active_restriction_for_scope(resolved_account_id, scope="reader")
        if restriction:
            snapshot = self._access_snapshot(
                required=True,
                access_tier="restricted",
                quote=0.0,
                reason="manual_restriction_active",
                entitlement_type="governance_restriction",
                balance=None,
                status="restricted",
                account_id=resolved_account_id,
                metering_rule=rule.get("metering_rule"),
            )
            snapshot["restriction"] = restriction
            snapshot["restriction_id"] = restriction.get("restriction_id")
            snapshot["required_capability"] = None
            snapshot["suggested_checkout_tier"] = None
            snapshot["required_units"] = 0.0
            return snapshot
        subscription = self.monetization.active_subscription(account_id=resolved_account_id)
        if subscription:
            tier = self.monetization.get_tier(subscription["tier_id"])
            capability_key = rule.get("subscription_capability")
            if tier.get("reader_access") and (not capability_key or tier.get("capabilities", {}).get(capability_key, False)):
                return self._access_snapshot(
                    required=False,
                    access_tier=subscription["tier_id"],
                    quote=0.0,
                    reason="subscription_active",
                    entitlement_type="subscriber",
                    balance=None,
                    status=subscription["status"],
                    account_id=resolved_account_id,
                    tier_id=subscription["tier_id"],
                    provider=subscription["provider"],
                    entitlement_id=subscription["subscription_id"],
                    metering_rule=rule.get("metering_rule"),
                )

        entitlements = self.list_entitlements_for_account(resolved_account_id, world_id=world_id)["entitlements"]
        world_pass = next((item for item in entitlements if item["status"] == "active" and item["entitlement_type"] == "world_pass"), None)
        if world_pass:
            return self._access_snapshot(
                required=False,
                access_tier="paid",
                quote=0.0,
                reason=world_pass["reason"],
                entitlement_type="world_pass",
                balance=None,
                status=world_pass["status"],
                account_id=resolved_account_id,
                entitlement_id=world_pass.get("entitlement_id"),
                metering_rule=rule.get("metering_rule"),
            )

        wallet_type = rule.get("wallet_type", "story_credits")
        story_wallet = self._wallets_for_account(resolved_account_id)[wallet_type]
        required_units = self._required_units_for_rule(rule)
        if story_wallet["status"] == "active" and float(story_wallet.get("balance") or 0.0) >= required_units:
            return self._access_snapshot(
                required=False,
                access_tier="paid",
                quote=0.0,
                reason=story_wallet["reason"],
                entitlement_type="credits",
                balance=story_wallet.get("balance"),
                status=story_wallet["status"],
                account_id=resolved_account_id,
                wallet_type=wallet_type,
                entitlement_id=story_wallet.get("entitlement_id"),
                metering_rule=rule.get("metering_rule"),
            )

        required_tier = required_tier_snapshot["required_tier"] or "play_pass"
        checkout = self.start_checkout(account_id=resolved_account_id, tier_id=required_tier)
        snapshot = self._access_snapshot(
            required=True,
            access_tier=quote["access_tier"],
            quote=quote["quote"],
            reason=story_wallet["reason"] if story_wallet else quote["reason"],
            entitlement_type="credits",
            balance=story_wallet.get("balance"),
            status=story_wallet.get("status"),
            account_id=resolved_account_id,
            tier_id=required_tier,
            wallet_type=wallet_type,
            provider=checkout["provider"],
            entitlement_id=story_wallet.get("entitlement_id"),
            metering_rule=rule.get("metering_rule"),
        )
        snapshot.update(required_tier_snapshot)
        snapshot["required_capability"] = rule.get("subscription_capability")
        snapshot["suggested_checkout_tier"] = required_tier
        snapshot["required_units"] = required_units
        return snapshot

    def access_check(self, session_id: str, *, reader_id: Optional[str] = None, account_id: Optional[str] = None) -> Dict[str, Any]:
        return self.access_check_reader(session_id, account_id=account_id, reader_id=reader_id)

    def consume_story_credits(self, session_id: str, *, account_id: str, access: Dict[str, Any]) -> Dict[str, Any]:
        if access.get("wallet_type") != "story_credits":
            return access
        updated_wallet = self.debit_wallet_credits(account_id=account_id, wallet_type="story_credits", amount=1.0)
        return self._access_snapshot(
            required=False,
            access_tier="paid",
            quote=0.0,
            reason="credits_consumed",
            entitlement_type="credits",
            balance=updated_wallet.get("balance"),
            status=updated_wallet["status"],
            account_id=account_id,
            wallet_type="story_credits",
            entitlement_id=updated_wallet.get("entitlement_id"),
            metering_rule=self.monetization.entitlement_rule("reader", "continue_story").get("metering_rule"),
        )

    def consume_entitlement(self, session_id: str, *, reader_id: Optional[str], access: Dict[str, Any], account_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_account_id = self.resolve_account_id(account_id=account_id, reader_id=reader_id)
        if access.get("wallet_type") == "story_credits" and resolved_account_id:
            return self.consume_story_credits(session_id, account_id=resolved_account_id, access=access)
        return access

    def access_check_author(
        self,
        *,
        account_id: Optional[str],
        action_name: str = "simulate",
        required_access: str = "basic",
    ) -> Dict[str, Any]:
        rule = self.monetization.entitlement_rule("author", action_name)
        required_tier = rule.get("required_tier", "creator_pass")
        wallet_type = rule.get("wallet_type", "studio_credits")
        minimum_author_access = rule.get("minimum_author_access", required_access)
        capability_key = rule.get("subscription_capability")
        required_units = self._required_units_for_rule(rule)
        resolved_account_id = self.resolve_account_id(account_id=account_id)
        if not resolved_account_id:
            snapshot = {
                "allowed": False,
                "wallet_type": wallet_type,
                "balance": 0.0,
                "reason": "missing_account",
                "account_id": None,
            }
            snapshot.update(self._required_tier_snapshot(required_tier))
            snapshot["required_capability"] = capability_key
            snapshot["minimum_author_access"] = minimum_author_access
            snapshot["config_version"] = self.monetization.config_version()
            snapshot["suggested_checkout_tier"] = required_tier
            snapshot["required_units"] = required_units
            return snapshot
        restriction = self._active_restriction_for_scope(resolved_account_id, scope="author")
        if restriction:
            snapshot = {
                "allowed": False,
                "wallet_type": wallet_type,
                "balance": self._wallets_for_account(resolved_account_id)[wallet_type].get("balance", 0.0) if wallet_type else None,
                "reason": "manual_restriction_active",
                "account_id": resolved_account_id,
                "restriction": restriction,
                "restriction_id": restriction.get("restriction_id"),
            }
            snapshot.update(self._required_tier_snapshot(required_tier))
            snapshot["required_capability"] = capability_key
            snapshot["minimum_author_access"] = minimum_author_access
            snapshot["config_version"] = self.monetization.config_version()
            snapshot["subscription_status"] = None
            snapshot["suggested_checkout_tier"] = None
            snapshot["required_units"] = 0.0
            return snapshot
        subscription = self.monetization.active_subscription(account_id=resolved_account_id)
        if not subscription:
            snapshot = {
                "allowed": False,
                "wallet_type": wallet_type,
                "balance": self._wallets_for_account(resolved_account_id)[wallet_type].get("balance", 0.0) if wallet_type else None,
                "reason": "subscription_required",
                "account_id": resolved_account_id,
            }
            snapshot.update(self._required_tier_snapshot(required_tier))
            snapshot["required_capability"] = capability_key
            snapshot["minimum_author_access"] = minimum_author_access
            snapshot["config_version"] = self.monetization.config_version()
            snapshot["suggested_checkout_tier"] = required_tier
            snapshot["required_units"] = required_units
            return snapshot
        tier = self.monetization.get_tier(subscription["tier_id"])
        author_access = tier.get("author_access", "none")
        author_access_allowed = self._author_access_rank(author_access) >= self._author_access_rank(minimum_author_access)
        capability_allowed = True if not capability_key else bool(tier.get("capabilities", {}).get(capability_key, False))
        if not author_access_allowed or not capability_allowed:
            snapshot = {
                "allowed": False,
                "wallet_type": wallet_type,
                "balance": self._wallets_for_account(resolved_account_id)[wallet_type].get("balance", 0.0) if wallet_type else None,
                "reason": "author_tier_required",
                "account_id": resolved_account_id,
            }
            snapshot.update(self._required_tier_snapshot(required_tier))
            snapshot["required_capability"] = capability_key
            snapshot["minimum_author_access"] = minimum_author_access
            snapshot["config_version"] = self.monetization.config_version()
            snapshot["subscription_status"] = subscription["status"]
            snapshot["suggested_checkout_tier"] = required_tier
            snapshot["required_units"] = required_units
            return snapshot
        if not wallet_type:
            snapshot = {
                "allowed": True,
                "wallet_type": None,
                "balance": None,
                "reason": "subscription_active",
                "account_id": resolved_account_id,
                "tier_id": subscription["tier_id"],
                "subscription_status": subscription["status"],
                "required_capability": capability_key,
                "minimum_author_access": minimum_author_access,
                "metering_rule": rule.get("metering_rule"),
                "config_version": self.monetization.config_version(),
            }
            snapshot.update(self._required_tier_snapshot(required_tier))
            snapshot["suggested_checkout_tier"] = required_tier
            snapshot["required_units"] = required_units
            return snapshot
        studio_wallet = self._wallets_for_account(resolved_account_id)[wallet_type]
        snapshot = {
            "allowed": studio_wallet["status"] == "active" and float(studio_wallet.get("balance") or 0.0) >= required_units,
            "wallet_type": wallet_type,
            "balance": studio_wallet.get("balance", 0.0),
            "reason": "studio_credits_balance" if studio_wallet["status"] == "active" and float(studio_wallet.get("balance") or 0.0) >= required_units else studio_wallet["reason"],
            "account_id": resolved_account_id,
            "tier_id": subscription["tier_id"],
            "subscription_status": subscription["status"],
            "required_capability": capability_key,
            "minimum_author_access": minimum_author_access,
            "metering_rule": rule.get("metering_rule"),
            "config_version": self.monetization.config_version(),
        }
        snapshot.update(self._required_tier_snapshot(required_tier))
        snapshot["suggested_checkout_tier"] = required_tier
        snapshot["required_units"] = required_units
        return snapshot

    def author_access_snapshot(self, *, account_id: Optional[str], world_version_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_account_id = self.resolve_account_id(account_id=account_id)
        subscription_payload = self.subscription_status(account_id=resolved_account_id) if resolved_account_id else {}
        return {
            "account_id": resolved_account_id or None,
            "world_version_id": world_version_id,
            "subscription": subscription_payload.get("subscription") if resolved_account_id else None,
            "wallets": self._wallets_for_account(resolved_account_id) if resolved_account_id else {},
            "lifecycle_history_summary": subscription_payload.get("lifecycle_history_summary", {}) if resolved_account_id else {},
            "recommended_action": subscription_payload.get("recommended_action") if resolved_account_id else None,
            "actions": {
                "save_draft": self.access_check_author(account_id=resolved_account_id, action_name="save_draft"),
                "update_draft": self.access_check_author(account_id=resolved_account_id, action_name="update_draft"),
                "validate_draft": self.access_check_author(account_id=resolved_account_id, action_name="validate_draft"),
                "submit_draft": self.access_check_author(account_id=resolved_account_id, action_name="submit_draft"),
                "draft_from_brief": self.access_check_author(account_id=resolved_account_id, action_name="draft_from_brief"),
                "simulate": self.access_check_author(account_id=resolved_account_id, action_name="simulate"),
            },
            **self._config_snapshot(),
        }

    def _support_action(
        self,
        *,
        action_type: str,
        label: str,
        prefill: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "action_type": action_type,
            "label": label,
            "prefill": dict(prefill or {}),
        }

    def _support_issue(
        self,
        *,
        issue_type: str,
        severity: str,
        title: str,
        summary: str,
        reason: str,
        detected_at: Optional[str],
        surfaces: List[str],
        evidence: Dict[str, Any],
        related_objects: Dict[str, Any],
        suggested_operator_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "issue_id": "%s_%s" % (issue_type, abs(hash((issue_type, reason, detected_at, title))) % 100000),
            "issue_type": issue_type,
            "severity": severity,
            "title": title,
            "summary": summary,
            "reason": reason,
            "detected_at": detected_at,
            "surfaces": list(surfaces),
            "evidence": dict(evidence),
            "related_objects": dict(related_objects),
            "suggested_operator_actions": list(suggested_operator_actions),
        }

    def support_issue_lookup(self, *, account_id: str, limit: int = 10) -> Dict[str, Any]:
        resolved_account_id = self.resolve_account_id(account_id=account_id)
        subscription_payload = self.subscription_status(account_id=resolved_account_id)
        subscription = dict(subscription_payload.get("subscription") or {})
        wallets = dict(subscription_payload.get("wallets") or {})
        lifecycle_history_summary = dict(subscription_payload.get("lifecycle_history_summary") or {})
        author_access = self.author_access_snapshot(account_id=resolved_account_id)
        authored_world_version_ids = self._authored_world_version_ids(resolved_account_id, limit=5)
        recent_events = self.repository.list_analytics_events(reader_id=resolved_account_id, limit=max(limit * 5, 20))
        payment_required_events = [item for item in recent_events if item.get("event_name") == "payment_required"]
        revoked_events = [item for item in recent_events if item.get("event_name") == "entitlement_revoked"]
        checkout_events = [item for item in recent_events if item.get("event_name") == "checkout_started"]
        has_author_subscription = bool(subscription) and subscription.get("author_access") not in {None, "", "none"}
        has_author_context = has_author_subscription or bool(authored_world_version_ids) or any(
            str(item.get("event_name") or "").startswith("author_draft_") for item in recent_events
        )
        blocked_author_actions = {
            key: value
            for key, value in dict(author_access.get("actions", {})).items()
            if not value.get("allowed")
        }
        story_wallet = dict(wallets.get("story_credits") or {})
        studio_wallet = dict(wallets.get("studio_credits") or {})

        issues: List[Dict[str, Any]] = []

        subscription_status = subscription.get("status")
        if subscription_status in {"past_due", "expired", "canceled"}:
            tier_id = subscription.get("tier_id") or "play_pass"
            issues.append(
                self._support_issue(
                    issue_type="subscription_lifecycle_issue",
                    severity="high" if subscription_status in {"past_due", "expired"} else "medium",
                    title="Subscription lifecycle blocks access",
                    summary="订阅当前处于 %s，Reader/Author 可能因此被挡住。" % subscription_status,
                    reason=subscription.get("lifecycle_reason") or subscription_status,
                    detected_at=subscription.get("period_end") or subscription.get("updated_at"),
                    surfaces=["reader", "author"],
                    evidence={
                        "subscription_id": subscription.get("subscription_id"),
                        "status": subscription_status,
                        "next_action": subscription.get("next_action"),
                        "tier_id": tier_id,
                        "retry_attempt_count": lifecycle_history_summary.get("retry_attempt_count", 0),
                    },
                    related_objects={
                        "subscription_id": subscription.get("subscription_id"),
                        "tier_id": tier_id,
                    },
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="retry_payment",
                            label="重试支付并恢复订阅",
                            prefill={"account_id": resolved_account_id, "tier_id": tier_id, "subscription_status": "active"},
                        ),
                        self._support_action(
                            action_type="grant_subscription",
                            label="重新授予 %s" % tier_id,
                            prefill={"account_id": resolved_account_id, "tier_id": tier_id, "subscription_status": "active"},
                        ),
                    ],
                )
            )

        if not subscription and (payment_required_events or (has_author_context and blocked_author_actions)):
            tier_id = "creator_pass" if has_author_context and blocked_author_actions else "play_pass"
            issues.append(
                self._support_issue(
                    issue_type="missing_subscription",
                    severity="high",
                    title="No active subscription for blocked account",
                    summary="账号没有 active/trialing subscription，但最近已经出现付费挡板或 Author gating。",
                    reason="subscription_required",
                    detected_at=(payment_required_events[0].get("occurred_at") if payment_required_events else None),
                    surfaces=["reader"] + (["author"] if blocked_author_actions else []),
                    evidence={
                        "payment_required_count": len(payment_required_events),
                        "blocked_author_actions": sorted(blocked_author_actions.keys()) if has_author_context else [],
                    },
                    related_objects={
                        "session_ids": [item.get("session_id") for item in payment_required_events if item.get("session_id")],
                        "world_version_ids": [item.get("world_version_id") for item in payment_required_events if item.get("world_version_id")],
                    },
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="grant_subscription",
                            label="授予 %s" % tier_id,
                            prefill={"account_id": resolved_account_id, "tier_id": tier_id, "subscription_status": "active"},
                        ),
                    ],
                )
            )

        if payment_required_events:
            worlds = [item.get("payload_json", {}).get("world_id") for item in payment_required_events if item.get("payload_json", {}).get("world_id")]
            sessions = [item.get("session_id") for item in payment_required_events if item.get("session_id")]
            issues.append(
                self._support_issue(
                    issue_type="reader_payment_required_recent",
                    severity="high" if len(payment_required_events) >= 2 else "medium",
                    title="Reader recently hit paywall",
                    summary="最近出现了 %s 次 payment_required，需要快速判断是 story credits、world pass 还是 subscription 问题。" % len(payment_required_events),
                    reason=(payment_required_events[0].get("payload_json", {}) or {}).get("reason") or "payment_required",
                    detected_at=payment_required_events[0].get("occurred_at"),
                    surfaces=["reader"],
                    evidence={
                        "event_count": len(payment_required_events),
                        "wallet_reason": (payment_required_events[0].get("payload_json", {}) or {}).get("reason"),
                        "world_ids": worlds,
                    },
                    related_objects={
                        "session_ids": sessions,
                        "world_ids": worlds,
                    },
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="grant_wallet",
                            label="补充 story_credits",
                            prefill={"account_id": resolved_account_id, "wallet_type": "story_credits", "amount": 10},
                        ),
                        self._support_action(
                            action_type="grant_subscription",
                            label="授予 Play Pass",
                            prefill={"account_id": resolved_account_id, "tier_id": "play_pass", "subscription_status": "active"},
                        ),
                    ],
                )
            )

        if float(story_wallet.get("balance") or 0.0) < 1.0 and payment_required_events:
            issues.append(
                self._support_issue(
                    issue_type="story_credits_exhausted",
                    severity="medium",
                    title="Story credits exhausted",
                    summary="Story Credits 已耗尽，Reader 继续阅读会被挡板拦下。",
                    reason=str(story_wallet.get("reason") or "credits_exhausted"),
                    detected_at=None,
                    surfaces=["reader"],
                    evidence={
                        "balance": float(story_wallet.get("balance") or 0.0),
                        "status": story_wallet.get("status"),
                        "payment_required_count": len(payment_required_events),
                    },
                    related_objects={"entitlement_id": story_wallet.get("entitlement_id")},
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="grant_wallet",
                            label="充值 story_credits",
                            prefill={"account_id": resolved_account_id, "wallet_type": "story_credits", "amount": 10},
                        ),
                    ],
                )
            )

        if float(studio_wallet.get("balance") or 0.0) < 1.0 and has_author_context:
            issues.append(
                self._support_issue(
                    issue_type="studio_credits_exhausted",
                    severity="medium",
                    title="Studio credits exhausted",
                    summary="Studio Credits 已耗尽，Author draft/simulate 会被挡下。",
                    reason=str(studio_wallet.get("reason") or "studio_credits_exhausted"),
                    detected_at=None,
                    surfaces=["author"],
                    evidence={
                        "balance": float(studio_wallet.get("balance") or 0.0),
                        "status": studio_wallet.get("status"),
                        "blocked_author_actions": sorted(blocked_author_actions.keys()),
                    },
                    related_objects={"entitlement_id": studio_wallet.get("entitlement_id")},
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="grant_wallet",
                            label="充值 studio_credits",
                            prefill={"account_id": resolved_account_id, "wallet_type": "studio_credits", "amount": 10},
                        ),
                    ],
                )
            )

        if blocked_author_actions and has_author_context:
            highest_tier = max(
                (value.get("suggested_checkout_tier") or value.get("required_tier") or "creator_pass" for value in blocked_author_actions.values()),
                key=lambda tier: {"play_pass": 1, "creator_pass": 2, "studio_pass": 3}.get(tier, 0),
            )
            issues.append(
                self._support_issue(
                    issue_type="author_access_blocked",
                    severity="high",
                    title="Author actions are blocked",
                    summary="Author 关键动作当前不可用，需要补 tier 或 studio credits。",
                    reason=next(iter(blocked_author_actions.values())).get("reason") or "author_access_blocked",
                    detected_at=None,
                    surfaces=["author"],
                    evidence={
                        "blocked_actions": {
                            key: {
                                "reason": value.get("reason"),
                                "wallet_type": value.get("wallet_type"),
                                "required_tier": value.get("required_tier"),
                            }
                            for key, value in blocked_author_actions.items()
                        }
                    },
                    related_objects={"subscription_id": subscription.get("subscription_id")},
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="grant_subscription",
                            label="授予 %s" % highest_tier,
                            prefill={"account_id": resolved_account_id, "tier_id": highest_tier, "subscription_status": "active"},
                        ),
                        self._support_action(
                            action_type="grant_wallet",
                            label="补充 studio_credits",
                            prefill={"account_id": resolved_account_id, "wallet_type": "studio_credits", "amount": 10},
                        ),
                    ],
                )
            )

        if revoked_events:
            entitlement_ids = [
                item.get("payload_json", {}).get("entitlement_id")
                for item in revoked_events
                if item.get("payload_json", {}).get("entitlement_id")
            ]
            issues.append(
                self._support_issue(
                    issue_type="entitlement_recently_revoked",
                    severity="medium",
                    title="Recent entitlement revoke detected",
                    summary="最近有 entitlement 被撤销，可能解释了为什么账号突然失去能力或额度。",
                    reason=(revoked_events[0].get("payload_json", {}) or {}).get("reason") or "entitlement_revoked",
                    detected_at=revoked_events[0].get("occurred_at"),
                    surfaces=["ops", "reader", "author"],
                    evidence={
                        "event_count": len(revoked_events),
                        "entitlement_ids": entitlement_ids,
                    },
                    related_objects={"entitlement_ids": entitlement_ids},
                    suggested_operator_actions=[
                        self._support_action(
                            action_type="prefill_entitlement_revoke",
                            label="检查被撤销的 entitlement",
                            prefill={
                                "account_id": resolved_account_id,
                                "entitlement_id": entitlement_ids[0] if entitlement_ids else None,
                                "entitlement_reason": "manual_entitlement_revoke",
                            },
                        ),
                    ],
                )
            )

        issues.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}.get(str(item.get("severity")), 3),
                str(item.get("detected_at") or ""),
            ),
            reverse=False,
        )
        issues = issues[:limit]

        severity_counts: Dict[str, int] = {}
        issue_type_counts: Dict[str, int] = {}
        recommended_actions: List[Dict[str, Any]] = []
        seen_actions = set()
        for issue in issues:
            severity = str(issue.get("severity") or "unknown")
            issue_type = str(issue.get("issue_type") or "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
            for action in issue.get("suggested_operator_actions", []):
                signature = (action.get("action_type"), json.dumps(action.get("prefill", {}), sort_keys=True, ensure_ascii=False))
                if signature in seen_actions:
                    continue
                seen_actions.add(signature)
                recommended_actions.append(action)

        return {
            "account_id": resolved_account_id,
            "subscription": subscription,
            "wallets": wallets,
            "support_summary": {
                "open_issue_count": len(issues),
                "high_priority_issue_count": severity_counts.get("high", 0),
                "issue_type_counts": issue_type_counts,
                "severity_counts": severity_counts,
                "primary_issue_type": issues[0].get("issue_type") if issues else None,
                "latest_issue_at": next((item.get("detected_at") for item in issues if item.get("detected_at")), None),
                "recent_payment_required_count": len(payment_required_events),
                "recent_checkout_started_count": len(checkout_events),
            },
            "support_issues": issues,
            "support_tooling": {
                "prefill_defaults": {"account_id": resolved_account_id},
                "recommended_actions": recommended_actions[:6],
                "quick_refs": {
                    "subscription_id": subscription.get("subscription_id"),
                    "story_wallet_entitlement_id": story_wallet.get("entitlement_id"),
                    "studio_wallet_entitlement_id": studio_wallet.get("entitlement_id"),
                    "recent_session_ids": [item.get("session_id") for item in payment_required_events if item.get("session_id")][:5],
                    "recent_world_version_ids": [item.get("world_version_id") for item in payment_required_events if item.get("world_version_id")][:5],
                },
            },
        }

    def account_detail(self, *, account_id: str, limit: int = 10) -> Dict[str, Any]:
        entitlement_audit = self.entitlement_audit(account_id=account_id, limit=limit)
        subscription_snapshot = self.subscription_status(account_id=account_id)
        audit_bundle = self.full_audit_trail(account_id=account_id, limit=max(limit * 2, 20))
        support_lookup = self.support_issue_lookup(account_id=account_id, limit=limit)
        checkout_sessions = self.repository.list_billing_checkout_sessions(account_id=account_id, limit=limit)
        lifecycle_events = self.repository.list_billing_lifecycle_events(account_id=account_id, limit=limit)
        retry_attempts = self.repository.list_billing_retry_attempts(account_id=account_id, limit=limit)
        recent_meters = self.repository.list_usage_meters(account_id=account_id)[:limit]
        recent_events = self.repository.list_analytics_events(reader_id=account_id, limit=limit)
        recent_sessions: List[Dict[str, Any]] = []
        for session in self.repository.list_sessions():
            try:
                detail = self.repository.get_session(session["session_id"])
            except KeyError:
                continue
            if detail.metadata.get("reader_id") != account_id:
                continue
            recent_sessions.append(
                {
                    "session_id": session["session_id"],
                    "world_id": session["world_id"],
                    "world_version_id": session["world_version_id"],
                    "current_turn_index": session["current_turn_index"],
                    "last_event_title": session.get("last_event_title"),
                    "last_chapter_title": session.get("last_chapter_title"),
                    "created_at": session.get("created_at"),
                    "access_tier": detail.metadata.get("entitlements_snapshot", {}).get("access_tier"),
                    "reason": detail.metadata.get("entitlements_snapshot", {}).get("reason"),
                }
            )
            if len(recent_sessions) >= limit:
                break

        recent_drafts: List[Dict[str, Any]] = []
        for item in self.repository.list_world_versions():
            try:
                version = self.repository.get_world_version(item["world_version_id"])
            except KeyError:
                continue
            if version.author_id != account_id:
                continue
            recent_drafts.append(
                {
                    "world_version_id": version.world_version_id,
                    "world_id": version.world_id,
                    "status": version.status,
                    "version": version.version,
                    "risk_rating": version.risk_rating,
                    "title": version.worldpack_json.get("title", version.world_id),
                    "updated_at": item.get("updated_at"),
                }
            )
            if len(recent_drafts) >= limit:
                break

        meter_summary: Dict[str, Dict[str, Any]] = {}
        for item in recent_meters:
            action = str(item.get("action_type", "unknown"))
            entry = meter_summary.setdefault(
                action,
                {
                    "action_type": action,
                    "count": 0,
                    "usage_units": 0.0,
                    "wallet_types": set(),
                },
            )
            entry["count"] += 1
            entry["usage_units"] += float(item.get("usage_units", 0.0))
            if item.get("wallet_type"):
                entry["wallet_types"].add(item.get("wallet_type"))

        activity_summary = {
            "recent_meter_count": len(recent_meters),
            "recent_event_count": len(recent_events),
            "recent_session_count": len(recent_sessions),
            "recent_draft_count": len(recent_drafts),
            "billing_event_count": len(lifecycle_events),
            "retry_attempt_count": len(retry_attempts),
            "meter_by_action": [
                {
                    "action_type": key,
                    "count": value["count"],
                    "usage_units": round(value["usage_units"], 3),
                    "wallet_types": sorted(value["wallet_types"]),
                }
                for key, value in sorted(
                    meter_summary.items(),
                    key=lambda item: (-item[1]["count"], item[0]),
                )
            ],
        }

        return {
            "account_id": account_id,
            "subscription": subscription_snapshot.get("subscription"),
            "wallets": subscription_snapshot.get("wallets", {}),
            "checkout_session": subscription_snapshot.get("latest_checkout_session"),
            "recent_checkout_sessions": checkout_sessions,
            "lifecycle_history_summary": subscription_snapshot.get("lifecycle_history_summary", {}),
            "billing_lifecycle_events": lifecycle_events,
            "billing_retry_attempts": retry_attempts,
            "author_access": self.author_access_snapshot(account_id=account_id),
            "entitlement_audit": entitlement_audit,
            "audit_trail": audit_bundle.get("audit_trail", []),
            "audit_breakdown": audit_bundle.get("audit_breakdown", {}),
            "timeline_cursor": audit_bundle.get("timeline_cursor", {}),
            "support_summary": support_lookup.get("support_summary", {}),
            "support_issues": support_lookup.get("support_issues", []),
            "support_tooling": support_lookup.get("support_tooling", {}),
            "recent_meters": recent_meters,
            "recent_events": recent_events,
            "recent_sessions": recent_sessions,
            "recent_drafts": recent_drafts,
            "activity_summary": activity_summary,
            **self._config_snapshot(),
        }

    def consume_studio_credits(self, *, account_id: str, amount: float) -> Dict[str, Any]:
        return self.debit_wallet_credits(account_id=account_id, wallet_type="studio_credits", amount=amount)

    def meter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.create_usage_meter(payload)
