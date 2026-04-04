from __future__ import annotations

from typing import Dict, List, Optional

from .fate import update_fate_pressure
from .karma import compute_karmic_weather, create_karmic_seeds, resolve_or_transform_seeds, ripen_karmic_seeds
from .models import EventAtom, NarrativeState, PromiseLedgerEntry
from .relationship_graph import apply_debt_deltas, sync_character_debts, unresolved_debt_keys
from .scene_functions import normalize_scene_function


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _merge_unique(items: List[str], new_items: List[str]) -> List[str]:
    seen = set(items)
    merged = list(items)
    for item in new_items:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _normalize_promise_turns(
    promise: PromiseLedgerEntry,
    *,
    turn_index: int,
) -> PromiseLedgerEntry:
    normalized = PromiseLedgerEntry.from_dict(promise.to_dict())
    if normalized.opened_at_turn <= 0:
        normalized.opened_at_turn = turn_index
    if normalized.due_by_turn <= normalized.opened_at_turn:
        normalized.due_by_turn = normalized.opened_at_turn + 2
    if normalized.status != "open":
        normalized.status = "open"
    return normalized


def _metadata_list(state: NarrativeState, key: str) -> List[Dict[str, object]]:
    return [dict(item) for item in state.metadata.get(key, [])]


def _persist_thread_metadata(state: NarrativeState, key: str, items: List[Dict[str, object]], *, limit: int = 12) -> None:
    state.metadata[key] = items[-limit:]


def _link_overlap(left: Dict[str, object], right: Dict[str, object]) -> bool:
    left_actors = set(left.get("actors", []))
    right_actors = set(right.get("actors", []))
    if left_actors & right_actors:
        return True
    left_seed = left.get("seed_tag")
    right_seed = right.get("seed_tag")
    return bool(left_seed and right_seed and left_seed == right_seed)


def _cross_pressure_key(thread: Dict[str, object], consequence: Dict[str, object]) -> str:
    thread_focus = str(thread.get("focus", "thread"))
    consequence_focus = str(consequence.get("focus", "consequence"))
    actor_part = "-".join(sorted(set(thread.get("actors", [])) | set(consequence.get("actors", []))))
    return "%s::%s::%s" % (thread_focus, consequence_focus, actor_part)


def determine_story_phase(chapter_index: int) -> str:
    if chapter_index <= 2:
        return "setup"
    if chapter_index <= 4:
        return "early_rising"
    if chapter_index <= 6:
        return "midpoint"
    if chapter_index <= 9:
        return "crisis"
    if chapter_index <= 12:
        return "climax"
    return "aftermath"


def update_scene_history(state: NarrativeState, scene_intent_id: Optional[str] = None) -> NarrativeState:
    scene_history = list(state.metadata.get("scene_history", []))
    scene_history.extend(state.recent_scene_functions[-1:])
    state.metadata["scene_history"] = scene_history
    if scene_intent_id:
        intent_history = list(state.metadata.get("scene_intent_history", []))
        intent_history.append(scene_intent_id)
        state.metadata["scene_intent_history"] = intent_history
    return state


def aging_open_promises(state: NarrativeState) -> NarrativeState:
    pressure: Dict[str, float] = {}
    for promise in state.open_promises:
        horizon = max(1, promise.due_by_turn - promise.opened_at_turn)
        elapsed = max(0, state.chapter_index - promise.opened_at_turn)
        pressure[promise.promise_id] = round(min(1.0, elapsed / horizon), 3)
    state.metadata["promise_pressure_map"] = pressure
    return state


def update_payoff_pressure(state: NarrativeState) -> NarrativeState:
    promise_pressure = state.metadata.get("promise_pressure_map", {})
    cross_pressure = [
        min(1.0, 0.18 * int(item.get("intensity", 1)))
        for item in state.metadata.get("cross_pressure_threads", [])
        if item.get("status") in {"open", "reopened", "echoing"}
    ]
    state.metadata["payoff_pressure"] = max(
        [*promise_pressure.values(), *cross_pressure],
        default=0.0,
    )
    return state


def update_character_private_memory(state: NarrativeState) -> NarrativeState:
    for character in state.characters.values():
        character.beliefs_true = list(dict.fromkeys(character.beliefs_true))
        character.beliefs_false = list(dict.fromkeys(character.beliefs_false))
    return state


def _apply_poison_activation(state: NarrativeState, event: EventAtom) -> NarrativeState:
    for actor_id in event.actors:
        character = state.characters.get(actor_id)
        if character is None:
            continue
        for poison_name, delta in event.temptation_vector.items():
            if not hasattr(character.poisons, poison_name):
                continue
            current = float(getattr(character.poisons, poison_name))
            stress_multiplier = 1.0 + 0.35 * state.tension
            if character.wound.core_wound and character.wound.core_wound in event.wound_triggers:
                stress_multiplier += 0.2
            setattr(character.poisons, poison_name, _clamp(current + float(delta) * stress_multiplier))
        if event.awakening_affordances:
            character.awakening.clarity = _clamp(
                character.awakening.clarity + 0.08 * len(event.awakening_affordances)
            )
            character.awakening.reflection_capacity = _clamp(
                character.awakening.reflection_capacity + 0.05 * len(event.awakening_affordances)
            )
            character.poisons.delusion = _clamp(
                character.poisons.delusion - 0.06 * len(event.awakening_affordances)
            )
            character.poisons.doubt = _clamp(
                character.poisons.doubt - 0.04 * len(event.awakening_affordances)
            )
    return state


def refresh_karma_derivatives(state: NarrativeState) -> NarrativeState:
    misunderstanding_threads: List[Dict[str, object]] = []
    delayed_consequences: List[Dict[str, object]] = []
    cross_pressure_threads: List[Dict[str, object]] = []

    for character_id, character in state.characters.items():
        for seed in character.karmic_seeds:
            if seed.status in {"resolved", "transformed"}:
                continue
            if {"love", "secrecy", "doubt", "misrecognition"} & set(seed.tags):
                misunderstanding_threads.append(
                    {
                        "thread_id": seed.seed_id,
                        "focus": seed.seed_type,
                        "actors": [character_id] + ([seed.target] if seed.target else []),
                        "status": "reopened" if seed.status == "ripening" else "open",
                        "seed_tag": seed.tags[0] if seed.tags else seed.seed_type,
                        "opened_at_chapter": seed.created_at_turn,
                        "last_touched_chapter": state.chapter_index,
                        "escalation_count": 1 + int(seed.status == "ripening"),
                        "linked_consequence_ids": [],
                        "cross_pressure_count": 0,
                    }
                )
            if seed.status == "ripening" or {"shame", "humiliation", "sacrifice", "reputation"} & set(seed.tags):
                delayed_consequences.append(
                    {
                        "consequence_id": seed.seed_id,
                        "focus": seed.seed_type,
                        "status": "paid" if seed.status == "ripening" else "open",
                        "weight": seed.charge,
                        "opened_at_chapter": seed.created_at_turn,
                        "last_touched_chapter": state.chapter_index,
                        "echo_count": int(seed.status == "ripening"),
                        "actors": [character_id] + ([seed.target] if seed.target else []),
                        "seed_tag": seed.tags[0] if seed.tags else seed.seed_type,
                        "linked_thread_ids": [],
                    }
                )

    for debt_key in state.unresolved_debts:
        source, target, debt_type = debt_key.split(":", 2)
        delayed_consequences.append(
            {
                "consequence_id": debt_key,
                "focus": debt_type,
                "status": "open",
                "weight": 0.5,
                "opened_at_chapter": state.chapter_index,
                "last_touched_chapter": state.chapter_index,
                "echo_count": 0,
                "actors": [source, target],
                "seed_tag": debt_type,
                "linked_thread_ids": [],
            }
        )

    for thread in misunderstanding_threads:
        for consequence in delayed_consequences:
            if _link_overlap(thread, consequence):
                cross_pressure_threads.append(
                    {
                        "cross_id": _cross_pressure_key(thread, consequence),
                        "thread_focus": thread.get("focus"),
                        "consequence_focus": consequence.get("focus"),
                        "status": "open",
                        "intensity": 1,
                        "opened_at_chapter": state.chapter_index,
                        "last_touched_chapter": state.chapter_index,
                        "linked_thread_ids": list(thread.get("linked_consequence_ids", [])),
                        "linked_consequence_ids": list(consequence.get("linked_thread_ids", [])),
                    }
                )

    _persist_thread_metadata(state, "misunderstanding_threads", misunderstanding_threads)
    _persist_thread_metadata(state, "delayed_consequences", delayed_consequences)
    _persist_thread_metadata(state, "cross_pressure_threads", cross_pressure_threads)
    if cross_pressure_threads:
        state.metadata["recent_cross_pressure"] = {
            "thread_focus": cross_pressure_threads[-1]["thread_focus"],
            "consequence_focus": cross_pressure_threads[-1]["consequence_focus"],
        }
    return state


def update_misunderstanding_threads(state: NarrativeState, event: EventAtom) -> NarrativeState:
    threads = _metadata_list(state, "misunderstanding_threads")
    consequences = _metadata_list(state, "delayed_consequences")
    relevant_seed = next((tag for tag in event.tags if tag in {"secrecy", "love", "truth"}), None)
    relevant_pair = list(event.actors[:2])

    for thread in threads:
        if thread.get("status") == "resolved":
            resolved_at = int(thread.get("resolved_at_chapter", state.chapter_index))
            if state.chapter_index - resolved_at >= 1:
                thread["status"] = "smoldering"

    if (
        relevant_seed is not None
        and event.scene_function in {"temptation", "misrecognition", "truth_trial", "karma_ripening", "confession_window"}
    ):
        matching_thread = next(
            (
                thread
                for thread in reversed(threads)
                if thread.get("seed_tag") == relevant_seed
                and set(thread.get("actors", [])) == set(relevant_pair)
            ),
            None,
        )
        if matching_thread is None:
            threads.append(
                {
                    "thread_id": "%s@%s" % (event.event_id, state.chapter_index),
                    "focus": event.title,
                    "actors": relevant_pair,
                    "status": "open",
                    "seed_tag": relevant_seed,
                    "opened_at_chapter": state.chapter_index,
                    "last_touched_chapter": state.chapter_index,
                    "escalation_count": 1,
                    "linked_consequence_ids": [],
                    "cross_pressure_count": 0,
                }
            )
        elif matching_thread.get("status") in {"smoldering", "resolved"}:
            matching_thread["status"] = "reopened"
            matching_thread["focus"] = event.title
            matching_thread["last_touched_chapter"] = state.chapter_index
            matching_thread["escalation_count"] = int(matching_thread.get("escalation_count", 1)) + 1
            state.metadata["recent_misunderstanding_reignition"] = event.title
        else:
            matching_thread["focus"] = event.title
            matching_thread["last_touched_chapter"] = state.chapter_index
            matching_thread["escalation_count"] = int(matching_thread.get("escalation_count", 1)) + 1

    for thread in threads:
        if thread.get("status") not in {"open", "reopened", "smoldering", "resolved"}:
            continue
        for consequence in consequences:
            if consequence.get("status") not in {"open", "echoing", "paid"}:
                continue
            if _link_overlap(thread, consequence):
                linked = list(thread.get("linked_consequence_ids", []))
                consequence_id = consequence.get("consequence_id")
                if consequence_id and consequence_id not in linked:
                    linked.append(consequence_id)
                thread["linked_consequence_ids"] = linked
                thread["cross_pressure_count"] = int(thread.get("cross_pressure_count", 0)) + 1
                if consequence.get("status") in {"echoing", "paid"}:
                    state.metadata["recent_cross_pressure"] = {
                        "thread_focus": thread.get("focus"),
                        "consequence_focus": consequence.get("focus"),
                    }

    if event.scene_function in {"karma_ripening", "debt_exchange", "vow_payment"} or (
        event.scene_function == "truth_trial" and any(tag in event.tags for tag in {"truth", "honesty", "love"})
    ):
        for thread in threads:
            if thread.get("status") == "open":
                thread["status"] = "resolved"
                state.metadata["recent_misunderstanding_resolution"] = thread.get("focus")
                thread["last_touched_chapter"] = state.chapter_index
                thread["resolved_at_chapter"] = state.chapter_index
                break
    else:
        for thread in threads:
            if thread.get("status") in {"open", "reopened", "smoldering"}:
                thread["last_touched_chapter"] = state.chapter_index

    _persist_thread_metadata(state, "misunderstanding_threads", threads)
    return state


def update_delayed_consequences(state: NarrativeState, event: EventAtom) -> NarrativeState:
    consequences = _metadata_list(state, "delayed_consequences")
    threads = _metadata_list(state, "misunderstanding_threads")

    for consequence in consequences:
        if consequence.get("status") == "paid":
            paid_at = int(consequence.get("paid_at_chapter", state.chapter_index))
            if state.chapter_index - paid_at >= 1:
                consequence["status"] = "echoing"

    if event.scene_function in {"vow_payment", "karma_ripening", "mask_crack", "debt_exchange", "humiliation"}:
        consequences.append(
            {
                "consequence_id": "%s@%s" % (event.event_id, state.chapter_index),
                "focus": event.title,
                "status": "open",
                "weight": min(1.0, max(0.25, abs(event.tension_delta))),
                "opened_at_chapter": state.chapter_index,
                "last_touched_chapter": state.chapter_index,
                "echo_count": 0,
                "actors": list(event.actors[:2]),
                "seed_tag": next((tag for tag in event.tags if tag in {"secrecy", "love", "truth"}), "truth"),
                "linked_thread_ids": [],
            }
        )

    for consequence in consequences:
        if consequence.get("status") not in {"open", "echoing", "paid"}:
            continue
        for thread in threads:
            if thread.get("status") not in {"open", "reopened", "smoldering", "resolved"}:
                continue
            if _link_overlap(thread, consequence):
                linked = list(consequence.get("linked_thread_ids", []))
                thread_id = thread.get("thread_id")
                if thread_id and thread_id not in linked:
                    linked.append(thread_id)
                consequence["linked_thread_ids"] = linked
                consequence["echo_count"] = int(consequence.get("echo_count", 0)) + 1
                if thread.get("status") in {"resolved", "smoldering", "reopened"}:
                    state.metadata["recent_cross_pressure"] = {
                        "thread_focus": thread.get("focus"),
                        "consequence_focus": consequence.get("focus"),
                    }

    if event.scene_function in {"debt_exchange", "vow_payment"}:
        for consequence in consequences:
            if consequence.get("status") == "open":
                consequence["status"] = "paid"
                state.metadata["recent_delayed_payoff"] = consequence.get("focus")
                consequence["last_touched_chapter"] = state.chapter_index
                consequence["paid_at_chapter"] = state.chapter_index
                break
    else:
        for consequence in consequences:
            if consequence.get("status") in {"open", "echoing"}:
                consequence["last_touched_chapter"] = state.chapter_index
                if consequence.get("status") == "echoing":
                    consequence["echo_count"] = int(consequence.get("echo_count", 0)) + 1

    _persist_thread_metadata(state, "delayed_consequences", consequences)
    return state


def update_cross_pressure_threads(state: NarrativeState) -> NarrativeState:
    threads = _metadata_list(state, "misunderstanding_threads")
    consequences = _metadata_list(state, "delayed_consequences")
    cross_threads = _metadata_list(state, "cross_pressure_threads")

    for cross in cross_threads:
        last_touched = int(cross.get("last_touched_chapter", state.chapter_index))
        if cross.get("status") in {"open", "reopened"} and state.chapter_index - last_touched >= 1:
            cross["status"] = "echoing"

    for thread in threads:
        if thread.get("status") not in {"open", "reopened", "smoldering", "resolved"}:
            continue
        for consequence in consequences:
            if consequence.get("status") not in {"open", "echoing", "paid"}:
                continue
            if not _link_overlap(thread, consequence):
                continue

            key = _cross_pressure_key(thread, consequence)
            existing = next(
                (cross for cross in cross_threads if cross.get("cross_id") == key),
                None,
            )
            if existing is None:
                existing = {
                    "cross_id": key,
                    "thread_focus": thread.get("focus"),
                    "consequence_focus": consequence.get("focus"),
                    "status": "open",
                    "intensity": 1,
                    "opened_at_chapter": state.chapter_index,
                    "last_touched_chapter": state.chapter_index,
                    "linked_thread_ids": list(thread.get("linked_consequence_ids", [])),
                    "linked_consequence_ids": list(consequence.get("linked_thread_ids", [])),
                }
                cross_threads.append(existing)
            else:
                if existing.get("status") == "echoing":
                    existing["status"] = "reopened"
                else:
                    existing["status"] = "open"
                existing["intensity"] = int(existing.get("intensity", 1)) + 1
                existing["last_touched_chapter"] = state.chapter_index

            state.metadata["recent_cross_pressure"] = {
                "thread_focus": thread.get("focus"),
                "consequence_focus": consequence.get("focus"),
            }

    _persist_thread_metadata(state, "cross_pressure_threads", cross_threads)
    return state


def advance_story_phase_if_needed(
    state: NarrativeState,
    *,
    scene_intent_id: Optional[str] = None,
) -> NarrativeState:
    state.chapter_index += 1
    state.story_phase = determine_story_phase(state.chapter_index)
    update_scene_history(state, scene_intent_id=scene_intent_id)
    aging_open_promises(state)
    update_payoff_pressure(state)
    return state


def apply_event(state: NarrativeState, event: EventAtom) -> NarrativeState:
    next_state = NarrativeState.from_dict(state.to_dict())
    event = EventAtom.from_dict({**event.to_dict(), "scene_function": normalize_scene_function(event.scene_function)})
    next_state.turn_index += 1
    next_state.timeline.append(event.title)
    next_state.visited_event_ids = _merge_unique(next_state.visited_event_ids, [event.event_id])

    fact_set = set(next_state.world_facts)
    for item in event.world_fact_deltas_remove:
        fact_set.discard(item)
    for item in event.world_fact_deltas_add:
        fact_set.add(item)
    next_state.world_facts = sorted(fact_set)

    for character_id, updates in event.belief_updates.items():
        if character_id not in next_state.characters:
            continue
        character = next_state.characters[character_id]
        add_true = list(updates.get("add_true", []))
        add_false = list(updates.get("add_false", []))
        if add_true:
            character.beliefs_false = [
                belief for belief in character.beliefs_false if belief not in set(add_true)
            ]
        if add_false:
            character.beliefs_true = [
                belief for belief in character.beliefs_true if belief not in set(add_false)
            ]
        character.beliefs_true = _merge_unique(character.beliefs_true, add_true)
        character.beliefs_false = _merge_unique(character.beliefs_false, add_false)

    for delta in event.trust_deltas:
        if delta.source in next_state.characters:
            source = next_state.characters[delta.source]
            current = source.trust.get(delta.target, 0.5)
            source.trust[delta.target] = _clamp(current + delta.delta)

    for delta in event.emotion_deltas:
        if delta.character in next_state.characters:
            character = next_state.characters[delta.character]
            current = character.emotions.get(delta.emotion, 0.0)
            character.emotions[delta.emotion] = _clamp(current + delta.delta)

    apply_debt_deltas(next_state, event.debt_deltas, opened_at_turn=next_state.turn_index)

    to_close = set(event.promises_close)
    still_open: List[PromiseLedgerEntry] = []
    closed_ids = list(state.metadata.get("closed_promise_ids", []))
    for promise in next_state.open_promises:
        if promise.promise_id in to_close:
            if promise.promise_id not in closed_ids:
                closed_ids.append(promise.promise_id)
            continue
        still_open.append(PromiseLedgerEntry.from_dict(promise.to_dict()))

    existing_ids = {promise.promise_id for promise in still_open}
    for promise in event.promises_open:
        normalized = _normalize_promise_turns(promise, turn_index=next_state.turn_index)
        if normalized.promise_id in existing_ids:
            continue
        still_open.append(normalized)
        existing_ids.add(normalized.promise_id)

    next_state.open_promises = still_open
    next_state.tension = _clamp(next_state.tension + event.tension_delta)

    for theme, impact in event.theme_impacts.items():
        next_state.themes[theme] = _clamp(next_state.themes.get(theme, 0.0) + impact)

    next_state.recent_scene_functions.append(event.scene_function)
    next_state.recent_scene_functions = next_state.recent_scene_functions[-3:]

    fingerprint_bits = list(event.tags)
    if event.convergence_key:
        fingerprint_bits.append("merge:%s" % event.convergence_key)
    fingerprint_bits.extend(
        [
            "scene:%s" % event.scene_function,
            "location:%s" % event.location,
            "event:%s" % event.event_id,
        ]
    )
    next_state.route_fingerprint = _merge_unique(next_state.route_fingerprint, fingerprint_bits)

    next_state.metadata["last_event_id"] = event.event_id
    next_state.metadata["last_location"] = event.location
    next_state.metadata["closed_promise_ids"] = closed_ids
    next_state.state_id = "%s__%s" % (state.state_id, event.event_id)
    update_character_private_memory(next_state)
    sync_character_debts(next_state)
    create_karmic_seeds(next_state, event)
    _apply_poison_activation(next_state, event)
    ripen_karmic_seeds(next_state, event)
    resolve_or_transform_seeds(next_state, event)
    next_state.karmic_weather = compute_karmic_weather(next_state)
    next_state.unresolved_debts = unresolved_debt_keys(next_state)
    refresh_karma_derivatives(next_state)
    update_fate_pressure(next_state, event)
    aging_open_promises(next_state)
    update_payoff_pressure(next_state)
    return next_state
