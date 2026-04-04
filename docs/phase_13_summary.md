# Phase 13 Summary

- 新增 reranker promotion builder：
  - `src/narrativeos/eval/learned_reranker_promotion.py`
- 新增 Ops API：
  - `GET /v1/ops/learned-reranker-promotion`
- 当前 `/app` 的 Ops 区新增：
  - `Reranker Promotion Gate`
- reranker promotion summary 会统一输出：
  - `status`
  - `recommended_action`
  - `blockers`
  - `advisories`
  - `checklist`
  - `evidence`
- 当前结论：
  - NarrativeOS 已把 evaluator / reranker 两条 learned 线都推进到 promotion 治理层
  - evaluator 是 manual approval，reranker 仍是 recommend-only
  - 这层仍然不影响线上 gate
