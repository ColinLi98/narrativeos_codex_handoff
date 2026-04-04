from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from ..models import EvaluationReport
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..schemas import validate_payload


PHASE4_EVENT_NAMES = [
    "session_created",
    "continue_story",
    "chapter_rendered",
    "payment_required",
    "credits_consumed",
    "entitlement_granted",
    "publish_blocked",
    "rollback_performed",
]
ABANDON_WINDOW_HOURS = 24


class TrainingSignalService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _selected_versions(self, *, world_id: Optional[str], world_version_id: Optional[str]) -> List[Dict[str, Any]]:
        if world_version_id:
            version = self.repository.get_world_version(world_version_id)
            return [
                {
                    "world_id": version.world_id,
                    "world_version_id": version.world_version_id,
                    "status": version.status,
                    "updated_at": next(
                        (item["updated_at"] for item in self.repository.list_world_versions(world_id=version.world_id) if item["world_version_id"] == version.world_version_id),
                        None,
                    ),
                }
            ]
        if world_id:
            return self.repository.list_world_versions(world_id=world_id)
        versions: List[Dict[str, Any]] = []
        for world in self.repository.list_worlds():
            versions.extend(self.repository.list_world_versions(world_id=world["world_id"]))
        return versions

    def _parse_note_payload(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _normalize_issue_codes(self, values: Sequence[Any]) -> List[str]:
        normalized = {
            str(value).strip().upper()
            for value in values or []
            if str(value).strip()
        }
        return sorted(normalized)

    def _normalize_source_ref(self, payload: Dict[str, Any], *, chapter_id: str) -> Dict[str, Any]:
        source_ref = dict(payload.get("source_ref") or {})
        return {
            "kind": str(source_ref.get("kind") or "manual_entry"),
            "chapter_id": str(source_ref.get("chapter_id") or chapter_id),
        }

    def _review_sample_ingestion_key(self, sample: Dict[str, Any]) -> str:
        stable_fields = [
            str(sample.get("world_version_id") or ""),
            str(sample.get("chapter_id") or ""),
            str(sample.get("reviewer_id") or ""),
            str(sample.get("source") or ""),
            str(sample.get("revision_id") or ""),
            str(sample.get("session_id") or ""),
            str((sample.get("source_ref") or {}).get("kind") or ""),
        ]
        return hashlib.sha256("|".join(stable_fields).encode("utf-8")).hexdigest()[:16]

    def _preference_sample_ingestion_key(self, sample: Dict[str, Any]) -> str:
        stable_fields = [
            str(sample.get("world_version_id") or ""),
            str(sample.get("reviewer_id") or ""),
            str(sample.get("left_revision_id") or ""),
            str(sample.get("right_revision_id") or ""),
            str(sample.get("preferred_revision_id") or ""),
            str(sample.get("source") or ""),
        ]
        return hashlib.sha256("|".join(stable_fields).encode("utf-8")).hexdigest()[:16]

    def _ranking_sample_ingestion_key(self, sample: Dict[str, Any]) -> str:
        stable_fields = [
            str(sample.get("world_version_id") or ""),
            str(sample.get("reviewer_id") or ""),
            ",".join(str(item) for item in sample.get("ranked_revision_ids") or []),
            str(sample.get("source") or ""),
        ]
        return hashlib.sha256("|".join(stable_fields).encode("utf-8")).hexdigest()[:16]

    def _stable_review_sample_id(self, sample: Dict[str, Any]) -> str:
        provided = payload_id = sample.get("sample_id")
        if provided:
            return str(payload_id)
        if sample.get("source") == "evaluation_report_auto":
            return "sample_%s" % sample["chapter_id"]
        return "sample_%s" % self._review_sample_ingestion_key(sample)

    def _stable_preference_sample_id(self, sample: Dict[str, Any]) -> str:
        provided = sample.get("preference_id")
        if provided:
            return str(provided)
        return "pref_%s" % self._preference_sample_ingestion_key(sample)

    def _stable_ranking_sample_id(self, sample: Dict[str, Any]) -> str:
        provided = sample.get("ranking_id")
        if provided:
            return str(provided)
        return "rank_%s" % self._ranking_sample_ingestion_key(sample)

    def _world_version_context(self, world_version_id: str) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        return {
            "world_id": version.world_id,
            "world_version_id": version.world_version_id,
            "metadata": dict((version.worldpack_json or {}).get("metadata", {})),
        }

    def _known_revision_ids(self, world_version_id: str) -> Set[str]:
        metadata = self._world_version_context(world_version_id)["metadata"]
        return {
            str(item.get("revision_id"))
            for item in metadata.get("revision_history", [])
            if item.get("revision_id")
        }

    def _validate_revision_ids(self, world_version_id: str, revision_ids: Sequence[Any]) -> None:
        known = self._known_revision_ids(world_version_id)
        normalized = [str(item) for item in revision_ids if str(item).strip()]
        if not normalized:
            raise ValueError("revision_ids_required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate_revision_ids")
        for revision_id in normalized:
            if revision_id not in known:
                raise ValueError("unknown_revision_id")

    def _validate_review_sample_refs(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        try:
            version_context = self._world_version_context(sample["world_version_id"])
        except KeyError:
            world_version_id = str(sample["world_version_id"])
            world_id = str(sample["world_id"])
            if not world_version_id.startswith(f"{world_id}@"):
                raise KeyError("unknown_world_version:%s" % world_version_id)
            version_context = {
                "world_id": world_id,
                "world_version_id": world_version_id,
                "metadata": {},
            }
            reference_status = "fallback_world_version_pattern"
        else:
            if version_context["world_id"] != sample["world_id"]:
                raise ValueError("world_id_world_version_mismatch")
            reference_status = "validated"
        session_context: Dict[str, Any] = {}
        if sample.get("session_id"):
            session = self.repository.get_session(str(sample["session_id"]))
            session_version_id = str(session.metadata.get("world_version_id") or "")
            if session.world_id != sample["world_id"] or (session_version_id and session_version_id != sample["world_version_id"]):
                raise ValueError("session_world_version_mismatch")
            session_context = {
                "session_reader_id": session.metadata.get("reader_id") or session.player_profile.get("reader_id"),
                "session_world_id": session.world_id,
            }
        if sample.get("revision_id"):
            if str(sample["revision_id"]) not in self._known_revision_ids(sample["world_version_id"]):
                raise ValueError("unknown_revision_id")
        return {
            "reference_status": reference_status,
            **session_context,
        }

    def _validate_preference_sample_refs(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        reference_context = self._validate_review_sample_refs(
            {
                "world_id": sample["world_id"],
                "world_version_id": sample["world_version_id"],
                "session_id": sample.get("session_id"),
                "revision_id": None,
            }
        )
        self._validate_revision_ids(
            sample["world_version_id"],
            [sample["left_revision_id"], sample["right_revision_id"]],
        )
        if sample["preferred_revision_id"] not in {sample["left_revision_id"], sample["right_revision_id"]}:
            raise ValueError("preferred_revision_id_not_in_pair")
        return reference_context

    def _validate_ranking_sample_refs(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        reference_context = self._validate_review_sample_refs(
            {
                "world_id": sample["world_id"],
                "world_version_id": sample["world_version_id"],
                "session_id": sample.get("session_id"),
                "revision_id": None,
            }
        )
        ranked_revision_ids = [str(item) for item in sample.get("ranked_revision_ids") or [] if str(item).strip()]
        if len(ranked_revision_ids) < 2:
            raise ValueError("ranking_requires_two_or_more_revisions")
        self._validate_revision_ids(sample["world_version_id"], ranked_revision_ids)
        return reference_context

    def _build_cursor(self, timestamp: Optional[str], identifier: Optional[str]) -> Optional[str]:
        if not timestamp or not identifier:
            return None
        return f"{timestamp}|{identifier}"

    def _split_for(self, world_version_id: str, stable_id: str) -> str:
        digest = hashlib.sha256(f"{world_version_id}:{stable_id}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        if bucket < 80:
            return "train"
        if bucket < 90:
            return "val"
        return "test"

    def _parse_cursor(self, cursor: Optional[str]) -> Optional[Tuple[datetime, str]]:
        if not cursor or "|" not in cursor:
            return None
        timestamp, identifier = cursor.split("|", 1)
        return self._parse_timestamp(timestamp), identifier

    def _apply_incremental_window(
        self,
        items: Sequence[Dict[str, Any]],
        *,
        timestamp_key: str,
        identifier_key: str,
        since: Optional[str],
        cursor: Optional[str],
        limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        since_dt = self._parse_timestamp(since) if since else None
        cursor_value = self._parse_cursor(cursor)
        filtered: List[Dict[str, Any]] = []
        for item in items:
            item_dt = self._parse_timestamp(item.get(timestamp_key))
            item_identifier = str(item.get(identifier_key) or "")
            if since_dt and item_dt < since_dt:
                continue
            if cursor_value:
                cursor_dt, cursor_identifier = cursor_value
                if item_dt > cursor_dt:
                    continue
                if item_dt == cursor_dt and item_identifier >= cursor_identifier:
                    continue
            filtered.append(item)
        filtered.sort(
            key=lambda item: (
                self._parse_timestamp(item.get(timestamp_key)),
                str(item.get(identifier_key) or ""),
            ),
            reverse=True,
        )
        return filtered[:limit] if limit is not None else filtered

    def _review_sample_from_report(self, report_payload: Dict[str, Any], *, world_id: str) -> Dict[str, Any]:
        report = EvaluationReport.from_dict(report_payload)
        sample = {
            "sample_id": "sample_%s" % report.chapter_id,
            "chapter_id": report.chapter_id,
            "world_id": world_id,
            "world_version_id": report.world_version_id,
            "session_id": report.session_id,
            "reviewer_id": "narrative_eval_auto",
            "score_overall": report.scores.overall_score,
            "issue_codes": self._normalize_issue_codes([issue.issue_code for issue in report.issues]),
            "freeform_notes": report.summary,
            "would_continue": report.decision.decision in {"pass", "rewrite"},
            "would_pay": report.decision.decision == "pass",
            "created_at": report.created_at,
            "source": "evaluation_report_auto",
            "revision_id": None,
            "linked_issue_codes": self._normalize_issue_codes([issue.issue_code for issue in report.issues]),
            "source_ref": {"kind": "evaluation_report", "chapter_id": report.chapter_id},
            "ingestion_meta": {
                "ingestion_key": "auto_%s" % report.chapter_id,
                "reference_status": "validated",
                "ingested_at": report.created_at,
                "storage_mode": "synthetic",
                "ingestion_warnings": [],
            },
        }
        validate_payload(sample, "review_sample.schema.json")
        return sample

    def save_review_sample(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        source = str(payload.get("source") or "human_review")
        if source not in {"evaluation_report_auto", "human_review"}:
            raise ValueError("invalid_review_sample_source")
        sample = {
            "sample_id": None,
            "chapter_id": str(payload["chapter_id"]),
            "world_id": str(payload["world_id"]),
            "world_version_id": str(payload["world_version_id"]),
            "session_id": payload.get("session_id"),
            "reviewer_id": str(payload["reviewer_id"]),
            "score_overall": float(payload["score_overall"]),
            "issue_codes": self._normalize_issue_codes(payload.get("issue_codes", [])),
            "freeform_notes": str(payload.get("freeform_notes", "")),
            "would_continue": bool(payload["would_continue"]),
            "would_pay": bool(payload["would_pay"]),
            "created_at": str(payload.get("created_at") or self._utcnow()),
            "source": source,
            "revision_id": payload.get("revision_id"),
            "linked_issue_codes": self._normalize_issue_codes(payload.get("linked_issue_codes") or payload.get("issue_codes") or []),
            "source_ref": self._normalize_source_ref(payload, chapter_id=str(payload["chapter_id"])),
        }
        sample["sample_id"] = self._stable_review_sample_id({**sample, "sample_id": payload.get("sample_id")})
        reference_context = self._validate_review_sample_refs(sample)
        ingestion_warnings: List[str] = []
        if source == "human_review" and not sample.get("linked_issue_codes"):
            ingestion_warnings.append("missing_linked_issue_codes")
        if source == "human_review" and not sample.get("session_id"):
            ingestion_warnings.append("missing_session_context")
        sample["ingestion_meta"] = {
            "ingestion_key": self._review_sample_ingestion_key(sample),
            "reference_status": reference_context.get("reference_status"),
            "ingested_at": self._utcnow(),
            "storage_mode": "upsert",
            "ingestion_warnings": ingestion_warnings,
        }
        validate_payload(sample, "review_sample.schema.json")
        self.repository.save_review_record(
            {
                "review_id": "review_sample_%s" % sample["sample_id"],
                "asset_type": "review_sample",
                "asset_id": sample["chapter_id"],
                "status": sample["source"],
                "reviewer_id": sample["reviewer_id"],
                "notes": json.dumps(sample, ensure_ascii=False),
            }
        )
        return sample

    def list_review_samples(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(asset_type="review_sample", reviewer_id=reviewer_id)
        samples: List[Dict[str, Any]] = []
        for record in records:
            sample = self._parse_note_payload(record.get("notes"))
            if not sample:
                continue
            if world_version_id and sample.get("world_version_id") != world_version_id:
                continue
            if world_id and sample.get("world_id") != world_id:
                continue
            if source and sample.get("source") != source:
                continue
            sample.setdefault("created_at", record.get("updated_at"))
            sample["issue_codes"] = self._normalize_issue_codes(sample.get("issue_codes", []))
            sample["linked_issue_codes"] = self._normalize_issue_codes(sample.get("linked_issue_codes") or sample.get("issue_codes") or [])
            sample["source_ref"] = self._normalize_source_ref(sample, chapter_id=str(sample.get("chapter_id", "")))
            sample.setdefault(
                "ingestion_meta",
                {
                    "ingestion_key": self._review_sample_ingestion_key(sample),
                    "reference_status": "unknown",
                    "ingested_at": sample.get("created_at"),
                    "storage_mode": "legacy",
                    "ingestion_warnings": [],
                },
            )
            validate_payload(sample, "review_sample.schema.json")
            samples.append(sample)
        return self._apply_incremental_window(
            samples,
            timestamp_key="created_at",
            identifier_key="sample_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def save_preference_sample(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        source = str(payload.get("source") or "human_preference")
        if source != "human_preference":
            raise ValueError("invalid_preference_sample_source")
        sample = {
            "preference_id": None,
            "world_id": str(payload["world_id"]),
            "world_version_id": str(payload["world_version_id"]),
            "chapter_id": payload.get("chapter_id"),
            "session_id": payload.get("session_id"),
            "reviewer_id": str(payload["reviewer_id"]),
            "left_revision_id": str(payload["left_revision_id"]),
            "right_revision_id": str(payload["right_revision_id"]),
            "preferred_revision_id": str(payload["preferred_revision_id"]),
            "freeform_notes": str(payload.get("freeform_notes", "")),
            "linked_issue_codes": self._normalize_issue_codes(payload.get("linked_issue_codes") or []),
            "preference_strength": str(payload.get("preference_strength") or "medium"),
            "created_at": str(payload.get("created_at") or self._utcnow()),
            "source": source,
        }
        if sample["preference_strength"] not in {"strong", "medium", "weak"}:
            raise ValueError("invalid_preference_strength")
        sample["preference_id"] = self._stable_preference_sample_id({**sample, "preference_id": payload.get("preference_id")})
        reference_context = self._validate_preference_sample_refs(sample)
        ingestion_warnings: List[str] = []
        if not sample["linked_issue_codes"]:
            ingestion_warnings.append("missing_linked_issue_codes")
        if not sample.get("session_id"):
            ingestion_warnings.append("missing_session_context")
        sample["ingestion_meta"] = {
            "ingestion_key": self._preference_sample_ingestion_key(sample),
            "reference_status": reference_context.get("reference_status"),
            "ingested_at": self._utcnow(),
            "storage_mode": "upsert",
            "ingestion_warnings": ingestion_warnings,
        }
        validate_payload(sample, "preference_sample.schema.json")
        self.repository.save_review_record(
            {
                "review_id": "preference_sample_%s" % sample["preference_id"],
                "asset_type": "preference_sample",
                "asset_id": sample["preference_id"],
                "status": sample["source"],
                "reviewer_id": sample["reviewer_id"],
                "notes": json.dumps(sample, ensure_ascii=False),
            }
        )
        return sample

    def list_preference_samples(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(asset_type="preference_sample", reviewer_id=reviewer_id)
        samples: List[Dict[str, Any]] = []
        for record in records:
            sample = self._parse_note_payload(record.get("notes"))
            if not sample:
                continue
            if world_version_id and sample.get("world_version_id") != world_version_id:
                continue
            if world_id and sample.get("world_id") != world_id:
                continue
            sample.setdefault("created_at", record.get("updated_at"))
            sample["linked_issue_codes"] = self._normalize_issue_codes(sample.get("linked_issue_codes") or [])
            sample.setdefault(
                "ingestion_meta",
                {
                    "ingestion_key": self._preference_sample_ingestion_key(sample),
                    "reference_status": "unknown",
                    "ingested_at": sample.get("created_at"),
                    "storage_mode": "legacy",
                    "ingestion_warnings": [],
                },
            )
            validate_payload(sample, "preference_sample.schema.json")
            samples.append(sample)
        return self._apply_incremental_window(
            samples,
            timestamp_key="created_at",
            identifier_key="preference_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def save_ranking_sample(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        source = str(payload.get("source") or "human_ranking")
        if source != "human_ranking":
            raise ValueError("invalid_ranking_sample_source")
        ranked_revision_ids = [str(item) for item in payload.get("ranked_revision_ids") or [] if str(item).strip()]
        sample = {
            "ranking_id": None,
            "world_id": str(payload["world_id"]),
            "world_version_id": str(payload["world_version_id"]),
            "chapter_id": payload.get("chapter_id"),
            "session_id": payload.get("session_id"),
            "reviewer_id": str(payload["reviewer_id"]),
            "ranked_revision_ids": ranked_revision_ids,
            "top_revision_id": ranked_revision_ids[0] if ranked_revision_ids else "",
            "freeform_notes": str(payload.get("freeform_notes", "")),
            "linked_issue_codes": self._normalize_issue_codes(payload.get("linked_issue_codes") or []),
            "created_at": str(payload.get("created_at") or self._utcnow()),
            "source": source,
        }
        sample["ranking_id"] = self._stable_ranking_sample_id({**sample, "ranking_id": payload.get("ranking_id")})
        reference_context = self._validate_ranking_sample_refs(sample)
        ingestion_warnings: List[str] = []
        if not sample["linked_issue_codes"]:
            ingestion_warnings.append("missing_linked_issue_codes")
        if not sample.get("session_id"):
            ingestion_warnings.append("missing_session_context")
        sample["ingestion_meta"] = {
            "ingestion_key": self._ranking_sample_ingestion_key(sample),
            "reference_status": reference_context.get("reference_status"),
            "ingested_at": self._utcnow(),
            "storage_mode": "upsert",
            "ingestion_warnings": ingestion_warnings,
        }
        validate_payload(sample, "ranking_sample.schema.json")
        self.repository.save_review_record(
            {
                "review_id": "ranking_sample_%s" % sample["ranking_id"],
                "asset_type": "ranking_sample",
                "asset_id": sample["ranking_id"],
                "status": sample["source"],
                "reviewer_id": sample["reviewer_id"],
                "notes": json.dumps(sample, ensure_ascii=False),
            }
        )
        return sample

    def list_ranking_samples(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        records = self.repository.list_review_records(asset_type="ranking_sample", reviewer_id=reviewer_id)
        samples: List[Dict[str, Any]] = []
        for record in records:
            sample = self._parse_note_payload(record.get("notes"))
            if not sample:
                continue
            if world_version_id and sample.get("world_version_id") != world_version_id:
                continue
            if world_id and sample.get("world_id") != world_id:
                continue
            sample.setdefault("created_at", record.get("updated_at"))
            sample["linked_issue_codes"] = self._normalize_issue_codes(sample.get("linked_issue_codes") or [])
            sample.setdefault(
                "ingestion_meta",
                {
                    "ingestion_key": self._ranking_sample_ingestion_key(sample),
                    "reference_status": "unknown",
                    "ingested_at": sample.get("created_at"),
                    "storage_mode": "legacy",
                    "ingestion_warnings": [],
                },
            )
            validate_payload(sample, "ranking_sample.schema.json")
            samples.append(sample)
        return self._apply_incremental_window(
            samples,
            timestamp_key="created_at",
            identifier_key="ranking_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def pack_quality_trends(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        trends: List[Dict[str, Any]] = []
        for version_meta in versions:
            version = self.repository.get_world_version(version_meta["world_version_id"])
            simulation = dict(version.simulation_report_json or {})
            evaluation_summary = dict(simulation.get("evaluation_summary", {}))
            trend = {
                "world_id": version.world_id,
                "world_version_id": version.world_version_id,
                "pass_rate": float(evaluation_summary.get("pass_rate", 0.0)),
                "rewrite_rate": float(evaluation_summary.get("rewrite_rate", 0.0)),
                "block_rate": float(evaluation_summary.get("block_rate", 0.0)),
                "cross_pack_pass_rate": float(simulation.get("cross_pack_summary", {}).get("cross_pack_pass_rate", 0.0)),
                "updated_at": version_meta.get("updated_at"),
            }
            trends.append(trend)
        return self._apply_incremental_window(
            trends,
            timestamp_key="updated_at",
            identifier_key="world_version_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def _relative_weakest_world_ids(self, trends: Sequence[Dict[str, Any]]) -> Set[str]:
        ordered = sorted(
            trends,
            key=lambda item: (
                float(item.get("pass_rate", 0.0)),
                -float(item.get("block_rate", 0.0)),
                -float(item.get("rewrite_rate", 0.0)),
                float(item.get("cross_pack_pass_rate", 0.0)),
            ),
        )
        return {item["world_id"] for item in ordered[:3]}

    def review_sample_backlog(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        focus_issue_codes = {"Q03", "Q04", "Q05", "Q09"}
        trends = self.pack_quality_trends(world_id=world_id, world_version_id=world_version_id, limit=None)
        weakest_world_ids = self._relative_weakest_world_ids(trends)
        human_review_chapter_ids = {
            sample["chapter_id"]
            for sample in self.list_review_samples(
                world_id=world_id,
                world_version_id=world_version_id,
                source="human_review",
                limit=None,
            )
        }
        backlog: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for version_meta in self._selected_versions(world_id=world_id, world_version_id=world_version_id):
            version = self.repository.get_world_version(version_meta["world_version_id"])
            report_payloads = list(version.simulation_report_json.get("chapter_evaluations", []))
            report_payloads.extend(self.repository.list_evaluation_reports(world_version_id=version.world_version_id))
            for report_payload in report_payloads:
                report = EvaluationReport.from_dict(report_payload)
                if report.chapter_id in seen or report.chapter_id in human_review_chapter_ids:
                    continue
                seen.add(report.chapter_id)
                issue_codes = sorted({issue.issue_code for issue in report.issues})
                issue_focus = bool(set(issue_codes) & focus_issue_codes)
                decision = report.decision.decision
                if decision == "block":
                    priority = "high"
                elif decision == "rewrite":
                    priority = "medium"
                elif version.world_id in weakest_world_ids and issue_focus:
                    priority = "low"
                else:
                    continue
                backlog.append(
                    {
                        "chapter_id": report.chapter_id,
                        "world_id": version.world_id,
                        "world_version_id": version.world_version_id,
                        "session_id": report.session_id,
                        "decision": decision,
                        "score_overall": report.scores.overall_score,
                        "issue_codes": issue_codes,
                        "summary": report.summary,
                        "priority": priority,
                        "source": "evaluation_report_auto",
                        "created_at": report.created_at,
                    }
                )
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        backlog.sort(key=lambda item: (priority_rank[item["priority"]], -self._parse_timestamp(item["created_at"]).timestamp()))
        return backlog[:limit] if limit is not None else backlog

    def issue_fix_pair_backlog(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        issue_fix_pairs = self.issue_fix_pairs(
            world_id=world_id,
            world_version_id=world_version_id,
            limit=None,
        )
        revision_logs = self.author_revision_logs(
            world_id=world_id,
            world_version_id=world_version_id,
            limit=None,
        )
        review_samples = self.chapter_review_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            limit=None,
        )

        pair_counts: Dict[Tuple[str, str], int] = {}
        strong_pair_counts: Dict[Tuple[str, str], int] = {}
        for pair in issue_fix_pairs:
            version_issue_codes = list(pair.get("linked_issue_codes") or [])
            for issue_code in version_issue_codes:
                pair_counts[(pair["world_version_id"], str(issue_code))] = pair_counts.get((pair["world_version_id"], str(issue_code)), 0) + 1
                if pair.get("pair_quality") in {"strong", "medium"}:
                    strong_pair_counts[(pair["world_version_id"], str(issue_code))] = strong_pair_counts.get((pair["world_version_id"], str(issue_code)), 0) + 1

        review_issue_counts: Dict[Tuple[str, str], int] = {}
        for sample in review_samples:
            issue_codes = list(sample.get("linked_issue_codes") or sample.get("issue_codes") or [])
            for issue_code in issue_codes:
                review_issue_counts[(sample["world_version_id"], str(issue_code))] = review_issue_counts.get(
                    (sample["world_version_id"], str(issue_code)),
                    0,
                ) + 1

        revision_logs_by_version: Dict[str, List[Dict[str, Any]]] = {}
        for log in revision_logs:
            revision_logs_by_version.setdefault(log["world_version_id"], []).append(log)

        backlog: List[Dict[str, Any]] = []
        for version_meta in versions:
            version_id = version_meta["world_version_id"]
            current_logs = sorted(
                revision_logs_by_version.get(version_id, []),
                key=lambda item: self._parse_timestamp(item.get("timestamp")).timestamp(),
                reverse=True,
            )
            recent_logs = current_logs[:3]
            recent_revision_ids = [item["revision_id"] for item in recent_logs if item.get("revision_id")]
            changed_sections = sorted(
                {
                    section
                    for item in recent_logs
                    for section in item.get("changed_sections", [])
                }
            )
            latest_timestamp = recent_logs[0]["timestamp"] if recent_logs else version_meta.get("updated_at")
            issue_codes = sorted(
                {
                    issue_code
                    for (sample_version_id, issue_code), count in review_issue_counts.items()
                    if sample_version_id == version_id and count > 0
                }
                | {
                    issue_code
                    for (pair_version_id, issue_code), count in pair_counts.items()
                    if pair_version_id == version_id and count > 0
                }
            )
            for issue_code in issue_codes:
                coverage_count = int(pair_counts.get((version_id, issue_code), 0))
                effective_coverage_count = int(strong_pair_counts.get((version_id, issue_code), 0))
                if effective_coverage_count >= 3:
                    continue
                recommendation = "request_more_revisions" if effective_coverage_count == 0 else "expand_issue_fix_pairs"
                backlog.append(
                    {
                        "world_id": version_meta["world_id"],
                        "world_version_id": version_id,
                        "issue_code": issue_code,
                        "coverage_count": coverage_count,
                        "effective_coverage_count": effective_coverage_count,
                        "recent_revision_ids": recent_revision_ids,
                        "changed_sections": changed_sections,
                        "recommended_action": recommendation,
                        "created_at": latest_timestamp,
                    }
                )

        backlog.sort(
            key=lambda item: (
                item["coverage_count"],
                item["effective_coverage_count"],
                -len(item["recent_revision_ids"]),
                -self._parse_timestamp(item.get("created_at")).timestamp(),
                item["world_id"],
                item["issue_code"],
            )
        )
        return backlog[:limit] if limit is not None else backlog

    def chapter_review_samples(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        samples: List[Dict[str, Any]] = []
        seen_auto: Set[str] = set()
        for version_meta in versions:
            version = self.repository.get_world_version(version_meta["world_version_id"])
            report_payloads = list(version.simulation_report_json.get("chapter_evaluations", []))
            report_payloads.extend(self.repository.list_evaluation_reports(world_version_id=version.world_version_id))
            for report_payload in report_payloads:
                chapter_id = report_payload.get("chapter_id")
                if not chapter_id or chapter_id in seen_auto:
                    continue
                seen_auto.add(chapter_id)
                samples.append(self._review_sample_from_report(report_payload, world_id=version.world_id))
        samples.extend(
            self.list_review_samples(
                world_id=world_id,
                world_version_id=world_version_id,
                since=since,
                cursor=cursor,
                limit=None,
            )
        )
        deduped: Dict[str, Dict[str, Any]] = {}
        for sample in samples:
            deduped[str(sample["sample_id"])] = sample
        return self._apply_incremental_window(
            list(deduped.values()),
            timestamp_key="created_at",
            identifier_key="sample_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def review_samples_from_reports(
        self,
        report_payloads: Sequence[Dict[str, Any]],
        *,
        world_id: str,
    ) -> List[Dict[str, Any]]:
        return [self._review_sample_from_report(report_payload, world_id=world_id) for report_payload in report_payloads]

    def evaluator_examples_from_reports(
        self,
        report_payloads: Sequence[Dict[str, Any]],
        *,
        world_id: str,
    ) -> List[Dict[str, Any]]:
        return self.evaluator_examples(self.review_samples_from_reports(report_payloads, world_id=world_id))

    def author_revision_logs(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        logs: List[Dict[str, Any]] = []
        for version_meta in versions:
            version = self.repository.get_world_version(version_meta["world_version_id"])
            metadata = dict((version.worldpack_json or {}).get("metadata", {}))
            for revision in metadata.get("revision_history", []):
                log = {
                    "world_id": version.world_id,
                    "world_version_id": version.world_version_id,
                    "revision_id": revision.get("revision_id"),
                    "source": revision.get("source", "manual_update"),
                    "label": revision.get("label", ""),
                    "changed_sections": list(revision.get("changed_sections", [])),
                    "summary": revision.get("summary", ""),
                    "simulation_delta": revision.get("simulation_delta"),
                    "timestamp": revision.get("created_at", ""),
                }
                validate_payload(log, "author_revision_log.schema.json")
                logs.append(log)
        return self._apply_incremental_window(
            logs,
            timestamp_key="timestamp",
            identifier_key="revision_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def _samples_in_window(
        self,
        samples: Sequence[Dict[str, Any]],
        *,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for sample in samples:
            sample_dt = self._parse_timestamp(sample.get("created_at"))
            if start_dt and sample_dt < start_dt:
                continue
            if end_dt and sample_dt >= end_dt:
                continue
            selected.append(sample)
        return selected

    def _pair_quality(
        self,
        *,
        improved: bool,
        changed_sections: Sequence[str],
        linked_issue_codes: Sequence[str],
        human_review_count: int,
        review_coverage_count: int,
    ) -> str:
        if improved and human_review_count > 0 and linked_issue_codes and changed_sections:
            return "strong"
        if improved and (linked_issue_codes or review_coverage_count > 0):
            return "medium"
        return "weak"

    def _pair_source(
        self,
        *,
        before_human_count: int,
        after_human_count: int,
        before_count: int,
        after_count: int,
    ) -> str:
        if before_human_count and after_human_count:
            return "human_before_after"
        if after_human_count:
            return "human_after_window"
        if before_human_count:
            return "human_before_window"
        if after_count:
            return "auto_eval_after_window"
        if before_count:
            return "auto_eval_before_window"
        return "revision_delta_only"

    def issue_fix_pairs(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        pairs: List[Dict[str, Any]] = []
        for version_meta in versions:
            version = self.repository.get_world_version(version_meta["world_version_id"])
            metadata = dict((version.worldpack_json or {}).get("metadata", {}))
            revisions = list(metadata.get("revision_history", []))
            version_samples = self.chapter_review_samples(world_version_id=version.world_version_id, limit=None)
            for index in range(1, len(revisions)):
                before = revisions[index - 1]
                after = revisions[index]
                next_revision = revisions[index + 1] if index + 1 < len(revisions) else None
                simulation_delta = dict(after.get("simulation_delta") or {})
                metric_deltas = dict(simulation_delta.get("metric_deltas") or {})
                if not simulation_delta and not metric_deltas:
                    continue
                if not any(
                    value not in (None, 0, {}, [])
                    for value in [
                        simulation_delta.get("pass_rate_delta"),
                        simulation_delta.get("rewrite_rate_delta"),
                        simulation_delta.get("block_rate_delta"),
                        metric_deltas,
                    ]
                ):
                    continue
                before_dt = self._parse_timestamp(before.get("created_at"))
                after_dt = self._parse_timestamp(after.get("created_at"))
                next_dt = self._parse_timestamp(next_revision.get("created_at")) if next_revision else None
                before_window_samples = self._samples_in_window(version_samples, start_dt=before_dt, end_dt=after_dt)
                after_window_samples = self._samples_in_window(version_samples, start_dt=after_dt, end_dt=next_dt)
                linked_samples = [*before_window_samples, *after_window_samples]
                pass_rate_delta = float(simulation_delta.get("pass_rate_delta") or 0.0)
                rewrite_rate_delta = float(simulation_delta.get("rewrite_rate_delta") or 0.0)
                block_rate_delta = float(simulation_delta.get("block_rate_delta") or 0.0)
                before_human_samples = [sample for sample in before_window_samples if sample.get("source") == "human_review"]
                after_human_samples = [sample for sample in after_window_samples if sample.get("source") == "human_review"]
                human_samples = [*before_human_samples, *after_human_samples]
                source_samples = after_human_samples or before_human_samples or after_window_samples or before_window_samples
                linked_issue_codes = []
                for sample in source_samples:
                    linked_issue_codes.extend(list(sample.get("linked_issue_codes") or sample.get("issue_codes") or []))
                linked_issue_codes = self._normalize_issue_codes(linked_issue_codes)
                improved = pass_rate_delta > 0 or rewrite_rate_delta < 0 or block_rate_delta < 0
                pair_warnings: List[str] = []
                if not linked_samples:
                    pair_warnings.append("no_linked_review_samples")
                if not human_samples:
                    pair_warnings.append("no_human_review_window")
                if not linked_issue_codes:
                    pair_warnings.append("no_linked_issue_codes")
                if not after.get("changed_sections", []):
                    pair_warnings.append("missing_changed_sections")
                pair = {
                    "pair_id": "pair_%s_%s" % (before.get("revision_id"), after.get("revision_id")),
                    "world_id": version.world_id,
                    "world_version_id": version.world_version_id,
                    "before_revision_id": before.get("revision_id"),
                    "after_revision_id": after.get("revision_id"),
                    "changed_sections": list(after.get("changed_sections", [])),
                    "before_summary": before.get("summary", ""),
                    "after_summary": after.get("summary", ""),
                    "simulation_delta": simulation_delta,
                    "improved": improved,
                    "linked_review_sample_ids": [sample["sample_id"] for sample in linked_samples],
                    "before_review_sample_ids": [sample["sample_id"] for sample in before_window_samples],
                    "after_review_sample_ids": [sample["sample_id"] for sample in after_window_samples],
                    "linked_issue_codes": linked_issue_codes,
                    "review_coverage_count": len(linked_samples),
                    "human_review_count": len(human_samples),
                    "pair_source": self._pair_source(
                        before_human_count=len(before_human_samples),
                        after_human_count=len(after_human_samples),
                        before_count=len(before_window_samples),
                        after_count=len(after_window_samples),
                    ),
                    "pair_quality": self._pair_quality(
                        improved=improved,
                        changed_sections=after.get("changed_sections", []),
                        linked_issue_codes=linked_issue_codes,
                        human_review_count=len(human_samples),
                        review_coverage_count=len(linked_samples),
                    ),
                    "pair_warnings": pair_warnings,
                    "timestamp": after.get("created_at", ""),
                }
                validate_payload(pair, "issue_fix_pair.schema.json")
                pairs.append(pair)
        return self._apply_incremental_window(
            pairs,
            timestamp_key="timestamp",
            identifier_key="pair_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def _manifest(
        self,
        *,
        chapter_review_samples: Sequence[Dict[str, Any]],
        preference_samples: Sequence[Dict[str, Any]],
        ranking_samples: Sequence[Dict[str, Any]],
        author_revision_logs: Sequence[Dict[str, Any]],
        continue_churn_events: Sequence[Dict[str, Any]],
        issue_fix_pairs: Sequence[Dict[str, Any]],
        evaluator_examples: Sequence[Dict[str, Any]],
        reranker_examples: Sequence[Dict[str, Any]],
        analytics_examples: Sequence[Dict[str, Any]],
        generated_at: str,
        filters: Dict[str, Any],
        warnings: Sequence[str],
    ) -> Dict[str, Any]:
        issue_counter: Counter[str] = Counter()
        for sample in chapter_review_samples:
            for issue_code in sample.get("linked_issue_codes") or sample.get("issue_codes") or []:
                issue_counter[str(issue_code)] += 1
        inferred_event_count = sum(
            1 for event in continue_churn_events if event.get("event_name") == "session_abandoned" and event.get("payload_json", {}).get("inferred")
        )
        return {
            "bundle_id": "bundle_%s" % uuid4().hex[:12],
            "generated_at": generated_at,
            "filters": dict(filters),
            "counts": {
                "chapter_review_samples": len(chapter_review_samples),
                "preference_samples": len(preference_samples),
                "ranking_samples": len(ranking_samples),
                "author_revision_logs": len(author_revision_logs),
                "continue_churn_events": len(continue_churn_events),
                "issue_fix_pairs": len(issue_fix_pairs),
            },
            "source_breakdown": {
                "evaluation_report_auto": sum(1 for sample in chapter_review_samples if sample.get("source") == "evaluation_report_auto"),
                "human_review": sum(1 for sample in chapter_review_samples if sample.get("source") == "human_review"),
                "human_preference": sum(1 for sample in preference_samples if sample.get("source") == "human_preference"),
                "human_ranking": sum(1 for sample in ranking_samples if sample.get("source") == "human_ranking"),
                "inferred_session_abandoned": inferred_event_count,
            },
            "issue_code_histogram": dict(issue_counter),
            "inferred_event_count": inferred_event_count,
            "warnings": list(warnings),
        }

    def _label_decision_from_sample(self, sample: Dict[str, Any]) -> str:
        if bool(sample.get("would_pay")):
            return "pass"
        if bool(sample.get("would_continue")):
            return "rewrite"
        return "block"

    def evaluator_examples(self, chapter_review_samples: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for sample in chapter_review_samples:
            grouped.setdefault(sample["chapter_id"], []).append(sample)
        examples: List[Dict[str, Any]] = []
        for chapter_id, samples in grouped.items():
            preferred = sorted(
                samples,
                key=lambda item: (
                    0 if item.get("source") == "human_review" else 1,
                    -self._parse_timestamp(item.get("created_at")).timestamp(),
                ),
            )[0]
            example = {
                "example_id": f"eval_{preferred['sample_id']}",
                "chapter_id": chapter_id,
                "world_id": preferred["world_id"],
                "world_version_id": preferred["world_version_id"],
                "review_source": preferred["source"],
                "score_overall": float(preferred["score_overall"]),
                "issue_codes": list(preferred.get("issue_codes", [])),
                "linked_issue_codes": list(preferred.get("linked_issue_codes") or preferred.get("issue_codes") or []),
                "would_continue": bool(preferred["would_continue"]),
                "would_pay": bool(preferred["would_pay"]),
                "label_decision": self._label_decision_from_sample(preferred),
                "split": self._split_for(preferred["world_version_id"], chapter_id),
                "text_source_ref": {
                    "chapter_id": preferred["chapter_id"],
                    "world_version_id": preferred["world_version_id"],
                },
            }
            examples.append(example)
        return sorted(examples, key=lambda item: item["example_id"])

    def reranker_examples(
        self,
        issue_fix_pairs: Sequence[Dict[str, Any]],
        *,
        preference_samples: Optional[Sequence[Dict[str, Any]]] = None,
        ranking_samples: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        examples: List[Dict[str, Any]] = []
        for pair in issue_fix_pairs:
            if not pair.get("improved"):
                continue
            simulation_delta = dict(pair.get("simulation_delta") or {})
            pass_rate_delta = float(simulation_delta.get("pass_rate_delta") or 0.0)
            rewrite_rate_delta = float(simulation_delta.get("rewrite_rate_delta") or 0.0)
            block_rate_delta = float(simulation_delta.get("block_rate_delta") or 0.0)
            preference_strength = "strong" if pass_rate_delta > 0 or block_rate_delta < 0 else "medium"
            examples.append(
                {
                    "example_id": f"rerank_{pair['pair_id']}",
                    "world_id": pair["world_id"],
                    "world_version_id": pair["world_version_id"],
                    "before_revision_id": pair["before_revision_id"],
                    "after_revision_id": pair["after_revision_id"],
                    "changed_sections": list(pair.get("changed_sections", [])),
                    "linked_issue_codes": list(pair.get("linked_issue_codes", [])),
                    "preferred_revision_id": pair["after_revision_id"],
                    "preference_strength": preference_strength,
                    "example_source": "issue_fix_pair",
                    "split": self._split_for(pair["world_version_id"], pair["pair_id"]),
                }
            )
        for sample in preference_samples or []:
            examples.append(
                {
                    "example_id": f"rerank_pref_{sample['preference_id']}",
                    "world_id": sample["world_id"],
                    "world_version_id": sample["world_version_id"],
                    "before_revision_id": sample["left_revision_id"],
                    "after_revision_id": sample["right_revision_id"],
                    "changed_sections": [],
                    "linked_issue_codes": list(sample.get("linked_issue_codes", [])),
                    "preferred_revision_id": sample["preferred_revision_id"],
                    "preference_strength": "strong" if sample.get("preference_strength") == "weak" else sample.get("preference_strength", "medium"),
                    "example_source": "preference_sample",
                    "split": self._split_for(sample["world_version_id"], sample["preference_id"]),
                }
            )
        for sample in ranking_samples or []:
            ranked_revision_ids = list(sample.get("ranked_revision_ids", []))
            for higher_index in range(len(ranked_revision_ids)):
                for lower_index in range(higher_index + 1, len(ranked_revision_ids)):
                    preferred_revision_id = ranked_revision_ids[higher_index]
                    alternative_revision_id = ranked_revision_ids[lower_index]
                    examples.append(
                        {
                            "example_id": f"rerank_rank_{sample['ranking_id']}_{higher_index}_{lower_index}",
                            "world_id": sample["world_id"],
                            "world_version_id": sample["world_version_id"],
                            "before_revision_id": alternative_revision_id,
                            "after_revision_id": preferred_revision_id,
                            "changed_sections": [],
                            "linked_issue_codes": list(sample.get("linked_issue_codes", [])),
                            "preferred_revision_id": preferred_revision_id,
                            "preference_strength": "strong" if lower_index - higher_index > 1 else "medium",
                            "example_source": "ranking_sample",
                            "split": self._split_for(sample["world_version_id"], f"{sample['ranking_id']}::{higher_index}::{lower_index}"),
                        }
                    )
        return sorted(examples, key=lambda item: item["example_id"])

    def analytics_examples(self, continue_churn_events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for event in continue_churn_events:
            session_id = event.get("session_id")
            if session_id:
                grouped.setdefault(session_id, []).append(event)
        examples: List[Dict[str, Any]] = []
        for session_id, events in grouped.items():
            has_continue = any(event["event_name"] == "continue_story" for event in events)
            has_churn = any(event["event_name"] == "session_abandoned" for event in events)
            if has_continue and has_churn:
                # contradictory labels are dropped and surfaced via warnings
                continue
            if not has_continue and not has_churn:
                continue
            anchor = sorted(events, key=lambda item: self._parse_timestamp(item.get("occurred_at")), reverse=True)[0]
            examples.append(
                {
                    "example_id": f"analytics_{session_id}",
                    "reader_id": anchor.get("reader_id"),
                    "session_id": session_id,
                    "world_id": anchor["world_id"],
                    "world_version_id": anchor["world_version_id"],
                    "chapter_index": anchor.get("chapter_index"),
                    "access_tier": anchor.get("access_tier"),
                    "label_continue": 1 if has_continue else 0,
                    "label_churn": 1 if has_churn else 0,
                    "event_source": "continue_story" if has_continue else "session_abandoned",
                    "split": self._split_for(anchor["world_version_id"], session_id),
                }
            )
        return sorted(examples, key=lambda item: item["example_id"])

    def _split_leakage_warning(self, examples: Sequence[Dict[str, Any]], stable_key: str) -> bool:
        seen: Dict[str, str] = {}
        for item in examples:
            stable_id = str(item.get(stable_key) or "")
            if not stable_id:
                continue
            split = item.get("split")
            previous = seen.get(stable_id)
            if previous is not None and previous != split:
                return True
            seen[stable_id] = split
        return False

    def _warnings(
        self,
        *,
        chapter_review_samples: Sequence[Dict[str, Any]],
        preference_samples: Sequence[Dict[str, Any]],
        ranking_samples: Sequence[Dict[str, Any]],
        issue_fix_pairs: Sequence[Dict[str, Any]],
        evaluator_examples: Sequence[Dict[str, Any]],
        reranker_examples: Sequence[Dict[str, Any]],
        analytics_examples: Sequence[Dict[str, Any]],
    ) -> List[str]:
        warnings: List[str] = []
        if not any(sample.get("source") == "human_review" for sample in chapter_review_samples):
            warnings.append("missing_human_review_coverage")
        if any(not example.get("linked_issue_codes") for example in evaluator_examples) or any(not pair.get("linked_issue_codes") for pair in issue_fix_pairs):
            warnings.append("missing_linked_issue_codes")
        if len(preference_samples) < 3:
            warnings.append("insufficient_preference_samples")
        if len(ranking_samples) < 2:
            warnings.append("insufficient_ranking_samples")
        if len(reranker_examples) < 5:
            warnings.append("insufficient_reranker_pairs")
        if any(pair.get("pair_quality") == "weak" for pair in issue_fix_pairs):
            warnings.append("weak_issue_fix_pairs_present")
        if any((sample.get("ingestion_meta") or {}).get("ingestion_warnings") for sample in chapter_review_samples):
            warnings.append("review_sample_ingestion_warnings_present")
        if any((sample.get("ingestion_meta") or {}).get("ingestion_warnings") for sample in preference_samples):
            warnings.append("preference_sample_ingestion_warnings_present")
        if any((sample.get("ingestion_meta") or {}).get("ingestion_warnings") for sample in ranking_samples):
            warnings.append("ranking_sample_ingestion_warnings_present")
        if len(analytics_examples) < 5:
            warnings.append("insufficient_analytics_examples")
        if (
            self._split_leakage_warning(evaluator_examples, "chapter_id")
            or self._split_leakage_warning(reranker_examples, "example_id")
            or self._split_leakage_warning(analytics_examples, "session_id")
        ):
            warnings.append("potential_split_leakage")
        return warnings

    def continue_churn_events(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        include_inferred: bool = True,
    ) -> List[Dict[str, Any]]:
        versions = self._selected_versions(world_id=world_id, world_version_id=world_version_id)
        version_ids = [item["world_version_id"] for item in versions]
        version_world_map = {item["world_version_id"]: item["world_id"] for item in versions}

        raw_events = self.repository.list_analytics_events(
            event_names=PHASE4_EVENT_NAMES,
            world_version_ids=version_ids or None,
        )
        normalized: List[Dict[str, Any]] = []
        seen_session_events: Dict[str, Set[str]] = {}

        for event in raw_events:
            payload_json = dict(event.get("payload_json", {}))
            session_id = event.get("session_id")
            if session_id:
                seen_session_events.setdefault(session_id, set()).add(event["event_name"])
            normalized_event = {
                "event_name": event["event_name"],
                "reader_id": event.get("reader_id"),
                "session_id": session_id,
                "world_id": payload_json.get("world_id") or version_world_map.get(event.get("world_version_id"), ""),
                "world_version_id": event.get("world_version_id") or "",
                "chapter_index": payload_json.get("chapter_index"),
                "access_tier": payload_json.get("access_tier"),
                "occurred_at": event.get("occurred_at"),
                "payload_json": payload_json,
            }
            validate_payload(normalized_event, "continue_churn_event.schema.json")
            normalized.append(normalized_event)

        if include_inferred:
            now = datetime.now(timezone.utc)
            sessions = self.repository.list_sessions(world_id=world_id)
            for session in sessions:
                if world_version_id and session["world_version_id"] != world_version_id:
                    continue
                created_events = seen_session_events.get(session["session_id"], set())
                if "session_created" not in created_events:
                    continue
                if "continue_story" in created_events or "chapter_rendered" in created_events:
                    continue
                session_created_at = self._parse_timestamp(session["created_at"])
                abandon_at = session_created_at + timedelta(hours=ABANDON_WINDOW_HOURS)
                if now < abandon_at:
                    continue
                session_record = self.repository.get_session(session["session_id"])
                inferred = {
                    "event_name": "session_abandoned",
                    "reader_id": session_record.metadata.get("reader_id") or session_record.player_profile.get("reader_id"),
                    "session_id": session["session_id"],
                    "world_id": session["world_id"],
                    "world_version_id": session["world_version_id"],
                    "chapter_index": 0,
                    "access_tier": session_record.metadata.get("entitlements_snapshot", {}).get("access_tier"),
                    "occurred_at": abandon_at.isoformat(),
                    "payload_json": {
                        "inferred": True,
                        "inference_reason": "no_continue_or_render_after_session_created",
                        "abandon_window_hours": ABANDON_WINDOW_HOURS,
                    },
                }
                validate_payload(inferred, "continue_churn_event.schema.json")
                normalized.append(inferred)

        return self._apply_incremental_window(
            normalized,
            timestamp_key="occurred_at",
            identifier_key="session_id",
            since=since,
            cursor=cursor,
            limit=limit,
        )

    def export_bundle(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        since: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        include_inferred: bool = True,
        include_fix_pairs: bool = True,
        dataset_view: str = "raw",
    ) -> Dict[str, Any]:
        filters = {
            "world_id": world_id,
            "world_version_id": world_version_id,
            "limit": limit,
            "since": since,
            "cursor": cursor,
            "include_inferred": include_inferred,
            "include_fix_pairs": include_fix_pairs,
            "dataset_view": dataset_view,
        }
        chapter_review_samples = self.chapter_review_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
        preference_samples = self.list_preference_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
        ranking_samples = self.list_ranking_samples(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
        author_revision_logs = self.author_revision_logs(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )
        continue_churn_events = self.continue_churn_events(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
            include_inferred=include_inferred,
        )
        issue_fix_pairs = (
            self.issue_fix_pairs(
                world_id=world_id,
                world_version_id=world_version_id,
                since=since,
                cursor=cursor,
                limit=limit,
            )
            if include_fix_pairs
            else []
        )
        evaluator_examples = self.evaluator_examples(chapter_review_samples)
        reranker_examples = self.reranker_examples(
            issue_fix_pairs,
            preference_samples=preference_samples,
            ranking_samples=ranking_samples,
        )
        analytics_examples = self.analytics_examples(continue_churn_events)
        pack_quality_trends = self.pack_quality_trends(
            world_id=world_id,
            world_version_id=world_version_id,
            since=since,
            cursor=cursor,
            limit=limit,
        )

        cursor_candidates: List[Tuple[datetime, str]] = []
        for items, timestamp_key, id_key in [
            (chapter_review_samples, "created_at", "sample_id"),
            (preference_samples, "created_at", "preference_id"),
            (ranking_samples, "created_at", "ranking_id"),
            (author_revision_logs, "timestamp", "revision_id"),
            (continue_churn_events, "occurred_at", "session_id"),
            (issue_fix_pairs, "timestamp", "pair_id"),
        ]:
            for item in items:
                cursor_candidates.append((self._parse_timestamp(item.get(timestamp_key)), str(item.get(id_key) or "")))
        oldest = min(cursor_candidates, default=None)
        next_cursor = self._build_cursor(oldest[0].isoformat(), oldest[1]) if oldest else None
        generated_at = self._utcnow()
        warnings = self._warnings(
            chapter_review_samples=chapter_review_samples,
            preference_samples=preference_samples,
            ranking_samples=ranking_samples,
            issue_fix_pairs=issue_fix_pairs,
            evaluator_examples=evaluator_examples,
            reranker_examples=reranker_examples,
            analytics_examples=analytics_examples,
        )
        manifest = self._manifest(
            chapter_review_samples=chapter_review_samples,
            preference_samples=preference_samples,
            ranking_samples=ranking_samples,
            author_revision_logs=author_revision_logs,
            continue_churn_events=continue_churn_events,
            issue_fix_pairs=issue_fix_pairs,
            evaluator_examples=evaluator_examples,
            reranker_examples=reranker_examples,
            analytics_examples=analytics_examples,
            generated_at=generated_at,
            filters=filters,
            warnings=warnings,
        )

        if dataset_view == "raw":
            selected_evaluator_examples: List[Dict[str, Any]] = []
            selected_reranker_examples: List[Dict[str, Any]] = []
            selected_analytics_examples: List[Dict[str, Any]] = []
        elif dataset_view == "evaluator":
            selected_evaluator_examples = evaluator_examples
            selected_reranker_examples = []
            selected_analytics_examples = []
        elif dataset_view == "reranker":
            selected_evaluator_examples = []
            selected_reranker_examples = reranker_examples
            selected_analytics_examples = []
        elif dataset_view == "analytics":
            selected_evaluator_examples = []
            selected_reranker_examples = []
            selected_analytics_examples = analytics_examples
        else:
            raise ValueError("invalid_dataset_view")

        bundle = {
            "chapter_review_samples": chapter_review_samples,
            "preference_samples": preference_samples,
            "ranking_samples": ranking_samples,
            "author_revision_logs": author_revision_logs,
            "continue_churn_events": continue_churn_events,
            "issue_fix_pairs": issue_fix_pairs,
            "manifest": manifest,
            "pack_quality_trends": pack_quality_trends,
            "evaluator_examples": selected_evaluator_examples,
            "reranker_examples": selected_reranker_examples,
            "analytics_examples": selected_analytics_examples,
            "generated_at": generated_at,
            "filters": filters,
            "next_cursor": next_cursor,
        }
        validate_payload(bundle, "training_signal_bundle.schema.json")
        return bundle
