你现在接手一个名为 NarrativeOS 的 Python 仓库。请先完整阅读：

0. `docs/gpt_handoff_status_and_commercialization.md`（如果你想先快速理解“当前状态 + 商业化差距”，优先看这个）
1. README.md
2. TASKS_FOR_CODEX.md
3. docs/ 目录
4. specs/ 目录
5. examples/ 目录

然后按以下原则施工：

- 先跑测试，再改代码
- 每个阶段提交最小可验证改动
- 所有新增数据结构都要保持 JSON 可序列化
- 优先保护：因果一致性、角色稳定性、Promise Ledger、route 可解释性
- 逻辑层与文风层严格分离
- 搜索目标是“下一事件”，不是“下一段文字”
- 分支需要显式多样性控制，而不是高温采样
- 任何 hard constraint 违规的候选事件都必须被过滤
- 输出中保留 debug 解释，方便产品和创作者理解为什么选了这条路

请按 Phase 1 → Phase 6 顺序推进。每完成一个 phase：

1. 更新测试
2. 运行测试
3. 更新 README 中的“当前实现状态”
4. 输出剩余风险与下一步建议

优先完成内容：

- candidate provider 接口化
- critic loop
- session persistence
- replay
- creator controls

非优先项：

- UI 美化
- 复杂部署
- 支付集成
