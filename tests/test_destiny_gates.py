from src.narrativeos.canon import hard_constraint_errors
from src.narrativeos.models import EventAtom, NarrativeState


def _terminal_event(shape: str) -> EventAtom:
    return EventAtom.from_dict(
        {
            "event_id": "terminal_%s" % shape,
            "title": "终局 %s" % shape,
            "summary": "人物来到命运要结算的一幕。",
            "location": "渡口",
            "actors": ["yu_cheng"],
            "scene_function": "vow_payment",
            "tags": ["selfhood", "cost"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": ["fate_closes"],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": -0.05,
            "theme_impacts": {},
            "agency_affordances": ["selfhood"],
            "rating_ceiling": "PG",
            "temptation_vector": {},
            "vow_tests": ["live_the_vow_openly"],
            "wound_triggers": ["永远要证明自己才值得被留下"],
            "debt_deltas": [],
            "karmic_seed_creations": [],
            "karmic_seed_resolutions": [],
            "awakening_affordances": ["vow_payment"],
            "concealment_level": 0.0,
            "consequence_delay_hint": 0,
            "metadata": {
                "terminal": True,
                "endgame_shape": shape,
                "required_fate_pressure": 0.55,
                "required_inescapable_nodes": ["为愿付出代价"],
                "ending_gate": {
                    "min_turn": 8,
                    "required_scene_functions": ["mask_crack", "truth_trial", "debt_exchange"],
                    "required_closed_promises": [],
                    "required_tension_min": 0.5,
                },
            },
        }
    )


def test_terminal_gate_blocks_before_min_end_turn(demo_world, demo_state):
    event = _terminal_event("awakening")
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.chapter_index = 5
    state.story_phase = "midpoint"
    state.fate_pressure = 0.8
    errors = hard_constraint_errors(state, event, world=demo_world)
    assert "fate_min_end_turn" in errors


def test_terminal_gate_requires_allowed_endgame_shape(demo_world, demo_state):
    event = _terminal_event("impossible_shape")
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.chapter_index = 9
    state.story_phase = "climax"
    state.fate_pressure = 0.8
    state.metadata["scene_history"] = ["mask_crack", "truth_trial", "debt_exchange"]
    errors = hard_constraint_errors(state, event, world=demo_world)
    assert "endgame_shape_not_permitted" in errors


def test_awakening_terminal_can_pass_gate_when_destiny_and_phase_are_ready(demo_world, demo_state):
    event = _terminal_event("awakening")
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.chapter_index = 9
    state.story_phase = "climax"
    state.fate_pressure = 0.8
    state.world_facts.append("为愿付出代价")
    state.metadata["scene_history"] = ["mask_crack", "truth_trial", "debt_exchange"]
    errors = hard_constraint_errors(state, event, world=demo_world)
    assert "fate_min_end_turn" not in errors
    assert "endgame_shape_not_permitted" not in errors
