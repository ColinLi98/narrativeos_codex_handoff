from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ACCEPTED_STATUSES = {"ok", "pass", "passed", "ready", "completed"}
FORMAL_PILOT_APP_URL = "https://pilot.lixidol.com"
FORMAL_PILOT_DOMAIN = "pilot.lixidol.com"
REMOTE_PRODUCT_SMOKE_PATH = "artifacts/vercel_remote_acceptance/latest/product_smoke.json"
REMOTE_READER_PAID_PATH_SMOKE_PATH = "artifacts/reader_paid_path_smoke_result.json"
REMOTE_AUTHOR_APPROVAL_SMOKE_PATH = "artifacts/author_remote_approval_flow/latest/summary.json"
REMOTE_OPS_SMOKE_PATH = "artifacts/quantum_ops_url_state_smoke_result.json"
REMOTE_VERCEL_PERFORMANCE_PATH = "artifacts/vercel_remote_acceptance/latest/performance.json"
REMOTE_NPM_AUDIT_PATH = "artifacts/vercel_remote_acceptance/latest/npm_audit.json"
REMOTE_DATABASE_READINESS_PATH = "artifacts/vercel_remote_acceptance/latest/database_readiness.json"
REMOTE_DATABASE_LOAD_SMOKE_PATH = "artifacts/vercel_remote_acceptance/latest/database_load_smoke.json"
REMOTE_READER_QUALITY_SAMPLE_PATH = "artifacts/vercel_remote_acceptance/latest/reader_quality_sample.json"
LAUNCH_WEEK_MONITORING_PATH = "artifacts/launch_week_monitoring/latest/summary.json"
LANE_OUTPUT_DIRS = {
    "A": Path("artifacts/lane_a_1_12_500_ready_promotion/latest"),
    "B": Path("artifacts/author_repair_efficiency/latest"),
    "C": Path("artifacts/paid_pilot_acceptance/latest/lane_c_billing_credits_audit"),
    "D": Path("artifacts/ops_pilot_console/latest"),
    "F": Path("artifacts/runtime_pilot_evidence/latest"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_path(base_dir: Path, relative_path: str) -> Path:
    return base_dir / relative_path


def _relative(base_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _read_json(base_dir: Path, relative_path: str) -> Dict[str, Any]:
    path = _artifact_path(base_dir, relative_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_read_error": True}
    return payload if isinstance(payload, dict) else {"_payload": payload}


def _read_text(base_dir: Path, relative_path: str) -> str:
    path = _artifact_path(base_dir, relative_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _first_existing_relative(base_dir: Path, candidates: Iterable[str]) -> str:
    ordered = list(candidates)
    for relative_path in ordered:
        if _artifact_path(base_dir, relative_path).exists():
            return relative_path
    return ordered[0] if ordered else ""


def _artifact(base_dir: Path, relative_path: str) -> Dict[str, Any]:
    path = _artifact_path(base_dir, relative_path)
    return {
        "path": relative_path,
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _accepted_status(value: Any) -> bool:
    return str(value or "").strip().lower() in ACCEPTED_STATUSES


def _int_from_match(pattern: str, text: str, default: int = 0) -> int:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return default
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return default


def _line_list(pattern: str, text: str) -> List[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return []
    value = match.group(1).strip()
    if not value or value == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip() and item.strip() != "-"]


def _lane_status(blockers: Iterable[Dict[str, Any]]) -> str:
    blocker_list = list(blockers)
    if any(str(item.get("severity") or "") == "missing" for item in blocker_list):
        return "missing"
    return "blocked" if blocker_list else "passed"


def _blocker(key: str, detail: str, *, severity: str = "high", **extra: Any) -> Dict[str, Any]:
    payload = {"key": key, "severity": severity, "detail": detail}
    payload.update(extra)
    return payload


def _looks_local_url(value: Optional[str]) -> bool:
    raw = str(value or "").strip().lower()
    return raw.startswith("http://127.0.0.1") or raw.startswith("http://localhost") or "://0.0.0.0" in raw


def _domain_from_url(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return urllib.parse.urlparse(raw).hostname or ""
    except Exception:
        return ""


def _resolve_vercel_deployment_id(base_dir: Path, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    binding = _read_json(base_dir, "artifacts/vercel_remote_acceptance/latest/domain_binding.json")
    deployment_id = str(binding.get("deployment_id") or "").strip()
    return deployment_id or None


def _string_contains_secret(value: str) -> bool:
    lowered = value.lower()
    secret_markers = [
        "bearer ",
        "authorization:",
        "access_token",
        "refresh_token",
        "database_url",
        "database-url",
        "postgres://",
        "postgresql://",
        "mysql://",
        "neon.tech/",
    ]
    return any(marker in lowered for marker in secret_markers)


def _payload_contains_secret(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _string_contains_secret(str(key)):
                return True
            if _payload_contains_secret(value):
                return True
        return False
    if isinstance(payload, list):
        return any(_payload_contains_secret(item) for item in payload)
    if isinstance(payload, str):
        return _string_contains_secret(payload)
    return False


def _lane_result(
    *,
    lane: str,
    task: str,
    title: str,
    evidence: Dict[str, Any],
    blockers: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
    recommended_actions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "lane": lane,
        "task": task,
        "title": title,
        "status": _lane_status(blockers),
        "ready": not blockers,
        "evidence": evidence,
        "blockers": blockers,
        "artifacts": artifacts,
        "recommended_actions": recommended_actions or ([] if not blockers else [f"close_{task.lower().replace(' ', '_')}"]),
    }


def _latest_file(base_dir: Path, pattern: str) -> Optional[Path]:
    files = [path for path in base_dir.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def build_runtime_pilot_evidence(
    *,
    base_dir: Path,
    health_url: str = "http://127.0.0.1:8000/health",
    remote_only: bool = False,
) -> Dict[str, Any]:
    runbook_text = _read_text(base_dir, "docs/deployment_runbook.md")
    latest_backup_manifest = _latest_file(base_dir, "artifacts/runtime_backups/*.json")
    latest_restore_result = _latest_file(base_dir, "artifacts/runtime_postgres_ops/job_*/result.json")
    restore_payload: Dict[str, Any] = {}
    if latest_restore_result is not None:
        try:
            restore_payload = json.loads(latest_restore_result.read_text(encoding="utf-8"))
        except Exception:
            restore_payload = {"_read_error": True}

    health_payload: Dict[str, Any] = {"status": "not_checked", "url": health_url}
    try:
        with urllib.request.urlopen(health_url, timeout=2.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        health_payload = {
            "status": "ok" if str(parsed.get("status") or "").lower() == "ok" else "unexpected",
            "url": health_url,
            "payload": parsed,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        health_payload = {"status": "unreachable", "url": health_url, "error": str(exc)}

    checks = {
        "backend_local_script_present": (base_dir / "scripts/run_backend_local.sh").exists(),
        "fixed_port_runbook_present": "http://127.0.0.1:3000" in runbook_text and "http://127.0.0.1:8000" in runbook_text,
        "health_endpoint_ok": health_payload.get("status") == "ok",
        "backup_manifest_present": latest_backup_manifest is not None,
        "restore_request_evidence_present": latest_restore_result is not None
        and str(restore_payload.get("action") or "") == "restore"
        and str(restore_payload.get("status") or "") == "completed",
        "production_restore_manual_only": "Do not paste live secrets" in runbook_text
        and "Production-only confirmations stay manual" in runbook_text,
    }
    if remote_only:
        checks["formal_domain_health_endpoint"] = not _looks_local_url(health_url) and health_payload.get("status") == "ok"
        checks["remote_only_acceptance_runbook_present"] = (
            "pilot.lixidol.com" in runbook_text
            and "REMOTE_MODE=1" in runbook_text
            and "商业化" in runbook_text
        )
    blockers = [
        _blocker(key, "Runtime pilot evidence check did not pass.")
        for key, passed in checks.items()
        if not passed and not (remote_only and key in {"backend_local_script_present", "fixed_port_runbook_present"})
    ]
    return {
        "schema_version": "runtime_pilot_evidence/v1",
        "generated_at": _utc_now(),
        "acceptance_source": "formal_domain_remote" if remote_only else "local_runtime",
        "status": _lane_status(blockers),
        "ready": not blockers,
        "fixed_ports": {"frontend": 3000, "backend": 8000},
        "checks": checks,
        "health": health_payload,
        "latest_backup_manifest": _relative(base_dir, latest_backup_manifest) if latest_backup_manifest else None,
        "latest_restore_result": _relative(base_dir, latest_restore_result) if latest_restore_result else None,
        "blockers": blockers,
    }


def _optional_artifact_json(base_dir: Path, relative_path: Optional[str]) -> Dict[str, Any]:
    if not relative_path:
        return {}
    return _read_json(base_dir, relative_path)


def _has_collection_errors(payload: Dict[str, Any], keys: Iterable[str]) -> bool:
    return any(bool(payload.get(key)) for key in keys)


def build_remote_vercel_acceptance(
    *,
    base_dir: Path,
    public_app_url: Optional[str] = None,
    vercel_deployment_id: Optional[str] = None,
    vercel_domain: Optional[str] = None,
    remote_smoke_summary_path: Optional[str] = None,
    reader_paid_path_summary_path: Optional[str] = None,
    author_approval_summary_path: Optional[str] = None,
    ops_remote_smoke_summary_path: Optional[str] = None,
    vercel_performance_summary_path: Optional[str] = None,
    npm_audit_summary_path: Optional[str] = None,
    database_readiness_summary_path: Optional[str] = None,
    database_load_smoke_summary_path: Optional[str] = None,
    reader_quality_sample_summary_path: Optional[str] = None,
    launch_week_monitoring_summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    smoke = _optional_artifact_json(base_dir, remote_smoke_summary_path)
    reader_paid = _optional_artifact_json(base_dir, reader_paid_path_summary_path)
    author_approval = _optional_artifact_json(base_dir, author_approval_summary_path)
    ops_remote = _optional_artifact_json(base_dir, ops_remote_smoke_summary_path)
    performance = _optional_artifact_json(base_dir, vercel_performance_summary_path)
    npm_audit = _optional_artifact_json(base_dir, npm_audit_summary_path)
    database_readiness = _optional_artifact_json(base_dir, database_readiness_summary_path)
    database_load_smoke = _optional_artifact_json(base_dir, database_load_smoke_summary_path)
    reader_quality_sample = _optional_artifact_json(base_dir, reader_quality_sample_summary_path)
    launch_week_monitoring = _optional_artifact_json(base_dir, launch_week_monitoring_summary_path)
    blockers: List[Dict[str, Any]] = []
    production_high_count = int(npm_audit.get("production_high_count", 0) or 0) if npm_audit else None
    resolved_deployment_id = _resolve_vercel_deployment_id(base_dir, vercel_deployment_id)

    if public_app_url:
        if _looks_local_url(public_app_url):
            blockers.append(_blocker("formal_domain_url_required", "Commercial ready acceptance must use the formal external URL, not localhost."))
        if _domain_from_url(public_app_url) != FORMAL_PILOT_DOMAIN:
            blockers.append(_blocker("formal_domain_mismatch", "Commercial ready acceptance must target pilot.lixidol.com."))
        if not resolved_deployment_id:
            blockers.append(_blocker("vercel_deployment_id_missing", "Formal-domain acceptance must record the Vercel production deployment id."))

        if not remote_smoke_summary_path or not smoke:
            blockers.append(_blocker("remote_product_smoke_missing", "Formal-domain browser/API smoke evidence is required."))
        elif not _accepted_status(smoke.get("status")) or _has_collection_errors(
            smoke,
            ["api_errors", "browser_response_errors", "console_errors", "layout_errors"],
        ):
            blockers.append(_blocker("remote_product_smoke_failed", "Formal-domain product smoke must pass without API, console, or layout errors."))
        elif _payload_contains_secret(smoke):
            blockers.append(_blocker("remote_product_smoke_secret_leak", "Remote product smoke artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

        if not reader_quality_sample_summary_path or not reader_quality_sample:
            blockers.append(_blocker("remote_reader_quality_sample_missing", "Formal-domain Reader generated quality sample evidence is required."))
        else:
            if not bool(reader_quality_sample.get("ready", False)) or not _accepted_status(reader_quality_sample.get("status")):
                blockers.append(
                    _blocker(
                        "remote_reader_quality_sample_not_ready",
                        "Formal-domain Reader generated sample must have no broken slots, engineering/meta leaks, or Q03/choice regressions.",
                        violation_count=reader_quality_sample.get("violation_count"),
                        issue_counts=reader_quality_sample.get("issue_counts"),
                    )
                )
            if _looks_local_url(reader_quality_sample.get("public_app_url") or reader_quality_sample.get("api_origin")):
                blockers.append(_blocker("remote_reader_quality_sample_local_url", "Reader quality sample must come from the formal domain."))
            if _payload_contains_secret(reader_quality_sample):
                blockers.append(_blocker("remote_reader_quality_sample_secret_leak", "Reader quality sample artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

        if not reader_paid_path_summary_path or not reader_paid:
            blockers.append(_blocker("remote_reader_paid_path_smoke_missing", "Formal-domain Reader paid-path smoke evidence is required."))
        else:
            runtime = dict(reader_paid.get("runtime") or {})
            remote_mode = bool(reader_paid.get("remote_mode", False) or runtime.get("remote_mode", False))
            if not _accepted_status(reader_paid.get("status")):
                blockers.append(_blocker("remote_reader_paid_path_smoke_failed", "Reader paid-path remote smoke must pass."))
            if not remote_mode:
                blockers.append(_blocker("remote_reader_paid_path_not_remote", "Reader paid-path smoke must run in remote mode for commercial acceptance."))
            if reader_paid.get("schema_version") != "reader_paid_path_smoke/v2":
                blockers.append(_blocker("remote_reader_paid_path_schema_outdated", "Reader paid-path smoke must use v2 remote-only artifact schema."))
            if _looks_local_url(runtime.get("public_app_url") or reader_paid.get("public_app_url")):
                blockers.append(_blocker("remote_reader_paid_path_local_url", "Reader paid-path artifact cannot be based on localhost."))
            if reader_paid.get("database_ref") or runtime.get("database_ref"):
                blockers.append(_blocker("remote_reader_paid_path_db_ref_present", "Reader paid-path remote smoke must not record or depend on database refs."))
            if not dict(reader_paid.get("paywall") or {}).get("required"):
                blockers.append(_blocker("remote_reader_paid_path_paywall_missing", "Reader paid-path remote smoke must prove payment_required before checkout."))
            if str(reader_paid.get("subscription_status") or "") != "active":
                blockers.append(_blocker("remote_reader_paid_path_subscription_inactive", "Reader paid-path remote smoke must activate subscription after checkout."))
            if _payload_contains_secret(reader_paid):
                blockers.append(_blocker("remote_reader_paid_path_secret_leak", "Reader paid-path artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

        if not author_approval_summary_path or not author_approval:
            blockers.append(_blocker("remote_author_approval_smoke_missing", "Formal-domain Author/Reviewer approval smoke evidence is required."))
        else:
            author_runtime = dict(author_approval.get("runtime") or {})
            if not _accepted_status(author_approval.get("status")) or _has_collection_errors(author_approval, ["api_errors", "console_errors", "browser_response_errors"]):
                blockers.append(_blocker("remote_author_approval_smoke_failed", "Formal-domain Author/Reviewer approval smoke must pass without API or browser errors."))
            if not bool(author_approval.get("remote_mode", False) or author_runtime.get("remote_mode", False)):
                blockers.append(_blocker("remote_author_approval_not_remote", "Author approval smoke must run against the formal domain for commercial acceptance."))
            if _looks_local_url(author_approval.get("public_app_url") or author_runtime.get("public_app_url") or author_runtime.get("api_origin")):
                blockers.append(_blocker("remote_author_approval_local_url", "Author approval smoke artifact cannot be based on localhost."))
            if _payload_contains_secret(author_approval):
                blockers.append(_blocker("remote_author_approval_secret_leak", "Author approval smoke artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

        if not ops_remote_smoke_summary_path or not ops_remote:
            blockers.append(_blocker("remote_ops_smoke_missing", "Formal-domain Ops smoke evidence is required."))
        else:
            if not _accepted_status(ops_remote.get("status")) or _has_collection_errors(ops_remote, ["api_errors", "browser_response_errors", "console_errors", "layout_errors"]):
                blockers.append(_blocker("remote_ops_smoke_failed", "Formal-domain Ops smoke must pass without API, console, or layout errors."))
            if not bool(ops_remote.get("remote_mode", False)):
                blockers.append(_blocker("remote_ops_smoke_not_remote", "Ops smoke must run against the formal domain for commercial acceptance."))
            if _looks_local_url(ops_remote.get("public_app_url") or ops_remote.get("api_origin")):
                blockers.append(_blocker("remote_ops_smoke_local_url", "Ops smoke artifact cannot be based on localhost."))
            if _payload_contains_secret(ops_remote):
                blockers.append(_blocker("remote_ops_smoke_secret_leak", "Ops smoke artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

        if not vercel_performance_summary_path or not performance:
            blockers.append(_blocker("vercel_performance_summary_missing", "Vercel bundle/cold-start performance evidence is required."))
        elif not bool(performance.get("ready", False)):
            blockers.append(_blocker("vercel_performance_not_ready", "Vercel bundle/cold-start checks did not pass."))

        if not npm_audit_summary_path or not npm_audit:
            blockers.append(_blocker("npm_audit_summary_missing", "npm audit evidence is required for remote acceptance."))
        elif production_high_count != 0:
            blockers.append(
                _blocker(
                    "npm_production_high_vulnerabilities_present",
                    "Production npm audit high vulnerabilities must be zero.",
                    production_high_count=production_high_count,
                )
            )

        if not database_readiness_summary_path or not database_readiness:
            blockers.append(_blocker("public_beta_database_readiness_missing", "Public Beta database readiness evidence is required."))
        elif not bool(database_readiness.get("ready", False)):
            blockers.append(
                _blocker(
                    "public_beta_database_not_ready",
                    "Public Beta requires pooled Postgres, direct migration URL, read-replica evidence, and SQLite failover disabled.",
                    failed_checks=[
                        key
                        for key, passed in dict(database_readiness.get("checks") or {}).items()
                        if not passed
                    ],
                )
            )

        if not database_load_smoke_summary_path or not database_load_smoke:
            blockers.append(_blocker("public_beta_database_load_smoke_missing", "Public Beta database load smoke evidence is required."))
        elif not bool(database_load_smoke.get("ready", False)):
            blockers.append(
                _blocker(
                    "public_beta_database_load_smoke_failed",
                    "Public Beta database load smoke must pass without quota, connection, or latency failures.",
                    error_count=database_load_smoke.get("error_count"),
                    read_p95_ms=database_load_smoke.get("read_p95_ms"),
                    write_p95_ms=database_load_smoke.get("write_p95_ms"),
                )
            )

        if not launch_week_monitoring_summary_path or not launch_week_monitoring:
            blockers.append(_blocker("launch_week_monitoring_missing", "Launch-week remote monitoring closure evidence is required."))
        else:
            monitoring_deployment_id = str(launch_week_monitoring.get("vercel_deployment_id") or "").strip()
            if not monitoring_deployment_id:
                blockers.append(_blocker("launch_week_monitoring_deployment_id_missing", "Launch-week monitoring summary must record the Vercel deployment id."))
            elif resolved_deployment_id and monitoring_deployment_id != resolved_deployment_id:
                blockers.append(
                    _blocker(
                        "launch_week_monitoring_deployment_id_mismatch",
                        "Launch-week monitoring deployment id must match the paid acceptance deployment id.",
                        monitoring_deployment_id=monitoring_deployment_id,
                        acceptance_deployment_id=resolved_deployment_id,
                    )
                )
            if not bool(launch_week_monitoring.get("ready_to_expand", False)):
                blockers.append(_blocker("launch_week_monitoring_not_ready_to_expand", "Launch-week monitoring is red; pause new invite expansion."))
            if _payload_contains_secret(launch_week_monitoring):
                blockers.append(_blocker("launch_week_monitoring_secret_leak", "Launch-week monitoring artifact must not contain tokens, cookies, DB URLs, or raw secrets."))

    return {
        "schema_version": "remote_vercel_acceptance/v1",
        "generated_at": _utc_now(),
        "public_app_url": public_app_url,
        "vercel_domain": vercel_domain,
        "vercel_deployment_id": resolved_deployment_id,
        "ready": not blockers,
        "status": "passed" if not blockers else "blocked",
        "remote_smoke": {
            "path": remote_smoke_summary_path,
            "status": smoke.get("status"),
            "completed_step_count": len(list(smoke.get("completed_steps") or [])),
            "api_error_count": len(list(smoke.get("api_errors") or [])),
            "browser_response_error_count": len(list(smoke.get("browser_response_errors") or [])),
            "console_error_count": len(list(smoke.get("console_errors") or [])),
            "layout_error_count": len(list(smoke.get("layout_errors") or [])),
        },
        "reader_quality_sample": {
            "path": reader_quality_sample_summary_path,
            "status": reader_quality_sample.get("status"),
            "ready": bool(reader_quality_sample.get("ready", False)),
            "sample_node_count": reader_quality_sample.get("sample_node_count"),
            "violation_count": reader_quality_sample.get("violation_count"),
            "issue_counts": reader_quality_sample.get("issue_counts"),
        },
        "reader_paid_path": {
            "path": reader_paid_path_summary_path,
            "status": reader_paid.get("status"),
            "schema_version": reader_paid.get("schema_version"),
            "remote_mode": bool(reader_paid.get("remote_mode", False) or dict(reader_paid.get("runtime") or {}).get("remote_mode", False)),
            "paywall_required": bool(dict(reader_paid.get("paywall") or {}).get("required")),
            "subscription_status": reader_paid.get("subscription_status"),
            "cleanup": dict(reader_paid.get("cleanup") or {}),
        },
        "author_approval": {
            "path": author_approval_summary_path,
            "status": author_approval.get("status"),
            "remote_mode": bool(author_approval.get("remote_mode", False) or dict(author_approval.get("runtime") or {}).get("remote_mode", False)),
            "completed_step_count": len(list(author_approval.get("completed_steps") or author_approval.get("steps") or [])),
            "ops_audit_hit_count": author_approval.get("ops_audit_hit_count") or dict(author_approval.get("summary") or {}).get("ops_audit_hit_count"),
        },
        "ops_remote_smoke": {
            "path": ops_remote_smoke_summary_path,
            "status": ops_remote.get("status"),
            "remote_mode": bool(ops_remote.get("remote_mode", False)),
            "completed_step_count": len(list(ops_remote.get("completed_steps") or [])),
            "cleanup": dict(ops_remote.get("cleanup") or {}),
        },
        "performance": {
            "path": vercel_performance_summary_path,
            "ready": performance.get("ready"),
            "bundle_mb": performance.get("bundle_mb"),
            "health_hot_ms": performance.get("health_hot_ms"),
            "cold_start_5xx_count": performance.get("cold_start_5xx_count"),
        },
        "npm_audit": {
            "path": npm_audit_summary_path,
            "production_high_count": production_high_count,
            "full_high_count": npm_audit.get("full_high_count") if npm_audit else None,
            "risk_register": npm_audit.get("risk_register") if npm_audit else None,
        },
        "database_readiness": {
            "path": database_readiness_summary_path,
            "ready": database_readiness.get("ready") if database_readiness else None,
            "status": database_readiness.get("status") if database_readiness else None,
            "failed_checks": [
                key
                for key, passed in dict(database_readiness.get("checks") or {}).items()
                if not passed
            ] if database_readiness else [],
            "runtime_database": dict(database_readiness.get("runtime_database") or {}) if database_readiness else {},
            "read_replica_configured": bool(
                dict(database_readiness.get("read_replica_database") or {}).get("configured")
            ) if database_readiness else False,
            "sqlite_failover": dict(database_readiness.get("sqlite_failover") or {}) if database_readiness else {},
        },
        "database_load_smoke": {
            "path": database_load_smoke_summary_path,
            "ready": database_load_smoke.get("ready") if database_load_smoke else None,
            "status": database_load_smoke.get("status") if database_load_smoke else None,
            "read_concurrency": database_load_smoke.get("read_concurrency") if database_load_smoke else None,
            "write_concurrency": database_load_smoke.get("write_concurrency") if database_load_smoke else None,
            "error_count": database_load_smoke.get("error_count") if database_load_smoke else None,
            "read_p95_ms": database_load_smoke.get("read_p95_ms") if database_load_smoke else None,
            "write_p95_ms": database_load_smoke.get("write_p95_ms") if database_load_smoke else None,
        },
        "launch_week_monitoring": {
            "path": launch_week_monitoring_summary_path,
            "status": launch_week_monitoring.get("status"),
            "ready_to_expand": bool(launch_week_monitoring.get("ready_to_expand", False)),
            "vercel_deployment_id": launch_week_monitoring.get("vercel_deployment_id"),
            "breached_signals": list(launch_week_monitoring.get("breached_signals") or []),
        },
        "blockers": blockers,
    }


def _lane_a(base_dir: Path, *, require_remote_reader_quality: bool = False) -> Dict[str, Any]:
    markdown_path = _first_existing_relative(
        base_dir,
        [
            "artifacts/lane_a_quality_closure_all_pack_500.md",
            "artifacts/lane_a_1_13_all_pack_500.md",
            "artifacts/lane_a_1_7_all_pack_500.md",
        ],
    )
    runtime_path = _first_existing_relative(
        base_dir,
        [
            "artifacts/lane_a_quality_closure_all_pack_500_runtime.json",
            "artifacts/lane_a_1_13_all_pack_500_runtime.json",
            "artifacts/lane_a_1_7_all_pack_500_runtime.json",
        ],
    )
    human_path = "artifacts/lane_a_1_8_500_human_sampling.json"
    replay_path = "artifacts/lane_a_1_10_500_replay_result.json"
    remote_quality_path = REMOTE_READER_QUALITY_SAMPLE_PATH
    text = _read_text(base_dir, markdown_path)
    human = _read_json(base_dir, human_path)
    replay = _read_json(base_dir, replay_path)
    remote_quality = _read_json(base_dir, remote_quality_path)

    packs_reaching = _line_list(r"- packs reaching target:\s*(.+)", text)
    continue_worlds = _line_list(r"- continue worlds:\s*(.+)", text)
    stop_ready_worlds = _line_list(r"- stop-ready worlds:\s*(.+)", text)
    program_status_match = re.search(r"- program status:\s*([^\n]+)", text, flags=re.IGNORECASE)
    program_status = program_status_match.group(1).strip() if program_status_match else None
    hard_fail_count = _int_from_match(r"- hard fail count:\s*(\d+)", text)
    scene_card_violations = _int_from_match(r"- scene-card visible text violations:\s*(\d+)", text)
    human_target = int(human.get("target_count", 0) or 0)
    human_reviewed = int(human.get("reviewed_count", 0) or 0)
    human_high = int(human.get("high_count", 0) or 0)
    human_medium = int(human.get("medium_count", 0) or 0)
    human_ready = (
        human_target >= 36
        and human_reviewed >= human_target
        and human_high == 0
        and human_medium <= int(human.get("max_medium", 0) or 0)
        and bool(human.get("reader_q03_recovery_ready", False))
        and bool(human.get("reader_perceived_redundancy_closeout_ready", False))
    )
    replay_ready = (
        _accepted_status(replay.get("status"))
        and int(replay.get("reviewed_count", 0) or 0) >= int(replay.get("target_count", 0) or 0)
        and int(replay.get("worlds_reaching_500", 0) or 0) >= int(replay.get("world_count", 0) or 0)
        and not list(replay.get("console_errors") or [])
    )
    fresh_500_ready = (
        len(packs_reaching) >= 6
        and hard_fail_count == 0
        and scene_card_violations == 0
        and _artifact_path(base_dir, runtime_path).exists()
        and program_status == "stop_ready"
        and not [world for world in continue_worlds if world in {"jade_court_exam", "jade_court_romance"}]
    )
    remote_quality_ready = (
        bool(remote_quality.get("ready", False))
        and _accepted_status(remote_quality.get("status"))
        and int(remote_quality.get("violation_count", 0) or 0) == 0
        and not _payload_contains_secret(remote_quality)
        and not _looks_local_url(remote_quality.get("public_app_url") or remote_quality.get("api_origin"))
    )
    blockers: List[Dict[str, Any]] = []
    if len(packs_reaching) < 6:
        blockers.append(_blocker("longform_500_all_pack_incomplete", "Fresh all-pack 500 evidence did not show 6/6 packs reaching 500.", packs_reaching=packs_reaching))
    if hard_fail_count != 0:
        blockers.append(_blocker("longform_500_hard_failures_present", "Persisted chapter hard failures must be zero.", hard_fail_count=hard_fail_count))
    if scene_card_violations != 0:
        blockers.append(_blocker("scene_card_visible_text_violations_present", "Scene-card visible text violations must be zero.", violation_count=scene_card_violations))
    if not human_ready:
        blockers.append(_blocker("review_sample_coverage_500_human_closeout_not_ready", "36 chapter human sampling closeout is incomplete or has unacceptable risk.", target_count=human_target, reviewed_count=human_reviewed, high_count=human_high, medium_count=human_medium))
    if not replay_ready:
        blockers.append(_blocker("reader_500_replay_not_ready", "Reader 500 replay projection evidence is missing or has console/sample failures."))
    if not _artifact_path(base_dir, runtime_path).exists():
        blockers.append(_blocker("longform_500_runtime_profile_missing", "Runtime profile artifact is required."))
    jade_continue = [world for world in continue_worlds if world in {"jade_court_exam", "jade_court_romance"}]
    if program_status != "stop_ready" or jade_continue:
        blockers.append(_blocker("weakest_pack_polish_program_not_stop_ready", "Jade weakest-pack continue_polish must be closed before promotion.", program_status=program_status, continue_worlds=continue_worlds))
    if require_remote_reader_quality and not remote_quality_ready:
        blockers.append(
            _blocker(
                "remote_reader_quality_sample_not_ready",
                "Formal-domain Reader generated sample must pass content-quality smoke before promotion.",
                violation_count=remote_quality.get("violation_count"),
                issue_counts=remote_quality.get("issue_counts"),
            )
        )

    evidence = {
        "fresh_500_ready": fresh_500_ready,
        "packs_reaching_500_count": len(packs_reaching),
        "packs_reaching_500": packs_reaching,
        "hard_fail_count": hard_fail_count,
        "scene_card_visible_text_violation_count": scene_card_violations,
        "human_sampling_ready": human_ready,
        "review_sample_coverage_500": {
            "human_closeout_ready": human_ready,
            "target_count": human_target,
            "reviewed_count": human_reviewed,
            "high_count": human_high,
            "medium_count": human_medium,
        },
        "reader_500_replay_ready": replay_ready,
        "runtime_profile_present": _artifact_path(base_dir, runtime_path).exists(),
        "weakest_pack_polish_program": {
            "status": program_status,
            "stop_ready_worlds": stop_ready_worlds,
            "continue_worlds": continue_worlds,
        },
        "remote_reader_quality_sample_ready": remote_quality_ready,
        "remote_reader_quality_sample": {
            "status": remote_quality.get("status"),
            "sample_node_count": remote_quality.get("sample_node_count"),
            "violation_count": remote_quality.get("violation_count"),
            "issue_counts": remote_quality.get("issue_counts"),
        },
        "product_ready_band_500_promoted": not blockers,
    }
    return _lane_result(
        lane="A",
        task="1.13" if "lane_a_1_13" in markdown_path else "1.12",
        title=(
            "Jade continue_polish Kernel Closure"
            if "lane_a_1_13" in markdown_path
            else "500-Ready Promotion Closure"
        ),
        evidence=evidence,
        blockers=blockers,
        artifacts=[
            _artifact(base_dir, markdown_path),
            _artifact(base_dir, runtime_path),
            _artifact(base_dir, human_path),
            _artifact(base_dir, replay_path),
            _artifact(base_dir, remote_quality_path),
        ],
        recommended_actions=[] if not blockers else ["close_jade_continue_polish", "rerun_longform_500_with_human_closeout_ingested"],
    )


def _lane_c(base_dir: Path, *, remote_only: bool = False) -> Dict[str, Any]:
    reader_path = "artifacts/reader_paid_path_smoke_result.json"
    uat_path = "artifacts/commercialization_uat/latest/summary.json"
    stripe_path = "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json"
    reader = _read_json(base_dir, reader_path)
    uat = _read_json(base_dir, uat_path)
    stripe = _read_json(base_dir, stripe_path)
    journey = dict(uat.get("journey") or {})
    lifecycle_after_failure = dict(journey.get("lifecycle_after_failure") or {})
    lifecycle_after_recovery = dict(journey.get("lifecycle_after_recovery") or {})

    blockers: List[Dict[str, Any]] = []
    if not _accepted_status(reader.get("status")):
        blockers.append(_blocker("reader_paid_path_smoke_not_passed", "Reader paid path smoke must pass."))
    if str(reader.get("subscription_status") or "") != "active":
        blockers.append(_blocker("subscription_not_active_after_checkout", "Checkout completion must activate the subscription."))
    paywall = dict(reader.get("paywall") or {})
    if not bool(paywall.get("required")) or str(paywall.get("reason") or "") != "credits_exhausted":
        blockers.append(_blocker("reader_paywall_payment_required_not_proven", "Unsubscribed/zero-credit Reader path must hit payment_required semantics."))
    if list(reader.get("apiErrors") or []) or list(reader.get("browserResponseErrors") or []) or list(reader.get("consoleErrors") or []):
        blockers.append(_blocker("reader_paid_path_browser_or_api_errors", "Paid path smoke must have no browser/API errors."))
    if remote_only:
        runtime = dict(reader.get("runtime") or {})
        if not bool(reader.get("remote_mode", False) or runtime.get("remote_mode", False)):
            blockers.append(_blocker("reader_paid_path_not_remote", "Commercial ready billing evidence must come from the formal-domain Reader paid-path smoke."))
        if reader.get("schema_version") != "reader_paid_path_smoke/v2":
            blockers.append(_blocker("reader_paid_path_schema_outdated", "Reader paid-path remote smoke must emit schema v2."))
        if reader.get("database_ref") or runtime.get("database_ref"):
            blockers.append(_blocker("reader_paid_path_db_ref_present", "Remote Reader paid-path smoke must not depend on or record database refs."))
    acceptance = dict(uat.get("acceptance") or {})
    if not bool(acceptance.get("all_passed", False)):
        blockers.append(_blocker("commercialization_uat_not_passed", "Commercial billing UAT acceptance must pass."))
    dunning_failure = dict(lifecycle_after_failure.get("dunning_summary") or {})
    dunning_recovery = dict(lifecycle_after_recovery.get("dunning_summary") or {})
    if str(dunning_failure.get("status") or "") != "open" or str(dunning_recovery.get("status") or "") != "resolved":
        blockers.append(_blocker("failed_payment_retry_reconcile_not_visible", "Failure, retry, and recovery lifecycle evidence is required."))
    invoice = dict(stripe.get("invoice") or {})
    stripe_test_mode = bool(dict(invoice.get("invoice_payload_json") or {}).get("livemode") is False) if invoice else True
    if not stripe_test_mode:
        blockers.append(_blocker("live_payment_provider_detected", "Paid pilot evidence must not use live provider keys."))

    evidence = {
        "reader_paid_path_status": reader.get("status"),
        "paywall_reason": paywall.get("reason"),
        "checkout_session_id": reader.get("checkout_session_id"),
        "subscription_status": reader.get("subscription_status"),
        "effective_tier": reader.get("effective_tier"),
        "story_credits_after_checkout": next((step.get("story_credits") for step in reader.get("steps", []) if step.get("name") == "verify_post_payment_state"), None),
        "commercialization_uat_all_passed": bool(acceptance.get("all_passed", False)),
        "commercialization_uat_checkpoint_count": acceptance.get("checkpoint_count"),
        "failed_payment_status": dunning_failure.get("status"),
        "recovered_payment_status": dunning_recovery.get("status"),
        "stripe_external_acceptance_test_mode": stripe_test_mode,
        "provider": paywall.get("provider"),
        "remote_mode": bool(reader.get("remote_mode", False) or dict(reader.get("runtime") or {}).get("remote_mode", False)),
        "smoke_run_id": reader.get("smoke_run_id"),
    }
    return _lane_result(
        lane="C",
        task="3.9",
        title="Paid Pilot Billing / Credits / Audit E2E",
        evidence=evidence,
        blockers=blockers,
        artifacts=[_artifact(base_dir, reader_path), _artifact(base_dir, uat_path), _artifact(base_dir, stripe_path)],
        recommended_actions=[] if not blockers else ["rerun_reader_paid_path_smoke", "rerun_commercialization_uat"],
    )


def _lane_f(base_dir: Path, runtime_evidence: Dict[str, Any]) -> Dict[str, Any]:
    blockers = list(runtime_evidence.get("blockers") or [])
    evidence = {
        "runtime_evidence_ready": bool(runtime_evidence.get("ready", False)),
        "fixed_ports": runtime_evidence.get("fixed_ports"),
        "checks": runtime_evidence.get("checks"),
        "health": runtime_evidence.get("health"),
        "latest_backup_manifest": runtime_evidence.get("latest_backup_manifest"),
        "latest_restore_result": runtime_evidence.get("latest_restore_result"),
    }
    artifacts = [
        _artifact(base_dir, "docs/deployment_runbook.md"),
        _artifact(base_dir, "scripts/run_backend_local.sh"),
    ]
    latest_backup = runtime_evidence.get("latest_backup_manifest")
    latest_restore = runtime_evidence.get("latest_restore_result")
    if latest_backup:
        artifacts.append(_artifact(base_dir, str(latest_backup)))
    if latest_restore:
        artifacts.append(_artifact(base_dir, str(latest_restore)))
    return _lane_result(
        lane="F",
        task="6.8",
        title="Staging/Prod Runtime Evidence Pack",
        evidence=evidence,
        blockers=blockers,
        artifacts=artifacts,
        recommended_actions=[] if not blockers else ["restart_backend_on_8000", "rerun_runtime_preflight_evidence_builder"],
    )


def _lane_b(base_dir: Path) -> Dict[str, Any]:
    result_path = "artifacts/author_repair_loop_smoke_result.json"
    result = _read_json(base_dir, result_path)
    summary = dict(result.get("summary") or {})
    completed_steps = list(result.get("completed_steps") or [])
    blockers: List[Dict[str, Any]] = []
    if not _accepted_status(result.get("status")):
        blockers.append(_blocker("author_repair_loop_smoke_not_passed", "Author repair loop smoke must pass."))
    required_steps = {
        "author_create_draft_from_brief",
        "author_simulate_draft",
        "author_repair_loop_visible_after_rerun",
        "author_execute_strategy_bundle",
        "author_repair_loop_ready_for_validation",
        "author_submit_repaired_draft",
    }
    missing_steps = sorted(required_steps - set(completed_steps))
    if missing_steps:
        blockers.append(_blocker("author_repair_loop_missing_steps", "Author repair loop smoke did not cover required steps.", missing_steps=missing_steps))
    if not summary.get("author_repair_loop_issue_code"):
        blockers.append(_blocker("author_repair_loop_issue_not_actionable", "Top issue code must be visible."))
    if not bool(summary.get("author_repair_loop_ready_for_validation", False)):
        blockers.append(_blocker("author_repair_loop_not_ready_for_validation", "Ready-for-validation must drive submit for paid pilot acceptance.", severity="medium"))
    if not summary.get("author_repair_loop_execution_id") or int(summary.get("author_repair_loop_applied_edit_count", 0) or 0) <= 0:
        blockers.append(_blocker("author_strategy_bundle_receipt_missing", "Author repair loop must include an applied strategy bundle receipt.", severity="medium"))
    if not bool(summary.get("author_repair_loop_before_after_available", False)):
        blockers.append(_blocker("author_repair_loop_compare_missing", "Author repair loop must expose before/after compare evidence.", severity="medium"))
    if str(summary.get("author_submit_status") or "") not in {"submitted", "review_requested", "pending_review"}:
        blockers.append(_blocker("author_repair_loop_submit_missing", "Author repair loop must submit the repaired draft after validation.", severity="medium"))
    evidence = {
        "smoke_status": result.get("status"),
        "completed_step_count": len(completed_steps),
        "issue_code": summary.get("author_repair_loop_issue_code"),
        "asset_type": summary.get("author_repair_loop_asset_type"),
        "strategy_bundle_id": summary.get("author_repair_loop_strategy_bundle_id"),
        "strategy_bundle_execution_id": summary.get("author_repair_loop_execution_id"),
        "applied_edit_count": summary.get("author_repair_loop_applied_edit_count"),
        "before_after_available": bool(summary.get("author_repair_loop_before_after_available", False)),
        "severity_trend": summary.get("author_repair_loop_severity_trend"),
        "ready_for_validation": bool(summary.get("author_repair_loop_ready_for_validation", False)),
        "submit_status": summary.get("author_submit_status"),
        "submit_review_request_id": summary.get("author_submit_review_request_id"),
        "console_errors": list(result.get("console_errors") or []),
    }
    return _lane_result(
        lane="B",
        task="2.8",
        title="Author Repair Workbench Efficiency",
        evidence=evidence,
        blockers=blockers,
        artifacts=[_artifact(base_dir, result_path)],
        recommended_actions=[] if not blockers else ["complete_author_strategy_bundle_submit_flow", "rerun_author_repair_loop_smoke"],
    )


def _lane_d(base_dir: Path) -> Dict[str, Any]:
    ops_path = "artifacts/quantum_ops_url_state_smoke_result.json"
    closure_path = "artifacts/human_signoff_closure/latest/operator_evidence_closure.json"
    support_packet_path = "artifacts/human_signoff_closure/latest/support_review_packet.md"
    ops = _read_json(base_dir, ops_path)
    closure = _read_json(base_dir, closure_path)
    completed_steps = list(ops.get("completed_steps") or [])
    summary = dict(ops.get("summary") or {})
    blockers: List[Dict[str, Any]] = []
    if not _accepted_status(ops.get("status")):
        blockers.append(_blocker("ops_url_state_smoke_not_passed", "Ops console smoke must pass."))
    required_steps = {
        "open_quantum_ops_account",
        "open_quantum_ops_release",
        "open_quantum_ops_alerts",
        "acknowledge_quantum_ops_alert",
        "resolve_quantum_ops_alert",
        "open_governance_case_detail",
        "append_governance_evidence",
        "transition_governance_status",
    }
    missing_steps = sorted(required_steps - set(completed_steps))
    if missing_steps:
        blockers.append(_blocker("ops_console_missing_required_steps", "Ops console smoke did not cover required support/rollback steps.", missing_steps=missing_steps))
    if not summary.get("ops_account_account_id"):
        blockers.append(_blocker("ops_account_workspace_not_proven", "Ops account workspace evidence is required."))
    signoff = dict(closure.get("signoff") or {})
    rollup = dict(signoff.get("rollup_summary_json") or {})
    pending_items = int(rollup.get("pending_item_count", 0) or 0)
    if pending_items > 0:
        blockers.append(_blocker("operator_evidence_closure_pending", "Operator support/rollback evidence still has pending items.", severity="medium", pending_item_count=pending_items))
    evidence = {
        "ops_smoke_status": ops.get("status"),
        "completed_step_count": len(completed_steps),
        "ops_account_account_id": summary.get("ops_account_account_id"),
        "ops_alert_id": summary.get("ops_alert_id"),
        "ops_governance_case_id": summary.get("ops_governance_case_id"),
        "ops_release_url_restored": summary.get("ops_release_url_restored"),
        "operator_evidence_status": closure.get("status"),
        "operator_pending_item_count": pending_items,
        "support_packet_present": _artifact_path(base_dir, support_packet_path).exists(),
    }
    return _lane_result(
        lane="D",
        task="4.7",
        title="Ops Support / Rollback Pilot Console",
        evidence=evidence,
        blockers=blockers,
        artifacts=[_artifact(base_dir, ops_path), _artifact(base_dir, closure_path), _artifact(base_dir, support_packet_path)],
        recommended_actions=[] if not blockers else ["close_operator_support_rollback_evidence", "rerun_ops_pilot_console_smoke"],
    )


def build_paid_pilot_acceptance(
    *,
    base_dir: Path,
    health_url: str = "http://127.0.0.1:8000/health",
    public_app_url: Optional[str] = None,
    vercel_deployment_id: Optional[str] = None,
    vercel_domain: Optional[str] = None,
    remote_smoke_summary_path: Optional[str] = None,
    reader_paid_path_summary_path: Optional[str] = None,
    author_approval_summary_path: Optional[str] = None,
    ops_remote_smoke_summary_path: Optional[str] = None,
    vercel_performance_summary_path: Optional[str] = None,
    npm_audit_summary_path: Optional[str] = None,
    database_readiness_summary_path: Optional[str] = None,
    database_load_smoke_summary_path: Optional[str] = None,
    reader_quality_sample_summary_path: Optional[str] = None,
    launch_week_monitoring_summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    remote_only = bool(public_app_url)
    if remote_only:
        remote_smoke_summary_path = remote_smoke_summary_path or REMOTE_PRODUCT_SMOKE_PATH
        reader_paid_path_summary_path = reader_paid_path_summary_path or REMOTE_READER_PAID_PATH_SMOKE_PATH
        author_approval_summary_path = author_approval_summary_path or REMOTE_AUTHOR_APPROVAL_SMOKE_PATH
        ops_remote_smoke_summary_path = ops_remote_smoke_summary_path or REMOTE_OPS_SMOKE_PATH
        vercel_performance_summary_path = vercel_performance_summary_path or REMOTE_VERCEL_PERFORMANCE_PATH
        npm_audit_summary_path = npm_audit_summary_path or REMOTE_NPM_AUDIT_PATH
        database_readiness_summary_path = database_readiness_summary_path or REMOTE_DATABASE_READINESS_PATH
        database_load_smoke_summary_path = database_load_smoke_summary_path or REMOTE_DATABASE_LOAD_SMOKE_PATH
        reader_quality_sample_summary_path = reader_quality_sample_summary_path or REMOTE_READER_QUALITY_SAMPLE_PATH
        launch_week_monitoring_summary_path = launch_week_monitoring_summary_path or LAUNCH_WEEK_MONITORING_PATH
    runtime_evidence = build_runtime_pilot_evidence(base_dir=base_dir, health_url=health_url, remote_only=remote_only)
    remote_vercel_acceptance = build_remote_vercel_acceptance(
        base_dir=base_dir,
        public_app_url=public_app_url,
        vercel_deployment_id=vercel_deployment_id,
        vercel_domain=vercel_domain,
        remote_smoke_summary_path=remote_smoke_summary_path,
        reader_paid_path_summary_path=reader_paid_path_summary_path,
        author_approval_summary_path=author_approval_summary_path,
        ops_remote_smoke_summary_path=ops_remote_smoke_summary_path,
        vercel_performance_summary_path=vercel_performance_summary_path,
        npm_audit_summary_path=npm_audit_summary_path,
        database_readiness_summary_path=database_readiness_summary_path,
        database_load_smoke_summary_path=database_load_smoke_summary_path,
        reader_quality_sample_summary_path=reader_quality_sample_summary_path,
        launch_week_monitoring_summary_path=launch_week_monitoring_summary_path,
    )
    lanes = [
        _lane_a(base_dir, require_remote_reader_quality=remote_only),
        _lane_c(base_dir, remote_only=remote_only),
        _lane_f(base_dir, runtime_evidence),
        _lane_b(base_dir),
        _lane_d(base_dir),
    ]
    lane_statuses = {lane["lane"]: lane["status"] for lane in lanes}
    blockers = [
        {
            "lane": lane["lane"],
            "task": lane["task"],
            "key": blocker.get("key"),
            "severity": blocker.get("severity"),
            "detail": blocker.get("detail"),
        }
        for lane in lanes
        for blocker in lane.get("blockers", [])
    ]
    blockers.extend(
        {
            "lane": "F",
            "task": "6.10" if str(blocker.get("key") or "").startswith("public_beta_database") else "6.9",
            "key": blocker.get("key"),
            "severity": blocker.get("severity"),
            "detail": blocker.get("detail"),
        }
        for blocker in remote_vercel_acceptance.get("blockers", [])
    )
    ready = all(lane["ready"] for lane in lanes) and bool(remote_vercel_acceptance.get("ready", True))
    return {
        "schema_version": "paid_pilot_acceptance/v1",
        "generated_at": _utc_now(),
        "target": "controlled_paid_pilot",
        "ready": ready,
        "status": "passed" if ready else "blocked",
        "lane_statuses": lane_statuses,
        "lanes": lanes,
        "blockers": blockers,
        "acceptance_contract": {
            "public_self_serve_launch": False,
            "requires_live_stripe_keys": False,
            "requires_redacted_live_payment_refs": True,
            "invite_only_checkout_supported": True,
            "executes_production_restore": False,
            "commercial_ready_source": "formal_domain_remote" if remote_only else "local_dev",
            "formal_domain": FORMAL_PILOT_DOMAIN if remote_only else None,
            "local_manual_ports": {"frontend": 3000, "backend": 8000},
        },
        "runtime_pilot_evidence": runtime_evidence,
        "remote_vercel_acceptance": remote_vercel_acceptance,
    }


def render_lane_markdown(lane: Dict[str, Any]) -> str:
    lines = [
        f"# Lane {lane.get('lane')} Task {lane.get('task')}: {lane.get('title')}",
        "",
        f"- status: {lane.get('status')}",
        f"- ready: {'yes' if lane.get('ready') else 'no'}",
        "",
        "## Evidence",
    ]
    for key, value in dict(lane.get("evidence") or {}).items():
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Blockers"])
    blockers = list(lane.get("blockers") or [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker.get('key')}: {blocker.get('detail')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts"])
    for artifact in lane.get("artifacts", []):
        lines.append(f"- {artifact.get('path')}: {'present' if artifact.get('exists') else 'missing'}")
    lines.append("")
    return "\n".join(lines)


def render_paid_pilot_markdown(summary: Dict[str, Any], *, customer_packet: bool = False) -> str:
    title = "Paid Pilot Customer Signoff Packet" if customer_packet else "Paid Pilot Acceptance Report"
    lines = [
        f"# {title}",
        "",
        f"- generated at: {summary.get('generated_at')}",
        f"- target: {summary.get('target')}",
        f"- status: {summary.get('status')}",
        f"- ready: {'yes' if summary.get('ready') else 'no'}",
        "- scope: controlled paid pilot, not public self-serve launch",
        "- local payment execution: sandbox/test provider only; invite-only live cutover requires redacted operator refs and external live secrets",
        "- production restore: request/approval evidence only, no automatic restore",
        f"- public app url: {dict(summary.get('remote_vercel_acceptance') or {}).get('public_app_url') or 'not provided'}",
        f"- vercel deployment id: {dict(summary.get('remote_vercel_acceptance') or {}).get('vercel_deployment_id') or 'not provided'}",
        f"- commercial ready source: {dict(summary.get('acceptance_contract') or {}).get('commercial_ready_source') or 'not provided'}",
        "",
        "## Lane Status",
    ]
    for lane in summary.get("lanes", []):
        lines.append(f"- Lane {lane.get('lane')} Task {lane.get('task')}: {lane.get('status')} ({lane.get('title')})")
    lines.extend(["", "## Blocking Items"])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- Lane {blocker.get('lane')} {blocker.get('key')}: {blocker.get('detail')}")
    else:
        lines.append("- none")
    if not customer_packet:
        remote = dict(summary.get("remote_vercel_acceptance") or {})
        lines.extend(
            [
                "",
                "## Remote Vercel Acceptance",
                f"- status: {remote.get('status')}",
                f"- public_app_url: {remote.get('public_app_url')}",
                f"- vercel_domain: {remote.get('vercel_domain')}",
                f"- vercel_deployment_id: {remote.get('vercel_deployment_id')}",
                f"- remote_smoke: {json.dumps(remote.get('remote_smoke') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- reader_quality_sample: {json.dumps(remote.get('reader_quality_sample') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- reader_paid_path: {json.dumps(remote.get('reader_paid_path') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- author_approval: {json.dumps(remote.get('author_approval') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- ops_remote_smoke: {json.dumps(remote.get('ops_remote_smoke') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- performance: {json.dumps(remote.get('performance') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- npm_audit: {json.dumps(remote.get('npm_audit') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- database_readiness: {json.dumps(remote.get('database_readiness') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- database_load_smoke: {json.dumps(remote.get('database_load_smoke') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- launch_week_monitoring: {json.dumps(remote.get('launch_week_monitoring') or {}, ensure_ascii=False, sort_keys=True)}",
            ]
        )
        lines.extend(["", "## Evidence Details"])
        for lane in summary.get("lanes", []):
            lines.append("")
            lines.append(f"### Lane {lane.get('lane')}")
            for key, value in dict(lane.get("evidence") or {}).items():
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines.append("")
    return "\n".join(lines)


def write_paid_pilot_acceptance(
    *,
    base_dir: Path,
    output_dir: Optional[Path] = None,
    health_url: str = "http://127.0.0.1:8000/health",
    public_app_url: Optional[str] = None,
    vercel_deployment_id: Optional[str] = None,
    vercel_domain: Optional[str] = None,
    remote_smoke_summary_path: Optional[str] = None,
    reader_paid_path_summary_path: Optional[str] = None,
    author_approval_summary_path: Optional[str] = None,
    ops_remote_smoke_summary_path: Optional[str] = None,
    vercel_performance_summary_path: Optional[str] = None,
    npm_audit_summary_path: Optional[str] = None,
    database_readiness_summary_path: Optional[str] = None,
    database_load_smoke_summary_path: Optional[str] = None,
    reader_quality_sample_summary_path: Optional[str] = None,
    launch_week_monitoring_summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    output = output_dir or base_dir / "artifacts/paid_pilot_acceptance/latest"
    output.mkdir(parents=True, exist_ok=True)
    summary = build_paid_pilot_acceptance(
        base_dir=base_dir,
        health_url=health_url,
        public_app_url=public_app_url,
        vercel_deployment_id=vercel_deployment_id,
        vercel_domain=vercel_domain,
        remote_smoke_summary_path=remote_smoke_summary_path,
        reader_paid_path_summary_path=reader_paid_path_summary_path,
        author_approval_summary_path=author_approval_summary_path,
        ops_remote_smoke_summary_path=ops_remote_smoke_summary_path,
        vercel_performance_summary_path=vercel_performance_summary_path,
        npm_audit_summary_path=npm_audit_summary_path,
        database_readiness_summary_path=database_readiness_summary_path,
        database_load_smoke_summary_path=database_load_smoke_summary_path,
        reader_quality_sample_summary_path=reader_quality_sample_summary_path,
        launch_week_monitoring_summary_path=launch_week_monitoring_summary_path,
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (output / "report.md").write_text(render_paid_pilot_markdown(summary), encoding="utf-8")
    (output / "customer_signoff_packet.md").write_text(
        render_paid_pilot_markdown(summary, customer_packet=True),
        encoding="utf-8",
    )

    for lane in summary.get("lanes", []):
        lane_code = str(lane.get("lane") or "")
        lane_dir = base_dir / LANE_OUTPUT_DIRS.get(lane_code, Path("artifacts/paid_pilot_acceptance/latest"))
        lane_dir.mkdir(parents=True, exist_ok=True)
        (lane_dir / "summary.json").write_text(json.dumps(lane, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        (lane_dir / "report.md").write_text(render_lane_markdown(lane), encoding="utf-8")
    runtime_dir = base_dir / LANE_OUTPUT_DIRS["F"]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime = dict(summary.get("runtime_pilot_evidence") or {})
    (runtime_dir / "runtime_evidence.json").write_text(json.dumps(runtime, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return summary
