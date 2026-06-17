# 统一质量架构计划

## 目标
- 在不推倒重写的前提下，为 NarrativeOS 建立一套覆盖产品质量与文本生成质量的统一架构。
- 复用现有 `eval / benchmark / review / ops / observability / training_signal` 骨架。
- 把质量从“局部评分”升级为“治理配置 + 运行时状态机 + 审核队列 + 看板 + 学习闭环”。

## 总体设计原则
- 生产链路优先复用，新增层优先包裹而不是替换。
- 新表用于 canonical 质量对象；旧表继续做兼容层和投影层。
- 所有新 gate 默认支持 `disabled / observe / shadow / enforce` 级别控制。
- 所有质量决定都写入可审计事件并带版本信息。

## Layer A — Quality Governance

### 复用
- `configs/release_quality_gate.json`
- `configs/content_quality_contracts.json`
- `configs/content_quality_strategy_bundles.json`
- `risk_rating`、`rating_ceiling`、ops severity 现有语义

### 新增
- `configs/quality_governance.json`
- `configs/quality_rubrics.json`
- `configs/quality_scenarios.json`

### 统一对象
- `QualityPolicy`
- `QualityRule`
- `ScenarioClassification`
- `RiskTier`

### 治理职责
- 场景分类
- 风险分级 L1/L2/L3/L4
- veto rule
- 模型 / Prompt / Policy / Eval 版本
- 场景到规则集映射

## Layer B — Offline Evaluation

### 复用
- `src/narrativeos/benchmark/runner.py`
- `src/narrativeos/services/training_signal.py`
- `specs/review_sample.schema.json`
- `specs/preference_sample.schema.json`
- `specs/ranking_sample.schema.json`
- `specs/training_signal_bundle.schema.json`

### 新增
- `EvalSample`
- `EvalRun`
- 统一 quality eval runner
- 失败样本导出脚本

### 输出
- 产品流程测试集结果
- 文本质量测试集结果
- 对抗输入测试集结果
- 归档到 `artifacts/quality_eval/`

## Layer C — Runtime Guardrails

### 复用
- `SessionService.continue_story`
- `AuthoringService`
- `AuthorWork`
- `ReviewService.publish`
- `evaluate_persisted_chapter`
- provider routing / canon / critic / entitlement / governance block

### 新增
- 统一质量编排服务，例如 `QualityOrchestratorService`
- `GuardrailDecision`
- `GroundingCheck`
- `ContentQualityScore`
- `QualityIncident`

### 关键判断链
1. 场景分类
2. 风险分级
3. 检索 / 工具 / provider planning 检查
4. 主流程执行
5. 规则检查
6. evaluator 评分
7. groundedness 检查
8. 审核判定
9. 写 quality event

## Layer D — Human Review Queue

### 复用
- `review_records`
- `ops_review_items`
- `OpsReviewHubService`
- governance cases
- review sample capture UI

### 新增
- `ReviewCase`
- `quality_review_cases` canonical 表
- runtime/content case 到 `ops_review_items` 的同步投影器

### 目标
- runtime 低质量
- groundedness 失败
- 高风险文本
- 发布前质量异常
- 用户重复 retry / 差评代理

都可以进入同一套结构化审阅流。

## Layer E — Online Monitoring

### 复用
- `analytics_events`
- `ObservabilityService`
- `OpsAlertingService`
- `OpsTraceabilityService`
- `aggregate_eval_metrics`
- Ops 前端多个质量面板

### 新增
- 产品质量 scorecard 聚合
- 文本质量 scorecard 聚合
- 统一质量事件看板
- guardrail 拦截趋势
- adoption / retry / churn 代理趋势

### 统一对象
- `QualityScorecard`
- `QualityFeedbackItem`

## Layer F — Continuous Learning

### 复用
- `TrainingSignalService`
- review / preference / ranking sample 流
- learned dashboard / data ops / promotion

### 新增
- runtime low-quality 样本导出
- human edit 与 guard failure 统一回流
- weekly eval dataset refresh job
- rubric refresh cadence

## 统一领域模型

### 新增 dataclass / schema
- `QualityPolicy`
- `QualityRule`
- `ScenarioClassification`
- `RiskTier`
- `EvalSample`
- `EvalRun`
- `QualityScorecard`
- `ContentQualityScore`
- `ReviewCase`
- `GuardrailDecision`
- `GroundingCheck`
- `QualityIncident`
- `QualityFeedbackItem`

### 设计要求
- 可序列化
- 可落库
- 可导出
- 可供 dashboard 消费
- 保留版本字段和 evidence refs

## 存储设计

### 继续复用
- `analytics_events`
  - 用户行为代理
  - retry / continue / paywall / adoption 统计
- `review_records`
  - 审计历史
  - legacy review / governance / async retry
- `ops_review_items`
  - 队列投影

### 建议新增 canonical 表
- `quality_events`
- `quality_review_cases`
- `quality_feedback_items`
- `quality_eval_runs`

### 原则
- 旧表不迁移掉
- 新表追加式
- 旧 UI 先接聚合接口，不要求一次性迁移历史数据

## Ops 工作台扩展

### 直接复用现有页面
- `src/narrativeos/web/index.html`
- `src/narrativeos/web/ops_refresh.js`
- `src/narrativeos/web/ops_render_sections.js`

### 新增统一质量工作台内容
- 最近质量事件
- 审核队列
- 场景分数
- guardrail 拦截统计
- 产品质量 scorecard
- 文本质量 scorecard
- retry / continue / pay proxy 趋势

## 推进顺序

### Phase 1
- 配置治理层
- 统一领域模型
- runtime 统一 `GuardrailDecision`
- quality event 写入

### Phase 2
- review case canonical 层
- Ops 质量工作台
- unified eval runner

### Phase 3
- quality feedback item
- weekly dataset refresh
- 降级 / 告警 / 自动回流

## 关键复用决策
- 不推倒 `EvaluationReport`，把它作为文本质量内核输入之一。
- 不新起第二套 Ops 系统，`ops_review_items` 继续作为统一队列 UI 投影。
- 不把 `analytics_events` 替换掉，而是把它限定为行为代理层。
- 不把 groundedness 做成 prompt-only evaluator，必须绑定 evidence pack。

## 交付边界
- 本阶段只输出分析与设计，不进入生产实现。
- 下一阶段实现时，以“新增对象 + 包装现有链路 + 扩展现有 Ops 面板”为主，不做大规模重构。
