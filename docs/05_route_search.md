# 路线搜索与评分

## 搜索目标
搜索“接下来发生哪一个事件”以及“看两步之后会不会走崩”。

## v0 推荐算法
- Hard filter
- Scoring
- Beam search (depth=2, width=3)

## 后续升级
- MCTS
- Learned heuristics
- Retrieval-augmented candidate generation
- Critic-guided search

## 显式评分函数

```text
Score =
0.28 * causal_consistency
+ 0.20 * character_fidelity
+ 0.16 * dramatic_tension_delta
+ 0.12 * user_agency_alignment
+ 0.10 * thematic_resonance
+ 0.09 * branch_novelty
+ 0.05 * pacing_quality
```

## 解释

### causal_consistency
前提条件、设定、时间线、已知/未知信息是否成立。

### character_fidelity
角色行为是否符合长期欲望、约束与情绪。

### dramatic_tension_delta
这一事件是否让戏剧曲线朝正确方向推进。

### user_agency_alignment
是否与玩家的意图向量形成呼应，而不是完全无视玩家。

### thematic_resonance
是否推进本作的命题，而不是只堆事情。

### branch_novelty
是否和兄弟分支足够不同。

### pacing_quality
是否避免连续重复同类场景函数。

## Hard constraints 永远高于 score
非法事件不能靠高分翻盘。
