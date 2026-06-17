from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..commercialization.config import load_billing_metering
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .billing import BillingService
from .commercial_audit import CommercialAuditService
from .customer_accounts import CustomerAccountService
from .observability import ObservabilityService
from .ops_quality_projection import OpsQualityProjectionService


COMMERCIAL_BILLABLE_METRICS = frozenset({"validated_presented", "validated_handoff", "validated_conversion"})
COMMERCIAL_BILLABLE_STATUSES = frozenset({"recorded", "approved", "disputed", "credited", "reversed", "refunded"})


class CommercialBillingService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        billing_service: BillingService,
        customer_account_service: CustomerAccountService,
        audit_service: CommercialAuditService,
        observability_service: ObservabilityService,
        quality_projection_service: OpsQualityProjectionService,
    ) -> None:
        self.repository = repository
        self.billing = billing_service
        self.customer_accounts = customer_account_service
        self.audit = audit_service
        self.observability = observability_service
        self.quality_projection = quality_projection_service

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _period_bounds(self, *, period_start: Optional[str] = None) -> Tuple[str, str, str]:
        if period_start:
            normalized = str(period_start).replace("Z", "+00:00")
            start_dt = datetime.fromisoformat(normalized)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            start_dt = start_dt.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            now = self._utcnow()
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        period_key = start_dt.strftime("%Y%m")
        return start_dt.isoformat(), next_month.isoformat(), period_key

    def _config(self) -> Dict[str, Any]:
        return load_billing_metering()

    def _metric_config(self, metric_type: str, plan_id: str) -> Dict[str, Any]:
        config = self._config()
        metrics = dict(config.get("metrics") or {})
        metric = dict(metrics.get(metric_type) or {})
        if not metric:
            raise KeyError("unknown_billable_metric:%s" % metric_type)
        included = float(dict(metric.get("included_units") or {}).get(plan_id, 0) or 0)
        unit_price = float(dict(metric.get("unit_price_usd") or {}).get(plan_id, 0.0) or 0.0)
        return {
            "metric_type": metric_type,
            "display_name": metric.get("display_name") or metric_type,
            "included_units": included,
            "unit_price_usd": unit_price,
            "config_version": config.get("config_version"),
        }

    def _credit_balance(self, *, account_id: str, customer_account_id: Optional[str]) -> Dict[str, Any]:
        balance_type = str((self._config().get("credit_policy") or {}).get("default_balance_type") or "commercial_credit_usd")
        balances = self.repository.list_credit_balances(account_id=account_id, balance_type=balance_type)
        if balances:
            return balances[0]
        return self.repository.save_credit_balance(
            {
                "credit_balance_id": f"credit_balance_{account_id}",
                "account_id": account_id,
                "customer_account_id": customer_account_id,
                "balance_type": balance_type,
                "amount_usd": 0.0,
                "source_ref": {"kind": "system_default", "account_id": account_id},
            }
        )

    def _trace_event_candidates(self, *, account_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        events = self.quality_projection.list_projected_quality_events(account_id=account_id, limit=1000)
        feedback_items = self.quality_projection.list_projected_quality_feedback_items(account_id=account_id, limit=1000)
        receipts = self.observability.list_runtime_receipts(account_id=account_id, limit=1000)
        receipts_by_trace = {
            str(item.get("trace_id") or "").strip(): item
            for item in receipts
            if str(item.get("trace_id") or "").strip()
        }
        feedback_by_trace: Dict[str, Dict[str, Any]] = {}
        for item in feedback_items:
            trace = str(item.get("trace_id") or "").strip()
            if not trace:
                continue
            if trace not in feedback_by_trace:
                feedback_by_trace[trace] = item
            else:
                current = feedback_by_trace[trace]
                if str(item.get("created_at") or "") < str(current.get("created_at") or ""):
                    feedback_by_trace[trace] = item
        return events, receipts_by_trace, feedback_by_trace

    def _billable_candidates(self, *, account_id: str, plan_id: str) -> List[Dict[str, Any]]:
        events, receipts_by_trace, feedback_by_trace = self._trace_event_candidates(account_id=account_id)
        billable: List[Dict[str, Any]] = []
        for event in events:
            trace_id = str(event.get("trace_id") or "").strip()
            if not trace_id:
                continue
            quality_event_id = str(event.get("event_id") or "").strip()
            if str(event.get("status") or "") == "passed" and str(event.get("source_surface") or "") == "reader":
                receipt = receipts_by_trace.get(trace_id)
                if receipt and str(receipt.get("response_status") or "") == "ok":
                    metric = self._metric_config("validated_presented", plan_id)
                    billable.append(
                        {
                            "billable_event_id": f"billable_presented_{trace_id}",
                            "metric_type": "validated_presented",
                            "trace_id": trace_id,
                            "quality_event_id": quality_event_id,
                            "runtime_receipt_event_id": receipt.get("event_id"),
                            "feedback_item_id": None,
                            "source_surface": event.get("source_surface"),
                            "world_version_id": event.get("world_version_id"),
                            "session_id": event.get("session_id"),
                            "reason_codes": list(event.get("reason_codes") or []),
                            "quantity": 1.0,
                            "unit_price_usd": metric["unit_price_usd"],
                            "amount_usd": metric["unit_price_usd"],
                            "payload": {
                                "metric_config": metric,
                                "quality_status": event.get("status"),
                                "runtime_receipt_status": receipt.get("response_status"),
                            },
                        }
                    )
            if str(event.get("status") or "") == "passed" and str(event.get("source_surface") or "") == "publish":
                metric = self._metric_config("validated_handoff", plan_id)
                billable.append(
                    {
                        "billable_event_id": f"billable_handoff_{trace_id}",
                        "metric_type": "validated_handoff",
                        "trace_id": trace_id,
                        "quality_event_id": quality_event_id,
                        "runtime_receipt_event_id": None,
                        "feedback_item_id": None,
                        "source_surface": event.get("source_surface"),
                        "world_version_id": event.get("world_version_id"),
                        "session_id": event.get("session_id"),
                        "reason_codes": list(event.get("reason_codes") or []),
                        "quantity": 1.0,
                        "unit_price_usd": metric["unit_price_usd"],
                        "amount_usd": metric["unit_price_usd"],
                        "payload": {
                            "metric_config": metric,
                            "quality_status": event.get("status"),
                            "handoff_kind": "publish_quality_passed",
                        },
                    }
                )
            positive_feedback = feedback_by_trace.get(trace_id)
            if (
                str(event.get("status") or "") == "passed"
                and positive_feedback
                and str(positive_feedback.get("signal") or "") in {"explicit_positive", "positive_proxy"}
            ):
                metric = self._metric_config("validated_conversion", plan_id)
                billable.append(
                    {
                        "billable_event_id": f"billable_conversion_{trace_id}",
                        "metric_type": "validated_conversion",
                        "trace_id": trace_id,
                        "quality_event_id": quality_event_id,
                        "runtime_receipt_event_id": None,
                        "feedback_item_id": positive_feedback.get("feedback_item_id"),
                        "source_surface": event.get("source_surface"),
                        "world_version_id": event.get("world_version_id"),
                        "session_id": event.get("session_id"),
                        "reason_codes": list(event.get("reason_codes") or []),
                        "quantity": 1.0,
                        "unit_price_usd": metric["unit_price_usd"],
                        "amount_usd": metric["unit_price_usd"],
                        "payload": {
                            "metric_config": metric,
                            "feedback_signal": positive_feedback.get("signal"),
                            "feedback_type": positive_feedback.get("feedback_type"),
                        },
                    }
                )
        deduped = {item["billable_event_id"]: item for item in billable}
        return list(deduped.values())

    def sync_account_billing(self, *, account_id: str, period_start: Optional[str] = None) -> Dict[str, Any]:
        if self.repository.get_customer_account_by_account_id(account_id, default=None) is None:
            self.customer_accounts.ensure_customer_account(account_id=account_id, display_name=account_id)
        customer_detail = self.customer_accounts.customer_account_detail(account_id=account_id)
        customer = dict(customer_detail.get("customer_account") or {})
        plan = dict(customer_detail.get("plan") or {})
        billing_period_start, billing_period_end, period_key = self._period_bounds(period_start=period_start)
        ledger_id = f"usage_ledger_{account_id}_{period_key}"
        customer_account_id = customer.get("customer_account_id")
        plan_id = str(plan.get("plan_id") or customer.get("plan_id") or "play_pass")
        billable_candidates = self._billable_candidates(account_id=account_id, plan_id=plan_id)
        saved_billable_events: List[Dict[str, Any]] = []
        for candidate in billable_candidates:
            existing = self.repository.get_billable_event(candidate["billable_event_id"], default=None)
            status = str((existing or {}).get("status") or "recorded")
            saved_billable_events.append(
                self.repository.save_billable_event(
                    {
                        "billable_event_id": candidate["billable_event_id"],
                        "usage_ledger_id": ledger_id,
                        "account_id": account_id,
                        "customer_account_id": customer_account_id,
                        "plan_id": plan_id,
                        "billable_metric": candidate["metric_type"],
                        "status": status,
                        "trace_id": candidate["trace_id"],
                        "quality_event_id": candidate["quality_event_id"],
                        "runtime_receipt_event_id": candidate["runtime_receipt_event_id"],
                        "feedback_item_id": candidate["feedback_item_id"],
                        "source_surface": candidate["source_surface"],
                        "world_version_id": candidate["world_version_id"],
                        "session_id": candidate["session_id"],
                        "quantity": candidate["quantity"],
                        "unit_price_usd": candidate["unit_price_usd"],
                        "amount_usd": candidate["amount_usd"],
                        "reason_codes": candidate["reason_codes"],
                        "event_payload": candidate["payload"],
                    }
                )
            )

        metric_counts: Dict[str, int] = {key: 0 for key in COMMERCIAL_BILLABLE_METRICS}
        subtotal = 0.0
        disputed = 0.0
        credited = 0.0
        reversed_amount = 0.0
        line_items: List[Dict[str, Any]] = []
        overage_flags: List[Dict[str, Any]] = []
        events_by_metric: Dict[str, List[Dict[str, Any]]] = {}
        for item in saved_billable_events:
            events_by_metric.setdefault(str(item.get("billable_metric") or ""), []).append(item)
        for metric_type in COMMERCIAL_BILLABLE_METRICS:
            metric_events = list(events_by_metric.get(metric_type) or [])
            active_events = [item for item in metric_events if str(item.get("status") or "") not in {"disputed", "credited", "reversed", "refunded"}]
            metric_counts[metric_type] = len(active_events)
            metric_conf = self._metric_config(metric_type, plan_id)
            included_units = float(metric_conf["included_units"])
            observed_units = float(len(active_events))
            billable_units = max(0.0, observed_units - included_units)
            line_amount = round(billable_units * float(metric_conf["unit_price_usd"]), 6)
            subtotal += line_amount
            disputed += sum(float(item.get("amount_usd") or 0.0) for item in metric_events if str(item.get("status") or "") == "disputed")
            credited += sum(float(item.get("amount_usd") or 0.0) for item in metric_events if str(item.get("status") or "") == "credited")
            reversed_amount += sum(float(item.get("amount_usd") or 0.0) for item in metric_events if str(item.get("status") or "") == "reversed")
            line_items.append(
                {
                    "metric_type": metric_type,
                    "display_name": metric_conf["display_name"],
                    "observed_units": observed_units,
                    "included_units": included_units,
                    "billable_units": billable_units,
                    "unit_price_usd": metric_conf["unit_price_usd"],
                    "line_amount_usd": line_amount,
                }
            )
            flag_status = "active" if billable_units > 0 else "resolved"
            overage_flags.append(
                self.repository.save_overage_flag(
                    {
                        "overage_flag_id": f"overage_{account_id}_{metric_type}",
                        "account_id": account_id,
                        "customer_account_id": customer_account_id,
                        "plan_id": plan_id,
                        "metric_type": metric_type,
                        "status": flag_status,
                        "observed_units": observed_units,
                        "included_units": included_units,
                        "overage_units": billable_units,
                        "flag_payload": {"metric_config": metric_conf, "billing_period_start": billing_period_start},
                    }
                )
            )

        ledger = self.repository.save_usage_ledger(
            {
                "usage_ledger_id": ledger_id,
                "account_id": account_id,
                "customer_account_id": customer_account_id,
                "plan_id": plan_id,
                "status": "open",
                "billing_period_start": billing_period_start,
                "billing_period_end": billing_period_end,
                "presented_count": metric_counts["validated_presented"],
                "handoff_count": metric_counts["validated_handoff"],
                "conversion_count": metric_counts["validated_conversion"],
                "subtotal_amount_usd": subtotal,
                "disputed_amount_usd": disputed,
                "credited_amount_usd": credited,
                "reversed_amount_usd": reversed_amount,
                "ledger_payload": {
                    "line_items": line_items,
                    "metric_counts": metric_counts,
                },
            }
        )
        credit_balance = self._credit_balance(account_id=account_id, customer_account_id=customer_account_id)
        credits_applied = min(float(credit_balance.get("amount_usd") or 0.0), max(0.0, subtotal - disputed - credited - reversed_amount))
        invoice_preview = self.repository.save_invoice_preview(
            {
                "invoice_preview_id": f"invoice_preview_{account_id}_{period_key}",
                "usage_ledger_id": ledger["usage_ledger_id"],
                "account_id": account_id,
                "customer_account_id": customer_account_id,
                "plan_id": plan_id,
                "status": "draft",
                "billing_period_start": billing_period_start,
                "billing_period_end": billing_period_end,
                "subtotal_amount_usd": subtotal,
                "credits_applied_usd": credits_applied,
                "disputed_amount_usd": disputed,
                "credited_amount_usd": credited,
                "reversed_amount_usd": reversed_amount,
                "total_due_usd": round(max(0.0, subtotal - disputed - credited - reversed_amount - credits_applied), 6),
                "line_items": line_items,
                "summary": {
                    "metric_counts": metric_counts,
                    "billable_event_count": len(saved_billable_events),
                    "credit_balance_usd": float(credit_balance.get("amount_usd") or 0.0),
                    "config_version": self._config().get("config_version"),
                },
            }
        )
        return {
            "customer_account": customer,
            "plan": plan,
            "usage_ledger": ledger,
            "billable_events": saved_billable_events,
            "invoice_preview": invoice_preview,
            "credit_balance": credit_balance,
            "overage_flags": overage_flags,
        }

    def invoice_preview(self, *, account_id: str, period_start: Optional[str] = None) -> Dict[str, Any]:
        synced = self.sync_account_billing(account_id=account_id, period_start=period_start)
        invoice_preview = dict(synced.get("invoice_preview") or {})
        billable_events = list(synced.get("billable_events") or [])
        status_counts = Counter(str(item.get("status") or "unknown") for item in billable_events)
        line_items = list(invoice_preview.get("line_items_json") or [])
        csv_lines = [
            "metric_type,display_name,observed_units,included_units,billable_units,unit_price_usd,line_amount_usd"
        ]
        for item in line_items:
            csv_lines.append(
                ",".join(
                    [
                        str(item.get("metric_type") or ""),
                        str(item.get("display_name") or ""),
                        str(item.get("observed_units") or 0),
                        str(item.get("included_units") or 0),
                        str(item.get("billable_units") or 0),
                        str(item.get("unit_price_usd") or 0),
                        str(item.get("line_amount_usd") or 0),
                    ]
                )
            )
        result = {
            "generated_at": self._utcnow().isoformat(),
            "account_id": account_id,
            "customer_account": synced.get("customer_account"),
            "plan": synced.get("plan"),
            "usage_ledger": synced.get("usage_ledger"),
            "billable_events": billable_events,
            "invoice_preview": invoice_preview,
            "credit_balance": synced.get("credit_balance"),
            "overage_flags": synced.get("overage_flags"),
            "export_artifacts": {
                "json_filename": f"invoice_preview_{account_id}.json",
                "csv_filename": f"invoice_preview_{account_id}.csv",
                "csv_preview": "\n".join(csv_lines),
            },
            "summary": {
                "billable_event_count": len(billable_events),
                "status_counts": dict(status_counts),
                "metrics": dict((invoice_preview.get("summary_json") or {}).get("metric_counts") or {}),
            },
        }
        self.audit.record_audit_log(
            actor_id=account_id,
            actor_role="customer",
            account_id=account_id,
            object_type="invoice_preview",
            object_id=str((invoice_preview or {}).get("invoice_preview_id") or f"invoice_preview::{account_id}"),
            action_type="invoice_preview_generated",
            source_surface="customer",
            customer_visible_payload={"invoice_preview": invoice_preview, "summary": result.get("summary")},
            internal_payload=result,
        )
        return result

    def list_usage_ledgers(self, *, account_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        ledgers = self.repository.list_usage_ledgers(account_id=account_id, limit=limit)
        return {
            "usage_ledgers": ledgers,
            "summary": {
                "ledger_count": len(ledgers),
                "subtotal_amount_usd": round(sum(float(item.get("subtotal_amount_usd") or 0.0) for item in ledgers), 6),
            },
        }

    def list_invoice_previews(self, *, account_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        previews = self.repository.list_invoice_previews(account_id=account_id, limit=limit)
        return {
            "invoice_previews": previews,
            "summary": {
                "preview_count": len(previews),
                "total_due_usd": round(sum(float(item.get("total_due_usd") or 0.0) for item in previews), 6),
            },
        }

    def update_billable_event_status(self, *, billable_event_id: str, status: str) -> Dict[str, Any]:
        normalized = str(status or "").strip()
        if normalized not in COMMERCIAL_BILLABLE_STATUSES:
            raise ValueError("billable_event_status_invalid:%s" % normalized)
        updated = self.repository.update_billable_event_status(billable_event_id, status=normalized)
        self.audit.record_audit_log(
            actor_id="ops_billing",
            actor_role="reviewer",
            account_id=updated.get("account_id"),
            object_type="billable_event",
            object_id=billable_event_id,
            action_type="billable_event_status_changed",
            source_surface="ops",
            customer_visible_payload={"billable_event": updated},
            internal_payload={"status": normalized},
        )
        return updated

    def trace_billing_projection(self, *, trace_id: str) -> Dict[str, Any]:
        events = self.repository.list_billable_events(trace_id=trace_id, limit=20)
        related_invoice_ids = {str(item.get("usage_ledger_id") or "") for item in events if str(item.get("usage_ledger_id") or "").strip()}
        previews = []
        for invoice in self.repository.list_invoice_previews(limit=100):
            if str(invoice.get("usage_ledger_id") or "") in related_invoice_ids:
                previews.append(invoice)
        return {
            "billable_events": events,
            "invoice_previews": previews[:5],
            "summary": {
                "billable_event_count": len(events),
                "total_amount_usd": round(sum(float(item.get("amount_usd") or 0.0) for item in events), 6),
                "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in events)),
            },
        }
