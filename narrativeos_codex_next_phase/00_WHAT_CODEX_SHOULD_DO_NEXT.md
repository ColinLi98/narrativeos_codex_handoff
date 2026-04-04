# Codex 接下来应该做什么

## 核心判断

NarrativeOS 当前已经是：

- 多 World Pack 的 Beta 内核
- 已接入 Karma Character Engine v0.1
- 已有 Reader / Author / Ops 三端骨架
- 已有 NarrativeEval、cross-pack benchmark、publish gate

但它还不是成熟商业化产品。

因此，**Codex 的下一阶段目标不是“再把当前 Jade Court 写得更好”**，而是完成下面 3 个过渡：

1. 从 **pack-specific 优化** 过渡到 **cross-pack capability 提升**
2. 从 **可运行 Beta kernel** 过渡到 **可持续供给 + 可运营 Beta product**
3. 从 **规则 / 资产驱动** 过渡到 **带数据飞轮的商业化内容系统**

## 接下来 90 天，真正该做的三件大事

### A. 先把内容能力拉到“商业可用”

先不要做支付闭环，不要先做大规模增长。

优先级最高的是：

- 把 weakest packs 从长期 `rewrite` 拉出来
- 继续提升 `cross_pack_pass_rate`
- 重点压低：`Q03 / Q04 / Q05 / Q09`
- 建立更可靠的 pack-level 失败诊断与修复闭环

### B. 把 Author 做成真实供给工具

现在 Author 已有最小路径，但还不够支撑内容供给。

Codex 应优先补：

- draft detail
- 角色卡编辑
- scene blueprint 编辑
- style / sensory / pacing 配置编辑
- simulate / validate drill-down
- asset diff / versioning

### C. 把 Ops 与商业化骨架做实

现在已有 review / publish / rollback / metering 骨架，但还不够形成可收费、可追踪、可审计的闭环。

Codex 应优先补：

- review history
- publish checklist
- rollback history
- quality trend drill-down
- entitlement / credits / access tier 的可运行主路径
- audit trail

## 明确禁止 Codex 继续做的事情

- 不要继续围绕单一剧情写“更像小说”的 pack-specific patch
- 不要只改 `core/writer.py` 来掩盖 kernel 问题
- 不要跳过测试、回归和 metrics
- 不要在没有 benchmark 提升的情况下声称“质量提升了”
- 不要优先做支付 UI，而忽略 weakest packs 仍长期 rewrite

## 这阶段的北极星

### 北极星 1：内容能力

- `cross_pack_pass_rate` 持续上升
- weakest packs 脱离长期 `rewrite`
- `Q03 / Q04 / Q05 / Q09` 明显下降

### 北极星 2：供给效率

- 普通作者能从 brief 产出可编辑 draft
- 作者能直接编辑角色 / scene / style / pacing 资产
- validate / simulate 的问题能被清楚追踪

### 北极星 3：运营可控

- Ops 能追踪 issue -> module -> pack -> asset
- publish / rollback 有完整记录
- entitlement / meter 可支持后续收费实验

