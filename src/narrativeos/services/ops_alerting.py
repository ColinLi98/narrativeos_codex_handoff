from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .async_jobs import AsyncJobService
from .billing import BillingService
from .governance import GovernanceService
from .observability import ObservabilityService
from .ops_traceability import OpsTraceabilityService
from .runtime_ops import RuntimeOpsService


class OpsAlertingService:
    VALID_STATUSES = {"open", "acknowledged", "resolved", "suppressed"}

    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: BillingService,
        governance_service: GovernanceService,
        observability_service: ObservabilityService,
        runtime_ops_service: RuntimeOpsService,
        async_job_service: AsyncJobService,
        ops_traceability_service: OpsTraceabilityService,
    ) -> None:
        self.repository = repository
        self.billing = billing_service
        self.governance = governance_service
        self.observability = observability_service
        self.runtime_ops = runtime_ops_service
        self.async_jobs = async_job_service
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

    def _severity_rank(self, value: Optional[str]) -> int:
        return {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "info": 4,
        }.get(str(value or "info"), 5)

    def _payment_required_threshold(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_OPS_ALERT_PAYMENT_REQUIRED_THRESHOLD", "2")))
        except ValueError:
            return 2

    def _runtime_fallback_threshold(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_OPS_ALERT_RUNTIME_FALLBACK_THRESHOLD", "2")))
        except ValueError:
            return 2

    def _failed_job_threshold(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_OPS_ALERT_FAILED_JOB_THRESHOLD", "1")))
        except ValueError:
            return 1

    def _alert_state(self, alert_id: str) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="ops_alert", asset_id=alert_id)
        if not records:
            return {
                "status": "open",
                "reviewer_id": None,
                "updated_at": None,
                "note": None,
            }
        latest = records[0]
        try:
            payload = json.loads(latest.get("notes") or "{}")
        except json.JSONDecodeError:
            payload = {}
        return {
            "status": latest.get("status") or "open",
            "reviewer_id": latest.get("reviewer_id"),
            "updated_at": latest.get("updated_at"),
            "note": payload.get("note"),
        }

    def _known_account_ids(self, *, limit: int = 50) -> List[str]:
        account_ids = set()
        for item in self.repository.list_subscriptions():
            if item.get("account_id"):
                account_ids.add(item["account_id"])
        for event in self.repository.list_analytics_events(limit=max(limit * 8, 200)):
            if event.get("reader_id"):
                account_ids.add(event["reader_id"])
        for item in self.repository.list_world_versions()[: max(limit * 3, 50)]:
            try:
                version = self.repository.get_world_version(item["world_version_id"])
            except KeyError:
                continue
            if version.author_id:
                account_ids.add(version.author_id)
        return sorted(account_ids)[:limit]

    def _alert(
        self,
        *,
        alert_id: str,
        account_id: Optional[str],
        category: str,
        severity: str,
        title: str,
        summary: str,
        detected_at: Optional[str],
        source_type: str,
        source_refs: List[Dict[str, Any]],
        recommended_actions: List[str],
        investigation_ref: Optional[Dict[str, Any]] = None,
        standard_operating_path: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        state = self._alert_state(alert_id)
        return {
            "alert_id": alert_id,
            "account_id": account_id,
            "category": category,
            "severity": severity,
            "status": state["status"],
            "title": title,
            "summary": summary,
            "detected_at": detected_at,
            "source_type": source_type,
            "source_refs": source_refs,
            "recommended_actions": recommended_actions,
            "investigation_ref": dict(investigation_ref or {}),
            "standard_operating_path": list(
                standard_operating_path
                or [
                    "review_alert_summary",
                    "open_investigation_trace",
                    "execute_standard_action",
                    "acknowledge_or_resolve",
                ]
            ),
            "state": state,
        }

    def _runtime_alerts_for_account(self, account_id: str) -> List[Dict[str, Any]]:
        snapshot = self.observability.runtime_incident_snapshot(account_id=account_id, limit=20)
        alerts: List[Dict[str, Any]] = []
        provider_error_count = int((snapshot.get("by_incident_type") or {}).get("provider_error") or 0)
        budget_blocked_count = int((snapshot.get("by_incident_type") or {}).get("budget_blocked") or 0)
        fallback_count = int((snapshot.get("by_incident_type") or {}).get("fallback_used") or 0)

        if provider_error_count:
            latest = list(snapshot.get("latest_backend_errors") or [])
            alerts.append(
                self._alert(
                    alert_id=f"runtime_provider_error::{account_id}",
                    account_id=account_id,
                    category="runtime",
                    severity="high",
                    title="Runtime provider errors require investigation",
                    summary=f"发现 {provider_error_count} 次 provider_error，可能影响 Reader/Author 流程。",
                    detected_at=(latest[0].get("occurred_at") if latest else None),
                    source_type="runtime_receipt",
                    source_refs=[
                        {
                            "kind": "runtime_receipt",
                            "label": item.get("action") or "runtime_receipt",
                            "ref_id": str(item.get("event_id") or item.get("occurred_at") or ""),
                            "preview": f"{item.get('selected_provider') or item.get('provider') or '-'} / {(item.get('incident_flags') or [])}",
                        }
                        for item in latest[:5]
                    ],
                    recommended_actions=["open_investigation", "inspect_runtime_receipts", "review_incident_playbook"],
                    investigation_ref={"account_id": account_id},
                )
            )
        if budget_blocked_count:
            latest = list(snapshot.get("latest_budget_blocks") or [])
            alerts.append(
                self._alert(
                    alert_id=f"runtime_budget_block::{account_id}",
                    account_id=account_id,
                    category="runtime",
                    severity="high",
                    title="Runtime budget blocks are affecting traffic",
                    summary=f"发现 {budget_blocked_count} 次 budget_blocked，可能导致关键路径降级或中断。",
                    detected_at=(latest[0].get("occurred_at") if latest else None),
                    source_type="runtime_receipt",
                    source_refs=[
                        {
                            "kind": "runtime_receipt",
                            "label": item.get("action") or "runtime_receipt",
                            "ref_id": str(item.get("event_id") or item.get("occurred_at") or ""),
                            "preview": f"budget_blocked / {item.get('world_version_id') or '-'} / {item.get('session_id') or '-'}",
                        }
                        for item in latest[:5]
                    ],
                    recommended_actions=["open_investigation", "review_incident_playbook", "inspect_prompt_budget"],
                    investigation_ref={"account_id": account_id},
                )
            )
        if fallback_count >= self._runtime_fallback_threshold():
            latest = list(snapshot.get("latest_fallbacks") or [])
            alerts.append(
                self._alert(
                    alert_id=f"runtime_fallback_rate::{account_id}",
                    account_id=account_id,
                    category="runtime",
                    severity="medium",
                    title="Runtime fallback rate is rising",
                    summary=f"最近 fallback_used 达到 {fallback_count} 次，建议确认 provider 路由是否退化。",
                    detected_at=(latest[0].get("occurred_at") if latest else None),
                    source_type="runtime_receipt",
                    source_refs=[
                        {
                            "kind": "runtime_receipt",
                            "label": item.get("action") or "runtime_receipt",
                            "ref_id": str(item.get("event_id") or item.get("occurred_at") or ""),
                            "preview": f"{item.get('selected_provider') or item.get('provider') or '-'} / fallback_used",
                        }
                        for item in latest[:5]
                    ],
                    recommended_actions=["open_investigation", "inspect_runtime_receipts", "compare_provider_runtime_metrics"],
                    investigation_ref={"account_id": account_id},
                )
            )
        return alerts

    def _support_alerts_for_account(self, account_id: str) -> List[Dict[str, Any]]:
        lookup = self.billing.support_issue_lookup(account_id=account_id, limit=12)
        alerts: List[Dict[str, Any]] = []
        for issue in lookup.get("support_issues", []):
            related_objects = dict(issue.get("related_objects") or {})
            world_version_id = next(
                (
                    item
                    for item in list(related_objects.get("world_version_ids") or [])
                    if item
                ),
                None,
            )
            alerts.append(
                self._alert(
                    alert_id=f"support_issue::{account_id}::{issue['issue_id']}",
                    account_id=account_id,
                    category="support",
                    severity=str(issue.get("severity") or "medium"),
                    title=str(issue.get("title") or issue.get("issue_type") or "support_issue"),
                    summary=str(issue.get("summary") or ""),
                    detected_at=issue.get("detected_at"),
                    source_type="support_issue",
                    source_refs=[
                        {
                            "kind": "support_issue",
                            "label": issue.get("issue_type") or "support_issue",
                            "ref_id": issue.get("issue_id"),
                            "preview": str(issue.get("reason") or issue.get("summary") or "-"),
                        }
                    ],
                    recommended_actions=[
                        "open_investigation",
                        *[
                            item.get("action_type")
                            for item in issue.get("suggested_operator_actions", [])
                            if item.get("action_type")
                        ],
                        "escalate_to_governance",
                    ],
                    investigation_ref={
                        "account_id": account_id,
                        "world_version_id": world_version_id,
                    },
                )
            )
        return alerts

    def _governance_alerts_for_account(self, account_id: str) -> List[Dict[str, Any]]:
        snapshot = self.governance.account_snapshot(account_id=account_id, limit=12)
        alerts: List[Dict[str, Any]] = []
        for case in snapshot.get("governance_cases", []):
            restriction = case.get("restriction") or {}
            if case.get("status") not in {"open", "in_review", "escalated"} and restriction.get("status") != "active":
                continue
            severity = "high" if restriction.get("status") == "active" else str(case.get("severity") or "medium")
            alerts.append(
                self._alert(
                    alert_id=f"governance_case::{account_id}::{case['case_id']}",
                    account_id=account_id,
                    category="governance",
                    severity=severity,
                    title=str(case.get("summary") or case.get("case_id")),
                    summary=f"{case.get('case_type') or '-'} · {case.get('status') or '-'} · {restriction.get('restriction_type') or 'no_active_restriction'}",
                    detected_at=case.get("updated_at"),
                    source_type="governance_case",
                    source_refs=[
                        {
                            "kind": "governance_case",
                            "label": case.get("case_type") or "governance_case",
                            "ref_id": case.get("case_id"),
                            "preview": str(case.get("resolution_notes") or case.get("summary") or "-"),
                        }
                    ]
                    + (
                        [
                            {
                                "kind": "governance_restriction",
                                "label": restriction.get("restriction_type") or "restriction",
                                "ref_id": restriction.get("restriction_id"),
                                "preview": f"{restriction.get('status') or '-'} / {restriction.get('reason') or '-'}",
                            }
                        ]
                        if restriction
                        else []
                    ),
                    recommended_actions=["open_investigation", "review_governance_case", "update_case_status"],
                    investigation_ref={
                        "account_id": account_id,
                        "world_version_id": case.get("world_version_id"),
                        "case_id": case.get("case_id"),
                    },
                )
            )
        return alerts

    def _async_job_alerts(self) -> List[Dict[str, Any]]:
        snapshot = self.async_jobs.incident_snapshot(limit=12)
        failed_count = int(snapshot.get("failed_count") or 0)
        stale_count = int(snapshot.get("stale_running_count") or 0)
        if failed_count < self._failed_job_threshold() and stale_count == 0 and snapshot.get("status") == "healthy":
            return []
        severity = "high" if failed_count >= self._failed_job_threshold() or stale_count > 0 else "medium"
        source_refs = []
        for job in list(snapshot.get("failed_jobs") or [])[:5] + list(snapshot.get("stale_running_jobs") or [])[:5]:
            source_refs.append(
                {
                    "kind": "async_job",
                    "label": job.get("job_type") or "async_job",
                    "ref_id": job.get("job_id"),
                    "preview": f"{job.get('status') or '-'} / {job.get('lease_status') or '-'} / {job.get('error') or '-'}",
                }
            )
        return [
            self._alert(
                alert_id="async_jobs::global",
                account_id=None,
                category="async_jobs",
                severity=severity,
                title="Async job incident queue requires operator attention",
                summary=(
                    f"failed {failed_count} · queued {snapshot.get('queued_count') or 0} · "
                    f"stale {stale_count} · recoverable {snapshot.get('recoverable_count') or 0}"
                ),
                detected_at=snapshot.get("generated_at"),
                source_type="async_job_incident",
                source_refs=source_refs,
                recommended_actions=["review_async_incidents", "recover_incidents", "retry_failed_jobs"],
                investigation_ref={},
            )
        ]

    def _all_alerts(self, *, account_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        account_ids = [account_id] if account_id else self._known_account_ids(limit=limit)
        for item in account_ids:
            alerts.extend(self._runtime_alerts_for_account(item))
            alerts.extend(self._support_alerts_for_account(item))
            alerts.extend(self._governance_alerts_for_account(item))
        alerts.extend(self._async_job_alerts())
        return alerts

    def _filter_alerts(
        self,
        alerts: List[Dict[str, Any]],
        *,
        status_filter: str,
        severity: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        filtered = alerts
        if severity:
            filtered = [item for item in filtered if item.get("severity") == severity]
        if status_filter == "open":
            filtered = [item for item in filtered if item.get("status") == "open"]
        elif status_filter == "actionable":
            filtered = [item for item in filtered if item.get("status") not in {"resolved", "suppressed"}]
        filtered.sort(
            key=lambda item: (
                self._severity_rank(item.get("severity")),
                self._parse_timestamp(item.get("detected_at")),
            )
        )
        return filtered[:limit]

    def _summary(self, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_category: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for item in alerts:
            category = str(item.get("category") or "unknown")
            severity = str(item.get("severity") or "unknown")
            status = str(item.get("status") or "unknown")
            by_category[category] = by_category.get(category, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "total_alert_count": len(alerts),
            "actionable_alert_count": sum(1 for item in alerts if item.get("status") not in {"resolved", "suppressed"}),
            "by_category": by_category,
            "by_severity": by_severity,
            "by_status": by_status,
            "latest_detected_at": alerts[0].get("detected_at") if alerts else None,
        }

    def list_alerts(
        self,
        *,
        account_id: Optional[str] = None,
        status_filter: str = "actionable",
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        alerts = self._filter_alerts(
            self._all_alerts(account_id=account_id, limit=max(limit, 10)),
            status_filter=status_filter,
            severity=severity,
            limit=limit,
        )
        return {
            "generated_at": self._utcnow(),
            "filters": {
                "account_id": account_id,
                "status_filter": status_filter,
                "severity": severity,
                "limit": limit,
            },
            "summary": self._summary(alerts),
            "alerts": alerts,
        }

    def _build_alert_detail(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        investigation_ref = dict(alert.get("investigation_ref") or {})
        account_id = alert.get("account_id")
        category = alert.get("category")
        detail: Dict[str, Any] = {
            "alert": alert,
            "runbook": {},
            "standard_response_bundle": {},
            "investigation_bundle": None,
        }
        if account_id:
            try:
                detail["investigation_bundle"] = self.traceability.investigate_account(
                    account_id=account_id,
                    world_version_id=investigation_ref.get("world_version_id"),
                    case_id=investigation_ref.get("case_id"),
                    limit=25,
                )
            except KeyError:
                detail["investigation_bundle"] = None
        if category == "runtime":
            detail["runbook"] = self.runtime_ops.build_incident_playbook(account_id=account_id)
        elif category == "support":
            lookup = self.billing.support_issue_lookup(account_id=account_id, limit=20) if account_id else {}
            issue_id = alert["alert_id"].split("::", 2)[-1]
            issue = next((item for item in lookup.get("support_issues", []) if item.get("issue_id") == issue_id), None)
            detail["standard_response_bundle"] = {
                "support_issue": issue,
                "support_tooling": lookup.get("support_tooling", {}),
                "recommended_actions": (
                    [item.get("action_type") for item in issue.get("suggested_operator_actions", []) if item.get("action_type")]
                    if issue
                    else []
                ),
            }
        elif category == "governance":
            case_id = investigation_ref.get("case_id") or alert["alert_id"].split("::", 2)[-1]
            try:
                detail["standard_response_bundle"] = self.governance.case_detail(case_id)
            except KeyError:
                detail["standard_response_bundle"] = {}
        elif category == "async_jobs":
            detail["runbook"] = {
                "incident_snapshot": self.async_jobs.incident_snapshot(limit=20),
                "standard_actions": ["recover_incidents", "retry_failed_jobs", "acknowledge_alert"],
            }
        return detail

    def alert_detail(self, alert_id: str, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        alerts = self._all_alerts(account_id=account_id, limit=50)
        alert = next((item for item in alerts if item.get("alert_id") == alert_id), None)
        if alert is None:
            raise KeyError(f"unknown_alert:{alert_id}")
        detail = self._build_alert_detail(alert)
        detail["generated_at"] = self._utcnow()
        return detail

    def update_alert_status(
        self,
        alert_id: str,
        *,
        status: str,
        reviewer_id: Optional[str] = None,
        note: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError("invalid_alert_status")
        detail = self.alert_detail(alert_id, account_id=account_id)
        alert = dict(detail["alert"])
        self.repository.save_review_record(
            {
                "asset_type": "ops_alert",
                "asset_id": alert_id,
                "status": status,
                "reviewer_id": reviewer_id,
                "risk_rating": alert.get("severity"),
                "notes": json.dumps(
                    {
                        "note": note,
                        "account_id": alert.get("account_id"),
                        "category": alert.get("category"),
                        "source_type": alert.get("source_type"),
                        "recommended_actions": alert.get("recommended_actions"),
                        "investigation_ref": alert.get("investigation_ref"),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return self.alert_detail(alert_id, account_id=account_id)
