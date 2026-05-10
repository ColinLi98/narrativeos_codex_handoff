from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..services.auth import AuthServiceError


class AuthRegisterRequest(BaseModel):
    actor_id: str
    actor_role: str = "author"
    password: str
    account_id: Optional[str] = None
    display_name: Optional[str] = None


class AuthLoginRequest(BaseModel):
    actor_id: str
    password: str


class AuthRefreshRequest(BaseModel):
    refresh_token: str


class AuthProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email_address: Optional[str] = None


class AuthPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class AuthEmailChangeRequest(BaseModel):
    new_email: str
    current_password: str


class AuthVerificationRequest(BaseModel):
    actor_id: Optional[str] = None


class AuthVerificationConfirmRequest(BaseModel):
    token: str


class AuthPasswordResetRequest(BaseModel):
    actor_id: str


class AuthPasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class AdminViewBridgeRequest(BaseModel):
    workspace: str = "review"
    account_id: Optional[str] = None
    world_id: Optional[str] = None
    world_version_id: Optional[str] = None
    case_id: Optional[str] = None
    alert_id: Optional[str] = None


class AdminViewSessionBridgeRequest(AdminViewBridgeRequest):
    actor_id: str
    password: str


class AdminViewBridgeResolveRequest(BaseModel):
    token: str


router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _request_token(request: Request) -> str:
    token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not token:
        raise HTTPException(status_code=401, detail={"code": "missing_bearer_token"})
    return token


def _raise_auth_service_error(exc: AuthServiceError) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.detail()) from exc


def _auth_identifier_from_request(request: Request, *, raw_identifier: str) -> str:
    try:
        return request.app.state.auth_service.resolve_actor_id_from_identifier(raw_identifier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_identifier_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


def _auth_export_payload(request: Request, *, identity: Dict[str, Any]) -> Dict[str, Any]:
    account_id = str(identity.get("account_id") or identity.get("actor_id") or "")
    security = {
        "email_address": identity.get("email_address"),
        "pending_email_address": identity.get("pending_email_address"),
        "avatar_url": identity.get("avatar_url"),
        "email_verified": bool(identity.get("email_verified")),
        "verification_required": bool(identity.get("verification_required")),
        "verification_sent_at": identity.get("verification_sent_at"),
        "verified_at": identity.get("verified_at"),
        "password_reset_sent_at": identity.get("password_reset_sent_at"),
        "pending_email_change_requested_at": identity.get("pending_email_change_requested_at"),
        "email_change_last_sent_at": identity.get("email_change_last_sent_at"),
        "ui_preferences": dict(identity.get("ui_preferences") or {}),
        "deactivated_at": identity.get("deactivated_at"),
        "deactivated_by": identity.get("deactivated_by"),
        "deactivation_reason": identity.get("deactivation_reason"),
    }
    billing = request.app.state.billing_service.subscription_status(account_id=account_id)
    sessions = []
    for item in request.app.state.repository.list_sessions():
        try:
            detail = request.app.state.repository.get_session(str(item.get("session_id") or ""))
        except KeyError:
            continue
        owner_account_id = str(detail.metadata.get("reader_id") or detail.player_profile.get("reader_id") or "").strip()
        if owner_account_id != account_id:
            continue
        sessions.append(
            {
                "session_id": item.get("session_id"),
                "world_id": item.get("world_id"),
                "world_version_id": item.get("world_version_id"),
                "current_turn_index": item.get("current_turn_index"),
                "last_event_title": item.get("last_event_title"),
                "last_chapter_title": item.get("last_chapter_title"),
                "created_at": item.get("created_at"),
            }
        )
        if len(sessions) >= 10:
            break
    author_works = [
        {
            "work_id": item.get("work_id"),
            "world_version_id": item.get("world_version_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "chapter_count": item.get("chapter_count"),
            "target_chapter_count": item.get("target_chapter_count"),
            "updated_at": item.get("updated_at"),
        }
        for item in request.app.state.repository.list_author_works(account_id=account_id, limit=10)
    ]
    deletion_requests = [
        {
            "deletion_request_id": item.get("deletion_request_id"),
            "scope": item.get("scope"),
            "status": item.get("status"),
            "requested_by": item.get("requested_by"),
            "updated_at": item.get("updated_at"),
        }
        for item in request.app.state.repository.list_data_deletion_requests(account_id=account_id, limit=10)
    ]
    export_payload = {
        "generated_at": request.app.state.auth_service._utcnow(),
        "identity": {
            "actor_id": identity.get("actor_id"),
            "account_id": identity.get("account_id"),
            "actor_role": identity.get("actor_role"),
            "display_name": identity.get("display_name"),
            "created_at": identity.get("created_at"),
        },
        "profile": security,
        "billing": {
            "effective_tier": billing.get("effective_tier"),
            "subscription": billing.get("subscription"),
            "wallets": billing.get("wallets"),
            "customer_id": billing.get("customer_id"),
            "customer_portal_available": billing.get("customer_portal_available"),
        },
        "library_summary": {
            "recent_reader_sessions": sessions,
            "author_works": author_works,
        },
        "audit_summary": {
            "data_deletion_requests": deletion_requests,
            "latest_checkout_session": billing.get("latest_checkout_session") or billing.get("checkout_session"),
            "recent_checkout_sessions": billing.get("recent_checkout_sessions"),
        },
    }
    content = json.dumps(export_payload, ensure_ascii=False, indent=2)
    filename_account_id = account_id.replace("@", "_at_").replace("/", "_")
    return {
        "filename": f"account_export_{filename_account_id}.json",
        "content_type": "application/json",
        "content": content,
    }


@router.post("/register")
def register_auth_identity(payload: AuthRegisterRequest, request: Request) -> Dict[str, Any]:
    try:
        result = request.app.state.auth_service.register_identity(
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            password=payload.password,
            account_id=payload.account_id,
            display_name=payload.display_name,
        )
        if payload.actor_role == "customer" and hasattr(request.app.state, "customer_account_service"):
            request.app.state.customer_account_service.ensure_customer_account(
                account_id=str(result["identity"].get("account_id") or result["identity"].get("actor_id") or ""),
                display_name=result["identity"].get("display_name") or result["identity"].get("actor_id"),
            )
        return result
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_register_invalid", "reason": str(exc)}) from exc


@router.post("/login")
def login_auth_identity(payload: AuthLoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    try:
        result = request.app.state.auth_service.issue_token(actor_id=_auth_identifier_from_request(request, raw_identifier=payload.actor_id), password=payload.password)
        response.set_cookie(
            value=result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return result
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_login_failed", "reason": str(exc)}) from exc


@router.post("/refresh")
def refresh_auth_identity(payload: AuthRefreshRequest, request: Request, response: Response) -> Dict[str, Any]:
    try:
        result = request.app.state.auth_service.refresh_access_token(raw_refresh_token=payload.refresh_token)
        response.set_cookie(
            value=result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return result
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_refresh_failed", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_refresh_missing", "reason": str(exc)}) from exc


@router.get("/me")
def auth_me(request: Request) -> Dict[str, Any]:
    try:
        return {"identity": request.app.state.auth_service.resolve_bearer_token(_request_token(request))}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_token_missing", "reason": str(exc)}) from exc


@router.put("/profile")
def update_auth_profile(payload: AuthProfileUpdateRequest, request: Request) -> Dict[str, Any]:
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(_request_token(request))
        updated = request.app.state.auth_service.update_profile(
            actor_id=str(identity.get("actor_id") or ""),
            display_name=payload.display_name,
            avatar_url=payload.avatar_url,
            email_address=payload.email_address,
        )
        return {"identity": updated["identity"]}
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_profile_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/password-change")
def change_auth_password(payload: AuthPasswordChangeRequest, request: Request, response: Response) -> Dict[str, Any]:
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(_request_token(request))
        result = request.app.state.auth_service.change_password(
            actor_id=str(identity.get("actor_id") or ""),
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        response.set_cookie(
            value=result["token"]["access_token"],
            **request.app.state.auth_service.auth_cookie_settings(),
        )
        return result
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_password_change_failed", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_password_change_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.get("/export")
def export_auth_account(request: Request, format: str = "json") -> Dict[str, Any]:
    if str(format or "").strip().lower() != "json":
        raise HTTPException(status_code=400, detail={"code": "auth_export_invalid", "reason": "unsupported_export_format"})
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(_request_token(request))
        return _auth_export_payload(request, identity=identity)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/email-change/request")
def request_auth_email_change(payload: AuthEmailChangeRequest, request: Request) -> Dict[str, Any]:
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(_request_token(request))
        return request.app.state.auth_service.request_email_change(
            actor_id=str(identity.get("actor_id") or ""),
            current_password=payload.current_password,
            new_email=payload.new_email,
        )
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_email_change_request_failed", "reason": str(exc)}) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 409 if reason in {"email_change_email_already_in_use", "email_change_email_pending_elsewhere"} else 400
        raise HTTPException(status_code=status_code, detail={"code": "auth_email_change_request_invalid", "reason": reason}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/email-change/confirm")
def confirm_auth_email_change(payload: AuthVerificationConfirmRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.confirm_email_change(token=payload.token)
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_email_change_token_invalid", "reason": str(exc)}) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 409 if reason == "email_change_email_already_in_use" else 400
        raise HTTPException(status_code=status_code, detail={"code": "auth_email_change_invalid", "reason": reason}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/logout")
def auth_logout(request: Request, response: Response) -> Dict[str, Any]:
    try:
        revoked = request.app.state.auth_service.revoke_bearer_token(_request_token(request))
        response.delete_cookie(
            key=request.app.state.auth_service.auth_cookie_settings()["key"],
            path="/",
            domain=request.app.state.auth_service.auth_cookie_settings().get("domain"),
        )
        return {"session": revoked}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_token_missing", "reason": str(exc)}) from exc


@router.post("/admin-view-bridge")
def create_admin_view_bridge(payload: AdminViewBridgeRequest, request: Request) -> Dict[str, Any]:
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(_request_token(request))
        return request.app.state.auth_service.issue_admin_view_bridge(
            actor_id=str(identity.get("actor_id") or ""),
            actor_role=str(identity.get("actor_role") or ""),
            account_id=payload.account_id or identity.get("account_id"),
            workspace=payload.workspace,
            world_id=payload.world_id,
            world_version_id=payload.world_version_id,
            case_id=payload.case_id,
            alert_id=payload.alert_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "admin_view_bridge_forbidden", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/admin-view-session-bridge")
def create_admin_view_session_bridge(payload: AdminViewSessionBridgeRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.issue_admin_view_session_bridge(
            actor_id=payload.actor_id,
            password=payload.password,
            account_id=payload.account_id,
            workspace=payload.workspace,
            world_id=payload.world_id,
            world_version_id=payload.world_version_id,
            case_id=payload.case_id,
            alert_id=payload.alert_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "admin_view_bridge_forbidden", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/admin-view-bridge/resolve")
def resolve_admin_view_bridge(payload: AdminViewBridgeResolveRequest, request: Request) -> Dict[str, Any]:
    try:
        authorization = request.headers.get("Authorization") or ""
        if authorization.lower().startswith("bearer "):
            token = request.app.state.auth_service.extract_request_token(
                authorization=authorization,
                cookies=None,
            )
            identity = request.app.state.auth_service.resolve_bearer_token(token or "")
            return request.app.state.auth_service.resolve_admin_view_bridge(
                raw_token=payload.token,
                actor_id=str(identity.get("actor_id") or ""),
                actor_role=str(identity.get("actor_role") or ""),
            )
        return request.app.state.auth_service.resolve_admin_view_bridge_token(raw_token=payload.token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "admin_view_bridge_forbidden", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "admin_view_bridge_missing", "reason": str(exc)}) from exc


@router.post("/verification/request")
def request_auth_verification(payload: AuthVerificationRequest, request: Request) -> Dict[str, Any]:
    actor_id = payload.actor_id
    actor_id_from_token = False
    if not actor_id:
        try:
            actor_id = request.app.state.auth_service.resolve_bearer_token(_request_token(request)).get("actor_id")
            actor_id_from_token = True
        except HTTPException:
            actor_id = None
        except (PermissionError, KeyError):
            actor_id = None
    if not actor_id:
        raise HTTPException(status_code=400, detail={"code": "auth_verification_invalid", "reason": "actor_id_required"})
    try:
        resolved_actor_id = str(actor_id) if actor_id_from_token else _auth_identifier_from_request(request, raw_identifier=actor_id)
        return request.app.state.auth_service.request_email_verification(actor_id=resolved_actor_id)
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_verification_invalid", "reason": str(exc)}) from exc


@router.post("/verification/confirm")
def confirm_auth_verification(payload: AuthVerificationConfirmRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.confirm_email_verification(token=payload.token)
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_verification_invalid", "reason": str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_verification_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.post("/password-reset/request")
def request_password_reset(payload: AuthPasswordResetRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.request_password_reset(actor_id=_auth_identifier_from_request(request, raw_identifier=payload.actor_id))
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_password_reset_invalid", "reason": str(exc)}) from exc


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: AuthPasswordResetConfirmRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.confirm_password_reset(token=payload.token, new_password=payload.new_password)
    except AuthServiceError as exc:
        _raise_auth_service_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_password_reset_invalid", "reason": str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_password_reset_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc
