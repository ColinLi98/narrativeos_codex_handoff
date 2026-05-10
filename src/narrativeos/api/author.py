from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..eval.service import ChapterQualityGuardError


class SaveDraftRequest(BaseModel):
    worldpack: Dict[str, Any]
    change_context: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None


class AuthorBriefRequest(BaseModel):
    brief: Dict[str, Any]
    account_id: Optional[str] = None


class AuthorAccountRequest(BaseModel):
    account_id: Optional[str] = None


class AuthorLongformBootstrapRequest(BaseModel):
    account_id: Optional[str] = None
    mode: str = "structured_longform"
    target_band: Optional[str] = None


class AuthorWorkCreateRequest(BaseModel):
    world_version_id: str
    account_id: Optional[str] = None


class AuthorWorkListRequest(BaseModel):
    account_id: Optional[str] = None
    world_version_id: Optional[str] = None


class AuthorWorkGenerateRequest(BaseModel):
    mode: str = "next"
    account_id: Optional[str] = None


class AuthorWorkChapterEditRequest(BaseModel):
    chapter_title: Optional[str] = None
    body: Optional[str] = None
    summary: Optional[str] = None
    account_id: Optional[str] = None


class AuthorWorkDiagnosticsRequest(BaseModel):
    account_id: Optional[str] = None


class AuthorWorkSubmitRequest(BaseModel):
    account_id: Optional[str] = None


class AuthorWorkBranchCreateRequest(BaseModel):
    source_chapter_index: int
    label: Optional[str] = None
    steering_directive: Optional[Dict[str, Any]] = None
    choice_source: Optional[Any] = None
    account_id: Optional[str] = None


class AuthorInteractiveScenarioDirectiveRequest(BaseModel):
    current_user_intent: Optional[str] = None
    summary: Optional[str] = None
    impacted_character_ids: list[str] = Field(default_factory=list)
    memory_patch_note: Optional[str] = None
    affected_arc_id: Optional[str] = None


class AuthorInteractiveScenarioRequest(BaseModel):
    scenario_id: Optional[str] = None
    scenario_kind: str = "mild_steer"
    label: str = ""
    trigger_chapter: Optional[int] = None
    steering_directive: AuthorInteractiveScenarioDirectiveRequest = Field(default_factory=AuthorInteractiveScenarioDirectiveRequest)


class AuthorDraftSimulateRequest(BaseModel):
    account_id: Optional[str] = None
    interactive_scenarios: list[AuthorInteractiveScenarioRequest] = Field(default_factory=list)
    include_cross_pack: bool = True
    max_chapters: int = Field(default=6, ge=1, le=12)


class StrategyBundleExecuteRequest(BaseModel):
    campaign_id: Optional[str] = None
    account_id: Optional[str] = None


class PromiseStateUpdateRequest(BaseModel):
    promise_id: str
    editor_state: str = ""
    notes: str = ""
    chapter_index: Optional[int] = None
    chapter_task_id: Optional[str] = None
    arc_id: Optional[str] = None
    volume_id: Optional[str] = None
    account_id: Optional[str] = None


class ContinuityOverrideUpdateRequest(BaseModel):
    chapter_index: int
    override_state: str = ""
    notes: str = ""
    issue_scope: list[str] = Field(default_factory=list)
    chapter_task_id: Optional[str] = None
    arc_id: Optional[str] = None
    volume_id: Optional[str] = None
    account_id: Optional[str] = None


class TaskBulkApplyRequest(BaseModel):
    chapter_indices: list[int] = Field(default_factory=list)
    override_state: str = ""
    notes: str = ""
    issue_scope: list[str] = Field(default_factory=list)
    chapter_task_id: Optional[str] = None
    arc_id: Optional[str] = None
    volume_id: Optional[str] = None
    account_id: Optional[str] = None


class AuthorCommentThreadRequest(BaseModel):
    revision_id: Optional[str] = None
    anchor_type: str
    anchor_key: str
    severity: str = "normal"
    assignee_id: Optional[str] = None
    actor_id: str
    actor_role: str = "author"
    body: str


class AuthorCommentReplyRequest(BaseModel):
    actor_id: str
    actor_role: str = "author"
    body: str


class AuthorCommentStatusRequest(BaseModel):
    status: str
    severity: Optional[str] = None
    assignee_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: str = "author"
    body: Optional[str] = None


class AuthorApprovalRequest(BaseModel):
    revision_id: Optional[str] = None
    reviewer_id: str
    reason: str
    actor_id: Optional[str] = None
    actor_role: str = "author"


class AuthorApprovalDecisionRequest(BaseModel):
    revision_id: Optional[str] = None
    reviewer_id: str
    status: str
    reason: str


class AuthorNotificationStatusRequest(BaseModel):
    status: str
    recipient_id: Optional[str] = None
    limit: int = 20


class AuthorNotificationBulkStatusRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list)
    recipient_id: str
    status: str
    limit: int = 20


class AuthorThreadWatcherRequest(BaseModel):
    actor_id: str
    watcher_id: Optional[str] = None


class AuthorDraftWatcherRequest(BaseModel):
    actor_id: str
    watcher_id: Optional[str] = None


class AuthorNotificationPreferenceRequest(BaseModel):
    actor_id: Optional[str] = None
    notification_type: str
    in_app_enabled: bool = True
    async_mirror_enabled: bool = True
    async_sink_name: Optional[str] = None
    delivery_target: Optional[str] = None


router = APIRouter(prefix="/v1/author", tags=["author"])
ACTOR_ID_HEADER = "X-NarrativeOS-Actor-Id"
ACTOR_ROLE_HEADER = "X-NarrativeOS-Actor-Role"
ACCOUNT_ID_HEADER = "X-NarrativeOS-Account-Id"


def _request_identity(request: Request) -> Dict[str, Optional[str]]:
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
            "identity_source": "bearer",
        }
    actor_id = request.headers.get(ACTOR_ID_HEADER)
    actor_role = request.headers.get(ACTOR_ROLE_HEADER)
    account_id = request.headers.get(ACCOUNT_ID_HEADER)
    if actor_id or actor_role or account_id:
        return {
            "actor_id": actor_id.strip() if actor_id else None,
            "actor_role": actor_role.strip() if actor_role else None,
            "account_id": account_id.strip() if account_id else None,
            "identity_source": "header",
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
            "identity_source": "cookie",
        }
    return {
        "actor_id": actor_id.strip() if actor_id else None,
        "actor_role": actor_role.strip() if actor_role else None,
        "account_id": account_id.strip() if account_id else None,
        "identity_source": "header" if (actor_id or actor_role or account_id) else None,
    }


def _apply_identity(
    request: Request,
    payload: Dict[str, Any],
    *,
    actor_field: Optional[str] = "actor_id",
    role_field: Optional[str] = "actor_role",
    reviewer_field: Optional[str] = None,
    recipient_field: Optional[str] = None,
    account_field: Optional[str] = None,
) -> Dict[str, Any]:
    resolved = dict(payload)
    identity = _request_identity(request)
    if identity["actor_id"]:
        if reviewer_field:
            resolved[reviewer_field] = identity["actor_id"]
        elif recipient_field:
            resolved[recipient_field] = identity["actor_id"]
        elif actor_field:
            resolved[actor_field] = identity["actor_id"]
    if role_field and identity["actor_role"]:
        resolved[role_field] = identity["actor_role"]
    if account_field and identity["account_id"]:
        resolved[account_field] = identity["account_id"]
    return resolved


def _resolve_identity_value(request: Request, fallback: Optional[str] = None) -> Optional[str]:
    identity = _request_identity(request)
    return identity["actor_id"] or fallback


def _resolve_account_value(request: Request, fallback: Optional[str] = None) -> Optional[str]:
    identity = _request_identity(request)
    return identity["account_id"] or identity["actor_id"] or fallback


def _resolve_authenticated_account_value(request: Request, fallback: Optional[str] = None) -> Optional[str]:
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not raw_token:
        return fallback
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    return identity.get("account_id") or identity.get("actor_id") or fallback


def _authenticated_author_identity(
    request: Request,
    *,
    missing_code: str = "author_draft_auth_required",
    missing_reason: str = "author_draft_owner_token_required",
) -> Dict[str, Any]:
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not raw_token:
        raise HTTPException(status_code=401, detail={"code": missing_code, "reason": missing_reason})
    try:
        return request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc


def _author_identity_actor_id(identity: Dict[str, Any]) -> str:
    return str(identity.get("actor_id") or "").strip()


def _author_identity_account_id(identity: Dict[str, Any]) -> str:
    return str(identity.get("account_id") or identity.get("actor_id") or "").strip()


def _authenticated_author_actor_context(
    request: Request,
    *,
    missing_code: str = "author_collaboration_session_required",
    forbidden_code: str = "author_collaboration_role_forbidden",
    allowed_roles: Optional[set[str]] = None,
) -> Dict[str, str]:
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not raw_token:
        raise HTTPException(status_code=403, detail={"code": missing_code, "reason": missing_code})
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "auth_token_invalid", "reason": str(exc)}) from exc
    actor_id = _author_identity_actor_id(identity)
    actor_role = str(identity.get("actor_role") or "").strip()
    account_id = _author_identity_account_id(identity)
    if not actor_id:
        raise HTTPException(status_code=403, detail={"code": missing_code, "reason": missing_code})
    if allowed_roles is not None and actor_role not in allowed_roles:
        raise HTTPException(status_code=403, detail={"code": forbidden_code, "reason": forbidden_code})
    return {
        "actor_id": actor_id,
        "actor_role": actor_role,
        "account_id": account_id,
    }


def _record_author_audit_log(
    request: Request,
    *,
    actor_id: str,
    actor_role: str,
    account_id: str,
    world_version_id: str,
    action_type: str,
    customer_visible_payload: Optional[Dict[str, Any]] = None,
    internal_payload: Optional[Dict[str, Any]] = None,
) -> None:
    audit_service = getattr(request.app.state, "commercial_audit_service", None)
    if audit_service is None:
        return
    try:
        audit_service.record_audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=account_id,
            object_type="author_draft",
            object_id=world_version_id,
            action_type=action_type,
            source_surface="author",
            customer_visible_payload=customer_visible_payload or {},
            internal_payload=internal_payload or {},
        )
    except Exception:
        return


def _author_payload_with_actor(
    payload: Dict[str, Any],
    actor: Dict[str, str],
    *,
    actor_field: Optional[str] = "actor_id",
    role_field: Optional[str] = "actor_role",
    reviewer_field: Optional[str] = None,
    recipient_field: Optional[str] = None,
    account_field: Optional[str] = None,
) -> Dict[str, Any]:
    resolved = dict(payload)
    if reviewer_field:
        resolved[reviewer_field] = actor["actor_id"]
    elif recipient_field:
        resolved[recipient_field] = actor["actor_id"]
    elif actor_field:
        resolved[actor_field] = actor["actor_id"]
    if role_field:
        resolved[role_field] = actor["actor_role"]
    if account_field:
        resolved[account_field] = actor["account_id"]
    return resolved


def _normalized_author_account_id(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _ensure_author_account_owner(
    request: Request,
    *requested_account_ids: Any,
    world_version_id: Optional[str] = None,
) -> str:
    identity = _authenticated_author_identity(
        request,
        missing_code="author_account_auth_required",
        missing_reason="author_account_token_required",
    )
    token_account_id = _author_identity_account_id(identity)
    if not token_account_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "author_account_auth_required", "reason": "author_account_required"},
        )

    candidates = [_normalized_author_account_id(item) for item in requested_account_ids]
    if world_version_id:
        try:
            version = request.app.state.repository.get_world_version(world_version_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        candidates.append(_normalized_author_account_id(version.author_id))

    for requested_account_id in [item for item in candidates if item]:
        if requested_account_id != token_account_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "author_account_mismatch",
                    "reason": "author_account_mismatch",
                    "token_account_id": token_account_id,
                    "requested_account_id": requested_account_id,
                },
            )
    return token_account_id


def _author_payload_worldpack_owner(worldpack: Dict[str, Any]) -> Optional[str]:
    manifest = worldpack.get("manifest")
    if isinstance(manifest, dict):
        return _normalized_author_account_id(manifest.get("author_id"))
    return None


def _with_author_worldpack_owner(worldpack: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    resolved = dict(worldpack)
    manifest = dict(resolved.get("manifest") or {})
    manifest["author_id"] = account_id
    resolved["manifest"] = manifest
    return resolved


def _with_author_brief_owner(brief: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    return {**brief, "account_id": account_id, "author_id": account_id}


def _ensure_author_draft_owner(request: Request, world_version_id: str) -> tuple[Any, str]:
    identity = _authenticated_author_identity(request)
    token_account_id = _author_identity_account_id(identity)
    if not token_account_id:
        raise HTTPException(status_code=401, detail={"code": "author_draft_auth_required", "reason": "author_account_required"})
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    owner_account_id = str(version.author_id or "").strip()
    if not owner_account_id:
        raise HTTPException(status_code=403, detail={"code": "author_draft_owner_missing", "reason": "author_draft_owner_missing"})
    if token_account_id != owner_account_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "author_draft_ownership_mismatch",
                "reason": "author_draft_owner_mismatch",
                "token_account_id": token_account_id,
                "owner_account_id": owner_account_id,
            },
        )
    return version, token_account_id


def _ensure_author_workflow_account(request: Request, *, account_id: Optional[str], world_version_id: Optional[str]) -> str:
    identity = _authenticated_author_identity(request)
    token_account_id = _author_identity_account_id(identity)
    if not token_account_id:
        raise HTTPException(status_code=401, detail={"code": "author_workflow_auth_required", "reason": "author_account_required"})
    if world_version_id:
        _version, owner_account_id = _ensure_author_draft_owner(request, world_version_id)
        return owner_account_id
    requested_account_id = str(account_id or "").strip()
    if requested_account_id and requested_account_id != token_account_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "author_workflow_account_mismatch",
                "reason": "author_workflow_account_mismatch",
                "token_account_id": token_account_id,
                "requested_account_id": requested_account_id,
            },
        )
    return token_account_id


def _author_collaboration_participant_ids(request: Request, *, world_version_id: str) -> set[str]:
    participant_ids: set[str] = set()
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    owner_id = str(version.author_id or "").strip()
    if owner_id:
        participant_ids.add(owner_id)
    for watcher in request.app.state.repository.list_author_draft_watchers(world_version_id=world_version_id):
        watcher_id = str(watcher.get("watcher_id") or "").strip()
        if watcher_id:
            participant_ids.add(watcher_id)
    for approval in request.app.state.repository.list_author_approval_records(world_version_id=world_version_id, status="requested"):
        reviewer_id = str(approval.get("reviewer_id") or "").strip()
        if reviewer_id:
            participant_ids.add(reviewer_id)
    for thread in request.app.state.repository.list_author_comment_threads(world_version_id=world_version_id):
        for candidate in (thread.get("created_by"), thread.get("assignee_id")):
            candidate_id = str(candidate or "").strip()
            if candidate_id:
                participant_ids.add(candidate_id)
        for watcher in request.app.state.repository.list_author_thread_watchers(thread_id=str(thread.get("thread_id") or "")):
            watcher_id = str(watcher.get("watcher_id") or "").strip()
            if watcher_id:
                participant_ids.add(watcher_id)
    return participant_ids


def _ensure_author_collaboration_object_scope(request: Request, *, world_version_id: str) -> Dict[str, Any]:
    identity = _authenticated_author_identity(request)
    candidate_ids = {
        value
        for value in {
            _author_identity_actor_id(identity),
            _author_identity_account_id(identity),
        }
        if value
    }
    participant_ids = _author_collaboration_participant_ids(request, world_version_id=world_version_id)
    if candidate_ids & participant_ids:
        return identity
    raise HTTPException(
        status_code=403,
        detail={
            "code": "author_collaboration_object_forbidden",
            "reason": "author_collaboration_object_forbidden",
        },
    )


def _ensure_author_thread_collaboration_scope(request: Request, *, thread_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    try:
        thread = request.app.state.repository.get_author_comment_thread(thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    identity = _ensure_author_collaboration_object_scope(request, world_version_id=str(thread.get("world_version_id") or ""))
    return identity, thread


def _ensure_author_draft_watcher_mutation_scope(request: Request, *, world_version_id: str, watcher_id: str, add: bool) -> None:
    identity = _authenticated_author_identity(request)
    token_ids = {
        value
        for value in {
            _author_identity_actor_id(identity),
            _author_identity_account_id(identity),
        }
        if value
    }
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    owner_id = str(version.author_id or "").strip()
    if owner_id and owner_id in token_ids:
        return
    target_watcher_id = str(watcher_id or "").strip()
    existing_self_watcher = bool(
        target_watcher_id
        and target_watcher_id in token_ids
        and request.app.state.repository.list_author_draft_watchers(
            world_version_id=world_version_id,
            watcher_id=target_watcher_id,
        )
    )
    if not add and existing_self_watcher:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "author_collaboration_object_forbidden",
            "reason": "author_collaboration_object_forbidden",
        },
    )


def _ensure_author_thread_watcher_mutation_scope(request: Request, *, thread_id: str, watcher_id: str, add: bool) -> None:
    identity, thread = _ensure_author_thread_collaboration_scope(request, thread_id=thread_id)
    token_ids = {
        value
        for value in {
            _author_identity_actor_id(identity),
            _author_identity_account_id(identity),
        }
        if value
    }
    try:
        owner_id = str(request.app.state.repository.get_world_version(str(thread.get("world_version_id") or "")).author_id or "").strip()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if owner_id and owner_id in token_ids:
        return
    target_watcher_id = str(watcher_id or "").strip()
    existing_self_watcher = bool(
        target_watcher_id
        and target_watcher_id in token_ids
        and request.app.state.repository.list_author_thread_watchers(
            thread_id=thread_id,
            watcher_id=target_watcher_id,
        )
    )
    if not add and existing_self_watcher:
        return
    if add and token_ids & _author_collaboration_participant_ids(request, world_version_id=str(thread.get("world_version_id") or "")):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "author_collaboration_object_forbidden",
            "reason": "author_collaboration_object_forbidden",
        },
    )


def ensure_author_collaboration_access(request: Request) -> Optional[Dict[str, Optional[str]]]:
    identity = _request_identity(request)
    try:
        return request.app.state.author_permission_policy.authorize(
            actor_id=identity.get("actor_id"),
            actor_role=identity.get("actor_role"),
            identity_source=identity.get("identity_source"),
            method=request.method,
            path=request.url.path,
        )
    except PermissionError as exc:
        reason = str(exc)
        raise HTTPException(status_code=403, detail={"code": reason, "reason": reason}) from exc


def _ensure_author_work_account(request: Request, expected_account_id: Optional[str], fallback: Optional[str] = None) -> str:
    identity = _authenticated_author_identity(
        request,
        missing_code="author_work_identity_required",
        missing_reason="author_account_required",
    )
    resolved_account_id = _author_identity_account_id(identity)
    if not resolved_account_id:
        raise HTTPException(status_code=401, detail={"code": "author_work_identity_required", "reason": "author_account_required"})
    for candidate in (
        _normalized_author_account_id(expected_account_id),
        _normalized_author_account_id(fallback),
    ):
        if candidate and resolved_account_id != candidate:
            raise HTTPException(status_code=403, detail={"code": "author_work_forbidden", "reason": "author_work_account_mismatch"})
    return resolved_account_id


def _execute_collaboration_action(fn):
    try:
        return fn()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "author_collaboration_forbidden", "reason": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "author_collaboration_missing", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "author_collaboration_invalid", "reason": str(exc)}) from exc


@router.get("/drafts")
def list_drafts(request: Request) -> Dict[str, Any]:
    account_id = _resolve_authenticated_account_value(request)
    drafts = request.app.state.repository.list_world_versions(status="draft")
    if account_id:
        drafts = [item for item in drafts if str(item.get("author_id") or "").strip() == str(account_id).strip()]
    else:
        drafts = []
    return {"drafts": drafts}


@router.post("/drafts")
def save_draft(payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    account_id = _ensure_author_account_owner(
        request,
        payload.account_id,
        _author_payload_worldpack_owner(payload.worldpack),
    )
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="save_draft")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                **access,
            },
        )
    worldpack = _with_author_worldpack_owner(payload.worldpack, account_id)
    draft = request.app.state.authoring_service.save_draft(worldpack, change_context=payload.change_context)
    request.app.state.analytics_service.track(
        "author_draft_saved",
        reader_id=account_id,
        account_id=account_id,
        world_id=draft.get("world_id"),
        world_version_id=draft.get("world_version_id"),
        access_tier=access.get("tier_id"),
        payload_json={
            "change_source": (payload.change_context or {}).get("source"),
            "change_label": (payload.change_context or {}).get("label"),
            "wallet_type": access.get("wallet_type"),
            "subscription_status": access.get("subscription_status"),
        },
    )
    return draft


@router.get("/brief-template")
def brief_template(request: Request) -> Dict[str, Any]:
    return request.app.state.authoring_service.get_brief_template()


@router.get("/access")
def author_access(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_account_id = _ensure_author_account_owner(
        request,
        account_id,
        world_version_id=world_version_id,
    )
    return request.app.state.billing_service.author_access_snapshot(
        account_id=resolved_account_id,
        world_version_id=world_version_id,
    )


@router.get("/workflow")
def author_workflow(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_account_id = _ensure_author_workflow_account(
        request,
        account_id=account_id,
        world_version_id=world_version_id,
    )
    return request.app.state.authoring_service.workflow_summary(
        account_id=resolved_account_id,
        world_version_id=world_version_id,
    )


@router.get("/drafts/{world_version_id}/collaboration")
def collaboration_summary(world_version_id: str, request: Request) -> Dict[str, Any]:
    _ensure_author_collaboration_object_scope(request, world_version_id=world_version_id)
    return request.app.state.author_collaboration_service.collaboration_summary(world_version_id=world_version_id)


@router.get("/reviewer-inbox")
def reviewer_inbox(
    request: Request,
    reviewer_id: Optional[str] = None,
    limit: int = 20,
    world_version_id: Optional[str] = None,
    status_filter: str = "all",
    notification_type: Optional[str] = None,
    blocking_only: bool = False,
    cursor: Optional[str] = None,
    q: Optional[str] = None,
) -> Dict[str, Any]:
    actor = _authenticated_author_actor_context(
        request,
        missing_code="author_review_session_required",
        forbidden_code="author_review_role_forbidden",
        allowed_roles={"reviewer", "ops", "admin", "editor"},
    )
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.reviewer_inbox(
            reviewer_id=actor["actor_id"],
            limit=limit,
            world_version_id=world_version_id,
            status_filter=status_filter,
            notification_type=notification_type,
            blocking_only=blocking_only,
            cursor=cursor,
            q=q,
        )
    )


@router.post("/drafts/{world_version_id}/comments")
def create_comment_thread(
    world_version_id: str,
    payload: AuthorCommentThreadRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_draft_owner(request, world_version_id)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.create_comment_thread(
            world_version_id=world_version_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/comments/{thread_id}/reply")
def reply_comment_thread(
    thread_id: str,
    payload: AuthorCommentReplyRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_thread_collaboration_scope(request, thread_id=thread_id)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.reply_to_thread(
            thread_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/comments/{thread_id}/status")
def update_comment_thread_status(
    thread_id: str,
    payload: AuthorCommentStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_thread_collaboration_scope(request, thread_id=thread_id)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.update_thread_status(
            thread_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/drafts/{world_version_id}/approval/request")
def request_author_approval(
    world_version_id: str,
    payload: AuthorApprovalRequest,
    request: Request,
) -> Dict[str, Any]:
    version, account_id = _ensure_author_draft_owner(request, world_version_id)
    result = _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.request_approval(
            world_version_id=world_version_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )
    approval = dict(result.get("approval") or {})
    _record_author_audit_log(
        request,
        actor_id=account_id,
        actor_role="author",
        account_id=account_id,
        world_version_id=world_version_id,
        action_type="author_approval_requested",
        customer_visible_payload={
            "world_id": version.world_id,
            "world_version_id": world_version_id,
            "approval_status": approval.get("status"),
            "reviewer_id": approval.get("reviewer_id"),
        },
        internal_payload={
            "approval_id": approval.get("approval_id"),
            "reason": approval.get("reason"),
        },
    )
    return result


@router.post("/drafts/{world_version_id}/approval/decision")
def decide_author_approval(
    world_version_id: str,
    payload: AuthorApprovalDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_collaboration_object_scope(request, world_version_id=world_version_id)
    actor = _authenticated_author_actor_context(
        request,
        missing_code="author_review_session_required",
        forbidden_code="author_review_role_forbidden",
        allowed_roles={"reviewer", "ops", "admin", "editor"},
    )
    result = _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.approval_decision(
            world_version_id=world_version_id,
            payload=_author_payload_with_actor(
                payload.model_dump(),
                actor,
                actor_field=None,
                role_field=None,
                reviewer_field="reviewer_id",
            ),
        )
    )
    approval = dict(result.get("approval") or {})
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
        account_id = str(version.author_id or "").strip()
        world_id = version.world_id
    except KeyError:
        account_id = str(approval.get("reviewer_id") or actor["account_id"] or actor["actor_id"])
        world_id = ""
    _record_author_audit_log(
        request,
        actor_id=actor["actor_id"],
        actor_role=actor["actor_role"],
        account_id=account_id,
        world_version_id=world_version_id,
        action_type="author_approval_decision",
        customer_visible_payload={
            "world_id": world_id,
            "world_version_id": world_version_id,
            "approval_status": approval.get("status"),
            "reviewer_id": actor["actor_id"],
        },
        internal_payload={
            "approval_id": approval.get("approval_id"),
            "reason": approval.get("reason"),
        },
    )
    return result


@router.post("/notifications/{notification_id}/status")
def update_author_notification_status(
    notification_id: str,
    payload: AuthorNotificationStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _authenticated_author_actor_context(request, allowed_roles={"author", "reviewer", "ops", "admin", "editor"})
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.update_notification_status(
            notification_id,
            payload=_author_payload_with_actor(
                payload.model_dump(),
                actor,
                actor_field=None,
                role_field=None,
                recipient_field="recipient_id",
            ),
        )
    )


@router.post("/notifications/bulk-status")
def bulk_update_author_notification_status(
    payload: AuthorNotificationBulkStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _authenticated_author_actor_context(request, allowed_roles={"author", "reviewer", "ops", "admin", "editor"})
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.bulk_update_notification_status(
            _author_payload_with_actor(
                payload.model_dump(),
                actor,
                actor_field=None,
                role_field=None,
                recipient_field="recipient_id",
            ),
        )
    )


@router.post("/comments/{thread_id}/watchers")
def add_author_thread_watcher(
    thread_id: str,
    payload: AuthorThreadWatcherRequest,
    request: Request,
) -> Dict[str, Any]:
    watcher_id = str(payload.watcher_id or payload.actor_id or "").strip()
    _ensure_author_thread_watcher_mutation_scope(request, thread_id=thread_id, watcher_id=watcher_id, add=True)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.add_thread_watcher(
            thread_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/comments/{thread_id}/watchers/{watcher_id}/remove")
def remove_author_thread_watcher(
    thread_id: str,
    watcher_id: str,
    payload: AuthorThreadWatcherRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_thread_watcher_mutation_scope(request, thread_id=thread_id, watcher_id=watcher_id, add=False)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.remove_thread_watcher(
            thread_id,
            watcher_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/drafts/{world_version_id}/watchers")
def add_author_draft_watcher(
    world_version_id: str,
    payload: AuthorDraftWatcherRequest,
    request: Request,
) -> Dict[str, Any]:
    watcher_id = str(payload.watcher_id or payload.actor_id or "").strip()
    _ensure_author_draft_watcher_mutation_scope(request, world_version_id=world_version_id, watcher_id=watcher_id, add=True)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.add_draft_watcher(
            world_version_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/drafts/{world_version_id}/watchers/{watcher_id}/remove")
def remove_author_draft_watcher(
    world_version_id: str,
    watcher_id: str,
    payload: AuthorDraftWatcherRequest,
    request: Request,
) -> Dict[str, Any]:
    _ensure_author_draft_watcher_mutation_scope(request, world_version_id=world_version_id, watcher_id=watcher_id, add=False)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.remove_draft_watcher(
            world_version_id,
            watcher_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.get("/notification-preferences")
def author_notification_preferences(
    request: Request,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    actor = _authenticated_author_actor_context(request, allowed_roles={"author", "reviewer", "ops", "admin", "editor"})
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.notification_preferences(actor["actor_id"])
    )


@router.post("/notification-preferences")
def update_author_notification_preference(
    payload: AuthorNotificationPreferenceRequest,
    request: Request,
) -> Dict[str, Any]:
    actor = _authenticated_author_actor_context(request, allowed_roles={"author", "reviewer", "ops", "admin", "editor"})
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.update_notification_preference(
            _author_payload_with_actor(payload.model_dump(), actor),
        )
    )


@router.post("/drafts/from-brief")
def create_draft_from_brief(payload: AuthorBriefRequest, request: Request) -> Dict[str, Any]:
    account_id = _ensure_author_account_owner(
        request,
        payload.account_id,
        payload.brief.get("account_id"),
        payload.brief.get("author_id"),
    )
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="draft_from_brief")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                "required_tier": access["required_tier"],
                "wallet_type": access["wallet_type"],
                "balance": access["balance"],
                "reason": access["reason"],
            },
        )
    draft = request.app.state.authoring_service.create_draft_from_brief(_with_author_brief_owner(payload.brief, account_id))
    wallet = request.app.state.billing_service.consume_studio_credits(
        account_id=access["account_id"],
        amount=request.app.state.monetization_service.metering_rules()["author_from_brief_studio_credits"],
    )
    request.app.state.billing_service.meter_action(
        surface="author",
        action_name="draft_from_brief",
        account_id=access["account_id"],
        reader_id=access["account_id"],
        world_version_id=draft["world_version_id"],
        access=access,
        provider="internal",
        estimated_cost=0.0,
    )
    request.app.state.analytics_service.track(
        "studio_credits_consumed",
        reader_id=access["account_id"],
        account_id=access["account_id"],
        world_version_id=draft["world_version_id"],
        payload_json={
            "wallet_type": "studio_credits",
            "balance": wallet.get("balance"),
            "action_type": "author_from_brief",
            "tier_id": access.get("tier_id"),
        },
    )
    request.app.state.analytics_service.track(
        "author_draft_created_from_brief",
        reader_id=access["account_id"],
        account_id=access["account_id"],
        world_id=draft.get("world_id"),
        world_version_id=draft.get("world_version_id"),
        access_tier=access.get("tier_id"),
        payload_json={
            "genre_preset": payload.brief.get("genre_preset"),
            "wallet_type": "studio_credits",
            "balance": wallet.get("balance"),
            "tier_id": access.get("tier_id"),
        },
    )
    return draft


@router.get("/drafts/{world_version_id}")
def get_draft(world_version_id: str, request: Request) -> Dict[str, Any]:
    _ensure_author_draft_owner(request, world_version_id)
    return request.app.state.authoring_service.get_draft(world_version_id)


@router.get("/works")
def list_author_works(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_account_id = _ensure_author_work_account(request, account_id, account_id)
    return request.app.state.author_work_service.list_works(
        account_id=resolved_account_id,
        world_version_id=world_version_id,
    )


@router.post("/works")
def create_author_work(payload: AuthorWorkCreateRequest, request: Request) -> Dict[str, Any]:
    version = request.app.state.repository.get_world_version(payload.world_version_id)
    account_id = _ensure_author_work_account(request, version.author_id, payload.account_id or version.author_id)
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"code": "author_entitlement_required", **access})
    return request.app.state.author_work_service.create_work(
        world_version_id=payload.world_version_id,
        account_id=account_id or version.author_id,
    )


@router.get("/works/{work_id}")
def get_author_work(work_id: str, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
        _ensure_author_work_account(request, work.get("account_id"), work.get("account_id"))
        return request.app.state.author_work_service.get_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/works/{work_id}/export")
def export_author_work(work_id: str, request: Request, format: str = "nosbook", route: str = "active") -> JSONResponse:
    if str(format or "").strip() != "nosbook":
        raise HTTPException(status_code=400, detail={"code": "unsupported_author_work_export_format", "reason": format})
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _ensure_author_work_account(request, work.get("account_id"), work.get("account_id"))
    payload = request.app.state.author_work_service.export_work_nosbook(work_id=work_id, route=route)
    return JSONResponse(
        content=payload,
        media_type="application/vnd.narrativeos.nosbook+json",
        headers={"Content-Disposition": f"attachment; filename=\"{payload.get('filename') or 'narrativeos-work.nosbook'}\""},
    )


@router.delete("/works/{work_id}")
def delete_author_work(work_id: str, request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _ensure_author_work_account(request, work.get("account_id"), account_id or work.get("account_id"))
    return request.app.state.author_work_service.delete_work_family(work_id=work_id)


@router.get("/works/{work_id}/chapters/{chapter_index}")
def get_author_work_chapter(work_id: str, chapter_index: int, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
        _ensure_author_work_account(request, work.get("account_id"), work.get("account_id"))
        return request.app.state.author_work_service.get_work_chapter(work_id=work_id, chapter_index=chapter_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/works/{work_id}/chapters/generate")
def generate_author_work_chapters(work_id: str, payload: AuthorWorkGenerateRequest, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    account_id = _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="simulate")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                "required_tier": access["required_tier"],
                "wallet_type": access["wallet_type"],
                "balance": access["balance"],
                "reason": access["reason"],
            },
        )
    try:
        result = request.app.state.author_work_service.generate_chapters(work_id=work_id, mode=payload.mode)
    except ChapterQualityGuardError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.quality_gate.get("code"), "quality_gate": exc.quality_gate}) from exc
    request.app.state.billing_service.consume_studio_credits(
        account_id=access["account_id"],
        amount=request.app.state.monetization_service.metering_rules()["author_simulate_studio_credits"],
    )
    return result


@router.post("/works/{work_id}/chapters/{chapter_index}/edit")
def edit_author_work_chapter(
    work_id: str,
    chapter_index: int,
    payload: AuthorWorkChapterEditRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    account_id = _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"code": "author_entitlement_required", **access})
    try:
        return request.app.state.author_work_service.edit_chapter(
            work_id=work_id,
            chapter_index=chapter_index,
            title=payload.chapter_title,
            body=payload.body,
            summary=payload.summary,
        )
    except ChapterQualityGuardError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.quality_gate.get("code"), "quality_gate": exc.quality_gate}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/works/{work_id}/diagnostics/run")
def run_author_work_diagnostics(work_id: str, payload: AuthorWorkDiagnosticsRequest, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    account_id = _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="simulate")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                "required_tier": access["required_tier"],
                "wallet_type": access["wallet_type"],
                "balance": access["balance"],
                "reason": access["reason"],
            },
        )
    result = request.app.state.author_work_service.run_diagnostics(work_id=work_id)
    request.app.state.billing_service.consume_studio_credits(
        account_id=access["account_id"],
        amount=request.app.state.monetization_service.metering_rules()["author_simulate_studio_credits"],
    )
    return result


@router.post("/works/{work_id}/submit")
def submit_author_work(work_id: str, payload: AuthorWorkSubmitRequest, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    account_id = _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="submit_draft")
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"code": "author_entitlement_required", **access})
    try:
        return request.app.state.author_work_service.submit_work(work_id=work_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/works/{work_id}/branches")
def list_author_work_branches(work_id: str, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _ensure_author_work_account(request, work.get("account_id"), work.get("account_id"))
    return request.app.state.author_work_service.list_branches(work_id=work_id)


@router.post("/works/{work_id}/branches")
def create_author_work_branch(work_id: str, payload: AuthorWorkBranchCreateRequest, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    account_id = _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="simulate")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                "required_tier": access["required_tier"],
                "wallet_type": access["wallet_type"],
                "balance": access["balance"],
                "reason": access["reason"],
            },
        )
    try:
        return request.app.state.author_work_service.create_branch(
            work_id=work_id,
            source_chapter_index=payload.source_chapter_index,
            label=payload.label,
            steering_directive=payload.steering_directive,
            choice_source=payload.choice_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/works/{work_id}/activate-line")
def activate_author_work_line(work_id: str, payload: AuthorAccountRequest, request: Request) -> Dict[str, Any]:
    try:
        work = request.app.state.repository.get_author_work(work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _ensure_author_work_account(request, work.get("account_id"), payload.account_id or work.get("account_id"))
    return request.app.state.author_work_service.activate_branch(work_id=work_id)


@router.put("/drafts/{world_version_id}")
def update_draft(world_version_id: str, payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        _ensure_author_account_owner(
            request,
            payload.account_id,
            _author_payload_worldpack_owner(payload.worldpack),
        )
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        worldpack = _with_author_worldpack_owner(payload.worldpack, account_id)
        draft = request.app.state.authoring_service.update_draft(world_version_id, worldpack, change_context=payload.change_context)
        request.app.state.analytics_service.track(
            "author_draft_updated",
            reader_id=account_id,
            account_id=account_id,
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "change_source": (payload.change_context or {}).get("source"),
                "change_label": (payload.change_context or {}).get("label"),
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/longform-bootstrap")
def bootstrap_longform_workbench(world_version_id: str, payload: AuthorLongformBootstrapRequest, request: Request) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        draft = request.app.state.authoring_service.bootstrap_longform_workbench(
            world_version_id,
            mode=payload.mode,
            target_band=payload.target_band,
        )
        request.app.state.analytics_service.track(
            "author_longform_workbench_bootstrapped",
            reader_id=account_id,
            account_id=account_id,
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "mode": payload.mode,
                "target_band": payload.target_band,
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/promise-state")
def update_promise_state(world_version_id: str, payload: PromiseStateUpdateRequest, request: Request) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        draft = request.app.state.authoring_service.update_promise_state(
            world_version_id,
            promise_id=payload.promise_id,
            editor_state=payload.editor_state,
            notes=payload.notes,
            chapter_index=payload.chapter_index,
            chapter_task_id=payload.chapter_task_id,
            arc_id=payload.arc_id,
            volume_id=payload.volume_id,
        )
        request.app.state.analytics_service.track(
            "author_promise_state_updated",
            reader_id=account_id,
            account_id=account_id,
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "promise_id": payload.promise_id,
                "editor_state": payload.editor_state,
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/continuity-override")
def update_continuity_override(world_version_id: str, payload: ContinuityOverrideUpdateRequest, request: Request) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        draft = request.app.state.authoring_service.update_continuity_override(
            world_version_id,
            chapter_index=payload.chapter_index,
            override_state=payload.override_state,
            notes=payload.notes,
            issue_scope=payload.issue_scope,
            chapter_task_id=payload.chapter_task_id,
            arc_id=payload.arc_id,
            volume_id=payload.volume_id,
        )
        request.app.state.analytics_service.track(
            "author_continuity_override_updated",
            reader_id=account_id,
            account_id=account_id,
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "chapter_index": payload.chapter_index,
                "override_state": payload.override_state,
                "issue_scope": payload.issue_scope,
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/task-bulk-apply")
def bulk_apply_task_to_simulation(world_version_id: str, payload: TaskBulkApplyRequest, request: Request) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        draft = request.app.state.authoring_service.bulk_apply_task_continuity_override(
            world_version_id,
            chapter_indices=payload.chapter_indices,
            override_state=payload.override_state,
            notes=payload.notes,
            issue_scope=payload.issue_scope,
            chapter_task_id=payload.chapter_task_id,
            arc_id=payload.arc_id,
            volume_id=payload.volume_id,
        )
        request.app.state.analytics_service.track(
            "author_task_bulk_apply",
            reader_id=account_id,
            account_id=account_id,
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "chapter_count": len(payload.chapter_indices),
                "override_state": payload.override_state,
                "chapter_task_id": payload.chapter_task_id,
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/strategy-bundles/execute")
def execute_content_quality_strategy_bundle(
    world_version_id: str,
    payload: StrategyBundleExecuteRequest,
    request: Request,
) -> Dict[str, Any]:
    try:
        _version, account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="simulate")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    "required_tier": access["required_tier"],
                    "wallet_type": access["wallet_type"],
                    "balance": access["balance"],
                    "reason": access["reason"],
                },
            )
        draft = request.app.state.authoring_service.execute_content_quality_strategy_bundle(
            world_version_id,
            campaign_id=payload.campaign_id,
        )
        wallet = request.app.state.billing_service.consume_studio_credits(
            account_id=access["account_id"],
            amount=request.app.state.monetization_service.metering_rules()["author_simulate_studio_credits"],
        )
        request.app.state.billing_service.meter_action(
            surface="author",
            action_name="simulate",
            account_id=access["account_id"],
            reader_id=access["account_id"],
            world_version_id=world_version_id,
            access=access,
            provider="internal",
            estimated_cost=0.0,
        )
        latest_execution = dict(draft.get("latest_strategy_bundle_execution") or {})
        request.app.state.analytics_service.track(
            "author_strategy_bundle_executed",
            reader_id=access["account_id"],
            account_id=access["account_id"],
            world_id=draft.get("world_id"),
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "campaign_id": payload.campaign_id,
                "strategy_bundle_id": latest_execution.get("strategy_bundle_id"),
                "stop_decision": dict(latest_execution.get("stop_decision") or {}).get("decision"),
                "wallet_type": access.get("wallet_type"),
                "wallet_balance": wallet.get("balance"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return draft
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/drafts/validate")
def validate_draft(payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    account_id = _ensure_author_account_owner(
        request,
        payload.account_id,
        _author_payload_worldpack_owner(payload.worldpack),
    )
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="validate_draft")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                **access,
            },
        )
    worldpack = _with_author_worldpack_owner(payload.worldpack, account_id)
    validation = request.app.state.world_registry.validate_worldpack(worldpack)
    request.app.state.analytics_service.track(
        "author_draft_validated",
        reader_id=account_id,
        account_id=account_id,
        world_id=payload.worldpack.get("world_id"),
        access_tier=access.get("tier_id"),
        payload_json={
            "ok": validation.get("ok"),
            "error_count": len(validation.get("errors", [])),
            "warning_count": len(validation.get("warnings", [])),
            "wallet_type": access.get("wallet_type"),
            "subscription_status": access.get("subscription_status"),
        },
    )
    return {
        **validation,
        "validation_drilldown": request.app.state.authoring_service._build_validation_drilldown(validation),
    }


@router.post("/drafts/{world_version_id}/simulate")
def simulate_draft(
    world_version_id: str,
    request: Request,
    payload: Optional[AuthorDraftSimulateRequest] = None,
    account_id: Optional[str] = None,
    summary_only: bool = False,
) -> Dict[str, Any]:
    try:
        version, resolved_account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=resolved_account_id, action_name="simulate")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    "required_tier": access["required_tier"],
                    "wallet_type": access["wallet_type"],
                    "balance": access["balance"],
                    "reason": access["reason"],
                },
            )
        if summary_only:
            workflow = request.app.state.authoring_service.workflow_summary(
                account_id=resolved_account_id,
                world_version_id=world_version_id,
            )
            draft = request.app.state.authoring_service.get_draft(world_version_id)
            simulation_summary = dict(workflow.get("simulation_summary") or {})
            latest_outcome = dict(draft.get("latest_repair_loop_outcome") or {})
            latest_issues = list(draft.get("latest_quality_issues") or draft.get("issues") or [])
            request.app.state.analytics_service.track(
                "author_draft_simulation_summary_viewed",
                reader_id=access["account_id"],
                account_id=access["account_id"],
                world_id=version.world_id,
                world_version_id=world_version_id,
                access_tier=access.get("tier_id"),
                payload_json={
                    "summary_only": True,
                    "simulation_available": bool(simulation_summary.get("available")),
                    "completed_chapters": simulation_summary.get("completed_chapters"),
                    "pass_rate": simulation_summary.get("pass_rate"),
                    "wallet_type": access.get("wallet_type"),
                    "subscription_status": access.get("subscription_status"),
                },
            )
            return {
                "status": "simulated",
                "summary_only": True,
                "simulation_executed": False,
                "serverless_safe": True,
                "world_version_id": world_version_id,
                "stage": workflow.get("stage"),
                "recommended_action": workflow.get("recommended_action"),
                "completed_chapters": simulation_summary.get("completed_chapters", 0),
                "pass_rate": simulation_summary.get("pass_rate", 0.0),
                "issue_count": len(latest_issues),
                "simulation_summary": simulation_summary,
                "latest_repair_loop_outcome": {
                    "ready_for_validation": latest_outcome.get("ready_for_validation"),
                    "severity_trend": latest_outcome.get("severity_trend"),
                    "issue_count_delta": latest_outcome.get("issue_count_delta"),
                },
                "access": {
                    "allowed": True,
                    "tier_id": access.get("tier_id"),
                    "wallet_type": access.get("wallet_type"),
                    "subscription_status": access.get("subscription_status"),
                },
            }
        interactive_scenarios = [
            {
                **item.model_dump(exclude_none=True),
                "steering_directive": item.steering_directive.model_dump(exclude_none=True),
            }
            for item in (payload.interactive_scenarios if payload else [])
        ]
        include_cross_pack = bool(payload.include_cross_pack) if payload else True
        max_chapters = int(payload.max_chapters if payload else 6)
        report = request.app.state.authoring_service.run_simulation_for_world_version(
            world_version_id,
            include_cross_pack=include_cross_pack,
            max_chapters=max_chapters,
            interactive_scenarios=interactive_scenarios or None,
        )
        wallet = request.app.state.billing_service.consume_studio_credits(
            account_id=access["account_id"],
            amount=request.app.state.monetization_service.metering_rules()["author_simulate_studio_credits"],
        )
        request.app.state.billing_service.meter_action(
            surface="author",
            action_name="simulate",
            account_id=access["account_id"],
            reader_id=access["account_id"],
            world_version_id=world_version_id,
            access=access,
            provider="internal",
            estimated_cost=0.0,
        )
        request.app.state.analytics_service.track(
            "studio_credits_consumed",
            reader_id=access["account_id"],
            account_id=access["account_id"],
            world_version_id=world_version_id,
            payload_json={
                "wallet_type": "studio_credits",
                "balance": wallet.get("balance"),
                "action_type": "author_simulate",
                "tier_id": access.get("tier_id"),
            },
        )
        request.app.state.analytics_service.track(
            "author_draft_simulated",
            reader_id=access["account_id"],
            account_id=access["account_id"],
            world_id=version.world_id,
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "wallet_type": "studio_credits",
                "balance": wallet.get("balance"),
                "tier_id": access.get("tier_id"),
                "completed_chapters": report.get("completed_chapters"),
                "pass_rate": report.get("evaluation_summary", {}).get("pass_rate"),
            },
        )
        return report
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/drafts/{world_version_id}/submit")
def submit_draft(world_version_id: str, request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        version, resolved_account_id = _ensure_author_draft_owner(request, world_version_id)
        access = request.app.state.billing_service.access_check_author(account_id=resolved_account_id, action_name="submit_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        result = request.app.state.authoring_service.submit_for_review(world_version_id)
        request.app.state.analytics_service.track(
            "author_draft_submitted",
            reader_id=resolved_account_id,
            account_id=resolved_account_id,
            world_id=version.world_id,
            world_version_id=world_version_id,
            access_tier=access.get("tier_id"),
            payload_json={
                "status": result.get("status"),
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        _record_author_audit_log(
            request,
            actor_id=resolved_account_id,
            actor_role="author",
            account_id=resolved_account_id,
            world_version_id=world_version_id,
            action_type="author_draft_submitted",
            customer_visible_payload={
                "world_id": version.world_id,
                "world_version_id": world_version_id,
                "status": result.get("status"),
            },
            internal_payload={
                "access_tier": access.get("tier_id"),
                "wallet_type": access.get("wallet_type"),
                "subscription_status": access.get("subscription_status"),
            },
        )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
