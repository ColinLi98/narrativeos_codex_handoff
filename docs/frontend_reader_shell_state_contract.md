# Frontend Reader Shell State Contract

版本：2026-04-17

目的：
- 为 Reader shell v2 提供最小状态合同
- 把当前 Reader 壳层从巨型共享状态里收窄到可替换 shell 所需的最小面

## ShellState

仅保留以下字段：

| 字段 | 类型 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `activeProduct` | `string` | `reader` | 当前产品视图 |
| `authPage` | `string \| null` | `null` | 当前 auth route |
| `debug` | `boolean` | `false` | debug/internal mode |
| `startupRouteProduct` | `string \| null` | `null` | 启动时路由 product |
| `startupRouteWorkspace` | `string \| null` | `null` | 启动时路由 workspace |
| `readerWorkspace` | `landing \| read` | `landing` | Reader 工作区 |
| `lastReaderView` | `experience \| storybook \| backstage` | `experience` | 离开 backstage 前的视图 |

## ReaderShellState

仅保留以下字段：

| 字段 | 类型 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `worldId` | `string \| null` | `null` | 当前世界 |
| `worldVersionId` | `string \| null` | `null` | 当前世界版本 |
| `readerId` | `string` | `reader_demo` | 当前 reader/account 标识 |
| `readerAuthSession` | `object \| null` | `null` | Reader 登录态 |
| `sessionId` | `string \| null` | `null` | 当前 Reader session |
| `currentBundle` | `object \| null` | `null` | 当前 world/example bundle |
| `sessionLibrary` | `array` | `[]` | 可恢复 session 列表 |
| `authoredWorkLibrary` | `array` | `[]` | 作者作品入口列表 |
| `currentState` | `object \| null` | `null` | 当前 narrative state |
| `latestStep` | `object \| null` | `null` | 最近成功推进的章节结果 |
| `latestStepFailure` | `object \| null` | `null` | 最近失败推进结果 |
| `continuityContract` | `object \| null` | `null` | Reader continuity contract |
| `intentPrefill` | `object \| null` | `null` | 推荐起笔句与压力提示 |
| `replay` | `object \| null` | `null` | replay payload |
| `sessionMedia` | `object` | `{ coverImage: "", atmosphereImage: "" }` | 当前 session 的封面与章节插图 URL |
| `readerEntitlements` | `array` | `[]` | Reader entitlement 列表 |
| `readerSubscription` | `object \| null` | `null` | Reader subscription payload |
| `readerCheckoutSession` | `object \| null` | `null` | 最近 checkout session |
| `pendingCheckoutContext` | `object \| null` | `null` | checkout return 恢复上下文 |
| `activeView` | `experience \| storybook \| backstage` | `experience` | 当前 Reader 子视图 |

## 状态不变式

- `activeProduct !== "reader"` 时，Reader shell 只保留状态，不主动渲染
- `readerWorkspace === "landing"` 时，不要求存在 `sessionId`
- `readerWorkspace === "read"` 时，允许以下任一状态驱动渲染：
  - `latestStep`
  - `latestStepFailure`
  - `sessionId + currentBundle`
- `sessionMedia.coverImage` / `sessionMedia.atmosphereImage` 为渐进增强字段，缺失时 Reader 必须保留文字/渐变 fallback
- `readerWorkspace === "read"` 且 Reader shell v2 启用时，`#reader-shell-v2` 必须移除 `is-hidden` 并真实显示 Storybook / Experience 内容，不能只把 replay 正文渲染进隐藏 DOM
- `continuityContract.status === "payment_required"` 时，必须保留当前 session 路径
- `continuityContract.status === "quality_guard_failed"` 时，必须保留当前 session、上一章上下文和 retry path
- `pendingCheckoutContext` 必须至少能恢复：
  - `accountId`
  - `sessionId`
  - `readerWorkspace`
  - `activeView`

## Legacy 字段

以下 Reader 旧状态字段视为 legacy，不进入 v2 首版合同：
- `shelfWorlds`
- `latestPreview`
- `selectedIntentOverride`
- `selectedReplayIndex`
- `sessionPaywall`
- `pendingCheckoutSessionId`
- `pendingCheckoutStatus`
- `continuityDiagnostics`
- `activeTone`
- `activeAuthoredWorkPreview`

这些字段可以暂时继续存在于旧 runtime，但新 Reader shell 首版不应依赖它们作为核心合同。
