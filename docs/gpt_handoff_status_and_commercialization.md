# NarrativeOS 当前状态与商业化差距（给 GPT / Codex）

## 一句话结论

截至当前版本，NarrativeOS 已经不是“单作品 demo”或“只能续写一章的实验项目”。

它现在更准确地说是一个：

- 可运行的多 World Pack 章节化叙事内核
- 已接入 Karma Character Engine v0.1 的 narrative system
- 已具备 `Reader / Author / Ops` 三端 Beta 骨架
- 已具备 `NarrativeEval + cross-pack benchmark + learned governance` 的运营与治理层

但它仍然**不是成熟商业化产品**，也还不是“真正通用、稳定、可规模化收费”的 narrative model。

最准确的阶段判断是：

`商业化 Beta 内核已成形，learned governance 已进入运营期，但内容质量、供给效率、数据飞轮与商业闭环仍明显不足。`

---

## 1. 当前已经完成到什么状态

### 1.1 产品 / kernel 状态

当前 NarrativeOS 已具备：

- 一回合 = 一章节 / 一场景，而不是单事件拼接
- `story_phase / chapter_index / min_end_turn`
- `Planner -> Writer -> Linter -> Presenter` 的章节生成链路
- Reader Mode 输出、session 持久化、replay、route preview
- Karma / Fate / Debt / Seed / Relationship 的人物与因果状态层
- 多 World Pack runtime，而不是单世界硬编码

当前已存在并可运行的 world packs 至少包括：

- `jade_court_exam_pack`
- `jade_court_romance_pack`
- `urban_mystery_lotus_lane`
- `xianxia_forgotten_vow`
- `synthetic_min_pack`

这说明 NarrativeOS 已经跨过了“是否只是剧情 demo”的阶段，进入了 **可运行的 narrative kernel** 阶段。

### 1.2 三端产品状态

`/app` 当前已经具备三端骨架：

- `Reader`
- `Author`
- `Ops`

其中：

- Reader 已支持连续阅读、session 恢复、replay、intent prefill、entitlement / credits 最小闭环
- Author 已支持 draft CRUD、validate、simulate、submit，并支持“选题材 + 写 brief + 生成 Draft”
- Author collaboration 已补 reviewer inbox、in-app notifications 与 `@mention` workflow，能把 comment / approval request / approval decision 路由到明确处理人
- Ops 已支持 review queue、publish、rollback、metering、NarrativeEval 指标、cross-pack 质量面板
- Ops 现已补 `Unified Investigation`：
  - 以 `account_id` 为主键把 `billing / support / governance / review / publish / rollback / runtime` 串成统一 trace timeline
  - 可按 `world_version_id / case_id` drill-down
  - 可导出 JSON investigation trace bundle
  - 会给出 `billing_first / governance_first / content_release_first` 的推荐排查顺序
- Ops 现已补 `Alert Center`：
  - 主动聚合 `runtime incidents / support issues / governance restrictions / async job incidents`
  - 支持 `acknowledge / resolve`
  - 每条 alert 都带 `standard_operating_path` 与 `investigation_ref`
  - 能从被动“查 account”推进到主动“看今天有哪些事在烧”
- governance workflow 本身也已从 skeleton 往前推进一段：
  - case 现有 `owner / due / evidence / policy labels / disposition / checklist`
  - 单 case detail 会返回 `workflow_summary + permission_summary`
  - governance mutation 在 bearer / reviewer identity 存在时会优先信任该身份
  - `author` 角色不能执行 governance mutation
  - Ops 已能从 support escalation -> claim/assign -> add evidence -> in_review/escalated -> resolved/dismissed 走完最小处置流
- account detail 现在也不再只是“数据汇总接口”：
  - 新增 `GET /v1/ops/accounts/{account_id}/workspace`
  - 会把 `subscription / wallets / entitlements / support / alerts / investigation` 聚成一个 account-first operator workspace
  - 输出 `health_status / top_blockers / action_pack / operator_timeline`
  - 让 Ops 可以在同一个 account 入口里先判断“哪里坏了、先做什么、有哪些可直接执行的动作”，再继续 drill-down
- content release 线也已不再只是三个分散面板：
  - 新增 `GET /v1/ops/worlds/{world_id}/release-workspace`
  - 会把 `publish checklist / review history / rollback history / quality trend / release-side investigation prefill` 聚成一个 world-first operator workspace
  - 输出 `release_summary / publish_blockers / review_ownership_summary / version_matrix / rollback_workspace / action_pack / operator_timeline`
  - 让 Ops 可以围绕一个 world 先判断“能不能发、为什么不能发、最近为什么回滚、下一步按 publish / rollback / investigation 哪个动作”
- 这些 panel 现在又被进一步收束到一个顶层 `Ops Control Plane`：
  - 新增 `GET /v1/ops/navigation-model`
  - 用 `account_id / world_id / case_id / alert_id` 解析 shared context
  - 输出 `escalation_summary / linked_context / navigation_targets / follow_up_actions`
  - 让 Ops 不再在多个 panel 之间手动抄 id，而是先决定“当前看哪个 scope、先沿哪条升级路径走”，再进入具体 workspace
- control plane 最近还做了一轮 refresh / data-loading hardening：
  - 现已按 `review_release / runtime / jobs / account / alerts / learned / navigation / investigation` scope 增量刷新
  - 高频处置动作默认不再触发整页 full refresh
  - 关键 helper 加了 stale-request protection，减少连续操作时旧数据覆盖新状态的问题
  - render 层也已开始按同一 scope 做 section-level 条件渲染，为后续真正拆成局部 render/update modules 铺路
  - `navigation / review_release / runtime / jobs / account / investigation / learned` 现已各自落成独立 section helper，`renderOpsSurface` 本身主要只剩 scope dispatch
  - 这些 render section 现已迁到独立前端脚本 `ops_render_sections.js`，前端边界比之前更接近“state/orchestration”和“render sections”分离
  - 现在又继续拆到了：
    - `ops_refresh.js`
    - `ops_actions.js`
    - `ops_render_sections.js`
    - `app.js`
    这让 Ops control plane 更接近清晰的前端状态机分层，而不是所有逻辑继续堆在单文件里
  - 同时现已补 shell smoke coverage，直接锁 `/app` 的脚本加载顺序和四层模块边界，减少后续演进时把逻辑重新揉回 `app.js` 的风险
  - `GET /v1/ops/navigation-model` 现也对 stale `alert_id` 做 soft-fail：Control Plane 不再因过期 alert 整体 404，而是继续用剩余 context 解析 account/world/case，并在 navigation summary 中标出 stale ref warning
  - 这层 soft-fail 现已进一步扩到 stale `case_id / world_id / world_version_id`：即使某个 drill-down ref 已经失效，Control Plane 仍会尽量用剩余 context 继续指向 account workspace / release workspace / investigation，而不是整条路径中断
  - Control Plane 现也会直接给出 stale-ref remediation actions：`Clear Stale Refs / Re-sync From Valid Context`，并把 surviving context 重新同步到 account / release / governance / investigation 面板输入
  - 仓库现已补可重复执行的浏览器 smoke harness：`scripts/run_ops_navigation_stale_ref_smoke.sh`
    - 会 seed 一份 deterministic stale-ref 场景
    - 会自动启动本地 API + Chrome remote debugging
    - 会验证 `stale warning -> Re-sync From Valid Context -> Clear Stale Refs`
  - 现也已补 CI/headless runner：`.github/workflows/ops-navigation-stale-ref-smoke.yml`
    - workflow 会安装 stable Chrome
    - 然后用 `CI_HEADLESS=1 CHROME_BIN=... bash scripts/run_ops_navigation_stale_ref_smoke.sh` 跑完整 smoke

这意味着它已经不是“只有模型输出”，而是已经带有最小产品工作流。

### 1.3 NarrativeEval 与 benchmark 状态

当前已具备：

- `Q01 ~ Q10` issue taxonomy
- L0 hard validators
- L1 narrative scoring
- `pass / rewrite / block`
- `EvaluationReport`
- simulation / publish gate
- cross-pack benchmark
- `top_failing_packs`
- `delta_summary`
- per-pack issue diagnosis
- benchmark `all` 现已由 registry 中 `benchmark_enabled` 的 published packs 自动发现，模板资产不会混入 cross-pack 质量基线

这说明系统已经具备“质量观测、问题分类、运营闸门”能力，而不是只看文本是否成功生成。

### 1.4 learned layer 与治理状态

当前 learned layer 已经从“离线 baseline”推进到了“运营治理层”：

#### Evaluator

- baseline training
- shadow inference
- shadow summary
- dashboard / compare / data ops
- impact tracking
- promotion gate
- manual approval workflow

#### Reranker

- baseline training
- shadow summary
- dashboard / compare / data ops
- promotion gate
- manual approval workflow

#### Ops 侧现在已具备

- `Learned Dashboard`
- `Learned Impact`
- `Learned Cadence`
- `Assisted Gate Experiment`
- `Assisted Rerank Experiment`
- `Shadow Candidate Compare`
- `Learned Data Ops`
- `Human Review Coverage & Quality`
- `Last Action Impact`
- `Evaluator Promotion Gate`
- `Reranker Promotion Gate`

当前 learned governance 已经能让 Ops：

- 看当前哪条 learned 线更成熟
- 看 evaluator / reranker 是否和继续读 / 付费代理指标一起变好
- 看 review / pair backlog
- 补 human review
- 看哪些 world 的 human review 覆盖不足、reviewer diversity 偏低、样本本身存在 ingestion warning
- 看 evaluator / reranker 当前到底更该补样、重训、做 shadow 验证，还是申请 promotion / activate
- 看一次补样后对 learned 层的即时影响
- 对 evaluator / reranker 的 promotion 做 approve / revoke
- 在 evidence 变差时看到 `stale / reconfirm required`
- 在非常窄的 bucket 中运行 `shadow_only -> assisted_gate` 受控实验
- 在非常窄的 bucket 中运行 `shadow_only -> assisted_rerank` 受控实验

但这些都**仍然只影响治理层，不影响线上生成 / publish / simulation gate**。

现在又多了一层更明确的 impact 观测：

- 新增 `GET /v1/ops/learned-impact`
- evaluator / reranker 会分别给出：
  - `impact_status`
  - `continuation_correlation`
  - `monetization_correlation`
  - `evidence_sufficiency`
- retention proxy 与 monetization proxy 被显式分开
- `assisted_gate` experiment receipts 现在也被接进 learned impact
- Ops 可以直接看到：
  - `assisted block` 是否和 continuation proxy 一起改善
  - `assisted block` 是否和 checkout / subscription / paywall proxy 一起变化
  - 哪些 world / issue 已经出现 assisted gate decision 痕迹

同时现在也多了一层更明确的数据质量观测：

- 新增 `GET /v1/ops/learned-review-quality`
- 新增 `GET /v1/ops/learned-review-quality/worlds/{world_id}`
- Ops 可以直接看到：
  - human review 覆盖是否达到 target
  - reviewer diversity 是否偏低
  - 哪些样本带 `ingestion_warnings`
  - 哪些 world 需要优先做 high-coverage replenishment

同时现在也多了一层更明确的 cadence 观测：

- 新增 `GET /v1/ops/learned-cadence`
- 新增 `GET /v1/ops/learned-cadence/{track}`
- 会把：
  - `sample accumulation`
  - `latest training run`
  - `artifact freshness`
  - `shadow validation`
  - `promotion approval`
  - `rollout status`
  聚成统一阶段视图
- 同时会直接显示：
  - `stale_reasons`
  - `checkpoint_summary`
  - `recent_events`
- 但它仍然是只读治理层，不直接改 promotion / rollout 判定

现在又补上了一层更窄、更保守的受控实验：

- 新增 `GET /v1/ops/learned-assisted-gate`
- 新增 `POST /v1/ops/learned-assisted-gate/configure`
- 当前实验只覆盖 `assisted gate`，不覆盖 reranker runtime
- 当前实验现在分成两条：
  - `assisted_gate`
  - `assisted_rerank`
- guardrail 固定为：
  - 必须显式启用
  - 必须命中 bucket / allowlist
  - 必须保持 evaluator rollout active
  - 必须保持 evaluator promotion approved
  - **不会 force-pass 一个 rule-blocked version**
- 第一版真正允许的线上影响只有：
  - 当规则本来会放行时，learned 在高置信条件下辅助拦截
- rerank 侧现在也有最小受控实验：
  - 新增 `GET /v1/ops/learned-assisted-rerank`
  - 新增 `POST /v1/ops/learned-assisted-rerank/configure`
  - 只在 Reader runtime 的候选链路上，对 `beat 1` 做 top-candidate assisted rerank
  - 必须保持 reranker rollout active + promotion approved
  - 还要满足 `bucket 命中 + max_score_gap`
- rollback 也固定为：
  - 关闭 experiment config
  - rollback evaluator rollout
  - revoke evaluator promotion approval
  - rollback reranker rollout
  - revoke reranker promotion approval

### 1.5 Monetization & Entitlements M0 状态

当前商业化基础设施已经不再只是概念方案，M0 骨架已开始落地：

- 3 档会员：
  - `play_pass`
  - `creator_pass`
  - `studio_pass`
- 双钱包：
  - `story_credits`
  - `studio_credits`
- `subscriptions` 状态机骨架
- web-first checkout stub provider
- checkout session / lifecycle event / retry attempt 持久化骨架
- webhook / renewal / cancel / retry / reconcile 闭环已开始落地
- Reader `story_credits` gating
- Author `studio_credits` gating（当前先覆盖 `from-brief` 与 `simulate`）
- Ops monetization audit / manual grant / revoke / wallet 调整

这说明商业化闭环已经从“只有 entitlement skeleton”推进到了“开始有最小可运行会员层”，但仍远未达到真实支付与生产运营级。

---

## 2. 当前客观验证基线

当前仓库的已知基线：

- `./.venv/bin/python -m pytest -q`：`215 passed, 2 warnings`
- `./.venv/bin/python -m src.narrativeos.demo`：正常
- `GET /health`：正常
- `/app`：`Reader / Author / Ops` 可打开并交互
- benchmark CLI：正常

当前 benchmark 基线：

- `cross_pack_pass_rate = 0.9`
- `delta_summary.regressions = []`

当前系统说明：

- weakest packs 已脱离长期 `rewrite`
- benchmark / regression 的 `all` 覆盖已与真实 published non-template packs 对齐
- 但相对较弱的 packs 仍然主要集中在：
  - `jade_court_romance`
  - `jade_court_exam`
  - `synthetic_min_pack`

当前 learned governance 的真实运行状态通常仍偏保守：

- evaluator promotion 常常仍是 `blocked / unapproved`
- reranker promotion 常常仍是 `blocked / unapproved`

这不是 bug，而是说明 **治理层已经有了，但证据质量还没全面达到可 promotion 的水平**。

---

## 3. 距离商业化还缺什么

下面这些差距，才是阻止 NarrativeOS 成为成熟商业化产品的核心问题。

### 3.1 内容质量还没稳定到“值得持续付费”

当前 weakest packs 已经可运行、可评测、可运营，但还没到：

- 多题材都稳定好读
- 多题材都稳定想继续读
- 多题材都稳定支撑付费与留存

最现实的内容缺口仍然集中在：

- `Q03` 重复
- `Q04` 解释句过多
- `Q05` 场景细节不足
- `Q09` 节奏与中段推进问题

### 3.2 作者供给系统还不够强

Author 虽然已经不是 JSON 编辑器，但离真正的供给工作台还有明显距离。

仍缺：

- 更成熟的角色卡 / scene blueprint / pacing / hook 编辑体验
- 更强的 draft diff / validation / simulation drill-down
- 团队协作级的草稿到发布流
- 世界资产生产效率工具

### 3.3 数据飞轮刚起步，还没变成模型飞轮

当前已有：

- chapter review samples
- issue fix pairs
- analytics events
- learned dashboard / compare / data ops / impact

但还没有形成真正持续增强模型能力的闭环：

- 高覆盖率人工评审样本
- 高质量 preference / ranking 数据
- learned evaluator / reranker 的稳定迭代节奏
- 更强的训练、蒸馏、偏好优化路径

换句话说，**治理和数据入口已经有了，但 learned model layer 还没真正“长起来”**。

### 3.4 商业化产品闭环仍然只是骨架

现在已有：

- entitlement shape
- tier config / subscription skeleton / dual-wallet M0
- credits / world pass / subscriber 语义
- metering skeleton
- publish / rollback / review audit line

但距离真实商业化还缺：

- 用户账户体系
- 真实支付与对账
- 成熟订阅策略
- 审核后台与合规策略
- 实验 / 增长 / retention 分析
- 用户资产沉淀

### 3.5 生产级 infra / routing / observability 仍不足

当前 provider boundary 已有，但仍缺：

- 模型路由策略
- 成本治理
- 延迟治理
- cache / retry / fallback
- provider-level observability
- 风险隔离与灰度机制
- Postgres / migration / 多人并发级别的生产化完善

本轮已把 provider routing 从 skeleton 推到了更接近真实运行面：

- Reader `continue_story` 现已接入统一 candidate / renderer routing runtime
- Authoring `run_simulation_for_world_version` 也复用同一套 runtime
- candidate / renderer 现在支持按 `scope` 分别组装 backend policy
- primary provider 失败、budget blocked、或 retry 后仍失败时，会继续走 fallback，而不是直接中断 Reader / Authoring 主路径
- Ops 现可通过 `GET /v1/ops/provider-routing` 看到 candidate / renderer 的当前 routing policy

同时现在也补上了一层更明确的 runtime rollout control：

- 新增 `GET /v1/ops/provider-rollout`
- 新增：
  - `POST /v1/ops/provider-rollout/{track}/canary`
  - `POST /v1/ops/provider-rollout/{track}/activate`
  - `POST /v1/ops/provider-rollout/{track}/rollback`
- candidate / renderer 两条 runtime 轨都可以独立：
  - `shadow`
  - `canary`
  - `active`
  - `rolled_back`

Postgres / migration / schema lifecycle 这一段也开始从 SQL skeleton 走向更正式的 migration discipline：

- 仓库现在有最小 Alembic scaffold：
  - `alembic.ini`
  - `db/alembic/env.py`
  - `db/alembic/versions/20260404_0011_platform_baseline.py`
  - `db/alembic/versions/20260404_0012_runtime_hotspot_indexes.py`
- `GET /v1/ops/schema-lifecycle` 现在不仅看 SQL migrations，也会返回：
  - `alembic.current_revision`
  - `alembic.head_revision`
  - `alembic.pending_revisions`
  - `alembic.status`
- `python -m src.narrativeos.persistence.migrations` 现在支持：
  - `--dry-run`
  - `--alembic-current`
  - `--alembic-history`
  - `--alembic-upgrade-head`
- 当前策略仍然是：
  - SQL migrations 继续作为最安全的 apply source
  - Alembic 负责 revision discipline / current-head visibility / future forward-revision path

另外 Phase 6 也开始补数据层完整性与修复工具：

- 新增 `GET /v1/ops/data-integrity`
- 新增 `POST /v1/ops/data-integrity/repair`
- 可以直接看到：
  - hotspot composite index coverage
  - session pointer drift
  - orphan route choice backlog
  - duplicate active subscription backlog
  - missing first-class review asset references
- 当前 safe repair 只开放两类：
  - `reconcile_session_chapter_pointers`
  - `prune_orphan_route_choices`
- `duplicate active subscriptions` 仍然保留为 manual review，不自动修。
  - `canary`
  - `active`
  - `rolled_back`
- canary 命中结果现在也会进入 runtime receipts，方便在 Ops 侧确认当前请求到底是否落进了灰度桶

同时 runtime observability 现在也不再只看“有没有 fallback / budget block”，而是开始接近真实运营观测：

- runtime receipts 现在会记录：
  - `runtime_latency_ms`
  - `candidate_latency_ms`
  - `renderer_latency_ms`
  - `candidate_attempt_count`
  - `renderer_attempt_count`
  - `candidate_estimated_request_cost_usd`
  - `renderer_estimated_request_cost_usd`
- provider metrics 现在会汇总：
  - `latency_summary`
  - `latency_trend`
  - `rollout_stage_summary`
  - provider 级 `avg/p95 latency`
  - `selected_as_candidate_count / selected_as_renderer_count`

Phase 6 的 backup / restore / deploy / recovery runbook 这条线也继续往生产可控收了一步：

- runtime backup manifest 现在会带 `verification_snapshot`
  - backend
  - schema/alembic 状态
  - 核心表 row counts
- `POST /v1/ops/runtime-restore` 现在会返回：
  - `restore_decision`
  - `restore_decision_hints`
  - `pre_restore_verification`
  - `post_restore_verification`
  - `restore_verification_steps`
- 新增：
  - `GET /v1/ops/recovery-drills`
  - `POST /v1/ops/recovery-drill`
- 现在还继续往前推了一段：
  - `GET /v1/ops/runtime-restore-requests`
  - `POST /v1/ops/runtime-restore/request`
  - `POST /v1/ops/runtime-restore/{request_id}/approve`
  - `POST /v1/ops/runtime-restore/{request_id}/revoke`
  - `POST /v1/ops/jobs/runtime-restores`
- 这意味着 Postgres 不再只是“operator 看着命令手敲”：
  - backup 现在可以走真实 `pg_dump` custom dump 执行
  - restore 有两步 approval gate
  - 真正执行走 async job
  - wrapper / stdout / stderr / result.json 都会留 artifact
- 也就是说，现在 Ops 不只是“能备份/恢复”，而是能在恢复前先做 dry-run drill，并把恢复前后验证链记录下来。

---

## 4. 当前最现实的优先级

如果目标是“最终商业化”，最现实的优先级不是先做支付，而是：

### P0：继续把内容质量拉到商业可用

- 持续提升 weakest packs
- 继续压 `Q03 / Q04 / Q05 / Q09`
- 提升跨题材稳定性
- 提升章节中段与长线可读性

### P1：把 Author 真正做成供给工具

- brief -> draft 继续做强
- 角色 / scene / pacing / sensory 编辑更成熟
- 资产 diff / validation / simulation drill-down 更强

### P2：把 Ops 和商业化闭环做实

- moderation / rights / audit trail
- 更完整的 publish / rollback / quality governance
- entitlement / credits / account ownership
- 更成熟的运营分析

### P3：把 learned layer 从治理层推进到真正的模型层

- evaluator / reranker 数据覆盖提升
- 更稳定的训练与迭代流程
- 从 shadow governance 演进到真正的 model improvement loop

---

## 5. 给 GPT / Codex 的最准确结论

截至当前版本，NarrativeOS 已经完成了：

- 从单作品 Alpha 到多 pack Beta kernel 的跨越
- 从“能生成章节”到“能被评测、能被运营、能被创作”的跨越
- 从纯规则/资产能力到 learned governance 的跨越

但它距离“真正成熟、可持续商业化的通用 narrative model”还差的最大几项仍然是：

1. **跨题材质量稳定性**
2. **作者供给效率**
3. **高质量数据飞轮**
4. **learned model layer 真正增强**
5. **完整商业化与运营闭环**

一句最准确的话是：

`我们已经做出了一个可运营、可治理、可扩展的 narrative kernel，但还没有做出一个真正成熟、稳定、可持续商业化的通用 narrative product。`
