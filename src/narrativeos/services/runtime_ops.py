from __future__ import annotations

import gzip
import hashlib
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.engine.url import make_url

from ..persistence.db import (
    AnalyticsEventRow,
    BillingCheckoutSessionRow,
    BillingLifecycleEventRow,
    BillingRetryAttemptRow,
    ChapterRow,
    ReviewRecordRow,
    SessionRow,
    SubscriptionRow,
    UsageMeterRow,
)
from ..persistence.migrations import inspect_schema_lifecycle
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .data_integrity import DataIntegrityService
from .observability import ObservabilityService
from .review import parse_review_notes


VERIFICATION_TABLES = [
    ("sessions", SessionRow),
    ("chapters", ChapterRow),
    ("review_records", ReviewRecordRow),
    ("subscriptions", SubscriptionRow),
    ("usage_meters", UsageMeterRow),
    ("analytics_events", AnalyticsEventRow),
    ("billing_checkout_sessions", BillingCheckoutSessionRow),
    ("billing_lifecycle_events", BillingLifecycleEventRow),
    ("billing_retry_attempts", BillingRetryAttemptRow),
]

POSTGRES_RESTORE_REQUEST_ASSET_TYPE = "runtime_restore_request"
POSTGRES_RESTORE_REQUEST_STATUSES = {"requested", "approved", "revoked", "executed"}
POSTGRES_BINARY_ENV_VARS = {
    "pg_dump": "NARRATIVEOS_PG_DUMP_BIN",
    "pg_restore": "NARRATIVEOS_PG_RESTORE_BIN",
    "psql": "NARRATIVEOS_PSQL_BIN",
}
DEFAULT_RUNTIME_RESTORE_APPROVAL_TTL_HOURS = 24


class RuntimeOpsService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        observability_service: Optional[ObservabilityService] = None,
        async_job_service: Optional[Any] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.observability = observability_service or ObservabilityService(repository)
        self.async_job_service = async_job_service
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[3])

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _database_url(self) -> str:
        return self.repository.engine.url.render_as_string(hide_password=False)

    def _backend(self) -> str:
        return self.repository.engine.url.get_backend_name()

    def _sqlite_db_path(self) -> Optional[Path]:
        if self._backend() != "sqlite":
            return None
        database = self.repository.engine.url.database
        if not database:
            return None
        return Path(database)

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _backup_dir(self, output_dir: Optional[str] = None) -> Path:
        if output_dir:
            return Path(output_dir)
        return self.base_dir / "artifacts" / "runtime_backups"

    def _manifest_path(self, backup_dir: Path, backup_id: str) -> Path:
        return backup_dir / f"{backup_id}.json"

    def _read_manifest(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _runtime_restore_approval_ttl_hours(self) -> int:
        try:
            return max(1, int(os.getenv("NARRATIVEOS_RUNTIME_RESTORE_APPROVAL_TTL_HOURS", str(DEFAULT_RUNTIME_RESTORE_APPROVAL_TTL_HOURS))))
        except (TypeError, ValueError):
            return DEFAULT_RUNTIME_RESTORE_APPROVAL_TTL_HOURS

    def _redacted_database_url(self, database_url: Optional[str] = None) -> str:
        target = str(database_url or self._database_url())
        try:
            return make_url(target).render_as_string(hide_password=True)
        except Exception:
            return target

    def _database_identity(self, database_url: Optional[str] = None) -> str:
        target = str(database_url or self._database_url())
        try:
            url = make_url(target)
            host = url.host or "localhost"
            port = f":{url.port}" if url.port else ""
            database = f"/{url.database}" if url.database else ""
            username = f"{url.username}@" if url.username else ""
            return f"{url.drivername}://{username}{host}{port}{database}"
        except Exception:
            return self._redacted_database_url(target)

    def _hash_json(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _guess_manifest_paths(self, data_path: Path) -> List[Path]:
        candidates = [data_path.with_suffix(".json")]
        stripped = data_path
        for _ in data_path.suffixes:
            stripped = stripped.with_suffix("")
            candidates.append(stripped.with_suffix(".json"))
        deduped: List[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _resolve_binary(self, tool_name: str) -> Dict[str, Any]:
        env_var = POSTGRES_BINARY_ENV_VARS[tool_name]
        requested_path = str(os.getenv(env_var, "") or "").strip() or None
        resolved_path = requested_path or shutil.which(tool_name)
        version = None
        available = bool(resolved_path and Path(resolved_path).exists())
        if available:
            try:
                completed = subprocess.run(
                    [str(resolved_path), "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                version = (completed.stdout or completed.stderr or "").strip().splitlines()[0] if (completed.stdout or completed.stderr) else None
            except Exception:
                version = None
        return {
            "tool": tool_name,
            "env_var": env_var,
            "requested_path": requested_path,
            "resolved_path": resolved_path,
            "available": available,
            "version": version,
        }

    def _resolve_binary_map(self, tools: List[str]) -> Dict[str, Dict[str, Any]]:
        return {tool: self._resolve_binary(tool) for tool in tools}

    def _infer_backup_format(self, backup_path: Path, manifest: Optional[Dict[str, Any]] = None) -> str:
        if manifest and manifest.get("backup_format"):
            return str(manifest.get("backup_format"))
        lower_name = backup_path.name.lower()
        if lower_name.endswith(".sql.gz"):
            return "sql_gzip"
        if lower_name.endswith(".sql"):
            return "sql"
        return "custom"

    def _required_restore_tool(self, backup_format: str) -> str:
        return "pg_restore" if backup_format == "custom" else "psql"

    def _required_tools_for_backend_operation(self, *, action: str, backup_format: Optional[str] = None) -> List[str]:
        if action == "backup":
            return ["pg_dump"]
        if action == "restore":
            if backup_format == "custom":
                return ["pg_restore"]
            return ["psql"]
        return []

    def _missing_required_tools(self, resolution: Dict[str, Dict[str, Any]], required_tools: List[str]) -> List[str]:
        return [tool for tool in required_tools if not resolution.get(tool, {}).get("available")]

    def _postgres_ops_dir(self, execution_id: str) -> Path:
        return self.base_dir / "artifacts" / "runtime_postgres_ops" / execution_id

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _run_subprocess(
        self,
        command: List[str],
        *,
        input_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        completed = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "exit_code": int(completed.returncode),
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }

    def _build_command_preview(self, command: List[str]) -> str:
        return " ".join(shlex.quote(part) for part in command)

    def _resolve_backup_reference(self, backup_path: str) -> Dict[str, Any]:
        source_path = Path(str(backup_path))
        manifest_path = source_path if source_path.suffix == ".json" else None
        manifest: Dict[str, Any] = {}
        data_path = source_path
        if manifest_path is not None:
            manifest = self._read_manifest(manifest_path)
            data_path = Path(str(manifest.get("backup_path") or ""))
        else:
            for candidate in self._guess_manifest_paths(source_path):
                if candidate.exists():
                    manifest_path = candidate
                    manifest = self._read_manifest(candidate)
                    break
        if manifest and not data_path:
            data_path = Path(str(manifest.get("backup_path") or ""))
        if not data_path.exists():
            raise FileNotFoundError(str(data_path))
        backup_format = self._infer_backup_format(data_path, manifest)
        manifest_sha256 = self._sha256_file(manifest_path) if manifest_path and manifest_path.exists() else None
        recorded_backup_sha256 = manifest.get("sha256")
        backup_sha256 = self._sha256_file(data_path)
        return {
            "source_path": str(source_path),
            "data_path": str(data_path),
            "manifest_path": str(manifest_path) if manifest_path else None,
            "manifest": manifest,
            "backup_format": backup_format,
            "backup_sha256": backup_sha256,
            "recorded_backup_sha256": recorded_backup_sha256,
            "manifest_sha256": manifest_sha256,
            "backup_created_at": manifest.get("created_at"),
            "schema_lifecycle_status": manifest.get("schema_lifecycle_status"),
            "verification_snapshot": manifest.get("verification_snapshot"),
            "backup_tool": manifest.get("backup_tool"),
        }

    def _restore_request_record(self, *, request_id: str, status: str, reviewer_id: str, notes: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "asset_type": POSTGRES_RESTORE_REQUEST_ASSET_TYPE,
            "asset_id": request_id,
            "status": status,
            "reviewer_id": reviewer_id,
            "notes": json.dumps(notes, ensure_ascii=False),
        }

    def _restore_request_records(self, request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(asset_type=POSTGRES_RESTORE_REQUEST_ASSET_TYPE, asset_id=request_id)
        return [dict(item) for item in records]

    def _latest_restore_request_record(self, request_id: str, *, status: Optional[str] = None) -> Optional[Dict[str, Any]]:
        records = self._restore_request_records(request_id)
        for record in records:
            if status is None or record.get("status") == status:
                payload = parse_review_notes(record.get("notes"))
                return {**record, "payload": payload}
        return None

    def _request_approval_state(self, request_id: str) -> Dict[str, Any]:
        latest = self._latest_restore_request_record(request_id)
        requested = self._latest_restore_request_record(request_id, status="requested")
        approved = self._latest_restore_request_record(request_id, status="approved")
        revoked = self._latest_restore_request_record(request_id, status="revoked")
        executed = self._latest_restore_request_record(request_id, status="executed")
        approval_ttl_hours = self._runtime_restore_approval_ttl_hours()
        approval_expires_at = None
        approval_status = "unapproved"
        if approved:
            approved_at = approved.get("updated_at")
            try:
                approved_dt = datetime.fromisoformat(str(approved_at).replace("Z", "+00:00"))
                if approved_dt.tzinfo is None:
                    approved_dt = approved_dt.replace(tzinfo=timezone.utc)
                expires_dt = approved_dt.astimezone(timezone.utc) + timedelta(hours=approval_ttl_hours)
            except Exception:
                expires_dt = None
            if expires_dt is not None:
                approval_expires_at = expires_dt.isoformat()
                approval_status = "approved" if expires_dt > datetime.now(timezone.utc) else "stale"
            else:
                approval_status = "stale"
        if revoked and latest and latest.get("review_id") == revoked.get("review_id"):
            approval_status = "revoked"
        if executed and latest and latest.get("review_id") == executed.get("review_id"):
            approval_status = "executed"
        return {
            "latest_record": latest,
            "requested_record": requested,
            "approved_record": approved,
            "revoked_record": revoked,
            "executed_record": executed,
            "approval_status": approval_status,
            "approval_expires_at": approval_expires_at,
            "approval_ttl_hours": approval_ttl_hours,
        }

    def list_restore_requests(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(asset_type=POSTGRES_RESTORE_REQUEST_ASSET_TYPE)
        request_ids: List[str] = []
        for record in records:
            request_id = str(record.get("asset_id") or "")
            if request_id and request_id not in request_ids:
                request_ids.append(request_id)
        summaries: List[Dict[str, Any]] = []
        for request_id in request_ids[: limit * 3]:
            state = self._request_approval_state(request_id)
            requested = state["requested_record"]
            approved = state["approved_record"]
            latest = state["latest_record"]
            payload = dict((requested or latest or {}).get("payload") or {})
            summaries.append(
                {
                    "request_id": request_id,
                    "latest_status": latest.get("status") if latest else None,
                    "approval_status": state["approval_status"],
                    "approval_expires_at": state["approval_expires_at"],
                    "requested_by": requested.get("reviewer_id") if requested else None,
                    "requested_at": requested.get("updated_at") if requested else None,
                    "approved_by": approved.get("reviewer_id") if approved else None,
                    "approved_at": approved.get("updated_at") if approved else None,
                    "executed_by": ((state["executed_record"] or {}).get("payload") or {}).get("executed_by") if state["executed_record"] else None,
                    "backup_path": payload.get("backup_path"),
                    "backup_format": payload.get("backup_format"),
                    "backup_sha256": payload.get("backup_sha256"),
                    "manifest_sha256": payload.get("manifest_sha256"),
                    "target_database_identity": payload.get("target_database_identity"),
                    "reason": payload.get("reason"),
                    "binary_resolution": payload.get("binary_resolution", {}),
                    "restore_decision": payload.get("restore_decision"),
                    "restore_decision_hints": payload.get("restore_decision_hints", []),
                    "executed_job_id": ((state["executed_record"] or {}).get("payload") or {}).get("job_id") if state["executed_record"] else None,
                    "artifact_path": ((state["executed_record"] or {}).get("payload") or {}).get("artifact_path") if state["executed_record"] else None,
                }
            )
        summaries.sort(key=lambda item: str(item.get("requested_at") or ""), reverse=True)
        return summaries[:limit]

    def _postgres_backup_command(self, *, binary_path: str, backup_path: Path) -> List[str]:
        return [binary_path, "--format=custom", "--file", str(backup_path), self._database_url()]

    def _postgres_restore_command(self, *, binary_path: str, backup_path: Path, backup_format: str) -> List[str]:
        if backup_format == "custom":
            return [
                binary_path,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                self._database_url(),
                str(backup_path),
            ]
        if backup_format == "sql":
            return [binary_path, self._database_url(), "-v", "ON_ERROR_STOP=1", "-f", str(backup_path)]
        return [binary_path, self._database_url(), "-v", "ON_ERROR_STOP=1"]

    def _postgres_wrapper_preview(self, *, action: str, binary_path: str, backup_path: Path, backup_format: Optional[str] = None) -> str:
        redacted_url = self._redacted_database_url()
        if action == "backup":
            preview_command = [binary_path, "--format=custom", "--file", str(backup_path), redacted_url]
            return self._build_command_preview(preview_command)
        if backup_format == "custom":
            preview_command = [
                binary_path,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                redacted_url,
                str(backup_path),
            ]
            return self._build_command_preview(preview_command)
        if backup_format == "sql":
            preview_command = [binary_path, redacted_url, "-v", "ON_ERROR_STOP=1", "-f", str(backup_path)]
            return self._build_command_preview(preview_command)
        return f"gunzip -c {shlex.quote(str(backup_path))} | {shlex.quote(binary_path)} {shlex.quote(redacted_url)} -v ON_ERROR_STOP=1"

    def _write_postgres_wrapper(
        self,
        *,
        artifact_dir: Path,
        action: str,
        backup_path: Path,
        binary_path: str,
        backup_format: Optional[str] = None,
    ) -> str:
        wrapper_name = "backup.sh" if action == "backup" else "restore.sh"
        lines = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
        ]
        if action == "backup":
            lines.extend(
                [
                    f'PG_DUMP_BIN="${{PG_DUMP_BIN:-{binary_path}}}"',
                    f'TARGET_DSN="${{TARGET_DSN:-{self._redacted_database_url()}}}"',
                    f'"$PG_DUMP_BIN" --format=custom --file {shlex.quote(str(backup_path))} "$TARGET_DSN"',
                ]
            )
        elif backup_format == "custom":
            lines.extend(
                [
                    f'PG_RESTORE_BIN="${{PG_RESTORE_BIN:-{binary_path}}}"',
                    f'TARGET_DSN="${{TARGET_DSN:-{self._redacted_database_url()}}}"',
                    f'"$PG_RESTORE_BIN" --clean --if-exists --no-owner --no-privileges --dbname "$TARGET_DSN" {shlex.quote(str(backup_path))}',
                ]
            )
        elif backup_format == "sql":
            lines.extend(
                [
                    f'PSQL_BIN="${{PSQL_BIN:-{binary_path}}}"',
                    f'TARGET_DSN="${{TARGET_DSN:-{self._redacted_database_url()}}}"',
                    f'"$PSQL_BIN" "$TARGET_DSN" -v ON_ERROR_STOP=1 -f {shlex.quote(str(backup_path))}',
                ]
            )
        else:
            lines.extend(
                [
                    f'PSQL_BIN="${{PSQL_BIN:-{binary_path}}}"',
                    f'TARGET_DSN="${{TARGET_DSN:-{self._redacted_database_url()}}}"',
                    f'gunzip -c {shlex.quote(str(backup_path))} | "$PSQL_BIN" "$TARGET_DSN" -v ON_ERROR_STOP=1',
                ]
            )
        wrapper_path = artifact_dir / wrapper_name
        self._write_text(wrapper_path, "\n".join(lines) + "\n")
        wrapper_path.chmod(0o750)
        return str(wrapper_path)

    def _build_postgres_execution_result(
        self,
        *,
        execution_id: str,
        action: str,
        artifact_dir: Path,
        command_preview: str,
        binary_resolution: Dict[str, Dict[str, Any]],
        backup_path: str,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
        job_status_override: str,
        backup_format: Optional[str] = None,
        request_id: Optional[str] = None,
        approval_review_id: Optional[str] = None,
        pre_restore_verification: Optional[Dict[str, Any]] = None,
        post_restore_verification: Optional[Dict[str, Any]] = None,
        verification_comparison: Optional[Dict[str, Any]] = None,
        pre_restore_backup: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        stdout_path = artifact_dir / "stdout.log"
        stderr_path = artifact_dir / "stderr.log"
        result_path = artifact_dir / "result.json"
        self._write_text(stdout_path, stdout_text)
        self._write_text(stderr_path, stderr_text)
        result = {
            "job_id": execution_id,
            "action": action,
            "status": "completed" if exit_code == 0 else "failed",
            "request_id": request_id,
            "approval_review_id": approval_review_id,
            "backup_format": backup_format,
            "target_path": backup_path,
            "redacted_command": command_preview,
            "binary_resolution": binary_resolution,
            "started_at": started_at or self._utcnow(),
            "finished_at": finished_at or self._utcnow(),
            "exit_code": exit_code,
            "pre_restore_verification": pre_restore_verification,
            "post_restore_verification": post_restore_verification,
            "verification_comparison": verification_comparison,
            "pre_restore_backup": pre_restore_backup,
            "error": error,
            "artifacts": {
                "artifact_dir": str(artifact_dir),
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "result_json": str(result_path),
            },
            "_job_status_override": job_status_override,
        }
        self._write_text(result_path, json.dumps(result, ensure_ascii=False, indent=2))
        return result

    def request_restore(
        self,
        *,
        backup_path: str,
        requested_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not self._backend().startswith("postgres"):
            raise ValueError("postgres_backend_required")
        if not str(requested_by or "").strip():
            raise ValueError("requested_by_required")
        if not str(reason or "").strip():
            raise ValueError("restore_reason_required")
        backup_ref = self._resolve_backup_reference(backup_path)
        binary_resolution = self._resolve_binary_map(
            self._required_tools_for_backend_operation(action="restore", backup_format=backup_ref["backup_format"])
        )
        missing = self._missing_required_tools(
            binary_resolution,
            self._required_tools_for_backend_operation(action="restore", backup_format=backup_ref["backup_format"]),
        )
        if missing:
            raise ValueError(f"postgres_restore_binary_missing:{','.join(missing)}")
        plan = self.restore_backup(backup_path=backup_ref["data_path"], dry_run=True)
        request_id = f"restore_request_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        payload = {
            "request_id": request_id,
            "backup_path": backup_ref["data_path"],
            "source_path": backup_ref["source_path"],
            "manifest_path": backup_ref["manifest_path"],
            "backup_format": backup_ref["backup_format"],
            "backup_sha256": backup_ref["backup_sha256"],
            "manifest_sha256": backup_ref["manifest_sha256"],
            "backup_created_at": backup_ref["backup_created_at"],
            "requested_by": requested_by,
            "reason": reason,
            "target_database_identity": self._database_identity(),
            "requested_at": self._utcnow(),
            "binary_resolution": binary_resolution,
            "restore_decision": plan.get("restore_decision"),
            "restore_decision_hints": plan.get("restore_decision_hints", []),
            "restore_verification_steps": plan.get("restore_verification_steps", []),
        }
        self.repository.save_review_record(
            self._restore_request_record(
                request_id=request_id,
                status="requested",
                reviewer_id=requested_by,
                notes=payload,
            )
        )
        return next(item for item in self.list_restore_requests(limit=50) if item["request_id"] == request_id)

    def approve_restore_request(self, *, request_id: str, approver_id: str, reason: str) -> Dict[str, Any]:
        if not str(approver_id or "").strip():
            raise ValueError("approver_id_required")
        state = self._request_approval_state(request_id)
        requested = state["requested_record"]
        latest = state["latest_record"]
        if requested is None:
            raise KeyError(f"unknown_restore_request:{request_id}")
        if latest and latest.get("status") in {"revoked", "executed"}:
            raise ValueError(f"restore_request_not_approvable:{latest.get('status')}")
        if str(requested.get("reviewer_id") or "") == str(approver_id):
            raise ValueError("restore_request_self_approval_forbidden")
        payload = {
            **dict(requested.get("payload") or {}),
            "approved_by": approver_id,
            "approval_reason": reason,
            "approved_at": self._utcnow(),
            "approval_ttl_hours": self._runtime_restore_approval_ttl_hours(),
        }
        self.repository.save_review_record(
            self._restore_request_record(
                request_id=request_id,
                status="approved",
                reviewer_id=approver_id,
                notes=payload,
            )
        )
        return next(item for item in self.list_restore_requests(limit=50) if item["request_id"] == request_id)

    def revoke_restore_request(self, *, request_id: str, reviewer_id: str, reason: str) -> Dict[str, Any]:
        state = self._request_approval_state(request_id)
        requested = state["requested_record"]
        if requested is None:
            raise KeyError(f"unknown_restore_request:{request_id}")
        payload = {
            **dict(requested.get("payload") or {}),
            "revoked_by": reviewer_id,
            "revoke_reason": reason,
            "revoked_at": self._utcnow(),
        }
        self.repository.save_review_record(
            self._restore_request_record(
                request_id=request_id,
                status="revoked",
                reviewer_id=reviewer_id,
                notes=payload,
            )
        )
        return next(item for item in self.list_restore_requests(limit=50) if item["request_id"] == request_id)

    def _recovery_drill_dir(self, output_dir: Optional[str] = None) -> Path:
        if output_dir:
            return Path(output_dir)
        return self.base_dir / "artifacts" / "recovery_drills"

    def _recovery_drill_path(self, drill_dir: Path, drill_id: str) -> Path:
        return drill_dir / f"{drill_id}.json"

    def _table_count_snapshot(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        with self.repository.SessionLocal() as session:
            for label, row_cls in VERIFICATION_TABLES:
                counts[label] = int(session.execute(select(func.count()).select_from(row_cls)).scalar_one())
        return counts

    def _verification_snapshot(self, *, source: str) -> Dict[str, Any]:
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        return {
            "generated_at": self._utcnow(),
            "source": source,
            "backend": self._backend(),
            "schema_status": schema_lifecycle.get("status"),
            "alembic_status": (schema_lifecycle.get("alembic") or {}).get("status"),
            "alembic_current_revision": (schema_lifecycle.get("alembic") or {}).get("current_revision"),
            "alembic_head_revision": (schema_lifecycle.get("alembic") or {}).get("head_revision"),
            "table_counts": self._table_count_snapshot(),
        }

    def _backup_age_hours(self, created_at: Optional[str]) -> Optional[float]:
        if not created_at:
            return None
        try:
            created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            return round((datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)).total_seconds() / 3600.0, 2)
        except Exception:
            return None

    def _compare_verification_snapshots(self, expected: Optional[Dict[str, Any]], actual: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not expected or not actual:
            return {
                "status": "incomplete",
                "mismatches": ["verification_snapshot_missing"],
            }
        mismatches: List[str] = []
        if expected.get("backend") != actual.get("backend"):
            mismatches.append("backend")
        if expected.get("schema_status") != actual.get("schema_status"):
            mismatches.append("schema_status")
        if expected.get("alembic_head_revision") != actual.get("alembic_head_revision"):
            mismatches.append("alembic_head_revision")
        if expected.get("alembic_current_revision") != actual.get("alembic_current_revision"):
            mismatches.append("alembic_current_revision")
        expected_counts = dict(expected.get("table_counts") or {})
        actual_counts = dict(actual.get("table_counts") or {})
        for key, value in expected_counts.items():
            if actual_counts.get(key) != value:
                mismatches.append(f"table_counts.{key}")
        return {
            "status": "matched" if not mismatches else "mismatch",
            "mismatches": mismatches,
        }

    def _restore_decision_summary(
        self,
        *,
        manifest: Dict[str, Any],
        backup_snapshot: Optional[Dict[str, Any]],
        current_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        hints: List[str] = []
        decision = "ready_to_restore"
        backup_age_hours = self._backup_age_hours(manifest.get("created_at"))
        backup_backend = manifest.get("backend") or current_snapshot.get("backend")
        if backup_backend != current_snapshot.get("backend"):
            decision = "manual_review_required"
            hints.append("backup_backend_differs_from_current_backend")
        if backup_age_hours is None:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("backup_age_unknown")
        elif backup_age_hours > 72:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("backup_stale_over_72h")
        elif backup_age_hours > 24:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("backup_older_than_24h")
        if (manifest.get("schema_lifecycle_status") or "") not in {"up_to_date", "pending_migrations"}:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("backup_schema_lifecycle_not_clean")
        if (current_snapshot.get("schema_status") or "") not in {"up_to_date", "pending_migrations"}:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("current_schema_lifecycle_not_clean")
        if not backup_snapshot:
            if decision != "manual_review_required":
                decision = "restore_with_caution"
            hints.append("backup_verification_snapshot_missing")
        if not hints:
            hints.append("restore_ready_for_operator_verification")
        return {
            "decision": decision,
            "hints": hints,
            "backup_age_hours": backup_age_hours,
        }

    def _restore_verification_steps(self) -> List[str]:
        return [
            "1. Verify GET /health returns ok before restore.",
            "2. Capture GET /v1/ops/schema-lifecycle and GET /v1/ops/data-integrity before restore.",
            "3. Record the selected backup manifest path and verification snapshot.",
            "4. For sqlite, take a pre_restore_snapshot before copying bytes back into place.",
            "5. After restore, re-check /health, /v1/ops/schema-lifecycle, /v1/ops/data-integrity, /v1/ops/provider-runtime-metrics, and benchmark smoke.",
        ]

    def _restore_decision_hints_from_latest_backup(self, recent_backups: List[Dict[str, Any]]) -> List[str]:
        if not recent_backups:
            return ["no_recent_backup_available"]
        latest = recent_backups[0]
        summary = self._restore_decision_summary(
            manifest=latest,
            backup_snapshot=latest.get("verification_snapshot"),
            current_snapshot=self._verification_snapshot(source="current_runtime"),
        )
        return summary["hints"]

    def list_recovery_drills(self, *, output_dir: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        drill_dir = self._recovery_drill_dir(output_dir)
        if not drill_dir.exists():
            return []
        drills: List[Dict[str, Any]] = []
        for path in sorted(drill_dir.glob("*.json"), reverse=True):
            try:
                drills.append(self._read_manifest(path))
            except Exception:
                continue
        drills.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return drills[:limit]

    def list_backups(self, *, output_dir: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        backup_dir = self._backup_dir(output_dir)
        if not backup_dir.exists():
            return []
        manifests = []
        for path in sorted(backup_dir.glob("*.json"), reverse=True):
            try:
                manifests.append(self._read_manifest(path))
            except Exception:
                continue
        manifests.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return manifests[:limit]

    def _execute_postgres_backup(
        self,
        *,
        manifest: Dict[str, Any],
        backup_path: Path,
        binary_resolution: Dict[str, Dict[str, Any]],
        job_id: str,
    ) -> Dict[str, Any]:
        artifact_dir = self._postgres_ops_dir(job_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        resolved_pg_dump = binary_resolution["pg_dump"].get("resolved_path")
        command_preview = self._postgres_wrapper_preview(
            action="backup",
            binary_path=str(resolved_pg_dump or "pg_dump"),
            backup_path=backup_path,
        )
        wrapper_path = self._write_postgres_wrapper(
            artifact_dir=artifact_dir,
            action="backup",
            backup_path=backup_path,
            binary_path=str(resolved_pg_dump or "pg_dump"),
        )
        missing = self._missing_required_tools(binary_resolution, ["pg_dump"])
        if missing:
            result = self._build_postgres_execution_result(
                execution_id=job_id,
                action="backup",
                artifact_dir=artifact_dir,
                command_preview=command_preview,
                binary_resolution=binary_resolution,
                backup_path=str(backup_path),
                exit_code=127,
                stdout_text="",
                stderr_text=f"missing required postgres binary: {','.join(missing)}\n",
                job_status_override="failed",
                backup_format="custom",
                error=f"postgres_backup_binary_missing:{','.join(missing)}",
                started_at=self._utcnow(),
                finished_at=self._utcnow(),
            )
            result["artifacts"]["wrapper_script"] = wrapper_path
            return result
        started_at = self._utcnow()
        command = self._postgres_backup_command(binary_path=str(resolved_pg_dump), backup_path=backup_path)
        completed = self._run_subprocess(command)
        finished_at = self._utcnow()
        if completed["exit_code"] == 0 and backup_path.exists():
            manifest["sha256"] = self._sha256_file(backup_path)
            manifest["size_bytes"] = backup_path.stat().st_size
            manifest["status"] = "completed"
        else:
            manifest["status"] = "failed"
        result = self._build_postgres_execution_result(
            execution_id=job_id,
            action="backup",
            artifact_dir=artifact_dir,
            command_preview=command_preview,
            binary_resolution=binary_resolution,
            backup_path=str(backup_path),
            exit_code=completed["exit_code"],
            stdout_text=completed["stdout"],
            stderr_text=completed["stderr"],
            job_status_override="succeeded" if completed["exit_code"] == 0 else "failed",
            backup_format="custom",
            error=None if completed["exit_code"] == 0 else "pg_dump_failed",
            started_at=started_at,
            finished_at=finished_at,
        )
        result["artifacts"]["wrapper_script"] = wrapper_path
        return result

    def _execute_postgres_restore(
        self,
        *,
        backup_path: Path,
        backup_format: str,
        binary_resolution: Dict[str, Dict[str, Any]],
        job_id: str,
        request_id: str,
        approval_review_id: Optional[str],
        backup_snapshot: Optional[Dict[str, Any]],
        pre_restore_verification: Dict[str, Any],
        pre_restore_backup: Dict[str, Any],
    ) -> Dict[str, Any]:
        artifact_dir = self._postgres_ops_dir(job_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        required_tool = self._required_restore_tool(backup_format)
        resolved_tool = binary_resolution[required_tool].get("resolved_path")
        command_preview = self._postgres_wrapper_preview(
            action="restore",
            binary_path=str(resolved_tool or required_tool),
            backup_path=backup_path,
            backup_format=backup_format,
        )
        wrapper_path = self._write_postgres_wrapper(
            artifact_dir=artifact_dir,
            action="restore",
            backup_path=backup_path,
            binary_path=str(resolved_tool or required_tool),
            backup_format=backup_format,
        )
        missing = self._missing_required_tools(binary_resolution, [required_tool])
        if missing:
            result = self._build_postgres_execution_result(
                execution_id=job_id,
                action="restore",
                artifact_dir=artifact_dir,
                command_preview=command_preview,
                binary_resolution=binary_resolution,
                backup_path=str(backup_path),
                exit_code=127,
                stdout_text="",
                stderr_text=f"missing required postgres binary: {','.join(missing)}\n",
                job_status_override="failed",
                backup_format=backup_format,
                request_id=request_id,
                approval_review_id=approval_review_id,
                pre_restore_verification=pre_restore_verification,
                pre_restore_backup=pre_restore_backup,
                error=f"postgres_restore_binary_missing:{','.join(missing)}",
                started_at=self._utcnow(),
                finished_at=self._utcnow(),
            )
            result["artifacts"]["wrapper_script"] = wrapper_path
            return result

        started_at = self._utcnow()
        if backup_format == "sql_gzip":
            with gzip.open(backup_path, "rt", encoding="utf-8") as handle:
                sql_text = handle.read()
            completed = self._run_subprocess(
                self._postgres_restore_command(binary_path=str(resolved_tool), backup_path=backup_path, backup_format=backup_format),
                input_text=sql_text,
            )
        else:
            completed = self._run_subprocess(
                self._postgres_restore_command(binary_path=str(resolved_tool), backup_path=backup_path, backup_format=backup_format)
            )
        finished_at = self._utcnow()
        post_restore_verification = self._verification_snapshot(source="post_restore_runtime")
        verification_comparison = self._compare_verification_snapshots(backup_snapshot, post_restore_verification)
        result = self._build_postgres_execution_result(
            execution_id=job_id,
            action="restore",
            artifact_dir=artifact_dir,
            command_preview=command_preview,
            binary_resolution=binary_resolution,
            backup_path=str(backup_path),
            exit_code=completed["exit_code"],
            stdout_text=completed["stdout"],
            stderr_text=completed["stderr"],
            job_status_override="succeeded" if completed["exit_code"] == 0 else "failed",
            backup_format=backup_format,
            request_id=request_id,
            approval_review_id=approval_review_id,
            pre_restore_verification=pre_restore_verification,
            post_restore_verification=post_restore_verification,
            verification_comparison=verification_comparison,
            pre_restore_backup=pre_restore_backup,
            error=None if completed["exit_code"] == 0 else f"{required_tool}_restore_failed",
            started_at=started_at,
            finished_at=finished_at,
        )
        result["artifacts"]["wrapper_script"] = wrapper_path
        return result

    def create_backup(
        self,
        *,
        label: Optional[str] = None,
        output_dir: Optional[str] = None,
        dry_run: bool = False,
        execute_postgres: bool = False,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        backup_dir = self._backup_dir(output_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backend = self._backend()
        backup_id = "backup_%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        created_at = self._utcnow()
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        verification_snapshot = self._verification_snapshot(source="backup_source")
        manifest: Dict[str, Any] = {
            "backup_id": backup_id,
            "label": label or "",
            "created_at": created_at,
            "backend": backend,
            "database_url": self._redacted_database_url(),
            "target_database_identity": self._database_identity(),
            "schema_lifecycle_status": schema_lifecycle.get("status"),
            "verification_snapshot": verification_snapshot,
            "dry_run": dry_run,
            "status": "planned" if dry_run else "completed",
            "backup_path": None,
            "restore_instructions": [],
        }

        if backend == "sqlite":
            source = self._sqlite_db_path()
            if source is None or not source.exists():
                raise ValueError("sqlite_database_file_missing")
            backup_path = backup_dir / f"{backup_id}.sqlite3"
            manifest["backup_path"] = str(backup_path)
            manifest["restore_instructions"] = [f"copy {backup_path} back to {source}"]
            if not dry_run:
                self.repository.engine.dispose()
                shutil.copy2(source, backup_path)
                manifest["size_bytes"] = backup_path.stat().st_size
                manifest["sha256"] = self._sha256_file(backup_path)
            else:
                manifest["size_bytes"] = source.stat().st_size
                manifest["sha256"] = None
        else:
            planned_path = backup_dir / f"{backup_id}.dump"
            binary_resolution = self._resolve_binary_map(["pg_dump", "pg_restore"])
            manifest["backup_path"] = str(planned_path)
            manifest["backup_format"] = "custom"
            manifest["backup_tool"] = "pg_dump"
            manifest["binary_resolution"] = binary_resolution
            manifest["backup_command_preview"] = self._postgres_wrapper_preview(
                action="backup",
                binary_path=str(binary_resolution["pg_dump"].get("resolved_path") or "pg_dump"),
                backup_path=planned_path,
            )
            manifest["restore_instructions"] = [
                self._postgres_wrapper_preview(
                    action="backup",
                    binary_path=str(binary_resolution["pg_dump"].get("resolved_path") or "pg_dump"),
                    backup_path=planned_path,
                ),
                self._postgres_wrapper_preview(
                    action="restore",
                    binary_path=str(binary_resolution["pg_restore"].get("resolved_path") or "pg_restore"),
                    backup_path=planned_path,
                    backup_format="custom",
                ),
            ]
            manifest["plan_only"] = not execute_postgres
            missing = self._missing_required_tools(binary_resolution, ["pg_dump"])
            if missing:
                manifest["status"] = "blocked"
                manifest["blocked_reason"] = f"postgres_backup_binary_missing:{','.join(missing)}"
            elif not execute_postgres:
                manifest["status"] = "planned"
            else:
                execution_result = self._execute_postgres_backup(
                    manifest=manifest,
                    backup_path=planned_path,
                    binary_resolution=binary_resolution,
                    job_id=job_id or backup_id,
                )
                manifest["status"] = execution_result["status"]
                manifest["artifacts"] = execution_result.get("artifacts", {})
                if execution_result.get("error"):
                    manifest["error"] = execution_result["error"]
                self._manifest_path(backup_dir, backup_id).write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return {
                    **manifest,
                    **execution_result,
                    "backup_id": backup_id,
                    "label": label or "",
                    "created_at": created_at,
                    "backend": backend,
                    "database_url": self._redacted_database_url(),
                    "dry_run": dry_run,
                }

        self._manifest_path(backup_dir, backup_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def restore_backup(
        self,
        *,
        backup_path: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        backup_ref = self._resolve_backup_reference(backup_path)
        data_path = Path(backup_ref["data_path"])
        manifest = dict(backup_ref["manifest"] or {})
        backend = manifest.get("backend") or self._backend()
        current_snapshot = self._verification_snapshot(source="pre_restore_runtime")
        backup_snapshot = backup_ref.get("verification_snapshot")
        backup_format = backup_ref["backup_format"]
        binary_resolution = self._resolve_binary_map(
            self._required_tools_for_backend_operation(action="restore", backup_format=backup_format)
        )
        decision_summary = self._restore_decision_summary(
            manifest=manifest,
            backup_snapshot=backup_snapshot,
            current_snapshot=current_snapshot,
        )
        result = {
            "backup_path": str(data_path),
            "backend": backend,
            "dry_run": dry_run,
            "status": "planned" if dry_run else "completed",
            "restored_at": self._utcnow(),
            "pre_restore_backup": None,
            "backup_manifest_created_at": manifest.get("created_at"),
            "backup_verification_snapshot": backup_snapshot,
            "pre_restore_verification": current_snapshot,
            "backup_format": backup_format,
            "backup_sha256": backup_ref.get("backup_sha256"),
            "manifest_sha256": backup_ref.get("manifest_sha256"),
            "binary_resolution": binary_resolution,
            "required_restore_tool": self._required_restore_tool(backup_format),
            "restore_decision": decision_summary["decision"],
            "restore_decision_hints": decision_summary["hints"],
            "backup_age_hours": decision_summary["backup_age_hours"],
            "restore_verification_steps": self._restore_verification_steps(),
            "post_restore_verification": None,
            "verification_status": "planned" if dry_run else "pending",
        }
        if backend == "sqlite":
            target = self._sqlite_db_path()
            if target is None:
                raise ValueError("sqlite_database_file_missing")
            if not data_path.exists():
                raise FileNotFoundError(str(data_path))
            pre_restore = self.create_backup(label="pre_restore_snapshot", output_dir=str(data_path.parent), dry_run=False)
            result["pre_restore_backup"] = pre_restore
            if not dry_run:
                self.repository.engine.dispose()
                for sidecar in [target, target.with_name(f"{target.name}-wal"), target.with_name(f"{target.name}-shm")]:
                    if sidecar.exists():
                        sidecar.unlink()
                shutil.copy2(data_path, target)
                result["post_restore_verification"] = self._verification_snapshot(source="post_restore_runtime")
                result["verification_status"] = self._compare_verification_snapshots(
                    backup_snapshot,
                    result["post_restore_verification"],
                )["status"]
            result["target_database"] = str(target)
        else:
            result["status"] = "planned"
            result["restore_instructions"] = [
                self._postgres_wrapper_preview(
                    action="restore",
                    binary_path=str(binary_resolution[self._required_restore_tool(backup_format)].get("resolved_path") or self._required_restore_tool(backup_format)),
                    backup_path=data_path,
                    backup_format=backup_format,
                )
            ]
            result["plan_only"] = True
            result["verification_status"] = "planned"
            missing = self._missing_required_tools(binary_resolution, [self._required_restore_tool(backup_format)])
            if missing:
                result["status"] = "blocked"
                result["blocked_reason"] = f"postgres_restore_binary_missing:{','.join(missing)}"
        return result

    def execute_restore_request(
        self,
        *,
        request_id: str,
        job_id: str,
        requested_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._backend().startswith("postgres"):
            raise ValueError("postgres_backend_required")
        approval_state = self._request_approval_state(request_id)
        requested = approval_state["requested_record"]
        approved = approval_state["approved_record"]
        latest = approval_state["latest_record"]
        if requested is None:
            raise KeyError(f"unknown_restore_request:{request_id}")
        if approval_state["approval_status"] != "approved" or approved is None:
            raise PermissionError(f"restore_request_not_approved:{approval_state['approval_status']}")
        if latest and latest.get("status") == "executed":
            raise ValueError("restore_request_already_executed")

        requested_payload = dict(requested.get("payload") or {})
        if requested_by and str(requested_by) == str(requested.get("reviewer_id") or ""):
            raise PermissionError("restore_request_executor_cannot_match_requester")
        backup_ref = self._resolve_backup_reference(str(requested_payload.get("backup_path")))
        if requested_payload.get("backup_sha256") != backup_ref.get("backup_sha256"):
            raise PermissionError("restore_request_backup_fingerprint_mismatch")
        if requested_payload.get("manifest_sha256") != backup_ref.get("manifest_sha256"):
            raise PermissionError("restore_request_manifest_fingerprint_mismatch")

        plan = self.restore_backup(backup_path=str(backup_ref["data_path"]), dry_run=True)
        if plan.get("status") == "blocked":
            return {
                **plan,
                "job_id": job_id,
                "request_id": request_id,
                "_job_status_override": "failed",
                "error": plan.get("blocked_reason"),
                "artifacts": {},
            }

        pre_restore_verification = self._verification_snapshot(source="pre_restore_runtime")
        pre_restore_backup = self.create_backup(
            label=f"pre_restore_snapshot:{request_id}",
            output_dir=str(self._backup_dir()),
            dry_run=False,
            execute_postgres=True,
            job_id=f"{job_id}__pre_restore",
        )
        if pre_restore_backup.get("_job_status_override") == "failed" or pre_restore_backup.get("status") == "failed":
            artifact_dir = self._postgres_ops_dir(job_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            return self._build_postgres_execution_result(
                execution_id=job_id,
                action="restore",
                artifact_dir=artifact_dir,
                command_preview="pre_restore_backup_failed",
                binary_resolution=plan["binary_resolution"],
                backup_path=str(backup_ref["data_path"]),
                exit_code=1,
                stdout_text="",
                stderr_text="pre_restore_backup_failed\n",
                job_status_override="failed",
                backup_format=str(backup_ref["backup_format"]),
                request_id=request_id,
                approval_review_id=approved.get("review_id"),
                pre_restore_verification=pre_restore_verification,
                pre_restore_backup=pre_restore_backup,
                error="pre_restore_backup_failed",
                started_at=self._utcnow(),
                finished_at=self._utcnow(),
            )
        binary_resolution = plan["binary_resolution"]
        execution_result = self._execute_postgres_restore(
            backup_path=Path(str(backup_ref["data_path"])),
            backup_format=str(backup_ref["backup_format"]),
            binary_resolution=binary_resolution,
            job_id=job_id,
            request_id=request_id,
            approval_review_id=approved.get("review_id"),
            backup_snapshot=backup_ref.get("verification_snapshot"),
            pre_restore_verification=pre_restore_verification,
            pre_restore_backup=pre_restore_backup,
        )
        if execution_result.get("_job_status_override") == "succeeded":
            executed_payload = {
                **requested_payload,
                "job_id": job_id,
                "executed_by": requested_by or approved.get("reviewer_id"),
                "executed_at": self._utcnow(),
                "artifact_path": execution_result.get("artifacts", {}).get("result_json"),
                "approval_review_id": approved.get("review_id"),
            }
            self.repository.save_review_record(
                self._restore_request_record(
                    request_id=request_id,
                    status="executed",
                    reviewer_id=requested_by or approved.get("reviewer_id") or "ops_web",
                    notes=executed_payload,
                )
            )
        return execution_result

    def run_recovery_drill(
        self,
        *,
        backup_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_backup_path = backup_path
        recent_backups = self.list_backups(limit=1)
        if not selected_backup_path:
            selected_backup_path = recent_backups[0]["backup_path"] if recent_backups else None
        if not selected_backup_path:
            return {
                "status": "blocked",
                "reason": "backup_missing",
                "generated_at": self._utcnow(),
                "recent_backups": recent_backups,
            }
        restore_plan = self.restore_backup(backup_path=selected_backup_path, dry_run=True)
        drill_dir = self._recovery_drill_dir(output_dir)
        drill_dir.mkdir(parents=True, exist_ok=True)
        drill_id = "recovery_drill_%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        artifact = {
            "drill_id": drill_id,
            "created_at": self._utcnow(),
            "status": "ready" if restore_plan.get("restore_decision") == "ready_to_restore" else "operator_review",
            "backup_path": selected_backup_path,
            "restore_plan": restore_plan,
            "verification_commands": [
                "GET /health",
                "GET /v1/ops/schema-lifecycle",
                "GET /v1/ops/data-integrity",
                "GET /v1/ops/provider-runtime-metrics",
                "bash scripts/run_cross_pack_merge_gate.sh",
            ],
        }
        artifact_path = self._recovery_drill_path(drill_dir, drill_id)
        artifact["artifact_path"] = str(artifact_path)
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return artifact

    def build_deployment_runbook(self) -> Dict[str, Any]:
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        recent_backups = self.list_backups(limit=5)
        recent_recovery_drills = self.list_recovery_drills(limit=3)
        recent_restore_requests = self.list_restore_requests(limit=5)
        recent_restore_jobs = (
            self.async_job_service.list_jobs(job_type="runtime_restore", limit=5)
            if getattr(self, "async_job_service", None) is not None
            else []
        )
        postgres_tooling = self._postgres_tooling_check()
        backend = self._backend()
        return {
            "generated_at": self._utcnow(),
            "backend": backend,
            "database_url": self._redacted_database_url(),
            "schema_lifecycle": schema_lifecycle,
            "recent_backups": recent_backups,
            "recent_recovery_drills": recent_recovery_drills,
            "recent_restore_requests": recent_restore_requests,
            "recent_restore_jobs": recent_restore_jobs,
            "preflight_checks": [
                {
                    "key": "schema_lifecycle",
                    "ok": schema_lifecycle.get("status") in {"up_to_date", "pending_migrations"},
                    "reason": schema_lifecycle.get("status"),
                },
                {
                    "key": "recent_backup_available",
                    "ok": bool(recent_backups),
                    "reason": "backup_available" if recent_backups else "backup_missing",
                },
                {
                    "key": postgres_tooling["key"],
                    "ok": postgres_tooling["status"] in {"pass", "not_applicable"},
                    "reason": postgres_tooling["reason"],
                },
            ],
            "deploy_steps": [
                "1. Inspect schema lifecycle and pending migrations.",
                "2. Create a runtime backup before applying any migration or deploy.",
                "3. Run a recovery drill dry-run or confirm the latest drill artifact is still valid.",
                "4. Apply pending migrations or dry-run them first.",
                "5. Restart API and verify /health plus Ops schema lifecycle endpoint.",
                "6. Run benchmark / merge gate after deploy.",
            ],
            "rollback_steps": [
                "1. If incident scope is infra, inspect runtime incident snapshot first.",
                "2. Compare current runtime verification with the selected backup manifest verification snapshot.",
                "3. Restore latest known-good backup for sqlite, or follow postgres restore instructions.",
                "4. Re-run /health, schema lifecycle, data integrity, provider metrics, and benchmark smoke checks.",
            ],
            "restore_verification_steps": self._restore_verification_steps(),
            "restore_decision_hints": self._restore_decision_hints_from_latest_backup(recent_backups),
            "postgres_tooling": postgres_tooling,
        }

    def _database_connectivity_check(self) -> Dict[str, Any]:
        try:
            with self.repository.engine.begin() as connection:
                connection.execute(text("select 1"))
            return {
                "key": "database_connectivity",
                "status": "pass",
                "reason": "database_query_ok",
            }
        except Exception as exc:
            return {
                "key": "database_connectivity",
                "status": "block",
                "reason": f"database_query_failed:{exc}",
            }

    def _backup_freshness_check(self, recent_backups: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not recent_backups:
            return {
                "key": "recent_backup",
                "status": "block",
                "reason": "backup_missing",
            }
        latest = recent_backups[0]
        created_at = latest.get("created_at")
        try:
            latest_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if latest_dt.tzinfo is None:
                latest_dt = latest_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - latest_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
        except Exception:
            age_hours = None
        if age_hours is None:
            return {
                "key": "recent_backup",
                "status": "warn",
                "reason": "backup_age_unknown",
            }
        if age_hours <= 12:
            return {
                "key": "recent_backup",
                "status": "pass",
                "reason": "backup_recent",
                "age_hours": round(age_hours, 2),
            }
        if age_hours <= 24:
            return {
                "key": "recent_backup",
                "status": "warn",
                "reason": "backup_aging",
                "age_hours": round(age_hours, 2),
            }
        return {
            "key": "recent_backup",
            "status": "block",
            "reason": "backup_stale",
            "age_hours": round(age_hours, 2),
        }

    def _restore_readiness_check(self, recent_backups: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not recent_backups:
            return {
                "key": "restore_readiness",
                "status": "block",
                "reason": "backup_missing",
            }
        latest = recent_backups[0]
        verification_snapshot = latest.get("verification_snapshot")
        if not verification_snapshot:
            return {
                "key": "restore_readiness",
                "status": "warn",
                "reason": "verification_snapshot_missing",
            }
        hints = self._restore_decision_hints_from_latest_backup(recent_backups)
        if any(item.startswith("backup_backend_differs") for item in hints):
            return {
                "key": "restore_readiness",
                "status": "block",
                "reason": "backup_backend_mismatch",
            }
        if any(item in {"backup_stale_over_72h", "backup_verification_snapshot_missing"} for item in hints):
            return {
                "key": "restore_readiness",
                "status": "warn",
                "reason": hints[0],
            }
        return {
            "key": "restore_readiness",
            "status": "pass",
            "reason": "restore_verification_ready",
        }

    def _postgres_tooling_check(self) -> Dict[str, Any]:
        if not self._backend().startswith("postgres"):
            return {
                "key": "postgres_operator_tooling",
                "status": "not_applicable",
                "reason": "non_postgres_backend",
                "binary_resolution": {},
            }
        resolution = self._resolve_binary_map(["pg_dump", "pg_restore", "psql"])
        if not resolution["pg_dump"]["available"]:
            status = "block"
            reason = "pg_dump_missing"
        elif not resolution["pg_restore"]["available"] and not resolution["psql"]["available"]:
            status = "block"
            reason = "pg_restore_and_psql_missing"
        elif not resolution["pg_restore"]["available"] or not resolution["psql"]["available"]:
            status = "warn"
            reason = "partial_restore_tooling"
        else:
            status = "pass"
            reason = "postgres_tooling_ready"
        return {
            "key": "postgres_operator_tooling",
            "status": status,
            "reason": reason,
            "binary_resolution": resolution,
        }

    def _schema_gate_check(self, schema_lifecycle: Dict[str, Any]) -> Dict[str, Any]:
        status = schema_lifecycle.get("status")
        if status == "up_to_date":
            return {"key": "schema_lifecycle", "status": "pass", "reason": "up_to_date"}
        if status == "pending_migrations":
            return {"key": "schema_lifecycle", "status": "warn", "reason": "pending_migrations"}
        return {"key": "schema_lifecycle", "status": "block", "reason": status or "unknown"}

    def _incident_gate_check(self, incident_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        incident_types = dict(incident_snapshot.get("by_incident_type", {}))
        if incident_types.get("provider_error"):
            return {"key": "runtime_incidents", "status": "block", "reason": "provider_error_present"}
        if incident_types.get("budget_blocked") or incident_types.get("fallback_used"):
            return {"key": "runtime_incidents", "status": "warn", "reason": "runtime_incidents_present"}
        return {"key": "runtime_incidents", "status": "pass", "reason": "runtime_incidents_clear"}

    def _overall_gate_status(self, checks: List[Dict[str, Any]]) -> str:
        statuses = [item.get("status") for item in checks]
        if "block" in statuses:
            return "block"
        if "warn" in statuses:
            return "warn"
        return "pass"

    def build_deployment_health_gate(self, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        recent_backups = self.list_backups(limit=5)
        incident_snapshot = self.observability.runtime_incident_snapshot(account_id=account_id, limit=20)
        checks = [
            self._database_connectivity_check(),
            self._schema_gate_check(schema_lifecycle),
            self._backup_freshness_check(recent_backups),
            self._restore_readiness_check(recent_backups),
            self._postgres_tooling_check(),
            self._incident_gate_check(incident_snapshot),
        ]
        overall_status = self._overall_gate_status(checks)
        if overall_status == "pass":
            recommended_action = "deploy_clear"
        elif overall_status == "warn":
            recommended_action = "deploy_with_operator_review"
        else:
            recommended_action = "block_and_investigate"
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "status": overall_status,
            "recommended_action": recommended_action,
            "checks": checks,
            "schema_lifecycle": schema_lifecycle,
            "recent_backups": recent_backups,
            "incident_snapshot": {
                "incident_count": incident_snapshot.get("incident_count"),
                "by_incident_type": incident_snapshot.get("by_incident_type", {}),
                "by_provider": incident_snapshot.get("by_provider", {}),
                "cache_hit_rate": incident_snapshot.get("cache_hit_rate"),
                "latency_summary": incident_snapshot.get("latency_summary", {}),
            },
            "restore_decision_hints": self._restore_decision_hints_from_latest_backup(recent_backups),
        }

    def build_preflight_verification_bundle(self, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        health_gate = self.build_deployment_health_gate(account_id=account_id)
        runbook = self.build_deployment_runbook()
        incident_playbook = self.build_incident_playbook(account_id=account_id)
        verification_commands = [
            "GET /health",
            "GET /v1/ops/schema-lifecycle",
            "GET /v1/ops/data-integrity",
            "GET /v1/ops/runtime-incident-snapshot",
            "POST /v1/ops/recovery-drill",
            "bash scripts/run_cross_pack_merge_gate.sh",
        ]
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "health_gate": health_gate,
            "deployment_runbook": runbook,
            "incident_playbook": incident_playbook,
            "verification_commands": verification_commands,
            "verification_summary": {
                "gate_status": health_gate.get("status"),
                "recommended_action": health_gate.get("recommended_action"),
                "command_count": len(verification_commands),
                "schema_status": health_gate.get("schema_lifecycle", {}).get("status"),
                "incident_count": health_gate.get("incident_snapshot", {}).get("incident_count"),
            },
            "restore_verification_steps": self._restore_verification_steps(),
            "recent_restore_requests": runbook.get("recent_restore_requests", []),
            "recent_restore_jobs": runbook.get("recent_restore_jobs", []),
        }

    def build_incident_playbook(self, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        snapshot = self.observability.runtime_incident_snapshot(account_id=account_id, limit=20)
        runbook = self.build_deployment_runbook()
        integrity = DataIntegrityService(self.repository).build_summary(limit=10)
        triage_steps: List[str] = []
        recovery_steps: List[str] = []
        if snapshot.get("schema_lifecycle_status") not in {"up_to_date", None}:
            triage_steps.append("Inspect schema lifecycle before touching runtime traffic.")
        if snapshot.get("by_incident_type", {}).get("provider_error"):
            triage_steps.append("Inspect provider routing receipts and selected_provider failure patterns.")
            recovery_steps.append("Force fallback provider order or disable affected provider.")
        if snapshot.get("by_incident_type", {}).get("budget_blocked"):
            triage_steps.append("Inspect prompt budget guardrails and request-size estimates.")
            recovery_steps.append("Raise budget threshold or shorten prompt payloads.")
        if snapshot.get("by_incident_type", {}).get("fallback_used"):
            triage_steps.append("Check whether fallback rate is rising compared with recent receipts.")
        if not runbook.get("recent_backups"):
            recovery_steps.append("Create a runtime backup before any restore or rollback action.")
        else:
            recovery_steps.append("Compare current runtime verification snapshot with the selected backup manifest before restore.")
        if not recovery_steps:
            recovery_steps.append("No immediate recovery action required; continue monitoring receipts.")
        decision_matrix = [
            {
                "scenario": "provider_error_or_fallback_spike",
                "preferred_action": "rollback_provider",
                "when": bool(snapshot.get("by_incident_type", {}).get("provider_error") or snapshot.get("by_incident_type", {}).get("fallback_used")),
                "inspect": [
                    "GET /v1/ops/provider-runtime-metrics",
                    "GET /v1/ops/runtime-incident-snapshot",
                    "recent runtime receipts",
                ],
            },
            {
                "scenario": "schema_or_restore_ready_drift",
                "preferred_action": "restore_runtime",
                "when": bool(runbook.get("schema_lifecycle", {}).get("status") not in {"up_to_date", "pending_migrations"} or runbook.get("restore_decision_hints")),
                "inspect": [
                    "GET /v1/ops/schema-lifecycle",
                    "GET /v1/ops/runtime-restore-requests",
                    "GET /v1/ops/recovery-drills",
                ],
            },
            {
                "scenario": "repairable_data_drift",
                "preferred_action": "run_data_integrity_repair",
                "when": integrity.get("status") == "repairable_attention",
                "inspect": [
                    "GET /v1/ops/data-integrity",
                    "repairable checks",
                    "manual backlog",
                ],
            },
        ]
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "incident_snapshot": snapshot,
            "data_integrity": {
                "status": integrity.get("status"),
                "warnings": integrity.get("warnings", []),
                "repair_actions": integrity.get("repair_actions", []),
            },
            "deployment_runbook": {
                "backend": runbook.get("backend"),
                "schema_lifecycle": runbook.get("schema_lifecycle", {}),
                "recent_backups": runbook.get("recent_backups", []),
                "restore_decision_hints": runbook.get("restore_decision_hints", []),
                "recent_recovery_drills": runbook.get("recent_recovery_drills", []),
                "recent_restore_requests": runbook.get("recent_restore_requests", []),
                "recent_restore_jobs": runbook.get("recent_restore_jobs", []),
            },
            "triage_steps": triage_steps or ["Review latest runtime receipts for this account or surface."],
            "recovery_steps": recovery_steps,
            "restore_verification_steps": self._restore_verification_steps(),
            "decision_matrix": decision_matrix,
        }
