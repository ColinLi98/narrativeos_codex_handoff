from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .analytics import AnalyticsService


class ReviewService:
    def __init__(self, repository: SQLAlchemyPlatformRepository, analytics_service: Optional[AnalyticsService] = None) -> None:
        self.repository = repository
        self.analytics = analytics_service or AnalyticsService(repository)

    def _publish_gate_errors(self, simulation: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        evaluation_summary = dict(simulation.get("evaluation_summary", {}))
        cross_pack_summary = dict(simulation.get("cross_pack_summary", {}))
        delta_summary = dict(cross_pack_summary.get("delta_summary", {}))
        regressions = list(delta_summary.get("regressions", []))
        if not simulation:
            errors.append("publish_requires_simulation_report")
            return errors
        if not cross_pack_summary:
            errors.append("missing_cross_pack_summary")
        if simulation.get("latest_decision") == "block" or evaluation_summary.get("block_rate", 0.0) > 0.0:
            errors.append("narrative_eval_block")
        if any(float(item.get("prose_leak_rate", 0.0)) > 0.0 for item in cross_pack_summary.get("worlds", [])):
            errors.append("prose_leak_rate_above_zero")
        if float(delta_summary.get("cross_pack_pass_rate_delta", 0.0)) < 0:
            errors.append("cross_pack_pass_rate_regressed")
        if regressions:
            errors.append("metric_regression_detected")
        return errors

    def _review_note(
        self,
        *,
        world_version_id: Optional[str] = None,
        world_id: Optional[str] = None,
        simulation: Optional[Dict[str, Any]] = None,
        publish_gate_errors: Optional[List[str]] = None,
        target_world_version_id: Optional[str] = None,
        published_world_version_id: Optional[str] = None,
        previous_world_version_id: Optional[str] = None,
        entitlement_reason: Optional[str] = None,
        risk_summary: Optional[Dict[str, Any]] = None,
        assisted_gate_receipt: Optional[Dict[str, Any]] = None,
    ) -> str:
        simulation = dict(simulation or {})
        payload = {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "latest_decision": simulation.get("latest_decision"),
            "cross_pack_pass_rate": simulation.get("cross_pack_summary", {}).get("cross_pack_pass_rate"),
            "top_failing_packs": simulation.get("top_failing_packs", []),
            "publish_gate_errors": list(publish_gate_errors or []),
            "target_world_version_id": target_world_version_id,
            "published_world_version_id": published_world_version_id,
            "previous_world_version_id": previous_world_version_id,
            "entitlement_reason": entitlement_reason,
            "risk_summary": dict(risk_summary or {}),
            "assisted_gate_receipt": dict(assisted_gate_receipt or {}),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _pack_ids(self, packs: List[Any]) -> List[str]:
        ids: List[str] = []
        for item in packs or []:
            if isinstance(item, dict):
                candidate = item.get("world_id") or item.get("pack_id") or item.get("id")
            else:
                candidate = str(item) if item is not None else None
            if candidate:
                ids.append(str(candidate))
        return ids

    def _checklist_item(
        self,
        *,
        key: str,
        label: str,
        ok: bool,
        reason: str,
        source: str,
        owner: str,
        severity: str,
        next_action: str,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "ok": ok,
            "reason": reason,
            "source": source,
            "owner": owner,
            "severity": "info" if ok else severity,
            "next_action": "none" if ok else next_action,
            "evidence": evidence,
        }

    def _publish_checklist_summary(self, checklist: List[Dict[str, Any]]) -> Dict[str, Any]:
        blocked = [item for item in checklist if not item.get("ok")]
        return {
            "total": len(checklist),
            "ok_count": sum(1 for item in checklist if item.get("ok")),
            "blocked_count": len(blocked),
            "publish_ready": not blocked,
            "blocker_keys": [item.get("key") for item in blocked],
            "owners": sorted({str(item.get("owner")) for item in checklist if item.get("owner")}),
            "next_actions": [item.get("next_action") for item in blocked if item.get("next_action") and item.get("next_action") != "none"],
        }

    def _review_timeline_entry(self, record: Dict[str, Any]) -> Dict[str, Any]:
        note_payload = parse_review_notes(record.get("notes"))
        return {
            **record,
            "note_payload": note_payload,
            "world_id": note_payload.get("world_id"),
            "world_version_id": note_payload.get("world_version_id") or (record.get("asset_id") if record.get("asset_type") == "world_version" else None),
            "published_world_version_id": note_payload.get("published_world_version_id"),
            "previous_world_version_id": note_payload.get("previous_world_version_id"),
            "target_world_version_id": note_payload.get("target_world_version_id"),
            "latest_decision": note_payload.get("latest_decision"),
            "cross_pack_pass_rate": note_payload.get("cross_pack_pass_rate"),
            "top_failing_pack_ids": self._pack_ids(note_payload.get("top_failing_packs", [])),
            "publish_gate_errors": list(note_payload.get("publish_gate_errors", [])),
            "entitlement_reason": note_payload.get("entitlement_reason"),
            "risk_summary": dict(note_payload.get("risk_summary", {})),
            "assisted_gate_receipt": dict(note_payload.get("assisted_gate_receipt", {})),
            "timeline_group": "rollback" if record.get("status") == "rolled_back" else "review",
        }

    def _review_summary(self, timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        reviewer_counts: Dict[str, int] = {}
        for item in timeline:
            status = str(item.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            reviewer_id = item.get("reviewer_id")
            if reviewer_id:
                reviewer_counts[str(reviewer_id)] = reviewer_counts.get(str(reviewer_id), 0) + 1
        latest_published = next((item.get("published_world_version_id") or item.get("world_version_id") for item in timeline if item.get("status") == "published"), None)
        latest_blocked = next((item.get("world_version_id") for item in timeline if item.get("status") == "publish_blocked"), None)
        latest_rollback = next((item.get("target_world_version_id") for item in timeline if item.get("timeline_group") == "rollback"), None)
        return {
            "total_entries": len(timeline),
            "status_counts": status_counts,
            "reviewer_counts": reviewer_counts,
            "latest_at": timeline[0].get("updated_at") if timeline else None,
            "latest_published_world_version_id": latest_published,
            "latest_blocked_world_version_id": latest_blocked,
            "latest_rollback_target_world_version_id": latest_rollback,
        }

    def _rollback_drilldown_entry(self, record: Dict[str, Any]) -> Dict[str, Any]:
        timeline_entry = self._review_timeline_entry(record)
        risk_summary = dict(timeline_entry.get("risk_summary", {}))
        return {
            **timeline_entry,
            "rollback_target_world_version_id": timeline_entry.get("target_world_version_id"),
            "rollback_previous_world_version_id": timeline_entry.get("previous_world_version_id"),
            "rollback_reason": timeline_entry.get("entitlement_reason") or "operator_requested_rollback",
            "rollback_gate_errors": list(risk_summary.get("publish_gate_errors", [])),
        }

    def _rollback_summary(self, rollback_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        reviewer_counts: Dict[str, int] = {}
        target_counts: Dict[str, int] = {}
        for item in rollback_entries:
            reviewer_id = item.get("reviewer_id")
            if reviewer_id:
                reviewer_counts[str(reviewer_id)] = reviewer_counts.get(str(reviewer_id), 0) + 1
            target = item.get("rollback_target_world_version_id")
            if target:
                target_counts[str(target)] = target_counts.get(str(target), 0) + 1
        latest = rollback_entries[0] if rollback_entries else {}
        return {
            "total_entries": len(rollback_entries),
            "reviewer_counts": reviewer_counts,
            "target_counts": target_counts,
            "latest_at": latest.get("updated_at"),
            "latest_target_world_version_id": latest.get("rollback_target_world_version_id"),
            "latest_previous_world_version_id": latest.get("rollback_previous_world_version_id"),
            "latest_reason": latest.get("rollback_reason"),
        }

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _quality_trend_entry(
        self,
        version_meta: Dict[str, Any],
        *,
        world_version: Any,
        previous_entry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        simulation = dict(world_version.simulation_report_json or {})
        evaluation = dict(simulation.get("evaluation_summary", {}))
        cross_pack_summary = dict(simulation.get("cross_pack_summary", {}))
        delta_summary = dict(cross_pack_summary.get("delta_summary", {}))
        checklist = self.build_publish_checklist(world_version.world_version_id) if simulation else []
        checklist_summary = self._publish_checklist_summary(checklist)
        pass_rate = self._safe_float(evaluation.get("pass_rate"))
        rewrite_rate = self._safe_float(evaluation.get("rewrite_rate"))
        block_rate = self._safe_float(evaluation.get("block_rate"))
        cross_pack_pass_rate = self._safe_float(cross_pack_summary.get("cross_pack_pass_rate"))
        entry = {
            "world_version_id": world_version.world_version_id,
            "status": world_version.status,
            "pass_rate": pass_rate,
            "rewrite_rate": rewrite_rate,
            "block_rate": block_rate,
            "cross_pack_pass_rate": cross_pack_pass_rate,
            "cross_pack_pass_rate_delta": self._safe_float(delta_summary.get("cross_pack_pass_rate_delta")),
            "latest_decision": simulation.get("latest_decision"),
            "top_failing_pack_ids": self._pack_ids(cross_pack_summary.get("top_failing_packs", simulation.get("top_failing_packs", []))),
            "regressions": list(delta_summary.get("regressions", [])),
            "publish_checklist_summary": checklist_summary,
            "publish_gate_errors": [item.get("reason") for item in checklist if not item.get("ok")],
            "updated_at": version_meta.get("updated_at"),
        }
        if previous_entry:
            entry["delta_vs_previous"] = {
                "pass_rate": round(pass_rate - self._safe_float(previous_entry.get("pass_rate")), 3),
                "rewrite_rate": round(rewrite_rate - self._safe_float(previous_entry.get("rewrite_rate")), 3),
                "block_rate": round(block_rate - self._safe_float(previous_entry.get("block_rate")), 3),
                "cross_pack_pass_rate": round(cross_pack_pass_rate - self._safe_float(previous_entry.get("cross_pack_pass_rate")), 3),
            }
        else:
            entry["delta_vs_previous"] = {
                "pass_rate": 0.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "cross_pack_pass_rate": 0.0,
            }
        entry["regression_detected"] = (
            bool(entry["regressions"])
            or entry["delta_vs_previous"]["pass_rate"] < 0
            or entry["delta_vs_previous"]["block_rate"] > 0
            or entry["delta_vs_previous"]["cross_pack_pass_rate"] < 0
        )
        return entry

    def _quality_trend_summary(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not entries:
            return {
                "total_versions": 0,
                "latest_world_version_id": None,
                "strongest_world_version_id": None,
                "weakest_world_version_id": None,
                "regression_version_ids": [],
                "blocked_version_ids": [],
                "improving_version_ids": [],
            }
        strongest = max(entries, key=lambda item: (self._safe_float(item.get("pass_rate")), self._safe_float(item.get("cross_pack_pass_rate"))))
        weakest = min(entries, key=lambda item: (self._safe_float(item.get("cross_pack_pass_rate")), self._safe_float(item.get("pass_rate"))))
        regression_version_ids = [item.get("world_version_id") for item in entries if item.get("regression_detected")]
        blocked_version_ids = [item.get("world_version_id") for item in entries if self._safe_float(item.get("block_rate")) > 0 or item.get("latest_decision") == "block"]
        improving_version_ids = [
            item.get("world_version_id")
            for item in entries
            if item.get("delta_vs_previous", {}).get("pass_rate", 0.0) > 0
            or item.get("delta_vs_previous", {}).get("cross_pack_pass_rate", 0.0) > 0
        ]
        latest = entries[0]
        return {
            "total_versions": len(entries),
            "latest_world_version_id": latest.get("world_version_id"),
            "strongest_world_version_id": strongest.get("world_version_id"),
            "weakest_world_version_id": weakest.get("world_version_id"),
            "latest_delta": dict(latest.get("delta_vs_previous", {})),
            "regression_version_ids": regression_version_ids,
            "blocked_version_ids": blocked_version_ids,
            "improving_version_ids": improving_version_ids,
        }

    def _record_lifecycle(
        self,
        *,
        asset_type: str,
        asset_id: str,
        status: str,
        reviewer_id: Optional[str] = None,
        risk_rating: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        return self.repository.save_review_record(
            {
                "asset_type": asset_type,
                "asset_id": asset_id,
                "status": status,
                "reviewer_id": reviewer_id,
                "risk_rating": risk_rating,
                "notes": notes,
            }
        )

    def build_publish_checklist(self, world_version_id: str) -> List[Dict[str, Any]]:
        world_version = self.repository.get_world_version(world_version_id)
        simulation = dict(world_version.simulation_report_json or {})
        errors = self._publish_gate_errors(simulation)
        evaluation_summary = dict(simulation.get("evaluation_summary", {}))
        cross_pack_summary = dict(simulation.get("cross_pack_summary", {}))
        delta_summary = dict(cross_pack_summary.get("delta_summary", {}))
        top_failing_pack_ids = self._pack_ids(cross_pack_summary.get("top_failing_packs", simulation.get("top_failing_packs", [])))
        leaking_worlds = [
            {
                "world_id": item.get("world_id"),
                "prose_leak_rate": item.get("prose_leak_rate"),
            }
            for item in cross_pack_summary.get("worlds", [])
            if float(item.get("prose_leak_rate", 0.0)) > 0.0
        ]
        return [
            self._checklist_item(
                key="simulation_report",
                label="存在最新 simulation",
                ok=bool(simulation),
                reason="simulation_report_ready" if simulation else "publish_requires_simulation_report",
                source="simulation_report",
                owner="authoring_service",
                severity="blocker",
                next_action="rerun_world_version_simulation",
                evidence={
                    "present": bool(simulation),
                    "latest_decision": simulation.get("latest_decision"),
                    "completed_chapters": simulation.get("completed_chapters"),
                },
            ),
            self._checklist_item(
                key="cross_pack_summary",
                label="包含 cross-pack summary",
                ok=bool(cross_pack_summary),
                reason="cross_pack_summary_ready" if cross_pack_summary else "missing_cross_pack_summary",
                source="cross_pack_summary",
                owner="benchmark_runner",
                severity="blocker",
                next_action="rerun_cross_pack_benchmark",
                evidence={
                    "present": bool(cross_pack_summary),
                    "cross_pack_pass_rate": cross_pack_summary.get("cross_pack_pass_rate"),
                    "top_failing_pack_ids": top_failing_pack_ids,
                },
            ),
            self._checklist_item(
                key="prose_leak_rate",
                label="prose_leak_rate 为 0",
                ok="prose_leak_rate_above_zero" not in errors,
                reason="prose_leak_rate_zero" if "prose_leak_rate_above_zero" not in errors else "prose_leak_rate_above_zero",
                source="cross_pack_summary",
                owner="core_writer",
                severity="blocker",
                next_action="inspect_writer_prose_contract",
                evidence={
                    "leaking_worlds": leaking_worlds,
                    "max_prose_leak_rate": max((float(item.get("prose_leak_rate") or 0.0) for item in leaking_worlds), default=0.0),
                },
            ),
            self._checklist_item(
                key="cross_pack_regression",
                label="cross-pack 指标无回退",
                ok="cross_pack_pass_rate_regressed" not in errors and "metric_regression_detected" not in errors,
                reason=(
                    "cross_pack_delta_clean"
                    if "cross_pack_pass_rate_regressed" not in errors and "metric_regression_detected" not in errors
                    else ("cross_pack_pass_rate_regressed" if "cross_pack_pass_rate_regressed" in errors else "metric_regression_detected")
                ),
                source="delta_summary",
                owner="benchmark_reporting",
                severity="blocker",
                next_action="inspect_cross_pack_regressions",
                evidence={
                    "cross_pack_pass_rate_delta": delta_summary.get("cross_pack_pass_rate_delta"),
                    "regressions": list(delta_summary.get("regressions", [])),
                },
            ),
            self._checklist_item(
                key="chapter_eval_gate",
                label="章节评测未 block",
                ok="narrative_eval_block" not in errors,
                reason="chapter_eval_pass" if "narrative_eval_block" not in errors else "narrative_eval_block",
                source="evaluation_summary",
                owner="narrative_eval",
                severity="blocker",
                next_action="fix_blocking_eval_issues",
                evidence={
                    "latest_decision": simulation.get("latest_decision"),
                    "pass_rate": evaluation_summary.get("pass_rate"),
                    "rewrite_rate": evaluation_summary.get("rewrite_rate"),
                    "block_rate": evaluation_summary.get("block_rate"),
                },
            ),
        ]

    def _recent_entitlement_events(self, version_ids: List[str]) -> List[Dict[str, Any]]:
        if not version_ids:
            return []
        events = self.repository.list_analytics_events(
            event_names=["entitlement_granted", "payment_required", "credits_consumed"],
            world_version_ids=version_ids,
            limit=10,
        )
        return [
            {
                **event,
                "reason": event.get("payload_json", {}).get("reason"),
                "entitlement_type": event.get("payload_json", {}).get("entitlement_type"),
                "balance": event.get("payload_json", {}).get("balance"),
            }
            for event in events
        ]

    def _risk_summary(
        self,
        *,
        publish_checklist: List[Dict[str, Any]],
        rollback_history: List[Dict[str, Any]],
        entitlement_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        publish_gate_errors = [item["reason"] for item in publish_checklist if not item["ok"]]
        latest_rollback = rollback_history[0] if rollback_history else None
        latest_rollback_payload = parse_review_notes(latest_rollback.get("notes")) if latest_rollback else {}
        entitlement_alerts = [
            {
                "event_name": item["event_name"],
                "reason": item.get("reason"),
                "occurred_at": item.get("occurred_at"),
            }
            for item in entitlement_events
            if item["event_name"] == "payment_required" or item.get("reason") in {"entitlement_expired", "credits_exhausted"}
        ]
        return {
            "publish_ready": bool(publish_checklist) and not publish_gate_errors,
            "publish_gate_errors": publish_gate_errors,
            "latest_rollback_reason": (
                latest_rollback_payload.get("entitlement_reason") or "operator_requested_rollback"
                if latest_rollback
                else None
            ),
            "latest_rollback_target": latest_rollback_payload.get("target_world_version_id") if latest_rollback else None,
            "entitlement_alerts": entitlement_alerts,
        }

    def queue(self) -> List[Dict[str, Any]]:
        reviews = self.repository.list_review_records(status="submitted", asset_type="world_version")
        enriched = []
        for review in reviews:
            simulation = {}
            try:
                world_version = self.repository.get_world_version(review["asset_id"])
                simulation = dict(world_version.simulation_report_json or {})
            except KeyError:
                simulation = {}
            publish_checklist = self.build_publish_checklist(review["asset_id"]) if simulation else []
            gate_errors = [item["reason"] for item in publish_checklist if not item["ok"]]
            enriched.append(
                {
                    **review,
                    "latest_decision": simulation.get("latest_decision"),
                    "top_failing_packs": simulation.get("top_failing_packs", []),
                    "publish_checklist": publish_checklist,
                    "publish_gate_errors": gate_errors,
                }
            )
        return enriched

    def submit_world_version(self, world_version_id: str) -> Dict[str, Any]:
        world_version = self.repository.get_world_version(world_version_id)
        world_version.status = "submitted"
        self.repository.save_world_version(world_version, publish=False)
        simulation = dict(world_version.simulation_report_json or {})
        return self._record_lifecycle(
            asset_type="world_version",
            asset_id=world_version_id,
            status="submitted",
            risk_rating=world_version.risk_rating,
            notes=self._review_note(
                world_version_id=world_version_id,
                world_id=world_version.world_id,
                simulation=simulation,
            ),
        )

    def publish(self, world_version_id: str, *, reviewer_id: Optional[str] = None) -> Dict[str, Any]:
        from ..eval.learned_assisted_gate import evaluate_assisted_gate_decision

        world_version = self.repository.get_world_version(world_version_id)
        simulation = dict(world_version.simulation_report_json or {})
        errors = self._publish_gate_errors(simulation)
        assisted_gate_receipt = evaluate_assisted_gate_decision(
            repository=self.repository,
            world_version_id=world_version_id,
            simulation={**simulation, "world_id": world_version.world_id},
            rule_gate_errors=errors,
        )
        if not errors and assisted_gate_receipt.get("assisted_action") == "block_publish":
            errors = list(assisted_gate_receipt.get("final_gate_errors", []))
        self.analytics.track(
            "learned_assisted_gate_evaluated",
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            payload_json={
                "mode": assisted_gate_receipt.get("mode"),
                "bucket_match": assisted_gate_receipt.get("bucket_match"),
                "guardrail_status": assisted_gate_receipt.get("guardrail_status"),
                "assisted_action": assisted_gate_receipt.get("assisted_action"),
                "would_block": assisted_gate_receipt.get("would_block"),
            },
        )
        if errors:
            risk_summary = {"publish_gate_errors": errors, "publish_ready": False}
            self._record_lifecycle(
                asset_type="world_version",
                asset_id=world_version_id,
                status="publish_blocked",
                reviewer_id=reviewer_id,
                risk_rating=world_version.risk_rating,
                notes=self._review_note(
                    world_version_id=world_version_id,
                    world_id=world_version.world_id,
                    simulation=simulation,
                    publish_gate_errors=errors,
                    entitlement_reason="publish_blocked",
                    risk_summary=risk_summary,
                    assisted_gate_receipt=assisted_gate_receipt,
                ),
            )
            self.analytics.track(
                "publish_blocked",
                world_id=world_version.world_id,
                world_version_id=world_version_id,
                payload_json={
                    "publish_gate_errors": errors,
                    "assisted_gate_action": assisted_gate_receipt.get("assisted_action"),
                },
            )
            if assisted_gate_receipt.get("assisted_action") == "block_publish":
                self.analytics.track(
                    "learned_assisted_gate_blocked",
                    world_id=world_version.world_id,
                    world_version_id=world_version_id,
                    payload_json={
                        "publish_gate_errors": errors,
                        "mode": assisted_gate_receipt.get("mode"),
                        "bucket_match": assisted_gate_receipt.get("bucket_match"),
                    },
                )
            raise ValueError(errors[0])

        previous_world_version_id = next(
            (item["world_version_id"] for item in self.repository.list_world_versions(world_id=world_version.world_id) if item["status"] == "published"),
            None,
        )
        self._record_lifecycle(
            asset_type="world_version",
            asset_id=world_version_id,
            status="approved",
            reviewer_id=reviewer_id,
            risk_rating=world_version.risk_rating,
            notes=self._review_note(
                world_version_id=world_version_id,
                world_id=world_version.world_id,
                simulation=simulation,
                previous_world_version_id=previous_world_version_id,
                published_world_version_id=world_version_id,
                assisted_gate_receipt=assisted_gate_receipt,
            ),
        )
        result = self.repository.publish_world_version(world_version_id, reviewer_id=reviewer_id)
        review = self._record_lifecycle(
            asset_type="world_version",
            asset_id=world_version_id,
            status="published",
            reviewer_id=reviewer_id,
            risk_rating=world_version.risk_rating,
            notes=self._review_note(
                world_version_id=world_version_id,
                world_id=world_version.world_id,
                simulation=simulation,
                previous_world_version_id=previous_world_version_id,
                published_world_version_id=world_version_id,
                assisted_gate_receipt=assisted_gate_receipt,
            ),
        )
        return {**result, "review": review}

    def rollback(self, world_id: str, target_world_version_id: str, *, reviewer_id: Optional[str] = None) -> Dict[str, Any]:
        result = self.repository.rollback_world(world_id, target_world_version_id)
        review = self._record_lifecycle(
            asset_type="world",
            asset_id=world_id,
            status="rolled_back",
            reviewer_id=reviewer_id,
            notes=self._review_note(
                world_id=world_id,
                target_world_version_id=target_world_version_id,
                previous_world_version_id=result.get("previous_version"),
                published_world_version_id=target_world_version_id,
                entitlement_reason="operator_requested_rollback",
            ),
        )
        self.analytics.track(
            "rollback_performed",
            world_id=world_id,
            world_version_id=target_world_version_id,
            payload_json={
                "target_world_version_id": target_world_version_id,
                "previous_world_version_id": result.get("previous_version"),
                "reason": "operator_requested_rollback",
            },
        )
        return {**result, "review": review}

    def world_history(self, world_id: str) -> Dict[str, Any]:
        versions = self.repository.list_world_versions(world_id=world_id)
        version_ids = [item["world_version_id"] for item in versions]
        review_history = self.repository.list_review_records(asset_type="world_version", asset_ids=version_ids)
        rollback_history = self.repository.list_review_records(asset_type="world", asset_id=world_id)
        rollback_drilldown = [self._rollback_drilldown_entry(item) for item in rollback_history]
        review_timeline = sorted(
            [self._review_timeline_entry(item) for item in [*review_history, *rollback_history]],
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )
        chronological_versions = sorted(versions, key=lambda item: str(item.get("updated_at") or ""))
        quality_trend_chronological: List[Dict[str, Any]] = []
        previous_entry: Optional[Dict[str, Any]] = None
        for version_meta in chronological_versions:
            version = self.repository.get_world_version(version_meta["world_version_id"])
            entry = self._quality_trend_entry(version_meta, world_version=version, previous_entry=previous_entry)
            quality_trend_chronological.append(entry)
            previous_entry = entry
        quality_trend = list(reversed(quality_trend_chronological))
        return {
            "world_id": world_id,
            "versions": versions,
            "review_history": review_history,
            "rollback_history": rollback_history,
            "rollback_drilldown": rollback_drilldown,
            "rollback_summary": self._rollback_summary(rollback_drilldown),
            "review_timeline": review_timeline,
            "review_summary": self._review_summary(review_timeline),
            "quality_trend": quality_trend,
            "quality_trend_summary": self._quality_trend_summary(quality_trend),
        }

    def world_status(self, world_id: str) -> Dict[str, Any]:
        versions = self.repository.list_world_versions(world_id=world_id)
        active_version_id = next((item["world_version_id"] for item in versions if item["status"] in {"submitted", "draft"}), None) or next(
            (item["world_version_id"] for item in versions if item["status"] == "published"),
            None,
        )
        active_version = self.repository.get_world_version(active_version_id) if active_version_id else None
        latest_simulation = dict(active_version.simulation_report_json or {}) if active_version else {}
        version_ids = [item["world_version_id"] for item in versions]
        recent_reviews = self.repository.list_review_records(asset_type="world_version", asset_ids=[item["world_version_id"] for item in versions])[:5]
        rollback_history = self.repository.list_review_records(asset_type="world", asset_id=world_id)
        rollback_targets = [item for item in versions if item["world_version_id"] != next((entry["world_version_id"] for entry in versions if entry["status"] == "published"), None)]
        publish_checklist = self.build_publish_checklist(active_version_id) if active_version_id else []
        entitlement_events = self._recent_entitlement_events(version_ids)
        risk_summary = self._risk_summary(
            publish_checklist=publish_checklist,
            rollback_history=rollback_history,
            entitlement_events=entitlement_events,
        )
        recent_reviews_drilldown = [self._review_timeline_entry(item) for item in recent_reviews]
        return {
            "world_id": world_id,
            "versions": versions,
            "published_version": next((item["world_version_id"] for item in versions if item["status"] == "published"), None),
            "evaluation_summary": self.repository.aggregate_eval_metrics(
                world_version_id=next((item["world_version_id"] for item in versions if item["status"] == "published"), None)
            ) if versions else {},
            "latest_simulation": latest_simulation,
            "publish_checklist": publish_checklist,
            "publish_checklist_summary": self._publish_checklist_summary(publish_checklist),
            "recent_reviews": recent_reviews,
            "recent_reviews_drilldown": recent_reviews_drilldown,
            "rollback_targets": rollback_targets,
            "recent_entitlement_events": entitlement_events,
            "risk_summary": risk_summary,
        }


def parse_review_notes(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
