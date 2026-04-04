# Phase 0 Tasks：工程护栏与 benchmark 观测

## Task 0.1：Core / WorldPack 边界检查

### 目标
阻止 core 被具体 pack 污染。

### 建议改动
- 增加静态检查或轻量 lint
- 扫描 `src/narrativeos/core/` 中是否 import 具体 pack 模块
- 在 CI 中阻断违规提交

### 验收
- 新增测试或脚本
- README / docs 更新
- CI 可运行

---

## Task 0.2：Cross-pack benchmark 报表增强

### 目标
让 weakest packs 的问题更容易被诊断，而不只是看到 pass rate。

### 建议改动
- benchmark 输出每个 pack 的：
  - pass/rewrite/block
  - top failing issue categories
  - dimension scores
  - delta summary
- 生成 machine-readable JSON

### 验收
- CLI 正常运行
- 输出可被 Ops 使用

---

## Task 0.3：Merge gate 引入跨 pack 指标

### 目标
不再允许只证明某一个 pack 变好。

### 建议改动
- PR 检查增加：
  - cross_pack_pass_rate delta
  - weakest pack delta
  - top failing issues delta

### 验收
- CI / scripts 可跑
- docs 说明清楚

