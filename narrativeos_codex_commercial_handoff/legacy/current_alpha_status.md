# NarrativeOS 当前状态说明

## 一句话结论

截至当前版本，NarrativeOS 已经从“事件搜索 demo”升级为一个**可运行的章节化叙事引擎 Alpha**，并完成了 **Karma Character Engine v0.1** 的接入。

它现在已经具备：

- 章节化推进，而不是单事件拼接
- Reader Mode 输出，而不是工程调试文本
- 人物因果驱动，而不只是 goals / emotions / trust
- 因果种子、关系债、命运压力、关系图等核心运行结构

但它仍然**不是商业化完成品**。

更准确地说，它目前处于：

- 可演示
- 可测试
- 可继续迭代
- 适合内部验证 / 小范围体验

还不适合直接当作成熟付费产品上线。

## 当前已经完成的部分

### 1. 叙事引擎基础

- 已完成从“一个回合 = 一个事件”到“一个回合 = 一个场景”的升级
- 每章内部支持 3-5 拍结构
- 已具备 `story_phase / chapter_index / min_end_turn`
- 已有 phase-aware 的章节推进与结局门控

### 2. Karma Character Engine v0.1

角色状态已从基础人物体升级为包含以下层级：

- 命：`DestinyContract`
- 业：`KarmicSeed`、`DebtEntry`
- 毒：`PoisonVector`
- 愿：`VowProfile`
- 惑：`WoundProfile`
- 智：`AwakeningProfile`

全局状态已新增：

- `fate_pressure`
- `karmic_weather`
- `unresolved_debts`
- `relationship_graph`

事件状态已新增：

- `temptation_vector`
- `vow_tests`
- `wound_triggers`
- `debt_deltas`
- `karmic_seed_creations`
- `karmic_seed_resolutions`
- `awakening_affordances`
- `concealment_level`
- `consequence_delay_hint`

### 3. 评分与搜索

当前候选选择已不再主要依赖简单的 goal overlap，而是转向以下因果驱动项：

- `desire_pull`
- `shadow_pull`
- `poison_pull`
- `vow_pull`
- `wound_pull`
- `debt_pull`
- `karma_pull`
- `fate_pull`
- `wisdom_resistance`

这意味着人物不会只做“最合理”的事，而会更多地表现为：

- 顺着自己的习气行动
- 保护自我叙事
- 暂时逃避痛苦
- 或在少数时刻接近真相与愿

### 4. Reader Mode 与前端可用性

默认用户层仍然是 Reader Mode，主要返回：

- `chapter_title`
- `recap`
- `body`
- `scene_card`
- `choices`
- `relationship_hints`
- `can_continue`

当前正文已经能做到：

- 不直接泄漏 `event_id / seed_id / debt_type / endgame_shape / poison` 等工程字段
- 能把内部因果转换为可读的章节信号
- 保留章节感、人物冲突感和关系余波

Web 前端仍可正常使用：

- 创建 / 恢复 / 删除 session
- 预览 route
- 推进一步
- 查看 replay
- 查看 Storybook 图文视图

## 当前验证结果

当前基线如下：

- `pytest -q`：`40 passed`
- `python -m src.narrativeos.demo`：正常
- `GET /health`：正常
- `/app`：可打开并继续使用

这说明现在系统在“代码可运行、API 可跑、示例世界可玩、测试可回归”这个层面是稳定的。

## 现在已经能做到什么

如果你现在把它当作一个内部 demo / Alpha 产品，它已经可以：

1. 让用户进入一个世界并推进章节。
2. 让人物行为受到愿、伤、毒、债、seed、fate 的共同影响。
3. 让行为不只产生即时后果，而能留下延迟成熟的因果种子。
4. 让关系不只体现为 trust，而有 attachment / resentment / shame / obligation / fear 等更真实的维度。
5. 让章节规划开始偏向“逼出哪种人性”而不是只推进事实。

## 现在还不能算完成的部分

### 1. 文学质量还不够稳定

虽然正文已经明显比早期 demo 强，但还没到：

- 连续 30-50 章都稳定好看
- 多世界都稳定成立
- 每个角色都有成熟作者级语言习惯

当前仍然更像“强规则 + 较强模板渲染”的 Alpha，而不是成熟小说引擎。

### 2. 内容供给系统还不够

现在 demo 世界已经升级，但仍然主要只有少数示例世界。

缺的不是再多一个按钮，而是：

- 更多完整世界观
- 更多高质量事件原子
- 更多精标过的 Karma / Fate / Debt 数据
- 更完整的作者工具与内容生产流

### 3. 商业产品骨架还没补齐

当前还没有完整商业化需要的这些部分：

- 登录 / 用户资产体系
- 订阅 / 额度 / 支付
- 运营后台
- 审核与风控
- 指标面板与转化分析
- 成本控制与模型策略

### 4. Karma v0.1 还只是第一层

现在已经有：

- 种子创建
- 种子成熟
- 转化 / 兑现
- 债务与关系图
- 命运压力

但仍然还缺更深的一层：

- 更复杂的 ripening conditions
- 更细的种子转化链
- 更强的长期关系线编排
- 更成熟的 scene intent 与 LLM 混合规划

## 商业化位置判断

如果按产品阶段判断，我会把它放在：

### 当前所在阶段

`可运行 Alpha / 创始人原型`

### 还没到的阶段

- 小规模付费 Beta
- 稳定商业化内容产品
- 面向普通用户的成熟连载平台

### 粗略完成度判断

如果把“最终商业化版本”定义为 100%，当前大致在：

`25% - 35%`

原因不是功能没做，而是以下能力还不够稳定：

- 内容质量可复制
- 内容供给可扩张
- 成本可控
- 留存可验证
- 风险可管理

## 最关键的结论

现在最大的缺口已经不是“会不会生成下一章”，而是：

**能不能稳定生成值得被反复阅读、值得被付费的下一章。**

这是两个完全不同的问题。

NarrativeOS 现在已经跨过了前者，但离后者还有明显距离。

## 下一步最值得做的事情

### P0

- 继续提高章节文本稳定性
- 扩充世界内容库
- 丰富 KarmaSeed 的成熟与转化规则
- 让 scene intent 更像真正的人性冲突规划器

### P1

- 做作者工具和内容标注工具
- 做运营 / 评测 / 质量面板
- 做用户账户与 session 资产体系

### P2

- 做订阅 / 支付 / 商业策略
- 做审核、风控、观测与成本管理
- 做多世界、多题材内容矩阵

## 结尾判断

NarrativeOS 现在已经不再是一个简单的“剧情搜索 demo”。

它已经是一个：

- 有状态
- 有因果
- 有人物内在牵引
- 有章节结构
- 有 Reader Mode 输出
- 有前端可试玩入口

的 Alpha 叙事系统。

但离真正商业化，还差内容质量稳定化、内容供给系统、产品骨架和运营能力这几大块。
