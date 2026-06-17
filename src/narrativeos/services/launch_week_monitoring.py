from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .async_jobs import AsyncJobService
from .observability import ObservabilityService
from .ops_quality_projection import OpsQualityProjectionService
from .reader_generation_jobs import READER_GENERATION_JOB_TYPE
from ..persistence.repositories import SQLAlchemyPlatformRepository


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = "launch_week_monitoring/v1"
DEFAULT_PUBLIC_APP_URL = "https://pilot.lixidol.com"
DEFAULT_PROBE_ENDPOINTS = [
    "/health",
    "/api/v1/health",
    "/api/v1/story/import/public-works",
    "/showcase",
    "/story",
]
PILOT_ACCOUNT_STATUSES = {"trial", "active", "paused", "renewal_due"}
PILOT_TRACK_STATUSES = {"watch", "ready_for_conversion", "converted"}
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:postgres(?:ql)?|mysql|sqlite)://[^\s\"']+", re.IGNORECASE),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bvercel_[A-Za-z0-9]{20,}\b", re.IGNORECASE),
    re.compile(r"\bVERCEL_TOKEN\b", re.IGNORECASE),
    re.compile(r"\b(?:DATABASE_URL|COOKIE|SET_COOKIE|ACCESS_TOKEN|REFRESH_TOKEN)\b", re.IGNORECASE),
]


class LaunchWeekMonitoringService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        observability_service: ObservabilityService,
        async_job_service: Optional[AsyncJobService] = None,
        quality_projection_service: Optional[OpsQualityProjectionService] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.repository = repository
        self.observability = observability_service
        self.async_jobs = async_job_service
        self.quality_projection = quality_projection_service
        self.base_dir = Path(base_dir or ROOT)

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _within_window(self, item: Dict[str, Any], *, since: datetime, keys: Sequence[str]) -> bool:
        for key in keys:
            parsed = self._parse_timestamp(item.get(key))
            if parsed is not None and parsed >= since:
                return True
        return False

    def _threshold(self, env_key: str, default: int) -> int:
        try:
            return max(0, int(os.getenv(env_key, str(default))))
        except ValueError:
            return default

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _percentile(self, values: Sequence[float], percentile: float) -> Optional[float]:
        cleaned = sorted(float(value) for value in values)
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return round(cleaned[0], 3)
        rank = max(0.0, min(1.0, percentile)) * float(len(cleaned) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(cleaned) - 1)
        fraction = rank - lower
        return round(cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction, 3)

    def _redact_ref(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if len(raw) <= 10:
            return f"{raw[:3]}…"
        return f"{raw[:6]}…{raw[-4:]}"

    def _redact_refs(self, refs: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
        redacted = []
        for item in refs:
            kind = str(item.get("kind") or "ref")
            value = str(item.get("id") or "").strip()
            if not value:
                continue
            redacted.append({"kind": kind, "id_ref": self._redact_ref(value)})
        return redacted

    def _is_smoke_or_test_account(self, item: Dict[str, Any]) -> bool:
        metadata = dict(item.get("metadata_json") or item.get("track_payload_json") or {})
        account_id = str(item.get("account_id") or "").lower()
        display_name = str(item.get("display_name") or "").lower()
        values = " ".join(
            [
                account_id,
                display_name,
                json.dumps(metadata, ensure_ascii=False, default=str).lower(),
            ]
        )
        smoke_markers = {
            "smoke",
            "smoke_run",
            "remote_smoke",
            "ci_headless",
            "test_account",
            "qa_account",
        }
        return any(marker in values for marker in smoke_markers)

    def resolve_invited_pilot_cohort(self, *, limit: int = 1000) -> Dict[str, Any]:
        customers = self.repository.list_customer_accounts(limit=limit)
        tracks = self.repository.list_pilot_conversion_tracks(limit=limit)
        account_ids: set[str] = set()
        source_counts = {"customer_account": 0, "pilot_conversion_track": 0}
        excluded_smoke_count = 0

        for item in customers:
            if self._is_smoke_or_test_account(item):
                excluded_smoke_count += 1
                continue
            if str(item.get("status") or "") in PILOT_ACCOUNT_STATUSES and str(item.get("account_id") or "").strip():
                account_ids.add(str(item["account_id"]))
                source_counts["customer_account"] += 1

        for item in tracks:
            if self._is_smoke_or_test_account(item):
                excluded_smoke_count += 1
                continue
            if str(item.get("status") or "") in PILOT_TRACK_STATUSES and str(item.get("account_id") or "").strip():
                account_ids.add(str(item["account_id"]))
                source_counts["pilot_conversion_track"] += 1

        sorted_ids = sorted(account_ids)
        return {
            "account_ids": sorted_ids,
            "account_refs": [{"kind": "account", "id": item} for item in sorted_ids],
            "account_count": len(sorted_ids),
            "source_counts": source_counts,
            "excluded_smoke_count": excluded_smoke_count,
        }

    def _signal_payload(
        self,
        *,
        signal_key: str,
        count: int,
        threshold: int,
        refs: Optional[List[Dict[str, Any]]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        breached = count > threshold
        return {
            "signal_key": signal_key,
            "count": count,
            "threshold": threshold,
            "status": "alert" if breached else "ok",
            "breached": breached,
            "refs": list(refs or []),
            "details": dict(details or {}),
        }

    def _runtime_receipts_for_accounts(
        self,
        *,
        account_ids: set[str],
        since: datetime,
        limit: int,
    ) -> List[Dict[str, Any]]:
        receipts: List[Dict[str, Any]] = []
        for account_id in sorted(account_ids):
            for item in self.observability.list_runtime_receipts(account_id=account_id, incident_only=True, limit=limit):
                if not self._within_window(item, since=since, keys=("occurred_at", "generated_at")):
                    continue
                surface = str(item.get("surface") or "").lower()
                action = str(item.get("action") or "").lower()
                if surface in {"reader", "story", "reader_shell"} or any(
                    marker in action for marker in ("reader", "story", "continue", "choice", "import")
                ):
                    receipts.append(item)
        return receipts

    def _remote_generation_signal(self, *, account_ids: set[str], since: datetime) -> Dict[str, Any]:
        refs: List[Dict[str, Any]] = []
        by_reason: Dict[str, int] = {}
        failed_jobs: List[Dict[str, Any]] = []
        stale_jobs: List[Dict[str, Any]] = []
        if self.async_jobs is not None:
            for job in self.async_jobs.list_jobs(job_type=READER_GENERATION_JOB_TYPE, limit=1000):
                if str(job.get("account_id") or "") not in account_ids:
                    continue
                if not self._within_window(job, since=since, keys=("finished_at", "updated_at", "created_at", "started_at")):
                    continue
                status = str(job.get("status") or "")
                if status == "failed":
                    failed_jobs.append(job)
                    by_reason["async_job_failed"] = by_reason.get("async_job_failed", 0) + 1
                    refs.append({"kind": "account", "id": job.get("account_id")})
                    refs.append({"kind": "async_job", "id": job.get("job_id")})
                elif status == "running" and str(job.get("lease_status") or "") in {"expired", "missing"}:
                    stale_jobs.append(job)
                    by_reason["async_job_stale_running"] = by_reason.get("async_job_stale_running", 0) + 1
                    refs.append({"kind": "account", "id": job.get("account_id")})
                    refs.append({"kind": "async_job", "id": job.get("job_id")})
        receipts = self._runtime_receipts_for_accounts(account_ids=account_ids, since=since, limit=100)
        for receipt in receipts:
            for flag in list(receipt.get("incident_flags") or []):
                by_reason[str(flag)] = by_reason.get(str(flag), 0) + 1
            refs.append({"kind": "account", "id": receipt.get("account_id") or receipt.get("reader_id")})
            refs.append({"kind": "runtime_receipt", "id": receipt.get("event_id")})

        count = len(failed_jobs) + len(stale_jobs) + len(receipts)
        return self._signal_payload(
            signal_key="remote_generation_failures",
            count=count,
            threshold=self._threshold("NARRATIVEOS_LAUNCH_ALERT_REMOTE_GENERATION_FAILURE_THRESHOLD", 0),
            refs=refs,
            details={
                "failed_job_count": len(failed_jobs),
                "stale_running_job_count": len(stale_jobs),
                "runtime_incident_count": len(receipts),
                "by_reason": by_reason,
            },
        )

    def _checkout_signal(self, *, account_ids: set[str], since: datetime) -> Dict[str, Any]:
        failed_statuses = {"failed", "expired", "canceled", "cancelled", "blocked", "error"}
        successful_statuses = {"fulfilled", "completed", "complete", "paid", "active"}
        now = datetime.now(timezone.utc)
        checkout_failures = []
        for item in self.repository.list_billing_checkout_sessions(limit=1000):
            if str(item.get("account_id") or "") not in account_ids:
                continue
            if not self._within_window(item, since=since, keys=("updated_at", "created_at", "expires_at")):
                continue
            status = str(item.get("status") or "").lower()
            expires_at = self._parse_timestamp(item.get("expires_at"))
            if status in failed_statuses or (expires_at is not None and expires_at <= now and status not in successful_statuses):
                checkout_failures.append(item)

        payment_failures = [
            item
            for item in self.repository.list_payment_transactions(status="failed", limit=1000)
            if str(item.get("account_id") or "") in account_ids
            and self._within_window(item, since=since, keys=("occurred_at", "created_at"))
        ]
        refs = [
            *[{"kind": "account", "id": item.get("account_id")} for item in checkout_failures + payment_failures],
            *[{"kind": "checkout_session", "id": item.get("checkout_session_id")} for item in checkout_failures],
            *[{"kind": "payment_transaction", "id": item.get("payment_transaction_id")} for item in payment_failures],
        ]
        return self._signal_payload(
            signal_key="checkout_failures",
            count=len(checkout_failures) + len(payment_failures),
            threshold=self._threshold("NARRATIVEOS_LAUNCH_ALERT_CHECKOUT_FAILURE_THRESHOLD", 0),
            refs=refs,
            details={
                "checkout_session_failure_count": len(checkout_failures),
                "payment_transaction_failure_count": len(payment_failures),
                "checkout_status_counts": dict(Counter(str(item.get("status") or "unknown") for item in checkout_failures)),
            },
        )

    def _support_signal(self, *, account_ids: set[str], since: datetime) -> Dict[str, Any]:
        open_cases = [
            item
            for item in self.repository.list_support_cases(limit=1000)
            if str(item.get("account_id") or "") in account_ids
            and str(item.get("status") or "") in {"open", "in_progress"}
            and self._within_window(item, since=since, keys=("updated_at", "created_at"))
        ]
        high_cases = [item for item in open_cases if str(item.get("priority") or "").lower() == "high"]
        refs = [
            *[{"kind": "account", "id": item.get("account_id")} for item in high_cases or open_cases],
            *[{"kind": "support_case", "id": item.get("support_case_id")} for item in high_cases or open_cases],
        ]
        return self._signal_payload(
            signal_key="support_cases",
            count=len(high_cases),
            threshold=self._threshold("NARRATIVEOS_LAUNCH_ALERT_HIGH_SUPPORT_CASE_THRESHOLD", 0),
            refs=refs,
            details={
                "open_or_in_progress_count": len(open_cases),
                "high_priority_count": len(high_cases),
                "priority_counts": dict(Counter(str(item.get("priority") or "unknown") for item in open_cases)),
            },
        )

    def _quality_signal(self, *, account_ids: set[str], since: datetime) -> Dict[str, Any]:
        blocked: List[Dict[str, Any]] = []
        review_required: List[Dict[str, Any]] = []
        if self.quality_projection is not None:
            for account_id in sorted(account_ids):
                events = self.quality_projection.list_projected_quality_events(account_id=account_id, limit=200)
                for event in events:
                    if not self._within_window(event, since=since, keys=("created_at",)):
                        continue
                    status = str(event.get("status") or "")
                    if status == "blocked":
                        blocked.append(event)
                    elif status == "review_required":
                        review_required.append(event)
        else:
            events = self.repository.list_quality_events(limit=1000)
            for event in events:
                if not self._within_window(event, since=since, keys=("created_at",)):
                    continue
                source_ref = dict(event.get("source_ref") or {})
                if str(source_ref.get("account_id") or "") not in account_ids:
                    continue
                status = str(event.get("status") or "")
                if status == "blocked":
                    blocked.append(event)
                elif status == "review_required":
                    review_required.append(event)

        refs = [
            *[{"kind": "account", "id": item.get("account_id")} for item in blocked],
            *[{"kind": "quality_event", "id": item.get("event_id")} for item in blocked],
        ]
        return self._signal_payload(
            signal_key="quality_blocks",
            count=len(blocked),
            threshold=self._threshold("NARRATIVEOS_LAUNCH_ALERT_QUALITY_BLOCK_THRESHOLD", 0),
            refs=refs,
            details={
                "blocked_count": len(blocked),
                "review_required_count": len(review_required),
                "reason_counts": dict(Counter(reason for item in blocked + review_required for reason in list(item.get("reason_codes") or []))),
            },
        )

    def _load_performance_summary(self, performance_summary_path: Optional[str]) -> Dict[str, Any]:
        path = Path(performance_summary_path or self.base_dir / "artifacts" / "vercel_remote_acceptance" / "latest" / "performance.json")
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.exists():
            return {"status": "missing", "measurements": [], "cold_start_5xx_count": 0}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"status": "invalid_json", "measurements": [], "cold_start_5xx_count": 0}

    def _read_json_artifact(self, relative_path: str) -> Dict[str, Any]:
        path = self.base_dir / relative_path
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _resolve_deployment_id(self, explicit: Optional[str]) -> Optional[str]:
        if explicit:
            return explicit
        env_value = str(os.getenv("VERCEL_DEPLOYMENT_ID") or os.getenv("DEPLOYMENT_ID") or "").strip()
        if env_value:
            return env_value
        paid_acceptance = self._read_json_artifact("artifacts/paid_pilot_acceptance/latest/summary.json")
        remote_acceptance = dict(paid_acceptance.get("remote_vercel_acceptance") or {})
        paid_deployment_id = str(remote_acceptance.get("vercel_deployment_id") or "").strip()
        if paid_deployment_id:
            return paid_deployment_id
        domain_binding = self._read_json_artifact("artifacts/vercel_remote_acceptance/latest/domain_binding.json")
        binding_deployment_id = str(domain_binding.get("deployment_id") or "").strip()
        return binding_deployment_id or None

    def _url(self, base_url: str, path: str) -> str:
        return base_url.rstrip("/") + "/" + path.lstrip("/")

    def _timed_get(self, url: str, timeout: float = 20.0) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                response.read(256)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "url": url,
                "status": 0,
                "ok": False,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "error": str(exc),
            }
        return {
            "url": url,
            "status": status,
            "ok": 200 <= status < 400,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    def _vercel_signal(
        self,
        *,
        public_app_url: str,
        performance_summary_path: Optional[str],
        run_probes: bool,
    ) -> Dict[str, Any]:
        performance = self._load_performance_summary(performance_summary_path)
        measurements = list(performance.get("measurements") or [])
        probe_measurements: List[Dict[str, Any]] = []
        if run_probes and public_app_url:
            for endpoint in DEFAULT_PROBE_ENDPOINTS:
                probe_measurements.append(self._timed_get(self._url(public_app_url, endpoint)))
            measurements.extend(probe_measurements)
        durations = [float(item["duration_ms"]) for item in measurements if self._safe_float(item.get("duration_ms")) is not None]
        p95_ms = self._percentile(durations, 0.95)
        five_xx_count = int(performance.get("cold_start_5xx_count") or 0) + sum(
            1 for item in probe_measurements if int(item.get("status") or 0) >= 500
        )
        failed_probe_count = len([item for item in probe_measurements if not item.get("ok")])
        p95_threshold = self._threshold("NARRATIVEOS_LAUNCH_ALERT_COLD_START_P95_MS", 3000)
        five_xx_threshold = self._threshold("NARRATIVEOS_LAUNCH_ALERT_COLD_START_5XX_THRESHOLD", 0)
        breached = five_xx_count > five_xx_threshold or (p95_ms is not None and p95_ms > p95_threshold)
        return {
            "signal_key": "vercel_cold_start_latency",
            "count": five_xx_count,
            "threshold": five_xx_threshold,
            "status": "alert" if breached else "ok",
            "breached": breached,
            "refs": [],
            "details": {
                "public_app_url": public_app_url,
                "performance_summary_status": performance.get("status"),
                "measurement_count": len(measurements),
                "probe_count": len(probe_measurements),
                "failed_probe_count": failed_probe_count,
                "cold_start_5xx_count": five_xx_count,
                "cold_start_5xx_threshold": five_xx_threshold,
                "p95_latency_ms": p95_ms,
                "p95_latency_threshold_ms": p95_threshold,
            },
        }

    def evaluate(
        self,
        *,
        public_app_url: str = DEFAULT_PUBLIC_APP_URL,
        performance_summary_path: Optional[str] = None,
        window_hours: Optional[int] = None,
        run_probes: bool = False,
    ) -> Dict[str, Any]:
        resolved_window_hours = int(window_hours or self._threshold("NARRATIVEOS_LAUNCH_WEEK_WINDOW_HOURS", 24) or 24)
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, resolved_window_hours))
        cohort = self.resolve_invited_pilot_cohort()
        account_ids = set(cohort["account_ids"])
        signals = {
            "remote_generation_failures": self._remote_generation_signal(account_ids=account_ids, since=since),
            "checkout_failures": self._checkout_signal(account_ids=account_ids, since=since),
            "support_cases": self._support_signal(account_ids=account_ids, since=since),
            "quality_blocks": self._quality_signal(account_ids=account_ids, since=since),
            "vercel_cold_start_latency": self._vercel_signal(
                public_app_url=public_app_url,
                performance_summary_path=performance_summary_path,
                run_probes=run_probes,
            ),
        }
        breached = [key for key, value in signals.items() if value.get("breached")]
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self._utcnow(),
            "public_app_url": public_app_url,
            "window_hours": resolved_window_hours,
            "window_start": since.isoformat(),
            "gate_mode": "post_cutover_expansion_guard",
            "ready_to_expand": not breached,
            "status": "ready_to_expand" if not breached else "blocked",
            "cohort": cohort,
            "signals": signals,
            "breached_signals": breached,
        }

    def _alert_from_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not signal.get("breached"):
            return None
        key = str(signal.get("signal_key") or "")
        details = dict(signal.get("details") or {})
        config = {
            "remote_generation_failures": {
                "severity": "high",
                "owner_role": "infra_owner",
                "summary": f"Reader 远端生成失败/队列异常 {signal.get('count') or 0} 次。",
                "recommended_actions": ["inspect_reader_generation_jobs", "resume_or_retry_failed_jobs", "review_runtime_receipts"],
            },
            "checkout_failures": {
                "severity": "high",
                "owner_role": "stripe_owner",
                "summary": f"试点 checkout/payment 失败 {signal.get('count') or 0} 次。",
                "recommended_actions": ["inspect_checkout_sessions", "reconcile_provider_payment", "follow_up_customer"],
            },
            "support_cases": {
                "alert_key": "support_backlog",
                "severity": "high",
                "owner_role": "support_finance_owner",
                "summary": f"高优先级 support case {details.get('high_priority_count') or 0} 条。",
                "recommended_actions": ["assign_case_owner", "inspect_account_workspace", "update_support_case"],
            },
            "quality_blocks": {
                "severity": "high",
                "owner_role": "quality_owner",
                "summary": f"内容质量阻断 {signal.get('count') or 0} 次，需确认未持久化破损章节。",
                "recommended_actions": ["inspect_quality_events", "review_quality_block_reason", "pause_world_if_repeating"],
            },
            "vercel_cold_start_latency": {
                "severity": "critical" if int(details.get("cold_start_5xx_count") or 0) > 0 else "high",
                "owner_role": "infra_owner",
                "summary": f"Vercel cold-start p95={details.get('p95_latency_ms')}ms, 5xx={details.get('cold_start_5xx_count') or 0}。",
                "recommended_actions": ["inspect_vercel_deployment", "measure_remote_performance", "review_function_imports"],
            },
        }.get(key)
        if not config:
            return None
        alert_key = str(config.get("alert_key") or key)
        refs = list(signal.get("refs") or [])
        account_ids = [item.get("id") for item in refs if item.get("kind") == "account" and item.get("id")]
        return {
            "alert_key": alert_key,
            "severity": config["severity"],
            "owner_role": config["owner_role"],
            "count": int(signal.get("count") or 0),
            "summary": config["summary"],
            "account_ids": account_ids,
            "invoice_ids": [],
            "payment_transaction_ids": [item.get("id") for item in refs if item.get("kind") == "payment_transaction" and item.get("id")],
            "webhook_event_ids": [],
            "support_case_ids": [item.get("id") for item in refs if item.get("kind") == "support_case" and item.get("id")],
            "dispute_ids": [],
            "recommended_actions": config["recommended_actions"],
            "drilldown_refs": [
                {"kind": item.get("kind"), "id": item.get("id"), "label": item.get("id")}
                for item in refs[:5]
                if item.get("id")
            ],
            "source": "launch_week_monitoring",
        }

    def current_alert_pack(
        self,
        *,
        public_app_url: str = DEFAULT_PUBLIC_APP_URL,
        performance_summary_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        monitoring = self.evaluate(
            public_app_url=public_app_url,
            performance_summary_path=performance_summary_path,
            run_probes=False,
        )
        alerts = [
            alert
            for alert in (self._alert_from_signal(signal) for signal in monitoring["signals"].values())
            if alert is not None
        ]
        alerts.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item["severity"], 4), item["alert_key"]))
        return {
            "generated_at": monitoring["generated_at"],
            "summary": {
                "ready_to_expand": monitoring["ready_to_expand"],
                "alert_count": len(alerts),
                "by_alert_key": dict(Counter(item["alert_key"] for item in alerts)),
                "by_severity": dict(Counter(item["severity"] for item in alerts)),
                "by_owner_role": dict(Counter(item["owner_role"] for item in alerts)),
            },
            "alerts": alerts,
            "monitoring_summary": {
                "schema_version": monitoring["schema_version"],
                "public_app_url": monitoring["public_app_url"],
                "window_hours": monitoring["window_hours"],
                "cohort_count": monitoring["cohort"]["account_count"],
                "breached_signals": list(monitoring["breached_signals"]),
            },
        }

    def _redacted_monitoring_summary(self, monitoring: Dict[str, Any], *, deployment_id: Optional[str]) -> Dict[str, Any]:
        cohort = dict(monitoring.get("cohort") or {})
        redacted_signals = {}
        for key, signal in dict(monitoring.get("signals") or {}).items():
            redacted_signals[key] = {
                **{k: v for k, v in signal.items() if k != "refs"},
                "refs": self._redact_refs(list(signal.get("refs") or [])),
            }
        return {
            **{k: v for k, v in monitoring.items() if k not in {"cohort", "signals"}},
            "vercel_deployment_id": deployment_id,
            "cohort": {
                **{k: v for k, v in cohort.items() if k not in {"account_ids", "account_refs"}},
                "account_refs": self._redact_refs(list(cohort.get("account_refs") or [])),
            },
            "signals": redacted_signals,
        }

    def secret_scan(self, payload: Dict[str, Any]) -> List[str]:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        issues = []
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(pattern.pattern)
        return issues

    def _report_markdown(self, summary: Dict[str, Any]) -> str:
        lines = [
            "# Launch-Week Remote Monitoring Closure",
            "",
            f"- schema_version: {summary.get('schema_version')}",
            f"- public_app_url: {summary.get('public_app_url')}",
            f"- vercel_deployment_id: {summary.get('vercel_deployment_id') or '-'}",
            f"- window_hours: {summary.get('window_hours')}",
            f"- cohort_count: {dict(summary.get('cohort') or {}).get('account_count') or 0}",
            f"- ready_to_expand: {summary.get('ready_to_expand')}",
            f"- breached_signals: {', '.join(summary.get('breached_signals') or []) or '-'}",
            "",
            "| signal | status | count | threshold | details |",
            "| --- | --- | --- | --- | --- |",
        ]
        for key, signal in dict(summary.get("signals") or {}).items():
            details = dict(signal.get("details") or {})
            detail_bits = []
            for detail_key in (
                "failed_job_count",
                "runtime_incident_count",
                "checkout_session_failure_count",
                "payment_transaction_failure_count",
                "open_or_in_progress_count",
                "high_priority_count",
                "blocked_count",
                "review_required_count",
                "cold_start_5xx_count",
                "p95_latency_ms",
            ):
                if detail_key in details:
                    detail_bits.append(f"{detail_key}={details.get(detail_key)}")
            lines.append(
                f"| {key} | {signal.get('status')} | {signal.get('count')} | {signal.get('threshold')} | {'; '.join(detail_bits) or '-'} |"
            )
        lines.extend(
            [
                "",
                "## Expansion Gate",
                "",
                "This is a post-cutover guard. A red result pauses new invites or pilot expansion, but does not invalidate the already-passed paid-pilot acceptance packet.",
            ]
        )
        return "\n".join(lines)

    def build_monitoring_closure(
        self,
        *,
        public_app_url: str = DEFAULT_PUBLIC_APP_URL,
        performance_summary_path: Optional[str] = None,
        deployment_id: Optional[str] = None,
        window_hours: Optional[int] = None,
        run_probes: bool = True,
        output_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        monitoring = self.evaluate(
            public_app_url=public_app_url,
            performance_summary_path=performance_summary_path,
            window_hours=window_hours,
            run_probes=run_probes,
        )
        resolved_deployment_id = self._resolve_deployment_id(deployment_id)
        summary = self._redacted_monitoring_summary(monitoring, deployment_id=resolved_deployment_id)
        secret_issues = self.secret_scan(summary)
        summary["secret_scan"] = {"passed": not secret_issues, "issue_count": len(secret_issues), "issues": secret_issues}
        if secret_issues:
            raise RuntimeError(f"launch_week_monitoring_secret_scan_failed:{','.join(secret_issues)}")

        run_id = f"launch_week_monitoring_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        bundle_dir = Path(output_root) if output_root else self.base_dir / "artifacts" / "launch_week_monitoring" / run_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        summary_path = bundle_dir / "summary.json"
        report_path = bundle_dir / "report.md"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        report_path.write_text(self._report_markdown(summary).rstrip() + "\n", encoding="utf-8")

        latest_dir = self.base_dir / "artifacts" / "launch_week_monitoring" / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return {
            "status": summary["status"],
            "ready_to_expand": bool(summary["ready_to_expand"]),
            "bundle_dir": str(bundle_dir),
            "latest_dir": str(latest_dir),
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "summary": summary,
        }
