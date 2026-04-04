from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from ..benchmark.runner import run_benchmark
from ..persistence.migrations import inspect_schema_lifecycle
from ..eval.learned_compare import build_learned_compare_summary
from ..eval.learned_data_impact import build_learned_data_impact_receipt
from ..eval.learned_data_ops import build_learned_data_ops_summary
from ..eval.learned_dashboard import build_learned_dashboard_summary
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


class LearnedPromotionDecisionRequest(BaseModel):
    reviewer_id: str
    reason: str


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


class InvestigationRequest(BaseModel):
    limit: int = 50


class AlertStatusRequest(BaseModel):
    account_id: Optional[str] = None
    status: str
    reviewer_id: Optional[str] = None
    note: Optional[str] = None


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
ACTOR_ID_HEADER = "X-NarrativeOS-Actor-Id"
ACTOR_ROLE_HEADER = "X-NarrativeOS-Actor-Role"
ACCOUNT_ID_HEADER = "X-NarrativeOS-Account-Id"


def _ops_request_identity(request: Request) -> Dict[str, Optional[str]]:
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
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
    actor_id = request.headers.get(ACTOR_ID_HEADER)
    actor_role = request.headers.get(ACTOR_ROLE_HEADER)
    account_id = request.headers.get(ACCOUNT_ID_HEADER)
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
    if not actor["actor_id"]:
        raise HTTPException(status_code=403, detail={"code": "ops_actor_missing", "reason": "reviewer_identity_required"})
    if actor["actor_role"] not in {"reviewer", "ops"}:
        raise HTTPException(status_code=403, detail={"code": "ops_actor_forbidden", "reason": "reviewer_or_ops_required"})
    return actor


@router.get("/review-queue")
def review_queue(request: Request) -> Dict[str, Any]:
    return {"reviews": request.app.state.review_service.queue()}


@router.get("/worlds/{world_id}/status")
def world_status(world_id: str, request: Request) -> Dict[str, Any]:
    payload = request.app.state.review_service.world_status(world_id)
    payload["learned_shadow_summary"] = request.app.state.learned_shadow_service.summarize(
        payload.get("latest_simulation", {}).get("learned_evaluation_summary", {})
    )
    reranker_bundle = request.app.state.training_signal_service.export_bundle(
        world_id=world_id,
        dataset_view="reranker",
    )
    payload["learned_reranker_shadow_summary"] = request.app.state.learned_reranker_shadow_service.summarize(
        reranker_bundle
    )
    return payload


@router.get("/worlds/{world_id}/release-workspace")
def world_release_workspace(world_id: str, request: Request, limit: int = 12) -> Dict[str, Any]:
    try:
        return request.app.state.ops_release_workspace_service.world_release_workspace(world_id=world_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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
    try:
        detail = request.app.state.ops_alerting_service.update_alert_status(
            alert_id,
            status=payload.status,
            reviewer_id=payload.reviewer_id,
            note=payload.note,
            account_id=payload.account_id,
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


@router.post("/governance/cases")
def create_governance_case(payload: GovernanceCaseRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.create_case(
            _apply_ops_identity(request, payload.model_dump())
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
            due_at=payload.due_at,
            note=payload.note,
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
            title=payload.title,
            preview=payload.preview,
            ref_id=payload.ref_id,
            kind=payload.kind,
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
    _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.apply_restriction(
            _apply_ops_identity(request, payload.model_dump())
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
            release_reason=payload.release_reason,
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


@router.post("/governance/cases/{case_id}/status")
def update_governance_case_status(case_id: str, payload: GovernanceCaseStatusRequest, request: Request) -> Dict[str, Any]:
    actor = _require_ops_reviewer(request, payload.reviewer_id)
    try:
        case = request.app.state.governance_service.update_case_status(
            case_id,
            status=payload.status,
            reviewer_id=actor["actor_id"],
            resolution_notes=payload.resolution_notes,
            disposition=payload.disposition,
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
def cross_pack_quality(request: Request) -> Dict[str, Any]:
    return run_benchmark(
        repository=request.app.state.repository,
        golden_dir=request.app.state.base_dir / "tests" / "golden_routes",
        baseline=json.loads(
            (request.app.state.base_dir / "tests" / "benchmark_baseline.json").read_text(encoding="utf-8")
        ),
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
