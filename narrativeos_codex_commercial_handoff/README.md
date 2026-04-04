# NarrativeOS 商业化与通用化 Codex Handoff Kit

这是一套面向 **Codex/CodeX 执行** 的交接包，目标不是继续围绕单一作品打补丁，而是把现有 Alpha 叙事系统升级为：

- **多世界可复用的通用叙事引擎**
- **可由作者持续供给内容的创作平台**
- **可上线验证付费与留存的商业产品骨架**

## 这套交接包解决什么问题

现状不是“不会生成下一章”，而是：

1. 现有实现仍然明显偏向单一作品和单一世界。
2. 核心引擎、内容资产、作者工具、商业产品骨架还没有完全解耦。
3. 当前 Alpha 已有 Karma Character Engine v0.1，但还没有形成 **可扩张、可审核、可计费、可评测** 的平台标准。

## 先读哪些文件

建议 Codex 按以下顺序阅读：

1. `00_EXEC_SUMMARY.md`
2. `01_CURRENT_ALPHA_STATUS.md`
3. `02_FROM_SINGLE_WORK_TO_PLATFORM_GAP.md`
4. `03_NORTH_STAR_PRD.md`
5. `15_TASKS_FOR_CODEX.md`
6. `16_CODEX_EXECUTION_PROMPT.md`
7. `17_REPO_MIGRATION_FILE_MAP.md`
8. `specs/`、`db/`、`contracts/`
9. `legacy/`

## 包内目录说明

- `00_*` 到 `17_*`：产品、架构、运营、商业化、迁移、执行说明
- `specs/`：通用 schema 与 OpenAPI 合约
- `db/`：建议数据库 schema
- `contracts/`：Python / TypeScript 接口草案
- `configs/`：模型策略与评分权重示例
- `prompts/`：规划、渲染、评测、审核提示模板
- `examples/`：多题材 world pack 示例
- `legacy/`：此前的重构方案、角色因果规范、当前 Alpha 状态

## 强约束

1. **不要把“单一作品世界观”硬编码到核心 runtime。**
2. **世界观资产与引擎运行时必须彻底分离。**
3. **商业化能力不是最后再接，而是从 schema、权限、审核、metering 开始预埋。**
4. **默认以 Web-first、Reader Mode-first、multi-world-first 为设计原则。**
5. **任何“无限量”承诺都要改成 metered credits + fair-use。**

## 这套材料的预期产出

Codex 完成后，仓库应该具备：

- 多 world pack 加载与版本管理
- 通用 Narrative Runtime
- 作者工具后端接口
- 评测 / 审核 / 计费基础设施
- 面向 Reader / Author / Ops 三类角色的产品骨架
- 由单作品 Alpha 升级为可商业验证的 Beta 内核
