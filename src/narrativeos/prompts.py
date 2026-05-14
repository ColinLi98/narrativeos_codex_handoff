from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from .models import ChapterPlan, EventAtom, NarrativeState, SceneBeat, SceneRenderSpec, WorldBible
from .quality.hard_constraints import build_generation_hard_constraint_prompt_contract


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
    chapter_plan: Optional[ChapterPlan] = None,
    scene_beats: Optional[List[SceneBeat]] = None,
    render_spec: Optional[SceneRenderSpec] = None,
) -> str:
    target_chapters = int(getattr(getattr(world, "series_plan", None), "total_chapter_target", 0) or 0)
    payload = {
        "task": "render_scene",
        "world": world.to_dict(),
        "state_before": state_before.to_dict(),
        "state_after": state_after.to_dict(),
        "event": event.to_dict(),
        "generation_hard_constraints": build_generation_hard_constraint_prompt_contract(
            target_chapters=target_chapters,
            worldpack_payload=world.to_dict(),
        ),
    }
    if chapter_plan is not None:
        payload["chapter_plan"] = chapter_plan.to_dict()
    if scene_beats is not None:
        payload["scene_beats"] = [beat.to_dict() for beat in scene_beats]
    if render_spec is not None:
        payload["render_spec"] = render_spec.to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2)
