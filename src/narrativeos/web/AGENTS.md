# Web AGENTS.md — NarrativeOS Reader / Author / Ops Shell

Read repo-root `AGENTS.md` first. This file narrows the rules for `src/narrativeos/web/`.

## Mission
- Treat `web/` as the Reader / Author / Ops product shell.
- Preserve clear boundaries between UI, APIs, entitlements, and quality diagnostics.

## Do
- Improve workflow clarity, diagnostics visibility, and product-state communication.
- Keep UI aligned with benchmark, review, and entitlement evidence exposed by APIs.

## Do not
- Hardcode tier or entitlement logic in UI.
- Bypass API checks or hide missing backend evidence with front-end-only messaging.
- Add pack-specific assumptions to make one world look better.

## Validation
- Run relevant tests.
- Smoke-check Reader / Author / Ops paths when changing shell behavior.
- Update docs or samples when benchmark / diagnostics UI expectations change.
