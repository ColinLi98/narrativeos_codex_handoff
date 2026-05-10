from __future__ import annotations

from collections import Counter
import os
from typing import Any, Dict, List, Optional

from .commercial_support import CommercialSupportService
from .commercial_lifecycle_automation import CommercialLifecycleAutomationService
from .customer_accounts import CustomerAccountService
from .customer_success_reporting import CustomerSuccessReportingService
from .go_live_day_runner import GoLiveDayRunnerService
from .human_signoff_closure import HumanSignoffClosureService
from .launch_command_center import LaunchCommandCenterService
from .launch_week_guard import LaunchWeekGuardService
from .launch_week_monitoring import DEFAULT_PUBLIC_APP_URL, LaunchWeekMonitoringService
from .partner_readiness import PartnerReadinessService
from .production_acceptance import ProductionAcceptanceService
from .production_preflight import ProductionPreflightService
from .production_handshake_pack import ProductionHandshakePackService
from .production_launch_week_pack import ProductionLaunchWeekPackService
from .production_launch_ledger import ProductionLaunchLedgerService
from .production_signoff_board import ProductionSignoffBoardService
from .production_signoff import ProductionSignoffService
from .wave_activation_controller import WaveActivationControllerService
from ..persistence.repositories import SQLAlchemyPlatformRepository


class OpsCommercializationDashboardService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_account_service: CustomerAccountService,
        commercial_support_service: CommercialSupportService,
        partner_readiness_service: PartnerReadinessService,
        commercial_lifecycle_automation_service: CommercialLifecycleAutomationService,
        production_signoff_service: Optional[ProductionSignoffService] = None,
        production_signoff_board_service: Optional[ProductionSignoffBoardService] = None,
        production_preflight_service: Optional[ProductionPreflightService] = None,
        production_acceptance_service: Optional[ProductionAcceptanceService] = None,
        launch_command_center_service: Optional[LaunchCommandCenterService] = None,
        customer_success_reporting_service: Optional[CustomerSuccessReportingService] = None,
        production_launch_ledger_service: Optional[ProductionLaunchLedgerService] = None,
        human_signoff_closure_service: Optional[HumanSignoffClosureService] = None,
        wave_activation_controller_service: Optional[WaveActivationControllerService] = None,
        go_live_day_runner_service: Optional[GoLiveDayRunnerService] = None,
        launch_week_guard_service: Optional[LaunchWeekGuardService] = None,
        launch_week_monitoring_service: Optional[LaunchWeekMonitoringService] = None,
        production_launch_week_pack_service: Optional[ProductionLaunchWeekPackService] = None,
        production_handshake_pack_service: Optional[ProductionHandshakePackService] = None,
    ) -> None:
        self.repository = repository
        self.customer_accounts = customer_account_service
        self.commercial_support = commercial_support_service
        self.partner_readiness = partner_readiness_service
        self.commercial_lifecycle = commercial_lifecycle_automation_service
        self.production_signoff = production_signoff_service
        self.production_signoff_board = production_signoff_board_service
        self.production_preflight = production_preflight_service
        self.production_acceptance = production_acceptance_service
        self.launch_command_center = launch_command_center_service
        self.customer_success = customer_success_reporting_service
        self.launch_ledger = production_launch_ledger_service
        self.human_signoff_closure = human_signoff_closure_service
        self.wave_activation = wave_activation_controller_service
        self.go_live_day_runner = go_live_day_runner_service
        self.launch_week_guard = launch_week_guard_service
        self.launch_week_monitoring = launch_week_monitoring_service
        self.launch_week_pack = production_launch_week_pack_service
        self.handshake_pack = production_handshake_pack_service

    def _utcnow(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    def _threshold(self, env_key: str, default: int) -> int:
        try:
            return max(1, int(os.getenv(env_key, str(default))))
        except ValueError:
            return default

    def _launch_week_alert(
        self,
        *,
        alert_key: str,
        severity: str,
        owner_role: str,
        summary: str,
        count: int,
        account_ids: Optional[List[str]] = None,
        invoice_ids: Optional[List[str]] = None,
        payment_transaction_ids: Optional[List[str]] = None,
        webhook_event_ids: Optional[List[str]] = None,
        support_case_ids: Optional[List[str]] = None,
        dispute_ids: Optional[List[str]] = None,
        recommended_actions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "alert_key": alert_key,
            "severity": severity,
            "owner_role": owner_role,
            "count": count,
            "summary": summary,
            "account_ids": list(account_ids or []),
            "invoice_ids": list(invoice_ids or []),
            "payment_transaction_ids": list(payment_transaction_ids or []),
            "webhook_event_ids": list(webhook_event_ids or []),
            "support_case_ids": list(support_case_ids or []),
            "dispute_ids": list(dispute_ids or []),
            "recommended_actions": list(recommended_actions or []),
            "drilldown_refs": [
                item
                for item in [
                    *[
                        {"kind": "account", "id": value, "label": value}
                        for value in list(account_ids or [])[:5]
                    ],
                    *[
                        {"kind": "invoice", "id": value, "label": value}
                        for value in list(invoice_ids or [])[:5]
                    ],
                    *[
                        {"kind": "payment_transaction", "id": value, "label": value}
                        for value in list(payment_transaction_ids or [])[:5]
                    ],
                    *[
                        {"kind": "provider_webhook_event", "id": value, "label": value}
                        for value in list(webhook_event_ids or [])[:5]
                    ],
                    *[
                        {"kind": "support_case", "id": value, "label": value}
                        for value in list(support_case_ids or [])[:5]
                    ],
                    *[
                        {"kind": "dispute", "id": value, "label": value}
                        for value in list(dispute_ids or [])[:5]
                    ],
                ]
                if item.get("id")
            ],
        }

    def _launch_week_alert_pack(
        self,
        *,
        invoice_issuances: List[Dict[str, Any]],
        payment_transactions: List[Dict[str, Any]],
        provider_webhook_events: List[Dict[str, Any]],
        dunning_runs: List[Dict[str, Any]],
        disputes: List[Dict[str, Any]],
        support_cases: List[Dict[str, Any]],
        customers: List[Dict[str, Any]],
        active_overage_flags: List[Dict[str, Any]],
        recommended_expansions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        alerts: List[Dict[str, Any]] = []
        payment_failures = [item for item in payment_transactions if str(item.get("status") or "") == "failed"]
        webhook_failures = [item for item in provider_webhook_events if str(item.get("status") or "") != "processed"]
        invoice_failures = [
            item
            for item in invoice_issuances
            if str(item.get("status") or "") in {"failed", "void"}
            or (str(item.get("status") or "") in {"draft", "issued"} and (not item.get("hosted_invoice_url") or not item.get("invoice_pdf_url")))
        ]
        open_dunning_runs = [item for item in dunning_runs if str(item.get("status") or "") == "open"]
        dispute_backlog = [item for item in disputes if str(item.get("status") or "") in {"open", "under_review", "approved"}]
        support_backlog = [item for item in support_cases if str(item.get("status") or "") in {"open", "in_progress"}]
        recommended_expansion_accounts = {str(item.get("account_id") or "") for item in recommended_expansions if str(item.get("account_id") or "")}
        open_dunning_accounts = {str(item.get("account_id") or "") for item in open_dunning_runs if str(item.get("account_id") or "")}
        renewal_due_no_action = [
            item
            for item in customers
            if str(item.get("status") or "") == "renewal_due"
            and str(item.get("account_id") or "") not in open_dunning_accounts
            and str(item.get("account_id") or "") not in recommended_expansion_accounts
        ]
        overage_without_upgrade = [
            item for item in recommended_expansions if str(item.get("status") or "") == "recommended"
        ]

        if len(payment_failures) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_PAYMENT_FAILURE_THRESHOLD", 1):
            alerts.append(
                self._launch_week_alert(
                    alert_key="payment_failures",
                    severity="high",
                    owner_role="stripe_owner",
                    summary=f"发现 {len(payment_failures)} 笔支付失败，需确认客户重试与催缴路径。",
                    count=len(payment_failures),
                    account_ids=[str(item.get("account_id") or "") for item in payment_failures if item.get("account_id")],
                    invoice_ids=[str(item.get("invoice_id") or "") for item in payment_failures if item.get("invoice_id")],
                    payment_transaction_ids=[str(item.get("payment_transaction_id") or "") for item in payment_failures if item.get("payment_transaction_id")],
                    recommended_actions=["review_customer_invoice", "follow_up_dunning", "verify_payment_retry"],
                )
            )
        if len(webhook_failures) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_WEBHOOK_FAILURE_THRESHOLD", 1):
            alerts.append(
                self._launch_week_alert(
                    alert_key="webhook_failures",
                    severity="critical",
                    owner_role="infra_owner",
                    summary=f"发现 {len(webhook_failures)} 条 provider webhook 未完成处理。",
                    count=len(webhook_failures),
                    account_ids=[str(item.get("account_id") or "") for item in webhook_failures if item.get("account_id")],
                    invoice_ids=[str(item.get("invoice_id") or "") for item in webhook_failures if item.get("invoice_id")],
                    webhook_event_ids=[str(item.get("provider_webhook_event_id") or "") for item in webhook_failures if item.get("provider_webhook_event_id")],
                    recommended_actions=["replay_provider_webhook", "inspect_webhook_processing", "confirm_webhook_endpoint"],
                )
            )
        if len(invoice_failures) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_INVOICE_FAILURE_THRESHOLD", 1):
            alerts.append(
                self._launch_week_alert(
                    alert_key="invoice_issuance_failures",
                    severity="high",
                    owner_role="stripe_owner",
                    summary=f"发现 {len(invoice_failures)} 条 invoice issuance 异常或缺失 hosted/pdf link。",
                    count=len(invoice_failures),
                    account_ids=[str(item.get("account_id") or "") for item in invoice_failures if item.get("account_id")],
                    invoice_ids=[str(item.get("invoice_id") or "") for item in invoice_failures if item.get("invoice_id")],
                    recommended_actions=["inspect_invoice_issuance", "compare_invoice_preview", "verify_hosted_invoice_links"],
                )
            )
        if len(open_dunning_runs) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_DUNNING_SPIKE_THRESHOLD", 2):
            alerts.append(
                self._launch_week_alert(
                    alert_key="dunning_spikes",
                    severity="medium",
                    owner_role="support_finance_owner",
                    summary=f"当前有 {len(open_dunning_runs)} 条 open dunning run，需确认 follow-up 节奏。",
                    count=len(open_dunning_runs),
                    account_ids=[str(item.get("account_id") or "") for item in open_dunning_runs if item.get("account_id")],
                    invoice_ids=[str(item.get("invoice_id") or "") for item in open_dunning_runs if item.get("invoice_id")],
                    recommended_actions=["review_dunning_queue", "follow_up_customer", "verify_retry_schedule"],
                )
            )
        if len(dispute_backlog) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_DISPUTE_SPIKE_THRESHOLD", 2):
            alerts.append(
                self._launch_week_alert(
                    alert_key="dispute_spikes",
                    severity="medium",
                    owner_role="support_finance_owner",
                    summary=f"当前有 {len(dispute_backlog)} 条未结 disputes。",
                    count=len(dispute_backlog),
                    account_ids=[str(item.get("account_id") or "") for item in dispute_backlog if item.get("account_id")],
                    dispute_ids=[str(item.get("dispute_id") or "") for item in dispute_backlog if item.get("dispute_id")],
                    recommended_actions=["review_disputes", "coordinate_finance", "inspect_customer_history"],
                )
            )
        if len(support_backlog) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_SUPPORT_BACKLOG_THRESHOLD", 2):
            alerts.append(
                self._launch_week_alert(
                    alert_key="support_backlog",
                    severity="medium",
                    owner_role="support_finance_owner",
                    summary=f"当前有 {len(support_backlog)} 条 open/in_progress support cases。",
                    count=len(support_backlog),
                    account_ids=[str(item.get("account_id") or "") for item in support_backlog if item.get("account_id")],
                    support_case_ids=[str(item.get("support_case_id") or "") for item in support_backlog if item.get("support_case_id")],
                    recommended_actions=["review_support_cases", "assign_case_owner", "inspect_account_workspace"],
                )
            )
        if len(renewal_due_no_action) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_RENEWAL_NO_ACTION_THRESHOLD", 1):
            alerts.append(
                self._launch_week_alert(
                    alert_key="renewal_due_no_action",
                    severity="high",
                    owner_role="stripe_owner",
                    summary=f"发现 {len(renewal_due_no_action)} 个 renewal_due 账户尚未挂上 dunning 或升级动作。",
                    count=len(renewal_due_no_action),
                    account_ids=[str(item.get("account_id") or "") for item in renewal_due_no_action if item.get("account_id")],
                    recommended_actions=["inspect_customer_workspace", "create_cutover_followup", "assign_owner"],
                )
            )
        if len(overage_without_upgrade) >= self._threshold("NARRATIVEOS_LAUNCH_ALERT_OVERAGE_NO_UPGRADE_THRESHOLD", 1):
            alerts.append(
                self._launch_week_alert(
                    alert_key="overage_without_upgrade_follow_up",
                    severity="medium",
                    owner_role="support_finance_owner",
                    summary=f"发现 {len(overage_without_upgrade)} 个账户存在 overage 且仍停留在 recommended upgrade。",
                    count=len(overage_without_upgrade),
                    account_ids=[str(item.get("account_id") or "") for item in overage_without_upgrade if item.get("account_id")],
                    recommended_actions=["review_upgrade_followup", "contact_customer", "confirm_plan_change"],
                )
            )

        alerts.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item["severity"], 4), -int(item.get("count") or 0), item["alert_key"]))
        return {
            "generated_at": self._utcnow().isoformat(),
            "summary": {
                "alert_count": len(alerts),
                "by_alert_key": dict(Counter(item["alert_key"] for item in alerts)),
                "by_severity": dict(Counter(item["severity"] for item in alerts)),
                "by_owner_role": dict(Counter(item["owner_role"] for item in alerts)),
            },
            "alerts": alerts[:20],
        }

    def _merge_launch_week_monitoring_alerts(self, alert_pack: Dict[str, Any]) -> Dict[str, Any]:
        if self.launch_week_monitoring is None:
            return alert_pack
        monitoring_pack = self.launch_week_monitoring.current_alert_pack(
            public_app_url=os.getenv("PUBLIC_APP_URL", DEFAULT_PUBLIC_APP_URL),
            performance_summary_path=os.getenv("NARRATIVEOS_VERCEL_PERFORMANCE_SUMMARY"),
        )
        alerts = list(alert_pack.get("alerts") or []) + list(monitoring_pack.get("alerts") or [])
        alerts.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(item.get("severity") or ""), 4), -int(item.get("count") or 0), str(item.get("alert_key") or "")))
        return {
            **alert_pack,
            "summary": {
                **dict(alert_pack.get("summary") or {}),
                "alert_count": len(alerts),
                "by_alert_key": dict(Counter(str(item.get("alert_key") or "unknown") for item in alerts)),
                "by_severity": dict(Counter(str(item.get("severity") or "unknown") for item in alerts)),
                "by_owner_role": dict(Counter(str(item.get("owner_role") or "unknown") for item in alerts)),
                "launch_week_monitoring_ready_to_expand": bool((monitoring_pack.get("summary") or {}).get("ready_to_expand", True)),
                "launch_week_monitoring": dict(monitoring_pack.get("monitoring_summary") or {}),
            },
            "alerts": alerts[:20],
        }

    def launch_week_alert_pack(self, *, limit: int = 50) -> Dict[str, Any]:
        customers = self.repository.list_customer_accounts(limit=500)
        support_cases = self.repository.list_support_cases(limit=500)
        disputes = self.repository.list_disputes(limit=500)
        overage_flags = self.repository.list_overage_flags(limit=500)
        invoice_issuances = self.repository.list_invoice_issuances(limit=500)
        payment_transactions = self.repository.list_payment_transactions(limit=1000)
        provider_webhook_events = self.repository.list_provider_webhook_events(limit=500)
        for item in customers[:]:
            self.commercial_lifecycle.sync_account(account_id=item["account_id"])
        dunning_runs = self.repository.list_dunning_runs(limit=500)
        expansion_candidates = self.repository.list_expansion_candidates(limit=500)
        active_overage_flags = [item for item in overage_flags if str(item.get("status") or "") == "active"]
        recommended_expansions = [item for item in expansion_candidates if str(item.get("status") or "") == "recommended"]
        return self._merge_launch_week_monitoring_alerts(self._launch_week_alert_pack(
            invoice_issuances=invoice_issuances,
            payment_transactions=payment_transactions,
            provider_webhook_events=provider_webhook_events,
            dunning_runs=dunning_runs,
            disputes=disputes,
            support_cases=support_cases,
            customers=customers,
            active_overage_flags=active_overage_flags,
            recommended_expansions=recommended_expansions,
        ))

    def summary(self, *, limit: int = 50) -> Dict[str, Any]:
        customers = self.repository.list_customer_accounts(limit=500)
        invoice_previews = self.repository.list_invoice_previews(limit=500)
        billable_events = self.repository.list_billable_events(limit=1000)
        overage_flags = self.repository.list_overage_flags(limit=500)
        disputes = self.repository.list_disputes(limit=500)
        support_cases = self.repository.list_support_cases(limit=500)
        partners = self.partner_readiness.list_partners(limit=200)
        invoice_issuances = self.repository.list_invoice_issuances(limit=500)
        payment_transactions = self.repository.list_payment_transactions(limit=1000)
        provider_webhook_events = self.repository.list_provider_webhook_events(limit=500)

        pilot_accounts = [item for item in customers if str(item.get("status") or "") == "trial"]
        paid_accounts = [item for item in customers if str(item.get("status") or "") in {"active", "paused", "renewal_due"}]
        renewal_due_accounts = [item for item in customers if str(item.get("status") or "") == "renewal_due"]
        churn_risk_accounts = [
            item
            for item in customers
            if str(item.get("status") or "") in {"paused", "renewal_due"}
            or any(dispute.get("account_id") == item.get("account_id") and str(dispute.get("status") or "") in {"open", "approved"} for dispute in disputes)
        ]
        unpaid_invoice_previews = [item for item in invoice_previews if float(item.get("total_due_usd") or 0.0) > 0.0]
        disputed_events = [item for item in billable_events if str(item.get("status") or "") == "disputed"]
        credited_events = [item for item in billable_events if str(item.get("status") or "") == "credited"]
        support_backlog = [item for item in support_cases if str(item.get("status") or "") in {"open", "in_progress"}]
        dispute_backlog = [item for item in disputes if str(item.get("status") or "") in {"open", "under_review", "approved"}]
        active_overage_flags = [item for item in overage_flags if str(item.get("status") or "") == "active"]
        for item in customers[:]:
            self.commercial_lifecycle.sync_account(account_id=item["account_id"])
        renewal_trackers = self.repository.list_renewal_trackers(limit=500)
        dunning_runs = self.repository.list_dunning_runs(limit=500)
        pilot_tracks = self.repository.list_pilot_conversion_tracks(limit=500)
        expansion_candidates = self.repository.list_expansion_candidates(limit=500)
        churn_flags = self.repository.list_churn_risk_flags(limit=500)
        open_dunning_runs = [item for item in dunning_runs if str(item.get("status") or "") == "open"]
        recommended_expansions = [item for item in expansion_candidates if str(item.get("status") or "") == "recommended"]
        watch_churn_flags = [item for item in churn_flags if str(item.get("status") or "") == "watch"]
        ready_pilot_tracks = [item for item in pilot_tracks if str(item.get("status") or "") == "ready_for_conversion"]

        launch_week_alert_pack = self._merge_launch_week_monitoring_alerts(self._launch_week_alert_pack(
            invoice_issuances=invoice_issuances,
            payment_transactions=payment_transactions,
            provider_webhook_events=provider_webhook_events,
            dunning_runs=dunning_runs,
            disputes=disputes,
            support_cases=support_cases,
            customers=customers,
            active_overage_flags=active_overage_flags,
            recommended_expansions=recommended_expansions,
        ))

        return {
            "pilot_vs_paid": {
                "pilot_account_count": len(pilot_accounts),
                "paid_account_count": len(paid_accounts),
                "pilot_account_ids": [item.get("account_id") for item in pilot_accounts[:limit]],
                "paid_account_ids": [item.get("account_id") for item in paid_accounts[:limit]],
            },
            "invoice_preview_totals": {
                "preview_count": len(invoice_previews),
                "subtotal_amount_usd": round(sum(float(item.get("subtotal_amount_usd") or 0.0) for item in invoice_previews), 6),
                "total_due_usd": round(sum(float(item.get("total_due_usd") or 0.0) for item in invoice_previews), 6),
                "invoice_preview_ids": [item.get("invoice_preview_id") for item in invoice_previews[:limit]],
            },
            "financial_status_totals": {
                "unpaid_count": len(unpaid_invoice_previews),
                "disputed_count": len(disputed_events),
                "credited_count": len(credited_events),
                "unpaid_invoice_preview_ids": [item.get("invoice_preview_id") for item in unpaid_invoice_previews[:limit]],
                "disputed_billable_event_ids": [item.get("billable_event_id") for item in disputed_events[:limit]],
                "credited_billable_event_ids": [item.get("billable_event_id") for item in credited_events[:limit]],
            },
            "overage_totals": {
                "active_flag_count": len(active_overage_flags),
                "by_metric": dict(Counter(str(item.get("metric_type") or "unknown") for item in active_overage_flags)),
                "overage_flag_ids": [item.get("overage_flag_id") for item in active_overage_flags[:limit]],
            },
            "renewal_due_accounts": {
                "count": len([item for item in renewal_trackers if str(item.get("status") or "") == "renewal_due"]),
                "account_ids": [item.get("account_id") for item in renewal_trackers if str(item.get("status") or "") == "renewal_due"][:limit],
            },
            "dunning_runs": {
                "count": len(open_dunning_runs),
                "account_ids": [item.get("account_id") for item in open_dunning_runs[:limit]],
                "invoice_ids": [item.get("invoice_id") for item in open_dunning_runs[:limit]],
                "step_counts": dict(Counter(str(item.get("current_step") or "unknown") for item in open_dunning_runs)),
            },
            "pilot_conversion": {
                "ready_count": len(ready_pilot_tracks),
                "converted_count": len([item for item in pilot_tracks if str(item.get("status") or "") == "converted"]),
                "watch_count": len([item for item in pilot_tracks if str(item.get("status") or "") == "watch"]),
                "account_ids": [item.get("account_id") for item in ready_pilot_tracks[:limit]],
            },
            "expansion_candidates": {
                "recommended_count": len(recommended_expansions),
                "account_ids": [item.get("account_id") for item in recommended_expansions[:limit]],
                "by_trigger": dict(Counter(str(item.get("trigger_type") or "unknown") for item in recommended_expansions)),
            },
            "churn_risk_accounts": {
                "count": len(watch_churn_flags),
                "account_ids": [item.get("account_id") for item in watch_churn_flags[:limit]],
                "risk_levels": dict(Counter(str(item.get("risk_level") or "unknown") for item in watch_churn_flags)),
            },
            "partner_readiness_heatmap": {
                "lifecycle_counts": dict((partners.get("summary") or {}).get("lifecycle_counts") or {}),
                "health_counts": dict((partners.get("summary") or {}).get("health_counts") or {}),
                "partner_ids": [item["partner"].get("partner_id") for item in (partners.get("partners") or [])[:limit]],
            },
            "support_backlog": {
                "count": len(support_backlog),
                "support_case_ids": [item.get("support_case_id") for item in support_backlog[:limit]],
            },
            "dispute_backlog": {
                "count": len(dispute_backlog),
                "dispute_ids": [item.get("dispute_id") for item in dispute_backlog[:limit]],
            },
            "lifecycle_automation": {
                "dunning_run_count": len(open_dunning_runs),
                "pilot_ready_count": len(ready_pilot_tracks),
                "expansion_candidate_count": len(recommended_expansions),
                "churn_watch_count": len(watch_churn_flags),
            },
            "production_signoff": self.production_signoff.current_signoff_summary() if self.production_signoff else None,
            "production_signoff_action_board": self.production_signoff_board.current_board_summary() if self.production_signoff_board else None,
            "production_acceptance": (
                self.production_acceptance.list_acceptance_records(limit=limit).get("summary")
                if self.production_acceptance
                else None
            ),
            "production_preflight_summary": self.production_preflight.list_runs(limit=limit).get("summary") if self.production_preflight else None,
            "launch_week_alert_pack": launch_week_alert_pack,
            "launch_week_ops_pack": self.launch_week_pack.current_pack_summary(
                signoff_summary=self.production_signoff.current_signoff_summary() if self.production_signoff else None,
                acceptance_summary=(
                    self.production_acceptance.list_acceptance_records(limit=limit).get("summary")
                    if self.production_acceptance
                    else None
                ),
                launch_week_alert_pack=launch_week_alert_pack,
            )
            if self.launch_week_pack
            else None,
            "launch_handshake_pack": self.handshake_pack.current_pack_summary(
                signoff_summary=self.production_signoff.current_signoff_summary() if self.production_signoff else None,
                acceptance_summary=(
                    self.production_acceptance.list_acceptance_records(limit=limit).get("summary")
                    if self.production_acceptance
                    else None
                ),
            )
            if self.handshake_pack
            else None,
            "launch_command_center_summary": self.launch_command_center.command_center().get("summary") if self.launch_command_center else None,
            "customer_success_summary": self.customer_success.list_customer_success(limit=limit).get("summary") if self.customer_success else None,
            "launch_ledger_summary": self.launch_ledger.list_events(limit=limit).get("summary") if self.launch_ledger else None,
            "human_signoff_closure_summary": self.human_signoff_closure.current_summary() if self.human_signoff_closure else None,
            "wave_activation_summary": self.wave_activation.summary().get("summary") if self.wave_activation else None,
            "go_live_day_summary": self.go_live_day_runner.summary().get("summary") if self.go_live_day_runner else None,
            "launch_week_guard_summary": self.launch_week_guard.list_runs().get("summary") if self.launch_week_guard else None,
        }
