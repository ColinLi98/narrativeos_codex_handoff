from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Column, Float, Index, Integer, String, Text, create_engine
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
    tier_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_ref = Column(String, nullable=True, index=True)
    subscription_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="created")
    checkout_url = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, index=True)
    expires_at = Column(String, nullable=True)
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


def create_platform_engine(database_url: str):
    return create_engine(database_url, future=True)


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
        bootstrap_postgres_schema(engine)
    PlatformBase.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
