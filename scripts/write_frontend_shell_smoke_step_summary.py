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
    parser = argparse.ArgumentParser(description="Render GitHub step summary for the frontend shell smoke.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--chrome-log", required=True)
    parser.add_argument("--failure-artifact", required=True)
    args = parser.parse_args()

    result = read_json(Path(args.result_file))
    failure = read_json(Path(args.failure_artifact))

    status = result.get("status", "unknown")
    print("# Frontend Shell Smoke")
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
        print(f"- Headline metric: `{summary.get('headline_metric', '-')}`")
        print(f"- Headline value: `{summary.get('headline_value', '-')}`")
        print(f"- Suite scope: `{summary.get('suite_scope', '-')}`")
    if summary:
        print("")
        print("## Summary")
        print("")
        for key in [
            "reader_world_cards",
            "reader_turn_after_step",
            "reader_gating_reason",
            "reader_gating_display_name",
            "reader_checkout_tier",
            "reader_checkout_provider",
            "reader_checkout_status",
            "reader_subscription_status",
            "reader_turn_after_activation",
            "author_visible_panels",
            "author_mutation_actor_id",
            "author_saved_draft_title",
            "author_saved_draft_version_id",
            "author_simulation_completed_chapters",
            "author_studio_credits_after_simulation",
            "author_workflow_recommended_action_after_simulation",
            "author_workspace_after_interaction",
            "ops_visible_panels",
            "ops_review_workspace",
            "ops_account_workspace",
            "ops_mutation_account_id",
            "ops_mutation_tier_id",
            "ops_governance_case_id",
            "ops_governance_case_status",
            "ops_governance_case_type",
            "ops_governance_case_severity",
            "ops_governance_case_target_type",
            "ops_governance_case_target_id",
            "ops_governance_case_status_after_transition",
            "ops_governance_evidence_count_after_append",
            "ops_governance_latest_evidence_title",
            "ops_governance_restriction_case_id",
            "ops_governance_restriction_status",
            "ops_governance_restriction_type",
            "ops_governance_restriction_state",
            "ops_governance_active_restriction_count",
            "ops_governance_case_status_after_release",
            "ops_governance_restriction_state_after_release",
            "ops_governance_active_restriction_count_after_release",
            "ops_governance_case_owner_after_assignment",
            "ops_governance_non_owner_resolve_error",
            "ops_governance_non_owner_denial_banner",
            "ops_governance_case_status_after_owner_resolution",
            "ops_governance_open_case_count_after_owner_resolution",
            "ops_governance_dismiss_case_id",
            "ops_governance_case_status_after_dismiss",
            "ops_governance_open_case_count_after_dismiss",
            "final_product",
            "final_workspace",
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
