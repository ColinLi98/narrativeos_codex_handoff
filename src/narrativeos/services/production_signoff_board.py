from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .production_signoff import APPROVED_ITEM_STATUSES, PENDING_ITEM_STATUSES, REJECTED_ITEM_STATUSES, ProductionSignoffService


class ProductionSignoffBoardService:
    def __init__(self, *, production_signoff_service: ProductionSignoffService) -> None:
        self.production_signoff = production_signoff_service

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

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

    def _is_seed_only(self, item: Dict[str, Any], evidence_rows: List[Dict[str, Any]]) -> bool:
        relevant = [row for row in evidence_rows if str(row.get("signoff_item_id") or "") == str(item.get("signoff_item_id") or "")]
        if not relevant:
            return True
        return all(str(row.get("summary") or "").startswith("seeded:") for row in relevant)

    def _blockers_for_item(self, item: Dict[str, Any], evidence_rows: List[Dict[str, Any]]) -> List[str]:
        blockers: List[str] = []
        requires_manual = bool((item.get("item_payload_json") or {}).get("requires_manual_confirmation"))
        status = str(item.get("status") or "")
        due_at = self._parse_dt(item.get("due_at"))
        is_actionable = requires_manual or status in PENDING_ITEM_STATUSES or status in REJECTED_ITEM_STATUSES
        if is_actionable and not str(item.get("owner_actor_id") or "").strip():
            blockers.append("owner_missing")
        if is_actionable and not item.get("due_at"):
            blockers.append("due_missing")
        if status in PENDING_ITEM_STATUSES and due_at and due_at < self._utcnow():
            blockers.append("overdue")
        if requires_manual and status not in APPROVED_ITEM_STATUSES:
            blockers.append("manual_confirmation_pending")
        if is_actionable and self._is_seed_only(item, evidence_rows):
            blockers.append("no_actionable_evidence_beyond_seed")
        if status in REJECTED_ITEM_STATUSES:
            blockers.append("rejected")
        return blockers

    def board(self, *, signoff_id: Optional[str] = None) -> Dict[str, Any]:
        if signoff_id:
            detail = self.production_signoff.signoff_detail(signoff_id=signoff_id)
        else:
            current = self.production_signoff.current_signoff_summary()
            if not current:
                return {
                    "board_status": "not_initialized",
                    "current_signoff": None,
                    "items": [],
                    "summary": {
                        "item_count": 0,
                        "pending_item_count": 0,
                        "approved_item_count": 0,
                        "rejected_item_count": 0,
                        "overdue_count": 0,
                        "blocker_counts": {},
                        "owner_status_buckets": {},
                    },
                    "overdue_items": [],
                    "export_refs": {},
                }
            detail = self.production_signoff.signoff_detail(signoff_id=current["signoff_id"])
        evidence_rows = list(detail.get("evidence") or [])
        items_with_blockers: List[Dict[str, Any]] = []
        blocker_counts: Counter[str] = Counter()
        owner_status_buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: Counter())
        overdue_items: List[Dict[str, Any]] = []
        for item in list(detail.get("items") or []):
            blockers = self._blockers_for_item(item, evidence_rows)
            blocker_counts.update(blockers)
            bucket_key = str(item.get("owner_role") or "unassigned")
            owner_status_buckets[bucket_key][str(item.get("status") or "unknown")] += 1
            materialized = {
                **item,
                "blockers": blockers,
                "has_blockers": bool(blockers),
                "latest_evidence_ref": ((item.get("latest_evidence") or {}).get("source_ref_json") or {}),
            }
            items_with_blockers.append(materialized)
            if "overdue" in blockers:
                overdue_items.append(materialized)
        return {
            "board_status": "active",
            "current_signoff": detail.get("signoff"),
            "items": items_with_blockers,
            "summary": {
                "item_count": len(items_with_blockers),
                "pending_item_count": sum(1 for item in items_with_blockers if str(item.get("status") or "") in PENDING_ITEM_STATUSES),
                "approved_item_count": sum(1 for item in items_with_blockers if str(item.get("status") or "") in APPROVED_ITEM_STATUSES),
                "rejected_item_count": sum(1 for item in items_with_blockers if str(item.get("status") or "") in REJECTED_ITEM_STATUSES),
                "overdue_count": len(overdue_items),
                "blocker_counts": dict(blocker_counts),
                "owner_status_buckets": {key: dict(value) for key, value in owner_status_buckets.items()},
                "linked_cutover_window": detail.get("rollup_summary", {}).get("planned_cutover_window"),
                "next_due_item": detail.get("rollup_summary", {}).get("next_due_item"),
            },
            "overdue_items": overdue_items,
            "export_refs": detail.get("export_refs") or {},
        }

    def current_board_summary(self) -> Optional[Dict[str, Any]]:
        board = self.board()
        if board["board_status"] == "not_initialized":
            return None
        signoff = board.get("current_signoff") or {}
        summary = board.get("summary") or {}
        return {
            "signoff_id": signoff.get("signoff_id"),
            "status": signoff.get("status"),
            "pending_item_count": summary.get("pending_item_count", 0),
            "approved_item_count": summary.get("approved_item_count", 0),
            "rejected_item_count": summary.get("rejected_item_count", 0),
            "overdue_count": summary.get("overdue_count", 0),
            "blocker_counts": summary.get("blocker_counts") or {},
            "next_due_item": summary.get("next_due_item"),
            "linked_cutover_window": summary.get("linked_cutover_window"),
            "export_refs": board.get("export_refs") or {},
        }
