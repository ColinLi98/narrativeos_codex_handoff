# 03. North Star PRD（目标产品定义）

## 产品定位

NarrativeOS 是一个 **AI 叙事操作系统**：
- 对读者，它是可进入、多路线、可复玩的叙事产品；
- 对作者，它是 world pack + chapter generation + review + publish 的创作平台；
- 对运营，它是可审核、可计费、可观测的内容系统。

## 核心用户

### 1) Reader
希望进入某个世界，阅读章节、做选择、获得沉浸与情绪价值。

### 2) Author
希望上传世界、角色、风格、场景蓝图，并让 AI 在其框架下生成章节与路线。

### 3) Editor/Ops
希望管理质量、风险、上线节奏、模型成本、营收与用户反馈。

## 核心体验目标

### Reader 体验目标
- 一次“继续”得到的是一章，而不是一条摘要
- 不看到工程化字段
- 章节之间存在明确的关系余波、因果成熟与命运推进
- 不同世界有显著题材差异，但交互逻辑一致

### Author 体验目标
- 不需要改代码即可创建/验证/发布 world pack
- 能可视化地编辑角色、场景蓝图、因果种子模板
- 能在发布前运行模拟与评测

### Ops 体验目标
- 能看到质量、投诉、风险、成本、付费、留存指标
- 能冻结/回滚某个 world version
- 能按区域、风险等级、商业策略管理分发

## 非目标

- 不以“无限自由聊天”作为产品核心
- 不把每次用户输入都当成开放式 roleplay
- 不追求一次上线所有题材与所有国家
- 不把影视改编代理作为当前阶段主营能力

## 核心产品对象

- Library Shelf：世界库
- World Detail：世界详情页
- Session Reader：阅读器
- Route Branch Preview：命运分歧预览
- Author Studio：作者工作台
- Ops Console：运营与审核后台

## 北极星指标

- `chapter_completion_rate`
- `route_replay_rate`
- `paid_route_conversion`
- `reader_d7_retention`
- `worldpack_publish_success_rate`
- `cost_per_completed_chapter`
- `policy_violation_rate`

## Beta 版最小可用范围

Reader：
- 3 个高质量世界
- 每个世界至少 2 条完整路线
- 支持章节阅读、选择、回看、收藏、购买

Author：
- 创建 world pack 草稿
- 校验 world pack
- 运行模拟
- 提交审核

Ops：
- 审核与发布
- 世界版本管理
- 使用量与成本看板
