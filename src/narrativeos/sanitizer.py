from __future__ import annotations

import re
from typing import Iterable


ENGINEERING_PATTERNS = [
    re.compile(r"\bevent_id\b", re.IGNORECASE),
    re.compile(r"\bscene_function\b", re.IGNORECASE),
    re.compile(r"\bconvergence_key\b", re.IGNORECASE),
    re.compile(r"\bseed_id\b", re.IGNORECASE),
    re.compile(r"\bdebt_type\b", re.IGNORECASE),
    re.compile(r"\bendgame_shape\b", re.IGNORECASE),
    re.compile(r"\b(?:greed|anger|delusion|pride|doubt)\b", re.IGNORECASE),
    re.compile(r"\broute\s*=", re.IGNORECASE),
    re.compile(r"->"),
    re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b"),
    re.compile(r"\b(?:duty|ambition|love|selfhood|truth|reform|sacrifice|loyalty|curiosity|destiny|system|power|family|hope|loss|cost)\b", re.IGNORECASE),
]


def sanitize_text(text: str) -> str:
    cleaned = text
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
