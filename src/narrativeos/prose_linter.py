from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import re
from typing import Dict, List

from .meta_leak_detector import detect_meta_leaks, meta_sentence_rate
from .repetition_detector import repetition_score, repetition_signal_bundle
from .sanitizer import sanitize_text
from .style_sanitizer import style_sanitize


DETAIL_MARKERS = [
    "灯", "袖", "茶", "风", "门", "阶", "檐", "影", "衣", "案", "纸", "雨", "香", "窗", "灯影",
    "栏", "栏杆", "杯", "杯沿", "门框", "木板", "纸页", "桌沿", "桌角", "器物", "石径", "叶影",
    "扫描台", "蓝线", "红灯", "防潮盒", "钝印", "胶痕", "签章", "声纹", "画稿", "盐壳", "录音笔", "话筒",
    "石砖", "空杯", "窗纸", "木栏", "地板", "檐角", "冷光", "回声", "香灰", "笔架", "卷面", "号板",
    "墨迹", "鞋底", "手背", "发梢", "灰尘", "水痕", "潮气", "湿气", "衣摆", "袖口",
    "指节", "呼吸", "肩背", "掌心", "眼睫", "廊柱", "石阶", "花枝", "帘钩", "玉佩", "朱批", "折角",
    "灯座", "玉阶", "香炉", "钟声", "檀香", "冷雾", "山门", "剑穗", "符纸", "云气", "霜意",
    "湖面", "石栏", "水声", "水雾", "月色", "水线", "浪声", "水滴声", "盐味", "潮痕",
    "雨棚", "旧门牌", "雨伞骨", "监控探头", "电流声", "鞋底水声", "翻卷声", "霓虹", "湿雾", "油烟",
]
ACTION_MARKERS = ["抬", "落", "偏", "按", "握", "退", "站", "看", "拢", "推", "折", "停", "走", "靠", "咽", "压", "掠", "碰", "擦", "收", "绷", "卷", "撞", "回", "拨", "绕", "贴", "拖"]
LATIN_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")
LATIN_TOKEN_WHITELIST_PATTERN = re.compile(r"^[A-Z]{2,}$")


def _normalize_visible_text_for_language_scan(text: str) -> str:
    cleaned = style_sanitize(str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _split_paragraphs(text: str) -> List[str]:
    return [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]


def _count_dialogue(text: str) -> int:
    return text.count("“")


def _count_actions(text: str) -> int:
    return sum(text.count(marker) for marker in ACTION_MARKERS)


def _count_details(text: str) -> int:
    return sum(text.count(marker) for marker in DETAIL_MARKERS)


def story_text_unit_count(text: str) -> int:
    normalized = re.sub(r"\s+", "", str(text or ""))
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", normalized))


@lru_cache(maxsize=512)
def _cached_repetition_signal_bundle(cleaned_paragraphs: tuple[str, ...]) -> Dict[str, object]:
    return repetition_signal_bundle(list(cleaned_paragraphs))


def _safe_repetition_signal_bundle(cleaned_paragraphs: List[str]) -> Dict[str, object]:
    # Repetition analysis is one of the expensive pure checks repeatedly invoked
    # during quality repair. Return a copy so callers can keep mutating payloads.
    return deepcopy(_cached_repetition_signal_bundle(tuple(cleaned_paragraphs)))


def extract_latin_token_hits(text: str, *, field: str = "body", precleaned: bool = False) -> List[Dict[str, object]]:
    cleaned = str(text or "") if precleaned else _normalize_visible_text_for_language_scan(str(text or ""))
    hits: List[Dict[str, object]] = []
    for match in LATIN_TOKEN_PATTERN.finditer(cleaned):
        token = match.group(0)
        start = max(0, match.start() - 12)
        end = min(len(cleaned), match.end() + 12)
        hits.append(
            {
                "field": field,
                "token": token,
                "allowed": bool(LATIN_TOKEN_WHITELIST_PATTERN.fullmatch(token)),
                "context_excerpt": cleaned[start:end],
            }
        )
    return hits


def lint_prose(text: str) -> Dict[str, object]:
    paragraphs = _split_paragraphs(text)
    cleaned = sanitize_text(style_sanitize(text))
    cleaned_paragraphs = _split_paragraphs(cleaned)
    repetition_bundle = _safe_repetition_signal_bundle(cleaned_paragraphs)
    latin_token_hits = extract_latin_token_hits(text, field="body")
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
        "repetition_signal_bundle": repetition_bundle,
        "lexical_repetition_score": repetition_bundle["lexical_repetition_score"],
        "paragraph_similarity_score": repetition_bundle["paragraph_similarity_score"],
        "semantic_paragraph_similarity_score": repetition_bundle["semantic_paragraph_similarity_score"],
        "n_gram_repetition_score": repetition_bundle["n_gram_repetition_score"],
        "beat_structure_repetition_score": repetition_bundle["beat_structure_repetition_score"],
        "suspicious_refrain_count": repetition_bundle["suspicious_refrain_count"],
        "event_coverage_gap_score": repetition_bundle["event_coverage_gap_score"],
        "beat_coverage_gap_score": repetition_bundle["beat_coverage_gap_score"],
        "uncovered_event_count": repetition_bundle["uncovered_event_count"],
        "uncovered_beat_count": repetition_bundle["uncovered_beat_count"],
        "overcovered_beat_count": repetition_bundle["overcovered_beat_count"],
        "exposition_ratio": exposition_ratio,
        "dialogue_plus_action_ratio": dialogue_plus_action_ratio,
        "concrete_detail_density": concrete_detail_density,
        "latin_token_hits": latin_token_hits,
        "disallowed_latin_token_hits": [item for item in latin_token_hits if not item["allowed"]],
        "dialogue_count": dialogue_count,
        "action_count": action_count,
        "detail_count": detail_count,
        "text_unit_count": story_text_unit_count(cleaned),
        "raw_paragraphs": paragraphs,
    }
