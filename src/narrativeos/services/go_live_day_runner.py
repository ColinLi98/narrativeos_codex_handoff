from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .customer_success_reporting import CustomerSuccessReportingService
from .launch_command_center import LaunchCommandCenterService
from .production_preflight import ProductionPreflightService
from .wave_activation_controller import WaveActivationControllerService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]

CHECKPOINT_KEYS = [
    "pre_activation_signoff_check",
    "pre_activation_preflight_check",
    "pre_activation_acceptance_check",
    "post_activation_t_plus_5",
    "post_activation_t_plus_15",
    "post_activation_t_plus_60",
]


class GoLiveDayRunnerService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        wave_activation_controller_service: WaveActivationControllerService,
        production_preflight_service: ProductionPreflightService,
        launch_command_center_service: LaunchCommandCenterService,
        customer_success_reporting_service: CustomerSuccessReportingService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.wave_activation = wave_activation_controller_service
        self.production_preflight = production_preflight_service
        self.launch_command_center = launch_command_center_service
        self.customer_success = customer_success_reporting_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

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
                writer.writerow({key: row.get(key) for key in fieldnames})

    def _record_checkpoint(
        self,
        *,
        run_id: str,
        checkpoint_key: str,
        status: str,
        summary: str,
        evidence_ref: str,
        rollback_recommendation: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.repository.save_go_live_day_checkpoint(
            {
                "go_live_day_run_id": run_id,
                "checkpoint_key": checkpoint_key,
                "status": status,
                "summary": summary,
                "evidence_ref": evidence_ref,
                "rollback_recommendation": rollback_recommendation,
                "checkpoint_payload": payload,
            }
        )

    def run(
        self,
        *,
        actor_id: str,
        actor_role: str,
        launch_wave: str = "wave_1",
        signoff_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.wave_activation.evaluate(
            launch_wave=launch_wave,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        account = account_id or next(iter(current.get("launch_account_ids") or []), None)
        run = self.repository.save_go_live_day_run(
            {
                "signoff_id": signoff_id or current.get("current_wave_status", {}).get("signoff_id"),
                "launch_wave": launch_wave,
                "account_id": account,
                "status": "running",
                "activation_state_before": current.get("activation_state"),
                "report_payload": {"requested_by": actor_id},
            }
        )
        checkpoints: List[Dict[str, Any]] = []

        signoff_ok = str(current.get("signoff_status") or "") == "fully_signed"
        checkpoints.append(
            self._record_checkpoint(
                run_id=run["go_live_day_run_id"],
                checkpoint_key="pre_activation_signoff_check",
                status="passed" if signoff_ok else "failed",
                summary=f"signoff={current.get('signoff_status')}",
                evidence_ref=str((current.get("current_wave_status") or {}).get("launch_wave_status_id") or ""),
                rollback_recommendation="do_not_activate" if not signoff_ok else "none",
                payload=current,
            )
        )
        preflight = self.production_preflight.list_runs(launch_wave=launch_wave, limit=1).get("current_run")
        preflight_ok = bool(preflight and str(preflight.get("status") or "") == "passed" and str(preflight.get("go_no_go") or "") == "go")
        checkpoints.append(
            self._record_checkpoint(
                run_id=run["go_live_day_run_id"],
                checkpoint_key="pre_activation_preflight_check",
                status="passed" if preflight_ok else "failed",
                summary=f"preflight={preflight.get('status') if preflight else '-'} / {preflight.get('go_no_go') if preflight else '-'}",
                evidence_ref=str((preflight or {}).get("preflight_run_id") or ""),
                rollback_recommendation="do_not_activate" if not preflight_ok else "none",
                payload=preflight or {},
            )
        )
        acceptance_ready = current.get("ready_account_count", 0) >= len(current.get("launch_account_ids") or []) and bool(current.get("launch_account_ids"))
        checkpoints.append(
            self._record_checkpoint(
                run_id=run["go_live_day_run_id"],
                checkpoint_key="pre_activation_acceptance_check",
                status="passed" if acceptance_ready else "failed",
                summary=f"ready_accounts={current.get('ready_account_count')} / launch_accounts={len(current.get('launch_account_ids') or [])}",
                evidence_ref=launch_wave,
                rollback_recommendation="do_not_activate" if not acceptance_ready else "none",
                payload=current,
            )
        )

        post_activation_state = current
        if signoff_ok and preflight_ok and acceptance_ready:
            if current.get("activation_state") != "active":
                armed = self.wave_activation.arm(actor_id=actor_id, actor_role=actor_role, launch_wave=launch_wave)
                post_activation_state = armed.get("evaluation") or post_activation_state

        for checkpoint_key, label in [
            ("post_activation_t_plus_5", "T+5"),
            ("post_activation_t_plus_15", "T+15"),
            ("post_activation_t_plus_60", "T+60"),
        ]:
            center = self.launch_command_center.command_center(launch_wave=launch_wave)
            critical_alerts = [
                item
                for panel_key in ("billing_anomaly_panel", "support_urgency_panel", "dispute_anomaly_panel", "dunning_anomaly_panel", "webhook_anomaly_panel")
                for item in list((center.get(panel_key) or {}).get("alerts") or [])
                if str(item.get("severity") or "") == "critical"
            ]
            success_report = self.customer_success.list_customer_success(launch_wave=launch_wave, limit=50)
            status = "passed" if post_activation_state.get("activation_state") == "active" and not critical_alerts else "failed"
            checkpoints.append(
                self._record_checkpoint(
                    run_id=run["go_live_day_run_id"],
                    checkpoint_key=checkpoint_key,
                    status=status,
                    summary=f"{label} active={post_activation_state.get('activation_state')} critical_alerts={len(critical_alerts)}",
                    evidence_ref=launch_wave,
                    rollback_recommendation="consider_rollback" if status == "failed" else "none",
                    payload={"command_center": center, "customer_success": success_report},
                )
            )

        overall_status = "passed"
        if any(checkpoint["checkpoint_key"].startswith("pre_activation") and checkpoint["status"] != "passed" for checkpoint in checkpoints):
            overall_status = "failed"
        elif any(checkpoint["checkpoint_key"].startswith("post_activation") and checkpoint["status"] != "passed" for checkpoint in checkpoints):
            overall_status = "rollback_watch"
        updated_run = self.repository.save_go_live_day_run(
            {
                **run,
                "status": overall_status,
                "activation_state_before": current.get("activation_state"),
                "activation_state_after": post_activation_state.get("activation_state"),
                "report_payload": {
                    "checkpoint_count": len(checkpoints),
                    "account_id": account,
                },
            }
        )
        report_refs = self._write_report(run=updated_run, checkpoints=checkpoints)
        return {
            "go_live_day_run": updated_run,
            "checkpoints": checkpoints,
            "report_refs": report_refs,
        }

    def _write_report(self, *, run: Dict[str, Any], checkpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
        bundle_dir = self._artifacts_root() / "go_live_day_runs" / run["go_live_day_run_id"]
        bundle_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(bundle_dir / "summary.json", {"go_live_day_run": run, "checkpoints": checkpoints})
        report = [
            "# Go-Live Day Report",
            "",
            f"- go_live_day_run_id: {run['go_live_day_run_id']}",
            f"- launch_wave: {run['launch_wave']}",
            f"- status: {run['status']}",
            f"- activation_before: {run.get('activation_state_before') or '-'}",
            f"- activation_after: {run.get('activation_state_after') or '-'}",
            "",
            "## Checkpoints",
        ]
        report.extend([f"- {item['checkpoint_key']}: {item['status']} · {item['summary']}" for item in checkpoints])
        self._write_text(bundle_dir / "day_0_report.md", "\n".join(report))
        self._write_csv(
            bundle_dir / "checkpoint_log.csv",
            rows=checkpoints,
            fieldnames=["go_live_day_checkpoint_id", "checkpoint_key", "status", "summary", "evidence_ref", "rollback_recommendation", "created_at"],
        )
        latest_dir = self._artifacts_root() / "go_live_day_runs" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "artifact_dir": str(bundle_dir),
            "summary_json": str(bundle_dir / "summary.json"),
            "day_0_report_md": str(bundle_dir / "day_0_report.md"),
            "checkpoint_log_csv": str(bundle_dir / "checkpoint_log.csv"),
        }

    def detail(self, *, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_go_live_day_run(run_id)
        checkpoints = self.repository.list_go_live_day_checkpoints(go_live_day_run_id=run_id, limit=100)
        artifact_dir = self._artifacts_root() / "go_live_day_runs" / run_id
        return {
            "go_live_day_run": run,
            "checkpoints": checkpoints,
            "report_refs": {
                "artifact_dir": str(artifact_dir),
                "summary_json": str(artifact_dir / "summary.json"),
                "day_0_report_md": str(artifact_dir / "day_0_report.md"),
                "checkpoint_log_csv": str(artifact_dir / "checkpoint_log.csv"),
            },
        }

    def summary(self, *, launch_wave: Optional[str] = None) -> Dict[str, Any]:
        runs = self.repository.list_go_live_day_runs(launch_wave=launch_wave, limit=50)
        current = runs[0] if runs else None
        return {
            "runs": runs,
            "current_run": current,
            "summary": {
                "run_count": len(runs),
                "latest_run_id": (current or {}).get("go_live_day_run_id"),
                "status_counts": {key: len([item for item in runs if str(item.get("status") or "") == key]) for key in {"passed", "failed", "rollback_watch", "running"}},
            },
        }
