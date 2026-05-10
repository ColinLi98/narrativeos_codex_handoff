import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository


ROOT = Path(__file__).resolve().parents[1]


def test_reader_contract_docs_and_json_exist_and_cover_required_reader_surface():
    md_matrix = ROOT / "docs" / "frontend_reader_api_dependency_matrix.md"
    md_state = ROOT / "docs" / "frontend_reader_shell_state_contract.md"
    json_matrix = ROOT / "docs" / "frontend_reader_api_dependency_matrix.json"
    json_state = ROOT / "docs" / "frontend_reader_shell_state_contract.json"

    assert md_matrix.exists()
    assert md_state.exists()
    assert json_matrix.exists()
    assert json_state.exists()

    matrix_payload = json.loads(json_matrix.read_text(encoding="utf-8"))
    state_payload = json.loads(json_state.read_text(encoding="utf-8"))

    api_paths = {item["path"] for item in matrix_payload["api_dependencies"]}
    assert "/v1/library/worlds" in api_paths
    assert "/v1/library/worlds/{world_id}" in api_paths
    assert "/v1/reader/sessions" in api_paths
    assert "/v1/reader/continue" in api_paths
    assert "/v1/reader/entitlements" in api_paths
    assert "/v1/reader/subscription" in api_paths
    assert "/v1/reader/checkout/start" in api_paths
    assert "/v1/reader/checkout/{checkout_session_id}/complete" in api_paths
    assert "/v1/sessions/{session_id}/replay" in api_paths
    assert "/v1/sessions/{session_id}/prefill" in api_paths

    shell_fields = {item["name"] for item in state_payload["shell_state"]["fields"]}
    reader_fields = {item["name"] for item in state_payload["reader_shell_state"]["fields"]}
    assert shell_fields == {
        "activeProduct",
        "authPage",
        "debug",
        "startupRouteProduct",
        "startupRouteWorkspace",
        "readerWorkspace",
        "lastReaderView",
    }
    assert {
        "worldId",
        "worldVersionId",
        "readerId",
        "readerAuthSession",
        "sessionId",
        "currentBundle",
        "sessionLibrary",
        "authoredWorkLibrary",
        "currentState",
        "latestStep",
        "latestStepFailure",
        "continuityContract",
        "intentPrefill",
        "replay",
        "readerEntitlements",
        "readerSubscription",
        "readerCheckoutSession",
        "pendingCheckoutContext",
        "activeView",
    } <= reader_fields


def test_app_shell_loads_reader_shell_v2_assets_and_container_in_order(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_shell_v2.db")))
    client = TestClient(app)

    shell = client.get("/app")
    assert shell.status_code == 200
    assert 'id="reader-shell-v2"' in shell.text

    reader_runtime_index = shell.text.index("/assets/reader.js")
    reader_v2_dom_index = shell.text.index("/assets/reader_shell_v2_dom.js")
    reader_v2_index = shell.text.index("/assets/reader_shell_v2.js")
    bootstrap_index = shell.text.index("/assets/shell_bootstrap_runtime.js")

    assert reader_runtime_index < reader_v2_dom_index < reader_v2_index < bootstrap_index


def test_reader_shell_v2_assets_and_bootstrap_prefer_v2_runtime(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_shell_v2_assets.db")))
    client = TestClient(app)

    reader_v2_dom = client.get("/assets/reader_shell_v2_dom.js")
    reader_v2 = client.get("/assets/reader_shell_v2.js")
    shell_dom = client.get("/assets/shell_dom.js")
    shell_status = client.get("/assets/shell_status_runtime.js")
    bootstrap = client.get("/assets/shell_bootstrap_runtime.js")

    assert reader_v2_dom.status_code == 200
    assert reader_v2.status_code == 200
    assert shell_dom.status_code == 200
    assert shell_status.status_code == 200
    assert bootstrap.status_code == 200

    assert 'id="reader-shell-v2"' not in reader_v2.text
    assert "readerShellV2" in shell_dom.text
    assert "readerShellV2?.classList.toggle" in shell_status.text
    assert "ReaderShellV2DOM" in reader_v2_dom.text
    assert "initializeReaderRuntime" in reader_v2.text
    assert "renderLanding" in reader_v2.text
    assert "renderRead" in reader_v2.text
    assert "renderStorybook" in reader_v2.text
    assert "renderBackstage" in reader_v2.text
    assert "restoreCheckoutContext" in reader_v2.text
    assert "reader-v2-spotlight" in reader_v2.text
    assert "reader-v2-storybook" in reader_v2.text
    assert "reader-v2-backstage" in reader_v2.text
    assert "reader-v2-backstage-close" in reader_v2.text
    assert "window.ReaderRuntimeLegacy" in reader_v2.text
    assert "window.ReaderRuntime = ReaderShellV2" in reader_v2.text
    assert 'typeof ReaderShellV2 === "object" && ReaderShellV2' in bootstrap.text


def test_reader_shell_v2_storybook_asset_exposes_canvas_beats_and_trajectory(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "reader_storybook_refine.db")))
    client = TestClient(app)

    reader_v2 = client.get("/assets/reader_shell_v2.js")

    assert reader_v2.status_code == 200
    assert "reader-v2-storybook-canvas" in reader_v2.text
    assert "reader-v2-storybook-canvas-meta" in reader_v2.text
    assert "activeAtmosphereImage" in reader_v2.text
    assert "reader-shell-v2__image-panel" in reader_v2.text
    assert "reader-shell-v2__card-media" in reader_v2.text
    assert "reader-v2-storybook-beats" in reader_v2.text
    assert "reader-v2-storybook-beat-summary" in reader_v2.text
    assert "reader-v2-storybook-sequence-summary" in reader_v2.text
    assert "jump-storybook:" in reader_v2.text
