from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select

from ..persistence.db import AnalyticsEventRow, AuthorWorkRow, SessionRow
from ..persistence.repositories import SQLAlchemyPlatformRepository


LIBRARY_STATS_SEMANTIC_VERSION = "library_stats_semantic/v2"


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


class LibraryStatsSemanticLayerService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _session_rows(self, *, account_id: str) -> List[SessionRow]:
        with self.repository.SessionLocal() as session:
            stmt = (
                select(SessionRow)
                .where(SessionRow.reader_id == account_id)
                .order_by(desc(SessionRow.updated_at))
            )
            return list(session.execute(stmt).scalars().all())

    def _author_work_rows(self, *, account_id: str) -> List[AuthorWorkRow]:
        with self.repository.SessionLocal() as session:
            stmt = (
                select(AuthorWorkRow)
                .where(AuthorWorkRow.account_id == account_id)
                .order_by(desc(AuthorWorkRow.updated_at))
            )
            return list(session.execute(stmt).scalars().all())

    def _continue_counts_by_session(self, *, account_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self.repository.list_analytics_events(
            event_names=["continue_story"],
            reader_id=account_id,
            limit=2000,
        ):
            session_id = str(item.get("session_id") or "").strip()
            if not session_id:
                continue
            counts[session_id] = counts.get(session_id, 0) + 1
        return counts

    def source_updated_at_inputs(self, *, account_id: str) -> Dict[str, Optional[str]]:
        latest_session_updated_at = None
        latest_continue_story_at = None
        latest_author_work_updated_at = None
        with self.repository.SessionLocal() as session:
            latest_session_updated_at = session.execute(
                select(SessionRow.updated_at)
                .where(SessionRow.reader_id == account_id)
                .order_by(desc(SessionRow.updated_at))
                .limit(1)
            ).scalar_one_or_none()
            latest_continue_story_at = session.execute(
                select(AnalyticsEventRow.occurred_at)
                .where(
                    AnalyticsEventRow.reader_id == account_id,
                    AnalyticsEventRow.event_name.in_(["session_created", "continue_story"]),
                )
                .order_by(desc(AnalyticsEventRow.occurred_at))
                .limit(1)
            ).scalar_one_or_none()
            latest_author_work_updated_at = session.execute(
                select(AuthorWorkRow.updated_at)
                .where(AuthorWorkRow.account_id == account_id)
                .order_by(desc(AuthorWorkRow.updated_at))
                .limit(1)
            ).scalar_one_or_none()
        return {
            "latest_session_updated_at": str(latest_session_updated_at or "") or None,
            "latest_continue_story_at": str(latest_continue_story_at or "") or None,
            "latest_author_work_updated_at": str(latest_author_work_updated_at or "") or None,
        }

    def source_updated_at(self, *, account_id: str) -> str:
        latest = datetime.fromtimestamp(0, tz=timezone.utc)
        for value in self.source_updated_at_inputs(account_id=account_id).values():
            latest = max(latest, _parse_timestamp(value))
        return latest.isoformat()

    def build_snapshot_payload(self, *, account_id: str) -> Dict[str, Any]:
        session_rows = self._session_rows(account_id=account_id)
        author_work_rows = self._author_work_rows(account_id=account_id)
        continue_counts = self._continue_counts_by_session(account_id=account_id)

        reader_session_count = len(session_rows)
        reader_continue_count = sum(continue_counts.values())
        reader_turn_units = sum(
            max(int(getattr(row, "chapter_index", 0) or 0), continue_counts.get(str(getattr(row, "session_id", "") or ""), 0) + 1)
            for row in session_rows
        )
        author_work_count = len(author_work_rows)
        author_parallel_branch_count = sum(
            1 for row in author_work_rows if str(getattr(row, "branch_kind", "") or "") == "parallel_universe"
        )

        world_ids = {
            str(self.repository.get_world_version(str(getattr(row, "world_version_id", "") or "")).world_id or "").strip()
            for row in session_rows + author_work_rows
            if str(getattr(row, "world_version_id", "") or "").strip()
        }
        world_ids.discard("")
        fragment_count = len(
            {str(getattr(row, "session_id", "") or "").strip() for row in session_rows if str(getattr(row, "session_id", "") or "").strip()}
            | {str(getattr(row, "work_id", "") or "").strip() for row in author_work_rows if str(getattr(row, "work_id", "") or "").strip()}
        )

        snapshot_payload = {
            "totalPlayTime": round((reader_turn_units * 12) / 60.0, 1) if reader_turn_units else 0,
            "totalBranches": reader_continue_count + author_parallel_branch_count,
            "worldFragments": len(world_ids),
            "totalFragments": fragment_count,
        }
        source_breakdown = {
            "reader_session_count": reader_session_count,
            "reader_continue_count": reader_continue_count,
            "reader_turn_units": reader_turn_units,
            "author_work_count": author_work_count,
            "author_parallel_branch_count": author_parallel_branch_count,
            "world_count": len(world_ids),
            "fragment_count": fragment_count,
            "source_updated_at_inputs": self.source_updated_at_inputs(account_id=account_id),
        }
        return {
            "semantic_version": LIBRARY_STATS_SEMANTIC_VERSION,
            "snapshot_payload": snapshot_payload,
            "source_breakdown": source_breakdown,
            "source_updated_at": self.source_updated_at(account_id=account_id),
        }
