from __future__ import annotations

import json
from pathlib import Path

from .models import EventAtom, NarrativeState, WorldBible


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_FILES = {
    "planner": "planner.md",
    "actor": "actor.md",
    "critic_consistency": "critic_consistency.md",
    "critic_drama": "critic_drama.md",
    "critic_diversity": "critic_diversity.md",
    "renderer": "renderer.md",
}


def get_prompt_text(name: str) -> str:
    prompt_path = PROMPT_DIR / PROMPT_FILES[name]
    return prompt_path.read_text(encoding="utf-8")


def render_candidate_user_prompt(
    *,
    world: WorldBible,
    state: NarrativeState,
    depth: int,
    min_candidates: int,
    max_candidates: int,
) -> str:
    payload = {
        "task": "generate_candidate_events",
        "depth": depth,
        "min_candidates": min_candidates,
        "max_candidates": max_candidates,
        "world": world.to_dict(),
        "state": state.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_scene_user_prompt(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    state_after: NarrativeState,
    event: EventAtom,
) -> str:
    payload = {
        "task": "render_scene",
        "world": world.to_dict(),
        "state_before": state_before.to_dict(),
        "state_after": state_after.to_dict(),
        "event": event.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
