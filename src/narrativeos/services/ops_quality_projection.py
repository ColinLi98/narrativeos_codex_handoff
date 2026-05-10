from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


class OpsQualityProjectionService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _safe_world_version_author(self, world_version_id: Optional[str]) -> Optional[str]:
        value = str(world_version_id or "").strip()
        if not value:
            return None
        try:
            return self.repository.get_world_version(value).author_id
        except KeyError:
            return None

    def _safe_world_id(self, world_version_id: Optional[str]) -> Optional[str]:
        value = str(world_version_id or "").strip()
        if not value:
            return None
        try:
            return self.repository.get_world_version(value).world_id
        except KeyError:
            return None

    def _safe_session_reader(self, session_id: Optional[str]) -> Optional[str]:
        value = str(session_id or "").strip()
        if not value:
            return None
        try:
            session = self.repository.get_session(value)
        except KeyError:
            return None
        return str(session.player_profile.get("reader_id") or "").strip() or None

    def infer_account_id(
        self,
        *,
        source_ref: Optional[Dict[str, Any]] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        source_ref = dict(source_ref or {})
        candidates = [
            str(source_ref.get("account_id") or "").strip(),
            self._safe_session_reader(session_id),
            self._safe_world_version_author(world_version_id),
        ]
        for item in candidates:
            if item:
                return item
        return None

    def _score_lookup(self, *, trace_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not str(trace_id or "").strip():
            return None
        scores = self.repository.list_content_quality_scores(trace_id=str(trace_id), limit=1)
        return scores[0] if scores else None

    def _review_case_lookup(self, *, trace_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not str(trace_id or "").strip():
            return None
        cases = self.repository.list_review_cases(trace_id=str(trace_id), limit=1)
        return cases[0] if cases else None

    def _grounding_check_lookup(self, *, trace_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not str(trace_id or "").strip():
            return None
        checks = self.repository.list_grounding_checks(trace_id=str(trace_id), limit=1)
        return checks[0] if checks else None

    def list_projected_quality_events(
        self,
        *,
        account_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source_surface: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        events = self.repository.list_quality_events(
            world_version_id=world_version_id,
            session_id=session_id,
            source_surface=source_surface,
            status=status,
            limit=max(limit * 3, limit),
        )
        projected: List[Dict[str, Any]] = []
        for event in events:
            inferred_account_id = self.infer_account_id(
                source_ref=event.get("source_ref"),
                world_version_id=event.get("world_version_id"),
                session_id=event.get("session_id"),
            )
            if account_id and inferred_account_id != account_id:
                continue
            score = self._score_lookup(trace_id=event.get("trace_id"))
            review_case = self._review_case_lookup(trace_id=event.get("trace_id"))
            grounding_check = self._grounding_check_lookup(trace_id=event.get("trace_id"))
            reason_codes = []
            for source in [
                list((grounding_check or {}).get("reason_codes") or []),
                list((score or {}).get("reason_codes") or []),
                list((review_case or {}).get("reason_codes") or []),
                list(dict(event.get("payload") or {}).get("reason_codes") or []),
            ]:
                for item in source:
                    normalized = str(item or "").strip()
                    if normalized and normalized not in reason_codes:
                        reason_codes.append(normalized)
            projected.append(
                {
                    **event,
                    "account_id": inferred_account_id,
                    "world_id": self._safe_world_id(event.get("world_version_id")),
                    "reason_codes": reason_codes,
                    "overall_score": (score or {}).get("overall_score"),
                    "veto": (score or {}).get("veto"),
                    "grounding_status": (grounding_check or {}).get("status"),
                    "review_case_id": (review_case or {}).get("case_id"),
                    "review_case_status": (review_case or {}).get("status"),
                    "review_case_owner_id": (review_case or {}).get("owner_id"),
                }
            )
            if len(projected) >= limit:
                break
        return projected

    def quality_summary(
        self,
        *,
        account_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source_surface: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        events = self.list_projected_quality_events(
            account_id=account_id,
            world_version_id=world_version_id,
            session_id=session_id,
            source_surface=source_surface,
            status=status,
            limit=limit,
        )
        cases = self.repository.list_review_cases(
            world_version_id=world_version_id,
            session_id=session_id,
            trace_id=None,
            limit=max(limit * 3, limit),
        )
        projected_cases = []
        for case in cases:
            inferred_account_id = self.infer_account_id(
                source_ref=case.get("source_ref"),
                world_version_id=case.get("world_version_id"),
                session_id=case.get("session_id"),
            )
            if account_id and inferred_account_id != account_id:
                continue
            if source_surface and str(case.get("source_surface") or "") != str(source_surface):
                continue
            if status and str(case.get("status") or "") != str(status):
                continue
            projected_cases.append({**case, "account_id": inferred_account_id})
            if len(projected_cases) >= limit:
                break

        by_status = Counter(str(item.get("status") or "unknown") for item in events)
        by_surface = Counter(str(item.get("source_surface") or "unknown") for item in events)
        grounding_checks = self.repository.list_grounding_checks(
            world_version_id=world_version_id,
            session_id=session_id,
            limit=max(limit * 3, limit),
        )
        top_reason_codes = Counter(
            code
            for item in events
            for code in list(item.get("reason_codes") or [])
            if str(code or "").strip()
        )
        latest_trace = events[0].get("trace_id") if events else None
        feedback_items = self.list_projected_quality_feedback_items(
            account_id=account_id,
            world_version_id=world_version_id,
            session_id=session_id,
            limit=limit,
        )
        top_feedback_types = Counter(
            str(item.get("feedback_type") or "unknown")
            for item in feedback_items
        )
        explicit_feedback = [item for item in feedback_items if str(item.get("feedback_type") or "") == "explicit_user_feedback"]
        implicit_feedback = [item for item in feedback_items if str(item.get("feedback_type") or "") != "explicit_user_feedback"]
        explicit_reason_codes = Counter(
            str(dict(item.get("payload") or {}).get("reason_code") or "")
            for item in explicit_feedback
            if str(dict(item.get("payload") or {}).get("reason_code") or "").strip()
        )
        return {
            "generated_at": self._utcnow(),
            "filters": {
                "account_id": account_id,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "source_surface": source_surface,
                "status": status,
                "limit": limit,
            },
            "summary": {
                "event_count": len(events),
                "review_case_count": len(projected_cases),
                "open_review_case_count": sum(1 for item in projected_cases if item.get("status") in {"open", "in_review"}),
                "blocked_event_count": sum(1 for item in events if item.get("status") == "blocked"),
                "review_required_event_count": sum(1 for item in events if item.get("status") == "review_required"),
                "grounding_check_count": len(grounding_checks),
                "feedback_item_count": len(feedback_items),
                "retry_signal_count": sum(1 for item in feedback_items if str(item.get("signal") or "") == "retry"),
                "by_status": dict(by_status),
                "by_source_surface": dict(by_surface),
                "top_reason_codes": [
                    {"reason_code": key, "count": count}
                    for key, count in top_reason_codes.most_common(5)
                ],
                "top_feedback_types": [
                    {"feedback_type": key, "count": count}
                    for key, count in top_feedback_types.most_common(5)
                ],
                "latest_trace_id": latest_trace,
            },
            "groundedness_summary": {
                "pass_rate": round(sum(1 for item in grounding_checks if str(item.get("status") or "") == "passed") / float(max(1, len(grounding_checks))), 3) if grounding_checks else 0.0,
                "weak_count": sum(1 for item in grounding_checks if str(item.get("status") or "") == "weak"),
                "failed_count": sum(1 for item in grounding_checks if str(item.get("status") or "") == "failed"),
                "unsupported_claim_count": sum(len(item.get("unsupported_claims") or []) for item in grounding_checks),
            },
            "feedback_summary": {
                "thumbs_up_count": sum(1 for item in explicit_feedback if str(item.get("signal") or "") == "explicit_positive"),
                "thumbs_down_count": sum(1 for item in explicit_feedback if str(item.get("signal") or "") == "explicit_negative"),
                "explicit_vs_implicit": {
                    "explicit": len(explicit_feedback),
                    "implicit": len(implicit_feedback),
                },
                "top_reason_codes": [
                    {"reason_code": key, "count": count}
                    for key, count in explicit_reason_codes.most_common(5)
                ],
            },
            "review_pressure": {
                "new_review_cases": sum(1 for item in projected_cases if item.get("status") == "open"),
                "unresolved_review_cases": sum(1 for item in projected_cases if item.get("status") in {"open", "in_review"}),
                "top_review_reasons": [
                    {"reason_code": key, "count": count}
                    for key, count in Counter(
                        code
                        for item in projected_cases
                        for code in list(item.get("reason_codes") or [])
                        if str(code or "").strip()
                    ).most_common(5)
                ],
            },
            "quality_trend": {
                "score_trend": [
                    {"trace_id": item.get("trace_id"), "overall_score": item.get("overall_score"), "created_at": item.get("created_at")}
                    for item in events[:12]
                ],
                "veto_trend": [
                    {"trace_id": item.get("trace_id"), "veto": bool(item.get("veto")), "created_at": item.get("created_at")}
                    for item in events[:12]
                ],
                "guard_failed_trend": [
                    {"trace_id": item.get("trace_id"), "status": item.get("status"), "created_at": item.get("created_at")}
                    for item in events[:12]
                ],
            },
            "events": events,
            "review_cases": projected_cases,
            "feedback_items": feedback_items[:10],
        }

    def list_projected_quality_feedback_items(
        self,
        *,
        account_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        items = self.repository.list_quality_feedback_items(
            account_id=account_id,
            world_version_id=world_version_id,
            session_id=session_id,
            trace_id=trace_id,
            limit=limit,
        )
        return [
            {
                **item,
                "account_id": item.get("account_id") or self.infer_account_id(
                    source_ref=item.get("source_ref"),
                    world_version_id=item.get("world_version_id"),
                    session_id=item.get("session_id"),
                ),
                "world_id": self._safe_world_id(item.get("world_version_id")),
            }
            for item in items
        ]

    def quality_trace_detail(self, trace_id: str) -> Dict[str, Any]:
        trace = str(trace_id or "").strip()
        if not trace:
            raise KeyError("unknown_quality_trace:")
        events = self.repository.list_quality_events(trace_id=trace, limit=10)
        if not events:
            raise KeyError("unknown_quality_trace:%s" % trace)
        event = events[0]
        score = self._score_lookup(trace_id=trace)
        review_case = self._review_case_lookup(trace_id=trace)
        grounding_check = self._grounding_check_lookup(trace_id=trace)
        account_id = self.infer_account_id(
            source_ref=event.get("source_ref"),
            world_version_id=event.get("world_version_id"),
            session_id=event.get("session_id"),
        )
        feedback_items = self.list_projected_quality_feedback_items(trace_id=trace, limit=20)
        feedback_types = Counter(str(item.get("feedback_type") or "unknown") for item in feedback_items)
        explicit_feedback = [item for item in feedback_items if str(item.get("feedback_type") or "") == "explicit_user_feedback"]
        implicit_feedback = [item for item in feedback_items if str(item.get("feedback_type") or "") != "explicit_user_feedback"]
        return {
            "generated_at": self._utcnow(),
            "trace_id": trace,
            "event": {
                **event,
                "account_id": account_id,
                "world_id": self._safe_world_id(event.get("world_version_id")),
            },
            "score": score,
            "grounding_check": grounding_check,
            "review_case": review_case,
            "linked_context": {
                "account_id": account_id,
                "world_id": self._safe_world_id(event.get("world_version_id")),
                "world_version_id": event.get("world_version_id"),
                "session_id": event.get("session_id"),
            },
            "grounding_summary": {
                "status": (grounding_check or {}).get("status"),
                "confidence": (grounding_check or {}).get("confidence"),
                "unsupported_claim_count": len((grounding_check or {}).get("unsupported_claims") or []),
                "reason_codes": list((grounding_check or {}).get("reason_codes") or []),
            },
            "feedback_summary": {
                "feedback_item_count": len(feedback_items),
                "retry_signal_count": sum(1 for item in feedback_items if str(item.get("signal") or "") == "retry"),
                "by_feedback_type": dict(feedback_types),
            },
            "explicit_feedback": explicit_feedback,
            "implicit_feedback_summary": {
                "count": len(implicit_feedback),
                "by_feedback_type": dict(Counter(str(item.get("feedback_type") or "unknown") for item in implicit_feedback)),
            },
            "feedback_timeline": feedback_items,
            "feedback_items": feedback_items,
        }

    def _case_severity(self, *, review_case: Dict[str, Any], quality_event: Optional[Dict[str, Any]], score: Optional[Dict[str, Any]]) -> str:
        if str((quality_event or {}).get("status") or "") == "blocked" or bool((score or {}).get("veto")):
            return "high"
        if str((quality_event or {}).get("status") or "") == "review_required":
            return "medium"
        return "medium"

    def _priority(self, *, severity: str, status: str) -> int:
        base = {"high": 10, "medium": 20, "low": 30, "info": 40}.get(str(severity or "medium"), 20)
        if status == "new":
            return base
        if status == "in_review":
            return base + 5
        if status in {"resolved", "dismissed"}:
            return base + 90
        return base + 10

    def build_quality_review_case_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for case in self.repository.list_review_cases(limit=500):
            trace_id = str(case.get("trace_id") or "")
            event_rows = self.repository.list_quality_events(trace_id=trace_id, limit=1) if trace_id else []
            event = event_rows[0] if event_rows else None
            score = self._score_lookup(trace_id=trace_id)
            account_id = self.infer_account_id(
                source_ref=case.get("source_ref"),
                world_version_id=case.get("world_version_id"),
                session_id=case.get("session_id"),
            )
            world_id = self._safe_world_id(case.get("world_version_id"))
            source_status = {
                "open": "new",
                "in_review": "in_review",
                "resolved": "resolved",
                "dismissed": "dismissed",
            }.get(str(case.get("status") or "open"), "new")
            severity = self._case_severity(review_case=case, quality_event=event, score=score)
            reason_codes = list(case.get("reason_codes") or []) or list((score or {}).get("reason_codes") or [])
            item = {
                "review_item_id": f"ops_review::quality_review_case::{case['case_id']}",
                "source_type": "quality_review_case",
                "source_id": str(case["case_id"]),
                "queue": "runtime",
                "status": source_status,
                "severity": severity,
                "priority": self._priority(severity=severity, status=source_status),
                "owner_id": case.get("owner_id"),
                "reviewer_id": None,
                "account_id": account_id,
                "world_id": world_id,
                "world_version_id": case.get("world_version_id"),
                "headline": f"{str((event or {}).get('source_surface') or case.get('source_surface') or 'quality')} · 质量审阅",
                "summary": f"status {str((event or {}).get('status') or '-')} · reasons {' / '.join(reason_codes[:3]) or '-'}",
                "recommended_action": "open_investigation" if str((event or {}).get("status") or "") == "blocked" else "review_quality_case",
                "due_at": None,
                "sla_bucket": "backlog" if source_status not in {"resolved", "dismissed"} else "closed",
                "allowed_actions": ["assign_to_me", "mark_in_review", "resolve", "dismiss", "open_account_workspace", "open_release_workspace", "open_investigation"],
                "linked_entities": [
                    item
                    for item in [
                        {"kind": "account", "id": account_id, "label": account_id} if account_id else None,
                        {"kind": "world", "id": world_id, "label": world_id} if world_id else None,
                        {"kind": "world_version", "id": case.get("world_version_id"), "label": case.get("world_version_id")} if case.get("world_version_id") else None,
                        {"kind": "session", "id": case.get("session_id"), "label": case.get("session_id")} if case.get("session_id") else None,
                        {"kind": "trace", "id": trace_id, "label": trace_id} if trace_id else None,
                    ]
                    if item
                ],
                "source_updated_at": case.get("updated_at"),
                "source_payload": {
                    "review_case": case,
                    "quality_event": event or {},
                    "content_quality_score": score or {},
                    "trace_summary": {
                        "trace_id": trace_id,
                        "source_surface": (event or {}).get("source_surface") or case.get("source_surface"),
                        "status": (event or {}).get("status"),
                        "reason_codes": reason_codes,
                        "overall_score": (score or {}).get("overall_score"),
                        "veto": (score or {}).get("veto"),
                    },
                },
            }
            items.append(item)
        items.sort(
            key=lambda item: (
                int(item.get("priority", 100)),
                SEVERITY_ORDER.get(str(item.get("severity") or "medium"), 9),
                str(item.get("source_updated_at") or ""),
            )
        )
        return items
