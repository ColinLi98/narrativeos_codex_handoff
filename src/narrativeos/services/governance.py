from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from ..persistence.db import utcnow_iso
from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .billing import BillingService
    from .commercial_audit import CommercialAuditService


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
    VALID_OWNER_ROLES = {"reviewer", "ops", "admin"}
    BULK_ACTIONS = {"assignOwner", "updateStatus", "updateDueAt", "addPolicyLabels", "removePolicyLabels", "applyRestriction"}
    CAPACITY_WINDOW_DAYS = 14
    CAPACITY_BASELINE_VERSION = "governance_capacity_v1"
    CAPACITY_OVERRIDE_CONFIG_TYPE = "governance_capacity_override"
    ROLE_CAPACITY_BASELINE = {
        "reviewer": {
            "capacityUnitsPerDay": 12.0,
            "criticalCaseLimit": 2,
            "activeRestrictionLimit": 3,
            "slaHours": 24,
            "roleMultiplier": 1.0,
            "enabled": True,
        },
        "ops": {
            "capacityUnitsPerDay": 14.0,
            "criticalCaseLimit": 2,
            "activeRestrictionLimit": 3,
            "slaHours": 24,
            "roleMultiplier": 1.15,
            "enabled": True,
        },
        "admin": {
            "capacityUnitsPerDay": 8.0,
            "criticalCaseLimit": 2,
            "activeRestrictionLimit": 3,
            "slaHours": 24,
            "roleMultiplier": 0.75,
            "enabled": True,
        },
    }
    OWNER_CAPACITY_OVERRIDES: Dict[str, Dict[str, Any]] = {}
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
        audit_service: Optional["CommercialAuditService"] = None,
    ) -> None:
        self.repository = repository
        self.billing = billing_service
        self.audit = audit_service

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

    def owner_roster(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        return [
            {
                "actor_id": item.get("actor_id"),
                "display_name": item.get("display_name") or item.get("actor_id"),
                "actor_role": item.get("actor_role"),
                "account_id": item.get("account_id"),
                "status": item.get("status"),
            }
            for item in self.repository.list_auth_identities(
                actor_roles=sorted(self.VALID_OWNER_ROLES),
                status="active",
                limit=limit,
            )
        ]

    def _validate_assignable_owner(self, owner_id: str) -> Dict[str, Any]:
        try:
            identity = self.repository.get_auth_identity(str(owner_id or "").strip())
        except KeyError as exc:
            raise ValueError("governance_owner_invalid") from exc
        if str(identity.get("status") or "") != "active":
            raise ValueError("governance_owner_invalid")
        if str(identity.get("actor_role") or "") not in self.VALID_OWNER_ROLES:
            raise ValueError("governance_owner_invalid")
        return identity

    def _validation_result(
        self,
        *,
        target_type: str,
        target_id: str,
        account_id: Optional[str],
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        entitlement_id: Optional[str] = None,
        warnings: Optional[List[str]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_warnings = [str(item) for item in list(warnings or []) if str(item).strip()]
        return {
            "status": "valid_with_warnings" if normalized_warnings else "valid",
            "target_type": target_type,
            "target_id": target_id,
            "account_id": account_id,
            "world_version_id": world_version_id,
            "session_id": session_id,
            "entitlement_id": entitlement_id,
            "validation_warnings": normalized_warnings,
            "validated_at": utcnow_iso(),
            "target_snapshot": dict(snapshot or {}),
        }

    def _invalid_target_validation(
        self,
        *,
        target_type: str,
        target_id: Optional[str],
        account_id: Optional[str],
        code: str,
    ) -> Dict[str, Any]:
        return {
            "status": "invalid",
            "code": code,
            "target_type": target_type,
            "target_id": target_id,
            "account_id": account_id,
            "validation_warnings": [],
            "validated_at": utcnow_iso(),
            "target_snapshot": {
                "id": target_id,
                "target_type": target_type,
                "account_id": account_id,
            },
        }

    def _validate_target(
        self,
        *,
        target_type: str,
        target_id: Optional[str],
        account_id: Optional[str],
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        entitlement_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_target_type = str(target_type or "").strip() or "account"
        if resolved_target_type not in self.VALID_TARGET_TYPES:
            raise ValueError("invalid_target_type")

        resolved_account_id = str(account_id or "").strip() or None
        resolved_target_id = str(target_id or "").strip() or None
        if resolved_target_type == "account":
            resolved_target_id = resolved_target_id or resolved_account_id
            resolved_account_id = resolved_account_id or resolved_target_id
            if not resolved_target_id:
                raise ValueError("governance_case_target_required")
            if resolved_account_id and resolved_target_id != resolved_account_id:
                raise ValueError("governance_target_account_scope_mismatch")
            return self._validation_result(
                target_type=resolved_target_type,
                target_id=resolved_target_id,
                account_id=resolved_account_id,
                snapshot={
                    "id": resolved_target_id,
                    "label": resolved_target_id,
                    "status": "active",
                    "account_id": resolved_account_id,
                    "target_type": resolved_target_type,
                    "validation_warnings": [],
                },
            )

        if not resolved_target_id:
            raise ValueError("governance_case_target_required")

        if resolved_target_type == "world_version":
            if world_version_id and str(world_version_id).strip() != resolved_target_id:
                raise ValueError("governance_target_type_mismatch")
            try:
                version = self.repository.get_world_version(resolved_target_id)
            except KeyError as exc:
                raise ValueError("governance_target_not_found") from exc
            author_id = str(version.author_id or "").strip() or None
            if resolved_account_id and author_id and author_id != resolved_account_id:
                raise ValueError("governance_target_account_scope_mismatch")
            warnings: List[str] = []
            if str(version.status or "") not in {"published", "submitted"}:
                warnings.append("world_version_not_published")
            return self._validation_result(
                target_type=resolved_target_type,
                target_id=resolved_target_id,
                account_id=resolved_account_id or author_id,
                world_version_id=version.world_version_id,
                warnings=warnings,
                snapshot={
                    "id": version.world_version_id,
                    "label": (version.worldpack_json.get("title") or version.world_id or version.world_version_id),
                    "status": version.status,
                    "account_id": author_id,
                    "target_type": resolved_target_type,
                    "world_id": version.world_id,
                    "world_version_id": version.world_version_id,
                    "risk_rating": version.risk_rating,
                    "validation_warnings": warnings,
                },
            )

        if resolved_target_type == "session":
            if session_id and str(session_id).strip() != resolved_target_id:
                raise ValueError("governance_target_type_mismatch")
            try:
                session_record = self.repository.get_session(resolved_target_id)
            except KeyError as exc:
                raise ValueError("governance_target_not_found") from exc
            session_owner = str(
                session_record.metadata.get("reader_id")
                or session_record.player_profile.get("reader_id")
                or ""
            ).strip() or None
            if resolved_account_id and session_owner and session_owner != resolved_account_id:
                raise ValueError("governance_target_account_scope_mismatch")
            entitlements_snapshot = dict(session_record.metadata.get("entitlements_snapshot") or {})
            warnings = []
            if str(entitlements_snapshot.get("status") or "").strip() == "blocked":
                warnings.append("session_access_blocked")
            return self._validation_result(
                target_type=resolved_target_type,
                target_id=resolved_target_id,
                account_id=resolved_account_id or session_owner,
                session_id=session_record.session_id,
                world_version_id=str(session_record.metadata.get("world_version_id") or "").strip() or None,
                warnings=warnings,
                snapshot={
                    "id": session_record.session_id,
                    "label": session_record.world_id or session_record.session_id,
                    "status": "active",
                    "account_id": session_owner,
                    "target_type": resolved_target_type,
                    "world_id": session_record.world_id,
                    "world_version_id": session_record.metadata.get("world_version_id"),
                    "session_id": session_record.session_id,
                    "validation_warnings": warnings,
                },
            )

        if entitlement_id and str(entitlement_id).strip() != resolved_target_id:
            raise ValueError("governance_target_type_mismatch")
        if not self.billing:
            raise ValueError("governance_target_not_found")
        if not resolved_account_id:
            raise ValueError("governance_case_target_required")
        entitlements = list(
            (self.billing.list_entitlements_for_account(resolved_account_id).get("entitlements") or [])
        )
        target_entitlement = next(
            (
                item
                for item in entitlements
                if str(item.get("entitlement_id") or "").strip() == resolved_target_id
            ),
            None,
        )
        if target_entitlement is None:
            raise ValueError("governance_target_not_found")
        warnings = []
        entitlement_status = str(target_entitlement.get("status") or "").strip()
        if entitlement_status not in {"active", "trialing"}:
            warnings.append("entitlement_inactive")
        expires_at = self._parse_datetime(str(target_entitlement.get("expires_at") or "").strip() or None)
        if expires_at and expires_at <= datetime.now(timezone.utc):
            warnings.append("entitlement_expired")
        return self._validation_result(
            target_type=resolved_target_type,
            target_id=resolved_target_id,
            account_id=resolved_account_id,
            entitlement_id=str(target_entitlement.get("entitlement_id") or "").strip() or None,
            warnings=warnings,
            snapshot={
                "id": target_entitlement.get("entitlement_id"),
                "label": f"{str(target_entitlement.get('entitlement_type') or '')}:{str(target_entitlement.get('wallet_type') or target_entitlement.get('tier_id') or target_entitlement.get('world_id') or '')}",
                "status": target_entitlement.get("status"),
                "account_id": target_entitlement.get("account_id"),
                "target_type": resolved_target_type,
                "entitlement_id": target_entitlement.get("entitlement_id"),
                "entitlement_type": target_entitlement.get("entitlement_type"),
                "wallet_type": target_entitlement.get("wallet_type"),
                "tier_id": target_entitlement.get("tier_id"),
                "world_id": target_entitlement.get("world_id"),
                "expires_at": target_entitlement.get("expires_at"),
                "validation_warnings": warnings,
            },
        )

    def target_resolver(self, *, account_id: Optional[str], limit: int = 10) -> Dict[str, Any]:
        resolved_account_id = str(account_id or "").strip() or None
        if not resolved_account_id:
            return {"accounts": [], "world_versions": [], "sessions": [], "entitlements": []}
        account_detail = self.billing.account_detail(account_id=resolved_account_id, limit=limit) if self.billing else {}
        worlds = []
        for item in self.repository.list_world_versions():
            if str(item.get("author_id") or "").strip() != resolved_account_id:
                continue
            validation = self._validate_target(
                target_type="world_version",
                target_id=str(item.get("world_version_id") or ""),
                account_id=resolved_account_id,
                world_version_id=str(item.get("world_version_id") or ""),
            )
            worlds.append(validation["target_snapshot"])
            if len(worlds) >= limit:
                break
        sessions = []
        for item in list(account_detail.get("recent_sessions") or [])[:limit]:
            session_id = str(item.get("session_id") or "").strip()
            if not session_id:
                continue
            validation = self._validate_target(
                target_type="session",
                target_id=session_id,
                account_id=resolved_account_id,
                session_id=session_id,
            )
            sessions.append(validation["target_snapshot"])
        entitlements = []
        if self.billing:
            for item in list((self.billing.list_entitlements_for_account(resolved_account_id).get("entitlements") or []))[:limit]:
                entitlement_id_value = str(item.get("entitlement_id") or "").strip()
                if not entitlement_id_value:
                    continue
                validation = self._validate_target(
                    target_type="entitlement",
                    target_id=entitlement_id_value,
                    account_id=resolved_account_id,
                    entitlement_id=entitlement_id_value,
                )
                entitlements.append(validation["target_snapshot"])
        return {
            "accounts": [
                {
                    "id": resolved_account_id,
                    "label": resolved_account_id,
                    "status": "active",
                    "account_id": resolved_account_id,
                    "target_type": "account",
                    "validation_warnings": [],
                }
            ],
            "world_versions": worlds,
            "sessions": sessions,
            "entitlements": entitlements,
        }

    def target_resolver_meta(self, *, account_id: Optional[str]) -> Dict[str, Any]:
        return {
            "scope_account_id": str(account_id or "").strip() or None,
            "strict_scope_enabled": bool(str(account_id or "").strip()),
            "validation_mode": "account_scoped_hard",
            "supported_target_types": sorted(self.VALID_TARGET_TYPES),
        }

    def _clamp(self, minimum: float, maximum: float, value: float) -> float:
        return max(minimum, min(maximum, float(value)))

    def _capacity_baseline(self, *, owner_id: str, actor_role: Optional[str]) -> Dict[str, Any]:
        baseline = dict(self.ROLE_CAPACITY_BASELINE.get(str(actor_role or "reviewer"), self.ROLE_CAPACITY_BASELINE["reviewer"]))
        persisted_override = dict(self._persistent_capacity_override_payload(owner_id=owner_id))
        runtime_override = dict(self.OWNER_CAPACITY_OVERRIDES.get(str(owner_id or "").strip(), {}))
        override = {**persisted_override, **runtime_override}
        merged = {**baseline, **override}
        merged["capacityUnitsPerDay"] = float(merged.get("capacityUnitsPerDay") or baseline["capacityUnitsPerDay"])
        merged["criticalCaseLimit"] = int(merged.get("criticalCaseLimit") or baseline["criticalCaseLimit"])
        merged["activeRestrictionLimit"] = int(merged.get("activeRestrictionLimit") or baseline["activeRestrictionLimit"])
        merged["slaHours"] = int(merged.get("slaHours") or baseline["slaHours"])
        merged["roleMultiplier"] = float(merged.get("roleMultiplier") or baseline["roleMultiplier"])
        merged["enabled"] = bool(merged.get("enabled", True))
        return merged

    def _persistent_capacity_override_map(self, *, limit: int = 200) -> Dict[str, Dict[str, Any]]:
        rows = self.repository.list_ops_configs(
            config_type=self.CAPACITY_OVERRIDE_CONFIG_TYPE,
            limit=limit,
        )
        overrides: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            payload = dict(row.get("config_payload") or {})
            owner_id = str(row.get("scope_key") or payload.get("owner_id") or "").strip()
            if not owner_id or owner_id in overrides:
                continue
            overrides[owner_id] = {
                "opsConfigId": row.get("ops_config_id"),
                "mode": row.get("status"),
                "updatedAt": row.get("updated_at"),
                "payload": payload,
            }
        return overrides

    def _persistent_capacity_override_payload(self, *, owner_id: str) -> Dict[str, Any]:
        record = self._persistent_capacity_override_map(limit=500).get(str(owner_id or "").strip(), {})
        if str(record.get("mode") or "") != "active":
            return {}
        return dict(record.get("payload") or {})

    def capacity_admin_surface(self) -> Dict[str, Any]:
        overrides = self._persistent_capacity_override_map(limit=500)
        return {
            "can_edit_roles": ["admin"],
            "storage": "ops_config",
            "configType": self.CAPACITY_OVERRIDE_CONFIG_TYPE,
            "baselineConfigVersion": self.CAPACITY_BASELINE_VERSION,
            "editableFields": [
                "capacityUnitsPerDay",
                "criticalCaseLimit",
                "activeRestrictionLimit",
                "slaHours",
                "roleMultiplier",
                "enabled",
            ],
            "persistedOverrides": [
                {
                    "ownerId": owner_id,
                    "opsConfigId": record.get("opsConfigId"),
                    "mode": record.get("mode"),
                    "updatedAt": record.get("updatedAt"),
                    "override": dict(record.get("payload") or {}),
                }
                for owner_id, record in sorted(overrides.items())
            ],
        }

    def update_capacity_override(
        self,
        owner_id: str,
        *,
        capacity_units_per_day: Optional[float] = None,
        critical_case_limit: Optional[int] = None,
        active_restriction_limit: Optional[int] = None,
        sla_hours: Optional[int] = None,
        role_multiplier: Optional[float] = None,
        enabled: Optional[bool] = None,
        clear_override: bool = False,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        note: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        validated_owner = self._validate_assignable_owner(owner_id)
        normalized_owner_id = str(validated_owner.get("actor_id") or owner_id).strip()
        if not clear_override and all(
            value is None
            for value in [
                capacity_units_per_day,
                critical_case_limit,
                active_restriction_limit,
                sla_hours,
                role_multiplier,
                enabled,
            ]
        ):
            raise ValueError("governance_capacity_override_empty")
        if capacity_units_per_day is not None and float(capacity_units_per_day) <= 0:
            raise ValueError("invalid_capacity_units_per_day")
        if critical_case_limit is not None and int(critical_case_limit) < 0:
            raise ValueError("invalid_critical_case_limit")
        if active_restriction_limit is not None and int(active_restriction_limit) < 0:
            raise ValueError("invalid_active_restriction_limit")
        if sla_hours is not None and int(sla_hours) <= 0:
            raise ValueError("invalid_sla_hours")
        if role_multiplier is not None and float(role_multiplier) <= 0:
            raise ValueError("invalid_role_multiplier")
        next_payload: Dict[str, Any] = {
            "owner_id": normalized_owner_id,
            "owner_role": validated_owner.get("actor_role"),
            "updated_by": reviewer_id,
            "note": note,
        }
        if not clear_override:
            if capacity_units_per_day is not None:
                next_payload["capacityUnitsPerDay"] = float(capacity_units_per_day)
            if critical_case_limit is not None:
                next_payload["criticalCaseLimit"] = int(critical_case_limit)
            if active_restriction_limit is not None:
                next_payload["activeRestrictionLimit"] = int(active_restriction_limit)
            if sla_hours is not None:
                next_payload["slaHours"] = int(sla_hours)
            if role_multiplier is not None:
                next_payload["roleMultiplier"] = float(role_multiplier)
            if enabled is not None:
                next_payload["enabled"] = bool(enabled)
        persisted = self.repository.save_ops_config(
            {
                "ops_config_id": f"governance_capacity_override::{normalized_owner_id}",
                "config_type": self.CAPACITY_OVERRIDE_CONFIG_TYPE,
                "scope_key": normalized_owner_id,
                "status": "disabled" if clear_override else "active",
                "config_payload": next_payload,
            }
        )
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(reviewer_id or "ops_unknown"),
                actor_role=str(actor_role or "admin"),
                account_id=None,
                object_type="governance_capacity_override",
                object_id=normalized_owner_id,
                action_type="governance_capacity_override_updated",
                source_surface=source_surface,
                customer_visible_payload={
                    "owner_id": normalized_owner_id,
                    "status": "disabled" if clear_override else "active",
                },
                internal_payload={
                    "owner_id": normalized_owner_id,
                    "owner_role": validated_owner.get("actor_role"),
                    "clear_override": clear_override,
                    "ops_config": persisted,
                    "override_payload": next_payload,
                },
            )
        return {
            "ownerId": normalized_owner_id,
            "actorRole": validated_owner.get("actor_role"),
            "mode": persisted.get("status"),
            "updatedAt": persisted.get("updated_at"),
            "override": next_payload,
        }

    def _observed_capacity_overlay(
        self,
        *,
        owner_id: str,
        cases_by_id: Dict[str, Dict[str, Any]],
        baseline: Dict[str, Any],
    ) -> Dict[str, Any]:
        window_start = datetime.now(timezone.utc) - timedelta(days=self.CAPACITY_WINDOW_DAYS)
        audit_logs = self.repository.list_audit_logs(
            actor_id=owner_id,
            object_type="governance_case",
            action_type="governance_case_status_changed",
            limit=1000,
        )
        resolution_hours: List[float] = []
        overdue_resolved = 0
        resolved_count = 0
        for entry in audit_logs:
            occurred_at = self._parse_datetime(str(entry.get("created_at") or "").strip() or None)
            if occurred_at is None or occurred_at < window_start:
                continue
            internal_payload = dict(entry.get("internal_payload_json") or {})
            if str(internal_payload.get("next_status") or "") not in {"resolved", "dismissed"}:
                continue
            resolved_count += 1
            case = cases_by_id.get(str(entry.get("object_id") or ""))
            if not case:
                continue
            created_at = self._parse_datetime(str(case.get("created_at") or "").strip() or None)
            if created_at is not None:
                resolution_hours.append(max(0.0, (occurred_at - created_at).total_seconds() / 3600.0))
            due_at = self._parse_datetime(str(case.get("due_at") or "").strip() or None)
            if due_at is not None and occurred_at > due_at:
                overdue_resolved += 1
        median_resolution_hours = None
        if resolution_hours:
            ordered = sorted(resolution_hours)
            middle = len(ordered) // 2
            if len(ordered) % 2:
                median_resolution_hours = ordered[middle]
            else:
                median_resolution_hours = (ordered[middle - 1] + ordered[middle]) / 2
        overdue_resolved_ratio = (overdue_resolved / resolved_count) if resolved_count else 0.0
        throughput_factor = self._clamp(
            0.85,
            1.15,
            resolved_count / max(1.0, float(baseline["capacityUnitsPerDay"]) * float(self.CAPACITY_WINDOW_DAYS)),
        )
        if median_resolution_hours is None:
            sla_factor = 1.0
        else:
            sla_factor = 0.85 if median_resolution_hours > int(baseline["slaHours"]) else 1.05
        overdue_factor = 0.85 if overdue_resolved_ratio > 0.20 else 1.0
        return {
            "windowDays": self.CAPACITY_WINDOW_DAYS,
            "resolvedCount14d": resolved_count,
            "medianResolutionHours14d": round(median_resolution_hours, 2) if median_resolution_hours is not None else None,
            "overdueResolvedRatio14d": round(overdue_resolved_ratio, 4),
            "throughputFactor": round(throughput_factor, 4),
            "slaFactor": round(sla_factor, 4),
            "overdueFactor": round(overdue_factor, 4),
        }

    def _effective_capacity_units(self, *, baseline: Dict[str, Any], overlay: Dict[str, Any]) -> float:
        return round(
            float(baseline["capacityUnitsPerDay"])
            * float(baseline["roleMultiplier"])
            * float(overlay["throughputFactor"])
            * float(overlay["slaFactor"])
            * float(overlay["overdueFactor"]),
            2,
        )

    def _calibrated_load_score(
        self,
        *,
        raw_load_units: float,
        effective_capacity_units: float,
        critical_count: int,
        active_restriction_count: int,
        baseline: Dict[str, Any],
    ) -> float:
        score = (float(raw_load_units) / max(1.0, float(effective_capacity_units))) * 10.0
        score += max(0, int(critical_count) - int(baseline["criticalCaseLimit"])) * 2.0
        score += max(0, int(active_restriction_count) - int(baseline["activeRestrictionLimit"])) * 1.5
        return round(score, 2)

    def _severity_weight(self, severity: Optional[str]) -> int:
        return {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
        }.get(str(severity or "medium"), 1)

    def _is_actionable_case(self, case: Dict[str, Any]) -> bool:
        return str(case.get("status") or "") in {"open", "in_review", "escalated"}

    def _is_due_within_24h(self, case: Dict[str, Any]) -> bool:
        due_at = self._parse_datetime(str(case.get("due_at") or "").strip() or None)
        if due_at is None:
            return False
        now = datetime.now(timezone.utc)
        return now <= due_at <= (now + timedelta(hours=24))

    def _case_load_units(self, case: Dict[str, Any]) -> int:
        units = self._severity_weight(str(case.get("severity") or "medium"))
        if str(case.get("status") or "") == "escalated":
            units += 2
        if bool((case.get("workflow_summary") or {}).get("is_overdue")):
            units += 3
        if bool((case.get("restriction") or {}).get("status") == "active"):
            units += 2
        if self._is_due_within_24h(case):
            units += 1
        return units

    def _queue_case_row(self, case: Dict[str, Any]) -> Dict[str, Any]:
        workflow_summary = dict(case.get("workflow_summary") or {})
        restriction = dict(case.get("restriction") or {})
        return {
            "case_id": case.get("case_id"),
            "account_id": case.get("account_id"),
            "summary": case.get("summary"),
            "case_type": case.get("case_type"),
            "status": case.get("status"),
            "severity": case.get("severity"),
            "owner_id": workflow_summary.get("owner_id") or case.get("owner_id"),
            "due_at": workflow_summary.get("due_at") or case.get("due_at"),
            "is_overdue": bool(workflow_summary.get("is_overdue")),
            "target_type": case.get("target_type"),
            "target_id": case.get("target_id"),
            "support_issue_ids": list(case.get("support_issue_ids") or []),
            "has_active_restriction": bool(restriction.get("status") == "active"),
            "restriction_type": restriction.get("restriction_type"),
            "restriction_status": restriction.get("status"),
            "updated_at": case.get("updated_at"),
            "target_validation": dict(case.get("target_validation") or {}),
        }

    def _bulk_action_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"id": "assignOwner", "label": "Assign Owner", "requiresPreview": True},
            {"id": "updateStatus", "label": "Update Status", "requiresPreview": True},
            {"id": "updateDueAt", "label": "Update Due At", "requiresPreview": True},
            {"id": "addPolicyLabels", "label": "Add Policy Labels", "requiresPreview": True},
            {"id": "removePolicyLabels", "label": "Remove Policy Labels", "requiresPreview": True},
            {"id": "applyRestriction", "label": "Apply Restriction", "requiresPreview": True},
        ]

    def _filter_queue_cases(
        self,
        cases: List[Dict[str, Any]],
        *,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        case_type: Optional[str] = None,
        severity: Optional[str] = None,
        target_type: Optional[str] = None,
        has_active_restriction: Optional[bool] = None,
        overdue_only: bool = False,
        unassigned_only: bool = False,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filtered = list(cases)
        if status:
            status_values = {item.strip() for item in str(status).split(",") if item.strip()}
            filtered = [item for item in filtered if str(item.get("status") or "") in status_values]
        if owner_id:
            filtered = [item for item in filtered if str((item.get("workflow_summary") or {}).get("owner_id") or item.get("owner_id") or "") == owner_id]
        if case_type:
            filtered = [item for item in filtered if str(item.get("case_type") or "") == case_type]
        if severity:
            filtered = [item for item in filtered if str(item.get("severity") or "") == severity]
        if target_type:
            filtered = [item for item in filtered if str(item.get("target_type") or "") == target_type]
        if has_active_restriction is not None:
            filtered = [item for item in filtered if bool((item.get("restriction") or {}).get("status") == "active") == has_active_restriction]
        if overdue_only:
            filtered = [item for item in filtered if bool((item.get("workflow_summary") or {}).get("is_overdue"))]
        if unassigned_only:
            filtered = [item for item in filtered if not str((item.get("workflow_summary") or {}).get("owner_id") or item.get("owner_id") or "").strip()]
        if search:
            normalized_search = str(search or "").strip().lower()
            filtered = [
                item
                for item in filtered
                if normalized_search in " ".join(
                    [
                        str(item.get("summary") or ""),
                        str(item.get("target_id") or ""),
                        str(item.get("account_id") or ""),
                        " ".join(str(value) for value in list(item.get("support_issue_ids") or [])),
                    ]
                ).lower()
            ]
        return filtered

    def _owner_workload_rows(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        roster = self.owner_roster(limit=200)
        roster_map = {str(item.get("actor_id") or ""): item for item in roster}
        cases_by_id = {str(item.get("case_id") or ""): item for item in cases if str(item.get("case_id") or "").strip()}
        persisted_override_map = self._persistent_capacity_override_map(limit=500)
        rows: Dict[str, Dict[str, Any]] = {
            str(item.get("actor_id") or ""): {
                "owner_id": item.get("actor_id"),
                "display_name": item.get("display_name") or item.get("actor_id"),
                "actor_role": item.get("actor_role"),
                "status": item.get("status"),
                "open_count": 0,
                "in_review_count": 0,
                "escalated_count": 0,
                "overdue_count": 0,
                "active_restriction_count": 0,
                "critical_count": 0,
                "due_within_24h_count": 0,
                "raw_load_units": 0.0,
                "case_ids": [],
            }
            for item in roster
            if str(item.get("actor_id") or "").strip()
        }
        for case in cases:
            owner_id = str((case.get("workflow_summary") or {}).get("owner_id") or case.get("owner_id") or "").strip()
            if not owner_id:
                continue
            row = rows.setdefault(
                owner_id,
                {
                    "owner_id": owner_id,
                    "display_name": (roster_map.get(owner_id) or {}).get("display_name") or owner_id,
                    "actor_role": (roster_map.get(owner_id) or {}).get("actor_role") or "unknown",
                    "status": (roster_map.get(owner_id) or {}).get("status") or "unknown",
                    "open_count": 0,
                    "in_review_count": 0,
                    "escalated_count": 0,
                    "overdue_count": 0,
                    "active_restriction_count": 0,
                    "critical_count": 0,
                    "due_within_24h_count": 0,
                    "raw_load_units": 0.0,
                    "case_ids": [],
                },
            )
            case_status = str(case.get("status") or "")
            if case_status == "open":
                row["open_count"] += 1
            if case_status == "in_review":
                row["in_review_count"] += 1
            if case_status == "escalated":
                row["escalated_count"] += 1
            if bool((case.get("workflow_summary") or {}).get("is_overdue")):
                row["overdue_count"] += 1
            if bool((case.get("restriction") or {}).get("status") == "active"):
                row["active_restriction_count"] += 1
            if str(case.get("severity") or "") == "critical":
                row["critical_count"] += 1
            if self._is_due_within_24h(case):
                row["due_within_24h_count"] += 1
            row["raw_load_units"] += self._case_load_units(case)
            row["case_ids"].append(case.get("case_id"))
        return sorted(
            [
                {
                    "ownerId": item["owner_id"],
                    "displayName": item["display_name"],
                    "actorRole": item["actor_role"],
                    "status": item["status"],
                    "openCount": item["open_count"],
                    "inReviewCount": item["in_review_count"],
                    "escalatedCount": item["escalated_count"],
                    "overdueCount": item["overdue_count"],
                    "activeRestrictionCount": item["active_restriction_count"],
                    "criticalCount": item["critical_count"],
                    "dueWithin24hCount": item["due_within_24h_count"],
                    "rawLoadUnits": round(float(item["raw_load_units"]), 2),
                    **self._capacity_profile_payload(
                        owner_id=str(item["owner_id"] or ""),
                        actor_role=str(item["actor_role"] or ""),
                        raw_load_units=float(item["raw_load_units"]),
                        critical_count=int(item["critical_count"]),
                        active_restriction_count=int(item["active_restriction_count"]),
                        cases_by_id=cases_by_id,
                        persisted_record=persisted_override_map.get(str(item["owner_id"] or "").strip(), {}),
                    ),
                    "caseIds": list(item["case_ids"]),
                }
                for item in rows.values()
            ],
            key=lambda item: (-float(item["calibratedLoadScore"]), int(item["overdueCount"]), int(item["criticalCount"]), str(item["ownerId"] or "")),
        )

    def _capacity_profile_payload(
        self,
        *,
        owner_id: str,
        actor_role: str,
        raw_load_units: float,
        critical_count: int,
        active_restriction_count: int,
        cases_by_id: Dict[str, Dict[str, Any]],
        persisted_record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resolved_persisted_record = dict(persisted_record or {})
        baseline = self._capacity_baseline(owner_id=owner_id, actor_role=actor_role)
        overlay = self._observed_capacity_overlay(owner_id=owner_id, cases_by_id=cases_by_id, baseline=baseline)
        effective_capacity_units = self._effective_capacity_units(baseline=baseline, overlay=overlay)
        calibrated_load_score = self._calibrated_load_score(
            raw_load_units=raw_load_units,
            effective_capacity_units=effective_capacity_units,
            critical_count=critical_count,
            active_restriction_count=active_restriction_count,
            baseline=baseline,
        )
        return {
            "capacityUnitsPerDay": baseline["capacityUnitsPerDay"],
            "criticalCaseLimit": baseline["criticalCaseLimit"],
            "activeRestrictionLimit": baseline["activeRestrictionLimit"],
            "slaHours": baseline["slaHours"],
            "roleMultiplier": baseline["roleMultiplier"],
            "enabled": baseline["enabled"],
            "effectiveCapacityUnits": effective_capacity_units,
            "calibratedLoadScore": calibrated_load_score,
            "observedOverlay": overlay,
            "baselineConfigVersion": self.CAPACITY_BASELINE_VERSION,
            "hasPersistentOverride": str(resolved_persisted_record.get("mode") or "") == "active",
            "overrideMode": str(resolved_persisted_record.get("mode") or "inherited"),
            "overrideUpdatedAt": resolved_persisted_record.get("updatedAt"),
            "overrideValues": dict(resolved_persisted_record.get("payload") or {}),
        }

    def _predict_calibrated_load_score(
        self,
        *,
        owner_row: Dict[str, Any],
        additional_units: float = 0.0,
        additional_critical: int = 0,
        additional_active_restriction: int = 0,
    ) -> float:
        return self._calibrated_load_score(
            raw_load_units=float(owner_row.get("rawLoadUnits") or 0.0) + float(additional_units),
            effective_capacity_units=float(owner_row.get("effectiveCapacityUnits") or 0.0),
            critical_count=int(owner_row.get("criticalCount") or 0) + int(additional_critical),
            active_restriction_count=int(owner_row.get("activeRestrictionCount") or 0) + int(additional_active_restriction),
            baseline={
                "criticalCaseLimit": int(owner_row.get("criticalCaseLimit") or 0),
                "activeRestrictionLimit": int(owner_row.get("activeRestrictionLimit") or 0),
            },
        )

    def _build_rebalance_preview(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        workload = self._owner_workload_rows(cases)
        owner_rows = {str(item.get("ownerId") or ""): item for item in workload if str(item.get("ownerId") or "").strip()}
        actionable_cases = [item for item in cases if self._is_actionable_case(item)]
        if not actionable_cases or not owner_rows:
            return {
                "eligibleCaseIds": [],
                "skippedCaseIds": [],
                "perCaseOutcome": [],
                "aggregateDelta": {"eligibleCount": 0, "skippedCount": 0, "ownerDelta": {}},
                "ownerAssignments": {},
            }
        per_case_outcome: List[Dict[str, Any]] = []
        owner_assignments: Dict[str, str] = {}
        owner_delta: Dict[str, Dict[str, int]] = {
            owner_id: {"incoming": 0, "outgoing": 0}
            for owner_id in owner_rows.keys()
        }
        ordered_cases = sorted(
            actionable_cases,
            key=lambda item: (
                -self._case_load_units(item),
                -self._severity_weight(str(item.get("severity") or "medium")),
                str(item.get("due_at") or ""),
                str(item.get("case_id") or ""),
            ),
        )
        for case in ordered_cases:
            case_id = str(case.get("case_id") or "")
            current_owner_id = str((case.get("workflow_summary") or {}).get("owner_id") or case.get("owner_id") or "").strip()
            current_owner_row = owner_rows.get(current_owner_id)
            additional_units = self._case_load_units(case)
            additional_critical = 1 if str(case.get("severity") or "") == "critical" else 0
            additional_active_restriction = 1 if bool((case.get("restriction") or {}).get("status") == "active") else 0
            candidate_rows = []
            for owner_id, owner_row in owner_rows.items():
                if not bool(owner_row.get("enabled")) or owner_id == current_owner_id:
                    continue
                if additional_critical and int(owner_row.get("criticalCount") or 0) >= int(owner_row.get("criticalCaseLimit") or 0):
                    continue
                if additional_active_restriction and int(owner_row.get("activeRestrictionCount") or 0) >= int(owner_row.get("activeRestrictionLimit") or 0):
                    continue
                candidate_rows.append(owner_row)
            if not candidate_rows:
                continue
            candidate_rows.sort(
                key=lambda owner_row: (
                    self._predict_calibrated_load_score(
                        owner_row=owner_row,
                        additional_units=additional_units,
                        additional_critical=additional_critical,
                        additional_active_restriction=additional_active_restriction,
                    ),
                    int(owner_row.get("overdueCount") or 0),
                    int(owner_row.get("criticalCount") or 0),
                    str(owner_row.get("ownerId") or ""),
                )
            )
            selected_owner_row = candidate_rows[0]
            min_candidate_score = self._predict_calibrated_load_score(
                owner_row=selected_owner_row,
                additional_units=additional_units,
                additional_critical=additional_critical,
                additional_active_restriction=additional_active_restriction,
            )
            current_owner_score = (
                float(current_owner_row.get("calibratedLoadScore") or 0.0)
                if current_owner_row and bool(current_owner_row.get("enabled"))
                else float("inf")
            )
            should_suggest = (not current_owner_id) or (current_owner_score > (min_candidate_score + 1.0))
            if not should_suggest:
                continue
            next_owner_id = str(selected_owner_row.get("ownerId") or "")
            owner_assignments[case_id] = next_owner_id
            if current_owner_id:
                owner_delta.setdefault(current_owner_id, {"incoming": 0, "outgoing": 0})
                owner_delta[current_owner_id]["outgoing"] += 1
            owner_delta.setdefault(next_owner_id, {"incoming": 0, "outgoing": 0})
            owner_delta[next_owner_id]["incoming"] += 1
            per_case_outcome.append(
                {
                    "caseId": case_id,
                    "status": "eligible",
                    "reason": "rebalance_owner_assignment",
                    "currentOwnerId": current_owner_id or None,
                    "nextOwnerId": next_owner_id,
                    "currentPredictedCalibratedLoadScore": None if current_owner_score == float("inf") else round(current_owner_score, 2),
                    "nextPredictedCalibratedLoadScore": round(min_candidate_score, 2),
                }
            )
        eligible_case_ids = [item["caseId"] for item in per_case_outcome]
        skipped_case_ids = [str(item.get("case_id") or "") for item in ordered_cases if str(item.get("case_id") or "") not in set(eligible_case_ids)]
        return {
            "eligibleCaseIds": eligible_case_ids,
            "skippedCaseIds": skipped_case_ids,
            "perCaseOutcome": per_case_outcome,
            "aggregateDelta": {
                "eligibleCount": len(eligible_case_ids),
                "skippedCount": len(skipped_case_ids),
                "ownerDelta": owner_delta,
            },
            "ownerAssignments": owner_assignments,
        }

    def _permission_summary(self, case: Dict[str, Any], *, actor_id: Optional[str], actor_role: Optional[str]) -> Dict[str, Any]:
        privileged = actor_role in {None, "reviewer", "ops", "admin"}
        owner_id = self._owner_for_case(case)
        can_claim = privileged and bool(actor_id) and case.get("status") in {"open", "escalated"}
        can_assign = privileged and bool(actor_id)
        can_add_evidence = privileged and bool(actor_id)
        can_release_restriction = privileged and bool(actor_id) and bool((case.get("restriction") or {}).get("status") == "active") and (not owner_id or owner_id == actor_id)
        can_edit_restriction = privileged and bool(actor_id) and bool((case.get("restriction") or {}).get("status") == "active") and (not owner_id or owner_id == actor_id)
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
            "can_edit_restriction": can_edit_restriction,
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
        target_snapshot = dict(payload.get("target_snapshot") or {}) or None
        target_validation = dict(payload.get("target_validation") or {}) or None
        if not target_validation and target_id:
            try:
                fallback_validation = self._validate_target(
                    target_type=target_type,
                    target_id=str(target_id),
                    account_id=str(account_id or "").strip() or None,
                    world_version_id=str(payload.get("world_version_id") or "").strip() or None,
                    session_id=str(payload.get("session_id") or "").strip() or None,
                    entitlement_id=str(payload.get("entitlement_id") or "").strip() or None,
                )
                target_snapshot = dict(target_snapshot or fallback_validation.get("target_snapshot") or {}) or None
                target_validation = {
                    key: value
                    for key, value in fallback_validation.items()
                    if key != "target_snapshot"
                }
            except ValueError as exc:
                fallback_validation = self._invalid_target_validation(
                    target_type=target_type,
                    target_id=str(target_id),
                    account_id=str(account_id or "").strip() or None,
                    code=str(exc),
                )
                target_snapshot = dict(target_snapshot or fallback_validation.get("target_snapshot") or {}) or None
                target_validation = {
                    key: value
                    for key, value in fallback_validation.items()
                    if key != "target_snapshot"
                }
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
            "world_id": payload.get("world_id") or dict(target_validation.get("target_snapshot") or {}).get("world_id"),
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
            "target_snapshot": target_snapshot,
            "target_validation": target_validation,
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
                        "support_issue_ids": [issue.get("issue_id")] if issue.get("issue_id") else [],
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
            "operator_audit_trail": self.repository.list_audit_logs(
                object_type="governance_case",
                object_id=case_id,
                limit=20,
            ),
            "restriction_history": self.restriction_history(case_id, limit=20).get("entries", []),
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

    def _load_case_record(self, case_id: str) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        return records[0]

    def _diff_snapshots(self, previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        diff: Dict[str, Dict[str, Any]] = {}
        previous_payload = dict(previous or {})
        current_payload = dict(current or {})
        for key in sorted(set(previous_payload) | set(current_payload)):
            if previous_payload.get(key) != current_payload.get(key):
                diff[key] = {"before": previous_payload.get(key), "after": current_payload.get(key)}
        return diff

    def restriction_history(self, case_id: str, *, limit: int = 20) -> Dict[str, Any]:
        _ = self._load_case_record(case_id)
        events = [
            item
            for item in reversed(
                self.repository.list_audit_logs(
                    object_type="governance_case",
                    object_id=case_id,
                    limit=max(limit * 4, 40),
                )
            )
            if str(item.get("action_type") or "") in {
                "governance_restriction_applied",
                "governance_restriction_updated",
                "governance_restriction_released",
            }
        ]
        history: List[Dict[str, Any]] = []
        previous_snapshot: Optional[Dict[str, Any]] = None
        for entry in events:
            raw_payload = dict(entry.get("internal_payload_json") or {})
            action_type = str(entry.get("action_type") or "")
            if action_type == "governance_restriction_applied":
                snapshot = {
                    "restriction_id": raw_payload.get("restriction_id"),
                    "restriction_type": raw_payload.get("restriction_type"),
                    "reason": raw_payload.get("restriction_reason"),
                    "expires_at": raw_payload.get("expires_at"),
                    "status": "active",
                    "applied_at": entry.get("created_at"),
                    "applied_by": entry.get("actor_id"),
                }
            elif action_type == "governance_restriction_updated":
                snapshot = dict(raw_payload.get("next_restriction") or {})
            else:
                snapshot = dict(raw_payload.get("restriction") or {})
            history.append(
                {
                    "auditLogId": entry.get("audit_log_id"),
                    "actionType": action_type,
                    "actorId": entry.get("actor_id"),
                    "createdAt": entry.get("created_at"),
                    "snapshot": snapshot,
                    "diff": self._diff_snapshots(previous_snapshot, snapshot),
                    "rawPayload": raw_payload,
                }
            )
            previous_snapshot = dict(snapshot)
        return {
            "caseId": case_id,
            "entries": history[-limit:],
        }

    def update_case_due_at(
        self,
        case_id: str,
        *,
        due_at: str,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        parsed_due_at = self._parse_datetime(str(due_at or "").strip() or None)
        if parsed_due_at is None:
            raise ValueError("invalid_due_at")
        existing = self._load_case_record(case_id)
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
        previous_due_at = notes.get("due_at")
        notes["due_at"] = parsed_due_at.isoformat()
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
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(reviewer_id or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_case_due_at_updated",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": existing.get("status"),
                    "summary": str(current_case.get("summary") or case_id),
                    "due_at": parsed_due_at.isoformat(),
                },
                internal_payload={
                    "case_id": case_id,
                    "previous_due_at": previous_due_at,
                    "next_due_at": parsed_due_at.isoformat(),
                },
            )
        return self._normalize_case_record(updated)

    def update_case_policy_labels(
        self,
        case_id: str,
        *,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        normalized_add = [str(item).strip() for item in list(add_labels or []) if str(item).strip()]
        normalized_remove = [str(item).strip() for item in list(remove_labels or []) if str(item).strip()]
        if not normalized_add and not normalized_remove:
            raise ValueError("policy_labels_required")
        existing = self._load_case_record(case_id)
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
        previous_labels = list(notes.get("policy_labels") or [])
        next_labels = list(previous_labels)
        for label in normalized_add:
            if label not in next_labels:
                next_labels.append(label)
        for label in normalized_remove:
            next_labels = [item for item in next_labels if item != label]
        notes["policy_labels"] = next_labels
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
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(reviewer_id or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_case_policy_labels_updated",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": existing.get("status"),
                    "summary": str(current_case.get("summary") or case_id),
                    "policy_labels": next_labels,
                },
                internal_payload={
                    "case_id": case_id,
                    "previous_policy_labels": previous_labels,
                    "next_policy_labels": next_labels,
                },
            )
        return self._normalize_case_record(updated)

    def apply_case_restriction(
        self,
        case_id: str,
        *,
        restriction_type: str,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        restriction_reason: Optional[str] = None,
        expires_at: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        normalized_type = str(restriction_type or "").strip()
        if normalized_type not in self.VALID_RESTRICTION_TYPES:
            raise ValueError("invalid_restriction_type")
        parsed_expiry = None
        if str(expires_at or "").strip():
            parsed_expiry = self._parse_datetime(str(expires_at or "").strip())
            if parsed_expiry is None or parsed_expiry <= datetime.now(timezone.utc):
                raise ValueError("invalid_restriction_expiry")
        existing = self._load_case_record(case_id)
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
        if str(current_case.get("target_type") or "") != "account" or not str(current_case.get("account_id") or "").strip():
            raise ValueError("governance_case_restriction_target_ineligible")
        if bool((current_case.get("restriction") or {}).get("status") == "active"):
            raise ValueError("governance_restriction_already_active")
        if not self._is_actionable_case(current_case):
            raise ValueError("governance_case_not_actionable")
        owner_id = self._owner_for_case(current_case)
        acting_reviewer = str(reviewer_id or existing.get("reviewer_id") or "").strip() or None
        if owner_id and acting_reviewer and owner_id != acting_reviewer:
            raise PermissionError("governance_case_owner_required")
        notes["restriction"] = {
            "restriction_id": "restriction_%s" % uuid4().hex[:10],
            "restriction_type": normalized_type,
            "scope": {
                "reader_access_block": "reader",
                "author_access_block": "author",
                "checkout_block": "checkout",
                "account_hold": "account",
            }[normalized_type],
            "status": "active",
            "reason": str(restriction_reason or "").strip() or current_case.get("summary"),
            "applied_at": utcnow_iso(),
            "applied_by": acting_reviewer,
            "expires_at": parsed_expiry.isoformat() if parsed_expiry else None,
            "released_at": None,
            "released_by": None,
            "release_reason": None,
        }
        policy_labels = list(notes.get("policy_labels") or [])
        if normalized_type not in policy_labels:
            policy_labels.append(normalized_type)
        notes["policy_labels"] = policy_labels
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": case_id,
                "status": existing.get("status"),
                "reviewer_id": acting_reviewer or existing.get("reviewer_id"),
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        normalized = self._normalize_case_record(updated)
        if self.audit is not None:
            restriction = dict(normalized.get("restriction") or {})
            self.audit.record_audit_log(
                actor_id=str(acting_reviewer or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_restriction_applied",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": normalized.get("status"),
                    "summary": str(current_case.get("summary") or case_id),
                    "restriction_type": restriction.get("restriction_type"),
                },
                internal_payload={
                    "case_id": case_id,
                    "restriction_id": restriction.get("restriction_id"),
                    "account_id": current_case.get("account_id"),
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "restriction_type": restriction.get("restriction_type"),
                    "restriction_reason": restriction.get("reason"),
                    "summary": current_case.get("summary"),
                    "description": current_case.get("description"),
                    "expires_at": restriction.get("expires_at"),
                    "support_issue_ids": list(current_case.get("support_issue_ids") or []),
                },
            )
        return normalized

    def _preview_bulk_case_action(
        self,
        case: Dict[str, Any],
        *,
        action: str,
        payload: Dict[str, Any],
        reviewer_id: Optional[str],
        actor_role: Optional[str],
    ) -> Dict[str, Any]:
        owner_id = self._owner_for_case(case)
        permission_summary = self._permission_summary(case, actor_id=reviewer_id, actor_role=actor_role)
        result: Dict[str, Any] = {
            "caseId": case.get("case_id"),
            "currentOwnerId": owner_id,
            "currentStatus": case.get("status"),
            "currentDueAt": case.get("due_at"),
        }
        try:
            if action == "assignOwner":
                owner_assignments = dict(payload.get("owner_assignments") or {})
                next_owner_id = str(owner_assignments.get(str(case.get("case_id") or "")) or payload.get("owner_id") or "").strip()
                if not next_owner_id:
                    raise ValueError("owner_required")
                self._validate_assignable_owner(next_owner_id)
                result.update({"nextOwnerId": next_owner_id, "nextDueAt": payload.get("due_at")})
            elif action == "updateStatus":
                next_status = str(payload.get("status") or "").strip()
                if not next_status:
                    raise ValueError("status_required")
                self._validate_transition(str(case.get("status") or "open"), next_status)
                if next_status in {"resolved", "dismissed"} and not str(payload.get("resolution_notes") or "").strip():
                    raise ValueError("resolution_notes_required")
                if str(case.get("status") or "") in {"in_review", "escalated"} and next_status in {"escalated", "resolved", "dismissed"} and owner_id and reviewer_id != owner_id:
                    raise PermissionError("governance_case_owner_required")
                result.update({"nextStatus": next_status})
            elif action == "updateDueAt":
                parsed_due_at = self._parse_datetime(str(payload.get("due_at") or "").strip() or None)
                if parsed_due_at is None:
                    raise ValueError("invalid_due_at")
                result.update({"nextDueAt": parsed_due_at.isoformat()})
            elif action == "addPolicyLabels":
                next_labels = [str(item).strip() for item in list(payload.get("policy_labels") or []) if str(item).strip()]
                if not next_labels:
                    raise ValueError("policy_labels_required")
                result.update({"nextPolicyLabels": sorted(set(list(case.get("policy_labels") or []) + next_labels))})
            elif action == "removePolicyLabels":
                next_labels = [str(item).strip() for item in list(payload.get("policy_labels") or []) if str(item).strip()]
                if not next_labels:
                    raise ValueError("policy_labels_required")
                result.update({"nextPolicyLabels": [item for item in list(case.get("policy_labels") or []) if item not in next_labels]})
            elif action == "applyRestriction":
                normalized_type = str(payload.get("restriction_type") or "").strip()
                if normalized_type not in self.VALID_RESTRICTION_TYPES:
                    raise ValueError("invalid_restriction_type")
                if bool((case.get("restriction") or {}).get("status") == "active"):
                    raise ValueError("governance_restriction_already_active")
                if str(case.get("target_type") or "") != "account" or not str(case.get("account_id") or "").strip():
                    raise ValueError("governance_case_restriction_target_ineligible")
                if not self._is_actionable_case(case):
                    raise ValueError("governance_case_not_actionable")
                if not permission_summary.get("can_edit_restriction") and owner_id:
                    raise PermissionError("governance_case_owner_required")
                if str(payload.get("expires_at") or "").strip():
                    parsed_expiry = self._parse_datetime(str(payload.get("expires_at") or "").strip())
                    if parsed_expiry is None or parsed_expiry <= datetime.now(timezone.utc):
                        raise ValueError("invalid_restriction_expiry")
                result.update({"nextRestrictionType": normalized_type})
            else:
                raise ValueError("unsupported_bulk_action")
        except (ValueError, PermissionError) as exc:
            return {**result, "status": "skipped", "reason": str(exc)}
        return {**result, "status": "eligible"}

    def owner_workload(
        self,
        *,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        case_type: Optional[str] = None,
        severity: Optional[str] = None,
        target_type: Optional[str] = None,
        has_active_restriction: Optional[bool] = None,
        overdue_only: bool = False,
        unassigned_only: bool = False,
        search: Optional[str] = None,
        selected_case_ids: Optional[List[str]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        cases = self.list_cases(limit=max(limit * 5, 500)).get("cases", [])
        filtered_cases = self._filter_queue_cases(
            cases,
            status=status,
            owner_id=owner_id,
            case_type=case_type,
            severity=severity,
            target_type=target_type,
            has_active_restriction=has_active_restriction,
            overdue_only=overdue_only,
            unassigned_only=unassigned_only,
            search=search,
        )
        case_rows = [self._queue_case_row(item) for item in filtered_cases[:limit]]
        owner_workload = self._owner_workload_rows(filtered_cases)
        rebalance_preview = self._build_rebalance_preview(filtered_cases)
        selection_limit = 50
        requested_selected_case_ids = [str(item).strip() for item in list(selected_case_ids or []) if str(item).strip()]
        truncated_selected_case_ids = requested_selected_case_ids[:selection_limit]
        visible_case_ids = {str(item.get("case_id") or "") for item in case_rows if str(item.get("case_id") or "").strip()}
        retained_selected_case_ids = [item for item in truncated_selected_case_ids if item in visible_case_ids]
        dropped_case_ids = [item for item in truncated_selected_case_ids if item not in visible_case_ids]
        selection_truncated = len(requested_selected_case_ids) > selection_limit
        return {
            "queueSummary": {
                "totalCaseCount": len(filtered_cases),
                "openCount": sum(1 for item in filtered_cases if str(item.get("status") or "") == "open"),
                "inReviewCount": sum(1 for item in filtered_cases if str(item.get("status") or "") == "in_review"),
                "escalatedCount": sum(1 for item in filtered_cases if str(item.get("status") or "") == "escalated"),
                "overdueCount": sum(1 for item in filtered_cases if bool((item.get("workflow_summary") or {}).get("is_overdue"))),
                "unassignedCount": sum(1 for item in filtered_cases if not str((item.get("workflow_summary") or {}).get("owner_id") or item.get("owner_id") or "").strip()),
                "activeRestrictionCount": sum(1 for item in filtered_cases if bool((item.get("restriction") or {}).get("status") == "active")),
                "criticalCount": sum(1 for item in filtered_cases if str(item.get("severity") or "") == "critical"),
                "rebalanceSuggestionCount": len(list(rebalance_preview.get("eligibleCaseIds") or [])),
            },
            "caseRows": case_rows,
            "ownerWorkload": owner_workload,
            "filters": {
                "status": status,
                "ownerId": owner_id,
                "caseType": case_type,
                "severity": severity,
                "targetType": target_type,
                "hasActiveRestriction": has_active_restriction,
                "overdueOnly": overdue_only,
                "unassignedOnly": unassigned_only,
                "search": search,
                "limit": limit,
            },
            "selectionState": {
                "selectedCaseIds": retained_selected_case_ids,
                "droppedCaseIds": dropped_case_ids,
                "truncated": selection_truncated,
                "maxSelectable": selection_limit,
                "selectVisibleSupported": True,
                "clearSelectionSupported": True,
            },
            "bulkActionCatalog": self._bulk_action_catalog(),
            "rebalancePreview": rebalance_preview,
            "rebalanceMeta": {
                "mode": "balanced_mix",
                "recomputedAt": utcnow_iso(),
                "sourceFilters": {
                    "status": status,
                    "ownerId": owner_id,
                    "caseType": case_type,
                    "severity": severity,
                    "targetType": target_type,
                    "hasActiveRestriction": has_active_restriction,
                    "overdueOnly": overdue_only,
                    "unassignedOnly": unassigned_only,
                    "search": search,
                    "limit": limit,
                },
                "selectionCount": len(retained_selected_case_ids),
            },
            "capacityModel": {
                "windowDays": self.CAPACITY_WINDOW_DAYS,
                "baselineConfigVersion": self.CAPACITY_BASELINE_VERSION,
                "overlayEnabled": True,
                "slaStrategy": "balanced_mix",
            },
            "capacityAdminSurface": self.capacity_admin_surface(),
        }

    def bulk_action_preview(
        self,
        *,
        case_ids: List[str],
        action: str,
        payload: Dict[str, Any],
        reviewer_id: Optional[str],
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_action = str(action or "").strip()
        if normalized_action not in self.BULK_ACTIONS:
            raise ValueError("unsupported_bulk_action")
        per_case_outcome: List[Dict[str, Any]] = []
        affected_account_ids: List[str] = []
        for case_id in [str(item).strip() for item in case_ids if str(item).strip()]:
            try:
                case = self._normalize_case_record(self._load_case_record(case_id))
            except KeyError:
                per_case_outcome.append({"caseId": case_id, "status": "skipped", "reason": "unknown_case"})
                continue
            affected_account_ids.append(str(case.get("account_id") or "").strip())
            per_case_outcome.append(
                self._preview_bulk_case_action(
                    case,
                    action=normalized_action,
                    payload=payload,
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                )
            )
        eligible_case_ids = [str(item.get("caseId") or "") for item in per_case_outcome if str(item.get("status") or "") == "eligible"]
        skipped_case_ids = [str(item.get("caseId") or "") for item in per_case_outcome if str(item.get("status") or "") == "skipped"]
        owner_delta: Dict[str, Dict[str, int]] = {}
        status_delta: Dict[str, Dict[str, int]] = {}
        active_restriction_delta = 0
        for item in per_case_outcome:
            if str(item.get("status") or "") != "eligible":
                continue
            current_owner = str(item.get("currentOwnerId") or "").strip()
            next_owner = str(item.get("nextOwnerId") or "").strip()
            if current_owner != next_owner and next_owner:
                if current_owner:
                    owner_delta.setdefault(current_owner, {"outgoing": 0, "incoming": 0})
                    owner_delta[current_owner]["outgoing"] += 1
                owner_delta.setdefault(next_owner, {"outgoing": 0, "incoming": 0})
                owner_delta[next_owner]["incoming"] += 1
            current_status = str(item.get("currentStatus") or "").strip()
            next_status = str(item.get("nextStatus") or current_status).strip()
            if current_status != next_status and next_status:
                status_delta.setdefault(current_status, {"from": 0, "to": 0})
                status_delta.setdefault(next_status, {"from": 0, "to": 0})
                status_delta[current_status]["from"] += 1
                status_delta[next_status]["to"] += 1
            if normalized_action == "applyRestriction":
                active_restriction_delta += 1
        return {
            "action": normalized_action,
            "eligibleCaseIds": eligible_case_ids,
            "skippedCaseIds": skipped_case_ids,
            "perCaseOutcome": per_case_outcome,
            "aggregateDelta": {
                "eligibleCount": len(eligible_case_ids),
                "skippedCount": len(skipped_case_ids),
                "ownerDelta": owner_delta,
                "statusDelta": status_delta,
                "activeRestrictionDelta": active_restriction_delta,
            },
            "affectedAccountIds": sorted({item for item in affected_account_ids if item}),
        }

    def bulk_action_execute(
        self,
        *,
        case_ids: List[str],
        action: str,
        payload: Dict[str, Any],
        reviewer_id: Optional[str],
        actor_role: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        preview = self.bulk_action_preview(
            case_ids=case_ids,
            action=action,
            payload=payload,
            reviewer_id=reviewer_id,
            actor_role=actor_role,
        )
        executed: List[Dict[str, Any]] = []
        normalized_action = str(action or "").strip()
        for item in list(preview.get("perCaseOutcome") or []):
            if str(item.get("status") or "") != "eligible":
                executed.append({**item, "status": "skipped"})
                continue
            case_id = str(item.get("caseId") or "").strip()
            if normalized_action == "assignOwner":
                owner_assignments = dict(payload.get("owner_assignments") or {})
                owner_id_value = str(owner_assignments.get(case_id) or payload.get("owner_id") or "").strip()
                updated = self.assign_case(
                    case_id,
                    owner_id=owner_id_value,
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    due_at=str(payload.get("due_at") or "").strip() or None,
                    note=str(payload.get("note") or "").strip() or None,
                    source_surface=source_surface,
                )
            elif normalized_action == "updateStatus":
                updated = self.update_case_status(
                    case_id,
                    status=str(payload.get("status") or "").strip(),
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    resolution_notes=str(payload.get("resolution_notes") or "").strip() or None,
                    disposition=str(payload.get("disposition") or "").strip() or None,
                    source_surface=source_surface,
                )
            elif normalized_action == "updateDueAt":
                updated = self.update_case_due_at(
                    case_id,
                    due_at=str(payload.get("due_at") or "").strip(),
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    source_surface=source_surface,
                )
            elif normalized_action == "addPolicyLabels":
                updated = self.update_case_policy_labels(
                    case_id,
                    add_labels=list(payload.get("policy_labels") or []),
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    source_surface=source_surface,
                )
            elif normalized_action == "removePolicyLabels":
                updated = self.update_case_policy_labels(
                    case_id,
                    remove_labels=list(payload.get("policy_labels") or []),
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    source_surface=source_surface,
                )
            else:
                updated = self.apply_case_restriction(
                    case_id,
                    restriction_type=str(payload.get("restriction_type") or "").strip(),
                    reviewer_id=reviewer_id,
                    actor_role=actor_role,
                    restriction_reason=str(payload.get("restriction_reason") or "").strip() or None,
                    expires_at=str(payload.get("expires_at") or "").strip() or None,
                    source_surface=source_surface,
                )
            executed.append({**item, "status": "executed", "updatedCase": self._queue_case_row(updated)})
        return {
            **preview,
            "perCaseOutcome": executed,
            "executedCaseIds": [str(item.get("caseId") or "") for item in executed if str(item.get("status") or "") == "executed"],
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
        target_validation = self._validate_target(
            target_type=target_type,
            target_id=str(payload.get("target_id") or "").strip() or None,
            account_id=str(payload.get("account_id") or "").strip() or None,
            world_version_id=str(payload.get("world_version_id") or "").strip() or None,
            session_id=str(payload.get("session_id") or "").strip() or None,
            entitlement_id=str(payload.get("entitlement_id") or "").strip() or None,
        )
        account_id = target_validation.get("account_id") or (
            payload.get("target_id") if target_type == "account" else None
        )
        changed_at = utcnow_iso()
        notes = {
            "case_id": case_id,
            "case_type": case_type,
            "queue": self._queue_for_case_type(case_type),
            "severity": payload.get("severity", "medium"),
            "owner_id": payload.get("owner_id") or payload.get("reviewer_id"),
            "due_at": payload.get("due_at") or self._default_due_at(case_type=case_type, severity=str(payload.get("severity", "medium"))),
            "target_type": target_type,
            "target_id": target_validation.get("target_id"),
            "account_id": account_id,
            "world_id": payload.get("world_id"),
            "world_version_id": target_validation.get("world_version_id") or payload.get("world_version_id"),
            "session_id": target_validation.get("session_id") or payload.get("session_id"),
            "entitlement_id": target_validation.get("entitlement_id") or payload.get("entitlement_id"),
            "summary": payload.get("summary"),
            "description": payload.get("description"),
            "source": payload.get("source", "ops_manual"),
            "recommended_action": payload.get("recommended_action"),
            "support_issue_ids": list(payload.get("support_issue_ids", [])),
            "resolution_notes": payload.get("resolution_notes"),
            "disposition": payload.get("disposition"),
            "policy_labels": list(payload.get("policy_labels", [])),
            "evidence_refs": self._normalize_evidence_refs(payload.get("evidence_refs")),
            "target_snapshot": dict(target_validation.get("target_snapshot") or {}),
            "target_validation": {
                key: value
                for key, value in target_validation.items()
                if key != "target_snapshot"
            },
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
        normalized = self._normalize_case_record(record)
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(payload.get("reviewer_id") or "ops_unknown"),
                actor_role=str(payload.get("actor_role") or "reviewer"),
                account_id=str(normalized.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=str(normalized.get("case_id") or case_id),
                action_type="governance_case_created",
                source_surface=str(payload.get("source_surface") or "ops_api"),
                customer_visible_payload={
                    "status": normalized.get("status"),
                    "summary": str(normalized.get("summary") or case_id),
                    "case_type": normalized.get("case_type"),
                },
                internal_payload={
                    "case_id": normalized.get("case_id") or case_id,
                    "target_type": normalized.get("target_type"),
                    "target_id": normalized.get("target_id"),
                    "account_id": normalized.get("account_id"),
                    "world_id": normalized.get("world_id"),
                    "world_version_id": normalized.get("world_version_id"),
                    "session_id": normalized.get("session_id"),
                    "entitlement_id": normalized.get("entitlement_id"),
                    "due_at": normalized.get("due_at"),
                    "severity": normalized.get("severity"),
                    "summary": normalized.get("summary"),
                    "description": normalized.get("description"),
                    "target_validation": dict(normalized.get("target_validation") or {}),
                    "support_issue_ids": list(normalized.get("support_issue_ids") or []),
                    "policy_labels": list(normalized.get("policy_labels") or []),
                },
            )
        return normalized

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
        normalized = self._normalize_case_record(updated)
        if self.audit is not None:
            restriction = dict(normalized.get("restriction") or {})
            self.audit.record_audit_log(
                actor_id=str(payload.get("reviewer_id") or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(payload.get("actor_role") or "reviewer"),
                account_id=str(normalized.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=str(normalized.get("case_id") or created["case_id"]),
                action_type="governance_restriction_applied",
                source_surface=str(payload.get("source_surface") or "ops_api"),
                customer_visible_payload={
                    "status": normalized.get("status"),
                    "summary": str(normalized.get("summary") or created["case_id"]),
                    "restriction_type": restriction.get("restriction_type"),
                },
                internal_payload={
                    "case_id": normalized.get("case_id") or created["case_id"],
                    "restriction_id": restriction.get("restriction_id"),
                    "account_id": normalized.get("account_id"),
                    "world_id": normalized.get("world_id"),
                    "world_version_id": normalized.get("world_version_id"),
                    "restriction_type": restriction.get("restriction_type"),
                    "restriction_reason": restriction.get("reason"),
                    "summary": normalized.get("summary"),
                    "description": normalized.get("description"),
                    "expires_at": restriction.get("expires_at"),
                    "support_issue_ids": list(normalized.get("support_issue_ids") or []),
                },
            )
        return normalized

    def update_case_status(
        self,
        case_id: str,
        *,
        status: str,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        disposition: Optional[str] = None,
        source_surface: str = "ops_api",
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
        previous_status = current_status
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
        if self.audit is not None:
            account_id = current_case.get("account_id")
            self.audit.record_audit_log(
                actor_id=str(acting_reviewer or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(account_id or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_case_status_changed",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": status,
                    "summary": str(current_case.get("summary") or case_id),
                    "case_type": current_case.get("case_type"),
                },
                internal_payload={
                    "case_id": case_id,
                    "account_id": account_id,
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "previous_status": previous_status,
                    "next_status": status,
                    "resolution_notes": resolution_notes,
                    "disposition": disposition,
                    "owner_id": owner_id,
                },
            )
        return self._normalize_case_record(updated)

    def assign_case(
        self,
        case_id: str,
        *,
        owner_id: str,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        due_at: Optional[str] = None,
        note: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        validated_owner = self._validate_assignable_owner(owner_id)
        resolved_owner_id = str(validated_owner.get("actor_id") or owner_id).strip()
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
        previous_owner_id = notes.get("owner_id") or existing.get("reviewer_id")
        notes["owner_id"] = resolved_owner_id
        if due_at:
            notes["due_at"] = due_at
        ownership_events = list(notes.get("ownership_events", []))
        ownership_events.append(
            {
                "owner_id": resolved_owner_id,
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
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(reviewer_id or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_case_assigned",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": existing.get("status"),
                    "summary": str(current_case.get("summary") or case_id),
                    "owner_id": resolved_owner_id,
                },
                internal_payload={
                    "case_id": case_id,
                    "account_id": current_case.get("account_id"),
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "previous_owner_id": previous_owner_id,
                    "next_owner_id": resolved_owner_id,
                    "note": note,
                    "due_at": due_at,
                },
            )
        return self._normalize_case_record(updated)

    def append_case_evidence(
        self,
        case_id: str,
        *,
        reviewer_id: Optional[str],
        actor_role: Optional[str] = None,
        title: str,
        preview: str,
        ref_id: Optional[str] = None,
        kind: str = "note",
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=case_id)
        if not records:
            raise KeyError("unknown_governance_case:%s" % case_id)
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        current_case = self._normalize_case_record(existing)
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
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(reviewer_id or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=case_id,
                action_type="governance_case_evidence_appended",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": current_case.get("status"),
                    "summary": str(current_case.get("summary") or case_id),
                    "evidence_title": title,
                    "evidence_kind": kind,
                },
                internal_payload={
                    "case_id": case_id,
                    "account_id": current_case.get("account_id"),
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "title": title,
                    "preview": preview,
                    "ref_id": ref_id,
                    "kind": kind,
                },
            )
        return self._normalize_case_record(updated)

    def update_restriction(
        self,
        restriction_id: str,
        *,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        restriction_type: Optional[str] = None,
        restriction_reason: Optional[str] = None,
        expires_at: Optional[str] = None,
        source_surface: str = "ops_api",
    ) -> Dict[str, Any]:
        if restriction_type is None and restriction_reason is None and expires_at is None:
            raise ValueError("governance_restriction_update_empty")
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
        current_case = dict(target)
        current_restriction = dict(current_case.get("restriction") or {})
        if current_restriction.get("status") != "active":
            raise ValueError("governance_restriction_not_editable")
        owner_id = self._owner_for_case(current_case)
        acting_reviewer = str(reviewer_id or current_case.get("reviewer_id") or "").strip() or None
        if owner_id and acting_reviewer and owner_id != acting_reviewer:
            raise PermissionError("governance_case_owner_required")
        if actor_role and actor_role not in self.VALID_OWNER_ROLES:
            raise PermissionError("reviewer_or_ops_required")
        next_restriction = dict(current_restriction)
        if restriction_type is not None:
            normalized_type = str(restriction_type or "").strip()
            if normalized_type not in self.VALID_RESTRICTION_TYPES:
                raise ValueError("invalid_restriction_type")
            next_restriction["restriction_type"] = normalized_type
            next_restriction["scope"] = {
                "reader_access_block": "reader",
                "author_access_block": "author",
                "checkout_block": "checkout",
                "account_hold": "account",
            }[normalized_type]
        if restriction_reason is not None:
            next_restriction["reason"] = str(restriction_reason or "").strip() or None
        if expires_at is not None:
            normalized_expires_at = str(expires_at or "").strip() or None
            if normalized_expires_at:
                parsed_expires_at = self._parse_datetime(normalized_expires_at)
                if parsed_expires_at is None or parsed_expires_at <= datetime.now(timezone.utc):
                    raise ValueError("invalid_restriction_expiry")
                next_restriction["expires_at"] = parsed_expires_at.isoformat()
            else:
                next_restriction["expires_at"] = None
        records = self.repository.list_review_records(asset_type="governance_case", asset_id=current_case["case_id"])
        existing = records[0]
        notes = parse_governance_notes(existing.get("notes"))
        notes["restriction"] = next_restriction
        updated = self.repository.save_review_record(
            {
                "review_id": existing.get("review_id"),
                "asset_type": "governance_case",
                "asset_id": current_case["case_id"],
                "status": existing.get("status"),
                "reviewer_id": acting_reviewer or existing.get("reviewer_id"),
                "risk_rating": existing.get("risk_rating"),
                "notes": json.dumps(notes, ensure_ascii=False),
            }
        )
        normalized = self._normalize_case_record(updated)
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(acting_reviewer or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=str(current_case.get("case_id") or restriction_id),
                action_type="governance_restriction_updated",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": normalized.get("status"),
                    "summary": str(current_case.get("summary") or current_case.get("case_id") or restriction_id),
                    "restriction_type": (normalized.get("restriction") or {}).get("restriction_type"),
                },
                internal_payload={
                    "case_id": current_case.get("case_id"),
                    "restriction_id": current_restriction.get("restriction_id") or restriction_id,
                    "account_id": current_case.get("account_id"),
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "previous_restriction": current_restriction,
                    "next_restriction": normalized.get("restriction"),
                },
            )
        return normalized

    def release_restriction(
        self,
        restriction_id: str,
        *,
        reviewer_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        release_reason: Optional[str] = None,
        source_surface: str = "ops_api",
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
        current_case = dict(target)
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
        if self.audit is not None:
            self.audit.record_audit_log(
                actor_id=str(acting_reviewer or existing.get("reviewer_id") or "ops_unknown"),
                actor_role=str(actor_role or "reviewer"),
                account_id=str(current_case.get("account_id") or "") or None,
                object_type="governance_case",
                object_id=str(current_case.get("case_id") or target["case_id"]),
                action_type="governance_restriction_released",
                source_surface=source_surface,
                customer_visible_payload={
                    "status": "released",
                    "summary": str(current_case.get("summary") or target["case_id"]),
                    "restriction_type": restriction.get("restriction_type"),
                },
                internal_payload={
                    "case_id": current_case.get("case_id") or target["case_id"],
                    "restriction_id": restriction.get("restriction_id") or restriction_id,
                    "account_id": current_case.get("account_id"),
                    "world_id": current_case.get("world_id"),
                    "world_version_id": current_case.get("world_version_id"),
                    "release_reason": release_reason,
                    "restriction": restriction,
                },
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
