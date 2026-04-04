# NarrativeOS · Beta Kernel Handoff

如果要最快理解“当前已经完成到什么状态 + 距离商业化还缺什么”，优先阅读：

- [docs/gpt_handoff_status_and_commercialization.md](/Users/lili/Desktop/narrativeos_codex_handoff/docs/gpt_handoff_status_and_commercialization.md)

这套仓库现在已经从“单作品可运行 Alpha”升级为一个 **商业化 Beta 内核雏形**。它仍然保留现有 Alpha 的 `/app`、Reader Mode、示例世界与基础 API，但新增了：

- 多 `World Pack` 加载与版本管理
- `Author / Ops / Reader` 三端最小产品骨架
- Author 端已支持“选题材 + 写 brief + 生成 Draft”的普通用户创作入口
- Author 端现已补强 `draft diff + simulation drill-down`
- Author 端现已补 `style / pacing / hook` 结构化控制面板
- Ops 端已支持 review history、publish checklist、rollback history、quality trend 与风险摘要
- Ops 端现已补 `Alert Center`，能把 runtime / support / governance / async job 信号聚成主动告警 feed，并支持 acknowledge / resolve / investigation prefill
- Ops 端现已补 `Ops Control Plane`，把 `Alert Center + Account Workspace + Release Workspace + Governance + Investigation` 串到同一套 navigation / escalation model
- Ops control plane 的前端边界现也被 shell smoke test 锁住：`/app` 会按 `ops_refresh.js -> ops_actions.js -> ops_render_sections.js -> app.js` 顺序装配，避免模块职责悄悄回流到单文件
- Ops navigation 现已对失效 `alert_id` 做 soft-fail：不会因为 stale alert 直接让 Control Plane 404，而是保留其余 `account/world/case` 上下文继续排查，并在 summary 中提示 stale ref
- Ops navigation stale-ref hardening 现已扩到 `case_id / world_id / world_version_id`，Control Plane 会尽量保住剩余上下文继续解析，而不是因为单个 ref 失效就整条导航掉线
- Ops Control Plane 现也补了 stale-ref remediation actions：会在 follow-up actions 中直接给出 `Clear Stale Refs / Re-sync From Valid Context`，让 Ops 不必手动删 input 再刷新
- 仓库现也补了 `scripts/run_ops_navigation_stale_ref_smoke.sh`，可重复执行这条 remediation 的真实浏览器 smoke
- Ops 端的 `review history + publish checklist` 现已支持 drill-down：
  - `publish_checklist[*].owner / severity / next_action / evidence`
  - `publish_checklist_summary`
  - `recent_reviews_drilldown`
  - `review_timeline / review_summary`
- Ops 端的 `rollback history + quality trend` 现也支持 drill-down：
  - `rollback_drilldown / rollback_summary`
  - `quality_trend[*].delta_vs_previous / regression_detected / publish_gate_errors / top_failing_pack_ids`
  - `quality_trend_summary`
- Reader 端已支持内测 entitlement / credits 授予、`active / expired / exhausted` 状态与访问原因展示
- Monetization & Entitlements M0 已开始落地：3 档会员、双钱包、subscription lifecycle、web-first checkout stub
- Phase 3 monetization 现已继续补 webhook / renewal / cancel / retry / past_due 生命周期闭环、checkout session 持久化，以及 Reader / Author / Ops 生命周期可见性
- Phase 4 数据飞轮接口已继续推进：支持 `dataset_view`，可导出 evaluator-ready / reranker-ready / analytics-ready examples，并附带 split 与质量告警
- `Postgres-first + SQLite fallback` 的平台化持久层
- `Authoring / Review / Billing / Analytics` 服务层
- `Monetization / Subscription / Wallet` 并行主线骨架
- learned evaluator baseline runner（离线）
- learned evaluator shadow inference（并行对照，不影响 gate）
- learned evaluator shadow candidate summary（后端 + Ops surfacing）
- learned reranker baseline runner（离线）
- learned reranker shadow candidate summary（后端 + Ops surfacing）
- shared learned analysis runner（离线）
- unified learned dashboard contract（Ops summary）
- learned shadow decision compare（Ops compare summary）
- learned impact tracking（Ops retention / monetization correlation summary）
- `Karma Character Engine v0.1` 与章节化叙事核心
- `Story Feed + Sticky Composer + Intent Prefill` 的连续阅读流
- `NarrativeEval v0.1` 的多层评测与 pass / rewrite / block 闸门
- `Kernel-first / capability-first` 的正文能力边界：
  - `DialogueRealismPolicy`
  - `VoiceProfile`
  - `EmotionActionPolicy`
  - `SensoryGroundingPolicy`
  - `SceneRealizationContract`
  - `WorldNarrativeStylePack`
- cross-pack benchmark、provider abstraction 与 merge gate 雏形
- weakest packs 的 capability 资产已补强，`cross_pack_pass_rate` 已从 `0.0` 拉升到 `0.9`
- cross-pack benchmark 现已输出 per-pack issue diagnosis，weakest packs 不再只显示 pass rate

## 当前实现状态

### 本轮重构完成情况

- Phase 1 已完成：`story_phase / chapter_index / min_end_turn` 入状态；ending gate 接入 canon；张力改为 phase-based
- Phase 2 已完成：新增 `ChapterPlan / SceneBeat / SceneRenderSpec / SceneIntent`；内部从“单事件回合”升级为“单场景章节”
- Phase 3 已完成：新增 `presenter.py / sanitizer.py`；API 默认输出 Reader Mode，debug 信息只在显式 `debug=true` 时返回
- Phase 4 已完成：加入 promise pressure、scene history、长线事件扩容；demo 世界单路线可稳定支撑 8-12 章节
- Phase 5 已完成：渲染新增 `novel_light / novel_lush / manhua_drama` 风格；默认用户层使用更长的章节正文
- Karma Engine v0.1 已完成：`CharacterState` 升级为“命 / 业 / 毒 / 愿 / 惑 / 智”人物体；`NarrativeState` 新增 `fate_pressure / karmic_weather / unresolved_debts / relationship_graph`
- Karma/Fate/Relationship 子系统已落地：新增 `karma.py / fate.py / relationship_graph.py / character_engine.py / scene_functions.py`
- Beta Kernel 平台化骨架已完成：
  - 新增 `core / worldpacks / services / api / persistence`
  - handoff 中的 `db/`、`contracts/`、`legacy/`、补充 `specs/` 已迁入根仓库
  - world pack registry、authoring、review、billing、analytics 已有最小可运行实现
  - `/app` 已扩成 `Reader / Author / Ops` 三端骨架
- 内容与阅读流去噪已完成第一轮：
  - 新增 `current_generation_pipeline` 与 `provenance_policy`
  - 引入 `ScenePlan -> Writer -> Linter -> Presenter`
  - Reader 主区改成 `Story Feed`
  - 新增 `Intent Prefill Service`
- NarrativeEval v0.1 已完成第一轮：
  - 新增 `eval/` 目录
  - 章节可生成 `EvaluationReport`
  - simulation / publish 受 `pass / rewrite / block` 闸门约束
  - Reader 在线生成只记录，不阻断
  - draft simulation 现已附带 `cross_pack_summary / metric_deltas / top_failing_packs`
  - publish gate 现会检查 `cross-pack summary / prose leak / metric regression`
- Repository 默认会读取 `DATABASE_URL`；未设置时回退到 `sqlite:///narrativeos_beta.db`

### 已实现能力

- `WorldBible`、`NarrativeState`、`EventAtom`、`RouteCandidate` 等核心领域模型支持稳定 JSON 序列化
- `NarrativeState` 现已包含 `story_phase`、`chapter_index`、`min_end_turn`
- 新增 `EndingGate`、`SceneIntent`、`SceneBeat`、`SceneRenderSpec`、`ChapterPlan`、`NarrativeViewModel`
- 新增 `PoisonVector`、`VowProfile`、`WoundProfile`、`AwakeningProfile`、`DestinyContract`、`DebtEntry`、`KarmicSeed`、`RelationshipEdge`
- `examples/` 下 demo world/state/events 可通过 schema 校验并完整反序列化
- `examples/worldpacks/` 下已具备多 pack 资产：
  `jade_court_exam_pack`、`jade_court_romance_pack`、`urban_mystery_lotus_lane`、`xianxia_forgotten_vow`
- 已新增 `synthetic_min_pack`，专门用于验证 kernel 不依赖任何当前示例人物或礼法体系
- world pack 现已可承载 capability 资产：
  - `dialogue_realism_policy`
  - `voice_profiles`
  - `response_cadence_profiles`
  - `pressure_response_styles`
  - `emotion_action_policies`
  - `sensory_grounding_policies`
  - `scene_realization_contracts`
- `docs/runtime_asset_inventory.md` 已明确记录当前 Alpha 的资产耦合点与可平台化部分
- `docs/architecture/current_generation_pipeline.md` 已明确当前生成链路
- `docs/legal/provenance_policy.md` 已写明 clean-room 规则
- `docs/phase_0_summary.md` 到 `docs/phase_4_summary.md` 已记录本轮阶段交付
- `docs/narrative_eval_v0_1.md` 与 `docs/phase_eval_summary.md` 已记录评测层
- 内部主循环已从“一个回合 = 一个事件”升级为“一个回合 = 一个场景”，单章内部会推进 3-5 个 beats
- 评分主轴已从简单 goal overlap 升级为 `desire / shadow / poison / vow / wound / debt / karma / fate / wisdom_resistance`
- 事件现在会显式种下 `KarmicSeed`，并通过 `relationship_graph` 与 `debt_deltas` 写入全局关系债
- `scene_function` 已切到人性冲突型主路径：`temptation / mask_crack / debt_exchange / misrecognition / truth_trial / mercy_vs_control / humiliation / confession_window / karma_ripening / vow_payment / false_peace`
- 默认 step 接口输出 Reader Mode：`chapter_title / recap / body / scene_card / choices`
- 渲染层与逻辑层严格分离，默认章节正文为更长的 `premium_prose`
- 默认章节正文已加入角色化对白、动作线、误会/债务回响与 Karma 派生的命运压力
- 误解与代价现在被视为 `KarmicSeed + DebtEntry + relationship_graph` 的派生视图，而不是独立真相源
- 场景规划已改成“章节 3-5 拍 + 2-3 个真实推进事件”的混合结构，避免正文只靠同一句 summary 反复扩写
- `world / world_version / session / chapter / review / entitlement / usage_meter / analytics_event` 已有统一 Repository contract
- Reader API 已扩成 Library Shelf、World Detail、Create Session、Continue Story、Replay、Quote Continue
- Reader API 已补 `prefill`
- Reader API 已补：
  - `GET /v1/reader/entitlements`
  - `POST /v1/reader/entitlements/grant`
- entitlement 语义现已统一为：
  - `subscriber`
  - `world_pass`
  - `credits`
  并在返回中明确给出 `status / reason / balance / expires_at`
- tier config 与 gating 现已统一收口到：
  - `configs/monetization_tiers.json`
  - `entitlement_matrix`
  - `author_access_levels`
  - `config_version`
- `reader/subscription` 与 `ops/entitlements` 现会直接返回 tier catalog + entitlement matrix，不再只返回零散余额与状态
- `ops/entitlements` 现已补：
  - `audit_summary`
  - `audit_timeline`
  - `audit_trail`
  - `audit_breakdown`
  - `timeline_cursor`
  - `revoke_candidates`
  并支持 `POST /v1/ops/entitlements/revoke`
- Ops 现已补 `account detail` 入口：
  - `GET /v1/ops/accounts/{account_id}`
  - `GET /v1/ops/accounts/{account_id}/workspace`
  - 聚合 `subscription / wallets / entitlements / recent_meters / recent_events / recent_sessions / recent_drafts / author_access / audit_trail / audit_breakdown / support_summary / support_issues`
  - `workspace` 现会进一步返回：
    - `workspace_summary`
    - `wallet_posture`
    - `entitlement_posture`
    - `top_blockers`
    - `action_pack`
    - `investigation_summary`
    - `linked_context`
    - `operator_timeline`
  - `/app` 中对应的 `账户详情 / 权益 / 订阅 / 钱包统一排查页` 现已把原本分散的 account detail / support / alerts / investigation 重新收束成一个 operator workspace：
    - 先看 account health / blockers / recommended path
    - 再看 quick actions
    - 再看 operator timeline
    - 最后继续 drill-down 到原有 `subscription audit / support / alert / governance / investigation`
- Ops 现已补 `account issue lookup`：
  - `GET /v1/ops/accounts/{account_id}/issues`
  - 输出 `support_summary / support_issues / support_tooling`
  - 能直接定位 `missing_subscription / payment_required / credits_exhausted / studio_credits_exhausted / author_access_blocked / subscription_lifecycle_issue`
- Ops 现已补 `rights / moderation / abuse flow skeleton`：
  - `GET /v1/ops/accounts/{account_id}/governance`
  - `POST /v1/ops/accounts/{account_id}/governance/escalate-support`
  - `GET /v1/ops/governance/cases`
  - `GET /v1/ops/governance/cases/{case_id}`
  - `POST /v1/ops/governance/cases`
  - `POST /v1/ops/governance/cases/{case_id}/assign`
  - `POST /v1/ops/governance/cases/{case_id}/evidence`
  - `POST /v1/ops/governance/cases/{case_id}/status`
  - `GET /v1/ops/governance/restrictions`
  - `POST /v1/ops/governance/restrictions`
  - `POST /v1/ops/governance/restrictions/{restriction_id}/release`
  - `GET /v1/ops/export/governance-audit`
  - 复用 `review_records` 作为最小 case storage，不引入新表
  - `/app` 中新增 `治理 Case 流` 面板，可创建 case、更新状态、施加/释放 restriction、从 support issue 一键升级治理 case，并查看单 case drill-down 与治理导出摘要
  - restriction 当前支持：
    - `reader_access_block`
    - `author_access_block`
    - `checkout_block`
    - `account_hold`
  - governance case 现已补 `owner_id / due_at / disposition / policy_labels / evidence_refs / workflow_checklist`
  - 单 case detail 现会返回：
    - `workflow_summary`
    - `permission_summary`
    - `evidence_refs`
    - `detail_summary.owner_id / evidence_count`
  - status flow 现已从“任意改状态”收口到明确 transition：
    - `open -> in_review / escalated / dismissed`
    - `in_review -> escalated / resolved / dismissed`
    - `escalated -> in_review / resolved / dismissed`
  - 当使用 bearer token 或 `X-NarrativeOS-*` reviewer identity 时，governance mutation 会优先信任该身份；`author` 角色不能执行 governance mutation
  - `/app` 中新增 `Owner ID / Due At / Policy Labels / Evidence Title / Evidence Preview`，并支持 `Assign Case / Add Evidence`
- Ops 现已补 `Unified Investigation` 聚合排查入口：
  - `GET /v1/ops/investigations/accounts/{account_id}`
  - `GET /v1/ops/investigations/cases/{case_id}`
  - `GET /v1/ops/investigations/world-versions/{world_version_id}`
  - `GET /v1/ops/export/investigation-trace`
  - 统一返回 `generated_at / filters / investigation_summary / linked_entities / trace_timeline / evidence_index / recommended_paths`
  - 把 `billing lifecycle / retry attempts / support issues / governance cases / review timeline / publish checklist / rollback drilldown / runtime receipts` 串成同一条 account-first 调查路径
  - `/app` Ops 面板新增 `Unified Investigation`，可直接输入 `account_id`，再按 `world_version_id / case_id` drill-down 并导出 JSON trace bundle
- Ops 现已补 `Alert Center`：
  - `GET /v1/ops/alerts`
  - `GET /v1/ops/alerts/{alert_id}`
  - `POST /v1/ops/alerts/{alert_id}/status`
  - 把 `runtime incident / support issue / governance case+restriction / async job incident` 聚成统一主动告警 feed
  - 每条 alert 都会给出 `recommended_actions / standard_operating_path / investigation_ref`
  - `/app` Ops 面板新增 `Alert Center`，支持筛选、acknowledge、resolve，并可一键把 alert prefill 到 `Unified Investigation`
- Author API 已具备 Draft CRUD / Validate / Simulate / Submit for Review，并已补 collaboration / approval / compare 基础能力
- Author collaboration 现已继续补 reviewer inbox / in-app notifications / `@mention` workflow，可对 comment threads、approval request 与 approval decision 做最小路由
- Author collaboration 现已继续补 inline thread reply / watcher / inbox filters / bulk notification status / async notification mirror
- Author collaboration 现已继续补 header-based identity shim / draft watcher / inbox cursor + search / notification preferences / thread-update throttling
- Author collaboration 现已继续补 `/v1/auth register/login/me/logout`、bearer token auth、独立 Notification Settings panel 与 per-user email/slack routing stub
- Author API 已补 `brief-template` 与 `drafts/from-brief`
- Ops API 已具备 Review Queue / Publish / Rollback / World Status / Meter 查询
- Ops API 已补 `/v1/ops/worlds/{world_id}/history`
- Ops API 已补 `/v1/ops/worlds/{world_id}/release-workspace`
- Ops `world status` 现已返回 richer `publish_checklist / recent_reviews / recent_entitlement_events / risk_summary`
- Ops `world status` 现已把 publish gate 补成 drill-down contract：
  - `publish_checklist_summary`
  - `publish_checklist[*].owner / severity / next_action / evidence`
  - `recent_reviews_drilldown`
- Ops `world history` 现已补：
  - `review_timeline`
  - `review_summary`
  - `rollback_drilldown`
  - `rollback_summary`
  - `quality_trend_summary`
- content release 线现已补 `Content Release Workspace`：
  - 统一返回：
    - `release_summary`
    - `publish_blockers`
    - `review_ownership_summary`
    - `version_matrix`
    - `rollback_workspace`
    - `action_pack`
    - `investigation_summary`
    - `operator_timeline`
  - `/app` 中新增 `发布 / Checklist / 回滚统一处置页`
  - operator 现在可以围绕一个 `world_id` 先看：
    - 能不能发
    - 为什么不能发
    - 谁在 owner 当前 blocker
    - 最近 review / rollback 轨迹
    - 下一步能直接按什么动作
- Ops 顶层现已补 `GET /v1/ops/navigation-model`
  - 统一接收 `account_id / world_id / case_id / alert_id`
  - 输出：
    - `active_context`
    - `context_resolution`
    - `escalation_summary`
    - `linked_context`
    - `navigation_targets`
    - `follow_up_actions`
  - `/app` 顶部 `统一导航 / 升级路径` 面板现在会把 account/world/case/alert 收口到同一 shared context，再驱动各个 workspace 的 drill-down，而不是再维护多套平行输入
  - 最近又补了一轮 Ops control plane refresh hardening：
    - `refreshOpsSurface` 现已拆成 `review_release / runtime / jobs / account / alerts / learned / navigation / investigation` scopes
    - 高频动作默认只刷新对应 scope，不再总是整页 full refresh
    - 关键 workspace helper 现已加 stale-request protection，避免旧请求覆盖新状态
    - 当前 `renderOpsSurface` 也已开始按同一 scope 做 section-level 条件渲染，逐步从“大渲染函数”推进到“局部 render/update pipeline”
    - 目前 `navigation / review_release / runtime / jobs / account / investigation / learned` 已各自抽成独立 render section helper，`renderOpsSurface` 主要只负责 scope dispatch
    - 这些 Ops render section 现已物理迁到独立前端脚本 `ops_render_sections.js`，`app.js` 更接近只保留 state / refresh orchestration / action handlers
    - 现在 `ops_refresh.js / ops_actions.js / ops_render_sections.js / app.js` 已形成更清晰的前端分层：
      - `ops_refresh.js`：shared context + scope refresh orchestration
      - `ops_actions.js`：Ops navigation / governance / account / release / jobs action handlers
      - `ops_render_sections.js`：Ops section render helpers
      - `app.js`：全局 state、Reader/Author 主线、事件绑定与总装配
    - 现已补 `tests/test_ops_frontend_split.py`，直接锁 `/app` 的脚本加载顺序与 refresh/action/render/app 四层职责边界
- Ops `eval-metrics` 现已可返回 learned-vs-rule 摘要与继续读相关性：
  - `online_continuation_correlation`
  - `continuation_signal_summary`
  - `quality_signal_correlations`
  - `continuation_world_details`
  - `continuation_version_details`
  - `continuation_sample_accumulation`
  - `learned_eval_available`
  - `learned_rule_agreement_rate`
  - `top_mismatch_worlds`
  - `top_mismatch_issue_codes`
  - `learned_shadow_summary`
  - `learned_reranker_shadow_summary`
- 内置 Web 前端 `/app` 现已包含 `Reader / Author / Ops` 三端骨架
- Author 端已不再只支持复制当前世界，也支持从题材预设与 freeform brief 直接生成新 world pack draft
- Reader 主区已不再只显示单章，而是连续追加式 Story Feed
- Reader 现在会直接解释：
  - 为什么可读 / 不可读
  - 当前世界是否已解锁
  - 剩余 credits
- `继续旅程` 书架现在支持删除多余 session
- demo 世界已扩容到更长的中段路线，单路线可稳定支撑 8-12 章节以上
- 已生成一个对应的 Figma 设计文件，方便继续做视觉迭代
- analytics 事件口径现已统一覆盖：
  - `session_created`
  - `continue_story`
  - `payment_required`
  - `credits_consumed`
  - `entitlement_granted`
  - `publish_blocked`
  - `rollback_performed`
- `eval/learned_baseline.py` 现已支持：
  - 读取 `dataset_view=evaluator`
  - 训练 scikit-learn baseline
  - 写出 `model.joblib / metrics.json / training_manifest.json`
- `eval/learned_inference.py` 现已支持：
  - 从 `artifacts/learned_evaluator_baseline` 自动加载 artifact
  - 对 evaluator examples 做并行预测
  - 输出 `agreement_rate / mismatch_examples / top_mismatch_worlds / top_mismatch_issue_codes`
- `eval/learned_shadow.py` 现已支持：
  - 结合 artifact 与 live disagreement 产出 `learned_shadow_summary`
  - 输出 `status / warnings / recommended_next_action`
- `eval/learned_reranker_baseline.py` 现已支持：
  - 读取 `dataset_view=reranker`
  - 训练 scikit-learn preference baseline
  - 写出 `reranker_model.joblib / reranker_metrics.json / reranker_training_manifest.json`
- `eval/learned_reranker_shadow.py` 现已支持：
  - 结合 reranker artifact 与 pair coverage 产出 `learned_reranker_shadow_summary`
  - 输出 `status / warnings / recommended_next_action`
- `eval/learned_compare.py` 现已支持：
  - 对 evaluator / reranker 的 shadow readiness 做统一对比
  - 输出 `preferred_shadow_candidate / disagreement_worlds / disagreement_issue_codes`
- `eval/learned_data_ops.py` 现已支持：
  - 把 learned dashboard / compare / backlog 聚成可执行的 Ops 数据扩充工作流
  - 输出 `review_sample_backlog / pair_coverage_backlog / action_queue`
- `eval/learned_review_quality.py` 现已支持：
  - 聚合 `human review coverage / reviewer diversity / ingestion warning / reference validation`
  - 输出 `high-coverage replenishment backlog`
  - 提供 world 级 review quality drill-down
- `eval/learned_data_impact.py` 现已支持：
  - 对单次 human review capture 计算 before / after impact receipt
  - 输出 `preferred_shadow_candidate / backlog count / next action` 的即时变化
- `eval/learned_impact.py` 现已支持：
  - 聚合 evaluator / reranker 的 learned impact summary
  - 分开输出 `retention proxy` 与 `monetization proxy`
  - 提供 `world / issue` 级 impact drill-down
  - 对 `assisted_gate` experiment receipts 额外输出 experiment-aware retention / monetization correlation
  - 让 Ops 直接看到 `assisted block` 是否和 continuation / checkout / subscription / paywall proxy 同步变化
- `eval/learned_cadence.py` 现已支持：
  - 把 `data coverage / latest training / shadow validation / promotion approval / rollout` 聚成统一 cadence 视图
  - 输出每条 learned track 当前所处的 `collect_data / train_candidate / validate_shadow / request_promotion / ready_to_activate / monitor_active / rebuild_readiness`
  - 额外输出 `cadence_health / stale_reasons / checkpoint_summary / recent_events`
  - 提供 per-track cadence detail，且不改变现有 promotion / rollout gate
- `eval/learned_assisted_gate.py` 现已支持：
  - `shadow_only -> assisted_gate` 的受控实验 config / summary / decision receipt
  - 仅在 `evaluator rollout active + promotion approved + bucket 命中` 时允许极窄的 assisted block
  - 明确禁止 learned force-pass 一个 rule-blocked version
  - 输出 `recent decisions / guardrails / rollback conditions`
- `eval/learned_assisted_rerank.py` 现已支持：
  - `shadow_only -> assisted_rerank` 的受控实验 config / summary / decision receipt
  - 在 Reader runtime 的候选排序链路里，只对 `beat 1` 做可回滚的 top-candidate assisted rerank
  - 仅在 `reranker rollout active + promotion approved + bucket 命中 + score gap 足够小` 时允许重排
  - 输出 `recent decisions / guardrails / rollback conditions`
- `eval/learned_promotion.py` 现已支持：
  - 基于 evaluator shadow / compare / data ops 计算 recommendation-only promotion summary
  - 输出 `status / blockers / advisories / checklist / evidence`
- `eval/learned_training_automation.py` 现已支持：
  - 一次性运行 evaluator / reranker / both baseline training
  - 产出 per-track training result
  - 生成 `promotion evidence pack`
  - 在 training result 与 evidence pack 中附带 cadence snapshot
  - 写入 run summary artifact
- `eval/learned_rollout.py` 现已支持：
  - `shadow -> active -> rolled_back` 的最小 rollout 状态机
  - rollout safety 依赖 `shadow compare + promotion approval`
  - active rollout watchlist 与 rollback recommendation
- `eval/learned_promotion_workflow.py` 现已支持：
  - 复用 `review_records` 为 evaluator promotion 叠加人工批准/撤销状态
  - 输出 `recommendation_status / approval_status / reconfirm_required / latest_approval_record`
- `eval/learned_reranker_promotion.py` 现已支持：
  - 基于 reranker shadow / compare / data ops 计算 recommend-only promotion summary
  - 输出 `status / blockers / advisories / checklist / evidence`
- `eval/learned_reranker_promotion_workflow.py` 现已支持：
  - 复用 `review_records` 为 reranker promotion 叠加人工批准/撤销状态
  - 输出 `recommendation_status / approval_status / reconfirm_required / latest_approval_record`
- `services/monetization.py` 现已支持：
  - tier config 读取
  - entitlement matrix 读取
  - config snapshot 输出
  - subscription lifecycle
  - lifecycle reconcile（`active/trialing -> past_due/expired`）
  - reactivation renew + wallet refill
  - web-first checkout stub
  - monthly wallet refill
- `services/billing.py` 现已支持：
  - Reader / Author metering 统一走 entitlement matrix
  - `usage_units` 对齐实际 charged credits
  - `model_policy_version` 记录 `config_version:metering_rule`
  - subscription-backed continue 会记录 `0` credits metered，而不是伪装成 credit 消耗
  - Reader / Author gating payload 会直接暴露 `required_display_name / required_capability / required_units / suggested_checkout_tier`
- Ops API 已补最小离线导出入口：
  - `GET /v1/ops/export/training-signal`
- Ops API 已补：
  - `POST /v1/ops/review-samples`
  - `GET /v1/ops/review-samples`
  - `GET /v1/ops/review-sample-backlog`
  - `GET /v1/ops/issue-fix-pair-backlog`
  - `GET /v1/ops/issue-fix-pairs`
  - `GET /v1/ops/learned-dashboard`
  - `GET /v1/ops/learned-dashboard/worlds/{world_id}`
  - `GET /v1/ops/learned-dashboard/issues/{issue_code}`
  - `GET /v1/ops/learned-compare`
  - `GET /v1/ops/learned-impact`
  - `GET /v1/ops/learned-impact/worlds/{world_id}`
  - `GET /v1/ops/learned-impact/issues/{issue_code}`
  - `GET /v1/ops/learned-cadence`
  - `GET /v1/ops/learned-cadence/{track}`
  - `GET /v1/ops/learned-assisted-gate`
  - `POST /v1/ops/learned-assisted-gate/configure`
  - `GET /v1/ops/learned-assisted-rerank`
  - `POST /v1/ops/learned-assisted-rerank/configure`
  - `GET /v1/ops/learned-data-ops`
  - `GET /v1/ops/learned-review-quality`
  - `GET /v1/ops/learned-review-quality/worlds/{world_id}`
  - `GET /v1/ops/learned-promotion`
  - `GET /v1/ops/learned-reranker-promotion`
  - `POST /v1/ops/learned-training/run`
  - `GET /v1/ops/learned-promotion-evidence`
  - `GET /v1/ops/learned-rollout`
  - `POST /v1/ops/learned-rollout/{track}/activate`
  - `POST /v1/ops/learned-rollout/{track}/rollback`
  - `GET /v1/ops/runtime-receipts`
  - `GET /v1/ops/runtime-incident-snapshot`
  - `GET /v1/ops/provider-routing`
  - `GET /v1/ops/provider-rollout`
  - `POST /v1/ops/provider-rollout/{track}/canary`
  - `POST /v1/ops/provider-rollout/{track}/activate`
  - `POST /v1/ops/provider-rollout/{track}/rollback`
  - `GET /v1/ops/provider-runtime-metrics`
  - `GET /v1/ops/deployment-runbook`
  - `GET /v1/ops/deployment-health-gate`
  - `GET /v1/ops/preflight-verification-bundle`
  - `GET /v1/ops/incident-playbook`
  - `GET /v1/ops/recovery-drills`
  - `GET /v1/ops/runtime-restore-requests`
  - `GET /v1/ops/jobs`
  - `GET /v1/ops/jobs/incidents`
  - `GET /v1/ops/jobs/boot-reconcile`
  - `GET /v1/ops/jobs/artifact-retention`
  - `GET /v1/ops/jobs/operator-history`
  - `GET /v1/ops/jobs/notification-sinks`
  - `GET /v1/ops/jobs/adapter-config-validation`
  - `GET /v1/ops/jobs/adapter-health-probe`
  - `GET /v1/ops/jobs/retry-policies`
  - `GET /v1/ops/jobs/notification-delivery-receipts`
  - `GET /v1/ops/jobs/notification-delivery-receipts/{event_id}`
  - `GET /v1/ops/jobs/notification-retry-queue`
  - `GET /v1/ops/jobs/notification-dead-letter-queue`
  - `GET /v1/ops/jobs/retry-outcome-dashboard`
  - `GET /v1/ops/jobs/handoff-bundle`
  - `GET /v1/ops/jobs/remote-shipping`
  - `GET /v1/ops/jobs/handoff-sla`
  - `POST /v1/ops/jobs/handoff-bundle/export`
  - `POST /v1/ops/jobs/handoff-sla/escalate`
  - `POST /v1/ops/jobs/notification-retry-queue/enqueue`
  - `POST /v1/ops/jobs/enforce-retention`
  - `POST /v1/ops/jobs/cold-start-drill`
  - `GET /v1/ops/jobs/{job_id}`
  - `POST /v1/ops/jobs/{job_id}/acknowledge`
  - `POST /v1/ops/jobs/{job_id}/ship-remote`
  - `POST /v1/ops/jobs/notification-retry-queue/{retry_id}/process`
  - `POST /v1/ops/jobs/{job_id}/retry`
  - `POST /v1/ops/jobs/{job_id}/resume`
  - `POST /v1/ops/jobs/learned-training`
  - `POST /v1/ops/jobs/runtime-backups`
  - `POST /v1/ops/jobs/recover-incidents`
  - `POST /v1/ops/runtime-backups`
  - `POST /v1/ops/runtime-restore`
  - `POST /v1/ops/recovery-drill`
  - `POST /v1/ops/runtime-restore/request`
  - `POST /v1/ops/runtime-restore/{request_id}/approve`
  - `POST /v1/ops/runtime-restore/{request_id}/revoke`
  - `POST /v1/ops/jobs/runtime-restores`
  - `POST /v1/ops/learned-promotion/approve`
  - `POST /v1/ops/learned-promotion/revoke`
  - `POST /v1/ops/learned-reranker-promotion/approve`
  - `POST /v1/ops/learned-reranker-promotion/revoke`
  - `GET /v1/ops/subscriptions`
  - `GET /v1/ops/entitlements`
  - `POST /v1/ops/subscriptions/grant`
  - `POST /v1/ops/subscriptions/state`
  - `POST /v1/ops/subscriptions/{subscription_id}/reconcile`
  - `POST /v1/ops/subscriptions/{subscription_id}/retry-payment`
  - `POST /v1/ops/billing-events/{event_id}/replay`
  - `POST /v1/ops/wallets/grant`
  - `POST /v1/ops/wallets/debit`
- Reader API 已扩展：
  - `GET /v1/reader/subscription`
  - `POST /v1/reader/checkout/start`
  - `POST /v1/reader/checkout/webhook`
  - `POST /v1/reader/subscription/{account_id}/retry-payment`
  - `POST /v1/reader/subscription/{account_id}/renew`
  - `POST /v1/reader/subscription/{account_id}/cancel`
- `/app` 的 Ops 区现已补：
  - `Evaluator Promotion Gate`
  - `Reranker Promotion Gate`
  - `Training Automation`
  - `Async Jobs`
  - `Runtime Receipts / Incident Snapshot`
  - `Provider Runtime Metrics`
  - `Deployment / Backup / Incident`
  - `Deployment Health Gate`
  - `Last Action Impact`
  - `Monetization` audit panel
  - 用于展示一次 human review 提交后，对 backlog / compare / next action 的即时影响
- `specs/` 现已新增：
  - `review_sample.schema.json`
  - `author_revision_log.schema.json`
  - `continue_churn_event.schema.json`
  - `training_signal_bundle.schema.json`
  - `issue_fix_pair.schema.json`
- `training_signal_bundle` 现已包含：
  - `manifest`
  - `pack_quality_trends`
  - `next_cursor`
  - `evaluator_examples`
  - `reranker_examples`
  - `analytics_examples`
  - `manifest.warnings`
  - `rollback_performed`
- `promotion evidence pack` 现已聚合：
  - artifact state
  - learned dashboard summary
  - compare summary
  - data ops summary
  - promotion summary
  - promotion workflow
  - analysis report
- Phase 6 现已补 `long-running jobs + async workflow skeleton`：
  - 通过 `FastAPI BackgroundTasks + review_records` 复用现有持久层，不引入外部队列
  - 当前已接入两个真实长任务入口：
    - `learned_training`
    - `runtime_backup`
  - `/v1/ops/jobs` 会返回队列摘要、每个 job 的 `queued / running / succeeded / failed` 状态与 workflow steps
- Phase 6 现已继续补 `durable job retry / resume + async workflow incident recovery`：
  - 支持单 job `retry`、单 job `resume`
  - 支持批量 `recover-incidents`，优先恢复 `queued` 与 `stale running` jobs
  - `/v1/ops/jobs/incidents` 会返回 failed / queued / stale-running 的恢复摘要与建议动作
- Phase 6 现已继续补 `boot-time async reconciler + job heartbeat / lease model`：
  - app startup 会把 orphaned `running` jobs reconcile 回 `queued`
  - job 状态现会暴露 `lease_owner / lease_expires_at / heartbeat_at / heartbeat_count / lease_status`
  - `/v1/ops/jobs/boot-reconcile` 可查看最近一次 boot reconcile 摘要
- Phase 6 现已继续补 `async job artifact retention + operator run history`：
  - `/v1/ops/jobs/artifact-retention` 会聚合 artifact 存在性、保留天数、到期时间与缺失/过期状态
  - `/v1/ops/jobs/operator-history` 会聚合 enqueue、retry、resume、boot reconcile 等 operator 动作历史
  - `/app` 的 Async Jobs 面板现可直接看到 retention 摘要和 operator run history
- Phase 6 现已继续补 `async job cleanup / retention enforcement + cold-start recovery drill`：
  - `POST /v1/ops/jobs/enforce-retention` 可执行过期 artifact cleanup
  - `POST /v1/ops/jobs/cold-start-drill` 可做当前队列的 cold-start recovery 演练
  - `/app` 的 Async Jobs 面板现可直接触发 retention enforcement 和 cold-start drill
- Phase 6 现已继续补 `async job export / handoff bundle + operator acknowledgement flow`：
  - `GET /v1/ops/jobs/handoff-bundle` 会聚合需要交接的 async jobs 与 acknowledgement 摘要
  - `POST /v1/ops/jobs/handoff-bundle/export` 会写出 handoff bundle artifact
  - `POST /v1/ops/jobs/{job_id}/acknowledge` 可记录 operator acknowledgement
- Phase 6 现已继续补 `async job remote artifact shipping + handoff SLA escalation skeleton`：
  - `GET /v1/ops/jobs/remote-shipping` 会汇总 remote shipping 状态
  - `POST /v1/ops/jobs/{job_id}/ship-remote` 会把 job artifacts 复制到 remote stub 目录并写 shipping manifest
  - `GET /v1/ops/jobs/handoff-sla` 会汇总 overdue / pending handoff 状态
  - `POST /v1/ops/jobs/handoff-sla/escalate` 会对 overdue handoff 做 SLA escalation skeleton 记录
- Phase 6 现已继续补 `async adapter config validation + notification delivery receipt drill-down`：
  - `GET /v1/ops/jobs/adapter-config-validation` 会校验默认 remote adapter / notification sink 是否注册且路径可写
  - `GET /v1/ops/jobs/notification-delivery-receipts` 会汇总 notification delivery receipts、target path 是否存在与 event type 分布
  - `GET /v1/ops/jobs/notification-delivery-receipts/{event_id}` 可查看单条 receipt 的 target payload preview
- Phase 6 现已继续补 `async adapter health probe + notification retry queue skeleton`：
  - `GET /v1/ops/jobs/adapter-health-probe` 会输出 adapter/sink probe 状态
  - `GET /v1/ops/jobs/retry-policies` 会输出 notification retry policy registry
  - `GET /v1/ops/jobs/notification-retry-queue` 会汇总 notification retry queue
  - `POST /v1/ops/jobs/notification-retry-queue/enqueue` 可把 delivery receipt 入重试队列
  - `POST /v1/ops/jobs/notification-retry-queue/{retry_id}/process` 可执行最小 retry skeleton
- Phase 6 现已继续补 `async dead-letter queue + retry outcome dashboard`：
  - `GET /v1/ops/jobs/notification-dead-letter-queue` 会汇总 terminal failures
  - `GET /v1/ops/jobs/retry-outcome-dashboard` 会汇总 retry success / planned / terminal failure 与 failure class 分布
- Phase 6 现已继续补 `async retry policy registry + adapter failure classification`：
  - retry queue 现在会记录 `retry_policy_id / retry_policy / failure_classification / retry_decision / next_retry_at`
  - adapter 失败会按 `configuration / permission / missing_resource / timeout / transient_io / rate_limited / unsupported / unknown` 分类
  - retry 决策现在由 policy registry 驱动，而不是单纯成功/失败二分
- `shadow compare` 现已补 rollout hardening：
  - `rollout_readiness`
  - `safe_rollout_candidates`
- `/app` 的 Learned 区现已补 `Safe Rollout` 卡片，可直接查看 active tracks、safe candidates、rollback watchlist，并触发 activate / rollback
- `review sample ingestion` 现已补硬化：
  - `world_id / world_version_id / session_id / revision_id` 引用校验
  - `issue_codes / linked_issue_codes` 规范化
  - human review 默认按 stable ingestion key upsert，避免同一 logical sample 无限重复
  - `ingestion_meta` 会记录 `reference_status / storage_mode / ingestion_warnings`
- `issue-fix pair pipeline` 现已补 richer contract：
  - `before_review_sample_ids / after_review_sample_ids`
  - `review_coverage_count / human_review_count`
  - `pair_source / pair_quality / pair_warnings`
  - backlog 会额外输出 `effective_coverage_count`

### 当前未做

- 真实供应商的 LLM 接入仍保留为可替换 backend 接口，没有默认绑定具体厂商
- provider boundary 已存在：
  - `AnthropicProvider`
  - `OpenAIProvider`
  - `LocalRuleBasedProvider`
- provider routing / retry / fallback skeleton 现已补：
  - `RetryingLLMBackend`
  - `RoutingLLMBackend`
  - `CachedLLMBackend`
  - `BudgetedLLMBackend`
  - `build_llm_backend_from_env(scope=...)`
  - `build_llm_policy_from_env(scope=...)`
  - `ProviderRoutingService`
  - `LLMCandidateProvider` / `LLMRenderer` 会暴露 `backend_routing` debug
  - Reader `continue_story` 与 Authoring `run_simulation_for_world_version` 现已接入统一的 candidate / renderer runtime
  - primary provider 失败、budget blocked、或 retry 后仍失败时，会自动走 static candidate / template renderer fallback
  但默认开发与 benchmark 仍以 deterministic / local 路径为主
- provider runtime metrics / cost trend 现已补：
  - `provider_summary`
  - `cost_trend`
  - `latency_summary`
  - `latency_trend`
  - `rollout_stage_summary`
  - `surface_summary`
  - `action_summary`
  - `selected_as_candidate_count / selected_as_renderer_count`
  - `avg/p95 runtime / candidate / renderer latency`
  - `candidate_estimated_request_cost / renderer_estimated_request_cost`
- Postgres schema 已进入根仓库 `db/postgres_schema.sql`，但本地默认仍以 SQLite fallback 跑测试与开发
- Postgres migration / schema lifecycle 现已补：
  - `schema_sql_fingerprint`
  - `migrations_fingerprint`
  - `inspect_schema_lifecycle`
  - `bootstrap_schema_lifecycle`
  - `bootstrap_postgres_runtime(..., dry_run=True)`
  - Alembic scaffold:
    - `alembic.ini`
    - `db/alembic/env.py`
    - `db/alembic/versions/20260404_0011_platform_baseline.py`
    - `db/alembic/versions/20260404_0012_runtime_hotspot_indexes.py`
  - Alembic lifecycle signals:
    - `current_revision`
    - `head_revision`
    - `pending_revisions`
    - `status`
- data integrity / repair 现已补：
  - hotspot composite index coverage summary
  - session pointer drift detection
  - orphan route choice detection
  - duplicate active subscription detection
  - safe dry-run / apply repair actions
- runtime ops / runbook 现已补：
  - sqlite backup / restore
  - deployment runbook
  - deployment health gate
  - preflight verification bundle
  - incident playbook
  - recovery drill dry-run artifact
  - restore decision hints + pre/post restore verification
  - Postgres restore request / approve / revoke workflow
  - Postgres `pg_dump` / `pg_restore` / `psql` wrapper execution with result artifacts
  - runtime observability receipts 联动
- Author / Ops 前端目前是最小产品骨架，还不是完整工作台
- 真实支付、鉴权、内容审核外部服务、模型路由策略仍是占位骨架
- 当前 core 已基本清除 Jade Court pack-specific prose hardcode，但 world pack 资产和 benchmark 仍需要继续丰富，才能让 4+ packs 同时受益

## 你拿到的内容

- `docs/`：产品范围、算法设计、API 合约、评测与风控说明
  - 其中 canonical handoff 文档是：
    `docs/gpt_handoff_status_and_commercialization.md`
- `specs/`：Alpha schema + 平台化 `worldpack / scene_plan / character_profile / route_offer / billing_meter / content_review` schema
- `db/`：`postgres_schema.sql`
- `contracts/`：Python / TypeScript 契约草案
- `legacy/`：此前 Alpha 与 Karma 相关历史方案
- `configs/`：评分权重、策略示例
- `prompts/`：规划器、角色器、批评器、渲染器 Prompt 模板
- `examples/`：Alpha 示例世界 + `examples/worldpacks/` 多 pack 资产
- `src/narrativeos/`：当前 Beta Kernel 实现
- `tests/`：Alpha 回归 + Beta 平台化骨架测试
- `TASKS_FOR_CODEX.md`：原始执行清单
- `CODEX_HANDOFF_PROMPT.md`：原始交接 prompt

## 设计原则

1. **状态先于文本**：先维护世界、人物、关系、承诺与张力，再生成文本。
2. **事件先于段落**：系统搜索“下一步发生什么事件”，而不是直接续写下一段。
3. **分支不是树，而是带疤痕的 DAG**：允许汇合，但要保留关系、资源、秘密、伤痕等后果。
4. **显式评分函数**：不要把“好剧情”完全托付给模型感觉。
5. **多 critic 回路**：一致性、戏剧推进、多样性都要单独检查。
6. **创作者可控**：通过 canon anchors / forbidden moves / theme targets 等参数控制作品灵魂。

## 快速启动

推荐做法：

```bash
cd narrativeos_codex_handoff
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m src.narrativeos.demo
```

如果要跑 API：

```bash
source .venv/bin/activate
uvicorn src.narrativeos.api:app --reload
```

前端入口：

```text
http://127.0.0.1:8000/app
```

Ops navigation stale-ref remediation browser smoke：

```bash
bash scripts/run_ops_navigation_stale_ref_smoke.sh
```

它会 seed 一份 deterministic stale-ref 场景，并验证：
- stale warning 出现
- `Re-sync From Valid Context`
- `Clear Stale Refs`

CI / headless 模式：

```bash
CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_ops_navigation_stale_ref_smoke.sh
```

如果要显式指定 SQLite fallback：

```bash
source .venv/bin/activate
export DATABASE_URL=sqlite:///narrativeos_beta.db
uvicorn src.narrativeos.api:app --reload
```

如果要启用 provider routing skeleton：

```bash
source .venv/bin/activate
export NARRATIVEOS_LLM_ROUTING_ENABLED=true
export NARRATIVEOS_LLM_PROVIDER_ORDER=openai,anthropic,local
export NARRATIVEOS_LLM_MAX_ATTEMPTS=2
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
uvicorn src.narrativeos.api:app --reload
```

Postgres-first 开发时，请先应用 `db/postgres_schema.sql`，再把仓库层改为对应 DSN。

更完整的 Postgres 初始化方式：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --seed-builtins
```

只检查 schema lifecycle，不实际 apply migrations：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --dry-run
```

查看 Alembic current/head：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --alembic-current
```

查看 Alembic revision history：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations --alembic-history
```

如果已有 Postgres schema 需要正式 stamp 到当前 Alembic head，继续走标准 bootstrap：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos'
```

如果未来新增 forward Alembic revisions，可以显式执行：

```bash
source .venv/bin/activate
python -m src.narrativeos.persistence.migrations \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --alembic-upgrade-head
```

检查数据完整性与 repair backlog：

```bash
source .venv/bin/activate
python -m src.narrativeos.services.data_integrity \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos'
```

只对 safe actions 做 dry-run：

```bash
source .venv/bin/activate
python -m src.narrativeos.services.data_integrity \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --action reconcile_session_chapter_pointers \
  --action prune_orphan_route_choices
```

应用 safe repair：

```bash
source .venv/bin/activate
python -m src.narrativeos.services.data_integrity \
  --database-url 'postgresql://user:password@localhost:5432/narrativeos' \
  --apply \
  --action reconcile_session_chapter_pointers \
  --action prune_orphan_route_choices
```

NarrativeEval nightly / regression 调用方式：

```bash
source .venv/bin/activate
python -m src.narrativeos.eval.regression \
  --worldpack all \
  --golden-dir tests/golden_routes \
  --database-url sqlite:///narrativeos_beta.db
```

Learned evaluator baseline 调用方式：

```bash
source .venv/bin/activate
python -m src.narrativeos.eval.learned_baseline \
  --dataset-view evaluator \
  --world-id urban_mystery_lotus_lane \
  --output-dir tmp/learned_evaluator_baseline \
  --database-url sqlite:///narrativeos_beta.db
```

Learned reranker baseline 调用方式：

```bash
source .venv/bin/activate
python -m src.narrativeos.eval.learned_reranker_baseline \
  --dataset-view reranker \
  --world-id urban_mystery_lotus_lane \
  --output-dir tmp/learned_reranker_baseline \
  --database-url sqlite:///narrativeos_beta.db
```

Shared learned analysis 调用方式：

```bash
source .venv/bin/activate
python -m src.narrativeos.eval.learned_analysis \
  --world-id urban_mystery_lotus_lane \
  --evaluator-artifact-dir artifacts/learned_evaluator_baseline \
  --reranker-artifact-dir artifacts/learned_reranker_baseline \
  --output-dir tmp/learned_analysis \
  --database-url sqlite:///narrativeos_beta.db
```

Kernel-first cross-pack benchmark：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack all \
  --golden-dir tests/golden_routes \
  --baseline-file tests/benchmark_baseline.json \
  --database-url sqlite:///narrativeos_beta.db \
  --markdown-out artifacts/cross_pack_benchmark_summary.md
```

报表 JSON 现至少包含：

- 顶层：
  - `benchmark_mode`
  - `chapter_budget`
  - `worlds`
  - `cross_pack_pass_rate`
  - `strongest_packs`
  - `weakest_packs`
  - `top_failing_packs`
  - `weakest_pack_diagnostics`
  - `delta_summary`
- 每个 `worlds[*]`：
  - `completion_ratio`
  - `stop_reason`
  - `issue_mix`
  - `long_route_quality`
  - `mid_arc_drop`
  - `dialogue_distinctness`
  - `diagnostic_score`
  - `diagnostic_rank`
  - `top_issue_categories`
  - `dimension_scores`
  - `issue_summary`

同时 CLI 支持把人工可读报表写到 `--markdown-out` 指定路径，便于在本地或 PR 附件里直接查看 strongest / weakest packs 与 benchmark delta。
其中 `weakest_pack_diagnostics` 会继续下钻 weakest packs，补出：

- `worst_chapters`
- `issue_category_distribution`
- `attribution_map.modules / assets / policies`
- `next_fix_candidates`

Long-route benchmark（30–50 章压力测试）：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack all \
  --golden-dir tests/golden_routes \
  --baseline-file tests/long_route_benchmark_baseline.json \
  --database-url sqlite:///narrativeos_beta.db \
  --max-chapters 36 \
  --min-end-turn-override 30 \
  --markdown-out artifacts/long_route_benchmark_summary.md
```

long-route 模式会额外输出：

- `benchmark_mode = long_route`
- `completion_ratio / stop_reason / premature_ending`
- `avg_repetition_score / avg_exposition_ratio / avg_hook_quality`
- `mid_arc_pass_rate / late_arc_pass_rate`
- top-level `long_route_summary`

当 `min_end_turn` 被拉高到 long-route 级别时，静态 provider 现在会启用一层 kernel-level continuation candidates：

- 只在 long-route 语境补充续航事件，不改标准 6 章基线
- continuation candidates 复用现有 pack actors / tags / contracts，但使用新的 event ids，避免 event pool 被一次性耗尽
- continuation candidates 会移除 terminal metadata，并按 phase 轮换 scene function / promise / seed / location
- 这样 long-route benchmark 更接近“内容是否还能继续读”，而不是过早停在 `no_legal_routes`

Q03 / Q04 / Q05 / Q09 remediation framework：

- `Q03`
  - generic repetition variation pass on repaired drafts
- `Q04`
  - exposition guard that injects more scene-facing dialogue pressure when drafts are too summary-like
- `Q05`
  - detail reinforcement pass that adds concrete sensory grounding when density is too thin
- `Q09`
  - stronger hook reinforcement plus phase-aware terminal scene penalty before `min_end_turn`

Cross-pack merge gate：

```bash
source .venv/bin/activate
scripts/run_cross_pack_merge_gate.sh
```

如果要在本地连同 PR 证据一起校验，可额外提供：

```bash
PR_BODY_FILE=/absolute/path/to/pr-body.md scripts/run_cross_pack_merge_gate.sh
```

merge gate 当前会阻断：

- `cross_pack_pass_rate` 回退
- benchmark `regressions` 非空
- PR 缺少 `strongest pack delta / weakest pack delta / cross-pack pass-rate delta / rollback point`
- PR 缺少 `Goal met / Out-of-scope changes introduced / commercialization / kernel-vs-current-pack polish` 等纪律字段
- `Does this improve kernel/product/ops instead of just current-pack polish? = no`

Phase 0 guardrails：

```bash
source .venv/bin/activate
bash scripts/run_phase0_guardrails.sh
```

当前会强制检查：

- root + nested `AGENTS.md` 存在
- `.github/pull_request_template.md` 持续保留 commercialization / kernel-first 纪律字段
- `src/narrativeos/core/` 与 `rendering.py` 不得导入 `worldpacks`
- benchmark-enabled published `world_id` 不得硬编码进 `core/` 或 `rendering.py`
- `README.md` 持续引用 benchmark sample
- `tests/cross_pack_benchmark_summary.md` 作为受版本控制的 benchmark markdown baseline，与当前 benchmark 生成结果保持同步

benchmark `--worldpack all` 当前已改为 registry-driven：

- 来源是 `FileSystemWorldRegistry().list_benchmark_worldpacks()`
- 只覆盖 `catalog_role = published` 且 `benchmark_enabled = true` 的 world packs
- Author 模板资产 `world_template_minimal.json` 会继续保留，但不会混入 benchmark / regression 的 `all` 集合

## API 概览

- `GET /health`
- `GET /app`
- `GET /v1/examples`
- `GET /v1/examples/{example_id}`
- `GET /v1/examples/demo`
- `GET /v1/worlds`
- `POST /v1/worlds`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `DELETE /v1/sessions/{session_id}`
- `POST /v1/sessions`
- `POST /v1/sessions/{session_id}/step`
- `GET /v1/sessions/{session_id}/replay`
- `POST /v1/routes/preview`
- `GET /v1/library/worlds`
- `GET /v1/library/worlds/{world_id}`
- `POST /v1/reader/sessions`
- `POST /v1/reader/continue`
- `GET /v1/reader/sessions/{session_id}/quote`
- `GET /v1/reader/entitlements`
- `POST /v1/reader/entitlements/grant`
- `GET /v1/reader/sessions/{session_id}/replay`
- `GET /v1/author/drafts`
- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/auth/me`
- `POST /v1/auth/logout`
- `GET /v1/author/brief-template`
- `POST /v1/author/drafts`
- `POST /v1/author/drafts/from-brief`
- `POST /v1/author/drafts/validate`
- `POST /v1/author/drafts/{world_version_id}/simulate`
- `POST /v1/author/drafts/{world_version_id}/submit`
- `GET /v1/author/workflow`
- `GET /v1/author/drafts/{world_version_id}/collaboration`
- `GET /v1/author/reviewer-inbox`
- `GET /v1/author/notification-preferences`
- `POST /v1/author/drafts/{world_version_id}/comments`
- `POST /v1/author/comments/{thread_id}/reply`
- `POST /v1/author/comments/{thread_id}/status`
- `POST /v1/author/comments/{thread_id}/watchers`
- `POST /v1/author/comments/{thread_id}/watchers/{watcher_id}/remove`
- `POST /v1/author/drafts/{world_version_id}/watchers`
- `POST /v1/author/drafts/{world_version_id}/watchers/{watcher_id}/remove`
- `POST /v1/author/drafts/{world_version_id}/approval/request`
- `POST /v1/author/drafts/{world_version_id}/approval/decision`
- `POST /v1/author/notifications/{notification_id}/status`
- `POST /v1/author/notifications/bulk-status`
- `POST /v1/author/notification-preferences`

Author draft detail / simulate 现在还会直接暴露：

- `diff_drilldown`
  - 每个 revision 的结构化 diff summary
  - 角色 / 场景 / capability 改动明细
  - revision compare 与 simulation delta
  - `section_change_counts / recommended_next_actions / simulation_freshness`
- `simulation_drilldown`
  - `issue_histogram / module_histogram`
  - `decision_histogram / story_phase_histogram / scene_function_histogram`
  - `issue_focus_queue`
  - `weakest_chapters`
  - `chapter_breakdown`
  - `quality_pass_summary`
  - `chapter_trace`
  - `next_actions`
- `validation_drilldown`
  - `blockers / warning_groups / next_actions`
- `revision_compare`
  - latest revision vs previous revision 的结构与 simulation delta 对照
- `before_after_chapter_compare`
  - latest simulation vs previous simulation 的章节前后对照
- `collaboration`
  - anchored comments / blocking threads / latest approval state
  - `queue_summary / assignee_queues / threads_by_anchor / notification_summary`
  - thread payload 现会带 `messages / watchers / watcher_ids / notifications`
  - collaboration summary 现会带 `draft_watcher_summary`
- `reviewer_inbox`
  - assigned open threads / blocking assigned threads / pending approvals / unread notifications
  - filters: `world_version_id / status_filter / notification_type / blocking_only / cursor / q`
  - quick triage for `read / archive / resolve / approve / changes_requested`
  - bulk actions: `bulk notification status`
- `notification_preferences`
  - per actor + per event type 的 `in_app_enabled / async_mirror_enabled / async_sink_name / delivery_target`
- `auth`
  - bearer token auth 现已可用于 Author APIs
  - identity precedence: `Authorization Bearer` > `X-NarrativeOS-*` headers > legacy body fields

Author 主路径现在建议按这个顺序演示：

1. `根据 Brief 生成 Draft`
2. 查看 `主路径引导`
3. 如果 workflow 显示已自动通过当前校验，直接 `运行 Simulation`
4. 修改一处角色 / 场景 / 风格配置
5. 查看 workflow 变成 `修改后待重跑`
6. `重新运行 Simulation`
7. workflow 进入 `准备送审`
8. `送审`

面板变化说明：

- 创建后：应自动聚焦到 `Draft Detail`
- 校验/自动校验后：应在 `主路径引导` 与 `Validation` 中看到当前状态
- 模拟后：应自动聚焦到 `Simulation`
- 保存 revision 后：应自动聚焦到 `Asset Diff`，且 workflow 显示 `re_simulate`
- 送审后：应自动聚焦到 `Version History`
- `GET /v1/ops/review-queue`
- `GET /v1/ops/worlds/{world_id}/status`
- `GET /v1/ops/worlds/{world_id}/history`
- `POST /v1/ops/review-samples`
- `GET /v1/ops/review-samples`
- `GET /v1/ops/review-sample-backlog`
- `GET /v1/ops/export/training-signal`
- `POST /v1/ops/world-versions/{world_version_id}/publish`
- `POST /v1/ops/worlds/{world_id}/rollback`
- `GET /v1/ops/meters`
- `GET /v1/ops/schema-lifecycle`
- `GET /v1/ops/eval-metrics`
- `GET /v1/ops/cross-pack-quality`

`specs/openapi.yaml` 已和当前实现同步更新。

## 运行与测试结果

当前验证基线：

- `./.venv/bin/python -m pytest -q`：215 passed, 2 warnings
- `python -m src.narrativeos.demo`：可稳定运行
- `demo.py` 连跑 3 次输出稳定：默认返回 Reader Mode 章节摘要与正文预览
- `python -m src.narrativeos.benchmark.runner --baseline-file tests/benchmark_baseline.json --markdown-out artifacts/cross_pack_benchmark_summary.md`：可稳定输出 JSON + markdown summary，包含 `strongest_packs / weakest_packs / top_failing_packs / delta_summary.ranking_changes`；`tests/cross_pack_benchmark_summary.md` 保存当前受版本控制的 markdown baseline
- `python -m src.narrativeos.benchmark.runner --baseline-file tests/long_route_benchmark_baseline.json --max-chapters 36 --min-end-turn-override 30 --markdown-out artifacts/long_route_benchmark_summary.md`：可稳定输出 long-route JSON + markdown summary，包含 `long_route_summary / completion_ratio / stop_reason / mid_arc_pass_rate / late_arc_pass_rate`
- `scripts/run_cross_pack_merge_gate.sh`：可本地执行 cross-pack merge gate；GitHub Actions 的 `cross-pack-quality` workflow 也会调用同一套 gate 逻辑
- `cross-pack-quality` workflow 现已在 benchmark step 显式使用 `sqlite:///narrativeos_beta.db`，避免 CI 中 `DATABASE_URL` 缺失时 benchmark runner 直接失败
- 当前 benchmark 基线：
  `cross_pack_pass_rate = 0.933`
  strongest packs（composite diagnostic）= `jade_court_exam / xianxia_forgotten_vow`
  weakest packs（更偏诊断，不只看 pass rate）= `jade_court_romance / synthetic_min_pack / urban_mystery_lotus_lane`
  `benchmark delta = +0.000`，当前无 regressions
  weakest packs 现可直接看到 `issue_mix / long_route_quality / mid_arc_drop / dialogue_distinctness / weakest_dimensions`
  weakest diagnostics 现已补出 `worst_chapters / module-asset-policy attribution / next_fix_candidates`
  merge gate 现已要求 strongest / weakest / cross-pack delta 证据，不再只接受“某个 pack 看起来更好”
  Q03 / Q04 / Q05 / Q09 定向修复框架现已接入默认 draft 生成链
- 当前 long-route benchmark（`36 / 30`）基线：
  `cross_pack_pass_rate = 1.000`
  `avg_completion_ratio = 1.000`
  strongest packs（long-route）= `xianxia_forgotten_vow / jade_court_exam`
  weakest packs（long-route）= `jade_court_romance / urban_mystery_lotus_lane / synthetic_min_pack`
  `packs_reaching_target = urban_mystery_lotus_lane / xianxia_forgotten_vow / jade_court_exam / jade_court_romance / synthetic_min_pack`
  `premature_ending_packs = -`
  这说明 long-route survivability 已不再主要受 `no_legal_routes` 限制，当前长线弱项已从“跑不长”转向具体的 `Q03 / Q05` 内容质量残留
- 浏览器验证通过：
  `/app` 可切换 `Reader / Author / Ops`
  Reader 可切换 `Duty / Romance` worlds、创建/恢复/删除 session、预览 route、执行 step、查看 replay
  Reader 具备 `Story Feed + Sticky Composer + suggested_prefill`
  Author 可把当前世界存成 draft、触发 simulate、submit for review，并查看 `revision compare / before-after chapter compare / issue heatmap / weakest chapters / chapter breakdown / style-pacing-hook controls / collaboration / approval`
  Ops 可查看 review queue、publish、rollback、查看 metering
  Ops 可查看 `cross-pack quality`、`top failing packs`、`metric delta`

## 环境说明

- 仓库目标运行时仍建议使用 `Python >= 3.11`
- 当前这台机器实际可用的是 `python3 3.9.6`，本次验证在 `.venv` 中基于它完成
- 因此 README 保留了 3.11 目标，但如果你要复现实验结果，优先以本仓库 `.venv` 为准

## 剩余风险与下一步建议

- 最优先的下一步是把 `worldpacks/` 和 `services/` 从当前最小实现继续做深：真正接 Postgres、补 Alembic、把 review / metering / entitlement 变成生产级
- 第二优先级是继续扩容世界内容库，把单路线从 8-12 章继续拉长到更接近连载长度，并为更多角色补完整语言习惯库
- 第三优先级是把 Author / Ops 前端从最小骨架升级为真实工作台，并把 `specs/openapi.yaml` 对齐到新增 Beta 路径
- 如果要进入多人或长流程使用，下一步应补 Alembic 迁移、数据库索引、session 并发安全与 replay 查询分页
- 如果要进入创作者工作流，建议补 creator controls 的管理 API、权重可视化、phase/ending gate 编辑器和世界内容库工具

## 目录树

```text
narrativeos_codex_handoff/
├── README.md
├── TASKS_FOR_CODEX.md
├── CODEX_HANDOFF_PROMPT.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── configs/
├── docs/
├── examples/
├── prompts/
├── specs/
├── src/narrativeos/
│   ├── api.py
│   ├── canon.py
│   ├── critics.py
│   ├── demo.py
│   ├── intent.py
│   ├── memory.py
│   ├── models.py
│   ├── pipeline.py
│   ├── prompts.py
│   ├── providers.py
│   ├── rendering.py
│   ├── repository.py
│   ├── schemas.py
│   ├── scoring.py
│   └── search.py
└── tests/
```
