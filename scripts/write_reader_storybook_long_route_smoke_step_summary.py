from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path_str: str | None) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[-4000:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GitHub step summary for the Reader storybook long-route smoke.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--chrome-log", required=True)
    parser.add_argument("--failure-artifact", required=True)
    args = parser.parse_args()

    result = read_json(Path(args.result_file))
    failure = read_json(Path(args.failure_artifact))
    status = result.get("status", "unknown")
    summary = result.get("summary") or {}
    artifacts = result.get("artifacts") or {}

    print("# Reader Storybook Long-Route Smoke")
    print("")
    print(f"- Status: `{status}`")
    print(f"- Failed step: `{result.get('failed_step')}`")
    print(f"- Completed steps: `{', '.join(result.get('completed_steps', [])) or '-'}`")
    if artifacts:
        print(f"- Result artifact: `{artifacts.get('result_file', '-')}`")
        print(f"- History artifact: `{artifacts.get('history_file', '-')}`")
    if summary:
        print("")
        print("## Summary")
        print("")
        for key in [
            "reader_seed_world_ids",
            "reader_seed_target_chapters",
            "reader_seed_reached_chapters",
            "reader_storybook_visible_trajectory_count",
            "reader_storybook_title_homogenization_warning_count",
            "reader_storybook_title_homogenization_history_summary",
            "reader_storybook_title_homogenization_promoted_pairs",
        ]:
            if key in summary:
                print(f"- {key}: `{summary[key]}`")

    console_errors = result.get("console_errors") or []
    if console_errors:
        print("")
        print("## Console Errors")
        print("")
        for item in console_errors[:10]:
            print(f"- `{item.get('type', 'error')}` {item.get('text', '')}")

    if failure:
        print("")
        print("## Failure Snapshot")
        print("")
        print(f"- Error: `{failure.get('error_message', '-')}`")
        print(f"- Screenshot: `{failure.get('failure_screenshot_file') or failure.get('screenshot', {}).get('screenshot_file') or '-'}`")

    server_log = read_text(args.server_log)
    if server_log:
        print("")
        print("## Server Log Tail")
        print("")
        print("```text")
        print(server_log)
        print("```")

    chrome_log = read_text(args.chrome_log)
    if chrome_log:
        print("")
        print("## Chrome Log Tail")
        print("")
        print("```text")
        print(chrome_log)
        print("```")


if __name__ == "__main__":
    main()
