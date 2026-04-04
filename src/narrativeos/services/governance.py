from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from ..persistence.db import utcnow_iso
from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .billing import BillingService


def parse_governance_notes(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


class GovernanceService:
    VALID_CASE_TYPES = {"rights", "moderation", "abuse"}
    VALID_TARGET_TYPES = {"account", "world_version", "session", "entitlement"}
    VALID_STATUSES = {"open", "in_review", "escalated", "resolved", "dismissed"}
    VALID_RESTRICTION_TYPES = {"reader_access_block", "author_access_block", "checkout_block", "account_hold"}
    STATUS_TRANSITIONS = {
        "open": {"in_review", "escalated", "dismissed"},
        "in_review": {"escalated", "resolved", "dismissed"},
        "escalated": {"in_review", "resolved", "dismissed"},
        "resolved": set(),
        "dismissed": set(),
    }

    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: Optional["BillingService"] = None,
    ) -> None:
        self.repository = repository
        self.billing = billing_service

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

    def _queue_for_case_type(self, case_type: str) -> str:
        return {
            "rights": "rights_queue",
            "moderation": "moderation_queue",
            "abuse": "abuse_queue",
        }.get(case_type, "ops_queue")

    def _default_due_at(self, *, case_type: str, severity: str) -> str:
        base_hours = {
            "rights": 24,
            "moderation": 12,
            "abuse": 8,
        }.get(case_type, 24)
        severity_modifier = {
            "critical": 0.25,
            "high": 0.5,
            "medium": 1.0,
            "low": 2.0,
        }.get(str(severity or "medium"), 1.0)
        due_at = datetime.now(timezone.utc) + timedelta(hours=max(1, int(base_hours * severity_modifier)))
        return due_at.isoformat()

    def _workflow_template(self, *, case_type: str, target_type: str) -> List[Dict[str, Any]]:
        base = {
            "rights": [
                ("triage_entitlement_context", "核对 entitlement / subscription / wallet 上下文"),
                ("confirm_account_scope", "确认 account ownership 与影响面"),
                ("record_customer_resolution", "记录 customer-facing resolution"),
            ],
            "moderation": [
                ("triage_content_scope", "确认内容范围与命中对象"),
                ("review_policy_evidence", "复核 policy 证据"),
                ("record_moderation_disposition", "记录 moderation disposition"),
            ],
            "abuse": [
                ("triage_abuse_signal", "确认 abuse signal 与风险等级"),
                ("review_restriction_need", "确认 restriction 是否必要"),
                ("record_enforcement_decision", "记录 enforcement decision"),
            ],
        }.get(case_type, [])
        if target_type == "world_version":
            base.append(("inspect_target_world_version", "检查 world_version 的 review / publish 上下文"))
        if target_type == "session":
            base.append(("inspect_target_session", "检查 session 级 runtime / paywall 上下文"))
        if target_type == "entitlement":
            base.append(("inspect_target_entitlement", "检查 entitlement / wallet 变化轨迹"))
        return [
            {
                "key": key,
                "label": label,
                "status": "pending",
                "completed_at": None,
                "completed_by": None,
                "note": None,
            }
            for key, label in base
        ]

    def _normalize_evidence_refs(self, evidence_refs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in evidence_refs or []:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "evidence_id": item.get("evidence_id") or f"evidence_{uuid4().hex[:10]}",
                    "kind": item.get("kind") or "note",
                    "title": item.get("title") or item.get("label") or "evidence",
                    "ref_id": item.get("ref_id"),
                    "preview": str(item.get("preview") or item.get("summary") or "-")[:280],
                    "added_at": item.get("added_at"),
                    "added_by": item.get("added_by"),
                }
            )
        return normalized

    def _ensure_workflow_checklist(
        self,
        *,
        case_type: str,
        target_type: str,
        checklist: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        template = {item["key"]: item for item in self._workflow_template(case_type=case_type, target_type=target_type)}
        for item in checklist or []:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            template[item["key"]] = {
                "key": item.get("key"),
                "label": item.get("label") or template.get(item["key"], {}).get("label") or item.get("key"),
                "status": item.get("status") or "pending",
                "completed_at": item.get("completed_at"),
                "completed_by": item.get("completed_by"),
                "note": item.get("note"),
            }
        return list(template.values())

    def _transition_options(self, status: str) -> List[str]:
        return sorted(self.STATUS_TRANSITIONS.get(status, set()))

    def _validate_transition(self, current_status: str, next_status: str) -> None:
        if next_status == current_status:
            return
        if next_status not in self.STATUS_TRANSITIONS.get(current_status, set()):
            raise ValueError("invalid_case_transition")

    def _owner_for_case(self, case: Dict[str, Any]) -> Optional[str]:
        return case.get("owner_id") or case.get("reviewer_id")

    def _permission_summary(self, case: Dict[str, Any], *, actor_id: Optional[str], actor_role: Optional[str]) -> Dict[str, Any]:
        privileged = actor_role in {None, "reviewer", "ops"}
        owner_id = self._owner_for_case(case)
        can_claim = privileged and bool(actor_id) and case.get("status") in {"open", "escalated"}
        can_assign = privileged and bool(actor_id)
        can_add_evidence = privileged and bool(actor_id)
        can_release_restriction = privileged and bool(actor_id) and bool((case.get("restriction") or {}).get("status") == "active") and (not owner_id or owner_id == actor_id)
        can_transition = privileged and bool(actor_id) and (not owner_id or owner_id == actor_id or case.get("status") == "open")
        return {
            "actor_id": actor_id,
            "actor_role": actor_role,
            "owner_id": owner_id,
            "can_claim": can_claim,
            "can_assign": can_assign,
            "can_add_evidence": can_add_evidence,
            "can_transition": can_transition,
            "can_release_restriction": can_release_restriction,
        }

    def _workflow_summary(self, case: Dict[str, Any]) -> Dict[str, Any]:
        checklist = list(case.get("workflow_checklist") or [])
        pending = [item for item in checklist if item.get("status") != "done"]
        completed = [item for item in checklist if item.get("status") == "done"]
        due_at = self._parse_datetime(case.get("due_at"))
        return {
            "owner_id": self._owner_for_case(case),
            "due_at": case.get("due_at"),
            "is_overdue": bool(due_at and due_at < datetime.now(timezone.utc) and case.get("status") not in {"resolved", "dismissed"}),
            "pending_checklist_count": len(pending),
            "completed_checklist_count": len(completed),
            "transition_options": self._transition_options(str(case.get("status") or "open")),
            "policy_labels": list(case.get("policy_labels") or []),
            "evidence_count": len(case.get("evidence_refs") or []),
            "disposition": case.get("disposition"),
        }

    def _upsert_checklist_completion(
        self,
        checklist: List[Dict[str, Any]],
        *,
        status: str,
        reviewer_id: Optional[str],
        resolution_notes: Optional[str],
    ) -> List[Dict[str, Any]]:
        updated = [dict(item) for item in checklist]
        if status == "in_review":
            for item in updated:
                if item.get("status") != "done":
                    item["status"] = "in_progress"
                    break
        elif status in {"resolved", "dismissed"}:
            now = utcnow_iso()
            for item in updated:
                item["status"] = "done"
                if not item.get("completed_at"):
                    item["completed_at"] = now
                    item["completed_by"] = reviewer_id
                if resolution_notes and not item.get("note"):
                    item["note"] = resolution_notes
        return updated

    def _normalize_case_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = parse_governance_notes(record.get("notes"))
        transitions = list(payload.get("status_transitions", []))
        latest_transition = transitions[-1] if transitions else {
            "status": record.get("status"),
            "reviewer_id": record.get("reviewer_id"),
            "changed_at": record.get("updated_at"),
            "notes": payload.get("resolution_notes"),
        }
        case_type = str(payload.get("case_type") or "rights")
        target_type = str(payload.get("target_type") or "account")
        target_id = payload.get("target_id") or payload.get("account_id") or record.get("asset_id")
        account_id = payload.get("account_id")
        if not account_id and target_type == "account":
            account_id = target_id
        restriction = self._normalize_restriction(payload.get("restriction"))
        case = {
            "case_id": record.get("asset_id"),
            "review_id": record.get("review_id"),
            "status": record.get("status"),
            "case_type": case_type,
            "queue": payload.get("queue") or self._queue_for_case_type(case_type),
            "severity": payload.get("severity") or record.get("risk_rating"),
            "owner_id": payload.get("owner_id"),
            "due_at": payload.get("due_at"),
            "target_type": target_type,
            "target_id": target_id,
            "account_id": account_id,
            "world_id": payload.get("world_id"),
            "world_version_id": payload.get("world_version_id"),
            "session_id": payload.get("session_id"),
            "entitlement_id": payload.get("entitlement_id"),
            "support_issue_ids": list(payload.get("support_issue_ids", [])),
            "summary": payload.get("summary"),
            "description": payload.get("description"),
            "source": payload.get("source") or "ops_manual",
            "recommended_action": payload.get("recommended_action"),
            "resolution_notes": payload.get("resolution_notes"),
            "disposition": payload.get("disposition"),
            "policy_labels": list(payload.get("policy_labels", [])),
            "evidence_refs": self._normalize_evidence_refs(payload.get("evidence_refs")),
            "workflow_checklist": self._ensure_workflow_checklist(
                case_type=case_type,
                target_type=target_type,
                checklist=payload.get("workflow_checklist"),
            ),
            "restriction": restriction,
            "status_transitions": transitions,
            "latest_transition": latest_transition,
            "reviewer_id": record.get("reviewer_id"),
            "created_at": transitions[0].get("changed_at") if transitions else record.get("updated_at"),
            "updated_at": record.get("updated_at"),
        }
        case["workflow_summary"] = self._workflow_summary(case)
        return case

    def _normalize_restriction(self, restriction: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(restriction, dict):
            return None
        payload = dict(restriction)
        status = str(payload.get("status") or "active")
        expires_at = self._parse_datetime(payload.get("expires_at"))
        if status == "active" and expires_at and expires_at <= datetime.now(timezone.utc):
            status = "expired"
        scope = str(payload.get("scope") or "account")
        if scope not in {"reader", "author", "checkout", "account"}:
            scope = "account"
        return {
            "restriction_id": payload.get("restriction_id"),
            "restriction_type": payload.get("restriction_type"),
            "scope": scope,
            "status": status,
            "reason": payload.get("reason"),
            "applied_at": payload.get("applied_at"),
            "applied_by": payload.get("applied_by"),
            "expires_at": payload.get("expires_at"),
            "released_at": payload.get("released_at"),
            "released_by": payload.get("released_by"),
            "release_reason": payload.get("release_reason"),
        }

    def _summary(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        case_type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        queue_counts: Dict[str, int] = {}
        owner_counts: Dict[str, int] = {}
        active_restriction_count = 0
        overdue_case_count = 0
        for item in cases:
            status = str(item.get("status") or "unknown")
            case_type = str(item.get("case_type") or "unknown")
            severity = str(item.get("severity") or "unknown")
            queue = str(item.get("queue") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            case_type_counts[case_type] = case_type_counts.get(case_type, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            queue_counts[queue] = queue_counts.get(queue, 0) + 1
            owner_id = self._owner_for_case(item)
            if owner_id:
                owner_counts[owner_id] = owner_counts.get(owner_id, 0) + 1
            if (item.get("restriction") or {}).get("status") == "active":
                active_restriction_count += 1
            if self._workflow_summary(item).get("is_overdue"):
                overdue_case_count += 1
        return {
            "total_cases": len(cases),
            "open_case_count": sum(1 for item in cases if item.get("status") in {"open", "in_review", "escalated"}),
            "escalated_case_count": status_counts.get("escalated", 0),
            "active_restriction_count": active_restriction_count,
            "overdue_case_count": overdue_case_count,
            "status_counts": status_counts,
            "case_type_counts": case_type_counts,
            "severity_counts": severity_counts,
            "queue_counts": queue_counts,
            "owner_counts": owner_counts,
            "latest_case_id": cases[0].get("case_id") if cases else None,
            "latest_case_at": cases[0].get("updated_at") if cases else None,
        }

    def _recommended_prefills(self, *, account_id: str, support_lookup: Dict[str, Any]) -> List[Dict[str, Any]]:
        prefills: List[Dict[str, Any]] = []
        for issue in support_lookup.get("support_issues", []):
            issue_type = str(issue.get("issue_type") or "")
            if issue_type in {"missing_subscription", "subscription_lifecycle_issue", "story_credits_exhausted", "studio_credits_exhausted", "author_access_blocked"}:
                case_type = "rights"
            elif issue_type == "entitlement_recently_revoked":
                case_type = "abuse"
            else:
                continue
            prefills.append(
                {
                    "label": "为 %s 建立 %s case" % (issue_type, case_type),
                    "prefill": {
                        "account_id": account_id,
                        "case_type": case_type,
                        "target_type": "account",
                        "target_id": account_id,
                        "severity": issue.get("severity") or "medium",
                        "summary": issue.get("title") or issue_type,
                        "description": issue.get("summary") or "",
                        "support_issue_ids": issue.get("issue_id"),
                    },
                }
            )
        return prefills[:6]

    def _default_case_type_for_issue(self, issue_type: str) -> str:
        if issue_type in {"entitlement_recently_revoked"}:
            return "abuse"
        if issue_type in {"reader_payment_required_recent", "story_credits_exhausted", "studio_credits_exhausted", "missing_subscription", "subscription_lifecycle_issue", "author_access_blocked"}:
            return "rights"
        return "moderation"

    def _case_audit_events(self, case: Dict[str, Any], *, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.billing or not case.get("account_id"):
            return []
        trail = self.billing.full_audit_trail(account_id=case["account_id"], limit=max(limit * 4, 40)).get("audit_trail", [])
        restriction_id = (case.get("restriction") or {}).get("restriction_id")
        target_id = case.get("target_id")
        world_version_id = case.get("world_version_id")
        filtered = []
        for item in trail:
            details = dict(item.get("details") or {})
            if details.get("case_id") == case.get("case_id"):
                filtered.append(item)
                continue
            if restriction_id and ((item.get("object_id") == restriction_id) or details.get("restriction", {}).get("restriction_id") == restriction_id):
                filtered.append(item)
                continue
            if target_id and item.get("object_id") == target_id:
                filtered.append(item)
                continue
            if world_version_id and item.get("world_version_id") == world_version_id:
                filtered.append(item)
                continue
        return filtered[:limit]

    def _case_next_actions(self, case: Dict[str, Any], linked_support_issues: List[Dict[str, Any]]) -> List[str]:
        actions: List[str] = []
        restriction = case.get("restriction") or {}
        if case.get("status") in {"open", "in_review"}:
            actions.append("triage_case")
        if case.get("status") == "escalated":
            actions.append("confirm_operator_action")
        if restriction.get("status") == "active":
            actions.append("review_active_restriction")
        if linked_support_issues:
            actions.append("respond_to_linked_support_issue")
        if case.get("status") not in {"resolved", "dismissed"}:
            actions.append("record_resolution_or_dismissal")
        return actions

    def list_cases(
        self,
        *,
        account_id: Optional[str] = None,
        case_type: Optional[str] = None,
        status: Optional[str] = None,
        target_type: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", status=status)
        cases = [self._normalize_case_record(item) for item in records]
        if account_id is not None:
            cases = [item for item in cases if item.get("account_id") == account_id]
        if case_type is not None:
            cases = [item for item in cases if item.get("case_type") == case_type]
        if target_type is not None:
            cases = [item for item in cases if item.get("target_type") == target_type]
        cases = sorted(cases, key=lambda item: str(item.get("updated_at") or ""), reverse=True)[:limit]
        return {
            "cases": cases,
            "governance_summary": self._summary(cases),
        }

    def case_detail(
        self,
        case_id: str,
        *,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        case = self._normalize_case_record(records[0])
        support_lookup = self.billing.support_issue_lookup(account_id=case["account_id"], limit=50) if self.billing and case.get("account_id") else {}
        linked_support_issues = [
            item
            for item in support_lookup.get("support_issues", [])
            if item.get("issue_id") in set(case.get("support_issue_ids", []))
        ]
        audit_events = self._case_audit_events(case)
        return {
            **case,
            "linked_support_issues": linked_support_issues,
            "audit_events": audit_events,
            "detail_summary": {
                "linked_support_issue_count": len(linked_support_issues),
                "audit_event_count": len(audit_events),
                "active_restriction": bool((case.get("restriction") or {}).get("status") == "active"),
                "latest_transition_status": (case.get("latest_transition") or {}).get("status"),
                "evidence_count": len(case.get("evidence_refs") or []),
                "owner_id": self._owner_for_case(case),
            },
            "workflow_summary": self._workflow_summary(case),
            "permission_summary": self._permission_summary(case, actor_id=actor_id, actor_role=actor_role),
            "recommended_next_actions": self._case_next_actions(case, linked_support_issues),
        }

    def list_restrictions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        cases = self.list_cases(account_id=account_id, limit=limit * 2).get("cases", [])
        restrictions = []
        for case in cases:
            restriction = dict(case.get("restriction") or {})
            if not restriction:
                continue
            if status is not None and restriction.get("status") != status:
                continue
            restrictions.append(
                {
                    "case_id": case.get("case_id"),
                    "account_id": case.get("account_id"),
                    "case_type": case.get("case_type"),
                    "severity": case.get("severity"),
                    "target_type": case.get("target_type"),
                    "target_id": case.get("target_id"),
                    **restriction,
                }
            )
        restrictions = sorted(restrictions, key=lambda item: str(item.get("applied_at") or item.get("released_at") or ""), reverse=True)[:limit]
        return {
            "restrictions": restrictions,
            "restriction_summary": {
                "total_restrictions": len(restrictions),
                "active_restriction_count": sum(1 for item in restrictions if item.get("status") == "active"),
                "status_counts": {
                    key: sum(1 for item in restrictions if item.get("status") == key)
                    for key in sorted({str(item.get("status")) for item in restrictions})
                },
                "type_counts": {
                    key: sum(1 for item in restrictions if item.get("restriction_type") == key)
                    for key in sorted({str(item.get("restriction_type")) for item in restrictions})
                },
            },
        }

    def create_case(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        case_type = str(payload.get("case_type") or "rights")
        if case_type not in self.VALID_CASE_TYPES:
            raise ValueError("invalid_case_type")
        target_type = str(payload.get("target_type") or "account")
        if target_type not in self.VALID_TARGET_TYPES:
            raise ValueError("invalid_target_type")
        status = str(payload.get("status") or "open")
        if status not in self.VALID_STATUSES:
            raise ValueError("invalid_case_status")
        case_id = str(payload.get("case_id") or "govcase_%s" % uuid4().hex[:10])
        account_id = payload.get("account_id") or (payload.get("target_id") if target_type == "account" else None)
        changed_at = utcnow_iso()
        notes = {
            "case_id": case_id,
            "case_type": case_type,
            "queue": self._queue_for_case_type(case_type),
            "severity": payload.get("severity", "medium"),
            "owner_id": payload.get("owner_id") or payload.get("reviewer_id"),
            "due_at": payload.get("due_at") or self._default_due_at(case_type=case_type, severity=str(payload.get("severity", "medium"))),
            "target_type": target_type,
            "target_id": payload.get("target_id"),
            "account_id": account_id,
            "world_id": payload.get("world_id"),
            "world_version_id": payload.get("world_version_id"),
            "session_id": payload.get("session_id"),
            "entitlement_id": payload.get("entitlement_id"),
            "summary": payload.get("summary"),
            "description": payload.get("description"),
            "source": payload.get("source", "ops_manual"),
            "recommended_action": payload.get("recommended_action"),
            "support_issue_ids": list(payload.get("support_issue_ids", [])),
            "resolution_notes": payload.get("resolution_notes"),
            "disposition": payload.get("disposition"),
            "policy_labels": list(payload.get("policy_labels", [])),
            "evidence_refs": self._normalize_evidence_refs(payload.get("evidence_refs")),
            "workflow_checklist": self._ensure_workflow_checklist(
                case_type=case_type,
                target_type=target_type,
                checklist=payload.get("workflow_checklist"),
            ),
            "status_transitions": [
                {
                    "status": status,
                    "reviewer_id": payload.get("reviewer_id"),
                    "changed_at": changed_at,
                    "notes": payload.get("resolution_notes"),
                }
            ],
        }
        record = self.repository.save_review_record(
            {
                "asset_type": "governance_case",
                "asset_id": case_id,
                "status": status,
                "reviewer_id": payload.get("reviewer_id"),
                "risk_rating": payload.get("severity", "medium"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(record)

    def escalate_support_issue(
        self,
        *,
        account_id: str,
        issue_id: str,
        reviewer_id: Optional[str] = None,
        case_type: Optional[str] = None,
        severity: Optional[str] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.billing:
            raise ValueError("support_lookup_unavailable")
        support_lookup = self.billing.support_issue_lookup(account_id=account_id, limit=50)
        support_issue = next((item for item in support_lookup.get("support_issues", []) if item.get("issue_id") == issue_id), None)
        if support_issue is None:
            raise KeyError("unknown_support_issue:%s" % issue_id)
        existing = self.list_cases(account_id=account_id, limit=200).get("cases", [])
        active_existing = next(
            (
                item
                for item in existing
                if issue_id in set(item.get("support_issue_ids", []))
                and item.get("status") in {"open", "in_review", "escalated"}
            ),
            None,
        )
        if active_existing:
            return self.case_detail(active_existing["case_id"])
        case = self.create_case(
            {
                "case_type": case_type or self._default_case_type_for_issue(str(support_issue.get("issue_type") or "")),
                "target_type": "account",
                "target_id": account_id,
                "account_id": account_id,
                "severity": severity or support_issue.get("severity") or "medium",
                "summary": summary or support_issue.get("title") or issue_id,
                "description": description or support_issue.get("summary") or "",
                "reviewer_id": reviewer_id,
                "owner_id": reviewer_id,
                "support_issue_ids": [issue_id],
                "recommended_action": "triage_support_escalation",
                "evidence_refs": [
                    {
                        "kind": "support_issue",
                        "title": support_issue.get("title") or issue_id,
                        "ref_id": issue_id,
                        "preview": support_issue.get("summary") or "",
                        "added_at": utcnow_iso(),
                        "added_by": reviewer_id,
                    }
                ],
            }
        )
        return self.case_detail(case["case_id"])

    def apply_restriction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        restriction_type = str(payload.get("restriction_type") or "account_hold")
        if restriction_type not in self.VALID_RESTRICTION_TYPES:
            raise ValueError("invalid_restriction_type")
        case_payload = dict(payload)
        case_payload.setdefault("case_type", "abuse")
        case_payload.setdefault("target_type", "account")
        case_payload.setdefault("status", "escalated")
        case_payload.setdefault("summary", "Manual restriction applied")
        case_payload.setdefault("owner_id", payload.get("reviewer_id"))
        case_payload.setdefault("policy_labels", [restriction_type])
        created = self.create_case(case_payload)
        restriction_scope = {
            "reader_access_block": "reader",
            "author_access_block": "author",
            "checkout_block": "checkout",
            "account_hold": "account",
        }[restriction_type]
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=created["case_id"])
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        notes["restriction"] = {
            "restriction_id": payload.get("restriction_id") or "restriction_%s" % uuid4().hex[:10],
            "restriction_type": restriction_type,
            "scope": restriction_scope,
            "status": "active",
            "reason": payload.get("restriction_reason") or payload.get("resolution_notes") or payload.get("summary"),
            "applied_at": utcnow_iso(),
            "applied_by": payload.get("reviewer_id"),
            "expires_at": payload.get("expires_at"),
            "released_at": None,
            "released_by": None,
            "release_reason": None,
        }
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": created["case_id"],
                "status": "escalated",
                "reviewer_id": payload.get("reviewer_id"),
                "risk_rating": payload.get("severity", existing.get("risk_rating")),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(updated)

    def update_case_status(
        self,
        case_id: str,
        *,
        status: str,
        reviewer_id: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        disposition: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError("invalid_case_status")
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
        current_status = str(existing.get("status") or "open")
        self._validate_transition(current_status, status)
        owner_id = notes.get("owner_id") or existing.get("reviewer_id")
        acting_reviewer = reviewer_id or existing.get("reviewer_id")
        if current_status in {"in_review", "escalated"} and status in {"escalated", "resolved", "dismissed"} and owner_id and acting_reviewer != owner_id:
            raise PermissionError("governance_case_owner_required")
        if status in {"resolved", "dismissed"} and not str(resolution_notes or "").strip():
            raise ValueError("resolution_notes_required")
        transitions = list(notes.get("status_transitions", []))
        transitions.append(
            {
                "status": status,
                "reviewer_id": acting_reviewer,
                "changed_at": utcnow_iso(),
                "notes": resolution_notes,
            }
        )
        notes["status_transitions"] = transitions
        if status == "in_review" and not notes.get("owner_id"):
            notes["owner_id"] = acting_reviewer
        if notes.get("workflow_checklist") is not None or current_case.get("workflow_checklist"):
            notes["workflow_checklist"] = self._upsert_checklist_completion(
                current_case.get("workflow_checklist") or [],
                status=status,
                reviewer_id=acting_reviewer,
                resolution_notes=resolution_notes,
            )
        if resolution_notes:
            notes["resolution_notes"] = resolution_notes
        if disposition:
            notes["disposition"] = disposition
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": case_id,
                "status": status,
                "reviewer_id": acting_reviewer,
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(updated)

    def assign_case(
        self,
        case_id: str,
        *,
        owner_id: str,
        reviewer_id: Optional[str] = None,
        due_at: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        notes["owner_id"] = owner_id
        if due_at:
            notes["due_at"] = due_at
        ownership_events = list(notes.get("ownership_events", []))
        ownership_events.append(
            {
                "owner_id": owner_id,
                "assigned_by": reviewer_id or existing.get("reviewer_id"),
                "assigned_at": utcnow_iso(),
                "note": note,
            }
        )
        notes["ownership_events"] = ownership_events
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": case_id,
                "status": existing.get("status"),
                "reviewer_id": reviewer_id or existing.get("reviewer_id"),
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(updated)

    def append_case_evidence(
        self,
        case_id: str,
        *,
        reviewer_id: Optional[str],
        title: str,
        preview: str,
        ref_id: Optional[str] = None,
        kind: str = "note",
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        evidence_refs = self._normalize_evidence_refs(notes.get("evidence_refs"))
        evidence_refs.append(
            {
                "evidence_id": f"evidence_{uuid4().hex[:10]}",
                "kind": kind,
                "title": title,
                "ref_id": ref_id,
                "preview": preview,
                "added_at": utcnow_iso(),
                "added_by": reviewer_id,
            }
        )
        notes["evidence_refs"] = evidence_refs
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": case_id,
                "status": existing.get("status"),
                "reviewer_id": reviewer_id or existing.get("reviewer_id"),
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(updated)

    def release_restriction(
        self,
        restriction_id: str,
        *,
        reviewer_id: Optional[str] = None,
        release_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        cases = self.list_cases(limit=500).get("cases", [])
        target = next(
            (
                item
                for item in cases
                if (item.get("restriction") or {}).get("restriction_id") == restriction_id or item.get("case_id") == restriction_id
            ),
            None,
        )
        if target is None:
            raise KeyError("unknown_restriction:%s" % restriction_id)
        acting_reviewer = reviewer_id or target.get("reviewer_id")
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=target["case_id"])
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        restriction = dict(notes.get("restriction") or {})
        restriction["status"] = "released"
        restriction["released_at"] = utcnow_iso()
        restriction["released_by"] = reviewer_id or existing.get("reviewer_id")
        restriction["release_reason"] = release_reason
        notes["restriction"] = restriction
        transitions = list(notes.get("status_transitions", []))
        transitions.append(
            {
                "status": "resolved",
                "reviewer_id": reviewer_id or existing.get("reviewer_id"),
                "changed_at": utcnow_iso(),
                "notes": release_reason,
            }
        )
        notes["status_transitions"] = transitions
        if release_reason:
            notes["resolution_notes"] = release_reason
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": target["case_id"],
                "status": "resolved",
                "reviewer_id": acting_reviewer,
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        return self._normalize_case_record(updated)

    def governance_audit_export(
        self,
        *,
        account_id: Optional[str] = None,
        case_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        cases_payload = self.list_cases(
            account_id=account_id,
            case_type=case_type,
            status=status,
            limit=limit,
        )
        restrictions_payload = self.list_restrictions(account_id=account_id, limit=limit)
        return {
            "export_generated_at": utcnow_iso(),
            "filters": {
                "account_id": account_id,
                "case_type": case_type,
                "status": status,
                "limit": limit,
            },
            "governance_summary": cases_payload.get("governance_summary", {}),
            "restriction_summary": restrictions_payload.get("restriction_summary", {}),
            "cases": cases_payload.get("cases", []),
            "restrictions": restrictions_payload.get("restrictions", []),
        }

    def account_snapshot(self, *, account_id: str, limit: int = 20) -> Dict[str, Any]:
        support_lookup = self.billing.support_issue_lookup(account_id=account_id, limit=limit) if self.billing else {}
        cases_payload = self.list_cases(account_id=account_id, limit=limit)
        restrictions_payload = self.list_restrictions(account_id=account_id, limit=limit)
        linked_case_map: Dict[str, List[Dict[str, Any]]] = {}
        for case in cases_payload.get("cases", []):
            for issue_id in case.get("support_issue_ids", []):
                linked_case_map.setdefault(issue_id, []).append(
                    {
                        "case_id": case.get("case_id"),
                        "status": case.get("status"),
                        "case_type": case.get("case_type"),
                    }
                )
        return {
            "account_id": account_id,
            "governance_summary": cases_payload.get("governance_summary", {}),
            "governance_cases": cases_payload.get("cases", []),
            "restriction_summary": restrictions_payload.get("restriction_summary", {}),
            "active_restrictions": [item for item in restrictions_payload.get("restrictions", []) if item.get("status") == "active"],
            "recommended_case_prefills": self._recommended_prefills(account_id=account_id, support_lookup=support_lookup),
            "support_summary": support_lookup.get("support_summary", {}),
            "support_issue_refs": [
                {
                    "issue_id": item.get("issue_id"),
                    "issue_type": item.get("issue_type"),
                    "severity": item.get("severity"),
                    "title": item.get("title"),
                    "linked_cases": linked_case_map.get(item.get("issue_id"), []),
                }
                for item in support_lookup.get("support_issues", [])[:10]
            ],
        }
