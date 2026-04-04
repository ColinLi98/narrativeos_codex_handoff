# Narrative State Schema 说明

## 设计目标
状态层是整个系统的真相源，而不是 prose summary。

## 顶层字段

### `world_facts`
当前世界中客观成立的事实集合，例如：
- `spring_exam_announced`
- `family_reputation_fragile`

### `timeline`
已经发生的重要事件摘要，便于 replay 与分析。

### `characters`
每个角色单独维护：
- public goals
- hidden goals
- constraints
- beliefs true / false
- emotions
- trust map

### `open_promises`
未兑现的叙事承诺。
这是避免“结局像抽签”的关键。

### `tension`
0 到 1 的张力值。

### `themes`
主题推进度，例如：
- destiny
- duty
- selfhood
- love
- reputation

### `player_intent`
玩家当前意图向量，不等于文字输入本身。

### `recent_scene_functions`
最近使用过的场景功能，用于避免：
- 连续 exposition
- 连续 confession
- 连续 confrontation

### `route_fingerprint`
用于 novelty 计算的轨迹指纹。

## 重要原则

1. 世界真实 ≠ 角色所知
2. 角色 A 所知 ≠ 角色 B 所知
3. 状态要支持局部汇合，但保留后果疤痕
4. 任何 prose 都不应成为唯一记忆载体
