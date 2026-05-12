# 统一离线评测集计划

## 目标
- 在现有 benchmark 与 training signal 之上，建立统一的离线评测资产结构。
- 同时覆盖产品流程、文本质量、对抗输入三类评测。
- 支持样本定义、自动跑批、失败样本导出、结果归档和每周更新。

## 建议目录布局

### 静态样本
- `tests/fixtures/quality_eval/product_flows/`
- `tests/fixtures/quality_eval/content_quality/`
- `tests/fixtures/quality_eval/adversarial/`

### 运行产物
- `artifacts/quality_eval/runs/`
- `artifacts/quality_eval/failures/`
- `artifacts/quality_eval/exports/`

### 原因
- `tests/fixtures` 已是仓内可版本化测试资产位置。
- `artifacts` 已用于 benchmark、training、runtime 输出，适合存放 eval run 结果。

## 三类评测集

### 1. 产品流程测试集

#### 覆盖目标
- Reader create session / continue
- payment required / restriction / retry
- Author draft / simulate / save / manual edit
- publish checklist / release gate / review queue
- Ops alert / trace / review item navigation

#### 样本建议字段
- `sample_id`
- `scenario_id`
- `surface`
- `request_payload`
- `expected_status`
- `expected_step_states`
- `expected_guardrail_outcome`
- `expected_user_visible_state`
- `expected_audit_events`

### 2. 文本质量测试集

#### 覆盖目标
- 正常高质量章节
- Q03/Q04/Q05/Q09 典型失败
- groundedness 缺证据
- style drift
- task mismatch

#### 样本建议字段
- `sample_id`
- `world_id`
- `world_version_id`
- `chapter_input_ref`
- `reference_text`
- `expected_issue_codes`
- `expected_dimension_scores`
- `expected_veto`
- `expected_grounding_refs`

### 3. 对抗 / 恶意输入测试集

#### 覆盖目标
- meta / engineering leak 诱导
- 越权 prompt / capability overreach
- unsupported tool / provider route overreach
- high-risk content bypass
- false evidence / contradictory evidence

#### 样本建议字段
- `sample_id`
- `attack_class`
- `surface`
- `input_payload`
- `expected_block_or_review`
- `expected_reason_codes`
- `expected_risk_tier`

## 现有 schema 复用策略

### 直接复用
- `specs/review_sample.schema.json`
- `specs/preference_sample.schema.json`
- `specs/ranking_sample.schema.json`
- `specs/training_signal_bundle.schema.json`

### 用法
- 人工 review / preference / ranking 不另起 schema。
- offline eval runner 失败样本导出时，优先产出可直接喂给 `training_signal` 的格式。

## 新增 schema 建议

### `EvalSample`
- 统一三类评测的基础壳
- 按 `sample_type=product_flow|content_quality|adversarial` 分支

### `EvalRun`
- `run_id`
- `suite_id`
- `sample_count`
- `passed_count`
- `failed_count`
- `generated_at`
- `config_versions`
- `output_paths`

## 跑批脚本建议

### 新增脚本
- `scripts/run_quality_eval.py`
- `scripts/export_quality_eval_failures.py`
- `scripts/export_quality_dashboard_snapshot.py`

### runner 行为
- 输入 suite 配置、过滤器、输出目录
- 支持只跑一个 surface 或一个 world
- 每次跑完生成：
  - `summary.json`
  - `summary.md`
  - `failed_samples.json`
  - `metrics.json`

## 失败样本导出规范

### 内容
- `sample_id`
- `sample_type`
- `world_id`
- `surface`
- `actual_status`
- `expected_status`
- `actual_reason_codes`
- `expected_reason_codes`
- `guardrail_decision_ref`
- `quality_event_ref`
- `evidence_refs`

### 导出位置
- `artifacts/quality_eval/failures/<run_id>/`

## 归档规范

### 每次 `EvalRun`
- `artifacts/quality_eval/runs/<run_id>/summary.json`
- `artifacts/quality_eval/runs/<run_id>/summary.md`
- `artifacts/quality_eval/runs/<run_id>/metrics.json`
- `artifacts/quality_eval/runs/<run_id>/failures.json`

### 周期性汇总
- `artifacts/quality_eval/exports/latest.json`
- `artifacts/quality_eval/exports/latest.md`

## 每周更新机制

### 样本来源
- `quality_events` 中 runtime low-quality 与 groundedness failure
- `quality_feedback_items` 中 retry / abandon / low adoption
- `review_sample` 中高价值人工评审
- `author_revision_logs` / issue fix pairs

### 周更流程
1. 收集上周失败样本候选
2. 去重与分类
3. 人工确认加入哪个 suite
4. 更新 `tests/fixtures/quality_eval/*`
5. 运行回归
6. 归档 `EvalRun`

## 当前立即可复用资产
- `tests/golden_routes/`
- `tests/benchmark_baseline.json`
- `tests/long_route_benchmark_baseline.json`
- `scripts/run_targeted_longform100_compare.py`
- `TrainingSignalService.export_bundle`

## 当前缺口
- 没有统一 `EvalRun`
- 没有产品流程测试样本 schema
- 没有对抗输入测试集目录
- 没有统一失败样本导出脚本

## 结论
- 最稳妥的做法是“复用 training signal schema + 新增统一 eval sample / run 壳 + 把 benchmark 和 runtime failures 汇总到同一归档协议”。
