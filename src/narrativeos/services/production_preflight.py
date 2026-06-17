from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .production_cutover_checks import (
    run_audit_logging_smoke,
    run_backup_restore_verification_hooks,
    run_customer_workspace_smoke,
    run_invoice_issuance_smoke,
    run_payment_sync_smoke,
    run_stripe_connectivity_check,
    run_support_routing_smoke,
    run_webhook_health_check,
)
from .production_signoff import ProductionSignoffService
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]

CHECK_SPECS = [
    {"check_key": "stripe_connectivity", "owner_role": "stripe_owner", "linked_signoff_item_code": "billing_005", "classification": "hard", "runner": run_stripe_connectivity_check},
    {"check_key": "webhook_health", "owner_role": "infra_owner", "linked_signoff_item_code": "webhook_001", "classification": "hard", "runner": run_webhook_health_check},
    {"check_key": "invoice_issuance_smoke", "owner_role": "stripe_owner", "linked_signoff_item_code": "billing_005", "classification": "hard", "runner": run_invoice_issuance_smoke},
    {"check_key": "payment_sync_smoke", "owner_role": "infra_owner", "linked_signoff_item_code": "webhook_001", "classification": "hard", "runner": run_payment_sync_smoke},
    {"check_key": "customer_workspace_smoke", "owner_role": "ops_reviewer", "linked_signoff_item_code": None, "classification": "soft", "runner": run_customer_workspace_smoke},
    {"check_key": "support_routing_smoke", "owner_role": "support_finance_owner", "linked_signoff_item_code": "operations_003", "classification": "soft", "runner": run_support_routing_smoke},
    {"check_key": "audit_logging_smoke", "owner_role": "security_owner", "linked_signoff_item_code": "security_003", "classification": "soft", "runner": run_audit_logging_smoke},
    {"check_key": "backup_restore_readiness_hooks", "owner_role": "db_owner", "linked_signoff_item_code": "deploy_002", "classification": "hard", "runner": run_backup_restore_verification_hooks},
]


class ProductionPreflightService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        production_signoff_service: ProductionSignoffService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.production_signoff = production_signoff_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _current_signoff_id(self, signoff_id: Optional[str]) -> Optional[str]:
        if signoff_id:
            return signoff_id
        current = self.production_signoff.current_signoff_summary()
        return (current or {}).get("signoff_id")

    def _append_signoff_evidence_if_linked(self, *, signoff_id: Optional[str], check_row: Dict[str, Any], evidence_ref: str) -> None:
        if not signoff_id or not check_row.get("linked_signoff_item_code"):
            return
        detail = self.production_signoff.signoff_detail(signoff_id=signoff_id)
        item = next((row for row in detail.get("items") or [] if row.get("item_code") == check_row["linked_signoff_item_code"]), None)
        if not item:
            return
        self.production_signoff.append_signoff_evidence(
            actor_id="production_preflight_runner",
            actor_role="ops",
            signoff_item_id=item["signoff_item_id"],
            evidence_type="artifact_ref",
            summary=f"preflight:{check_row['check_key']}:{check_row['status']}",
            source_ref={"path": evidence_ref},
            payload={"preflight_run_id": check_row["preflight_run_id"], "check_key": check_row["check_key"], "status": check_row["status"]},
            customer_safe=False,
        )

    def run_preflight(
        self,
        *,
        actor_id: str,
        actor_role: str,
        launch_wave: str = "wave_1",
        signoff_id: Optional[str] = None,
        target_environment: str = "production",
        output_root: str | Path | None = None,
    ) -> Dict[str, Any]:
        resolved_signoff_id = self._current_signoff_id(signoff_id)
        run = self.repository.save_production_preflight_run(
            {
                "signoff_id": resolved_signoff_id,
                "launch_wave": launch_wave,
                "target_environment": target_environment,
                "status": "running",
                "go_no_go": "manual_review",
                "run_payload": {"requested_by": actor_id, "requested_role": actor_role},
            }
        )
        bundle_dir = Path(output_root) if output_root else (self._artifacts_root() / "production_preflight_runs" / run["preflight_run_id"])
        checks_dir = bundle_dir / "checks"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        checks_dir.mkdir(parents=True, exist_ok=True)

        persisted_checks: List[Dict[str, Any]] = []
        hard_fail_count = 0
        soft_fail_count = 0
        for spec in CHECK_SPECS:
            runner: Callable[..., Dict[str, Any]] = spec["runner"]
            result = runner(output_root=checks_dir)
            check_status = "passed"
            if not bool(result.get("healthy")):
                check_status = "hard_failed" if spec["classification"] == "hard" else "soft_failed"
            if check_status == "hard_failed":
                hard_fail_count += 1
            elif check_status == "soft_failed":
                soft_fail_count += 1
            evidence_ref = f"checks/{spec['check_key']}.json"
            check_row = self.repository.save_production_preflight_check(
                {
                    "preflight_run_id": run["preflight_run_id"],
                    "check_key": spec["check_key"],
                    "linked_signoff_item_code": spec["linked_signoff_item_code"],
                    "owner_role": spec["owner_role"],
                    "status": check_status,
                    "summary": result.get("summary") or spec["check_key"],
                    "evidence_ref": evidence_ref,
                    "payload": result,
                }
            )
            persisted_checks.append(check_row)
            self._append_signoff_evidence_if_linked(signoff_id=resolved_signoff_id, check_row=check_row, evidence_ref=evidence_ref)

        status = "passed"
        go_no_go = "go"
        if hard_fail_count > 0:
            status = "hard_failed"
            go_no_go = "no_go"
        elif soft_fail_count > 0:
            status = "soft_failed"
            go_no_go = "manual_review"
        updated_run = self.repository.save_production_preflight_run(
            {
                **run,
                "status": status,
                "go_no_go": go_no_go,
                "hard_fail_count": hard_fail_count,
                "soft_fail_count": soft_fail_count,
                "run_payload_json": {
                    "requested_by": actor_id,
                    "requested_role": actor_role,
                    "checks_dir": str(checks_dir),
                    "artifact_dir": str(bundle_dir),
                    "check_count": len(persisted_checks),
                },
            }
        )
        report_refs = self._write_report(run=updated_run, checks=persisted_checks, bundle_dir=bundle_dir)
        return {
            "preflight_run": updated_run,
            "checks": persisted_checks,
            "report_refs": report_refs,
        }

    def _write_report(self, *, run: Dict[str, Any], checks: List[Dict[str, Any]], bundle_dir: Path) -> Dict[str, Any]:
        summary_payload = {
            "preflight_run": run,
            "checks": checks,
        }
        self._write_json(bundle_dir / "summary.json", summary_payload)
        lines = [
            "# Production Preflight Report",
            "",
            f"- preflight_run_id: {run['preflight_run_id']}",
            f"- signoff_id: {run.get('signoff_id') or '-'}",
            f"- launch_wave: {run['launch_wave']}",
            f"- target_environment: {run['target_environment']}",
            f"- status: {run['status']}",
            f"- go_no_go: {run['go_no_go']}",
            f"- hard_fail_count: {run['hard_fail_count']}",
            f"- soft_fail_count: {run['soft_fail_count']}",
            "",
            "## Checks",
        ]
        for check in checks:
            lines.append(f"- {check['check_key']}: {check['status']} · owner {check['owner_role']} · linked {check.get('linked_signoff_item_code') or '-'}")
        self._write_text(bundle_dir / "report.md", "\n".join(lines))
        return {
            "artifact_dir": str(bundle_dir),
            "summary_json": str(bundle_dir / "summary.json"),
            "report_md": str(bundle_dir / "report.md"),
        }

    def list_runs(
        self,
        *,
        signoff_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        runs = self.repository.list_production_preflight_runs(signoff_id=signoff_id, launch_wave=launch_wave, limit=limit)
        latest = runs[0] if runs else None
        return {
            "runs": runs,
            "current_run": latest,
            "summary": {
                "run_count": len(runs),
                "latest_run_id": (latest or {}).get("preflight_run_id"),
                "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in runs)),
            },
        }

    def run_detail(self, *, preflight_run_id: str) -> Dict[str, Any]:
        run = self.repository.get_production_preflight_run(preflight_run_id)
        checks = self.repository.list_production_preflight_checks(preflight_run_id=preflight_run_id, limit=100)
        artifact_dir = Path((run.get("run_payload_json") or {}).get("artifact_dir") or self._artifacts_root() / "production_preflight_runs" / preflight_run_id)
        return {
            "preflight_run": run,
            "checks": checks,
            "report_refs": {
                "artifact_dir": str(artifact_dir),
                "summary_json": str(artifact_dir / "summary.json"),
                "report_md": str(artifact_dir / "report.md"),
            },
        }

    def report(self, *, preflight_run_id: str) -> Dict[str, Any]:
        detail = self.run_detail(preflight_run_id=preflight_run_id)
        artifact_dir = Path(detail["report_refs"]["artifact_dir"])
        if not (artifact_dir / "summary.json").exists():
            self._write_report(run=detail["preflight_run"], checks=detail["checks"], bundle_dir=artifact_dir)
        return detail["report_refs"]
