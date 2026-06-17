from src.narrativeos.services.longform_capability import build_longform_500_product_readiness


def test_longform_500_product_readiness_separates_structure_claim_from_product_ready_evidence():
    readiness = build_longform_500_product_readiness(
        claim_safe_band="500",
        longform_readiness={"status": "ready"},
        simulation_report={},
    )

    assert readiness["ready"] is False
    assert readiness["product_ready_band"] is None
    blocker_keys = {item["key"] for item in readiness["blockers"]}
    assert "longform_500_static_signoff_missing" in blocker_keys
    assert "longform_500_human_review_closeout_missing" in blocker_keys
    assert "longform_500_weakest_stop_ready_missing" in blocker_keys
    assert "longform_500_hard_constraint_evidence_missing" in blocker_keys
    assert "longform_500_scene_card_visible_text_evidence_missing" in blocker_keys
    assert "reader_500_replay_projection_evidence_missing" in blocker_keys


def test_longform_500_product_readiness_passes_with_full_paid_pilot_evidence():
    readiness = build_longform_500_product_readiness(
        claim_safe_band="1000",
        longform_readiness={"status": "ready"},
        simulation_report={
            "cross_pack_summary": {
                "longform_500_signoff": {"ready": True},
                "longform_500_interactive_signoff": {"ready": True},
                "longform_500_human_review_closeout": {"ready": True},
                "weakest_pack_polish_program": {"status": "stop_ready", "continue_worlds": []},
                "generation_hard_constraint_summary": {
                    "chapter_count": 3000,
                    "hard_fail_count": 0,
                    "scene_card_visible_text_audit": {"violation_count": 0},
                },
                "reader_replay_projection_summary": {"ready": True},
                "benchmark_runtime_profile": {"total_wall_ms": 3_600_000},
            }
        },
    )

    assert readiness["ready"] is True
    assert readiness["product_ready_band"] == "500"
    assert readiness["blockers"] == []


def test_longform_500_product_readiness_blocks_when_human_or_weakest_stop_ready_missing():
    readiness = build_longform_500_product_readiness(
        claim_safe_band="500",
        longform_readiness={"status": "ready"},
        simulation_report={
            "cross_pack_summary": {
                "longform_500_signoff": {"ready": True},
                "longform_500_interactive_signoff": {"ready": True},
                "generation_hard_constraint_summary": {
                    "chapter_count": 3000,
                    "hard_fail_count": 0,
                    "scene_card_visible_text_audit": {"violation_count": 0},
                },
                "reader_storybook_500_verification": {"ready": True},
                "benchmark_runtime_profile": {"total_wall_ms": 3_600_000},
            }
        },
    )

    blocker_keys = {item["key"] for item in readiness["blockers"]}
    assert readiness["ready"] is False
    assert "longform_500_human_review_closeout_missing" in blocker_keys
    assert "longform_500_weakest_stop_ready_missing" in blocker_keys
    assert readiness["product_ready_band"] is None
