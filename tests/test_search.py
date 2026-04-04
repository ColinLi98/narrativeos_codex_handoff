from src.narrativeos.pipeline import plan_next_turn_from_events
from src.narrativeos.search import beam_search, static_candidate_provider
from src.narrativeos.models import NarrativeState


def test_beam_search_returns_ranked_routes(demo_world, demo_state, demo_events):
    routes = beam_search(
        demo_state,
        world=demo_world,
        candidate_provider=static_candidate_provider(demo_events),
        depth=2,
        beam_width=3,
    )

    assert len(routes) >= 1
    assert routes[0].total_score >= routes[-1].total_score
    assert len(routes[0].events) >= 1
    assert routes[0].critic_trace
    assert routes[0].to_dict()["event_ids"]


def test_plan_next_turn_returns_scored_candidates_and_rendered_scene(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(
        demo_state,
        demo_events,
        world=demo_world,
        beam_width=3,
        depth=2,
        debug=True,
    )

    assert result["status"] == "ok"
    assert result["candidate_batch"]["raw_candidates"]
    assert result["candidate_batch"]["legal_candidates"]
    assert result["scored_candidates"]
    assert result["critic_trace"]
    assert result["rendered_scene"]["concise_summary"]
    assert result["updated_state"]["chapter_index"] == 1
    assert len(result["scene_beats"]) >= 3
    assert len({beat["event"]["event_id"] for beat in result["scene_beats"]}) >= 2
    assert len(result["rendered_scene"]["premium_prose"]) >= 600


def test_default_plan_next_turn_returns_reader_view_without_internal_fields(demo_world, demo_state, demo_events):
    result = plan_next_turn_from_events(demo_state, demo_events, world=demo_world, beam_width=3, depth=2)

    assert result["status"] == "ok"
    assert result["reader_view"]["body"]
    assert "candidate_batch" not in result
    assert "event_id" not in result["reader_view"]["body"]


def test_demo_world_can_run_beyond_six_turns(demo_world, demo_state, demo_events):
    state = demo_state
    completed_turns = 0
    for _ in range(10):
        result = plan_next_turn_from_events(
            state,
            demo_events,
            world=demo_world,
            beam_width=3,
            depth=2,
            debug=True,
        )
        if result["status"] != "ok":
            break
        completed_turns += 1
        state = NarrativeState.from_dict(result["updated_state"])

    assert completed_turns >= 8
