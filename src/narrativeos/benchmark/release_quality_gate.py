from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_RELEASE_QUALITY_GATE_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "release_quality_gate.json"
)
DEFAULT_RELEASE_QUALITY_GATE = {
    "config_version": "phase_a_quality_gate_v1",
    "cross_pack_pass_rate_min": 0.9,
    "weakest_pack_limit": 3,
    "weakest_pack_pass_rate_min": 0.55,
    "commercial_long_route_chapter_budget_min": 50,
    "commercial_long_route_weakest_long_route_quality_min": 0.5,
    "commercial_long_route_weakest_completion_ratio_min": 0.8,
    "commercial_long_route_weakest_mid_arc_drop_max": 0.35,
    "weakest_pack_issue_share_max": {
        "Q03": 0.35,
        "Q04": 0.3,
        "Q05": 0.3,
        "Q09": 0.2,
    },
}


def load_release_quality_gate_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_RELEASE_QUALITY_GATE_PATH
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        return {
            "config_version": str(payload.get("config_version") or DEFAULT_RELEASE_QUALITY_GATE["config_version"]),
            "cross_pack_pass_rate_min": float(
                payload.get("cross_pack_pass_rate_min", DEFAULT_RELEASE_QUALITY_GATE["cross_pack_pass_rate_min"])
            ),
            "weakest_pack_limit": int(payload.get("weakest_pack_limit", DEFAULT_RELEASE_QUALITY_GATE["weakest_pack_limit"])),
            "weakest_pack_pass_rate_min": float(
                payload.get("weakest_pack_pass_rate_min", DEFAULT_RELEASE_QUALITY_GATE["weakest_pack_pass_rate_min"])
            ),
            "commercial_long_route_chapter_budget_min": int(
                payload.get(
                    "commercial_long_route_chapter_budget_min",
                    DEFAULT_RELEASE_QUALITY_GATE["commercial_long_route_chapter_budget_min"],
                )
            ),
            "commercial_long_route_weakest_long_route_quality_min": float(
                payload.get(
                    "commercial_long_route_weakest_long_route_quality_min",
                    DEFAULT_RELEASE_QUALITY_GATE["commercial_long_route_weakest_long_route_quality_min"],
                )
            ),
            "commercial_long_route_weakest_completion_ratio_min": float(
                payload.get(
                    "commercial_long_route_weakest_completion_ratio_min",
                    DEFAULT_RELEASE_QUALITY_GATE["commercial_long_route_weakest_completion_ratio_min"],
                )
            ),
            "commercial_long_route_weakest_mid_arc_drop_max": float(
                payload.get(
                    "commercial_long_route_weakest_mid_arc_drop_max",
                    DEFAULT_RELEASE_QUALITY_GATE["commercial_long_route_weakest_mid_arc_drop_max"],
                )
            ),
            "weakest_pack_issue_share_max": {
                key: float(value)
                for key, value in dict(
                    payload.get("weakest_pack_issue_share_max", DEFAULT_RELEASE_QUALITY_GATE["weakest_pack_issue_share_max"])
                ).items()
            },
        }
    return dict(DEFAULT_RELEASE_QUALITY_GATE)


def _issue_share(issue_mix: List[Dict[str, Any]], issue_code: str) -> float:
    for item in issue_mix or []:
        if str(item.get("issue_code") or "") == issue_code:
            return float(item.get("share", 0.0) or 0.0)
    return 0.0


def _commercial_long_route_checks(report: Dict[str, Any], thresholds: Dict[str, Any]) -> List[Dict[str, Any]]:
    benchmark_mode = str(report.get("benchmark_mode") or "standard")
    chapter_budget = int(report.get("chapter_budget", 0) or 0)
    required_budget = int(thresholds.get("commercial_long_route_chapter_budget_min", 50) or 50)
    if benchmark_mode != "long_route" or chapter_budget < required_budget:
        return []

    weakest_limit = max(1, int(thresholds.get("weakest_pack_limit", 3) or 3))
    weakest_packs = list(report.get("weakest_packs") or report.get("top_failing_packs") or [])[:weakest_limit]
    quality_min = float(thresholds.get("commercial_long_route_weakest_long_route_quality_min", 0.5) or 0.5)
    completion_min = float(thresholds.get("commercial_long_route_weakest_completion_ratio_min", 0.8) or 0.8)
    mid_arc_drop_max = float(thresholds.get("commercial_long_route_weakest_mid_arc_drop_max", 0.35) or 0.35)

    missing_evidence: List[Dict[str, Any]] = []
    readability_failures: List[Dict[str, Any]] = []
    focus_issue_failures: List[Dict[str, Any]] = []
    focus_issue_limits = dict(thresholds.get("weakest_pack_issue_share_max", {}))
    for pack in weakest_packs:
        world_id = str(pack.get("world_id") or "")
        issue_mix = list(pack.get("issue_mix") or [])
        missing_keys = [
            key
            for key in ("long_route_quality", "mid_arc_drop", "completion_ratio", "stop_reason", "issue_mix")
            if key not in pack
        ]
        if missing_keys:
            missing_evidence.append({"world_id": world_id, "missing_keys": missing_keys})
            continue

        long_route_quality = float(pack.get("long_route_quality", 0.0) or 0.0)
        completion_ratio = float(pack.get("completion_ratio", 0.0) or 0.0)
        mid_arc_drop = float(pack.get("mid_arc_drop", 0.0) or 0.0)
        failed_metrics: List[str] = []
        if long_route_quality < quality_min:
            failed_metrics.append("long_route_quality")
        if completion_ratio < completion_min:
            failed_metrics.append("completion_ratio")
        if mid_arc_drop > mid_arc_drop_max:
            failed_metrics.append("mid_arc_drop")
        if failed_metrics:
            readability_failures.append(
                {
                    "world_id": world_id,
                    "failed_metrics": failed_metrics,
                    "long_route_quality": round(long_route_quality, 3),
                    "completion_ratio": round(completion_ratio, 3),
                    "mid_arc_drop": round(mid_arc_drop, 3),
                    "stop_reason": pack.get("stop_reason"),
                }
            )

        exceeded_focus_issues = []
        for issue_code in ("Q03", "Q04", "Q05", "Q09"):
            share = _issue_share(issue_mix, issue_code)
            limit = float(focus_issue_limits.get(issue_code, 1.0) or 1.0)
            if share > limit:
                exceeded_focus_issues.append(
                    {
                        "issue_code": issue_code,
                        "share": round(share, 3),
                        "threshold": round(limit, 3),
                    }
                )
        if exceeded_focus_issues:
            focus_issue_failures.append({"world_id": world_id, "issues": exceeded_focus_issues})

    return [
        {
            "key": "commercial_long_route_scope",
            "ok": bool(report.get("benchmark_scope_complete", True)) and bool(weakest_packs),
            "reason": "commercial_long_route_scope_met"
            if bool(report.get("benchmark_scope_complete", True)) and bool(weakest_packs)
            else "commercial_long_route_scope_incomplete",
            "actual": {
                "benchmark_mode": benchmark_mode,
                "chapter_budget": chapter_budget,
                "benchmark_scope_complete": bool(report.get("benchmark_scope_complete", True)),
                "weakest_pack_count": len(weakest_packs),
            },
            "threshold": {"benchmark_mode": "long_route", "chapter_budget_min": required_budget},
        },
        {
            "key": "commercial_long_route_weakest_evidence",
            "ok": not missing_evidence,
            "reason": "commercial_long_route_weakest_evidence_present"
            if not missing_evidence
            else "commercial_long_route_weakest_evidence_missing",
            "actual": missing_evidence,
            "threshold": ["long_route_quality", "mid_arc_drop", "completion_ratio", "stop_reason", "issue_mix"],
            "evaluated_world_ids": [str(pack.get("world_id") or "") for pack in weakest_packs],
        },
        {
            "key": "commercial_long_route_readability",
            "ok": not readability_failures,
            "reason": "commercial_long_route_readability_met"
            if not readability_failures
            else "commercial_long_route_readability_below_min",
            "actual": readability_failures,
            "threshold": {
                "long_route_quality_min": round(quality_min, 3),
                "completion_ratio_min": round(completion_min, 3),
                "mid_arc_drop_max": round(mid_arc_drop_max, 3),
            },
            "evaluated_world_ids": [str(pack.get("world_id") or "") for pack in weakest_packs],
        },
        {
            "key": "commercial_long_route_focus_issues",
            "ok": not focus_issue_failures,
            "reason": "commercial_long_route_focus_issues_met"
            if not focus_issue_failures
            else "commercial_long_route_focus_issue_share_exceeded",
            "actual": focus_issue_failures,
            "threshold": {key: round(float(value), 3) for key, value in focus_issue_limits.items()},
            "evaluated_world_ids": [str(pack.get("world_id") or "") for pack in weakest_packs],
        },
    ]


def evaluate_commercial_long_route_gate(
    report: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = dict(config or load_release_quality_gate_config())
    checks = _commercial_long_route_checks(report, thresholds)
    applicable = bool(checks)
    failed_checks = [item["reason"] for item in checks if not item.get("ok")]
    return {
        "config_version": str(thresholds.get("config_version") or ""),
        "applicable": applicable,
        "ok": not failed_checks if applicable else True,
        "checks": checks,
        "failed_checks": failed_checks,
        "thresholds": {
            "benchmark_mode": "long_route",
            "chapter_budget_min": int(thresholds.get("commercial_long_route_chapter_budget_min", 50) or 50),
            "weakest_long_route_quality_min": float(
                thresholds.get("commercial_long_route_weakest_long_route_quality_min", 0.5) or 0.5
            ),
            "weakest_completion_ratio_min": float(
                thresholds.get("commercial_long_route_weakest_completion_ratio_min", 0.8) or 0.8
            ),
            "weakest_mid_arc_drop_max": float(
                thresholds.get("commercial_long_route_weakest_mid_arc_drop_max", 0.35) or 0.35
            ),
        },
    }


def evaluate_release_quality_gate(
    report: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = dict(config or load_release_quality_gate_config())
    weakest_limit = max(1, int(thresholds.get("weakest_pack_limit", 3) or 3))
    weakest_packs = list(report.get("weakest_packs") or report.get("top_failing_packs") or [])[:weakest_limit]
    checks: List[Dict[str, Any]] = []

    cross_pack_pass_rate = float(report.get("cross_pack_pass_rate", 0.0) or 0.0)
    cross_pack_min = float(thresholds.get("cross_pack_pass_rate_min", 0.9) or 0.9)
    checks.append(
        {
            "key": "cross_pack_pass_rate",
            "ok": cross_pack_pass_rate >= cross_pack_min,
            "reason": "phase_a_cross_pack_pass_rate_met"
            if cross_pack_pass_rate >= cross_pack_min
            else "phase_a_cross_pack_pass_rate_below_min",
            "actual": round(cross_pack_pass_rate, 3),
            "threshold": round(cross_pack_min, 3),
        }
    )

    weakest_pack_pass_rate_min = float(thresholds.get("weakest_pack_pass_rate_min", 0.55) or 0.55)
    weakest_pack_pass_rate_evaluated = [
        pack for pack in weakest_packs if "pass_rate" in pack and pack.get("pass_rate") is not None
    ]
    weakest_pack_failures = [
        {
            "world_id": str(pack.get("world_id") or ""),
            "pass_rate": round(float(pack.get("pass_rate", 0.0) or 0.0), 3),
        }
        for pack in weakest_pack_pass_rate_evaluated
        if float(pack.get("pass_rate", 0.0) or 0.0) < weakest_pack_pass_rate_min
    ]
    checks.append(
        {
            "key": "weakest_pack_pass_rate",
            "ok": not weakest_pack_failures,
            "reason": "phase_a_weakest_pack_pass_rate_met"
            if not weakest_pack_failures
            else "phase_a_weakest_pack_pass_rate_below_min",
            "actual": weakest_pack_failures,
            "threshold": round(weakest_pack_pass_rate_min, 3),
            "evaluated_world_ids": [str(pack.get("world_id") or "") for pack in weakest_pack_pass_rate_evaluated],
            "skipped": not bool(weakest_pack_pass_rate_evaluated),
        }
    )

    for issue_code, share_limit in dict(thresholds.get("weakest_pack_issue_share_max", {})).items():
        exceeded = []
        evaluated_world_ids = []
        for pack in weakest_packs:
            world_id = str(pack.get("world_id") or "")
            issue_mix = list(pack.get("issue_mix") or [])
            if not world_id or not issue_mix:
                continue
            evaluated_world_ids.append(world_id)
            share = _issue_share(issue_mix, issue_code)
            if share > float(share_limit):
                exceeded.append({"world_id": world_id, "share": round(share, 3)})
        checks.append(
            {
                "key": f"{issue_code.lower()}_weakest_issue_share",
                "ok": not exceeded,
                "reason": f"phase_a_{issue_code.lower()}_weakest_issue_share_met"
                if not exceeded
                else f"phase_a_{issue_code.lower()}_weakest_issue_share_exceeded",
                "actual": exceeded,
                "threshold": round(float(share_limit), 3),
                "evaluated_world_ids": evaluated_world_ids,
                "skipped": not bool(evaluated_world_ids),
            }
        )

    checks.extend(_commercial_long_route_checks(report, thresholds))

    failed_checks = [item["reason"] for item in checks if not item.get("ok")]
    skipped_checks = [item["key"] for item in checks if item.get("skipped")]
    return {
        "config_version": str(thresholds.get("config_version") or ""),
        "thresholds": thresholds,
        "ok": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "skipped_checks": skipped_checks,
        "evaluated_weakest_world_ids": [str(pack.get("world_id") or "") for pack in weakest_packs],
    }
