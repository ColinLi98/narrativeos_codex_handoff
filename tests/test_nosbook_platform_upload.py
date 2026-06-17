from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.models import NarrativeState
from src.narrativeos.repository import SQLAlchemyRepository


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
            "state_id": f"nosbook_upload_state_{chapter_index}",
            "world_id": "nosbook_upload_world",
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


def _minimal_nosbook(*, world_version_id: str = "unknown_world_version") -> Dict[str, Any]:
    return {
        "schema_version": "nosbook/v1",
        "content_type": "application/vnd.narrativeos.nosbook+json",
        "filename": "import-test.nosbook",
        "work": {
            "title": "上传闭环测试",
            "world_version_id": world_version_id,
            "route_name": "主线",
            "chapter_count": 1,
            "target_chapter_count": 10,
        },
        "export_route": {"route": "active", "route_name": "主线", "is_active_line": True},
        "chapters": [
            {
                "chapter_index": 1,
                "chapter_title": "第 1 章 · 雾港",
                "body": "雾从码头压下来。\n\n林澈把证据藏进衣袋，决定先相信证人。",
                "summary": "主角保留证据并相信证人。",
                "choices": ["追查证据", "保护证人"],
                "choice_impacts": [
                    {
                        "choice_id": "choice_1_1",
                        "label": "追查证据",
                        "risk_level": "高",
                        "emotion": "冲突",
                        "pacing": "推进",
                        "relationship": "怀疑",
                        "mystery": "加深",
                    }
                ],
            }
        ],
        "branch_map": [
            {
                "route_name": "主线",
                "current_chapter_count": 1,
                "recent_choice": "主线推进",
                "quality_status": "稳定",
                "is_export_main_route": True,
                "fork_after_chapter_index": 0,
            }
        ],
        "choice_history": [
            {
                "route_name": "主线",
                "chapter_index": 1,
                "selected_choice": "保护证人",
                "expected_effect": "增强人物关系",
            }
        ],
        "quality_summary": {
            "重复感": "良好",
            "场景细节": "充足",
            "节奏": "稳定",
            "结尾风险": "正常",
        },
        "cover": {"mode": "default", "source": "agent_studio_default_cover", "metadata": {}},
    }


def _load_upload_module():
    spec = importlib.util.spec_from_file_location("upload_nosbook", ROOT / "scripts" / "upload_nosbook.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nosbook_import_api_requires_bearer_token(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{tmp_path / 'missing_token.db'}"))
    client = TestClient(app)

    response = client.post("/v1/author/nosbooks/import", json=_minimal_nosbook())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "nosbook_import_auth_required"


def test_nosbook_import_rejects_invalid_schema_and_empty_chapters(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url=f"sqlite:///{tmp_path / 'invalid_schema.db'}"))
    client = TestClient(app)
    headers = _auth_headers(client, actor_id="nosbook_invalid_author")

    invalid_schema = _minimal_nosbook()
    invalid_schema["schema_version"] = "nosbook/v2"
    invalid_response = client.post("/v1/author/nosbooks/import", headers=headers, json=invalid_schema)
    assert invalid_response.status_code == 400
    assert invalid_response.json()["detail"]["code"] == "unsupported_nosbook_schema"

    empty_chapters = _minimal_nosbook()
    empty_chapters["chapters"] = []
    empty_response = client.post("/v1/author/nosbooks/import", headers=headers, json=empty_chapters)
    assert empty_response.status_code == 400
    assert empty_response.json()["detail"]["reason"] == "nosbook_chapters_must_be_non_empty_array"


def test_nosbook_import_unknown_world_creates_source_only_private_draft(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url=f"sqlite:///{tmp_path / 'source_only.db'}")
    app = create_app(repository=repository)
    client = TestClient(app)
    headers = _auth_headers(client, actor_id="nosbook_source_only_author")

    response = client.post("/v1/author/nosbooks/import", headers=headers, json=_minimal_nosbook(world_version_id="missing_world_version"))

    assert response.status_code == 200
    result = response.json()
    assert result["schema_version"] == "nosbook_import_result/v1"
    assert result["status"] == "private_draft"
    assert result["world_version_link_status"] == "source_only"
    assert result["chapter_count"] == 1
    assert result["warnings"][0]["code"] == "source_world_version_not_found"

    detail = client.get(f"/v1/author/works/{result['work_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["title"] == "上传闭环测试"
    assert detail.json()["chapters"][0]["body"].startswith("雾从码头压下来。")


def test_nosbook_import_from_agent_studio_export_restores_metadata_and_dedupes(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url=f"sqlite:///{tmp_path / 'round_trip.db'}")
    app = create_app(repository=repository)
    client = TestClient(app)
    source_headers = _auth_headers(client, actor_id="nosbook_source_author")
    target_headers = _auth_headers(client, actor_id="nosbook_target_author")

    draft = app.state.authoring_service.create_draft_from_brief(
        {
            "genre_preset": "urban_mystery",
            "world_title": "Nosbook Upload Export",
            "lead_name": "林澈",
            "counterpart_name": "沈知",
            "core_premise": "验证 Codex 类 agent 上传 .nosbook 的闭环。",
            "life_theme": "信任与隐瞒",
            "author_id": "nosbook_source_author",
            "account_id": "nosbook_source_author",
        }
    )
    work = app.state.author_work_service.create_work(
        world_version_id=draft["world_version_id"],
        account_id="nosbook_source_author",
    )
    repository.save_author_work_chapter(
        {
            "work_id": work["work_id"],
            "chapter_index": 1,
            "chapter_title": "第 1 章 · 雾港",
            "body": "雨线把码头切成几段。\n\n林澈听见证人在仓库后门轻敲三下。",
            "summary": "主角抵达雾港并遇到证人。",
            "choices_json": ["追查证据", "保护证人", "隐藏真相"],
            "state_snapshot_json": _state(1),
        }
    )
    app.state.author_work_service.create_branch(
        work_id=work["work_id"],
        source_chapter_index=1,
        label="路线 A：保护证人",
        choice_source="保护证人",
        steering_directive={"current_user_intent": "增强人物关系", "summary": "增强人物关系"},
    )
    export_response = client.get(
        f"/v1/author/works/{work['work_id']}/export",
        headers=source_headers,
        params={"format": "nosbook", "route": "active"},
    )
    assert export_response.status_code == 200
    nosbook_payload = export_response.json()

    first_import = client.post("/v1/author/nosbooks/import", headers=target_headers, json=nosbook_payload)
    assert first_import.status_code == 200
    first_result = first_import.json()
    assert first_result["status"] == "private_draft"
    assert first_result["world_version_link_status"] == "linked"
    assert first_result["duplicate"] is False

    stored_work = repository.get_author_work(first_result["work_id"])
    import_metadata = stored_work["diagnostics_summary_json"]["nosbook_import"]
    assert import_metadata["branch_map"]
    assert import_metadata["choice_history"][0]["selected_choice"] == "保护证人"
    assert import_metadata["quality_summary"]["重复感"] == "良好"

    chapters = repository.list_author_work_chapters(work_id=first_result["work_id"])
    assert len(chapters) == first_result["chapter_count"]
    assert chapters[0]["source_type"] == "nosbook_import"
    assert chapters[0]["choices_json"] == ["追查证据", "保护证人", "隐藏真相"]

    detail = client.get(f"/v1/author/works/{first_result['work_id']}", headers=target_headers)
    assert detail.status_code == 200
    assert detail.json()["chapters"][0]["chapter_title"] == "第 1 章 · 雾港"

    second_import = client.post("/v1/author/nosbooks/import", headers=target_headers, json=nosbook_payload)
    assert second_import.status_code == 200
    duplicate_result = second_import.json()
    assert duplicate_result["work_id"] == first_result["work_id"]
    assert duplicate_result["duplicate"] is True
    assert duplicate_result["duplicate_status"] == "existing_private_draft"


def test_upload_nosbook_cli_missing_token_fails_without_secret_leak(tmp_path: Path):
    nosbook_file = tmp_path / "work.nosbook"
    nosbook_file.write_text(json.dumps(_minimal_nosbook(), ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "NARRATIVEOS_PLATFORM_URL": "http://127.0.0.1:1"}
    env.pop("NARRATIVEOS_PLATFORM_TOKEN", None)

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "upload_nosbook.py"), "--file", str(nosbook_file)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["code"] == "missing_platform_token"
    assert "NARRATIVEOS_PLATFORM_TOKEN" in payload["message"]
    assert "Bearer" not in result.stdout


def test_upload_nosbook_cli_mock_success_outputs_platform_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    upload_module = _load_upload_module()
    nosbook_file = tmp_path / "work.nosbook"
    nosbook_file.write_text(json.dumps(_minimal_nosbook(), ensure_ascii=False), encoding="utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"schema_version":"nosbook_import_result/v1","work_id":"work_uploaded","status":"private_draft"}'

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://platform.example/v1/author/nosbooks/import"
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert timeout == 12
        return FakeResponse()

    monkeypatch.setattr(upload_module.urllib.request, "urlopen", fake_urlopen)

    result = upload_module.upload_nosbook_file(
        nosbook_file,
        platform_url="https://platform.example/",
        token="secret-token",
        timeout=12,
    )

    assert result["schema_version"] == "nosbook_import_result/v1"
    assert result["work_id"] == "work_uploaded"


def test_upload_nosbook_cli_local_work_id_exports_then_uploads_with_separate_tokens(monkeypatch: pytest.MonkeyPatch):
    upload_module = _load_upload_module()
    calls = []

    class FakeResponse:
        def __init__(self, payload: Dict[str, Any]):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.full_url.startswith("http://127.0.0.1:8000/v1/author/works/work_123/export"):
            assert request.get_method() == "GET"
            assert request.headers["Authorization"] == "Bearer local-secret"
            assert "format=nosbook" in request.full_url
            assert "route=main" in request.full_url
            assert timeout == 9
            return FakeResponse(_minimal_nosbook(world_version_id="linked_world"))
        assert request.full_url == "https://platform.example/v1/author/nosbooks/import"
        assert request.get_method() == "POST"
        assert request.headers["Authorization"] == "Bearer platform-secret"
        assert json.loads(request.data.decode("utf-8"))["schema_version"] == "nosbook/v1"
        return FakeResponse(
            {
                "schema_version": "nosbook_import_result/v1",
                "work_id": "work_uploaded_from_local",
                "status": "private_draft",
            }
        )

    monkeypatch.setattr(upload_module.urllib.request, "urlopen", fake_urlopen)

    result = upload_module.upload_nosbook_from_local_work(
        work_id="work_123",
        local_url="http://127.0.0.1:8000",
        local_token="local-secret",
        local_route="main",
        platform_url="https://platform.example",
        platform_token="platform-secret",
        timeout=9,
    )

    assert len(calls) == 2
    assert result["work_id"] == "work_uploaded_from_local"


def test_upload_nosbook_cli_local_work_id_requires_local_token_and_keeps_tokens_secret(tmp_path: Path):
    env = {
        **os.environ,
        "NARRATIVEOS_PLATFORM_URL": "https://platform.example",
        "NARRATIVEOS_PLATFORM_TOKEN": "platform-secret",
    }
    env.pop("NARRATIVEOS_LOCAL_STUDIO_TOKEN", None)

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "upload_nosbook.py"), "--local-work-id", "work_123"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["code"] == "missing_local_studio_token"
    assert "NARRATIVEOS_LOCAL_STUDIO_TOKEN" in payload["message"]
    assert "platform-secret" not in result.stdout


def test_upload_nosbook_cli_rejects_conflicting_or_missing_inputs(tmp_path: Path):
    nosbook_file = tmp_path / "work.nosbook"
    nosbook_file.write_text(json.dumps(_minimal_nosbook(), ensure_ascii=False), encoding="utf-8")
    env = {
        **os.environ,
        "NARRATIVEOS_PLATFORM_URL": "https://platform.example",
        "NARRATIVEOS_PLATFORM_TOKEN": "platform-secret",
        "NARRATIVEOS_LOCAL_STUDIO_TOKEN": "local-secret",
    }

    conflict = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "upload_nosbook.py"),
            "--file",
            str(nosbook_file),
            "--local-work-id",
            "work_123",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert conflict.returncode == 2
    assert json.loads(conflict.stdout)["code"] == "upload_input_conflict"

    missing = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "upload_nosbook.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["code"] == "upload_input_missing"


def test_upload_nosbook_cli_local_export_http_error_is_diagnostic_and_token_safe(monkeypatch: pytest.MonkeyPatch):
    upload_module = _load_upload_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":{"code":"author_work_forbidden","echo":"local-secret"}}'),
        )

    monkeypatch.setattr(upload_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(upload_module.NosbookUploadCliError) as exc_info:
        upload_module.upload_nosbook_from_local_work(
            work_id="work_123",
            local_url="http://127.0.0.1:8000",
            local_token="local-secret",
            local_route="active",
            platform_url="https://platform.example",
            platform_token="platform-secret",
            timeout=9,
        )

    payload = upload_module._error_payload(exc_info.value)
    serialized = json.dumps(payload)
    assert payload["code"] == "local_export_failed"
    assert payload["details"]["status_code"] == 403
    assert "author_work_forbidden" in serialized
    assert "local-secret" not in serialized
    assert "platform-secret" not in serialized


def test_upload_nosbook_cli_local_export_rejects_non_nosbook_payload(monkeypatch: pytest.MonkeyPatch):
    upload_module = _load_upload_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"schema_version":"nosbook/v2"}'

    monkeypatch.setattr(upload_module.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(upload_module.NosbookUploadCliError) as exc_info:
        upload_module.export_local_work_nosbook(
            work_id="work_123",
            local_url="http://127.0.0.1:8000",
            local_token="local-secret",
            route="active",
            timeout=9,
        )

    assert exc_info.value.code == "local_export_invalid_nosbook"


def test_upload_nosbook_cli_mock_platform_error_is_diagnostic_and_token_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    upload_module = _load_upload_module()
    nosbook_file = tmp_path / "work.nosbook"
    nosbook_file.write_text(json.dumps(_minimal_nosbook(), ensure_ascii=False), encoding="utf-8")

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":{"code":"malformed_nosbook","echo":"secret-token"}}'),
        )

    monkeypatch.setattr(upload_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(upload_module.NosbookUploadCliError) as exc_info:
        upload_module.upload_nosbook_file(
            nosbook_file,
            platform_url="https://platform.example",
            token="secret-token",
            timeout=12,
        )

    payload = upload_module._error_payload(exc_info.value)
    serialized = json.dumps(payload)
    assert payload["code"] == "platform_upload_failed"
    assert payload["details"]["status_code"] == 400
    assert "malformed_nosbook" in serialized
    assert "secret-token" not in serialized
