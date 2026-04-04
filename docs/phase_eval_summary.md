# Phase Eval Summary

- 新增 `src/narrativeos/eval/` 目录
- 实现 taxonomy / validators / scorers / gating / reporting / regression runner
- 每章现在可生成 `EvaluationReport`
- Author simulate 现在会返回 `evaluation_summary`、`cross_pack_summary`、`metric_deltas`、`top_failing_packs`
- Review publish 现在会受 NarrativeEval summary 与 capability-aware publish gate 约束
- Ops 可通过 eval metrics 与 cross-pack quality 查看 pass / rewrite / block、top issues、top failing packs、metric delta
- Cross-pack benchmark 现已为每个 pack 输出：
  - `top_issue_categories`
  - `dimension_scores`
  - `issue_summary`
