from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Protocol
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlencode, urljoin


REQUIRED_ILLUSTRATION_ENV_KEYS = (
    "OPENAI_API_KEY",
    "NARRATIVEOS_IMAGE_MODEL",
    "NARRATIVEOS_WORLD_BLOB_READ_WRITE_TOKEN",
    "NARRATIVEOS_READER_BLOB_READ_WRITE_TOKEN",
)
def illustration_env_status(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    source = dict(os.environ if env is None else env)
    missing_keys = [
        key
        for key in REQUIRED_ILLUSTRATION_ENV_KEYS
        if not str(source.get(key) or "").strip()
    ]
    vite_api_local = str(source.get("VITE_API_LOCAL") or "").strip().lower() == "true"
    return {
        "required_keys": list(REQUIRED_ILLUSTRATION_ENV_KEYS),
        "missing_keys": missing_keys,
        "vite_api_local": vite_api_local,
        "database_url_present": bool(str(source.get("DATABASE_URL") or "").strip()),
        "ready": not missing_keys and not vite_api_local,
    }


class ReaderIllustrationAcceptanceTransport(Protocol):
    def get_json(self, target: str, *, headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        ...

    def post_json(
        self,
        target: str,
        payload: Mapping[str, Any],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        ...

    def get_binary(self, target: str, *, headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        ...


class UrllibReaderIllustrationAcceptanceTransport:
    def __init__(self, *, base_url: str) -> None:
        self.base_url = str(base_url or "").rstrip("/")

    def _full_url(self, target: str) -> str:
        normalized = str(target or "").strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return normalized
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return urljoin(f"{self.base_url}/", normalized.lstrip("/"))

    def _request(
        self,
        method: str,
        target: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = None
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if payload is not None:
            data = json.dumps(dict(payload)).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        req = urlrequest.Request(
            self._full_url(target),
            data=data,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urlrequest.urlopen(req) as response:  # noqa: S310
                raw_body = response.read()
                status_code = int(response.status)
                response_headers = dict(response.headers.items())
        except urlerror.HTTPError as exc:
            raw_body = exc.read()
            status_code = int(exc.code)
            response_headers = dict(exc.headers.items())
        normalized_headers = {str(key).lower(): value for key, value in response_headers.items()}
        content_type = str(normalized_headers.get("content-type") or "")
        body_json: Any = None
        if raw_body:
            try:
                body_json = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body_json = None
        return {
            "status_code": status_code,
            "headers": response_headers,
            "content_type": content_type,
            "body_json": body_json,
            "body_bytes": raw_body,
        }

    def get_json(self, target: str, *, headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        response = self._request("GET", target, headers=headers)
        return response

    def post_json(
        self,
        target: str,
        payload: Mapping[str, Any],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        response = self._request("POST", target, headers=headers, payload=payload)
        return response

    def get_binary(self, target: str, *, headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        response = self._request("GET", target, headers=headers)
        return response


@dataclass
class ReaderIllustrationAcceptanceConfig:
    backend_url: str = "http://127.0.0.1:8013"
    world_id: str = "jade_court_exam"
    username: Optional[str] = None
    email: Optional[str] = None
    password: str = "secret123"
    timeout_seconds: Optional[float] = None
    cover_timeout_seconds: float = 60.0
    hero_timeout_seconds: float = 180.0
    poll_interval_seconds: float = 1.0


class ReaderIllustrationAcceptanceError(RuntimeError):
    def __init__(self, reason: str, *, summary: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.summary = dict(summary or {})


def _require_http_200(response: Dict[str, Any], *, step: str) -> Dict[str, Any]:
    status_code = int(response.get("status_code") or 0)
    if status_code != 200:
        raise ReaderIllustrationAcceptanceError(f"{step}:http_{status_code}")
    return response


def _require_success_envelope(response: Dict[str, Any], *, step: str) -> Any:
    payload = dict(_require_http_200(response, step=step).get("body_json") or {})
    if int(payload.get("code") or 0) != 200:
        raise ReaderIllustrationAcceptanceError(
            f"{step}:unexpected_envelope:{payload.get('code')}:{payload.get('message')}"
        )
    return payload.get("data")


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _unique_identity(*, username: Optional[str], email: Optional[str]) -> tuple[str, str]:
    if username and email:
        return str(username), str(email)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = str(int(time.time() * 1000))[-6:]
    resolved_username = str(username or f"reader_illustration_{stamp}_{suffix}")
    resolved_email = str(email or f"{resolved_username}@example.com")
    return resolved_username, resolved_email


def _register_quantum_user(
    transport: ReaderIllustrationAcceptanceTransport,
    *,
    username: str,
    email: str,
    password: str,
) -> Dict[str, Any]:
    payload = _require_success_envelope(
        transport.post_json(
            "/api/v1/auth/register",
            {
                "username": username,
                "email": email,
                "password": password,
                "displayName": username,
            },
        ),
        step="auth_register",
    )
    token = str(payload.get("token") or "").strip()
    if not token:
        raise ReaderIllustrationAcceptanceError("auth_register:missing_token")
    return {
        "token": token,
        "user": dict(payload.get("user") or {}),
    }


def _find_public_work(items: list[Dict[str, Any]], *, world_id: str) -> Dict[str, Any]:
    for item in items:
        if str(item.get("worldId") or "").strip() == world_id:
            return item
    raise ReaderIllustrationAcceptanceError(f"public_works:world_missing:{world_id}")


def _effective_timeout(
    *,
    stage_timeout_seconds: float,
    legacy_timeout_seconds: Optional[float],
) -> float:
    if legacy_timeout_seconds is not None:
        return float(legacy_timeout_seconds)
    return float(stage_timeout_seconds)


def _poll_story_session(
    transport: ReaderIllustrationAcceptanceTransport,
    *,
    session_id: str,
    token: str,
    required_field: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> Dict[str, Any]:
    deadline = time.monotonic() + float(timeout_seconds or 0.0)
    latest: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _require_success_envelope(
            transport.get_json(
                f"/api/v1/story/session/{session_id}",
                headers=_auth_headers(token),
            ),
            step=f"story_session:{required_field}",
        )
        if str(latest.get(required_field) or "").strip():
            return {
                "status": "ready",
                "session": latest,
                "required_field": required_field,
            }
        time.sleep(max(0.1, float(poll_interval_seconds or 0.1)))
    return {
        "status": "timeout",
        "session": latest,
        "required_field": required_field,
    }


def _assert_image_response(
    transport: ReaderIllustrationAcceptanceTransport,
    *,
    image_url: str,
    step: str,
) -> Dict[str, Any]:
    normalized = str(image_url or "").strip()
    if not normalized:
        raise ReaderIllustrationAcceptanceError(f"{step}:missing_url")
    response = _require_http_200(transport.get_binary(normalized), step=step)
    content_type = str(response.get("content_type") or "")
    if not content_type.startswith("image/"):
        raise ReaderIllustrationAcceptanceError(f"{step}:unexpected_content_type:{content_type}")
    body_bytes = bytes(response.get("body_bytes") or b"")
    if not body_bytes:
        raise ReaderIllustrationAcceptanceError(f"{step}:empty_body")
    return {
        "url": normalized,
        "content_type": content_type,
        "byte_length": len(body_bytes),
    }


def _story_choice_phase(
    transport: ReaderIllustrationAcceptanceTransport,
    *,
    session_id: str,
    token: str,
    current_node_id: str,
) -> Dict[str, Any]:
    choices = _require_success_envelope(
        transport.get_json(
            f"/api/v1/story/session/{session_id}/choices?{urlencode({'nodeId': current_node_id})}",
            headers=_auth_headers(token),
        ),
        step="story_choices",
    )
    if not choices:
        raise ReaderIllustrationAcceptanceError("story_choices:empty")
    first_choice = dict(list(choices)[0] or {})
    selected_choice_id = str(first_choice.get("id") or "")
    response = transport.post_json(
        "/api/v1/story/choice",
        {
            "sessionId": session_id,
            "choiceId": selected_choice_id,
            "nodeId": str(current_node_id or ""),
        },
        headers=_auth_headers(token),
    )
    status_code = int(response.get("status_code") or 0)
    body_json = dict(response.get("body_json") or {})
    if status_code == 200:
        chosen = dict(body_json.get("data") or {})
        if not str(chosen.get("id") or "").strip():
            raise ReaderIllustrationAcceptanceError("story_choice:missing_new_node")
        return {
            "attempted": True,
            "status": "ok",
            "separate_issue": False,
            "http_status": status_code,
            "selected_choice_id": selected_choice_id,
            "new_node_id": str(chosen.get("id") or ""),
            "quality_gate": None,
            "continuity_contract": None,
        }
    if status_code == 402:
        payload = dict(body_json.get("data") or {})
        return {
            "attempted": True,
            "status": "payment_required",
            "separate_issue": True,
            "http_status": status_code,
            "selected_choice_id": selected_choice_id,
            "new_node_id": None,
            "quality_gate": None,
            "continuity_contract": payload.get("continuityContract"),
        }
    if status_code == 409 and str(body_json.get("message") or "") == "story_reader_quality_guard_failed":
        payload = dict(body_json.get("data") or {})
        return {
            "attempted": True,
            "status": "quality_guard_failed",
            "separate_issue": True,
            "http_status": status_code,
            "selected_choice_id": selected_choice_id,
            "new_node_id": None,
            "quality_gate": payload.get("qualityGate"),
            "continuity_contract": payload.get("continuityContract"),
        }
    raise ReaderIllustrationAcceptanceError(
        f"story_choice:http_{status_code}",
        summary={
            "story_choice": {
                "attempted": True,
                "status": "unexpected_http_error",
                "separate_issue": False,
                "http_status": status_code,
                "selected_choice_id": selected_choice_id,
                "quality_gate": dict((body_json.get("data") or {}).get("qualityGate") or {})
                if isinstance(body_json.get("data"), dict)
                else None,
                "continuity_contract": dict((body_json.get("data") or {}).get("continuityContract") or {})
                if isinstance(body_json.get("data"), dict)
                else None,
            }
        },
    )


def run_reader_illustration_acceptance(
    transport: ReaderIllustrationAcceptanceTransport,
    *,
    config: Optional[ReaderIllustrationAcceptanceConfig] = None,
) -> Dict[str, Any]:
    resolved = config or ReaderIllustrationAcceptanceConfig()
    cover_timeout_seconds = _effective_timeout(
        stage_timeout_seconds=resolved.cover_timeout_seconds,
        legacy_timeout_seconds=resolved.timeout_seconds,
    )
    hero_timeout_seconds = _effective_timeout(
        stage_timeout_seconds=resolved.hero_timeout_seconds,
        legacy_timeout_seconds=resolved.timeout_seconds,
    )
    username, email = _unique_identity(username=resolved.username, email=resolved.email)
    health_response = _require_http_200(
        transport.get_json("/api/v1/health"),
        step="api_health",
    )
    health_payload = dict(health_response.get("body_json") or {})
    if str(health_payload.get("status") or "") != "ok":
        raise ReaderIllustrationAcceptanceError("api_health:status_not_ok")

    public_works_before = _require_success_envelope(
        transport.get_json("/api/v1/story/import/public-works"),
        step="story_import_public_works_before",
    )
    world_before = _find_public_work(
        [dict(item or {}) for item in list(public_works_before or [])],
        world_id=resolved.world_id,
    )

    auth_bundle = _register_quantum_user(
        transport,
        username=username,
        email=email,
        password=resolved.password,
    )
    token = str(auth_bundle["token"])

    launch = _require_success_envelope(
        transport.post_json(
            "/api/v1/story/import/start",
            {"targetType": "world", "targetId": resolved.world_id},
            headers=_auth_headers(token),
        ),
        step="story_import_start",
    )
    session_id = str(launch.get("sessionId") or "").strip()
    world_version_id = str(launch.get("worldVersionId") or "").strip()
    if not session_id:
        raise ReaderIllustrationAcceptanceError("story_import_start:missing_session_id")

    summary: Dict[str, Any] = {
        "healthy": False,
        "illustration_healthy": False,
        "backend_url": str(resolved.backend_url or "").rstrip("/"),
        "world_id": resolved.world_id,
        "world_version_id": world_version_id,
        "username": username,
        "email": email,
        "session_id": session_id,
        "illustration_phase": {
            "status": "running",
            "cover": None,
            "hero": None,
            "library_recent": None,
            "public_works": None,
            "showcase": None,
        },
        "story_choice": {
            "attempted": False,
            "status": "not_attempted",
            "separate_issue": False,
            "http_status": None,
            "selected_choice_id": None,
            "new_node_id": None,
            "quality_gate": None,
            "continuity_contract": None,
        },
        "separate_issues": [],
    }

    cover_poll = _poll_story_session(
        transport,
        session_id=session_id,
        token=token,
        required_field="coverImage",
        timeout_seconds=cover_timeout_seconds,
        poll_interval_seconds=resolved.poll_interval_seconds,
    )
    session_with_cover = dict(cover_poll.get("session") or {})
    if cover_poll.get("status") != "ready":
        summary["illustration_phase"]["status"] = "waiting_on_cover"
        summary["illustration_phase"]["cover"] = {
            "status": "timeout",
            "url": str(session_with_cover.get("coverImage") or ""),
        }
        raise ReaderIllustrationAcceptanceError(
            f"story_session:coverImage:timeout:{session_id}",
            summary=summary,
        )
    session_cover = _assert_image_response(
        transport,
        image_url=str(session_with_cover.get("coverImage") or ""),
        step="session_cover",
    )
    summary["session_cover"] = session_cover
    summary["illustration_phase"]["cover"] = {
        "status": "ready",
        **session_cover,
    }

    hero_poll = _poll_story_session(
        transport,
        session_id=session_id,
        token=token,
        required_field="atmosphereImage",
        timeout_seconds=hero_timeout_seconds,
        poll_interval_seconds=resolved.poll_interval_seconds,
    )
    session_with_hero = dict(hero_poll.get("session") or session_with_cover)
    if hero_poll.get("status") != "ready":
        summary["illustration_phase"]["status"] = "waiting_on_hero"
        summary["illustration_phase"]["hero"] = {
            "status": "timeout",
            "url": str(session_with_hero.get("atmosphereImage") or ""),
        }
        raise ReaderIllustrationAcceptanceError(
            f"story_session:atmosphereImage:timeout:{session_id}",
            summary=summary,
        )
    atmosphere_image = str(session_with_hero.get("atmosphereImage") or "")
    if "/api/v1/media/assets/" not in atmosphere_image:
        summary["illustration_phase"]["status"] = "hero_route_invalid"
        summary["illustration_phase"]["hero"] = {
            "status": "invalid_route",
            "url": atmosphere_image,
        }
        raise ReaderIllustrationAcceptanceError(
            "chapter_hero:expected_private_media_route",
            summary=summary,
        )
    chapter_hero = _assert_image_response(
        transport,
        image_url=atmosphere_image,
        step="chapter_hero",
    )
    summary["chapter_hero"] = chapter_hero
    summary["illustration_phase"]["hero"] = {
        "status": "ready",
        **chapter_hero,
    }

    recent_library_items = _require_success_envelope(
        transport.get_json(
            "/api/v1/library/works?filter=recent",
            headers=_auth_headers(token),
        ),
        step="library_recent",
    )
    library_item = next(
        (
            dict(item or {})
            for item in list(recent_library_items or [])
            if str(item.get("id") or "") == session_id
            or session_id in str(item.get("targetHref") or "")
        ),
        None,
    )
    if library_item is None:
        summary["illustration_phase"]["status"] = "library_recent_missing"
        raise ReaderIllustrationAcceptanceError("library_recent:session_item_missing", summary=summary)
    if not str(library_item.get("coverImage") or "").strip():
        summary["illustration_phase"]["status"] = "library_recent_cover_missing"
        raise ReaderIllustrationAcceptanceError("library_recent:cover_missing", summary=summary)
    summary["library_recent_cover_image"] = str(library_item.get("coverImage") or "")
    summary["illustration_phase"]["library_recent"] = {
        "status": "ready",
        "cover_image": str(library_item.get("coverImage") or ""),
    }

    public_works_after = _require_success_envelope(
        transport.get_json("/api/v1/story/import/public-works"),
        step="story_import_public_works_after",
    )
    world_after = _find_public_work(
        [dict(item or {}) for item in list(public_works_after or [])],
        world_id=resolved.world_id,
    )
    if not str(world_after.get("coverImage") or "").strip():
        summary["illustration_phase"]["status"] = "public_work_cover_missing"
        raise ReaderIllustrationAcceptanceError("public_works:cover_missing", summary=summary)
    world_cover = _assert_image_response(
        transport,
        image_url=str(world_after.get("coverImage") or ""),
        step="world_cover",
    )
    summary["public_work_cover_before"] = str(world_before.get("coverImage") or "")
    summary["public_work_cover_after"] = str(world_after.get("coverImage") or "")
    summary["world_cover"] = world_cover
    summary["illustration_phase"]["public_works"] = {
        "status": "ready",
        **world_cover,
    }

    showcase_items = _require_success_envelope(
        transport.get_json("/api/v1/showcase/works?sort=hot&page=1&pageSize=20"),
        step="showcase_works",
    )
    showcase_item = next(
        (
            dict(item or {})
            for item in list(showcase_items or [])
            if str(item.get("id") or "").strip() == world_version_id
        ),
        None,
    )
    if showcase_item is None:
        summary["illustration_phase"]["status"] = "showcase_missing"
        raise ReaderIllustrationAcceptanceError(
            f"showcase_works:world_version_missing:{world_version_id}",
            summary=summary,
        )
    if not str(showcase_item.get("coverImage") or "").strip():
        summary["illustration_phase"]["status"] = "showcase_cover_missing"
        raise ReaderIllustrationAcceptanceError("showcase_works:cover_missing", summary=summary)
    summary["showcase_cover_image"] = str(showcase_item.get("coverImage") or "")
    summary["illustration_phase"]["showcase"] = {
        "status": "ready",
        "cover_image": str(showcase_item.get("coverImage") or ""),
    }
    summary["illustration_phase"]["status"] = "ok"
    summary["illustration_healthy"] = True

    story_choice = _story_choice_phase(
        transport,
        session_id=session_id,
        token=token,
        current_node_id=str(session_with_hero.get("currentNodeId") or session_with_cover.get("currentNodeId") or ""),
    )
    summary["story_choice"] = story_choice
    if story_choice.get("separate_issue"):
        if story_choice["status"] == "quality_guard_failed":
            summary["separate_issues"].append("story_quality_guard")
        elif story_choice["status"] == "payment_required":
            summary["separate_issues"].append("story_payment_required")

    summary["healthy"] = bool(summary["illustration_healthy"])
    return summary
