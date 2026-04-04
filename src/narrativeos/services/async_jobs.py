from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .analytics import AnalyticsService
from .async_job_adapters import (
    NotificationSinkRegistry,
    RemoteShippingConfigRegistry,
    RetryPolicyRegistry,
    build_notification_sink_registry,
    build_remote_shipping_registry,
    build_retry_policy_registry,
    classify_adapter_failure,
)


ASYNC_JOB_ASSET_TYPE = "async_job"
ASYNC_NOTIFICATION_RETRY_ASSET_TYPE = "async_notification_retry"
ASYNC_NOTIFICATION_DEAD_LETTER_ASSET_TYPE = "async_notification_dead_letter"
JOB_ARTIFACT_RETENTION_DAYS = {
    "learned_training": 30,
    "runtime_backup": 14,
    "runtime_restore": 14,
}
ARTIFACT_RETENTION_EXPIRING_SOON_DAYS = 3
DEFAULT_HANDOFF_SLA_MINUTES = 240

JOB_STEP_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "learned_training": [
        {"key": "queued", "label": "Queued"},
        {"key": "training", "label": "Train Tracks"},
        {"key": "evidence", "label": "Build Evidence"},
        {"key": "completed", "label": "Completed"},
    ],
    "runtime_backup": [
        {"key": "queued", "label": "Queued"},
        {"key": "snapshot", "label": "Snapshot Database"},
        {"key": "manifest", "label": "Write Manifest"},
        {"key": "completed", "label": "Completed"},
    ],
    "runtime_restore": [
        {"key": "queued", "label": "Queued"},
        {"key": "verify", "label": "Verify Approval"},
        {"key": "pre_backup", "label": "Pre-restore Backup"},
        {"key": "restore", "label": "Restore Database"},
        {"key": "completed", "label": "Completed"},
    ],
}


class AsyncJobService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        analytics_service: Optional[AnalyticsService] = None,
        base_dir: Optional[Path] = None,
        remote_shipping_registry: Optional[RemoteShippingConfigRegistry] = None,
        notification_sink_registry: Optional[NotificationSinkRegistry] = None,
        retry_policy_registry: Optional[RetryPolicyRegistry] = None,
    ) -> None:
        self.repository = repository
        self.analytics = analytics_service
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[3])
        self._runners: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.remote_shipping_registry = remote_shipping_registry or build_remote_shipping_registry(self.base_dir)
        self.notification_sink_registry = notification_sink_registry or build_notification_sink_registry(self.base_dir)
        self.retry_policy_registry = retry_policy_registry or build_retry_policy_registry()

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _default_lease_timeout_minutes(self, job: Optional[Dict[str, Any]] = None) -> int:
        if job and job.get("lease_timeout_minutes") is not None:
            try:
                return max(1, int(job.get("lease_timeout_minutes")))
            except (TypeError, ValueError):
                return 15
        return 15

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def register_runner(self, job_type: str, runner: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._runners[job_type] = runner

    def _workflow_steps(self, job_type: str, status: str) -> List[Dict[str, str]]:
        templates = JOB_STEP_TEMPLATES.get(job_type, [])
        if not templates:
            return []
        if status == "queued":
            active_index = 0
            failed_index = None
        elif status == "running":
            active_index = min(1, len(templates) - 1)
            failed_index = None
        elif status == "succeeded":
            active_index = len(templates)
            failed_index = None
        elif status == "failed":
            active_index = min(1, len(templates) - 1)
            failed_index = active_index
        else:
            active_index = 0
            failed_index = None
        steps: List[Dict[str, str]] = []
        for index, item in enumerate(templates):
            step_status = "pending"
            if status == "succeeded":
                step_status = "completed"
            elif status == "failed":
                if index < active_index:
                    step_status = "completed"
                elif index == failed_index:
                    step_status = "failed"
                else:
                    step_status = "skipped"
            elif status == "running":
                if index < active_index:
                    step_status = "completed"
                elif index == active_index:
                    step_status = "running"
            elif status == "queued":
                if index == 0:
                    step_status = "queued"
            steps.append(
                {
                    "key": item["key"],
                    "label": item["label"],
                    "status": step_status,
                }
            )
        return steps

    def _artifact_retention_days(self, job: Dict[str, Any]) -> int:
        if job.get("artifact_retention_days") is not None:
            try:
                return max(1, int(job.get("artifact_retention_days")))
            except (TypeError, ValueError):
                return JOB_ARTIFACT_RETENTION_DAYS.get(str(job.get("job_type") or ""), 7)
        return JOB_ARTIFACT_RETENTION_DAYS.get(str(job.get("job_type") or ""), 7)

    def _artifact_reference_time(self, job: Dict[str, Any]) -> datetime:
        return self._parse_timestamp(
            job.get("finished_at")
            or job.get("created_at")
            or job.get("updated_at")
        )

    def _artifact_retention_until(self, job: Dict[str, Any]) -> str:
        return (
            self._artifact_reference_time(job)
            + timedelta(days=self._artifact_retention_days(job))
        ).isoformat()

    def _artifact_paths(self, job: Dict[str, Any]) -> List[Dict[str, str]]:
        seen: set[str] = set()
        entries: List[Dict[str, str]] = []

        def add(label: str, raw_path: Any) -> None:
            if not isinstance(raw_path, str) or not raw_path.strip():
                return
            normalized = str(Path(raw_path))
            if normalized in seen:
                return
            seen.add(normalized)
            entries.append({"label": label, "path": normalized})

        result_summary = dict(job.get("result_summary") or {})
        add("summary_artifact", result_summary.get("summary_artifact"))
        for track, path in dict(result_summary.get("evidence_paths") or {}).items():
            add(f"evidence:{track}", path)
        add("backup_path", result_summary.get("backup_path"))
        for key, value in dict(job.get("artifacts") or {}).items():
            add(f"artifact:{key}", value)
        return entries

    def _artifact_inventory(self, job: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = self._artifact_paths(job)
        now = datetime.now(timezone.utc)
        retention_until = self._artifact_retention_until(job)
        retention_until_dt = self._parse_timestamp(retention_until)
        items: List[Dict[str, Any]] = []
        available_count = 0
        missing_count = 0
        total_bytes = 0
        for item in artifacts:
            path = Path(item["path"])
            exists = path.exists()
            size_bytes = 0
            modified_at = None
            path_type = "missing"
            if exists:
                available_count += 1
                if path.is_file():
                    size_bytes = path.stat().st_size
                    path_type = "file"
                elif path.is_dir():
                    size_bytes = sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
                    path_type = "dir"
                total_bytes += size_bytes
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            else:
                missing_count += 1
            items.append(
                {
                    **item,
                    "exists": exists,
                    "path_type": path_type,
                    "size_bytes": size_bytes,
                    "modified_at": modified_at,
                }
            )
        artifact_status = "no_artifacts"
        if artifacts:
            if available_count == 0:
                artifact_status = "missing"
            elif retention_until_dt <= now:
                artifact_status = "expired"
            elif retention_until_dt <= now + timedelta(days=ARTIFACT_RETENTION_EXPIRING_SOON_DAYS):
                artifact_status = "expiring_soon"
            else:
                artifact_status = "retained"
        return {
            "artifact_count": len(artifacts),
            "available_count": available_count,
            "missing_count": missing_count,
            "total_bytes": total_bytes,
            "artifact_status": artifact_status,
            "artifact_retention_days": self._artifact_retention_days(job),
            "artifact_retention_until": retention_until,
            "items": items,
        }

    def _lease_status(self, job: Dict[str, Any]) -> str:
        if job.get("status") != "running":
            return "released"
        expires_at = job.get("lease_expires_at")
        if not expires_at:
            return "missing"
        if self._parse_timestamp(expires_at) <= datetime.now(timezone.utc):
            return "expired"
        return "active"

    def _job_record(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "review_id": job["job_id"],
            "asset_type": ASYNC_JOB_ASSET_TYPE,
            "asset_id": job["job_id"],
            "status": job["status"],
            "reviewer_id": job.get("requested_by"),
            "risk_rating": job.get("job_type"),
            "notes": json.dumps(job, ensure_ascii=False, indent=2, default=str),
        }

    def _notification_retry_record(self, retry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "review_id": retry["retry_id"],
            "asset_type": ASYNC_NOTIFICATION_RETRY_ASSET_TYPE,
            "asset_id": retry["retry_id"],
            "status": retry["status"],
            "reviewer_id": retry.get("requested_by"),
            "risk_rating": str(retry.get("source_event_id") or ""),
            "notes": json.dumps(retry, ensure_ascii=False, indent=2, default=str),
        }

    def _notification_dead_letter_record(self, dead_letter: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "review_id": dead_letter["dead_letter_id"],
            "asset_type": ASYNC_NOTIFICATION_DEAD_LETTER_ASSET_TYPE,
            "asset_id": dead_letter["dead_letter_id"],
            "status": dead_letter["status"],
            "reviewer_id": dead_letter.get("requested_by"),
            "risk_rating": str(dead_letter.get("source_event_id") or ""),
            "notes": json.dumps(dead_letter, ensure_ascii=False, indent=2, default=str),
        }

    def _normalize_job(self, record: Dict[str, Any]) -> Dict[str, Any]:
        raw_notes = record.get("notes")
        payload: Dict[str, Any] = {}
        if isinstance(raw_notes, str) and raw_notes.strip():
            try:
                parsed = json.loads(raw_notes)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}
        job = {
            **payload,
            "job_id": payload.get("job_id") or record.get("asset_id"),
            "job_type": payload.get("job_type") or record.get("risk_rating"),
            "status": record.get("status"),
            "requested_by": payload.get("requested_by") or record.get("reviewer_id"),
            "updated_at": record.get("updated_at"),
        }
        job["workflow"] = {
            "mode": "fastapi_background_tasks",
            "steps": self._workflow_steps(str(job.get("job_type") or ""), str(job.get("status") or "")),
        }
        job["lease_status"] = self._lease_status(job)
        job["artifact_retention_days"] = self._artifact_retention_days(job)
        job["artifact_retention_until"] = self._artifact_retention_until(job)
        return job

    def _normalize_notification_retry(self, record: Dict[str, Any]) -> Dict[str, Any]:
        raw_notes = record.get("notes")
        payload: Dict[str, Any] = {}
        if isinstance(raw_notes, str) and raw_notes.strip():
            try:
                parsed = json.loads(raw_notes)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}
        return {
            **payload,
            "retry_id": payload.get("retry_id") or record.get("asset_id"),
            "status": record.get("status"),
            "requested_by": payload.get("requested_by") or record.get("reviewer_id"),
            "updated_at": record.get("updated_at"),
        }

    def _normalize_notification_dead_letter(self, record: Dict[str, Any]) -> Dict[str, Any]:
        raw_notes = record.get("notes")
        payload: Dict[str, Any] = {}
        if isinstance(raw_notes, str) and raw_notes.strip():
            try:
                parsed = json.loads(raw_notes)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}
        return {
            **payload,
            "dead_letter_id": payload.get("dead_letter_id") or record.get("asset_id"),
            "status": record.get("status"),
            "requested_by": payload.get("requested_by") or record.get("reviewer_id"),
            "updated_at": record.get("updated_at"),
        }

    def _append_recovery_action(
        self,
        job: Dict[str, Any],
        *,
        action: str,
        requested_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        history = list(job.get("recovery_history") or [])
        history.insert(
            0,
            {
                "action": action,
                "requested_by": requested_by or job.get("requested_by"),
                "reason": reason or action,
                "occurred_at": self._utcnow(),
            },
        )
        return {
            **job,
            "recovery_history": history[:10],
            "recovery_count": int(job.get("recovery_count") or 0) + 1,
            "last_recovery_action": action,
        }

    def _append_cleanup_action(
        self,
        job: Dict[str, Any],
        *,
        action: str,
        requested_by: Optional[str] = None,
        removed_items: Optional[List[Dict[str, Any]]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        history = list(job.get("cleanup_history") or [])
        history.insert(
            0,
            {
                "action": action,
                "requested_by": requested_by or job.get("requested_by"),
                "occurred_at": self._utcnow(),
                "dry_run": dry_run,
                "removed_items": removed_items or [],
            },
        )
        return {
            **job,
            "cleanup_history": history[:10],
            "cleanup_count": int(job.get("cleanup_count") or 0) + 1,
            "last_cleanup_action": action,
            "cleaned_at": None if dry_run else self._utcnow(),
        }

    def _append_shipping_action(
        self,
        job: Dict[str, Any],
        *,
        action: str,
        requested_by: Optional[str] = None,
        shipped_items: Optional[List[Dict[str, Any]]] = None,
        dry_run: bool = False,
        remote_dir: Optional[str] = None,
        remote_manifest_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        history = list(job.get("remote_shipping_history") or [])
        history.insert(
            0,
            {
                "action": action,
                "requested_by": requested_by or job.get("requested_by"),
                "occurred_at": self._utcnow(),
                "dry_run": dry_run,
                "remote_dir": remote_dir,
                "remote_manifest_path": remote_manifest_path,
                "shipped_items": shipped_items or [],
            },
        )
        return {
            **job,
            "remote_shipping_history": history[:10],
            "remote_shipping_count": int(job.get("remote_shipping_count") or 0) + 1,
            "last_remote_shipping_action": action,
            "remote_shipping_status": "planned" if dry_run else "shipped",
            "remote_shipping_dir": remote_dir,
            "remote_manifest_path": remote_manifest_path,
            "remote_shipped_at": None if dry_run else self._utcnow(),
        }

    def _append_sla_escalation_action(
        self,
        job: Dict[str, Any],
        *,
        action: str,
        requested_by: Optional[str] = None,
        note: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        history = list(job.get("handoff_sla_history") or [])
        history.insert(
            0,
            {
                "action": action,
                "requested_by": requested_by or job.get("requested_by"),
                "occurred_at": self._utcnow(),
                "dry_run": dry_run,
                "note": note or "",
            },
        )
        return {
            **job,
            "handoff_sla_history": history[:10],
            "handoff_sla_escalation_count": int(job.get("handoff_sla_escalation_count") or 0) + 1,
            "last_handoff_sla_action": action,
            "handoff_sla_escalated_at": None if dry_run else self._utcnow(),
        }

    def _save_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        saved = self.repository.save_review_record(self._job_record(job))
        normalized = self._normalize_job(saved)
        normalized.setdefault("created_at", job.get("created_at"))
        normalized.setdefault("started_at", job.get("started_at"))
        normalized.setdefault("finished_at", job.get("finished_at"))
        normalized.setdefault("payload", job.get("payload", {}))
        normalized.setdefault("result_summary", job.get("result_summary"))
        normalized.setdefault("error", job.get("error"))
        normalized.setdefault("duration_seconds", job.get("duration_seconds"))
        normalized.setdefault("attempt_count", job.get("attempt_count", 0))
        normalized.setdefault("artifacts", job.get("artifacts", {}))
        normalized.setdefault("recovery_history", job.get("recovery_history", []))
        normalized.setdefault("recovery_count", job.get("recovery_count", 0))
        normalized.setdefault("last_recovery_action", job.get("last_recovery_action"))
        normalized.setdefault("last_error", job.get("last_error"))
        normalized.setdefault("lease_owner", job.get("lease_owner"))
        normalized.setdefault("lease_acquired_at", job.get("lease_acquired_at"))
        normalized.setdefault("lease_expires_at", job.get("lease_expires_at"))
        normalized.setdefault("lease_timeout_minutes", job.get("lease_timeout_minutes"))
        normalized.setdefault("heartbeat_at", job.get("heartbeat_at"))
        normalized.setdefault("heartbeat_count", job.get("heartbeat_count", 0))
        normalized.setdefault("artifact_retention_days", job.get("artifact_retention_days"))
        normalized.setdefault("artifact_retention_until", job.get("artifact_retention_until"))
        normalized.setdefault("cleanup_history", job.get("cleanup_history", []))
        normalized.setdefault("cleanup_count", job.get("cleanup_count", 0))
        normalized.setdefault("last_cleanup_action", job.get("last_cleanup_action"))
        normalized.setdefault("cleaned_at", job.get("cleaned_at"))
        normalized.setdefault("acknowledged_by", job.get("acknowledged_by"))
        normalized.setdefault("acknowledged_at", job.get("acknowledged_at"))
        normalized.setdefault("acknowledgement_note", job.get("acknowledgement_note"))
        normalized.setdefault("acknowledgement_history", job.get("acknowledgement_history", []))
        normalized.setdefault("acknowledgement_count", job.get("acknowledgement_count", 0))
        normalized.setdefault("remote_shipping_history", job.get("remote_shipping_history", []))
        normalized.setdefault("remote_shipping_count", job.get("remote_shipping_count", 0))
        normalized.setdefault("last_remote_shipping_action", job.get("last_remote_shipping_action"))
        normalized.setdefault("remote_shipping_status", job.get("remote_shipping_status"))
        normalized.setdefault("remote_shipping_dir", job.get("remote_shipping_dir"))
        normalized.setdefault("remote_manifest_path", job.get("remote_manifest_path"))
        normalized.setdefault("remote_shipped_at", job.get("remote_shipped_at"))
        normalized.setdefault("handoff_sla_minutes", job.get("handoff_sla_minutes"))
        normalized.setdefault("handoff_sla_due_at", job.get("handoff_sla_due_at"))
        normalized.setdefault("handoff_sla_status", job.get("handoff_sla_status"))
        normalized.setdefault("handoff_sla_history", job.get("handoff_sla_history", []))
        normalized.setdefault("handoff_sla_escalation_count", job.get("handoff_sla_escalation_count", 0))
        normalized.setdefault("last_handoff_sla_action", job.get("last_handoff_sla_action"))
        normalized.setdefault("handoff_sla_escalated_at", job.get("handoff_sla_escalated_at"))
        normalized["updated_at"] = saved.get("updated_at")
        normalized["lease_status"] = self._lease_status(normalized)
        normalized["artifact_retention_days"] = self._artifact_retention_days(normalized)
        normalized["artifact_retention_until"] = self._artifact_retention_until(normalized)
        normalized["handoff_sla_minutes"] = self._handoff_sla_minutes(normalized)
        normalized["handoff_sla_due_at"] = self._handoff_sla_due_at(normalized)
        return normalized

    def _track(self, event_name: str, *, job: Dict[str, Any]) -> None:
        if self.analytics is None:
            return
        self.analytics.track(
            event_name,
            reader_id=job.get("account_id"),
            account_id=job.get("account_id"),
            payload_json={
                "job_id": job.get("job_id"),
                "job_type": job.get("job_type"),
                "status": job.get("status"),
                "requested_by": job.get("requested_by"),
                "result_summary": job.get("result_summary"),
                "error": job.get("error"),
            },
        )

    def _track_batch_event(self, event_name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.analytics is None:
            return
        return self.analytics.track(
            event_name,
            payload_json=payload,
        )

    def _acknowledgement_status(self, job: Dict[str, Any], *, required: bool) -> str:
        if not required:
            return "not_required"
        if job.get("acknowledged_at"):
            return "acknowledged"
        return "pending"

    def _handoff_bundle_dir(self, output_dir: Optional[str] = None) -> Path:
        if output_dir:
            return Path(output_dir)
        return self.base_dir / "artifacts" / "async_job_handoffs"

    def _remote_shipping_dir(self, output_dir: Optional[str] = None) -> Path:
        if output_dir:
            return Path(output_dir)
        return self.base_dir / "artifacts" / "async_job_remote_shipments"

    def _handoff_sla_minutes(self, job: Dict[str, Any], *, override_minutes: Optional[int] = None) -> int:
        if override_minutes is not None:
            try:
                return max(1, int(override_minutes))
            except (TypeError, ValueError):
                return DEFAULT_HANDOFF_SLA_MINUTES
        if job.get("handoff_sla_minutes") is not None:
            try:
                return max(1, int(job.get("handoff_sla_minutes")))
            except (TypeError, ValueError):
                return DEFAULT_HANDOFF_SLA_MINUTES
        return DEFAULT_HANDOFF_SLA_MINUTES

    def _handoff_reference_time(self, job: Dict[str, Any]) -> datetime:
        return self._parse_timestamp(
            job.get("finished_at")
            or job.get("created_at")
            or job.get("updated_at")
        )

    def _handoff_sla_due_at(self, job: Dict[str, Any], *, override_minutes: Optional[int] = None) -> str:
        return (
            self._handoff_reference_time(job)
            + timedelta(minutes=self._handoff_sla_minutes(job, override_minutes=override_minutes))
        ).isoformat()

    def _handoff_sla_status(self, job: Dict[str, Any], *, required: bool, override_minutes: Optional[int] = None) -> str:
        if not required:
            return "not_required"
        if job.get("acknowledged_at"):
            return "acknowledged"
        due_at = self._parse_timestamp(self._handoff_sla_due_at(job, override_minutes=override_minutes))
        if due_at <= datetime.now(timezone.utc):
            return "overdue"
        return "within_sla"

    def _handoff_job_entries(self, *, limit: int = 20, sla_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
        jobs = self.list_jobs(limit=max(limit * 4, 50))
        retention_snapshot = self.artifact_retention_snapshot(limit=max(limit * 4, 50))
        retention_lookup = {
            str(item.get("job_id")): item for item in retention_snapshot.get("artifact_jobs", [])
        }
        entries: List[Dict[str, Any]] = []
        for job in jobs:
            flags: List[str] = []
            if job.get("status") == "failed":
                flags.append("failed_job")
            elif job.get("status") == "running":
                flags.append("running_job")
            elif job.get("status") == "queued":
                flags.append("queued_job")
            retention = retention_lookup.get(str(job.get("job_id")), {})
            artifact_status = retention.get("artifact_status")
            if artifact_status == "missing":
                flags.append("artifact_missing")
            elif artifact_status == "expired":
                flags.append("artifact_expired")
            elif artifact_status == "expiring_soon":
                flags.append("artifact_expiring_soon")
            remote_shipping_status = str(job.get("remote_shipping_status") or "not_shipped")
            if artifact_status in {"retained", "expiring_soon"} and remote_shipping_status not in {"shipped", "planned"}:
                flags.append("remote_shipping_missing")
            handoff_required = bool(flags)
            handoff_sla_due_at = self._handoff_sla_due_at(job, override_minutes=sla_minutes)
            handoff_sla_status = self._handoff_sla_status(job, required=handoff_required, override_minutes=sla_minutes)
            entries.append(
                {
                    "job_id": job.get("job_id"),
                    "job_type": job.get("job_type"),
                    "status": job.get("status"),
                    "requested_by": job.get("requested_by"),
                    "lease_status": job.get("lease_status"),
                    "artifact_status": artifact_status or "no_artifacts",
                    "remote_shipping_status": remote_shipping_status,
                    "handoff_flags": flags,
                    "handoff_required": handoff_required,
                    "acknowledgement_status": self._acknowledgement_status(job, required=handoff_required),
                    "handoff_sla_minutes": self._handoff_sla_minutes(job, override_minutes=sla_minutes),
                    "handoff_sla_due_at": handoff_sla_due_at,
                    "handoff_sla_status": handoff_sla_status,
                    "handoff_sla_escalated_at": job.get("handoff_sla_escalated_at"),
                    "acknowledged_by": job.get("acknowledged_by"),
                    "acknowledged_at": job.get("acknowledged_at"),
                    "acknowledgement_note": job.get("acknowledgement_note"),
                    "result_summary": job.get("result_summary"),
                }
            )
        return entries[:limit]

    def _compact_result(self, job_type: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if job_type == "learned_training":
            summary = dict(result.get("summary") or {})
            evidence_paths = {
                track: payload.get("evidence_path")
                for track, payload in dict(result.get("evidence_results") or {}).items()
                if isinstance(payload, dict) and payload.get("evidence_path")
            }
            return {
                "run_id": summary.get("run_id"),
                "tracks_requested": list(summary.get("tracks_requested") or []),
                "tracks_succeeded": list(summary.get("tracks_succeeded") or []),
                "tracks_failed": list(summary.get("tracks_failed") or []),
                "output_dir": summary.get("output_dir"),
                "summary_artifact": dict(result.get("artifacts") or {}).get("summary"),
                "evidence_paths": evidence_paths,
            }
        if job_type == "runtime_backup":
            return {
                "backup_id": result.get("backup_id"),
                "label": result.get("label"),
                "status": result.get("status"),
                "backend": result.get("backend"),
                "backup_path": result.get("backup_path"),
                "created_at": result.get("created_at"),
                "schema_lifecycle_status": result.get("schema_lifecycle_status"),
                "dry_run": result.get("dry_run"),
            }
        if job_type == "runtime_restore":
            return {
                "request_id": result.get("request_id"),
                "status": result.get("status"),
                "backup_path": result.get("backup_path"),
                "restore_decision": result.get("restore_decision"),
                "verification_status": result.get("verification_status"),
                "artifact_dir": dict(result.get("artifacts") or {}).get("artifact_dir"),
                "result_json": dict(result.get("artifacts") or {}).get("result_json"),
                "stdout_log": dict(result.get("artifacts") or {}).get("stdout_log"),
                "stderr_log": dict(result.get("artifacts") or {}).get("stderr_log"),
            }
        return result

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(
            asset_type=ASYNC_JOB_ASSET_TYPE,
            status=status,
        )
        jobs = [self._normalize_job(item) for item in records]
        if job_type is not None:
            jobs = [item for item in jobs if item.get("job_type") == job_type]
        jobs.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return jobs[:limit]

    def get_job(self, job_id: str) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type=ASYNC_JOB_ASSET_TYPE, asset_id=job_id)
        if not records:
            raise KeyError(f"unknown_async_job:{job_id}")
        return self._normalize_job(records[0])

    def queue_summary(self, *, limit: int = 20) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=limit)
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_lease_status: Dict[str, int] = {}
        for job in jobs:
            by_status[str(job.get("status") or "unknown")] = by_status.get(str(job.get("status") or "unknown"), 0) + 1
            by_type[str(job.get("job_type") or "unknown")] = by_type.get(str(job.get("job_type") or "unknown"), 0) + 1
            by_lease_status[str(job.get("lease_status") or "unknown")] = (
                by_lease_status.get(str(job.get("lease_status") or "unknown"), 0) + 1
            )
        latest_finished = next((item for item in jobs if item.get("status") in {"succeeded", "failed"}), None)
        return {
            "generated_at": self._utcnow(),
            "job_count": len(jobs),
            "by_status": by_status,
            "by_type": by_type,
            "by_lease_status": by_lease_status,
            "latest_finished_job": latest_finished,
            "supported_job_types": sorted(self._runners.keys()),
        }

    def artifact_retention_snapshot(self, *, limit: int = 20) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=max(limit * 4, 50))
        artifact_jobs: List[Dict[str, Any]] = []
        by_status: Dict[str, int] = {}
        total_bytes = 0
        total_artifact_count = 0
        for job in jobs:
            inventory = self._artifact_inventory(job)
            total_bytes += int(inventory.get("total_bytes") or 0)
            total_artifact_count += int(inventory.get("artifact_count") or 0)
            by_status[str(inventory.get("artifact_status") or "unknown")] = (
                by_status.get(str(inventory.get("artifact_status") or "unknown"), 0) + 1
            )
            if inventory.get("artifact_count"):
                artifact_jobs.append(
                    {
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "requested_by": job.get("requested_by"),
                        "status": job.get("status"),
                        "artifact_status": inventory.get("artifact_status"),
                        "artifact_retention_days": inventory.get("artifact_retention_days"),
                        "artifact_retention_until": inventory.get("artifact_retention_until"),
                        "artifact_count": inventory.get("artifact_count"),
                        "available_count": inventory.get("available_count"),
                        "missing_count": inventory.get("missing_count"),
                        "total_bytes": inventory.get("total_bytes"),
                        "last_cleanup_action": job.get("last_cleanup_action"),
                        "cleaned_at": job.get("cleaned_at"),
                        "items": inventory.get("items", []),
                    }
                )
        artifact_jobs.sort(key=lambda item: str(item.get("artifact_retention_until") or ""), reverse=False)
        return {
            "generated_at": self._utcnow(),
            "job_count": len(jobs),
            "jobs_with_artifacts": len([item for item in artifact_jobs if item.get("artifact_count")]),
            "total_artifact_count": total_artifact_count,
            "total_bytes": total_bytes,
            "by_status": by_status,
            "expiring_soon_count": by_status.get("expiring_soon", 0),
            "expired_count": by_status.get("expired", 0),
            "missing_count": by_status.get("missing", 0),
            "artifact_jobs": artifact_jobs[:limit],
        }

    def remote_shipping_snapshot(self, *, limit: int = 20) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=max(limit * 4, 50))
        by_status: Dict[str, int] = {}
        shipped_jobs: List[Dict[str, Any]] = []
        total_shipped_items = 0
        for job in jobs:
            status = str(job.get("remote_shipping_status") or "not_shipped")
            by_status[status] = by_status.get(status, 0) + 1
            shipped_items = list(job.get("remote_shipping_history") or [])
            if job.get("remote_shipping_dir") or shipped_items:
                latest = shipped_items[0] if shipped_items else {}
                item_count = len(latest.get("shipped_items") or [])
                total_shipped_items += item_count
                shipped_jobs.append(
                    {
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "remote_shipping_status": status,
                        "remote_shipping_dir": job.get("remote_shipping_dir"),
                        "remote_manifest_path": job.get("remote_manifest_path"),
                        "remote_shipped_at": job.get("remote_shipped_at"),
                        "shipped_item_count": item_count,
                    }
                )
        shipped_jobs.sort(key=lambda item: str(item.get("remote_shipped_at") or ""), reverse=True)
        return {
            "generated_at": self._utcnow(),
            "job_count": len(jobs),
            "jobs_with_remote_shipping": len(shipped_jobs),
            "total_shipped_items": total_shipped_items,
            "registry": self.remote_shipping_registry.summary(),
            "by_status": by_status,
            "shipped_jobs": shipped_jobs[:limit],
        }

    def _validate_path_target(self, path_value: Optional[str]) -> Dict[str, Any]:
        if not path_value:
            return {"valid": False, "issues": ["missing_path"], "exists": False, "writable": False}
        path = Path(path_value)
        issues: List[str] = []
        if not path.is_absolute():
            issues.append("path_not_absolute")
        exists = path.exists()
        writable = False
        if exists:
            writable = os.access(path, os.W_OK)
            if not writable:
                issues.append("path_not_writable")
        else:
            parent = path.parent
            writable = parent.exists() and os.access(parent, os.W_OK)
            if not writable:
                issues.append("parent_not_writable")
        return {
            "valid": not issues,
            "issues": issues,
            "exists": exists,
            "writable": writable,
        }

    def adapter_config_validation(self) -> Dict[str, Any]:
        remote_summary = self.remote_shipping_registry.summary()
        sink_summary = self.notification_sink_registry.summary()
        remote_checks: List[Dict[str, Any]] = []
        sink_checks: List[Dict[str, Any]] = []
        remote_valid = True
        sink_valid = True

        for name, description in dict(remote_summary.get("descriptions") or {}).items():
            base_dir = description.get("base_dir")
            path_check = self._validate_path_target(base_dir) if base_dir else {
                "valid": True,
                "issues": [],
                "exists": False,
                "writable": False,
            }
            valid = bool(path_check.get("valid", True))
            remote_valid = remote_valid and valid
            remote_checks.append(
                {
                    "adapter_name": name,
                    "kind": description.get("kind"),
                    "base_dir": base_dir,
                    **path_check,
                }
            )

        if remote_summary.get("default_adapter") not in set(remote_summary.get("available_adapters") or []):
            remote_valid = False
            remote_checks.insert(
                0,
                {
                    "adapter_name": remote_summary.get("default_adapter"),
                    "kind": "missing_default",
                    "base_dir": None,
                    "valid": False,
                    "issues": ["default_adapter_not_registered"],
                    "exists": False,
                    "writable": False,
                },
            )

        for name, description in dict(sink_summary.get("descriptions") or {}).items():
            base_dir = description.get("base_dir")
            path_check = self._validate_path_target(base_dir) if base_dir else {
                "valid": True,
                "issues": [],
                "exists": False,
                "writable": False,
            }
            valid = bool(path_check.get("valid", True))
            sink_valid = sink_valid and valid
            sink_checks.append(
                {
                    "sink_name": name,
                    "kind": description.get("kind"),
                    "base_dir": base_dir,
                    **path_check,
                }
            )

        if sink_summary.get("default_sink") not in set(sink_summary.get("available_sinks") or []):
            sink_valid = False
            sink_checks.insert(
                0,
                {
                    "sink_name": sink_summary.get("default_sink"),
                    "kind": "missing_default",
                    "base_dir": None,
                    "valid": False,
                    "issues": ["default_sink_not_registered"],
                    "exists": False,
                    "writable": False,
                },
            )

        return {
            "generated_at": self._utcnow(),
            "valid": remote_valid and sink_valid,
            "remote_shipping": {
                "valid": remote_valid,
                "config_source": {
                    "default_adapter_env": "NARRATIVEOS_ASYNC_REMOTE_PROVIDER",
                    "base_dir_env": "NARRATIVEOS_ASYNC_REMOTE_BASE_DIR",
                    "resolved_default_adapter": remote_summary.get("default_adapter"),
                },
                "registry": remote_summary,
                "checks": remote_checks,
            },
            "notification_sinks": {
                "valid": sink_valid,
                "config_source": {
                    "default_sink_env": "NARRATIVEOS_ASYNC_NOTIFICATION_SINK",
                    "base_dir_env": "NARRATIVEOS_ASYNC_NOTIFICATION_BASE_DIR",
                    "resolved_default_sink": sink_summary.get("default_sink"),
                },
                "registry": sink_summary,
                "checks": sink_checks,
            },
        }

    def adapter_health_probe(self) -> Dict[str, Any]:
        remote_probe = self.remote_shipping_registry.probe_all()
        sink_probe = self.notification_sink_registry.probe_all()
        remote_default = remote_probe.get("default_probe") or {}
        sink_default = sink_probe.get("default_probe") or {}
        status = "pass"
        if remote_default.get("status") == "fail" or sink_default.get("status") == "fail":
            status = "fail"
        elif remote_default.get("status") == "warn" or sink_default.get("status") == "warn":
            status = "warn"
        return {
            "generated_at": self._utcnow(),
            "status": status,
            "remote_shipping": remote_probe,
            "notification_sinks": sink_probe,
        }

    def retry_policy_summary(self) -> Dict[str, Any]:
        return {
            "generated_at": self._utcnow(),
            **self.retry_policy_registry.summary(),
        }

    def _notification_receipt_from_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(event.get("payload_json") or {})
        target_path = str(payload.get("target_path") or "")
        target = Path(target_path) if target_path else None
        exists = bool(target and target.exists())
        size_bytes = target.stat().st_size if target and target.exists() and target.is_file() else 0
        return {
            "event_id": event.get("event_id"),
            "occurred_at": event.get("occurred_at"),
            "event_name": event.get("event_name"),
            "sink_name": payload.get("sink_name"),
            "event_type": payload.get("event_type"),
            "status": payload.get("status"),
            "target_path": target_path,
            "target_exists": exists,
            "target_size_bytes": size_bytes,
            "requested_by": payload.get("requested_by"),
        }

    def notification_delivery_receipts(
        self,
        *,
        sink_name: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        events = self.repository.list_analytics_events(
            event_names=["async_job_notification_sent", "async_job_notification_planned"],
            limit=max(limit * 4, 100),
        )
        receipts: List[Dict[str, Any]] = []
        by_sink: Dict[str, int] = {}
        by_event_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for event in events:
            payload = dict(event.get("payload_json") or {})
            if sink_name is not None and payload.get("sink_name") != sink_name:
                continue
            if event_type is not None and payload.get("event_type") != event_type:
                continue
            receipt = self._notification_receipt_from_event(event)
            receipts.append(receipt)
            by_sink[str(receipt.get("sink_name") or "unknown")] = by_sink.get(str(receipt.get("sink_name") or "unknown"), 0) + 1
            by_event_type[str(receipt.get("event_type") or "unknown")] = by_event_type.get(str(receipt.get("event_type") or "unknown"), 0) + 1
            by_status[str(receipt.get("status") or "unknown")] = by_status.get(str(receipt.get("status") or "unknown"), 0) + 1
        receipts.sort(key=lambda item: str(item.get("occurred_at") or ""), reverse=True)
        return {
            "generated_at": self._utcnow(),
            "receipt_count": len(receipts),
            "by_sink": by_sink,
            "by_event_type": by_event_type,
            "by_status": by_status,
            "latest_receipts": receipts[:limit],
        }

    def list_notification_retry_queue(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(
            asset_type=ASYNC_NOTIFICATION_RETRY_ASSET_TYPE,
            status=status,
        )
        items = [self._normalize_notification_retry(item) for item in records]
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        by_status: Dict[str, int] = {}
        for item in items:
            key = str(item.get("status") or "unknown")
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "generated_at": self._utcnow(),
            "retry_count": len(items),
            "by_status": by_status,
            "retries": items[:limit],
        }

    def list_notification_dead_letter_queue(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(
            asset_type=ASYNC_NOTIFICATION_DEAD_LETTER_ASSET_TYPE,
            status=status,
        )
        items = [self._normalize_notification_dead_letter(item) for item in records]
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        by_status: Dict[str, int] = {}
        by_failure_class: Dict[str, int] = {}
        for item in items:
            status_key = str(item.get("status") or "unknown")
            by_status[status_key] = by_status.get(status_key, 0) + 1
            failure_key = str((item.get("failure_classification") or {}).get("failure_class") or "unknown")
            by_failure_class[failure_key] = by_failure_class.get(failure_key, 0) + 1
        return {
            "generated_at": self._utcnow(),
            "dead_letter_count": len(items),
            "by_status": by_status,
            "by_failure_class": by_failure_class,
            "dead_letters": items[:limit],
        }

    def _upsert_notification_dead_letter(
        self,
        *,
        retry: Dict[str, Any],
        classification: Dict[str, Any],
        requested_by: Optional[str] = None,
        attempt_count: int,
    ) -> Dict[str, Any]:
        existing_id = retry.get("dead_letter_id")
        existing: Dict[str, Any] | None = None
        if existing_id:
            records = self.repository.list_review_records(
                asset_type=ASYNC_NOTIFICATION_DEAD_LETTER_ASSET_TYPE,
                asset_id=existing_id,
            )
            if records:
                existing = self._normalize_notification_dead_letter(records[0])
        now = self._utcnow()
        dead_letter = {
            **dict(existing or {}),
            "dead_letter_id": existing_id or f"notify_dlq_{uuid4().hex[:12]}",
            "retry_id": retry["retry_id"],
            "source_event_id": retry.get("source_event_id"),
            "source_event_type": retry.get("source_event_type"),
            "source_sink_name": retry.get("source_sink_name"),
            "requested_by": requested_by or retry.get("requested_by") or "ops_web",
            "retry_policy_id": retry.get("retry_policy_id"),
            "failure_classification": classification,
            "last_error": classification.get("message"),
            "attempt_count": attempt_count,
            "created_at": (existing or {}).get("created_at") or now,
            "last_failed_at": now,
            "latest_retry_status": "failed",
            "status": "open",
        }
        saved = self.repository.save_review_record(self._notification_dead_letter_record(dead_letter))
        normalized = self._normalize_notification_dead_letter(saved)
        self._track_batch_event(
            "async_notification_dead_letter_recorded",
            {
                "requested_by": dead_letter["requested_by"],
                "dead_letter_id": normalized["dead_letter_id"],
                "retry_id": retry["retry_id"],
                "source_event_id": retry.get("source_event_id"),
                "failure_classification": classification,
            },
        )
        return normalized

    def enqueue_notification_retry(
        self,
        event_id: int,
        *,
        requested_by: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        detail = self.notification_delivery_receipt_detail(event_id)
        receipt = detail["receipt"]
        retry_policy = self.retry_policy_registry.resolve_notification_policy(receipt.get("sink_name"))
        retry = {
            "retry_id": f"notify_retry_{uuid4().hex[:12]}",
            "source_event_id": int(event_id),
            "source_event_type": receipt.get("event_type"),
            "source_sink_name": receipt.get("sink_name"),
            "source_target_path": receipt.get("target_path"),
            "requested_by": requested_by or "ops_web",
            "note": note or "",
            "status": "queued",
            "created_at": self._utcnow(),
            "process_count": 0,
            "last_error": None,
            "latest_notification_receipt": None,
            "retry_policy_id": retry_policy.get("policy_id"),
            "retry_policy": retry_policy,
            "failure_classification": None,
            "retry_decision": "queued",
            "next_retry_at": None,
        }
        saved = self.repository.save_review_record(self._notification_retry_record(retry))
        normalized = self._normalize_notification_retry(saved)
        self._track_batch_event(
            "async_notification_retry_enqueued",
            {
                "requested_by": requested_by or "ops_web",
                "retry_id": normalized["retry_id"],
                "source_event_id": int(event_id),
                "source_event_type": receipt.get("event_type"),
                "source_sink_name": receipt.get("sink_name"),
            },
        )
        return normalized

    def process_notification_retry(
        self,
        retry_id: str,
        *,
        requested_by: Optional[str] = None,
        sink_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        records = self.repository.list_review_records(asset_type=ASYNC_NOTIFICATION_RETRY_ASSET_TYPE, asset_id=retry_id)
        if not records:
            raise KeyError(f"unknown_notification_retry:{retry_id}")
        retry = self._normalize_notification_retry(records[0])
        source_detail = self.notification_delivery_receipt_detail(int(retry["source_event_id"]))
        payload = ((source_detail.get("target_payload") or {}).get("payload")) or {
            "retry_of_event_id": retry["source_event_id"],
            "source_event_type": retry.get("source_event_type"),
        }
        resolved_sink = sink_name or retry.get("source_sink_name")
        retry_policy = self.retry_policy_registry.resolve_notification_policy(resolved_sink)
        next_attempt = int(retry.get("process_count") or 0) + 1
        try:
            receipt = self._send_notification(
                event_type=str(retry.get("source_event_type") or "async_notification_retry"),
                payload=payload,
                requested_by=requested_by,
                dry_run=dry_run,
                sink_name=resolved_sink,
            )
            updated_retry = {
                **retry,
                "status": "planned" if dry_run else "succeeded",
                "processed_at": self._utcnow(),
                "process_count": next_attempt,
                "requested_by": requested_by or retry.get("requested_by"),
                "latest_notification_receipt": receipt,
                "last_error": None,
                "failure_classification": None,
                "retry_policy_id": retry_policy.get("policy_id"),
                "retry_policy": retry_policy,
                "retry_decision": "planned" if dry_run else "succeeded",
                "next_retry_at": None,
            }
            saved = self.repository.save_review_record(self._notification_retry_record(updated_retry))
            normalized = self._normalize_notification_retry(saved)
            normalized["latest_notification_receipt"] = receipt
            self._track_batch_event(
                "async_notification_retry_processed" if not dry_run else "async_notification_retry_planned",
                {
                    "requested_by": requested_by or retry.get("requested_by") or "ops_web",
                    "retry_id": normalized["retry_id"],
                    "source_event_id": retry["source_event_id"],
                    "sink_name": receipt.get("sink_name"),
                    "status": normalized["status"],
                    "retry_policy_id": retry_policy.get("policy_id"),
                },
            )
            return normalized

        except Exception as exc:
            classification = classify_adapter_failure(exc)
            max_attempts = int(retry_policy.get("max_attempts") or 1)
            retryable_classes = set(retry_policy.get("retryable_failure_classes") or [])
            should_retry = (
                classification.get("retryable")
                and classification.get("failure_class") in retryable_classes
                and next_attempt < max_attempts
            )
            status = "queued" if should_retry else "failed"
            retry_decision = "retry_scheduled" if should_retry else "terminal_failure"
            next_retry_at = (
                (datetime.now(timezone.utc) + timedelta(seconds=int(retry_policy.get("backoff_seconds") or 0))).isoformat()
                if should_retry and not dry_run
                else None
            )
            dead_letter = None
            if not should_retry:
                dead_letter = self._upsert_notification_dead_letter(
                    retry=retry,
                    classification=classification,
                    requested_by=requested_by,
                    attempt_count=next_attempt,
                )
            updated_retry = {
                **retry,
                "status": status,
                "processed_at": self._utcnow(),
                "process_count": next_attempt,
                "requested_by": requested_by or retry.get("requested_by"),
                "latest_notification_receipt": None,
                "last_error": str(exc),
                "failure_classification": classification,
                "retry_policy_id": retry_policy.get("policy_id"),
                "retry_policy": retry_policy,
                "retry_decision": retry_decision,
                "next_retry_at": next_retry_at,
                "dead_letter_id": dead_letter["dead_letter_id"] if dead_letter else retry.get("dead_letter_id"),
            }
            saved = self.repository.save_review_record(self._notification_retry_record(updated_retry))
            normalized = self._normalize_notification_retry(saved)
            self._track_batch_event(
                "async_notification_retry_failed",
                {
                    "requested_by": requested_by or retry.get("requested_by") or "ops_web",
                    "retry_id": normalized["retry_id"],
                    "source_event_id": retry["source_event_id"],
                    "sink_name": resolved_sink,
                    "status": normalized["status"],
                    "retry_policy_id": retry_policy.get("policy_id"),
                    "failure_classification": classification,
                    "retry_decision": retry_decision,
                },
            )
            return normalized

    def notification_retry_outcome_dashboard(self, *, limit: int = 20) -> Dict[str, Any]:
        records = self.repository.list_review_records(
            asset_type=ASYNC_NOTIFICATION_RETRY_ASSET_TYPE,
        )
        retries = [self._normalize_notification_retry(item) for item in records]
        retries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        dead_letters = self.list_notification_dead_letter_queue(limit=limit)
        by_status: Dict[str, int] = {}
        by_sink: Dict[str, int] = {}
        by_event_type: Dict[str, int] = {}
        by_failure_class: Dict[str, int] = {}
        by_retry_decision: Dict[str, int] = {}
        successful_retry_count = 0
        planned_retry_count = 0
        terminal_failure_count = 0
        processed_attempt_count = 0

        for item in retries:
            status_key = str(item.get("status") or "unknown")
            by_status[status_key] = by_status.get(status_key, 0) + 1
            sink_key = str(item.get("source_sink_name") or "unknown")
            by_sink[sink_key] = by_sink.get(sink_key, 0) + 1
            event_key = str(item.get("source_event_type") or "unknown")
            by_event_type[event_key] = by_event_type.get(event_key, 0) + 1
            failure_key = str((item.get("failure_classification") or {}).get("failure_class") or "none")
            by_failure_class[failure_key] = by_failure_class.get(failure_key, 0) + 1
            decision_key = str(item.get("retry_decision") or "unknown")
            by_retry_decision[decision_key] = by_retry_decision.get(decision_key, 0) + 1

            if status_key == "succeeded":
                successful_retry_count += 1
            if status_key == "planned":
                planned_retry_count += 1
            if decision_key == "terminal_failure":
                terminal_failure_count += 1
            if int(item.get("process_count") or 0) > 0:
                processed_attempt_count += 1

        success_rate = round(successful_retry_count / float(processed_attempt_count), 3) if processed_attempt_count else None
        return {
            "generated_at": self._utcnow(),
            "retry_count": len(retries),
            "dead_letter_count": dead_letters.get("dead_letter_count", 0),
            "by_status": by_status,
            "by_sink": by_sink,
            "by_event_type": by_event_type,
            "by_failure_class": by_failure_class,
            "by_retry_decision": by_retry_decision,
            "successful_retry_count": successful_retry_count,
            "planned_retry_count": planned_retry_count,
            "terminal_failure_count": terminal_failure_count,
            "success_rate": success_rate,
            "latest_dead_letters": dead_letters.get("dead_letters", [])[:limit],
            "latest_retry_outcomes": retries[:limit],
        }

    def notification_delivery_receipt_detail(self, event_id: int) -> Dict[str, Any]:
        events = self.repository.list_analytics_events(
            event_names=["async_job_notification_sent", "async_job_notification_planned"],
            limit=500,
        )
        target_event = next((item for item in events if int(item.get("event_id") or -1) == int(event_id)), None)
        if target_event is None:
            raise KeyError(f"unknown_notification_receipt:{event_id}")
        receipt = self._notification_receipt_from_event(target_event)
        target_path = str(receipt.get("target_path") or "")
        target = Path(target_path) if target_path else None
        parsed_target_payload: Dict[str, Any] | None = None
        if target and target.exists() and target.is_file():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    parsed_target_payload = loaded
            except Exception:
                parsed_target_payload = None
        payload_preview = {
            "has_receipt": bool(parsed_target_payload and parsed_target_payload.get("receipt")),
            "has_payload": bool(parsed_target_payload and parsed_target_payload.get("payload")),
            "payload_keys": sorted(list((parsed_target_payload or {}).keys())),
        }
        return {
            "generated_at": self._utcnow(),
            "receipt": receipt,
            "target_payload_preview": payload_preview,
            "target_payload": parsed_target_payload,
        }

    def ship_remote_artifacts(
        self,
        job_id: str,
        *,
        requested_by: Optional[str] = None,
        remote_dir: Optional[str] = None,
        dry_run: bool = False,
        adapter_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        job = self.get_job(job_id)
        inventory = self._artifact_inventory(job)
        shipped_items: List[Dict[str, Any]] = []
        for item in inventory.get("items", []):
            if not item.get("exists"):
                continue
            source = Path(str(item.get("path")))
            shipped_items.append(
                {
                    "label": item.get("label"),
                    "source_path": str(source),
                    "path_type": item.get("path_type"),
                    "size_bytes": item.get("size_bytes", 0),
                }
            )
        adapter = self.remote_shipping_registry.get(adapter_name)
        shipping_result = adapter.ship(
            job_id=job_id,
            items=shipped_items,
            remote_dir=remote_dir,
            dry_run=dry_run,
        )
        action = "remote_shipping_planned" if dry_run else "remote_shipping_enforced"
        updated = self._append_shipping_action(
            job,
            action=action,
            requested_by=requested_by,
            shipped_items=list(shipping_result.get("shipped_items") or []),
            dry_run=dry_run,
            remote_dir=shipping_result.get("remote_dir"),
            remote_manifest_path=shipping_result.get("remote_manifest_path"),
        )
        updated = self._save_job(updated)
        result = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_web",
            "dry_run": dry_run,
            "adapter_name": adapter.adapter_name,
            "job": updated,
            "registry": self.remote_shipping_registry.summary(),
            "remote_dir": shipping_result.get("remote_dir"),
            "remote_manifest_path": shipping_result.get("remote_manifest_path"),
            "shipped_item_count": shipping_result.get("shipped_item_count", 0),
            "shipped_items": shipping_result.get("shipped_items", []),
        }
        self._track_batch_event(
            "async_job_remote_shipping_planned" if dry_run else "async_job_remote_shipping_applied",
            {
                "requested_by": requested_by or "ops_web",
                "job_id": job_id,
                "job_type": job.get("job_type"),
                "status": updated.get("status"),
                "adapter_name": adapter.adapter_name,
                "shipped_item_count": shipping_result.get("shipped_item_count", 0),
                "remote_dir": shipping_result.get("remote_dir"),
            },
        )
        return result

    def handoff_sla_snapshot(self, *, sla_minutes: int = DEFAULT_HANDOFF_SLA_MINUTES, limit: int = 20) -> Dict[str, Any]:
        entries = self._handoff_job_entries(limit=max(limit * 4, 50), sla_minutes=sla_minutes)
        overdue = [item for item in entries if item.get("handoff_sla_status") == "overdue"]
        pending = [item for item in entries if item.get("handoff_sla_status") == "within_sla"]
        acknowledged = [item for item in entries if item.get("handoff_sla_status") == "acknowledged"]
        by_status: Dict[str, int] = {}
        for item in entries:
            status = str(item.get("handoff_sla_status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "generated_at": self._utcnow(),
            "sla_minutes": sla_minutes,
            "required_count": len([item for item in entries if item.get("handoff_required")]),
            "overdue_count": len(overdue),
            "pending_count": len(pending),
            "acknowledged_count": len(acknowledged),
            "by_status": by_status,
            "overdue_jobs": overdue[:limit],
            "pending_jobs": pending[:limit],
            "recommended_action": "escalate_overdue_handoffs" if overdue else ("await_acknowledgement" if pending else "none"),
        }

    def enforce_artifact_retention(
        self,
        *,
        requested_by: Optional[str] = None,
        dry_run: bool = False,
        limit: int = 20,
    ) -> Dict[str, Any]:
        snapshot = self.artifact_retention_snapshot(limit=max(limit * 4, 50))
        expired_jobs = [item for item in snapshot.get("artifact_jobs", []) if item.get("artifact_status") == "expired"]
        cleaned_jobs: List[Dict[str, Any]] = []
        removed_item_count = 0
        removed_bytes = 0
        for entry in expired_jobs[:limit]:
            job = self.get_job(str(entry.get("job_id")))
            inventory = self._artifact_inventory(job)
            removed_items: List[Dict[str, Any]] = []
            for item in inventory.get("items", []):
                if not item.get("exists"):
                    continue
                removed_item = {
                    "label": item.get("label"),
                    "path": item.get("path"),
                    "path_type": item.get("path_type"),
                    "size_bytes": item.get("size_bytes", 0),
                }
                removed_items.append(removed_item)
                removed_item_count += 1
                removed_bytes += int(item.get("size_bytes") or 0)
                if dry_run:
                    continue
                target = Path(str(item.get("path")))
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.exists():
                    target.unlink()
            action = "artifact_cleanup_planned" if dry_run else "artifact_cleanup_enforced"
            updated = self._append_cleanup_action(
                job,
                action=action,
                requested_by=requested_by,
                removed_items=removed_items,
                dry_run=dry_run,
            )
            updated = self._save_job(updated)
            cleaned_jobs.append(updated)
        result = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_web",
            "dry_run": dry_run,
            "expired_job_count": len(expired_jobs),
            "cleaned_job_count": len(cleaned_jobs),
            "removed_item_count": removed_item_count,
            "removed_bytes": removed_bytes,
            "cleaned_jobs": cleaned_jobs[:limit],
            "recommended_next_action": "review_missing_artifacts" if cleaned_jobs and not dry_run else "none",
        }
        self._track_batch_event(
            "async_job_artifact_cleanup_applied" if not dry_run else "async_job_artifact_cleanup_planned",
            result,
        )
        return result

    def operator_run_history(
        self,
        *,
        operator_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=max(limit * 4, 100))
        entries: List[Dict[str, Any]] = []
        for job in jobs:
            requested_by = job.get("requested_by")
            if requested_by:
                entries.append(
                    {
                        "occurred_at": job.get("created_at"),
                        "operator_id": requested_by,
                        "action": "enqueue_job",
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "job_status": job.get("status"),
                    }
                )
            for item in list(job.get("recovery_history") or []):
                entries.append(
                    {
                        "occurred_at": item.get("occurred_at"),
                        "operator_id": item.get("requested_by"),
                        "action": item.get("action"),
                        "reason": item.get("reason"),
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "job_status": job.get("status"),
                    }
                )
            for item in list(job.get("cleanup_history") or []):
                entries.append(
                    {
                        "occurred_at": item.get("occurred_at"),
                        "operator_id": item.get("requested_by"),
                        "action": item.get("action"),
                        "reason": "dry_run" if item.get("dry_run") else "cleanup",
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "job_status": job.get("status"),
                    }
                )
            for item in list(job.get("acknowledgement_history") or []):
                entries.append(
                    {
                        "occurred_at": item.get("occurred_at"),
                        "operator_id": item.get("requested_by"),
                        "action": item.get("action"),
                        "reason": item.get("note"),
                        "job_id": job.get("job_id"),
                        "job_type": job.get("job_type"),
                        "job_status": job.get("status"),
                    }
                )
        batch_events = self.repository.list_analytics_events(
            event_names=[
                "async_job_artifact_cleanup_applied",
                "async_job_artifact_cleanup_planned",
                "async_job_cold_start_recovery_drill_run",
                "async_job_handoff_bundle_exported",
                "async_job_remote_shipping_applied",
                "async_job_remote_shipping_planned",
                "async_job_handoff_sla_escalated",
                "async_job_handoff_sla_escalation_planned",
            ],
            limit=max(limit * 4, 100),
        )
        for event in batch_events:
            payload = dict(event.get("payload_json") or {})
            entries.append(
                {
                    "occurred_at": event.get("occurred_at"),
                    "operator_id": payload.get("requested_by"),
                    "action": event.get("event_name"),
                    "reason": payload.get("recommended_next_action"),
                    "job_id": payload.get("job_id"),
                    "job_type": payload.get("job_type") or "async_job_batch",
                    "job_status": payload.get("status"),
                }
            )
        if operator_id is not None:
            entries = [item for item in entries if item.get("operator_id") == operator_id]
        entries.sort(key=lambda item: str(item.get("occurred_at") or ""), reverse=True)
        by_operator: Dict[str, int] = {}
        by_action: Dict[str, int] = {}
        for item in entries:
            by_operator[str(item.get("operator_id") or "unknown")] = by_operator.get(str(item.get("operator_id") or "unknown"), 0) + 1
            by_action[str(item.get("action") or "unknown")] = by_action.get(str(item.get("action") or "unknown"), 0) + 1
        return {
            "generated_at": self._utcnow(),
            "operator_count": len(by_operator),
            "entry_count": len(entries[:limit]),
            "by_operator": by_operator,
            "by_action": by_action,
            "latest_entries": entries[:limit],
        }

    def acknowledge_job(
        self,
        job_id: str,
        *,
        requested_by: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        job = self.get_job(job_id)
        occurred_at = self._utcnow()
        history = list(job.get("acknowledgement_history") or [])
        history.insert(
            0,
            {
                "action": "acknowledge_job",
                "requested_by": requested_by or "ops_web",
                "note": note or "",
                "occurred_at": occurred_at,
            },
        )
        acknowledged = {
            **job,
            "acknowledged_by": requested_by or "ops_web",
            "acknowledged_at": occurred_at,
            "acknowledgement_note": note or "",
            "acknowledgement_history": history[:10],
            "acknowledgement_count": int(job.get("acknowledgement_count") or 0) + 1,
            "handoff_sla_escalated_at": None,
        }
        acknowledged = self._save_job(acknowledged)
        self._track("async_job_acknowledged", job=acknowledged)
        return acknowledged

    def escalate_handoff_sla(
        self,
        *,
        requested_by: Optional[str] = None,
        sla_minutes: int = DEFAULT_HANDOFF_SLA_MINUTES,
        limit: int = 20,
        dry_run: bool = False,
        sink_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        snapshot = self.handoff_sla_snapshot(sla_minutes=sla_minutes, limit=max(limit * 4, 50))
        overdue_jobs = list(snapshot.get("overdue_jobs") or [])
        escalated_jobs: List[Dict[str, Any]] = []
        for entry in overdue_jobs[:limit]:
            job = self.get_job(str(entry.get("job_id")))
            updated = self._append_sla_escalation_action(
                job,
                action="handoff_sla_escalation_planned" if dry_run else "handoff_sla_escalated",
                requested_by=requested_by,
                note=f"sla_minutes:{sla_minutes}",
                dry_run=dry_run,
            )
            updated = self._save_job(updated)
            escalated_jobs.append(updated)
        result = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_web",
            "dry_run": dry_run,
            "sla_minutes": sla_minutes,
            "overdue_count": len(overdue_jobs),
            "escalated_count": len(escalated_jobs),
            "escalated_jobs": escalated_jobs[:limit],
            "recommended_next_action": "export_handoff_bundle" if escalated_jobs and not dry_run else "none",
        }
        notification_receipt = self._send_notification(
            event_type="async_job_handoff_sla_escalation",
            payload=result,
            requested_by=requested_by,
            dry_run=dry_run,
            sink_name=sink_name,
        )
        result["notification_receipt"] = notification_receipt
        self._track_batch_event(
            "async_job_handoff_sla_escalation_planned" if dry_run else "async_job_handoff_sla_escalated",
            result,
        )
        return result

    def build_handoff_bundle(
        self,
        *,
        requested_by: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        incidents = self.incident_snapshot(limit=limit)
        retention = self.artifact_retention_snapshot(limit=limit)
        remote_shipping = self.remote_shipping_snapshot(limit=limit)
        handoff_sla = self.handoff_sla_snapshot(limit=limit)
        history = self.operator_run_history(limit=max(limit * 2, 20))
        job_entries = self._handoff_job_entries(limit=limit)
        requiring = [item for item in job_entries if item.get("handoff_required")]
        pending = [item for item in requiring if item.get("acknowledgement_status") == "pending"]
        acknowledged = [item for item in requiring if item.get("acknowledgement_status") == "acknowledged"]
        bundle = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_web",
            "queue_summary": self.queue_summary(limit=limit),
            "incident_snapshot": incidents,
            "artifact_retention": retention,
            "remote_shipping": remote_shipping,
            "handoff_sla": handoff_sla,
            "notification_sinks": self.notification_sink_registry.summary(),
            "operator_history": {
                "operator_count": history.get("operator_count"),
                "entry_count": history.get("entry_count"),
                "by_operator": history.get("by_operator", {}),
                "by_action": history.get("by_action", {}),
            },
            "jobs_requiring_handoff": requiring,
            "acknowledgement_summary": {
                "required_count": len(requiring),
                "pending_count": len(pending),
                "acknowledged_count": len(acknowledged),
            },
            "recommended_next_action": (
                "escalate_overdue_handoffs"
                if handoff_sla.get("overdue_count", 0)
                else (
                    "ship_remote_artifacts"
                    if any(item.get("remote_shipping_status") == "not_shipped" for item in requiring)
                    else (
                        "acknowledge_pending_jobs"
                        if pending
                        else ("review_failed_jobs" if incidents.get("failed_count", 0) else "none")
                    )
                )
            ),
        }
        return bundle

    def export_handoff_bundle(
        self,
        *,
        requested_by: Optional[str] = None,
        limit: int = 20,
        output_dir: Optional[str] = None,
        sink_name: Optional[str] = None,
        dry_run_notification: bool = False,
    ) -> Dict[str, Any]:
        bundle = self.build_handoff_bundle(requested_by=requested_by, limit=limit)
        handoff_dir = self._handoff_bundle_dir(output_dir)
        handoff_dir.mkdir(parents=True, exist_ok=True)
        export_path = handoff_dir / f"handoff_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
        export_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        notification_receipt = self._send_notification(
            event_type="async_job_handoff_bundle_exported",
            payload={"export_path": str(export_path), "handoff_bundle": bundle},
            requested_by=requested_by,
            dry_run=dry_run_notification,
            sink_name=sink_name,
        )
        result = {
            "generated_at": bundle["generated_at"],
            "requested_by": requested_by or "ops_web",
            "export_path": str(export_path),
            "handoff_bundle": bundle,
            "notification_receipt": notification_receipt,
        }
        self._track_batch_event("async_job_handoff_bundle_exported", result)
        return result

    def notification_sink_snapshot(self) -> Dict[str, Any]:
        return {
            "generated_at": self._utcnow(),
            **self.notification_sink_registry.summary(),
        }

    def dispatch_author_notification(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        requested_by: Optional[str] = None,
        dry_run: bool = False,
        sink_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._send_notification(
            event_type=event_type,
            payload=payload,
            requested_by=requested_by,
            dry_run=dry_run,
            sink_name=sink_name,
        )

    def _send_notification(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        requested_by: Optional[str] = None,
        dry_run: bool = False,
        sink_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        sink = self.notification_sink_registry.get(sink_name)
        receipt = sink.notify(
            event_type=event_type,
            payload=payload,
            dry_run=dry_run,
        )
        tracked = self._track_batch_event(
            "async_job_notification_planned" if dry_run else "async_job_notification_sent",
            {
                "requested_by": requested_by or "ops_web",
                "sink_name": sink.sink_name,
                "event_type": event_type,
                "target_path": receipt.get("target_path"),
                "status": receipt.get("status"),
            },
        )
        if tracked and tracked.get("event_id") is not None:
            receipt["event_id"] = tracked.get("event_id")
        return receipt

    def run_cold_start_recovery_drill(
        self,
        *,
        requested_by: Optional[str] = None,
        stale_after_minutes: int = 15,
        limit: int = 20,
    ) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=max(limit * 4, 50))
        running_jobs = [item for item in jobs if item.get("status") == "running"]
        queued_jobs = [item for item in jobs if item.get("status") == "queued"]
        failed_jobs = [item for item in jobs if item.get("status") == "failed"]
        would_reconcile = [
            {
                "job_id": item.get("job_id"),
                "job_type": item.get("job_type"),
                "lease_status": item.get("lease_status"),
                "lease_owner": item.get("lease_owner"),
            }
            for item in running_jobs[:limit]
        ]
        would_recover = [
            {
                "job_id": item.get("job_id"),
                "job_type": item.get("job_type"),
                "source": "queued" if item.get("status") == "queued" else "running",
            }
            for item in (queued_jobs + running_jobs)[:limit]
        ]
        result = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_web",
            "stale_after_minutes": stale_after_minutes,
            "running_job_count": len(running_jobs),
            "queued_job_count": len(queued_jobs),
            "failed_job_count": len(failed_jobs),
            "would_reconcile_count": len(running_jobs),
            "would_reconcile_jobs": would_reconcile,
            "would_recover_count": len(queued_jobs) + len(running_jobs),
            "would_recover_jobs": would_recover,
            "recommended_operator_steps": [
                "1. Boot reconciler would move running jobs back to queued.",
                "2. Recover incidents would resume queued or stale jobs.",
                "3. Failed jobs still require explicit retry.",
            ],
            "recommended_next_action": (
                "simulate_boot_reconcile_and_resume"
                if running_jobs or queued_jobs
                else ("retry_failed_jobs" if failed_jobs else "none")
            ),
        }
        self._track_batch_event("async_job_cold_start_recovery_drill_run", result)
        return result

    def _is_stale_running_job(self, job: Dict[str, Any], *, stale_after_minutes: int = 15) -> bool:
        if job.get("status") != "running":
            return False
        if self._lease_status(job) == "expired":
            return True
        heartbeat_reference = job.get("heartbeat_at") or job.get("updated_at") or job.get("started_at")
        if heartbeat_reference:
            age = datetime.now(timezone.utc) - self._parse_timestamp(heartbeat_reference)
            return age >= timedelta(minutes=max(1, stale_after_minutes))
        reference = self._parse_timestamp(job.get("started_at") or job.get("updated_at"))
        age = datetime.now(timezone.utc) - reference
        return age >= timedelta(minutes=max(1, stale_after_minutes))

    def incident_snapshot(self, *, stale_after_minutes: int = 15, limit: int = 20) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=max(limit * 4, 50))
        failed_jobs = [item for item in jobs if item.get("status") == "failed"]
        queued_jobs = [item for item in jobs if item.get("status") == "queued"]
        stale_running_jobs = [
            item for item in jobs if self._is_stale_running_job(item, stale_after_minutes=stale_after_minutes)
        ]
        recoverable_jobs = queued_jobs + stale_running_jobs
        by_type: Dict[str, int] = {}
        for job in failed_jobs + recoverable_jobs:
            job_type = str(job.get("job_type") or "unknown")
            by_type[job_type] = by_type.get(job_type, 0) + 1
        status = "healthy"
        if stale_running_jobs or failed_jobs:
            status = "incident"
        elif queued_jobs:
            status = "degraded"
        return {
            "generated_at": self._utcnow(),
            "status": status,
            "stale_after_minutes": stale_after_minutes,
            "failed_count": len(failed_jobs),
            "queued_count": len(queued_jobs),
            "stale_running_count": len(stale_running_jobs),
            "recoverable_count": len(recoverable_jobs),
            "by_type": by_type,
            "recommended_action": (
                "retry_failed_jobs_and_resume_stale_jobs"
                if failed_jobs or stale_running_jobs
                else ("resume_queued_jobs" if queued_jobs else "none")
            ),
            "expired_lease_count": len([item for item in stale_running_jobs if item.get("lease_status") == "expired"]),
            "failed_jobs": failed_jobs[:limit],
            "queued_jobs": queued_jobs[:limit],
            "stale_running_jobs": stale_running_jobs[:limit],
        }

    def enqueue_job(
        self,
        *,
        job_type: str,
        payload: Optional[Dict[str, Any]] = None,
        requested_by: Optional[str] = None,
        account_id: Optional[str] = None,
        schedule: Optional[Callable[[Callable[..., Any], str], None]] = None,
    ) -> Dict[str, Any]:
        if job_type not in self._runners:
            raise ValueError(f"unsupported_async_job_type:{job_type}")
        now = self._utcnow()
        job = {
            "job_id": f"job_{uuid4().hex[:12]}",
            "job_type": job_type,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "requested_by": requested_by or "ops_async",
            "account_id": account_id,
            "payload": dict(payload or {}),
            "result_summary": None,
            "error": None,
            "duration_seconds": None,
            "attempt_count": 0,
            "artifacts": {},
            "lease_owner": None,
            "lease_acquired_at": None,
            "lease_expires_at": None,
            "lease_timeout_minutes": 15,
            "heartbeat_at": None,
            "heartbeat_count": 0,
        }
        saved = self._save_job(job)
        self._track("async_job_enqueued", job=saved)
        if schedule is not None:
            schedule(self.run_job, saved["job_id"])
        return saved

    def heartbeat_job(
        self,
        job_id: str,
        *,
        requested_by: Optional[str] = None,
        lease_timeout_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        job = self.get_job(job_id)
        if job.get("status") != "running":
            raise ValueError("async_job_not_running")
        now = self._utcnow()
        timeout_minutes = max(1, int(lease_timeout_minutes or self._default_lease_timeout_minutes(job)))
        heartbeat = {
            **job,
            "heartbeat_at": now,
            "heartbeat_count": int(job.get("heartbeat_count") or 0) + 1,
            "lease_expires_at": (self._parse_timestamp(now) + timedelta(minutes=timeout_minutes)).isoformat(),
            "lease_timeout_minutes": timeout_minutes,
            "lease_owner": requested_by or job.get("lease_owner") or "async_runner",
        }
        heartbeat = self._save_job(heartbeat)
        self._track("async_job_heartbeat_recorded", job=heartbeat)
        return heartbeat

    def reconcile_on_boot(
        self,
        *,
        requested_by: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        jobs = self.list_jobs(limit=limit)
        reconciled_jobs: List[Dict[str, Any]] = []
        for job in jobs:
            if job.get("status") != "running":
                continue
            reconciled = {
                **job,
                "status": "queued",
                "started_at": None,
                "finished_at": None,
                "duration_seconds": None,
                "error": None,
                "last_error": job.get("error") or job.get("last_error"),
                "lease_owner": None,
                "lease_acquired_at": None,
                "lease_expires_at": None,
            }
            reconciled = self._append_recovery_action(
                reconciled,
                action="boot_reconciled_orphaned_running_job",
                requested_by=requested_by or "boot_reconciler",
                reason=f"lease_status:{job.get('lease_status') or 'unknown'}",
            )
            reconciled = self._save_job(reconciled)
            reconciled_jobs.append(reconciled)
        summary = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "boot_reconciler",
            "reconciled_count": len(reconciled_jobs),
            "reconciled_jobs": reconciled_jobs,
            "recommended_action": "resume_reconciled_jobs_manually" if reconciled_jobs else "none",
        }
        if reconciled_jobs:
            self._track(
                "async_job_boot_reconciled",
                job={
                    "job_id": "boot_reconciler",
                    "job_type": "async_job_boot_reconcile",
                    "status": "succeeded",
                    "requested_by": requested_by or "boot_reconciler",
                    "account_id": None,
                    "result_summary": {
                        "reconciled_count": len(reconciled_jobs),
                        "job_ids": [item["job_id"] for item in reconciled_jobs],
                    },
                    "error": None,
                },
            )
        return summary

    def _schedule_run(
        self,
        job: Dict[str, Any],
        *,
        schedule: Optional[Callable[[Callable[..., Any], str], None]] = None,
    ) -> Dict[str, Any]:
        if schedule is not None:
            schedule(self.run_job, job["job_id"])
            return self.get_job(job["job_id"])
        return job

    def retry_job(
        self,
        job_id: str,
        *,
        requested_by: Optional[str] = None,
        schedule: Optional[Callable[[Callable[..., Any], str], None]] = None,
    ) -> Dict[str, Any]:
        job = self.get_job(job_id)
        if job.get("status") != "failed":
            raise ValueError("async_job_not_failed")
        retried = {
            **job,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "error": None,
            "last_error": job.get("error"),
            "requested_by": requested_by or job.get("requested_by"),
            "lease_owner": None,
            "lease_acquired_at": None,
            "lease_expires_at": None,
        }
        retried = self._append_recovery_action(
            retried,
            action="retry_failed_job",
            requested_by=requested_by,
            reason="manual_retry",
        )
        retried = self._save_job(retried)
        self._track("async_job_retried", job=retried)
        return self._schedule_run(retried, schedule=schedule)

    def resume_job(
        self,
        job_id: str,
        *,
        requested_by: Optional[str] = None,
        stale_after_minutes: int = 15,
        force: bool = False,
        schedule: Optional[Callable[[Callable[..., Any], str], None]] = None,
    ) -> Dict[str, Any]:
        job = self.get_job(job_id)
        can_resume = job.get("status") == "queued" or force or self._is_stale_running_job(
            job,
            stale_after_minutes=stale_after_minutes,
        )
        if not can_resume:
            raise ValueError("async_job_not_resumable")
        resumed = {
            **job,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "error": None,
            "last_error": job.get("error") or job.get("last_error"),
            "requested_by": requested_by or job.get("requested_by"),
            "lease_owner": None,
            "lease_acquired_at": None,
            "lease_expires_at": None,
        }
        resumed = self._append_recovery_action(
            resumed,
            action="resume_job",
            requested_by=requested_by,
            reason="manual_resume" if force or job.get("status") == "running" else "resume_queued_job",
        )
        resumed = self._save_job(resumed)
        self._track("async_job_resumed", job=resumed)
        return self._schedule_run(resumed, schedule=schedule)

    def recover_incidents(
        self,
        *,
        requested_by: Optional[str] = None,
        stale_after_minutes: int = 15,
        limit: int = 10,
        schedule: Optional[Callable[[Callable[..., Any], str], None]] = None,
    ) -> Dict[str, Any]:
        snapshot = self.incident_snapshot(stale_after_minutes=stale_after_minutes, limit=limit)
        recovered_jobs: List[Dict[str, Any]] = []
        for job in (snapshot.get("queued_jobs") or [])[:limit]:
            recovered_jobs.append(
                self.resume_job(
                    job["job_id"],
                    requested_by=requested_by,
                    stale_after_minutes=stale_after_minutes,
                    schedule=schedule,
                )
            )
        for job in (snapshot.get("stale_running_jobs") or [])[: max(0, limit - len(recovered_jobs))]:
            recovered_jobs.append(
                self.resume_job(
                    job["job_id"],
                    requested_by=requested_by,
                    stale_after_minutes=stale_after_minutes,
                    schedule=schedule,
                )
            )
        result = {
            "generated_at": self._utcnow(),
            "requested_by": requested_by or "ops_async",
            "stale_after_minutes": stale_after_minutes,
            "recovered_count": len(recovered_jobs),
            "recovered_jobs": recovered_jobs,
            "remaining_failed_count": snapshot.get("failed_count", 0),
            "recommended_next_action": "retry_failed_jobs_manually" if snapshot.get("failed_count", 0) else "none",
        }
        if recovered_jobs:
            self._track(
                "async_job_incident_recovery_applied",
                job={
                    "job_id": "batch_recovery",
                    "job_type": "async_job_recovery",
                    "status": "succeeded",
                    "requested_by": requested_by or "ops_async",
                    "account_id": None,
                    "result_summary": {
                        "recovered_count": len(recovered_jobs),
                        "remaining_failed_count": snapshot.get("failed_count", 0),
                    },
                    "error": None,
                },
            )
        return result

    def run_job(self, job_id: str) -> Dict[str, Any]:
        job = self.get_job(job_id)
        if job.get("status") not in {"queued", "failed"}:
            return job
        started_at = self._utcnow()
        running = {
            **job,
            "status": "running",
            "started_at": started_at,
            "attempt_count": int(job.get("attempt_count") or 0) + 1,
            "error": None,
            "lease_owner": "fastapi_background_tasks",
            "lease_acquired_at": started_at,
            "lease_expires_at": (
                self._parse_timestamp(started_at) + timedelta(minutes=self._default_lease_timeout_minutes(job))
            ).isoformat(),
            "lease_timeout_minutes": self._default_lease_timeout_minutes(job),
            "heartbeat_at": started_at,
            "heartbeat_count": int(job.get("heartbeat_count") or 0) + 1,
        }
        running = self._save_job(running)
        self._track("async_job_started", job=running)
        runner = self._runners[job["job_type"]]
        started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        try:
            result = runner(running)
            job_status_override = str((result or {}).get("_job_status_override") or "").strip().lower()
            try:
                latest_running = self.get_job(job_id)
            except KeyError:
                latest_running = running
            finished_at = self._utcnow()
            finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            final_status = "failed" if job_status_override == "failed" else "succeeded"
            completed = {
                **latest_running,
                "status": final_status,
                "finished_at": finished_at,
                "duration_seconds": round((finished_dt - started_dt).total_seconds(), 3),
                "result_summary": self._compact_result(job["job_type"], dict(result or {})),
                "artifacts": dict((result or {}).get("artifacts") or {}),
                "error": (result or {}).get("error") if final_status == "failed" else None,
                "last_error": (result or {}).get("error") if final_status == "failed" else latest_running.get("last_error"),
                "lease_owner": None,
                "lease_acquired_at": None,
                "lease_expires_at": None,
                "heartbeat_at": finished_at,
            }
            completed = self._save_job(completed)
            self._track("async_job_failed" if final_status == "failed" else "async_job_succeeded", job=completed)
            return completed
        except Exception as exc:  # pragma: no cover - exercised through API and runner failure tests
            try:
                latest_running = self.get_job(job_id)
            except KeyError:
                latest_running = running
            finished_at = self._utcnow()
            finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            failed = {
                **latest_running,
                "status": "failed",
                "finished_at": finished_at,
                "duration_seconds": round((finished_dt - started_dt).total_seconds(), 3),
                "error": str(exc),
                "last_error": str(exc),
                "lease_owner": None,
                "lease_acquired_at": None,
                "lease_expires_at": None,
                "heartbeat_at": finished_at,
            }
            failed = self._save_job(failed)
            self._track("async_job_failed", job=failed)
            return failed
