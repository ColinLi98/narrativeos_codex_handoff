from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.contracts import (
    DialogueRealismPolicy,
    EmotionActionPolicy,
    ResponseCadenceProfile,
    SceneRealizationContract,
    SensoryGroundingPolicy,
    VoiceProfile,
    WorldNarrativeStylePack,
)
from ..models import CharacterState, CreatorControls, EventAtom, NarrativeState, WorldBible, WorldRecord
from ..scene_functions import normalize_scene_function
from .models import RuntimeBundle, SceneBlueprint, WorldPack, WorldVersion
from .validator import validate_worldpack_payload


BASE_DIR = Path(__file__).resolve().parents[3]
WORLDPACK_DIR = BASE_DIR / "examples" / "worldpacks"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_empty_style_pack(style_pack: WorldNarrativeStylePack) -> bool:
    payload = style_pack.to_dict()
    return not any(
        payload[key]
        for key in ("goal_labels", "tag_labels")
    ) and not any(
        payload[section]
        for section in ("dialogue", "emotion_actions", "sensory_grounding", "scene_realization")
        if payload[section] != WorldNarrativeStylePack().to_dict()[section]
    )


def _style_pack_from_assets(worldpack: WorldPack) -> WorldNarrativeStylePack:
    if not any(
        [
            worldpack.dialogue_realism_policy,
            worldpack.voice_profiles,
            worldpack.response_cadence_profiles,
            worldpack.pressure_response_styles,
            worldpack.emotion_action_policies,
            worldpack.sensory_grounding_policies,
            worldpack.scene_realization_contracts,
        ]
    ):
        return WorldNarrativeStylePack()
    return WorldNarrativeStylePack(
        style_pack_id=worldpack.narrative_style_pack.style_pack_id or "default",
        tonal_lexicon=list(worldpack.narrative_style_pack.tonal_lexicon),
        thematic_axis_labels=dict(worldpack.narrative_style_pack.thematic_axis_labels),
        hook_templates=list(worldpack.narrative_style_pack.hook_templates),
        goal_labels=dict(worldpack.narrative_style_pack.goal_labels),
        tag_labels=dict(worldpack.narrative_style_pack.tag_labels),
        dialogue=DialogueRealismPolicy.from_dict(
            {
                **dict(worldpack.dialogue_realism_policy or {}),
                "voice_profiles": worldpack.voice_profiles,
                "response_profiles": worldpack.response_cadence_profiles,
                "pressure_styles": worldpack.pressure_response_styles,
            }
        ),
        emotion_actions=EmotionActionPolicy.from_dict(
            next(iter(worldpack.emotion_action_policies.values()), {})
        ),
        sensory_grounding=SensoryGroundingPolicy.from_dict(
            next(iter(worldpack.sensory_grounding_policies.values()), {})
        ),
        scene_realization=SceneRealizationContract.from_dict(
            next(iter(worldpack.scene_realization_contracts.values()), {})
        ),
    )


def _default_style_pack(worldpack: WorldPack) -> WorldNarrativeStylePack:
    voice_profiles = {}
    response_profiles = {}
    action_map: Dict[str, Dict[str, List[str]]] = {}
    location_slots: Dict[str, Dict[str, List[str]]] = {}
    for character in worldpack.characters:
        cadence = "cool" if "冷" in "".join(character.speech_traits) else "measured"
        directness = 0.72 if any(token in "".join(character.speech_traits) for token in ["直", "逼", "冷"]) else 0.48
        restraint = 0.72 if any(token in "".join(character.speech_traits) for token in ["克制", "体面", "迟疑"]) else 0.52
        voice_profiles[character.character_id] = VoiceProfile(
            cadence=cadence,
            directness=directness,
            bluntness=0.62 if "逼问" in "".join(character.action_traits) else 0.4,
            restraint=restraint,
            social_rank_awareness=0.8 if character.role in {"matriarch", "heir", "lead"} else 0.45,
            opening_style=["我知道这句话一旦说出来，就再也没法装作没发生。"],
            pressure_style=["事到这里，再躲下去也只会让事情更难收。"],
            pivot_style=["真正难的不是选哪条路，而是承认自己早就偏了过去。"],
            aftermath_style=["话停在这里，可谁都知道，后面的代价还没真正追上来。"],
            echo_style=["等下一次再开口时，谁也不可能还是刚才那个人。"],
        )
        response_profiles[character.character_id] = ResponseCadenceProfile(
            reaction_tempo="measured",
            reaction_lines={
                "entry": ["他没有立刻接话，只是把那句意思在心里又过了一遍。"],
                "pressure": ["听到这里，手上的细小动作先停住了。"],
                "pivot": ["这才抬起眼来，像终于不打算再替谁留余地。"],
                "aftermath": ["到收声的时候，反而比刚才更轻，也更沉。"],
                "echo": ["没有再追问，可沉默已经替下一次相见留了一道裂口。"],
            },
            reply_lines={
                "entry": ["这句话既然已经出口，就别再往回收了。"],
                "pressure": ["你总得先替自己承认一次。"],
                "pivot": ["再退半步，也只是让伤口换个地方继续裂。"],
                "aftermath": ["这事不会就这样过去。"],
                "echo": ["下次再来时，就别只带着半句真话。"],
            },
        )

    for blueprint in worldpack.scene_blueprints:
        action_map[normalize_scene_function(blueprint.scene_function)] = {
            "entry": ["动作不算大，可场里的气已经先压紧了。"],
            "pressure": ["连最细小的停顿都带上了掂量，像谁先多动一下，谁就会先露底。"],
            "pivot": ["那一点极轻的改口和停顿，让场面从还能周旋，变成了不得不选边。"],
            "aftermath": ["说出口的话停了，可每个人散开时都比来时更沉。"],
            "echo": ["越到后面，越能听见那些没说尽的话慢慢回身索账。"],
            "repeat": ["动作并不大，可谁都知道事情已经换了味道。"],
        }

    for location in worldpack.world_bible.get("locations", []) or []:
        location_slots[location] = {
            "atmosphere": [f"{location}里并不安静，连空气都像在替谁压住一口没说完的话。"],
            "detail": [f"{location}里的光线和器物都像偏向了更难退开的那一边。"],
            "repeat_detail": [f"{location}里最轻的一点动静，反而把场面的情绪压得更清。"],
        }

    return WorldNarrativeStylePack(
        dialogue=DialogueRealismPolicy(
            turn_pattern=["speaker", "reaction", "reply"],
            minimum_exchanges=1,
            voice_profiles=voice_profiles,
            response_profiles=response_profiles,
            pressure_styles={},
        ),
        emotion_actions=EmotionActionPolicy(action_map=action_map),
        sensory_grounding=SensoryGroundingPolicy(
            location_slots=location_slots,
            generic_slots={
                "atmosphere": ["场里并不安静，连空气都像在替谁压住一口没说完的话。"],
                "detail": ["细小的声响和光线变化，把场里的情绪压得更清了一层。"],
                "repeat_detail": ["越到后面，越能听见那些没说尽的话在场里慢慢回身。"],
            },
        ),
        scene_realization=SceneRealizationContract(
            scene_openings={normalize_scene_function(scene.scene_function): [f"{scene.scene_id} 这一类场面最先压下来的，是还没人肯说破的那一点心事。"] for scene in worldpack.scene_blueprints},
            scene_hooks={normalize_scene_function(scene.scene_function): [f"等这场话停下来时，真正要追上来的往往是{scene.scene_id}留下来的余波。"] for scene in worldpack.scene_blueprints},
            scene_pressures={},
        ),
        goal_labels={},
        tag_labels={genre: genre.replace("_", " ") for genre in worldpack.manifest.genres},
    )


def runtime_bundle_from_worldpack_data(bundle: Dict[str, Any]) -> RuntimeBundle:
    payload = dict(bundle.get("worldpack", bundle))
    worldpack = WorldPack.from_dict(payload)
    asset_style_pack = _style_pack_from_assets(worldpack)
    if not _is_empty_style_pack(asset_style_pack):
        worldpack.narrative_style_pack = asset_style_pack
    elif _is_empty_style_pack(worldpack.narrative_style_pack):
        worldpack.narrative_style_pack = _default_style_pack(worldpack)
    if worldpack.runtime_world_bible and worldpack.runtime_initial_state and worldpack.runtime_event_atoms:
        runtime_world = dict(worldpack.runtime_world_bible)
        runtime_world.setdefault("creator_controls", {})
        runtime_world["creator_controls"].setdefault("metadata", {})
        runtime_world["creator_controls"]["metadata"]["narrative_style_pack"] = worldpack.narrative_style_pack.to_dict()
        world = WorldBible.from_dict(runtime_world)
        initial_state = NarrativeState.from_dict(worldpack.runtime_initial_state)
        event_atoms = [EventAtom.from_dict(item) for item in worldpack.runtime_event_atoms]
        return RuntimeBundle(
            world_version_id=bundle.get("world_version_id", "%s@%s" % (worldpack.world_id, worldpack.version)),
            worldpack=worldpack,
            world_record=WorldRecord(world=world, event_atoms=event_atoms, metadata={"worldpack": worldpack.to_dict()}),
            initial_state=initial_state,
            event_atoms=event_atoms,
            player_inputs=list(worldpack.runtime_player_inputs or []),
        )
    return synthesize_runtime_bundle(worldpack)


def _character_state_from_profile(profile: Dict[str, Any]) -> CharacterState:
    return CharacterState.from_dict(
        {
            "name": profile["display_name"],
            "role": profile.get("role", "lead"),
            "public_goals": [profile["destiny_contract"].get("life_theme", "")]
            if profile["destiny_contract"].get("life_theme")
            else [],
            "hidden_goals": list(profile["vow_profile"].get("vows", [])),
            "constraints": [],
            "beliefs_true": [],
            "beliefs_false": [],
            "emotions": {"suspicion": 0.3, "hope": 0.3},
            "trust": {},
            "poisons": profile["poison_vector"],
            "vows": profile["vow_profile"],
            "wound": profile["wound_profile"],
            "awakening": profile["awakening_profile"],
            "destiny": {
                "life_theme": profile["destiny_contract"].get("life_theme", ""),
                "inescapable_nodes": list(profile["destiny_contract"].get("inescapable_nodes", [])),
                "fated_relations": list(profile["destiny_contract"].get("fated_relations", [])),
                "forbidden_escape": [profile["destiny_contract"].get("forbidden_escape", "")] if profile["destiny_contract"].get("forbidden_escape") else [],
                "endgame_shapes": list(profile["destiny_contract"].get("endgame_shapes", [])),
            },
            "debts": [],
            "karmic_seeds": [],
        }
    )


def _synthesize_event_from_blueprint(
    worldpack: WorldPack,
    blueprint: SceneBlueprint,
    beat_index: int,
    actor_ids: List[str],
) -> Dict[str, Any]:
    beat_text = blueprint.beats_template[beat_index]
    event_id = "%s__%s__%s" % (worldpack.world_id, blueprint.scene_id, beat_index)
    seed_id = "%s__seed" % event_id
    is_last = beat_index == len(blueprint.beats_template) - 1
    world_locations = list(worldpack.world_bible.get("locations", []))
    location = world_locations[beat_index % len(world_locations)] if world_locations else "%s·%s" % (worldpack.title, blueprint.scene_id)
    promise_id = "%s__promise" % blueprint.scene_id
    return {
        "event_id": event_id,
        "title": "%s · %s" % (blueprint.scene_id, beat_text),
        "summary": "%s 中，%s 让人物进一步卷入 %s。" % (worldpack.title, beat_text, blueprint.scene_function),
        "location": location,
        "actors": actor_ids,
        "scene_function": normalize_scene_function(blueprint.scene_function),
        "tags": list(dict.fromkeys((worldpack.manifest.genres[:2] + blueprint.vow_tests[:1] + blueprint.wound_triggers[:1]) or ["fate", "choice"])),
        "preconditions_all": [] if beat_index == 0 else ["%s__step_%s" % (blueprint.scene_id, beat_index - 1)],
        "forbidden_if_any": [],
        "world_fact_deltas_add": ["%s__step_%s" % (blueprint.scene_id, beat_index)],
        "world_fact_deltas_remove": [],
        "belief_updates": {},
        "trust_deltas": [],
        "emotion_deltas": [],
        "promises_open": [
            {
                "promise_id": promise_id,
                "description": "%s 迟早要被说清楚。" % beat_text,
                "opened_at_turn": 0,
                "due_by_turn": 3,
                "holders": list(dict.fromkeys(actor_ids[:2] or actor_ids[:1])),
                "fulfillment_modes": ["truth", "choice", "confession"],
                "status": "open",
                "stakes": "medium",
                "tags": [normalize_scene_function(blueprint.scene_function), "story_thread"],
            }
        ] if beat_index == 0 and not is_last else [],
        "promises_close": [],
        "tension_delta": 0.08 if not is_last else 0.04,
        "theme_impacts": {genre: 0.06 for genre in worldpack.manifest.genres[:2]},
        "agency_affordances": list(dict.fromkeys(blueprint.vow_tests[:1] + blueprint.wound_triggers[:1] + ["selfhood"])),
        "rating_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
        "temptation_vector": {
            "greed": 0.04 if blueprint.scene_function == "temptation" else 0.0,
            "anger": 0.06 if blueprint.scene_function in {"truth_trial", "humiliation"} else 0.0,
            "delusion": 0.08 if blueprint.scene_function == "misrecognition" else 0.02,
            "pride": 0.06 if blueprint.scene_function in {"mask_crack", "false_peace"} else 0.03,
            "doubt": 0.08 if blueprint.scene_function in {"temptation", "misrecognition"} else 0.03,
        },
        "vow_tests": list(blueprint.vow_tests),
        "wound_triggers": list(blueprint.wound_triggers),
        "debt_deltas": [
            {
                "source": actor_ids[0],
                "target": actor_ids[1] if len(actor_ids) > 1 else actor_ids[0],
                "debt_type": "scene_aftertaste",
                "magnitude": 0.12,
                "obligation": 0.05,
                "note": beat_text,
            }
        ],
        "karmic_seed_creations": [
            {
                "seed_id": seed_id,
                "source_event_id": event_id,
                "actor": actor_ids[0],
                "target": actor_ids[1] if len(actor_ids) > 1 else None,
                "seed_type": blueprint.scene_function,
                "charge": 0.36,
                "tags": list(dict.fromkeys(blueprint.vow_tests[:1] + blueprint.wound_triggers[:1] + worldpack.manifest.genres[:2])),
                "created_at_turn": 0,
                "ripening_conditions": [normalize_scene_function(blueprint.scene_function), "truth_trial", "karma_ripening"],
                "earliest_turn": 2,
                "latest_turn": 8,
                "status": "dormant",
                "transformable_by": ["mutual_truth", "vow_payment", "public_witness"],
            }
        ],
        "karmic_seed_resolutions": [],
        "awakening_affordances": ["mutual_truth"] if blueprint.scene_function in {"truth_trial", "confession_window"} else [],
        "concealment_level": 0.55 if blueprint.scene_function in {"temptation", "misrecognition", "false_peace"} else 0.12,
        "consequence_delay_hint": 2,
        "metadata": {
            "scene_blueprint_id": blueprint.scene_id,
            "generated_from_worldpack": True,
            **({"terminal": True, "endgame_shape": "awakening", "required_fate_pressure": 0.4, "required_inescapable_nodes": list(profile for profile in blueprint.vow_tests[:1]), "ending_gate": blueprint.ending_gate or {"min_turn": 6, "required_scene_functions": [normalize_scene_function(blueprint.scene_function)], "required_closed_promises": [], "required_tension_min": 0.35}} if is_last and blueprint.ending_gate else {}),
        },
    }


def synthesize_runtime_bundle(worldpack: WorldPack) -> RuntimeBundle:
    asset_style_pack = _style_pack_from_assets(worldpack)
    if not _is_empty_style_pack(asset_style_pack):
        worldpack.narrative_style_pack = asset_style_pack
    elif _is_empty_style_pack(worldpack.narrative_style_pack):
        worldpack.narrative_style_pack = _default_style_pack(worldpack)
    character_ids = [profile.character_id for profile in worldpack.characters]
    characters = {profile.character_id: _character_state_from_profile(profile.to_dict()) for profile in worldpack.characters}
    for source_id in characters:
        characters[source_id].trust = {
            target_id: 0.55
            for target_id in character_ids
            if target_id != source_id
        }
    world = WorldBible.from_dict(
        {
            "world_id": worldpack.world_id,
            "title": worldpack.title,
            "source_type": "worldpack",
            "themes": list(dict.fromkeys(worldpack.manifest.genres + ["fate", "selfhood"]))[:5],
            "canon_anchors": [worldpack.world_bible.get("premise", worldpack.title)] + list(worldpack.world_bible.get("canon_rules", [])),
            "forbidden_moves": list(worldpack.world_bible.get("forbidden_moves", [])),
            "characters": character_ids,
            "locations": list(worldpack.world_bible.get("locations", [])) or [worldpack.title, "长廊", "回廊", "门前"],
            "creator_controls": {
                "merge_policy": "allow_dag_with_scars",
                "darkness_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
                "theme_targets": list(worldpack.manifest.genres[:3]),
                "payoff_style": "beta_worldpack",
                "metadata": {"narrative_style_pack": worldpack.narrative_style_pack.to_dict()},
            },
        }
    )
    relationship_graph = []
    if len(character_ids) >= 2:
        for source_id in character_ids:
            for target_id in character_ids:
                if source_id == target_id:
                    continue
                relationship_graph.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "attachment": 0.28,
                        "resentment": 0.08,
                        "shame": 0.05,
                        "obligation": 0.12,
                        "projection": 0.15,
                        "possession": 0.06,
                        "gratitude": 0.12,
                        "fear": 0.2,
                        "debts": [],
                        "notes": ["synthetic_worldpack_edge"],
                    }
                )
    initial_state = NarrativeState.from_dict(
        {
            "state_id": "%s__state_0001" % worldpack.world_id,
            "world_id": worldpack.world_id,
            "turn_index": 0,
            "story_phase": "setup",
            "chapter_index": 0,
            "min_end_turn": 6,
            "fate_pressure": 0.18,
            "karmic_weather": {"suspicion": 0.18, "grief": 0.06, "temptation": 0.22, "shame": 0.11, "mercy": 0.09},
            "unresolved_debts": [],
            "world_facts": [worldpack.world_bible.get("premise", worldpack.title)],
            "timeline": [],
            "characters": {key: value.to_dict() for key, value in characters.items()},
            "relationship_graph": relationship_graph,
            "open_promises": [],
            "tension": 0.34,
            "themes": {genre: 0.45 for genre in worldpack.manifest.genres[:4]},
            "player_intent": {"curiosity": 0.55, "selfhood": 0.55, "honesty": 0.4},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
            "metadata": {"source_type": "synthesized_worldpack"},
        }
    )
    event_atoms: List[EventAtom] = []
    for blueprint in worldpack.scene_blueprints:
        actor_ids = [
            next(
                (
                    profile.character_id
                    for profile in worldpack.characters
                    if profile.role == role
                ),
                character_ids[0],
            )
            for role in blueprint.required_roles
        ] or character_ids[:1]
        for index in range(len(blueprint.beats_template)):
            event_atoms.append(EventAtom.from_dict(_synthesize_event_from_blueprint(worldpack, blueprint, index, actor_ids)))
    return RuntimeBundle(
        world_version_id="%s@%s" % (worldpack.world_id, worldpack.version),
        worldpack=worldpack,
        world_record=WorldRecord(world=world, event_atoms=event_atoms, metadata={"synthesized": True}),
        initial_state=initial_state,
        event_atoms=event_atoms,
        player_inputs=[{"raw_input": "先看看这条命会把我带去哪里。", "intent_vector": {"curiosity": 0.7, "selfhood": 0.5}}],
    )


class FileSystemWorldRegistry:
    def __init__(self, worldpack_dir: Optional[Path] = None) -> None:
        self.worldpack_dir = worldpack_dir or WORLDPACK_DIR

    def _world_card_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(payload.get("metadata", {}))
        catalog_role = str(metadata.get("catalog_role", "published") or "published")
        benchmark_enabled = bool(metadata.get("benchmark_enabled", catalog_role == "published"))
        return {
            "world_id": payload["world_id"],
            "title": payload["title"],
            "world_version_id": "%s@%s" % (payload["world_id"], payload.get("version", "1.0.0")),
            "status": "published",
            "manifest": payload.get("manifest", {}),
            "metadata": metadata,
            "catalog_role": catalog_role,
            "benchmark_enabled": benchmark_enabled,
            "worldpack": payload,
        }

    def list_worldpacks(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for path in sorted(self.worldpack_dir.glob("*.json")):
            if not path.is_file():
                continue
            payload = _load_json(path)
            results.append(self._world_card_from_payload(payload))
        return results

    def list_benchmark_worldpacks(self) -> List[Dict[str, Any]]:
        return [
            item
            for item in self.list_worldpacks()
            if item.get("catalog_role") == "published" and bool(item.get("benchmark_enabled", True))
        ]

    def validate_worldpack(self, worldpack: Dict[str, Any]) -> Dict[str, Any]:
        return validate_worldpack_payload(worldpack)

    def get_published_world(self, world_id: str) -> Dict[str, Any]:
        for path in self.worldpack_dir.glob("*.json"):
            payload = _load_json(path)
            if payload.get("world_id") == world_id:
                return self._world_card_from_payload(payload)
        raise KeyError("unknown_world:%s" % world_id)

    def get_world_version(self, world_version_id: str) -> Dict[str, Any]:
        world_id = world_version_id.split("@", 1)[0]
        published = self.get_published_world(world_id)
        return {
            "world_version_id": world_version_id,
            "world_id": published["world_id"],
            "status": "published",
            "worldpack": published["worldpack"],
        }

    def get_runtime_bundle(self, world_version_id: str) -> RuntimeBundle:
        return runtime_bundle_from_worldpack_data(self.get_world_version(world_version_id))
