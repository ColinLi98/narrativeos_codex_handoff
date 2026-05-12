# Cross-Pack Benchmark Summary

## Overview
- benchmark mode: standard
- cross-pack pass rate: 1.000
- benchmark delta: +0.067
- packs covered: 6
- regressions: 5

## Phase A Quality Gate
- status: pass
- config version: phase_a_quality_gate_v1
- failed checks: none
- weakest packs evaluated: jade_court_romance, jade_court_exam, synthetic_min_pack

## Commercial Long-Route 50 Gate
- applicable: no
- status: pass
- failed checks: none
- evidence command: python -m src.narrativeos.benchmark.runner --worldpack all --database-url sqlite:///artifacts/commercial_long_route_50.db --benchmark-mode long_route --max-chapters 50 --markdown-out artifacts/commercial_long_route_50.md

### Commercial Weakest-Pack Evidence
- jade_court_romance: long-route 0.899 · mid-arc drop 0.026 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean
- jade_court_exam: long-route 0.890 · mid-arc drop 0.000 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean
- synthetic_min_pack: long-route 0.848 · mid-arc drop 0.000 · completion 1.000 · stop chapter_budget_reached
  focus issues: clean

## Strongest Packs
- xianxia_forgotten_vow: pass 1.000 · long-route 0.870 · mid-arc drop 0.000 · dialogue distinctness 0.934 · diagnostic 0.026
  issue mix: clean
- urban_mystery_lotus_lane: pass 1.000 · long-route 0.858 · mid-arc drop 0.000 · dialogue distinctness 0.933 · diagnostic 0.028
  issue mix: clean

## Weakest Packs
- jade_court_romance: pass 1.000 · long-route 0.899 · mid-arc drop 0.026 · dialogue distinctness 0.861 · diagnostic 0.033
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.060 / dialogue_ratio=0.535 / voice_separation_score=0.861
  recommended target: writer / planner / world pack asset
- jade_court_exam: pass 1.000 · long-route 0.890 · mid-arc drop 0.000 · dialogue distinctness 0.861 · diagnostic 0.030
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.057 / dialogue_ratio=0.517 / character_fidelity=0.850
  recommended target: writer / planner / world pack asset
- synthetic_min_pack: pass 1.000 · long-route 0.848 · mid-arc drop 0.000 · dialogue distinctness 0.933 · diagnostic 0.029
  completion ratio: 1.000 · stop reason: chapter_budget_reached
  issue mix: clean
  weakest dimensions: scene_detail_density=0.063 / dialogue_ratio=0.528 / character_fidelity=0.727
  recommended target: writer / planner / world pack asset

## Weakest Pack Diagnostics
- jade_court_romance: diagnostic rank 1 · diagnostic 0.033 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_jade_court_romance@1.0.0_3 pass 0.862 [clean] | simulation_jade_court_romance@1.0.0_6 pass 0.887 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: continue_polish (dialogue_ratio)
- jade_court_exam: diagnostic rank 2 · diagnostic 0.030 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_jade_court_exam@1.0.0_2 pass 0.859 [clean] | simulation_jade_court_exam@1.0.0_1 pass 0.882 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: continue_polish (dialogue_ratio)
- synthetic_min_pack: diagnostic rank 3 · diagnostic 0.029 · completion 1.000 · stop chapter_budget_reached
  worst chapters: simulation_synthetic_min_pack@0.1.0_1 pass 0.780 [clean] | simulation_synthetic_min_pack@0.1.0_2 pass 0.831 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
  stop condition: continue_polish (long_route_quality, dialogue_ratio)

## Weakest Pack Polish Program
- program status: continue_polish
- stop-ready worlds: -
- continue worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- recommended action: continue_lane_a_weakest_pack_polish
- jade_court_romance · continue_polish · dimensions scene_detail_density, dialogue_ratio, voice_separation_score
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
- jade_court_exam · continue_polish · dimensions scene_detail_density, dialogue_ratio, character_fidelity
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy
- synthetic_min_pack · continue_polish · dimensions scene_detail_density, dialogue_ratio, character_fidelity
  bundle: writer x sensory_grounding_policies x scene_realization_contracts | writer x voice_profiles x dialogue_realism_policy

## Longform L1 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_100
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_100_benchmark, confirm_weakest_pack_polish_program

## Interactive Longform Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_100_interactive
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_100_interactive_benchmark, confirm_interactive_gate

## Longform 250 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_250_benchmark, review_sample_coverage_250

## Longform 250 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250_interactive
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_250_interactive_benchmark, review_sample_coverage_250

## Longform 250 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_250_family
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_250_benchmark, submit_human_review_samples_for_250_windows

## Longform 500 Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_500_benchmark

## Longform 500 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_family
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_500_benchmark, submit_human_review_samples_for_500_windows

## Longform 500 Ending Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_family
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_500_benchmark, review_sample_coverage_500.ending_window_human_closeout_ready

## Longform 500 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_500_interactive
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_500_interactive_benchmark, review_sample_coverage_500

## Longform 1000 Readiness
- status: watch
- ready: no
- reason: longform_1000_readiness_watch
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: longform_1000_feasibility.ready, fresh_longform_1000_diagnostics_benchmark

## Longform 1000 Interactive Sign-off
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_interactive
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_1000_interactive_benchmark, longform_1000_readiness.ready

## Longform 1000 Human Review Closeout
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_family
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_1000_diagnostics_benchmark, submit_human_review_samples_for_1000_windows
- human reviewed target count: 0
- planned target count: 0

## Longform 1000 Feasibility
- status: watch
- ready: no
- reason: benchmark_mode_not_longform_1000_family
- blocking worlds: -
- watch worlds: jade_court_romance, jade_court_exam, synthetic_min_pack
- required evidence: run_longform_1000_diagnostics_benchmark

## Ranking and Metric Delta
- strongest packs changed: entered [urban_mystery_lotus_lane] · exited [jade_court_exam]
- weakest packs changed: entered [jade_court_exam] · exited [urban_mystery_lotus_lane]
- current strongest: xianxia_forgotten_vow, urban_mystery_lotus_lane
- current weakest: jade_court_romance, jade_court_exam, synthetic_min_pack
- regressions: jade_court_exam [avg_repetition_score]; jade_court_romance [mid_arc_drop, avg_repetition_score]; synthetic_min_pack [avg_repetition_score, avg_hook_quality]; urban_mystery_lotus_lane [avg_repetition_score]; xianxia_forgotten_vow [avg_repetition_score]
