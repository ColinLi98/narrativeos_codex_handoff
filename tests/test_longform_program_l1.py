from __future__ import annotations

from pathlib import Path

from src.narrativeos.benchmark.reporting import (
    build_longform_250_interactive_signoff,
    build_longform_250_human_review_closeout,
    build_longform_250_signoff,
    build_longform_1000_feasibility,
    build_longform_1000_human_review_closeout,
    build_longform_1000_interactive_signoff,
    build_longform_1000_readiness,
    build_longform_500_ending_signoff,
    build_longform_500_human_review_closeout,
    build_longform_500_interactive_signoff,
    build_longform_500_signoff,
)
from src.narrativeos.benchmark.runner import run_benchmark
from src.narrativeos.longform import configure_longform_runtime, default_chapter_task, longform_min_end_turn_floor, longform_terminal_allowed
from src.narrativeos.pipeline import plan_next_turn_from_events
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService, _resolve_longform_structure
from src.narrativeos.services.training_signal import TrainingSignalService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry
from src.narrativeos.worldpacks.validator import validate_worldpack_payload


def test_authoring_brief_generates_longform_planning_skeleton(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_brief.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_l1_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证长篇规划骨架。",
            "life_theme": "长线关系与承诺如何持续推进",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]

    validation = validate_worldpack_payload(worldpack)
    assert validation["ok"] is True
    assert worldpack["series_plan"]["total_chapter_target"] == 100
    assert worldpack["series_plan"]["total_volume_target"] == 5
    assert len(worldpack["volume_plans"]) == 5
    assert len(worldpack["arc_plans"]) >= 15
    assert worldpack["chapter_budget_policy"]["default_target_words"] == 2000
    assert worldpack["chapter_budget_policy"]["min_target_words"] == 1800
    assert worldpack["chapter_budget_policy"]["max_target_words"] == 2200
    assert worldpack["metadata"]["longform_program_stage"] == "L1_foundation"
    assert worldpack["arc_plans"][0]["chapter_tasks"]


def test_configure_longform_runtime_raises_min_end_turn_floor(demo_world, demo_state):
    configure_longform_runtime(
        demo_state,
        series_plan={
            "series_id": "series_demo",
            "title": "demo",
            "total_volume_target": 5,
            "total_chapter_target": 100,
            "target_word_count": 200000,
        },
        volume_plans=[
            {
                "volume_id": "series_demo::volume_1",
                "order": 1,
                "title": "第1卷",
                "goal": "推进",
                "target_chapters": 20,
                "climax_definition": "改变关系",
                "end_state": "打开下一卷",
            }
        ],
        arc_plans=[],
        chapter_budget_policy={"default_target_words": 2000},
        world=demo_world,
    )
    assert demo_state.min_end_turn == longform_min_end_turn_floor(100)
    assert demo_state.metadata["longform_min_end_turn_floor"] == longform_min_end_turn_floor(100)


def test_plan_next_turn_exposes_longform_task_and_context(demo_world, demo_state, demo_events):
    demo_state.current_series_id = "series_demo"
    demo_state.current_volume_id = "series_demo::volume_1"
    demo_state.current_arc_id = "series_demo::volume_1::arc_1"
    demo_state.word_budget = 2000

    result = plan_next_turn_from_events(
        demo_state,
        demo_events,
        world=demo_world,
        debug=True,
    )

    assert result["status"] == "ok"
    assert result["chapter_plan"]["chapter_task"]["duty_type"]
    assert result["chapter_plan"]["chapter_task_execution_summary"]["target_words"] == 2000
    assert result["longform_context_pack"]["current_series_id"] == "series_demo"
    assert "promise_ledger" in result["longform_context_pack"]
    assert "rolling_recap" in result["updated_state"]


def test_longform_progression_state_machine_advances_arc_and_volume(tmp_path: Path, demo_world, demo_state):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_progress.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_progress_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证长篇推进状态机。",
            "life_theme": "让卷和弧线真正前进",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_progress",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    worldpack = authoring.get_draft(draft["world_version_id"])["worldpack"]
    configure_longform_runtime(
        demo_state,
        series_plan=dict(worldpack["series_plan"]),
        volume_plans=list(worldpack["volume_plans"]),
        arc_plans=list(worldpack["arc_plans"]),
        chapter_budget_policy=dict(worldpack["chapter_budget_policy"]),
        world=demo_world,
    )

    demo_state.chapter_index = 1
    first_task = default_chapter_task(demo_state, demo_world)
    assert demo_state.metadata["longform_progression"]["volume_order"] == 1
    assert demo_state.metadata["longform_progression"]["arc_order"] == 1
    assert first_task["chapter_task_id"].endswith("task_1")

    demo_state.chapter_index = 7
    second_arc_task = default_chapter_task(demo_state, demo_world)
    assert demo_state.metadata["longform_progression"]["volume_order"] == 1
    assert demo_state.metadata["longform_progression"]["arc_order"] == 2
    assert second_arc_task["chapter_task_id"].startswith(f"{demo_state.current_arc_id}::")

    demo_state.chapter_index = 21
    second_volume_task = default_chapter_task(demo_state, demo_world)
    assert demo_state.metadata["longform_progression"]["volume_order"] == 2
    assert demo_state.metadata["longform_progression"]["volume_id"].endswith("volume_2")
    assert second_volume_task["target_words"] == 2000


def test_longform_terminal_gate_blocks_early_terminal_scene(demo_world, demo_state, demo_events):
    terminal_event = demo_events[0]
    demo_state.current_series_id = "series_demo"
    demo_state.current_volume_id = "series_demo::volume_1"
    demo_state.current_arc_id = "series_demo::volume_1::arc_1"
    chapter_task = {
        "chapter_task_id": "series_demo::task_1",
        "objective": "先推进，不允许提前完结",
        "duty_type": "advance_plot",
        "target_words": 2000,
        "reveal_budget": 1,
        "promise_actions": ["maintain_continuity"],
        "allow_terminal": False,
        }
    assert longform_terminal_allowed(demo_state, chapter_task, terminal_event) is False


def test_simulation_report_includes_longform_drilldown(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_sim.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_sim_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 simulation longform drilldown。",
            "life_theme": "章节职责如何持续推进",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )

    report = authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )

    assert report["longform_drilldown"]["volume_progress"]
    assert report["longform_drilldown"]["arc_progress"]
    assert report["longform_gate"]["status"] == "not_applicable"
    assert report["longform_plan_snapshot"]["series_plan"]["total_chapter_target"] == 100

    detail = authoring.get_draft(draft["world_version_id"])
    assert detail["promise_ledger_workbench"]["available"] is True
    assert "open_count" in detail["promise_ledger_workbench"]
    assert detail["promise_state_workbench"]["available"] is True
    assert detail["promise_state_workbench"]["editable_promises"]
    assert detail["series_volume_arc_promise_mapping"]["available"] is True
    assert detail["series_volume_arc_promise_mapping"]["volumes"]
    assert detail["chapter_task_simulation_linking"]["available"] is True
    assert detail["chapter_task_simulation_linking"]["task_links"]
    assert detail["chapter_task_simulation_linking"]["task_links"][0]["linked_chapters"]
    assert "promise_targets" in detail["chapter_task_simulation_linking"]["task_links"][0]
    assert "planned_promises" in detail["chapter_task_simulation_linking"]["task_links"][0]
    assert detail["continuity_diff_workbench"]["available"] is True
    assert detail["continuity_override_workbench"]["available"] is True
    assert detail["continuity_override_workbench"]["candidate_chapters"]
    assert "simulation_freshness" in detail["continuity_diff_workbench"]


def test_longform_simulation_survives_past_initial_route_exhaustion(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_survival.db"))
    authoring = AuthoringService(repository)

    report = authoring.run_simulation_for_world_version(
        authoring._select_candidate_world_version_id("synthetic_min_pack"),
        include_cross_pack=False,
        max_chapters=12,
    )

    assert report["completed_chapters"] >= 12
    assert report["stop_reason"] == "chapter_budget_reached"


def test_runtime_fallback_longform_plan_reduces_duty_looping(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_runtime_fallback.db"))
    authoring = AuthoringService(repository)

    report = authoring.run_simulation_for_world_version(
        authoring._select_candidate_world_version_id("synthetic_min_pack"),
        include_cross_pack=False,
        max_chapters=12,
    )

    duties = [str((item.get("chapter_task") or {}).get("duty_type") or "") for item in report["chapter_trace"]]
    repeats = sum(1 for index in range(1, len(duties)) if duties[index] == duties[index - 1])
    assert report["longform_plan_snapshot"]["plan_source"] == "runtime_fallback"
    assert report["longform_summary"]["arc_task_repeat_rate"] <= 0.25
    assert repeats == 0


def test_authoring_can_bootstrap_longform_workbench_for_legacy_pack(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_bootstrap.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    draft = authoring.save_draft(pack, change_context={"source": "legacy_clone", "label": "复制旧 pack"})

    bootstrapped = authoring.bootstrap_longform_workbench(draft["world_version_id"])
    worldpack = bootstrapped["worldpack"]

    assert worldpack["series_plan"]["total_chapter_target"] >= 24
    assert worldpack["volume_plans"]
    assert worldpack["arc_plans"]
    assert worldpack["metadata"]["longform_program_stage"] == "L2_workbench"
    assert worldpack["metadata"]["longform_workbench_bootstrapped"] is True


def test_authoring_can_persist_chapter_task_edit(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_task_edit.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_task_edit_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 chapter task 编辑持久化。",
            "life_theme": "让任务编辑回写到 draft",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    first_arc = worldpack["arc_plans"][0]
    first_task = first_arc["chapter_tasks"][0]
    first_task["duty_type"] = "deliver_climax"
    first_task["objective"] = "把这一章改成更强的高潮推进。"
    first_task["target_words"] = 2300
    first_task["reveal_budget"] = 3
    first_task["promise_actions"] = ["advance_payoff", "close_arc_loop"]
    first_task["promise_targets"] = ["promise_1", "promise_2"]
    first_task["allow_terminal"] = True

    updated = authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "longform_editor", "label": "保存 chapter task"},
    )

    persisted_task = updated["worldpack"]["arc_plans"][0]["chapter_tasks"][0]
    assert persisted_task["duty_type"] == "deliver_climax"
    assert persisted_task["objective"] == "把这一章改成更强的高潮推进。"
    assert persisted_task["target_words"] == 2300
    assert persisted_task["reveal_budget"] == 3
    assert persisted_task["promise_actions"] == ["advance_payoff", "close_arc_loop"]
    assert persisted_task["promise_targets"] == ["promise_1", "promise_2"]
    assert persisted_task["allow_terminal"] is True


def test_quick_brief_simulation_surfaces_promise_runway_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "quick_brief_runway_summary.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "xianxia",
            "world_title": "quick_brief_runway_world",
            "lead_name": "沈照",
            "counterpart_name": "叶青烛",
            "core_premise": "验证 quick brief 也会给出 promise runway summary。",
            "life_theme": "长线续航需要 promises 先撑住",
            "locations": "太玄山门\n沉星古渡\n北辰废宫",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 10,
            "target_word_count": 220000,
        }
    )

    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=12,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    runway = detail["promise_runway_summary"]
    assert runway["available"] is True
    assert runway["open_count"] >= 1
    assert runway["runway_status"] in {"healthy", "thinning", "exhausted"}
    assert "promise_runway_summary" in detail["longform_drilldown"]


def test_longform_drilldown_flags_midrun_structure_exhaustion():
    repository = SQLAlchemyRepository(database_url="sqlite://")
    authoring = AuthoringService(repository)
    simulation_report = {
        "completed_chapters": 36,
        "evaluation_summary": {
            "top_issue_categories": [
                {"issue_code": "Q04", "count": 4},
                {"issue_code": "Q09", "count": 5},
            ]
        },
        "chapter_evaluations": [
            {
                "chapter_id": f"chapter_{index}",
                "scores": {
                    "pacing": 0.31,
                    "hook_quality": 0.44,
                    "scene_density": 0.52,
                    "overall_score": 0.41,
                },
                "issues": [
                    {"issue_code": "Q04"},
                    {"issue_code": "Q09"},
                ],
                "hard_validator_results": {
                    "lint_metrics": {
                        "exposition_ratio": 0.56,
                    }
                },
            }
            for index in range(32, 37)
        ],
        "chapter_trace": [
            {
                "chapter_id": f"chapter_{index}",
                "chapter_title": f"第{index}章",
                "scene_function": "false_peace",
                "chapter_task_execution_summary": {"series_chapter_index": index},
                "open_promise_ids": [],
                "closed_promise_ids": [],
            }
            for index in range(32, 37)
        ],
        "final_state_snapshot": {
            "turn_index": 36,
            "open_promises": [],
            "metadata": {"closed_promise_ids": ["promise_closed_1", "promise_closed_2"]},
        },
        "longform_summary": {
            "series_id": "series_demo",
            "target_chapters": 100,
        },
        "longform_plan_snapshot": {
            "series_plan": {
                "series_id": "series_demo",
                "title": "长线世界",
                "total_chapter_target": 100,
            },
            "volume_plans": [
                {
                    "volume_id": "volume_1",
                    "order": 1,
                    "title": "卷一",
                    "target_chapters": 50,
                }
            ],
            "arc_plans": [
                {
                    "arc_id": "arc_1",
                    "volume_id": "volume_1",
                    "order": 1,
                    "title": "弧线一",
                    "target_chapters": 20,
                    "chapter_tasks": [{"chapter_task_id": "task_1"}],
                }
            ],
        },
    }

    drilldown = authoring._build_longform_drilldown(simulation_report)

    assert drilldown["promise_runway_summary"]["runway_status"] == "exhausted"
    assert drilldown["midrun_signal_window"]["avg_pacing"] < 0.34
    assert drilldown["midrun_signal_window"]["avg_exposition_ratio"] > 0.5
    assert drilldown["midrun_signal_window"]["scene_family_repeat_ratio"] == 1.0
    assert drilldown["longform_structure_exhaustion"]["key"] == "longform_structure_exhaustion"
    assert set(drilldown["longform_structure_exhaustion"]["trigger_issue_codes"]) == {"Q04", "Q09"}


def test_authoring_can_persist_promise_state_edit(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_promise_state.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_promise_state_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 promise state 编辑持久化。",
            "life_theme": "让 promise 风险可以被作者标注",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    promise_item = detail["promise_state_workbench"]["editable_promises"][0]
    task_link = detail["chapter_task_simulation_linking"]["task_links"][0]
    updated = authoring.update_promise_state(
        draft["world_version_id"],
        promise_id=promise_item["promise_id"],
        editor_state="defer",
        notes="延后到下一条 arc 再回收。",
        chapter_index=promise_item["last_seen_chapter"],
        chapter_task_id=task_link["chapter_task_id"],
        arc_id=task_link["arc_id"],
        volume_id=task_link["volume_id"],
    )

    persisted = next(
        item
        for item in updated["promise_state_workbench"]["editable_promises"]
        if item["promise_id"] == promise_item["promise_id"]
    )
    assert persisted["editor_state"] == "defer"
    assert persisted["editor_notes"] == "延后到下一条 arc 再回收。"
    assert updated["promise_state_workbench"]["override_count"] == 1
    assert updated["revision_history"][-1]["source"] == "promise_state_editor"


def test_authoring_can_persist_continuity_override(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_continuity_override.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_continuity_override_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 continuity override 持久化。",
            "life_theme": "让作者能标记刻意漂移与接受的权衡",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    candidate = detail["continuity_override_workbench"]["candidate_chapters"][0]
    updated = authoring.update_continuity_override(
        draft["world_version_id"],
        chapter_index=int(candidate["chapter_index"]),
        override_state="intentional",
        notes="这是刻意保留的漂移，下一次 payoff 会解释。",
        issue_scope=list(candidate.get("issue_codes", [])),
        chapter_task_id=candidate.get("chapter_task_id"),
        arc_id=candidate.get("arc_id"),
        volume_id=candidate.get("volume_id"),
    )
    persisted = next(
        item
        for item in updated["continuity_override_workbench"]["candidate_chapters"]
        if int(item["chapter_index"]) == int(candidate["chapter_index"])
    )
    assert persisted["override_state"] == "intentional"
    assert persisted["override_notes"] == "这是刻意保留的漂移，下一次 payoff 会解释。"
    assert updated["continuity_override_workbench"]["override_count"] == 1
    assert updated["revision_history"][-1]["source"] == "continuity_override_editor"


def test_task_level_compare_diff_is_exposed_after_resimulation(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_task_compare.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_task_compare_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 task-level compare diff。",
            "life_theme": "让任务编辑和章节对照真正连起来",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["arc_plans"][0]["chapter_tasks"][0]["objective"] = "把第一条 task 改成更明显的关系推进。"
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "longform_editor", "label": "更新 task 以触发 compare"},
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    refreshed = authoring.get_draft(draft["world_version_id"])
    first_task = refreshed["chapter_task_simulation_linking"]["task_links"][0]
    assert "compare_summary" in first_task
    assert "compare_chapters" in first_task
    assert first_task["compare_summary"]["compared_chapter_count"] >= 0
    assert "promise_drift" in first_task
    assert "planned_only_ids" in first_task["promise_drift"]
    assert "observed_only_ids" in first_task["promise_drift"]
    assert "remediation_suggestions" in first_task
    assert "rewrite_workflow" in first_task
    assert refreshed["simulation_diff_checkpoint"]["available"] is True


def test_simulation_diff_checkpoint_marks_pending_resimulation_after_task_edit(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_checkpoint_pending.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_checkpoint_pending_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 checkpoint 在 task 编辑后提示待重跑。",
            "life_theme": "让 rewrite 后的状态更可见",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["arc_plans"][0]["chapter_tasks"][0]["objective"] = "把这一条改成新的 rewrite 目标。"
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "longform_editor", "label": "更新 task 触发 checkpoint"},
    )
    refreshed = authoring.get_draft(draft["world_version_id"])
    assert refreshed["simulation_diff_checkpoint"]["status"] == "pending_resimulation"
    assert refreshed["simulation_diff_checkpoint"]["auto_resimulate_suggested"] is True
    assert refreshed["simulation_diff_checkpoint"]["suggested_action"] == "simulate_draft"


def test_authoring_can_bulk_apply_task_to_simulation(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_task_bulk_apply.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_task_bulk_apply_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 task bulk apply 到 simulation。",
            "life_theme": "让一条 task 对应的章节可一次性标记",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    detail = authoring.get_draft(draft["world_version_id"])
    first_task = detail["chapter_task_simulation_linking"]["task_links"][0]
    chapter_indices = [int(item["chapter_index"]) for item in first_task["linked_chapters"]]
    updated = authoring.bulk_apply_task_continuity_override(
        draft["world_version_id"],
        chapter_indices=chapter_indices,
        override_state="needs_rewrite",
        notes="这一组章节统一重写。",
        issue_scope=["Q06", "Q07"],
        chapter_task_id=first_task["chapter_task_id"],
        arc_id=first_task["arc_id"],
        volume_id=first_task["volume_id"],
    )
    overrides = {
        int(item["chapter_index"]): item
        for item in updated["continuity_override_workbench"]["candidate_chapters"]
        if item["override_state"] == "needs_rewrite"
    }
    assert chapter_indices
    assert all(index in overrides for index in chapter_indices)
    assert updated["revision_history"][-1]["source"] == "task_bulk_apply"


def test_task_promise_drift_reports_planned_only_ids(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_task_promise_drift.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "longform_task_promise_drift_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 task promise drift。",
            "life_theme": "让计划中的 promise 目标和实际观测能对照出来",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    worldpack["arc_plans"][0]["chapter_tasks"][0]["promise_targets"] = ["promise_planned_only"]
    authoring.update_draft(
        draft["world_version_id"],
        worldpack,
        change_context={"source": "longform_editor", "label": "设置 promise targets"},
    )
    authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=6,
    )
    refreshed = authoring.get_draft(draft["world_version_id"])
    first_task = refreshed["chapter_task_simulation_linking"]["task_links"][0]
    assert first_task["promise_targets"] == ["promise_planned_only"]
    assert first_task["promise_drift"]["status"] in {"planned_only", "diverged"}
    assert "promise_planned_only" in first_task["promise_drift"]["planned_only_ids"]
    assert first_task["promise_drift"]["recommended_actions"]
    assert first_task["remediation_suggestions"]
    assert first_task["rewrite_workflow"]["available"] is True


def test_benchmark_supports_longform_100_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 100,
            "chapter_budget": 100,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 90,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.04,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.12,
                "q09_incidence_rate": 0.02,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.05,
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_100",
        max_chapters=12,
    )

    assert report["benchmark_mode"] == "longform_100"
    assert report["chapter_budget"] == 100
    assert report["longform_summary"]["target_chapters"] == 100
    assert report["longform_summary"]["gate_pass_rate"] == 1.0
    assert report["longform_summary"]["q09_incidence_rate"] == 0.02
    assert report["longform_gate"]["passed_world_count"] == 1
    assert "calibration" in report["longform_gate"]
    assert report["worlds"][0]["longform_gate"]["passed"] is True
    assert report["worlds"][0]["character_drift_rate"] == 0.04
    assert report["worlds"][0]["premature_ending_trigger_rate"] == 0.0


def test_authoring_simulation_supports_interactive_steering(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "interactive_longform_sim.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "interactive_longform_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 interactive steering simulation。",
            "life_theme": "让 reader 引导仍能稳定生成后续章节",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    report = authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=12,
        interactive_scenarios=[
            {
                "scenario_id": "memory_steer",
                "scenario_kind": "memory_steer",
                "trigger_chapter": 4,
                "label": "reader 补记忆",
                "steering_directive": {
                    "memory_patch_note": "角色突然想起一段旧事，影响后续选择。",
                    "impacted_character_ids": ["lead"],
                },
            }
        ],
    )
    assert report["steering_checkpoints"]
    assert report["replan_history"]
    assert report["memory_patch_summary"]["pending_count"] >= 0
    assert report["interactive_summary"]["scenario_count"] == 1
    assert "steering_recovery_rate" in report["interactive_summary"]
    assert report["creative_cockpit"]["available"] is True
    assert report["creative_cockpit"]["steering_timeline"]["checkpoint_count"] == 1
    assert "relationship_network" in report["creative_cockpit"]
    assert "impacted_character_ids" in report["creative_cockpit"]["steering_timeline"]["entries"][0]
    assert "chapter_task_id" in report["creative_cockpit"]["chapter_heatmap"]["chapters"][0]
    assert "scene_id" in report["creative_cockpit"]["chapter_heatmap"]["chapters"][0]

    detail = authoring.get_draft(draft["world_version_id"])
    assert detail["creative_cockpit"]["steering_timeline"]["checkpoint_count"] == 1
    assert "chapter_heatmap" in detail["creative_cockpit"]


def test_creative_cockpit_groups_heatmap_hotspots_into_asset_priorities(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "creative_cockpit_issue_groups.db"))
    authoring = AuthoringService(repository)
    cockpit = authoring._build_creative_cockpit(
        {
            "characters": [
                {"character_id": "lead", "display_name": "甲", "role": "lead"},
                {"character_id": "counterpart", "display_name": "乙", "role": "counterpart"},
            ],
            "scene_blueprints": [
                {
                    "scene_id": "scene_false_peace",
                    "scene_function": "false_peace",
                    "required_roles": ["lead", "counterpart"],
                }
            ],
        },
        {
            "final_state_snapshot": {
                "relationship_graph": [],
                "characters": {},
                "volume_memory_snapshots": [],
                "series_memory_snapshots": [],
                "series_ending_checkpoint": {},
                "replan_stability_metrics": {},
            },
            "simulation_drilldown": {
                "chapter_breakdown": [
                    {"chapter_index": 1, "chapter_title": "第1章", "decision": "rewrite", "overall_score": 0.41, "issue_codes": ["Q03"], "scene_function": "false_peace"},
                    {"chapter_index": 2, "chapter_title": "第2章", "decision": "rewrite", "overall_score": 0.38, "issue_codes": ["Q04"], "scene_function": "false_peace"},
                    {"chapter_index": 3, "chapter_title": "第3章", "decision": "rewrite", "overall_score": 0.35, "issue_codes": ["Q05"], "scene_function": "false_peace"},
                    {"chapter_index": 4, "chapter_title": "第4章", "decision": "block", "overall_score": 0.21, "issue_codes": ["Q09"], "scene_function": "false_peace"},
                ],
                "decision_histogram": {"rewrite": 3, "block": 1},
            },
            "chapter_trace": [
                {
                    "chapter_id": "chapter_1",
                    "scene_function": "false_peace",
                    "chapter_task": {"chapter_task_id": "task_1"},
                    "arc_id": "arc_1",
                    "volume_id": "volume_1",
                    "chapter_task_execution_summary": {"series_chapter_index": 1},
                },
                {
                    "chapter_id": "chapter_2",
                    "scene_function": "false_peace",
                    "chapter_task": {"chapter_task_id": "task_2"},
                    "arc_id": "arc_1",
                    "volume_id": "volume_1",
                    "chapter_task_execution_summary": {"series_chapter_index": 2},
                },
                {
                    "chapter_id": "chapter_3",
                    "scene_function": "false_peace",
                    "chapter_task": {"chapter_task_id": "task_3"},
                    "arc_id": "arc_1",
                    "volume_id": "volume_1",
                    "chapter_task_execution_summary": {"series_chapter_index": 3},
                },
                {
                    "chapter_id": "chapter_4",
                    "scene_function": "false_peace",
                    "chapter_task": {"chapter_task_id": "task_4"},
                    "arc_id": "arc_1",
                    "volume_id": "volume_1",
                    "chapter_task_execution_summary": {"series_chapter_index": 4},
                },
            ],
            "longform_plan_snapshot": {
                "volume_plans": [{"volume_id": "volume_1", "order": 1, "title": "卷一", "target_chapters": 4}],
                "arc_plans": [{"arc_id": "arc_1", "volume_id": "volume_1", "order": 1, "title": "弧线一", "target_chapters": 4, "chapter_tasks": [{"chapter_task_id": "task_1"}]}],
            },
        },
    )
    groups = {item["issue_code"]: item for item in cockpit["chapter_heatmap"]["issue_priority_groups"]}
    assert groups["Q03"]["primary_asset_type"] == "scene_blueprint"
    assert groups["Q03"]["primary_validation_panel"] == "compare"
    assert groups["Q04"]["asset_priorities"][1]["asset_type"] == "character_card"
    assert groups["Q04"]["asset_priorities"][1]["validation_panel"] == "continuity"
    assert groups["Q05"]["asset_priorities"][1]["available"] is True
    assert groups["Q09"]["primary_asset_type"] == "chapter_task"
    assert groups["Q09"]["primary_asset"]["validation_panel"] == "task_linking"


def test_repair_loop_outcome_compares_latest_issue_group_against_prior_simulation():
    repository = SQLAlchemyRepository(database_url="sqlite://")
    authoring = AuthoringService(repository)
    revisions = [
        {
            "revision_id": "rev_base",
            "simulation_snapshot": {
                "chapter_snapshots": [
                    {"chapter_index": 1, "chapter_title": "第1章", "decision": "rewrite", "issue_codes": ["Q05"]},
                    {"chapter_index": 2, "chapter_title": "第2章", "decision": "block", "issue_codes": ["Q05", "Q09"]},
                ]
            },
        },
        {
            "revision_id": "rev_fix",
            "repair_loop_context": {
                "issue_code": "Q05",
                "issue_label": "lack of scene detail",
                "asset_type": "scene_blueprint",
                "asset_label": "场景蓝图",
                "target_label": "scene_false_peace",
                "validation_panel": "compare",
                "validation_panel_label": "Compare",
                "validation_reason": "改完 scene 后回 Compare 看前后章节差异。",
                "scene_id": "scene_false_peace",
                "scene_function": "false_peace",
                "chapter_index": 1,
                "chapter_title": "第1章",
                "targeted_chapter_indices": [1, 2],
                "window_label": "early",
                "window_breach_kind": "early_window_q03_q04_share",
                "contract_failed_checks": ["detail_density_floor"],
            },
        },
    ]
    outcome = authoring._build_repair_loop_outcome(
        revisions,
        current_issue_groups=[
            {
                "issue_code": "Q05",
                "chapter_count": 1,
                "primary_asset_type": "scene_blueprint",
            }
        ],
        current_chapter_heatmap=[
            {
                "chapter_index": 2,
                "chapter_title": "第2章",
                "decision": "rewrite",
                "issue_count": 1,
                "issue_codes": ["Q05"],
            }
        ],
    )
    assert outcome["repair_loop_revision_id"] == "rev_fix"
    assert outcome["baseline_issue_count"] == 2
    assert outcome["current_issue_count"] == 1
    assert outcome["count_delta"] == -1
    assert outcome["baseline_worst_decision"] == "block"
    assert outcome["current_worst_decision"] == "rewrite"
    assert outcome["window_label"] == "early"
    assert outcome["window_breach_kind"] == "early_window_q03_q04_share"
    assert outcome["baseline_window_issue_count"] == 2
    assert outcome["current_window_issue_count"] == 1
    assert outcome["baseline_window_worst_decision"] == "block"
    assert outcome["current_window_worst_decision"] == "rewrite"
    assert outcome["severity_trend"] == "improved"
    assert outcome["ready_for_validation"] is True
    assert outcome["resolved_chapters"][0]["chapter_index"] == 1
    assert outcome["resolved_window_chapters"][0]["chapter_index"] == 1


def test_authoring_simulation_snapshots_final_completed_volume(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "final_volume_snapshot.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "volume_snapshot_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 final volume snapshot。",
            "life_theme": "长线推进不漏掉最终卷快照",
            "locations": "中庭\n长廊\n窗边",
            "author_id": "acct_longform",
            "target_total_chapters": 12,
            "target_total_volumes": 3,
            "target_word_count": 24000,
        }
    )
    report = authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=12,
    )
    snapshots = list((report.get("final_state_snapshot") or {}).get("volume_memory_snapshots", []))
    snapshot_volume_ids = {str(item.get("volume_id") or "") for item in snapshots if str(item.get("volume_id") or "")}
    assert report["completed_chapters"] == 12
    assert len(snapshot_volume_ids) == 3
    assert report["longform_summary"]["target_chapters"] == 12


def test_authoring_simulation_builds_series_snapshots_and_ending_checkpoint(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "series_snapshot_world.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "series_snapshot_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 series-level compression 和 ending checkpoint。",
            "life_theme": "长线推进与结局控制",
            "author_id": "acct_longform",
            "target_total_chapters": 40,
            "target_total_volumes": 4,
            "target_word_count": 80000,
        }
    )
    report = authoring.run_simulation_for_world_version(
        draft["world_version_id"],
        include_cross_pack=False,
        max_chapters=40,
    )
    final_state = dict(report.get("final_state_snapshot") or {})
    series_snapshots = list(final_state.get("series_memory_snapshots", []))
    series_ending_checkpoint = dict(final_state.get("series_ending_checkpoint", {}))

    assert len(series_snapshots) >= 2
    assert series_ending_checkpoint["terminal_ready"] is True
    assert series_ending_checkpoint["status"] == "ready"


def test_series_snapshot_prunes_archive_memory_when_policy_is_tight(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "series_archive_prune.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "series_archive_prune_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 series snapshot 会剪掉已被总结覆盖的 archive memory。",
            "life_theme": "长线压缩",
            "author_id": "acct_longform",
            "target_total_chapters": 40,
            "target_total_volumes": 4,
            "target_word_count": 80000,
        }
    )
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = dict(detail["worldpack"])
    worldpack["memory_compression_policy"] = {
        **dict(worldpack.get("memory_compression_policy") or {}),
        "series_snapshot_every_n_volumes": 1,
        "archive_retention_limit": 5,
        "series_archive_prune_margin_chapters": 0,
        "timeline_retention_limit": 40,
        "continuation_fact_retention_limit": 40,
        "continuation_visit_retention_limit": 40,
    }
    updated = authoring.save_draft(
        worldpack,
        change_context={"source": "test", "label": "tight archive prune policy"},
    )
    report = authoring.run_simulation_for_world_version(
        updated["world_version_id"],
        include_cross_pack=False,
        max_chapters=40,
    )
    final_state = dict(report.get("final_state_snapshot") or {})
    assert len(final_state.get("series_memory_snapshots", [])) >= 1
    assert len(final_state.get("archive_memory", [])) <= 5
    assert len(final_state.get("timeline", [])) <= 40
    continuation_facts = [item for item in final_state.get("world_facts", []) if str(item).startswith("continuation::")]
    continuation_event_ids = [item for item in final_state.get("visited_event_ids", []) if "__continuation__" in str(item)]
    assert len(continuation_facts) <= 40
    assert len(continuation_event_ids) <= 40


def test_benchmark_supports_longform_100_interactive_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "interactive_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str, scenarios):
        assert scenarios
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 100,
            "chapter_budget": 100,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 90,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.02,
                "promise_unresolved_rate": 0.1,
                "arc_task_repeat_rate": 0.05,
                "q09_incidence_rate": 0.01,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.04,
            },
            "longform_gate": {"passed": True},
            "interactive_summary": {
                "scenario_count": 3,
                "steering_recovery_rate": 1.0,
                "post_steer_route_survival": 0.9,
                "memory_consistency_after_steer": 0.9,
                "promise_reconciliation_after_steer": 0.85,
                "replan_stability_score": 0.9,
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_100_interactive",
        max_chapters=100,
    )

    assert report["benchmark_mode"] == "longform_100_interactive"
    assert report["interactive_longform_gate"]["pass_rate"] == 1.0
    assert report["interactive_longform_signoff"]["status"] == "watch"


def test_benchmark_supports_longform_250_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_250_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 250,
            "chapter_budget": 250,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 90,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_250_summary": {
                "target_chapters": 250,
                "target_volume_count": 5,
                "completed_volume_count": 5,
                "volume_boundary_survival": 1.0,
                "memory_recall_coverage": 0.9,
                "replan_stability_score": 0.95,
                "volume_snapshot_integrity": 1.0,
                "mid_volume_pass_rate": 1.0,
                "late_volume_pass_rate": 1.0,
            },
            "longform_250_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_250",
        max_chapters=250,
    )

    assert report["benchmark_mode"] == "longform_250"
    assert report["longform_250_summary"]["gate_pass_rate"] == 1.0
    assert "review_sample_coverage_250" in report
    assert "longform_250_signoff" in report


def test_benchmark_supports_longform_250_interactive_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_250_interactive_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str, scenarios):
        assert scenarios
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 250,
            "chapter_budget": 250,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 180,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_250_summary": {
                "target_chapters": 250,
                "target_volume_count": 5,
                "completed_volume_count": 5,
                "volume_boundary_survival": 1.0,
                "memory_recall_coverage": 0.9,
                "replan_stability_score": 0.95,
                "volume_snapshot_integrity": 1.0,
                "mid_volume_pass_rate": 1.0,
                "late_volume_pass_rate": 1.0,
            },
            "longform_250_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
            "interactive_summary": {
                "scenario_count": 3,
                "steering_recovery_rate": 1.0,
                "post_steer_route_survival": 0.9,
                "memory_consistency_after_steer": 0.9,
                "promise_reconciliation_after_steer": 0.85,
                "replan_stability_score": 0.9,
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_250_interactive",
        max_chapters=250,
        execute_review_sampling_250=True,
    )

    assert report["benchmark_mode"] == "longform_250_interactive"
    assert report["longform_250_summary"]["gate_pass_rate"] == 1.0
    assert report["longform_250_interactive_gate"]["pass_rate"] == 1.0
    assert "longform_250_interactive_signoff" in report


def test_benchmark_supports_longform_500_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_500_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 500,
            "chapter_budget": 500,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 400,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_500_summary": {
                "target_chapters": 500,
                "series_boundary_survival": 1.0,
                "series_memory_snapshot_integrity": 1.0,
                "memory_recall_coverage": 1.0,
                "replan_stability_score": 0.9,
                "late_series_pass_rate": 1.0,
                "series_ending_control_score": 1.0,
            },
            "longform_500_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_500",
        max_chapters=500,
    )

    assert report["benchmark_mode"] == "longform_500"
    assert report["longform_500_summary"]["gate_pass_rate"] == 1.0
    assert report["longform_500_signoff"]["status"] == "watch"
    assert report["longform_500_human_review_closeout"]["status"] == "watch"
    assert report["longform_500_ending_signoff"]["status"] == "watch"


def test_benchmark_supports_longform_500_interactive_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_500_interactive_benchmark.db"))

    def simulation_runner(_world_id: str, world_version_id: str, _interactive_scenarios=None):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 500,
            "chapter_budget": 500,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 400,
            "chapter_evaluations": [
                {
                    "chapter_id": f"simulation_{world_version_id}_{chapter_index}",
                    "world_version_id": world_version_id,
                    "session_id": "simulation:synthetic_min_pack",
                    "decision": {"decision": "pass", "reason": "benchmark"},
                    "issues": [],
                    "scores": {
                        "readability": 0.9,
                        "scene_density": 0.9,
                        "character_fidelity": 0.9,
                        "causal_continuity": 0.9,
                        "pacing": 0.9,
                        "choice_distinctness": 0.9,
                        "hook_quality": 0.9,
                        "monetize_ready": 0.9,
                        "overall_score": 0.9,
                    },
                    "hard_validator_results": {},
                    "summary": f"chapter {chapter_index}",
                    "created_at": "2026-04-06T00:00:00+00:00",
                }
                for chapter_index in [1, 21, 220, 260, 460, 480]
            ],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_500_summary": {
                "target_chapters": 500,
                "series_boundary_survival": 1.0,
                "series_memory_snapshot_integrity": 1.0,
                "memory_recall_coverage": 1.0,
                "replan_stability_score": 0.9,
                "late_series_pass_rate": 1.0,
                "series_ending_control_score": 1.0,
            },
            "longform_500_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
            "interactive_summary": {
                "scenario_count": 3,
                "steering_recovery_rate": 1.0,
                "post_steer_route_survival": 0.9,
                "memory_consistency_after_steer": 0.95,
                "promise_reconciliation_after_steer": 0.9,
                "replan_stability_score": 0.9,
            },
        }

    for chapter_index in [1, 21, 220, 260, 460, 480]:
        TrainingSignalService(repository).save_review_sample(
            {
                "chapter_id": f"simulation_synthetic_min_pack@0.1.0_{chapter_index}",
                "world_id": "synthetic_min_pack",
                "world_version_id": "synthetic_min_pack@0.1.0",
                "reviewer_id": "ops_human_closeout",
                "score_overall": 0.9,
                "issue_codes": [],
                "linked_issue_codes": [],
                "freeform_notes": "interactive 500 closeout",
                "would_continue": True,
                "would_pay": True,
                "source": "human_review",
                "source_ref": {"kind": "manual_entry", "chapter_id": f"simulation_synthetic_min_pack@0.1.0_{chapter_index}"},
            }
        )

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_500_interactive",
        max_chapters=500,
    )

    assert report["benchmark_mode"] == "longform_500_interactive"
    assert report["longform_500_summary"]["gate_pass_rate"] == 1.0
    assert report["longform_500_interactive_gate"]["pass_rate"] == 1.0
    assert report["longform_500_human_review_closeout"]["status"] == "watch"
    assert report["longform_500_ending_signoff"]["status"] == "watch"
    assert report["longform_500_interactive_signoff"]["status"] == "watch"


def test_benchmark_supports_longform_1000_diagnostics_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_1000_diagnostics.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 1000,
            "chapter_budget": 1000,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 800,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_1000_summary": {
                "target_chapters": 1000,
                "series_boundary_survival": 1.0,
                "series_memory_snapshot_integrity": 1.0,
                "memory_recall_coverage": 1.0,
                "replan_stability_score": 0.9,
                "archive_retention_integrity": 1.0,
                "timeline_retention_integrity": 1.0,
                "continuation_state_retention_integrity": 1.0,
                "late_stage_runtime_p95_ms": 1800.0,
                "late_stage_runtime_budget_score": 1.0,
                "series_ending_control_score": 1.0,
            },
            "longform_1000_evidence": {
                "status": "promising",
                "failed_checks": [],
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_1000_diagnostics",
        max_chapters=1000,
    )

    assert report["benchmark_mode"] == "longform_1000_diagnostics"
    assert report["longform_1000_summary"]["diagnostic_pass_rate"] == 1.0
    assert report["longform_1000_feasibility"]["status"] == "watch"
    assert report["longform_1000_readiness"]["status"] == "watch"
    assert report["longform_1000_human_review_closeout"]["status"] == "watch"


def test_benchmark_supports_longform_1000_interactive_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_1000_interactive.db"))

    def simulation_runner(_world_id: str, world_version_id: str, _interactive_scenarios=None):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 1000,
            "chapter_budget": 1000,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 800,
            "chapter_evaluations": [
                {
                    "chapter_id": f"simulation_{world_version_id}_{chapter_index}",
                    "world_version_id": world_version_id,
                    "session_id": "simulation:synthetic_min_pack",
                    "decision": {"decision": "pass", "reason": "benchmark"},
                    "issues": [
                        {
                            "issue_code": "Q03",
                            "severity": "medium",
                            "summary": "repeat",
                            "owning_module": "writer",
                            "evidence": [],
                        }
                    ] if chapter_index == 220 else [],
                    "scores": {
                        "readability": 0.9,
                        "scene_density": 0.9,
                        "character_fidelity": 0.9,
                        "causal_continuity": 0.9,
                        "pacing": 0.9,
                        "choice_distinctness": 0.9,
                        "hook_quality": 0.9,
                        "monetize_ready": 0.9,
                        "overall_score": 0.9,
                    },
                    "hard_validator_results": {},
                    "summary": f"chapter {chapter_index}",
                    "created_at": "2026-04-06T00:00:00+00:00",
                }
                for chapter_index in [1, 40, 420, 500, 920, 960]
            ],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_1000_summary": {
                "target_chapters": 1000,
                "series_boundary_survival": 1.0,
                "series_memory_snapshot_integrity": 1.0,
                "memory_recall_coverage": 1.0,
                "replan_stability_score": 0.9,
                "archive_retention_integrity": 1.0,
                "timeline_retention_integrity": 1.0,
                "continuation_state_retention_integrity": 1.0,
                "late_stage_runtime_p95_ms": 1200.0,
                "late_stage_runtime_budget_score": 1.0,
                "series_ending_control_score": 1.0,
            },
            "longform_1000_evidence": {
                "status": "promising",
                "failed_checks": [],
            },
            "interactive_summary": {
                "scenario_count": 3,
                "steering_recovery_rate": 1.0,
                "post_steer_route_survival": 0.95,
                "memory_consistency_after_steer": 0.96,
                "promise_reconciliation_after_steer": 0.94,
                "replan_stability_score": 0.91,
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_1000_interactive",
        max_chapters=1000,
    )

    assert report["benchmark_mode"] == "longform_1000_interactive"
    assert report["longform_1000_summary"]["diagnostic_pass_rate"] == 1.0
    assert report["longform_1000_interactive_gate"]["pass_rate"] == 1.0
    assert report["longform_1000_readiness"]["status"] == "watch"
    assert report["longform_1000_interactive_signoff"]["status"] == "watch"
    assert report["longform_1000_human_review_closeout"]["status"] == "watch"


def test_benchmark_can_execute_longform_250_review_sampling_closeout(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_250_review_sampling.db"))

    def chapter_report(*, chapter_id: str, overall_score: float, issue_codes: list[str], detail_density: float) -> dict[str, object]:
        return {
            "chapter_id": chapter_id,
            "world_version_id": "synthetic_min_pack@0.1.0",
            "session_id": "simulation:synthetic_min_pack",
            "decision": {"decision": "pass", "reason": "benchmark"},
            "issues": [
                {
                    "issue_code": code,
                    "severity": "medium",
                    "summary": code,
                    "owning_module": "writer",
                    "evidence": [],
                }
                for code in issue_codes
            ],
            "scores": {
                "readability": overall_score,
                "scene_density": overall_score,
                "character_fidelity": overall_score,
                "causal_continuity": overall_score,
                "pacing": overall_score,
                "choice_distinctness": overall_score,
                "hook_quality": overall_score,
                "monetize_ready": overall_score,
                "overall_score": overall_score,
            },
            "hard_validator_results": {
                "lint_metrics": {
                    "engineering_leak_rate": 0.0,
                    "dialogue_plus_action_ratio": 0.6,
                    "concrete_detail_density": detail_density,
                    "repetition_score": 0.0,
                    "exposition_ratio": 0.2,
                }
            },
            "summary": "synthetic benchmark report",
            "created_at": "2026-04-06T00:00:00Z",
        }

    def simulation_runner(_world_id: str, world_version_id: str):
        chapter_indices = [1, 10, 80, 100, 200, 225]
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 250,
            "chapter_budget": 250,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 90,
            "chapter_evaluations": [
                chapter_report(
                    chapter_id=f"simulation_{world_version_id}_{chapter_index}",
                    overall_score=0.86,
                    issue_codes=["Q05"] if chapter_index in {80, 200} else [],
                    detail_density=0.06,
                )
                for chapter_index in chapter_indices
            ],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [{"issue_code": "Q05", "count": 2}],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_250_summary": {
                "target_chapters": 250,
                "target_volume_count": 5,
                "completed_volume_count": 5,
                "volume_boundary_survival": 1.0,
                "memory_recall_coverage": 0.9,
                "replan_stability_score": 0.95,
                "volume_snapshot_integrity": 1.0,
                "mid_volume_pass_rate": 1.0,
                "late_volume_pass_rate": 1.0,
            },
            "longform_250_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_250",
        max_chapters=250,
        execute_review_sampling_250=True,
    )

    coverage = report["review_sample_coverage_250"]
    assert coverage["planned_target_count"] == 6
    assert coverage["executed_target_count"] == 6
    assert coverage["auto_seeded_target_count"] == 6
    assert coverage["closeout_ready"] is True
    assert coverage["closeout_status"] == "closed_with_auto_seed"
    assert coverage["human_closeout_ready"] is False
    assert coverage["human_closeout_status"] == "watch"
    assert len(coverage["human_unreviewed_targets"]) == 6
    assert not coverage["unreviewed_targets"]
    saved_samples = TrainingSignalService(repository).list_review_samples(world_id="synthetic_min_pack")
    assert len(saved_samples) == 6


def test_benchmark_can_execute_longform_500_review_and_human_closeout(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_500_review_sampling.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        chapter_indices = [1, 21, 220, 260, 460, 480]
        chapter_evaluations = []
        for chapter_index in chapter_indices:
            repetition_score = 0.21 if chapter_index == 220 else 0.04
            issue_codes = ["Q03"] if chapter_index == 220 else []
            chapter_evaluations.append(
                {
                    "chapter_id": f"simulation_{world_version_id}_{chapter_index}",
                    "world_version_id": world_version_id,
                    "session_id": "simulation:synthetic_min_pack",
                    "decision": {"decision": "pass", "reason": "benchmark"},
                    "issues": [
                        {
                            "issue_code": code,
                            "severity": "medium",
                            "summary": code,
                            "owning_module": "writer",
                            "evidence": [],
                        }
                        for code in issue_codes
                    ],
                    "scores": {
                        "readability": 0.9,
                        "scene_density": 0.9,
                        "character_fidelity": 0.9,
                        "causal_continuity": 0.9,
                        "pacing": 0.9,
                        "choice_distinctness": 0.9,
                        "hook_quality": 0.9,
                        "monetize_ready": 0.9,
                        "overall_score": 0.9,
                    },
                    "hard_validator_results": {
                        "lint_metrics": {
                            "engineering_leak_rate": 0.0,
                            "dialogue_plus_action_ratio": 0.55,
                            "concrete_detail_density": 0.06,
                            "repetition_score": repetition_score,
                            "exposition_ratio": 0.2,
                            "repetition_signal_bundle": {
                                "semantic_paragraph_similarity_score": 0.1,
                                "event_coverage_gap_score": 0.0,
                                "beat_coverage_gap_score": 0.0,
                                "uncovered_beat_count": 0,
                                "overcovered_beat_count": 0,
                            },
                        }
                    },
                    "summary": f"chapter {chapter_index}",
                    "created_at": "2026-04-06T00:00:00Z",
                }
            )
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 500,
            "chapter_budget": 500,
            "completion_ratio": 1.0,
            "stop_reason": "chapter_budget_reached",
            "min_end_turn_target": 400,
            "chapter_evaluations": chapter_evaluations,
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [{"issue_code": "Q03", "count": 1}],
            },
            "longform_summary": {
                "character_drift_rate": 0.01,
                "promise_unresolved_rate": 0.08,
                "arc_task_repeat_rate": 0.03,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.02,
            },
            "longform_500_summary": {
                "target_chapters": 500,
                "series_boundary_survival": 1.0,
                "series_memory_snapshot_integrity": 1.0,
                "memory_recall_coverage": 1.0,
                "replan_stability_score": 0.9,
                "late_series_pass_rate": 1.0,
                "series_ending_control_score": 1.0,
            },
            "longform_500_evidence": {
                "status": "ready",
                "failed_checks": [],
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_500",
        max_chapters=500,
        execute_review_sampling_500=True,
        execute_human_review_closeout_500=True,
        human_review_closeout_500_reviewer_id="ops_test_longform500",
    )

    coverage = report["review_sample_coverage_500"]
    assert coverage["planned_target_count"] == 6
    assert coverage["executed_target_count"] == 6
    assert coverage["auto_seeded_target_count"] == 6
    assert coverage["human_reviewed_target_count"] == 6
    assert coverage["human_closeout_ready"] is True
    assert coverage["ending_window_human_closeout_ready"] is True
    assert report["longform_500_human_review_closeout"]["reason"] == "benchmark_scope_incomplete"
    assert report["longform_500_ending_signoff"]["reason"] == "benchmark_scope_incomplete"
    assert report["worlds"][0]["surface_issue_chapters"][0]["chapter_index"] == 220
    assert report["worlds"][0]["surface_issue_chapters"][0]["issue_codes"] == ["Q03"]
    saved_samples = TrainingSignalService(repository).list_review_samples(world_id="synthetic_min_pack")
    assert len(saved_samples) == 12
    assert sum(1 for sample in saved_samples if sample["source"] == "evaluation_report_auto") == 6
    assert sum(1 for sample in saved_samples if sample["source"] == "human_review") == 6


def test_longform_250_signoff_requires_review_sampling_closeout():
    summary = {
        "benchmark_mode": "longform_250",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "weakest_pack_polish_program": {"continue_worlds": []},
        "longform_250_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
            "review_sample_closeout_ready": False,
        },
        "review_sample_coverage_250": {"closeout_ready": False},
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_250_signoff(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["review_sample_closeout_ready"] is False


def test_longform_250_interactive_signoff_requires_static_interactive_and_review_evidence():
    summary = {
        "benchmark_mode": "longform_250_interactive",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "weakest_pack_polish_program": {"continue_worlds": []},
        "longform_250_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
            "review_sample_closeout_ready": False,
        },
        "longform_250_interactive_gate": {
            "pass_rate": 1.0,
            "failed_worlds": [],
        },
        "review_sample_coverage_250": {"closeout_ready": False},
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_250_interactive_signoff(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["review_sample_closeout_ready"] is False


def test_longform_250_human_review_closeout_watches_until_human_targets_are_closed():
    summary = {
        "benchmark_mode": "longform_250",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "review_sample_coverage_250": {
            "planned_target_count": 30,
            "human_reviewed_target_count": 0,
            "human_closeout_ready": False,
            "human_closeout_status": "watch",
            "human_unreviewed_targets": [
                {"world_id": "jade_court_romance"},
                {"world_id": "jade_court_exam"},
            ],
        },
        "weakest_packs": [{"world_id": "jade_court_romance"}],
    }

    signoff = build_longform_250_human_review_closeout(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["blocking_worlds"] == ["jade_court_exam", "jade_court_romance"]


def test_longform_500_signoff_requires_fresh_longform_500_evidence():
    summary = {
        "benchmark_mode": "longform_500",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "weakest_pack_polish_program": {"continue_worlds": []},
        "longform_500_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
        },
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_500_signoff(summary)

    assert signoff["status"] == "ready"
    assert signoff["ready"] is True


def test_longform_500_human_review_closeout_watches_until_human_targets_are_closed():
    summary = {
        "benchmark_mode": "longform_500",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "review_sample_coverage_500": {
            "planned_target_count": 30,
            "human_reviewed_target_count": 0,
            "human_closeout_ready": False,
            "human_closeout_status": "watch",
            "human_unreviewed_targets": [
                {"world_id": "jade_court_romance", "window_label": "460-500"},
                {"world_id": "jade_court_exam", "window_label": "220-300"},
            ],
        },
        "weakest_packs": [{"world_id": "jade_court_romance"}],
    }

    signoff = build_longform_500_human_review_closeout(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["blocking_worlds"] == ["jade_court_exam", "jade_court_romance"]


def test_longform_500_ending_signoff_requires_ending_window_human_closeout():
    summary = {
        "benchmark_mode": "longform_500",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "longform_500_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
        },
        "review_sample_coverage_500": {
            "ending_window_label": "460-500",
            "ending_window_human_closeout_ready": False,
            "human_unreviewed_targets": [
                {"world_id": "jade_court_romance", "window_label": "460-500"},
                {"world_id": "synthetic_min_pack", "window_label": "1-40"},
            ],
        },
        "weakest_packs": [{"world_id": "jade_court_romance"}],
    }

    signoff = build_longform_500_ending_signoff(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["blocking_worlds"] == ["jade_court_romance"]


def test_longform_500_interactive_signoff_requires_static_interactive_and_human_closeout():
    summary = {
        "benchmark_mode": "longform_500_interactive",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "weakest_pack_polish_program": {"continue_worlds": []},
        "longform_500_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
        },
        "longform_500_interactive_gate": {
            "pass_rate": 1.0,
            "failed_worlds": [],
        },
        "review_sample_coverage_500": {
            "human_closeout_ready": False,
            "ending_window_human_closeout_ready": False,
        },
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_500_interactive_signoff(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["human_closeout_ready"] is False
    assert signoff["ending_window_human_closeout_ready"] is False


def test_longform_500_interactive_signoff_ready_with_all_evidence():
    summary = {
        "benchmark_mode": "longform_500_interactive",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "weakest_pack_polish_program": {"continue_worlds": []},
        "longform_500_evidence": {
            "gate_pass_rate": 1.0,
            "failed_worlds": [],
        },
        "longform_500_interactive_gate": {
            "pass_rate": 1.0,
            "failed_worlds": [],
        },
        "review_sample_coverage_500": {
            "human_closeout_ready": True,
            "ending_window_human_closeout_ready": True,
        },
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_500_interactive_signoff(summary)

    assert signoff["status"] == "ready"
    assert signoff["ready"] is True


def test_longform_1000_feasibility_promising_with_all_diagnostics():
    summary = {
        "benchmark_mode": "longform_1000_diagnostics",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "longform_1000_summary": {"diagnostic_pass_rate": 1.0},
        "longform_1000_evidence": {
            "diagnostic_pass_rate": 1.0,
            "failed_worlds": [],
        },
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_1000_feasibility(summary)

    assert signoff["status"] == "promising"
    assert signoff["ready"] is True


def test_longform_1000_readiness_ready_with_feasibility():
    summary = {
        "benchmark_mode": "longform_1000_diagnostics",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "longform_1000_summary": {"diagnostic_pass_rate": 1.0},
        "longform_1000_evidence": {"diagnostic_pass_rate": 1.0, "failed_worlds": []},
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_1000_readiness(summary)

    assert signoff["status"] == "ready"
    assert signoff["ready"] is True


def test_longform_1000_human_review_closeout_watches_until_human_targets_are_closed():
    summary = {
        "benchmark_mode": "longform_1000_diagnostics",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "review_sample_coverage_1000": {
            "planned_target_count": 6,
            "human_reviewed_target_count": 0,
            "human_closeout_ready": False,
            "human_closeout_status": "watch",
            "human_unreviewed_targets": [
                {"world_id": "jade_court_romance"},
                {"world_id": "jade_court_exam"},
            ],
        },
        "weakest_packs": [{"world_id": "jade_court_romance"}],
    }

    signoff = build_longform_1000_human_review_closeout(summary)

    assert signoff["status"] == "watch"
    assert signoff["ready"] is False
    assert signoff["blocking_worlds"] == ["jade_court_exam", "jade_court_romance"]


def test_longform_1000_interactive_signoff_requires_static_readiness_and_interactive_gate():
    summary = {
        "benchmark_mode": "longform_1000_interactive",
        "benchmark_scope_complete": True,
        "generated_at": "2026-04-06T00:00:00+00:00",
        "longform_1000_readiness": {"status": "ready", "ready": True, "blocking_worlds": [], "watch_worlds": []},
        "longform_1000_interactive_gate": {"pass_rate": 1.0, "failed_worlds": []},
        "weakest_packs": [{"world_id": "synthetic_min_pack"}],
    }

    signoff = build_longform_1000_interactive_signoff(summary)

    assert signoff["status"] == "ready"
    assert signoff["ready"] is True


def test_character_fidelity_remediation_framework_builds_from_simulation_report(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "q06_framework.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "q06_framework_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 Q06 remediation framework。",
            "life_theme": "角色一致性",
            "author_id": "acct_longform",
            "target_total_chapters": 100,
            "target_total_volumes": 5,
            "target_word_count": 200000,
        }
    )
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "chapter_trace": [
            {
                "chapter_id": f"simulation_{draft['world_version_id']}_1",
                "chapter_title": "第一章",
                "scene_function": "truth_trial",
                "actor_ids": ["lead", "counterpart"],
                "chapter_task": {"chapter_task_id": "task_1", "duty_type": "advance_plot"},
                "chapter_task_execution_summary": {"series_chapter_index": 1},
            }
        ],
        "chapter_evaluations": [
            {
                "chapter_id": f"simulation_{draft['world_version_id']}_1",
                "issues": [{"issue_code": "Q06"}],
                "scores": {"character_fidelity": 0.22},
            }
        ],
    }
    repository.save_world_version(version, publish=False)

    detail = authoring.get_draft(draft["world_version_id"])
    framework = detail["character_fidelity_remediation_framework"]

    assert framework["available"] is True
    assert framework["q06_chapter_count"] == 1
    assert framework["top_character_hotspots"][0]["character_id"] == "counterpart" or framework["top_character_hotspots"][0]["character_id"] == "lead"
    assert framework["top_duty_hotspots"][0]["duty_type"] == "advance_plot"


def test_training_signal_builds_longform_250_human_review_closeout_backlog(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_250_human_closeout.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "human_closeout_world",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 250 human review closeout backlog。",
            "life_theme": "长线验证",
            "author_id": "acct_longform",
            "target_total_chapters": 250,
            "target_total_volumes": 5,
            "target_word_count": 500000,
        }
    )
    version = repository.get_world_version(draft["world_version_id"])
    chapter_indices = [1, 11, 80, 100, 200, 225]
    version.simulation_report_json = {
        "completed_chapters": 250,
        "longform_250_summary": {"target_chapters": 250},
        "chapter_evaluations": [
            {
                "chapter_id": f"simulation_{draft['world_version_id']}_{chapter_index}",
                "world_version_id": draft["world_version_id"],
                "session_id": f"simulation:{draft['world_id']}",
                "decision": {"decision": "pass", "reason": "benchmark"},
                "issues": [],
                "scores": {
                    "readability": 0.9,
                    "scene_density": 0.9,
                    "character_fidelity": 0.9,
                    "causal_continuity": 0.9,
                    "pacing": 0.9,
                    "choice_distinctness": 0.9,
                    "hook_quality": 0.9,
                    "monetize_ready": 0.9,
                    "overall_score": 0.9,
                },
                "hard_validator_results": {},
                "summary": f"chapter {chapter_index}",
                "created_at": "2026-04-06T00:00:00+00:00",
            }
            for chapter_index in chapter_indices
        ],
    }
    repository.save_world_version(version, publish=False)
    training_signal = TrainingSignalService(repository)

    summary = training_signal.longform_250_human_review_closeout(world_id=draft["world_id"])

    assert summary["planned_target_count"] == 6
    assert summary["human_reviewed_target_count"] == 0
    assert summary["human_closeout_ready"] is False
    assert summary["human_closeout_status"] == "watch"
    assert len(summary["backlog"]) == 6


def test_training_signal_builds_longform_500_human_review_closeout_backlog(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_500_human_closeout.db"))
    authoring = AuthoringService(repository)
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "synthetic",
            "world_title": "human_closeout_world_500",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "core_premise": "验证 500 human review closeout backlog。",
            "life_theme": "长线验证",
            "author_id": "acct_longform",
            "target_total_chapters": 500,
            "target_total_volumes": 10,
            "target_word_count": 1000000,
        }
    )
    version = repository.get_world_version(draft["world_version_id"])
    chapter_indices = [1, 21, 220, 260, 460, 480]
    version.simulation_report_json = {
        "completed_chapters": 500,
        "longform_500_summary": {"target_chapters": 500},
        "chapter_evaluations": [
            {
                "chapter_id": f"simulation_{draft['world_version_id']}_{chapter_index}",
                "world_version_id": draft["world_version_id"],
                "session_id": f"simulation:{draft['world_id']}",
                "decision": {"decision": "pass", "reason": "benchmark"},
                "issues": [],
                "scores": {
                    "readability": 0.9,
                    "scene_density": 0.9,
                    "character_fidelity": 0.9,
                    "causal_continuity": 0.9,
                    "pacing": 0.9,
                    "choice_distinctness": 0.9,
                    "hook_quality": 0.9,
                    "monetize_ready": 0.9,
                    "overall_score": 0.9,
                },
                "hard_validator_results": {},
                "summary": f"chapter {chapter_index}",
                "created_at": "2026-04-06T00:00:00+00:00",
            }
            for chapter_index in chapter_indices
        ],
    }
    repository.save_world_version(version, publish=False)
    training_signal = TrainingSignalService(repository)

    summary = training_signal.longform_500_human_review_closeout(world_id=draft["world_id"])

    assert summary["planned_target_count"] == 6
    assert summary["human_reviewed_target_count"] == 0
    assert summary["human_closeout_ready"] is False
    assert summary["human_closeout_status"] == "watch"
    assert summary["ending_window_label"] == "460-500"
    assert summary["ending_window_target_count"] == 2
    assert summary["ending_window_human_reviewed_count"] == 0
    assert summary["ending_window_human_closeout_ready"] is False
    assert len(summary["backlog"]) == 6


def test_runtime_fallback_uses_more_volumes_for_500_targets():
    structure = _resolve_longform_structure(
        worldpack_payload={"world_id": "legacy_runtime_world", "title": "Legacy Runtime World", "metadata": {}},
        runtime_world_title="Legacy Runtime World",
        max_chapters=500,
    )

    assert structure["series_plan"]["total_chapter_target"] == 500
    assert structure["series_plan"]["total_volume_target"] >= 8


def test_runtime_fallback_uses_more_volumes_for_1000_targets():
    structure = _resolve_longform_structure(
        worldpack_payload={"world_id": "legacy_runtime_world", "title": "Legacy Runtime World", "metadata": {}},
        runtime_world_title="Legacy Runtime World",
        max_chapters=1000,
    )

    assert structure["series_plan"]["total_chapter_target"] == 1000
    assert structure["series_plan"]["total_volume_target"] >= 16


def test_longform_100_gate_surfaces_mid_arc_and_stop_reason_evidence(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "longform_gate_evidence.db"))

    def simulation_runner(_world_id: str, world_version_id: str):
        return {
            "world_version_id": world_version_id,
            "world_id": "synthetic_min_pack",
            "completed_chapters": 8,
            "chapter_budget": 100,
            "completion_ratio": 0.08,
            "stop_reason": "no_legal_routes",
            "min_end_turn_target": 90,
            "chapter_evaluations": [],
            "evaluation_summary": {
                "pass_rate": 1.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
            },
            "longform_summary": {
                "character_drift_rate": 0.0,
                "promise_unresolved_rate": 0.2,
                "arc_task_repeat_rate": 0.3,
                "q09_incidence_rate": 0.0,
                "premature_ending_trigger_rate": 0.0,
                "volume_climax_spacing_error": 0.0,
            },
        }

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="synthetic_min_pack",
        simulation_runner=simulation_runner,
        benchmark_mode="longform_100",
        max_chapters=100,
    )

    gate = report["worlds"][0]["longform_gate"]
    assert gate["passed"] is False
    assert "stop_reason" in gate["failed_checks"]
    assert "mid_arc_window_reached" in gate["failed_checks"]
    assert report["worlds"][0]["q09_incidence_rate"] == 0.0
