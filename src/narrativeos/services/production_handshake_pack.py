from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .production_acceptance import ProductionAcceptanceService
from .production_signoff import DEFAULT_OWNER_ROLE_MAP, ProductionSignoffService

if TYPE_CHECKING:
    from .ops_commercialization_dashboard import OpsCommercializationDashboardService


ROOT = Path(__file__).resolve().parents[3]

CATEGORY_LAUNCH_IMPACT = {
    "billing": "Blocks production billing / invoice issuance confidence.",
    "webhook": "Blocks provider state sync and payment reconciliation.",
    "security": "Blocks customer-safe production operation and audit posture.",
    "operations": "Blocks support / finance / on-call launch coverage.",
    "deploy": "Blocks rollback / restore confidence during launch.",
    "acceptance": "Blocks first-customer production launch approval.",
    "delivery": "Blocks commercial handoff completeness.",
}

ROLE_BY_CATEGORY = {
    "billing": "stripe_owner",
    "webhook": "infra_owner",
    "security": "security_owner",
    "operations": "support_finance_owner",
    "deploy": "db_owner",
}

OWNER_MATRIX = [
    {
        "owner_role": "ops_reviewer",
        "responsibilities": [
            "production signoff coordination",
            "launch wave decision",
            "first-customer acceptance oversight",
        ],
        "fallback_owner_role": "support_finance_owner",
        "source_refs": ["production_signoff", "production_acceptance", "launch_week_ops_pack"],
    },
    {
        "owner_role": "stripe_owner",
        "responsibilities": [
            "Stripe live billing readiness",
            "invoice issuance and payment recovery",
            "renewal / dunning escalation",
        ],
        "fallback_owner_role": "support_finance_owner",
        "source_refs": ["billing_005", "payment_failures", "invoice_issuance_failures"],
    },
    {
        "owner_role": "infra_owner",
        "responsibilities": [
            "production webhook endpoint",
            "webhook replay and connectivity",
            "cutover environment checks",
        ],
        "fallback_owner_role": "db_owner",
        "source_refs": ["webhook_001", "webhook_failures", "production_cutover_pack"],
    },
    {
        "owner_role": "security_owner",
        "responsibilities": [
            "customer-safe logging boundary",
            "retention / access review",
            "security escalation signoff",
        ],
        "fallback_owner_role": "ops_reviewer",
        "source_refs": ["security_003", "customer_safe_logging"],
    },
    {
        "owner_role": "support_finance_owner",
        "responsibilities": [
            "support / dispute triage",
            "finance reconciliation",
            "customer escalation handling",
        ],
        "fallback_owner_role": "ops_reviewer",
        "source_refs": ["operations_003", "support_backlog", "dispute_spikes", "finance_reconciliation"],
    },
    {
        "owner_role": "db_owner",
        "responsibilities": [
            "backup / restore readiness",
            "rollback operator execution",
            "database recovery escalation",
        ],
        "fallback_owner_role": "infra_owner",
        "source_refs": ["deploy_002", "backup_restore_verification"],
    },
]

INTERNAL_ESCALATION_TIERS = [
    {
        "tier": "sev1_billing",
        "trigger": "payment failure, invoice issuance failure, or dunning spike with customer impact",
        "primary_owner_role": "stripe_owner",
        "secondary_owner_role": "support_finance_owner",
    },
    {
        "tier": "sev1_webhook",
        "trigger": "webhook delivery / replay failure or provider state divergence",
        "primary_owner_role": "infra_owner",
        "secondary_owner_role": "stripe_owner",
    },
    {
        "tier": "sev1_security",
        "trigger": "customer-safe logging / retention / access boundary concern",
        "primary_owner_role": "security_owner",
        "secondary_owner_role": "ops_reviewer",
    },
    {
        "tier": "sev2_support_finance",
        "trigger": "support backlog, dispute escalation, or reconciliation mismatch",
        "primary_owner_role": "support_finance_owner",
        "secondary_owner_role": "ops_reviewer",
    },
]


class ProductionHandshakePackService:
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

    def _load_json_artifact(self, relative_path: str, *, optional: bool = False) -> Dict[str, Any]:
        path = self.base_dir / relative_path
        if not path.exists():
            if optional:
                return {}
            raise FileNotFoundError(f"missing_artifact:{relative_path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _latest_go_live_checklist(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_go_live_checklist/latest/go_live_checklist.json")

    def _latest_manual_signoff(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_manual_signoff/latest/manual_signoff_sheet.json")

    def _latest_cutover_pack(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_cutover_pack/latest/summary.json")

    def _latest_launch_week_pack(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_launch_week_pack/latest/summary.json", optional=True)

    def _latest_delivery_bundle_manifest(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/commercial_delivery_bundle/latest/bundle_manifest.json")

    def _latest_external_acceptance(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json", optional=True)

    def _latest_pack_dir(self) -> Path:
        return self._artifacts_root() / "production_handshake_pack" / "latest"

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

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

    def _owner_role_for(self, *, item_code: Optional[str], category: Optional[str]) -> str:
        if item_code:
            return DEFAULT_OWNER_ROLE_MAP.get(str(item_code), ROLE_BY_CATEGORY.get(str(category or ""), "ops_owner"))
        return ROLE_BY_CATEGORY.get(str(category or ""), "ops_owner")

    def _current_context(self) -> Dict[str, Any]:
        signoff_summary = self.production_signoff.current_signoff_summary()
        signoff_detail = None
        if signoff_summary and signoff_summary.get("signoff_id"):
            try:
                signoff_detail = self.production_signoff.signoff_detail(signoff_id=signoff_summary["signoff_id"])
            except KeyError:
                signoff_detail = None
        acceptance_listing = self.production_acceptance.list_acceptance_records(limit=100)
        launch_week_alert_pack = {"summary": {"alert_count": 0}, "alerts": []}
        if self.dashboard_service is not None:
            launch_week_alert_pack = self.dashboard_service.summary(limit=50).get("launch_week_alert_pack") or launch_week_alert_pack
        return {
            "go_live_checklist": self._latest_go_live_checklist(),
            "manual_signoff": self._latest_manual_signoff(),
            "cutover_summary": self._latest_cutover_pack(),
            "launch_week_pack": self._latest_launch_week_pack(),
            "delivery_manifest": self._latest_delivery_bundle_manifest(),
            "external_acceptance": self._latest_external_acceptance(),
            "signoff_summary": signoff_summary or {},
            "signoff_detail": signoff_detail or {},
            "acceptance_listing": acceptance_listing,
            "launch_week_alert_pack": launch_week_alert_pack,
        }

    def _signoff_items_by_code(self, context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        items = (context.get("signoff_detail") or {}).get("items") or []
        return {str(item.get("item_code") or ""): dict(item) for item in items if item.get("item_code")}

    def _code_ready_rows(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        signoff_items = self._signoff_items_by_code(context)
        for source_item in list((context.get("go_live_checklist") or {}).get("items") or []):
            if bool(source_item.get("requires_manual_confirmation")):
                continue
            item_code = str(source_item.get("item_id") or "")
            signoff_item = signoff_items.get(item_code, {})
            rows.append(
                {
                    "dependency_id": item_code,
                    "dependency_class": "code_ready",
                    "category": str(source_item.get("category") or "unknown"),
                    "label": str(source_item.get("label") or item_code),
                    "owner_role": self._owner_role_for(item_code=item_code, category=source_item.get("category")),
                    "current_status": str(signoff_item.get("status") or source_item.get("status") or "ready"),
                    "human_signoff_required": "no",
                    "launch_impact": CATEGORY_LAUNCH_IMPACT.get(str(source_item.get("category") or ""), "Supports launch readiness evidence."),
                    "source_ref": str(source_item.get("evidence") or ""),
                    "notes": str(source_item.get("notes") or ""),
                }
            )
        external_acceptance = context.get("external_acceptance") or {}
        delivery_manifest = context.get("delivery_manifest") or {}
        acceptance_summary = (context.get("acceptance_listing") or {}).get("summary") or {}
        rows.extend(
            [
                {
                    "dependency_id": "delivery_bundle_001",
                    "dependency_class": "code_ready",
                    "category": "delivery",
                    "label": "Final commercial delivery bundle is generated and ready for signature",
                    "owner_role": "ops_reviewer",
                    "current_status": str(delivery_manifest.get("bundle_status") or "unknown"),
                    "human_signoff_required": "no",
                    "launch_impact": CATEGORY_LAUNCH_IMPACT["delivery"],
                    "source_ref": "artifacts/commercial_delivery_bundle/latest/bundle_manifest.json",
                    "notes": f"included_files={len(delivery_manifest.get('included_files') or [])}",
                },
                {
                    "dependency_id": "acceptance_flow_001",
                    "dependency_class": "code_ready",
                    "category": "acceptance",
                    "label": "First-customer production acceptance flow is available",
                    "owner_role": "ops_reviewer",
                    "current_status": "ready" if int(acceptance_summary.get("acceptance_record_count") or 0) > 0 else "warning",
                    "human_signoff_required": "no",
                    "launch_impact": CATEGORY_LAUNCH_IMPACT["acceptance"],
                    "source_ref": "/v1/ops/production-acceptance",
                    "notes": f"acceptance_records={acceptance_summary.get('acceptance_record_count') or 0}",
                },
                {
                    "dependency_id": "external_acceptance_001",
                    "dependency_class": "code_ready",
                    "category": "billing",
                    "label": "Latest Stripe sandbox external acceptance evidence is available",
                    "owner_role": "stripe_owner",
                    "current_status": "ready" if bool((external_acceptance.get("acceptance") or {}).get("all_passed")) else "warning",
                    "human_signoff_required": "no",
                    "launch_impact": CATEGORY_LAUNCH_IMPACT["billing"],
                    "source_ref": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
                    "notes": f"all_passed={bool((external_acceptance.get('acceptance') or {}).get('all_passed'))}",
                },
            ]
        )
        return rows

    def _org_ready_rows(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        signoff_items = self._signoff_items_by_code(context)
        for source_item in list((context.get("manual_signoff") or {}).get("items") or []):
            item_code = str(source_item.get("item_id") or "")
            signoff_item = signoff_items.get(item_code, {})
            latest_evidence = signoff_item.get("latest_evidence") or {}
            source_ref = ""
            if isinstance(latest_evidence.get("source_ref"), dict):
                source_ref = str(latest_evidence["source_ref"].get("path") or "")
            rows.append(
                {
                    "dependency_id": item_code,
                    "dependency_class": "org_ready",
                    "category": str(source_item.get("category") or "unknown"),
                    "label": str(source_item.get("label") or item_code),
                    "owner_role": self._owner_role_for(item_code=item_code, category=source_item.get("category")),
                    "owner_actor_id": signoff_item.get("owner_actor_id"),
                    "due_at": signoff_item.get("due_at"),
                    "current_status": str(signoff_item.get("status") or source_item.get("status") or "pending_manual_signoff"),
                    "human_signoff_required": "yes",
                    "launch_impact": CATEGORY_LAUNCH_IMPACT.get(str(source_item.get("category") or ""), "Blocks production launch signoff."),
                    "source_ref": source_ref or str(source_item.get("evidence") or ""),
                    "prompt": str(source_item.get("prompt") or ""),
                    "notes": str(signoff_item.get("decision_note") or source_item.get("notes") or ""),
                }
            )
        return rows

    def _customer_contact_rows(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        ready_accounts = list((context.get("acceptance_listing") or {}).get("go_live_ready_accounts") or [])
        rows: List[Dict[str, Any]] = []
        for item in ready_accounts:
            rows.append(
                {
                    "account_id": str(item.get("account_id") or ""),
                    "launch_wave": str(item.get("launch_wave") or "-"),
                    "go_live_status": str(item.get("status") or "-"),
                    "customer_primary_contact": "human_fill_required",
                    "customer_billing_contact": "human_fill_required",
                    "customer_ops_contact": "human_fill_required",
                    "internal_launch_owner_role": "ops_reviewer",
                    "internal_billing_owner_role": "stripe_owner",
                    "internal_support_owner_role": "support_finance_owner",
                    "internal_escalation_path": "ops_reviewer -> stripe_owner/infra_owner/security_owner/support_finance_owner",
                    "status": "incomplete",
                }
            )
        return rows

    def _contact_gap_count(self, contact_rows: List[Dict[str, Any]]) -> int:
        return sum(
            1
            for row in contact_rows
            for key in ("customer_primary_contact", "customer_billing_contact", "customer_ops_contact")
            if str(row.get(key) or "") == "human_fill_required"
        )

    def _legal_ops_handoff_checklist(self, context: Dict[str, Any], *, code_rows: List[Dict[str, Any]], org_rows: List[Dict[str, Any]], contact_rows: List[Dict[str, Any]]) -> str:
        signoff = context.get("signoff_summary") or {}
        acceptance_summary = (context.get("acceptance_listing") or {}).get("summary") or {}
        external_acceptance = context.get("external_acceptance") or {}
        lines = [
            "# Legal Ops Handoff Checklist",
            "",
            "> This checklist structures launch dependencies for legal / finance / support / on-call handoff. It is not legal advice and does not replace human signoff.",
            "",
            "## Launch Snapshot",
            f"- production_signoff: {signoff.get('status') or '-'}",
            f"- pending_manual_signoff_items: {len([row for row in org_rows if row['current_status'] not in {'approved', 'waived'}])}",
            f"- launch_wave_count: {acceptance_summary.get('launch_wave_count') or 0}",
            f"- go_live_ready_accounts: {acceptance_summary.get('go_live_ready_count') or 0}",
            f"- blocked_go_live_accounts: {acceptance_summary.get('blocked_go_live_count') or 0}",
            f"- stripe_sandbox_external_acceptance: {bool((external_acceptance.get('acceptance') or {}).get('all_passed'))}",
            f"- customer_contact_slots_missing: {self._contact_gap_count(contact_rows)}",
            "",
            "## Code-Ready Evidence",
            "| dependency_id | owner_role | status | source_ref | notes |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in code_rows:
            lines.append(
                f"| {row['dependency_id']} | {row['owner_role']} | {row['current_status']} | {row['source_ref'] or '-'} | {row['notes'] or '-'} |"
            )
        lines.extend(
            [
                "",
                "## Org-Ready Human Signoff",
                "| dependency_id | owner_role | status | due_at | source_ref | notes |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in org_rows:
            lines.append(
                f"| {row['dependency_id']} | {row['owner_role']} | {row['current_status']} | {row.get('due_at') or '-'} | {row['source_ref'] or '-'} | {row['notes'] or '-'} |"
            )
        lines.extend(
            [
                "",
                "## Required Human Signoff Inputs",
                "- confirm live Stripe merchant configuration and launch scope against the contract/order form",
                "- confirm production webhook endpoint / signing secret in the provider dashboard",
                "- confirm production customer-safe logging / retention / access boundaries",
                "- confirm launch-week on-call, finance, and support coverage",
                "- confirm backup / restore operator readiness and rollback ownership",
            ]
        )
        return "\n".join(lines)

    def _contract_dependency_matrix(self, *, code_rows: List[Dict[str, Any]], org_rows: List[Dict[str, Any]]) -> str:
        lines = [
            "# Contract Dependency Matrix",
            "",
            "> Separate code-ready evidence from org-ready launch commitments. Do not treat this file as a legal conclusion.",
            "",
            "## Code-Ready Dependencies",
            "| dependency_id | category | owner_role | current_status | human_signoff_required | launch_impact | source_ref |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in code_rows:
            lines.append(
                f"| {row['dependency_id']} | {row['category']} | {row['owner_role']} | {row['current_status']} | {row['human_signoff_required']} | {row['launch_impact']} | {row['source_ref'] or '-'} |"
            )
        lines.extend(
            [
                "",
                "## Org-Ready Dependencies",
                "| dependency_id | category | owner_role | current_status | human_signoff_required | launch_impact | source_ref |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in org_rows:
            lines.append(
                f"| {row['dependency_id']} | {row['category']} | {row['owner_role']} | {row['current_status']} | {row['human_signoff_required']} | {row['launch_impact']} | {row['source_ref'] or '-'} |"
            )
        return "\n".join(lines)

    def _production_owner_matrix(self, context: Dict[str, Any], *, org_rows: List[Dict[str, Any]]) -> str:
        alerts = list((context.get("launch_week_alert_pack") or {}).get("alerts") or [])
        open_by_role: Dict[str, int] = {}
        for row in org_rows:
            if row["current_status"] not in {"approved", "waived"}:
                open_by_role[row["owner_role"]] = open_by_role.get(row["owner_role"], 0) + 1
        alert_keys_by_role: Dict[str, List[str]] = {}
        for alert in alerts:
            role = str(alert.get("owner_role") or "")
            if not role:
                continue
            alert_keys_by_role.setdefault(role, []).append(str(alert.get("alert_key") or ""))
        lines = [
            "# Production Owner Matrix",
            "",
            "| owner_role | responsibilities | fallback_owner_role | open_dependencies | active_alert_keys | source_refs |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in OWNER_MATRIX:
            lines.append(
                f"| {row['owner_role']} | {' / '.join(row['responsibilities'])} | {row['fallback_owner_role']} | {open_by_role.get(row['owner_role'], 0)} | {' / '.join(alert_keys_by_role.get(row['owner_role'], [])) or '-'} | {' / '.join(row['source_refs'])} |"
            )
        return "\n".join(lines)

    def _customer_escalation_contacts(self, *, contact_rows: List[Dict[str, Any]]) -> str:
        lines = [
            "# Customer Escalation Contacts",
            "",
            "> External customer contacts must be filled by human operators. Placeholders below are intentional and should not be treated as approved contacts.",
            "",
            "## Internal Escalation Roles",
            "| escalation_tier | trigger | primary_owner_role | secondary_owner_role |",
            "| --- | --- | --- | --- |",
        ]
        for tier in INTERNAL_ESCALATION_TIERS:
            lines.append(
                f"| {tier['tier']} | {tier['trigger']} | {tier['primary_owner_role']} | {tier['secondary_owner_role']} |"
            )
        lines.extend(
            [
                "",
                "## First-Customer Launch Contacts",
                "| account_id | launch_wave | go_live_status | customer_primary_contact | customer_billing_contact | customer_ops_contact | internal_launch_owner_role | internal_billing_owner_role | internal_support_owner_role | status |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        if not contact_rows:
            lines.append("| - | - | - | human_fill_required | human_fill_required | human_fill_required | ops_reviewer | stripe_owner | support_finance_owner | no_launch_customers_selected |")
        else:
            for row in contact_rows:
                lines.append(
                    f"| {row['account_id'] or '-'} | {row['launch_wave'] or '-'} | {row['go_live_status'] or '-'} | {row['customer_primary_contact']} | {row['customer_billing_contact']} | {row['customer_ops_contact']} | {row['internal_launch_owner_role']} | {row['internal_billing_owner_role']} | {row['internal_support_owner_role']} | {row['status']} |"
                )
        return "\n".join(lines)

    def current_pack_summary(
        self,
        *,
        signoff_summary: Optional[Dict[str, Any]] = None,
        acceptance_summary: Optional[Dict[str, Any]] = None,
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
                "org_ready_dependency_count": summary.get("org_ready_dependency_count"),
                "contact_gap_count": summary.get("contact_gap_count"),
                "launch_wave_count": summary.get("launch_wave_count"),
                "launch_customer_count": summary.get("launch_customer_count"),
                "refs": summary.get("refs") or {},
                "manifest": manifest,
            }
        manual_items = list(self._latest_manual_signoff().get("items") or [])
        acceptance_summary = acceptance_summary or {}
        launch_customer_count = int(acceptance_summary.get("acceptance_record_count") or 0)
        return {
            "status": "not_generated",
            "bundle_id": None,
            "generated_at": None,
            "document_count": 4,
            "unresolved_manual_signoff_count": len([item for item in manual_items if str(item.get("status") or "") == "pending_manual_signoff"]),
            "org_ready_dependency_count": len(manual_items),
            "contact_gap_count": launch_customer_count * 3,
            "launch_wave_count": int(acceptance_summary.get("launch_wave_count") or 0),
            "launch_customer_count": launch_customer_count,
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

    def build_pack(self, output_root: str | Path | None = None) -> Dict[str, Any]:
        context = self._current_context()
        code_rows = self._code_ready_rows(context)
        org_rows = self._org_ready_rows(context)
        contact_rows = self._customer_contact_rows(context)

        run_id = f"production_handshake_pack_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = Path(output_root) if output_root else (self._artifacts_root() / "production_handshake_pack" / run_id)
        docs_dir = bundle_dir / "docs"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)

        doc_payloads = {
            "legal_ops_handoff_checklist.md": self._legal_ops_handoff_checklist(context, code_rows=code_rows, org_rows=org_rows, contact_rows=contact_rows),
            "contract_dependency_matrix.md": self._contract_dependency_matrix(code_rows=code_rows, org_rows=org_rows),
            "production_owner_matrix.md": self._production_owner_matrix(context, org_rows=org_rows),
            "customer_escalation_contacts.md": self._customer_escalation_contacts(contact_rows=contact_rows),
        }
        for name, content in doc_payloads.items():
            self._write_text(docs_dir / name, content)

        acceptance_summary = (context.get("acceptance_listing") or {}).get("summary") or {}
        summary = {
            "bundle_id": run_id,
            "generated_at": self._utcnow(),
            "document_count": len(doc_payloads),
            "unresolved_manual_signoff_count": len([row for row in org_rows if row["current_status"] not in {"approved", "waived"}]),
            "org_ready_dependency_count": len(org_rows),
            "contact_gap_count": self._contact_gap_count(contact_rows),
            "launch_wave_count": int(acceptance_summary.get("launch_wave_count") or 0),
            "launch_customer_count": int(acceptance_summary.get("acceptance_record_count") or 0),
            "refs": {
                "doc_refs": [f"docs/{name}" for name in doc_payloads],
                "source_refs": {
                    "go_live_checklist": "artifacts/production_go_live_checklist/latest/go_live_checklist.json",
                    "manual_signoff": "artifacts/production_manual_signoff/latest/manual_signoff_sheet.json",
                    "cutover_pack": "artifacts/production_cutover_pack/latest/summary.json",
                    "launch_week_pack": "artifacts/production_launch_week_pack/latest/summary.json",
                    "delivery_bundle": "artifacts/commercial_delivery_bundle/latest/bundle_manifest.json",
                    "stripe_external_acceptance": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
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
                    "# Production Legal & Human-Ops Handshake Pack",
                    "",
                    "This pack structures code-ready evidence and org-ready human dependencies for production launch signoff.",
                ]
            ),
            encoding="utf-8",
        )
        zip_path = self._zip_bundle(bundle_dir)
        latest_dir = self._artifacts_root() / "production_handshake_pack" / "latest"
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
