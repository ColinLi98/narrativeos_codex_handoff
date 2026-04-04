# Phase 1 Summary

- 新增 `ScenePlan / ChapterDraft / IntentPrefill` 结构
- 新增 `src/narrativeos/core/writer.py`
- 新增 `src/narrativeos/core/linter.py`
- 渲染链路开始按 `ScenePlan -> Writer -> Linter -> Presenter` 组织
- 旧 `plan_next_turn*` 路径保持兼容
