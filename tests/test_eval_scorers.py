from src.narrativeos.eval.scorers import (
    choice_distinctness,
    derive_scoring_issues,
    hook_quality,
    monetize_ready,
    readability,
    scene_density,
)
from src.narrativeos.models import EvaluationScores, NarrativeState
from src.narrativeos.pipeline import _phase_penalty
from src.narrativeos.models import EventAtom


def test_readability_and_scene_density_have_positive_cases():
    text = "“你先别退。”她按住杯沿。灯影落在窗纸上，风从檐下掠过去。"
    assert readability(text) > 0.3
    assert scene_density(1, 3, 3, text) > 0.2


def test_choice_distinctness_and_hook_quality():
    assert choice_distinctness(["先问真相", "先保住她", "先顺着局势"]) > 0.6
    assert hook_quality("话停在这里，可下一次开口时，谁都不可能还是刚才那个人。") > 0.7


def test_monetize_ready_respects_paywall_continuity():
    assert monetize_ready(0.8, "这是一段足够长的正文。" * 80, True) > monetize_ready(0.2, "短。", False)


def test_q04_q05_q08_q09_soft_issues_are_derived():
    state = NarrativeState.from_dict(
        {
            "state_id": "s",
            "world_id": "w",
            "turn_index": 0,
            "story_phase": "midpoint",
            "chapter_index": 3,
            "min_end_turn": 8,
            "fate_pressure": 0.1,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.5,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    )
    scores = EvaluationScores(
        readability=0.7,
        scene_density=0.3,
        character_fidelity=0.8,
        causal_continuity=0.8,
        pacing=0.35,
        choice_distinctness=0.3,
        hook_quality=0.3,
        monetize_ready=0.4,
        overall_score=0.5,
    )
    issues = derive_scoring_issues(
        scores=scores,
        exposition_ratio=0.55,
        concrete_detail_density=0.001,
        ending_ready=False,
        state_after=state,
    )
    codes = {issue.issue_code for issue in issues}
    assert {"Q04", "Q05", "Q08", "Q09"} <= codes


def test_phase_penalty_strongly_discourages_terminal_events_before_min_end_turn():
    state = NarrativeState.from_dict(
        {
            "state_id": "s",
            "world_id": "w",
            "turn_index": 0,
            "story_phase": "early_rising",
            "chapter_index": 4,
            "min_end_turn": 10,
            "fate_pressure": 0.1,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.5,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    )
    terminal = EventAtom.from_dict(
        {
            "event_id": "terminal",
            "title": "结局",
            "summary": "一切都结束了",
            "actors": [],
            "scene_function": "vow_payment",
            "tags": [],
            "preconditions_all": [],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": [],
            "rating_ceiling": "PG13",
            "temptation_vector": {},
            "vow_tests": [],
            "wound_triggers": [],
            "debt_deltas": [],
            "karmic_seed_creations": [],
            "karmic_seed_resolutions": [],
            "awakening_affordances": [],
            "concealment_level": 0.0,
            "consequence_delay_hint": 0,
            "metadata": {"terminal": True},
        }
    )
    non_terminal = EventAtom.from_dict(
        {
            "event_id": "non_terminal",
            "title": "继续试探",
            "summary": "局势还没完",
            "actors": [],
            "scene_function": "truth_trial",
            "tags": [],
            "preconditions_all": [],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": [],
            "rating_ceiling": "PG13",
            "temptation_vector": {},
            "vow_tests": [],
            "wound_triggers": [],
            "debt_deltas": [],
            "karmic_seed_creations": [],
            "karmic_seed_resolutions": [],
            "awakening_affordances": [],
            "concealment_level": 0.0,
            "consequence_delay_hint": 0,
            "metadata": {},
        }
    )
    assert _phase_penalty(state, terminal) > _phase_penalty(state, non_terminal)
    assert _phase_penalty(state, terminal) >= 0.75
