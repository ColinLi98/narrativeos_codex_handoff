from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


class RemoteShippingAdapter(Protocol):
    adapter_name: str

    def describe(self) -> Dict[str, Any]:
        ...

    def probe(self) -> Dict[str, Any]:
        ...

    def ship(
        self,
        *,
        job_id: str,
        items: List[Dict[str, Any]],
        remote_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        ...


class NotificationSinkAdapter(Protocol):
    sink_name: str

    def describe(self) -> Dict[str, Any]:
        ...

    def probe(self) -> Dict[str, Any]:
        ...

    def notify(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        ...


class RetryPolicyRegistry:
    def __init__(self, *, default_policy_id: str) -> None:
        self.default_policy_id = default_policy_id
        self._policies: Dict[str, Dict[str, Any]] = {}

    def register(self, policy_id: str, payload: Dict[str, Any]) -> None:
        self._policies[policy_id] = {"policy_id": policy_id, **payload}

    def get(self, policy_id: Optional[str] = None) -> Dict[str, Any]:
        target = policy_id or self.default_policy_id
        if target not in self._policies:
            raise KeyError(f"unknown_retry_policy:{target}")
        return dict(self._policies[target])

    def resolve_notification_policy(self, sink_name: Optional[str] = None) -> Dict[str, Any]:
        if sink_name:
            candidate = f"notification:{sink_name}"
            if candidate in self._policies:
                return self.get(candidate)
        return self.get(self.default_policy_id)

    def summary(self) -> Dict[str, Any]:
        return {
            "default_policy_id": self.default_policy_id,
            "available_policy_ids": list(self._policies.keys()),
            "policies": {policy_id: dict(payload) for policy_id, payload in self._policies.items()},
        }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_adapter_failure(error: Exception) -> Dict[str, Any]:
    message = str(error).lower()
    failure_class = "unknown"
    retryable = True

    if isinstance(error, KeyError):
        failure_class = "configuration"
        retryable = False
    elif isinstance(error, PermissionError):
        failure_class = "permission"
        retryable = False
    elif isinstance(error, FileNotFoundError):
        failure_class = "missing_resource"
        retryable = False
    elif isinstance(error, TimeoutError):
        failure_class = "timeout"
        retryable = True
    elif isinstance(error, ConnectionError):
        failure_class = "transient_io"
        retryable = True
    elif isinstance(error, OSError):
        if getattr(error, "errno", None) in {11, 110, 111}:
            failure_class = "transient_io"
            retryable = True
        elif getattr(error, "errno", None) == 13:
            failure_class = "permission"
            retryable = False
        else:
            failure_class = "os_error"
            retryable = True
    elif "rate limit" in message or "429" in message:
        failure_class = "rate_limited"
        retryable = True
    elif "timeout" in message:
        failure_class = "timeout"
        retryable = True
    elif "not implemented" in message or isinstance(error, NotImplementedError):
        failure_class = "unsupported"
        retryable = False
    elif "config" in message or "invalid" in message:
        failure_class = "configuration"
        retryable = False

    return {
        "failure_class": failure_class,
        "retryable": retryable,
        "message": str(error),
    }


class LocalMirrorRemoteShippingAdapter:
    adapter_name = "local_mirror"

    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def describe(self) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "kind": "filesystem_stub",
            "base_dir": str(self.base_dir),
        }

    def probe(self) -> Dict[str, Any]:
        issues: List[str] = []
        base_dir = self.base_dir
        if not base_dir.is_absolute():
            issues.append("base_dir_not_absolute")
        exists = base_dir.exists()
        if exists:
            writable = os.access(base_dir, os.W_OK)
            if not writable:
                issues.append("base_dir_not_writable")
        else:
            writable = base_dir.parent.exists() and os.access(base_dir.parent, os.W_OK)
            if not writable:
                issues.append("parent_not_writable")
        status = "pass" if not issues else "fail"
        return {
            "adapter_name": self.adapter_name,
            "status": status,
            "issues": issues,
            "base_dir": str(base_dir),
            "exists": exists,
            "writable": writable,
        }

    def ship(
        self,
        *,
        job_id: str,
        items: List[Dict[str, Any]],
        remote_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        target_root = Path(remote_dir) if remote_dir else (self.base_dir / job_id)
        shipped_items: List[Dict[str, Any]] = []
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)
        for item in items:
            source = Path(str(item.get("source_path") or ""))
            if not source.exists():
                continue
            target = target_root / f"{str(item.get('label') or 'artifact').replace(':', '_')}__{source.name}"
            shipped_items.append(
                {
                    **item,
                    "target_path": str(target),
                }
            )
            if dry_run:
                continue
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        manifest = {
            "generated_at": _utcnow(),
            "adapter_name": self.adapter_name,
            "job_id": job_id,
            "dry_run": dry_run,
            "target_root": str(target_root),
            "shipped_items": shipped_items,
        }
        manifest_path = target_root / "shipping_manifest.json"
        if not dry_run:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "adapter_name": self.adapter_name,
            "dry_run": dry_run,
            "remote_dir": str(target_root),
            "remote_manifest_path": str(manifest_path),
            "shipped_item_count": len(shipped_items),
            "shipped_items": shipped_items,
        }


class NoopRemoteShippingAdapter:
    adapter_name = "noop"

    def describe(self) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "kind": "noop",
        }

    def probe(self) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "status": "pass",
            "issues": [],
            "kind": "noop",
        }

    def ship(
        self,
        *,
        job_id: str,
        items: List[Dict[str, Any]],
        remote_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "dry_run": True,
            "remote_dir": remote_dir or "",
            "remote_manifest_path": "",
            "shipped_item_count": len(items),
            "shipped_items": items,
        }


class FileNotificationSinkAdapter:
    sink_name = "file"

    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def describe(self) -> Dict[str, Any]:
        return {
            "sink_name": self.sink_name,
            "kind": "json_file_stub",
            "base_dir": str(self.base_dir),
        }

    def probe(self) -> Dict[str, Any]:
        issues: List[str] = []
        base_dir = self.base_dir
        if not base_dir.is_absolute():
            issues.append("base_dir_not_absolute")
        exists = base_dir.exists()
        if exists:
            writable = os.access(base_dir, os.W_OK)
            if not writable:
                issues.append("base_dir_not_writable")
        else:
            writable = base_dir.parent.exists() and os.access(base_dir.parent, os.W_OK)
            if not writable:
                issues.append("parent_not_writable")
        status = "pass" if not issues else "fail"
        return {
            "sink_name": self.sink_name,
            "status": status,
            "issues": issues,
            "base_dir": str(base_dir),
            "exists": exists,
            "writable": writable,
        }

    def notify(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        notification_id = f"notify_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        target_dir = self.base_dir
        target_path = target_dir / f"{notification_id}.json"
        receipt = {
            "notification_id": notification_id,
            "sink_name": self.sink_name,
            "event_type": event_type,
            "dry_run": dry_run,
            "target_path": str(target_path),
            "status": "planned" if dry_run else "sent",
            "generated_at": _utcnow(),
        }
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                json.dumps({"receipt": receipt, "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return receipt


class EmailNotificationSinkAdapter:
    sink_name = "email"

    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def describe(self) -> Dict[str, Any]:
        return {
            "sink_name": self.sink_name,
            "kind": "email_stub",
            "base_dir": str(self.base_dir),
        }

    def probe(self) -> Dict[str, Any]:
        return FileNotificationSinkAdapter(base_dir=self.base_dir).probe() | {"sink_name": self.sink_name, "kind": "email_stub"}

    def notify(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        notification_id = f"notify_email_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        target_dir = self.base_dir
        target_path = target_dir / f"{notification_id}.json"
        receipt = {
            "notification_id": notification_id,
            "sink_name": self.sink_name,
            "event_type": event_type,
            "dry_run": dry_run,
            "target_path": str(target_path),
            "status": "planned" if dry_run else "sent",
            "generated_at": _utcnow(),
        }
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                json.dumps({"receipt": receipt, "channel": "email", "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return receipt


class SlackNotificationSinkAdapter:
    sink_name = "slack"

    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def describe(self) -> Dict[str, Any]:
        return {
            "sink_name": self.sink_name,
            "kind": "slack_stub",
            "base_dir": str(self.base_dir),
        }

    def probe(self) -> Dict[str, Any]:
        return FileNotificationSinkAdapter(base_dir=self.base_dir).probe() | {"sink_name": self.sink_name, "kind": "slack_stub"}

    def notify(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        notification_id = f"notify_slack_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        target_dir = self.base_dir
        target_path = target_dir / f"{notification_id}.json"
        receipt = {
            "notification_id": notification_id,
            "sink_name": self.sink_name,
            "event_type": event_type,
            "dry_run": dry_run,
            "target_path": str(target_path),
            "status": "planned" if dry_run else "sent",
            "generated_at": _utcnow(),
        }
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                json.dumps({"receipt": receipt, "channel": "slack", "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return receipt


class NoopNotificationSinkAdapter:
    sink_name = "noop"

    def describe(self) -> Dict[str, Any]:
        return {
            "sink_name": self.sink_name,
            "kind": "noop",
        }

    def probe(self) -> Dict[str, Any]:
        return {
            "sink_name": self.sink_name,
            "status": "pass",
            "issues": [],
            "kind": "noop",
        }

    def notify(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return {
            "notification_id": f"notify_noop_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
            "sink_name": self.sink_name,
            "event_type": event_type,
            "dry_run": True,
            "target_path": "",
            "status": "planned",
            "generated_at": _utcnow(),
        }


class RemoteShippingConfigRegistry:
    def __init__(self, *, default_adapter: str) -> None:
        self.default_adapter = default_adapter
        self._adapters: Dict[str, RemoteShippingAdapter] = {}

    def register(self, adapter: RemoteShippingAdapter) -> None:
        self._adapters[adapter.adapter_name] = adapter

    def get(self, adapter_name: Optional[str] = None) -> RemoteShippingAdapter:
        target = adapter_name or self.default_adapter
        if target not in self._adapters:
            raise KeyError(f"unknown_remote_shipping_adapter:{target}")
        return self._adapters[target]

    def summary(self) -> Dict[str, Any]:
        return {
            "default_adapter": self.default_adapter,
            "available_adapters": list(self._adapters.keys()),
            "descriptions": {name: adapter.describe() for name, adapter in self._adapters.items()},
        }

    def probe_all(self) -> Dict[str, Any]:
        probes = {name: adapter.probe() for name, adapter in self._adapters.items()}
        default_probe = probes.get(self.default_adapter)
        return {
            **self.summary(),
            "probes": probes,
            "default_probe": default_probe,
        }


class NotificationSinkRegistry:
    def __init__(self, *, default_sink: str) -> None:
        self.default_sink = default_sink
        self._sinks: Dict[str, NotificationSinkAdapter] = {}

    def register(self, sink: NotificationSinkAdapter) -> None:
        self._sinks[sink.sink_name] = sink

    def get(self, sink_name: Optional[str] = None) -> NotificationSinkAdapter:
        target = sink_name or self.default_sink
        if target not in self._sinks:
            raise KeyError(f"unknown_notification_sink:{target}")
        return self._sinks[target]

    def summary(self) -> Dict[str, Any]:
        return {
            "default_sink": self.default_sink,
            "available_sinks": list(self._sinks.keys()),
            "descriptions": {name: sink.describe() for name, sink in self._sinks.items()},
        }

    def probe_all(self) -> Dict[str, Any]:
        probes = {name: sink.probe() for name, sink in self._sinks.items()}
        default_probe = probes.get(self.default_sink)
        return {
            **self.summary(),
            "probes": probes,
            "default_probe": default_probe,
        }


def build_remote_shipping_registry(base_dir: Path) -> RemoteShippingConfigRegistry:
    shipping_root = Path(os.getenv("NARRATIVEOS_ASYNC_REMOTE_BASE_DIR", str(base_dir / "artifacts" / "async_job_remote_shipments")))
    default_adapter = os.getenv("NARRATIVEOS_ASYNC_REMOTE_PROVIDER", "local_mirror")
    registry = RemoteShippingConfigRegistry(default_adapter=default_adapter)
    registry.register(LocalMirrorRemoteShippingAdapter(base_dir=shipping_root))
    registry.register(NoopRemoteShippingAdapter())
    return registry


def build_notification_sink_registry(base_dir: Path) -> NotificationSinkRegistry:
    sink_root = Path(os.getenv("NARRATIVEOS_ASYNC_NOTIFICATION_BASE_DIR", str(base_dir / "artifacts" / "async_job_notifications")))
    default_sink = os.getenv("NARRATIVEOS_ASYNC_NOTIFICATION_SINK", "file")
    registry = NotificationSinkRegistry(default_sink=default_sink)
    registry.register(FileNotificationSinkAdapter(base_dir=sink_root))
    registry.register(EmailNotificationSinkAdapter(base_dir=sink_root / "email"))
    registry.register(SlackNotificationSinkAdapter(base_dir=sink_root / "slack"))
    registry.register(NoopNotificationSinkAdapter())
    return registry


def build_retry_policy_registry() -> RetryPolicyRegistry:
    registry = RetryPolicyRegistry(default_policy_id="notification:default")
    registry.register(
        "notification:default",
        {
            "scope": "notification_retry",
            "max_attempts": 3,
            "backoff_seconds": 60,
            "retryable_failure_classes": ["transient_io", "timeout", "rate_limited", "unknown", "os_error"],
            "terminal_failure_classes": ["configuration", "permission", "missing_resource", "unsupported"],
        },
    )
    registry.register(
        "notification:file",
        {
            "scope": "notification_retry",
            "max_attempts": 2,
            "backoff_seconds": 15,
            "retryable_failure_classes": ["os_error", "transient_io"],
            "terminal_failure_classes": ["configuration", "permission", "missing_resource", "unsupported"],
        },
    )
    registry.register(
        "notification:noop",
        {
            "scope": "notification_retry",
            "max_attempts": 1,
            "backoff_seconds": 0,
            "retryable_failure_classes": [],
            "terminal_failure_classes": ["unsupported"],
        },
    )
    registry.register(
        "notification:email",
        {
            "scope": "notification_retry",
            "max_attempts": 2,
            "backoff_seconds": 30,
            "retryable_failure_classes": ["os_error", "transient_io"],
            "terminal_failure_classes": ["configuration", "permission", "missing_resource", "unsupported"],
        },
    )
    registry.register(
        "notification:slack",
        {
            "scope": "notification_retry",
            "max_attempts": 2,
            "backoff_seconds": 30,
            "retryable_failure_classes": ["os_error", "transient_io", "timeout"],
            "terminal_failure_classes": ["configuration", "permission", "missing_resource", "unsupported"],
        },
    )
    return registry
