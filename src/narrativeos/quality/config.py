from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import QualityPolicy, QualityRule


BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_QUALITY_CONFIG_DIR = BASE_DIR / "configs" / "quality"

RISK_TIER_IDS = {"L1", "L2", "L3", "L4"}


class QualityConfigError(ValueError):
    pass


@dataclass(frozen=True)
class QualityConfigPaths:
    config_dir: Path = DEFAULT_QUALITY_CONFIG_DIR

    @property
    def scenarios(self) -> Path:
        return self.config_dir / "scenarios.yaml"

    @property
    def risk_tiers(self) -> Path:
        return self.config_dir / "risk_tiers.yaml"

    @property
    def rules(self) -> Path:
        return self.config_dir / "rules.yaml"

    @property
    def content_rubrics(self) -> Path:
        return self.config_dir / "content_rubrics.yaml"

    @property
    def review_policies(self) -> Path:
        return self.config_dir / "review_policies.yaml"

    @property
    def grounding_policies(self) -> Path:
        return self.config_dir / "grounding_policies.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise QualityConfigError("quality_config_missing:%s" % path) from exc
    if not isinstance(payload, dict):
        raise QualityConfigError("quality_config_invalid_root:%s" % path)
    return payload


def _require_keys(payload: Dict[str, Any], keys: List[str], *, context: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise QualityConfigError("%s_missing_keys:%s" % (context, ",".join(missing)))


def load_quality_scenarios(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.scenarios)
    _require_keys(payload, ["config_version", "scenarios"], context="quality_scenarios")
    scenarios = list(payload.get("scenarios") or [])
    scenario_map: Dict[str, Dict[str, Any]] = {}
    for item in scenarios:
        if not isinstance(item, dict):
            raise QualityConfigError("quality_scenarios_invalid_item")
        _require_keys(
            item,
            ["scenario_id", "surface", "description", "default_risk_tier", "quality_policy_id"],
            context="quality_scenario",
        )
        risk_tier = str(item.get("default_risk_tier") or "")
        if risk_tier not in RISK_TIER_IDS:
            raise QualityConfigError("quality_scenario_risk_tier_invalid:%s" % risk_tier)
        scenario_id = str(item.get("scenario_id") or "")
        scenario_map[scenario_id] = dict(item)
    return {
        "config_version": str(payload.get("config_version") or ""),
        "scenarios": list(scenario_map.values()),
        "scenario_map": scenario_map,
    }


def load_quality_risk_tiers(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.risk_tiers)
    _require_keys(payload, ["config_version", "risk_tiers"], context="quality_risk_tiers")
    tier_map: Dict[str, Dict[str, Any]] = {}
    for item in list(payload.get("risk_tiers") or []):
        if not isinstance(item, dict):
            raise QualityConfigError("quality_risk_tiers_invalid_item")
        _require_keys(
            item,
            ["risk_tier", "label", "description", "requires_human_review", "blocks_on_veto_only"],
            context="quality_risk_tier",
        )
        tier_id = str(item.get("risk_tier") or "")
        if tier_id not in RISK_TIER_IDS:
            raise QualityConfigError("quality_risk_tier_invalid:%s" % tier_id)
        tier_map[tier_id] = dict(item)
    return {
        "config_version": str(payload.get("config_version") or ""),
        "risk_tiers": list(tier_map.values()),
        "risk_tier_map": tier_map,
    }


def load_quality_rules(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.rules)
    _require_keys(payload, ["config_version", "rules"], context="quality_rules")
    rules = [QualityRule.from_dict(item) for item in list(payload.get("rules") or [])]
    return {
        "config_version": str(payload.get("config_version") or ""),
        "rules": rules,
        "rule_map": {item.rule_id: item for item in rules},
    }


def load_content_rubrics_config(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.content_rubrics)
    _require_keys(payload, ["config_version", "rubrics"], context="content_rubrics")
    rubrics = dict(payload.get("rubrics") or {})
    if "default" not in rubrics:
        raise QualityConfigError("content_rubrics_missing_default")
    default = dict(rubrics.get("default") or {})
    _require_keys(default, ["rubric_version", "overall_scale", "dimensions", "veto_reason_codes"], context="content_rubric")
    return {
        "config_version": str(payload.get("config_version") or ""),
        "rubrics": rubrics,
    }


def load_quality_review_policies(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.review_policies)
    _require_keys(payload, ["config_version", "policies"], context="quality_review_policies")
    policies = [QualityPolicy.from_dict(item) for item in list(payload.get("policies") or [])]
    return {
        "config_version": str(payload.get("config_version") or ""),
        "policies": policies,
        "policy_map": {item.policy_id: item for item in policies},
    }


def load_quality_config_bundle(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    scenarios = load_quality_scenarios(resolved_paths)
    risk_tiers = load_quality_risk_tiers(resolved_paths)
    rules = load_quality_rules(resolved_paths)
    rubrics = load_content_rubrics_config(resolved_paths)
    policies = load_quality_review_policies(resolved_paths)

    scenario_ids = set(scenarios["scenario_map"].keys())
    rule_ids = set(rules["rule_map"].keys())
    risk_tier_ids = set(risk_tiers["risk_tier_map"].keys())

    for policy in policies["policies"]:
        if policy.scenario_id not in scenario_ids:
            raise QualityConfigError("quality_policy_unknown_scenario:%s" % policy.scenario_id)
        if policy.risk_tier not in risk_tier_ids:
            raise QualityConfigError("quality_policy_unknown_risk_tier:%s" % policy.risk_tier)
        missing_rule_ids = [rule_id for rule_id in policy.rule_ids if rule_id not in rule_ids]
        if missing_rule_ids:
            raise QualityConfigError("quality_policy_unknown_rules:%s" % ",".join(missing_rule_ids))

    scenario_policy_ids = {item["quality_policy_id"] for item in scenarios["scenarios"]}
    missing_policies = sorted(policy_id for policy_id in scenario_policy_ids if policy_id not in policies["policy_map"])
    if missing_policies:
        raise QualityConfigError("quality_scenario_missing_policy:%s" % ",".join(missing_policies))

    return {
        "scenarios": scenarios,
        "risk_tiers": risk_tiers,
        "rules": rules,
        "content_rubrics": rubrics,
        "review_policies": policies,
    }


def load_grounding_policies(paths: Optional[QualityConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or QualityConfigPaths()
    payload = _load_yaml(resolved_paths.grounding_policies)
    _require_keys(payload, ["config_version", "policies"], context="grounding_policies")
    return {
        "config_version": str(payload.get("config_version") or ""),
        "policies": dict(payload.get("policies") or {}),
    }


def get_quality_policy_for_scenario(
    scenario_id: str,
    paths: Optional[QualityConfigPaths] = None,
) -> QualityPolicy:
    bundle = load_quality_config_bundle(paths)
    scenario = dict(bundle["scenarios"]["scenario_map"].get(str(scenario_id) or "") or {})
    if not scenario:
        raise QualityConfigError("quality_scenario_unknown:%s" % scenario_id)
    policy_id = str(scenario.get("quality_policy_id") or "")
    policy = bundle["review_policies"]["policy_map"].get(policy_id)
    if policy is None:
        raise QualityConfigError("quality_policy_unknown:%s" % policy_id)
    return policy
