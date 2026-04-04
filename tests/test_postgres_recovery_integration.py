from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository


REQUIRED_ENV_VARS = [
    "NARRATIVEOS_POSTGRES_INTEGRATION",
    "NARRATIVEOS_POSTGRES_TEST_URL",
    "NARRATIVEOS_PG_DUMP_BIN",
    "NARRATIVEOS_PG_RESTORE_BIN",
    "NARRATIVEOS_PSQL_BIN",
]


def _integration_enabled() -> bool:
    return str(os.getenv("NARRATIVEOS_POSTGRES_INTEGRATION", "")).strip() == "1"


def _require_integration_env() -> tuple[str, Path]:
    if not _integration_enabled():
        pytest.skip("postgres integration disabled")
    missing = [key for key in REQUIRED_ENV_VARS if not str(os.getenv(key, "")).strip()]
    if missing:
        pytest.skip(f"postgres integration env missing: {','.join(missing)}")
    for tool_env in ["NARRATIVEOS_PG_DUMP_BIN", "NARRATIVEOS_PG_RESTORE_BIN", "NARRATIVEOS_PSQL_BIN"]:
        binary = str(os.getenv(tool_env, "")).strip()
        if not binary or not Path(binary).exists():
            pytest.skip(f"postgres integration binary missing: {tool_env}")
    database_url = str(os.getenv("NARRATIVEOS_POSTGRES_TEST_URL", "")).strip()
    output_dir = Path(os.getenv("NARRATIVEOS_POSTGRES_TEST_OUTPUT_DIR", "artifacts/postgres_integration"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return database_url, output_dir


@pytest.mark.integration
def test_postgres_recovery_end_to_end():
    database_url, output_dir = _require_integration_env()
    repository = SQLAlchemyRepository(database_url=database_url)
    app = create_app(repository=repository)
    client = TestClient(app)

    before_event = f"before_backup_{uuid.uuid4().hex[:8]}"
    after_event = f"after_backup_{uuid.uuid4().hex[:8]}"

    repository.record_analytics_event({"event_name": before_event})

    backup_response = client.post(
        "/v1/ops/jobs/runtime-backups",
        json={
            "label": "postgres_integration_backup",
            "output_dir": str(output_dir / "backups"),
            "requested_by": "ops_backup_admin",
        },
    )
    assert backup_response.status_code == 200
    backup_job_id = backup_response.json()["job"]["job_id"]
    if backup_response.json()["job"]["status"] != "succeeded":
        app.state.async_job_service.run_job(backup_job_id)
    backup_job = client.get(f"/v1/ops/jobs/{backup_job_id}")
    assert backup_job.status_code == 200
    assert backup_job.json()["job"]["status"] == "succeeded"
    backup_path = backup_job.json()["job"]["result_summary"]["backup_path"]
    assert backup_path
    assert Path(backup_path).exists()

    drill = client.post("/v1/ops/recovery-drill", json={"backup_path": backup_path, "output_dir": str(output_dir / "drills")})
    assert drill.status_code == 200
    assert drill.json()["recovery_drill"]["status"] in {"ready", "operator_review"}

    repository.record_analytics_event({"event_name": after_event})

    request_headers = {
        "X-NarrativeOS-Actor-Id": "ops_requester",
        "X-NarrativeOS-Actor-Role": "ops",
    }
    approve_headers = {
        "X-NarrativeOS-Actor-Id": "ops_admin",
        "X-NarrativeOS-Actor-Role": "admin",
    }
    execute_headers = {
        "X-NarrativeOS-Actor-Id": "ops_executor_admin",
        "X-NarrativeOS-Actor-Role": "admin",
    }

    requested = client.post(
        "/v1/ops/runtime-restore/request",
        headers=request_headers,
        json={"backup_path": backup_path, "reason": "postgres integration restore"},
    )
    assert requested.status_code == 200
    request_id = requested.json()["restore_request"]["request_id"]

    approved = client.post(
        f"/v1/ops/runtime-restore/{request_id}/approve",
        headers=approve_headers,
        json={"reason": "admin approved integration restore"},
    )
    assert approved.status_code == 200
    assert approved.json()["restore_request"]["approval_status"] == "approved"

    restore_job_response = client.post(
        "/v1/ops/jobs/runtime-restores",
        headers=execute_headers,
        json={"request_id": request_id},
    )
    assert restore_job_response.status_code == 200
    restore_job_id = restore_job_response.json()["job"]["job_id"]
    if restore_job_response.json()["job"]["status"] != "succeeded":
        app.state.async_job_service.run_job(restore_job_id)
    restore_job = client.get(f"/v1/ops/jobs/{restore_job_id}")
    assert restore_job.status_code == 200
    assert restore_job.json()["job"]["status"] == "succeeded"

    result_json = Path(restore_job.json()["job"]["result_summary"]["result_json"])
    assert result_json.exists()

    events = repository.list_analytics_events(limit=200)
    event_names = [item["event_name"] for item in events]
    assert before_event in event_names
    assert after_event not in event_names

    requests_payload = client.get("/v1/ops/runtime-restore-requests")
    assert requests_payload.status_code == 200
    matched = next(item for item in requests_payload.json()["restore_requests"] if item["request_id"] == request_id)
    assert matched["approval_status"] == "executed"
    assert matched["executed_by"] == "ops_executor_admin"
