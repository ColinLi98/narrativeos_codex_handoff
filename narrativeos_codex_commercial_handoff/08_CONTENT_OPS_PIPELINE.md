# 08. 内容生产与运营流水线

## 目标

从“个人写 prompt 试玩”升级为“平台可持续供给内容”的生产流水线。

## 标准流程

```text
Concept Brief
  → World Pack Draft
  → Validation
  → Simulation Batch
  → Editorial QA
  → Risk Review
  → Publish
  → Monitor
  → Iterate / Rollback
```

## 各阶段产物

### 1) Concept Brief
- 世界 premise
- 目标人群
- 题材标签
- 预期 route 数量

### 2) World Pack Draft
- 填写标准 schema
- 角色与关系图
- scene blueprints
- style pack

### 3) Validation
自动发现：
- 缺角色
- 缺 phase coverage
- seed 与 debt 没有兑现路径
- endings 过早可达

### 4) Simulation Batch
自动跑 30~100 条路径，计算：
- 平均章节数
- 章节文本长度
- 角色保真
- 因果成熟率
- route 差异度
- 成本/chapter

### 5) Editorial QA
人工看样章：
- 是否像一章真正可读的内容
- 是否有重复桥段
- 是否有明显工程腔
- 是否值得继续阅读

### 6) Risk Review
处理：
- 权利来源
- 风险等级
- 内容边界
- 标签与分发配置

### 7) Publish
- 生成 world_version_id
- 上架 library
- 开启计费 / entitlements

### 8) Monitor
观察：
- completion
- replay
-付费
-投诉
-内容风险
-模型成本

## 必要后台能力

- 模拟批次任务
- world version 回滚
- 样章对比查看器
- review status board
- world health dashboard
