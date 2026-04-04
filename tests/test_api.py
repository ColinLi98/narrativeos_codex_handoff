from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from tests.conftest import load_example


def test_world_session_step_and_replay_flow(tmp_path: Path):
    database_url = "sqlite:///%s" % (tmp_path / "narrativeos.db")
    app = create_app(repository=SQLAlchemyRepository(database_url=database_url))
    client = TestClient(app)

    world_payload = {
        "world_bible": load_example("demo_world_bible.json"),
        "event_atoms": load_example("demo_event_atoms.json"),
        "metadata": {"source": "test"},
    }
    world_response = client.post("/v1/worlds", json=world_payload)
    assert world_response.status_code == 200
    world_id = world_response.json()["world_id"]

    session_response = client.post(
        "/v1/sessions",
        json={
            "world_id": world_id,
            "initial_state": load_example("demo_initial_state.json"),
            "player_profile": {"tier": "free"},
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]
    assert session_response.json()["world_version_id"]
    assert "paywall" in session_response.json()

    step_response = client.post(
        "/v1/sessions/%s/step" % session_id,
        json={"player_input": "我先顺着家里来，但我也想给自己留后路。"},
    )
    assert step_response.status_code == 200
    step_payload = step_response.json()
    assert step_payload["reader_view"]
    assert "event_id" not in step_payload["reader_view"]["body"]
    assert step_payload["updated_state_summary"]["chapter_index"] == 1
    assert step_payload["replay_preview"]["latest_title"]
    assert step_payload["world_version_id"]
    assert "paywall" in step_payload

    debug_session_response = client.post(
        "/v1/sessions",
        json={
            "world_id": world_id,
            "initial_state": load_example("demo_initial_state.json"),
            "player_profile": {"tier": "debug"},
        },
    )
    assert debug_session_response.status_code == 200
    debug_session_id = debug_session_response.json()["session_id"]
    debug_step_response = client.post(
        "/v1/sessions/%s/step?debug=true" % debug_session_id,
        json={"player_input": "我先顺着家里来，但我也想给自己留后路。"},
    )
    assert debug_step_response.status_code == 200
    debug_step_payload = debug_step_response.json()
    assert debug_step_payload["chosen_event"]
    assert debug_step_payload["updated_state"]["chapter_index"] >= 1
    assert debug_step_payload["rendered_scene"]["concise_summary"]
    assert debug_step_payload["candidate_batch"]["raw_candidates"]

    replay_response = client.get("/v1/sessions/%s/replay" % session_id)
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert len(replay_payload["event_trace"]) == 1
    assert len(replay_payload["state_snapshots"]) == 2
    assert replay_payload["rendered_scenes"]
    assert replay_payload["reader_views"]

    sessions_response = client.get("/v1/sessions", params={"world_id": world_id})
    assert sessions_response.status_code == 200
    sessions_payload = sessions_response.json()
    assert sessions_payload["sessions"]
    session_ids = {item["session_id"] for item in sessions_payload["sessions"]}
    assert session_id in session_ids
    assert debug_session_id in session_ids

    session_detail = client.get(f"/v1/sessions/{session_id}")
    assert session_detail.status_code == 200
    detail_payload = session_detail.json()
    assert detail_payload["session"]["session_id"] == session_id
    assert detail_payload["latest_step"]["reader_view"]["chapter_title"]
    assert detail_payload["world_version_id"]

    delete_response = client.delete(f"/v1/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["session_id"] == session_id

    missing_after_delete = client.get(f"/v1/sessions/{session_id}")
    assert missing_after_delete.status_code == 404


def test_route_preview_uses_explicit_world_and_candidates(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "preview.db")))
    client = TestClient(app)

    response = client.post(
        "/v1/routes/preview",
        json={
            "world": load_example("demo_world_bible.json"),
            "state": load_example("demo_initial_state.json"),
            "candidate_events": load_example("demo_event_atoms.json"),
            "beam_width": 2,
            "depth": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["routes"]
    assert payload["scored_candidates"]


def test_frontend_shell_and_demo_bundle_are_served(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "frontend.db")))
    client = TestClient(app)

    root = client.get("/", follow_redirects=False)
    assert root.status_code in (307, 308)
    assert root.headers["location"] == "/app"

    app_page = client.get("/app")
    assert app_page.status_code == 200
    assert "NarrativeOS Studio" in app_page.text
    assert "/assets/app.js" in app_page.text
    assert "图文画卷" in app_page.text
    assert "幕后解析" in app_page.text
    assert "Author" in app_page.text
    assert "Ops" in app_page.text
    assert "下一步心意" in app_page.text
    assert "Story Feed" in app_page.text
    assert "推荐起笔句" in app_page.text

    styles = client.get("/assets/styles.css")
    assert styles.status_code == 200
    assert "--accent" in styles.text

    script = client.get("/assets/app.js")
    assert script.status_code == 200
    assert "bootstrapWorld" in script.text

    demo = client.get("/v1/examples/demo")
    assert demo.status_code == 200
    payload = demo.json()
    assert payload["world_bible"]["world_id"] == "jade_court_exam"
    assert payload["player_inputs"]

    examples = client.get("/v1/examples")
    assert examples.status_code == 200
    example_payload = examples.json()
    example_ids = [item["example_id"] for item in example_payload["examples"]]
    assert "demo" in example_ids
    assert "romance" in example_ids

    romance = client.get("/v1/examples/romance")
    assert romance.status_code == 200
    romance_payload = romance.json()
    assert romance_payload["world_bible"]["world_id"] == "jade_court_romance"
