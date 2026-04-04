from __future__ import annotations

from typing import Any, Dict, List

from ..models import EventAtom, NarrativeState, WorldBible
from ..schemas import validate_payload
from .models import WorldPack


def validate_worldpack_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    try:
        validate_payload(payload, "worldpack.schema.json")
    except Exception as exc:  # noqa: BLE001
        errors.append("schema:%s" % exc)

    runtime_world_bible = payload.get("runtime_world_bible")
    runtime_initial_state = payload.get("runtime_initial_state")
    runtime_event_atoms = payload.get("runtime_event_atoms")

    if runtime_world_bible is not None:
        try:
            validate_payload(runtime_world_bible, "world_bible.schema.json")
            WorldBible.from_dict(runtime_world_bible)
        except Exception as exc:  # noqa: BLE001
            errors.append("runtime_world_bible:%s" % exc)
    else:
        warnings.append("runtime_world_bible_missing:will_synthesize")

    if runtime_initial_state is not None:
        try:
            validate_payload(runtime_initial_state, "narrative_state.schema.json")
            NarrativeState.from_dict(runtime_initial_state)
        except Exception as exc:  # noqa: BLE001
            errors.append("runtime_initial_state:%s" % exc)
    else:
        warnings.append("runtime_initial_state_missing:will_synthesize")

    if runtime_event_atoms is not None:
        try:
            for item in runtime_event_atoms:
                validate_payload(item, "event_atom.schema.json")
                EventAtom.from_dict(item)
        except Exception as exc:  # noqa: BLE001
            errors.append("runtime_event_atoms:%s" % exc)
    else:
        warnings.append("runtime_event_atoms_missing:will_synthesize")

    if not payload.get("scene_blueprints"):
        errors.append("scene_blueprints_missing")
    if not payload.get("characters"):
        errors.append("characters_missing")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "world_id": payload.get("world_id"),
        "version": payload.get("version"),
    }


def validate_worldpack(worldpack: WorldPack) -> Dict[str, Any]:
    return validate_worldpack_payload(worldpack.to_dict())
