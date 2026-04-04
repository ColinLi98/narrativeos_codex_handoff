from copy import deepcopy

from src.narrativeos.canon import hard_constraint_errors
from src.narrativeos.models import EventAtom, NarrativeState, WorldBible
from src.narrativeos.schemas import validate_payload
from tests.conftest import load_example


def test_examples_roundtrip_and_schema_validation():
    world_payload = load_example("demo_world_bible.json")
    state_payload = load_example("demo_initial_state.json")
    event_payloads = load_example("demo_event_atoms.json")
    romance_world_payload = load_example("romance_world_bible.json")
    romance_state_payload = load_example("romance_initial_state.json")

    validate_payload(world_payload, "world_bible.schema.json")
    validate_payload(state_payload, "narrative_state.schema.json")
    validate_payload(romance_world_payload, "world_bible.schema.json")
    validate_payload(romance_state_payload, "narrative_state.schema.json")
    for event_payload in event_payloads:
        validate_payload(event_payload, "event_atom.schema.json")

    assert WorldBible.from_dict(world_payload).to_dict() == world_payload
    assert NarrativeState.from_dict(state_payload).to_dict() == state_payload
    assert WorldBible.from_dict(romance_world_payload).to_dict() == romance_world_payload
    assert NarrativeState.from_dict(romance_state_payload).to_dict() == romance_state_payload
    assert [EventAtom.from_dict(event).to_dict() for event in event_payloads] == event_payloads


def test_canon_flags_rating_ceiling_knowledge_leak_and_scene_repeat(demo_world, demo_state):
    repeated_state = NarrativeState.from_dict(demo_state.to_dict())
    repeated_state.recent_scene_functions = ["commitment", "commitment"]

    illegal_event = EventAtom.from_dict(
        {
            "event_id": "bad_event",
            "title": "一切突然变坏",
            "summary": "余澄突然知道了并未发生的秘密，还越过了分级上限。",
            "location": "花厅",
            "actors": ["yu_cheng"],
            "scene_function": "commitment",
            "tags": ["secret"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {"lin_wan": {"add_true": ["unseen_secret"], "add_false": []}},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": ["secrecy"],
            "rating_ceiling": "R",
        }
    )

    errors = hard_constraint_errors(repeated_state, illegal_event, world=demo_world)
    assert any(error.startswith("rating_exceeds_ceiling") for error in errors)
    assert any(error.startswith("belief_update_non_actor") for error in errors)
    assert any(error.startswith("scene_function_window_repeat") for error in errors)


def test_world_forbidden_moves_can_reject_specific_patterns(demo_world, demo_state):
    supernatural_world = WorldBible.from_dict(deepcopy(demo_world.to_dict()))
    supernatural_world.forbidden_moves.append("角色不能突然拥有超自然力量。")
    event = EventAtom.from_dict(
        {
            "event_id": "supernatural_break",
            "title": "余澄忽得神通",
            "summary": "他忽然得了 supernatural magic 的力量。",
            "location": "渡口",
            "actors": ["yu_cheng"],
            "scene_function": "reversal",
            "tags": ["magic", "supernatural"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": ["yu_cheng_has_magic"],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.2,
            "theme_impacts": {"destiny": 0.2},
            "agency_affordances": ["risk"],
            "rating_ceiling": "PG13",
        }
    )

    errors = hard_constraint_errors(demo_state, event, world=supernatural_world)
    assert any(error.startswith("forbidden_move_match") for error in errors)
