# 13. 数据与服务架构

## 核心服务

### 1) API Gateway
统一鉴权、路由、速率限制。

### 2) World Registry Service
管理 world packs、版本、发布状态。

### 3) Session Service
管理 reader session、chapter records、choices、replays。

### 4) Generation Orchestrator
调用 planner / karma / search / renderer / critics / policy。

### 5) Authoring Service
管理作者草稿、验证、模拟任务、发布申请。

### 6) Moderation Service
审核 world packs、抽检章节、处理举报。

### 7) Billing & Metering Service
管理 entitlements、credits、usage meters。

### 8) Analytics Service
采集 reader/author/ops 事件与报表。

## 数据存储建议

- Postgres：事务性主数据
- Object Storage：world assets / chapter snapshots / cover assets
- Redis：session cache / hot shelf cache
- Queue：simulation jobs / review jobs / analytics events

## 关键主键

- `world_id`
- `world_version_id`
- `session_id`
- `chapter_id`
- `review_id`
- `meter_id`
- `entitlement_id`

## 可观测性

所有生成流程必须带：
- trace_id
- request_id
- session_id
- world_version_id
- model_policy_version
