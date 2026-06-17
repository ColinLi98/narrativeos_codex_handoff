from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .billing import BillingService
from .commercial_audit import CommercialAuditService
from .customer_accounts import CustomerAccountService
from .monetization import MonetizationService
from ..persistence.repositories import SQLAlchemyPlatformRepository


class StripeInvoicingService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        monetization_service: MonetizationService,
        billing_service: BillingService,
        customer_account_service: CustomerAccountService,
        audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.monetization = monetization_service
        self.billing = billing_service
        self.customer_accounts = customer_account_service
        self.audit = audit_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        return value

    def _billing_profile(self, *, customer_account_id: str) -> Optional[Dict[str, Any]]:
        profiles = self.repository.list_billing_profiles(customer_account_id=customer_account_id, limit=1)
        return profiles[0] if profiles else None

    def _invoice_status(self, stripe_status: Optional[str], *, fallback: str = "issued") -> str:
        status = str(stripe_status or "").strip().lower()
        return {
            "draft": "draft",
            "open": "issued",
            "paid": "paid",
            "void": "void",
            "uncollectible": "failed",
        }.get(status, fallback)

    def _line_items(self, invoice_preview: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for item in list(invoice_preview.get("line_items_json") or []):
            amount = float(item.get("line_amount_usd") or 0.0)
            if amount <= 0:
                continue
            items.append(
                {
                    "metric_type": item.get("metric_type"),
                    "description": f"{item.get('display_name') or item.get('metric_type')} ({item.get('billable_units') or 0} billable units)",
                    "amount_usd": amount,
                }
            )
        return items

    def issue_invoice(self, *, invoice_preview_id: str, requested_by: str) -> Dict[str, Any]:
        preview = self.repository.get_invoice_preview(invoice_preview_id)
        customer = self.customer_accounts.customer_account_detail(account_id=preview["account_id"])["customer_account"]
        profile = self._billing_profile(customer_account_id=customer["customer_account_id"])
        customer_email = (profile or {}).get("invoice_email") or (self.repository.get_auth_identity_profile(preview["account_id"], default={}) or {}).get("email_address")
        customer_ref = (profile or {}).get("provider_customer_ref")
        stripe_customer = self.monetization.ensure_stripe_customer(
            customer_email=customer_email,
            customer_id=customer_ref,
            metadata={"account_id": preview["account_id"], "invoice_preview_id": invoice_preview_id},
        )
        if not customer_ref and profile is not None:
            self.repository.save_billing_profile(
                {
                    **profile,
                    "provider_customer_ref": stripe_customer.get("id"),
                    "profile_payload_json": dict(profile.get("profile_payload_json") or {}),
                }
            )
        line_items = self._line_items(preview)
        issued = self.monetization.issue_stripe_invoice(
            customer_id=stripe_customer.get("id"),
            currency="USD",
            line_items=line_items,
            metadata={"account_id": preview["account_id"], "invoice_preview_id": invoice_preview_id},
        )
        invoice = self.repository.save_invoice_issuance(
            {
                "invoice_id": f"invoice_{invoice_preview_id}",
                "invoice_preview_id": invoice_preview_id,
                "customer_account_id": customer["customer_account_id"],
                "account_id": preview["account_id"],
                "provider": "stripe",
                "provider_invoice_ref": issued.get("id"),
                "provider_customer_ref": stripe_customer.get("id"),
                "status": self._invoice_status(issued.get("status")),
                "currency": "USD",
                "subtotal_amount_usd": preview.get("subtotal_amount_usd") or 0.0,
                "total_due_usd": preview.get("total_due_usd") or 0.0,
                "hosted_invoice_url": issued.get("hosted_invoice_url"),
                "invoice_pdf_url": issued.get("invoice_pdf"),
                "issued_at": self._utcnow(),
                "invoice_payload": issued,
            }
        )
        self.audit.record_audit_log(
            actor_id=requested_by,
            actor_role="reviewer",
            account_id=preview["account_id"],
            object_type="invoice",
            object_id=invoice["invoice_id"],
            action_type="invoice_issued",
            source_surface="ops",
            customer_visible_payload={"invoice": invoice},
            internal_payload={"invoice_preview": preview, "provider_payload": issued},
        )
        return {
            "invoice": invoice,
            "stripe_customer": stripe_customer,
        }

    def list_invoices(self, *, account_id: Optional[str] = None, customer_account_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        invoices = self.repository.list_invoice_issuances(account_id=account_id, customer_account_id=customer_account_id, limit=limit)
        transactions = self.repository.list_payment_transactions(account_id=account_id, limit=limit * 2 if account_id else limit * 2)
        return {
            "invoices": invoices,
            "transactions": transactions,
            "summary": {
                "invoice_count": len(invoices),
                "paid_count": sum(1 for item in invoices if str(item.get("status") or "") == "paid"),
                "failed_count": sum(1 for item in invoices if str(item.get("status") or "") == "failed"),
                "void_count": sum(1 for item in invoices if str(item.get("status") or "") == "void"),
                "refunded_count": sum(1 for item in invoices if str(item.get("status") or "") == "refunded"),
            },
        }

    def get_invoice_detail(self, *, invoice_id: str) -> Dict[str, Any]:
        invoice = self.repository.get_invoice_issuance(invoice_id)
        transactions = self.repository.list_payment_transactions(invoice_id=invoice_id, limit=50)
        credit_notes = self.repository.list_credit_notes(invoice_id=invoice_id, limit=50)
        retries = self.repository.list_payment_retry_attempts(invoice_id=invoice_id, limit=50)
        dunning = self.repository.list_dunning_events(invoice_id=invoice_id, limit=50)
        return {
            "invoice": invoice,
            "transactions": transactions,
            "credit_notes": credit_notes,
            "payment_retry_attempts": retries,
            "dunning_events": dunning,
        }

    def _record_payment_transaction(
        self,
        *,
        invoice: Dict[str, Any],
        provider_transaction_ref: Optional[str],
        transaction_type: str,
        status: str,
        amount_usd: float,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.repository.save_payment_transaction(
            {
                "invoice_id": invoice["invoice_id"],
                "customer_account_id": invoice.get("customer_account_id"),
                "account_id": invoice["account_id"],
                "provider": "stripe",
                "provider_transaction_ref": provider_transaction_ref,
                "transaction_type": transaction_type,
                "status": status,
                "amount_usd": amount_usd,
                "currency": "USD",
                "trace_id": payload.get("trace_id"),
                "transaction_payload": self._json_safe(payload),
            }
        )

    def _record_webhook(self, *, event: Dict[str, Any], invoice_id: Optional[str], account_id: Optional[str], processing_result: Dict[str, Any], status: str = "processed") -> Dict[str, Any]:
        return self.repository.save_provider_webhook_event(
            {
                "provider": "stripe",
                "provider_event_id": str(event.get("id") or ""),
                "event_type": str(event.get("type") or ""),
                "status": status,
                "invoice_id": invoice_id,
                "account_id": account_id,
                "payload": self._json_safe(event),
                "processing_result": self._json_safe(processing_result),
                "processed_at": self._utcnow(),
            }
        )

    def _invoice_from_provider_ref(self, provider_invoice_ref: str) -> Dict[str, Any]:
        return self.repository.get_invoice_issuance_by_provider_ref(provider_invoice_ref)

    def ingest_stripe_webhook(self, *, raw_body: bytes, signature: str) -> Dict[str, Any]:
        webhook_secret = self.billing._stripe_webhook_secret()
        if not webhook_secret:
            raise ValueError("stripe_webhook_not_configured")
        try:
            import stripe  # type: ignore
        except ModuleNotFoundError as exc:
            raise ValueError("stripe_sdk_missing") from exc
        stripe.api_key = self.monetization.stripe_checkout.secret_key
        stripe.api_version = self.monetization.stripe_checkout.api_version
        try:
            stripe_event = stripe.Webhook.construct_event(payload=raw_body, sig_header=signature, secret=webhook_secret)
        except Exception as exc:
            raise ValueError("stripe_webhook_signature_invalid") from exc
        event = stripe_event.to_dict() if hasattr(stripe_event, "to_dict") else dict(stripe_event)
        event_type = str(event.get("type") or "")
        data_object = dict(dict(event.get("data") or {}).get("object") or {})
        provider_invoice_ref = str(data_object.get("invoice") or data_object.get("id") or "").strip()
        invoice = self._invoice_from_provider_ref(provider_invoice_ref) if provider_invoice_ref else None
        processing_result: Dict[str, Any] = {}
        if event_type == "invoice.paid" and invoice:
            invoice = self.repository.save_invoice_issuance(
                {
                    **invoice,
                    "status": "paid",
                    "invoice_payload_json": dict(invoice.get("invoice_payload_json") or {}),
                    "paid_at": self._utcnow(),
                }
            )
            processing_result["invoice"] = invoice
            processing_result["payment_transaction"] = self._record_payment_transaction(
                invoice=invoice,
                provider_transaction_ref=str(data_object.get("payment_intent") or data_object.get("charge") or provider_invoice_ref),
                transaction_type="payment",
                status="paid",
                amount_usd=float(invoice.get("total_due_usd") or 0.0),
                payload=data_object,
            )
        elif event_type == "invoice.payment_failed" and invoice:
            invoice = self.repository.save_invoice_issuance(
                {
                    **invoice,
                    "status": "failed",
                    "invoice_payload_json": dict(invoice.get("invoice_payload_json") or {}),
                }
            )
            processing_result["invoice"] = invoice
            processing_result["payment_transaction"] = self._record_payment_transaction(
                invoice=invoice,
                provider_transaction_ref=str(data_object.get("payment_intent") or data_object.get("charge") or provider_invoice_ref),
                transaction_type="payment",
                status="failed",
                amount_usd=float(invoice.get("total_due_usd") or 0.0),
                payload=data_object,
            )
            processing_result["payment_retry_attempt"] = self.repository.save_payment_retry_attempt(
                {
                    "invoice_id": invoice["invoice_id"],
                    "customer_account_id": invoice.get("customer_account_id"),
                    "account_id": invoice["account_id"],
                    "provider": "stripe",
                    "status": "planned",
                    "retry_reason": "invoice_payment_failed",
                    "attempt_count": 1,
                    "next_retry_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "retry_payload": self._json_safe(data_object),
                }
            )
            processing_result["dunning_event"] = self.repository.save_dunning_event(
                {
                    "invoice_id": invoice["invoice_id"],
                    "customer_account_id": invoice.get("customer_account_id"),
                    "account_id": invoice["account_id"],
                    "status": "scheduled",
                    "step": "payment_failed_initial",
                    "event_payload": self._json_safe(data_object),
                }
            )
        elif event_type == "invoice.voided" and invoice:
            invoice = self.repository.save_invoice_issuance(
                {
                    **invoice,
                    "status": "void",
                    "invoice_payload_json": dict(invoice.get("invoice_payload_json") or {}),
                    "voided_at": self._utcnow(),
                }
            )
            processing_result["invoice"] = invoice
        elif event_type in {"charge.refunded", "refund.updated"} and invoice:
            invoice = self.repository.save_invoice_issuance(
                {
                    **invoice,
                    "status": "refunded",
                    "invoice_payload_json": dict(invoice.get("invoice_payload_json") or {}),
                }
            )
            processing_result["invoice"] = invoice
            processing_result["payment_transaction"] = self._record_payment_transaction(
                invoice=invoice,
                provider_transaction_ref=str(data_object.get("id") or provider_invoice_ref),
                transaction_type="refund",
                status="refunded",
                amount_usd=float(invoice.get("total_due_usd") or 0.0),
                payload=data_object,
            )
        elif event_type == "credit_note.created" and invoice:
            credit_note = self.repository.save_credit_note(
                {
                    "invoice_id": invoice["invoice_id"],
                    "customer_account_id": invoice.get("customer_account_id"),
                    "account_id": invoice["account_id"],
                    "provider": "stripe",
                    "provider_credit_note_ref": data_object.get("id"),
                    "status": "issued",
                    "amount_usd": float(data_object.get("amount", 0) or 0) / 100.0,
                    "reason": data_object.get("reason"),
                    "credit_payload": data_object,
                }
            )
            processing_result["credit_note"] = credit_note
        webhook = self._record_webhook(
            event=event,
            invoice_id=(processing_result.get("invoice") or {}).get("invoice_id") if isinstance(processing_result.get("invoice"), dict) else (invoice or {}).get("invoice_id") if invoice else None,
            account_id=(invoice or {}).get("account_id") if invoice else None,
            processing_result=processing_result,
        )
        return {"webhook_event": webhook, **processing_result}

    def replay_webhook(self, provider_webhook_event_id: str) -> Dict[str, Any]:
        event = self.repository.get_provider_webhook_event(provider_webhook_event_id)
        # Limited replay: return stored event until full replay orchestration is needed.
        return {"webhook_event": event, "replayed": False}

    def retry_invoice_payment(self, *, invoice_id: str, requested_by: str) -> Dict[str, Any]:
        invoice = self.repository.get_invoice_issuance(invoice_id)
        attempt = self.repository.save_payment_retry_attempt(
            {
                "invoice_id": invoice_id,
                "customer_account_id": invoice.get("customer_account_id"),
                "account_id": invoice["account_id"],
                "provider": "stripe",
                "status": "planned",
                "retry_reason": "manual_retry",
                "attempt_count": len(self.repository.list_payment_retry_attempts(invoice_id=invoice_id, limit=100)) + 1,
                "next_retry_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "retry_payload": {"requested_by": requested_by},
            }
        )
        dunning = self.repository.save_dunning_event(
            {
                "invoice_id": invoice_id,
                "customer_account_id": invoice.get("customer_account_id"),
                "account_id": invoice["account_id"],
                "status": "scheduled",
                "step": "manual_retry_requested",
                "event_payload": self._json_safe({"requested_by": requested_by}),
            }
        )
        return {"payment_retry_attempt": attempt, "dunning_event": dunning}
