from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.contracts import WorldNarrativeStylePack
from ..models import CharacterState, EventAtom, NarrativeState, WorldBible, WorldRecord


@dataclass
class SeriesPlan:
    series_id: str
    title: str
    total_volume_target: int
    total_chapter_target: int
    target_word_count: int
    theme_statement: str = ""
    series_promises: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeriesPlan":
        return cls(
            series_id=str(data["series_id"]),
            title=str(data["title"]),
            total_volume_target=int(data.get("total_volume_target", 1)),
            total_chapter_target=int(data.get("total_chapter_target", 1)),
            target_word_count=int(data.get("target_word_count", 1000)),
            theme_statement=str(data.get("theme_statement", "")),
            series_promises=[dict(item) for item in data.get("series_promises", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_id": self.series_id,
            "title": self.title,
            "total_volume_target": self.total_volume_target,
            "total_chapter_target": self.total_chapter_target,
            "target_word_count": self.target_word_count,
            "theme_statement": self.theme_statement,
            "series_promises": [dict(item) for item in self.series_promises],
        }


@dataclass
class ChapterTaskTemplate:
    chapter_task_id: str
    objective: str
    duty_type: str
    target_words: int
    reveal_budget: int
    promise_actions: List[str] = field(default_factory=list)
    promise_targets: List[str] = field(default_factory=list)
    allow_terminal: bool = False
    bridge_only: bool = False
    notes: str = ""
    quality_contract: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterTaskTemplate":
        return cls(
            chapter_task_id=str(data["chapter_task_id"]),
            objective=str(data["objective"]),
            duty_type=str(data["duty_type"]),
            target_words=int(data.get("target_words", 2000)),
            reveal_budget=int(data.get("reveal_budget", 1)),
            promise_actions=list(data.get("promise_actions", [])),
            promise_targets=list(data.get("promise_targets", [])),
            allow_terminal=bool(data.get("allow_terminal", False)),
            bridge_only=bool(data.get("bridge_only", False)),
            notes=str(data.get("notes", "")),
            quality_contract=dict(data.get("quality_contract", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_task_id": self.chapter_task_id,
            "objective": self.objective,
            "duty_type": self.duty_type,
            "target_words": self.target_words,
            "reveal_budget": self.reveal_budget,
            "promise_actions": list(self.promise_actions),
            "promise_targets": list(self.promise_targets),
            "allow_terminal": self.allow_terminal,
            "bridge_only": self.bridge_only,
            "notes": self.notes,
            "quality_contract": dict(self.quality_contract),
        }


@dataclass
class ArcPlan:
    arc_id: str
    volume_id: str
    order: int
    title: str
    goal: str
    conflict: str
    reveal_budget: int
    payoff_targets: List[str]
    completion_conditions: List[str]
    target_chapters: int
    arc_promises: List[Dict[str, Any]] = field(default_factory=list)
    chapter_tasks: List[ChapterTaskTemplate] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArcPlan":
        return cls(
            arc_id=str(data["arc_id"]),
            volume_id=str(data["volume_id"]),
            order=int(data.get("order", 1)),
            title=str(data.get("title", "")),
            goal=str(data.get("goal", "")),
            conflict=str(data.get("conflict", "")),
            reveal_budget=int(data.get("reveal_budget", 1)),
            payoff_targets=list(data.get("payoff_targets", [])),
            completion_conditions=list(data.get("completion_conditions", [])),
            target_chapters=int(data.get("target_chapters", 1)),
            arc_promises=[dict(item) for item in data.get("arc_promises", [])],
            chapter_tasks=[ChapterTaskTemplate.from_dict(item) for item in data.get("chapter_tasks", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arc_id": self.arc_id,
            "volume_id": self.volume_id,
            "order": self.order,
            "title": self.title,
            "goal": self.goal,
            "conflict": self.conflict,
            "reveal_budget": self.reveal_budget,
            "payoff_targets": list(self.payoff_targets),
            "completion_conditions": list(self.completion_conditions),
            "target_chapters": self.target_chapters,
            "arc_promises": [dict(item) for item in self.arc_promises],
            "chapter_tasks": [item.to_dict() for item in self.chapter_tasks],
        }


@dataclass
class VolumePlan:
    volume_id: str
    order: int
    title: str
    goal: str
    target_chapters: int
    climax_definition: str
    end_state: str
    volume_promises: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VolumePlan":
        return cls(
            volume_id=str(data["volume_id"]),
            order=int(data.get("order", 1)),
            title=str(data.get("title", "")),
            goal=str(data.get("goal", "")),
            target_chapters=int(data.get("target_chapters", 1)),
            climax_definition=str(data.get("climax_definition", "")),
            end_state=str(data.get("end_state", "")),
            volume_promises=[dict(item) for item in data.get("volume_promises", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_id": self.volume_id,
            "order": self.order,
            "title": self.title,
            "goal": self.goal,
            "target_chapters": self.target_chapters,
            "climax_definition": self.climax_definition,
            "end_state": self.end_state,
            "volume_promises": [dict(item) for item in self.volume_promises],
        }


@dataclass
class ChapterBudgetPolicy:
    default_target_words: int
    min_target_words: int
    max_target_words: int
    default_reveal_budget: int
    duty_cycle: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterBudgetPolicy":
        return cls(
            default_target_words=int(data.get("default_target_words", 2000)),
            min_target_words=int(data.get("min_target_words", 1800)),
            max_target_words=int(data.get("max_target_words", 2200)),
            default_reveal_budget=int(data.get("default_reveal_budget", 1)),
            duty_cycle=list(data.get("duty_cycle", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_target_words": self.default_target_words,
            "min_target_words": self.min_target_words,
            "max_target_words": self.max_target_words,
            "default_reveal_budget": self.default_reveal_budget,
            "duty_cycle": list(self.duty_cycle),
        }


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
    continuation_blueprints: List[Dict[str, Any]] = field(default_factory=list)
    ending_gate: Dict[str, Any] = field(default_factory=dict)
    quality_contract: Dict[str, Any] = field(default_factory=dict)

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
            continuation_blueprints=[dict(item) for item in data.get("continuation_blueprints", [])],
            ending_gate=dict(data.get("ending_gate", {})),
            quality_contract=dict(data.get("quality_contract", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "scene_id": self.scene_id,
            "scene_function": self.scene_function,
            "phase_support": list(self.phase_support),
            "required_roles": list(self.required_roles),
            "beats_template": list(self.beats_template),
            "wound_triggers": list(self.wound_triggers),
            "vow_tests": list(self.vow_tests),
            "seed_templates": list(self.seed_templates),
            "continuation_blueprints": [dict(item) for item in self.continuation_blueprints],
            "ending_gate": dict(self.ending_gate),
        }
        if self.quality_contract:
            payload["quality_contract"] = dict(self.quality_contract)
        return payload


@dataclass
class WorldPack:
    world_id: str
    title: str
    version: str
    manifest: WorldManifest
    series_plan: Optional[SeriesPlan]
    volume_plans: List[VolumePlan]
    arc_plans: List[ArcPlan]
    chapter_budget_policy: Optional[ChapterBudgetPolicy]
    world_bible: Dict[str, Any]
    characters: List[CharacterProfile]
    scene_blueprints: List[SceneBlueprint]
    style_pack: Dict[str, Any]
    risk_policy: Dict[str, Any]
    memory_compression_policy: Dict[str, Any] = field(default_factory=dict)
    series_storyline_contract: Dict[str, Any] = field(default_factory=dict)
    character_memory_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    steering_guardrails: Dict[str, Any] = field(default_factory=dict)
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
            series_plan=SeriesPlan.from_dict(payload["series_plan"]) if payload.get("series_plan") else None,
            volume_plans=[VolumePlan.from_dict(item) for item in payload.get("volume_plans", [])],
            arc_plans=[ArcPlan.from_dict(item) for item in payload.get("arc_plans", [])],
            chapter_budget_policy=ChapterBudgetPolicy.from_dict(payload["chapter_budget_policy"]) if payload.get("chapter_budget_policy") else None,
            memory_compression_policy=dict(payload.get("memory_compression_policy", {})),
            series_storyline_contract=dict(payload.get("series_storyline_contract", {})),
            character_memory_profiles={key: dict(value) for key, value in payload.get("character_memory_profiles", {}).items()},
            steering_guardrails=dict(payload.get("steering_guardrails", {})),
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
            "metadata": dict(self.metadata),
            "world_bible": dict(self.world_bible),
            "characters": [character.to_dict() for character in self.characters],
            "scene_blueprints": [scene.to_dict() for scene in self.scene_blueprints],
            "style_pack": dict(self.style_pack),
            "narrative_style_pack": self.narrative_style_pack.to_dict(),
            "risk_policy": dict(self.risk_policy),
        }
        if self.series_plan is not None:
            payload["series_plan"] = self.series_plan.to_dict()
        if self.volume_plans:
            payload["volume_plans"] = [item.to_dict() for item in self.volume_plans]
        if self.arc_plans:
            payload["arc_plans"] = [item.to_dict() for item in self.arc_plans]
        if self.chapter_budget_policy is not None:
            payload["chapter_budget_policy"] = self.chapter_budget_policy.to_dict()
        if self.memory_compression_policy:
            payload["memory_compression_policy"] = dict(self.memory_compression_policy)
        if self.series_storyline_contract:
            payload["series_storyline_contract"] = dict(self.series_storyline_contract)
        if self.character_memory_profiles:
            payload["character_memory_profiles"] = {key: dict(value) for key, value in self.character_memory_profiles.items()}
        if self.steering_guardrails:
            payload["steering_guardrails"] = dict(self.steering_guardrails)
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
