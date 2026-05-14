from __future__ import annotations

from typing import Any, Dict, List


def evaluate_content_quality_contract_gate(report: Dict[str, Any]) -> Dict[str, Any]:
    worlds = [dict(item or {}) for item in list(report.get("worlds") or [])]
    checks: List[Dict[str, Any]] = []
    failed_world_items: List[Dict[str, Any]] = []
    blocking_worlds: List[str] = []
    config_version = ""
    for world in worlds:
        world_id = str(world.get("world_id") or "")
        coverage = dict(world.get("content_quality_contract_coverage") or {})
        window_metrics = dict(world.get("content_quality_contract_window_metrics") or {})
        gate_enforced = bool(window_metrics.get("gate_enforced", coverage.get("gate_enforced", False)))
        if not bool(coverage.get("applicable")):
            continue
        if not gate_enforced:
            continue
        config_version = str(coverage.get("config_version") or config_version)
        if not bool(coverage.get("ok", False)):
            checks.append(
                {
                    "key": "asset_contract_coverage",
                    "world_id": world_id,
                    "ok": False,
                    "reason": "content_quality_contract_asset_coverage_missing",
                    "actual": list(coverage.get("failed_checks") or []),
                    "threshold": "full_coverage",
                }
            )
            blocking_worlds.append(world_id)
            failed_world_items.append(
                {
                    "world_id": world_id,
                    "reason": "content_quality_contract_asset_coverage_missing",
                    "failed_checks": list(coverage.get("failed_checks") or []),
                }
            )
        if bool(window_metrics.get("enabled")):
            thresholds = dict(window_metrics.get("thresholds") or {})
            for key, actual, threshold_key, reason in [
                ("early_window_q03_q04_share", float(window_metrics.get("early_window_q03_q04_share", 0.0) or 0.0), "early_window_q03_q04_share_max", "content_quality_contract_early_window_exceeded"),
                ("mid_window_repeat_breach_rate", float(window_metrics.get("mid_window_repeat_breach_rate", 0.0) or 0.0), "mid_window_repeat_breach_rate_max", "content_quality_contract_mid_repeat_exceeded"),
                ("mid_window_exposition_breach_rate", float(window_metrics.get("mid_window_exposition_breach_rate", 0.0) or 0.0), "mid_window_exposition_breach_rate_max", "content_quality_contract_mid_exposition_exceeded"),
                ("late_window_q09_breach_rate", float(window_metrics.get("late_window_q09_breach_rate", 0.0) or 0.0), "late_window_q09_breach_rate_max", "content_quality_contract_late_q09_exceeded"),
            ]:
                threshold = float(thresholds.get(threshold_key, 0.0) or 0.0)
                ok = actual <= threshold
                checks.append(
                    {
                        "key": key,
                        "world_id": world_id,
                        "ok": ok,
                        "reason": f"{reason}_met" if ok else reason,
                        "actual": round(actual, 3),
                        "threshold": round(threshold, 3),
                    }
                )
                if not ok and world_id not in blocking_worlds:
                    blocking_worlds.append(world_id)
                    failed_world_items.append(
                        {
                            "world_id": world_id,
                            "reason": reason,
                            "failed_checks": [key],
                        }
                    )
    failed_checks = [str(item.get("reason") or "") for item in checks if not item.get("ok")]
    return {
        "config_version": config_version,
        "ok": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "blocking_worlds": blocking_worlds,
        "failed_world_items": failed_world_items,
    }
