from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository


def test_ops_shell_loads_split_scripts_in_order(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_frontend.db")))
    client = TestClient(app)

    shell = client.get("/app")
    assert shell.status_code == 200

    script_paths = [
        "/assets/ops_refresh.js",
        "/assets/ops_actions.js",
        "/assets/ops_render_sections.js",
        "/assets/app.js",
    ]
    positions = [shell.text.index(path) for path in script_paths]

    assert positions == sorted(positions)


def test_ops_frontend_assets_keep_refresh_action_render_boundaries(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "ops_assets.db")))
    client = TestClient(app)

    refresh_asset = client.get("/assets/ops_refresh.js")
    actions_asset = client.get("/assets/ops_actions.js")
    render_asset = client.get("/assets/ops_render_sections.js")
    app_asset = client.get("/assets/app.js")

    assert refresh_asset.status_code == 200
    assert actions_asset.status_code == 200
    assert render_asset.status_code == 200
    assert app_asset.status_code == 200

    refresh_text = refresh_asset.text
    actions_text = actions_asset.text
    render_text = render_asset.text
    app_text = app_asset.text

    assert "async function refreshOpsSurface" in refresh_text
    assert "async function refreshOpsAccountFlow" in refresh_text
    assert "function syncOpsNavigationContext" in refresh_text
    assert "function renderOpsSurface" not in refresh_text
    assert "async function assignGovernanceCase" not in refresh_text

    assert "async function assignGovernanceCase" in actions_text
    assert "async function addGovernanceEvidence" in actions_text
    assert "function renderOpsSurface" not in actions_text
    assert "async function refreshOpsSurface" not in actions_text

    assert "function renderOpsSurface" in render_text
    assert "function renderOpsNavigationSection" in render_text
    assert "function renderOpsAccountSection" in render_text
    assert "function renderOpsInvestigationSection" in render_text
    assert "async function refreshOpsSurface" not in render_text
    assert "async function assignGovernanceCase" not in render_text

    assert "async function refreshOpsSurface" not in app_text
    assert "function renderOpsSurface" not in app_text
    assert "async function assignGovernanceCase" not in app_text
