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
  - 对重复段落做 variation pass，优先改写重复 beat 的段落结构
- `Q04 over-explanation`
  - 当 exposition ratio 过高或正文过短时，补一段更 scene-facing 的 dialogue pressure
- `Q05 lack of scene detail`
  - 当 concrete detail density 过低时，补具体的 sensory grounding 段落
- `Q09 pacing failure / premature ending`
  - 加强结尾 hook
  - 在 `min_end_turn` 之前，对 terminal scene function 施加更强 penalty

它的目标不是直接替代更深的 planner/writer 重构，而是先提供一个可复用、可 benchmark 的 kernel-level 修复框架。

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

它的用途是回答：

1. 当前 pack 是否能撑到 30–50 章
2. 中段是否开始掉速
3. 重复和解释句是否在长线里持续升高
4. 失败主要是过早收束，还是根本无合法路线

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

## 离线评测数据包建议
每个 world 至少准备：
- 20 条合法路径
- 10 条非法路径
- 10 个人物保真 case
- 10 个 promise 兑现 case
- 5 个分支多样性 case
