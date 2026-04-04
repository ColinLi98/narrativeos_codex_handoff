# Provenance Policy

## 目的

本仓库允许参考公开产品与公开工程的高层思路，但不允许复制任何未明确授权的代码、prompt、目录实现或测试内容。

## 硬约束

### 1. 禁止使用泄漏源码

禁止将以下来源的代码、prompt、配置、目录结构一比一复制或改写并入本仓库：

- `cloud-code`
- Claude Code 泄漏源码
- 任何未明确授权的 Anthropic 内部实现

### 2. 官方 public repo 也不能默认自由复制

即使某些公开仓库可访问，也不能把它们的代码直接并入本项目。

允许的只有：

- 阅读公开资料
- 提炼高层架构思想
- clean-room 重写

### 3. 允许借鉴的层级

仅允许借鉴：

- 插件式扩展思想
- hook 体系思想
- workflow 分层思想
- presenter / view-model 解耦思想
- 安全 / lint / policy 守卫思想

### 4. 禁止借鉴的层级

禁止复制：

- 源码
- prompt 文本
- 命名体系
- 注释
- 目录与文件一比一复刻
- 测试用例

## 本仓库执行规则

任何外部参考如果影响实现，必须满足：

1. `public idea inspiration`
2. `clean-room reimplementation`
3. `no code copied`

## 提交说明要求

后续 PR / 提交说明中，若涉及外部灵感，必须写清：

- 借鉴来源
- 借鉴层级（思想 / 架构 / 交互，不是代码）
- clean-room 说明

## 当前项目适用范围

本政策适用于：

- runtime
- world pack
- authoring
- review / billing / analytics
- Reader / Author / Ops 前端

## 一句话原则

NarrativeOS 可以吸收公开思想，但只能用 **clean-room** 的方式重写，不允许混入任何可能与外部具体实现混淆的代码或 prompt。
