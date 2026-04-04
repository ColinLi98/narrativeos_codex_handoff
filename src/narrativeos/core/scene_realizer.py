from __future__ import annotations

from ..models import NarrativeState, SceneBeat, WorldBible
from .contracts import style_pack_from_world
from .dialogue import compose_dialogue
from .emotion_actions import compose_emotion_action
from .sensory_grounding import scene_atmosphere, scene_detail


def realize_scene_opening(world: WorldBible, beat: SceneBeat, chapter_goal: str, conflict_axis: str) -> str:
    style_pack = style_pack_from_world(world)
    opening = style_pack.scene_realization.scene_openings.get(beat.event.scene_function, [])
    chosen = opening[0] if opening else f"{chapter_goal}。{scene_atmosphere(world, beat)}"
    return " ".join([chosen, f"压下来的先是{conflict_axis}，紧跟着便是人物再也躲不开的那一点心意。"])


def realize_beat(world: WorldBible, state_before: NarrativeState, beat: SceneBeat, *, repeated: bool) -> str:
    return " ".join(
        [
            compose_emotion_action(world, beat, repeated=repeated),
            compose_dialogue(world, state_before, beat, repeated=repeated),
            scene_detail(world, beat, repeated=repeated),
        ]
    )


def realize_hook(world: WorldBible, ending_hook: str, scene_function: str) -> str:
    style_pack = style_pack_from_world(world)
    hook = style_pack.scene_realization.scene_hooks.get(scene_function, [])
    if hook:
        return hook[0]
    return f"等人声慢慢静下去时，留下来的并不是哪一句话更重，而是{ending_hook}。那一点没说尽的情绪已经追到下一次开口之前。"
