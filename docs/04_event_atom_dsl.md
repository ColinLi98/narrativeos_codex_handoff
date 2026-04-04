# Event Atom DSL

## 为什么要有事件原子
系统真正搜索的是“下一步发生什么”，而不是“下一段怎么写”。

## 一个事件原子的最小组成

- `event_id`
- `title`
- `summary`
- `actors`
- `scene_function`
- `tags`
- `preconditions_all`
- `forbidden_if_any`
- `world_fact_deltas_add`
- `world_fact_deltas_remove`
- `belief_updates`
- `trust_deltas`
- `emotion_deltas`
- `promises_open`
- `promises_close`
- `tension_delta`
- `theme_impacts`
- `agency_affordances`
- `rating_ceiling`
- `convergence_key`

## scene_function 的建议枚举
- exposition
- setup
- temptation
- commitment
- discovery
- confrontation
- reversal
- sacrifice
- ordeal
- reveal
- consequence
- ending

## convergence_key 的作用
用于把分支从树结构收束为 DAG，例如：

- `ending_honors`
- `ending_elopement`
- `ending_reform`

注意：允许汇合，但汇合时状态不能抹平。
