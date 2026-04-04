# Deployment Runbook

## Scope

This runbook covers the current NarrativeOS Beta runtime:

- database schema lifecycle checks
- runtime backup creation
- migration apply / dry-run flow
- post-deploy verification
- rollback path

## Preflight

1. Check `GET /v1/ops/schema-lifecycle`.
2. Confirm `status` is `up_to_date` or `pending_migrations`.
3. Create a runtime backup before changing schema or restarting the API.
4. Confirm `GET /health` returns `ok`.

## Deploy

1. Apply migrations or run `python -m src.narrativeos.persistence.migrations --dry-run`.
2. Restart the API process.
3. Verify:
   - `GET /health`
   - `GET /v1/ops/schema-lifecycle`
   - `GET /v1/ops/runtime-incident-snapshot`
   - optional local Ops control-plane smoke: `bash scripts/run_ops_navigation_stale_ref_smoke.sh`
   - CI/headless form: `CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_ops_navigation_stale_ref_smoke.sh`
4. Run benchmark / merge gate smoke checks.

## Rollback

1. Inspect `GET /v1/ops/runtime-incident-snapshot`.
2. Restore the latest known-good backup.
3. Re-check:
   - `GET /health`
   - `GET /v1/ops/schema-lifecycle`
   - benchmark / merge gate smoke

## Notes

- SQLite backups are executable in-repo.
- Postgres remains plan-oriented for backup/restore in this phase.
