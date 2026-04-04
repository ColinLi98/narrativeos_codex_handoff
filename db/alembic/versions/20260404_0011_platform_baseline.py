"""NarrativeOS platform baseline.

Revision ID: 20260404_0011
Revises:
Create Date: 2026-04-04 12:00:00
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from alembic import op
from sqlalchemy import text


revision = "20260404_0011"
down_revision = None
branch_labels = None
depends_on = None

ROOT_DIR = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = ROOT_DIR / "db" / "migrations"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
BASELINE_SQL_CEILING = "0011_billing_retry_attempts"


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


def _migration_files() -> List[Path]:
    return sorted(
        path
        for path in MIGRATIONS_DIR.glob("*.sql")
        if path.is_file() and path.stem <= BASELINE_SQL_CEILING
    )


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
    applied_at = datetime.now(timezone.utc).isoformat()
    for path in _migration_files():
        for statement in _split_sql(path.read_text(encoding="utf-8")):
            bind.exec_driver_sql(statement)
        bind.execute(
            text(
                f"""
                insert into {SCHEMA_MIGRATIONS_TABLE} (version, applied_at)
                values (:version, :applied_at)
                on conflict (version) do nothing
                """
            ),
            {"version": path.stem, "applied_at": applied_at},
        )


def downgrade() -> None:
    raise RuntimeError(
        "Baseline Alembic downgrade is intentionally blocked. "
        "Use backup/restore for production rollback until forward revisions exist."
    )
