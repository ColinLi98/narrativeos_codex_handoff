from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Sequence, Tuple


LONG_ROUTE_QUALITY_METADATA_KEY = "long_route_quality_budget"

DEFAULT_READER_CHOICE = "顺着此刻的局势先退半步，再找一个更稳的开口。"

STOCK_REFRAIN_REPLACEMENTS: Dict[str, Sequence[str]] = {
    "眼前这一处": ("眼前", "这道裂口", "当前线索"),
    "这一处": ("这里", "此刻", "眼前", "这道裂口"),
    "真话窗口": ("开口的时机", "那道短暂的缝隙", "能说实话的一刻"),
    "把每一步都接住": ("把眼前这一步稳住", "先守住当前的转圜", "让下一步落在实处"),
    "别再漏掉": ("别再放过关键处", "不能再让线索滑开", "别让这处空过去"),
    "真正要转向的那句终于逼到眼前": ("那句该说的话终于贴近眼前", "局面逼出必须回应的一句", "被拖住的回答终于到了近前"),
    "被压回去的": ("没说出口的", "被藏住的", "被按下去的"),
    DEFAULT_READER_CHOICE: (
        "先稳住眼前这一处，再顺着露出的线索追下去。",
        "先接住当前的变化，再换一个更清楚的问法。",
        "先把局面收稳，再逼近下一处没有说完的地方。",
    ),
}
STOCK_REFRAIN_KEEP_LIMITS: Dict[str, int] = {
    "眼前这一处": 1,
    "这一处": 2,
}

BROKEN_SLOT_PATTERNS: Sequence[Tuple[re.Pattern[str], str]] = (
    (re.compile(r"被压回去的\s*[、，]\s*"), "被压回去的话，"),
    (re.compile(r"(?P<prefix>[\u4e00-\u9fff]{2,12}的)\s*[、，]\s*(?=(?:并|也|才|就|却|仍|还|没有|不|把|被|让|在|从|沿|往))"), r"\g<prefix>事，"),
    (re.compile(r"(?P<prefix>[\u4e00-\u9fff]{2,12}的)\s*[、，]\s*(?=[。！？；\n]|$)"), r"\g<prefix>事"),
)
META_VISIBLE_REPLACEMENTS: Sequence[Tuple[re.Pattern[str], str]] = (
    (re.compile(r"如果把这一章放远一点看"), "把眼前这一幕放远一点看"),
    (re.compile(r"这一章"), "这一幕"),
    (re.compile(r"从这里起"), "从这里开始"),
    (re.compile(r"更糟的是"), "更紧的是"),
    (re.compile(r"真正厉害的是"), "真正压住人的地方在于"),
)
SCENE_CARD_TEXT_FIELDS = ("title", "summary", "quote", "pull_quote")
SCENE_CARD_LIST_FIELDS = ("story_beats", "beats", "visual_details")

LOCATION_ANCHOR_PER_CHAPTER_MAX = 3
LOCATION_ANCHOR_GLOBAL_SOFT_MAX = 150
STOCK_REFRAIN_GLOBAL_MAX = 8
CHOICE_TEXT_GLOBAL_MAX = 2
RECENT_CHOICE_WINDOW = 40


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _stable_index(seed: int, size: int) -> int:
    if size <= 0:
        return 0
    return abs(int(seed or 0)) % size


def clean_broken_reader_slots(text: str) -> Tuple[str, Dict[str, Any]]:
    cleaned = str(text or "")
    repairs: List[Dict[str, Any]] = []
    for pattern, replacement in BROKEN_SLOT_PATTERNS:
        matches = list(pattern.finditer(cleaned))
        if not matches:
            continue
        cleaned = pattern.sub(replacement, cleaned)
        repairs.append({"pattern": pattern.pattern, "count": len(matches)})
    cleaned = re.sub(r"\s+([，。！？；：、,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([，、]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), {"broken_slot_repairs": repairs, "broken_slot_repaired": bool(repairs)}


def clean_reader_visible_meta_language(text: str) -> Tuple[str, Dict[str, Any]]:
    cleaned = str(text or "")
    repairs: List[Dict[str, Any]] = []
    for pattern, replacement in META_VISIBLE_REPLACEMENTS:
        matches = list(pattern.finditer(cleaned))
        if not matches:
            continue
        cleaned = pattern.sub(replacement, cleaned)
        repairs.append({"pattern": pattern.pattern, "count": len(matches), "replacement": replacement})
    return cleaned.strip(), {"meta_language_repairs": repairs, "meta_language_repaired": bool(repairs)}


def _coerce_beat_payload(raw: Any) -> Dict[str, Any]:
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
    payload = dict(raw or {})
    event = payload.get("event") or {}
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    payload["event"] = dict(event or {})
    return payload


def _extract_location_anchors(coverage_context: Dict[str, Any] | None) -> List[str]:
    anchors: List[str] = []
    for raw in list(dict(coverage_context or {}).get("scene_beats") or []):
        event = _coerce_beat_payload(raw).get("event") or {}
        location = _normalize_text(str(dict(event).get("location") or ""))
        if 2 <= len(location) <= 16 and location not in {"未指定", "场面", "眼前"}:
            anchors.append(location)
    return list(dict.fromkeys(anchors))


def _replace_from_occurrence(text: str, phrase: str, replacement: str, *, keep: int) -> Tuple[str, int]:
    if not phrase:
        return text, 0
    seen = 0
    replaced = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal seen, replaced
        seen += 1
        if seen <= keep:
            return match.group(0)
        replaced += 1
        return replacement

    cleaned = re.sub(re.escape(phrase), repl, text)
    return cleaned, replaced


def _apply_stock_refrain_budget(text: str, counts: Dict[str, int], *, chapter_index: int) -> Tuple[str, List[Dict[str, Any]]]:
    cleaned = str(text or "")
    actions: List[Dict[str, Any]] = []
    for phrase, replacements in STOCK_REFRAIN_REPLACEMENTS.items():
        occurrences = cleaned.count(phrase)
        if occurrences <= 0:
            continue
        normalized = _normalize_text(phrase)
        previous = int(counts.get(normalized, 0) or 0)
        max_keep = int(STOCK_REFRAIN_KEEP_LIMITS.get(phrase, STOCK_REFRAIN_GLOBAL_MAX))
        keep = max(0, max_keep - previous)
        replacement = str(replacements[_stable_index(chapter_index + previous, len(replacements))])
        cleaned, replaced = _replace_from_occurrence(cleaned, phrase, replacement, keep=keep)
        counts[normalized] = previous + occurrences
        if replaced:
            actions.append({"kind": "stock_refrain_budget", "phrase": phrase, "replaced": replaced, "previous": previous})
    return cleaned, actions


def _apply_location_anchor_budget(
    text: str,
    anchors: Sequence[str],
    counts: Dict[str, int],
    *,
    chapter_index: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    cleaned = str(text or "")
    actions: List[Dict[str, Any]] = []
    replacements = ("那里", "旧处", "眼前", "那处")
    for anchor in anchors:
        phrase = str(anchor or "").strip()
        occurrences = cleaned.count(phrase)
        if occurrences <= 0:
            continue
        normalized = _normalize_text(phrase)
        previous = int(counts.get(normalized, 0) or 0)
        keep = LOCATION_ANCHOR_PER_CHAPTER_MAX
        if previous >= LOCATION_ANCHOR_GLOBAL_SOFT_MAX:
            keep = min(1, occurrences)
        replacement = replacements[_stable_index(chapter_index + previous, len(replacements))]
        cleaned, replaced = _replace_from_occurrence(cleaned, phrase, replacement, keep=keep)
        counts[normalized] = previous + occurrences
        if replaced:
            actions.append({"kind": "location_anchor_budget", "phrase": phrase, "replaced": replaced, "previous": previous})
    return cleaned, actions


def _choice_replacement(*, index: int, chapter_index: int, anchor: str) -> str:
    anchor_text = anchor or "眼前这一处"
    templates = (
        "先稳住{anchor}里露出的变化，再追问下一处空白。",
        "换一个角度逼近{anchor}，把没有说完的地方接住。",
        "暂时不退，顺着{anchor}的裂口继续往前问。",
        "先护住当前线索，再把{anchor}里的旧账翻到明处。",
        "沿着{anchor}留下的细节往下查，不急着替任何人收场。",
        "把{anchor}里的停顿问清楚，再决定下一步要压向谁。",
        "先看清{anchor}里谁在回避，再把问题换到更实的一处。",
        "不急着表态，先让{anchor}里的证据自己露出下一层。",
        "顺着{anchor}的异常往前推，看看旧账会落到谁手里。",
        "把{anchor}里最轻的破绽扣住，逼对方给出更具体的回答。",
        "先绕开场面话，直接追问{anchor}里没有对上的细节。",
        "守住{anchor}这一线，再把迟迟没人认的代价翻出来。",
    )
    return templates[_stable_index(chapter_index + index, len(templates))].format(anchor=anchor_text)


def _diversify_choices(
    choices: Iterable[str],
    *,
    counts: Dict[str, int],
    recent_choices: Sequence[str],
    chapter_index: int,
    anchor: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    output: List[str] = []
    actions: List[Dict[str, Any]] = []
    current_seen: Counter[str] = Counter()
    recent_set = {_normalize_text(item) for item in recent_choices if _normalize_text(item)}
    for index, raw in enumerate(list(choices or []), start=1):
        cleaned, slot_report = clean_broken_reader_slots(str(raw or ""))
        cleaned, meta_report = clean_reader_visible_meta_language(cleaned)
        cleaned, stock_actions = _apply_stock_refrain_budget(cleaned, counts, chapter_index=chapter_index)
        normalized = _normalize_text(cleaned)
        previous = int(counts.get(f"choice:{normalized}", 0) or 0)
        must_replace = (
            not normalized
            or normalized == _normalize_text(DEFAULT_READER_CHOICE)
            or normalized in recent_set
            or previous >= CHOICE_TEXT_GLOBAL_MAX
            or current_seen[normalized] > 0
        )
        if must_replace:
            replacement = _choice_replacement(index=index, chapter_index=chapter_index, anchor=anchor)
            suffix = 1
            while _normalize_text(replacement) in {_normalize_text(item) for item in output}:
                suffix += 1
                replacement = _choice_replacement(index=index + suffix, chapter_index=chapter_index, anchor=anchor)
            actions.append({"kind": "choice_budget", "previous_text": cleaned, "replacement": replacement, "previous": previous})
            cleaned = replacement
            normalized = _normalize_text(cleaned)
        if slot_report.get("broken_slot_repaired"):
            actions.append({"kind": "choice_broken_slot_repair", "index": index, **slot_report})
        if meta_report.get("meta_language_repaired"):
            actions.append({"kind": "choice_meta_language_repair", "index": index, **meta_report})
        actions.extend(stock_actions)
        counts[f"choice:{normalized}"] = int(counts.get(f"choice:{normalized}", 0) or 0) + 1
        current_seen[normalized] += 1
        output.append(cleaned)
    return output, actions


def _repair_visible_text_field(
    value: str,
    *,
    field: str,
    phrase_counts: Dict[str, int],
    anchors: Sequence[str],
    chapter_index: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    cleaned, slot_report = clean_broken_reader_slots(str(value or ""))
    cleaned, meta_report = clean_reader_visible_meta_language(cleaned)
    cleaned, anchor_actions = _apply_location_anchor_budget(cleaned, anchors, phrase_counts, chapter_index=chapter_index)
    cleaned, stock_actions = _apply_stock_refrain_budget(cleaned, phrase_counts, chapter_index=chapter_index)
    actions: List[Dict[str, Any]] = []
    if slot_report.get("broken_slot_repaired"):
        actions.append({"kind": "broken_slot_repair", "field": field, **slot_report})
    if meta_report.get("meta_language_repaired"):
        actions.append({"kind": "meta_language_repair", "field": field, **meta_report})
    actions.extend({"field": field, **item} for item in stock_actions + anchor_actions)
    return cleaned, actions


def repair_reader_view_for_display(
    reader_view: Dict[str, Any],
    *,
    source: str = "legacy_read_projection",
) -> Dict[str, Any]:
    """Repair legacy stored reader-visible text without mutating source quality evidence."""
    working = deepcopy(dict(reader_view or {}))
    phrase_counts: Dict[str, int] = {}
    actions: List[Dict[str, Any]] = []
    chapter_index = int(working.get("chapter_index", 0) or 0)

    for field in ("chapter_title", "recap", "body"):
        if field not in working:
            continue
        cleaned, field_actions = _repair_visible_text_field(
            str(working.get(field) or ""),
            field=field,
            phrase_counts=phrase_counts,
            anchors=[],
            chapter_index=chapter_index,
        )
        working[field] = cleaned
        actions.extend(field_actions)

    relationship_hints = []
    for index, raw in enumerate(list(working.get("relationship_hints") or []), start=1):
        cleaned, field_actions = _repair_visible_text_field(
            str(raw or ""),
            field=f"relationship_hints[{index}]",
            phrase_counts=phrase_counts,
            anchors=[],
            chapter_index=chapter_index,
        )
        relationship_hints.append(cleaned)
        actions.extend(field_actions)
    if "relationship_hints" in working:
        working["relationship_hints"] = relationship_hints

    scene_card = dict(working.get("scene_card") or {})
    if scene_card:
        for key in SCENE_CARD_TEXT_FIELDS:
            if key not in scene_card:
                continue
            cleaned, field_actions = _repair_visible_text_field(
                str(scene_card.get(key) or ""),
                field=f"scene_card.{key}",
                phrase_counts=phrase_counts,
                anchors=[],
                chapter_index=chapter_index,
            )
            scene_card[key] = cleaned
            actions.extend(field_actions)
        for key in SCENE_CARD_LIST_FIELDS:
            if key not in scene_card:
                continue
            repaired_items = []
            for index, raw in enumerate(list(scene_card.get(key) or []), start=1):
                cleaned, field_actions = _repair_visible_text_field(
                    str(raw or ""),
                    field=f"scene_card.{key}[{index}]",
                    phrase_counts=phrase_counts,
                    anchors=[],
                    chapter_index=chapter_index,
                )
                repaired_items.append(cleaned)
                actions.extend(field_actions)
            scene_card[key] = repaired_items
        working["scene_card"] = scene_card

    if "choices" in working:
        repaired_choices = []
        for index, raw in enumerate(list(working.get("choices") or []), start=1):
            cleaned, field_actions = _repair_visible_text_field(
                str(raw or ""),
                field=f"choices[{index}]",
                phrase_counts=phrase_counts,
                anchors=[],
                chapter_index=chapter_index,
            )
            repaired_choices.append(cleaned)
            actions.extend(field_actions)
        working["choices"] = repaired_choices

    if actions:
        working["display_sanitization"] = {
            "schema_version": "reader_view_display_sanitization/v1",
            "source": source,
            "repaired": True,
            "actions": actions[-20:],
        }
    return working


def apply_long_route_quality_controls(
    reader_view: Dict[str, Any],
    *,
    state_before: Any,
    state_after: Any,
    coverage_context: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
    working = deepcopy(dict(reader_view or {}))
    before_metadata = dict(getattr(state_before, "metadata", {}) or {})
    budget = dict(before_metadata.get(LONG_ROUTE_QUALITY_METADATA_KEY) or {})
    phrase_counts = {str(key): int(value or 0) for key, value in dict(budget.get("phrase_counts") or {}).items()}
    choice_counts = {str(key): int(value or 0) for key, value in dict(budget.get("choice_counts") or {}).items()}
    recent_choices = [str(item) for item in list(budget.get("recent_choices") or []) if str(item).strip()]
    chapter_index = int(getattr(state_after, "chapter_index", 0) or 0)
    anchors = _extract_location_anchors(coverage_context)
    primary_anchor = anchors[0] if anchors else ""
    actions: List[Dict[str, Any]] = []

    for field in ("chapter_title", "recap", "body"):
        cleaned, field_actions = _repair_visible_text_field(
            str(working.get(field) or ""),
            field=field,
            phrase_counts=phrase_counts,
            anchors=anchors,
            chapter_index=chapter_index,
        )
        working[field] = cleaned
        actions.extend(field_actions)

    relationship_hints = []
    for index, raw in enumerate(list(working.get("relationship_hints") or []), start=1):
        field_name = f"relationship_hints[{index}]"
        cleaned, field_actions = _repair_visible_text_field(
            str(raw or ""),
            field=field_name,
            phrase_counts=phrase_counts,
            anchors=anchors,
            chapter_index=chapter_index,
        )
        relationship_hints.append(cleaned)
        actions.extend(field_actions)
    working["relationship_hints"] = relationship_hints

    scene_card = dict(working.get("scene_card") or {})
    if scene_card:
        for key in SCENE_CARD_TEXT_FIELDS:
            if key not in scene_card:
                continue
            field_name = f"scene_card.{key}"
            cleaned, field_actions = _repair_visible_text_field(
                str(scene_card.get(key) or ""),
                field=field_name,
                phrase_counts=phrase_counts,
                anchors=anchors,
                chapter_index=chapter_index,
            )
            scene_card[key] = cleaned
            actions.extend(field_actions)
        for key in SCENE_CARD_LIST_FIELDS:
            if key not in scene_card:
                continue
            repaired_items = []
            for index, raw in enumerate(list(scene_card.get(key) or []), start=1):
                field_name = f"scene_card.{key}[{index}]"
                cleaned, field_actions = _repair_visible_text_field(
                    str(raw or ""),
                    field=field_name,
                    phrase_counts=phrase_counts,
                    anchors=anchors,
                    chapter_index=chapter_index,
                )
                repaired_items.append(cleaned)
                actions.extend(field_actions)
            scene_card[key] = repaired_items
        working["scene_card"] = scene_card

    choices, choice_actions = _diversify_choices(
        list(working.get("choices") or []),
        counts=choice_counts,
        recent_choices=recent_choices,
        chapter_index=chapter_index,
        anchor=primary_anchor,
    )
    working["choices"] = choices
    actions.extend(choice_actions)

    updated_recent_choices = (recent_choices + choices)[-RECENT_CHOICE_WINDOW:]
    metadata = {
        **dict(getattr(state_after, "metadata", {}) or {}),
        LONG_ROUTE_QUALITY_METADATA_KEY: {
            "phrase_counts": dict(sorted(phrase_counts.items())),
            "choice_counts": dict(sorted(choice_counts.items())),
            "recent_choices": updated_recent_choices,
            "last_actions": actions[-20:],
        },
    }
    state_after.metadata = metadata
    return working, state_after, {
        "long_route_quality_controls_applied": bool(actions),
        "actions": actions,
        "tracked_location_anchors": anchors,
    }
