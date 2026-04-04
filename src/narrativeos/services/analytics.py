from __future__ import annotations

from typing import Any, Dict

from ..persistence.repositories import SQLAlchemyPlatformRepository


class AnalyticsService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

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
        return self.repository.record_analytics_event(
            {
                "event_name": event_name,
                "reader_id": payload.get("reader_id"),
                "session_id": payload.get("session_id"),
                "world_version_id": payload.get("world_version_id"),
                "payload_json": {key: value for key, value in payload_json.items() if value is not None},
            }
        )
