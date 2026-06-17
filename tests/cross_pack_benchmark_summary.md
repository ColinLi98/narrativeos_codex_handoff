# Cross-Pack Benchmark Summary

## Overview
- benchmark mode: standard
- cross-pack pass rate: 1.000
- benchmark delta: +0.067
- packs covered: 6
- regressions: 0

## Benchmark Runtime Profile
- profile: full
- total wall ms: 84637.804
- slowest worlds: urban_mystery_lotus_lane 22817.726ms, tide_archive_memory_debt 19855.862ms, jade_court_exam 12182.468ms
- stage totals: simulation=84411.075ms, generation_runtime=81568.156ms, quality_pass=80245.560ms, lint=524.714ms, evaluation=1234.784ms, world_total=84568.621ms
- quality-pass stage actions: length_recovery=265, other=7, q03_repetition=1640, q04_exposition=220, q05_detail=70, q09_pacing=14
- fast gate: selected urban_mystery_lotus_lane, xianxia_forgotten_vow, jade_court_exam, jade_court_romance, synthetic_min_pack, tide_archive_memory_debt / nightly required no

## Phase A Quality Gate
- status: pass
- config version: phase_a_quality_gate_v1
- failed checks: none
- weakest packs evaluated: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane

## Commercial Long-Route 50 Gate
- applicable: no
- status: pass
- failed checks: none
- evidence command: python -m src.narrativeos.benchmark.runner --worldpack all --database-url sqlite:///artifacts/commercial_long_route_50.db --benchmark-mode long_route --max-chapters 50 --markdown-out artifacts/commercial_long_route_50.md

### Commercial Weakest-Pack Evidence
- jade_court_exam: long-route 0.907 · mid-arc drop 0.000 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean
- jade_court_romance: long-route 0.909 · mid-arc drop 0.000 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean
- urban_mystery_lotus_lane: long-route 0.866 · mid-arc drop 0.000 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean

## Strongest Packs
- synthetic_min_pack: pass 1.000 · long-route 0.875 · mid-arc drop 0.000 · dialogue distinctness 0.933 · diagnostic 0.025
  issue mix: clean
- tide_archive_memory_debt: pass 1.000 · long-route 0.873 · mid-arc drop 0.000 · dialogue distinctness 0.938 · diagnostic 0.025
  issue mix: clean

## Generation Hard Constraint Summary
- chapters: 36
- hard fail count: 0
- hard fail rate: 0.000
- repair attempts: 36
- repair success rate: 1.000
- scene-card visible text violations: 0

### Hard Constraint Violation Mix
- none

### Scene-Card Visible Text Audit
- none

## Weakest Packs
- jade_court_exam: pass 1.000 · long-route 0.907 · mid-arc drop 0.000 · dialogue distinctness 0.861 · diagnostic 0.028
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.063 / dialogue_ratio=0.594 / voice_separation_score=0.861
  recommended target: writer / planner / world pack asset
- jade_court_romance: pass 1.000 · long-route 0.909 · mid-arc drop 0.000 · dialogue distinctness 0.861 · diagnostic 0.028
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.053 / dialogue_ratio=0.606 / voice_separation_score=0.861
  recommended target: writer / planner / world pack asset
- urban_mystery_lotus_lane: pass 1.000 · long-route 0.866 · mid-arc drop 0.000 · dialogue distinctness 0.933 · diagnostic 0.027
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.058 / dialogue_ratio=0.573 / character_fidelity=0.731
  recommended target: writer / planner / world pack asset

## Weakest Pack Diagnostics
- jade_court_exam: diagnostic rank 1 · diagnostic 0.028 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_jade_court_exam@1.0.0_1 pass 0.893 [clean] | simulation_jade_court_exam@1.0.0_6 pass 0.905 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: stop_ready (all_checks_passed)
- jade_court_romance: diagnostic rank 2 · diagnostic 0.028 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_jade_court_romance@1.0.0_2 pass 0.887 [clean] | simulation_jade_court_romance@1.0.0_5 pass 0.909 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: stop_ready (all_checks_passed)
- urban_mystery_lotus_lane: diagnostic rank 3 · diagnostic 0.027 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_urban_mystery_lotus_lane@0.1.0_1 pass 0.843 [clean] | simulation_urban_mystery_lotus_lane@0.1.0_5 pass 0.864 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: stop_ready (all_checks_passed)

## Weakest Pack Polish Program
- program status: stop_ready
- stop-ready worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- continue worlds: -
- recommended action: pause_lane_a_weakest_pack_polish
- jade_court_exam · stop_ready · dimensions scene_detail_density, dialogue_ratio, voice_separation_score
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
- jade_court_romance · stop_ready · dimensions scene_detail_density, dialogue_ratio, voice_separation_score
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
- urban_mystery_lotus_lane · stop_ready · dimensions scene_detail_density, dialogue_ratio, character_fidelity
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy

## Longform L1 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_100
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_100_benchmark, confirm_weakest_pack_polish_program

## Interactive Longform Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_100_interactive
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_100_interactive_benchmark, confirm_interactive_gate

## Longform 250 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_250_benchmark, review_sample_coverage_250

## Longform 250 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250_interactive
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_250_interactive_benchmark, review_sample_coverage_250

## Longform 250 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250_family
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_250_benchmark, submit_human_review_samples_for_250_windows

## Longform 500 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_500_benchmark

## Longform 500 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_family
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_500_benchmark, submit_human_review_samples_for_500_windows

## Longform 500 Ending Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_family
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_500_benchmark, review_sample_coverage_500.ending_window_human_closeout_ready

## Longform 500 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_interactive
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_500_interactive_benchmark, review_sample_coverage_500

## Longform 1000 Readiness
- status: watch
- ready: no
- reason: longform_1000_readiness_watch
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: longform_1000_feasibility.ready, fresh_longform_1000_diagnostics_benchmark

## Longform 1000 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_interactive
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_1000_interactive_benchmark, longform_1000_readiness.ready

## Longform 1000 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_family
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_1000_diagnostics_benchmark, submit_human_review_samples_for_1000_windows
- human reviewed target count: 0
- planned target count: 0

## Longform 1000 Feasibility
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_family
- blocking worlds: -
- watch worlds: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- required evidence: run_longform_1000_diagnostics_benchmark

## Ranking and Metric Delta
- strongest packs changed: entered [synthetic_min_pack, tide_archive_memory_debt] · exited [jade_court_exam, xianxia_forgotten_vow]
- weakest packs changed: entered [jade_court_exam] · exited [synthetic_min_pack]
- current strongest: synthetic_min_pack, tide_archive_memory_debt
- current weakest: jade_court_exam, jade_court_romance, urban_mystery_lotus_lane
- regressions: none
