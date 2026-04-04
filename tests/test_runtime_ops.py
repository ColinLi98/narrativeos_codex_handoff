from pathlib import Path
import gzip

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.observability import ObservabilityService
from src.narrativeos.services.runtime_ops import RuntimeOpsService


def _mock_postgres_runtime(service: RuntimeOpsService, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(service, "_backend", lambda: "postgresql")
    monkeypatch.setattr(service, "_database_url", lambda: "postgresql://operator:secret@db.example:5432/narrativeos")

    def fake_resolve_binary_map(tools):
        return {
            tool: {
                "tool": tool,
                "env_var": f"NARRATIVEOS_{tool.upper()}_BIN",
                "requested_path": None,
                "resolved_path": f"/usr/local/bin/{tool}",
                "available": True,
                "version": f"{tool} 16.2",
            }
            for tool in tools
        }

    def fake_run_subprocess(command, *, input_text=None):
        executable = Path(command[0]).name
        if executable == "pg_dump":
            output_path = Path(command[3])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("pg_dump content", encoding="utf-8")
            return {"exit_code": 0, "stdout": "backup ok\n", "stderr": ""}
        if executable in {"pg_restore", "psql"}:
            return {"exit_code": 0, "stdout": "restore ok\n", "stderr": ""}
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(service, "_resolve_binary_map", fake_resolve_binary_map)
    monkeypatch.setattr(service, "_run_subprocess", fake_run_subprocess)


def test_runtime_ops_can_backup_and_restore_sqlite_database(tmp_path: Path):
    db_path = tmp_path / "runtime_ops.db"
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % db_path)
    repository.record_analytics_event({"event_name": "before_backup"})
    service = RuntimeOpsService(
        repository,
        observability_service=ObservabilityService(repository),
        base_dir=tmp_path,
    )

    backup = service.create_backup(label="test_backup", output_dir=str(tmp_path / "backups"))
    assert backup["status"] == "completed"
    assert Path(backup["backup_path"]).exists()
    assert "verification_snapshot" in backup
    assert "table_counts" in backup["verification_snapshot"]

    repository.record_analytics_event({"event_name": "after_backup"})
    restore = service.restore_backup(backup_path=backup["backup_path"])
    assert restore["status"] == "completed"
    assert restore["pre_restore_backup"] is not None
    assert restore["restore_decision"] in {"ready_to_restore", "restore_with_caution", "manual_review_required"}
    assert restore["pre_restore_verification"]["table_counts"]["analytics_events"] >= 2
    assert restore["post_restore_verification"] is not None
    assert restore["verification_status"] == "matched"

    restored_repository = SQLAlchemyRepository(database_url="sqlite:///%s" % db_path)
    events = restored_repository.list_analytics_events(limit=10)
    event_names = [item["event_name"] for item in events]
    assert "before_backup" in event_names
    assert "after_backup" not in event_names


def test_runtime_ops_builds_runbook_and_incident_playbook(tmp_path: Path):
    db_path = tmp_path / "runtime_ops_playbook.db"
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % db_path)
    observability = ObservabilityService(repository)
    observability.record_runtime_receipt(
        surface="reader",
        action="continue_story",
        response_status="ok",
        world_id="jade_court_exam",
        world_version_id="jade_court_exam@1.0.0",
        session_id="session_rt_1",
        account_id="acct_rt",
        reader_id="acct_rt",
        candidate_batch={"debug": {"provider": "llm", "backend_error": "provider_down", "backend_routing": {"selected_provider": "local", "fallback_used": True, "latency_ms": 44.0, "attempt_count": 2}}},
        rendered_scene={"debug": {"backend_routing": {"selected_provider": "template", "latency_ms": 9.0}}},
        reader_view={"body": "短文本"},
        estimated_cost=0.05,
        runtime_latency_ms=61.0,
    )
    service = RuntimeOpsService(repository, observability_service=observability, base_dir=tmp_path)

    runbook = service.build_deployment_runbook()
    assert "deploy_steps" in runbook
    assert "rollback_steps" in runbook
    assert "restore_verification_steps" in runbook
    assert "restore_decision_hints" in runbook

    playbook = service.build_incident_playbook(account_id="acct_rt")
    assert playbook["incident_snapshot"]["incident_count"] >= 1
    assert playbook["triage_steps"]
    assert playbook["recovery_steps"]
    assert playbook["restore_verification_steps"]
    health_gate = service.build_deployment_health_gate(account_id="acct_rt")
    assert health_gate["status"] in {"pass", "warn", "block"}
    assert health_gate["checks"]
    assert "restore_decision_hints" in health_gate
    bundle = service.build_preflight_verification_bundle(account_id="acct_rt")
    assert bundle["verification_summary"]["gate_status"] == health_gate["status"]
    assert bundle["verification_commands"]
    assert bundle["restore_verification_steps"]
    assert health_gate["incident_snapshot"]["latency_summary"]["runtime"]["avg_latency_ms"] is not None

    backup_for_drill = service.create_backup(label="pre_drill_backup", output_dir=str(tmp_path / "backups"))
    drill = service.run_recovery_drill(backup_path=backup_for_drill["backup_path"], output_dir=str(tmp_path / "drills"))
    assert drill["status"] in {"ready", "operator_review"}
    assert Path(drill["artifact_path"]).exists()
    assert drill["restore_plan"]["status"] == "planned"


def test_postgres_backup_restore_contract_and_request_flow(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "runtime_ops_postgres.db"
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % db_path)
    service = RuntimeOpsService(repository, observability_service=ObservabilityService(repository), base_dir=tmp_path)
    _mock_postgres_runtime(service, tmp_path, monkeypatch)

    blocked_service = RuntimeOpsService(repository, observability_service=ObservabilityService(repository), base_dir=tmp_path)
    monkeypatch.setattr(blocked_service, "_backend", lambda: "postgresql")
    monkeypatch.setattr(blocked_service, "_database_url", lambda: "postgresql://operator:secret@db.example:5432/narrativeos")
    monkeypatch.setattr(
        blocked_service,
        "_resolve_binary_map",
        lambda tools: {
            tool: {
                "tool": tool,
                "env_var": f"NARRATIVEOS_{tool.upper()}_BIN",
                "requested_path": None,
                "resolved_path": None,
                "available": False,
                "version": None,
            }
            for tool in tools
        },
    )
    blocked_backup = blocked_service.create_backup(label="blocked_backup", output_dir=str(tmp_path / "blocked_backups"))
    assert blocked_backup["status"] == "blocked"
    assert blocked_backup["blocked_reason"] == "postgres_backup_binary_missing:pg_dump"

    backup = service.create_backup(
        label="postgres_backup",
        output_dir=str(tmp_path / "postgres_backups"),
        execute_postgres=True,
        job_id="job_pg_backup",
    )
    assert backup["status"] == "completed"
    assert backup["backup_format"] == "custom"
    assert backup["backup_tool"] == "pg_dump"
    assert backup["_job_status_override"] == "succeeded"
    assert Path(backup["backup_path"]).exists()
    assert Path(backup["artifacts"]["result_json"]).exists()

    sql_gz_path = tmp_path / "import.sql.gz"
    with gzip.open(sql_gz_path, "wt", encoding="utf-8") as handle:
        handle.write("select 1;\n")
    sql_gz_plan = service.restore_backup(backup_path=str(sql_gz_path), dry_run=True)
    assert sql_gz_plan["required_restore_tool"] == "psql"
    assert sql_gz_plan["backup_format"] == "sql_gzip"

    restore_request = service.request_restore(
        backup_path=backup["backup_path"],
        requested_by="ops_requester",
        reason="nightly validation restore",
    )
    assert restore_request["approval_status"] == "unapproved"
    assert restore_request["backup_format"] == "custom"

    try:
        service.approve_restore_request(
            request_id=restore_request["request_id"],
            approver_id="ops_requester",
            reason="self approve should fail",
        )
        raise AssertionError("self approval should fail")
    except ValueError as exc:
        assert str(exc) == "restore_request_self_approval_forbidden"

    approved = service.approve_restore_request(
        request_id=restore_request["request_id"],
        approver_id="ops_approver",
        reason="approved for controlled restore",
    )
    assert approved["approval_status"] == "approved"

    executed = service.execute_restore_request(
        request_id=restore_request["request_id"],
        job_id="job_pg_restore",
        requested_by="ops_executor",
    )
    assert executed["_job_status_override"] == "succeeded"
    assert executed["status"] == "completed"
    assert Path(executed["artifacts"]["result_json"]).exists()

    tampered_path = Path(backup["backup_path"])
    tampered_path.write_text("tampered dump", encoding="utf-8")
    second_request = service.request_restore(
        backup_path=backup["backup_path"],
        requested_by="ops_requester_2",
        reason="tamper test",
    )
    service.approve_restore_request(
        request_id=second_request["request_id"],
        approver_id="ops_approver_2",
        reason="approve tamper test",
    )
    tampered_path.write_text("tampered again", encoding="utf-8")
    try:
        service.execute_restore_request(
            request_id=second_request["request_id"],
            job_id="job_pg_restore_tampered",
            requested_by="ops_executor",
        )
        raise AssertionError("fingerprint mismatch should fail")
    except PermissionError as exc:
        assert str(exc) == "restore_request_backup_fingerprint_mismatch"


def test_runtime_ops_endpoints_return_runbook_backup_and_playbook(tmp_path: Path):
    db_path = tmp_path / "runtime_ops_api.db"
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % db_path))
    client = TestClient(app)

    runbook = client.get("/v1/ops/deployment-runbook")
    assert runbook.status_code == 200
    assert "deploy_steps" in runbook.json()
    assert "recent_backups" in runbook.json()
    gate = client.get("/v1/ops/deployment-health-gate")
    assert gate.status_code == 200
    assert "checks" in gate.json()
    bundle = client.get("/v1/ops/preflight-verification-bundle")
    assert bundle.status_code == 200
    assert "verification_commands" in bundle.json()

    backup = client.post(
        "/v1/ops/runtime-backups",
        json={"label": "api_backup", "output_dir": str(tmp_path / "api_backups")},
    )
    assert backup.status_code == 200
    backup_path = backup.json()["backup"]["backup_path"]
    assert Path(backup_path).exists()

    playbook = client.get("/v1/ops/incident-playbook")
    assert playbook.status_code == 200
    assert "triage_steps" in playbook.json()
    assert "restore_verification_steps" in playbook.json()

    drills = client.get("/v1/ops/recovery-drills")
    assert drills.status_code == 200
    assert "recovery_drills" in drills.json()

    drill = client.post("/v1/ops/recovery-drill", json={"backup_path": backup_path})
    assert drill.status_code == 200
    assert "recovery_drill" in drill.json()
    assert drill.json()["recovery_drill"]["restore_plan"]["status"] == "planned"

    restore = client.post("/v1/ops/runtime-restore", json={"backup_path": backup_path, "dry_run": True})
    assert restore.status_code == 200
    assert restore.json()["restore"]["status"] == "planned"
    assert "restore_decision" in restore.json()["restore"]


def test_postgres_restore_request_endpoints_and_jobs(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "runtime_ops_postgres_api.db"
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % db_path))
    client = TestClient(app)
    _mock_postgres_runtime(app.state.runtime_ops_service, tmp_path, monkeypatch)

    backup = app.state.runtime_ops_service.create_backup(
        label="api_pg_backup",
        output_dir=str(tmp_path / "api_pg_backups"),
        execute_postgres=True,
        job_id="job_api_pg_backup",
    )
    assert backup["status"] == "completed"

    requested = client.post(
        "/v1/ops/runtime-restore/request",
        headers={
            "X-NarrativeOS-Actor-Id": "ops_requester",
            "X-NarrativeOS-Actor-Role": "ops",
        },
        json={
            "backup_path": backup["backup_path"],
            "reason": "api request restore",
        },
    )
    assert requested.status_code == 200
    request_id = requested.json()["restore_request"]["request_id"]

    listed = client.get("/v1/ops/runtime-restore-requests")
    assert listed.status_code == 200
    assert any(item["request_id"] == request_id for item in listed.json()["restore_requests"])

    approved = client.post(
        f"/v1/ops/runtime-restore/{request_id}/approve",
        headers={
            "X-NarrativeOS-Actor-Id": "ops_admin",
            "X-NarrativeOS-Actor-Role": "admin",
        },
        json={"approver_id": "ops_approver", "reason": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["restore_request"]["approval_status"] == "approved"

    job_response = client.post(
        "/v1/ops/jobs/runtime-restores",
        headers={
            "X-NarrativeOS-Actor-Id": "ops_executor_admin",
            "X-NarrativeOS-Actor-Role": "admin",
        },
        json={"request_id": request_id, "requested_by": "ops_executor"},
    )
    assert job_response.status_code == 200
    job_id = job_response.json()["job"]["job_id"]
    if job_response.json()["job"]["status"] != "succeeded":
        app.state.async_job_service.run_job(job_id)
    job_detail = client.get(f"/v1/ops/jobs/{job_id}")
    assert job_detail.status_code == 200
    assert job_detail.json()["job"]["job_type"] == "runtime_restore"
    assert job_detail.json()["job"]["status"] == "succeeded"

    second_request = client.post(
        "/v1/ops/runtime-restore/request",
        headers={
            "X-NarrativeOS-Actor-Id": "ops_requester_2",
            "X-NarrativeOS-Actor-Role": "ops",
        },
        json={
            "backup_path": backup["backup_path"],
            "reason": "revoke path",
        },
    )
    second_request_id = second_request.json()["restore_request"]["request_id"]
    revoked = client.post(
        f"/v1/ops/runtime-restore/{second_request_id}/revoke",
        headers={
            "X-NarrativeOS-Actor-Id": "ops_admin_2",
            "X-NarrativeOS-Actor-Role": "admin",
        },
        json={"reviewer_id": "ops_approver", "reason": "do not run"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["restore_request"]["approval_status"] == "revoked"
