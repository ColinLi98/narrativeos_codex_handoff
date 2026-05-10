from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/v1/billing", tags=["billing"])


@router.post("/stripe/webhook")
async def stripe_billing_webhook(request: Request) -> Dict[str, Any]:
    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature") or ""
    try:
        return request.app.state.stripe_invoicing_service.ingest_stripe_webhook(
            raw_body=raw_body,
            signature=signature,
        )
    except ValueError as exc:
        reason = str(exc)
        status_code = 400
        if reason in {"stripe_webhook_not_configured", "stripe_sdk_missing"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": "stripe_billing_webhook_failed", "reason": reason}) from exc
