from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import BASE_DIR, create_platform_engine, utcnow_iso


MIGRATIONS_DIR = BASE_DIR / "db" / "migrations"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
ALEMBIC_INI_PATH = BASE_DIR / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = BASE_DIR / "db" / "alembic"
ALEMBIC_VERSIONS_DIR = ALEMBIC_SCRIPT_LOCATION / "versions"
DEFAULT_SCHEMA_PATH = BASE_DIR / "db" / "postgres_schema.sql"


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


def alembic_dependency_installed() -> bool:
    return importlib.util.find_spec("alembic") is not None


def alembic_repo_configured(
    *,
    config_path: Path = ALEMBIC_INI_PATH,
    script_location: Path = ALEMBIC_SCRIPT_LOCATION,
    versions_dir: Path = ALEMBIC_VERSIONS_DIR,
) -> bool:
    return config_path.exists() and script_location.exists() and versions_dir.exists()


def alembic_enabled() -> bool:
    return alembic_dependency_installed() and alembic_repo_configured()


def _get_alembic_modules() -> Any:
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    return command, Config, MigrationContext, ScriptDirectory


def _build_alembic_config(database_url: Optional[str] = None) -> Any:
    _, Config, _, _ = _get_alembic_modules()
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def inspect_alembic_state(engine: Engine) -> dict:
    base = {
        "enabled": alembic_enabled(),
        "dependency_installed": alembic_dependency_installed(),
        "config_path": str(ALEMBIC_INI_PATH),
        "script_location": str(ALEMBIC_SCRIPT_LOCATION),
        "versions_dir": str(ALEMBIC_VERSIONS_DIR),
        "known_revisions": [],
        "head_revision": None,
        "current_revision": None,
        "pending_revisions": [],
        "status": "unavailable",
        "at_head": False,
    }
    if not base["dependency_installed"]:
        base["status"] = "dependency_missing"
        return base
    if not alembic_repo_configured():
        base["status"] = "config_missing"
        return base

    _, _, MigrationContext, ScriptDirectory = _get_alembic_modules()
    config = _build_alembic_config(str(engine.url))
    script_directory = ScriptDirectory.from_config(config)
    revisions = list(reversed(list(script_directory.walk_revisions())))
    known_revisions = [
        {
            "revision": revision.revision,
            "down_revision": list(revision.down_revision)
            if isinstance(revision.down_revision, tuple)
            else revision.down_revision,
            "doc": revision.doc,
            "path": revision.path,
        }
        for revision in revisions
    ]
    head_revision = script_directory.get_current_head()
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()

    revision_ids = [item["revision"] for item in known_revisions]
    if current_revision is None:
        status = "not_stamped"
        pending_revisions = revision_ids
    elif current_revision not in revision_ids:
        status = "unknown_revision"
        pending_revisions = revision_ids
    else:
        current_index = revision_ids.index(current_revision)
        pending_revisions = revision_ids[current_index + 1 :]
        status = "at_head" if current_revision == head_revision else "behind_head"

    return {
        **base,
        "known_revisions": known_revisions,
        "head_revision": head_revision,
        "current_revision": current_revision,
        "pending_revisions": pending_revisions,
        "status": status,
        "at_head": bool(head_revision and current_revision == head_revision),
    }


def alembic_history(database_url: Optional[str] = None) -> dict:
    if not alembic_enabled():
        return {"enabled": False, "history": []}
    state = inspect_alembic_state(create_platform_engine(database_url or "sqlite://"))
    return {
        "enabled": True,
        "head_revision": state["head_revision"],
        "history": state["known_revisions"],
    }


def stamp_alembic_head(database_url: str) -> dict:
    if not alembic_enabled():
        return {"enabled": False, "changed": False, "target_revision": None}
    command, _, _, _ = _get_alembic_modules()
    config = _build_alembic_config(database_url)
    state_before = inspect_alembic_state(create_platform_engine(database_url))
    command.stamp(config, "head")
    state_after = inspect_alembic_state(create_platform_engine(database_url))
    return {
        "enabled": True,
        "changed": state_before["current_revision"] != state_after["current_revision"],
        "target_revision": state_after["head_revision"],
        "before": state_before,
        "after": state_after,
        "command": "stamp",
    }


def upgrade_alembic_head(database_url: str) -> dict:
    if not alembic_enabled():
        return {"enabled": False, "changed": False, "target_revision": None}
    command, _, _, _ = _get_alembic_modules()
    config = _build_alembic_config(database_url)
    state_before = inspect_alembic_state(create_platform_engine(database_url))
    command.upgrade(config, "head")
    state_after = inspect_alembic_state(create_platform_engine(database_url))
    return {
        "enabled": True,
        "changed": state_before["current_revision"] != state_after["current_revision"],
        "target_revision": state_after["head_revision"],
        "before": state_before,
        "after": state_after,
        "command": "upgrade",
    }


def downgrade_alembic_target(database_url: str, revision: str) -> dict:
    if not alembic_enabled():
        return {"enabled": False, "changed": False, "target_revision": revision}
    command, _, _, _ = _get_alembic_modules()
    config = _build_alembic_config(database_url)
    state_before = inspect_alembic_state(create_platform_engine(database_url))
    command.downgrade(config, revision)
    state_after = inspect_alembic_state(create_platform_engine(database_url))
    return {
        "enabled": True,
        "changed": state_before["current_revision"] != state_after["current_revision"],
        "target_revision": revision,
        "before": state_before,
        "after": state_after,
        "command": "downgrade",
    }


def _repo_schema_paths(
    *,
    migrations_dir: Path,
    schema_path: Path,
) -> bool:
    return migrations_dir.resolve() == MIGRATIONS_DIR.resolve() and schema_path.resolve() == DEFAULT_SCHEMA_PATH.resolve()


def inspect_schema_lifecycle(
    engine: Engine,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> dict:
    available_files = list_migration_files(migrations_dir)
    available_versions = [path.stem for path in available_files]
    applied_versions = applied_migrations(engine)
    pending_versions = [version for version in available_versions if version not in set(applied_versions)]
    schema_fp = schema_file_fingerprint(schema_path)
    migrations_fp = migrations_fingerprint(migrations_dir)
    schema_matches_migrations = bool(schema_fp and migrations_fp and schema_fp == migrations_fp)
    alembic_state = inspect_alembic_state(engine)
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
        "alembic": alembic_state,
    }


def bootstrap_schema_lifecycle(
    engine: Engine,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    apply: bool = True,
) -> dict:
    before = inspect_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path)
    applied_now: List[str] = []
    alembic_action: Optional[dict] = None
    if apply and before["pending_versions"]:
        applied_now = apply_pending_migrations(engine, migrations_dir=migrations_dir)
    if apply and _repo_schema_paths(migrations_dir=migrations_dir, schema_path=schema_path) and before["alembic"]["enabled"]:
        current_revision = before["alembic"]["current_revision"]
        head_revision = before["alembic"]["head_revision"]
        if head_revision and current_revision != head_revision:
            if before["pending_versions"] or current_revision is None:
                alembic_action = stamp_alembic_head(str(engine.url))
            else:
                alembic_action = upgrade_alembic_head(str(engine.url))
    after = inspect_schema_lifecycle(engine, migrations_dir=migrations_dir, schema_path=schema_path)
    return {
        "before": before,
        "after": after,
        "applied_migrations": applied_now,
        "changed": bool(applied_now),
        "dry_run": not apply,
        "alembic_action": alembic_action,
    }


def bootstrap_postgres_runtime(
    database_url: str,
    *,
    seed: bool = False,
    dry_run: bool = False,
    migrations_dir: Path = MIGRATIONS_DIR,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
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
    parser.add_argument("--database-url", help="Database URL for lifecycle inspection or Alembic commands")
    parser.add_argument("--seed-builtins", action="store_true", help="Seed built-in world packs after migrations")
    parser.add_argument("--dry-run", action="store_true", help="Inspect schema lifecycle without applying migrations")
    parser.add_argument("--alembic-current", action="store_true", help="Report current/head Alembic revisions")
    parser.add_argument("--alembic-history", action="store_true", help="List Alembic revision history")
    parser.add_argument("--alembic-upgrade-head", action="store_true", help="Run Alembic upgrade head")
    parser.add_argument("--alembic-downgrade", metavar="REVISION", help="Run Alembic downgrade to REVISION")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.alembic_history:
        result = alembic_history(args.database_url)
    elif args.alembic_current:
        if not args.database_url:
            parser.error("--database-url is required for --alembic-current")
        result = inspect_alembic_state(create_platform_engine(args.database_url))
    elif args.alembic_upgrade_head:
        if not args.database_url:
            parser.error("--database-url is required for --alembic-upgrade-head")
        result = upgrade_alembic_head(args.database_url)
    elif args.alembic_downgrade:
        if not args.database_url:
            parser.error("--database-url is required for --alembic-downgrade")
        result = downgrade_alembic_target(args.database_url, args.alembic_downgrade)
    else:
        if not args.database_url:
            parser.error("--database-url is required for bootstrap inspection/apply")
        result = bootstrap_postgres_runtime(args.database_url, seed=args.seed_builtins, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
