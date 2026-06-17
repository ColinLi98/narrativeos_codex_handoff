from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .commercial_audit import CommercialAuditService
from .launch_command_center import LaunchCommandCenterService
from .production_acceptance import ProductionAcceptanceService
from .production_preflight import ProductionPreflightService
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]


class WaveActivationControllerService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        production_signoff_service: ProductionSignoffService,
        production_acceptance_service: ProductionAcceptanceService,
        production_preflight_service: ProductionPreflightService,
        launch_command_center_service: LaunchCommandCenterService,
        commercial_audit_service: CommercialAuditService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.production_signoff = production_signoff_service
        self.production_acceptance = production_acceptance_service
        self.production_preflight = production_preflight_service
        self.launch_command_center = launch_command_center_service
        self.commercial_audit = commercial_audit_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _current_signoff_detail(self, launch_wave: str) -> Optional[Dict[str, Any]]:
        acceptance = self.production_acceptance.list_acceptance_records(launch_wave=launch_wave, limit=100)
        for record in list(acceptance.get("acceptance_records") or []):
            signoff_id = record.get("signoff_id")
            if signoff_id:
                try:
                    return self.production_signoff.signoff_detail(signoff_id=signoff_id)
                except KeyError:
                    continue
        current = self.production_signoff.current_signoff_summary()
        if current and current.get("signoff_id"):
            return self.production_signoff.signoff_detail(signoff_id=current["signoff_id"])
        return None

    def _latest_preflight(self, launch_wave: str) -> Optional[Dict[str, Any]]:
        return self.production_preflight.list_runs(launch_wave=launch_wave, limit=1).get("current_run")

    def _current_wave_status(self, launch_wave: str) -> Optional[Dict[str, Any]]:
        return next(iter(self.repository.list_launch_wave_statuses(launch_wave=launch_wave, limit=1)), None)

    def _launch_accounts(self, launch_wave: str) -> List[Dict[str, Any]]:
        latest: Dict[str, Dict[str, Any]] = {}
        for row in list(self.repository.list_go_live_ready_accounts(launch_wave=launch_wave, limit=200)):
            account_id = str(row.get("account_id") or "")
            if not account_id:
                continue
            if account_id not in latest or str(row.get("updated_at") or "") > str(latest[account_id].get("updated_at") or ""):
                latest[account_id] = row
        return list(latest.values())

    def _critical_alerts(self, launch_wave: str, account_ids: List[str]) -> List[Dict[str, Any]]:
        center = self.launch_command_center.command_center(launch_wave=launch_wave)
        alerts = []
        for panel_key in ("billing_anomaly_panel", "support_urgency_panel", "dispute_anomaly_panel", "dunning_anomaly_panel", "webhook_anomaly_panel"):
            alerts.extend(list((center.get(panel_key) or {}).get("alerts") or []))
        return [
            alert
            for alert in alerts
            if str(alert.get("severity") or "") == "critical"
            and (not account_ids or any(account_id in set(alert.get("account_ids") or []) for account_id in account_ids))
        ]

    def evaluate(self, *, launch_wave: str = "wave_1", actor_id: Optional[str] = None, actor_role: Optional[str] = None) -> Dict[str, Any]:
        signoff = self._current_signoff_detail(launch_wave)
        if signoff and actor_id and actor_role and str((signoff.get("signoff") or {}).get("status") or "") == "fully_signed":
            existing_accounts = {str(item.get("account_id") or "") for item in self._launch_accounts(launch_wave) if item.get("account_id")}
            for account_id in existing_accounts:
                self.production_acceptance.generate_acceptance_record(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    account_id=account_id,
                    launch_wave=launch_wave,
                    signoff_id=(signoff.get("signoff") or {}).get("signoff_id"),
                )
        preflight = self._latest_preflight(launch_wave)
        acceptance = self.production_acceptance.list_acceptance_records(launch_wave=launch_wave, limit=100)
        launch_accounts = self._launch_accounts(launch_wave)
        account_ids = [str(item.get("account_id") or "") for item in launch_accounts if item.get("account_id")]
        wave_status = self._current_wave_status(launch_wave)
        critical_alerts = self._critical_alerts(launch_wave, account_ids)
        blockers: List[str] = []
        if not launch_accounts:
            blockers.append("no_launch_customer_selected")
        if not signoff or str((signoff.get("signoff") or {}).get("status") or "") != "fully_signed":
            blockers.append("signoff_not_fully_signed")
        if not preflight or str(preflight.get("status") or "") != "passed" or str(preflight.get("go_no_go") or "") != "go":
            blockers.append("latest_preflight_not_go")
        ready_accounts = [item for item in launch_accounts if str(item.get("status") or "") == "ready"]
        if account_ids and len(ready_accounts) < len(account_ids):
            blockers.append("launch_acceptance_not_ready")
        if critical_alerts:
            blockers.append("critical_launch_alert_present")

        current_status = str((wave_status or {}).get("status") or "blocked")
        activation_state = "blocked"
        auto_activation_eligible = False
        if current_status == "active":
            activation_state = "active"
        elif current_status == "rollback_watch":
            activation_state = "rollback_watch"
        elif current_status == "armed":
            activation_state = "armed"
            auto_activation_eligible = len(blockers) == 0
        elif len(blockers) == 0:
            activation_state = "activation_ready"

        result = {
            "launch_wave": launch_wave,
            "activation_state": activation_state,
            "auto_activation_eligible": auto_activation_eligible,
            "blockers": blockers,
            "signoff_status": (signoff or {}).get("signoff", {}).get("status"),
            "preflight_status": (preflight or {}).get("status"),
            "go_no_go": (preflight or {}).get("go_no_go"),
            "ready_account_count": len(ready_accounts),
            "launch_account_ids": account_ids,
            "critical_alert_count": len(critical_alerts),
            "critical_alerts": critical_alerts,
            "current_wave_status": wave_status,
            "artifact_refs": self._latest_activation_artifact_refs() if activation_state == "active" else {},
        }
        if auto_activation_eligible and actor_id and actor_role:
            return self._activate(
                actor_id=actor_id,
                actor_role=actor_role,
                launch_wave=launch_wave,
                state_snapshot=result,
                signoff_id=(signoff or {}).get("signoff", {}).get("signoff_id"),
            )
        return result

    def _write_activation_bundle(self, *, launch_wave: str, state_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        run_id = f"wave_activation_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = self._artifacts_root() / "wave_activation" / run_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        report = "\n".join(
            [
                "# Wave Activation Report",
                "",
                f"- launch_wave: {launch_wave}",
                f"- activation_state: {state_snapshot.get('activation_state')}",
                f"- signoff_status: {state_snapshot.get('signoff_status')}",
                f"- preflight_status: {state_snapshot.get('preflight_status')} / {state_snapshot.get('go_no_go')}",
                f"- ready_account_count: {state_snapshot.get('ready_account_count')}",
                f"- critical_alert_count: {state_snapshot.get('critical_alert_count')}",
                f"- blockers: {state_snapshot.get('blockers')}",
            ]
        )
        (bundle_dir / "summary.json").write_text(json.dumps(state_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        (bundle_dir / "activation_report.md").write_text(report + "\n", encoding="utf-8")
        latest_dir = self._artifacts_root() / "wave_activation" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "bundle_dir": str(bundle_dir),
            "latest_dir": str(latest_dir),
            "summary_json": str(bundle_dir / "summary.json"),
            "activation_report_md": str(bundle_dir / "activation_report.md"),
        }

    def _latest_activation_artifact_refs(self) -> Dict[str, Any]:
        latest_dir = self._artifacts_root() / "wave_activation" / "latest"
        if not latest_dir.exists():
            return {}
        return {
            "bundle_dir": str(latest_dir),
            "latest_dir": str(latest_dir),
            "summary_json": str(latest_dir / "summary.json"),
            "activation_report_md": str(latest_dir / "activation_report.md"),
        }

    def _activate(
        self,
        *,
        actor_id: str,
        actor_role: str,
        launch_wave: str,
        state_snapshot: Dict[str, Any],
        signoff_id: Optional[str],
    ) -> Dict[str, Any]:
        for account in self._launch_accounts(launch_wave):
            self.production_acceptance.generate_acceptance_record(
                actor_id=actor_id,
                actor_role=actor_role,
                account_id=str(account.get("account_id")),
                launch_wave=launch_wave,
                signoff_id=signoff_id,
            )
        wave_status = self.production_acceptance.update_launch_wave_status(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_wave=launch_wave,
            status="active",
            note="wave_activation_controller_activated",
        )["launch_wave_status"]
        activation_snapshot = {
            **state_snapshot,
            "activation_state": "active",
            "current_wave_status": wave_status,
            "activated_at": self._utcnow(),
        }
        artifact_refs = self._write_activation_bundle(launch_wave=launch_wave, state_snapshot=activation_snapshot)
        event = self.repository.save_production_launch_event(
            {
                "launch_wave": launch_wave,
                "account_id": None,
                "event_category": "activation",
                "event_type": "wave_activated",
                "phase": "launch_day",
                "severity": "info",
                "related_object_type": "launch_wave_status",
                "related_object_id": wave_status["launch_wave_status_id"],
                "event_payload": {
                    "signoff_id": signoff_id,
                    "artifact_refs": artifact_refs,
                },
            }
        )
        self.commercial_audit.record_audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=None,
            object_type="wave_activation",
            object_id=wave_status["launch_wave_status_id"],
            action_type="wave_activated",
            source_surface="ops",
            customer_visible_payload={},
            internal_payload={"activation_snapshot": activation_snapshot, "artifact_refs": artifact_refs, "launch_event": event},
        )
        return {
            **activation_snapshot,
            "artifact_refs": artifact_refs,
            "launch_event": event,
        }

    def arm(self, *, actor_id: str, actor_role: str, launch_wave: str = "wave_1") -> Dict[str, Any]:
        current = self._current_wave_status(launch_wave)
        wave_status = self.production_acceptance.update_launch_wave_status(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_wave=launch_wave,
            status="armed",
            note="wave_activation_controller_armed",
        )["launch_wave_status"]
        self.repository.save_production_launch_event(
            {
                "launch_wave": launch_wave,
                "account_id": None,
                "event_category": "activation",
                "event_type": "wave_armed",
                "phase": "go_no_go",
                "severity": "info",
                "related_object_type": "launch_wave_status",
                "related_object_id": wave_status["launch_wave_status_id"],
                "event_payload": {"previous_status": (current or {}).get("status")},
            }
        )
        evaluated = self.evaluate(launch_wave=launch_wave, actor_id=actor_id, actor_role=actor_role)
        return {
            "launch_wave_status": wave_status,
            "evaluation": evaluated,
        }

    def mark_rollback_watch(self, *, actor_id: str, actor_role: str, launch_wave: str = "wave_1", note: Optional[str] = None) -> Dict[str, Any]:
        wave_status = self.production_acceptance.update_launch_wave_status(
            actor_id=actor_id,
            actor_role=actor_role,
            launch_wave=launch_wave,
            status="rollback_watch",
            note=note or "wave_activation_controller_rollback_watch",
        )["launch_wave_status"]
        event = self.repository.save_production_launch_event(
            {
                "launch_wave": launch_wave,
                "account_id": None,
                "event_category": "activation",
                "event_type": "rollback_watch",
                "phase": "launch_day",
                "severity": "warning",
                "related_object_type": "launch_wave_status",
                "related_object_id": wave_status["launch_wave_status_id"],
                "event_payload": {"note": note},
            }
        )
        return {"launch_wave_status": wave_status, "launch_event": event}

    def summary(self, *, launch_wave: Optional[str] = None) -> Dict[str, Any]:
        waves = self.repository.list_launch_wave_statuses(launch_wave=launch_wave, limit=100)
        items = []
        for row in waves:
            items.append(self.evaluate(launch_wave=str(row.get("launch_wave") or "")))
        current = items[0] if items else (self.evaluate(launch_wave=launch_wave) if launch_wave else None)
        return {
            "waves": items,
            "current_wave": current,
            "summary": {
                "wave_count": len(items),
                "active_count": len([item for item in items if item.get("activation_state") == "active"]),
                "armed_count": len([item for item in items if item.get("activation_state") == "armed"]),
                "activation_ready_count": len([item for item in items if item.get("activation_state") == "activation_ready"]),
                "blocked_count": len([item for item in items if item.get("activation_state") == "blocked"]),
            },
        }
