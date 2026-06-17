from pathlib import Path

from src.narrativeos.quality.grounding import build_grounding_check, build_grounding_decision
from src.narrativeos.repository import SQLAlchemyRepository


def test_grounding_engine_supports_pass_weak_failed_and_not_applicable():
    passed = build_grounding_decision(
        scenario_id="reader_continue",
        text="她终于决定继续把这句真话说出来。",
        coverage_context={
            "selected_event_ids": ["她", "决定", "继续", "真话", "说出来"],
            "scene_beats": [{"event": {"title": "她决定说出真话", "summary": "她终于决定继续把真话说出来", "scene_function": "truth_trial", "location": "回廊"}}],
            "chapter_task": {"objective": "继续说出真话", "summary": "她决定继续把真话说出来", "target_words": 2200},
        },
        state_after=type("State", (), {"world_facts": ["她决定继续把真话说出来", "回廊里的真话已经被说出"], "open_promises": []})(),
        worldpack_payload={"world_bible": {"theme": "真话", "summary": "她决定继续把真话说出来", "location": "回廊"}},
    )
    assert passed.status in {"passed", "weak"}

    weak = build_grounding_decision(
        scenario_id="reader_continue",
        text="她终于决定继续把这句真话说出来，但是另一段过去仍然压在心里。",
        coverage_context={
            "scene_beats": [{"event": {"title": "她决定说出真话", "summary": "她终于决定继续", "scene_function": "truth_trial"}}],
            "chapter_task": {"objective": "继续说出真话"},
        },
        state_after=type("State", (), {"world_facts": ["她决定继续"], "open_promises": []})(),
        worldpack_payload={"world_bible": {"theme": "真话"}},
    )
    assert weak.status in {"weak", "failed"}

    failed = build_grounding_decision(
        scenario_id="publish_candidate",
        text="她已经回到了从未存在过的第七王朝，并公开承认旧世界的债已经全部结束。",
        coverage_context={
            "scene_beats": [{"event": {"title": "公开承认旧债", "summary": "她承认旧债", "scene_function": "truth_trial"}}],
            "chapter_task": {"objective": "承认旧债"},
        },
        state_after=type("State", (), {"world_facts": ["旧债仍未结束"], "open_promises": []})(),
        worldpack_payload={"world_bible": {"theme": "旧债"}},
    )
    assert failed.status in {"weak", "failed"}

    not_applicable = build_grounding_decision(
        scenario_id="reader_continue",
        text="风停了。",
        coverage_context={},
        state_after=type("State", (), {"world_facts": [], "open_promises": []})(),
        worldpack_payload={},
    )
    assert not_applicable.status == "not_applicable"


def test_grounding_check_persists_in_repository(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "grounding_repo.db"))
    check = repository.save_grounding_check(
        build_grounding_check(
            scenario_id="reader_continue",
            text="她终于决定继续把这句真话说出来。",
            source_surface="reader",
            trace_id="trace_grounding_1",
            world_version_id="jade_court_exam@0.1.0",
            session_id="session_grounding_1",
            chapter_id="chapter_grounding_1",
            coverage_context={"chapter_task": {"objective": "说出真话"}},
            state_after=type("State", (), {"world_facts": ["说出真话"], "open_promises": []})(),
            worldpack_payload={"world_bible": {"theme": "真话"}},
        ).to_dict()
    )
    assert check["trace_id"] == "trace_grounding_1"
    assert repository.list_grounding_checks(trace_id="trace_grounding_1")[0]["grounding_check_id"] == check["grounding_check_id"]
