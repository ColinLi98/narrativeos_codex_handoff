from src.narrativeos.eval.validators import (
    chapter_structure_validator,
    engineering_leak_validator,
    meta_narration_validator,
    paragraph_repetition_validator,
    premature_ending_validator,
)
from src.narrativeos.models import NarrativeState


def test_engineering_and_meta_validators():
    assert engineering_leak_validator("event_id seed_id foo_bar a -> b")
    assert meta_narration_validator("这一章如果把这一章放远一点看，第1拍就会显得很明显。")


def test_repetition_validator_hits_repeated_paragraphs():
    issues = paragraph_repetition_validator(["同一句话重复很多次", "同一句话重复很多次", "另一句"])
    assert issues


def test_structure_and_premature_ending_validators():
    issues = chapter_structure_validator(
        text="太短了。",
        paragraphs=["太短了。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
    )
    assert issues

    state = NarrativeState.from_dict(
        {
            "state_id": "s",
            "world_id": "w",
            "turn_index": 0,
            "story_phase": "setup",
            "chapter_index": 1,
            "min_end_turn": 8,
            "fate_pressure": 0.1,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.2,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    )
    ending_issues = premature_ending_validator(state_after=state, ending_ready=True, body="")
    assert ending_issues
