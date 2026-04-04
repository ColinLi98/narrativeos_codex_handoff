from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Protocol


def _asdict(instance: Any) -> Dict[str, Any]:
    return asdict(instance)


@dataclass
class VoiceProfile:
    profile_id: str = "default"
    cadence: str = "measured"
    directness: float = 0.5
    bluntness: float = 0.5
    restraint: float = 0.5
    social_rank_awareness: float = 0.5
    hesitation_style: str = ""
    direct_address_style: str = ""
    opening_style: List[str] = field(default_factory=list)
    pressure_style: List[str] = field(default_factory=list)
    pivot_style: List[str] = field(default_factory=list)
    aftermath_style: List[str] = field(default_factory=list)
    echo_style: List[str] = field(default_factory=list)
    signature_openings: List[str] = field(default_factory=list)
    signature_replies: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "VoiceProfile":
        payload = dict(data or {})
        return cls(
            profile_id=payload.get("profile_id", "default"),
            cadence=payload.get("cadence", "measured"),
            directness=float(payload.get("directness", 0.5)),
            bluntness=float(payload.get("bluntness", 0.5)),
            restraint=float(payload.get("restraint", 0.5)),
            social_rank_awareness=float(payload.get("social_rank_awareness", 0.5)),
            hesitation_style=payload.get("hesitation_style", ""),
            direct_address_style=payload.get("direct_address_style", ""),
            opening_style=list(payload.get("opening_style", [])),
            pressure_style=list(payload.get("pressure_style", [])),
            pivot_style=list(payload.get("pivot_style", [])),
            aftermath_style=list(payload.get("aftermath_style", [])),
            echo_style=list(payload.get("echo_style", [])),
            signature_openings=list(payload.get("signature_openings", [])),
            signature_replies=list(payload.get("signature_replies", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class ResponseCadenceProfile:
    cadence_id: str = "default"
    reaction_tempo: str = "measured"
    pause_style: str = ""
    reaction_style: str = ""
    reply_timing: str = ""
    interruption_style: str = ""
    reaction_lines: Dict[str, List[str]] = field(default_factory=dict)
    reply_lines: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "ResponseCadenceProfile":
        payload = dict(data or {})
        return cls(
            cadence_id=payload.get("cadence_id", "default"),
            reaction_tempo=payload.get("reaction_tempo", "measured"),
            pause_style=payload.get("pause_style", ""),
            reaction_style=payload.get("reaction_style", ""),
            reply_timing=payload.get("reply_timing", ""),
            interruption_style=payload.get("interruption_style", ""),
            reaction_lines={key: list(value) for key, value in payload.get("reaction_lines", {}).items()},
            reply_lines={key: list(value) for key, value in payload.get("reply_lines", {}).items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class PressureResponseStyle:
    style_id: str = "default"
    under_pressure: str = ""
    when_cornered: str = ""
    when_softening: str = ""
    when_deflecting: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "PressureResponseStyle":
        payload = dict(data or {})
        return cls(
            style_id=payload.get("style_id", "default"),
            under_pressure=payload.get("under_pressure", ""),
            when_cornered=payload.get("when_cornered", ""),
            when_softening=payload.get("when_softening", ""),
            when_deflecting=payload.get("when_deflecting", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class DialogueRealismPolicy:
    policy_id: str = "default"
    require_turn_taking: bool = True
    require_counter_reaction: bool = True
    min_turns: int = 2
    max_turns: int = 3
    turn_pattern: List[str] = field(default_factory=lambda: ["speaker", "reaction", "reply"])
    minimum_exchanges: int = 1
    voice_profiles: Dict[str, VoiceProfile] = field(default_factory=dict)
    response_profiles: Dict[str, ResponseCadenceProfile] = field(default_factory=dict)
    pressure_styles: Dict[str, PressureResponseStyle] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "DialogueRealismPolicy":
        payload = dict(data or {})
        return cls(
            policy_id=payload.get("policy_id", "default"),
            require_turn_taking=bool(payload.get("require_turn_taking", True)),
            require_counter_reaction=bool(payload.get("require_counter_reaction", True)),
            min_turns=int(payload.get("min_turns", 2)),
            max_turns=int(payload.get("max_turns", 3)),
            turn_pattern=list(payload.get("turn_pattern", ["speaker", "reaction", "reply"])),
            minimum_exchanges=int(payload.get("minimum_exchanges", 1)),
            voice_profiles={key: VoiceProfile.from_dict(value) for key, value in payload.get("voice_profiles", {}).items()},
            response_profiles={key: ResponseCadenceProfile.from_dict(value) for key, value in payload.get("response_profiles", {}).items()},
            pressure_styles={key: PressureResponseStyle.from_dict(value) for key, value in payload.get("pressure_styles", {}).items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        data = _asdict(self)
        data["voice_profiles"] = {key: value.to_dict() for key, value in self.voice_profiles.items()}
        data["response_profiles"] = {key: value.to_dict() for key, value in self.response_profiles.items()}
        data["pressure_styles"] = {key: value.to_dict() for key, value in self.pressure_styles.items()}
        return data


@dataclass
class EmotionActionPolicy:
    policy_id: str = "default"
    action_map: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "EmotionActionPolicy":
        payload = dict(data or {})
        return cls(
            policy_id=payload.get("policy_id", "default"),
            action_map={
                key: {slot: list(values) for slot, values in slot_map.items()}
                for key, slot_map in payload.get("action_map", {}).items()
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class SensoryGroundingPolicy:
    policy_id: str = "default"
    location_slots: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    generic_slots: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "SensoryGroundingPolicy":
        payload = dict(data or {})
        return cls(
            policy_id=payload.get("policy_id", "default"),
            location_slots={
                key: {slot: list(values) for slot, values in slot_map.items()}
                for key, slot_map in payload.get("location_slots", {}).items()
            },
            generic_slots={key: list(values) for key, values in payload.get("generic_slots", {}).items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class SceneRealizationContract:
    contract_id: str = "default"
    dialogue_policy_id: str = "default"
    default_voice_profile_id: str = "default"
    default_cadence_id: str = "default"
    default_pressure_style_id: str = "default"
    default_emotion_action_policy_id: str = "default"
    default_sensory_policy_id: str = "default"
    narrative_style_pack_id: str = "default"
    scene_openings: Dict[str, List[str]] = field(default_factory=dict)
    scene_hooks: Dict[str, List[str]] = field(default_factory=dict)
    scene_pressures: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "SceneRealizationContract":
        payload = dict(data or {})
        return cls(
            contract_id=payload.get("contract_id", "default"),
            dialogue_policy_id=payload.get("dialogue_policy_id", "default"),
            default_voice_profile_id=payload.get("default_voice_profile_id", "default"),
            default_cadence_id=payload.get("default_cadence_id", "default"),
            default_pressure_style_id=payload.get("default_pressure_style_id", "default"),
            default_emotion_action_policy_id=payload.get("default_emotion_action_policy_id", "default"),
            default_sensory_policy_id=payload.get("default_sensory_policy_id", "default"),
            narrative_style_pack_id=payload.get("narrative_style_pack_id", "default"),
            scene_openings={key: list(values) for key, values in payload.get("scene_openings", {}).items()},
            scene_hooks={key: list(values) for key, values in payload.get("scene_hooks", {}).items()},
            scene_pressures={key: list(values) for key, values in payload.get("scene_pressures", {}).items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class WorldNarrativeStylePack:
    style_pack_id: str = "default"
    tonal_lexicon: List[str] = field(default_factory=list)
    thematic_axis_labels: Dict[str, str] = field(default_factory=dict)
    hook_templates: List[str] = field(default_factory=list)
    dialogue: DialogueRealismPolicy = field(default_factory=DialogueRealismPolicy)
    emotion_actions: EmotionActionPolicy = field(default_factory=EmotionActionPolicy)
    sensory_grounding: SensoryGroundingPolicy = field(default_factory=SensoryGroundingPolicy)
    scene_realization: SceneRealizationContract = field(default_factory=SceneRealizationContract)
    goal_labels: Dict[str, str] = field(default_factory=dict)
    tag_labels: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "WorldNarrativeStylePack":
        payload = dict(data or {})
        return cls(
            style_pack_id=payload.get("style_pack_id", "default"),
            tonal_lexicon=list(payload.get("tonal_lexicon", [])),
            thematic_axis_labels=dict(payload.get("thematic_axis_labels", {})),
            hook_templates=list(payload.get("hook_templates", [])),
            dialogue=DialogueRealismPolicy.from_dict(payload.get("dialogue")),
            emotion_actions=EmotionActionPolicy.from_dict(payload.get("emotion_actions")),
            sensory_grounding=SensoryGroundingPolicy.from_dict(payload.get("sensory_grounding")),
            scene_realization=SceneRealizationContract.from_dict(payload.get("scene_realization")),
            goal_labels=dict(payload.get("goal_labels", {})),
            tag_labels=dict(payload.get("tag_labels", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = _asdict(self)
        data["dialogue"] = self.dialogue.to_dict()
        data["emotion_actions"] = self.emotion_actions.to_dict()
        data["sensory_grounding"] = self.sensory_grounding.to_dict()
        data["scene_realization"] = self.scene_realization.to_dict()
        return data


def style_pack_from_world(world: Any) -> WorldNarrativeStylePack:
    capability_assets = getattr(world, "capability_assets", {}) or {}
    if capability_assets.get("narrative_style_pack"):
        return WorldNarrativeStylePack.from_dict(capability_assets["narrative_style_pack"])
    metadata = getattr(getattr(world, "creator_controls", None), "metadata", {}) or {}
    if metadata.get("narrative_style_pack"):
        return WorldNarrativeStylePack.from_dict(metadata["narrative_style_pack"])
    return WorldNarrativeStylePack()


class CharacterReasoner(Protocol):
    def reason(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        ...


class CausalMemory(Protocol):
    def update(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        ...


class PlotPlanner(Protocol):
    def plan(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        ...


class ChoiceGenerator(Protocol):
    def generate_choices(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        ...


class ProseWriter(Protocol):
    def write(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        ...


class NarrativeJudge(Protocol):
    def evaluate(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        ...
