from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.review import ReviewService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_ops_release_workspace_summarizes_publish_blockers_and_actions(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_release_workspace.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository)
    app = create_app(repository=repository)

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.4"
    pack["manifest"]["author_id"] = "ops_release"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    authoring.submit_for_review(draft["world_version_id"])
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": False,
        "latest_decision": "block",
        "evaluation_summary": {"pass_rate": 0.0, "rewrite_rate": 0.0, "block_rate": 1.0},
        "cross_pack_summary": {
            "cross_pack_pass_rate": 0.4,
            "top_failing_packs": [{"world_id": "jade_court_exam"}],
            "delta_summary": {"cross_pack_pass_rate_delta": -0.1, "regressions": ["cross_pack_pass_rate"], "world_deltas": {}},
            "worlds": [],
        },
        "top_failing_packs": [{"world_id": "jade_court_exam"}],
    }
    repository.save_world_version(version, publish=False)

    payload = app.state.ops_release_workspace_service.world_release_workspace(world_id="urban_mystery_lotus_lane", limit=12)
    assert payload["release_summary"]["selected_world_version_id"] == draft["world_version_id"]
    assert payload["publish_blockers"]["items"]
    handlers = {item["handler"] for item in payload["action_pack"]}
    assert "run_release_investigation" in handlers
    assert any(item["handler"] == "inspect_publish_blocker" for item in payload["action_pack"])
    assert payload["version_matrix"]
    assert payload["operator_timeline"]

    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "ok": True,
        "latest_decision": "pass",
        "evaluation_summary": {"pass_rate": 1.0, "rewrite_rate": 0.0, "block_rate": 0.0},
        "cross_pack_summary": {
            "cross_pack_pass_rate": 0.9,
            "top_failing_packs": [],
            "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": [], "world_deltas": {}},
            "worlds": [],
        },
    }
    repository.save_world_version(version, publish=False)
    ready_payload = app.state.ops_release_workspace_service.world_release_workspace(world_id="urban_mystery_lotus_lane", limit=12)
    ready_handlers = {item["handler"] for item in ready_payload["action_pack"]}
    assert ready_payload["release_summary"]["health_status"] in {"ready", "watch"}
    assert "publish_world_version" in ready_handlers


def test_ops_release_workspace_endpoint_and_shell(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_release_workspace_api.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    review = ReviewService(repository)
    app = create_app(repository=repository)
    client = TestClient(app)

    pack = registry.get_published_world("xianxia_forgotten_vow")["worldpack"]
    pack["version"] = "0.2.2"
    pack["manifest"]["author_id"] = "ops_release_api"
    draft = authoring.save_draft(pack)
    authoring.run_simulation_for_world_version(draft["world_version_id"])
    authoring.submit_for_review(draft["world_version_id"])

    shell = client.get("/app")
    assert shell.status_code == 200
    assert "发布 / Checklist / 回滚统一处置页" in shell.text
    assert "Refresh Release Workspace" in shell.text

    workspace = client.get("/v1/ops/worlds/xianxia_forgotten_vow/release-workspace")
    assert workspace.status_code == 200
    payload = workspace.json()
    assert "release_summary" in payload
    assert "publish_blockers" in payload
    assert "rollback_workspace" in payload
    assert "action_pack" in payload
    assert "operator_timeline" in payload
