# 06. World Pack 标准

## 定义

World Pack 是 NarrativeOS 的内容供给基本单位。
它不是一部现成小说，而是一个可供引擎运行的世界包，至少包括：

- 世界观与规则
- 角色原型
- 场景蓝图
- 因果模板
- 风格包
- 分发与风险配置

## 目录结构建议

```text
worldpack/
  manifest.json
  world_bible.json
  characters.json
  scene_blueprints.json
  karmic_seed_templates.json
  style_pack.yaml
  risk_policy.yaml
  cover_assets/
  localization/
```

## 必填模块

### 1) manifest
- world_id
- title
- version
- author_id
- language
- genres
- risk_rating
- monetization_policy

### 2) world_bible
- premise
- canon facts
- forbidden moves
- geography / factions / timeline
- theme pillars

### 3) characters
至少包含主角组与关键关系图。

### 4) scene_blueprints
至少覆盖：
- setup
- temptation
- trust test
- concealment
- debt activation
- reversal
- rupture
- confession / sacrifice / confrontation
- climax
- aftermath

### 5) karmic_seed_templates
把“说谎”“拖延”“越界保护”“公开羞辱”“替人背债”“真正坦白”等行为抽象成跨世界可复用模板。

### 6) style_pack
指定叙述偏好：
- 视角
- 对白密度
- 描写浓度
- 节奏
- 禁用表达

## 校验规则

发布前必须通过：

1. schema 校验
2. 角色关系图闭合性校验
3. scene blueprint 覆盖度校验
4. risk policy 完整性校验
5. 最少 30 次模拟运行无致命崩坏

## 最低发布标准

一个可发布的 world pack 至少应支持：

- 8 章可读路线
- 2 个有效结局形态
- 2 个以上核心人物关系线
- 3 个以上可成熟的 karmic seed 模板
- 1 套明确风格包
