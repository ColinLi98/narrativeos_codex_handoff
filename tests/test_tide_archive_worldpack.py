from src.narrativeos.benchmark.runner import run_benchmark
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.longform_capability import longform_structure_counts
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry
from src.narrativeos.worldpacks.validator import validate_worldpack_payload


def test_tide_archive_worldpack_is_benchmark_registered():
    registry = FileSystemWorldRegistry()
    card = registry.get_published_world("tide_archive_memory_debt")

    assert card["catalog_role"] == "published"
    assert card["benchmark_enabled"] is True
    assert card["world_version_id"] == "tide_archive_memory_debt@0.1.0"


def test_tide_archive_worldpack_meets_longform_structure_contract():
    registry = FileSystemWorldRegistry()
    payload = registry.get_published_world("tide_archive_memory_debt")["worldpack"]
    validation = validate_worldpack_payload(payload)
    counts = longform_structure_counts(payload)

    assert validation["ok"] is True
    assert payload["series_plan"]["total_chapter_target"] == 100
    assert payload["series_plan"]["total_volume_target"] == 5
    assert len(payload["volume_plans"]) == 5
    assert len(payload["arc_plans"]) == 15
    assert counts["character_count"] == 10
    assert counts["scene_blueprint_count"] == 12
    assert counts["location_count"] == 8
    assert counts["scene_family_count"] >= 10
    assert counts["distinct_role_pair_count"] >= 12
    assert validation["content_quality_contract_coverage"]["ok"] is True


def test_tide_archive_worldpack_carries_benchmark_windows_and_thresholds():
    registry = FileSystemWorldRegistry()
    payload = registry.get_published_world("tide_archive_memory_debt")["worldpack"]
    benchmark_pack = payload["metadata"]["benchmark_test_pack"]

    assert benchmark_pack["route_families"] == ["真相优先", "关系优先", "生存优先", "权力优先"]
    assert benchmark_pack["ending_families"] == ["公开揭露", "私下保全", "牺牲封口", "带罪共存"]
    assert [item["window"] for item in benchmark_pack["manual_review_windows"]] == [
        "1-5",
        "18-22",
        "38-42",
        "58-62",
        "78-82",
        "96-100",
    ]
    assert [item["chapter"] for item in benchmark_pack["interactive_scenarios"]] == [15, 33, 52]
    assert benchmark_pack["acceptance_thresholds"]["voice_separation_score_min"] == 0.65


def test_tide_archive_worldpack_applies_round_one_window_repairs():
    registry = FileSystemWorldRegistry()
    payload = registry.get_published_world("tide_archive_memory_debt")["worldpack"]

    archive_anomaly = next(item for item in payload["scene_blueprints"] if item["scene_id"] == "archive_anomaly")
    submerged_return = next(item for item in payload["scene_blueprints"] if item["scene_id"] == "submerged_return")
    late_arc = next(item for item in payload["arc_plans"] if item["arc_id"] == "tide_archive_memory_debt::series::volume_5::arc_1")
    late_task = next(item for item in late_arc["chapter_tasks"] if item["chapter_task_id"] == "tide_archive_memory_debt::series::volume_5::arc_1::task_2")

    assert archive_anomaly["quality_contract"]["dialogue_pressure"] == "high"
    assert "information_reveal" in archive_anomaly["quality_contract"]["variation_axes"]
    assert "object_state" in archive_anomaly["quality_contract"]["detail_anchor_types"]
    assert archive_anomaly["beats_template"][0].startswith("闻汐从防潮盒里抽出")

    assert submerged_return["quality_contract"]["dialogue_pressure"] == "high"
    assert "information_reveal" in submerged_return["quality_contract"]["variation_axes"]
    assert "object_state" in submerged_return["quality_contract"]["detail_anchor_types"]
    assert submerged_return["beats_template"][0].startswith("打捞箱开封")

    assert "next_chapter_hook_intensified" in late_arc["completion_conditions"]
    assert late_task["quality_contract"]["delayed_payoff_window"] == {"min_chapters": 1, "max_chapters": 4}
    assert late_task["promise_targets"] == ["tide_archive_memory_debt::series::volume_5::arc_1::promise_turn"]
    assert "contract_q09_repair_window=late" in late_task["notes"]
    assert "结尾必须把下一章问题推出去" in late_task["objective"]


def test_tide_archive_worldpack_applies_group_scene_realization_and_emotion_action_repairs():
    registry = FileSystemWorldRegistry()
    payload = registry.get_published_world("tide_archive_memory_debt")["worldpack"]

    scene_realization = payload["scene_realization_contracts"]["default"]
    emotion_actions = payload["emotion_action_policies"]["default"]["action_map"]

    assert len(scene_realization["scene_openings"]["false_peace"]) >= 3
    assert len(scene_realization["scene_hooks"]["false_peace"]) >= 3
    assert len(scene_realization["scene_openings"]["temptation"]) >= 3
    assert len(scene_realization["scene_hooks"]["temptation"]) >= 3
    assert len(scene_realization["scene_openings"]["truth_trial"]) >= 3
    assert len(scene_realization["scene_hooks"]["truth_trial"]) >= 3
    assert len(scene_realization["scene_openings"]["karma_ripening"]) >= 3
    assert len(scene_realization["scene_hooks"]["karma_ripening"]) >= 3
    assert "misrecognition" in scene_realization["scene_openings"]
    assert "debt_exchange" in scene_realization["scene_hooks"]

    assert len(emotion_actions["false_peace"]["entry"]) >= 3
    assert len(emotion_actions["false_peace"]["pressure"]) >= 3
    assert len(emotion_actions["karma_ripening"]["pivot"]) >= 3
    assert len(emotion_actions["debt_exchange"]["echo"]) >= 3

    xu_hui = payload["voice_profiles"]["xu_hui"]
    song_wanqing = payload["voice_profiles"]["song_wanqing"]
    assert len(xu_hui["opening_style"]) >= 3
    assert len(xu_hui["signature_replies"]) >= 3
    assert len(song_wanqing["pressure_style"]) >= 3
    assert len(song_wanqing["echo_style"]) >= 3


def test_tide_archive_worldpack_standard_benchmark_smoke(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "tide_archive_benchmark.db"))

    report = run_benchmark(
        repository=repository,
        golden_dir=tmp_path / "goldens",
        worldpack="tide_archive_memory_debt",
    )

    world = report["worlds"][0]
    assert world["world_id"] == "tide_archive_memory_debt"
    assert world["completion_ratio"] == 1.0
    assert world["stop_reason"] == "chapter_budget_reached"
    assert world["voice_separation_score"] >= 0.65
    assert report["phase_a_quality_gate"]["ok"] is True
    issue_codes = {item["issue_code"] for item in world["top_issue_categories"]}
    assert "Q03" not in issue_codes
    assert "Q04" not in issue_codes


def test_tide_runtime_bundle_preserves_character_id_required_roles():
    registry = FileSystemWorldRegistry()
    runtime = registry.get_runtime_bundle("tide_archive_memory_debt@0.1.0")

    first_event = runtime.event_atoms[0]
    second_event = runtime.event_atoms[1]

    assert first_event.actors == ["wen_xi", "gu_chenzhou"]
    assert second_event.actors == ["wen_xi", "gu_chenzhou"]
