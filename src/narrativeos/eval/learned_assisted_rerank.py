from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..models import ScoredCandidate
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .artifact_registry import default_learned_reranker_artifact_dir
from .learned_rollout import build_learned_rollout_summary


ASSISTED_RERANK_CONFIG_ASSET_TYPE = "learned_experiment"
ASSISTED_RERANK_CONFIG_ASSET_ID = "assisted_rerank_config"
ASSISTED_RERANK_DECISION_ASSET_TYPE = "learned_experiment_decision"
ASSISTED_RERANK_DECISION_ASSET_ID = "assisted_rerank"
VALID_MODES = {"shadow_only", "assisted_rerank"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "mode": "shadow_only",
        "bucket_percentage": 0,
        "confidence_threshold": 0.65,
        "candidate_window": 3,
        "max_score_gap": 0.08,
        "world_allowlist": [],
        "require_active_rollout": True,
        "require_candidate_ready": False,
        "require_approved_promotion": True,
        "allowed_beat_indexes": [1],
    }


def _parse_notes(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bucket_match(world_version_id: str, bucket_percentage: int) -> bool:
    if bucket_percentage <= 0:
        return False
    if bucket_percentage >= 100:
        return True
    digest = hashlib.md5(world_version_id.encode("utf-8")).hexdigest()
    sample = int(digest[:8], 16) % 100
    return sample < bucket_percentage


def _latest_config_record(repository: SQLAlchemyPlatformRepository) -> Optional[Dict[str, Any]]:
    records = repository.list_review_records(
        asset_type=ASSISTED_RERANK_CONFIG_ASSET_TYPE,
        asset_id=ASSISTED_RERANK_CONFIG_ASSET_ID,
    )
    return dict(records[0]) if records else None


def load_assisted_rerank_config(repository: SQLAlchemyPlatformRepository) -> Dict[str, Any]:
    record = _latest_config_record(repository)
    config = dict(_default_config())
    if not record:
        return {
            "track": "reranker",
            "config": config,
            "updated_at": None,
            "reviewer_id": None,
            "reason": None,
            "status": "disabled",
        }
    payload = _parse_notes(record.get("notes"))
    config.update({key: value for key, value in dict(payload.get("config", {})).items() if key in config})
    config["mode"] = str(config.get("mode") or "shadow_only")
    if config["mode"] not in VALID_MODES:
        config["mode"] = "shadow_only"
    config["bucket_percentage"] = max(0, min(100, int(config.get("bucket_percentage", 0) or 0)))
    config["confidence_threshold"] = max(0.0, min(1.0, float(config.get("confidence_threshold", 0.65) or 0.65)))
    config["candidate_window"] = max(2, int(config.get("candidate_window", 3) or 3))
    config["max_score_gap"] = max(0.0, float(config.get("max_score_gap", 0.08) or 0.08))
    config["world_allowlist"] = sorted({str(item) for item in config.get("world_allowlist", []) if str(item).strip()})
    config["allowed_beat_indexes"] = [int(item) for item in config.get("allowed_beat_indexes", [1]) if int(item) >= 1] or [1]
    return {
        "track": "reranker",
        "config": config,
        "updated_at": record.get("updated_at"),
        "reviewer_id": record.get("reviewer_id"),
        "reason": payload.get("reason"),
        "status": record.get("status"),
    }


def save_assisted_rerank_config(
    *,
    repository: SQLAlchemyPlatformRepository,
    reviewer_id: str,
    reason: str,
    enabled: bool,
    mode: str,
    bucket_percentage: int,
    confidence_threshold: float,
    candidate_window: int,
    max_score_gap: float,
    world_allowlist: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError("invalid_assisted_rerank_mode")
    config = {
        **_default_config(),
        "enabled": bool(enabled),
        "mode": mode,
        "bucket_percentage": max(0, min(100, int(bucket_percentage))),
        "confidence_threshold": max(0.0, min(1.0, float(confidence_threshold))),
        "candidate_window": max(2, int(candidate_window)),
        "max_score_gap": max(0.0, float(max_score_gap)),
        "world_allowlist": sorted({str(item) for item in world_allowlist or [] if str(item).strip()}),
    }
    status = "enabled" if config["enabled"] else "disabled"
    record = repository.save_review_record(
        {
            "asset_type": ASSISTED_RERANK_CONFIG_ASSET_TYPE,
            "asset_id": ASSISTED_RERANK_CONFIG_ASSET_ID,
            "status": status,
            "reviewer_id": reviewer_id,
            "notes": json.dumps(
                {
                    "track": "reranker",
                    "reason": reason,
                    "config": config,
                },
                ensure_ascii=False,
            ),
        }
    )
    return {
        "track": "reranker",
        "config": config,
        "updated_at": record.get("updated_at"),
        "reviewer_id": reviewer_id,
        "reason": reason,
        "status": status,
    }


class LearnedAssistedRerankService:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._cached_bundle: Optional[Dict[str, Any]] = None
        self._cached_signature: Optional[tuple] = None

    def _artifact_paths(self) -> Dict[str, Path]:
        return {
            "model": self.artifact_dir / "reranker_model.joblib",
        }

    def _signature(self) -> Optional[tuple]:
        paths = self._artifact_paths()
        if not all(path.exists() for path in paths.values()):
            return None
        return tuple(path.stat().st_mtime_ns for path in paths.values())

    def _load_bundle(self) -> Dict[str, Any]:
        signature = self._signature()
        if signature is None:
            raise FileNotFoundError("learned_reranker_artifact_missing")
        if self._cached_bundle is not None and self._cached_signature == signature:
            return self._cached_bundle
        from joblib import load

        bundle = load(self._artifact_paths()["model"])
        self._cached_bundle = bundle
        self._cached_signature = signature
        return bundle

    def availability(self) -> Dict[str, Any]:
        try:
            self._load_bundle()
        except FileNotFoundError:
            return {
                "available": False,
                "artifact_dir": str(self.artifact_dir),
                "reason": "artifact_missing",
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "available": False,
                "artifact_dir": str(self.artifact_dir),
                "reason": "artifact_load_failed",
                "error": str(exc),
            }
        return {
            "available": True,
            "artifact_dir": str(self.artifact_dir),
        }

    def _preference_strength(self, delta: float) -> str:
        absolute = abs(float(delta))
        if absolute >= 0.15:
            return "strong"
        if absolute >= 0.05:
            return "medium"
        return "weak"

    def _feature_payload(self, preferred: ScoredCandidate, alternative: ScoredCandidate, *, world_id: str) -> Dict[str, Any]:
        total_delta = float(preferred.total_score) - float(alternative.total_score)
        critic_delta = float(preferred.critic_penalty or 0.0) - float(alternative.critic_penalty or 0.0)
        payload: Dict[str, Any] = {
            "world_id": str(world_id),
            "preference_strength": self._preference_strength(total_delta),
            "pass_rate_delta": total_delta,
            "rewrite_rate_delta": -critic_delta,
            "block_rate_delta": critic_delta,
        }
        for component_name in sorted(set(preferred.components) | set(alternative.components)):
            payload[f"metric_delta::{component_name}"] = float(preferred.components.get(component_name, 0.0)) - float(
                alternative.components.get(component_name, 0.0)
            )
        payload[f"changed_section::{preferred.event.scene_function}"] = 1
        payload[f"changed_section::{alternative.event.scene_function}"] = 1
        return payload

    def compare(self, preferred: ScoredCandidate, alternative: ScoredCandidate, *, world_id: str) -> Dict[str, Any]:
        availability = self.availability()
        if not availability.get("available"):
            return {
                "available": False,
                "preferred_event_id": preferred.event.event_id,
                "alternative_event_id": alternative.event.event_id,
                "reason": availability.get("reason"),
            }
        bundle = self._load_bundle()
        classifier = bundle["classifier"]
        vectorizer = bundle["vectorizer"]

        def _probability(preferred_candidate: ScoredCandidate, alternative_candidate: ScoredCandidate) -> float:
            payload = self._feature_payload(preferred_candidate, alternative_candidate, world_id=world_id)
            features = vectorizer.transform([payload])
            if hasattr(classifier, "predict_proba"):
                probabilities = classifier.predict_proba(features)[0]
                classes = list(getattr(classifier, "classes_", []))
                if 1 in classes:
                    return float(probabilities[classes.index(1)])
                return float(max(probabilities))
            prediction = classifier.predict(features)[0]
            return 1.0 if int(prediction) == 1 else 0.0

        preferred_probability = _probability(preferred, alternative)
        alternative_probability = _probability(alternative, preferred)
        return {
            "available": True,
            "preferred_event_id": preferred.event.event_id,
            "alternative_event_id": alternative.event.event_id,
            "preferred_probability": round(preferred_probability, 4),
            "alternative_probability": round(alternative_probability, 4),
            "score_gap": round(float(preferred.total_score) - float(alternative.total_score), 4),
        }


def _save_decision_receipt(
    *,
    repository: SQLAlchemyPlatformRepository,
    receipt: Dict[str, Any],
) -> Dict[str, Any]:
    status = str(receipt.get("assisted_action") or "shadow")
    if receipt.get("guardrail_status") == "skipped":
        status = "skipped"
    elif receipt.get("mode") == "shadow_only":
        status = "shadow"
    elif receipt.get("assisted_action") == "rerank_top_candidate":
        status = "assisted_rerank"
    elif receipt.get("would_swap"):
        status = "would_swap"
    return repository.save_review_record(
        {
            "asset_type": ASSISTED_RERANK_DECISION_ASSET_TYPE,
            "asset_id": ASSISTED_RERANK_DECISION_ASSET_ID,
            "status": status,
            "reviewer_id": "system",
            "notes": json.dumps(receipt, ensure_ascii=False),
        }
    )


def list_assisted_rerank_decisions(
    repository: SQLAlchemyPlatformRepository,
    *,
    limit: Optional[int] = 20,
) -> List[Dict[str, Any]]:
    records = repository.list_review_records(
        asset_type=ASSISTED_RERANK_DECISION_ASSET_TYPE,
        asset_id=ASSISTED_RERANK_DECISION_ASSET_ID,
    )
    selected_records = records if limit is None else records[:limit]
    decisions: List[Dict[str, Any]] = []
    for record in selected_records:
        payload = _parse_notes(record.get("notes"))
        decisions.append(
            {
                "review_id": record.get("review_id"),
                "status": record.get("status"),
                "updated_at": record.get("updated_at"),
                **payload,
            }
        )
    return decisions


def evaluate_assisted_rerank_candidates(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_id: str,
    world_version_id: str,
    ranked_candidates: Sequence[ScoredCandidate],
    beat_index: int,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
    rerank_service: Optional[LearnedAssistedRerankService] = None,
    persist_receipt: bool = True,
) -> Dict[str, Any]:
    config_payload = load_assisted_rerank_config(repository)
    config = dict(config_payload.get("config", {}))
    bucket_match = _bucket_match(world_version_id, int(config.get("bucket_percentage", 0) or 0))
    allowlist = set(config.get("world_allowlist", []))
    in_allowlist = not allowlist or world_id in allowlist
    rollout_summary = build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    reranker_rollout = dict(rollout_summary.get("tracks", {}).get("reranker", {}))
    service = rerank_service or LearnedAssistedRerankService(
        Path(reranker_artifact_dir or default_learned_reranker_artifact_dir(Path(__file__).resolve().parents[3]))
    )
    availability = service.availability()

    guardrails: List[str] = []
    if not config.get("enabled"):
        guardrails.append("experiment_disabled")
    if not in_allowlist:
        guardrails.append("world_not_in_allowlist")
    if not bucket_match:
        guardrails.append("not_in_bucket")
    if len(ranked_candidates) < 2:
        guardrails.append("insufficient_candidates")
    if beat_index not in list(config.get("allowed_beat_indexes", [1])):
        guardrails.append("beat_not_eligible")
    if config.get("require_active_rollout") and reranker_rollout.get("rollout_status") != "active":
        guardrails.append("rollout_not_active")
    if config.get("require_candidate_ready") and not reranker_rollout.get("candidate_ready"):
        guardrails.append("candidate_not_ready")
    if config.get("require_approved_promotion") and reranker_rollout.get("latest_approval_status") != "approved":
        guardrails.append("promotion_not_approved")
    if not availability.get("available"):
        guardrails.append(str(availability.get("reason") or "artifact_unavailable"))

    candidate_window = min(len(ranked_candidates), int(config.get("candidate_window", 3) or 3))
    top_candidates = list(ranked_candidates[:candidate_window])
    baseline_top = top_candidates[0] if top_candidates else None
    pairwise_comparisons: List[Dict[str, Any]] = []
    challenger = None
    challenger_probability = 0.0
    if baseline_top is not None and availability.get("available"):
        for alternative in top_candidates[1:]:
            comparison = service.compare(baseline_top, alternative, world_id=world_id)
            pairwise_comparisons.append(comparison)
            if (
                comparison.get("available")
                and float(comparison.get("alternative_probability", 0.0)) >= float(config.get("confidence_threshold", 0.65))
                and abs(float(comparison.get("score_gap", 0.0))) <= float(config.get("max_score_gap", 0.08))
                and float(comparison.get("alternative_probability", 0.0)) > challenger_probability
            ):
                challenger = alternative
                challenger_probability = float(comparison.get("alternative_probability", 0.0))

    would_swap = challenger is not None
    guardrail_status = "eligible"
    if config.get("mode") == "shadow_only":
        guardrail_status = "shadow_only"
    if guardrails:
        guardrail_status = "skipped" if config.get("mode") != "shadow_only" else "shadow_only"

    assisted_action = "none"
    reordered_candidates = list(ranked_candidates)
    if config.get("enabled") and config.get("mode") == "assisted_rerank" and not guardrails and would_swap:
        assisted_action = "rerank_top_candidate"
        reordered_candidates = [challenger] + [item for item in ranked_candidates if item.event.event_id != challenger.event.event_id]

    receipt = {
        "generated_at": _utcnow(),
        "experiment_name": "assisted_rerank",
        "track": "reranker",
        "world_id": world_id,
        "world_version_id": world_version_id,
        "mode": config.get("mode"),
        "enabled": bool(config.get("enabled")),
        "bucket_match": bucket_match,
        "world_in_allowlist": in_allowlist,
        "beat_index": beat_index,
        "guardrail_status": guardrail_status,
        "guardrails": guardrails,
        "config_snapshot": config,
        "rollout_snapshot": {
            "rollout_status": reranker_rollout.get("rollout_status"),
            "candidate_ready": bool(reranker_rollout.get("candidate_ready")),
            "latest_approval_status": reranker_rollout.get("latest_approval_status"),
            "safe_to_rollout": bool(reranker_rollout.get("safe_to_rollout")),
        },
        "baseline_event_id": baseline_top.event.event_id if baseline_top else None,
        "baseline_score": round(float(baseline_top.total_score), 4) if baseline_top else None,
        "candidate_count": len(ranked_candidates),
        "candidate_window": candidate_window,
        "pairwise_comparisons": pairwise_comparisons,
        "challenger_event_id": challenger.event.event_id if challenger else None,
        "challenger_score": round(float(challenger.total_score), 4) if challenger else None,
        "would_swap": would_swap,
        "assisted_action": assisted_action,
        "selected_event_id": reordered_candidates[0].event.event_id if reordered_candidates else None,
        "guardrails_and_rollback": {
            "guardrails": [
                "must be explicitly enabled",
                "must hit bucket and optional world allowlist",
                "must keep reranker rollout active",
                "must keep reranker promotion approved",
                "must stay within max_score_gap before swapping",
            ],
            "rollback_conditions": [
                "disable experiment config",
                "roll back reranker rollout",
                "revoke reranker promotion approval",
            ],
        },
    }
    if persist_receipt:
        _save_decision_receipt(repository=repository, receipt=receipt)
    return {
        "ranked_candidates": reordered_candidates,
        "receipt": receipt,
    }


def build_assisted_rerank_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    limit: int = 20,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    config_payload = load_assisted_rerank_config(repository)
    rollout_summary = build_learned_rollout_summary(
        repository=repository,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    reranker_rollout = dict(rollout_summary.get("tracks", {}).get("reranker", {}))
    decisions = list_assisted_rerank_decisions(repository, limit=limit)
    counters = {
        "decision_count": len(decisions),
        "shadow_count": sum(1 for item in decisions if item.get("status") == "shadow"),
        "skipped_count": sum(1 for item in decisions if item.get("status") == "skipped"),
        "would_swap_count": sum(1 for item in decisions if item.get("would_swap")),
        "assisted_swap_count": sum(1 for item in decisions if item.get("assisted_action") == "rerank_top_candidate"),
        "in_bucket_count": sum(1 for item in decisions if item.get("bucket_match")),
    }
    if not config_payload["config"].get("enabled"):
        recommended_next_action = "enable_shadow_only_rerank_capture"
    elif reranker_rollout.get("rollout_status") != "active":
        recommended_next_action = "activate_reranker_rollout_before_assist"
    elif config_payload["config"].get("mode") == "shadow_only":
        recommended_next_action = "review_shadow_rerank_receipts"
    else:
        recommended_next_action = "monitor_assisted_rerank_swap_rate"
    return {
        "generated_at": _utcnow(),
        "track": "reranker",
        "config": config_payload,
        "rollout_summary": {
            "rollout_status": reranker_rollout.get("rollout_status"),
            "candidate_ready": bool(reranker_rollout.get("candidate_ready")),
            "latest_approval_status": reranker_rollout.get("latest_approval_status"),
            "safe_to_rollout": bool(reranker_rollout.get("safe_to_rollout")),
        },
        "guardrails": [
            "must be explicitly enabled",
            "must hit bucket and optional world allowlist",
            "must keep reranker rollout active and approved",
            "must stay within max_score_gap before swapping",
        ],
        "rollback_conditions": [
            "disable experiment config",
            "roll back reranker rollout",
            "revoke reranker promotion approval",
        ],
        "counters": counters,
        "recent_decisions": decisions,
        "recommended_next_action": recommended_next_action,
    }
