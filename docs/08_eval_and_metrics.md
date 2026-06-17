# 评测框架与指标

## 核心体验指标

### 1. 因果自洽率
用户回看时认为“这条线讲得通”的比例。

### 2. 角色保真度
用户认为角色“没崩”的比例。

### 3. 分支独特度
兄弟分支在事件层面的平均差异，而不是文案措辞差异。

### 4. 后果延迟价值
一个选择在几幕之后仍然能带来影响。

### 5. 重玩率
玩家是否愿意回到上一步尝试其他命运。

## 自动指标

- unresolved promise count
- scene function repetition rate
- forbidden fact violation rate
- knowledge leakage rate
- branch similarity score
- route entropy
- pass_rate
- rewrite_rate
- block_rate
- top_issue_categories
- online_continuation_correlation
- continuation_signal_summary
- quality_signal_correlations
- continuation_world_details
- continuation_version_details
- continuation_sample_accumulation

其中：

- `online_continuation_correlation`
  - 当前定义为 `overall_score` 与“该章节之后是否真的继续读到下一章”的章节级相关系数
- `continuation_signal_summary`
  - 输出 `sample_count / positive_count / negative_count / censored_count / continuation_rate`
  - 让 Ops 看清这次相关性到底建立在多少真实 reader continuation 样本上
- `quality_signal_correlations`
  - 对 `overall_score / readability / scene_density / pacing / hook_quality / issue_count / Q03/Q04/Q05/Q09 presence` 等指标给出章节级相关系数
  - 目标不是替代 cross-pack benchmark，而是回答“哪些质量指标更接近真实继续读行为”
- `continuation_world_details`
  - 以 `world_id` 为粒度输出 `sample_count / continuation_rate / correlation / sample_gap / recommended_action`
  - 用于回答“哪个题材的真实继续读样本还不够”
- `continuation_version_details`
  - 以 `world_version_id` 为粒度输出同样的 continuation correlation 明细
  - 让 Ops 能直接下钻到具体版本，而不是只看全局平均
- `continuation_sample_accumulation`
  - 汇总 `target_sample_count_per_world / target_sample_count_per_version / target_negative_samples`
  - 给出 `prioritized_worlds / prioritized_versions`
  - 目标是把“继续读样本不足”变成可执行的样本积累 backlog

## Q03 / Q04 / Q05 / Q09 定向修复框架

当前默认生成链已接入一个通用 remediation pass，目标不是润色某个 pack，而是统一压以下四类问题：

- `Q03 repetition`
  - 不再只看词项重复，而是联合判断：
    - 段落语义近似
    - event / beat coverage gap
    - 结构性回环证据
  - 对重复段落做 variation pass，优先改写重复 beat 的段落结构
- `Q04 over-explanation`
  - 当 exposition ratio 过高或正文过短时，补一段更 scene-facing 的 dialogue pressure
- `Q05 lack of scene detail`
  - 当 concrete detail density 过低时，补具体的 sensory grounding 段落
- `Q09 pacing failure / premature ending`
  - 加强结尾 hook
  - 在 `min_end_turn` 之前，对 terminal scene function 施加更强 penalty

它的目标不是直接替代更深的 planner/writer 重构，而是先提供一个可复用、可 benchmark 的 kernel-level 修复框架。

## Long-route Q03 / Grounding hardening

50 章 Reader 路线证明当前内核可以长跑，但也暴露了两个会随章节数放大的问题：固定 refrain / 地点锚点重复，以及 grounding failed 仍可能被质量事件记录为 passed。

当前合同：

- Reader 生成在持久化前执行 long-route quality controls：
  - 清理空槽位，例如 `被压回去的 、`
  - 对高频 refrain、位置锚点、默认 choice 文案施加 session 级预算
  - 将 choice text history 写入 state metadata，不改公开 API 或 DB schema
- grounding 是质量 gate 的输入：
  - `grounding_status=failed` 会把 Reader gate 改为 `block`
  - failed grounding 不允许产生 `quality_event.status=passed`
  - `weak` grounding 保留为可观测信号，不阻断正常 Reader 长文
- 中文 grounding tokenizer 使用 3/4 字片段匹配，避免整句被当成单个 token 导致所有长文误判为 unsupported。
- 只读诊断 CLI：
  - `scripts/diagnose_long_route_quality.py --database-url <url> --session-id <id> --markdown-out <path>`
  - 输出 broken slot、stock refrain、重复 choice、grounding status 和 repetition bundle。

目标指标：

- 50 章 Reader-like route 的 broken slot 命中为 `0`
- 单一默认 choice 不再覆盖所有章节
- stock refrain 在 session 级别被限制在预算内
- grounding failed 章节不持久化为 passed quality event

## Cross-genre hard constraint stack

Lane A 现在把 Reader 生成质量分成两层：

- **Hard constraints**：确定性、本地校验、不可被类型 profile 关闭。
  - `schema_complete`：章节标题、正文、choice schema 必须完整。
  - `broken_slot`：空槽位和模板碎片不得进入持久化正文。
  - `engineering_leak` / `meta_narration_leak`：工程字段、路线标记、章节策划口吻不得出现在 Reader 可见文本。
  - `grounding_failed`：failed grounding 必须 block，不能写成 passed quality event。
  - `premature_terminal`：未到路线终局窗口的结局触发必须 block。
  - `stock_refrain_budget` / `choice_text_budget`：长路线高频 refrain 和重复 choice 受 deterministic budget 约束。
- **Genre / length profiles**：只允许调整阈值，不能禁用 universal hard rules。
  - 类型 profile 覆盖 mystery / romance / fantasy / realist / light_novel。
  - 30 / 50 章 length profile 收紧长路线 repetition 和 choice 预算。

执行策略是 `repair_once_then_fail_closed`：

- 生成后先进入一次通用 repair/control pass。
- 修复后再跑 hard constraints。
- 仍失败则返回 `quality_guard_failed`，不保存 step/chapter。
- `quality_event.payload.hard_constraint_result` 会记录 profile、repair attempts、repair success、failed rule ids。

Benchmark markdown 会输出 `Generation Hard Constraint Summary`：

- hard fail count / rate
- repair attempts / repair success rate
- violation mix by rule id

这套约束借鉴的是 LLM 推理系统常用的 schema validation、rejection/repair loop、eval gate 和 policy taxonomy；不假设模型供应商训练已经覆盖 NarrativeOS 的世界观、长线连载、Reader choice 或商业化质量要求。

## 200 章诊断合同

当前 `content_quality_contracts` 已把 `200` 章建模为 diagnostic profile，而不是 merge/publish blocker。

- `band = 200`
- `diagnostic_enabled = true`
- `gate_enforced = false`
- 重点观察窗口：
  - `early = 1-20`
  - `mid = 60-140`
  - `late = 160-200`

该档位会输出：

- `early_window_q03_q04_share`
- `mid_window_repeat_breach_rate`
- `mid_window_exposition_breach_rate`
- `mid_window_detail_breach_rate`
- `late_window_q09_breach_rate`
- `late_window_detail_breach_rate`
- `contract_issue_surface_counts / rates`

目标是把 `200` 章作为通用诊断 rail，帮助我们看清强交互中后段的重复、过解释、细节发虚和节奏塌陷，而不是直接作为发布门。

这也意味着：

- `Q05` 不再只在 contract summary 里可见，而要同步进入 benchmark issue surface
- weakest-pack 诊断会额外输出 `window_breach_attribution`
  - 例如 `mid:Q05` 或 `late:Q09`
  - 并直接映射到 `writer / planner / asset / policy`

## Cross-pack Benchmark 报表

当前 benchmark 不再只输出 `pass_rate`，而会为每个 pack 提供可诊断报表。

### 顶层字段

- `worlds`
- `cross_pack_pass_rate`
- `benchmark_mode`
- `chapter_budget`
- `strongest_packs`
- `weakest_packs`
- `top_failing_packs`
- `weakest_pack_diagnostics`
- `strategy_validation_summary`
- `strategy_bundle_batch_validation`（仅当显式开启 batch validate）
- `delta_summary`
- `long_route_summary`（仅 long-route 模式）

### 每个 `worlds[*]` 至少包含

- `pass_rate / rewrite_rate / block_rate`
- `completion_ratio / stop_reason`
- `issue_mix`
- `long_route_quality`
- `mid_arc_drop`
- `dialogue_distinctness`
- `avg_repetition_score / avg_exposition_ratio / avg_hook_quality`
- `mid_arc_pass_rate / late_arc_pass_rate`
- `diagnostic_score / diagnostic_rank`
- `top_issue_categories`
- `dimension_scores`
- `issue_summary`

其中：

- `issue_mix`
  - 直接聚合 `chapter_evaluations[*].issues`
  - 至少包含 `issue_code / count / share / owning_module / fix_hint`
  - 用来回答 weakest packs 究竟是 `Q03 / Q04 / Q05 / Q09` 哪类问题在拖分
- `top_issue_categories`
  - 直接复用章节 `EvaluationReport` 聚合出的 issue category
  - 至少包含 `issue_code / count / owning_module / fix_hint`
- `long_route_quality`
  - 用章节 `overall_score` 平均值结合完成章数归一化
  - 不是只看“有没有 pass”，而是看长线能不能站住
- `completion_ratio / stop_reason`
  - 用来回答路线是跑满 budget、提前结局，还是在中途无合法路线
- `mid_arc_drop`
  - 用前段质量和中段质量的差值表示
  - 用来暴露中段掉速或掉质
- `avg_repetition_score / avg_exposition_ratio / avg_hook_quality`
  - 用来跟踪长路线里重复、解释句和钩子质量是否在中后段变坏
- `mid_arc_pass_rate / late_arc_pass_rate`
  - 不再只看总 pass rate，而是明确看中段和后段是否还站得住
- `dialogue_distinctness`
  - 当前阶段直接复用 `voice_separation_score` 的启发式值
  - 后续如需更细的对白分离 scorer，再单开任务
- `diagnostic_score / diagnostic_rank`
  - weakest / strongest 的 composite ranking 基础
  - 不再只按 `pass_rate` 排名
- `dimension_scores`
  - 当前稳定维度包括：
    - `character_fidelity`
    - `causal_continuity`
    - `choice_distinctness`
    - `prose_leak_rate`
    - `route_longevity`
    - `dialogue_ratio`
    - `scene_detail_density`
    - `voice_separation_score`
    - `emotion_action_specificity`
- `issue_summary`
  - `dominant_issue`
  - `weakest_dimensions`
  - `recommended_target`

### strongest / weakest / top failing

- `weakest_packs`
  - 直接面向诊断使用
  - 默认包含 `issue_mix / long_route_quality / mid_arc_drop / dialogue_distinctness / weakest_dimensions / recommended_target`
- `strongest_packs`
  - 用来和 weakest packs 对照，避免只汇报某一个 pack 变好
- `top_failing_packs`
  - 当前与 `weakest_packs` 保持同一份 payload，兼容现有消费方

### `weakest_pack_diagnostics`

这是 `weakest_packs` 的继续下钻层，目标是不再停留在“哪个 pack 最弱”，而是回答“最弱在哪里、先改什么”。

每个 weakest diagnostic 至少包含：

- `world_id / diagnostic_rank / diagnostic_score`
- `issue_category_distribution`
- `worst_chapters`
- `attribution_map`
  - `modules`
  - `assets`
  - `policies`
- `asset_snapshot`
- `next_fix_candidates`

其中：

- `worst_chapters`
  - 默认按 `decision -> overall_score -> issue_count` 排序
  - 至少提供 `chapter_id / decision / overall_score / issue_codes / signal_snapshot`
- `attribution_map`
  - 用 issue mix + weakest dimensions 推断最该看的 `module / asset / policy`
  - 当前是 heuristic diagnostics，不是自动修复器
- `next_fix_candidates`
  - 给出可执行的修复起点
  - 结构上明确 `module / asset / policy / suggested_action`

### `delta_summary` 增强字段

- `cross_pack_pass_rate_delta`
- `world_deltas`
- `regressions`
- `ranking_changes`
  - `current_strongest / baseline_strongest`
  - `current_weakest / baseline_weakest`
  - `entered_* / exited_*`
  - `rank_deltas`

这样 Ops 不再只能看到 weakest pack 是谁，而能进一步看到：

1. 主问题是什么
2. 最弱能力维度是什么
3. 是短线问题、长线问题，还是 mid-arc 掉速
4. strongest / weakest 榜单相对上次怎么变化
5. 优先应该改哪一层

### `strategy_bundle_batch_validation`

当 benchmark 显式开启 `validate_strategy_bundle` 时，顶层会额外输出这一层执行证据。

它的目标不是回答“推荐了哪个 bundle”，而是回答“这个 bundle 在 weakest packs 上真实跑起来以后到底有没有用”。

至少包含：

- `strategy_bundle_id / strategy_bundle_label`
- `batch_execution_mode`
- `weakest_source_world_ids`
- `compatible_world_ids`
- `skipped_worlds`
- `validated_world_count`
- `validated_worlds`
- `aggregated_step_receipts`
- `aggregated_result_attribution`
- `effectiveness_rate`
- `decision`
- `decision_reason`
- `adaptation_targets`

其中：

- `validated_worlds[*]`
  - 至少提供 `world_id / campaign_id / window_label / issue_codes`
  - 以及 `step_level_apply_receipt / step_receipt_summary / result_attribution / stop_decision`
- `effectiveness_rate`
  - 只按实际被验证的 compatible weakest packs 计算
  - 当前定义为 `overall_status == improved` 或 `ready_for_validation == true` 的 pack 占比
- `decision`
  - 当前只允许 `continue / adapt / retire`
  - 用来回答该 bundle 是继续沿用、需要调整，还是应该淘汰
- `adaptation_targets`
  - 当前从 regression 最集中的 metrics 与 noop/skipped 最集中的 asset steps 两类信号里生成

这一层现在还会被三个消费面直接使用：

- benchmark markdown
  - 在 `Weakest Pack Polish Program` 之后追加 `Strategy Bundle Batch Validation`
- release evidence / release workspace
  - 进入 `release_evidence_bundle.strategy_bundle_batch_validation`
  - 同时生成 `...strategy_bundle_batch_validation_summary`
- 进入 `...strategy_bundle_batch_validation_history / ...trend / ...history_summary`
- Ops 现有跨包区块
  - 直接显示 bundle 是否跑过、validated worlds、有 效率、`continue / adapt / retire` 结论，以及 adaptation targets

注意：

- 该字段当前是 `evidence-only`
- 它不会改变 publish blockers
- 也不会改变 `release_evidence_bundle.combined_signoff.ready`

### `strategy_bundle_batch_validation_history`

当同一个 bundle 被多次显式 batch validate 运行后，系统会保存最近几轮的历史。

顶层固定包含：

- `available`
- `strategy_bundle_id`
- `entry_count`
- `entries`

每条 `entries[*]` 至少包含：

- `generated_at`
- `benchmark_mode`
- `validated_world_count`
- `effectiveness_rate`
- `decision`
- `decision_reason`
- `compatible_world_ids`
- `top_adaptation_targets`

### `strategy_bundle_batch_validation_trend`

这是对最近几轮 batch validation history 的规则化趋势判断。

固定包含：

- `recent_run_count`
- `latest_decision`
- `latest_effectiveness_rate`
- `previous_effectiveness_rate`
- `delta_effectiveness_rate`
- `trend_status`
- `trend_reason`
- `retire_recommended`

当前 `trend_status` 只允许：

- `insufficient_history`
- `improving`
- `flat`
- `deteriorating`
- `retire_watch`

Ops 现有跨包区块会直接显示这层趋势，用来回答：

1. 这个 bundle 最近几轮是在变好还是变差
2. 当前是不是已经进入 retire watch
3. 现在更适合继续沿用、调整，还是准备淘汰

### `long_route_summary`

当 benchmark 以 long-route 模式运行时，顶层会额外输出：

- `target_chapters`
- `avg_completion_ratio`
- `avg_mid_arc_drop`
- `avg_repetition_score`
- `avg_exposition_ratio`
- `packs_reaching_target`
- `premature_ending_packs`
- `stop_reason_counts`
- `q03_q09_calibration`

它的用途是回答：

1. 当前 pack 是否能撑到 30–50 章
2. 中段是否开始掉速
3. 重复和解释句是否在长线里持续升高
4. 失败主要是过早收束，还是根本无合法路线

### Targeted weakest-three compare

当前可通过 `scripts/run_targeted_longform100_compare.py` 对 weakest three packs 做 focused compare：

1. 跑 weakest-three baseline `longform_100`
2. 用真实 Reader 会话补 continuation 样本
3. rerun weakest-three `longform_100`
4. 输出 before / after / delta artifacts

在做 weakest-pack 的 `Q03` remediation 时，优先修改运行时真正消费的 top-level pack 资产：

- `voice_profiles`
- `response_cadence_profiles`
- `pressure_response_styles`
- `emotion_action_policies`
- `sensory_grounding_policies`
- `scene_realization_contracts`
- `scene_blueprints`

不要只改 `narrative_style_pack`。
当前 runtime 会先从上述 top-level 资产重建 style pack；如果这些字段仍是默认模板，benchmark 会继续回落到通用 opening / detail / beat realization，导致 `semantic_paragraph_similarity_score` 和 `event_coverage_gap_score` 一起升高。

当 weakest pack 的 `Q03` 主要来自 chapter 内对同一 continuation motif 的反复拉回时，优先检查三层：

- `runtime_event_atoms[*].metadata.continuation_blueprints`
  - 关键 base event 应优先走事件自带 continuation 分支，而不是完全依赖通用 continuation title/summary
- `simulate_scene_beats()`
  - `progression_target` 之后的 pivot / aftermath / echo 应使用独立 beat projection，而不是把同一个 event id 在同一章里重复记两次
- `coverage_context`
  - `selected_event_ids` 应按 event 去重
  - `scene_beats` 仍保留全部 beat，用于 `beat_coverage_gap_score`

这样才能把“重复 beat”与“重复 event”拆开，不让 `Q03` 因 chapter 结构性回声被误放大。

### Weakest-set rebaseline

当一轮 full `longform_100` confirmation 跑完以后，应立刻重排 weakest set，而不是继续追旧 weakest-three。

当前 closeout 后的 weakest set 已切换为：

- `synthetic_min_pack`
- `jade_court_romance`
- 相对观察包：`jade_court_exam`

进入下一轮 remediation 时，优先检查：

- 是否缺少 runtime continuation blueprints
- 是否仍大量回落到 generic continuation titles
- `scene_detail_density / dialogue_ratio / voice_separation_score` 是否同时偏弱

如果像 `synthetic_min_pack` 一样在 targeted compare 的补样阶段出现 `continue_status = no_legal_routes`，要把它当成 continuation supply 问题，而不只是 calibration coverage 问题。

### Long-route continuation kernel

当 `min_end_turn` 被拉高到 long-route 级别时，静态 candidate provider 现在会在事件池即将耗尽时补充一层 deterministic continuation candidates：

- 只在 long-route 语境启用，不影响标准 6 章 benchmark 基线
- continuation candidates 复用现有 pack actors / tags / contracts，但会生成新的 event ids，避免被 `visited_event_ids` 提前耗尽
- continuation candidates 会移除 terminal / ending metadata，并按 phase 注入新的非终局 scene functions、promise、seed 与 location 轮换
- 目标不是直接让 weakest packs “看起来更好”，而是先把 benchmark 从 `no_legal_routes` 主导，推进到真正能观察 mid-arc / late-arc 内容质量

### Markdown Summary

benchmark CLI 现在可通过 `--markdown-out` 额外生成 markdown summary，适合：

- 本地快速查看
- PR 附件
- Ops 复盘记录

summary 至少包含：

- `Overview`
- `Strongest Packs`
- `Long-Route Summary`（仅 long-route 模式）
- `Weakest Packs`
- `Weakest Pack Diagnostics`
- `Ranking and Metric Delta`

### Lane A / Phase 1 / Task 1.3 longform_100 quality recovery

2026-04-24 closeout:

- baseline artifacts: `artifacts/longform100_stability.json`, `artifacts/longform100_stability_repeat2.json`
- after artifacts:
  - `artifacts/longform100_q05_q03_after_run1.json`
  - `artifacts/longform100_q05_q03_after_run1.md`
  - `artifacts/longform100_q05_q03_after_run2.json`
  - `artifacts/longform100_q05_q03_after_run2.md`

Before recovery, all 6 packs reached 100 chapters, but Phase A stayed blocked by weakest-pack issue share:

- `jade_court_exam`: Q05 share 0.750
- `jade_court_romance`: Q05 share 0.778
- `synthetic_min_pack`: Q03 share 0.429, Q05 share 0.429, Q09 share 0.143

After recovery, both independent `longform_100` runs are Phase A green:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_gate.pass_rate`: 1.0
- packs reaching 100 chapters: 6/6
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`
- weakest-pack Q03/Q04/Q05/Q09 issue mix: empty in both runs
- strongest packs: `xianxia_forgotten_vow`, then `urban_mystery_lotus_lane`

Implementation notes:

- Q05 recovery is kernel-level: final detail repair now uses beat-linked coverage anchors, compact concrete object/sound/body detail, and post-trim length recovery.
- Q03 recovery is kernel-level: final repetition repair can replace repeated paragraphs with coverage bridges or lexical relief, and synthetic fallback dialogue/action now rotates by chapter seed.
- Q09 recovery is route-level: longform promise runway no longer stops opening continuation promises immediately at `min_end_turn` when a series target still has runway before the final 4%.
- Targeted synthetic pack edits are structured runtime assets: continuation blueprint variety, cadence variation, pressure response variation, and repeat-detail anchors.
- No Phase A thresholds or benchmark baselines were lowered.

Residual watch:

- `tide_archive_memory_debt` still carries non-weakest Q03/Q04 counts in the full run summaries, but it is not a Phase A blocker after Task 1.3.
- Next Lane A pass should decide whether to bring Tide Archive into the weakest-set polish queue or keep focus on Reader-facing evidence capture.

### Lane A / Phase 1 / 100-to-250 longform clean run

2026-04-24 follow-up closeout:

- 100-chapter current-code artifact:
  - `artifacts/longform100_no_redundancy_after_current.json`
  - `artifacts/longform100_no_redundancy_after_current.md`
- 250-chapter current-code artifact:
  - `artifacts/longform250_no_redundancy_after_current.json`
  - `artifacts/longform250_no_redundancy_after_current.md`
- 250 baseline defect artifact:
  - `artifacts/longform250_initial_diag.json`

Before recovery, `longform_250` already reached 250 chapters for all 6 packs, but Phase A was blocked:

- `phase_a_quality_gate.ok`: `false`
- failed checks: `phase_a_q03_weakest_issue_share_exceeded`, `phase_a_q09_weakest_issue_share_exceeded`
- `cross_pack_pass_rate`: 0.994
- `synthetic_min_pack`: Q03 x4, Q09 x3, Q04 x2
- `tide_archive_memory_debt`: Q03 x9, Q09 x5, Q04 x2
- `urban_mystery_lotus_lane`: Q03 x5, Q09 x2, Q04 x1

After recovery, the current-code all-pack `longform_100` run is clean:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_gate.pass_rate`: 1.0
- packs reaching 100 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

The current-code all-pack `longform_250` run is also clean on content-quality evidence:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_250_summary.gate_pass_rate`: 1.0
- packs reaching 250 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Implementation notes:

- Q03 recovery is kernel-level: coverage anchor scoring ignores generic synthetic/meta anchor text, token coverage is considered alongside semantic similarity, and beat coverage can inherit same-event coverage where appropriate.
- Q04/Q03 interaction recovery is kernel-level: final Q04 micro repair now uses chapter/paragraph-aware action-dialogue variation and is followed by a final repetition/coverage pass plus length-floor recovery.
- No Phase A thresholds or benchmark baselines were lowered.
- Follow-up fresh closeout run:
  - artifact: `artifacts/longform250_review_closeout_run2.json`
  - backlog: `artifacts/longform250_human_review_backlog_run2.md`
  - after reviewer artifact: `artifacts/longform250_review_closeout_run2_after_human.json`
  - reviewer receipt: `artifacts/longform250_human_review_closeout_after_reviewer_run2.json`
  - `longform_250_signoff.ready`: `true`
  - `review_sample_coverage_250.closeout_ready`: `true`
  - `review_sample_coverage_250.closeout_status`: `closed_with_auto_seed`
  - `review_sample_coverage_250.planned_target_count`: 36
  - `review_sample_coverage_250.executed_target_count`: 36
  - reviewer samples written: 36/36 with `source=human_review`
  - `review_sample_coverage_250.human_closeout_ready`: `true`
  - `longform_250_human_review_closeout.ready`: `true`
- The first closeout pass only produced auto-seeded samples. The after-reviewer artifact records the separate reviewer samples rather than relabeling auto-seeded samples.

### Lane A / Phase 1 / longform_500 diagnostic entry

2026-04-24 diagnostic run after 250 closeout:

- artifact: `artifacts/longform500_diagnostic_after250_closeout.json`
- markdown: `artifacts/longform500_diagnostic_after250_closeout.md`
- summary: `artifacts/longform500_diagnostic_after250_closeout_summary.json`
- review backlog: `artifacts/longform500_review_backlog_after250_closeout.md`

Result:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- `longform_500_signoff.ready`: `true`
- `longform_500_human_review_closeout.ready`: `false`
- `longform_500_ending_signoff.ready`: `false`
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Residual issue surface:

- `urban_mystery_lotus_lane`: Q03 x1
- `tide_archive_memory_debt`: Q04 x1
- all other packs: empty `issue_mix`

500 follow-up:

- Run 500 review sampling / reviewer closeout for the 36 planned targets, including the `460-500` ending window.
- Investigate the two non-weakest residual issue chapters before claiming strict no-redundancy at 500.
- Keep 500 remediation kernel-level; do not pack-tune single chapters.

2026-04-25 residual recovery + human/ending closeout:

- focused Urban artifact: `artifacts/urban_q03_focus_after4.json`
- focused Tide artifact: `artifacts/tide_q04_focus_after8.json`
- final all-pack artifact: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.json`
- final all-pack markdown: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.md`
- final all-pack closeout DB: `artifacts/longform500_after_residual_fix_closeout_fresh_20260425.db`

Result:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- per-pack `surface_issue_chapters`: empty for all 6 packs
- `longform_500_signoff.ready`: `true`
- `longform_500_human_review_closeout.ready`: `true`
- `longform_500_ending_signoff.ready`: `true`
- `review_sample_coverage_500.planned_target_count`: 36
- `review_sample_coverage_500.executed_target_count`: 36
- `review_sample_coverage_500.auto_seeded_target_count`: 36
- `review_sample_coverage_500.human_reviewed_target_count`: 36
- `review_sample_coverage_500.human_closeout_ready`: `true`
- `review_sample_coverage_500.ending_window_human_closeout_ready`: `true`
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Residual deltas:

- `urban_mystery_lotus_lane` Q03: 1 -> 0
- `tide_archive_memory_debt` Q04: 1 -> 0
- all-pack Q03/Q04/Q05/Q09 blockers: 2 -> 0

Implementation notes:

- The benchmark now exposes chapter-level `surface_issue_chapters` diagnostics for longform issue surfaces, including issue codes and lint/repetition/detail metrics.
- Q03 recovery remains kernel-level: final repetition repair can replace repeated long-route paragraphs with beat-aware coverage bridges and multi-beat scene coverage.
- Q04 recovery remains kernel-level: final over-explanation repair is followed by dialogue/action pressure and a repetition/lint recheck.
- Longform repetition validation now uses longform chapter context when evaluating 1500+ unit chapters, preventing 500-route chapters from being misclassified under shortform repetition gates.
- The 500 closeout path writes separate `source=human_review` samples with reviewer id `ops_longform500_reviewer_after_residual_fix`; auto/eval samples remain separate.

2026-04-25 Reader product replay verification:

- Reader replay DB: `artifacts/reader_storybook_500_20260425.db`
- seed artifact: `artifacts/reader_storybook_500_20260425_seed.json`
- UI verification artifact: `artifacts/reader_storybook_500_20260425_result.json`
- screenshot directory: `artifacts/reader_storybook_500_20260425_screenshots/`
- redundancy audit artifact: `artifacts/reader_storybook_500_20260425_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_20260425_redundancy_audit.md`

Product display result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- packs reaching 500 in Reader replay: 6/6
- Storybook sampled chapter checks: 36/36
- required selectors verified: title, prose, quote, beats, sequence/active trajectory card
- browser console errors: 0
- image generation: not enabled

Reader redundancy audit result:

- reviewer id: `ops_longform500_reader_redundancy_audit_20260425`
- new `source=human_review` samples: 36
- DB count for this reviewer/source: 36
- risk breakdown: low 15, medium 12, high 9
- `reader_perceived_redundancy_closeout_ready`: `false`
- strongest Reader-perceived packs: `urban_mystery_lotus_lane`, `tide_archive_memory_debt`
- weakest Reader-perceived packs: `jade_court_exam`, `jade_court_romance`

Status distinction:

- Benchmark 500 closeout remains green and closed.
- Reader UI replay display closeout is green for the 36 sampled targets.
- Reader-perceived redundancy closeout is not closed; the next Lane A work should reduce Q03 sameness in reusable route/dialogue/scene-function generation.

2026-04-26 Reader-perceived Q03 recovery closeout:

- fresh all-pack benchmark: `artifacts/longform500_reader_q03_recovery2_20260425.json`
- benchmark markdown: `artifacts/longform500_reader_q03_recovery2_20260425.md`
- Reader replay DB: `artifacts/reader_storybook_500_q03_recovery2_20260425.db`
- seed artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_seed.json`
- UI verification artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_result.json`
- screenshot directory: `artifacts/reader_storybook_500_q03_recovery2_20260425_screenshots/`
- redundancy audit artifact: `artifacts/reader_storybook_500_q03_recovery2_20260425_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_q03_recovery2_20260425_redundancy_audit.md`

Benchmark result:

- `phase_a_quality_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Product display result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- Storybook sampled chapter checks: 36/36
- packs reaching 500 in Reader replay: 6/6
- browser console errors: 0
- minimum sampled prose length: 2051
- minimum sampled quote length: 8
- minimum sampled beat count: 3
- image generation: not enabled

Reader redundancy audit result:

- reviewer id: `ops_longform500_reader_q03_recovery_20260425`
- new `source=human_review` samples: 36
- risk breakdown: low 36, medium 0, high 0
- recovery gate: `high<=0`, `medium<=6`
- `reader_q03_recovery_ready`: `true`
- Jade/xianxia high-risk Q03: 0
- Urban/Tide high-risk Q03: 0

Reader redundancy delta:

- baseline Reader audit: high 9, medium 12
- first recovery attempt: high 5, medium 15
- final recovery audit: high 0, medium 0

Implementation notes:

- Scene opening, event-anchor, hook, and fallback dialogue variation now rotate by chapter/event/scene-function/beat context.
- Reader-facing scene-card quote and beat fields now use chapter-aware persisted replay data instead of static event-title fallbacks.
- SQLite Reader replay payload loading uses lean JSON extraction for Story UI endpoints, avoiding full long-route `plan_json` deserialization during 500 replay verification.
- Phase A thresholds and benchmark baselines were unchanged.

2026-04-26 Storage + Jade voice + Q05 polish closeout:

- final all-pack benchmark: `artifacts/longform500_storage_voice_q05_final_20260426.json`
- benchmark markdown: `artifacts/longform500_storage_voice_q05_final_20260426.md`
- standard guardrail artifact: `artifacts/phase0_guardrail_storage_voice_q05_final_20260426.json`
- Reader replay DB: `artifacts/reader_storybook_500_storage_voice_q05_20260426.db`
- seed artifact: `artifacts/reader_storybook_500_storage_voice_q05_20260426_seed.json`
- UI verification artifact: `artifacts/reader_storybook_500_storage_voice_q05_20260426_result.json`
- screenshot directory: `artifacts/reader_storybook_500_storage_voice_q05_20260426_screenshots/`
- redundancy audit artifact: `artifacts/reader_storybook_500_storage_voice_q05_20260426_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_storage_voice_q05_20260426_redundancy_audit.md`

Benchmark result:

- `phase_a_quality_gate.ok`: `true`
- `content_quality_contract_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- strongest packs: `xianxia_forgotten_vow`, `urban_mystery_lotus_lane`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Polish metrics:

- Q05 detail density: Urban 0.077, Xianxia 0.082, Jade Exam 0.077, Jade Romance 0.077, Synthetic 0.081, Tide 0.076
- Jade voice separation: 0.623 -> 0.861 for both `jade_court_exam` and `jade_court_romance`
- Standard Phase A guardrail remains green with `phase_a_quality_gate.ok=true`; longform-only Q05 uplift is intentionally scoped away from short-route chapters.

Replay storage result:

- fresh 6-pack x 500 Reader replay DB total size, including WAL/SHM: 383.84 MiB
- `plan_json` p95: 132,100 bytes
- `plan_json` max: 143,078 bytes
- chapter rows: 3000
- lean storage rows: 3000/3000
- top-level full debug keys: 0 rows with `step_record`, `candidate_batch`, `scored_candidates`, `routes`, or `promise_ledger_snapshot`

Reader product replay result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- Storybook sampled chapter checks: 36/36
- packs reaching 500 in Reader replay: 6/6
- browser console errors: 0
- minimum sampled prose length: 2061
- minimum sampled quote length: 8
- minimum sampled beat count: 3
- image generation: not enabled

Reader redundancy audit result:

- reviewer id: `ops_longform500_reader_q03_recovery_20260425`
- new `source=human_review` samples: 36
- risk breakdown: low 34, medium 2, high 0
- `reader_q03_recovery_ready`: `true`
- `reader_perceived_redundancy_closeout_ready`: `true`

Implementation notes:

- `save_step()` now writes lean replay payloads by default; full step traces require `NARRATIVEOS_STORE_FULL_STEP_RECORD=1`.
- `scripts/compact_replay_plan_json.py` provides explicit old-DB compaction and preserves Reader replay fields, choices, review flags, and human review samples.
- Q05 repair now adds beat-linked sensory anchors and then re-runs final Q03/Q04 coverage and exposition guards.
- The 500 run remains expensive: final all-pack acceptance took roughly 104 minutes locally, so 500 should remain an acceptance/nightly gate until lint/repetition caching is added.

2026-04-27 Longform acceptance runtime hardening:

- Benchmark artifacts now include `benchmark_runtime_profile` and per-world `runtime_profile` payloads.
- The profile records wall-clock simulation time, summed chapter generation latency, quality-pass total time, lint/evaluation time, route diagnostics, content-quality-contract metrics, slowest worlds, and quality-pass action buckets.
- Repetition signal analysis now uses a process-local safe LRU cache for identical cleaned paragraph sets; callers receive copies, so lint/repetition payload mutation remains isolated.
- CLI supports `--acceptance-profile fast|full|nightly`, `--changed-worldpacks`, `--fast-gate-weakest-limit`, and `--runtime-profile-out`.
- Fast profile selects changed packs plus baseline weakest packs and marks `nightly_full_gate_required=true` whenever the selected set is not all six benchmark packs.
- Release policy: fast gate is suitable for merge triage; full all-pack 500 remains required for release evidence and Reader replay closeout.

2026-04-27 Lane A / Phase 1 / Task A1.4 fast-gate precheck:

- Baseline fast-gate artifact: `artifacts/fast_gate_a14_jade_current_weakest_20260427.json`
- Post-title-polish fast-gate artifact: `artifacts/fast_gate_a14_title_function_after_20260427.json`
- Scope: changed packs `jade_court_exam`, `jade_court_romance`; baseline weakest pack `synthetic_min_pack`.
- Both runs reached 500/500 for all 3 selected packs.
- Both runs kept `phase_a_quality_gate.ok=true`, `content_quality_contract_gate.ok=true`, `cross_pack_pass_rate=1.0`, and `longform_500_summary.gate_pass_rate=1.0`.
- Both runs kept `issue_mix=[]` and Q03/Q04/Q05/Q09 counts at 0 for all selected packs.
- Post-title-polish metrics: Jade Exam detail 0.077 / voice 0.861 / long-route quality 0.897; Jade Romance detail 0.077 / voice 0.861 / long-route quality 0.903; Synthetic detail 0.081 / voice 0.933 / long-route quality 0.865.
- Runtime cost remains high even in fast mode: post-title-polish selected-pack gate took about 44.08 minutes, with about 40.59 minutes attributed to quality pass.

2026-04-27 Lane A / Phase 1 / Task A1.4 full Reader longform closeout:

- fresh all-pack benchmark: `artifacts/longform500_a14_closeout_20260427.json`
- benchmark markdown: `artifacts/longform500_a14_closeout_20260427.md`
- runtime profile: `artifacts/longform500_a14_closeout_20260427_runtime.json`
- benchmark DB: `artifacts/longform500_a14_closeout_20260427.db`
- Reader replay DB: `artifacts/reader_storybook_500_a14_closeout_20260427.db`
- Reader replay seed: `artifacts/reader_storybook_500_a14_closeout_20260427_seed.json`
- UI verification artifact: `artifacts/reader_storybook_500_a14_closeout_20260427_result.json`
- screenshot directory: `artifacts/reader_storybook_500_a14_closeout_20260427_screenshots/`
- redundancy audit artifact: `artifacts/reader_storybook_500_a14_closeout_20260427_redundancy_audit.json`
- redundancy audit markdown: `artifacts/reader_storybook_500_a14_closeout_20260427_redundancy_audit.md`

Benchmark result:

- `phase_a_quality_gate.ok`: `true`
- `content_quality_contract_gate.ok`: `true`
- `cross_pack_pass_rate`: 1.0
- `longform_500_summary.gate_pass_rate`: 1.0
- packs reaching 500 chapters: 6/6
- per-pack `issue_mix`: empty for all 6 packs
- Q03/Q04/Q05/Q09 counts: 0/0/0/0 for every pack
- strongest packs: `xianxia_forgotten_vow`, `urban_mystery_lotus_lane`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`

Per-pack quality snapshot:

| Pack | Detail density | Voice separation | Long-route quality | Issue mix |
| --- | ---: | ---: | ---: | --- |
| `urban_mystery_lotus_lane` | 0.077 | 0.933 | 0.888 | empty |
| `xianxia_forgotten_vow` | 0.082 | 0.934 | 0.890 | empty |
| `jade_court_exam` | 0.077 | 0.861 | 0.897 | empty |
| `jade_court_romance` | 0.077 | 0.861 | 0.903 | empty |
| `synthetic_min_pack` | 0.081 | 0.933 | 0.865 | empty |
| `tide_archive_memory_debt` | 0.076 | 0.938 | 0.883 | empty |

Runtime result:

- all-pack full benchmark wall-clock profile: about 101.00 minutes
- quality-pass cost: about 93.86 minutes
- slowest worlds by total time: `urban_mystery_lotus_lane` about 21.05 minutes, `tide_archive_memory_debt` about 20.78 minutes, `synthetic_min_pack` about 17.57 minutes
- This confirms F1.1 fast/deep split remains necessary; full all-pack 500 is release evidence, not routine merge triage.

Reader product replay result:

- Quantum frontend: `http://127.0.0.1:3000`
- API backend: `http://127.0.0.1:8000`
- Storybook sampled chapter checks: 36/36
- packs reaching 500 in Reader replay: 6/6
- browser console errors: 0
- minimum sampled prose length: 2061
- minimum sampled quote length: 8
- minimum sampled beat count: 3
- screenshots written: 6 pack screenshots
- image generation: not enabled

Replay storage result:

- fresh 6-pack x 500 Reader replay DB total size, including WAL/SHM: 384.05 MiB
- chapter rows: 3000
- `plan_json` average: 115,516.9 bytes
- `plan_json` p95: 132,006 bytes
- `plan_json` max: 143,148 bytes
- top-level full debug payload keys present: 0 rows for `step_record`, `candidate_batch`, `scored_candidates`, `routes`, or `promise_ledger_snapshot`

Reader redundancy audit result:

- reviewer id: `ops_longform500_reader_q03_recovery_20260425`
- reviewed targets: 36/36
- risk breakdown: low 34, medium 2, high 0
- `reader_q03_recovery_ready`: `true`
- `reader_perceived_redundancy_closeout_ready`: `true`
- baseline comparison artifact: `artifacts/reader_storybook_500_storage_voice_q05_20260426_redundancy_audit.json`
- Jade guard: `jade_court_exam` medium 1 -> 1, high 0 -> 0; `jade_court_romance` medium 1 -> 1, high 0 -> 0
- Medium-risk backlog remains bounded to chapter 21 in `jade_court_exam` and chapter 21 in `jade_court_romance`; no high-risk Q03 sample exists.

2026-04-27 Lane A weakest-pack diagnostic for Reader waiting-state PR:

- benchmark artifact: `artifacts/lane_a_weakest_pack_diagnostic.md`
- benchmark DB: `artifacts/lane_a_weakest_pack_diagnostic.db`
- command required explicit `--database-url sqlite:///artifacts/lane_a_weakest_pack_diagnostic.db` because this local shell had no default `DATABASE_URL`.
- benchmark mode: `long_route`, chapter budget `36`, min end turn override `30`, all 6 benchmark packs covered.
- `phase_a_quality_gate.ok`: `true`
- `content_quality_contract_gate.ok`: `true`
- `cross_pack_pass_rate`: `1.000`
- benchmark delta vs `tests/long_route_benchmark_baseline.json`: `+0.067`
- strongest packs: `xianxia_forgotten_vow`, `urban_mystery_lotus_lane`
- weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`
- Q03/Q04/Q05 issue mix: clean for weakest packs; Q10 is not covered by this benchmark and remains a Reader continuity / UI follow-up signal, not a generated-prose delta.
- weakest dimensions still point to `scene_detail_density`, `dialogue_ratio`, and either `voice_separation_score` or `character_fidelity`; recommended target remains writer / planner / world pack asset.
- metric regressions: `avg_repetition_score` regressed for `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`, `urban_mystery_lotus_lane`, and `xianxia_forgotten_vow`, even though issue mix stayed clean.
- runtime: total wall about 410s; quality-pass cost about 392s, confirming this diagnostic is too expensive for every frontend-only change.
- `world_template_minimal` is excluded from benchmark registry. Task 1.11 now filters `catalog_role=template` / `public_catalog_visible=false` from public Reader import and showcase surfaces; if a long-running local backend still shows it, restart the API process so the catalog gate is picked up.

### Lane A / Phase 1 / Task 1.6 500-chapter product readiness contract

500 chapters is no longer treated as a single successful long run. A world can only be product-marked as 500-ready when four evidence classes are present:

- structural capability: `claim_safe_band >= 500` and `longform_readiness.status=ready`
- generation hard constraints: latest 500 evidence includes `generation_hard_constraint_summary.chapter_count >= 500` and `hard_fail_count=0`
- Reader replay projection: 500 Reader replay has a windowed/projection evidence summary, not only a full-route payload
- runtime profile: benchmark output carries `benchmark_runtime_profile` so full 500 cost remains visible

Task 1.6 adds scene-card visible text to generation hard constraints. `scene_card.title / summary / quote / story_beats / visual_details` are now checked for broken slots, meta narration, engineering leaks, and repeated stock phrases. Benchmark markdown now reports `scene_card_visible_text_audit` alongside the existing hard-fail and repair summary.

Reader replay supports windowed projection via `start_chapter / end_chapter / limit / latest`. The default remains full replay for compatibility, but 500 Storybook/Reader flows should request early, middle, ending, and recent windows instead of requiring the browser to load the full 500-node route.

2026-04-28 Task 1.6 synthetic 500 smoke:

- artifact: `artifacts/task_1_6_synthetic_500_cached.md`
- runtime profile: `artifacts/task_1_6_synthetic_500_cached_runtime.json`
- scope: `synthetic_min_pack` only, `longform_500`, fast acceptance profile; this is not all-pack signoff.
- result: 500/500 chapters reached, `hard_fail_count=0`, `repair_success_rate=1.000`, `scene_card_visible_text_audit.violation_count=0`.
- performance after repetition detector cache: total wall `1,041,620ms`, quality pass `975,709ms`.
- previous same-scope profile before detector cache: total wall `1,107,665ms`, quality pass `1,043,149ms`.
- delta: about 6.0% total wall reduction and 6.5% quality-pass reduction. Useful but not sufficient for the product target; all-pack 500 still belongs in nightly/release gate until the repair loop reduces repeated Q03/length lint passes.
- signoff state remains watch: `longform_500_signoff.ready=false` because benchmark scope is incomplete and interactive/replay signoff still needs all-pack evidence.

### Lane A / Phase 1 / Tasks 1.7-1.11 500-chapter commercial readiness closeout

500 readiness is judged against the user experience of reading, choosing, and continuing one chapter at a time. Full benchmark wall-clock remains an internal eval cost signal, not a user-side blocker.

Task 1.7 fresh all-pack evidence:

- fixed command:
  - `.venv311/bin/python -m src.narrativeos.benchmark.runner --worldpack all --database-url sqlite:///artifacts/lane_a_1_7_all_pack_500.db --benchmark-mode longform_500 --max-chapters 500 --min-end-turn-override 500 --markdown-out artifacts/lane_a_1_7_all_pack_500.md --runtime-profile-out artifacts/lane_a_1_7_all_pack_500_runtime.json`
- benchmark DB: `artifacts/lane_a_1_7_all_pack_500.db`
- benchmark markdown: `artifacts/lane_a_1_7_all_pack_500.md`
- runtime profile: `artifacts/lane_a_1_7_all_pack_500_runtime.json`
- required pass criteria:
  - 6/6 benchmark packs reach 500 chapters
  - persisted chapter hard violations stay at 0
  - `scene_card_visible_text_audit.violation_count=0`
  - `grounding_status=failed` cannot be counted as passed quality
  - Q03/Q04/Q05/Q09 issue mix has no blocker
- result:
  - cross-pack pass rate: 1.000
  - benchmark delta: +0.067
  - packs reaching 500 chapters: 6/6
  - generation hard constraint chapters: 3000
  - hard fail count: 0
  - repair success rate: 1.000
  - scene-card visible text violations: 0
  - longform 500 gate pass rate: 1.000
  - weakest packs: `jade_court_exam`, `jade_court_romance`, `synthetic_min_pack`
  - strongest packs: `tide_archive_memory_debt`, `xianxia_forgotten_vow`
  - residual issue mix: non-blocking Q03 x1 in `tide_archive_memory_debt` and Q03 x1 in `xianxia_forgotten_vow`; weakest-pack issue mix remains clean.
- runtime:
  - total wall ms: 5,839,704.159 (~97.33 minutes)
  - quality pass ms: 5,363,617.311 (~89.39 minutes)
  - slowest worlds: `urban_mystery_lotus_lane`, `tide_archive_memory_debt`, `synthetic_min_pack`
- signoff interpretation:
  - hard generation/replay prerequisites passed.
  - benchmark-native `longform_500_signoff`, `human_review_closeout`, and `ending_signoff` still report `watch` because the runner does not ingest the separate Task 1.8 human sampling artifact and because `jade_court_exam` / `jade_court_romance` remain `continue_polish`.
  - Therefore this is fresh 500 hard-evidence, not full commercial 500-ready badge authorization for every world.

Task 1.8 human readability sampling:

- artifact: `artifacts/lane_a_1_8_500_human_sampling.json`
- markdown: `artifacts/lane_a_1_8_500_human_sampling.md`
- source replay DB: `artifacts/reader_storybook_500_a14_closeout_20260427.db`
- fixed sample chapters per pack: 1, 21, 220, 260, 460, 480
- result: 36/36 reviewed, risk breakdown low 34 / medium 2 / high 0
- medium backlog: `jade_court_exam` chapter 21 and `jade_court_romance` chapter 21, both Q03; no high-risk sample and no medium concentration in the 460-500 ending window.

Task 1.9 legacy content quarantine:

- Legacy replay text may be repaired at read time by `repair_reader_view_for_display`.
- The repair covers reader-visible title, recap, body, relationship hints, scene-card title/summary/quote/beats/visual details, and choices.
- Repaired responses carry `reader_view.display_sanitization` with source `legacy_read_projection`.
- The raw persisted chapter and original quality event remain unchanged, so historical broken content is not reclassified as fresh pass.

Task 1.10 Reader single-chapter continuation proof:

- Reader continue must remain a one-chapter-at-a-time path with waiting state, retryable failures, and no persistence of failed quality guard chapters.
- 500 replay verification must use window projection rather than loading the full route into the Story shell.
- Failure messages must keep backend-down, entitlement/credit, permission, and quality-block states distinct.
- Latest-code isolated replay verification:
  - result artifact: `artifacts/lane_a_1_10_500_replay_result.json`
  - screenshots: `artifacts/lane_a_1_10_500_replay_screenshots/`
  - audit artifact: `artifacts/lane_a_1_10_500_replay_redundancy_audit.json`
  - audit markdown: `artifacts/lane_a_1_10_500_replay_redundancy_audit.md`
  - app/backend ports: `3001/8012`, because the user's default `3000/8000` processes were already running without backend reload.
  - result: 36/36 sampled chapters checked, 6/6 worlds reaching 500, console errors 0, minimum prose length 2061, minimum quote length 8, minimum beat count 3.
  - separate `3000` smoke on the already-running app showed no console errors and no 500-ready badge; that process should not be used as fresh backend evidence until API is restarted.

Task 1.11 Catalog 500-ready gate:

- Public catalog and showcase may expose `claimSafeBand` for transparency, but must not use it as a 500-ready badge.
- The only public 500-ready signal is `productReadyBand === "500"` plus `longform500ProductReady === true`.
- `catalog_role=template` and `public_catalog_visible=false` versions are excluded from public Reader import/showcase surfaces.
- Ops should retain missing-evidence reasons through `longform_500_product_readiness.blockers`.

### Lane A / Phase 1 / Task 1.13 Jade continue_polish kernel closure

Task 1.13 closes the Jade `continue_polish` blocker through kernel-level writer/dialogue/scene realization policy, not pack-local prose edits and not threshold changes.

- Formal artifact set:
  - benchmark DB: `artifacts/lane_a_1_13_all_pack_500.db`
  - benchmark JSON: `artifacts/lane_a_1_13_all_pack_500.json`
  - benchmark markdown: `artifacts/lane_a_1_13_all_pack_500.md`
  - runtime profile: `artifacts/lane_a_1_13_all_pack_500_runtime.json`
- command:
  - `.venv311/bin/python -m src.narrativeos.benchmark.runner --worldpack all --database-url sqlite:///artifacts/lane_a_1_13_all_pack_500.db --benchmark-mode longform_500 --max-chapters 500 --min-end-turn-override 500 --execute-human-review-closeout-500 --markdown-out artifacts/lane_a_1_13_all_pack_500.md --runtime-profile-out artifacts/lane_a_1_13_all_pack_500_runtime.json`
- result:
  - benchmark scope complete: 6/6 packs
  - packs reaching 500 chapters: 6/6
  - `longform_500_summary.gate_pass_rate`: 1.000
  - `longform_500_signoff.ready`: `true`
  - `longform_500_human_review_closeout.ready`: `true`
  - `longform_500_ending_signoff.ready`: `true`
  - `weakest_pack_polish_program.status`: `stop_ready`
  - `continue_worlds`: `[]`
  - hard fail count: 0 across 3000 chapters
  - scene-card visible text violations: 0
  - Q03/Q04/Q05/Q09 issue mix: empty for every benchmark world
- Jade effect:
  - `jade_court_exam`: dialogue ratio 0.590, issue mix empty, stop-ready.
  - `jade_court_romance`: dialogue ratio 0.593, issue mix empty, stop-ready.
- strongest / weakest:
  - all worlds reached pass rate 1.000; weakest long-route quality remains `synthetic_min_pack` at 0.873, but it is stop-ready and not in `continue_worlds`.
  - strongest by long-route quality is `urban_mystery_lotus_lane` at 0.896 among non-Jade packs, with `jade_court_romance` at 0.900.
- runtime:
  - total wall ms: 7,578,248.316 (~126.30 minutes)
  - this is acceptable as release evidence, but eval cost remains a follow-up for profiling/cache work.

## 离线评测数据包建议
每个 world 至少准备：
- 20 条合法路径
- 10 条非法路径
- 10 个人物保真 case
- 10 个 promise 兑现 case
- 5 个分支多样性 case
