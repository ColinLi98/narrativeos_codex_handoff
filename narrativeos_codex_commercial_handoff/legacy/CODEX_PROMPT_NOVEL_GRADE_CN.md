请对 NarrativeOS 进行一次“小说/漫剧级叙事重构”，目标不是继续堆功能，而是修复当前 4 个核心问题：
1. 每回合内容太少
2. 故事 10 回合内就结束
3. 输出泄漏工程化字段
4. 阅读体验像 demo，不像小说/漫剧

先阅读：
- NARRATIVEOS_NOVEL_GRADE_REFACTOR_PLAN_CN.md
- README.md
- TASKS_FOR_CODEX.md
- docs/
- specs/
- src/

请按以下顺序实现：

## Phase 1：防止故事过早结束
- 在 NarrativeState 中加入 story_phase / chapter_index / min_end_turn
- 为 ending 事件增加 gate：min_turn、required_scene_functions、required_closed_promises、required_tension_min
- 将 dramatic_tension_delta 从 turn-based 改为 phase-based
- 补测试：前 6 章不会过早触发结局

## Phase 2：将“一个回合 = 一个事件”改成“一个回合 = 一个场景”
- 新增 ChapterPlan / SceneBeat / SceneRenderSpec
- 实现 plan_next_scene() / simulate_scene_beats() / render_scene()
- 每次用户前进时，内部推进 3~5 个 beats，再输出 600~1200 字正文
- 补测试：输出 view model 中不再直接暴露 event summary 作为正文

## Phase 3：移除工程化泄漏
- 新增 presenter.py 和 sanitizer.py
- 默认只输出 Reader Mode 的 view model
- 禁止 event_id、route trace、snake_case facts、theme keys 泄漏到用户层
- 补测试：输出中不包含 `->`、`event_id`、`scene_function`、snake_case token

## Phase 4：把故事拉长到小说感
- 加 promise aging / payoff pressure
- 加 scene intent 层
- 扩充示例 world，使单路线至少可支撑 8~12 个章节
- 补测试：平均路线长度显著增加

## Phase 5：提升文学性
- 新增 renderer 风格：novel_light / novel_lush / manhua_drama
- 强化对白、动作线、场景细节
- 增加角色误解与延迟后果

实现要求：
- 不要大改现有 schema 到不可运行
- 以渐进式重构为主
- 每个 phase 完成后都补单元测试并更新 README
- 代码优先保证可运行、可测试、可解释
