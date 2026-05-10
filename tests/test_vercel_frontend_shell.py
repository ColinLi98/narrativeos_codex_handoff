from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api.app_factory import create_app
from src.narrativeos.repository import SQLAlchemyRepository


def test_vercel_modern_frontend_shell_serves_spa_without_intercepting_api(monkeypatch, tmp_path) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<main>NarrativeOS shell</main>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('shell')", encoding="utf-8")

    monkeypatch.setenv("NARRATIVEOS_SERVE_MODERN_FRONTEND", "1")
    monkeypatch.setenv("NARRATIVEOS_FRONTEND_DIST_DIR", str(dist_dir))

    repository = SQLAlchemyRepository(database_url=f"sqlite:///{tmp_path / 'vercel_shell.db'}")
    client = TestClient(create_app(repository=repository))

    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}

    showcase_response = client.get("/showcase")
    assert showcase_response.status_code == 200
    assert "NarrativeOS shell" in showcase_response.text

    story_response = client.get("/story?session=session_external")
    assert story_response.status_code == 200
    assert "NarrativeOS shell" in story_response.text

    asset_response = client.get("/assets/app.js")
    assert asset_response.status_code == 200
    assert "console.log" in asset_response.text

    legacy_asset_response = client.get("/assets/shell_runtime.js")
    assert legacy_asset_response.status_code == 200
    assert "ShellRuntime" in legacy_asset_response.text


def test_ops_api_calls_do_not_fall_back_to_demo_mode_for_remote_acceptance() -> None:
    client_path = Path("Kimi_Agent_设计系统加载/app/src/api/client.ts")
    client_text = client_path.read_text(encoding="utf-8")

    assert "path.startsWith('/story/') || path.startsWith('/ops/')" in client_text
