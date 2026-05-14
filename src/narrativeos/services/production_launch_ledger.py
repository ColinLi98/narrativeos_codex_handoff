from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .launch_command_center import LaunchCommandCenterService
from .production_acceptance import ProductionAcceptanceService
from .production_preflight import ProductionPreflightService
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]


class ProductionLaunchLedgerService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        production_signoff_service: ProductionSignoffService,
        production_acceptance_service: ProductionAcceptanceService,
        production_preflight_service: ProductionPreflightService,
        launch_command_center_service: LaunchCommandCenterService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.production_signoff = production_signoff_service
        self.production_acceptance = production_acceptance_service
        self.production_preflight = production_preflight_service
        self.launch_command_center = launch_command_center_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _event_id(self, *parts: str) -> str:
        digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:12]
        return f"production_launch_event_{digest}"

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_csv(self, path: Path, *, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def sync(self, *, actor_id: str, actor_role: str, launch_wave: str = "wave_1") -> Dict[str, Any]:
        acceptance = self.production_acceptance.list_acceptance_records(launch_wave=launch_wave, limit=100)
        signoff = self.production_signoff.current_signoff_summary()
        command_center = self.launch_command_center.command_center(launch_wave=launch_wave)
        audits = self.repository.list_audit_logs(limit=500)
        preflight_runs = self.repository.list_production_preflight_runs(launch_wave=launch_wave, limit=100)
        preflight_checks_by_run = {
            row["preflight_run_id"]: self.repository.list_production_preflight_checks(preflight_run_id=row["preflight_run_id"], limit=50)
            for row in preflight_runs
        }
        events: List[Dict[str, Any]] = []
        for audit in audits:
            action = str(audit.get("action_type") or "")
            internal = dict(audit.get("internal_payload_json") or {})
            if action == "production_signoff_initialized" and signoff:
                events.append(
                    self.repository.save_production_launch_event(
                        {
                            "launch_event_id": self._event_id(launch_wave, "audit", action, str(audit.get("audit_log_id") or "")),
                            "launch_wave": launch_wave,
                            "account_id": None,
                            "event_category": "signoff",
                            "event_type": action,
                            "phase": "prep",
                            "severity": "info",
                            "related_object_type": audit.get("object_type"),
                            "related_object_id": audit.get("object_id"),
                            "occurred_at": audit.get("created_at"),
                            "event_payload": {"audit_log_id": audit.get("audit_log_id"), "action_type": action},
                        }
                    )
                )
            if action == "launch_wave_status_updated" and str(internal.get("launch_wave") or "") == launch_wave:
                events.append(
                    self.repository.save_production_launch_event(
                        {
                            "launch_event_id": self._event_id(launch_wave, "audit", action, str(audit.get("audit_log_id") or "")),
                            "launch_wave": launch_wave,
                            "account_id": None,
                            "event_category": "launch_wave",
                            "event_type": action,
                            "phase": "go_no_go" if str(internal.get("status") or "") != "active" else "launch_day",
                            "severity": "info",
                            "related_object_type": audit.get("object_type"),
                            "related_object_id": audit.get("object_id"),
                            "occurred_at": audit.get("created_at"),
                            "event_payload": internal,
                        }
                    )
                )
            if action == "production_acceptance_generated":
                obj = dict(internal.get("acceptance_record") or {})
                if str(obj.get("launch_wave") or "") == launch_wave:
                    events.append(
                        self.repository.save_production_launch_event(
                            {
                                "launch_event_id": self._event_id(launch_wave, "audit", action, str(audit.get("audit_log_id") or "")),
                                "launch_wave": launch_wave,
                                "account_id": obj.get("account_id"),
                                "event_category": "acceptance",
                                "event_type": action,
                                "phase": "prep",
                                "severity": "warning" if str(obj.get("status") or "") == "blocked" else "info",
                                "related_object_type": audit.get("object_type"),
                                "related_object_id": audit.get("object_id"),
                                "occurred_at": audit.get("created_at"),
                                "event_payload": {"acceptance_status": obj.get("status")},
                            }
                        )
                    )
        for run in preflight_runs:
            phase = "go_no_go"
            severity = "critical" if str(run.get("status") or "") == "hard_failed" else ("warning" if str(run.get("status") or "") == "soft_failed" else "info")
            events.append(
                self.repository.save_production_launch_event(
                    {
                        "launch_event_id": self._event_id(launch_wave, "preflight_run", str(run.get("preflight_run_id") or "")),
                        "launch_wave": launch_wave,
                        "account_id": None,
                        "event_category": "preflight",
                        "event_type": "preflight_run",
                        "phase": phase,
                        "severity": severity,
                        "related_object_type": "production_preflight_run",
                        "related_object_id": run.get("preflight_run_id"),
                        "occurred_at": run.get("updated_at"),
                        "event_payload": {"status": run.get("status"), "go_no_go": run.get("go_no_go")},
                    }
                )
            )
            for check in preflight_checks_by_run.get(run["preflight_run_id"], []):
                events.append(
                    self.repository.save_production_launch_event(
                        {
                            "launch_event_id": self._event_id(launch_wave, "preflight_check", str(check.get("preflight_check_id") or "")),
                            "launch_wave": launch_wave,
                            "account_id": None,
                            "event_category": "preflight_check",
                            "event_type": check.get("check_key"),
                            "phase": "go_no_go",
                            "severity": "critical" if str(check.get("status") or "") == "hard_failed" else ("warning" if str(check.get("status") or "") == "soft_failed" else "info"),
                            "related_object_type": "production_preflight_check",
                            "related_object_id": check.get("preflight_check_id"),
                            "occurred_at": check.get("created_at"),
                            "event_payload": {"status": check.get("status"), "linked_signoff_item_code": check.get("linked_signoff_item_code")},
                        }
                    )
                )
        for panel_key in ("billing_anomaly_panel", "support_urgency_panel", "dispute_anomaly_panel", "dunning_anomaly_panel", "webhook_anomaly_panel"):
            panel = command_center.get(panel_key) or {}
            for alert in list(panel.get("alerts") or []):
                events.append(
                    self.repository.save_production_launch_event(
                        {
                            "launch_event_id": self._event_id(launch_wave, "alert", str(alert.get("alert_key") or ""), "/".join(sorted(str(x) for x in alert.get("account_ids") or []))),
                            "launch_wave": launch_wave,
                            "account_id": next(iter(alert.get("account_ids") or []), None),
                            "event_category": "alert",
                            "event_type": alert.get("alert_key"),
                            "phase": "week_1",
                            "severity": alert.get("severity") or "warning",
                            "related_object_type": "launch_week_alert",
                            "related_object_id": alert.get("alert_key"),
                            "occurred_at": self._utcnow(),
                            "event_payload": {"count": alert.get("count"), "owner_role": alert.get("owner_role")},
                        }
                    )
                )
        return {
            "launch_wave": launch_wave,
            "event_count": len(events),
            "events": events,
        }

    def list_events(self, *, launch_wave: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        events = self.repository.list_production_launch_events(launch_wave=launch_wave, limit=limit)
        return {
            "events": events,
            "summary": {
                "event_count": len(events),
                "severity_counts": dict(Counter(str(item.get("severity") or "unknown") for item in events)),
                "phase_counts": dict(Counter(str(item.get("phase") or "unknown") for item in events)),
            },
        }

    def build_postmortem_pack(self, *, launch_wave: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        events = self.repository.list_production_launch_events(launch_wave=launch_wave, account_id=account_id, limit=500)
        summary = {
            "launch_wave": launch_wave,
            "account_id": account_id,
            "event_count": len(events),
            "severity_counts": dict(Counter(str(item.get("severity") or "unknown") for item in events)),
            "phase_counts": dict(Counter(str(item.get("phase") or "unknown") for item in events)),
        }
        postmortem = self.repository.save_production_postmortem_record(
            {
                "launch_wave": launch_wave,
                "account_id": account_id,
                "status": "draft",
                "summary": summary,
            }
        )
        run_id = f"production_postmortem_pack_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = self._artifacts_root() / "production_postmortem_pack" / run_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        timeline_lines = ["# Launch Timeline", ""] + [f"- {item['occurred_at']}: {item['event_category']} / {item['event_type']} / {item['severity']}" for item in events]
        incident_lines = ["# Incident Chronology", ""] + [f"- {item['occurred_at']}: {item['event_type']} -> {item['event_payload_json']}" for item in events if str(item.get("severity") or "") in {"warning", "critical"}]
        template_lines = [
            "# Postmortem Template",
            "",
            "## Summary",
            "- what happened",
            "- customer impact",
            "- revenue impact",
            "",
            "## Timeline",
            "- signoff to go-live",
            "- incidents and recovery steps",
            "",
            "## Actions",
            "- blockers to close",
            "- runbook changes",
            "- monitoring changes",
        ]
        rows = [
            {
                "occurred_at": item.get("occurred_at"),
                "event_category": item.get("event_category"),
                "event_type": item.get("event_type"),
                "severity": item.get("severity"),
                "phase": item.get("phase"),
                "related_object_type": item.get("related_object_type"),
                "related_object_id": item.get("related_object_id"),
            }
            for item in events
            if str(item.get("severity") or "") in {"warning", "critical"}
        ]
        self._write_text(bundle_dir / "launch_timeline.md", "\n".join(timeline_lines))
        self._write_text(bundle_dir / "incident_chronology.md", "\n".join(incident_lines))
        self._write_text(bundle_dir / "postmortem_template.md", "\n".join(template_lines))
        self._write_csv(
            bundle_dir / "blocker_delay_recovery_capture.csv",
            rows=rows,
            fieldnames=["occurred_at", "event_category", "event_type", "severity", "phase", "related_object_type", "related_object_id"],
        )
        self._write_json(bundle_dir / "summary.json", {"postmortem_record": postmortem, "summary": summary})
        latest_dir = self._artifacts_root() / "production_postmortem_pack" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "postmortem_record": postmortem,
            "artifact_refs": {
                "bundle_dir": str(bundle_dir),
                "summary_json": str(bundle_dir / "summary.json"),
                "launch_timeline_md": str(bundle_dir / "launch_timeline.md"),
                "incident_chronology_md": str(bundle_dir / "incident_chronology.md"),
                "blocker_delay_recovery_capture_csv": str(bundle_dir / "blocker_delay_recovery_capture.csv"),
                "postmortem_template_md": str(bundle_dir / "postmortem_template.md"),
            },
        }
