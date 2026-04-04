from __future__ import annotations

from typing import Iterable, List

from .models import CharacterState, EventAtom, NarrativeState
from .relationship_graph import relation_pressure_for_actor


def _tokenize(parts: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in str(part).lower().replace("-", "_").replace(" ", "_").split("_"):
            if token:
                tokens.add(token)
    return tokens


def _overlap(a: Iterable[str], b: Iterable[str]) -> float:
    left = _tokenize(a)
    right = _tokenize(b)
    if not left or not right:
        return 0.0
    return float(len(left & right)) / float(len(left | right))


def surface_goal_alignment(character: CharacterState, state: NarrativeState, event: EventAtom) -> float:
    active_intents = [
        key
        for key, value in state.player_intent.items()
        if value >= 0.5
    ]
    return _overlap(
        character.public_goals + active_intents,
        event.tags + event.agency_affordances + event.vow_tests + [event.summary],
    )


def shadow_desire_alignment(character: CharacterState, event: EventAtom) -> float:
    probes = character.hidden_goals + [character.wound.shadow_desire, character.wound.public_self]
    return _overlap(probes, event.tags + event.wound_triggers + event.awakening_affordances + [event.summary])


def poison_activation_score(character: CharacterState, state: NarrativeState, event: EventAtom) -> float:
    baseline = (
        character.poisons.greed
        + character.poisons.anger
        + character.poisons.delusion
        + character.poisons.pride
        + character.poisons.doubt
    ) / 5.0
    activation = sum(
        float(event.temptation_vector.get(key, 0.0))
        for key in ("greed", "anger", "delusion", "pride", "doubt")
    ) / 5.0
    stress_multiplier = 1.0 + 0.4 * state.tension
    clarity_offset = 0.35 * character.awakening.clarity
    return max(0.0, min(1.0, baseline * 0.6 + activation * stress_multiplier - clarity_offset))


def vow_alignment(character: CharacterState, event: EventAtom) -> float:
    overlap = _overlap(character.vows.vows, event.vow_tests + event.awakening_affordances + event.tags)
    return min(1.0, overlap * (0.65 + 0.2 * character.vows.sacrifice_capacity + 0.15 * character.vows.truth_tolerance))


def wound_trigger_score(character: CharacterState, event: EventAtom) -> float:
    return _overlap(
        [character.wound.core_wound, character.wound.defense_style, character.wound.public_self],
        event.wound_triggers + event.tags + [event.summary],
    )


def debt_pressure_score(character: CharacterState, state: NarrativeState, event: EventAtom) -> float:
    actor_id = actor_id_for_character(state, character)
    counterpart_ids = [counterpart_id for counterpart_id in event.actors if counterpart_id != actor_id]
    debt_load = sum(debt.magnitude for debt in character.debts)
    graph_load = relation_pressure_for_actor(state, actor_id, counterpart_ids)
    return min(1.0, 0.25 * debt_load + graph_load)


def ripening_seed_pressure(character: CharacterState, state: NarrativeState, event: EventAtom) -> float:
    active = [
        seed
        for seed in character.karmic_seeds
        if seed.status in {"dormant", "ripening"}
    ]
    if not active:
        return 0.0
    probes = set(event.tags + event.awakening_affordances + [event.scene_function] + state.world_facts)
    hits = 0.0
    for seed in active:
        if set(seed.ripening_conditions) & probes:
            hits += seed.charge
        elif seed.status == "ripening":
            hits += 0.5 * seed.charge
    return min(1.0, hits / float(max(len(active), 1)))


def awakening_resistance(character: CharacterState, event: EventAtom) -> float:
    if event.awakening_affordances:
        exposure = 1.0 - min(1.0, 0.55 * character.awakening.clarity + 0.45 * character.awakening.reflection_capacity)
        if set(event.awakening_affordances) & set(character.awakening.transformation_paths):
            exposure *= max(0.2, character.awakening.repentance_threshold)
        return min(1.0, exposure)
    return min(1.0, 1.0 - character.awakening.clarity)


def choice_score(character: CharacterState, state: NarrativeState, event: EventAtom, *, fate_pull: float) -> dict[str, float]:
    desire_pull = surface_goal_alignment(character, state, event)
    shadow_pull = shadow_desire_alignment(character, event)
    poison_pull = poison_activation_score(character, state, event)
    vow_pull = vow_alignment(character, event)
    wound_pull = wound_trigger_score(character, event)
    debt_pull = debt_pressure_score(character, state, event)
    karma_pull = ripening_seed_pressure(character, state, event)
    wisdom_resistance = awakening_resistance(character, event)
    total = (
        0.12 * desire_pull
        + 0.14 * shadow_pull
        + 0.16 * poison_pull
        + 0.12 * vow_pull
        + 0.10 * wound_pull
        + 0.12 * debt_pull
        + 0.12 * karma_pull
        + 0.08 * fate_pull
        - 0.10 * wisdom_resistance
    )
    return {
        "desire_pull": desire_pull,
        "shadow_pull": shadow_pull,
        "poison_pull": poison_pull,
        "vow_pull": vow_pull,
        "wound_pull": wound_pull,
        "debt_pull": debt_pull,
        "karma_pull": karma_pull,
        "fate_pull": fate_pull,
        "wisdom_resistance": wisdom_resistance,
        "character_fidelity": max(0.0, min(1.0, total + wisdom_resistance * 0.10)),
        "choice_total": max(0.0, min(1.0, total)),
    }


def actor_id_for_character(state: NarrativeState, character: CharacterState) -> str:
    for actor_id, current in state.characters.items():
        if current is character:
            return actor_id
    return ""
