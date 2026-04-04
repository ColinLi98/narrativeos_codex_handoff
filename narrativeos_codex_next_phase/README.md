# NarrativeOS × Codex 下一阶段交接包

本交接包的目标：

- 不再围绕某一个 world pack 做局部正文润色。
- 让 Codex 以 **kernel-first / capability-first / commercialization-aware** 的方式推进 NarrativeOS。
- 将工作拆成一组 **可执行、可验证、可回归** 的小任务，适配 Codex 的最佳工作方式。

建议阅读顺序：

1. `00_WHAT_CODEX_SHOULD_DO_NEXT.md`
2. `01_90_DAY_EXECUTION_PLAN.md`
3. `03_AGENTS.md`
4. `04_PHASE_0_TASKS.md`
5. `05_PHASE_1_TASKS.md`
6. `06_PHASE_2_TASKS.md`
7. `07_ACCEPTANCE_METRICS.md`
8. `02_CODEX_MASTER_PROMPT.md`

使用方式：

- 先把 `03_AGENTS.md` 放到仓库根目录作为持久上下文。
- 每次给 Codex 只发 **一个 task brief**，不要一次塞完整个路线图。
- 先用 Ask / plan，让它输出实施计划，再切到 Code。
- 每个任务都要求：
  - 只改相关目录
  - 补测试
  - 跑测试
  - 更新 README / docs
  - 给出验收结果与风险

