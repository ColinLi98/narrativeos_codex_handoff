from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .billing import BillingService
from .governance import GovernanceService
from .ops_alerting import OpsAlertingService
from .ops_traceability import OpsTraceabilityService


class OpsAccountWorkspaceService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: BillingService,
        governance_service: GovernanceService,
        ops_alerting_service: OpsAlertingService,
        ops_traceability_service: OpsTraceabilityService,
    ) -> None:
        self.repository = repository
        self.billing = billing_service
        self.governance = governance_service
        self.alerting = ops_alerting_service
        self.traceability = ops_traceability_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _blocked_author_actions(self, detail: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        actions = dict((detail.get("author_access") or {}).get("actions") or {})
        return [(key, value) for key, value in actions.items() if not value.get("allowed")]

    def _health_status(
        self,
        *,
        detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
        alerts_payload: Dict[str, Any],
    ) -> str:
        subscription = dict(detail.get("subscription") or {})
        if int((governance_snapshot.get("restriction_summary") or {}).get("active_restriction_count") or 0) > 0:
            return "critical"
        if subscription.get("status") in {"past_due", "expired", "canceled"}:
            return "critical"
        if any(item.get("severity") in {"high", "critical"} for item in alerts_payload.get("alerts", [])):
            return "critical"
        if detail.get("support_issues") or self._blocked_author_actions(detail):
            return "needs_attention"
        return "healthy"

    def _surface_statuses(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        subscription = dict(detail.get("subscription") or {})
        story_wallet = dict((detail.get("wallets") or {}).get("story_credits") or {})
        studio_wallet = dict((detail.get("wallets") or {}).get("studio_credits") or {})
        author_blocked = self._blocked_author_actions(detail)
        return {
            "reader": {
                "status": "blocked" if subscription.get("status") in {"past_due", "expired", "canceled"} or self._safe_float(story_wallet.get("balance")) < 1 else "open",
                "reason": subscription.get("lifecycle_reason") or story_wallet.get("reason"),
            },
            "author": {
                "status": "blocked" if author_blocked else "open",
                "reason": author_blocked[0][1].get("reason") if author_blocked else None,
            },
        }

    def _wallet_posture(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        wallets = dict(detail.get("wallets") or {})
        entries = []
        for wallet_type, value in wallets.items():
            balance = self._safe_float(value.get("balance"))
            status = value.get("status")
            entries.append(
                {
                    "wallet_type": wallet_type,
                    "balance": balance,
                    "status": status,
                    "reason": value.get("reason"),
                    "anomaly": status in {"expired", "exhausted"} or balance < 1.0,
                }
            )
        return {
            "wallets": entries,
            "anomaly_count": sum(1 for item in entries if item["anomaly"]),
        }

    def _entitlement_posture(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        audit = dict(detail.get("entitlement_audit") or {})
        entitlements = list(audit.get("entitlements") or [])
        status_counts: Dict[str, int] = {}
        for item in entitlements:
            status = str(item.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "total_entitlements": len(entitlements),
            "status_counts": status_counts,
            "revoke_candidates": list(audit.get("revoke_candidates") or []),
        }

    def _top_blockers(
        self,
        *,
        detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
        alerts_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        blockers: List[Dict[str, Any]] = []
        subscription = dict(detail.get("subscription") or {})
        if subscription.get("status") in {"past_due", "expired", "canceled"}:
            blockers.append(
                {
                    "blocker_id": "subscription_lifecycle",
                    "severity": "high",
                    "headline": f"subscription={subscription.get('status')}",
                    "summary": subscription.get("lifecycle_reason") or subscription.get("next_action") or "subscription requires operator attention",
                }
            )
        for wallet in self._wallet_posture(detail)["wallets"]:
            if wallet["anomaly"]:
                blockers.append(
                    {
                        "blocker_id": f"wallet::{wallet['wallet_type']}",
                        "severity": "medium",
                        "headline": f"{wallet['wallet_type']}={wallet['status']}",
                        "summary": f"balance {wallet['balance']:.0f} · {wallet.get('reason') or '-'}",
                    }
                )
        if int((governance_snapshot.get("restriction_summary") or {}).get("active_restriction_count") or 0) > 0:
            blockers.append(
                {
                    "blocker_id": "active_restriction",
                    "severity": "high",
                    "headline": "active governance restriction",
                    "summary": f"{(governance_snapshot.get('restriction_summary') or {}).get('active_restriction_count')} active restrictions",
                }
            )
        for issue in list(detail.get("support_issues") or [])[:3]:
            blockers.append(
                {
                    "blocker_id": issue.get("issue_id"),
                    "severity": issue.get("severity") or "medium",
                    "headline": issue.get("title") or issue.get("issue_type") or "support_issue",
                    "summary": issue.get("summary") or issue.get("reason") or "",
                }
            )
        for alert in list(alerts_payload.get("alerts") or [])[:3]:
            blockers.append(
                {
                    "blocker_id": alert.get("alert_id"),
                    "severity": alert.get("severity") or "medium",
                    "headline": alert.get("title") or alert.get("category") or "alert",
                    "summary": alert.get("summary") or "",
                }
            )
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        blockers.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 5), item.get("headline") or ""))
        return blockers[:8]

    def _normalize_action(
        self,
        *,
        action_id: str,
        label: str,
        handler: str,
        mode: str,
        reason: str,
        priority: int,
        prefill: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "action_id": action_id,
            "label": label,
            "handler": handler,
            "mode": mode,
            "reason": reason,
            "priority": priority,
            "prefill": dict(prefill or {}),
        }

    def _action_pack(
        self,
        *,
        detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
        alerts_payload: Dict[str, Any],
        investigation: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        account_id = detail.get("account_id")
        actions: List[Dict[str, Any]] = [
            self._normalize_action(
                action_id="open_investigation",
                label="Open Investigation",
                handler="run_investigation",
                mode="navigate",
                reason=(investigation.get("recommended_paths") or [{}])[0].get("reason") or "inspect unified investigation trace",
                priority=0,
                prefill=dict(investigation.get("export_refs") or {"account_id": account_id}),
            ),
        ]
        subscription = dict(detail.get("subscription") or {})
        if subscription.get("status") == "past_due":
            actions.append(
                self._normalize_action(
                    action_id="retry_payment",
                    label="Retry Subscription Payment",
                    handler="retry_subscription_payment",
                    mode="execute",
                    reason="subscription is past_due",
                    priority=1,
                    prefill={"account_id": account_id},
                )
            )
            actions.append(
                self._normalize_action(
                    action_id="reconcile_subscription",
                    label="Reconcile Subscription",
                    handler="reconcile_subscription",
                    mode="execute",
                    reason="refresh lifecycle snapshot after payment retry or manual review",
                    priority=2,
                    prefill={"account_id": account_id},
                )
            )
        if subscription.get("status") in {"expired", "canceled"}:
            tier_id = subscription.get("tier_id") or "play_pass"
            actions.append(
                self._normalize_action(
                    action_id="grant_subscription",
                    label=f"Grant {tier_id}",
                    handler="grant_subscription",
                    mode="execute",
                    reason=f"subscription status is {subscription.get('status')}",
                    priority=1,
                    prefill={"account_id": account_id, "tier_id": tier_id},
                )
            )
        for issue in detail.get("support_issues", []):
            for action in issue.get("suggested_operator_actions", []):
                action_type = action.get("action_type")
                if action_type == "grant_wallet":
                    wallet_type = action.get("prefill", {}).get("wallet_type") or "story_credits"
                    actions.append(
                        self._normalize_action(
                            action_id=f"grant_wallet::{wallet_type}",
                            label=action.get("label") or f"Grant {wallet_type}",
                            handler="grant_wallet",
                            mode="execute",
                            reason=issue.get("title") or issue.get("issue_type") or "support issue",
                            priority=1 if wallet_type == "story_credits" else 2,
                            prefill={**dict(action.get("prefill") or {}), "account_id": account_id},
                        )
                    )
                elif action_type == "grant_subscription":
                    tier_id = action.get("prefill", {}).get("tier_id") or "play_pass"
                    actions.append(
                        self._normalize_action(
                            action_id=f"grant_subscription::{tier_id}",
                            label=action.get("label") or f"Grant {tier_id}",
                            handler="grant_subscription",
                            mode="execute",
                            reason=issue.get("title") or issue.get("issue_type") or "support issue",
                            priority=1,
                            prefill={**dict(action.get("prefill") or {}), "account_id": account_id},
                        )
                    )
                elif action_type == "retry_payment":
                    actions.append(
                        self._normalize_action(
                            action_id="retry_payment_from_support",
                            label=action.get("label") or "Retry Payment",
                            handler="retry_subscription_payment",
                            mode="execute",
                            reason=issue.get("title") or issue.get("issue_type") or "support issue",
                            priority=1,
                            prefill={"account_id": account_id},
                        )
                    )
        if int((governance_snapshot.get("restriction_summary") or {}).get("active_restriction_count") or 0) > 0:
            first_case = (governance_snapshot.get("governance_cases") or [{}])[0]
            actions.append(
                self._normalize_action(
                    action_id="open_governance_case",
                    label="Open Governance Case",
                    handler="open_governance_case",
                    mode="navigate",
                    reason="active restriction is present",
                    priority=1,
                    prefill={
                        "case_id": first_case.get("case_id"),
                        "account_id": account_id,
                    },
                )
            )
        if alerts_payload.get("alerts"):
            actions.append(
                self._normalize_action(
                    action_id="open_alerts",
                    label="Review Alerts",
                    handler="open_alert_feed",
                    mode="navigate",
                    reason=f"{len(alerts_payload.get('alerts') or [])} actionable alerts",
                    priority=1,
                    prefill={"account_id": account_id},
                )
            )
        deduped: Dict[str, Dict[str, Any]] = {}
        for action in actions:
            if action["action_id"] not in deduped or action["priority"] < deduped[action["action_id"]]["priority"]:
                deduped[action["action_id"]] = action
        return sorted(deduped.values(), key=lambda item: (item["priority"], item["label"]))

    def _operator_timeline(
        self,
        *,
        detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
        alerts_payload: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for item in list(detail.get("audit_trail") or [])[:limit]:
            entries.append(
                {
                    "entry_id": f"audit::{item.get('audit_id') or item.get('occurred_at')}",
                    "occurred_at": item.get("occurred_at"),
                    "category": item.get("category") or "audit",
                    "headline": item.get("action") or "audit_event",
                    "summary": f"{item.get('object_type') or '-'}:{item.get('object_id') or '-'} · {item.get('reason') or '-'}",
                    "next_actions": [],
                }
            )
        for item in list(detail.get("billing_lifecycle_events") or [])[:limit]:
            entries.append(
                {
                    "entry_id": f"billing::{item.get('event_id')}",
                    "occurred_at": item.get("occurred_at"),
                    "category": "billing",
                    "headline": item.get("event_type") or "billing_event",
                    "summary": f"{item.get('status') or '-'} · {item.get('subscription_id') or '-'}",
                    "next_actions": ["replay_billing_event"] if item.get("status") != "processed" else [],
                }
            )
        for item in list(governance_snapshot.get("governance_cases") or [])[:limit]:
            entries.append(
                {
                    "entry_id": f"governance::{item.get('case_id')}",
                    "occurred_at": item.get("updated_at"),
                    "category": "governance",
                    "headline": item.get("summary") or item.get("case_id") or "governance_case",
                    "summary": f"{item.get('status') or '-'} · owner {(item.get('workflow_summary') or {}).get('owner_id') or item.get('owner_id') or '-'}",
                    "next_actions": list((item.get("workflow_summary") or {}).get("transition_options") or []),
                }
            )
        for item in list(alerts_payload.get("alerts") or [])[:limit]:
            entries.append(
                {
                    "entry_id": item.get("alert_id"),
                    "occurred_at": item.get("detected_at"),
                    "category": "alert",
                    "headline": item.get("title") or item.get("category") or "alert",
                    "summary": item.get("summary") or "",
                    "next_actions": list(item.get("recommended_actions") or []),
                }
            )
        entries.sort(key=lambda item: self._parse_timestamp(item.get("occurred_at")), reverse=True)
        return entries[:limit]

    def account_workspace(self, *, account_id: str, limit: int = 12) -> Dict[str, Any]:
        detail = self.billing.account_detail(account_id=account_id, limit=limit)
        governance_snapshot = self.governance.account_snapshot(account_id=account_id, limit=limit)
        alerts_payload = self.alerting.list_alerts(account_id=account_id, status_filter="actionable", limit=8)
        investigation = self.traceability.investigate_account(account_id=account_id, limit=min(limit, 12))

        health_status = self._health_status(
            detail=detail,
            governance_snapshot=governance_snapshot,
            alerts_payload=alerts_payload,
        )
        wallet_posture = self._wallet_posture(detail)
        entitlement_posture = self._entitlement_posture(detail)
        surface_statuses = self._surface_statuses(detail)
        top_blockers = self._top_blockers(
            detail=detail,
            governance_snapshot=governance_snapshot,
            alerts_payload=alerts_payload,
        )
        action_pack = self._action_pack(
            detail=detail,
            governance_snapshot=governance_snapshot,
            alerts_payload=alerts_payload,
            investigation=investigation,
        )
        operator_timeline = self._operator_timeline(
            detail=detail,
            governance_snapshot=governance_snapshot,
            alerts_payload=alerts_payload,
            limit=limit,
        )
        subscription = dict(detail.get("subscription") or {})
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "workspace_summary": {
                "health_status": health_status,
                "subscription_status": subscription.get("status") or "inactive",
                "tier_id": subscription.get("tier_id"),
                "actionable_alert_count": int((alerts_payload.get("summary") or {}).get("actionable_alert_count") or 0),
                "support_issue_count": len(detail.get("support_issues") or []),
                "active_restriction_count": int((governance_snapshot.get("restriction_summary") or {}).get("active_restriction_count") or 0),
                "open_governance_case_count": int((governance_snapshot.get("governance_summary") or {}).get("open_case_count") or 0),
                "recommended_path": (investigation.get("recommended_paths") or [{}])[0].get("path_id"),
                "surface_statuses": surface_statuses,
            },
            "wallet_posture": wallet_posture,
            "entitlement_posture": entitlement_posture,
            "top_blockers": top_blockers,
            "action_pack": action_pack,
            "investigation_summary": {
                "recommended_paths": investigation.get("recommended_paths") or [],
                "summary": investigation.get("investigation_summary") or {},
                "export_refs": investigation.get("export_refs") or {"account_id": account_id},
            },
            "linked_context": {
                "support_issue_ids": [item.get("issue_id") for item in detail.get("support_issues", [])],
                "governance_case_ids": [item.get("case_id") for item in governance_snapshot.get("governance_cases", [])],
                "alert_ids": [item.get("alert_id") for item in alerts_payload.get("alerts", [])],
                "recent_session_ids": [item.get("session_id") for item in detail.get("recent_sessions", []) if item.get("session_id")],
                "recent_world_version_ids": [item.get("world_version_id") for item in detail.get("recent_drafts", []) if item.get("world_version_id")],
                "subscription_id": subscription.get("subscription_id"),
            },
            "operator_timeline": operator_timeline,
        }
