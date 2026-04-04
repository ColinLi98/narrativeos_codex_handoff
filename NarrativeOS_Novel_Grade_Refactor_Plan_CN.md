# NarrativeOS：从“演示型互动故事”升级到“小说/漫剧级叙事引擎”的重构方案

## 1. 当前版本的根因诊断

### 1.1 为什么每回合内容很少
当前实现中，一个 `EventAtom` 基本就对应用户看到的一整个回合，而事件只有 `title + summary + state delta`，缺少“场景渲染层”。

现状路径：
- `search.py` 只是在事件池中挑一个分数最高的事件
- `memory.py` 只更新状态
- `pipeline.py` 直接把选中的事件返回给前端

问题：
- 事件是“状态更新原子”，不是“可读正文单元”
- 前端暴露的是规划信息，不是经过文学化渲染后的场景

### 1.2 为什么故事 10 回合内就结束
主要有三点：

1. `pipeline.py` 默认 `depth=2`
2. `search.py` 的 `static_candidate_provider()` 会把所有未访问事件都作为候选，没有章节/幕结构限制
3. `scoring.py` 的 `dramatic_tension_delta()` 在 `turn_index > 3` 后期望张力增量变成 `-0.02`

这意味着：
- 系统在第 4 回合以后开始偏好“降张力”事件
- 一旦结局事件满足前置条件，就很容易被高分选中
- 没有“最短故事长度”“幕级门槛”“结局锁”这类机制

### 1.3 为什么会出现很多工程化内容
当前前端展示了内部变量与调试字段，例如：
- `secret_meet_lin_wan -> lin_wan_asks_for_truth`
- `love / selfhood`
- `love, secrecy, curiosity`
- 各类事实 ID、scene function、route trace

问题本质不是文风，而是**没有把内部表示层和用户呈现层彻底隔离**。

### 1.4 为什么与现实小说/漫剧差距大
当前版本更接近：
- 一个可解释的剧情状态机 demo
- 一个互动故事原型

它还不是：
- 具备章节推进、铺垫回收、关系震荡、场景渲染、对白张力、长程命运感的小说系统

---

## 2. 升级目标：把产品从“回合制事件选择器”改成“章节式叙事系统”

## 核心原则

### 原则 A：一回合不等于一个事件
用户看到的一回合，应该是一整个“场景”或“章节片段”，内部可以由 3~8 个 beat / event 组成。

### 原则 B：事件负责逻辑，渲染负责文学性
- 事件层：决定发生什么
- 场景层：决定这段戏如何推进
- 渲染层：决定最终写成什么样

### 原则 C：故事先按章节走，再在关键处交互
不要每一步都让用户做一个小选择。现实中的小说/漫剧是“先沉浸，再抉择”。

### 原则 D：所有技术字段都只能出现在 Debug 模式
默认用户只能看到：
- 本章标题
- 正文
- 前情提要
- 角色关系变化（可选）
- 关键抉择

不能看到：
- event_id
- route trace
- theme key
- snake_case world facts
- score breakdown

---

## 3. 新的叙事层级设计

建议从现在的“turn-based event”升级为四层：

### 层 1：Story Arc（全书/全路线）
目标长度：
- 20~40 个内部 beats
- 8~15 个用户可感知章节/场景
- 3~6 个关键决策点

输出内容：
- 主命题
- 角色核心冲突
- 终局池（不是单一结局）
- 章节骨架

### 层 2：Chapter / Scene（用户感知回合）
用户每次点击“继续”，实际获得的是：
- 600~1500 字中文正文
- 1 个完整场景目标
- 至少 1 次关系或命运推进
- 2~4 个高质量抉择（不是按钮式流水线）

### 层 3：Beat（内部推进单元）
每个场景内部由多个 beat 构成，例如：
- 入场/环境建立
- 试探
- 冲突升级
- 让步或误会
- 小反转
- 余波

### 层 4：State Delta（状态更新原子）
保留你现在的 `EventAtom` 思路，但只作为最底层，不直接暴露给用户。

---

## 4. 需要新增的核心机制

### 4.1 幕结构与节奏门控（必须加）
新增 `story_phase`：
- setup
- early_rising
- midpoint
- crisis
- climax
- aftermath

规则：
- `ending` 类型事件只能在 `climax` 或 `aftermath` 阶段出现
- `reversal` 事件不能连续重复
- `consequence` 事件必须在重大承诺或秘密之后出现

建议新增字段：

```python
state.metadata["story_phase"]
state.metadata["chapter_index"]
state.metadata["target_chapter_count"]
state.metadata["decision_points_used"]
state.metadata["min_end_turn"]
```

### 4.2 结局锁（Ending Gate）
当前最大问题之一是结局太早开放。

所有结局事件增加门槛：
- 最少 turn / chapter 数
- 最少已关闭 promise 数
- tension 必须达到某阈值后再允许回落
- 至少发生 1 次 reversal + 1 次 sacrifice/ordeal + 1 次 consequence

建议新增：

```python
event.metadata["min_turn"]
event.metadata["required_scene_functions"]
event.metadata["required_closed_promises"]
event.metadata["required_tension_min"]
```

### 4.3 Promise Ledger 进阶版
当前 promise ledger 只有 open / close，还不够。

需要支持：
- promise importance（高/中/低）
- suspense value（拖多久最值钱）
- reveal window（何时适合揭晓）
- overdue penalty（拖太久会削弱故事）
- linked characters / linked facts

这决定“伏笔”是真伏笔，还是表面字段。

### 4.4 角色双层记忆
每个角色都应同时维护：
- objective memory：世界真实发生了什么
- subjective memory：角色自己相信什么、误解什么、隐瞒什么

否则就写不出：
- 戏剧性误会
- 反讽
- 隐瞒式亲密
- 迟到的报应

### 4.5 场景渲染层（最重要）
新增 `SceneRenderSpec`：
- viewpoint character
- prose mode（轻读 / 华彩 / 漫剧镜头）
- target word count
- must_include beats
- dialogue density
- sensory motifs
- emotional pivot
- ending cadence

然后由 renderer 把 3~8 个内部 beat 渲染成一段真正可读的正文。

---

## 5. 用户体验层的重做建议

### 5.1 默认只保留 Reader Mode
当前 UI 混合了：
- 作者后台
- 调试台
- 玩家阅读器

建议拆为三个模式：

#### Reader Mode（默认）
只显示：
- 章节标题
- 正文
- 前情提要
- 可选抉择

#### Director Mode（高阶玩家）
可选显示：
- 当前张力
- 人物关系变化
- 未兑现伏笔数量

#### Author Debug Mode（仅创作者/开发者）
显示：
- event ids
- route trace
- score breakdown
- promise ledger
- hidden facts

### 5.2 把“看工程信息”改成“看故事”
你截图里最伤沉浸感的不是内容少，而是“剧情还没开始，后台先露出来了”。

建议前端隐藏：
- `secret_meet_lin_wan`
- `lin_wan_asks_for_truth`
- `love / selfhood`
- `love, secrecy, curiosity`
- 所有事实 ID 与状态统计

默认玩家界面最好连“scene function”都看不到。

### 5.3 让选择看起来像命运抉择，而不是接口按钮
当前选择文案已经比纯按钮好，但还不够“有文学张力”。

建议 choice schema 增加：
- external action（表面行为）
- inner intent（内在动机）
- tradeoff（代价）
- likely emotional tone（情绪后果）

最终给玩家展示的是“含代价的选择”，不是策略按钮。

---

## 6. 对现有代码的具体改造建议

## 6.1 models.py
新增：
- `StoryArcPlan`
- `ChapterPlan`
- `SceneBeat`
- `SceneRenderSpec`
- `ChoiceOption`
- `EndingGate`
- `NarrativeViewModel`

## 6.2 search.py
从“事件池 beam search”升级为“两阶段搜索”：

### 第一阶段：场景规划
从全局状态中挑选适合当前章节的若干 scene intents：
- intimate confrontation
- public pressure
- false calm
- hidden reveal
- social humiliation
- sacrifice test

### 第二阶段：beat 生成与筛选
在场景内再生成 3~8 个 beats，并做：
- legality check
- phase check
- promise check
- diversity check

### 必改点
- 不再使用纯 `static_candidate_provider()` 作为主逻辑
- 引入 phase-aware provider
- 结局候选必须 gated

## 6.3 scoring.py
当前打分维度太少，而且缺少“小说感”。

新增评分项：
- `payoff_readiness`
- `dialogue_pressure`
- `world_texture`
- `surprise_inevitability_balance`
- `promise_value`
- `scene_completeness`

并修正：
- `dramatic_tension_delta()` 不应在第 4 回合后默认偏好降张力
- tension 目标应由 `story_phase` 驱动，而不是固定 turn rule

建议张力曲线：
- setup: 低 -> 中
- early_rising: 中 -> 中高
- midpoint: 短暂失衡
- crisis: 高
- climax: 最高
- aftermath: 下降但有余震

## 6.4 pipeline.py
拆成：
- `plan_arc()`
- `plan_next_scene()`
- `simulate_scene_beats()`
- `render_scene()`
- `present_scene_for_reader()`

现在的 `plan_next_turn()` 太短路了：
- 直接选事件
- 直接返回给前端

以后应改为：
- 先选场景意图
- 再在场景内推进多个 beat
- 最后渲染成正文与选择

## 6.5 memory.py
增加：
- `advance_story_phase_if_needed()`
- `update_character_private_memory()`
- `update_scene_history()`
- `update_payoff_pressure()`
- `aging_open_promises()`

## 6.6 新增 rendering.py
职责：
- 把内部 beat 序列转成 600~1500 字中文场景
- 控制旁白与对白比例
- 统一风格
- 去除工程字段

建议提供三种渲染风格：
- `novel_light`
- `novel_lush`
- `manhua_drama`

## 6.7 新增 presenter.py
职责：
- 生成 Reader Mode 的 view model
- 屏蔽内部字段
- 将内部 theme key 映射为对外可读表述
- 生成“前情提要”“本章看点”“选择提示”

## 6.8 新增 sanitizer.py
职责：
- 检测输出中的 snake_case、箭头、debug key、变量名
- 阻止 `route=`, `event_id`, `scene_function`, `convergence_key` 等泄漏
- 检测“工程腔”句式

---

## 7. 数据与内容层需要同步扩容

当前 demo 之所以看起来像 demo，不只是代码结构，还因为内容密度太低。

### 最低建议
一个可玩的单世界至少需要：
- 10~15 个核心角色状态模板
- 30~50 个地点细节模板
- 150~300 个 event / beat atoms
- 40~80 个 scene intents
- 20~30 个高质量 choice frame 模板
- 10~20 个 payoff / reveal 机制模板

### 世界细节库必须加
每个地点都需要：
- 可见物
- 气味/声音/天气
- 社会阶层痕迹
- 行为禁忌
- 可用于冲突的空间结构

否则文字很快会变成抽象说明文。

---

## 8. 你应该如何定义“更接近现实”

不要把目标定义成“更像模型写的长文本”，而要定义成：

### 对用户来说
- 一回合像在看一段真正的小说/漫剧正文
- 选择像在改命，而不是点流程
- 前面的决定会在后面反噬或兑现
- 人物会记仇、会误解、会迟疑、会自欺

### 对系统来说
- 故事平均可支撑 8~15 个可感知章节
- 结局不会在第 4~8 步过早触发
- 输出不再泄漏工程字段
- 每个场景至少有一个戏剧动作，不只是总结

---

## 9. 建议的目标指标

### 内容指标
- 平均每章正文：600~1500 中文字
- 平均每条路线章节数：8~15
- 平均每条路线关键抉择数：3~6
- 每章对白占比：20%~60%（题材可配）
- 伏笔兑现率：>70%

### 质量指标
- 工程字段泄漏率：0
- 人物崩坏率：<10%
- 重复 scene function 连续出现率：<15%
- 早结局率（前 6 章结束）：<5%
- 用户“愿意继续看下一章”率：>55%

### 体验指标
- 单次阅读停留时长
- 第二路线重玩率
- 角色选择分布熵
- 章节完成率

---

## 10. 给 Codex 的执行顺序

### Phase 1：先把“不要再提前完结”修好
1. 加 `story_phase`
2. 加 `min_end_turn`
3. 给 ending 事件加 gate
4. 把 tension 曲线改成 phase-based

### Phase 2：把“一个回合 = 一个事件”改掉
1. 引入 `ChapterPlan`
2. 一次生成 3~5 个 beats
3. 统一走 renderer
4. 前端显示章节正文而不是事件 summary

### Phase 3：彻底清理工程化泄漏
1. 新增 presenter/sanitizer
2. UI 默认进入 Reader Mode
3. debug 信息全部隐藏到开发者面板

### Phase 4：把故事拉长到可阅读长度
1. 引入 scene intents
2. 增加 promise aging / payoff pressure
3. 扩展事件库与场景模板
4. 增加章节 recap 与余波机制

### Phase 5：提升文学性与漫剧感
1. 增强对白驱动
2. 增强镜头感/动作线
3. 增加场景细节库
4. 增加角色误解和迟滞后果

### Phase 6：再做多路线与商业化层
1. route replay
2. author controls
3. creator tools
4. 付费结局/长篇路线

---

## 11. 最重要的一句判断

你现在的问题不是“模型文笔不够”，而是：

**你把内部叙事原子直接端给了用户，而没有经过“章节化 + 场景化 + 文学化渲染 + 呈现层隔离”。**

只要这一层不补上，内容再多，看起来也会像工程 demo；
一旦这层补上，哪怕底层仍然是状态机 + 搜索，也会开始像真正的小说系统。
