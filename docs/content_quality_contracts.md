# 通用内容质量约束框架

`content_quality_contracts` 是 Lane A 的共享质量 contract 配置，用来把 `Q03 / Q04 / Q05 / Q09` 从 benchmark 报表中的诊断标签升级成可执行的全链路硬约束。

## 配置源

- 配置文件：`configs/content_quality_contracts.json`
- 当前启用 band：`100`
- 预留 band：`250 / 500 / 1000`
- 生成硬约束：`generation_hard_constraints`

`100` band 当前默认阈值：

- `repetition_score_max = 0.20`
- `exposition_ratio_max = 0.52`
- `concrete_detail_density_min = 0.04`
- `dialogue_plus_action_ratio_min = 0.42`
- `late_window_hook_quality_min = 0.85`
- `q09_pre_end_max = 0.08`

窗口规则：

- `early (1-10)`：`Q03/Q04` 合计 breach share 不得高于 `0.45`
- `mid (30-60)`：`repetition` / `exposition` breach rate 各不得高于 `0.30`
- `late (80-100)`：`Q09` breach rate 不得高于 `0.08`，且不得出现 premature terminal

## 生成硬约束

`generation_hard_constraints` 定义跨类型文章共享的不可破坏规则。它不依赖 LLM 供应商训练结果，而是在 NarrativeOS 生成后、本地持久化前执行。

Universal rules 不能被类型 profile 关闭：

- `schema_complete`
- `broken_slot`
- `engineering_leak`
- `meta_narration_leak`
- `grounding_failed`
- `premature_terminal`
- `stock_refrain_budget`
- `choice_text_budget`

类型 profile 只允许调整阈值，例如 mystery 可以更严格地限制 stock refrain；length profile 会在 30/50 章路线收紧重复与 choice 预算。

执行策略：

- prompt/spec 会携带 compact hard constraint contract。
- 生成后先做一次 repair/control pass。
- 修复后执行确定性 hard constraint validation。
- 仍失败则 `quality_gate.enforced_decision = block`，Reader step 不持久化。
- 质量事件写入 `payload.hard_constraint_result`，用于 Ops / benchmark 统计。

## 资产层 contract

对 `benchmark_enabled && total_chapter_target >= 100` 的 published pack，以下字段必须存在：

- `scene_blueprint.quality_contract`
  - `variation_axes`
  - `detail_anchor_types`
  - `dialogue_pressure`
  - `continuation_obligation`
- `chapter_task.quality_contract`
  - `delayed_payoff_window`
  - `continuation_pressure_required`
  - `max_exposition_ratio`
  - `min_dialogue_action_ratio`
  - `min_detail_density`
- 顶层质量资产：
  - `voice_profiles`
  - `sensory_grounding_policies`
  - `dialogue_realism_policy`
  - `scene_realization_contracts`

低于 `100` 章的 pack 继续走兼容路径，不强制要求上述 schema。

## 章节级 gate

共享入口仍然是 `evaluate_persisted_chapter -> build_chapter_quality_gate`，但现在会额外接收：

- `chapter_index`
- `target_chapters`
- `story_phase`
- `scene_quality_contract`
- `chapter_task_quality_contract`
- `rolling_quality_window`
- `enforcement_scope`

新增 contract checks：

- `repetition_score_cap`
- `exposition_ratio_cap`
- `detail_density_floor`
- `dialogue_action_floor`
- `continuation_pressure_floor`
- `premature_terminal_forbidden`
- `rolling_window_repeat_breach`
- `rolling_window_exposition_breach`
- `late_window_q09_breach`

返回 payload 新增：

- `quality_gate.contract_checks`
- `quality_gate.contract_thresholds`
- `quality_gate.primary_issue_group`
- `quality_gate.primary_asset_target`
- `quality_gate.window_breach_kind`
- `quality_gate.blocking_dimension`
- `quality_gate.enforcement_scope`
- `quality_gate.quality_contract_window`

## 全链路接入

当前接入面：

- `AuthorWorkService.generate_chapters`
- `AuthorWorkService.edit_chapter`
- `AuthorWorkService._chapter_reports`
- `SessionService.continue_story`
- legacy session API step

成功写入后，`NarrativeState.metadata.quality_contract_window` 会持久化最近 `5` 章的 contract 观测，用于 rolling breach 升级。

失败时会自动生成 `repair_loop_context`，至少包含：

- `issue_code`
- `asset_type`
- `asset_label`
- `target_label`
- `validation_panel`
- `targeted_chapter_indices`
- `window_breach_kind`

## Repair Loop

在 `Author draft detail / work detail / simulate` 中，系统现在会额外输出 `content_quality_repair_workbench`。

它基于当前 `content_quality_contract_window_metrics` 生成窗口级 repair campaign：

- `early 1-10`
- `mid 30-60`
- `late 80-100`

每个 campaign 至少包含：

- `window_label / window_range`
- `issue_code / issue_label`
- `breach_kind`
- `strategy_bundle_id / strategy_bundle`
- `targeted_chapter_indices`
- `baseline_issue_count / baseline_worst_decision`
- `primary_asset_type / primary_asset_target`
- `validation_panel`
- `suggested_actions`
- `suggested_field_edits`
- `rerun_scope`

默认 campaign 选择顺序固定为：

- 先 `late > mid > early`
- 再 `Q09 > Q04 > Q03`
- 再比较 `failed chapter count / worst decision / average score`

当窗口里 `Q03 / Q04` 同时存在时，repair loop 默认会优先落到组合策略包：

- `q03_q04_scene_dialogue_cadence_task_coupling`

它的目标不是只改一个资产，而是把：

- `scene_blueprint`
- `scene_realization_contracts`
- `emotion_action_policies`
- `voice_profiles`
- `response_cadence_profiles`
- `chapter_task coupling`

收成一套统一执行/验证路径。

strategy bundle 现在不再只是推荐标签，而会额外返回 execution protocol：

- `bundle_step_planning`
- `step_level_apply_order`
- `rerun_attribution`
- `stop_condition`

这让 repair loop 可以继续向真正的 agent 执行协议推进，而不是停在“该改什么”的建议层。

现在作者端已经能直接执行 strategy bundle：

- `POST /v1/author/drafts/{world_version_id}/strategy-bundles/execute`

输入：

- `campaign_id?`
- `account_id?`

如果不传 `campaign_id`，默认执行当前 `content_quality_repair_workbench.default_campaign`。

执行时系统会：

1. 读取 `bundle_step_planning`
2. 按 `step_level_apply_order` 顺序应用字段建议
3. 生成 `step_level_apply_receipt`
4. 自动触发一次 full rerun
5. 基于 `rerun_attribution` 生成 `result_attribution`
6. 按 `stop_condition` 生成 `stop_decision`

执行完成后，draft detail / simulate payload 会额外带：

- `latest_strategy_bundle_execution`
- `strategy_bundle_execution_history`

`latest_strategy_bundle_execution` 至少包含：

- `campaign_id`
- `strategy_bundle_id / strategy_bundle_label`
- `bundle_step_planning`
- `step_level_apply_order`
- `step_level_apply_receipt`
- `applied_step_count / applied_edit_count`
- `rerun_attribution`
- `result_attribution`
- `stop_condition`
- `stop_decision`
- `repair_loop_outcome`

其中：

- `result_attribution` 会输出 `metric_receipt / improved_metrics / regressed_metrics / flat_metrics / overall_status / primary_signal / candidate_contributors`
- `stop_decision` 只会返回 `stop / continue / escalate` 三种决策，用来决定当前 bundle 是结束、再跑一轮，还是升级到更高层的策略

修稿后，`latest_repair_loop_outcome` 会按窗口输出 before/after：

- `baseline_window_issue_count / current_window_issue_count`
- `baseline_window_worst_decision / current_window_worst_decision`
- `resolved_window_chapters / remaining_window_chapters`
- `ready_for_validation`

## Benchmark / Release

每个 world 的 benchmark 输出新增：

- `content_quality_contract_coverage`
- `content_quality_contract_window_metrics`

其中窗口指标固定包含：

- `early_window_q03_q04_share`
- `mid_window_repeat_breach_rate`
- `mid_window_exposition_breach_rate`
- `late_window_q09_breach_rate`
- `contract_failed_chapters`

顶层新增 `content_quality_contract_gate`，作为 `phase_a_quality_gate` 之外的独立 blocker。

它会在以下任一情况阻断发布：

- 100 章 benchmark-enabled pack 缺少资产层 quality contract coverage
- early / mid / late 窗口 breach 超过 `content_quality_contracts.json` 阈值

Release checklist / workspace 已接入这个 blocker，Ops 可在 `publish_blockers.content_quality_contract_gate` 中查看失败明细。
