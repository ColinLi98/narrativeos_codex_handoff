# Longform 500 Quality Improvement Dossier - 2026-04-25

## Scope

This dossier summarizes the current 500-chapter generation result, remaining product-quality risks, and the next improvement plan.

Image generation remains out of scope.

Primary evidence:

- Final all-pack artifact: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.json`
- Final markdown report: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.md`
- Closeout DB: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.db`
- Focused Urban Q03 recovery: `artifacts/urban_q03_focus_after4.json`
- Focused Tide Q04 recovery: `artifacts/tide_q04_focus_after8.json`
- Reader replay DB: `artifacts/reader_storybook_500_20260425.db`
- Reader replay seed: `artifacts/reader_storybook_500_20260425_seed.json`
- Reader UI verification: `artifacts/reader_storybook_500_20260425_result.json`
- Reader screenshots: `artifacts/reader_storybook_500_20260425_screenshots/`
- Reader redundancy audit: `artifacts/reader_storybook_500_20260425_redundancy_audit.json`

## Quantity Result

The 500-chapter benchmark is currently stable at the automated benchmark level.

- Benchmark mode: `longform_500`
- Target chapters per pack: 500
- Packs tested: 6
- Packs reaching 500 chapters: 6/6
- `longform_500_summary.gate_pass_rate`: 1.0
- `cross_pack_pass_rate`: 1.0
- `phase_a_quality_gate.ok`: `true`
- Failed worlds: none

Per-pack chapter survival:

| Pack | Reached chapters | Gate |
| --- | ---: | --- |
| `urban_mystery_lotus_lane` | 500 | pass |
| `xianxia_forgotten_vow` | 500 | pass |
| `jade_court_exam` | 500 | pass |
| `jade_court_romance` | 500 | pass |
| `synthetic_min_pack` | 500 | pass |
| `tide_archive_memory_debt` | 500 | pass |

## Quality Result

The blocking 500-chapter residues were cleared.

- Before residual recovery:
  - `urban_mystery_lotus_lane`: Q03 x1
  - `tide_archive_memory_debt`: Q04 x1
- After residual recovery:
  - all-pack `issue_mix`: empty for all 6 packs
  - all-pack `surface_issue_chapters`: empty for all 6 packs
  - Q03/Q04/Q05/Q09 blockers: 0

Longform continuity metrics:

- `series_boundary_survival`: 1.0
- `series_memory_snapshot_integrity`: 1.0
- `memory_recall_coverage`: 1.0
- `late_series_pass_rate`: 1.0
- `series_ending_control_score`: 1.0
- `replan_stability_score`: 0.694

Review and signoff state:

- `review_sample_coverage_500.planned_target_count`: 36
- `review_sample_coverage_500.executed_target_count`: 36
- `review_sample_coverage_500.auto_seeded_target_count`: 36
- `review_sample_coverage_500.human_reviewed_target_count`: 36
- `review_sample_coverage_500.human_closeout_ready`: `true`
- `review_sample_coverage_500.ending_window_human_closeout_ready`: `true`
- `longform_500_signoff.ready`: `true`
- `longform_500_human_review_closeout.ready`: `true`
- `longform_500_ending_signoff.ready`: `true`

Review source separation in the closeout DB:

- `evaluation_report_auto | narrative_eval_auto`: 36 records
- `human_review | ops_longform500_reviewer_after_residual_fix`: 36 records

## Reader Product Replay Verification

2026-04-25 product replay verification used the real Quantum frontend on `http://127.0.0.1:3000` and the API on `http://127.0.0.1:8000`, pointed at the already-seeded Reader replay DB. No image generation was enabled.

- Reader replay sessions reaching 500 chapters: 6/6
- Sampled chapters rendered in Storybook: 36/36
- Sample windows per pack: chapters 1, 21, 220, 260, 460, 480
- Required UI selectors verified: `#reader-v2-storybook-title`, `#reader-v2-storybook-prose`, `#reader-v2-storybook-quote`, `#reader-v2-storybook-beats`, `#reader-v2-storybook-sequence`
- All sampled chapters had title, prose length > 400, non-placeholder quote, at least one beat, and active trajectory-card switching.
- Browser console errors: 0

The Reader UI closeout is therefore display-green for the sampled 500 replay targets. The verification also exposed a UI robustness/performance lesson: 500-node replay pages need tolerant loading windows and defensive partial-payload handling, especially for deviation payloads and long session navigation.

## Reader-Perceived Redundancy Audit

The Reader replay audit wrote 36 separate `source=human_review` samples with reviewer id `ops_longform500_reader_redundancy_audit_20260425`. These are distinct from benchmark auto/eval samples and from the previous 500 closeout reviewer samples.

Overall risk:

- Low: 15
- Medium: 12
- High: 9
- Reader-perceived redundancy closeout ready: `false`

Per-pack risk:

| Pack | Low | Medium | High |
| --- | ---: | ---: | ---: |
| `urban_mystery_lotus_lane` | 5 | 1 | 0 |
| `xianxia_forgotten_vow` | 2 | 3 | 1 |
| `jade_court_exam` | 1 | 0 | 5 |
| `jade_court_romance` | 0 | 3 | 3 |
| `synthetic_min_pack` | 2 | 4 | 0 |
| `tide_archive_memory_debt` | 5 | 1 | 0 |

Interpretation:

- Benchmark Phase A and automated Q03 remain green, but human-perceived sameness is still present.
- The strongest Reader-perceived packs are `urban_mystery_lotus_lane` and `tide_archive_memory_debt`.
- The weakest Reader-perceived packs are `jade_court_exam` and `jade_court_romance`, with `xianxia_forgotten_vow` carrying one high-risk late-route Q03 sample.
- The next quality task should target recurring chapter-function and dialogue-pressure templates, not single chapter patches.

## Pack Ranking Snapshot

Strongest packs:

| Pack | Diagnostic score | Long-route quality | Detail density | Dialogue ratio |
| --- | ---: | ---: | ---: | ---: |
| `tide_archive_memory_debt` | 0.038 | 0.893 | 0.056 | 0.529 |
| `xianxia_forgotten_vow` | 0.040 | 0.902 | 0.064 | 0.581 |

Weakest packs:

| Pack | Diagnostic score | Long-route quality | Detail density | Dialogue ratio | Voice separation |
| --- | ---: | ---: | ---: | ---: | ---: |
| `jade_court_exam` | 0.052 | 0.906 | 0.060 | 0.560 | 0.623 |
| `jade_court_romance` | 0.051 | 0.912 | 0.061 | 0.555 | 0.623 |
| `synthetic_min_pack` | 0.045 | 0.871 | 0.072 | 0.570 | 0.746 |

Interpretation:

- The weakest packs are not failing packs; they are diagnostic-priority packs.
- Jade packs are mainly weaker on voice separation and scene-detail density.
- `synthetic_min_pack` is still the lowest long-route-quality pack at 0.871 and has the largest character-fidelity gap at 0.769.
- `tide_archive_memory_debt` is strongest by diagnostic score, but its detail-density metric is still numerically low, so it should not be treated as fully polished prose.

## Remaining Issues

### 1. Reader UI display is green, but 500 replay load cost is high

The product Reader Storybook now proves the real 500 replay can display sampled early, middle, late, and ending chapters across all 6 packs. However, each 500-node session loads a multi-megabyte replay payload in the dev frontend, so verification needs long readiness windows and the product should not assume short-route loading behavior.

Risk:

- Large replay payloads can make long routes feel slow even when the page eventually renders correctly.

Next action:

- Add long-replay pagination/windowed node loading or a lighter Reader replay projection for product use.

### 2. Automated no-redundancy is green, but reader-perceived redundancy remains open

Q03 is clear by the automated repetition and coverage gates, but the 36-target Reader audit found 12 medium and 9 high reader-perceived redundancy risks.

Risk:

- Long routes may still feel formulaic if chapter functions, emotional pressure, or scene objects rotate correctly but produce similar reader experience.

Next action:

- Prioritize reusable Q03 recovery for Jade Court exam/romance route templates, then xianxia late-route repetition and synthetic medium-risk dialogue pressure.

### 3. Scene detail density is passing but remains the weakest visible prose dimension

All packs pass Q05, but detail-density values remain low in absolute terms:

- `tide_archive_memory_debt`: 0.056
- `jade_court_exam`: 0.060
- `jade_court_romance`: 0.061
- `urban_mystery_lotus_lane`: 0.063
- `xianxia_forgotten_vow`: 0.064
- `synthetic_min_pack`: 0.072

Risk:

- Chapters can be structurally valid but still feel thin or under-realized to readers.

Next action:

- Improve reusable scene-realization assets and sensory anchors across packs.
- Track Q05 not only as a blocker, but as a polish metric with target uplift.

### 4. Jade packs remain weak on voice separation

`jade_court_exam` and `jade_court_romance` both have voice separation score 0.623, the weakest among the 6 packs.

Risk:

- Dialogue can pass action/dialogue density while still making characters feel insufficiently distinct.

Next action:

- Add pack-structured voice profile assets and a kernel-level dialogue contrast pass.
- Test with targeted Jade samples plus all-pack regression to avoid pack-only tuning.

### 5. `synthetic_min_pack` remains lowest on long-route quality

`synthetic_min_pack` reaches 500 and has no issue blockers, but still has:

- lowest long-route quality: 0.871
- lowest character fidelity: 0.769
- small but present mid-arc drop: 0.002

Risk:

- Synthetic route is stable enough for longevity, but still weaker as a stress test for character continuity and route richness.

Next action:

- Continue improving generic fallback variation and synthetic structured assets, especially character-state continuity and pressure response variety.

### 6. Runtime cost is high

The fresh all-pack 500 run completed, but it took roughly 70+ minutes locally and spent significant CPU in regex-heavy lint/repetition checks.

Risk:

- 500/1000 chapter diagnostics may become too slow for routine CI or release gating.

Next action:

- Profile and cache repeated lint/repetition calculations.
- Split 500 into nightly/full acceptance and faster per-pack residual reruns.

## 2026-04-26 Reader-Perceived Q03 Recovery Closeout

Artifacts:

- fresh all-pack benchmark: `artifacts/longform500_reader_q03_recovery2_20260425.json`
- benchmark markdown: `artifacts/longform500_reader_q03_recovery2_20260425.md`
- Reader replay DB: `artifacts/reader_storybook_500_q03_recovery2_20260425.db`
- seed artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_seed.json`
- UI verification artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_result.json`
- screenshot directory: `artifacts/reader_storybook_500_q03_recovery2_20260425_screenshots/`
- redundancy audit artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_q03_recovery2_20260425_redundancy_audit.md`

Benchmark result:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Reader product replay result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- Storybook sampled chapter checks: 36/36
- packs reaching 500 in Reader replay: 6/6
- browser console errors: 0
- minimum sampled prose length: 2051
- minimum sampled quote length: 8
- minimum sampled beat count: 3
- image generation: not enabled

Reader redundancy audit delta:

- before Reader audit baseline: low 15, medium 12, high 9
- first recovery attempt: medium 15, high 5
- final recovery audit: low 36, medium 0, high 0
- Jade Court high-risk samples: 8 -> 0
- xianxia high-risk samples: 1 -> 0
- Urban/Tide high-risk samples: 0 -> 0
- `reader_q03_recovery_ready`: `true`

Implementation notes:

- Kernel scene realization now rotates openings, event anchors, hooks, and dialogue fallbacks by chapter/event/scene-function/beat context.
- Jade Court and xianxia reusable scene/dialogue assets were enriched; no single generated chapter prose was patched.
- Reader scene-card quote/beat rendering now uses chapter-aware persisted replay data so the audit reads product-facing text instead of static event-title fallbacks.
- SQLite Reader replay loading now uses lean JSON extraction for Story payloads, preventing 500 replay UI verification from blocking on full `plan_json` deserialization.
- No Phase A thresholds or benchmark baselines were changed.

## Improvement Plan

### P0 - Product replay verification

Goal:

- Prove the generated 500-chapter content can be consumed in the Reader UI, not only in benchmark JSON.

Acceptance:

- Done on 2026-04-25: 6 Reader replay sessions reached 500 and 36/36 sampled chapters passed Storybook UI checks.

### P1 - Human-perceived redundancy audit

Goal:

- Validate that automated Q03 green correlates with reader-perceived novelty.

Acceptance:

- Done on 2026-04-25: 36/36 `source=human_review` audit samples written.
- Closed on 2026-04-26: fresh recovery audit wrote 36/36 new `source=human_review` samples with `high=0`, `medium=0`, and `reader_q03_recovery_ready=true`.

### P2 - Scene-detail uplift without threshold changes

Goal:

- Raise detail-density polish while keeping Q03/Q04 green.

Acceptance:

- Detail density improves on weakest packs without increasing issue surface.
- All-pack 500 still passes Phase A.
- No new repeated sensory-anchor pattern.

### P3 - Jade voice separation recovery

Goal:

- Improve `jade_court_exam` and `jade_court_romance` voice separation through reusable assets and kernel dialogue contrast, not chapter patching.

Acceptance:

- Jade voice separation improves from 0.623.
- Other packs do not regress.
- Q03/Q04 remain clear.

### P4 - Synthetic long-route richness

Goal:

- Improve `synthetic_min_pack` long-route quality and character fidelity while preserving 500 chapter survival.

Acceptance:

- `synthetic_min_pack.long_route_quality` improves from 0.871.
- Character fidelity improves from 0.769.
- Route still reaches 500 and issue mix remains empty.

### P5 - 500 benchmark runtime hardening

Goal:

- Make 500 diagnostics cheaper to run repeatedly.

Acceptance:

- Add timing breakdown by pack and quality pass stage.
- Cache duplicate lint/repetition calculations where safe.
- Preserve all current quality outputs and gates.

## Recommended Next Task

`[Lane A / Phase 1] 500 Reader Voice Separation + Detail Density Polish`

Background:

- The 500 benchmark, Reader Storybook display path, and Reader-perceived Q03 recovery are closed.
- Remaining weakest dimensions are Jade voice separation and cross-pack scene detail density polish, not route survival or high-risk repetition.

Goal:

- Improve `jade_court_exam` / `jade_court_romance` voice separation and raise Q05 scene-detail density through reusable assets and kernel-level dialogue/detail contrast.

Non-goals:

- No image generation.
- No threshold lowering.
- No pack-specific prose patching.

Acceptance:

- Fresh all-pack `longform_500` remains `phase_a_quality_gate.ok: true`.
- Fresh Reader replay verification remains 36/36 display-green.
- Reader redundancy audit remains `high=0`, `medium<=6`.
- Jade voice separation improves from 0.623 without creating Q03/Q04/Q05/Q09 blockers.

## 2026-04-26 Storage + Jade Voice + Q05 Polish Closeout

Artifacts:

- final all-pack benchmark: `artifacts/longform500_storage_voice_q05_final_20260426.json`
- final benchmark markdown: `artifacts/longform500_storage_voice_q05_final_20260426.md`
- standard Phase A guardrail: `artifacts/phase0_guardrail_storage_voice_q05_final_20260426.json`
- Reader replay DB: `artifacts/reader_storybook_500_storage_voice_q05_20260426.db`
- Reader replay seed: `artifacts/reader_storybook_500_storage_voice_q05_20260426_seed.json`
- Reader UI verification: `artifacts/reader_storybook_500_storage_voice_q05_20260426_result.json`
- Reader screenshots: `artifacts/reader_storybook_500_storage_voice_q05_20260426_screenshots/`
- redundancy audit: `artifacts/reader_storybook_500_storage_voice_q05_20260426_redundancy_audit.json`

Benchmark result:

- `phase_a_quality_gate.ok`: `true`
- `content_quality_contract_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `xianxia_forgotten_vow`, `urban_mystery_lotus_lane`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Q05 / voice result:

| Pack | Detail density | Voice separation | Issue mix |
| --- | ---: | ---: | --- |
| `urban_mystery_lotus_lane` | 0.077 | 0.933 | empty |
| `xianxia_forgotten_vow` | 0.082 | 0.934 | empty |
| `jade_court_exam` | 0.077 | 0.861 | empty |
| `jade_court_romance` | 0.077 | 0.861 | empty |
| `synthetic_min_pack` | 0.081 | 0.933 | empty |
| `tide_archive_memory_debt` | 0.076 | 0.938 | empty |

Storage result:

- fresh 6-pack x 500 Reader replay DB total size, including WAL/SHM: 383.84 MiB
- target: <= 1.2 GiB
- chapter rows: 3000
- `plan_json` average: 115,558.8 bytes
- `plan_json` p95: 132,100 bytes
- `plan_json` max: 143,078 bytes
- storage mode: 3000/3000 `lean_replay`
- top-level full debug payload keys present: 0 for `step_record`, `candidate_batch`, `scored_candidates`, `routes`, and `promise_ledger_snapshot`

Reader product replay result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- Storybook sampled chapter checks: 36/36
- packs reaching 500 in Reader replay: 6/6
- browser console errors: 0
- minimum sampled prose length: 2061
- minimum sampled quote length: 8
- minimum sampled beat count: 3
- image generation: not enabled

Reader redundancy audit result:

- reviewer id: `ops_longform500_reader_q03_recovery_20260425`
- new `source=human_review` samples: 36
- risk breakdown: low 34, medium 2, high 0
- `reader_q03_recovery_ready`: `true`
- `reader_perceived_redundancy_closeout_ready`: `true`
- medium-risk backlog: one `jade_court_exam` sample and one `jade_court_romance` sample

Implementation notes:

- Reader chapter persistence now defaults to lean replay payloads and keeps full step records behind `NARRATIVEOS_STORE_FULL_STEP_RECORD=1`.
- Old full `plan_json.step_record` DBs can be compacted explicitly with `scripts/compact_replay_plan_json.py`; application startup does not auto-migrate artifacts.
- Jade Court voice profile enrichment moved `jade_court_exam` and `jade_court_romance` from 0.623 to 0.861 without pack-local chapter patches.
- Longform Q05 repair now adds beat-linked object/sound/body/ambient anchors and then re-runs Q03/Q04 guards.
- A final coverage/Q04 guard was required to clear Urban Q03 and Synthetic Q04 residues after Q05 top-up.

Remaining risk:

- The final all-pack `longform_500` run took roughly 104 minutes locally. The product path is green, but 500 diagnostics still need profiling/caching before they can be routine CI.
- Standard short-route detail density remains lower for some packs because aggressive Q05 uplift is scoped to true longform chapters to keep Phase A stable.

## 2026-04-27 Runtime Hardening Addendum

Implemented:

- Benchmark JSON now includes top-level `benchmark_runtime_profile` and each world includes `runtime_profile`.
- Runtime profile covers simulation wall time, summed chapter generation latency, quality-pass total time, lint/evaluation time, route diagnostics, content-quality-contract metrics, and slowest worlds.
- Quality-pass actions are grouped into Q03 repetition, Q04 exposition, Q05 detail, Q09 pacing, length recovery, and other buckets. Per-stage milliseconds are marked as estimates derived from actual quality-pass total time plus action distribution.
- Repetition signal analysis now has a process-local safe LRU cache for identical cleaned paragraph sets.
- CLI can run `--acceptance-profile fast --changed-worldpacks <ids>` to rerun changed packs plus baseline weakest packs, while preserving full/nightly all-pack 500 as release evidence.

Release-gate policy:

- Fast gate is a merge-triage tool only.
- Full all-pack `longform_500`, Reader 500 replay verification, and redundancy audit remain required before claiming commercial Beta content closeout.

## 2026-04-27 A1.4 Reader Longform Title / Function Fast-Gate Check

Scope:

- Task: `[Lane A / Phase 1 / Task A1.4] Reader Longform Polish: Title, Function, Jade Medium Redundancy`
- Precondition: use the new fast gate before claiming title/function polish is safe.
- Selected packs: changed Jade packs plus current weakest baseline pack.
- Image generation: not enabled.

Artifacts:

- Baseline fast gate before the title polish patch: `artifacts/fast_gate_a14_jade_current_weakest_20260427.json`
- Baseline markdown: `artifacts/fast_gate_a14_jade_current_weakest_20260427.md`
- Baseline runtime profile: `artifacts/fast_gate_a14_jade_current_weakest_20260427_runtime.json`
- Post-title-polish fast gate: `artifacts/fast_gate_a14_title_function_after_20260427.json`
- Post-title-polish markdown: `artifacts/fast_gate_a14_title_function_after_20260427.md`
- Post-title-polish runtime profile: `artifacts/fast_gate_a14_title_function_after_20260427_runtime.json`

Fast-gate result:

| Run | Packs | Phase A | Cross-pack | 500 gate | Issue mix | Q03/Q04/Q05/Q09 |
| --- | --- | --- | ---: | ---: | --- | --- |
| baseline | Jade Exam, Jade Romance, Synthetic | pass | 1.0 | 1.0 | empty | 0/0/0/0 |
| post-title-polish | Jade Exam, Jade Romance, Synthetic | pass | 1.0 | 1.0 | empty | 0/0/0/0 |

Post-title-polish selected-pack metrics:

| Pack | Reached chapters | Detail density | Voice separation | Long-route quality | Issue mix |
| --- | ---: | ---: | ---: | ---: | --- |
| `jade_court_exam` | 500 | 0.077 | 0.861 | 0.897 | empty |
| `jade_court_romance` | 500 | 0.077 | 0.861 | 0.903 | empty |
| `synthetic_min_pack` | 500 | 0.081 | 0.933 | 0.865 | empty |

Implementation note:

- Reader chapter title generation now rotates deterministic, scene-facing Chinese title tails by chapter/event/scene-function context instead of reusing `scene_intent.label`.
- The patch does not change body generation, Phase A thresholds, benchmark baselines, Reader API shape, or image-generation behavior.
- Focused tests confirm title tails rotate across long-route chapter windows and do not leak internal scene-function tokens such as `vow_payment`.

Remaining A1.4 risk:

- The fast gate proves no selected-pack Q03/Q04/Q05/Q09 regression, but it is not a replacement for the fresh all-pack 500 + Reader replay UI verification + redundancy audit required to close A1.4.
- Fast gate is still expensive: the post-title-polish selected-pack run took about 44.08 minutes locally, with quality pass accounting for about 40.59 minutes.

## 2026-04-27 A1.4 Full Reader Longform Closeout

Scope:

- Task: `[Lane A / Phase 1 / Task A1.4] Full Reader Longform Closeout`
- Evidence chain: fresh all-pack `longform_500`, fresh all-pack Reader 500 replay seed, product UI Storybook verification on `http://127.0.0.1:3000`, and fresh redundancy audit.
- Image generation: not enabled.
- Phase A thresholds and benchmark baselines: unchanged.

Artifacts:

- fresh all-pack benchmark: `artifacts/longform500_a14_closeout_20260427.json`
- benchmark markdown: `artifacts/longform500_a14_closeout_20260427.md`
- runtime profile: `artifacts/longform500_a14_closeout_20260427_runtime.json`
- benchmark DB: `artifacts/longform500_a14_closeout_20260427.db`
- Reader replay DB: `artifacts/reader_storybook_500_a14_closeout_20260427.db`
- Reader replay seed: `artifacts/reader_storybook_500_a14_closeout_20260427_seed.json`
- Reader UI verification: `artifacts/reader_storybook_500_a14_closeout_20260427_result.json`
- Reader screenshots: `artifacts/reader_storybook_500_a14_closeout_20260427_screenshots/`
- redundancy audit: `artifacts/reader_storybook_500_a14_closeout_20260427_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_a14_closeout_20260427_redundancy_audit.md`

Full benchmark result:

| Metric | Result |
| --- | --- |
| `phase_a_quality_gate.ok` | `true` |
| `content_quality_contract_gate.ok` | `true` |
| `cross_pack_pass_rate` | 1.0 |
| `longform_500_summary.gate_pass_rate` | 1.0 |
| Packs reaching 500 | 6/6 |
| Per-pack `issue_mix` | empty for all packs |
| Q03/Q04/Q05/Q09 blockers | 0/0/0/0 for every pack |

Per-pack quality snapshot:

| Pack | Reached chapters | Detail density | Voice separation | Long-route quality | Issue mix |
| --- | ---: | ---: | ---: | ---: | --- |
| `urban_mystery_lotus_lane` | 500 | 0.077 | 0.933 | 0.888 | empty |
| `xianxia_forgotten_vow` | 500 | 0.082 | 0.934 | 0.890 | empty |
| `jade_court_exam` | 500 | 0.077 | 0.861 | 0.897 | empty |
| `jade_court_romance` | 500 | 0.077 | 0.861 | 0.903 | empty |
| `synthetic_min_pack` | 500 | 0.081 | 0.933 | 0.865 | empty |
| `tide_archive_memory_debt` | 500 | 0.076 | 0.938 | 0.883 | empty |

Strongest / weakest effect:

- Strongest packs: `xianxia_forgotten_vow`, `urban_mystery_lotus_lane`.
- Weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`.
- The weakest status is now polish-oriented: Jade remains weaker on voice/detail dimensions than the strongest packs, but it has no Q03/Q04/Q05/Q09 blocker and no high-risk reader redundancy sample.

Runtime profile:

- Full all-pack benchmark runtime: about 101.00 minutes.
- Quality pass runtime: about 93.86 minutes.
- Slowest worlds: `urban_mystery_lotus_lane` about 21.05 minutes, `tide_archive_memory_debt` about 20.78 minutes, `synthetic_min_pack` about 17.57 minutes.
- This reinforces the release-gate policy: full all-pack 500 is required for release evidence, while fast gates remain the merge-triage path.

Reader replay and UI result:

- Fresh Reader replay sessions reaching 500 chapters: 6/6.
- Product frontend URL: `http://127.0.0.1:3000`.
- API backend URL: `http://127.0.0.1:8000`.
- Storybook target checks: 36/36.
- Browser console errors: 0.
- Required selectors rendered in the product UI: title, prose, quote, beats, sequence/trajectory active card.
- Minimum sampled prose length: 2061.
- Minimum sampled quote length: 8.
- Minimum sampled beat count: 3.
- Screenshots written: 6 pack screenshots.

Replay storage result:

- Fresh 6-pack x 500 Reader replay DB total size, including WAL/SHM: 384.05 MiB.
- Chapter rows: 3000.
- `plan_json` average: 115,516.9 bytes.
- `plan_json` p95: 132,006 bytes.
- `plan_json` max: 143,148 bytes.
- Full debug payload keys present at top level: 0 rows for `step_record`, `candidate_batch`, `scored_candidates`, `routes`, or `promise_ledger_snapshot`.

Reader redundancy audit:

| Scope | Low | Medium | High | Unknown |
| --- | ---: | ---: | ---: | ---: |
| 2026-04-26 baseline | 34 | 2 | 0 | 0 |
| 2026-04-27 full A1.4 closeout | 34 | 2 | 0 | 0 |

Jade guard:

| Pack | Baseline medium/high | Current medium/high | Delta |
| --- | ---: | ---: | --- |
| `jade_court_exam` | 1 / 0 | 1 / 0 | no increase |
| `jade_court_romance` | 1 / 0 | 1 / 0 | no increase |

Closeout status:

- `reviewed_count`: 36.
- `reader_q03_recovery_ready`: `true`.
- `reader_perceived_redundancy_closeout_ready`: `true`.
- Overall high-risk reader-perceived Q03 remains 0.
- Overall medium-risk count remains 2, matching the accepted baseline.
- Medium backlog remains bounded to `jade_court_exam` chapter 21 and `jade_court_romance` chapter 21.

Operational note:

- During the first resume after seed, port 8000 was occupied by an existing backend. That process was stopped rather than switching to another port, and verification resumed against the same fresh seed DB on the required 3000/8000 ports.
