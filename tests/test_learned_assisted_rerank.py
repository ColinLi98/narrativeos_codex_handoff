from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.eval.learned_assisted_rerank import (
    LearnedAssistedRerankService,
    build_assisted_rerank_summary,
    evaluate_assisted_rerank_candidates,
    save_assisted_rerank_config,
)
from src.narrativeos.eval.learned_reranker_baseline import train_learned_reranker_baseline
from src.narrativeos.eval.learned_reranker_promotion_workflow import (
    build_reranker_promotion_workflow_summary,
    save_reranker_promotion_decision,
)
from src.narrativeos.eval.learned_rollout import activate_learned_rollout
from src.narrativeos.models import EventAtom, ScoredCandidate
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.sessions import ReaderContinueCommand, SessionService
from tests.conftest import load_example
from tests.test_learned_reranker_baseline import _seed_reranker_world


def _candidate(event_id: str, total_score: float, *, tension: float = 0.0) -> ScoredCandidate:
    raw_event = next(item for item in load_example("demo_event_atoms.json") if item["event_id"] == event_id)
    event = EventAtom.from_dict(raw_event)
    return ScoredCandidate(
        event=event,
        total_score=total_score,
        components={
            "desire_pull": total_score,
            "dramatic_tension_delta": tension,
            "character_fidelity": total_score * 0.8,
        },
        explanation=f"score {total_score}",
    )


class _PreferChallengerService(LearnedAssistedRerankService):
    def __init__(self) -> None:
        pass

    def availability(self):
        return {"available": True}

    def compare(self, preferred, alternative, *, world_id: str):
        return {
            "available": True,
            "preferred_event_id": preferred.event.event_id,
            "alternative_event_id": alternative.event.event_id,
            "preferred_probability": 0.21 if alternative.event.event_id == "confide_in_tutor_xu" else 0.72,
            "alternative_probability": 0.88 if alternative.event.event_id == "confide_in_tutor_xu" else 0.28,
            "score_gap": round(float(preferred.total_score) - float(alternative.total_score), 4),
        }


def test_assisted_rerank_summary_defaults_to_disabled_shadow_mode(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_rerank_empty.db"))
    summary = build_assisted_rerank_summary(repository=repository)

    assert summary["config"]["config"]["enabled"] is False
    assert summary["config"]["config"]["mode"] == "shadow_only"
    assert summary["recommended_next_action"] == "enable_shadow_only_rerank_capture"


def test_assisted_rerank_shadow_only_receipt_does_not_reorder(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_rerank_shadow.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    ranked = [
        _candidate("accept_exam_nomination", 0.78),
        _candidate("confide_in_tutor_xu", 0.76),
        _candidate("secret_meet_lin_wan", 0.74),
    ]
    save_assisted_rerank_config(
        repository=repository,
        reviewer_id="ops_web",
        reason="先只跑 shadow。",
        enabled=True,
        mode="shadow_only",
        bucket_percentage=100,
        confidence_threshold=0.65,
        candidate_window=3,
        max_score_gap=0.08,
        world_allowlist=[],
    )
    result = evaluate_assisted_rerank_candidates(
        repository=repository,
        world_id="urban_mystery_lotus_lane",
        world_version_id=world_version_id,
        ranked_candidates=ranked,
        beat_index=1,
        rerank_service=_PreferChallengerService(),
        persist_receipt=False,
    )

    assert result["receipt"]["mode"] == "shadow_only"
    assert result["receipt"]["would_swap"] is True
    assert result["receipt"]["assisted_action"] == "none"
    assert result["ranked_candidates"][0].event.event_id == "accept_exam_nomination"


def test_assisted_rerank_can_reorder_after_rollout_and_enablement(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_rerank_active.db"))
    world_version_id = _seed_reranker_world(repository, world_id="urban_mystery_lotus_lane")
    reranker_artifact_dir = tmp_path / "rerank_artifacts"
    train_learned_reranker_baseline(
        repository=repository,
        output_dir=reranker_artifact_dir,
        dataset_view="reranker",
        world_version_id=world_version_id,
    )
    workflow = build_reranker_promotion_workflow_summary(
        repository=repository,
        world_version_id=world_version_id,
        reranker_artifact_dir=reranker_artifact_dir,
        evaluator_artifact_dir=tmp_path / "missing_eval",
    )
    save_reranker_promotion_decision(
        repository=repository,
        reviewer_id="ops_promoter",
        reason="允许 reranker 进入实验 rollout。",
        status="approved",
        recommendation_summary=workflow,
    )
    activate_learned_rollout(
        repository=repository,
        track="reranker",
        reviewer_id="ops_promoter",
        reason="启动 reranker rollout。",
        world_version_id=world_version_id,
        evaluator_artifact_dir=tmp_path / "missing_eval",
        reranker_artifact_dir=reranker_artifact_dir,
    )
    save_assisted_rerank_config(
        repository=repository,
        reviewer_id="ops_web",
        reason="开启 assisted rerank。",
        enabled=True,
        mode="assisted_rerank",
        bucket_percentage=100,
        confidence_threshold=0.65,
        candidate_window=3,
        max_score_gap=0.08,
        world_allowlist=[],
    )
    ranked = [
        _candidate("accept_exam_nomination", 0.78),
        _candidate("confide_in_tutor_xu", 0.76),
        _candidate("secret_meet_lin_wan", 0.74),
    ]
    result = evaluate_assisted_rerank_candidates(
        repository=repository,
        world_id="urban_mystery_lotus_lane",
        world_version_id=world_version_id,
        ranked_candidates=ranked,
        beat_index=1,
        reranker_artifact_dir=reranker_artifact_dir,
        rerank_service=_PreferChallengerService(),
        persist_receipt=False,
    )

    assert result["receipt"]["guardrail_status"] == "eligible"
    assert result["receipt"]["assisted_action"] == "rerank_top_candidate"
    assert result["ranked_candidates"][0].event.event_id == "confide_in_tutor_xu"


def test_session_service_persists_assisted_rerank_receipt(tmp_path: Path, monkeypatch):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_rerank_session.db"))
    service = SessionService(repository)
    session = service.create_session("jade_court_exam", reader_id="reader_rerank")

    def _receipt(**kwargs):
        ranked_candidates = list(kwargs["ranked_candidates"])
        swapped = [ranked_candidates[1], ranked_candidates[0], *ranked_candidates[2:]]
        return {
            "ranked_candidates": swapped,
            "receipt": {
                "mode": "assisted_rerank",
                "bucket_match": True,
                "guardrail_status": "eligible",
                "beat_index": kwargs.get("beat_index"),
                "baseline_event_id": ranked_candidates[0].event.event_id,
                "selected_event_id": swapped[0].event.event_id,
                "would_swap": True,
                "assisted_action": "rerank_top_candidate",
            },
        }

    monkeypatch.setattr("src.narrativeos.eval.learned_assisted_rerank.evaluate_assisted_rerank_candidates", _receipt)
    result = service.continue_story(ReaderContinueCommand(session["session_id"], freeform_intent="继续。"), reader_id="reader_rerank")
    latest_step = repository.get_latest_step(session["session_id"])
    analytics = repository.list_analytics_events(event_names=["learned_assisted_rerank_evaluated", "learned_assisted_rerank_applied"])

    assert result["status"] == "ok"
    assert latest_step is not None
    receipts = latest_step.metadata.get("assisted_rerank_receipts", [])
    assert receipts
    assert receipts[0]["assisted_action"] == "rerank_top_candidate"
    assert receipts[0]["selected_event_id"] == latest_step.chosen_event.event_id
    assert any(item["event_name"] == "learned_assisted_rerank_evaluated" for item in analytics)
    assert any(item["event_name"] == "learned_assisted_rerank_applied" for item in analytics)


def test_assisted_rerank_endpoints_can_configure_and_report_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "assisted_rerank_api.db"))
    client = TestClient(create_app(repository=repository))

    initial = client.get("/v1/ops/learned-assisted-rerank")
    assert initial.status_code == 200
    assert initial.json()["config"]["config"]["mode"] == "shadow_only"

    configured = client.post(
        "/v1/ops/learned-assisted-rerank/configure",
        json={
            "reviewer_id": "ops_web",
            "reason": "先开 rerank shadow。",
            "enabled": True,
            "mode": "shadow_only",
            "bucket_percentage": 15,
            "confidence_threshold": 0.65,
            "candidate_window": 3,
            "max_score_gap": 0.08,
            "world_allowlist": ["urban_mystery_lotus_lane"],
        },
    )
    assert configured.status_code == 200
    assert configured.json()["config"]["config"]["enabled"] is True
    assert configured.json()["config"]["config"]["candidate_window"] == 3
