import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.narrativeos.benchmark.merge_gate import (
    build_gate_summary,
    run_merge_gate,
    validate_benchmark_report,
    validate_pr_evidence,
)
from src.narrativeos.benchmark.release_quality_gate import evaluate_release_quality_gate


def _sample_pr_body() -> str:
    return """## PR summary
- Lane: Lane A
- Phase: Phase 0
- Task: Task 0.3
- Goal met: yes
- Out-of-scope changes introduced: no

## Evidence
- Tests run: pytest -q
- Benchmark / eval run: yes
- strongest pack delta: unchanged
- weakest pack delta: unchanged
- cross-pack pass-rate delta: +0.000
- issue category delta (Q03/Q04/Q05/Q09 if relevant): unchanged
- rollback point: revert merge gate files
- next suggested task: Long-route benchmark

## Product impact
- Does this move commercialization forward?: yes
- Does this improve kernel/product/ops instead of just current-pack polish?: yes
- Does this make weakest packs easier to diagnose or improve?: yes
"""


def test_validate_benchmark_report_accepts_current_shape():
    report = {
        "cross_pack_pass_rate": 0.93,
        "strongest_packs": [{"world_id": "xianxia_forgotten_vow"}],
        "weakest_packs": [
            {
                "world_id": "jade_court_romance",
                "pass_rate": 0.61,
                "issue_mix": [
                    {"issue_code": "Q03", "share": 0.2},
                    {"issue_code": "Q05", "share": 0.24},
                ],
            }
        ],
        "top_failing_packs": [
            {
                "world_id": "jade_court_romance",
                "pass_rate": 0.61,
                "issue_mix": [
                    {"issue_code": "Q03", "share": 0.2},
                    {"issue_code": "Q05", "share": 0.24},
                ],
            }
        ],
        "delta_summary": {
            "cross_pack_pass_rate_delta": 0.0,
            "regressions": [],
            "ranking_changes": {},
        },
    }
    assert validate_benchmark_report(report) == []


def test_validate_benchmark_report_rejects_regression():
    report = {
        "cross_pack_pass_rate": 0.8,
        "strongest_packs": [{"world_id": "a"}],
        "weakest_packs": [{"world_id": "b"}],
        "top_failing_packs": [{"world_id": "b"}],
        "delta_summary": {
            "cross_pack_pass_rate_delta": -0.1,
            "regressions": [{"world_id": "b", "metrics": ["prose_leak_rate"]}],
            "ranking_changes": {},
        },
    }
    errors = validate_benchmark_report(report)
    assert "cross_pack_pass_rate_regressed" in errors
    assert "metric_regression_detected" in errors


def test_release_quality_gate_uses_shared_phase_a_thresholds():
    gate = evaluate_release_quality_gate(
        {
            "cross_pack_pass_rate": 0.91,
            "weakest_packs": [
                {
                    "world_id": "jade_court_romance",
                    "pass_rate": 0.62,
                    "issue_mix": [
                        {"issue_code": "Q03", "share": 0.22},
                        {"issue_code": "Q05", "share": 0.28},
                    ],
                }
            ],
        }
    )
    assert gate["ok"] is True
    assert gate["config_version"] == "phase_a_quality_gate_v1"


def test_release_quality_gate_blocks_when_shared_thresholds_are_missed():
    gate = evaluate_release_quality_gate(
        {
            "cross_pack_pass_rate": 0.85,
            "weakest_packs": [
                {
                    "world_id": "jade_court_romance",
                    "pass_rate": 0.5,
                    "issue_mix": [
                        {"issue_code": "Q03", "share": 0.4},
                        {"issue_code": "Q09", "share": 0.25},
                    ],
                }
            ],
        }
    )
    assert gate["ok"] is False
    assert "phase_a_cross_pack_pass_rate_below_min" in gate["failed_checks"]
    assert "phase_a_weakest_pack_pass_rate_below_min" in gate["failed_checks"]
    assert "phase_a_q03_weakest_issue_share_exceeded" in gate["failed_checks"]
    assert "phase_a_q09_weakest_issue_share_exceeded" in gate["failed_checks"]


def test_release_quality_gate_blocks_commercial_long_route_weakest_pack_collapse():
    gate = evaluate_release_quality_gate(
        {
            "benchmark_mode": "long_route",
            "chapter_budget": 50,
            "benchmark_scope_complete": True,
            "cross_pack_pass_rate": 0.95,
            "weakest_packs": [
                {
                    "world_id": "urban_mystery_lotus_lane",
                    "pass_rate": 0.72,
                    "long_route_quality": 0.42,
                    "completion_ratio": 0.74,
                    "mid_arc_drop": 0.42,
                    "stop_reason": "quality_collapse",
                    "issue_mix": [
                        {"issue_code": "Q03", "share": 0.2},
                        {"issue_code": "Q04", "share": 0.18},
                        {"issue_code": "Q05", "share": 0.22},
                        {"issue_code": "Q09", "share": 0.18},
                    ],
                }
            ],
        }
    )
    assert gate["ok"] is False
    assert "commercial_long_route_readability_below_min" in gate["failed_checks"]


def test_release_quality_gate_skips_commercial_long_route_for_short_benchmark():
    gate = evaluate_release_quality_gate(
        {
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "cross_pack_pass_rate": 0.95,
            "weakest_packs": [
                {
                    "world_id": "synthetic_min_pack",
                    "pass_rate": 0.72,
                    "issue_mix": [{"issue_code": "Q03", "share": 0.2}],
                }
            ],
        }
    )
    assert gate["ok"] is True
    assert not any(str(item).startswith("commercial_long_route") for item in gate["failed_checks"])


def test_release_quality_gate_accepts_empty_commercial_issue_mix_as_clean_evidence():
    gate = evaluate_release_quality_gate(
        {
            "benchmark_mode": "long_route",
            "chapter_budget": 50,
            "benchmark_scope_complete": True,
            "cross_pack_pass_rate": 0.95,
            "weakest_packs": [
                {
                    "world_id": "jade_court_exam",
                    "pass_rate": 1.0,
                    "long_route_quality": 0.9,
                    "completion_ratio": 1.0,
                    "mid_arc_drop": 0.0,
                    "stop_reason": "chapter_budget_reached",
                    "issue_mix": [],
                }
            ],
        }
    )
    assert gate["ok"] is True
    assert "commercial_long_route_weakest_evidence_missing" not in gate["failed_checks"]


def test_validate_benchmark_report_rejects_blocked_longform_l1_signoff():
    report = {
        "benchmark_mode": "longform_100",
        "cross_pack_pass_rate": 1.0,
        "strongest_packs": [{"world_id": "a"}],
        "weakest_packs": [{"world_id": "b"}],
        "top_failing_packs": [{"world_id": "b"}],
        "delta_summary": {
            "cross_pack_pass_rate_delta": 0.0,
            "regressions": [],
            "ranking_changes": {},
        },
        "longform_l1_signoff": {
            "status": "blocked",
            "blocking_worlds": ["b"],
        },
    }
    errors = validate_benchmark_report(report)
    assert "longform_l1_signoff_blocked" in errors


def test_validate_benchmark_report_rejects_stale_longform_l1_signoff():
    report = {
        "benchmark_mode": "longform_100",
        "cross_pack_pass_rate": 1.0,
        "strongest_packs": [{"world_id": "a"}],
        "weakest_packs": [{"world_id": "b"}],
        "top_failing_packs": [{"world_id": "b"}],
        "delta_summary": {
            "cross_pack_pass_rate_delta": 0.0,
            "regressions": [],
            "ranking_changes": {},
        },
        "longform_l1_signoff": {
            "status": "watch",
            "reason": "benchmark_signoff_stale",
            "generated_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
            "blocking_worlds": [],
        },
    }
    errors = validate_benchmark_report(report)
    assert "longform_l1_signoff_blocked" in errors


def test_validate_pr_evidence_requires_delta_fields():
    errors = validate_pr_evidence("## PR summary\n- Lane: Lane A\n")
    assert "missing_pr_field:Goal met" in errors
    assert "missing_pr_field:strongest pack delta" in errors
    assert "missing_pr_field:rollback point" in errors


def test_validate_pr_evidence_rejects_current_pack_polish_only():
    errors = validate_pr_evidence(
        _sample_pr_body().replace(
            "- Does this improve kernel/product/ops instead of just current-pack polish?: yes",
            "- Does this improve kernel/product/ops instead of just current-pack polish?: no",
        )
    )
    assert "current_pack_polish_only" in errors


def test_run_merge_gate_checks_pr_body_and_writes_summary(tmp_path):
    benchmark_path = tmp_path / "benchmark.json"
    summary_path = tmp_path / "summary.md"
    benchmark_path.write_text(
        json.dumps(
            {
                "cross_pack_pass_rate": 0.9,
                "strongest_packs": [{"world_id": "xianxia_forgotten_vow"}],
                "weakest_packs": [{"world_id": "jade_court_romance"}],
                "top_failing_packs": [{"world_id": "jade_court_romance"}],
                "delta_summary": {
                    "cross_pack_pass_rate_delta": 0.0,
                    "regressions": [],
                    "ranking_changes": {
                        "current_strongest": ["xianxia_forgotten_vow"],
                        "current_weakest": ["jade_court_romance"],
                    },
                },
                "longform_l1_signoff": {
                    "status": "watch",
                    "blocking_worlds": [],
                },
            }
        ),
        encoding="utf-8",
    )
    pr_body_path = tmp_path / "pr-body.md"
    pr_body_path.write_text(_sample_pr_body(), encoding="utf-8")
    result = run_merge_gate(
        benchmark_file=benchmark_path,
        pr_body_file=pr_body_path,
        require_pr_evidence=True,
        summary_out=summary_path,
    )
    assert result["benchmark_errors"] == []
    assert result["pr_errors"] == []
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "Cross-Pack Merge Gate" in summary_text
    assert "strongest packs: xianxia_forgotten_vow" in summary_text
    assert "longform_l1_signoff: watch" in summary_text
    assert "phase_a_quality_gate" in summary_text


def test_run_merge_gate_fails_when_pr_body_missing(tmp_path):
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "cross_pack_pass_rate": 0.9,
                "strongest_packs": [{"world_id": "xianxia_forgotten_vow"}],
                "weakest_packs": [{"world_id": "jade_court_romance"}],
                "top_failing_packs": [{"world_id": "jade_court_romance"}],
                "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": [], "ranking_changes": {}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        run_merge_gate(
            benchmark_file=benchmark_path,
            pr_body_file=None,
            require_pr_evidence=True,
            summary_out=None,
        )
    assert "missing_pr_body_file" in str(exc.value)


def test_build_gate_summary_surfaces_errors():
    summary = build_gate_summary(
        {
            "cross_pack_pass_rate": 0.9,
            "strongest_packs": [{"world_id": "x"}],
            "weakest_packs": [{"world_id": "y"}],
            "delta_summary": {"cross_pack_pass_rate_delta": 0.0},
        },
        benchmark_errors=["metric_regression_detected"],
        pr_errors=["missing_pr_field:strongest pack delta"],
    )
    assert "metric_regression_detected" in summary
    assert "missing_pr_field:strongest pack delta" in summary
