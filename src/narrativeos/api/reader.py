from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.sessions import ReaderContinueCommand


class CreateReaderSessionRequest(BaseModel):
    world_id: str
    account_id: Optional[str] = None
    reader_id: Optional[str] = None


class ContinueReaderRequest(BaseModel):
    session_id: str
    choice_id: Optional[str] = None
    freeform_intent: Optional[str] = None
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
    provider: str = "web_stub"


class CheckoutWebhookRequest(BaseModel):
    provider: str = "web_stub"
    provider_event_id: str
    event_type: str
    account_id: Optional[str] = None
    subscription_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    occurred_at: Optional[str] = None


router = APIRouter(prefix="/v1/reader", tags=["reader"])


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
            reader_id=payload.reader_id or payload.account_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/continue")
def continue_reader_story(payload: ContinueReaderRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.session_service.continue_story(
            ReaderContinueCommand(
                session_id=payload.session_id,
                choice_id=payload.choice_id,
                freeform_intent=payload.freeform_intent,
            ),
            reader_id=payload.reader_id or payload.account_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/entitlements")
def reader_entitlements(
    reader_id: Optional[str] = None,
    account_id: Optional[str] = None,
    world_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    resolved_account_id = request.app.state.billing_service.resolve_account_id(account_id=account_id, reader_id=reader_id)
    return request.app.state.billing_service.list_entitlements_for_account(resolved_account_id, world_id=world_id)


@router.get("/subscription")
def reader_subscription(
    reader_id: Optional[str] = None,
    account_id: Optional[str] = None,
    request: Request = None,
) -> Dict[str, Any]:
    resolved_account_id = request.app.state.billing_service.resolve_account_id(account_id=account_id, reader_id=reader_id)
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
    resolved_account_id = request.app.state.billing_service.resolve_account_id(
        account_id=payload.account_id,
        reader_id=payload.reader_id,
    )
    try:
        checkout = request.app.state.billing_service.start_checkout(
            account_id=resolved_account_id,
            tier_id=payload.tier_id,
            provider=payload.provider,
        )
    except ValueError as exc:
        if str(exc) == "checkout_restricted":
            raise HTTPException(status_code=403, detail={"code": "checkout_restricted", "account_id": resolved_account_id})
        raise HTTPException(status_code=400, detail=str(exc))
    request.app.state.analytics_service.track(
        "checkout_started",
        reader_id=resolved_account_id,
        account_id=resolved_account_id,
        access_tier=payload.tier_id,
        payload_json=checkout,
    )
    return {"checkout": checkout}


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
    try:
        payload = request.app.state.billing_service.retry_subscription_payment(account_id=account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    request.app.state.analytics_service.track(
        "subscription_retry_requested",
        reader_id=account_id,
        account_id=account_id,
        payload_json=payload,
    )
    return payload


@router.post("/subscription/{account_id}/renew")
def reader_renew_subscription(account_id: str, request: Request) -> Dict[str, Any]:
    try:
        payload = request.app.state.billing_service.renew_subscription(account_id=account_id)
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
    try:
        payload = request.app.state.billing_service.cancel_subscription(account_id=account_id)
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
def reader_replay(session_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.repository.get_replay(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}/prefill")
def reader_prefill(session_id: str, request: Request) -> Dict[str, Any]:
    try:
        session_record = request.app.state.repository.get_session(session_id)
        latest_step = request.app.state.repository.get_latest_step(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return request.app.state.intent_prefill_service.build(session_record, latest_step).to_dict()


@router.get("/sessions/{session_id}/quote")
def reader_quote(session_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.billing_service.quote_continue(session_id, "continue")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
