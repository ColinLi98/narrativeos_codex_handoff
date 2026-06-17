from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import quote

from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .analytics import AnalyticsService
    from .billing import BillingService
    from .author_work import AuthorWorkService
    from .illustration import IllustrationService
    from .library_stats_cube import LibraryStatsCubeService


SOUL_DIMENSION_LABELS = ("理性", "情感", "冒险", "命运", "混沌")
VALID_SOUL_PRIVACY_MODES = {"public", "followers", "private"}
VALID_LIBRARY_FILTERS = {"recent", "favorites", "following", "completed"}
VALID_SHOWCASE_SORTS = {"hot", "new", "ongoing"}


def _is_public_catalog_visible(metadata: Dict[str, Any]) -> bool:
    if str(metadata.get("catalog_role") or "").strip() == "template":
        return False
    if metadata.get("public_catalog_visible") is False:
        return False
    return True


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


def _clamp_percent(value: Any) -> int:
    try:
        numeric = int(round(float(value or 0)))
    except (TypeError, ValueError):
        numeric = 0
    return max(0, min(100, numeric))


class QuantumReadModelService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        author_work_service: "AuthorWorkService",
        analytics_service: Optional["AnalyticsService"] = None,
        billing_service: Optional["BillingService"] = None,
        library_stats_cube_service: Optional["LibraryStatsCubeService"] = None,
        illustration_service: Optional["IllustrationService"] = None,
    ) -> None:
        self.repository = repository
        self.author_work_service = author_work_service
        self.analytics = analytics_service
        self.billing = billing_service
        self.library_stats_cube = library_stats_cube_service
        self.illustration = illustration_service

    def _world_cover_url(self, *, world_version_id: str) -> str:
        if self.illustration is None or not world_version_id:
            return ""
        return self.illustration.world_cover_url(world_version_id=world_version_id)

    def _session_cover_url(self, *, session_id: str, world_version_id: str) -> str:
        if self.illustration is None:
            return ""
        return self.illustration.session_cover_url(session_id=session_id) or self._world_cover_url(
            world_version_id=world_version_id
        )

    def _resolve_identity_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        normalized = str(user_id or "").strip()
        if not normalized or normalized == "guest":
            return None
        try:
            return self.repository.get_auth_identity(normalized)
        except KeyError:
            pass
        try:
            return self.repository.get_auth_identity_by_account_id(normalized)
        except KeyError:
            return None

    def _default_soul_preferences(self, *, actor_id: str, account_id: Optional[str]) -> Dict[str, Any]:
        return {
            "actor_id": actor_id,
            "account_id": account_id,
            "genres": [],
            "styles": [],
            "privacy_mode": "followers",
        }

    def get_soul_preferences(self, *, actor_id: str, account_id: Optional[str]) -> Dict[str, Any]:
        return self.repository.get_soul_profile_preferences(
            actor_id,
            default=self._default_soul_preferences(actor_id=actor_id, account_id=account_id),
        )

    def update_soul_preferences(
        self,
        *,
        actor_id: str,
        account_id: Optional[str],
        genres: Optional[List[str]] = None,
        styles: Optional[List[str]] = None,
        privacy_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_soul_preferences(actor_id=actor_id, account_id=account_id)
        next_privacy_mode = str(privacy_mode or existing.get("privacy_mode") or "followers").strip() or "followers"
        if next_privacy_mode not in VALID_SOUL_PRIVACY_MODES:
            raise ValueError("soul_preferences_privacy_invalid")
        return self.repository.save_soul_profile_preferences(
            {
                "actor_id": actor_id,
                "account_id": account_id,
                "genres": existing.get("genres") if genres is None else genres,
                "styles": existing.get("styles") if styles is None else styles,
                "privacy_mode": next_privacy_mode,
            }
        )

    def _reader_continue_counts_by_session(self, *, account_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for event in self.repository.list_analytics_events(
            event_names=["continue_story"],
            reader_id=account_id,
            limit=1000,
        ):
            session_id = str(event.get("session_id") or "").strip()
            if not session_id:
                continue
            counts[session_id] = counts.get(session_id, 0) + 1
        return counts

    def _reader_recent_activity_map(self, *, account_id: str) -> Dict[str, Dict[str, Any]]:
        items: Dict[str, Dict[str, Any]] = {}
        for event in self.repository.list_analytics_events(
            event_names=["session_created", "continue_story", "story_share_created", "story_share_revoked"],
            reader_id=account_id,
            limit=1000,
        ):
            session_id = str(event.get("session_id") or "").strip()
            if not session_id:
                continue
            occurred_at = str(event.get("occurred_at") or "")
            current = items.get(session_id)
            if current is None or _parse_timestamp(occurred_at) > _parse_timestamp(current.get("occurred_at")):
                items[session_id] = dict(event)
        return items

    def _bookmark_summary_by_session(self, *, account_id: str) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        for item in self.repository.list_story_session_bookmarks(account_id=account_id):
            session_id = str(item.get("session_id") or "").strip()
            node_id = str(item.get("node_id") or "").strip()
            if not session_id:
                continue
            entry = summary.setdefault(
                session_id,
                {"node_ids": set(), "count": 0, "latest_node_id": None, "_updated_at_dt": datetime.fromtimestamp(0, tz=timezone.utc)},
            )
            if node_id:
                entry["node_ids"].add(node_id)
            entry["count"] += 1
            updated_at = _parse_timestamp(item.get("updated_at") or item.get("created_at"))
            if updated_at >= entry["_updated_at_dt"]:
                entry["_updated_at_dt"] = updated_at
                entry["latest_node_id"] = node_id or entry.get("latest_node_id")
        return summary

    def _story_session_current_node_id(self, session_id: str) -> str:
        latest_step = self.repository.get_latest_step(session_id)
        if latest_step is not None:
            step_index = int(getattr(latest_step, "step_index", 0) or 0)
            if step_index > 0:
                return f"node:{session_id}:{step_index}"
        return f"node:{session_id}:0"

    def _library_favorite_state(self, *, account_id: str) -> Dict[str, Any]:
        state_by_work_id: Dict[str, Dict[str, Any]] = {}
        for event in self.repository.list_analytics_events(
            event_names=["library_work_favorited", "library_work_unfavorited"],
            reader_id=account_id,
            limit=4000,
        ):
            payload = dict(event.get("payload_json") or {})
            work_id = str(payload.get("work_id") or "").strip()
            work_kind = str(payload.get("work_kind") or "").strip() or None
            if not work_id:
                continue
            occurred_at = _parse_timestamp(event.get("occurred_at"))
            current = state_by_work_id.get(work_id)
            if current is None or occurred_at >= current["_occurred_at_dt"]:
                state_by_work_id[work_id] = {
                    "active": str(event.get("event_name") or "") == "library_work_favorited",
                    "work_kind": work_kind,
                    "_occurred_at_dt": occurred_at,
                }
        reader_session_ids = {
            work_id
            for work_id, item in state_by_work_id.items()
            if item.get("active") and item.get("work_kind") == "reader_session"
        }
        author_work_ids = {
            work_id
            for work_id, item in state_by_work_id.items()
            if item.get("active") and item.get("work_kind") == "author_work"
        }
        active_work_ids = {
            work_id
            for work_id, item in state_by_work_id.items()
            if item.get("active")
        }
        updated_at_by_work_id = {
            work_id: str(item["_occurred_at_dt"].isoformat())
            for work_id, item in state_by_work_id.items()
            if item.get("active")
        }
        return {
            "reader_session_ids": reader_session_ids,
            "author_work_ids": author_work_ids,
            "active_work_ids": active_work_ids,
            "updated_at_by_work_id": updated_at_by_work_id,
        }

    def _library_follow_state(self, *, account_id: str) -> Dict[str, Any]:
        state_by_target: Dict[tuple[str, str], Dict[str, Any]] = {}
        for event in self.repository.list_analytics_events(
            event_names=["library_target_followed", "library_target_unfollowed"],
            reader_id=account_id,
            limit=4000,
        ):
            payload = dict(event.get("payload_json") or {})
            target_type = str(payload.get("target_type") or "").strip()
            target_id = str(payload.get("target_id") or "").strip()
            if not target_type or not target_id:
                continue
            occurred_at = _parse_timestamp(event.get("occurred_at"))
            key = (target_type, target_id)
            current = state_by_target.get(key)
            if current is None or occurred_at >= current["_occurred_at_dt"]:
                state_by_target[key] = {
                    "active": str(event.get("event_name") or "") == "library_target_followed",
                    "_occurred_at_dt": occurred_at,
                }
        author_ids = {
            target_id
            for (target_type, target_id), item in state_by_target.items()
            if target_type == "author" and item.get("active")
        }
        world_ids = {
            target_id
            for (target_type, target_id), item in state_by_target.items()
            if target_type == "world" and item.get("active")
        }
        updated_at_by_target = {
            f"{target_type}:{target_id}": str(item["_occurred_at_dt"].isoformat())
            for (target_type, target_id), item in state_by_target.items()
            if item.get("active")
        }
        return {"author_ids": author_ids, "world_ids": world_ids, "updated_at_by_target": updated_at_by_target}

    def _library_bookmark_state(self, *, account_id: str) -> Dict[str, Dict[str, Any]]:
        state_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
        for event in self.repository.list_analytics_events(
            event_names=["story_bookmark_created", "story_bookmark_deleted"],
            reader_id=account_id,
            limit=4000,
        ):
            payload = dict(event.get("payload_json") or {})
            session_id = str(event.get("session_id") or payload.get("session_id") or "").strip()
            node_id = str(payload.get("node_id") or "").strip()
            if not session_id or not node_id:
                continue
            occurred_at = _parse_timestamp(event.get("occurred_at"))
            key = (session_id, node_id)
            current = state_by_key.get(key)
            if current is None or occurred_at >= current["_occurred_at_dt"]:
                state_by_key[key] = {
                    "active": str(event.get("event_name") or "") == "story_bookmark_created",
                    "_occurred_at_dt": occurred_at,
                }
        summary: Dict[str, Dict[str, Any]] = {}
        for (session_id, node_id), item in state_by_key.items():
            if not item.get("active"):
                continue
            entry = summary.setdefault(
                session_id,
                {"node_ids": set(), "count": 0, "latest_node_id": None, "_updated_at_dt": datetime.fromtimestamp(0, tz=timezone.utc)},
            )
            entry["node_ids"].add(node_id)
            entry["count"] += 1
            updated_at = item["_occurred_at_dt"]
            if updated_at >= entry["_updated_at_dt"]:
                entry["_updated_at_dt"] = updated_at
                entry["latest_node_id"] = node_id
        return summary

    def _canonical_library_state_bundle(self, *, account_id: str) -> Dict[str, Any]:
        favorite_state = self._library_favorite_state(account_id=account_id)
        follow_state = self._library_follow_state(account_id=account_id)
        bookmark_state = self._library_bookmark_state(account_id=account_id)
        return {
            "favorite_state": favorite_state,
            "follow_state": follow_state,
            "bookmark_state": bookmark_state,
        }

    def _projected_current_node_id(self, session_id: str) -> str:
        try:
            session = self.repository.get_session(session_id)
        except KeyError:
            return f"node:{session_id}:0"
        return f"node:{session_id}:{int(getattr(session.current_state, 'chapter_index', 0) or 0)}"

    def _reader_session_items(
        self,
        *,
        account_id: str,
        favorite_ids_override: Optional[set[str]] = None,
        followed_world_ids_override: Optional[set[str]] = None,
        bookmark_summary_override: Optional[Dict[str, Dict[str, Any]]] = None,
        current_node_resolver: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        activity_by_session = self._reader_recent_activity_map(account_id=account_id)
        continue_counts = self._reader_continue_counts_by_session(account_id=account_id)
        bookmark_summary = (
            bookmark_summary_override
            if bookmark_summary_override is not None
            else self._bookmark_summary_by_session(account_id=account_id)
        )
        followed_world_ids = (
            followed_world_ids_override
            if followed_world_ids_override is not None
            else self._follow_sets(account_id=account_id)["world_ids"]
        )
        favorite_ids = (
            favorite_ids_override
            if favorite_ids_override is not None
            else {
                str(item.get("work_id") or "")
                for item in self.repository.list_library_work_favorites(account_id=account_id)
                if str(item.get("work_kind") or "") == "reader_session"
            }
        )
        items: List[Dict[str, Any]] = []
        for session in self.repository.list_sessions():
            session_id = str(session.get("session_id") or "").strip()
            if not session_id:
                continue
            try:
                detail = self.repository.get_session(session_id)
            except KeyError:
                continue
            owner_account_id = str(detail.metadata.get("reader_id") or detail.player_profile.get("reader_id") or "").strip()
            if owner_account_id != account_id:
                continue
            activity = activity_by_session.get(session_id, {})
            updated_at = str(activity.get("occurred_at") or session.get("created_at") or "")
            current_node_id = (
                current_node_resolver(session_id)
                if current_node_resolver is not None
                else self._projected_current_node_id(session_id)
            )
            bookmark_entry = dict(bookmark_summary.get(session_id) or {})
            progress_units = int(session.get("current_turn_index") or 0)
            deviation_value = _clamp_percent(float(getattr(detail.current_state, "fate_pressure", 0.0) or 0.0) * 100.0)
            items.append(
                {
                    "id": session_id,
                    "title": str(session.get("last_chapter_title") or session.get("world_id") or session_id),
                    "coverImage": self._session_cover_url(
                        session_id=session_id,
                        world_version_id=str(session.get("world_version_id") or ""),
                    ),
                    "author": "最近阅读",
                    "status": str(detail.status or "active") if getattr(detail, "status", None) else "active",
                    "progress": min(100, progress_units * 10),
                    "branchCount": int(continue_counts.get(session_id, 0)),
                    "endingCount": 1 if str(getattr(detail, "status", "") or "") == "completed" else 0,
                    "totalEndings": 1,
                    "deviation": deviation_value,
                    "lastPlayedAt": updated_at,
                    "universe": str(session.get("world_id") or ""),
                    "worldId": str(session.get("world_id") or ""),
                    "kind": "reader_session",
                    "targetHref": f"/story?session={quote(session_id, safe='')}",
                    "updatedAt": updated_at,
                    "currentNodeId": current_node_id,
                    "viewerHasBookmarkedCurrentNode": current_node_id in set(bookmark_entry.get("node_ids") or set()),
                    "bookmarkCount": int(bookmark_entry.get("count") or 0),
                    "isFavorited": session_id in favorite_ids,
                    "viewerHasFollowedWorld": str(session.get("world_id") or "") in followed_world_ids,
                    "_updated_at_dt": _parse_timestamp(updated_at),
                    "_world_id": str(session.get("world_id") or ""),
                    "_account_id": account_id,
                    "_work_kind": "reader_session",
                }
            )
        items.sort(key=lambda item: item["_updated_at_dt"], reverse=True)
        return items

    def _author_work_items(
        self,
        *,
        account_id: str,
        favorite_ids_override: Optional[set[str]] = None,
        followed_world_ids_override: Optional[set[str]] = None,
    ) -> List[Dict[str, Any]]:
        works = list((self.author_work_service.list_works(account_id=account_id) or {}).get("works") or [])
        followed_world_ids = (
            followed_world_ids_override
            if followed_world_ids_override is not None
            else self._follow_sets(account_id=account_id)["world_ids"]
        )
        favorite_ids = (
            favorite_ids_override
            if favorite_ids_override is not None
            else {
                str(item.get("work_id") or "")
                for item in self.repository.list_library_work_favorites(account_id=account_id)
                if str(item.get("work_kind") or "") == "author_work"
            }
        )
        items: List[Dict[str, Any]] = []
        for work in works:
            branch_family = list(work.get("branch_family") or [])
            target_count = int(work.get("target_chapter_count") or 0)
            chapter_count = int(work.get("chapter_count") or 0)
            world_version_id = str(work.get("world_version_id") or "").strip()
            world_id = world_version_id.split("@")[0] if world_version_id else ""
            updated_at = str(work.get("updated_at") or "")
            diagnostics = dict(work.get("diagnostics_summary_json") or {})
            top_issue_codes = [str(item) for item in list(diagnostics.get("top_issue_codes") or []) if str(item).strip()]
            items.append(
                {
                    "id": str(work.get("work_id") or ""),
                    "title": str(work.get("title") or world_version_id or "未命名作品"),
                    "coverImage": self._world_cover_url(world_version_id=world_version_id),
                    "author": "我的创作",
                    "status": "completed" if str(work.get("status") or "") == "submitted" else "active",
                    "progress": round((chapter_count / target_count) * 100) if target_count > 0 else min(100, chapter_count * 10),
                    "branchCount": sum(1 for item in branch_family if str(item.get("branch_kind") or "") == "parallel_universe"),
                    "endingCount": 1 if str(work.get("status") or "") == "submitted" else 0,
                    "totalEndings": max(1, sum(1 for item in branch_family if str(item.get("branch_kind") or "") == "parallel_universe") + 1),
                    "deviation": _clamp_percent(len(top_issue_codes) * 12),
                    "lastPlayedAt": updated_at,
                    "universe": world_id,
                    "worldId": world_id,
                    "kind": "author_work",
                    "targetHref": f"/studio/{quote(world_version_id, safe='')}" if world_version_id else "/studio",
                    "updatedAt": updated_at,
                    "isFavorited": str(work.get("work_id") or "") in favorite_ids,
                    "viewerHasFollowedWorld": world_id in followed_world_ids,
                    "_updated_at_dt": _parse_timestamp(updated_at),
                    "_world_id": world_id,
                    "_account_id": account_id,
                    "_work_kind": "author_work",
                    "_author_id": account_id,
                }
            )
        items.sort(key=lambda item: item["_updated_at_dt"], reverse=True)
        return items

    def _author_draft_activity_items(self, *, account_id: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for item in self.repository.list_world_versions():
            if str(item.get("author_id") or "").strip() != account_id:
                continue
            world_version_id = str(item.get("world_version_id") or "").strip()
            if not world_version_id:
                continue
            updated_at = str(item.get("updated_at") or "")
            items.append(
                {
                    "id": world_version_id,
                    "title": str(item.get("title") or world_version_id),
                    "coverImage": self._world_cover_url(world_version_id=world_version_id),
                    "branchName": "创作草稿",
                    "progress": 0,
                    "kind": "author_draft",
                    "targetHref": f"/studio/{quote(world_version_id, safe='')}",
                    "updatedAt": updated_at,
                    "_updated_at_dt": _parse_timestamp(updated_at),
                }
            )
        items.sort(key=lambda item: item["_updated_at_dt"], reverse=True)
        return items

    def _follow_sets(self, *, account_id: str) -> Dict[str, set[str]]:
        author_ids: set[str] = set()
        world_ids: set[str] = set()
        for item in self.repository.list_library_follows(account_id=account_id):
            target_type = str(item.get("target_type") or "")
            target_id = str(item.get("target_id") or "")
            if target_type == "author":
                author_ids.add(target_id)
            elif target_type == "world":
                world_ids.add(target_id)
        return {"author_ids": author_ids, "world_ids": world_ids}

    def _canonical_world_follow_target(self, target_id: str) -> str:
        normalized = str(target_id or "").strip()
        if not normalized:
            raise KeyError("library_follow_target_missing")
        try:
            version = self.repository.get_world_version(normalized)
        except KeyError:
            version = None
        if version is not None:
            return str(version.world_id or "").strip()
        world_ids = {
            str(item.get("world_id") or "").strip()
            for item in self.repository.list_worlds()
            if str(item.get("world_id") or "").strip()
        }
        if normalized in world_ids:
            return normalized
        if self.repository.list_world_versions(world_id=normalized):
            return normalized
        raise KeyError(f"library_follow_target_missing:{normalized}")

    def _canonical_author_follow_target(self, target_id: str) -> str:
        identity = self._resolve_identity_by_user_id(target_id)
        if identity is None:
            raise KeyError(f"library_follow_target_missing:{str(target_id or '').strip()}")
        actor_id = str(identity.get("actor_id") or "").strip()
        if not actor_id:
            raise KeyError(f"library_follow_target_missing:{str(target_id or '').strip()}")
        return actor_id

    def follow_library_target(
        self,
        *,
        account_id: str,
        actor_id: Optional[str],
        target_type: str,
        target_id: str,
    ) -> Dict[str, Any]:
        normalized_type = str(target_type or "").strip()
        if normalized_type == "world":
            canonical_target_id = self._canonical_world_follow_target(target_id)
        elif normalized_type == "author":
            canonical_target_id = self._canonical_author_follow_target(target_id)
            if actor_id and canonical_target_id == str(actor_id or "").strip():
                raise ValueError("library_follow_self_forbidden")
        else:
            raise ValueError("library_follow_target_type_invalid")
        payload = self.repository.save_library_follow(
            {
                "account_id": account_id,
                "target_type": normalized_type,
                "target_id": canonical_target_id,
            }
        )
        if self.analytics is not None:
            self.analytics.track(
                "library_target_followed",
                reader_id=account_id,
                account_id=account_id,
                payload_json={
                    "target_type": normalized_type,
                    "target_id": canonical_target_id,
                },
            )
        return {
            "followId": payload.get("follow_id"),
            "targetType": normalized_type,
            "targetId": canonical_target_id,
            "following": True,
        }

    def unfollow_library_target(
        self,
        *,
        account_id: str,
        actor_id: Optional[str],
        target_type: str,
        target_id: str,
    ) -> Dict[str, Any]:
        normalized_type = str(target_type or "").strip()
        if normalized_type == "world":
            canonical_target_id = self._canonical_world_follow_target(target_id)
        elif normalized_type == "author":
            canonical_target_id = self._canonical_author_follow_target(target_id)
            if actor_id and canonical_target_id == str(actor_id or "").strip():
                raise ValueError("library_follow_self_forbidden")
        else:
            raise ValueError("library_follow_target_type_invalid")
        payload = self.repository.delete_library_follow(
            account_id=account_id,
            target_type=normalized_type,
            target_id=canonical_target_id,
        )
        if self.analytics is not None:
            self.analytics.track(
                "library_target_unfollowed",
                reader_id=account_id,
                account_id=account_id,
                payload_json={
                    "target_type": normalized_type,
                    "target_id": canonical_target_id,
                },
            )
        return {
            "followId": payload.get("follow_id"),
            "targetType": normalized_type,
            "targetId": canonical_target_id,
            "following": False,
            "deleted": bool(payload.get("deleted")),
        }

    def _all_library_items(self, *, account_id: str) -> List[Dict[str, Any]]:
        state_bundle = self._canonical_library_state_bundle(account_id=account_id)
        items = self._reader_session_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["reader_session_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
            bookmark_summary_override=state_bundle["bookmark_state"],
            current_node_resolver=self._story_session_current_node_id,
        ) + self._author_work_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["author_work_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
        )
        items.sort(key=lambda item: item["_updated_at_dt"], reverse=True)
        return items

    def library_works(self, *, account_id: Optional[str], filter_value: str) -> List[Dict[str, Any]]:
        if not account_id:
            return []
        normalized = str(filter_value or "").strip()
        if normalized not in VALID_LIBRARY_FILTERS:
            normalized = "recent"
        state_bundle = self._canonical_library_state_bundle(account_id=account_id)
        items = self._reader_session_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["reader_session_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
            bookmark_summary_override=state_bundle["bookmark_state"],
            current_node_resolver=self._story_session_current_node_id,
        ) + self._author_work_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["author_work_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
        )
        items.sort(key=lambda item: item["_updated_at_dt"], reverse=True)
        if normalized == "recent":
            selected = items
        elif normalized == "favorites":
            selected = [item for item in items if bool(item.get("isFavorited"))]
        elif normalized == "following":
            selected = [
                item for item in items
                if str(item.get("_world_id") or "") in state_bundle["follow_state"]["world_ids"]
            ]
        else:
            selected = [item for item in items if str(item.get("status") or "") == "completed"]
        output: List[Dict[str, Any]] = []
        for item in selected:
            payload = dict(item)
            for transient in ("_updated_at_dt", "_world_id", "_account_id", "_work_kind", "_author_id"):
                payload.pop(transient, None)
            output.append(payload)
        return output

    def resolve_library_work(self, *, account_id: str, work_id: str) -> Dict[str, Any]:
        for item in self._all_library_items(account_id=account_id):
            if str(item.get("id") or "") == work_id:
                return item
        raise KeyError("library_work_missing:%s" % work_id)

    def favorite_library_work(self, *, account_id: str, work_id: str) -> Dict[str, Any]:
        work = self.resolve_library_work(account_id=account_id, work_id=work_id)
        payload = self.repository.save_library_work_favorite(
            {
                "account_id": account_id,
                "work_id": work_id,
                "work_kind": work.get("_work_kind") or work.get("kind") or "reader_session",
                "title_snapshot": work.get("title"),
            }
        )
        if self.analytics is not None:
            self.analytics.track(
                "library_work_favorited",
                reader_id=account_id,
                account_id=account_id,
                payload_json={
                    "work_id": work_id,
                    "work_kind": payload.get("work_kind") or work.get("_work_kind") or work.get("kind") or "reader_session",
                },
            )
        return payload

    def unfavorite_library_work(self, *, account_id: str, work_id: str) -> Dict[str, Any]:
        payload = self.repository.delete_library_work_favorite(account_id=account_id, work_id=work_id)
        if self.analytics is not None:
            self.analytics.track(
                "library_work_unfavorited",
                reader_id=account_id,
                account_id=account_id,
                payload_json={
                    "work_id": work_id,
                    "work_kind": payload.get("work_kind"),
                },
            )
        return payload

    def bookmark_story_node(self, *, account_id: str, session_id: str, node_id: str) -> Dict[str, Any]:
        payload = self.repository.save_story_session_bookmark(
            {
                "session_id": session_id,
                "account_id": account_id,
                "node_id": node_id,
            }
        )
        if self.analytics is not None:
            try:
                session = self.repository.get_session(session_id)
                world_id = session.world_id
                world_version_id = session.metadata.get("world_version_id")
            except KeyError:
                world_id = None
                world_version_id = None
            self.analytics.track(
                "story_bookmark_created",
                reader_id=account_id,
                account_id=account_id,
                session_id=session_id,
                world_id=world_id,
                world_version_id=world_version_id,
                payload_json={"node_id": node_id},
            )
        return payload

    def unbookmark_story_node(self, *, account_id: str, session_id: str, node_id: str) -> Dict[str, Any]:
        payload = self.repository.delete_story_session_bookmark(
            session_id=session_id,
            account_id=account_id,
            node_id=node_id,
        )
        if self.analytics is not None:
            try:
                session = self.repository.get_session(session_id)
                world_id = session.world_id
                world_version_id = session.metadata.get("world_version_id")
            except KeyError:
                world_id = None
                world_version_id = None
            self.analytics.track(
                "story_bookmark_deleted",
                reader_id=account_id,
                account_id=account_id,
                session_id=session_id,
                world_id=world_id,
                world_version_id=world_version_id,
                payload_json={"node_id": node_id},
            )
        return payload

    def library_stats(self, *, account_id: Optional[str]) -> Dict[str, Any]:
        if not account_id or self.library_stats_cube is None:
            return {
                "totalPlayTime": 0,
                "totalBranches": 0,
                "worldFragments": 0,
                "totalFragments": 0,
            }
        return self.library_stats_cube.get_stats(account_id=account_id)

    def library_achievements(self, *, account_id: Optional[str]) -> List[Dict[str, Any]]:
        if not account_id:
            return []
        state_bundle = self._canonical_library_state_bundle(account_id=account_id)
        sessions = self._reader_session_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["reader_session_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
            bookmark_summary_override=state_bundle["bookmark_state"],
            current_node_resolver=self._story_session_current_node_id,
        )
        author_items = self._author_work_items(
            account_id=account_id,
            favorite_ids_override=set(state_bundle["favorite_state"]["author_work_ids"]),
            followed_world_ids_override=set(state_bundle["follow_state"]["world_ids"]),
        )
        continue_counts = self._reader_continue_counts_by_session(account_id=account_id)
        unlocked_world_count = len({str(item.get("_world_id") or "") for item in sessions + author_items if str(item.get("_world_id") or "").strip()})
        favorite_updated_ats = list(state_bundle["favorite_state"]["updated_at_by_work_id"].values())
        follow_updated_ats = list(state_bundle["follow_state"]["updated_at_by_target"].values())
        return [
            {
                "id": "first_branch",
                "title": "第一次偏离",
                "icon": "🜂",
                "color": "amber",
                "unlocked": bool(sum(continue_counts.values()) >= 1),
                "unlockedAt": sessions[0].get("updatedAt") if sessions else None,
            },
            {
                "id": "world_cartographer",
                "title": "世界测绘者",
                "icon": "🜁",
                "color": "cyan",
                "unlocked": unlocked_world_count >= 2,
                "unlockedAt": (sessions[0].get("updatedAt") if sessions else None) or (author_items[0].get("updatedAt") if author_items else None),
            },
            {
                "id": "archive_curator",
                "title": "书馆策展人",
                "icon": "✦",
                "color": "violet",
                "unlocked": len(state_bundle["favorite_state"]["active_work_ids"]) >= 1,
                "unlockedAt": max(favorite_updated_ats) if favorite_updated_ats else None,
            },
            {
                "id": "co_creator",
                "title": "共创者",
                "icon": "✎",
                "color": "emerald",
                "unlocked": bool(state_bundle["follow_state"]["updated_at_by_target"]),
                "unlockedAt": max(follow_updated_ats) if follow_updated_ats else None,
            },
        ]

    def _recent_activity_count(self, *, account_id: str) -> int:
        window_start = datetime.now(timezone.utc).timestamp() - (24 * 60 * 60)
        events = self.repository.list_analytics_events(
            event_names=[
                "session_created",
                "continue_story",
                "author_draft_created_from_brief",
                "author_draft_saved",
                "author_draft_updated",
                "author_draft_validated",
                "author_draft_simulated",
                "author_draft_submitted",
                "author_longform_workbench_bootstrapped",
                "library_work_favorited",
                "library_work_unfavorited",
                "library_target_followed",
                "library_target_unfollowed",
                "story_bookmark_created",
                "story_bookmark_deleted",
                "showcase_work_liked",
                "showcase_work_commented",
                "showcase_tip_sent",
            ],
            reader_id=account_id,
            limit=1000,
        )
        count = 0
        for event in events:
            if _parse_timestamp(event.get("occurred_at")).timestamp() >= window_start:
                count += 1
        return count

    def _soul_dimensions(self, *, account_id: str) -> List[Dict[str, Any]]:
        state_bundle = self._canonical_library_state_bundle(account_id=account_id)
        favorite_state = state_bundle["favorite_state"]
        follow_state = state_bundle["follow_state"]
        bookmark_state = state_bundle["bookmark_state"]
        sessions = self._reader_session_items(
            account_id=account_id,
            favorite_ids_override=set(favorite_state["reader_session_ids"]),
            followed_world_ids_override=set(follow_state["world_ids"]),
            bookmark_summary_override=bookmark_state,
            current_node_resolver=self._story_session_current_node_id,
        )
        author_items = self._author_work_items(
            account_id=account_id,
            favorite_ids_override=set(favorite_state["author_work_ids"]),
            followed_world_ids_override=set(follow_state["world_ids"]),
        )
        likes = len(self.repository.list_showcase_work_likes(account_id=account_id))
        comments = len([item for item in self.repository.list_showcase_work_comments(limit=200) if str(item.get("account_id") or "") == account_id])
        tips = self.repository.list_showcase_work_tips(account_id=account_id)
        continue_total = sum(self._reader_continue_counts_by_session(account_id=account_id).values())
        unique_worlds = len({str(item.get("_world_id") or "") for item in sessions + author_items if str(item.get("_world_id") or "").strip()})
        tip_total = sum(int(item.get("amount") or 0) for item in tips)
        favorites = len(favorite_state["active_work_ids"])
        dims = [
            _clamp_percent((continue_total * 14) + (len(author_items) * 10)),
            _clamp_percent((comments * 18) + (likes * 8) + (len(tips) * 12)),
            _clamp_percent((continue_total * 10) + (unique_worlds * 12)),
            _clamp_percent((tip_total / 2) + (favorites * 8) + (20 if self.billing and str((self.billing.subscription_status(account_id=account_id) or {}).get("effective_tier") or "free") != "free" else 0)),
            _clamp_percent((sum(int(item.get("deviation") or 0) for item in sessions + author_items) / max(1, len(sessions) + len(author_items))) + (favorites * 6)),
        ]
        return [
            {"label": label, "value": value, "max": 100}
            for label, value in zip(SOUL_DIMENSION_LABELS, dims)
        ]

    def _public_activity_feed(self, *, account_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        items = self._all_library_items(account_id=account_id)
        public_items: List[Dict[str, Any]] = []
        for item in items[:limit]:
            public_items.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "coverImage": item.get("coverImage") or "",
                    "branchName": "公开活动" if item.get("kind") == "reader_session" else "公开创作",
                    "progress": item.get("progress") or 0,
                    "kind": item.get("kind"),
                    "targetHref": item.get("targetHref"),
                    "updatedAt": item.get("updatedAt"),
                }
            )
        return public_items

    def soul_profile(
        self,
        *,
        user_id: str,
        viewer_account_id: Optional[str] = None,
        viewer_actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        identity = self._resolve_identity_by_user_id(user_id)
        if identity is None:
            return {
                "userId": "guest",
                "displayName": "guest",
                "avatar": "",
                "readingMileage": 0,
                "ifBranchTriggered": 0,
                "todayFocus": 0,
                "level": 1,
                "dimensions": [{"label": label, "value": 0, "max": 100} for label in SOUL_DIMENSION_LABELS],
                "preferences": {"genres": [], "styles": [], "privacyMode": "followers"},
                "recentSessions": [],
                "viewerIsOwner": False,
                "viewerHasFollowedAuthor": False,
            }
        actor_id = str(identity.get("actor_id") or "").strip()
        account_id = str(identity.get("account_id") or actor_id).strip()
        preferences = self.get_soul_preferences(actor_id=actor_id, account_id=account_id)
        viewer_is_owner = bool(
            (viewer_actor_id and viewer_actor_id == actor_id)
            or (viewer_account_id and viewer_account_id == account_id)
        )
        authorized_follower = False
        if not viewer_is_owner and viewer_account_id:
            viewer_follow_state = self._library_follow_state(account_id=viewer_account_id)
            authorized_follower = actor_id in viewer_follow_state["author_ids"]
        privacy_mode = str(preferences.get("privacy_mode") or "followers")
        can_view_full = viewer_is_owner or authorized_follower or privacy_mode == "public"
        state_bundle = self._canonical_library_state_bundle(account_id=account_id)
        favorite_state = state_bundle["favorite_state"]
        follow_state = state_bundle["follow_state"]
        bookmark_state = state_bundle["bookmark_state"]
        sessions = self._reader_session_items(
            account_id=account_id,
            favorite_ids_override=set(favorite_state["reader_session_ids"]),
            followed_world_ids_override=set(follow_state["world_ids"]),
            bookmark_summary_override=bookmark_state,
            current_node_resolver=self._story_session_current_node_id,
        )
        author_items = self._author_work_items(
            account_id=account_id,
            favorite_ids_override=set(favorite_state["author_work_ids"]),
            followed_world_ids_override=set(follow_state["world_ids"]),
        )
        continue_total = sum(self._reader_continue_counts_by_session(account_id=account_id).values())
        reading_mileage = sum(max(1, int(item.get("progress") or 0) // 10) for item in sessions)
        recent_count = self._recent_activity_count(account_id=account_id)
        merged_recent = sorted(
            [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "coverImage": item.get("coverImage") or "",
                    "branchName": "阅读进度",
                    "progress": item.get("progress") or 0,
                    "kind": item.get("kind"),
                    "targetHref": item.get("targetHref"),
                    "updatedAt": item.get("updatedAt"),
                    "currentNodeId": item.get("currentNodeId"),
                    "viewerHasBookmarkedCurrentNode": item.get("viewerHasBookmarkedCurrentNode"),
                }
                for item in sessions
            ]
            + [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "coverImage": item.get("coverImage") or "",
                    "branchName": "创作草稿",
                    "progress": item.get("progress") or 0,
                    "kind": item.get("kind"),
                    "targetHref": item.get("targetHref"),
                    "updatedAt": item.get("updatedAt"),
                }
                for item in self._author_draft_activity_items(account_id=account_id)
            ],
            key=lambda item: _parse_timestamp(item.get("updatedAt")),
            reverse=True,
        )[:6]
        recent_sessions = merged_recent if can_view_full else self._public_activity_feed(account_id=account_id, limit=3)
        return {
            "userId": account_id,
            "displayName": str(identity.get("display_name") or actor_id or account_id),
            "avatar": "",
            "readingMileage": reading_mileage,
            "ifBranchTriggered": continue_total,
            "todayFocus": min(100, 20 * recent_count),
            "level": max(1, 1 + ((reading_mileage + len(author_items) + recent_count) // 5)),
            "dimensions": self._soul_dimensions(account_id=account_id),
            "preferences": {
                "genres": list(preferences.get("genres") or []) if can_view_full else [],
                "styles": list(preferences.get("styles") or []) if can_view_full else [],
                "privacyMode": privacy_mode,
            },
            "recentSessions": recent_sessions,
            "viewerIsOwner": viewer_is_owner,
            "viewerHasFollowedAuthor": authorized_follower,
        }

    def showcase_viewer_key(self, *, viewer_account_id: Optional[str], request_headers: Optional[Dict[str, Any]] = None, remote_host: Optional[str] = None) -> str:
        if viewer_account_id:
            return f"account::{viewer_account_id}"
        headers = request_headers or {}
        agent = str(headers.get("user-agent") or headers.get("User-Agent") or "guest").strip() or "guest"
        host = str(remote_host or "local").strip() or "local"
        return f"guest::{host}::{agent[:80]}"

    def showcase_interaction_maps(
        self,
        *,
        world_ids: List[str],
        viewer_account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        like_counts = self.repository.showcase_work_like_counts(world_ids=world_ids)
        comment_counts = self.repository.showcase_work_comment_counts(world_ids=world_ids, status="published")
        tip_totals = self.repository.showcase_work_tip_totals(world_ids=world_ids)
        view_counts = self.repository.showcase_work_view_counts(world_ids=world_ids, event_type="view")
        impression_counts = self.repository.showcase_work_view_counts(world_ids=world_ids, event_type="impression")
        liked_world_ids = set()
        if viewer_account_id:
            liked_world_ids = {
                str(item.get("world_id") or "")
                for item in self.repository.list_showcase_work_likes(world_ids=world_ids, account_id=viewer_account_id)
                if str(item.get("world_id") or "").strip()
            }
        return {
            "like_counts": like_counts,
            "comment_counts": comment_counts,
            "tip_totals": tip_totals,
            "view_counts": view_counts,
            "impression_counts": impression_counts,
            "liked_world_ids": liked_world_ids,
        }

    def _showcase_latest_published_versions(self) -> List[Dict[str, Any]]:
        latest_by_world: Dict[str, Dict[str, Any]] = {}
        for item in self.repository.list_world_versions(status="published"):
            world_id = str(item.get("world_id") or "").strip()
            if not world_id or world_id in latest_by_world:
                continue
            try:
                version = self.repository.get_world_version(str(item.get("world_version_id") or ""))
            except KeyError:
                continue
            metadata = dict(dict(version.worldpack_json or {}).get("metadata") or {})
            if not _is_public_catalog_visible(metadata):
                continue
            latest_by_world[world_id] = dict(item)
        return list(latest_by_world.values())

    def track_showcase_view(
        self,
        *,
        world_id: str,
        world_version_id: str,
        viewer_key: str,
        account_id: Optional[str],
        event_type: str,
    ) -> Dict[str, Any]:
        return self.repository.save_showcase_work_view(
            {
                "world_id": world_id,
                "world_version_id": world_version_id,
                "viewer_key": viewer_key,
                "account_id": account_id,
                "event_type": event_type,
            }
        )

    def showcase_item_from_version(
        self,
        *,
        version_summary: Dict[str, Any],
        hot_rank: Optional[int],
        interaction_maps: Dict[str, Any],
        viewer_account_id: Optional[str],
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(str(version_summary["world_version_id"]))
        worldpack = dict(version.worldpack_json or {})
        world_bible = dict(worldpack.get("world_bible") or {})
        metadata = dict(worldpack.get("metadata") or {})
        manifest = dict(version.manifest_json or {})
        world_id = str(version.world_id or "")
        review_records = self.repository.list_review_records(asset_id=version.world_version_id)
        latest_review = review_records[0] if review_records else {}
        moderation_status = "published_live" if str(version.status or "") == "published" else str(version.status or "draft")
        moderation_label = (
            "已发布"
            if moderation_status == "published_live"
            else str(latest_review.get("status") or moderation_status)
        )
        author_user_id = str(manifest.get("author_id") or version.author_id or "").strip()
        return {
            "id": version.world_version_id,
            "title": str(worldpack.get("title") or version.world_id),
            "coverImage": self._world_cover_url(world_version_id=version.world_version_id),
            "description": str(world_bible.get("premise") or ""),
            "visibility": "public",
            "authorName": str(author_user_id or "官方"),
            "authorAvatar": "",
            "authorUserId": author_user_id or None,
            "authorProfileHref": f"/soul/{quote(author_user_id, safe='')}" if author_user_id else None,
            "viewCount": int((interaction_maps.get("view_counts") or {}).get(world_id, 0)),
            "impressionCount": int((interaction_maps.get("impression_counts") or {}).get(world_id, 0)),
            "likeCount": int((interaction_maps.get("like_counts") or {}).get(world_id, 0)),
            "commentCount": int((interaction_maps.get("comment_counts") or {}).get(world_id, 0)),
            "tipAmount": int((interaction_maps.get("tip_totals") or {}).get(world_id, 0)),
            "createdAt": str(version_summary.get("updated_at") or ""),
            "isHotRanked": hot_rank is not None,
            "hotRank": hot_rank,
            "viewerHasLiked": world_id in set(interaction_maps.get("liked_world_ids") or set()) if viewer_account_id else False,
            "moderationStatus": moderation_status,
            "moderationLabel": moderation_label,
            "claimSafeBand": metadata.get("claim_safe_band"),
            "productReadyBand": metadata.get("product_ready_band"),
            "longform500ProductReady": bool(dict(metadata.get("longform_500_product_readiness") or {}).get("ready", False)),
        }

    def showcase_works(
        self,
        *,
        sort_value: str,
        page: int,
        page_size: int,
        viewer_account_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_sort = str(sort_value or "").strip()
        if normalized_sort not in VALID_SHOWCASE_SORTS:
            normalized_sort = "hot"
        published_versions = self._showcase_latest_published_versions()
        world_ids = [str(item.get("world_id") or "") for item in published_versions if str(item.get("world_id") or "").strip()]
        interaction_maps = self.showcase_interaction_maps(world_ids=world_ids, viewer_account_id=viewer_account_id)

        def hot_score(version_summary: Dict[str, Any]) -> float:
            world_id = str(version_summary.get("world_id") or "")
            created_at = _parse_timestamp(version_summary.get("updated_at"))
            freshness_days = max(1.0, (datetime.now(timezone.utc) - created_at).total_seconds() / (24 * 60 * 60))
            return (
                float((interaction_maps["like_counts"].get(world_id) or 0) * 5)
                + float((interaction_maps["comment_counts"].get(world_id) or 0) * 3)
                + float((interaction_maps["tip_totals"].get(world_id) or 0) * 0.1)
                + float((interaction_maps["view_counts"].get(world_id) or 0))
                + (6.0 / freshness_days)
            )

        if normalized_sort == "new":
            ordered = sorted(published_versions, key=lambda item: _parse_timestamp(item.get("updated_at")), reverse=True)
        elif normalized_sort == "ongoing":
            ordered = sorted(
                published_versions,
                key=lambda item: (
                    max(
                        int((interaction_maps["comment_counts"].get(str(item.get("world_id") or "")) or 0)),
                        int((interaction_maps["tip_totals"].get(str(item.get("world_id") or "")) or 0)),
                        int((interaction_maps["view_counts"].get(str(item.get("world_id") or "")) or 0)),
                    ),
                    _parse_timestamp(item.get("updated_at")),
                ),
                reverse=True,
            )
        else:
            ordered = sorted(published_versions, key=hot_score, reverse=True)

        items = [
            self.showcase_item_from_version(
                version_summary=item,
                hot_rank=index + 1 if normalized_sort == "hot" else None,
                interaction_maps=interaction_maps,
                viewer_account_id=viewer_account_id,
            )
            for index, item in enumerate(ordered)
        ]
        page_index = max(1, int(page or 1))
        per_page = max(1, min(100, int(page_size or 20)))
        start = (page_index - 1) * per_page
        end = start + per_page
        return items[start:end]
