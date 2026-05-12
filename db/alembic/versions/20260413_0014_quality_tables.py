"""Canonical quality tables.

Revision ID: 20260413_0014
Revises: 20260404_0012
Create Date: 2026-04-13 15:00:00
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from alembic import op
from sqlalchemy import text


revision = "20260413_0014"
down_revision = "20260404_0012"
branch_labels = None
depends_on = None

ROOT_DIR = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT_DIR / "db" / "migrations" / "0014_quality_tables.sql"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"


def _split_sql(sql_text: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
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


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        f"""
        create table if not exists {SCHEMA_MIGRATIONS_TABLE} (
          version text primary key,
          applied_at timestamptz not null
        );
        """
    )
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    for statement in _split_sql(sql_text):
        bind.exec_driver_sql(statement)
    bind.execute(
        text(
            f"""
            insert into {SCHEMA_MIGRATIONS_TABLE} (version, applied_at)
            values (:version, :applied_at)
            on conflict (version) do nothing
            """
        ),
        {"version": SQL_PATH.stem, "applied_at": datetime.now(timezone.utc).isoformat()},
    )


def downgrade() -> None:
    bind = op.get_bind()
    for statement in [
        "drop index if exists idx_review_cases_session_status_updated_at",
        "drop index if exists idx_review_cases_world_status_updated_at",
        "drop index if exists idx_review_cases_trace_updated_at",
        "drop index if exists idx_review_cases_status_updated_at",
        "drop table if exists review_cases",
        "drop index if exists idx_content_quality_scores_session_created_at",
        "drop index if exists idx_content_quality_scores_world_created_at",
        "drop index if exists idx_content_quality_scores_status_created_at",
        "drop index if exists idx_content_quality_scores_trace_created_at",
        "drop table if exists content_quality_scores",
        "drop index if exists idx_quality_events_session_created_at",
        "drop index if exists idx_quality_events_world_created_at",
        "drop index if exists idx_quality_events_surface_status_created_at",
        "drop index if exists idx_quality_events_trace_created_at",
        "drop table if exists quality_events",
        "drop index if exists idx_quality_policies_mode_updated_at",
        "drop index if exists idx_quality_policies_scenario_risk_updated_at",
        "drop table if exists quality_policies",
    ]:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(
        f"""
        create table if not exists {SCHEMA_MIGRATIONS_TABLE} (
          version text primary key,
          applied_at timestamptz not null
        );
        """
    )
    bind.execute(text(f"delete from {SCHEMA_MIGRATIONS_TABLE} where version = :version"), {"version": SQL_PATH.stem})
