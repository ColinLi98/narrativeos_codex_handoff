# 当前生成链路（Current Generation Pipeline）

## 目标

这份文档描述 NarrativeOS 当前真实存在的章节生成链路，并明确：

- 哪些结构是内部结构
- 哪些结构是用户可见内容
- 哪些地方仍有 meta / engineering 泄漏风险

## 当前主链路

```text
Reader Input
  -> intent parser
  -> planner (scene intent / chapter planning)
  -> beat simulation / candidate search
  -> writer-ish rendering
  -> prose sanitizer
  -> presenter
  -> Reader View Model
  -> frontend Story / Composer / Backstage
```

## 当前模块边界

### 1. Planner 输入

当前入口主要来自：

- `src/narrativeos/pipeline.py`
- `src/narrativeos/search.py`
- `src/narrativeos/scoring.py`

输入包括：

- `NarrativeState`
- `WorldBible`
- `EventAtom` 候选集
- `player_intent`
- critic / weights / scene intent 规则

当前 Planner 会直接处理：

- `SceneIntent`
- `SceneBeat`
- `ChapterPlan`
- beat 选择与 scene progression

### 2. Writer / Renderer 输出

当前“正文初稿”与“展示文本”主要仍混在：

- `src/narrativeos/rendering.py`

目前这个层同时承担了：

- scene 转 prose
- style 变体
- 对白生成
- 动作线补写
- story card 文案

这意味着它还没有和 planner / presenter 完整解耦。

### 3. Presenter 输出

当前 Presenter 在：

- `src/narrativeos/presenter.py`

负责：

- 将清洗后的正文封装进 `NarrativeViewModel`
- 输出 `chapter_title / recap / body / scene_card / choices / relationship_hints`

这是当前最接近“用户层”的正式结构。

### 4. Front-end View Model

当前前端主要消费：

- `reader_view`
- `rendered_scene`
- `replay`
- `candidate/scored/debug`（幕后解析）

主要文件：

- `src/narrativeos/web/index.html`
- `src/narrativeos/web/app.js`

当前问题是：

- Reader 主区仍然带有控制台遗留布局
- Story Feed 与 Sticky Composer 还没有成为真正一等公民
- Author / Ops 已有骨架，但信息层次还偏“内测工具”

## 当前用户可见层 vs 内部层

### 用户可见层

- `NarrativeViewModel`
- Reader Mode 正文
- Storybook 图文内容
- Reader choices
- relationship hints

### 内部结构层

- `SceneIntent`
- `ChapterPlan`
- `SceneBeat`
- `ScoredCandidate`
- `critic_trace`
- `route candidates`
- `KarmicSeed`
- `DebtEntry`
- `cross_pressure_threads`

### 当前边界风险

尽管已经有 `presenter.py / sanitizer.py`，但以下风险仍在：

- 渲染层自己直接写解释句
- writer-style prose 和 presenter-style prose 还没彻底分层
- debug 词汇有时仍可能从 renderer 混到正文
- 前端在部分视图里仍读 `rendered_scene` 而不只读清洗后的 `reader_view`

## 当前明确的 meta / engineering 泄漏点

### 已知高风险模式

- `第X拍`
- `第X幕`
- `这一章`
- `从这里起`
- `如果把这一章放远一点看`
- `a -> b`
- snake_case token
- `event_id / seed_id / debt_type / endgame_shape / poison`

### 泄漏来源

1. `rendering.py`
   当前 prose 模板中仍会主动产出部分“作者总结句 / 规划总结句”。

2. `sanitizer.py`
   当前更像简单的 token 清洗器，而不是完整 prose linter。

3. `frontend`
   当前 Reader 已以 `reader_view` 为主，但部分辅助区块仍可能回退到 `rendered_scene`。

## 下一步拆分建议

### 目标边界

```text
planner.py
  -> ScenePlan (纯结构)

writer.py
  -> ChapterDraft (纯正文初稿)

linter.py
  -> cleaned_prose + metrics

presenter.py
  -> NarrativeViewModel
```

### 原则

- Planner 不输出用户 prose
- Writer 不知道前端结构
- Linter 不参与剧情决策
- Presenter 不回读 planner/debug 内部结构
