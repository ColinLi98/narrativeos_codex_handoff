from __future__ import annotations

import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .production_acceptance import ProductionAcceptanceService
from .production_signoff import ProductionSignoffService

if TYPE_CHECKING:
    from .ops_commercialization_dashboard import OpsCommercializationDashboardService


ROOT = Path(__file__).resolve().parents[3]

ALERT_THRESHOLD_ENV_MAP = {
    "payment_failures": "NARRATIVEOS_LAUNCH_ALERT_PAYMENT_FAILURE_THRESHOLD",
    "checkout_failures": "NARRATIVEOS_LAUNCH_ALERT_CHECKOUT_FAILURE_THRESHOLD",
    "remote_generation_failures": "NARRATIVEOS_LAUNCH_ALERT_REMOTE_GENERATION_FAILURE_THRESHOLD",
    "quality_blocks": "NARRATIVEOS_LAUNCH_ALERT_QUALITY_BLOCK_THRESHOLD",
    "vercel_cold_start_latency": "NARRATIVEOS_LAUNCH_ALERT_COLD_START_P95_MS / NARRATIVEOS_LAUNCH_ALERT_COLD_START_5XX_THRESHOLD",
    "webhook_failures": "NARRATIVEOS_LAUNCH_ALERT_WEBHOOK_FAILURE_THRESHOLD",
    "invoice_issuance_failures": "NARRATIVEOS_LAUNCH_ALERT_INVOICE_FAILURE_THRESHOLD",
    "dunning_spikes": "NARRATIVEOS_LAUNCH_ALERT_DUNNING_SPIKE_THRESHOLD",
    "dispute_spikes": "NARRATIVEOS_LAUNCH_ALERT_DISPUTE_SPIKE_THRESHOLD",
    "support_backlog": "NARRATIVEOS_LAUNCH_ALERT_SUPPORT_BACKLOG_THRESHOLD",
    "renewal_due_no_action": "NARRATIVEOS_LAUNCH_ALERT_RENEWAL_NO_ACTION_THRESHOLD",
    "overage_without_upgrade_follow_up": "NARRATIVEOS_LAUNCH_ALERT_OVERAGE_NO_UPGRADE_THRESHOLD",
}

INCIDENT_ESCALATION_RULES = {
    "payment_failures": {
        "when_to_escalate": "支付失败数量超过阈值或同一 account 重复失败",
        "escalation_owner": "stripe_owner",
        "rollback_trigger": "大面积支付失败且 retry 无法恢复",
        "required_evidence": ["payment transaction", "customer invoice detail", "dunning state"],
    },
    "checkout_failures": {
        "when_to_escalate": "邀请制试点 checkout 创建、过期或支付完成链路失败",
        "escalation_owner": "stripe_owner",
        "rollback_trigger": "checkout 无法完成导致付费用户无法恢复权益",
        "required_evidence": ["checkout session", "payment transaction", "provider reconcile result"],
    },
    "remote_generation_failures": {
        "when_to_escalate": "正式域名 Reader 生成 job failed、stale running 或 runtime receipt 出现 provider/backend incident",
        "escalation_owner": "infra_owner",
        "rollback_trigger": "Reader continue / import / choice 在 serverless 环境持续不可恢复",
        "required_evidence": ["reader generation job", "runtime receipt", "resume/retry outcome"],
    },
    "quality_blocks": {
        "when_to_escalate": "Reader/Author 质量门 blocked，或同一 world/account 重复触发",
        "escalation_owner": "quality_owner",
        "rollback_trigger": "质量阻断开始影响试点用户连续阅读或提交",
        "required_evidence": ["quality event", "reason codes", "world/session trace"],
    },
    "vercel_cold_start_latency": {
        "when_to_escalate": "正式域名 cold-start p95 超过阈值或出现 5xx",
        "escalation_owner": "infra_owner",
        "rollback_trigger": "冷启动导致 Reader/checkout/Ops 关键路径频繁失败",
        "required_evidence": ["remote performance artifact", "deployment id", "endpoint timing"],
    },
    "webhook_failures": {
        "when_to_escalate": "provider webhook 未 processed 或 replay 失败",
        "escalation_owner": "infra_owner",
        "rollback_trigger": "关键 webhook 持续积压导致状态无法收敛",
        "required_evidence": ["provider webhook event", "webhook replay result", "invoice/payment state"],
    },
    "invoice_issuance_failures": {
        "when_to_escalate": "issued invoice 缺 hosted/pdf link 或状态异常",
        "escalation_owner": "stripe_owner",
        "rollback_trigger": "正式 invoice 无法稳定签发",
        "required_evidence": ["invoice preview", "issued invoice payload", "provider invoice ref"],
    },
    "dunning_spikes": {
        "when_to_escalate": "open dunning run 超过阈值",
        "escalation_owner": "support_finance_owner",
        "rollback_trigger": "launch 后短时间大面积进入催缴",
        "required_evidence": ["dunning run", "invoice status", "customer workspace"],
    },
    "dispute_spikes": {
        "when_to_escalate": "未结 dispute 超过阈值",
        "escalation_owner": "support_finance_owner",
        "rollback_trigger": "同一波次客户 dispute 快速增多",
        "required_evidence": ["dispute record", "billable event", "manual adjustment/refund state"],
    },
    "support_backlog": {
        "when_to_escalate": "open/in_progress support cases 超过阈值",
        "escalation_owner": "support_finance_owner",
        "rollback_trigger": "launch week 支持积压影响 SLA",
        "required_evidence": ["support case", "account workspace", "owner assignment"],
    },
    "renewal_due_no_action": {
        "when_to_escalate": "renewal_due 账户未挂 dunning/upgrade 动作",
        "escalation_owner": "stripe_owner",
        "rollback_trigger": "关键首批客户临近续费但无动作",
        "required_evidence": ["customer account", "renewal summary", "launch wave status"],
    },
    "overage_without_upgrade_follow_up": {
        "when_to_escalate": "recommended upgrade 长时间无 follow-up",
        "escalation_owner": "support_finance_owner",
        "rollback_trigger": "overage 持续增长但扩容无跟进",
        "required_evidence": ["overage flag", "expansion candidate", "customer workspace"],
    },
}


class ProductionLaunchWeekPackService:
    def __init__(
        self,
        *,
        production_signoff_service: ProductionSignoffService,
        production_acceptance_service: ProductionAcceptanceService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.production_signoff = production_signoff_service
        self.production_acceptance = production_acceptance_service
        self.base_dir = Path(base_dir or ROOT)
        self.dashboard_service: Optional["OpsCommercializationDashboardService"] = None

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _load_json_artifact(self, relative_path: str) -> Dict[str, Any]:
        path = self.base_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"missing_artifact:{relative_path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _latest_go_live_checklist(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_go_live_checklist/latest/go_live_checklist.json")

    def _latest_manual_signoff(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_manual_signoff/latest/manual_signoff_sheet.json")

    def _latest_cutover_pack_summary(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_cutover_pack/latest/summary.json")

    def _latest_delivery_manifest(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/commercial_delivery_bundle/latest/bundle_manifest.json")

    def _latest_pack_dir(self) -> Path:
        return self._artifacts_root() / "production_launch_week_pack" / "latest"

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _write_csv(self, path: Path, *, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _sha256(self, path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _zip_bundle(self, bundle_dir: Path) -> Path:
        zip_path = bundle_dir.parent / f"{bundle_dir.name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(bundle_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(bundle_dir))
        return zip_path

    def _current_context(self) -> Dict[str, Any]:
        signoff_summary = self.production_signoff.current_signoff_summary()
        signoff_detail = None
        if signoff_summary and signoff_summary.get("signoff_id"):
            try:
                signoff_detail = self.production_signoff.signoff_detail(signoff_id=signoff_summary["signoff_id"])
            except KeyError:
                signoff_detail = None
        acceptance_listing = self.production_acceptance.list_acceptance_records(limit=100)
        launch_week_pack = None
        if self.dashboard_service is not None:
            launch_week_pack = self.dashboard_service.summary(limit=50).get("launch_week_alert_pack")
        return {
            "go_live_checklist": self._latest_go_live_checklist(),
            "manual_signoff": self._latest_manual_signoff(),
            "cutover_summary": self._latest_cutover_pack_summary(),
            "delivery_manifest": self._latest_delivery_manifest(),
            "signoff_summary": signoff_summary or {},
            "signoff_detail": signoff_detail or {},
            "acceptance_listing": acceptance_listing,
            "launch_week_alert_pack": launch_week_pack or {"summary": {"alert_count": 0}, "alerts": []},
        }

    def current_pack_summary(
        self,
        *,
        signoff_summary: Optional[Dict[str, Any]] = None,
        acceptance_summary: Optional[Dict[str, Any]] = None,
        launch_week_alert_pack: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        latest_dir = self._latest_pack_dir()
        summary_path = latest_dir / "summary.json"
        manifest_path = latest_dir / "manifest.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            return {
                "status": "generated",
                "bundle_id": summary.get("bundle_id"),
                "generated_at": summary.get("generated_at"),
                "document_count": summary.get("document_count"),
                "unresolved_manual_signoff_count": summary.get("unresolved_manual_signoff_count"),
                "launch_week_alert_count": summary.get("launch_week_alert_count"),
                "launch_wave_count": summary.get("launch_wave_count"),
                "refs": summary.get("refs") or {},
                "manifest": manifest,
            }
        unresolved_manual = len(
            [item for item in list(self._latest_manual_signoff().get("items") or []) if str(item.get("status") or "") == "pending_manual_signoff"]
        )
        return {
            "status": "not_generated",
            "bundle_id": None,
            "generated_at": None,
            "document_count": 6,
            "unresolved_manual_signoff_count": unresolved_manual,
            "launch_week_alert_count": int((launch_week_alert_pack or {}).get("summary", {}).get("alert_count") or 0),
            "launch_wave_count": int((acceptance_summary or {}).get("launch_wave_count") or 0),
            "refs": {},
            "manifest": {},
        }

    def latest_pack(self) -> Dict[str, Any]:
        latest_dir = self._latest_pack_dir()
        summary = self.current_pack_summary()
        return {
            "summary": summary,
            "latest_dir": str(latest_dir) if latest_dir.exists() else None,
            "doc_refs": summary.get("refs", {}).get("doc_refs", []),
        }

    def _launch_day_checklist(self, context: Dict[str, Any]) -> str:
        signoff_detail = context["signoff_detail"] or {}
        cutover_summary = context["cutover_summary"] or {}
        pending_items = [item for item in list(signoff_detail.get("items") or []) if item.get("status") == "pending"]
        lines = [
            "# Launch Day Checklist",
            "",
            "## T-24h",
            f"- Review unresolved production signoff items: {len(pending_items)} pending",
            f"- Confirm cutover pack overall health: {cutover_summary.get('overall_health')}",
            "- Confirm first-customer acceptance status and launch wave assignment",
            "",
            "## T-2h",
            "- Re-run stripe connectivity, webhook health, invoice issuance, payment sync, and customer workspace smoke checks",
            "- Confirm no critical launch-week alerts remain unresolved",
            "- Confirm planned cutover window and rollback owner are visible in canonical signoff",
            "",
            "## T-0",
            "- Mark launch wave status to active when operator decision is made",
            "- Start live monitoring of Reader generation, checkout, quality blocks, Vercel cold-start, support, and dispute signals",
            "",
            "## T+1h",
            "- Review Launch Week Alert Pack for new high/critical signals",
            "- Confirm launch-week remote monitoring remains ready_to_expand before issuing more invites",
            "- Confirm first-customer workspace still reflects invoice / dunning / upgrade posture",
            "",
            "## T+4h",
            "- Review dunning spikes, support backlog, dispute spikes, and overage follow-up",
            "- Attach any material operational evidence to production signoff items",
            "",
            "## T+24h",
            "- Review finance reconciliation sheet",
            "- Confirm support, finance, and on-call owners have no unresolved handoff gaps",
        ]
        return "\n".join(lines)

    def _day_1_monitoring_rows(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for alert in list((context["launch_week_alert_pack"] or {}).get("alerts") or []):
            rows.append(
                {
                    "alert_key": alert.get("alert_key"),
                    "owner_role": alert.get("owner_role"),
                    "threshold_source": ALERT_THRESHOLD_ENV_MAP.get(str(alert.get("alert_key") or ""), "hardcoded"),
                    "escalation_action": " / ".join(alert.get("recommended_actions") or []),
                    "drilldown_refs": " / ".join(f"{item.get('kind')}:{item.get('id')}" for item in alert.get("drilldown_refs") or []),
                }
            )
        return rows

    def _day_1_monitoring_sheet(self, context: Dict[str, Any]) -> str:
        rows = self._day_1_monitoring_rows(context)
        lines = [
            "# Day 1 Monitoring Sheet",
            "",
            "| alert_key | owner_role | threshold_source | escalation_action | drilldown_refs |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                f"| {row['alert_key'] or '-'} | {row['owner_role'] or '-'} | {row['threshold_source'] or '-'} | {row['escalation_action'] or '-'} | {row['drilldown_refs'] or '-'} |"
            )
        return "\n".join(lines)

    def _week_1_ops_board(self, context: Dict[str, Any]) -> str:
        signoff_summary = context["signoff_summary"] or {}
        acceptance_summary = context["acceptance_listing"].get("summary") or {}
        alert_summary = (context["launch_week_alert_pack"] or {}).get("summary") or {}
        lines = [
            "# Week 1 Ops Board",
            "",
            "## Day 1",
            f"- production signoff status: {signoff_summary.get('status') or '-'}",
            f"- launch-week alert count: {alert_summary.get('alert_count') or 0}",
            f"- go_live_ready accounts: {acceptance_summary.get('go_live_ready_count') or 0}",
            "",
            "## Day 2-3",
            f"- blocked go-live accounts: {acceptance_summary.get('blocked_go_live_count') or 0}",
            f"- launch waves: {acceptance_summary.get('launch_wave_count') or 0}",
            f"- unresolved manual signoff: {len([item for item in list(context['manual_signoff'].get('items') or []) if item.get('status') == 'pending_manual_signoff'])}",
            "",
            "## Day 4-7",
            "- review finance reconciliation, support backlog, dispute trends, and expansion follow-up",
            "- confirm no launch-week alert remains without owner action",
        ]
        return "\n".join(lines)

    def _support_triage_matrix(self) -> str:
        rows = [
            ("support_case", "medium", "support_finance_owner", "support -> ops commercialization -> governance if needed", "same business day"),
            ("dispute", "medium", "support_finance_owner", "support -> finance -> manual_adjustment/refund", "same business day"),
            ("governance_case", "high", "security_owner", "support -> governance -> reviewer owner", "same day"),
            ("payment_failure_customer_report", "high", "stripe_owner", "support -> stripe_owner -> dunning follow-up", "same hour"),
        ]
        lines = [
            "# Support Triage Matrix",
            "",
            "| issue_type | severity | primary_owner_role | escalation_path | sla_expectation |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |")
        return "\n".join(lines)

    def _incident_escalation_matrix(self) -> str:
        lines = [
            "# Incident Escalation Matrix",
            "",
            "| alert_key | when_to_escalate | escalation_owner | rollback_trigger | required_evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for key, rule in INCIDENT_ESCALATION_RULES.items():
            lines.append(
                f"| {key} | {rule['when_to_escalate']} | {rule['escalation_owner']} | {rule['rollback_trigger']} | {' / '.join(rule['required_evidence'])} |"
            )
        return "\n".join(lines)

    def _finance_reconciliation_sheet(self, context: Dict[str, Any]) -> str:
        cutover_summary = context["cutover_summary"] or {}
        checks = cutover_summary.get("checks") or {}
        invoice = checks.get("invoice_issuance_smoke") or {}
        payment = checks.get("payment_sync_smoke") or {}
        lines = [
            "# Finance Reconciliation Sheet",
            "",
            f"- invoice preview due: {(invoice.get('invoice_preview') or {}).get('total_due_usd') or 0}",
            f"- issued invoice status: {(invoice.get('issued_invoice') or {}).get('status') or '-'}",
            f"- failed invoice observed: {(payment.get('failed_invoice') or {}).get('status') or '-'}",
            f"- paid invoice observed: {(payment.get('paid_invoice') or {}).get('status') or '-'}",
            f"- dunning after recovery: {(payment.get('lifecycle_after_recovery') or {}).get('dunning_summary', {}).get('status') or '-'}",
            "",
            "## Checklist",
            "- compare invoice preview amount to issued invoice amount",
            "- compare canonical invoice status to provider payment status",
            "- review dunning state against payment failure/recovery",
            "- review disputes and manual adjustments before close of day",
        ]
        return "\n".join(lines)

    def build_pack(self, output_root: str | Path | None = None) -> Dict[str, Any]:
        context = self._current_context()
        run_id = f"production_launch_week_pack_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = Path(output_root) if output_root else (self._artifacts_root() / "production_launch_week_pack" / run_id)
        docs_dir = bundle_dir / "docs"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)

        doc_payloads = {
            "launch_day_checklist.md": self._launch_day_checklist(context),
            "day_1_monitoring_sheet.md": self._day_1_monitoring_sheet(context),
            "week_1_ops_board.md": self._week_1_ops_board(context),
            "support_triage_matrix.md": self._support_triage_matrix(),
            "incident_escalation_matrix.md": self._incident_escalation_matrix(),
            "finance_reconciliation_sheet.md": self._finance_reconciliation_sheet(context),
        }
        for name, content in doc_payloads.items():
            self._write_text(docs_dir / name, content)

        unresolved_manual = len([item for item in list(context["manual_signoff"].get("items") or []) if item.get("status") == "pending_manual_signoff"])
        launch_alert_count = int((context["launch_week_alert_pack"] or {}).get("summary", {}).get("alert_count") or 0)
        acceptance_summary = context["acceptance_listing"].get("summary") or {}
        summary = {
            "bundle_id": run_id,
            "generated_at": self._utcnow(),
            "document_count": len(doc_payloads),
            "unresolved_manual_signoff_count": unresolved_manual,
            "launch_week_alert_count": launch_alert_count,
            "launch_wave_count": acceptance_summary.get("launch_wave_count") or 0,
            "refs": {
                "doc_refs": [f"docs/{name}" for name in doc_payloads],
                "source_refs": {
                    "go_live_checklist": "artifacts/production_go_live_checklist/latest/go_live_checklist.json",
                    "manual_signoff": "artifacts/production_manual_signoff/latest/manual_signoff_sheet.json",
                    "cutover_pack": "artifacts/production_cutover_pack/latest/summary.json",
                    "delivery_bundle": "artifacts/commercial_delivery_bundle/latest/bundle_manifest.json",
                },
            },
        }
        (bundle_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {
            "bundle_id": run_id,
            "generated_at": self._utcnow(),
            "included_files": [
                {
                    "path": str(path.relative_to(bundle_dir)),
                    "size_bytes": path.stat().st_size,
                    "sha256": self._sha256(path),
                }
                for path in sorted(bundle_dir.rglob("*"))
                if path.is_file()
            ],
        }
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (bundle_dir / "README.md").write_text(
            "\n".join(
                [
                    "# Production Launch Week Ops Pack",
                    "",
                    "This pack contains launch-week operational docs derived from current signoff, cutover, acceptance, and commercialization evidence.",
                ]
            ),
            encoding="utf-8",
        )
        zip_path = self._zip_bundle(bundle_dir)
        latest_dir = self._artifacts_root() / "production_launch_week_pack" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "bundle_id": run_id,
            "bundle_dir": str(bundle_dir),
            "latest_dir": str(latest_dir),
            "zip_path": str(zip_path),
            "summary": summary,
        }
