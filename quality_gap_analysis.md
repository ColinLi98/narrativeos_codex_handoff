# 统一质量架构 Gap Analysis

## 执行摘要
- 仓库已经具备“多条局部质量链”，但还没有一条贯穿 Reader / Author / Publish / Ops / Learning 的统一质量主链。
- 当前最小增量路径不是重写 NarrativeEval，而是把已有 `eval + review + observability + ops + training_signal` 组合成统一领域对象、统一事件流、统一看板和统一回流机制。
- 现有系统已经在生产路径上拦截低质量章节，这说明质量系统不是旁路；但缺少更强的状态对象、审核桥接和 groundedness 证据，容易形成“拦截了但解释不清、追不全、回流不成体系”的问题。

## 现有能力盘点

### 产品质量已有能力

| 能力 | 现有实现 | 评价 |
| --- | --- | --- |
| 关键流程状态 | Reader / Author / Billing / Ops 各自有状态对象与 API 响应 | 存在，但未统一成产品质量 scorecard |
| 失败可见性 | `analytics_events`、runtime receipts、ops alerts、traceability timeline | 较强 |
| 运维工作流 | `ops_review_items`、Ops Review Hub、Alert Center、Governance cases | 较强 |
| 发布门禁 | publish checklist、release gate、cross-pack signoff | 较强 |
| 数据回流 | `training_signal.py`、review/preference/ranking samples | 中等 |

### 文本质量已有能力

| 能力 | 现有实现 | 评价 |
| --- | --- | --- |
| 规则校验 | `validators.py`、canon critics、rating ceiling、phase gates | 强 |
| 自动评分 | `scorers.py`、`EvaluationScores`、decision gating | 强 |
| 长线质量 contract | `content_quality_contracts.py`、window metrics、strategy bundles | 强 |
| cross-pack 诊断 | benchmark reporting、weakest pack breakdown、issue mix | 强 |
| 人工评审样本 | `review_sample/preference/ranking` | 中等 |

## 主要缺口

### A. 治理层缺口
- 没有统一 `QualityPolicy` / `QualityRule` / `ScenarioClassification` / `RiskTier` 配置。
- 风险等级当前分散在 `risk_rating`、`rating_ceiling`、governance severity、ops alert severity，语义不统一。
- 模型 / Prompt / Policy / Eval 版本没有统一挂到质量决策对象上。

### B. Runtime Guardrail 缺口
- Reader / Author 当前只有章节级 `quality_gate`，没有统一 `GuardrailDecision`。
- 没有场景分类、风险分级前置步骤。
- 没有 groundedness / evidence support 检查。
- 没有“是否进入人工审核”的结构化决策结果。
- 没有把 provider routing / budget / permission / publish capability overreach 合并成统一越权检查。

### C. 人工审核缺口
- `review_records` 和 `ops_review_items` 很强，但 runtime 文本质量案例没有 canonical `ReviewCase`。
- 告警、发布、治理、训练样本是多条队列，尚未形成质量问题的统一分诊视图。
- 修改记录和回流结果存在于多个系统中，没有一个统一对象串起来。

### D. 监控与审计缺口
- 运行时 receipt 已有，但质量事件没有单独 canonical 存储。
- 没有产品质量 scorecard。
- 没有文本质量 scorecard 的线上聚合视图。
- adoption 仍依赖 `continue/pay/retry` 的代理事件，没有标准化 `QualityFeedbackItem`。

### E. 离线评测缺口
- 有 benchmark、有 learned export，但没有统一三类评测集目录。
- 没有 `EvalRun` 级统一归档。
- 没有对抗输入测试集和失败样本导出标准流程。

## 最小改动 / 最大收益

| 优先级 | 改动 | 收益 | 原因 |
| --- | --- | --- | --- |
| 1 | 新增统一质量配置文件 | 高 | 最低侵入，先把治理语义统一 |
| 2 | 增补质量域对象与 schema | 高 | 统一 Reader/Author/Ops/Offline 语义 |
| 3 | 新增 `quality_events` + `quality_review_cases` | 高 | 把现有散落事件串成可查、可审计、可聚合的主线 |
| 4 | 包装现有 `evaluate_persisted_chapter` 为统一 guardrail decision | 高 | 最大化复用 বর্ত有 NarrativeEval |
| 5 | 在 Ops 现有页面扩一块统一质量工作台 | 高 | 不起新后台，交付速度快 |
| 6 | groundedness 证据包 | 中高 | 文本质量从“分数”升级到“可追溯” |

## 线上风险热点

### 高风险
- `SessionService.continue_story` / `api/app_factory.py` 的 runtime guard 已直接影响用户路径。
- `ReviewService.publish` 与 benchmark gate 已直接影响发布。
- `ops_permissions.py` 已经对 Ops 页面和 API 可见性生效，权限漂移会直接打断排查。

### 中风险
- `author_work.py` manual edit / generation 的 hard gate 可能带来作者流程阻塞。
- `ops_review_items` 是汇总投影，若新质量 case 同步逻辑不稳定，会造成队列错漏。
- `analytics_events` 若事件语义继续膨胀而不做质量命名空间，会污染聚合口径。

### 低到中风险
- learned dashboard / promotion 主要是运营证据，不直接拦主链，但会影响数据闭环判断。

## 今天可以立即产出的指标

### 产品质量
- Reader 继续流程成功率 / `payment_required` / `quality_guard_failed` / `restricted` 分布
- runtime provider error / budget blocked / fallback rate
- publish checklist blocker 数量
- ops alert 数量、严重度分布、SLA bucket
- review hub backlog / blocked / unassigned 数量

### 文本质量
- pass / rewrite / block rate
- Q03/Q04/Q05/Q09 出现率
- scene density / pacing / hook / overall score
- cross-pack pass rate
- weakest packs / top issue categories
- continuation correlation

## 需要补采的指标

### 产品质量
- “用户可见” 与 “用户采纳” 分层指标
- 质量拦截后的 retry 成功率
- 审核队列 case turn-around time
- 降级路径命中率
- groundedness 失败率

### 文本质量
- groundedness support score
- evidence missing / evidence conflict rate
- style consistency score
- scenario-level quality score
- evaluator 与规则分歧率的运行时明细

## 当前基线风险
- 工作区已脏，存在大量用户或历史未提交修改；后续实现必须避免误回滚。
- 抽样验证命令：
  - `./.venv/bin/pytest -q tests/test_eval_scorers.py tests/test_eval_validators.py tests/test_ops_review_hub.py tests/test_ops_alerting.py tests/test_observability_runtime.py tests/test_learned_data_ops.py`
- 结果：`20 passed, 2 failed`
- 失败 1：`tests/test_ops_alerting.py::test_ops_alert_endpoints_and_shell`
  - 现象：`GET /v1/ops/alerts` 返回 `403`
  - 风险：Ops 读权限策略已影响质量排查入口
- 失败 2：`tests/test_observability_runtime.py::test_runtime_observability_endpoints_return_receipts_and_snapshot`
  - 现象：预期 `status == "ok"`，实际为 `quality_guard_failed`
  - 风险：runtime 质检行为已变化，但观测测试基线未跟上

## 结论
- 仓库不缺“质量功能点”，缺的是“统一质量操作系统”。
- 应优先把分散的 `evaluation_report / review_record / analytics_event / ops_review_item / training signal` 统一到可配置、可回滚、可观测、可审计的一套对象模型上。
