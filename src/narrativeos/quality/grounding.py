from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from .config import load_grounding_policies
from .models import GroundingCheck, GroundingDecision


CLAIM_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
RESULT_MARKERS = ("已经", "终于", "决定", "承认", "发现", "知道", "记得", "答应", "失去", "回到", "继续")
RELATION_MARKERS = ("关系", "誓言", "真相", "债", "命", "世界", "记忆")
CONTRADICTION_PATTERNS = (
    (("全部结束", "已经结束", "结束了"), ("仍未结束", "未结束", "尚未结束", "没有结束")),
    (("已经失去", "失去了"), ("仍在", "还在", "没有失去")),
    (("已经答应", "答应了"), ("尚未答应", "没有答应", "未答应")),
)


def _policy_for_scenario(scenario_id: str) -> Dict[str, Any]:
    payload = load_grounding_policies()
    return dict((payload.get("policies") or {}).get(str(scenario_id) or "", {}) or {})


def _split_sentences(text: str, pattern: str) -> List[str]:
    chunks = [segment.strip() for segment in re.split(pattern, str(text or "")) if segment.strip()]
    return chunks


def _claim_candidates(text: str, *, split_pattern: str) -> List[str]:
    sentences = _split_sentences(text, split_pattern)
    claims: List[str] = []
    for sentence in sentences:
        if any(marker in sentence for marker in RESULT_MARKERS) or any(marker in sentence for marker in RELATION_MARKERS):
            parts = [part.strip() for part in re.split(r"(?:但是|然而|可是|却)", sentence) if part.strip()]
            claims.extend(parts or [sentence])
    return claims


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for raw in CLAIM_TOKEN_PATTERN.findall(str(text or "")):
        token = raw.strip()
        if len(token) <= 1:
            continue
        if CJK_PATTERN.search(token):
            if len(token) <= 6:
                tokens.append(token)
            for size in (3, 4):
                if len(token) < size:
                    continue
                tokens.extend(token[index : index + size] for index in range(0, len(token) - size + 1))
        else:
            tokens.append(token)
    return list(dict.fromkeys(tokens))


def _flatten_evidence_values(value: Any, *, limit: int = 120) -> List[str]:
    output: List[str] = []
    if value is None or len(output) >= limit:
        return output
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, dict):
        for item in value.values():
            output.extend(_flatten_evidence_values(item, limit=limit - len(output)))
            if len(output) >= limit:
                break
        return output
    if isinstance(value, (list, tuple, set)):
        for item in value:
            output.extend(_flatten_evidence_values(item, limit=limit - len(output)))
            if len(output) >= limit:
                break
    return output


def _evidence_pack_tokens(
    *,
    body: str,
    coverage_context: Optional[Dict[str, Any]] = None,
    state_after: Optional[Any] = None,
    worldpack_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    coverage_context = dict(coverage_context or {})
    scene_beats = list(coverage_context.get("scene_beats") or [])
    selected_event_ids = [str(item) for item in list(coverage_context.get("selected_event_ids") or []) if str(item)]
    chapter_task = dict(coverage_context.get("chapter_task") or {})
    world_facts = list(getattr(state_after, "world_facts", []) or [])
    timeline = list(getattr(state_after, "timeline", []) or [])
    canonical_memory = list(getattr(state_after, "canonical_memory", []) or [])
    active_arc_memory = list(getattr(state_after, "active_arc_memory", []) or [])
    rolling_recap = list(getattr(state_after, "rolling_recap", []) or [])
    archive_memory = list(getattr(state_after, "archive_memory", []) or [])
    open_promises = [getattr(item, "description", "") for item in list(getattr(state_after, "open_promises", []) or [])]
    world_bible = dict((worldpack_payload or {}).get("world_bible") or {})

    evidence_sources = {
        "selected_event_ids": " ".join(selected_event_ids),
        "scene_beats": " ".join(
            " ".join(
                str(value)
                for value in [
                    dict(beat.get("event") or {}).get("title"),
                    dict(beat.get("event") or {}).get("summary"),
                    dict(beat.get("event") or {}).get("scene_function"),
                    dict(beat.get("event") or {}).get("location"),
                ]
                if str(value or "").strip()
            )
            for beat in scene_beats
        ),
        "chapter_task": " ".join(str(value) for value in chapter_task.values() if isinstance(value, (str, int, float))),
        "world_facts": " ".join(str(item) for item in world_facts if str(item)),
        "timeline": " ".join(str(item) for item in timeline if str(item)),
        "longform_memory": " ".join(
            _flatten_evidence_values(canonical_memory)
            + _flatten_evidence_values(active_arc_memory)
            + _flatten_evidence_values(rolling_recap)
            + _flatten_evidence_values(archive_memory)
        ),
        "open_promises": " ".join(str(item) for item in open_promises if str(item)),
        "world_bible": " ".join(str(value) for value in world_bible.values() if isinstance(value, (str, int, float))),
    }
    return evidence_sources


def _supported_token_hits(claim: str, evidence_sources: Dict[str, str]) -> tuple[int, List[Dict[str, Any]]]:
    tokens = _tokenize(claim)
    refs: List[Dict[str, Any]] = []
    hit_count = 0
    for token in tokens:
        for kind, source_text in evidence_sources.items():
            if token and token in source_text:
                hit_count += 1
                refs.append({"kind": kind, "ref_id": token, "preview": token})
                break
    return hit_count, refs


def _contradicts_evidence(claim: str, evidence_sources: Dict[str, str]) -> bool:
    evidence_text = " ".join(str(item or "") for item in evidence_sources.values())
    for claim_markers, evidence_markers in CONTRADICTION_PATTERNS:
        if any(marker in claim for marker in claim_markers) and any(marker in evidence_text for marker in evidence_markers):
            return True
    return False


def build_grounding_decision(
    *,
    scenario_id: str,
    text: str,
    coverage_context: Optional[Dict[str, Any]] = None,
    state_after: Optional[Any] = None,
    worldpack_payload: Optional[Dict[str, Any]] = None,
) -> GroundingDecision:
    policy = _policy_for_scenario(scenario_id)
    if not policy:
        return GroundingDecision(
            status="not_applicable",
            confidence=0.0,
            evidence_refs=[],
            unsupported_claims=[],
            reason_codes=[],
            summary="no_grounding_policy",
        )
    split_pattern = str(policy.get("sentence_split_pattern") or r"[。！？!?]")
    min_supported_token_hits = int(policy.get("min_supported_token_hits", 2) or 2)
    weak_unsupported_claim_max = int(policy.get("weak_unsupported_claim_max", 1) or 1)
    pass_confidence = float(policy.get("min_confidence_for_pass", 0.7) or 0.7)
    default_weak_confidence = 0.15 if str(scenario_id or "") == "reader_continue" else 0.4
    weak_confidence = float(policy.get("min_confidence_for_weak", default_weak_confidence) or default_weak_confidence)

    claims = _claim_candidates(text, split_pattern=split_pattern)
    if not claims:
        return GroundingDecision(
            status="not_applicable",
            confidence=0.0,
            evidence_refs=[],
            unsupported_claims=[],
            reason_codes=[],
            summary="no_grounding_claims_detected",
        )

    evidence_sources = _evidence_pack_tokens(
        body=text,
        coverage_context=coverage_context,
        state_after=state_after,
        worldpack_payload=worldpack_payload,
    )
    unsupported_claims: List[str] = []
    evidence_refs: List[Dict[str, Any]] = []
    supported_claims = 0
    for claim in claims:
        hit_count, refs = _supported_token_hits(claim, evidence_sources)
        evidence_refs.extend(refs)
        if _contradicts_evidence(claim, evidence_sources):
            unsupported_claims.append(claim)
        elif hit_count >= min_supported_token_hits:
            supported_claims += 1
        else:
            unsupported_claims.append(claim)

    confidence = round(supported_claims / float(max(1, len(claims))), 3)
    reason_codes: List[str] = []
    if not unsupported_claims and confidence >= pass_confidence:
        status = "passed"
    elif len(unsupported_claims) <= weak_unsupported_claim_max or confidence >= weak_confidence:
        status = "weak"
        reason_codes.append("grounding_missing_support")
    else:
        status = "failed"
        reason_codes.append("grounding_missing_support")

    if "但是" in text and unsupported_claims:
        if "grounding_contradiction" not in reason_codes:
            reason_codes.append("grounding_contradiction")

    summary = f"{status} · claims={len(claims)} · unsupported={len(unsupported_claims)} · confidence={confidence}"
    unique_refs = []
    seen = set()
    for ref in evidence_refs:
        key = (ref.get("kind"), ref.get("ref_id"))
        if key in seen:
            continue
        seen.add(key)
        unique_refs.append(ref)
    return GroundingDecision(
        status=status,
        confidence=confidence,
        evidence_refs=unique_refs[:12],
        unsupported_claims=unsupported_claims[:6],
        reason_codes=reason_codes,
        summary=summary,
    )


def build_grounding_check(
    *,
    scenario_id: str,
    text: str,
    source_surface: str,
    trace_id: Optional[str] = None,
    world_version_id: Optional[str] = None,
    session_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    coverage_context: Optional[Dict[str, Any]] = None,
    state_after: Optional[Any] = None,
    worldpack_payload: Optional[Dict[str, Any]] = None,
) -> GroundingCheck:
    decision = build_grounding_decision(
        scenario_id=scenario_id,
        text=text,
        coverage_context=coverage_context,
        state_after=state_after,
        worldpack_payload=worldpack_payload,
    )
    return GroundingCheck(
        grounding_check_id=f"grounding_check_{uuid4().hex[:12]}",
        trace_id=trace_id,
        status=decision.status,
        confidence=decision.confidence,
        evidence_refs=decision.evidence_refs,
        unsupported_claims=decision.unsupported_claims,
        reason_codes=decision.reason_codes,
        summary=decision.summary,
        source_surface=source_surface,
        world_version_id=world_version_id,
        session_id=session_id,
        chapter_id=chapter_id,
    )
