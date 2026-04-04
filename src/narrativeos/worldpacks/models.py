from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.contracts import WorldNarrativeStylePack
from ..models import CharacterState, EventAtom, NarrativeState, WorldBible, WorldRecord


@dataclass
class WorldManifest:
    author_id: str
    language: str
    genres: List[str]
    risk_rating: str
    monetization_policy: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldManifest":
        return cls(
            author_id=str(data.get("author_id", "system")),
            language=str(data.get("language", "zh-CN")),
            genres=list(data.get("genres", [])),
            risk_rating=str(data.get("risk_rating", "PG-13")),
            monetization_policy=dict(data.get("monetization_policy", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "author_id": self.author_id,
            "language": self.language,
            "genres": list(self.genres),
            "risk_rating": self.risk_rating,
            "monetization_policy": dict(self.monetization_policy),
        }


@dataclass
class CharacterProfile:
    character_id: str
    display_name: str
    role: str
    destiny_contract: Dict[str, Any]
    poison_vector: Dict[str, float]
    vow_profile: Dict[str, Any]
    wound_profile: Dict[str, Any]
    awakening_profile: Dict[str, Any]
    speech_traits: List[str] = field(default_factory=list)
    action_traits: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterProfile":
        return cls(
            character_id=str(data["character_id"]),
            display_name=str(data["display_name"]),
            role=str(data.get("role", "")),
            destiny_contract=dict(data.get("destiny_contract", {})),
            poison_vector={key: float(value) for key, value in data.get("poison_vector", {}).items()},
            vow_profile=dict(data.get("vow_profile", {})),
            wound_profile=dict(data.get("wound_profile", {})),
            awakening_profile=dict(data.get("awakening_profile", {})),
            speech_traits=list(data.get("speech_traits", [])),
            action_traits=list(data.get("action_traits", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_id": self.character_id,
            "display_name": self.display_name,
            "role": self.role,
            "destiny_contract": dict(self.destiny_contract),
            "poison_vector": dict(self.poison_vector),
            "vow_profile": dict(self.vow_profile),
            "wound_profile": dict(self.wound_profile),
            "awakening_profile": dict(self.awakening_profile),
            "speech_traits": list(self.speech_traits),
            "action_traits": list(self.action_traits),
        }


@dataclass
class SceneBlueprint:
    scene_id: str
    scene_function: str
    phase_support: List[str]
    required_roles: List[str]
    beats_template: List[str]
    wound_triggers: List[str] = field(default_factory=list)
    vow_tests: List[str] = field(default_factory=list)
    seed_templates: List[str] = field(default_factory=list)
    ending_gate: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneBlueprint":
        return cls(
            scene_id=str(data["scene_id"]),
            scene_function=str(data["scene_function"]),
            phase_support=list(data.get("phase_support", [])),
            required_roles=list(data.get("required_roles", [])),
            beats_template=list(data.get("beats_template", [])),
            wound_triggers=list(data.get("wound_triggers", [])),
            vow_tests=list(data.get("vow_tests", [])),
            seed_templates=list(data.get("seed_templates", [])),
            ending_gate=dict(data.get("ending_gate", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_function": self.scene_function,
            "phase_support": list(self.phase_support),
            "required_roles": list(self.required_roles),
            "beats_template": list(self.beats_template),
            "wound_triggers": list(self.wound_triggers),
            "vow_tests": list(self.vow_tests),
            "seed_templates": list(self.seed_templates),
            "ending_gate": dict(self.ending_gate),
        }


@dataclass
class WorldPack:
    world_id: str
    title: str
    version: str
    manifest: WorldManifest
    world_bible: Dict[str, Any]
    characters: List[CharacterProfile]
    scene_blueprints: List[SceneBlueprint]
    style_pack: Dict[str, Any]
    risk_policy: Dict[str, Any]
    narrative_style_pack: WorldNarrativeStylePack = field(default_factory=WorldNarrativeStylePack)
    dialogue_realism_policy: Dict[str, Any] = field(default_factory=dict)
    voice_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    response_cadence_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pressure_response_styles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    emotion_action_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    sensory_grounding_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scene_realization_contracts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    runtime_world_bible: Optional[Dict[str, Any]] = None
    runtime_initial_state: Optional[Dict[str, Any]] = None
    runtime_event_atoms: Optional[List[Dict[str, Any]]] = None
    runtime_player_inputs: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldPack":
        payload = dict(data)
        return cls(
            world_id=str(payload["world_id"]),
            title=str(payload["title"]),
            version=str(payload["version"]),
            manifest=WorldManifest.from_dict(payload["manifest"]),
            world_bible=dict(payload.get("world_bible", {})),
            characters=[CharacterProfile.from_dict(item) for item in payload.get("characters", [])],
            scene_blueprints=[SceneBlueprint.from_dict(item) for item in payload.get("scene_blueprints", [])],
            style_pack=dict(payload.get("style_pack", {})),
            narrative_style_pack=WorldNarrativeStylePack.from_dict(payload.get("narrative_style_pack")),
            risk_policy=dict(payload.get("risk_policy", {})),
            dialogue_realism_policy=dict(payload.get("dialogue_realism_policy", {})),
            voice_profiles={key: dict(value) for key, value in payload.get("voice_profiles", {}).items()},
            response_cadence_profiles={key: dict(value) for key, value in payload.get("response_cadence_profiles", {}).items()},
            pressure_response_styles={key: dict(value) for key, value in payload.get("pressure_response_styles", {}).items()},
            emotion_action_policies={key: dict(value) for key, value in payload.get("emotion_action_policies", {}).items()},
            sensory_grounding_policies={key: dict(value) for key, value in payload.get("sensory_grounding_policies", {}).items()},
            scene_realization_contracts={key: dict(value) for key, value in payload.get("scene_realization_contracts", {}).items()},
            runtime_world_bible=dict(payload.get("runtime_world_bible", {})) if payload.get("runtime_world_bible") else None,
            runtime_initial_state=dict(payload.get("runtime_initial_state", {})) if payload.get("runtime_initial_state") else None,
            runtime_event_atoms=[dict(item) for item in payload.get("runtime_event_atoms", [])] if payload.get("runtime_event_atoms") else None,
            runtime_player_inputs=[dict(item) for item in payload.get("runtime_player_inputs", [])] if payload.get("runtime_player_inputs") else None,
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "world_id": self.world_id,
            "title": self.title,
            "version": self.version,
            "manifest": self.manifest.to_dict(),
            "world_bible": dict(self.world_bible),
            "characters": [character.to_dict() for character in self.characters],
            "scene_blueprints": [scene.to_dict() for scene in self.scene_blueprints],
            "style_pack": dict(self.style_pack),
            "narrative_style_pack": self.narrative_style_pack.to_dict(),
            "risk_policy": dict(self.risk_policy),
        }
        if self.dialogue_realism_policy:
            payload["dialogue_realism_policy"] = dict(self.dialogue_realism_policy)
        if self.voice_profiles:
            payload["voice_profiles"] = {key: dict(value) for key, value in self.voice_profiles.items()}
        if self.response_cadence_profiles:
            payload["response_cadence_profiles"] = {key: dict(value) for key, value in self.response_cadence_profiles.items()}
        if self.pressure_response_styles:
            payload["pressure_response_styles"] = {key: dict(value) for key, value in self.pressure_response_styles.items()}
        if self.emotion_action_policies:
            payload["emotion_action_policies"] = {key: dict(value) for key, value in self.emotion_action_policies.items()}
        if self.sensory_grounding_policies:
            payload["sensory_grounding_policies"] = {key: dict(value) for key, value in self.sensory_grounding_policies.items()}
        if self.scene_realization_contracts:
            payload["scene_realization_contracts"] = {key: dict(value) for key, value in self.scene_realization_contracts.items()}
        if self.runtime_world_bible is not None:
            payload["runtime_world_bible"] = dict(self.runtime_world_bible)
        if self.runtime_initial_state is not None:
            payload["runtime_initial_state"] = dict(self.runtime_initial_state)
        if self.runtime_event_atoms is not None:
            payload["runtime_event_atoms"] = [dict(item) for item in self.runtime_event_atoms]
        if self.runtime_player_inputs is not None:
            payload["runtime_player_inputs"] = [dict(item) for item in self.runtime_player_inputs]
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass
class WorldVersion:
    world_version_id: str
    world_id: str
    version: str
    author_id: str
    status: str
    risk_rating: str
    manifest_json: Dict[str, Any]
    worldpack_json: Dict[str, Any]
    validation_report_json: Dict[str, Any] = field(default_factory=dict)
    simulation_report_json: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_worldpack(
        cls,
        *,
        worldpack: WorldPack,
        world_version_id: str,
        status: str = "draft",
        validation_report_json: Optional[Dict[str, Any]] = None,
        simulation_report_json: Optional[Dict[str, Any]] = None,
    ) -> "WorldVersion":
        return cls(
            world_version_id=world_version_id,
            world_id=worldpack.world_id,
            version=worldpack.version,
            author_id=worldpack.manifest.author_id,
            status=status,
            risk_rating=worldpack.manifest.risk_rating,
            manifest_json=worldpack.manifest.to_dict(),
            worldpack_json=worldpack.to_dict(),
            validation_report_json=dict(validation_report_json or {}),
            simulation_report_json=dict(simulation_report_json or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_version_id": self.world_version_id,
            "world_id": self.world_id,
            "version": self.version,
            "author_id": self.author_id,
            "status": self.status,
            "risk_rating": self.risk_rating,
            "manifest_json": dict(self.manifest_json),
            "worldpack_json": dict(self.worldpack_json),
            "validation_report_json": dict(self.validation_report_json),
            "simulation_report_json": dict(self.simulation_report_json),
        }


@dataclass
class RuntimeBundle:
    world_version_id: str
    worldpack: WorldPack
    world_record: WorldRecord
    initial_state: NarrativeState
    event_atoms: List[EventAtom]
    player_inputs: List[Dict[str, Any]]


def worldpack_from_world_record(
    world_record: WorldRecord,
    *,
    initial_state: NarrativeState,
    player_inputs: Optional[List[Dict[str, Any]]] = None,
    world_version_id: Optional[str] = None,
    version: str = "1.0.0",
    author_id: str = "system_demo",
    genres: Optional[List[str]] = None,
    risk_rating: str = "PG-13",
    trial_chapters: int = 1,
    paid_after: int = 3,
) -> WorldPack:
    characters = []
    for character_id, character in initial_state.characters.items():
        characters.append(
            CharacterProfile(
                character_id=character_id,
                display_name=character.name,
                role=character.role,
                destiny_contract={
                    "life_theme": character.destiny.life_theme,
                    "inescapable_nodes": list(character.destiny.inescapable_nodes),
                    "fated_relations": list(character.destiny.fated_relations),
                    "forbidden_escape": character.destiny.forbidden_escape[0] if character.destiny.forbidden_escape else "",
                    "endgame_shapes": list(character.destiny.endgame_shapes),
                },
                poison_vector=character.poisons.to_dict(),
                vow_profile=character.vows.to_dict(),
                wound_profile=character.wound.to_dict(),
                awakening_profile=character.awakening.to_dict(),
                speech_traits=list(character.wound.defense_style.split("与")),
                action_traits=list(character.public_goals[:2]),
            )
        )

    blueprint_map: Dict[str, SceneBlueprint] = {}
    for event in world_record.event_atoms:
        key = event.scene_function
        if key not in blueprint_map:
            blueprint_map[key] = SceneBlueprint(
                scene_id="scene_%s" % key,
                scene_function=event.scene_function,
                phase_support=["setup", "early_rising", "midpoint", "crisis", "climax", "aftermath"],
                required_roles=[initial_state.characters[actor_id].role for actor_id in event.actors if actor_id in initial_state.characters],
                beats_template=[event.title, event.summary[:24], "余波未散"],
                wound_triggers=list(event.wound_triggers),
                vow_tests=list(event.vow_tests),
                seed_templates=[seed.seed_type for seed in event.karmic_seed_creations],
                ending_gate=dict(event.metadata.get("ending_gate", {})),
            )

    return WorldPack(
        world_id=world_record.world.world_id,
        title=world_record.world.title,
        version=version,
        manifest=WorldManifest(
            author_id=author_id,
            language="zh-CN",
            genres=list(genres or world_record.world.themes[:3] or ["drama"]),
            risk_rating=risk_rating,
            monetization_policy={"trial_chapters": trial_chapters, "paid_after": paid_after},
        ),
        world_bible={
            "premise": world_record.world.title,
            "canon_rules": list(world_record.world.canon_anchors),
            "forbidden_moves": list(world_record.world.forbidden_moves),
        },
        characters=characters,
        scene_blueprints=list(blueprint_map.values()),
        style_pack={"mode": "novel_lush", "pov": "limited_third", "dialogue_density": "medium"},
        risk_policy={"shareable": True, "requires_manual_review": False},
        runtime_world_bible=world_record.world.to_dict(),
        runtime_initial_state=initial_state.to_dict(),
        runtime_event_atoms=[event.to_dict() for event in world_record.event_atoms],
        runtime_player_inputs=list(player_inputs or []),
        metadata={"source": "alpha_migrated", "world_version_id": world_version_id or "%s@%s" % (world_record.world.world_id, version)},
    )
