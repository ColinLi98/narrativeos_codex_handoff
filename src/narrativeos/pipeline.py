from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .critics import BaseCritic, default_critics
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
from .search import beam_search, evaluate_candidates


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
    return SceneRenderSpec(
        prose_mode=prose_mode,
        viewpoint_character="",
        target_word_count={
            "novel_light": 650,
            "novel_lush": 950,
            "manhua_drama": 780,
        }[prose_mode],
        dialogue_density=0.32 if prose_mode == "novel_light" else (0.4 if prose_mode == "manhua_drama" else 0.35),
        sensory_motifs=scene_intent.preferred_tags[:3],
        emotional_pivot=scene_intent.label,
        ending_cadence="lingering" if prose_mode != "manhua_drama" else "hard_cut",
        must_include_beats=[scene_intent.label],
    )


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
) -> Tuple[List[SceneBeat], NarrativeState, List[Dict[str, object]]]:
    current_state = NarrativeState.from_dict(state.to_dict())
    scene_beats: List[SceneBeat] = []
    chosen_events: List[EventAtom] = []
    rerank_receipts: List[Dict[str, object]] = []
    beat_blueprint = BEAT_BLUEPRINTS.get(beat_target, BEAT_BLUEPRINTS[3])
    progression_target = _progression_event_target(state.story_phase, len(beat_blueprint))

    for beat_index, (prefix, job) in enumerate(beat_blueprint, start=1):
        if beat_index > progression_target:
            if not chosen_events:
                break
            echo_source = chosen_events[-1] if job in {"pivot", "aftermath", "echo"} else chosen_events[0]
            scene_beats.append(
                SceneBeat(
                    beat_index=beat_index,
                    event=echo_source,
                    beat_label="%s：%s" % (prefix, echo_source.title),
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
            depth=min(beat_index - 1, 2),
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        if not scored_candidates:
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

        chosen_candidate = next(
            (
                candidate
                for candidate in ranked_candidates
                if candidate.event.event_id not in {event.event_id for event in chosen_events}
            ),
            ranked_candidates[0],
        )
        chosen_event = chosen_candidate.event
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

    return scene_beats, current_state, rerank_receipts


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
) -> Tuple[Optional[ChapterPlan], List[SceneBeat], NarrativeState, SceneRenderSpec, List[Dict[str, object]]]:
    scene_intent = _pick_scene_intent(state, world)
    beat_target = _beat_target_for_phase(state.story_phase)
    scene_beats, scene_state, rerank_receipts = simulate_scene_beats(
        state,
        world=world,
        candidate_provider=candidate_provider,
        critics=critics,
        weights=weights,
        scene_intent=scene_intent,
        beat_target=beat_target,
        candidate_reranker=candidate_reranker,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    if not scene_beats:
        return None, [], state, _render_spec_for_scene(state, scene_intent), rerank_receipts

    finalized_state = NarrativeState.from_dict(scene_state.to_dict())
    advance_story_phase_if_needed(finalized_state, scene_intent_id=scene_intent.intent_id)
    render_spec = _render_spec_for_scene(finalized_state, scene_intent)
    chapter_plan = ChapterPlan(
        chapter_index=finalized_state.chapter_index,
        story_phase=finalized_state.story_phase,
        scene_intent=scene_intent,
        beat_target=beat_target,
        beat_count=len(scene_beats),
        ending_ready=is_terminal_scene_function(scene_beats[-1].event.scene_function, scene_beats[-1].event.metadata),
        selected_event_ids=[beat.event.event_id for beat in scene_beats],
    )
    return chapter_plan, scene_beats, finalized_state, render_spec, rerank_receipts


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

    candidate_batch, scored_candidates = evaluate_candidates(
        state,
        world,
        candidate_provider=candidate_provider,
        critics=active_critics,
        weights=resolved_weights,
        depth=0,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    routes = beam_search(
        state,
        world=world,
        candidate_provider=candidate_provider,
        critics=active_critics,
        depth=depth,
        beam_width=beam_width,
        weights=resolved_weights,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )

    chapter_plan, scene_beats, updated_state, render_spec, assisted_rerank_receipts = plan_next_scene(
        state,
        world=world,
        candidate_provider=candidate_provider,
        critics=active_critics,
        weights=resolved_weights,
        candidate_reranker=candidate_reranker,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    if chapter_plan is None or not scene_beats:
        return {
            "status": "no_legal_routes",
            "reader_view": None,
            "updated_state_summary": _state_summary(state),
            "replay_preview": {"chapter_index": state.chapter_index, "latest_title": None},
            "candidate_batch": candidate_batch.to_dict(),
            "scored_candidates": [candidate.to_dict() for candidate in scored_candidates],
            "routes": [route.to_dict() for route in routes],
            "critic_trace": [],
            "rendered_scene": None,
            "updated_state": state.to_dict(),
            "chapter_plan": None,
            "scene_beats": [],
            "scene_render_spec": render_spec.to_dict(),
            "assisted_rerank_receipts": assisted_rerank_receipts,
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

    response = {
        "status": "ok",
        "reader_view": reader_view.to_dict(),
        "updated_state_summary": _state_summary(updated_state),
        "replay_preview": {
            "chapter_index": updated_state.chapter_index,
            "latest_title": reader_view.chapter_title,
        },
    }

    if debug:
        response.update(
            {
                "chosen_event": scene_beats[0].event.to_dict(),
                "updated_state": updated_state.to_dict(),
                "best_route_event_ids": [event.event_id for event in routes[0].events] if routes else [],
                "candidate_batch": candidate_batch.to_dict(),
                "scored_candidates": [candidate.to_dict() for candidate in scored_candidates],
                "routes": [route.to_dict() for route in routes],
                "critic_trace": routes[0].critic_trace if routes else [],
                "rendered_scene": rendered_scene.to_dict(),
                "chapter_plan": chapter_plan.to_dict(),
                "scene_beats": [beat.to_dict() for beat in scene_beats],
                "scene_render_spec": render_spec.to_dict(),
                "assisted_rerank_receipts": assisted_rerank_receipts,
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
