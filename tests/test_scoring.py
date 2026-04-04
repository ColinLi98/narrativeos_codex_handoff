from src.narrativeos.models import SearchWeights
from src.narrativeos.scoring import score_event


def test_ambition_prefers_exam_path(demo_world, demo_state, demo_events):
    events = {event.event_id: event for event in demo_events}

    exam = score_event(demo_state, events["accept_exam_nomination"], world=demo_world)
    romance = score_event(demo_state, events["secret_meet_lin_wan"], world=demo_world)

    assert exam.total_score > romance.total_score
    assert exam.components["desire_pull"] >= romance.components["desire_pull"]


def test_creator_control_weights_can_shift_route_preference(demo_world, demo_state, demo_events):
    romance_world = demo_world
    romance_world.creator_controls.theme_targets = ["love", "selfhood"]
    romance_world.creator_controls.scoring_weights = SearchWeights(
        desire_pull=0.08,
        shadow_pull=0.2,
        poison_pull=0.2,
        vow_pull=0.14,
        wound_pull=0.12,
        debt_pull=0.1,
        karma_pull=0.12,
        fate_pull=0.08,
        wisdom_resistance=0.06,
    ).to_dict()
    demo_state.player_intent = {"romance": 0.8, "curiosity": 0.6, "selfhood": 0.6}

    events = {event.event_id: event for event in demo_events}
    exam = score_event(
        demo_state,
        events["accept_exam_nomination"],
        world=romance_world,
        weights=SearchWeights.from_dict(romance_world.creator_controls.scoring_weights),
    )
    romance = score_event(
        demo_state,
        events["secret_meet_lin_wan"],
        world=romance_world,
        weights=SearchWeights.from_dict(romance_world.creator_controls.scoring_weights),
    )

    assert romance.total_score > exam.total_score
