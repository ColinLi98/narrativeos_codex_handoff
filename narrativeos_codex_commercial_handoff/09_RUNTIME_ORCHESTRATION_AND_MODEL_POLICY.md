# 09. 运行时编排与模型策略

## 原则

不要用一个模型干完所有事。

运行时应拆成：
- planner
- simulator
- renderer
- critics
- moderation / policy

## 模型路由建议

### 1) Planner
需求：结构化、便宜、稳定。
建议：中小模型，输出 JSON / schema-first。

### 2) Simulator
需求：多候选、状态一致、可批量。
建议：中模型或程序规则 + 模型混合。

### 3) Renderer
需求：语言质量、对话张力、文风。
建议：更强模型，但要有长度和成本上限。

### 4) Critics
需求：一致性/沉浸/重复检测。
建议：便宜模型 + 规则校验优先。

### 5) Policy Guard
需求：快速、保守、可审计。
建议：规则 + 分类模型 + 可人工兜底。

## 每章 token/cost 策略

每章应有显式预算：
- planner budget
- simulator budget
- renderer budget
- critics budget

并把估计成本写入 `ChapterRecord.cost_estimate`。

## 缓存策略

可缓存：
- world pack normalization
- character prompt fragments
- style pack fragments
- scene blueprint embeddings
- chapter recap compression

## 降级策略

当成本或延迟异常时：
- 减少候选 route 数
- 缩短 renderer 输出目标长度
- 关闭高成本 critic
- fallback 到更轻量 style mode

## 必须记录的元数据

- `model_policy_version`
- `planner_model`
- `renderer_model`
- `estimated_cost`
- `latency_ms`
- `cache_hit_flags`
