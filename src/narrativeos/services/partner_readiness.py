from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .commercial_audit import CommercialAuditService


PARTNER_LIFECYCLE_STATUSES = {
    "discovered",
    "parsed",
    "verified",
    "commercial_qualified",
    "active",
    "paused",
    "blocked",
}


class PartnerReadinessService:
    def __init__(self, repository: SQLAlchemyPlatformRepository, *, audit_service: CommercialAuditService) -> None:
        self.repository = repository
        self.audit = audit_service

    def _validate_lifecycle(self, status: str) -> str:
        normalized = str(status or "").strip()
        if normalized not in PARTNER_LIFECYCLE_STATUSES:
            raise ValueError("partner_lifecycle_invalid:%s" % normalized)
        return normalized

    def upsert_partner(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        partner = self.repository.save_partner(
            {
                "partner_id": payload.get("partner_id"),
                "name": payload["name"],
                "lifecycle_status": self._validate_lifecycle(payload.get("lifecycle_status", "discovered")),
                "sla_status": payload.get("sla_status", "unknown"),
                "receipt_capability": payload.get("receipt_capability", "unknown"),
                "disclosure_readiness": payload.get("disclosure_readiness", "unknown"),
                "billing_readiness": payload.get("billing_readiness", "unknown"),
                "allowlisted_channels": list(payload.get("allowlisted_channels") or []),
                "primary_endpoint_url": payload.get("primary_endpoint_url"),
                "endpoint_health_status": payload.get("endpoint_health_status", "unknown"),
                "partner_payload": dict(payload.get("partner_payload") or {}),
            }
        )
        capabilities = self.repository.replace_partner_capabilities(
            partner_id=partner["partner_id"],
            capabilities=list(payload.get("capabilities") or []),
        )
        if payload.get("health_check"):
            self.repository.save_partner_health_check(
                {
                    "partner_id": partner["partner_id"],
                    **dict(payload.get("health_check") or {}),
                }
            )
        detail = self.partner_detail(partner["partner_id"])
        self.audit.record_audit_log(
            actor_id="ops_seed",
            actor_role="ops",
            account_id=None,
            object_type="partner",
            object_id=partner["partner_id"],
            action_type="partner_upserted",
            source_surface="ops",
            customer_visible_payload={"partner": detail.get("partner")},
            internal_payload=detail,
        )
        return detail

    def change_status(self, *, partner_id: str, status: str, note: Optional[str] = None) -> Dict[str, Any]:
        existing = self.repository.get_partner(partner_id)
        updated = self.repository.save_partner(
            {
                **existing,
                "lifecycle_status": self._validate_lifecycle(status),
                "allowlisted_channels_json": existing.get("allowlisted_channels_json", []),
                "partner_payload_json": {
                    **dict(existing.get("partner_payload_json") or {}),
                    "status_note": note,
                },
            }
        )
        detail = self.partner_detail(updated["partner_id"])
        self.audit.record_audit_log(
            actor_id="ops_status",
            actor_role="ops",
            account_id=None,
            object_type="partner",
            object_id=updated["partner_id"],
            action_type="partner_status_changed",
            source_surface="ops",
            customer_visible_payload={"partner": detail.get("partner")},
            internal_payload={**detail, "note": note},
        )
        return detail

    def record_health_check(
        self,
        *,
        partner_id: str,
        endpoint_url: Optional[str],
        status: str,
        status_code: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        health_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        check = self.repository.save_partner_health_check(
            {
                "partner_id": partner_id,
                "endpoint_url": endpoint_url,
                "status": status,
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "health_payload": dict(health_payload or {}),
            }
        )
        partner = self.repository.get_partner(partner_id)
        self.repository.save_partner(
            {
                **partner,
                "allowlisted_channels_json": partner.get("allowlisted_channels_json", []),
                "endpoint_health_status": status,
                "partner_payload_json": dict(partner.get("partner_payload_json") or {}),
            }
        )
        return check

    def _readiness_summary(self, *, partner: Dict[str, Any], capabilities: List[Dict[str, Any]], health_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        capability_counts = Counter(str(item.get("status") or "unknown") for item in capabilities)
        latest_health = health_checks[0] if health_checks else None
        return {
            "lifecycle_status": partner.get("lifecycle_status"),
            "allowlisted_channel_count": len(partner.get("allowlisted_channels_json") or []),
            "capability_status_counts": dict(capability_counts),
            "latest_health_status": (latest_health or {}).get("status") or partner.get("endpoint_health_status"),
            "receipt_capability": partner.get("receipt_capability"),
            "disclosure_readiness": partner.get("disclosure_readiness"),
            "billing_readiness": partner.get("billing_readiness"),
            "commercial_ready": (
                str(partner.get("lifecycle_status") or "") in {"commercial_qualified", "active"}
                and str(partner.get("disclosure_readiness") or "") in {"ready", "verified"}
                and str(partner.get("billing_readiness") or "") in {"ready", "verified"}
                and str((latest_health or {}).get("status") or partner.get("endpoint_health_status") or "") in {"healthy", "pass"}
            ),
        }

    def partner_detail(self, partner_id: str) -> Dict[str, Any]:
        partner = self.repository.get_partner(partner_id)
        capabilities = self.repository.list_partner_capabilities(partner_id=partner_id)
        health_checks = self.repository.list_partner_health_checks(partner_id=partner_id, limit=10)
        return {
            "partner": partner,
            "capabilities": capabilities,
            "health_checks": health_checks,
            "readiness_summary": self._readiness_summary(partner=partner, capabilities=capabilities, health_checks=health_checks),
        }

    def list_partners(self, *, lifecycle_status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        partners = self.repository.list_partners(lifecycle_status=lifecycle_status, limit=limit)
        details = [self.partner_detail(item["partner_id"]) for item in partners]
        return {
            "partners": details,
            "summary": {
                "partner_count": len(details),
                "lifecycle_counts": dict(Counter(str(item["partner"].get("lifecycle_status") or "unknown") for item in details)),
                "health_counts": dict(Counter(str(item["readiness_summary"].get("latest_health_status") or "unknown") for item in details)),
            },
        }
