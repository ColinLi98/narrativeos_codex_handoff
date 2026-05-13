from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.models import NarrativeState
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.choice_semantics import build_choice_impacts


ROOT = Path(__file__).resolve().parents[1]


def _auth_headers(client: TestClient, *, actor_id: str, actor_role: str = "author", password: str = "secret123") -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={
            "actor_id": actor_id,
            "actor_role": actor_role,
            "password": password,
            "account_id": actor_id,
        },
    )
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']['access_token']}"}


def _state(chapter_index: int = 1) -> dict:
    return NarrativeState.from_dict(
        {
            "state_id": f"agent_studio_state_{chapter_index}",
            "world_id": "agent_studio_world",
            "turn_index": chapter_index,
            "story_phase": "setup",
            "chapter_index": chapter_index,
            "min_end_turn": 8,
            "fate_pressure": 0.0,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.3,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    ).to_dict()


def test_choice_semantics_are_product_language_and_keep_choice_ids():
    impacts = build_choice_impacts(
        ["追查证据", "保护证人", "隐藏真相"],
        chapter_index=13,
    )

    assert [item["choice_id"] for item in impacts] == ["choice_13_1", "choice_13_2", "choice_13_3"]
    assert impacts[0]["label"] == "追查证据"
    assert impacts[0]["risk_level"] == "高"
    assert impacts[1]["relationship"] == "信任"
    assert impacts[2]["mystery"] == "加深"
    assert all("Q0" not in str(item) for item in impacts)


def test_route_choice_history_repository_round_trips(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "route_choices.db"))

    saved = repository.save_route_choice(
        session_id="studio_session",
        chapter_id="chapter_studio_session_12",
        choice_id="choice_12_2",
        payload_json={
            "choice_id": "choice_12_2",
            "selected_choice": {"label": "保护证人"},
            "director_intent": "增强人物关系",
        },
    )
    history = repository.list_route_choices(session_id="studio_session")

    assert saved["choice_id"] == "choice_12_2"
    assert len(history) == 1
    assert history[0]["payload_json"]["selected_choice"]["label"] == "保护证人"


def test_author_work_nosbook_export_active_route_contains_branch_map_and_choice_history(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "nosbook_export.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    headers = _auth_headers(client, actor_id="agent_studio_author")

    draft = app.state.authoring_service.create_draft_from_brief(
        {
            "genre_preset": "urban_mystery",
            "world_title": "Agent Studio Export",
            "lead_name": "林澈",
            "counterpart_name": "沈知",
            "core_premise": "验证本地创作工作台导出主线。",
            "life_theme": "信任与隐瞒",
            "author_id": "agent_studio_author",
            "account_id": "agent_studio_author",
        }
    )
    work = app.state.author_work_service.create_work(
        world_version_id=draft["world_version_id"],
        account_id="agent_studio_author",
    )
    repository.save_author_work_chapter(
        {
            "work_id": work["work_id"],
            "chapter_index": 1,
            "chapter_title": "第 1 章 · 雾港",
            "body": "雾从码头压下来。\n\n林澈决定先保护证人。",
            "summary": "主角做出第一步选择。",
            "choices_json": ["追查证据", "保护证人", "隐藏真相"],
            "state_snapshot_json": _state(1),
        }
    )
    branch = app.state.author_work_service.create_branch(
        work_id=work["work_id"],
        source_chapter_index=1,
        label="路线 A：保护证人",
        choice_source="保护证人",
        steering_directive={"current_user_intent": "增强人物关系", "summary": "增强人物关系"},
    )

    response = client.get(
        f"/v1/author/works/{work['work_id']}/export",
        headers=headers,
        params={"format": "nosbook", "route": "active"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.narrativeos.nosbook+json")
    payload = response.json()
    assert payload["schema_version"] == "nosbook/v1"
    assert payload["export_route"]["route_name"].startswith("路线 A")
    assert payload["chapters"][0]["choice_impacts"][0]["risk_level"] == "高"
    assert any(item["route_name"] == "主线" for item in payload["branch_map"])
    assert any(item["selected_choice"] == "保护证人" for item in payload["choice_history"])
    assert payload["quality_summary"] == {
        "重复感": "良好",
        "场景细节": "充足",
        "节奏": "稳定",
        "结尾风险": "正常",
    }
    assert branch["is_active_line"] is True


def test_agent_studio_shell_assets_are_registered_and_parseable(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "agent_studio_shell.db")))
    client = TestClient(app)

    shell = client.get("/app")
    assert shell.status_code == 200
    assert 'id="agent-studio-shell"' in shell.text
    assert 'id="agent-studio-director"' in shell.text
    assert "/assets/agent_studio_dom.js" in shell.text
    assert "/assets/agent_studio.js" in shell.text
    assert shell.text.index("/assets/author_workspace.js") < shell.text.index("/assets/agent_studio.js")
    assert "重复感" in shell.text
    agent_shell_slice = shell.text[shell.text.index('id="agent-studio-shell"') : shell.text.index('id="customer-shell"')]
    assert "Q03" not in agent_shell_slice

    runtime = client.get("/assets/agent_studio.js")
    assert runtime.status_code == 200
    assert "AgentStudioRuntime" in runtime.text
    assert "choice_impacts" in runtime.text
    assert "lastNosbookExport" in runtime.text
    assert "NOSBOOK_CONTENT_TYPE" in runtime.text
    assert "application/vnd.narrativeos.nosbook+json" in runtime.text
    assert "generationStatus" in runtime.text
    assert "第一章生成中" in runtime.text
    assert "正在建立作品设定、人物冲突和章节正文，可能需要一两分钟。" in runtime.text
    assert "续写中" in runtime.text
    assert "正在沿导演意图推进下一章，完成后会自动跳到新章节。" in runtime.text
    assert "新路线创建中" in runtime.text
    assert "正在从当前章节保存分支。" in runtime.text
    assert "safeStudioErrorMessage" in runtime.text
    assert "第一章需要重试。" in runtime.text
    assert "这一章还没有达到可读质量" in runtime.text
    assert "第一章暂时没有入库" not in runtime.text
    assert "Q03" not in runtime.text
    assert "Q04" not in runtime.text
    assert "Q05" not in runtime.text
    assert "Q09" not in runtime.text

    node = shutil.which("node")
    if node:
        subprocess.run(
            [node, "-e", f"new Function(require('fs').readFileSync({(ROOT / 'src/narrativeos/web/agent_studio.js').as_posix()!r}, 'utf8'));"],
            check=True,
            cwd=ROOT,
        )


def test_agent_studio_layout_css_keeps_reader_primary():
    styles = (ROOT / "src/narrativeos/web/styles.css").read_text()
    shell_status = (ROOT / "src/narrativeos/web/shell_status_runtime.js").read_text()

    assert 'data-author-workspace="studio"' in styles
    assert 'grid-template-areas: "rail reader director"' not in styles
    assert '"reader director"' in styles
    assert '"rail director"' in styles
    assert 'minmax(320px, 360px)' in styles
    assert "min-height: 560px;" in styles
    assert "min-height: clamp(860px, calc(100vh - 120px), 1040px);" in styles
    assert "grid-template-rows: auto minmax(560px, min(64vh, 680px)) auto auto;" in styles
    assert "max-height: min(720px, 72vh);" in styles
    assert "position: sticky;" in styles
    assert "top: 16px;" in styles
    assert ".toolbar-group--utility .status-grid--compact" in styles
    assert ".session-summary .toolbar-label" in styles
    assert "overflow: visible;" in styles
    assert "max-height: min(360px, 42vh);" in styles
    assert '"director"' in styles
    assert '"reader"' in styles
    assert '"rail"' in styles
    assert '[data-author-workspace="studio"] #shell-status-banner' in styles
    assert "shellDom.appShell.dataset.authorWorkspace" in shell_status


def test_agent_studio_local_launcher_opens_studio_frontend():
    launcher = ROOT / "scripts" / "run_agent_studio_local.sh"
    shell_runtime = ROOT / "src" / "narrativeos" / "web" / "shell_runtime.js"
    author_api = ROOT / "src" / "narrativeos" / "api" / "author.py"
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111

    text = launcher.read_text(encoding="utf-8")
    shell_text = shell_runtime.read_text(encoding="utf-8")
    author_api_text = author_api.read_text(encoding="utf-8")
    assert "AGENT_STUDIO_URL" in text
    assert "product=author&workspace=studio&debug=1&local_studio=1" in text
    assert "AGENT_STUDIO_LOCAL_DB" in text
    assert "DATABASE_URL=\"${DATABASE_URL:-sqlite:///${AGENT_STUDIO_LOCAL_DB}}\"" in text
    assert "export DATABASE_URL" in text
    assert "AGENT_STUDIO_LOCAL_ACCOUNT_ID" in text
    assert "AGENT_STUDIO_OPEN_BROWSER" in text
    assert "scripts/run_backend_local.sh" in text
    assert "/health" in text
    assert "agent_studio_frontend:" in text
    assert "open \"${AGENT_STUDIO_URL}\"" in text
    assert "xdg-open \"${AGENT_STUDIO_URL}\"" in text
    assert "python3 -m webbrowser \"${AGENT_STUDIO_URL}\"" in text
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "product=author&workspace=studio&debug=1&local_studio=1&account_id=agent_studio_user_demo" in readme_text
    assert "narrativeos_agent_studio_local.db" in readme_text
    assert "bootstrapLocalStudioAuthorIfRequested" in shell_text
    assert "local_studio" in shell_text
    assert "isLocalStudioOrigin" in shell_text
    assert "127.0.0.1" in shell_text
    assert "/v1/auth/register" in shell_text
    assert "/v1/auth/login" in shell_text
    assert "/v1/author/local-studio/bootstrap-access" in shell_text
    assert "local_studio_bootstrap_access" in author_api_text
    assert "local_loopback_required" in author_api_text
    assert "creator_pass" in author_api_text
    assert "studio_credits" in author_api_text
    assert "可直接设定故事目标开始创作" in shell_text


def test_local_studio_bootstrap_access_grants_author_creation_entitlements(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "local_studio_bootstrap.db"))
    app = create_app(repository=repository)
    client = TestClient(app)
    headers = _auth_headers(client, actor_id="agent_studio_local_author")

    blocked = client.post(
        "/v1/author/local-studio/bootstrap-access",
        headers={**headers, "host": "example.com"},
        json={"account_id": "agent_studio_local_author"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "local_studio_bootstrap_forbidden"

    response = client.post(
        "/v1/author/local-studio/bootstrap-access",
        headers={**headers, "host": "127.0.0.1"},
        json={"account_id": "agent_studio_local_author", "minimum_studio_credits": 20},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "local_agent_studio_bootstrap_access/v1"
    assert payload["status"] == "ready"
    assert payload["subscription"]["tier_id"] == "creator_pass"
    assert float(payload["wallets"]["studio_credits"]["balance"]) >= 20

    entitlements = client.get(
        "/v1/reader/entitlements?account_id=agent_studio_local_author",
        headers=headers,
    )
    assert entitlements.status_code == 200
    assert entitlements.json()["subscription"]["tier_id"] == "creator_pass"
    assert float(entitlements.json()["wallets"]["studio_credits"]["balance"]) >= 20
