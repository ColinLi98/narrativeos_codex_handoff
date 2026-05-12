from src.narrativeos.memory import apply_event
from src.narrativeos.providers import InlineJSONLLMBackend
from src.narrativeos.rendering import LLMRenderer, TemplateRenderer
from src.narrativeos.models import ChapterPlan, SceneBeat, SceneIntent, SceneRenderSpec


def test_template_renderer_outputs_three_layers(demo_world, demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    rendered = TemplateRenderer().render(demo_world, demo_state, next_state, event)

    assert rendered.concise_summary
    assert rendered.interactive_scene
    assert rendered.premium_prose
    assert rendered.story_title
    assert rendered.chapter_summary
    assert rendered.pull_quote
    assert rendered.story_beats
    assert rendered.visual_details
    assert rendered.visual_prompt
    assert rendered.image_caption
    assert rendered.image_motif == event.scene_function
    assert len(rendered.premium_prose) > len(rendered.concise_summary)
    assert "“" in rendered.premium_prose
    assert any(name in rendered.premium_prose for name in ["余澄", "荣老太君"])
    assert any(token in rendered.premium_prose for token in ["花厅", "灯影", "衣角", "空气"])
    assert "accept_exam_nomination" not in rendered.concise_summary
    assert rendered.event_id == event.event_id


def test_llm_renderer_uses_backend_when_payload_is_valid(demo_world, demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    renderer = LLMRenderer(
        InlineJSONLLMBackend(
            {
                "concise_summary": "短摘要",
                "interactive_scene": "互动场景",
                "premium_prose": "精修 prose",
            }
        ),
        TemplateRenderer(),
    )
    rendered = renderer.render(demo_world, demo_state, next_state, event)

    assert rendered.concise_summary == "短摘要"
    assert rendered.debug["renderer"] == "llm"
    assert rendered.image_caption == "短摘要"


def test_llm_renderer_falls_back_to_template(demo_world, demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    renderer = LLMRenderer(InlineJSONLLMBackend({"bad": "payload"}), TemplateRenderer())
    rendered = renderer.render(demo_world, demo_state, next_state, event)

    assert rendered.concise_summary
    assert rendered.debug["renderer"] == "llm_fallback_template"


class SequenceLLMBackend:
    provider_id = "sequence"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []
        self.last_route_debug = {}

    def generate_json(self, *, system_prompt: str, user_prompt: str):
        self.prompts.append(user_prompt)
        self.last_route_debug = {
            "provider": self.provider_id,
            "selected_provider": self.provider_id,
            "attempt_count": len(self.prompts),
        }
        return self.payloads.pop(0)


def _render_scene_inputs(demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    beat = SceneBeat(
        beat_index=1,
        event=event,
        beat_label=event.title,
        dramatic_job=event.scene_function,
        tension_after=next_state.tension,
    )
    chapter_plan = ChapterPlan(
        chapter_index=next_state.chapter_index,
        story_phase=next_state.story_phase,
        scene_intent=SceneIntent(
            intent_id=event.scene_function,
            label=event.title,
            description=event.summary,
            preferred_scene_functions=[event.scene_function],
            preferred_tags=list(event.tags),
        ),
        beat_target=1,
        beat_count=1,
        ending_ready=False,
        selected_event_ids=[event.event_id],
    )
    render_spec = SceneRenderSpec(
        prose_mode="novel_lush",
        viewpoint_character=event.actors[0],
        target_word_count=120,
        min_target_word_count=80,
        max_target_word_count=260,
        dialogue_density=0.35,
        sensory_motifs=list(event.tags[:2]),
        emotional_pivot=event.scene_function,
        ending_cadence="lingering",
        must_include_beats=[event.title],
    )
    return event, next_state, chapter_plan, [beat], render_spec


def _scene_payload(prose: str):
    return {
        "concise_summary": "余澄接下春闱之命，厅中责任继续收紧。",
        "interactive_scene": "花厅里，荣老太君把春闱之命压到余澄面前。",
        "premium_prose": prose,
        "story_title": "第 1 章 · 花厅里的静处起波",
        "chapter_summary": "花厅里的门影把表面平静推向余澄与荣老太君。",
    }


def test_llm_renderer_retries_length_gate_before_fallback(demo_world, demo_state, demo_events):
    _, next_state, chapter_plan, scene_beats, render_spec = _render_scene_inputs(demo_state, demo_events)
    good_prose = (
        "花厅里灯影贴着青砖慢慢移开，余澄按住袖口，听见荣老太君的茶盖轻轻一响。"
        "“孙儿明白。”他说。荣老太君没有立刻答话，只把拐杖往地上一点。"
        "“明白就好。”那一声落下去，满厅的人都低了头，他却觉得门外的风更冷，"
        "像把还没说出口的话推回胸口，也把春闱之后的代价推到眼前。"
    )
    backend = SequenceLLMBackend([
        _scene_payload("太短。"),
        _scene_payload(good_prose),
    ])
    renderer = LLMRenderer(backend, TemplateRenderer())

    rendered = renderer.render_scene(demo_world, demo_state, next_state, chapter_plan, scene_beats, render_spec)

    assert rendered.debug["renderer"] == "llm"
    assert rendered.debug["renderer_attempt_count"] == 2
    assert rendered.debug["llm_payload_gate"]["length_gate"]["ok"] is True
    assert len(backend.prompts) == 2
    assert "previous premium_prose failed the length gate" in backend.prompts[1]


def test_llm_renderer_falls_back_on_malformed_scene_json(demo_world, demo_state, demo_events):
    _, next_state, chapter_plan, scene_beats, render_spec = _render_scene_inputs(demo_state, demo_events)
    renderer = LLMRenderer(InlineJSONLLMBackend("{bad json"), TemplateRenderer())

    rendered = renderer.render_scene(demo_world, demo_state, next_state, chapter_plan, scene_beats, render_spec)

    assert rendered.debug["renderer"] == "llm_fallback_template"
    assert rendered.debug["renderer_fallback_reason"] == "llm_backend_error"


def test_llm_renderer_falls_back_on_event_actor_boundary_violation(demo_world, demo_state, demo_events):
    _, next_state, chapter_plan, scene_beats, render_spec = _render_scene_inputs(demo_state, demo_events)
    bad_prose = (
        "花厅里灯影压着青砖，余澄听见荣老太君的拐杖轻轻一点。“孙儿明白。”"
        "林绾却从侧门后退了一步，像把没有轮到她承受的秘密也带进了这场话。"
        "荣老太君看着余澄，茶盏沿着案角停住，门外的风把春闱两个字吹得更重。"
    )
    renderer = LLMRenderer(InlineJSONLLMBackend(_scene_payload(bad_prose)), TemplateRenderer())

    rendered = renderer.render_scene(demo_world, demo_state, next_state, chapter_plan, scene_beats, render_spec)

    assert rendered.debug["renderer"] == "llm_fallback_template"
    assert rendered.debug["renderer_fallback_reason"] == "llm_grounding_gate_failed"
    issues = rendered.debug["llm_payload_gate"]["grounding_issues"]
    assert any(issue["issue"] == "event_actor_boundary_violation" for issue in issues)
