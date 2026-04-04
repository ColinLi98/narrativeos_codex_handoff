from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .scene_functions import normalize_scene_function


RATINGS_ORDER = {"G": 0, "PG": 1, "PG13": 2, "R": 3}
STORY_PHASES = ("setup", "early_rising", "midpoint", "crisis", "climax", "aftermath")


def _deepcopy_dataclass(instance: Any) -> Dict[str, Any]:
    return asdict(instance)


@dataclass
class PoisonVector:
    greed: float = 0.0
    anger: float = 0.0
    delusion: float = 0.0
    pride: float = 0.0
    doubt: float = 0.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PoisonVector":
        payload = dict(data or {})
        return cls(
            greed=float(payload.get("greed", 0.0)),
            anger=float(payload.get("anger", 0.0)),
            delusion=float(payload.get("delusion", 0.0)),
            pride=float(payload.get("pride", 0.0)),
            doubt=float(payload.get("doubt", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class VowProfile:
    vows: List[str] = field(default_factory=list)
    sacrifice_capacity: float = 0.0
    truth_tolerance: float = 0.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "VowProfile":
        payload = dict(data or {})
        return cls(
            vows=list(payload.get("vows", [])),
            sacrifice_capacity=float(payload.get("sacrifice_capacity", 0.0)),
            truth_tolerance=float(payload.get("truth_tolerance", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class WoundProfile:
    core_wound: str = ""
    public_self: str = ""
    shadow_desire: str = ""
    defense_style: str = ""

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "WoundProfile":
        payload = dict(data or {})
        return cls(
            core_wound=payload.get("core_wound", ""),
            public_self=payload.get("public_self", ""),
            shadow_desire=payload.get("shadow_desire", ""),
            defense_style=payload.get("defense_style", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class AwakeningProfile:
    clarity: float = 0.0
    reflection_capacity: float = 0.0
    repentance_threshold: float = 0.5
    transformation_paths: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AwakeningProfile":
        payload = dict(data or {})
        return cls(
            clarity=float(payload.get("clarity", 0.0)),
            reflection_capacity=float(payload.get("reflection_capacity", 0.0)),
            repentance_threshold=float(payload.get("repentance_threshold", 0.5)),
            transformation_paths=list(payload.get("transformation_paths", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class DestinyContract:
    life_theme: str = ""
    inescapable_nodes: List[str] = field(default_factory=list)
    fated_relations: List[str] = field(default_factory=list)
    forbidden_escape: List[str] = field(default_factory=list)
    endgame_shapes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DestinyContract":
        payload = dict(data or {})
        return cls(
            life_theme=payload.get("life_theme", ""),
            inescapable_nodes=list(payload.get("inescapable_nodes", [])),
            fated_relations=list(payload.get("fated_relations", [])),
            forbidden_escape=list(payload.get("forbidden_escape", [])),
            endgame_shapes=list(payload.get("endgame_shapes", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class DebtEntry:
    relation_with: str
    debt_type: str
    magnitude: float
    opened_at_turn: int
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebtEntry":
        return cls(
            relation_with=data["relation_with"],
            debt_type=data["debt_type"],
            magnitude=float(data.get("magnitude", 0.0)),
            opened_at_turn=int(data.get("opened_at_turn", 0)),
            notes=data.get("notes", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class KarmicSeed:
    seed_id: str
    source_event_id: str
    actor: str
    target: Optional[str]
    seed_type: str
    charge: float
    tags: List[str]
    created_at_turn: int
    ripening_conditions: List[str]
    earliest_turn: int
    latest_turn: Optional[int]
    status: str
    transformable_by: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KarmicSeed":
        return cls(
            seed_id=data["seed_id"],
            source_event_id=data["source_event_id"],
            actor=data["actor"],
            target=data.get("target"),
            seed_type=data["seed_type"],
            charge=float(data.get("charge", 0.0)),
            tags=list(data.get("tags", [])),
            created_at_turn=int(data.get("created_at_turn", 0)),
            ripening_conditions=list(data.get("ripening_conditions", [])),
            earliest_turn=int(data.get("earliest_turn", 0)),
            latest_turn=int(data["latest_turn"]) if data.get("latest_turn") is not None else None,
            status=data.get("status", "dormant"),
            transformable_by=list(data.get("transformable_by", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class RelationshipEdge:
    source: str
    target: str
    attachment: float = 0.0
    resentment: float = 0.0
    shame: float = 0.0
    obligation: float = 0.0
    projection: float = 0.0
    possession: float = 0.0
    gratitude: float = 0.0
    fear: float = 0.0
    debts: List[DebtEntry] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipEdge":
        payload = dict(data)
        return cls(
            source=payload["source"],
            target=payload["target"],
            attachment=float(payload.get("attachment", 0.0)),
            resentment=float(payload.get("resentment", 0.0)),
            shame=float(payload.get("shame", 0.0)),
            obligation=float(payload.get("obligation", 0.0)),
            projection=float(payload.get("projection", 0.0)),
            possession=float(payload.get("possession", 0.0)),
            gratitude=float(payload.get("gratitude", 0.0)),
            fear=float(payload.get("fear", 0.0)),
            debts=[DebtEntry.from_dict(item) for item in payload.get("debts", [])],
            notes=list(payload.get("notes", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class KarmicWeatherProfile:
    suspicion: float = 0.0
    grief: float = 0.0
    temptation: float = 0.0
    shame: float = 0.0
    mercy: float = 0.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "KarmicWeatherProfile":
        payload = dict(data or {})
        return cls(
            suspicion=float(payload.get("suspicion", 0.0)),
            grief=float(payload.get("grief", 0.0)),
            temptation=float(payload.get("temptation", 0.0)),
            shame=float(payload.get("shame", 0.0)),
            mercy=float(payload.get("mercy", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class CharacterState:
    name: str
    role: str
    public_goals: List[str]
    hidden_goals: List[str]
    constraints: List[str]
    beliefs_true: List[str]
    beliefs_false: List[str]
    emotions: Dict[str, float]
    trust: Dict[str, float]
    poisons: PoisonVector
    vows: VowProfile
    wound: WoundProfile
    awakening: AwakeningProfile
    destiny: DestinyContract
    debts: List[DebtEntry]
    karmic_seeds: List[KarmicSeed]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterState":
        payload = dict(data)
        return cls(
            name=payload["name"],
            role=payload["role"],
            public_goals=list(payload.get("public_goals", [])),
            hidden_goals=list(payload.get("hidden_goals", [])),
            constraints=list(payload.get("constraints", [])),
            beliefs_true=list(payload.get("beliefs_true", [])),
            beliefs_false=list(payload.get("beliefs_false", [])),
            emotions={key: float(value) for key, value in payload.get("emotions", {}).items()},
            trust={key: float(value) for key, value in payload.get("trust", {}).items()},
            poisons=PoisonVector.from_dict(payload.get("poisons")),
            vows=VowProfile.from_dict(payload.get("vows")),
            wound=WoundProfile.from_dict(payload.get("wound")),
            awakening=AwakeningProfile.from_dict(payload.get("awakening")),
            destiny=DestinyContract.from_dict(payload.get("destiny")),
            debts=[DebtEntry.from_dict(item) for item in payload.get("debts", [])],
            karmic_seeds=[KarmicSeed.from_dict(item) for item in payload.get("karmic_seeds", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class PromiseLedgerEntry:
    promise_id: str
    description: str
    opened_at_turn: int
    due_by_turn: int
    holders: List[str]
    fulfillment_modes: List[str]
    status: str
    stakes: str
    tags: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromiseLedgerEntry":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class TrustDelta:
    source: str
    target: str
    delta: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustDelta":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EmotionDelta:
    character: str
    emotion: str
    delta: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionDelta":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class CreatorControls:
    merge_policy: str = "allow_dag_with_scars"
    darkness_ceiling: str = "PG13"
    theme_targets: List[str] = field(default_factory=list)
    payoff_style: str = ""
    scoring_weights: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CreatorControls":
        if not data:
            return cls()
        payload = dict(data)
        return cls(
            merge_policy=payload.get("merge_policy", "allow_dag_with_scars"),
            darkness_ceiling=payload.get("darkness_ceiling", "PG13"),
            theme_targets=list(payload.get("theme_targets", [])),
            payoff_style=payload.get("payoff_style", ""),
            scoring_weights=dict(payload.get("scoring_weights", {})),
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "merge_policy": self.merge_policy,
            "darkness_ceiling": self.darkness_ceiling,
        }
        if self.theme_targets:
            data["theme_targets"] = list(self.theme_targets)
        if self.payoff_style:
            data["payoff_style"] = self.payoff_style
        if self.scoring_weights:
            data["scoring_weights"] = dict(self.scoring_weights)
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class EventAtom:
    event_id: str
    title: str
    summary: str
    actors: List[str]
    scene_function: str
    tags: List[str]
    preconditions_all: List[str]
    forbidden_if_any: List[str]
    world_fact_deltas_add: List[str]
    world_fact_deltas_remove: List[str]
    belief_updates: Dict[str, Dict[str, List[str]]]
    trust_deltas: List[TrustDelta]
    emotion_deltas: List[EmotionDelta]
    promises_open: List[PromiseLedgerEntry]
    promises_close: List[str]
    tension_delta: float
    theme_impacts: Dict[str, float]
    agency_affordances: List[str]
    rating_ceiling: str
    temptation_vector: Dict[str, float]
    vow_tests: List[str]
    wound_triggers: List[str]
    debt_deltas: List[Dict[str, Any]]
    karmic_seed_creations: List[KarmicSeed]
    karmic_seed_resolutions: List[str]
    awakening_affordances: List[str]
    concealment_level: float
    consequence_delay_hint: int
    location: str = ""
    convergence_key: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventAtom":
        payload = dict(data)
        payload["trust_deltas"] = [
            TrustDelta.from_dict(item) for item in payload.get("trust_deltas", [])
        ]
        payload["emotion_deltas"] = [
            EmotionDelta.from_dict(item) for item in payload.get("emotion_deltas", [])
        ]
        payload["promises_open"] = [
            PromiseLedgerEntry.from_dict(item) for item in payload.get("promises_open", [])
        ]
        payload["temptation_vector"] = {
            key: float(value) for key, value in payload.get("temptation_vector", {}).items()
        }
        payload["vow_tests"] = list(payload.get("vow_tests", []))
        payload["wound_triggers"] = list(payload.get("wound_triggers", []))
        payload["debt_deltas"] = [dict(item) for item in payload.get("debt_deltas", [])]
        payload["karmic_seed_creations"] = [
            KarmicSeed.from_dict(item) for item in payload.get("karmic_seed_creations", [])
        ]
        payload["karmic_seed_resolutions"] = list(payload.get("karmic_seed_resolutions", []))
        payload["awakening_affordances"] = list(payload.get("awakening_affordances", []))
        payload["concealment_level"] = float(payload.get("concealment_level", 0.0))
        payload["consequence_delay_hint"] = int(payload.get("consequence_delay_hint", 0))
        payload["scene_function"] = normalize_scene_function(payload.get("scene_function", "false_peace"))
        payload.setdefault("location", "")
        payload.setdefault("convergence_key", "")
        payload.setdefault("metadata", {})
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EndingGate:
    min_turn: int = 8
    required_scene_functions: List[str] = field(default_factory=list)
    required_closed_promises: List[str] = field(default_factory=list)
    required_tension_min: float = 0.7

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EndingGate":
        if not data:
            return cls()
        return cls(
            min_turn=int(data.get("min_turn", 8)),
            required_scene_functions=list(data.get("required_scene_functions", [])),
            required_closed_promises=list(data.get("required_closed_promises", [])),
            required_tension_min=float(data.get("required_tension_min", 0.7)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class NarrativeState:
    state_id: str
    world_id: str
    turn_index: int
    story_phase: str
    chapter_index: int
    min_end_turn: int
    fate_pressure: float
    karmic_weather: Dict[str, float]
    unresolved_debts: List[str]
    world_facts: List[str]
    timeline: List[str]
    characters: Dict[str, CharacterState]
    relationship_graph: List[RelationshipEdge]
    open_promises: List[PromiseLedgerEntry]
    tension: float
    themes: Dict[str, float]
    player_intent: Dict[str, float]
    recent_scene_functions: List[str]
    visited_event_ids: List[str]
    route_fingerprint: List[str]
    rating_ceiling: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeState":
        payload = dict(data)
        payload["characters"] = {
            key: CharacterState.from_dict(value)
            for key, value in payload.get("characters", {}).items()
        }
        payload["open_promises"] = [
            PromiseLedgerEntry.from_dict(item)
            for item in payload.get("open_promises", [])
        ]
        payload["relationship_graph"] = [
            RelationshipEdge.from_dict(item)
            for item in payload.get("relationship_graph", [])
        ]
        payload.setdefault("story_phase", "setup")
        payload.setdefault("chapter_index", payload.get("turn_index", 0))
        payload.setdefault("min_end_turn", 8)
        payload.setdefault("fate_pressure", 0.0)
        payload.setdefault("karmic_weather", {})
        payload.setdefault("unresolved_debts", [])
        payload.setdefault("metadata", {})
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "world_id": self.world_id,
            "turn_index": self.turn_index,
            "story_phase": self.story_phase,
            "chapter_index": self.chapter_index,
            "min_end_turn": self.min_end_turn,
            "fate_pressure": self.fate_pressure,
            "karmic_weather": dict(self.karmic_weather),
            "unresolved_debts": list(self.unresolved_debts),
            "world_facts": list(self.world_facts),
            "timeline": list(self.timeline),
            "characters": {key: value.to_dict() for key, value in self.characters.items()},
            "relationship_graph": [edge.to_dict() for edge in self.relationship_graph],
            "open_promises": [promise.to_dict() for promise in self.open_promises],
            "tension": self.tension,
            "themes": dict(self.themes),
            "player_intent": dict(self.player_intent),
            "recent_scene_functions": list(self.recent_scene_functions),
            "visited_event_ids": list(self.visited_event_ids),
            "route_fingerprint": list(self.route_fingerprint),
            "rating_ceiling": self.rating_ceiling,
            "metadata": dict(self.metadata),
        }


@dataclass
class WorldBible:
    world_id: str
    title: str
    source_type: str
    themes: List[str]
    canon_anchors: List[str]
    forbidden_moves: List[str]
    characters: List[str]
    locations: List[str]
    creator_controls: CreatorControls = field(default_factory=CreatorControls)
    capability_assets: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldBible":
        payload = dict(data)
        payload["creator_controls"] = CreatorControls.from_dict(payload.get("creator_controls"))
        payload.setdefault("capability_assets", {})
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        data = _deepcopy_dataclass(self)
        data["creator_controls"] = self.creator_controls.to_dict()
        return data


@dataclass
class WorldRecord:
    world: WorldBible
    event_atoms: List[EventAtom]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldRecord":
        return cls(
            world=WorldBible.from_dict(data["world"]),
            event_atoms=[EventAtom.from_dict(item) for item in data.get("event_atoms", [])],
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world": self.world.to_dict(),
            "event_atoms": [event.to_dict() for event in self.event_atoms],
            "metadata": dict(self.metadata),
        }


@dataclass
class SearchWeights:
    desire_pull: float = 0.12
    shadow_pull: float = 0.14
    poison_pull: float = 0.16
    vow_pull: float = 0.12
    wound_pull: float = 0.10
    debt_pull: float = 0.12
    karma_pull: float = 0.12
    fate_pull: float = 0.08
    wisdom_resistance: float = 0.10

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SearchWeights":
        if not data:
            return cls()
        return cls(
            desire_pull=float(data.get("desire_pull", cls.desire_pull)),
            shadow_pull=float(data.get("shadow_pull", cls.shadow_pull)),
            poison_pull=float(data.get("poison_pull", cls.poison_pull)),
            vow_pull=float(data.get("vow_pull", cls.vow_pull)),
            wound_pull=float(data.get("wound_pull", cls.wound_pull)),
            debt_pull=float(data.get("debt_pull", cls.debt_pull)),
            karma_pull=float(data.get("karma_pull", cls.karma_pull)),
            fate_pull=float(data.get("fate_pull", cls.fate_pull)),
            wisdom_resistance=float(data.get("wisdom_resistance", cls.wisdom_resistance)),
        )

    def normalized(self) -> "SearchWeights":
        return SearchWeights.from_dict(self.to_dict())

    def to_dict(self) -> Dict[str, float]:
        return _deepcopy_dataclass(self)


@dataclass
class CriticDecision:
    critic_name: str
    verdict: str
    reasons: List[str]
    suggested_fix: str = ""
    score_adjustment: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriticDecision":
        return cls(
            critic_name=data["critic_name"],
            verdict=data["verdict"],
            reasons=list(data.get("reasons", [])),
            suggested_fix=data.get("suggested_fix", ""),
            score_adjustment=float(data.get("score_adjustment", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class SceneIntent:
    intent_id: str
    label: str
    description: str
    preferred_scene_functions: List[str]
    preferred_tags: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneIntent":
        return cls(
            intent_id=data["intent_id"],
            label=data["label"],
            description=data.get("description", ""),
            preferred_scene_functions=list(data.get("preferred_scene_functions", [])),
            preferred_tags=list(data.get("preferred_tags", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class SceneBeat:
    beat_index: int
    event: EventAtom
    beat_label: str
    dramatic_job: str
    tension_after: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneBeat":
        return cls(
            beat_index=int(data["beat_index"]),
            event=EventAtom.from_dict(data["event"]),
            beat_label=data.get("beat_label", ""),
            dramatic_job=data.get("dramatic_job", ""),
            tension_after=float(data.get("tension_after", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_index": self.beat_index,
            "event": self.event.to_dict(),
            "beat_label": self.beat_label,
            "dramatic_job": self.dramatic_job,
            "tension_after": self.tension_after,
        }


@dataclass
class SceneRenderSpec:
    prose_mode: str
    viewpoint_character: str
    target_word_count: int
    dialogue_density: float
    sensory_motifs: List[str]
    emotional_pivot: str
    ending_cadence: str
    must_include_beats: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneRenderSpec":
        return cls(
            prose_mode=data["prose_mode"],
            viewpoint_character=data.get("viewpoint_character", ""),
            target_word_count=int(data.get("target_word_count", 900)),
            dialogue_density=float(data.get("dialogue_density", 0.35)),
            sensory_motifs=list(data.get("sensory_motifs", [])),
            emotional_pivot=data.get("emotional_pivot", ""),
            ending_cadence=data.get("ending_cadence", ""),
            must_include_beats=list(data.get("must_include_beats", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class ChapterPlan:
    chapter_index: int
    story_phase: str
    scene_intent: SceneIntent
    beat_target: int
    beat_count: int
    ending_ready: bool
    selected_event_ids: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterPlan":
        return cls(
            chapter_index=int(data["chapter_index"]),
            story_phase=data["story_phase"],
            scene_intent=SceneIntent.from_dict(data["scene_intent"]),
            beat_target=int(data.get("beat_target", 3)),
            beat_count=int(data.get("beat_count", 0)),
            ending_ready=bool(data.get("ending_ready", False)),
            selected_event_ids=list(data.get("selected_event_ids", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "story_phase": self.story_phase,
            "scene_intent": self.scene_intent.to_dict(),
            "beat_target": self.beat_target,
            "beat_count": self.beat_count,
            "ending_ready": self.ending_ready,
            "selected_event_ids": list(self.selected_event_ids),
        }


@dataclass
class ScenePlan:
    chapter_goal: str
    scene_goal: str
    conflict_axes: List[str]
    beats: List[Dict[str, str]]
    ending_hook: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenePlan":
        return cls(
            chapter_goal=data.get("chapter_goal", ""),
            scene_goal=data.get("scene_goal", ""),
            conflict_axes=list(data.get("conflict_axes", [])),
            beats=[dict(item) for item in data.get("beats", [])],
            ending_hook=data.get("ending_hook", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class ChapterDraft:
    body: str
    paragraphs: List[str]
    dialogue_count: int
    action_count: int
    detail_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterDraft":
        return cls(
            body=data.get("body", ""),
            paragraphs=list(data.get("paragraphs", [])),
            dialogue_count=int(data.get("dialogue_count", 0)),
            action_count=int(data.get("action_count", 0)),
            detail_count=int(data.get("detail_count", 0)),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class NarrativeViewModel:
    chapter_title: str
    chapter_index: int
    recap: str
    body: str
    scene_card: Dict[str, Any]
    choices: List[str]
    relationship_hints: List[str]
    can_continue: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeViewModel":
        return cls(
            chapter_title=data["chapter_title"],
            chapter_index=int(data.get("chapter_index", 0)),
            recap=data.get("recap", ""),
            body=data.get("body", ""),
            scene_card=dict(data.get("scene_card", {})),
            choices=list(data.get("choices", [])),
            relationship_hints=list(data.get("relationship_hints", [])),
            can_continue=bool(data.get("can_continue", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class IntentPrefill:
    last_player_intent: str
    current_pressure: str
    suggested_prefill: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentPrefill":
        return cls(
            last_player_intent=data.get("last_player_intent", ""),
            current_pressure=data.get("current_pressure", ""),
            suggested_prefill=data.get("suggested_prefill", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EvaluationIssue:
    issue_code: str
    severity: str
    summary: str
    owning_module: str
    evidence: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationIssue":
        return cls(
            issue_code=data["issue_code"],
            severity=data["severity"],
            summary=data.get("summary", ""),
            owning_module=data.get("owning_module", ""),
            evidence=list(data.get("evidence", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EvaluationScores:
    readability: float
    scene_density: float
    character_fidelity: float
    causal_continuity: float
    pacing: float
    choice_distinctness: float
    hook_quality: float
    monetize_ready: float
    overall_score: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationScores":
        return cls(
            readability=float(data.get("readability", 0.0)),
            scene_density=float(data.get("scene_density", 0.0)),
            character_fidelity=float(data.get("character_fidelity", 0.0)),
            causal_continuity=float(data.get("causal_continuity", 0.0)),
            pacing=float(data.get("pacing", 0.0)),
            choice_distinctness=float(data.get("choice_distinctness", 0.0)),
            hook_quality=float(data.get("hook_quality", 0.0)),
            monetize_ready=float(data.get("monetize_ready", 0.0)),
            overall_score=float(data.get("overall_score", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EvaluationDecision:
    decision: str
    reason: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationDecision":
        return cls(
            decision=data.get("decision", "rewrite"),
            reason=data.get("reason", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class EvaluationReport:
    chapter_id: str
    world_version_id: str
    session_id: str
    decision: EvaluationDecision
    issues: List[EvaluationIssue]
    scores: EvaluationScores
    hard_validator_results: Dict[str, Any]
    summary: str
    created_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationReport":
        return cls(
            chapter_id=data["chapter_id"],
            world_version_id=data.get("world_version_id", ""),
            session_id=data.get("session_id", ""),
            decision=EvaluationDecision.from_dict(data.get("decision", {})),
            issues=[EvaluationIssue.from_dict(item) for item in data.get("issues", [])],
            scores=EvaluationScores.from_dict(data.get("scores", {})),
            hard_validator_results=dict(data.get("hard_validator_results", {})),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "world_version_id": self.world_version_id,
            "session_id": self.session_id,
            "decision": self.decision.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
            "scores": self.scores.to_dict(),
            "hard_validator_results": dict(self.hard_validator_results),
            "summary": self.summary,
            "created_at": self.created_at,
        }


@dataclass
class RenderedScene:
    event_id: str
    concise_summary: str
    interactive_scene: str
    premium_prose: str
    story_title: str = ""
    chapter_summary: str = ""
    pull_quote: str = ""
    story_beats: List[str] = field(default_factory=list)
    visual_details: List[str] = field(default_factory=list)
    visual_prompt: str = ""
    image_caption: str = ""
    image_motif: str = ""
    palette_hint: str = ""
    debug: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderedScene":
        return cls(
            event_id=data["event_id"],
            concise_summary=data["concise_summary"],
            interactive_scene=data["interactive_scene"],
            premium_prose=data["premium_prose"],
            story_title=data.get("story_title", ""),
            chapter_summary=data.get("chapter_summary", ""),
            pull_quote=data.get("pull_quote", ""),
            story_beats=list(data.get("story_beats", [])),
            visual_details=list(data.get("visual_details", [])),
            visual_prompt=data.get("visual_prompt", ""),
            image_caption=data.get("image_caption", ""),
            image_motif=data.get("image_motif", ""),
            palette_hint=data.get("palette_hint", ""),
            debug=dict(data.get("debug", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy_dataclass(self)


@dataclass
class CandidateBatch:
    raw_candidates: List[EventAtom]
    legal_candidates: List[EventAtom]
    illegal_candidate_reasons: Dict[str, List[str]]
    debug: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateBatch":
        return cls(
            raw_candidates=[EventAtom.from_dict(item) for item in data.get("raw_candidates", [])],
            legal_candidates=[EventAtom.from_dict(item) for item in data.get("legal_candidates", [])],
            illegal_candidate_reasons={
                key: list(value)
                for key, value in data.get("illegal_candidate_reasons", {}).items()
            },
            debug=dict(data.get("debug", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_candidates": [event.to_dict() for event in self.raw_candidates],
            "legal_candidates": [event.to_dict() for event in self.legal_candidates],
            "illegal_candidate_reasons": {
                key: list(value) for key, value in self.illegal_candidate_reasons.items()
            },
            "debug": dict(self.debug),
        }


@dataclass
class ScoredCandidate:
    event: EventAtom
    total_score: float
    components: Dict[str, float]
    explanation: str
    critic_decisions: List[CriticDecision] = field(default_factory=list)
    critic_penalty: float = 0.0
    provider_debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "total_score": self.total_score,
            "components": dict(self.components),
            "explanation": self.explanation,
            "critic_decisions": [decision.to_dict() for decision in self.critic_decisions],
            "critic_penalty": self.critic_penalty,
            "provider_debug": dict(self.provider_debug),
        }


@dataclass
class RouteCandidate:
    events: List[EventAtom]
    total_score: float
    score_breakdown: Dict[str, float]
    critic_trace: List[Dict[str, Any]]
    explanation: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteCandidate":
        return cls(
            events=[EventAtom.from_dict(item) for item in data.get("events", [])],
            total_score=float(data["total_score"]),
            score_breakdown={key: float(value) for key, value in data.get("score_breakdown", {}).items()},
            critic_trace=[dict(item) for item in data.get("critic_trace", [])],
            explanation=data.get("explanation", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "event_ids": [event.event_id for event in self.events],
            "total_score": self.total_score,
            "score_breakdown": dict(self.score_breakdown),
            "critic_trace": [dict(item) for item in self.critic_trace],
            "explanation": self.explanation,
        }


@dataclass
class SessionRecord:
    session_id: str
    world_id: str
    player_profile: Dict[str, Any]
    initial_state: NarrativeState
    current_state: NarrativeState
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionRecord":
        return cls(
            session_id=data["session_id"],
            world_id=data["world_id"],
            player_profile=dict(data.get("player_profile", {})),
            initial_state=NarrativeState.from_dict(data["initial_state"]),
            current_state=NarrativeState.from_dict(data["current_state"]),
            created_at=data.get("created_at", ""),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "world_id": self.world_id,
            "player_profile": dict(self.player_profile),
            "initial_state": self.initial_state.to_dict(),
            "current_state": self.current_state.to_dict(),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class StepRecord:
    session_id: str
    step_index: int
    player_input: str
    intent_vector: Dict[str, float]
    candidate_batch: CandidateBatch
    scored_candidates: List[ScoredCandidate]
    routes: List[RouteCandidate]
    chosen_event: Optional[EventAtom]
    chapter_plan: Optional[ChapterPlan]
    scene_beats: List[SceneBeat]
    scene_render_spec: Optional[SceneRenderSpec]
    rendered_scene: Optional[RenderedScene]
    reader_view: Optional[NarrativeViewModel]
    state_before: NarrativeState
    state_after: NarrativeState
    critic_trace: List[Dict[str, Any]]
    promise_ledger_snapshot: List[PromiseLedgerEntry]
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepRecord":
        return cls(
            session_id=data["session_id"],
            step_index=int(data["step_index"]),
            player_input=data.get("player_input", ""),
            intent_vector={
                key: float(value) for key, value in data.get("intent_vector", {}).items()
            },
            candidate_batch=CandidateBatch.from_dict(data["candidate_batch"]),
            scored_candidates=[
                ScoredCandidate(
                    event=EventAtom.from_dict(item["event"]),
                    total_score=float(item["total_score"]),
                    components={key: float(value) for key, value in item.get("components", {}).items()},
                    explanation=item.get("explanation", ""),
                    critic_decisions=[
                        CriticDecision.from_dict(decision)
                        for decision in item.get("critic_decisions", [])
                    ],
                    critic_penalty=float(item.get("critic_penalty", 0.0)),
                    provider_debug=dict(item.get("provider_debug", {})),
                )
                for item in data.get("scored_candidates", [])
            ],
            routes=[RouteCandidate.from_dict(item) for item in data.get("routes", [])],
            chosen_event=EventAtom.from_dict(data["chosen_event"]) if data.get("chosen_event") else None,
            chapter_plan=ChapterPlan.from_dict(data["chapter_plan"]) if data.get("chapter_plan") else None,
            scene_beats=[SceneBeat.from_dict(item) for item in data.get("scene_beats", [])],
            scene_render_spec=SceneRenderSpec.from_dict(data["scene_render_spec"]) if data.get("scene_render_spec") else None,
            rendered_scene=RenderedScene.from_dict(data["rendered_scene"]) if data.get("rendered_scene") else None,
            reader_view=NarrativeViewModel.from_dict(data["reader_view"]) if data.get("reader_view") else None,
            state_before=NarrativeState.from_dict(data["state_before"]),
            state_after=NarrativeState.from_dict(data["state_after"]),
            critic_trace=[dict(item) for item in data.get("critic_trace", [])],
            promise_ledger_snapshot=[
                PromiseLedgerEntry.from_dict(item)
                for item in data.get("promise_ledger_snapshot", [])
            ],
            created_at=data.get("created_at", ""),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "step_index": self.step_index,
            "player_input": self.player_input,
            "intent_vector": dict(self.intent_vector),
            "candidate_batch": self.candidate_batch.to_dict(),
            "scored_candidates": [candidate.to_dict() for candidate in self.scored_candidates],
            "routes": [route.to_dict() for route in self.routes],
            "chosen_event": self.chosen_event.to_dict() if self.chosen_event else None,
            "chapter_plan": self.chapter_plan.to_dict() if self.chapter_plan else None,
            "scene_beats": [beat.to_dict() for beat in self.scene_beats],
            "scene_render_spec": self.scene_render_spec.to_dict() if self.scene_render_spec else None,
            "rendered_scene": self.rendered_scene.to_dict() if self.rendered_scene else None,
            "reader_view": self.reader_view.to_dict() if self.reader_view else None,
            "state_before": self.state_before.to_dict(),
            "state_after": self.state_after.to_dict(),
            "critic_trace": [dict(item) for item in self.critic_trace],
            "promise_ledger_snapshot": [
                promise.to_dict() for promise in self.promise_ledger_snapshot
            ],
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


def rating_allowed(state_or_rating: str, event_rating: str) -> bool:
    ceiling = RATINGS_ORDER.get(state_or_rating, RATINGS_ORDER["R"])
    return RATINGS_ORDER.get(event_rating, RATINGS_ORDER["R"]) <= ceiling
