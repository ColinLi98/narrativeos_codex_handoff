from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple


ENGINEERING_REPLACEMENTS = [
    (re.compile(r"(?<![A-Za-z])temptation(?![A-Za-z])", re.IGNORECASE), "试探"),
    (re.compile(r"(?<![A-Za-z])false(?:_|\s+)peace(?![A-Za-z])", re.IGNORECASE), "表面平静"),
    (re.compile(r"(?<![A-Za-z])truth(?:_|\s+)trial(?![A-Za-z])", re.IGNORECASE), "真相试探"),
    (re.compile(r"(?<![A-Za-z])misrecognition(?![A-Za-z])", re.IGNORECASE), "错认"),
    (re.compile(r"(?<![A-Za-z])confession(?:_|\s+)window(?![A-Za-z])", re.IGNORECASE), "说破窗口"),
    (re.compile(r"(?<![A-Za-z])mask(?:_|\s+)crack(?![A-Za-z])", re.IGNORECASE), "面具裂口"),
    (re.compile(r"(?<![A-Za-z])debt(?:_|\s+)exchange(?![A-Za-z])", re.IGNORECASE), "债务交换"),
    (re.compile(r"(?<![A-Za-z])karma(?:_|\s+)ripening(?![A-Za-z])", re.IGNORECASE), "因果熟成"),
    (re.compile(r"(?<![A-Za-z])vow(?:_|\s+)payment(?![A-Za-z])", re.IGNORECASE), "誓愿偿付"),
    (re.compile(r"(?<![A-Za-z])mercy(?:_|\s+)vs(?:_|\s+)control(?![A-Za-z])", re.IGNORECASE), "仁慈与控制"),
    (re.compile(r"(?<![A-Za-z])humiliation(?![A-Za-z])", re.IGNORECASE), "折辱"),
    (re.compile(r"(?<![A-Za-z])trust(?:_|\s+)test(?![A-Za-z])", re.IGNORECASE), "信任试探"),
    (re.compile(r"(?<![A-Za-z])discovery(?![A-Za-z])", re.IGNORECASE), "发现"),
    (re.compile(r"(?<![A-Za-z])reversal(?![A-Za-z])", re.IGNORECASE), "逆转"),
]


ENGINEERING_PATTERNS = [
    re.compile(r"\bevent_id\b", re.IGNORECASE),
    re.compile(r"\bscene_function\b", re.IGNORECASE),
    re.compile(r"\bconvergence_key\b", re.IGNORECASE),
    re.compile(r"\bseed_id\b", re.IGNORECASE),
    re.compile(r"\bdebt_type\b", re.IGNORECASE),
    re.compile(r"\bendgame_shape\b", re.IGNORECASE),
    re.compile(r"\b(?:greed|anger|delusion|pride|doubt)\b", re.IGNORECASE),
    re.compile(
        r"(?<![A-Za-z])(?:temptation|false_peace|truth_trial|misrecognition|confession_window|mask_crack|debt_exchange|karma_ripening|vow_payment|mercy_vs_control|humiliation|trust_test|discovery|reversal)(?![A-Za-z])",
        re.IGNORECASE,
    ),
    re.compile(r"\broute\s*=", re.IGNORECASE),
    re.compile(r"->"),
    re.compile(r"(?<![A-Za-z0-9_])[a-z]+(?:_[a-z0-9]+)+(?![A-Za-z0-9_])"),
    re.compile(r"\b(?:duty|ambition|love|selfhood|truth|reform|sacrifice|loyalty|curiosity|destiny|system|power|family|hope|loss|cost)\b", re.IGNORECASE),
]

LATIN_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")
LATIN_TOKEN_WHITELIST_PATTERN = re.compile(r"^[A-Z]{2,}$")
READER_VISIBLE_LATIN_REPLACEMENTS = {
    "secrecy": "藏着没说的真心",
    "obedience": "顺从",
    "honesty": "坦白",
    "loyalty": "忠诚",
    "curiosity": "追问",
    "romance": "情意",
    "love": "情意",
    "truth": "真相",
    "duty": "责任",
    "ambition": "前途",
    "reputation": "体面",
    "selfhood": "自我",
    "destiny": "命运",
    "sacrifice": "代价",
    "reform": "改写旧秩序",
    "system": "旧秩序",
    "power": "权势",
    "family": "家门",
    "hope": "希望",
    "loss": "失去",
    "cost": "代价",
    "urban": "城中",
    "mystery": "谜局",
    "urban_mystery": "真相",
    "synthetic": "试探",
    "benchmark": "试探",
    "xianxia": "修行",
    "suspense": "压迫",
    "temptation": "试探",
    "false": "表面",
    "peace": "平静",
    "misrecognition": "误解",
    "confession": "真话",
    "window": "窗口",
    "mask": "面具",
    "crack": "裂口",
    "debt": "旧账",
    "exchange": "交换",
    "karma": "因果",
    "ripening": "回响",
    "vow": "誓愿",
    "payment": "偿付",
    "mercy": "仁慈",
    "control": "控制",
    "humiliation": "难堪",
    "trust": "信任",
    "test": "试探",
    "discovery": "发现",
    "reversal": "逆转",
}


def sanitize_text(text: str) -> str:
    cleaned = text
    for pattern, replacement in ENGINEERING_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    for pattern in ENGINEERING_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def contains_engineering_leak(text: str) -> bool:
    return any(pattern.search(text) for pattern in ENGINEERING_PATTERNS)


def sanitize_lines(lines: Iterable[str]) -> list[str]:
    return [sanitize_text(line) for line in lines if sanitize_text(line)]


def _sanitize_remaining_latin_tokens(text: str) -> Tuple[str, List[str]]:
    sanitized_tokens: List[str] = []

    def replace(match: re.Match[str]) -> str:
        token = str(match.group(0) or "")
        if LATIN_TOKEN_WHITELIST_PATTERN.fullmatch(token):
            return token
        sanitized_tokens.append(token)
        replacement = READER_VISIBLE_LATIN_REPLACEMENTS.get(token.lower(), "")
        return replacement

    cleaned = LATIN_TOKEN_PATTERN.sub(replace, str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([（《“‘【])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([）》”’】])", r"\1", cleaned)
    return cleaned.strip(), list(dict.fromkeys(sanitized_tokens))


def sanitize_reader_visible_text(text: str) -> str:
    cleaned, _ = sanitize_reader_visible_text_with_report(text)
    return cleaned


def sanitize_reader_visible_text_with_report(text: str) -> Tuple[str, Dict[str, object]]:
    original_latin_tokens = [
        token
        for token in LATIN_TOKEN_PATTERN.findall(str(text or ""))
        if not LATIN_TOKEN_WHITELIST_PATTERN.fullmatch(token)
    ]
    base = sanitize_text(text)
    cleaned, remaining_latin_tokens = _sanitize_remaining_latin_tokens(base)
    sanitized_tokens = list(dict.fromkeys(original_latin_tokens + remaining_latin_tokens))
    return cleaned, {
        "reader_visible_language_sanitized": bool(sanitized_tokens),
        "sanitized_latin_tokens": sanitized_tokens,
    }


def sanitize_reader_visible_lines(lines: Iterable[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        cleaned = sanitize_reader_visible_text(str(line or ""))
        if cleaned:
            output.append(cleaned)
    return output


def _merge_reader_visible_language_reports(*reports: Dict[str, object]) -> Dict[str, object]:
    sanitized = False
    fields: List[str] = []
    tokens: List[str] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        sanitized = sanitized or bool(report.get("reader_visible_language_sanitized"))
        fields.extend([str(item) for item in list(report.get("fields") or []) if str(item).strip()])
        tokens.extend([str(item) for item in list(report.get("sanitized_latin_tokens") or []) if str(item).strip()])
    return {
        "reader_visible_language_sanitized": sanitized,
        "fields": list(dict.fromkeys(fields)),
        "sanitized_latin_tokens": list(dict.fromkeys(tokens)),
    }


def sanitize_reader_visible_payload(payload: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object]]:
    working = dict(payload or {})
    reports: List[Dict[str, object]] = []

    def sanitize_field(name: str, value: str) -> str:
        cleaned, report = sanitize_reader_visible_text_with_report(value)
        if report["reader_visible_language_sanitized"]:
            reports.append(
                {
                    "reader_visible_language_sanitized": True,
                    "fields": [name],
                    "sanitized_latin_tokens": list(report["sanitized_latin_tokens"]),
                }
            )
        return cleaned

    working["chapter_title"] = sanitize_field("chapter_title", str(working.get("chapter_title") or ""))
    working["recap"] = sanitize_field("recap", str(working.get("recap") or ""))
    working["body"] = sanitize_field("body", str(working.get("body") or ""))
    working["choices"] = [
        sanitize_field(f"choice[{index}]", str(item or ""))
        for index, item in enumerate(list(working.get("choices") or []))
    ]
    working["relationship_hints"] = [
        sanitize_field(f"relationship_hint[{index}]", str(item or ""))
        for index, item in enumerate(list(working.get("relationship_hints") or []))
    ]

    scene_card = dict(working.get("scene_card") or {})
    if scene_card:
        scene_card["title"] = sanitize_field("scene_card.title", str(scene_card.get("title") or ""))
        scene_card["summary"] = sanitize_field("scene_card.summary", str(scene_card.get("summary") or ""))
        scene_card["quote"] = sanitize_field("scene_card.quote", str(scene_card.get("quote") or ""))
        scene_card["palette_hint"] = sanitize_field("scene_card.palette_hint", str(scene_card.get("palette_hint") or ""))
        scene_card["story_beats"] = [
            sanitize_field(f"scene_card.story_beats[{index}]", str(item or ""))
            for index, item in enumerate(list(scene_card.get("story_beats") or []))
        ]
        scene_card["visual_details"] = [
            sanitize_field(f"scene_card.visual_details[{index}]", str(item or ""))
            for index, item in enumerate(list(scene_card.get("visual_details") or []))
        ]
        working["scene_card"] = scene_card

    return working, _merge_reader_visible_language_reports(*reports)
