# Phase 1 Tasks：内容能力商业可用化

## Task 1.1：Weakest Pack Diagnostics

### 目标
建立 pack 级 root cause 报表，解释 weakest packs 为什么长期 rewrite。

### 建议改动
- 新增 `services/benchmark_diagnostics.py` 或等效模块
- 对每个 failing pack 产出：
  - Q03/Q04/Q05/Q09 占比
  - 章节长度、对白密度、场景细节密度
  - 过早收束率
  - choice distinctness

### 验收
- 可生成 JSON / markdown 报表
- 可直接被 Ops 页面消费

---

## Task 1.2：Scene Realization Calibration

### 目标
把 weakest packs 的 scene realization 调到可读，而不是继续只修 strongest packs。

### 建议改动
- 允许 pack capability overlay：
  - dialogue realism policy
  - response cadence profiles
  - sensory grounding policies
  - scene realization contracts
- 增加 pack-level calibration runner

### 验收
- 至少 2 个 weakest packs 的 pass rate 提升
- regression 不伤 strongest packs

---

## Task 1.3：Q03/Q04/Q05/Q09 定向修复

### 目标
把当前最影响付费体验的四类问题往下压。

### 建议改动
- Q03：重复检测与重写策略
- Q04：抽象解释句占比控制
- Q05：场景细节最小密度约束
- Q09：phase-aware 节奏与 premature ending 控制

### 验收
- NarrativeEval 报表显示对应 issue 下降
- demo 与 benchmark 均可复现

