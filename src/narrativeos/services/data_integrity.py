from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select

from ..persistence.db import (
    ChapterRow,
    RouteChoiceRow,
    SessionRow,
    SubscriptionRow,
    ReviewRecordRow,
    WorldRow,
    WorldVersionRow,
    EntitlementRow,
    BillingCheckoutSessionRow,
)
from ..persistence.migrations import inspect_schema_lifecycle
from ..persistence.repositories import DEFAULT_DATABASE_URL, SQLAlchemyPlatformRepository
from ..persistence.db import utcnow_iso


SAFE_REPAIR_ACTIONS = [
    "reconcile_session_chapter_pointers",
    "prune_orphan_route_choices",
]

HOTSPOT_INDEXES: Dict[str, List[Dict[str, Any]]] = {
    "sessions": [
        {"name": "idx_sessions_world_version_updated_at", "columns": ["world_version_id", "updated_at"], "reason": "reader and ops session recency scans"},
        {"name": "idx_sessions_reader_updated_at", "columns": ["reader_id", "updated_at"], "reason": "reader/account session lookups"},
        {"name": "idx_sessions_status_updated_at", "columns": ["status", "updated_at"], "reason": "stale/running session diagnostics"},
    ],
    "chapters": [
        {"name": "idx_chapters_session_chapter_index", "columns": ["session_id", "chapter_index"], "reason": "step replay and latest chapter scans"},
        {"name": "idx_chapters_world_version_created_at", "columns": ["world_version_id", "created_at"], "reason": "world-version chapter evaluation scans"},
    ],
    "review_records": [
        {"name": "idx_review_records_asset_type_status_updated_at", "columns": ["asset_type", "status", "updated_at"], "reason": "ops/governance status queues"},
        {"name": "idx_review_records_asset_type_asset_id_updated_at", "columns": ["asset_type", "asset_id", "updated_at"], "reason": "asset timeline drill-down"},
        {"name": "idx_review_records_reviewer_updated_at", "columns": ["reviewer_id", "updated_at"], "reason": "reviewer workload/history"},
    ],
    "subscriptions": [
        {"name": "idx_subscriptions_account_status_updated_at", "columns": ["account_id", "status", "updated_at"], "reason": "account billing and active-subscription scans"},
    ],
    "usage_meters": [
        {"name": "idx_usage_meters_account_created_at", "columns": ["account_id", "created_at"], "reason": "account usage timeline"},
        {"name": "idx_usage_meters_session_created_at", "columns": ["session_id", "created_at"], "reason": "session metering timeline"},
        {"name": "idx_usage_meters_world_version_created_at", "columns": ["world_version_id", "created_at"], "reason": "world-version usage aggregation"},
    ],
    "analytics_events": [
        {"name": "idx_analytics_events_event_name_occurred_at", "columns": ["event_name", "occurred_at"], "reason": "event-name correlation scans"},
        {"name": "idx_analytics_events_session_occurred_at", "columns": ["session_id", "occurred_at"], "reason": "session event replay"},
        {"name": "idx_analytics_events_world_version_occurred_at", "columns": ["world_version_id", "occurred_at"], "reason": "world-version impact tracking"},
    ],
}

REVIEW_ASSET_TABLES = {
    "world_version": WorldVersionRow,
    "world": WorldRow,
    "session": SessionRow,
    "chapter": ChapterRow,
    "subscription": SubscriptionRow,
    "entitlement": EntitlementRow,
    "billing_checkout_session": BillingCheckoutSessionRow,
}


class DataIntegrityService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _backend(self) -> str:
        return self.repository.engine.url.get_backend_name()

    def _scan_hotspot_indexes(self) -> Dict[str, Any]:
        inspector = sqlalchemy_inspect(self.repository.engine)
        table_details: List[Dict[str, Any]] = []
        missing_total = 0
        covered_total = 0
        for table_name, expected_specs in HOTSPOT_INDEXES.items():
            existing_indexes = {item.get("name"): item for item in inspector.get_indexes(table_name)}
            items: List[Dict[str, Any]] = []
            for spec in expected_specs:
                existing = existing_indexes.get(spec["name"])
                covered = existing is not None
                missing_total += 0 if covered else 1
                covered_total += 1 if covered else 0
                items.append(
                    {
                        "name": spec["name"],
                        "columns": spec["columns"],
                        "reason": spec["reason"],
                        "covered": covered,
                        "actual_columns": list(existing.get("column_names") or []) if existing else [],
                    }
                )
            table_details.append(
                {
                    "table": table_name,
                    "expected_count": len(expected_specs),
                    "covered_count": sum(1 for item in items if item["covered"]),
                    "missing_count": sum(1 for item in items if not item["covered"]),
                    "indexes": items,
                }
            )
        return {
            "expected_count": covered_total + missing_total,
            "covered_count": covered_total,
            "missing_count": missing_total,
            "status": "covered" if missing_total == 0 else "missing_indexes",
            "tables": table_details,
        }

    def _latest_chapter_by_session(self) -> Dict[str, ChapterRow]:
        latest: Dict[str, ChapterRow] = {}
        with self.repository.SessionLocal() as session:
            rows = session.execute(
                select(ChapterRow).order_by(ChapterRow.session_id.asc(), ChapterRow.chapter_index.desc(), ChapterRow.created_at.desc())
            ).scalars()
            for row in rows:
                latest.setdefault(row.session_id, row)
        return latest

    def _extract_state_after(self, chapter_row: ChapterRow) -> Dict[str, Any]:
        payload = dict(chapter_row.plan_json or {})
        step_record = dict(payload.get("step_record") or {})
        state_after = dict(step_record.get("state_after") or {})
        if "chapter_index" not in state_after:
            state_after["chapter_index"] = chapter_row.chapter_index
        return state_after

    def _scan_session_pointer_drift(self, *, limit: int = 20) -> Dict[str, Any]:
        latest_chapters = self._latest_chapter_by_session()
        items: List[Dict[str, Any]] = []
        with self.repository.SessionLocal() as session:
            rows = session.execute(select(SessionRow).order_by(SessionRow.updated_at.desc())).scalars()
            for row in rows:
                latest = latest_chapters.get(row.session_id)
                if latest is None:
                    continue
                latest_state = self._extract_state_after(latest)
                latest_index = int(latest_state.get("chapter_index") or latest.chapter_index or 0)
                session_index = int(row.chapter_index or 0)
                latest_phase = latest_state.get("story_phase")
                session_phase = row.story_phase
                state_index = int(dict(row.narrative_state_json or {}).get("chapter_index") or session_index)
                if latest_index == session_index and latest_index == state_index and (latest_phase is None or latest_phase == session_phase):
                    continue
                items.append(
                    {
                        "session_id": row.session_id,
                        "world_version_id": row.world_version_id,
                        "session_chapter_index": session_index,
                        "state_chapter_index": state_index,
                        "latest_chapter_index": latest_index,
                        "session_story_phase": session_phase,
                        "latest_story_phase": latest_phase,
                        "latest_chapter_id": latest.chapter_id,
                        "updated_at": row.updated_at,
                    }
                )
                if len(items) >= limit:
                    break
        return {
            "key": "session_pointer_drift",
            "count": len(items),
            "items": items,
            "repair_action": "reconcile_session_chapter_pointers",
        }

    def _scan_orphan_route_choices(self, *, limit: int = 20) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        with self.repository.SessionLocal() as session:
            session_ids = {item[0] for item in session.execute(select(SessionRow.session_id)).all()}
            chapter_ids = {item[0] for item in session.execute(select(ChapterRow.chapter_id)).all()}
            rows = session.execute(select(RouteChoiceRow).order_by(RouteChoiceRow.selected_at.desc())).scalars()
            for row in rows:
                missing_session = row.session_id not in session_ids
                missing_chapter = row.chapter_id not in chapter_ids
                if not missing_session and not missing_chapter:
                    continue
                reason = "missing_session_and_chapter" if missing_session and missing_chapter else ("missing_session" if missing_session else "missing_chapter")
                items.append(
                    {
                        "choice_event_id": row.choice_event_id,
                        "session_id": row.session_id,
                        "chapter_id": row.chapter_id,
                        "reason": reason,
                        "selected_at": row.selected_at,
                    }
                )
                if len(items) >= limit:
                    break
        return {
            "key": "orphan_route_choices",
            "count": len(items),
            "items": items,
            "repair_action": "prune_orphan_route_choices",
        }

    def _scan_duplicate_active_subscriptions(self, *, limit: int = 20) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        with self.repository.SessionLocal() as session:
            rows = session.execute(
                select(SubscriptionRow).where(SubscriptionRow.status.in_(["trialing", "active"])).order_by(SubscriptionRow.account_id.asc(), SubscriptionRow.updated_at.desc())
            ).scalars()
            grouped: Dict[str, List[SubscriptionRow]] = defaultdict(list)
            for row in rows:
                grouped[str(row.account_id or "")].append(row)
            for account_id, subscriptions in grouped.items():
                if len(subscriptions) <= 1:
                    continue
                items.append(
                    {
                        "account_id": account_id,
                        "active_subscription_ids": [row.subscription_id for row in subscriptions],
                        "statuses": [row.status for row in subscriptions],
                        "latest_updated_at": subscriptions[0].updated_at,
                        "reason": "multiple_trialing_or_active_subscriptions",
                    }
                )
                if len(items) >= limit:
                    break
        return {
            "key": "duplicate_active_subscriptions",
            "count": len(items),
            "items": items,
            "repair_action": None,
        }

    def _scan_review_asset_refs(self, *, limit: int = 20) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        skipped_asset_types: List[str] = []
        with self.repository.SessionLocal() as session:
            rows = session.execute(select(ReviewRecordRow).order_by(ReviewRecordRow.updated_at.desc())).scalars().all()
            present_types = {row.asset_type for row in rows}
            known_sets: Dict[str, set[str]] = {}
            for asset_type, row_cls in REVIEW_ASSET_TABLES.items():
                if asset_type not in present_types:
                    continue
                id_column = getattr(row_cls, list(row_cls.__table__.primary_key.columns)[0].name)
                known_sets[asset_type] = {str(item[0]) for item in session.execute(select(id_column)).all()}
            skipped_asset_types = sorted(present_types - set(REVIEW_ASSET_TABLES.keys()))
            for row in rows:
                if row.asset_type not in REVIEW_ASSET_TABLES:
                    continue
                if str(row.asset_id) in known_sets.get(row.asset_type, set()):
                    continue
                items.append(
                    {
                        "review_id": row.review_id,
                        "asset_type": row.asset_type,
                        "asset_id": row.asset_id,
                        "status": row.status,
                        "updated_at": row.updated_at,
                        "reason": "missing_asset_reference",
                    }
                )
                if len(items) >= limit:
                    break
        return {
            "key": "review_asset_ref_gaps",
            "count": len(items),
            "items": items,
            "skipped_asset_types": skipped_asset_types,
            "repair_action": None,
        }

    def build_summary(self, *, limit: int = 20) -> Dict[str, Any]:
        index_summary = self._scan_hotspot_indexes()
        session_drift = self._scan_session_pointer_drift(limit=limit)
        orphan_route_choices = self._scan_orphan_route_choices(limit=limit)
        duplicate_subscriptions = self._scan_duplicate_active_subscriptions(limit=limit)
        review_asset_refs = self._scan_review_asset_refs(limit=limit)

        warnings: List[str] = []
        if index_summary["missing_count"]:
            warnings.append("hotspot_indexes_missing")
        if duplicate_subscriptions["count"]:
            warnings.append("duplicate_active_subscriptions_require_manual_review")
        if review_asset_refs["count"]:
            warnings.append("review_asset_reference_gaps_present")
        if review_asset_refs["skipped_asset_types"]:
            warnings.append("some_review_asset_types_are_plan_only")

        repair_actions = [
            {
                "action": "reconcile_session_chapter_pointers",
                "safe_apply_supported": True,
                "target_count": session_drift["count"],
                "reason": "session rows can lag latest committed chapter under retries or interrupted writes",
            },
            {
                "action": "prune_orphan_route_choices",
                "safe_apply_supported": True,
                "target_count": orphan_route_choices["count"],
                "reason": "orphan route choices add noise to replay/analytics paths",
            },
        ]
        manual_backlog = [
            {
                "action": "review_duplicate_active_subscriptions",
                "target_count": duplicate_subscriptions["count"],
                "reason": "requires billing/operator decision, not auto-fix",
            },
            {
                "action": "review_missing_review_asset_refs",
                "target_count": review_asset_refs["count"],
                "reason": "review history refers to missing first-class assets",
            },
        ]
        if any(item["target_count"] for item in manual_backlog):
            status = "manual_review_required"
        elif any(item["target_count"] for item in repair_actions) or index_summary["missing_count"]:
            status = "repairable_attention"
        else:
            status = "healthy"

        return {
            "generated_at": self._utcnow(),
            "backend": self._backend(),
            "status": status,
            "schema_lifecycle": inspect_schema_lifecycle(self.repository.engine),
            "hotspot_index_summary": index_summary,
            "concurrency_summary": {
                "duplicate_step_write_strategy": "idempotent_chapter_reuse",
                "session_pointer_drift_count": session_drift["count"],
                "orphan_route_choice_count": orphan_route_choices["count"],
                "duplicate_active_subscription_count": duplicate_subscriptions["count"],
            },
            "repairable_checks": [session_drift, orphan_route_choices],
            "manual_review_checks": [duplicate_subscriptions, review_asset_refs],
            "repair_actions": repair_actions,
            "manual_backlog": manual_backlog,
            "warnings": warnings,
        }

    def _apply_reconcile_session_chapter_pointers(self, *, limit: int = 50, apply: bool = False) -> Dict[str, Any]:
        scan = self._scan_session_pointer_drift(limit=limit)
        applied = 0
        if apply and scan["items"]:
            with self.repository.SessionLocal() as session:
                for item in scan["items"]:
                    session_row = session.get(SessionRow, item["session_id"])
                    chapter_row = session.get(ChapterRow, item["latest_chapter_id"])
                    if session_row is None or chapter_row is None:
                        continue
                    state_after = self._extract_state_after(chapter_row)
                    session_row.chapter_index = int(item["latest_chapter_index"])
                    session_row.story_phase = item.get("latest_story_phase") or session_row.story_phase
                    session_row.narrative_state_json = state_after or dict(session_row.narrative_state_json or {})
                    session_row.updated_at = utcnow_iso()
                    applied += 1
                session.commit()
        return {
            "action": "reconcile_session_chapter_pointers",
            "safe_apply_supported": True,
            "planned_count": scan["count"],
            "applied_count": applied,
            "changed": applied > 0,
            "items": scan["items"],
        }

    def _apply_prune_orphan_route_choices(self, *, limit: int = 50, apply: bool = False) -> Dict[str, Any]:
        scan = self._scan_orphan_route_choices(limit=limit)
        applied = 0
        if apply and scan["items"]:
            orphan_ids = [int(item["choice_event_id"]) for item in scan["items"]]
            with self.repository.SessionLocal() as session:
                rows = session.execute(select(RouteChoiceRow).where(RouteChoiceRow.choice_event_id.in_(orphan_ids))).scalars()
                for row in rows:
                    session.delete(row)
                    applied += 1
                session.commit()
        return {
            "action": "prune_orphan_route_choices",
            "safe_apply_supported": True,
            "planned_count": scan["count"],
            "applied_count": applied,
            "changed": applied > 0,
            "items": scan["items"],
        }

    def run_repair(self, *, actions: Optional[List[str]] = None, apply: bool = False, limit: int = 50) -> Dict[str, Any]:
        selected_actions = actions or list(SAFE_REPAIR_ACTIONS)
        invalid_actions = [action for action in selected_actions if action not in SAFE_REPAIR_ACTIONS]
        before = self.build_summary(limit=min(limit, 20))
        action_results: List[Dict[str, Any]] = []
        if "reconcile_session_chapter_pointers" in selected_actions:
            action_results.append(self._apply_reconcile_session_chapter_pointers(limit=limit, apply=apply))
        if "prune_orphan_route_choices" in selected_actions:
            action_results.append(self._apply_prune_orphan_route_choices(limit=limit, apply=apply))
        after = self.build_summary(limit=min(limit, 20)) if apply else None
        return {
            "generated_at": self._utcnow(),
            "backend": self._backend(),
            "apply": apply,
            "selected_actions": selected_actions,
            "invalid_actions": invalid_actions,
            "changed": any(item["changed"] for item in action_results),
            "action_results": action_results,
            "summary_before": before,
            "summary_after": after,
        }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or repair NarrativeOS data integrity hotspots.")
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL, help="Database URL to inspect")
    parser.add_argument("--apply", action="store_true", help="Apply safe repair actions instead of dry-run")
    parser.add_argument("--action", action="append", dest="actions", help="Safe repair action to run; can be repeated")
    parser.add_argument("--limit", type=int, default=20, help="Max items per check/action")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repository = SQLAlchemyPlatformRepository(database_url=args.database_url)
    service = DataIntegrityService(repository)
    if args.actions or args.apply:
        result = service.run_repair(actions=args.actions, apply=args.apply, limit=args.limit)
    else:
        result = service.build_summary(limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
