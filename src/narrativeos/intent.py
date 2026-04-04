from __future__ import annotations

from typing import Dict, Optional


DEFAULT_INTENT_AXES = (
    "ambition",
    "loyalty",
    "honesty",
    "secrecy",
    "romance",
    "sacrifice",
    "cruelty",
    "curiosity",
    "selfhood",
    "risk",
    "duty",
)

KEYWORD_MAP = {
    "考": {"ambition": 0.6, "duty": 0.4},
    "家": {"loyalty": 0.4, "duty": 0.2},
    "真话": {"honesty": 0.8, "selfhood": 0.4},
    "坦白": {"honesty": 0.7},
    "秘密": {"secrecy": 0.8},
    "林绾": {"romance": 0.6},
    "爱": {"romance": 0.5},
    "试探": {"curiosity": 0.5},
    "自己": {"selfhood": 0.5},
    "冒险": {"risk": 0.7},
}


class SimpleIntentParser:
    def parse(self, raw_input: str, *, overrides: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        if overrides:
            return {key: float(value) for key, value in overrides.items()}

        scores = {axis: 0.0 for axis in DEFAULT_INTENT_AXES}
        for keyword, weights in KEYWORD_MAP.items():
            if keyword in raw_input:
                for axis, value in weights.items():
                    scores[axis] = max(scores[axis], value)

        active_scores = {key: value for key, value in scores.items() if value > 0.0}
        return active_scores or {"curiosity": 0.4}
