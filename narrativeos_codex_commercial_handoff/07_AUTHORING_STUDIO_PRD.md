# 07. Authoring Studio PRD

## 目标

让作者无需修改核心代码，就能创建、验证、模拟、提交并发布新的世界包。

## 作者工作台的核心模块

### 1) World Composer
创建 world metadata、premise、canon、theme pillars、forbidden moves。

### 2) Character Lab
编辑：
- DestinyContract
- PoisonVector
- VowProfile
- WoundProfile
- AwakeningProfile
- speech/action traits

### 3) Scene Blueprint Editor
以“戏剧功能”而不是“具体文本”来编辑场景蓝图。

### 4) Karma/Debt Editor
配置：
- seed template
- ripening conditions
- debt deltas
- transformation paths

### 5) Style Pack Editor
控制：
- 文风
- 镜头感
- 对白比例
- 情绪强度
- 禁词/禁表达

### 6) Simulator
运行指定 world pack 的多次自动模拟，观察：
- 路线长度
- 角色崩坏率
- 结局触发分布
- 文本泄漏率
- 成本估计

### 7) Review Submission
一键提交审核，附带：
- world version
- simulation report
- risk answers
- sample chapters

## 作者权限等级

- Draft Author
- Verified Author
- Trusted Author
- Managed Studio

不同等级影响：
- 可发布世界数量
- 默认可见范围
- 是否需要强制人工复核
- 收益结算节奏

## 必做的作者体验原则

- 不让作者直接编辑内部 Python 结构体
- 尽量用表单、图谱、校验提示完成大部分工作
- 任何关键缺失都应有可解释的 validation report
