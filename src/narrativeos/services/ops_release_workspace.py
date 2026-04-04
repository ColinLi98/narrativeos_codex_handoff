from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .ops_traceability import OpsTraceabilityService
from .review import ReviewService


class OpsReleaseWorkspaceService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        review_service: ReviewService,
        ops_traceability_service: OpsTraceabilityService,
    ) -> None:
        self.repository = repository
        self.review = review_service
        self.traceability = ops_traceability_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _selected_world_version_id(self, status_payload: Dict[str, Any]) -> Optional[str]:
        for item in status_payload.get("versions", []):
            if item.get("status") in {"submitted", "draft"}:
                return item.get("world_version_id")
        return status_payload.get("published_version")

    def _release_health_status(
        self,
        *,
        status_payload: Dict[str, Any],
        history_payload: Dict[str, Any],
    ) -> str:
        checklist = dict(status_payload.get("publish_checklist_summary") or {})
        latest_trend = (history_payload.get("quality_trend") or [{}])[0]
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        if not checklist.get("publish_ready"):
            return "blocked"
        if latest_trend.get("regression_detected") or int(rollback_summary.get("total_entries") or 0) > 0:
            return "watch"
        return "ready"

    def _recommended_action(
        self,
        *,
        status_payload: Dict[str, Any],
        history_payload: Dict[str, Any],
        selected_world_version_id: Optional[str],
    ) -> str:
        checklist_summary = dict(status_payload.get("publish_checklist_summary") or {})
        if not checklist_summary.get("publish_ready"):
            return (checklist_summary.get("next_actions") or ["inspect_publish_blockers"])[0]
        if selected_world_version_id and selected_world_version_id != status_payload.get("published_version"):
            return "publish_candidate"
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        if int(rollback_summary.get("total_entries") or 0) > 0:
            return "inspect_recent_rollback"
        return "observe_release_state"

    def _publish_blockers(self, status_payload: Dict[str, Any]) -> Dict[str, Any]:
        blockers = [item for item in status_payload.get("publish_checklist", []) if not item.get("ok")]
        by_owner: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for item in blockers:
            owner = str(item.get("owner") or "unknown")
            severity = str(item.get("severity") or "unknown")
            by_owner[owner] = by_owner.get(owner, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        return {
            "blocker_count": len(blockers),
            "owners": by_owner,
            "severity_counts": by_severity,
            "items": blockers,
        }

    def _review_ownership_summary(self, history_payload: Dict[str, Any], status_payload: Dict[str, Any]) -> Dict[str, Any]:
        review_summary = dict(history_payload.get("review_summary") or {})
        latest_review = (status_payload.get("recent_reviews_drilldown") or [{}])[0]
        return {
            "reviewer_counts": dict(review_summary.get("reviewer_counts") or {}),
            "latest_reviewer_id": latest_review.get("reviewer_id"),
            "latest_review_status": latest_review.get("status"),
            "checklist_owners": list((status_payload.get("publish_checklist_summary") or {}).get("owners") or []),
        }

    def _version_matrix(self, history_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        matrix = []
        for item in history_payload.get("quality_trend", []):
            checklist_summary = dict(item.get("publish_checklist_summary") or {})
            matrix.append(
                {
                    "world_version_id": item.get("world_version_id"),
                    "status": item.get("status"),
                    "latest_decision": item.get("latest_decision"),
                    "cross_pack_pass_rate": item.get("cross_pack_pass_rate"),
                    "pass_rate": item.get("pass_rate"),
                    "block_rate": item.get("block_rate"),
                    "regression_detected": bool(item.get("regression_detected")),
                    "publish_ready": bool(checklist_summary.get("publish_ready")),
                    "blocked_checklist_count": int(checklist_summary.get("blocked_count") or 0),
                    "top_failing_pack_ids": list(item.get("top_failing_pack_ids") or []),
                    "publish_gate_errors": list(item.get("publish_gate_errors") or []),
                    "updated_at": item.get("updated_at"),
                }
            )
        return matrix

    def _rollback_workspace(self, status_payload: Dict[str, Any], history_payload: Dict[str, Any]) -> Dict[str, Any]:
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        latest = (history_payload.get("rollback_drilldown") or [{}])[0]
        return {
            "summary": rollback_summary,
            "latest_rollback": latest if latest.get("review_id") or latest.get("asset_id") else None,
            "rollback_candidates": list(status_payload.get("rollback_targets") or []),
        }

    def _action_pack(
        self,
        *,
        world_id: str,
        status_payload: Dict[str, Any],
        selected_world_version_id: Optional[str],
        publish_blockers: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = [
            {
                "action_id": "open_release_investigation",
                "label": "Open Release Investigation",
                "handler": "run_release_investigation",
                "mode": "navigate",
                "reason": "inspect content release evidence chain",
                "priority": 0,
                "prefill": {"world_version_id": selected_world_version_id},
            }
        ]
        if selected_world_version_id and not publish_blockers.get("items") and selected_world_version_id != status_payload.get("published_version"):
            actions.append(
                {
                    "action_id": "publish_candidate",
                    "label": "Publish Candidate",
                    "handler": "publish_world_version",
                    "mode": "execute",
                    "reason": "publish checklist is green",
                    "priority": 1,
                    "prefill": {"world_version_id": selected_world_version_id},
                }
            )
        rollback_targets = list(status_payload.get("rollback_targets") or [])
        if rollback_targets:
            actions.append(
                {
                    "action_id": "rollback_world",
                    "label": "Rollback To Previous",
                    "handler": "rollback_world",
                    "mode": "execute",
                    "reason": "a rollback candidate exists",
                    "priority": 2,
                    "prefill": {
                        "world_id": world_id,
                        "target_world_version_id": rollback_targets[0].get("world_version_id"),
                    },
                }
            )
        for item in publish_blockers.get("items", [])[:3]:
            actions.append(
                {
                    "action_id": f"inspect_blocker::{item.get('key')}",
                    "label": f"Inspect {item.get('label') or item.get('key')}",
                    "handler": "inspect_publish_blocker",
                    "mode": "navigate",
                    "reason": item.get("reason") or "publish blocker present",
                    "priority": 1,
                    "prefill": {"blocker_key": item.get("key"), "world_version_id": selected_world_version_id},
                }
            )
        deduped: Dict[str, Dict[str, Any]] = {}
        for action in actions:
            if action["action_id"] not in deduped or action["priority"] < deduped[action["action_id"]]["priority"]:
                deduped[action["action_id"]] = action
        return sorted(deduped.values(), key=lambda item: (item["priority"], item["label"]))

    def _operator_timeline(
        self,
        *,
        history_payload: Dict[str, Any],
        status_payload: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for item in history_payload.get("review_timeline", []):
            entries.append(
                {
                    "entry_id": item.get("review_id") or item.get("asset_id"),
                    "occurred_at": item.get("updated_at"),
                    "category": "review" if item.get("timeline_group") != "rollback" else "rollback",
                    "headline": item.get("status") or "review_event",
                    "summary": f"{item.get('world_version_id') or item.get('target_world_version_id') or '-'} · reviewer {item.get('reviewer_id') or '-'}",
                    "next_actions": list(item.get("publish_gate_errors") or []),
                }
            )
        for item in status_payload.get("recent_entitlement_events", []):
            entries.append(
                {
                    "entry_id": f"entitlement::{item.get('event_id') or item.get('occurred_at')}",
                    "occurred_at": item.get("occurred_at"),
                    "category": "entitlement",
                    "headline": item.get("event_name") or "entitlement_event",
                    "summary": f"{item.get('reason') or '-'} · balance {item.get('balance') if item.get('balance') is not None else '-'}",
                    "next_actions": [],
                }
            )
        entries.sort(key=lambda item: self._parse_timestamp(item.get("occurred_at")), reverse=True)
        return entries[:limit]

    def world_release_workspace(self, *, world_id: str, limit: int = 12) -> Dict[str, Any]:
        status_payload = self.review.world_status(world_id)
        history_payload = self.review.world_history(world_id)
        selected_world_version_id = self._selected_world_version_id(status_payload)
        publish_blockers = self._publish_blockers(status_payload)
        investigation = (
            self.traceability.investigate_world_version(selected_world_version_id, limit=min(limit, 12))
            if selected_world_version_id
            else None
        )
        return {
            "generated_at": self._utcnow(),
            "world_id": world_id,
            "selected_world_version_id": selected_world_version_id,
            "release_summary": {
                "health_status": self._release_health_status(status_payload=status_payload, history_payload=history_payload),
                "recommended_action": self._recommended_action(
                    status_payload=status_payload,
                    history_payload=history_payload,
                    selected_world_version_id=selected_world_version_id,
                ),
                "published_version": status_payload.get("published_version"),
                "selected_world_version_id": selected_world_version_id,
                "publish_ready": bool((status_payload.get("publish_checklist_summary") or {}).get("publish_ready")),
                "blocked_checklist_count": int((status_payload.get("publish_checklist_summary") or {}).get("blocked_count") or 0),
                "recent_rollback_count": int((history_payload.get("rollback_summary") or {}).get("total_entries") or 0),
                "latest_rollback_target": (history_payload.get("rollback_summary") or {}).get("latest_target_world_version_id"),
            },
            "publish_blockers": publish_blockers,
            "review_ownership_summary": self._review_ownership_summary(history_payload, status_payload),
            "version_matrix": self._version_matrix(history_payload),
            "rollback_workspace": self._rollback_workspace(status_payload, history_payload),
            "action_pack": self._action_pack(
                world_id=world_id,
                status_payload=status_payload,
                selected_world_version_id=selected_world_version_id,
                publish_blockers=publish_blockers,
            ),
            "investigation_summary": {
                "recommended_paths": (investigation or {}).get("recommended_paths") or [],
                "summary": (investigation or {}).get("investigation_summary") or {},
                "export_refs": (investigation or {}).get("export_refs") or {"world_version_id": selected_world_version_id},
            },
            "linked_context": {
                "world_id": world_id,
                "published_version": status_payload.get("published_version"),
                "rollback_target_ids": [item.get("world_version_id") for item in status_payload.get("rollback_targets", [])],
                "review_ids": [item.get("review_id") for item in history_payload.get("review_timeline", []) if item.get("review_id")],
            },
            "operator_timeline": self._operator_timeline(
                history_payload=history_payload,
                status_payload=status_payload,
                limit=limit,
            ),
            "world_status": status_payload,
            "world_history": history_payload,
        }
