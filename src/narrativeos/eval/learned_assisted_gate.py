from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..services.training_signal import TrainingSignalService
from .learned_inference import LearnedInferenceService, default_learned_artifact_dir
from .learned_rollout import build_learned_rollout_summary


ASSISTED_GATE_CONFIG_ASSET_TYPE = "learned_experiment"
ASSISTED_GATE_CONFIG_ASSET_ID = "assisted_gate_config"
ASSISTED_GATE_DECISION_ASSET_TYPE = "learned_experiment_decision"
ASSISTED_GATE_DECISION_ASSET_ID = "assisted_gate"
VALID_MODES = {"shadow_only", "assisted_gate"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "mode": "shadow_only",
        "bucket_percentage": 0,
        "confidence_threshold": 0.9,
        "min_example_count": 3,
        "min_high_confidence_blocks": 2,
        "required_block_share": 0.5,
        "world_allowlist": [],
        "require_active_rollout": True,
        "require_candidate_ready": False,
        "require_approved_promotion": True,
        "allow_assisted_block": True,
        "allow_assisted_pass": False,
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
        asset_type=ASSISTED_GATE_CONFIG_ASSET_TYPE,
        asset_id=ASSISTED_GATE_CONFIG_ASSET_ID,
    )
    return dict(records[0]) if records else None


def load_assisted_gate_config(repository: SQLAlchemyPlatformRepository) -> Dict[str, Any]:
    record = _latest_config_record(repository)
    config = dict(_default_config())
    if not record:
        return {
            "track": "evaluator",
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
    config["confidence_threshold"] = max(0.0, min(1.0, float(config.get("confidence_threshold", 0.9) or 0.9)))
    config["min_example_count"] = max(1, int(config.get("min_example_count", 3) or 3))
    config["min_high_confidence_blocks"] = max(1, int(config.get("min_high_confidence_blocks", 2) or 2))
    config["required_block_share"] = max(0.0, min(1.0, float(config.get("required_block_share", 0.5) or 0.5)))
    config["world_allowlist"] = sorted({str(item) for item in config.get("world_allowlist", []) if str(item).strip()})
    config["allow_assisted_pass"] = False
    return {
        "track": "evaluator",
        "config": config,
        "updated_at": record.get("updated_at"),
        "reviewer_id": record.get("reviewer_id"),
        "reason": payload.get("reason"),
        "status": record.get("status"),
    }


def save_assisted_gate_config(
    *,
    repository: SQLAlchemyPlatformRepository,
    reviewer_id: str,
    reason: str,
    enabled: bool,
    mode: str,
    bucket_percentage: int,
    confidence_threshold: float,
    min_example_count: int,
    min_high_confidence_blocks: int,
    required_block_share: float,
    world_allowlist: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError("invalid_assisted_gate_mode")
    config = {
        **_default_config(),
        "enabled": bool(enabled),
        "mode": mode,
        "bucket_percentage": max(0, min(100, int(bucket_percentage))),
        "confidence_threshold": max(0.0, min(1.0, float(confidence_threshold))),
        "min_example_count": max(1, int(min_example_count)),
        "min_high_confidence_blocks": max(1, int(min_high_confidence_blocks)),
        "required_block_share": max(0.0, min(1.0, float(required_block_share))),
        "world_allowlist": sorted({str(item) for item in world_allowlist or [] if str(item).strip()}),
        "allow_assisted_pass": False,
    }
    status = "enabled" if config["enabled"] else "disabled"
    record = repository.save_review_record(
        {
            "asset_type": ASSISTED_GATE_CONFIG_ASSET_TYPE,
            "asset_id": ASSISTED_GATE_CONFIG_ASSET_ID,
            "status": status,
            "reviewer_id": reviewer_id,
            "notes": json.dumps(
                {
                    "track": "evaluator",
                    "reason": reason,
                    "config": config,
                },
                ensure_ascii=False,
            ),
        }
    )
    return {
        "track": "evaluator",
        "config": config,
        "updated_at": record.get("updated_at"),
        "reviewer_id": reviewer_id,
        "reason": reason,
        "status": status,
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
    elif receipt.get("assisted_action") == "block_publish":
        status = "assisted_block"
    elif receipt.get("would_block"):
        status = "would_block"
    return repository.save_review_record(
        {
            "asset_type": ASSISTED_GATE_DECISION_ASSET_TYPE,
            "asset_id": ASSISTED_GATE_DECISION_ASSET_ID,
            "status": status,
            "reviewer_id": "system",
            "notes": json.dumps(receipt, ensure_ascii=False),
        }
    )


def list_assisted_gate_decisions(
    repository: SQLAlchemyPlatformRepository,
    *,
    limit: Optional[int] = 20,
) -> List[Dict[str, Any]]:
    records = repository.list_review_records(
        asset_type=ASSISTED_GATE_DECISION_ASSET_TYPE,
        asset_id=ASSISTED_GATE_DECISION_ASSET_ID,
    )
    decisions: List[Dict[str, Any]] = []
    selected_records = records if limit is None else records[:limit]
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


def evaluate_assisted_gate_decision(
    *,
    repository: SQLAlchemyPlatformRepository,
    world_version_id: str,
    simulation: Dict[str, Any],
    rule_gate_errors: Sequence[str],
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
    learned_inference_service: Optional[LearnedInferenceService] = None,
    persist_receipt: bool = True,
) -> Dict[str, Any]:
    config_payload = load_assisted_gate_config(repository)
    config = dict(config_payload.get("config", {}))
    world_id = str(simulation.get("world_id") or repository.get_world_version(world_version_id).world_id)
    rollout_summary = build_learned_rollout_summary(
        repository=repository,
        world_id=world_id,
        world_version_id=world_version_id,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    evaluator_rollout = dict(rollout_summary.get("tracks", {}).get("evaluator", {}))
    learned_inference = learned_inference_service or LearnedInferenceService(
        Path(evaluator_artifact_dir or default_learned_artifact_dir(Path(__file__).resolve().parents[3]))
    )
    training_signal = TrainingSignalService(repository)
    examples = training_signal.evaluator_examples_from_reports(
        simulation.get("chapter_evaluations", []),
        world_id=world_id,
    )
    bucket_match = _bucket_match(world_version_id, int(config.get("bucket_percentage", 0) or 0))
    allowlist = set(config.get("world_allowlist", []))
    in_allowlist = not allowlist or world_id in allowlist

    guardrails: List[str] = []
    if not config.get("enabled"):
        guardrails.append("experiment_disabled")
    if not in_allowlist:
        guardrails.append("world_not_in_allowlist")
    if not bucket_match:
        guardrails.append("not_in_bucket")
    if not examples:
        guardrails.append("missing_chapter_evaluations")
    if config.get("require_active_rollout") and evaluator_rollout.get("rollout_status") != "active":
        guardrails.append("rollout_not_active")
    if config.get("require_candidate_ready") and not evaluator_rollout.get("candidate_ready"):
        guardrails.append("candidate_not_ready")
    if config.get("require_approved_promotion") and evaluator_rollout.get("latest_approval_status") != "approved":
        guardrails.append("promotion_not_approved")
    if rule_gate_errors:
        guardrails.append("rule_gate_already_blocked")

    prediction_counts: Dict[str, int] = {}
    high_confidence_block_count = 0
    predicted_block_examples: List[str] = []
    prediction_failures = 0
    for example in examples:
        prediction = learned_inference.predict_example(example)
        predicted = prediction.get("predicted_decision")
        if not predicted:
            prediction_failures += 1
            continue
        prediction_counts[predicted] = prediction_counts.get(predicted, 0) + 1
        if predicted == "block" and float(prediction.get("confidence") or 0.0) >= float(config.get("confidence_threshold", 0.9)):
            high_confidence_block_count += 1
            predicted_block_examples.append(str(example.get("chapter_id")))

    example_count = len(examples)
    block_share = round(high_confidence_block_count / float(max(1, example_count)), 3)
    would_block = bool(
        example_count >= int(config.get("min_example_count", 3))
        and high_confidence_block_count >= int(config.get("min_high_confidence_blocks", 2))
        and block_share >= float(config.get("required_block_share", 0.5))
    )

    guardrail_status = "eligible"
    if config.get("mode") == "shadow_only":
        guardrail_status = "shadow_only"
    if guardrails:
        guardrail_status = "skipped" if config.get("mode") != "shadow_only" else "shadow_only"

    assisted_action = "none"
    final_gate_errors = list(rule_gate_errors)
    if (
        config.get("enabled")
        and config.get("mode") == "assisted_gate"
        and not guardrails
        and config.get("allow_assisted_block")
        and would_block
    ):
        assisted_action = "block_publish"
        final_gate_errors = [*final_gate_errors, "assisted_learned_gate_block"]

    receipt = {
        "generated_at": _utcnow(),
        "experiment_name": "assisted_gate",
        "track": "evaluator",
        "world_id": world_id,
        "world_version_id": world_version_id,
        "mode": config.get("mode"),
        "enabled": bool(config.get("enabled")),
        "bucket_match": bucket_match,
        "world_in_allowlist": in_allowlist,
        "guardrail_status": guardrail_status,
        "guardrails": guardrails,
        "config_snapshot": config,
        "rollout_snapshot": {
            "rollout_status": evaluator_rollout.get("rollout_status"),
            "candidate_ready": bool(evaluator_rollout.get("candidate_ready")),
            "latest_approval_status": evaluator_rollout.get("latest_approval_status"),
            "safe_to_rollout": bool(evaluator_rollout.get("safe_to_rollout")),
        },
        "rule_gate_errors_before": list(rule_gate_errors),
        "final_gate_errors": final_gate_errors,
        "learned_signal": {
            "example_count": example_count,
            "prediction_counts": prediction_counts,
            "prediction_failures": prediction_failures,
            "high_confidence_block_count": high_confidence_block_count,
            "block_share": block_share,
            "predicted_block_examples": predicted_block_examples[:5],
        },
        "would_block": would_block,
        "assisted_action": assisted_action,
        "guardrails_and_rollback": {
            "guardrails": [
                "rollout must be active",
                "promotion must still be approved",
                "bucket and allowlist must match",
                "rule-blocked versions are never force-passed",
            ],
            "rollback_conditions": [
                "promotion approval becomes stale or revoked",
                "rollout is rolled_back",
                "ops disables experiment config",
            ],
        },
    }
    if persist_receipt:
        _save_decision_receipt(repository=repository, receipt=receipt)
    return receipt


def build_assisted_gate_summary(
    *,
    repository: SQLAlchemyPlatformRepository,
    limit: int = 20,
    evaluator_artifact_dir: Optional[Path] = None,
    reranker_artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    config_payload = load_assisted_gate_config(repository)
    rollout_summary = build_learned_rollout_summary(
        repository=repository,
        evaluator_artifact_dir=evaluator_artifact_dir,
        reranker_artifact_dir=reranker_artifact_dir,
    )
    decisions = list_assisted_gate_decisions(repository, limit=limit)
    counters = {
        "decision_count": len(decisions),
        "shadow_count": sum(1 for item in decisions if item.get("status") == "shadow"),
        "skipped_count": sum(1 for item in decisions if item.get("status") == "skipped"),
        "would_block_count": sum(1 for item in decisions if item.get("would_block")),
        "assisted_block_count": sum(1 for item in decisions if item.get("assisted_action") == "block_publish"),
        "in_bucket_count": sum(1 for item in decisions if item.get("bucket_match")),
    }
    evaluator_rollout = dict(rollout_summary.get("tracks", {}).get("evaluator", {}))
    if not config_payload["config"].get("enabled"):
        recommended_next_action = "enable_shadow_only_capture"
    elif evaluator_rollout.get("rollout_status") != "active":
        recommended_next_action = "activate_evaluator_rollout_before_assist"
    elif config_payload["config"].get("mode") == "shadow_only":
        recommended_next_action = "review_shadow_decisions_before_assisted_gate"
    else:
        recommended_next_action = "monitor_assisted_gate_block_rate"
    return {
        "generated_at": _utcnow(),
        "track": "evaluator",
        "config": config_payload,
        "rollout_summary": {
            "rollout_status": evaluator_rollout.get("rollout_status"),
            "candidate_ready": bool(evaluator_rollout.get("candidate_ready")),
            "latest_approval_status": evaluator_rollout.get("latest_approval_status"),
            "safe_to_rollout": bool(evaluator_rollout.get("safe_to_rollout")),
        },
        "guardrails": [
            "must be explicitly enabled",
            "must hit bucket and optional world allowlist",
            "must keep evaluator rollout active and approved",
            "never force-pass a rule-blocked version",
        ],
        "rollback_conditions": [
            "disable experiment config",
            "roll back evaluator rollout",
            "revoke evaluator promotion approval",
        ],
        "counters": counters,
        "recent_decisions": decisions,
        "recommended_next_action": recommended_next_action,
    }
