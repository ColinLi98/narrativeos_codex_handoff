# 05. 通用领域模型

## 核心实体

### 1) WorldPack
一个可发布、可版本化、可审核的世界包。

关键字段：
- `world_id`
- `version`
- `title`
- `genre`
- `risk_rating`
- `canon_rules`
- `style_profile`
- `characters`
- `scene_blueprints`
- `ending_policies`

### 2) CharacterArchetype
世界级角色定义。

包含：
- 基础身份与关系
- DestinyContract
- PoisonVector
- VowProfile
- WoundProfile
- AwakeningProfile
- speech / action traits

### 3) CharacterInstance
会话内人物状态实例。

包含：
- 当前 belief
- 当前情绪与 tension
- 当前 debts / seeds / clarity
- 当前对其他角色的 attachment / shame / fear / obligation

### 4) SceneBlueprint
通用场景蓝图。

描述：
- 戏剧功能
- 适用 story phase
- 参与角色条件
- 可触发的 wound / vow / poison
- 可创建或成熟的 karmic seed

### 5) KarmicSeedTemplate
业种子模板。

描述：
- `seed_type`
- `charge_formula`
- `ripening_conditions`
- `transformation_paths`
- `resolution_styles`

### 6) StorySession
某位读者在某世界版本上的一个运行实例。

描述：
- `session_id`
- `reader_id`
- `world_version_id`
- `story_phase`
- `chapter_index`
- `narrative_state`
- `entitlements_snapshot`

### 7) ChapterRecord
已生成的一章。

描述：
- `chapter_id`
- `plan`
- `rendered_body`
- `choices`
- `cost_estimate`
- `review_flags`

### 8) RouteOffer
读者面前的一个命运选择。

描述：
- 表面行为
- 内在动机
- 预期代价
- 标签
- access tier / price tier

### 9) ReviewRecord
审核记录。

### 10) Entitlement & Meter
权限与额度。

## 设计原则

1. **World-level 与 Session-level 分离。**
2. **Schema 先能表达，再谈模型优化。**
3. **任何可卖内容都必须可追溯到 world version。**
