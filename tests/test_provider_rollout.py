from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.providers import InlineJSONLLMBackend
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.provider_rollout import ProviderRolloutService
from src.narrativeos.services.provider_routing import ProviderRoutingService


def _ops_headers(client: TestClient, *, actor_id: str = "ops_provider_rollout") -> dict[str, str]:
    registered = client.post(
        "/v1/auth/register",
        json={"actor_id": actor_id, "actor_role": "ops", "password": "secret123", "account_id": actor_id},
    )
    assert registered.status_code == 200
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": "secret123"})
    assert login.status_code == 200
    token = login.json()["token"]["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


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
    headers = _ops_headers(client)

    initial = client.get("/v1/ops/provider-rollout", headers=headers)
    assert initial.status_code == 200
    assert "tracks" in initial.json()

    canary = client.post(
        "/v1/ops/provider-rollout/candidate/canary",
        json={"reviewer_id": "ops_web", "reason": "start canary", "bucket_percentage": 10, "world_allowlist": ["jade_court_exam"]},
        headers=headers,
    )
    assert canary.status_code == 200
    assert canary.json()["tracks"]["candidate"]["rollout_status"] == "canary"

    activate = client.post(
        "/v1/ops/provider-rollout/renderer/activate",
        json={"reviewer_id": "ops_web", "reason": "go active"},
        headers=headers,
    )
    assert activate.status_code == 200
    assert activate.json()["tracks"]["renderer"]["rollout_status"] == "active"

    rollback = client.post(
        "/v1/ops/provider-rollout/candidate/rollback",
        json={"reviewer_id": "ops_web", "reason": "rollback candidate"},
        headers=headers,
    )
    assert rollback.status_code == 200
    assert rollback.json()["tracks"]["candidate"]["rollout_status"] == "rolled_back"
