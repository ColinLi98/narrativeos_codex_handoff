# 10. 评测、质量与指标体系

## 一、离线评测

### 叙事质量
- `causal_consistency`
- `character_fidelity`
- `promise_payoff_rate`
- `karma_ripening_plausibility`
- `ending_readiness`
- `branch_novelty`
- `reader_immersion`
- `engineering_leak_rate`

### 产品代理指标
- `mean_chapter_length`
- `mean_route_length`
- `choice_click_entropy`
- `chapter_generation_cost`
- `policy_block_rate`

## 二、在线指标

Reader：
- `chapter_completion_rate`
- `next_chapter_continue_rate`
- `route_replay_rate`
- `favorite_world_rate`
- `purchase_conversion`
- `refund_or_complaint_rate`

Author：
- `draft_to_publish_rate`
- `validation_fail_rate`
- `simulation_pass_rate`

Ops：
- `review_backlog`
- `policy_violation_rate`
- `cost_per_paid_chapter`

## 三、自动回归测试

每次提交至少跑：

1. schema validation tests
2. deterministic state update tests
3. early-ending prevention tests
4. text leakage tests
5. multi-world loading tests
6. cost metering tests
7. world publish / rollback tests

## 四、黄金集

需要维护：
- 3 个世界
- 每个世界 20 条黄金路由
- 每条路由至少 8 章
- 每章有人工标注的质量点评

## 五、上线阈值建议

Beta 前至少满足：
- 平均路线长度 >= 8 章
- 文本泄漏率 <= 1%
- 自动模拟中角色崩坏率 <= 5%
- 完成章节成本落在可控区间
