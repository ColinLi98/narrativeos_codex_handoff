from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..worldpacks.registry import FileSystemWorldRegistry
from .db import BASE_DIR, create_platform_engine, utcnow_iso


MIGRATIONS_DIR = BASE_DIR / "db" / "migrations"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"


def list_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> List[Path]:
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


def _normalized_sql(sql_text: str) -> str:
    chunks: List[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        chunks.append(" ".join(stripped.split()))
    return "\n".join(chunks)


def sql_fingerprint(sql_text: str) -> str:
    normalized = _normalized_sql(sql_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def schema_file_fingerprint(schema_path: Path) -> Optional[str]:
    if not schema_path.exists():
        return None
    return sql_fingerprint(schema_path.read_text(encoding="utf-8"))


def migrations_fingerprint(migrations_dir: Path = MIGRATIONS_DIR) -> Optional[str]:
    files = list_migration_files(migrations_dir)
    if not files:
        return None
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    return sql_fingerprint(combined)


def ensure_migration_table(engine: Engine) -> None:
    statement = f"""
    create table if not exists {SCHEMA_MIGRATIONS_TABLE} (
      version text primary key,
      applied_at timestamptz not null
    );
    """
    with engine.begin() as connection:
        connection.exec_driver_sql(statement)


def applied_migrations(engine: Engine) -> List[str]:
    ensure_migration_table(engine)
    with engine.begin() as connection:
        rows = connection.execute(text(f"select version from {SCHEMA_MIGRATIONS_TABLE} order by version asc"))
        return [row[0] for row in rows.fetchall()]


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


def apply_sql_migration(engine: Engine, *, version: str, sql_text: str) -> None:
    ensure_migration_table(engine)
    with engine.begin() as connection:
        for statement in _split_sql(sql_text):
            connection.exec_driver_sql(statement)
        connection.execute(
            text(f"insert into {SCHEMA_MIGRATIONS_TABLE} (version, applied_at) values (:version, :applied_at) on conflict (version) do nothing"),
            {"version": version, "applied_at": utcnow_iso()},
        )


def apply_pending_migrations(engine: Engine, migrations_dir: Path = MIGRATIONS_DIR) -> List[str]:
    done = set(applied_migrations(engine))
    applied_now: List[str] = []
    for path in list_migration_files(migrations_dir):
        version = path.stem
        if version in done:
            continue
        apply_sql_migration(engine, version=version, sql_text=path.read_text(encoding="utf-8"))
        applied_now.append(version)
    return applied_now


def inspect_schema_lifecycle(
    engine: Engine,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = BASE_DIR / "db" / "postgres_schema.sql",
) -> dict:
    available_files = list_migration_files(migrations_dir)
    available_versions = [path.stem for path in available_files]
    applied_versions = applied_migrations(engine)
    pending_versions = [version for version in available_versions if version not in set(applied_versions)]
    schema_fp = schema_file_fingerprint(schema_path)
    migrations_fp = migrations_fingerprint(migrations_dir)
    schema_matches_migrations = bool(schema_fp and migrations_fp and schema_fp == migrations_fp)
    if pending_versions:
        status = "pending_migrations"
    elif schema_fp and migrations_fp and not schema_matches_migrations:
        status = "drift_detected"
    elif available_versions:
        status = "up_to_date"
    else:
        status = "missing_migrations"
    return {
        "backend": engine.url.get_backend_name(),
        "schema_path": str(schema_path),
        "migrations_dir": str(migrations_dir),
        "available_versions": available_versions,
        "applied_versions": applied_versions,
        "pending_versions": pending_versions,
        "latest_available_version": available_versions[-1] if available_versions else None,
        "latest_applied_version": applied_versions[-1] if applied_versions else None,
        "schema_sql_fingerprint": schema_fp,
        "migrations_fingerprint": migrations_fp,
        "schema_matches_migrations": schema_matches_migrations,
        "status": status,
    }


def bootstrap_schema_lifecycle(
    engine: Engine,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = BASE_DIR / "db" / "postgres_schema.sql",
    apply: bool = True,
) -> dict:
    before = inspect_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path)
    applied_now: List[str] = []
    if apply and before["pending_versions"]:
        applied_now = apply_pending_migrations(engine, migrations_dir=migrations_dir)
    after = inspect_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path)
    return {
        "before": before,
        "after": after,
        "applied_migrations": applied_now,
        "changed": bool(applied_now),
        "dry_run": not apply,
    }


def bootstrap_postgres_runtime(
    database_url: str,
    *,
    seed: bool = False,
    dry_run: bool = False,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = BASE_DIR / "db" / "postgres_schema.sql",
) -> dict:
    engine = create_platform_engine(database_url)
    lifecycle = bootstrap_schema_lifecycle(
        engine,
        migrations_dir=migrations_dir,
        schema_path=schema_path,
        apply=not dry_run,
    )
    seeded_worlds: List[str] = []
    if seed and not dry_run:
        from ..persistence.repositories import SQLAlchemyPlatformRepository

        repository = SQLAlchemyPlatformRepository(database_url=database_url)
        seeded_worlds = [item["world_id"] for item in repository.list_worlds()]
    return {
        "database_url": database_url,
        "schema_lifecycle": lifecycle,
        "applied_migrations": lifecycle["applied_migrations"],
        "seeded_worlds": seeded_worlds,
        "dry_run": dry_run,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap NarrativeOS Postgres schema and optional built-in world packs.")
    parser.add_argument("--database-url", required=True, help="Postgres database URL")
    parser.add_argument("--seed-builtins", action="store_true", help="Seed built-in world packs after migrations")
    parser.add_argument("--dry-run", action="store_true", help="Inspect schema lifecycle without applying migrations")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = bootstrap_postgres_runtime(args.database_url, seed=args.seed_builtins, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
