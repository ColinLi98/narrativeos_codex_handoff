# 15. 给 Codex 的任务清单

按优先级执行，除非有明确技术阻塞，否则不要跳 phase。

## Phase 0：先读与盘点

1. 阅读 `README.md`、`00_EXEC_SUMMARY.md`、`01_CURRENT_ALPHA_STATUS.md`。
2. 阅读 `legacy/` 和当前仓库代码，列出：
   - runtime 代码
   - world-specific assets
   - 前端 reader 代码
   - 测试覆盖薄弱处
3. 输出 `docs/runtime_asset_inventory.md`。

**验收标准**：能清楚指出当前 repo 中哪些逻辑仍然绑定单一作品。

## Phase 1：world pack 通用化

1. 引入 `WorldPack` / `WorldVersion` / `WorldRegistry`。
2. 把当前示例世界迁移为标准 world pack。
3. session 必须绑定 `world_version_id`。
4. 补 `multi-world loading` 与 `world publish / rollback` 测试。

**验收标准**：至少 3 个 world packs 可在同一 runtime 中加载并运行。

## Phase 2：通用 schema 与 DB

1. 实现 `specs/` 中的 schema 校验。
2. 落地 `db/postgres_schema.sql` 的核心表。
3. 增加 world、session、chapter、review、meter、entitlement 的 repository 层。

**验收标准**：主数据可持久化，世界、会话、章节可追溯。

## Phase 3：Authoring 后端

1. 实现作者 draft CRUD。
2. 实现 `validate world pack` API。
3. 实现模拟批次 job。
4. 输出 simulation report。

**验收标准**：作者可以不改代码创建 draft、跑校验、跑模拟。

## Phase 4：Runtime 通用化

1. 将 chapter planner、karma engine、renderer 的输入改为 world pack 标准对象。
2. 删除 runtime 中所有 world-specific 常量与人物名耦合。
3. 建立 style pack 与 risk policy 的可插拔接口。

**验收标准**：runtime 不依赖某个示例世界字段命名。

## Phase 5：Reader 商业化骨架

1. 引入 entitlement / meter record。
2. 章节继续前进行 access check。
3. 实现 free credits + paid continue 的接口占位。
4. 记录 cost per chapter。

**验收标准**：同一世界中可存在试读章、付费章、订阅可读章。

## Phase 6：评测与审核

1. 实现基本 critic pipeline。
2. 实现 world review queue。
3. 实现 publish / rollback。
4. 加入 leak / early ending / route length regression tests。

**验收标准**：每个 world version 发布前都有 validation + simulation + review 记录。

## Phase 7：前端产品骨架

1. Reader 增加 library shelf、world detail、entitlement state。
2. Author 增加 draft list、validation report、simulation report 页面。
3. Ops 增加 review queue 与 world status 页面。

**验收标准**：前端至少能体现三种角色的最小操作路径。

## Phase 8：文档与交付

1. 更新 README 和架构图。
2. 给出本地启动方式。
3. 给出 demo 数据与测试方式。
4. 列出未完成项与下一阶段建议。
