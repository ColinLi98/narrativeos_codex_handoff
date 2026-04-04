from pathlib import Path

from src.narrativeos.providers import BudgetedLLMBackend, InlineJSONLLMBackend
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.billing import BillingService
from src.narrativeos.services.observability import ObservabilityService
from src.narrativeos.services.provider_rollout import ProviderRolloutService
from src.narrativeos.services.provider_routing import ProviderRoutingService
from src.narrativeos.services.sessions import ReaderContinueCommand, SessionService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _long_prose() -> str:
    return "夜色贴着回廊一路压下来，灯影在石阶上来回晃动，像谁的心事始终落不稳。她没有立刻开口，只让那口气在胸腔里停了一停，再把那句早该问出口的话缓慢送到他面前。" * 4


def test_reader_runtime_uses_primary_candidate_and_renderer_backends(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_runtime_reader.db"))
    observability = ObservabilityService(repository)
    world_record = repository.get_world("jade_court_exam")
    routing = ProviderRoutingService(
        candidate_backend=InlineJSONLLMBackend({"candidate_events": [event.to_dict() for event in world_record.event_atoms[:6]]}),
        renderer_backend=InlineJSONLLMBackend(
            {
                "concise_summary": "短摘要",
                "interactive_scene": "互动场景",
                "premium_prose": _long_prose(),
                "story_title": "测试标题",
                "chapter_summary": "测试摘要",
            }
        ),
    )
    service = SessionService(
        repository,
        billing_service=BillingService(repository),
        analytics_service=AnalyticsService(repository),
        observability_service=observability,
        provider_routing_service=routing,
    )

    session = service.create_session("jade_court_exam", reader_id="reader_rt_primary")
    result = service.continue_story(ReaderContinueCommand(session["session_id"], freeform_intent="继续。"), reader_id="reader_rt_primary")
    latest_step = repository.get_latest_step(session["session_id"])
    receipts = observability.list_runtime_receipts(account_id="reader_rt_primary", limit=5)

    assert result["status"] == "ok"
    assert latest_step is not None
    assert latest_step.candidate_batch.debug["backend_routing"]["selected_provider"] == "inline_json"
    assert latest_step.candidate_batch.debug["backend_error"] is None
    assert latest_step.rendered_scene.debug["backend_routing"]["selected_provider"] == "inline_json"
    assert receipts[0]["selected_provider"] == "inline_json"
    assert receipts[0]["backend_error"] is None


def test_reader_runtime_falls_back_when_budget_blocks_primary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_runtime_budget.db"))
    observability = ObservabilityService(repository)
    routing = ProviderRoutingService(
        candidate_backend=BudgetedLLMBackend(
            InlineJSONLLMBackend({"candidate_events": []}),
            max_prompt_chars=5,
            estimated_cost_per_1k_chars=0.002,
        ),
        renderer_backend=BudgetedLLMBackend(
            InlineJSONLLMBackend(
                {
                    "concise_summary": "短摘要",
                    "interactive_scene": "互动场景",
                    "premium_prose": _long_prose(),
                }
            ),
            max_prompt_chars=5,
            estimated_cost_per_1k_chars=0.002,
        ),
    )
    service = SessionService(
        repository,
        billing_service=BillingService(repository),
        analytics_service=AnalyticsService(repository),
        observability_service=observability,
        provider_routing_service=routing,
    )

    session = service.create_session("jade_court_exam", reader_id="reader_rt_budget")
    result = service.continue_story(ReaderContinueCommand(session["session_id"], freeform_intent="继续。"), reader_id="reader_rt_budget")
    latest_step = repository.get_latest_step(session["session_id"])
    receipts = observability.list_runtime_receipts(account_id="reader_rt_budget", limit=5)

    assert result["status"] == "ok"
    assert latest_step is not None
    assert latest_step.candidate_batch.debug["backend_routing"]["budget_blocked"] is True
    assert latest_step.candidate_batch.debug["backend_routing"]["fallback_used"] is True
    assert latest_step.rendered_scene.debug["renderer"] == "llm_fallback_template"
    assert latest_step.rendered_scene.debug["backend_routing"]["budget_blocked"] is True
    assert receipts[0]["budget_blocked"] is True
    assert receipts[0]["fallback_used"] is True


def test_reader_runtime_respects_candidate_rollout_rollback(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_runtime_rollout.db"))
    observability = ObservabilityService(repository)
    world_record = repository.get_world("jade_court_exam")
    rollout = ProviderRolloutService(repository)
    rollout.save_track_decision(
        track="candidate",
        reviewer_id="ops_web",
        reason="rollback candidate runtime",
        rollout_status="rolled_back",
    )
    routing = ProviderRoutingService(
        rollout_service=rollout,
        candidate_backend=InlineJSONLLMBackend({"candidate_events": [event.to_dict() for event in world_record.event_atoms[:6]]}),
        renderer_backend=InlineJSONLLMBackend(
            {
                "concise_summary": "短摘要",
                "interactive_scene": "互动场景",
                "premium_prose": _long_prose(),
                "story_title": "测试标题",
                "chapter_summary": "测试摘要",
            }
        ),
    )
    service = SessionService(
        repository,
        billing_service=BillingService(repository),
        analytics_service=AnalyticsService(repository),
        observability_service=observability,
        provider_routing_service=routing,
    )

    session = service.create_session("jade_court_exam", reader_id="reader_rt_rollout")
    result = service.continue_story(ReaderContinueCommand(session["session_id"], freeform_intent="继续。"), reader_id="reader_rt_rollout")
    latest_step = repository.get_latest_step(session["session_id"])

    assert result["status"] == "ok"
    assert latest_step is not None
    assert latest_step.candidate_batch.debug["provider_rollout"]["rollout_status"] == "rolled_back"
    assert latest_step.candidate_batch.debug["provider_rollout"]["enabled"] is False


def test_authoring_simulation_preserves_routing_trace_and_fallback(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_runtime_authoring.db"))
    observability = ObservabilityService(repository)
    registry = FileSystemWorldRegistry()
    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "1.0.9"
    pack["manifest"]["author_id"] = "routing_author"
    routing = ProviderRoutingService(
        candidate_backend=BudgetedLLMBackend(
            InlineJSONLLMBackend({"candidate_events": []}),
            max_prompt_chars=5,
            estimated_cost_per_1k_chars=0.002,
        ),
        renderer_backend=BudgetedLLMBackend(
            InlineJSONLLMBackend(
                {
                    "concise_summary": "短摘要",
                    "interactive_scene": "互动场景",
                    "premium_prose": _long_prose(),
                }
            ),
            max_prompt_chars=5,
            estimated_cost_per_1k_chars=0.002,
        ),
    )
    authoring = AuthoringService(
        repository,
        registry=registry,
        billing_service=BillingService(repository),
        provider_routing_service=routing,
        observability_service=observability,
    )

    draft = authoring.save_draft(pack)
    report = authoring.run_simulation_for_world_version(draft["world_version_id"], include_cross_pack=False, max_chapters=1)
    receipts = observability.list_runtime_receipts(account_id="routing_author", limit=10)

    assert report["chapter_trace"]
    assert report["chapter_trace"][0]["candidate_backend_routing"]["budget_blocked"] is True
    assert report["chapter_trace"][0]["candidate_backend_routing"]["fallback_used"] is True
    assert report["chapter_trace"][0]["renderer_backend_routing"]["budget_blocked"] is True
    assert any(item["surface"] == "authoring_simulation" for item in receipts)
