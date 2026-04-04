# 11. 商业化与单位经济骨架

## 目标

让商业化能力成为运行时和内容系统的一部分，而不是临上线再补支付页面。

## 产品分层

### 1) Free Tier
- 公开世界的试读章节
- 每日有限 credits
- 可看但不一定能继续高级路线

### 2) Credit Packs
- 按章节 / route / premium world 消耗
- 适合作为单次低门槛付费

### 3) Subscription
- 月度 credits
- 世界 pass 折扣
- 高优先队列
- 作者专区内容

### 4) Creator Revenue
- 按 `net receipts after channel fees / tax / refunds` 分成
- world-level、route-level、subscription pool-level 都可计提

## 不建议做的事情

- 不承诺“无限生成”
- 不用 gross GMV 直接给作者算 80%
- 不把所有付费形式都绑定 app 内数字购买
- 不在没有 metering 和 refund tracking 时开放 creator payout

## 最小计费实体

- `entitlement`：用户获得了什么权限
- `meter_record`：这次继续生成用了多少额度/成本
- `access_policy`：本章节/本路线是否收费、如何收费

## 成本控制建议

- 试读世界使用轻量模型路由
- 付费章才调用高质量渲染模式
- 对回放、复看优先缓存已生成章节
- 模拟批次与线上阅读分开算成本池

## 初期营收建议

优先级：
1. Web 端 credit packs
2. Subscription credits
3. World passes
4. Author subscriptions

暂缓：
- 复杂联运
- 多档创作者分账
- 影视代理等远端收入
