from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ..runtime_env import load_local_env
from .db import create_platform_engine, is_postgres_url


def _redact_url(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    host = parsed.hostname or "unknown-host"
    database_name = parsed.path.lstrip("/") or "unknown-database"
    return f"{host}/{database_name} (database-url-redacted)"


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_neon_pooler_host(host: Optional[str]) -> bool:
    return "-pooler" in str(host or "").lower()


def _classify_database_error(message: str) -> str:
    lowered = str(message or "").lower()
    if "password authentication failed" in lowered or "authentication failed" in lowered:
        return "authentication_failed"
    if "could not translate host name" in lowered or "name or service not known" in lowered:
        return "dns_unreachable"
    if "connection refused" in lowered or "timeout expired" in lowered or "could not connect to server" in lowered:
        return "network_unreachable"
    if "ssl" in lowered or "channel_binding" in lowered:
        return "ssl_configuration_error"
    return "connection_failed"


def database_preflight(*, database_url: Optional[str] = None, load_env_files: bool = True) -> Dict[str, Any]:
    if load_env_files:
        load_local_env()
    resolved_url = str(database_url or os.getenv("DATABASE_URL", "")).strip()
    if not resolved_url:
        return {
            "ok": False,
            "reason": "missing_database_url",
            "database_kind": "missing",
            "database_url_redacted": None,
        }

    database_kind = "postgres" if is_postgres_url(resolved_url) else ("sqlite" if resolved_url.lower().startswith("sqlite:") else "other")
    parsed = urlsplit(resolved_url)
    payload: Dict[str, Any] = {
        "ok": False,
        "reason": None,
        "database_kind": database_kind,
        "database_url_redacted": _redact_url(resolved_url),
        "host": parsed.hostname,
        "database_name": parsed.path.lstrip("/") or None,
    }

    try:
        engine = create_platform_engine(resolved_url)
        with engine.connect() as connection:
            probe = connection.execute(text("select 1")).scalar()
        payload.update(
            {
                "ok": True,
                "reason": "ok",
                "probe_result": probe,
            }
        )
        return payload
    except OperationalError as exc:
        message = str(exc)
        payload.update(
            {
                "reason": _classify_database_error(message),
                "error": message,
            }
        )
        return payload
    except Exception as exc:  # pragma: no cover - defensive classification
        payload.update(
            {
                "reason": "connection_failed",
                "error": str(exc),
            }
        )
        return payload


def public_beta_database_readiness(
    *,
    database_url: Optional[str] = None,
    direct_database_url: Optional[str] = None,
    read_replica_url: Optional[str] = None,
    load_env_files: bool = True,
    run_live_probe: bool = True,
) -> Dict[str, Any]:
    if load_env_files:
        load_local_env()
    runtime_url = str(database_url or os.getenv("DATABASE_URL", "")).strip()
    direct_url = str(
        direct_database_url
        or os.getenv("DATABASE_URL_UNPOOLED", "")
        or os.getenv("POSTGRES_URL_NON_POOLING", "")
    ).strip()
    replica_url = str(read_replica_url or os.getenv("NARRATIVEOS_READ_REPLICA_DATABASE_URL", "")).strip()
    failover_enabled = _env_enabled("NARRATIVEOS_DATABASE_FAILOVER_SQLITE")
    runtime_parsed = urlsplit(runtime_url) if runtime_url else None
    direct_parsed = urlsplit(direct_url) if direct_url else None
    replica_parsed = urlsplit(replica_url) if replica_url else None

    checks: Dict[str, bool] = {
        "runtime_database_url_present": bool(runtime_url),
        "runtime_database_is_postgres": bool(runtime_url and is_postgres_url(runtime_url)),
        "runtime_database_uses_neon_pooler": bool(runtime_parsed and _is_neon_pooler_host(runtime_parsed.hostname)),
        "direct_database_url_present": bool(direct_url),
        "direct_database_is_postgres": bool(direct_url and is_postgres_url(direct_url)),
        "direct_database_is_not_pooler": bool(direct_parsed and not _is_neon_pooler_host(direct_parsed.hostname)),
        "read_replica_url_present": bool(replica_url),
        "read_replica_is_postgres": bool(replica_url and is_postgres_url(replica_url)),
        "read_replica_uses_neon_pooler": bool(replica_parsed and _is_neon_pooler_host(replica_parsed.hostname)),
        "sqlite_failover_disabled": not failover_enabled,
    }
    runtime_probe: Dict[str, Any] = {"ok": None, "reason": "not_run"}
    if run_live_probe and runtime_url:
        runtime_probe = database_preflight(database_url=runtime_url, load_env_files=False)
        checks["runtime_database_live_probe_ok"] = bool(runtime_probe.get("ok"))

    blockers = [
        {
            "key": key,
            "severity": "high",
            "detail": "Public Beta database readiness check failed.",
        }
        for key, passed in checks.items()
        if not passed
    ]
    return {
        "schema_version": "public_beta_database_readiness/v1",
        "ready": not blockers,
        "status": "passed" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "runtime_database": {
            "url_redacted": _redact_url(runtime_url),
            "host": runtime_parsed.hostname if runtime_parsed else None,
            "database_name": runtime_parsed.path.lstrip("/") if runtime_parsed else None,
            "pooled": bool(runtime_parsed and _is_neon_pooler_host(runtime_parsed.hostname)),
            "live_probe": runtime_probe,
        },
        "direct_database": {
            "url_redacted": _redact_url(direct_url),
            "host": direct_parsed.hostname if direct_parsed else None,
            "database_name": direct_parsed.path.lstrip("/") if direct_parsed else None,
            "pooled": bool(direct_parsed and _is_neon_pooler_host(direct_parsed.hostname)),
        },
        "read_replica_database": {
            "url_redacted": _redact_url(replica_url),
            "host": replica_parsed.hostname if replica_parsed else None,
            "database_name": replica_parsed.path.lstrip("/") if replica_parsed else None,
            "pooled": bool(replica_parsed and _is_neon_pooler_host(replica_parsed.hostname)),
            "configured": bool(replica_url),
        },
        "sqlite_failover": {
            "enabled": failover_enabled,
            "env_var": "NARRATIVEOS_DATABASE_FAILOVER_SQLITE",
        },
    }
