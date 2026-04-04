from __future__ import annotations

ISSUE_TAXONOMY = {
    "Q01": {"label": "engineering leak", "owning_module": "linter", "fix_hint": "检查 sanitizer / prose linter，移除 event_id、snake_case 与路由箭头。"},
    "Q02": {"label": "meta narration leak", "owning_module": "writer", "fix_hint": "减少“这一章/这一幕/放远一点看”式总结句，改为场景内动作和感受。"},
    "Q03": {"label": "repetition", "owning_module": "writer", "fix_hint": "检查重复 beat 的段落模板，增加动作、对白和细节的差异化写法。"},
    "Q04": {"label": "over-explanation", "owning_module": "writer", "fix_hint": "减少解释句，改成对白、动作与环境共同推进。"},
    "Q05": {"label": "lack of scene detail", "owning_module": "writer", "fix_hint": "补场景物件、动作、声响与人物细微反应。"},
    "Q06": {"label": "character inconsistency", "owning_module": "planner", "fix_hint": "回看角色愿/伤/毒与当前事件的拉力，避免说话与行动突然换人。"},
    "Q07": {"label": "causal discontinuity", "owning_module": "planner", "fix_hint": "检查 promises / debts / seeds / world facts 是否承接到当前章。"},
    "Q08": {"label": "weak choice distinctness", "owning_module": "presenter", "fix_hint": "让 choices 在动机、代价、风险上真正分叉，而不是只换措辞。"},
    "Q09": {"label": "pacing failure / premature ending", "owning_module": "planner", "fix_hint": "检查 hook、ending gate 与章节节奏，避免过早收束或无钩子收尾。"},
    "Q10": {"label": "product continuity failure", "owning_module": "reader_ui", "fix_hint": "检查 Story Feed、Sticky Composer 和 prefill 是否保持连续阅读体验。"},
}


SEVERITY_ORDER = ("low", "medium", "high")
