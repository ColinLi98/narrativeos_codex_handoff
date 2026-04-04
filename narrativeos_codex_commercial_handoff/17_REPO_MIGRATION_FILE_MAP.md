# 17. 仓库迁移映射

本文件用于指导 Codex 把当前 Alpha 仓库迁移为平台化结构。

## 建议目标目录

```text
src/narrativeos/
  core/
    state.py
    karma.py
    planner.py
    search.py
    renderer.py
    critics.py
    policy.py
  worldpacks/
    models.py
    registry.py
    validator.py
  services/
    sessions.py
    authoring.py
    review.py
    billing.py
    analytics.py
  api/
    reader.py
    author.py
    ops.py
  persistence/
    repositories.py
    db.py
  web/
  tests/
```

## 现有模块建议映射

- `models.py` → `core/state.py` + `worldpacks/models.py`
- `memory.py` → `core/karma.py` / `services/sessions.py`
- `search.py` → `core/search.py`
- `scoring.py` → `core/search.py` 或 `core/critics.py`
- `pipeline.py` → `services/sessions.py` / `core/planner.py`
- `api.py` → `api/reader.py`

## 必须新建的模块

- `worldpacks/registry.py`
- `worldpacks/validator.py`
- `services/authoring.py`
- `services/review.py`
- `services/billing.py`
- `services/analytics.py`

## 迁移顺序建议

1. 先迁 `worldpack` 标准与 registry
2. 再迁 session 绑定 world_version
3. 再拆分 services 与 api
4. 最后补 author / ops 功能
