from __future__ import annotations

from typing import Dict, List

from .models import EventAtom, KarmicSeed, NarrativeState


def create_karmic_seeds(state: NarrativeState, event: EventAtom) -> NarrativeState:
    for actor_id in event.actors:
        character = state.characters.get(actor_id)
        if character is None:
            continue
        for seed in event.karmic_seed_creations:
            if seed.actor == actor_id:
                character.karmic_seeds.append(KarmicSeed.from_dict(seed.to_dict()))
        if event.concealment_level >= 0.65:
            auto_seed = KarmicSeed(
                seed_id="%s:%s:hidden_aftertaste" % (event.event_id, actor_id),
                source_event_id=event.event_id,
                actor=actor_id,
                target=event.actors[1] if len(event.actors) > 1 else None,
                seed_type="concealed_truth",
                charge=round(event.concealment_level, 3),
                tags=list(dict.fromkeys(event.tags + ["concealment"])),
                created_at_turn=state.turn_index,
                ripening_conditions=["truth_trial", "karma_ripening", "public_crisis"],
                earliest_turn=state.turn_index + max(1, event.consequence_delay_hint),
                latest_turn=state.turn_index + max(4, event.consequence_delay_hint + 4),
                status="dormant",
                transformable_by=["confession", "full_confession", "mutual_truth"],
            )
            if auto_seed.seed_id not in {seed.seed_id for seed in character.karmic_seeds}:
                character.karmic_seeds.append(auto_seed)
    return state


def _condition_hits(state: NarrativeState, event: EventAtom, seed: KarmicSeed) -> bool:
    probes = set(event.tags + event.agency_affordances + event.awakening_affordances + [event.scene_function])
    probes |= set(state.world_facts)
    probes |= set(state.metadata.get("scene_history", []))
    return bool(set(seed.ripening_conditions) & probes)


def ripen_karmic_seeds(state: NarrativeState, event: EventAtom) -> NarrativeState:
    for character in state.characters.values():
        for seed in character.karmic_seeds:
            if seed.status in {"resolved", "transformed"}:
                continue
            if state.turn_index < seed.earliest_turn:
                continue
            if seed.latest_turn is not None and state.turn_index > seed.latest_turn and seed.status == "dormant":
                seed.status = "ripening"
                continue
            if _condition_hits(state, event, seed):
                seed.status = "ripening"
    return state


def resolve_or_transform_seeds(state: NarrativeState, event: EventAtom) -> NarrativeState:
    resolution_ids = set(event.karmic_seed_resolutions)
    transforms = set(event.awakening_affordances + event.vow_tests)
    for character in state.characters.values():
        for seed in character.karmic_seeds:
            if seed.status not in {"dormant", "ripening"}:
                continue
            if seed.seed_id in resolution_ids:
                if transforms & set(seed.transformable_by):
                    seed.status = "transformed"
                else:
                    seed.status = "resolved"
            elif seed.status == "ripening" and transforms & set(seed.transformable_by):
                seed.status = "transformed"
    return state


def compute_karmic_weather(state: NarrativeState) -> Dict[str, float]:
    weather = {
        "suspicion": 0.0,
        "grief": 0.0,
        "temptation": 0.0,
        "shame": 0.0,
        "mercy": 0.0,
    }
    for character in state.characters.values():
        for seed in character.karmic_seeds:
            if seed.status not in {"dormant", "ripening"}:
                continue
            if {"secrecy", "doubt", "concealment"} & set(seed.tags):
                weather["suspicion"] += 0.08 * seed.charge
            if {"loss", "grief", "humiliation"} & set(seed.tags):
                weather["grief"] += 0.06 * seed.charge
            if {"love", "obsession", "temptation"} & set(seed.tags):
                weather["temptation"] += 0.08 * seed.charge
            if {"shame", "reputation", "humiliation"} & set(seed.tags):
                weather["shame"] += 0.07 * seed.charge
            if {"mercy", "forgiveness", "sacrifice"} & set(seed.tags):
                weather["mercy"] += 0.05 * seed.charge
    return {key: round(min(1.0, value), 3) for key, value in weather.items()}
