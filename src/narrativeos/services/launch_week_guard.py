from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .customer_success_reporting import CustomerSuccessReportingService
from .launch_command_center import LaunchCommandCenterService
from .production_launch_ledger import ProductionLaunchLedgerService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]


class LaunchWeekGuardService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_success_reporting_service: CustomerSuccessReportingService,
        launch_command_center_service: LaunchCommandCenterService,
        production_launch_ledger_service: ProductionLaunchLedgerService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.customer_success = customer_success_reporting_service
        self.launch_command_center = launch_command_center_service
        self.launch_ledger = production_launch_ledger_service
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

    def _high_support_urgency(self, *, account_id: str) -> int:
        cases = self.repository.list_support_cases(account_id=account_id, limit=100)
        return len([item for item in cases if str(item.get("status") or "") in {"open", "in_progress"} and str(item.get("priority") or "") == "high"])

    def _open_disputes(self, *, account_id: str) -> int:
        disputes = self.repository.list_disputes(account_id=account_id, limit=100)
        return len([item for item in disputes if str(item.get("status") or "") in {"open", "under_review", "approved"}])

    def sync(self, *, actor_id: str, actor_role: str, launch_wave: str = "wave_1") -> Dict[str, Any]:
        success_listing = self.customer_success.list_customer_success(launch_wave=launch_wave, limit=50)
        account = next(iter(success_listing.get("accounts") or []), None)
        account_id = (account or {}).get("account_id")
        center = self.launch_command_center.command_center(launch_wave=launch_wave)
        critical_alerts = [
            item
            for panel_key in (
                "billing_anomaly_panel",
                "checkout_failure_panel",
                "reader_generation_panel",
                "quality_block_panel",
                "vercel_runtime_panel",
                "support_urgency_panel",
                "dispute_anomaly_panel",
                "dunning_anomaly_panel",
                "webhook_anomaly_panel",
            )
            for item in list((center.get(panel_key) or {}).get("alerts") or [])
            if str(item.get("severity") or "") == "critical"
        ]
        latest_score = (account or {}).get("pilot_to_paid_readiness_score") or {}
        open_disputes = self._open_disputes(account_id=account_id) if account_id else 0
        high_support = self._high_support_urgency(account_id=account_id) if account_id else 0
        summaries = {
            "day1": {
                "launch_wave": launch_wave,
                "critical_alert_count": len(critical_alerts),
                "watchlist_count": center.get("summary", {}).get("watchlist_count", 0),
            },
            "day3": {
                "launch_wave": launch_wave,
                "customer_success_band": latest_score.get("band"),
                "launch_event_count": self.launch_ledger.list_events(launch_wave=launch_wave).get("summary", {}).get("event_count", 0),
            },
            "day7": {
                "launch_wave": launch_wave,
                "open_disputes": open_disputes,
                "high_support_urgency": high_support,
                "critical_alert_count": len(critical_alerts),
            },
        }
        criteria = {
            "day_summaries_exist": all(bool(value) for value in summaries.values()),
            "no_unresolved_critical_alert": len(critical_alerts) == 0,
            "latest_customer_success_band_ready": str(latest_score.get("band") or "") == "ready",
            "no_open_dispute_backlog": open_disputes == 0,
            "no_open_support_urgency_high": high_support == 0,
            "launch_week_expansion_guard_clear": int(center.get("summary", {}).get("launch_week_expansion_guard_alert_count") or 0) == 0,
        }
        replication_readiness = "ready" if all(criteria.values()) else "not_ready"
        run = self.repository.save_launch_week_guard_run(
            {
                "launch_wave": launch_wave,
                "account_id": account_id,
                "status": "ready" if replication_readiness == "ready" else "not_ready",
                "replication_readiness": replication_readiness,
                "summary": {
                    "criteria": criteria,
                    "day_summaries": summaries,
                    "critical_alert_count": len(critical_alerts),
                },
            }
        )
        pack = self.repository.save_first_customer_success_pack(
            {
                "launch_wave": launch_wave,
                "account_id": account_id,
                "status": replication_readiness,
                "pack_payload": {
                    "run_id": run["launch_week_guard_run_id"],
                    "criteria": criteria,
                    "day_summaries": summaries,
                },
            }
        )
        artifact_refs = self._build_pack(run=run, pack=pack, account_id=account_id, summaries=summaries, criteria=criteria)
        pack = self.repository.save_first_customer_success_pack(
            {
                **pack,
                "pack_payload_json": {
                    **dict(pack.get("pack_payload_json") or {}),
                    "artifact_refs": artifact_refs,
                },
            }
        )
        return {
            "launch_week_guard_run": run,
            "first_customer_success_pack": pack,
            "artifact_refs": artifact_refs,
        }

    def _build_pack(
        self,
        *,
        run: Dict[str, Any],
        pack: Dict[str, Any],
        account_id: Optional[str],
        summaries: Dict[str, Dict[str, Any]],
        criteria: Dict[str, bool],
    ) -> Dict[str, Any]:
        run_id = f"first_customer_success_pack_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = self._artifacts_root() / "first_customer_success_pack" / run_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        for key, payload in summaries.items():
            self._write_text(
                bundle_dir / f"{key}_summary.md",
                "\n".join([f"# {key.upper()} Summary", "", json.dumps(payload, ensure_ascii=False, indent=2)]),
            )
        success_lines = [
            "# First Customer Success Pack",
            "",
            f"- launch_wave: {run['launch_wave']}",
            f"- account_id: {account_id or '-'}",
            f"- replication_readiness: {run['replication_readiness']}",
            f"- criteria: {criteria}",
        ]
        self._write_text(bundle_dir / "first_customer_success_pack.md", "\n".join(success_lines))
        self._write_text(
            bundle_dir / "wave_stabilization_checklist.md",
            "\n".join(
                [
                    "# Wave Stabilization Checklist",
                    "",
                    f"- no unresolved critical alert: {criteria['no_unresolved_critical_alert']}",
                    f"- latest customer success band ready: {criteria['latest_customer_success_band_ready']}",
                    f"- no open dispute backlog: {criteria['no_open_dispute_backlog']}",
                    f"- no high support urgency: {criteria['no_open_support_urgency_high']}",
                ]
            ),
        )
        self._write_text(
            bundle_dir / "replication_readiness_assessment.md",
            "\n".join(
                [
                    "# Replication Readiness Assessment",
                    "",
                    f"- verdict: {run['replication_readiness']}",
                    f"- criteria: {criteria}",
                ]
            ),
        )
        self._write_json(bundle_dir / "summary.json", {"run": run, "pack": pack, "criteria": criteria, "summaries": summaries})
        latest_dir = self._artifacts_root() / "first_customer_success_pack" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "artifact_dir": str(bundle_dir),
            "summary_json": str(bundle_dir / "summary.json"),
            "day1_summary_md": str(bundle_dir / "day1_summary.md"),
            "day3_summary_md": str(bundle_dir / "day3_summary.md"),
            "day7_summary_md": str(bundle_dir / "day7_summary.md"),
            "first_customer_success_pack_md": str(bundle_dir / "first_customer_success_pack.md"),
            "wave_stabilization_checklist_md": str(bundle_dir / "wave_stabilization_checklist.md"),
            "replication_readiness_assessment_md": str(bundle_dir / "replication_readiness_assessment.md"),
        }

    def list_runs(self, *, launch_wave: Optional[str] = None) -> Dict[str, Any]:
        runs = self.repository.list_launch_week_guard_runs(launch_wave=launch_wave, limit=50)
        current = runs[0] if runs else None
        return {
            "runs": runs,
            "current_run": current,
            "summary": {
                "run_count": len(runs),
                "latest_run_id": (current or {}).get("launch_week_guard_run_id"),
                "ready_count": len([item for item in runs if str(item.get("replication_readiness") or "") == "ready"]),
            },
        }

    def detail(self, *, launch_wave: str) -> Dict[str, Any]:
        run = next(iter(self.repository.list_launch_week_guard_runs(launch_wave=launch_wave, limit=1)), None)
        pack = next(iter(self.repository.list_first_customer_success_packs(launch_wave=launch_wave, limit=1)), None)
        return {
            "launch_week_guard_run": run,
            "first_customer_success_pack": pack,
            "artifact_refs": dict((pack or {}).get("pack_payload_json") or {}).get("artifact_refs", {}),
        }
