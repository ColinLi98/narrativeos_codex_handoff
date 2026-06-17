from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .commercial_audit import CommercialAuditService
from ..persistence.repositories import SQLAlchemyPlatformRepository


DEFAULT_OWNER_ROLE_MAP = {
    "billing_005": "stripe_owner",
    "webhook_001": "infra_owner",
    "security_003": "security_owner",
    "operations_003": "support_finance_owner",
    "deploy_002": "db_owner",
}

APPROVED_ITEM_STATUSES = {"approved", "waived"}
PENDING_ITEM_STATUSES = {"pending", "ready_for_review"}
REJECTED_ITEM_STATUSES = {"rejected"}


class ProductionSignoffService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        audit_service: CommercialAuditService,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.audit = audit_service
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[3])

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _utcnow_iso(self) -> str:
        return self._utcnow().isoformat()

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _default_due_at(self, *, due_in_days: int) -> str:
        return (self._utcnow() + timedelta(days=max(1, int(due_in_days or 1)))).isoformat()

    def _artifacts_root(self) -> Path:
        return self.base_dir / "artifacts"

    def _load_json_artifact(self, relative_path: str) -> Dict[str, Any]:
        path = self.base_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"missing_artifact:{relative_path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _latest_go_live_checklist(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_go_live_checklist/latest/go_live_checklist.json")

    def _latest_manual_signoff_sheet(self) -> Dict[str, Any]:
        return self._load_json_artifact("artifacts/production_manual_signoff/latest/manual_signoff_sheet.json")

    def _next_due_item(self, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        pending = [item for item in items if str(item.get("status") or "") in PENDING_ITEM_STATUSES]
        if not pending:
            return None
        pending.sort(key=lambda item: (self._parse_dt(item.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc), str(item.get("item_code") or "")))
        return pending[0]

    def _rollup(self, items: List[Dict[str, Any]], cutover_windows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        approved_count = sum(1 for item in items if str(item.get("status") or "") in APPROVED_ITEM_STATUSES)
        pending_count = sum(1 for item in items if str(item.get("status") or "") in PENDING_ITEM_STATUSES)
        rejected_count = sum(1 for item in items if str(item.get("status") or "") in REJECTED_ITEM_STATUSES)
        total_count = len(items)
        manual_items = [item for item in items if bool((item.get("item_payload_json") or {}).get("requires_manual_confirmation"))]
        approved_manual_count = sum(1 for item in manual_items if str(item.get("status") or "") in APPROVED_ITEM_STATUSES)
        next_due_item = self._next_due_item(items)
        planned_cutover = None
        if cutover_windows:
            ordered = sorted(
                cutover_windows,
                key=lambda item: (self._parse_dt(item.get("starts_at")) or datetime.max.replace(tzinfo=timezone.utc), str(item.get("cutover_window_id") or "")),
            )
            planned_cutover = ordered[0]
        overall_status = "draft"
        if rejected_count > 0:
            overall_status = "blocked"
        elif total_count == 0:
            overall_status = "draft"
        elif manual_items and approved_manual_count == len(manual_items):
            overall_status = "fully_signed"
        elif approved_manual_count > 0:
            overall_status = "partially_signed"
        else:
            overall_status = "in_review"
        return {
            "status": overall_status,
            "item_count": total_count,
            "approved_item_count": approved_count,
            "pending_item_count": pending_count,
            "rejected_item_count": rejected_count,
            "manual_item_count": len(manual_items),
            "approved_manual_item_count": approved_manual_count,
            "next_due_item": next_due_item,
            "planned_cutover_window": planned_cutover,
        }

    def _owner_role_for_code(self, item_code: str) -> str:
        return DEFAULT_OWNER_ROLE_MAP.get(str(item_code or ""), "ops_owner")

    def _initialize_item_records(
        self,
        *,
        signoff_id: str,
        due_in_days: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        checklist = self._latest_go_live_checklist()
        manual_sheet = self._latest_manual_signoff_sheet()
        manual_by_code = {str(item.get("item_id") or ""): dict(item or {}) for item in list(manual_sheet.get("items") or [])}
        created_items: List[Dict[str, Any]] = []
        created_evidence: List[Dict[str, Any]] = []
        for source_item in list(checklist.get("items") or []):
            item_code = str(source_item.get("item_id") or "")
            manual_entry = manual_by_code.get(item_code, {})
            requires_manual = bool(source_item.get("requires_manual_confirmation"))
            status = "pending" if requires_manual else "approved"
            approved_at = None if requires_manual else self._utcnow_iso()
            due_at = self._default_due_at(due_in_days=due_in_days) if requires_manual else None
            item_payload = {
                "source_status": source_item.get("status"),
                "source_evidence": source_item.get("evidence"),
                "source_notes": source_item.get("notes"),
                "requires_manual_confirmation": requires_manual,
                "manual_prompt": manual_entry.get("prompt"),
                "manual_sheet_status": manual_entry.get("status"),
            }
            item = self.repository.save_production_signoff_item(
                {
                    "signoff_id": signoff_id,
                    "item_code": item_code,
                    "category": source_item["category"],
                    "label": source_item["label"],
                    "owner_role": self._owner_role_for_code(item_code),
                    "owner_actor_id": None,
                    "due_at": due_at,
                    "status": status,
                    "decision_note": None if requires_manual else "seeded_from_go_live_checklist",
                    "approved_at": approved_at,
                    "evidence_count": 0,
                    "item_payload": item_payload,
                }
            )
            created_items.append(item)
            evidence = self.repository.save_production_signoff_evidence(
                {
                    "signoff_id": signoff_id,
                    "signoff_item_id": item["signoff_item_id"],
                    "evidence_type": "artifact_ref",
                    "source_ref": {"path": str(source_item.get("evidence") or "")},
                    "summary": f"seeded:{item_code}",
                    "customer_safe": False,
                    "payload": {"source_item": source_item, "manual_entry": manual_entry},
                }
            )
            created_evidence.append(evidence)
            item = self.repository.save_production_signoff_item({**item, "item_payload_json": item["item_payload_json"], "evidence_count": 1})
            created_items[-1] = item
        return created_items, created_evidence

    def _audit(self, *, actor_id: str, actor_role: str, signoff_id: str, action_type: str, payload: Dict[str, Any]) -> None:
        self.audit.record_audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            account_id=None,
            object_type="production_signoff",
            object_id=signoff_id,
            action_type=action_type,
            source_surface="ops",
            customer_visible_payload={},
            internal_payload=payload,
        )

    def initialize_signoff_run(
        self,
        *,
        actor_id: str,
        actor_role: str,
        launch_label: Optional[str] = None,
        due_in_days: int = 2,
    ) -> Dict[str, Any]:
        checklist = self._latest_go_live_checklist()
        manual_sheet = self._latest_manual_signoff_sheet()
        resolved_label = str(launch_label or f"production_launch_{self._utcnow().strftime('%Y%m%d')}").strip()
        signoff = self.repository.save_production_signoff(
            {
                "launch_label": resolved_label,
                "status": "draft",
                "source_go_live_checklist_id": checklist.get("checklist_id"),
                "source_manual_signoff_bundle_id": "latest_manual_signoff_sheet",
                "rollup_summary": {},
            }
        )
        items, evidence = self._initialize_item_records(signoff_id=signoff["signoff_id"], due_in_days=due_in_days)
        rollup = self._rollup(items)
        signoff = self.repository.save_production_signoff({**signoff, "status": rollup["status"], "rollup_summary_json": rollup})
        result = {
            "signoff": signoff,
            "items": items,
            "evidence": evidence,
            "source_checklist_id": checklist.get("checklist_id"),
            "source_manual_signoff_count": len(list(manual_sheet.get("items") or [])),
        }
        self._audit(actor_id=actor_id, actor_role=actor_role, signoff_id=signoff["signoff_id"], action_type="production_signoff_initialized", payload=result)
        return result

    def _refresh_signoff_rollup(self, signoff_id: str) -> Dict[str, Any]:
        signoff = self.repository.get_production_signoff(signoff_id)
        items = self.repository.list_production_signoff_items(signoff_id=signoff_id)
        cutover_windows = self.repository.list_production_cutover_windows(signoff_id=signoff_id)
        rollup = self._rollup(items, cutover_windows=cutover_windows)
        return self.repository.save_production_signoff({**signoff, "status": rollup["status"], "rollup_summary_json": rollup})

    def list_signoffs(self, *, limit: int = 25) -> Dict[str, Any]:
        signoffs = self.repository.list_production_signoffs(limit=limit)
        current = signoffs[0] if signoffs else None
        return {
            "signoffs": signoffs,
            "current_signoff": current,
            "summary": {
                "signoff_count": len(signoffs),
                "current_signoff_id": (current or {}).get("signoff_id"),
            },
        }

    def signoff_detail(self, *, signoff_id: str) -> Dict[str, Any]:
        signoff = self.repository.get_production_signoff(signoff_id)
        items = self.repository.list_production_signoff_items(signoff_id=signoff_id)
        evidence = self.repository.list_production_signoff_evidence(signoff_id=signoff_id, limit=500)
        cutover_windows = self.repository.list_production_cutover_windows(signoff_id=signoff_id, limit=100)
        rollup = self._rollup(items, cutover_windows=cutover_windows)
        signoff = self.repository.save_production_signoff({**signoff, "status": rollup["status"], "rollup_summary_json": rollup})
        latest_evidence_by_item: Dict[str, Dict[str, Any]] = {}
        for item in evidence:
            key = str(item.get("signoff_item_id") or "")
            if key and key not in latest_evidence_by_item:
                latest_evidence_by_item[key] = item
        item_details = []
        for item in items:
            item_details.append(
                {
                    **item,
                    "latest_evidence": latest_evidence_by_item.get(str(item.get("signoff_item_id") or "")),
                }
            )
        return {
            "signoff": signoff,
            "rollup_summary": rollup,
            "items": item_details,
            "evidence": evidence,
            "cutover_windows": cutover_windows,
            "export_refs": {
                "record_dir": str(self._artifacts_root() / "production_signoff_records" / signoff_id),
            },
        }

    def assign_signoff_item_owner(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_item_id: str,
        owner_actor_id: Optional[str],
    ) -> Dict[str, Any]:
        item = self.repository.get_production_signoff_item(signoff_item_id)
        updated = self.repository.save_production_signoff_item(
            {
                **item,
                "item_payload_json": item.get("item_payload_json", {}),
                "owner_actor_id": str(owner_actor_id or "").strip() or None,
            }
        )
        signoff = self._refresh_signoff_rollup(updated["signoff_id"])
        self._audit(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_id=updated["signoff_id"],
            action_type="production_signoff_item_owner_assigned",
            payload={"signoff_item_id": signoff_item_id, "owner_actor_id": updated.get("owner_actor_id")},
        )
        return {"item": updated, "signoff": signoff}

    def append_signoff_evidence(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_item_id: str,
        evidence_type: str,
        summary: Optional[str],
        source_ref: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        customer_safe: bool = False,
    ) -> Dict[str, Any]:
        item = self.repository.get_production_signoff_item(signoff_item_id)
        evidence = self.repository.save_production_signoff_evidence(
            {
                "signoff_id": item["signoff_id"],
                "signoff_item_id": signoff_item_id,
                "evidence_type": evidence_type,
                "summary": summary,
                "source_ref": dict(source_ref or {}),
                "payload": dict(payload or {}),
                "customer_safe": customer_safe,
            }
        )
        updated_item = self.repository.save_production_signoff_item(
            {
                **item,
                "item_payload_json": item.get("item_payload_json", {}),
                "evidence_count": int(item.get("evidence_count") or 0) + 1,
            }
        )
        signoff = self._refresh_signoff_rollup(updated_item["signoff_id"])
        self._audit(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_id=updated_item["signoff_id"],
            action_type="production_signoff_evidence_appended",
            payload={"signoff_item_id": signoff_item_id, "evidence_id": evidence["evidence_id"], "evidence_type": evidence_type},
        )
        return {"item": updated_item, "evidence": evidence, "signoff": signoff}

    def decide_signoff_item(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_item_id: str,
        decision: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        item = self.repository.get_production_signoff_item(signoff_item_id)
        normalized = str(decision or "").strip()
        if normalized not in {"approved", "rejected", "waived", "ready_for_review"}:
            raise ValueError("production_signoff_decision_invalid:%s" % normalized)
        updated = self.repository.save_production_signoff_item(
            {
                **item,
                "item_payload_json": item.get("item_payload_json", {}),
                "status": normalized,
                "decision_note": note,
                "approved_at": self._utcnow_iso() if normalized in APPROVED_ITEM_STATUSES else None,
            }
        )
        signoff = self._refresh_signoff_rollup(updated["signoff_id"])
        self._audit(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_id=updated["signoff_id"],
            action_type="production_signoff_item_decided",
            payload={"signoff_item_id": signoff_item_id, "decision": normalized, "note": note},
        )
        return {"item": updated, "signoff": signoff}

    def mark_cutover_window(
        self,
        *,
        actor_id: str,
        actor_role: str,
        signoff_id: str,
        launch_wave: str,
        target_environment: str,
        starts_at: Optional[str],
        ends_at: Optional[str],
        rollback_owner_role: Optional[str],
        status: str = "planned",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        window = self.repository.save_production_cutover_window(
            {
                "signoff_id": signoff_id,
                "launch_wave": launch_wave,
                "target_environment": target_environment,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "rollback_owner_role": rollback_owner_role,
                "status": status,
                "cutover_payload": dict(payload or {}),
            }
        )
        signoff = self._refresh_signoff_rollup(signoff_id)
        self._audit(
            actor_id=actor_id,
            actor_role=actor_role,
            signoff_id=signoff_id,
            action_type="production_cutover_window_marked",
            payload={"cutover_window_id": window["cutover_window_id"], "status": status},
        )
        return {"cutover_window": window, "signoff": signoff}

    def export_signoff_record(self, *, signoff_id: str) -> Dict[str, Any]:
        detail = self.signoff_detail(signoff_id=signoff_id)
        output_dir = self._artifacts_root() / "production_signoff_records" / signoff_id
        output_dir.mkdir(parents=True, exist_ok=True)
        record_json_path = output_dir / "production_signoff_record.json"
        record_md_path = output_dir / "production_signoff_record.md"
        items_csv_path = output_dir / "production_signoff_items.csv"
        record_json_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        md_lines = [
            "# Production Signoff Record",
            "",
            f"- signoff_id: {detail['signoff']['signoff_id']}",
            f"- launch_label: {detail['signoff']['launch_label']}",
            f"- status: {detail['signoff']['status']}",
            f"- pending: {detail['rollup_summary']['pending_item_count']}",
            f"- approved: {detail['rollup_summary']['approved_item_count']}",
            f"- rejected: {detail['rollup_summary']['rejected_item_count']}",
            "",
            "## Items",
        ]
        for item in detail["items"]:
            md_lines.extend(
                [
                    f"### {item['item_code']} — {item['label']}",
                    f"- status: {item['status']}",
                    f"- owner_role: {item['owner_role']}",
                    f"- owner_actor_id: {item.get('owner_actor_id') or '-'}",
                    f"- due_at: {item.get('due_at') or '-'}",
                    f"- evidence_count: {item.get('evidence_count') or 0}",
                    f"- decision_note: {item.get('decision_note') or '-'}",
                    f"- latest_evidence: {(item.get('latest_evidence') or {}).get('summary') or '-'}",
                    "",
                ]
            )
        record_md_path.write_text("\n".join(md_lines), encoding="utf-8")
        with items_csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["signoff_item_id", "item_code", "category", "label", "owner_role", "owner_actor_id", "due_at", "status", "decision_note", "approved_at", "evidence_count"],
            )
            writer.writeheader()
            for item in detail["items"]:
                writer.writerow({key: item.get(key) for key in writer.fieldnames})
        return {
            "signoff": detail["signoff"],
            "export_refs": {
                "record_json": str(record_json_path),
                "record_md": str(record_md_path),
                "items_csv": str(items_csv_path),
            },
        }

    def current_signoff_summary(self) -> Optional[Dict[str, Any]]:
        signoffs = self.repository.list_production_signoffs(limit=1)
        if not signoffs:
            return None
        signoff = signoffs[0]
        items = self.repository.list_production_signoff_items(signoff_id=signoff["signoff_id"])
        cutover_windows = self.repository.list_production_cutover_windows(signoff_id=signoff["signoff_id"], limit=25)
        rollup = self._rollup(items, cutover_windows=cutover_windows)
        return {
            "signoff_id": signoff["signoff_id"],
            "launch_label": signoff["launch_label"],
            "status": rollup["status"],
            "pending_item_count": rollup["pending_item_count"],
            "approved_item_count": rollup["approved_item_count"],
            "rejected_item_count": rollup["rejected_item_count"],
            "next_due_item": rollup["next_due_item"],
            "planned_cutover_window": rollup["planned_cutover_window"],
        }
