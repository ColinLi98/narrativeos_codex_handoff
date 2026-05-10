from pathlib import Path
import shutil
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_shell_smoke_scripts_exist_and_are_parseable():
    run_script = ROOT / "scripts" / "run_frontend_shell_smoke.sh"
    reader_run_script = ROOT / "scripts" / "run_reader_shell_smoke.sh"
    verify_script = ROOT / "scripts" / "verify_frontend_shell_smoke.js"
    paid_chapter_helper = ROOT / "scripts" / "force_reader_paid_chapter.py"
    agent_studio_run_script = ROOT / "scripts" / "run_agent_studio_smoke.sh"
    agent_studio_verify_script = ROOT / "scripts" / "verify_agent_studio_smoke.js"
    agent_studio_summary_script = ROOT / "scripts" / "write_agent_studio_smoke_step_summary.py"
    author_repair_run_script = ROOT / "scripts" / "run_author_repair_loop_smoke.sh"
    author_repair_verify_script = ROOT / "scripts" / "verify_author_repair_loop_smoke.js"
    public_run_script = ROOT / "scripts" / "run_public_shell_copy_check.sh"
    public_verify_script = ROOT / "scripts" / "verify_public_shell_copy.js"
    internal_run_script = ROOT / "scripts" / "run_ops_internal_snapshot_check.sh"
    internal_verify_script = ROOT / "scripts" / "verify_ops_internal_snapshot.js"
    internal_form_run_script = ROOT / "scripts" / "run_ops_internal_form_copy_check.sh"
    internal_form_verify_script = ROOT / "scripts" / "verify_ops_internal_form_copy.js"
    internal_static_run_script = ROOT / "scripts" / "run_ops_internal_static_copy_check.sh"
    internal_static_verify_script = ROOT / "scripts" / "verify_ops_internal_static_copy.js"
    internal_populated_run_script = ROOT / "scripts" / "run_ops_internal_populated_copy_check.sh"
    internal_populated_verify_script = ROOT / "scripts" / "verify_ops_internal_populated_copy.js"
    internal_account_run_script = ROOT / "scripts" / "run_ops_internal_account_copy_check.sh"
    internal_account_verify_script = ROOT / "scripts" / "verify_ops_internal_account_copy.js"
    internal_entry_script = ROOT / "scripts" / "run_ops_internal_browser_guards.sh"
    internal_summary_script = ROOT / "scripts" / "write_ops_internal_browser_guard_summary.py"
    summary_script = ROOT / "scripts" / "write_frontend_shell_smoke_step_summary.py"

    assert run_script.exists()
    assert reader_run_script.exists()
    assert verify_script.exists()
    assert paid_chapter_helper.exists()
    assert agent_studio_run_script.exists()
    assert agent_studio_verify_script.exists()
    assert agent_studio_summary_script.exists()
    assert author_repair_run_script.exists()
    assert author_repair_verify_script.exists()
    assert public_run_script.exists()
    assert public_verify_script.exists()
    assert internal_run_script.exists()
    assert internal_verify_script.exists()
    assert internal_form_run_script.exists()
    assert internal_form_verify_script.exists()
    assert internal_static_run_script.exists()
    assert internal_static_verify_script.exists()
    assert internal_populated_run_script.exists()
    assert internal_populated_verify_script.exists()
    assert internal_account_run_script.exists()
    assert internal_account_verify_script.exists()
    assert internal_entry_script.exists()
    assert internal_summary_script.exists()
    assert summary_script.exists()

    run_text = run_script.read_text(encoding="utf-8")
    reader_run_text = reader_run_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")
    paid_chapter_helper_text = paid_chapter_helper.read_text(encoding="utf-8")
    agent_studio_run_text = agent_studio_run_script.read_text(encoding="utf-8")
    agent_studio_verify_text = agent_studio_verify_script.read_text(encoding="utf-8")
    agent_studio_summary_text = agent_studio_summary_script.read_text(encoding="utf-8")
    author_repair_run_text = author_repair_run_script.read_text(encoding="utf-8")
    author_repair_verify_text = author_repair_verify_script.read_text(encoding="utf-8")
    public_run_text = public_run_script.read_text(encoding="utf-8")
    public_verify_text = public_verify_script.read_text(encoding="utf-8")
    internal_run_text = internal_run_script.read_text(encoding="utf-8")
    internal_verify_text = internal_verify_script.read_text(encoding="utf-8")
    internal_form_run_text = internal_form_run_script.read_text(encoding="utf-8")
    internal_form_verify_text = internal_form_verify_script.read_text(encoding="utf-8")
    internal_static_run_text = internal_static_run_script.read_text(encoding="utf-8")
    internal_static_verify_text = internal_static_verify_script.read_text(encoding="utf-8")
    internal_populated_run_text = internal_populated_run_script.read_text(encoding="utf-8")
    internal_populated_verify_text = internal_populated_verify_script.read_text(encoding="utf-8")
    internal_account_run_text = internal_account_run_script.read_text(encoding="utf-8")
    internal_account_verify_text = internal_account_verify_script.read_text(encoding="utf-8")
    internal_entry_text = internal_entry_script.read_text(encoding="utf-8")
    internal_summary_text = internal_summary_script.read_text(encoding="utf-8")
    summary_text = summary_script.read_text(encoding="utf-8")

    assert "CI_HEADLESS" in run_text
    assert "CHROME_BIN" in run_text
    assert "reader_shell_smoke_result.json" in reader_run_text
    assert "reader_shell_smoke_failure_snapshot.json" in reader_run_text
    assert "reader_shell_smoke_failure.png" in reader_run_text
    assert "--scope reader" in reader_run_text
    assert "author_repair_loop_smoke_result.json" in author_repair_run_text
    assert "author_repair_loop_smoke_failure_snapshot.json" in author_repair_run_text
    assert "author_repair_loop_smoke_failure.png" in author_repair_run_text
    assert "verify_author_repair_loop_smoke.js" in author_repair_run_text
    assert "frontend_shell_smoke_result.json" in run_text
    assert "frontend_shell_smoke_failure_snapshot.json" in run_text
    assert "frontend_shell_smoke_failure.png" in run_text
    assert "agent_studio_smoke_result.json" in agent_studio_run_text
    assert "agent_studio_smoke_failure_snapshot.json" in agent_studio_run_text
    assert "agent_studio_smoke_failure.png" in agent_studio_run_text
    assert "agent_studio_smoke_desktop.png" in agent_studio_run_text
    assert "agent_studio_smoke_mobile.png" in agent_studio_run_text
    assert "agent_studio_smoke_visual_review.md" in agent_studio_run_text
    assert "--desktop-screenshot-file" in agent_studio_run_text
    assert "--mobile-screenshot-file" in agent_studio_run_text
    assert "--visual-review-file" in agent_studio_run_text
    assert "verify_agent_studio_smoke.js" in agent_studio_run_text
    assert "APP_PORT=\"${APP_PORT:-8018}\"" in agent_studio_run_text
    assert "CHROME_PORT=\"${CHROME_PORT:-9238}\"" in agent_studio_run_text
    assert "--result-file" in run_text
    assert "--failure-artifact-file" in run_text
    assert "--failure-screenshot-file" in run_text
    assert "scripts/force_reader_paid_chapter.py" in verify_text
    assert "Force a reader session into a paid chapter" in paid_chapter_helper_text
    assert "public_shell_copy_result.json" in public_run_text
    assert "public_shell_copy_failure_snapshot.json" in public_run_text
    assert "public_shell_copy_failure.png" in public_run_text
    assert "verify_public_shell_copy.js" in public_run_text
    assert "ops_internal_snapshot_result.json" in internal_run_text
    assert "ops_internal_snapshot_failure_snapshot.json" in internal_run_text
    assert "ops_internal_snapshot_failure.png" in internal_run_text
    assert "verify_ops_internal_snapshot.js" in internal_run_text
    assert "ops_internal_form_copy_result.json" in internal_form_run_text
    assert "ops_internal_form_copy_failure_snapshot.json" in internal_form_run_text
    assert "ops_internal_form_copy_failure.png" in internal_form_run_text
    assert "verify_ops_internal_form_copy.js" in internal_form_run_text
    assert "ops_internal_static_copy_result.json" in internal_static_run_text
    assert "ops_internal_static_copy_failure_snapshot.json" in internal_static_run_text
    assert "ops_internal_static_copy_failure.png" in internal_static_run_text
    assert "verify_ops_internal_static_copy.js" in internal_static_run_text
    assert "ops_internal_populated_copy_result.json" in internal_populated_run_text
    assert "ops_internal_populated_copy_failure_snapshot.json" in internal_populated_run_text
    assert "ops_internal_populated_copy_failure.png" in internal_populated_run_text
    assert "verify_ops_internal_populated_copy.js" in internal_populated_run_text
    assert "ops_internal_account_copy_result.json" in internal_account_run_text
    assert "ops_internal_account_copy_failure_snapshot.json" in internal_account_run_text
    assert "ops_internal_account_copy_failure.png" in internal_account_run_text
    assert "verify_ops_internal_account_copy.js" in internal_account_run_text
    assert "BASE_APP_PORT" in internal_entry_text
    assert "BASE_CHROME_PORT" in internal_entry_text
    assert "run_ops_internal_snapshot_check.sh" in internal_entry_text
    assert "run_ops_internal_form_copy_check.sh" in internal_entry_text
    assert "run_ops_internal_static_copy_check.sh" in internal_entry_text
    assert "run_ops_internal_populated_copy_check.sh" in internal_entry_text
    assert "run_ops_internal_account_copy_check.sh" in internal_entry_text
    assert "Ops Internal Browser Guards" in internal_summary_text
    assert "Server Log Tail" in internal_summary_text
    assert "Chrome Log Tail" in internal_summary_text
    assert "ops_internal_snapshot" in internal_summary_text
    assert "ops_internal_account_copy" in internal_summary_text

    assert "failed_step" in verify_text
    assert "reader_job_timeout" in verify_text
    assert "reader_job_failed" in verify_text
    assert "reader_ui_sync_stale" in verify_text
    assert "readerGenerationJob" in verify_text
    assert "console_errors" in verify_text
    assert "agent_studio_smoke/v1" in agent_studio_verify_text
    assert "agent_studio_startup" in agent_studio_verify_text
    assert "agent_studio_director_continue" in agent_studio_verify_text
    assert "agent_studio_create_branch" in agent_studio_verify_text
    assert "agent_studio_export_nosbook" in agent_studio_verify_text
    assert "lastNosbookExport" in agent_studio_verify_text
    assert "generation_wait_copy" in agent_studio_verify_text
    assert "第一章生成中" in agent_studio_verify_text
    assert "续写中" in agent_studio_verify_text
    assert "新路线创建中" in agent_studio_verify_text
    assert "Emulation.setDeviceMetricsOverride" in agent_studio_verify_text
    assert "Page.captureScreenshot" in agent_studio_verify_text
    assert "desktop_screenshot_file" in agent_studio_verify_text
    assert "mobile_screenshot_file" in agent_studio_verify_text
    assert "mobile_overflow_width" in agent_studio_verify_text
    assert "desktop_sticky_director" in agent_studio_verify_text
    assert "desktop_director_top_after_scroll" in agent_studio_verify_text
    assert "mobile_choice_bounded_scroll" in agent_studio_verify_text
    assert "mobile_choice_client_height" in agent_studio_verify_text
    assert "mobile_choice_scroll_height" in agent_studio_verify_text
    assert "mobile_choice_overflow_y" in agent_studio_verify_text
    assert "agent_studio_sticky_director_regression" in agent_studio_verify_text
    assert "agent_studio_mobile_choice_scroll_regression" in agent_studio_verify_text
    assert "Desktop sticky director" in agent_studio_verify_text
    assert "Mobile choice bounded scroll" in agent_studio_verify_text
    assert "horizontal_overflow_width" in agent_studio_verify_text
    assert "director_visible" in agent_studio_verify_text
    assert "branch_map_visible" in agent_studio_verify_text
    assert "visual_review_checklist" in agent_studio_verify_text
    assert "visual_review_total" in agent_studio_verify_text
    assert "visual_review_auto_pass" in agent_studio_verify_text
    assert "visual_review_manual_review" in agent_studio_verify_text
    assert "visual_review_blocking_failures" in agent_studio_verify_text
    assert "manual_review" in agent_studio_verify_text
    assert "blocking_failure" in agent_studio_verify_text
    assert "writeVisualReviewMarkdown" in agent_studio_verify_text
    assert "nosbook/v1" in agent_studio_verify_text
    assert "application/vnd.narrativeos.nosbook+json" in agent_studio_verify_text
    assert "Agent Studio Smoke" in agent_studio_summary_text
    assert "nosbook_choice_history_count" in agent_studio_summary_text
    assert "Viewport QA" in agent_studio_summary_text
    assert "desktop_screenshot_file" in agent_studio_summary_text
    assert "mobile_screenshot_file" in agent_studio_summary_text
    assert "mobile_overflow_width" in agent_studio_summary_text
    assert "desktop_sticky_director" in agent_studio_summary_text
    assert "desktop_director_top_after_scroll" in agent_studio_summary_text
    assert "mobile_choice_bounded_scroll" in agent_studio_summary_text
    assert "mobile_choice_client_height" in agent_studio_summary_text
    assert "mobile_choice_scroll_height" in agent_studio_summary_text
    assert "mobile_choice_overflow_y" in agent_studio_summary_text
    assert "Visual Review Checklist" in agent_studio_summary_text
    assert "visual_review_file" in agent_studio_summary_text
    assert "visual_review_total" in agent_studio_summary_text
    assert "visual_review_auto_pass" in agent_studio_summary_text
    assert "visual_review_manual_review" in agent_studio_summary_text
    assert "visual_review_blocking_failures" in agent_studio_summary_text
    assert "generation_wait_copy" in agent_studio_summary_text
    visual_review_text = "\n".join([agent_studio_run_text, agent_studio_verify_text, agent_studio_summary_text])
    for forbidden in ["pixel diff", "golden image", "golden screenshot", "image hash", "snapshot comparison", "visual snapshot"]:
        assert forbidden not in visual_review_text.lower()
    assert "author_repair_loop_smoke/v1" in author_repair_verify_text
    assert "author_register_login" in author_repair_verify_text
    assert "grant_author_creator_access" in author_repair_verify_text
    assert "author_create_draft_from_brief" in author_repair_verify_text
    assert "author_simulate_draft" in author_repair_verify_text
    assert "author_repair_loop_visible_after_rerun" in author_repair_verify_text
    assert "author_repair_loop_issue_code" in author_repair_verify_text
    assert "author_repair_loop_summary_text" in author_repair_verify_text
    assert "schema_version" in verify_text
    assert "summary_meta" in verify_text
    assert "artifacts" in verify_text
    assert "reader_world_cards" in verify_text
    assert "restore_reader_workspace" in verify_text
    assert "reader_turn_after_step" in verify_text
    assert "reader_gating_reason" in verify_text
    assert "reader_gating_display_name" in verify_text
    assert "reader_checkout_tier" in verify_text
    assert "reader_checkout_provider" in verify_text
    assert "reader_checkout_status" in verify_text
    assert "reader_subscription_status" in verify_text
    assert "reader_turn_after_activation" in verify_text
    assert "reader_storybook_view" in verify_text
    assert "reader_backstage_view" in verify_text
    assert "reader_storybook_title" in verify_text
    assert "reader_storybook_prose_length" in verify_text
    assert "reader_backstage_copy_length" in verify_text
    assert "author_visible_panels" in verify_text
    assert "author_mutation_actor_id" in verify_text
    assert "author_saved_draft_title" in verify_text
    assert "#author-draft-list article.is-active h3" in verify_text
    assert "#author-draft-detail h3" in verify_text
    assert "author_saved_draft_version_id" in verify_text
    assert "author_simulation_completed_chapters" in verify_text
    assert "author_simulate_latest_decision" in verify_text
    assert "author_simulate_freshness_status" in verify_text
    assert "author_simulate_next_focus_chapter" in verify_text
    assert "author_simulate_shortest_loop_relationship" in verify_text
    assert "author_simulate_review_hint" in verify_text
    assert "author_studio_credits_after_simulation" in verify_text
    assert "author_workflow_recommended_action_after_simulation" in verify_text
    assert "author_repair_loop_issue_code" in verify_text
    assert "author_repair_loop_asset_type" in verify_text
    assert "author_repair_loop_asset_target" in verify_text
    assert "author_repair_loop_severity_trend" in verify_text
    assert "author_repair_loop_ready_for_validation" in verify_text
    assert "author_repair_loop_validation_panel" in verify_text
    assert "author_repair_loop_baseline_issue_count" in verify_text
    assert "author_repair_loop_current_issue_count" in verify_text
    assert "author_repair_loop_baseline_worst_decision" in verify_text
    assert "author_repair_loop_current_worst_decision" in verify_text
    assert "author_repair_loop_remaining_chapter_count" in verify_text
    assert "author_workspace_after_interaction" in verify_text
    assert "ops_visible_panels" in verify_text
    assert "ops_review_workspace" in verify_text
    assert "ops_account_workspace" in verify_text
    assert "ops_mutation_account_id" in verify_text
    assert "ops_mutation_tier_id" in verify_text
    assert "ops_governance_case_id" in verify_text
    assert "ops_governance_case_status" in verify_text
    assert "ops_governance_case_type" in verify_text
    assert "ops_governance_case_severity" in verify_text
    assert "ops_governance_case_target_type" in verify_text
    assert "ops_governance_case_target_id" in verify_text
    assert "ops_governance_case_status_after_transition" in verify_text
    assert "ops_governance_evidence_count_after_append" in verify_text
    assert "ops_governance_latest_evidence_title" in verify_text
    assert "ops_governance_restriction_case_id" in verify_text
    assert "ops_governance_restriction_status" in verify_text
    assert "ops_governance_restriction_type" in verify_text
    assert "ops_governance_restriction_state" in verify_text
    assert "ops_governance_active_restriction_count" in verify_text
    assert "ops_governance_case_status_after_release" in verify_text
    assert "ops_governance_restriction_state_after_release" in verify_text
    assert "ops_governance_active_restriction_count_after_release" in verify_text
    assert "ops_governance_case_owner_after_assignment" in verify_text
    assert "opsAssignedOwnerId" in verify_text
    assert "ownerRoster" in verify_text
    assert "ops_owner_smoke_" not in verify_text
    assert "ops_governance_non_owner_resolve_status" in verify_text
    assert "ops_governance_non_owner_resolve_code" in verify_text
    assert "ops_governance_non_owner_resolve_endpoint" in verify_text
    assert "ops_governance_non_owner_denial_expected_owner_id" in verify_text
    assert "ops_governance_non_owner_denial_action_label" in verify_text
    assert "ops_governance_non_owner_denial_kind" in verify_text
    assert "ops_governance_case_status_after_owner_resolution" in verify_text
    assert "ops_governance_open_case_count_after_owner_resolution" in verify_text
    assert "ops_governance_dismiss_case_id" in verify_text
    assert "ops_governance_case_status_after_dismiss" in verify_text
    assert "ops_governance_open_case_count_after_dismiss" in verify_text
    assert "step_reader_once" in verify_text
    assert "author_refresh_once" in verify_text
    assert "author_open_settings" in verify_text
    assert "author_register_login" in verify_text
    assert "admin-view-session-bridge" in verify_text
    assert "narrativeos_admin_view_bridge" in verify_text
    assert "return_author_workspace" in verify_text
    assert "author_open_brief" in verify_text
    assert "author_save_draft" in verify_text
    assert "author_simulate_draft" in verify_text
    assert "author_repair_loop_visible_after_rerun" in verify_text
    assert "ops_switch_review" in verify_text
    assert "ops_switch_account" in verify_text
    assert "ops_grant_subscription" in verify_text
    assert "ops_create_governance_case" in verify_text
    assert "ops_transition_governance_case" in verify_text
    assert "ops_add_governance_evidence" in verify_text
    assert "ops_apply_governance_restriction" in verify_text
    assert "ops_release_governance_restriction" in verify_text
    assert "ops_assign_governance_case_owner" in verify_text
    assert "ops_non_owner_resolve_rejected" in verify_text
    assert "ops_non_owner_resolve_ui_denial" in verify_text
    assert "ops_resolve_governance_case_by_owner" in verify_text
    assert "ops_create_governance_dismiss_case" in verify_text
    assert "ops_dismiss_governance_case" in verify_text
    assert "start_reader_checkout" in verify_text
    assert "complete_reader_checkout_webhook" in verify_text
    assert "resume_reader_after_activation" in verify_text
    assert "captureScreenshot" in verify_text
    assert "verify_public_author_copy" in public_verify_text
    assert "verify_public_reader_copy" in public_verify_text
    assert "verify_public_reader_payment_card" in public_verify_text
    assert "verify_public_reader_sidebar" in public_verify_text
    assert "verify_public_author_workspaces" in public_verify_text
    assert "public_mode_ops_hidden" in public_verify_text
    assert "public_mode_debug_hidden" in public_verify_text
    assert "public_reader_payment_forbidden_hits" in public_verify_text
    assert "public_reader_sidebar_forbidden_hits" in public_verify_text
    assert "public_author_workspace_snapshots" in public_verify_text
    assert "forbidden_hits" in public_verify_text
    assert "schema_version" in public_verify_text
    assert "summary_meta" in public_verify_text
    assert "artifacts" in public_verify_text
    assert "Reader Workspace" in public_verify_text
    assert "Membership & Wallet" in public_verify_text
    assert '"overview", "brief", "draft", "simulate", "review", "settings"' in public_verify_text
    assert "inject_internal_ops_snapshot_data" in internal_verify_text
    assert "verify_internal_ops_deep_cards" in internal_verify_text
    assert "ops_internal_runtime_receipts" in internal_verify_text
    assert "ops_internal_provider_runtime_metrics" in internal_verify_text
    assert "ops_internal_governance_export" in internal_verify_text
    assert "ops_internal_investigation_timeline" in internal_verify_text
    assert "ops_internal_learned_compare" in internal_verify_text
    assert "ops_internal_evaluator_promotion" in internal_verify_text
    assert "ops_internal_reranker_promotion" in internal_verify_text
    assert "ops_internal_learned_data_ops" in internal_verify_text
    assert "ops_internal_review_sample_backlog" in internal_verify_text
    assert "ops_internal_preference_samples" in internal_verify_text
    assert "ops_internal_ranking_samples" in internal_verify_text
    assert "ops_internal_pair_coverage_backlog" in internal_verify_text
    assert "ops_internal_review_capture_context" in internal_verify_text
    assert "ops_internal_last_action_impact" in internal_verify_text
    assert "schema_version" in internal_verify_text
    assert "Runtime Receipts" in internal_verify_text
    assert "Provider Runtime Metrics" in internal_verify_text
    assert "Evaluator Promotion Gate" in internal_verify_text
    assert "verify_internal_ops_form_copy" in internal_form_verify_text
    assert "ops_form_navigation" in internal_form_verify_text
    assert "ops_form_release" in internal_form_verify_text
    assert "ops_form_account_subscription" in internal_form_verify_text
    assert "ops_form_alerts" in internal_form_verify_text
    assert "ops_form_governance" in internal_form_verify_text
    assert "ops_form_investigation" in internal_form_verify_text
    assert "ops_form_assisted_gate" in internal_form_verify_text
    assert "ops_form_assisted_rerank" in internal_form_verify_text
    assert "ops_form_evaluator_promotion" in internal_form_verify_text
    assert "ops_form_reranker_promotion" in internal_form_verify_text
    assert "ops_form_review_capture" in internal_form_verify_text
    assert "ops_form_preference_capture" in internal_form_verify_text
    assert "ops_form_ranking_capture" in internal_form_verify_text
    assert "ops_form_data_integrity" in internal_form_verify_text
    assert "ops_form_runbook" in internal_form_verify_text
    assert "ops_form_async_jobs" in internal_form_verify_text
    assert "ops_form_provider_rollout" in internal_form_verify_text
    assert "schema_version" in internal_form_verify_text
    assert "Account ID" in internal_form_verify_text
    assert "Reviewer ID" in internal_form_verify_text
    assert "verify_internal_ops_static_copy" in internal_static_verify_text
    assert "ops_static_world_status" in internal_static_verify_text
    assert "ops_static_release_workspace" in internal_static_verify_text
    assert "ops_static_account_workspace" in internal_static_verify_text
    assert "ops_static_support" in internal_static_verify_text
    assert "ops_static_alerts" in internal_static_verify_text
    assert "ops_static_governance" in internal_static_verify_text
    assert "ops_static_investigation" in internal_static_verify_text
    assert "ops_static_eval_metrics" in internal_static_verify_text
    assert "ops_static_cross_pack" in internal_static_verify_text
    assert "ops_static_learned_overview" in internal_static_verify_text


def test_author_work_login_guard_contract_is_present():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    ui_shared = (ROOT / "src" / "narrativeos" / "web" / "ui_shared.js").read_text(encoding="utf-8")

    assert "author_work_identity_required" in author_workspace
    assert "author_work_forbidden" in author_workspace
    assert "URL 里的 account_id 只用于定位，不代表已登录" in author_workspace
    assert "这份 Draft 属于作者账号" in author_workspace
    assert "登录这个作者后继续创作" in author_workspace
    assert "shouldPromptAuthorLoginForDeepLink()" in author_workspace
    assert "shouldPromptAuthorAccountSwitchForDeepLink" in author_workspace
    assert "preferredAuthorDraftVersionId" in author_workspace
    assert "expectedDraftAuthorAccountId" in author_workspace
    assert "normalizeAuthorDraftRouteAccount" in author_workspace
    assert "clearAuthorAuthSessionLocal" in author_workspace
    assert "ensureAuthorDeepLinkLoginPrompt();" in author_workspace
    assert "ensureAuthorDeepLinkAccountSwitchPrompt(authenticatedAuthorAccountIdValue);" in author_workspace
    assert "ensureAuthorDeepLinkAccountSwitchPrompt(String(authorState.authorAuthSession?.identity?.account_id || \"\").trim());" in author_workspace
    assert "clearMismatchedAuthorDeepLinkContext" in author_workspace
    assert "错误深链参数已清除，当前登录会保留" in author_workspace
    assert "旧会话已清除，请直接登录正确账号继续创作" not in author_workspace
    assert "authorDeepLinkResumeUrl" in author_workspace
    assert "resumeAuthorDeepLinkIfPossible" in author_workspace
    assert "window.location.replace(resumeUrl)" in author_workspace
    assert "const hasAuthorSession = Boolean(authorState.authorAuthSession?.accessToken && sessionAccountId);" in author_workspace
    assert "currentUrl.pathname === \"/app/user\"" in author_workspace
    assert "currentUrl.searchParams.get(\"workspace\") === \"settings\"" in author_workspace
    assert "let activeAuthorAccountIdValue =" in author_workspace
    assert "const authenticatedAuthorAccountIdValue = String(authorState.authorAuthSession?.identity?.account_id || \"\").trim();" in author_workspace
    assert "currentDraftAuthorAccountId()" in author_workspace
    assert "currentDraftAuthorAccountId() || params.get(\"account_id\")" in author_workspace


def test_author_happy_path_error_copy_and_session_gating_contract_is_present():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")

    assert "function formatAuthorApiErrorMessage" in author_workspace
    assert "作者登录已失效，请先在“账户协作”里重新登录。" in author_workspace
    assert "当前账号没有这份 Draft 的访问权限，请切换到正确作者账号后再试。" in author_workspace
    assert "const allowAuthorDraftRequests = hasAuthorAuthenticatedSession();" in author_workspace
    assert "const allowAuthorDraftRequests = Boolean(authorState.authorAuthSession?.accessToken) || shellState.debug;" not in author_workspace
    assert "authorState.authorDrafts = [];" in author_workspace
    assert "authorState.activeDraftDetail = null;" in author_workspace
    assert "生成 Draft 失败，请稍后再试。" in author_workspace
    assert "保存角色卡失败，请稍后再试。" in author_workspace
    assert "`生成 Draft 失败：${error.message}`" not in author_workspace
    assert "`保存角色卡失败：${error.message}`" not in author_workspace


def test_author_collaboration_frontend_uses_token_identity_without_legacy_headers():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    reader_workspace = (ROOT / "src" / "narrativeos" / "web" / "reader.js").read_text(encoding="utf-8")

    assert "function hasAuthorAuthenticatedSession()" in author_workspace
    assert "function authorCollaborationHeaders(options = {})" in author_workspace
    assert "void options;" in author_workspace
    assert "Authorization: `Bearer ${token}`" in author_workspace
    assert "\"X-NarrativeOS-Actor-Id\"" not in author_workspace
    assert "\"X-NarrativeOS-Actor-Role\"" not in author_workspace
    assert "\"X-NarrativeOS-Account-Id\"" not in author_workspace
    assert "if (!hasAuthorAuthenticatedSession() || !authorSessionCanReview() || !reviewerId)" in author_workspace
    assert "if (!actorId || !hasAuthorAuthenticatedSession())" in author_workspace
    assert "if (!readerState.readerAuthSession?.accessToken && !(readerState.readerAuthSession?.cookieBacked && readerState.readerAuthSession?.identity))" in reader_workspace


def test_author_longform_capability_contract_is_present():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    authoring_service = (ROOT / "src" / "narrativeos" / "services" / "authoring.py").read_text(encoding="utf-8")
    author_api = (ROOT / "src" / "narrativeos" / "api" / "author.py").read_text(encoding="utf-8")
    capability_config = (ROOT / "configs" / "longform_capability_profiles.json").read_text(encoding="utf-8")

    assert "bootstrap_structured_longform" in author_workspace
    assert "bootstrap_quick_brief_enrich" in author_workspace
    assert "当前 quick brief 只会直接承诺到 100 章" in author_workspace
    assert "进入结构化长篇蓝图" in author_workspace
    assert "claim_safe_band" in author_workspace
    assert "requested_target_band" in author_workspace
    assert "longform_readiness" in author_workspace
    assert "supported_target_band" in authoring_service
    assert "requires_structured_longform" in authoring_service
    assert "longform_structure_exhaustion" in authoring_service
    assert "AuthorLongformBootstrapRequest" in author_api
    assert "\"1000\"" in capability_config
    assert "refreshAuthorWorks(activeAuthorAccountIdValue)" in author_workspace


def test_ops_release_claim_alignment_contract_is_present():
    ops_render = (ROOT / "src" / "narrativeos" / "web" / "ops_render_sections.js").read_text(encoding="utf-8")
    review_service = (ROOT / "src" / "narrativeos" / "services" / "review.py").read_text(encoding="utf-8")

    assert "author_longform_capability" in review_service
    assert "author_longform_claim_alignment" in review_service
    assert "ops_release_ready_band" in review_service
    assert "Author 入口" in ops_render
    assert "Author claim" in ops_render
    assert "Ops ready band" in ops_render
    assert "author longform capability" in ops_render
    assert "author claim alignment" in ops_render


def test_author_work_reading_preview_contract_is_present():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "narrativeos" / "web" / "styles.css").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")

    assert "作品阅读预览" in author_workspace
    assert "用阅读视角查看当前作品稿" in author_workspace
    assert "story-feed author-reading-preview-feed" in author_workspace
    assert "回到正文编辑" in author_workspace
    assert "章节硬约束未通过" in author_workspace
    assert "formatAuthorQualityGateSummary" in author_workspace
    assert "authorWorkQualityGateFailure" in state_runtime
    assert ".author-reading-preview-panel" in styles
    assert ".author-reading-preview-feed" in styles


def test_author_relationship_section_prioritizes_ranked_hotspots_over_dense_edge_labels():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "narrativeos" / "web" / "styles.css").read_text(encoding="utf-8")

    assert "关系影响榜单" in author_workspace
    assert "关系结构示意" in author_workspace
    assert "relationshipStrengthLabel" in author_workspace
    assert "authorRelationshipNetworkMarkerCounter" in author_workspace
    assert 'document.createElementNS("http://www.w3.org/2000/svg", "path")' in author_workspace
    assert 'path.setAttribute("d", `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`)' in author_workspace
    assert "const hasReciprocal =" in author_workspace
    assert "const curveDirection =" in author_workspace
    assert 'label.textContent = `${edge.dominant_metric_label}' not in author_workspace
    assert ".author-relationship-network {" in styles
    assert "min-height: 220px;" in styles


def test_author_heatmap_declutters_repeated_issue_codes():
    author_workspace = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "narrativeos" / "web" / "styles.css").read_text(encoding="utf-8")

    assert "buildHeatmapIssueAggregation" in author_workspace
    assert "authorHeatmapDecisionLabel" in author_workspace
    assert 'pass: "通过"' in author_workspace
    assert 'rewrite: "重写"' in author_workspace
    assert 'block: "阻断"' in author_workspace
    assert "authorSceneFunctionShortLabel" in author_workspace
    assert 'false_peace: "假平静"' in author_workspace
    assert 'confession_window: "告白窗口"' in author_workspace
    assert "decision.textContent = authorHeatmapDecisionLabel" in author_workspace
    assert "caption.textContent = authorSceneFunctionShortLabel" in author_workspace
    assert "appendHeatmapIssueBadgeRow" in author_workspace
    assert "author-heatmap-summary-badges" in author_workspace
    assert "author-heatmap-cell-badges" in author_workspace
    assert "issueCodes.slice(0, 2)" in author_workspace
    assert "`+${issueCodes.length - 2}`" in author_workspace
    assert ".author-heatmap-summary-badges" in styles
    assert ".author-heatmap-badge.is-overflow" in styles


def test_reader_my_works_entry_and_preview_contract_is_present():
    reader_js = (ROOT / "src" / "narrativeos" / "web" / "reader.js").read_text(encoding="utf-8")
    reader_dom = (ROOT / "src" / "narrativeos" / "web" / "reader_dom.js").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")
    index_html = (ROOT / "src" / "narrativeos" / "web" / "index.html").read_text(encoding="utf-8")

    assert "readerJumpAuthoredWorks" in reader_dom
    assert "readerAuthoredWorkLibrary" in reader_dom
    assert "authoredWorkLibrary" in state_runtime
    assert "activeAuthoredWorkPreview" in state_runtime
    assert "我的作品" in index_html
    assert "像读者一样阅读" in reader_js
    assert "删除作品" in reader_js
    assert "refreshAuthoredWorkLibrary" in reader_js
    assert "openAuthoredWorkPreview" in reader_js
    assert "deleteAuthoredWork" in reader_js
    assert 'api(`/v1/author/works/${encodeURIComponent(workId)}`, { method: "DELETE" })' in reader_js
    assert "及其平行宇宙会一起移除" in reader_js
    assert "作者作品只读预览" in reader_js
    assert "登录作者账号后，这里会显示你自己创作的作品" in reader_js


def test_internal_ops_populated_and_account_copy_scripts_remain_wired():
    internal_populated_verify_text = (ROOT / "scripts" / "verify_ops_internal_populated_copy.js").read_text(encoding="utf-8")
    internal_account_verify_text = (ROOT / "scripts" / "verify_ops_internal_account_copy.js").read_text(encoding="utf-8")

    assert "inject_internal_ops_populated_data" in internal_populated_verify_text
    assert "verify_internal_ops_populated_cards" in internal_populated_verify_text
    assert "ops_populated_review_queue" in internal_populated_verify_text
    assert "ops_populated_world_status" in internal_populated_verify_text
    assert "ops_populated_runtime_snapshot" in internal_populated_verify_text
    assert "ops_populated_provider_routing" in internal_populated_verify_text
    assert "ops_populated_provider_rollout" in internal_populated_verify_text
    assert "ops_populated_provider_runtime_metrics" in internal_populated_verify_text
    assert "ops_populated_investigation_summary" in internal_populated_verify_text
    assert "ops_populated_investigation_evidence" in internal_populated_verify_text
    assert "ops_populated_eval_metrics" in internal_populated_verify_text
    assert "ops_populated_cross_pack_quality" in internal_populated_verify_text
    assert "schema_version" in internal_populated_verify_text
    assert "publish gate:" in internal_populated_verify_text
    assert "Provider Routing Policy" in internal_populated_verify_text
    assert "Continuation Drill-down" in internal_populated_verify_text
    assert "inject_internal_ops_account_data" in internal_account_verify_text
    assert "verify_internal_ops_account_cards" in internal_account_verify_text
    assert "ops_account_subscription_audit" in internal_account_verify_text
    assert "ops_account_subscription_timeline" in internal_account_verify_text
    assert "ops_account_workspace_timeline" in internal_account_verify_text
    assert "ops_account_support_issues" in internal_account_verify_text
    assert "ops_account_alert_feed" in internal_account_verify_text
    assert "ops_account_alert_detail" in internal_account_verify_text
    assert "ops_account_governance_summary" in internal_account_verify_text
    assert "ops_account_governance_cases" in internal_account_verify_text
    assert "ops_account_governance_detail" in internal_account_verify_text
    assert "ops_account_audit_breakdown" in internal_account_verify_text
    assert "ops_account_audit_trail" in internal_account_verify_text
    assert "schema_version" in internal_account_verify_text
    assert "subscriptions:" in internal_account_verify_text
    assert "Audit Breakdown" in internal_account_verify_text


def test_frontend_shell_summary_scripts_remain_wired():
    summary_text = (ROOT / "scripts" / "write_frontend_shell_smoke_step_summary.py").read_text(encoding="utf-8")
    internal_summary_text = (ROOT / "scripts" / "write_ops_internal_browser_guard_summary.py").read_text(encoding="utf-8")

    assert "Frontend Shell Smoke" in summary_text
    assert "Server Log Tail" in summary_text
    assert "Chrome Log Tail" in summary_text
    assert "Primary summary key" in summary_text
    assert "Result artifact" in summary_text
    assert "Primary summary key" in internal_summary_text
    assert "Result artifact" in internal_summary_text


def test_frontend_shell_core_assets_are_parseable_by_node():
    node = shutil.which("node")
    if not node:
      return

    assets = [
        ROOT / "src" / "narrativeos" / "web" / "reader.js",
        ROOT / "src" / "narrativeos" / "web" / "author_workspace.js",
        ROOT / "src" / "narrativeos" / "web" / "author_dom.js",
        ROOT / "src" / "narrativeos" / "web" / "agent_studio_dom.js",
        ROOT / "src" / "narrativeos" / "web" / "agent_studio.js",
        ROOT / "src" / "narrativeos" / "web" / "shell_bootstrap_runtime.js",
        ROOT / "src" / "narrativeos" / "web" / "shell_runtime.js",
        ROOT / "scripts" / "verify_public_shell_copy.js",
        ROOT / "scripts" / "verify_ops_internal_snapshot.js",
        ROOT / "scripts" / "verify_ops_internal_form_copy.js",
        ROOT / "scripts" / "verify_ops_internal_static_copy.js",
        ROOT / "scripts" / "verify_ops_internal_populated_copy.js",
        ROOT / "scripts" / "verify_ops_internal_account_copy.js",
    ]
    for asset in assets:
        subprocess.run(
            [node, "-e", f"new Function(require('fs').readFileSync({asset.as_posix()!r}, 'utf8'));"],
            check=True,
            cwd=ROOT,
        )

    subprocess.run(
        ["python3", "-m", "py_compile", str(ROOT / "scripts" / "write_ops_internal_browser_guard_summary.py")],
        check=True,
        cwd=ROOT,
    )


def test_author_steering_and_creative_cockpit_runtime_contract_is_present():
    author_runtime = (ROOT / "src" / "narrativeos" / "web" / "author_workspace.js").read_text(encoding="utf-8")
    author_dom = (ROOT / "src" / "narrativeos" / "web" / "author_dom.js").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")

    assert "createAuthorWorkBranchFromSteering" in author_runtime
    assert "resolveAuthorSteeringForkContext" in author_runtime
    assert "switchActiveAuthorWork" in author_runtime
    assert "setAuthorBranchExecutionState" in author_runtime
    assert "clearAuthorBranchExecutionState" in author_runtime
    assert "buildAuthorBranchExecutionPresentation" in author_runtime
    assert "/works/${encodeURIComponent(authorState.activeWorkId)}/branches" in author_runtime
    assert "/activate-line" in author_runtime
    assert "branch_family" in author_runtime
    assert "平行宇宙" in author_runtime
    assert "missing_simulation_context" in author_runtime
    assert "当前分叉点章节" in author_runtime
    assert "当前分叉点以你选中的章节为准" in author_runtime
    assert "主线后续章节不会复制到新宇宙" in author_runtime
    assert "sourceChapterIndex: Number(authorState.activeWorkDetail?.chapter_count" not in author_runtime
    assert "阅读预览只看标题和正文，不把章节摘要混进正文流" in author_runtime
    assert "chapterDetail.summary" not in author_runtime[author_runtime.index("const readingPreviewPanel"):author_runtime.index("const hintItems = [];")]
    assert "先在模拟报告里定位到当前章节，再创建新的命运线。" in author_runtime
    assert "renderAuthorSteeringComposer();" in author_runtime
    assert "runSteeredSimulation" in author_runtime
    assert "命运线执行状态" in author_runtime
    assert "创建分支成功" in author_runtime
    assert "创建新命运线失败" in author_runtime
    assert "当前分支已生成到第" in author_runtime
    assert "生成链路没有返回新的章节结果" in author_runtime
    assert "clearMismatchedAuthorDeepLinkContext" in author_runtime
    assert "错误深链参数已清除" in author_runtime
    assert "旧会话已清除" not in author_runtime
    assert "normalizeAuthorChoiceText" in author_runtime
    assert "prefillAuthorSteeringFromChoice" in author_runtime
    assert 'dom.authorSteeringIntent.value = choiceText' in author_runtime
    assert 'copy.textContent = normalizeAuthorChoiceText(choice) || JSON.stringify(choice);' in author_runtime
    assert "renderAuthorSteeringComposer" in author_runtime
    assert "renderAuthorCreativeCockpit" in author_runtime
    assert "openAuthorCharacterAsset" in author_runtime
    assert "openAuthorSceneAsset" in author_runtime
    assert "openAuthorTaskAsset" in author_runtime
    assert "openAuthorPriorityAsset" in author_runtime
    assert "openAuthorRepairLoopValidationPanel" in author_runtime
    assert "createRepairLoopSummaryCard" in author_runtime
    assert "buildDraftChangeContext" in author_runtime
    assert "currentAuthorRepairLoopResult" in author_runtime
    assert "WorkspaceLayoutRuntime" in author_runtime
    assert "ShellStatusRuntime" in author_runtime
    assert "authorBranchExecutionState" in state_runtime
    assert "author-run-steered-simulation" in author_dom
    assert "author-steering-intent" in author_dom
    assert "author-creative-cockpit" in author_dom


def test_ops_release_workspace_highlight_contract_is_present():
    ops_actions = (ROOT / "src" / "narrativeos" / "web" / "ops_actions.js").read_text(encoding="utf-8")
    ops_render = (ROOT / "src" / "narrativeos" / "web" / "ops_render_sections.js").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")

    assert "highlightOpsReleaseWorkspaceTarget" in ops_actions
    assert "selectedOpsReleaseBlockerKey" in ops_actions
    assert "selectedOpsReleaseBlockerCheckKey" in ops_actions
    assert "dataset.releaseBlockerKey" in ops_render
    assert "dataset.releaseBlockerCheckKey" in ops_render
    assert "selectedOpsReleaseBlockerKey" in state_runtime
    assert "selectedOpsReleaseBlockerCheckKey" in state_runtime


def test_reader_checkout_return_context_contract_is_present():
    reader_runtime = (ROOT / "src" / "narrativeos" / "web" / "reader.js").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")

    assert "narrativeos_reader_checkout_context" in reader_runtime
    assert "persistPendingCheckoutContext" in reader_runtime
    assert "restorePendingCheckoutContext" in reader_runtime
    assert "applyCheckoutContext" in reader_runtime
    assert "checkoutContext?.sessionId" in reader_runtime
    assert "checkoutContext?.accountId" in reader_runtime
    assert "pendingCheckoutContext" in state_runtime


def test_reader_shell_v2_polls_queued_generation_jobs():
    reader_shell = (ROOT / "src" / "narrativeos" / "web" / "reader_shell_v2.js").read_text(encoding="utf-8")
    state_runtime = (ROOT / "src" / "narrativeos" / "web" / "state_runtime.js").read_text(encoding="utf-8")

    assert "readerGenerationJob" in state_runtime
    assert "pollReaderGenerationJob" in reader_shell
    assert "/v1/reader/jobs/${encodeURIComponent(jobId)}" in reader_shell
    assert "reader_job_timeout" in reader_shell
    assert "reader_job_failed" in reader_shell
    assert "reader_ui_sync_stale" in reader_shell
    assert "reloadReaderSessionAfterGeneration" in reader_shell
    assert "生成中" in reader_shell


def test_frontend_shell_smoke_workflow_wires_headless_runner_and_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "frontend-shell-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert payload["name"] == "frontend-shell-smoke"
    assert set(payload["jobs"]) == {"smoke", "agent-studio-smoke"}
    smoke_job = payload["jobs"]["smoke"]
    steps = smoke_job["steps"]

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    run_step = next(step for step in steps if step.get("name") == "Run frontend shell smoke")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_frontend_shell_smoke.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish frontend shell smoke summary")
    summary_run = summary_step["run"]
    assert summary_step["if"] == "always()"
    assert "write_frontend_shell_smoke_step_summary.py" in summary_run
    assert "frontend_shell_smoke_result.json" in summary_run
    assert "frontend_shell_smoke_failure_snapshot.json" in summary_run
    assert "cp /tmp/frontend_shell_smoke_server.log artifacts/frontend_shell_smoke_server.log" in summary_run
    assert "cp /tmp/frontend_shell_smoke_chrome.log artifacts/frontend_shell_smoke_chrome.log" in summary_run
    assert "$GITHUB_STEP_SUMMARY" in summary_run

    artifact_step = next(step for step in steps if step.get("name") == "Upload frontend shell smoke artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/frontend_shell_smoke_result.json" in artifact_path
    assert "artifacts/frontend_shell_smoke_failure_snapshot.json" in artifact_path
    assert "artifacts/frontend_shell_smoke_failure.png" in artifact_path
    assert "artifacts/frontend_shell_smoke_server.log" in artifact_path
    assert "artifacts/frontend_shell_smoke_chrome.log" in artifact_path
    assert "/tmp/frontend_shell_smoke_server.log" not in artifact_path
    assert "/tmp/frontend_shell_smoke_chrome.log" not in artifact_path


def test_agent_studio_smoke_workflow_wires_headless_runner_and_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "frontend-shell-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    job = payload["jobs"]["agent-studio-smoke"]
    steps = job["steps"]

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    run_step = next(step for step in steps if step.get("name") == "Run Agent Studio smoke")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_agent_studio_smoke.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish Agent Studio smoke summary")
    summary_run = summary_step["run"]
    assert summary_step["if"] == "always()"
    assert "write_agent_studio_smoke_step_summary.py" in summary_run
    assert "agent_studio_smoke_result.json" in summary_run
    assert "agent_studio_smoke_failure_snapshot.json" in summary_run
    assert "cp /tmp/agent_studio_smoke_server.log artifacts/agent_studio_smoke_server.log" in summary_run
    assert "cp /tmp/agent_studio_smoke_chrome.log artifacts/agent_studio_smoke_chrome.log" in summary_run
    assert "$GITHUB_STEP_SUMMARY" in summary_run

    artifact_step = next(step for step in steps if step.get("name") == "Upload Agent Studio smoke artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/agent_studio_smoke_result.json" in artifact_path
    assert "artifacts/agent_studio_smoke_failure_snapshot.json" in artifact_path
    assert "artifacts/agent_studio_smoke_failure.png" in artifact_path
    assert "artifacts/agent_studio_smoke_desktop.png" in artifact_path
    assert "artifacts/agent_studio_smoke_mobile.png" in artifact_path
    assert "artifacts/agent_studio_smoke_visual_review.md" in artifact_path
    assert "artifacts/agent_studio_smoke_server.log" in artifact_path
    assert "artifacts/agent_studio_smoke_chrome.log" in artifact_path
    assert "/tmp/agent_studio_smoke_server.log" not in artifact_path
    assert "/tmp/agent_studio_smoke_chrome.log" not in artifact_path


def test_author_live_api_smoke_scripts_exist_and_are_parseable():
    run_script = ROOT / "scripts" / "run_author_live_api_smoke.sh"
    verify_script = ROOT / "scripts" / "verify_author_live_api_smoke.js"
    summary_script = ROOT / "scripts" / "write_author_live_api_smoke_step_summary.py"

    assert run_script.exists()
    assert verify_script.exists()
    assert summary_script.exists()

    run_text = run_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")
    summary_text = summary_script.read_text(encoding="utf-8")

    assert "author_live_api_smoke_result.json" in run_text
    assert "author_live_api_smoke_failure_snapshot.json" in run_text
    assert "author_live_api_smoke_failure.png" in run_text
    assert "AUTHOR_CHROME_PORT" in run_text
    assert "REVIEWER_CHROME_PORT" in run_text
    assert "AUTHOR_APP_URL" in run_text
    assert "REVIEWER_APP_URL" in run_text
    assert "stop_existing_debug_port" in run_text
    assert "verify_author_live_api_smoke.js" in run_text

    assert "author_live_api_smoke/v1" in verify_text
    assert "author_register_login" in verify_text
    assert "author_create_draft_from_brief" in verify_text
    assert "author_save_character_card" in verify_text
    assert "author_simulate_draft" in verify_text
    assert "author_request_review" in verify_text
    assert "reviewer_login" in verify_text
    assert "reviewer_open_inbox" in verify_text
    assert "reviewer_approve_request" in verify_text
    assert "author_submit_draft" in verify_text
    assert "author_brief_payload_world_title" in verify_text
    assert "reviewer_decision_status" in verify_text
    assert "author_submit_stage" in verify_text

    assert "Author Live API Smoke" in summary_text
    assert "author_brief_payload_world_title" in summary_text
    assert "author_saved_draft_version_id" in summary_text
    assert "reviewer_inbox_target_world_version_id" in summary_text
    assert "reviewer_decision_status" in summary_text
    assert "author_submit_stage" in summary_text
    assert "Reviewer Chrome Log Tail" in summary_text
    assert "Failed to load resource: the server responded with a status of 403" not in verify_text


def test_author_live_api_smoke_workflow_wires_headless_runner_and_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "author-live-api-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert payload["name"] == "author-live-api-smoke"
    smoke_job = payload["jobs"]["smoke"]
    steps = smoke_job["steps"]

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    run_step = next(step for step in steps if step.get("name") == "Run author live API smoke")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_author_live_api_smoke.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish author live API smoke summary")
    summary_run = summary_step["run"]
    assert summary_step["if"] == "always()"
    assert "write_author_live_api_smoke_step_summary.py" in summary_run
    assert "author_live_api_smoke_result.json" in summary_run
    assert "author_live_api_smoke_failure_snapshot.json" in summary_run
    assert "/tmp/author_live_api_smoke_author_chrome.log" in summary_run
    assert "/tmp/author_live_api_smoke_reviewer_chrome.log" in summary_run
    assert "$GITHUB_STEP_SUMMARY" in summary_run

    artifact_step = next(step for step in steps if step.get("name") == "Upload author live API smoke artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/author_live_api_smoke_result.json" in artifact_path
    assert "artifacts/author_live_api_smoke_failure_snapshot.json" in artifact_path
    assert "artifacts/author_live_api_smoke_failure.png" in artifact_path
    assert "/tmp/author_live_api_smoke_server.log" in artifact_path
    assert "/tmp/author_live_api_smoke_author_chrome.log" in artifact_path
    assert "/tmp/author_live_api_smoke_reviewer_chrome.log" in artifact_path


def test_ops_internal_browser_guard_workflow_wires_unified_entrypoint():
    workflow_path = ROOT / ".github" / "workflows" / "ops-internal-browser-guards.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert payload["name"] == "ops-internal-browser-guards"
    job = payload["jobs"]["guards"]
    steps = job["steps"]

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    run_step = next(step for step in steps if step.get("name") == "Run internal Ops browser guards")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_ops_internal_browser_guards.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish internal Ops browser guard summary")
    summary_run = summary_step["run"]
    assert summary_step["if"] == "always()"
    assert "write_ops_internal_browser_guard_summary.py" in summary_run
    assert "--artifacts-dir artifacts" in summary_run
    assert "$GITHUB_STEP_SUMMARY" in summary_run

    artifact_step = next(step for step in steps if step.get("name") == "Upload internal Ops browser guard artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/ops_internal_*_result.json" in artifact_path
    assert "artifacts/ops_internal_*_failure_snapshot.json" in artifact_path
    assert "artifacts/ops_internal_*.png" in artifact_path
