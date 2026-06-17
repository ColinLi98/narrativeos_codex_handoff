from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..persistence.repositories import SQLAlchemyPlatformRepository


NOSBOOK_SCHEMA_VERSION = "nosbook/v1"
NOSBOOK_IMPORT_RESULT_SCHEMA_VERSION = "nosbook_import_result/v1"
NOSBOOK_CONTENT_TYPE = "application/vnd.narrativeos.nosbook+json"
REQUIRED_NOSBOOK_FIELDS = {
    "work",
    "chapters",
    "branch_map",
    "choice_history",
    "quality_summary",
}


class NosbookImportError(ValueError):
    def __init__(self, code: str, reason: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.details = dict(details or {})

    def detail(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            **({"details": self.details} if self.details else {}),
        }


class NosbookImportService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _canonical_checksum(self, envelope: Dict[str, Any]) -> str:
        encoded = json.dumps(
            envelope,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _require_mapping(self, payload: Any, *, code: str, reason: str) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise NosbookImportError(code, reason)
        return dict(payload)

    def _validate_envelope(self, envelope: Any) -> Dict[str, Any]:
        payload = self._require_mapping(
            envelope,
            code="malformed_nosbook",
            reason="nosbook_envelope_must_be_json_object",
        )
        schema_version = str(payload.get("schema_version") or "").strip()
        if schema_version != NOSBOOK_SCHEMA_VERSION:
            raise NosbookImportError(
                "unsupported_nosbook_schema",
                "nosbook_schema_version_must_be_nosbook_v1",
                details={"schema_version": schema_version or None},
            )
        missing = sorted(field for field in REQUIRED_NOSBOOK_FIELDS if field not in payload)
        if missing:
            raise NosbookImportError(
                "malformed_nosbook",
                "nosbook_required_fields_missing",
                details={"missing_fields": missing},
            )
        work = self._require_mapping(
            payload.get("work"),
            code="malformed_nosbook",
            reason="nosbook_work_must_be_json_object",
        )
        chapters = payload.get("chapters")
        if not isinstance(chapters, list) or not chapters:
            raise NosbookImportError(
                "malformed_nosbook",
                "nosbook_chapters_must_be_non_empty_array",
            )
        branch_map = payload.get("branch_map")
        if not isinstance(branch_map, list):
            raise NosbookImportError("malformed_nosbook", "nosbook_branch_map_must_be_array")
        choice_history = payload.get("choice_history")
        if not isinstance(choice_history, list):
            raise NosbookImportError("malformed_nosbook", "nosbook_choice_history_must_be_array")
        quality_summary = payload.get("quality_summary")
        if not isinstance(quality_summary, dict):
            raise NosbookImportError("malformed_nosbook", "nosbook_quality_summary_must_be_json_object")
        normalized_chapters: List[Dict[str, Any]] = []
        for index, chapter in enumerate(chapters, start=1):
            item = self._require_mapping(
                chapter,
                code="malformed_nosbook",
                reason="nosbook_chapter_must_be_json_object",
            )
            body = str(item.get("body") or "").strip()
            if not body:
                raise NosbookImportError(
                    "malformed_nosbook",
                    "nosbook_chapter_body_required",
                    details={"chapter_position": index},
                )
            chapter_index = int(item.get("chapter_index") or index)
            normalized_chapters.append({**item, "chapter_index": chapter_index, "body": body})
        return {
            **payload,
            "work": work,
            "chapters": normalized_chapters,
            "branch_map": [dict(item) for item in branch_map if isinstance(item, dict)],
            "choice_history": [dict(item) for item in choice_history if isinstance(item, dict)],
            "quality_summary": dict(quality_summary),
        }

    def _world_version_link_status(self, world_version_id: str, warnings: List[Dict[str, Any]]) -> str:
        if not world_version_id:
            warnings.append(
                {
                    "code": "missing_source_world_version_id",
                    "message": "Imported as source-only because the nosbook did not include a source world version.",
                }
            )
            return "source_only"
        try:
            self.repository.get_world_version(world_version_id)
        except KeyError:
            warnings.append(
                {
                    "code": "source_world_version_not_found",
                    "message": "Imported as source-only; platform continuation may be limited until the source world exists.",
                    "world_version_id": world_version_id,
                }
            )
            return "source_only"
        return "linked"

    def _duplicate_result(
        self,
        *,
        account_id: str,
        checksum: str,
        import_id: str,
        world_version_link_status: str,
        warnings: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for work in self.repository.list_author_works(account_id=account_id, limit=500):
            diagnostics = dict(work.get("diagnostics_summary_json") or {})
            metadata = dict(diagnostics.get("nosbook_import") or {})
            if str(metadata.get("checksum") or "") != checksum:
                continue
            return {
                "schema_version": NOSBOOK_IMPORT_RESULT_SCHEMA_VERSION,
                "import_id": str(metadata.get("import_id") or import_id),
                "work_id": work["work_id"],
                "status": "private_draft",
                "chapter_count": int(work.get("chapter_count") or 0),
                "warnings": list(warnings),
                "world_version_link_status": str(metadata.get("world_version_link_status") or world_version_link_status),
                "duplicate": True,
                "duplicate_status": "existing_private_draft",
            }
        return None

    def import_nosbook(self, envelope: Any, *, account_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id:
            raise NosbookImportError("nosbook_import_account_required", "account_id_required")
        payload = self._validate_envelope(envelope)
        checksum = self._canonical_checksum(payload)
        import_id = f"nosbook_import_{checksum[:16]}"
        warnings: List[Dict[str, Any]] = []
        work_payload = dict(payload.get("work") or {})
        source_world_version_id = str(work_payload.get("world_version_id") or "").strip()
        world_version_id = source_world_version_id or f"source_only_nosbook_{checksum[:12]}"
        world_link_status = self._world_version_link_status(source_world_version_id, warnings)

        duplicate = self._duplicate_result(
            account_id=normalized_account_id,
            checksum=checksum,
            import_id=import_id,
            world_version_link_status=world_link_status,
            warnings=warnings,
        )
        if duplicate:
            return duplicate

        chapters = list(payload["chapters"])
        title = str(work_payload.get("title") or "Imported NarrativeOS Work").strip() or "Imported NarrativeOS Work"
        imported_at = self._utcnow()
        import_metadata = {
            "schema_version": "nosbook_import_metadata/v1",
            "import_id": import_id,
            "checksum": checksum,
            "actor_id": str(actor_id or "") or None,
            "account_id": normalized_account_id,
            "imported_at": imported_at,
            "source_world_version_id": source_world_version_id or None,
            "world_version_id": world_version_id,
            "world_version_link_status": world_link_status,
            "source_route_name": str((payload.get("export_route") or {}).get("route_name") or work_payload.get("route_name") or "").strip() or None,
            "branch_map": list(payload.get("branch_map") or []),
            "choice_history": list(payload.get("choice_history") or []),
            "quality_summary": dict(payload.get("quality_summary") or {}),
            "cover": dict(payload.get("cover") or {}),
        }
        work = self.repository.save_author_work(
            {
                "world_version_id": world_version_id,
                "account_id": normalized_account_id,
                "title": title,
                "status": "draft",
                "chapter_count": len(chapters),
                "target_chapter_count": int(work_payload.get("target_chapter_count") or len(chapters) or 0),
                "branch_name": "主线",
                "branch_kind": "mainline",
                "fork_after_chapter_index": 0,
                "is_active_line": True,
                "narrative_state_json": {
                    "state_id": f"{import_id}::state",
                    "metadata": {
                        "nosbook_import": import_metadata,
                    },
                },
                "diagnostics_summary_json": {
                    "nosbook_import": import_metadata,
                    "source": "nosbook_import",
                },
            }
        )
        work = self.repository.save_author_work(
            {
                **work,
                "root_work_id": work["work_id"],
                "branch_id": work["work_id"],
                "is_active_line": True,
            }
        )
        for position, chapter in enumerate(chapters, start=1):
            chapter_index = int(chapter.get("chapter_index") or position)
            self.repository.save_author_work_chapter(
                {
                    "chapter_record_id": f"nosbook_chapter_{uuid4().hex[:12]}",
                    "work_id": work["work_id"],
                    "chapter_index": chapter_index,
                    "chapter_title": str(chapter.get("chapter_title") or f"第 {chapter_index} 章"),
                    "body": str(chapter.get("body") or ""),
                    "status": "generated",
                    "source_type": "nosbook_import",
                    "summary": str(chapter.get("summary") or ""),
                    "diagnostic_summary_json": {},
                    "chapter_task_json": {
                        "source": "nosbook_import",
                        "choice_impacts": list(chapter.get("choice_impacts") or []),
                    },
                    "choices_json": list(chapter.get("choices") or []),
                    "state_snapshot_json": {
                        "state_id": f"{import_id}::chapter::{chapter_index}",
                        "metadata": {
                            "nosbook_import_id": import_id,
                            "source_chapter_index": chapter_index,
                        },
                    },
                }
            )
        revision = self.repository.save_author_work_revision(
            {
                "work_id": work["work_id"],
                "revision_type": "nosbook_imported",
                "summary": "导入 .nosbook 为作者私有草稿",
                "snapshot_json": {
                    "nosbook_import": import_metadata,
                    "chapter_count": len(chapters),
                },
            }
        )
        self.repository.save_author_work({**work, "current_revision": revision["revision_id"], "chapter_count": len(chapters)})
        return {
            "schema_version": NOSBOOK_IMPORT_RESULT_SCHEMA_VERSION,
            "import_id": import_id,
            "work_id": work["work_id"],
            "status": "private_draft",
            "chapter_count": len(chapters),
            "warnings": warnings,
            "world_version_link_status": world_link_status,
            "duplicate": False,
            "duplicate_status": None,
        }
