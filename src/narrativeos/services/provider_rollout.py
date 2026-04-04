from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository


PROVIDER_ROLLOUT_ASSET_TYPE = "provider_rollout"
VALID_TRACKS = {"candidate", "renderer"}
VALID_STATUSES = {"shadow", "canary", "active", "rolled_back"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_notes(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bucket_match(stable_key: str, bucket_percentage: int) -> bool:
    if bucket_percentage <= 0:
        return False
    if bucket_percentage >= 100:
        return True
    digest = hashlib.md5(stable_key.encode("utf-8")).hexdigest()
    sample = int(digest[:8], 16) % 100
    return sample < bucket_percentage


class ProviderRolloutService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _latest_record(self, track: str) -> Optional[Dict[str, Any]]:
        records = self.repository.list_review_records(
            asset_type=PROVIDER_ROLLOUT_ASSET_TYPE,
            asset_id=track,
        )
        return dict(records[0]) if records else None

    def _default_summary(self, *, track: str, backend_present: bool) -> Dict[str, Any]:
        rollout_status = "active" if backend_present else "shadow"
        return {
            "track": track,
            "rollout_status": rollout_status,
            "managed": False,
            "backend_present": backend_present,
            "bucket_percentage": 0,
            "world_allowlist": [],
            "reviewer_id": None,
            "updated_at": None,
            "reason": None,
            "previous_status": None,
            "recommended_action": "monitor_active_rollout" if backend_present else "configure_provider_backend",
        }

    def track_summary(self, *, track: str, backend_present: bool) -> Dict[str, Any]:
        if track not in VALID_TRACKS:
            raise ValueError("invalid_provider_rollout_track")
        record = self._latest_record(track)
        if not record:
            return self._default_summary(track=track, backend_present=backend_present)
        payload = _parse_notes(record.get("notes"))
        status = str(record.get("status") or "shadow")
        if status not in VALID_STATUSES:
            status = "shadow"
        bucket_percentage = max(0, min(100, int(payload.get("bucket_percentage", 0) or 0)))
        world_allowlist = sorted({str(item) for item in payload.get("world_allowlist", []) if str(item).strip()})
        if status == "active":
            recommended_action = "monitor_active_rollout"
        elif status == "canary":
            recommended_action = "monitor_canary_rollout"
        elif status == "rolled_back":
            recommended_action = "investigate_and_reenable"
        elif backend_present:
            recommended_action = "start_canary_rollout"
        else:
            recommended_action = "configure_provider_backend"
        return {
            "track": track,
            "rollout_status": status,
            "managed": True,
            "backend_present": backend_present,
            "bucket_percentage": bucket_percentage,
            "world_allowlist": world_allowlist,
            "reviewer_id": record.get("reviewer_id"),
            "updated_at": record.get("updated_at"),
            "reason": payload.get("reason"),
            "previous_status": payload.get("previous_status"),
            "recommended_action": recommended_action,
        }

    def resolve_track(
        self,
        *,
        track: str,
        backend_present: bool,
        surface: str,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        summary = self.track_summary(track=track, backend_present=backend_present)
        stable_key = (
            str(account_id or "").strip()
            or str(session_id or "").strip()
            or str(world_version_id or "").strip()
            or str(world_id or "").strip()
            or f"{track}:{surface}"
        )
        bucket_percentage = int(summary.get("bucket_percentage", 0) or 0)
        world_allowlist = set(summary.get("world_allowlist", []))
        world_match = not world_allowlist or str(world_id or "") in world_allowlist
        canary_match = _bucket_match(stable_key, bucket_percentage) if summary["rollout_status"] == "canary" else False
        if summary["rollout_status"] == "active":
            enabled = backend_present
        elif summary["rollout_status"] == "canary":
            enabled = backend_present and world_match and canary_match
        else:
            enabled = False
        return {
            **summary,
            "surface": surface,
            "account_id": account_id,
            "session_id": session_id,
            "world_id": world_id,
            "world_version_id": world_version_id,
            "stable_key": stable_key,
            "world_match": world_match,
            "canary_match": canary_match,
            "enabled": enabled,
            "fallback_only": not enabled,
        }

    def save_track_decision(
        self,
        *,
        track: str,
        reviewer_id: str,
        reason: str,
        rollout_status: str,
        bucket_percentage: int = 0,
        world_allowlist: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        if track not in VALID_TRACKS:
            raise ValueError("invalid_provider_rollout_track")
        if rollout_status not in VALID_STATUSES:
            raise ValueError("invalid_provider_rollout_status")
        previous = self.track_summary(track=track, backend_present=True)
        record = self.repository.save_review_record(
            {
                "asset_type": PROVIDER_ROLLOUT_ASSET_TYPE,
                "asset_id": track,
                "status": rollout_status,
                "reviewer_id": reviewer_id,
                "notes": json.dumps(
                    {
                        "reason": reason,
                        "bucket_percentage": max(0, min(100, int(bucket_percentage))),
                        "world_allowlist": sorted({str(item) for item in world_allowlist or [] if str(item).strip()}),
                        "previous_status": previous.get("rollout_status"),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return {
            "track": track,
            "rollout_status": rollout_status,
            "reviewer_id": reviewer_id,
            "updated_at": record.get("updated_at"),
            "reason": reason,
            "bucket_percentage": max(0, min(100, int(bucket_percentage))),
            "world_allowlist": sorted({str(item) for item in world_allowlist or [] if str(item).strip()}),
            "previous_status": previous.get("rollout_status"),
        }

    def summary(self, *, candidate_backend_present: bool, renderer_backend_present: bool) -> Dict[str, Any]:
        candidate = self.track_summary(track="candidate", backend_present=candidate_backend_present)
        renderer = self.track_summary(track="renderer", backend_present=renderer_backend_present)
        active_tracks = [item["track"] for item in (candidate, renderer) if item["rollout_status"] == "active"]
        canary_tracks = [item["track"] for item in (candidate, renderer) if item["rollout_status"] == "canary"]
        rolled_back_tracks = [item["track"] for item in (candidate, renderer) if item["rollout_status"] == "rolled_back"]
        if rolled_back_tracks:
            recommended_next_action = "investigate_and_reenable"
        elif canary_tracks:
            recommended_next_action = "monitor_canary_rollout"
        elif active_tracks:
            recommended_next_action = "monitor_active_rollout"
        else:
            recommended_next_action = "start_canary_rollout"
        return {
            "generated_at": _utcnow(),
            "tracks": {
                "candidate": candidate,
                "renderer": renderer,
            },
            "active_tracks": active_tracks,
            "canary_tracks": canary_tracks,
            "rolled_back_tracks": rolled_back_tracks,
            "recommended_next_action": recommended_next_action,
        }
