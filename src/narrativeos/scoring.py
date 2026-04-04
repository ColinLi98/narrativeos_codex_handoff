from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .canon import hard_constraint_errors
from .character_engine import choice_score
from .fate import destiny_alignment
from .models import EventAtom, NarrativeState, ScoredCandidate, SearchWeights, WorldBible


def _tokenize(parts: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in str(part).lower().replace("-", "_").replace(" ", "_").split("_"):
            if token:
                tokens.add(token)
    return tokens


def _keyword_overlap(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = _tokenize(a)
    set_b = _tokenize(b)
    if not set_a or not set_b:
        return 0.0
    return float(len(set_a & set_b)) / float(len(set_a | set_b))


def causal_consistency(
    state: NarrativeState,
    event: EventAtom,
    *,
    world: Optional[WorldBible] = None,
) -> float:
    return 0.0 if hard_constraint_errors(state, event, world=world) else 1.0


def dramatic_tension_delta(state: NarrativeState, event: EventAtom) -> float:
    phase_targets = {
        "setup": 0.08,
        "early_rising": 0.12,
        "midpoint": 0.08,
        "crisis": 0.16,
        "climax": 0.14,
        "aftermath": -0.08,
    }
    desired_delta = phase_targets.get(state.story_phase, 0.08)
    diff = abs(event.tension_delta - desired_delta)
    return max(0.0, 1.0 - diff / 0.30)


def _aggregate_character_signals(state: NarrativeState, event: EventAtom) -> Dict[str, float]:
    actor_ids = [actor_id for actor_id in event.actors if actor_id in state.characters]
    if not actor_ids:
        return {
            "desire_pull": 0.0,
            "shadow_pull": 0.0,
            "poison_pull": 0.0,
            "vow_pull": 0.0,
            "wound_pull": 0.0,
            "debt_pull": 0.0,
            "karma_pull": 0.0,
            "fate_pull": 0.0,
            "wisdom_resistance": 0.0,
            "character_fidelity": 0.0,
            "choice_total": 0.0,
        }

    weights: List[float] = []
    if len(actor_ids) == 1:
        weights = [1.0]
    else:
        trailing_weight = 0.45 / float(len(actor_ids) - 1)
        weights = [0.55] + [trailing_weight] * (len(actor_ids) - 1)

    totals = {
        "desire_pull": 0.0,
        "shadow_pull": 0.0,
        "poison_pull": 0.0,
        "vow_pull": 0.0,
        "wound_pull": 0.0,
        "debt_pull": 0.0,
        "karma_pull": 0.0,
        "fate_pull": 0.0,
        "wisdom_resistance": 0.0,
        "character_fidelity": 0.0,
        "choice_total": 0.0,
    }
    for actor_id, weight in zip(actor_ids, weights):
        character = state.characters[actor_id]
        fate_pull = destiny_alignment(character, state, event)
        scored = choice_score(character, state, event, fate_pull=fate_pull)
        for key in totals:
            totals[key] += weight * scored[key]
    return {key: max(0.0, min(1.0, value)) for key, value in totals.items()}


def thematic_resonance(
    state: NarrativeState,
    event: EventAtom,
    *,
    world: Optional[WorldBible] = None,
) -> float:
    active_themes = [key for key, value in state.themes.items() if value >= 0.35]
    target_themes: List[str] = []
    if world is not None:
        target_themes = list(world.creator_controls.theme_targets or [])
    comparison = active_themes + target_themes + list(event.theme_impacts.keys()) + event.tags
    return _keyword_overlap(active_themes + target_themes, comparison)


def explain_components(components: Dict[str, float]) -> str:
    ordered = sorted(components.items(), key=lambda item: item[1], reverse=True)
    best = ", ".join("%s=%.2f" % (name, value) for name, value in ordered[:4])
    weakest = ", ".join("%s=%.2f" % (name, value) for name, value in ordered[-2:])
    return "Top drivers: %s; weakest: %s" % (best, weakest)


def score_event(
    state: NarrativeState,
    event: EventAtom,
    *,
    weights: Optional[SearchWeights] = None,
    sibling_events: Optional[Sequence[EventAtom]] = None,
    world: Optional[WorldBible] = None,
) -> ScoredCandidate:
    resolved = (weights or SearchWeights()).normalized()
    causal = causal_consistency(state, event, world=world)
    actor_components = _aggregate_character_signals(state, event)
    components = {
        "desire_pull": actor_components["desire_pull"],
        "shadow_pull": actor_components["shadow_pull"],
        "poison_pull": actor_components["poison_pull"],
        "vow_pull": actor_components["vow_pull"],
        "wound_pull": actor_components["wound_pull"],
        "debt_pull": actor_components["debt_pull"],
        "karma_pull": actor_components["karma_pull"],
        "fate_pull": actor_components["fate_pull"],
        "wisdom_resistance": actor_components["wisdom_resistance"],
        "character_fidelity": actor_components["character_fidelity"],
        "causal_consistency": causal,
        "dramatic_tension_delta": dramatic_tension_delta(state, event),
        "thematic_resonance": thematic_resonance(state, event, world=world),
    }
    total = (
        resolved.desire_pull * components["desire_pull"]
        + resolved.shadow_pull * components["shadow_pull"]
        + resolved.poison_pull * components["poison_pull"]
        + resolved.vow_pull * components["vow_pull"]
        + resolved.wound_pull * components["wound_pull"]
        + resolved.debt_pull * components["debt_pull"]
        + resolved.karma_pull * components["karma_pull"]
        + resolved.fate_pull * components["fate_pull"]
        - resolved.wisdom_resistance * components["wisdom_resistance"]
    )
    total = max(0.0, min(1.0, total)) * causal
    return ScoredCandidate(
        event=event,
        total_score=total,
        components=components,
        explanation=explain_components(components),
    )
