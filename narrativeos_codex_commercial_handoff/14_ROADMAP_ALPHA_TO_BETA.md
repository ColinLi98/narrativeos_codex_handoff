# 14. Alpha → Beta 路线图

## Phase 0：抽离与定界（1~2 周）
目标：确认哪些是 runtime，哪些是 world-specific assets。

交付：
- runtime vs assets 清单
- world pack schema v1
- repo migration map

## Phase 1：多世界运行时（2~4 周）
目标：支持至少 3 个 world packs 在同一 runtime 中运行。

交付：
- world registry
- session 绑定 world_version
- multi-world tests

## Phase 2：作者工具后端（2~4 周）
目标：支持创建、验证、模拟 world pack。

交付：
- author draft APIs
- validation APIs
- simulation jobs

## Phase 3：评测与审核（2~3 周）
目标：发布前必须有 simulation report 与 risk review。

交付：
- eval metrics pipeline
- review queue
- publish / rollback flow

## Phase 4：Reader 商业化骨架（2~4 周）
目标：Reader 具备 credits / entitlements / shelf / paid continue。

交付：
- entitlements
- metering
- paid route gates

## Phase 5：Ops 与成本控制（2~3 周）
目标：看得到成本、付费、质量、投诉、下架能力。

交付：
- ops dashboard backend
- world health metrics
- cost dashboard

## Phase 6：Beta 验证（持续）
目标：验证多世界、多题材的留存与付费。

最小进入条件：
- 3 个高质量 world packs
- 8+ 章平均路线长度
- 商业化、审核、回滚、metering 可用
