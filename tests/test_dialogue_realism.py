from src.narrativeos.core.dialogue import compose_dialogue, compose_late_longform_compact_exchange
from src.narrativeos.core.linter import lint_chapter_draft
from src.narrativeos.core.scene_realizer import realize_hook, realize_scene_opening
from src.narrativeos.core.voice import response_profile_for_actor, voice_profile_for_actor
from src.narrativeos.models import ChapterPlan, SceneIntent
from src.narrativeos.rendering import _chapter_summary, _reader_chapter_title, _reader_pull_quote, _reader_story_beats
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _voice_separation_score(profiles):
    bluntness_values = [float(item.get("bluntness", 0.5)) for item in profiles.values()]
    restraint_values = [float(item.get("restraint", 0.5)) for item in profiles.values()]
    return min(
        1.0,
        (
            (max(bluntness_values) - min(bluntness_values))
            + (max(restraint_values) - min(restraint_values))
        )
        / 2.0,
    )


def test_turn_taking_dialogue_structure_exists():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    beat = runtime.event_atoms[0]
    scene_beat = type("Beat", (), {"event": beat, "dramatic_job": "entry"})()
    text = compose_dialogue(runtime.world_record.world, runtime.initial_state, scene_beat, repeated=False)
    assert "：“" in text
    assert text.count("”") >= 2


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


def test_weakest_pack_voice_assets_are_diversified():
    registry = FileSystemWorldRegistry()
    for world_version_id in [
        "urban_mystery_lotus_lane@0.1.0",
        "jade_court_romance@1.0.0",
        "synthetic_min_pack@0.1.0",
    ]:
        runtime = registry.get_runtime_bundle(world_version_id)
        profiles = runtime.worldpack.voice_profiles
        assert profiles
        bluntness_values = [float(item.get("bluntness", 0.5)) for item in profiles.values()]
        restraint_values = [float(item.get("restraint", 0.5)) for item in profiles.values()]
        assert max(bluntness_values) - min(bluntness_values) >= 0.35
        assert max(restraint_values) - min(restraint_values) >= 0.25
        for payload in profiles.values():
            assert len(payload.get("opening_style", [])) >= 3
            assert len(payload.get("pressure_style", [])) >= 3
            assert len(payload.get("pivot_style", [])) >= 3


def test_jade_voice_separation_reaches_longform_polish_target():
    registry = FileSystemWorldRegistry()
    for world_version_id in ["jade_court_exam@1.0.0", "jade_court_romance@1.0.0"]:
        runtime = registry.get_runtime_bundle(world_version_id)
        assert _voice_separation_score(runtime.worldpack.voice_profiles) >= 0.70


def test_jade_same_scene_function_dialogue_uses_role_distinct_templates():
    registry = FileSystemWorldRegistry()
    for world_version_id in ["jade_court_exam@1.0.0", "jade_court_romance@1.0.0"]:
        runtime = registry.get_runtime_bundle(world_version_id)
        events = [
            event
            for event in runtime.event_atoms
            if event.scene_function == "vow_payment" and len(event.actors) >= 2
        ]
        yu_cheng_event = next(event for event in events if event.actors[0] == "yu_cheng")
        lin_wan_event = next(event for event in events if event.actors[0] == "lin_wan")
        state = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": 260})
        samples = []
        for event in [yu_cheng_event, lin_wan_event]:
            beat = type(
                "Beat",
                (),
                {
                    "event": event,
                    "dramatic_job": "pressure",
                    "beat_index": 2,
                    "beat_label": event.title,
                },
            )()
            samples.append(compose_dialogue(runtime.world_record.world, state, beat, repeated=True))

        first_lines = [sample.split("”", 1)[0] for sample in samples]
        assert samples[0] != samples[1]
        assert first_lines[0] != first_lines[1]


def test_targeted_q03_worldpacks_expose_richer_asset_coverage():
    registry = FileSystemWorldRegistry()
    expectations = {
        "xianxia_forgotten_vow@0.1.0": 5,
        "urban_mystery_lotus_lane@0.1.0": 5,
        "jade_court_exam@1.0.0": 11,
    }
    for world_version_id, min_scene_count in expectations.items():
        runtime = registry.get_runtime_bundle(world_version_id)
        worldpack = runtime.worldpack
        assert len(worldpack.scene_blueprints) >= min_scene_count
        for payload in worldpack.voice_profiles.values():
            assert len(payload.get("opening_style", [])) >= 3
            assert len(payload.get("pressure_style", [])) >= 3
            assert len(payload.get("pivot_style", [])) >= 3
            assert len(payload.get("aftermath_style", [])) >= 3
            assert len(payload.get("echo_style", [])) >= 3
        for payload in worldpack.response_cadence_profiles.values():
            for beat_key in ["entry", "pressure", "pivot", "aftermath", "echo"]:
                assert len((payload.get("reaction_lines") or {}).get(beat_key, [])) >= 3
                assert len((payload.get("reply_lines") or {}).get(beat_key, [])) >= 3
        scene_openings = ((worldpack.scene_realization_contracts or {}).get("default") or {}).get("scene_openings") or {}
        assert scene_openings
        for variants in scene_openings.values():
            assert len(variants) >= 3


def test_synthetic_repeated_dialogue_rotates_by_chapter():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    beat = type("Beat", (), {"event": runtime.event_atoms[0], "dramatic_job": "pressure", "beat_index": 2})()
    samples = []
    for chapter_index in [1, 37, 78]:
        state = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": chapter_index})
        samples.append(compose_dialogue(runtime.world_record.world, state, beat, repeated=True))

    assert len(set(samples)) >= 2
    assert any("两人都知道，话已经绕不过刚才留下的那层意思了。" not in sample for sample in samples)


def _beat_for_scene_function(runtime, scene_function: str, *, dramatic_job: str = "pressure", beat_index: int = 2):
    event = next(item for item in runtime.event_atoms if item.scene_function == scene_function and len(item.actors) >= 2)
    return type(
        "Beat",
        (),
        {
            "event": event,
            "dramatic_job": dramatic_job,
            "beat_index": beat_index,
            "beat_label": event.title,
        },
    )()


def test_reader_q03_dialogue_rotates_for_jade_and_xianxia_chapter_windows():
    registry = FileSystemWorldRegistry()
    targets = [
        ("jade_court_exam@1.0.0", "vow_payment"),
        ("jade_court_romance@1.0.0", "misrecognition"),
        ("xianxia_forgotten_vow@0.1.0", "karma_ripening"),
    ]
    for world_version_id, scene_function in targets:
        runtime = registry.get_runtime_bundle(world_version_id)
        beat = _beat_for_scene_function(runtime, scene_function)
        samples = []
        for chapter_index in [21, 220, 260, 460, 480]:
            state = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": chapter_index})
            samples.append(compose_dialogue(runtime.world_record.world, state, beat, repeated=True))

        assert len(set(samples)) >= 4
        assert len({sample.split("：“", 1)[0] for sample in samples}) >= 3
        assert len({sample for sample in samples if "别只给我半句" in sample}) <= 1
        assert len({sample for sample in samples if "不会再推给局势" in sample}) <= 1


def test_late_longform_compact_exchange_is_dense_rotating_and_clean():
    registry = FileSystemWorldRegistry()
    targets = [
        ("jade_court_exam@1.0.0", "vow_payment"),
        ("jade_court_romance@1.0.0", "misrecognition"),
    ]
    forbidden = ["这一章", "这一幕", "scene", "beat", "Q03", "slot", "None", "{}"]
    for world_version_id, scene_function in targets:
        runtime = registry.get_runtime_bundle(world_version_id)
        beat = _beat_for_scene_function(runtime, scene_function)
        samples = []
        for chapter_index in [21, 220, 260, 460, 480]:
            state = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": chapter_index})
            sample = compose_late_longform_compact_exchange(
                runtime.world_record.world,
                state,
                beat,
                repeated=True,
                variant_offset=chapter_index,
            )
            lint = lint_chapter_draft(sample)
            samples.append(sample)
            assert lint["dialogue_count"] >= 4
            assert float(lint["dialogue_plus_action_ratio"]) >= 0.75
            assert all(token not in sample for token in forbidden)

        assert len(set(samples)) >= 4


def test_reader_scene_card_metadata_rotates_for_redundancy_audit():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    beat = _beat_for_scene_function(runtime, "temptation", dramatic_job="pressure", beat_index=2)
    body = "余澄低声道：“这一回我先接住杯沿边那层后果。” 林绾回道：“把后半句也放到门影旁。” 余澄又说：“该疼的地方我不躲了。”"
    summaries = set()
    beat_surfaces = set()
    quotes = set()
    for chapter_index in [21, 220, 260, 460, 480]:
        state_after = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": chapter_index})
        summaries.add(_chapter_summary(runtime.world_record.world, runtime.initial_state, state_after, beat.event))
        beat_surfaces.add(" ".join(_reader_story_beats(runtime.world_record.world, runtime.initial_state, state_after, [beat])))
        quotes.add(_reader_pull_quote(body, state_after, [beat]))

    assert len(summaries) >= 4
    assert len(beat_surfaces) >= 4
    assert len(quotes) >= 2


def test_reader_chapter_titles_rotate_without_internal_scene_tokens():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    beat = _beat_for_scene_function(runtime, "vow_payment", dramatic_job="pressure", beat_index=2)
    chapter_plan = ChapterPlan(
        chapter_index=21,
        story_phase="crisis",
        scene_intent=SceneIntent(
            intent_id="sacrifice_test",
            label="真正要付出代价的时刻",
            description="人物必须承担污名来证明选择不是空话。",
            preferred_scene_functions=["vow_payment"],
            preferred_tags=["sacrifice", "selfhood"],
        ),
        beat_target=3,
        beat_count=1,
        ending_ready=False,
        selected_event_ids=[beat.event.event_id],
    )

    title_tails = set()
    for chapter_index in [21, 220, 260, 460, 480]:
        state_after = type(runtime.initial_state).from_dict({**runtime.initial_state.to_dict(), "chapter_index": chapter_index})
        title = _reader_chapter_title(runtime.world_record.world, runtime.initial_state, state_after, chapter_plan, [beat])
        tail = title.split("·", 1)[-1]
        title_tails.add(tail.strip())
        assert title.startswith(f"第 {chapter_index} 章 · ")
        assert "vow_payment" not in title
        assert "_" not in title
        assert "真正要付出代价的时刻" not in title
        assert "·" not in tail
        assert len(tail.strip()) >= 4

    assert len(title_tails) >= 4


def test_reader_q03_scene_realizer_rotates_openings_hooks_and_pressures():
    registry = FileSystemWorldRegistry()
    targets = [
        ("jade_court_exam@1.0.0", "vow_payment"),
        ("jade_court_romance@1.0.0", "vow_payment"),
        ("xianxia_forgotten_vow@0.1.0", "mask_crack"),
    ]
    for world_version_id, scene_function in targets:
        runtime = registry.get_runtime_bundle(world_version_id)
        beat = _beat_for_scene_function(runtime, scene_function, dramatic_job="entry", beat_index=1)
        openings = {
            realize_scene_opening(
                runtime.world_record.world,
                beat,
                "让人物把眼前选择推到明处",
                "家门、旧誓与真心",
                chapter_index=chapter_index,
            )
            for chapter_index in [1, 21, 220, 260, 460, 480]
        }
        hooks = {
            realize_hook(
                runtime.world_record.world,
                "这句余波会追到下一次开口之前",
                scene_function,
                chapter_index=chapter_index,
            )
            for chapter_index in [1, 21, 220, 260, 460, 480]
        }

        assert len(openings) >= 4
        assert len(hooks) >= 3
        assert not all("真正先逼近的不是答案" in item for item in openings)


def test_targeted_q03_scene_opening_pools_are_function_specific():
    registry = FileSystemWorldRegistry()
    expectations = {
        "jade_court_exam@1.0.0": ["humiliation", "vow_payment", "debt_exchange", "karma_ripening", "misrecognition"],
        "jade_court_romance@1.0.0": ["temptation", "confession_window", "humiliation", "vow_payment", "misrecognition"],
        "xianxia_forgotten_vow@0.1.0": ["false_peace", "temptation", "mask_crack", "karma_ripening", "vow_payment"],
    }
    for world_version_id, functions in expectations.items():
        runtime = registry.get_runtime_bundle(world_version_id)
        contract = ((runtime.worldpack.scene_realization_contracts or {}).get("default") or {})
        scene_openings = contract.get("scene_openings") or {}
        scene_hooks = contract.get("scene_hooks") or {}
        scene_pressures = contract.get("scene_pressures") or {}

        opening_pools = [tuple(scene_openings.get(scene_function) or []) for scene_function in functions]
        hook_pools = [tuple(scene_hooks.get(scene_function) or []) for scene_function in functions]
        assert all(len(pool) >= 3 for pool in opening_pools)
        assert all(len(pool) >= 3 for pool in hook_pools)
        assert not any("真正先逼近的不是答案" in line for pool in opening_pools for line in pool)
        assert len(set(opening_pools)) == len(opening_pools)
        assert len(set(hook_pools)) == len(hook_pools)
        assert all(len(scene_pressures.get(scene_function) or []) >= 3 for scene_function in functions)
