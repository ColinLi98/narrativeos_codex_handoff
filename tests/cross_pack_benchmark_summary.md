# Cross-Pack Benchmark Summary

## Overview
- benchmark mode: standard
- cross-pack pass rate: 1.000
- benchmark delta: +0.067
- packs covered: 5
- regressions: 0

## Strongest Packs
- jade_court_exam: pass 1.000 · long-route 0.857 · mid-arc drop 0.000 · dialogue distinctness 0.250 · diagnostic 0.146
  issue mix: clean
- xianxia_forgotten_vow: pass 1.000 · long-route 0.544 · mid-arc drop 0.000 · dialogue distinctness 0.330 · diagnostic 0.155
  issue mix: clean

## Weakest Packs
- synthetic_min_pack: pass 1.000 · long-route 0.133 · mid-arc drop 0.000 · dialogue distinctness 0.255 · diagnostic 0.245
  completion ratio: 0.167 · stop reason: no_legal_routes
  issue mix: clean
  weakest dimensions: scene_detail_density=0.012 / route_longevity=1.000 / voice_separation_score=0.255
  recommended target: writer / planner / world pack asset
- jade_court_romance: pass 1.000 · long-route 0.413 · mid-arc drop 0.000 · dialogue distinctness 0.250 · diagnostic 0.223
  completion ratio: 0.500 · stop reason: no_legal_routes
  issue mix: Q04 x1 (1.000)
  weakest dimensions: scene_detail_density=0.008 / voice_separation_score=0.250 / dialogue_ratio=0.397
  recommended target: writer / sensory / scene realization
- urban_mystery_lotus_lane: pass 1.000 · long-route 0.555 · mid-arc drop 0.000 · dialogue distinctness 0.275 · diagnostic 0.204
  completion ratio: 0.667 · stop reason: no_legal_routes
  issue mix: clean
  weakest dimensions: scene_detail_density=0.007 / voice_separation_score=0.275 / dialogue_ratio=0.403
  recommended target: writer / planner / world pack asset

## Weakest Pack Diagnostics
- synthetic_min_pack: diagnostic rank 1 · diagnostic 0.245 · completion 0.167 · stop no_legal_routes
  worst chapters: simulation_synthetic_min_pack@0.1.0_1 pass 0.797 [clean]
  module / asset / policy: writer / sensory_grounding_policies / scene_realization_contracts
  next fixes: writer x sensory_grounding_policies x scene_realization_contracts | planner x scene_blueprints x scene_realization_contracts
- jade_court_romance: diagnostic rank 2 · diagnostic 0.223 · completion 0.500 · stop no_legal_routes
  worst chapters: simulation_jade_court_romance@1.0.0_3 pass 0.794 [Q04] | simulation_jade_court_romance@1.0.0_1 pass 0.840 [clean]
  module / asset / policy: writer / voice_profiles / scene_realization_contracts
  next fixes: writer x voice_profiles x dialogue_realism_policy | writer x scene_blueprints x scene_realization_contracts
- urban_mystery_lotus_lane: diagnostic rank 3 · diagnostic 0.204 · completion 0.667 · stop no_legal_routes
  worst chapters: simulation_urban_mystery_lotus_lane@0.1.0_1 pass 0.811 [clean] | simulation_urban_mystery_lotus_lane@0.1.0_2 pass 0.833 [clean]
  module / asset / policy: writer / voice_profiles / dialogue_realism_policy
  next fixes: writer x voice_profiles x dialogue_realism_policy | writer x sensory_grounding_policies x scene_realization_contracts

## Ranking and Metric Delta
- strongest packs changed: entered [-] · exited [-]
- weakest packs changed: entered [-] · exited [-]
- current strongest: jade_court_exam, xianxia_forgotten_vow
- current weakest: synthetic_min_pack, jade_court_romance, urban_mystery_lotus_lane
- regressions: none
