from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .ops_quality_projection import OpsQualityProjectionService
from .ops_traceability import OpsTraceabilityService
from .review import ReviewService


class OpsReleaseWorkspaceService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        review_service: ReviewService,
        ops_traceability_service: OpsTraceabilityService,
        quality_projection_service: Optional[OpsQualityProjectionService] = None,
    ) -> None:
        self.repository = repository
        self.review = review_service
        self.traceability = ops_traceability_service
        self.quality_projection = quality_projection_service or OpsQualityProjectionService(repository)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _selected_world_version_id(self, status_payload: Dict[str, Any]) -> Optional[str]:
        for item in status_payload.get("versions", []):
            if item.get("status") in {"submitted", "draft"}:
                return item.get("world_version_id")
        return status_payload.get("published_version")

    def _release_health_status(
        self,
        *,
        status_payload: Dict[str, Any],
        history_payload: Dict[str, Any],
    ) -> str:
        checklist = dict(status_payload.get("publish_checklist_summary") or {})
        latest_trend = (history_payload.get("quality_trend") or [{}])[0]
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        release_bundle = dict(status_payload.get("release_evidence_bundle") or {})
        combined_signoff = dict(release_bundle.get("combined_signoff") or {})
        if not checklist.get("publish_ready"):
            return "blocked"
        if release_bundle and not bool(combined_signoff.get("ready", False)):
            return "watch"
        if latest_trend.get("regression_detected") or int(rollback_summary.get("total_entries") or 0) > 0:
            return "watch"
        return "ready"

    def _recommended_action(
        self,
        *,
        status_payload: Dict[str, Any],
        history_payload: Dict[str, Any],
        selected_world_version_id: Optional[str],
    ) -> str:
        checklist_summary = dict(status_payload.get("publish_checklist_summary") or {})
        release_bundle = dict(status_payload.get("release_evidence_bundle") or {})
        combined_signoff = dict(release_bundle.get("combined_signoff") or {})
        if not checklist_summary.get("publish_ready"):
            return (checklist_summary.get("next_actions") or ["inspect_publish_blockers"])[0]
        if release_bundle and not bool(combined_signoff.get("ready", False)):
            return "inspect_release_evidence_bundle"
        if selected_world_version_id and selected_world_version_id != status_payload.get("published_version"):
            return "publish_candidate"
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        if int(rollback_summary.get("total_entries") or 0) > 0:
            return "inspect_recent_rollback"
        return "observe_release_state"

    def _strategy_bundle_batch_validation_status(self, release_bundle: Dict[str, Any]) -> str:
        summary = dict(release_bundle.get("strategy_bundle_batch_validation_summary") or {})
        if not summary:
            return "not_run"
        if not bool(summary.get("available", False)):
            return "not_run"
        return str(summary.get("decision") or "not_run")

    def _publish_blockers(self, status_payload: Dict[str, Any]) -> Dict[str, Any]:
        blockers = [item for item in status_payload.get("publish_checklist", []) if not item.get("ok")]
        by_owner: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for item in blockers:
            owner = str(item.get("owner") or "unknown")
            severity = str(item.get("severity") or "unknown")
            by_owner[owner] = by_owner.get(owner, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        phase_a_gate_item = next((item for item in blockers if str(item.get("key") or "") == "phase_a_quality_gate"), None)
        phase_a_evidence = dict((phase_a_gate_item or {}).get("evidence") or {})
        content_quality_gate_item = next((item for item in blockers if str(item.get("key") or "") == "content_quality_contract_gate"), None)
        content_quality_evidence = dict((content_quality_gate_item or {}).get("evidence") or {})
        phase_a_check_labels = {
            "cross_pack_pass_rate": "Cross-pack pass rate",
            "weakest_pack_pass_rate": "Weakest pack pass rate",
            "q03_weakest_issue_share": "Q03 weakest-pack share",
            "q04_weakest_issue_share": "Q04 weakest-pack share",
            "q05_weakest_issue_share": "Q05 weakest-pack share",
            "q09_weakest_issue_share": "Q09 weakest-pack share",
        }
        content_quality_check_labels = {
            "asset_contract_coverage": "Asset contract coverage",
            "early_window_q03_q04_share": "Early window Q03/Q04 share",
            "mid_window_repeat_breach_rate": "Mid window repetition breach rate",
            "mid_window_exposition_breach_rate": "Mid window exposition breach rate",
            "late_window_q09_breach_rate": "Late window Q09 breach rate",
        }
        phase_a_failed_check_items = []
        for check in phase_a_evidence.get("checks", []) or []:
            payload = dict(check or {})
            if payload.get("ok") or payload.get("skipped"):
                continue
            phase_a_failed_check_items.append(
                {
                    "check_key": str(payload.get("key") or ""),
                    "label": phase_a_check_labels.get(str(payload.get("key") or ""), str(payload.get("key") or "")),
                    "reason": str(payload.get("reason") or ""),
                    "actual": payload.get("actual"),
                    "threshold": payload.get("threshold"),
                    "evaluated_world_ids": [str(item) for item in payload.get("evaluated_world_ids", []) if str(item)],
                }
            )
        content_quality_failed_check_items = []
        for check in content_quality_evidence.get("checks", []) or []:
            payload = dict(check or {})
            if payload.get("ok"):
                continue
            content_quality_failed_check_items.append(
                {
                    "check_key": str(payload.get("key") or ""),
                    "label": content_quality_check_labels.get(str(payload.get("key") or ""), str(payload.get("key") or "")),
                    "reason": str(payload.get("reason") or ""),
                    "actual": payload.get("actual"),
                    "threshold": payload.get("threshold"),
                    "world_id": str(payload.get("world_id") or ""),
                }
            )
        return {
            "blocker_count": len(blockers),
            "owners": by_owner,
            "severity_counts": by_severity,
            "items": blockers,
            "phase_a_quality_gate": {
                "available": bool(phase_a_gate_item),
                "config_version": str(phase_a_evidence.get("config_version") or ""),
                "failed_check_items": phase_a_failed_check_items,
            },
            "content_quality_contract_gate": {
                "available": bool(content_quality_gate_item),
                "config_version": str(content_quality_evidence.get("config_version") or ""),
                "failed_check_items": content_quality_failed_check_items,
                "blocking_worlds": list(content_quality_evidence.get("blocking_worlds") or []),
            },
        }

    def _review_ownership_summary(self, history_payload: Dict[str, Any], status_payload: Dict[str, Any]) -> Dict[str, Any]:
        review_summary = dict(history_payload.get("review_summary") or {})
        latest_review = (status_payload.get("recent_reviews_drilldown") or [{}])[0]
        return {
            "reviewer_counts": dict(review_summary.get("reviewer_counts") or {}),
            "latest_reviewer_id": latest_review.get("reviewer_id"),
            "latest_review_status": latest_review.get("status"),
            "checklist_owners": list((status_payload.get("publish_checklist_summary") or {}).get("owners") or []),
        }

    def _version_matrix(self, history_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        matrix = []
        for item in history_payload.get("quality_trend", []):
            checklist_summary = dict(item.get("publish_checklist_summary") or {})
            matrix.append(
                {
                    "world_version_id": item.get("world_version_id"),
                    "status": item.get("status"),
                    "latest_decision": item.get("latest_decision"),
                    "cross_pack_pass_rate": item.get("cross_pack_pass_rate"),
                    "pass_rate": item.get("pass_rate"),
                    "block_rate": item.get("block_rate"),
                    "regression_detected": bool(item.get("regression_detected")),
                    "publish_ready": bool(checklist_summary.get("publish_ready")),
                    "blocked_checklist_count": int(checklist_summary.get("blocked_count") or 0),
                    "top_failing_pack_ids": list(item.get("top_failing_pack_ids") or []),
                    "publish_gate_errors": list(item.get("publish_gate_errors") or []),
                    "updated_at": item.get("updated_at"),
                }
            )
        return matrix

    def _rollback_workspace(self, status_payload: Dict[str, Any], history_payload: Dict[str, Any]) -> Dict[str, Any]:
        rollback_summary = dict(history_payload.get("rollback_summary") or {})
        latest = (history_payload.get("rollback_drilldown") or [{}])[0]
        return {
            "summary": rollback_summary,
            "latest_rollback": latest if latest.get("review_id") or latest.get("asset_id") else None,
            "rollback_candidates": list(status_payload.get("rollback_targets") or []),
        }

    def _action_pack(
        self,
        *,
        world_id: str,
        status_payload: Dict[str, Any],
        selected_world_version_id: Optional[str],
        publish_blockers: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = [
            {
                "action_id": "open_release_investigation",
                "label": "Open Release Investigation",
                "handler": "run_release_investigation",
                "mode": "navigate",
                "reason": "inspect content release evidence chain",
                "priority": 0,
                "prefill": {
                    "world_version_id": selected_world_version_id,
                    "account_id": next((item.get("author_id") for item in status_payload.get("versions", []) if item.get("world_version_id") == selected_world_version_id), None),
                    "claim_safe_band": dict(status_payload.get("author_longform_capability") or {}).get("claim_safe_band"),
                    "ops_release_ready_band": dict(status_payload.get("author_claim_alignment") or {}).get("ops_release_ready_band"),
                    "author_claim_alignment": dict(status_payload.get("author_claim_alignment") or {}).get("aligned"),
                },
            }
        ]
        release_bundle = dict(status_payload.get("release_evidence_bundle") or {})
        strategy_batch_summary = dict(release_bundle.get("strategy_bundle_batch_validation_summary") or {})
        strategy_batch_history_summary = dict(release_bundle.get("strategy_bundle_batch_validation_history_summary") or {})
        if release_bundle:
            actions.append(
                {
                    "action_id": "inspect_release_evidence_bundle",
                    "label": "Inspect Release Evidence Bundle",
                    "handler": "inspect_release_evidence_bundle",
                    "mode": "navigate",
                    "reason": str(dict(release_bundle.get("combined_signoff") or {}).get("reason") or "review longform release evidence"),
                    "priority": 0,
                    "prefill": {"world_version_id": selected_world_version_id},
                }
            )
        if bool(strategy_batch_summary.get("available", False) or strategy_batch_history_summary.get("available", False)):
            actions.append(
                {
                    "action_id": "inspect_strategy_bundle_batch_validation",
                    "label": "Inspect Strategy Bundle Batch Validation",
                    "handler": "inspect_strategy_bundle_batch_validation",
                    "mode": "navigate",
                    "reason": str(
                        strategy_batch_history_summary.get("trend_reason")
                        or strategy_batch_summary.get("decision_reason")
                        or "review cross-pack strategy bundle evidence"
                    ),
                    "priority": (
                        0
                        if str(strategy_batch_history_summary.get("trend_status") or "") in {"deteriorating", "retire_watch"}
                        else 1
                    ),
                    "prefill": {
                        "strategy_bundle_id": strategy_batch_summary.get("strategy_bundle_id") or strategy_batch_history_summary.get("strategy_bundle_id"),
                        "validate_strategy_bundle": False,
                    },
                }
            )
            if (
                str(strategy_batch_history_summary.get("trend_status") or "") in {"deteriorating", "retire_watch"}
                or str(strategy_batch_summary.get("decision") or "") in {"adapt", "retire"}
            ):
                actions.append(
                    {
                        "action_id": "inspect_cross_pack_quality",
                        "label": "Inspect Cross-Pack Quality",
                        "handler": "inspect_cross_pack_quality",
                        "mode": "navigate",
                        "reason": str(
                            strategy_batch_history_summary.get("trend_reason")
                            or strategy_batch_summary.get("decision_reason")
                            or "cross-pack remediation decision requires follow-up"
                        ),
                        "priority": 0,
                        "prefill": {
                            "strategy_bundle_id": strategy_batch_summary.get("strategy_bundle_id") or strategy_batch_history_summary.get("strategy_bundle_id"),
                            "validate_strategy_bundle": False,
                        },
                    }
                )
        if selected_world_version_id and not publish_blockers.get("items") and selected_world_version_id != status_payload.get("published_version"):
            actions.append(
                {
                    "action_id": "publish_candidate",
                    "label": "Publish Candidate",
                    "handler": "publish_world_version",
                    "mode": "execute",
                    "reason": "publish checklist is green",
                    "priority": 1,
                    "prefill": {"world_version_id": selected_world_version_id},
                }
            )
        rollback_targets = list(status_payload.get("rollback_targets") or [])
        if rollback_targets:
            actions.append(
                {
                    "action_id": "rollback_world",
                    "label": "Rollback To Previous",
                    "handler": "rollback_world",
                    "mode": "execute",
                    "reason": "a rollback candidate exists",
                    "priority": 2,
                    "prefill": {
                        "world_id": world_id,
                        "target_world_version_id": rollback_targets[0].get("world_version_id"),
                    },
                }
            )
        for item in publish_blockers.get("items", [])[:3]:
            if str(item.get("key") or "") == "phase_a_quality_gate" and (publish_blockers.get("phase_a_quality_gate") or {}).get("failed_check_items"):
                for failed_check in list((publish_blockers.get("phase_a_quality_gate") or {}).get("failed_check_items") or [])[:3]:
                    actions.append(
                        {
                            "action_id": f"inspect_blocker::{item.get('key')}::{failed_check.get('check_key')}",
                            "label": f"Inspect {failed_check.get('label') or failed_check.get('check_key')}",
                            "handler": "inspect_publish_blocker",
                            "mode": "navigate",
                            "reason": failed_check.get("reason") or item.get("reason") or "publish blocker present",
                            "priority": 1,
                            "prefill": {
                                "blocker_key": item.get("key"),
                                "check_key": failed_check.get("check_key"),
                                "world_version_id": selected_world_version_id,
                            },
                        }
                    )
                continue
            if str(item.get("key") or "") == "content_quality_contract_gate" and (publish_blockers.get("content_quality_contract_gate") or {}).get("failed_check_items"):
                for failed_check in list((publish_blockers.get("content_quality_contract_gate") or {}).get("failed_check_items") or [])[:3]:
                    actions.append(
                        {
                            "action_id": f"inspect_blocker::{item.get('key')}::{failed_check.get('check_key')}::{failed_check.get('world_id')}",
                            "label": f"Inspect {failed_check.get('label') or failed_check.get('check_key')}",
                            "handler": "inspect_publish_blocker",
                            "mode": "navigate",
                            "reason": failed_check.get("reason") or item.get("reason") or "publish blocker present",
                            "priority": 1,
                            "prefill": {
                                "blocker_key": item.get("key"),
                                "check_key": failed_check.get("check_key"),
                                "world_id": failed_check.get("world_id"),
                                "world_version_id": selected_world_version_id,
                            },
                        }
                    )
                continue
            actions.append(
                {
                    "action_id": f"inspect_blocker::{item.get('key')}",
                    "label": f"Inspect {item.get('label') or item.get('key')}",
                    "handler": "inspect_publish_blocker",
                    "mode": "navigate",
                    "reason": item.get("reason") or "publish blocker present",
                    "priority": 1,
                    "prefill": {"blocker_key": item.get("key"), "world_version_id": selected_world_version_id},
                }
            )
        deduped: Dict[str, Dict[str, Any]] = {}
        for action in actions:
            if action["action_id"] not in deduped or action["priority"] < deduped[action["action_id"]]["priority"]:
                deduped[action["action_id"]] = action
        return sorted(deduped.values(), key=lambda item: (item["priority"], item["label"]))

    def _operator_timeline(
        self,
        *,
        history_payload: Dict[str, Any],
        status_payload: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for item in history_payload.get("review_timeline", []):
            entries.append(
                {
                    "entry_id": item.get("review_id") or item.get("asset_id"),
                    "occurred_at": item.get("updated_at"),
                    "category": "review" if item.get("timeline_group") != "rollback" else "rollback",
                    "headline": item.get("status") or "review_event",
                    "summary": f"{item.get('world_version_id') or item.get('target_world_version_id') or '-'} · reviewer {item.get('reviewer_id') or '-'}",
                    "next_actions": list(item.get("publish_gate_errors") or []),
                }
            )
        for item in status_payload.get("recent_entitlement_events", []):
            entries.append(
                {
                    "entry_id": f"entitlement::{item.get('event_id') or item.get('occurred_at')}",
                    "occurred_at": item.get("occurred_at"),
                    "category": "entitlement",
                    "headline": item.get("event_name") or "entitlement_event",
                    "summary": f"{item.get('reason') or '-'} · balance {item.get('balance') if item.get('balance') is not None else '-'}",
                    "next_actions": [],
                }
            )
        entries.sort(key=lambda item: self._parse_timestamp(item.get("occurred_at")), reverse=True)
        return entries[:limit]

    def world_release_workspace(self, *, world_id: str, limit: int = 12) -> Dict[str, Any]:
        status_payload = self.review.world_status(world_id)
        history_payload = self.review.world_history(world_id)
        selected_world_version_id = self._selected_world_version_id(status_payload)
        publish_blockers = self._publish_blockers(status_payload)
        quality_projection = self.quality_projection.quality_summary(
            world_version_id=selected_world_version_id,
            limit=12,
        ) if selected_world_version_id else {"summary": {}, "events": [], "review_cases": []}
        investigation = (
            self.traceability.investigate_world_version(selected_world_version_id, limit=min(limit, 12))
            if selected_world_version_id
            else None
        )
        release_evidence_bundle = dict(status_payload.get("release_evidence_bundle") or {})
        combined_signoff = dict(release_evidence_bundle.get("combined_signoff") or {})
        strategy_bundle_batch_validation_summary = dict(
            release_evidence_bundle.get("strategy_bundle_batch_validation_summary") or {}
        )
        strategy_bundle_batch_validation_history_summary = dict(
            release_evidence_bundle.get("strategy_bundle_batch_validation_history_summary") or {}
        )
        reader_storybook_title_homogenization_history_summary = dict(
            release_evidence_bundle.get("reader_storybook_title_homogenization_history_summary") or {}
        )
        reader_storybook_title_homogenization_promoted_pairs = list(
            release_evidence_bundle.get("reader_storybook_title_homogenization_promoted_pairs") or []
        )
        return {
            "generated_at": self._utcnow(),
            "world_id": world_id,
            "selected_world_version_id": selected_world_version_id,
            "release_summary": {
                "health_status": self._release_health_status(status_payload=status_payload, history_payload=history_payload),
                "recommended_action": self._recommended_action(
                    status_payload=status_payload,
                    history_payload=history_payload,
                    selected_world_version_id=selected_world_version_id,
                ),
                "published_version": status_payload.get("published_version"),
                "selected_world_version_id": selected_world_version_id,
                "publish_ready": bool((status_payload.get("publish_checklist_summary") or {}).get("publish_ready")),
                "blocked_checklist_count": int((status_payload.get("publish_checklist_summary") or {}).get("blocked_count") or 0),
                "release_evidence_status": combined_signoff.get("status"),
                "release_evidence_ready": bool(combined_signoff.get("ready", False)),
                "author_entry_mode": dict(status_payload.get("author_longform_capability") or {}).get("entry_mode"),
                "author_claim_safe_band": dict(status_payload.get("author_longform_capability") or {}).get("claim_safe_band"),
                "author_requested_target_band": dict(status_payload.get("author_longform_capability") or {}).get("requested_target_band"),
                "ops_release_ready_band": dict(status_payload.get("author_claim_alignment") or {}).get("ops_release_ready_band"),
                "author_claim_alignment": bool(dict(status_payload.get("author_claim_alignment") or {}).get("aligned")),
                "strategy_bundle_batch_validation_status": self._strategy_bundle_batch_validation_status(release_evidence_bundle),
                "strategy_bundle_batch_validation_reason": str(
                    strategy_bundle_batch_validation_summary.get("decision_reason") or ""
                ),
                "strategy_bundle_batch_validation_trend_status": str(
                    strategy_bundle_batch_validation_history_summary.get("trend_status") or ""
                ),
                "strategy_bundle_batch_validation_trend_reason": str(
                    strategy_bundle_batch_validation_history_summary.get("trend_reason") or ""
                ),
                "strategy_bundle_batch_validation_retire_recommended": bool(
                    strategy_bundle_batch_validation_history_summary.get("retire_recommended", False)
                ),
                "reader_storybook_title_homogenization_trend_status": str(
                    reader_storybook_title_homogenization_history_summary.get("trend_status") or ""
                ),
                "reader_storybook_title_homogenization_trend_reason": str(
                    reader_storybook_title_homogenization_history_summary.get("trend_reason") or ""
                ),
                "reader_storybook_title_homogenization_promoted_pair_count": len(
                    reader_storybook_title_homogenization_promoted_pairs
                ),
                "recent_rollback_count": int((history_payload.get("rollback_summary") or {}).get("total_entries") or 0),
                "latest_rollback_target": (history_payload.get("rollback_summary") or {}).get("latest_target_world_version_id"),
                "quality_open_case_count": int((quality_projection.get("summary") or {}).get("open_review_case_count") or 0),
                "quality_blocked_event_count": int((quality_projection.get("summary") or {}).get("blocked_event_count") or 0),
                "quality_review_required_event_count": int((quality_projection.get("summary") or {}).get("review_required_event_count") or 0),
                "quality_latest_trace_id": (quality_projection.get("summary") or {}).get("latest_trace_id"),
            },
            "publish_blockers": publish_blockers,
            "release_evidence_bundle": release_evidence_bundle,
            "review_ownership_summary": self._review_ownership_summary(history_payload, status_payload),
            "version_matrix": self._version_matrix(history_payload),
            "rollback_workspace": self._rollback_workspace(status_payload, history_payload),
            "action_pack": self._action_pack(
                world_id=world_id,
                status_payload=status_payload,
                selected_world_version_id=selected_world_version_id,
                publish_blockers=publish_blockers,
            ),
            "investigation_summary": {
                "recommended_paths": (investigation or {}).get("recommended_paths") or [],
                "summary": (investigation or {}).get("investigation_summary") or {},
                "export_refs": (investigation or {}).get("export_refs") or {
                    "world_version_id": selected_world_version_id,
                    "claim_safe_band": dict(status_payload.get("author_longform_capability") or {}).get("claim_safe_band"),
                    "ops_release_ready_band": dict(status_payload.get("author_claim_alignment") or {}).get("ops_release_ready_band"),
                    "author_claim_alignment": dict(status_payload.get("author_claim_alignment") or {}).get("aligned"),
                },
            },
            "linked_context": {
                "world_id": world_id,
                "published_version": status_payload.get("published_version"),
                "rollback_target_ids": [item.get("world_version_id") for item in status_payload.get("rollback_targets", [])],
                "review_ids": [item.get("review_id") for item in history_payload.get("review_timeline", []) if item.get("review_id")],
                "quality_trace_ids": [item.get("trace_id") for item in list(quality_projection.get("events") or []) if item.get("trace_id")][:3],
            },
            "quality_projection_summary": quality_projection,
            "operator_timeline": self._operator_timeline(
                history_payload=history_payload,
                status_payload=status_payload,
                limit=limit,
            ),
            "world_status": status_payload,
            "world_history": history_payload,
        }
