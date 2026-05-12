from copy import deepcopy

from src.narrativeos.core.emotion_actions import compose_emotion_action
from src.narrativeos.models import EventAtom, NarrativeState, SceneBeat, WorldBible, SearchWeights
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


def test_q06_scoring_uses_character_card_and_duty_alignment(demo_world, demo_state, demo_events):
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.player_intent = {"romance": 0.85, "selfhood": 0.75, "honesty": 0.65}
    state.current_chapter_task = {
        "chapter_task_id": "task_relationship",
        "duty_type": "advance_relationship",
        "objective": "推进角色关系并逼近真话。",
    }
    state.character_memory_runtime = {
        "yu_cheng": {
            "structured_memory": {
                "goals": ["remain_true_to_lin_wan", "seek_selfhood"],
                "promises": ["宁可自己背负，也不让她替我受伤"],
                "scars": ["永远要证明自己才值得被留下"],
                "taboos": ["空洞功名"],
            }
        },
        "lin_wan": {
            "structured_memory": {
                "goals": ["protect_truth", "protect_yu_cheng"],
                "promises": ["若他不肯说真话，我也不替他圆谎"],
                "scars": ["先相信的人总是先受伤"],
                "taboos": ["含混试探"],
            }
        },
    }
    world = WorldBible.from_dict(deepcopy(demo_world.to_dict()))
    world.creator_controls.theme_targets = ["love", "honesty", "selfhood"]

    events = {event.event_id: event for event in demo_events}
    romance = score_event(state, events["secret_meet_lin_wan"], world=world)
    exam = score_event(state, events["accept_exam_nomination"], world=world)

    assert romance.total_score > exam.total_score
    assert romance.components["character_card_alignment"] > exam.components["character_card_alignment"]
    assert romance.components["duty_alignment"] > exam.components["duty_alignment"]


def test_emotion_action_defaults_shift_with_duty_when_policy_missing(demo_world, demo_state, demo_events):
    world = WorldBible.from_dict(deepcopy(demo_world.to_dict()))
    world.capability_assets = {}
    world.creator_controls.metadata = {}
    state = NarrativeState.from_dict(demo_state.to_dict())
    beat = SceneBeat(
        beat_index=1,
        event=next(event for event in demo_events if event.event_id == "secret_meet_lin_wan"),
        beat_label="测试 beat",
        dramatic_job="pressure",
        tension_after=state.tension,
    )

    state.current_chapter_task = {"duty_type": "advance_relationship"}
    relationship_text = compose_emotion_action(world, state, beat, repeated=False)
    state.current_chapter_task = {"duty_type": "resolve_promise"}
    promise_text = compose_emotion_action(world, state, beat, repeated=False)

    assert relationship_text != promise_text
    assert any(token in relationship_text for token in ["靠近", "试探", "真心"])
    assert any(token in promise_text for token in ["旧账", "真话", "认下"])


def test_longform_scoring_penalizes_terminal_and_repeated_clusters_before_late_window(demo_world, demo_state, demo_events):
    state = NarrativeState.from_dict(demo_state.to_dict())
    state.current_chapter_task = {
        "chapter_task_id": "task_climax",
        "duty_type": "deliver_climax",
        "objective": "推进终局前压力，但不能过早收束。",
        "quality_contract": {"continuation_pressure_required": True},
    }
    state.recent_scene_functions = ["vow_payment", "vow_payment", "truth_trial"]
    state.metadata["recent_duty_types"] = ["deliver_climax", "deliver_climax"]
    state.metadata["longform_progression"] = {
        "series_target_chapters": 200,
        "series_chapter_index": 120,
    }
    state.metadata["replan_debt"] = {
        "status": "active",
        "issue_codes": ["Q09"],
        "active_until_chapter": 130,
        "intensity": 2,
    }
    terminal_event = EventAtom.from_dict(
        {
            **deepcopy(next(event for event in demo_events if event.event_id == "accept_exam_nomination").to_dict()),
            "event_id": "terminal_test_event",
            "scene_function": "vow_payment",
            "metadata": {"terminal": True, "ending_gate": {"min_turn": 180}},
            "tags": ["truth", "destiny", "climax"],
        }
    )
    recovery_event = EventAtom.from_dict(
        {
            **deepcopy(next(event for event in demo_events if event.event_id == "secret_meet_lin_wan").to_dict()),
            "event_id": "recovery_test_event",
            "scene_function": "debt_exchange",
            "metadata": {"terminal": False},
            "tags": ["truth", "love", "reputation", "loyalty"],
        }
    )

    terminal = score_event(state, terminal_event, world=demo_world)
    recovery = score_event(state, recovery_event, world=demo_world)

    assert recovery.total_score > terminal.total_score
    assert terminal.components["terminal_before_late_penalty"] > 0.0
    assert terminal.components["duty_cluster_penalty"] > 0.0
    assert terminal.components["replan_debt_penalty"] > 0.0
    assert recovery.components["continuation_pressure_bonus"] > 0.0
    assert recovery.components["relationship_debt_bonus"] > 0.0
