from typing import Optional

from src.narrativeos.benchmark.runner import BENCHMARK_PACKS, main, run_benchmark
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
    return {
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


def test_cross_pack_benchmark_composite_ranking_and_delta_changes(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "benchmark_delta.db"))
    target_worlds = list(BENCHMARK_PACKS)
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
