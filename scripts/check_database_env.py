#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.persistence.preflight import database_preflight, public_beta_database_readiness
from src.narrativeos.runtime_env import describe_env_sources


def _text_report(payload: dict) -> str:
    lines = [
        f"database_kind: {payload.get('database_kind')}",
        f"database_url: {payload.get('database_url_redacted') or '-'}",
    ]
    if payload.get("host"):
        lines.append(f"host: {payload.get('host')}")
    if payload.get("database_name"):
        lines.append(f"database: {payload.get('database_name')}")
    lines.append(f"ok: {payload.get('ok')}")
    lines.append(f"reason: {payload.get('reason')}")
    if payload.get("error"):
        lines.append(f"error: {payload.get('error')}")
    if payload.get("reason") == "authentication_failed":
        lines.extend(
            [
                "remediation:",
                "- run `npx vercel env pull .env.local --environment=development`",
                "- rerun this preflight",
                "- if it still fails, rotate the Neon/Vercel database password and refresh DATABASE_URL/DATABASE_URL_UNPOOLED/PGPASSWORD",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check current DATABASE_URL connectivity.")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL for this preflight run.")
    parser.add_argument("--direct-database-url", default=None, help="Override DATABASE_URL_UNPOOLED for Public Beta readiness.")
    parser.add_argument("--read-replica-url", default=None, help="Override read-replica URL for Public Beta readiness.")
    parser.add_argument("--public-beta", action="store_true", help="Run Public Beta pooled/direct/read-replica/failover checks.")
    parser.add_argument("--skip-live-probe", action="store_true", help="Skip the live database connection probe.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    if args.public_beta:
        payload = public_beta_database_readiness(
            database_url=args.database_url,
            direct_database_url=args.direct_database_url,
            read_replica_url=args.read_replica_url,
            load_env_files=True,
            run_live_probe=not args.skip_live_probe,
        )
    else:
        payload = database_preflight(database_url=args.database_url, load_env_files=True)
    payload["env_sources"] = describe_env_sources()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.public_beta:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(_text_report(payload))

    return 0 if (payload.get("ready") if args.public_beta else payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
