from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def tail_lines(path: Path, limit: int = 20) -> str:
    if not path.exists():
        return "(missing)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "(empty)"
    return "\n".join(lines[-limit:])


def remediation_summary(payload: dict[str, Any]) -> list[str]:
    if payload.get("status") != "ok":
        return []
    resync = dict(payload.get("resyncSnapshot") or {})
    clear = dict(payload.get("clearSnapshot") or {})
    nav_after_resync = dict(resync.get("nav") or {})
    nav_after_clear = dict(clear.get("nav") or {})
    checks = [
        f"stale warning cleared after resync: {'yes' if not list(resync.get('warnings') or []) else 'no'}",
        f"alert ref empty after resync: {'yes' if not nav_after_resync.get('alertId') else 'no'}",
        f"stale refs empty after clear: {'yes' if not dict(clear.get('staleRefs') or {}) else 'no'}",
        f"alert ref empty after clear: {'yes' if not nav_after_clear.get('alertId') else 'no'}",
    ]
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GitHub step summary for Ops navigation stale-ref smoke.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--chrome-log", required=True)
    parser.add_argument("--failure-artifact", required=True)
    args = parser.parse_args()

    result_path = Path(args.result_file)
    server_log = Path(args.server_log)
    chrome_log = Path(args.chrome_log)
    failure_artifact = Path(args.failure_artifact)

    print("## Ops Navigation Stale-Ref Smoke")

    if not result_path.exists():
        print("")
        print("- Status: `missing_result`")
        print("- Failed step: `unknown`")
        print("")
        print("### Server Log Tail")
        print("```text")
        print(tail_lines(server_log))
        print("```")
        print("")
        print("### Chrome Log Tail")
        print("```text")
        print(tail_lines(chrome_log))
        print("```")
        return

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    status = payload.get("status", "unknown")
    seed = dict(payload.get("seed") or {})
    completed = list(payload.get("completed_steps") or [])

    print("")
    print(f"- Status: `{status}`")
    print(f"- App URL: `{payload.get('app_url', '-')}`")
    print(f"- Account: `{seed.get('account_id', '-')}`")
    print(f"- World: `{seed.get('world_id', '-')}`")
    print(f"- Case: `{seed.get('case_id', '-')}`")
    print(f"- Stale Alert: `{seed.get('stale_alert_id', '-')}`")
    print(f"- Failed step: `{payload.get('failed_step') or '-'}`")
    print(f"- Completed steps: `{', '.join(completed) if completed else '-'}`")

    if status == "ok":
        print("")
        print("### Remediation Checks")
        for item in remediation_summary(payload):
            print(f"- {item}")
    else:
        print("")
        print("### Failure")
        print(f"- Error: `{payload.get('error_message', '-')}`")
        if failure_artifact.exists():
            failure_payload = json.loads(failure_artifact.read_text(encoding="utf-8"))
            snapshot = dict(failure_payload.get("snapshot") or {})
            screenshot = dict(failure_payload.get("screenshot") or {})
            nav_inputs = dict(snapshot.get("navInputs") or {})
            panels = dict(snapshot.get("panels") or {})
            print(f"- Failure artifact: `{failure_artifact}`")
            if screenshot.get("screenshot_file"):
                print(f"- Failure screenshot: `{screenshot.get('screenshot_file')}`")
            elif screenshot.get("screenshot_error"):
                print(f"- Failure screenshot error: `{screenshot.get('screenshot_error')}`")
            print("")
            print("### Failure Snapshot")
            print(f"- Page title: `{snapshot.get('title', '-')}`")
            print(f"- Page URL: `{snapshot.get('url', '-')}`")
            print(
                f"- Nav inputs: `account={nav_inputs.get('account', '')} world={nav_inputs.get('world', '')} case={nav_inputs.get('caseId', '')} alert={nav_inputs.get('alertId', '')}`"
            )
            if panels.get("navigationSummary"):
                print("")
                print("### Navigation Summary Excerpt")
                print("```text")
                print(panels["navigationSummary"][:2000])
                print("```")
            if panels.get("navigationActions"):
                print("")
                print("### Navigation Actions Excerpt")
                print("```text")
                print(panels["navigationActions"][:1200])
                print("```")
            if snapshot.get("body_text_excerpt"):
                print("")
                print("### Body Text Excerpt")
                print("```text")
                print(str(snapshot["body_text_excerpt"])[:2000])
                print("```")
        print("")
        print("### Server Log Tail")
        print("```text")
        print(tail_lines(server_log))
        print("```")
        print("")
        print("### Chrome Log Tail")
        print("```text")
        print(tail_lines(chrome_log))
        print("```")


if __name__ == "__main__":
    main()
