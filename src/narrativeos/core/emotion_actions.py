from __future__ import annotations

from ..models import SceneBeat, WorldBible
from .contracts import style_pack_from_world


def _pick_line(lines: list[str], index: int) -> str:
    return lines[index % len(lines)] if lines else ""


def compose_emotion_action(world: WorldBible, beat: SceneBeat, *, repeated: bool) -> str:
    style_pack = style_pack_from_world(world)
    scene_function = beat.event.scene_function
    job = beat.dramatic_job
    beat_index = getattr(beat, "beat_index", 0)
    action_pool = style_pack.emotion_actions.action_map.get(scene_function, {})
    if repeated and action_pool.get("repeat"):
        return _pick_line(action_pool["repeat"], beat_index)
    if action_pool.get(job):
        return _pick_line(action_pool[job], beat_index)
    defaults = {
        "entry": "桌上的器物轻轻一碰，谁都知道这一步已经走出去，很难再收回来。",
        "pressure": "连抬眼、换气和指尖的细小停顿都带上了掂量，像谁先多动一下，谁就会先露底。",
        "pivot": "那一点极轻的停顿和改口，让场面从还能周旋，变成了不得不选边。",
        "aftermath": "说出口的那几句已经停了，可散开时每个人都比来时更沉。",
        "echo": "越到最后，越能听见那些没说尽的话在场里慢慢回身索账。",
    }
    return defaults.get(job, "动作并不大，可局势已经变了味道。")
