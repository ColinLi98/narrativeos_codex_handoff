from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import router as auth_router
from .author import router as author_router
from .ops import router as ops_router
from .reader import router as reader_router
from ..eval.learned_training_automation import run_learned_training_automation
from ..intent import SimpleIntentParser
from ..eval.learned_shadow import default_learned_shadow_service
from ..eval.learned_reranker_shadow import default_learned_reranker_shadow_service
from ..models import EventAtom, NarrativeState, StepRecord, WorldBible, WorldRecord
from ..pipeline import plan_next_turn_from_events
from ..eval.learned_inference import LearnedInferenceService, default_learned_artifact_dir
from ..services.analytics import AnalyticsService
from ..services.auth import AuthService
from ..services.author_collaboration import AuthorCollaborationService
from ..services.async_job_adapters import (
    build_notification_sink_registry,
    build_remote_shipping_registry,
)
from ..services.async_jobs import AsyncJobService
from ..services.authoring import AuthoringService
from ..services.billing import BillingService
from ..services.data_integrity import DataIntegrityService
from ..services.governance import GovernanceService
from ..services.intent_prefill import IntentPrefillService
from ..services.monetization import MonetizationService
from ..services.observability import ObservabilityService
from ..services.ops_traceability import OpsTraceabilityService
from ..services.ops_alerting import OpsAlertingService
from ..services.ops_account_workspace import OpsAccountWorkspaceService
from ..services.ops_release_workspace import OpsReleaseWorkspaceService
from ..services.ops_navigation import OpsNavigationService
from ..services.provider_routing import ProviderRoutingService
from ..services.provider_rollout import ProviderRolloutService
from ..services.review import ReviewService
from ..services.runtime_ops import RuntimeOpsService
from ..services.sessions import SessionService
from ..services.training_signal import TrainingSignalService
from ..rendering import TemplateRenderer
from ..repository import SQLAlchemyRepository
from ..schemas import validate_payload
from ..worldpacks.registry import FileSystemWorldRegistry


BASE_DIR = Path(__file__).resolve().parents[3]
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
EXAMPLES_DIR = BASE_DIR / "examples"


def load_example_json(name: str) -> Any:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


EXAMPLE_BUNDLES = {
    "demo": {
        "label": "玉阙春闱 · Duty Route",
        "description": "偏职责与家门名誉的基础示例世界。",
        "world_bible": "demo_world_bible.json",
        "initial_state": "demo_initial_state.json",
        "event_atoms": "demo_event_atoms.json",
        "player_inputs": "demo_player_inputs.json",
    },
    "romance": {
        "label": "玉阙春闱 · Romance Route",
        "description": "偏爱情与自我抉择的变体世界。",
        "world_bible": "romance_world_bible.json",
        "initial_state": "romance_initial_state.json",
        "event_atoms": "demo_event_atoms.json",
        "player_inputs": "romance_player_inputs.json",
    },
}


def build_example_bundle(example_id: str) -> Dict[str, Any]:
    config = EXAMPLE_BUNDLES[example_id]
    return {
        "example_id": example_id,
        "label": config["label"],
        "description": config["description"],
        "world_bible": load_example_json(config["world_bible"]),
        "initial_state": load_example_json(config["initial_state"]),
        "event_atoms": load_example_json(config["event_atoms"]),
        "player_inputs": load_example_json(config["player_inputs"]),
    }


class RoutePreviewRequest(BaseModel):
    world: Dict[str, Any]
    state: Dict[str, Any]
    candidate_events: List[Dict[str, Any]]
    beam_width: int = 3
    depth: int = 2


class CreateWorldRequest(BaseModel):
    world_bible: Dict[str, Any]
    event_atoms: List[Dict[str, Any]]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    world_id: str
    initial_state: Dict[str, Any]
    player_profile: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StepRequest(BaseModel):
    player_input: str
    intent_override: Optional[Dict[str, float]] = None
    candidate_events: Optional[List[Dict[str, Any]]] = None
    beam_width: int = 3
    depth: int = 2
    metadata: Dict[str, Any] = Field(default_factory=dict)


def create_app(
    *,
    repository: Optional[SQLAlchemyRepository] = None,
    intent_parser: Optional[SimpleIntentParser] = None,
    renderer: Optional[TemplateRenderer] = None,
    candidate_backend: Any = None,
    renderer_backend: Any = None,
    llm_backend: Any = None,
    provider_routing_service: Optional[ProviderRoutingService] = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if hasattr(app.state, "async_job_service"):
            app.state.async_job_boot_reconcile = app.state.async_job_service.reconcile_on_boot(
                requested_by="boot_reconciler"
            )
        yield

    app = FastAPI(title="NarrativeOS API", version="0.3.0", lifespan=lifespan)
    app.state.base_dir = BASE_DIR
    app.state.repository = repository or SQLAlchemyRepository()
    app.state.intent_parser = intent_parser or SimpleIntentParser()
    app.state.provider_rollout_service = ProviderRolloutService(app.state.repository)
    app.state.provider_routing_service = provider_routing_service or ProviderRoutingService.from_env(
        rollout_service=app.state.provider_rollout_service,
        candidate_backend=candidate_backend,
        renderer_backend=renderer_backend,
        shared_backend=llm_backend,
        fallback_renderer=renderer or TemplateRenderer(),
    )
    app.state.candidate_backend = app.state.provider_routing_service.candidate_backend
    app.state.renderer_backend = app.state.provider_routing_service.renderer_backend
    app.state.llm_backend = app.state.candidate_backend
    app.state.renderer = app.state.provider_routing_service.build_renderer()
    app.state.world_registry = FileSystemWorldRegistry()
    app.state.monetization_service = MonetizationService(app.state.repository, base_dir=BASE_DIR)
    app.state.billing_service = BillingService(
        app.state.repository,
        monetization_service=app.state.monetization_service,
    )
    app.state.auth_service = AuthService(app.state.repository)
    app.state.analytics_service = AnalyticsService(app.state.repository)
    app.state.observability_service = ObservabilityService(app.state.repository)
    app.state.runtime_ops_service = RuntimeOpsService(
        app.state.repository,
        observability_service=app.state.observability_service,
        base_dir=BASE_DIR,
    )
    app.state.data_integrity_service = DataIntegrityService(app.state.repository)
    app.state.async_remote_shipping_registry = build_remote_shipping_registry(BASE_DIR)
    app.state.async_notification_sink_registry = build_notification_sink_registry(BASE_DIR)
    app.state.async_job_service = AsyncJobService(
        app.state.repository,
        analytics_service=app.state.analytics_service,
        base_dir=BASE_DIR,
        remote_shipping_registry=app.state.async_remote_shipping_registry,
        notification_sink_registry=app.state.async_notification_sink_registry,
    )
    app.state.runtime_ops_service.async_job_service = app.state.async_job_service
    app.state.review_service = ReviewService(app.state.repository, analytics_service=app.state.analytics_service)
    app.state.governance_service = GovernanceService(
        app.state.repository,
        billing_service=app.state.billing_service,
    )
    app.state.ops_traceability_service = OpsTraceabilityService(
        app.state.repository,
        billing_service=app.state.billing_service,
        governance_service=app.state.governance_service,
        review_service=app.state.review_service,
        observability_service=app.state.observability_service,
    )
    app.state.ops_alerting_service = OpsAlertingService(
        app.state.repository,
        billing_service=app.state.billing_service,
        governance_service=app.state.governance_service,
        observability_service=app.state.observability_service,
        runtime_ops_service=app.state.runtime_ops_service,
        async_job_service=app.state.async_job_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.ops_account_workspace_service = OpsAccountWorkspaceService(
        app.state.repository,
        billing_service=app.state.billing_service,
        governance_service=app.state.governance_service,
        ops_alerting_service=app.state.ops_alerting_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.ops_release_workspace_service = OpsReleaseWorkspaceService(
        app.state.repository,
        review_service=app.state.review_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.ops_navigation_service = OpsNavigationService(
        app.state.repository,
        account_workspace_service=app.state.ops_account_workspace_service,
        release_workspace_service=app.state.ops_release_workspace_service,
        alerting_service=app.state.ops_alerting_service,
        governance_service=app.state.governance_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.training_signal_service = TrainingSignalService(app.state.repository)
    app.state.learned_inference_service = LearnedInferenceService(default_learned_artifact_dir(BASE_DIR))
    app.state.learned_shadow_service = default_learned_shadow_service(BASE_DIR)
    app.state.learned_reranker_shadow_service = default_learned_reranker_shadow_service(BASE_DIR)
    app.state.intent_prefill_service = IntentPrefillService()
    app.state.authoring_service = AuthoringService(
        app.state.repository,
        registry=app.state.world_registry,
        training_signal_service=app.state.training_signal_service,
        learned_inference_service=app.state.learned_inference_service,
        learned_shadow_service=app.state.learned_shadow_service,
        billing_service=app.state.billing_service,
        provider_routing_service=app.state.provider_routing_service,
        observability_service=app.state.observability_service,
    )
    app.state.author_collaboration_service = AuthorCollaborationService(
        app.state.repository,
        analytics_service=app.state.analytics_service,
        async_job_service=app.state.async_job_service,
    )
    app.state.session_service = SessionService(
        app.state.repository,
        intent_parser=app.state.intent_parser,
        renderer=app.state.renderer,
        billing_service=app.state.billing_service,
        analytics_service=app.state.analytics_service,
        observability_service=app.state.observability_service,
        provider_routing_service=app.state.provider_routing_service,
    )

    def _run_learned_training_job(job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="learned_training_runner")
        result = run_learned_training_automation(
            repository=app.state.repository,
            output_dir=BASE_DIR / "artifacts" / "learned_training_runs",
            tracks=payload.get("tracks") or ["evaluator", "reranker"],
            world_id=payload.get("world_id"),
            world_version_id=payload.get("world_version_id"),
            limit=payload.get("limit"),
        )
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="learned_training_runner")
        app.state.analytics_service.track(
            "learned_training_run_completed",
            account_id=job.get("account_id"),
            payload_json={
                "job_id": job.get("job_id"),
                "summary": result.get("summary", {}),
                "artifacts": result.get("artifacts", {}),
            },
        )
        return result

    def _run_runtime_backup_job(job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="runtime_backup_runner")
        result = app.state.runtime_ops_service.create_backup(
            label=payload.get("label"),
            output_dir=payload.get("output_dir"),
            dry_run=bool(payload.get("dry_run")),
            execute_postgres=True,
            job_id=job.get("job_id"),
        )
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="runtime_backup_runner")
        app.state.analytics_service.track(
            "runtime_backup_created",
            account_id=job.get("account_id"),
            payload_json={
                **result,
                "job_id": job.get("job_id"),
            },
        )
        return result

    def _run_runtime_restore_job(job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="runtime_restore_runner")
        result = app.state.runtime_ops_service.execute_restore_request(
            request_id=str(payload.get("request_id") or ""),
            job_id=job.get("job_id"),
            requested_by=payload.get("requested_by") or job.get("requested_by"),
        )
        app.state.async_job_service.heartbeat_job(job["job_id"], requested_by="runtime_restore_runner")
        app.state.analytics_service.track(
            "runtime_restore_executed" if result.get("_job_status_override") != "failed" else "runtime_restore_failed",
            account_id=job.get("account_id"),
            payload_json={
                **result,
                "job_id": job.get("job_id"),
            },
        )
        return result

    app.state.async_job_service.register_runner("learned_training", _run_learned_training_job)
    app.state.async_job_service.register_runner("runtime_backup", _run_runtime_backup_job)
    app.state.async_job_service.register_runner("runtime_restore", _run_runtime_restore_job)
    app.state.async_job_boot_reconcile = None

    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
    app.include_router(reader_router)
    app.include_router(auth_router)
    app.include_router(author_router)
    app.include_router(ops_router)

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/app")

    @app.get("/app")
    def app_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/examples/demo")
    def demo_bundle() -> Dict[str, Any]:
        return build_example_bundle("demo")

    @app.get("/v1/examples")
    def list_examples() -> Dict[str, Any]:
        return {
            "examples": [
                {
                    "example_id": example_id,
                    "label": config["label"],
                    "description": config["description"],
                    "world_id": load_example_json(config["world_bible"])["world_id"],
                }
                for example_id, config in EXAMPLE_BUNDLES.items()
            ]
        }

    @app.get("/v1/examples/{example_id}")
    def get_example(example_id: str) -> Dict[str, Any]:
        if example_id not in EXAMPLE_BUNDLES:
            raise HTTPException(status_code=404, detail="unknown_example:%s" % example_id)
        return build_example_bundle(example_id)

    @app.get("/v1/library/worlds")
    def list_library_worlds() -> Dict[str, Any]:
        return {"worlds": app.state.repository.list_worlds()}

    @app.get("/v1/library/worlds/{world_id}")
    def get_library_world(world_id: str) -> Dict[str, Any]:
        versions = app.state.repository.list_world_versions(world_id=world_id)
        if not versions:
            raise HTTPException(status_code=404, detail="unknown_world:%s" % world_id)
        published = next((item for item in versions if item["status"] == "published"), versions[0])
        version = app.state.repository.get_world_version(published["world_version_id"])
        return {
            "world_id": world_id,
            "title": version.worldpack_json.get("title", world_id),
            "world_version_id": version.world_version_id,
            "manifest": version.manifest_json,
            "risk_policy": version.worldpack_json.get("risk_policy", {}),
            "worldpack": version.worldpack_json,
            "versions": versions,
        }

    @app.get("/v1/worlds")
    def list_worlds() -> Dict[str, Any]:
        return {"worlds": app.state.repository.list_worlds()}

    @app.post("/v1/worlds")
    def create_world(payload: CreateWorldRequest) -> Dict[str, Any]:
        try:
            validate_payload(payload.world_bible, "world_bible.schema.json")
            for event_atom in payload.event_atoms:
                validate_payload(event_atom, "event_atom.schema.json")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid_world_payload:%s" % exc)

        world_record = WorldRecord(
            world=WorldBible.from_dict(payload.world_bible),
            event_atoms=[EventAtom.from_dict(item) for item in payload.event_atoms],
            metadata=dict(payload.metadata),
        )
        app.state.repository.create_world(world_record)
        return {"world_id": world_record.world.world_id}

    @app.post("/v1/sessions")
    def create_session(payload: CreateSessionRequest) -> Dict[str, Any]:
        try:
            validate_payload(payload.initial_state, "narrative_state.schema.json")
            initial_state = NarrativeState.from_dict(payload.initial_state)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid_initial_state:%s" % exc)

        if initial_state.world_id != payload.world_id:
            raise HTTPException(status_code=400, detail="world_id_mismatch")

        try:
            app.state.repository.get_world(payload.world_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        session_record = app.state.repository.create_session(
            payload.world_id,
            initial_state,
            player_profile=payload.player_profile,
            metadata={"reader_id": payload.player_profile.get("reader_id"), **payload.metadata},
        )
        access = app.state.billing_service.access_check(session_record.session_id, reader_id=payload.player_profile.get("reader_id"))
        snapshot = {
            "access_tier": access.get("access_tier"),
            "reason": access.get("reason"),
            "quote": access.get("quote"),
            "entitlement_type": access.get("entitlement_type"),
            "balance": access.get("balance"),
            "status": access.get("status"),
        }
        app.state.repository.update_session_entitlements_snapshot(session_record.session_id, snapshot)
        app.state.analytics_service.track(
            "session_created",
            reader_id=payload.player_profile.get("reader_id"),
            session_id=session_record.session_id,
            world_id=payload.world_id,
            world_version_id=session_record.metadata.get("world_version_id"),
            access_tier=access.get("access_tier"),
            payload_json=snapshot,
        )
        return {
            "session_id": session_record.session_id,
            "reader_id": payload.player_profile.get("reader_id"),
            "world_version_id": session_record.metadata.get("world_version_id"),
            "current_state": session_record.current_state.to_dict(),
            "paywall": access,
        }

    @app.get("/v1/sessions")
    def list_sessions(world_id: Optional[str] = None) -> Dict[str, Any]:
        return {"sessions": app.state.repository.list_sessions(world_id=world_id)}

    @app.get("/v1/sessions/{session_id}")
    def get_session(session_id: str) -> Dict[str, Any]:
        try:
            session_record = app.state.repository.get_session(session_id)
            latest_step = app.state.repository.get_latest_step(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {
            "session": session_record.to_dict(),
            "latest_step": latest_step.to_dict() if latest_step else None,
            "world_version_id": session_record.metadata.get("world_version_id"),
            "paywall": app.state.billing_service.access_check(session_id, reader_id=session_record.metadata.get("reader_id")),
            "entitlements_snapshot": session_record.metadata.get("entitlements_snapshot", {}),
            "intent_prefill": app.state.intent_prefill_service.build(session_record, latest_step).to_dict(),
        }

    @app.delete("/v1/sessions/{session_id}")
    def delete_session(session_id: str) -> Dict[str, Any]:
        try:
            return app.state.repository.delete_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/v1/routes/preview")
    def route_preview(payload: RoutePreviewRequest) -> Dict[str, Any]:
        try:
            world = WorldBible.from_dict(payload.world)
            state = NarrativeState.from_dict(payload.state)
            candidate_events = [EventAtom.from_dict(item) for item in payload.candidate_events]
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid_preview_payload:%s" % exc)

        return plan_next_turn_from_events(
            state,
            candidate_events,
            world=world,
            beam_width=payload.beam_width,
            depth=payload.depth,
            renderer=app.state.provider_routing_service.build_renderer(
                surface="route_preview",
                world_id=world.world_id,
            ),
            debug=True,
        )

    @app.post("/v1/sessions/{session_id}/step")
    def step_session(
        session_id: str,
        payload: StepRequest,
        debug: bool = False,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            session_record = app.state.repository.get_session(session_id)
            world_record = app.state.repository.get_world(session_record.world_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        reader_id = None
        if payload.metadata:
            reader_id = payload.metadata.get("reader_id")
        reader_id = reader_id or session_record.metadata.get("reader_id") or session_record.player_profile.get("reader_id")
        access = app.state.billing_service.access_check(session_id, reader_id=reader_id)
        if access["required"]:
            latest_step = app.state.repository.get_latest_step(session_id)
            snapshot = {
                "access_tier": access.get("access_tier"),
                "reason": access.get("reason"),
                "quote": access.get("quote"),
                "entitlement_type": access.get("entitlement_type"),
                "balance": access.get("balance"),
                "status": access.get("status"),
            }
            app.state.repository.update_session_entitlements_snapshot(session_id, snapshot)
            blocked_status = "restricted" if access.get("reason") == "manual_restriction_active" else "payment_required"
            blocked_event = "governance_restriction_blocked" if blocked_status == "restricted" else "payment_required"
            app.state.analytics_service.track(
                blocked_event,
                reader_id=reader_id,
                session_id=session_id,
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
                access_tier=access.get("access_tier"),
                payload_json=snapshot,
            )
            app.state.observability_service.record_runtime_receipt(
                surface="session_api",
                action="step_session",
                response_status=blocked_status,
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
                session_id=session_id,
                account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                reader_id=reader_id,
                estimated_cost=0.0,
            )
            return {
                "status": blocked_status,
                "world_version_id": session_record.metadata.get("world_version_id"),
                "reader_view": latest_step.reader_view.to_dict() if latest_step and latest_step.reader_view else None,
                "updated_state_summary": None,
                "replay_preview": None,
                "paywall": access,
            }

        state_before = NarrativeState.from_dict(session_record.current_state.to_dict())
        state_before.player_intent = app.state.intent_parser.parse(
            payload.player_input,
            overrides=payload.intent_override,
        )

        if payload.candidate_events:
            candidate_events = [EventAtom.from_dict(item) for item in payload.candidate_events]
            started = perf_counter()
            result = plan_next_turn_from_events(
                state_before,
                candidate_events,
                world=world_record.world,
                beam_width=payload.beam_width,
                depth=payload.depth,
                renderer=app.state.provider_routing_service.build_renderer(
                    surface="session_api",
                    account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                    session_id=session_id,
                    world_id=world_record.world.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                ),
                debug=True,
            )
        else:
            provider = app.state.provider_routing_service.build_candidate_provider(
                world_record.event_atoms,
                surface="session_api",
                account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                session_id=session_id,
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
            )
            from ..pipeline import plan_next_turn

            started = perf_counter()
            result = plan_next_turn(
                state_before,
                world=world_record.world,
                candidate_provider=provider,
                beam_width=payload.beam_width,
                depth=payload.depth,
                renderer=app.state.provider_routing_service.build_renderer(
                    surface="session_api",
                    account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                    session_id=session_id,
                    world_id=world_record.world.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                ),
                debug=True,
            )
        runtime_latency_ms = round((perf_counter() - started) * 1000.0, 3)

        chosen_event = EventAtom.from_dict(result["chosen_event"]) if result.get("chosen_event") else None
        state_after = (
            NarrativeState.from_dict(result["updated_state"])
            if result.get("updated_state")
            else session_record.current_state
        )
        step_record = StepRecord.from_dict(
            {
                "session_id": session_id,
                "step_index": state_after.chapter_index if result["status"] == "ok" else session_record.current_state.chapter_index,
                "player_input": payload.player_input,
                "intent_vector": dict(state_before.player_intent),
                "candidate_batch": result.get("candidate_batch", {"raw_candidates": [], "legal_candidates": [], "illegal_candidate_reasons": {}, "debug": {}}),
                "scored_candidates": result.get("scored_candidates", []),
                "routes": result.get("routes", []),
                "chosen_event": chosen_event.to_dict() if chosen_event else None,
                "chapter_plan": result.get("chapter_plan"),
                "scene_beats": result.get("scene_beats", []),
                "scene_render_spec": result.get("scene_render_spec"),
                "rendered_scene": result.get("rendered_scene"),
                "reader_view": result.get("reader_view"),
                "state_before": state_before.to_dict(),
                "state_after": state_after.to_dict(),
                "critic_trace": result.get("critic_trace", []),
                "promise_ledger_snapshot": [promise.to_dict() for promise in state_after.open_promises],
                "metadata": payload.metadata,
            }
        )
        consumed_access = app.state.billing_service.consume_entitlement(session_id, reader_id=reader_id, access=access)
        if result["status"] == "ok":
            snapshot = {
                "access_tier": consumed_access.get("access_tier"),
                "reason": consumed_access.get("reason"),
                "quote": consumed_access.get("quote"),
                "balance": consumed_access.get("balance"),
                "entitlement_type": consumed_access.get("entitlement_type"),
                "status": consumed_access.get("status"),
            }
            app.state.repository.save_step(
                step_record,
                entitlements_snapshot=snapshot,
                cost_estimate=round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3),
            )
            app.state.repository.update_session_entitlements_snapshot(session_id, snapshot)
            app.state.billing_service.meter_action(
                surface="reader",
                action_name="continue_story",
                account_id=consumed_access.get("account_id") or app.state.billing_service.resolve_account_id(reader_id=reader_id),
                reader_id=reader_id,
                session_id=session_id,
                chapter_id="chapter_%s_%s" % (session_id, step_record.step_index),
                world_version_id=session_record.metadata.get("world_version_id"),
                access=consumed_access,
                charged_units=None if consumed_access.get("reason") == "credits_consumed" else 0.0,
                estimated_cost=0.0,
            )
            app.state.analytics_service.track(
                "continue_story",
                reader_id=reader_id,
                session_id=session_id,
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
                chapter_index=step_record.step_index,
                access_tier=consumed_access.get("access_tier"),
                payload_json=snapshot,
            )
            if consumed_access.get("reason") == "credits_consumed":
                app.state.analytics_service.track(
                    "credits_consumed",
                    reader_id=reader_id,
                    session_id=session_id,
                    world_id=world_record.world.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                    chapter_index=step_record.step_index,
                    access_tier=consumed_access.get("access_tier"),
                    payload_json=snapshot,
                )
        paywall = consumed_access if result["status"] == "ok" else access
        if result["status"] == "ok":
            app.state.observability_service.record_runtime_receipt(
                surface="session_api",
                action="step_session",
                response_status="ok",
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
                session_id=session_id,
                account_id=consumed_access.get("account_id") or app.state.billing_service.resolve_account_id(reader_id=reader_id),
                reader_id=reader_id,
                candidate_batch=result.get("candidate_batch"),
                rendered_scene=result.get("rendered_scene"),
                reader_view=result.get("reader_view"),
                estimated_cost=round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3),
                runtime_latency_ms=runtime_latency_ms,
            )
        else:
            app.state.observability_service.record_runtime_receipt(
                surface="session_api",
                action="step_session",
                response_status=str(result["status"]),
                world_id=world_record.world.world_id,
                world_version_id=session_record.metadata.get("world_version_id"),
                session_id=session_id,
                account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                reader_id=reader_id,
                candidate_batch=result.get("candidate_batch"),
                rendered_scene=result.get("rendered_scene"),
                reader_view=result.get("reader_view"),
                estimated_cost=0.0,
                runtime_latency_ms=runtime_latency_ms,
            )
        base_response = {
            "status": result["status"],
            "world_version_id": session_record.metadata.get("world_version_id"),
            "reader_view": result.get("reader_view"),
            "updated_state_summary": result.get("updated_state_summary"),
            "replay_preview": result.get("replay_preview"),
            "paywall": paywall,
        }
        if debug or mode == "debug":
            base_response.update(
                {
                    "chosen_event": result.get("chosen_event"),
                    "updated_state": result.get("updated_state"),
                    "scored_candidates": result.get("scored_candidates"),
                    "critic_trace": result.get("critic_trace"),
                    "rendered_scene": result.get("rendered_scene"),
                    "candidate_batch": result.get("candidate_batch"),
                    "routes": result.get("routes"),
                    "chapter_plan": result.get("chapter_plan"),
                    "scene_beats": result.get("scene_beats"),
                    "scene_render_spec": result.get("scene_render_spec"),
                }
            )
        return base_response

    @app.get("/v1/sessions/{session_id}/replay")
    def replay_session(session_id: str) -> Dict[str, Any]:
        try:
            return app.state.repository.get_replay(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/v1/sessions/{session_id}/prefill")
    def session_prefill(session_id: str) -> Dict[str, Any]:
        try:
            session_record = app.state.repository.get_session(session_id)
            latest_step = app.state.repository.get_latest_step(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return app.state.intent_prefill_service.build(session_record, latest_step).to_dict()

    return app


app = create_app()
