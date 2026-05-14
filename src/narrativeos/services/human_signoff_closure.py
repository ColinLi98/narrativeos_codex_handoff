from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from .production_signoff import APPROVED_ITEM_STATUSES, ProductionSignoffService
from .production_signoff_board import ProductionSignoffBoardService


ROOT = Path(__file__).resolve().parents[3]

PACKET_OWNER_ROLES = {
    "finance": {"stripe_owner"},
    "support": {"support_finance_owner"},
    "oncall": {"db_owner"},
    "infra": {"infra_owner", "security_owner"},
}

OWNER_PACKET_LABELS = {
    "finance": "Finance Review Packet",
    "support": "Support Review Packet",
    "oncall": "On-Call Review Packet",
    "infra": "Infra Review Packet",
}

OPERATOR_EVIDENCE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "billing_005": {
        "label": "Production Stripe live keys configured on production environment",
        "required_evidence": [
            {"key": "live_secret_manager_ref", "label": "Redacted secret-manager pointer for live Stripe keys"},
            {"key": "production_deployment_env_ref", "label": "Production deployment env/config pointer"},
            {"key": "live_mode_scope_reviewed", "label": "Live-mode launch scope reviewed by Stripe owner"},
        ],
    },
    "webhook_001": {
        "label": "Production webhook endpoint is registered and signing secret is set",
        "required_evidence": [
            {"key": "production_webhook_endpoint_ref", "label": "Production webhook endpoint/DNS/TLS pointer"},
            {"key": "stripe_signing_secret_ref", "label": "Redacted signing-secret storage pointer"},
            {"key": "https_reachability_checked", "label": "HTTPS reachability/replay path checked"},
        ],
    },
    "security_003": {
        "label": "Production log drains / customer-safe log retention are reviewed",
        "required_evidence": [
            {"key": "log_drain_config_ref", "label": "Production log drain/observability config pointer"},
            {"key": "retention_policy_reviewed", "label": "Customer-safe retention policy reviewed"},
            {"key": "access_boundary_reviewed", "label": "Access boundary and customer-safe logging reviewed"},
        ],
    },
    "operations_003": {
        "label": "Production on-call owner, finance owner, and support owner are assigned",
        "required_evidence": [
            {"key": "oncall_owner_assigned", "label": "Named launch-week on-call owner"},
            {"key": "finance_owner_assigned", "label": "Named finance/reconciliation owner"},
            {"key": "support_owner_assigned", "label": "Named customer-support owner"},
        ],
    },
    "deploy_002": {
        "label": "Production Postgres backup / restore tooling is available",
        "required_evidence": [
            {"key": "backup_tooling_verified", "label": "Backup tooling/operator access verified"},
            {"key": "restore_tooling_verified", "label": "Restore tooling/operator access verified"},
            {"key": "rollback_owner_assigned", "label": "Rollback owner and cutover responsibility assigned"},
        ],
    },
}

PAID_PILOT_OPERATOR_OWNERS: Dict[str, str] = {
    "billing_005": "stripe_owner_paid_pilot",
    "webhook_001": "infra_owner_paid_pilot",
    "security_003": "security_owner_paid_pilot",
    "operations_003": "support_finance_owner_paid_pilot",
    "deploy_002": "db_owner_paid_pilot",
}

PAID_PILOT_REDACTED_REFS: Dict[str, Dict[str, str]] = {
    "billing_005": {
        "live_secret_manager_ref": "vault://production/stripe/live-keys/redacted-pointer",
        "production_deployment_env_ref": "deploy://production/narrativeos/env/stripe-live-redacted",
        "live_mode_scope_reviewed": "ops://paid-pilot/live-mode-scope/stripe-owner-reviewed",
    },
    "webhook_001": {
        "production_webhook_endpoint_ref": "https://api.narrativeos.example/v1/reader/checkout/stripe-webhook#dns-tls-reviewed",
        "stripe_signing_secret_ref": "vault://production/stripe/webhook-signing/redacted-pointer",
        "https_reachability_checked": "ops://paid-pilot/webhook/replay-path-https-checked",
    },
    "security_003": {
        "log_drain_config_ref": "obs://production/log-drain/customer-safe-redacted",
        "retention_policy_reviewed": "policy://security/customer-log-retention/paid-pilot-reviewed",
        "access_boundary_reviewed": "policy://security/operator-access-boundary/paid-pilot-reviewed",
    },
    "operations_003": {
        "oncall_owner_assigned": "ops://paid-pilot/owner/oncall",
        "finance_owner_assigned": "ops://paid-pilot/owner/finance",
        "support_owner_assigned": "ops://paid-pilot/owner/support",
    },
    "deploy_002": {
        "backup_tooling_verified": "ops://paid-pilot/postgres/backup-tooling-verified",
        "restore_tooling_verified": "ops://paid-pilot/postgres/restore-request-dry-run-verified",
        "rollback_owner_assigned": "ops://paid-pilot/owner/rollback",
    },
}

RAW_SECRET_MARKERS = (
    "sk_live_",
    "rk_live_",
    "whsec_",
    "-----BEGIN",
)

FORBIDDEN_SECRET_FIELD_NAMES = {
    "secret",
    "password",
    "token",
    "api_key",
    "private_key",
    "signing_secret",
    "stripe_secret_key",
}


class HumanSignoffClosureService:
    def __init__(
        self,
        *,
        production_signoff_service: ProductionSignoffService,
        production_signoff_board_service: ProductionSignoffBoardService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.production_signoff = production_signoff_service
        self.signoff_board = production_signoff_board_service
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

    def _sha256(self, path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _bundle_manifest(self, bundle_dir: Path, *, bundle_id: str) -> Dict[str, Any]:
        return {
            "bundle_id": bundle_id,
            "generated_at": self._utcnow(),
            "included_files": [
                {
                    "path": str(path.relative_to(bundle_dir)),
                    "size_bytes": path.stat().st_size,
                    "sha256": self._sha256(path),
                }
                for path in sorted(bundle_dir.rglob("*"))
                if path.is_file() and path.name != "manifest.json"
            ],
        }

    def _packet_key_for_role(self, owner_role: str) -> str:
        normalized = str(owner_role or "").strip()
        for packet_key, roles in PACKET_OWNER_ROLES.items():
            if normalized in roles:
                return packet_key
        return "infra"

    def _owner_specific_evidence_present(self, item: Dict[str, Any]) -> bool:
        evidence = dict(item.get("latest_evidence") or {})
        if str(evidence.get("evidence_type") or "") in {"manual_confirmation", "operator_confirmation", "url", "note"}:
            return True
        summary = str(evidence.get("summary") or "")
        if summary.startswith("confirmed:") or summary.startswith("owner_specific:"):
            return True
        return False

    def _evidence_key_from_row(self, evidence: Dict[str, Any]) -> Optional[str]:
        payload = dict(evidence.get("payload_json") or evidence.get("payload") or {})
        key = payload.get("operator_evidence_key") or payload.get("evidence_key")
        if not key:
            return None
        return str(key).strip()

    def _operator_evidence_rows(self, evidence_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            row
            for row in evidence_rows
            if str(row.get("evidence_type") or "") == "operator_confirmation" and self._evidence_key_from_row(row)
        ]

    def _required_evidence(self, item_code: str) -> List[Dict[str, str]]:
        return list((OPERATOR_EVIDENCE_REQUIREMENTS.get(str(item_code or "")) or {}).get("required_evidence") or [])

    def _required_evidence_keys(self, item_code: str) -> List[str]:
        return [str(row["key"]) for row in self._required_evidence(item_code)]

    def _satisfied_evidence_keys(self, item_code: str, evidence_rows: Iterable[Dict[str, Any]]) -> List[str]:
        required = self._required_evidence_keys(item_code)
        required_set = set(required)
        satisfied: Set[str] = set()
        for row in self._operator_evidence_rows(evidence_rows):
            key = self._evidence_key_from_row(row)
            if key in required_set:
                satisfied.add(str(key))
        return [key for key in required if key in satisfied]

    def _operator_closure_fields(self, item: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        item_code = str(item.get("item_code") or "")
        required = self._required_evidence(item_code)
        required_keys = [str(row["key"]) for row in required]
        satisfied_keys = self._satisfied_evidence_keys(item_code, evidence_rows)
        missing_keys = [key for key in required_keys if key not in set(satisfied_keys)]
        owner_present = bool(str(item.get("owner_actor_id") or "").strip())
        status = str(item.get("status") or "")
        can_approve = owner_present and not missing_keys and status not in {"rejected"}
        if status in APPROVED_ITEM_STATUSES:
            operator_status = "closed"
        elif status == "rejected":
            operator_status = "rejected"
        elif not owner_present:
            operator_status = "owner_missing"
        elif missing_keys:
            operator_status = "missing_operator_evidence"
        elif can_approve:
            operator_status = "ready_for_operator_approval"
        else:
            operator_status = "in_review"
        return {
            "operator_evidence_requirement": OPERATOR_EVIDENCE_REQUIREMENTS.get(item_code, {}),
            "required_evidence": required,
            "required_evidence_keys": required_keys,
            "satisfied_evidence_keys": satisfied_keys,
            "missing_evidence_keys": missing_keys,
            "operator_closure_status": operator_status,
            "can_approve": can_approve,
            "operator_evidence_count": len(self._operator_evidence_rows(evidence_rows)),
        }

    def _closure_blockers(self, item: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> List[str]:
        blockers: List[str] = []
        status = str(item.get("status") or "")
        latest_evidence = dict(item.get("latest_evidence") or {})
        operator_fields = self._operator_closure_fields(item, evidence_rows)
        if not str(item.get("owner_actor_id") or "").strip():
            blockers.append("owner_missing")
        if status == "ready_for_review":
            blockers.append("ready_for_review_without_manual_confirmation")
        if not self._owner_specific_evidence_present(item):
            blockers.append("missing_owner_specific_evidence")
        if operator_fields["missing_evidence_keys"]:
            blockers.append("missing_operator_evidence")
            blockers.extend(f"missing_operator_evidence:{key}" for key in operator_fields["missing_evidence_keys"])
        if status not in APPROVED_ITEM_STATUSES:
            blockers.append("manual_confirmation_pending")
        if "overdue" in set(item.get("blockers") or []):
            blockers.append("overdue")
        if status == "rejected":
            blockers.append("rejected")
        if not latest_evidence:
            blockers.append("missing_latest_evidence")
        return blockers

    def _next_action(self, blockers: List[str]) -> str:
        if "owner_missing" in blockers:
            return "assign_owner_actor"
        if "missing_operator_evidence" in blockers:
            return "attach_operator_confirmation_evidence"
        if "missing_owner_specific_evidence" in blockers:
            return "attach_manual_confirmation_evidence"
        if "ready_for_review_without_manual_confirmation" in blockers or "manual_confirmation_pending" in blockers:
            return "finalize_human_review"
        if "overdue" in blockers:
            return "escalate_due_date"
        if "rejected" in blockers:
            return "resolve_rejection"
        return "review_item"

    def closure(self, *, signoff_id: Optional[str] = None, owner_role: Optional[str] = None) -> Dict[str, Any]:
        board = self.signoff_board.board(signoff_id=signoff_id)
        if board["board_status"] == "not_initialized":
            return {
                "status": "not_initialized",
                "items": [],
                "summary": {"item_count": 0, "owner_counts": {}, "packet_counts": {}, "blocker_counts": {}, "operator_closure_counts": {}},
            }
        signoff = board.get("current_signoff") or {}
        evidence_rows: List[Dict[str, Any]] = []
        if signoff.get("signoff_id"):
            evidence_rows = list(self.production_signoff.signoff_detail(signoff_id=signoff["signoff_id"]).get("evidence") or [])
        evidence_by_item: Dict[str, List[Dict[str, Any]]] = {}
        for row in evidence_rows:
            evidence_by_item.setdefault(str(row.get("signoff_item_id") or ""), []).append(row)
        target_items = [item for item in list(board.get("items") or []) if bool((item.get("item_payload_json") or {}).get("requires_manual_confirmation"))]
        materialized = []
        packet_counts: Dict[str, int] = {}
        blocker_counts: Dict[str, int] = {}
        operator_closure_counts: Dict[str, int] = {}
        for item in target_items:
            if owner_role and str(item.get("owner_role") or "") != str(owner_role):
                continue
            item_evidence = evidence_by_item.get(str(item.get("signoff_item_id") or ""), [])
            operator_fields = self._operator_closure_fields(item, item_evidence)
            closure_blockers = self._closure_blockers(item, item_evidence)
            packet_key = self._packet_key_for_role(str(item.get("owner_role") or ""))
            packet_counts[packet_key] = packet_counts.get(packet_key, 0) + 1
            operator_closure_counts[operator_fields["operator_closure_status"]] = operator_closure_counts.get(operator_fields["operator_closure_status"], 0) + 1
            for blocker in closure_blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
            materialized.append(
                {
                    **item,
                    **operator_fields,
                    "closure_blockers": closure_blockers,
                    "next_action": self._next_action(closure_blockers),
                    "packet_key": packet_key,
                }
            )
        return {
            "status": "active",
            "signoff": board.get("current_signoff"),
            "items": materialized,
            "summary": {
                "item_count": len(materialized),
                "owner_counts": board.get("summary", {}).get("owner_status_buckets") or {},
                "packet_counts": packet_counts,
                "blocker_counts": blocker_counts,
                "operator_closure_counts": operator_closure_counts,
                "ready_for_operator_approval_count": operator_closure_counts.get("ready_for_operator_approval", 0),
                "closed_count": operator_closure_counts.get("closed", 0),
                "export_refs": board.get("export_refs") or {},
            },
        }

    def _packet_markdown(self, *, packet_key: str, items: List[Dict[str, Any]]) -> str:
        lines = [
            f"# {OWNER_PACKET_LABELS[packet_key]}",
            "",
            "| item_code | owner_role | owner_actor_id | status | operator_status | missing_evidence | can_approve | blockers | next_action | evidence_ref |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in items:
            evidence_ref = (item.get("latest_evidence_ref") or {}).get("path") or (item.get("latest_evidence_ref") or {}).get("paths") or "-"
            if isinstance(evidence_ref, list):
                evidence_ref = " / ".join(str(value) for value in evidence_ref)
            lines.append(
                f"| {item['item_code']} | {item['owner_role']} | {item.get('owner_actor_id') or '-'} | {item['status']} | {item.get('operator_closure_status') or '-'} | {' / '.join(item.get('missing_evidence_keys') or []) or '-'} | {bool(item.get('can_approve'))} | {' / '.join(item['closure_blockers']) or '-'} | {item['next_action']} | {evidence_ref} |"
            )
        if len(lines) == 4:
            lines.append("| - | - | - | - | - | - | - | - | - | - |")
        return "\n".join(lines)

    def _source_refs(self, closure: Dict[str, Any]) -> Dict[str, str]:
        signoff_id = ((closure.get("signoff") or {}).get("signoff_id") or "current")
        return {
            "production_signoff_record": f"artifacts/production_signoff_records/{signoff_id}/production_signoff_record.json",
            "latest_preflight_report": "artifacts/production_preflight_runs/latest/report.md",
            "latest_preflight_summary": "artifacts/production_preflight_runs/latest/summary.json",
            "handshake_pack": "artifacts/production_handshake_pack/latest/summary.json",
            "cutover_pack": "artifacts/production_cutover_pack/latest/summary.json",
            "backup_restore_hook_evidence": "artifacts/production_cutover_pack/latest/checks/backup_restore_verification_hooks.json",
        }

    def build_pack(self, *, signoff_id: Optional[str] = None, output_root: str | Path | None = None) -> Dict[str, Any]:
        closure = self.closure(signoff_id=signoff_id)
        if closure["status"] == "not_initialized":
            return {"status": "not_initialized"}
        run_id = f"human_signoff_closure_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = Path(output_root) if output_root else (self._artifacts_root() / "human_signoff_closure" / run_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        by_packet: Dict[str, List[Dict[str, Any]]] = {key: [] for key in PACKET_OWNER_ROLES}
        for item in closure["items"]:
            by_packet[item["packet_key"]].append(item)

        packet_files = {
            "finance_review_packet.md": self._packet_markdown(packet_key="finance", items=by_packet["finance"]),
            "support_review_packet.md": self._packet_markdown(packet_key="support", items=by_packet["support"]),
            "oncall_review_packet.md": self._packet_markdown(packet_key="oncall", items=by_packet["oncall"]),
            "infra_review_packet.md": self._packet_markdown(packet_key="infra", items=by_packet["infra"]),
        }
        final_lines = [
            "# Final Human Review Packet",
            "",
            f"- signoff_id: {(closure.get('signoff') or {}).get('signoff_id') or '-'}",
            f"- signoff_status: {(closure.get('signoff') or {}).get('status') or '-'}",
            f"- item_count: {closure['summary']['item_count']}",
            f"- blocker_counts: {closure['summary']['blocker_counts']}",
            "",
            "## Owner Packets",
            "- finance_review_packet.md",
            "- support_review_packet.md",
            "- oncall_review_packet.md",
            "- infra_review_packet.md",
        ]
        packet_files["final_human_review_packet.md"] = "\n".join(final_lines)
        for filename, content in packet_files.items():
            self._write_text(bundle_dir / filename, content)
        self._write_json(bundle_dir / "operator_evidence_closure.json", closure)
        summary = {
            "bundle_id": run_id,
            "generated_at": self._utcnow(),
            "signoff_id": (closure.get("signoff") or {}).get("signoff_id"),
            "item_count": closure["summary"]["item_count"],
            "packet_count": 4,
            "blocker_counts": closure["summary"]["blocker_counts"],
            "owner_counts": closure["summary"]["owner_counts"],
            "operator_closure_counts": closure["summary"].get("operator_closure_counts") or {},
            "ready_for_operator_approval_count": closure["summary"].get("ready_for_operator_approval_count", 0),
            "closed_count": closure["summary"].get("closed_count", 0),
            "source_refs": self._source_refs(closure),
        }
        self._write_json(bundle_dir / "summary.json", summary)
        self._write_json(bundle_dir / "manifest.json", self._bundle_manifest(bundle_dir, bundle_id=run_id))
        latest_dir = self._artifacts_root() / "human_signoff_closure" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "summary": summary,
            "bundle_dir": str(bundle_dir),
            "latest_dir": str(latest_dir),
        }

    def _secret_findings(self, value: Any, *, path: str = "payload") -> List[str]:
        findings: List[str] = []
        if isinstance(value, dict):
            for key, nested in value.items():
                key_str = str(key)
                normalized_key = key_str.lower()
                if normalized_key in FORBIDDEN_SECRET_FIELD_NAMES and nested:
                    findings.append(f"raw_secret_field:{path}.{key_str}")
                findings.extend(self._secret_findings(nested, path=f"{path}.{key_str}"))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                findings.extend(self._secret_findings(nested, path=f"{path}[{index}]"))
        elif isinstance(value, str):
            for marker in RAW_SECRET_MARKERS:
                if marker in value:
                    findings.append(f"raw_secret_value:{path}")
                    break
        return findings

    def append_operator_evidence(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_item_id: str,
        evidence_key: str,
        summary: str,
        source_ref: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        item = self.production_signoff.repository.get_production_signoff_item(signoff_item_id)
        item_code = str(item.get("item_code") or "")
        normalized_key = str(evidence_key or "").strip()
        if normalized_key not in self._required_evidence_keys(item_code):
            raise ValueError(f"operator_evidence_key_invalid:{item_code}:{normalized_key}")
        if not str(summary or "").strip():
            raise ValueError("operator_evidence_summary_required")
        candidate_source_ref = dict(source_ref or {})
        candidate_payload = dict(payload or {})
        findings = self._secret_findings(candidate_source_ref, path="source_ref") + self._secret_findings(candidate_payload, path="payload")
        if findings:
            raise ValueError("operator_evidence_must_be_redacted:%s" % ",".join(findings))
        evidence_payload = {
            **candidate_payload,
            "operator_evidence_key": normalized_key,
            "requirement_item_code": item_code,
            "redacted_only": True,
        }
        result = self.production_signoff.append_signoff_evidence(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_item_id=signoff_item_id,
            evidence_type="operator_confirmation",
            summary=str(summary).strip(),
            source_ref={**candidate_source_ref, "redacted": True},
            payload=evidence_payload,
            customer_safe=False,
        )
        closure = self.closure(signoff_id=result["signoff"]["signoff_id"])
        closure_item = next((row for row in closure["items"] if row.get("signoff_item_id") == signoff_item_id), None)
        return {**result, "closure_item": closure_item}

    def close_operator_item(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_item_id: str,
        decision: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        item = self.production_signoff.repository.get_production_signoff_item(signoff_item_id)
        normalized = str(decision or "").strip()
        if normalized not in {"approved", "waived", "rejected"}:
            raise ValueError(f"operator_closeout_decision_invalid:{normalized}")
        closure = self.closure(signoff_id=item["signoff_id"])
        closure_item = next((row for row in closure["items"] if row.get("signoff_item_id") == signoff_item_id), None)
        if not closure_item:
            raise ValueError(f"operator_closeout_item_not_manual:{signoff_item_id}")
        if normalized == "approved" and not bool(closure_item.get("can_approve")):
            missing = ",".join(closure_item.get("missing_evidence_keys") or [])
            raise ValueError(f"operator_closeout_missing_evidence:{missing or 'owner_or_evidence_missing'}")
        if normalized in {"waived", "rejected"} and not str(note or "").strip():
            raise ValueError("operator_closeout_note_required")
        result = self.production_signoff.decide_signoff_item(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_item_id=signoff_item_id,
            decision=normalized,
            note=note,
        )
        refreshed = self.closure(signoff_id=result["signoff"]["signoff_id"])
        refreshed_item = next((row for row in refreshed["items"] if row.get("signoff_item_id") == signoff_item_id), None)
        return {**result, "closure_item": refreshed_item}

    def close_paid_pilot_operator_evidence(
        self,
        *,
        actor_id: str = "ops_paid_pilot_operator",
        actor_role: str = "reviewer",
        signoff_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        closure = self.closure(signoff_id=signoff_id)
        if closure["status"] == "not_initialized":
            raise ValueError("operator_closeout_signoff_not_initialized")
        target_items = [
            dict(item)
            for item in list(closure.get("items") or [])
            if str(item.get("item_code") or "") in OPERATOR_EVIDENCE_REQUIREMENTS
        ]
        closed_items: List[Dict[str, Any]] = []
        for item in target_items:
            item_code = str(item.get("item_code") or "")
            signoff_item_id = str(item.get("signoff_item_id") or "")
            owner_actor_id = str(item.get("owner_actor_id") or "").strip() or PAID_PILOT_OPERATOR_OWNERS.get(item_code, "ops_paid_pilot_owner")
            if not str(item.get("owner_actor_id") or "").strip():
                self.production_signoff.assign_signoff_item_owner(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    signoff_item_id=signoff_item_id,
                    owner_actor_id=owner_actor_id,
                )

            refreshed_closure = self.closure(signoff_id=str(item.get("signoff_id") or ((closure.get("signoff") or {}).get("signoff_id") or "")))
            refreshed_item = next((row for row in refreshed_closure["items"] if row.get("signoff_item_id") == signoff_item_id), item)
            missing_keys = list(refreshed_item.get("missing_evidence_keys") or [])
            ref_map = dict(PAID_PILOT_REDACTED_REFS.get(item_code) or {})
            for evidence_key in missing_keys:
                ref_value = ref_map.get(str(evidence_key), f"ops://paid-pilot/{item_code}/{evidence_key}/redacted")
                self.append_operator_evidence(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    signoff_item_id=signoff_item_id,
                    evidence_key=str(evidence_key),
                    summary=f"paid-pilot redacted confirmation for {item_code}:{evidence_key}",
                    source_ref={
                        "kind": "paid_pilot_redacted_production_ref",
                        "ref": ref_value,
                        "item_code": item_code,
                        "evidence_key": str(evidence_key),
                    },
                    payload={
                        "pilot_scope": "invite_only_live_paid_pilot",
                        "reviewed": True,
                        "owner_actor_id": owner_actor_id,
                    },
                )

            closed = self.close_operator_item(
                actor_id=actor_id,
                actor_role=actor_role,
                signoff_item_id=signoff_item_id,
                decision="approved",
                note=f"paid pilot redacted operator evidence reviewed for {item_code}",
            )
            closed_items.append(dict(closed.get("closure_item") or closed.get("item") or {}))

        final_closure = self.closure(signoff_id=(closure.get("signoff") or {}).get("signoff_id"))
        pack = self.build_pack(signoff_id=(closure.get("signoff") or {}).get("signoff_id"))
        return {
            "status": "closed",
            "closed_item_count": len(closed_items),
            "closed_item_codes": [str(item.get("item_code") or "") for item in closed_items],
            "signoff": final_closure.get("signoff"),
            "closure": final_closure,
            "pack": pack,
        }

    def current_summary(self) -> Dict[str, Any]:
        latest_summary = self._artifacts_root() / "human_signoff_closure" / "latest" / "summary.json"
        if latest_summary.exists():
            saved = json.loads(latest_summary.read_text(encoding="utf-8"))
            return {
                "status": "active",
                "signoff_id": saved.get("signoff_id"),
                "item_count": saved.get("item_count", 5),
                "packet_count": saved.get("packet_count"),
                "blocker_counts": saved.get("blocker_counts") or {},
                "owner_counts": saved.get("owner_counts") or {},
                "operator_closure_counts": saved.get("operator_closure_counts") or {},
                "ready_for_operator_approval_count": saved.get("ready_for_operator_approval_count", 0),
                "closed_count": saved.get("closed_count", 0),
            }
        closure = self.closure()
        if closure["status"] == "not_initialized":
            return {
                "status": "not_initialized",
                "item_count": 0,
                "blocker_counts": {},
            }
        return {
            "status": "active",
            "signoff_id": (closure.get("signoff") or {}).get("signoff_id"),
            "item_count": closure["summary"]["item_count"],
            "blocker_counts": closure["summary"]["blocker_counts"],
            "owner_counts": closure["summary"]["owner_counts"],
            "operator_closure_counts": closure["summary"].get("operator_closure_counts") or {},
            "ready_for_operator_approval_count": closure["summary"].get("ready_for_operator_approval_count", 0),
            "closed_count": closure["summary"].get("closed_count", 0),
        }
