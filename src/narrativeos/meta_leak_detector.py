from __future__ import annotations

import re
from typing import Iterable, List


META_PATTERNS = [
    re.compile(r"第[一二三四五六七八九十0-9]+拍"),
    re.compile(r"第[一二三四五六七八九十0-9]+幕"),
    re.compile(r"这一章"),
    re.compile(r"从这里起"),
    re.compile(r"如果把这一章放远一点看"),
    re.compile(r"更糟的是"),
    re.compile(r"真正厉害的是"),
    re.compile(r"[a-z]+_[a-z0-9_]+"),
    re.compile(r".+\s*->\s*.+"),
]


def detect_meta_leaks(text: str) -> List[str]:
    hits: List[str] = []
    for pattern in META_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def has_meta_leak(text: str) -> bool:
    return bool(detect_meta_leaks(text))


def meta_sentence_rate(lines: Iterable[str]) -> float:
    sentences = [line.strip() for line in lines if line.strip()]
    if not sentences:
        return 0.0
    meta_count = sum(1 for line in sentences if has_meta_leak(line))
    return meta_count / float(len(sentences))
