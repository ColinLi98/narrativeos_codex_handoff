from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    normalized = text.lower()
    return any(str(keyword).lower() in normalized for keyword in keywords)


def _choice_label(text: str) -> str:
    normalized = _normalized_text(text)
    if not normalized:
        return "继续推进"
    for marker in ("：", ":", "，", ",", "。", ".", "\n"):
        if marker in normalized:
            normalized = normalized.split(marker, 1)[0].strip()
    return normalized[:18] or "继续推进"


def _risk_level(text: str) -> tuple[str, str]:
    if _contains_any(
        text,
        (
            "揭露",
            "摊牌",
            "追查",
            "闯入",
            "对抗",
            "暴露",
            "反派",
            "危险",
            "逼问",
            "betray",
            "confront",
            "expose",
        ),
    ):
        return "高", "可能让身份、秘密或关系压力提前暴露"
    if _contains_any(
        text,
        (
            "保护",
            "等待",
            "观察",
            "暂缓",
            "隐藏",
            "退后",
            "守住",
            "delay",
            "protect",
            "wait",
        ),
    ):
        return "低", "更偏向保留余地，但线索推进会放慢"
    return "中", "会改变下一章压力，但仍保留回旋空间"


def _emotion(text: str) -> str:
    if _contains_any(text, ("争执", "对抗", "摊牌", "逼问", "冲突", "confront", "argue")):
        return "冲突"
    if _contains_any(text, ("相信", "靠近", "保护", "坦白", "升温", "trust", "protect", "confess")):
        return "升温"
    if _contains_any(text, ("隐瞒", "退后", "离开", "冷却", "疏远", "hide", "leave")):
        return "冷却"
    return "波动"


def _pacing(text: str) -> str:
    if _contains_any(text, ("反转", "误会", "真相", "揭晓", "reverse", "twist")):
        return "反转"
    if _contains_any(text, ("等待", "观察", "隐藏", "保护", "放慢", "暂缓", "delay", "wait")):
        return "暂缓"
    if _contains_any(text, ("追查", "推进", "进入", "选择", "摊牌", "证据", "advance", "follow")):
        return "推进"
    return "推进"


def _relationship(text: str) -> str:
    if _contains_any(text, ("背叛", "出卖", "反派", "betray")):
        return "背叛"
    if _contains_any(text, ("相信", "坦白", "保护", "靠近", "信任", "trust", "confess")):
        return "信任"
    if _contains_any(text, ("试探", "隐瞒", "误会", "调查", "怀疑", "hide", "doubt")):
        return "怀疑"
    return "拉扯"


def _mystery(text: str) -> str:
    if _contains_any(text, ("隐瞒", "隐藏", "误会", "不要揭晓", "悬疑", "暂缓", "hide", "delay")):
        return "加深"
    if _contains_any(text, ("追查", "证据", "真相", "揭露", "揭晓", "evidence", "truth")):
        return "揭开"
    if _contains_any(text, ("反转", "转向", "twist", "turn")):
        return "转向"
    return "维持"


def _expected_effect(*, pacing: str, relationship: str, mystery: str) -> str:
    if pacing == "反转":
        return "制造转折并改变读者对局势的判断"
    if mystery == "揭开":
        return "推进主线线索并提高下一章行动压力"
    if mystery == "加深":
        return "保留真相并制造新的误会空间"
    if relationship == "信任":
        return "增强人物关系并让后续选择更有代价"
    if relationship == "怀疑":
        return "拉高关系不确定性并延后摊牌"
    return "推动当前局势进入下一段选择压力"


def build_choice_impacts(
    choices: Iterable[Any],
    *,
    reader_view: Optional[Dict[str, Any]] = None,
    routes: Optional[Iterable[Any]] = None,
    chapter_index: int = 0,
) -> List[Dict[str, Any]]:
    """Build product-language impact tags without pack-specific prose rules."""
    _ = reader_view, routes
    impacts: List[Dict[str, Any]] = []
    for index, raw_choice in enumerate(list(choices or []), start=1):
        text = _normalized_text(raw_choice)
        label = _choice_label(text)
        risk_level, risk_reason = _risk_level(text)
        emotion = _emotion(text)
        pacing = _pacing(text)
        relationship = _relationship(text)
        mystery = _mystery(text)
        expected_effect = _expected_effect(pacing=pacing, relationship=relationship, mystery=mystery)
        choice_id = f"choice_{int(chapter_index or 0)}_{index}" if int(chapter_index or 0) > 0 else f"choice_{index}"
        impacts.append(
            {
                "choice_id": choice_id,
                "label": label,
                "expected_effect": expected_effect,
                "risk_level": risk_level,
                "risk_reason": risk_reason,
                "emotion": emotion,
                "pacing": pacing,
                "relationship": relationship,
                "mystery": mystery,
                "director_intent_prefill": f"沿着「{label}」继续，让下一章{expected_effect}。",
            }
        )
    return impacts


def merge_choice_impacts_into_reader_view(
    reader_view: Dict[str, Any],
    *,
    routes: Optional[Iterable[Any]] = None,
    chapter_index: int = 0,
) -> Dict[str, Any]:
    payload = dict(reader_view or {})
    payload["choice_impacts"] = build_choice_impacts(
        payload.get("choices") or [],
        reader_view=payload,
        routes=routes,
        chapter_index=chapter_index or int(payload.get("chapter_index") or 0),
    )
    return payload
