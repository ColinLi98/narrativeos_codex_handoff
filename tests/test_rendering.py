from src.narrativeos.memory import apply_event
from src.narrativeos.providers import InlineJSONLLMBackend
from src.narrativeos.rendering import LLMRenderer, TemplateRenderer


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
