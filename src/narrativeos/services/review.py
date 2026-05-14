from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..benchmark.content_quality_contract_gate import evaluate_content_quality_contract_gate
from ..content_quality_strategy_execution import (
    build_strategy_bundle_batch_validation_trend,
    list_strategy_bundle_batch_validation_history,
)
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..quality.adapter import record_publish_preflight_quality_event
from ..benchmark.release_quality_gate import evaluate_release_quality_gate
from .analytics import AnalyticsService
from .longform_capability import band_rank, build_longform_capability_payload
from .ops_quality_projection import OpsQualityProjectionService
from .reader_storybook_title_homogenization import (
    build_reader_storybook_title_homogenization_trend,
    load_reader_storybook_title_homogenization_history,
    promoted_reader_storybook_title_homogenization_pairs_for_world,
    summarize_reader_storybook_title_homogenization_history,
)


class ReviewService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        analytics_service: Optional[AnalyticsService] = None,
        quality_projection_service: Optional[OpsQualityProjectionService] = None,
    ) -> None:
        self.repository = repository
        self.analytics = analytics_service or AnalyticsService(repository)
        self.quality_projection = quality_projection_service or OpsQualityProjectionService(repository)
        self.base_dir = Path(__file__).resolve().parents[3]

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _publish_gate_errors(self, simulation: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not simulation:
            errors.append("publish_requires_simulation_report")
            return errors
        evaluation_summary = dict(simulation.get("evaluation_summary", {}))
        cross_pack_summary = dict(simulation.get("cross_pack_summary", {}))
        delta_summary = dict(cross_pack_summary.get("delta_summary", {}))
        regressions = list(delta_summary.get("regressions", []))
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
        quality_gate = dict(cross_pack_summary.get("phase_a_quality_gate") or simulation.get("phase_a_quality_gate") or evaluate_release_quality_gate(cross_pack_summary or simulation))
        errors.extend(str(item) for item in quality_gate.get("failed_checks", []))
        content_quality_gate = dict(
            cross_pack_summary.get("content_quality_contract_gate")
            or simulation.get("content_quality_contract_gate")
            or evaluate_content_quality_contract_gate(cross_pack_summary or simulation)
        )
        errors.extend(str(item) for item in content_quality_gate.get("failed_checks", []))
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
        review_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "ok": ok,
            "review_status": review_status or ("ready" if ok else "blocked"),
            "reason": reason,
            "source": source,
            "owner": owner,
            "severity": "info" if ok else severity,
            "next_action": (
                "none"
                if ok and (review_status or ("ready" if ok else "blocked")) == "ready"
                else next_action
            ),
            "evidence": evidence,
        }

    def _publish_checklist_summary(self, checklist: List[Dict[str, Any]]) -> Dict[str, Any]:
        blocked = [item for item in checklist if not item.get("ok")]
        status_counts: Dict[str, int] = {}
        for item in checklist:
            status = str(item.get("review_status") or ("ready" if item.get("ok") else "blocked"))
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "total": len(checklist),
            "ok_count": sum(1 for item in checklist if item.get("ok")),
            "blocked_count": len(blocked),
            "publish_ready": not blocked,
            "blocker_keys": [item.get("key") for item in blocked],
            "owners": sorted({str(item.get("owner")) for item in checklist if item.get("owner")}),
            "next_actions": [item.get("next_action") for item in blocked if item.get("next_action") and item.get("next_action") != "none"],
            "review_status_counts": status_counts,
        }

    def _artifact_candidate(self, *relative_paths: str) -> Optional[Dict[str, str]]:
        base_dir = Path(__file__).resolve().parents[3]
        for relative_path in relative_paths:
            path = base_dir / relative_path
            if path.exists():
                markdown_path = path.with_suffix(".md") if path.suffix == ".json" else None
                return {
                    "json": str(path) if path.suffix == ".json" else "",
                    "markdown": str(markdown_path) if markdown_path and markdown_path.exists() else "",
                }
        return None

    def _artifact_metrics(self, artifact_ref: Optional[Dict[str, str]]) -> Dict[str, Any]:
        json_path = str((artifact_ref or {}).get("json") or "")
        if not json_path:
            return {}
        try:
            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _summarize_strategy_bundle_batch_validation(
        self,
        batch_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = dict(batch_validation or {})
        return {
            "available": bool(payload.get("available", False)),
            "strategy_bundle_id": str(payload.get("strategy_bundle_id") or ""),
            "strategy_bundle_label": str(payload.get("strategy_bundle_label") or ""),
            "validated_world_count": int(payload.get("validated_world_count", 0) or 0),
            "effectiveness_rate": self._safe_float(payload.get("effectiveness_rate")),
            "decision": str(payload.get("decision") or ""),
            "decision_reason": str(payload.get("decision_reason") or ""),
            "top_adaptation_targets": [
                dict(item or {})
                for item in list(payload.get("adaptation_targets") or [])[:3]
            ],
            "compatible_world_ids": [str(item) for item in list(payload.get("compatible_world_ids") or []) if str(item)],
        }

    def _summarize_strategy_bundle_batch_validation_history(
        self,
        history_payload: Dict[str, Any],
        trend_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        history = dict(history_payload or {})
        trend = dict(trend_payload or {})
        return {
            "available": bool(history.get("available", False) or trend.get("available", False)),
            "strategy_bundle_id": str(trend.get("strategy_bundle_id") or history.get("strategy_bundle_id") or ""),
            "recent_run_count": int(trend.get("recent_run_count", 0) or 0),
            "latest_decision": str(trend.get("latest_decision") or ""),
            "latest_effectiveness_rate": self._safe_float(trend.get("latest_effectiveness_rate")),
            "delta_effectiveness_rate": self._safe_float(trend.get("delta_effectiveness_rate")),
            "trend_status": str(trend.get("trend_status") or ""),
            "trend_reason": str(trend.get("trend_reason") or ""),
            "retire_recommended": bool(trend.get("retire_recommended", False)),
        }

    def _reader_storybook_title_homogenization_release_evidence(
        self,
        *,
        world_id: str,
    ) -> Dict[str, Any]:
        history_payload = load_reader_storybook_title_homogenization_history(
            base_dir=self.base_dir
        )
        trend_payload = build_reader_storybook_title_homogenization_trend(history_payload)
        history_summary = summarize_reader_storybook_title_homogenization_history(
            history_payload,
            trend_payload,
        )
        promoted_pairs = promoted_reader_storybook_title_homogenization_pairs_for_world(
            trend_payload,
            world_id=world_id,
        )
        return {
            "reader_storybook_title_homogenization_history_summary": history_summary,
            "reader_storybook_title_homogenization_trend": trend_payload,
            "reader_storybook_title_homogenization_promoted_pairs": promoted_pairs,
        }

    def _build_longform_500_release_evidence_bundle(self, cross_pack_summary: Dict[str, Any]) -> Dict[str, Any]:
        static_signoff = dict(cross_pack_summary.get("longform_500_signoff", {}))
        interactive_signoff = dict(cross_pack_summary.get("longform_500_interactive_signoff", {}))
        human_closeout = dict(cross_pack_summary.get("longform_500_human_review_closeout", {}))
        ending_signoff = dict(cross_pack_summary.get("longform_500_ending_signoff", {}))
        review_sample_coverage_500 = dict(cross_pack_summary.get("review_sample_coverage_500", {}))

        static_artifact = self._artifact_candidate(
            "artifacts/longform/longform_500_rerun_all_v5_aggregated.json",
            "artifacts/longform/longform_500_rerun_all_v3.json",
            "artifacts/longform/longform_500_rerun_all_v5.json",
        )
        bundle_artifact = self._artifact_candidate(
            "artifacts/longform/longform_500_release_evidence_bundle.json",
        )
        interactive_artifact = self._artifact_candidate(
            "artifacts/longform/longform_500_interactive_rerun_all_aggregated.json",
        )
        human_review_artifact = self._artifact_candidate(
            "artifacts/longform/longform_500_human_review_execution.json",
        )

        static_metrics = self._artifact_metrics(static_artifact)
        interactive_metrics = self._artifact_metrics(interactive_artifact)
        human_metrics = self._artifact_metrics(human_review_artifact)

        required_components = {
            "static_ready": bool(static_signoff.get("ready", False)),
            "interactive_ready": bool(interactive_signoff.get("ready", False)),
            "human_review_closeout_ready": bool(human_closeout.get("ready", False)),
            "ending_signoff_ready": bool(ending_signoff.get("ready", False)),
        }
        combined_ready = all(required_components.values())
        blocking_worlds = sorted(
            {
                str(world_id)
                for payload in [static_signoff, interactive_signoff, human_closeout, ending_signoff]
                for world_id in list(payload.get("blocking_worlds", []))
                if str(world_id)
            }
        )
        watch_worlds = sorted(
            {
                str(world_id)
                for payload in [static_signoff, interactive_signoff, human_closeout, ending_signoff]
                for world_id in list(payload.get("watch_worlds", []))
                if str(world_id) and str(world_id) not in blocking_worlds
            }
        )
        return {
            "generated_at": self._utcnow(),
            "bundle_artifact": bundle_artifact or {},
            "static_artifact": static_artifact or {},
            "interactive_artifact": interactive_artifact or {},
            "human_review_artifact": human_review_artifact or {},
            "static_signoff": static_signoff,
            "interactive_signoff": interactive_signoff,
            "human_review_closeout": human_closeout,
            "ending_signoff": ending_signoff,
            "combined_signoff": {
                "status": "ready" if combined_ready else "watch",
                "ready": combined_ready,
                "reason": "longform_500_release_bundle_ready" if combined_ready else "longform_500_release_bundle_watch",
                "required_evidence": [
                    "longform_500_signoff.ready",
                    "longform_500_interactive_signoff.ready",
                    "longform_500_human_review_closeout.ready",
                    "longform_500_ending_signoff.ready",
                ],
                "blocking_worlds": blocking_worlds,
                "watch_worlds": watch_worlds,
            },
            "summary_metrics": {
                "static_cross_pack_pass_rate": static_metrics.get("cross_pack_pass_rate"),
                "static_gate_pass_rate": dict(static_metrics.get("longform_500_summary", {})).get("gate_pass_rate"),
                "interactive_cross_pack_pass_rate": interactive_metrics.get("cross_pack_pass_rate"),
                "interactive_gate_pass_rate": dict(interactive_metrics.get("longform_500_interactive_summary", {})).get("gate_pass_rate"),
                "human_reviewed_target_count": int(review_sample_coverage_500.get("human_reviewed_target_count", 0) or 0),
                "ending_window_human_reviewed_count": int(review_sample_coverage_500.get("ending_window_human_reviewed_count", 0) or 0),
            },
            "release_ready": combined_ready,
        }

    def _build_longform_1000_release_evidence_bundle(self, cross_pack_summary: Dict[str, Any]) -> Dict[str, Any]:
        static_signoff = dict(cross_pack_summary.get("longform_1000_readiness", {}))
        interactive_signoff = dict(cross_pack_summary.get("longform_1000_interactive_signoff", {}))
        human_closeout = dict(cross_pack_summary.get("longform_1000_human_review_closeout", {}))
        feasibility = dict(cross_pack_summary.get("longform_1000_feasibility", {}))
        review_sample_coverage_1000 = dict(cross_pack_summary.get("review_sample_coverage_1000", {}))

        static_artifact = self._artifact_candidate(
            "artifacts/longform/longform_1000_diagnostics_all_v6_aggregated.json",
            "artifacts/longform/longform_1000_diagnostics_all_v5_aggregated.json",
        )
        bundle_artifact = self._artifact_candidate(
            "artifacts/longform/longform_1000_release_evidence_bundle.json",
        )
        interactive_artifact = self._artifact_candidate(
            "artifacts/longform/longform_1000_interactive_rerun_all_aggregated.json",
        )
        human_review_artifact = self._artifact_candidate(
            "artifacts/longform/longform_1000_human_review_execution.json",
        )

        static_metrics = self._artifact_metrics(static_artifact)
        interactive_metrics = self._artifact_metrics(interactive_artifact)

        required_components = {
            "static_ready": bool(static_signoff.get("ready", False)),
            "interactive_ready": bool(interactive_signoff.get("ready", False)),
            "human_review_closeout_ready": bool(human_closeout.get("ready", False)),
        }
        combined_ready = all(required_components.values())
        blocking_worlds = sorted(
            {
                str(world_id)
                for payload in [static_signoff, interactive_signoff, human_closeout]
                for world_id in list(payload.get("blocking_worlds", []))
                if str(world_id)
            }
        )
        watch_worlds = sorted(
            {
                str(world_id)
                for payload in [static_signoff, interactive_signoff, human_closeout]
                for world_id in list(payload.get("watch_worlds", []))
                if str(world_id) and str(world_id) not in blocking_worlds
            }
        )
        return {
            "generated_at": self._utcnow(),
            "bundle_artifact": bundle_artifact or {},
            "static_artifact": static_artifact or {},
            "interactive_artifact": interactive_artifact or {},
            "human_review_artifact": human_review_artifact or {},
            "static_signoff": static_signoff,
            "interactive_signoff": interactive_signoff,
            "human_review_closeout": human_closeout,
            "feasibility": feasibility,
            "combined_signoff": {
                "status": "ready" if combined_ready else "watch",
                "ready": combined_ready,
                "reason": "longform_1000_release_bundle_ready" if combined_ready else "longform_1000_release_bundle_watch",
                "required_evidence": [
                    "longform_1000_readiness.ready",
                    "longform_1000_interactive_signoff.ready",
                    "longform_1000_human_review_closeout.ready",
                ],
                "blocking_worlds": blocking_worlds,
                "watch_worlds": watch_worlds,
            },
            "summary_metrics": {
                "static_cross_pack_pass_rate": static_metrics.get("cross_pack_pass_rate"),
                "static_diagnostic_pass_rate": dict(static_metrics.get("longform_1000_summary", {})).get("diagnostic_pass_rate"),
                "interactive_cross_pack_pass_rate": interactive_metrics.get("cross_pack_pass_rate"),
                "interactive_gate_pass_rate": dict(interactive_metrics.get("longform_1000_interactive_summary", {})).get("gate_pass_rate"),
                "human_reviewed_target_count": int(review_sample_coverage_1000.get("human_reviewed_target_count", 0) or 0),
                "planned_target_count": int(review_sample_coverage_1000.get("planned_target_count", 0) or 0),
                "feasibility_status": feasibility.get("status"),
            },
            "release_ready": combined_ready,
        }

    def _build_release_evidence_bundle(self, cross_pack_summary: Dict[str, Any]) -> Dict[str, Any]:
        benchmark_mode = str(cross_pack_summary.get("benchmark_mode") or "")
        longform_1000_readiness = dict(cross_pack_summary.get("longform_1000_readiness") or {})
        longform_1000_interactive_signoff = dict(cross_pack_summary.get("longform_1000_interactive_signoff") or {})
        longform_1000_human_review_closeout = dict(cross_pack_summary.get("longform_1000_human_review_closeout") or {})
        batch_validation = dict(cross_pack_summary.get("strategy_bundle_batch_validation") or {})
        resolved_strategy_bundle_id = str(batch_validation.get("strategy_bundle_id") or "").strip()
        if not resolved_strategy_bundle_id:
            resolved_strategy_bundle_id = str(
                dict((cross_pack_summary.get("strategy_validation_summary") or {}).get("bundle_groups", [{}])[0]).get("strategy_bundle_id") or ""
            ).strip()
        batch_validation_history = dict(cross_pack_summary.get("strategy_bundle_batch_validation_history") or {})
        if not batch_validation_history and resolved_strategy_bundle_id:
            batch_validation_history = list_strategy_bundle_batch_validation_history(
                repository=self.repository,
                strategy_bundle_id=resolved_strategy_bundle_id,
                limit=5,
            )
        batch_validation_trend = dict(cross_pack_summary.get("strategy_bundle_batch_validation_trend") or {})
        if not batch_validation_trend and resolved_strategy_bundle_id:
            batch_validation_trend = build_strategy_bundle_batch_validation_trend(batch_validation_history)
        if (
            benchmark_mode in {"longform_1000_diagnostics", "longform_1000_interactive"}
            or bool(longform_1000_readiness.get("ready", False))
            or bool(longform_1000_interactive_signoff.get("ready", False))
            or bool(longform_1000_human_review_closeout.get("ready", False))
        ):
            bundle = self._build_longform_1000_release_evidence_bundle(cross_pack_summary)
        else:
            bundle = self._build_longform_500_release_evidence_bundle(cross_pack_summary)
        bundle["strategy_bundle_batch_validation"] = batch_validation
        bundle["strategy_bundle_batch_validation_summary"] = self._summarize_strategy_bundle_batch_validation(batch_validation)
        bundle["strategy_bundle_batch_validation_history"] = batch_validation_history
        bundle["strategy_bundle_batch_validation_trend"] = batch_validation_trend
        bundle["strategy_bundle_batch_validation_history_summary"] = self._summarize_strategy_bundle_batch_validation_history(
            batch_validation_history,
            batch_validation_trend,
        )
        return bundle

    def _author_longform_capability(self, world_version: Optional[Any]) -> Dict[str, Any]:
        if world_version is None:
            return {}
        metadata = dict((world_version.worldpack_json or {}).get("metadata") or {})
        if not (
            metadata.get("author_brief")
            or metadata.get("entry_mode")
            or metadata.get("claim_safe_band")
            or metadata.get("requested_target_chapters")
            or metadata.get("longform_readiness")
        ):
            return {}
        return build_longform_capability_payload(
            base_dir=self.base_dir,
            repository=self.repository,
            worldpack_payload=dict(world_version.worldpack_json or {}),
            version=world_version,
        )

    def _ops_release_ready_band(
        self,
        *,
        longform_signoff: Dict[str, Any],
        interactive_longform_signoff: Dict[str, Any],
        longform_250_signoff: Dict[str, Any],
        longform_250_interactive_signoff: Dict[str, Any],
        longform_250_human_review_closeout: Dict[str, Any],
        longform_500_release_bundle: Dict[str, Any],
        longform_1000_release_bundle: Dict[str, Any],
    ) -> Optional[str]:
        if bool(dict(longform_1000_release_bundle.get("combined_signoff") or {}).get("ready", False)):
            return "1000"
        if bool(dict(longform_500_release_bundle.get("combined_signoff") or {}).get("ready", False)):
            return "500"
        if (
            bool(longform_250_signoff.get("ready", False))
            and bool(longform_250_interactive_signoff.get("ready", False))
            and bool(longform_250_human_review_closeout.get("ready", False))
        ):
            return "250"
        if str(longform_signoff.get("status") or "") != "blocked" and str(interactive_longform_signoff.get("status") or "") != "blocked":
            return "100"
        return None

    def _author_claim_alignment(
        self,
        *,
        author_capability: Dict[str, Any],
        ops_release_ready_band: Optional[str],
    ) -> Dict[str, Any]:
        if not author_capability:
            return {
                "claim_safe_band": None,
                "ops_release_ready_band": ops_release_ready_band,
                "aligned": True,
                "reason": "author_longform_claim_not_asserted",
                "blocking_worlds": [],
            }
        claim_safe_band = str(author_capability.get("claim_safe_band") or "").strip() or None
        if not claim_safe_band:
            return {
                "claim_safe_band": None,
                "ops_release_ready_band": ops_release_ready_band,
                "aligned": True,
                "reason": "author_claim_safe_band_missing",
                "blocking_worlds": [],
            }
        if not ops_release_ready_band:
            return {
                "claim_safe_band": claim_safe_band,
                "ops_release_ready_band": None,
                "aligned": False,
                "reason": "ops_release_ready_band_missing",
                "blocking_worlds": [],
            }
        aligned = band_rank(claim_safe_band) <= band_rank(ops_release_ready_band)
        return {
            "claim_safe_band": claim_safe_band,
            "ops_release_ready_band": ops_release_ready_band,
            "aligned": aligned,
            "reason": "author_claim_aligned" if aligned else "author_claim_exceeds_ops_release_ready_band",
            "blocking_worlds": [],
        }

    def _augment_release_evidence_bundle(
        self,
        *,
        release_evidence_bundle: Dict[str, Any],
        author_capability: Dict[str, Any],
        author_claim_alignment: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = dict(release_evidence_bundle or {})
        combined_signoff = dict(bundle.get("combined_signoff") or {})
        required_evidence = list(combined_signoff.get("required_evidence") or [])
        if "author_longform_claim_alignment.ready" not in required_evidence:
            required_evidence.append("author_longform_claim_alignment.ready")
        combined_ready = bool(combined_signoff.get("ready", False)) and bool(author_claim_alignment.get("aligned"))
        bundle["author_longform_capability"] = author_capability
        bundle["author_claim_alignment"] = author_claim_alignment
        bundle["combined_signoff"] = {
            **combined_signoff,
            "ready": combined_ready,
            "status": "ready" if combined_ready else "watch",
            "reason": combined_signoff.get("reason") if author_claim_alignment.get("aligned") else str(author_claim_alignment.get("reason") or "author_claim_exceeds_ops_release_ready_band"),
            "required_evidence": required_evidence,
        }
        bundle["release_ready"] = combined_ready
        return bundle

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
        longform_signoff = dict(cross_pack_summary.get("longform_l1_signoff", {}))
        interactive_longform_signoff = dict(cross_pack_summary.get("interactive_longform_signoff", {}))
        longform_250_signoff = dict(cross_pack_summary.get("longform_250_signoff", {}))
        longform_250_interactive_signoff = dict(cross_pack_summary.get("longform_250_interactive_signoff", {}))
        longform_250_human_review_closeout = dict(cross_pack_summary.get("longform_250_human_review_closeout", {}))
        longform_500_signoff = dict(cross_pack_summary.get("longform_500_signoff", {}))
        longform_500_interactive_signoff = dict(cross_pack_summary.get("longform_500_interactive_signoff", {}))
        longform_1000_readiness = dict(cross_pack_summary.get("longform_1000_readiness", {}))
        longform_1000_interactive_signoff = dict(cross_pack_summary.get("longform_1000_interactive_signoff", {}))
        longform_1000_feasibility = dict(cross_pack_summary.get("longform_1000_feasibility", {}))
        longform_1000_human_review_closeout = dict(cross_pack_summary.get("longform_1000_human_review_closeout", {}))
        review_sample_coverage_250 = dict(cross_pack_summary.get("review_sample_coverage_250", {}))
        longform_500_human_review_closeout = dict(cross_pack_summary.get("longform_500_human_review_closeout", {}))
        longform_500_ending_signoff = dict(cross_pack_summary.get("longform_500_ending_signoff", {}))
        review_sample_coverage_500 = dict(cross_pack_summary.get("review_sample_coverage_500", {}))
        review_sample_coverage_1000 = dict(cross_pack_summary.get("review_sample_coverage_1000", {}))
        has_longform_1000_contract = bool(cross_pack_summary.get("longform_1000_readiness") or cross_pack_summary.get("longform_1000_feasibility"))
        longform_500_release_bundle = self._build_longform_500_release_evidence_bundle(cross_pack_summary)
        longform_1000_release_bundle = self._build_longform_1000_release_evidence_bundle(cross_pack_summary) if has_longform_1000_contract else {}
        author_capability = self._author_longform_capability(world_version)
        ops_release_ready_band = self._ops_release_ready_band(
            longform_signoff=longform_signoff,
            interactive_longform_signoff=interactive_longform_signoff,
            longform_250_signoff=longform_250_signoff,
            longform_250_interactive_signoff=longform_250_interactive_signoff,
            longform_250_human_review_closeout=longform_250_human_review_closeout,
            longform_500_release_bundle=longform_500_release_bundle,
            longform_1000_release_bundle=longform_1000_release_bundle,
        )
        author_claim_alignment = self._author_claim_alignment(
            author_capability=author_capability,
            ops_release_ready_band=ops_release_ready_band,
        )
        has_author_longform_contract = bool(author_capability)
        character_fidelity_remediation_framework = dict(cross_pack_summary.get("character_fidelity_remediation_framework", {}))
        reader_storybook_title_homogenization_evidence = (
            self._reader_storybook_title_homogenization_release_evidence(
                world_id=world_version.world_id,
            )
        )
        reader_storybook_title_homogenization_history_summary = dict(
            reader_storybook_title_homogenization_evidence.get(
                "reader_storybook_title_homogenization_history_summary"
            )
            or {}
        )
        reader_storybook_title_homogenization_promoted_pairs = list(
            reader_storybook_title_homogenization_evidence.get(
                "reader_storybook_title_homogenization_promoted_pairs"
            )
            or []
        )
        top_failing_pack_ids = self._pack_ids(cross_pack_summary.get("top_failing_packs", simulation.get("top_failing_packs", [])))
        shared_quality_gate = dict(cross_pack_summary.get("phase_a_quality_gate") or simulation.get("phase_a_quality_gate") or evaluate_release_quality_gate(cross_pack_summary or simulation))
        content_quality_contract_gate = dict(
            cross_pack_summary.get("content_quality_contract_gate")
            or simulation.get("content_quality_contract_gate")
            or evaluate_content_quality_contract_gate(cross_pack_summary or simulation)
        )
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
                key="phase_a_quality_gate",
                label="Phase A 共享质量门槛",
                ok=bool(shared_quality_gate.get("ok", False)),
                reason=(
                    "phase_a_quality_gate_met"
                    if shared_quality_gate.get("ok", False)
                    else str((shared_quality_gate.get("failed_checks") or ["phase_a_quality_gate_blocked"])[0])
                ),
                source="release_quality_gate",
                owner="benchmark_reporting",
                severity="blocker",
                next_action="inspect_phase_a_quality_gate_failures",
                evidence=shared_quality_gate,
            ),
            self._checklist_item(
                key="content_quality_contract_gate",
                label="Content quality contract gate",
                ok=bool(content_quality_contract_gate.get("ok", False)),
                reason=(
                    "content_quality_contract_gate_met"
                    if content_quality_contract_gate.get("ok", False)
                    else str((content_quality_contract_gate.get("failed_checks") or ["content_quality_contract_gate_blocked"])[0])
                ),
                source="content_quality_contract_gate",
                owner="benchmark_reporting",
                severity="blocker",
                next_action="inspect_content_quality_contract_gate_failures",
                evidence=content_quality_contract_gate,
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
            self._checklist_item(
                key="author_longform_readiness",
                label="Author longform readiness",
                ok=(not has_author_longform_contract) or dict(author_capability.get("longform_readiness") or {}).get("status") == "ready",
                review_status=str(dict(author_capability.get("longform_readiness") or {}).get("status") or ("ready" if not has_author_longform_contract else "blocked")),
                reason=str(
                    ((dict(author_capability.get("longform_readiness") or {}).get("blockers") or [{}])[0] or {}).get("key")
                    or ("author_longform_claim_not_asserted" if not has_author_longform_contract else "author_longform_readiness_blocked")
                ),
                source="author_longform_readiness",
                owner="authoring_service",
                severity="blocker",
                next_action=str(((dict(author_capability.get("longform_readiness") or {}).get("recommended_actions") or ["focus_longform"])[0])),
                evidence={
                    "entry_mode": author_capability.get("entry_mode"),
                    "requested_target_band": author_capability.get("requested_target_band"),
                    "supported_target_band": author_capability.get("supported_target_band"),
                    "claim_safe_band": author_capability.get("claim_safe_band"),
                    "status": dict(author_capability.get("longform_readiness") or {}).get("status"),
                    "blockers": list(dict(author_capability.get("longform_readiness") or {}).get("blockers") or []),
                    "structure_counts": dict(author_capability.get("structure_counts") or {}),
                },
            ),
            self._checklist_item(
                key="author_longform_claim_alignment",
                label="Author claim aligns with ops release band",
                ok=bool(author_claim_alignment.get("aligned")),
                review_status="ready" if author_claim_alignment.get("aligned") else "blocked",
                reason=str(author_claim_alignment.get("reason") or "author_claim_exceeds_ops_release_ready_band"),
                source="author_longform_claim_alignment",
                owner="ops_release",
                severity="blocker",
                next_action="inspect_release_evidence_bundle",
                evidence={
                    "entry_mode": author_capability.get("entry_mode"),
                    "requested_target_band": author_capability.get("requested_target_band"),
                    "claim_safe_band": author_claim_alignment.get("claim_safe_band"),
                    "ops_release_ready_band": author_claim_alignment.get("ops_release_ready_band"),
                    "aligned": bool(author_claim_alignment.get("aligned")),
                    "status": dict(author_capability.get("longform_readiness") or {}).get("status"),
                    "blockers": list(dict(author_capability.get("longform_readiness") or {}).get("blockers") or []),
                },
            ),
            self._checklist_item(
                key="longform_l1_signoff",
                label="Longform L1 sign-off",
                ok=longform_signoff.get("status") != "blocked",
                review_status=str(longform_signoff.get("status") or "watch"),
                reason=str(longform_signoff.get("reason") or "longform_l1_signoff_missing"),
                source="longform_l1_signoff",
                owner="benchmark_reporting",
                severity="high",
                next_action=(
                    "rerun_longform_100_signoff"
                    if str(longform_signoff.get("status") or "watch") == "watch"
                    else "continue_lane_a_polish"
                ),
                evidence={
                    "status": longform_signoff.get("status"),
                    "ready": bool(longform_signoff.get("ready", False)),
                    "blocking_worlds": list(longform_signoff.get("blocking_worlds", [])),
                    "watch_worlds": list(longform_signoff.get("watch_worlds", [])),
                },
            ),
        ] + (
            [
                self._checklist_item(
                    key="interactive_100_readiness",
                    label="Interactive 100 readiness",
                    ok=interactive_longform_signoff.get("status") != "blocked",
                    review_status=str(interactive_longform_signoff.get("status") or "watch"),
                    reason=str(interactive_longform_signoff.get("reason") or "interactive_longform_signoff_missing"),
                    source="interactive_longform_signoff",
                    owner="benchmark_reporting",
                    severity="high",
                    next_action=(
                        "rerun_longform_100_interactive_signoff"
                        if str(interactive_longform_signoff.get("status") or "watch") == "watch"
                        else "continue_interactive_lane_a_polish"
                    ),
                    evidence={
                        "status": interactive_longform_signoff.get("status"),
                        "ready": bool(interactive_longform_signoff.get("ready", False)),
                        "blocking_worlds": list(interactive_longform_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(interactive_longform_signoff.get("watch_worlds", [])),
                    },
                )
            ]
            if interactive_longform_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_250_readiness",
                    label="Longform 250 readiness",
                    ok=True,
                    review_status=str(longform_250_signoff.get("status") or "watch"),
                    reason=str(longform_250_signoff.get("reason") or "longform_250_signoff_missing"),
                    source="longform_250_signoff",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "execute_longform_250_review_sampling"
                        if not bool(review_sample_coverage_250.get("closeout_ready", False))
                        else (
                            "rerun_longform_250_benchmark"
                            if str(longform_250_signoff.get("status") or "watch") == "watch"
                            else "review_longform_250_evidence"
                        )
                    ),
                    evidence={
                        "status": longform_250_signoff.get("status"),
                        "ready": bool(longform_250_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_250_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_250_signoff.get("watch_worlds", [])),
                        "review_sample_closeout_status": review_sample_coverage_250.get("closeout_status"),
                        "review_sample_closeout_ready": bool(review_sample_coverage_250.get("closeout_ready", False)),
                        "executed_target_count": int(review_sample_coverage_250.get("executed_target_count", 0) or 0),
                        "planned_target_count": int(review_sample_coverage_250.get("planned_target_count", 0) or 0),
                    },
                )
            ]
            if longform_250_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="interactive_250_readiness",
                    label="Interactive 250 readiness",
                    ok=True,
                    review_status=str(longform_250_interactive_signoff.get("status") or "watch"),
                    reason=str(longform_250_interactive_signoff.get("reason") or "longform_250_interactive_signoff_missing"),
                    source="longform_250_interactive_signoff",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_250_interactive_benchmark"
                        if str(longform_250_interactive_signoff.get("status") or "watch") == "watch"
                        else "review_longform_250_interactive_evidence"
                    ),
                    evidence={
                        "status": longform_250_interactive_signoff.get("status"),
                        "ready": bool(longform_250_interactive_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_250_interactive_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_250_interactive_signoff.get("watch_worlds", [])),
                    },
                )
            ]
            if longform_250_interactive_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_250_human_review_closeout",
                    label="Longform 250 human-review closeout",
                    ok=True,
                    review_status=str(longform_250_human_review_closeout.get("status") or "watch"),
                    reason=str(longform_250_human_review_closeout.get("reason") or "longform_250_human_review_closeout_missing"),
                    source="longform_250_human_review_closeout",
                    owner="ops_review",
                    severity="info",
                    next_action=(
                        "capture_longform_250_human_reviews"
                        if str(longform_250_human_review_closeout.get("status") or "watch") == "watch"
                        else "review_longform_250_human_closeout"
                    ),
                    evidence={
                        "status": longform_250_human_review_closeout.get("status"),
                        "ready": bool(longform_250_human_review_closeout.get("ready", False)),
                        "blocking_worlds": list(longform_250_human_review_closeout.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_250_human_review_closeout.get("watch_worlds", [])),
                        "human_closeout_status": review_sample_coverage_250.get("human_closeout_status"),
                        "human_closeout_ready": bool(review_sample_coverage_250.get("human_closeout_ready", False)),
                        "human_reviewed_target_count": int(review_sample_coverage_250.get("human_reviewed_target_count", 0) or 0),
                        "planned_target_count": int(review_sample_coverage_250.get("planned_target_count", 0) or 0),
                    },
                )
            ]
            if longform_250_human_review_closeout
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_500_readiness",
                    label="Longform 500 readiness",
                    ok=True,
                    review_status=str(longform_500_signoff.get("status") or "watch"),
                    reason=str(longform_500_signoff.get("reason") or "longform_500_signoff_missing"),
                    source="longform_500_signoff",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_500_benchmark"
                        if str(longform_500_signoff.get("status") or "watch") == "watch"
                        else "review_longform_500_evidence"
                    ),
                    evidence={
                        "status": longform_500_signoff.get("status"),
                        "ready": bool(longform_500_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_500_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_500_signoff.get("watch_worlds", [])),
                    },
                )
            ]
            if longform_500_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="interactive_500_readiness",
                    label="Interactive 500 readiness",
                    ok=True,
                    review_status=str(longform_500_interactive_signoff.get("status") or "watch"),
                    reason=str(longform_500_interactive_signoff.get("reason") or "longform_500_interactive_signoff_missing"),
                    source="longform_500_interactive_signoff",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_500_interactive_benchmark"
                        if str(longform_500_interactive_signoff.get("status") or "watch") == "watch"
                        else "review_longform_500_interactive_evidence"
                    ),
                    evidence={
                        "status": longform_500_interactive_signoff.get("status"),
                        "ready": bool(longform_500_interactive_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_500_interactive_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_500_interactive_signoff.get("watch_worlds", [])),
                    },
                )
            ]
            if longform_500_interactive_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_1000_readiness",
                    label="Longform 1000 readiness",
                    ok=True,
                    review_status=str(longform_1000_readiness.get("status") or "watch"),
                    reason=str(longform_1000_readiness.get("reason") or "longform_1000_readiness_missing"),
                    source="longform_1000_readiness",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_1000_diagnostics"
                        if str(longform_1000_readiness.get("status") or "watch") == "watch"
                        else "review_longform_1000_readiness"
                    ),
                    evidence={
                        "status": longform_1000_readiness.get("status"),
                        "ready": bool(longform_1000_readiness.get("ready", False)),
                        "blocking_worlds": list(longform_1000_readiness.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_1000_readiness.get("watch_worlds", [])),
                    },
                )
            ]
            if longform_1000_readiness
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_1000_feasibility",
                    label="Longform 1000 feasibility",
                    ok=True,
                    review_status=str(longform_1000_feasibility.get("status") or "watch"),
                    reason=str(longform_1000_feasibility.get("reason") or "longform_1000_feasibility_missing"),
                    source="longform_1000_feasibility",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_1000_diagnostics"
                        if str(longform_1000_feasibility.get("status") or "watch") == "watch"
                        else "review_longform_1000_feasibility"
                    ),
                    evidence={
                        "status": longform_1000_feasibility.get("status"),
                        "ready": bool(longform_1000_feasibility.get("ready", False)),
                        "blocking_worlds": list(longform_1000_feasibility.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_1000_feasibility.get("watch_worlds", [])),
                        "diagnostic_pass_rate": longform_1000_feasibility.get("diagnostic_pass_rate"),
                    },
                )
            ]
            if longform_1000_feasibility
            else []
        ) + (
            [
                self._checklist_item(
                    key="interactive_1000_readiness",
                    label="Interactive 1000 readiness",
                    ok=True,
                    review_status=str(longform_1000_interactive_signoff.get("status") or "watch"),
                    reason=str(longform_1000_interactive_signoff.get("reason") or "longform_1000_interactive_signoff_missing"),
                    source="longform_1000_interactive_signoff",
                    owner="benchmark_reporting",
                    severity="info",
                    next_action=(
                        "rerun_longform_1000_interactive_benchmark"
                        if str(longform_1000_interactive_signoff.get("status") or "watch") == "watch"
                        else "review_longform_1000_interactive_evidence"
                    ),
                    evidence={
                        "status": longform_1000_interactive_signoff.get("status"),
                        "ready": bool(longform_1000_interactive_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_1000_interactive_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_1000_interactive_signoff.get("watch_worlds", [])),
                    },
                )
            ]
            if longform_1000_interactive_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_1000_human_review_closeout",
                    label="Longform 1000 human-review closeout",
                    ok=True,
                    review_status=str(longform_1000_human_review_closeout.get("status") or "watch"),
                    reason=str(longform_1000_human_review_closeout.get("reason") or "longform_1000_human_review_closeout_missing"),
                    source="longform_1000_human_review_closeout",
                    owner="ops_review",
                    severity="info",
                    next_action=(
                        "capture_longform_1000_human_reviews"
                        if str(longform_1000_human_review_closeout.get("status") or "watch") == "watch"
                        else "review_longform_1000_human_closeout"
                    ),
                    evidence={
                        "status": longform_1000_human_review_closeout.get("status"),
                        "ready": bool(longform_1000_human_review_closeout.get("ready", False)),
                        "blocking_worlds": list(longform_1000_human_review_closeout.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_1000_human_review_closeout.get("watch_worlds", [])),
                        "human_closeout_status": review_sample_coverage_1000.get("human_closeout_status"),
                        "human_closeout_ready": bool(review_sample_coverage_1000.get("human_closeout_ready", False)),
                        "human_reviewed_target_count": int(review_sample_coverage_1000.get("human_reviewed_target_count", 0) or 0),
                        "planned_target_count": int(review_sample_coverage_1000.get("planned_target_count", 0) or 0),
                    },
                )
            ]
            if longform_1000_human_review_closeout
            else []
        ) + (
            [
                self._checklist_item(
                    key="q06_character_fidelity_framework",
                    label="Q06 character fidelity framework",
                    ok=True,
                    review_status="watch" if character_fidelity_remediation_framework.get("available") else "ready",
                    reason=(
                        "q06_character_fidelity_framework_active"
                        if character_fidelity_remediation_framework.get("available")
                        else "q06_character_fidelity_framework_clear"
                    ),
                    source="character_fidelity_remediation_framework",
                    owner="planner",
                    severity="info",
                    next_action=(
                        "tighten_character_cards_and_emotion_action_policies"
                        if character_fidelity_remediation_framework.get("available")
                        else "none"
                    ),
                    evidence=character_fidelity_remediation_framework,
                )
            ]
            if cross_pack_summary
            else []
        ) + (
            [
                self._checklist_item(
                    key="reader_storybook_title_homogenization_trend",
                    label="Reader storybook title homogenization trend",
                    ok=True,
                    review_status="watch",
                    reason="reader_storybook_title_homogenization_promoted:%s" % (
                        "/".join(
                            f"{item.get('jade_world_id')}@{int(item.get('consecutive_warning_count', 0) or 0)}"
                            for item in reader_storybook_title_homogenization_promoted_pairs
                        )
                        or "watch"
                    ),
                    source="reader_storybook_long_route_smoke",
                    owner="ops_release",
                    severity="info",
                    next_action="inspect_release_evidence_bundle",
                    evidence={
                        "threshold": int(
                            reader_storybook_title_homogenization_history_summary.get("threshold", 0)
                            or 0
                        ),
                        "entry_count": int(
                            reader_storybook_title_homogenization_history_summary.get("entry_count", 0)
                            or 0
                        ),
                        "latest_generated_at": reader_storybook_title_homogenization_history_summary.get(
                            "latest_generated_at"
                        ),
                        "trend_status": reader_storybook_title_homogenization_history_summary.get(
                            "trend_status"
                        ),
                        "trend_reason": reader_storybook_title_homogenization_history_summary.get(
                            "trend_reason"
                        ),
                        "promoted_pairs": reader_storybook_title_homogenization_promoted_pairs,
                    },
                )
            ]
            if reader_storybook_title_homogenization_promoted_pairs
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_500_human_review_closeout",
                    label="Longform 500 human-review closeout",
                    ok=True,
                    review_status=str(longform_500_human_review_closeout.get("status") or "watch"),
                    reason=str(longform_500_human_review_closeout.get("reason") or "longform_500_human_review_closeout_missing"),
                    source="longform_500_human_review_closeout",
                    owner="ops_review",
                    severity="info",
                    next_action=(
                        "capture_longform_500_human_reviews"
                        if str(longform_500_human_review_closeout.get("status") or "watch") == "watch"
                        else "review_longform_500_human_closeout"
                    ),
                    evidence={
                        "status": longform_500_human_review_closeout.get("status"),
                        "ready": bool(longform_500_human_review_closeout.get("ready", False)),
                        "blocking_worlds": list(longform_500_human_review_closeout.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_500_human_review_closeout.get("watch_worlds", [])),
                        "human_closeout_status": review_sample_coverage_500.get("human_closeout_status"),
                        "human_closeout_ready": bool(review_sample_coverage_500.get("human_closeout_ready", False)),
                        "human_reviewed_target_count": int(review_sample_coverage_500.get("human_reviewed_target_count", 0) or 0),
                        "planned_target_count": int(review_sample_coverage_500.get("planned_target_count", 0) or 0),
                    },
                )
            ]
            if longform_500_human_review_closeout
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_500_ending_signoff",
                    label="Longform 500 ending sign-off",
                    ok=True,
                    review_status=str(longform_500_ending_signoff.get("status") or "watch"),
                    reason=str(longform_500_ending_signoff.get("reason") or "longform_500_ending_signoff_missing"),
                    source="longform_500_ending_signoff",
                    owner="ops_review",
                    severity="info",
                    next_action=(
                        "capture_longform_500_ending_window_human_reviews"
                        if str(longform_500_ending_signoff.get("status") or "watch") == "watch"
                        else "review_longform_500_ending_evidence"
                    ),
                    evidence={
                        "status": longform_500_ending_signoff.get("status"),
                        "ready": bool(longform_500_ending_signoff.get("ready", False)),
                        "blocking_worlds": list(longform_500_ending_signoff.get("blocking_worlds", [])),
                        "watch_worlds": list(longform_500_ending_signoff.get("watch_worlds", [])),
                        "ending_window_label": review_sample_coverage_500.get("ending_window_label"),
                        "ending_window_human_closeout_ready": bool(review_sample_coverage_500.get("ending_window_human_closeout_ready", False)),
                        "ending_window_human_reviewed_count": int(review_sample_coverage_500.get("ending_window_human_reviewed_count", 0) or 0),
                        "ending_window_target_count": int(review_sample_coverage_500.get("ending_window_target_count", 0) or 0),
                    },
                )
            ]
            if longform_500_ending_signoff
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_500_release_bundle",
                    label="Longform 500 release bundle",
                    ok=True,
                    review_status=str(dict(longform_500_release_bundle.get("combined_signoff", {})).get("status") or "watch"),
                    reason=str(dict(longform_500_release_bundle.get("combined_signoff", {})).get("reason") or "longform_500_release_bundle_missing"),
                    source="longform_500_release_bundle",
                    owner="ops_release",
                    severity="info",
                    next_action=(
                        "inspect_release_evidence_bundle"
                        if bool(longform_500_release_bundle.get("release_ready", False))
                        else "close_longform_500_release_evidence_gaps"
                    ),
                    evidence={
                        "release_ready": bool(longform_500_release_bundle.get("release_ready", False)),
                        "component_readiness": {
                            "static": bool(longform_500_signoff.get("ready", False)),
                            "interactive": bool(longform_500_interactive_signoff.get("ready", False)),
                            "human_review_closeout": bool(longform_500_human_review_closeout.get("ready", False)),
                            "ending_signoff": bool(longform_500_ending_signoff.get("ready", False)),
                        },
                        "artifact_paths": {
                            "bundle_json": dict(longform_500_release_bundle.get("bundle_artifact", {})).get("json"),
                            "static_json": dict(longform_500_release_bundle.get("static_artifact", {})).get("json"),
                            "interactive_json": dict(longform_500_release_bundle.get("interactive_artifact", {})).get("json"),
                            "human_review_json": dict(longform_500_release_bundle.get("human_review_artifact", {})).get("json"),
                        },
                    },
                )
            ]
            if longform_500_release_bundle
            else []
        ) + (
            [
                self._checklist_item(
                    key="longform_1000_release_bundle",
                    label="Longform 1000 release bundle",
                    ok=True,
                    review_status=str(dict(longform_1000_release_bundle.get("combined_signoff", {})).get("status") or "watch"),
                    reason=str(dict(longform_1000_release_bundle.get("combined_signoff", {})).get("reason") or "longform_1000_release_bundle_missing"),
                    source="longform_1000_release_bundle",
                    owner="ops_release",
                    severity="info",
                    next_action=(
                        "inspect_release_evidence_bundle"
                        if bool(longform_1000_release_bundle.get("release_ready", False))
                        else "close_longform_1000_release_evidence_gaps"
                    ),
                    evidence={
                        "release_ready": bool(longform_1000_release_bundle.get("release_ready", False)),
                        "component_readiness": {
                            "static": bool(longform_1000_readiness.get("ready", False)),
                            "interactive": bool(longform_1000_interactive_signoff.get("ready", False)),
                            "human_review_closeout": bool(longform_1000_human_review_closeout.get("ready", False)),
                        },
                        "artifact_paths": {
                            "bundle_json": dict(longform_1000_release_bundle.get("bundle_artifact", {})).get("json"),
                            "static_json": dict(longform_1000_release_bundle.get("static_artifact", {})).get("json"),
                            "interactive_json": dict(longform_1000_release_bundle.get("interactive_artifact", {})).get("json"),
                            "human_review_json": dict(longform_1000_release_bundle.get("human_review_artifact", {})).get("json"),
                        },
                    },
                )
            ]
            if longform_1000_release_bundle
            else []
        )

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
        checklist = self.build_publish_checklist(world_version_id)
        errors.extend(
            str(item.get("reason") or "")
            for item in checklist
            if not item.get("ok") and str(item.get("reason") or "").strip()
        )
        errors = list(dict.fromkeys(errors))
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
            try:
                record_publish_preflight_quality_event(
                    self.repository,
                    world_id=world_version.world_id,
                    world_version_id=world_version_id,
                    status="blocked",
                    reason_codes=errors,
                    reviewer_id=reviewer_id,
                )
            except Exception:
                pass
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

        try:
            record_publish_preflight_quality_event(
                self.repository,
                world_id=world_version.world_id,
                world_version_id=world_version_id,
                status="passed",
                reason_codes=[],
                reviewer_id=reviewer_id,
            )
        except Exception:
            pass
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
        cross_pack_summary = dict((latest_simulation.get("cross_pack_summary") or {}))
        release_evidence_bundle = self._build_release_evidence_bundle(cross_pack_summary)
        author_longform_capability = self._author_longform_capability(active_version)
        ops_release_ready_band = self._ops_release_ready_band(
            longform_signoff=dict(cross_pack_summary.get("longform_l1_signoff", {})),
            interactive_longform_signoff=dict(cross_pack_summary.get("interactive_longform_signoff", {})),
            longform_250_signoff=dict(cross_pack_summary.get("longform_250_signoff", {})),
            longform_250_interactive_signoff=dict(cross_pack_summary.get("longform_250_interactive_signoff", {})),
            longform_250_human_review_closeout=dict(cross_pack_summary.get("longform_250_human_review_closeout", {})),
            longform_500_release_bundle=self._build_longform_500_release_evidence_bundle(cross_pack_summary),
            longform_1000_release_bundle=self._build_longform_1000_release_evidence_bundle(cross_pack_summary)
            if bool(cross_pack_summary.get("longform_1000_readiness") or cross_pack_summary.get("longform_1000_feasibility"))
            else {},
        )
        author_claim_alignment = self._author_claim_alignment(
            author_capability=author_longform_capability,
            ops_release_ready_band=ops_release_ready_band,
        )
        release_evidence_bundle = self._augment_release_evidence_bundle(
            release_evidence_bundle=release_evidence_bundle,
            author_capability=author_longform_capability,
            author_claim_alignment=author_claim_alignment,
        )
        release_evidence_bundle.update(
            self._reader_storybook_title_homogenization_release_evidence(
                world_id=world_id,
            )
        )
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
            "release_evidence_bundle": release_evidence_bundle,
            "author_longform_capability": author_longform_capability,
            "author_claim_alignment": author_claim_alignment,
            "longform_1000_readiness": dict(cross_pack_summary.get("longform_1000_readiness") or {}),
            "longform_1000_interactive_signoff": dict(cross_pack_summary.get("longform_1000_interactive_signoff") or {}),
            "longform_1000_human_review_closeout": dict(cross_pack_summary.get("longform_1000_human_review_closeout") or {}),
            "longform_1000_feasibility": dict((latest_simulation.get("cross_pack_summary") or {}).get("longform_1000_feasibility") or {}),
            "character_fidelity_remediation_framework": dict((latest_simulation.get("cross_pack_summary") or {}).get("character_fidelity_remediation_framework") or {}),
            "quality_projection_summary": self.quality_projection.quality_summary(
                world_version_id=active_version_id,
                limit=12,
            ),
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
