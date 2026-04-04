# Incident Playbook

## Trigger

Use this playbook when any of the following rises in `GET /v1/ops/runtime-incident-snapshot`:

- `provider_error`
- `budget_blocked`
- `fallback_used`
- schema lifecycle not `up_to_date`

## Triage

1. Inspect latest runtime receipts for the affected account or session.
2. Check selected provider, fallback usage, and backend error.
3. Check whether incidents are isolated to one surface:
   - `reader`
   - `session_api`
4. Check schema lifecycle before making runtime changes.

## Recovery

- If provider errors dominate:
  switch provider order or disable the failing provider.
- If budget blocks dominate:
  raise guardrails or reduce prompt payload size.
- If fallback usage spikes:
  compare fallback rate against recent receipts before rollout changes.
- If schema lifecycle is degraded:
  stop runtime changes until migrations are reconciled.

## Backup / Restore

Before destructive recovery actions:

1. create a runtime backup
2. record the backup path
3. compare current runtime verification against the backup manifest verification snapshot
4. run a recovery drill dry-run if time permits
5. for Postgres, ensure the restore request is approved by a second operator
6. restore only from a known-good snapshot
