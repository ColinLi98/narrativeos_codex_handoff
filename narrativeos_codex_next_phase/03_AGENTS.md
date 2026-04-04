# AGENTS.md

## 项目定位

NarrativeOS 不是单作品互动小说项目，而是一个：

- 多 World Pack 叙事内核
- 具备 Karma / Fate / Debt / Seed 人物逻辑
- 具备 Reader / Author / Ops 三端骨架
- 具备 NarrativeEval 与 publish gate
- 正在向商业化 Beta 演进的内容系统

## 当前阶段

- Beta kernel 已成形
- 商业化闭环只有骨架
- 真正缺口在 cross-pack 质量稳定性、作者供给、Ops 工作台、数据飞轮

## 高优先级原则

1. Kernel-first
   - `src/narrativeos/core/` 不允许写死具体 world pack 逻辑

2. Capability-first
   - 改动应尽量落到通用 contract / service / evaluator / tooling

3. Cross-pack-first
   - 任何质量改动都必须用多个 pack 验证

4. Commercialization-aware
   - 不只看“能生成”，还看“能否供给、评审、发布、回滚、计费”

## 禁止事项

- 不要围绕 Jade Court 做局部写作调参并宣称全局进步
- 不要将 pack asset 和 core 逻辑耦合
- 不要引入 leaked / reverse-engineered 第三方 agent 代码
- 不要跳过测试和 benchmark

## 建议目录边界

- `src/narrativeos/core/`：通用 engine / contracts / evaluator / planners
- `src/narrativeos/worldpacks/`：pack 资产与配置
- `src/narrativeos/services/`：业务服务
- `src/narrativeos/api/`：API
- `src/narrativeos/persistence/`：持久层
- `app/`：Reader / Author / Ops

## 任务完成定义

一个任务只有在以下条件都满足时才算完成：

- 代码通过测试
- 文档更新
- 有可复现的验收步骤
- 有清晰的指标改善或结构改善
- 不破坏现有 Reader / Author / Ops 主路径

