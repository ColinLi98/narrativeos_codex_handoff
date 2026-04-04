from __future__ import annotations

from typing import Iterable, List, Optional

from .models import CharacterState, EventAtom, NarrativeState
from .scene_functions import is_terminal_scene_function


def _tokenize(parts: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in str(part).lower().replace("-", "_").replace(" ", "_").split("_"):
            if token:
                tokens.add(token)
    return tokens


def destiny_alignment(character: CharacterState, state: NarrativeState, event: EventAtom) -> float:
    destiny_tokens = _tokenize(
        [character.destiny.life_theme]
        + character.destiny.inescapable_nodes
        + character.destiny.fated_relations
        + character.destiny.forbidden_escape
        + character.destiny.endgame_shapes
    )
    event_tokens = _tokenize(
        event.tags
        + event.awakening_affordances
        + event.vow_tests
        + event.wound_triggers
        + event.world_fact_deltas_add
        + [event.summary, event.title, event.scene_function]
    )
    if not destiny_tokens or not event_tokens:
        return 0.0
    return float(len(destiny_tokens & event_tokens)) / float(len(destiny_tokens | event_tokens))


def update_fate_pressure(state: NarrativeState, event: EventAtom) -> NarrativeState:
    charge = sum(seed.charge for character in state.characters.values() for seed in character.karmic_seeds if seed.status == "ripening")
    pressure = (
        0.45 * state.tension
        + 0.15 * event.concealment_level
        + 0.10 * max(state.karmic_weather.values(), default=0.0)
        + 0.06 * charge
    )
    if is_terminal_scene_function(event.scene_function, event.metadata):
        pressure += 0.1
    state.fate_pressure = round(min(1.0, pressure), 3)
    return state


def endgame_shape_for_event(event: EventAtom) -> str:
    return str(event.metadata.get("endgame_shape", ""))


def endgame_gate_errors(state: NarrativeState, event: EventAtom) -> List[str]:
    if not is_terminal_scene_function(event.scene_function, event.metadata):
        return []
    errors: List[str] = []
    shape = endgame_shape_for_event(event)
    if state.chapter_index < state.min_end_turn:
        errors.append("fate_min_end_turn")
    if state.fate_pressure < float(event.metadata.get("required_fate_pressure", 0.45)):
        errors.append("fate_pressure_too_low")
    if not shape:
        errors.append("missing_endgame_shape")
    active_shapes = {
        desired_shape
        for character in state.characters.values()
        for desired_shape in character.destiny.endgame_shapes
    }
    if shape and shape not in active_shapes:
        errors.append("endgame_shape_not_permitted")
    required_nodes = list(event.metadata.get("required_inescapable_nodes", []))
    if required_nodes:
        visited = set(state.world_facts) | set(state.timeline) | set(state.metadata.get("scene_history", []))
        if any(node not in visited for node in required_nodes):
            errors.append("inescapable_nodes_incomplete")
    return errors
