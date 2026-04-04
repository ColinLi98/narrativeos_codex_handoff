from copy import deepcopy

from src.narrativeos.critics import ConsistencyCritic, DiversityCritic, DramaCritic
from src.narrativeos.memory import apply_event
from src.narrativeos.models import EventAtom, NarrativeState, PromiseLedgerEntry, WorldBible
from src.narrativeos.providers import InlineJSONLLMBackend, LLMCandidateProvider, StaticCandidateProvider
from src.narrativeos.search import evaluate_candidates


def test_static_candidate_provider_meets_phase2_counts(demo_world, demo_state, demo_events):
    provider = StaticCandidateProvider(demo_events)
    batch = provider.generate(demo_state, demo_world, min_candidates=6, max_candidates=10)

    assert len(batch.raw_candidates) >= 6
    assert len(batch.legal_candidates) >= 3
    assert batch.debug["provider"] == "static"
    assert batch.illegal_candidate_reasons


def test_llm_candidate_provider_validates_payload_and_backfills(demo_world, demo_state, demo_events):
    llm_payload = {
        "candidate_events": [
            demo_events[0].to_dict(),
            {"event_id": "broken"},
            demo_events[0].to_dict(),
        ]
    }
    provider = LLMCandidateProvider(
        InlineJSONLLMBackend(llm_payload),
        StaticCandidateProvider(demo_events),
    )

    batch = provider.generate(demo_state, demo_world, min_candidates=6, max_candidates=8)
    assert len(batch.raw_candidates) >= 6
    assert batch.debug["provider"] == "llm"
    assert batch.debug["invalid_payloads"]
    assert "accept_exam_nomination" in [event.event_id for event in batch.legal_candidates]


def test_static_candidate_provider_synthesizes_continuation_candidates_when_pool_is_exhausted(
    demo_world, demo_state, demo_events
):
    exhausted_state = NarrativeState.from_dict(demo_state.to_dict())
    exhausted_state.visited_event_ids = [event.event_id for event in demo_events]
    exhausted_state.chapter_index = 4
    exhausted_state.story_phase = "midpoint"
    exhausted_state.min_end_turn = 12
    provider = StaticCandidateProvider(demo_events)

    batch = provider.generate(exhausted_state, demo_world, min_candidates=4, max_candidates=6)

    assert batch.raw_candidates
    assert batch.debug["continuation_candidate_count"] > 0
    assert any(event.metadata.get("continuation_variant") for event in batch.raw_candidates)
    assert all(event.event_id not in exhausted_state.visited_event_ids for event in batch.raw_candidates)
    assert any(event.promises_open for event in batch.raw_candidates)
    assert batch.legal_candidates


def test_critics_surface_revisions_and_rejections(demo_world, demo_state):
    revised_state = NarrativeState.from_dict(demo_state.to_dict())
    revised_state.recent_scene_functions = ["temptation"]
    revised_state.open_promises = [
        PromiseLedgerEntry(
            promise_id="overdue",
            description="必须尽快兑现。",
            opened_at_turn=0,
            due_by_turn=0,
            holders=["yu_cheng"],
            fulfillment_modes=["answer"],
            status="open",
            stakes="trust",
            tags=["honesty"],
        )
    ]

    repetitive_event = EventAtom.from_dict(
        {
            "event_id": "repeat_secret_scene",
            "title": "又一次试探",
            "summary": "余澄再次绕着林绾试探，却没有推进任何代价。",
            "location": "回廊",
            "actors": ["yu_cheng", "lin_wan"],
            "scene_function": "temptation",
            "tags": ["love", "secrecy"],
            "preconditions_all": ["spring_exam_announced"],
            "forbidden_if_any": [],
            "world_fact_deltas_add": [],
            "world_fact_deltas_remove": [],
            "belief_updates": {},
            "trust_deltas": [],
            "emotion_deltas": [],
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": ["romance", "secrecy"],
            "rating_ceiling": "PG",
        }
    )
    duplicate_event = EventAtom.from_dict(deepcopy(repetitive_event.to_dict()))
    duplicate_event.event_id = "repeat_secret_scene_b"

    provider = StaticCandidateProvider([repetitive_event, duplicate_event])
    _, scored = evaluate_candidates(
        revised_state,
        demo_world,
        candidate_provider=provider,
        critics=[ConsistencyCritic(), DramaCritic(), DiversityCritic()],
        min_candidates=2,
        max_candidates=2,
    )

    assert scored
    decisions = scored[0].critic_decisions
    assert any(decision.critic_name == "consistency" and decision.verdict == "revise" for decision in decisions)
    assert any(decision.critic_name == "drama" and decision.verdict == "revise" for decision in decisions)
    assert any(decision.critic_name == "diversity" and decision.verdict == "revise" for decision in decisions)


def test_duplicate_scene_window_is_rejected_by_consistency_critic(demo_world, demo_state):
    repeated_state = NarrativeState.from_dict(demo_state.to_dict())
    repeated_state.recent_scene_functions = ["commitment", "commitment"]
    event = EventAtom.from_dict(
        {
            "event_id": "third_commitment",
            "title": "再一次承诺",
            "summary": "又一次公开承诺。",
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
            "promises_open": [],
            "promises_close": [],
            "tension_delta": 0.0,
            "theme_impacts": {},
            "agency_affordances": ["duty"],
            "rating_ceiling": "PG",
        }
    )

    decision = ConsistencyCritic().evaluate(repeated_state, event, demo_world)
    assert decision.verdict == "reject"
