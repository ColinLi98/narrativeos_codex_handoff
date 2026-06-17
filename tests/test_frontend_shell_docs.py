from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_runbook_mentions_frontend_shell_smoke_summary():
    runbook = (ROOT / "docs" / "deployment_runbook.md").read_text(encoding="utf-8")
    assert "run_frontend_shell_smoke.sh" in runbook
    assert "run_reader_shell_smoke.sh" in runbook
    assert "run_reader_storybook_long_route_smoke.sh" in runbook
    assert "run_author_repair_loop_smoke.sh" in runbook
    assert "--interactive-profile strong" in runbook
    assert "benchmark_200_interactive.md" in runbook
    assert "initializing作品稿 still requires the matching author login" in runbook
    assert "而不是显示 `[object Object]`" in runbook
    assert "auto land on `账户协作` and prefill the expected author account" in runbook
    assert "auto resume to `/app?product=author&workspace=draft...`" in runbook
    assert "must only happen after a real matching author session exists" in runbook
    assert "trust the Draft's real `author_id`, rewrite the route to that account" in runbook
    assert "clear that local session before showing the switch prompt" in runbook
    assert "reader_checkout_status = completed" in runbook
    assert "reader_seed_world_ids = [jade_court_exam, jade_court_romance, urban_mystery_lotus_lane]" in runbook
    assert "reader_seed_target_chapters = 30" in runbook
    assert "reader_seed_reached_chapters >= 30" in runbook
    assert "reader_storybook_visible_trajectory_count >= 3" in runbook
    assert "reader_storybook_sampled_quote_lengths / reader_storybook_sampled_beat_counts" in runbook
    assert "reader_storybook_cross_pack_distinctness" in runbook
    assert "passes_min_difference = true" in runbook
    assert "reader_storybook_title_homogenization_warnings" in runbook
    assert "reader_storybook_long_route_smoke_history.json" in runbook
    assert "reader_storybook_title_homogenization_trend" in runbook
    assert "author_saved_draft_version_id" in runbook
    assert "author_simulation_completed_chapters" in runbook
    assert "author_simulate_latest_decision / freshness_status / next_focus_chapter / shortest_loop_relationship / review_hint" in runbook
    assert "author_repair_loop_issue_code" in runbook
    assert "author_repair_loop_asset_target / validation_panel / baseline_issue_count / current_issue_count / remaining_chapter_count" in runbook
    assert "author_workflow_recommended_action_after_simulation" in runbook
    assert "ops_mutation_tier_id = creator_pass" in runbook
    assert "ops_governance_case_id" in runbook
    assert "ops_governance_case_type / case_severity / case_target_type / case_target_id" in runbook
    assert "ops_governance_case_status = open" in runbook
    assert "ops_governance_case_status_after_transition = in_review" in runbook
    assert "ops_governance_evidence_count_after_append" in runbook
    assert "ops_governance_restriction_type = checkout_block" in runbook
    assert "ops_governance_restriction_state = active" in runbook
    assert "ops_governance_case_status_after_release = resolved" in runbook
    assert "ops_governance_restriction_state_after_release = released" in runbook
    assert "ops_governance_non_owner_resolve_status = 403" in runbook
    assert "ops_governance_non_owner_resolve_code = governance_case_owner_required" in runbook
    assert "ops_governance_non_owner_resolve_endpoint" in runbook
    assert "ops_governance_non_owner_denial_expected_owner_id / action_label / denial_kind" in runbook
    assert "ops_governance_case_status_after_owner_resolution = resolved" in runbook
    assert "ops_governance_case_status_after_dismiss = dismissed" in runbook


def test_quantum_local_dev_url_contract_keeps_manual_ports_fixed_and_ci_ports_isolated():
    runbook = (ROOT / "docs" / "deployment_runbook.md").read_text(encoding="utf-8")
    quantum_readme = (ROOT / "Kimi_Agent_设计系统加载" / "app" / "README.md").read_text(encoding="utf-8")
    browser_display = (ROOT / "docs" / "browser_display_test_generated_chapters.md").read_text(encoding="utf-8")
    illustration_pipeline = (ROOT / "docs" / "reader_illustration_pipeline.md").read_text(encoding="utf-8")
    api_mapping = (ROOT / "docs" / "quantum_frontend_backend_api_mapping.md").read_text(encoding="utf-8")

    for text in [runbook, quantum_readme, browser_display, illustration_pipeline, api_mapping]:
        assert "http://127.0.0.1:3000" in text
        assert "http://127.0.0.1:8000" in text

    assert "Local Dev URL Contract" in runbook
    assert "Local URL Contract" in quantum_readme
    assert "manual local browser verification" in quantum_readme.lower()
    assert "CI/headless smoke scripts are the exception" in quantum_readme
    assert "dynamic-port behavior exists to avoid CI job collisions" in runbook
    assert "CI/headless smoke scripts may still set isolated `BACKEND_PORT` / `FRONTEND_PORT`" in api_mapping

    assert "NARRATIVEOS_API_ORIGIN=http://127.0.0.1:8017 npm run dev" not in browser_display
    assert "APP_PORT=8013 ./scripts/run_backend_local.sh" not in illustration_pipeline
    assert "--backend-url http://127.0.0.1:8013" not in illustration_pipeline
    assert "NARRATIVEOS_API_ORIGIN=http://127.0.0.1:8013 npm run dev -- --host 127.0.0.1 --port 3003" not in illustration_pipeline

    smoke_defaults = {
        "run_quantum_ops_url_state_smoke.sh": ("8012", "3001"),
        "run_quantum_library_smoke.sh": ("8013", "3002"),
        "run_quantum_author_follow_smoke.sh": ("8014", "3003"),
    }
    for script_name, (backend_port, frontend_port) in smoke_defaults.items():
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert f'BACKEND_PORT="${{BACKEND_PORT:-{backend_port}}}"' in script
        assert f'FRONTEND_PORT="${{FRONTEND_PORT:-{frontend_port}}}"' in script
        assert 'BACKEND_PORT="${BACKEND_PORT:-8000}"' not in script
        assert 'FRONTEND_PORT="${FRONTEND_PORT:-3000}"' not in script


def test_handoff_and_dispatch_docs_capture_frontend_shell_smoke_and_next_mutation():
    handoff = (ROOT / "docs" / "gpt_handoff_status_and_commercialization.md").read_text(encoding="utf-8")
    dispatch = (ROOT / "narrativeos_codex_execution_dossier" / "06_RECURRING_DISPATCH_PROTOCOL.md").read_text(encoding="utf-8")

    assert "frontend shell smoke" in handoff
    assert "run_author_repair_loop_smoke.sh" in handoff
    assert "reader_checkout_status = completed" in handoff
    assert "author_saved_draft_version_id" in handoff
    assert "author_simulation_completed_chapters" in handoff
    assert "author_simulate_latest_decision / freshness_status / next_focus_chapter / shortest_loop_relationship / review_hint" in handoff
    assert "author_repair_loop_issue_code" in handoff
    assert "author_repair_loop_asset_target / validation_panel / baseline_issue_count / current_issue_count / remaining_chapter_count" in handoff
    assert "ops_governance_case_id" in handoff
    assert "ops_governance_case_type / case_severity / case_target_type / case_target_id" in handoff
    assert "ops_governance_case_status_after_transition = in_review" in handoff
    assert "ops_governance_evidence_count_after_append" in handoff
    assert "ops_governance_restriction_type = checkout_block" in handoff
    assert "ops_governance_case_status_after_release = resolved" in handoff
    assert "ops_governance_non_owner_resolve_status = 403" in handoff
    assert "ops_governance_non_owner_resolve_code = governance_case_owner_required" in handoff
    assert "ops_governance_non_owner_resolve_endpoint" in handoff
    assert "ops_governance_non_owner_denial_expected_owner_id / action_label / denial_kind" in handoff
    assert "ops_governance_case_status_after_owner_resolution = resolved" in handoff
    assert "ops_governance_case_status_after_dismiss = dismissed" in handoff
    assert "Ops governance dismiss button interaction coverage" in handoff
    assert "frontend shell smoke summary" in dispatch
    assert "author_saved_draft_version_id" in dispatch
    assert "author_simulation_completed_chapters" in dispatch
    assert "author_workflow_recommended_action_after_simulation" in dispatch
    assert "ops_mutation_tier_id" in dispatch
    assert "ops_governance_case_id" in dispatch
    assert "ops_governance_case_status" in dispatch
    assert "ops_governance_case_type" in dispatch
    assert "ops_governance_case_severity" in dispatch
    assert "ops_governance_case_target_type" in dispatch
    assert "ops_governance_case_target_id" in dispatch
    assert "ops_governance_case_status_after_transition" in dispatch
    assert "ops_governance_evidence_count_after_append" in dispatch
    assert "ops_governance_restriction_type" in dispatch
    assert "ops_governance_restriction_state" in dispatch
    assert "ops_governance_case_status_after_release" in dispatch
    assert "ops_governance_restriction_state_after_release" in dispatch
    assert "ops_governance_non_owner_resolve_status" in dispatch
    assert "ops_governance_non_owner_resolve_code" in dispatch
    assert "ops_governance_non_owner_resolve_endpoint" in dispatch
    assert "ops_governance_non_owner_denial_expected_owner_id" in dispatch
    assert "ops_governance_non_owner_denial_action_label" in dispatch
    assert "ops_governance_non_owner_denial_kind" in dispatch
    assert "ops_governance_case_status_after_owner_resolution" in dispatch
    assert "ops_governance_case_status_after_dismiss" in dispatch


def test_commercialization_handoff_and_next_phase_docs_capture_v1_completion_standard():
    handoff = (ROOT / "docs" / "gpt_handoff_status_and_commercialization.md").read_text(encoding="utf-8")
    frontend = (ROOT / "docs" / "frontend_shell_rebuild.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "narrativeos_codex_next_phase" / "01_90_DAY_EXECUTION_PLAN.md").read_text(encoding="utf-8")
    metrics = (ROOT / "narrativeos_codex_next_phase" / "07_ACCEPTANCE_METRICS.md").read_text(encoding="utf-8")
    next_phase = (ROOT / "narrativeos_codex_next_phase" / "README.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "商业化 v1 最终完成态标准" in handoff
    assert "内容质量与阅读价值必须达标" in handoff
    assert "接下来实施计划" in handoff
    assert "Phase A" in roadmap
    assert "把内容质量变成真正的发布门槛" in roadmap
    assert "Phase F" in roadmap
    assert "Author 供给效率" in metrics
    assert "Learned 数据飞轮" in metrics
    assert "Infra 与可靠性" in metrics
    assert "商业化 v1 完成态标准" in next_phase
    assert "最终商业化 v1 完成态" in readme
    assert "run_reader_shell_smoke.sh" in frontend
    assert "run_reader_storybook_long_route_smoke.sh" in frontend
    assert "run_agent_studio_smoke.sh" in frontend
    assert "agent_studio_smoke_visual_review.md" in frontend
    assert "visual review checklist" in frontend.lower()
    assert "Reader-only smoke" in frontend
    assert "long-route Reader storybook smoke" in frontend
    assert "jade_court_exam,jade_court_romance,urban_mystery_lotus_lane" in frontend
    assert "title_similarity / quote_similarity / passes_min_difference" in frontend
    assert "reader_storybook_title_homogenization_warnings / warning_count" in frontend
    assert "reader_storybook_long_route_smoke_history.json" in frontend
    assert "reader_storybook_title_homogenization_history_summary / trend / promoted_pairs" in frontend
    assert "interactive-profile strong" in readme
    assert "benchmark_200_interactive.md" in readme


def test_agent_studio_layout_pr_review_convention_is_documented():
    pr_template = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    review_template = (ROOT / "narrativeos_codex_execution_dossier" / "03_CODEX_PR_REVIEW_TEMPLATE.md").read_text(encoding="utf-8")
    studio_doc = (ROOT / "docs" / "agent_studio_interactive_workbench.md").read_text(encoding="utf-8")
    frontend_doc = (ROOT / "docs" / "frontend_shell_rebuild.md").read_text(encoding="utf-8")

    for text in [pr_template, review_template, studio_doc, frontend_doc]:
        assert "agent_studio_smoke_visual_review.md" in text
        assert "manual_review" in text
        assert "desktop / Three-column workbench review / manual_review" in text
        assert "mobile / Stacked workbench review / manual_review" in text
        assert "accepted" in text
        assert "needs follow-up" in text

    assert "Agent Studio layout CSS" in pr_template
    assert "Agent Studio layout CSS touched: [ ] yes / [ ] no" in pr_template
    assert "src/narrativeos/web/styles.css" in pr_template
    assert ".agent-studio-*" in pr_template
    assert "Agent Studio layout CSS touched: [ ] yes / [ ] no" in review_template
    assert "Agent Studio layout CSS changed and the PR lacks the pasted `manual_review` rows" in review_template
    assert "human visual triage" in frontend_doc

    forbidden = ["pixel", "golden", "snapshot comparison"]
    combined = "\n".join([pr_template, review_template, studio_doc, frontend_doc]).lower()
    for phrase in forbidden:
        assert phrase not in combined


def test_agent_studio_docs_define_codex_nosbook_upload_workflow():
    studio_doc = (ROOT / "docs" / "agent_studio_interactive_workbench.md").read_text(encoding="utf-8")
    frontend_doc = (ROOT / "docs" / "frontend_shell_rebuild.md").read_text(encoding="utf-8")
    api_contracts = (ROOT / "docs" / "07_api_contracts.md").read_text(encoding="utf-8")
    upload_script = (ROOT / "scripts" / "upload_nosbook.py").read_text(encoding="utf-8")

    for text in [studio_doc, frontend_doc, api_contracts]:
        assert "POST /v1/author/nosbooks/import" in text
        assert "nosbook_import_result/v1" in text
        assert "private_draft" in text
        assert "source_only" in text

    for text in [studio_doc, frontend_doc]:
        assert "NARRATIVEOS_PLATFORM_URL" in text
        assert "NARRATIVEOS_PLATFORM_TOKEN" in text
        assert "NARRATIVEOS_LOCAL_STUDIO_URL" in text
        assert "NARRATIVEOS_LOCAL_STUDIO_TOKEN" in text
        assert "scripts/upload_nosbook.py --file" in text
        assert "scripts/upload_nosbook.py --local-work-id" in text
        assert "does not print or persist the token" in text

    assert "nosbook_import_auth_required" in api_contracts
    assert "author_work_chapters" in api_contracts

    assert "NOSBOOK_CONTENT_TYPE" in upload_script
    assert "application/vnd.narrativeos.nosbook+json" in upload_script
    assert "/v1/author/nosbooks/import" in upload_script
    assert "--local-work-id" in upload_script
    assert "NARRATIVEOS_LOCAL_STUDIO_URL" in upload_script
    assert "NARRATIVEOS_LOCAL_STUDIO_TOKEN" in upload_script
    assert "http://127.0.0.1:8000" in upload_script
    assert "local_export_invalid_nosbook" in upload_script
    assert "Authorization" in upload_script
    assert "NARRATIVEOS_PLATFORM_TOKEN" in upload_script
