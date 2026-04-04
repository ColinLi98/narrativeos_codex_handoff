from __future__ import annotations

from typing import Dict

from ..prose_linter import lint_prose


def lint_chapter_draft(text: str) -> Dict[str, object]:
    return lint_prose(text)
