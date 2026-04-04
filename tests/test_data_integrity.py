from __future__ import annotations

from pathlib import Path

from src.narrativeos.persistence.db import RouteChoiceRow, SessionRow
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from src.narrativeos.services.billing import BillingService
from src.narrativeos.services.data_integrity import DataIntegrityService
from src.narrativeos.services.monetization import MonetizationService
from src.narrativeos.services.observability import ObservabilityService
from src.narrativeos.services.sessions import ReaderContinueCommand, SessionService
from src.narrativeos.intent import SimpleIntentParser
from src.narrativeos.rendering import TemplateRenderer


def _build_session_service(repository: SQLAlchemyRepository) -> SessionService:
    monetization = MonetizationService(repository)
    billing = BillingService(repository, monetization_service=monetization)
    return SessionService(
        repository,
        intent_parser=SimpleIntentParser(),
        renderer=TemplateRenderer(),
        analytics_service=AnalyticsService(repository),
        billing_service=billing,
        observability_service=ObservabilityService(repository),
    )


def test_data_integrity_summary_and_safe_repairs(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "data_integrity.db"))
    session_service = _build_session_service(repository)
    service = DataIntegrityService(repository)

    created = session_service.create_session("jade_court_exam", reader_id="reader_integrity")
    stepped = session_service.continue_story(
        ReaderContinueCommand(session_id=created["session_id"], freeform_intent="我继续向前。"),
        reader_id="reader_integrity",
    )
    assert stepped["status"] == "ok"

    latest_step = repository.get_latest_step(created["session_id"])
    assert latest_step is not None
    repository.save_step(
        latest_step,
        world_version_id=created["world_version_id"],
        entitlements_snapshot={},
        cost_estimate=0.1,
    )
    assert len(repository.list_steps(created["session_id"])) == 1

    repository.save_subscription({"account_id": "acct_dup", "tier_id": "play_pass", "status": "active"})
    repository.save_subscription({"account_id": "acct_dup", "tier_id": "play_pass", "status": "trialing"})

    with repository.SessionLocal() as session:
        row = session.get(SessionRow, created["session_id"])
        state = dict(row.narrative_state_json or {})
        state["chapter_index"] = 0
        state["story_phase"] = "setup"
        row.chapter_index = 0
        row.story_phase = "setup"
        row.narrative_state_json = state
        session.add(
            RouteChoiceRow(
                session_id="ghost_session",
                chapter_id="ghost_chapter",
                choice_id="choice_ghost",
                payload_json={},
            )
        )
        session.commit()

    summary = service.build_summary(limit=10)
    assert summary["hotspot_index_summary"]["missing_count"] == 0
    assert summary["concurrency_summary"]["session_pointer_drift_count"] >= 1
    assert summary["concurrency_summary"]["orphan_route_choice_count"] >= 1
    assert summary["concurrency_summary"]["duplicate_active_subscription_count"] >= 1

    dry_run = service.run_repair(
        actions=["reconcile_session_chapter_pointers", "prune_orphan_route_choices"],
        apply=False,
        limit=10,
    )
    assert dry_run["changed"] is False
    assert len(dry_run["action_results"]) == 2

    applied = service.run_repair(
        actions=["reconcile_session_chapter_pointers", "prune_orphan_route_choices"],
        apply=True,
        limit=10,
    )
    assert applied["changed"] is True
    assert any(item["applied_count"] >= 1 for item in applied["action_results"])

    repaired = service.build_summary(limit=10)
    assert repaired["concurrency_summary"]["session_pointer_drift_count"] == 0
    assert repaired["concurrency_summary"]["orphan_route_choice_count"] == 0
    assert repaired["concurrency_summary"]["duplicate_active_subscription_count"] >= 1
