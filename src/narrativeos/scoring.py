from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .canon import hard_constraint_errors
from .character_engine import choice_score
from .core.contracts import style_pack_from_world
from .fate import destiny_alignment
from .longform import active_replan_debt
from .models import EventAtom, NarrativeState, ScoredCandidate, SearchWeights, WorldBible
from .scene_functions import is_terminal_scene_function


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


_DUTY_ALIGNMENT_RULES: Dict[str, Dict[str, List[str]]] = {
    "advance_plot": {
        "scene_functions": ["truth_trial", "mask_crack", "debt_exchange", "karma_ripening", "temptation"],
        "tags": ["truth", "destiny", "reputation", "system", "selfhood"],
    },
    "advance_relationship": {
        "scene_functions": ["temptation", "misrecognition", "confession_window", "truth_trial"],
        "tags": ["love", "honesty", "selfhood", "loyalty", "curiosity"],
    },
    "resolve_promise": {
        "scene_functions": ["vow_payment", "confession_window", "truth_trial", "debt_exchange"],
        "tags": ["truth", "honesty", "sacrifice", "loyalty", "choice"],
    },
    "expand_world": {
        "scene_functions": ["false_peace", "karma_ripening", "mask_crack", "truth_trial"],
        "tags": ["system", "reform", "destiny", "reputation", "world"],
    },
    "pace_breath": {
        "scene_functions": ["false_peace", "confession_window", "misrecognition"],
        "tags": ["hope", "mercy", "selfhood", "reflection", "earned_peace"],
    },
    "deliver_climax": {
        "scene_functions": ["vow_payment", "karma_ripening", "truth_trial", "debt_exchange"],
        "tags": ["destiny", "selfhood", "truth", "sacrifice", "reputation"],
    },
}


def _event_signal_tokens(event: EventAtom) -> List[str]:
    return (
        list(event.tags)
        + list(event.agency_affordances)
        + list(event.vow_tests)
        + list(event.wound_triggers)
        + [event.scene_function, event.summary]
    )


def _character_memory_payload(
    state: NarrativeState,
    actor_id: str,
    *,
    world: Optional[WorldBible] = None,
) -> Dict[str, object]:
    runtime_entry = dict((state.character_memory_runtime or {}).get(actor_id) or {})
    if runtime_entry:
        return runtime_entry
    metadata = dict(getattr(getattr(world, "creator_controls", None), "metadata", {}) or {})
    profiles = dict(metadata.get("character_memory_profiles") or {})
    return dict(profiles.get(actor_id) or {})


def _character_card_alignment(
    state: NarrativeState,
    event: EventAtom,
    *,
    world: Optional[WorldBible] = None,
) -> float:
    actor_ids = [actor_id for actor_id in event.actors if actor_id in state.characters]
    if not actor_ids:
        return 0.5
    event_probes = _event_signal_tokens(event)
    duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
    if duty_type:
        event_probes.append(duty_type)
        event_probes.extend(_DUTY_ALIGNMENT_RULES.get(duty_type, {}).get("tags", []))
    scores: List[float] = []
    for actor_id in actor_ids:
        character = state.characters[actor_id]
        runtime_entry = _character_memory_payload(state, actor_id, world=world)
        structured_memory = dict(runtime_entry.get("structured_memory") or {})
        card_probes = (
            list(character.public_goals[:3])
            + list(character.hidden_goals[:3])
            + list(character.vows.vows[:3])
            + [
                character.wound.core_wound,
                character.wound.public_self,
                character.wound.shadow_desire,
                character.destiny.life_theme,
            ]
            + list(structured_memory.get("goals", []))
            + list(structured_memory.get("promises", []))
            + list(structured_memory.get("scars", []))
            + list(structured_memory.get("taboos", []))
        )
        filtered_probes = [str(item) for item in card_probes if str(item)]
        scores.append(_keyword_overlap(filtered_probes, event_probes) if filtered_probes else 0.5)
    return max(0.0, min(1.0, sum(scores) / float(len(scores))))


def _duty_alignment(state: NarrativeState, event: EventAtom) -> float:
    duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
    if not duty_type:
        return 0.5
    rules = _DUTY_ALIGNMENT_RULES.get(duty_type)
    if not rules:
        return 0.5
    scene_score = 1.0 if event.scene_function in rules["scene_functions"] else 0.0
    tag_score = _keyword_overlap(_event_signal_tokens(event), rules["tags"] + rules["scene_functions"])
    return max(0.0, min(1.0, 0.65 * scene_score + 0.35 * tag_score))


def _actor_style_coverage(world: WorldBible, state: NarrativeState, actor_ids: Sequence[str]) -> float:
    if not actor_ids:
        return 0.5
    style_pack = style_pack_from_world(world)
    voice_profiles = dict(style_pack.dialogue.voice_profiles or {})
    pressure_styles = dict(style_pack.dialogue.pressure_styles or {})
    covered = 0.0
    for actor_id in actor_ids:
        role_key = getattr(state.characters.get(actor_id), "role", "")
        if actor_id in voice_profiles or role_key in voice_profiles:
            covered += 0.5
        if actor_id in pressure_styles or role_key in pressure_styles:
            covered += 0.5
    return max(0.0, min(1.0, covered / float(len(actor_ids))))


def _emotion_action_alignment(
    state: NarrativeState,
    event: EventAtom,
    *,
    world: Optional[WorldBible] = None,
) -> float:
    if world is None:
        return 0.5
    style_pack = style_pack_from_world(world)
    action_pool = dict((style_pack.emotion_actions.action_map or {}).get(event.scene_function, {}) or {})
    slot_coverage = sum(1 for slot in ("entry", "pressure", "pivot", "aftermath", "echo") if action_pool.get(slot))
    normalized_slot_coverage = float(slot_coverage) / 5.0 if slot_coverage else 0.4
    actor_coverage = _actor_style_coverage(world, state, [actor_id for actor_id in event.actors if actor_id in state.characters])
    return max(0.0, min(1.0, 0.6 * normalized_slot_coverage + 0.4 * actor_coverage))


def _terminal_before_late_penalty(state: NarrativeState, event: EventAtom) -> float:
    progression = dict((state.metadata or {}).get("longform_progression") or {})
    target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapter = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    completion_ratio = (
        float(current_chapter) / float(max(1, target_chapters))
        if target_chapters > 0
        else 0.0
    )
    if not is_terminal_scene_function(event.scene_function, event.metadata):
        return 0.0
    if bool((state.metadata or {}).get("series_terminal_ready")):
        return 0.0
    if completion_ratio < 0.8:
        return 1.0
    if completion_ratio < 0.92:
        return 0.8
    return 0.4


def _scene_function_cluster_penalty(state: NarrativeState, event: EventAtom) -> float:
    recent = [str(item) for item in list(state.recent_scene_functions or []) if str(item)]
    if not recent:
        return 0.0
    same_count = sum(1 for item in recent if item == event.scene_function)
    if same_count == 0:
        return 0.0
    return min(1.0, same_count / float(max(1, len(recent))))


def _duty_cluster_penalty(state: NarrativeState) -> float:
    duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
    recent = [str(item) for item in list((state.metadata or {}).get("recent_duty_types") or []) if str(item)]
    if not duty_type or not recent:
        return 0.0
    same_count = sum(1 for item in recent if item == duty_type)
    if same_count == 0:
        return 0.0
    if duty_type in {"resolve_promise", "deliver_climax"}:
        return min(1.0, 0.5 + (same_count / float(max(1, len(recent)))))
    return min(1.0, same_count / float(max(1, len(recent))))


def _continuation_pressure_bonus(state: NarrativeState, event: EventAtom) -> float:
    quality_contract = dict((state.current_chapter_task or {}).get("quality_contract") or {})
    if not bool(quality_contract.get("continuation_pressure_required", False)):
        return 0.0
    if is_terminal_scene_function(event.scene_function, event.metadata):
        return 0.0
    continuation_scene_functions = {
        "debt_exchange",
        "karma_ripening",
        "truth_trial",
        "misrecognition",
        "temptation",
        "confession_window",
        "mask_crack",
    }
    continuation_tags = {"truth", "love", "loyalty", "reputation", "destiny", "selfhood"}
    if event.scene_function in continuation_scene_functions:
        return 1.0
    if set(event.tags) & continuation_tags:
        return 0.7
    return 0.2


def _replan_debt_penalty(state: NarrativeState, event: EventAtom) -> float:
    debt = active_replan_debt(state)
    if not debt:
        return 0.0
    issue_codes = {str(item) for item in debt.get("issue_codes", []) if str(item)}
    penalty = 0.0
    if "Q09" in issue_codes and (
        is_terminal_scene_function(event.scene_function, event.metadata)
        or event.scene_function in {"vow_payment", "karma_ripening"}
    ):
        penalty += 0.7
    if "Q07" in issue_codes and event.scene_function in {"false_peace", "vow_payment"}:
        penalty += 0.3
    return min(1.0, penalty)


def _relationship_debt_bonus(state: NarrativeState, event: EventAtom) -> float:
    debt = active_replan_debt(state)
    if not debt:
        return 0.0
    recovery_scene_functions = {"debt_exchange", "misrecognition", "truth_trial", "confession_window", "temptation"}
    recovery_tags = {"love", "truth", "loyalty", "reputation", "sacrifice"}
    if event.scene_function in recovery_scene_functions:
        return 1.0
    if set(event.tags) & recovery_tags:
        return 0.7
    return 0.0


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
    card_alignment = _character_card_alignment(state, event, world=world)
    duty_alignment = _duty_alignment(state, event)
    emotion_alignment = _emotion_action_alignment(state, event, world=world)
    terminal_before_late_penalty = _terminal_before_late_penalty(state, event)
    scene_function_cluster_penalty = _scene_function_cluster_penalty(state, event)
    duty_cluster_penalty = _duty_cluster_penalty(state)
    continuation_pressure_bonus = _continuation_pressure_bonus(state, event)
    replan_debt_penalty = _replan_debt_penalty(state, event)
    relationship_debt_bonus = _relationship_debt_bonus(state, event)
    blended_character_fidelity = max(
        0.0,
        min(
            1.0,
            0.72 * actor_components["character_fidelity"]
            + 0.14 * card_alignment
            + 0.08 * duty_alignment
            + 0.06 * emotion_alignment,
        ),
    )
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
        "character_fidelity": blended_character_fidelity,
        "character_card_alignment": card_alignment,
        "duty_alignment": duty_alignment,
        "emotion_action_alignment": emotion_alignment,
        "continuation_pressure_bonus": continuation_pressure_bonus,
        "relationship_debt_bonus": relationship_debt_bonus,
        "terminal_before_late_penalty": terminal_before_late_penalty,
        "scene_function_cluster_penalty": scene_function_cluster_penalty,
        "duty_cluster_penalty": duty_cluster_penalty,
        "replan_debt_penalty": replan_debt_penalty,
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
    if state.current_chapter_task:
        total += 0.08 * card_alignment + 0.06 * duty_alignment + 0.04 * emotion_alignment
        total += 0.05 * continuation_pressure_bonus + 0.04 * relationship_debt_bonus
        total -= 0.08 * terminal_before_late_penalty
        total -= 0.05 * scene_function_cluster_penalty
        total -= 0.05 * duty_cluster_penalty
        total -= 0.07 * replan_debt_penalty
    total = max(0.0, min(1.0, total)) * causal
    return ScoredCandidate(
        event=event,
        total_score=total,
        components=components,
        explanation=explain_components(components),
    )
