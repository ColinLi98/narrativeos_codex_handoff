from __future__ import annotations

from typing import Any, Callable, Dict, List, Set

from ..persistence.repositories import SQLAlchemyPlatformRepository


class AnalyticsService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository
        self._listeners: List[tuple[Set[str], Callable[[Dict[str, Any]], None]]] = []

    def register_listener(self, event_names: set[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append((set(event_names), callback))

    def track(self, event_name: str, **payload: Any) -> Dict[str, Any]:
        reserved = {
            "reader_id",
            "session_id",
            "world_id",
            "world_version_id",
            "chapter_index",
            "access_tier",
            "payload_json",
        }
        payload_json = {
            "world_id": payload.get("world_id"),
            "world_version_id": payload.get("world_version_id"),
            "chapter_index": payload.get("chapter_index"),
            "access_tier": payload.get("access_tier"),
            **dict(payload.get("payload_json", {})),
            **{key: value for key, value in payload.items() if key not in reserved and value is not None},
        }
        saved = self.repository.record_analytics_event(
            {
                "event_name": event_name,
                "reader_id": payload.get("reader_id"),
                "session_id": payload.get("session_id"),
                "world_version_id": payload.get("world_version_id"),
                "payload_json": {key: value for key, value in payload_json.items() if value is not None},
                "occurred_at": payload.get("occurred_at"),
            }
        )
        for listener_event_names, callback in self._listeners:
            if event_name not in listener_event_names:
                continue
            try:
                callback(saved)
            except Exception:
                continue
        return saved
