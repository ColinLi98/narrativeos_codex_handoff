from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .commercial_audit import CommercialAuditService
from .customer_accounts import CustomerAccountService
from .customer_workspace import CustomerWorkspaceService
from .production_acceptance import ProductionAcceptanceService
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


READINESS_WEIGHTS = {
    "value_delivery": 30,
    "billing_health": 25,
    "operational_stability": 20,
    "product_continuity": 15,
    "expansion_renewal": 10,
}


class CustomerSuccessReportingService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_workspace_service: CustomerWorkspaceService,
        customer_account_service: CustomerAccountService,
        production_acceptance_service: ProductionAcceptanceService,
        production_signoff_service: ProductionSignoffService,
        commercial_audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.customer_workspace = customer_workspace_service
        self.customer_accounts = customer_account_service
        self.production_acceptance = production_acceptance_service
        self.production_signoff = production_signoff_service
        self.commercial_audit = commercial_audit_service

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _utcnow_iso(self) -> str:
        return self._utcnow().isoformat()

    def _active_launch_anchor(self, *, launch_wave: str, fallback: Optional[str]) -> Optional[str]:
        audits = self.repository.list_audit_logs(action_type="launch_wave_status_updated", limit=500)
        active_candidates: List[datetime] = []
        for row in audits:
            internal = dict(row.get("internal_payload_json") or {})
            if str(internal.get("launch_wave") or "") != launch_wave:
                continue
            if str(internal.get("status") or "") != "active":
                continue
            parsed = self._parse_dt(row.get("created_at"))
            if parsed:
                active_candidates.append(parsed)
        if active_candidates:
            return min(active_candidates).isoformat()
        return fallback

    def _latest_by_account(self, rows: List[Dict[str, Any]], *, account_key: str = "account_id", generated_key: str = "generated_at") -> Dict[str, Dict[str, Any]]:
        latest: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            account_id = str(row.get(account_key) or "")
            if not account_id:
                continue
            if account_id not in latest or str(row.get(generated_key) or "") > str(latest[account_id].get(generated_key) or ""):
                latest[account_id] = row
        return latest

    def _readiness_components(self, *, workspace: Dict[str, Any], account_detail: Dict[str, Any], acceptance_record: Dict[str, Any], signoff: Optional[Dict[str, Any]]) -> Dict[str, float]:
        handoff = dict(workspace.get("handoff_conversion_summary") or {})
        support = dict(workspace.get("support_summary") or {})
        disputes = dict(workspace.get("dispute_summary") or {})
        billing_profile = dict(workspace.get("billing_profile") or {})
        invoice_preview = dict(workspace.get("invoice_preview") or {})
        expansion = dict(workspace.get("expansion_summary") or {})
        renewal = dict(workspace.get("renewal_summary") or {})
        quality = dict(workspace.get("quality_summary") or {})
        launch_alert_count = 0
        value_delivery = 1.0 if (int(handoff.get("validated_conversion_count") or 0) > 0 or int(handoff.get("validated_handoff_count") or 0) > 0) else 0.4
        billing_health = 1.0 if billing_profile.get("billing_profile_id") and invoice_preview.get("invoice_preview_id") else 0.3
        operational_stability = 1.0 if int(support.get("case_count") or 0) == 0 and int(disputes.get("dispute_count") or 0) == 0 else 0.5
        product_continuity = 1.0 if int(quality.get("event_count") or 0) > 0 and acceptance_record.get("status") != "blocked" else 0.5
        expansion_renewal = 1.0 if expansion.get("recommended_plan_id") or renewal.get("status") in {"renewal_due", "active", "stable"} else 0.4
        if signoff and str((signoff.get("signoff") or {}).get("status") or "") != "fully_signed":
            operational_stability = min(operational_stability, 0.6)
        return {
            "value_delivery": value_delivery,
            "billing_health": billing_health,
            "operational_stability": operational_stability,
            "product_continuity": product_continuity,
            "expansion_renewal": expansion_renewal,
            "launch_alert_count": float(launch_alert_count),
        }

    def _score_band(self, score: float) -> str:
        if score >= 75.0:
            return "ready"
        if score >= 50.0:
            return "watch"
        return "at_risk"

    def _build_account_snapshots(self, *, account_id: str, launch_wave: str) -> Dict[str, Any]:
        workspace = self.customer_workspace.workspace(account_id=account_id)
        account_detail = self.customer_accounts.customer_account_detail(account_id=account_id)
        acceptance_record = next(iter(self.repository.list_production_customer_acceptance_records(account_id=account_id, launch_wave=launch_wave, limit=1)), None)
        if acceptance_record is None:
            raise KeyError(f"missing_production_acceptance_for_account:{account_id}")
        signoff = None
        if acceptance_record.get("signoff_id"):
            try:
                signoff = self.production_signoff.signoff_detail(signoff_id=acceptance_record["signoff_id"])
            except KeyError:
                signoff = None
        fallback_anchor = acceptance_record.get("created_at")
        launch_anchor_at = self._active_launch_anchor(launch_wave=launch_wave, fallback=fallback_anchor)
        payment_transactions = self.repository.list_payment_transactions(account_id=account_id, limit=500)
        invoice_issuances = self.repository.list_invoice_issuances(account_id=account_id, limit=500)
        dunning_runs = self.repository.list_dunning_runs(account_id=account_id, limit=500)
        support_cases = self.repository.list_support_cases(account_id=account_id, limit=500)
        disputes = self.repository.list_disputes(account_id=account_id, limit=500)
        partner_channels = dict((workspace.get("channel_partner_performance") or {})).get("allowlisted_channels") or []
        handoff = dict(workspace.get("handoff_conversion_summary") or {})
        receipt = dict(workspace.get("receipt_summary") or {})
        expansion = dict(workspace.get("expansion_summary") or {})
        renewal = dict(workspace.get("renewal_summary") or {})
        components = self._readiness_components(
            workspace=workspace,
            account_detail=account_detail,
            acceptance_record=acceptance_record,
            signoff=signoff,
        )
        score = sum(components[key] * READINESS_WEIGHTS[key] for key in READINESS_WEIGHTS)
        band = self._score_band(score)
        first_7_day_payload = {
            "billing_outcome": {
                "invoice_count": len(invoice_issuances),
                "payment_failure_count": len([item for item in payment_transactions if str(item.get("status") or "") == "failed"]),
                "payment_paid_count": len([item for item in payment_transactions if str(item.get("status") or "") == "paid"]),
            },
            "support_dispute": {
                "support_case_count": len(support_cases),
                "dispute_count": len(disputes),
            },
            "value_delivery": {
                "receipt_count": int(receipt.get("receipt_count") or 0),
                "validated_handoff_count": int(handoff.get("validated_handoff_count") or 0),
                "validated_conversion_count": int(handoff.get("validated_conversion_count") or 0),
            },
            "lifecycle": {
                "dunning_open_count": len([item for item in dunning_runs if str(item.get("status") or "") == "open"]),
                "renewal_status": renewal.get("status"),
                "upgrade_recommendation": expansion.get("recommended_plan_id"),
            },
            "launch_alert_count": 0,
        }
        first_30_payload = {
            "usage_billing_realized": {
                "invoice_count": len(invoice_issuances),
                "total_due_usd": float(sum(float(item.get("total_due_usd") or 0.0) for item in invoice_issuances)),
            },
            "partner_campaign_posture": {
                "campaign_count": int((workspace.get("campaign_summary") or {}).get("campaign_count") or 0),
                "allowlisted_channels": list(partner_channels),
            },
            "support_burden": {
                "support_case_count": len(support_cases),
                "dispute_count": len(disputes),
            },
            "renewal_expansion": {
                "renewal_status": renewal.get("status"),
                "expansion_status": expansion.get("status"),
                "recommended_plan_id": expansion.get("recommended_plan_id"),
            },
        }
        provisional = True
        if launch_anchor_at:
            anchor_dt = self._parse_dt(launch_anchor_at)
            provisional = not bool(anchor_dt and (self._utcnow() - anchor_dt).days >= 30)
        snapshot_payload = {
            "account_id": account_id,
            "launch_wave": launch_wave,
            "launch_anchor_at": launch_anchor_at,
            "customer_workspace": {
                "quality_summary": workspace.get("quality_summary"),
                "receipt_summary": workspace.get("receipt_summary"),
                "handoff_conversion_summary": workspace.get("handoff_conversion_summary"),
                "renewal_summary": workspace.get("renewal_summary"),
                "dunning_summary": workspace.get("dunning_summary"),
                "expansion_summary": workspace.get("expansion_summary"),
                "support_summary": workspace.get("support_summary"),
                "dispute_summary": workspace.get("dispute_summary"),
            },
            "production_acceptance": acceptance_record,
            "production_signoff": {
                "signoff_id": (signoff or {}).get("signoff", {}).get("signoff_id"),
                "status": (signoff or {}).get("signoff", {}).get("status"),
            },
            "pilot_to_paid_readiness": {
                "score": score,
                "band": band,
                "components": {key: {"normalized": components[key], "weight": READINESS_WEIGHTS[key], "weighted_score": components[key] * READINESS_WEIGHTS[key]} for key in READINESS_WEIGHTS},
            },
        }
        return {
            "launch_anchor_at": launch_anchor_at,
            "first_7_day_payload": first_7_day_payload,
            "first_30_day_payload": first_30_payload,
            "provisional": provisional,
            "score": score,
            "band": band,
            "score_payload": snapshot_payload["pilot_to_paid_readiness"],
            "snapshot_payload": snapshot_payload,
            "customer_account_id": (account_detail.get("customer_account") or {}).get("customer_account_id"),
        }

    def sync_snapshots(
        self,
        *,
        actor_id: str,
        actor_role: str,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
    ) -> Dict[str, Any]:
        candidates = self.repository.list_go_live_ready_accounts(account_id=account_id, launch_wave=launch_wave, limit=100)
        saved: List[Dict[str, Any]] = []
        for item in candidates:
            account = str(item.get("account_id") or "")
            wave = str(item.get("launch_wave") or "")
            if not account or not wave:
                continue
            built = self._build_account_snapshots(account_id=account, launch_wave=wave)
            first7 = self.repository.save_first_7_day_outcome(
                {
                    "account_id": account,
                    "customer_account_id": built["customer_account_id"],
                    "launch_wave": wave,
                    "launch_anchor_at": built["launch_anchor_at"],
                    "outcome_payload": built["first_7_day_payload"],
                }
            )
            first30 = self.repository.save_first_30_day_value_summary(
                {
                    "account_id": account,
                    "customer_account_id": built["customer_account_id"],
                    "launch_wave": wave,
                    "launch_anchor_at": built["launch_anchor_at"],
                    "provisional": built["provisional"],
                    "summary_payload": built["first_30_day_payload"],
                }
            )
            score = self.repository.save_pilot_to_paid_readiness_score(
                {
                    "account_id": account,
                    "customer_account_id": built["customer_account_id"],
                    "launch_wave": wave,
                    "launch_anchor_at": built["launch_anchor_at"],
                    "score": built["score"],
                    "band": built["band"],
                    "score_payload": built["score_payload"],
                }
            )
            snapshot = self.repository.save_customer_success_snapshot(
                {
                    "account_id": account,
                    "customer_account_id": built["customer_account_id"],
                    "launch_wave": wave,
                    "launch_anchor_at": built["launch_anchor_at"],
                    "snapshot_payload": built["snapshot_payload"],
                }
            )
            saved.append({"first_7_day_outcome": first7, "first_30_day_value_summary": first30, "pilot_to_paid_readiness_score": score, "customer_success_snapshot": snapshot})
            self.commercial_audit.record_audit_log(
                actor_id=actor_id,
                actor_role=actor_role,
                account_id=account,
                object_type="customer_success_snapshot",
                object_id=snapshot["customer_success_snapshot_id"],
                action_type="customer_success_snapshot_synced",
                source_surface="ops",
                customer_visible_payload={},
                internal_payload=saved[-1],
            )
        return {
            "synced": saved,
            "summary": {
                "snapshot_count": len(saved),
                "account_ids": [item["customer_success_snapshot"]["account_id"] for item in saved],
                "band_counts": dict(Counter(str(item["pilot_to_paid_readiness_score"]["band"] or "unknown") for item in saved)),
            },
        }

    def _latest_snapshot_bundle(self, *, account_id: Optional[str] = None, launch_wave: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        return {
            "first_7_day": self._latest_by_account(self.repository.list_first_7_day_outcomes(account_id=account_id, launch_wave=launch_wave, limit=200)),
            "first_30_day": self._latest_by_account(self.repository.list_first_30_day_value_summaries(account_id=account_id, launch_wave=launch_wave, limit=200)),
            "scores": self._latest_by_account(self.repository.list_pilot_to_paid_readiness_scores(account_id=account_id, launch_wave=launch_wave, limit=200)),
            "snapshots": self._latest_by_account(self.repository.list_customer_success_snapshots(account_id=account_id, launch_wave=launch_wave, limit=200)),
        }

    def list_customer_success(self, *, account_id: Optional[str] = None, launch_wave: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        latest = self._latest_snapshot_bundle(account_id=account_id, launch_wave=launch_wave)
        account_ids = list(latest["snapshots"].keys())[:limit]
        records = []
        for account in account_ids:
            records.append(
                {
                    "account_id": account,
                    "snapshot": latest["snapshots"].get(account),
                    "first_7_day_outcome": latest["first_7_day"].get(account),
                    "first_30_day_value_summary": latest["first_30_day"].get(account),
                    "pilot_to_paid_readiness_score": latest["scores"].get(account),
                }
            )
        bands = Counter(str((item.get("pilot_to_paid_readiness_score") or {}).get("band") or "unknown") for item in records)
        provisional_count = sum(1 for item in records if bool((item.get("first_30_day_value_summary") or {}).get("provisional")))
        return {
            "accounts": records,
            "summary": {
                "account_count": len(records),
                "band_counts": dict(bands),
                "provisional_30_day_count": provisional_count,
                "launch_wave_count": len({str((item.get("snapshot") or {}).get("launch_wave") or "") for item in records if (item.get("snapshot") or {}).get("launch_wave")}),
            },
        }

    def _detail(self, *, account_id: str) -> Dict[str, Any]:
        latest = self._latest_snapshot_bundle(account_id=account_id)
        snapshot = next(iter(latest["snapshots"].values()), None)
        first7 = next(iter(latest["first_7_day"].values()), None)
        first30 = next(iter(latest["first_30_day"].values()), None)
        score = next(iter(latest["scores"].values()), None)
        return {
            "account_id": account_id,
            "customer_success_snapshot": snapshot,
            "first_7_day_outcome": first7,
            "first_30_day_value_summary": first30,
            "pilot_to_paid_readiness_score": score,
        }

    def detail(self, *, account_id: str) -> Dict[str, Any]:
        return self._detail(account_id=account_id)

    def report(self, *, account_id: Optional[str] = None, launch_wave: Optional[str] = None, view: str = "internal") -> Dict[str, Any]:
        normalized_view = str(view or "internal")
        if normalized_view == "investor_safe":
            listing = self.list_customer_success(launch_wave=launch_wave, limit=200)
            scores = [float((item.get("pilot_to_paid_readiness_score") or {}).get("score") or 0.0) for item in listing["accounts"]]
            return {
                "view": "investor_safe",
                "launch_wave": launch_wave,
                "summary": {
                    "account_count": listing["summary"]["account_count"],
                    "band_counts": listing["summary"]["band_counts"],
                    "provisional_30_day_count": listing["summary"]["provisional_30_day_count"],
                    "avg_readiness_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
                },
            }
        if not account_id:
            raise KeyError("customer_success_account_id_required")
        detail = self._detail(account_id=account_id)
        if normalized_view == "customer_safe":
            return {
                "view": "customer_safe",
                "account_id": account_id,
                "customer_success_snapshot": self.commercial_audit.customer_safe_payload(detail.get("customer_success_snapshot") or {}),
                "first_7_day_outcome": self.commercial_audit.customer_safe_payload(detail.get("first_7_day_outcome") or {}),
                "first_30_day_value_summary": self.commercial_audit.customer_safe_payload(detail.get("first_30_day_value_summary") or {}),
                "pilot_to_paid_readiness_score": self.commercial_audit.customer_safe_payload(detail.get("pilot_to_paid_readiness_score") or {}),
            }
        return {
            "view": "internal",
            **detail,
        }
