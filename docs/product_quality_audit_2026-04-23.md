# Product Quality Audit - 2026-04-23

Task label: `[Lane C / Phase 3 / Task QA] Subscription/image2 gating and front-back alignment audit`

## Goal

Run a narrow product-quality audit for Reader / Author / Ops front-back alignment, current failing surfaces, and whether `gpt-image-2` can be covered by a subscription-plan strategy instead of uncontrolled per-image spend.

## Validation Summary

- Backend targeted QA suite: 98 passed, 12 failed.
- Quantum React frontend Vitest: 39 passed.
- Quantum React frontend production build: passed with one bundle-size warning.
- Health and boot probe: `/health`, `/api/v1/health`, `/app`, and `/v1/examples` returned 200 via `TestClient`.
- Benchmark / eval rerun: not run; this audit did not change narrative kernel/prose behavior.

## Current Issues

### P1 - Subscription and image2 are not connected

`IllustrationService` defaults to `NARRATIVEOS_IMAGE_MODEL=gpt-image-2` and `NARRATIVEOS_ILLUSTRATIONS_ENABLED=true`. Session creation and story continuation enqueue `session_cover`, `world_cover`, and `chapter_hero` directly after runtime work. The enqueue gate only checks service enabled state, storage, OpenAI API key, and async jobs. It does not check subscription tier, wallet balance, per-account quota, or an image-specific entitlement rule.

Effect:

- A Reader can trigger paid image generation through normal session/chapter flow once global env and provider credentials are enabled.
- Current `Play Pass / Creator Pass / Studio Pass` config meters text continuation and author actions, but not image generation.
- Ops can observe generated-media assets/events, but cannot set a product policy such as "Studio gets N hero images/month" or "Reader uses low-quality thumbnails only."

Recommended fix:

- Add `image_credits` or `media_credits` wallet and explicit entitlement matrix rules for `world_cover`, `session_cover`, `chapter_hero`, and on-demand generation.
- Gate automatic image enqueue in `SessionService`/`IllustrationService` through `BillingService`, not by UI.
- Default local/prod rollout should set `NARRATIVEOS_ILLUSTRATIONS_ENABLED=false` until the gate exists.
- Add image generation metering events with model, quality, size, output token estimate/cost estimate, account_id, session_id, and asset_kind.

### P1 - Frontend dark-matter economics do not match backend metering

Settings UI says "约10暗物质/章 (~$0.02)". Backend config currently charges `reader_continue_story_credits = 1`, and ink packages start at 500 credits for $0.99.

Effect:

- User-facing copy implies 10 credits per chapter.
- Backend consumes 1 `story_credit` per paid continuation.
- This makes price-per-chapter and wallet expectations off by 10x.

Recommended fix:

- Move per-chapter copy to backend commerce payload, derived from `configs/monetization_tiers.json`.
- Add a frontend contract test asserting displayed chapter cost equals the backend `metering.reader_continue_story_credits` rule.

### P1 - Monetization backend tests are stale against Ops auth hardening

The Ops middleware now requires privileged identity for `/v1/ops/*` reads/writes. Many `tests/test_monetization_m0.py` cases still call Ops mutation/read endpoints without headers. Those calls now return `403 ops_actor_missing`, so subsequent subscription and wallet assertions fail.

Effect:

- The product behavior is more secure, but the monetization regression suite no longer proves subscription lifecycle correctness through API paths.
- Several failures are cascading false negatives after unauthorized Ops grants.

Recommended fix:

- Update monetization API tests to use `tests/ops_auth_helpers.py`.
- Keep one negative test for unauthenticated Ops mutation; route the rest through reviewer/admin headers.

### P2 - Auth cookie/account-id mismatch can break Reader API probes

One observability endpoint test registers/logs in an Ops identity, then creates a Reader session for a different `account_id` using the same `TestClient`. Reader account resolution treats the existing auth token/cookie as authoritative and rejects a mismatched provided account.

Effect:

- This is correct from an ownership-policy perspective, but tests and any legacy shell flows that expose a free-form Reader account field while logged in can produce confusing 403s.

Recommended fix:

- Tests should isolate clients or use matching account IDs.
- UI should avoid sending arbitrary `account_id` when authenticated; derive account identity from token.

### P2 - Quality gate expectation drift

`tests/test_provider_runtime_routing.py::test_reader_runtime_quality_gate_blocks_failed_chapter_persistence` expected `required_text_units >= 1800`; current runtime returned `990`.

Effect:

- Either the runtime quality gate no longer receives the longform `min_target_words=1800` contract for this route, or the test assumes a longform route while the current route is short/derived from `target_words * 0.9`.
- This weakens P0 quality signal unless intentional.

Recommended fix:

- Confirm whether paid Reader continuation should enforce the 1800 floor.
- If yes, pass chapter budget policy into runtime quality gate consistently.
- If no, update test expectation and report the route as shortform/non-longform.

### P2 - Frontend fallback can hide backend absence

The Quantum React client falls back to local demo data when health/network checks fail. This keeps the UI usable, but can mask production API drift unless the backend status banner and CI tests stay strict.

Recommended fix:

- Keep `VITE_API_LOCAL=false` for acceptance.
- Add a hard acceptance mode that fails on demo fallback for purchase, subscription, image, and Reader continuation flows.

## image2 Subscription Plan Assessment

OpenAI ChatGPT subscriptions and OpenAI API billing are separate systems. A ChatGPT subscription should not be treated as a way to cover API `gpt-image-2` costs. Product subscription plans can still be used internally, but only by gating and budgeting our own API calls through NarrativeOS entitlements/wallets.

OpenAI official pricing currently lists `gpt-image-2` as API-token priced. Standard `gpt-image-2` image output is $30.00 / 1M image output tokens, and Batch is $15.00 / 1M output tokens. The image guide's example calculator lists GPT Image 2 output estimates at:

- 1024x1024 low: about $0.006
- 1024x1024 medium: about $0.053
- 1024x1024 high: about $0.211
- 1536x1024 low: about $0.005
- 1536x1024 medium: about $0.041
- 1536x1024 high: about $0.165

Current repo calls `/v1/images/generations` with `model`, `prompt`, and `size` only. It does not set `quality`, so it leaves quality at provider default/auto behavior. For cost control, use explicit `quality: "low"` for drafts/thumbnails and reserve medium/high for final assets.

## Recommended Next Task

`[Lane C / Phase 3 / Task QA.1] Image generation entitlement and cost gate`

Background: `gpt-image-2` is wired to Reader illustration delivery, but not to subscription/wallet policy.

Goal: Add central media-generation entitlement rules and make all automatic image enqueue paths honor them.

Non-goals: Do not change prompt style, worldpack art direction, or generated prose.

Scope:

- `configs/monetization_tiers.json`
- `src/narrativeos/services/billing.py`
- `src/narrativeos/services/illustration.py`
- `src/narrativeos/services/sessions.py`
- tests for Reader session, continue, on-demand illustration, and Ops audit.

Acceptance:

- Free/unsubscribed accounts do not enqueue paid images automatically.
- Play/Creator/Studio tiers get explicit monthly media quotas.
- Every image job records metering/audit with model, size, quality, asset_kind, and account_id.
- Frontend receives clear image availability/fallback state without hardcoded tier logic.

Rollback point:

- Revert the media entitlement rule and the IllustrationService gate; keep `NARRATIVEOS_ILLUSTRATIONS_ENABLED=false` as kill switch.
