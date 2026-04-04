# Memory 与 Promise Ledger

## Memory 分层

### Canon Memory
世界观、地理、时代规则、不可改变设定。

### Episodic Memory
已经发生的事件、时间顺序、谁见过谁、谁说过什么。

### Social Memory
信任、债务、盟约、怨恨。

### Promise Ledger
由前文显式开启的叙事债务。

## Promise Ledger 字段
- promise_id
- description
- opened_at_turn
- due_by_turn
- holders
- fulfillment_modes
- stakes
- tags
- status

## 为什么它重要
好的结局不是“随机生成出来”的，而是被前文开出的账逼出来的。

## 兑现规则建议
- 每个重要 promise 要有最晚兑现窗口
- 允许多种兑现方式
- 不兑现要有后果
- critic 需要检查 promise 是否长期悬空
