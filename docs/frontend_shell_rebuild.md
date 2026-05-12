# NarrativeOS Frontend Shell Rebuild

## What Changed

The web shell now treats `Reader`, `Author`, and `Ops` as separate product workspaces instead of one long scrolling console.

- `Reader` defaults to a `Landing / Shelf` experience with three top-level actions:
  - continue a prior journey
  - browse worlds
  - start a new journey
- `Reader` switches into a dedicated reading workspace after a session is created or restored.
- `Author` is grouped into guided workspaces:
  - `Overview`
  - `Brief`
  - `Draft`
  - `Simulate`
  - `Review & Submit`
  - `Settings`
- `Ops` is grouped into task-oriented workspaces:
  - `Dashboard`
  - `Review Queue`
  - `Account Investigation`
  - `Release Workspace`
  - `Alerts & Governance`
  - `Learned / Infra`

## Reader Polish

The Reader surface now follows the `Landing -> Read -> Storybook / Backstage` progression more explicitly.

- Landing now foregrounds:
  - continue a prior journey
  - browse worlds
  - start a new journey
- Landing shows a compact context summary for:
  - current world
  - current reader id
  - whether resumable sessions exist
- World cards now externalize tacit context:
  - theme / mood
  - recommended play style
  - access state
- Session cards now emphasize the safe continue path first. `继续阅读` is the only primary action.
- Starting a session now enters a readable `序章` state instead of a blank reading workspace.
- Storybook now renders in an editorial order:
  - title
  - recap
  - quote
  - prose
  - beats
  - tags
  - timeline
- Reader shell v2 的 Storybook 进一步改成高保真章节画布：
  - 顶部先外显章节编号、当前 turn、未解牵挂和画面母题
  - 正文与引句分栏，避免 recap / quote / prose 混成一块
  - 节拍改成编号列表，先回答“这一章怎么抬势、落子、留余波”
  - 连续章节轨迹改成可点击回看卡，允许在最近几章之间直接切换
- Paywall and unlock are now rendered as chapter-inline unlock cards instead of standalone system banners.
  - the last readable chapter carries the unlock explanation
  - the CTA continues the current reading path instead of bouncing the user to a separate control surface
  - the same unlock card appears inside `Storybook` when a chapter is blocked
- Backstage has a dedicated `返回阅读` action and behaves like a contextual analysis drawer instead of a permanent third-column console.

## Reader Continuity Contract

Reader 继续阅读现在统一围绕四种可恢复状态组织：

- `ok`
- `payment_required`
- `quality_guard_failed`
- `restricted`

界面行为约束：

- 只要存在 `session_id / pending checkout / quality guard failure / authored work preview`，Reader 都必须保持在 `workspace=read`
- `payment_required` 不再把用户弹回 landing；主动作是“解锁并继续当前 session”
- `quality_guard_failed` 不再被当成“读坏了”；主动作是“重试当前章”，同时保留当前 session、上一章内容和当前阅读视图
- `Backstage` 关闭后回到上一个阅读视图，而不是固定回 `experience`

## Author Polish

The Author surface now behaves more like a daily workbench and less like a raw panel dump.

- Overview now foregrounds a `推荐下一步` focus block instead of forcing the author to scan all panels equally.
- The top Author hero now adapts to context:
  - no draft: guide the author into `Brief`
  - active draft present: guide the author into `Draft 摘要` or `Simulate`
- Brief is now grouped into three clear composer clusters:
  - 世界与关系
  - 命题与冲突
  - 氛围与地点
  - the only primary action in this workspace is `根据 Brief 生成 Draft`
- Draft now has a local subsection switch instead of a flat panel dump:
  - `Assets`
  - `Longform`
  - `Repair`
  - `Style`
  - the subsection rail stays visible while individual panels swap beneath it
- Workflow is now rendered as a structured work card:
  - current stage
  - recommended next action
  - validation/simulation health
  - blocker summary
  - stage pills
- Draft detail is now rendered as a scan-friendly summary instead of a raw multiline dump:
  - project positioning
  - current health
  - run-state
  - narrative style
  - diagnosis
- Settings now exposes three explicit summary cards at the top:
  - auth state
  - notification state
  - collaboration state
  - each card now carries a current anomaly or reminder plus a primary action
- Simulate now exposes work cards instead of only jump buttons:
  - chapter task work card
  - continuity work card
  - compare work card
  - each work card now shows current object, current problem, and the recommended next edit path
- Simulate and Review now each start with a summary dock:
  - Simulate foregrounds `latest decision / freshness / issue queue / weakest chapter`
  - Review foregrounds `readiness / compare evidence / revision stack`
- Author interactions now prefer shell status banners and toasts over blocking alerts for common missing-field and action-failed feedback.

## Author Validation Routes

Use these routes when validating the Author shell by hand:

- `?product=author&workspace=overview`
- `?product=author&workspace=brief`
- `?product=author&workspace=draft`
- `?product=author&workspace=simulate`
- `?product=author&workspace=review`
- `?product=author&workspace=settings`

## Public Vs Internal Shell

The shell now distinguishes between:

- Public mode: the default `/app` experience for user-facing surfaces
  - only `阅读 / 创作` are visible in the top product switcher
  - `运营` and `内部模式` controls stay hidden
  - public-facing banners and cards should avoid raw engineering errors, ids, provider names, or untranslated product terms
- Internal mode: `?debug=1`
  - `运营` becomes visible again
  - smoke verification and operator-only tools continue to run here
  - deep Ops cards are still expected to render in Chinese, even when they expose internal workflow detail

The repo now keeps these browser checks:

- Reader-only smoke: `scripts/run_reader_shell_smoke.sh`
- Internal end-to-end smoke: `scripts/run_frontend_shell_smoke.sh`
- Agent Studio workbench smoke: `scripts/run_agent_studio_smoke.sh`
- Public copy guard: `scripts/run_public_shell_copy_check.sh`
- Unified internal Ops browser guard entry: `scripts/run_ops_internal_browser_guards.sh`
- Internal Ops deep-card guard: `scripts/run_ops_internal_snapshot_check.sh`
- Internal Ops form-copy guard: `scripts/run_ops_internal_form_copy_check.sh`
- Internal Ops static-copy guard: `scripts/run_ops_internal_static_copy_check.sh`
- Internal Ops populated-card guard: `scripts/run_ops_internal_populated_copy_check.sh`
- Internal Ops account/alert/governance populated guard: `scripts/run_ops_internal_account_copy_check.sh`

The recommended CI entry for internal Ops browser verification is now:

- workflow: `.github/workflows/ops-internal-browser-guards.yml`
- local runner: `scripts/run_ops_internal_browser_guards.sh`
- summary writer: `scripts/write_ops_internal_browser_guard_summary.py`

The unified runner executes the internal Ops browser guards in one place with staggered ports, so CI and local verification no longer need to remember each individual script manually.
The workflow now also publishes a GitHub step summary in the same style as `frontend-shell-smoke`, including:

- overall status
- per-guard completed/failed steps
- failure snapshot references
- server log tails
- chrome log tails

All browser guard result files now target the same lightweight schema family:

- `schema_version`
- `guard`
- `summary_meta`
- `artifacts`
- `status / completed_steps / failed_step / console_errors / summary`

This keeps `public shell`, `frontend shell smoke`, and `internal Ops guards` ready to merge into one QA dashboard without extra result-shape conversion.

## Agent Studio QA Rails

Use the Agent Studio smoke when validating the Author-side co-directed fiction workbench:

- local author launcher: `scripts/run_agent_studio_local.sh` opens `/app?product=author&workspace=studio&debug=1` after the backend health check passes
- local runner: `scripts/run_agent_studio_smoke.sh`
- CI/headless form: `CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_agent_studio_smoke.sh`
- artifacts:
  - `artifacts/agent_studio_smoke_result.json`
  - `artifacts/agent_studio_smoke_failure_snapshot.json`
  - `artifacts/agent_studio_smoke_failure.png`
  - `artifacts/agent_studio_smoke_desktop.png`
  - `artifacts/agent_studio_smoke_mobile.png`
  - `artifacts/agent_studio_smoke_visual_review.md`

The smoke verifies startup, first chapter generation, director continuation, route branching, `.nosbook` export, visible product-language wait copy, desktop workbench rendering at `1440x1000`, desktop sticky director behavior after scrolling to choices/routes, mobile workbench rendering at `390x844`, mobile bounded choice-card scrolling, mobile horizontal overflow, and a visual review checklist for screenshot triage.

Codex-style agents can upload an exported `.nosbook` to a platform private draft through the API/CLI bridge:

```bash
export NARRATIVEOS_PLATFORM_URL="https://your-platform.example"
export NARRATIVEOS_PLATFORM_TOKEN="<author bearer token>"
python scripts/upload_nosbook.py --file path/to/work.nosbook
```

For a one-command local Studio bridge, use `--local-work-id` with a separate local author token:

```bash
export NARRATIVEOS_LOCAL_STUDIO_URL="http://127.0.0.1:8000"
export NARRATIVEOS_LOCAL_STUDIO_TOKEN="<local author bearer token>"
export NARRATIVEOS_PLATFORM_URL="https://your-platform.example"
export NARRATIVEOS_PLATFORM_TOKEN="<platform author bearer token>"
python scripts/upload_nosbook.py --local-work-id work_xxx
```

The CLI calls local `GET /v1/author/works/{work_id}/export?format=nosbook&route=active`, then platform `POST /v1/author/nosbooks/import`, expects `schema_version: nosbook/v1`, prints machine-readable JSON with `schema_version: nosbook_import_result/v1` and `status: private_draft`, and does not print or persist the token. Imports report `world_version_link_status: linked` or `source_only`. The upload is intentionally API/CLI-only in v1; Studio still does not show a platform upload button.

The visual review checklist combines automatic evidence rows with `manual_review` prompts for layout balance, overlap, reader prominence, mobile readability, control reachability, and clipped text. Only objective smoke checks can fail the run.

For PRs that change Agent Studio layout CSS, reviewers must paste the two `manual_review` rows from `artifacts/agent_studio_smoke_visual_review.md` into a PR comment and mark each as `accepted` or `needs follow-up` after screenshot inspection:

- `desktop / Three-column workbench review / manual_review`
- `mobile / Stacked workbench review / manual_review`

This convention is human visual triage only; it does not add an automated image comparison gate.

## Reader QA Rails

Use the Reader-only smoke when we need a clean regression signal for the reading surface without Author/Ops coupling:

- local runner: `scripts/run_reader_shell_smoke.sh`
- CI/headless form: `CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_reader_shell_smoke.sh`
- artifacts:
  - `artifacts/reader_shell_smoke_result.json`
  - `artifacts/reader_shell_smoke_failure_snapshot.json`
  - `artifacts/reader_shell_smoke_failure.png`

The Reader-only smoke verifies:

- `Landing -> Create Session -> Restore Session`
- first Reader step and inline paywall rendering
- checkout completion and resume into the same session
- `Storybook / Backstage` view switching after the session is active

Use the long-route Reader storybook smoke when we need to check chapter-canvas stability after 30–50 chapters instead of only the first few turns:

- local runner: `bash scripts/run_reader_storybook_long_route_smoke.sh`
- CI/headless form: `CI_HEADLESS=1 CHROME_BIN=/path/to/google-chrome bash scripts/run_reader_storybook_long_route_smoke.sh`
- CI workflow: `.github/workflows/reader-storybook-long-route-smoke.yml`
- defaults:
  - `WORLD_IDS=jade_court_exam,jade_court_romance,urban_mystery_lotus_lane`
  - `TARGET_CHAPTERS=30`
  - `MIN_TARGET_CHAPTERS=30`
- artifacts:
  - `artifacts/reader_storybook_long_route_smoke_seed.json`
  - `artifacts/reader_storybook_long_route_smoke_result.json`
  - `artifacts/reader_storybook_long_route_smoke_history.json`
  - `artifacts/reader_storybook_long_route_smoke_failure_snapshot.json`
  - `artifacts/reader_storybook_long_route_smoke_failure.png`
  - `artifacts/reader_storybook_long_route_smoke_storybook.png`

The long-route Reader storybook smoke verifies:

- seeded Reader sessions can really reach the `30 / 30` long-route target window on at least `jade_court_exam` / `jade_court_romance` / `urban_mystery_lotus_lane`
- `Storybook` trajectory no longer stays in single-chapter mode after long-route accumulation
- each seeded pack is restored and verified independently by `session_id`
- sampled early / middle / latest visible trajectory cards in each seeded pack all render non-placeholder `quote`
- sampled early / middle / latest visible trajectory cards in each seeded pack all render non-empty `beats`
- every non Jade Court pack must keep a minimum difference from Jade Court packs:
  - if sampled titles are highly similar, sampled quote-token overlap must still stay below the smoke threshold
  - the smoke currently records `title_similarity / quote_similarity / passes_min_difference`
- title homogenization is also emitted as a non-blocking warning:
  - when sampled titles stay nearly identical across packs but quote-token overlap is still low
  - the smoke records `reader_storybook_title_homogenization_warnings / warning_count`
- repeated title-homogenization warnings are persisted into `reader_storybook_long_route_smoke_history.json`
  - after `3` consecutive eligible runs for the same non-Jade vs Jade pair, the trend is promoted into release review as a watch-only checklist observation
  - the smoke records `reader_storybook_title_homogenization_history_summary / trend / promoted_pairs`
  - the CI workflow restores the latest non-expired `reader-storybook-long-route-smoke-history` artifact before the run, then uploads the appended history again after the run
- a success screenshot is captured from the long-route storybook surface for visual QA

The public copy guard verifies:

- `debug=0` hides Ops and internal controls
- payment card copy stays user-facing
- reader left rail copy stays user-facing
- Author `overview / brief / draft / simulate / review / settings` first-screen copy stays user-facing
- a forbidden-terms list does not reappear in visible public text

The internal Ops deep-card guard verifies:

- `debug=1&product=ops` can render internal Ops mode cleanly
- mocked deep Ops cards still render Chinese field labels instead of old English headings
- the remaining deep-detail containers stay guarded:
  - runtime receipts
  - provider runtime metrics
  - governance export
  - investigation timeline
  - learned compare
  - evaluator / reranker promotion gates
  - learned data ops summary and backlog/detail cards

The internal Ops form-copy guard verifies:

- `debug=1&product=ops` 下的表单区标签、按钮、选项和 placeholder 都维持中文
- 重点覆盖：
  - 统一导航
  - 发布台
  - 账户 / 订阅 / 钱包操作区
  - 告警、治理、统一排查
  - 辅助门控 / 辅助重排 / 发布审批
  - 人工审阅、偏好采集、排序采集
  - 数据一致性、备份恢复、异步任务、通道灰度
- `Account ID / Reviewer ID / World Version ID / Restriction Type` 这类旧英文标签不会回退到可见界面

The internal Ops static-copy guard verifies:

- `debug=1&product=ops` 下默认空态的说明区仍然是中文
- 重点覆盖：
  - 发布台与账户排查空态
  - 告警、治理、统一排查说明区
  - 学习层总览、实验、灰度、发布门、待补样区
  - 跨包基准、审核历史、质量趋势
  - 数据库结构、运行手册、异步任务、运行观测
- `world version / trace timeline / learned summary / runtime incident snapshot / cost trend dashboard` 这类旧英文说明不会回退到可见界面

The internal Ops populated-card guard verifies:

- `debug=1&product=ops` 下带数据的运营卡片正文仍然保持中文
- 重点覆盖：
  - 审核队列与世界状态
  - 运行时事故快照、通道路由、通道灰度、通道运行指标
  - 排查摘要与证据索引
  - 质量评测卡片与跨包基准卡片
- `latest / summary / provider / trace / issue / cross-pack / publish gate` 这类旧英文正文不会回退到真实数据卡片里

The internal Ops account/alert/governance populated guard verifies:

- `debug=1&product=ops` 下账户、告警、治理三组带数据详情卡片正文仍然保持中文
- 重点覆盖：
  - 订阅审计 / 生命周期时间线 / 账户运营时间线
  - 客服问题定位卡片
  - 告警列表与告警详情
  - 治理摘要 / 治理个案 / 治理详情 / 审计导出
  - 账户审计拆解 / 审计轨迹
- `subscriptions / provider / linked cases / target / owner / policy / evidence / audit breakdown / actor / wallet / tier` 这类旧英文正文不会回退到用户可见详情卡片里

## Routing Model

The shell now syncs primary UI state into the URL query string.

- `product`
- `workspace`
- `view`
- `world_id`
- `session_id`
- `draft_id`
- `account_id`
- `debug`

Examples:

- Reader landing: `?product=reader&workspace=landing`
- Reader reading view: `?product=reader&workspace=read&view=experience&session_id=...`
- Author review workspace: `?product=author&workspace=review&draft_id=...`
- Ops account investigation: `?product=ops&workspace=account&account_id=...`

## UX Rules

- Internal debug and entitlement testing controls are hidden by default.
- Reader entitlement, subscription, and checkout requests only run when needed:
  - debug mode is enabled
  - a paywall quote exists
  - a checkout flow is already in progress
- Blocking `alert()` dialogs are replaced with non-blocking status banners and toasts.
- Mobile keeps a single primary pane visible at a time.
- Reader backstage analysis no longer lives as a permanent third column.

## Implementation Notes

- `src/narrativeos/web/index.html` now owns the new shell header, landing entry, and cache-busted asset references.
- `src/narrativeos/web/state_runtime.js` now owns the explicit shared state boundary:
  - `shellState`
  - `readerState`
  - `authorState`
  - `opsState`
- `src/narrativeos/web/ui_shared.js` now owns UI/transport helpers such as API fetch/error handling, status/toast messaging, generic card utilities, formatting, and parse helpers.
- `src/narrativeos/web/reader_accessors.js` now owns membership/gating/unlock accessors used by Reader and any surface that needs reader-facing entitlement labels.
- `src/narrativeos/web/author_accessors.js` now owns draft/workbench accessors and author-specific gating helpers.
- `src/narrativeos/web/ops_accessors.js` now owns Ops-only state accessors such as async job lookup.
- `src/narrativeos/web/route_sync_runtime.js` now owns shell URL/query synchronization, including product/workspace/view/account/draft/session route hydration and replacement.
- `src/narrativeos/web/workspace_layout_runtime.js` now owns workspace grouping, subnav rendering, workspace switching, and scroll-to-workspace bridging.
- `src/narrativeos/web/shell_status_runtime.js` now owns shell status/UI synchronization such as `syncViewMode`, `syncProductMode`, `updateStatus`, and debug-toggle side effects.
- `src/narrativeos/web/shell_bootstrap_runtime.js` now owns the classic-script exposure layer, wiring runtime exports into the shared global names that older scripts still call.
- `src/narrativeos/web/dom_shared.js` now owns the DOM query helpers and `NULL_NODE` fallback used by each DOM runtime directly.
- `src/narrativeos/web/shell_dom.js` now owns shell-scoped DOM lookups.
- `src/narrativeos/web/reader_dom.js` now owns Reader-scoped DOM lookups, including Storybook templates and tone pills.
- `src/narrativeos/web/author_dom.js` now owns Author-scoped DOM lookups.
- `src/narrativeos/web/ops_dom.js` now owns Ops-scoped DOM lookups.
- `src/narrativeos/web/reader.js` now owns Reader runtime behavior, reading flow, Storybook rendering, unlock cards, and Reader bootstrapping.
- `src/narrativeos/web/author_workspace.js` now owns Author workspace behavior, rendering, workflow actions, and guided workspace transitions.
- `src/narrativeos/web/ops_shared.js` now owns shared Ops helpers used by both `ops_actions.js` and `ops_render_sections.js`.
- `src/narrativeos/web/ops_refresh.js` now exports `OpsRefreshRuntime`, which owns Ops refresh scopes, navigation context sync, and scoped surface reload flows.
- `src/narrativeos/web/ops_actions.js` now exports `OpsActionsRuntime`, which owns Ops action handlers instead of leaking action names through implicit global script scope.
- `src/narrativeos/web/ops_render_sections.js` now exports `OpsRenderRuntime`, which owns Ops section rendering and consumes refresh/actions through explicit runtime boundaries.
- `src/narrativeos/web/ops_runtime.js` now owns the remaining Ops runtime form submissions that used to live in `app.js`, including review capture, preference capture, and ranking capture flows.
- `src/narrativeos/web/reader.js` now exposes `bindReaderEvents()` so Reader-specific listeners stay with Reader behavior and rendering.
- `src/narrativeos/web/author_workspace.js` now exposes `bindAuthorWorkspaceEvents()` and `initializeAuthorWorkspaceRuntime()` so Author listeners and auth/session boot stay with the Author surface.
- `src/narrativeos/web/ops_runtime.js` now exposes `bindOpsEvents()` and `initializeOpsRuntime()` so Ops listeners stay with Ops refresh/action runtimes instead of leaking back into shell bootstrap.
- `src/narrativeos/web/shell_runtime.js` now owns only top-level shell startup order, product mode switching, debug toggle wiring, and runtime boot orchestration. It no longer carries product-specific listener lists.
- `src/narrativeos/web/app.js` has been removed from the `/app` runtime chain. DOM registration now lives in `dom_shared` plus `shell_dom / reader_dom / author_dom / ops_dom`.
- The repo now includes a minimal cross-surface smoke harness for `/app`:
  - local runner: `scripts/run_frontend_shell_smoke.sh`
  - browser verification: `scripts/verify_frontend_shell_smoke.js`
  - CI workflow: `.github/workflows/frontend-shell-smoke.yml`
  - current flow coverage:
    - Reader enters a world and advances one step
    - Reader can be forced into a paid chapter, show an inline unlock card, create checkout, simulate webhook activation, and resume reading
    - Author refreshes once, registers/logs in a smoke actor, creates a real draft from brief, then runs a real simulate
    - Ops switches `Dashboard -> Review Queue -> Account Investigation`, grants one `creator_pass` subscription mutation for the smoke actor, creates one real governance case on that account, pushes it into `in_review`, appends one real evidence note, applies one real `checkout_block` restriction, releases that restriction, then assigns an explicit owner and resolves the original case as that owner
- Agent Studio now has a focused rendered smoke for the co-directed workbench:
  - local runner: `bash scripts/run_agent_studio_smoke.sh`
  - browser verification: `scripts/verify_agent_studio_smoke.js`
  - summary: `scripts/write_agent_studio_smoke_step_summary.py`
  - artifacts: `artifacts/agent_studio_smoke_result.json`, `artifacts/agent_studio_smoke_failure_snapshot.json`, `artifacts/agent_studio_smoke_failure.png`, `artifacts/agent_studio_smoke_desktop.png`, `artifacts/agent_studio_smoke_mobile.png`, `artifacts/agent_studio_smoke_visual_review.md`
  - flow coverage: startup page -> first chapter -> director continuation -> branch creation -> `.nosbook` export
  - layout regression coverage: desktop sticky director and mobile bounded choice-card scrolling
- Startup flow now resolves as:
  - `DOMShared`
  - `ShellDOM`
  - `ReaderDOM`
  - `AuthorDOM`
  - `OpsDOM`
  - `StateRuntime`
  - `UIShared`
  - `ReaderAccessors`
  - `AuthorAccessors`
  - `OpsAccessors`
  - `OpsShared`
  - `OpsRefreshRuntime`
  - `OpsActionsRuntime`
  - `OpsRenderRuntime`
  - `OpsRuntime`
  - `ReaderRuntime`
  - `AuthorWorkspaceRuntime`
  - `RouteSyncRuntime`
  - `WorkspaceLayoutRuntime`
  - `ShellStatusRuntime`
  - `ShellBootstrapRuntime`
  - `ShellRuntime.initializeShellRuntime()`
- `src/narrativeos/web/ops_refresh.js` still defers expensive account/runtime/release requests until the matching workspace is active, but those refresh paths are now consumed through `OpsRefreshRuntime` instead of bare cross-file globals.
