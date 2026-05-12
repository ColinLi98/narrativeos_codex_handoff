#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


NOSBOOK_CONTENT_TYPE = "application/vnd.narrativeos.nosbook+json"
IMPORT_PATH = "/v1/author/nosbooks/import"
LOCAL_DEFAULT_URL = "http://127.0.0.1:8000"


class NosbookUploadCliError(RuntimeError):
    def __init__(self, code: str, message: str, *, exit_code: int = 1, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = dict(details or {})


def _json_dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise NosbookUploadCliError("nosbook_file_missing", "nosbook file does not exist", details={"file": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise NosbookUploadCliError(
            "nosbook_file_invalid_json",
            "nosbook file is not valid JSON",
            details={"file": str(path), "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(payload, dict):
        raise NosbookUploadCliError("nosbook_file_invalid_json", "nosbook file must contain a JSON object", details={"file": str(path)})
    return payload


def _decode_response_body(raw_body: bytes) -> Dict[str, Any]:
    try:
        decoded = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        decoded = raw_body.decode("utf-8", errors="replace")
    try:
        payload = json.loads(decoded or "{}")
    except json.JSONDecodeError:
        return {"raw": decoded}
    return payload if isinstance(payload, dict) else {"raw": payload}


def _redact_secret(value: Any, secret: str) -> Any:
    if not secret:
        return value
    if isinstance(value, dict):
        return {key: _redact_secret(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    if isinstance(value, str):
        return value.replace(secret, "[redacted]")
    return value


def _redact_secrets(value: Any, *secrets: str) -> Any:
    redacted = value
    for secret in secrets:
        redacted = _redact_secret(redacted, secret)
    return redacted


def export_local_work_nosbook(
    *,
    work_id: str,
    local_url: str = LOCAL_DEFAULT_URL,
    local_token: str,
    route: str = "active",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    normalized_work_id = str(work_id or "").strip()
    if not normalized_work_id:
        raise NosbookUploadCliError("upload_input_missing", "--local-work-id is required", exit_code=2)
    normalized_url = str(local_url or LOCAL_DEFAULT_URL).strip().rstrip("/") or LOCAL_DEFAULT_URL
    normalized_token = str(local_token or "").strip()
    if not normalized_token:
        raise NosbookUploadCliError("missing_local_studio_token", "NARRATIVEOS_LOCAL_STUDIO_TOKEN is required", exit_code=2)
    normalized_route = str(route or "active").strip() or "active"
    query = urllib.parse.urlencode({"format": "nosbook", "route": normalized_route})
    request = urllib.request.Request(
        f"{normalized_url}/v1/author/works/{urllib.parse.quote(normalized_work_id, safe='')}/export?{query}",
        headers={
            "Authorization": f"Bearer {normalized_token}",
            "Accept": NOSBOOK_CONTENT_TYPE,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = _decode_response_body(response.read())
    except urllib.error.HTTPError as exc:
        details = _redact_secret(_decode_response_body(exc.read()), normalized_token)
        raise NosbookUploadCliError(
            "local_export_failed",
            "local Studio export returned an error",
            details={"status_code": exc.code, "response": details},
        ) from exc
    except urllib.error.URLError as exc:
        raise NosbookUploadCliError(
            "local_studio_unreachable",
            "local Studio API could not be reached",
            details={"reason": str(exc.reason)},
        ) from exc
    if str(payload.get("schema_version") or "").strip() != "nosbook/v1":
        raise NosbookUploadCliError(
            "local_export_invalid_nosbook",
            "local Studio export did not return a nosbook/v1 envelope",
            details={"schema_version": payload.get("schema_version")},
        )
    return payload


def upload_nosbook_payload(
    payload: Dict[str, Any],
    *,
    platform_url: str,
    token: str,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    normalized_url = str(platform_url or "").strip().rstrip("/")
    if not normalized_url:
        raise NosbookUploadCliError("missing_platform_url", "NARRATIVEOS_PLATFORM_URL is required", exit_code=2)
    normalized_token = str(token or "").strip()
    if not normalized_token:
        raise NosbookUploadCliError("missing_platform_token", "NARRATIVEOS_PLATFORM_TOKEN is required", exit_code=2)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{normalized_url}{IMPORT_PATH}",
        data=body,
        headers={
            "Authorization": f"Bearer {normalized_token}",
            "Content-Type": NOSBOOK_CONTENT_TYPE,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode_response_body(response.read())
    except urllib.error.HTTPError as exc:
        details = _redact_secret(_decode_response_body(exc.read()), normalized_token)
        raise NosbookUploadCliError(
            "platform_upload_failed",
            "platform returned an error",
            details={"status_code": exc.code, "response": details},
        ) from exc
    except urllib.error.URLError as exc:
        raise NosbookUploadCliError(
            "platform_unreachable",
            "platform API could not be reached",
            details={"reason": str(exc.reason)},
        ) from exc


def upload_nosbook_file(
    path: Path,
    *,
    platform_url: str,
    token: str,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    return upload_nosbook_payload(
        _read_json_file(path),
        platform_url=platform_url,
        token=token,
        timeout=timeout,
    )


def upload_nosbook_from_local_work(
    *,
    work_id: str,
    local_url: str,
    local_token: str,
    local_route: str,
    platform_url: str,
    platform_token: str,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    payload = export_local_work_nosbook(
        work_id=work_id,
        local_url=local_url,
        local_token=local_token,
        route=local_route,
        timeout=timeout,
    )
    return upload_nosbook_payload(
        payload,
        platform_url=platform_url,
        token=platform_token,
        timeout=timeout,
    )


def _error_payload(error: NosbookUploadCliError) -> Dict[str, Any]:
    return {
        "schema_version": "nosbook_upload_cli_error/v1",
        "ok": False,
        "code": error.code,
        "message": error.message,
        **({"details": error.details} if error.details else {}),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Upload a NarrativeOS .nosbook export to the platform as a private draft.")
    parser.add_argument("--file", help="Path to a .nosbook JSON envelope.")
    parser.add_argument("--local-work-id", help="Export this local Agent Studio AuthorWork before uploading.")
    parser.add_argument("--local-url", default=os.environ.get("NARRATIVEOS_LOCAL_STUDIO_URL", LOCAL_DEFAULT_URL))
    parser.add_argument("--local-token", default=os.environ.get("NARRATIVEOS_LOCAL_STUDIO_TOKEN", ""))
    parser.add_argument("--local-route", default="active")
    parser.add_argument("--platform-url", default=os.environ.get("NARRATIVEOS_PLATFORM_URL", ""))
    parser.add_argument("--token", dest="platform_token", default=None)
    parser.add_argument("--platform-token", dest="platform_token", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    platform_token = args.platform_token if args.platform_token is not None else os.environ.get("NARRATIVEOS_PLATFORM_TOKEN", "")

    try:
        if args.file and args.local_work_id:
            raise NosbookUploadCliError("upload_input_conflict", "use either --file or --local-work-id, not both", exit_code=2)
        if not args.file and not args.local_work_id:
            raise NosbookUploadCliError("upload_input_missing", "either --file or --local-work-id is required", exit_code=2)
        if args.local_work_id:
            result = upload_nosbook_from_local_work(
                work_id=args.local_work_id,
                local_url=args.local_url,
                local_token=args.local_token,
                local_route=args.local_route,
                platform_url=args.platform_url,
                platform_token=platform_token,
                timeout=args.timeout,
            )
        else:
            result = upload_nosbook_file(
                Path(args.file),
                platform_url=args.platform_url,
                token=platform_token,
                timeout=args.timeout,
            )
    except NosbookUploadCliError as exc:
        error_payload = _redact_secrets(
            _error_payload(exc),
            str(args.local_token or ""),
            str(platform_token or ""),
        )
        print(_json_dump(error_payload))
        return exc.exit_code
    print(_json_dump(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
