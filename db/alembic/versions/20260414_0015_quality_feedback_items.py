"""Canonical quality feedback items.

Revision ID: 20260414_0015
Revises: 20260413_0014
Create Date: 2026-04-14 10:00:00
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from alembic import op
from sqlalchemy import text


revision = "20260414_0015"
down_revision = "20260413_0014"
branch_labels = None
depends_on = None

ROOT_DIR = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT_DIR / "db" / "migrations" / "0015_quality_feedback_items.sql"
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
        "drop index if exists idx_quality_feedback_items_type_signal_created_at",
        "drop index if exists idx_quality_feedback_items_session_created_at",
        "drop index if exists idx_quality_feedback_items_account_created_at",
        "drop index if exists idx_quality_feedback_items_trace_created_at",
        "drop table if exists quality_feedback_items",
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
