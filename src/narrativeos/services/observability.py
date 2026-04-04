from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from ..persistence.migrations import inspect_schema_lifecycle
from ..persistence.repositories import SQLAlchemyPlatformRepository


RUNTIME_RECEIPT_EVENT = "runtime_observability_receipt"


class ObservabilityService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _deep_find(self, payload: Any, key: str) -> Any:
        if isinstance(payload, dict):
            if key in payload:
                return payload.get(key)
            for value in payload.values():
                found = self._deep_find(value, key)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = self._deep_find(value, key)
                if found is not None:
                    return found
        return None

    def build_runtime_receipt(
        self,
        *,
        surface: str,
        action: str,
        response_status: str,
        world_id: str,
        world_version_id: str,
        session_id: Optional[str] = None,
        account_id: Optional[str] = None,
        reader_id: Optional[str] = None,
        candidate_batch: Optional[Dict[str, Any]] = None,
        rendered_scene: Optional[Dict[str, Any]] = None,
        reader_view: Optional[Dict[str, Any]] = None,
        estimated_cost: float = 0.0,
    ) -> Dict[str, Any]:
        candidate_debug = dict((candidate_batch or {}).get("debug") or {})
        candidate_routing = dict(candidate_debug.get("backend_routing") or {})
        render_debug = dict((rendered_scene or {}).get("debug") or {})
        render_routing = dict(render_debug.get("backend_routing") or {})
        selected_provider = (
            self._deep_find(candidate_routing, "selected_provider")
            or self._deep_find(render_routing, "selected_provider")
            or self._deep_find(candidate_routing, "provider")
            or self._deep_find(render_routing, "provider")
            or candidate_debug.get("provider")
            or render_debug.get("renderer")
        )
        cache_hit = self._deep_find(candidate_routing, "cache_hit")
        if cache_hit is None:
            cache_hit = self._deep_find(render_routing, "cache_hit")
        budget_blocked = bool(self._deep_find(candidate_routing, "budget_blocked") or self._deep_find(render_routing, "budget_blocked"))
        fallback_used = bool(
            self._deep_find(candidate_routing, "fallback_used")
            or self._deep_find(render_routing, "fallback_used")
            or candidate_debug.get("backend_error")
            or render_debug.get("renderer_fallback_reason")
        )
        backend_error = candidate_debug.get("backend_error")
        if not backend_error and render_debug.get("renderer_fallback_reason") == "llm_backend_error":
            raw_payload = dict(render_debug.get("raw_payload") or {})
            backend_error = raw_payload.get("error") or "llm_backend_error"
        output_chars = len(str((reader_view or {}).get("body") or ""))
        incident_flags: List[str] = []
        if backend_error:
            incident_flags.append("provider_error")
        if budget_blocked:
            incident_flags.append("budget_blocked")
        if fallback_used:
            incident_flags.append("fallback_used")
        if response_status == "no_legal_routes":
            incident_flags.append("no_legal_routes")
        severity = "high" if {"provider_error", "budget_blocked"} & set(incident_flags) else ("medium" if incident_flags else "info")
        return {
            "receipt_type": "runtime_receipt",
            "generated_at": self._utcnow(),
            "surface": surface,
            "action": action,
            "response_status": response_status,
            "severity": severity,
            "incident_flags": incident_flags,
            "world_id": world_id,
            "world_version_id": world_version_id,
            "session_id": session_id,
            "account_id": account_id,
            "reader_id": reader_id,
            "provider": candidate_debug.get("provider") or render_debug.get("renderer"),
            "selected_provider": selected_provider,
            "candidate_counts": {
                "raw": int(candidate_debug.get("raw_count") or candidate_debug.get("llm_raw_count") or 0),
                "legal": int(candidate_debug.get("legal_count") or candidate_debug.get("llm_valid_count") or 0),
            },
            "fallback_used": fallback_used,
            "cache_hit": bool(cache_hit) if cache_hit is not None else None,
            "budget_blocked": budget_blocked,
            "backend_error": backend_error,
            "renderer_fallback_reason": render_debug.get("renderer_fallback_reason"),
            "estimated_cost": float(estimated_cost or 0.0),
            "output_chars": output_chars,
            "backend_routing": candidate_routing or render_routing,
        }

    def record_runtime_receipt(self, **payload: Any) -> Dict[str, Any]:
        receipt = self.build_runtime_receipt(**payload)
        event = self.repository.record_analytics_event(
            {
                "event_name": RUNTIME_RECEIPT_EVENT,
                "reader_id": payload.get("account_id") or payload.get("reader_id"),
                "session_id": payload.get("session_id"),
                "world_version_id": payload.get("world_version_id"),
                "payload_json": receipt,
            }
        )
        return {
            **receipt,
            "event_id": event.get("event_id"),
        }

    def list_runtime_receipts(
        self,
        *,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        incident_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        events = self.repository.list_analytics_events(
            event_names=[RUNTIME_RECEIPT_EVENT],
            session_id=session_id,
            limit=max(limit * 4, 50),
        )
        receipts: List[Dict[str, Any]] = []
        for event in events:
            receipt = dict(event.get("payload_json") or {})
            if not receipt:
                continue
            if account_id and receipt.get("account_id") != account_id and event.get("reader_id") != account_id:
                continue
            if incident_only and not receipt.get("incident_flags"):
                continue
            receipts.append(
                {
                    "event_id": event.get("event_id"),
                    "occurred_at": event.get("occurred_at"),
                    **receipt,
                }
            )
        return receipts[:limit]

    def runtime_incident_snapshot(
        self,
        *,
        account_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        receipts = self.list_runtime_receipts(account_id=account_id, limit=max(limit * 4, 50))
        incidents = [item for item in receipts if item.get("incident_flags")]
        by_incident_type: Dict[str, int] = {}
        by_provider: Dict[str, int] = {}
        by_surface: Dict[str, int] = {}
        cache_hits = 0
        cache_total = 0
        total_estimated_cost = 0.0
        for item in receipts:
            total_estimated_cost += float(item.get("estimated_cost") or 0.0)
            if item.get("cache_hit") is not None:
                cache_total += 1
                cache_hits += 1 if item.get("cache_hit") else 0
            provider = str(item.get("selected_provider") or item.get("provider") or "unknown")
            by_provider[provider] = by_provider.get(provider, 0) + 1
            surface = str(item.get("surface") or "unknown")
            by_surface[surface] = by_surface.get(surface, 0) + 1
            for flag in item.get("incident_flags", []):
                by_incident_type[str(flag)] = by_incident_type.get(str(flag), 0) + 1
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        return {
            "generated_at": self._utcnow(),
            "health_status": "ok",
            "schema_lifecycle_status": schema_lifecycle.get("status"),
            "receipt_count": len(receipts),
            "incident_count": len(incidents),
            "cache_hit_rate": round(cache_hits / float(cache_total), 3) if cache_total else None,
            "total_estimated_cost": round(total_estimated_cost, 6),
            "by_incident_type": by_incident_type,
            "by_provider": by_provider,
            "by_surface": by_surface,
            "latest_incidents": incidents[:limit],
            "latest_budget_blocks": [item for item in incidents if "budget_blocked" in item.get("incident_flags", [])][:limit],
            "latest_backend_errors": [item for item in incidents if "provider_error" in item.get("incident_flags", [])][:limit],
            "latest_fallbacks": [item for item in incidents if "fallback_used" in item.get("incident_flags", [])][:limit],
        }

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def provider_runtime_metrics(
        self,
        *,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        receipts = self.list_runtime_receipts(
            account_id=account_id,
            session_id=session_id,
            limit=max(limit * 4, 100),
        )
        provider_buckets: Dict[str, Dict[str, Any]] = {}
        surface_summary: Dict[str, int] = {}
        action_summary: Dict[str, int] = {}
        trend_buckets: Dict[str, Dict[str, Any]] = {}

        for item in receipts:
            provider = str(item.get("selected_provider") or item.get("provider") or "unknown")
            surface = str(item.get("surface") or "unknown")
            action = str(item.get("action") or "unknown")
            cost = float(item.get("estimated_cost") or 0.0)
            output_chars = int(item.get("output_chars") or 0)
            bucket = provider_buckets.setdefault(
                provider,
                {
                    "provider": provider,
                    "receipt_count": 0,
                    "incident_count": 0,
                    "fallback_count": 0,
                    "budget_block_count": 0,
                    "cache_hit_count": 0,
                    "cache_observed_count": 0,
                    "total_estimated_cost": 0.0,
                    "total_output_chars": 0,
                },
            )
            bucket["receipt_count"] += 1
            bucket["incident_count"] += 1 if item.get("incident_flags") else 0
            bucket["fallback_count"] += 1 if item.get("fallback_used") else 0
            bucket["budget_block_count"] += 1 if item.get("budget_blocked") else 0
            if item.get("cache_hit") is not None:
                bucket["cache_observed_count"] += 1
                bucket["cache_hit_count"] += 1 if item.get("cache_hit") else 0
            bucket["total_estimated_cost"] += cost
            bucket["total_output_chars"] += output_chars

            surface_summary[surface] = surface_summary.get(surface, 0) + 1
            action_summary[action] = action_summary.get(action, 0) + 1

            trend_key = self._parse_timestamp(item.get("occurred_at")).strftime("%Y-%m-%dT%H:00:00+00:00")
            trend = trend_buckets.setdefault(
                trend_key,
                {
                    "bucket": trend_key,
                    "receipt_count": 0,
                    "incident_count": 0,
                    "total_estimated_cost": 0.0,
                },
            )
            trend["receipt_count"] += 1
            trend["incident_count"] += 1 if item.get("incident_flags") else 0
            trend["total_estimated_cost"] += cost

        provider_summary = []
        for payload in provider_buckets.values():
            count = int(payload["receipt_count"])
            provider_summary.append(
                {
                    "provider": payload["provider"],
                    "receipt_count": count,
                    "incident_count": int(payload["incident_count"]),
                    "fallback_rate": round(payload["fallback_count"] / float(count), 3) if count else 0.0,
                    "budget_block_rate": round(payload["budget_block_count"] / float(count), 3) if count else 0.0,
                    "cache_hit_rate": (
                        round(payload["cache_hit_count"] / float(payload["cache_observed_count"]), 3)
                        if payload["cache_observed_count"]
                        else None
                    ),
                    "total_estimated_cost": round(payload["total_estimated_cost"], 6),
                    "avg_estimated_cost": round(payload["total_estimated_cost"] / float(count), 6) if count else 0.0,
                    "avg_output_chars": round(payload["total_output_chars"] / float(count), 2) if count else 0.0,
                }
            )
        provider_summary.sort(key=lambda item: (-item["total_estimated_cost"], item["provider"]))

        cost_trend = [
            {
                **payload,
                "total_estimated_cost": round(payload["total_estimated_cost"], 6),
            }
            for payload in sorted(trend_buckets.values(), key=lambda item: item["bucket"], reverse=True)[:limit]
        ]

        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "receipt_count": len(receipts),
            "total_estimated_cost": round(sum(item["total_estimated_cost"] for item in provider_summary), 6),
            "provider_summary": provider_summary,
            "surface_summary": surface_summary,
            "action_summary": action_summary,
            "cost_trend": cost_trend,
        }

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def provider_runtime_metrics(
        self,
        *,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        receipts = self.list_runtime_receipts(
            account_id=account_id,
            session_id=session_id,
            limit=max(limit * 4, 100),
        )
        provider_summary_map: Dict[str, Dict[str, Any]] = {}
        surface_summary: Dict[str, int] = {}
        action_summary: Dict[str, int] = {}
        cost_buckets: Dict[str, Dict[str, Any]] = {}

        for item in receipts:
            provider = str(item.get("selected_provider") or item.get("provider") or "unknown")
            surface = str(item.get("surface") or "unknown")
            action = str(item.get("action") or "unknown")
            cost = float(item.get("estimated_cost") or 0.0)
            output_chars = int(item.get("output_chars") or 0)
            provider_bucket = provider_summary_map.setdefault(
                provider,
                {
                    "provider": provider,
                    "receipt_count": 0,
                    "incident_count": 0,
                    "fallback_count": 0,
                    "budget_block_count": 0,
                    "backend_error_count": 0,
                    "cache_hits": 0,
                    "cache_observed": 0,
                    "total_estimated_cost": 0.0,
                    "total_output_chars": 0,
                    "surface_counts": {},
                    "action_counts": {},
                },
            )
            provider_bucket["receipt_count"] += 1
            provider_bucket["incident_count"] += 1 if item.get("incident_flags") else 0
            provider_bucket["fallback_count"] += 1 if item.get("fallback_used") else 0
            provider_bucket["budget_block_count"] += 1 if item.get("budget_blocked") else 0
            provider_bucket["backend_error_count"] += 1 if item.get("backend_error") else 0
            if item.get("cache_hit") is not None:
                provider_bucket["cache_observed"] += 1
                provider_bucket["cache_hits"] += 1 if item.get("cache_hit") else 0
            provider_bucket["total_estimated_cost"] += cost
            provider_bucket["total_output_chars"] += output_chars
            provider_bucket["surface_counts"][surface] = provider_bucket["surface_counts"].get(surface, 0) + 1
            provider_bucket["action_counts"][action] = provider_bucket["action_counts"].get(action, 0) + 1

            surface_summary[surface] = surface_summary.get(surface, 0) + 1
            action_summary[action] = action_summary.get(action, 0) + 1

            bucket_key = self._parse_timestamp(item.get("occurred_at")).strftime("%Y-%m-%dT%H:00:00+00:00")
            bucket = cost_buckets.setdefault(
                bucket_key,
                {
                    "bucket": bucket_key,
                    "receipt_count": 0,
                    "incident_count": 0,
                    "total_estimated_cost": 0.0,
                    "by_provider": {},
                },
            )
            bucket["receipt_count"] += 1
            bucket["incident_count"] += 1 if item.get("incident_flags") else 0
            bucket["total_estimated_cost"] += cost
            bucket["by_provider"][provider] = round(bucket["by_provider"].get(provider, 0.0) + cost, 6)

        provider_summary = []
        for payload in provider_summary_map.values():
            receipt_count = int(payload["receipt_count"])
            provider_summary.append(
                {
                    "provider": payload["provider"],
                    "receipt_count": receipt_count,
                    "incident_count": int(payload["incident_count"]),
                    "fallback_rate": round(payload["fallback_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "budget_block_rate": round(payload["budget_block_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "backend_error_rate": round(payload["backend_error_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "cache_hit_rate": (
                        round(payload["cache_hits"] / float(payload["cache_observed"]), 3)
                        if payload["cache_observed"]
                        else None
                    ),
                    "total_estimated_cost": round(payload["total_estimated_cost"], 6),
                    "avg_estimated_cost": round(payload["total_estimated_cost"] / float(receipt_count), 6) if receipt_count else 0.0,
                    "avg_output_chars": round(payload["total_output_chars"] / float(receipt_count), 2) if receipt_count else 0.0,
                    "surface_counts": payload["surface_counts"],
                    "action_counts": payload["action_counts"],
                }
            )
        provider_summary.sort(key=lambda item: (-item["total_estimated_cost"], item["provider"]))

        cost_trend = sorted(cost_buckets.values(), key=lambda item: item["bucket"], reverse=True)[:limit]
        cost_trend = [
            {
                **item,
                "total_estimated_cost": round(item["total_estimated_cost"], 6),
            }
            for item in cost_trend
        ]

        total_cost = round(sum(item["total_estimated_cost"] for item in provider_summary), 6)
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "provider_summary": provider_summary,
            "cost_trend": cost_trend,
            "surface_summary": surface_summary,
            "action_summary": action_summary,
            "receipt_count": len(receipts),
            "total_estimated_cost": total_cost,
        }
