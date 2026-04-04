from __future__ import annotations

import re


STYLE_REPLACEMENTS = {
    "这一章": "",
    "这一幕": "",
    "从这里起": "",
    "如果把这一章放远一点看": "",
    "真正厉害的是": "更难的是",
    "更糟的是": "麻烦的是",
}


def style_sanitize(text: str) -> str:
    cleaned = text
    for source, target in STYLE_REPLACEMENTS.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"第[一二三四五六七八九十0-9]+拍[:：]?", "", cleaned)
    cleaned = re.sub(r"第[一二三四五六七八九十0-9]+幕[:：]?", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
