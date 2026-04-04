# Runtime / Asset Inventory

## 当前 runtime 代码

- `src/narrativeos/core/`：Beta 内核统一入口，当前主要以 wrapper 方式接入现有实现。
- `src/narrativeos/pipeline.py`：章节规划、beat 模拟、Reader Mode 生成的现有主入口。
- `src/narrativeos/memory.py` / `karma.py` / `fate.py` / `relationship_graph.py`：人物因果、种子成熟、关系债、命运压力更新。
- `src/narrativeos/search.py` / `scoring.py` / `critics.py`：候选生成、评分、critic loop。
- `src/narrativeos/rendering.py` / `presenter.py` / `sanitizer.py`：章节正文与 Reader Mode 输出。

## 当前仍明显绑定单一作品的资产

- `examples/demo_world_bible.json`
- `examples/romance_world_bible.json`
- `examples/demo_initial_state.json`
- `examples/romance_initial_state.json`
- `examples/demo_event_atoms.json`
- `examples/demo_player_inputs.json`
- `examples/romance_player_inputs.json`

这些文件仍然直接承载：

- 具体角色名（余澄 / 林绾 / 荣老太君 / 徐师）
- 具体家门结构与春闱设定
- 单作品的关系债与命运命题
- 单作品的事件库和 scene progression

## 当前前端 Reader 代码

- `src/narrativeos/web/index.html`
- `src/narrativeos/web/app.js`
- `src/narrativeos/web/styles.css`

当前前端已经有 Library / Session Shelf / Storybook / Backstage 概念，但仍然主要服务 Reader 单端，不具备正式 Author / Ops 主路径。

## 测试覆盖相对薄弱的部分

- 多 World Pack 注册、版本切换、发布/回滚
- Postgres-first persistence
- Authoring draft / validate / simulate / submit
- Entitlement / meter / access tier
- Review queue / publish / rollback
- 三端前端最小路径

## 已经可以直接抽到平台层的部分

- Karma Character Engine 与 NarrativeState
- Scene planner / search / critics / renderer 的通用运行逻辑
- Reader Mode 输出契约
- Session replay 机制

## 仍然需要从 runtime 中抽离的单作品耦合

- 内置示例世界通过 `examples/` 直接加载，而不是统一走 World Pack Registry
- 当前 `/app` 仍然默认围绕 demo/romance 示例世界组织内容
- 现有 world/session API 默认假设“世界 = 一组本地 JSON”，还没有强制落在 `world_version_id`
- 前端读者视图仍然默认把世界当作单机 demo 体验，而不是多 world shelf / entitlement-aware 产品入口
