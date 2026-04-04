from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from ..persistence.db import utcnow_iso
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .analytics import AnalyticsService
from .async_jobs import AsyncJobService


VALID_ANCHOR_TYPES = {
    "draft",
    "character",
    "scene",
    "capability",
    "simulation",
    "workflow",
}

VALID_THREAD_STATUSES = {"open", "resolved", "closed"}
VALID_APPROVAL_STATUSES = {"requested", "approved", "changes_requested", "revoked"}
VALID_NOTIFICATION_STATUSES = {"unread", "read", "archived"}
VALID_INBOX_STATUS_FILTERS = {"all", "unread", "active"}
VALID_NOTIFICATION_PREFERENCE_SINKS = {"default", "file", "email", "slack", "noop"}
THREAD_NOTIFICATION_PRIORITY = {"thread_assigned": 3, "thread_mentioned": 2, "thread_updated": 1}
THREAD_UPDATED_THROTTLE_WINDOW = timedelta(minutes=10)
ASYNC_AUTHOR_NOTIFICATION_EVENT_TYPES = {
    "thread_assigned": "author_notification_thread_assigned",
    "thread_mentioned": "author_notification_thread_mentioned",
    "approval_requested": "author_notification_approval_requested",
    "approval_decision": "author_notification_approval_decision",
}
AUTHOR_NOTIFICATION_PREFERENCE_DEFAULTS = {
    "thread_assigned": {"in_app_enabled": True, "async_mirror_enabled": True, "async_sink_name": "default", "delivery_target": None},
    "thread_mentioned": {"in_app_enabled": True, "async_mirror_enabled": True, "async_sink_name": "default", "delivery_target": None},
    "thread_updated": {"in_app_enabled": True, "async_mirror_enabled": False, "async_sink_name": "default", "delivery_target": None},
    "approval_requested": {"in_app_enabled": True, "async_mirror_enabled": True, "async_sink_name": "default", "delivery_target": None},
    "approval_decision": {"in_app_enabled": True, "async_mirror_enabled": True, "async_sink_name": "default", "delivery_target": None},
}
VALID_AUTHOR_NOTIFICATION_TYPES = set(AUTHOR_NOTIFICATION_PREFERENCE_DEFAULTS.keys())
MENTION_PATTERN = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_.:-]+)")
SEARCH_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.:-]+")


class AuthorCollaborationService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        analytics_service: Optional[AnalyticsService] = None,
        async_job_service: Optional[AsyncJobService] = None,
    ) -> None:
        self.repository = repository
        self.analytics = analytics_service or AnalyticsService(repository)
        self.async_job_service = async_job_service

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _build_notification_cursor(self, notification: Dict[str, Any]) -> Optional[str]:
        updated_at = str(notification.get("updated_at") or "").strip()
        notification_id = str(notification.get("notification_id") or "").strip()
        if not updated_at or not notification_id:
            return None
        return f"{updated_at}|{notification_id}"

    def _parse_notification_cursor(self, cursor: Optional[str]) -> Optional[Tuple[str, str]]:
        if not cursor or "|" not in str(cursor):
            return None
        updated_at, notification_id = str(cursor).split("|", 1)
        updated_at = updated_at.strip()
        notification_id = notification_id.strip()
        if not updated_at or not notification_id:
            return None
        return updated_at, notification_id

    def _extract_mentions(self, body: Optional[str]) -> List[str]:
        if not body:
            return []
        mentions: List[str] = []
        seen = set()
        for match in MENTION_PATTERN.findall(body):
            actor_id = str(match or "").strip()
            if actor_id and actor_id not in seen:
                mentions.append(actor_id)
                seen.add(actor_id)
        return mentions

    def _tokenize_search(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [token.lower() for token in SEARCH_TOKEN_PATTERN.findall(str(value)) if token]

    def _weighted_search_score(self, query: str, fields: List[Tuple[str, float]]) -> float:
        query_tokens = self._tokenize_search(query)
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return 0.0
        if not query_tokens:
            score = 0.0
            for field_value, weight in fields:
                lowered = str(field_value or "").lower()
                if normalized_query and normalized_query in lowered:
                    score += weight * 1.5
            return round(score, 3)
        score = 0.0
        for field_value, weight in fields:
            lowered = str(field_value or "").lower()
            field_tokens = set(self._tokenize_search(field_value))
            if not lowered:
                continue
            for token in query_tokens:
                if token in field_tokens:
                    score += weight * 2.0
                elif any(candidate.startswith(token) or token.startswith(candidate) for candidate in field_tokens):
                    score += weight * 1.25
                elif token in lowered:
                    score += weight * 0.75
        return round(score, 3)

    def _message_payload(self, message: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **message,
            "mentioned_actor_ids": self._extract_mentions(message.get("body")),
        }

    def _thread_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        return [self._message_payload(item) for item in self.repository.list_author_comment_messages(thread_id=thread_id)]

    def _thread_watchers(self, thread_id: str) -> List[Dict[str, Any]]:
        return self.repository.list_author_thread_watchers(thread_id=thread_id)

    def _thread_watcher_ids(self, thread_id: str) -> List[str]:
        return [str(item.get("watcher_id")) for item in self._thread_watchers(thread_id) if item.get("watcher_id")]

    def _draft_watchers(self, world_version_id: str, *, include_author: bool = True) -> List[Dict[str, Any]]:
        watchers = list(self.repository.list_author_draft_watchers(world_version_id=world_version_id))
        if include_author:
            author_id = self._draft_author_id(world_version_id)
            if author_id and not any(str(item.get("watcher_id")) == author_id for item in watchers):
                watchers = [
                    {
                        "watcher_record_id": f"implicit_author::{world_version_id}",
                        "world_version_id": world_version_id,
                        "watcher_id": author_id,
                        "added_by": author_id,
                        "created_at": None,
                        "implicit": True,
                    },
                    *watchers,
                ]
        return watchers

    def _draft_watcher_ids(self, world_version_id: str, *, include_author: bool = True) -> List[str]:
        seen = set()
        watcher_ids: List[str] = []
        for item in self._draft_watchers(world_version_id, include_author=include_author):
            watcher_id = str(item.get("watcher_id") or "").strip()
            if watcher_id and watcher_id not in seen:
                watcher_ids.append(watcher_id)
                seen.add(watcher_id)
        return watcher_ids

    def _notification_preferences(self, actor_id: str) -> Dict[str, Dict[str, Any]]:
        preferences = {
            notification_type: {
                "notification_type": notification_type,
                "in_app_enabled": defaults["in_app_enabled"],
                "async_mirror_enabled": defaults["async_mirror_enabled"],
                "async_sink_name": defaults.get("async_sink_name"),
                "delivery_target": defaults.get("delivery_target"),
                "is_default": True,
            }
            for notification_type, defaults in AUTHOR_NOTIFICATION_PREFERENCE_DEFAULTS.items()
        }
        for record in self.repository.list_author_notification_preferences(actor_id=actor_id):
            preferences[record["notification_type"]] = {
                "notification_type": record["notification_type"],
                "in_app_enabled": bool(record.get("in_app_enabled")),
                "async_mirror_enabled": bool(record.get("async_mirror_enabled")),
                "async_sink_name": record.get("async_sink_name") or "default",
                "delivery_target": record.get("delivery_target"),
                "is_default": False,
                "preference_id": record.get("preference_id"),
                "updated_at": record.get("updated_at"),
            }
        return preferences

    def notification_preferences(self, actor_id: str) -> Dict[str, Any]:
        resolved_actor_id = str(actor_id or "").strip()
        if not resolved_actor_id:
            raise ValueError("actor_id_required")
        preferences = self._notification_preferences(resolved_actor_id)
        return {
            "actor_id": resolved_actor_id,
            "preferences": [preferences[key] for key in sorted(preferences.keys())],
        }

    def update_notification_preference(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = self._actor_required(payload)
        notification_type = str(payload.get("notification_type") or "").strip()
        async_sink_name = str(payload.get("async_sink_name") or "default").strip() or "default"
        if notification_type not in VALID_AUTHOR_NOTIFICATION_TYPES:
            raise ValueError("invalid_notification_type")
        if async_sink_name not in VALID_NOTIFICATION_PREFERENCE_SINKS:
            raise ValueError("invalid_async_sink_name")
        preference = self.repository.save_author_notification_preference(
            {
                "actor_id": actor_id,
                "notification_type": notification_type,
                "in_app_enabled": bool(payload.get("in_app_enabled", True)),
                "async_mirror_enabled": bool(payload.get("async_mirror_enabled", True)),
                "async_sink_name": async_sink_name,
                "delivery_target": str(payload.get("delivery_target") or "").strip() or None,
            }
        )
        return {
            "preference": preference,
            "preferences": self.notification_preferences(actor_id),
        }

    def _thread_notifications(self, *, thread_id: str) -> List[Dict[str, Any]]:
        return self.repository.list_author_notifications(thread_id=thread_id, limit=100)

    def _thread_participants(self, thread: Dict[str, Any], messages: List[Dict[str, Any]]) -> List[str]:
        participants: List[str] = []
        seen = set()
        for actor_id in [thread.get("created_by"), thread.get("assignee_id")]:
            target = str(actor_id or "").strip()
            if target and target not in seen:
                participants.append(target)
                seen.add(target)
        for message in messages:
            actor_id = str(message.get("actor_id") or "").strip()
            if actor_id and actor_id not in seen:
                participants.append(actor_id)
                seen.add(actor_id)
            for mentioned in message.get("mentioned_actor_ids", []):
                target = str(mentioned or "").strip()
                if target and target not in seen:
                    participants.append(target)
                    seen.add(target)
        for watcher_id in self._thread_watcher_ids(thread["thread_id"]):
            if watcher_id and watcher_id not in seen:
                participants.append(watcher_id)
                seen.add(watcher_id)
        return participants

    def _thread_payload(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        messages = self._thread_messages(thread["thread_id"])
        latest_message = messages[-1] if messages else None
        notifications = self._thread_notifications(thread_id=thread["thread_id"])
        unread_notifications = [item for item in notifications if item.get("status") == "unread"]
        watchers = self._thread_watchers(thread["thread_id"])
        watcher_ids = [str(item.get("watcher_id")) for item in watchers if item.get("watcher_id")]
        return {
            **thread,
            "messages": messages,
            "message_count": len(messages),
            "watchers": watchers,
            "watcher_ids": watcher_ids,
            "watch_count": len(watchers),
            "participant_ids": self._thread_participants(thread, messages),
            "mentioned_actor_ids": sorted(
                {
                    actor_id
                    for message in messages
                    for actor_id in message.get("mentioned_actor_ids", [])
                    if actor_id
                }
            ),
            "latest_message_preview": (latest_message or {}).get("body", "")[:180] if latest_message else "",
            "latest_message_at": (latest_message or {}).get("created_at"),
            "latest_message_actor_id": (latest_message or {}).get("actor_id"),
            "notification_count": len(notifications),
            "unread_notification_count": len(unread_notifications),
            "notifications": notifications[:12],
        }

    def _draft_author_id(self, world_version_id: str) -> str:
        return str(self.repository.get_world_version(world_version_id).author_id)

    def _approval_summary(self, *, world_version_id: str) -> Dict[str, Any]:
        records = self.repository.list_author_approval_records(world_version_id=world_version_id)
        latest = records[0] if records else None
        return {
            "available": bool(records),
            "latest_status": latest.get("status") if latest else None,
            "latest_record": latest,
            "history": records,
        }

    def _notification_summary(self, *, world_version_id: str) -> Dict[str, Any]:
        notifications = self.repository.list_author_notifications(world_version_id=world_version_id, limit=100)
        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_recipient: Dict[str, int] = {}
        for notification in notifications:
            notification_type = str(notification.get("notification_type") or "unknown")
            status = str(notification.get("status") or "unknown")
            recipient_id = str(notification.get("recipient_id") or "unknown")
            by_type[notification_type] = by_type.get(notification_type, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            by_recipient[recipient_id] = by_recipient.get(recipient_id, 0) + 1
        return {
            "notification_count": len(notifications),
            "unread_count": by_status.get("unread", 0),
            "by_type": by_type,
            "by_status": by_status,
            "by_recipient": by_recipient,
            "latest_notifications": notifications[:8],
        }

    def _draft_watcher_summary(self, *, world_version_id: str) -> Dict[str, Any]:
        watchers = self._draft_watchers(world_version_id)
        explicit_watchers = [item for item in watchers if not item.get("implicit")]
        return {
            "watcher_count": len(watchers),
            "explicit_watcher_count": len(explicit_watchers),
            "watcher_ids": [str(item.get("watcher_id")) for item in watchers if item.get("watcher_id")],
            "watchers": watchers,
        }

    def _threads_by_anchor(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for thread in threads:
            grouped.setdefault((thread["anchor_type"], thread["anchor_key"]), []).append(thread)
        anchors = []
        for (anchor_type, anchor_key), items in grouped.items():
            anchors.append(
                {
                    "anchor_type": anchor_type,
                    "anchor_key": anchor_key,
                    "thread_count": len(items),
                    "open_count": sum(1 for item in items if item.get("status") == "open"),
                    "blocking_count": sum(
                        1
                        for item in items
                        if item.get("status") == "open" and item.get("severity") in {"blocker", "high"}
                    ),
                    "threads": items,
                }
            )
        anchors.sort(key=lambda item: (-item["blocking_count"], -item["open_count"], item["anchor_type"], item["anchor_key"]))
        return anchors

    def _assignee_queues(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for thread in threads:
            assignee_id = str(thread.get("assignee_id") or "unassigned")
            grouped.setdefault(assignee_id, []).append(thread)
        queues = []
        for assignee_id, items in grouped.items():
            queues.append(
                {
                    "assignee_id": assignee_id,
                    "open_count": sum(1 for item in items if item.get("status") == "open"),
                    "blocking_count": sum(
                        1
                        for item in items
                        if item.get("status") == "open" and item.get("severity") in {"blocker", "high"}
                    ),
                    "thread_count": len(items),
                    "threads": items,
                }
            )
        queues.sort(key=lambda item: (-item["blocking_count"], -item["open_count"], item["assignee_id"]))
        return queues

    def _status_queues(self, threads: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for thread in threads:
            status = str(thread.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def collaboration_summary(self, *, world_version_id: str) -> Dict[str, Any]:
        threads = [self._thread_payload(item) for item in self.repository.list_author_comment_threads(world_version_id=world_version_id)]
        approval = self._approval_summary(world_version_id=world_version_id)
        notifications = self._notification_summary(world_version_id=world_version_id)
        draft_watchers = self._draft_watcher_summary(world_version_id=world_version_id)
        open_thread_count = sum(1 for item in threads if item.get("status") == "open")
        blocking_thread_count = sum(
            1
            for item in threads
            if item.get("status") == "open" and item.get("severity") in {"blocker", "high"}
        )
        latest_approval_status = approval.get("latest_status")
        if blocking_thread_count:
            recommended_next_action = "resolve_blocking_threads"
        elif latest_approval_status == "requested":
            recommended_next_action = "await_internal_approval"
        elif latest_approval_status == "changes_requested":
            recommended_next_action = "address_requested_changes"
        elif latest_approval_status == "approved":
            recommended_next_action = "ready_for_submit"
        elif open_thread_count:
            recommended_next_action = "review_open_threads"
        else:
            recommended_next_action = "request_internal_approval"
        return {
            "world_version_id": world_version_id,
            "open_thread_count": open_thread_count,
            "blocking_thread_count": blocking_thread_count,
            "latest_approval_state": latest_approval_status,
            "recommended_next_action": recommended_next_action,
            "queue_summary": {
                "open_thread_count": open_thread_count,
                "blocking_thread_count": blocking_thread_count,
                "requested_approval_count": 1 if latest_approval_status == "requested" else 0,
                "changes_requested_count": 1 if latest_approval_status == "changes_requested" else 0,
                "approved_count": 1 if latest_approval_status == "approved" else 0,
                "unread_notification_count": notifications.get("unread_count", 0),
                "status_counts": self._status_queues(threads),
            },
            "assignee_queues": self._assignee_queues(threads),
            "threads": threads,
            "threads_by_anchor": self._threads_by_anchor(threads),
            "approval_summary": approval,
            "notification_summary": notifications,
            "draft_watcher_summary": draft_watchers,
        }

    def _actor_required(self, payload: Dict[str, Any], key: str = "actor_id") -> str:
        actor_id = str(payload.get(key) or "").strip()
        if not actor_id:
            raise PermissionError("actor_required")
        return actor_id

    def _ensure_draft_author(self, *, world_version_id: str, actor_id: str, action: str) -> None:
        if actor_id != self._draft_author_id(world_version_id):
            raise PermissionError(f"{action}_requires_draft_author")

    def _ensure_thread_status_allowed(self, thread: Dict[str, Any], *, actor_id: str) -> None:
        draft_author_id = self._draft_author_id(thread["world_version_id"])
        assignee_id = str(thread.get("assignee_id") or "").strip()
        if actor_id not in {draft_author_id, assignee_id}:
            raise PermissionError("thread_status_forbidden")

    def _ensure_thread_reply_allowed(self, thread: Dict[str, Any], *, actor_id: str) -> None:
        allowed = set(self._thread_watcher_ids(thread["thread_id"]))
        assignee_id = str(thread.get("assignee_id") or "").strip()
        if assignee_id:
            allowed.add(assignee_id)
        if actor_id not in allowed:
            raise PermissionError("thread_reply_forbidden")

    def _ensure_watch_change_allowed(
        self,
        thread: Dict[str, Any],
        *,
        actor_id: str,
        watcher_id: str,
    ) -> None:
        if actor_id == watcher_id:
            return
        if actor_id == self._draft_author_id(thread["world_version_id"]):
            return
        raise PermissionError("thread_watch_forbidden")

    def _ensure_draft_watch_change_allowed(self, *, world_version_id: str, actor_id: str, watcher_id: str) -> None:
        if actor_id == watcher_id:
            return
        if actor_id == self._draft_author_id(world_version_id):
            return
        raise PermissionError("draft_watch_forbidden")

    def _ensure_notification_recipient(self, notification: Dict[str, Any], *, recipient_id: str) -> None:
        if str(notification.get("recipient_id") or "") != recipient_id:
            raise PermissionError("notification_recipient_mismatch")

    def _latest_requested_approval(self, world_version_id: str) -> Optional[Dict[str, Any]]:
        requested = self.repository.list_author_approval_records(world_version_id=world_version_id, status="requested")
        return requested[0] if requested else None

    def _ensure_named_reviewer_can_decide(self, *, world_version_id: str, reviewer_id: str) -> None:
        latest_requested = self._latest_requested_approval(world_version_id)
        if latest_requested is None:
            raise PermissionError("approval_request_not_pending")
        if str(latest_requested.get("reviewer_id") or "") != reviewer_id:
            raise PermissionError("approval_decision_forbidden")

    def _ensure_thread_watchers(self, *, thread_id: str, watcher_ids: List[str], added_by: str) -> List[Dict[str, Any]]:
        saved: List[Dict[str, Any]] = []
        seen = set()
        for watcher_id in watcher_ids:
            target = str(watcher_id or "").strip()
            if not target or target in seen:
                continue
            seen.add(target)
            saved.append(
                self.repository.save_author_thread_watcher(
                    {
                        "thread_id": thread_id,
                        "watcher_id": target,
                        "added_by": added_by,
                    }
                )
            )
        return saved

    def _ensure_draft_watchers(self, *, world_version_id: str, watcher_ids: List[str], added_by: str) -> List[Dict[str, Any]]:
        saved: List[Dict[str, Any]] = []
        seen = set()
        author_id = self._draft_author_id(world_version_id)
        for watcher_id in watcher_ids:
            target = str(watcher_id or "").strip()
            if not target or target in seen or target == author_id:
                continue
            seen.add(target)
            saved.append(
                self.repository.save_author_draft_watcher(
                    {
                        "world_version_id": world_version_id,
                        "watcher_id": target,
                        "added_by": added_by,
                    }
                )
            )
        return saved

    def _async_event_type(self, notification_type: str) -> Optional[str]:
        return ASYNC_AUTHOR_NOTIFICATION_EVENT_TYPES.get(notification_type)

    def _notification_preference(self, actor_id: str, notification_type: str) -> Dict[str, Any]:
        return dict(self._notification_preferences(actor_id).get(notification_type) or {})

    def _throttle_existing_notification(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if payload.get("notification_type") != "thread_updated":
            return None
        thread_id = str(payload.get("thread_id") or "").strip()
        recipient_id = str(payload.get("recipient_id") or "").strip()
        if not thread_id or not recipient_id:
            return None
        existing_items = self.repository.list_author_notifications(
            recipient_id=recipient_id,
            thread_id=thread_id,
            notification_type="thread_updated",
            limit=25,
        )
        for existing in existing_items:
            if existing.get("status") == "archived":
                continue
            age = datetime.now(timezone.utc) - self._parse_timestamp(existing.get("updated_at"))
            if age > THREAD_UPDATED_THROTTLE_WINDOW:
                continue
            metadata = dict(existing.get("metadata_json") or {})
            throttle = dict(metadata.get("throttle") or {})
            throttle["collapsed_count"] = int(throttle.get("collapsed_count") or 0) + 1
            throttle["first_created_at"] = throttle.get("first_created_at") or existing.get("created_at")
            throttle["last_actor_id"] = payload.get("actor_id")
            throttle["last_body_excerpt"] = str(payload.get("body") or "")[:180]
            metadata["throttle"] = throttle
            updated = self.repository.save_author_notification(
                {
                    **existing,
                    "body": payload.get("body") or existing.get("body") or "",
                    "title": payload.get("title") or existing.get("title") or "",
                    "metadata_json": metadata,
                }
            )
            self.analytics.track(
                "author_notification_throttled",
                account_id=recipient_id,
                world_version_id=updated.get("world_version_id"),
                payload_json={
                    "notification_id": updated.get("notification_id"),
                    "thread_id": thread_id,
                    "collapsed_count": throttle["collapsed_count"],
                },
            )
            return updated
        return None

    def _dispatch_async_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        if self.async_job_service is None:
            return notification
        event_type = self._async_event_type(str(notification.get("notification_type") or ""))
        if event_type is None:
            return notification
        metadata = dict(notification.get("metadata_json") or {})
        preference = self._notification_preference(str(notification.get("recipient_id") or ""), str(notification.get("notification_type") or ""))
        sink_name = preference.get("async_sink_name")
        resolved_sink_name = None if sink_name in {None, "", "default"} else str(sink_name)
        delivery_target = preference.get("delivery_target")
        try:
            receipt = self.async_job_service.dispatch_author_notification(
                event_type=event_type,
                payload={
                    "notification": notification,
                    "world_version_id": notification.get("world_version_id"),
                    "recipient_id": notification.get("recipient_id"),
                    "delivery_target": delivery_target,
                },
                requested_by=notification.get("actor_id") or notification.get("recipient_id"),
                sink_name=resolved_sink_name,
            )
            metadata["async_delivery"] = {
                "status": str(receipt.get("status") or "sent"),
                "event_type": event_type,
                "sink_name": receipt.get("sink_name"),
                "event_id": receipt.get("event_id"),
                "target_path": receipt.get("target_path"),
                "delivery_target": delivery_target,
            }
        except Exception as exc:
            metadata["async_delivery"] = {
                "status": "failed",
                "event_type": event_type,
                "sink_name": None,
                "event_id": None,
                "target_path": None,
                "error": str(exc),
            }
            self.analytics.track(
                "author_notification_async_delivery_failed",
                account_id=notification.get("recipient_id"),
                world_version_id=notification.get("world_version_id"),
                payload_json={
                    "notification_id": notification.get("notification_id"),
                    "event_type": event_type,
                    "error": str(exc),
                },
            )
        return self.repository.save_author_notification(
            {
                **notification,
                "metadata_json": metadata,
            }
        )

    def _save_notification(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        recipient_id = str(payload.get("recipient_id") or "").strip()
        notification_type = str(payload.get("notification_type") or "").strip()
        if not recipient_id or notification_type not in VALID_AUTHOR_NOTIFICATION_TYPES:
            return None
        preference = self._notification_preference(recipient_id, notification_type)
        if not preference.get("in_app_enabled", True):
            return None
        throttled = self._throttle_existing_notification(payload)
        if throttled is not None:
            return throttled
        record = self.repository.save_author_notification(payload)
        self.analytics.track(
            "author_notification_created",
            account_id=payload.get("actor_id"),
            world_version_id=payload["world_version_id"],
            payload_json={
                "notification_id": record["notification_id"],
                "recipient_id": record["recipient_id"],
                "recipient_role": record["recipient_role"],
                "notification_type": record["notification_type"],
                "thread_id": record.get("thread_id"),
                "approval_id": record.get("approval_id"),
            },
        )
        if preference.get("async_mirror_enabled", True):
            return self._dispatch_async_notification(record)
        return record

    def _deliver_thread_notifications(
        self,
        *,
        thread: Dict[str, Any],
        actor_id: str,
        actor_role: str,
        body: Optional[str],
    ) -> List[Dict[str, Any]]:
        mentioned_actor_ids = self._extract_mentions(body)
        watcher_ids = self._thread_watcher_ids(thread["thread_id"])
        draft_watcher_ids = self._draft_watcher_ids(thread["world_version_id"])
        excerpt = (body or "").strip()[:180] or f"{thread.get('anchor_type')}:{thread.get('anchor_key')}"
        recipients: Dict[str, Dict[str, Any]] = {}

        def register(recipient_id: Optional[str], *, recipient_role: str, notification_type: str, title: str) -> None:
            target = str(recipient_id or "").strip()
            if not target or target == actor_id:
                return
            existing = recipients.get(target)
            if existing and THREAD_NOTIFICATION_PRIORITY[existing["notification_type"]] >= THREAD_NOTIFICATION_PRIORITY[notification_type]:
                return
            recipients[target] = {
                "world_version_id": thread["world_version_id"],
                "thread_id": thread["thread_id"],
                "recipient_id": target,
                "recipient_role": recipient_role,
                "notification_type": notification_type,
                "status": "unread",
                "actor_id": actor_id,
                "actor_role": actor_role,
                "title": title,
                "body": excerpt,
                "anchor_type": thread.get("anchor_type"),
                "anchor_key": thread.get("anchor_key"),
                "metadata_json": {
                    "thread_status": thread.get("status"),
                    "thread_severity": thread.get("severity"),
                    "mentioned_actor_ids": mentioned_actor_ids,
                },
            }

        register(
            thread.get("assignee_id"),
            recipient_role="assignee",
            notification_type="thread_assigned",
            title=f"{thread.get('anchor_type')}:{thread.get('anchor_key')} 已分配给你",
        )
        for mentioned_actor_id in mentioned_actor_ids:
            register(
                mentioned_actor_id,
                recipient_role="mentioned",
                notification_type="thread_mentioned",
                title=f"{actor_id} 在协作线程中提到了你",
            )
        for watcher_id in watcher_ids:
            register(
                watcher_id,
                recipient_role="watcher",
                notification_type="thread_updated",
                title=f"{actor_id} 更新了协作线程",
            )
        for watcher_id in draft_watcher_ids:
            register(
                watcher_id,
                recipient_role="draft_watcher",
                notification_type="thread_updated",
                title=f"{actor_id} 更新了 Draft 协作流",
            )
        return [item for item in (self._save_notification(item) for item in recipients.values()) if item is not None]

    def _deliver_approval_notification(
        self,
        *,
        approval: Dict[str, Any],
        recipient_id: Optional[str],
        recipient_role: str,
        actor_id: Optional[str],
        actor_role: Optional[str],
        notification_type: str,
        title: str,
        body: str,
    ) -> Optional[Dict[str, Any]]:
        target = str(recipient_id or "").strip()
        if not target or target == str(actor_id or "").strip():
            return None
        return self._save_notification(
            {
                "world_version_id": approval["world_version_id"],
                "approval_id": approval["approval_id"],
                "recipient_id": target,
                "recipient_role": recipient_role,
                "notification_type": notification_type,
                "status": "unread",
                "actor_id": actor_id,
                "actor_role": actor_role,
                "title": title,
                "body": body[:180],
                "metadata_json": {
                    "approval_status": approval.get("status"),
                    "reviewer_id": approval.get("reviewer_id"),
                },
            }
        )

    def _thread_matches_query(self, thread: Dict[str, Any], query: str) -> bool:
        return self._thread_search_score(thread, query) > 0

    def _thread_search_score(self, thread: Dict[str, Any], query: str) -> float:
        return self._weighted_search_score(
            query,
            [
                (str(thread.get("anchor_type") or ""), 1.5),
                (str(thread.get("anchor_key") or ""), 1.5),
                (str(thread.get("latest_message_preview") or ""), 1.0),
                (str(thread.get("thread_id") or ""), 1.2),
                (str(thread.get("world_version_id") or ""), 1.3),
                (str(thread.get("assignee_id") or ""), 1.1),
            ],
        )

    def _approval_matches_query(self, approval: Dict[str, Any], query: str) -> bool:
        return self._approval_search_score(approval, query) > 0

    def _approval_search_score(self, approval: Dict[str, Any], query: str) -> float:
        return self._weighted_search_score(
            query,
            [
                (str(approval.get("reason") or ""), 1.7),
                (str(approval.get("reviewer_id") or ""), 1.5),
                (str(approval.get("world_version_id") or ""), 1.4),
                (str(approval.get("revision_id") or ""), 1.0),
                (str(approval.get("status") or ""), 0.8),
            ],
        )

    def _notification_matches_query(self, notification: Dict[str, Any], query: str) -> bool:
        return self._notification_search_score(notification, query) > 0

    def _notification_search_score(self, notification: Dict[str, Any], query: str) -> float:
        score = self._weighted_search_score(
            query,
            [
                (str(notification.get("title") or ""), 2.0),
                (str(notification.get("body") or ""), 1.8),
                (str(notification.get("actor_id") or ""), 1.4),
                (str(notification.get("recipient_id") or ""), 1.4),
                (str(notification.get("world_version_id") or ""), 1.3),
                (str(notification.get("notification_type") or ""), 1.0),
            ],
        )
        thread_id = str(notification.get("thread_id") or "").strip()
        if thread_id:
            try:
                score += self._thread_search_score(self._thread_payload(self.repository.get_author_comment_thread(thread_id)), query)
            except KeyError:
                pass
        approval_id = str(notification.get("approval_id") or "").strip()
        if approval_id:
            for approval in self.repository.list_author_approval_records(world_version_id=notification.get("world_version_id")):
                if str(approval.get("approval_id")) == approval_id:
                    score += self._approval_search_score(approval, query)
                    break
        return round(score, 3)

    def reviewer_inbox(
        self,
        *,
        reviewer_id: str,
        limit: int = 20,
        world_version_id: Optional[str] = None,
        status_filter: str = "all",
        notification_type: Optional[str] = None,
        blocking_only: bool = False,
        cursor: Optional[str] = None,
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status_filter not in VALID_INBOX_STATUS_FILTERS:
            raise ValueError("invalid_inbox_status_filter")
        if not str(reviewer_id or "").strip():
            raise ValueError("reviewer_id_required")
        cursor_payload = self._parse_notification_cursor(cursor)
        search_query = str(q or "").strip()
        assigned_threads_all = [
            self._thread_payload(item)
            for item in self.repository.list_author_comment_threads(
                assignee_id=reviewer_id,
                world_version_id=world_version_id,
                status="open",
            )
        ]
        blocking_assigned_threads_all = [item for item in assigned_threads_all if item.get("severity") in {"blocker", "high"}]
        pending_approvals_all = [
            item
            for item in self.repository.list_author_approval_records(
                world_version_id=world_version_id,
                status="requested",
            )
            if item.get("reviewer_id") == reviewer_id
        ]
        notifications: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = None
        has_more = False
        scanned = 0
        working_cursor = cursor_payload
        batch_size = max(limit * 4, 40)
        max_scan = max(limit * 12, 200)
        while len(notifications) < limit + 1 and scanned < max_scan:
            batch = self.repository.list_author_notifications(
                recipient_id=reviewer_id,
                world_version_id=world_version_id,
                notification_type=notification_type,
                cursor_updated_at=working_cursor[0] if working_cursor else None,
                cursor_notification_id=working_cursor[1] if working_cursor else None,
                limit=batch_size,
            )
            if not batch:
                break
            scanned += len(batch)
            working_cursor = self._parse_notification_cursor(self._build_notification_cursor(batch[-1]))
            for item in batch:
                if status_filter in {"unread", "active"} and item.get("status") != "unread":
                    continue
                if search_query and not self._notification_matches_query(item, search_query):
                    continue
                notifications.append(item)
                if len(notifications) >= limit + 1:
                    break
            if len(batch) < batch_size:
                break
        if len(notifications) > limit:
            has_more = True
            next_cursor = self._build_notification_cursor(notifications[limit - 1])
            notifications = notifications[:limit]
        unread_notifications = [item for item in notifications if item.get("status") == "unread"]

        if search_query:
            assigned_threads_all = [item for item in assigned_threads_all if self._thread_matches_query(item, search_query)]
            blocking_assigned_threads_all = [item for item in blocking_assigned_threads_all if self._thread_matches_query(item, search_query)]
            pending_approvals_all = [item for item in pending_approvals_all if self._approval_matches_query(item, search_query)]
            notifications = sorted(
                notifications,
                key=lambda item: (
                    -self._notification_search_score(item, search_query),
                    -self._parse_timestamp(item.get("updated_at")).timestamp(),
                ),
            )

        filtered_notifications = list(notifications)
        assigned_threads = list(assigned_threads_all)
        pending_approvals = list(pending_approvals_all)
        if status_filter == "unread":
            filtered_notifications = unread_notifications
        elif status_filter == "active":
            filtered_notifications = unread_notifications
            assigned_threads = blocking_assigned_threads_all

        mentioned_thread_ids = {
            str(item.get("thread_id"))
            for item in filtered_notifications
            if item.get("notification_type") == "thread_mentioned" and item.get("thread_id")
        }
        mentioned_threads = []
        for thread_id in mentioned_thread_ids:
            try:
                thread = self.repository.get_author_comment_thread(thread_id)
            except KeyError:
                continue
            if world_version_id and thread.get("world_version_id") != world_version_id:
                continue
            if thread.get("status") != "open":
                continue
            payload = self._thread_payload(thread)
            if search_query and not self._thread_matches_query(payload, search_query):
                continue
            mentioned_threads.append(payload)

        if blocking_only:
            blocking_thread_ids = {
                item["thread_id"]
                for item in (blocking_assigned_threads_all + mentioned_threads)
                if item.get("severity") in {"blocker", "high"}
            }
            filtered_notifications = [
                item
                for item in filtered_notifications
                if not item.get("thread_id") or str(item.get("thread_id")) in blocking_thread_ids
            ]
            assigned_threads = [item for item in assigned_threads if item.get("severity") in {"blocker", "high"}]
            mentioned_threads = [item for item in mentioned_threads if item.get("severity") in {"blocker", "high"}]

        if has_more and filtered_notifications:
            next_cursor = self._build_notification_cursor(filtered_notifications[-1])

        filtered_unread_notifications = [item for item in filtered_notifications if item.get("status") == "unread"]
        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_world_version: Dict[str, Dict[str, Any]] = {}
        for notification in filtered_notifications:
            notification_type_key = str(notification.get("notification_type") or "unknown")
            status_key = str(notification.get("status") or "unknown")
            world_version_key = str(notification.get("world_version_id") or "unknown")
            by_type[notification_type_key] = by_type.get(notification_type_key, 0) + 1
            by_status[status_key] = by_status.get(status_key, 0) + 1
            bucket = by_world_version.setdefault(
                world_version_key,
                {
                    "world_version_id": world_version_key,
                    "notification_count": 0,
                    "unread_count": 0,
                },
            )
            bucket["notification_count"] += 1
            if status_key == "unread":
                bucket["unread_count"] += 1

        blocking_assigned_threads = [item for item in assigned_threads if item.get("severity") in {"blocker", "high"}]
        if blocking_assigned_threads:
            recommended_next_action = "resolve_blocking_threads"
        elif pending_approvals:
            recommended_next_action = "review_requested_approval"
        elif filtered_unread_notifications:
            recommended_next_action = "clear_unread_notifications"
        elif assigned_threads:
            recommended_next_action = "review_assigned_threads"
        else:
            recommended_next_action = "inbox_clear"
        return {
            "reviewer_id": reviewer_id,
            "filters": {
                "world_version_id": world_version_id,
                "status_filter": status_filter,
                "notification_type": notification_type,
                "blocking_only": blocking_only,
                "cursor": cursor,
                "q": search_query or None,
            },
            "returned_count": len(filtered_notifications),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "recommended_next_action": recommended_next_action,
            "queue_summary": {
                "assigned_open_thread_count": len(assigned_threads),
                "blocking_assigned_thread_count": len(blocking_assigned_threads),
                "pending_approval_count": len(pending_approvals),
                "unread_notification_count": len(filtered_unread_notifications),
                "status_counts": by_status,
                "notification_type_counts": by_type,
            },
            "assigned_threads": assigned_threads[:limit],
            "blocking_assigned_threads": blocking_assigned_threads[:limit],
            "mentioned_threads": mentioned_threads[:limit],
            "pending_approvals": pending_approvals[:limit],
            "notifications": filtered_notifications[:limit],
            "unread_notifications": filtered_unread_notifications[:limit],
            "world_version_queues": sorted(
                by_world_version.values(),
                key=lambda item: (-item["unread_count"], -item["notification_count"], item["world_version_id"]),
            ),
        }

    def update_notification_status(self, notification_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.repository.get_author_notification(notification_id)
        status = str(payload.get("status") or existing.get("status"))
        recipient_id = str(payload.get("recipient_id") or "").strip()
        if status not in VALID_NOTIFICATION_STATUSES:
            raise ValueError("invalid_notification_status")
        if not recipient_id:
            raise PermissionError("notification_recipient_required")
        self._ensure_notification_recipient(existing, recipient_id=recipient_id)
        updated = self.repository.save_author_notification(
            {
                **existing,
                "status": status,
                "read_at": existing.get("read_at") if status == existing.get("status") else (None if status == "unread" else utcnow_iso()),
            }
        )
        self.analytics.track(
            "author_notification_status_updated",
            account_id=recipient_id,
            world_version_id=updated["world_version_id"],
            payload_json={
                "notification_id": updated["notification_id"],
                "status": updated["status"],
                "recipient_id": updated["recipient_id"],
            },
        )
        return {
            "notification": updated,
            "reviewer_inbox": self.reviewer_inbox(
                reviewer_id=recipient_id,
                limit=int(payload.get("limit") or 20),
            ),
        }

    def bulk_update_notification_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        recipient_id = str(payload.get("recipient_id") or "").strip()
        status = str(payload.get("status") or "")
        notification_ids = [str(item).strip() for item in payload.get("notification_ids", []) if str(item).strip()]
        if not recipient_id:
            raise PermissionError("notification_recipient_required")
        if status not in VALID_NOTIFICATION_STATUSES:
            raise ValueError("invalid_notification_status")
        if not notification_ids:
            raise ValueError("notification_ids_required")
        updated_notifications = []
        for notification_id in notification_ids:
            updated_notifications.append(
                self.update_notification_status(
                    notification_id,
                    {
                        "status": status,
                        "recipient_id": recipient_id,
                        "limit": payload.get("limit") or 20,
                    },
                )["notification"]
            )
        return {
            "updated_count": len(updated_notifications),
            "notifications": updated_notifications,
            "reviewer_inbox": self.reviewer_inbox(
                reviewer_id=recipient_id,
                limit=int(payload.get("limit") or 20),
            ),
        }

    def add_thread_watcher(self, thread_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        thread = self.repository.get_author_comment_thread(thread_id)
        actor_id = self._actor_required(payload)
        watcher_id = str(payload.get("watcher_id") or actor_id).strip()
        if not watcher_id:
            raise ValueError("watcher_id_required")
        self._ensure_watch_change_allowed(thread, actor_id=actor_id, watcher_id=watcher_id)
        watcher = self.repository.save_author_thread_watcher(
            {
                "thread_id": thread_id,
                "watcher_id": watcher_id,
                "added_by": actor_id,
            }
        )
        return {
            "watcher": watcher,
            "thread": self._thread_payload(thread),
            "collaboration_summary": self.collaboration_summary(world_version_id=thread["world_version_id"]),
        }

    def add_draft_watcher(self, world_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = self._actor_required(payload)
        watcher_id = str(payload.get("watcher_id") or actor_id).strip()
        if not watcher_id:
            raise ValueError("watcher_id_required")
        self._ensure_draft_watch_change_allowed(world_version_id=world_version_id, actor_id=actor_id, watcher_id=watcher_id)
        watcher = self.repository.save_author_draft_watcher(
            {
                "world_version_id": world_version_id,
                "watcher_id": watcher_id,
                "added_by": actor_id,
            }
        )
        return {
            "watcher": watcher,
            "draft_watcher_summary": self._draft_watcher_summary(world_version_id=world_version_id),
            "collaboration_summary": self.collaboration_summary(world_version_id=world_version_id),
        }

    def remove_thread_watcher(self, thread_id: str, watcher_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        thread = self.repository.get_author_comment_thread(thread_id)
        actor_id = self._actor_required(payload)
        target_watcher_id = str(watcher_id or "").strip()
        if not target_watcher_id:
            raise ValueError("watcher_id_required")
        self._ensure_watch_change_allowed(thread, actor_id=actor_id, watcher_id=target_watcher_id)
        removed = self.repository.delete_author_thread_watcher(thread_id=thread_id, watcher_id=target_watcher_id)
        return {
            "watcher": removed,
            "thread": self._thread_payload(thread),
            "collaboration_summary": self.collaboration_summary(world_version_id=thread["world_version_id"]),
        }

    def remove_draft_watcher(self, world_version_id: str, watcher_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = self._actor_required(payload)
        target_watcher_id = str(watcher_id or "").strip()
        if not target_watcher_id:
            raise ValueError("watcher_id_required")
        self._ensure_draft_watch_change_allowed(world_version_id=world_version_id, actor_id=actor_id, watcher_id=target_watcher_id)
        removed = self.repository.delete_author_draft_watcher(world_version_id=world_version_id, watcher_id=target_watcher_id)
        return {
            "watcher": removed,
            "draft_watcher_summary": self._draft_watcher_summary(world_version_id=world_version_id),
            "collaboration_summary": self.collaboration_summary(world_version_id=world_version_id),
        }

    def create_comment_thread(self, *, world_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = self._actor_required(payload)
        actor_role = str(payload.get("actor_role") or "author")
        self._ensure_draft_author(world_version_id=world_version_id, actor_id=actor_id, action="create_thread")
        anchor_type = str(payload.get("anchor_type") or "draft")
        if anchor_type not in VALID_ANCHOR_TYPES:
            raise ValueError("invalid_anchor_type")
        thread = self.repository.save_author_comment_thread(
            {
                "world_version_id": world_version_id,
                "revision_id": payload.get("revision_id"),
                "anchor_type": anchor_type,
                "anchor_key": str(payload.get("anchor_key") or world_version_id),
                "status": payload.get("status", "open"),
                "severity": payload.get("severity", "normal"),
                "assignee_id": payload.get("assignee_id"),
                "created_by": actor_id,
            }
        )
        message = self.repository.save_author_comment_message(
            {
                "thread_id": thread["thread_id"],
                "actor_id": actor_id,
                "actor_role": actor_role,
                "body": payload["body"],
            }
        )
        self._ensure_thread_watchers(
            thread_id=thread["thread_id"],
            watcher_ids=[actor_id, str(payload.get("assignee_id") or "").strip(), *self._extract_mentions(payload.get("body"))],
            added_by=actor_id,
        )
        notifications = self._deliver_thread_notifications(
            thread=thread,
            actor_id=actor_id,
            actor_role=actor_role,
            body=payload["body"],
        )
        self.analytics.track(
            "author_comment_thread_created",
            account_id=actor_id,
            world_version_id=world_version_id,
            payload_json={
                "thread_id": thread["thread_id"],
                "anchor_type": thread["anchor_type"],
                "anchor_key": thread["anchor_key"],
                "severity": thread["severity"],
                "mentioned_actor_ids": self._extract_mentions(payload.get("body")),
            },
        )
        return {
            "thread": self._thread_payload(thread),
            "message": message,
            "notifications": notifications,
            "collaboration_summary": self.collaboration_summary(world_version_id=world_version_id),
        }

    def reply_to_thread(self, thread_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        thread = self.repository.get_author_comment_thread(thread_id)
        actor_id = self._actor_required(payload)
        actor_role = str(payload.get("actor_role") or "author")
        self._ensure_thread_reply_allowed(thread, actor_id=actor_id)
        message = self.repository.save_author_comment_message(
            {
                "thread_id": thread_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "body": payload["body"],
            }
        )
        self._ensure_thread_watchers(
            thread_id=thread_id,
            watcher_ids=[actor_id, *self._extract_mentions(payload.get("body"))],
            added_by=actor_id,
        )
        notifications = self._deliver_thread_notifications(
            thread=thread,
            actor_id=actor_id,
            actor_role=actor_role,
            body=payload["body"],
        )
        return {
            "thread": self._thread_payload(thread),
            "message": message,
            "notifications": notifications,
            "collaboration_summary": self.collaboration_summary(world_version_id=thread["world_version_id"]),
        }

    def update_thread_status(self, thread_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.repository.get_author_comment_thread(thread_id)
        actor_id = self._actor_required(payload)
        actor_role = str(payload.get("actor_role") or "reviewer")
        self._ensure_thread_status_allowed(existing, actor_id=actor_id)
        status = str(payload.get("status") or existing.get("status"))
        if status not in VALID_THREAD_STATUSES:
            raise ValueError("invalid_thread_status")
        updated = self.repository.save_author_comment_thread(
            {
                **existing,
                "status": status,
                "severity": payload.get("severity", existing.get("severity")),
                "assignee_id": payload.get("assignee_id", existing.get("assignee_id")),
            }
        )
        mentioned_actor_ids = self._extract_mentions(payload.get("body"))
        self._ensure_thread_watchers(
            thread_id=thread_id,
            watcher_ids=[str(updated.get("assignee_id") or "").strip(), *mentioned_actor_ids],
            added_by=actor_id,
        )
        if payload.get("body"):
            self.repository.save_author_comment_message(
                {
                    "thread_id": thread_id,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "body": payload["body"],
                }
            )
        notifications = self._deliver_thread_notifications(
            thread=updated,
            actor_id=actor_id,
            actor_role=actor_role,
            body=payload.get("body"),
        )
        return {
            "thread": self._thread_payload(updated),
            "notifications": notifications,
            "collaboration_summary": self.collaboration_summary(world_version_id=updated["world_version_id"]),
        }

    def request_approval(self, *, world_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = str(payload.get("actor_id") or self._draft_author_id(world_version_id)).strip()
        self._ensure_draft_author(world_version_id=world_version_id, actor_id=actor_id, action="request_approval")
        self._ensure_draft_watchers(
            world_version_id=world_version_id,
            watcher_ids=[payload["reviewer_id"]],
            added_by=actor_id,
        )
        record = self.repository.save_author_approval_record(
            {
                "world_version_id": world_version_id,
                "revision_id": payload.get("revision_id"),
                "status": "requested",
                "reviewer_id": payload["reviewer_id"],
                "reason": payload["reason"],
            }
        )
        notification = self._deliver_approval_notification(
            approval=record,
            recipient_id=payload["reviewer_id"],
            recipient_role="reviewer",
            actor_id=actor_id,
            actor_role=payload.get("actor_role") or "author",
            notification_type="approval_requested",
            title=f"{world_version_id} 请求你审批",
            body=payload["reason"],
        )
        return {
            "approval": record,
            "notification": notification,
            "collaboration_summary": self.collaboration_summary(world_version_id=world_version_id),
        }

    def approval_decision(self, *, world_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str(payload.get("status") or "")
        reviewer_id = str(payload.get("reviewer_id") or "").strip()
        if status not in VALID_APPROVAL_STATUSES - {"requested"}:
            raise ValueError("invalid_approval_status")
        if not reviewer_id:
            raise PermissionError("reviewer_required")
        self._ensure_named_reviewer_can_decide(world_version_id=world_version_id, reviewer_id=reviewer_id)
        record = self.repository.save_author_approval_record(
            {
                "world_version_id": world_version_id,
                "revision_id": payload.get("revision_id"),
                "status": status,
                "reviewer_id": reviewer_id,
                "reason": payload["reason"],
            }
        )
        notification = self._deliver_approval_notification(
            approval=record,
            recipient_id=self._draft_author_id(world_version_id),
            recipient_role="author",
            actor_id=reviewer_id,
            actor_role="reviewer",
            notification_type="approval_decision",
            title=f"{world_version_id} 审批结果：{status}",
            body=payload["reason"],
        )
        return {
            "approval": record,
            "notification": notification,
            "collaboration_summary": self.collaboration_summary(world_version_id=world_version_id),
        }
