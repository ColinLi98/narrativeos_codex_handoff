# 潮汐档案 100章压测 Pack

`tide_archive_memory_debt` 是一个 `benchmark-enabled` 的 Lane A 压测 world pack，用来验证 NarrativeOS 在 `100章 / 5卷 / 15弧 / 约20万字` 条件下的长线创作续航。

## 目标

- 题材：近未来海港悬疑 + 情感群像 + 阴谋推进
- 核心命题：当记忆可以被交易，人靠什么承担承诺
- 主要压测问题：`Q03 / Q04 / Q05 / Q09`、角色一致性、延迟回收、中后段续航
- 路线家族：真相优先 / 关系优先 / 生存优先 / 权力优先
- 结局家族：公开揭露 / 私下保全 / 牺牲封口 / 带罪共存

## 角色与结构

- 角色数：10
- 地点数：8
- scene families：10
- distinct role pairs：12
- 长线结构：5 卷、每卷 20 章、每卷 3 弧

卷结构固定为：

- 卷 1 `潮门初裂`：建立世界规则、关系债和第一次错误选择
- 卷 2 `账本上岸`：调查升级、阵营分裂、首次公开代价
- 卷 3 `中潮迷航`：中段疲劳带，专门观察重复、解释增多与角色漂移
- 卷 4 `旧债回潮`：旧债集中结算，路线显著分化
- 卷 5 `终港对证`：85-95 章保持 continuation pressure，96-100 收束但禁止偷懒终结

## Benchmark 用法

标准 6 章：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack tide_archive_memory_debt \
  --database-url sqlite:///narrativeos_beta.db
```

36 / 30 long-route：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack tide_archive_memory_debt \
  --baseline-file tests/long_route_benchmark_baseline.json \
  --max-chapters 36 \
  --min-end-turn-override 30 \
  --database-url sqlite:///narrativeos_beta.db
```

100 章主压测：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack tide_archive_memory_debt \
  --benchmark-mode longform_100 \
  --max-chapters 100 \
  --database-url sqlite:///narrativeos_beta.db
```

100 章 interactive：

```bash
source .venv/bin/activate
python -m src.narrativeos.benchmark.runner \
  --worldpack tide_archive_memory_debt \
  --benchmark-mode longform_100_interactive \
  --max-chapters 100 \
  --database-url sqlite:///narrativeos_beta.db
```

## 人工抽检

固定窗口：

- `1-5`
- `18-22`
- `38-42`
- `58-62`
- `78-82`
- `96-100`

每个窗口至少抽 `2` 章，记录：

- `Q03 / Q04 / Q05 / Q09`
- 角色是否崩
- 选择后果是否在 `3-10` 章内真实回收
- 是否仍有下一章 continuation pressure

## Interactive 检查点

- 第 `15` 章：关系方向轻微改写
- 第 `33` 章：弧线目标从“查真相”切到“先保人”
- 第 `52` 章：补入关键旧记忆，检查 memory consistency 与 promise reconciliation

## 验收阈值

- `completion_ratio = 1.0`
- `longform_gate.passed = true`
- `interactive_longform_gate.passed = true`
- `mid_arc_pass_rate >= 0.85`
- `late_arc_pass_rate >= 0.80`
- `character_drift_rate <= 0.10`
- `promise_unresolved_rate <= 0.12`
- `arc_task_repeat_rate <= 0.15`
- `q09_incidence_rate <= 0.05`
- `volume_climax_spacing_error <= 0.10`
- `scene_detail_density >= 0.06`
- `voice_separation_score >= 0.65`

## Repair Round 1

首轮 contract-driven repair loop 已按三个窗口落到资产层：

- `early 1-10`
  - 目标 issue：`Q03 / Q04`
  - 主资产：`scene_blueprint.archive_anomaly`
  - 已执行：
    - 提高 `dialogue_pressure`
    - 扩 `variation_axes` 到 `information_reveal / object_state`
    - 扩 `detail_anchor_types`
    - 重写 `beats_template`，把起盘从抽象“异常空白”改成更具体的档案、签章、红灯异常
- `mid 30-60`
  - 目标 issue：`Q03 / Q04`
  - 主资产：`scene_blueprint.submerged_return`
  - 已执行：
    - 扩 `variation_axes` 到 `information_reveal / object_state`
    - 扩 `detail_anchor_types`
    - 重写 `beats_template`，把中段回圈改成“残片 / 画稿 / 声纹 / 时间轴”多轴揭示
- `late 80-100`
  - 目标 issue：`Q09`
  - 主资产：`chapter_task tide_archive_memory_debt::series::volume_5::arc_1::task_2`
  - 次级资产：`arc_plan tide_archive_memory_debt::series::volume_5::arc_1`
  - 已执行：
    - 把 `delayed_payoff_window` 收紧到 `1-4`
    - 让 `promise_targets` 只绑定本弧 turn promise
    - 在 `objective / notes` 中显式写入 continuation pressure 义务
    - 给弧线 `completion_conditions` 增补 `next_chapter_hook_intensified`

## Repair Round 2

第二轮重点不是继续扩 scene，而是验证二级修复链是否能稳定落到角色侧资产：

- `early 1-10`
  - 二级资产：`wen_xi.voice_profiles / wen_xi.response_cadence_profiles / wen_xi.character_card`
  - 已执行：
    - 把 `wound_profile.defense_style` 改成“先扣住证据，再用最短的话把人逼到真相前”
    - 把 `speech_traits / action_traits` 改成更短句、更动作承压的表达
    - 扩 `voice_profiles` 的 `opening / pressure / pivot / aftermath / echo / signature_replies`
    - 扩 `response_cadence_profiles` 的 `reaction_lines` 与 `reply_lines`
- `mid 30-60`
  - 二级资产：`he_mo.voice_profiles / he_mo.response_cadence_profiles / he_mo.character_card`
  - 已执行：
    - 把 `wound_profile.defense_style` 改成“先拿残片和声纹说话，再用轻描淡写掩掉真正的站位”
    - 收紧 `speech_traits / action_traits`
    - 扩 `voice_profiles`
    - 扩 `response_cadence_profiles`

第二轮结论：

- repair loop 现在已经能稳定把 `Q03 / Q04` 预填到 `voice_profiles / response_cadence_profiles / character_card`
- 但 focused `longform_100` 复跑后，`early / mid` 的窗口指标仍没有明显下降
- 说明“二级链路做准”这一步已经完成，但当前角色侧修复策略仍然不够强，下一步需要升级到 `scene_realization_contracts / emotion_action_policies` 的成组修复

## Repair Round 3

第三轮不再继续单角色微调，改为 group-level 资产修复：

- 目标：
  - `early 1-10` 的 `Q03 / Q04`
  - `mid 30-60` 的 `Q03 / Q04`
- 主修资产：
  - `scene_realization_contracts["default"]`
  - `emotion_action_policies["default"]`
- 已执行：
  - 给 `false_peace / misrecognition / confession_window / debt_exchange / karma_ripening` 补三组以上 `scene_openings / scene_hooks`
  - 给 `false_peace / misrecognition / confession_window / debt_exchange / karma_ripening` 补三组以上 `entry / pressure / pivot / aftermath / echo` 动作变体
- 本轮意图：
  - 不再靠单角色换说法解决 `Q03 / Q04`
  - 直接让同一窗口里最常复用的 scene function 自身具备更强的开场、动作和结尾差异化

## 报告要求

每次正式压测至少输出：

- 新 Pack 在 `--worldpack all` 里的位置
- strongest / weakest 对比
- 最差 5 章
- 主要问题归因到 `writer / planner / world pack asset / policy` 哪一层
