from src.narrativeos.karma import compute_karmic_weather
from src.narrativeos.memory import apply_event


def test_event_creates_karmic_seed(demo_state, demo_events):
    event = {item.event_id: item for item in demo_events}["secret_meet_lin_wan"]
    next_state = apply_event(demo_state, event)
    seeds = {seed.seed_id for seed in next_state.characters["yu_cheng"].karmic_seeds}
    assert "seed_half_truth_lin" in seeds


def test_seed_does_not_ripen_before_earliest_turn(demo_state, demo_events):
    lookup = {item.event_id: item for item in demo_events}
    state = apply_event(demo_state, lookup["secret_meet_lin_wan"])
    seed_map = {seed.seed_id: seed.status for seed in state.characters["yu_cheng"].karmic_seeds}
    assert seed_map["seed_half_truth_lin"] == "dormant"


def test_seed_ripens_or_transforms_when_condition_hits(demo_state, demo_events):
    lookup = {item.event_id: item for item in demo_events}
    state = apply_event(demo_state, lookup["secret_meet_lin_wan"])
    state = apply_event(state, lookup["lin_wan_asks_for_truth"])
    seed_map = {seed.seed_id: seed.status for seed in state.characters["yu_cheng"].karmic_seeds}
    assert seed_map["seed_half_truth_lin"] in {"ripening", "resolved", "transformed"}


def test_compute_karmic_weather_reflects_active_seeds(demo_state, demo_events):
    event = {item.event_id: item for item in demo_events}["secret_meet_lin_wan"]
    next_state = apply_event(demo_state, event)
    weather = compute_karmic_weather(next_state)
    assert weather["temptation"] > 0
    assert weather["suspicion"] > 0
