from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .billing import BillingService
from .governance import GovernanceService
from .observability import ObservabilityService
from .review import ReviewService


class OpsTraceabilityService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: BillingService,
        governance_service: GovernanceService,
        review_service: ReviewService,
        observability_service: ObservabilityService,
    ) -> None:
        self.repository = repository
        self.billing = billing_service
        self.governance = governance_service
        self.review = review_service
        self.observability = observability_service

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

    def _severity_rank(self, value: Optional[str]) -> int:
        return {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "info": 4,
        }.get(str(value or "info"), 5)

    def _trace_entry(
        self,
        *,
        trace_id: str,
        occurred_at: Optional[str],
        source_type: str,
        category: str,
        severity: str,
        status: Optional[str],
        headline: str,
        summary: str,
        account_id: Optional[str],
        world_version_id: Optional[str] = None,
        case_id: Optional[str] = None,
        session_id: Optional[str] = None,
        object_type: str,
        object_id: Optional[str],
        evidence_refs: Optional[List[Dict[str, Any]]] = None,
        related_trace_ids: Optional[List[str]] = None,
        next_actions: Optional[List[str]] = None,
        link_tokens: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "trace_id": trace_id,
            "occurred_at": occurred_at,
            "source_type": source_type,
            "category": category,
            "severity": severity,
            "status": status,
            "headline": headline,
            "summary": summary,
            "account_id": account_id,
            "world_version_id": world_version_id,
            "case_id": case_id,
            "session_id": session_id,
            "object_type": object_type,
            "object_id": object_id,
            "evidence_refs": list(evidence_refs or []),
            "related_trace_ids": list(related_trace_ids or []),
            "next_actions": list(next_actions or []),
            "_link_tokens": list(link_tokens or []),
        }

    def _evidence_ref(self, *, kind: str, label: str, ref_id: str, preview: str) -> Dict[str, Any]:
        return {
            "kind": kind,
            "label": label,
            "ref_id": ref_id,
            "preview": preview[:220],
        }

    def _evidence_item(
        self,
        *,
        evidence_id: str,
        source_type: str,
        source_id: str,
        title: str,
        preview: str,
        linked_object_type: str,
        linked_object_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "evidence_id": evidence_id,
            "source_type": source_type,
            "source_id": source_id,
            "title": title,
            "preview": preview[:280],
            "linked_object_type": linked_object_type,
            "linked_object_id": linked_object_id,
        }

    def _world_versions_for_account(self, account_id: str) -> List[str]:
        result: List[str] = []
        for item in self.repository.list_world_versions():
            try:
                version = self.repository.get_world_version(item["world_version_id"])
            except KeyError:
                continue
            if version.author_id == account_id:
                result.append(version.world_version_id)
        return result

    def _recommended_paths(
        self,
        *,
        account_detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
        world_traces: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        support_summary = dict(account_detail.get("support_summary") or {})
        lifecycle_summary = dict(account_detail.get("lifecycle_history_summary") or {})
        governance_summary = dict(governance_snapshot.get("governance_summary") or {})
        restriction_summary = dict(governance_snapshot.get("restriction_summary") or {})

        billing_score = 0
        if (support_summary.get("issue_type_counts") or {}).get("subscription_lifecycle_issue"):
            billing_score += 3
        if int(support_summary.get("recent_payment_required_count") or 0) > 0:
            billing_score += 2
        if int(lifecycle_summary.get("retry_attempt_count") or 0) > 0:
            billing_score += 2

        governance_score = 0
        if int(restriction_summary.get("active_restriction_count") or 0) > 0:
            governance_score += 3
        if int(governance_summary.get("open_case_count") or 0) > 0:
            governance_score += 2
        if any(item.get("source_type") == "governance_case" and item.get("severity") in {"high", "critical"} for item in world_traces):
            governance_score += 1

        release_score = 0
        if any(item.get("source_type") == "rollback_drilldown" for item in world_traces):
            release_score += 3
        if any(item.get("source_type") == "publish_checklist" and item.get("status") == "blocked" for item in world_traces):
            release_score += 2
        if any(item.get("source_type") == "review_timeline" and item.get("status") == "publish_blocked" for item in world_traces):
            release_score += 2

        ranked = sorted(
            [
                {
                    "path_id": "billing_first",
                    "score": billing_score,
                    "reason": "subscription_lifecycle_issue / payment_required / retry_attempts dominate",
                },
                {
                    "path_id": "governance_first",
                    "score": governance_score,
                    "reason": "active restriction or open abuse/moderation governance case dominates",
                },
                {
                    "path_id": "content_release_first",
                    "score": release_score,
                    "reason": "publish blocked / rollback / review anomaly dominate",
                },
            ],
            key=lambda item: (-item["score"], item["path_id"]),
        )
        return ranked

    def _billing_trace_entries(self, account_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        account_id = account_detail.get("account_id")
        entries: List[Dict[str, Any]] = []
        for event in account_detail.get("billing_lifecycle_events", []):
            event_type = str(event.get("event_type") or "")
            severity = "high" if event_type in {"subscription_payment_failed", "subscription_past_due"} else "info"
            entries.append(
                self._trace_entry(
                    trace_id=f"billing_event::{event['event_id']}",
                    occurred_at=event.get("occurred_at"),
                    source_type="billing_lifecycle_event",
                    category="billing",
                    severity=severity,
                    status=event.get("status"),
                    headline=event_type,
                    summary=f"provider {event.get('provider') or '-'} · subscription {event.get('subscription_id') or '-'}",
                    account_id=account_id,
                    object_type="billing_event",
                    object_id=event.get("event_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="billing_lifecycle_processing_result",
                            label=event_type,
                            ref_id=event.get("event_id"),
                            preview=str(event.get("processing_result") or event.get("payload_json") or "-"),
                        )
                    ],
                    next_actions=["replay_lifecycle_event"] if event.get("status") != "processed" else [],
                    link_tokens=[
                        f"subscription:{event.get('subscription_id')}" if event.get("subscription_id") else "",
                        f"checkout_session:{event.get('checkout_session_id')}" if event.get("checkout_session_id") else "",
                    ],
                )
            )
        for retry in account_detail.get("billing_retry_attempts", []):
            entries.append(
                self._trace_entry(
                    trace_id=f"billing_retry::{retry['retry_attempt_id']}",
                    occurred_at=retry.get("updated_at") or retry.get("created_at"),
                    source_type="billing_retry_attempt",
                    category="billing",
                    severity="high" if retry.get("status") == "failed" else "medium",
                    status=retry.get("status"),
                    headline=str(retry.get("retry_reason") or "retry_attempt"),
                    summary=f"subscription {retry.get('subscription_id') or '-'} · attempt {retry.get('attempt_count') or 0}",
                    account_id=account_id,
                    object_type="billing_retry_attempt",
                    object_id=retry.get("retry_attempt_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="billing_retry_payload",
                            label="retry_attempt",
                            ref_id=retry.get("retry_attempt_id"),
                            preview=str(retry.get("payload_json") or "-"),
                        )
                    ],
                    next_actions=["retry_payment"] if retry.get("status") != "succeeded" else [],
                    link_tokens=[
                        f"subscription:{retry.get('subscription_id')}" if retry.get("subscription_id") else "",
                        f"billing_event:{retry.get('source_event_id')}" if retry.get("source_event_id") else "",
                    ],
                )
            )
        return entries

    def _activity_trace_entries(self, account_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        account_id = account_detail.get("account_id")
        entries: List[Dict[str, Any]] = []
        for event in account_detail.get("recent_events", []):
            event_name = str(event.get("event_name") or "analytics_event")
            payload = dict(event.get("payload_json") or {})
            category = "billing" if event_name in {
                "payment_required",
                "checkout_started",
                "subscription_activated",
                "subscription_state_changed",
                "subscription_canceled",
                "entitlement_granted",
                "entitlement_revoked",
            } else "activity"
            severity = "medium" if event_name in {"payment_required", "subscription_state_changed"} else "info"
            entries.append(
                self._trace_entry(
                    trace_id=f"analytics_event::{event.get('event_id')}",
                    occurred_at=event.get("occurred_at"),
                    source_type="analytics_event",
                    category=category,
                    severity=severity,
                    status=event_name,
                    headline=event_name,
                    summary=str(payload.get("reason") or payload.get("status") or payload.get("world_id") or "-"),
                    account_id=account_id,
                    world_version_id=event.get("world_version_id"),
                    session_id=event.get("session_id"),
                    object_type="analytics_event",
                    object_id=str(event.get("event_id") or ""),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="analytics_event_payload",
                            label=event_name,
                            ref_id=str(event.get("event_id") or ""),
                            preview=str(payload or "-"),
                        )
                    ],
                    next_actions=["inspect_paywall_path"] if event_name == "payment_required" else [],
                    link_tokens=[
                        f"session:{event.get('session_id')}" if event.get("session_id") else "",
                        f"world_version:{event.get('world_version_id')}" if event.get("world_version_id") else "",
                        f"subscription:{payload.get('subscription_id')}" if payload.get("subscription_id") else "",
                    ],
                )
            )
        for meter in account_detail.get("recent_meters", []):
            entries.append(
                self._trace_entry(
                    trace_id=f"usage_meter::{meter.get('meter_id')}",
                    occurred_at=meter.get("occurred_at"),
                    source_type="usage_meter",
                    category="usage",
                    severity="info",
                    status=meter.get("action_type"),
                    headline=str(meter.get("action_type") or "usage_meter"),
                    summary=f"wallet {meter.get('wallet_type') or '-'} · units {meter.get('usage_units') or 0}",
                    account_id=account_id,
                    world_version_id=meter.get("world_version_id"),
                    session_id=meter.get("session_id"),
                    object_type="usage_meter",
                    object_id=str(meter.get("meter_id") or ""),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="usage_meter_payload",
                            label=meter.get("action_type") or "usage_meter",
                            ref_id=str(meter.get("meter_id") or ""),
                            preview=f"units={meter.get('usage_units') or 0} / cost={meter.get('estimated_cost') or 0} / rule={meter.get('model_policy_version') or '-'}",
                        )
                    ],
                    link_tokens=[
                        f"session:{meter.get('session_id')}" if meter.get("session_id") else "",
                        f"world_version:{meter.get('world_version_id')}" if meter.get("world_version_id") else "",
                    ],
                )
            )
        return entries

    def _support_trace_entries(self, account_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        account_id = account_detail.get("account_id")
        entries = []
        for issue in account_detail.get("support_issues", []):
            evidence_preview = " / ".join(f"{key}={value}" for key, value in dict(issue.get("evidence") or {}).items()) or "-"
            entries.append(
                self._trace_entry(
                    trace_id=f"support_issue::{issue['issue_id']}",
                    occurred_at=issue.get("detected_at"),
                    source_type="support_issue",
                    category="support",
                    severity=str(issue.get("severity") or "medium"),
                    status="open",
                    headline=str(issue.get("title") or issue.get("issue_type") or "support_issue"),
                    summary=str(issue.get("summary") or issue.get("reason") or ""),
                    account_id=account_id,
                    object_type="support_issue",
                    object_id=issue.get("issue_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="support_issue_evidence",
                            label=issue.get("issue_type") or "support_issue",
                            ref_id=issue.get("issue_id"),
                            preview=evidence_preview,
                        )
                    ],
                    next_actions=[item.get("action_type") for item in issue.get("suggested_operator_actions", []) if item.get("action_type")],
                    link_tokens=[
                        f"session:{session_id}"
                        for session_id in list((issue.get("related_objects") or {}).get("session_ids") or [])
                        if session_id
                    ]
                    + [
                        f"world_version:{world_version_id}"
                        for world_version_id in list((issue.get("related_objects") or {}).get("world_version_ids") or [])
                        if world_version_id
                    ],
                )
            )
        return entries

    def _governance_trace_entries(
        self,
        governance_snapshot: Dict[str, Any],
        *,
        account_id: str,
        case_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        cases = list(governance_snapshot.get("governance_cases", []))
        if case_id:
            cases = [item for item in cases if item.get("case_id") == case_id]
        for item in cases:
            restriction = item.get("restriction") or {}
            entries.append(
                self._trace_entry(
                    trace_id=f"governance_case::{item['case_id']}",
                    occurred_at=item.get("updated_at"),
                    source_type="governance_case",
                    category="governance",
                    severity="high" if restriction.get("status") == "active" else str(item.get("severity") or "medium"),
                    status=item.get("status"),
                    headline=str(item.get("summary") or item.get("case_id")),
                    summary=f"{item.get('case_type') or '-'} · {item.get('target_type') or '-'}:{item.get('target_id') or '-'}",
                    account_id=account_id,
                    world_version_id=item.get("world_version_id"),
                    case_id=item.get("case_id"),
                    session_id=item.get("session_id"),
                    object_type="governance_case",
                    object_id=item.get("case_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="governance_case_payload",
                            label=item.get("case_type") or "governance_case",
                            ref_id=item.get("case_id"),
                            preview=str(item.get("summary") or item.get("resolution_notes") or "-"),
                        )
                    ],
                    next_actions=list(item.get("recommended_next_actions") or []),
                    link_tokens=[
                        f"case:{item.get('case_id')}" if item.get("case_id") else "",
                        f"world_version:{item.get('world_version_id')}" if item.get("world_version_id") else "",
                        f"session:{item.get('session_id')}" if item.get("session_id") else "",
                    ],
                )
            )
            if restriction:
                entries.append(
                    self._trace_entry(
                        trace_id=f"governance_restriction::{restriction.get('restriction_id') or item.get('case_id')}",
                        occurred_at=restriction.get("applied_at") or item.get("updated_at"),
                        source_type="governance_restriction",
                        category="governance",
                        severity="high" if restriction.get("status") == "active" else "medium",
                        status=restriction.get("status"),
                        headline=str(restriction.get("restriction_type") or "restriction"),
                        summary=str(restriction.get("reason") or ""),
                        account_id=account_id,
                        world_version_id=item.get("world_version_id"),
                        case_id=item.get("case_id"),
                        object_type="governance_restriction",
                        object_id=restriction.get("restriction_id"),
                        evidence_refs=[
                            self._evidence_ref(
                                kind="governance_restriction_payload",
                                label=restriction.get("restriction_type") or "restriction",
                                ref_id=restriction.get("restriction_id") or item.get("case_id"),
                                preview=f"{restriction.get('scope') or '-'} · {restriction.get('status') or '-'} · {restriction.get('reason') or '-'}",
                            )
                        ],
                        next_actions=["review_active_restriction"] if restriction.get("status") == "active" else [],
                        link_tokens=[
                            f"case:{item.get('case_id')}" if item.get("case_id") else "",
                            f"world_version:{item.get('world_version_id')}" if item.get("world_version_id") else "",
                        ],
                    )
                )
        return entries

    def _world_release_trace_entries(self, world_version_id: str, *, account_id: str) -> List[Dict[str, Any]]:
        try:
            version = self.repository.get_world_version(world_version_id)
        except KeyError:
            return []
        history = self.review.world_history(version.world_id)
        status = self.review.world_status(version.world_id)
        entries: List[Dict[str, Any]] = []
        for item in history.get("review_timeline", []):
            if world_version_id not in {item.get("world_version_id"), item.get("published_world_version_id"), item.get("target_world_version_id")}:
                continue
            entries.append(
                self._trace_entry(
                    trace_id=f"review_timeline::{item.get('review_id') or item.get('asset_id')}",
                    occurred_at=item.get("updated_at"),
                    source_type="review_timeline",
                    category="content_release",
                    severity="high" if item.get("status") in {"publish_blocked", "rolled_back"} else "medium",
                    status=item.get("status"),
                    headline=str(item.get("status") or "review"),
                    summary=f"{item.get('world_version_id') or '-'} · decision {item.get('latest_decision') or '-'}",
                    account_id=account_id,
                    world_version_id=item.get("world_version_id"),
                    object_type="review_record",
                    object_id=item.get("review_id") or item.get("asset_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="review_timeline_payload",
                            label=item.get("status") or "review",
                            ref_id=item.get("review_id") or item.get("asset_id"),
                            preview=str(item.get("note_payload") or "-"),
                        )
                    ],
                    next_actions=[],
                    link_tokens=[
                        f"world_version:{item.get('world_version_id')}" if item.get("world_version_id") else "",
                    ],
                )
            )
        for item in status.get("publish_checklist", []):
            entries.append(
                self._trace_entry(
                    trace_id=f"publish_checklist::{version.world_id}:{item.get('key')}",
                    occurred_at=status.get("versions", [{}])[0].get("updated_at") if status.get("versions") else None,
                    source_type="publish_checklist",
                    category="content_release",
                    severity="info" if item.get("ok") else str(item.get("severity") or "medium"),
                    status="ok" if item.get("ok") else "blocked",
                    headline=str(item.get("label") or item.get("key") or "publish_check"),
                    summary=str(item.get("reason") or ""),
                    account_id=account_id,
                    world_version_id=world_version_id,
                    object_type="publish_check",
                    object_id=item.get("key"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="publish_checklist_evidence",
                            label=item.get("label") or item.get("key") or "publish_check",
                            ref_id=item.get("key") or "publish_check",
                            preview=str(item.get("evidence") or "-"),
                        )
                    ],
                    next_actions=[str(item.get("next_action"))] if item.get("next_action") and item.get("next_action") != "none" else [],
                    link_tokens=[f"world_version:{world_version_id}"],
                )
            )
        for item in history.get("rollback_drilldown", []):
            entries.append(
                self._trace_entry(
                    trace_id=f"rollback_drilldown::{item.get('review_id') or item.get('asset_id')}",
                    occurred_at=item.get("updated_at"),
                    source_type="rollback_drilldown",
                    category="content_release",
                    severity="high",
                    status=item.get("status"),
                    headline="rollback",
                    summary=str(item.get("rollback_reason") or "-"),
                    account_id=account_id,
                    world_version_id=item.get("rollback_target_world_version_id") or world_version_id,
                    object_type="rollback_record",
                    object_id=item.get("review_id") or item.get("asset_id"),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="rollback_drilldown_payload",
                            label="rollback",
                            ref_id=item.get("review_id") or item.get("asset_id"),
                            preview=str(item.get("rollback_gate_errors") or "-"),
                        )
                    ],
                    next_actions=["inspect_rollback_target"],
                    link_tokens=[
                        f"world_version:{item.get('rollback_target_world_version_id') or world_version_id}",
                    ],
                )
            )
        return entries

    def _runtime_trace_entries(self, *, account_id: str, world_version_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        receipts = self.observability.list_runtime_receipts(account_id=account_id, limit=max(limit * 4, 50))
        if world_version_id:
            receipts = [item for item in receipts if item.get("world_version_id") == world_version_id]
        entries = []
        for item in receipts[:limit]:
            entries.append(
                self._trace_entry(
                    trace_id=f"runtime_receipt::{item.get('event_id')}",
                    occurred_at=item.get("occurred_at"),
                    source_type="runtime_receipt",
                    category="runtime",
                    severity=str(item.get("severity") or "info"),
                    status=item.get("response_status"),
                    headline=str(item.get("action") or "runtime_receipt"),
                    summary=f"{item.get('surface') or '-'} · {item.get('provider') or '-'}",
                    account_id=account_id,
                    world_version_id=item.get("world_version_id"),
                    session_id=item.get("session_id"),
                    object_type="runtime_receipt",
                    object_id=str(item.get("event_id") or item.get("occurred_at") or ""),
                    evidence_refs=[
                        self._evidence_ref(
                            kind="runtime_receipt_evidence",
                            label=item.get("action") or "runtime_receipt",
                            ref_id=str(item.get("event_id") or item.get("occurred_at") or ""),
                            preview=f"flags={(item.get('incident_flags') or [])} · provider={item.get('selected_provider') or item.get('provider') or '-'}",
                        )
                    ],
                    next_actions=["inspect_runtime_receipt"] if item.get("incident_flags") else [],
                    link_tokens=[
                        f"session:{item.get('session_id')}" if item.get("session_id") else "",
                        f"world_version:{item.get('world_version_id')}" if item.get("world_version_id") else "",
                    ],
                )
            )
        return entries

    def _link_trace_timeline(self, trace_timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        token_map: Dict[str, List[str]] = {}
        for trace in trace_timeline:
            for token in trace.get("_link_tokens", []):
                if not token:
                    continue
                token_map.setdefault(token, []).append(trace["trace_id"])

        linked: List[Dict[str, Any]] = []
        for trace in trace_timeline:
            related_ids = set(trace.get("related_trace_ids", []))
            for token in trace.get("_link_tokens", []):
                for trace_id in token_map.get(token, []):
                    if trace_id != trace["trace_id"]:
                        related_ids.add(trace_id)
            payload = dict(trace)
            payload["related_trace_ids"] = sorted(related_ids)
            payload.pop("_link_tokens", None)
            linked.append(payload)
        return linked

    def _build_evidence_index(self, trace_timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen = set()
        for trace in trace_timeline:
            for ref in trace.get("evidence_refs", []):
                evidence_id = f"{trace['trace_id']}::{ref.get('ref_id')}"
                if evidence_id in seen:
                    continue
                seen.add(evidence_id)
                items.append(
                    self._evidence_item(
                        evidence_id=evidence_id,
                        source_type=trace["source_type"],
                        source_id=str(ref.get("ref_id") or ""),
                        title=str(ref.get("label") or trace.get("headline") or "-"),
                        preview=str(ref.get("preview") or "-"),
                        linked_object_type=trace.get("object_type") or "object",
                        linked_object_id=trace.get("object_id"),
                    )
                )
        return items

    def _investigation_summary(
        self,
        *,
        trace_timeline: List[Dict[str, Any]],
        account_detail: Dict[str, Any],
        governance_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        category_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        for item in trace_timeline:
            category = str(item.get("category") or "unknown")
            severity = str(item.get("severity") or "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return {
            "trace_count": len(trace_timeline),
            "latest_at": trace_timeline[0].get("occurred_at") if trace_timeline else None,
            "category_counts": category_counts,
            "severity_counts": severity_counts,
            "active_restriction_count": int(governance_snapshot.get("restriction_summary", {}).get("active_restriction_count") or 0),
            "open_support_issue_count": int(account_detail.get("support_summary", {}).get("open_issue_count") or 0),
            "billing_retry_attempt_count": int(account_detail.get("lifecycle_history_summary", {}).get("retry_attempt_count") or 0),
            "billing_event_count": int(account_detail.get("lifecycle_history_summary", {}).get("event_count") or 0),
        }

    def investigate_account(
        self,
        *,
        account_id: str,
        world_version_id: Optional[str] = None,
        case_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        account_detail = self.billing.account_detail(account_id=account_id, limit=limit)
        governance_snapshot = self.governance.account_snapshot(account_id=account_id, limit=limit)
        support_issues = account_detail.get("support_issues", [])
        world_version_ids = [world_version_id] if world_version_id else self._world_versions_for_account(account_id)

        trace_timeline = [
            *self._billing_trace_entries(account_detail),
            *self._activity_trace_entries(account_detail),
            *self._support_trace_entries(account_detail),
            *self._governance_trace_entries(governance_snapshot, account_id=account_id, case_id=case_id),
            *self._runtime_trace_entries(account_id=account_id, world_version_id=world_version_id, limit=limit),
        ]
        for wid in world_version_ids[:10]:
            trace_timeline.extend(self._world_release_trace_entries(wid, account_id=account_id))

        if world_version_id:
            trace_timeline = [item for item in trace_timeline if item.get("world_version_id") in {None, world_version_id}]
        if case_id:
            trace_timeline = [item for item in trace_timeline if item.get("case_id") in {None, case_id} or item.get("object_id") == case_id]

        trace_timeline = sorted(
            trace_timeline,
            key=lambda item: (self._parse_timestamp(item.get("occurred_at")), -len(item.get("evidence_refs", []))),
            reverse=True,
        )[:limit]
        trace_timeline = self._link_trace_timeline(trace_timeline)
        evidence_index = self._build_evidence_index(trace_timeline)
        recommended_paths = self._recommended_paths(
            account_detail=account_detail,
            governance_snapshot=governance_snapshot,
            world_traces=trace_timeline,
        )

        return {
            "generated_at": self._utcnow(),
            "filters": {
                "account_id": account_id,
                "world_version_id": world_version_id,
                "case_id": case_id,
                "limit": limit,
            },
            "investigation_summary": self._investigation_summary(
                trace_timeline=trace_timeline,
                account_detail=account_detail,
                governance_snapshot=governance_snapshot,
            ),
            "linked_entities": {
                "account_id": account_detail.get("account_id"),
                "subscription_id": account_detail.get("subscription", {}).get("subscription_id") if account_detail.get("subscription") else None,
                "checkout_session_id": account_detail.get("checkout_session", {}).get("checkout_session_id") if account_detail.get("checkout_session") else None,
                "governance_case_ids": [item.get("case_id") for item in governance_snapshot.get("governance_cases", [])],
                "world_version_ids": world_version_ids,
                "support_issue_ids": [item.get("issue_id") for item in support_issues],
            },
            "trace_timeline": trace_timeline,
            "evidence_index": evidence_index,
            "recommended_paths": recommended_paths,
            "export_refs": {
                "account_id": account_id,
                "world_version_id": world_version_id,
                "case_id": case_id,
            },
        }

    def investigate_case(self, case_id: str, *, limit: int = 50) -> Dict[str, Any]:
        case = self.governance.case_detail(case_id)
        return self.investigate_account(
            account_id=case["account_id"],
            world_version_id=case.get("world_version_id"),
            case_id=case_id,
            limit=limit,
        )

    def investigate_world_version(self, world_version_id: str, *, limit: int = 50) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        return self.investigate_account(
            account_id=version.author_id,
            world_version_id=world_version_id,
            limit=limit,
        )
