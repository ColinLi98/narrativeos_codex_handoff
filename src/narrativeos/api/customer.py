from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.customer_accounts import COMMERCIAL_CUSTOMER_ROLES


router = APIRouter(prefix="/v1/customer", tags=["customer"])


class CampaignCreateRequest(BaseModel):
    campaign_id: Optional[str] = None
    title: str
    target_icp_vertical: str
    cta_text: str
    disclosure_text: str
    selected_channels: list[str] = []
    selected_partner_refs: list[str] = []
    proof_points: list[str] = []
    proof_source_urls: list[str] = []
    proof_artifact_refs: list[str] = []


class CampaignSubmitRequest(BaseModel):
    pass


class DisputeCreateRequest(BaseModel):
    campaign_id: Optional[str] = None
    invoice_preview_id: Optional[str] = None
    billable_event_id: Optional[str] = None
    quality_event_id: Optional[str] = None
    trace_id: Optional[str] = None
    dispute_reason_code: str
    note: Optional[str] = None
    requested_amount_usd: Optional[float] = None


class SupportCaseCreateRequest(BaseModel):
    campaign_id: Optional[str] = None
    invoice_preview_id: Optional[str] = None
    billable_event_id: Optional[str] = None
    quality_event_id: Optional[str] = None
    trace_id: Optional[str] = None
    case_type: str = "general"
    subject: str
    description: str
    priority: str = "medium"


class DataDeletionRequestPayload(BaseModel):
    scope: str = "customer_account"
    requested_payload: Dict[str, Any] = {}


def _customer_identity(request: Request) -> Dict[str, Any]:
    raw_token = request.app.state.auth_service.extract_request_token(
        authorization=request.headers.get("Authorization"),
        cookies=request.cookies,
    )
    if not raw_token:
        raise HTTPException(status_code=401, detail={"code": "customer_auth_missing"})
    try:
        identity = request.app.state.auth_service.resolve_bearer_token(raw_token)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "customer_auth_invalid", "reason": str(exc)}) from exc
    actor_role = str(identity.get("actor_role") or "")
    if actor_role not in COMMERCIAL_CUSTOMER_ROLES:
        raise HTTPException(status_code=403, detail={"code": "customer_role_forbidden", "actor_role": actor_role})
    return identity


def _resolve_customer_account(
    request: Request,
    *,
    identity: Dict[str, Any],
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    service = request.app.state.customer_account_service
    actor_role = str(identity.get("actor_role") or "")
    identity_account_id = str(identity.get("account_id") or identity.get("actor_id") or "").strip()
    resolved_customer_account_id = str(customer_account_id or "").strip() or None
    resolved_account_id = str(account_id or "").strip() or None
    if actor_role == "customer":
        target_account_id = resolved_account_id or identity_account_id
        if target_account_id != identity_account_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "customer_account_ownership_mismatch",
                    "provided_account_id": target_account_id,
                    "token_account_id": identity_account_id,
                },
            )
        existing = service.repository.get_customer_account_by_account_id(target_account_id, default=None)
        if existing is None:
            service.ensure_customer_account(
                account_id=target_account_id,
                display_name=identity.get("display_name") or identity.get("actor_id"),
            )
        detail = service.customer_account_detail(account_id=target_account_id)
        if resolved_customer_account_id and detail["customer_account"]["customer_account_id"] != resolved_customer_account_id:
            raise HTTPException(status_code=403, detail={"code": "customer_account_ownership_mismatch"})
        return detail
    if resolved_customer_account_id:
        return service.customer_account_detail(customer_account_id=resolved_customer_account_id)
    if resolved_account_id:
        return service.customer_account_detail(account_id=resolved_account_id)
    if identity_account_id and service.repository.get_customer_account_by_account_id(identity_account_id, default=None):
        return service.customer_account_detail(account_id=identity_account_id)
    raise HTTPException(status_code=400, detail={"code": "customer_account_target_required"})


def _customer_safe_response(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    return request.app.state.commercial_audit_service.customer_safe_payload(payload)


@router.get("/account")
def customer_account(
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    return _customer_safe_response(request, {
        "identity": {
            "actor_id": identity.get("actor_id"),
            "account_id": identity.get("account_id"),
            "actor_role": identity.get("actor_role"),
            "display_name": identity.get("display_name"),
        },
        **detail,
    })


@router.get("/invoice-preview")
def customer_invoice_preview(
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
    period_start: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    return _customer_safe_response(request, request.app.state.commercial_billing_service.invoice_preview(
        account_id=resolved_account_id,
        period_start=period_start,
    ))


@router.get("/workspace")
def customer_workspace(
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
    period_start: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    return _customer_safe_response(request, request.app.state.customer_workspace_service.workspace(
        account_id=resolved_account_id,
        period_start=period_start,
    ))


@router.get("/campaigns/{campaign_id}/report")
def customer_campaign_report(
    campaign_id: str,
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
    period_start: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    return _customer_safe_response(request, request.app.state.customer_workspace_service.campaign_report(
        account_id=resolved_account_id,
        campaign_id=campaign_id,
        period_start=period_start,
    ))


@router.post("/campaigns")
def create_customer_campaign(payload: CampaignCreateRequest, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    try:
        return request.app.state.customer_campaign_service.create_or_update_campaign(
            account_id=resolved_account_id,
            payload=payload.model_dump(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "campaign_account_ownership_mismatch", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "campaign_create_invalid", "reason": str(exc)}) from exc


@router.post("/campaigns/{campaign_id}/submit")
def submit_customer_campaign(campaign_id: str, payload: CampaignSubmitRequest, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    try:
        return request.app.state.customer_campaign_service.submit_campaign(
            account_id=resolved_account_id,
            campaign_id=campaign_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "campaign_account_ownership_mismatch", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "campaign_submit_invalid", "reason": str(exc)}) from exc


@router.post("/disputes")
def create_customer_dispute(payload: DisputeCreateRequest, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    try:
        dispute = request.app.state.commercial_support_service.create_dispute(
            account_id=resolved_account_id,
            requested_by=str(identity.get("actor_id") or resolved_account_id),
            payload=payload.model_dump(),
        )
        return _customer_safe_response(request, {"dispute": dispute})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "dispute_create_invalid", "reason": str(exc)}) from exc


@router.get("/disputes")
def customer_disputes(request: Request, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    return _customer_safe_response(request, request.app.state.commercial_support_service.list_disputes(account_id=resolved_account_id, status=status, limit=limit))


@router.post("/support")
def create_customer_support_case(payload: SupportCaseCreateRequest, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    try:
        support_case = request.app.state.commercial_support_service.create_support_case(
            account_id=resolved_account_id,
            requested_by=str(identity.get("actor_id") or resolved_account_id),
            payload=payload.model_dump(),
        )
        return _customer_safe_response(request, {"support_case": support_case})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "support_case_create_invalid", "reason": str(exc)}) from exc


@router.get("/support")
def customer_support_cases(request: Request, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    return _customer_safe_response(request, request.app.state.commercial_support_service.list_support_cases(account_id=resolved_account_id, status=status, limit=limit))


@router.get("/invoices")
def customer_invoices(request: Request, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    payload = request.app.state.stripe_invoicing_service.list_invoices(account_id=resolved_account_id, limit=limit)
    if status:
        payload["invoices"] = [item for item in payload.get("invoices", []) if item.get("status") == status]
    return _customer_safe_response(request, payload)


@router.get("/invoices/{invoice_id}")
def customer_invoice_detail(invoice_id: str, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    payload = request.app.state.stripe_invoicing_service.get_invoice_detail(invoice_id=invoice_id)
    if str((payload.get("invoice") or {}).get("account_id") or "") != resolved_account_id:
        raise HTTPException(status_code=403, detail={"code": "customer_account_ownership_mismatch"})
    return _customer_safe_response(request, payload)


@router.get("/exports/{report_type}")
def customer_export(
    report_type: str,
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
    period_start: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    try:
        return _customer_safe_response(request, request.app.state.customer_workspace_service.export_payload(
            account_id=resolved_account_id,
            report_type=report_type,
            period_start=period_start,
        ))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "customer_export_unknown", "reason": str(exc)}) from exc


@router.get("/audit-export")
def customer_audit_export(
    request: Request,
    customer_account_id: Optional[str] = None,
    account_id: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(
        request,
        identity=identity,
        customer_account_id=customer_account_id,
        account_id=account_id,
    )
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    payload = request.app.state.commercial_audit_service.customer_audit_export(
        account_id=resolved_account_id,
        requested_by=str(identity.get("actor_id") or resolved_account_id),
        period_start=period_start,
        period_end=period_end,
    )
    return payload


@router.post("/data-deletion-request")
def customer_data_deletion_request(payload: DataDeletionRequestPayload, request: Request) -> Dict[str, Any]:
    identity = _customer_identity(request)
    detail = _resolve_customer_account(request, identity=identity)
    resolved_account_id = str((detail.get("customer_account") or {}).get("account_id") or "")
    deletion_request = request.app.state.commercial_audit_service.create_data_deletion_request(
        account_id=resolved_account_id,
        requested_by=str(identity.get("actor_id") or resolved_account_id),
        scope=payload.scope,
        requested_payload=payload.requested_payload,
    )
    return _customer_safe_response(request, {"deletion_request": deletion_request})
