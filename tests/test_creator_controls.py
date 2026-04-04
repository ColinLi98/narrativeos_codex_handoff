import json
from pathlib import Path

from src.narrativeos.models import NarrativeState, WorldBible
from src.narrativeos.pipeline import plan_next_turn_from_events


def test_different_world_controls_can_change_the_selected_route(demo_world, demo_state, demo_events):
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "romance_world_bible.json"
    romance_world = WorldBible.from_dict(json.loads(fixture_path.read_text(encoding="utf-8")))
    romance_state = NarrativeState.from_dict(demo_state.to_dict())
    romance_state.world_id = romance_world.world_id
    romance_state.player_intent = {"romance": 0.8, "curiosity": 0.6, "selfhood": 0.6}
    base_state = NarrativeState.from_dict(demo_state.to_dict())

    base_result = plan_next_turn_from_events(base_state, demo_events, world=demo_world, beam_width=3, depth=2, debug=True)
    romance_result = plan_next_turn_from_events(
        romance_state,
        demo_events,
        world=romance_world,
        beam_width=3,
        depth=2,
        debug=True,
    )

    assert base_result["chosen_event"]["event_id"] != romance_result["chosen_event"]["event_id"]
    assert romance_result["chosen_event"]["event_id"] == "secret_meet_lin_wan"
