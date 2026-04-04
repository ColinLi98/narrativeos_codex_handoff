# NarrativeOS 会员盈利模式与 Codex 任务补充（CN）

## 1. 设计原则

NarrativeOS 当前更接近“可运营的商业化 Beta 内核”，但离真正稳定、可持续收费的内容产品还差三件事：
1. 跨题材内容质量稳定性
2. Author 供给效率
3. 数据飞轮与完整商业闭环

因此，会员体系要遵循 4 个原则：

- **先卖持续体验，不卖无限生成。** 先把“值得继续读、值得继续创作”的权益卖清楚，而不是用无限量承诺透支模型成本。
- **Reader 与 Author 权益分开设计。** 不同层级不能只是“额度更多”，而要让 $20 和 $60 显著解锁创作与运营能力。
- **订阅为主，top-up 为辅。** 主体收入来自月度会员；额外 credits / world pass / seasonal arc 作为补充收入。
- **Web-first 计费，App 内做 entitlement 同步。** 若未来上架 App Store / Google Play，数字内容订阅需要考虑平台内购规则，因此当前先把 entitlement / metering / subscription lifecycle 做实，再接不同支付 provider。

## 2. 建议的商业模型

### 核心收入结构

1. **会员订阅（主收入）**
   - Play Pass: $10 / 月
   - Creator Pass: $20 / 月
   - Studio Pass: $60 / 月

2. **Top-up 加购（辅助收入）**
   - 额外 Story Credits 包
   - 额外 Studio Credits 包
   - Seasonal World Pass / 特别篇

3. **未来收入（暂不作为当前主线）**
   - Creator monetization / marketplace 抽成
   - 品牌联名 world pack
   - B2B narrative engine / white-label

## 3. 计费单位建议

建议不要只用一个“次数”概念，改成两种权益池：

### A. Story Credits（面向 Reader）
消耗场景：
- 继续一章
- 打开高质量 alternate branch
- premium route rewind / replay
- premium public world pack 章节推进

### B. Studio Credits（面向 Author）
消耗场景：
- 从 brief 生成 draft
- simulate / validate
- quality drill-down
- 高质量 writer / reranker 路径
- 高上下文作者级工具调用

这样可以避免：
- 纯读者觉得自己在为创作工具买单
- 创作者快速烧完全部权益，导致体验失真

## 4. 三档会员设计

## Tier 1 — Play Pass（$10 / 月）
**目标用户：** 重度读者 / 轻度互动玩家

### 核心权益
- 解锁全部标准 public world packs
- 每月 **120 Story Credits**
- 最多 **20 条活跃 routes**
- 标准优先级生成队列
- route replay / recap / 章节回看
- 每月 **2 个会员限定特别篇 / side stories**
- 账户云同步与跨设备继续阅读
- 新 world pack 提前 **48 小时** 体验

### 不包含
- Author draft 生成
- 高级 simulate / validate
- publish / submit for review
- 高优先级 creator queue

### 设计意图
这一档必须足够“好买”，主要卖点不是复杂的创作能力，而是：
- 更完整的读
- 更顺滑的继续读
- 更像订阅内容平台而不是按次付费工具

---

## Tier 2 — Creator Pass（$20 / 月）
**目标用户：** 深度读者 + 初级创作者 / fanfic 与原创作者

### 包含 Play Pass 全部权益，外加：
- 每月 **300 Story Credits**
- 每月 **40 Studio Credits**
- 最多 **5 个 private drafts / worlds**
- `from-brief -> draft` 能力
- `validate` / `simulate` 基础可用
- 更长 continuity / memory 模式（creator route）
- 更高优先级生成队列
- 新功能 / 新 pack 提前 **7 天** 体验
- 自己 draft 的基础 analytics：
  - chapter pass rate
  - top issue categories
  - route completion signals（lite）
- 每月 **2 次 submit-for-review 配额**（进入自动 review queue，不承诺人工精修）

### 不包含
- 团队协作 seats
- 高级 diagnostics / issue heatmap for own packs
- 批量 simulation
- 最优先 creator review queue

### 设计意图
$20 档应该成为最核心的 ARPU 档位：
- 既能消费，也能创作
- 不承诺过重的人力服务
- 用 author-lite 能力拉升留存和内容供给

---

## Tier 3 — Studio Pass（$60 / 月）
**目标用户：** 高强度创作者 / 工作室 / 超级用户 / 头部社区 KOL

### 包含 Creator Pass 全部权益，外加：
- 每月 **1000 Story Credits**
- 每月 **200 Studio Credits**
- 未用完的 Studio Credits **可滚存 2 个月**（上限 400）
- 最多 **20 个 private drafts / worlds**
- 最多 **2 个 collaborator seats**
- 高优先级 writer / reranker 路径
- 批量 simulate / compare / draft diff
- 高级 diagnostics：
  - issue heatmap
  - dialogue distinctness
  - scene detail density
  - mid-arc pacing trend
- 每月 **5 次 submit-for-review 配额**（优先 review queue）
- 发布前 checklist / pre-publish QA 报告
- 创作者 monetization beta / marketplace 内测优先资格
- 每月 1 次 creator office hours / closed community access
- 新功能 / 新模型 / 新工具最优先体验

### 设计意图
$60 档不能只是“大号 $20”，必须卖三样东西：
1. 更高产能
2. 更强诊断能力
3. 更接近发行 / monetization 的路径

## 5. 额外加购设计（建议）

### Story Credits Top-up
- 50 Credits = $5
- 150 Credits = $12

### Studio Credits Top-up
- 20 Credits = $10
- 60 Credits = $24

### Seasonal World Pass
- $6.99 - $14.99 / 次
- 用于节庆活动、限定世界、联名 arc

### 年付建议
- 年付默认 **85 折**
- Play: $102 / 年
- Creator: $204 / 年
- Studio: $612 / 年

## 6. 不建议现在承诺的权益

当前不要承诺：
- 无限生成
- 无限 simulate
- 人工逐章改稿
- 稳定 creator 收益分成
- SLA 级人工 support
- “所有会员都能发布作品并获得流量”

原因：这些权益会直接把当前仍在爬坡期的内容质量、审核与人工运营成本打穿。

## 7. 会员文案（用户侧）

### Play Pass
“更完整地进入故事，持续追更你喜欢的世界。”

### Creator Pass
“不只是读故事，也开始塑造属于你的世界。”

### Studio Pass
“把 NarrativeOS 当作你的创作工作台，而不只是阅读产品。”

## 8. 添加进接下来任务中的内容（给 Codex）

## 新增工作流主线：Monetization & Entitlements Track

这条主线应当作为 **并行任务** 插入接下来的 roadmap，
但**不要替代** 当前最重要的内容商业可用性工作（long-route benchmark / weakest-pack diagnostics / cross-pack quality stabilization）。

### Phase M0 — Subscription / Entitlement Foundations

#### Task M0.1 — Tier config & entitlement matrix
实现三档会员的统一配置层：
- `PLAY_PASS`
- `CREATOR_PASS`
- `STUDIO_PASS`

并定义：
- Story Credits monthly allotment
- Studio Credits monthly allotment
- route limits
- private draft/world limits
- early access windows
- submit-for-review monthly quota
- collaborator seat limit
- feature flags

#### Task M0.2 — Metering service
新增可追踪的 metering：
- `story_credits_consumed`
- `studio_credits_consumed`
- reset / rollover rules
- grace period
- insufficient credits behavior

#### Task M0.3 — Subscription state machine
实现最小 subscription lifecycle：
- trialing
- active
- past_due
- grace_period
- canceled
- expired

#### Task M0.4 — Reader gating
Reader 端根据 tier 控制：
- premium world access
- replay / route depth
- chapter continuation gating
- early access banners
- paywall surfaces

#### Task M0.5 — Author gating
Author 端根据 tier 控制：
- draft creation
- simulate / validate
- submit-for-review quota
- analytics lite / pro
- collaborator seats

#### Task M0.6 — Ops / Admin support
Ops 侧新增：
- subscription lookup
- credit adjustments
- abuse / anomaly flags
- entitlement audit trail
- manual grant / revoke

#### Task M0.7 — Analytics
至少埋这些漏斗：
- paywall_view
- upgrade_click
- checkout_start
- checkout_success
- downgrade
- cancel
- churn_reason
- credits_exhausted
- top_up_purchase
- submit_for_review_blocked_by_tier

#### Task M0.8 — Provider boundary
先做 provider abstraction，不要求立即接真实支付：
- `BillingProvider`
- `WebCheckoutProvider`
- `AppStoreReceiptProvider`（stub）
- `GooglePlayBillingProvider`（stub）

### Phase M1 — Paywall & Packaging

#### Task M1.1
Reader / Author 双 paywall：
- Reader 强调世界访问、章节推进、会员特别篇
- Author 强调 draft、simulate、analytics、publish path

#### Task M1.2
实现 top-up flow：
- Story Credits pack
- Studio Credits pack
- seasonal world pass placeholder

#### Task M1.3
实现年付配置与优惠文案

### Phase M2 — Monetization Readiness Validation

#### Task M2.1
新增 monetization dashboard：
- subscriber count by tier
- upgrade / downgrade funnel
- churn by tier
- ARPU / ARPPU
- credits burn by tier
- gross margin proxy by tier

#### Task M2.2
新增 tier correlation report：
- quality vs retention by tier
- credits exhaustion vs churn
- author feature adoption vs upgrade

## 9. 给 Codex 的直接提示词

```text
Goal:
Add a new Monetization & Entitlements track to NarrativeOS without replacing the current cross-pack quality stabilization work.

Important:
Do NOT revert to pack-specific prose tuning.
Do NOT start with real payment integrations.
Do NOT promise unlimited generation.

Design and implement support for 3 membership tiers:
- Play Pass: $10/month
- Creator Pass: $20/month
- Studio Pass: $60/month

Use a two-wallet model:
- Story Credits for reading / chapter continuation / premium route actions
- Studio Credits for authoring / simulate / validate / advanced tools

Required work:
1. Add tier config and entitlement matrix.
2. Add metering service for Story Credits and Studio Credits.
3. Add subscription lifecycle state machine.
4. Add Reader gating.
5. Add Author gating.
6. Add Ops support for entitlement audit and manual adjustments.
7. Add monetization analytics events and dashboards.
8. Add provider boundary for web checkout now, and stubs for App Store / Google Play later.

Constraints:
- Keep current Reader / Author / Ops flows runnable.
- Keep current benchmark and eval flows runnable.
- This monetization track should be parallel to current content-quality work, not a replacement.
- Use configuration and provider abstractions; do not hardcode a single billing path.

First reply format:
1. Task Understanding
2. Entitlement Model Proposal
3. Modules Likely To Change
4. Validation Plan
5. Risks / Assumptions
6. Minimal Deliverable for M0
```
