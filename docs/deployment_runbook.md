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
