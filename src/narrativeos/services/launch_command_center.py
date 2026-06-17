from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .production_acceptance import ProductionAcceptanceService
from .production_preflight import ProductionPreflightService
from .production_signoff_board import ProductionSignoffBoardService
from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .ops_commercialization_dashboard import OpsCommercializationDashboardService


ALERT_KEYS_BY_PANEL = {
    "billing_anomaly_panel": {"payment_failures", "invoice_issuance_failures"},
    "checkout_failure_panel": {"checkout_failures"},
    "reader_generation_panel": {"remote_generation_failures"},
    "quality_block_panel": {"quality_blocks"},
    "vercel_runtime_panel": {"vercel_cold_start_latency"},
    "support_urgency_panel": {"support_backlog"},
    "dispute_anomaly_panel": {"dispute_spikes"},
    "dunning_anomaly_panel": {"dunning_spikes"},
    "webhook_anomaly_panel": {"webhook_failures"},
}


class LaunchCommandCenterService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        commercialization_dashboard_service: OpsCommercializationDashboardService,
        production_acceptance_service: ProductionAcceptanceService,
        production_signoff_board_service: ProductionSignoffBoardService,
        production_preflight_service: ProductionPreflightService,
    ) -> None:
        self.repository = repository
        self.commercialization = commercialization_dashboard_service
        self.production_acceptance = production_acceptance_service
        self.signoff_board = production_signoff_board_service
        self.preflight = production_preflight_service

    def _latest_preflight_by_wave(self) -> Dict[str, Dict[str, Any]]:
        runs = self.repository.list_production_preflight_runs(limit=200)
        latest: Dict[str, Dict[str, Any]] = {}
        for row in runs:
            wave = str(row.get("launch_wave") or "")
            if not wave:
                continue
            if wave not in latest or str(row.get("updated_at") or "") > str(latest[wave].get("updated_at") or ""):
                latest[wave] = row
        return latest

    def command_center(self, *, launch_wave: Optional[str] = None) -> Dict[str, Any]:
        acceptance = self.production_acceptance.list_acceptance_records(launch_wave=launch_wave, limit=100)
        launch_week_alert_pack = self.commercialization.launch_week_alert_pack(limit=100)
        signoff_board = self.signoff_board.board()
        latest_preflight_by_wave = self._latest_preflight_by_wave()
        ready_accounts = list(acceptance.get("go_live_ready_accounts") or [])
        alerts = list((launch_week_alert_pack or {}).get("alerts") or [])
        watchlist = []
        for item in ready_accounts:
            wave = str(item.get("launch_wave") or "")
            account_id = str(item.get("account_id") or "")
            preflight = latest_preflight_by_wave.get(wave)
            account_alerts = [row for row in alerts if account_id and account_id in set(row.get("account_ids") or [])]
            support_count = len(self.repository.list_support_cases(account_id=account_id, limit=100)) if account_id else 0
            dispute_count = len(self.repository.list_disputes(account_id=account_id, limit=100)) if account_id else 0
            watchlist.append(
                {
                    "account_id": account_id,
                    "launch_wave": wave,
                    "go_live_status": item.get("status"),
                    "latest_preflight_status": (preflight or {}).get("status"),
                    "latest_go_no_go": (preflight or {}).get("go_no_go"),
                    "signoff_status": (signoff_board.get("current_signoff") or {}).get("status"),
                    "alert_count": len(account_alerts),
                    "support_count": support_count,
                    "dispute_count": dispute_count,
                }
            )
        panels = {}
        for panel_key, keys in ALERT_KEYS_BY_PANEL.items():
            filtered = [row for row in alerts if str(row.get("alert_key") or "") in keys]
            panels[panel_key] = {
                "count": len(filtered),
                "alerts": filtered,
                "severity_counts": dict(Counter(str(item.get("severity") or "unknown") for item in filtered)),
            }
        revenue_protection_alerts = [
            row
            for row in alerts
            if str(row.get("alert_key") or "") in {"payment_failures", "checkout_failures", "invoice_issuance_failures", "renewal_due_no_action", "overage_without_upgrade_follow_up"}
        ]
        expansion_guard_alerts = [
            row
            for row in alerts
            if str(row.get("alert_key") or "") in {"remote_generation_failures", "checkout_failures", "quality_blocks", "vercel_cold_start_latency", "support_backlog"}
        ]
        return {
            "launch_customer_watchlist": watchlist,
            **panels,
            "launch_wave_status_board": acceptance.get("launch_waves") or [],
            "revenue_protection_alerts": revenue_protection_alerts,
            "launch_week_expansion_guard_alerts": expansion_guard_alerts,
            "summary": {
                "watchlist_count": len(watchlist),
                "launch_wave_count": len(acceptance.get("launch_waves") or []),
                "revenue_protection_alert_count": len(revenue_protection_alerts),
                "launch_week_expansion_guard_alert_count": len(expansion_guard_alerts),
                "ready_to_expand": len([item for item in expansion_guard_alerts if str(item.get("severity") or "") in {"critical", "high"}]) == 0,
                "latest_preflight_by_wave": {key: {"status": value.get("status"), "go_no_go": value.get("go_no_go")} for key, value in latest_preflight_by_wave.items()},
            },
        }
