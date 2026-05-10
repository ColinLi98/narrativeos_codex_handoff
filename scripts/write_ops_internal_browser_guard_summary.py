#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    names = [
        "ops_internal_snapshot",
        "ops_internal_form_copy",
        "ops_internal_static_copy",
        "ops_internal_populated_copy",
        "ops_internal_account_copy",
    ]
    print("# Ops Internal Browser Guards")
    print()
    print("| Check | Status | Primary summary key | Result artifact |")
    print("| --- | --- | --- | --- |")
    for name in names:
        result_file = artifacts / f"{name}_result.json"
        status = "missing"
        primary_summary_key = "schema_version"
        if result_file.exists():
            try:
                status = json.loads(result_file.read_text(encoding="utf-8")).get("status", "unknown")
            except json.JSONDecodeError:
                status = "invalid_json"
        print(f"| {name} | {status} | {primary_summary_key} | {result_file} |")
    print()
    print("## Server Log Tail")
    print()
    print("## Chrome Log Tail")


if __name__ == "__main__":
    main()
