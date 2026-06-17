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


def markdown_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def print_visual_review_checklist(checklist: list[dict]) -> None:
    if not checklist:
        return
    print("")
    print("## Visual Review Checklist")
    print("")
    print("| Viewport | Check | Status | Evidence | Reviewer note |")
    print("| --- | --- | --- | --- | --- |")
    for item in checklist:
        print(
            "| "
            + " | ".join(
                [
                    markdown_cell(item.get("viewport")),
                    markdown_cell(item.get("check")),
                    markdown_cell(item.get("status")),
                    markdown_cell(item.get("evidence")),
                    markdown_cell(item.get("reviewer_note")),
                ]
            )
            + " |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GitHub step summary for the Agent Studio smoke.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--chrome-log", required=True)
    parser.add_argument("--failure-artifact", required=True)
    args = parser.parse_args()

    result = read_json(Path(args.result_file))
    failure = read_json(Path(args.failure_artifact))

    status = result.get("status", "unknown")
    print("# Agent Studio Smoke")
    print("")
    print(f"- Status: `{status}`")
    print(f"- Failed step: `{result.get('failed_step')}`")
    print(f"- Completed steps: `{', '.join(result.get('completed_steps', [])) or '-'}`")
    guard = result.get("guard") or {}
    summary_meta = result.get("summary_meta") or {}
    artifacts = result.get("artifacts") or {}
    if guard:
        print(f"- Guard id: `{guard.get('id', '-')}`")
    if summary_meta:
        print(f"- Primary summary key: `{summary_meta.get('primary_key', '-')}`")
        print(f"- Primary summary count: `{summary_meta.get('primary_count', 0)}`")
    if artifacts:
        print(f"- Result artifact: `{artifacts.get('result_file', '-')}`")

    summary = result.get("summary") or {}
    if summary:
        print("")
        print("## Summary")
        print("")
        for key in [
            "headline_metric",
            "headline_value",
            "suite_scope",
            "author_actor_id",
            "work_id",
            "startup_chapter_count",
            "chapter_count_after_continue",
            "route_count_after_branch",
            "nosbook_schema_version",
            "nosbook_content_type",
            "nosbook_chapter_count",
            "nosbook_branch_map_count",
            "nosbook_choice_history_count",
            "nosbook_quality_summary_keys",
            "desktop_screenshot_file",
            "mobile_screenshot_file",
            "mobile_overflow_width",
            "desktop_sticky_director",
            "desktop_director_top_after_scroll",
            "mobile_choice_bounded_scroll",
            "mobile_choice_client_height",
            "mobile_choice_scroll_height",
            "mobile_choice_overflow_y",
            "desktop_reader_body_length",
            "mobile_reader_body_length",
            "mobile_director_visible",
            "mobile_branch_map_visible",
            "mobile_quality_labels",
            "visual_review_file",
            "visual_review_total",
            "visual_review_auto_pass",
            "visual_review_manual_review",
            "visual_review_blocking_failures",
            "generation_wait_copy",
            "visible_q_code",
        ]:
            if key in summary:
                print(f"- {key}: `{summary[key]}`")

        if "desktop_screenshot_file" in summary or "mobile_screenshot_file" in summary:
            print("")
            print("## Viewport QA")
            print("")
            print(f"- Desktop screenshot: `{summary.get('desktop_screenshot_file', '-')}`")
            print(f"- Mobile screenshot: `{summary.get('mobile_screenshot_file', '-')}`")
            print(f"- Mobile horizontal overflow: `{summary.get('mobile_overflow_width', '-')}`")
            print(f"- Desktop sticky director: `{summary.get('desktop_sticky_director', '-')}`")
            print(f"- Desktop director top after scroll: `{summary.get('desktop_director_top_after_scroll', '-')}`")
            print(f"- Mobile choice bounded scroll: `{summary.get('mobile_choice_bounded_scroll', '-')}`")
            print(f"- Mobile choice height: `{summary.get('mobile_choice_client_height', '-')}` / `{summary.get('mobile_choice_scroll_height', '-')}`")
            print(f"- Mobile choice overflow-y: `{summary.get('mobile_choice_overflow_y', '-')}`")
            print(f"- Mobile director visible: `{summary.get('mobile_director_visible', '-')}`")
            print(f"- Mobile branch map visible: `{summary.get('mobile_branch_map_visible', '-')}`")

    print_visual_review_checklist(result.get("visual_review_checklist") or [])

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
        print(f"- Screenshot: `{failure.get('screenshot', {}).get('screenshot_file') or '-'}`")

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
