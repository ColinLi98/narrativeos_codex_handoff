# NarrativeOS 角色因果引擎规范（Karma Character Engine）v0.1

## 目标

把人物从“目标 + 情绪 + 信任”升级为“命、业、毒、愿、惑、债”共同驱动的动态体。

这个规范不是哲学宣言，而是叙事引擎的运行公理：
- 人物不会只按显性目标行动。
- 人物会被习气、创伤、欲望、关系债与自我欺骗牵引。
- 行为不会只产生即时结果，而会生成延迟成熟的因果种子。
- 所谓“命运感”，来自**可见选择**与**不可见牵引**并存。

---

## 一、核心模型：六层人物结构

### 1. 命（Destiny Contract）
角色进入故事时自带的命题与不能绕开的课题。

字段建议：
- `life_theme`: 此生要回答的命题，例如“爱能否不以占有为前提”
- `inescapable_nodes`: 必经节点，例如“被误解”“失去一次最信的人”
- `fated_relations`: 注定纠缠的关系
- `forbidden_escape`: 角色最想绕开的真相
- `endgame_shapes`: 允许的终局形态（觉悟/沉沦/断裂/守愿）

### 2. 业（Karmic Seeds + Debt Ledger）
每次关键行为都会留下种子，不一定立刻成熟。

字段建议：
- `karmic_seeds`: 当前尚未成熟的因果种子
- `debt_ledger`: 欠、负、怨、羞、恩、救赎等关系债
- `ripening_profile`: 哪类情境最容易让种子成熟

### 3. 毒（Five Poisons）
将“五毒”作为驱动力向量，而不是道德标签。

字段建议：
- `greed` 贪：占有、控制、补偿性索取
- `anger` 嗔：反击、防御、惩罚他人
- `delusion` 痴：自我欺骗、合理化、看不清真相
- `pride` 慢：不肯低头、维护自体完整幻象
- `doubt` 疑：不信任、反复试探、迟迟不敢交付

### 4. 愿（Vow / Aspiration）
角色想成为谁，愿不愿意承担代价。

字段建议：
- `vows`: 角色的愿，例如“宁可自己背负，也不让她替我受伤”
- `sacrifice_capacity`: 为愿付出代价的能力
- `truth_tolerance`: 承受真相的能力

### 5. 惑（Mask / Self-Deception）
人物表面说辞与真实动因的差。

字段建议：
- `public_self`: 角色自以为自己是什么样的人
- `shadow_desire`: 不肯承认但真实存在的欲望
- `defense_style`: 回避、操控、冷漠、奉献、讨好、反击
- `core_wound`: 最深的伤，例如“被抛弃”“不配被爱”“永远要证明自己”

### 6. 智（Awakening Potential）
角色是否有能力看见自己，并在关键时刻转向。

字段建议：
- `clarity`: 当前清明度
- `reflection_capacity`: 反思能力
- `repentance_threshold`: 从执念转向觉察的门槛
- `transformation_paths`: 可行的转化路径

---

## 二、建议替换现有 CharacterState

当前 `CharacterState` 只有：
- public_goals
- hidden_goals
- constraints
- beliefs_true / beliefs_false
- emotions
- trust

这对于“工程正确”够用，但不够生成像人的人物。

建议升级为：

```python
@dataclass
class PoisonVector:
    greed: float
    anger: float
    delusion: float
    pride: float
    doubt: float

@dataclass
class VowProfile:
    vows: list[str]
    sacrifice_capacity: float
    truth_tolerance: float

@dataclass
class WoundProfile:
    core_wound: str
    public_self: str
    shadow_desire: str
    defense_style: str

@dataclass
class AwakeningProfile:
    clarity: float
    reflection_capacity: float
    repentance_threshold: float
    transformation_paths: list[str]

@dataclass
class DestinyContract:
    life_theme: str
    inescapable_nodes: list[str]
    fated_relations: list[str]
    forbidden_escape: list[str]
    endgame_shapes: list[str]

@dataclass
class DebtEntry:
    relation_with: str
    debt_type: str  # owed, betrayal, gratitude, shame, rescue, obsession
    magnitude: float
    opened_at_turn: int
    notes: str

@dataclass
class KarmicSeed:
    seed_id: str
    source_event_id: str
    actor: str
    target: str | None
    seed_type: str  # lie, betrayal, mercy, obsession, sacrifice, humiliation
    charge: float
    tags: list[str]
    created_at_turn: int
    ripening_conditions: list[str]
    earliest_turn: int
    latest_turn: int | None
    status: str  # dormant, ripening, resolved, transformed
    transformable_by: list[str]

@dataclass
class CharacterState:
    name: str
    role: str
    public_goals: list[str]
    hidden_goals: list[str]
    constraints: list[str]
    beliefs_true: list[str]
    beliefs_false: list[str]
    emotions: dict[str, float]
    trust: dict[str, float]
    poisons: PoisonVector
    vows: VowProfile
    wound: WoundProfile
    awakening: AwakeningProfile
    destiny: DestinyContract
    debts: list[DebtEntry]
    karmic_seeds: list[KarmicSeed]
```

---

## 三、NarrativeState 需要增加的字段

```python
@dataclass
class NarrativeState:
    ...
    chapter_index: int
    story_phase: str  # setup, rise, midpoint, crisis, climax, aftermath
    min_end_turn: int
    fate_pressure: float
    karmic_weather: dict[str, float]  # 当前世界的因果天气，例如 suspicion/grief/temptation
    unresolved_debts: list[str]
```

### 解释
- `story_phase`: 用于控制哪些事件可以出现
- `min_end_turn`: 防止早结局
- `fate_pressure`: 命运感累计值，越高越容易触发重大揭示或报应
- `karmic_weather`: 当前这一章最强的世界情绪
- `unresolved_debts`: 对应全局债务

---

## 四、EventAtom 需要升级成“会种因果”的事件

建议为 `EventAtom` 增加：

```python
@dataclass
class EventAtom:
    ...
    temptation_vector: dict[str, float]  # 对五毒的引诱方向
    vow_tests: list[str]                 # 测试哪些愿
    wound_triggers: list[str]            # 触发哪些核心伤
    debt_deltas: list[dict[str, Any]]    # 关系债变化
    karmic_seed_creations: list[KarmicSeed]
    karmic_seed_resolutions: list[str]
    awakening_affordances: list[str]     # 忏悔、告白、承认、止念、放手
    concealment_level: float             # 该事件更偏隐瞒还是揭示
    consequence_delay_hint: int          # 后果倾向在几回合后成熟
```

---

## 五、真正的人物决策函数

不要再只看 `goal overlap`。

### 建议决策分数

```python
def choice_score(character, state, event, player_intent):
    desire_pull = surface_goal_alignment(character, event)
    shadow_pull = shadow_desire_alignment(character, event)
    poison_pull = poison_activation_score(character, state, event)
    vow_pull = vow_alignment(character, event)
    wound_pull = wound_trigger_score(character, event)
    debt_pull = debt_pressure_score(character, state, event)
    karma_pull = ripening_seed_pressure(character, state, event)
    wisdom_resistance = awakening_resistance(character, event)
    fate_pull = destiny_alignment(character, state, event)

    return (
        0.12 * desire_pull
        + 0.14 * shadow_pull
        + 0.16 * poison_pull
        + 0.12 * vow_pull
        + 0.10 * wound_pull
        + 0.12 * debt_pull
        + 0.12 * karma_pull
        + 0.08 * fate_pull
        - 0.10 * wisdom_resistance
    )
```

### 核心原则
人物不是选“最优解”，而是选：
- 最符合自己习气的
- 最能保护自我叙事的
- 最能暂时逃避痛苦的
- 或在极少数时刻，最接近愿与真相的

这才像人。

---

## 六、因果不是即时奖惩，而是“延迟成熟”

这是最关键的一层。

### KarmicSeed 运行逻辑
一个关键行为会留下种子，例如：
- 对爱的人说半真半假的话
- 当众羞辱某人
- 以保护之名实施控制
- 为别人承担罪责
- 关键时刻退缩

这些不会立刻结束，而是生成 `KarmicSeed`：

```python
seed = KarmicSeed(
    seed_id="seed_half_truth_001",
    source_event_id="secret_meet_lin_wan",
    actor="yu_cheng",
    target="lin_wan",
    seed_type="concealed_truth",
    charge=0.72,
    tags=["love", "secrecy", "doubt"],
    created_at_turn=3,
    ripening_conditions=["trust_request", "third_party_reveal", "public_crisis"],
    earliest_turn=5,
    latest_turn=10,
    status="dormant",
    transformable_by=["full_confession", "sacrifice", "mutual_truth"]
)
```

### 成熟规则
种子成熟时，不一定只有一种表现：
- 报应：原先隐瞒的真相在更坏的时刻曝光
- 反噬：角色以为保护了对方，实际上伤得更深
- 兑现：当年的善意终于被理解
- 转化：原本会变成仇怨的因果，被告白或牺牲化解

这样故事才会有“很多年后才明白”的重量。

---

## 七、把“五毒”从标签变成动态激活值

不是给角色一个固定 `greed=0.7` 就结束。

应当有：
- 基线值 `baseline`
- 场景触发 `activation`
- 压力放大 `stress_multiplier`
- 智慧抵消 `clarity_offset`

### 示例
林绾平常 `doubt=0.35`，但在：
- 被隐瞒
- 旧伤被触发
- 第三方介入
- 自尊受损

时会瞬间升到 `0.81`，此时她就更可能做出：
- 试探
- 先拒绝再靠近
- 说反话
- 用冷漠保护自己

于是人物会像真人，而不是参数木偶。

---

## 八、关系不要只用 trust，要改成“关系债务图”

建议你保留 `trust`，但新增更真实的关系维度：

- `attachment` 依恋
- `resentment` 怨
- `shame` 羞
- `obligation` 欠
- `projection` 投射
- `possession` 占有欲
- `gratitude` 恩
- `fear` 对失去或重演创伤的恐惧

这样“爱”才不会被简化成一个数。

---

## 九、剧情选择应该从“推进什么事”改成“逼出哪种人性”

每一章的场景目标不只是推进情节，还要推进一种内在矛盾。

### 场景功能建议
- `temptation`: 诱发五毒
- `mask_crack`: 面具裂开
- `debt_exchange`: 欠与还
- `misrecognition`: 误认、误会、投射
- `truth_trial`: 真相试炼
- `mercy_vs_control`: 爱与控制对撞
- `humiliation`: 自尊受创
- `confession_window`: 给出坦白机会
- `karma_ripening`: 旧因成熟
- `vow_payment`: 以代价兑现愿
- `false_peace`: 表面平静，实则埋下更重的后果

优秀的剧情不是发生了很多事，而是人物一次次被迫面对自己。

---

## 十、终局不能只有 happy / bad，要有四种真实命运

建议默认四类结局：

### 1. 沉沦
人物明知道，却还是顺着毒与欲走下去。

### 2. 伪觉醒
人物说出了正确的话，但核心模式没变，只是学会更体面地重复旧错误。

### 3. 断裂
人物看见真相，却承受不起，最终失去关系、自我或理想。

### 4. 觉悟
人物不一定赢得世俗结果，但看见了自己的毒与执，愿意承担代价，不再继续制造同样的因。

这四种结局，比“HE/BE”更像真实人生。

---

## 十一、可直接在当前 repo 中新增的文件

### 新增
- `src/narrativeos/karma.py`
- `src/narrativeos/character_engine.py`
- `src/narrativeos/fate.py`
- `src/narrativeos/relationship_graph.py`
- `src/narrativeos/scene_functions.py`
- `tests/test_karma.py`
- `tests/test_five_poisons.py`
- `tests/test_destiny_gates.py`

### 修改
- `src/narrativeos/models.py`
- `src/narrativeos/scoring.py`
- `src/narrativeos/memory.py`
- `src/narrativeos/search.py`
- `src/narrativeos/pipeline.py`
- `specs/narrative_state.schema.json`
- `specs/event_atom.schema.json`
- `examples/demo_initial_state.json`
- `examples/demo_event_atoms.json`

---

## 十二、最小实现路径（不求一步到位）

### Phase 1：先把“毒、愿、伤、债”补进人物
只改 schema 和评分，不动大前端。

### Phase 2：加入 `KarmicSeed` 和 `ripening_engine`
让行为有延迟后果。

### Phase 3：加入 `story_phase + min_end_turn`
防止早结局。

### Phase 4：把 scene_function 改成更有“人性冲突”的场景功能
从推进事件改成推进执念与代价。

### Phase 5：渲染层把这些内在冲突写成正文
此时才能真正接近小说。

---

## 十三、一个最重要的产品原则

不要把“人性本恶”写成程序里的结论。

更好的做法是把它写成默认戏剧先验：
- 人物首先会自保
- 其次会合理化自己
- 最后才可能选择真相

这样你既保留了你要的黑暗真实，也保留了人物觉悟与转化的空间。

因为真正动人的作品，不是所有人都坏，
而是所有人都在自己的毒里挣扎，偶尔有人愿意停下来，看见它，然后不再继续传递下去。
