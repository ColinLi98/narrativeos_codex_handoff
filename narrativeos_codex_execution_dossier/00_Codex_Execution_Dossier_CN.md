# NarrativeOS：如何高效使用 Codex 开发的执行档案

> 更新说明：
> 当前仓库未来任务派发的 lane taxonomy 与 recurring dispatch protocol，
> 以 `narrativeos_codex_execution_dossier/06_RECURRING_DISPATCH_PROTOCOL.md` 为准。
> 本文保留为背景与执行上下文，早期 5-lane 表述应视为历史版本。

## 0. 这份档案解决什么问题

你们现在最大的风险，不是“Codex 不会写代码”，而是：

1. **Codex 很容易退化成 pack-level 优化器**  
   它会优先优化当前最显眼、最容易改出效果的 pack、writer、prompt 或某条剧情线。

2. **NarrativeOS 的真实目标是 kernel-first / product-first**  
   你们已经不再是单作品 demo，而是一个具备多 World Pack、Reader / Author / Ops、NarrativeEval、cross-pack benchmark、会员/额度骨架的商业化 Beta 内核。

3. **如果没有明确 operating model，Codex 会持续消耗在“看起来更好”的局部修补上**  
   例如：当前 pack 的文风优化、某个页面的微调、局部 prompt 重写、某个 world 的事件扩写。

所以，这份档案的目标是把 Codex 变成：

- **可被管理的工程执行器**
- **围绕商业化目标推进的开发代理**
- **按 lane / phase / acceptance criteria 运作的 PR 机器**

而不是一个“哪里顺手修哪里”的写码助手。

---

## 1. 当前阶段判断

NarrativeOS 当前最准确的阶段，不是 Alpha，也不是成熟商业化产品，而是：

**可运营的商业化 Beta 内核**

你们已经具备：
- 多 World Pack runtime
- Reader / Author / Ops 三端
- NarrativeEval + cross-pack benchmark
- learned governance
- 会员/额度/订阅状态机骨架
- 最小 metering 与 entitlements

但仍明显缺：
- 长线章节质量稳定到真正商业可用
- weakest packs 长期稳定
- 真实支付闭环
- 正式账户/权限体系
- 作者供给效率
- learned layer 从治理层推进到模型增强层
- 生产级 infra / routing / observability

**因此 Codex 的任务不能再围绕“把当前剧情写好”，而要围绕“把 Beta 内核推进到收费产品”展开。**

---

## 2. Codex 的角色定义

Codex 在 NarrativeOS 里只做三类事：

### A. 结构化工程实现
- kernel / service / api / app / persistence 的明确改造
- benchmark / eval / metering / entitlement / ops dashboard 等系统功能
- author / ops / reader 的产品工作流实现

### B. 诊断与回归
- weakest pack diagnostics
- cross-pack delta report
- regression runner
- issue heatmap
- long-route benchmark

### C. 小范围、可验证的优化
- 某一条 lane 里的一个 PR 级任务
- 可量化、有测试、有回归、有报表

Codex **不做**：
- “继续把内容写得更好”
- “想办法让整个产品变得更厉害”
- “顺手把当前 pack 再润一润”
- 没有边界的大重构
- 多 lane 混改
- 没有 benchmark delta 的“感觉更好”改动

---

## 3. 你应该怎么给 Codex 发任务

### 原则 1：先 Ask，后 Code
每个中大型任务都先让 Codex 出 implementation plan，再切到 Code。

### 原则 2：任务大小控制在 1 个 PR / 1 小时人工工作量 / 数百行代码量级
不要一次性给“做完整会员系统”“做完整支付”“让 weakest packs 全部过线”这种任务。

### 原则 3：Prompt 要像 GitHub Issue
每个任务都必须写清楚：
- 背景
- 目标
- 非目标
- 影响范围
- 文件/模块
- 测试要求
- 输出格式
- 验收标准

### 原则 4：必须有 AGENTS.md
AGENTS.md 是常驻上下文，不要把仓库规则每次都重新讲一遍。

### 原则 5：每个 PR 必须展示 cross-pack delta
NarrativeOS 不接受只证明 Jade Court 变好的 PR。

---

## 4. 先在仓库里放什么

在 repo root 放这些文件：

1. `AGENTS.md`
2. `docs/codex/ISSUE_TEMPLATE.md`
3. `docs/codex/PR_REVIEW_TEMPLATE.md`
4. `docs/codex/ACCEPTANCE_METRICS.md`
5. `scripts/codex_bootstrap.sh`
6. `scripts/run_core_checks.sh`
7. `scripts/run_cross_pack_benchmark.sh`

### `scripts/codex_bootstrap.sh` 最少做这些事
- 安装依赖
- 说明 Python / Node 版本
- 初始化环境变量
- 提供 demo / pytest / benchmark / app 启动方法
- 明确哪些命令是 Codex 提交前必须跑的

---

## 5. NarrativeOS 的开发 lane

Codex 之后的开发，强制分成 5 条 lane。**一个 PR 只能属于一条主 lane。**

### Lane A：Content Commercial Readiness
目标：把内容质量拉到“值得持续阅读、值得收费”的水平。

任务例子：
- long-route benchmark
- weakest pack diagnostics
- issue heatmap
- dialogue distinctness metric
- scene detail density metric
- Q03 / Q04 / Q05 / Q09 定向修复

### Lane B：Author Supply System
目标：让供给效率上来，不再靠核心团队手工扶正。

任务例子：
- 角色卡编辑
- scene blueprint 编辑
- pacing / hook / style 编辑
- draft diff
- validation / simulation drill-down
-协作与审批流

### Lane C：Monetization & Entitlements
目标：让会员、credits、权限、metering 形成真实产品闭环。

任务例子：
- subscription state machine
- story_credits / studio_credits
- entitlement audit
- reader/author gating
- checkout provider boundary
- renewal/cancel/retry/past_due 流程

### Lane D：Ops & Governance
目标：让真实收费产品可运营、可排查、可回滚。

任务例子：
- review history
- account detail
- audit trail
- moderation / rights / abuse flow
- alerting
- quality trend drill-down

### Lane E：Infra & Reliability
目标：让系统接近生产。

任务例子：
- Postgres migration / Alembic
- provider routing / retry / cache / fallback
- observability
- cost governance
- rollout / rollback
- backup / restore

---

## 6. 现在 Codex 最该做什么

## Phase 0：先把“Codex 不再围着当前剧本转”这件事做成工程事实

### Task 0.1：Root AGENTS.md
目标：
- 把 NarrativeOS 的 kernel-first、cross-pack、single-lane、PR gate 规则写进 root AGENTS.md

验收：
- 仓库根目录出现正式 AGENTS.md
- 明确禁止 pack-specific prose tuning 作为默认开发方向
- 明确要求 Ask mode -> Code mode
- 明确 PR 需提供 cross-pack delta

### Task 0.2：Cross-pack benchmark 报表增强
目标：
- benchmark 不只输出 pass_rate，还输出 per-pack issue mix、long-route quality、mid-arc drop、dialogue distinctness、scene detail density

验收：
- 生成 JSON + markdown summary
- weakest packs 自动排序
- 每次 benchmark 可对比上次 delta

### Task 0.3：Merge gate 引入 cross-pack 指标
目标：
- 所有主要 PR 必须展示跨 pack 的质量 delta，而不是某个 pack 的单点提升

验收：
- CI 或本地检查能失败
- PR 模板里要求填写 strongest/weakest pack delta

---

## Phase 1：把“为什么还不够商业可用”变成可见报表

### Task 1.1：Weakest Pack Diagnostics
输出：
- weakest packs
- 最差章节列表
- issue category 分布
- 归因到 module / asset / policy
- 下一步修复建议

### Task 1.2：Long-route benchmark
目标：
- 30–50 章路线质量评测
- 不再只看单章 pass / rewrite / block

### Task 1.3：Q03 / Q04 / Q05 / Q09 定向根因报表
目标：
- 让“重复、解释句、场景不足、节奏掉速”有结构化根因，而不是继续靠主观争论

---

## Phase 2：把 Author 做成供给工具

### Task 2.1：角色卡编辑器
### Task 2.2：scene blueprint 编辑器
### Task 2.3：draft diff + simulation drill-down
### Task 2.4：style / pacing / hook 控制面板

---

## Phase 3：把会员与额度做成产品主线

### Task 3.1：Tier config + entitlement matrix
### Task 3.2：story_credits / studio_credits metering
### Task 3.3：Reader / Author gating
### Task 3.4：subscription lifecycle
### Task 3.5：entitlement audit / manual grant / revoke

---

## 7. 每个任务都必须长什么样

下面是你给 Codex 的标准任务结构：

```text
Title:
[Lane X] <Task name>

Background:
NarrativeOS is now a commercial beta kernel with multi-world runtime, Reader/Author/Ops, NarrativeEval, and partial monetization skeleton. This task must improve the product at kernel/product level, not pack-specific prose tuning.

Goal:
<one clear goal>

Non-goals:
- Do not tune only jade_court_exam_pack
- Do not do prose-only changes
- Do not touch unrelated lanes
- Do not introduce broad refactors outside task scope

Scope:
Files/modules allowed:
- ...
Files/modules out of scope:
- ...

Required outputs:
- code changes
- tests
- docs update
- benchmark delta
- sample output / screenshot if UI

Validation:
- run tests
- run benchmark
- include strongest/weakest pack delta
- include risks and follow-ups

Acceptance criteria:
- ...
```

---

## 8. 你要怎么审 Codex 的结果

不要只问“跑通了吗”，要按下面 8 条审：

1. **是不是只修了当前 pack？**
2. **有没有新的 cross-pack 证据？**
3. **有没有 benchmark delta？**
4. **测试有没有补齐？**
5. **docs 有没有更新？**
6. **是否越界改了其他 lane？**
7. **是否把问题做成系统能力，而不是一次性 patch？**
8. **是否让商业化更近了一步？**

只要第 1 / 2 / 3 条不成立，这个 PR 基本就不应该 merge。

---

## 9. 创始人 / 负责人每周怎么用 Codex

### 周一：选任务
- 只选 2–4 个 PR 级任务
- 每个任务明确属于哪条 lane
- 每个任务都写 issue 风格 brief

### 周二至周四：并行跑
- 让 Codex 先 Ask mode 出计划
- 通过后再 Code mode
- 同时跑多个小任务，而不是一个大任务

### 周五：只做审查
- 看 benchmark delta
- 看 weakest pack 是否真的改善
- 看是否推进了商业闭环
- 拒绝 pack-level 的漂亮小修补

---

## 10. 未来 30 天建议的 Codex 顺序

### Week 1
- Task 0.1 Root AGENTS.md
- Task 0.2 Cross-pack benchmark 报表增强
- Task 0.3 Merge gate 引入 cross-pack 指标

### Week 2
- Task 1.1 Weakest Pack Diagnostics
- Task 1.2 Long-route benchmark

### Week 3
- Task 1.3 Q03/Q04/Q05/Q09 根因报表
- Task 2.1 角色卡编辑器

### Week 4
- Task 2.2 scene blueprint 编辑器
- Task 3.1 tier config + entitlement matrix
- Task 3.2 metering + gating

---

## 11. 最重要的三条硬规则

### 规则 A
**NarrativeOS 的目标是“收费产品”，不是“更像作家”。**  
任何任务都要回答：它是否让收费产品更近了一步？

### 规则 B
**Codex 默认必须优化 kernel / product / ops / monetization，不默认优化当前剧本。**

### 规则 C
**任何“感觉更好”的改动，如果没有 cross-pack delta，就不算完成。**

---

## 12. 你现在发给 Codex 的第一条消息

```text
请先阅读仓库根目录 AGENTS.md，然后只执行 [Lane A / Phase 0 / Task 0.2]：Cross-pack benchmark 报表增强。

要求：
1. 先用 Ask mode 输出 implementation plan，不要直接改代码。
2. 只处理当前任务，不要顺手做其他优化。
3. 改动后必须：
   - 补测试
   - 跑测试
   - 跑 benchmark
   - 更新 docs/README
4. 输出结果必须包含：
   - 改动文件清单
   - 测试结果
   - benchmark delta
   - strongest/weakest packs 变化
   - 新增报表样例
   - 风险与下一步建议

注意：
- 不要做 pack-specific prose tuning
- 不要只展示 Jade Court 变好
- 必须让 weakest packs 的问题更容易被诊断
```

---

## 13. 一句话结论

你要高效用 Codex，不是给它更多自由，而是给它更强的**边界、节奏、验收和证据要求**。

NarrativeOS 现在最需要的，不是“继续让它写”，而是：

**把 Codex 变成推动商业化 Beta 内核向收费产品前进的工程系统。**
