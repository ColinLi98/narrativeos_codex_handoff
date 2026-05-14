from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from ..benchmark.runner import run_benchmark
from ..persistence.migrations import inspect_schema_lifecycle
from ..eval.learned_assisted_gate import (
    build_assisted_gate_summary,
    save_assisted_gate_config,
)
from ..eval.learned_assisted_rerank import (
    build_assisted_rerank_summary,
    save_assisted_rerank_config,
)
from ..eval.learned_compare import build_learned_compare_summary
from ..eval.learned_cadence import (
    build_learned_cadence_summary,
    build_learned_cadence_track_detail,
)
from ..eval.learned_data_impact import build_learned_data_impact_receipt
from ..eval.learned_data_ops import build_learned_data_ops_summary
from ..eval.learned_dashboard import build_learned_dashboard_summary
from ..eval.learned_impact import (
    build_learned_impact_issue_detail,
    build_learned_impact_summary,
    build_learned_impact_world_detail,
)
from ..eval.learned_rollout import (
    activate_learned_rollout,
    build_learned_rollout_summary,
    rollback_learned_rollout,
)
from ..eval.learned_training_automation import (
    build_promotion_evidence_pack,
    run_learned_training_automation,
)
from ..eval.learned_promotion_workflow import (
    build_evaluator_promotion_workflow_summary,
    save_evaluator_promotion_decision,
)
from ..eval.learned_reranker_promotion_workflow import (
    build_reranker_promotion_workflow_summary,
    save_reranker_promotion_decision,
)
from ..eval.learned_review_quality import (
    build_learned_review_quality_summary,
    build_learned_review_quality_world_detail,
)
from ..services.provider_rollout import ProviderRolloutService
from ..services.ops_permissions import OpsPermissionPolicyService

class PublishRequest(BaseModel):
    reviewer_id: Optional[str] = None


class RollbackRequest(BaseModel):
    target_world_version_id: str
    reviewer_id: Optional[str] = None


class ReviewSampleRequest(BaseModel):
    sample_id: Optional[str] = None
    chapter_id: str
    world_id: str
    world_version_id: str
    session_id: Optional[str] = None
    reviewer_id: str
    score_overall: float
    issue_codes: list[str]
    freeform_notes: str
    would_continue: bool
    would_pay: bool
    created_at: Optional[str] = None
    source: str = "human_review"
    revision_id: Optional[str] = None
    linked_issue_codes: Optional[list[str]] = None
    source_ref: Optional[Dict[str, Any]] = None


class PreferenceSampleRequest(BaseModel):
    preference_id: Optional[str] = None
    world_id: str
    world_version_id: str
    chapter_id: Optional[str] = None
    session_id: Optional[str] = None
    reviewer_id: str
    left_revision_id: str
    right_revision_id: str
    preferred_revision_id: str
    freeform_notes: str
    linked_issue_codes: Optional[list[str]] = None
    preference_strength: str = "medium"
    created_at: Optional[str] = None
    source: str = "human_preference"


class RankingSampleRequest(BaseModel):
    ranking_id: Optional[str] = None
    world_id: str
    world_version_id: str
    chapter_id: Optional[str] = None
    session_id: Optional[str] = None
    reviewer_id: str
    ranked_revision_ids: list[str]
    freeform_notes: str
    linked_issue_codes: Optional[list[str]] = None
    created_at: Optional[str] = None
    source: str = "human_ranking"


class LearnedPromotionDecisionRequest(BaseModel):
    reviewer_id: str
    reason: str


class LearnedAssistedGateConfigRequest(BaseModel):
    reviewer_id: str
    reason: str
    enabled: bool = False
    mode: str = "shadow_only"
    bucket_percentage: int = 0
    confidence_threshold: float = 0.9
    min_example_count: int = 3
    min_high_confidence_blocks: int = 2
    required_block_share: float = 0.5
    world_allowlist: list[str] = []


class LearnedAssistedRerankConfigRequest(BaseModel):
    reviewer_id: str
    reason: str
    enabled: bool = False
    mode: str = "shadow_only"
    bucket_percentage: int = 0
    confidence_threshold: float = 0.65
    candidate_window: int = 3
    max_score_gap: float = 0.08
    world_allowlist: list[str] = []


class ProviderRolloutDecisionRequest(BaseModel):
    reviewer_id: str
    reason: str
    bucket_percentage: int = 0
    world_allowlist: list[str] = []


class DataIntegrityRepairRequest(BaseModel):
    apply: bool = False
    actions: list[str] = []
    limit: int = 20


class SubscriptionGrantRequest(BaseModel):
    account_id: str
    tier_id: str
    provider: str = "ops_manual"
    status: str = "active"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    cancel_at_period_end: bool = False


class SubscriptionStateRequest(BaseModel):
    subscription_id: str
    status: str
    cancel_at_period_end: Optional[bool] = None


class WalletGrantRequest(BaseModel):
    account_id: str
    wallet_type: str
    amount: float
    tier_id: Optional[str] = None
    expires_at: Optional[str] = None
    reason: str = "manual_wallet_grant"


class WalletDebitRequest(BaseModel):
    account_id: str
    wallet_type: str
    amount: float
    reason: str = "manual_wallet_debit"


class EntitlementRevokeRequest(BaseModel):
    entitlement_id: str
    reason: str = "manual_entitlement_revoke"


class BillingLifecycleReplayRequest(BaseModel):
    requested_by: Optional[str] = None


class BillingRetryRequest(BaseModel):
    requested_by: Optional[str] = None


class AccountBillingReconcileRequest(BaseModel):
    requested_by: Optional[str] = None
    provider: Optional[str] = None


class BillableEventStatusRequest(BaseModel):
    status: str


class CampaignDecisionRequest(BaseModel):
    decision: str
    note: Optional[str] = None


class PartnerStatusRequest(BaseModel):
    status: str
    note: Optional[str] = None


class ProductionSignoffInitializeRequest(BaseModel):
    launch_label: Optional[str] = None
    due_in_days: int = 2


class ProductionSignoffAssignRequest(BaseModel):
    owner_actor_id: Optional[str] = None


class ProductionSignoffDecisionRequest(BaseModel):
    decision: str
    note: Optional[str] = None


class ProductionSignoffEvidenceRequest(BaseModel):
    evidence_type: str
    summary: Optional[str] = None
    source_ref: Dict[str, Any] = {}
    payload: Dict[str, Any] = {}
    customer_safe: bool = False


class ProductionSignoffOperatorEvidenceRequest(BaseModel):
    evidence_key: str
    summary: str
    source_ref: Dict[str, Any] = {}
    payload: Dict[str, Any] = {}


class ProductionSignoffOperatorCloseRequest(BaseModel):
    decision: str
    note: Optional[str] = None


class ProductionCutoverWindowRequest(BaseModel):
    launch_wave: str
    target_environment: str
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    rollback_owner_role: Optional[str] = None
    status: str = "planned"
    payload: Dict[str, Any] = {}


class ProductionAcceptanceGenerateRequest(BaseModel):
    account_id: str
    launch_wave: str = "wave_1"
    signoff_id: Optional[str] = None


class LaunchWaveStatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


class ProductionPreflightRunRequest(BaseModel):
    signoff_id: Optional[str] = None
    launch_wave: str = "wave_1"
    target_environment: str = "production"


class CustomerSuccessSyncRequest(BaseModel):
    account_id: Optional[str] = None
    launch_wave: Optional[str] = None


class LaunchLedgerSyncRequest(BaseModel):
    launch_wave: str = "wave_1"


class WaveActivationRequest(BaseModel):
    note: Optional[str] = None


class GoLiveDayRunRequest(BaseModel):
    launch_wave: str = "wave_1"
    signoff_id: Optional[str] = None
    account_id: Optional[str] = None


class LaunchWeekGuardSyncRequest(BaseModel):
    launch_wave: str = "wave_1"


class DisputeDecisionRequest(BaseModel):
    decision: str
    note: Optional[str] = None


class ManualAdjustmentRequest(BaseModel):
    account_id: str
    dispute_id: Optional[str] = None
    refund_request_id: Optional[str] = None
    invoice_preview_id: Optional[str] = None
    billable_event_id: Optional[str] = None
    adjustment_type: str
    amount_usd: float
    target_billable_status: Optional[str] = None
    adjustment_payload: Dict[str, Any] = {}


class SupportCaseStatusRequest(BaseModel):
    status: str
    note: Optional[str] = None


class InvoiceIssueRequest(BaseModel):
    requested_by: Optional[str] = None


class InvoiceRetryRequest(BaseModel):
    requested_by: Optional[str] = None


class LifecycleAutomationSyncRequest(BaseModel):
    account_id: str


class InvestigationRequest(BaseModel):
    limit: int = 50


class AlertStatusRequest(BaseModel):
    account_id: Optional[str] = None
    status: str
    reviewer_id: Optional[str] = None
    note: Optional[str] = None


class OpsReviewItemAssignRequest(BaseModel):
    owner_id: str
    reviewer_id: Optional[str] = None


class OpsReviewItemStatusRequest(BaseModel):
    status: str
    reviewer_id: Optional[str] = None


class OpsReviewItemDecisionRequest(BaseModel):
    decision: str
    reviewer_id: Optional[str] = None


class GovernanceCaseRequest(BaseModel):
    case_type: str
    target_type: str
    target_id: str
    account_id: Optional[str] = None
    world_id: Optional[str] = None
    world_version_id: Optional[str] = None
    session_id: Optional[str] = None
    entitlement_id: Optional[str] = None
    severity: str = "medium"
    summary: str
    description: Optional[str] = None
    source: str = "ops_manual"
    reviewer_id: Optional[str] = None
    owner_id: Optional[str] = None
    due_at: Optional[str] = None
    disposition: Optional[str] = None
    policy_labels: list[str] = []
    evidence_refs: list[Dict[str, Any]] = []
    resolution_notes: Optional[str] = None
    support_issue_ids: list[str] = []


class GovernanceCaseStatusRequest(BaseModel):
    status: str
    reviewer_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    disposition: Optional[str] = None


class GovernanceCaseAssignRequest(BaseModel):
    owner_id: str
    reviewer_id: Optional[str] = None
    due_at: Optional[str] = None
    note: Optional[str] = None


class GovernanceCaseEvidenceRequest(BaseModel):
    reviewer_id: Optional[str] = None
    title: str
    preview: str
    ref_id: Optional[str] = None
    kind: str = "note"


class GovernanceRestrictionRequest(BaseModel):
    restriction_type: str
    account_id: str
    case_type: str = "abuse"
    severity: str = "high"
    summary: str
    description: Optional[str] = None
    reviewer_id: Optional[str] = None
    expires_at: Optional[str] = None
    restriction_reason: Optional[str] = None
    support_issue_ids: list[str] = []


class GovernanceRestrictionReleaseRequest(BaseModel):
    reviewer_id: Optional[str] = None
    release_reason: Optional[str] = None


class GovernanceRestrictionUpdateRequest(BaseModel):
    reviewer_id: Optional[str] = None
    restriction_type: Optional[str] = None
    restriction_reason: Optional[str] = None
    expires_at: Optional[str] = None


class GovernanceCaseRestrictionRequest(BaseModel):
    reviewer_id: Optional[str] = None
    restriction_type: str
    restriction_reason: Optional[str] = None
    expires_at: Optional[str] = None


class GovernanceBulkActionRequest(BaseModel):
    case_ids: list[str]
    action: str
    owner_id: Optional[str] = None
    owner_assignments: Dict[str, str] = {}
    due_at: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None
    resolution_notes: Optional[str] = None
    disposition: Optional[str] = None
    policy_labels: list[str] = []
    restriction_type: Optional[str] = None
    restriction_reason: Optional[str] = None
    expires_at: Optional[str] = None
    reviewer_id: Optional[str] = None


class GovernanceCapacityOverrideRequest(BaseModel):
    reviewer_id: Optional[str] = None
    capacity_units_per_day: Optional[float] = None
    critical_case_limit: Optional[int] = None
    active_restriction_limit: Optional[int] = None
    sla_hours: Optional[int] = None
    role_multiplier: Optional[float] = None
    enabled: Optional[bool] = None
    clear_override: bool = False
    note: Optional[str] = None


class GovernanceSupportEscalationRequest(BaseModel):
    issue_id: str
    reviewer_id: Optional[str] = None
    case_type: Optional[str] = None
    severity: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None


class LearnedTrainingRunRequest(BaseModel):
    tracks: list[str] = ["evaluator", "reranker"]
    world_id: Optional[str] = None
    world_version_id: Optional[str] = None
    limit: Optional[int] = None


class RuntimeBackupRequest(BaseModel):
    label: Optional[str] = None
    output_dir: Optional[str] = None
    dry_run: bool = False


class RuntimeRestoreRequest(BaseModel):
    backup_path: str
    dry_run: bool = False


class RuntimeRestoreCreateRequest(BaseModel):
    backup_path: str
    reason: str


class RuntimeRestoreApproveRequest(BaseModel):
    reason: str


class RuntimeRestoreRevokeRequest(BaseModel):
    reason: str


class RuntimeRecoveryDrillRequest(BaseModel):
    backup_path: Optional[str] = None
    output_dir: Optional[str] = None


class AsyncRuntimeRestoreJobRequest(BaseModel):
    request_id: str
    account_id: Optional[str] = None


class AsyncLearnedTrainingJobRequest(BaseModel):
    tracks: list[str] = ["evaluator", "reranker"]
    world_id: Optional[str] = None
    world_version_id: Optional[str] = None
    limit: Optional[int] = None
    requested_by: Optional[str] = None


class AsyncRuntimeBackupJobRequest(BaseModel):
    label: Optional[str] = None
    output_dir: Optional[str] = None
    dry_run: bool = False
    requested_by: Optional[str] = None
    account_id: Optional[str] = None


class AsyncJobActionRequest(BaseModel):
    requested_by: Optional[str] = None
    force: bool = False
    stale_after_minutes: int = 15


class AsyncJobRecoveryRequest(BaseModel):
    requested_by: Optional[str] = None
    stale_after_minutes: int = 15
    limit: int = 10


class AsyncJobRetentionCleanupRequest(BaseModel):
    requested_by: Optional[str] = None
    dry_run: bool = False
    limit: int = 20


class AsyncJobColdStartDrillRequest(BaseModel):
    requested_by: Optional[str] = None
    stale_after_minutes: int = 15
    limit: int = 20


class AsyncJobHandoffExportRequest(BaseModel):
    requested_by: Optional[str] = None
    limit: int = 20
    output_dir: Optional[str] = None
    sink_name: Optional[str] = None
    dry_run_notification: bool = False


class AsyncJobAcknowledgeRequest(BaseModel):
    requested_by: Optional[str] = None
    note: Optional[str] = None


class AsyncNotificationRetryEnqueueRequest(BaseModel):
    event_id: int
    requested_by: Optional[str] = None
    note: Optional[str] = None


class AsyncNotificationRetryProcessRequest(BaseModel):
    requested_by: Optional[str] = None
    sink_name: Optional[str] = None
    dry_run: bool = False


class AsyncJobRemoteShippingRequest(BaseModel):
    requested_by: Optional[str] = None
    adapter_name: Optional[str] = None
    remote_dir: Optional[str] = None
    dry_run: bool = False


class AsyncJobHandoffSlaRequest(BaseModel):
    requested_by: Optional[str] = None
    sla_minutes: int = 240
    limit: int = 20
    dry_run: bool = False
    sink_name: Optional[str] = None


router = APIRouter(prefix="/v1/ops", tags=["ops"])
logger = logging.getLogger(__name__)
ACTOR_ID_HEADER = "X-NarrativeOS-Actor-Id"
ACTOR_ROLE_HEADER = "X-NarrativeOS-Actor-Role"
ACCOUNT_ID_HEADER = "X-NarrativeOS-Account-Id"
ADMIN_VIEW_BRIDGE_HEADER = "X-NarrativeOS-Admin-Bridge"


def _ops_request_identity(request: Request) -> Dict[str, Optional[str]]:
    bridge_token = request.headers.get(ADMIN_VIEW_BRIDGE_HEADER) or ""
    if bridge_token.strip():
        try:
            resolved = request.app.state.auth_service.resolve_admin_view_bridge_token(raw_token=bridge_token.strip())
        except (PermissionError, KeyError) as exc:
            raise HTTPException(status_code=401, detail={"code": "admin_view_bridge_invalid", "reason": str(exc)}) from exc
        return {
            "actor_id": resolved.get("actor_id"),
            "actor_role": resolved.get("actor_role"),
            "account_id": resolved.get("account_id") or resolved.get("context", {}).get("account_id"),
        }
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        raw_token = request.app.state.auth_service.extract_request_token(
            authorization=authorization,
            cookies=None,
        )
        try:
            resolved = request.app.state.auth_service.resolve_bearer_token(raw_token or "")
        except (PermissionError, KeyError) as exc:
            raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
        return {
            "actor_id": resolved.get("actor_id"),
            "actor_role": resolved.get("actor_role"),
            "account_id": resolved.get("account_id"),
        }
    actor_id = request.headers.get(ACTOR_ID_HEADER)
    actor_role = request.headers.get(ACTOR_ROLE_HEADER)
    account_id = request.headers.get(ACCOUNT_ID_HEADER)
    if actor_id or actor_role or account_id:
        return {
            "actor_id": actor_id.strip() if actor_id else None,
            "actor_role": actor_role.strip() if actor_role else None,
            "account_id": account_id.strip() if account_id else None,
        }
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=None,
        cookies=request.cookies,
    )
    if raw_token:
        try:
            resolved = request.app.state.auth_service.resolve_bearer_token(raw_token)
        except (PermissionError, KeyError) as exc:
            raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
        return {
            "actor_id": resolved.get("actor_id"),
            "actor_role": resolved.get("actor_role"),
            "account_id": resolved.get("account_id"),
        }
    return {
        "actor_id": actor_id.strip() if actor_id else None,
        "actor_role": actor_role.strip() if actor_role else None,
        "account_id": account_id.strip() if account_id else None,
    }


def _apply_ops_identity(
    request: Request,
    payload: Dict[str, Any],
    *,
    reviewer_field: str = "reviewer_id",
) -> Dict[str, Any]:
    resolved = dict(payload)
    identity = _ops_request_identity(request)
    if identity["actor_id"]:
        resolved[reviewer_field] = identity["actor_id"]
    return resolved


def _ops_actor(request: Request, fallback_reviewer_id: Optional[str] = None) -> Dict[str, Optional[str]]:
    identity = _ops_request_identity(request)
    actor_id = identity["actor_id"] or fallback_reviewer_id
    actor_role = identity["actor_role"] or ("reviewer" if actor_id else None)
    return {
        "actor_id": actor_id,
        "actor_role": actor_role,
        "account_id": identity["account_id"],
    }


def _require_ops_reviewer(request: Request, fallback_reviewer_id: Optional[str] = None) -> Dict[str, Optional[str]]:
    actor = _ops_actor(request, fallback_reviewer_id)
    try:
        request.app.state.ops_permission_policy.authorize_roles(
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            allowed_roles={"reviewer", "ops", "admin"},
            missing_reason="reviewer_identity_required",
            forbidden_reason="reviewer_or_ops_required",
        )
    except PermissionError as exc:
        reason = str(exc)
        code = "ops_actor_missing" if "identity_required" in reason else "ops_actor_forbidden"
        raise HTTPException(status_code=403, detail={"code": code, "reason": reason}) from exc
    return actor


def _require_ops_roles(
    request: Request,
    *,
    allowed_roles: set[str],
    fallback_actor_id: Optional[str] = None,
    missing_reason: str = "ops_identity_required",
    forbidden_reason: str = "ops_role_forbidden",
) -> Dict[str, Optional[str]]:
    actor = _ops_actor(request, fallback_actor_id)
    try:
        request.app.state.ops_permission_policy.authorize_roles(
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            allowed_roles=allowed_roles,
            missing_reason=missing_reason,
            forbidden_reason=forbidden_reason,
        )
    except PermissionError as exc:
        reason = str(exc)
        code = "ops_actor_missing" if "identity_required" in reason else "ops_actor_forbidden"
        raise HTTPException(status_code=403, detail={"code": code, "reason": reason}) from exc
    return actor


def _require_restore_requester(request: Request) -> Dict[str, Optional[str]]:
    return _require_ops_roles(
        request,
        allowed_roles={"reviewer", "ops", "admin"},
        missing_reason="restore_requester_identity_required",
        forbidden_reason="restore_requester_role_forbidden",
    )


def _require_restore_admin(request: Request) -> Dict[str, Optional[str]]:
    return _require_ops_roles(
        request,
        allowed_roles={"admin"},
        missing_reason="restore_admin_identity_required",
        forbidden_reason="restore_admin_required",
    )


def ensure_ops_read_access(request: Request) -> Dict[str, Optional[str]]:
    actor = _ops_actor(request)
    try:
        request.app.state.ops_permission_policy.authorize_read(
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
        )
    except PermissionError as exc:
        reason = str(exc)
        code = "ops_actor_missing" if "identity_required" in reason else "ops_actor_forbidden"
        raise HTTPException(status_code=403, detail={"code": code, "reason": reason}) from exc
    return actor


def ensure_ops_write_access(request: Request) -> Dict[str, Optional[str]]:
    actor = _ops_actor(request)
    try:
        request.app.state.ops_permission_policy.authorize_write(
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            method=request.method,
            path=request.url.path.rstrip("/") or request.url.path,
        )
    except PermissionError as exc:
        reason = str(exc)
        code = "ops_actor_missing" if "identity_required" in reason else "ops_actor_forbidden"
        raise HTTPException(status_code=403, detail={"code": code, "reason": reason}) from exc
    return actor


@router.get("/review-queue")
def review_queue(request: Request) -> Dict[str, Any]:
    return {"reviews": request.app.state.review_service.queue()}


@router.get("/review-hub")
def review_hub(
    request: Request,
    queue: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    severity: Optional[str] = None,
    account_id: Optional[str] = None,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return request.app.state.ops_review_hub_service.review_hub(
        queue=queue,
        status=status,
        owner_id=owner_id,
        severity=severity,
        account_id=account_id,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/review-items/{review_item_id}")
def review_item_detail(review_item_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.ops_review_hub_service.review_item_detail(review_item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/review-items/{review_item_id}/work")
def review_item_work_detail(review_item_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.ops_review_hub_service.review_item_work_detail(review_item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/review-items/{review_item_id}/assign")
def assign_review_item(review_item_id: str, payload: OpsReviewItemAssignRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        return request.app.state.ops_review_hub_service.assign_review_item(
            review_item_id=review_item_id,
            owner_id=payload.owner_id,
            reviewer_id=str(actor["actor_id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/review-items/{review_item_id}/status")
def update_review_item_status(review_item_id: str, payload: OpsReviewItemStatusRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        return request.app.state.ops_review_hub_service.update_review_item_status(
            review_item_id=review_item_id,
            status=payload.status,
            reviewer_id=str(actor["actor_id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/review-items/{review_item_id}/decision")
def decide_review_item(review_item_id: str, payload: OpsReviewItemDecisionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        return request.app.state.ops_review_hub_service.decide_review_item(
            review_item_id=review_item_id,
            decision=payload.decision,
            reviewer_id=str(actor["actor_id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/worlds/{world_id}/status")
def world_status(world_id: str, request: Request) -> Dict[str, Any]:
    versions = request.app.state.repository.list_world_versions(world_id=world_id)
    published_version = next((item["world_version_id"] for item in versions if item.get("status") == "published"), None)
    rollback_targets = [item for item in versions if item.get("world_version_id") != published_version]
    payload: Dict[str, Any] = {
        "world_id": world_id,
        "versions": versions,
        "published_version": published_version,
        "evaluation_summary": {},
        "latest_simulation": {},
        "publish_checklist": [],
        "publish_checklist_summary": {
            "total": 0,
            "ok_count": 0,
            "blocked_count": 0,
            "publish_ready": False,
            "blocker_keys": [],
            "owners": [],
            "next_actions": [],
            "review_status_counts": {},
        },
        "recent_reviews": [],
        "recent_reviews_drilldown": [],
        "rollback_targets": rollback_targets,
        "recent_entitlement_events": [],
        "risk_summary": {
            "publish_ready": False,
            "publish_gate_errors": [],
            "latest_rollback_reason": None,
            "latest_rollback_target": None,
            "entitlement_alerts": [],
        },
        "release_evidence_bundle": {},
        "author_longform_capability": {},
        "author_claim_alignment": {},
        "longform_1000_readiness": {},
        "longform_1000_interactive_signoff": {},
        "longform_1000_human_review_closeout": {},
        "longform_1000_feasibility": {},
        "character_fidelity_remediation_framework": {},
        "quality_projection_summary": {},
        "status_warnings": [],
    }
    try:
        payload.update(request.app.state.review_service.world_status(world_id))
    except Exception as exc:  # pragma: no cover - production fallback
        logger.exception("ops world status base payload failed", extra={"world_id": world_id})
        payload["status_warnings"].append({"stage": "review_world_status", "reason": str(exc)})
    try:
        payload["learned_shadow_summary"] = request.app.state.learned_shadow_service.summarize(
            payload.get("latest_simulation", {}).get("learned_evaluation_summary", {})
        )
    except Exception as exc:  # pragma: no cover - production fallback
        logger.exception("ops world status learned shadow summary failed", extra={"world_id": world_id})
        payload["learned_shadow_summary"] = {
            "available": False,
            "status": "unavailable",
            "warnings": [str(exc)],
            "recommended_next_action": "inspect_world_status_warning",
        }
        payload["status_warnings"].append({"stage": "learned_shadow_summary", "reason": str(exc)})
    try:
        reranker_bundle = request.app.state.training_signal_service.export_bundle(
            world_id=world_id,
            dataset_view="reranker",
        )
        payload["learned_reranker_shadow_summary"] = request.app.state.learned_reranker_shadow_service.summarize(
            reranker_bundle
        )
    except Exception as exc:  # pragma: no cover - production fallback
        logger.exception("ops world status reranker summary failed", extra={"world_id": world_id})
        payload["learned_reranker_shadow_summary"] = {
            "available": False,
            "status": "unavailable",
            "warnings": [str(exc)],
            "recommended_next_action": "inspect_world_status_warning",
        }
        payload["status_warnings"].append({"stage": "learned_reranker_shadow_summary", "reason": str(exc)})
    return payload


@router.get("/worlds/{world_id}/release-workspace")
def world_release_workspace(world_id: str, request: Request, limit: int = 12) -> Dict[str, Any]:
    try:
        return request.app.state.ops_release_workspace_service.world_release_workspace(world_id=world_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/worlds/{world_id}/release-evidence-bundle")
def world_release_evidence_bundle(world_id: str, request: Request) -> Dict[str, Any]:
    payload = request.app.state.review_service.world_status(world_id)
    return {
        "world_id": world_id,
        "release_evidence_bundle": payload.get("release_evidence_bundle", {}),
        "published_version": payload.get("published_version"),
    }


@router.post("/world-versions/{world_version_id}/publish")
def publish_world_version(world_version_id: str, payload: PublishRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.review_service.publish(world_version_id, reviewer_id=payload.reviewer_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/worlds/{world_id}/rollback")
def rollback_world(world_id: str, payload: RollbackRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.review_service.rollback(world_id, payload.target_world_version_id, reviewer_id=payload.reviewer_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/meters")
def list_meters(
    reader_id: Optional[str] = None,
    account_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    return {
        "meters": request.app.state.repository.list_usage_meters(
            reader_id=reader_id,
            account_id=account_id,
            session_id=session_id,
        )
    }


@router.get("/schema-lifecycle")
def schema_lifecycle(request: Request) -> Dict[str, Any]:
    return inspect_schema_lifecycle(request.app.state.repository.engine)


@router.get("/data-integrity")
def data_integrity(limit: int = 20, request: Request = None) -> Dict[str, Any]:
    return request.app.state.data_integrity_service.build_summary(limit=limit)


@router.post("/data-integrity/repair")
def repair_data_integrity(payload: DataIntegrityRepairRequest, request: Request) -> Dict[str, Any]:
    return request.app.state.data_integrity_service.run_repair(
        actions=list(payload.actions or []),
        apply=payload.apply,
        limit=payload.limit,
    )


@router.get("/runtime-receipts")
def runtime_receipts(
    request: Request,
    account_id: Optional[str] = None,
    session_id: Optional[str] = None,
    incident_only: bool = False,
    limit: int = 50,
) -> Dict[str, Any]:
    return {
        "runtime_receipts": request.app.state.observability_service.list_runtime_receipts(
            account_id=account_id,
            session_id=session_id,
            incident_only=incident_only,
            limit=limit,
        )
    }


@router.get("/quality/summary")
def quality_summary(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    session_id: Optional[str] = None,
    source_surface: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.ops_quality_projection_service.quality_summary(
        account_id=account_id,
        world_version_id=world_version_id,
        session_id=session_id,
        source_surface=source_surface,
        status=status,
        limit=limit,
    )


@router.get("/quality/events")
def quality_events(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    session_id: Optional[str] = None,
    source_surface: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    summary = request.app.state.ops_quality_projection_service.quality_summary(
        account_id=account_id,
        world_version_id=world_version_id,
        session_id=session_id,
        source_surface=source_surface,
        status=status,
        limit=limit,
    )
    return {
        "generated_at": summary.get("generated_at"),
        "filters": summary.get("filters", {}),
        "summary": summary.get("summary", {}),
        "events": summary.get("events", []),
    }


@router.get("/quality/traces/{trace_id}")
def quality_trace_detail(trace_id: str, request: Request) -> Dict[str, Any]:
    try:
        payload = request.app.state.ops_quality_projection_service.quality_trace_detail(trace_id)
        account_id = str((payload.get("linked_context") or {}).get("account_id") or "").strip()
        if account_id:
            request.app.state.commercial_billing_service.sync_account_billing(account_id=account_id)
        payload["billing_projection"] = request.app.state.commercial_billing_service.trace_billing_projection(trace_id=trace_id)
        return payload
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/runtime-incident-snapshot")
def runtime_incident_snapshot(
    request: Request,
    account_id: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.observability_service.runtime_incident_snapshot(
        account_id=account_id,
        limit=limit,
    )


@router.get("/story-bootstrap-world-summary")
def story_bootstrap_world_summary(
    request: Request,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.observability_service.story_bootstrap_world_summary(limit=limit)


@router.get("/story-bootstrap-world-summary/worlds/{world_id}")
def story_bootstrap_world_detail(
    world_id: str,
    request: Request,
    limit: int = 20,
) -> Dict[str, Any]:
    try:
        return request.app.state.observability_service.story_bootstrap_world_detail(world_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/provider-routing")
def provider_routing_policy(
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.provider_routing_service.policy_summary()


@router.get("/provider-rollout")
def provider_rollout_summary(
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.provider_rollout_service.summary(
        candidate_backend_present=request.app.state.candidate_backend is not None,
        renderer_backend_present=request.app.state.renderer_backend is not None,
    )


@router.post("/provider-rollout/{track}/canary")
def provider_rollout_canary(
    track: str,
    payload: ProviderRolloutDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        request.app.state.provider_rollout_service.save_track_decision(
            track=track,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
            rollout_status="canary",
            bucket_percentage=payload.bucket_percentage,
            world_allowlist=payload.world_allowlist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return request.app.state.provider_rollout_service.summary(
        candidate_backend_present=request.app.state.candidate_backend is not None,
        renderer_backend_present=request.app.state.renderer_backend is not None,
    )


@router.post("/provider-rollout/{track}/activate")
def provider_rollout_activate(
    track: str,
    payload: ProviderRolloutDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        request.app.state.provider_rollout_service.save_track_decision(
            track=track,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
            rollout_status="active",
            bucket_percentage=0,
            world_allowlist=payload.world_allowlist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return request.app.state.provider_rollout_service.summary(
        candidate_backend_present=request.app.state.candidate_backend is not None,
        renderer_backend_present=request.app.state.renderer_backend is not None,
    )


@router.post("/provider-rollout/{track}/rollback")
def provider_rollout_rollback(
    track: str,
    payload: ProviderRolloutDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        request.app.state.provider_rollout_service.save_track_decision(
            track=track,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
            rollout_status="rolled_back",
            bucket_percentage=0,
            world_allowlist=[],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return request.app.state.provider_rollout_service.summary(
        candidate_backend_present=request.app.state.candidate_backend is not None,
        renderer_backend_present=request.app.state.renderer_backend is not None,
    )


@router.get("/provider-runtime-metrics")
def provider_runtime_metrics(
    request: Request,
    account_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return request.app.state.observability_service.provider_runtime_metrics(
        account_id=account_id,
        session_id=session_id,
        limit=limit,
    )


@router.get("/jobs")
def list_async_jobs(
    request: Request,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    return {
        "summary": request.app.state.async_job_service.queue_summary(limit=limit),
        "jobs": request.app.state.async_job_service.list_jobs(
            status=status,
            job_type=job_type,
            limit=limit,
        ),
    }


@router.get("/jobs/incidents")
def async_job_incidents(
    request: Request,
    stale_after_minutes: int = 15,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.incident_snapshot(
        stale_after_minutes=stale_after_minutes,
        limit=limit,
    )


@router.get("/jobs/boot-reconcile")
def async_job_boot_reconcile(request: Request) -> Dict[str, Any]:
    return request.app.state.async_job_boot_reconcile or {
        "generated_at": None,
        "requested_by": "boot_reconciler",
        "reconciled_count": 0,
        "reconciled_jobs": [],
        "recommended_action": "none",
    }


@router.get("/jobs/artifact-retention")
def async_job_artifact_retention(request: Request, limit: int = 20) -> Dict[str, Any]:
    return request.app.state.async_job_service.artifact_retention_snapshot(limit=limit)


@router.get("/jobs/operator-history")
def async_job_operator_history(
    request: Request,
    operator_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.operator_run_history(
        operator_id=operator_id,
        limit=limit,
    )


@router.get("/jobs/handoff-bundle")
def async_job_handoff_bundle(request: Request, limit: int = 20) -> Dict[str, Any]:
    return request.app.state.async_job_service.build_handoff_bundle(limit=limit)


@router.get("/jobs/remote-shipping")
def async_job_remote_shipping(request: Request, limit: int = 20) -> Dict[str, Any]:
    return request.app.state.async_job_service.remote_shipping_snapshot(limit=limit)


@router.get("/jobs/handoff-sla")
def async_job_handoff_sla(request: Request, limit: int = 20, sla_minutes: int = 240) -> Dict[str, Any]:
    return request.app.state.async_job_service.handoff_sla_snapshot(limit=limit, sla_minutes=sla_minutes)


@router.get("/jobs/notification-sinks")
def async_job_notification_sinks(request: Request) -> Dict[str, Any]:
    return request.app.state.async_job_service.notification_sink_snapshot()


@router.get("/jobs/retry-policies")
def async_job_retry_policies(request: Request) -> Dict[str, Any]:
    return request.app.state.async_job_service.retry_policy_summary()


@router.get("/jobs/adapter-config-validation")
def async_job_adapter_config_validation(request: Request) -> Dict[str, Any]:
    return request.app.state.async_job_service.adapter_config_validation()


@router.get("/jobs/adapter-health-probe")
def async_job_adapter_health_probe(request: Request) -> Dict[str, Any]:
    return request.app.state.async_job_service.adapter_health_probe()


@router.get("/jobs/notification-delivery-receipts")
def async_job_notification_delivery_receipts(
    request: Request,
    sink_name: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.notification_delivery_receipts(
        sink_name=sink_name,
        event_type=event_type,
        limit=limit,
    )


@router.get("/jobs/notification-delivery-receipts/{event_id}")
def async_job_notification_delivery_receipt_detail(event_id: int, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.async_job_service.notification_delivery_receipt_detail(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/jobs/notification-retry-queue")
def async_notification_retry_queue(
    request: Request,
    status: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.list_notification_retry_queue(status=status, limit=limit)


@router.get("/jobs/notification-dead-letter-queue")
def async_notification_dead_letter_queue(
    request: Request,
    status: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.list_notification_dead_letter_queue(status=status, limit=limit)


@router.get("/jobs/retry-outcome-dashboard")
def async_retry_outcome_dashboard(
    request: Request,
    limit: int = 20,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.notification_retry_outcome_dashboard(limit=limit)


@router.post("/jobs/notification-retry-queue/enqueue")
def enqueue_async_notification_retry(
    payload: AsyncNotificationRetryEnqueueRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        retry = request.app.state.async_job_service.enqueue_notification_retry(
            payload.event_id,
            requested_by=payload.requested_by or "ops_web",
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"retry": retry}


@router.post("/jobs/notification-retry-queue/{retry_id}/process")
def process_async_notification_retry(
    retry_id: str,
    payload: AsyncNotificationRetryProcessRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        retry = request.app.state.async_job_service.process_notification_retry(
            retry_id,
            requested_by=payload.requested_by or "ops_web",
            sink_name=payload.sink_name,
            dry_run=payload.dry_run,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"retry": retry}


@router.post("/jobs/handoff-bundle/export")
def export_async_job_handoff_bundle(
    payload: AsyncJobHandoffExportRequest,
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.export_handoff_bundle(
        requested_by=payload.requested_by or "ops_web",
        limit=payload.limit,
        output_dir=payload.output_dir,
        sink_name=payload.sink_name,
        dry_run_notification=payload.dry_run_notification,
    )


@router.post("/jobs/handoff-sla/escalate")
def escalate_async_job_handoff_sla(
    payload: AsyncJobHandoffSlaRequest,
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.escalate_handoff_sla(
        requested_by=payload.requested_by or "ops_web",
        sla_minutes=payload.sla_minutes,
        limit=payload.limit,
        dry_run=payload.dry_run,
        sink_name=payload.sink_name,
    )


@router.post("/jobs/enforce-retention")
def enforce_async_job_retention(
    payload: AsyncJobRetentionCleanupRequest,
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.enforce_artifact_retention(
        requested_by=payload.requested_by or "ops_web",
        dry_run=payload.dry_run,
        limit=payload.limit,
    )


@router.post("/jobs/cold-start-drill")
def run_async_job_cold_start_drill(
    payload: AsyncJobColdStartDrillRequest,
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.run_cold_start_recovery_drill(
        requested_by=payload.requested_by or "ops_web",
        stale_after_minutes=payload.stale_after_minutes,
        limit=payload.limit,
    )


@router.get("/jobs/{job_id}")
def get_async_job(job_id: str, request: Request) -> Dict[str, Any]:
    try:
        return {"job": request.app.state.async_job_service.get_job(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/{job_id}/acknowledge")
def acknowledge_async_job(
    job_id: str,
    payload: AsyncJobAcknowledgeRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.acknowledge_job(
            job_id,
            requested_by=payload.requested_by or "ops_web",
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"job": job}


@router.post("/jobs/{job_id}/ship-remote")
def ship_async_job_remote_artifacts(
    job_id: str,
    payload: AsyncJobRemoteShippingRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        return request.app.state.async_job_service.ship_remote_artifacts(
            job_id,
            requested_by=payload.requested_by or "ops_web",
            adapter_name=payload.adapter_name,
            remote_dir=payload.remote_dir,
            dry_run=payload.dry_run,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/learned-training")
def enqueue_learned_training_job(
    payload: AsyncLearnedTrainingJobRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.enqueue_job(
            job_type="learned_training",
            payload={
                "tracks": payload.tracks,
                "world_id": payload.world_id,
                "world_version_id": payload.world_version_id,
                "limit": payload.limit,
            },
            requested_by=payload.requested_by or "ops_web",
            schedule=background_tasks.add_task,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@router.post("/jobs/runtime-backups")
def enqueue_runtime_backup_job(
    payload: AsyncRuntimeBackupJobRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.enqueue_job(
            job_type="runtime_backup",
            payload={
                "label": payload.label,
                "output_dir": payload.output_dir,
                "dry_run": payload.dry_run,
            },
            requested_by=payload.requested_by or "ops_web",
            account_id=payload.account_id,
            schedule=background_tasks.add_task,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@router.post("/jobs/{job_id}/retry")
def retry_async_job(
    job_id: str,
    payload: AsyncJobActionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.retry_job(
            job_id,
            requested_by=payload.requested_by or "ops_web",
            schedule=background_tasks.add_task,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@router.post("/jobs/{job_id}/resume")
def resume_async_job(
    job_id: str,
    payload: AsyncJobActionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.resume_job(
            job_id,
            requested_by=payload.requested_by or "ops_web",
            stale_after_minutes=payload.stale_after_minutes,
            force=payload.force,
            schedule=background_tasks.add_task,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@router.post("/jobs/recover-incidents")
def recover_async_job_incidents(
    payload: AsyncJobRecoveryRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    return request.app.state.async_job_service.recover_incidents(
        requested_by=payload.requested_by or "ops_web",
        stale_after_minutes=payload.stale_after_minutes,
        limit=payload.limit,
        schedule=background_tasks.add_task,
    )


@router.get("/deployment-runbook")
def deployment_runbook(request: Request) -> Dict[str, Any]:
    return request.app.state.runtime_ops_service.build_deployment_runbook()


@router.get("/deployment-health-gate")
def deployment_health_gate(request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.runtime_ops_service.build_deployment_health_gate(account_id=account_id)


@router.get("/preflight-verification-bundle")
def preflight_verification_bundle(request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.runtime_ops_service.build_preflight_verification_bundle(account_id=account_id)


@router.get("/incident-playbook")
def incident_playbook(request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.runtime_ops_service.build_incident_playbook(account_id=account_id)


@router.get("/recovery-drills")
def recovery_drills(request: Request) -> Dict[str, Any]:
    return {"recovery_drills": request.app.state.runtime_ops_service.list_recovery_drills(limit=10)}


@router.get("/runtime-restore-requests")
def runtime_restore_requests(request: Request, limit: int = 20) -> Dict[str, Any]:
    return {"restore_requests": request.app.state.runtime_ops_service.list_restore_requests(limit=limit)}


@router.post("/runtime-restore/request")
def request_runtime_restore(payload: RuntimeRestoreCreateRequest, request: Request) -> Dict[str, Any]:
    try:
        actor = _require_restore_requester(request)
        restore_request = request.app.state.runtime_ops_service.request_restore(
            backup_path=payload.backup_path,
            requested_by=str(actor["actor_id"]),
            reason=payload.reason,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"restore_request": restore_request}


@router.post("/runtime-restore/{request_id}/approve")
def approve_runtime_restore(request_id: str, payload: RuntimeRestoreApproveRequest, request: Request) -> Dict[str, Any]:
    try:
        actor = _require_restore_admin(request)
        restore_request = request.app.state.runtime_ops_service.approve_restore_request(
            request_id=request_id,
            approver_id=str(actor["actor_id"]),
            reason=payload.reason,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"restore_request": restore_request}


@router.post("/runtime-restore/{request_id}/revoke")
def revoke_runtime_restore(request_id: str, payload: RuntimeRestoreRevokeRequest, request: Request) -> Dict[str, Any]:
    try:
        actor = _require_restore_admin(request)
        restore_request = request.app.state.runtime_ops_service.revoke_restore_request(
            request_id=request_id,
            reviewer_id=str(actor["actor_id"]),
            reason=payload.reason,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"restore_request": restore_request}


@router.post("/recovery-drill")
def recovery_drill(payload: RuntimeRecoveryDrillRequest, request: Request) -> Dict[str, Any]:
    result = request.app.state.runtime_ops_service.run_recovery_drill(
        backup_path=payload.backup_path,
        output_dir=payload.output_dir,
    )
    request.app.state.analytics_service.track(
        "runtime_recovery_drill_ran",
        payload_json=result,
    )
    return {"recovery_drill": result}


@router.post("/jobs/runtime-restores")
def enqueue_runtime_restore_job(
    payload: AsyncRuntimeRestoreJobRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    try:
        actor = _require_restore_admin(request)
        job = request.app.state.async_job_service.enqueue_job(
            job_type="runtime_restore",
            payload={
                "request_id": payload.request_id,
                "requested_by": str(actor["actor_id"]),
            },
            requested_by=str(actor["actor_id"]),
            account_id=payload.account_id,
            schedule=background_tasks.add_task,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@router.post("/runtime-backups")
def runtime_backup(payload: RuntimeBackupRequest, request: Request) -> Dict[str, Any]:
    result = request.app.state.runtime_ops_service.create_backup(
        label=payload.label,
        output_dir=payload.output_dir,
        dry_run=payload.dry_run,
    )
    request.app.state.analytics_service.track(
        "runtime_backup_created",
        payload_json=result,
    )
    return {"backup": result}


@router.post("/runtime-restore")
def runtime_restore(payload: RuntimeRestoreRequest, request: Request) -> Dict[str, Any]:
    result = request.app.state.runtime_ops_service.restore_backup(
        backup_path=payload.backup_path,
        dry_run=payload.dry_run,
    )
    request.app.state.analytics_service.track(
        "runtime_restore_applied" if not payload.dry_run else "runtime_restore_planned",
        payload_json=result,
    )
    return {"restore": result}


@router.get("/subscriptions")
def list_subscriptions(account_id: Optional[str] = None, status: Optional[str] = None, request: Request = None) -> Dict[str, Any]:
    return request.app.state.billing_service.list_subscriptions(account_id=account_id, status=status)


@router.get("/entitlements")
def list_entitlements(account_id: Optional[str] = None, reader_id: Optional[str] = None, world_id: Optional[str] = None, request: Request = None) -> Dict[str, Any]:
    resolved_account_id = request.app.state.billing_service.resolve_account_id(account_id=account_id, reader_id=reader_id)
    return request.app.state.billing_service.entitlement_audit(account_id=resolved_account_id, world_id=world_id)


@router.get("/accounts/{account_id}")
def account_detail(account_id: str, request: Request, limit: int = 10) -> Dict[str, Any]:
    return request.app.state.billing_service.account_detail(account_id=account_id, limit=limit)


@router.get("/accounts/{account_id}/workspace")
def account_workspace(account_id: str, request: Request, limit: int = 12) -> Dict[str, Any]:
    return request.app.state.ops_account_workspace_service.account_workspace(account_id=account_id, limit=limit)


@router.get("/customers")
def list_customers(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.customer_account_service.list_customer_accounts(status=status, limit=limit)


@router.get("/customers/{customer_account_id}")
def customer_detail(customer_account_id: str, request: Request) -> Dict[str, Any]:
    return request.app.state.customer_account_service.customer_account_detail(customer_account_id=customer_account_id)


@router.get("/billing/usage-ledgers")
def list_usage_ledgers(
    request: Request,
    account_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    if account_id:
        request.app.state.commercial_billing_service.sync_account_billing(account_id=account_id)
    return request.app.state.commercial_billing_service.list_usage_ledgers(account_id=account_id, limit=limit)


@router.get("/billing/invoice-previews")
def list_invoice_previews(
    request: Request,
    account_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    if account_id:
        request.app.state.commercial_billing_service.sync_account_billing(account_id=account_id)
    return request.app.state.commercial_billing_service.list_invoice_previews(account_id=account_id, limit=limit)


@router.post("/billing/billable-events/{billable_event_id}/status")
def update_billable_event_status(
    billable_event_id: str,
    payload: BillableEventStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        event = request.app.state.commercial_billing_service.update_billable_event_status(
            billable_event_id=billable_event_id,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "billable_event_status_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "billable_event_missing", "reason": str(exc)}) from exc
    return {"billable_event": event}


@router.post("/campaigns/{campaign_id}/decision")
def decide_campaign(campaign_id: str, payload: CampaignDecisionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.customer_campaign_service.decide_campaign(
            campaign_id=campaign_id,
            reviewer_id=str(actor["actor_id"]),
            decision=payload.decision,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "campaign_decision_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "campaign_missing", "reason": str(exc)}) from exc


@router.get("/partners")
def list_partners(
    request: Request,
    lifecycle_status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.partner_readiness_service.list_partners(lifecycle_status=lifecycle_status, limit=limit)


@router.get("/partners/{partner_id}")
def partner_detail(partner_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.partner_readiness_service.partner_detail(partner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "partner_missing", "reason": str(exc)}) from exc


@router.post("/partners/{partner_id}/status")
def update_partner_status(partner_id: str, payload: PartnerStatusRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.partner_readiness_service.change_status(
            partner_id=partner_id,
            status=payload.status,
            note=payload.note or str(actor["actor_id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "partner_status_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "partner_missing", "reason": str(exc)}) from exc


@router.get("/disputes")
def list_disputes(request: Request, account_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    return request.app.state.commercial_support_service.list_disputes(account_id=account_id, status=status, limit=limit)


@router.post("/disputes/{dispute_id}/decision")
def decide_dispute(dispute_id: str, payload: DisputeDecisionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.commercial_support_service.decide_dispute(
            dispute_id=dispute_id,
            reviewer_id=str(actor["actor_id"]),
            decision=payload.decision,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "dispute_decision_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "dispute_missing", "reason": str(exc)}) from exc


@router.post("/manual-adjustments")
def create_manual_adjustment(payload: ManualAdjustmentRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        adjustment = request.app.state.commercial_support_service.create_manual_adjustment(
            account_id=payload.account_id,
            reviewer_id=str(actor["actor_id"]),
            payload=payload.model_dump(),
        )
        return {"manual_adjustment": adjustment}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "manual_adjustment_invalid", "reason": str(exc)}) from exc


@router.get("/support-cases")
def list_support_cases(request: Request, account_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    return request.app.state.commercial_support_service.list_support_cases(account_id=account_id, status=status, limit=limit)


@router.post("/support-cases/{support_case_id}/status")
def update_support_case_status(support_case_id: str, payload: SupportCaseStatusRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        support_case = request.app.state.commercial_support_service.update_support_case_status(
            support_case_id=support_case_id,
            reviewer_id=str(actor["actor_id"]),
            status=payload.status,
            note=payload.note,
        )
        return {"support_case": support_case}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "support_case_status_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "support_case_missing", "reason": str(exc)}) from exc


@router.post("/invoices/{invoice_preview_id}/issue")
def issue_invoice(invoice_preview_id: str, payload: InvoiceIssueRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.stripe_invoicing_service.issue_invoice(
            invoice_preview_id=invoice_preview_id,
            requested_by=payload.requested_by or str(actor["actor_id"]),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invoice_issue_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "invoice_preview_missing", "reason": str(exc)}) from exc


@router.get("/invoices")
def list_issued_invoices(request: Request, account_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    return request.app.state.stripe_invoicing_service.list_invoices(account_id=account_id, limit=limit)


@router.post("/invoices/{invoice_id}/retry-payment")
def retry_invoice_payment(invoice_id: str, payload: InvoiceRetryRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.stripe_invoicing_service.retry_invoice_payment(
            invoice_id=invoice_id,
            requested_by=payload.requested_by or str(actor["actor_id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "invoice_missing", "reason": str(exc)}) from exc


@router.post("/provider-webhooks/{provider_webhook_event_id}/replay")
def replay_provider_webhook(provider_webhook_event_id: str, request: Request) -> Dict[str, Any]:
    _require_ops_reviewer(request, None)
    try:
        return request.app.state.stripe_invoicing_service.replay_webhook(provider_webhook_event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "provider_webhook_missing", "reason": str(exc)}) from exc


@router.get("/audit")
def list_ops_audit(
    request: Request,
    account_id: Optional[str] = None,
    customer_account_id: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return request.app.state.commercial_audit_service.audit_log_listing(
        account_id=account_id,
        customer_account_id=customer_account_id,
        action_type=action_type,
        limit=limit,
    )


@router.get("/commercialization-summary")
def commercialization_summary(request: Request, limit: int = 50) -> Dict[str, Any]:
    return request.app.state.ops_commercialization_dashboard_service.summary(limit=limit)


@router.get("/production-signoff")
def list_production_signoff(request: Request, limit: int = 25) -> Dict[str, Any]:
    return request.app.state.production_signoff_service.list_signoffs(limit=limit)


@router.post("/production-signoff/initialize")
def initialize_production_signoff(payload: ProductionSignoffInitializeRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_signoff_service.initialize_signoff_run(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            launch_label=payload.launch_label,
            due_in_days=payload.due_in_days,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "production_signoff_seed_artifact_missing", "reason": str(exc)}) from exc


@router.get("/production-signoff/{signoff_id}")
def production_signoff_detail(signoff_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.production_signoff_service.signoff_detail(signoff_id=signoff_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/items/{signoff_item_id}/assign")
def assign_production_signoff_item(signoff_item_id: str, payload: ProductionSignoffAssignRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_signoff_service.assign_signoff_item_owner(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_item_id=signoff_item_id,
            owner_actor_id=payload.owner_actor_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_item_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/items/{signoff_item_id}/decision")
def decide_production_signoff_item(signoff_item_id: str, payload: ProductionSignoffDecisionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_signoff_service.decide_signoff_item(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_item_id=signoff_item_id,
            decision=payload.decision,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "production_signoff_decision_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_item_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/items/{signoff_item_id}/evidence")
def append_production_signoff_evidence(signoff_item_id: str, payload: ProductionSignoffEvidenceRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_signoff_service.append_signoff_evidence(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_item_id=signoff_item_id,
            evidence_type=payload.evidence_type,
            summary=payload.summary,
            source_ref=payload.source_ref,
            payload=payload.payload,
            customer_safe=payload.customer_safe,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_item_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/items/{signoff_item_id}/operator-evidence")
def append_production_signoff_operator_evidence(signoff_item_id: str, payload: ProductionSignoffOperatorEvidenceRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.human_signoff_closure_service.append_operator_evidence(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_item_id=signoff_item_id,
            evidence_key=payload.evidence_key,
            summary=payload.summary,
            source_ref=payload.source_ref,
            payload=payload.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "production_operator_evidence_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_item_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/items/{signoff_item_id}/operator-close")
def close_production_signoff_operator_item(signoff_item_id: str, payload: ProductionSignoffOperatorCloseRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.human_signoff_closure_service.close_operator_item(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_item_id=signoff_item_id,
            decision=payload.decision,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "production_operator_close_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_item_missing", "reason": str(exc)}) from exc


@router.post("/production-signoff/{signoff_id}/cutover-window")
def mark_production_cutover_window(signoff_id: str, payload: ProductionCutoverWindowRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_signoff_service.mark_cutover_window(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            signoff_id=signoff_id,
            launch_wave=payload.launch_wave,
            target_environment=payload.target_environment,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            rollback_owner_role=payload.rollback_owner_role,
            status=payload.status,
            payload=payload.payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_missing", "reason": str(exc)}) from exc


@router.get("/production-signoff/{signoff_id}/export")
def export_production_signoff(signoff_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.production_signoff_service.export_signoff_record(signoff_id=signoff_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_missing", "reason": str(exc)}) from exc


@router.get("/production-signoff-board")
def production_signoff_board(request: Request, signoff_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        return request.app.state.production_signoff_board_service.board(signoff_id=signoff_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_signoff_missing", "reason": str(exc)}) from exc


@router.get("/human-signoff-closure")
def human_signoff_closure(request: Request, signoff_id: Optional[str] = None) -> Dict[str, Any]:
    pack = request.app.state.human_signoff_closure_service.build_pack(signoff_id=signoff_id)
    return {
        "closure": request.app.state.human_signoff_closure_service.closure(signoff_id=signoff_id),
        "artifact_refs": pack,
    }


@router.get("/human-signoff-closure/{owner_role}")
def human_signoff_closure_owner(owner_role: str, request: Request, signoff_id: Optional[str] = None) -> Dict[str, Any]:
    pack = request.app.state.human_signoff_closure_service.build_pack(signoff_id=signoff_id)
    return {
        "closure": request.app.state.human_signoff_closure_service.closure(signoff_id=signoff_id, owner_role=owner_role),
        "artifact_refs": pack,
    }


@router.post("/production-preflight/runs")
def run_production_preflight(payload: ProductionPreflightRunRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.production_preflight_service.run_preflight(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        signoff_id=payload.signoff_id,
        launch_wave=payload.launch_wave,
        target_environment=payload.target_environment,
    )


@router.get("/production-preflight")
def list_production_preflight(
    request: Request,
    signoff_id: Optional[str] = None,
    launch_wave: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    return request.app.state.production_preflight_service.list_runs(
        signoff_id=signoff_id,
        launch_wave=launch_wave,
        limit=limit,
    )


@router.get("/production-preflight/{preflight_run_id}")
def production_preflight_detail(preflight_run_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.production_preflight_service.run_detail(preflight_run_id=preflight_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_preflight_missing", "reason": str(exc)}) from exc


@router.get("/production-preflight/{preflight_run_id}/report")
def production_preflight_report(preflight_run_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.production_preflight_service.report(preflight_run_id=preflight_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_preflight_missing", "reason": str(exc)}) from exc


@router.get("/launch-week-pack")
def launch_week_pack(request: Request) -> Dict[str, Any]:
    return request.app.state.production_launch_week_pack_service.latest_pack()


@router.get("/launch-handshake-pack")
def launch_handshake_pack(request: Request) -> Dict[str, Any]:
    return request.app.state.production_handshake_pack_service.latest_pack()


@router.get("/wave-activation")
def list_wave_activation(request: Request, launch_wave: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.wave_activation_controller_service.summary(launch_wave=launch_wave)


@router.get("/wave-activation/{launch_wave}")
def wave_activation_detail(launch_wave: str, request: Request) -> Dict[str, Any]:
    return request.app.state.wave_activation_controller_service.evaluate(launch_wave=launch_wave)


@router.post("/wave-activation/{launch_wave}/arm")
def arm_wave_activation(launch_wave: str, payload: WaveActivationRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.wave_activation_controller_service.arm(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=launch_wave,
    )


@router.post("/wave-activation/{launch_wave}/evaluate")
def evaluate_wave_activation(launch_wave: str, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.wave_activation_controller_service.evaluate(
        launch_wave=launch_wave,
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
    )


@router.post("/wave-activation/{launch_wave}/rollback-watch")
def mark_wave_activation_rollback_watch(launch_wave: str, payload: WaveActivationRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.wave_activation_controller_service.mark_rollback_watch(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=launch_wave,
        note=payload.note,
    )


@router.get("/launch-command-center")
def launch_command_center(request: Request, launch_wave: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.launch_command_center_service.command_center(launch_wave=launch_wave)


@router.get("/production-acceptance")
def list_production_acceptance(
    request: Request,
    launch_wave: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.production_acceptance_service.list_acceptance_records(
        launch_wave=launch_wave,
        status=status,
        limit=limit,
    )


@router.post("/production-acceptance/generate")
def generate_production_acceptance(payload: ProductionAcceptanceGenerateRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    try:
        return request.app.state.production_acceptance_service.generate_acceptance_record(
            actor_id=str(actor["actor_id"]),
            actor_role=str(actor["actor_role"]),
            account_id=payload.account_id,
            launch_wave=payload.launch_wave,
            signoff_id=payload.signoff_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_acceptance_missing_dependency", "reason": str(exc)}) from exc


@router.get("/production-acceptance/{acceptance_record_id}")
def production_acceptance_detail(acceptance_record_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.production_acceptance_service.acceptance_record_detail(
            acceptance_record_id=acceptance_record_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "production_acceptance_missing", "reason": str(exc)}) from exc


@router.get("/launch-waves")
def list_launch_waves(request: Request, launch_wave: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    records = request.app.state.production_acceptance_service.list_acceptance_records(
        launch_wave=launch_wave,
        status=status,
        limit=limit,
    )
    return {
        "launch_waves": records["launch_waves"],
        "summary": records["summary"],
    }


@router.get("/launch-week-pack")
def launch_week_pack(request: Request) -> Dict[str, Any]:
    return request.app.state.production_launch_week_pack_service.latest_pack()


@router.post("/launch-waves/{launch_wave}/status")
def update_launch_wave_status(launch_wave: str, payload: LaunchWaveStatusUpdateRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.production_acceptance_service.update_launch_wave_status(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=launch_wave,
        status=payload.status,
        note=payload.note,
    )


@router.post("/customer-success/snapshots/sync")
def sync_customer_success(payload: CustomerSuccessSyncRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.customer_success_reporting_service.sync_snapshots(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        account_id=payload.account_id,
        launch_wave=payload.launch_wave,
    )


@router.get("/customer-success")
def list_customer_success(request: Request, account_id: Optional[str] = None, launch_wave: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    return request.app.state.customer_success_reporting_service.list_customer_success(
        account_id=account_id,
        launch_wave=launch_wave,
        limit=limit,
    )


@router.get("/customer-success/report")
def customer_success_launch_wave_report(request: Request, launch_wave: str, view: str = "investor_safe") -> Dict[str, Any]:
    try:
        return request.app.state.customer_success_reporting_service.report(launch_wave=launch_wave, view=view)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "customer_success_missing", "reason": str(exc)}) from exc


@router.get("/customer-success/{account_id}")
def customer_success_detail(account_id: str, request: Request) -> Dict[str, Any]:
    return request.app.state.customer_success_reporting_service.detail(account_id=account_id)


@router.get("/customer-success/{account_id}/report")
def customer_success_account_report(account_id: str, request: Request, view: str = "internal") -> Dict[str, Any]:
    try:
        return request.app.state.customer_success_reporting_service.report(account_id=account_id, view=view)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "customer_success_missing", "reason": str(exc)}) from exc


@router.post("/launch-ledger/sync")
def sync_launch_ledger(payload: LaunchLedgerSyncRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.production_launch_ledger_service.sync(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=payload.launch_wave,
    )


@router.get("/launch-ledger")
def list_launch_ledger(request: Request, launch_wave: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    return request.app.state.production_launch_ledger_service.list_events(launch_wave=launch_wave, limit=limit)


@router.get("/launch-ledger/{launch_wave}")
def launch_ledger_detail(launch_wave: str, request: Request, limit: int = 200) -> Dict[str, Any]:
    return request.app.state.production_launch_ledger_service.list_events(launch_wave=launch_wave, limit=limit)


@router.get("/postmortem-pack")
def build_postmortem_pack(request: Request, launch_wave: str, account_id: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.production_launch_ledger_service.build_postmortem_pack(
        launch_wave=launch_wave,
        account_id=account_id,
    )


@router.post("/go-live-day/run")
def run_go_live_day(payload: GoLiveDayRunRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.go_live_day_runner_service.run(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=payload.launch_wave,
        signoff_id=payload.signoff_id,
        account_id=payload.account_id,
    )


@router.get("/go-live-day/{run_id}")
def go_live_day_detail(run_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.go_live_day_runner_service.detail(run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "go_live_day_run_missing", "reason": str(exc)}) from exc


@router.post("/launch-week-guard/sync")
def sync_launch_week_guard(payload: LaunchWeekGuardSyncRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, None)
    return request.app.state.launch_week_guard_service.sync(
        actor_id=str(actor["actor_id"]),
        actor_role=str(actor["actor_role"]),
        launch_wave=payload.launch_wave,
    )


@router.get("/launch-week-guard")
def list_launch_week_guard(request: Request, launch_wave: Optional[str] = None) -> Dict[str, Any]:
    return request.app.state.launch_week_guard_service.list_runs(launch_wave=launch_wave)


@router.get("/launch-week-guard/{launch_wave}")
def launch_week_guard_detail(launch_wave: str, request: Request) -> Dict[str, Any]:
    return request.app.state.launch_week_guard_service.detail(launch_wave=launch_wave)


@router.get("/first-customer-success-pack/{launch_wave}")
def first_customer_success_pack(launch_wave: str, request: Request) -> Dict[str, Any]:
    detail = request.app.state.launch_week_guard_service.detail(launch_wave=launch_wave)
    pack = detail.get("first_customer_success_pack")
    if not pack:
        raise HTTPException(status_code=404, detail={"code": "first_customer_success_pack_missing", "reason": launch_wave})
    return detail


@router.get("/lifecycle-automation")
def lifecycle_automation_state(request: Request, account_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    return request.app.state.commercial_lifecycle_automation_service.list_account_state(account_id=account_id, limit=limit)


@router.post("/lifecycle-automation/sync")
def sync_lifecycle_automation(payload: LifecycleAutomationSyncRequest, request: Request) -> Dict[str, Any]:
    _require_ops_reviewer(request, None)
    return request.app.state.commercial_lifecycle_automation_service.sync_account(account_id=payload.account_id)


@router.get("/accounts/{account_id}/issues")
def account_issue_lookup(account_id: str, request: Request, limit: int = 10) -> Dict[str, Any]:
    return request.app.state.billing_service.support_issue_lookup(account_id=account_id, limit=limit)


@router.get("/accounts/{account_id}/governance")
def account_governance(account_id: str, request: Request, limit: int = 20) -> Dict[str, Any]:
    return request.app.state.governance_service.account_snapshot(account_id=account_id, limit=limit)


@router.get("/investigations/accounts/{account_id}")
def investigate_account(
    account_id: str,
    request: Request,
    world_version_id: Optional[str] = None,
    case_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.ops_traceability_service.investigate_account(
        account_id=account_id,
        world_version_id=world_version_id,
        case_id=case_id,
        limit=limit,
    )


@router.get("/investigations/cases/{case_id}")
def investigate_case(case_id: str, request: Request, limit: int = 50) -> Dict[str, Any]:
    try:
        return request.app.state.ops_traceability_service.investigate_case(case_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/investigations/world-versions/{world_version_id}")
def investigate_world_version(world_version_id: str, request: Request, limit: int = 50) -> Dict[str, Any]:
    try:
        return request.app.state.ops_traceability_service.investigate_world_version(world_version_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/export/investigation-trace")
def export_investigation_trace(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    case_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    if case_id:
        return request.app.state.ops_traceability_service.investigate_case(case_id, limit=limit)
    if world_version_id:
        return request.app.state.ops_traceability_service.investigate_world_version(world_version_id, limit=limit)
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id_or_case_id_or_world_version_id_required")
    return request.app.state.ops_traceability_service.investigate_account(
        account_id=account_id,
        world_version_id=world_version_id,
        case_id=case_id,
        limit=limit,
    )


@router.get("/alerts")
def list_ops_alerts(
    request: Request,
    account_id: Optional[str] = None,
    status_filter: str = "actionable",
    severity: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.ops_alerting_service.list_alerts(
        account_id=account_id,
        status_filter=status_filter,
        severity=severity,
        limit=limit,
    )


@router.get("/navigation-model")
def ops_navigation_model(
    request: Request,
    account_id: Optional[str] = None,
    world_id: Optional[str] = None,
    case_id: Optional[str] = None,
    alert_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        return request.app.state.ops_navigation_service.navigation_model(
            account_id=account_id,
            world_id=world_id,
            case_id=case_id,
            alert_id=alert_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/alerts/{alert_id}")
def ops_alert_detail(
    alert_id: str,
    request: Request,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        return request.app.state.ops_alerting_service.alert_detail(alert_id, account_id=account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/alerts/{alert_id}/status")
def update_ops_alert_status(
    alert_id: str,
    payload: AlertStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        detail = request.app.state.ops_alerting_service.update_alert_status(
            alert_id,
            status=payload.status,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            note=payload.note,
            account_id=payload.account_id,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return detail


@router.post("/accounts/{account_id}/governance/escalate-support")
def escalate_support_issue_to_governance(
    account_id: str,
    payload: GovernanceSupportEscalationRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.escalate_support_issue(
            account_id=account_id,
            issue_id=payload.issue_id,
            reviewer_id=actor["actor_id"],
            case_type=payload.case_type,
            severity=payload.severity,
            summary=payload.summary,
            description=payload.description,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_case_escalated_from_support",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.get("/governance/cases")
def list_governance_cases(
    request: Request,
    account_id: Optional[str] = None,
    case_type: Optional[str] = None,
    status: Optional[str] = None,
    target_type: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.governance_service.list_cases(
        account_id=account_id,
        case_type=case_type,
        status=status,
        target_type=target_type,
        limit=limit,
    )


@router.get("/governance/workload")
def governance_owner_workload(
    request: Request,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    case_type: Optional[str] = None,
    severity: Optional[str] = None,
    target_type: Optional[str] = None,
    has_active_restriction: Optional[bool] = None,
    overdue_only: bool = False,
    unassigned_only: bool = False,
    search: Optional[str] = None,
    selected_case_ids: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request)
    del actor
    return request.app.state.governance_service.owner_workload(
        status=status,
        owner_id=owner_id,
        case_type=case_type,
        severity=severity,
        target_type=target_type,
        has_active_restriction=has_active_restriction,
        overdue_only=overdue_only,
        unassigned_only=unassigned_only,
        search=search,
        selected_case_ids=[item.strip() for item in str(selected_case_ids or "").split(",") if item.strip()],
        limit=limit,
    )


@router.put("/governance/capacity/owners/{owner_id}")
def update_governance_capacity_override(
    owner_id: str,
    payload: GovernanceCapacityOverrideRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_roles(
        request,
        allowed_roles={"admin"},
        fallback_actor_id=payload.reviewer_id,
        missing_reason="governance_capacity_admin_required",
        forbidden_reason="governance_capacity_admin_required",
    )
    try:
        override = request.app.state.governance_service.update_capacity_override(
            owner_id,
            capacity_units_per_day=payload.capacity_units_per_day,
            critical_case_limit=payload.critical_case_limit,
            active_restriction_limit=payload.active_restriction_limit,
            sla_hours=payload.sla_hours,
            role_multiplier=payload.role_multiplier,
            enabled=payload.enabled,
            clear_override=payload.clear_override,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            note=payload.note,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"override": override}


@router.get("/governance/cases/{case_id}")
def governance_case_detail(case_id: str, request: Request) -> Dict[str, Any]:
    actor = _ops_actor(request)
    try:
        return request.app.state.governance_service.case_detail(
            case_id,
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/governance/cases/{case_id}/restriction-history")
def governance_case_restriction_history(case_id: str, request: Request, limit: int = 20) -> Dict[str, Any]:
    actor = _ops_actor(request)
    try:
        request.app.state.ops_permission_policy.authorize_read(
            actor_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            missing_reason="reviewer_identity_required",
        )
        return request.app.state.governance_service.restriction_history(case_id, limit=max(1, min(100, int(limit or 20))))
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/governance/cases")
def create_governance_case(payload: GovernanceCaseRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.create_case(
            {
                **_apply_ops_identity(request, payload.model_dump()),
                "actor_role": actor["actor_role"],
                "source_surface": "ops_api",
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_case_created",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.post("/governance/cases/{case_id}/restriction")
def apply_governance_case_restriction(
    case_id: str,
    payload: GovernanceCaseRestrictionRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.apply_case_restriction(
            case_id,
            restriction_type=payload.restriction_type,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            restriction_reason=payload.restriction_reason,
            expires_at=payload.expires_at,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_restriction_applied",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.post("/governance/cases/{case_id}/assign")
def assign_governance_case(
    case_id: str,
    payload: GovernanceCaseAssignRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.assign_case(
            case_id,
            owner_id=payload.owner_id,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            due_at=payload.due_at,
            note=payload.note,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"case": case}


@router.post("/governance/cases/{case_id}/evidence")
def append_governance_case_evidence(
    case_id: str,
    payload: GovernanceCaseEvidenceRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.append_case_evidence(
            case_id,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            title=payload.title,
            preview=payload.preview,
            ref_id=payload.ref_id,
            kind=payload.kind,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"case": case}


@router.get("/governance/restrictions")
def list_governance_restrictions(
    request: Request,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    return request.app.state.governance_service.list_restrictions(
        account_id=account_id,
        status=status,
        limit=limit,
    )


@router.post("/governance/restrictions")
def apply_governance_restriction(payload: GovernanceRestrictionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.apply_restriction(
            {
                **_apply_ops_identity(request, payload.model_dump()),
                "actor_role": actor["actor_role"],
                "source_surface": "ops_api",
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_restriction_applied",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.post("/governance/restrictions/{restriction_id}/release")
def release_governance_restriction(
    restriction_id: str,
    payload: GovernanceRestrictionReleaseRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.release_restriction(
            restriction_id,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            release_reason=payload.release_reason,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_restriction_released",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.patch("/governance/restrictions/{restriction_id}")
def update_governance_restriction(
    restriction_id: str,
    payload: GovernanceRestrictionUpdateRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.update_restriction(
            restriction_id,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            restriction_type=payload.restriction_type,
            restriction_reason=payload.restriction_reason,
            expires_at=payload.expires_at,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_restriction_updated",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.post("/governance/cases/{case_id}/status")
def update_governance_case_status(case_id: str, payload: GovernanceCaseStatusRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.update_case_status(
            case_id,
            status=payload.status,
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            resolution_notes=payload.resolution_notes,
            disposition=payload.disposition,
            source_surface="ops_api",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    request.app.state.analytics_service.track(
        "governance_case_status_changed",
        reader_id=case.get("account_id"),
        account_id=case.get("account_id"),
        world_id=case.get("world_id"),
        world_version_id=case.get("world_version_id"),
        payload_json=case,
    )
    return {"case": case}


@router.post("/governance/cases/bulk/preview")
def governance_bulk_action_preview(payload: GovernanceBulkActionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        return request.app.state.governance_service.bulk_action_preview(
            case_ids=list(payload.case_ids or []),
            action=payload.action,
            payload=payload.model_dump(),
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/governance/cases/bulk/execute")
def governance_bulk_action_execute(payload: GovernanceBulkActionRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        return request.app.state.governance_service.bulk_action_execute(
            case_ids=list(payload.case_ids or []),
            action=payload.action,
            payload=payload.model_dump(),
            reviewer_id=actor["actor_id"],
            actor_role=actor["actor_role"],
            source_surface="ops_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/export/governance-audit")
def export_governance_audit(
    request: Request,
    account_id: Optional[str] = None,
    case_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return request.app.state.governance_service.governance_audit_export(
        account_id=account_id,
        case_type=case_type,
        status=status,
        limit=limit,
    )


@router.post("/learned-training/run")
def run_learned_training(
    payload: LearnedTrainingRunRequest,
    request: Request,
) -> Dict[str, Any]:
    output_dir = request.app.state.base_dir / "artifacts" / "learned_training_runs"
    try:
        return run_learned_training_automation(
            repository=request.app.state.repository,
            output_dir=output_dir,
            tracks=payload.tracks,
            world_id=payload.world_id,
            world_version_id=payload.world_version_id,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-promotion-evidence")
def learned_promotion_evidence(
    request: Request,
    track: str,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    output_dir = request.app.state.base_dir / "artifacts" / "promotion_evidence"
    try:
        return build_promotion_evidence_pack(
            track=track,
            repository=request.app.state.repository,
            output_dir=output_dir,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/monetization-events")
def monetization_events(account_id: str, limit: int = 20, request: Request = None) -> Dict[str, Any]:
    return {
        "events": request.app.state.repository.list_analytics_events(
            reader_id=account_id,
            event_names=[
                "checkout_started",
                "subscription_activated",
                "subscription_state_changed",
                "subscription_canceled",
                "story_credits_consumed",
                "studio_credits_consumed",
                "entitlement_granted",
                "entitlement_revoked",
            ],
            limit=limit,
        ),
        "lifecycle_events": request.app.state.repository.list_billing_lifecycle_events(account_id=account_id, limit=limit),
        "retry_attempts": request.app.state.repository.list_billing_retry_attempts(account_id=account_id, limit=limit),
    }


@router.post("/subscriptions/grant")
def grant_subscription(payload: SubscriptionGrantRequest, request: Request) -> Dict[str, Any]:
    subscription = request.app.state.billing_service.grant_subscription(payload.model_dump())
    request.app.state.analytics_service.track(
        "subscription_activated",
        reader_id=payload.account_id,
        account_id=payload.account_id,
        access_tier=subscription.get("tier_id"),
        payload_json=subscription,
    )
    return {"subscription": subscription}


@router.post("/subscriptions/state")
def change_subscription_state(payload: SubscriptionStateRequest, request: Request) -> Dict[str, Any]:
    subscription = request.app.state.billing_service.change_subscription_state(
        payload.subscription_id,
        status=payload.status,
        cancel_at_period_end=payload.cancel_at_period_end,
    )
    request.app.state.analytics_service.track(
        "subscription_state_changed",
        reader_id=subscription.get("account_id"),
        account_id=subscription.get("account_id"),
        access_tier=subscription.get("tier_id"),
        payload_json=subscription,
    )
    if subscription["status"] == "canceled":
        request.app.state.analytics_service.track(
            "subscription_canceled",
            reader_id=subscription.get("account_id"),
            account_id=subscription.get("account_id"),
            access_tier=subscription.get("tier_id"),
            payload_json=subscription,
        )
    return {"subscription": subscription}


@router.post("/subscriptions/{subscription_id}/reconcile")
def reconcile_subscription(subscription_id: str, payload: BillingLifecycleReplayRequest, request: Request) -> Dict[str, Any]:
    try:
        reconciled = request.app.state.billing_service.reconcile_subscription(subscription_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_reconcile_requested",
        reader_id=reconciled["subscription"].get("account_id"),
        account_id=reconciled["subscription"].get("account_id"),
        payload_json={"subscription_id": subscription_id, "requested_by": payload.requested_by, **reconciled},
    )
    return reconciled


@router.post("/accounts/{account_id}/billing/reconcile")
def reconcile_account_billing(account_id: str, payload: AccountBillingReconcileRequest, request: Request) -> Dict[str, Any]:
    reconciled = request.app.state.billing_service.reconcile_account_billing(
        account_id=account_id,
        provider=payload.provider,
    )
    request.app.state.analytics_service.track(
        "account_billing_reconcile_requested",
        reader_id=account_id,
        account_id=account_id,
        payload_json={"requested_by": payload.requested_by, **reconciled},
    )
    return reconciled


@router.post("/subscriptions/{subscription_id}/retry-payment")
def ops_retry_subscription_payment(subscription_id: str, payload: BillingRetryRequest, request: Request) -> Dict[str, Any]:
    try:
        retried = request.app.state.billing_service.retry_subscription_payment(subscription_id=subscription_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_retry_requested",
        reader_id=retried["event"].get("account_id"),
        account_id=retried["event"].get("account_id"),
        payload_json={"subscription_id": subscription_id, "requested_by": payload.requested_by, **retried},
    )
    return retried


@router.post("/billing-events/{event_id}/replay")
def replay_billing_event(event_id: str, payload: BillingLifecycleReplayRequest, request: Request) -> Dict[str, Any]:
    try:
        replayed = request.app.state.billing_service.replay_lifecycle_event(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "billing_lifecycle_event_replayed",
        reader_id=replayed["event"].get("account_id"),
        account_id=replayed["event"].get("account_id"),
        payload_json={"event_id": event_id, "requested_by": payload.requested_by, **replayed},
    )
    return replayed


@router.post("/wallets/grant")
def grant_wallet(payload: WalletGrantRequest, request: Request) -> Dict[str, Any]:
    entitlement = request.app.state.billing_service.grant_wallet_credits(
        account_id=payload.account_id,
        wallet_type=payload.wallet_type,
        amount=payload.amount,
        tier_id=payload.tier_id,
        expires_at=payload.expires_at,
    )
    request.app.state.analytics_service.track(
        "entitlement_granted",
        reader_id=payload.account_id,
        account_id=payload.account_id,
        access_tier=payload.tier_id,
        payload_json={**entitlement, "reason": payload.reason},
    )
    return {"entitlement": entitlement}


@router.post("/wallets/debit")
def debit_wallet(payload: WalletDebitRequest, request: Request) -> Dict[str, Any]:
    entitlement = request.app.state.billing_service.debit_wallet_credits(
        account_id=payload.account_id,
        wallet_type=payload.wallet_type,
        amount=payload.amount,
    )
    request.app.state.analytics_service.track(
        "entitlement_revoked",
        reader_id=payload.account_id,
        account_id=payload.account_id,
        payload_json={**entitlement, "reason": payload.reason},
    )
    return {"entitlement": entitlement}


@router.post("/entitlements/revoke")
def revoke_entitlement(payload: EntitlementRevokeRequest, request: Request) -> Dict[str, Any]:
    entitlement = request.app.state.billing_service.revoke_entitlement(payload.entitlement_id)
    request.app.state.analytics_service.track(
        "entitlement_revoked",
        reader_id=entitlement.get("reader_id"),
        account_id=entitlement.get("account_id"),
        access_tier=entitlement.get("tier_id"),
        payload_json={**entitlement, "reason": payload.reason},
    )
    return {"entitlement": entitlement}


@router.get("/eval-metrics")
def eval_metrics(
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    metrics = request.app.state.repository.aggregate_eval_metrics(
        world_id=world_id,
        world_version_id=world_version_id,
    )
    learned_bundle = request.app.state.training_signal_service.export_bundle(
        world_version_id=world_version_id,
        dataset_view="evaluator",
    )
    learned_summary = request.app.state.learned_inference_service.summarize_examples(
        learned_bundle.get("evaluator_examples", [])
    )
    learned_shadow_summary = request.app.state.learned_shadow_service.summarize(learned_summary)
    reranker_bundle = request.app.state.training_signal_service.export_bundle(
        world_version_id=world_version_id,
        dataset_view="reranker",
    )
    learned_reranker_shadow_summary = request.app.state.learned_reranker_shadow_service.summarize(
        reranker_bundle
    )
    return {
        **metrics,
        "learned_eval_available": learned_shadow_summary.get("available", False),
        "learned_rule_agreement_rate": learned_shadow_summary.get("agreement_rate"),
        "top_mismatch_worlds": learned_shadow_summary.get("top_mismatch_worlds", []),
        "top_mismatch_issue_codes": learned_shadow_summary.get("top_mismatch_issue_codes", []),
        "learned_evaluation_summary": learned_summary,
        "learned_shadow_summary": learned_shadow_summary,
        "learned_reranker_shadow_summary": learned_reranker_shadow_summary,
    }


@router.get("/eval-metrics/worlds/{world_id}")
def eval_metrics_world_detail(world_id: str, request: Request) -> Dict[str, Any]:
    metrics = request.app.state.repository.aggregate_eval_metrics(world_id=world_id)
    detail = next((item for item in metrics.get("continuation_world_details", []) if item["world_id"] == world_id), None)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown_eval_metrics_world:{world_id}")
    return detail


@router.get("/eval-metrics/world-versions/{world_version_id}")
def eval_metrics_world_version_detail(world_version_id: str, request: Request) -> Dict[str, Any]:
    metrics = request.app.state.repository.aggregate_eval_metrics(world_version_id=world_version_id)
    detail = next(
        (
            item
            for item in metrics.get("continuation_version_details", [])
            if item["world_version_id"] == world_version_id
        ),
        None,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown_eval_metrics_world_version:{world_version_id}")
    return detail


@router.get("/cross-pack-quality")
def cross_pack_quality(
    request: Request,
    validate_strategy_bundle: bool = False,
    strategy_bundle_id: Optional[str] = None,
    weakest_limit: int = 3,
) -> Dict[str, Any]:
    return run_benchmark(
        repository=request.app.state.repository,
        golden_dir=request.app.state.base_dir / "tests" / "golden_routes",
        baseline=json.loads(
            (request.app.state.base_dir / "tests" / "benchmark_baseline.json").read_text(encoding="utf-8")
        ),
        validate_strategy_bundle=validate_strategy_bundle,
        strategy_bundle_id=strategy_bundle_id,
        weakest_limit=weakest_limit,
    )


@router.get("/learned-dashboard")
def learned_dashboard(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    return build_learned_dashboard_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
    )


@router.get("/learned-dashboard/worlds/{world_id}")
def learned_dashboard_world_detail(
    world_id: str,
    request: Request,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    summary = build_learned_dashboard_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
    )
    detail = next((item for item in summary.get("world_details", []) if item["world_id"] == world_id), None)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown_learned_world:{world_id}")
    return detail


@router.get("/learned-dashboard/issues/{issue_code}")
def learned_dashboard_issue_detail(
    issue_code: str,
    request: Request,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    summary = build_learned_dashboard_summary(
        repository=request.app.state.repository,
        world_version_id=world_version_id,
    )
    detail = next((item for item in summary.get("issue_details", []) if item["issue_code"] == issue_code), None)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown_learned_issue:{issue_code}")
    return detail


@router.get("/learned-compare")
def learned_compare(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    return build_learned_compare_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
    )


@router.get("/learned-rollout")
def learned_rollout(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_learned_rollout_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.post("/learned-rollout/{track}/activate")
def activate_rollout(
    track: str,
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        return activate_learned_rollout(
            repository=request.app.state.repository,
            track=track,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/learned-rollout/{track}/rollback")
def rollback_rollout(
    track: str,
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        return rollback_learned_rollout(
            repository=request.app.state.repository,
            track=track,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/worlds/{world_id}/history")
def world_history(world_id: str, request: Request) -> Dict[str, Any]:
    return request.app.state.review_service.world_history(world_id)


@router.post("/review-samples")
def create_review_sample(payload: ReviewSampleRequest, request: Request) -> Dict[str, Any]:
    scoped_world_version_id = payload.world_version_id
    if scoped_world_version_id:
        try:
            request.app.state.repository.get_world_version(scoped_world_version_id)
        except KeyError:
            scoped_world_version_id = None
    before_summary = build_learned_data_ops_summary(
        repository=request.app.state.repository,
        world_id=payload.world_id,
        world_version_id=scoped_world_version_id,
    )
    try:
        sample = request.app.state.training_signal_service.save_review_sample(payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    after_summary = build_learned_data_ops_summary(
        repository=request.app.state.repository,
        world_id=payload.world_id,
        world_version_id=scoped_world_version_id,
    )
    impact_receipt = build_learned_data_impact_receipt(
        before_summary=before_summary,
        after_summary=after_summary,
        review_sample=sample,
    )
    return {"review_sample": sample, "impact_receipt": impact_receipt}


@router.get("/review-samples")
def list_review_samples(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    since: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "review_samples": request.app.state.training_signal_service.list_review_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            reviewer_id=reviewer_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
    }


@router.post("/preference-samples")
def create_preference_sample(payload: PreferenceSampleRequest, request: Request) -> Dict[str, Any]:
    try:
        sample = request.app.state.training_signal_service.save_preference_sample(payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"preference_sample": sample}


@router.get("/preference-samples")
def list_preference_samples(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    since: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "preference_samples": request.app.state.training_signal_service.list_preference_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            reviewer_id=reviewer_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
    }


@router.post("/ranking-samples")
def create_ranking_sample(payload: RankingSampleRequest, request: Request) -> Dict[str, Any]:
    try:
        sample = request.app.state.training_signal_service.save_ranking_sample(payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ranking_sample": sample}


@router.get("/ranking-samples")
def list_ranking_samples(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    since: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "ranking_samples": request.app.state.training_signal_service.list_ranking_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            reviewer_id=reviewer_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
    }


@router.get("/review-sample-backlog")
def review_sample_backlog(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    summary = build_learned_data_ops_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )
    return {"backlog": summary["review_sample_backlog"]}


@router.get("/longform-250-human-review-closeout")
def longform_250_human_review_closeout(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return request.app.state.training_signal_service.longform_250_human_review_closeout(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/longform-500-human-review-closeout")
def longform_500_human_review_closeout(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return request.app.state.training_signal_service.longform_500_human_review_closeout(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/longform-1000-human-review-closeout")
def longform_1000_human_review_closeout(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return request.app.state.training_signal_service.longform_1000_human_review_closeout(
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/issue-fix-pair-backlog")
def issue_fix_pair_backlog(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    summary = build_learned_data_ops_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )
    return {"backlog": summary["pair_coverage_backlog"]}


@router.get("/issue-fix-pairs")
def list_issue_fix_pairs(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    since: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "issue_fix_pairs": request.app.state.training_signal_service.issue_fix_pairs(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
    }


@router.get("/learned-data-ops")
def learned_data_ops(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_learned_data_ops_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/learned-review-quality")
def learned_review_quality(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_learned_review_quality_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/learned-review-quality/worlds/{world_id}")
def learned_review_quality_world_detail(
    world_id: str,
    request: Request,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        return build_learned_review_quality_world_detail(
            repository=request.app.state.repository,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/learned-impact")
def learned_impact(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        return build_learned_impact_summary(
            repository=request.app.state.repository,
            world_id=world_id,
            world_version_id=world_version_id,
            track=track,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-impact/worlds/{world_id}")
def learned_impact_world_detail(
    world_id: str,
    request: Request,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        return build_learned_impact_world_detail(
            repository=request.app.state.repository,
            world_id=world_id,
            world_version_id=world_version_id,
            track=track,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-impact/issues/{issue_code}")
def learned_impact_issue_detail(
    issue_code: str,
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    track: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        return build_learned_impact_issue_detail(
            repository=request.app.state.repository,
            issue_code=issue_code,
            world_id=world_id,
            world_version_id=world_version_id,
            track=track,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-assisted-gate")
def learned_assisted_gate(
    request: Request,
    limit: int = 20,
) -> Dict[str, Any]:
    return build_assisted_gate_summary(
        repository=request.app.state.repository,
        limit=limit,
    )


@router.post("/learned-assisted-gate/configure")
def configure_learned_assisted_gate(
    payload: LearnedAssistedGateConfigRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        save_assisted_gate_config(
            repository=request.app.state.repository,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
            enabled=payload.enabled,
            mode=payload.mode,
            bucket_percentage=payload.bucket_percentage,
            confidence_threshold=payload.confidence_threshold,
            min_example_count=payload.min_example_count,
            min_high_confidence_blocks=payload.min_high_confidence_blocks,
            required_block_share=payload.required_block_share,
            world_allowlist=payload.world_allowlist,
        )
        return build_assisted_gate_summary(
            repository=request.app.state.repository,
            limit=20,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-assisted-rerank")
def learned_assisted_rerank(
    request: Request,
    limit: int = 20,
) -> Dict[str, Any]:
    return build_assisted_rerank_summary(
        repository=request.app.state.repository,
        limit=limit,
    )


@router.post("/learned-assisted-rerank/configure")
def configure_learned_assisted_rerank(
    payload: LearnedAssistedRerankConfigRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        save_assisted_rerank_config(
            repository=request.app.state.repository,
            reviewer_id=payload.reviewer_id,
            reason=payload.reason,
            enabled=payload.enabled,
            mode=payload.mode,
            bucket_percentage=payload.bucket_percentage,
            confidence_threshold=payload.confidence_threshold,
            candidate_window=payload.candidate_window,
            max_score_gap=payload.max_score_gap,
            world_allowlist=payload.world_allowlist,
        )
        return build_assisted_rerank_summary(
            repository=request.app.state.repository,
            limit=20,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-cadence")
def learned_cadence(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_learned_cadence_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/learned-cadence/{track}")
def learned_cadence_track_detail(
    track: str,
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        return build_learned_cadence_track_detail(
            repository=request.app.state.repository,
            track=track,
            world_id=world_id,
            world_version_id=world_version_id,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/learned-promotion")
def learned_promotion(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_evaluator_promotion_workflow_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.get("/learned-reranker-promotion")
def learned_reranker_promotion(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    return build_reranker_promotion_workflow_summary(
        repository=request.app.state.repository,
        world_id=world_id,
        world_version_id=world_version_id,
        limit=limit,
    )


@router.post("/learned-promotion/approve")
def approve_learned_promotion(
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    summary = build_evaluator_promotion_workflow_summary(repository=request.app.state.repository)
    save_evaluator_promotion_decision(
        repository=request.app.state.repository,
        reviewer_id=payload.reviewer_id,
        reason=payload.reason,
        status="approved",
        recommendation_summary=summary,
    )
    return build_evaluator_promotion_workflow_summary(repository=request.app.state.repository)


@router.post("/learned-promotion/revoke")
def revoke_learned_promotion(
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    summary = build_evaluator_promotion_workflow_summary(repository=request.app.state.repository)
    save_evaluator_promotion_decision(
        repository=request.app.state.repository,
        reviewer_id=payload.reviewer_id,
        reason=payload.reason,
        status="revoked",
        recommendation_summary=summary,
    )
    return build_evaluator_promotion_workflow_summary(repository=request.app.state.repository)


@router.post("/learned-reranker-promotion/approve")
def approve_learned_reranker_promotion(
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    summary = build_reranker_promotion_workflow_summary(repository=request.app.state.repository)
    save_reranker_promotion_decision(
        repository=request.app.state.repository,
        reviewer_id=payload.reviewer_id,
        reason=payload.reason,
        status="approved",
        recommendation_summary=summary,
    )
    return build_reranker_promotion_workflow_summary(repository=request.app.state.repository)


@router.post("/learned-reranker-promotion/revoke")
def revoke_learned_reranker_promotion(
    payload: LearnedPromotionDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    summary = build_reranker_promotion_workflow_summary(repository=request.app.state.repository)
    save_reranker_promotion_decision(
        repository=request.app.state.repository,
        reviewer_id=payload.reviewer_id,
        reason=payload.reason,
        status="revoked",
        recommendation_summary=summary,
    )
    return build_reranker_promotion_workflow_summary(repository=request.app.state.repository)


@router.get("/export/training-signal")
def export_training_signal(
    request: Request,
    world_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    since: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    include_inferred: bool = True,
    include_fix_pairs: bool = True,
    dataset_view: str = "raw",
) -> Dict[str, Any]:
    try:
        return request.app.state.training_signal_service.export_bundle(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
            include_inferred=include_inferred,
            include_fix_pairs=include_fix_pairs,
            dataset_view=dataset_view,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
