from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.observability import ObservabilityService
from src.narrativeos.services.runtime_ops import RuntimeOpsService


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

    repository.record_analytics_event({"event_name": "after_backup"})
    restore = service.restore_backup(backup_path=backup["backup_path"])
    assert restore["status"] == "completed"
    assert restore["pre_restore_backup"] is not None

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
        candidate_batch={"debug": {"provider": "llm", "backend_error": "provider_down", "backend_routing": {"selected_provider": "local", "fallback_used": True}}},
        reader_view={"body": "短文本"},
        estimated_cost=0.05,
    )
    service = RuntimeOpsService(repository, observability_service=observability, base_dir=tmp_path)

    runbook = service.build_deployment_runbook()
    assert "deploy_steps" in runbook
    assert "rollback_steps" in runbook

    playbook = service.build_incident_playbook(account_id="acct_rt")
    assert playbook["incident_snapshot"]["incident_count"] >= 1
    assert playbook["triage_steps"]
    assert playbook["recovery_steps"]
    health_gate = service.build_deployment_health_gate(account_id="acct_rt")
    assert health_gate["status"] in {"pass", "warn", "block"}
    assert health_gate["checks"]
    bundle = service.build_preflight_verification_bundle(account_id="acct_rt")
    assert bundle["verification_summary"]["gate_status"] == health_gate["status"]
    assert bundle["verification_commands"]


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

    restore = client.post("/v1/ops/runtime-restore", json={"backup_path": backup_path, "dry_run": True})
    assert restore.status_code == 200
    assert restore.json()["restore"]["status"] == "planned"
