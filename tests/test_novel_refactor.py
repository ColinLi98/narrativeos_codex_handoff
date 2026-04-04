from src.narrativeos.canon import hard_constraint_errors
from src.narrativeos.memory import advance_story_phase_if_needed, apply_event
from src.narrativeos.models import EventAtom, NarrativeState
from src.narrativeos.pipeline import plan_next_turn_from_events
from src.narrativeos.sanitizer import contains_engineering_leak, sanitize_text
from src.narrativeos.scoring import dramatic_tension_delta


def test_story_phase_advances_by_chapter(demo_state):
    state = NarrativeState.from_dict(demo_state.to_dict())
    seen = []
    for intent in ["false_calm", "public_pressure", "social_humiliation", "earned_choice"]:
        advance_story_phase_if_needed(state, scene_intent_id=intent)
        seen.append((state.chapter_index, state.story_phase))

    assert seen[0][1] == "setup"
    assert seen[1][1] in {"setup", "early_rising"}
    assert seen[-1][0] == 4


def test_terminal_vow_payment_is_blocked_before_chapter_six(demo_world, demo_state):
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.chapter_index = 5
    state.story_phase = "midpoint"
    state.tension = 0.95
    state.fate_pressure = 0.6
    state.metadata["scene_history"] = ["mask_crack", "truth_trial", "debt_exchange"]
    state.metadata["closed_promise_ids"] = ["must_choose_new_future"]

    terminal_event = EventAtom.from_dict(
        {
            "event_id": "early_terminal_vow",
            "title": "过早的终局兑现",
            "summary": "故事还没走够章节，就想让人物直接把命运结算掉。",
            "location": "渡口",
            "actors": ["yu_cheng"],
            "scene_function": "vow_payment",
            "tags": ["selfhood", "cost"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": ["new_ending"],
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
                "endgame_shape": "awakening",
                "required_fate_pressure": 0.45,
                "required_inescapable_nodes": ["为愿付出代价"],
                "ending_gate": {
                    "min_turn": 8,
                    "required_scene_functions": ["mask_crack", "truth_trial", "debt_exchange"],
                    "required_closed_promises": ["must_choose_new_future"],
                    "required_tension_min": 0.8,
                },
            },
        }
    )

    errors = hard_constraint_errors(state, terminal_event, world=demo_world)
    assert any(error.startswith("ending_gate_min_turn") for error in errors)
    assert "fate_min_end_turn" in errors


def test_phase_based_tension_prefers_pressure_in_crisis(demo_state):
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.story_phase = "crisis"
    low = EventAtom.from_dict(
        {
            "event_id": "low",
            "title": "低压",
            "summary": "什么也没真正推进。",
            "actors": ["yu_cheng"],
            "scene_function": "debt_exchange",
            "tags": ["duty"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": -0.02,
            "theme_impacts": {},
            "agency_affordances": ["duty"],
            "rating_ceiling": "PG",
            "temptation_vector": {},
            "vow_tests": [],
            "wound_triggers": [],
            "debt_deltas": [],
            "karmic_seed_creations": [],
            "karmic_seed_resolutions": [],
            "awakening_affordances": [],
            "concealment_level": 0.0,
            "consequence_delay_hint": 0,
        }
    )
    high = EventAtom.from_dict({**low.to_dict(), "event_id": "high", "tension_delta": 0.16})
    assert dramatic_tension_delta(state, high) > dramatic_tension_delta(state, low)


def test_reader_view_is_sanitized(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world)
    body = result["reader_view"]["body"]
    assert not contains_engineering_leak(body)
    assert "->" not in body
    assert "event_id" not in body
    assert "seed_id" not in body


def test_sanitizer_removes_engineering_tokens():
    text = "route=foo -> bar event_id seed_id debt_type greed scene_function secret_meet_lin_wan"
    cleaned = sanitize_text(text)
    assert "route=" not in cleaned
    assert "->" not in cleaned
    assert "event_id" not in cleaned
    assert "seed_id" not in cleaned
    assert "secret_meet_lin_wan" not in cleaned


def test_concealed_truth_seed_transforms_under_truth_trial(demo_state, demo_events):
    lookup = {event.event_id: event for event in demo_events}
    state = apply_event(demo_state, lookup["secret_meet_lin_wan"])
    transformed = apply_event(state, lookup["lin_wan_asks_for_truth"])
    seed_map = {seed.seed_id: seed.status for seed in transformed.characters["yu_cheng"].karmic_seeds}
    assert seed_map["seed_half_truth_lin"] in {"resolved", "transformed"}


def test_scene_intent_shifts_when_cross_pressure_is_active(demo_world, demo_state, demo_events):
    lookup = {event.event_id: event for event in demo_events}
    state = apply_event(demo_state, lookup["secret_meet_lin_wan"])
    state = apply_event(state, lookup["accept_exam_nomination"])
    state = apply_event(state, lookup["refuse_the_exam_publicly"])
    state = apply_event(state, lookup["protect_family_and_take_blame"])
    state.chapter_index = 7
    state.story_phase = "crisis"

    result = plan_next_turn_from_events(state, demo_events, world=demo_world, debug=True)
    assert result["chapter_plan"]["scene_intent"]["intent_id"] in {
        "public_face_private_wound",
        "crossed_wound",
    }
