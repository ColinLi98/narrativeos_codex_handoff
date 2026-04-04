from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


def repetition_score(lines: Iterable[str]) -> float:
    tokens = []
    for line in lines:
        words = [token for token in re.split(r"[\s，。、“”‘’！？：；,.!?]+", line) if token]
        tokens.extend(words)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / float(len(tokens))
