from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.models import (
    CandidateBatch,
    EvaluationDecision,
    EvaluationReport,
    EvaluationScores,
    NarrativeState,
    NarrativeViewModel,
    SessionRecord,
    StepRecord,
)
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository


def _seed_reader_chapter(
    repository: SQLAlchemyRepository,
    *,
    session_id: str,
    world_id: str,
    world_version_id: str,
    initial_state: NarrativeState,
    chapter_index: int,
    overall_score: float,
    created_at: str,
) -> None:
    state_before = NarrativeState.from_dict(initial_state.to_dict())
    state_before.world_id = world_id
    state_before.chapter_index = max(0, chapter_index - 1)
    state_after = NarrativeState.from_dict(state_before.to_dict())
    state_after.chapter_index = chapter_index
    step = StepRecord(
        session_id=session_id,
        step_index=chapter_index,
        player_input="继续读下去。",
        intent_vector={"curiosity": 0.7},
        candidate_batch=CandidateBatch(raw_candidates=[], legal_candidates=[], illegal_candidate_reasons={}, debug={}),
        scored_candidates=[],
        routes=[],
        chosen_event=None,
        chapter_plan=None,
        scene_beats=[],
        scene_render_spec=None,
        rendered_scene=None,
        reader_view=NarrativeViewModel(
            chapter_title=f"第 {chapter_index} 章",
            chapter_index=chapter_index,
            recap="",
            body=f"chapter {chapter_index}",
            scene_card={},
            choices=["继续"],
            relationship_hints=[],
            can_continue=True,
        ),
        state_before=state_before,
        state_after=state_after,
        critic_trace=[],
        promise_ledger_snapshot=[],
        created_at=created_at,
        metadata={},
    )
    repository.save_step(step, world_version_id=world_version_id, entitlements_snapshot={}, cost_estimate=0.0)
    report = EvaluationReport(
        chapter_id=f"chapter_{session_id}_{chapter_index}",
        world_version_id=world_version_id,
        session_id=session_id,
        decision=EvaluationDecision(decision="pass", reason="test"),
        issues=[] if overall_score >= 0.5 else [],
        scores=EvaluationScores(
            readability=overall_score,
            scene_density=overall_score,
            character_fidelity=overall_score,
            causal_continuity=overall_score,
            pacing=overall_score,
            choice_distinctness=overall_score,
            hook_quality=overall_score,
            monetize_ready=overall_score,
            overall_score=overall_score,
        ),
        hard_validator_results={},
        summary="test",
        created_at=created_at,
    )
    repository.save_evaluation_report(report.chapter_id, report)


def test_repository_eval_metrics_computes_real_continuation_correlation(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "eval_corr.db"))
    world = repository.list_worlds()[0]
    runtime = repository.get_runtime_bundle(world["latest_version"])
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=48)).isoformat()

    session_record = repository.create_session_record(
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        reader_id="reader_corr",
        session_id="session_corr",
        entitlements_snapshot={},
    )

    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=world["world_id"],
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=1,
        overall_score=0.95,
        created_at=old_time,
    )
    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=world["world_id"],
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=2,
        overall_score=0.20,
        created_at=old_time,
    )

    with repository.SessionLocal() as session:
        row = session.get(SessionRow, session_record.session_id)
        assert row is not None
        row.updated_at = old_time
        session.commit()

    metrics = repository.aggregate_eval_metrics(world_version_id=runtime.world_version_id)
    assert metrics["continuation_signal_summary"]["sample_count"] == 2
    assert metrics["continuation_signal_summary"]["positive_count"] == 1
    assert metrics["continuation_signal_summary"]["negative_count"] == 1
    assert metrics["online_continuation_correlation"] > 0.9
    assert metrics["continuation_world_details"]
    assert metrics["continuation_version_details"]
    assert metrics["continuation_sample_accumulation"]["target_sample_count_per_world"] >= 1
    correlations = {item["metric"]: item["correlation"] for item in metrics["quality_signal_correlations"]}
    assert correlations["overall_score"] > 0.9
    assert correlations["pacing"] > 0.9


def test_eval_metrics_endpoint_exposes_correlation_summary(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "eval_corr_api.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    response = client.get("/v1/ops/eval-metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "continuation_signal_summary" in payload
    assert "quality_signal_correlations" in payload
    assert "continuation_world_details" in payload
    assert "continuation_version_details" in payload
    assert "continuation_sample_accumulation" in payload


def test_eval_metrics_detail_endpoints_return_world_and_version_drilldown(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "eval_corr_detail_api.db"))
    world = repository.list_worlds()[0]
    runtime = repository.get_runtime_bundle(world["latest_version"])
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=48)).isoformat()
    session_record = repository.create_session_record(
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        reader_id="reader_corr_detail",
        session_id="session_corr_detail",
        entitlements_snapshot={},
    )
    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=world["world_id"],
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=1,
        overall_score=0.9,
        created_at=old_time,
    )
    _seed_reader_chapter(
        repository,
        session_id=session_record.session_id,
        world_id=world["world_id"],
        world_version_id=runtime.world_version_id,
        initial_state=runtime.initial_state,
        chapter_index=2,
        overall_score=0.1,
        created_at=old_time,
    )
    with repository.SessionLocal() as session:
        row = session.get(SessionRow, session_record.session_id)
        assert row is not None
        row.updated_at = old_time
        session.commit()

    app = create_app(repository=repository)
    client = TestClient(app)

    world_detail = client.get(f"/v1/ops/eval-metrics/worlds/{world['world_id']}")
    version_detail = client.get(f"/v1/ops/eval-metrics/world-versions/{world['latest_version']}")

    assert world_detail.status_code == 200
    assert version_detail.status_code == 200
    assert world_detail.json()["world_id"] == world["world_id"]
    assert version_detail.json()["world_version_id"] == world["latest_version"]
