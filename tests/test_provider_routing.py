from src.narrativeos.memory import apply_event
from src.narrativeos.providers import (
    BudgetedLLMBackend,
    CachedLLMBackend,
    InlineJSONLLMBackend,
    LLMCandidateProvider,
    LocalRuleBasedProvider,
    RetryingLLMBackend,
    RoutingLLMBackend,
    build_llm_backend_from_env,
    build_llm_policy_from_env,
)
from src.narrativeos.services.provider_routing import ProviderRoutingService
from src.narrativeos.rendering import LLMRenderer, TemplateRenderer


class _FlakyBackend:
    provider_id = "flaky"

    def __init__(self, payload, *, fail_count: int = 1) -> None:
        self.payload = payload
        self.fail_count = fail_count
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str):
        _ = system_prompt
        _ = user_prompt
        self.calls += 1
        if self.calls <= self.fail_count:
            raise TimeoutError("temporary_timeout")
        return self.payload


class _BrokenBackend:
    provider_id = "broken"

    def generate_json(self, *, system_prompt: str, user_prompt: str):
        _ = system_prompt
        _ = user_prompt
        raise TimeoutError("route_down")


class _CountingBackend:
    provider_id = "counting"

    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str):
        _ = system_prompt
        _ = user_prompt
        self.calls += 1
        return self.payload


def test_retrying_backend_retries_transient_failures_then_succeeds():
    backend = RetryingLLMBackend(
        _FlakyBackend({"candidate_events": []}, fail_count=1),
        provider_id="flaky",
        max_attempts=3,
    )
    payload = backend.generate_json(system_prompt="a", user_prompt="b")
    assert payload == {"candidate_events": []}
    assert backend.last_route_debug["attempt_count"] == 2
    assert backend.last_route_debug["succeeded"] is True


def test_routing_backend_falls_back_to_secondary_provider():
    routing = RoutingLLMBackend(
        [
            _BrokenBackend(),
            InlineJSONLLMBackend({"candidate_events": [{"event_id": "demo"}]}),
        ],
        provider_ids=["broken", "inline"],
        max_attempts_per_backend=2,
    )
    payload = routing.generate_json(system_prompt="a", user_prompt="b")
    assert payload["candidate_events"][0]["event_id"] == "demo"
    assert routing.last_route_debug["selected_provider"] == "inline"
    assert routing.last_route_debug["fallback_used"] is True


def test_build_llm_backend_from_env_can_construct_local_routing(monkeypatch):
    monkeypatch.setenv("NARRATIVEOS_LLM_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_PROVIDER_ORDER", "local")
    backend = build_llm_backend_from_env()
    assert backend is not None
    assert backend.generate_json(system_prompt="a", user_prompt="b") == {"candidate_events": []}


def test_build_llm_backend_from_env_supports_scope_specific_policy(monkeypatch):
    monkeypatch.setenv("NARRATIVEOS_LLM_CANDIDATE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_CANDIDATE_PROVIDER_ORDER", "local")
    monkeypatch.setenv("NARRATIVEOS_LLM_RENDERER_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_RENDERER_PROVIDER_ORDER", "local")
    monkeypatch.setenv("NARRATIVEOS_LLM_RENDERER_CACHE_ENABLED", "true")

    candidate = build_llm_backend_from_env(scope="candidate")
    renderer = build_llm_backend_from_env(scope="renderer")
    candidate_policy = build_llm_policy_from_env("candidate")
    renderer_policy = build_llm_policy_from_env("renderer")

    assert candidate is not None
    assert renderer is not None
    assert candidate_policy["provider_order"] == ["local"]
    assert renderer_policy["provider_order"] == ["local"]
    assert renderer_policy["cache_policy"]["enabled"] is True


def test_provider_routing_service_exposes_policy_summary(monkeypatch):
    monkeypatch.setenv("NARRATIVEOS_LLM_CANDIDATE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_CANDIDATE_PROVIDER_ORDER", "local")
    monkeypatch.setenv("NARRATIVEOS_LLM_RENDERER_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_RENDERER_PROVIDER_ORDER", "local")

    service = ProviderRoutingService.from_env()
    summary = service.policy_summary()

    assert summary["candidate"]["backend_present"] is True
    assert summary["renderer"]["backend_present"] is True
    assert summary["candidate"]["fallback_chain"] == ["llm_routing", "static_candidate_provider"]
    assert summary["renderer"]["fallback_chain"] == ["llm_renderer", "template_renderer"]


def test_cached_backend_hits_runtime_cache_without_recalling_delegate():
    delegate = _CountingBackend({"candidate_events": []})
    backend = CachedLLMBackend(delegate, max_entries=8)
    first = backend.generate_json(system_prompt="same", user_prompt="prompt")
    second = backend.generate_json(system_prompt="same", user_prompt="prompt")
    assert first == second
    assert delegate.calls == 1
    assert backend.last_route_debug["cache_hit"] is True


def test_budgeted_backend_blocks_prompt_over_budget():
    backend = BudgetedLLMBackend(
        InlineJSONLLMBackend({"candidate_events": []}),
        max_prompt_chars=5,
        estimated_cost_per_1k_chars=0.002,
    )
    import pytest

    with pytest.raises(Exception):
        backend.generate_json(system_prompt="123456", user_prompt="7890")
    assert backend.last_route_debug["budget_blocked"] is True


def test_build_llm_backend_from_env_can_wrap_cache_and_budget(monkeypatch):
    monkeypatch.setenv("NARRATIVEOS_LLM_ROUTING_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_PROVIDER_ORDER", "local")
    monkeypatch.setenv("NARRATIVEOS_LLM_CACHE_ENABLED", "true")
    monkeypatch.setenv("NARRATIVEOS_LLM_CACHE_MAX_ENTRIES", "16")
    monkeypatch.setenv("NARRATIVEOS_LLM_MAX_PROMPT_CHARS", "100")
    backend = build_llm_backend_from_env()
    assert backend is not None
    payload = backend.generate_json(system_prompt="a", user_prompt="b")
    assert payload == {"candidate_events": []}
    debug = backend.generate_json(system_prompt="a", user_prompt="b") or {}
    _ = debug
    route_debug = backend.last_route_debug
    assert "cache_hit" in route_debug


def test_llm_candidate_provider_exposes_backend_routing_debug(demo_world, demo_state, demo_events):
    routing = RoutingLLMBackend(
        [
            _BrokenBackend(),
            InlineJSONLLMBackend({"candidate_events": [demo_events[0].to_dict()]}),
        ],
        provider_ids=["broken", "inline"],
        max_attempts_per_backend=1,
    )
    provider = LLMCandidateProvider(routing, fallback_provider=LocalRuleBasedStaticFallback(demo_events))
    batch = provider.generate(demo_state, demo_world, min_candidates=2, max_candidates=4)
    assert batch.debug["backend_routing"]["selected_provider"] == "inline"
    assert batch.debug["backend_routing"]["fallback_used"] is True


def test_llm_candidate_provider_exposes_cache_and_budget_debug(demo_world, demo_state, demo_events):
    delegate = _CountingBackend({"candidate_events": [demo_events[0].to_dict()]})
    backend = CachedLLMBackend(
        BudgetedLLMBackend(delegate, max_prompt_chars=50000, estimated_cost_per_1k_chars=0.002),
        max_entries=4,
    )
    provider = LLMCandidateProvider(backend, fallback_provider=LocalRuleBasedStaticFallback(demo_events))
    first = provider.generate(demo_state, demo_world, min_candidates=2, max_candidates=4)
    second = provider.generate(demo_state, demo_world, min_candidates=2, max_candidates=4)
    assert first.debug["backend_routing"]["cache_hit"] is False
    assert second.debug["backend_routing"]["cache_hit"] is True


def test_llm_candidate_provider_falls_back_when_backend_errors(demo_world, demo_state, demo_events):
    provider = LLMCandidateProvider(_BrokenBackend(), fallback_provider=LocalRuleBasedStaticFallback(demo_events))
    batch = provider.generate(demo_state, demo_world, min_candidates=2, max_candidates=4)
    assert batch.debug["backend_error"] == "route_down"
    assert batch.debug["fallback_raw_count"] >= 1


class LocalRuleBasedStaticFallback:
    def __init__(self, demo_events) -> None:
        from src.narrativeos.providers import StaticCandidateProvider

        self._delegate = StaticCandidateProvider(demo_events)

    def generate(self, *args, **kwargs):
        return self._delegate.generate(*args, **kwargs)


def test_llm_renderer_includes_backend_routing_debug(demo_world, demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    routing = RoutingLLMBackend(
        [InlineJSONLLMBackend({"concise_summary": "短摘要", "interactive_scene": "互动场景", "premium_prose": "精修 prose"})],
        provider_ids=["inline"],
        max_attempts_per_backend=1,
    )
    renderer = LLMRenderer(routing, TemplateRenderer())
    rendered = renderer.render(demo_world, demo_state, next_state, event)
    assert rendered.debug["backend_routing"]["selected_provider"] == "inline"


def test_llm_renderer_falls_back_on_backend_error(demo_world, demo_state, demo_events):
    event = {event.event_id: event for event in demo_events}["accept_exam_nomination"]
    next_state = apply_event(demo_state, event)
    renderer = LLMRenderer(_BrokenBackend(), TemplateRenderer())
    rendered = renderer.render(demo_world, demo_state, next_state, event)
    assert rendered.debug["renderer"] == "llm_fallback_template"
    assert rendered.debug["renderer_fallback_reason"] == "llm_backend_error"
