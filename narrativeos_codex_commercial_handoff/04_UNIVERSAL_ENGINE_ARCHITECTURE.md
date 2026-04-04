# 04. 通用引擎架构

## 总体架构

```text
World Pack Registry
    ↓
Session Orchestrator
    ├─ Chapter Planner
    ├─ Karma Engine
    ├─ Route Search
    ├─ Scene Simulator
    ├─ Renderer
    ├─ Critics (consistency / drama / immersion / diversity)
    ├─ Policy Guard
    └─ Metering & Analytics
    ↓
Reader View Model
```

## 1. World Pack Registry
职责：
- 存放 world pack 与版本
- 提供校验与兼容性检查
- 管理发布状态

输入：作者提交的世界资产
输出：可运行的标准化 world version

## 2. Session Orchestrator
职责：
- 读取 session state
- 加载 world version
- 调用 planner / search / renderer / policy / metering
- 写回 chapter 结果与 analytics

## 3. Chapter Planner
职责：
- 根据 story_phase、promises、debts、seeds、reader intent 规划下一章 scene intent
- 决定本章的戏剧任务而不是直接写正文

输出：`ScenePlan`

## 4. Karma Engine
职责：
- 计算人物在愿、伤、毒、债、seed、fate 共同作用下的行为牵引
- 生成和成熟因果种子
- 更新关系债和命运压力

## 5. Route Search
职责：
- 为下一章生成多个 route candidates
- 用评分函数筛选
- 对 भाई 分支施加差异约束

## 6. Scene Simulator
职责：
- 把 scene plan 扩展为多个 beats
- 确保一章内有铺垫、试探、升级、反转、余波

## 7. Renderer
职责：
- 只负责把已决定的 beats 渲染为可读正文
- 支持不同 style pack：`novel_light / novel_lush / manhua_drama`

## 8. Critics
四个最小 critic：
- consistency
- character fidelity
- reader immersion
- diversity

## 9. Policy Guard
职责：
- 根据 world risk profile、reader age band、地区策略、作者权限做裁剪
- 阻止违规生成与越界分发

## 10. Metering & Analytics
职责：
- 记录 token / calls / latency / model tier / cost estimate
- 记录章节完成、选择、付费与投诉事件

## 关键边界

- `Runtime` 只消费标准 schema，不感知作者内部数据来源
- `Renderer` 不负责决定重大剧情
- `Policy Guard` 必须在渲染前与渲染后都可拦截
- `Metering` 必须绑定 session_id / chapter_id / world_version_id
