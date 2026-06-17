from copy import deepcopy

from src.narrativeos.critics import ConsistencyCritic, DiversityCritic, DramaCritic
from src.narrativeos.memory import apply_event
from src.narrativeos.models import EventAtom, NarrativeState, PromiseLedgerEntry, WorldBible
from src.narrativeos.providers import InlineJSONLLMBackend, LLMCandidateProvider, StaticCandidateProvider
from src.narrativeos.search import evaluate_candidates
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_static_candidate_provider_meets_phase2_counts(demo_world, demo_state, demo_events):
    provider = StaticCandidateProvider(demo_events)
    batch = provider.generate(demo_state, demo_world, min_candidates=6, max_candidates=10)

    assert len(batch.raw_candidates) >= 6
    assert len(batch.legal_candidates) >= 3
    assert batch.debug["provider"] == "static"
    assert batch.illegal_candidate_reasons


def test_static_candidate_provider_exposes_cache_hit_on_repeat_generation(demo_world, demo_state, demo_events):
    provider = StaticCandidateProvider(demo_events)
    first = provider.generate(demo_state, demo_world, min_candidates=6, max_candidates=10)
    second = provider.generate(demo_state, demo_world, min_candidates=6, max_candidates=10)

    assert first.debug["cache_hit"] is False
    assert second.debug["cache_hit"] is True
    assert second.debug["cache_key"]


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


def test_static_candidate_provider_enables_continuations_for_longform_even_below_short_route_threshold(
    demo_world, demo_state, demo_events
):
    longform_state = NarrativeState.from_dict(demo_state.to_dict())
    longform_state.visited_event_ids = [event.event_id for event in demo_events]
    longform_state.chapter_index = 2
    longform_state.story_phase = "early_rising"
    longform_state.min_end_turn = 6
    longform_state.metadata["longform_plan_enabled"] = True
    provider = StaticCandidateProvider(demo_events)

    batch = provider.generate(longform_state, demo_world, min_candidates=4, max_candidates=6)

    assert batch.debug["continuation_mode"] == "longform"
    assert batch.debug["continuation_candidate_count"] > 0
    assert batch.legal_candidates


def test_jade_accept_exam_nomination_prefers_runtime_continuation_blueprints():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_exam@1.0.0")
    provider = StaticCandidateProvider(runtime.event_atoms)
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.chapter_index = 4
    state.story_phase = "midpoint"
    state.min_end_turn = 12

    batch = provider.generate(state, runtime.world_record.world, min_candidates=4, max_candidates=6)

    continuation_candidates = [
        event
        for event in batch.raw_candidates
        if event.metadata.get("base_event_id") == "accept_exam_nomination"
    ]
    assert continuation_candidates
    assert any(
        "荣老太君顺着体面把最难认的那句逼到余澄面前" in event.title
        or "徐师在书房里把那句不能再装糊涂的话留给余澄自己来认" in event.title
        for event in continuation_candidates
    )


def test_urban_synthesized_runtime_events_expose_continuation_blueprints_and_promise_closure():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("urban_mystery_lotus_lane@0.1.0")
    base_event = next(
        event
        for event in runtime.event_atoms
        if (event.metadata or {}).get("scene_blueprint_id") == "alley_meet"
    )
    assert (base_event.metadata or {}).get("continuation_blueprints")

    provider = StaticCandidateProvider(runtime.event_atoms)
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.chapter_index = 20
    state.turn_index = 20
    state.story_phase = "aftermath"
    state.min_end_turn = 12
    state.current_chapter_task = {
        "duty_type": "pace_breath",
        "promise_actions": ["maintain_continuity"],
    }
    state.open_promises = [
        PromiseLedgerEntry(
            promise_id="alley_meet__promise",
            description="旧巷那一夜迟早要被真正说清。",
            opened_at_turn=1,
            due_by_turn=3,
            holders=["jiang_yi", "zhou_lan"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="trust",
            tags=["false_peace"],
        ),
        PromiseLedgerEntry(
            promise_id="truth_request__promise",
            description="追问不能永远停在半句真话上。",
            opened_at_turn=2,
            due_by_turn=4,
            holders=["jiang_yi", "zhou_lan"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="trust",
            tags=["truth_trial"],
        ),
        PromiseLedgerEntry(
            promise_id="rooftop_confession__promise",
            description="天台那次真话不能一直停在风口。",
            opened_at_turn=5,
            due_by_turn=7,
            holders=["jiang_yi", "zhou_lan"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="trust",
            tags=["confession_window"],
        ),
        PromiseLedgerEntry(
            promise_id="lotus_file_ripening__promise",
            description="旧案翻出的代价迟早要结算。",
            opened_at_turn=6,
            due_by_turn=8,
            holders=["jiang_yi", "zhou_lan"],
            fulfillment_modes=["repair"],
            status="open",
            stakes="medium",
            tags=["karma_ripening"],
        ),
        PromiseLedgerEntry(
            promise_id="archive_mask_crack__promise",
            description="档案室里露出的裂口不能再被解释缝回去。",
            opened_at_turn=7,
            due_by_turn=9,
            holders=["jiang_yi", "zhou_lan"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="medium",
            tags=["mask_crack"],
        ),
    ]

    batch = provider.generate(state, runtime.world_record.world, min_candidates=4, max_candidates=6)
    continuation_candidates = [event for event in batch.raw_candidates if event.metadata.get("continuation_variant")]
    assert continuation_candidates
    assert any(event.promises_close for event in continuation_candidates)
    assert any(
        "那次旧巷相遇真正没说完的话终于被逼到风口" in event.title
        or "天台那次停住的后半句终于被江屹自己补完" in event.title
        or "因果回潮之后，两个人终于得到一次不靠试探的缓口气" in event.title
        for event in continuation_candidates
    )


def test_xianxia_synthesized_runtime_events_expose_continuation_blueprints():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("xianxia_forgotten_vow@0.1.0")
    base_event = next(
        event
        for event in runtime.event_atoms
        if (event.metadata or {}).get("scene_blueprint_id") == "vow_trial"
    )
    assert (base_event.metadata or {}).get("continuation_blueprints")

    provider = StaticCandidateProvider(runtime.event_atoms)
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.chapter_index = 18
    state.turn_index = 18
    state.story_phase = "climax"
    state.min_end_turn = 12
    state.current_chapter_task = {
        "duty_type": "deliver_climax",
        "promise_actions": ["close_arc_loop", "maintain_continuity"],
    }
    state.open_promises = [
        PromiseLedgerEntry(
            promise_id="vow_trial__promise",
            description="山门前那句最重的话迟早要被真正认下。",
            opened_at_turn=2,
            due_by_turn=5,
            holders=["shen_zhao", "ye_qingzhu"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="destiny",
            tags=["temptation"],
        )
    ]

    batch = provider.generate(state, runtime.world_record.world, min_candidates=4, max_candidates=6)
    continuation_candidates = [event for event in batch.raw_candidates if event.metadata.get("continuation_variant")]
    assert continuation_candidates
    assert any(event.promises_close for event in continuation_candidates)
    assert any(
        "照骨灯前那句一直绕着走的旧誓终于被逼到明处" in event.title
        or "照骨灯照出来的那句真话终于换成了正面逼问" in event.title
        or "山门前那句若天命与旧誓撞上先舍哪一个终于被追到最重" in event.title
        or "旧誓动摇以后，终于出现了一个不能再拿大道遮羞的窗口" in event.title
        for event in continuation_candidates
    )


def test_synthetic_pack_synthesized_runtime_events_expose_continuation_blueprints():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("synthetic_min_pack@0.1.0")
    base_event = next(
        event
        for event in runtime.event_atoms
        if (event.metadata or {}).get("scene_blueprint_id") == "synthetic_setup"
    )
    assert (base_event.metadata or {}).get("continuation_blueprints")

    provider = StaticCandidateProvider(runtime.event_atoms)
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.chapter_index = 14
    state.turn_index = 14
    state.story_phase = "climax"
    state.min_end_turn = 12
    state.current_chapter_task = {
        "duty_type": "resolve_promise",
        "promise_actions": ["advance_payoff", "maintain_continuity"],
    }
    state.open_promises = [
        PromiseLedgerEntry(
            promise_id="synthetic_setup__promise",
            description="最开始那句没认完的话迟早要被说清。",
            opened_at_turn=1,
            due_by_turn=3,
            holders=["lead_a", "lead_b"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="trust",
            tags=["setup"],
        )
    ]

    batch = provider.generate(state, runtime.world_record.world, min_candidates=4, max_candidates=6)
    continuation_candidates = [event for event in batch.raw_candidates if event.metadata.get("continuation_variant")]
    assert continuation_candidates
    assert any(event.promises_close for event in continuation_candidates)
    assert any(
        "正面碰撞" in event.title
        or "后果回潮" in event.title
        or "终于被逼到最前面" in event.title
        or "终于开始有人认回去" in event.title
        for event in continuation_candidates
    )


def test_jade_court_romance_runtime_events_expose_continuation_blueprints():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("jade_court_romance@1.0.0")
    base_event = next(event for event in runtime.event_atoms if event.event_id == "accept_exam_nomination")
    assert (base_event.metadata or {}).get("continuation_blueprints")

    provider = StaticCandidateProvider(runtime.event_atoms)
    state = NarrativeState.from_dict(runtime.initial_state.to_dict())
    state.visited_event_ids = [event.event_id for event in runtime.event_atoms]
    state.chapter_index = 18
    state.turn_index = 18
    state.story_phase = "climax"
    state.min_end_turn = 12
    state.current_chapter_task = {
        "duty_type": "advance_relationship",
        "promise_actions": ["maintain_continuity"],
    }
    state.open_promises = [
        PromiseLedgerEntry(
            promise_id="must_sit_first_exam",
            description="春闱之命必须被真正兑现或公开改写。",
            opened_at_turn=1,
            due_by_turn=3,
            holders=["yu_cheng", "lady_rong"],
            fulfillment_modes=["truth"],
            status="open",
            stakes="family_reputation_and_selfhood",
            tags=["exam"],
        )
    ]

    batch = provider.generate(state, runtime.world_record.world, min_candidates=4, max_candidates=6)
    continuation_candidates = [event for event in batch.raw_candidates if event.metadata.get("continuation_variant")]
    assert continuation_candidates
    assert any(event.promises_close for event in continuation_candidates)
    assert any(
        "春闱之命压下来以后，余澄第一次被逼着把那层真心说到更前面" in event.title
        or "那次试探没有白过去，终于出现了一个能把真心说全的窗口" in event.title
        for event in continuation_candidates
    )


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
