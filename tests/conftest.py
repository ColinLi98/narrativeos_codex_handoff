from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.narrativeos.models import EventAtom, NarrativeState, WorldBible


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str):
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def demo_world() -> WorldBible:
    return WorldBible.from_dict(load_example("demo_world_bible.json"))


@pytest.fixture
def demo_state() -> NarrativeState:
    return NarrativeState.from_dict(load_example("demo_initial_state.json"))


@pytest.fixture
def demo_events():
    return [EventAtom.from_dict(item) for item in load_example("demo_event_atoms.json")]
