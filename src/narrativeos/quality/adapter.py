from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from ..models import EvaluationReport
from .config import get_quality_policy_for_scenario
from .grounding import build_grounding_check
from .models import ContentQualityScore, GroundingCheck, GuardrailDecision, QualityEvent, ReviewCase


SCENARIO_CASE_TYPES = {
    "reader_continue": "runtime_quality",
    "author_generate_chapter": "content_quality",
    "author_manual_edit": "content_quality",
    "publish_candidate": "publish_quality",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_from_quality_gate(quality_gate: Dict[str, Any]) -> str:
    if bool(quality_gate.get("ok", False)):
        return "passed"
    if str(quality_gate.get("enforced_decision") or "") == "block":
        return "blocked"
    return "review_required"


def _coerce_grounding_check(value: Any) -> Optional[GroundingCheck]:
    if isinstance(value, GroundingCheck):
        return value
    if isinstance(value, dict) and value:
        return GroundingCheck.from_dict(value)
    return None


def enforce_grounding_quality_gate(
    quality_bundle: Dict[str, Any],
    *,
    grounding_check: GroundingCheck | Dict[str, Any],
    source_surface: str,
) -> Dict[str, Any]:
    bundle = dict(quality_bundle or {})
    check = _coerce_grounding_check(grounding_check)
    if check is None:
        return bundle
    quality_gate = dict(bundle.get("quality_gate") or {})
    grounding_payload = check.to_dict()
    quality_gate["grounding_status"] = check.status
    quality_gate["grounding_result"] = grounding_payload
    quality_gate.setdefault("code", "chapter_quality_guard_failed")
    if check.status == "failed":
        failed_checks = [
            str(item)
            for item in list(quality_gate.get("failed_checks") or [])
            if str(item)
        ]
        for reason_code in list(check.reason_codes or []) or ["grounding_missing_support"]:
            if reason_code not in failed_checks:
                failed_checks.append(reason_code)
        quality_gate["ok"] = False
        quality_gate["failed_checks"] = failed_checks
        quality_gate.setdefault("failed_contract_checks", [])
        quality_gate["enforced_decision"] = "block" if str(source_surface or "") == "reader" else "rewrite"
        quality_gate["summary"] = str(check.summary or "grounding failed") or "grounding failed"
        quality_gate["blocking_dimension"] = "grounding"
    bundle["quality_gate"] = quality_gate
    bundle["grounding_check"] = check
    return bundle


def _rule_hits(quality_bundle: Dict[str, Any]) -> list[Dict[str, Any]]:
    quality_gate = dict(quality_bundle.get("quality_gate") or {})
    failed_checks = [str(item) for item in list(quality_gate.get("failed_checks") or []) if str(item)]
    contract_checks = [str(item) for item in list(quality_gate.get("failed_contract_checks") or []) if str(item)]
    if not failed_checks and not contract_checks:
        return [{"rule_id": "chapter_quality_gate", "reason_code": "passed", "blocking": False}]
    return [
        {
            "rule_id": "chapter_quality_gate",
            "reason_code": reason_code,
            "blocking": str(quality_gate.get("enforced_decision") or "") == "block",
        }
        for reason_code in failed_checks + contract_checks
    ]


def _reason_codes(report: EvaluationReport, quality_gate: Dict[str, Any]) -> list[str]:
    issue_codes = [str(issue.issue_code) for issue in list(report.issues or []) if str(issue.issue_code or "")]
    failed_checks = [str(item) for item in list(quality_gate.get("failed_checks") or []) if str(item)]
    if not issue_codes and not failed_checks:
        return ["quality_passed"]
    ordered = []
    for item in issue_codes + failed_checks:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _evidence_refs(report: EvaluationReport, source_ref: Dict[str, Any]) -> list[Dict[str, Any]]:
    refs = []
    chapter_id = str(source_ref.get("chapter_id") or report.chapter_id or "")
    if chapter_id:
        refs.append({"kind": "evaluation_report", "ref_id": chapter_id})
    for issue in list(report.issues or []):
        if issue.evidence:
            refs.append(
                {
                    "kind": "issue_evidence",
                    "ref_id": str(issue.issue_code),
                    "issue_code": str(issue.issue_code),
                    "preview": " | ".join(str(item) for item in list(issue.evidence or [])[:3]),
                }
            )
    return refs


def build_phase1_grounding_result() -> Dict[str, Any]:
    return {
        "status": "not_evaluated",
        "mode": "observe_only",
        "evidence_refs": [],
        "missing_support": [],
        "contradictions": [],
    }


def build_guardrail_records(
    *,
    quality_bundle: Dict[str, Any],
    scenario_id: str,
    source_surface: str,
    source_ref: Dict[str, Any],
    world_version_id: Optional[str] = None,
    session_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    coverage_context: Optional[Dict[str, Any]] = None,
    state_after: Optional[Any] = None,
    worldpack_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    report = quality_bundle.get("report")
    if isinstance(report, dict):
        report = EvaluationReport.from_dict(report)
    assert isinstance(report, EvaluationReport)
    policy = get_quality_policy_for_scenario(scenario_id)
    grounding_check = _coerce_grounding_check(quality_bundle.get("grounding_check") or quality_bundle.get("grounding_result"))
    if grounding_check is None:
        grounding_check = build_grounding_check(
            scenario_id=scenario_id,
            text=str(source_ref.get("rendered_text") or ""),
            source_surface=source_surface,
            world_version_id=world_version_id,
            session_id=session_id,
            chapter_id=chapter_id,
            coverage_context=coverage_context,
            state_after=state_after,
            worldpack_payload=worldpack_payload,
        )
    quality_bundle = enforce_grounding_quality_gate(
        quality_bundle,
        grounding_check=grounding_check,
        source_surface=source_surface,
    )
    quality_gate = dict(quality_bundle.get("quality_gate") or {})
    hard_constraint_result = dict(quality_gate.get("hard_constraint_result") or {})
    status = _status_from_quality_gate(quality_gate)
    trace_id = f"quality_trace_{uuid4().hex[:12]}"
    score_id = f"quality_score_{uuid4().hex[:12]}"
    case_id = f"review_case_{uuid4().hex[:12]}" if status != "passed" else None
    reason_codes = _reason_codes(report, quality_gate)
    evidence_refs = _evidence_refs(report, source_ref)
    score = ContentQualityScore(
        score_id=score_id,
        rubric_version="content_quality_rubric_v1",
        overall_score=float(report.scores.overall_score),
        dimension_scores={
            "readability": float(report.scores.readability),
            "scene_density": float(report.scores.scene_density),
            "character_fidelity": float(report.scores.character_fidelity),
            "causal_continuity": float(report.scores.causal_continuity),
            "pacing": float(report.scores.pacing),
            "choice_distinctness": float(report.scores.choice_distinctness),
            "hook_quality": float(report.scores.hook_quality),
            "monetize_ready": float(report.scores.monetize_ready),
        },
        veto=status == "blocked",
        reason_codes=reason_codes,
        evidence_refs=evidence_refs,
        metadata={
            "source_surface": source_surface,
            "status": status,
            "hard_constraint_result": hard_constraint_result,
        },
    )
    decision = GuardrailDecision(
        trace_id=trace_id,
        status=status,
        scenario_id=scenario_id,
        risk_tier=policy.risk_tier,
        rule_hits=_rule_hits(quality_bundle),
        scores_ref=score_id,
        grounding_result=grounding_check.to_dict(),
        review_required=status != "passed",
        review_case_id=case_id,
        metadata={
            "policy_id": policy.policy_id,
            "policy_mode": policy.mode,
            "hard_constraint_result": hard_constraint_result,
        },
    )
    review_case = None
    if case_id is not None:
        review_case = ReviewCase(
            case_id=case_id,
            case_type=SCENARIO_CASE_TYPES.get(scenario_id, "content_quality"),
            status="open",
            owner_id=None,
            source_ref=dict(source_ref or {}),
            reason_codes=reason_codes,
            evidence_refs=evidence_refs,
            metadata={"trace_id": trace_id, "source_surface": source_surface, "world_version_id": world_version_id, "session_id": session_id},
        )
    event = QualityEvent(
        event_id=f"quality_event_{uuid4().hex[:12]}",
        trace_id=trace_id,
        event_type="guardrail_decision",
        source_surface=source_surface,
        source_ref=dict(source_ref or {}),
        payload={
            "status": status,
            "scenario_id": scenario_id,
            "risk_tier": policy.risk_tier,
            "policy_id": policy.policy_id,
            "scores_ref": score_id,
            "review_case_id": case_id,
            "rule_hits": decision.rule_hits,
            "grounding_result": decision.grounding_result,
            "hard_constraint_result": hard_constraint_result,
        },
        created_at=_utcnow(),
    )
    return {
        "policy": policy,
        "score": score,
        "decision": decision,
        "review_case": review_case,
        "event": event,
        "grounding_check": grounding_check,
        "trace_id": trace_id,
    }


def persist_guardrail_records(
    repository: Any,
    *,
    quality_bundle: Dict[str, Any],
    scenario_id: str,
    source_surface: str,
    source_ref: Dict[str, Any],
    world_version_id: Optional[str] = None,
    session_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    coverage_context: Optional[Dict[str, Any]] = None,
    state_after: Optional[Any] = None,
    worldpack_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    records = build_guardrail_records(
        quality_bundle=quality_bundle,
        scenario_id=scenario_id,
        source_surface=source_surface,
        source_ref=source_ref,
        world_version_id=world_version_id,
        session_id=session_id,
        chapter_id=chapter_id,
        coverage_context=coverage_context,
        state_after=state_after,
        worldpack_payload=worldpack_payload,
    )
    policy = records["policy"]
    score = records["score"]
    decision = records["decision"]
    review_case = records["review_case"]
    event = records["event"]
    grounding_check = records["grounding_check"]

    saved_policy = repository.save_quality_policy(policy.to_dict())
    saved_grounding_check = repository.save_grounding_check(
        {
            **grounding_check.to_dict(),
            "trace_id": decision.trace_id,
        }
    )
    saved_score = repository.save_content_quality_score(
        {
            **score.to_dict(),
            "trace_id": decision.trace_id,
            "source_surface": source_surface,
            "status": decision.status,
            "world_version_id": world_version_id,
            "session_id": session_id,
            "chapter_id": chapter_id or source_ref.get("chapter_id"),
            "score_payload": {
                **score.to_dict(),
                "policy_id": saved_policy["policy_id"],
                "grounding_check_id": saved_grounding_check["grounding_check_id"],
                "grounding_status": saved_grounding_check["status"],
                "hard_constraint_result": (score.metadata or {}).get("hard_constraint_result", {}),
            },
        }
    )
    saved_case = None
    if review_case is not None:
        saved_case = repository.save_review_case(
            {
                **review_case.to_dict(),
                "trace_id": decision.trace_id,
                "source_surface": source_surface,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "score_id": saved_score["score_id"],
                "case_payload": {
                    **review_case.to_dict(),
                    "policy_id": saved_policy["policy_id"],
                },
            }
        )
    saved_event = repository.save_quality_event(
        {
            **event.to_dict(),
            "status": decision.status,
            "world_version_id": world_version_id,
            "session_id": session_id,
            "payload": {
                **event.payload,
                "policy_id": saved_policy["policy_id"],
                "scores_ref": saved_score["score_id"],
                "review_case_id": saved_case["case_id"] if saved_case else None,
                "grounding_check_id": saved_grounding_check["grounding_check_id"],
                "grounding_status": saved_grounding_check["status"],
                "hard_constraint_result": (event.payload or {}).get("hard_constraint_result", {}),
            },
        }
    )
    return {
        "policy": saved_policy,
        "grounding_check": saved_grounding_check,
        "score": saved_score,
        "decision": {
            **decision.to_dict(),
            "scores_ref": saved_score["score_id"],
            "review_case_id": saved_case["case_id"] if saved_case else None,
            "grounding_result": saved_grounding_check,
        },
        "review_case": saved_case,
        "event": saved_event,
        "trace_id": decision.trace_id,
    }


def record_publish_preflight_quality_event(
    repository: Any,
    *,
    world_id: str,
    world_version_id: str,
    status: str,
    reason_codes: list[str],
    reviewer_id: Optional[str] = None,
) -> Dict[str, Any]:
    policy = get_quality_policy_for_scenario("publish_candidate")
    repository.save_quality_policy(policy.to_dict())
    trace_id = f"quality_trace_{uuid4().hex[:12]}"
    review_case = None
    if status != "passed":
        review_case = repository.save_review_case(
            {
                "case_id": f"review_case_{uuid4().hex[:12]}",
                "trace_id": trace_id,
                "case_type": "publish_quality",
                "status": "open",
                "owner_id": reviewer_id,
                "source_surface": "publish",
                "world_version_id": world_version_id,
                "session_id": None,
                "score_id": None,
                "source_ref": {"kind": "world_version", "world_id": world_id, "world_version_id": world_version_id},
                "reason_codes": reason_codes,
                "evidence_refs": [{"kind": "publish_checklist", "ref_id": world_version_id}],
                "case_payload": {"policy_id": policy.policy_id, "status": status},
            }
        )
    event = repository.save_quality_event(
        {
            "event_id": f"quality_event_{uuid4().hex[:12]}",
            "trace_id": trace_id,
            "event_type": "publish_preflight",
            "source_surface": "publish",
            "status": status,
            "world_version_id": world_version_id,
            "session_id": None,
            "source_ref": {"kind": "world_version", "world_id": world_id, "world_version_id": world_version_id},
            "payload": {
                "scenario_id": "publish_candidate",
                "risk_tier": policy.risk_tier,
                "reason_codes": reason_codes,
                "review_case_id": review_case["case_id"] if review_case else None,
                "policy_id": policy.policy_id,
                "grounding_status": "not_applicable",
            },
        }
    )
    return {
        "trace_id": trace_id,
        "event": event,
        "review_case": review_case,
    }
