from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from sqlalchemy import JSON, Boolean, Column, Float, Index, Integer, String, Text, UniqueConstraint, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


PlatformBase = declarative_base()
BASE_DIR = Path(__file__).resolve().parents[3]
POSTGRES_SCHEMA_PATH = BASE_DIR / "db" / "postgres_schema.sql"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorldRow(PlatformBase):
    __tablename__ = "worlds"

    world_id = Column(String, primary_key=True)
    latest_version = Column(String, nullable=True)
    title = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="draft")
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class WorldVersionRow(PlatformBase):
    __tablename__ = "world_versions"

    world_version_id = Column(String, primary_key=True)
    world_id = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    risk_rating = Column(String, nullable=True)
    manifest_json = Column(JSON, nullable=False)
    worldpack_json = Column(JSON, nullable=False)
    validation_report_json = Column(JSON, nullable=True)
    simulation_report_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class SessionRow(PlatformBase):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("idx_sessions_world_version_updated_at", "world_version_id", "updated_at"),
        Index("idx_sessions_reader_updated_at", "reader_id", "updated_at"),
        Index("idx_sessions_status_updated_at", "status", "updated_at"),
    )

    session_id = Column(String, primary_key=True)
    reader_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active")
    chapter_index = Column(Integer, nullable=False, default=0)
    story_phase = Column(String, nullable=True)
    narrative_state_json = Column(JSON, nullable=False)
    entitlements_snapshot_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ChapterRow(PlatformBase):
    __tablename__ = "chapters"
    __table_args__ = (
        Index("idx_chapters_session_chapter_index", "session_id", "chapter_index"),
        Index("idx_chapters_world_version_created_at", "world_version_id", "created_at"),
    )

    chapter_id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)
    plan_json = Column(JSON, nullable=True)
    rendered_body = Column(Text, nullable=True)
    choices_json = Column(JSON, nullable=True)
    cost_estimate = Column(Float, nullable=True)
    review_flags_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class RouteChoiceRow(PlatformBase):
    __tablename__ = "route_choices"

    choice_event_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    chapter_id = Column(String, nullable=False, index=True)
    choice_id = Column(String, nullable=False)
    selected_at = Column(String, nullable=False, default=utcnow_iso)
    payload_json = Column(JSON, nullable=True)


class EntitlementRow(PlatformBase):
    __tablename__ = "entitlements"

    entitlement_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    reader_id = Column(String, nullable=False, index=True)
    world_id = Column(String, nullable=True, index=True)
    entitlement_type = Column(String, nullable=False)
    wallet_type = Column(String, nullable=True)
    tier_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    balance = Column(Float, nullable=True)
    expires_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class SubscriptionRow(PlatformBase):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("idx_subscriptions_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    subscription_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    tier_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_ref = Column(String, nullable=True)
    status = Column(String, nullable=False, default="trialing")
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    cancel_at_period_end = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class UsageMeterRow(PlatformBase):
    __tablename__ = "usage_meters"
    __table_args__ = (
        Index("idx_usage_meters_account_created_at", "account_id", "created_at"),
        Index("idx_usage_meters_session_created_at", "session_id", "created_at"),
        Index("idx_usage_meters_world_version_created_at", "world_version_id", "created_at"),
    )

    meter_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    reader_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    chapter_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    action_type = Column(String, nullable=False)
    usage_units = Column(Float, nullable=False)
    estimated_cost = Column(Float, nullable=True)
    wallet_type = Column(String, nullable=True)
    subscription_tier = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model_policy_version = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ReviewRecordRow(PlatformBase):
    __tablename__ = "review_records"
    __table_args__ = (
        Index("idx_review_records_asset_type_status_updated_at", "asset_type", "status", "updated_at"),
        Index("idx_review_records_asset_type_asset_id_updated_at", "asset_type", "asset_id", "updated_at"),
        Index("idx_review_records_reviewer_updated_at", "reviewer_id", "updated_at"),
    )

    review_id = Column(String, primary_key=True)
    asset_type = Column(String, nullable=False)
    asset_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=True)
    risk_rating = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorCommentThreadRow(PlatformBase):
    __tablename__ = "author_comment_threads"

    thread_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, index=True)
    revision_id = Column(String, nullable=True, index=True)
    anchor_type = Column(String, nullable=False)
    anchor_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="open")
    severity = Column(String, nullable=False, default="normal")
    assignee_id = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorCommentMessageRow(PlatformBase):
    __tablename__ = "author_comment_messages"

    message_id = Column(String, primary_key=True)
    thread_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorApprovalRecordRow(PlatformBase):
    __tablename__ = "author_approval_records"

    approval_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, index=True)
    revision_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorNotificationRow(PlatformBase):
    __tablename__ = "author_notifications"

    notification_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=True, index=True)
    approval_id = Column(String, nullable=True, index=True)
    recipient_id = Column(String, nullable=False, index=True)
    recipient_role = Column(String, nullable=False, default="reviewer")
    notification_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="unread")
    actor_id = Column(String, nullable=True)
    actor_role = Column(String, nullable=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    anchor_type = Column(String, nullable=True)
    anchor_key = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    read_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorThreadWatcherRow(PlatformBase):
    __tablename__ = "author_thread_watchers"

    watcher_record_id = Column(String, primary_key=True)
    thread_id = Column(String, nullable=False, index=True)
    watcher_id = Column(String, nullable=False, index=True)
    added_by = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorDraftWatcherRow(PlatformBase):
    __tablename__ = "author_draft_watchers"

    watcher_record_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, index=True)
    watcher_id = Column(String, nullable=False, index=True)
    added_by = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorNotificationPreferenceRow(PlatformBase):
    __tablename__ = "author_notification_preferences"

    preference_id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    notification_type = Column(String, nullable=False, index=True)
    in_app_enabled = Column(String, nullable=False, default="true")
    async_mirror_enabled = Column(String, nullable=False, default="true")
    async_sink_name = Column(String, nullable=True)
    delivery_target = Column(String, nullable=True)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ShowcaseWorkLikeRow(PlatformBase):
    __tablename__ = "showcase_work_likes"
    __table_args__ = (
        UniqueConstraint("world_id", "account_id", name="uq_showcase_work_likes_world_account"),
        Index("idx_showcase_work_likes_world_created_at", "world_id", "created_at"),
        Index("idx_showcase_work_likes_account_created_at", "account_id", "created_at"),
    )

    showcase_like_id = Column(String, primary_key=True)
    world_id = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ShowcaseWorkCommentRow(PlatformBase):
    __tablename__ = "showcase_work_comments"
    __table_args__ = (
        Index("idx_showcase_work_comments_world_status_created_at", "world_id", "status", "created_at"),
        Index("idx_showcase_work_comments_account_created_at", "account_id", "created_at"),
    )

    showcase_comment_id = Column(String, primary_key=True)
    world_id = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=True)
    author_name = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="published", index=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ShowcaseWorkTipRow(PlatformBase):
    __tablename__ = "showcase_work_tips"
    __table_args__ = (
        Index("idx_showcase_work_tips_world_created_at", "world_id", "created_at"),
        Index("idx_showcase_work_tips_account_created_at", "account_id", "created_at"),
    )

    showcase_tip_id = Column(String, primary_key=True)
    world_id = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=False, default=0)
    wallet_type = Column(String, nullable=False, default="story_credits")
    balance_after = Column(Float, nullable=False, default=0.0)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class StorySessionBookmarkRow(PlatformBase):
    __tablename__ = "story_session_bookmarks"
    __table_args__ = (
        UniqueConstraint("session_id", "account_id", "node_id", name="uq_story_session_bookmarks_session_account_node"),
        Index("idx_story_session_bookmarks_session_created_at", "session_id", "created_at"),
        Index("idx_story_session_bookmarks_account_created_at", "account_id", "created_at"),
    )

    bookmark_id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    node_id = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class StorySessionShareTokenRow(PlatformBase):
    __tablename__ = "story_session_share_tokens"
    __table_args__ = (
        Index("idx_story_session_share_tokens_token_created_at", "share_token", "created_at"),
        Index("idx_story_session_share_tokens_session_created_at", "session_id", "created_at"),
        Index("idx_story_session_share_tokens_account_created_at", "account_id", "created_at"),
        Index(
            "idx_story_session_share_tokens_session_account_node_status",
            "session_id",
            "account_id",
            "node_id",
            "status",
        ),
    )

    share_token = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    node_id = Column(String, nullable=False)
    sharer_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    expires_at = Column(String, nullable=True)
    revoked_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class SoulProfilePreferenceRow(PlatformBase):
    __tablename__ = "soul_profile_preferences"
    __table_args__ = (
        Index("idx_soul_profile_preferences_account_updated_at", "account_id", "updated_at"),
    )

    actor_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    genres_json = Column(JSON, nullable=False, default=list)
    styles_json = Column(JSON, nullable=False, default=list)
    privacy_mode = Column(String, nullable=False, default="followers")
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class LibraryWorkFavoriteRow(PlatformBase):
    __tablename__ = "library_work_favorites"
    __table_args__ = (
        UniqueConstraint("account_id", "work_id", name="uq_library_work_favorites_account_work"),
        Index("idx_library_work_favorites_account_created_at", "account_id", "created_at"),
        Index("idx_library_work_favorites_work_created_at", "work_id", "created_at"),
    )

    favorite_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    work_id = Column(String, nullable=False, index=True)
    work_kind = Column(String, nullable=False)
    title_snapshot = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class LibraryFollowRow(PlatformBase):
    __tablename__ = "library_follows"
    __table_args__ = (
        UniqueConstraint("account_id", "target_type", "target_id", name="uq_library_follows_account_target"),
        Index("idx_library_follows_account_created_at", "account_id", "created_at"),
        Index("idx_library_follows_target_created_at", "target_type", "target_id", "created_at"),
    )

    follow_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False, index=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class LibraryStatsCubeRow(PlatformBase):
    __tablename__ = "library_stats_cubes"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_library_stats_cubes_account"),
        Index("idx_library_stats_cubes_account_updated_at", "account_id", "updated_at"),
        Index("idx_library_stats_cubes_source_updated_at", "source_updated_at"),
        Index("idx_library_stats_cubes_invalidated_at", "invalidated_at"),
    )

    library_stats_cube_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    semantic_version = Column(String, nullable=False, default="library_stats_semantic/v2")
    snapshot_payload_json = Column(JSON, nullable=False, default=dict)
    source_breakdown_json = Column(JSON, nullable=False, default=dict)
    source_updated_at = Column(String, nullable=False, default=utcnow_iso)
    invalidated_at = Column(String, nullable=True)
    last_invalidated_event_name = Column(String, nullable=True)
    last_invalidated_event_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ShowcaseWorkViewRow(PlatformBase):
    __tablename__ = "showcase_work_views"
    __table_args__ = (
        UniqueConstraint("world_id", "viewer_key", "event_type", name="uq_showcase_work_views_world_viewer_event"),
        Index("idx_showcase_work_views_world_event_created_at", "world_id", "event_type", "created_at"),
        Index("idx_showcase_work_views_account_event_created_at", "account_id", "event_type", "created_at"),
    )

    showcase_view_id = Column(String, primary_key=True)
    world_id = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    viewer_key = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, default="view", index=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class GeneratedMediaAssetRow(PlatformBase):
    __tablename__ = "generated_media_assets"
    __table_args__ = (
        Index(
            "idx_generated_media_assets_owner_kind_status_updated_at",
            "owner_scope",
            "owner_id",
            "asset_kind",
            "generation_status",
            "updated_at",
        ),
        Index(
            "idx_generated_media_assets_world_kind_status_updated_at",
            "world_version_id",
            "asset_kind",
            "generation_status",
            "updated_at",
        ),
        Index(
            "idx_generated_media_assets_owner_fingerprint",
            "owner_scope",
            "owner_id",
            "asset_kind",
            "source_fingerprint",
        ),
    )

    asset_id = Column(String, primary_key=True)
    asset_kind = Column(String, nullable=False, index=True)
    owner_scope = Column(String, nullable=False, index=True)
    owner_id = Column(String, nullable=False, index=True)
    world_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    chapter_index = Column(Integer, nullable=True)
    reader_id = Column(String, nullable=True, index=True)
    storage_bucket = Column(String, nullable=True)
    storage_key = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    visibility = Column(String, nullable=False, default="private", index=True)
    generation_status = Column(String, nullable=False, default="queued", index=True)
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    source_fingerprint = Column(String, nullable=True, index=True)
    prompt_trace_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorProjectGraphRow(PlatformBase):
    __tablename__ = "author_project_graphs"
    __table_args__ = (
        Index("idx_author_project_graphs_account_updated_at", "account_id", "updated_at"),
        Index("idx_author_project_graphs_world_version_updated_at", "world_version_id", "updated_at"),
    )

    project_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, unique=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    engine = Column(String, nullable=False, default="balanced")
    enabled_rule_ids_json = Column(JSON, nullable=False, default=list)
    nodes_json = Column(JSON, nullable=False, default=list)
    connections_json = Column(JSON, nullable=False, default=list)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthIdentityRow(PlatformBase):
    __tablename__ = "auth_identities"

    actor_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    actor_role = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorWorkRow(PlatformBase):
    __tablename__ = "author_works"
    __table_args__ = (
        Index("idx_author_works_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_author_works_world_version_updated_at", "world_version_id", "updated_at"),
        Index("idx_author_works_root_work_updated_at", "root_work_id", "updated_at"),
    )

    work_id = Column(String, primary_key=True)
    world_version_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    current_revision = Column(String, nullable=True)
    chapter_count = Column(Integer, nullable=False, default=0)
    target_chapter_count = Column(Integer, nullable=False, default=0)
    branch_id = Column(String, nullable=True, index=True)
    root_work_id = Column(String, nullable=True, index=True)
    parent_work_id = Column(String, nullable=True, index=True)
    branch_name = Column(String, nullable=True)
    branch_kind = Column(String, nullable=True)
    branch_origin_label = Column(Text, nullable=True)
    fork_after_chapter_index = Column(Integer, nullable=True)
    is_active_line = Column(Integer, nullable=False, default=0)
    narrative_state_json = Column(JSON, nullable=True)
    diagnostics_summary_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorWorkChapterRow(PlatformBase):
    __tablename__ = "author_work_chapters"
    __table_args__ = (
        Index("idx_author_work_chapters_work_chapter", "work_id", "chapter_index"),
    )

    chapter_record_id = Column(String, primary_key=True)
    work_id = Column(String, nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)
    chapter_title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="generated")
    source_type = Column(String, nullable=False, default="generated")
    summary = Column(Text, nullable=True)
    diagnostic_summary_json = Column(JSON, nullable=True)
    chapter_task_json = Column(JSON, nullable=True)
    choices_json = Column(JSON, nullable=True)
    state_snapshot_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthorWorkRevisionRow(PlatformBase):
    __tablename__ = "author_work_revisions"
    __table_args__ = (
        Index("idx_author_work_revisions_work_created_at", "work_id", "created_at"),
    )

    revision_id = Column(String, primary_key=True)
    work_id = Column(String, nullable=False, index=True)
    revision_type = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    snapshot_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class AuthTokenRow(PlatformBase):
    __tablename__ = "auth_tokens"

    token_id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    actor_role = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(String, nullable=False, default=utcnow_iso)
    expires_at = Column(String, nullable=True)
    last_used_at = Column(String, nullable=True)


class AuthIdentityProfileRow(PlatformBase):
    __tablename__ = "auth_identity_profiles"

    actor_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    email_address = Column(String, nullable=True, index=True)
    pending_email_address = Column(String, nullable=True, index=True)
    avatar_url = Column(String, nullable=True)
    email_verified = Column(String, nullable=False, default="false")
    verification_required = Column(String, nullable=False, default="false")
    verification_sent_at = Column(String, nullable=True)
    verified_at = Column(String, nullable=True)
    password_reset_sent_at = Column(String, nullable=True)
    pending_email_change_requested_at = Column(String, nullable=True)
    email_change_last_sent_at = Column(String, nullable=True)
    ui_preferences_json = Column(JSON, nullable=True)
    deactivated_at = Column(String, nullable=True)
    deactivated_by = Column(String, nullable=True)
    deactivation_reason = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthFlowTokenRow(PlatformBase):
    __tablename__ = "auth_flow_tokens"

    flow_token_id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    flow_type = Column(String, nullable=False, index=True)
    token_hash = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active")
    payload_json = Column(JSON, nullable=True)
    expires_at = Column(String, nullable=True)
    consumed_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuthDeliveryAttemptRow(PlatformBase):
    __tablename__ = "auth_delivery_attempts"
    __table_args__ = (
        Index("idx_auth_delivery_attempts_actor_flow_created_at", "actor_id", "flow_type", "created_at"),
        Index("idx_auth_delivery_attempts_recipient_created_at", "recipient_email", "created_at"),
        Index("idx_auth_delivery_attempts_status_created_at", "status", "created_at"),
    )

    attempt_id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=True, index=True)
    flow_type = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    email_mode = Column(String, nullable=False)
    sender_email = Column(String, nullable=True)
    recipient_email = Column(String, nullable=False)
    status = Column(String, nullable=False)
    provider_message_id = Column(String, nullable=True, index=True)
    error_code = Column(String, nullable=True, index=True)
    error_reason = Column(Text, nullable=True)
    retryable = Column(String, nullable=False, default="false")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class BillingRetryAttemptRow(PlatformBase):
    __tablename__ = "billing_retry_attempts"

    retry_attempt_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True, index=True)
    subscription_id = Column(String, nullable=True, index=True)
    checkout_session_id = Column(String, nullable=True, index=True)
    source_event_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="planned")
    retry_reason = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    next_retry_at = Column(String, nullable=True)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class BillingCheckoutSessionRow(PlatformBase):
    __tablename__ = "billing_checkout_sessions"

    checkout_session_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    checkout_kind = Column(String, nullable=False, default="subscription")
    tier_id = Column(String, nullable=False)
    package_id = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=False)
    provider_ref = Column(String, nullable=True, index=True)
    subscription_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="created")
    checkout_url = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, index=True)
    expires_at = Column(String, nullable=True)
    fulfilled_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class BillingLifecycleEventRow(PlatformBase):
    __tablename__ = "billing_lifecycle_events"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_event_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    subscription_id = Column(String, nullable=True, index=True)
    checkout_session_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="received")
    payload_json = Column(JSON, nullable=True)
    processing_result = Column(JSON, nullable=True)
    occurred_at = Column(String, nullable=False, default=utcnow_iso)
    processed_at = Column(String, nullable=True)


class ProviderSubscriptionRow(PlatformBase):
    __tablename__ = "provider_subscriptions"
    __table_args__ = (
        Index("idx_provider_subscriptions_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_provider_subscriptions_provider_ref", "provider", "provider_ref"),
    )

    provider_subscription_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    tier_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_ref = Column(String, nullable=True)
    provider_customer_id = Column(String, nullable=True, index=True)
    provider_checkout_session_id = Column(String, nullable=True, index=True)
    provider_order_id = Column(String, nullable=True, index=True)
    environment = Column(String, nullable=False, default="test")
    verification_status = Column(String, nullable=False, default="pending")
    last_verified_at = Column(String, nullable=True)
    status = Column(String, nullable=False, default="trialing")
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    cancel_at_period_end = Column(String, nullable=True)
    latest_event_id = Column(String, nullable=True, index=True)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AnalyticsEventRow(PlatformBase):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("idx_analytics_events_event_name_occurred_at", "event_name", "occurred_at"),
        Index("idx_analytics_events_session_occurred_at", "session_id", "occurred_at"),
        Index("idx_analytics_events_world_version_occurred_at", "world_version_id", "occurred_at"),
    )

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    event_name = Column(String, nullable=False)
    reader_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    payload_json = Column(JSON, nullable=True)
    occurred_at = Column(String, nullable=False, default=utcnow_iso)


class OpsReviewItemRow(PlatformBase):
    __tablename__ = "ops_review_items"
    __table_args__ = (
        Index("idx_ops_review_items_queue_status_priority_updated_at", "queue", "status", "priority", "updated_at"),
        Index("idx_ops_review_items_owner_status_updated_at", "owner_id", "status", "updated_at"),
        Index("idx_ops_review_items_source_type_source_id", "source_type", "source_id"),
        Index("idx_ops_review_items_account_queue_updated_at", "account_id", "queue", "updated_at"),
        Index("idx_ops_review_items_world_queue_updated_at", "world_id", "queue", "updated_at"),
        Index("idx_ops_review_items_world_version_queue_updated_at", "world_version_id", "queue", "updated_at"),
    )

    review_item_id = Column(String, primary_key=True)
    source_type = Column(String, nullable=False, index=True)
    source_id = Column(String, nullable=False, index=True)
    queue = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="new")
    severity = Column(String, nullable=False, default="medium")
    priority = Column(Integer, nullable=False, default=100)
    owner_id = Column(String, nullable=True, index=True)
    reviewer_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=True, index=True)
    world_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    headline = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    recommended_action = Column(String, nullable=True)
    due_at = Column(String, nullable=True, index=True)
    sla_bucket = Column(String, nullable=True, index=True)
    allowed_actions_json = Column(JSON, nullable=True)
    linked_entities_json = Column(JSON, nullable=True)
    source_updated_at = Column(String, nullable=True)
    last_synced_at = Column(String, nullable=False, default=utcnow_iso)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class QualityPolicyRow(PlatformBase):
    __tablename__ = "quality_policies"
    __table_args__ = (
        Index("idx_quality_policies_scenario_risk_updated_at", "scenario_id", "risk_tier", "updated_at"),
        Index("idx_quality_policies_mode_updated_at", "mode", "updated_at"),
    )

    policy_id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    scenario_id = Column(String, nullable=False, index=True)
    risk_tier = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False, index=True)
    rule_ids_json = Column(JSON, nullable=False)
    policy_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class OpsConfigRow(PlatformBase):
    __tablename__ = "ops_configs"
    __table_args__ = (
        Index("idx_ops_configs_type_scope_updated_at", "config_type", "scope_key", "updated_at"),
        Index("idx_ops_configs_status_updated_at", "status", "updated_at"),
    )

    ops_config_id = Column(String, primary_key=True)
    config_type = Column(String, nullable=False, index=True)
    scope_key = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    config_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class QualityEventRow(PlatformBase):
    __tablename__ = "quality_events"
    __table_args__ = (
        Index("idx_quality_events_trace_created_at", "trace_id", "created_at"),
        Index("idx_quality_events_surface_status_created_at", "source_surface", "status", "created_at"),
        Index("idx_quality_events_world_created_at", "world_version_id", "created_at"),
        Index("idx_quality_events_session_created_at", "session_id", "created_at"),
    )

    event_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    source_surface = Column(String, nullable=False, index=True)
    status = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    source_ref_json = Column(JSON, nullable=False)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ContentQualityScoreRow(PlatformBase):
    __tablename__ = "content_quality_scores"
    __table_args__ = (
        Index("idx_content_quality_scores_trace_created_at", "trace_id", "created_at"),
        Index("idx_content_quality_scores_status_created_at", "status", "created_at"),
        Index("idx_content_quality_scores_world_created_at", "world_version_id", "created_at"),
        Index("idx_content_quality_scores_session_created_at", "session_id", "created_at"),
    )

    score_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=True, index=True)
    source_surface = Column(String, nullable=False, index=True)
    status = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    chapter_id = Column(String, nullable=True, index=True)
    rubric_version = Column(String, nullable=False)
    overall_score = Column(Float, nullable=False, default=0.0)
    veto = Column(Boolean, nullable=False, default=False)
    dimension_scores_json = Column(JSON, nullable=False)
    reason_codes_json = Column(JSON, nullable=False)
    evidence_refs_json = Column(JSON, nullable=False)
    score_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ReviewCaseRow(PlatformBase):
    __tablename__ = "review_cases"
    __table_args__ = (
        Index("idx_review_cases_status_updated_at", "status", "updated_at"),
        Index("idx_review_cases_trace_updated_at", "trace_id", "updated_at"),
        Index("idx_review_cases_world_status_updated_at", "world_version_id", "status", "updated_at"),
        Index("idx_review_cases_session_status_updated_at", "session_id", "status", "updated_at"),
    )

    case_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=True, index=True)
    case_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    owner_id = Column(String, nullable=True, index=True)
    source_surface = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    score_id = Column(String, nullable=True, index=True)
    source_ref_json = Column(JSON, nullable=False)
    reason_codes_json = Column(JSON, nullable=False)
    evidence_refs_json = Column(JSON, nullable=False)
    case_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class QualityFeedbackItemRow(PlatformBase):
    __tablename__ = "quality_feedback_items"
    __table_args__ = (
        Index("idx_quality_feedback_items_trace_created_at", "trace_id", "created_at"),
        Index("idx_quality_feedback_items_account_created_at", "account_id", "created_at"),
        Index("idx_quality_feedback_items_session_created_at", "session_id", "created_at"),
        Index("idx_quality_feedback_items_type_signal_created_at", "feedback_type", "signal", "created_at"),
    )

    feedback_item_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=True, index=True)
    source_event_id = Column(String, nullable=True, index=True)
    feedback_type = Column(String, nullable=False, index=True)
    signal = Column(String, nullable=False, index=True)
    source_surface = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    chapter_id = Column(String, nullable=True, index=True)
    source_ref_json = Column(JSON, nullable=False)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class GroundingCheckRow(PlatformBase):
    __tablename__ = "grounding_checks"
    __table_args__ = (
        Index("idx_grounding_checks_trace_created_at", "trace_id", "created_at"),
        Index("idx_grounding_checks_status_created_at", "status", "created_at"),
        Index("idx_grounding_checks_world_created_at", "world_version_id", "created_at"),
        Index("idx_grounding_checks_session_created_at", "session_id", "created_at"),
    )

    grounding_check_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    source_surface = Column(String, nullable=False, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    chapter_id = Column(String, nullable=True, index=True)
    evidence_refs_json = Column(JSON, nullable=False)
    unsupported_claims_json = Column(JSON, nullable=False)
    reason_codes_json = Column(JSON, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class PlanRow(PlatformBase):
    __tablename__ = "plans"
    __table_args__ = (
        Index("idx_plans_status_updated_at", "status", "updated_at"),
    )

    plan_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    subscription_tier = Column(String, nullable=False, index=True)
    monthly_price_usd = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="active", index=True)
    seat_limit = Column(Integer, nullable=False, default=0)
    workspace_limit = Column(Integer, nullable=False, default=0)
    campaign_limit = Column(Integer, nullable=False, default=0)
    plan_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CustomerAccountRow(PlatformBase):
    __tablename__ = "customer_accounts"
    __table_args__ = (
        Index("idx_customer_accounts_status_updated_at", "status", "updated_at"),
        Index("idx_customer_accounts_plan_status_updated_at", "plan_id", "status", "updated_at"),
        Index("idx_customer_accounts_renewal_due_at", "renewal_due_at"),
    )

    customer_account_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="trial", index=True)
    plan_id = Column(String, nullable=False, index=True)
    seat_limit = Column(Integer, nullable=False, default=0)
    workspace_limit = Column(Integer, nullable=False, default=0)
    campaign_limit = Column(Integer, nullable=False, default=0)
    seat_count = Column(Integer, nullable=False, default=0)
    workspace_count = Column(Integer, nullable=False, default=0)
    campaign_count = Column(Integer, nullable=False, default=0)
    renewal_due_at = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class BillingProfileRow(PlatformBase):
    __tablename__ = "billing_profiles"
    __table_args__ = (
        Index("idx_billing_profiles_customer_updated_at", "customer_account_id", "updated_at"),
        Index("idx_billing_profiles_account_updated_at", "account_id", "updated_at"),
        Index("idx_billing_profiles_provider_status_updated_at", "provider", "status", "updated_at"),
    )

    billing_profile_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    provider_customer_ref = Column(String, nullable=True, index=True)
    invoice_email = Column(String, nullable=True)
    legal_name = Column(String, nullable=True)
    billing_country = Column(String, nullable=True)
    tax_status = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    profile_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class UsageLedgerRow(PlatformBase):
    __tablename__ = "usage_ledgers"
    __table_args__ = (
        Index("idx_usage_ledgers_account_period_updated_at", "account_id", "billing_period_start", "updated_at"),
        Index("idx_usage_ledgers_customer_period_updated_at", "customer_account_id", "billing_period_start", "updated_at"),
        Index("idx_usage_ledgers_status_updated_at", "status", "updated_at"),
    )

    usage_ledger_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    plan_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="open", index=True)
    billing_period_start = Column(String, nullable=False, index=True)
    billing_period_end = Column(String, nullable=False, index=True)
    presented_count = Column(Integer, nullable=False, default=0)
    handoff_count = Column(Integer, nullable=False, default=0)
    conversion_count = Column(Integer, nullable=False, default=0)
    subtotal_amount_usd = Column(Float, nullable=False, default=0.0)
    disputed_amount_usd = Column(Float, nullable=False, default=0.0)
    credited_amount_usd = Column(Float, nullable=False, default=0.0)
    reversed_amount_usd = Column(Float, nullable=False, default=0.0)
    ledger_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class BillableEventRow(PlatformBase):
    __tablename__ = "billable_events"
    __table_args__ = (
        Index("idx_billable_events_account_created_at", "account_id", "created_at"),
        Index("idx_billable_events_customer_created_at", "customer_account_id", "created_at"),
        Index("idx_billable_events_trace_created_at", "trace_id", "created_at"),
        Index("idx_billable_events_metric_status_created_at", "billable_metric", "status", "created_at"),
    )

    billable_event_id = Column(String, primary_key=True)
    usage_ledger_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    plan_id = Column(String, nullable=True, index=True)
    billable_metric = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="recorded", index=True)
    trace_id = Column(String, nullable=True, index=True)
    quality_event_id = Column(String, nullable=True, index=True)
    runtime_receipt_event_id = Column(String, nullable=True, index=True)
    feedback_item_id = Column(String, nullable=True, index=True)
    source_surface = Column(String, nullable=True, index=True)
    world_version_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    quantity = Column(Float, nullable=False, default=1.0)
    unit_price_usd = Column(Float, nullable=False, default=0.0)
    amount_usd = Column(Float, nullable=False, default=0.0)
    reason_codes_json = Column(JSON, nullable=False)
    event_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class InvoicePreviewRow(PlatformBase):
    __tablename__ = "invoice_previews"
    __table_args__ = (
        Index("idx_invoice_previews_account_period_updated_at", "account_id", "billing_period_start", "updated_at"),
        Index("idx_invoice_previews_customer_period_updated_at", "customer_account_id", "billing_period_start", "updated_at"),
    )

    invoice_preview_id = Column(String, primary_key=True)
    usage_ledger_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    plan_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    billing_period_start = Column(String, nullable=False, index=True)
    billing_period_end = Column(String, nullable=False, index=True)
    subtotal_amount_usd = Column(Float, nullable=False, default=0.0)
    credits_applied_usd = Column(Float, nullable=False, default=0.0)
    disputed_amount_usd = Column(Float, nullable=False, default=0.0)
    credited_amount_usd = Column(Float, nullable=False, default=0.0)
    reversed_amount_usd = Column(Float, nullable=False, default=0.0)
    total_due_usd = Column(Float, nullable=False, default=0.0)
    line_items_json = Column(JSON, nullable=False)
    summary_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CreditBalanceRow(PlatformBase):
    __tablename__ = "credit_balances"
    __table_args__ = (
        Index("idx_credit_balances_account_updated_at", "account_id", "updated_at"),
        Index("idx_credit_balances_customer_updated_at", "customer_account_id", "updated_at"),
        Index("idx_credit_balances_type_updated_at", "balance_type", "updated_at"),
    )

    credit_balance_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    balance_type = Column(String, nullable=False, index=True)
    amount_usd = Column(Float, nullable=False, default=0.0)
    source_ref_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class OverageFlagRow(PlatformBase):
    __tablename__ = "overage_flags"
    __table_args__ = (
        Index("idx_overage_flags_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_overage_flags_metric_status_updated_at", "metric_type", "status", "updated_at"),
    )

    overage_flag_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    plan_id = Column(String, nullable=True, index=True)
    metric_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    observed_units = Column(Float, nullable=False, default=0.0)
    included_units = Column(Float, nullable=False, default=0.0)
    overage_units = Column(Float, nullable=False, default=0.0)
    flag_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CampaignRow(PlatformBase):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("idx_campaigns_account_status_updated_at", "account_id", "activation_status", "updated_at"),
        Index("idx_campaigns_customer_status_updated_at", "customer_account_id", "activation_status", "updated_at"),
    )

    campaign_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    target_icp_vertical = Column(String, nullable=False)
    cta_text = Column(String, nullable=False)
    disclosure_text = Column(Text, nullable=False)
    activation_status = Column(String, nullable=False, default="draft", index=True)
    selected_channels_json = Column(JSON, nullable=False)
    selected_partner_refs_json = Column(JSON, nullable=False)
    primary_review_case_id = Column(String, nullable=True, index=True)
    latest_submission_id = Column(String, nullable=True, index=True)
    campaign_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CampaignProofBundleRow(PlatformBase):
    __tablename__ = "campaign_proof_bundles"
    __table_args__ = (
        Index("idx_campaign_proof_bundles_campaign_updated_at", "campaign_id", "updated_at"),
    )

    proof_bundle_id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=False, index=True)
    bundle_label = Column(String, nullable=False, default="default")
    proof_points_json = Column(JSON, nullable=False)
    source_urls_json = Column(JSON, nullable=False)
    artifact_refs_json = Column(JSON, nullable=False)
    bundle_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CampaignChannelTargetRow(PlatformBase):
    __tablename__ = "campaign_channel_targets"
    __table_args__ = (
        Index("idx_campaign_channel_targets_campaign_priority_updated_at", "campaign_id", "priority", "updated_at"),
    )

    channel_target_id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=False, index=True)
    channel_name = Column(String, nullable=False, index=True)
    partner_ref = Column(String, nullable=True, index=True)
    priority = Column(Integer, nullable=False, default=0)
    readiness_status = Column(String, nullable=False, default="selected")
    target_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class CampaignReviewSubmissionRow(PlatformBase):
    __tablename__ = "campaign_review_submissions"
    __table_args__ = (
        Index("idx_campaign_review_submissions_campaign_updated_at", "campaign_id", "updated_at"),
        Index("idx_campaign_review_submissions_review_case_updated_at", "review_case_id", "updated_at"),
        Index("idx_campaign_review_submissions_status_updated_at", "status", "updated_at"),
    )

    submission_id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=False, index=True)
    review_case_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="submitted", index=True)
    submitted_by = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=True, index=True)
    decision_note = Column(Text, nullable=True)
    submitted_at = Column(String, nullable=False, default=utcnow_iso)
    decided_at = Column(String, nullable=True)
    submission_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class PartnerRow(PlatformBase):
    __tablename__ = "partners"
    __table_args__ = (
        Index("idx_partners_lifecycle_updated_at", "lifecycle_status", "updated_at"),
        Index("idx_partners_endpoint_health_updated_at", "endpoint_health_status", "updated_at"),
    )

    partner_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    lifecycle_status = Column(String, nullable=False, default="discovered", index=True)
    sla_status = Column(String, nullable=False, default="unknown")
    receipt_capability = Column(String, nullable=False, default="unknown")
    disclosure_readiness = Column(String, nullable=False, default="unknown")
    billing_readiness = Column(String, nullable=False, default="unknown")
    allowlisted_channels_json = Column(JSON, nullable=False)
    primary_endpoint_url = Column(String, nullable=True)
    endpoint_health_status = Column(String, nullable=False, default="unknown", index=True)
    partner_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class PartnerCapabilityRow(PlatformBase):
    __tablename__ = "partner_capabilities"
    __table_args__ = (
        Index("idx_partner_capabilities_partner_updated_at", "partner_id", "updated_at"),
        Index("idx_partner_capabilities_type_status_updated_at", "capability_type", "status", "updated_at"),
    )

    partner_capability_id = Column(String, primary_key=True)
    partner_id = Column(String, nullable=False, index=True)
    capability_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="unknown", index=True)
    capability_value = Column(String, nullable=True)
    capability_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class PartnerHealthCheckRow(PlatformBase):
    __tablename__ = "partner_health_checks"
    __table_args__ = (
        Index("idx_partner_health_checks_partner_checked_at", "partner_id", "checked_at"),
        Index("idx_partner_health_checks_status_checked_at", "status", "checked_at"),
    )

    health_check_id = Column(String, primary_key=True)
    partner_id = Column(String, nullable=False, index=True)
    endpoint_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="unknown", index=True)
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    checked_at = Column(String, nullable=False, default=utcnow_iso)
    health_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class DisputeRow(PlatformBase):
    __tablename__ = "disputes"
    __table_args__ = (
        Index("idx_disputes_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_disputes_customer_status_updated_at", "customer_account_id", "status", "updated_at"),
        Index("idx_disputes_billable_event_updated_at", "billable_event_id", "updated_at"),
    )

    dispute_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    campaign_id = Column(String, nullable=True, index=True)
    invoice_preview_id = Column(String, nullable=True, index=True)
    billable_event_id = Column(String, nullable=True, index=True)
    quality_event_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    dispute_reason_code = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open", index=True)
    requested_amount_usd = Column(Float, nullable=False, default=0.0)
    resolved_amount_usd = Column(Float, nullable=False, default=0.0)
    requested_by = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=True, index=True)
    resolution_note = Column(Text, nullable=True)
    dispute_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class RefundRequestRow(PlatformBase):
    __tablename__ = "refund_requests"
    __table_args__ = (
        Index("idx_refund_requests_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_refund_requests_dispute_updated_at", "dispute_id", "updated_at"),
    )

    refund_request_id = Column(String, primary_key=True)
    dispute_id = Column(String, nullable=True, index=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    invoice_preview_id = Column(String, nullable=True, index=True)
    billable_event_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="requested", index=True)
    requested_amount_usd = Column(Float, nullable=False, default=0.0)
    approved_amount_usd = Column(Float, nullable=False, default=0.0)
    requested_by = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=True, index=True)
    refund_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class SettlementRunRow(PlatformBase):
    __tablename__ = "settlement_runs"
    __table_args__ = (
        Index("idx_settlement_runs_account_updated_at", "account_id", "updated_at"),
        Index("idx_settlement_runs_status_updated_at", "status", "updated_at"),
    )

    settlement_run_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=True, index=True)
    billing_period_start = Column(String, nullable=True, index=True)
    billing_period_end = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    subtotal_amount_usd = Column(Float, nullable=False, default=0.0)
    disputed_amount_usd = Column(Float, nullable=False, default=0.0)
    credited_amount_usd = Column(Float, nullable=False, default=0.0)
    reversed_amount_usd = Column(Float, nullable=False, default=0.0)
    refunded_amount_usd = Column(Float, nullable=False, default=0.0)
    net_amount_usd = Column(Float, nullable=False, default=0.0)
    run_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class SettlementItemRow(PlatformBase):
    __tablename__ = "settlement_items"
    __table_args__ = (
        Index("idx_settlement_items_run_status_created_at", "settlement_run_id", "status", "created_at"),
    )

    settlement_item_id = Column(String, primary_key=True)
    settlement_run_id = Column(String, nullable=False, index=True)
    billable_event_id = Column(String, nullable=True, index=True)
    invoice_preview_id = Column(String, nullable=True, index=True)
    dispute_id = Column(String, nullable=True, index=True)
    refund_request_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="approved", index=True)
    amount_usd = Column(Float, nullable=False, default=0.0)
    item_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class SupportCaseRow(PlatformBase):
    __tablename__ = "support_cases"
    __table_args__ = (
        Index("idx_support_cases_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_support_cases_owner_status_updated_at", "owner_id", "status", "updated_at"),
    )

    support_case_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    campaign_id = Column(String, nullable=True, index=True)
    invoice_preview_id = Column(String, nullable=True, index=True)
    billable_event_id = Column(String, nullable=True, index=True)
    quality_event_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    case_type = Column(String, nullable=False, default="general", index=True)
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="open", index=True)
    priority = Column(String, nullable=False, default="medium", index=True)
    requested_by = Column(String, nullable=False)
    owner_id = Column(String, nullable=True, index=True)
    resolution_note = Column(Text, nullable=True)
    support_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ManualAdjustmentRow(PlatformBase):
    __tablename__ = "manual_adjustments"
    __table_args__ = (
        Index("idx_manual_adjustments_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_manual_adjustments_dispute_updated_at", "dispute_id", "updated_at"),
    )

    adjustment_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    dispute_id = Column(String, nullable=True, index=True)
    refund_request_id = Column(String, nullable=True, index=True)
    invoice_preview_id = Column(String, nullable=True, index=True)
    billable_event_id = Column(String, nullable=True, index=True)
    adjustment_type = Column(String, nullable=False, index=True)
    amount_usd = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="applied", index=True)
    requested_by = Column(String, nullable=False)
    reviewer_id = Column(String, nullable=True, index=True)
    adjustment_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class AuditLogRow(PlatformBase):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_logs_account_created_at", "account_id", "created_at"),
        Index("idx_audit_logs_customer_created_at", "customer_account_id", "created_at"),
        Index("idx_audit_logs_actor_created_at", "actor_id", "created_at"),
        Index("idx_audit_logs_action_created_at", "action_type", "created_at"),
    )

    audit_log_id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    actor_role = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    object_type = Column(String, nullable=False, index=True)
    object_id = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False, index=True)
    source_surface = Column(String, nullable=False, index=True)
    customer_visible_payload_json = Column(JSON, nullable=False)
    internal_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class CustomerAuditExportRow(PlatformBase):
    __tablename__ = "customer_audit_exports"
    __table_args__ = (
        Index("idx_customer_audit_exports_account_created_at", "account_id", "created_at"),
        Index("idx_customer_audit_exports_customer_created_at", "customer_account_id", "created_at"),
    )

    audit_export_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    requested_by = Column(String, nullable=False)
    period_start = Column(String, nullable=True, index=True)
    period_end = Column(String, nullable=True, index=True)
    export_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class DataRetentionPolicyRow(PlatformBase):
    __tablename__ = "data_retention_policies"
    __table_args__ = (
        Index("idx_data_retention_policies_scope_status_updated_at", "scope", "status", "updated_at"),
    )

    retention_policy_id = Column(String, primary_key=True)
    scope = Column(String, nullable=False, index=True)
    retention_days = Column(Integer, nullable=False, default=30)
    deletion_mode = Column(String, nullable=False, default="manual_request")
    status = Column(String, nullable=False, default="active", index=True)
    policy_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class DataDeletionRequestRow(PlatformBase):
    __tablename__ = "data_deletion_requests"
    __table_args__ = (
        Index("idx_data_deletion_requests_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_data_deletion_requests_customer_status_updated_at", "customer_account_id", "status", "updated_at"),
    )

    deletion_request_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    requested_by = Column(String, nullable=False)
    scope = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="requested", index=True)
    requested_payload_json = Column(JSON, nullable=False)
    affected_object_counts_json = Column(JSON, nullable=False)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class InvoiceIssuanceRow(PlatformBase):
    __tablename__ = "invoice_issuances"
    __table_args__ = (
        Index("idx_invoice_issuances_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_invoice_issuances_customer_status_updated_at", "customer_account_id", "status", "updated_at"),
        Index("idx_invoice_issuances_provider_ref_updated_at", "provider_invoice_ref", "updated_at"),
    )

    invoice_id = Column(String, primary_key=True)
    invoice_preview_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    provider_invoice_ref = Column(String, nullable=True, index=True)
    provider_customer_ref = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    currency = Column(String, nullable=False, default="USD")
    subtotal_amount_usd = Column(Float, nullable=False, default=0.0)
    total_due_usd = Column(Float, nullable=False, default=0.0)
    hosted_invoice_url = Column(String, nullable=True)
    invoice_pdf_url = Column(String, nullable=True)
    issued_at = Column(String, nullable=True)
    paid_at = Column(String, nullable=True)
    voided_at = Column(String, nullable=True)
    invoice_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class PaymentTransactionRow(PlatformBase):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        Index("idx_payment_transactions_account_occurred_at", "account_id", "occurred_at"),
        Index("idx_payment_transactions_invoice_occurred_at", "invoice_id", "occurred_at"),
        Index("idx_payment_transactions_provider_ref_occurred_at", "provider_transaction_ref", "occurred_at"),
    )

    payment_transaction_id = Column(String, primary_key=True)
    invoice_id = Column(String, nullable=True, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    provider_transaction_ref = Column(String, nullable=True, index=True)
    transaction_type = Column(String, nullable=False, default="payment", index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    amount_usd = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="USD")
    trace_id = Column(String, nullable=True, index=True)
    transaction_payload_json = Column(JSON, nullable=False)
    occurred_at = Column(String, nullable=False, default=utcnow_iso)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ProviderWebhookEventRow(PlatformBase):
    __tablename__ = "provider_webhook_events"
    __table_args__ = (
        Index("idx_provider_webhook_events_provider_created_at", "provider", "created_at"),
        Index("idx_provider_webhook_events_provider_event_created_at", "provider_event_id", "created_at"),
        Index("idx_provider_webhook_events_status_created_at", "status", "created_at"),
    )

    provider_webhook_event_id = Column(String, primary_key=True)
    provider = Column(String, nullable=False, index=True)
    provider_event_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="received", index=True)
    invoice_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=True, index=True)
    payload_json = Column(JSON, nullable=False)
    processing_result_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    processed_at = Column(String, nullable=True)


class CreditNoteRow(PlatformBase):
    __tablename__ = "credit_notes"
    __table_args__ = (
        Index("idx_credit_notes_invoice_created_at", "invoice_id", "created_at"),
        Index("idx_credit_notes_provider_ref_created_at", "provider_credit_note_ref", "created_at"),
    )

    credit_note_id = Column(String, primary_key=True)
    invoice_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    provider_credit_note_ref = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="issued", index=True)
    amount_usd = Column(Float, nullable=False, default=0.0)
    reason = Column(String, nullable=True)
    credit_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class PaymentRetryAttemptRow(PlatformBase):
    __tablename__ = "payment_retry_attempts"
    __table_args__ = (
        Index("idx_payment_retry_attempts_invoice_updated_at", "invoice_id", "updated_at"),
        Index("idx_payment_retry_attempts_account_updated_at", "account_id", "updated_at"),
    )

    payment_retry_attempt_id = Column(String, primary_key=True)
    invoice_id = Column(String, nullable=True, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="planned", index=True)
    retry_reason = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    next_retry_at = Column(String, nullable=True)
    retry_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class DunningEventRow(PlatformBase):
    __tablename__ = "dunning_events"
    __table_args__ = (
        Index("idx_dunning_events_invoice_created_at", "invoice_id", "created_at"),
        Index("idx_dunning_events_account_created_at", "account_id", "created_at"),
    )

    dunning_event_id = Column(String, primary_key=True)
    invoice_id = Column(String, nullable=True, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="scheduled", index=True)
    step = Column(String, nullable=False, index=True)
    event_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class RenewalTrackerRow(PlatformBase):
    __tablename__ = "renewal_trackers"
    __table_args__ = (
        Index("idx_renewal_trackers_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    renewal_tracker_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="stable", index=True)
    renewal_due_at = Column(String, nullable=True)
    tracker_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class DunningRunRow(PlatformBase):
    __tablename__ = "dunning_runs"
    __table_args__ = (
        Index("idx_dunning_runs_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    dunning_run_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    invoice_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="open", index=True)
    current_step = Column(String, nullable=False, default="initial_notice")
    dunning_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class PilotConversionTrackRow(PlatformBase):
    __tablename__ = "pilot_conversion_tracks"
    __table_args__ = (
        Index("idx_pilot_conversion_tracks_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    pilot_conversion_track_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="watch", index=True)
    track_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ExpansionCandidateRow(PlatformBase):
    __tablename__ = "expansion_candidates"
    __table_args__ = (
        Index("idx_expansion_candidates_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    expansion_candidate_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="watch", index=True)
    trigger_type = Column(String, nullable=False, index=True)
    candidate_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ChurnRiskFlagRow(PlatformBase):
    __tablename__ = "churn_risk_flags"
    __table_args__ = (
        Index("idx_churn_risk_flags_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    churn_risk_flag_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="watch", index=True)
    risk_level = Column(String, nullable=False, default="medium", index=True)
    flag_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionSignoffRow(PlatformBase):
    __tablename__ = "production_signoffs"
    __table_args__ = (
        Index("idx_production_signoffs_status_updated_at", "status", "updated_at"),
        Index("idx_production_signoffs_launch_label_updated_at", "launch_label", "updated_at"),
    )

    signoff_id = Column(String, primary_key=True)
    launch_label = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    source_go_live_checklist_id = Column(String, nullable=True)
    source_manual_signoff_bundle_id = Column(String, nullable=True)
    rollup_summary_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionSignoffItemRow(PlatformBase):
    __tablename__ = "production_signoff_items"
    __table_args__ = (
        Index("idx_production_signoff_items_signoff_status_due_at", "signoff_id", "status", "due_at"),
        Index("idx_production_signoff_items_owner_status_due_at", "owner_role", "status", "due_at"),
        Index("idx_production_signoff_items_code_status_updated_at", "item_code", "status", "updated_at"),
    )

    signoff_item_id = Column(String, primary_key=True)
    signoff_id = Column(String, nullable=False, index=True)
    item_code = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    label = Column(Text, nullable=False)
    owner_role = Column(String, nullable=False, index=True)
    owner_actor_id = Column(String, nullable=True, index=True)
    due_at = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    decision_note = Column(Text, nullable=True)
    approved_at = Column(String, nullable=True)
    evidence_count = Column(Integer, nullable=False, default=0)
    item_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionSignoffEvidenceRow(PlatformBase):
    __tablename__ = "production_signoff_evidence"
    __table_args__ = (
        Index("idx_production_signoff_evidence_item_created_at", "signoff_item_id", "created_at"),
        Index("idx_production_signoff_evidence_signoff_created_at", "signoff_id", "created_at"),
    )

    evidence_id = Column(String, primary_key=True)
    signoff_id = Column(String, nullable=False, index=True)
    signoff_item_id = Column(String, nullable=False, index=True)
    evidence_type = Column(String, nullable=False, index=True)
    source_ref_json = Column(JSON, nullable=False)
    summary = Column(Text, nullable=True)
    customer_safe = Column(Boolean, nullable=False, default=False)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionCutoverWindowRow(PlatformBase):
    __tablename__ = "production_cutover_windows"
    __table_args__ = (
        Index("idx_production_cutover_windows_signoff_status_starts_at", "signoff_id", "status", "starts_at"),
        Index("idx_production_cutover_windows_env_status_starts_at", "target_environment", "status", "starts_at"),
    )

    cutover_window_id = Column(String, primary_key=True)
    signoff_id = Column(String, nullable=False, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    target_environment = Column(String, nullable=False, index=True)
    starts_at = Column(String, nullable=True)
    ends_at = Column(String, nullable=True)
    rollback_owner_role = Column(String, nullable=True)
    status = Column(String, nullable=False, default="planned", index=True)
    cutover_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionCustomerAcceptanceRecordRow(PlatformBase):
    __tablename__ = "production_customer_acceptance_records"
    __table_args__ = (
        Index("idx_production_customer_acceptance_account_status_updated_at", "account_id", "status", "updated_at"),
        Index("idx_production_customer_acceptance_wave_status_updated_at", "launch_wave", "status", "updated_at"),
    )

    acceptance_record_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    signoff_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    readiness_summary_json = Column(JSON, nullable=False)
    acceptance_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class GoLiveReadyAccountRow(PlatformBase):
    __tablename__ = "go_live_ready_accounts"
    __table_args__ = (
        Index("idx_go_live_ready_accounts_wave_status_updated_at", "launch_wave", "status", "updated_at"),
        Index("idx_go_live_ready_accounts_account_status_updated_at", "account_id", "status", "updated_at"),
    )

    go_live_ready_account_id = Column(String, primary_key=True)
    customer_account_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    acceptance_record_id = Column(String, nullable=False, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="candidate", index=True)
    readiness_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class LaunchWaveStatusRow(PlatformBase):
    __tablename__ = "launch_wave_statuses"
    __table_args__ = (
        Index("idx_launch_wave_statuses_wave_status_updated_at", "launch_wave", "status", "updated_at"),
    )

    launch_wave_status_id = Column(String, primary_key=True)
    launch_wave = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="planned", index=True)
    target_environment = Column(String, nullable=False, default="production")
    wave_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionPreflightRunRow(PlatformBase):
    __tablename__ = "production_preflight_runs"
    __table_args__ = (
        Index("idx_production_preflight_runs_signoff_status_updated_at", "signoff_id", "status", "updated_at"),
        Index("idx_production_preflight_runs_wave_status_updated_at", "launch_wave", "status", "updated_at"),
    )

    preflight_run_id = Column(String, primary_key=True)
    signoff_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    target_environment = Column(String, nullable=False, default="production", index=True)
    status = Column(String, nullable=False, default="running", index=True)
    go_no_go = Column(String, nullable=False, default="manual_review", index=True)
    hard_fail_count = Column(Integer, nullable=False, default=0)
    soft_fail_count = Column(Integer, nullable=False, default=0)
    run_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionPreflightCheckRow(PlatformBase):
    __tablename__ = "production_preflight_checks"
    __table_args__ = (
        Index("idx_production_preflight_checks_run_status_created_at", "preflight_run_id", "status", "created_at"),
        Index("idx_production_preflight_checks_linked_item_status_created_at", "linked_signoff_item_code", "status", "created_at"),
    )

    preflight_check_id = Column(String, primary_key=True)
    preflight_run_id = Column(String, nullable=False, index=True)
    check_key = Column(String, nullable=False, index=True)
    linked_signoff_item_code = Column(String, nullable=True, index=True)
    owner_role = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="passed", index=True)
    summary = Column(Text, nullable=True)
    evidence_ref = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class First7DayOutcomeRow(PlatformBase):
    __tablename__ = "first_7_day_outcomes"
    __table_args__ = (
        Index("idx_first_7_day_outcomes_account_generated_at", "account_id", "generated_at"),
        Index("idx_first_7_day_outcomes_wave_generated_at", "launch_wave", "generated_at"),
    )

    first_7_day_outcome_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    launch_anchor_at = Column(String, nullable=True)
    outcome_payload_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class First30DayValueSummaryRow(PlatformBase):
    __tablename__ = "first_30_day_value_summaries"
    __table_args__ = (
        Index("idx_first_30_day_value_summaries_account_generated_at", "account_id", "generated_at"),
        Index("idx_first_30_day_value_summaries_wave_generated_at", "launch_wave", "generated_at"),
    )

    first_30_day_value_summary_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    launch_anchor_at = Column(String, nullable=True)
    provisional = Column(Boolean, nullable=False, default=True)
    summary_payload_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class PilotToPaidReadinessScoreRow(PlatformBase):
    __tablename__ = "pilot_to_paid_readiness_scores"
    __table_args__ = (
        Index("idx_pilot_to_paid_readiness_scores_account_generated_at", "account_id", "generated_at"),
        Index("idx_pilot_to_paid_readiness_scores_wave_generated_at", "launch_wave", "generated_at"),
    )

    pilot_to_paid_readiness_score_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    launch_anchor_at = Column(String, nullable=True)
    score = Column(Float, nullable=False, default=0.0)
    band = Column(String, nullable=False, default="watch", index=True)
    score_payload_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class CustomerSuccessSnapshotRow(PlatformBase):
    __tablename__ = "customer_success_snapshots"
    __table_args__ = (
        Index("idx_customer_success_snapshots_account_generated_at", "account_id", "generated_at"),
        Index("idx_customer_success_snapshots_wave_generated_at", "launch_wave", "generated_at"),
    )

    customer_success_snapshot_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    customer_account_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    launch_anchor_at = Column(String, nullable=True)
    snapshot_payload_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionLaunchEventRow(PlatformBase):
    __tablename__ = "production_launch_events"
    __table_args__ = (
        Index("idx_production_launch_events_wave_phase_occurred_at", "launch_wave", "phase", "occurred_at"),
        Index("idx_production_launch_events_account_severity_occurred_at", "account_id", "severity", "occurred_at"),
    )

    launch_event_id = Column(String, primary_key=True)
    launch_wave = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    event_category = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    phase = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="info", index=True)
    related_object_type = Column(String, nullable=True, index=True)
    related_object_id = Column(String, nullable=True, index=True)
    occurred_at = Column(String, nullable=False, default=utcnow_iso)
    event_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class ProductionPostmortemRecordRow(PlatformBase):
    __tablename__ = "production_postmortem_records"
    __table_args__ = (
        Index("idx_production_postmortem_records_wave_status_generated_at", "launch_wave", "status", "generated_at"),
        Index("idx_production_postmortem_records_account_status_generated_at", "account_id", "status", "generated_at"),
    )

    postmortem_record_id = Column(String, primary_key=True)
    launch_wave = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    summary_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class GoLiveDayRunRow(PlatformBase):
    __tablename__ = "go_live_day_runs"
    __table_args__ = (
        Index("idx_go_live_day_runs_wave_status_updated_at", "launch_wave", "status", "updated_at"),
    )

    go_live_day_run_id = Column(String, primary_key=True)
    signoff_id = Column(String, nullable=True, index=True)
    launch_wave = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="running", index=True)
    activation_state_before = Column(String, nullable=True)
    activation_state_after = Column(String, nullable=True)
    report_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso)


class GoLiveDayCheckpointRow(PlatformBase):
    __tablename__ = "go_live_day_checkpoints"
    __table_args__ = (
        Index("idx_go_live_day_checkpoints_run_created_at", "go_live_day_run_id", "created_at"),
        Index("idx_go_live_day_checkpoints_key_status_created_at", "checkpoint_key", "status", "created_at"),
    )

    go_live_day_checkpoint_id = Column(String, primary_key=True)
    go_live_day_run_id = Column(String, nullable=False, index=True)
    checkpoint_key = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="passed", index=True)
    summary = Column(Text, nullable=True)
    evidence_ref = Column(Text, nullable=True)
    rollback_recommendation = Column(String, nullable=True)
    checkpoint_payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class LaunchWeekGuardRunRow(PlatformBase):
    __tablename__ = "launch_week_guard_runs"
    __table_args__ = (
        Index("idx_launch_week_guard_runs_wave_status_generated_at", "launch_wave", "status", "generated_at"),
    )

    launch_week_guard_run_id = Column(String, primary_key=True)
    launch_wave = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="not_ready", index=True)
    replication_readiness = Column(String, nullable=False, default="not_ready", index=True)
    summary_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


class FirstCustomerSuccessPackRow(PlatformBase):
    __tablename__ = "first_customer_success_packs"
    __table_args__ = (
        Index("idx_first_customer_success_packs_wave_status_generated_at", "launch_wave", "status", "generated_at"),
    )

    first_customer_success_pack_id = Column(String, primary_key=True)
    launch_wave = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="not_ready", index=True)
    pack_payload_json = Column(JSON, nullable=False)
    generated_at = Column(String, nullable=False, default=utcnow_iso)


def _is_file_sqlite_url(database_url: str) -> bool:
    lowered = str(database_url or "").lower()
    return lowered.startswith("sqlite:///") and lowered not in {"sqlite://", "sqlite:///:memory:"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "") or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _postgres_engine_options() -> dict:
    is_serverless = bool(os.getenv("VERCEL"))
    return {
        "pool_pre_ping": True,
        "pool_recycle": _int_env("NARRATIVEOS_DB_POOL_RECYCLE_SECONDS", 300),
        "pool_timeout": _int_env("NARRATIVEOS_DB_POOL_TIMEOUT_SECONDS", 10),
        "pool_size": _int_env("NARRATIVEOS_DB_POOL_SIZE", 1 if is_serverless else 5),
        "max_overflow": _int_env("NARRATIVEOS_DB_MAX_OVERFLOW", 2 if is_serverless else 10),
        "connect_args": {
            "connect_timeout": _int_env("NARRATIVEOS_DB_CONNECT_TIMEOUT_SECONDS", 10),
        },
    }


def create_platform_engine(database_url: str):
    if not str(database_url or "").lower().startswith("sqlite:"):
        return create_engine(database_url, future=True, **_postgres_engine_options())

    engine = create_engine(
        database_url,
        future=True,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite_runtime(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            if _is_file_sqlite_url(database_url):
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                except Exception:
                    # Some sqlite URLs can be read-only or backed by virtual files.
                    # Busy timeout is still useful there, so do not fail engine creation.
                    pass
        finally:
            cursor.close()

    return engine


SQLITE_COMPATIBILITY_COLUMNS = {
    "auth_identity_profiles": (
        {
            "name": "pending_email_address",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN pending_email_address VARCHAR",
        },
        {
            "name": "avatar_url",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN avatar_url VARCHAR",
        },
        {
            "name": "pending_email_change_requested_at",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN pending_email_change_requested_at VARCHAR",
        },
        {
            "name": "email_change_last_sent_at",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN email_change_last_sent_at VARCHAR",
        },
        {
            "name": "ui_preferences_json",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN ui_preferences_json JSON",
        },
        {
            "name": "deactivated_at",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN deactivated_at VARCHAR",
        },
        {
            "name": "deactivated_by",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN deactivated_by VARCHAR",
        },
        {
            "name": "deactivation_reason",
            "ddl": "ALTER TABLE auth_identity_profiles ADD COLUMN deactivation_reason TEXT",
        },
    ),
    "author_works": (
        {
            "name": "branch_id",
            "ddl": "ALTER TABLE author_works ADD COLUMN branch_id VARCHAR",
        },
        {
            "name": "root_work_id",
            "ddl": "ALTER TABLE author_works ADD COLUMN root_work_id VARCHAR",
            "backfill": "UPDATE author_works SET root_work_id = work_id WHERE root_work_id IS NULL",
        },
        {
            "name": "parent_work_id",
            "ddl": "ALTER TABLE author_works ADD COLUMN parent_work_id VARCHAR",
        },
        {
            "name": "branch_name",
            "ddl": "ALTER TABLE author_works ADD COLUMN branch_name VARCHAR",
            "backfill": "UPDATE author_works SET branch_name = '主线' WHERE branch_name IS NULL",
        },
        {
            "name": "branch_kind",
            "ddl": "ALTER TABLE author_works ADD COLUMN branch_kind VARCHAR",
            "backfill": "UPDATE author_works SET branch_kind = 'mainline' WHERE branch_kind IS NULL",
        },
        {
            "name": "branch_origin_label",
            "ddl": "ALTER TABLE author_works ADD COLUMN branch_origin_label TEXT",
        },
        {
            "name": "fork_after_chapter_index",
            "ddl": "ALTER TABLE author_works ADD COLUMN fork_after_chapter_index INTEGER",
            "backfill": "UPDATE author_works SET fork_after_chapter_index = 0 WHERE fork_after_chapter_index IS NULL",
        },
        {
            "name": "is_active_line",
            "ddl": "ALTER TABLE author_works ADD COLUMN is_active_line INTEGER DEFAULT 0",
            "backfill": "UPDATE author_works SET is_active_line = 1 WHERE is_active_line IS NULL",
        },
    ),
    "entitlements": (
        {
            "name": "account_id",
            "ddl": "ALTER TABLE entitlements ADD COLUMN account_id VARCHAR",
            "backfill": "UPDATE entitlements SET account_id = reader_id WHERE account_id IS NULL",
        },
        {
            "name": "wallet_type",
            "ddl": "ALTER TABLE entitlements ADD COLUMN wallet_type VARCHAR",
        },
        {
            "name": "tier_id",
            "ddl": "ALTER TABLE entitlements ADD COLUMN tier_id VARCHAR",
        },
    ),
    "subscriptions": (
        {
            "name": "account_id",
            "ddl": "ALTER TABLE subscriptions ADD COLUMN account_id VARCHAR",
        },
    ),
    "billing_checkout_sessions": (
        {
            "name": "checkout_kind",
            "ddl": "ALTER TABLE billing_checkout_sessions ADD COLUMN checkout_kind VARCHAR DEFAULT 'subscription'",
            "backfill": "UPDATE billing_checkout_sessions SET checkout_kind = 'subscription' WHERE checkout_kind IS NULL",
        },
        {
            "name": "package_id",
            "ddl": "ALTER TABLE billing_checkout_sessions ADD COLUMN package_id VARCHAR",
        },
        {
            "name": "fulfilled_at",
            "ddl": "ALTER TABLE billing_checkout_sessions ADD COLUMN fulfilled_at VARCHAR",
        },
    ),
    "usage_meters": (
        {
            "name": "account_id",
            "ddl": "ALTER TABLE usage_meters ADD COLUMN account_id VARCHAR",
            "backfill": "UPDATE usage_meters SET account_id = reader_id WHERE account_id IS NULL",
        },
        {
            "name": "wallet_type",
            "ddl": "ALTER TABLE usage_meters ADD COLUMN wallet_type VARCHAR",
        },
        {
            "name": "subscription_tier",
            "ddl": "ALTER TABLE usage_meters ADD COLUMN subscription_tier VARCHAR",
        },
        {
            "name": "provider",
            "ddl": "ALTER TABLE usage_meters ADD COLUMN provider VARCHAR",
        },
    ),
}


def bootstrap_sqlite_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if not table_names:
        return
    with engine.begin() as connection:
        for table_name, column_specs in SQLITE_COMPATIBILITY_COLUMNS.items():
            if table_name not in table_names:
                continue
            current_columns = {
                str(row[1])
                for row in connection.exec_driver_sql(f"PRAGMA table_info('{table_name}')")
            }
            for spec in column_specs:
                if spec["name"] in current_columns:
                    continue
                connection.exec_driver_sql(spec["ddl"])
                if spec.get("backfill"):
                    connection.exec_driver_sql(spec["backfill"])


def is_postgres_url(database_url: str) -> bool:
    lowered = database_url.lower()
    return lowered.startswith("postgresql://") or lowered.startswith("postgres://")


def load_postgres_schema_sql(schema_path: Path = POSTGRES_SCHEMA_PATH) -> str:
    return schema_path.read_text(encoding="utf-8")


def _split_sql_statements(sql_text: str) -> list[str]:
    statements = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).strip().rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current).strip().rstrip(";"))
    return [statement for statement in statements if statement]


def bootstrap_postgres_schema(engine: Engine, schema_path: Path = POSTGRES_SCHEMA_PATH) -> None:
    from .migrations import bootstrap_schema_lifecycle

    if (schema_path.parent / "migrations").exists():
        bootstrap_schema_lifecycle(
            engine,
            migrations_dir=schema_path.parent / "migrations",
            schema_path=schema_path,
            apply=True,
        )
        return
    if not schema_path.exists():
        return
    sql_text = load_postgres_schema_sql(schema_path)
    statements = _split_sql_statements(sql_text)
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)


def create_platform_session_local(database_url: str):
    engine = create_platform_engine(database_url)
    if is_postgres_url(database_url):
        # On a fresh managed Postgres, ensure base tables exist before replaying
        # our append-only SQL migration chain, which may contain backfills.
        PlatformBase.metadata.create_all(engine)
        bootstrap_postgres_schema(engine)
    elif database_url.lower().startswith("sqlite:"):
        bootstrap_sqlite_schema(engine)
    PlatformBase.metadata.create_all(engine)
    if database_url.lower().startswith("sqlite:"):
        bootstrap_sqlite_schema(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
