from src.narrativeos.core.emotion_actions import compose_emotion_action
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_emotion_actions_differ_across_packs():
    registry = FileSystemWorldRegistry()
    jade = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    urban = registry.get_runtime_bundle("urban_mystery_lotus_lane@0.1.0")
    jade_beat = type("Beat", (), {"event": jade.event_atoms[0], "dramatic_job": "entry"})()
    urban_beat = type("Beat", (), {"event": urban.event_atoms[0], "dramatic_job": "entry"})()
    jade_text = compose_emotion_action(jade.world_record.world, jade.initial_state, jade_beat, repeated=False)
    urban_text = compose_emotion_action(urban.world_record.world, urban.initial_state, urban_beat, repeated=False)
    assert jade_text != urban_text


def test_synthetic_emotion_actions_rotate_by_chapter_index():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    beat = type("Beat", (), {"event": runtime.event_atoms[0], "dramatic_job": "pressure", "beat_index": 2})()
    early_state = runtime.initial_state
    late_state = type(early_state).from_dict({**early_state.to_dict(), "chapter_index": 43})

    early = compose_emotion_action(runtime.world_record.world, early_state, beat, repeated=True)
    late = compose_emotion_action(runtime.world_record.world, late_state, beat, repeated=True)

    assert early != late
