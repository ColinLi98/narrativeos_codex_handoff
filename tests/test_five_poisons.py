from src.narrativeos.character_engine import poison_activation_score
from src.narrativeos.memory import apply_event


def test_wound_trigger_can_raise_doubt_and_delusion(demo_state, demo_events):
    event = {item.event_id: item for item in demo_events}["secret_meet_lin_wan"]
    before = demo_state.characters["yu_cheng"].poisons.doubt
    next_state = apply_event(demo_state, event)
    after = next_state.characters["yu_cheng"].poisons.doubt
    assert after > before


def test_poison_activation_uses_event_vector_and_stress(demo_state, demo_events):
    event = {item.event_id: item for item in demo_events}["lady_rong_offers_silent_bargain"]
    score = poison_activation_score(demo_state.characters["lady_rong"], demo_state, event)
    assert score > 0.2


def test_higher_clarity_reduces_poison_pull(demo_state, demo_events):
    event = {item.event_id: item for item in demo_events}["secret_meet_lin_wan"]
    low_clarity = demo_state.to_dict()
    high_clarity = demo_state.to_dict()
    low_clarity["characters"]["yu_cheng"]["awakening"]["clarity"] = 0.1
    high_clarity["characters"]["yu_cheng"]["awakening"]["clarity"] = 0.8

    from src.narrativeos.models import NarrativeState

    low_score = poison_activation_score(NarrativeState.from_dict(low_clarity).characters["yu_cheng"], NarrativeState.from_dict(low_clarity), event)
    high_score = poison_activation_score(NarrativeState.from_dict(high_clarity).characters["yu_cheng"], NarrativeState.from_dict(high_clarity), event)
    assert high_score < low_score
