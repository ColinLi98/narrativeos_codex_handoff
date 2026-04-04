# Preflight Verification Bundle

## Purpose

The preflight verification bundle is the compact, operator-facing summary used before a deploy or runtime change.

It combines:

- deployment health gate
- deployment runbook
- incident playbook
- restore verification steps
- recommended verification commands

## Current checks

- database connectivity
- schema lifecycle state
- recent backup availability / freshness
- restore readiness
- Postgres operator tooling readiness
- runtime incident pressure

## Expected usage

1. Review `GET /v1/ops/deployment-health-gate`
2. Review `GET /v1/ops/preflight-verification-bundle`
3. Run the suggested verification commands
4. If gate is `block`, do not proceed
5. If gate is `warn`, proceed only with operator review
6. If gate is `pass`, continue with deploy runbook
