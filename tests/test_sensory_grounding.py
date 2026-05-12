from src.narrativeos.core.sensory_grounding import scene_atmosphere, scene_detail
from src.narrativeos.prose_linter import lint_prose
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_sensory_grounding_varies_across_packs():
    registry = FileSystemWorldRegistry()
    jade = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    xianxia = registry.get_runtime_bundle("xianxia_forgotten_vow@0.1.0")
    jade_beat = type("Beat", (), {"event": jade.event_atoms[0], "dramatic_job": "entry"})()
    xianxia_beat = type("Beat", (), {"event": xianxia.event_atoms[0], "dramatic_job": "entry"})()
    assert scene_atmosphere(jade.world_record.world, jade_beat) != scene_atmosphere(xianxia.world_record.world, xianxia_beat)
    assert scene_detail(jade.world_record.world, jade_beat, repeated=False) != scene_detail(xianxia.world_record.world, xianxia_beat, repeated=False)


def test_weakest_pack_sensory_and_scene_assets_have_multiple_variants():
    registry = FileSystemWorldRegistry()
    for world_version_id in [
        "urban_mystery_lotus_lane@0.1.0",
        "jade_court_romance@1.0.0",
        "synthetic_min_pack@0.1.0",
    ]:
        runtime = registry.get_runtime_bundle(world_version_id)
        sensory = (runtime.worldpack.sensory_grounding_policies or {}).get("default") or {}
        location_slots = dict(sensory.get("location_slots") or {})
        assert location_slots
        sample_slot = next(iter(location_slots.values()))
        assert len(sample_slot.get("atmosphere", [])) >= 3
        assert len(sample_slot.get("detail", [])) >= 3
        assert len(sample_slot.get("repeat_detail", [])) >= 3

        scene = (runtime.worldpack.scene_realization_contracts or {}).get("default") or {}
        scene_openings = dict(scene.get("scene_openings") or {})
        scene_hooks = dict(scene.get("scene_hooks") or {})
        assert scene_openings
        assert scene_hooks
        first_opening = next(iter(scene_openings.values()))
        first_hook = next(iter(scene_hooks.values()))
        assert len(first_opening) >= 3
        assert len(first_hook) >= 3


def test_detail_markers_count_concrete_archive_and_court_objects():
    text = "扫描台蓝线照到钝印和胶痕，栏杆旁的杯沿、木板和录音笔一起发出轻响。"
    report = lint_prose(text)

    assert report["detail_count"] >= 8
    assert report["concrete_detail_density"] > 0.04


def test_runtime_event_metadata_carries_scene_quality_contract():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    first_event = runtime.event_atoms[0]

    contract = dict(first_event.metadata.get("scene_quality_contract") or {})
    assert contract["dialogue_pressure"] == "medium"
    assert "object_state" in contract["detail_anchor_types"]


def test_synthetic_detail_reinforcement_uses_scene_contract_anchors():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    beat = type("Beat", (), {"event": runtime.event_atoms[0], "dramatic_job": "entry", "beat_index": 1})()

    detail = scene_detail(runtime.world_record.world, beat, repeated=False, chapter_index=1)

    assert any(token in detail for token in ["石砖", "空杯", "纸页"])
    assert any(token in detail for token in ["门檐", "灯下", "潮气", "翻页声"])


def test_synthetic_repeated_detail_varies_across_long_route_chapters():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    beat = type("Beat", (), {"event": runtime.event_atoms[0], "dramatic_job": "pressure", "beat_index": 2})()

    samples = {
        scene_detail(runtime.world_record.world, beat, repeated=True, chapter_index=chapter_index)
        for chapter_index in [12, 39, 78]
    }

    assert len(samples) >= 2
    assert all(lint_prose(sample)["concrete_detail_density"] >= 0.04 for sample in samples)


def test_target_pack_scene_details_use_concrete_anchor_density():
    registry = FileSystemWorldRegistry()
    targets = [
        "tide_archive_memory_debt@0.1.0",
        "jade_court_exam@1.0.0",
        "jade_court_romance@1.0.0",
        "urban_mystery_lotus_lane@0.1.0",
        "xianxia_forgotten_vow@0.1.0",
    ]
    for world_version_id in targets:
        runtime = registry.get_runtime_bundle(world_version_id)
        event = next(item for item in runtime.event_atoms if item.location)
        beat = type("Beat", (), {"event": event, "dramatic_job": "pressure", "beat_index": 2})()

        detail = scene_detail(runtime.world_record.world, beat, repeated=False, chapter_index=260)
        report = lint_prose(detail)

        assert float(report["concrete_detail_density"]) >= 0.065
        assert any(token in detail for token in ["杯沿", "纸页", "灯座", "防潮盒", "雨棚", "石阶", "扫描台", "案角", "栏杆", "香炉", "门框", "笔架", "雨伞骨", "旧门牌"])
        assert any(token in detail for token in ["回声", "落笔声", "水滴声", "钟声", "电流声", "风声", "脚步声", "叶响", "衣袂", "翻卷声"])
