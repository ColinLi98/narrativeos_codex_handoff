from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from src.narrativeos.services.async_job_adapters import (
    NotificationSinkRegistry,
    RemoteShippingConfigRegistry,
    NoopNotificationSinkAdapter,
    NoopRemoteShippingAdapter,
)
from src.narrativeos.services.async_jobs import AsyncJobService


def test_async_job_service_persists_and_runs_jobs(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs.db"))
    analytics = AnalyticsService(repository)
    service = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    service.register_runner(
        "runtime_backup",
        lambda job: {
            "backup_id": "backup_fake",
            "status": "completed",
            "backup_path": str(tmp_path / "backup.sqlite3"),
            "created_at": "2026-04-02T12:00:00+00:00",
            "backend": "sqlite",
            "schema_lifecycle_status": "up_to_date",
            "dry_run": False,
        },
    )

    queued = service.enqueue_job(
        job_type="runtime_backup",
        payload={"label": "nightly"},
        requested_by="ops_test",
    )
    assert queued["status"] == "queued"
    assert queued["workflow"]["steps"][0]["status"] == "queued"

    completed = service.run_job(queued["job_id"])
    assert completed["status"] == "succeeded"
    assert completed["result_summary"]["backup_id"] == "backup_fake"

    listed = service.list_jobs(job_type="runtime_backup")
    assert listed[0]["job_id"] == queued["job_id"]
    assert listed[0]["result_summary"]["status"] == "completed"

    events = repository.list_analytics_events(
        event_names=["async_job_enqueued", "async_job_started", "async_job_succeeded"],
        limit=10,
    )
    assert [item["event_name"] for item in events].count("async_job_succeeded") == 1
    assert completed["lease_status"] == "released"
    assert completed["heartbeat_count"] >= 1


def test_async_job_heartbeat_and_boot_reconcile(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_heartbeat.db"))
    analytics = AnalyticsService(repository)
    service = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    service.register_runner("runtime_backup", lambda job: {"status": "completed"})

    started_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    running_job = service.enqueue_job(job_type="runtime_backup", payload={"label": "heartbeat"})
    running_job = service._save_job(
        {
            **running_job,
            "status": "running",
            "started_at": started_at,
            "lease_owner": "worker_a",
            "lease_acquired_at": started_at,
            "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            "lease_timeout_minutes": 15,
            "heartbeat_at": started_at,
            "heartbeat_count": 1,
        }
    )
    heartbeat = service.heartbeat_job(running_job["job_id"], requested_by="worker_a", lease_timeout_minutes=20)
    assert heartbeat["heartbeat_count"] == 2
    assert heartbeat["lease_status"] == "active"
    assert heartbeat["lease_owner"] == "worker_a"

    boot_summary = service.reconcile_on_boot(requested_by="boot_test")
    assert boot_summary["reconciled_count"] == 1
    reconciled = service.get_job(running_job["job_id"])
    assert reconciled["status"] == "queued"
    assert reconciled["lease_status"] == "released"
    assert reconciled["recovery_history"][0]["action"] == "boot_reconciled_orphaned_running_job"


def test_async_job_artifact_retention_and_operator_history(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_artifacts.db"))
    analytics = AnalyticsService(repository)
    service = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    summary_path = tmp_path / "learned_summary.json"
    backup_path = tmp_path / "runtime_backup.sqlite3"
    summary_path.write_text("{}", encoding="utf-8")
    backup_path.write_text("sqlite", encoding="utf-8")
    service.register_runner("learned_training", lambda job: {"status": "completed"})
    service.register_runner("runtime_backup", lambda job: {"status": "completed"})

    learned_job = service.enqueue_job(
        job_type="learned_training",
        payload={"tracks": ["evaluator"]},
        requested_by="ops_learned",
    )
    learned_job = service._save_job(
        {
            **learned_job,
            "status": "succeeded",
            "requested_by": "ops_learned",
            "result_summary": {
                "run_id": "run_retention",
                "tracks_requested": ["evaluator"],
                "tracks_succeeded": ["evaluator"],
                "tracks_failed": [],
                "summary_artifact": str(summary_path),
                "evidence_paths": {"evaluator": str(tmp_path / "missing_evidence.json")},
            },
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    backup_job = service.enqueue_job(
        job_type="runtime_backup",
        payload={"label": "nightly"},
        requested_by="ops_backup",
    )
    backup_job = service._save_job(
        {
            **backup_job,
            "status": "succeeded",
            "requested_by": "ops_backup",
            "result_summary": {
                "backup_id": "backup_keep",
                "backup_path": str(backup_path),
                "status": "completed",
                "backend": "sqlite",
            },
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "recovery_history": [
                {
                    "action": "retry_failed_job",
                    "requested_by": "ops_backup",
                    "reason": "manual_retry",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
    )

    retention = service.artifact_retention_snapshot(limit=10)
    assert retention["jobs_with_artifacts"] >= 2
    assert retention["total_artifact_count"] >= 2
    assert retention["by_status"]["retained"] >= 1 or retention["by_status"]["missing"] >= 1
    learned_retention = next(item for item in retention["artifact_jobs"] if item["job_id"] == learned_job["job_id"])
    assert learned_retention["missing_count"] >= 1

    history = service.operator_run_history(limit=20)
    assert history["operator_count"] >= 2
    assert history["by_action"]["enqueue_job"] >= 2
    assert any(item["action"] == "retry_failed_job" for item in history["latest_entries"])

    handoff = service.build_handoff_bundle(requested_by="ops_handoff", limit=10)
    assert "jobs_requiring_handoff" in handoff
    assert handoff["notification_sinks"]["default_sink"] == "file"
    exported = service.export_handoff_bundle(requested_by="ops_handoff", limit=10, output_dir=str(tmp_path / "handoffs"))
    assert Path(exported["export_path"]).exists()
    assert exported["notification_receipt"]["sink_name"] == "file"
    acknowledged = service.acknowledge_job(learned_job["job_id"], requested_by="ops_ack", note="night shift accepted")
    assert acknowledged["acknowledged_by"] == "ops_ack"

    shipped = service.ship_remote_artifacts(
        backup_job["job_id"],
        requested_by="ops_ship",
        remote_dir=str(tmp_path / "remote_shipments"),
        dry_run=False,
    )
    assert shipped["shipped_item_count"] >= 1
    assert Path(shipped["remote_manifest_path"]).exists()
    remote_snapshot = service.remote_shipping_snapshot(limit=10)
    assert remote_snapshot["jobs_with_remote_shipping"] >= 1
    assert remote_snapshot["registry"]["default_adapter"] == "local_mirror"

    overdue_job = service.enqueue_job(
        job_type="runtime_backup",
        payload={"label": "handoff_overdue"},
        requested_by="ops_overdue",
    )
    overdue_job = service._save_job(
        {
            **overdue_job,
            "status": "failed",
            "finished_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
        }
    )
    sla_snapshot = service.handoff_sla_snapshot(limit=20, sla_minutes=60)
    assert sla_snapshot["overdue_count"] >= 1
    escalated = service.escalate_handoff_sla(requested_by="ops_sla", sla_minutes=60, limit=20, dry_run=False)
    assert escalated["escalated_count"] >= 1

    history = service.operator_run_history(limit=50)
    assert any(item["action"] == "acknowledge_job" for item in history["latest_entries"])
    assert any(item["action"] == "async_job_handoff_bundle_exported" for item in history["latest_entries"])
    assert any(item["action"] == "async_job_remote_shipping_applied" for item in history["latest_entries"])
    assert any(item["action"] == "async_job_handoff_sla_escalated" for item in history["latest_entries"])


def test_async_job_service_uses_adapter_boundaries(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_adapters.db"))
    analytics = AnalyticsService(repository)
    remote_registry = RemoteShippingConfigRegistry(default_adapter="noop")
    remote_registry.register(NoopRemoteShippingAdapter())
    sink_registry = NotificationSinkRegistry(default_sink="noop")
    sink_registry.register(NoopNotificationSinkAdapter())
    service = AsyncJobService(
        repository,
        analytics_service=analytics,
        base_dir=tmp_path,
        remote_shipping_registry=remote_registry,
        notification_sink_registry=sink_registry,
    )
    service.register_runner("runtime_backup", lambda job: {"status": "completed"})
    artifact_path = tmp_path / "adapter_artifact.json"
    artifact_path.write_text("{}", encoding="utf-8")
    job = service.enqueue_job(job_type="runtime_backup", payload={"label": "adapter_case"}, requested_by="ops_adapter")
    job = service._save_job(
        {
            **job,
            "status": "succeeded",
            "result_summary": {
                "backup_id": "backup_adapter",
                "backup_path": str(artifact_path),
                "status": "completed",
                "backend": "sqlite",
            },
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    shipped = service.ship_remote_artifacts(job["job_id"], requested_by="ops_adapter", adapter_name="noop", dry_run=True)
    assert shipped["adapter_name"] == "noop"
    exported = service.export_handoff_bundle(requested_by="ops_adapter", sink_name="noop", dry_run_notification=True)
    assert exported["notification_receipt"]["sink_name"] == "noop"
    escalated = service.escalate_handoff_sla(requested_by="ops_adapter", sink_name="noop", dry_run=True, sla_minutes=1)
    assert escalated["notification_receipt"]["sink_name"] == "noop"
    validation = service.adapter_config_validation()
    assert validation["valid"] is True
    policies = service.retry_policy_summary()
    assert policies["default_policy_id"] == "notification:default"
    receipts = service.notification_delivery_receipts(limit=20)
    assert receipts["receipt_count"] >= 2
    receipt_id = receipts["latest_receipts"][0]["event_id"]
    detail = service.notification_delivery_receipt_detail(receipt_id)
    assert detail["receipt"]["event_id"] == receipt_id
    assert "target_payload_preview" in detail
    probe = service.adapter_health_probe()
    assert probe["status"] == "pass"
    assert probe["remote_shipping"]["default_probe"]["status"] == "pass"

    retry = service.enqueue_notification_retry(receipt_id, requested_by="ops_retry", note="retry this notification")
    assert retry["status"] == "queued"
    queue = service.list_notification_retry_queue(limit=10)
    assert queue["retry_count"] >= 1
    processed = service.process_notification_retry(retry["retry_id"], requested_by="ops_retry", dry_run=True)
    assert processed["status"] == "planned"
    queue = service.list_notification_retry_queue(limit=10)
    assert queue["retries"][0]["status"] in {"planned", "queued", "succeeded"}

    failed_retry = service.enqueue_notification_retry(receipt_id, requested_by="ops_retry", note="force classify")
    classified = service.process_notification_retry(
        failed_retry["retry_id"],
        requested_by="ops_retry",
        sink_name="missing_sink",
        dry_run=False,
    )
    assert classified["status"] == "failed"
    assert classified["failure_classification"]["failure_class"] == "configuration"
    assert classified["retry_decision"] == "terminal_failure"
    dead_letters = service.list_notification_dead_letter_queue(limit=10)
    assert dead_letters["dead_letter_count"] >= 1
    dashboard = service.notification_retry_outcome_dashboard(limit=10)
    assert dashboard["terminal_failure_count"] >= 1
    assert "configuration" in dashboard["by_failure_class"]


def test_async_job_config_validation_can_flag_invalid_defaults(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_invalid_registry.db"))
    analytics = AnalyticsService(repository)
    remote_registry = RemoteShippingConfigRegistry(default_adapter="missing_remote")
    remote_registry.register(NoopRemoteShippingAdapter())
    sink_registry = NotificationSinkRegistry(default_sink="missing_sink")
    sink_registry.register(NoopNotificationSinkAdapter())
    service = AsyncJobService(
        repository,
        analytics_service=analytics,
        base_dir=tmp_path,
        remote_shipping_registry=remote_registry,
        notification_sink_registry=sink_registry,
    )
    validation = service.adapter_config_validation()
    assert validation["valid"] is False
    assert validation["remote_shipping"]["valid"] is False
    assert validation["notification_sinks"]["valid"] is False
    assert any("default_adapter_not_registered" in (item.get("issues") or []) for item in validation["remote_shipping"]["checks"])
    assert any("default_sink_not_registered" in (item.get("issues") or []) for item in validation["notification_sinks"]["checks"])


def test_async_job_service_retry_resume_and_recovery(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_recovery.db"))
    analytics = AnalyticsService(repository)
    service = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    state = {"attempts": 0}

    def flaky_runner(job):
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise RuntimeError("transient_failure")
        return {
            "backup_id": "backup_retry",
            "status": "completed",
            "backup_path": str(tmp_path / "backup_retry.sqlite3"),
            "created_at": "2026-04-02T12:00:00+00:00",
            "backend": "sqlite",
            "schema_lifecycle_status": "up_to_date",
            "dry_run": False,
        }

    service.register_runner("runtime_backup", flaky_runner)

    failed = service.enqueue_job(job_type="runtime_backup", payload={"label": "retry_me"})
    failed = service.run_job(failed["job_id"])
    assert failed["status"] == "failed"
    assert failed["last_error"] == "transient_failure"

    retried = service.retry_job(failed["job_id"])
    assert retried["status"] == "queued"
    retried = service.run_job(retried["job_id"])
    assert retried["status"] == "succeeded"
    assert retried["recovery_count"] >= 1
    assert retried["recovery_history"][0]["action"] == "retry_failed_job"

    queued = service.enqueue_job(job_type="runtime_backup", payload={"label": "resume_me"})
    resumed = service.resume_job(queued["job_id"])
    assert resumed["status"] == "queued"
    resumed = service.run_job(resumed["job_id"])
    assert resumed["status"] == "succeeded"

    stale_started_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    stale_running = service.enqueue_job(job_type="runtime_backup", payload={"label": "stale_running"})
    stale_running = service._save_job(
        {
            **stale_running,
            "status": "running",
            "started_at": stale_started_at,
            "heartbeat_at": stale_started_at,
            "lease_expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "lease_owner": "worker_old",
        }
    )
    snapshot = service.incident_snapshot(stale_after_minutes=15)
    assert snapshot["stale_running_count"] >= 1
    recovered = service.recover_incidents(stale_after_minutes=15, limit=5)
    assert recovered["recovered_count"] >= 1


def test_async_job_endpoints_enqueue_and_report_status(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_api.db"))
    app = create_app(repository=repository)
    app.state.async_job_service.register_runner(
        "learned_training",
        lambda job: {
            "summary": {
                "run_id": "run_fake",
                "tracks_requested": list(job.get("payload", {}).get("tracks") or []),
                "tracks_succeeded": list(job.get("payload", {}).get("tracks") or []),
                "tracks_failed": [],
                "output_dir": str(tmp_path / "learned_output"),
            },
            "artifacts": {
                "summary": str(tmp_path / "learned_output" / "summary.json"),
            },
            "evidence_results": {},
        },
    )
    client = TestClient(app)

    backup_response = client.post(
        "/v1/ops/jobs/runtime-backups",
        json={"label": "api_async_backup", "output_dir": str(tmp_path / "backups")},
    )
    assert backup_response.status_code == 200
    backup_job = backup_response.json()["job"]
    if backup_job["status"] != "succeeded":
        app.state.async_job_service.run_job(backup_job["job_id"])
    backup_detail = client.get(f"/v1/ops/jobs/{backup_job['job_id']}")
    assert backup_detail.status_code == 200
    assert backup_detail.json()["job"]["job_type"] == "runtime_backup"
    assert backup_detail.json()["job"]["status"] == "succeeded"
    assert Path(backup_detail.json()["job"]["result_summary"]["backup_path"]).exists()

    learned_response = client.post(
        "/v1/ops/jobs/learned-training",
        json={"tracks": ["evaluator"], "requested_by": "ops_async"},
    )
    assert learned_response.status_code == 200
    learned_job = learned_response.json()["job"]
    if learned_job["status"] != "succeeded":
        app.state.async_job_service.run_job(learned_job["job_id"])
    learned_detail = client.get(f"/v1/ops/jobs/{learned_job['job_id']}")
    assert learned_detail.status_code == 200
    assert learned_detail.json()["job"]["status"] == "succeeded"
    assert learned_detail.json()["job"]["result_summary"]["tracks_succeeded"] == ["evaluator"]

    jobs = client.get("/v1/ops/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["summary"]["job_count"] >= 2
    assert "runtime_backup" in jobs.json()["summary"]["supported_job_types"]
    assert "learned_training" in jobs.json()["summary"]["supported_job_types"]

    incidents = client.get("/v1/ops/jobs/incidents")
    assert incidents.status_code == 200
    assert "recommended_action" in incidents.json()
    boot = client.get("/v1/ops/jobs/boot-reconcile")
    assert boot.status_code == 200
    assert "reconciled_count" in boot.json()
    retention = client.get("/v1/ops/jobs/artifact-retention")
    assert retention.status_code == 200
    assert "by_status" in retention.json()
    operator_history = client.get("/v1/ops/jobs/operator-history")
    assert operator_history.status_code == 200
    assert "by_operator" in operator_history.json()
    handoff = client.get("/v1/ops/jobs/handoff-bundle")
    assert handoff.status_code == 200
    assert "acknowledgement_summary" in handoff.json()
    remote_shipping = client.get("/v1/ops/jobs/remote-shipping")
    assert remote_shipping.status_code == 200
    assert "by_status" in remote_shipping.json()
    assert "registry" in remote_shipping.json()
    handoff_sla = client.get("/v1/ops/jobs/handoff-sla")
    assert handoff_sla.status_code == 200
    assert "recommended_action" in handoff_sla.json()
    notification_sinks = client.get("/v1/ops/jobs/notification-sinks")
    assert notification_sinks.status_code == 200
    assert "default_sink" in notification_sinks.json()
    adapter_validation = client.get("/v1/ops/jobs/adapter-config-validation")
    assert adapter_validation.status_code == 200
    assert "remote_shipping" in adapter_validation.json()
    exported = client.post(
        "/v1/ops/jobs/handoff-bundle/export",
        json={"requested_by": "ops_export", "limit": 10, "output_dir": str(tmp_path / "handoffs")},
    )
    assert exported.status_code == 200
    assert Path(exported.json()["export_path"]).exists()
    notification_receipts = client.get("/v1/ops/jobs/notification-delivery-receipts")
    assert notification_receipts.status_code == 200
    assert "receipt_count" in notification_receipts.json()
    receipt_id = notification_receipts.json()["latest_receipts"][0]["event_id"]
    receipt_detail = client.get(f"/v1/ops/jobs/notification-delivery-receipts/{receipt_id}")
    assert receipt_detail.status_code == 200
    assert receipt_detail.json()["receipt"]["event_id"] == receipt_id
    adapter_probe = client.get("/v1/ops/jobs/adapter-health-probe")
    assert adapter_probe.status_code == 200
    assert "status" in adapter_probe.json()
    assert "remote_shipping" in adapter_probe.json()
    retry_policies = client.get("/v1/ops/jobs/retry-policies")
    assert retry_policies.status_code == 200
    assert "default_policy_id" in retry_policies.json()
    retry_enqueued = client.post(
        "/v1/ops/jobs/notification-retry-queue/enqueue",
        json={"event_id": receipt_id, "requested_by": "ops_retry", "note": "retry receipt"},
    )
    assert retry_enqueued.status_code == 200
    retry_queue = client.get("/v1/ops/jobs/notification-retry-queue")
    assert retry_queue.status_code == 200
    assert retry_queue.json()["retry_count"] >= 1
    retry_id = retry_queue.json()["retries"][0]["retry_id"]
    retry_processed = client.post(
        f"/v1/ops/jobs/notification-retry-queue/{retry_id}/process",
        json={"requested_by": "ops_retry", "dry_run": True},
    )
    assert retry_processed.status_code == 200
    assert retry_processed.json()["retry"]["status"] == "planned"
    dead_letters = client.get("/v1/ops/jobs/notification-dead-letter-queue")
    assert dead_letters.status_code == 200
    assert "dead_letter_count" in dead_letters.json()
    outcomes = client.get("/v1/ops/jobs/retry-outcome-dashboard")
    assert outcomes.status_code == 200
    assert "terminal_failure_count" in outcomes.json()
    acknowledged = client.post(
        f"/v1/ops/jobs/{backup_job['job_id']}/acknowledge",
        json={"requested_by": "ops_ack", "note": "taking over backup follow-up"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["job"]["acknowledged_by"] == "ops_ack"
    remote_ship = client.post(
        f"/v1/ops/jobs/{backup_job['job_id']}/ship-remote",
        json={"requested_by": "ops_ship", "remote_dir": str(tmp_path / "remote_shipments"), "dry_run": False},
    )
    assert remote_ship.status_code == 200
    assert Path(remote_ship.json()["remote_manifest_path"]).exists()
    sla_escalation = client.post(
        "/v1/ops/jobs/handoff-sla/escalate",
        json={"requested_by": "ops_sla", "sla_minutes": 60, "limit": 20, "dry_run": True},
    )
    assert sla_escalation.status_code == 200
    assert "escalated_count" in sla_escalation.json()
    cleanup = client.post(
        "/v1/ops/jobs/enforce-retention",
        json={"requested_by": "ops_cleanup", "dry_run": True, "limit": 10},
    )
    assert cleanup.status_code == 200
    assert "cleaned_job_count" in cleanup.json()
    drill = client.post(
        "/v1/ops/jobs/cold-start-drill",
        json={"requested_by": "ops_drill", "stale_after_minutes": 15, "limit": 10},
    )
    assert drill.status_code == 200
    assert "would_recover_count" in drill.json()

    failing_repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_api_fail.db"))
    failing_app = create_app(repository=failing_repository)
    failing_app.state.async_job_service.register_runner(
        "runtime_backup",
        lambda job: (_ for _ in ()).throw(RuntimeError("forced_failure")),
    )
    failing_client = TestClient(failing_app)
    failing_job = failing_client.post("/v1/ops/jobs/runtime-backups", json={"label": "fail_me"}).json()["job"]
    if failing_job["status"] != "failed":
        failing_app.state.async_job_service.run_job(failing_job["job_id"])

    retry_response = failing_client.post(
        f"/v1/ops/jobs/{failing_job['job_id']}/retry",
        json={"requested_by": "ops_retry"},
    )
    assert retry_response.status_code in {200, 400}

    stale_started_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    stale_job = failing_app.state.async_job_service.enqueue_job(
        job_type="runtime_backup",
        payload={"label": "stale_me"},
    )
    stale_job = failing_app.state.async_job_service._save_job(
        {
            **stale_job,
            "status": "running",
            "started_at": stale_started_at,
            "heartbeat_at": stale_started_at,
            "lease_expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "lease_owner": "worker_old",
        }
    )
    resume_response = failing_client.post(
        f"/v1/ops/jobs/{stale_job['job_id']}/resume",
        json={"requested_by": "ops_resume", "stale_after_minutes": 15},
    )
    assert resume_response.status_code == 200

    recovery_response = failing_client.post(
        "/v1/ops/jobs/recover-incidents",
        json={"requested_by": "ops_recover", "stale_after_minutes": 1, "limit": 5},
    )
    assert recovery_response.status_code == 200


def test_create_app_boot_reconciles_orphaned_running_jobs(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "async_jobs_boot_app.db"))
    seed_service = AsyncJobService(repository, analytics_service=AnalyticsService(repository), base_dir=tmp_path)
    seed_service.register_runner("runtime_backup", lambda job: {"status": "completed"})
    stale_started_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    orphaned = seed_service.enqueue_job(job_type="runtime_backup", payload={"label": "boot_orphan"})
    seed_service._save_job(
        {
            **orphaned,
            "status": "running",
            "started_at": stale_started_at,
            "lease_owner": "worker_old",
            "lease_acquired_at": stale_started_at,
            "lease_expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "heartbeat_at": stale_started_at,
            "heartbeat_count": 1,
        }
    )

    app = create_app(repository=repository)
    with TestClient(app) as client:
        payload = client.get("/v1/ops/jobs/boot-reconcile")
        assert payload.status_code == 200
        assert payload.json()["reconciled_count"] >= 1
        jobs = client.get("/v1/ops/jobs").json()["jobs"]
        target = next(item for item in jobs if item["job_id"] == orphaned["job_id"])
        assert target["status"] == "queued"
        assert target["last_recovery_action"] == "boot_reconciled_orphaned_running_job"
