from src.narrativeos.models import EvaluationDecision, EvaluationReport, EvaluationScores
from src.narrativeos.quality.adapter import build_guardrail_records
from src.narrativeos.quality.hard_constraints import (
    DEFAULT_READER_CHOICE,
    build_generation_hard_constraint_prompt_contract,
    enforce_generation_hard_constraints,
    evaluate_reader_generation_hard_constraints,
    resolve_generation_hard_constraint_profile,
    summarize_generation_hard_constraints,
)
from src.narrativeos.quality.models import GroundingCheck


def _report() -> EvaluationReport:
    return EvaluationReport(
        chapter_id="chapter_hard_constraints",
        world_version_id="test_world@0.1.0",
        session_id="session_hard_constraints",
        decision=EvaluationDecision(decision="pass", reason="test"),
        issues=[],
        scores=EvaluationScores(
            readability=0.8,
            scene_density=0.7,
            character_fidelity=0.9,
            causal_continuity=0.85,
            pacing=0.75,
            choice_distinctness=0.65,
            hook_quality=0.7,
            monetize_ready=0.6,
            overall_score=0.76,
        ),
        hard_validator_results={"failed": False},
        summary="test report",
        created_at="2026-04-27T12:00:00+00:00",
    )


def _failed_grounding() -> GroundingCheck:
    return GroundingCheck(
        grounding_check_id="grounding_failed_hard_constraints",
        trace_id=None,
        status="failed",
        confidence=0.1,
        evidence_refs=[],
        unsupported_claims=["没有支撑的真相。"],
        reason_codes=["grounding_missing_support"],
        summary="failed",
        source_surface="reader",
        world_version_id="test_world@0.1.0",
        session_id="session_hard_constraints",
        chapter_id="chapter_hard_constraints",
    )


def test_genre_profile_cannot_disable_universal_rules():
    profile = resolve_generation_hard_constraint_profile(
        target_chapters=50,
        genre_profile="urban_mystery",
        config={
            "generation_hard_constraints": {
                "genre_profiles": {
                    "mystery": {
                        "aliases": ["urban_mystery"],
                        "disabled_rules": ["grounding_failed", "schema_complete"],
                        "threshold_overrides": {"min_choice_count": 3},
                    }
                }
            }
        },
    )

    assert "grounding_failed" in profile["active_rules"]
    assert "schema_complete" in profile["active_rules"]
    assert profile["thresholds"]["min_choice_count"] == 3
    assert profile["profile_warnings"][0]["code"] == "universal_rules_cannot_be_disabled"


def test_reader_hard_constraints_detect_schema_slots_and_choice_budget():
    result = evaluate_reader_generation_hard_constraints(
        reader_view={
            "chapter_title": "",
            "body": "真话窗口又一次打开。被压回去的 、 并没有松开。",
            "choices": [DEFAULT_READER_CHOICE, DEFAULT_READER_CHOICE, ""],
            "relationship_hints": [],
        },
        target_chapters=50,
    )

    assert result["ok"] is False
    assert {"schema_complete", "broken_slot", "choice_text_budget"} <= set(result["failed_checks"])
    assert result["length_profile"] == "long_route_50"


def test_reader_hard_constraints_include_scene_card_visible_text():
    result = evaluate_reader_generation_hard_constraints(
        reader_view={
            "chapter_title": "第 12 章",
            "body": "她把潮湿的纸页按在灯下，指腹停在旧印泥边缘，等对方先开口。",
            "choices": ["先追问灯下的纸页。", "暂时守住旧印泥。"],
            "relationship_hints": [],
            "scene_card": {
                "summary": "这一章把旧案线索推到眼前。",
                "story_beats": ["从这里起，证据开始转向。"],
            },
        },
        target_chapters=500,
    )

    assert result["ok"] is False
    assert "meta_narration_leak" in result["failed_checks"]
    assert any(item["field"] == "scene_card.summary" for item in result["violations"])


def test_hard_constraint_failure_forces_blocked_guardrail_records():
    bundle = enforce_generation_hard_constraints(
        {
            "report": _report(),
            "quality_gate": {"ok": True, "enforced_decision": "pass", "failed_checks": [], "failed_contract_checks": []},
            "grounding_check": _failed_grounding(),
        },
        reader_view={
            "chapter_title": "第 12 章",
            "body": "这一章从这里起把 event_id -> route_id 的变化解释清楚。",
            "choices": ["继续追问眼前的裂口。", "先守住当前证据。"],
        },
        grounding_check=_failed_grounding(),
        source_surface="reader",
        target_chapters=50,
    )

    gate = bundle["quality_gate"]
    assert gate["ok"] is False
    assert gate["enforced_decision"] == "block"
    assert "grounding_failed" in gate["failed_checks"]
    assert gate["hard_constraint_result"]["ok"] is False

    records = build_guardrail_records(
        quality_bundle=bundle,
        scenario_id="reader_continue",
        source_surface="reader",
        source_ref={"kind": "chapter", "chapter_id": "chapter_hard_constraints", "rendered_text": "正文"},
        world_version_id="test_world@0.1.0",
        session_id="session_hard_constraints",
        chapter_id="chapter_hard_constraints",
    )
    assert records["decision"].status == "blocked"
    assert records["event"].payload["hard_constraint_result"]["failed_checks"]


def test_generation_hard_constraint_prompt_contract_is_compact_and_cross_genre():
    contract = build_generation_hard_constraint_prompt_contract(
        target_chapters=100,
        worldpack_payload={"metadata": {"author_brief": {"genre_preset": "xianxia"}}},
    )

    assert contract["profile_id"] == "fantasy:long_route_50"
    assert contract["repair_policy"] == "repair_once_then_fail_closed"
    assert any(item["rule_id"] == "grounding_failed" for item in contract["hard_rules"])


def test_summarize_generation_hard_constraints_counts_repairs_and_hard_fails():
    summary = summarize_generation_hard_constraints(
        [
            {
                "quality_gate": {
                    "hard_constraint_result": {
                        "ok": False,
                        "failed_checks": ["schema_complete"],
                        "repair_attempts": 1,
                    }
                }
            },
            {
                "quality_gate": {
                    "hard_constraint_result": {
                        "ok": True,
                        "failed_checks": [],
                        "repair_attempts": 1,
                        "repair_success": True,
                    }
                }
            },
        ]
    )

    assert summary["hard_fail_count"] == 1
    assert summary["repair_attempt_count"] == 2
    assert summary["repair_success_count"] == 1
    assert summary["violation_mix"][0]["rule_id"] == "schema_complete"


def test_summarize_generation_hard_constraints_reports_scene_card_audit():
    summary = summarize_generation_hard_constraints(
        [
            {
                "quality_gate": {
                    "hard_constraint_result": {
                        "ok": False,
                        "failed_checks": ["meta_narration_leak"],
                        "violations": [
                            {
                                "rule_id": "meta_narration_leak",
                                "issue_code": "Q02",
                                "field": "scene_card.summary",
                            }
                        ],
                    }
                }
            }
        ]
    )

    audit = summary["scene_card_visible_text_audit"]
    assert audit["violation_count"] == 1
    assert audit["failed_rule_mix"][0]["rule_id"] == "meta_narration_leak"
    assert summary["field_violation_mix"][0]["field"] == "scene_card.summary"
