from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .reader_access import ensure_reader_session_access, reader_identity
from ..services.reader_generation_jobs import READER_GENERATION_JOB_TYPE
from ..services.sessions import build_reader_continuity_contract


class CreateReaderSessionRequest(BaseModel):
    world_id: str
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    longform_setup: Optional[Dict[str, Any]] = None


class ContinueReaderRequest(BaseModel):
    session_id: str
    choice_id: Optional[str] = None
    freeform_intent: Optional[str] = None
    steering_directive: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None
    reader_id: Optional[str] = None


class GrantEntitlementRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    entitlement_type: str
    tier_id: Optional[str] = None
    wallet_type: Optional[str] = None
    world_id: Optional[str] = None
    balance: Optional[float] = None
    expires_at: Optional[str] = None


class StartCheckoutRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    tier_id: str
    provider: Optional[str] = None


class CheckoutWebhookRequest(BaseModel):
    provider: str = "web_stub"
    provider_event_id: str
    event_type: str
    account_id: Optional[str] = None
    subscription_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    occurred_at: Optional[str] = None


class PortalSessionRequest(BaseModel):
    return_url: Optional[str] = None


class CompleteCheckoutSessionRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None


class AppleMobilePurchaseVerifyRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    original_transaction_id: Optional[str] = None
    signed_transaction_info: Optional[str] = None
    tier_id: Optional[str] = None
    environment: Optional[str] = None


class GoogleMobilePurchaseVerifyRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    purchase_token: str
    subscription_id: Optional[str] = None
    package_name: Optional[str] = None
    tier_id: Optional[str] = None
    environment: Optional[str] = None


class MobilePurchaseRestoreRequest(BaseModel):
    account_id: Optional[str] = None
    reader_id: Optional[str] = None
    apple_original_transaction_ids: list[str] = []
    apple_tier_id: Optional[str] = None
    apple_environment: Optional[str] = None
    google_purchase_tokens: list[str] = []
    google_subscription_id: Optional[str] = None
    google_tier_id: Optional[str] = None
    google_environment: Optional[str] = None
    package_name: Optional[str] = None


class AppleServerNotificationRequest(BaseModel):
    account_id: Optional[str] = None
    signedPayload: Optional[str] = None
    notificationType: Optional[str] = None
    data: Dict[str, Any] = {}


class GoogleRTDNRequest(BaseModel):
    account_id: Optional[str] = None
    packageName: Optional[str] = None
    message: Dict[str, Any] = {}
    subscriptionNotification: Dict[str, Any] = {}


class QualityFeedbackRequest(BaseModel):
    trace_id: str
    feedback: str
    reason_code: Optional[str] = None
    note: Optional[str] = None
    quality_event_id: Optional[str] = None


router = APIRouter(prefix="/v1/reader", tags=["reader"])


def _reader_identity(request: Request) -> Optional[Dict[str, Any]]:
    return reader_identity(request)


def _resolve_reader_account_id(
    request: Request,
    *,
    account_id: Optional[str] = None,
    reader_id: Optional[str] = None,
) -> str:
    identity = _reader_identity(request)
    if identity:
        token_account_id = str(identity.get("account_id") or identity.get("actor_id") or "")
        provided = next((str(value) for value in [account_id, reader_id] if str(value or "").strip()), None)
        if provided and token_account_id and provided != token_account_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "reader_account_ownership_mismatch",
                    "provided_account_id": provided,
                    "token_account_id": token_account_id,
                },
            )
        return token_account_id
    return request.app.state.billing_service.resolve_account_id(account_id=account_id, reader_id=reader_id)


def _reader_generation_scheduler(request: Request):
    return getattr(request.app.state, "reader_generation_job_scheduler", None)


def _reader_generation_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job.get("payload") or {})
    result_summary = dict(job.get("result_summary") or {})
    return {
        "jobId": job.get("job_id"),
        "jobType": job.get("job_type"),
        "operation": payload.get("operation") or result_summary.get("operation"),
        "status": job.get("status"),
        "sessionId": payload.get("session_id") or result_summary.get("session_id"),
        "readerStatus": result_summary.get("reader_status"),
        "pollAfterMs": 1000 if job.get("status") in {"queued", "running"} else 0,
        "retryable": job.get("status") in {"queued", "failed"} or job.get("lease_status") == "expired",
        "result": result_summary if job.get("status") == "succeeded" else None,
        "error": job.get("error"),
        "createdAt": job.get("created_at"),
        "updatedAt": job.get("updated_at"),
        "startedAt": job.get("started_at"),
        "finishedAt": job.get("finished_at"),
        "attemptCount": job.get("attempt_count", 0),
    }


def _ensure_reader_generation_job_access(request: Request, job_id: str) -> Dict[str, Any]:
    try:
        job = request.app.state.async_job_service.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if str(job.get("job_type") or "") != READER_GENERATION_JOB_TYPE:
        raise HTTPException(status_code=404, detail=f"unknown_reader_generation_job:{job_id}")
    session_id = str((job.get("payload") or {}).get("session_id") or (job.get("result_summary") or {}).get("session_id") or "")
    if session_id:
        ensure_reader_session_access(request, session_id=session_id)
    return job


@router.get("/library/worlds")
def library_worlds(request: Request) -> Dict[str, Any]:
    return {"worlds": request.app.state.repository.list_worlds()}


@router.get("/library/worlds/{world_id}")
def world_detail(world_id: str, request: Request) -> Dict[str, Any]:
    versions = request.app.state.repository.list_world_versions(world_id=world_id)
    if not versions:
        raise HTTPException(status_code=404, detail="unknown_world:%s" % world_id)
    published = next((item for item in versions if item["status"] == "published"), versions[0])
    version = request.app.state.repository.get_world_version(published["world_version_id"])
    return {
        "world_id": world_id,
        "title": version.worldpack_json.get("title", world_id),
        "world_version_id": version.world_version_id,
        "manifest": version.manifest_json,
        "risk_policy": version.worldpack_json.get("risk_policy", {}),
        "worldpack": version.worldpack_json,
        "versions": versions,
    }


@router.post("/sessions")
def create_reader_session(payload: CreateReaderSessionRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.session_service.create_session(
            payload.world_id,
            reader_id=_resolve_reader_account_id(request, account_id=payload.account_id, reader_id=payload.reader_id),
            longform_setup=payload.longform_setup,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/continue")
def continue_reader_story(payload: ContinueReaderRequest, request: Request) -> Dict[str, Any]:
    try:
        ensure_reader_session_access(request, session_id=payload.session_id)
        reader_id = _resolve_reader_account_id(request, account_id=payload.account_id, reader_id=payload.reader_id)
        access = request.app.state.billing_service.access_check(payload.session_id, reader_id=reader_id, account_id=reader_id)
        if access.get("required"):
            return {
                "session_id": payload.session_id,
                "status": "payment_required",
                "paywall": access,
                "continuity_contract": build_reader_continuity_contract(
                    status="payment_required",
                    session_id=payload.session_id,
                    paywall=access,
                ),
            }
        job = request.app.state.async_job_service.enqueue_job(
            job_type=READER_GENERATION_JOB_TYPE,
            payload={
                "operation": "reader_continue",
                "session_id": payload.session_id,
                "choice_id": payload.choice_id,
                "freeform_intent": payload.freeform_intent,
                "steering_directive": payload.steering_directive,
                "reader_id": reader_id,
                "account_id": reader_id,
            },
            requested_by=reader_id or "reader_guest",
            account_id=reader_id,
            schedule=_reader_generation_scheduler(request),
        )
        return {"status": "queued", "job": _reader_generation_job_payload(job)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/jobs/{job_id}")
def reader_generation_job_status(job_id: str, request: Request) -> Dict[str, Any]:
    job = _ensure_reader_generation_job_access(request, job_id)
    return {"job": _reader_generation_job_payload(job)}


@router.post("/jobs/{job_id}/resume")
def reader_generation_job_resume(job_id: str, request: Request) -> Dict[str, Any]:
    job = _ensure_reader_generation_job_access(request, job_id)
    job_status = str(job.get("status") or "")
    if job_status == "succeeded":
        return {"job": _reader_generation_job_payload(job)}
    if job_status == "running" and job.get("lease_status") != "expired":
        return {"job": _reader_generation_job_payload(job)}
    requested_by = str((reader_identity(request) or {}).get("account_id") or job.get("requested_by") or "reader")
    try:
        request.app.state.async_job_service.resume_job(
            job_id,
            requested_by=requested_by,
            force=job_status != "queued",
            schedule=None,
        )
        resumed = request.app.state.async_job_service.run_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"job": _reader_generation_job_payload(resumed)}


@router.get("/entitlements")
def reader_entitlements(
    reader_id: Optional[str] = None,
    account_id: Optional[str] = None,
    world_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=reader_id)
    return request.app.state.billing_service.list_entitlements_for_account(resolved_account_id, world_id=world_id)


@router.get("/subscription")
def reader_subscription(
    reader_id: Optional[str] = None,
    account_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=reader_id)
    return request.app.state.billing_service.subscription_status(account_id=resolved_account_id)


@router.post("/entitlements/grant")
def grant_reader_entitlement(payload: GrantEntitlementRequest, request: Request) -> Dict[str, Any]:
    try:
        entitlement = request.app.state.billing_service.grant_entitlement(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    world_version_id = None
    if entitlement.get("world_id"):
        world_card = next(
            (item for item in request.app.state.repository.list_worlds() if item["world_id"] == entitlement["world_id"]),
            None,
        )
        world_version_id = world_card["latest_version"] if world_card else None
    request.app.state.analytics_service.track(
        "entitlement_granted",
        reader_id=entitlement.get("reader_id"),
        account_id=entitlement.get("account_id"),
        world_id=entitlement.get("world_id"),
        world_version_id=world_version_id,
        access_tier=entitlement.get("tier_id") or entitlement.get("entitlement_type"),
        payload_json={
            "entitlement_id": entitlement.get("entitlement_id"),
            "entitlement_type": entitlement.get("entitlement_type"),
            "wallet_type": entitlement.get("wallet_type"),
            "tier_id": entitlement.get("tier_id"),
            "status": entitlement.get("status"),
            "balance": entitlement.get("balance"),
            "reason": entitlement.get("reason"),
            "expires_at": entitlement.get("expires_at"),
        },
    )
    return {"entitlement": entitlement}


@router.post("/checkout/start")
def start_checkout(payload: StartCheckoutRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(
        request,
        account_id=payload.account_id,
        reader_id=payload.reader_id,
    )
    try:
        checkout = request.app.state.billing_service.start_checkout(
            account_id=resolved_account_id,
            tier_id=payload.tier_id,
            provider=payload.provider,
            customer_email=(payload.reader_id if payload.reader_id and "@" in payload.reader_id else None),
            metadata={"reader_id": payload.reader_id or resolved_account_id},
        )
    except ValueError as exc:
        if str(exc) == "checkout_restricted":
            raise HTTPException(status_code=403, detail={"code": "checkout_restricted", "account_id": resolved_account_id})
        if str(exc) == "checkout_invite_required":
            raise HTTPException(status_code=403, detail={"code": "checkout_invite_required", "account_id": resolved_account_id})
        if str(exc) == "email_verification_required_for_billing":
            raise HTTPException(status_code=403, detail={"code": "email_verification_required_for_billing", "account_id": resolved_account_id})
        if str(exc) in {"stripe_not_configured", "stripe_sdk_missing"}:
            raise HTTPException(status_code=503, detail={"code": str(exc), "account_id": resolved_account_id})
        raise HTTPException(status_code=400, detail=str(exc))
    request.app.state.analytics_service.track(
        "checkout_started",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        access_tier=payload.tier_id,
        payload_json=checkout,
    )
    return {"checkout": checkout}


@router.post("/checkout/{checkout_session_id}/complete")
def complete_checkout_session(
    checkout_session_id: str,
    payload: CompleteCheckoutSessionRequest,
    request: Request,
) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(
        request,
        account_id=payload.account_id,
        reader_id=payload.reader_id,
    )
    try:
        completed = request.app.state.billing_service.complete_checkout_session(
            checkout_session_id=checkout_session_id,
            account_id=resolved_account_id or None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "checkout_completion_reconciled",
        reader_id=completed.get("account_id"),
        account_id=completed.get("account_id"),
        access_tier=(completed.get("subscription") or {}).get("tier_id") or (completed.get("checkout") or {}).get("tier_id"),
        payload_json={
            "checkout_session_id": checkout_session_id,
            "customer_id": completed.get("customer_id"),
            "remote_checkout_status": completed.get("remote_checkout_status"),
            "subscription_id": (completed.get("subscription") or {}).get("subscription_id"),
        },
    )
    return completed


@router.post("/subscription/{account_id}/portal")
def reader_customer_portal(account_id: str, payload: PortalSessionRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=account_id)
    try:
        portal = request.app.state.billing_service.start_customer_portal(
            account_id=resolved_account_id,
            return_url=payload.return_url,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "customer_portal_unavailable", "reason": str(exc)}) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    return {"portal": portal}


@router.post("/checkout/stripe-webhook")
async def reader_stripe_checkout_webhook(request: Request) -> Dict[str, Any]:
    signature = request.headers.get("Stripe-Signature") or ""
    raw_body = await request.body()
    try:
        processed = request.app.state.billing_service.ingest_stripe_webhook(raw_body=raw_body, signature=signature)
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_webhook_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    payload = dict(processed.get("event") or {})
    request.app.state.analytics_service.track(
        "billing_lifecycle_event_processed",
        reader_id=payload.get("account_id"),
        account_id=payload.get("account_id"),
        payload_json={
            "event_id": payload.get("event_id"),
            "event_type": payload.get("event_type"),
            "provider": payload.get("provider"),
            "status": payload.get("status"),
            "stripe_event_type": processed.get("stripe_event_type"),
        },
    )
    return processed


@router.post("/mobile-purchases/apple/verify")
def verify_apple_mobile_purchase(payload: AppleMobilePurchaseVerifyRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=payload.account_id, reader_id=payload.reader_id)
    try:
        verified = request.app.state.billing_service.verify_mobile_purchase(
            provider="app_store",
            account_id=resolved_account_id,
            payload=payload.model_dump(),
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"email_verification_required_for_billing"}:
            status_code = 403
        if reason in {"app_store_not_configured", "unsupported_mobile_purchase_provider"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "mobile_purchase_verified",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        access_tier=(verified.get("effective_subscription") or {}).get("tier_id"),
        payload_json={"provider": "app_store", **verified},
    )
    return verified


@router.post("/mobile-purchases/google/verify")
def verify_google_mobile_purchase(payload: GoogleMobilePurchaseVerifyRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=payload.account_id, reader_id=payload.reader_id)
    try:
        verified = request.app.state.billing_service.verify_mobile_purchase(
            provider="google_play",
            account_id=resolved_account_id,
            payload=payload.model_dump(),
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"email_verification_required_for_billing"}:
            status_code = 403
        if reason in {"google_play_not_configured", "unsupported_mobile_purchase_provider"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "mobile_purchase_verified",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        access_tier=(verified.get("effective_subscription") or {}).get("tier_id"),
        payload_json={"provider": "google_play", **verified},
    )
    return verified


@router.post("/mobile-purchases/restore")
def restore_mobile_purchases(payload: MobilePurchaseRestoreRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=payload.account_id, reader_id=payload.reader_id)
    try:
        restored = request.app.state.billing_service.restore_mobile_purchases(
            account_id=resolved_account_id,
            payload=payload.model_dump(),
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"email_verification_required_for_billing"}:
            status_code = 403
        if reason in {"app_store_not_configured", "google_play_not_configured"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "mobile_purchase_restore",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        access_tier=restored.get("effective_tier"),
        payload_json=restored,
    )
    return restored


@router.post("/billing/apple-server-notifications")
def apple_server_notifications(payload: AppleServerNotificationRequest, request: Request) -> Dict[str, Any]:
    try:
        processed = request.app.state.billing_service.ingest_store_notification(
            provider="app_store",
            payload=payload.model_dump(),
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"app_store_not_configured"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "store_notification_processed",
        reader_id=processed.get("account_id"),
        account_id=processed.get("account_id"),
        access_tier=(processed.get("effective_subscription") or {}).get("tier_id"),
        payload_json={"provider": "app_store", **processed},
    )
    return processed


@router.post("/billing/google-rtdn")
def google_rtdn(payload: GoogleRTDNRequest, request: Request) -> Dict[str, Any]:
    try:
        processed = request.app.state.billing_service.ingest_store_notification(
            provider="google_play",
            payload=payload.model_dump(),
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"google_play_not_configured"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": reason}) from exc
    request.app.state.analytics_service.track(
        "store_notification_processed",
        reader_id=processed.get("account_id"),
        account_id=processed.get("account_id"),
        access_tier=(processed.get("effective_subscription") or {}).get("tier_id"),
        payload_json={"provider": "google_play", **processed},
    )
    return processed


@router.post("/checkout/webhook")
def reader_checkout_webhook(payload: CheckoutWebhookRequest, request: Request) -> Dict[str, Any]:
    try:
        processed = request.app.state.billing_service.ingest_checkout_webhook(payload.model_dump())
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "billing_lifecycle_event_processed",
        reader_id=payload.account_id,
        account_id=payload.account_id,
        payload_json={
            "event_id": processed["event"]["event_id"],
            "event_type": processed["event"]["event_type"],
            "provider": processed["event"]["provider"],
            "status": processed["event"]["status"],
        },
    )
    return processed


@router.post("/subscription/{account_id}/retry-payment")
def reader_retry_subscription_payment(account_id: str, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=account_id)
    try:
        payload = request.app.state.billing_service.retry_subscription_payment(account_id=resolved_account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_retry_requested",
        reader_id=account_id,
        account_id=account_id,
        payload_json=payload,
    )
    try:
        request.app.state.repository.save_quality_feedback_item(
            {
                "feedback_type": "subscription_retry_requested",
                "signal": "retry",
                "source_surface": "reader",
                "account_id": resolved_account_id,
                "world_version_id": None,
                "session_id": None,
                "chapter_id": None,
                "source_ref": {"kind": "account", "account_id": resolved_account_id},
                "payload": payload,
            }
        )
    except Exception:
        pass
    return payload


@router.post("/quality-feedback")
def submit_reader_quality_feedback(payload: QualityFeedbackRequest, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=None, reader_id=None)
    signal = "explicit_positive" if payload.feedback == "thumbs_up" else "explicit_negative"
    item = request.app.state.repository.save_quality_feedback_item(
        {
            "trace_id": payload.trace_id,
            "source_event_id": payload.quality_event_id,
            "feedback_type": "explicit_user_feedback",
            "signal": signal,
            "source_surface": "reader",
            "account_id": resolved_account_id,
            "world_version_id": None,
            "session_id": None,
            "chapter_id": None,
            "source_ref": {"kind": "trace", "trace_id": payload.trace_id, "account_id": resolved_account_id},
            "payload": {
                "feedback": payload.feedback,
                "reason_code": payload.reason_code,
                "note": payload.note,
            },
        }
    )
    request.app.state.analytics_service.track(
        "reader_quality_feedback_submitted",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        payload_json=item,
    )
    return {"quality_feedback": item}


@router.post("/subscription/{account_id}/renew")
def reader_renew_subscription(account_id: str, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=account_id)
    try:
        payload = request.app.state.billing_service.renew_subscription(account_id=resolved_account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_renew_requested",
        reader_id=account_id,
        account_id=account_id,
        payload_json=payload,
    )
    return payload


@router.post("/subscription/{account_id}/cancel")
def reader_cancel_subscription(account_id: str, request: Request) -> Dict[str, Any]:
    resolved_account_id = _resolve_reader_account_id(request, account_id=account_id, reader_id=account_id)
    try:
        payload = request.app.state.billing_service.cancel_subscription(account_id=resolved_account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_cancel_requested",
        reader_id=account_id,
        account_id=account_id,
        payload_json=payload,
    )
    return payload


@router.get("/sessions/{session_id}/replay")
def reader_replay(
    session_id: str,
    request: Request,
    start_chapter: Optional[int] = None,
    end_chapter: Optional[int] = None,
    limit: Optional[int] = None,
    latest: bool = False,
) -> Dict[str, Any]:
    try:
        ensure_reader_session_access(request, session_id=session_id)
        return request.app.state.repository.get_replay(
            session_id,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            limit=limit,
            latest=latest,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}/prefill")
def reader_prefill(session_id: str, request: Request) -> Dict[str, Any]:
    try:
        session_record = ensure_reader_session_access(request, session_id=session_id)
        latest_step = request.app.state.repository.get_latest_step(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return request.app.state.intent_prefill_service.build(session_record, latest_step).to_dict()


@router.get("/sessions/{session_id}/quote")
def reader_quote(session_id: str, request: Request) -> Dict[str, Any]:
    try:
        ensure_reader_session_access(request, session_id=session_id)
        return request.app.state.billing_service.quote_continue(session_id, "continue")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
