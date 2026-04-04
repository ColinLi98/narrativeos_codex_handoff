from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class SaveDraftRequest(BaseModel):
    worldpack: Dict[str, Any]
    change_context: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None


class AuthorBriefRequest(BaseModel):
    brief: Dict[str, Any]
    account_id: Optional[str] = None


class AuthorAccountRequest(BaseModel):
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
    drafts = request.app.state.repository.list_world_versions(status="draft")
    return {"drafts": drafts}


@router.post("/drafts")
def save_draft(payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    account_id = _resolve_account_value(request, payload.account_id or payload.worldpack.get("manifest", {}).get("author_id") or "web_author")
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="save_draft")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                **access,
            },
        )
    draft = request.app.state.authoring_service.save_draft(payload.worldpack, change_context=payload.change_context)
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
    return request.app.state.billing_service.author_access_snapshot(
        account_id=_resolve_account_value(request, account_id),
        world_version_id=world_version_id,
    )


@router.get("/workflow")
def author_workflow(
    request: Request,
    account_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    return request.app.state.authoring_service.workflow_summary(
        account_id=_resolve_account_value(request, account_id),
        world_version_id=world_version_id,
    )


@router.get("/drafts/{world_version_id}/collaboration")
def collaboration_summary(world_version_id: str, request: Request) -> Dict[str, Any]:
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
    resolved_reviewer_id = _resolve_identity_value(request, reviewer_id)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.reviewer_inbox(
            reviewer_id=str(resolved_reviewer_id or ""),
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
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.request_approval(
            world_version_id=world_version_id,
            payload=_apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/drafts/{world_version_id}/approval/decision")
def decide_author_approval(
    world_version_id: str,
    payload: AuthorApprovalDecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.approval_decision(
            world_version_id=world_version_id,
            payload=_apply_identity(request, payload.model_dump(), actor_field=None, role_field=None, reviewer_field="reviewer_id"),
        )
    )


@router.post("/notifications/{notification_id}/status")
def update_author_notification_status(
    notification_id: str,
    payload: AuthorNotificationStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.update_notification_status(
            notification_id,
            payload=_apply_identity(request, payload.model_dump(), actor_field=None, role_field=None, recipient_field="recipient_id"),
        )
    )


@router.post("/notifications/bulk-status")
def bulk_update_author_notification_status(
    payload: AuthorNotificationBulkStatusRequest,
    request: Request,
) -> Dict[str, Any]:
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.bulk_update_notification_status(
            _apply_identity(request, payload.model_dump(), actor_field=None, role_field=None, recipient_field="recipient_id"),
        )
    )


@router.post("/comments/{thread_id}/watchers")
def add_author_thread_watcher(
    thread_id: str,
    payload: AuthorThreadWatcherRequest,
    request: Request,
) -> Dict[str, Any]:
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
    resolved_actor_id = _resolve_identity_value(request, actor_id)
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.notification_preferences(str(resolved_actor_id or ""))
    )


@router.post("/notification-preferences")
def update_author_notification_preference(
    payload: AuthorNotificationPreferenceRequest,
    request: Request,
) -> Dict[str, Any]:
    return _execute_collaboration_action(
        lambda: request.app.state.author_collaboration_service.update_notification_preference(
            _apply_identity(request, payload.model_dump()),
        )
    )


@router.post("/drafts/from-brief")
def create_draft_from_brief(payload: AuthorBriefRequest, request: Request) -> Dict[str, Any]:
    account_id = _resolve_account_value(
        request,
        payload.account_id or payload.brief.get("account_id") or payload.brief.get("author_id") or "web_author",
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
    draft = request.app.state.authoring_service.create_draft_from_brief(
        {**payload.brief, "account_id": account_id, "author_id": payload.brief.get("author_id") or account_id}
    )
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
    try:
        return request.app.state.authoring_service.get_draft(world_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/drafts/{world_version_id}")
def update_draft(world_version_id: str, payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
        account_id = _resolve_account_value(request, payload.account_id or version.author_id)
        access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="update_draft")
        if not access["allowed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "author_entitlement_required",
                    **access,
                },
            )
        draft = request.app.state.authoring_service.update_draft(world_version_id, payload.worldpack, change_context=payload.change_context)
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


@router.post("/drafts/validate")
def validate_draft(payload: SaveDraftRequest, request: Request) -> Dict[str, Any]:
    account_id = _resolve_account_value(request, payload.account_id or payload.worldpack.get("manifest", {}).get("author_id") or "web_author")
    access = request.app.state.billing_service.access_check_author(account_id=account_id, action_name="validate_draft")
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "author_entitlement_required",
                **access,
            },
        )
    validation = request.app.state.world_registry.validate_worldpack(payload.worldpack)
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
def simulate_draft(world_version_id: str, request: Request, account_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        version = request.app.state.repository.get_world_version(world_version_id)
        resolved_account_id = _resolve_account_value(request, account_id or version.author_id)
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
        report = request.app.state.authoring_service.run_simulation_for_world_version(world_version_id)
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
        version = request.app.state.repository.get_world_version(world_version_id)
        resolved_account_id = _resolve_account_value(request, account_id or version.author_id)
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
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
