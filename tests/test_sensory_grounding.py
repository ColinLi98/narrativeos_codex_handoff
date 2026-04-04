from src.narrativeos.core.sensory_grounding import scene_atmosphere, scene_detail
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_sensory_grounding_varies_across_packs():
    registry = FileSystemWorldRegistry()
    jade = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    xianxia = registry.get_runtime_bundle("xianxia_forgotten_vow@0.1.0")
    jade_beat = type("Beat", (), {"event": jade.event_atoms[0], "dramatic_job": "entry"})()
    xianxia_beat = type("Beat", (), {"event": xianxia.event_atoms[0], "dramatic_job": "entry"})()
    assert scene_atmosphere(jade.world_record.world, jade_beat) != scene_atmosphere(xianxia.world_record.world, xianxia_beat)
    assert scene_detail(jade.world_record.world, jade_beat, repeated=False) != scene_detail(xianxia.world_record.world, xianxia_beat, repeated=False)
