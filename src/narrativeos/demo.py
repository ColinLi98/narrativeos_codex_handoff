from __future__ import annotations

import json
from pathlib import Path

from .models import EventAtom, NarrativeState, WorldBible
from .pipeline import plan_next_turn_from_events


def load_json(name: str):
    base = Path(__file__).resolve().parents[2] / "examples"
    return json.loads((base / name).read_text(encoding="utf-8"))


def main() -> None:
    world = WorldBible.from_dict(load_json("demo_world_bible.json"))
    state = NarrativeState.from_dict(load_json("demo_initial_state.json"))
    events = [EventAtom.from_dict(item) for item in load_json("demo_event_atoms.json")]
    result = plan_next_turn_from_events(state, events, world=world, beam_width=3, depth=2)

    print("=== NarrativeOS Demo ===")
    print("Status:", result["status"])
    if result["status"] != "ok":
        print("No legal scene available.")
        return

    reader_view = result["reader_view"]
    print("Chapter:", reader_view["chapter_title"])
    print("Summary:", result["updated_state_summary"])
    print("Recap:", reader_view["recap"])
    print("Body preview:", reader_view["body"][:160] + "...")
    print("Choices:", " / ".join(reader_view["choices"]) if reader_view["choices"] else "继续阅读")


if __name__ == "__main__":
    main()
