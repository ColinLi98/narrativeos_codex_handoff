# NarrativeOS Codex PR Review Template

## PR summary
- Lane:
- Phase:
- Task:
- Goal met:
- Out-of-scope changes introduced: yes/no

## Evidence
- Tests run:
- Benchmark / eval run: yes/no
- strongest pack delta:
- weakest pack delta:
- cross-pack pass-rate delta:
- issue category delta (Q03/Q04/Q05/Q09 if relevant):
- Agent Studio layout CSS touched: [ ] yes / [ ] no
- Agent Studio visual review:
  - If yes, Agent Studio layout-facing CSS changed, especially `src/narrativeos/web/styles.css` selectors for `.agent-studio-*`.
  - Reviewers must paste the two `manual_review` rows from `artifacts/agent_studio_smoke_visual_review.md` into PR comments.
  - Required rows: `desktop / Three-column workbench review / manual_review` and `mobile / Stacked workbench review / manual_review`.
  - Each pasted row must be marked `accepted` or `needs follow-up` after screenshot inspection.
- rollback point:
- next suggested task:

## Product impact
- Does this move commercialization forward? yes/no
- Does this improve kernel/product/ops instead of just current-pack polish? yes/no
- Does this make weakest packs easier to diagnose or improve? yes/no

## Review gate
Reject if any are true:
- only one pack improved and no cross-pack evidence
- no tests
- no docs update
- benchmark omitted when required
- lane scope violated
- rollback / recovery is unclear
- result is mostly prose tuning rather than system capability
- Agent Studio layout CSS changed and the PR lacks the pasted `manual_review` rows from `artifacts/agent_studio_smoke_visual_review.md`

Agent Studio visual review is human screenshot triage, not an automated image comparison gate.

## Merge decision
- approve / request changes / reject
