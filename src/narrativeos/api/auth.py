from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class AuthRegisterRequest(BaseModel):
    actor_id: str
    actor_role: str = "author"
    password: str
    account_id: Optional[str] = None
    display_name: Optional[str] = None


class AuthLoginRequest(BaseModel):
    actor_id: str
    password: str


router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization") or ""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "missing_bearer_token"})
    return authorization.split(" ", 1)[1].strip()


@router.post("/register")
def register_auth_identity(payload: AuthRegisterRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.register_identity(
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            password=payload.password,
            account_id=payload.account_id,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "auth_register_invalid", "reason": str(exc)}) from exc


@router.post("/login")
def login_auth_identity(payload: AuthLoginRequest, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.auth_service.issue_token(actor_id=payload.actor_id, password=payload.password)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_login_failed", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_identity_missing", "reason": str(exc)}) from exc


@router.get("/me")
def auth_me(request: Request) -> Dict[str, Any]:
    try:
        return {"identity": request.app.state.auth_service.resolve_bearer_token(_bearer_token(request))}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_token_missing", "reason": str(exc)}) from exc


@router.post("/logout")
def auth_logout(request: Request) -> Dict[str, Any]:
    try:
        revoked = request.app.state.auth_service.revoke_bearer_token(_bearer_token(request))
        return {"session": revoked}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "auth_token_missing", "reason": str(exc)}) from exc
