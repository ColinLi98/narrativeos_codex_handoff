# Deployment Runbook

## Scope

This runbook covers the current NarrativeOS Beta runtime:

- database schema lifecycle checks
- runtime backup creation
- migration apply / dry-run flow
- restore decision hints and verification snapshots
- recovery drill dry-run
- post-deploy verification
- rollback path

## Preflight

1. Check `GET /v1/ops/schema-lifecycle`.
2. Confirm `status` is `up_to_date` or `pending_migrations`.
3. Confirm `alembic.status` is `at_head`, `behind_head`, or `not_stamped`, and note `alembic.head_revision`.
4. Check `GET /v1/ops/data-integrity` and confirm `status` is `healthy` or repairable with only safe actions.
5. Create a runtime backup before changing schema or restarting the API.
6. Confirm `GET /health` returns `ok`.
7. Confirm `GET /v1/ops/provider-routing` reflects the intended candidate / renderer provider order.
8. Confirm `GET /v1/ops/recovery-drills` is intentionally empty or already has a recent usable drill artifact.
9. If backend is Postgres, confirm restore operator tooling is ready:
   - `pg_dump`
   - `pg_restore`
   - `psql`

## Deploy

1. Inspect lifecycle first:
   - `python -m src.narrativeos.persistence.migrations --database-url ... --dry-run`
   - `python -m src.narrativeos.persistence.migrations --database-url ... --alembic-current`
2. Inspect repair backlog:
   - `python -m src.narrativeos.services.data_integrity --database-url ...`
   - optional dry-run: `python -m src.narrativeos.services.data_integrity --database-url ... --action reconcile_session_chapter_pointers --action prune_orphan_route_choices`
3. Create a runtime backup and record its manifest path.
4. Run a recovery drill dry-run:
   - `POST /v1/ops/recovery-drill`
   - or use the latest backup path explicitly
5. If a real Postgres restore may be needed, submit the restore request and get a second operator approval:
   - `POST /v1/ops/runtime-restore/request`
   - `POST /v1/ops/runtime-restore/{request_id}/approve`
6. Apply migrations or stamp current schema lifecycle:
   - `python -m src.narrativeos.persistence.migrations --database-url ...`
7. If a future forward Alembic revision exists beyond the stamped baseline, run:
   - `python -m src.narrativeos.persistence.migrations --database-url ... --alembic-upgrade-head`
8. If safe repair actions are required before traffic shift, apply them:
   - `python -m src.narrativeos.services.data_integrity --database-url ... --apply --action reconcile_session_chapter_pointers --action prune_orphan_route_choices`
9. Restart the API process.
10. Verify:
   - `GET /health`
   - `GET /v1/ops/schema-lifecycle`
   - `GET /v1/ops/data-integrity`
   - `GET /v1/ops/runtime-incident-snapshot`
   - `GET /v1/ops/provider-runtime-metrics`
   - `GET /v1/ops/provider-routing`
   - `GET /v1/ops/recovery-drills`
   - optional local Ops control-plane smoke: `bash scripts/run_ops_navigation_stale_ref_smoke.sh`
   - CI/headless form: `CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_ops_navigation_stale_ref_smoke.sh`
11. Run benchmark / merge gate smoke checks.

## Rollback

1. Inspect `GET /v1/ops/runtime-incident-snapshot`.
2. Inspect `GET /v1/ops/schema-lifecycle` and record `alembic.current_revision` / `alembic.head_revision`.
3. Inspect `GET /v1/ops/data-integrity` and record any drift / orphan / duplicate-active backlog.
4. Compare the current runtime verification snapshot against the selected backup manifest.
5. If backend is Postgres, confirm the restore request is approved and not stale.
6. Execute the approved restore:
   - `POST /v1/ops/jobs/runtime-restores`
7. Re-check:
   - `GET /health`
   - `GET /v1/ops/schema-lifecycle`
   - `GET /v1/ops/data-integrity`
   - `GET /v1/ops/provider-runtime-metrics`
   - `GET /v1/ops/recovery-drills`
   - `GET /v1/ops/runtime-restore-requests`
   - benchmark / merge gate smoke

## Notes

- SQLite backups are executable in-repo.
- Postgres backup/restore remains the preferred production rollback path.
- The initial Alembic baseline revision is intentionally restore-first for rollback; do not treat `alembic downgrade` as a production data rollback substitute.
- Provider telemetry now includes runtime / candidate / renderer latency plus provider-level cost estimates; check those before and after changing provider order.
- Runtime backup manifests now carry verification snapshots; use them to compare table counts and schema/alembic state before and after restore.
- Postgres execution is now gated by explicit restore approval plus binary readiness; do not bypass the request/approve/execute sequence.

## Frontend Smoke Contract Appendix

- Run `run_frontend_shell_smoke.sh`, `run_reader_shell_smoke.sh`, `run_reader_storybook_long_route_smoke.sh`, and `run_author_repair_loop_smoke.sh` before marking UI-heavy work ready.
- Strong long-route benchmark evidence uses `--interactive-profile strong` and writes `benchmark_200_interactive.md`.
- Auth deep-link guardrails: initializing作品稿 still requires the matching author login, and object payloads must render as product copy 而不是显示 `[object Object]`.
- Author deep links should auto land on `账户协作` and prefill the expected author account, then auto resume to `/app?product=author&workspace=draft...`.
- Draft access must only happen after a real matching author session exists.
- If a route contains the wrong account, trust the Draft's real `author_id`, rewrite the route to that account, and clear that local session before showing the switch prompt.
- Reader checkout evidence: reader_checkout_status = completed.
- Long-route Reader storybook evidence: reader_seed_world_ids = [jade_court_exam, jade_court_romance, urban_mystery_lotus_lane], reader_seed_target_chapters = 30, reader_seed_reached_chapters >= 30, reader_storybook_visible_trajectory_count >= 3.
- Distinctness evidence: reader_storybook_sampled_quote_lengths / reader_storybook_sampled_beat_counts, reader_storybook_cross_pack_distinctness, passes_min_difference = true, reader_storybook_title_homogenization_warnings, reader_storybook_long_route_smoke_history.json, reader_storybook_title_homogenization_trend.
- Author smoke evidence: author_saved_draft_version_id, author_simulation_completed_chapters, author_simulate_latest_decision / freshness_status / next_focus_chapter / shortest_loop_relationship / review_hint, author_repair_loop_issue_code, author_repair_loop_asset_target / validation_panel / baseline_issue_count / current_issue_count / remaining_chapter_count, author_workflow_recommended_action_after_simulation.
- Ops smoke evidence: ops_mutation_tier_id = creator_pass, ops_governance_case_id, ops_governance_case_type / case_severity / case_target_type / case_target_id, ops_governance_case_status = open, ops_governance_case_status_after_transition = in_review, ops_governance_evidence_count_after_append, ops_governance_restriction_type = checkout_block, ops_governance_restriction_state = active, ops_governance_case_status_after_release = resolved, ops_governance_restriction_state_after_release = released.
- Governance denial evidence: ops_governance_non_owner_resolve_status = 403, ops_governance_non_owner_resolve_code = governance_case_owner_required, ops_governance_non_owner_resolve_endpoint, ops_governance_non_owner_denial_expected_owner_id / action_label / denial_kind, ops_governance_case_status_after_owner_resolution = resolved, ops_governance_case_status_after_dismiss = dismissed.

## Local Dev URL Contract

Manual local browser verification keeps fixed ports: `http://127.0.0.1:3000` for frontend and `http://127.0.0.1:8000` for backend. The dynamic-port behavior exists to avoid CI job collisions.
