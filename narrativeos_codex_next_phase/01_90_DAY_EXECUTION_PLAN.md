# 90 天执行路线图

## Phase 0（第 1-2 周）
### 目标：建立“不要再围绕当前剧本优化”的工程护栏

交付：

- core / worldpack 边界检查
- cross-pack benchmark 报表增强
- AGENTS.md 生效
- merge gate 增加跨 pack 指标

验收：

- 任意 PR 必须展示 cross-pack delta
- core 内禁止直接 import 具体 pack 逻辑
- benchmark 输出 strongest / weakest / failing dimensions

---

## Phase 1（第 3-5 周）
### 目标：把 weakest packs 拉出长期 rewrite

交付：

- weakest pack 诊断器
- Q03/Q04/Q05/Q09 的 pack-level root cause 报表
- scene realization calibration 机制
- pack capability overlay 调参主路径

验收：

- 至少 2 个 weakest packs 的 pass rate 脱离 0
- cross_pack_pass_rate 有可量化提升
- NarrativeEval 报告支持 pack -> dimension drill-down

---

## Phase 2（第 6-8 周）
### 目标：把 Author 变成真实供给工具

交付：

- draft detail 页
- 角色卡编辑器
- scene blueprint 编辑器
- style/sensory/pacing 编辑器
- simulate / validate detail report
- asset diff / version history

验收：

- 普通作者可从 brief 到 draft 到 validate 到 simulate
- 作者可不改 JSON 手工维护关键资产
- draft / asset 版本可追溯

---

## Phase 3（第 9-10 周）
### 目标：把 Ops 与商业化骨架做实

交付：

- review history
- publish checklist
- rollback history
- quality trend dashboard
- entitlement / credits / access tier 主路径
- audit trail

验收：

- Ops 可完整查看一次 pack 从 draft 到 publish 的过程
- rollback 可追溯
- 有可运行的 entitlement 与 meter 主路径

---

## Phase 4（第 11-12 周）
### 目标：为 learned layer 做数据接口准备

交付：

- 章节级人工评审结构
- issue 修复前后样本采集
- 用户继续读 / 流失事件埋点规范
- author 修改行为日志 schema

验收：

- 为 learned evaluator / reranker 留出明确数据出口
- 线上与离线指标口径统一

