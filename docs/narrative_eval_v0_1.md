# NarrativeEval v0.1

## 目标

NarrativeEval v0.1 用于把章节生成结果统一分成：

- `pass`
- `rewrite`
- `block`

并把问题分类、得分和趋势统一反馈给：

- Author simulate
- Review publish
- Ops 质量面板
- 在线 Reader 生成后的告警记录

## Issue Taxonomy

- `Q01 engineering leak`
- `Q02 meta narration leak`
- `Q03 repetition`
- `Q04 over-explanation`
- `Q05 lack of scene detail`
- `Q06 character inconsistency`
- `Q07 causal discontinuity`
- `Q08 weak choice distinctness`
- `Q09 pacing failure / premature ending`
- `Q10 product continuity failure`

## 生效位置

### 强制闸门

- `AuthoringService.run_simulation()`
- `ReviewService.publish()`

### 在线只记录

- Reader 继续阅读
- chapter 生成后的 analytics / chapter review flags

## 当前阈值

- `block`：任一 hard validator fail
- `rewrite`：`overall_score < 0.72` 或 2 个以上 medium issue
- `pass`：`overall_score >= 0.72` 且无 hard fail

## 当前输出

每章生成 `EvaluationReport`，至少包含：

- chapter_id
- world_version_id
- session_id
- decision
- issues
- scores
- hard_validator_results
- summary
- created_at

## 当前 nightly 形态

使用 CLI：

```bash
python -m src.narrativeos.eval.regression --worldpack all --golden-dir tests/golden_routes
```

输出：

- 逐 world pack regression summary
- simulation report 聚合
- 可供本地或 CI 直接调用
