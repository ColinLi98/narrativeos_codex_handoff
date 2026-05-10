#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    result_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/author_live_api_smoke_result.json")
    payload = {}
    if result_file.exists():
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"status": "invalid_json"}
    summary = payload.get("summary") or {}
    print("# Author Live API Smoke")
    print()
    for key in [
        "author_brief_payload_world_title",
        "author_saved_draft_version_id",
        "reviewer_inbox_target_world_version_id",
        "reviewer_decision_status",
        "author_submit_stage",
    ]:
        print(f"- `{key}`: {summary.get(key, '')}")
    print()
    print("## Reviewer Chrome Log Tail")
