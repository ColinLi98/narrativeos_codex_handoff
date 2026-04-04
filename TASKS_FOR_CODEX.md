# 交给 Codex 的任务清单

## 总目标

把 NarrativeOS starter repo 补成一个可运行的 MVP 后端，满足：

- 输入世界观、当前状态、玩家意图
- 生成候选事件
- 过滤非法事件
- 显式打分
- 选择最优 route
- 输出结构化结果与自然语言片段
- 保留可评测、可回放、可解释的数据

## 建议执行顺序

### Phase 1：稳固核心引擎
1. 阅读 `README.md`、`docs/`、`specs/`
2. 确认 `pytest` 全绿
3. 扩展 `models.py`，保证 Schema 与 JSON round-trip 一致
4. 为 `memory.py` 增加更多状态迁移测试
5. 为 `canon.py` 增加更多 hard constraints

**验收标准**
- 所有测试通过
- `examples/` 里的 JSON 都能完整反序列化
- `demo.py` 连续运行 3 次输出稳定

### Phase 2：候选事件生成器
1. 实现 `candidate_provider` 接口
2. 增加两种实现：
   - `StaticCandidateProvider`：从事件池过滤
   - `LLMCandidateProvider`：从 Prompt + 世界状态生成
3. 生成的 event atom 必须满足 `specs/event_atom.schema.json`

**验收标准**
- 每一步最少产出 6 个候选事件
- 非法事件过滤后剩余 >= 3 个
- 可输出 debug score

### Phase 3：critic loop
1. 增加：
   - consistency critic
   - drama critic
   - diversity critic
2. critic 可以先规则实现，再升级为 LLM + rule hybrid
3. 允许 critic 返回：
   - `accept`
   - `revise`
   - `reject`

**验收标准**
- 对样例世界能识别人物崩坏、时间冲突、重复场景
- 搜索结果中包含 critic 解释

### Phase 4：文本渲染层
1. 事件决定后再渲染 prose
2. 分离 narrator voice / character voice / UI summary
3. 支持 3 个输出层：
   - concise summary
   - interactive scene
   - premium prose

**验收标准**
- 同一事件可切换不同文风渲染
- 逻辑层不受文风层污染

### Phase 5：API 与持久化
1. 补全 FastAPI endpoints
2. 加入 SQLite / Postgres repository layer
3. 保存：
   - world bible
   - session state
   - event trace
   - critic trace
   - promise ledger
4. 增加 replay endpoint

**验收标准**
- 可以创建 world、session、step
- 可以回放任意一步 route

### Phase 6：创作者控制面板
1. 支持创作者上传：
   - canon anchors
   - forbidden moves
   - theme targets
   - merge policy
   - darkness ceiling
2. 支持每个 world 独立评分权重

**验收标准**
- 同一底层引擎可以驱动 2 个风格明显不同的 world

## 不要做的事

- 不要把全部逻辑塞进一个 prompt
- 不要先做全量前端再回头补引擎
- 不要把“多样性”简化成 temperature 调大
- 不要只用长 summary 作为长期记忆
- 不要让角色共享全知视角
