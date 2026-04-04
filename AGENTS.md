# AGENTS.md — NarrativeOS Codex Operating Contract

## 1) What this repository is

NarrativeOS is **not** a single-script demo and **not** a prose-only project.
It is a **commercializing narrative kernel** with:

- multi World Pack runtime
- Karma Character Engine
- Reader / Author / Ops surfaces
- NarrativeEval + cross-pack benchmark
- learned governance
- early membership / entitlement rails

Treat the repo as a **kernel-first, capability-first product system**.

## 2) Current stage

The project is best understood as a **commercializable Beta kernel**, not a finished paid product.
The biggest remaining gaps are:

1. content quality stability across packs and long routes
2. author supply efficiency
3. learned layer becoming real model improvement, not only governance
4. account / subscription / payment / audit closure
5. production-grade infra and observability

## 3) North star

Do not optimize for “the current chapter looks nicer.”
Optimize for:

- cross-pack quality stability
- 30–50 chapter readability
- clear Reader value
- scalable Author supply
- safe Ops governance
- measurable monetization readiness

## 4) Hard constraints

### 4.1 Kernel-first
Never optimize only the current pack.
No pack-specific prose tuning unless the task explicitly says so.
Every meaningful change must either:

- improve a kernel capability, or
- improve diagnostics that reveal cross-pack weakness

### 4.2 Keep boundaries clean

Maintain strict separation between:

- `src/narrativeos/core/` → generic engine and capability contracts
- `src/narrativeos/worldpacks/` → pack assets, policies, content data
- `src/narrativeos/services/`, `api/`, `persistence/` → product/runtime system
- `/app` → Reader / Author / Ops product shell

Core must not silently depend on one specific world pack.

### 4.3 No illegal code import
Do **not** import, copy, adapt, or derive code from leaked / reverse-engineered repositories.
Use only official APIs / SDKs behind provider boundaries.

### 4.4 Preserve repo health
Every task must keep these green unless the task explicitly changes them:

- test suite
- demo run path
- health endpoint
- benchmark CLI
- Reader / Author / Ops boot path

## 5) What Codex should NOT do

Do not:

- keep polishing one Jade Court route while ignoring weakest packs
- solve narrative quality by adding meta explanation
- merge large unrelated refactors into a single task
- replace explicit quality gates with hand-wavy prompt changes
- introduce “unlimited” member entitlements
- bypass Ops / Eval / audit trails for convenience

## 6) Current priority ladder

### P0 — Commercially usable content quality
Focus first on:

- weakest pack diagnostics
- long-route benchmark (30–50 chapter)
- reducing `Q03 / Q04 / Q05 / Q09`
- mid-arc quality stability
- correlation between quality metrics and real continuation

### P1 — Author supply system
Focus next on:

- better draft detail experience
- character card / scene blueprint / pacing / hook editing
- simulation drill-down
- asset diff
- supply-side speed and clarity

### P2 — Ops + monetization closure
Then build:

- entitlement auditability
- subscription lifecycle closure
- account/role ownership
- moderation / rights / abuse handling
- publish / rollback / supportability

### P3 — Learned model layer
Then push from governance to real enhancement:

- better human review coverage
- preference / ranking data quality
- evaluator / reranker promotion evidence
- measured effect on retention / monetization signals

## 7) Membership / entitlement direction

Current commercial direction assumes three paid tiers:

- **Play Pass — $10/mo**
- **Creator Pass — $20/mo**
- **Studio Pass — $60/mo**

All membership work must be implemented as:

- entitlement matrix
- story credits wallet
- studio credits wallet
- subscription state machine
- Reader gating
- Author gating
- Ops audit / grant / revoke
- analytics events

Do not hardcode tier logic in UI components.
Use central config + policy checks.

## 8) Definition of done for any task

A task is **not done** unless it includes all of the following:

1. implementation
2. tests
3. docs update
4. benchmark / eval impact when relevant
5. explicit risks / follow-ups

Required final report format:

- changed files
- what changed
- tests run and result
- benchmark / eval delta or why not applicable
- strongest / weakest pack effect if applicable
- risks
- rollback point
- next recommended task

## 9) Task sizing and workflow

### 9.1 Start in Ask / Plan mode
For non-trivial tasks, first produce:

- implementation plan
- goal
- touched modules
- risks
- test plan
- benchmark / eval plan
- rollback point
- validation plan

Do not jump straight into code.

### 9.2 Keep tasks narrow
Preferred task size:

- one coherent engineering objective
- ideally ~1 hour human equivalent
- a few files, not half the repo

### 9.3 Avoid opportunistic extras
Do not “while I’m here” large-scope unrelated changes.

### 9.4 Use the standard task label
Every dispatched task should be titled:

- `[Lane X / Phase Y / Task Z] <task name>`

Use exactly one lane per task unless the task is explicitly about boundaries between lanes.

### 9.5 Use the standard task payload
When dispatching work, include:

- `Background`
- `Goal`
- `Non-goals`
- `Scope`
- `Acceptance`
- `Required output format`

For recurring dispatch rhythm and lane sequencing, see:

- [narrativeos_codex_execution_dossier/06_RECURRING_DISPATCH_PROTOCOL.md](/Users/lili/Desktop/narrativeos_codex_handoff/narrativeos_codex_execution_dossier/06_RECURRING_DISPATCH_PROTOCOL.md)

## 10) Quality gates

Use the project taxonomy and keep it visible:

- `Q01` engineering leak
- `Q02` meta narration leak
- `Q03` repetition
- `Q04` over-explanation
- `Q05` lack of scene detail
- `Q06` character inconsistency
- `Q07` causal discontinuity
- `Q08` weak choice distinctness
- `Q09` pacing failure / premature ending
- `Q10` product continuity failure

When fixing quality, identify:

- which issue classes are targeted
- which module owns the fix
- how success is measured

## 11) Required metrics discipline

When applicable, report deltas on:

- cross-pack pass rate
- weakest packs status
- long-route survival / continuation proxies
- Q03/Q04/Q05/Q09 rates
- Reader continuation correlation if available
- membership gating correctness if touched
- wallet / entitlement audit correctness if touched

Never report only “Jade Court improved.”

## 12) Current operating lanes

### Lane A — Cross-pack Quality
Examples:

- weakest pack diagnostics
- long-route benchmark
- issue heatmap
- metric correlation
- benchmark report improvements

### Lane B — Author Supply
Examples:

- draft detail
- asset editors
- validation/simulation drill-down
- supply workflow speed

### Lane C — Monetization & Accounts
Examples:

- tier config / entitlements
- wallets / credits
- subscriptions / billing
- web checkout provider integration
- account ownership
- auditability

### Lane D — Ops & Governance
Examples:

- review history
- publish checklist
- rollback trace
- moderation / rights / abuse flows
- support tooling

### Lane E — Learned Layer
Examples:

- review sample ingestion
- issue-fix / preference pipelines
- evaluator / reranker promotion evidence
- shadow compare and safe rollout

### Lane F — Infra / Reliability
Examples:

- Postgres migrations
- retries / fallback / routing
- observability
- deployment / backup / recovery

## 13) Immediate next tasks (default order)

Unless explicitly overridden, work in this order:

1. `[Lane A / Phase 0 / Task 0.3]` Merge gate with cross-pack quality deltas
2. `[Lane A / Phase 1 / Task 1.2]` Long-route benchmark (30–50 chapter)
3. `[Lane A / Phase 1 / Task 1.3]` Q03/Q04/Q05/Q09 targeted remediation framework
4. `[Lane B / Phase 2]` Author drill-down tools
5. `[Lane C / Phase 3]` Account / entitlement / subscription closure
6. `[Lane D / Phase 4]` Audit trail and ops detail pages
7. `[Lane E / Phase 5]` Learned data ingestion and promotion evidence
8. `[Lane F / Phase 6]` Postgres / routing / observability hardening

## 14) Reader-facing principle

User-visible output must feel like:

- a readable serialized narrative
- with stable chapter quality
- with meaningful continuation pressure
- and clear value after paying

Not like:

- system commentary
- planner notes
- benchmark language
- hidden engine labels leaking into prose

## 15) If uncertain

When uncertain, prefer:

- better diagnostics over blind tuning
- kernel capability over pack-local polish
- auditable policy over hidden branching
- reversible change over fragile rewrite
