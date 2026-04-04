from __future__ import annotations

import re
from typing import Dict, List

from .meta_leak_detector import detect_meta_leaks, meta_sentence_rate
from .repetition_detector import repetition_score
from .sanitizer import sanitize_text
from .style_sanitizer import style_sanitize


DETAIL_MARKERS = ["灯", "袖", "茶", "风", "门", "阶", "檐", "影", "衣", "案", "纸", "雨", "香", "窗", "灯影"]
ACTION_MARKERS = ["抬", "落", "偏", "按", "握", "退", "站", "看", "拢", "推", "折", "停", "走", "靠", "咽"]


def _split_paragraphs(text: str) -> List[str]:
    return [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]


def _count_dialogue(text: str) -> int:
    return text.count("“")


def _count_actions(text: str) -> int:
    return sum(text.count(marker) for marker in ACTION_MARKERS)


def _count_details(text: str) -> int:
    return sum(text.count(marker) for marker in DETAIL_MARKERS)


def lint_prose(text: str) -> Dict[str, object]:
    paragraphs = _split_paragraphs(text)
    cleaned = sanitize_text(style_sanitize(text))
    cleaned_paragraphs = _split_paragraphs(cleaned)
    dialogue_count = _count_dialogue(cleaned)
    action_count = _count_actions(cleaned)
    detail_count = _count_details(cleaned)
    meta_rate = meta_sentence_rate(cleaned_paragraphs)
    exposition_ratio = min(1.0, sum(1 for line in cleaned_paragraphs if "：" not in line and "“" not in line) / float(max(1, len(cleaned_paragraphs))))
    dialogue_plus_action_ratio = min(1.0, (dialogue_count * 24 + action_count * 8) / float(max(1, len(cleaned))))
    concrete_detail_density = detail_count / float(max(1, len(cleaned)))
    return {
        "cleaned_text": cleaned,
        "paragraphs": cleaned_paragraphs,
        "meta_leaks": detect_meta_leaks(cleaned),
        "meta_sentence_rate": meta_rate,
        "engineering_leak_rate": 0.0 if not detect_meta_leaks(cleaned) else 1.0,
        "repetition_score": repetition_score(cleaned_paragraphs),
        "exposition_ratio": exposition_ratio,
        "dialogue_plus_action_ratio": dialogue_plus_action_ratio,
        "concrete_detail_density": concrete_detail_density,
        "dialogue_count": dialogue_count,
        "action_count": action_count,
        "detail_count": detail_count,
        "raw_paragraphs": paragraphs,
    }
