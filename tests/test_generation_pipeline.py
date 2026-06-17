from pathlib import Path
from copy import deepcopy

from src.narrativeos.core.quality_pass import repair_chapter_draft
from src.narrativeos.core.linter import lint_chapter_draft, story_text_unit_count
from src.narrativeos.core.scene_realizer import realize_beat
from src.narrativeos.content_quality_contracts import diagnostic_issue_codes_for_chapter_payload
from src.narrativeos.eval.validators import run_hard_validators
from src.narrativeos.repetition_detector import repetition_signal_bundle
from src.narrativeos.core.writer import build_scene_plan, write_chapter_draft
from src.narrativeos.models import ChapterDraft, EventAtom, NarrativeState, SceneBeat, SceneRenderSpec
from src.narrativeos.pipeline import plan_next_turn_from_events
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.sessions import ReaderContinueCommand, SessionService
from src.narrativeos.services.intent_prefill import IntentPrefillService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_generation_pipeline_docs_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "architecture" / "current_generation_pipeline.md").exists()
    assert (root / "docs" / "legal" / "provenance_policy.md").exists()


def test_writer_and_linter_remove_meta_noise(demo_world, demo_state, demo_events):
    debug_result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    from src.narrativeos.models import SceneBeat, SceneRenderSpec

    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook=debug_result["chosen_event"]["summary"],
    )
    draft = write_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        render_spec=render_spec,
    )
    report = lint_chapter_draft(draft.body + "\n\n第1拍 concealed_truth a -> b 这一章")
    assert report["engineering_leak_rate"] == 0.0
    assert "第1拍" not in report["cleaned_text"]
    assert "concealed_truth" not in report["cleaned_text"]
    assert "->" not in report["cleaned_text"]


def test_linter_and_hard_validators_surface_disallowed_latin_tokens(demo_state):
    text = "她把 temptation 压回喉间，仍旧不肯开口。AI 与 API 只是缩写，不该算成违规正文。"
    report = lint_chapter_draft(text)
    assert any(item["token"] == "temptation" and item["allowed"] is False for item in report["latin_token_hits"])
    assert any(item["token"] == "AI" and item["allowed"] is True for item in report["latin_token_hits"])
    assert any(item["token"] == "API" and item["allowed"] is True for item in report["latin_token_hits"])

    hard = run_hard_validators(
        text=text,
        paragraphs=report["paragraphs"],
        dialogue_count=int(report["dialogue_count"]),
        action_count=int(report["action_count"]),
        detail_count=int(report["detail_count"]),
        state_after=demo_state,
        ending_ready=False,
    )
    assert any(item["token"] == "temptation" for item in hard["disallowed_latin_token_hits"])


def test_reader_body_is_clean_and_novelish(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world)
    body = result["reader_view"]["body"]
    assert "第1拍" not in body
    assert "这一章" not in body
    assert "这一幕" not in body
    assert "concealed_truth" not in body
    assert "->" not in body
    assert "“" in body
    assert body.count("“") >= 2
    assert 1800 <= story_text_unit_count(body) <= 2200


def test_render_spec_uses_state_word_budget_for_longform_chapters(demo_world, demo_state, demo_events):
    demo_state.word_budget = 2000
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    render_spec = result["scene_render_spec"]
    assert render_spec["target_word_count"] == 2000
    assert render_spec["min_target_word_count"] == 1800
    assert render_spec["max_target_word_count"] == 2200


def test_scene_realizer_compacts_redundant_continuation_anchor():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("tide_archive_memory_debt@0.1.0")
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.chapter_index = 76
    event = EventAtom.from_dict(
        {
            "event_id": "evt_compact_anchor",
            "title": "false_peace · 临港档案库 · 1",
            "summary": "潮汐档案 中，临港档案库 · 1 让人物进一步卷入 false_peace。",
            "actors": ["lead", "counterpart"],
            "scene_function": "false_peace",
            "tags": ["memory_debt", "truth"],
            "preconditions_all": [],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.1,
            "theme_impacts": {},
            "agency_affordances": [],
            "rating_ceiling": "PG13",
            "temptation_vector": {},
            "vow_tests": [],
            "wound_triggers": [],
            "debt_deltas": [],
            "karmic_seed_creations": [],
            "karmic_seed_resolutions": [],
            "awakening_affordances": [],
            "concealment_level": 0.0,
            "consequence_delay_hint": 1,
            "location": "临港档案库",
        }
    )
    beat = SceneBeat(
        beat_index=1,
        event=event,
        beat_label="起势：临港档案库 · 1",
        dramatic_job="entry",
        tension_after=0.3,
    )

    text = realize_beat(runtime.world_record.world, state, beat, repeated=False)

    assert "· 1这一拍" not in text
    assert "让人物进一步卷入" not in text
    assert text.count("临港档案库 · 1") == 0


def test_quality_pass_adds_repair_actions_and_stronger_hook(demo_world, demo_state, demo_events):
    debug_result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    from src.narrativeos.models import SceneBeat, SceneRenderSpec

    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="这件事就这样结束了",
    )
    weak_draft = ChapterDraft(
        body="他把事情想了一遍。\\n\\n他把事情想了一遍。",
        paragraphs=["他把事情想了一遍。", "他把事情想了一遍。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={},
    )
    draft = repair_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
    )
    assert draft.metadata["quality_pass_applied"] is True
    assert draft.metadata["quality_pass_actions"]
    assert any(token in draft.body for token in ["下一次", "追上来", "还没有散", "绕不过", "真要走到这里", "后半句"])
    assert draft.dialogue_count >= 1
    assert draft.detail_count >= 2


def test_quality_pass_can_raise_dialogue_action_balance(demo_world, demo_state, demo_events):
    from src.narrativeos.models import SceneBeat, SceneRenderSpec

    debug_result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句。",
    )
    weak_draft = ChapterDraft(
        body="灯影压下来。风从门边过去。纸页轻轻一晃。",
        paragraphs=["灯影压下来。", "风从门边过去。", "纸页轻轻一晃。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={},
    )
    draft = repair_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
    )
    lint = lint_chapter_draft(draft.body)
    assert "q05_dialogue_action_balance" in draft.metadata["quality_pass_actions"]
    assert float(lint["dialogue_plus_action_ratio"]) >= 0.42


def test_quality_pass_expands_draft_to_longform_length_gate(demo_world, demo_state, demo_events):
    debug_result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句。",
    )
    weak_draft = ChapterDraft(
        body="灯影压下来。风从门边过去。纸页轻轻一晃。",
        paragraphs=["灯影压下来。", "风从门边过去。", "纸页轻轻一晃。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={"target_word_count": 2000, "min_target_word_count": 1800, "max_target_word_count": 2200},
    )
    draft = repair_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
    )
    assert 1800 <= story_text_unit_count(draft.body) <= 2200
    assert any(action.startswith("length_gate_expand") for action in draft.metadata["quality_pass_actions"])


def test_quality_pass_longform_expansion_avoids_structural_refrains(demo_world, demo_state, demo_events):
    scene_beats = [
        SceneBeat(beat_index=1, event=demo_events[0], beat_label=demo_events[0].title, dramatic_job="entry", tension_after=demo_state.tension),
        SceneBeat(beat_index=2, event=demo_events[1], beat_label=demo_events[1].title, dramatic_job="pressure", tension_after=demo_state.tension),
        SceneBeat(beat_index=3, event=demo_events[2], beat_label=demo_events[2].title, dramatic_job="pivot", tension_after=demo_state.tension),
    ]
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label="测试长线扩写",
        scene_goal="验证扩写不回到同一句式。",
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句。",
    )
    weak_draft = ChapterDraft(
        body="灯影压下来。风从门边过去。纸页轻轻一晃。",
        paragraphs=["灯影压下来。", "风从门边过去。", "纸页轻轻一晃。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={"target_word_count": 2000, "min_target_word_count": 1800, "max_target_word_count": 2200},
    )

    draft = repair_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
    )
    bundle = repetition_signal_bundle(draft.paragraphs)

    assert story_text_unit_count(draft.body) >= 1800
    assert any(
        action.startswith("q03_post_length_paragraph_replace")
        or action.startswith("q03_bundle_target_replace")
        for action in draft.metadata["quality_pass_actions"]
    )


def test_quality_pass_final_detail_repair_clears_longform_q05_contract():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.chapter_index = 46
    state.turn_index = 46
    state.word_budget = 2000
    debug_result = plan_next_turn_from_events(state, runtime.event_atoms, world=runtime.world_record.world, debug=True)
    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=runtime.world_record.world,
        state_before=state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句。",
    )
    weak_draft = ChapterDraft(
        body="\n\n".join(["他把前因后果想得很清楚，却没有真正看见场面。"] * 10),
        paragraphs=["他把前因后果想得很清楚，却没有真正看见场面。"] * 10,
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={"target_word_count": 2000, "min_target_word_count": 1800, "max_target_word_count": 2200},
    )

    draft = repair_chapter_draft(
        world=runtime.world_record.world,
        state_before=state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
        render_spec=render_spec,
    )
    lint = lint_chapter_draft(draft.body)
    payload = {
        "chapter_id": "simulation_synthetic_min_pack@0.1.0_46",
        "issues": [],
        "hard_validator_results": {"lint_metrics": lint},
        "scores": {"hook_quality": 0.9},
    }

    assert float(lint["concrete_detail_density"]) >= 0.065
    assert "Q05" not in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=100)


def test_quality_pass_final_sweep_clears_longform_q03_q04_contract():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.chapter_index = 280
    state.turn_index = 280
    state.word_budget = 2000
    debug_result = plan_next_turn_from_events(state, runtime.event_atoms, world=runtime.world_record.world, debug=True)
    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=runtime.world_record.world,
        state_before=state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句。",
    )
    repeated_exposition = "他把所有因果、关系、压力和后果都想得很清楚，却仍然只是在心里反复说明，没有真正让场面发生变化。"
    weak_draft = ChapterDraft(
        body="\n\n".join([repeated_exposition] * 12),
        paragraphs=[repeated_exposition] * 12,
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={"target_word_count": 2000, "min_target_word_count": 1800, "max_target_word_count": 2200},
    )

    draft = repair_chapter_draft(
        world=runtime.world_record.world,
        state_before=state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
        render_spec=render_spec,
    )
    lint = lint_chapter_draft(draft.body)
    payload = {
        "chapter_id": "simulation_synthetic_min_pack@0.1.0_280",
        "issues": [],
        "hard_validator_results": {"lint_metrics": lint},
        "scores": {"hook_quality": 0.9},
    }

    assert story_text_unit_count(draft.body) >= 1800
    assert "Q03" not in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=500)
    assert "Q04" not in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=500)


def test_quality_pass_replaces_reader_q03_refrains_with_chapter_aware_jade_variation():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_romance@1.0.0")
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.chapter_index = 460
    state.turn_index = 460
    state.word_budget = 2000
    debug_result = plan_next_turn_from_events(state, runtime.event_atoms, world=runtime.world_record.world, debug=True)
    scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
    render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
    scene_plan = build_scene_plan(
        world=runtime.world_record.world,
        state_before=state,
        chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
        scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
        scene_beats=scene_beats,
        ending_hook="这句余波会追到下一次开口之前。",
    )
    repeated = "真正先逼近的不是答案，而是门第、真心和说不出口的后果；这一步只让它再也没法被带过去。"
    weak_draft = ChapterDraft(
        body="\n\n".join([repeated] * 12),
        paragraphs=[repeated] * 12,
        dialogue_count=0,
        action_count=0,
        detail_count=0,
        metadata={"target_word_count": 2000, "min_target_word_count": 1800, "max_target_word_count": 2200},
    )

    draft = repair_chapter_draft(
        world=runtime.world_record.world,
        state_before=state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=weak_draft,
        render_spec=render_spec,
    )
    lint = lint_chapter_draft(draft.body)
    payload = {
        "chapter_id": "simulation_jade_court_romance@1.0.0_460",
        "issues": [],
        "hard_validator_results": {"lint_metrics": lint},
        "scores": {"hook_quality": 0.9},
    }

    assert story_text_unit_count(draft.body) >= 1800
    assert draft.body.count("真正先逼近的不是答案") <= 2
    assert float(lint["concrete_detail_density"]) >= 0.04
    assert "Q03" not in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=500)
    assert "Q04" not in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=500)


def test_longform_jade_generated_drafts_reach_stop_ready_dialogue_ratio():
    registry = FileSystemWorldRegistry()
    for world_version_id in ["jade_court_exam@1.0.0", "jade_court_romance@1.0.0"]:
        runtime = registry.get_runtime_bundle(world_version_id)
        ratios = []
        samples = []
        for chapter_index in [220, 460]:
            state = NarrativeState.from_dict(runtime.initial_state.to_dict())
            state.chapter_index = chapter_index
            state.turn_index = chapter_index
            state.word_budget = 2000
            debug_result = plan_next_turn_from_events(state, runtime.event_atoms, world=runtime.world_record.world, debug=True)
            scene_beats = [SceneBeat.from_dict(item) for item in debug_result["scene_beats"]]
            render_spec = SceneRenderSpec.from_dict(debug_result["scene_render_spec"])
            scene_plan = build_scene_plan(
                world=runtime.world_record.world,
                state_before=state,
                chapter_label=debug_result["chapter_plan"]["scene_intent"]["label"],
                scene_goal=debug_result["chapter_plan"]["scene_intent"]["description"],
                scene_beats=scene_beats,
                ending_hook=debug_result["chosen_event"]["summary"],
            )
            draft = write_chapter_draft(
                world=runtime.world_record.world,
                state_before=state,
                scene_plan=scene_plan,
                scene_beats=scene_beats,
                render_spec=render_spec,
            )
            lint = lint_chapter_draft(draft.body)
            ratios.append(float(lint["dialogue_plus_action_ratio"]))
            samples.extend(sentence for sentence in draft.body.split("。") if "“" in sentence)
            assert story_text_unit_count(draft.body) >= 1840
            assert float(lint["dialogue_plus_action_ratio"]) >= 0.56
            assert float(lint["concrete_detail_density"]) >= 0.04
            assert "这一章" not in draft.body
            assert "slot" not in draft.body

        assert min(ratios) >= 0.56
        assert len(set(samples)) >= 4


def test_repetition_signal_bundle_surfaces_structural_refrains():
    paragraphs = [
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "他抬眼看她，知道这一步不是把真相说出来就算完，而是要连代价一起接住。",
    ]
    bundle = repetition_signal_bundle(paragraphs)
    assert bundle["paragraph_similarity_score"] > 0.8
    assert bundle["n_gram_repetition_score"] > 0.1
    assert bundle["suspicious_refrain_count"] >= 1


def test_repetition_signal_bundle_surfaces_semantic_similarity_and_coverage_gap():
    paragraphs = [
        "她把录音带翻到背面，指腹慢慢擦过已经泡开的纸签，像在确认那道旧伤是不是还留在这里。",
        "她把录音带翻到背面，指腹慢慢擦过已经泡开的纸签，像在确认那道旧伤是不是还留在这里。",
        "他没有立即接话，只把潮湿的纸袋压在案边，像是先让真正该出现的那一句话自己浮上来。",
    ]
    bundle = repetition_signal_bundle(
        paragraphs,
        coverage_context={
            "selected_event_ids": ["evt_1", "evt_2"],
            "scene_beats": [
                {
                    "beat_label": "翻出旧物",
                    "dramatic_job": "entry",
                    "event": {"event_id": "evt_1", "title": "翻出旧录音带", "summary": "她从纸袋里翻出旧录音带。", "scene_function": "truth_trial", "location": "档案仓", "tags": ["truth", "memory"]},
                },
                {
                    "beat_label": "追问来源",
                    "dramatic_job": "pressure",
                    "event": {"event_id": "evt_2", "title": "追问录音带来源", "summary": "他逼问这卷带子为什么会回到这里。", "scene_function": "temptation", "location": "档案仓", "tags": ["truth", "pressure"]},
                },
            ],
        },
    )
    assert bundle["semantic_paragraph_similarity_score"] > 0.7
    assert bundle["event_coverage_gap_score"] >= 0.0
    assert bundle["beat_coverage_gap_score"] >= 0.0
    assert "semantic_paragraph_similarity_pairs" in bundle


def test_repetition_coverage_ignores_generic_synthetic_summary_language():
    paragraphs = [
        "中庭里的脚步和回声把入场压实，谁都没法再绕开。甲抬手按住案角，乙没有替他收场。",
        "长廊里的窗纸、杯沿和门框一起把试探推到明处，甲低声道：“这一步我认。”",
        "表面平静没有真的安静下去，下一次开口前，那句还没说透的话还会追上来。",
    ]
    bundle = repetition_signal_bundle(
        paragraphs,
        coverage_context={
            "selected_event_ids": ["synthetic_min_pack__synthetic_setup__0"],
            "scene_beats": [
                {
                    "beat_label": "起势：synthetic_setup · 入场",
                    "dramatic_job": "entry",
                    "event": {
                        "event_id": "synthetic_min_pack__synthetic_setup__0",
                        "title": "synthetic_setup · 入场",
                        "summary": "Synthetic Minimal Pack 中，入场 让人物进一步卷入 setup。",
                        "scene_function": "false_peace",
                        "location": "中庭",
                        "tags": ["synthetic", "benchmark"],
                    },
                }
            ],
        },
    )

    assert bundle["event_coverage_gap_score"] < 0.42
    assert bundle["beat_coverage_gap_score"] < 0.35
    assert bundle["uncovered_beat_count"] == 0


def test_repetition_coverage_ignores_generic_projection_turn_anchor():
    paragraphs = [
        "临港档案库里的防潮盒被闻汐按在灯下，空白页边缘的水痕还没干，顾沉舟低声道：“这不是普通手续错误。”",
        "何默把旧熟人的价码推到桌边：“我能补齐事故断层，但你要承认真正会伤人的那一段还在。” 闻汐没有退。",
        "见旧熟人被临港档案库里的脚步和冷光压实，代价、退路和态度都落到两人面前。",
    ]
    bundle = repetition_signal_bundle(
        paragraphs,
        coverage_context={
            "selected_event_ids": [
                "tide_archive_memory_debt__archive_anomaly__0",
                "tide_archive_memory_debt__black_market_offer__0",
                "tide_archive_memory_debt__black_market_offer__0__beat_projection__3_pivot",
            ],
            "scene_beats": [
                {
                    "beat_label": "起势：archive_anomaly · 闻汐从防潮盒里抽出被替换过的空白页",
                    "dramatic_job": "entry",
                    "event": {
                        "event_id": "tide_archive_memory_debt__archive_anomaly__0",
                        "title": "archive_anomaly · 闻汐从防潮盒里抽出被替换过的空白页",
                        "summary": "潮汐档案 中，闻汐从防潮盒里抽出被替换过的空白页 让人物进一步卷入 false_peace。",
                        "scene_function": "false_peace",
                        "location": "临港档案库",
                        "tags": ["闻汐和顾沉舟在档案库第一次正面对上那段缺失的原始记忆，谁都意识到这不是普通手续错误。"],
                    },
                },
                {
                    "beat_label": "逼近：black_market_offer · 见旧熟人",
                    "dramatic_job": "pressure",
                    "event": {
                        "event_id": "tide_archive_memory_debt__black_market_offer__0",
                        "title": "black_market_offer · 见旧熟人",
                        "summary": "潮汐档案 中，见旧熟人 让人物进一步卷入 temptation。",
                        "scene_function": "temptation",
                        "location": "临港档案库",
                        "tags": ["何默提出能替闻汐暂时补齐事故断层，但代价是把真正会伤人的一段永远挪走。"],
                    },
                },
                {
                    "beat_label": "转向：black_market_offer · 见旧熟人 · 真正要转向的那句终于逼到眼前",
                    "dramatic_job": "pivot",
                    "event": {
                        "event_id": "tide_archive_memory_debt__black_market_offer__0__beat_projection__3_pivot",
                        "title": "black_market_offer · 见旧熟人 · 真正要转向的那句终于逼到眼前",
                        "summary": "真正要转向的那句终于逼到眼前继续压在临港档案库里，刚才没说透的态度、代价和退路都被逼到明处。",
                        "scene_function": "temptation",
                        "location": "临港档案库",
                        "tags": ["何默提出能替闻汐暂时补齐事故断层，但代价是把真正会伤人的一段永远挪走。"],
                    },
                },
            ],
        },
    )

    assert bundle["event_coverage_gap_score"] < 0.5
    assert bundle["uncovered_beat_count"] == 0


def test_repetition_coverage_uses_salient_terms_for_long_chinese_continuation_anchor():
    paragraphs = [
        "花厅里的脚步和回声把荣老太君那句追问压实，余澄没有退，只把手按在纸页边缘。",
        "徐师没有替他把话说圆，书房外落下一串细响，余澄低声道：“我听见了，也会照着做。”",
        "林绾在回廊里看住他：“别再拿更轻的话压回去。” 余澄把窗纸边的冷光接住，没有再绕开。",
    ]
    bundle = repetition_signal_bundle(
        paragraphs,
        coverage_context={
            "selected_event_ids": [
                "accept_exam_nomination__continuation__404_1_confession_window",
            ],
            "scene_beats": [
                {
                    "beat_label": "转向：徐师在书房里把那句不能再装糊涂的话留给余澄自己来认",
                    "dramatic_job": "pivot",
                    "event": {
                        "event_id": "accept_exam_nomination__continuation__404_1_confession_window",
                        "title": "徐师在书房里把那句不能再装糊涂的话留给余澄自己来认",
                        "summary": "花厅散后，余澄走进书房，徐师没有安慰，只把那句最难听的话放在他面前。",
                        "scene_function": "confession_window",
                        "location": "书房",
                        "tags": ["truth", "selfhood"],
                    },
                },
            ],
        },
    )

    assert bundle["event_coverage_gap_score"] < 0.42
    assert bundle["beat_coverage_gap_score"] < 0.35
    assert bundle["uncovered_event_count"] == 0
    assert bundle["uncovered_beat_count"] == 0


def test_jade_court_exam_first_reader_chapter_persists_after_quality_pass():
    repository = SQLAlchemyRepository(database_url="sqlite://")
    service = SessionService(repository)
    session = service.create_session("jade_court_exam", reader_id="reader_quality_probe")

    result = service.continue_story(
        ReaderContinueCommand(
            session_id=session["session_id"],
            freeform_intent="我先顺着家里来，但我也想给自己留后路。",
        ),
        reader_id="reader_quality_probe",
    )

    assert result["status"] == "ok"
    assert result.get("code") is None
    assert result["reader_view"]["chapter_title"]
    assert story_text_unit_count(result["reader_view"]["body"]) >= 900


def test_writer_varies_consecutive_same_scene_function_beats(demo_world, demo_state, demo_events):
    first = demo_events[0]
    second_payload = deepcopy(first.to_dict())
    second_payload["event_id"] = f"{first.event_id}__variant"
    second = EventAtom.from_dict(second_payload)
    scene_beats = [
        SceneBeat(beat_index=1, event=first, beat_label=first.title, dramatic_job="entry", tension_after=demo_state.tension),
        SceneBeat(beat_index=2, event=second, beat_label=second.title, dramatic_job="pressure", tension_after=demo_state.tension),
    ]
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label="测试重复场景变体",
        scene_goal="验证同类 beat 也能保持变体。",
        scene_beats=scene_beats,
        ending_hook="还有话没说完",
    )
    draft = write_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        render_spec=SceneRenderSpec(
            prose_mode="novel_lush",
            viewpoint_character="",
            target_word_count=900,
            dialogue_density=0.35,
            sensory_motifs=[],
            emotional_pivot="test",
            ending_cadence="lingering",
            must_include_beats=[],
        ),
    )
    assert len(draft.paragraphs) >= 3
    assert draft.paragraphs[1] != draft.paragraphs[2]


def test_writer_anchors_event_titles_into_body(demo_world, demo_state, demo_events):
    first = demo_events[0]
    second_payload = deepcopy(first.to_dict())
    second_payload["event_id"] = f"{first.event_id}__anchor"
    second_payload["title"] = "录音带再次翻出来"
    second = EventAtom.from_dict(second_payload)
    scene_beats = [
        SceneBeat(beat_index=1, event=first, beat_label=first.title, dramatic_job="entry", tension_after=demo_state.tension),
        SceneBeat(beat_index=2, event=second, beat_label=second.title, dramatic_job="pressure", tension_after=demo_state.tension),
    ]
    scene_plan = build_scene_plan(
        world=demo_world,
        state_before=demo_state,
        chapter_label="测试事件锚点",
        scene_goal="验证正文会把选中的事件落回段落里。",
        scene_beats=scene_beats,
        ending_hook="后面还有更难的一句",
    )
    draft = write_chapter_draft(
        world=demo_world,
        state_before=demo_state,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        render_spec=SceneRenderSpec(
            prose_mode="novel_lush",
            viewpoint_character="",
            target_word_count=900,
            dialogue_density=0.35,
            sensory_motifs=[],
            emotional_pivot="test",
            ending_cadence="lingering",
            must_include_beats=[],
        ),
    )
    assert "录音带再次翻出来" in draft.body


def test_longform_followup_beats_use_projection_events_for_unique_coverage(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    scene_beats = result["scene_beats"]
    assert len(scene_beats) >= 3
    assert scene_beats[-1]["event"]["metadata"].get("beat_projection") is True
    selected_event_ids = result["chapter_plan"]["selected_event_ids"]
    assert len(selected_event_ids) == len(set(selected_event_ids))


def test_aftermath_longform_keeps_two_real_events_when_promises_are_overdue():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("urban_mystery_lotus_lane@0.1.0")
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.story_phase = "aftermath"
    state.chapter_index = 20
    state.turn_index = 20
    state.min_end_turn = 12
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.current_chapter_task = {
        "duty_type": "pace_breath",
        "promise_actions": ["maintain_continuity"],
    }
    state.open_promises = [
        item
        for item in NarrativeState.from_dict(
            {
                **state.to_dict(),
                "open_promises": [
                    {
                        "promise_id": "alley_meet__promise",
                        "description": "旧巷那一夜迟早要被真正说清。",
                        "opened_at_turn": 1,
                        "due_by_turn": 3,
                        "holders": ["jiang_yi", "zhou_lan"],
                        "fulfillment_modes": ["truth"],
                        "status": "open",
                        "stakes": "trust",
                        "tags": ["false_peace"],
                    },
                    {
                        "promise_id": "truth_request__promise",
                        "description": "追问不能一直停在半句真话上。",
                        "opened_at_turn": 2,
                        "due_by_turn": 4,
                        "holders": ["jiang_yi", "zhou_lan"],
                        "fulfillment_modes": ["truth"],
                        "status": "open",
                        "stakes": "trust",
                        "tags": ["truth_trial"],
                    },
                    {
                        "promise_id": "rooftop_confession__promise",
                        "description": "天台那次真话不能一直停在风口。",
                        "opened_at_turn": 5,
                        "due_by_turn": 7,
                        "holders": ["jiang_yi", "zhou_lan"],
                        "fulfillment_modes": ["truth"],
                        "status": "open",
                        "stakes": "trust",
                        "tags": ["confession_window"],
                    },
                ],
            }
        ).open_promises
    ]
    result = plan_next_turn_from_events(state, runtime.event_atoms, world=runtime.world_record.world, debug=True)
    per_beat = result["planner_trace_summary"]["per_beat"]
    assert len(per_beat) >= 2
    assert per_beat[1]["selected_event_id"] != per_beat[0]["selected_event_id"]


def test_intent_prefill_service_returns_contract(demo_world, demo_state, demo_events):
    from src.narrativeos.models import SessionRecord

    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=True)
    state_after = NarrativeState.from_dict(result["updated_state"])
    latest_step = {
        "session_id": "session_test",
        "step_index": 1,
        "player_input": "我想先顺着家里应下来，但也给自己留后路。",
        "intent_vector": dict(demo_state.player_intent),
        "candidate_batch": result["candidate_batch"],
        "scored_candidates": result["scored_candidates"],
        "routes": result["routes"],
        "chosen_event": result["chosen_event"],
        "chapter_plan": result["chapter_plan"],
        "scene_beats": result["scene_beats"],
        "scene_render_spec": result["scene_render_spec"],
        "rendered_scene": result["rendered_scene"],
        "reader_view": result["reader_view"],
        "state_before": demo_state.to_dict(),
        "state_after": state_after.to_dict(),
        "critic_trace": result["critic_trace"],
        "promise_ledger_snapshot": [promise.to_dict() for promise in state_after.open_promises],
    }
    session_record = SessionRecord(
        session_id="session_test",
        world_id=demo_world.world_id,
        player_profile={},
        initial_state=demo_state,
        current_state=state_after,
        metadata={"world_version_id": "jade_court_exam@1.0.0"},
    )
    from src.narrativeos.models import StepRecord

    prefill = IntentPrefillService().build(session_record, StepRecord.from_dict(latest_step))
    payload = prefill.to_dict()
    assert payload["last_player_intent"]
    assert payload["current_pressure"]
    assert payload["suggested_prefill"]


def test_plan_next_turn_emits_planner_trace_summary(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, debug=False)
    planner_trace = result["planner_trace_summary"]
    assert "adapted_beat_target" in planner_trace
    assert "adapted_min_candidates" in planner_trace
    assert "adapted_max_candidates" in planner_trace
    assert "per_beat" in planner_trace
    assert "max_total_evaluate_latency_ms" in planner_trace
    if planner_trace["per_beat"]:
        assert "evaluate_candidates_timing_ms" in planner_trace["per_beat"][0]
