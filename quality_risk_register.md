# 质量风险登记册

## 风险分级说明
- 概率：Low / Medium / High
- 影响：Low / Medium / High / Critical
- 优先级参考：先看高影响，再看高概率

| 风险 ID | 风险 | 概率 | 影响 | 触发信号 | 缓解措施 | 回滚点 | 责任域 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QR-01 | Ops 读权限漂移导致质量排查入口不可用 | Medium | High | `/v1/ops/alerts` 返回 `403` | 新质量接口统一经过权限测试；把 Ops 只读能力纳入回归 | 关闭新质量工作台入口 | Ops / API |
| QR-02 | runtime quality gate 假阳性，正常章节被误拦截 | High | Critical | `quality_guard_failed` 升高、用户 retry 上升 | 新 gate 先 shadow / observe；保留旧 gate 并做差异对比 | 配置切回 observe | Reader / Eval |
| QR-03 | groundedness 检查误报，导致大量内容进审核队列 | Medium | High | review backlog 激增、grounding_missing_support 激增 | 区分 critical 与 advisory evidence；先对高风险场景 enforce | 关闭 groundedness enforce | Eval / Ops |
| QR-04 | 队列投影与 canonical case 不一致 | Medium | High | `quality_review_cases` 与 `ops_review_items` 数量不对齐 | 投影异步前先做幂等 upsert；加一致性校验脚本 | 停止投影，仅保留 canonical case | Persistence / Ops |
| QR-05 | `analytics_events` 被质量事件挤压，语义污染 | Medium | Medium | 查询变慢、事件名暴涨、聚合不稳定 | 质量 canonical 走新表；analytics 只保留行为代理 | 停写质量代理事件 | Persistence / Analytics |
| QR-06 | 发布链新增质量 gate 后误阻断上线 | Medium | Critical | publish blocker 激增、release checklist 不稳定 | publish 场景新增 gate 必须有 observe 期 | 配置移除新增 publish gate | Review / Release |
| QR-07 | 学习闭环回流低质量噪声样本，污染训练集 | Medium | High | evaluator/reranker 指标恶化 | `QualityFeedbackItem` 分层，低置信样本不直接入训练 | 回退到旧 training signal export | Eval / Training |
| QR-08 | groundedness 证据采集缺失，形成“有分无证” | High | High | quality event 中 evidence refs 为空 | evidence pack 作为 gate 输入的必填组件 | groundedness 只做 advisory | Eval / Services |
| QR-09 | 工作区已脏，实施阶段误覆盖现有改动 | High | High | 与用户现有修改冲突 | 实施时严格增量编辑，不做清理式重构 | 停止实现，先与用户对齐冲突范围 | Repo Health |
| QR-10 | 统一领域模型过大，拉长交付周期 | Medium | Medium | PR 体积失控、跨模块改动过多 | 分 Phase 逐步落对象；先上最小字段集 | 回退到文档化计划，拆小任务 | Architecture |
| QR-11 | Dashboard 聚合查询过重，Ops 页面变慢 | Medium | Medium | Ops 首屏慢、聚合超时 | 先做离线/周期聚合或分页 | 切回旧分面板展示 | Web / Persistence |
| QR-12 | 用户反馈信号过弱，采纳率/有效结果仍不可证 | High | Medium | 只能看到 continue/pay/retry 代理 | 引入 `QualityFeedbackItem`，先从 retry 与 abandon 开始 | 保持代理指标，不作为强门禁依据 | Product / Analytics |

## 当前已观测基线风险

### QR-B1
- 名称：Ops alert read path currently fails permission baseline
- 证据：`tests/test_ops_alerting.py::test_ops_alert_endpoints_and_shell`
- 现象：`GET /v1/ops/alerts` 返回 `403`
- 影响：质量事故发生后，Ops 无法稳定读取告警入口

### QR-B2
- 名称：Runtime observability baseline lags behind active quality gate behavior
- 证据：`tests/test_observability_runtime.py::test_runtime_observability_endpoints_return_receipts_and_snapshot`
- 现象：预期 `ok`，实际 `quality_guard_failed`
- 影响：说明 runtime 质检已进主链，但验证基线没有同步

## 建议优先缓解顺序
1. QR-01
2. QR-02
3. QR-06
4. QR-08
5. QR-04
6. QR-07

## 结论
- 统一质量架构的最大风险不在“没有能力”，而在“现有能力已经上主链，但缺少统一语义与验证护栏”。
