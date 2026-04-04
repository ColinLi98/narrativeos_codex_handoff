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

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _percentile(self, values: Sequence[float], percentile: float) -> Optional[float]:
        cleaned = sorted(float(value) for value in values)
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return round(cleaned[0], 3)
        rank = max(0.0, min(1.0, percentile)) * float(len(cleaned) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(cleaned) - 1)
        fraction = rank - lower
        value = cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction
        return round(value, 3)

    def _latency_summary(self, values: Sequence[Any]) -> Dict[str, Any]:
        cleaned = [float(value) for value in values if self._safe_float(value) is not None]
        if not cleaned:
            return {
                "count": 0,
                "avg_latency_ms": None,
                "p95_latency_ms": None,
                "max_latency_ms": None,
            }
        return {
            "count": len(cleaned),
            "avg_latency_ms": round(sum(cleaned) / float(len(cleaned)), 3),
            "p95_latency_ms": self._percentile(cleaned, 0.95),
            "max_latency_ms": round(max(cleaned), 3),
        }

    def _routing_payload(self, payload: Any) -> Dict[str, Any]:
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _budget_estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        estimate = dict(self._deep_find(payload, "budget_estimate") or {})
        return {
            "prompt_chars": estimate.get("prompt_chars"),
            "estimated_tokens": estimate.get("estimated_tokens"),
            "estimated_cost_usd": estimate.get("estimated_cost_usd"),
        }

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
        runtime_latency_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        candidate_debug = dict((candidate_batch or {}).get("debug") or {})
        candidate_routing = self._routing_payload(candidate_debug.get("backend_routing"))
        candidate_rollout = self._routing_payload(candidate_debug.get("provider_rollout"))
        render_debug = dict((rendered_scene or {}).get("debug") or {})
        render_routing = self._routing_payload(render_debug.get("backend_routing"))
        renderer_rollout = self._routing_payload(render_debug.get("provider_rollout"))

        candidate_selected_provider = (
            self._deep_find(candidate_routing, "selected_provider")
            or self._deep_find(candidate_routing, "provider")
        )
        renderer_selected_provider = (
            self._deep_find(render_routing, "selected_provider")
            or self._deep_find(render_routing, "provider")
        )
        selected_provider = (
            candidate_selected_provider
            or renderer_selected_provider
            or candidate_debug.get("provider")
            or render_debug.get("renderer")
        )

        candidate_cache_hit = self._deep_find(candidate_routing, "cache_hit")
        renderer_cache_hit = self._deep_find(render_routing, "cache_hit")
        cache_hit = candidate_cache_hit if candidate_cache_hit is not None else renderer_cache_hit

        candidate_budget_blocked = bool(self._deep_find(candidate_routing, "budget_blocked")) if self._deep_find(candidate_routing, "budget_blocked") is not None else False
        renderer_budget_blocked = bool(self._deep_find(render_routing, "budget_blocked")) if self._deep_find(render_routing, "budget_blocked") is not None else False
        budget_blocked = bool(candidate_budget_blocked or renderer_budget_blocked)

        fallback_used = bool(
            self._deep_find(candidate_routing, "fallback_used")
            or self._deep_find(render_routing, "fallback_used")
            or candidate_debug.get("backend_error")
            or render_debug.get("renderer_fallback_reason")
        )

        candidate_backend_error = candidate_debug.get("backend_error") or self._deep_find(candidate_routing, "backend_error")
        renderer_backend_error = render_debug.get("backend_error") or self._deep_find(render_routing, "backend_error")
        if not renderer_backend_error and render_debug.get("renderer_fallback_reason") == "llm_backend_error":
            raw_payload = dict(render_debug.get("raw_payload") or {})
            renderer_backend_error = raw_payload.get("error") or "llm_backend_error"
        backend_error = candidate_backend_error or renderer_backend_error

        candidate_attempt_count = int(self._deep_find(candidate_routing, "attempt_count") or 0)
        renderer_attempt_count = int(self._deep_find(render_routing, "attempt_count") or 0)
        candidate_latency_ms = self._safe_float(self._deep_find(candidate_routing, "latency_ms"))
        renderer_latency_ms = self._safe_float(self._deep_find(render_routing, "latency_ms"))
        runtime_latency = self._safe_float(runtime_latency_ms)

        candidate_budget_estimate = self._budget_estimate(candidate_routing)
        renderer_budget_estimate = self._budget_estimate(render_routing)
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
            "candidate_selected_provider": candidate_selected_provider,
            "renderer_selected_provider": renderer_selected_provider,
            "candidate_counts": {
                "raw": int(candidate_debug.get("raw_count") or candidate_debug.get("llm_raw_count") or 0),
                "legal": int(candidate_debug.get("legal_count") or candidate_debug.get("llm_valid_count") or 0),
            },
            "candidate_rollout_status": candidate_rollout.get("rollout_status"),
            "renderer_rollout_status": renderer_rollout.get("rollout_status"),
            "candidate_canary_match": candidate_rollout.get("canary_match"),
            "renderer_canary_match": renderer_rollout.get("canary_match"),
            "fallback_used": fallback_used,
            "cache_hit": bool(cache_hit) if cache_hit is not None else None,
            "candidate_cache_hit": bool(candidate_cache_hit) if candidate_cache_hit is not None else None,
            "renderer_cache_hit": bool(renderer_cache_hit) if renderer_cache_hit is not None else None,
            "budget_blocked": budget_blocked,
            "candidate_budget_blocked": candidate_budget_blocked,
            "renderer_budget_blocked": renderer_budget_blocked,
            "backend_error": backend_error,
            "candidate_backend_error": candidate_backend_error,
            "renderer_backend_error": renderer_backend_error,
            "attempt_count": candidate_attempt_count or renderer_attempt_count or 0,
            "candidate_attempt_count": candidate_attempt_count,
            "renderer_attempt_count": renderer_attempt_count,
            "runtime_latency_ms": round(float(runtime_latency), 3) if runtime_latency is not None else None,
            "candidate_latency_ms": round(float(candidate_latency_ms), 3) if candidate_latency_ms is not None else None,
            "renderer_latency_ms": round(float(renderer_latency_ms), 3) if renderer_latency_ms is not None else None,
            "renderer_fallback_reason": render_debug.get("renderer_fallback_reason"),
            "estimated_cost": float(estimated_cost or 0.0),
            "candidate_estimated_request_cost_usd": candidate_budget_estimate.get("estimated_cost_usd"),
            "renderer_estimated_request_cost_usd": renderer_budget_estimate.get("estimated_cost_usd"),
            "candidate_prompt_chars": candidate_budget_estimate.get("prompt_chars"),
            "renderer_prompt_chars": renderer_budget_estimate.get("prompt_chars"),
            "candidate_estimated_tokens": candidate_budget_estimate.get("estimated_tokens"),
            "renderer_estimated_tokens": renderer_budget_estimate.get("estimated_tokens"),
            "output_chars": output_chars,
            "backend_routing": {
                "candidate": candidate_routing,
                "renderer": render_routing,
            },
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
        runtime_latencies: List[float] = []
        candidate_latencies: List[float] = []
        renderer_latencies: List[float] = []
        for item in receipts:
            total_estimated_cost += float(item.get("estimated_cost") or 0.0)
            if item.get("cache_hit") is not None:
                cache_total += 1
                cache_hits += 1 if item.get("cache_hit") else 0
            if item.get("runtime_latency_ms") is not None:
                runtime_latencies.append(float(item["runtime_latency_ms"]))
            if item.get("candidate_latency_ms") is not None:
                candidate_latencies.append(float(item["candidate_latency_ms"]))
            if item.get("renderer_latency_ms") is not None:
                renderer_latencies.append(float(item["renderer_latency_ms"]))
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
            "latency_summary": {
                "runtime": self._latency_summary(runtime_latencies),
                "candidate": self._latency_summary(candidate_latencies),
                "renderer": self._latency_summary(renderer_latencies),
            },
            "by_incident_type": by_incident_type,
            "by_provider": by_provider,
            "by_surface": by_surface,
            "latest_incidents": incidents[:limit],
            "latest_budget_blocks": [item for item in incidents if "budget_blocked" in item.get("incident_flags", [])][:limit],
            "latest_backend_errors": [item for item in incidents if "provider_error" in item.get("incident_flags", [])][:limit],
            "latest_fallbacks": [item for item in incidents if "fallback_used" in item.get("incident_flags", [])][:limit],
        }

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
        rollout_stage_maps: Dict[str, Dict[str, Dict[str, Any]]] = {
            "candidate": {},
            "renderer": {},
        }
        runtime_latencies: List[float] = []
        candidate_latencies: List[float] = []
        renderer_latencies: List[float] = []

        for item in receipts:
            provider = str(item.get("selected_provider") or item.get("provider") or "unknown")
            surface = str(item.get("surface") or "unknown")
            action = str(item.get("action") or "unknown")
            cost = float(item.get("estimated_cost") or 0.0)
            candidate_request_cost = float(item.get("candidate_estimated_request_cost_usd") or 0.0)
            renderer_request_cost = float(item.get("renderer_estimated_request_cost_usd") or 0.0)
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
                    "candidate_estimated_request_cost": 0.0,
                    "renderer_estimated_request_cost": 0.0,
                    "total_output_chars": 0,
                    "surface_counts": {},
                    "action_counts": {},
                    "selected_as_candidate_count": 0,
                    "selected_as_renderer_count": 0,
                    "runtime_latencies": [],
                    "candidate_latencies": [],
                    "renderer_latencies": [],
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
            provider_bucket["candidate_estimated_request_cost"] += candidate_request_cost
            provider_bucket["renderer_estimated_request_cost"] += renderer_request_cost
            provider_bucket["total_output_chars"] += output_chars
            provider_bucket["surface_counts"][surface] = provider_bucket["surface_counts"].get(surface, 0) + 1
            provider_bucket["action_counts"][action] = provider_bucket["action_counts"].get(action, 0) + 1

            if item.get("runtime_latency_ms") is not None:
                runtime_value = float(item["runtime_latency_ms"])
                provider_bucket["runtime_latencies"].append(runtime_value)
                runtime_latencies.append(runtime_value)
            if item.get("candidate_latency_ms") is not None:
                candidate_value = float(item["candidate_latency_ms"])
                candidate_latencies.append(candidate_value)
                if str(item.get("candidate_selected_provider") or "") == provider:
                    provider_bucket["selected_as_candidate_count"] += 1
                    provider_bucket["candidate_latencies"].append(candidate_value)
            if item.get("renderer_latency_ms") is not None:
                renderer_value = float(item["renderer_latency_ms"])
                renderer_latencies.append(renderer_value)
                if str(item.get("renderer_selected_provider") or "") == provider:
                    provider_bucket["selected_as_renderer_count"] += 1
                    provider_bucket["renderer_latencies"].append(renderer_value)

            for track in ("candidate", "renderer"):
                rollout_status = str(item.get(f"{track}_rollout_status") or "unknown")
                stage_bucket = rollout_stage_maps[track].setdefault(
                    rollout_status,
                    {
                        "rollout_status": rollout_status,
                        "receipt_count": 0,
                        "incident_count": 0,
                        "fallback_count": 0,
                        "budget_block_count": 0,
                        "backend_error_count": 0,
                        "canary_match_count": 0,
                        "total_estimated_cost": 0.0,
                        "runtime_latencies": [],
                        "track_latencies": [],
                    },
                )
                stage_bucket["receipt_count"] += 1
                stage_bucket["incident_count"] += 1 if item.get("incident_flags") else 0
                stage_bucket["fallback_count"] += 1 if item.get("fallback_used") else 0
                stage_bucket["budget_block_count"] += 1 if item.get("budget_blocked") else 0
                stage_bucket["backend_error_count"] += 1 if item.get("backend_error") else 0
                stage_bucket["canary_match_count"] += 1 if item.get(f"{track}_canary_match") else 0
                stage_bucket["total_estimated_cost"] += cost
                if item.get("runtime_latency_ms") is not None:
                    stage_bucket["runtime_latencies"].append(float(item["runtime_latency_ms"]))
                track_latency = item.get(f"{track}_latency_ms")
                if track_latency is not None:
                    stage_bucket["track_latencies"].append(float(track_latency))

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
                    "runtime_latencies": [],
                    "candidate_latencies": [],
                    "renderer_latencies": [],
                    "by_provider": {},
                },
            )
            bucket["receipt_count"] += 1
            bucket["incident_count"] += 1 if item.get("incident_flags") else 0
            bucket["total_estimated_cost"] += cost
            bucket["by_provider"][provider] = round(bucket["by_provider"].get(provider, 0.0) + cost, 6)
            if item.get("runtime_latency_ms") is not None:
                bucket["runtime_latencies"].append(float(item["runtime_latency_ms"]))
            if item.get("candidate_latency_ms") is not None:
                bucket["candidate_latencies"].append(float(item["candidate_latency_ms"]))
            if item.get("renderer_latency_ms") is not None:
                bucket["renderer_latencies"].append(float(item["renderer_latency_ms"]))

        provider_summary = []
        for payload in provider_summary_map.values():
            receipt_count = int(payload["receipt_count"])
            provider_summary.append(
                {
                    "provider": payload["provider"],
                    "receipt_count": receipt_count,
                    "incident_count": int(payload["incident_count"]),
                    "selected_as_candidate_count": int(payload["selected_as_candidate_count"]),
                    "selected_as_renderer_count": int(payload["selected_as_renderer_count"]),
                    "fallback_rate": round(payload["fallback_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "budget_block_rate": round(payload["budget_block_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "backend_error_rate": round(payload["backend_error_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                    "cache_hit_rate": (
                        round(payload["cache_hits"] / float(payload["cache_observed"]), 3)
                        if payload["cache_observed"]
                        else None
                    ),
                    "total_estimated_cost": round(payload["total_estimated_cost"], 6),
                    "candidate_estimated_request_cost": round(payload["candidate_estimated_request_cost"], 6),
                    "renderer_estimated_request_cost": round(payload["renderer_estimated_request_cost"], 6),
                    "avg_estimated_cost": round(payload["total_estimated_cost"] / float(receipt_count), 6) if receipt_count else 0.0,
                    "avg_output_chars": round(payload["total_output_chars"] / float(receipt_count), 2) if receipt_count else 0.0,
                    "avg_runtime_latency_ms": self._latency_summary(payload["runtime_latencies"])["avg_latency_ms"],
                    "p95_runtime_latency_ms": self._latency_summary(payload["runtime_latencies"])["p95_latency_ms"],
                    "avg_candidate_latency_ms": self._latency_summary(payload["candidate_latencies"])["avg_latency_ms"],
                    "p95_candidate_latency_ms": self._latency_summary(payload["candidate_latencies"])["p95_latency_ms"],
                    "avg_renderer_latency_ms": self._latency_summary(payload["renderer_latencies"])["avg_latency_ms"],
                    "p95_renderer_latency_ms": self._latency_summary(payload["renderer_latencies"])["p95_latency_ms"],
                    "surface_counts": payload["surface_counts"],
                    "action_counts": payload["action_counts"],
                }
            )
        provider_summary.sort(key=lambda item: (-item["total_estimated_cost"], item["provider"]))

        cost_trend = []
        latency_trend = []
        for payload in sorted(cost_buckets.values(), key=lambda item: item["bucket"], reverse=True)[:limit]:
            cost_trend.append(
                {
                    "bucket": payload["bucket"],
                    "receipt_count": payload["receipt_count"],
                    "incident_count": payload["incident_count"],
                    "total_estimated_cost": round(payload["total_estimated_cost"], 6),
                    "by_provider": dict(payload["by_provider"]),
                }
            )
            latency_trend.append(
                {
                    "bucket": payload["bucket"],
                    "receipt_count": payload["receipt_count"],
                    "runtime": self._latency_summary(payload["runtime_latencies"]),
                    "candidate": self._latency_summary(payload["candidate_latencies"]),
                    "renderer": self._latency_summary(payload["renderer_latencies"]),
                }
            )

        total_cost = round(sum(item["total_estimated_cost"] for item in provider_summary), 6)
        rollout_stage_summary = {}
        for track, buckets in rollout_stage_maps.items():
            entries = []
            for payload in buckets.values():
                receipt_count = int(payload["receipt_count"])
                entries.append(
                    {
                        "rollout_status": payload["rollout_status"],
                        "receipt_count": receipt_count,
                        "incident_count": int(payload["incident_count"]),
                        "incident_rate": round(payload["incident_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                        "fallback_rate": round(payload["fallback_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                        "budget_block_rate": round(payload["budget_block_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                        "backend_error_rate": round(payload["backend_error_count"] / float(receipt_count), 3) if receipt_count else 0.0,
                        "canary_match_count": int(payload["canary_match_count"]),
                        "total_estimated_cost": round(payload["total_estimated_cost"], 6),
                        "avg_estimated_cost": round(payload["total_estimated_cost"] / float(receipt_count), 6) if receipt_count else 0.0,
                        "runtime_latency": self._latency_summary(payload["runtime_latencies"]),
                        "track_latency": self._latency_summary(payload["track_latencies"]),
                    }
                )
            entries.sort(
                key=lambda item: (
                    {"active": 0, "canary": 1, "shadow": 2, "rolled_back": 3}.get(item["rollout_status"], 9),
                    item["rollout_status"],
                )
            )
            rollout_stage_summary[track] = entries
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "provider_summary": provider_summary,
            "cost_trend": cost_trend,
            "latency_trend": latency_trend,
            "rollout_stage_summary": rollout_stage_summary,
            "surface_summary": surface_summary,
            "action_summary": action_summary,
            "receipt_count": len(receipts),
            "total_estimated_cost": total_cost,
            "latency_summary": {
                "runtime": self._latency_summary(runtime_latencies),
                "candidate": self._latency_summary(candidate_latencies),
                "renderer": self._latency_summary(renderer_latencies),
            },
        }
