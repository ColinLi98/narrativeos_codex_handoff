from __future__ import annotations

from typing import Any, Dict, Optional

from .library_stats_cube import LibraryStatsCubeService


LIBRARY_STATS_INVALIDATION_EVENTS = {
    "session_created",
    "continue_story",
    "author_work_created",
    "author_work_branch_created",
    "author_work_deleted",
    "session_deleted",
}


class LibraryStatsCubeProjectionService:
    def __init__(self, *, cube_service: LibraryStatsCubeService) -> None:
        self.cube = cube_service

    def _account_id_from_event(self, event: Dict[str, Any]) -> Optional[str]:
        payload_json = dict(event.get("payload_json") or {})
        account_id = str(payload_json.get("account_id") or event.get("reader_id") or "").strip()
        return account_id or None

    def on_analytics_event(self, event: Dict[str, Any]) -> None:
        event_name = str(event.get("event_name") or "").strip()
        if event_name not in LIBRARY_STATS_INVALIDATION_EVENTS:
            return
        account_id = self._account_id_from_event(event)
        if not account_id:
            return
        self.cube.invalidate_account(
            account_id=account_id,
            event_name=event_name,
            occurred_at=str(event.get("occurred_at") or "").strip() or None,
        )
