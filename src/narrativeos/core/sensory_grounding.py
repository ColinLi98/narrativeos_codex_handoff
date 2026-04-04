from __future__ import annotations

from ..models import SceneBeat, WorldBible
from .contracts import style_pack_from_world


def _pick_line(lines: list[str], index: int) -> str:
    return lines[index % len(lines)] if lines else ""


def scene_atmosphere(world: WorldBible, beat: SceneBeat) -> str:
    style_pack = style_pack_from_world(world)
    location = beat.event.location or "generic"
    beat_index = getattr(beat, "beat_index", 0)
    slots = style_pack.sensory_grounding.location_slots.get(location, {})
    atmosphere = slots.get("atmosphere", [])
    if atmosphere:
        return _pick_line(atmosphere, beat_index)
    generic = style_pack.sensory_grounding.generic_slots.get("atmosphere", [])
    if generic:
        return _pick_line(generic, beat_index)
    return f"{location}里并不安静，连空气都像在替谁压住一口没说完的话。"


def scene_detail(world: WorldBible, beat: SceneBeat, *, repeated: bool) -> str:
    style_pack = style_pack_from_world(world)
    location = beat.event.location or "generic"
    beat_index = getattr(beat, "beat_index", 0)
    slots = style_pack.sensory_grounding.location_slots.get(location, {})
    key = "repeat_detail" if repeated else "detail"
    details = slots.get(key, [])
    if details:
        return _pick_line(details, beat_index)
    generic = style_pack.sensory_grounding.generic_slots.get(key, [])
    if generic:
        return _pick_line(generic, beat_index)
    return "灯影和衣角的轻微动静都被这一场沉默压得更清。"
