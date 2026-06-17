from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


POLICY_MODES = {"disabled", "observe", "shadow", "enforce"}
RULE_TYPES = {"validator", "evaluator", "grounding", "review_routing"}
SEVERITY_LEVELS = {"low", "medium", "high", "critical"}
GUARDRAIL_STATUSES = {"passed", "blocked", "review_required"}
REVIEW_CASE_STATUSES = {"open", "in_review", "resolved", "dismissed"}
REVIEW_CASE_TYPES = {"content_quality", "runtime_quality", "publish_quality", "campaign_activation"}
FEEDBACK_SIGNALS = {"retry", "negative_proxy", "positive_proxy", "payment_recovery"}
GROUNDING_STATUSES = {"passed", "weak", "failed", "not_applicable"}


def _validate_enum(value: str, *, name: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError("%s_invalid:%s" % (name, normalized or ""))
    return normalized


def _deepcopy(instance: Any) -> Dict[str, Any]:
    return asdict(instance)


@dataclass
class QualityPolicy:
    policy_id: str
    version: str
    scenario_id: str
    risk_tier: str
    rule_ids: List[str]
    mode: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.mode = _validate_enum(self.mode, name="quality_policy_mode", allowed=POLICY_MODES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityPolicy":
        payload = dict(data or {})
        return cls(
            policy_id=str(payload.get("policy_id") or ""),
            version=str(payload.get("version") or ""),
            scenario_id=str(payload.get("scenario_id") or ""),
            risk_tier=str(payload.get("risk_tier") or ""),
            rule_ids=[str(item) for item in list(payload.get("rule_ids") or []) if str(item)],
            mode=str(payload.get("mode") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class QualityRule:
    rule_id: str
    rule_type: str
    severity: str
    blocking: bool
    config_ref: str
    reason_code: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rule_type = _validate_enum(self.rule_type, name="quality_rule_type", allowed=RULE_TYPES)
        self.severity = _validate_enum(self.severity, name="quality_rule_severity", allowed=SEVERITY_LEVELS)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityRule":
        payload = dict(data or {})
        return cls(
            rule_id=str(payload.get("rule_id") or ""),
            rule_type=str(payload.get("rule_type") or ""),
            severity=str(payload.get("severity") or ""),
            blocking=bool(payload.get("blocking", False)),
            config_ref=str(payload.get("config_ref") or ""),
            reason_code=str(payload.get("reason_code") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class GuardrailDecision:
    trace_id: str
    status: str
    scenario_id: str
    risk_tier: str
    rule_hits: List[Dict[str, Any]]
    scores_ref: Optional[str] = None
    grounding_result: Dict[str, Any] = field(default_factory=dict)
    review_required: bool = False
    review_case_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="guardrail_status", allowed=GUARDRAIL_STATUSES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuardrailDecision":
        payload = dict(data or {})
        return cls(
            trace_id=str(payload.get("trace_id") or ""),
            status=str(payload.get("status") or ""),
            scenario_id=str(payload.get("scenario_id") or ""),
            risk_tier=str(payload.get("risk_tier") or ""),
            rule_hits=[dict(item or {}) for item in list(payload.get("rule_hits") or [])],
            scores_ref=str(payload.get("scores_ref")) if payload.get("scores_ref") is not None else None,
            grounding_result=dict(payload.get("grounding_result") or {}),
            review_required=bool(payload.get("review_required", False)),
            review_case_id=str(payload.get("review_case_id")) if payload.get("review_case_id") is not None else None,
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class ContentQualityScore:
    score_id: str
    rubric_version: str
    overall_score: float
    dimension_scores: Dict[str, Any]
    veto: bool
    reason_codes: List[str]
    evidence_refs: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentQualityScore":
        payload = dict(data or {})
        return cls(
            score_id=str(payload.get("score_id") or ""),
            rubric_version=str(payload.get("rubric_version") or ""),
            overall_score=float(payload.get("overall_score", 0.0) or 0.0),
            dimension_scores=dict(payload.get("dimension_scores") or {}),
            veto=bool(payload.get("veto", False)),
            reason_codes=[str(item) for item in list(payload.get("reason_codes") or []) if str(item)],
            evidence_refs=[dict(item or {}) for item in list(payload.get("evidence_refs") or [])],
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class ReviewCase:
    case_id: str
    case_type: str
    status: str
    owner_id: Optional[str]
    source_ref: Dict[str, Any]
    reason_codes: List[str]
    evidence_refs: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.case_type = _validate_enum(self.case_type, name="review_case_type", allowed=REVIEW_CASE_TYPES)
        self.status = _validate_enum(self.status, name="review_case_status", allowed=REVIEW_CASE_STATUSES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewCase":
        payload = dict(data or {})
        owner_id = payload.get("owner_id")
        return cls(
            case_id=str(payload.get("case_id") or ""),
            case_type=str(payload.get("case_type") or ""),
            status=str(payload.get("status") or ""),
            owner_id=str(owner_id) if owner_id is not None else None,
            source_ref=dict(payload.get("source_ref") or {}),
            reason_codes=[str(item) for item in list(payload.get("reason_codes") or []) if str(item)],
            evidence_refs=[dict(item or {}) for item in list(payload.get("evidence_refs") or [])],
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class QualityEvent:
    event_id: str
    trace_id: str
    event_type: str
    source_surface: str
    source_ref: Dict[str, Any]
    payload: Dict[str, Any]
    created_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityEvent":
        payload = dict(data or {})
        return cls(
            event_id=str(payload.get("event_id") or ""),
            trace_id=str(payload.get("trace_id") or ""),
            event_type=str(payload.get("event_type") or ""),
            source_surface=str(payload.get("source_surface") or ""),
            source_ref=dict(payload.get("source_ref") or {}),
            payload=dict(payload.get("payload") or {}),
            created_at=str(payload.get("created_at") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class QualityFeedbackItem:
    feedback_item_id: str
    feedback_type: str
    signal: str
    source_surface: str
    source_ref: Dict[str, Any]
    payload: Dict[str, Any]
    created_at: str
    trace_id: Optional[str] = None
    account_id: Optional[str] = None
    world_version_id: Optional[str] = None
    session_id: Optional[str] = None
    chapter_id: Optional[str] = None
    source_event_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.signal = _validate_enum(self.signal, name="quality_feedback_signal", allowed=FEEDBACK_SIGNALS)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityFeedbackItem":
        payload = dict(data or {})
        return cls(
            feedback_item_id=str(payload.get("feedback_item_id") or ""),
            feedback_type=str(payload.get("feedback_type") or ""),
            signal=str(payload.get("signal") or ""),
            source_surface=str(payload.get("source_surface") or ""),
            source_ref=dict(payload.get("source_ref") or {}),
            payload=dict(payload.get("payload") or {}),
            created_at=str(payload.get("created_at") or ""),
            trace_id=str(payload.get("trace_id")) if payload.get("trace_id") is not None else None,
            account_id=str(payload.get("account_id")) if payload.get("account_id") is not None else None,
            world_version_id=str(payload.get("world_version_id")) if payload.get("world_version_id") is not None else None,
            session_id=str(payload.get("session_id")) if payload.get("session_id") is not None else None,
            chapter_id=str(payload.get("chapter_id")) if payload.get("chapter_id") is not None else None,
            source_event_id=str(payload.get("source_event_id")) if payload.get("source_event_id") is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class GroundingEvidenceRef:
    kind: str
    ref_id: str
    preview: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundingEvidenceRef":
        payload = dict(data or {})
        return cls(
            kind=str(payload.get("kind") or ""),
            ref_id=str(payload.get("ref_id") or ""),
            preview=str(payload.get("preview") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class GroundingCheck:
    grounding_check_id: str
    trace_id: Optional[str]
    status: str
    confidence: float
    evidence_refs: List[Dict[str, Any]]
    unsupported_claims: List[str]
    reason_codes: List[str]
    summary: str
    source_surface: str
    world_version_id: Optional[str] = None
    session_id: Optional[str] = None
    chapter_id: Optional[str] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="grounding_status", allowed=GROUNDING_STATUSES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundingCheck":
        payload = dict(data or {})
        return cls(
            grounding_check_id=str(payload.get("grounding_check_id") or ""),
            trace_id=str(payload.get("trace_id")) if payload.get("trace_id") is not None else None,
            status=str(payload.get("status") or ""),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            evidence_refs=[dict(item or {}) for item in list(payload.get("evidence_refs") or [])],
            unsupported_claims=[str(item) for item in list(payload.get("unsupported_claims") or []) if str(item)],
            reason_codes=[str(item) for item in list(payload.get("reason_codes") or []) if str(item)],
            summary=str(payload.get("summary") or ""),
            source_surface=str(payload.get("source_surface") or ""),
            world_version_id=str(payload.get("world_version_id")) if payload.get("world_version_id") is not None else None,
            session_id=str(payload.get("session_id")) if payload.get("session_id") is not None else None,
            chapter_id=str(payload.get("chapter_id")) if payload.get("chapter_id") is not None else None,
            created_at=str(payload.get("created_at") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)


@dataclass
class GroundingDecision:
    status: str
    confidence: float
    evidence_refs: List[Dict[str, Any]]
    unsupported_claims: List[str]
    reason_codes: List[str]
    summary: str

    def __post_init__(self) -> None:
        self.status = _validate_enum(self.status, name="grounding_status", allowed=GROUNDING_STATUSES)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundingDecision":
        payload = dict(data or {})
        return cls(
            status=str(payload.get("status") or ""),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            evidence_refs=[dict(item or {}) for item in list(payload.get("evidence_refs") or [])],
            unsupported_claims=[str(item) for item in list(payload.get("unsupported_claims") or []) if str(item)],
            reason_codes=[str(item) for item in list(payload.get("reason_codes") or []) if str(item)],
            summary=str(payload.get("summary") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return _deepcopy(self)
