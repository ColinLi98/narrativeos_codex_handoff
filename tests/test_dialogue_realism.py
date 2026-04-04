from src.narrativeos.core.dialogue import compose_dialogue
from src.narrativeos.core.voice import response_profile_for_actor, voice_profile_for_actor
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_turn_taking_dialogue_structure_exists():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    beat = runtime.event_atoms[0]
    scene_beat = type("Beat", (), {"event": beat, "dramatic_job": "entry"})()
    text = compose_dialogue(runtime.world_record.world, runtime.initial_state, scene_beat, repeated=False)
    assert "：“" in text
    assert "最后只回了一句" in text


def test_voice_profiles_differ_across_roles():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    lead_voice = voice_profile_for_actor(runtime.world_record.world, runtime.initial_state, runtime.event_atoms[0].actors[0])
    counterpart_voice = voice_profile_for_actor(runtime.world_record.world, runtime.initial_state, runtime.event_atoms[0].actors[1])
    assert (
        lead_voice.directness != counterpart_voice.directness
        or lead_voice.restraint != counterpart_voice.restraint
        or lead_voice.bluntness != counterpart_voice.bluntness
    )
    lead_response = response_profile_for_actor(runtime.world_record.world, runtime.initial_state, runtime.event_atoms[0].actors[0])
    counterpart_response = response_profile_for_actor(runtime.world_record.world, runtime.initial_state, runtime.event_atoms[0].actors[1])
    assert lead_response.reply_lines != counterpart_response.reply_lines
