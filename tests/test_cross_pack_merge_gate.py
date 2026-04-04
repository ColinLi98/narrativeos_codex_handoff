import json
from pathlib import Path

import pytest

from src.narrativeos.benchmark.merge_gate import (
    build_gate_summary,
    run_merge_gate,
    validate_benchmark_report,
    validate_pr_evidence,
)
from src.narrativeos.benchmark.runner import run_benchmark
from src.narrativeos.repository import SQLAlchemyRepository


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


def test_validate_benchmark_report_accepts_current_shape(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "merge_gate.db"))
    report = run_benchmark(repository=repository, golden_dir=tmp_path / "goldens", baseline={"worlds": [], "cross_pack_pass_rate": 0.0})
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
