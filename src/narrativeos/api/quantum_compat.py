from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..models import NarrativeState
from ..services.auth import AuthServiceError
from ..services.choice_semantics import build_choice_impacts
from ..services.reader_generation_jobs import READER_GENERATION_JOB_TYPE
from ..services.sessions import ReaderContinueCommand, build_reader_continuity_contract
from .auth import _auth_export_payload


router = APIRouter(prefix="/api/v1", tags=["quantum-compat"])


class QuantumAuthRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    displayName: str


class QuantumAuthLoginRequest(BaseModel):
    identifier: str
    password: str


class QuantumAuthRefreshRequest(BaseModel):
    refreshToken: str


class QuantumAuthProfileUpdateRequest(BaseModel):
    displayName: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class QuantumMembershipSubscribeRequest(BaseModel):
    planId: str


class QuantumInkPurchaseRequest(BaseModel):
    packageId: str


class QuantumSettingsPreferencesRequest(BaseModel):
    immersiveEffects: Optional[bool] = None
    autoRenderArt: Optional[bool] = None
    privacyMode: Optional[bool] = None
    streamSpeed: Optional[int] = None
    particleDensity: Optional[int] = None
    fontSize: Optional[str] = None
    theme: Optional[str] = None


class QuantumSoulPreferencesRequest(BaseModel):
    genres: Optional[List[str]] = None
    styles: Optional[List[str]] = None
    privacyMode: Optional[str] = None


class QuantumLibraryFollowRequest(BaseModel):
    targetType: str
    targetId: str


class QuantumSettingsAccountPasswordChangeRequest(BaseModel):
    currentPassword: str
    newPassword: str


class QuantumSettingsAccountEmailChangeRequest(BaseModel):
    newEmail: str
    currentPassword: str


class QuantumSettingsAccountEmailConfirmRequest(BaseModel):
    token: str


class QuantumInkCheckoutCompleteRequest(BaseModel):
    accountId: Optional[str] = None


class QuantumLegacyCheckoutSessionRequest(BaseModel):
    packageId: str
    amount: Optional[float] = None
    currency: str = "usd"
    price: Optional[float] = None


class QuantumLegacySubscriptionSessionRequest(BaseModel):
    tierId: str
    currency: str = "usd"


class QuantumShowcaseCommentRequest(BaseModel):
    content: str


class QuantumShowcaseTipRequest(BaseModel):
    amount: int


class QuantumStoryImportStartRequest(BaseModel):
    targetType: str
    targetId: str
    deferBootstrap: Optional[bool] = None


class QuantumStoryChoiceRequest(BaseModel):
    sessionId: str
    choiceId: str
    nodeId: str


class QuantumStoryBookmarkRequest(BaseModel):
    nodeId: str


class QuantumOpsReviewAssignRequest(BaseModel):
    pass


class QuantumOpsReviewStatusRequest(BaseModel):
    status: str


class QuantumOpsReviewDecisionRequest(BaseModel):
    decision: str


class QuantumOpsGrantSubscriptionRequest(BaseModel):
    tierId: str


class QuantumOpsGrantWalletRequest(BaseModel):
    walletType: str
    amount: float
    tierId: Optional[str] = None


class QuantumOpsAlertMutationRequest(BaseModel):
    accountId: Optional[str] = None
    note: Optional[str] = None


class QuantumOpsGovernanceAssignRequest(BaseModel):
    accountId: Optional[str] = None
    note: Optional[str] = None
    ownerId: Optional[str] = None
    dueAt: Optional[str] = None


class QuantumOpsGovernanceStatusRequest(BaseModel):
    accountId: Optional[str] = None
    status: str
    resolutionNotes: Optional[str] = None
    disposition: Optional[str] = None


class QuantumOpsGovernanceEvidenceRequest(BaseModel):
    accountId: Optional[str] = None
    title: str
    preview: str
    refId: Optional[str] = None
    kind: Optional[str] = None


class QuantumOpsGovernanceRestrictionReleaseRequest(BaseModel):
    accountId: Optional[str] = None
    releaseReason: str


class QuantumOpsGovernanceRestrictionUpdateRequest(BaseModel):
    accountId: Optional[str] = None
    restrictionType: Optional[str] = None
    restrictionReason: Optional[str] = None
    expiresAt: Optional[str] = None


class QuantumOpsGovernanceCaseRestrictionRequest(BaseModel):
    accountId: Optional[str] = None
    restrictionType: str
    restrictionReason: Optional[str] = None
    expiresAt: Optional[str] = None


class QuantumOpsGovernanceApplyRestrictionRequest(BaseModel):
    accountId: Optional[str] = None
    restrictionType: str
    summary: str
    description: Optional[str] = None
    severity: Optional[str] = None
    expiresAt: Optional[str] = None
    restrictionReason: Optional[str] = None
    supportIssueIds: Optional[List[str]] = None


class QuantumOpsGovernanceRestrictionConfig(BaseModel):
    enabled: bool = False
    restrictionType: Optional[str] = None
    expiresAt: Optional[str] = None
    restrictionReason: Optional[str] = None


class QuantumOpsGovernanceCreateCaseRequest(BaseModel):
    accountId: Optional[str] = None
    caseType: str
    targetType: str
    targetId: Optional[str] = None
    dueAt: Optional[str] = None
    severity: Optional[str] = None
    summary: str
    description: Optional[str] = None
    policyLabels: Optional[List[str]] = None
    supportIssueIds: Optional[List[str]] = None
    applyRestriction: Optional[QuantumOpsGovernanceRestrictionConfig] = None


class QuantumOpsGovernanceBulkActionRequest(BaseModel):
    caseIds: List[str]
    action: str
    ownerId: Optional[str] = None
    ownerAssignments: Optional[Dict[str, str]] = None
    dueAt: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None
    resolutionNotes: Optional[str] = None
    disposition: Optional[str] = None
    policyLabels: Optional[List[str]] = None
    restrictionType: Optional[str] = None
    restrictionReason: Optional[str] = None
    expiresAt: Optional[str] = None


class QuantumOpsGovernanceCapacityOverrideRequest(BaseModel):
    capacityUnitsPerDay: Optional[float] = None
    criticalCaseLimit: Optional[int] = None
    activeRestrictionLimit: Optional[int] = None
    slaHours: Optional[int] = None
    roleMultiplier: Optional[float] = None
    enabled: Optional[bool] = None
    clearOverride: bool = False
    note: Optional[str] = None


class QuantumStudioNodeCreateRequest(BaseModel):
    title: str
    type: str
    x: int
    y: int
    description: str = ""
    parentId: Optional[str] = None


class QuantumStudioNodeUpdateRequest(BaseModel):
    title: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    description: Optional[str] = None


class QuantumStudioPreviewRequest(BaseModel):
    pass


class QuantumStudioEngineRequest(BaseModel):
    engine: str


class QuantumStudioWorldRulesRequest(BaseModel):
    ruleIds: List[str]


QUANTUM_TIER_MAP = {
    "play_pass": "observer",
    "creator_pass": "intervener",
    "studio_pass": "savior",
    "observer": "observer",
    "intervener": "intervener",
    "savior": "savior",
}

QUANTUM_PLAN_CATALOG = {
    "play_pass": {
        "plan_id": "plan_observer",
        "frontend_tier": "observer",
        "name": "Observer",
    },
    "creator_pass": {
        "plan_id": "plan_intervener",
        "frontend_tier": "intervener",
        "name": "Intervener",
    },
    "studio_pass": {
        "plan_id": "plan_savior",
        "frontend_tier": "savior",
        "name": "Savior",
    },
}

QUANTUM_PLAN_ALIAS_TO_TIER = {
    "observer": "play_pass",
    "plan_observer": "play_pass",
    "play_pass": "play_pass",
    "intervener": "creator_pass",
    "plan_intervener": "creator_pass",
    "creator_pass": "creator_pass",
    "savior": "studio_pass",
    "plan_savior": "studio_pass",
    "studio_pass": "studio_pass",
}

QUANTUM_STORY_SHARE_TTL_DAYS = 7

QUANTUM_INK_PACKAGES: List[Dict[str, Any]] = [
    {"id": "ink_500", "amount": 500, "bonus": 0, "price": 0.99, "isRecommended": False},
    {"id": "ink_2500", "amount": 2500, "bonus": 100, "price": 4.99, "isRecommended": False},
    {"id": "ink_5000", "amount": 5000, "bonus": 500, "price": 9.99, "isRecommended": True},
    {"id": "ink_12000", "amount": 12000, "bonus": 2000, "price": 19.99, "isRecommended": False},
    {"id": "ink_30000", "amount": 30000, "bonus": 7500, "price": 49.99, "isRecommended": False},
    {"id": "ink_80000", "amount": 80000, "bonus": 25000, "price": 99.99, "isRecommended": False},
]

QUANTUM_STUDIO_ENGINES = ["balanced", "effect", "speed", "cost"]
QUANTUM_LIBRARY_FILTERS = {"recent", "favorites", "following", "completed"}
QUANTUM_SHOWCASE_SORTS = {"hot", "new", "ongoing"}
QUANTUM_STORY_BRANCH_TYPES = ["rational", "emotional", "adventurous", "fateful"]
QUANTUM_STORY_DEVIATION_INCREMENTS = [5, 15, 25, 35]


def _is_public_catalog_visible(metadata: Dict[str, Any]) -> bool:
    if str(metadata.get("catalog_role") or "").strip() == "template":
        return False
    if metadata.get("public_catalog_visible") is False:
        return False
    return True


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _success(*, data: Any, message: str = "success", code: int = 200) -> Dict[str, Any]:
    return {
        "code": code,
        "data": data,
        "message": message,
        "timestamp": _timestamp(),
    }


def _error(*, status_code: int, message: str, code: Optional[int] = None, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code or status_code,
            "data": data,
            "message": message,
            "timestamp": _timestamp(),
        },
    )


def _request_token(request: Request) -> Optional[str]:
    return request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )

def _maybe_identity(request: Request) -> Optional[Dict[str, Any]]:
    raw_token = _request_token(request)
    if not raw_token:
        return None
    try:
        return request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError):
        return None


def _resolve_login_actor_id(request: Request, identifier: str) -> str:
    return request.app.state.auth_service.resolve_actor_id_from_identifier(identifier)


def _ensure_registration_available(request: Request, *, username: str, email: str) -> None:
    try:
        request.app.state.repository.get_auth_identity(username)
    except KeyError:
        pass
    else:
        raise ValueError("username_already_registered")
    existing = request.app.state.repository.get_auth_identity_by_account_id(email, default=None)
    if existing is not None:
        raise ValueError("email_already_registered")


def _frontend_membership_tier(tier_id: Optional[str]) -> str:
    normalized = str(tier_id or "").strip()
    if not normalized:
        return "free"
    return QUANTUM_TIER_MAP.get(normalized, "free")


def _quantum_checkout_error(exc: Exception) -> JSONResponse:
    reason = str(exc) or "compat_checkout_failed"
    status_code = 400
    if reason in {"checkout_restricted", "email_verification_required_for_billing"}:
        status_code = 403
    elif reason in {"stripe_not_configured", "stripe_sdk_missing"}:
        status_code = 503
    return _error(status_code=status_code, message=reason)


def _quantum_identity_account_id(identity: Dict[str, Any]) -> str:
    return str(identity.get("account_id") or identity.get("actor_id") or "").strip()


def _quantum_identity_actor_id(identity: Dict[str, Any]) -> str:
    return str(identity.get("actor_id") or "").strip()


def _require_identity(request: Request) -> Dict[str, Any]:
    identity = _maybe_identity(request)
    if identity is None:
        raise PermissionError("auth_required")
    return identity


def _require_quantum_ops_actor(request: Request) -> Dict[str, Any]:
    raw_token = _request_token(request)
    if not raw_token:
        raise PermissionError("auth_required")
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise PermissionError(str(exc) or "auth_token_invalid") from exc
    try:
        request.app.state.ops_permission_policy.authorize_read(
            actor_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
        )
    except PermissionError as exc:
        raise ValueError(str(exc) or "ops_actor_forbidden") from exc
    return identity


def _quantum_ops_world_strip(request: Request, *, world_ids: List[str], limit: int = 3) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for world_id in world_ids:
        normalized = str(world_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            items.append(request.app.state.review_service.world_status(normalized))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


def _quantum_ops_reviewer_workspace_payload(
    request: Request,
    *,
    selected_review_item_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    review_hub = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"limit": limit, "source": "deferred"},
        "summary": {},
        "triage": {},
        "items": [],
    }
    selected_id = str(selected_review_item_id or "").strip()
    selected_review_item = None
    if selected_id:
        try:
            selected_review_item = request.app.state.ops_review_hub_service.review_item_detail_cached(selected_id).get("review_item")
        except KeyError:
            selected_review_item = None
    return {
        "reviewHub": review_hub,
        "reviewQueue": [],
        "selectedReviewItemId": selected_id or None,
        "selectedReviewItem": selected_review_item,
        "selectedReviewWork": None,
        "supportedMutations": {
            "assign": True,
            "statuses": ["triaged", "in_review"],
            "decisions": ["approve", "needs_changes", "block", "resolve", "dismiss"],
        },
        "selectedReviewItemAllowedActions": list((selected_review_item or {}).get("allowed_actions") or []),
        "worldStrip": [],
    }


def _quantum_ops_runtime_workspace_payload(
    request: Request,
    *,
    account_id: Optional[str],
    world_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    runtime_incident_snapshot = request.app.state.observability_service.runtime_incident_snapshot(
        account_id=account_id,
        limit=limit,
    )
    runtime_receipts = request.app.state.observability_service.list_runtime_receipts(
        account_id=account_id,
        limit=limit,
    )
    provider_routing = request.app.state.provider_routing_service.policy_summary()
    provider_rollout = request.app.state.provider_rollout_service.summary(
        candidate_backend_present=request.app.state.candidate_backend is not None,
        renderer_backend_present=request.app.state.renderer_backend is not None,
    )
    provider_runtime_metrics = request.app.state.observability_service.provider_runtime_metrics(
        account_id=account_id,
        limit=max(limit, 24),
    )
    story_bootstrap_world_summary = request.app.state.observability_service.story_bootstrap_world_summary(limit=12)
    selected_world_id = str(world_id or "").strip() or str((story_bootstrap_world_summary.get("worlds") or [{}])[0].get("worldId") or "").strip()
    story_bootstrap_world_detail = None
    if selected_world_id:
        try:
            story_bootstrap_world_detail = request.app.state.observability_service.story_bootstrap_world_detail(
                selected_world_id,
                limit=12,
            )
        except KeyError:
            story_bootstrap_world_detail = None
    return {
        "accountId": account_id,
        "worldId": selected_world_id or None,
        "runtimeIncidentSnapshot": runtime_incident_snapshot,
        "runtimeReceipts": runtime_receipts,
        "providerRouting": provider_routing,
        "providerRollout": provider_rollout,
        "providerRuntimeMetrics": provider_runtime_metrics,
        "storyBootstrapWorldSummary": story_bootstrap_world_summary.get("worlds") or [],
        "storyBootstrapWorldDetail": story_bootstrap_world_detail,
    }


def _quantum_ops_account_workspace_payload(
    request: Request,
    *,
    account_id: str,
    limit: int,
) -> Dict[str, Any]:
    billing = request.app.state.billing_service
    subscriptions = billing.monetization.list_subscriptions(account_id=account_id)
    subscription = next((item for item in subscriptions if item.get("status") in {"trialing", "active", "past_due"}), None) or (subscriptions[0] if subscriptions else None)
    subscription_payload = billing._subscription_snapshot(subscription) if subscription else None
    wallets = billing._wallets_for_account(account_id)
    entitlement_count = len([item for item in wallets.values() if item])
    subscription_audit = {
        "account_id": account_id,
        "config_version": "entitlement_matrix_v1",
        "audit_summary": {
            "entitlement_count": entitlement_count,
            "subscription_count": len(subscriptions),
            "source": "ops_account_workspace_light",
        },
    }
    account_detail = {
        "account_id": account_id,
        "subscription": subscription_payload,
        "wallets": wallets,
    }
    account_workspace = {
        "workspace_summary": {
            "health_status": "operational" if subscription_payload else "needs_attention",
            "recommended_path": "account_light_workspace",
            "source": "light",
        },
        "operator_timeline": [],
        "action_pack": [],
        "linked_context": {},
    }
    governance_snapshot = {
        "account_id": account_id,
        "governance_cases": [],
        "restriction_summary": {"active_restriction_count": 0},
        "support_summary": {},
    }
    available_mutations = [
        {
            "actionId": "grant_subscription",
            "label": "Grant Subscription",
            "handler": "grant_subscription",
            "reason": "manual ops grant",
            "prefill": {"tier_id": str((subscription_payload or {}).get("tier_id") or "play_pass")},
        },
        {
            "actionId": "grant_wallet",
            "label": "Grant Wallet",
            "handler": "grant_wallet",
            "reason": "manual wallet top-up",
            "prefill": {"wallet_type": "story_credits", "amount": 10},
        },
    ]
    subscription_id = _quantum_ops_primary_subscription_id(account_detail)
    if subscription_id:
        available_mutations.append(
            {
                "actionId": "retry_subscription_payment",
                "label": "Retry Subscription Payment",
                "handler": "retry_subscription_payment",
                "reason": "retry current subscription payment",
                "prefill": {"subscription_id": subscription_id},
            }
        )
        available_mutations.append(
            {
                "actionId": "reconcile_subscription",
                "label": "Reconcile Subscription",
                "handler": "reconcile_subscription",
                "reason": "refresh current subscription lifecycle snapshot",
                "prefill": {"subscription_id": subscription_id},
            }
        )
    return {
        "accountId": account_id,
        "subscriptionAudit": subscription_audit,
        "accountDetail": account_detail,
        "accountWorkspace": account_workspace,
        "governanceSnapshot": governance_snapshot,
        "availableMutations": available_mutations,
    }


def _quantum_ops_release_workspace_payload(
    request: Request,
    *,
    world_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    summary = request.app.state.observability_service.story_bootstrap_world_summary(limit=12)
    selected_world_id = str(world_id or "").strip() or str((summary.get("worlds") or [{}])[0].get("worldId") or "").strip()
    workspace = None
    if selected_world_id:
        try:
            workspace = request.app.state.ops_release_workspace_service.world_release_workspace(world_id=selected_world_id, limit=max(limit, 12))
        except KeyError:
            workspace = None
    return {
        "worldId": selected_world_id or None,
        "releaseWorkspace": workspace,
        "worldSummary": summary.get("worlds") or [],
    }


def _quantum_ops_alerts_workspace_payload(
    request: Request,
    *,
    account_id: Optional[str],
    alert_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    resolved_account_id = str(account_id or "").strip() or "ops_remote_acceptance"
    light_alert_id = f"quantum_ops_light::{resolved_account_id}"
    selected_alert_id = str(alert_id or "").strip() or light_alert_id
    audit_trail = request.app.state.repository.list_audit_logs(
        object_type="ops_alert",
        object_id=selected_alert_id,
        limit=20,
    )
    action_types = [str(item.get("action_type") or "") for item in audit_trail]
    if "ops_alert_resolved" in action_types:
        selected_alert_status = "resolved"
    elif "ops_alert_acknowledged" in action_types:
        selected_alert_status = "acknowledged"
    else:
        selected_alert_status = "open"
    selected_alert = {
        "alert_id": selected_alert_id,
        "account_id": resolved_account_id,
        "category": "runtime",
        "severity": "medium",
        "status": selected_alert_status,
        "source_type": "remote_acceptance",
        "summary": "Remote Ops lightweight alert",
        "title": "Remote Ops lightweight alert",
        "recommended_actions": ["acknowledge_alert", "resolve_alert"],
    }
    selected_alert_detail = {
        "alert": selected_alert,
        "runbook": {},
        "standard_response_bundle": {},
        "investigation_bundle": None,
        "operator_audit_trail": audit_trail,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    visible_alerts = [selected_alert] if selected_alert_status != "resolved" else []
    selected_alert = dict((selected_alert_detail or {}).get("alert") or {})
    selected_alert_allowed_actions: List[str] = []
    if selected_alert_status == "open":
        selected_alert_allowed_actions = ["acknowledge", "resolve"]
    elif selected_alert_status == "acknowledged":
        selected_alert_allowed_actions = ["resolve"]
    return {
        "accountId": resolved_account_id,
        "alertsSummary": {
            "alert_count": len(visible_alerts),
            "actionable_alert_count": len(visible_alerts),
            "source": "light",
        },
        "alerts": visible_alerts,
        "selectedAlertId": selected_alert_id or None,
        "selectedAlertDetail": selected_alert_detail,
        "selectedAlertAllowedActions": selected_alert_allowed_actions,
        "selectedAlertOperatorAudit": list((selected_alert_detail or {}).get("operator_audit_trail") or []),
    }


def _quantum_ops_governance_workspace_payload(
    request: Request,
    *,
    account_id: Optional[str],
    case_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    account_snapshot = (
        request.app.state.governance_service.account_snapshot(account_id=account_id, limit=max(limit, 20))
        if account_id
        else {"recommended_case_prefills": []}
    )
    cases_payload = request.app.state.governance_service.list_cases(account_id=account_id, limit=max(limit, 20))
    restrictions_payload = request.app.state.governance_service.list_restrictions(account_id=account_id, limit=max(limit, 20))
    selected_case_id = str(case_id or "").strip() or str((cases_payload.get("cases") or [{}])[0].get("case_id") or "").strip()
    selected_case_detail = None
    viewer_identity = _maybe_identity(request) or {}
    if selected_case_id:
        try:
            selected_case_detail = request.app.state.governance_service.case_detail(
                selected_case_id,
                actor_id=str(viewer_identity.get("actor_id") or "").strip() or None,
                actor_role=str(viewer_identity.get("actor_role") or "").strip() or None,
            )
        except KeyError:
            selected_case_detail = None
    permission_summary = dict((selected_case_detail or {}).get("permission_summary") or {})
    workflow_summary = dict((selected_case_detail or {}).get("workflow_summary") or {})
    restriction = dict((selected_case_detail or {}).get("restriction") or {}) or None
    owner_roster = request.app.state.governance_service.owner_roster(limit=25)
    return {
        "accountId": account_id,
        "governanceSummary": cases_payload.get("governance_summary") or {},
        "governanceCases": cases_payload.get("cases") or [],
        "restrictions": restrictions_payload.get("restrictions") or [],
        "restrictionSummary": restrictions_payload.get("restriction_summary") or {},
        "recommendedCasePrefills": list(account_snapshot.get("recommended_case_prefills") or []),
        "supportSummary": dict(account_snapshot.get("support_summary") or {}),
        "supportIssueRefs": list(account_snapshot.get("support_issue_refs") or []),
        "caseTypeCatalog": _quantum_governance_case_type_catalog(),
        "targetTypeCatalog": _quantum_governance_target_type_catalog(),
        "policyLabelSuggestions": _quantum_governance_policy_label_suggestions(),
        "targetResolver": _quantum_governance_target_resolver(request, account_id=account_id, limit=10),
        "targetResolverMeta": _quantum_governance_target_resolver_meta(request, account_id=account_id),
        "restrictionCatalog": _quantum_governance_restriction_catalog(),
        "ownerRoster": [
            {
                "actorId": str(item.get("actor_id") or ""),
                "displayName": str(item.get("display_name") or item.get("actor_id") or ""),
                "actorRole": str(item.get("actor_role") or ""),
                "accountId": str(item.get("account_id") or "") or None,
                "status": str(item.get("status") or ""),
            }
            for item in owner_roster
        ],
        "selectedCaseId": selected_case_id or None,
        "selectedCaseDetail": selected_case_detail,
        "selectedCaseAllowedActions": {
            "assignToMe": bool(permission_summary.get("can_assign")),
            "assignAnyOwner": bool(permission_summary.get("can_assign")),
            "statusTransitions": list(workflow_summary.get("transition_options") or []),
            "canAddEvidence": bool(permission_summary.get("can_add_evidence")),
            "canReleaseRestriction": bool(permission_summary.get("can_release_restriction")),
            "canEditRestriction": bool(permission_summary.get("can_edit_restriction")),
        },
        "selectedCaseRestriction": restriction,
        "selectedCaseTargetValidation": dict((selected_case_detail or {}).get("target_validation") or {}) or None,
        "selectedCaseOperatorAudit": list((selected_case_detail or {}).get("operator_audit_trail") or []),
        "restrictionHistory": list((selected_case_detail or {}).get("restriction_history") or []),
    }


def _quantum_ops_governance_queue_workspace_payload(
    request: Request,
    *,
    status: Optional[str],
    owner_id: Optional[str],
    case_type: Optional[str],
    severity: Optional[str],
    target_type: Optional[str],
    has_active_restriction: Optional[bool],
    overdue_only: bool,
    unassigned_only: bool,
    search: Optional[str],
    selected_case_ids: Optional[List[str]],
    limit: int,
    bulk_preview_result: Optional[Dict[str, Any]] = None,
    bulk_execution_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    viewer_identity = _maybe_identity(request) or {}
    payload = request.app.state.governance_service.owner_workload(
        status=status,
        owner_id=owner_id,
        case_type=case_type,
        severity=severity,
        target_type=target_type,
        has_active_restriction=has_active_restriction,
        overdue_only=overdue_only,
        unassigned_only=unassigned_only,
        search=search,
        selected_case_ids=selected_case_ids,
        limit=limit,
    )
    return {
        **payload,
        "capacityAdminSurface": {
            **dict(payload.get("capacityAdminSurface") or {}),
            "canEdit": str(viewer_identity.get("actor_role") or "").strip() == "admin",
        },
        "bulkPreviewResult": bulk_preview_result,
        "bulkExecutionResult": bulk_execution_result,
    }


def _quantum_ops_learned_workspace_payload(
    request: Request,
    *,
    world_id: Optional[str],
    issue_code: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    selected_world_id = str(world_id or "").strip() or "jade_court_exam"
    selected_issue_code = str(issue_code or "").strip() or "Q03"
    world_detail = {
        "world_id": selected_world_id,
        "status": "deferred",
        "surface": "quantum_ops_light",
    }
    issue_detail = {
        "issue_code": selected_issue_code,
        "status": "deferred",
        "surface": "quantum_ops_light",
    }
    dashboard = {
        "schema_version": "quantum_ops_learned_workspace_light/v1",
        "mode": "deferred",
        "world_details": [world_detail],
        "issue_details": [issue_detail],
        "artifact_status": {
            "evaluator": {"status": "deferred"},
            "reranker": {"status": "deferred"},
        },
        "recommended_next_focus": selected_issue_code,
    }
    compare = {
        "schema_version": "quantum_ops_learned_compare_light/v1",
        "mode": "deferred",
        "preferred_shadow_candidate": "deferred",
        "recommended_next_action": "open_dedicated_learned_ops",
        "disagreement_worlds": [],
        "disagreement_issue_codes": [selected_issue_code],
    }
    rollout = {
        "schema_version": "quantum_ops_learned_rollout_light/v1",
        "mode": "deferred",
        "world_id": selected_world_id,
        "limit": max(1, min(100, int(limit or 20))),
        "active_rollouts": [],
        "candidate_count": 0,
    }
    return {
        "worldId": selected_world_id or None,
        "issueCode": selected_issue_code or None,
        "dashboard": dashboard,
        "compare": compare,
        "rollout": rollout,
        "selectedWorldDetail": world_detail,
        "selectedIssueDetail": issue_detail,
    }


def _quantum_governance_restriction_catalog() -> List[Dict[str, Any]]:
    labels = {
        "reader_access_block": "Reader Access Block",
        "author_access_block": "Author Access Block",
        "checkout_block": "Checkout Block",
        "account_hold": "Account Hold",
    }
    scopes = {
        "reader_access_block": "reader",
        "author_access_block": "author",
        "checkout_block": "checkout",
        "account_hold": "account",
    }
    return [
        {"id": item, "label": labels[item], "scope": scopes[item]}
        for item in sorted(["reader_access_block", "author_access_block", "checkout_block", "account_hold"])
    ]


def _quantum_governance_case_type_catalog() -> List[Dict[str, Any]]:
    labels = {
        "rights": "Rights",
        "moderation": "Moderation",
        "abuse": "Abuse",
    }
    return [{"id": item, "label": labels[item]} for item in ["rights", "moderation", "abuse"]]


def _quantum_governance_target_type_catalog() -> List[Dict[str, Any]]:
    labels = {
        "account": "Account",
        "world_version": "World Version",
        "session": "Session",
        "entitlement": "Entitlement",
    }
    return [{"id": item, "label": labels[item]} for item in ["account", "world_version", "session", "entitlement"]]


def _quantum_governance_policy_label_suggestions() -> Dict[str, List[str]]:
    return {
        "rights": ["billing_rights", "entitlement_review", "customer_remedy", "account_scope_review"],
        "moderation": ["content_policy", "publication_review", "world_version_moderation", "appeal_review"],
        "abuse": ["abuse_signal", "restriction_review", "account_integrity", "enforcement_followup"],
    }


def _quantum_governance_target_resolver(request: Request, *, account_id: Optional[str], limit: int = 10) -> Dict[str, Any]:
    resolver = request.app.state.governance_service.target_resolver(account_id=account_id, limit=limit)

    def _map_item(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "label": str(item.get("label") or item.get("id") or ""),
            "status": str(item.get("status") or ""),
            "accountId": str(item.get("account_id") or "") or None,
            "targetType": str(item.get("target_type") or ""),
            "worldId": str(item.get("world_id") or "") or None,
            "worldVersionId": str(item.get("world_version_id") or "") or None,
            "sessionId": str(item.get("session_id") or "") or None,
            "entitlementId": str(item.get("entitlement_id") or "") or None,
            "entitlementType": str(item.get("entitlement_type") or "") or None,
            "walletType": str(item.get("wallet_type") or "") or None,
            "tierId": str(item.get("tier_id") or "") or None,
            "riskRating": str(item.get("risk_rating") or "") or None,
            "expiresAt": str(item.get("expires_at") or "") or None,
            "validationWarnings": [str(value) for value in list(item.get("validation_warnings") or [])],
        }

    return {
        "accounts": [_map_item(item) for item in list(resolver.get("accounts") or [])],
        "worldVersions": [_map_item(item) for item in list(resolver.get("world_versions") or [])],
        "sessions": [_map_item(item) for item in list(resolver.get("sessions") or [])],
        "entitlements": [_map_item(item) for item in list(resolver.get("entitlements") or [])],
    }


def _quantum_governance_target_resolver_meta(request: Request, *, account_id: Optional[str]) -> Dict[str, Any]:
    meta = request.app.state.governance_service.target_resolver_meta(account_id=account_id)
    return {
        "scopeAccountId": str(meta.get("scope_account_id") or "") or None,
        "strictScopeEnabled": bool(meta.get("strict_scope_enabled")),
        "validationMode": str(meta.get("validation_mode") or ""),
        "supportedTargetTypes": [str(item) for item in list(meta.get("supported_target_types") or [])],
    }


def _quantum_ops_primary_subscription_id(account_detail: Dict[str, Any]) -> Optional[str]:
    subscription = dict(account_detail.get("subscription") or {})
    subscription_id = str(subscription.get("subscription_id") or "").strip()
    return subscription_id or None


def _quantum_ops_bootstrap_payload(request: Request, *, identity: Dict[str, Any]) -> Dict[str, Any]:
    # Bootstrap is fetched on every Ops shell boot. Keep it to defaults and
    # identity only; full reviewer queues/details and release defaults are
    # loaded by dedicated workspace endpoints after the shell is mounted.
    default_account_id = _quantum_identity_account_id(identity) or None
    default_world_id = "jade_court_exam"
    return {
        "availableTabs": [
            {"id": "reviewer", "label": "审阅台"},
            {"id": "runtime", "label": "运行观测"},
            {"id": "account", "label": "账户工作区"},
            {"id": "release", "label": "发布工作台"},
            {"id": "alerts", "label": "告警中心"},
            {"id": "learned", "label": "学习层"},
            {"id": "governance", "label": "治理工作台"},
        ],
        "defaultTab": "reviewer",
        "defaultAccountId": default_account_id,
        "defaultWorldId": default_world_id,
        "defaultReviewItemId": None,
        "reviewer": {
            "actorId": str(identity.get("actor_id") or "").strip(),
            "actorRole": str(identity.get("actor_role") or "").strip(),
            "displayName": str(identity.get("display_name") or identity.get("actor_id") or "").strip(),
            "accountId": _quantum_identity_account_id(identity) or None,
        },
        "reviewHubSummary": {},
    }


def _resolve_plan_tier_id(raw_plan_id: str) -> str:
    normalized = str(raw_plan_id or "").strip()
    resolved = QUANTUM_PLAN_ALIAS_TO_TIER.get(normalized)
    if not resolved:
        raise ValueError("unknown_membership_plan")
    return resolved


def _plan_features_for_tier(request: Request, tier_id: str) -> List[str]:
    tier = request.app.state.billing_service.monetization.get_tier(tier_id)
    features = [
        f"${float(tier.get('price_usd_monthly') or 0):.0f} / month",
        f"{int(float(tier.get('monthly_story_credits') or 0))} story credits / month",
    ]
    studio_credits = int(float(tier.get("monthly_studio_credits") or 0))
    if studio_credits > 0:
        features.append(f"{studio_credits} studio credits / month")
    author_access = str(tier.get("author_access") or "none")
    if author_access != "none":
        features.append(f"Author access: {author_access}")
    description = str(tier.get("description") or "").strip()
    if description:
        features.append(description)
    return features


def _membership_plan_catalog(request: Request) -> List[Dict[str, Any]]:
    identity = _maybe_identity(request)
    current_tier = None
    expires_at = None
    if identity is not None:
        account_id = _quantum_identity_account_id(identity)
        billing_snapshot = request.app.state.billing_service.subscription_status(account_id=account_id)
        subscription = dict(billing_snapshot.get("subscription") or {})
        current_tier = str(
            billing_snapshot.get("effective_tier")
            or subscription.get("tier_id")
            or ""
        ).strip() or None
        expires_at = subscription.get("period_end")
    plans: List[Dict[str, Any]] = []
    for tier_id in ("play_pass", "creator_pass", "studio_pass"):
        catalog_entry = QUANTUM_PLAN_CATALOG[tier_id]
        tier = request.app.state.billing_service.monetization.get_tier(tier_id)
        plans.append(
            {
                "id": catalog_entry["plan_id"],
                "name": catalog_entry["name"],
                "price": float(tier.get("price_usd_monthly") or 0.0),
                "period": "monthly",
                "features": _plan_features_for_tier(request, tier_id),
                "isCurrent": current_tier == tier_id,
                "expiresAt": expires_at if current_tier == tier_id else None,
            }
        )
    return plans


def _resolve_ink_package(request: Request, raw_package_id: str) -> Dict[str, Any]:
    normalized = str(raw_package_id or "").strip()
    try:
        package = request.app.state.billing_service.monetization.get_ink_package(normalized)
    except KeyError as exc:
        raise ValueError("unknown_ink_package") from exc
    return {
        "id": str(package.get("package_id") or normalized),
        "amount": int(float(package.get("amount") or 0.0)),
        "bonus": int(float(package.get("bonus") or 0.0)),
        "price": float(package.get("price_usd") or 0.0),
        "isRecommended": bool(package.get("recommended")),
    }


def _ink_packages_catalog(request: Request) -> List[Dict[str, Any]]:
    packages = []
    for package in request.app.state.billing_service.monetization.ink_packages():
        packages.append(
            {
                "id": str(package.get("package_id") or ""),
                "amount": int(float(package.get("amount") or 0.0)),
                "bonus": int(float(package.get("bonus") or 0.0)),
                "price": float(package.get("price_usd") or 0.0),
                "isRecommended": bool(package.get("recommended")),
            }
        )
    return packages


def _request_frontend_origin(request: Request) -> str:
    origin = str(request.headers.get("origin") or "").strip()
    if origin:
        return origin.rstrip("/")
    referer = str(request.headers.get("referer") or "").strip()
    if referer:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
    return str(request.base_url).rstrip("/")


def _checkout_payload(
    *,
    url: str,
    provider: str,
    checkout_kind: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "url": url,
        "provider": provider,
        "checkoutKind": checkout_kind,
        **dict(extra or {}),
    }


def _start_membership_checkout(
    request: Request,
    *,
    identity: Dict[str, Any],
    raw_plan_id: str,
) -> Dict[str, Any]:
    account_id = _quantum_identity_account_id(identity)
    tier_id = _resolve_plan_tier_id(raw_plan_id)
    checkout = request.app.state.billing_service.start_checkout(
        account_id=account_id,
        tier_id=tier_id,
        customer_email=(account_id if "@" in account_id else None),
        metadata={
            "compat_surface": "quantum_settings_membership",
            "quantum_plan_id": raw_plan_id,
            "quantum_frontend_tier": QUANTUM_TIER_MAP.get(tier_id),
        },
    )
    return _checkout_payload(
        url=str(checkout.get("checkout_url") or ""),
        provider=str(checkout.get("provider") or "web_stub"),
        checkout_kind="subscription",
        extra={
            "checkoutSessionId": checkout.get("checkout_session_id"),
            "tierId": tier_id,
            "planId": raw_plan_id,
        },
    )


def _start_ink_checkout(
    request: Request,
    *,
    identity: Dict[str, Any],
    raw_package_id: str,
) -> Dict[str, Any]:
    account_id = _quantum_identity_account_id(identity)
    package = _resolve_ink_package(request, raw_package_id)
    frontend_origin = _request_frontend_origin(request)
    success_url = (
        f"{frontend_origin}/settings"
        f"?tab=matter&checkout=success&checkout_kind=ink&checkout_session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = f"{frontend_origin}/settings?tab=matter&checkout=cancel&checkout_kind=ink"
    checkout = request.app.state.billing_service.start_ink_checkout(
        account_id=account_id,
        package_id=package["id"],
        customer_email=(account_id if "@" in account_id else None),
        metadata={
            "compat_surface": "quantum_settings_ink",
            "package_id": package["id"],
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    request.app.state.analytics_service.track(
        "checkout_started",
        reader_id=account_id,
        account_id=account_id,
        access_tier="story_credits",
        payload_json={
            "provider": checkout.get("provider"),
            "package_id": package["id"],
            "amount": package["amount"],
            "bonus": package["bonus"],
            "price": package["price"],
            "checkout_url": checkout.get("checkout_url"),
            "checkout_session_id": checkout.get("checkout_session_id"),
        },
    )
    return _checkout_payload(
        url=str(checkout.get("checkout_url") or ""),
        provider=str(checkout.get("provider") or "web_stub"),
        checkout_kind="ink",
        extra={
            "checkoutSessionId": checkout.get("checkout_session_id"),
            "packageId": package["id"],
            "amount": package["amount"],
            "bonus": package["bonus"],
            "price": package["price"],
        },
    )


def _studio_title(worldpack: Dict[str, Any], project_id: str) -> str:
    return str(worldpack.get("title") or project_id)


def _studio_engine(worldpack: Dict[str, Any]) -> str:
    quantum_frontend = _studio_quantum_frontend_metadata(worldpack)
    engine = str(quantum_frontend.get("engine") or "").strip()
    return engine if engine in QUANTUM_STUDIO_ENGINES else "balanced"


def _studio_quantum_frontend_metadata(worldpack: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(worldpack.get("metadata") or {})
    return dict(metadata.get("quantum_frontend") or {})


def _studio_world_rule_specs(worldpack: Dict[str, Any]) -> List[Dict[str, Any]]:
    world_bible = dict(worldpack.get("world_bible") or {})
    characters = list(worldpack.get("characters") or [])
    arc_plans = list(worldpack.get("arc_plans") or [])
    locations = list(world_bible.get("locations") or [])
    return [
        {"id": "rule_premise", "name": "核心设定", "default_enabled": bool(str(world_bible.get("premise") or "").strip())},
        {"id": "rule_characters", "name": "角色阵列", "default_enabled": bool(characters)},
        {"id": "rule_arc_plan", "name": "章节弧线", "default_enabled": bool(arc_plans)},
        {"id": "rule_locations", "name": "地点锚定", "default_enabled": bool(locations)},
    ]


def _studio_characters(worldpack: Dict[str, Any]) -> List[Dict[str, Any]]:
    characters = []
    for index, item in enumerate(list(worldpack.get("characters") or []), start=1):
        payload = dict(item or {})
        character_id = str(
            payload.get("character_id")
            or payload.get("id")
            or payload.get("display_name")
            or payload.get("name")
            or f"character_{index}"
        ).strip()
        display_name = str(
            payload.get("display_name")
            or payload.get("name")
            or payload.get("character_id")
            or f"角色 {index}"
        ).strip()
        characters.append({"id": character_id, "name": display_name, "avatar": ""})
    return characters


def _studio_world_rules(worldpack: Dict[str, Any]) -> List[Dict[str, Any]]:
    quantum_frontend = _studio_quantum_frontend_metadata(worldpack)
    enabled_rule_ids = quantum_frontend.get("enabled_rule_ids")
    if isinstance(enabled_rule_ids, list):
        enabled_set = {str(item).strip() for item in enabled_rule_ids if str(item).strip()}
        return [
            {"id": item["id"], "name": item["name"], "enabled": item["id"] in enabled_set}
            for item in _studio_world_rule_specs(worldpack)
        ]
    return [
        {"id": item["id"], "name": item["name"], "enabled": bool(item["default_enabled"])}
        for item in _studio_world_rule_specs(worldpack)
    ]


def _studio_arc_nodes(worldpack: Dict[str, Any], *, project_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    world_bible = dict(worldpack.get("world_bible") or {})
    volume_order_map = {
        str(item.get("volume_id") or ""): int(item.get("order") or 0)
        for item in list(worldpack.get("volume_plans") or [])
        if str(item.get("volume_id") or "").strip()
    }
    arc_plans = sorted(
        [dict(item or {}) for item in list(worldpack.get("arc_plans") or [])],
        key=lambda item: (
            volume_order_map.get(str(item.get("volume_id") or ""), 10_000),
            int(item.get("order") or 0),
            str(item.get("arc_id") or ""),
        ),
    )[:12]

    nodes: List[Dict[str, Any]] = [
        {
            "id": project_id,
            "title": _studio_title(worldpack, project_id),
            "type": "root",
            "x": 380,
            "y": 72,
            "description": str(world_bible.get("premise") or ""),
            "status": "active",
        }
    ]
    connections: List[Dict[str, Any]] = []

    for index, arc in enumerate(arc_plans):
        arc_id = str(arc.get("arc_id") or f"arc_{index + 1}").strip()
        first_task = dict((list(arc.get("chapter_tasks") or [{}]) or [{}])[0] or {})
        description = str(
            first_task.get("objective")
            or first_task.get("notes")
            or arc.get("title")
            or arc.get("completion_conditions")
            or ""
        ).strip()
        nodes.append(
            {
                "id": arc_id,
                "title": str(arc.get("title") or f"章节弧线 {index + 1}").strip(),
                "type": "branch",
                "x": 120 + (index % 3) * 260,
                "y": 260 + (index // 3) * 210,
                "description": description,
                "status": "active",
            }
        )
        connections.append(
            {
                "from": project_id,
                "to": arc_id,
                "label": str(arc.get("volume_id") or ""),
            }
        )
    return nodes, connections


def _studio_project_graph(worldpack: Dict[str, Any], *, project_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    quantum_frontend = _studio_quantum_frontend_metadata(worldpack)
    stored_nodes = list(quantum_frontend.get("nodes") or [])
    stored_connections = list(quantum_frontend.get("connections") or [])
    if stored_nodes:
        nodes: List[Dict[str, Any]] = []
        for index, item in enumerate(stored_nodes):
            payload = dict(item or {})
            node_id = str(payload.get("id") or f"node_{index + 1}").strip()
            if not node_id:
                continue
            nodes.append(
                {
                    "id": node_id,
                    "title": str(payload.get("title") or node_id),
                    "type": str(payload.get("type") or "branch"),
                    "x": int(payload.get("x") or 0),
                    "y": int(payload.get("y") or 0),
                    "description": str(payload.get("description") or ""),
                    "status": str(payload.get("status") or "active"),
                }
            )
        connections = [
            {
                "from": str(dict(item or {}).get("from") or ""),
                "to": str(dict(item or {}).get("to") or ""),
                "label": str(dict(item or {}).get("label") or ""),
            }
            for item in stored_connections
            if str(dict(item or {}).get("from") or "").strip() and str(dict(item or {}).get("to") or "").strip()
        ]
        if nodes:
            return nodes, connections
    return _studio_arc_nodes(worldpack, project_id=project_id)


def _studio_update_quantum_frontend(
    worldpack: Dict[str, Any],
    *,
    engine: Optional[str] = None,
    enabled_rule_ids: Optional[List[str]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None,
    connections: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    next_worldpack = copy.deepcopy(worldpack)
    metadata = dict(next_worldpack.get("metadata") or {})
    quantum_frontend = dict(metadata.get("quantum_frontend") or {})
    if engine is not None:
        quantum_frontend["engine"] = engine
    if enabled_rule_ids is not None:
        quantum_frontend["enabled_rule_ids"] = list(enabled_rule_ids)
    if nodes is not None:
        quantum_frontend["nodes"] = list(nodes)
    if connections is not None:
        quantum_frontend["connections"] = list(connections)
    metadata["quantum_frontend"] = quantum_frontend
    next_worldpack["metadata"] = metadata
    return next_worldpack


def _studio_preview_payload(project_id: str, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
    chapter_evaluations = list(simulation_report.get("chapter_evaluations") or [])
    issue_counts: Dict[str, int] = {}
    for item in chapter_evaluations:
        for issue in list(item.get("issues") or []):
            code = str(dict(issue or {}).get("issue_code") or "").strip()
            if not code:
                continue
            issue_counts[code] = issue_counts.get(code, 0) + 1
    top_issue_codes = [
        code
        for code, _count in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    summary = (
        f"模拟 {len(chapter_evaluations)} 章"
        + (f" · 主要问题 {', '.join(top_issue_codes)}" if top_issue_codes else " · 当前未发现显著问题")
    )
    return {
        "previewId": f"preview_{project_id}_{uuid4().hex[:8]}",
        "status": "completed",
        "chapterCount": len(chapter_evaluations),
        "issueCodes": top_issue_codes,
        "summary": summary,
    }


def _studio_export_payload(project: Dict[str, Any], *, format_value: str) -> str:
    normalized = str(format_value or "").strip().lower()
    if normalized == "json":
        return json.dumps(project, ensure_ascii=False, indent=2)
    lines = [
        f"# {project['title']}",
        "",
        f"- projectId: {project['id']}",
        f"- engine: {project['engine']}",
        f"- worldRules: {', '.join(item['name'] for item in project.get('worldRules', []) if item.get('enabled')) or '-'}",
        "",
        "## Characters",
        *(f"- {item['name']}" for item in project.get("characters", [])),
        "",
        "## Nodes",
        *(f"- {item['id']}: {item['title']} ({item['type']})" for item in project.get("nodes", [])),
        "",
        "## Connections",
        *(f"- {item['from']} -> {item['to']}" + (f" [{item['label']}]" if item.get("label") else "") for item in project.get("connections", [])),
    ]
    return "\n".join(lines).strip() + "\n"


def _studio_project_payload(project_id: str, draft_detail: Dict[str, Any]) -> Dict[str, Any]:
    worldpack = dict(draft_detail.get("worldpack") or {})
    nodes, connections = _studio_project_graph(worldpack, project_id=project_id)
    return {
        "id": project_id,
        "title": _studio_title(worldpack, project_id),
        "engine": _studio_engine(worldpack),
        "availableEngines": list(QUANTUM_STUDIO_ENGINES),
        "worldRules": _studio_world_rules(worldpack),
        "characters": _studio_characters(worldpack),
        "nodes": nodes,
        "connections": connections,
    }


def _ensure_studio_project_owner(identity: Dict[str, Any], draft_detail: Dict[str, Any]) -> None:
    worldpack = dict(draft_detail.get("worldpack") or {})
    manifest = dict(worldpack.get("manifest") or {})
    author_id = str(manifest.get("author_id") or "").strip()
    allowed_ids = {
        str(identity.get("account_id") or "").strip(),
        str(identity.get("actor_id") or "").strip(),
    }
    allowed_ids.discard("")
    if author_id and author_id not in allowed_ids:
        raise PermissionError("studio_project_forbidden")


def _frontend_user(request: Request, identity: Dict[str, Any]) -> Dict[str, Any]:
    actor_id = str(identity.get("actor_id") or "").strip()
    account_id = str(identity.get("account_id") or actor_id).strip()
    try:
        account_security = request.app.state.repository.get_auth_identity_profile(actor_id, default={})
    except Exception:
        account_security = {}
    billing_snapshot = request.app.state.billing_service.subscription_status(account_id=account_id)
    entitlements = request.app.state.billing_service.list_entitlements_for_account(account_id)
    wallets = dict(entitlements.get("wallets") or {})
    story_wallet = dict(wallets.get("story_credits") or {})
    subscription = dict(billing_snapshot.get("subscription") or {})
    effective_tier = str(billing_snapshot.get("effective_tier") or subscription.get("tier_id") or "").strip()
    created_at = identity.get("created_at")
    if not created_at:
        auth_identity = request.app.state.repository.get_auth_identity(actor_id)
        created_at = auth_identity.get("created_at")
    email_value = (
        account_security.get("email_address")
        or (account_id if "@" in account_id else "")
        or (actor_id if "@" in actor_id else "")
    )
    return {
        "id": account_id or actor_id,
        "username": actor_id,
        "displayName": identity.get("display_name") or actor_id,
        "avatar": str(account_security.get("avatar_url") or ""),
        "email": email_value,
        "actorRole": str(identity.get("actor_role") or "").strip(),
        "inkBalance": float(story_wallet.get("balance") or 0.0),
        "membershipTier": _frontend_membership_tier(effective_tier),
        "membershipExpiresAt": subscription.get("period_end"),
        "createdAt": created_at or "",
    }


def _default_soul_dimensions() -> List[Dict[str, Any]]:
    return [
        {"label": "理性", "value": 0, "max": 100},
        {"label": "情感", "value": 0, "max": 100},
        {"label": "冒险", "value": 0, "max": 100},
        {"label": "命运", "value": 0, "max": 100},
        {"label": "混沌", "value": 0, "max": 100},
    ]


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reader_recent_activity_map(request: Request, *, account_id: str) -> Dict[str, Dict[str, Any]]:
    events = request.app.state.repository.list_analytics_events(
        event_names=["session_created", "continue_story"],
        reader_id=account_id,
        limit=200,
    )
    latest_by_session: Dict[str, Dict[str, Any]] = {}
    for event in events:
        session_id = str(event.get("session_id") or "").strip()
        if not session_id:
            continue
        occurred_at = _parse_iso_timestamp(event.get("occurred_at"))
        current = latest_by_session.get(session_id)
        current_dt = current.get("occurred_at_dt") if current else None
        if current is None or (occurred_at is not None and (current_dt is None or occurred_at > current_dt)):
            latest_by_session[session_id] = {
                "event_name": str(event.get("event_name") or ""),
                "occurred_at": event.get("occurred_at"),
                "occurred_at_dt": occurred_at,
            }
    return latest_by_session


def _soul_recent_reader_sessions(request: Request, *, account_id: str) -> List[Dict[str, Any]]:
    activity_by_session = _reader_recent_activity_map(request, account_id=account_id)
    bookmark_summary_by_session = _story_bookmark_summary_by_session(request, account_id=account_id)
    recent_items: List[Dict[str, Any]] = []
    for session in request.app.state.repository.list_sessions():
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            continue
        try:
            detail = request.app.state.repository.get_session(session_id)
        except KeyError:
            continue
        if str(detail.metadata.get("reader_id") or "").strip() != account_id:
            continue
        try:
            version = request.app.state.repository.get_world_version(str(session.get("world_version_id") or ""))
            world_title = str((version.worldpack_json or {}).get("title") or version.world_id)
        except KeyError:
            world_title = str(session.get("world_id") or session_id)
        activity = activity_by_session.get(session_id, {})
        updated_at = str(activity.get("occurred_at") or session.get("created_at") or "")
        bookmark_summary = dict(bookmark_summary_by_session.get(session_id) or {})
        current_node_id = _story_projected_current_node_id(request, session_id=session_id)
        recent_items.append(
            {
                "id": session_id,
                "title": str(session.get("last_chapter_title") or world_title),
                "coverImage": _session_cover_image(
                    request,
                    session_id=session_id,
                    world_version_id=str(session.get("world_version_id") or ""),
                ),
                "branchName": str(session.get("last_event_title") or "阅读进度"),
                "progress": int(session.get("current_turn_index") or 0),
                "kind": "reader_session",
                "targetHref": f"/story?session={quote(session_id, safe='')}",
                "updatedAt": updated_at,
                "currentNodeId": current_node_id,
                "viewerHasBookmarkedCurrentNode": current_node_id in set(bookmark_summary.get("node_ids") or set()),
                "_updated_at_dt": _parse_iso_timestamp(updated_at),
            }
        )
    recent_items.sort(
        key=lambda item: item.get("_updated_at_dt") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    return recent_items


def _soul_recent_author_drafts(request: Request, *, account_id: str) -> List[Dict[str, Any]]:
    recent_items: List[Dict[str, Any]] = []
    for item in request.app.state.repository.list_world_versions():
        world_version_id = str(item.get("world_version_id") or "").strip()
        if not world_version_id:
            continue
        try:
            version = request.app.state.repository.get_world_version(world_version_id)
        except KeyError:
            continue
        if str(version.author_id or "").strip() != account_id:
            continue
        updated_at = str(item.get("updated_at") or "")
        recent_items.append(
            {
                "id": f"draft:{world_version_id}",
                "title": str((version.worldpack_json or {}).get("title") or version.world_id),
                "coverImage": _world_cover_image(request, world_version_id=world_version_id),
                "branchName": "创作草稿",
                "progress": 0,
                "kind": "author_draft",
                "targetHref": f"/studio/{quote(world_version_id, safe='')}",
                "updatedAt": updated_at,
                "_updated_at_dt": _parse_iso_timestamp(updated_at),
            }
        )
    recent_items.sort(
        key=lambda item: item.get("_updated_at_dt") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    return recent_items


def _soul_recent_activity_feed(request: Request, *, account_id: str) -> List[Dict[str, Any]]:
    merged = _soul_recent_reader_sessions(request, account_id=account_id) + _soul_recent_author_drafts(request, account_id=account_id)
    merged.sort(
        key=lambda item: item.get("_updated_at_dt") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    output = []
    for item in merged[:6]:
        payload = dict(item)
        payload.pop("_updated_at_dt", None)
        output.append(payload)
    return output


def _soul_recent_activity_count(request: Request, *, account_id: str) -> int:
    activity_window_start = datetime.now(timezone.utc).timestamp() - (24 * 60 * 60)
    events = request.app.state.repository.list_analytics_events(
        event_names=[
            "session_created",
            "continue_story",
            "author_draft_created_from_brief",
            "author_draft_saved",
            "author_draft_updated",
            "author_draft_validated",
            "author_draft_simulated",
            "author_draft_submitted",
            "author_longform_workbench_bootstrapped",
        ],
        reader_id=account_id,
        limit=500,
    )
    count = 0
    for event in events:
        occurred_at = _parse_iso_timestamp(event.get("occurred_at"))
        if occurred_at and occurred_at.timestamp() >= activity_window_start:
            count += 1
    return count


def _normalize_library_filter(raw_filter: Any) -> str:
    normalized = str(raw_filter or "").strip()
    return normalized if normalized in QUANTUM_LIBRARY_FILTERS else "recent"


def _normalize_showcase_sort(raw_sort: Any) -> str:
    normalized = str(raw_sort or "").strip()
    return normalized if normalized in QUANTUM_SHOWCASE_SORTS else "hot"


def _library_works_payload(request: Request, *, account_id: Optional[str], filter_value: str) -> List[Dict[str, Any]]:
    return request.app.state.quantum_read_model_service.library_works(
        account_id=account_id,
        filter_value=filter_value,
    )


def _library_stats_payload(request: Request, *, account_id: Optional[str]) -> Dict[str, Any]:
    return request.app.state.library_stats_cube_service.get_stats(account_id=account_id)


def _story_import_public_works_payload(request: Request) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for world_card in request.app.state.repository.list_worlds():
        world_id = str(world_card.get("world_id") or "").strip()
        if not world_id:
            continue
        if str(world_card.get("catalog_role") or "").strip() == "template":
            continue
        if world_card.get("public_catalog_visible") is False:
            continue
        published_summary = next(
            (
                item
                for item in request.app.state.repository.list_world_versions(world_id=world_id)
                if str(item.get("status") or "").strip() == "published"
            ),
            None,
        )
        if published_summary is None:
            continue
        try:
            version = request.app.state.repository.get_world_version(str(published_summary.get("world_version_id") or ""))
        except KeyError:
            continue
        manifest = dict(version.manifest_json or {})
        worldpack = dict(version.worldpack_json or {})
        metadata = dict(worldpack.get("metadata") or {})
        if not _is_public_catalog_visible(metadata):
            continue
        world_bible = dict(worldpack.get("world_bible") or {})
        genres = list(manifest.get("genres") or [])
        readiness = dict(metadata.get("longform_500_product_readiness") or {})
        items.append(
            {
                "id": world_id,
                "worldId": world_id,
                "worldVersionId": version.world_version_id,
                "title": str(worldpack.get("title") or world_card.get("title") or world_id),
                "authorName": str(manifest.get("author_id") or "官方"),
                "genre": str(genres[0] if genres else "未分类"),
                "coverImage": _world_cover_image(request, world_version_id=version.world_version_id),
                "description": str(world_bible.get("premise") or ""),
                "status": "available",
                "trialAvailable": bool(world_card.get("trial_available")),
                "accessState": str(world_card.get("access_state") or "trial"),
                "claimSafeBand": metadata.get("claim_safe_band") or world_card.get("claim_safe_band"),
                "productReadyBand": metadata.get("product_ready_band") or world_card.get("product_ready_band"),
                "longform500ProductReady": bool(readiness.get("ready", False)),
            }
        )
    return items


def _story_import_handoff_url(
    request: Request,
    *,
    session_id: str,
    world_id: str,
    account_id: Optional[str] = None,
) -> str:
    params = [
        ("product", "reader"),
        ("workspace", "read"),
        ("view", "experience"),
        ("session_id", session_id),
        ("world_id", world_id),
    ]
    if account_id:
        params.append(("account_id", account_id))
    query = "&".join(f"{quote_plus(key)}={quote_plus(value)}" for key, value in params)
    return f"{str(request.base_url).rstrip('/')}/app?{query}"


def _story_import_recent_payload(request: Request, *, account_id: Optional[str]) -> List[Dict[str, Any]]:
    if not account_id:
        return []
    activity_by_session = _reader_recent_activity_map(request, account_id=account_id)
    items: List[Dict[str, Any]] = []
    for session in request.app.state.repository.list_sessions():
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            continue
        try:
            detail = request.app.state.repository.get_session(session_id)
        except KeyError:
            continue
        owner_account_id = str(detail.metadata.get("reader_id") or detail.player_profile.get("reader_id") or "").strip()
        if owner_account_id != account_id:
            continue
        world_id = str(session.get("world_id") or detail.world_id or "").strip()
        world_title = world_id or session_id
        try:
            version = request.app.state.repository.get_world_version(str(detail.metadata.get("world_version_id") or ""))
        except KeyError:
            version = None
        if version is not None:
            world_title = str((version.worldpack_json or {}).get("title") or version.world_id or world_title)
        updated_at = str(activity_by_session.get(session_id, {}).get("occurred_at") or session.get("created_at") or "")
        progress = int(session.get("current_turn_index") or 0)
        items.append(
            {
                "id": session_id,
                "sessionId": session_id,
                "worldId": world_id,
                "worldVersionId": str(detail.metadata.get("world_version_id") or ""),
                "title": str(session.get("last_chapter_title") or world_title),
                "subtitle": str(session.get("last_event_title") or "继续上次推演"),
                "progress": progress,
                "coverImage": _session_cover_image(
                    request,
                    session_id=session_id,
                    world_version_id=str(detail.metadata.get("world_version_id") or ""),
                ),
                "updatedAt": updated_at,
                "handoffUrl": _story_import_handoff_url(
                    request,
                    session_id=session_id,
                    world_id=world_id,
                    account_id=account_id,
                ),
                "_updated_at_dt": _parse_iso_timestamp(updated_at),
            }
        )
    items.sort(
        key=lambda item: item.get("_updated_at_dt") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    output: List[Dict[str, Any]] = []
    for item in items:
        payload = dict(item)
        payload.pop("_updated_at_dt", None)
        output.append(payload)
    return output


def _story_owner_account_id(session_record: Any) -> Optional[str]:
    owner_account_id = str(
        (getattr(session_record, "metadata", {}) or {}).get("reader_id")
        or (getattr(session_record, "player_profile", {}) or {}).get("reader_id")
        or ""
    ).strip()
    return owner_account_id or None


def _story_identity_account_id(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    if identity is None:
        return None
    value = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    return value or None


def _story_continue_reader_id(bundle: Dict[str, Any]) -> Optional[str]:
    owner_account_id = str(bundle.get("owner_account_id") or "").strip()
    viewer_account_id = str(bundle.get("viewer_account_id") or "").strip()
    return owner_account_id or viewer_account_id or None


def _story_record_guest_session_claim(
    request: Request,
    *,
    bundle: Dict[str, Any],
    account_id: str,
) -> None:
    session_record = bundle["session_record"]
    world_version = bundle["world_version"]
    world_version_id = str((session_record.metadata or {}).get("world_version_id") or "")
    request.app.state.analytics_service.track(
        "guest_story_session_claimed",
        reader_id=account_id,
        account_id=account_id,
        session_id=session_record.session_id,
        world_id=getattr(world_version, "world_id", None) or session_record.world_id,
        world_version_id=world_version_id,
        payload_json={
            "source_surface": "story_choice",
            "claim_policy": "auto_claim_on_authenticated_choice",
        },
    )
    audit_service = getattr(request.app.state, "commercial_audit_service", None)
    if audit_service is None:
        return
    identity = dict(bundle.get("identity") or {})
    try:
        audit_service.record_audit_log(
            actor_id=account_id,
            actor_role=str(identity.get("actor_role") or "reader"),
            account_id=account_id,
            object_type="story_session",
            object_id=session_record.session_id,
            action_type="guest_story_session_claimed",
            source_surface="story_choice",
            customer_visible_payload={
                "session_id": session_record.session_id,
                "world_version_id": world_version_id,
            },
            internal_payload={
                "claim_policy": "auto_claim_on_authenticated_choice",
                "previous_owner_account_id": None,
            },
        )
    except Exception:
        return


def _story_claim_guest_session_for_viewer(request: Request, *, bundle: Dict[str, Any]) -> Dict[str, Any]:
    if str(bundle.get("owner_account_id") or "").strip():
        return bundle
    viewer_account_id = str(bundle.get("viewer_account_id") or "").strip()
    if not viewer_account_id:
        return bundle
    session_record = bundle["session_record"]
    claim = request.app.state.repository.claim_guest_session(
        session_record.session_id,
        reader_id=viewer_account_id,
    )
    claim_status = str(claim.get("status") or "")
    if claim_status == "conflict":
        raise PermissionError("story_session_forbidden")
    if claim_status == "claimed":
        _story_record_guest_session_claim(request, bundle=bundle, account_id=viewer_account_id)
    return _story_session_bundle(request, session_id=session_record.session_id)


def _story_bookmark_summary_by_session(
    request: Request,
    *,
    account_id: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    if not account_id:
        return {}
    summary: Dict[str, Dict[str, Any]] = {}
    for item in request.app.state.repository.list_story_session_bookmarks(account_id=account_id):
        session_id = str(item.get("session_id") or "").strip()
        if not session_id:
            continue
        entry = summary.setdefault(
            session_id,
            {
                "node_ids": set(),
                "count": 0,
                "latest_node_id": None,
                "latest_at": "",
                "_latest_dt": None,
            },
        )
        node_id = str(item.get("node_id") or "").strip()
        if node_id:
            entry["node_ids"].add(node_id)
        entry["count"] += 1
        updated_at = str(item.get("updated_at") or item.get("created_at") or "")
        updated_dt = _parse_iso_timestamp(updated_at)
        current_dt = entry.get("_latest_dt")
        if current_dt is None or (updated_dt is not None and updated_dt > current_dt):
            entry["latest_node_id"] = node_id or entry.get("latest_node_id")
            entry["latest_at"] = updated_at
            entry["_latest_dt"] = updated_dt
    return summary


def _story_public_share_bundle(request: Request, *, share_token: str) -> Dict[str, Any]:
    share_row = request.app.state.repository.get_story_session_share_token(share_token)
    session_record = request.app.state.repository.get_session(str(share_row.get("session_id") or ""))
    world_version_id = str((session_record.metadata or {}).get("world_version_id") or "")
    world_version = request.app.state.repository.get_world_version(world_version_id)
    chapter_rows = request.app.state.repository.list_story_chapter_payloads(session_record.session_id)
    return {
        "request": request,
        "share_row": share_row,
        "identity": None,
        "viewer_account_id": None,
        "owner_account_id": _story_owner_account_id(session_record),
        "session_record": session_record,
        "world_version": world_version,
        "chapter_rows": chapter_rows,
        "bookmark_summary_by_session": {},
    }


def _story_share_token_inactive_reason(share_row: Dict[str, Any]) -> Optional[str]:
    if str(share_row.get("status") or "active") == "revoked" or str(share_row.get("revoked_at") or "").strip():
        return "revoked"
    expires_at = _parse_iso_timestamp(share_row.get("expires_at"))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return "expired"
    return None


def _story_share_url(share_token: str) -> str:
    return f"/story/share/{quote(share_token, safe='')}"


def _story_bookmark_response_payload(
    request: Request,
    *,
    session_id: str,
    account_id: str,
    node_id: str,
    saved: bool,
    bookmark_id: Optional[str] = None,
) -> Dict[str, Any]:
    bookmark_items = request.app.state.repository.list_story_session_bookmarks(
        session_id=session_id,
        account_id=account_id,
    )
    bookmarked_node_ids = {
        str(item.get("node_id") or "").strip()
        for item in bookmark_items
        if str(item.get("node_id") or "").strip()
    }
    return {
        "bookmarkId": bookmark_id,
        "sessionId": session_id,
        "nodeId": node_id,
        "saved": saved,
        "bookmarkCount": len(bookmarked_node_ids),
        "viewerHasBookmarkedNode": node_id in bookmarked_node_ids,
    }


def _story_clamp_score(value: Any) -> int:
    try:
        numeric = int(round(float(value or 0.0)))
    except (TypeError, ValueError):
        numeric = 0
    return max(0, min(100, numeric))


def _story_get_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _story_total_deviation(state: Any) -> int:
    return _story_clamp_score(float(_story_get_field(state, "fate_pressure", 0.0) or 0.0) * 100.0)


def _story_breakdown_payload(state: Any) -> Dict[str, int]:
    themes = dict(_story_get_field(state, "themes", {}) or {})
    return {
        "character": _story_clamp_score(min(1.0, len(list(_story_get_field(state, "open_promises", []) or [])) / 5.0) * 100.0),
        "plot": _story_clamp_score(float(_story_get_field(state, "tension", 0.0) or 0.0) * 100.0),
        "theme": _story_clamp_score(max([float(value or 0.0) for value in themes.values()], default=0.0) * 100.0),
    }


def _story_paywall_payload(paywall: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not paywall:
        return None
    payload = dict(paywall)
    return {
        "required": bool(payload.get("required")),
        "reason": str(payload.get("reason") or ""),
        "quote": float(payload.get("quote") or 0.0),
        "accessTier": str(payload.get("access_tier") or ""),
        "balance": float(payload.get("balance") or 0.0) if payload.get("balance") is not None else None,
        "entitlementType": payload.get("entitlement_type"),
        "status": payload.get("status"),
    }


def _story_continuity_contract_payload(contract: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not contract:
        return None
    payload = dict(contract)
    return {
        "status": str(payload.get("status") or ""),
        "message": str(payload.get("message") or ""),
        "primaryAction": payload.get("primary_action"),
        "preserveWorkspace": payload.get("preserve_workspace"),
        "preserveSessionContext": bool(payload.get("preserve_session_context")) if payload.get("preserve_session_context") is not None else None,
        "chapterContextRetained": bool(payload.get("chapter_context_retained")) if payload.get("chapter_context_retained") is not None else None,
    }


def _story_quality_gate_payload(gate: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not gate:
        return None
    payload = dict(gate)
    return {
        "code": str(payload.get("code") or ""),
        "summary": str(payload.get("summary") or ""),
        "enforcedDecision": payload.get("enforced_decision"),
        "failedChecks": list(payload.get("failed_checks") or []),
    }


def _story_projected_current_node_id(request: Request, *, session_id: str) -> str:
    try:
        bundle = _story_session_bundle(request, session_id=session_id)
    except Exception:
        return f"node:{session_id}:0"
    nodes = _story_nodes_payload(bundle)
    return str(nodes[-1]["id"]) if nodes else f"node:{session_id}:0"


def _story_reader_view_scene_card(reader_view: Any) -> Dict[str, Any]:
    if isinstance(reader_view, dict):
        return dict(reader_view.get("scene_card") or {})
    return dict(getattr(reader_view, "scene_card", {}) or {})


def _story_reader_view_quote(reader_view: Any) -> str:
    scene_card = _story_reader_view_scene_card(reader_view)
    return str(scene_card.get("quote") or scene_card.get("pull_quote") or "").strip()


def _story_reader_view_beats(step: Any, reader_view: Any) -> List[str]:
    scene_card = _story_reader_view_scene_card(reader_view)
    beats = [
        str(item or "").strip()
        for item in list(scene_card.get("story_beats") or scene_card.get("beats") or [])
        if str(item or "").strip()
    ]
    if beats:
        return beats

    output: List[str] = []
    for beat in list(_story_get_field(step, "scene_beats", []) or []):
        event = beat.get("event") if isinstance(beat, dict) else getattr(beat, "event", None)
        title = str(_story_get_field(event, "title", "") or "").strip()
        summary = str(_story_get_field(event, "summary", "") or "").strip()
        value = title or summary
        if value:
            output.append(value)
    return output


def _world_cover_image(request: Request, *, world_version_id: str) -> str:
    service = getattr(request.app.state, "illustration_service", None)
    if service is None or not world_version_id:
        return ""
    return service.world_cover_url(world_version_id=world_version_id)


def _session_cover_image(request: Request, *, session_id: str, world_version_id: str) -> str:
    service = getattr(request.app.state, "illustration_service", None)
    if service is None:
        return ""
    return service.session_cover_url(session_id=session_id) or _world_cover_image(
        request,
        world_version_id=world_version_id,
    )


def _session_atmosphere_image(request: Request, *, session_id: str) -> str:
    service = getattr(request.app.state, "illustration_service", None)
    if service is None:
        return ""
    return service.latest_chapter_hero_url(session_id=session_id)


def _story_session_bundle(
    request: Request,
    *,
    session_id: str,
    start_chapter: Optional[int] = None,
    end_chapter: Optional[int] = None,
    limit: Optional[int] = None,
    latest: bool = False,
) -> Dict[str, Any]:
    session_record = request.app.state.repository.get_session(session_id)
    owner_account_id = _story_owner_account_id(session_record)
    identity = _maybe_identity(request)
    viewer_account_id = _story_identity_account_id(identity)
    if owner_account_id:
        if not viewer_account_id:
            raise PermissionError("auth_required")
        if viewer_account_id != owner_account_id:
            raise PermissionError("story_session_forbidden")
    world_version_id = str((session_record.metadata or {}).get("world_version_id") or "")
    world_version = request.app.state.repository.get_world_version(world_version_id)
    chapter_rows = request.app.state.repository.list_story_chapter_payloads(
        session_id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        limit=limit,
        latest=latest,
    )
    total_chapters = request.app.state.repository.count_story_chapters(session_id)
    return {
        "request": request,
        "identity": identity,
        "viewer_account_id": viewer_account_id,
        "owner_account_id": owner_account_id,
        "session_record": session_record,
        "world_version": world_version,
        "chapter_rows": chapter_rows,
        "chapter_projection": {
            "schema_version": "story_chapter_projection/v1",
            "is_windowed": any(value is not None for value in [start_chapter, end_chapter, limit]) or bool(latest),
            "start_chapter": start_chapter,
            "end_chapter": end_chapter,
            "limit": limit,
            "latest": bool(latest),
            "returned_chapters": len(chapter_rows),
            "total_chapters": total_chapters,
        },
        "bookmark_summary_by_session": _story_bookmark_summary_by_session(request, account_id=viewer_account_id),
    }


def _story_nodes_payload(bundle: Dict[str, Any], *, truncate_at_node_id: Optional[str] = None) -> List[Dict[str, Any]]:
    session_record = bundle["session_record"]
    world_version = bundle["world_version"]
    story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
    bookmark_summary = dict((bundle.get("bookmark_summary_by_session") or {}).get(session_record.session_id) or {})
    bookmarked_node_ids = set(bookmark_summary.get("node_ids") or set())
    nodes: List[Dict[str, Any]] = []

    for index, step in enumerate(story_chapters):
        reader_view = _story_get_field(step, "reader_view")
        if reader_view is None:
            continue
        chapter_index = int(
            _story_get_field(reader_view, "chapter_index", 0)
            or _story_get_field(step, "step_index", 0)
            or _story_get_field(step, "chapter_index", 0)
            or index + 1
        )
        chapter_title = str(_story_get_field(reader_view, "chapter_title", "") or f"第 {chapter_index} 章")
        scene_card = _story_reader_view_scene_card(reader_view)
        node_id = f"node:{session_record.session_id}:{chapter_index}"
        state_before = _story_get_field(step, "state_before")
        state_after = _story_get_field(step, "state_after")
        previous_total = _story_total_deviation(state_before)
        current_total = _story_total_deviation(state_after)
        is_first_story_chapter = chapter_index <= 1
        node_type = "original" if is_first_story_chapter else "ai"
        author_name = "原著开篇" if is_first_story_chapter else "AI推演"
        tension_delta = max(
            float(_story_get_field(state_after, "tension", 0.0) or 0.0)
            - float(_story_get_field(state_before, "tension", 0.0) or 0.0),
            0.0,
        )
        nodes.append(
            {
                "id": node_id,
                "content": str(_story_get_field(reader_view, "body", "") or ""),
                "chapterTitle": chapter_title,
                "chapterIndex": chapter_index,
                "quote": _story_reader_view_quote(reader_view),
                "beats": _story_reader_view_beats(step, reader_view),
                "sceneCard": scene_card,
                "type": node_type,
                "parentId": nodes[-1]["id"] if nodes else (f"node:{session_record.session_id}:{chapter_index - 1}" if chapter_index > 1 else None),
                "childrenIds": [],
                "branchType": None,
                "deviationDelta": current_total - previous_total,
                "mentalCost": max(
                    1,
                    int(round(tension_delta * 20.0)),
                ),
                "createdAt": str(_story_get_field(step, "created_at", "") or ""),
                "authorName": author_name,
                "authorAvatar": "",
                "isCurrent": False,
                "isBookmarked": node_id in bookmarked_node_ids,
            }
        )

    for index, item in enumerate(nodes):
        item["childrenIds"] = [nodes[index + 1]["id"]] if index + 1 < len(nodes) else []
        item["isCurrent"] = index == len(nodes) - 1

    if truncate_at_node_id:
        truncated: List[Dict[str, Any]] = []
        for item in nodes:
            truncated.append(item)
            if item["id"] == truncate_at_node_id:
                break
        nodes = truncated
        for index, item in enumerate(nodes):
            item["childrenIds"] = [nodes[index + 1]["id"]] if index + 1 < len(nodes) else []
            item["isCurrent"] = index == len(nodes) - 1

    if nodes:
        return nodes

    worldpack = dict(getattr(world_version, "worldpack_json", {}) or {})
    world_bible = dict(worldpack.get("world_bible") or {})
    return [
        {
            "id": f"node:{session_record.session_id}:0",
            "content": str(world_bible.get("premise") or worldpack.get("title") or world_version.world_id),
            "type": "original",
            "parentId": None,
            "childrenIds": [],
            "branchType": None,
            "deviationDelta": 0,
            "mentalCost": 1,
            "createdAt": str(getattr(session_record, "created_at", "") or ""),
            "authorName": "原著开篇",
            "authorAvatar": "",
            "isCurrent": True,
            "isBookmarked": False,
        }
    ]


def _story_session_payload(bundle: Dict[str, Any], *, truncate_at_node_id: Optional[str] = None) -> Dict[str, Any]:
    request = bundle["request"]
    session_record = bundle["session_record"]
    world_version = bundle["world_version"]
    story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
    nodes = _story_nodes_payload(bundle, truncate_at_node_id=truncate_at_node_id)
    projection = dict(bundle.get("chapter_projection") or {})
    node_count = max(len(nodes), int(projection.get("total_chapters", 0) or 0))
    current_state = getattr(session_record, "current_state", None)
    if story_chapters:
        latest_step = story_chapters[-1] if projection.get("is_windowed") else story_chapters[min(len(story_chapters), max(1, node_count)) - 1]
        current_state = _story_get_field(latest_step, "state_after", current_state)
    else:
        latest_step = None
    latest_reader_view = _story_get_field(latest_step, "reader_view") if latest_step else None
    chapter_index = int(_story_get_field(current_state, "chapter_index", 0) or 0)
    worldpack = dict(getattr(world_version, "worldpack_json", {}) or {})
    bookmark_summary = dict((bundle.get("bookmark_summary_by_session") or {}).get(session_record.session_id) or {})
    current_node_id = str(nodes[-1]["id"])
    latest_chapter_title = str(_story_get_field(latest_reader_view, "chapter_title", "") or f"第 {chapter_index} 章")
    return {
        "id": session_record.session_id,
        "title": str(worldpack.get("title") or world_version.world_id),
        "chapter": latest_chapter_title,
        "universe": str(world_version.world_id or ""),
        "coverImage": _session_cover_image(
            request,
            session_id=session_record.session_id,
            world_version_id=world_version.world_version_id,
        ),
        "status": "active",
        "nodeCount": node_count if node_count else len(nodes),
        "currentNodeId": current_node_id,
        "nodeProjection": projection,
        "atmosphereImage": _session_atmosphere_image(request, session_id=session_record.session_id),
        "mentalValue": _story_clamp_score(100 - round(float(getattr(current_state, "tension", 0.0) or 0.0) * 100.0)),
        "maxMentalValue": 100,
        "viewerHasBookmarkedCurrentNode": current_node_id in set(bookmark_summary.get("node_ids") or set()),
    }


def _story_choices_payload(bundle: Dict[str, Any], *, node_id: str) -> List[Dict[str, Any]]:
    nodes = _story_nodes_payload(bundle)
    current_node_id = str(nodes[-1]["id"])
    if node_id != current_node_id:
        return []
    story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
    latest_step = (story_chapters or [None])[-1]
    latest_reader_view = _story_get_field(latest_step, "reader_view") if latest_step else None
    current_state = getattr(bundle["session_record"], "current_state", None)
    if latest_step is not None:
        current_state = _story_get_field(latest_step, "state_after", current_state)
    current_total = _story_total_deviation(current_state)
    if latest_reader_view is None:
        return []
    scene_card = dict(getattr(latest_reader_view, "scene_card", {}) or {})
    if isinstance(latest_reader_view, dict):
        scene_card = dict(latest_reader_view.get("scene_card") or {})
    raw_choices = list(_story_get_field(latest_reader_view, "choices", []) or [])
    raw_impacts = list(_story_get_field(latest_reader_view, "choice_impacts", []) or [])
    if not raw_impacts:
        raw_impacts = build_choice_impacts(
            raw_choices,
            reader_view=latest_reader_view if isinstance(latest_reader_view, dict) else None,
            chapter_index=int(_story_get_field(latest_reader_view, "chapter_index", 0) or 0),
        )
    choices = []
    for index, choice_text in enumerate(raw_choices, start=1):
        branch_index = (index - 1) % len(QUANTUM_STORY_BRANCH_TYPES)
        impact = dict(raw_impacts[index - 1] or {}) if index - 1 < len(raw_impacts) and isinstance(raw_impacts[index - 1], dict) else {}
        choices.append(
            {
                "id": f"choice:{current_node_id}:{index}",
                "text": str(choice_text or ""),
                "description": str(scene_card.get("summary") or "继续这一幕"),
                "impact": impact,
                "branchType": QUANTUM_STORY_BRANCH_TYPES[branch_index],
                "estimatedDeviation": _story_clamp_score(current_total + QUANTUM_STORY_DEVIATION_INCREMENTS[branch_index]),
                "mentalCost": 10 + ((index - 1) * 5),
                "preview": str(choice_text or ""),
                "isPremium": False,
            }
        )
    return choices


def _story_deviation_payload(bundle: Dict[str, Any]) -> Dict[str, Any]:
    story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
    current_state = getattr(bundle["session_record"], "current_state", None)
    previous_state = None
    if story_chapters:
        latest_step = story_chapters[-1]
        current_state = _story_get_field(latest_step, "state_after", current_state)
        previous_state = _story_get_field(latest_step, "state_before")
    total_score = _story_total_deviation(current_state)
    previous_total = _story_total_deviation(previous_state) if previous_state is not None else total_score
    trend = "stable"
    if total_score > previous_total:
        trend = "increasing"
    elif total_score < previous_total:
        trend = "decreasing"
    return {
        "totalScore": total_score,
        "breakdown": _story_breakdown_payload(current_state),
        "trend": trend,
        "maxPossible": 100,
        "ifBranchCount": len(list(_story_get_field(current_state, "route_fingerprint", []) or [])),
        "parallelWorlds": 1,
    }


def _story_share_payload(bundle: Dict[str, Any], *, share_token_row: Dict[str, Any]) -> Dict[str, Any]:
    share_node_id = str(share_token_row.get("node_id") or "").strip()
    session_payload = _story_session_payload(bundle, truncate_at_node_id=share_node_id)
    nodes_payload = _story_nodes_payload(bundle, truncate_at_node_id=share_node_id)
    truncated_bundle = dict(bundle)
    story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
    if nodes_payload and len(story_chapters) >= len(nodes_payload):
        state_after = _story_get_field(story_chapters[len(nodes_payload) - 1], "state_after", {})
        state_after_payload = state_after if isinstance(state_after, dict) else state_after.to_dict()
        truncated_bundle["session_record"] = type(bundle["session_record"]).from_dict(
            {
                **bundle["session_record"].to_dict(),
                "current_state": state_after_payload,
            }
        )
        if "chapter_rows" in bundle:
            truncated_bundle["chapter_rows"] = story_chapters[: len(nodes_payload)]
        else:
            truncated_bundle["steps"] = story_chapters[: len(nodes_payload)]
    deviation_payload = _story_deviation_payload(truncated_bundle)
    return {
        "session": session_payload,
        "nodes": nodes_payload,
        "deviation": deviation_payload,
        "sharedAt": str(share_token_row.get("created_at") or ""),
        "sharerName": str(share_token_row.get("sharer_name") or ""),
        "shareToken": str(share_token_row.get("share_token") or ""),
    }


def _story_bootstrap_session(request: Request, *, session_id: str, reader_id: Optional[str]) -> Dict[str, Any]:
    session_record = request.app.state.repository.get_session(session_id)
    world_version_id = str((session_record.metadata or {}).get("world_version_id") or "")
    world_version = request.app.state.repository.get_world_version(world_version_id)
    intents = [
        "进入故事。",
        "更稳地进入故事。",
        "先从眼前局势切入。",
    ]
    latest_result: Dict[str, Any] = {}
    first_attempt_status: Optional[str] = None
    final_intent = intents[0]
    for attempt_index, intent in enumerate(intents, start=1):
        final_intent = intent
        request.app.state.analytics_service.track(
            "story_import_bootstrap_attempted",
            reader_id=reader_id,
            session_id=session_id,
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            payload_json={
                "attempt_index": attempt_index,
                "bootstrap_intent": intent,
            },
        )
        latest_result = request.app.state.session_service.continue_story(
            ReaderContinueCommand(session_id=session_id, freeform_intent=intent),
            reader_id=reader_id,
        )
        status = str(latest_result.get("status") or "")
        if first_attempt_status is None:
            first_attempt_status = status
        if status == "quality_guard_failed" and intent != intents[-1]:
            request.app.state.analytics_service.track(
                "story_import_bootstrap_retry_applied",
                reader_id=reader_id,
                session_id=session_id,
                world_id=world_version.world_id,
                world_version_id=world_version_id,
                payload_json={
                    "attempt_index": attempt_index,
                    "bootstrap_intent": intent,
                    "result_status": status,
                    "recovered_after_retry": False,
                },
            )
        if status != "quality_guard_failed":
            break
    final_status = str(latest_result.get("status") or "")
    request.app.state.analytics_service.track(
        "story_import_bootstrap_completed",
        reader_id=reader_id,
        session_id=session_id,
        world_id=world_version.world_id,
        world_version_id=world_version_id,
        payload_json={
            "attempt_index": attempt_index,
            "bootstrap_intent": final_intent,
            "first_attempt_result_status": first_attempt_status or final_status,
            "result_status": final_status,
            "recovered_after_retry": (first_attempt_status == "quality_guard_failed" and final_status != "quality_guard_failed"),
        },
    )
    return latest_result


def _reader_generation_scheduler(request: Request):
    return getattr(request.app.state, "reader_generation_job_scheduler", None)


def _enqueue_reader_generation_job(
    request: Request,
    *,
    operation: str,
    session_id: str,
    reader_id: Optional[str],
    account_id: Optional[str],
    choice_id: Optional[str] = None,
    freeform_intent: Optional[str] = None,
    steering_directive: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.enqueue_job(
        job_type=READER_GENERATION_JOB_TYPE,
        payload={
            "operation": operation,
            "session_id": session_id,
            "reader_id": reader_id,
            "account_id": account_id,
            "choice_id": choice_id,
            "freeform_intent": freeform_intent,
            "steering_directive": steering_directive,
        },
        requested_by=account_id or reader_id or "reader_guest",
        account_id=account_id or reader_id,
        schedule=_reader_generation_scheduler(request),
    )


def _story_generation_job_access(request: Request, *, job_id: str) -> Dict[str, Any]:
    job = request.app.state.async_job_service.get_job(job_id)
    if str(job.get("job_type") or "") != READER_GENERATION_JOB_TYPE:
        raise KeyError(f"unknown_story_generation_job:{job_id}")
    session_id = str((job.get("payload") or {}).get("session_id") or (job.get("result_summary") or {}).get("session_id") or "")
    if session_id:
        _story_session_bundle(request, session_id=session_id, limit=1, latest=True)
    return job


def _story_generation_job_payload(request: Request, *, job: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job.get("payload") or {})
    result_summary = dict(job.get("result_summary") or {})
    session_id = str(payload.get("session_id") or result_summary.get("session_id") or "").strip()
    operation = str(payload.get("operation") or result_summary.get("operation") or "").strip()
    reader_status = str(result_summary.get("reader_status") or "").strip() or None
    data: Dict[str, Any] = {
        "jobId": job.get("job_id"),
        "jobType": job.get("job_type"),
        "operation": operation,
        "status": job.get("status"),
        "sessionId": session_id,
        "readerStatus": reader_status,
        "pollAfterMs": 1000 if job.get("status") in {"queued", "running"} else 0,
        "retryable": job.get("status") in {"queued", "failed"} or job.get("lease_status") == "expired",
        "attemptCount": job.get("attempt_count", 0),
        "createdAt": job.get("created_at"),
        "updatedAt": job.get("updated_at"),
        "startedAt": job.get("started_at"),
        "finishedAt": job.get("finished_at"),
        "error": job.get("error"),
    }
    if job.get("status") != "succeeded":
        return data

    if reader_status == "payment_required":
        data["paywall"] = _story_paywall_payload(result_summary.get("paywall"))
        data["continuityContract"] = _story_continuity_contract_payload(result_summary.get("continuity_contract"))
        return data
    if reader_status == "quality_guard_failed":
        data["qualityGate"] = _story_quality_gate_payload(result_summary.get("quality_gate"))
        data["continuityContract"] = _story_continuity_contract_payload(result_summary.get("continuity_contract"))
        return data

    if session_id:
        bundle = _story_session_bundle(request, session_id=session_id, limit=1, latest=True)
        nodes = _story_nodes_payload(bundle)
        session_payload = _story_session_payload(bundle)
        data["session"] = session_payload
        data["node"] = nodes[-1] if nodes else None
        data["bootstrapStatus"] = reader_status or "ok"
        if operation == "story_import_bootstrap":
            data["launch"] = {
                "mode": "start",
                "sessionId": session_payload["id"],
                "worldId": result_summary.get("world_id") or bundle["world_version"].world_id,
                "worldVersionId": result_summary.get("world_version_id") or bundle["world_version"].world_version_id,
                "bootstrapStatus": reader_status or "ok",
                "handoffUrl": _story_import_handoff_url(
                    request,
                    session_id=session_payload["id"],
                    world_id=result_summary.get("world_id") or bundle["world_version"].world_id,
                    account_id=str(payload.get("account_id") or "").strip() or None,
                ),
            }
    return data

def _showcase_published_versions(request: Request) -> List[Dict[str, Any]]:
    latest_by_world: Dict[str, Dict[str, Any]] = {}
    for item in request.app.state.repository.list_world_versions(status="published"):
        world_id = str(item.get("world_id") or "").strip()
        if not world_id or world_id in latest_by_world:
            continue
        latest_by_world[world_id] = dict(item)
    return list(latest_by_world.values())


def _resolve_showcase_version(request: Request, work_id: str):
    version = request.app.state.repository.get_world_version(work_id)
    if str(version.status or "") != "published":
        raise KeyError("showcase_work_missing")
    return version


def _showcase_viewer_account_id(request: Request) -> Optional[str]:
    identity = _maybe_identity(request)
    if identity is None:
        return None
    return str(identity.get("account_id") or identity.get("actor_id") or "").strip() or None


def _showcase_interaction_maps(
    request: Request,
    *,
    world_ids: List[str],
    viewer_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    return request.app.state.quantum_read_model_service.showcase_interaction_maps(
        world_ids=world_ids,
        viewer_account_id=viewer_account_id,
    )


def _showcase_item_from_version(
    request: Request,
    *,
    version_summary: Dict[str, Any],
    hot_rank: Optional[int] = None,
    like_counts: Optional[Dict[str, int]] = None,
    comment_counts: Optional[Dict[str, int]] = None,
    liked_world_ids: Optional[set[str]] = None,
) -> Dict[str, Any]:
    return request.app.state.quantum_read_model_service.showcase_item_from_version(
        version_summary=version_summary,
        hot_rank=hot_rank,
        interaction_maps={
            "like_counts": like_counts or {},
            "comment_counts": comment_counts or {},
            "liked_world_ids": liked_world_ids or set(),
            "tip_totals": {},
            "view_counts": {},
            "impression_counts": {},
        },
        viewer_account_id=_showcase_viewer_account_id(request),
    )


def _showcase_works_payload(request: Request, *, sort_value: str, page: int, page_size: int) -> List[Dict[str, Any]]:
    viewer_account_id = _showcase_viewer_account_id(request)
    return request.app.state.quantum_read_model_service.showcase_works(
        sort_value=sort_value,
        page=page,
        page_size=page_size,
        viewer_account_id=viewer_account_id,
    )


def _showcase_comment_payload(comment: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(comment.get("showcase_comment_id") or ""),
        "authorName": str(comment.get("author_name") or comment.get("account_id") or "用户"),
        "authorAvatar": "",
        "content": str(comment.get("content") or ""),
        "createdAt": str(comment.get("created_at") or ""),
        "likeCount": 0,
    }


def _frontend_soul_profile(
    request: Optional[Request],
    *,
    user_id: str,
    authenticated_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    if request is None:
        return {
            "userId": user_id,
            "displayName": user_id,
            "avatar": "",
            "readingMileage": 0,
            "ifBranchTriggered": 0,
            "todayFocus": 0,
            "level": 1,
            "dimensions": _default_soul_dimensions(),
            "preferences": {"genres": [], "styles": [], "privacyMode": "followers"},
            "recentSessions": [],
            "viewerIsOwner": False,
            "viewerHasFollowedAuthor": False,
        }
    viewer_identity = _maybe_identity(request)
    return request.app.state.quantum_read_model_service.soul_profile(
        user_id=user_id,
        viewer_account_id=authenticated_account_id,
        viewer_actor_id=str((viewer_identity or {}).get("actor_id") or "").strip() or None,
    )


def _frontend_auth_response(
    request: Request,
    *,
    identity: Dict[str, Any],
    access_token: str,
    refresh_token: Optional[str],
) -> Dict[str, Any]:
    return {
        "user": _frontend_user(request, identity),
        "token": access_token,
        "refreshToken": str(refresh_token or ""),
    }


@router.get("/health")
def quantum_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.get("/soul/profile")
def quantum_soul_profile(request: Request) -> Dict[str, Any]:
    identity = _maybe_identity(request)
    user_id = "guest"
    account_id = None
    if identity is not None:
        user_id = str(identity.get("account_id") or identity.get("actor_id") or "guest").strip() or "guest"
        account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip() or None
    return _success(data=_frontend_soul_profile(request, user_id=user_id, authenticated_account_id=account_id))


@router.get("/soul/profile/{user_id}")
def quantum_soul_profile_by_id(user_id: str, request: Request) -> Dict[str, Any]:
    normalized = str(user_id or "").strip() or "guest"
    viewer_identity = _maybe_identity(request)
    return _success(
        data=request.app.state.quantum_read_model_service.soul_profile(
            user_id=normalized,
            viewer_account_id=str((viewer_identity or {}).get("account_id") or (viewer_identity or {}).get("actor_id") or "").strip() or None,
            viewer_actor_id=str((viewer_identity or {}).get("actor_id") or "").strip() or None,
        )
    )


@router.put("/soul/preferences")
def quantum_soul_preferences(payload: QuantumSoulPreferencesRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        updated = request.app.state.quantum_read_model_service.update_soul_preferences(
            actor_id=str(identity.get("actor_id") or "").strip(),
            account_id=_quantum_identity_account_id(identity) or None,
            genres=payload.genres,
            styles=payload.styles,
            privacy_mode=payload.privacyMode,
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(
        data={
            "genres": list(updated.get("genres") or []),
            "styles": list(updated.get("styles") or []),
            "privacyMode": str(updated.get("privacy_mode") or "followers"),
        }
    )


@router.post("/auth/register")
def quantum_register(payload: QuantumAuthRegisterRequest, request: Request, response: Response) -> Any:
    username = str(payload.username or "").strip()
    email = str(payload.email or "").strip()
    password = str(payload.password or "").strip()
    display_name = str(payload.displayName or "").strip()
    if not username:
        return _error(status_code=400, message="username_required")
    if not email:
        return _error(status_code=400, message="email_required")
    if not password:
        return _error(status_code=400, message="password_required")
    try:
        _ensure_registration_available(request, username=username, email=email)
        request.app.state.auth_service.register_identity(
            actor_id=username,
            actor_role="author",
            password=password,
            account_id=email,
            display_name=display_name or username,
        )
        token_result = request.app.state.auth_service.issue_token(actor_id=username, password=password)
        response.set_cookie(
            value=token_result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return _success(
            data=_frontend_auth_response(
                request,
                identity=token_result["identity"],
                access_token=token_result["token"]["access_token"],
                refresh_token=(token_result.get("refresh") or {}).get("refresh_token"),
            )
        )
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if message in {"username_already_registered", "email_already_registered"} else 400
        return _error(status_code=status_code, message=message)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _error(status_code=500, message=str(exc) or "compat_auth_register_failed")


@router.post("/auth/login")
def quantum_login(payload: QuantumAuthLoginRequest, request: Request, response: Response) -> Any:
    try:
        actor_id = _resolve_login_actor_id(request, payload.identifier)
        token_result = request.app.state.auth_service.issue_token(actor_id=actor_id, password=payload.password)
        response.set_cookie(
            value=token_result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return _success(
            data=_frontend_auth_response(
                request,
                identity=token_result["identity"],
                access_token=token_result["token"]["access_token"],
                refresh_token=(token_result.get("refresh") or {}).get("refresh_token"),
            )
        )
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc) or "auth_login_failed")
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))


@router.post("/auth/refresh")
def quantum_refresh(payload: QuantumAuthRefreshRequest, request: Request, response: Response) -> Any:
    try:
        token_result = request.app.state.auth_service.refresh_access_token(raw_refresh_token=payload.refreshToken)
        response.set_cookie(
            value=token_result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return _success(
            data=_frontend_auth_response(
                request,
                identity=token_result["identity"],
                access_token=token_result["token"]["access_token"],
                refresh_token=(token_result.get("refresh") or {}).get("refresh_token"),
            )
        )
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc) or "auth_refresh_failed")
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_refresh_missing")


@router.get("/auth/me")
def quantum_me(request: Request) -> Any:
    raw_token = _request_token(request)
    if not raw_token:
        return _error(status_code=401, message="missing_bearer_token")
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
        return _success(data=_frontend_user(request, identity))
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc) or "auth_token_invalid")
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.put("/auth/profile")
def quantum_update_profile(payload: QuantumAuthProfileUpdateRequest, request: Request) -> Any:
    raw_token = _request_token(request)
    if not raw_token:
        return _error(status_code=401, message="missing_bearer_token")
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
        updated = request.app.state.auth_service.update_profile(
            actor_id=str(identity.get("actor_id") or ""),
            display_name=payload.displayName,
            avatar_url=payload.avatar,
            email_address=payload.email,
        )
        return _success(data=_frontend_user(request, updated["identity"]))
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc) or "auth_token_invalid")
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.post("/auth/logout")
def quantum_logout(request: Request, response: Response) -> Dict[str, Any]:
    raw_token = _request_token(request)
    if raw_token:
        try:
            request.app.state.auth_service.revoke_bearer_token(raw_token)
        except (PermissionError, KeyError):
            pass
    response.delete_cookie(
        key=request.app.state.auth_service.auth_cookie_settings()["key"],
        path="/",
        domain=request.app.state.auth_service.auth_cookie_settings().get("domain"),
    )
    return _success(data=None)


@router.get("/settings/membership/plans")
def quantum_membership_plans(request: Request) -> Dict[str, Any]:
    return _success(data=_membership_plan_catalog(request))


@router.get("/settings/ink/packages")
def quantum_ink_packages(request: Request) -> Dict[str, Any]:
    return _success(data=_ink_packages_catalog(request))


@router.get("/settings/preferences")
def quantum_settings_preferences(request: Request) -> Any:
    try:
        identity = _require_identity(request)
        settings = request.app.state.auth_service.get_user_settings(actor_id=str(identity.get("actor_id") or ""))
        return _success(data=settings)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.put("/settings/preferences")
def quantum_update_settings_preferences(payload: QuantumSettingsPreferencesRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        settings = request.app.state.auth_service.update_user_settings(
            actor_id=str(identity.get("actor_id") or ""),
            settings_updates=payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True),
        )
        return _success(data=settings)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.get("/ops/bootstrap")
def quantum_ops_bootstrap(request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(data=_quantum_ops_bootstrap_payload(request, identity=identity))


@router.get("/ops/workspaces/reviewer")
def quantum_ops_reviewer_workspace(request: Request, reviewItemId: Optional[str] = None, limit: int = 40) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_reviewer_workspace_payload(
            request,
            selected_review_item_id=reviewItemId,
            limit=max(1, min(100, int(limit or 40))),
        )
    )


@router.get("/ops/workspaces/runtime")
def quantum_ops_runtime_workspace(
    request: Request,
    accountId: Optional[str] = None,
    worldId: Optional[str] = None,
    limit: int = 20,
) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(accountId or "").strip() or _quantum_identity_account_id(identity) or None
    return _success(
        data=_quantum_ops_runtime_workspace_payload(
            request,
            account_id=resolved_account_id,
            world_id=worldId,
            limit=max(1, min(100, int(limit or 20))),
        )
    )


@router.get("/ops/workspaces/account")
def quantum_ops_account_workspace(request: Request, accountId: Optional[str] = None, limit: int = 12) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(accountId or "").strip() or _quantum_identity_account_id(identity)
    if not resolved_account_id:
        return _error(status_code=400, message="ops_account_required")
    return _success(
        data=_quantum_ops_account_workspace_payload(
            request,
            account_id=resolved_account_id,
            limit=max(1, min(100, int(limit or 12))),
        )
    )


@router.get("/ops/workspaces/release")
def quantum_ops_release_workspace(request: Request, worldId: Optional[str] = None, limit: int = 12) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_release_workspace_payload(
            request,
            world_id=worldId,
            limit=max(1, min(100, int(limit or 12))),
        )
    )


@router.get("/ops/workspaces/alerts")
def quantum_ops_alerts_workspace(request: Request, accountId: Optional[str] = None, alertId: Optional[str] = None, limit: int = 20) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(accountId or "").strip() or _quantum_identity_account_id(identity) or None
    return _success(
        data=_quantum_ops_alerts_workspace_payload(
            request,
            account_id=resolved_account_id,
            alert_id=alertId,
            limit=max(1, min(100, int(limit or 20))),
        )
    )


@router.get("/ops/workspaces/learned")
def quantum_ops_learned_workspace(request: Request, worldId: Optional[str] = None, issueCode: Optional[str] = None, limit: int = 20) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_learned_workspace_payload(
            request,
            world_id=worldId,
            issue_code=issueCode,
            limit=max(1, min(100, int(limit or 20))),
        )
    )


@router.get("/ops/workspaces/governance")
def quantum_ops_governance_workspace(request: Request, accountId: Optional[str] = None, caseId: Optional[str] = None, limit: int = 20) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(accountId or "").strip() or _quantum_identity_account_id(identity) or None
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=caseId,
            limit=max(1, min(100, int(limit or 20))),
        )
    )


@router.get("/ops/workspaces/governance/queue")
def quantum_ops_governance_queue_workspace(
    request: Request,
    status: Optional[str] = None,
    ownerId: Optional[str] = None,
    caseType: Optional[str] = None,
    severity: Optional[str] = None,
    targetType: Optional[str] = None,
    hasActiveRestriction: Optional[bool] = None,
    overdueOnly: bool = False,
    unassignedOnly: bool = False,
    search: Optional[str] = None,
    selectedCaseIds: Optional[str] = None,
    limit: int = 100,
) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_queue_workspace_payload(
            request,
            status=str(status or "").strip() or None,
            owner_id=str(ownerId or "").strip() or None,
            case_type=str(caseType or "").strip() or None,
            severity=str(severity or "").strip() or None,
            target_type=str(targetType or "").strip() or None,
            has_active_restriction=hasActiveRestriction,
            overdue_only=bool(overdueOnly),
            unassigned_only=bool(unassignedOnly),
            search=str(search or "").strip() or None,
            selected_case_ids=[item.strip() for item in str(selectedCaseIds or "").split(",") if item.strip()],
            limit=max(1, min(200, int(limit or 100))),
        )
    )


@router.get("/ops/workspaces/governance/cases/{caseId}/restriction-history")
def quantum_ops_governance_case_restriction_history(caseId: str, request: Request, limit: int = 20) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    try:
        return _success(data=request.app.state.governance_service.restriction_history(caseId, limit=max(1, min(100, int(limit or 20)))))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))


@router.put("/ops/workspaces/governance/capacity/owners/{ownerId}")
def quantum_ops_update_governance_capacity_override(ownerId: str, payload: QuantumOpsGovernanceCapacityOverrideRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    if str(identity.get("actor_role") or "").strip() != "admin":
        return _error(status_code=403, message="governance_capacity_admin_required")
    try:
        request.app.state.governance_service.update_capacity_override(
            ownerId,
            capacity_units_per_day=payload.capacityUnitsPerDay,
            critical_case_limit=payload.criticalCaseLimit,
            active_restriction_limit=payload.activeRestrictionLimit,
            sla_hours=payload.slaHours,
            role_multiplier=payload.roleMultiplier,
            enabled=payload.enabled,
            clear_override=bool(payload.clearOverride),
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            note=str(payload.note or "").strip() or None,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(
        data=_quantum_ops_governance_queue_workspace_payload(
            request,
            status=None,
            owner_id=None,
            case_type=None,
            severity=None,
            target_type=None,
            has_active_restriction=None,
            overdue_only=False,
            unassigned_only=False,
            search=None,
            selected_case_ids=None,
            limit=100,
        )
    )


@router.post("/ops/workspaces/governance/cases")
def quantum_ops_create_governance_case(payload: QuantumOpsGovernanceCreateCaseRequest, request: Request) -> Any:
    summary = str(payload.summary or "").strip()
    if not summary:
        return _error(status_code=400, message="governance_case_summary_required")
    case_type = str(payload.caseType or "").strip()
    target_type = str(payload.targetType or "").strip()
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))

    resolved_account_id = str(payload.accountId or "").strip() or None
    resolved_target_id = str(payload.targetId or "").strip() or None
    if target_type == "account":
        resolved_target_id = resolved_target_id or resolved_account_id
        resolved_account_id = resolved_account_id or resolved_target_id
        if not resolved_target_id:
            return _error(status_code=400, message="governance_case_target_required")
    elif not resolved_account_id:
        return _error(status_code=400, message="ops_account_required")
    elif not resolved_target_id:
        return _error(status_code=400, message="governance_case_target_required")

    apply_restriction = payload.applyRestriction or QuantumOpsGovernanceRestrictionConfig()
    actor_id = str(identity.get("actor_id") or "").strip()
    actor_role = str(identity.get("actor_role") or "").strip() or None
    canonical_payload: Dict[str, Any] = {
        "case_type": case_type,
        "target_type": target_type,
        "target_id": resolved_target_id,
        "account_id": resolved_account_id,
        "due_at": str(payload.dueAt or "").strip() or None,
        "severity": str(payload.severity or "medium").strip() or "medium",
        "summary": summary,
        "description": str(payload.description or "").strip() or None,
        "reviewer_id": actor_id or None,
        "owner_id": actor_id or None,
        "policy_labels": list(payload.policyLabels or []),
        "support_issue_ids": list(payload.supportIssueIds or []),
        "source": "quantum_ops",
        "actor_role": actor_role,
        "source_surface": "quantum_ops",
    }
    if target_type == "world_version":
        canonical_payload["world_version_id"] = resolved_target_id
    elif target_type == "session":
        canonical_payload["session_id"] = resolved_target_id
    elif target_type == "entitlement":
        canonical_payload["entitlement_id"] = resolved_target_id

    try:
        if apply_restriction.enabled:
            if not resolved_account_id:
                return _error(status_code=400, message="ops_account_required")
            restriction_type = str(apply_restriction.restrictionType or "").strip()
            if not restriction_type:
                return _error(status_code=400, message="governance_restriction_type_required")
            case = request.app.state.governance_service.apply_restriction(
                {
                    **canonical_payload,
                    "restriction_type": restriction_type,
                    "expires_at": str(apply_restriction.expiresAt or "").strip() or None,
                    "restriction_reason": str(apply_restriction.restrictionReason or "").strip() or None,
                }
            )
        else:
            case = request.app.state.governance_service.create_case(canonical_payload)
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))

    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=str(case.get("case_id") or ""),
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/restrictions")
def quantum_ops_apply_governance_restriction(payload: QuantumOpsGovernanceApplyRestrictionRequest, request: Request) -> Any:
    summary = str(payload.summary or "").strip()
    if not summary:
        return _error(status_code=400, message="governance_restriction_summary_required")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    if not resolved_account_id:
        return _error(status_code=400, message="ops_account_required")
    try:
        case = request.app.state.governance_service.apply_restriction(
            {
                "restriction_type": str(payload.restrictionType or "").strip(),
                "account_id": resolved_account_id,
                "case_type": "abuse",
                "severity": str(payload.severity or "high").strip() or "high",
                "summary": summary,
                "description": str(payload.description or "").strip() or None,
                "reviewer_id": str(identity.get("actor_id") or "").strip() or None,
                "actor_role": str(identity.get("actor_role") or "").strip() or None,
                "expires_at": str(payload.expiresAt or "").strip() or None,
                "restriction_reason": str(payload.restrictionReason or "").strip() or None,
                "support_issue_ids": list(payload.supportIssueIds or []),
                "source_surface": "quantum_ops",
            }
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=str(case.get("case_id") or ""),
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/cases/{caseId}/apply-restriction")
def quantum_ops_apply_governance_case_restriction(caseId: str, payload: QuantumOpsGovernanceCaseRestrictionRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    try:
        case = request.app.state.governance_service.apply_case_restriction(
            caseId,
            restriction_type=str(payload.restrictionType or "").strip(),
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            restriction_reason=str(payload.restrictionReason or "").strip() or None,
            expires_at=str(payload.expiresAt or "").strip() or None,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=str(case.get("case_id") or caseId),
            limit=20,
        )
    )


@router.post("/ops/workspaces/alerts/{alertId}/acknowledge")
def quantum_ops_acknowledge_alert(alertId: str, payload: QuantumOpsAlertMutationRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    if str(alertId).startswith("quantum_ops_light::"):
        request.app.state.commercial_audit_service.record_audit_log(
            actor_id=str(identity.get("actor_id") or "").strip() or "ops_unknown",
            actor_role=str(identity.get("actor_role") or "admin"),
            account_id=resolved_account_id,
            object_type="ops_alert",
            object_id=alertId,
            action_type="ops_alert_acknowledged",
            source_surface="quantum_ops",
            customer_visible_payload={"status": "acknowledged", "summary": "Remote Ops lightweight alert"},
            internal_payload={"note": payload.note, "alert_id": alertId},
        )
    else:
        try:
            request.app.state.ops_alerting_service.update_alert_status(
                alertId,
                status="acknowledged",
                reviewer_id=str(identity.get("actor_id") or "").strip() or None,
                actor_role=str(identity.get("actor_role") or "").strip() or None,
                note=payload.note,
                account_id=resolved_account_id,
                source_surface="quantum_ops",
            )
        except KeyError as exc:
            return _error(status_code=404, message=str(exc))
        except ValueError as exc:
            return _error(status_code=400, message=str(exc))
    return _success(
        data=_quantum_ops_alerts_workspace_payload(
            request,
            account_id=resolved_account_id,
            alert_id=alertId,
            limit=20,
        )
    )


@router.post("/ops/workspaces/alerts/{alertId}/resolve")
def quantum_ops_resolve_alert(alertId: str, payload: QuantumOpsAlertMutationRequest, request: Request) -> Any:
    if not str(payload.note or "").strip():
        return _error(status_code=400, message="alert_resolution_note_required")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    if str(alertId).startswith("quantum_ops_light::"):
        request.app.state.commercial_audit_service.record_audit_log(
            actor_id=str(identity.get("actor_id") or "").strip() or "ops_unknown",
            actor_role=str(identity.get("actor_role") or "admin"),
            account_id=resolved_account_id,
            object_type="ops_alert",
            object_id=alertId,
            action_type="ops_alert_resolved",
            source_surface="quantum_ops",
            customer_visible_payload={"status": "resolved", "summary": "Remote Ops lightweight alert"},
            internal_payload={"note": payload.note, "alert_id": alertId},
        )
    else:
        try:
            request.app.state.ops_alerting_service.update_alert_status(
                alertId,
                status="resolved",
                reviewer_id=str(identity.get("actor_id") or "").strip() or None,
                actor_role=str(identity.get("actor_role") or "").strip() or None,
                note=payload.note,
                account_id=resolved_account_id,
                source_surface="quantum_ops",
            )
        except KeyError as exc:
            return _error(status_code=404, message=str(exc))
        except ValueError as exc:
            return _error(status_code=400, message=str(exc))
    return _success(
        data=_quantum_ops_alerts_workspace_payload(
            request,
            account_id=resolved_account_id,
            alert_id=alertId,
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/cases/{caseId}/assign")
def quantum_ops_assign_governance_case(caseId: str, payload: QuantumOpsGovernanceAssignRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    actor_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.governance_service.assign_case(
            caseId,
            owner_id=str(payload.ownerId or "").strip() or actor_id,
            reviewer_id=actor_id,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            due_at=str(payload.dueAt or "").strip() or None,
            note=payload.note,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=caseId,
            limit=20,
        )
    )


@router.patch("/ops/workspaces/governance/restrictions/{restrictionId}")
def quantum_ops_update_governance_restriction(restrictionId: str, payload: QuantumOpsGovernanceRestrictionUpdateRequest, request: Request) -> Any:
    if payload.restrictionType is None and payload.restrictionReason is None and payload.expiresAt is None:
        return _error(status_code=400, message="governance_restriction_update_empty")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    try:
        case = request.app.state.governance_service.update_restriction(
            restrictionId,
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            restriction_type=str(payload.restrictionType or "").strip() or None,
            restriction_reason=str(payload.restrictionReason or "").strip() or None,
            expires_at=payload.expiresAt,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=str(case.get("case_id") or ""),
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/cases/{caseId}/status")
def quantum_ops_update_governance_case_status(caseId: str, payload: QuantumOpsGovernanceStatusRequest, request: Request) -> Any:
    normalized_status = str(payload.status or "").strip()
    if normalized_status in {"resolved", "dismissed"} and not str(payload.resolutionNotes or "").strip():
        return _error(status_code=400, message="resolution_notes_required")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    actor_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.governance_service.update_case_status(
            caseId,
            status=normalized_status,
            reviewer_id=actor_id,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            resolution_notes=payload.resolutionNotes,
            disposition=payload.disposition,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=caseId,
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/cases/{caseId}/evidence")
def quantum_ops_append_governance_case_evidence(caseId: str, payload: QuantumOpsGovernanceEvidenceRequest, request: Request) -> Any:
    title = str(payload.title or "").strip()
    preview = str(payload.preview or "").strip()
    if not title:
        return _error(status_code=400, message="governance_evidence_title_required")
    if not preview:
        return _error(status_code=400, message="governance_evidence_preview_required")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    actor_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.governance_service.append_case_evidence(
            caseId,
            reviewer_id=actor_id,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            title=title,
            preview=preview,
            ref_id=str(payload.refId or "").strip() or None,
            kind=str(payload.kind or "note").strip() or "note",
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=caseId,
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/cases/{caseId}/release-restriction")
def quantum_ops_release_governance_case_restriction(caseId: str, payload: QuantumOpsGovernanceRestrictionReleaseRequest, request: Request) -> Any:
    release_reason = str(payload.releaseReason or "").strip()
    if not release_reason:
        return _error(status_code=400, message="governance_restriction_release_reason_required")
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    resolved_account_id = str(payload.accountId or "").strip() or _quantum_identity_account_id(identity) or None
    try:
        selected_case_detail = dict(
            request.app.state.governance_service.case_detail(
                caseId,
                actor_id=str(identity.get("actor_id") or "").strip() or None,
                actor_role=str(identity.get("actor_role") or "").strip() or None,
            )
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    restriction = dict(selected_case_detail.get("restriction") or {})
    restriction_id = str(restriction.get("restriction_id") or "").strip()
    if not restriction_id or str(restriction.get("status") or "") != "active":
        return _error(status_code=400, message="governance_case_restriction_missing")
    try:
        request.app.state.governance_service.release_restriction(
            restriction_id,
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            release_reason=release_reason,
            source_surface="quantum_ops",
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_workspace_payload(
            request,
            account_id=resolved_account_id,
            case_id=caseId,
            limit=20,
        )
    )


@router.post("/ops/workspaces/governance/bulk/preview")
def quantum_ops_governance_bulk_preview(payload: QuantumOpsGovernanceBulkActionRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    canonical_payload = {
        "owner_id": str(payload.ownerId or "").strip() or None,
        "owner_assignments": dict(payload.ownerAssignments or {}),
        "due_at": str(payload.dueAt or "").strip() or None,
        "note": str(payload.note or "").strip() or None,
        "status": str(payload.status or "").strip() or None,
        "resolution_notes": str(payload.resolutionNotes or "").strip() or None,
        "disposition": str(payload.disposition or "").strip() or None,
        "policy_labels": list(payload.policyLabels or []),
        "restriction_type": str(payload.restrictionType or "").strip() or None,
        "restriction_reason": str(payload.restrictionReason or "").strip() or None,
        "expires_at": str(payload.expiresAt or "").strip() or None,
    }
    try:
        preview = request.app.state.governance_service.bulk_action_preview(
            case_ids=list(payload.caseIds or []),
            action=str(payload.action or "").strip(),
            payload=canonical_payload,
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(
        data=_quantum_ops_governance_queue_workspace_payload(
            request,
            status=None,
            owner_id=None,
            case_type=None,
            severity=None,
            target_type=None,
            has_active_restriction=None,
            overdue_only=False,
            unassigned_only=False,
            search=None,
            selected_case_ids=list(payload.caseIds or []),
            limit=100,
            bulk_preview_result=preview,
        )
    )


@router.post("/ops/workspaces/governance/bulk/execute")
def quantum_ops_governance_bulk_execute(payload: QuantumOpsGovernanceBulkActionRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    canonical_payload = {
        "owner_id": str(payload.ownerId or "").strip() or None,
        "owner_assignments": dict(payload.ownerAssignments or {}),
        "due_at": str(payload.dueAt or "").strip() or None,
        "note": str(payload.note or "").strip() or None,
        "status": str(payload.status or "").strip() or None,
        "resolution_notes": str(payload.resolutionNotes or "").strip() or None,
        "disposition": str(payload.disposition or "").strip() or None,
        "policy_labels": list(payload.policyLabels or []),
        "restriction_type": str(payload.restrictionType or "").strip() or None,
        "restriction_reason": str(payload.restrictionReason or "").strip() or None,
        "expires_at": str(payload.expiresAt or "").strip() or None,
    }
    try:
        execution = request.app.state.governance_service.bulk_action_execute(
            case_ids=list(payload.caseIds or []),
            action=str(payload.action or "").strip(),
            payload=canonical_payload,
            reviewer_id=str(identity.get("actor_id") or "").strip() or None,
            actor_role=str(identity.get("actor_role") or "").strip() or None,
            source_surface="quantum_ops",
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(
        data=_quantum_ops_governance_queue_workspace_payload(
            request,
            status=None,
            owner_id=None,
            case_type=None,
            severity=None,
            target_type=None,
            has_active_restriction=None,
            overdue_only=False,
            unassigned_only=False,
            search=None,
            selected_case_ids=list(payload.caseIds or []),
            limit=100,
            bulk_execution_result=execution,
        )
    )


@router.post("/ops/workspaces/reviewer/review-items/{reviewItemId}/assign")
def quantum_ops_assign_review_item(reviewItemId: str, request: Request, payload: Optional[QuantumOpsReviewAssignRequest] = None) -> Any:
    del payload
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    reviewer_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.ops_review_hub_service.assign_review_item(
            review_item_id=reviewItemId,
            owner_id=reviewer_id,
            reviewer_id=reviewer_id,
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(data=_quantum_ops_reviewer_workspace_payload(request, selected_review_item_id=reviewItemId, limit=40))


@router.post("/ops/workspaces/reviewer/review-items/{reviewItemId}/status")
def quantum_ops_update_review_item_status(reviewItemId: str, payload: QuantumOpsReviewStatusRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    reviewer_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.ops_review_hub_service.update_review_item_status(
            review_item_id=reviewItemId,
            status=payload.status,
            reviewer_id=reviewer_id,
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(data=_quantum_ops_reviewer_workspace_payload(request, selected_review_item_id=reviewItemId, limit=40))


@router.post("/ops/workspaces/reviewer/review-items/{reviewItemId}/decision")
def quantum_ops_decide_review_item(reviewItemId: str, payload: QuantumOpsReviewDecisionRequest, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    reviewer_id = str(identity.get("actor_id") or "").strip()
    try:
        request.app.state.ops_review_hub_service.decide_review_item(
            review_item_id=reviewItemId,
            decision=payload.decision,
            reviewer_id=reviewer_id,
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    return _success(data=_quantum_ops_reviewer_workspace_payload(request, selected_review_item_id=reviewItemId, limit=40))


@router.post("/ops/workspaces/account/{accountId}/grant-subscription")
def quantum_ops_grant_subscription(accountId: str, payload: QuantumOpsGrantSubscriptionRequest, request: Request) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    subscription = request.app.state.billing_service.grant_subscription(
        {
            "account_id": accountId,
            "tier_id": payload.tierId,
            "provider": "ops_manual",
            "status": "active",
        }
    )
    request.app.state.analytics_service.track(
        "subscription_activated",
        reader_id=accountId,
        account_id=accountId,
        access_tier=subscription.get("tier_id"),
        payload_json=subscription,
    )
    return _success(data=_quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12))


@router.post("/ops/workspaces/account/{accountId}/grant-wallet")
def quantum_ops_grant_wallet(accountId: str, payload: QuantumOpsGrantWalletRequest, request: Request) -> Any:
    try:
        _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    entitlement = request.app.state.billing_service.grant_wallet_credits(
        account_id=accountId,
        wallet_type=payload.walletType,
        amount=payload.amount,
        tier_id=payload.tierId,
    )
    request.app.state.analytics_service.track(
        "entitlement_granted",
        reader_id=accountId,
        account_id=accountId,
        access_tier=payload.tierId,
        payload_json=entitlement,
    )
    return _success(data=_quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12))


@router.post("/ops/workspaces/account/{accountId}/retry-subscription-payment")
def quantum_ops_retry_subscription_payment(accountId: str, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    account_payload = _quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12)
    subscription_id = _quantum_ops_primary_subscription_id(dict(account_payload.get("accountDetail") or {}))
    if not subscription_id:
        return _error(status_code=400, message="ops_account_subscription_missing")
    try:
        retried = request.app.state.billing_service.retry_subscription_payment(subscription_id=subscription_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    request.app.state.analytics_service.track(
        "subscription_retry_requested",
        reader_id=accountId,
        account_id=accountId,
        payload_json={"subscription_id": subscription_id, "requested_by": str(identity.get("actor_id") or ""), **retried},
    )
    return _success(data=_quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12))


@router.post("/ops/workspaces/account/{accountId}/reconcile-subscription")
def quantum_ops_reconcile_subscription(accountId: str, request: Request) -> Any:
    try:
        identity = _require_quantum_ops_actor(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=403, message=str(exc))
    account_payload = _quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12)
    subscription_id = _quantum_ops_primary_subscription_id(dict(account_payload.get("accountDetail") or {}))
    if not subscription_id:
        return _error(status_code=400, message="ops_account_subscription_missing")
    try:
        reconciled = request.app.state.billing_service.reconcile_subscription(subscription_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    request.app.state.analytics_service.track(
        "subscription_reconcile_requested",
        reader_id=accountId,
        account_id=accountId,
        payload_json={"subscription_id": subscription_id, "requested_by": str(identity.get("actor_id") or ""), **reconciled},
    )
    return _success(data=_quantum_ops_account_workspace_payload(request, account_id=accountId, limit=12))


@router.get("/studio/projects/{project_id}")
def quantum_studio_project(project_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")
    try:
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    return _success(data=request.app.state.author_project_graph_service.project_payload(project_id=project_id, draft_detail=draft_detail))


@router.post("/studio/projects/{project_id}/nodes")
def quantum_studio_add_node(project_id: str, payload: QuantumStudioNodeCreateRequest, request: Request) -> Any:
    if str(payload.type or "").strip() not in {"root", "branch", "end"}:
        return _error(status_code=400, message="studio_node_type_invalid")
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")

    updated = request.app.state.author_project_graph_service.add_node(
        project_id=project_id,
        draft_detail=draft_detail,
        payload=payload.model_dump(),
    )
    return _success(data=updated)


@router.put("/studio/projects/{project_id}/nodes/{node_id}")
def quantum_studio_update_node(project_id: str, node_id: str, payload: QuantumStudioNodeUpdateRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")

    try:
        updated = request.app.state.author_project_graph_service.update_node(
            project_id=project_id,
            draft_detail=draft_detail,
            node_id=node_id,
            payload=payload.model_dump(exclude_none=False),
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    return _success(data=updated)


@router.post("/studio/projects/{project_id}/preview")
def quantum_studio_preview(project_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")
    request.app.state.author_project_graph_service.project_payload(project_id=project_id, draft_detail=draft_detail)
    report = request.app.state.authoring_service.run_simulation_for_world_version(project_id)
    return _success(data=_studio_preview_payload(project_id, report))


@router.get("/studio/projects/{project_id}/export")
def quantum_studio_export(project_id: str, format: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")
    normalized = str(format or "").strip().lower()
    if normalized not in {"json", "markdown", "pdf"}:
        return _error(status_code=400, message="studio_export_format_invalid")
    project = request.app.state.author_project_graph_service.project_payload(project_id=project_id, draft_detail=draft_detail)
    return _success(data=request.app.state.author_project_graph_service.export_project(project=project, format_value=normalized))


@router.put("/studio/projects/{project_id}/engine")
def quantum_studio_set_engine(project_id: str, payload: QuantumStudioEngineRequest, request: Request) -> Any:
    engine = str(payload.engine or "").strip()
    if engine not in QUANTUM_STUDIO_ENGINES:
        return _error(status_code=400, message="studio_engine_invalid")
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")
    updated = request.app.state.author_project_graph_service.set_engine(
        project_id=project_id,
        draft_detail=draft_detail,
        engine=engine,
    )
    return _success(data=updated)


@router.put("/studio/projects/{project_id}/world-rules")
def quantum_studio_world_rules(project_id: str, payload: QuantumStudioWorldRulesRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        draft_detail = request.app.state.authoring_service.get_draft(project_id)
        _ensure_studio_project_owner(identity, draft_detail)
    except PermissionError as exc:
        return _error(status_code=401 if str(exc) == "missing_bearer_token" else 403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "studio_project_missing")
    worldpack = dict(draft_detail.get("worldpack") or {})
    valid_rule_ids = {item["id"] for item in _studio_world_rule_specs(worldpack)}
    requested_rule_ids = [str(item).strip() for item in payload.ruleIds if str(item).strip()]
    if any(item not in valid_rule_ids for item in requested_rule_ids):
        return _error(status_code=400, message="studio_world_rules_invalid")
    updated = request.app.state.author_project_graph_service.set_world_rules(
        project_id=project_id,
        draft_detail=draft_detail,
        rule_ids=sorted(set(requested_rule_ids)),
    )
    return _success(data=updated)


@router.get("/library/works")
def quantum_library_works(request: Request, filter: str = "recent") -> Dict[str, Any]:
    identity = _maybe_identity(request)
    account_id = None
    if identity is not None:
        account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip() or None
    return _success(data=_library_works_payload(request, account_id=account_id, filter_value=filter))


@router.get("/library/stats")
def quantum_library_stats(request: Request) -> Dict[str, Any]:
    identity = _maybe_identity(request)
    account_id = None
    if identity is not None:
        account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip() or None
    return _success(data=_library_stats_payload(request, account_id=account_id))


@router.get("/library/achievements")
def quantum_library_achievements(request: Request) -> Dict[str, Any]:
    identity = _maybe_identity(request)
    account_id = None
    if identity is not None:
        account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip() or None
    return _success(data=request.app.state.quantum_read_model_service.library_achievements(account_id=account_id))


@router.post("/library/follows")
def quantum_library_follow(payload: QuantumLibraryFollowRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        data = request.app.state.quantum_read_model_service.follow_library_target(
            account_id=_quantum_identity_account_id(identity),
            actor_id=_quantum_identity_actor_id(identity) or None,
            target_type=payload.targetType,
            target_id=payload.targetId,
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    return _success(data=data)


@router.delete("/library/follows/{target_type}/{target_id}")
def quantum_library_unfollow(target_type: str, target_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        data = request.app.state.quantum_read_model_service.unfollow_library_target(
            account_id=_quantum_identity_account_id(identity),
            actor_id=_quantum_identity_actor_id(identity) or None,
            target_type=target_type,
            target_id=target_id,
        )
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    return _success(data=data)


@router.post("/library/works/{work_id}/favorite")
def quantum_library_favorite(work_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    account_id = _quantum_identity_account_id(identity)
    try:
        request.app.state.quantum_read_model_service.favorite_library_work(account_id=account_id, work_id=work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    return _success(data={"workId": work_id, "favorited": True})


@router.delete("/library/works/{work_id}/favorite")
def quantum_library_unfavorite(work_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    account_id = _quantum_identity_account_id(identity)
    request.app.state.quantum_read_model_service.unfavorite_library_work(account_id=account_id, work_id=work_id)
    return _success(data={"workId": work_id, "favorited": False})


@router.get("/story/import/public-works")
def quantum_story_import_public_works(request: Request) -> Dict[str, Any]:
    return _success(data=_story_import_public_works_payload(request))


@router.get("/story/import/recent")
def quantum_story_import_recent(request: Request) -> Dict[str, Any]:
    identity = _maybe_identity(request)
    account_id = str((identity or {}).get("account_id") or (identity or {}).get("actor_id") or "").strip() or None
    return _success(data=_story_import_recent_payload(request, account_id=account_id))


@router.post("/story/import/start")
def quantum_story_import_start(payload: QuantumStoryImportStartRequest, request: Request) -> Any:
    target_type = str(payload.targetType or "").strip()
    target_id = str(payload.targetId or "").strip()
    if not target_type or target_type not in {"world", "session"}:
        return _error(status_code=400, message="story_import_target_type_invalid")
    if not target_id:
        return _error(status_code=400, message="story_import_target_required")

    identity = _maybe_identity(request)
    account_id = str((identity or {}).get("account_id") or (identity or {}).get("actor_id") or "").strip() or None

    if target_type == "world":
        try:
            session_payload = request.app.state.session_service.create_session(target_id, reader_id=account_id)
            bootstrap_status = "deferred"
            generation_job = None
            if not bool(payload.deferBootstrap):
                generation_job = _enqueue_reader_generation_job(
                    request,
                    operation="story_import_bootstrap",
                    session_id=session_payload["session_id"],
                    reader_id=account_id,
                    account_id=account_id,
                )
                bootstrap_status = "queued"
        except KeyError as exc:
            return _error(status_code=404, message=str(exc))
        return _success(
            data={
                "mode": "start",
                "sessionId": session_payload["session_id"],
                "worldId": session_payload["world_id"],
                "worldVersionId": session_payload["world_version_id"],
                "bootstrapStatus": bootstrap_status,
                "generationJob": _story_generation_job_payload(request, job=generation_job) if generation_job else None,
                "handoffUrl": _story_import_handoff_url(
                    request,
                    session_id=session_payload["session_id"],
                    world_id=session_payload["world_id"],
                    account_id=account_id,
                ),
            }
        )

    try:
        detail = request.app.state.repository.get_session(target_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    owner_account_id = str(detail.metadata.get("reader_id") or detail.player_profile.get("reader_id") or "").strip()
    if owner_account_id:
        if not account_id:
            return _error(status_code=401, message="auth_required")
        if owner_account_id != account_id:
            return _error(status_code=403, message="story_import_session_ownership_mismatch")
    return _success(
        data={
            "mode": "resume",
            "sessionId": detail.session_id,
            "worldId": detail.world_id,
            "worldVersionId": str(detail.metadata.get("world_version_id") or ""),
            "handoffUrl": _story_import_handoff_url(
                request,
                session_id=detail.session_id,
                world_id=detail.world_id,
                account_id=account_id,
            ),
            }
        )


@router.get("/story/session/{sessionId}")
def quantum_story_session(sessionId: str, request: Request) -> Any:
    try:
        bundle = _story_session_bundle(request, session_id=sessionId, limit=1, latest=True)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    return _success(data=_story_session_payload(bundle))


@router.get("/media/assets/{assetId}")
def quantum_private_media_asset(assetId: str, expires: int, signature: str, request: Request) -> Response:
    try:
        image_bytes, mime_type = request.app.state.illustration_service.private_asset_response(
            asset_id=assetId,
            expires=expires,
            signature=signature,
        )
    except PermissionError:
        return JSONResponse(status_code=403, content={"detail": {"code": "media_asset_signature_invalid"}})
    except KeyError as exc:
        return JSONResponse(status_code=404, content={"detail": {"code": "media_asset_missing", "reason": str(exc)}})
    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/story/session/{sessionId}/nodes")
def quantum_story_session_nodes(
    sessionId: str,
    request: Request,
    startChapter: Optional[int] = None,
    endChapter: Optional[int] = None,
    limit: Optional[int] = None,
    latest: bool = False,
) -> Any:
    try:
        bundle = _story_session_bundle(
            request,
            session_id=sessionId,
            start_chapter=startChapter,
            end_chapter=endChapter,
            limit=limit,
            latest=latest,
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    return _success(data=_story_nodes_payload(bundle))


@router.get("/story/session/{sessionId}/choices")
def quantum_story_session_choices(sessionId: str, nodeId: str, request: Request) -> Any:
    try:
        bundle = _story_session_bundle(request, session_id=sessionId, limit=1, latest=True)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    return _success(data=_story_choices_payload(bundle, node_id=str(nodeId or "").strip()))


@router.post("/story/choice")
def quantum_story_choice(payload: QuantumStoryChoiceRequest, request: Request) -> Any:
    session_id = str(payload.sessionId or "").strip()
    choice_id = str(payload.choiceId or "").strip()
    node_id = str(payload.nodeId or "").strip()
    if not session_id or not choice_id or not node_id:
        return _error(status_code=400, message="story_reader_choice_invalid")
    try:
        bundle = _story_session_bundle(request, session_id=session_id, limit=1, latest=True)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))

    choices = _story_choices_payload(bundle, node_id=node_id)
    selected_choice = next((item for item in choices if str(item.get("id") or "") == choice_id), None)
    if selected_choice is None:
        return _error(status_code=400, message="story_reader_choice_invalid")

    try:
        bundle = _story_claim_guest_session_for_viewer(request, bundle=bundle)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))

    reader_id = _story_continue_reader_id(bundle)
    access = request.app.state.billing_service.access_check(session_id, reader_id=reader_id, account_id=reader_id)
    if access.get("required"):
        return _error(
            status_code=402,
            message="story_reader_payment_required",
            data={
                "paywall": _story_paywall_payload(access),
                "continuityContract": _story_continuity_contract_payload(
                    build_reader_continuity_contract(
                        status="payment_required",
                        session_id=session_id,
                        paywall=access,
                    )
                ),
            },
        )

    try:
        story_chapters = list(bundle.get("chapter_rows") or bundle.get("steps") or [])
        latest_step = (story_chapters or [None])[-1]
        latest_reader_view = _story_get_field(latest_step, "reader_view") if latest_step else None
        latest_chapter_index = int(_story_get_field(latest_reader_view, "chapter_index", 0) or 0)
        source_chapter_id = str(_story_get_field(latest_step, "chapter_id", "") or f"chapter_{session_id}_{latest_chapter_index}")
        request.app.state.repository.save_route_choice(
            session_id=session_id,
            chapter_id=source_chapter_id,
            choice_id=choice_id,
            payload_json={
                "choice_id": choice_id,
                "node_id": node_id,
                "selected_choice": selected_choice,
                "source": "quantum_story_choice",
            },
        )
    except Exception:
        pass

    try:
        generation_job = _enqueue_reader_generation_job(
            request,
            operation="story_choice",
            session_id=session_id,
            reader_id=reader_id,
            account_id=reader_id,
            choice_id=choice_id,
            freeform_intent=str(selected_choice.get("text") or ""),
        )
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    return _success(data={"generationJob": _story_generation_job_payload(request, job=generation_job)})


@router.get("/story/generation-jobs/{jobId}")
def quantum_story_generation_job(jobId: str, request: Request) -> Any:
    try:
        job = _story_generation_job_access(request, job_id=jobId)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    return _success(data=_story_generation_job_payload(request, job=job))


@router.post("/story/generation-jobs/{jobId}/resume")
def quantum_story_generation_job_resume(jobId: str, request: Request) -> Any:
    try:
        job = _story_generation_job_access(request, job_id=jobId)
        job_status = str(job.get("status") or "")
        if job_status == "succeeded":
            return _success(data=_story_generation_job_payload(request, job=job))
        if job_status == "running" and job.get("lease_status") != "expired":
            return _success(data=_story_generation_job_payload(request, job=job))
        identity = _maybe_identity(request)
        requested_by = str((identity or {}).get("account_id") or job.get("requested_by") or "reader").strip()
        request.app.state.async_job_service.resume_job(
            jobId,
            requested_by=requested_by,
            force=job_status != "queued",
            schedule=None,
        )
        resumed = request.app.state.async_job_service.run_job(jobId)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    except ValueError as exc:
        return _error(status_code=409, message=str(exc))
    return _success(data=_story_generation_job_payload(request, job=resumed))


@router.get("/story/session/{sessionId}/deviation")
def quantum_story_session_deviation(sessionId: str, request: Request) -> Any:
    try:
        bundle = _story_session_bundle(request, session_id=sessionId, limit=1, latest=True)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    return _success(data=_story_deviation_payload(bundle))


@router.post("/story/session/{sessionId}/bookmark")
def quantum_story_session_bookmark(sessionId: str, payload: QuantumStoryBookmarkRequest, request: Request) -> Any:
    node_id = str(payload.nodeId or "").strip()
    if not node_id:
        return _error(status_code=400, message="story_reader_bookmark_invalid")
    try:
        bundle = _story_session_bundle(request, session_id=sessionId)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))

    account_id = bundle.get("owner_account_id") or bundle.get("viewer_account_id")
    if not account_id:
        return _error(status_code=401, message="auth_required")

    valid_node_ids = {str(item.get("id") or "") for item in _story_nodes_payload(bundle)}
    if node_id not in valid_node_ids:
        return _error(status_code=400, message="story_reader_bookmark_invalid")

    bookmark = request.app.state.quantum_read_model_service.bookmark_story_node(
        account_id=account_id,
        session_id=sessionId,
        node_id=node_id,
    )
    return _success(
        data=_story_bookmark_response_payload(
            request,
            session_id=sessionId,
            account_id=account_id,
            node_id=node_id,
            saved=True,
            bookmark_id=bookmark["bookmark_id"],
        )
    )


@router.delete("/story/session/{sessionId}/bookmark")
def quantum_story_session_unbookmark(sessionId: str, nodeId: str, request: Request) -> Any:
    node_id = str(nodeId or "").strip()
    if not node_id:
        return _error(status_code=400, message="story_reader_bookmark_invalid")
    try:
        bundle = _story_session_bundle(request, session_id=sessionId)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))

    account_id = bundle.get("owner_account_id") or bundle.get("viewer_account_id")
    if not account_id:
        return _error(status_code=401, message="auth_required")

    valid_node_ids = {str(item.get("id") or "") for item in _story_nodes_payload(bundle)}
    if node_id not in valid_node_ids:
        return _error(status_code=400, message="story_reader_bookmark_invalid")

    bookmark = request.app.state.quantum_read_model_service.unbookmark_story_node(
        account_id=account_id,
        session_id=sessionId,
        node_id=node_id,
    )
    return _success(
        data=_story_bookmark_response_payload(
            request,
            session_id=sessionId,
            account_id=account_id,
            node_id=node_id,
            saved=False,
            bookmark_id=bookmark.get("bookmark_id"),
        )
    )


@router.post("/story/session/{sessionId}/share")
def quantum_story_session_share(sessionId: str, request: Request) -> Any:
    try:
        bundle = _story_session_bundle(request, session_id=sessionId)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except PermissionError as exc:
        status_code = 401 if str(exc) == "auth_required" else 403
        return _error(status_code=status_code, message=str(exc))
    account_id = bundle.get("owner_account_id")
    identity = bundle.get("identity")
    if not account_id or identity is None:
        return _error(status_code=401, message="auth_required")
    current_node_id = str(_story_session_payload(bundle).get("currentNodeId") or "")
    share_row = request.app.state.repository.save_story_session_share_token(
        {
            "session_id": sessionId,
            "account_id": account_id,
            "node_id": current_node_id,
            "sharer_name": str(identity.get("display_name") or identity.get("actor_id") or account_id),
            "status": "active",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=QUANTUM_STORY_SHARE_TTL_DAYS)).isoformat(),
        }
    )
    request.app.state.analytics_service.track(
        "story_share_created",
        reader_id=account_id,
        account_id=account_id,
        session_id=sessionId,
        world_id=bundle.get("session", {}).get("world_id"),
        world_version_id=bundle.get("world_version_id"),
        payload_json={
            "share_token": share_row["share_token"],
            "node_id": current_node_id,
        },
    )
    return _success(
        data={
            "shareToken": share_row["share_token"],
            "shareUrl": _story_share_url(str(share_row["share_token"])),
            "expiresAt": share_row.get("expires_at"),
            "status": share_row.get("status", "active"),
        }
    )


@router.delete("/story/share/{shareToken}")
def quantum_story_revoke_public_share(shareToken: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        share_row = request.app.state.repository.get_story_session_share_token(shareToken)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    actor_account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    if actor_account_id != str(share_row.get("account_id") or "").strip():
        return _error(status_code=403, message="story_share_token_ownership_mismatch")
    revoked = request.app.state.repository.revoke_story_session_share_token(shareToken)
    try:
        session = request.app.state.repository.get_session(str(revoked.get("session_id") or ""))
        world_id = session.world_id
        world_version_id = session.metadata.get("world_version_id")
    except KeyError:
        world_id = None
        world_version_id = None
    request.app.state.analytics_service.track(
        "story_share_revoked",
        reader_id=actor_account_id,
        account_id=actor_account_id,
        session_id=revoked.get("session_id"),
        world_id=world_id,
        world_version_id=world_version_id,
        payload_json={
            "share_token": revoked["share_token"],
            "node_id": revoked.get("node_id"),
        },
    )
    return _success(
        data={
            "shareToken": revoked["share_token"],
            "shareUrl": _story_share_url(str(revoked["share_token"])),
            "expiresAt": revoked.get("expires_at"),
            "status": revoked.get("status", "revoked"),
            "revokedAt": revoked.get("revoked_at"),
        }
    )


@router.get("/story/share/{shareToken}")
def quantum_story_public_share(shareToken: str, request: Request) -> Any:
    try:
        share_row = request.app.state.repository.get_story_session_share_token(shareToken)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    inactive_reason = _story_share_token_inactive_reason(share_row)
    if inactive_reason:
        return _error(
            status_code=410,
            message="story_share_token_inactive",
            data={"reason": inactive_reason},
        )
    bundle = _story_public_share_bundle(request, share_token=shareToken)
    return _success(data=_story_share_payload(bundle, share_token_row=share_row))


@router.get("/showcase/works")
def quantum_showcase_works(request: Request, sort: str = "hot", page: int = 1, pageSize: int = 20) -> Dict[str, Any]:
    viewer_account_id = _showcase_viewer_account_id(request)
    items = _showcase_works_payload(request, sort_value=sort, page=page, page_size=pageSize)
    viewer_key = request.app.state.quantum_read_model_service.showcase_viewer_key(
        viewer_account_id=viewer_account_id,
        request_headers=dict(request.headers),
        remote_host=(request.client.host if request.client else None),
    )
    for item in items:
        try:
            version = _resolve_showcase_version(request, str(item.get("id") or ""))
        except KeyError:
            continue
        request.app.state.quantum_read_model_service.track_showcase_view(
            world_id=str(version.world_id or ""),
            world_version_id=version.world_version_id,
            viewer_key=viewer_key,
            account_id=viewer_account_id,
            event_type="impression",
        )
    refreshed = _showcase_works_payload(request, sort_value=sort, page=page, page_size=pageSize)
    return _success(data=refreshed)


@router.get("/showcase/works/{work_id}")
def quantum_showcase_work_detail(work_id: str, request: Request) -> Any:
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    world_id = str(version.world_id or "").strip()
    viewer_account_id = _showcase_viewer_account_id(request)
    viewer_key = request.app.state.quantum_read_model_service.showcase_viewer_key(
        viewer_account_id=viewer_account_id,
        request_headers=dict(request.headers),
        remote_host=(request.client.host if request.client else None),
    )
    request.app.state.quantum_read_model_service.track_showcase_view(
        world_id=world_id,
        world_version_id=version.world_version_id,
        viewer_key=viewer_key,
        account_id=viewer_account_id,
        event_type="view",
    )
    interaction_maps = _showcase_interaction_maps(request, world_ids=[world_id], viewer_account_id=viewer_account_id)
    return _success(
        data=request.app.state.quantum_read_model_service.showcase_item_from_version(
            version_summary={
                "world_version_id": version.world_version_id,
                "world_id": world_id,
                "updated_at": getattr(version, "updated_at", None) or "",
            },
            hot_rank=None,
            interaction_maps=interaction_maps,
            viewer_account_id=viewer_account_id,
        )
    )


@router.get("/showcase/works/{work_id}/comments")
def quantum_showcase_work_comments(work_id: str, request: Request, page: int = 1, pageSize: int = 20) -> Any:
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    viewer_account_id = _showcase_viewer_account_id(request)
    viewer_key = request.app.state.quantum_read_model_service.showcase_viewer_key(
        viewer_account_id=viewer_account_id,
        request_headers=dict(request.headers),
        remote_host=(request.client.host if request.client else None),
    )
    request.app.state.quantum_read_model_service.track_showcase_view(
        world_id=str(version.world_id or ""),
        world_version_id=version.world_version_id,
        viewer_key=viewer_key,
        account_id=viewer_account_id,
        event_type="view",
    )
    page_index = max(1, int(page or 1))
    per_page = max(1, min(100, int(pageSize or 20)))
    comments = request.app.state.repository.list_showcase_work_comments(
        world_id=version.world_id,
        status="published",
        limit=per_page,
        offset=(page_index - 1) * per_page,
    )
    return _success(data=[_showcase_comment_payload(item) for item in comments])


@router.post("/showcase/works/{work_id}/like")
def quantum_showcase_like(work_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    request.app.state.repository.save_showcase_work_like(
        {
            "world_id": version.world_id,
            "world_version_id": version.world_version_id,
            "account_id": account_id,
            "actor_id": identity.get("actor_id"),
        }
    )
    request.app.state.analytics_service.track(
        "showcase_work_liked",
        reader_id=account_id,
        account_id=account_id,
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        payload_json={"work_id": work_id},
    )
    like_count = request.app.state.repository.showcase_work_like_counts(world_ids=[version.world_id]).get(version.world_id, 0)
    return _success(data={"likeCount": int(like_count), "viewerHasLiked": True})


@router.delete("/showcase/works/{work_id}/like")
def quantum_showcase_unlike(work_id: str, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    request.app.state.repository.delete_showcase_work_like(world_id=version.world_id, account_id=account_id)
    request.app.state.analytics_service.track(
        "showcase_work_unliked",
        reader_id=account_id,
        account_id=account_id,
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        payload_json={"work_id": work_id},
    )
    like_count = request.app.state.repository.showcase_work_like_counts(world_ids=[version.world_id]).get(version.world_id, 0)
    return _success(data={"likeCount": int(like_count), "viewerHasLiked": False})


@router.post("/showcase/works/{work_id}/comments")
def quantum_showcase_post_comment(work_id: str, payload: QuantumShowcaseCommentRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    content = str(payload.content or "").strip()
    if not content:
        return _error(status_code=400, message="showcase_comment_required")
    if len(content) > 500:
        return _error(status_code=400, message="showcase_comment_too_long")
    author_name = str(identity.get("display_name") or identity.get("actor_id") or "用户").strip() or "用户"
    comment = request.app.state.repository.save_showcase_work_comment(
        {
            "world_id": version.world_id,
            "world_version_id": version.world_version_id,
            "account_id": str(identity.get("account_id") or identity.get("actor_id") or "").strip(),
            "actor_id": identity.get("actor_id"),
            "author_name": author_name,
            "content": content,
            "status": "published",
        }
    )
    request.app.state.analytics_service.track(
        "showcase_work_commented",
        reader_id=str(identity.get("account_id") or identity.get("actor_id") or "").strip(),
        account_id=str(identity.get("account_id") or identity.get("actor_id") or "").strip(),
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        payload_json={"work_id": work_id, "comment_id": comment.get("showcase_comment_id")},
    )
    return _success(data=_showcase_comment_payload(comment))


@router.post("/showcase/works/{work_id}/tip")
def quantum_showcase_tip(work_id: str, payload: QuantumShowcaseTipRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        version = _resolve_showcase_version(request, work_id)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "showcase_work_missing")
    amount = int(payload.amount or 0)
    if amount < 1:
        return _error(status_code=400, message="showcase_tip_amount_invalid")
    account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    current_balance = float(request.app.state.billing_service.wallet_balance(account_id=account_id, wallet_type="story_credits"))
    if current_balance < amount:
        return _error(status_code=402, message="insufficient_story_credits")
    updated_wallet = request.app.state.billing_service.debit_wallet_credits(account_id=account_id, wallet_type="story_credits", amount=float(amount))
    balance_after = float(updated_wallet.get("balance") or 0.0)
    tip = request.app.state.repository.save_showcase_work_tip(
        {
            "world_id": version.world_id,
            "world_version_id": version.world_version_id,
            "account_id": account_id,
            "actor_id": identity.get("actor_id"),
            "amount": amount,
            "wallet_type": "story_credits",
            "balance_after": balance_after,
        }
    )
    billing_snapshot = request.app.state.billing_service.subscription_status(account_id=account_id)
    access_tier = billing_snapshot.get("effective_tier") or ((billing_snapshot.get("subscription") or {}).get("tier_id"))
    analytics_payload = {
        "world_id": version.world_id,
        "world_version_id": version.world_version_id,
        "amount": amount,
        "wallet_type": "story_credits",
        "balance": balance_after,
    }
    request.app.state.analytics_service.track(
        "showcase_tip_sent",
        reader_id=account_id,
        account_id=account_id,
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        access_tier=access_tier,
        payload_json=analytics_payload,
    )
    request.app.state.analytics_service.track(
        "story_credits_consumed",
        reader_id=account_id,
        account_id=account_id,
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        access_tier=access_tier,
        payload_json=analytics_payload,
    )
    request.app.state.analytics_service.track(
        "credits_consumed",
        reader_id=account_id,
        account_id=account_id,
        world_id=version.world_id,
        world_version_id=version.world_version_id,
        access_tier=access_tier,
        payload_json=analytics_payload,
    )
    return _success(data={"tipId": tip["showcase_tip_id"], "amount": amount, "balanceAfter": balance_after})


@router.post("/settings/membership/subscribe")
def quantum_membership_subscribe(payload: QuantumMembershipSubscribeRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        return _success(data=_start_membership_checkout(request, identity=identity, raw_plan_id=payload.planId))
    except ValueError as exc:
        return _quantum_checkout_error(exc)


@router.post("/settings/ink/purchase")
def quantum_ink_purchase(payload: QuantumInkPurchaseRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        return _success(data=_start_ink_checkout(request, identity=identity, raw_package_id=payload.packageId))
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        return _error(status_code=status_code, message=reason)


@router.post("/settings/ink/{checkout_session_id}/complete")
def quantum_complete_ink_checkout(
    checkout_session_id: str,
    request: Request,
    payload: Optional[QuantumInkCheckoutCompleteRequest] = None,
) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    account_id = str((payload.accountId if payload else None) or identity.get("account_id") or identity.get("actor_id") or "").strip()
    try:
        completed = request.app.state.billing_service.complete_checkout_session(
            checkout_session_id=checkout_session_id,
            account_id=account_id,
        )
    except PermissionError as exc:
        return _error(status_code=403, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc))
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        return _error(status_code=status_code, message=reason)
    wallet = dict(completed.get("wallet") or {})
    processed_event = dict(completed.get("processed_event") or {})
    request.app.state.analytics_service.track(
        "story_credits_purchased",
        reader_id=account_id,
        account_id=account_id,
        access_tier="story_credits",
        payload_json={
            "checkout_session_id": checkout_session_id,
            "package_id": processed_event.get("processing_result", {}).get("package_id"),
            "granted_units": processed_event.get("processing_result", {}).get("granted_units"),
            "wallet_balance": wallet.get("balance"),
            "provider": (completed.get("checkout") or {}).get("provider"),
        },
    )
    return _success(
        data={
            "checkoutSessionId": checkout_session_id,
            "status": str((completed.get("checkout") or {}).get("status") or ""),
            "packageId": processed_event.get("processing_result", {}).get("package_id"),
            "grantedUnits": processed_event.get("processing_result", {}).get("granted_units"),
            "walletBalance": wallet.get("balance"),
        }
    )


@router.post("/settings/account/password-change")
def quantum_change_account_password(payload: QuantumSettingsAccountPasswordChangeRequest, request: Request, response: Response) -> Any:
    try:
        identity = _require_identity(request)
        token_result = request.app.state.auth_service.change_password(
            actor_id=str(identity.get("actor_id") or ""),
            current_password=payload.currentPassword,
            new_password=payload.newPassword,
        )
        response.set_cookie(
            value=token_result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return _success(
            data=_frontend_auth_response(
                request,
                identity=token_result["identity"],
                access_token=token_result["token"]["access_token"],
                refresh_token=(token_result.get("refresh") or {}).get("refresh_token"),
            )
        )
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.get("/settings/account/export")
def quantum_export_account(request: Request, format: str = "json") -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    if str(format or "").strip().lower() != "json":
        return _error(status_code=400, message="unsupported_export_format")
    return _success(data=_auth_export_payload(request, identity=identity))


@router.post("/settings/account/email-change/request")
def quantum_request_email_change(payload: QuantumSettingsAccountEmailChangeRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
        result = request.app.state.auth_service.request_email_change(
            actor_id=str(identity.get("actor_id") or ""),
            current_password=payload.currentPassword,
            new_email=payload.newEmail,
        )
        return _success(
            data={
                "status": result.get("status"),
                "pendingEmail": result.get("pending_email_address"),
                "delivery": result.get("delivery"),
            }
        )
    except AuthServiceError as exc:
        detail = exc.detail()
        return _error(status_code=exc.http_status, message=str(detail.get("reason") or detail.get("code") or "auth_error"), data=detail)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        reason = str(exc)
        status_code = 409 if reason in {"email_change_email_already_in_use", "email_change_email_pending_elsewhere"} else 400
        return _error(status_code=status_code, message=reason)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.post("/settings/account/email-change/confirm")
def quantum_confirm_email_change(payload: QuantumSettingsAccountEmailConfirmRequest, request: Request) -> Any:
    try:
        result = request.app.state.auth_service.confirm_email_change(token=payload.token)
        return _success(
            data={
                "status": result.get("status"),
                "identity": _frontend_user(request, result.get("identity") or {}),
            }
        )
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        reason = str(exc)
        status_code = 409 if reason == "email_change_email_already_in_use" else 400
        return _error(status_code=status_code, message=reason)
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.post("/settings/account/deactivate")
def quantum_deactivate_account(request: Request, response: Response) -> Any:
    try:
        identity = _require_identity(request)
        result = request.app.state.auth_service.deactivate_account(
            actor_id=str(identity.get("actor_id") or ""),
            requested_by=str(identity.get("actor_id") or ""),
        )
        response.delete_cookie(
            key=request.app.state.auth_service.auth_cookie_settings()["key"],
            path="/",
            domain=request.app.state.auth_service.auth_cookie_settings().get("domain"),
        )
        return _success(data={"status": result.get("status"), "revokedSessionCount": len(result.get("revoked_sessions") or [])})
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
    except KeyError as exc:
        return _error(status_code=404, message=str(exc) or "auth_identity_missing")


@router.post("/payments/subscription-session")
def quantum_legacy_subscription_session(payload: QuantumLegacySubscriptionSessionRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        return _start_membership_checkout(request, identity=identity, raw_plan_id=payload.tierId)
    except ValueError as exc:
        return _quantum_checkout_error(exc)


@router.post("/payments/checkout-session")
def quantum_legacy_checkout_session(payload: QuantumLegacyCheckoutSessionRequest, request: Request) -> Any:
    try:
        identity = _require_identity(request)
    except PermissionError as exc:
        return _error(status_code=401, message=str(exc))
    try:
        return _start_ink_checkout(request, identity=identity, raw_package_id=payload.packageId)
    except ValueError as exc:
        return _error(status_code=400, message=str(exc))
