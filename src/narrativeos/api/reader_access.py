from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request


def reader_identity(request: Request) -> Optional[Dict[str, Any]]:
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not raw_token:
        return None
    try:
        return request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "reader_auth_invalid", "reason": str(exc)}) from exc


def reader_identity_account_id(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    if identity is None:
        return None
    value = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    return value or None


def reader_session_owner_account_id(session_record: Any) -> Optional[str]:
    value = str(
        (getattr(session_record, "metadata", {}) or {}).get("reader_id")
        or (getattr(session_record, "metadata", {}) or {}).get("account_id")
        or (getattr(session_record, "player_profile", {}) or {}).get("reader_id")
        or ""
    ).strip()
    return value or None


def _registered_reader_owner_exists(request: Request, owner_account_id: str) -> bool:
    try:
        return request.app.state.repository.get_auth_identity_by_account_id(owner_account_id, default=None) is not None
    except AttributeError:
        return False


def ensure_reader_session_access(
    request: Request,
    *,
    session_id: str,
    session_record: Any = None,
) -> Any:
    resolved_session = session_record or request.app.state.repository.get_session(session_id)
    owner_account_id = reader_session_owner_account_id(resolved_session)
    identity = reader_identity(request)
    viewer_account_id = reader_identity_account_id(identity)
    if not owner_account_id:
        return resolved_session
    if identity is None and not _registered_reader_owner_exists(request, owner_account_id):
        return resolved_session
    if not viewer_account_id:
        raise HTTPException(status_code=401, detail={"code": "reader_session_auth_required", "session_id": session_id})
    if viewer_account_id != owner_account_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "reader_session_ownership_mismatch",
                "session_id": session_id,
                "token_account_id": viewer_account_id,
            },
        )
    return resolved_session
