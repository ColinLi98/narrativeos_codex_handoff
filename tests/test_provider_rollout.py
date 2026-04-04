from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.providers import InlineJSONLLMBackend
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.provider_rollout import ProviderRolloutService
from src.narrativeos.services.provider_routing import ProviderRoutingService


def test_provider_rollout_defaults_follow_backend_presence(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_rollout_default.db"))
    service = ProviderRolloutService(repository)

    candidate = service.track_summary(track="candidate", backend_present=True)
    renderer = service.track_summary(track="renderer", backend_present=False)

    assert candidate["rollout_status"] == "active"
    assert renderer["rollout_status"] == "shadow"


def test_provider_rollout_canary_resolution_uses_bucket_and_world_allowlist(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_rollout_canary.db"))
    rollout = ProviderRolloutService(repository)
    rollout.save_track_decision(
        track="candidate",
        reviewer_id="ops_web",
        reason="start canary",
        rollout_status="canary",
        bucket_percentage=100,
        world_allowlist=["jade_court_exam"],
    )

    match = rollout.resolve_track(
        track="candidate",
        backend_present=True,
        surface="reader",
        account_id="acct_rollout",
        world_id="jade_court_exam",
        world_version_id="jade_court_exam@1.0.0",
    )
    miss = rollout.resolve_track(
        track="candidate",
        backend_present=True,
        surface="reader",
        account_id="acct_rollout",
        world_id="urban_mystery_lotus_lane",
        world_version_id="urban_mystery_lotus_lane@0.9.1",
    )

    assert match["enabled"] is True
    assert match["canary_match"] is True
    assert miss["enabled"] is False
    assert miss["world_match"] is False


def test_provider_routing_service_respects_rolled_back_track(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_rollout_routing.db"))
    rollout = ProviderRolloutService(repository)
    rollout.save_track_decision(
        track="candidate",
        reviewer_id="ops_web",
        reason="rollback candidate",
        rollout_status="rolled_back",
    )
    routing = ProviderRoutingService(
        rollout_service=rollout,
        candidate_backend=InlineJSONLLMBackend({"candidate_events": []}),
    )
    runtime = repository.get_runtime_bundle("jade_court_exam@1.0.0")
    provider = routing.build_candidate_provider(
        runtime.event_atoms,
        surface="reader",
        account_id="acct_reader",
        session_id="session_reader",
        world_id="jade_court_exam",
        world_version_id="jade_court_exam@1.0.0",
    )
    batch = provider.generate(runtime.initial_state, runtime.world_record.world, depth=0, min_candidates=2, max_candidates=4)

    assert batch.debug["provider_rollout"]["rollout_status"] == "rolled_back"
    assert batch.debug["provider_rollout"]["enabled"] is False


def test_provider_rollout_endpoints_canary_activate_and_rollback(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "provider_rollout_api.db"))
    app = create_app(
        repository=repository,
        candidate_backend=InlineJSONLLMBackend({"candidate_events": []}),
        renderer_backend=InlineJSONLLMBackend({"concise_summary": "s", "interactive_scene": "i", "premium_prose": "p"}),
    )
    client = TestClient(app)

    initial = client.get("/v1/ops/provider-rollout")
    assert initial.status_code == 200
    assert "tracks" in initial.json()

    canary = client.post(
        "/v1/ops/provider-rollout/candidate/canary",
        json={"reviewer_id": "ops_web", "reason": "start canary", "bucket_percentage": 10, "world_allowlist": ["jade_court_exam"]},
    )
    assert canary.status_code == 200
    assert canary.json()["tracks"]["candidate"]["rollout_status"] == "canary"

    activate = client.post(
        "/v1/ops/provider-rollout/renderer/activate",
        json={"reviewer_id": "ops_web", "reason": "go active"},
    )
    assert activate.status_code == 200
    assert activate.json()["tracks"]["renderer"]["rollout_status"] == "active"

    rollback = client.post(
        "/v1/ops/provider-rollout/candidate/rollback",
        json={"reviewer_id": "ops_web", "reason": "rollback candidate"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["tracks"]["candidate"]["rollout_status"] == "rolled_back"
