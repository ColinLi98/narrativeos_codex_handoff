from pathlib import Path

from src.narrativeos.core.quality_pass import repair_chapter_draft
from src.narrativeos.core.linter import lint_chapter_draft
from src.narrativeos.core.writer import build_scene_plan, write_chapter_draft
from src.narrativeos.models import ChapterDraft, NarrativeState
from src.narrativeos.pipeline import plan_next_turn_from_events
from src.narrativeos.services.intent_prefill import IntentPrefillService


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
    assert any(token in draft.body for token in ["下一次", "追上来", "还没有散"])
    assert draft.dialogue_count >= 1
    assert draft.detail_count >= 2


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
