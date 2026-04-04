from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api.author import router as author_router
from .api.ops import router as ops_router
from .api.reader import router as reader_router
from .intent import SimpleIntentParser
from .models import EventAtom, NarrativeState, StepRecord, WorldBible, WorldRecord
from .pipeline import plan_next_turn_from_events
from .providers import LLMCandidateProvider, StaticCandidateProvider
from .services.analytics import AnalyticsService
from .services.authoring import AuthoringService
from .services.billing import BillingService
from .services.review import ReviewService
from .services.sessions import SessionService
from .rendering import TemplateRenderer
from .repository import SQLAlchemyRepository
from .schemas import validate_payload
from .worldpacks.registry import FileSystemWorldRegistry


BASE_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = Path(__file__).resolve().parent / "web"
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
    llm_backend: Any = None,
) -> FastAPI:
    app = FastAPI(title="NarrativeOS API", version="0.3.0")
    app.state.repository = repository or SQLAlchemyRepository()
    app.state.intent_parser = intent_parser or SimpleIntentParser()
    app.state.renderer = renderer or TemplateRenderer()
    app.state.llm_backend = llm_backend
    app.state.world_registry = FileSystemWorldRegistry()
    app.state.billing_service = BillingService(app.state.repository)
    app.state.analytics_service = AnalyticsService(app.state.repository)
    app.state.review_service = ReviewService(app.state.repository)
    app.state.authoring_service = AuthoringService(app.state.repository, registry=app.state.world_registry)
    app.state.session_service = SessionService(
        app.state.repository,
        intent_parser=app.state.intent_parser,
        renderer=app.state.renderer,
        billing_service=app.state.billing_service,
        analytics_service=app.state.analytics_service,
    )
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
    app.include_router(reader_router)
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
            metadata=payload.metadata,
        )
        return {
            "session_id": session_record.session_id,
            "current_state": session_record.current_state.to_dict(),
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
            renderer=app.state.renderer,
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

        state_before = NarrativeState.from_dict(session_record.current_state.to_dict())
        state_before.player_intent = app.state.intent_parser.parse(
            payload.player_input,
            overrides=payload.intent_override,
        )

        if payload.candidate_events:
            candidate_events = [EventAtom.from_dict(item) for item in payload.candidate_events]
            result = plan_next_turn_from_events(
                state_before,
                candidate_events,
                world=world_record.world,
                beam_width=payload.beam_width,
                depth=payload.depth,
                renderer=app.state.renderer,
                debug=True,
            )
        else:
            static_provider = StaticCandidateProvider(world_record.event_atoms)
            provider = static_provider
            if app.state.llm_backend is not None:
                provider = LLMCandidateProvider(app.state.llm_backend, static_provider)
            from .pipeline import plan_next_turn

            result = plan_next_turn(
                state_before,
                world=world_record.world,
                candidate_provider=provider,
                beam_width=payload.beam_width,
                depth=payload.depth,
                renderer=app.state.renderer,
                debug=True,
            )

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
        if result["status"] == "ok":
            app.state.repository.save_step(step_record)
        base_response = {
            "status": result["status"],
            "reader_view": result.get("reader_view"),
            "updated_state_summary": result.get("updated_state_summary"),
            "replay_preview": result.get("replay_preview"),
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

    return app


app = create_app()
