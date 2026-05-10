from __future__ import annotations

from typing import Any, Dict, Optional

from .analytics import AnalyticsService
from .sessions import ReaderContinueCommand, SessionService


READER_GENERATION_JOB_TYPE = "reader_generation"


def compact_reader_generation_result(result: Dict[str, Any]) -> Dict[str, Any]:
    operation = str(result.get("operation") or "")
    reader_result = dict(result.get("reader_result") or {})
    chapter_view = dict(reader_result.get("chapter_view") or {})
    reader_view = dict(reader_result.get("reader_view") or {})
    chapter_index = chapter_view.get("chapterIndex")
    if chapter_index is None:
        updated_state = reader_result.get("updated_state")
        if isinstance(updated_state, dict):
            chapter_index = updated_state.get("chapter_index")
    chapter_title = chapter_view.get("chapterTitle") or reader_view.get("chapter_title")
    summary = {
        "operation": operation,
        "session_id": result.get("session_id") or reader_result.get("session_id"),
        "world_id": result.get("world_id") or reader_result.get("world_id"),
        "world_version_id": result.get("world_version_id") or reader_result.get("world_version_id"),
        "reader_id": result.get("reader_id") or reader_result.get("reader_id"),
        "reader_status": str(reader_result.get("status") or result.get("reader_status") or "ok"),
        "chapter": {
            "chapter_id": chapter_view.get("chapterId"),
            "chapter_index": chapter_index,
            "chapter_title": chapter_title,
        },
        "paywall": reader_result.get("paywall"),
        "quality_gate": reader_result.get("quality_gate"),
        "continuity_contract": reader_result.get("continuity_contract"),
        "quality_trace_id": reader_result.get("quality_trace_id"),
        "bootstrap_attempts": result.get("bootstrap_attempts"),
        "final_intent": result.get("final_intent"),
    }
    return {key: value for key, value in summary.items() if value is not None}


class ReaderGenerationJobRunner:
    def __init__(
        self,
        *,
        repository: Any,
        session_service: SessionService,
        analytics_service: Optional[AnalyticsService] = None,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.analytics = analytics_service

    def run(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        operation = str(payload.get("operation") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        reader_id = str(payload.get("reader_id") or "").strip() or None
        if not session_id:
            return {
                "_job_status_override": "failed",
                "operation": operation,
                "session_id": session_id,
                "error": "reader_generation_session_required",
            }
        if operation == "story_import_bootstrap":
            return self._run_bootstrap(session_id=session_id, reader_id=reader_id, operation=operation)
        if operation in {"reader_continue", "story_choice"}:
            return self._run_continue(
                operation=operation,
                session_id=session_id,
                reader_id=reader_id,
                choice_id=payload.get("choice_id"),
                freeform_intent=payload.get("freeform_intent"),
                steering_directive=payload.get("steering_directive"),
            )
        return {
            "_job_status_override": "failed",
            "operation": operation,
            "session_id": session_id,
            "reader_id": reader_id,
            "error": f"unsupported_reader_generation_operation:{operation or 'missing'}",
        }

    def _track(self, event_name: str, **kwargs: Any) -> None:
        if self.analytics is None:
            return
        self.analytics.track(event_name, **kwargs)

    def _run_bootstrap(self, *, session_id: str, reader_id: Optional[str], operation: str) -> Dict[str, Any]:
        session_record = self.repository.get_session(session_id)
        world_version_id = str((session_record.metadata or {}).get("world_version_id") or "")
        world_version = self.repository.get_world_version(world_version_id)
        intents = [
            "进入故事。",
            "更稳地进入故事。",
            "先从眼前局势切入。",
        ]
        latest_result: Dict[str, Any] = {}
        first_attempt_status: Optional[str] = None
        final_intent = intents[0]
        attempts = []
        for attempt_index, intent in enumerate(intents, start=1):
            final_intent = intent
            self._track(
                "story_import_bootstrap_attempted",
                reader_id=reader_id,
                session_id=session_id,
                world_id=world_version.world_id,
                world_version_id=world_version_id,
                payload_json={
                    "attempt_index": attempt_index,
                    "bootstrap_intent": intent,
                    "async_job": True,
                },
            )
            latest_result = self.session_service.continue_story(
                ReaderContinueCommand(session_id=session_id, freeform_intent=intent),
                reader_id=reader_id,
            )
            status = str(latest_result.get("status") or "")
            attempts.append({"attempt_index": attempt_index, "intent": intent, "status": status})
            if first_attempt_status is None:
                first_attempt_status = status
            if status == "quality_guard_failed" and intent != intents[-1]:
                self._track(
                    "story_import_bootstrap_retry_applied",
                    reader_id=reader_id,
                    session_id=session_id,
                    world_id=world_version.world_id,
                    world_version_id=world_version_id,
                    payload_json={
                        "attempt_index": attempt_index,
                        "bootstrap_intent": intent,
                        "result_status": status,
                        "recovered_after_retry": False,
                        "async_job": True,
                    },
                )
            if status != "quality_guard_failed":
                break
        final_status = str(latest_result.get("status") or "")
        self._track(
            "story_import_bootstrap_completed",
            reader_id=reader_id,
            session_id=session_id,
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            payload_json={
                "attempt_index": len(attempts),
                "bootstrap_intent": final_intent,
                "first_attempt_result_status": first_attempt_status or final_status,
                "result_status": final_status,
                "recovered_after_retry": (
                    first_attempt_status == "quality_guard_failed" and final_status != "quality_guard_failed"
                ),
                "async_job": True,
            },
        )
        return {
            "operation": operation,
            "session_id": session_id,
            "reader_id": reader_id,
            "world_id": world_version.world_id,
            "world_version_id": world_version_id,
            "reader_status": final_status or "ok",
            "reader_result": latest_result,
            "bootstrap_attempts": attempts,
            "final_intent": final_intent,
        }

    def _run_continue(
        self,
        *,
        operation: str,
        session_id: str,
        reader_id: Optional[str],
        choice_id: Any = None,
        freeform_intent: Any = None,
        steering_directive: Any = None,
    ) -> Dict[str, Any]:
        result = self.session_service.continue_story(
            ReaderContinueCommand(
                session_id=session_id,
                choice_id=str(choice_id).strip() if choice_id else None,
                freeform_intent=str(freeform_intent).strip() if freeform_intent else None,
                steering_directive=dict(steering_directive or {}) if isinstance(steering_directive, dict) else None,
            ),
            reader_id=reader_id,
        )
        return {
            "operation": operation,
            "session_id": session_id,
            "reader_id": reader_id,
            "world_id": result.get("world_id"),
            "world_version_id": result.get("world_version_id"),
            "reader_status": str(result.get("status") or "ok"),
            "reader_result": result,
        }
