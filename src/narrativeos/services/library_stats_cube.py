from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .library_stats_semantic_layer import (
    LIBRARY_STATS_SEMANTIC_VERSION,
    LibraryStatsSemanticLayerService,
)


ZERO_LIBRARY_STATS = {
    "totalPlayTime": 0,
    "totalBranches": 0,
    "worldFragments": 0,
    "totalFragments": 0,
}


def _parse_timestamp(value: Optional[str]) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class LibraryStatsCubeService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        semantic_layer_service: LibraryStatsSemanticLayerService,
    ) -> None:
        self.repository = repository
        self.semantic = semantic_layer_service

    def build_snapshot(self, *, account_id: str) -> Dict[str, Any]:
        return dict(self.semantic.build_snapshot_payload(account_id=account_id).get("snapshot_payload") or ZERO_LIBRARY_STATS)

    def source_updated_at(self, *, account_id: str) -> str:
        return self.semantic.source_updated_at(account_id=account_id)

    def invalidate_account(
        self,
        *,
        account_id: str,
        event_name: str,
        occurred_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.repository.invalidate_library_stats_cube(
            account_id=account_id,
            event_name=event_name,
            occurred_at=occurred_at,
        )

    def is_stale(self, cube: Dict[str, Any], *, source_updated_at: str) -> bool:
        if not cube:
            return True
        if str(cube.get("semantic_version") or "") != LIBRARY_STATS_SEMANTIC_VERSION:
            return True
        if str(cube.get("invalidated_at") or "").strip():
            return True
        cube_source_updated_at = str(cube.get("source_updated_at") or "")
        return _parse_timestamp(cube_source_updated_at) < _parse_timestamp(source_updated_at)

    def sync_account(self, *, account_id: str, source_updated_at: Optional[str] = None) -> Dict[str, Any]:
        semantic_payload = self.semantic.build_snapshot_payload(account_id=account_id)
        resolved_source_updated_at = source_updated_at or str(semantic_payload.get("source_updated_at") or "")
        cube = self.repository.save_library_stats_cube(
            {
                "account_id": account_id,
                "semantic_version": str(semantic_payload.get("semantic_version") or LIBRARY_STATS_SEMANTIC_VERSION),
                "snapshot_payload": semantic_payload.get("snapshot_payload") or ZERO_LIBRARY_STATS,
                "source_breakdown": semantic_payload.get("source_breakdown") or {},
                "source_updated_at": resolved_source_updated_at,
                "invalidated_at": None,
                "last_invalidated_event_name": None,
                "last_invalidated_event_at": None,
            }
        )
        return {
            **cube,
            "snapshot_payload_json": dict(cube.get("snapshot_payload_json") or semantic_payload.get("snapshot_payload") or ZERO_LIBRARY_STATS),
            "source_breakdown_json": dict(cube.get("source_breakdown_json") or semantic_payload.get("source_breakdown") or {}),
        }

    def get_stats(self, *, account_id: Optional[str]) -> Dict[str, Any]:
        if not account_id:
            return dict(ZERO_LIBRARY_STATS)
        current_source_updated_at = self.source_updated_at(account_id=account_id)
        cube = self.repository.get_library_stats_cube(account_id, default={})
        if cube and not self.is_stale(cube, source_updated_at=current_source_updated_at):
            return dict(cube.get("snapshot_payload_json") or ZERO_LIBRARY_STATS)
        synced = self.sync_account(account_id=account_id, source_updated_at=current_source_updated_at)
        return dict(synced.get("snapshot_payload_json") or ZERO_LIBRARY_STATS)
