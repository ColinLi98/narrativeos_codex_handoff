# NarrativeOS Codex Recurring Dispatch Protocol

This file is the standing operating overlay for future Codex task dispatch.

Read order for future tasks:
1. repo-root `AGENTS.md`
2. this protocol
3. the concrete issue/task prompt

## Canonical lane taxonomy

Use these six lanes going forward:

- `Lane A` — Cross-pack quality
- `Lane B` — Author supply
- `Lane C` — Monetization / accounts / billing
- `Lane D` — Ops / governance
- `Lane E` — Learned evaluator / reranker / data flywheel
- `Lane F` — Production infra / routing / observability

One task belongs to one lane only unless the task is explicitly about boundaries between lanes.

## Phase order

Always prefer this commercialization sequence:

1. `Phase 0` — guardrails and task discipline
2. `Phase 1` — commercial-grade content quality
3. `Phase 2` — author supply efficiency
4. `Phase 3` — entitlements / accounts / billing closure
5. `Phase 4` — ops / governance maturity
6. `Phase 5` — learned layer becomes product-improving
7. `Phase 6` — production infra

## Standard dispatch workflow

For each new task:

1. Pick exactly one lane.
2. Confirm the task belongs to the right phase.
3. Start with Ask / Plan mode.
4. Reject any plan that:
   - centers on one pack’s prose
   - lacks tests / docs / benchmark thinking
   - lacks cross-pack evidence
   - lacks rollback thinking
5. Only then move to execution.

## Standard task prompt format

Every task should include these sections:

- `Title`
  - use `[Lane X / Phase Y / Task Z] <task name>`
- `Background`
- `Goal`
- `Non-goals`
- `Scope`
- `Acceptance`
- `Required output format`

For non-trivial tasks, explicitly require:

- read root `AGENTS.md` first
- output implementation plan before coding
- include goal / touched modules / test plan / benchmark-eval plan / rollback point
- forbid pack-specific prose tuning

## Required evidence from every implementation task

Every Codex delivery must include:

- changed files
- what changed
- tests run and result
- benchmark / eval delta or why not applicable
- strongest / weakest pack effect if applicable
- risks
- rollback point
- next suggested task

## Weekly operating rhythm

- Monday: one Ask / Plan task only
- Tuesday to Thursday: one narrow implementation task per day
- Friday: regression / benchmark review and lane reprioritization only

Avoid:

- multiple broad lanes in the same week
- “commercialize everything” mega-prompts
- accepting work without benchmark / tests / docs

## Current priority queue

Use this default order unless product priorities explicitly change:

1. `[Lane A / Phase 0 / Task 0.3]` Merge gate with cross-pack quality deltas
2. `[Lane A / Phase 1 / Task 1.2]` Long-route benchmark
3. `[Lane A / Phase 1 / Task 1.3]` Q03 / Q04 / Q05 / Q09 remediation framework
4. `[Lane B / Phase 2]` Author drill-down and diff tooling
5. `[Lane C / Phase 3]` Account / role / entitlement / wallet / subscription closure
6. `[Lane D / Phase 4]` Account detail + full audit trail
7. `[Lane E / Phase 5]` Learned data ingestion and promotion pipeline
8. `[Lane F / Phase 6]` Postgres / Alembic / routing / observability

## Permanent non-goals

Never accept these as platform progress:

- pack-specific prose tuning presented as system improvement
- one-pack wins without cross-pack evidence
- broad unrelated refactors in a narrow task
- hidden policy changes without rollback visibility

## Frontend Shell Smoke Summary Contract

Every frontend shell smoke summary should preserve these evidence keys:

- author_saved_draft_version_id
- author_simulation_completed_chapters
- author_workflow_recommended_action_after_simulation
- ops_mutation_tier_id
- ops_governance_case_id
- ops_governance_case_status
- ops_governance_case_type
- ops_governance_case_severity
- ops_governance_case_target_type
- ops_governance_case_target_id
- ops_governance_case_status_after_transition
- ops_governance_evidence_count_after_append
- ops_governance_restriction_type
- ops_governance_restriction_state
- ops_governance_case_status_after_release
- ops_governance_restriction_state_after_release
- ops_governance_non_owner_resolve_status
- ops_governance_non_owner_resolve_code
- ops_governance_non_owner_resolve_endpoint
- ops_governance_non_owner_denial_expected_owner_id
- ops_governance_non_owner_denial_action_label
- ops_governance_non_owner_denial_kind
- ops_governance_case_status_after_owner_resolution
- ops_governance_case_status_after_dismiss
