# Core AGENTS.md — NarrativeOS Core Boundary

Read repo-root `AGENTS.md` first. This file narrows the rules for `src/narrativeos/core/`.

## Mission
- Keep `core/` generic, reusable, and cross-pack safe.
- Improve contracts, planners, critics, rendering boundaries, and capability modules.
- Do not smuggle world-pack assumptions into generic engine code.

## Do
- Strengthen contracts and generic behavior.
- Prefer benchmark-visible capability improvements over local polish.
- Keep changes compatible with cross-pack benchmark, demo, and Reader / Author / Ops paths.

## Do not
- Import pack assets or hardcode world-specific tokens.
- Tune prose for a single pack and call it platform progress.
- Bypass evaluator, policy, or audit-facing hooks for convenience.

## Validation
- Run tests.
- Run cross-pack benchmark when core behavior changes.
- Report strongest / weakest pack effect when benchmark is relevant.
