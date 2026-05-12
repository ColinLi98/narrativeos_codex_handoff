import json
from unittest.mock import patch
from typing import Optional

from src.narrativeos.content_quality_strategy_execution import (
    build_strategy_bundle_batch_validation_summary,
    build_strategy_bundle_batch_validation_trend,
    list_strategy_bundle_batch_validation_history,
    record_strategy_bundle_batch_validation_run,
)
from src.narrativeos.benchmark.runner import (
    BENCHMARK_PACKS,
    _DiagnosticIssueScanCache,
    _surface_issue_codes_for_payload,
    main,
    run_benchmark,
)
from src.narrativeos.benchmark.reporting import render_benchmark_markdown
from src.narrativeos.eval.taxonomy import ISSUE_TAXONOMY
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_registry_benchmark_worldpacks_excludes_template_assets():
    registry = FileSystemWorldRegistry()
    world_ids = {item["world_id"] for item in registry.list_benchmark_worldpacks()}
    assert "world_template_minimal" not in world_ids
    assert {
        "jade_court_exam",
        "jade_court_romance",
        "urban_mystery_lotus_lane",
        "xianxia_forgotten_vow",
        "synthetic_min_pack",
        "tide_archive_memory_debt",
    } <= world_ids


def test_cross_pack_benchmark_outputs_kernel_metrics(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark.db"))
    baseline = {
        "worlds": [{"world_id": world_id, "pass_rate": 0.0, "prose_leak_rate": 0.0} for world_id in BENCHMARK_PACKS],
        "cross_pack_pass_rate": 0.0,
    }
    report = run_benchmark(repository=repository, golden_dir=tmp_path / "goldens", baseline=baseline)
    world_ids = {item["world_id"] for item in report["worlds"]}
    assert set(BENCHMARK_PACKS) <= world_ids
    sample = report["worlds"][0]
    for key in [
        "character_fidelity",
        "causal_continuity",
        "choice_distinctness",
        "prose_leak_rate",
        "route_longevity",
        "dialogue_ratio",
        "scene_detail_density",
        "voice_separation_score",
        "emotion_action_specificity",
        "cross_pack_pass_rate",
    ]:
        assert key in sample
    assert "top_issue_categories" in sample
    assert "dimension_scores" in sample
    assert "issue_summary" in sample
    assert "issue_mix" in sample
    assert "long_route_quality" in sample
    assert "mid_arc_drop" in sample
    assert "dialogue_distinctness" in sample
    assert "completion_ratio" in sample
    assert "stop_reason" in sample
    assert "diagnostic_score" in sample
    assert "diagnostic_rank" in sample
    assert sample["issue_summary"]["dominant_issue"] is not None
    assert "weakest_dimensions" in sample["issue_summary"]
    assert "recommended_target" in sample["issue_summary"]
    assert "top_failing_packs" in report
    assert "strongest_packs" in report
    assert "weakest_packs" in report
    assert "weakest_pack_diagnostics" in report
    assert "weakest_pack_polish_program" in report
    assert "content_quality_contract_gate" in report
    assert "commercial_long_route_gate" in report
    assert report["commercial_long_route_gate"]["applicable"] is False
    assert "strategy_validation_summary" in report
    assert "content_quality_contract_summary" in report
    assert report["top_failing_packs"] == report["weakest_packs"]
    assert "delta_summary" in report
    assert "cross_pack_pass_rate_delta" in report["delta_summary"]
    assert "ranking_changes" in report["delta_summary"]
    assert "top_issue_categories" in report["top_failing_packs"][0]
    assert "weakest_dimensions" in report["top_failing_packs"][0]
    assert "issue_mix" in report["top_failing_packs"][0]
    assert "issue_mix" in report["strongest_packs"][0]
    assert report["weakest_pack_diagnostics"][0]["world_id"] == report["weakest_packs"][0]["world_id"]
    assert "worst_chapters" in report["weakest_pack_diagnostics"][0]
    assert "attribution_map" in report["weakest_pack_diagnostics"][0]
    assert "next_fix_candidates" in report["weakest_pack_diagnostics"][0]
    assert "stop_condition" in report["weakest_pack_diagnostics"][0]
    assert "polish_bundle" in report["weakest_pack_diagnostics"][0]
    assert "recommended_strategy_bundles" in report["weakest_pack_diagnostics"][0]
    if report["strategy_validation_summary"]["available"]:
        assert report["strategy_validation_summary"]["bundle_count"] >= 1
        assert report["weakest_pack_diagnostics"][0]["recommended_strategy_bundles"][0]["execution_protocol_enabled"] is True
    else:
        assert report["content_quality_contract_gate"]["ok"] is True
        assert report["strategy_validation_summary"]["bundle_count"] == 0
        assert report["weakest_pack_diagnostics"][0]["recommended_strategy_bundles"] == []
    assert "content_quality_contract_window_metrics" in sample
    assert "content_quality_contract_coverage" in sample


def test_cross_pack_benchmark_outputs_runtime_profile(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_runtime.db"))
    simulated = _simulation_report(
        pass_rate=1.0,
        rewrite_rate=0.0,
        block_rate=0.0,
        overall_scores=[0.91, 0.9],
        issue_codes=[],
        detail_density=0.08,
    )
    simulated["chapter_trace"] = [
        {
            "runtime_latency_ms": 12.0,
            "lint_latency_ms": 1.5,
            "evaluation_latency_ms": 2.0,
            "render_timing_ms": {"write_draft": 7.0, "post_repair_lint": 1.0, "total_render_scene": 8.5},
            "quality_pass_timing_ms": {"total_ms": 5.0},
            "quality_pass_actions": ["q03_repetition_guard", "q05_detail_inline"],
        },
        {
            "runtime_latency_ms": 10.0,
            "lint_latency_ms": 1.0,
            "evaluation_latency_ms": 1.5,
            "render_timing_ms": {"write_draft": 6.0, "post_repair_lint": 0.8, "total_render_scene": 7.2},
            "quality_pass_timing_ms": {"total_ms": 4.0},
            "quality_pass_actions": ["q04_exposition_guard"],
        },
    ]
    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=["jade_court_exam"],
        baseline=None,
        simulation_runner=lambda _world_id, _world_version_id: simulated,
    )
    world_profile = report["worlds"][0]["runtime_profile"]
    assert world_profile["stages_ms"]["generation_runtime"] == 22.0
    assert world_profile["stages_ms"]["quality_pass"] == 9.0
    assert world_profile["stages_ms"]["lint"] == 2.5
    assert world_profile["quality_pass_stage_action_counts"]["q03_repetition"] == 1
    assert world_profile["quality_pass_stage_action_counts"]["q05_detail"] == 1
    assert report["benchmark_runtime_profile"]["stage_totals_ms"]["quality_pass"] == 9.0
    assert report["benchmark_runtime_profile"]["safe_caches"]["repetition_signal_bundle"]["enabled"] is True
    markdown = render_benchmark_markdown(report)
    assert "Benchmark Runtime Profile" in markdown
    assert "quality-pass stage actions" in markdown


def test_cross_pack_benchmark_writes_progress_and_checkpoint(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_progress.db"))
    progress_path = tmp_path / "benchmark_progress.jsonl"
    checkpoint_path = tmp_path / "benchmark_progress.checkpoint.json"

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=["jade_court_exam"],
        baseline=None,
        simulation_runner=lambda _world_id, _world_version_id: _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.9, 0.91],
            issue_codes=[],
            detail_density=0.08,
        ),
        progress_out=progress_path,
        checkpoint_out=checkpoint_path,
    )

    events = [
        json.loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [item["event"] for item in events if item["event"] in {"benchmark_start", "world_start", "world_complete", "benchmark_complete"}] == [
        "benchmark_start",
        "world_start",
        "world_complete",
        "benchmark_complete",
    ]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["schema_version"] == "benchmark_checkpoint/v1"
    assert checkpoint["stage"] == "complete"
    assert checkpoint["completed_world_count"] == 1
    assert checkpoint["completed_worlds"][0]["world_id"] == "jade_court_exam"
    assert checkpoint["diagnostic_issue_scan_cache"]["payload_policy"] == "bounded_metrics_only"
    assert report["benchmark_runtime_profile"]["safe_caches"]["diagnostic_issue_scan"]["enabled"] is True


def test_diagnostic_issue_scan_cache_bounds_payload_and_reuses_result():
    cache = _DiagnosticIssueScanCache()
    payload = {
        "chapter_id": "chapter_20",
        "body": "很长的可见正文" * 10000,
        "summary": "不应该传入诊断扫描的长摘要" * 1000,
        "issues": [],
        "hard_validator_results": {
            "lint_metrics": {
                "repetition_score": 0.33,
                "exposition_ratio": 0.2,
                "concrete_detail_density": 0.09,
                "dialogue_plus_action_ratio": 0.5,
                "repetition_signal_bundle": {
                    "event_coverage_gap_score": 0.0,
                    "beat_coverage_gap_score": 0.0,
                },
            }
        },
        "scores": {"hook_quality": 0.9, "overall_score": 0.91},
    }
    scanned_payloads = []

    def fake_scan(scan_payload, *, target_chapters):
        scanned_payloads.append(dict(scan_payload))
        assert "body" not in scan_payload
        assert "summary" not in scan_payload
        assert target_chapters == 500
        return ["Q03"]

    with patch("src.narrativeos.benchmark.runner.diagnostic_issue_codes_for_chapter_payload", side_effect=fake_scan):
        assert _surface_issue_codes_for_payload(payload, target_chapters=500, diagnostic_scan_cache=cache) == ["Q03"]
        assert _surface_issue_codes_for_payload(payload, target_chapters=500, diagnostic_scan_cache=cache) == ["Q03"]

    assert len(scanned_payloads) == 1
    assert cache.summary()["hits"] == 1
    assert cache.summary()["misses"] == 1


def test_fast_acceptance_profile_selects_changed_and_baseline_weakest_packs(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_fast_gate.db"))
    seen_worlds: list[str] = []

    def simulation_runner(world_id, _world_version_id):
        seen_worlds.append(world_id)
        return _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.9] * 3,
            issue_codes=[],
            detail_density=0.08,
        )

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="all",
        baseline={"weakest_packs": [{"world_id": "jade_court_exam"}, {"world_id": "synthetic_min_pack"}]},
        simulation_runner=simulation_runner,
        acceptance_profile="fast",
        changed_worldpacks=["urban_mystery_lotus_lane"],
        fast_gate_weakest_limit=1,
    )
    assert set(seen_worlds) == {"jade_court_exam", "urban_mystery_lotus_lane"}
    assert report["acceptance_profile"] == "fast"
    assert report["benchmark_scope_complete"] is False
    assert report["fast_gate"]["enabled"] is True
    assert report["fast_gate"]["nightly_full_gate_required"] is True
    assert set(report["benchmark_world_ids"]) == set(seen_worlds)


def test_commercial_long_route_gate_is_reported_in_markdown():
    markdown = render_benchmark_markdown(
        {
            "benchmark_mode": "long_route",
            "chapter_budget": 50,
            "cross_pack_pass_rate": 0.95,
            "worlds": [{"world_id": "a"}],
            "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": []},
            "phase_a_quality_gate": {
                "ok": True,
                "config_version": "phase_a_quality_gate_v1",
                "failed_checks": [],
                "evaluated_weakest_world_ids": ["a"],
            },
            "commercial_long_route_gate": {
                "applicable": True,
                "ok": True,
                "failed_checks": [],
            },
            "weakest_packs": [
                {
                    "world_id": "a",
                    "pass_rate": 0.9,
                    "long_route_quality": 0.82,
                    "mid_arc_drop": 0.03,
                    "completion_ratio": 1.0,
                    "stop_reason": "chapter_budget_reached",
                    "issue_mix": [
                        {"issue_code": "Q03", "count": 1, "share": 0.02},
                        {"issue_code": "Q09", "count": 0, "share": 0.0},
                    ],
                }
            ],
            "strongest_packs": [],
        }
    )
    assert "Commercial Long-Route 50 Gate" in markdown
    assert "commercial_long_route_50.db" in markdown
    assert "focus issues: Q03 x1" in markdown


def test_strategy_bundle_batch_validation_summary_decides_continue_adapt_retire():
    continue_summary = build_strategy_bundle_batch_validation_summary(
        strategy_bundle_id="q03_q04_scene_dialogue_cadence_task_coupling",
        strategy_bundle_label="Scene + Dialogue + Cadence + Task Coupling",
        batch_execution_mode="ephemeral_copy",
        benchmark_mode="standard",
        chapter_budget=6,
        weakest_source_world_ids=["a", "b", "c"],
        compatible_world_ids=["a", "b", "c"],
        skipped_worlds=[],
        validated_worlds=[
            {
                "world_id": "a",
                "step_receipt_summary": {
                    "step_status_counts": {"applied": 2},
                    "asset_type_counts": {"scene_blueprint": 1},
                    "operation_counts": {"replace": 2},
                    "applied_step_count": 2,
                    "applied_edit_count": 4,
                },
                "step_level_apply_receipt": [{"asset_type": "scene_blueprint", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "improved",
                    "improved_metrics": ["avg_repetition_score"],
                    "regressed_metrics": [],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "stop"},
                "ready_for_validation": True,
            },
            {
                "world_id": "b",
                "step_receipt_summary": {
                    "step_status_counts": {"applied": 1},
                    "asset_type_counts": {"voice_profiles": 1},
                    "operation_counts": {"expand": 1},
                    "applied_step_count": 1,
                    "applied_edit_count": 2,
                },
                "step_level_apply_receipt": [{"asset_type": "voice_profiles", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "improved",
                    "improved_metrics": ["dialogue_ratio"],
                    "regressed_metrics": [],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "stop"},
                "ready_for_validation": False,
            },
            {
                "world_id": "c",
                "step_receipt_summary": {
                    "step_status_counts": {"applied": 1},
                    "asset_type_counts": {"response_cadence_profiles": 1},
                    "operation_counts": {"expand": 1},
                    "applied_step_count": 1,
                    "applied_edit_count": 1,
                },
                "step_level_apply_receipt": [{"asset_type": "response_cadence_profiles", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "improved",
                    "improved_metrics": ["mid_window_exposition_breach_rate"],
                    "regressed_metrics": [],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "stop"},
                "ready_for_validation": False,
            },
        ],
    )
    assert continue_summary["available"] is True
    assert continue_summary["decision"] == "continue"
    assert continue_summary["effectiveness_rate"] == 1.0

    adapt_summary = build_strategy_bundle_batch_validation_summary(
        strategy_bundle_id="q04_scene_dialogue_cadence",
        strategy_bundle_label="Scene + Dialogue + Cadence",
        batch_execution_mode="ephemeral_copy",
        benchmark_mode="standard",
        chapter_budget=6,
        weakest_source_world_ids=["a", "b"],
        compatible_world_ids=["a", "b"],
        skipped_worlds=[],
        validated_worlds=[
            {
                "world_id": "a",
                "step_receipt_summary": {
                    "step_status_counts": {"applied": 1},
                    "asset_type_counts": {"scene_realization_contracts": 1},
                    "operation_counts": {"replace": 1},
                    "applied_step_count": 1,
                    "applied_edit_count": 1,
                },
                "step_level_apply_receipt": [{"asset_type": "scene_realization_contracts", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "improved",
                    "improved_metrics": ["dialogue_ratio"],
                    "regressed_metrics": [],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "stop"},
                "ready_for_validation": False,
            },
            {
                "world_id": "b",
                "step_receipt_summary": {
                    "step_status_counts": {"skipped": 1},
                    "asset_type_counts": {"emotion_action_policies": 1},
                    "operation_counts": {"replace": 1},
                    "applied_step_count": 0,
                    "applied_edit_count": 0,
                },
                "step_level_apply_receipt": [{"asset_type": "emotion_action_policies", "status": "skipped"}],
                "result_attribution": {
                    "overall_status": "flat",
                    "improved_metrics": [],
                    "regressed_metrics": [],
                    "flat_metrics": ["avg_exposition_ratio"],
                },
                "stop_decision": {"decision": "continue"},
                "ready_for_validation": False,
            },
        ],
    )
    assert adapt_summary["decision"] == "adapt"
    assert any(item["kind"] == "asset_step" for item in adapt_summary["adaptation_targets"])

    retire_summary = build_strategy_bundle_batch_validation_summary(
        strategy_bundle_id="q09_continuation_runway",
        strategy_bundle_label="Continuation Runway",
        batch_execution_mode="ephemeral_copy",
        benchmark_mode="longform_100",
        chapter_budget=100,
        weakest_source_world_ids=["a", "b"],
        compatible_world_ids=["a", "b"],
        skipped_worlds=[],
        validated_worlds=[
            {
                "world_id": "a",
                "step_receipt_summary": {"step_status_counts": {"applied": 1}, "asset_type_counts": {}, "operation_counts": {}, "applied_step_count": 1, "applied_edit_count": 1},
                "step_level_apply_receipt": [{"asset_type": "chapter_task", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "regressed",
                    "improved_metrics": [],
                    "regressed_metrics": ["late_window_q09_breach_rate"],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "escalate"},
                "ready_for_validation": False,
            },
            {
                "world_id": "b",
                "step_receipt_summary": {"step_status_counts": {"applied": 1}, "asset_type_counts": {}, "operation_counts": {}, "applied_step_count": 1, "applied_edit_count": 1},
                "step_level_apply_receipt": [{"asset_type": "arc_plan", "status": "applied"}],
                "result_attribution": {
                    "overall_status": "regressed",
                    "improved_metrics": [],
                    "regressed_metrics": ["q09_incidence_rate"],
                    "flat_metrics": [],
                },
                "stop_decision": {"decision": "escalate"},
                "ready_for_validation": False,
            },
        ],
    )
    assert retire_summary["decision"] == "retire"

    empty_summary = build_strategy_bundle_batch_validation_summary(
        strategy_bundle_id="q03_scene_dialogue_cadence",
        strategy_bundle_label="Scene + Dialogue + Cadence",
        batch_execution_mode="ephemeral_copy",
        benchmark_mode="standard",
        chapter_budget=6,
        weakest_source_world_ids=["a"],
        compatible_world_ids=[],
        skipped_worlds=[{"world_id": "a", "reason": "bundle_not_recommended_for_world"}],
        validated_worlds=[],
    )
    assert empty_summary["available"] is False
    assert empty_summary["decision"] == ""
    assert empty_summary["decision_reason"] == "no_compatible_weakest_packs"


def test_strategy_bundle_batch_validation_history_persists_and_builds_trend(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "strategy_bundle_history.db"))
    record_strategy_bundle_batch_validation_run(
        repository=repository,
        batch_validation={
            "generated_at": "2026-04-13T10:00:00+00:00",
            "strategy_bundle_id": "q03_scene_dialogue_cadence",
            "strategy_bundle_label": "Scene + Dialogue + Cadence",
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "weakest_source_world_ids": ["jade_court_exam"],
            "compatible_world_ids": ["jade_court_exam"],
            "validated_world_count": 1,
            "effectiveness_rate": 0.25,
            "decision": "adapt",
            "decision_reason": "bundle_mixed_signal_requires_adjustment",
            "aggregated_result_attribution": {"overall_status_counts": {"flat": 1}, "stop_decision_counts": {"continue": 1}},
            "adaptation_targets": [{"kind": "metric", "name": "avg_exposition_ratio", "count": 1}],
        },
    )
    record_strategy_bundle_batch_validation_run(
        repository=repository,
        batch_validation={
            "generated_at": "2026-04-13T11:00:00+00:00",
            "strategy_bundle_id": "q03_scene_dialogue_cadence",
            "strategy_bundle_label": "Scene + Dialogue + Cadence",
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "weakest_source_world_ids": ["jade_court_exam"],
            "compatible_world_ids": ["jade_court_exam"],
            "validated_world_count": 1,
            "effectiveness_rate": 0.45,
            "decision": "continue",
            "decision_reason": "bundle_effective_across_weakest_packs",
            "aggregated_result_attribution": {"overall_status_counts": {"improved": 1}, "stop_decision_counts": {"stop": 1}},
            "adaptation_targets": [],
        },
    )
    history = list_strategy_bundle_batch_validation_history(
        repository=repository,
        strategy_bundle_id="q03_scene_dialogue_cadence",
        limit=5,
    )
    trend = build_strategy_bundle_batch_validation_trend(history)
    assert history["available"] is True
    assert history["entry_count"] == 2
    assert history["entries"][0]["decision"] == "continue"
    assert trend["trend_status"] == "improving"
    assert trend["delta_effectiveness_rate"] == 0.2
    assert trend["retire_recommended"] is False


def test_strategy_bundle_batch_validation_trend_flags_retire_watch():
    trend = build_strategy_bundle_batch_validation_trend(
        {
            "available": True,
            "strategy_bundle_id": "q09_continuation_runway",
            "entry_count": 2,
            "entries": [
                {
                    "generated_at": "2026-04-13T11:00:00+00:00",
                    "strategy_bundle_id": "q09_continuation_runway",
                    "decision": "retire",
                    "effectiveness_rate": 0.1,
                },
                {
                    "generated_at": "2026-04-13T10:00:00+00:00",
                    "strategy_bundle_id": "q09_continuation_runway",
                    "decision": "retire",
                    "effectiveness_rate": 0.12,
                },
            ],
        }
    )
    assert trend["trend_status"] == "retire_watch"
    assert trend["retire_recommended"] is True


def test_run_benchmark_exposes_strategy_bundle_batch_validation_when_enabled(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_batch_validation.db"))
    with patch(
        "src.narrativeos.benchmark.runner._validate_strategy_bundle_batch",
        return_value={
            "available": True,
            "strategy_bundle_id": "q03_scene_dialogue_cadence",
            "strategy_bundle_label": "Scene + Dialogue + Cadence",
            "batch_execution_mode": "ephemeral_copy",
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "weakest_source_world_ids": ["jade_court_exam"],
            "compatible_world_ids": ["jade_court_exam"],
            "skipped_worlds": [],
            "validated_world_count": 1,
            "validated_worlds": [],
            "aggregated_step_receipts": {},
            "aggregated_result_attribution": {},
            "effectiveness_rate": 1.0,
            "decision": "continue",
            "decision_reason": "bundle_effective_across_weakest_packs",
            "adaptation_targets": [],
        },
    ) as validator:
        report = run_benchmark(
            repository=repository,
            golden_dir=tmp_path / "goldens",
            worldpack=["jade_court_exam", "synthetic_min_pack"],
            baseline=None,
            simulation_runner=lambda _world_id, _world_version_id: _simulation_report(
                pass_rate=0.8,
                rewrite_rate=0.2,
                block_rate=0.0,
                overall_scores=[0.82] * 6,
                issue_codes=["Q03"],
                detail_density=0.012,
            ),
            validate_strategy_bundle=True,
            strategy_bundle_id="q03_scene_dialogue_cadence",
            weakest_limit=2,
        )
    assert validator.called is True
    assert report["strategy_bundle_batch_validation"]["available"] is True
    assert report["strategy_bundle_batch_validation"]["strategy_bundle_id"] == "q03_scene_dialogue_cadence"
    markdown = render_benchmark_markdown(report)
    assert "Strategy Bundle Batch Validation" in markdown
    assert "bundle_effective_across_weakest_packs" in markdown


def test_run_benchmark_persists_strategy_bundle_batch_validation_history_when_enabled(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_batch_history_persist.db"))
    with patch(
        "src.narrativeos.benchmark.runner._validate_strategy_bundle_batch",
        return_value={
            "available": True,
            "generated_at": "2026-04-13T12:00:00+00:00",
            "strategy_bundle_id": "q03_scene_dialogue_cadence",
            "strategy_bundle_label": "Scene + Dialogue + Cadence",
            "batch_execution_mode": "ephemeral_copy",
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "weakest_source_world_ids": ["jade_court_exam"],
            "compatible_world_ids": ["jade_court_exam"],
            "skipped_worlds": [],
            "validated_world_count": 1,
            "validated_worlds": [],
            "aggregated_step_receipts": {},
            "aggregated_result_attribution": {"overall_status_counts": {"improved": 1}, "stop_decision_counts": {"stop": 1}},
            "effectiveness_rate": 0.8,
            "decision": "continue",
            "decision_reason": "bundle_effective_across_weakest_packs",
            "adaptation_targets": [],
        },
    ):
        report = run_benchmark(
            repository=repository,
            golden_dir=tmp_path / "goldens",
            worldpack=["jade_court_exam", "synthetic_min_pack"],
            baseline=None,
            simulation_runner=lambda _world_id, _world_version_id: _simulation_report(
                pass_rate=0.8,
                rewrite_rate=0.2,
                block_rate=0.0,
                overall_scores=[0.82] * 6,
                issue_codes=["Q03"],
                detail_density=0.012,
            ),
            validate_strategy_bundle=True,
            strategy_bundle_id="q03_scene_dialogue_cadence",
            weakest_limit=2,
        )
    saved = repository.list_review_records(
        asset_type="strategy_bundle_batch_validation",
        asset_id="q03_scene_dialogue_cadence",
    )
    assert len(saved) == 1
    assert saved[0]["status"] == "continue"
    assert report["strategy_bundle_batch_validation_history"]["available"] is True
    assert report["strategy_bundle_batch_validation_trend"]["trend_status"] == "insufficient_history"


def test_run_benchmark_can_read_strategy_bundle_history_without_new_rerun(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_batch_history_read.db"))
    record_strategy_bundle_batch_validation_run(
        repository=repository,
        batch_validation={
            "generated_at": "2026-04-13T09:00:00+00:00",
            "strategy_bundle_id": "q03_scene_dialogue_cadence",
            "strategy_bundle_label": "Scene + Dialogue + Cadence",
            "benchmark_mode": "standard",
            "chapter_budget": 6,
            "weakest_source_world_ids": ["jade_court_exam"],
            "compatible_world_ids": ["jade_court_exam"],
            "validated_world_count": 1,
            "effectiveness_rate": 0.55,
            "decision": "adapt",
            "decision_reason": "bundle_mixed_signal_requires_adjustment",
            "aggregated_result_attribution": {"overall_status_counts": {"flat": 1}, "stop_decision_counts": {"continue": 1}},
            "adaptation_targets": [{"kind": "metric", "name": "avg_exposition_ratio", "count": 1}],
        },
    )
    with patch("src.narrativeos.benchmark.runner._validate_strategy_bundle_batch") as validator:
        report = run_benchmark(
            repository=repository,
            golden_dir=tmp_path / "goldens",
            worldpack=["jade_court_exam", "synthetic_min_pack"],
            baseline=None,
            simulation_runner=lambda _world_id, _world_version_id: _simulation_report(
                pass_rate=0.8,
                rewrite_rate=0.2,
                block_rate=0.0,
                overall_scores=[0.82] * 6,
                issue_codes=["Q03"],
                detail_density=0.012,
            ),
            validate_strategy_bundle=False,
            strategy_bundle_id="q03_scene_dialogue_cadence",
            weakest_limit=2,
        )
    assert validator.called is False
    assert report["strategy_bundle_batch_validation"]["decision_reason"] == "history_only_query"
    assert report["strategy_bundle_batch_validation_history"]["entry_count"] == 1
    assert report["strategy_bundle_batch_validation_trend"]["trend_status"] == "insufficient_history"


def test_render_benchmark_markdown_shows_batch_validation_placeholder_when_unavailable():
    markdown = render_benchmark_markdown(
        {
            "cross_pack_pass_rate": 0.0,
            "worlds": [],
            "strongest_packs": [],
            "weakest_packs": [],
            "weakest_pack_diagnostics": [],
            "weakest_pack_polish_program": {},
            "delta_summary": {},
            "strategy_bundle_batch_validation": {
                "available": False,
                "strategy_bundle_id": "q03_scene_dialogue_cadence",
                "strategy_bundle_label": "Scene + Dialogue + Cadence",
                "batch_execution_mode": "ephemeral_copy",
                "weakest_source_world_ids": ["jade_court_exam"],
                "compatible_world_ids": [],
                "skipped_worlds": [{"world_id": "jade_court_exam", "reason": "bundle_not_recommended_for_world"}],
                "validated_world_count": 0,
                "aggregated_result_attribution": {},
                "effectiveness_rate": 0.0,
                "decision": "",
                "decision_reason": "no_compatible_weakest_packs",
                "adaptation_targets": [],
            },
        }
    )
    assert "Strategy Bundle Batch Validation" in markdown
    assert "status: not_run" in markdown
    assert "no_compatible_weakest_packs" in markdown


def test_cross_pack_benchmark_lifts_weakest_packs_above_zero(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_quality.db"))
    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        baseline={
            "worlds": [],
            "cross_pack_pass_rate": 0.3,
        },
    )
    weakest = {
        item["world_id"]: item["pass_rate"]
        for item in report["worlds"]
        if item["world_id"] in {"urban_mystery_lotus_lane", "xianxia_forgotten_vow", "synthetic_min_pack"}
    }
    assert sum(1 for value in weakest.values() if value > 0.0) >= 2
    assert report["cross_pack_pass_rate"] > 0.3
    assert report["delta_summary"]["regressions"] == []


def _chapter_report(
    *,
    chapter_id: str,
    overall_score: float,
    issue_codes: list[str],
    detail_density: float,
    decision: str = "pass",
    dialogue_ratio: float = 0.38,
    repetition_score: float = 0.0,
    exposition_ratio: float = 0.3,
    hook_quality: Optional[float] = None,
) -> dict[str, object]:
    issues = [
        {
            "issue_code": code,
            "severity": "medium",
            "summary": ISSUE_TAXONOMY.get(code, {}).get("label", code),
            "owning_module": ISSUE_TAXONOMY.get(code, {}).get("owning_module", ""),
            "evidence": [],
        }
        for code in issue_codes
    ]
    return {
        "chapter_id": chapter_id,
        "world_version_id": "test@1.0.0",
        "session_id": "simulation:test",
        "decision": {"decision": decision, "reason": "benchmark"},
        "issues": issues,
        "scores": {
            "readability": overall_score,
            "scene_density": overall_score,
            "character_fidelity": overall_score,
            "causal_continuity": overall_score,
            "pacing": overall_score,
            "choice_distinctness": overall_score,
            "hook_quality": overall_score if hook_quality is None else hook_quality,
            "monetize_ready": overall_score,
            "overall_score": overall_score,
        },
        "hard_validator_results": {
            "lint_metrics": {
                "engineering_leak_rate": 0.0,
                "dialogue_plus_action_ratio": dialogue_ratio,
                "concrete_detail_density": detail_density,
                "repetition_score": repetition_score,
                "exposition_ratio": exposition_ratio,
            }
        },
        "summary": "synthetic benchmark report",
        "created_at": "2026-04-02T00:00:00Z",
    }


def _simulation_report(
    *,
    pass_rate: float,
    rewrite_rate: float,
    block_rate: float,
    overall_scores: list[float],
    issue_codes: list[str],
    detail_density: float,
    stop_reason: str = "chapter_budget_reached",
    chapter_budget: Optional[int] = None,
    min_end_turn_target: Optional[int] = None,
    decision_sequence: Optional[list[str]] = None,
    repetition_score: float = 0.0,
    exposition_ratio: float = 0.3,
    dialogue_ratio: float = 0.38,
    hook_quality_sequence: Optional[list[float]] = None,
    interactive_summary: Optional[dict[str, object]] = None,
    post_steer_issue_window_summary: Optional[list[dict[str, object]]] = None,
) -> dict[str, object]:
    issue_count = len(overall_scores) if issue_codes else 0
    top_issue_categories = [
        {
            "issue_code": code,
            "count": issue_count,
            "owning_module": ISSUE_TAXONOMY.get(code, {}).get("owning_module", ""),
            "fix_hint": ISSUE_TAXONOMY.get(code, {}).get("fix_hint", ""),
        }
        for code in issue_codes
    ]
    report = {
        "evaluation_summary": {
            "pass_rate": pass_rate,
            "rewrite_rate": rewrite_rate,
            "block_rate": block_rate,
            "top_issue_categories": top_issue_categories,
        },
        "completed_chapters": len(overall_scores),
        "chapter_budget": chapter_budget or len(overall_scores),
        "completion_ratio": round(len(overall_scores) / float(max(1, chapter_budget or len(overall_scores))), 3),
        "min_end_turn_target": min_end_turn_target or len(overall_scores),
        "stop_reason": stop_reason,
        "terminated_by_budget": stop_reason == "chapter_budget_reached",
        "chapter_evaluations": [
            _chapter_report(
                chapter_id=f"chapter_{index}",
                overall_score=score,
                issue_codes=issue_codes,
                detail_density=detail_density,
                decision=(
                    decision_sequence[index - 1]
                    if decision_sequence and index - 1 < len(decision_sequence)
                    else "pass"
                ),
                dialogue_ratio=dialogue_ratio,
                repetition_score=repetition_score,
                exposition_ratio=exposition_ratio,
                hook_quality=(
                    hook_quality_sequence[index - 1]
                    if hook_quality_sequence and index - 1 < len(hook_quality_sequence)
                    else None
                ),
            )
            for index, score in enumerate(overall_scores, start=1)
        ],
    }
    if interactive_summary is not None:
        report["interactive_summary"] = interactive_summary
    if post_steer_issue_window_summary is not None:
        report["post_steer_issue_window_summary"] = post_steer_issue_window_summary
    return report


def test_cross_pack_benchmark_composite_ranking_and_delta_changes(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_delta.db"))
    baseline_reports = {
        "jade_court_exam": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.86, 0.84, 0.83, 0.82],
            issue_codes=["Q04"],
            detail_density=0.018,
        ),
        "urban_mystery_lotus_lane": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.93, 0.92, 0.91, 0.9],
            issue_codes=[],
            detail_density=0.024,
        ),
        "jade_court_romance": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.83, 0.8, 0.79, 0.78],
            issue_codes=["Q05"],
            detail_density=0.012,
        ),
        "xianxia_forgotten_vow": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.88, 0.87, 0.86, 0.85],
            issue_codes=[],
            detail_density=0.017,
        ),
        "synthetic_min_pack": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.9, 0.45, 0.42],
            issue_codes=["Q09"],
            detail_density=0.004,
        ),
    }
    target_worlds = list(baseline_reports)
    baseline = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=target_worlds,
        simulation_runner=lambda world_id, _world_version_id: baseline_reports[world_id],
    )
    current_reports = {
        "jade_court_exam": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.88, 0.39, 0.38],
            issue_codes=["Q09"],
            detail_density=0.006,
        ),
        "urban_mystery_lotus_lane": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.94, 0.93, 0.92, 0.91],
            issue_codes=[],
            detail_density=0.025,
        ),
        "jade_court_romance": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.82, 0.79, 0.78, 0.77],
            issue_codes=["Q05"],
            detail_density=0.01,
        ),
        "xianxia_forgotten_vow": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.8, 0.78, 0.77, 0.76],
            issue_codes=["Q04"],
            detail_density=0.009,
        ),
        "synthetic_min_pack": _simulation_report(
            pass_rate=1.0,
            rewrite_rate=0.0,
            block_rate=0.0,
            overall_scores=[0.92, 0.9, 0.88, 0.86],
            issue_codes=["Q03"],
            detail_density=0.018,
        ),
    }
    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=target_worlds,
        baseline=baseline,
        simulation_runner=lambda world_id, _world_version_id: current_reports[world_id],
    )
    assert report["weakest_packs"][0]["world_id"] == "jade_court_exam"
    assert report["weakest_packs"][0]["pass_rate"] == 1.0
    assert report["delta_summary"]["ranking_changes"]["entered_weakest"] == ["xianxia_forgotten_vow"]
    assert report["delta_summary"]["ranking_changes"]["exited_weakest"] == ["synthetic_min_pack"]
    assert report["delta_summary"]["ranking_changes"]["current_strongest"][0] == "urban_mystery_lotus_lane"
    assert report["delta_summary"]["ranking_changes"]["rank_deltas"]["jade_court_exam"]["diagnostic_rank_delta"] < 0
    assert report["weakest_pack_diagnostics"][0]["world_id"] == "jade_court_exam"
    assert report["weakest_pack_diagnostics"][0]["worst_chapters"][0]["chapter_id"] == "chapter_3"
    assert report["weakest_pack_diagnostics"][0]["attribution_map"]["modules"][0]["module"] == "planner"
    assert report["weakest_pack_diagnostics"][0]["next_fix_candidates"][0]["asset"] == "scene_blueprints"
    assert report["weakest_pack_diagnostics"][0]["stop_condition"]["status"] == "continue_polish"
    assert report["weakest_pack_polish_program"]["status"] == "continue_polish"
    assert "phase_a_quality_gate" in report
    assert report["phase_a_quality_gate"]["config_version"] == "phase_a_quality_gate_v1"
    markdown = main(
        [
            "--worldpack",
            "jade_court_exam",
            "--golden-dir",
            str(tmp_path / "goldens"),
            "--database-url",
            "sqlite:///%s" % (tmp_path / "benchmark_cli.db"),
            "--baseline-file",
            str(tmp_path / "baseline.json"),
            "--markdown-out",
            str(tmp_path / "summary.md"),
        ]
    )
    assert markdown == 0
    markdown_text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "benchmark delta" in markdown_text
    assert "Strongest Packs" in markdown_text
    assert "Weakest Packs" in markdown_text
    assert "Weakest Pack Diagnostics" in markdown_text
    assert "Weakest Pack Polish Program" in markdown_text
    assert "Phase A Quality Gate" in markdown_text
    assert "Longform L1 Sign-off" in markdown_text
    assert "issue mix" in markdown_text


def test_long_route_benchmark_outputs_route_level_metrics(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "long_route.db"))
    target_worlds = ["jade_court_exam", "synthetic_min_pack"]
    long_route_reports = {
        "jade_court_exam": _simulation_report(
            pass_rate=0.75,
            rewrite_rate=0.25,
            block_rate=0.0,
            overall_scores=[0.91] * 12 + [0.72] * 12 + [0.68] * 12,
            issue_codes=["Q09"],
            detail_density=0.014,
            stop_reason="chapter_budget_reached",
            chapter_budget=36,
            min_end_turn_target=30,
            decision_sequence=(["pass"] * 12) + (["pass"] * 6 + ["rewrite"] * 6) + (["rewrite"] * 9 + ["pass"] * 3),
            repetition_score=0.18,
            exposition_ratio=0.41,
            hook_quality_sequence=[0.88] * 12 + [0.61] * 12 + [0.53] * 12,
        ),
        "synthetic_min_pack": _simulation_report(
            pass_rate=0.4,
            rewrite_rate=0.6,
            block_rate=0.0,
            overall_scores=[0.82] * 6 + [0.61] * 6,
            issue_codes=["Q09"],
            detail_density=0.01,
            stop_reason="no_legal_routes",
            chapter_budget=36,
            min_end_turn_target=30,
            decision_sequence=(["pass"] * 6) + (["rewrite"] * 6),
            repetition_score=0.29,
            exposition_ratio=0.52,
            hook_quality_sequence=[0.8] * 6 + [0.46] * 6,
        ),
    }
    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=target_worlds,
        baseline=None,
        simulation_runner=lambda world_id, _world_version_id: long_route_reports[world_id],
        max_chapters=36,
        min_end_turn_override=30,
    )
    assert report["benchmark_mode"] == "long_route"
    assert report["chapter_budget"] == 36
    assert report["long_route_summary"]["target_chapters"] == 36
    assert report["long_route_summary"]["premature_ending_packs"] == ["synthetic_min_pack"]
    exam = next(item for item in report["worlds"] if item["world_id"] == "jade_court_exam")
    synthetic = next(item for item in report["worlds"] if item["world_id"] == "synthetic_min_pack")
    assert exam["completion_ratio"] == 1.0
    assert exam["mid_arc_pass_rate"] == 0.5
    assert exam["late_arc_pass_rate"] == 0.25
    assert exam["avg_repetition_score"] == 0.18
    assert synthetic["stop_reason"] == "no_legal_routes"
    assert synthetic["premature_ending"] is True
    assert synthetic["completion_ratio"] == 0.333
    assert report["weakest_pack_diagnostics"][0]["stop_reason"] in {"chapter_budget_reached", "no_legal_routes"}
    markdown = main(
        [
            "--worldpack",
            "jade_court_exam",
            "--golden-dir",
            str(tmp_path / "goldens"),
            "--database-url",
            "sqlite:///%s" % (tmp_path / "long_route_cli.db"),
            "--baseline-file",
            str(tmp_path / "long_route_baseline.json"),
            "--markdown-out",
            str(tmp_path / "long_route_summary.md"),
            "--max-chapters",
            "36",
            "--min-end-turn-override",
            "30",
        ]
    )
    assert markdown == 0
    markdown_text = (tmp_path / "long_route_summary.md").read_text(encoding="utf-8")
    assert "benchmark mode: long_route" in markdown_text
    assert "Long-Route Summary" in markdown_text
    assert "target chapters: 36" in markdown_text
    assert "q03 calibration recommendations" in markdown_text
    assert "q09 calibration recommendations" in markdown_text


def test_long_route_benchmark_supports_strong_interactive_profile(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "interactive_long_route.db"))
    target_worlds = ["jade_court_exam", "synthetic_min_pack"]
    seen_scenarios: dict[str, list[dict[str, object]]] = {}

    def simulation_runner(world_id, _world_version_id, interactive_scenarios):
        seen_scenarios[world_id] = [dict(item) for item in interactive_scenarios]
        return _simulation_report(
            pass_rate=0.95,
            rewrite_rate=0.05,
            block_rate=0.0,
            overall_scores=[0.89] * 200,
            issue_codes=["Q03"],
            detail_density=0.024,
            chapter_budget=200,
            interactive_summary={
                "scenario_count": len(interactive_scenarios),
                "steering_recovery_rate": 1.0,
                "post_steer_route_survival": 0.92,
                "memory_consistency_after_steer": 0.88,
                "promise_reconciliation_after_steer": 0.84,
                "replan_stability_score": 0.9,
            },
            post_steer_issue_window_summary=[
                {
                    "scenario_id": f"scenario_{index}",
                    "scenario_kind": str(scenario.get("scenario_kind") or ""),
                    "chapter_index": int(scenario.get("trigger_chapter", 0) or 0),
                    "short_window": {
                        "chapter_count": 3,
                        "issue_counts": {"Q03": 1, "Q04": 0, "Q05": 0, "Q09": 0},
                        "issue_rates": {"Q03": 0.333, "Q04": 0.0, "Q05": 0.0, "Q09": 0.0},
                    },
                    "long_window": {
                        "chapter_count": 10,
                        "issue_counts": {"Q03": 2, "Q04": 1, "Q05": 0, "Q09": 1},
                        "issue_rates": {"Q03": 0.2, "Q04": 0.1, "Q05": 0.0, "Q09": 0.1},
                    },
                }
                for index, scenario in enumerate(interactive_scenarios, start=1)
            ],
        )

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=target_worlds,
        baseline=None,
        simulation_runner=simulation_runner,
        benchmark_mode="long_route",
        max_chapters=200,
        interactive_profile="strong",
    )

    assert report["benchmark_mode"] == "long_route"
    assert report["interactive_profile"] == "strong"
    assert report["content_quality_contract_summary"]["band"] == "200"
    assert report["content_quality_contract_summary"]["gate_enforced"] is False
    assert report["interactive_long_route_summary"]["scenario_count"] == 5
    assert report["interactive_long_route_summary"]["avg_short_window_issue_rates"]["Q03"] == 0.333
    assert report["interactive_long_route_summary"]["avg_long_window_issue_rates"]["Q09"] == 0.1
    assert [item["trigger_chapter"] for item in seen_scenarios["jade_court_exam"]] == [20, 60, 100, 140, 180]

    exam = next(item for item in report["worlds"] if item["world_id"] == "jade_court_exam")
    assert exam["interactive_summary"]["scenario_count"] == 5
    assert len(exam["post_steer_issue_window_summary"]) == 5

    markdown = render_benchmark_markdown(report)
    assert "Interactive Long-Route Summary" in markdown
    assert "Content Quality Contract Summary" in markdown
    assert "band: 200" in markdown
    assert "profile: strong" in markdown
    assert "Post-Steer Issue Windows" in markdown


def test_200_diagnostic_surface_exposes_q05_detail_breaches(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "diagnostic_q05.db"))
    target_worlds = ["synthetic_min_pack"]
    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack=target_worlds,
        baseline=None,
        benchmark_mode="long_route",
        max_chapters=200,
        simulation_runner=lambda _world_id, _world_version_id: _simulation_report(
            pass_rate=0.9,
            rewrite_rate=0.1,
            block_rate=0.0,
            overall_scores=[0.82] * 200,
            issue_codes=[],
            detail_density=0.001,
            dialogue_ratio=0.25,
            exposition_ratio=0.55,
            chapter_budget=200,
        ),
    )
    world = report["worlds"][0]
    issue_codes = [item["issue_code"] for item in world["issue_mix"]]
    assert "Q05" in issue_codes
    assert report["content_quality_contract_summary"]["band"] == "200"
    diagnostic = report["weakest_pack_diagnostics"][0]
    assert any("Q05" in item.get("issue_codes", []) for item in diagnostic["window_breach_attribution"])
