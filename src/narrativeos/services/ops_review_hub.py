from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .billing import BillingService
from .commercial_support import CommercialSupportService
from .customer_campaigns import CustomerCampaignService
from .governance import GovernanceService
from .ops_alerting import OpsAlertingService
from .ops_quality_projection import OpsQualityProjectionService
from .review import ReviewService


VALID_REVIEW_ITEM_STATUSES = {
    "new",
    "triaged",
    "in_review",
    "needs_changes",
    "approved",
    "blocked",
    "resolved",
    "dismissed",
}

VALID_REVIEW_ITEM_DECISIONS = {
    "approve": "approved",
    "needs_changes": "needs_changes",
    "block": "blocked",
    "resolve": "resolved",
    "dismiss": "dismissed",
}

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
QUEUE_ORDER = {"content_release": 0, "governance": 1, "runtime": 2, "support": 3}


class OpsReviewHubService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        review_service: ReviewService,
        governance_service: GovernanceService,
        alerting_service: OpsAlertingService,
        billing_service: BillingService,
        commercial_support_service: CommercialSupportService,
        quality_projection_service: OpsQualityProjectionService,
        customer_campaign_service: CustomerCampaignService,
    ) -> None:
        self.repository = repository
        self.review = review_service
        self.governance = governance_service
        self.alerting = alerting_service
        self.billing = billing_service
        self.commercial_support = commercial_support_service
        self.quality_projection = quality_projection_service
        self.customer_campaigns = customer_campaign_service

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

    def _serialize_timestamp(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _severity_rank(self, severity: Optional[str]) -> int:
        return SEVERITY_RANK.get(str(severity or "info"), 5)

    def _queue_rank(self, queue: Optional[str]) -> int:
        return QUEUE_ORDER.get(str(queue or ""), 99)

    def _priority_for_item(self, *, queue: str, severity: str, due_at: Optional[str], source_status: str) -> int:
        priority = self._queue_rank(queue) * 100 + self._severity_rank(severity) * 10
        if source_status == "blocked":
            priority -= 5
        due_dt = self._parse_timestamp(due_at)
        now = datetime.now(timezone.utc)
        if due_at and due_dt <= now:
            priority -= 8
        elif due_at and due_dt <= now + timedelta(hours=24):
            priority -= 4
        return max(0, priority)

    def _sla_bucket(self, *, due_at: Optional[str], status: str) -> str:
        if status in {"resolved", "dismissed"}:
            return "closed"
        if not due_at:
            return "backlog"
        due_dt = self._parse_timestamp(due_at)
        now = datetime.now(timezone.utc)
        if due_dt <= now:
            return "overdue"
        if due_dt <= now + timedelta(hours=24):
            return "due_soon"
        return "scheduled"

    def _source_key(self, item: Dict[str, Any]) -> Tuple[str, str]:
        return str(item.get("source_type") or ""), str(item.get("source_id") or "")

    def _link(self, *, kind: str, entity_id: Optional[str], label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        value = str(entity_id or "").strip()
        if not value:
            return None
        return {
            "kind": kind,
            "id": value,
            "label": str(label or value),
        }

    def _merge_overlay(self, *, source_item: Dict[str, Any], overlay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not overlay:
            return source_item
        merged = dict(source_item)
        source_status = str(source_item.get("status") or "")
        if source_status not in {"resolved", "dismissed"}:
            merged["status"] = overlay.get("status") or source_status
        merged["owner_id"] = overlay.get("owner_id") or source_item.get("owner_id")
        merged["reviewer_id"] = overlay.get("reviewer_id") or source_item.get("reviewer_id")
        merged["due_at"] = overlay.get("due_at") or source_item.get("due_at")
        merged["priority"] = int(overlay.get("priority", source_item.get("priority", 100)) or source_item.get("priority", 100))
        return merged

    def _support_candidate_account_ids(self) -> List[str]:
        account_ids = {
            str(item.get("account_id") or "").strip()
            for item in self.repository.list_subscriptions()
            if str(item.get("account_id") or "").strip()
        }
        account_ids.update(
            str(item.get("author_id") or "").strip()
            for item in self.repository.list_world_versions(status="draft")
            if str(item.get("author_id") or "").strip()
        )
        account_ids.update(
            str(item.get("author_id") or "").strip()
            for item in self.repository.list_world_versions(status="submitted")
            if str(item.get("author_id") or "").strip()
        )
        return sorted(account_ids)

    def _author_work_status_to_item_status(self, work_status: str) -> str:
        return {
            "draft": "new",
            "review_ready": "triaged",
            "submitted": "in_review",
            "approved": "approved",
            "needs_changes": "needs_changes",
        }.get(work_status, "new")

    def _build_author_work_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        works = self.repository.list_author_works(limit=500)
        for work in works:
            chapters = self.repository.list_author_work_chapters(work_id=work["work_id"])
            diagnostics = dict(work.get("diagnostics_summary_json") or {})
            has_reviewable_content = bool(chapters) and bool(diagnostics)
            if work.get("status") not in {"review_ready", "submitted", "approved", "needs_changes"} and not has_reviewable_content:
                continue
            try:
                version = self.repository.get_world_version(str(work.get("world_version_id") or ""))
                world_id = version.world_id
            except KeyError:
                world_id = None
            evaluation_summary = dict(diagnostics.get("evaluation_summary") or {})
            latest_decision = diagnostics.get("latest_decision")
            item_status = self._author_work_status_to_item_status(str(work.get("status") or "draft"))
            if float(evaluation_summary.get("block_rate", 0.0) or 0.0) > 0.0:
                item_status = "blocked"
            severity = (
                "high"
                if item_status in {"blocked", "needs_changes"}
                else ("medium" if item_status == "in_review" else "low")
            )
            due_at = (self._parse_timestamp(work.get("updated_at")) + timedelta(hours=24)).isoformat() if work.get("updated_at") else None
            item = {
                "review_item_id": f"ops_review::author_work::{work['work_id']}",
                "source_type": "author_work",
                "source_id": str(work["work_id"]),
                "queue": "content_release",
                "status": item_status,
                "severity": severity,
                "priority": self._priority_for_item(queue="content_release", severity=severity, due_at=due_at, source_status=item_status),
                "owner_id": None,
                "reviewer_id": None,
                "account_id": work.get("account_id"),
                "world_id": world_id,
                "world_version_id": work.get("world_version_id"),
                "headline": f"{work.get('title') or work['work_id']} · 作品稿审阅",
                "summary": f"chapters {work.get('chapter_count', 0)}/{work.get('target_chapter_count', 0)} · decision {latest_decision or '-'}",
                "recommended_action": "inspect_author_work" if item_status in {"in_review", "blocked", "needs_changes"} else "open_release_workspace",
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=item_status),
                "allowed_actions": ["assign_to_me", "mark_triaged", "mark_in_review", "approve", "needs_changes", "block", "open_account_workspace", "open_release_workspace"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=work.get("account_id")),
                        self._link(kind="world_version", entity_id=work.get("world_version_id")),
                        self._link(kind="author_work", entity_id=work.get("work_id")),
                    ]
                    if item
                ],
                "source_updated_at": work.get("updated_at"),
                "source_payload": {
                    "work": work,
                    "chapters": [
                        {
                            "chapter_index": chapter.get("chapter_index"),
                            "chapter_title": chapter.get("chapter_title"),
                            "status": chapter.get("status"),
                            "source_type": chapter.get("source_type"),
                            "summary": chapter.get("summary"),
                        }
                        for chapter in chapters
                    ],
                    "diagnostics": diagnostics,
                },
            }
            items.append(item)
        return items

    def _build_release_items(self, *, covered_world_version_ids: Optional[set[str]] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for review_item in self.review.queue():
            note_payload = review_item.get("notes")
            latest_decision = review_item.get("latest_decision")
            gate_errors = list(review_item.get("publish_gate_errors") or [])
            status = "new"
            if gate_errors or latest_decision == "block":
                status = "blocked"
            elif latest_decision == "rewrite":
                status = "needs_changes"
            world_version_id = str(review_item.get("asset_id") or "")
            if covered_world_version_ids and world_version_id in covered_world_version_ids:
                continue
            try:
                version = self.repository.get_world_version(world_version_id)
                account_id = version.author_id
                world_id = version.world_id
                title = (version.worldpack_json or {}).get("title") or world_version_id
            except KeyError:
                account_id = None
                world_id = None
                title = world_version_id
            severity = "high" if gate_errors else ("medium" if latest_decision != "pass" else "low")
            due_at = (self._parse_timestamp(review_item.get("updated_at")) + timedelta(hours=24)).isoformat() if review_item.get("updated_at") else None
            item = {
                "review_item_id": f"ops_review::world_version_review::{world_version_id}",
                "source_type": "world_version_review",
                "source_id": world_version_id,
                "queue": "content_release",
                "status": status,
                "severity": severity,
                "priority": self._priority_for_item(
                    queue="content_release",
                    severity=severity,
                    due_at=due_at,
                    source_status=status,
                ),
                "owner_id": None,
                "reviewer_id": review_item.get("reviewer_id"),
                "account_id": account_id,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "headline": f"{title} · 发布审阅",
                "summary": f"decision {latest_decision or '-'} · gate {(gate_errors or ['none'])[0]}",
                "recommended_action": "inspect_publish_blockers" if gate_errors else ("review_candidate" if latest_decision != "pass" else "publish_candidate"),
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=status),
                "allowed_actions": ["assign_to_me", "mark_triaged", "mark_in_review", "approve", "needs_changes", "block", "open_release_workspace", "open_account_workspace"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=account_id),
                        self._link(kind="world", entity_id=world_id),
                        self._link(kind="world_version", entity_id=world_version_id),
                    ]
                    if item
                ],
                "source_updated_at": review_item.get("updated_at"),
                "source_payload": {
                    "review_record": review_item,
                    "publish_gate_errors": gate_errors,
                    "top_failing_packs": review_item.get("top_failing_packs", []),
                },
            }
            items.append(item)
        return items

    def _build_governance_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cases = list((self.governance.list_cases(limit=200) or {}).get("cases") or [])
        for case in cases:
            source_status = {
                "open": "new",
                "in_review": "in_review",
                "escalated": "in_review",
                "resolved": "resolved",
                "dismissed": "dismissed",
            }.get(str(case.get("status") or "open"), "new")
            owner_id = (case.get("workflow_summary") or {}).get("owner_id") or case.get("owner_id")
            due_at = case.get("due_at") or (case.get("workflow_summary") or {}).get("due_at")
            severity = str(case.get("severity") or "medium")
            item = {
                "review_item_id": f"ops_review::governance_case::{case['case_id']}",
                "source_type": "governance_case",
                "source_id": str(case["case_id"]),
                "queue": "governance",
                "status": source_status,
                "severity": severity,
                "priority": self._priority_for_item(queue="governance", severity=severity, due_at=due_at, source_status=source_status),
                "owner_id": owner_id,
                "reviewer_id": case.get("reviewer_id"),
                "account_id": case.get("account_id"),
                "world_id": case.get("world_id"),
                "world_version_id": case.get("world_version_id"),
                "headline": str(case.get("summary") or case.get("case_id") or "governance_case"),
                "summary": str(case.get("description") or case.get("resolution_notes") or case.get("case_type") or ""),
                "recommended_action": ((case.get("recommended_next_actions") or [])[:1] or [case.get("recommended_action") or "review_governance_case"])[0],
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=source_status),
                "allowed_actions": ["assign_to_me", "mark_in_review", "resolve", "dismiss", "open_governance_case", "open_account_workspace", "open_investigation"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=case.get("account_id")),
                        self._link(kind="world", entity_id=case.get("world_id")),
                        self._link(kind="world_version", entity_id=case.get("world_version_id")),
                        self._link(kind="case", entity_id=case.get("case_id")),
                    ]
                    if item
                ],
                "source_updated_at": case.get("updated_at"),
                "source_payload": case,
            }
            items.append(item)

            restriction = dict(case.get("restriction") or {})
            if restriction:
                restriction_status = {
                    "active": "blocked",
                    "released": "resolved",
                }.get(str(restriction.get("status") or "active"), "blocked")
                applied_at = restriction.get("applied_at") or restriction.get("released_at")
                restriction_due_at = restriction.get("expires_at")
                restriction_item = {
                    "review_item_id": f"ops_review::governance_restriction::{restriction.get('restriction_id') or case['case_id']}",
                    "source_type": "governance_restriction",
                    "source_id": str(restriction.get("restriction_id") or case["case_id"]),
                    "queue": "governance",
                    "status": restriction_status,
                    "severity": severity,
                    "priority": self._priority_for_item(queue="governance", severity=severity, due_at=restriction_due_at, source_status=restriction_status),
                    "owner_id": owner_id,
                    "reviewer_id": case.get("reviewer_id"),
                    "account_id": case.get("account_id"),
                    "world_id": case.get("world_id"),
                    "world_version_id": case.get("world_version_id"),
                    "headline": f"{restriction.get('restriction_type') or 'restriction'} · {case.get('summary') or case.get('case_id')}",
                    "summary": str(restriction.get("restriction_reason") or case.get("summary") or ""),
                    "recommended_action": "release_restriction" if restriction_status == "blocked" else "review_governance_case",
                    "due_at": restriction_due_at,
                    "sla_bucket": self._sla_bucket(due_at=restriction_due_at, status=restriction_status),
                    "allowed_actions": ["open_governance_case", "open_account_workspace"] + (["resolve"] if restriction_status == "blocked" else []),
                    "linked_entities": [
                        item
                        for item in [
                            self._link(kind="account", entity_id=case.get("account_id")),
                            self._link(kind="world", entity_id=case.get("world_id")),
                            self._link(kind="world_version", entity_id=case.get("world_version_id")),
                            self._link(kind="case", entity_id=case.get("case_id")),
                            self._link(kind="restriction", entity_id=restriction.get("restriction_id") or case.get("case_id")),
                        ]
                        if item
                    ],
                    "source_updated_at": applied_at,
                    "source_payload": {
                        "case": case,
                        "restriction": restriction,
                    },
                }
                items.append(restriction_item)
        return items

    def _queue_for_alert(self, alert: Dict[str, Any]) -> str:
        category = str(alert.get("category") or "")
        if category == "governance":
            return "governance"
        if category == "support":
            return "support"
        return "runtime"

    def _build_alert_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for alert in list((self.alerting.list_alerts(status_filter="all", limit=200) or {}).get("alerts") or []):
            queue = self._queue_for_alert(alert)
            alert_status = str(alert.get("status") or "open")
            source_status = {
                "resolved": "resolved",
                "suppressed": "dismissed",
                "acknowledged": "triaged",
                "open": "new",
            }.get(alert_status, "new")
            severity = str(alert.get("severity") or "medium")
            investigation_ref = dict(alert.get("investigation_ref") or {})
            due_at = (self._parse_timestamp(alert.get("detected_at")) + timedelta(hours=12)).isoformat() if alert.get("detected_at") else None
            item = {
                "review_item_id": f"ops_review::active_alert::{alert['alert_id']}",
                "source_type": "active_alert",
                "source_id": str(alert["alert_id"]),
                "queue": queue,
                "status": source_status,
                "severity": severity,
                "priority": self._priority_for_item(queue=queue, severity=severity, due_at=due_at, source_status=source_status),
                "owner_id": None,
                "reviewer_id": None,
                "account_id": alert.get("account_id") or investigation_ref.get("account_id"),
                "world_id": investigation_ref.get("world_id"),
                "world_version_id": investigation_ref.get("world_version_id"),
                "headline": str(alert.get("title") or alert.get("alert_id") or "alert"),
                "summary": str(alert.get("summary") or ""),
                "recommended_action": ((alert.get("recommended_actions") or [])[:1] or ["open_investigation"])[0],
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=source_status),
                "allowed_actions": ["assign_to_me", "mark_triaged", "mark_in_review", "resolve", "dismiss", "open_investigation", "open_account_workspace"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=alert.get("account_id") or investigation_ref.get("account_id")),
                        self._link(kind="world_version", entity_id=investigation_ref.get("world_version_id")),
                        self._link(kind="case", entity_id=investigation_ref.get("case_id")),
                        self._link(kind="alert", entity_id=alert.get("alert_id")),
                    ]
                    if item
                ],
                "source_updated_at": alert.get("detected_at"),
                "source_payload": alert,
            }
            items.append(item)
        return items

    def _build_support_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for account_id in self._support_candidate_account_ids():
            lookup = self.billing.support_issue_lookup(account_id=account_id, limit=20)
            for issue in list(lookup.get("support_issues") or []):
                severity = str(issue.get("severity") or "medium")
                detected_at = issue.get("detected_at")
                due_at = (self._parse_timestamp(detected_at) + timedelta(hours=24)).isoformat() if detected_at else None
                related_objects = dict(issue.get("related_objects") or {})
                item = {
                    "review_item_id": f"ops_review::support_issue::{issue['issue_id']}",
                    "source_type": "support_issue",
                    "source_id": str(issue["issue_id"]),
                    "queue": "support",
                    "status": "new",
                    "severity": severity,
                    "priority": self._priority_for_item(queue="support", severity=severity, due_at=due_at, source_status="new"),
                    "owner_id": None,
                    "reviewer_id": None,
                    "account_id": account_id,
                    "world_id": (related_objects.get("world_ids") or [None])[0],
                    "world_version_id": (related_objects.get("world_version_ids") or [None])[0],
                    "headline": str(issue.get("title") or issue.get("issue_id") or "support_issue"),
                    "summary": str(issue.get("summary") or issue.get("reason") or ""),
                    "recommended_action": (((issue.get("suggested_operator_actions") or [])[:1] or [{"action_type": "open_account_workspace"}])[0]).get("action_type"),
                    "due_at": due_at,
                    "sla_bucket": self._sla_bucket(due_at=due_at, status="new"),
                    "allowed_actions": ["assign_to_me", "mark_triaged", "mark_in_review", "resolve", "dismiss", "open_account_workspace", "open_investigation", "escalate_to_governance"],
                    "linked_entities": [
                        item
                        for item in [
                            self._link(kind="account", entity_id=account_id),
                            self._link(kind="world_version", entity_id=(related_objects.get("world_version_ids") or [None])[0]),
                            self._link(kind="session", entity_id=(related_objects.get("session_ids") or [None])[0]),
                            self._link(kind="support_issue", entity_id=issue.get("issue_id")),
                        ]
                        if item
                    ],
                    "source_updated_at": detected_at,
                    "source_payload": issue,
                }
                items.append(item)
        return items

    def _build_quality_review_case_items(self) -> List[Dict[str, Any]]:
        return self.quality_projection.build_quality_review_case_items()

    def _build_campaign_review_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for submission in self.repository.list_campaign_review_submissions(limit=500):
            if str(submission.get("status") or "") not in {"submitted", "in_review"}:
                continue
            try:
                bundle = self.customer_campaigns.campaign_detail(
                    account_id=self.repository.get_campaign(str(submission.get("campaign_id") or ""))["account_id"],
                    campaign_id=str(submission.get("campaign_id") or ""),
                )
            except Exception:
                continue
            campaign = dict(bundle.get("campaign") or {})
            review_case = dict(bundle.get("review_case") or {})
            status = "in_review" if str(submission.get("status") or "") == "in_review" else "new"
            due_at = (self._parse_timestamp(submission.get("submitted_at")) + timedelta(hours=24)).isoformat() if submission.get("submitted_at") else None
            item = {
                "review_item_id": f"ops_review::campaign_review_case::{submission['submission_id']}",
                "source_type": "campaign_review_case",
                "source_id": str(submission["submission_id"]),
                "queue": "content_release",
                "status": status,
                "severity": "medium",
                "priority": self._priority_for_item(queue="content_release", severity="medium", due_at=due_at, source_status=status),
                "owner_id": review_case.get("owner_id"),
                "reviewer_id": submission.get("reviewer_id"),
                "account_id": campaign.get("account_id"),
                "world_id": None,
                "world_version_id": None,
                "headline": f"{campaign.get('title') or campaign.get('campaign_id')} · Campaign Activation",
                "summary": f"ICP {campaign.get('target_icp_vertical') or '-'} · channels {' / '.join(campaign.get('selected_channels_json') or []) or '-'}",
                "recommended_action": "review_campaign_activation",
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=status),
                "allowed_actions": ["assign_to_me", "mark_in_review", "approve", "needs_changes", "block", "open_account_workspace", "open_investigation"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=campaign.get("account_id")),
                        self._link(kind="campaign", entity_id=campaign.get("campaign_id")),
                        self._link(kind="review_case", entity_id=review_case.get("case_id")),
                    ]
                    if item
                ],
                "source_updated_at": submission.get("updated_at"),
                "source_payload": {
                    "campaign": campaign,
                    "proof_bundles": bundle.get("proof_bundles") or [],
                    "channel_targets": bundle.get("channel_targets") or [],
                    "submission": submission,
                    "review_case": review_case,
                },
            }
            items.append(item)
        return items

    def _review_item_fallback_chapter_index(self, payload: Dict[str, Any], fallback: int) -> int:
        for key in ("chapter_index", "turn_index"):
            value = payload.get(key)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
        chapter_id = str(payload.get("chapter_id") or "")
        if chapter_id:
            suffix = chapter_id.rsplit("_", 1)[-1]
            try:
                return int(suffix)
            except ValueError:
                pass
        return fallback

    def _synthetic_work_chapters_from_simulation(self, simulation_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        chapter_trace = list(simulation_report.get("chapter_trace") or [])
        chapter_evaluations = list(simulation_report.get("chapter_evaluations") or [])
        evaluation_by_index: Dict[int, Dict[str, Any]] = {}
        for fallback_index, evaluation in enumerate(chapter_evaluations, start=1):
            payload = dict(evaluation or {})
            chapter_index = self._review_item_fallback_chapter_index(payload, fallback_index)
            evaluation_by_index[chapter_index] = payload

        chapters: List[Dict[str, Any]] = []
        for fallback_index, trace in enumerate(chapter_trace, start=1):
            payload = dict(trace or {})
            chapter_index = self._review_item_fallback_chapter_index(payload, fallback_index)
            evaluation = evaluation_by_index.get(chapter_index, {})
            trace_evaluation = dict(payload.get("evaluation") or {})
            issue_codes = list(trace_evaluation.get("issue_codes") or [])
            if not issue_codes:
                issue_codes = [
                    str(issue.get("issue_code") or "")
                    for issue in list(evaluation.get("issues") or [])
                    if str(issue.get("issue_code") or "").strip()
                ]
            decision = (
                str(trace_evaluation.get("decision") or "")
                or str(dict(evaluation.get("decision") or {}).get("decision") or "")
                or str(simulation_report.get("latest_decision") or "rewrite")
            )
            overall_score = trace_evaluation.get("overall_score")
            if overall_score is None:
                overall_score = dict(evaluation.get("scores") or {}).get("overall_score")
            chapters.append(
                {
                    "chapter_index": chapter_index,
                    "chapter_title": str(payload.get("chapter_title") or f"第 {chapter_index} 章"),
                    "status": decision or "rewrite",
                    "source_type": "world_version_review",
                    "summary": str(payload.get("chosen_event_title") or payload.get("scene_function") or ""),
                    "body": str(payload.get("body_excerpt") or ""),
                    "choices": list(payload.get("choices_preview") or []),
                    "chapter_task_json": dict(payload.get("chapter_task") or {}),
                    "diagnostic_summary_json": {
                        "decision": {"decision": decision or "rewrite"},
                        "scores": {"overall_score": overall_score},
                        "issues": [{"issue_code": code} for code in issue_codes],
                    },
                    "latest_diagnostic_summary": {
                        "decision": decision or "rewrite",
                        "overall_score": overall_score,
                        "issue_codes": issue_codes,
                    },
                }
            )
        return chapters

    def _synthetic_review_work_from_world_version(self, *, item: Dict[str, Any]) -> Dict[str, Any]:
        world_version_id = str(item.get("world_version_id") or item.get("source_id") or "")
        version = self.repository.get_world_version(world_version_id)
        worldpack = dict(version.worldpack_json or {})
        manifest = dict(worldpack.get("manifest") or {})
        simulation_report = dict(version.simulation_report_json or {})
        validation_report = dict(version.validation_report_json or {})
        chapters = self._synthetic_work_chapters_from_simulation(simulation_report)
        completed_chapters = int(simulation_report.get("completed_chapters", 0) or 0)
        chapter_budget = int(simulation_report.get("chapter_budget", 0) or 0)
        latest_revision = {
            "revision_id": f"world_version_review::{world_version_id}",
            "revision_type": "submitted_world_version",
            "created_at": self._serialize_timestamp(getattr(version, "updated_at", None)),
            "snapshot_json": {
                "validation_report": validation_report,
                "simulation_report": simulation_report,
            },
        }
        return {
            "work_id": f"world_version_review::{world_version_id}",
            "root_work_id": None,
            "branch_id": None,
            "is_active_line": False,
            "account_id": getattr(version, "author_id", None),
            "world_version_id": world_version_id,
            "title": str(worldpack.get("title") or world_version_id),
            "status": str(getattr(version, "status", None) or item.get("status") or "submitted"),
            "chapter_count": max(completed_chapters, len(chapters)),
            "target_chapter_count": max(chapter_budget, completed_chapters, len(chapters)),
            "active_chapter_index": chapters[-1]["chapter_index"] if chapters else None,
            "chapters": chapters,
            "revisions": [latest_revision],
            "latest_revision": latest_revision,
            "diagnostics_summary_json": simulation_report,
            "diagnostics_summary": simulation_report,
            "validation_report_json": validation_report,
            "hard_constraint_status": "clear",
            "blocking_dimension": "",
            "window_breach_kind": "",
            "ready_for_validation": True,
            "content_quality_repair_workbench": dict(simulation_report.get("content_quality_repair_workbench") or {}),
            "branch_family": [],
            "source_mode": "world_version_review_fallback",
            "source_summary": {
                "world_id": getattr(version, "world_id", None),
                "review_item_id": item.get("review_item_id"),
                "author_id": getattr(version, "author_id", None),
                "latest_decision": simulation_report.get("latest_decision"),
                "stop_reason": simulation_report.get("stop_reason"),
                "publish_gate_errors": list((dict(item.get("source_payload") or {}).get("publish_gate_errors") or [])),
                "manifest_author_id": manifest.get("author_id"),
            },
        }

    def _build_dispute_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for dispute in self.repository.list_disputes(limit=500):
            source_status = {
                "open": "new",
                "under_review": "in_review",
                "approved": "in_review",
                "credited": "resolved",
                "reversed": "resolved",
                "refunded": "resolved",
                "resolved": "resolved",
                "rejected": "dismissed",
            }.get(str(dispute.get("status") or "open"), "new")
            due_at = (self._parse_timestamp(dispute.get("created_at")) + timedelta(hours=24)).isoformat() if dispute.get("created_at") else None
            item = {
                "review_item_id": f"ops_review::dispute::{dispute['dispute_id']}",
                "source_type": "dispute",
                "source_id": str(dispute["dispute_id"]),
                "queue": "support",
                "status": source_status,
                "severity": "high",
                "priority": self._priority_for_item(queue="support", severity="high", due_at=due_at, source_status=source_status),
                "owner_id": dispute.get("reviewer_id"),
                "reviewer_id": dispute.get("reviewer_id"),
                "account_id": dispute.get("account_id"),
                "world_id": None,
                "world_version_id": None,
                "headline": f"Dispute · {dispute.get('dispute_reason_code') or dispute.get('dispute_id')}",
                "summary": f"amount {dispute.get('requested_amount_usd') or 0} · billable_event {dispute.get('billable_event_id') or '-'}",
                "recommended_action": "review_dispute",
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=source_status),
                "allowed_actions": ["assign_to_me", "mark_in_review", "resolve", "dismiss", "open_account_workspace", "open_investigation"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=dispute.get("account_id")),
                        self._link(kind="campaign", entity_id=dispute.get("campaign_id")),
                        self._link(kind="billable_event", entity_id=dispute.get("billable_event_id")),
                        self._link(kind="trace", entity_id=dispute.get("trace_id")),
                    ]
                    if item
                ],
                "source_updated_at": dispute.get("updated_at"),
                "source_payload": {"dispute": dispute},
            }
            items.append(item)
        return items

    def _build_support_case_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for case in self.repository.list_support_cases(limit=500):
            source_status = {
                "open": "new",
                "in_progress": "in_review",
                "resolved": "resolved",
                "dismissed": "dismissed",
            }.get(str(case.get("status") or "open"), "new")
            severity = "high" if str(case.get("priority") or "") == "high" else "medium"
            due_at = (self._parse_timestamp(case.get("created_at")) + timedelta(hours=24)).isoformat() if case.get("created_at") else None
            item = {
                "review_item_id": f"ops_review::support_case::{case['support_case_id']}",
                "source_type": "support_case",
                "source_id": str(case["support_case_id"]),
                "queue": "support",
                "status": source_status,
                "severity": severity,
                "priority": self._priority_for_item(queue="support", severity=severity, due_at=due_at, source_status=source_status),
                "owner_id": case.get("owner_id"),
                "reviewer_id": case.get("owner_id"),
                "account_id": case.get("account_id"),
                "world_id": None,
                "world_version_id": None,
                "headline": f"{case.get('subject') or case.get('support_case_id')} · Support",
                "summary": f"type {case.get('case_type') or '-'} · priority {case.get('priority') or '-'}",
                "recommended_action": "review_support_case",
                "due_at": due_at,
                "sla_bucket": self._sla_bucket(due_at=due_at, status=source_status),
                "allowed_actions": ["assign_to_me", "mark_in_review", "resolve", "dismiss", "open_account_workspace", "open_investigation"],
                "linked_entities": [
                    item
                    for item in [
                        self._link(kind="account", entity_id=case.get("account_id")),
                        self._link(kind="campaign", entity_id=case.get("campaign_id")),
                        self._link(kind="billable_event", entity_id=case.get("billable_event_id")),
                        self._link(kind="trace", entity_id=case.get("trace_id")),
                    ]
                    if item
                ],
                "source_updated_at": case.get("updated_at"),
                "source_payload": {"support_case": case},
            }
            items.append(item)
        return items

    def _synchronize_items(self) -> List[Dict[str, Any]]:
        existing = {
            (item["source_type"], item["source_id"]): item
            for item in self.repository.list_ops_review_items(limit=1000)
        }
        author_work_items = self._build_author_work_items()
        covered_world_version_ids = {
            str(item.get("world_version_id") or "")
            for item in author_work_items
            if str(item.get("world_version_id") or "").strip()
        }
        source_items = [
            *author_work_items,
            *self._build_release_items(covered_world_version_ids=covered_world_version_ids),
            *self._build_governance_items(),
            *self._build_alert_items(),
            *self._build_support_items(),
            *self._build_dispute_items(),
            *self._build_support_case_items(),
            *self._build_quality_review_case_items(),
            *self._build_campaign_review_items(),
        ]
        synchronized: List[Dict[str, Any]] = []
        for source_item in source_items:
            overlay = existing.get(self._source_key(source_item))
            merged = self._merge_overlay(source_item=source_item, overlay=overlay)
            persisted = self.repository.upsert_ops_review_item_by_source(
                {
                    **merged,
                    "linked_entities": merged.get("linked_entities", []),
                    "allowed_actions": merged.get("allowed_actions", []),
                    "source_updated_at": source_item.get("source_updated_at"),
                    "last_synced_at": self._utcnow(),
                }
            )
            synchronized.append({**persisted, "source_payload": source_item.get("source_payload", {})})
        synchronized.sort(
            key=lambda item: (
                int(item.get("priority", 100)),
                self._parse_timestamp(item.get("updated_at")),
            ),
            reverse=False,
        )
        return synchronized

    def _filter_items(
        self,
        items: List[Dict[str, Any]],
        *,
        queue: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        severity: Optional[str] = None,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        filtered = list(items)
        if queue is not None:
            filtered = [item for item in filtered if item.get("queue") == queue]
        if status is not None:
            filtered = [item for item in filtered if item.get("status") == status]
        if owner_id is not None:
            filtered = [item for item in filtered if item.get("owner_id") == owner_id]
        if severity is not None:
            filtered = [item for item in filtered if item.get("severity") == severity]
        if account_id is not None:
            filtered = [item for item in filtered if item.get("account_id") == account_id]
        if world_id is not None:
            filtered = [item for item in filtered if item.get("world_id") == world_id]
        if world_version_id is not None:
            filtered = [item for item in filtered if item.get("world_version_id") == world_version_id]
        return filtered[:limit]

    def _summary(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        queue_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        for item in items:
            queue = str(item.get("queue") or "unknown")
            status = str(item.get("status") or "unknown")
            severity = str(item.get("severity") or "unknown")
            queue_counts[queue] = queue_counts.get(queue, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return {
            "total_count": len(items),
            "queue_counts": queue_counts,
            "status_counts": status_counts,
            "severity_counts": severity_counts,
            "unassigned_count": sum(1 for item in items if not item.get("owner_id")),
            "blocked_count": sum(1 for item in items if item.get("status") == "blocked"),
            "overdue_count": sum(1 for item in items if item.get("due_at") and self._parse_timestamp(item.get("due_at")) <= now and item.get("status") not in {"resolved", "dismissed"}),
            "due_soon_count": sum(
                1
                for item in items
                if item.get("due_at")
                and now < self._parse_timestamp(item.get("due_at")) <= now + timedelta(hours=24)
                and item.get("status") not in {"resolved", "dismissed"}
            ),
            "actionable_count": sum(1 for item in items if item.get("status") not in {"resolved", "dismissed"}),
        }

    def _triage(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        def _top(values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return values[:8]

        return {
            "unassigned": _top([item for item in items if not item.get("owner_id") and item.get("status") not in {"resolved", "dismissed"}]),
            "blocked": _top([item for item in items if item.get("status") == "blocked"]),
            "due_soon": _top([item for item in items if item.get("sla_bucket") in {"due_soon", "overdue"} and item.get("status") not in {"resolved", "dismissed"}]),
            "by_queue": {
                queue: _top([item for item in items if item.get("queue") == queue])
                for queue in ["content_release", "governance", "runtime", "support"]
            },
        }

    def review_hub(
        self,
        *,
        queue: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        severity: Optional[str] = None,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        synchronized = self._synchronize_items()
        filtered = self._filter_items(
            synchronized,
            queue=queue,
            status=status,
            owner_id=owner_id,
            severity=severity,
            account_id=account_id,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        )
        return {
            "generated_at": self._utcnow(),
            "filters": {
                "queue": queue,
                "status": status,
                "owner_id": owner_id,
                "severity": severity,
                "account_id": account_id,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "limit": limit,
            },
            "summary": self._summary(filtered),
            "triage": self._triage(filtered),
            "items": filtered,
        }

    def review_hub_cached(
        self,
        *,
        queue: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        severity: Optional[str] = None,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        items = self.repository.list_ops_review_items(
            queue=queue,
            status=status,
            owner_id=owner_id,
            severity=severity,
            account_id=account_id,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        )
        return {
            "generated_at": self._utcnow(),
            "filters": {
                "queue": queue,
                "status": status,
                "owner_id": owner_id,
                "severity": severity,
                "account_id": account_id,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "limit": limit,
                "source": "cached",
            },
            "summary": self._summary(items),
            "triage": self._triage(items),
            "items": items,
        }

    def review_item_detail(self, review_item_id: str) -> Dict[str, Any]:
        synchronized = {item["review_item_id"]: item for item in self._synchronize_items()}
        item = synchronized.get(review_item_id)
        if item is None:
            persisted = self.repository.get_ops_review_item(review_item_id)
            item = {**persisted, "source_payload": {}}
        if item.get("source_type") in {"quality_review_case", "campaign_review_case"}:
            source_payload = dict(item.get("source_payload") or {})
            if not source_payload:
                if item.get("source_type") == "quality_review_case":
                    trace_id = None
                    linked_entities = list(item.get("linked_entities") or [])
                    for entity in linked_entities:
                        if str(entity.get("kind") or "") == "trace":
                            trace_id = entity.get("id")
                            break
                    if trace_id:
                        try:
                            trace_detail = self.quality_projection.quality_trace_detail(str(trace_id))
                        except KeyError:
                            trace_detail = {}
                        source_payload = {
                            "review_case": self.repository.get_review_case(item["source_id"]),
                            "quality_event": dict(trace_detail.get("event") or {}),
                            "content_quality_score": dict(trace_detail.get("score") or {}),
                            "trace_summary": {
                                "trace_id": trace_id,
                                "linked_context": dict(trace_detail.get("linked_context") or {}),
                            },
                        }
                        item = {**item, "source_payload": source_payload}
        return {
            "generated_at": self._utcnow(),
            "review_item": item,
            "detail_summary": {
                "queue": item.get("queue"),
                "status": item.get("status"),
                "severity": item.get("severity"),
                "allowed_actions": list(item.get("allowed_actions") or []),
                "linked_entity_count": len(item.get("linked_entities") or []),
                "source_type": item.get("source_type"),
            },
        }

    def review_item_detail_cached(self, review_item_id: str) -> Dict[str, Any]:
        item = {**self.repository.get_ops_review_item(review_item_id), "source_payload": {}}
        return {
            "generated_at": self._utcnow(),
            "review_item": item,
            "detail_summary": {
                "queue": item.get("queue"),
                "status": item.get("status"),
                "severity": item.get("severity"),
                "allowed_actions": list(item.get("allowed_actions") or []),
                "linked_entity_count": len(item.get("linked_entities") or []),
                "source_type": item.get("source_type"),
            },
        }

    def review_item_work_detail(self, review_item_id: str) -> Dict[str, Any]:
        detail = self.review_item_detail(review_item_id)
        item = detail["review_item"]
        if item.get("source_type") == "author_work":
            work = self.repository.get_author_work(item["source_id"])
            chapters = self.repository.list_author_work_chapters(work_id=item["source_id"])
            revisions = self.repository.list_author_work_revisions(work_id=item["source_id"], limit=20)
            return {
                **detail,
                "work": {
                    **work,
                    "chapters": chapters,
                    "revisions": revisions,
                    "latest_revision": revisions[0] if revisions else None,
                },
            }
        world_version_id = str(item.get("world_version_id") or "")
        if world_version_id:
            works = self.repository.list_author_works(world_version_id=world_version_id, limit=10)
            if works:
                work = works[0]
                chapters = self.repository.list_author_work_chapters(work_id=work["work_id"])
                revisions = self.repository.list_author_work_revisions(work_id=work["work_id"], limit=20)
                return {
                    **detail,
                    "work": {
                        **work,
                        "chapters": chapters,
                        "revisions": revisions,
                        "latest_revision": revisions[0] if revisions else None,
                    },
                }
            if item.get("source_type") == "world_version_review":
                return {
                    **detail,
                    "work": self._synthetic_review_work_from_world_version(item=item),
                }
        raise KeyError(f"review_item_work_missing:{review_item_id}")

    def assign_review_item(self, *, review_item_id: str, owner_id: str, reviewer_id: str) -> Dict[str, Any]:
        if not str(owner_id or "").strip():
            raise ValueError("owner_id_required")
        if not str(reviewer_id or "").strip():
            raise ValueError("reviewer_id_required")
        item = self.repository.get_ops_review_item(review_item_id)
        updated = self.repository.save_ops_review_item(
            {
                **item,
                "owner_id": owner_id,
                "reviewer_id": reviewer_id,
                "status": item.get("status") if item.get("source_type") == "quality_review_case" else ("triaged" if item.get("status") == "new" else item.get("status")),
            }
        )
        if item.get("source_type") == "quality_review_case":
            self.repository.update_review_case_status(item["source_id"], status="open", owner_id=owner_id)
        if item.get("source_type") == "campaign_review_case":
            submission = self.repository.get_campaign_review_submission(item["source_id"])
            if submission.get("review_case_id"):
                self.repository.update_review_case_status(submission["review_case_id"], status="open", owner_id=owner_id)
        if item.get("source_type") == "support_case":
            case = self.repository.get_support_case(item["source_id"])
            self.repository.save_support_case({**case, "owner_id": owner_id, "support_payload_json": case.get("support_payload_json", {})})
        if item.get("source_type") == "dispute":
            dispute = self.repository.get_dispute(item["source_id"])
            self.repository.save_dispute({**dispute, "reviewer_id": owner_id, "dispute_payload_json": dispute.get("dispute_payload_json", {})})
        return self.review_item_detail(updated["review_item_id"])

    def update_review_item_status(self, *, review_item_id: str, status: str, reviewer_id: str) -> Dict[str, Any]:
        normalized_status = str(status or "").strip()
        if normalized_status not in VALID_REVIEW_ITEM_STATUSES:
            raise ValueError("invalid_review_item_status")
        if not str(reviewer_id or "").strip():
            raise ValueError("reviewer_id_required")
        item = self.repository.get_ops_review_item(review_item_id)
        updated = self.repository.save_ops_review_item(
            {
                **item,
                "status": normalized_status,
                "reviewer_id": reviewer_id,
            }
        )
        if item.get("source_type") == "quality_review_case":
            case_status = {
                "new": "open",
                "triaged": "open",
                "in_review": "in_review",
                "resolved": "resolved",
                "dismissed": "dismissed",
                "blocked": "open",
                "approved": "resolved",
                "needs_changes": "open",
            }.get(normalized_status, "open")
            self.repository.update_review_case_status(item["source_id"], status=case_status)
        if item.get("source_type") == "campaign_review_case":
            submission = self.repository.get_campaign_review_submission(item["source_id"])
            case_status = {
                "new": "open",
                "triaged": "open",
                "in_review": "in_review",
                "resolved": "resolved",
                "dismissed": "dismissed",
                "blocked": "resolved",
                "approved": "resolved",
                "needs_changes": "resolved",
            }.get(normalized_status, "open")
            if submission.get("review_case_id"):
                self.repository.update_review_case_status(submission["review_case_id"], status=case_status)
            submission_status = "in_review" if normalized_status == "in_review" else submission.get("status")
            self.repository.save_campaign_review_submission({**submission, "status": submission_status})
        if item.get("source_type") == "support_case":
            case = self.repository.get_support_case(item["source_id"])
            mapped_status = {
                "new": "open",
                "triaged": "open",
                "in_review": "in_progress",
                "resolved": "resolved",
                "dismissed": "dismissed",
            }.get(normalized_status, "open")
            self.repository.save_support_case({**case, "status": mapped_status, "support_payload_json": case.get("support_payload_json", {})})
        if item.get("source_type") == "dispute":
            dispute = self.repository.get_dispute(item["source_id"])
            mapped_status = {
                "new": "open",
                "triaged": "under_review",
                "in_review": "under_review",
                "resolved": "resolved",
                "dismissed": "rejected",
            }.get(normalized_status, "open")
            self.repository.save_dispute({**dispute, "status": mapped_status, "dispute_payload_json": dispute.get("dispute_payload_json", {})})
        return self.review_item_detail(updated["review_item_id"])

    def decide_review_item(self, *, review_item_id: str, decision: str, reviewer_id: str) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip()
        if normalized_decision not in VALID_REVIEW_ITEM_DECISIONS:
            raise ValueError("invalid_review_item_decision")
        result = self.update_review_item_status(
            review_item_id=review_item_id,
            status=VALID_REVIEW_ITEM_DECISIONS[normalized_decision],
            reviewer_id=reviewer_id,
        )
        review_item = result["review_item"]
        if review_item.get("source_type") == "quality_review_case":
            case_status = {
                "resolve": "resolved",
                "dismiss": "dismissed",
            }.get(normalized_decision)
            if case_status:
                self.repository.update_review_case_status(review_item["source_id"], status=case_status)
            return self.review_item_detail(review_item_id)
        if review_item.get("source_type") == "campaign_review_case":
            submission = self.repository.get_campaign_review_submission(review_item["source_id"])
            campaign_id = str(submission.get("campaign_id") or "")
            mapped = {
                "approve": "approve",
                "needs_changes": "needs_changes",
                "block": "block",
            }.get(normalized_decision)
            if mapped:
                self.customer_campaigns.decide_campaign(
                    campaign_id=campaign_id,
                    reviewer_id=reviewer_id,
                    decision=mapped,
                )
            return self.review_item_detail(review_item_id)
        if review_item.get("source_type") == "author_work":
            work = self.repository.get_author_work(review_item["source_id"])
            next_work_status = {
                "approve": "approved",
                "needs_changes": "needs_changes",
                "block": "needs_changes",
            }.get(normalized_decision)
            if next_work_status:
                self.repository.save_author_work(
                    {
                        **work,
                        "status": next_work_status,
                    }
                )
                return self.review_item_detail(review_item_id)
        return result
