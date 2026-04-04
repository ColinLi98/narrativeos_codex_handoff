"""Runtime hotspot indexes and repair baseline.

Revision ID: 20260404_0012
Revises: 20260404_0011
Create Date: 2026-04-04 13:00:00
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from alembic import op
from sqlalchemy import text


revision = "20260404_0012"
down_revision = "20260404_0011"
branch_labels = None
depends_on = None

ROOT_DIR = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT_DIR / "db" / "migrations" / "0012_runtime_hotspot_indexes.sql"
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
    raise RuntimeError(
        "Runtime hotspot index downgrade is intentionally blocked. "
        "Use backup/restore if the rollout needs to be reversed."
    )
