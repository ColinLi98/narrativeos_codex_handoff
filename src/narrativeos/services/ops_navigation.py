from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .governance import GovernanceService
from .ops_account_workspace import OpsAccountWorkspaceService
from .ops_alerting import OpsAlertingService
from .ops_release_workspace import OpsReleaseWorkspaceService
from .ops_traceability import OpsTraceabilityService


class OpsNavigationService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        account_workspace_service: OpsAccountWorkspaceService,
        release_workspace_service: OpsReleaseWorkspaceService,
        alerting_service: OpsAlertingService,
        governance_service: GovernanceService,
        ops_traceability_service: OpsTraceabilityService,
    ) -> None:
        self.repository = repository
        self.account_workspace = account_workspace_service
        self.release_workspace = release_workspace_service
        self.alerting = alerting_service
        self.governance = governance_service
        self.traceability = ops_traceability_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _world_id_for_version(self, world_version_id: Optional[str]) -> Optional[str]:
        if not world_version_id:
            return None
        try:
            return self.repository.get_world_version(world_version_id).world_id
        except KeyError:
            return None

    def _world_version_exists(self, world_version_id: Optional[str]) -> bool:
        if not world_version_id:
            return False
        try:
            self.repository.get_world_version(world_version_id)
            return True
        except KeyError:
            return False

    def _mark_stale_ref(
        self,
        *,
        stale_refs: Dict[str, Dict[str, Any]],
        context_warnings: List[str],
        resolution_steps: List[str],
        ref_type: str,
        ref_id: Optional[str],
        reason: str,
    ) -> None:
        if not ref_id:
            return
        stale_refs[ref_type] = {
            "ref_id": ref_id,
            "reason": reason,
            "status": "stale_or_unknown",
        }
        context_warnings.append(f"stale_{ref_type}_ref:{ref_id}")
        resolution_steps.append(f"{ref_type}_id -> stale_or_unknown (soft-failed)")

    def _safe_case_detail(
        self,
        case_id: Optional[str],
        *,
        stale_refs: Dict[str, Dict[str, Any]],
        context_warnings: List[str],
        resolution_steps: List[str],
    ) -> Optional[Dict[str, Any]]:
        if not case_id:
            return None
        try:
            case_detail = self.governance.case_detail(case_id)
            resolution_steps.append("case_id -> account_id/world_id/world_version_id")
            return case_detail
        except KeyError as exc:
            self._mark_stale_ref(
                stale_refs=stale_refs,
                context_warnings=context_warnings,
                resolution_steps=resolution_steps,
                ref_type="case",
                ref_id=case_id,
                reason=str(exc),
            )
            return None

    def _safe_release_workspace(
        self,
        world_id: Optional[str],
        *,
        stale_refs: Dict[str, Dict[str, Any]],
        context_warnings: List[str],
        resolution_steps: List[str],
    ) -> Optional[Dict[str, Any]]:
        if not world_id:
            return None
        workspace = self.release_workspace.world_release_workspace(world_id=world_id, limit=10)
        has_versions = bool((workspace.get("world_status") or {}).get("versions"))
        has_selected = bool(workspace.get("selected_world_version_id"))
        has_published = bool((workspace.get("release_summary") or {}).get("published_version"))
        if not (has_versions or has_selected or has_published):
            self._mark_stale_ref(
                stale_refs=stale_refs,
                context_warnings=context_warnings,
                resolution_steps=resolution_steps,
                ref_type="world",
                ref_id=world_id,
                reason=f"unknown_world:{world_id}",
            )
            return None
        resolution_steps.append("world_id -> selected release workspace")
        return workspace

    def _resolve_context(
        self,
        *,
        account_id: Optional[str],
        world_id: Optional[str],
        case_id: Optional[str],
        alert_id: Optional[str],
    ) -> Dict[str, Any]:
        resolved = {
            "account_id": account_id,
            "world_id": world_id,
            "world_version_id": None,
            "case_id": case_id,
            "alert_id": alert_id,
        }
        resolution_steps: List[str] = []
        context_warnings: List[str] = []
        case_detail: Optional[Dict[str, Any]] = None
        alert_detail: Optional[Dict[str, Any]] = None
        stale_refs: Dict[str, Dict[str, Any]] = {}

        if case_id:
            case_detail = self._safe_case_detail(
                case_id,
                stale_refs=stale_refs,
                context_warnings=context_warnings,
                resolution_steps=resolution_steps,
            )
            if case_detail:
                resolved["account_id"] = resolved["account_id"] or case_detail.get("account_id")
                resolved["world_version_id"] = case_detail.get("world_version_id")
                resolved["world_id"] = resolved["world_id"] or case_detail.get("world_id") or self._world_id_for_version(case_detail.get("world_version_id"))
            else:
                resolved["case_id"] = None

        if alert_id:
            try:
                alert_detail = self.alerting.alert_detail(alert_id, account_id=resolved["account_id"])
                alert = dict(alert_detail.get("alert") or {})
                investigation_ref = dict(alert.get("investigation_ref") or {})
                resolved["account_id"] = resolved["account_id"] or alert.get("account_id") or investigation_ref.get("account_id")
                resolved["case_id"] = resolved["case_id"] or investigation_ref.get("case_id")
                resolved["world_version_id"] = resolved["world_version_id"] or investigation_ref.get("world_version_id")
                resolved["world_id"] = resolved["world_id"] or self._world_id_for_version(resolved["world_version_id"])
                resolution_steps.append("alert_id -> account_id/case_id/world_version_id")
                if resolved["case_id"] and not case_detail:
                    case_detail = self._safe_case_detail(
                        resolved["case_id"],
                        stale_refs=stale_refs,
                        context_warnings=context_warnings,
                        resolution_steps=resolution_steps,
                    )
                    if case_detail:
                        resolved["account_id"] = resolved["account_id"] or case_detail.get("account_id")
                        resolved["world_id"] = resolved["world_id"] or case_detail.get("world_id") or self._world_id_for_version(case_detail.get("world_version_id"))
                    else:
                        resolved["case_id"] = None
            except KeyError as exc:
                self._mark_stale_ref(
                    stale_refs=stale_refs,
                    context_warnings=context_warnings,
                    resolution_steps=resolution_steps,
                    ref_type="alert",
                    ref_id=alert_id,
                    reason=str(exc),
                )
                resolved["alert_id"] = None

        release_workspace = self._safe_release_workspace(
            resolved["world_id"],
            stale_refs=stale_refs,
            context_warnings=context_warnings,
            resolution_steps=resolution_steps,
        )
        if release_workspace:
            resolved["world_version_id"] = resolved["world_version_id"] or release_workspace.get("selected_world_version_id")
        else:
            resolved["world_id"] = None

        if resolved["world_version_id"] and not self._world_version_exists(resolved["world_version_id"]):
            self._mark_stale_ref(
                stale_refs=stale_refs,
                context_warnings=context_warnings,
                resolution_steps=resolution_steps,
                ref_type="world_version",
                ref_id=resolved["world_version_id"],
                reason=f"unknown_world_version:{resolved['world_version_id']}",
            )
            resolved["world_version_id"] = None

        if resolved["world_version_id"] and not resolved["world_id"]:
            resolved["world_id"] = self._world_id_for_version(resolved["world_version_id"])
            if resolved["world_id"]:
                resolution_steps.append("world_version_id -> world_id")
                if not release_workspace:
                    release_workspace = self._safe_release_workspace(
                        resolved["world_id"],
                        stale_refs=stale_refs,
                        context_warnings=context_warnings,
                        resolution_steps=resolution_steps,
                    )

        if resolved["account_id"]:
            account_workspace = self.account_workspace.account_workspace(account_id=resolved["account_id"], limit=10)
            resolution_steps.append("account_id -> account workspace")
        else:
            account_workspace = None

        return {
            "resolved": resolved,
            "case_detail": case_detail,
            "alert_detail": alert_detail,
            "account_workspace": account_workspace,
            "release_workspace": release_workspace,
            "resolution_steps": resolution_steps,
            "context_warnings": context_warnings,
            "stale_refs": stale_refs,
        }

    def _navigation_targets(
        self,
        *,
        resolved: Dict[str, Any],
        account_workspace: Optional[Dict[str, Any]],
        release_workspace: Optional[Dict[str, Any]],
        case_detail: Optional[Dict[str, Any]],
        alert_detail: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        targets: List[Dict[str, Any]] = []
        if resolved.get("account_id"):
            targets.append(
                {
                    "target_id": "account_workspace",
                    "label": "Account Workspace",
                    "kind": "account",
                    "active": bool(account_workspace),
                    "prefill": {"account_id": resolved["account_id"]},
                }
            )
        if resolved.get("world_id"):
            targets.append(
                {
                    "target_id": "release_workspace",
                    "label": "Release Workspace",
                    "kind": "world",
                    "active": bool(release_workspace),
                    "prefill": {"world_id": resolved["world_id"]},
                }
            )
        if resolved.get("case_id"):
            targets.append(
                {
                    "target_id": "governance_case",
                    "label": "Governance Case",
                    "kind": "case",
                    "active": bool(case_detail),
                    "prefill": {"case_id": resolved["case_id"], "account_id": resolved.get("account_id")},
                }
            )
        if resolved.get("alert_id"):
            targets.append(
                {
                    "target_id": "alert_detail",
                    "label": "Alert Detail",
                    "kind": "alert",
                    "active": bool(alert_detail),
                    "prefill": {"alert_id": resolved["alert_id"], "account_id": resolved.get("account_id")},
                }
            )
        if resolved.get("account_id") or resolved.get("world_version_id") or resolved.get("case_id"):
            targets.append(
                {
                    "target_id": "investigation",
                    "label": "Unified Investigation",
                    "kind": "investigation",
                    "active": True,
                    "prefill": {
                        "account_id": resolved.get("account_id"),
                        "world_version_id": resolved.get("world_version_id"),
                        "case_id": resolved.get("case_id"),
                    },
                }
            )
        return targets

    def _follow_up_actions(
        self,
        *,
        resolved: Dict[str, Any],
        account_workspace: Optional[Dict[str, Any]],
        release_workspace: Optional[Dict[str, Any]],
        case_detail: Optional[Dict[str, Any]],
        alert_detail: Optional[Dict[str, Any]],
        stale_refs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        stale_refs = dict(stale_refs or {})
        if stale_refs:
            actions.append(
                {
                    "action_id": "navigation::clear_stale_refs",
                    "label": "Clear Stale Refs",
                    "handler": "clear_stale_refs",
                    "mode": "execute",
                    "reason": "remove stale refs from the control plane before the next drill-down",
                    "priority": 0,
                    "prefill": {
                        "account_id": resolved.get("account_id"),
                        "world_id": resolved.get("world_id"),
                        "world_version_id": resolved.get("world_version_id"),
                        "case_id": resolved.get("case_id"),
                        "alert_id": resolved.get("alert_id"),
                        "stale_refs": stale_refs,
                    },
                    "source_surface": "navigation_model",
                }
            )
            actions.append(
                {
                    "action_id": "navigation::resync_navigation_context",
                    "label": "Re-sync From Valid Context",
                    "handler": "resync_navigation_context",
                    "mode": "execute",
                    "reason": "propagate surviving account/world/case context into the linked Ops workspaces",
                    "priority": 1,
                    "prefill": {
                        "account_id": resolved.get("account_id"),
                        "world_id": resolved.get("world_id"),
                        "world_version_id": resolved.get("world_version_id"),
                        "case_id": resolved.get("case_id"),
                        "alert_id": resolved.get("alert_id"),
                        "stale_refs": stale_refs,
                    },
                    "source_surface": "navigation_model",
                }
            )
        for item in (account_workspace or {}).get("action_pack", []):
            actions.append({**item, "source_surface": "account_workspace"})
        for item in (release_workspace or {}).get("action_pack", []):
            actions.append({**item, "source_surface": "release_workspace"})
        for item in (alert_detail or {}).get("alert", {}).get("recommended_actions", []):
            actions.append(
                {
                    "action_id": f"alert::{item}",
                    "label": item.replace("_", " "),
                    "handler": "open_alert_detail",
                    "mode": "navigate",
                    "reason": item,
                    "priority": 1,
                    "prefill": dict((alert_detail or {}).get("alert", {}).get("investigation_ref") or {}),
                    "source_surface": "alert_detail",
                }
            )
        for item in (case_detail or {}).get("recommended_next_actions", []):
            actions.append(
                {
                    "action_id": f"governance::{item}",
                    "label": item.replace("_", " "),
                    "handler": "open_governance_case",
                    "mode": "navigate",
                    "reason": item,
                    "priority": 2,
                    "prefill": {"case_id": (case_detail or {}).get("case_id"), "account_id": (case_detail or {}).get("account_id")},
                    "source_surface": "governance_case",
                }
            )
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in actions:
            if item["action_id"] not in deduped or item.get("priority", 99) < deduped[item["action_id"]].get("priority", 99):
                deduped[item["action_id"]] = item
        return sorted(deduped.values(), key=lambda entry: (entry.get("priority", 99), entry.get("label", "")))[:8]

    def _escalation_summary(
        self,
        *,
        resolved: Dict[str, Any],
        account_workspace: Optional[Dict[str, Any]],
        release_workspace: Optional[Dict[str, Any]],
        case_detail: Optional[Dict[str, Any]],
        alert_detail: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if alert_detail and (alert_detail.get("alert") or {}).get("status") not in {"resolved", "suppressed"}:
            return {
                "status": "alert_active",
                "recommended_target": "alert_detail",
                "recommended_reason": (alert_detail.get("alert") or {}).get("summary") or "review active alert first",
                "escalation_path": ["alert_detail", "investigation", "governance_case", "release_workspace"],
            }
        if case_detail and case_detail.get("status") in {"open", "in_review", "escalated"}:
            return {
                "status": "case_active",
                "recommended_target": "governance_case",
                "recommended_reason": (case_detail.get("workflow_summary") or {}).get("owner_id") or "governance case requires operator follow-up",
                "escalation_path": ["governance_case", "investigation", "account_workspace"],
            }
        if release_workspace and not (release_workspace.get("release_summary") or {}).get("publish_ready"):
            return {
                "status": "release_blocked",
                "recommended_target": "release_workspace",
                "recommended_reason": (release_workspace.get("release_summary") or {}).get("recommended_action") or "release is blocked",
                "escalation_path": ["release_workspace", "investigation", "governance_case"],
            }
        if account_workspace and (account_workspace.get("workspace_summary") or {}).get("health_status") in {"critical", "needs_attention"}:
            return {
                "status": "account_attention",
                "recommended_target": "account_workspace",
                "recommended_reason": (account_workspace.get("workspace_summary") or {}).get("recommended_path") or "account requires attention",
                "escalation_path": ["account_workspace", "alert_detail", "investigation"],
            }
        return {
            "status": "stable",
            "recommended_target": "investigation",
            "recommended_reason": "no urgent escalation target; use investigation for cross-surface context",
            "escalation_path": ["investigation", "account_workspace", "release_workspace"],
        }

    def _linked_context(
        self,
        *,
        resolved: Dict[str, Any],
        account_workspace: Optional[Dict[str, Any]],
        release_workspace: Optional[Dict[str, Any]],
        case_detail: Optional[Dict[str, Any]],
        alert_detail: Optional[Dict[str, Any]],
        stale_refs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return {
            "account_id": resolved.get("account_id"),
            "world_id": resolved.get("world_id"),
            "world_version_id": resolved.get("world_version_id"),
            "case_id": resolved.get("case_id"),
            "alert_id": resolved.get("alert_id"),
            "related_alert_ids": list((account_workspace or {}).get("linked_context", {}).get("alert_ids", [])),
            "related_governance_case_ids": list((account_workspace or {}).get("linked_context", {}).get("governance_case_ids", [])),
            "related_world_version_ids": list((account_workspace or {}).get("linked_context", {}).get("recent_world_version_ids", [])),
            "rollback_target_ids": list((release_workspace or {}).get("linked_context", {}).get("rollback_target_ids", [])),
            "review_ids": list((release_workspace or {}).get("linked_context", {}).get("review_ids", [])),
            "alert_investigation_ref": dict((alert_detail or {}).get("alert", {}).get("investigation_ref") or {}),
            "case_owner_id": (case_detail or {}).get("workflow_summary", {}).get("owner_id"),
            "stale_refs": stale_refs or {},
        }

    def navigation_model(
        self,
        *,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        case_id: Optional[str] = None,
        alert_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_bundle = self._resolve_context(
            account_id=account_id,
            world_id=world_id,
            case_id=case_id,
            alert_id=alert_id,
        )
        resolved = resolved_bundle["resolved"]
        account_workspace = resolved_bundle["account_workspace"]
        release_workspace = resolved_bundle["release_workspace"]
        case_detail = resolved_bundle["case_detail"]
        alert_detail = resolved_bundle["alert_detail"]
        return {
            "generated_at": self._utcnow(),
            "active_context": resolved,
            "context_resolution": resolved_bundle["resolution_steps"],
            "context_warnings": resolved_bundle["context_warnings"],
            "escalation_summary": self._escalation_summary(
                resolved=resolved,
                account_workspace=account_workspace,
                release_workspace=release_workspace,
                case_detail=case_detail,
                alert_detail=alert_detail,
            ),
            "linked_context": self._linked_context(
                resolved=resolved,
                account_workspace=account_workspace,
                release_workspace=release_workspace,
                case_detail=case_detail,
                alert_detail=alert_detail,
                stale_refs=resolved_bundle["stale_refs"],
            ),
            "navigation_targets": self._navigation_targets(
                resolved=resolved,
                account_workspace=account_workspace,
                release_workspace=release_workspace,
                case_detail=case_detail,
                alert_detail=alert_detail,
            ),
            "follow_up_actions": self._follow_up_actions(
                resolved=resolved,
                account_workspace=account_workspace,
                release_workspace=release_workspace,
                case_detail=case_detail,
                alert_detail=alert_detail,
                stale_refs=resolved_bundle["stale_refs"],
            ),
        }
