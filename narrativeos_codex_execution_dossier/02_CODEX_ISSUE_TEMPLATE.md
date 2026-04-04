# Codex Issue Template for NarrativeOS

## Title
[Lane X / Phase Y / Task Z] <Task name>

## Background
- Current phase:
- Why now:
- Which commercialization checklist item this task advances:
- NarrativeOS is a commercial beta kernel with multi-world runtime, Reader/Author/Ops, NarrativeEval, and partial monetization skeleton. This task must improve the product at kernel/product/ops level, not default to pack-specific prose tuning.

## Goal
- <up to 3 concrete goals>

## Non-goals
- Do not tune only the currently strongest pack
- Do not do prose-only polish unless explicitly requested
- Do not touch unrelated lanes
- Do not broaden scope into a platform-wide refactor

## Scope
### In scope
- <files/modules>

### Out of scope
- <files/modules>

## Ask / Plan requirements
- Read root `AGENTS.md` first
- Output implementation plan before coding
- Include:
  - goal
  - touched modules
  - test plan
  - benchmark / eval plan
  - rollback point
- Do not do pack-specific prose tuning

## Acceptance criteria
- tests
- benchmark / eval
- docs
- delta metrics
- rollback clarity

## Required outputs
- code changes
- tests
- docs update
- benchmark / eval delta or why not applicable
- strongest / weakest pack effect if applicable
- risks / rollback point
- next suggested task
- screenshots/sample outputs if UI

## Validation
- run tests
- run benchmark if core/content/eval changed
- include strongest/weakest pack delta when relevant
- include risks and next-step suggestions
