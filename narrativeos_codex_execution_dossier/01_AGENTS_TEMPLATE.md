# AGENTS.md (template for NarrativeOS)

## Repo mission
NarrativeOS is a commercial beta kernel for multi-world interactive narrative, not a single-pack writing project.

## Core operating rules
1. Default to kernel-first / capability-first / product-first work.
2. Do NOT default to pack-specific prose tuning.
3. Every substantial task should start in Ask mode with an implementation plan, then move to Code mode.
4. Scope each task to one PR-sized change, ideally about one hour of human work or a few hundred LOC.
5. Every task must update tests and relevant docs.
6. Every meaningful PR must show cross-pack evidence, not just improvement in one world pack.
7. One PR should belong to one main lane only:
   - Lane A Cross-pack Quality
   - Lane B Author Supply
   - Lane C Monetization / Accounts / Billing
   - Lane D Ops & Governance
   - Lane E Learned Layer
   - Lane F Infra & Reliability
8. Use task labels in the form `[Lane X / Phase Y / Task Z] <task name>`.
9. For non-trivial tasks, Ask-mode plans must include goal, touched modules, tests, benchmark/eval plan, and rollback point.

## Definition of done
A task is not done unless it includes:
- code changes
- tests
- docs update
- validation output
- benchmark delta when relevant

## Default non-goals
- Do not “just improve the current script”
- Do not optimize only jade_court_exam_pack / jade_court_romance_pack
- Do not introduce broad unrelated refactors
- Do not mix multiple lanes in one PR unless explicitly requested

## Validation commands
- run unit/integration tests
- run cross-pack benchmark when core/content/eval changes
- run app smoke checks when app/ui changes
- include strongest/weakest pack delta when benchmark is relevant

## Reporting format
Return:
1. what changed
2. files touched
3. tests run
4. benchmark / eval delta or N/A
5. strongest / weakest pack effect if applicable
6. risks / rollback
7. next suggested task
