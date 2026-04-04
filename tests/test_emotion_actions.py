from src.narrativeos.core.emotion_actions import compose_emotion_action
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_emotion_actions_differ_across_packs():
    registry = FileSystemWorldRegistry()
    jade = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    urban = registry.get_runtime_bundle("urban_mystery_lotus_lane@0.1.0")
    jade_beat = type("Beat", (), {"event": jade.event_atoms[0], "dramatic_job": "entry"})()
    urban_beat = type("Beat", (), {"event": urban.event_atoms[0], "dramatic_job": "entry"})()
    jade_text = compose_emotion_action(jade.world_record.world, jade_beat, repeated=False)
    urban_text = compose_emotion_action(urban.world_record.world, urban_beat, repeated=False)
    assert jade_text != urban_text
