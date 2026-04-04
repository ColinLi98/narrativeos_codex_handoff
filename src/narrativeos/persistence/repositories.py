from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sqrt
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import desc, select

from ..models import (
    CandidateBatch,
    EvaluationReport,
    EventAtom,
    NarrativeState,
    NarrativeViewModel,
    RenderedScene,
    RouteCandidate,
    SceneBeat,
    SceneRenderSpec,
    ScoredCandidate,
    SessionRecord,
    StepRecord,
    WorldRecord,
)
from ..worldpacks.models import RuntimeBundle, WorldPack, WorldVersion
from ..worldpacks.registry import FileSystemWorldRegistry, runtime_bundle_from_worldpack_data
from .db import (
    AnalyticsEventRow,
    AuthIdentityRow,
    AuthTokenRow,
    BillingCheckoutSessionRow,
    BillingLifecycleEventRow,
    BillingRetryAttemptRow,
    AuthorApprovalRecordRow,
    AuthorCommentMessageRow,
    AuthorDraftWatcherRow,
    AuthorNotificationRow,
    AuthorNotificationPreferenceRow,
    AuthorCommentThreadRow,
    AuthorThreadWatcherRow,
    ChapterRow,
    EntitlementRow,
    ReviewRecordRow,
    RouteChoiceRow,
    SessionRow,
    SubscriptionRow,
    UsageMeterRow,
    WorldRow,
    WorldVersionRow,
    create_platform_session_local,
    utcnow_iso,
)


DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///narrativeos_beta.db")
CONTINUATION_STALE_WINDOW_HOURS = 24
CONTINUATION_TARGET_SAMPLES_PER_WORLD = 12
CONTINUATION_TARGET_SAMPLES_PER_VERSION = 8
CONTINUATION_TARGET_NEGATIVE_SAMPLES = 2


def _parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pearson_correlation(points: List[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / float(len(xs))
    mean_y = sum(ys) / float(len(ys))
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = sqrt(denom_x * denom_y)
    if denominator == 0.0:
        return 0.0
    return round(numerator / denominator, 3)


def _continuation_recommended_action(
    *,
    sample_count: int,
    positive_count: int,
    negative_count: int,
    target_sample_count: int,
) -> str:
    if sample_count == 0:
        return "collect_first_reader_sessions"
    if negative_count < CONTINUATION_TARGET_NEGATIVE_SAMPLES:
        return "collect_more_abandonment_or_stale_tail_samples"
    if positive_count == 0:
        return "collect_more_successful_continue_sessions"
    if sample_count < target_sample_count:
        return "collect_more_mixed_reader_sessions"
    return "coverage_sufficient"


class SQLAlchemyPlatformRepository:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        self.engine, self.SessionLocal = create_platform_session_local(database_url)
        self.registry = FileSystemWorldRegistry()
        self._bootstrap_builtin_worldpacks()

    def _bootstrap_builtin_worldpacks(self) -> None:
        for world_card in self.registry.list_worldpacks():
            worldpack = WorldPack.from_dict(world_card["worldpack"])
            world_version = WorldVersion.from_worldpack(
                worldpack=worldpack,
                world_version_id=world_card["world_version_id"],
                status="published",
            )
            self.save_world_version(world_version, publish=True)

    # World / world version
    def save_world_version(self, world_version: WorldVersion, *, publish: bool = False) -> WorldVersion:
        now = utcnow_iso()
        with self.SessionLocal() as session:
            world_row = session.get(WorldRow, world_version.world_id)
            if world_row is None:
                world_row = WorldRow(
                    world_id=world_version.world_id,
                    latest_version=world_version.world_version_id if publish else None,
                    title=world_version.worldpack_json.get("title", world_version.world_id),
                    status="published" if publish else world_version.status,
                    created_at=now,
                    updated_at=now,
                )
                session.add(world_row)
            else:
                world_row.title = world_version.worldpack_json.get("title", world_version.world_id)
                world_row.status = "published" if publish else world_row.status
                if publish:
                    world_row.latest_version = world_version.world_version_id
                world_row.updated_at = now

            row = session.get(WorldVersionRow, world_version.world_version_id)
            if row is None:
                row = WorldVersionRow(
                    world_version_id=world_version.world_version_id,
                    world_id=world_version.world_id,
                    version=world_version.version,
                    author_id=world_version.author_id,
                    status="published" if publish else world_version.status,
                    risk_rating=world_version.risk_rating,
                    manifest_json=world_version.manifest_json,
                    worldpack_json=world_version.worldpack_json,
                    validation_report_json=world_version.validation_report_json,
                    simulation_report_json=world_version.simulation_report_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.version = world_version.version
                row.author_id = world_version.author_id
                row.status = "published" if publish else world_version.status
                row.risk_rating = world_version.risk_rating
                row.manifest_json = world_version.manifest_json
                row.worldpack_json = world_version.worldpack_json
                row.validation_report_json = world_version.validation_report_json
                row.simulation_report_json = world_version.simulation_report_json
                row.updated_at = now
            session.commit()
        world_version.status = "published" if publish else world_version.status
        return world_version

    def get_world_version(self, world_version_id: str) -> WorldVersion:
        with self.SessionLocal() as session:
            row = session.get(WorldVersionRow, world_version_id)
            if row is None:
                raise KeyError("unknown_world_version:%s" % world_version_id)
            return WorldVersion(
                world_version_id=row.world_version_id,
                world_id=row.world_id,
                version=row.version,
                author_id=row.author_id,
                status=row.status,
                risk_rating=row.risk_rating or "",
                manifest_json=dict(row.manifest_json or {}),
                worldpack_json=dict(row.worldpack_json or {}),
                validation_report_json=dict(row.validation_report_json or {}),
                simulation_report_json=dict(row.simulation_report_json or {}),
            )

    def list_world_versions(self, world_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(WorldVersionRow).order_by(desc(WorldVersionRow.updated_at))
            if world_id is not None:
                stmt = stmt.where(WorldVersionRow.world_id == world_id)
            if status is not None:
                stmt = stmt.where(WorldVersionRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "world_version_id": row.world_version_id,
                    "world_id": row.world_id,
                    "version": row.version,
                    "status": row.status,
                    "risk_rating": row.risk_rating,
                    "title": (row.worldpack_json or {}).get("title", row.world_id),
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def list_worlds(self) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            rows = session.execute(select(WorldRow).order_by(desc(WorldRow.updated_at))).scalars()
            worlds = []
            for row in rows:
                latest_worldpack = {}
                if row.latest_version:
                    try:
                        latest_worldpack = self.get_world_version(row.latest_version).worldpack_json
                    except KeyError:
                        latest_worldpack = {}
                worlds.append(
                    {
                        "world_id": row.world_id,
                        "title": row.title,
                        "status": row.status,
                        "latest_version": row.latest_version,
                        "genres": list((latest_worldpack.get("manifest") or {}).get("genres", [])),
                        "risk_rating": (latest_worldpack.get("manifest") or {}).get("risk_rating"),
                        "trial_available": ((latest_worldpack.get("manifest") or {}).get("monetization_policy") or {}).get("trial_chapters", 0) > 0,
                        "access_state": "trial",
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                )
            return worlds

    def get_world(self, world_id: str) -> WorldRecord:
        with self.SessionLocal() as session:
            row = session.get(WorldRow, world_id)
            if row is None or not row.latest_version:
                raise KeyError("unknown_world:%s" % world_id)
        runtime = self.get_runtime_bundle(row.latest_version)
        return runtime.world_record

    def get_runtime_bundle(self, world_version_id: str) -> RuntimeBundle:
        version = self.get_world_version(world_version_id)
        try:
            return self.registry.get_runtime_bundle(world_version_id)
        except KeyError:
            return runtime_bundle_from_worldpack_data(
                {
                    "world_version_id": world_version_id,
                    "world_id": version.world_id,
                    "status": version.status,
                    "worldpack": version.worldpack_json,
                }
            )

    def create_world(self, world_record: WorldRecord) -> WorldRecord:
        worldpack = WorldPack.from_dict(self.registry.get_published_world(world_record.world.world_id)["worldpack"]) if any(card["world_id"] == world_record.world.world_id for card in self.registry.list_worldpacks()) else None
        if worldpack is None:
            from ..worldpacks.models import worldpack_from_world_record

            worldpack = worldpack_from_world_record(world_record, initial_state=NarrativeState.from_dict({"state_id": "%s__bootstrap" % world_record.world.world_id, "world_id": world_record.world.world_id, "turn_index": 0, "story_phase": "setup", "chapter_index": 0, "min_end_turn": 8, "fate_pressure": 0.1, "karmic_weather": {}, "unresolved_debts": [], "world_facts": [], "timeline": [], "characters": {}, "relationship_graph": [], "open_promises": [], "tension": 0.0, "themes": {}, "player_intent": {}, "recent_scene_functions": [], "visited_event_ids": [], "route_fingerprint": [], "rating_ceiling": "PG13"}))
        world_version = WorldVersion.from_worldpack(
            worldpack=worldpack,
            world_version_id="%s@%s" % (worldpack.world_id, worldpack.version),
            status="published",
        )
        self.save_world_version(world_version, publish=True)
        return world_record

    # Sessions / chapters
    def create_session_record(
        self,
        *,
        world_version_id: str,
        initial_state: NarrativeState,
        reader_id: Optional[str] = None,
        player_profile: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        entitlements_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        world_version = self.get_world_version(world_version_id)
        record = SessionRecord(
            session_id=session_id or "session_%s" % uuid4().hex[:12],
            world_id=world_version.world_id,
            player_profile=dict(player_profile or {}),
            initial_state=initial_state,
            current_state=initial_state,
            created_at=utcnow_iso(),
            metadata={"world_version_id": world_version_id, **dict(metadata or {})},
        )
        with self.SessionLocal() as session:
            session.add(
                SessionRow(
                    session_id=record.session_id,
                    reader_id=reader_id,
                    world_version_id=world_version_id,
                    status="active",
                    chapter_index=initial_state.chapter_index,
                    story_phase=initial_state.story_phase,
                    narrative_state_json=record.current_state.to_dict(),
                    entitlements_snapshot_json=dict(entitlements_snapshot or {}),
                    created_at=record.created_at,
                    updated_at=record.created_at,
                )
            )
            session.commit()
        return record

    def create_session(
        self,
        world_id: str,
        initial_state: NarrativeState,
        *,
        player_profile: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        world_card = next((card for card in self.list_worlds() if card["world_id"] == world_id), None)
        if world_card is None:
            raise KeyError("unknown_world:%s" % world_id)
        return self.create_session_record(
            world_version_id=world_card["latest_version"],
            initial_state=initial_state,
            player_profile=player_profile,
            session_id=session_id,
            metadata=metadata,
        )

    def get_session(self, session_id: str) -> SessionRecord:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            world_version = self.get_world_version(row.world_version_id)
            current_state = NarrativeState.from_dict(dict(row.narrative_state_json))
            return SessionRecord(
                session_id=row.session_id,
                world_id=world_version.world_id,
                player_profile={"reader_id": row.reader_id} if row.reader_id else {},
                initial_state=current_state,
                current_state=current_state,
                created_at=row.created_at,
                metadata={
                    "world_version_id": row.world_version_id,
                    "reader_id": row.reader_id,
                    "entitlements_snapshot": dict(row.entitlements_snapshot_json or {}),
                },
            )

    def update_session_entitlements_snapshot(self, session_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            row.entitlements_snapshot_json = dict(snapshot or {})
            row.updated_at = utcnow_iso()
            session.commit()
            return dict(row.entitlements_snapshot_json or {})

    def list_sessions(self, world_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SessionRow).order_by(desc(SessionRow.updated_at))
            rows = session.execute(stmt).scalars()
            results = []
            for row in rows:
                world_version = self.get_world_version(row.world_version_id)
                if world_id is not None and world_version.world_id != world_id:
                    continue
                latest_step = self.get_latest_step(row.session_id)
                results.append(
                    {
                        "session_id": row.session_id,
                        "world_id": world_version.world_id,
                        "world_version_id": row.world_version_id,
                        "created_at": row.created_at,
                        "current_turn_index": row.chapter_index,
                        "last_event_title": latest_step.chosen_event.title if latest_step and latest_step.chosen_event else None,
                        "last_chapter_title": latest_step.reader_view.chapter_title if latest_step and latest_step.reader_view else None,
                    }
                )
            return results

    def save_step(self, step_record: StepRecord, *, world_version_id: Optional[str] = None, entitlements_snapshot: Optional[Dict[str, Any]] = None, cost_estimate: Optional[float] = None) -> StepRecord:
        created_at = step_record.created_at or utcnow_iso()
        step_record.created_at = created_at
        with self.SessionLocal() as session:
            session_row = session.get(SessionRow, step_record.session_id)
            if session_row is None:
                raise KeyError("unknown_session:%s" % step_record.session_id)
            chapter_id = "chapter_%s_%s" % (step_record.session_id, step_record.step_index)
            session.add(
                ChapterRow(
                    chapter_id=chapter_id,
                    session_id=step_record.session_id,
                    world_version_id=world_version_id or session_row.world_version_id,
                    chapter_index=step_record.step_index,
                    plan_json={
                        "step_record": step_record.to_dict(),
                        "chapter_plan": step_record.chapter_plan.to_dict() if step_record.chapter_plan else None,
                    },
                    rendered_body=step_record.reader_view.body if step_record.reader_view else (step_record.rendered_scene.premium_prose if step_record.rendered_scene else ""),
                    choices_json=step_record.reader_view.choices if step_record.reader_view else [],
                    cost_estimate=cost_estimate,
                    review_flags_json={"critic_trace": step_record.critic_trace},
                    created_at=created_at,
                )
            )
            session_row.chapter_index = step_record.state_after.chapter_index
            session_row.story_phase = step_record.state_after.story_phase
            session_row.narrative_state_json = step_record.state_after.to_dict()
            session_row.entitlements_snapshot_json = dict(entitlements_snapshot or (session_row.entitlements_snapshot_json or {}))
            session_row.updated_at = created_at
            session.commit()
        return step_record

    def save_evaluation_report(self, chapter_id: str, report: EvaluationReport) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ChapterRow, chapter_id)
            if row is None:
                raise KeyError("unknown_chapter:%s" % chapter_id)
            payload = dict(row.review_flags_json or {})
            payload["evaluation_report"] = report.to_dict()
            row.review_flags_json = payload
            session.commit()
        return report.to_dict()

    def get_evaluation_report(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ChapterRow, chapter_id)
            if row is None:
                raise KeyError("unknown_chapter:%s" % chapter_id)
            payload = dict(row.review_flags_json or {})
            return payload.get("evaluation_report")

    def list_evaluation_reports(
        self,
        *,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ChapterRow).order_by(desc(ChapterRow.created_at))
            if world_version_id is not None:
                stmt = stmt.where(ChapterRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(ChapterRow.session_id == session_id)
            rows = session.execute(stmt).scalars()
            reports = []
            for row in rows:
                payload = dict(row.review_flags_json or {})
                if payload.get("evaluation_report"):
                    reports.append(payload["evaluation_report"])
            return reports

    def list_steps(self, session_id: str) -> List[StepRecord]:
        with self.SessionLocal() as session:
            rows = session.execute(
                select(ChapterRow).where(ChapterRow.session_id == session_id).order_by(ChapterRow.chapter_index.asc())
            ).scalars()
            results = []
            for row in rows:
                payload = dict(row.plan_json or {})
                if payload.get("step_record"):
                    results.append(StepRecord.from_dict(payload["step_record"]))
            return results

    def get_latest_step(self, session_id: str) -> Optional[StepRecord]:
        steps = self.list_steps(session_id)
        return steps[-1] if steps else None

    def get_replay(self, session_id: str) -> Dict[str, Any]:
        session_record = self.get_session(session_id)
        steps = self.list_steps(session_id)
        evaluation_reports = self.list_evaluation_reports(session_id=session_id)
        return {
            "session": session_record.to_dict(),
            "full_timeline": [step.chosen_event.title for step in steps if step.chosen_event],
            "event_trace": [step.chosen_event.to_dict() for step in steps if step.chosen_event],
            "reader_views": [step.reader_view.to_dict() for step in steps if step.reader_view],
            "critic_trace": [step.critic_trace for step in steps],
            "state_snapshots": [session_record.initial_state.to_dict()] + [step.state_after.to_dict() for step in steps],
            "promise_ledger_snapshots": [[promise.to_dict() for promise in step.promise_ledger_snapshot] for step in steps],
            "rendered_scenes": [step.rendered_scene.to_dict() for step in steps if step.rendered_scene],
            "evaluation_reports": evaluation_reports,
        }

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            chapter_rows = session.execute(select(ChapterRow).where(ChapterRow.session_id == session_id)).scalars()
            deleted_steps = 0
            for chapter in chapter_rows:
                session.delete(chapter)
                deleted_steps += 1
            session.delete(row)
            session.commit()
        return {"session_id": session_id, "deleted_steps": deleted_steps}

    # Review / publish / rollback
    def save_review_record(self, review: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "review_id": review.get("review_id") or "review_%s" % uuid4().hex[:12],
            "asset_type": review["asset_type"],
            "asset_id": review["asset_id"],
            "status": review["status"],
            "reviewer_id": review.get("reviewer_id"),
            "risk_rating": review.get("risk_rating"),
            "notes": review.get("notes"),
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(ReviewRecordRow, payload["review_id"])
            if row is None:
                row = ReviewRecordRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.asset_type = payload["asset_type"]
                row.asset_id = payload["asset_id"]
                row.status = payload["status"]
                row.reviewer_id = payload["reviewer_id"]
                row.risk_rating = payload["risk_rating"]
                row.notes = payload["notes"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def save_author_comment_thread(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "thread_id": thread.get("thread_id") or "athread_%s" % uuid4().hex[:12],
            "world_version_id": thread["world_version_id"],
            "revision_id": thread.get("revision_id"),
            "anchor_type": thread["anchor_type"],
            "anchor_key": thread["anchor_key"],
            "status": thread.get("status", "open"),
            "severity": thread.get("severity", "normal"),
            "assignee_id": thread.get("assignee_id"),
            "created_by": thread["created_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentThreadRow, payload["thread_id"])
            if row is None:
                row = AuthorCommentThreadRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.world_version_id = payload["world_version_id"]
                row.revision_id = payload["revision_id"]
                row.anchor_type = payload["anchor_type"]
                row.anchor_key = payload["anchor_key"]
                row.status = payload["status"]
                row.severity = payload["severity"]
                row.assignee_id = payload["assignee_id"]
                row.created_by = payload["created_by"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def list_author_comment_threads(
        self,
        *,
        world_version_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        status: Optional[str] = None,
        anchor_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorCommentThreadRow).order_by(desc(AuthorCommentThreadRow.updated_at))
            if world_version_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.world_version_id == world_version_id)
            if revision_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.revision_id == revision_id)
            if status is not None:
                stmt = stmt.where(AuthorCommentThreadRow.status == status)
            if anchor_type is not None:
                stmt = stmt.where(AuthorCommentThreadRow.anchor_type == anchor_type)
            if assignee_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.assignee_id == assignee_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "thread_id": row.thread_id,
                    "world_version_id": row.world_version_id,
                    "revision_id": row.revision_id,
                    "anchor_type": row.anchor_type,
                    "anchor_key": row.anchor_key,
                    "status": row.status,
                    "severity": row.severity,
                    "assignee_id": row.assignee_id,
                    "created_by": row.created_by,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def get_author_comment_thread(self, thread_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentThreadRow, thread_id)
            if row is None:
                raise KeyError("unknown_author_comment_thread:%s" % thread_id)
            return {
                "thread_id": row.thread_id,
                "world_version_id": row.world_version_id,
                "revision_id": row.revision_id,
                "anchor_type": row.anchor_type,
                "anchor_key": row.anchor_key,
                "status": row.status,
                "severity": row.severity,
                "assignee_id": row.assignee_id,
                "created_by": row.created_by,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_author_comment_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "message_id": message.get("message_id") or "acomment_%s" % uuid4().hex[:12],
            "thread_id": message["thread_id"],
            "actor_id": message["actor_id"],
            "actor_role": message["actor_role"],
            "body": message["body"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentMessageRow, payload["message_id"])
            if row is None:
                row = AuthorCommentMessageRow(created_at=now, **payload)
                session.add(row)
            else:
                row.thread_id = payload["thread_id"]
                row.actor_id = payload["actor_id"]
                row.actor_role = payload["actor_role"]
                row.body = payload["body"]
            thread_row = session.get(AuthorCommentThreadRow, payload["thread_id"])
            if thread_row is not None:
                thread_row.updated_at = now
            session.commit()
        payload["created_at"] = now
        return payload

    def list_author_comment_messages(self, *, thread_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = (
                select(AuthorCommentMessageRow)
                .where(AuthorCommentMessageRow.thread_id == thread_id)
                .order_by(AuthorCommentMessageRow.created_at.asc())
            )
            rows = session.execute(stmt).scalars()
            return [
                {
                    "message_id": row.message_id,
                    "thread_id": row.thread_id,
                    "actor_id": row.actor_id,
                    "actor_role": row.actor_role,
                    "body": row.body,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def save_author_approval_record(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "approval_id": approval.get("approval_id") or "approval_%s" % uuid4().hex[:12],
            "world_version_id": approval["world_version_id"],
            "revision_id": approval.get("revision_id"),
            "status": approval["status"],
            "reviewer_id": approval["reviewer_id"],
            "reason": approval["reason"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorApprovalRecordRow, payload["approval_id"])
            if row is None:
                row = AuthorApprovalRecordRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.world_version_id = payload["world_version_id"]
                row.revision_id = payload["revision_id"]
                row.status = payload["status"]
                row.reviewer_id = payload["reviewer_id"]
                row.reason = payload["reason"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def list_author_approval_records(
        self,
        *,
        world_version_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorApprovalRecordRow).order_by(desc(AuthorApprovalRecordRow.updated_at))
            if world_version_id is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.world_version_id == world_version_id)
            if revision_id is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.revision_id == revision_id)
            if status is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "approval_id": row.approval_id,
                    "world_version_id": row.world_version_id,
                    "revision_id": row.revision_id,
                    "status": row.status,
                    "reviewer_id": row.reviewer_id,
                    "reason": row.reason,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_author_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "notification_id": notification.get("notification_id") or "anotify_%s" % uuid4().hex[:12],
            "world_version_id": notification["world_version_id"],
            "thread_id": notification.get("thread_id"),
            "approval_id": notification.get("approval_id"),
            "recipient_id": notification["recipient_id"],
            "recipient_role": notification.get("recipient_role", "reviewer"),
            "notification_type": notification["notification_type"],
            "status": notification.get("status", "unread"),
            "actor_id": notification.get("actor_id"),
            "actor_role": notification.get("actor_role"),
            "title": notification["title"],
            "body": notification["body"],
            "anchor_type": notification.get("anchor_type"),
            "anchor_key": notification.get("anchor_key"),
            "metadata_json": dict(notification.get("metadata_json") or {}),
            "read_at": notification.get("read_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthorNotificationRow, payload["notification_id"])
            if row is None:
                row = AuthorNotificationRow(created_at=now, updated_at=now, **payload)
                session.add(row)
                created_at = now
            else:
                row.world_version_id = payload["world_version_id"]
                row.thread_id = payload["thread_id"]
                row.approval_id = payload["approval_id"]
                row.recipient_id = payload["recipient_id"]
                row.recipient_role = payload["recipient_role"]
                row.notification_type = payload["notification_type"]
                row.status = payload["status"]
                row.actor_id = payload["actor_id"]
                row.actor_role = payload["actor_role"]
                row.title = payload["title"]
                row.body = payload["body"]
                row.anchor_type = payload["anchor_type"]
                row.anchor_key = payload["anchor_key"]
                row.metadata_json = payload["metadata_json"]
                row.read_at = payload["read_at"]
                row.updated_at = now
                created_at = row.created_at
            session.commit()
        payload["created_at"] = created_at
        payload["updated_at"] = now
        return payload

    def save_author_thread_watcher(self, watcher: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.list_author_thread_watchers(
            thread_id=watcher["thread_id"],
            watcher_id=watcher["watcher_id"],
        )
        if existing:
            return existing[0]
        payload = {
            "watcher_record_id": watcher.get("watcher_record_id") or "awatcher_%s" % uuid4().hex[:12],
            "thread_id": watcher["thread_id"],
            "watcher_id": watcher["watcher_id"],
            "added_by": watcher["added_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            session.add(AuthorThreadWatcherRow(created_at=now, **payload))
            session.commit()
        payload["created_at"] = now
        return payload

    def save_author_draft_watcher(self, watcher: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.list_author_draft_watchers(
            world_version_id=watcher["world_version_id"],
            watcher_id=watcher["watcher_id"],
        )
        if existing:
            return existing[0]
        payload = {
            "watcher_record_id": watcher.get("watcher_record_id") or "adwatcher_%s" % uuid4().hex[:12],
            "world_version_id": watcher["world_version_id"],
            "watcher_id": watcher["watcher_id"],
            "added_by": watcher["added_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            session.add(AuthorDraftWatcherRow(created_at=now, **payload))
            session.commit()
        payload["created_at"] = now
        return payload

    def list_author_thread_watchers(
        self,
        *,
        thread_id: Optional[str] = None,
        watcher_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorThreadWatcherRow).order_by(AuthorThreadWatcherRow.created_at.asc())
            if thread_id is not None:
                stmt = stmt.where(AuthorThreadWatcherRow.thread_id == thread_id)
            if watcher_id is not None:
                stmt = stmt.where(AuthorThreadWatcherRow.watcher_id == watcher_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "watcher_record_id": row.watcher_record_id,
                    "thread_id": row.thread_id,
                    "watcher_id": row.watcher_id,
                    "added_by": row.added_by,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def delete_author_thread_watcher(self, *, thread_id: str, watcher_id: str) -> Dict[str, Any]:
        removed = {"thread_id": thread_id, "watcher_id": watcher_id, "deleted": False}
        with self.SessionLocal() as session:
            rows = session.execute(
                select(AuthorThreadWatcherRow).where(
                    AuthorThreadWatcherRow.thread_id == thread_id,
                    AuthorThreadWatcherRow.watcher_id == watcher_id,
                )
            ).scalars().all()
            for row in rows:
                removed["deleted"] = True
                removed["watcher_record_id"] = row.watcher_record_id
                removed["created_at"] = row.created_at
                session.delete(row)
            session.commit()
        return removed

    def list_author_draft_watchers(
        self,
        *,
        world_version_id: Optional[str] = None,
        watcher_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorDraftWatcherRow).order_by(AuthorDraftWatcherRow.created_at.asc())
            if world_version_id is not None:
                stmt = stmt.where(AuthorDraftWatcherRow.world_version_id == world_version_id)
            if watcher_id is not None:
                stmt = stmt.where(AuthorDraftWatcherRow.watcher_id == watcher_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "watcher_record_id": row.watcher_record_id,
                    "world_version_id": row.world_version_id,
                    "watcher_id": row.watcher_id,
                    "added_by": row.added_by,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def delete_author_draft_watcher(self, *, world_version_id: str, watcher_id: str) -> Dict[str, Any]:
        removed = {"world_version_id": world_version_id, "watcher_id": watcher_id, "deleted": False}
        with self.SessionLocal() as session:
            rows = session.execute(
                select(AuthorDraftWatcherRow).where(
                    AuthorDraftWatcherRow.world_version_id == world_version_id,
                    AuthorDraftWatcherRow.watcher_id == watcher_id,
                )
            ).scalars().all()
            for row in rows:
                removed["deleted"] = True
                removed["watcher_record_id"] = row.watcher_record_id
                removed["created_at"] = row.created_at
                session.delete(row)
            session.commit()
        return removed

    def get_author_notification(self, notification_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthorNotificationRow, notification_id)
            if row is None:
                raise KeyError("unknown_author_notification:%s" % notification_id)
            return {
                "notification_id": row.notification_id,
                "world_version_id": row.world_version_id,
                "thread_id": row.thread_id,
                "approval_id": row.approval_id,
                "recipient_id": row.recipient_id,
                "recipient_role": row.recipient_role,
                "notification_type": row.notification_type,
                "status": row.status,
                "actor_id": row.actor_id,
                "actor_role": row.actor_role,
                "title": row.title,
                "body": row.body,
                "anchor_type": row.anchor_type,
                "anchor_key": row.anchor_key,
                "metadata_json": dict(row.metadata_json or {}),
                "read_at": row.read_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def list_author_notifications(
        self,
        *,
        recipient_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        status: Optional[str] = None,
        notification_type: Optional[str] = None,
        cursor_updated_at: Optional[str] = None,
        cursor_notification_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationRow).order_by(desc(AuthorNotificationRow.updated_at), desc(AuthorNotificationRow.notification_id))
            if recipient_id is not None:
                stmt = stmt.where(AuthorNotificationRow.recipient_id == recipient_id)
            if world_version_id is not None:
                stmt = stmt.where(AuthorNotificationRow.world_version_id == world_version_id)
            if thread_id is not None:
                stmt = stmt.where(AuthorNotificationRow.thread_id == thread_id)
            if approval_id is not None:
                stmt = stmt.where(AuthorNotificationRow.approval_id == approval_id)
            if status is not None:
                stmt = stmt.where(AuthorNotificationRow.status == status)
            if notification_type is not None:
                stmt = stmt.where(AuthorNotificationRow.notification_type == notification_type)
            rows = session.execute(stmt).scalars()
            items = [
                {
                    "notification_id": row.notification_id,
                    "world_version_id": row.world_version_id,
                    "thread_id": row.thread_id,
                    "approval_id": row.approval_id,
                    "recipient_id": row.recipient_id,
                    "recipient_role": row.recipient_role,
                    "notification_type": row.notification_type,
                    "status": row.status,
                    "actor_id": row.actor_id,
                    "actor_role": row.actor_role,
                    "title": row.title,
                    "body": row.body,
                    "anchor_type": row.anchor_type,
                    "anchor_key": row.anchor_key,
                    "metadata_json": dict(row.metadata_json or {}),
                    "read_at": row.read_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]
        if cursor_updated_at is not None and cursor_notification_id is not None:
            filtered = []
            for item in items:
                updated_at = str(item.get("updated_at") or "")
                notification_id_value = str(item.get("notification_id") or "")
                if updated_at < cursor_updated_at:
                    filtered.append(item)
                elif updated_at == cursor_updated_at and notification_id_value < cursor_notification_id:
                    filtered.append(item)
            items = filtered
        if limit is not None:
            items = items[:limit]
        return items

    def save_author_notification_preference(self, preference: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "preference_id": preference.get("preference_id") or "apref_%s" % uuid4().hex[:12],
            "actor_id": preference["actor_id"],
            "notification_type": preference["notification_type"],
            "in_app_enabled": "true" if preference.get("in_app_enabled", True) else "false",
            "async_mirror_enabled": "true" if preference.get("async_mirror_enabled", True) else "false",
            "async_sink_name": preference.get("async_sink_name"),
            "delivery_target": preference.get("delivery_target"),
        }
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationPreferenceRow).where(
                AuthorNotificationPreferenceRow.actor_id == payload["actor_id"],
                AuthorNotificationPreferenceRow.notification_type == payload["notification_type"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = AuthorNotificationPreferenceRow(updated_at=now, **payload)
                session.add(row)
            else:
                row.in_app_enabled = payload["in_app_enabled"]
                row.async_mirror_enabled = payload["async_mirror_enabled"]
                row.async_sink_name = payload["async_sink_name"]
                row.delivery_target = payload["delivery_target"]
                row.updated_at = now
                payload["preference_id"] = row.preference_id
            session.commit()
        return {
            **payload,
            "in_app_enabled": payload["in_app_enabled"] == "true",
            "async_mirror_enabled": payload["async_mirror_enabled"] == "true",
            "updated_at": now,
        }

    def list_author_notification_preferences(
        self,
        *,
        actor_id: Optional[str] = None,
        notification_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationPreferenceRow).order_by(
                AuthorNotificationPreferenceRow.actor_id.asc(),
                AuthorNotificationPreferenceRow.notification_type.asc(),
            )
            if actor_id is not None:
                stmt = stmt.where(AuthorNotificationPreferenceRow.actor_id == actor_id)
            if notification_type is not None:
                stmt = stmt.where(AuthorNotificationPreferenceRow.notification_type == notification_type)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "preference_id": row.preference_id,
                    "actor_id": row.actor_id,
                    "notification_type": row.notification_type,
                    "in_app_enabled": row.in_app_enabled == "true",
                    "async_mirror_enabled": row.async_mirror_enabled == "true",
                    "async_sink_name": row.async_sink_name,
                    "delivery_target": row.delivery_target,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_auth_identity(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "actor_id": identity["actor_id"],
            "account_id": identity.get("account_id"),
            "actor_role": identity["actor_role"],
            "display_name": identity.get("display_name"),
            "password_hash": identity["password_hash"],
            "password_salt": identity["password_salt"],
            "status": identity.get("status", "active"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityRow, payload["actor_id"])
            if row is None:
                row = AuthIdentityRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.actor_role = payload["actor_role"]
                row.display_name = payload["display_name"]
                row.password_hash = payload["password_hash"]
                row.password_salt = payload["password_salt"]
                row.status = payload["status"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "created_at": now,
            "updated_at": now,
        }

    def get_auth_identity(self, actor_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityRow, actor_id)
            if row is None:
                raise KeyError("unknown_auth_identity:%s" % actor_id)
            return {
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "display_name": row.display_name,
                "password_hash": row.password_hash,
                "password_salt": row.password_salt,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_auth_token(self, token: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "token_id": token.get("token_id") or "token_%s" % uuid4().hex[:12],
            "actor_id": token["actor_id"],
            "account_id": token.get("account_id"),
            "actor_role": token["actor_role"],
            "token_hash": token["token_hash"],
            "status": token.get("status", "active"),
            "expires_at": token.get("expires_at"),
            "last_used_at": token.get("last_used_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthTokenRow, payload["token_id"])
            if row is None:
                row = AuthTokenRow(created_at=now, **payload)
                session.add(row)
            else:
                row.actor_id = payload["actor_id"]
                row.account_id = payload["account_id"]
                row.actor_role = payload["actor_role"]
                row.token_hash = payload["token_hash"]
                row.status = payload["status"]
                row.expires_at = payload["expires_at"]
                row.last_used_at = payload["last_used_at"]
            session.commit()
        return {
            **payload,
            "created_at": now,
        }

    def get_auth_token_by_hash(self, token_hash: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(AuthTokenRow).where(AuthTokenRow.token_hash == token_hash)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                raise KeyError("unknown_auth_token")
            return {
                "token_id": row.token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "token_hash": row.token_hash,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "last_used_at": row.last_used_at,
            }

    def update_auth_token(self, token_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthTokenRow, token_id)
            if row is None:
                raise KeyError("unknown_auth_token:%s" % token_id)
            for key in ["status", "expires_at", "last_used_at", "account_id", "actor_role"]:
                if key in updates:
                    setattr(row, key, updates[key])
            session.commit()
            return {
                "token_id": row.token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "token_hash": row.token_hash,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "last_used_at": row.last_used_at,
            }

    def save_billing_checkout_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "checkout_session_id": payload.get("checkout_session_id") or "bcheckout_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "tier_id": payload["tier_id"],
            "provider": payload["provider"],
            "provider_ref": payload.get("provider_ref"),
            "subscription_id": payload.get("subscription_id"),
            "status": payload.get("status", "created"),
            "checkout_url": payload.get("checkout_url"),
            "idempotency_key": payload["idempotency_key"],
            "expires_at": payload.get("expires_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingCheckoutSessionRow, record["checkout_session_id"])
            if row is None:
                row = BillingCheckoutSessionRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.account_id = record["account_id"]
                row.tier_id = record["tier_id"]
                row.provider = record["provider"]
                row.provider_ref = record["provider_ref"]
                row.subscription_id = record["subscription_id"]
                row.status = record["status"]
                row.checkout_url = record["checkout_url"]
                row.idempotency_key = record["idempotency_key"]
                row.expires_at = record["expires_at"]
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def get_billing_checkout_session(self, checkout_session_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(BillingCheckoutSessionRow, checkout_session_id)
            if row is None:
                raise KeyError("unknown_billing_checkout_session:%s" % checkout_session_id)
            return {
                "checkout_session_id": row.checkout_session_id,
                "account_id": row.account_id,
                "tier_id": row.tier_id,
                "provider": row.provider,
                "provider_ref": row.provider_ref,
                "subscription_id": row.subscription_id,
                "status": row.status,
                "checkout_url": row.checkout_url,
                "idempotency_key": row.idempotency_key,
                "expires_at": row.expires_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def list_billing_checkout_sessions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingCheckoutSessionRow).order_by(desc(BillingCheckoutSessionRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.status == status)
            if provider is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.provider == provider)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "checkout_session_id": row.checkout_session_id,
                    "account_id": row.account_id,
                    "tier_id": row.tier_id,
                    "provider": row.provider,
                    "provider_ref": row.provider_ref,
                    "subscription_id": row.subscription_id,
                    "status": row.status,
                    "checkout_url": row.checkout_url,
                    "idempotency_key": row.idempotency_key,
                    "expires_at": row.expires_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def latest_billing_checkout_session(self, *, account_id: str) -> Optional[Dict[str, Any]]:
        sessions = self.list_billing_checkout_sessions(account_id=account_id, limit=1)
        return sessions[0] if sessions else None

    def save_billing_lifecycle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_billing_lifecycle_event_by_provider_ref(
            provider=payload["provider"],
            provider_event_id=payload["provider_event_id"],
            default=None,
        )
        if existing is not None:
            payload = {
                **existing,
                **payload,
                "event_id": existing["event_id"],
            }
        now = utcnow_iso()
        record = {
            "event_id": payload.get("event_id") or "bevent_%s" % uuid4().hex[:12],
            "event_type": payload["event_type"],
            "provider": payload["provider"],
            "provider_event_id": payload["provider_event_id"],
            "account_id": payload.get("account_id"),
            "subscription_id": payload.get("subscription_id"),
            "checkout_session_id": payload.get("checkout_session_id"),
            "status": payload.get("status", "received"),
            "payload_json": dict(payload.get("payload_json") or {}),
            "processing_result": dict(payload.get("processing_result") or {}) if payload.get("processing_result") is not None else None,
            "occurred_at": payload.get("occurred_at") or now,
            "processed_at": payload.get("processed_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingLifecycleEventRow, record["event_id"])
            if row is None:
                row = BillingLifecycleEventRow(**record)
                session.add(row)
            else:
                row.event_type = record["event_type"]
                row.provider = record["provider"]
                row.provider_event_id = record["provider_event_id"]
                row.account_id = record["account_id"]
                row.subscription_id = record["subscription_id"]
                row.checkout_session_id = record["checkout_session_id"]
                row.status = record["status"]
                row.payload_json = record["payload_json"]
                row.processing_result = record["processing_result"]
                row.occurred_at = record["occurred_at"]
                row.processed_at = record["processed_at"]
            session.commit()
        return record

    def get_billing_lifecycle_event_by_provider_ref(
        self,
        *,
        provider: str,
        provider_event_id: str,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingLifecycleEventRow).where(
                BillingLifecycleEventRow.provider == provider,
                BillingLifecycleEventRow.provider_event_id == provider_event_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_billing_lifecycle_event:%s:%s" % (provider, provider_event_id))
                return default
            return {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "provider": row.provider,
                "provider_event_id": row.provider_event_id,
                "account_id": row.account_id,
                "subscription_id": row.subscription_id,
                "checkout_session_id": row.checkout_session_id,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                "occurred_at": row.occurred_at,
                "processed_at": row.processed_at,
            }

    def list_billing_lifecycle_events(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        checkout_session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingLifecycleEventRow).order_by(desc(BillingLifecycleEventRow.occurred_at))
            if account_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.account_id == account_id)
            if subscription_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.subscription_id == subscription_id)
            if checkout_session_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.checkout_session_id == checkout_session_id)
            if event_type is not None:
                stmt = stmt.where(BillingLifecycleEventRow.event_type == event_type)
            if status is not None:
                stmt = stmt.where(BillingLifecycleEventRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "provider": row.provider,
                    "provider_event_id": row.provider_event_id,
                    "account_id": row.account_id,
                    "subscription_id": row.subscription_id,
                    "checkout_session_id": row.checkout_session_id,
                    "status": row.status,
                    "payload_json": dict(row.payload_json or {}),
                    "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                    "occurred_at": row.occurred_at,
                    "processed_at": row.processed_at,
                }
                for row in rows
            ]

    def get_billing_lifecycle_event(self, event_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(BillingLifecycleEventRow, event_id)
            if row is None:
                raise KeyError("unknown_billing_lifecycle_event:%s" % event_id)
            return {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "provider": row.provider,
                "provider_event_id": row.provider_event_id,
                "account_id": row.account_id,
                "subscription_id": row.subscription_id,
                "checkout_session_id": row.checkout_session_id,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                "occurred_at": row.occurred_at,
                "processed_at": row.processed_at,
            }

    def save_billing_retry_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "retry_attempt_id": payload.get("retry_attempt_id") or "bretry_%s" % uuid4().hex[:12],
            "account_id": payload.get("account_id"),
            "subscription_id": payload.get("subscription_id"),
            "checkout_session_id": payload.get("checkout_session_id"),
            "source_event_id": payload.get("source_event_id"),
            "status": payload.get("status", "planned"),
            "retry_reason": payload.get("retry_reason"),
            "attempt_count": int(payload.get("attempt_count") or 1),
            "next_retry_at": payload.get("next_retry_at"),
            "payload_json": dict(payload.get("payload_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingRetryAttemptRow, record["retry_attempt_id"])
            if row is None:
                row = BillingRetryAttemptRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.account_id = record["account_id"]
                row.subscription_id = record["subscription_id"]
                row.checkout_session_id = record["checkout_session_id"]
                row.source_event_id = record["source_event_id"]
                row.status = record["status"]
                row.retry_reason = record["retry_reason"]
                row.attempt_count = record["attempt_count"]
                row.next_retry_at = record["next_retry_at"]
                row.payload_json = record["payload_json"]
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def list_billing_retry_attempts(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingRetryAttemptRow).order_by(desc(BillingRetryAttemptRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.account_id == account_id)
            if subscription_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.subscription_id == subscription_id)
            if source_event_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.source_event_id == source_event_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "retry_attempt_id": row.retry_attempt_id,
                    "account_id": row.account_id,
                    "subscription_id": row.subscription_id,
                    "checkout_session_id": row.checkout_session_id,
                    "source_event_id": row.source_event_id,
                    "status": row.status,
                    "retry_reason": row.retry_reason,
                    "attempt_count": row.attempt_count,
                    "next_retry_at": row.next_retry_at,
                    "payload_json": dict(row.payload_json or {}),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def latest_billing_retry_attempt(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        attempts = self.list_billing_retry_attempts(
            account_id=account_id,
            subscription_id=subscription_id,
            limit=1,
        )
        return attempts[0] if attempts else None

    def list_review_records(
        self,
        *,
        status: Optional[str] = None,
        asset_type: Optional[str] = None,
        asset_id: Optional[str] = None,
        asset_ids: Optional[List[str]] = None,
        reviewer_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ReviewRecordRow).order_by(desc(ReviewRecordRow.updated_at))
            if status is not None:
                stmt = stmt.where(ReviewRecordRow.status == status)
            if asset_type is not None:
                stmt = stmt.where(ReviewRecordRow.asset_type == asset_type)
            if asset_id is not None:
                stmt = stmt.where(ReviewRecordRow.asset_id == asset_id)
            if asset_ids:
                stmt = stmt.where(ReviewRecordRow.asset_id.in_(asset_ids))
            if reviewer_id is not None:
                stmt = stmt.where(ReviewRecordRow.reviewer_id == reviewer_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "review_id": row.review_id,
                    "asset_type": row.asset_type,
                    "asset_id": row.asset_id,
                    "status": row.status,
                    "reviewer_id": row.reviewer_id,
                    "risk_rating": row.risk_rating,
                    "notes": row.notes,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def publish_world_version(self, world_version_id: str, *, reviewer_id: Optional[str] = None) -> Dict[str, Any]:
        world_version = self.get_world_version(world_version_id)
        world_version.status = "published"
        self.save_world_version(world_version, publish=True)
        return {"world_version_id": world_version_id, "status": "published", "reviewer_id": reviewer_id}

    def rollback_world(self, world_id: str, target_world_version_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            world_row = session.get(WorldRow, world_id)
            if world_row is None:
                raise KeyError("unknown_world:%s" % world_id)
            previous_version = world_row.latest_version
            world_row.latest_version = target_world_version_id
            world_row.updated_at = utcnow_iso()
            target_row = session.get(WorldVersionRow, target_world_version_id)
            if target_row is None:
                raise KeyError("unknown_world_version:%s" % target_world_version_id)
            target_row.status = "published"
            target_row.updated_at = utcnow_iso()
            session.commit()
        return {
            "world_id": world_id,
            "latest_version": target_world_version_id,
            "previous_version": previous_version,
            "status": "rolled_back",
        }

    # Entitlements / billing / meters / analytics
    def list_entitlements(
        self,
        reader_id: Optional[str] = None,
        *,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        wallet_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(EntitlementRow).order_by(desc(EntitlementRow.created_at))
            if account_id is not None:
                stmt = stmt.where(EntitlementRow.account_id == account_id)
            elif reader_id is not None:
                stmt = stmt.where(EntitlementRow.reader_id == reader_id)
            else:
                raise ValueError("reader_id_or_account_id_required")
            if world_id is not None:
                stmt = stmt.where((EntitlementRow.world_id == world_id) | (EntitlementRow.world_id.is_(None)))
            if wallet_type is not None:
                stmt = stmt.where(EntitlementRow.wallet_type == wallet_type)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "entitlement_id": row.entitlement_id,
                    "account_id": row.account_id,
                    "reader_id": row.reader_id,
                    "world_id": row.world_id,
                    "entitlement_type": row.entitlement_type,
                    "wallet_type": row.wallet_type,
                    "tier_id": row.tier_id,
                    "status": row.status,
                    "balance": row.balance,
                    "expires_at": row.expires_at,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def save_entitlement(self, entitlement: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "entitlement_id": entitlement.get("entitlement_id") or "entitlement_%s" % uuid4().hex[:12],
            "account_id": entitlement.get("account_id") or entitlement.get("reader_id"),
            "reader_id": entitlement.get("reader_id") or entitlement.get("account_id"),
            "world_id": entitlement.get("world_id"),
            "entitlement_type": entitlement["entitlement_type"],
            "wallet_type": entitlement.get("wallet_type"),
            "tier_id": entitlement.get("tier_id"),
            "status": entitlement.get("status", "active"),
            "balance": entitlement.get("balance"),
            "expires_at": entitlement.get("expires_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(EntitlementRow, payload["entitlement_id"])
            if row is None:
                session.add(EntitlementRow(created_at=utcnow_iso(), **payload))
            else:
                row.account_id = payload["account_id"]
                row.reader_id = payload["reader_id"]
                row.world_id = payload["world_id"]
                row.entitlement_type = payload["entitlement_type"]
                row.wallet_type = payload["wallet_type"]
                row.tier_id = payload["tier_id"]
                row.status = payload["status"]
                row.balance = payload["balance"]
                row.expires_at = payload["expires_at"]
            session.commit()
        return payload

    def get_entitlement(self, entitlement_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(EntitlementRow, entitlement_id)
            if row is None:
                raise KeyError("unknown_entitlement:%s" % entitlement_id)
            return {
                "entitlement_id": row.entitlement_id,
                "account_id": row.account_id,
                "reader_id": row.reader_id,
                "world_id": row.world_id,
                "entitlement_type": row.entitlement_type,
                "wallet_type": row.wallet_type,
                "tier_id": row.tier_id,
                "status": row.status,
                "balance": row.balance,
                "expires_at": row.expires_at,
                "created_at": row.created_at,
            }

    def list_subscriptions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SubscriptionRow).order_by(desc(SubscriptionRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(SubscriptionRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(SubscriptionRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "subscription_id": row.subscription_id,
                    "account_id": row.account_id,
                    "tier_id": row.tier_id,
                    "provider": row.provider,
                    "provider_ref": row.provider_ref,
                    "status": row.status,
                    "period_start": row.period_start,
                    "period_end": row.period_end,
                    "cancel_at_period_end": row.cancel_at_period_end == "true",
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_subscription(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "subscription_id": subscription.get("subscription_id") or "subscription_%s" % uuid4().hex[:12],
            "account_id": subscription["account_id"],
            "tier_id": subscription["tier_id"],
            "provider": subscription.get("provider", "web_stub"),
            "provider_ref": subscription.get("provider_ref"),
            "status": subscription.get("status", "trialing"),
            "period_start": subscription.get("period_start"),
            "period_end": subscription.get("period_end"),
            "cancel_at_period_end": "true" if subscription.get("cancel_at_period_end") else "false",
        }
        with self.SessionLocal() as session:
            row = session.get(SubscriptionRow, payload["subscription_id"])
            if row is None:
                row = SubscriptionRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.tier_id = payload["tier_id"]
                row.provider = payload["provider"]
                row.provider_ref = payload["provider_ref"]
                row.status = payload["status"]
                row.period_start = payload["period_start"]
                row.period_end = payload["period_end"]
                row.cancel_at_period_end = payload["cancel_at_period_end"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "cancel_at_period_end": payload["cancel_at_period_end"] == "true",
            "created_at": now,
            "updated_at": now,
        }

    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SubscriptionRow, subscription_id)
            if row is None:
                raise KeyError("unknown_subscription:%s" % subscription_id)
            return {
                "subscription_id": row.subscription_id,
                "account_id": row.account_id,
                "tier_id": row.tier_id,
                "provider": row.provider,
                "provider_ref": row.provider_ref,
                "status": row.status,
                "period_start": row.period_start,
                "period_end": row.period_end,
                "cancel_at_period_end": row.cancel_at_period_end == "true",
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def get_active_subscription_for_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        subscriptions = self.list_subscriptions(account_id=account_id)
        return next(
            (
                item
                for item in subscriptions
                if item["status"] in {"trialing", "active"}
            ),
            None,
        )

    def create_usage_meter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "meter_id": payload.get("meter_id") or "meter_%s" % uuid4().hex[:12],
            "account_id": payload.get("account_id"),
            "reader_id": payload.get("reader_id"),
            "session_id": payload.get("session_id"),
            "chapter_id": payload.get("chapter_id"),
            "world_version_id": payload.get("world_version_id"),
            "action_type": payload["action_type"],
            "usage_units": float(payload.get("usage_units", 0.0)),
            "estimated_cost": float(payload.get("estimated_cost", 0.0)),
            "wallet_type": payload.get("wallet_type"),
            "subscription_tier": payload.get("subscription_tier"),
            "provider": payload.get("provider"),
            "model_policy_version": payload.get("model_policy_version"),
        }
        with self.SessionLocal() as session:
            session.add(UsageMeterRow(created_at=utcnow_iso(), **record))
            session.commit()
        return record

    def list_usage_meters(
        self,
        *,
        reader_id: Optional[str] = None,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(UsageMeterRow).order_by(desc(UsageMeterRow.created_at))
            if account_id is not None:
                stmt = stmt.where(UsageMeterRow.account_id == account_id)
            if reader_id is not None:
                stmt = stmt.where(UsageMeterRow.reader_id == reader_id)
            if session_id is not None:
                stmt = stmt.where(UsageMeterRow.session_id == session_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "meter_id": row.meter_id,
                    "account_id": row.account_id,
                    "reader_id": row.reader_id,
                    "session_id": row.session_id,
                    "chapter_id": row.chapter_id,
                    "world_version_id": row.world_version_id,
                    "action_type": row.action_type,
                    "usage_units": row.usage_units,
                    "estimated_cost": row.estimated_cost,
                    "wallet_type": row.wallet_type,
                    "subscription_tier": row.subscription_tier,
                    "provider": row.provider,
                    "model_policy_version": row.model_policy_version,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def aggregate_eval_metrics(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_version_ids: Optional[List[str]] = None
        if world_version_id is not None:
            selected_version_ids = [world_version_id]
        elif world_id is not None:
            selected_version_ids = [item["world_version_id"] for item in self.list_world_versions(world_id=world_id)]

        report_payloads: List[Dict[str, Any]] = []
        if selected_version_ids is None:
            report_payloads = self.list_evaluation_reports()
        else:
            for version_id in selected_version_ids:
                report_payloads.extend(self.list_evaluation_reports(world_version_id=version_id))
        reports = [EvaluationReport.from_dict(item) for item in report_payloads]
        if not reports:
            return {
                "pass_rate": 0.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
                "per_world_pack_quality_trend": [],
                "online_continuation_correlation": 0.0,
                "continuation_signal_summary": {
                    "sample_count": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "censored_count": 0,
                    "continuation_rate": 0.0,
                    "stale_window_hours": CONTINUATION_STALE_WINDOW_HOURS,
                },
                "quality_signal_correlations": [],
                "continuation_world_details": [],
                "continuation_version_details": [],
                "continuation_sample_accumulation": {
                    "target_sample_count_per_world": CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                    "target_sample_count_per_version": CONTINUATION_TARGET_SAMPLES_PER_VERSION,
                    "target_negative_samples": CONTINUATION_TARGET_NEGATIVE_SAMPLES,
                    "worlds_below_target_count": 0,
                    "versions_below_target_count": 0,
                    "prioritized_worlds": [],
                    "prioritized_versions": [],
                },
            }
        from ..eval.reporting import aggregate_reports

        aggregate = aggregate_reports(reports)
        with self.SessionLocal() as session:
            stmt = select(AnalyticsEventRow).where(AnalyticsEventRow.event_name.in_(["continue_story", "chapter_rendered"]))
            if selected_version_ids is not None:
                stmt = stmt.where(AnalyticsEventRow.world_version_id.in_(selected_version_ids))
            analytics_rows = session.execute(stmt).scalars()
            continue_events = [row for row in analytics_rows if row.event_name == "continue_story"]
            chapter_stmt = (
                select(ChapterRow, SessionRow)
                .join(SessionRow, ChapterRow.session_id == SessionRow.session_id)
                .order_by(ChapterRow.session_id.asc(), ChapterRow.chapter_index.asc())
            )
            if selected_version_ids is not None:
                chapter_stmt = chapter_stmt.where(ChapterRow.world_version_id.in_(selected_version_ids))
            chapter_rows = session.execute(chapter_stmt).all()
        average_score = sum(report.scores.overall_score for report in reports) / float(max(1, len(reports)))
        aggregate["per_world_pack_quality_trend"] = [
            {
                "world_version_id": world_version_id or (world_id or "all"),
                "avg_score": round(average_score, 3),
            }
        ]
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=CONTINUATION_STALE_WINDOW_HOURS)
        grouped_chapters: Dict[str, List[Dict[str, Any]]] = {}
        world_id_cache: Dict[str, str] = {}
        for chapter_row, session_row in chapter_rows:
            payload = dict(chapter_row.review_flags_json or {})
            report_payload = payload.get("evaluation_report")
            if not report_payload:
                continue
            report = EvaluationReport.from_dict(report_payload)
            version_id = chapter_row.world_version_id
            if version_id not in world_id_cache:
                world_id_cache[version_id] = self.get_world_version(version_id).world_id
            grouped_chapters.setdefault(chapter_row.session_id, []).append(
                {
                    "chapter_id": report.chapter_id,
                    "chapter_index": int(chapter_row.chapter_index),
                    "session_id": chapter_row.session_id,
                    "world_version_id": version_id,
                    "world_id": world_id_cache[version_id],
                    "report": report,
                    "session_updated_at": session_row.updated_at,
                    "session_status": session_row.status,
                }
            )

        continuation_samples: List[Dict[str, Any]] = []
        censored_count = 0
        censored_world_counts: Dict[str, int] = {}
        censored_version_counts: Dict[str, int] = {}
        for session_id, items in grouped_chapters.items():
            ordered = sorted(items, key=lambda item: int(item["chapter_index"]))
            for index, item in enumerate(ordered):
                continued_label: Optional[int]
                signal_source: str
                if index < len(ordered) - 1:
                    continued_label = 1
                    signal_source = "observed_next_chapter"
                else:
                    session_updated_at = _parse_timestamp(item.get("session_updated_at"))
                    session_status = str(item.get("session_status") or "active")
                    if session_status != "active" or session_updated_at <= stale_cutoff:
                        continued_label = 0
                        signal_source = "stale_session_tail"
                    else:
                        censored_count += 1
                        censored_world_counts[item["world_id"]] = censored_world_counts.get(item["world_id"], 0) + 1
                        censored_version_counts[item["world_version_id"]] = censored_version_counts.get(item["world_version_id"], 0) + 1
                        continue
                report = item["report"]
                issue_codes = {issue.issue_code for issue in report.issues}
                continuation_samples.append(
                    {
                        "session_id": session_id,
                        "chapter_id": item["chapter_id"],
                        "chapter_index": int(item["chapter_index"]),
                        "world_version_id": item["world_version_id"],
                        "world_id": item["world_id"],
                        "continued": continued_label,
                        "signal_source": signal_source,
                        "overall_score": float(report.scores.overall_score),
                        "readability": float(report.scores.readability),
                        "scene_density": float(report.scores.scene_density),
                        "character_fidelity": float(report.scores.character_fidelity),
                        "causal_continuity": float(report.scores.causal_continuity),
                        "pacing": float(report.scores.pacing),
                        "choice_distinctness": float(report.scores.choice_distinctness),
                        "hook_quality": float(report.scores.hook_quality),
                        "monetize_ready": float(report.scores.monetize_ready),
                        "issue_count": float(len(report.issues)),
                        "q03_present": 1.0 if "Q03" in issue_codes else 0.0,
                        "q04_present": 1.0 if "Q04" in issue_codes else 0.0,
                        "q05_present": 1.0 if "Q05" in issue_codes else 0.0,
                        "q09_present": 1.0 if "Q09" in issue_codes else 0.0,
                    }
                )

        metric_names = [
            "overall_score",
            "readability",
            "scene_density",
            "character_fidelity",
            "causal_continuity",
            "pacing",
            "choice_distinctness",
            "hook_quality",
            "monetize_ready",
            "issue_count",
            "q03_present",
            "q04_present",
            "q05_present",
            "q09_present",
        ]
        def _build_correlation_entries(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            correlations: List[Dict[str, Any]] = []
            for metric_name in metric_names:
                points = [
                    (float(item[metric_name]), float(item["continued"]))
                    for item in samples
                ]
                metric_values = [float(item[metric_name]) for item in samples]
                correlations.append(
                    {
                        "metric": metric_name,
                        "correlation": _pearson_correlation(points),
                        "sample_count": len(points),
                        "mean_metric": round(sum(metric_values) / float(max(1, len(metric_values))), 3) if metric_values else 0.0,
                        "positive_direction": metric_name not in {"issue_count", "q03_present", "q04_present", "q05_present", "q09_present"},
                    }
                )
            correlations.sort(key=lambda item: (-abs(float(item["correlation"])), item["metric"]))
            return correlations

        def _build_signal_summary(
            samples: List[Dict[str, Any]],
            *,
            censored: int,
            target_sample_count: Optional[int] = None,
        ) -> Dict[str, Any]:
            positive = sum(1 for item in samples if int(item["continued"]) == 1)
            negative = sum(1 for item in samples if int(item["continued"]) == 0)
            sample_count = len(samples)
            continuation_rate = round(
                positive / float(max(1, sample_count)),
                3,
            )
            summary = {
                "sample_count": sample_count,
                "positive_count": positive,
                "negative_count": negative,
                "censored_count": censored,
                "continuation_rate": continuation_rate,
                "stale_window_hours": CONTINUATION_STALE_WINDOW_HOURS,
            }
            if target_sample_count is not None:
                summary["target_sample_count"] = target_sample_count
                summary["sample_gap"] = max(0, int(target_sample_count) - int(sample_count))
                summary["recommended_action"] = _continuation_recommended_action(
                    sample_count=sample_count,
                    positive_count=positive,
                    negative_count=negative,
                    target_sample_count=int(target_sample_count),
                )
            return summary

        correlations = _build_correlation_entries(continuation_samples)
        overall_correlation = next((item["correlation"] for item in correlations if item["metric"] == "overall_score"), 0.0)
        aggregate["online_continuation_correlation"] = overall_correlation
        aggregate["continuation_signal_summary"] = {
            **_build_signal_summary(continuation_samples, censored=censored_count),
            "observed_continue_events": len(continue_events),
        }
        aggregate["quality_signal_correlations"] = correlations
        world_samples: Dict[str, List[Dict[str, Any]]] = {}
        version_samples: Dict[str, List[Dict[str, Any]]] = {}
        for item in continuation_samples:
            world_samples.setdefault(item["world_id"], []).append(item)
            version_samples.setdefault(item["world_version_id"], []).append(item)

        world_details: List[Dict[str, Any]] = []
        for current_world_id, samples in world_samples.items():
            world_correlations = _build_correlation_entries(samples)
            world_details.append(
                {
                    "world_id": current_world_id,
                    "world_version_ids": sorted({item["world_version_id"] for item in samples}),
                    "online_continuation_correlation": next(
                        (item["correlation"] for item in world_correlations if item["metric"] == "overall_score"),
                        0.0,
                    ),
                    "top_correlations": world_correlations[:3],
                    "quality_signal_correlations": world_correlations,
                    **_build_signal_summary(
                        samples,
                        censored=censored_world_counts.get(current_world_id, 0),
                        target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                    ),
                }
            )
        world_details.sort(
            key=lambda item: (
                item.get("recommended_action") == "coverage_sufficient",
                int(item.get("sample_gap", 0)),
                str(item.get("world_id")),
            )
        )

        version_details: List[Dict[str, Any]] = []
        for current_world_version_id, samples in version_samples.items():
            version_correlations = _build_correlation_entries(samples)
            version_details.append(
                {
                    "world_version_id": current_world_version_id,
                    "world_id": samples[0]["world_id"] if samples else "",
                    "online_continuation_correlation": next(
                        (item["correlation"] for item in version_correlations if item["metric"] == "overall_score"),
                        0.0,
                    ),
                    "top_correlations": version_correlations[:3],
                    "quality_signal_correlations": version_correlations,
                    **_build_signal_summary(
                        samples,
                        censored=censored_version_counts.get(current_world_version_id, 0),
                        target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_VERSION,
                    ),
                }
            )
        version_details.sort(
            key=lambda item: (
                item.get("recommended_action") == "coverage_sufficient",
                int(item.get("sample_gap", 0)),
                str(item.get("world_version_id")),
            )
        )

        aggregate["continuation_world_details"] = world_details
        aggregate["continuation_version_details"] = version_details
        aggregate["continuation_sample_accumulation"] = {
            "target_sample_count_per_world": CONTINUATION_TARGET_SAMPLES_PER_WORLD,
            "target_sample_count_per_version": CONTINUATION_TARGET_SAMPLES_PER_VERSION,
            "target_negative_samples": CONTINUATION_TARGET_NEGATIVE_SAMPLES,
            "worlds_below_target_count": sum(1 for item in world_details if int(item.get("sample_gap", 0)) > 0),
            "versions_below_target_count": sum(1 for item in version_details if int(item.get("sample_gap", 0)) > 0),
            "prioritized_worlds": [item for item in world_details if item.get("recommended_action") != "coverage_sufficient"][:5],
            "prioritized_versions": [item for item in version_details if item.get("recommended_action") != "coverage_sufficient"][:8],
        }
        return aggregate

    def record_analytics_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = AnalyticsEventRow(
                event_name=payload["event_name"],
                reader_id=payload.get("reader_id"),
                session_id=payload.get("session_id"),
                world_version_id=payload.get("world_version_id"),
                payload_json=dict(payload.get("payload_json", {})),
                occurred_at=payload.get("occurred_at", utcnow_iso()),
            )
            session.add(row)
            session.commit()
            return {
                "event_id": row.event_id,
                "event_name": row.event_name,
                "session_id": row.session_id,
                "world_version_id": row.world_version_id,
            }

    def list_analytics_events(
        self,
        *,
        event_names: Optional[List[str]] = None,
        reader_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        world_version_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AnalyticsEventRow).order_by(desc(AnalyticsEventRow.occurred_at))
            if event_names:
                stmt = stmt.where(AnalyticsEventRow.event_name.in_(event_names))
            if reader_id is not None:
                stmt = stmt.where(AnalyticsEventRow.reader_id == reader_id)
            if session_id is not None:
                stmt = stmt.where(AnalyticsEventRow.session_id == session_id)
            if world_version_id is not None:
                stmt = stmt.where(AnalyticsEventRow.world_version_id == world_version_id)
            if world_version_ids:
                stmt = stmt.where(AnalyticsEventRow.world_version_id.in_(world_version_ids))
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "event_id": row.event_id,
                    "event_name": row.event_name,
                    "reader_id": row.reader_id,
                    "session_id": row.session_id,
                    "world_version_id": row.world_version_id,
                    "payload_json": dict(row.payload_json or {}),
                    "occurred_at": row.occurred_at,
                }
                for row in rows
            ]
