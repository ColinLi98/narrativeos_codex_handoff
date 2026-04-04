你现在的任务不是继续优化某一个剧本或 world pack，而是把 NarrativeOS 从“可运行的 Beta 内核”推进到“可持续供给、可跨 pack 稳定、可运营的 Beta product”。

请严格遵守以下原则：

1. 不要继续做 pack-specific prose tuning，除非任务明确要求。
2. 所有改动必须以 cross-pack benchmark 为验证标准，而不是只展示当前 Jade Court 变好。
3. 每个任务都必须：
   - 先输出 implementation plan
   - 只改相关目录
   - 补测试
   - 跑测试
   - 更新 docs/README
   - 输出验收结果
4. 优先顺序：
   - P0 内容能力商业可用化
   - P1 Author 供给工具
   - P2 Ops / commercialization skeleton
   - P3 learned layer 数据准备
5. 不允许：
   - 只改 `core/writer.py` 就宣称“整体质量提升”
   - 跳过 weakest packs 问题
   - 在没有 metrics 改善的情况下结束任务

当前任务边界：

- 仓库已经具备多 World Pack、Reader/Author/Ops、NarrativeEval、cross-pack benchmark、publish gate。
- 当前最大的商业化缺口是：
  1. cross-pack 质量不稳定
  2. 作者供给工具太薄
  3. 数据飞轮尚未建立
  4. 商业化闭环仍只有骨架

你的工作方式：

- 先读 AGENTS.md
- 再读当前 task brief
- 先 Ask / plan，再 Code
- 只处理当前单个 task brief
- 提交时必须包含：
  - 改动文件清单
  - 测试结果
  - 指标 delta
  - 风险与下一步

