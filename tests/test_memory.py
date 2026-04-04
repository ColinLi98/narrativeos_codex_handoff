import pytest

from src.narrativeos.memory import apply_event
from src.narrativeos.models import EventAtom


def test_promise_open_and_close(demo_state, demo_events):
    events = {event.event_id: event for event in demo_events}

    after_commit = apply_event(demo_state, events["accept_exam_nomination"])
    assert any(promise.promise_id == "must_sit_first_exam" for promise in after_commit.open_promises)
    assert "yu_cheng_commits_exam" in after_commit.world_facts

    after_exam = apply_event(after_commit, events["sit_the_exam"])
    assert not any(promise.promise_id == "must_sit_first_exam" for promise in after_exam.open_promises)
    assert "exam_completed" in after_exam.world_facts


def test_memory_updates_beliefs_emotions_trust_and_metadata(demo_state):
    event = EventAtom.from_dict(
        {
            "event_id": "synthetic_truth_scene",
            "title": "徐师看穿余澄的动摇",
            "summary": "徐师从余澄的话里听出了他真正的犹疑。",
            "location": "书房",
            "actors": ["yu_cheng", "tutor_xu"],
            "scene_function": "discovery",
            "tags": ["honesty", "mentorship"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": ["tutor_knows_yu_doubts"],
            "world_fact_deltas_remove": [],
            "belief_updates": {
                "tutor_xu": {"add_true": ["tutor_knows_yu_doubts"], "add_false": []}
            },
            "trust_deltas": [{"source": "tutor_xu", "target": "yu_cheng", "delta": 0.2}],
            "emotion_deltas": [{"character": "yu_cheng", "emotion": "anxiety", "delta": -0.2}],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.03,
            "theme_impacts": {"selfhood": 0.1},
            "agency_affordances": ["honesty", "selfhood"],
            "rating_ceiling": "PG",
        }
    )

    next_state = apply_event(demo_state, event)

    assert "tutor_knows_yu_doubts" in next_state.world_facts
    assert "tutor_knows_yu_doubts" in next_state.characters["tutor_xu"].beliefs_true
    assert next_state.characters["tutor_xu"].trust["yu_cheng"] == 0.7
    assert next_state.characters["yu_cheng"].emotions["anxiety"] == pytest.approx(0.5)
    assert next_state.metadata["last_event_id"] == "synthetic_truth_scene"
    assert next_state.route_fingerprint[-1] == "event:synthetic_truth_scene"


def test_placeholder_promises_are_normalized(demo_state):
    event = EventAtom.from_dict(
        {
            "event_id": "open_placeholder_promise",
            "title": "余澄立下迟早要面对的约",
            "summary": "他许下了还账的诺言。",
            "location": "花厅",
            "actors": ["yu_cheng"],
            "scene_function": "commitment",
            "tags": ["duty"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [
                {
                    "promise_id": "placeholder",
                    "description": "未来必须偿还。",
                    "opened_at_turn": -1,
                    "due_by_turn": -1,
                    "holders": ["yu_cheng"],
                    "fulfillment_modes": ["pay_it_back"],
                    "status": "failed",
                    "stakes": "reputation",
                    "tags": ["duty"],
                }
            ],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": ["duty"],
            "rating_ceiling": "PG",
        }
    )

    next_state = apply_event(demo_state, event)
    promise = next_state.open_promises[0]
    assert promise.opened_at_turn == 1
    assert promise.due_by_turn == 3
    assert promise.status == "open"
