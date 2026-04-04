你将接手一个已经具备 Alpha 叙事能力的 NarrativeOS 仓库。

你的任务不是围绕某个作品继续打磨，而是把它升级为：
- 通用 Narrative Runtime
- 多 World Pack 支持
- 作者工具后端
- 商业化必要骨架
- 评测、审核、metering 与可回滚发布流

请先阅读：
- README.md
- 00_EXEC_SUMMARY.md
- 01_CURRENT_ALPHA_STATUS.md
- 02_FROM_SINGLE_WORK_TO_PLATFORM_GAP.md
- 03_NORTH_STAR_PRD.md
- 15_TASKS_FOR_CODEX.md
- 17_REPO_MIGRATION_FILE_MAP.md
- specs/
- db/
- contracts/
- legacy/

工作原则：
1. 优先保留现有 Alpha 的可运行性。
2. 采用渐进式重构，不要一次性推翻所有模块。
3. runtime 与 world assets 必须强制解耦。
4. 每完成一个 Phase 都补测试，并更新 README。
5. 所有新增 API 都要给出示例 request/response。
6. 对商业化相关的 entitlement / metering / review 先做最小可运行骨架。

输出要求：
- 每个 phase 提交代码、测试、README 更新
- 说明架构决策与权衡
- 若某项依赖未满足，先写 TODO 与占位实现
