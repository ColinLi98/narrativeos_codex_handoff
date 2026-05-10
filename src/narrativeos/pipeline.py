from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .critics import BaseCritic, default_critics
from .longform import archive_longform_chapter, build_longform_context_pack, default_chapter_task, longform_terminal_allowed, sync_longform_progression
from .memory import advance_story_phase_if_needed, apply_event
from .models import (
    ChapterPlan,
    EventAtom,
    NarrativeState,
    SceneBeat,
    SceneIntent,
    SceneRenderSpec,
    SearchWeights,
    WorldBible,
)
from .presenter import present_scene_for_reader
from .providers import CandidateProvider, StaticCandidateProvider
from .rendering import Renderer, TemplateRenderer
from .scene_functions import is_terminal_scene_function
from .search import evaluate_candidates


SCENE_INTENTS = {
    "setup": [
        SceneIntent(
            intent_id="false_calm",
            label="表面平静下的暗潮",
            description="看似平静的一章，实际上把真正的矛盾悄悄拱出水面。",
            preferred_scene_functions=["false_peace", "temptation", "confession_window"],
            preferred_tags=["duty", "love", "curiosity", "reputation"],
        ),
        SceneIntent(
            intent_id="public_pressure",
            label="公开压力逼近",
            description="外部目光和规训开始一起压过来，让人物再难拖延。",
            preferred_scene_functions=["false_peace", "truth_trial", "humiliation"],
            preferred_tags=["reputation", "duty", "ambition"],
        ),
    ],
    "early_rising": [
        SceneIntent(
            intent_id="intimate_confrontation",
            label="关系里的试探与逼问",
            description="人物不再只躲在心里权衡，而开始在关系里互相逼近、互相试探。",
            preferred_scene_functions=["temptation", "misrecognition", "truth_trial"],
            preferred_tags=["love", "honesty", "selfhood"],
        ),
        SceneIntent(
            intent_id="hidden_reveal",
            label="被压着的真相露出一角",
            description="旧事、隐情或者权力的暗线被掀开一角，让局势开始失衡。",
            preferred_scene_functions=["confession_window", "mask_crack", "karma_ripening"],
            preferred_tags=["truth", "system", "selfhood"],
        ),
    ],
    "midpoint": [
        SceneIntent(
            intent_id="false_choice",
            label="一条看似体面的诱惑之路",
            description="人物眼前出现一条看似能两全的路，但代价其实已经在暗处成形。",
            preferred_scene_functions=["temptation", "mercy_vs_control", "debt_exchange"],
            preferred_tags=["loyalty", "reputation", "power"],
        ),
        SceneIntent(
            intent_id="social_humiliation",
            label="风声把人推到众目睽睽之下",
            description="风声、家门和舆论一起发力，逼着人物在公共场域里承担后果。",
            preferred_scene_functions=["humiliation", "truth_trial", "debt_exchange"],
            preferred_tags=["reputation", "honesty", "selfhood"],
        ),
    ],
    "crisis": [
        SceneIntent(
            intent_id="sacrifice_test",
            label="真正要付出代价的时刻",
            description="人物必须用失去、退让或承担污名来证明自己的选择不是一句空话。",
            preferred_scene_functions=["vow_payment", "humiliation", "debt_exchange"],
            preferred_tags=["sacrifice", "selfhood", "loyalty"],
        ),
        SceneIntent(
            intent_id="public_testimony",
            label="旧秩序在公开场合被逼问",
            description="被压下去的事实终于来到台前，让所有人的立场都无处可藏。",
            preferred_scene_functions=["karma_ripening", "truth_trial", "debt_exchange"],
            preferred_tags=["truth", "reform", "reputation"],
        ),
    ],
    "climax": [
        SceneIntent(
            intent_id="earned_choice",
            label="终于来到必须选命的章节",
            description="前面所有误解、牵挂和代价都压到这一章，人物必须给出会改写命运的决定。",
            preferred_scene_functions=["vow_payment", "karma_ripening", "truth_trial"],
            preferred_tags=["selfhood", "destiny", "love", "duty"],
        )
    ],
    "aftermath": [
        SceneIntent(
            intent_id="aftershock",
            label="余震与回响",
            description="结局之后的余波仍在人物心里和世界里继续发酵。",
            preferred_scene_functions=["debt_exchange", "karma_ripening", "vow_payment"],
            preferred_tags=["destiny", "reputation", "selfhood"],
        )
    ],
}

BEAT_BLUEPRINTS = {
    3: [("起势", "entry"), ("逼近", "pressure"), ("转向", "pivot")],
    4: [("起势", "entry"), ("逼近", "pressure"), ("转向", "pivot"), ("余波", "aftermath")],
    5: [("起势", "entry"), ("逼近", "pressure"), ("转向", "pivot"), ("余波", "aftermath"), ("回响", "echo")],
}

JOB_FUNCTION_PRIORITIES = {
    "entry": ["false_peace", "temptation", "confession_window", "misrecognition"],
    "pressure": ["truth_trial", "temptation", "humiliation", "mercy_vs_control"],
    "pivot": ["mask_crack", "karma_ripening", "debt_exchange", "truth_trial"],
    "aftermath": ["debt_exchange", "karma_ripening", "vow_payment", "confession_window"],
    "echo": ["karma_ripening", "vow_payment", "debt_exchange", "false_peace"],
}


def resolve_search_weights(
    world: WorldBible,
    weights: Optional[SearchWeights] = None,
) -> SearchWeights:
    if weights is not None:
        return weights
    if world.creator_controls.scoring_weights:
        return SearchWeights.from_dict(world.creator_controls.scoring_weights)
    return SearchWeights()


def plan_arc(state: NarrativeState, world: WorldBible) -> Dict[str, object]:
    return {
        "world_id": world.world_id,
        "story_phase": state.story_phase,
        "chapter_index": state.chapter_index,
        "min_end_turn": state.min_end_turn,
        "payoff_pressure": float(state.metadata.get("payoff_pressure", 0.0)),
    }


def _pick_scene_intent(state: NarrativeState, world: WorldBible) -> SceneIntent:
    open_threads = [
        thread
        for thread in state.metadata.get("misunderstanding_threads", [])
        if thread.get("status") in {"open", "reopened", "smoldering"}
    ]
    ripe_threads = [
        thread
        for thread in open_threads
        if state.chapter_index - int(thread.get("opened_at_chapter", state.chapter_index)) >= 1
    ]
    open_consequences = [
        item
        for item in state.metadata.get("delayed_consequences", [])
        if item.get("status") in {"open", "echoing"}
    ]
    ripe_consequences = [
        item
        for item in open_consequences
        if state.chapter_index - int(item.get("opened_at_chapter", state.chapter_index)) >= 1
    ]
    active_cross_pressures = [
        item
        for item in state.metadata.get("cross_pressure_threads", [])
        if item.get("status") in {"open", "reopened", "echoing"}
    ]
    ripe_cross_pressures = [
        item
        for item in active_cross_pressures
        if state.chapter_index - int(item.get("opened_at_chapter", state.chapter_index)) >= 1
    ]

    if state.story_phase == "setup":
        if state.player_intent.get("romance", 0.0) >= 0.6:
            return SceneIntent(
                intent_id="romance_probe",
                label="暧昧试探先起",
                description="这一章先让人与人之间的试探升温，再把真正的问题慢慢逼出来。",
                preferred_scene_functions=["temptation", "misrecognition", "truth_trial"],
                preferred_tags=["love", "selfhood", "curiosity"],
            )
        if max(state.player_intent.get("ambition", 0.0), state.player_intent.get("loyalty", 0.0)) >= 0.6:
            return SceneIntent(
                intent_id="duty_pressure",
                label="家门与前途先压上来",
                description="这一章让外部期待和家门压力先一步落到人物肩上，逼他意识到自己已经没有太多回旋余地。",
                preferred_scene_functions=["false_peace", "confession_window", "truth_trial"],
                preferred_tags=["duty", "reputation", "ambition"],
            )
    if state.metadata.get("recent_misunderstanding_resolution") and state.story_phase in {"midpoint", "crisis", "climax"}:
        return SceneIntent(
            intent_id="after_misread_silence",
            label="误会刚散，真正的亏欠才开始露出来",
            description="误会虽然被点破了一层，但留下来的尴尬、亏欠和迟来的理解，反而会把关系推向更难处理的章节。",
            preferred_scene_functions=["debt_exchange", "confession_window", "truth_trial"],
            preferred_tags=["love", "truth", "loyalty"],
        )
    if state.metadata.get("recent_delayed_payoff") and state.story_phase in {"crisis", "climax", "aftermath"}:
        return SceneIntent(
            intent_id="cost_aftershock",
            label="代价兑现之后，谁也回不到之前的位置",
            description="前面埋下的代价已经开始兑现，这一章要写的不是事情结束，而是谁因此被迫改了站位。",
            preferred_scene_functions=["debt_exchange", "karma_ripening", "vow_payment"],
            preferred_tags=["sacrifice", "reputation", "selfhood"],
        )
    if (state.metadata.get("recent_cross_pressure") or ripe_cross_pressures) and state.story_phase in {"midpoint", "crisis", "climax", "aftermath"}:
        if {"duty", "reputation"} & set(world.creator_controls.theme_targets or world.themes):
            return SceneIntent(
                intent_id="public_face_private_wound",
                label="门楣要体面，心里那道伤却一直没合上",
                description="最难堪的不是哪一边先输了，而是人物发现自己既要替家门撑着体面，又已经没法否认心里那道裂口。",
                preferred_scene_functions=["debt_exchange", "truth_trial", "karma_ripening"],
                preferred_tags=["reputation", "love", "truth", "loyalty"],
            )
        return SceneIntent(
            intent_id="crossed_wound",
            label="旧误会和旧代价在同一章里撞上了",
            description="这已经不是单一的一条关系线，也不是单独的一笔代价，而是两种后果在同一章里彼此放大，逼得人物再也无法退回原位。",
            preferred_scene_functions=["debt_exchange", "truth_trial", "karma_ripening"],
            preferred_tags=["love", "truth", "sacrifice", "reputation"],
        )
    if open_threads and (
        max(state.player_intent.get("loyalty", 0.0), state.player_intent.get("ambition", 0.0)) >= 0.5
        or {"duty", "reputation"} & set(world.creator_controls.theme_targets or world.themes)
    ) and state.story_phase in {"early_rising", "midpoint", "crisis"}:
        return SceneIntent(
            intent_id="heart_vs_house",
            label="真心刚露一点，门楣就压了下来",
            description="关系里的靠近还没来得及落稳，家门、体面和责任就先一步压了上来，让人无论往哪边站都要伤人。",
            preferred_scene_functions=["truth_trial", "debt_exchange", "karma_ripening"],
            preferred_tags=["love", "duty", "reputation", "selfhood"],
        )
    if active_cross_pressures and state.story_phase in {"early_rising", "midpoint", "crisis"}:
        return SceneIntent(
            intent_id="crossed_wound",
            label="旧误会和旧代价在同一章里撞上了",
            description="一条关系线和一笔旧代价开始在同一章里彼此放大，让人物再也没法把两边的伤口分开算。",
            preferred_scene_functions=["consequence", "confrontation", "reveal"],
            preferred_tags=["love", "truth", "reputation", "sacrifice"],
        )
    if state.metadata.get("recent_misunderstanding_reignition") and state.story_phase in {"midpoint", "crisis", "climax"}:
        return SceneIntent(
            intent_id="misread_aftershock",
            label="误会被点破之后，亏欠反而更深了",
            description="误会不是一说开就结束，它往往会把更难堪的真心和更迟到的亏欠一起翻出来。",
            preferred_scene_functions=["debt_exchange", "truth_trial", "misrecognition"],
            preferred_tags=["love", "truth", "selfhood"],
        )
    if ripe_threads and state.story_phase in {"early_rising", "midpoint", "crisis"}:
        seed = ripe_threads[0].get("seed_tag", "truth")
        if seed == "love":
            return SceneIntent(
                intent_id="misread_affection",
                label="一句话没说透，情意开始走偏",
                description="上一章没有说透的话开始反过来牵动关系，让人物既想靠近，又怕误会真的成形。",
                preferred_scene_functions=["misrecognition", "truth_trial", "debt_exchange"],
                preferred_tags=["love", "truth", "selfhood"],
            )
        return SceneIntent(
            intent_id="delayed_truth",
            label="那句没说透的话终于开始反咬",
            description="前面没有讲明白的真相开始在人物之间发酵，让局势不再只是推进，而是带着迟来的误会与回声。",
            preferred_scene_functions=["confession_window", "truth_trial", "karma_ripening"],
            preferred_tags=["truth", "selfhood", "reputation"],
        )
    if state.metadata.get("recent_delayed_payoff") and state.story_phase in {"climax", "aftermath"}:
        return SceneIntent(
            intent_id="paid_cost_residue",
            label="代价已经落下，余震却还在继续",
            description="真正残忍的不是代价本身，而是代价落下以后，人物才发现很多关系已经回不去原来的位置。",
            preferred_scene_functions=["debt_exchange", "karma_ripening", "confession_window"],
            preferred_tags=["sacrifice", "love", "reputation"],
        )
    if ripe_consequences and state.story_phase in {"midpoint", "crisis", "climax"}:
        return SceneIntent(
            intent_id="delayed_cost",
            label="旧代价终于追到门前",
            description="前面埋下的后果开始真正追上来，逼着人物在现在就为过去的决定付出具体代价。",
            preferred_scene_functions=["debt_exchange", "karma_ripening", "vow_payment"],
            preferred_tags=["sacrifice", "reputation", "loyalty"],
        )
    intents = SCENE_INTENTS.get(state.story_phase, SCENE_INTENTS["setup"])
    payoff_pressure = float(state.metadata.get("payoff_pressure", 0.0))
    if payoff_pressure >= 0.6 and state.story_phase in {"midpoint", "crisis", "climax"}:
        for intent in intents:
            if intent.intent_id in {"public_testimony", "sacrifice_test", "earned_choice"}:
                return intent
    active_themes = set(world.creator_controls.theme_targets or world.themes)
    for intent in intents:
        if active_themes & set(intent.preferred_tags):
            return intent
    return intents[0]


def _beat_target_for_phase(phase: str) -> int:
    return {
        "setup": 3,
        "early_rising": 3,
        "midpoint": 4,
        "crisis": 4,
        "climax": 5,
        "aftermath": 3,
    }.get(phase, 3)


def _progression_event_target(phase: str, beat_target: int) -> int:
    desired = {
        "setup": 2,
        "early_rising": 2,
        "midpoint": 2,
        "crisis": 3,
        "climax": 3,
        "aftermath": 1,
    }.get(phase, 2)
    return max(1, min(desired, beat_target))


def _adaptive_candidate_budget(
    state: NarrativeState,
    *,
    min_candidates: int,
    max_candidates: int,
) -> Tuple[int, int]:
    progression = dict((state.metadata or {}).get("longform_progression") or {})
    series_target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapter = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    diagnostics_mode = str((state.metadata or {}).get("longform_diagnostics_mode") or "")
    if series_target_chapters < 1000:
        return min_candidates, max_candidates
    if diagnostics_mode == "longform_1000":
        if current_chapter >= 900:
            return max(2, min(min_candidates, 2)), max(3, min(max_candidates, 3))
        if current_chapter >= 800:
            return max(2, min(min_candidates, 3)), max(4, min(max_candidates, 4))
        if current_chapter >= 700:
            return max(3, min(min_candidates, 4)), max(5, min(max_candidates, 5))
    if current_chapter >= 800:
        return max(3, min(min_candidates, 3)), max(4, min(max_candidates, 4))
    if current_chapter >= 750:
        return max(3, min(min_candidates, 4)), max(5, min(max_candidates, 5))
    if current_chapter >= 600:
        return max(4, min(min_candidates, 5)), max(7, min(max_candidates, 8))
    return min_candidates, max_candidates


def _adaptive_beat_target(state: NarrativeState, beat_target: int) -> int:
    progression = dict((state.metadata or {}).get("longform_progression") or {})
    series_target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapter = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    diagnostics_mode = str((state.metadata or {}).get("longform_diagnostics_mode") or "")
    if series_target_chapters < 1000:
        return beat_target
    if diagnostics_mode == "longform_1000":
        if current_chapter >= 900:
            return min(2, beat_target)
        if current_chapter >= 750:
            return min(3, beat_target)
    if current_chapter >= 800:
        return min(3, beat_target)
    if current_chapter >= 600:
        return min(4, beat_target)
    return beat_target


def _adaptive_progression_target(
    state: NarrativeState,
    progression_target: int,
) -> int:
    progression = dict((state.metadata or {}).get("longform_progression") or {})
    series_target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapter = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    diagnostics_mode = str((state.metadata or {}).get("longform_diagnostics_mode") or "")
    duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
    overdue_open_promises = sum(
        1
        for promise in state.open_promises
        if getattr(promise, "status", "") == "open" and int(getattr(promise, "due_by_turn", 0) or 0) <= int(state.turn_index or 0)
    )
    if state.story_phase == "aftermath" and progression_target < 2 and (
        len(state.open_promises) >= 3
        or overdue_open_promises > 0
        or duty_type in {"pace_breath", "expand_world", "resolve_promise", "advance_relationship", "deliver_climax"}
    ):
        progression_target = 2
    if state.story_phase == "aftermath" and duty_type in {"advance_relationship", "deliver_climax"}:
        progression_target = max(progression_target, 3)
    if state.story_phase == "aftermath" and duty_type in {"resolve_promise", "expand_world"} and (
        len(state.open_promises) >= 2 or overdue_open_promises > 0
    ):
        progression_target = max(progression_target, 3)
    if series_target_chapters < 1000:
        return progression_target
    if diagnostics_mode == "longform_1000":
        if current_chapter >= 900:
            return min(1, progression_target)
        if current_chapter >= 750:
            return min(2, progression_target)
    if current_chapter >= 800:
        return min(2, progression_target)
    return progression_target


def _adaptive_search_depth(state: NarrativeState, requested_depth: int) -> int:
    progression = dict((state.metadata or {}).get("longform_progression") or {})
    series_target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapter = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    diagnostics_mode = str((state.metadata or {}).get("longform_diagnostics_mode") or "")
    if series_target_chapters < 1000:
        return requested_depth
    if diagnostics_mode == "longform_1000":
        if current_chapter >= 900:
            return 0
        if current_chapter >= 750:
            return min(1, requested_depth)
    if current_chapter >= 800:
        return min(1, requested_depth)
    if current_chapter >= 600:
        return min(1, requested_depth)
    return requested_depth


def _budget_profile_for_state(
    state: NarrativeState,
    *,
    requested_beat_target: int,
    min_candidates: int,
    max_candidates: int,
) -> Dict[str, object]:
    adapted_beat_target = _adaptive_beat_target(state, requested_beat_target)
    adapted_progression_target = _adaptive_progression_target(
        state,
        _progression_event_target(state.story_phase, len(BEAT_BLUEPRINTS.get(adapted_beat_target, BEAT_BLUEPRINTS[3]))),
    )
    adapted_min_candidates, adapted_max_candidates = _adaptive_candidate_budget(
        state,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    return {
        "diagnostics_mode": str((state.metadata or {}).get("longform_diagnostics_mode") or ""),
        "requested_beat_target": requested_beat_target,
        "adapted_beat_target": adapted_beat_target,
        "adapted_progression_target": adapted_progression_target,
        "adapted_min_candidates": adapted_min_candidates,
        "adapted_max_candidates": adapted_max_candidates,
    }


def _score_scene_fit(scene_intent: SceneIntent, event: EventAtom) -> float:
    score = 0.0
    if event.scene_function in scene_intent.preferred_scene_functions:
        score += 0.25
    score += 0.1 * len(set(event.tags) & set(scene_intent.preferred_tags))
    return score


def _score_job_fit(job: str, event: EventAtom, *, is_last_beat: bool) -> float:
    score = 0.0
    for rank, scene_function in enumerate(JOB_FUNCTION_PRIORITIES.get(job, [])):
        if event.scene_function == scene_function:
            score += max(0.05, 0.24 - 0.04 * rank)
            break
    if is_terminal_scene_function(event.scene_function, event.metadata) and not is_last_beat:
        score -= 0.85
    if job == "echo" and event.scene_function in {"debt_exchange", "karma_ripening"}:
        score += 0.08
    return score


def _repeat_penalty(candidate: EventAtom, chosen_events: Sequence[EventAtom]) -> float:
    penalty = 0.0
    for prior in chosen_events:
        if candidate.event_id == prior.event_id:
            penalty += 0.75
            continue
        if candidate.location and candidate.location == prior.location:
            penalty += 0.05
        if candidate.scene_function == prior.scene_function:
            penalty += 0.06
        if set(candidate.tags) & set(prior.tags):
            penalty += 0.03
    return penalty


def _phase_penalty(state: NarrativeState, event: EventAtom) -> float:
    if is_terminal_scene_function(event.scene_function, event.metadata):
        chapters_remaining = max(0, int(state.min_end_turn) - int(state.chapter_index))
        if chapters_remaining >= 6:
            return 0.95
        if chapters_remaining >= 3:
            return 0.75
        if chapters_remaining >= 1:
            return 0.45
    if state.story_phase in {"setup", "early_rising"} and event.scene_function in {"humiliation", "vow_payment", "karma_ripening"}:
        return 0.45
    if state.story_phase == "midpoint" and is_terminal_scene_function(event.scene_function, event.metadata):
        return 0.35
    return 0.0


def _render_spec_for_scene(state: NarrativeState, scene_intent: SceneIntent) -> SceneRenderSpec:
    prose_mode = {
        "setup": "novel_light",
        "early_rising": "novel_lush",
        "midpoint": "novel_lush",
        "crisis": "manhua_drama",
        "climax": "manhua_drama",
        "aftermath": "novel_light",
    }.get(state.story_phase, "novel_lush")
    base_target_word_count = max(int(state.word_budget or 2000), 2000)
    authoring_surface = str((state.metadata or {}).get("authoring_surface") or "")
    if authoring_surface == "author_work_generation":
        target_word_count = min(max(base_target_word_count, 1800), 2000)
        min_target_word_count = 1800
        max_target_word_count = 2200
    elif state.story_phase in {"setup", "early_rising"}:
        target_word_count = base_target_word_count
        min_target_word_count = max(1800, target_word_count - 200)
        max_target_word_count = max(target_word_count, target_word_count + 200)
    else:
        target_word_count = base_target_word_count
        min_target_word_count = max(200, target_word_count - 200)
        max_target_word_count = max(target_word_count, target_word_count + 200)
    return SceneRenderSpec(
        prose_mode=prose_mode,
        viewpoint_character="",
        target_word_count=target_word_count,
        dialogue_density=0.32 if prose_mode == "novel_light" else (0.4 if prose_mode == "manhua_drama" else 0.35),
        sensory_motifs=scene_intent.preferred_tags[:3],
        emotional_pivot=scene_intent.label,
        ending_cadence="lingering" if prose_mode != "manhua_drama" else "hard_cut",
        min_target_word_count=min_target_word_count,
        max_target_word_count=max_target_word_count,
        must_include_beats=[scene_intent.label],
    )


def _trace_entry_from_scored_candidate(candidate) -> Dict[str, object]:
    return {
        "event_id": candidate.event.event_id,
        "total_score": candidate.total_score,
        "critic_penalty": candidate.critic_penalty,
        "components": dict(candidate.components),
        "critic_decisions": [
            decision.to_dict() for decision in candidate.critic_decisions
        ],
        "explanation": candidate.explanation,
    }


def _chosen_candidate_summary(chosen_trace: Sequence[Dict[str, object]]) -> Dict[str, object]:
    if not chosen_trace:
        return {}
    first = dict(chosen_trace[0] or {})
    return {
        "event_id": first.get("event_id"),
        "total_score": first.get("total_score"),
        "critic_penalty": first.get("critic_penalty"),
        "components": dict(first.get("components") or {}),
        "critic_decisions": list(first.get("critic_decisions") or []),
        "explanation": first.get("explanation"),
    }


def _debug_route_from_scene_beats(
    scene_beats: Sequence[SceneBeat],
    chosen_trace: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    events = [beat.event.to_dict() for beat in scene_beats]
    total_score = round(
        sum(float(item.get("total_score", 0.0) or 0.0) for item in chosen_trace),
        3,
    )
    component_totals: Dict[str, float] = {}
    for item in chosen_trace:
        for key, value in dict(item.get("components") or {}).items():
            component_totals[str(key)] = component_totals.get(str(key), 0.0) + float(value or 0.0)
    event_count = max(1, len(scene_beats))
    score_breakdown = {
        key: round(value / float(event_count), 3)
        for key, value in component_totals.items()
    }
    event_ids = [event["event_id"] for event in events if event.get("event_id")]
    return {
        "events": events,
        "event_ids": event_ids,
        "total_score": total_score,
        "score_breakdown": score_breakdown,
        "critic_trace": [dict(item) for item in chosen_trace],
        "explanation": "scene_route=%s; total_score=%.3f"
        % (" -> ".join(event_ids), total_score),
    }


def _projected_followup_event(
    source_event: EventAtom,
    *,
    dramatic_job: str,
    beat_index: int,
) -> EventAtom:
    payload = source_event.to_dict()
    label = {
        "pivot": "真正要转向的那句终于逼到眼前",
        "aftermath": "说出口后的余波开始追到账前",
        "echo": "没认完的后半句顺着回声追上来",
    }.get(dramatic_job, "这一拍留下来的余波开始显形")
    payload["event_id"] = f"{source_event.event_id}__beat_projection__{beat_index}_{dramatic_job}"
    payload["title"] = f"{source_event.title} · {label}"
    location = source_event.location or "原处"
    payload["summary"] = f"{label}继续压在{location}里，刚才没说透的态度、代价和退路都被逼到明处。"
    payload["metadata"] = {
        **dict(payload.get("metadata") or {}),
        "beat_projection": True,
        "beat_projection_of": source_event.event_id,
        "beat_projection_job": dramatic_job,
    }
    return EventAtom.from_dict(payload)


def simulate_scene_beats(
    state: NarrativeState,
    *,
    world: WorldBible,
    candidate_provider: CandidateProvider,
    critics: Sequence[BaseCritic],
    weights: SearchWeights,
    scene_intent: SceneIntent,
    beat_target: int,
    candidate_reranker: Optional[Callable[..., Dict[str, object]]] = None,
    min_candidates: int = 6,
    max_candidates: int = 10,
 ) -> Tuple[List[SceneBeat], NarrativeState, List[Dict[str, object]], Dict[str, object]]:
    current_state = NarrativeState.from_dict(state.to_dict())
    scene_beats: List[SceneBeat] = []
    chosen_events: List[EventAtom] = []
    rerank_receipts: List[Dict[str, object]] = []
    first_candidate_batch = None
    first_scored_candidates = []
    chosen_trace: List[Dict[str, object]] = []
    beat_candidate_trace: List[Dict[str, object]] = []
    beat_target = _adaptive_beat_target(state, beat_target)
    beat_blueprint = BEAT_BLUEPRINTS.get(beat_target, BEAT_BLUEPRINTS[3])
    progression_target = _adaptive_progression_target(
        state,
        _progression_event_target(state.story_phase, len(beat_blueprint)),
    )

    for beat_index, (prefix, job) in enumerate(beat_blueprint, start=1):
        if beat_index > progression_target:
            if not chosen_events:
                break
            echo_source = chosen_events[-1] if job in {"pivot", "aftermath", "echo"} else chosen_events[0]
            projected_event = _projected_followup_event(
                echo_source,
                dramatic_job=job,
                beat_index=beat_index,
            )
            scene_beats.append(
                SceneBeat(
                    beat_index=beat_index,
                    event=projected_event,
                    beat_label="%s：%s" % (prefix, projected_event.title),
                    dramatic_job=job,
                    tension_after=current_state.tension,
                )
            )
            continue

        candidate_batch, scored_candidates = evaluate_candidates(
            current_state,
            world,
            candidate_provider=candidate_provider,
            critics=critics,
            weights=weights,
            depth=_adaptive_search_depth(state, min(beat_index - 1, 2)),
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        if first_candidate_batch is None:
            first_candidate_batch = candidate_batch
            first_scored_candidates = list(scored_candidates)
        beat_trace_entry = {
            "beat_index": beat_index,
            "dramatic_job": job,
            "search_depth": _adaptive_search_depth(state, min(beat_index - 1, 2)),
            "requested_min_candidates": min_candidates,
            "requested_max_candidates": max_candidates,
            "raw_candidate_count": len(list(candidate_batch.raw_candidates or [])),
            "legal_candidate_count": len(list(candidate_batch.legal_candidates or [])),
            "scored_candidate_count": len(list(scored_candidates or [])),
            "critic_rejection_count": len(list((candidate_batch.debug or {}).get("critic_rejections", []) or [])),
            "evaluate_candidates_timing_ms": dict((candidate_batch.debug or {}).get("timing_ms") or {}),
        }
        if not scored_candidates:
            beat_candidate_trace.append(beat_trace_entry)
            break

        ranked_candidates = sorted(
            scored_candidates,
            key=lambda candidate: (
                -(
                    candidate.total_score
                    + _score_scene_fit(scene_intent, candidate.event)
                    + _score_job_fit(job, candidate.event, is_last_beat=beat_index == len(beat_blueprint))
                    - _phase_penalty(current_state, candidate.event)
                    - _repeat_penalty(candidate.event, chosen_events)
                ),
                candidate.event.event_id,
            ),
        )
        if not ranked_candidates:
            break

        if candidate_reranker is not None:
            rerank_result = candidate_reranker(
                current_state=current_state,
                world=world,
                ranked_candidates=ranked_candidates,
                beat_index=beat_index,
                dramatic_job=job,
                scene_intent=scene_intent,
                candidate_batch=candidate_batch,
                chosen_events=chosen_events,
            )
            reranked = list(rerank_result.get("ranked_candidates") or [])
            if reranked:
                ranked_candidates = reranked
            receipt = rerank_result.get("receipt")
            if receipt:
                rerank_receipts.append(dict(receipt))
        beat_trace_entry["ranked_candidate_count"] = len(list(ranked_candidates or []))

        chosen_candidate = next(
            (
                candidate
                for candidate in ranked_candidates
                if candidate.event.event_id not in {event.event_id for event in chosen_events}
            ),
            ranked_candidates[0],
        )
        chosen_event = chosen_candidate.event
        beat_trace_entry["selected_event_id"] = chosen_event.event_id
        chosen_trace.append(_trace_entry_from_scored_candidate(chosen_candidate))
        beat_candidate_trace.append(beat_trace_entry)
        current_state = apply_event(current_state, chosen_event)
        chosen_events.append(chosen_event)
        scene_beats.append(
            SceneBeat(
                beat_index=beat_index,
                event=chosen_event,
                beat_label="%s：%s" % (prefix, chosen_event.title),
                dramatic_job=job,
                tension_after=current_state.tension,
            )
        )

    return scene_beats, current_state, rerank_receipts, {
        "first_candidate_batch": first_candidate_batch,
        "first_scored_candidates": list(first_scored_candidates),
        "chosen_trace": list(chosen_trace),
        "beat_candidate_trace": list(beat_candidate_trace),
    }


def plan_next_scene(
    state: NarrativeState,
    *,
    world: WorldBible,
    candidate_provider: CandidateProvider,
    critics: Sequence[BaseCritic],
    weights: SearchWeights,
    candidate_reranker: Optional[Callable[..., Dict[str, object]]] = None,
    min_candidates: int = 6,
    max_candidates: int = 10,
) -> Tuple[Optional[ChapterPlan], List[SceneBeat], NarrativeState, SceneRenderSpec, List[Dict[str, object]], Dict[str, object]]:
    planning_state = NarrativeState.from_dict(state.to_dict())
    sync_longform_progression(planning_state, world)
    scene_intent = _pick_scene_intent(planning_state, world)
    beat_target = _beat_target_for_phase(state.story_phase)
    budgeted_min_candidates, budgeted_max_candidates = _adaptive_candidate_budget(
        planning_state,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    scene_beats, scene_state, rerank_receipts, search_trace = simulate_scene_beats(
        planning_state,
        world=world,
        candidate_provider=candidate_provider,
        critics=critics,
        weights=weights,
        scene_intent=scene_intent,
        beat_target=beat_target,
        candidate_reranker=candidate_reranker,
        min_candidates=budgeted_min_candidates,
        max_candidates=budgeted_max_candidates,
    )
    if not scene_beats:
        return None, [], state, _render_spec_for_scene(state, scene_intent), rerank_receipts, search_trace

    finalized_state = NarrativeState.from_dict(scene_state.to_dict())
    advance_story_phase_if_needed(finalized_state, scene_intent_id=scene_intent.intent_id)
    longform_progression = sync_longform_progression(finalized_state, world)
    chapter_task = dict(longform_progression.get("chapter_task") or default_chapter_task(finalized_state, world))
    finalized_state.current_chapter_task = dict(chapter_task)
    render_spec = _render_spec_for_scene(finalized_state, scene_intent)
    selected_event_ids = list(dict.fromkeys(beat.event.event_id for beat in scene_beats))
    chapter_plan = ChapterPlan(
        chapter_index=finalized_state.chapter_index,
        story_phase=finalized_state.story_phase,
        scene_intent=scene_intent,
        beat_target=beat_target,
        beat_count=len(scene_beats),
        ending_ready=(
            is_terminal_scene_function(scene_beats[-1].event.scene_function, scene_beats[-1].event.metadata)
            and longform_terminal_allowed(finalized_state, chapter_task, scene_beats[-1].event)
        ),
        selected_event_ids=selected_event_ids,
        chapter_task=dict(chapter_task),
        chapter_task_execution_summary={
            "duty_type": chapter_task.get("duty_type"),
            "target_words": chapter_task.get("target_words"),
            "reveal_budget": chapter_task.get("reveal_budget"),
            "promise_actions": list(chapter_task.get("promise_actions", [])),
            "selected_event_count": len(selected_event_ids),
            "series_chapter_index": longform_progression.get("series_chapter_index"),
            "series_target_chapters": longform_progression.get("series_target_chapters"),
            "volume_id": longform_progression.get("volume_id"),
            "volume_chapter_index": longform_progression.get("volume_chapter_index"),
            "volume_target_chapters": longform_progression.get("volume_target_chapters"),
            "arc_id": longform_progression.get("arc_id"),
            "arc_chapter_index": longform_progression.get("arc_chapter_index"),
            "arc_target_chapters": longform_progression.get("arc_target_chapters"),
            "task_sequence_index": longform_progression.get("task_sequence_index"),
            "used_fallback": bool(longform_progression.get("used_fallback", False)),
            "ending_gate_blocked": is_terminal_scene_function(scene_beats[-1].event.scene_function, scene_beats[-1].event.metadata)
            and not longform_terminal_allowed(finalized_state, chapter_task, scene_beats[-1].event),
        },
    )
    return chapter_plan, scene_beats, finalized_state, render_spec, rerank_receipts, search_trace


def render_scene(
    world: WorldBible,
    state_before: NarrativeState,
    state_after: NarrativeState,
    chapter_plan: ChapterPlan,
    scene_beats: List[SceneBeat],
    render_spec: SceneRenderSpec,
    renderer: Renderer,
) -> Dict[str, object]:
    return renderer.render_scene(
        world,
        state_before,
        state_after,
        chapter_plan,
        scene_beats,
        render_spec,
    ).to_dict()


def _state_summary(state: NarrativeState) -> Dict[str, object]:
    return {
        "story_phase": state.story_phase,
        "chapter_index": state.chapter_index,
        "turn_index": state.turn_index,
        "tension": round(state.tension, 3),
        "open_promise_count": len(state.open_promises),
    }


def plan_next_turn(
    state: NarrativeState,
    *,
    world: WorldBible,
    candidate_provider: CandidateProvider,
    critics: Optional[Sequence[BaseCritic]] = None,
    renderer: Optional[Renderer] = None,
    beam_width: int = 3,
    depth: int = 2,
    weights: Optional[SearchWeights] = None,
    candidate_reranker: Optional[Callable[..., Dict[str, object]]] = None,
    min_candidates: int = 6,
    max_candidates: int = 10,
    debug: bool = False,
) -> Dict:
    active_critics = list(critics or default_critics())
    active_renderer = renderer or TemplateRenderer()
    resolved_weights = resolve_search_weights(world, weights=weights)

    chapter_plan, scene_beats, updated_state, render_spec, assisted_rerank_receipts, search_trace = plan_next_scene(
        state,
        world=world,
        candidate_provider=candidate_provider,
        critics=active_critics,
        weights=resolved_weights,
        candidate_reranker=candidate_reranker,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    debug_candidate_batch = (
        search_trace.get("first_candidate_batch")
        if isinstance(search_trace, dict)
        else None
    )
    debug_scored_candidates = list(
        search_trace.get("first_scored_candidates") or []
    ) if isinstance(search_trace, dict) else []
    debug_critic_trace = list(
        search_trace.get("chosen_trace") or []
    ) if isinstance(search_trace, dict) else []
    beat_candidate_trace = list(
        search_trace.get("beat_candidate_trace") or []
    ) if isinstance(search_trace, dict) else []
    debug_routes = (
        [_debug_route_from_scene_beats(scene_beats, debug_critic_trace)]
        if scene_beats
        else []
    )
    planner_trace_summary = {
        **_budget_profile_for_state(
            state,
            requested_beat_target=_beat_target_for_phase(state.story_phase),
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        ),
        "per_beat": beat_candidate_trace,
        "max_raw_candidate_count": max((int(item.get("raw_candidate_count", 0) or 0) for item in beat_candidate_trace), default=0),
        "max_scored_candidate_count": max((int(item.get("scored_candidate_count", 0) or 0) for item in beat_candidate_trace), default=0),
        "max_provider_latency_ms": max((float(dict(item.get("evaluate_candidates_timing_ms") or {}).get("provider", 0.0) or 0.0) for item in beat_candidate_trace), default=0.0),
        "max_critics_latency_ms": max((float(dict(item.get("evaluate_candidates_timing_ms") or {}).get("critics", 0.0) or 0.0) for item in beat_candidate_trace), default=0.0),
        "max_scoring_latency_ms": max((float(dict(item.get("evaluate_candidates_timing_ms") or {}).get("scoring", 0.0) or 0.0) for item in beat_candidate_trace), default=0.0),
        "max_sort_latency_ms": max((float(dict(item.get("evaluate_candidates_timing_ms") or {}).get("sort", 0.0) or 0.0) for item in beat_candidate_trace), default=0.0),
        "max_total_evaluate_latency_ms": max((float(dict(item.get("evaluate_candidates_timing_ms") or {}).get("total", 0.0) or 0.0) for item in beat_candidate_trace), default=0.0),
    }
    chosen_candidate_summary = _chosen_candidate_summary(debug_critic_trace)
    if chapter_plan is None or not scene_beats:
        return {
            "status": "no_legal_routes",
            "reader_view": None,
            "updated_state_summary": _state_summary(state),
            "replay_preview": {"chapter_index": state.chapter_index, "latest_title": None},
            "candidate_batch": debug_candidate_batch.to_dict() if debug_candidate_batch is not None else {"raw_candidates": [], "legal_candidates": [], "illegal_candidate_reasons": {}, "debug": {}},
            "scored_candidates": [candidate.to_dict() for candidate in debug_scored_candidates],
            "routes": debug_routes,
            "critic_trace": debug_critic_trace,
            "rendered_scene": None,
            "updated_state": state.to_dict(),
            "chapter_plan": None,
            "scene_beats": [],
            "scene_render_spec": render_spec.to_dict(),
            "assisted_rerank_receipts": assisted_rerank_receipts,
            "longform_context_pack": build_longform_context_pack(state),
            "planner_trace_summary": planner_trace_summary,
            "chosen_candidate_summary": chosen_candidate_summary,
        }

    rendered_scene = active_renderer.render_scene(
        world,
        state,
        updated_state,
        chapter_plan,
        scene_beats,
        render_spec,
    )
    reader_view = present_scene_for_reader(
        world,
        state,
        updated_state,
        chapter_plan,
        scene_beats,
        rendered_scene,
    )
    updated_state = archive_longform_chapter(
        updated_state,
        chapter_plan=chapter_plan,
        chosen_event=scene_beats[0].event,
        rendered_body=reader_view.body,
    )
    longform_context_pack = build_longform_context_pack(updated_state)

    response = {
        "status": "ok",
        "reader_view": reader_view.to_dict(),
        "updated_state_summary": _state_summary(updated_state),
        "replay_preview": {
            "chapter_index": updated_state.chapter_index,
            "latest_title": reader_view.chapter_title,
        },
        "chosen_event": scene_beats[0].event.to_dict(),
        "updated_state": updated_state.to_dict(),
        "chapter_plan": chapter_plan.to_dict(),
        "planner_trace_summary": planner_trace_summary,
        "chosen_candidate_summary": chosen_candidate_summary,
    }

    if debug:
        response.update(
            {
                "best_route_event_ids": list(debug_routes[0].get("event_ids", [])) if debug_routes else [],
                "candidate_batch": debug_candidate_batch.to_dict() if debug_candidate_batch is not None else {"raw_candidates": [], "legal_candidates": [], "illegal_candidate_reasons": {}, "debug": {}},
                "scored_candidates": [candidate.to_dict() for candidate in debug_scored_candidates],
                "routes": debug_routes,
                "critic_trace": debug_critic_trace,
                "rendered_scene": rendered_scene.to_dict(),
                "scene_beats": [beat.to_dict() for beat in scene_beats],
                "scene_render_spec": render_spec.to_dict(),
                "assisted_rerank_receipts": assisted_rerank_receipts,
                "longform_context_pack": longform_context_pack,
            }
        )

    return response


def plan_next_turn_from_events(
    state: NarrativeState,
    candidate_events: Sequence[EventAtom],
    *,
    world: WorldBible,
    critics: Optional[Sequence[BaseCritic]] = None,
    renderer: Optional[Renderer] = None,
    beam_width: int = 3,
    depth: int = 2,
    weights: Optional[SearchWeights] = None,
    candidate_reranker: Optional[Callable[..., Dict[str, object]]] = None,
    min_candidates: int = 6,
    max_candidates: int = 10,
    debug: bool = False,
) -> Dict:
    provider = StaticCandidateProvider(candidate_events)
    return plan_next_turn(
        state,
        world=world,
        candidate_provider=provider,
        critics=critics,
        renderer=renderer,
        beam_width=beam_width,
        depth=depth,
        weights=weights,
        candidate_reranker=candidate_reranker,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
        debug=debug,
    )
