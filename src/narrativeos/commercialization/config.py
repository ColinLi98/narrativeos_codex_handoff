from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import CommercialPlan


BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_COMMERCIALIZATION_CONFIG_DIR = BASE_DIR / "configs" / "commercialization"


class CommercializationConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CommercializationConfigPaths:
    config_dir: Path = DEFAULT_COMMERCIALIZATION_CONFIG_DIR

    @property
    def plans(self) -> Path:
        return self.config_dir / "plans.yaml"

    @property
    def billing_metering(self) -> Path:
        return self.config_dir / "billing_metering.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CommercializationConfigError("commercialization_config_missing:%s" % path) from exc
    if not isinstance(payload, dict):
        raise CommercializationConfigError("commercialization_config_invalid_root:%s" % path)
    return payload


def load_commercial_plans(paths: Optional[CommercializationConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or CommercializationConfigPaths()
    payload = _load_yaml(resolved_paths.plans)
    if "config_version" not in payload or "plans" not in payload:
        raise CommercializationConfigError("commercialization_plans_missing_keys")
    plans = [CommercialPlan.from_dict(item) for item in list(payload.get("plans") or [])]
    if not plans:
        raise CommercializationConfigError("commercialization_plans_empty")
    return {
        "config_version": str(payload.get("config_version") or ""),
        "plans": plans,
        "plan_map": {plan.plan_id: plan for plan in plans},
    }


def load_billing_metering(paths: Optional[CommercializationConfigPaths] = None) -> Dict[str, Any]:
    resolved_paths = paths or CommercializationConfigPaths()
    payload = _load_yaml(resolved_paths.billing_metering)
    if "config_version" not in payload or "metrics" not in payload:
        raise CommercializationConfigError("commercialization_billing_metering_missing_keys")
    metrics = dict(payload.get("metrics") or {})
    if not metrics:
        raise CommercializationConfigError("commercialization_billing_metering_empty")
    for metric_id, metric_payload in metrics.items():
        entry = dict(metric_payload or {})
        if "display_name" not in entry or "included_units" not in entry or "unit_price_usd" not in entry:
            raise CommercializationConfigError("commercialization_billing_metering_invalid:%s" % metric_id)
    return {
        "config_version": str(payload.get("config_version") or ""),
        "metrics": metrics,
        "credit_policy": dict(payload.get("credit_policy") or {}),
    }
