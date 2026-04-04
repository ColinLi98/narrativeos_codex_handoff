from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..persistence.migrations import inspect_schema_lifecycle
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .observability import ObservabilityService


class RuntimeOpsService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        observability_service: Optional[ObservabilityService] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.observability = observability_service or ObservabilityService(repository)
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

    def create_backup(
        self,
        *,
        label: Optional[str] = None,
        output_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        backup_dir = self._backup_dir(output_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backend = self._backend()
        backup_id = "backup_%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        created_at = self._utcnow()
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        manifest: Dict[str, Any] = {
            "backup_id": backup_id,
            "label": label or "",
            "created_at": created_at,
            "backend": backend,
            "database_url": self._database_url(),
            "schema_lifecycle_status": schema_lifecycle.get("status"),
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
            planned_path = backup_dir / f"{backup_id}.sql.gz"
            manifest["backup_path"] = str(planned_path)
            manifest["status"] = "planned"
            manifest["restore_instructions"] = [
                f"pg_dump --format=custom --file {planned_path} {self._database_url()}",
                f"pg_restore --clean --if-exists --dbname {self._database_url()} {planned_path}",
            ]
            manifest["plan_only"] = True

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
        path = Path(backup_path)
        manifest: Dict[str, Any]
        if path.suffix == ".json":
            manifest = self._read_manifest(path)
            data_path = Path(manifest["backup_path"])
        else:
            data_path = path
            manifest_path = path.with_suffix(".json")
            manifest = self._read_manifest(manifest_path) if manifest_path.exists() else {
                "backup_path": str(path),
                "backend": self._backend(),
                "created_at": self._utcnow(),
            }
        backend = manifest.get("backend") or self._backend()
        result = {
            "backup_path": str(data_path),
            "backend": backend,
            "dry_run": dry_run,
            "status": "planned" if dry_run else "completed",
            "restored_at": self._utcnow(),
            "pre_restore_backup": None,
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
            result["target_database"] = str(target)
        else:
            result["status"] = "planned"
            result["restore_instructions"] = manifest.get("restore_instructions", [])
            result["plan_only"] = True
        return result

    def build_deployment_runbook(self) -> Dict[str, Any]:
        schema_lifecycle = inspect_schema_lifecycle(self.repository.engine)
        recent_backups = self.list_backups(limit=5)
        backend = self._backend()
        return {
            "generated_at": self._utcnow(),
            "backend": backend,
            "database_url": self._database_url(),
            "schema_lifecycle": schema_lifecycle,
            "recent_backups": recent_backups,
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
            ],
            "deploy_steps": [
                "1. Inspect schema lifecycle and pending migrations.",
                "2. Create a runtime backup before applying any migration or deploy.",
                "3. Apply pending migrations or dry-run them first.",
                "4. Restart API and verify /health plus Ops schema lifecycle endpoint.",
                "5. Run benchmark / merge gate after deploy.",
            ],
            "rollback_steps": [
                "1. If incident scope is infra, inspect runtime incident snapshot first.",
                "2. Restore latest known-good backup for sqlite, or follow postgres restore instructions.",
                "3. Re-run /health, schema lifecycle, and benchmark smoke checks.",
            ],
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
        if age_hours <= 24:
            return {
                "key": "recent_backup",
                "status": "pass",
                "reason": "backup_recent",
                "age_hours": round(age_hours, 2),
            }
        return {
            "key": "recent_backup",
            "status": "warn",
            "reason": "backup_stale",
            "age_hours": round(age_hours, 2),
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
            },
        }

    def build_preflight_verification_bundle(self, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        health_gate = self.build_deployment_health_gate(account_id=account_id)
        runbook = self.build_deployment_runbook()
        incident_playbook = self.build_incident_playbook(account_id=account_id)
        verification_commands = [
            "GET /health",
            "GET /v1/ops/schema-lifecycle",
            "GET /v1/ops/runtime-incident-snapshot",
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
        }

    def build_incident_playbook(self, *, account_id: Optional[str] = None) -> Dict[str, Any]:
        snapshot = self.observability.runtime_incident_snapshot(account_id=account_id, limit=20)
        runbook = self.build_deployment_runbook()
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
        if not recovery_steps:
            recovery_steps.append("No immediate recovery action required; continue monitoring receipts.")
        return {
            "generated_at": self._utcnow(),
            "account_id": account_id,
            "incident_snapshot": snapshot,
            "deployment_runbook": {
                "backend": runbook.get("backend"),
                "schema_lifecycle": runbook.get("schema_lifecycle", {}),
                "recent_backups": runbook.get("recent_backups", []),
            },
            "triage_steps": triage_steps or ["Review latest runtime receipts for this account or surface."],
            "recovery_steps": recovery_steps,
        }
