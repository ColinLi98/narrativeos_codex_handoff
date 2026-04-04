from __future__ import annotations

from typing import List, Optional, Sequence, Set

from .fate import endgame_gate_errors
from .models import EndingGate, EventAtom, NarrativeState, PromiseLedgerEntry, WorldBible, rating_allowed
from .scene_functions import is_terminal_scene_function, normalize_scene_function


def _normalize_text(parts: Sequence[str]) -> str:
    return " ".join(part.lower() for part in parts if part)


def effective_rating_ceiling(state: NarrativeState, world: Optional[WorldBible] = None) -> str:
    candidates = [state.rating_ceiling]
    if world is not None and world.creator_controls.darkness_ceiling:
        candidates.append(world.creator_controls.darkness_ceiling)
    return min(candidates, key=lambda rating: ["G", "PG", "PG13", "R"].index(rating))


def _promise_ids(promises: Sequence[PromiseLedgerEntry]) -> Set[str]:
    return {promise.promise_id for promise in promises}


def _ending_gate_for_event(state: NarrativeState, event: EventAtom) -> EndingGate:
    if not is_terminal_scene_function(event.scene_function, event.metadata):
        return EndingGate(min_turn=state.min_end_turn)
    gate_data = dict(event.metadata.get("ending_gate", {}))
    gate_data.setdefault("min_turn", state.min_end_turn)
    return EndingGate.from_dict(gate_data)


def _matches_forbidden_move(event: EventAtom, forbidden_move: str) -> bool:
    normalized_move = forbidden_move.lower()
    normalized_event = _normalize_text(
        list(event.tags)
        + list(event.agency_affordances)
        + list(event.world_fact_deltas_add)
        + list(event.world_fact_deltas_remove)
        + [event.title, event.summary, event.scene_function, event.location, event.convergence_key]
    )

    keyword_groups = (
        ("超自然", ("supernatural", "magic", "immortal", "divine")),
        ("圆满结局", ("perfect_ending", "happily_ever_after")),
        ("重大代价", ("costless", "free_win", "instant_redemption")),
    )
    for marker, keywords in keyword_groups:
        if marker in normalized_move and any(keyword in normalized_event for keyword in keywords):
            return True

    if "不能跳过重大代价直接进入圆满结局" in normalized_move:
        if is_terminal_scene_function(event.scene_function, event.metadata) and "sacrifice" not in event.tags and "cost" not in normalized_event:
            return True
    return False


def hard_constraint_errors(
    state: NarrativeState,
    event: EventAtom,
    world: Optional[WorldBible] = None,
) -> List[str]:
    errors: List[str] = []
    facts = set(state.world_facts)

    missing = [fact for fact in event.preconditions_all if fact not in facts]
    if missing:
        errors.append(f"missing_preconditions:{','.join(sorted(missing))}")

    violated = [fact for fact in event.forbidden_if_any if fact in facts]
    if violated:
        errors.append(f"forbidden_facts_present:{','.join(sorted(violated))}")

    missing_characters = [actor for actor in event.actors if actor not in state.characters]
    if missing_characters:
        errors.append(f"missing_characters:{','.join(sorted(missing_characters))}")

    if world is not None:
        world_missing = [actor for actor in event.actors if actor not in world.characters]
        if world_missing:
            errors.append(f"actors_not_in_world:{','.join(sorted(world_missing))}")

    ceiling = effective_rating_ceiling(state, world=world)
    if not rating_allowed(ceiling, event.rating_ceiling):
        errors.append(f"rating_exceeds_ceiling:{event.rating_ceiling}>{ceiling}")

    for character_id, updates in event.belief_updates.items():
        if character_id not in state.characters:
            errors.append(f"belief_update_unknown_character:{character_id}")
            continue
        if character_id not in event.actors:
            errors.append(f"belief_update_non_actor:{character_id}")

    for delta in event.trust_deltas:
        if delta.source not in state.characters or delta.target not in state.characters:
            errors.append(f"trust_delta_unknown_character:{delta.source}->{delta.target}")

    for delta in event.emotion_deltas:
        if delta.character not in state.characters:
            errors.append(f"emotion_delta_unknown_character:{delta.character}")

    existing_promise_ids = _promise_ids(state.open_promises)
    opened_promise_ids = _promise_ids(event.promises_open)
    unknown_closed_promises = sorted(
        promise_id
        for promise_id in event.promises_close
        if promise_id not in existing_promise_ids
        and promise_id not in opened_promise_ids
        and promise_id not in set(state.metadata.get("closed_promise_ids", []))
    )
    if unknown_closed_promises:
        errors.append(
            f"closing_unknown_promise:{','.join(unknown_closed_promises)}"
        )

    duplicate_opened_promises = sorted(existing_promise_ids & opened_promise_ids)
    if duplicate_opened_promises:
        errors.append(
            f"duplicate_open_promises:{','.join(duplicate_opened_promises)}"
        )

    if len(state.recent_scene_functions) >= 2:
        window = [normalize_scene_function(scene_function) for scene_function in state.recent_scene_functions[-2:]]
        if all(scene_function == normalize_scene_function(event.scene_function) for scene_function in window):
            errors.append(f"scene_function_window_repeat:{event.scene_function}")

    if world is not None:
        forbidden_hits = [
            forbidden_move
            for forbidden_move in world.forbidden_moves
            if _matches_forbidden_move(event, forbidden_move)
        ]
        if forbidden_hits:
            errors.append(f"forbidden_move_match:{' | '.join(forbidden_hits)}")

    if is_terminal_scene_function(event.scene_function, event.metadata):
        gate = _ending_gate_for_event(state, event)
        if state.chapter_index < max(6, gate.min_turn):
            errors.append(f"ending_gate_min_turn:{state.chapter_index}<{max(6, gate.min_turn)}")
        scene_history = set(state.metadata.get("scene_history", []))
        missing_scene_functions = [
            scene_function
            for scene_function in gate.required_scene_functions
            if scene_function not in scene_history
        ]
        if missing_scene_functions:
            errors.append(
                "ending_gate_missing_scene_functions:%s" % ",".join(sorted(missing_scene_functions))
            )
        closed_promise_ids = set(state.metadata.get("closed_promise_ids", []))
        missing_promises = [
            promise_id
            for promise_id in gate.required_closed_promises
            if promise_id not in closed_promise_ids
        ]
        if missing_promises:
            errors.append(
                "ending_gate_missing_closed_promises:%s" % ",".join(sorted(missing_promises))
            )
        if state.tension < gate.required_tension_min:
            errors.append(
                "ending_gate_tension_too_low:%.2f<%.2f" % (state.tension, gate.required_tension_min)
            )
        errors.extend(endgame_gate_errors(state, event))

    return errors


def is_event_legal(
    state: NarrativeState,
    event: EventAtom,
    world: Optional[WorldBible] = None,
) -> bool:
    return len(hard_constraint_errors(state, event, world=world)) == 0
