# 系统架构

## 总览

```text
Player Input
   ↓
Intent Parser
   ↓
State Store ─────────────── World Bible / Creator Controls
   ↓                               ↓
Candidate Provider ─────────────> Canon Engine
   ↓                               ↓
Scoring Engine <──────────── Critic Loop
   ↓
Route Search (Beam / MCTS later)
   ↓
Transition Engine
   ↓
Renderer
   ↓
API / Replay / Analytics
```

## 核心模块

### 1. Intent Parser
将自然语言玩家输入归一为 `intent_vector`，例如：

- ambition
- loyalty
- honesty
- secrecy
- romance
- sacrifice
- cruelty
- curiosity
- selfhood
- risk

### 2. State Store
维护：

- 世界事实
- 时间线
- 角色状态
- 社交图谱
- Promise Ledger
- 最近场景函数
- 已访问事件
- 当前张力
- 主题推进度

### 3. Candidate Provider
职责：提出候选 **事件原子**，不是直接写 prose。

实现建议：
- v0：从静态事件池过滤
- v1：LLM 生成结构化 event atom
- v2：LLM + rules + retrieval hybrid

### 4. Canon Engine
职责：做 hard constraints 检查。

示例：
- 人物是否存在
- 前提事实是否满足
- 是否违反 forbidden facts
- 是否越过分级上限
- 是否让角色获得不应知道的信息

### 5. Scoring Engine
显式多维评分，不让模型“凭感觉”选剧情。

### 6. Critic Loop
- Consistency Critic
- Drama Critic
- Diversity Critic

### 7. Transition Engine
把事件作用到状态上，产生下一步状态。

### 8. Renderer
只负责“怎么写”，不负责“发生什么”。

## 为什么分层

如果把这几个问题混在一个 prompt 里，你会得到：

- 逻辑漂移
- 人物崩坏
- 设定遗忘
- 分支表面不同、实质相同
- 很难 debug
