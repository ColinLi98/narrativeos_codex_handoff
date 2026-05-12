# 文本质量评分卡与 Rubric

## 评分目标
- 让自动 evaluator、规则项和人工审核使用同一套语言。
- 兼容现有 `Q01-Q10` taxonomy。
- 每一项都可给 1–5 分，并可携带证据、触发原因、是否 veto。

## 评分维度

| 维度 | 定义 | 1 分 | 3 分 | 5 分 | 现有信号映射 |
| --- | --- | --- | --- | --- | --- |
| 正确性 | 内容是否与状态、角色、世界事实、前文因果一致 | 明显错误或自相矛盾 | 基本正确但有局部模糊 | 无明显错误，因果稳定 | `Q06` `Q07` canon / critics |
| 依据性 / Groundedness | 是否能被可追溯证据支持 | 关键断言无证据或冲突 | 有部分支持，仍有缺口 | 关键断言均有明确支持 | 待新增 `GroundingCheck` |
| 完整性 | 是否完成当前任务要求而非半截输出 | 大量缺失 | 主体完成但细节不足 | 任务闭环完整 | chapter task / recap / choices / ending signals |
| 任务贴合度 | 是否真正回答当前用户或 chapter task 的目标 | 明显跑题 | 基本相关但偏离重点 | 紧贴目标，偏差小 | simulate target / chapter task / intent |
| 结构与可读性 | 是否便于阅读、结构清晰 | 摘要化、堆砌、难读 | 可读但有解释偏重 | 场景化、节奏自然、钩子清晰 | readability / pacing / hook / scene density |
| 风格一致性 | 是否保持 pack /角色 /场景风格连续 | 风格跳脱 | 有轻微失真 | 风格稳定一致 | voice / dialogue / sensory policies |
| 安全合规性 | 是否符合风险级别、审查和策略边界 | 明显越界 | 有可疑点 | 完全符合策略 | `rating_ceiling` `risk_rating` policy guards |
| 可执行性 | 下游是否可直接消费和继续推进 | 无法入库或无法继续 | 可继续但需要人工补洞 | 可入库、可继续、可追溯 | `quality_gate` / continuity contract |

## 一票否决规则

### 直接 veto
- `Q01` engineering leak
- `Q02` meta narration leak
- `Q07` causal discontinuity high severity
- `Q09` premature ending high severity
- groundedness contradiction
- groundedness missing critical evidence
- safety / policy / permission overreach

### 条件 veto
- `Q03/Q04/Q05` 连续窗口超阈
- evaluator 总分低于配置阈值
- 场景为 L3/L4 且缺少人工审核

## 分数解释建议

### 1 分
- 明显错误、不可用、需要阻断

### 2 分
- 存在严重问题，不能直接用户可见

### 3 分
- 可读但需要 rewrite 或人工确认

### 4 分
- 质量较稳，可放行但仍可优化

### 5 分
- 明确满足目标，可作为高质量样本

## 与现有 Q01-Q10 的映射

| Issue Code | 主要影响维度 | 次要影响维度 |
| --- | --- | --- |
| `Q01` | 安全合规性 / 可执行性 | 正确性 |
| `Q02` | 结构与可读性 / 风格一致性 | 任务贴合度 |
| `Q03` | 结构与可读性 | 完整性 |
| `Q04` | 结构与可读性 / 完整性 | 任务贴合度 |
| `Q05` | 完整性 / 结构与可读性 | 风格一致性 |
| `Q06` | 正确性 / 风格一致性 | 依据性 |
| `Q07` | 正确性 / 依据性 | 可执行性 |
| `Q08` | 任务贴合度 / 可执行性 | 结构与可读性 |
| `Q09` | 完整性 / 可执行性 | 结构与可读性 |
| `Q10` | 可执行性 / 产品连续性 | 任务贴合度 |

## evaluator 输出建议结构

```json
{
  "scorecard_version": "content_quality_rubric_v1",
  "overall_score": 3.8,
  "dimension_scores": {
    "correctness": 4,
    "groundedness": 2,
    "completeness": 4,
    "task_fit": 4,
    "readability": 3,
    "style_consistency": 4,
    "safety_compliance": 5,
    "executability": 3
  },
  "veto": false,
  "veto_reasons": [],
  "evidence_refs": [],
  "reason_codes": ["Q05", "grounding_missing_support"],
  "summary": "..."
}
```

## 证据保存要求
- 每个低分项都要有 `reason_code`
- 每个 veto 都要有 `veto_reason`
- groundedness 必须带 `evidence_refs`
- 规则检查必须带 `rule_id`
- evaluator 必须带 `rubric_version`

## 人工审核使用方式
- 人工审核默认看自动评分，再补结构化理由。
- 不允许只写自由备注而没有维度分数和 issue code。
- 人工修改后，要能回写：
  - 最终分数
  - 是否通过
  - 修改后 verdict
  - 是否进入训练样本

## 当前结论
- 现有 NarrativeEval 已覆盖部分维度，但更偏章节写作质量。
- 下一阶段需要把 groundedness、任务贴合度、可执行性正式提升为一等维度。
