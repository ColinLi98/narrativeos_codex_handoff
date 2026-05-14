from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import threading
from time import perf_counter
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import router as auth_router
from .billing_provider import router as billing_provider_router
from .quantum_compat import router as quantum_compat_router
from .author import ensure_author_collaboration_access, router as author_router
from .customer import router as customer_router
from .ops import ensure_ops_read_access, ensure_ops_write_access, router as ops_router
from .reader import router as reader_router
from .reader_access import ensure_reader_session_access, reader_identity, reader_identity_account_id
from ..core.linter import lint_chapter_draft
from ..eval.learned_training_automation import run_learned_training_automation
from ..intent import SimpleIntentParser
from ..eval.learned_shadow import default_learned_shadow_service
from ..eval.learned_reranker_shadow import default_learned_reranker_shadow_service
from ..models import EventAtom, NarrativeState, StepRecord, WorldBible, WorldRecord
from ..pipeline import plan_next_turn_from_events
from ..eval.learned_inference import LearnedInferenceService, default_learned_artifact_dir
from ..eval.service import evaluate_persisted_chapter
from ..long_route_quality import apply_long_route_quality_controls
from ..quality.adapter import enforce_grounding_quality_gate
from ..quality.hard_constraints import enforce_generation_hard_constraints
from ..quality.grounding import build_grounding_check
from ..services.analytics import AnalyticsService
from ..services.auth import AuthService
from ..services.emailing import EmailService
from ..services.author_collaboration import AuthorCollaborationService
from ..services.author_project_graph import AuthorProjectGraphService
from ..services.author_permissions import AuthorPermissionPolicyService
from ..services.author_work import AuthorWorkService
from ..services.async_job_adapters import (
    build_notification_sink_registry,
    build_remote_shipping_registry,
)
from ..services.async_jobs import AsyncJobService
from ..services.authoring import AuthoringService
from ..services.billing import BillingService
from ..services.commercial_billing import CommercialBillingService
from ..services.commercial_audit import CommercialAuditService
from ..services.commercial_lifecycle_automation import CommercialLifecycleAutomationService
from ..services.commercial_support import CommercialSupportService
from ..services.customer_accounts import CustomerAccountService
from ..services.customer_campaigns import CustomerCampaignService
from ..services.customer_success_reporting import CustomerSuccessReportingService
from ..services.customer_workspace import CustomerWorkspaceService
from ..services.data_integrity import DataIntegrityService
from ..services.governance import GovernanceService
from ..services.go_live_day_runner import GoLiveDayRunnerService
from ..services.human_signoff_closure import HumanSignoffClosureService
from ..services.intent_prefill import IntentPrefillService
from ..services.illustration import ILLUSTRATION_JOB_TYPE, IllustrationService
from ..services.library_stats_cube import LibraryStatsCubeService
from ..services.library_stats_cube_projection import (
    LIBRARY_STATS_INVALIDATION_EVENTS,
    LibraryStatsCubeProjectionService,
)
from ..services.library_stats_semantic_layer import LibraryStatsSemanticLayerService
from ..services.launch_week_guard import LaunchWeekGuardService
from ..services.launch_week_monitoring import LaunchWeekMonitoringService
from ..services.monetization import MonetizationService
from ..services.observability import ObservabilityService
from ..services.ops_traceability import OpsTraceabilityService
from ..services.ops_alerting import OpsAlertingService
from ..services.ops_commercialization_dashboard import OpsCommercializationDashboardService
from ..services.ops_account_workspace import OpsAccountWorkspaceService
from ..services.ops_release_workspace import OpsReleaseWorkspaceService
from ..services.ops_navigation import OpsNavigationService
from ..services.ops_quality_projection import OpsQualityProjectionService
from ..services.ops_review_hub import OpsReviewHubService
from ..services.ops_permissions import OpsPermissionPolicyService
from ..services.partner_readiness import PartnerReadinessService
from ..services.production_acceptance import ProductionAcceptanceService
from ..services.production_preflight import ProductionPreflightService
from ..services.production_signoff_board import ProductionSignoffBoardService
from ..services.production_handshake_pack import ProductionHandshakePackService
from ..services.production_launch_ledger import ProductionLaunchLedgerService
from ..services.production_launch_week_pack import ProductionLaunchWeekPackService
from ..services.production_signoff import ProductionSignoffService
from ..services.quantum_read_models import QuantumReadModelService
from ..services.launch_command_center import LaunchCommandCenterService
from ..services.wave_activation_controller import WaveActivationControllerService
from ..services.stripe_invoicing import StripeInvoicingService
from ..services.provider_routing import ProviderRoutingService
from ..services.provider_rollout import ProviderRolloutService
from ..services.review import ReviewService
from ..services.runtime_ops import RuntimeOpsService
from ..services.reader_generation_jobs import READER_GENERATION_JOB_TYPE, ReaderGenerationJobRunner
from ..services.sessions import SessionService, build_reader_continuity_contract
from ..services.training_signal import TrainingSignalService
from ..rendering import TemplateRenderer
from ..repository import SQLAlchemyRepository
from ..sanitizer import sanitize_reader_visible_payload
from ..schemas import validate_payload
from ..worldpacks.registry import FileSystemWorldRegistry


BASE_DIR = Path(__file__).resolve().parents[3]
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
DEFAULT_MODERN_FRONTEND_DIST_DIR = BASE_DIR / "Kimi_Agent_设计系统加载" / "app" / "dist"
EXAMPLES_DIR = BASE_DIR / "examples"

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers.update(NO_CACHE_HEADERS)
        return response


class FallbackNoCacheStaticFiles(NoCacheStaticFiles):
    def __init__(self, *, directory: Path, fallback_directory: Optional[Path] = None):
        super().__init__(directory=directory)
        self._fallback_static = (
            NoCacheStaticFiles(directory=fallback_directory)
            if fallback_directory and fallback_directory != directory and fallback_directory.is_dir()
            else None
        )

    async def get_response(self, path: str, scope: Dict[str, Any]):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404 and self._fallback_static is not None:
                return await self._fallback_static.get_response(path, scope)
            raise


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


def _env_flag(name: str) -> Optional[bool]:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _modern_frontend_enabled() -> bool:
    configured = _env_flag("NARRATIVEOS_SERVE_MODERN_FRONTEND")
    if configured is not None:
        return configured
    return bool(os.getenv("VERCEL"))


def _modern_frontend_dist_dir() -> Path:
    configured = str(os.getenv("NARRATIVEOS_FRONTEND_DIST_DIR", "") or "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MODERN_FRONTEND_DIST_DIR


def _frontend_static_file(frontend_path: str) -> Optional[Path]:
    dist_dir = _modern_frontend_dist_dir().resolve()
    candidate = (dist_dir / frontend_path).resolve()
    if candidate.is_file() and (candidate == dist_dir or dist_dir in candidate.parents):
        return candidate
    return None


def _is_modern_frontend_route(frontend_path: str) -> bool:
    first_segment = frontend_path.strip("/").split("/", 1)[0]
    return first_segment in {
        "",
        "author",
        "library",
        "ops",
        "settings",
        "showcase",
        "soul",
        "story",
        "studio",
        "welcome",
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
    longform_setup: Dict[str, Any] = Field(default_factory=dict)


class StepRequest(BaseModel):
    player_input: str
    intent_override: Optional[Dict[str, float]] = None
    steering_directive: Optional[Dict[str, Any]] = None
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
    app.state.customer_account_service = CustomerAccountService(
        app.state.repository,
        billing_service=app.state.billing_service,
    )
    app.state.commercial_audit_service = CommercialAuditService(
        app.state.repository,
        customer_account_service=app.state.customer_account_service,
    )
    app.state.commercial_audit_service.sync_default_retention_policies()
    app.state.email_service = EmailService()
    app.state.auth_service = AuthService(app.state.repository, email_service=app.state.email_service)
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
    def _schedule_async_job_thread(target, job_id: str) -> None:
        thread = threading.Thread(target=target, args=(job_id,), daemon=True)
        thread.start()

    reader_job_threads_env = os.getenv("NARRATIVEOS_READER_JOB_BACKGROUND_THREADS")
    reader_job_threads_enabled = (
        str(reader_job_threads_env).strip().lower() in {"1", "true", "yes", "on"}
        if reader_job_threads_env is not None
        else str(os.getenv("VERCEL") or "").strip().lower() not in {"1", "true"}
    )
    app.state.reader_generation_job_scheduler = _schedule_async_job_thread if reader_job_threads_enabled else None
    app.state.illustration_service = IllustrationService(
        app.state.repository,
        analytics_service=app.state.analytics_service,
        async_job_service=app.state.async_job_service,
        job_scheduler=_schedule_async_job_thread,
    )
    app.state.ops_quality_projection_service = OpsQualityProjectionService(app.state.repository)
    app.state.launch_week_monitoring_service = LaunchWeekMonitoringService(
        app.state.repository,
        observability_service=app.state.observability_service,
        async_job_service=app.state.async_job_service,
        quality_projection_service=app.state.ops_quality_projection_service,
        base_dir=BASE_DIR,
    )
    app.state.commercial_billing_service = CommercialBillingService(
        app.state.repository,
        billing_service=app.state.billing_service,
        customer_account_service=app.state.customer_account_service,
        audit_service=app.state.commercial_audit_service,
        observability_service=app.state.observability_service,
        quality_projection_service=app.state.ops_quality_projection_service,
    )
    app.state.commercial_audit_service.commercial_billing = app.state.commercial_billing_service
    app.state.stripe_invoicing_service = StripeInvoicingService(
        app.state.repository,
        monetization_service=app.state.monetization_service,
        billing_service=app.state.billing_service,
        customer_account_service=app.state.customer_account_service,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.commercial_support_service = CommercialSupportService(
        app.state.repository,
        customer_account_service=app.state.customer_account_service,
        commercial_billing_service=app.state.commercial_billing_service,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.customer_campaign_service = CustomerCampaignService(
        app.state.repository,
        customer_account_service=app.state.customer_account_service,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.partner_readiness_service = PartnerReadinessService(
        app.state.repository,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.commercial_lifecycle_automation_service = CommercialLifecycleAutomationService(
        app.state.repository,
        customer_account_service=app.state.customer_account_service,
        customer_campaign_service=app.state.customer_campaign_service,
        commercial_billing_service=app.state.commercial_billing_service,
        commercial_support_service=app.state.commercial_support_service,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.customer_workspace_service = CustomerWorkspaceService(
        customer_account_service=app.state.customer_account_service,
        customer_campaign_service=app.state.customer_campaign_service,
        partner_readiness_service=app.state.partner_readiness_service,
        commercial_billing_service=app.state.commercial_billing_service,
        commercial_support_service=app.state.commercial_support_service,
        commercial_audit_service=app.state.commercial_audit_service,
        commercial_lifecycle_automation_service=app.state.commercial_lifecycle_automation_service,
        quality_projection_service=app.state.ops_quality_projection_service,
        observability_service=app.state.observability_service,
    )
    app.state.review_service = ReviewService(
        app.state.repository,
        analytics_service=app.state.analytics_service,
        quality_projection_service=app.state.ops_quality_projection_service,
    )
    app.state.governance_service = GovernanceService(
        app.state.repository,
        billing_service=app.state.billing_service,
        audit_service=app.state.commercial_audit_service,
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
        audit_service=app.state.commercial_audit_service,
    )
    app.state.ops_account_workspace_service = OpsAccountWorkspaceService(
        app.state.repository,
        billing_service=app.state.billing_service,
        customer_account_service=app.state.customer_account_service,
        governance_service=app.state.governance_service,
        ops_alerting_service=app.state.ops_alerting_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.ops_release_workspace_service = OpsReleaseWorkspaceService(
        app.state.repository,
        review_service=app.state.review_service,
        ops_traceability_service=app.state.ops_traceability_service,
        quality_projection_service=app.state.ops_quality_projection_service,
    )
    app.state.ops_commercialization_dashboard_service = OpsCommercializationDashboardService(
        app.state.repository,
        customer_account_service=app.state.customer_account_service,
        commercial_support_service=app.state.commercial_support_service,
        partner_readiness_service=app.state.partner_readiness_service,
        commercial_lifecycle_automation_service=app.state.commercial_lifecycle_automation_service,
        launch_week_monitoring_service=app.state.launch_week_monitoring_service,
    )
    app.state.production_signoff_service = ProductionSignoffService(
        app.state.repository,
        audit_service=app.state.commercial_audit_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.production_signoff = app.state.production_signoff_service
    app.state.production_acceptance_service = ProductionAcceptanceService(
        app.state.repository,
        customer_workspace_service=app.state.customer_workspace_service,
        production_signoff_service=app.state.production_signoff_service,
        audit_service=app.state.commercial_audit_service,
    )
    app.state.ops_commercialization_dashboard_service.production_acceptance = app.state.production_acceptance_service
    app.state.production_launch_week_pack_service = ProductionLaunchWeekPackService(
        production_signoff_service=app.state.production_signoff_service,
        production_acceptance_service=app.state.production_acceptance_service,
        base_dir=BASE_DIR,
    )
    app.state.production_launch_week_pack_service.dashboard_service = app.state.ops_commercialization_dashboard_service
    app.state.ops_commercialization_dashboard_service.launch_week_pack = app.state.production_launch_week_pack_service
    app.state.production_handshake_pack_service = ProductionHandshakePackService(
        production_signoff_service=app.state.production_signoff_service,
        production_acceptance_service=app.state.production_acceptance_service,
        base_dir=BASE_DIR,
    )
    app.state.production_handshake_pack_service.dashboard_service = app.state.ops_commercialization_dashboard_service
    app.state.ops_commercialization_dashboard_service.handshake_pack = app.state.production_handshake_pack_service
    app.state.production_signoff_board_service = ProductionSignoffBoardService(
        production_signoff_service=app.state.production_signoff_service,
    )
    app.state.ops_commercialization_dashboard_service.production_signoff_board = app.state.production_signoff_board_service
    app.state.production_preflight_service = ProductionPreflightService(
        app.state.repository,
        production_signoff_service=app.state.production_signoff_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.production_preflight = app.state.production_preflight_service
    app.state.launch_command_center_service = LaunchCommandCenterService(
        app.state.repository,
        commercialization_dashboard_service=app.state.ops_commercialization_dashboard_service,
        production_acceptance_service=app.state.production_acceptance_service,
        production_signoff_board_service=app.state.production_signoff_board_service,
        production_preflight_service=app.state.production_preflight_service,
    )
    app.state.ops_commercialization_dashboard_service.launch_command_center = app.state.launch_command_center_service
    app.state.customer_success_reporting_service = CustomerSuccessReportingService(
        app.state.repository,
        customer_workspace_service=app.state.customer_workspace_service,
        customer_account_service=app.state.customer_account_service,
        production_acceptance_service=app.state.production_acceptance_service,
        production_signoff_service=app.state.production_signoff_service,
        commercial_audit_service=app.state.commercial_audit_service,
    )
    app.state.ops_commercialization_dashboard_service.customer_success = app.state.customer_success_reporting_service
    app.state.production_launch_ledger_service = ProductionLaunchLedgerService(
        app.state.repository,
        production_signoff_service=app.state.production_signoff_service,
        production_acceptance_service=app.state.production_acceptance_service,
        production_preflight_service=app.state.production_preflight_service,
        launch_command_center_service=app.state.launch_command_center_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.launch_ledger = app.state.production_launch_ledger_service
    app.state.human_signoff_closure_service = HumanSignoffClosureService(
        production_signoff_service=app.state.production_signoff_service,
        production_signoff_board_service=app.state.production_signoff_board_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.human_signoff_closure = app.state.human_signoff_closure_service
    app.state.wave_activation_controller_service = WaveActivationControllerService(
        app.state.repository,
        production_signoff_service=app.state.production_signoff_service,
        production_acceptance_service=app.state.production_acceptance_service,
        production_preflight_service=app.state.production_preflight_service,
        launch_command_center_service=app.state.launch_command_center_service,
        commercial_audit_service=app.state.commercial_audit_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.wave_activation = app.state.wave_activation_controller_service
    app.state.go_live_day_runner_service = GoLiveDayRunnerService(
        app.state.repository,
        wave_activation_controller_service=app.state.wave_activation_controller_service,
        production_preflight_service=app.state.production_preflight_service,
        launch_command_center_service=app.state.launch_command_center_service,
        customer_success_reporting_service=app.state.customer_success_reporting_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.go_live_day_runner = app.state.go_live_day_runner_service
    app.state.launch_week_guard_service = LaunchWeekGuardService(
        app.state.repository,
        customer_success_reporting_service=app.state.customer_success_reporting_service,
        launch_command_center_service=app.state.launch_command_center_service,
        production_launch_ledger_service=app.state.production_launch_ledger_service,
        base_dir=BASE_DIR,
    )
    app.state.ops_commercialization_dashboard_service.launch_week_guard = app.state.launch_week_guard_service
    app.state.ops_navigation_service = OpsNavigationService(
        app.state.repository,
        account_workspace_service=app.state.ops_account_workspace_service,
        release_workspace_service=app.state.ops_release_workspace_service,
        alerting_service=app.state.ops_alerting_service,
        governance_service=app.state.governance_service,
        ops_traceability_service=app.state.ops_traceability_service,
    )
    app.state.ops_review_hub_service = OpsReviewHubService(
        app.state.repository,
        review_service=app.state.review_service,
        governance_service=app.state.governance_service,
        alerting_service=app.state.ops_alerting_service,
        billing_service=app.state.billing_service,
        commercial_support_service=app.state.commercial_support_service,
        quality_projection_service=app.state.ops_quality_projection_service,
        customer_campaign_service=app.state.customer_campaign_service,
    )
    app.state.ops_permission_policy = OpsPermissionPolicyService()
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
    app.state.author_work_service = AuthorWorkService(
        app.state.repository,
        registry=app.state.world_registry,
        provider_routing_service=app.state.provider_routing_service,
        analytics_service=app.state.analytics_service,
    )
    app.state.library_stats_semantic_layer_service = LibraryStatsSemanticLayerService(
        app.state.repository,
    )
    app.state.library_stats_cube_service = LibraryStatsCubeService(
        app.state.repository,
        semantic_layer_service=app.state.library_stats_semantic_layer_service,
    )
    app.state.library_stats_cube_projection_service = LibraryStatsCubeProjectionService(
        cube_service=app.state.library_stats_cube_service,
    )
    app.state.analytics_service.register_listener(
        LIBRARY_STATS_INVALIDATION_EVENTS,
        app.state.library_stats_cube_projection_service.on_analytics_event,
    )
    app.state.quantum_read_model_service = QuantumReadModelService(
        app.state.repository,
        author_work_service=app.state.author_work_service,
        analytics_service=app.state.analytics_service,
        billing_service=app.state.billing_service,
        library_stats_cube_service=app.state.library_stats_cube_service,
        illustration_service=app.state.illustration_service,
    )
    app.state.author_project_graph_service = AuthorProjectGraphService(
        app.state.repository,
        authoring_service=app.state.authoring_service,
    )
    app.state.author_collaboration_service = AuthorCollaborationService(
        app.state.repository,
        analytics_service=app.state.analytics_service,
        async_job_service=app.state.async_job_service,
    )
    app.state.author_permission_policy = AuthorPermissionPolicyService()
    app.state.session_service = SessionService(
        app.state.repository,
        intent_parser=app.state.intent_parser,
        renderer=app.state.renderer,
        billing_service=app.state.billing_service,
        analytics_service=app.state.analytics_service,
        observability_service=app.state.observability_service,
        provider_routing_service=app.state.provider_routing_service,
        illustration_service=app.state.illustration_service,
    )

    @app.middleware("http")
    async def enforce_author_collaboration_access_policy(request, call_next):
        path = request.url.path.rstrip("/") or request.url.path
        if app.state.author_permission_policy.resolve_rule(method=request.method, path=path):
            try:
                ensure_author_collaboration_access(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    @app.middleware("http")
    async def enforce_ops_access(request, call_next):
        path = request.url.path.rstrip("/")
        if path == "/v1/ops" or path.startswith("/v1/ops/"):
            try:
                if request.method == "GET":
                    ensure_ops_read_access(request)
                elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                    ensure_ops_write_access(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    def _safe_async_job_heartbeat(job_id: str, *, requested_by: str) -> None:
        try:
            app.state.async_job_service.heartbeat_job(job_id, requested_by=requested_by)
        except (KeyError, ValueError):
            return

    def _run_learned_training_job(job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        _safe_async_job_heartbeat(job["job_id"], requested_by="learned_training_runner")
        result = run_learned_training_automation(
            repository=app.state.repository,
            output_dir=BASE_DIR / "artifacts" / "learned_training_runs",
            tracks=payload.get("tracks") or ["evaluator", "reranker"],
            world_id=payload.get("world_id"),
            world_version_id=payload.get("world_version_id"),
            limit=payload.get("limit"),
        )
        _safe_async_job_heartbeat(job["job_id"], requested_by="learned_training_runner")
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
        _safe_async_job_heartbeat(job["job_id"], requested_by="runtime_backup_runner")
        result = app.state.runtime_ops_service.create_backup(
            label=payload.get("label"),
            output_dir=payload.get("output_dir"),
            dry_run=bool(payload.get("dry_run")),
            execute_postgres=True,
            job_id=job.get("job_id"),
        )
        _safe_async_job_heartbeat(job["job_id"], requested_by="runtime_backup_runner")
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
        _safe_async_job_heartbeat(job["job_id"], requested_by="runtime_restore_runner")
        result = app.state.runtime_ops_service.execute_restore_request(
            request_id=str(payload.get("request_id") or ""),
            job_id=job.get("job_id"),
            requested_by=payload.get("requested_by") or job.get("requested_by"),
        )
        _safe_async_job_heartbeat(job["job_id"], requested_by="runtime_restore_runner")
        app.state.analytics_service.track(
            "runtime_restore_executed" if result.get("_job_status_override") != "failed" else "runtime_restore_failed",
            account_id=job.get("account_id"),
            payload_json={
                **result,
                "job_id": job.get("job_id"),
            },
        )
        return result

    def _run_illustration_generate_job(job: Dict[str, Any]) -> Dict[str, Any]:
        _safe_async_job_heartbeat(job["job_id"], requested_by="illustration_generate_runner")
        result = app.state.illustration_service.run_generation_job(job)
        _safe_async_job_heartbeat(job["job_id"], requested_by="illustration_generate_runner")
        return result

    app.state.reader_generation_job_runner = ReaderGenerationJobRunner(
        repository=app.state.repository,
        session_service=app.state.session_service,
        analytics_service=app.state.analytics_service,
    )

    def _run_reader_generation_job(job: Dict[str, Any]) -> Dict[str, Any]:
        _safe_async_job_heartbeat(job["job_id"], requested_by="reader_generation_runner")
        result = app.state.reader_generation_job_runner.run(job)
        _safe_async_job_heartbeat(job["job_id"], requested_by="reader_generation_runner")
        return result

    app.state.async_job_service.register_runner("learned_training", _run_learned_training_job)
    app.state.async_job_service.register_runner("runtime_backup", _run_runtime_backup_job)
    app.state.async_job_service.register_runner("runtime_restore", _run_runtime_restore_job)
    app.state.async_job_service.register_runner(ILLUSTRATION_JOB_TYPE, _run_illustration_generate_job)
    app.state.async_job_service.register_runner(READER_GENERATION_JOB_TYPE, _run_reader_generation_job)
    app.state.async_job_boot_reconcile = None

    frontend_dist_dir = _modern_frontend_dist_dir()
    frontend_static_dir = frontend_dist_dir / "assets"
    assets_dir = frontend_static_dir if _modern_frontend_enabled() and frontend_static_dir.is_dir() else WEB_DIR
    fallback_assets_dir = WEB_DIR if assets_dir != WEB_DIR else None
    app.mount(
        "/assets",
        FallbackNoCacheStaticFiles(directory=assets_dir, fallback_directory=fallback_assets_dir),
        name="assets",
    )
    app.include_router(quantum_compat_router)
    app.include_router(reader_router)
    app.include_router(billing_provider_router)
    app.include_router(auth_router)
    app.include_router(customer_router)
    app.include_router(author_router)
    app.include_router(ops_router)

    @app.get("/")
    def root():
        if _modern_frontend_enabled():
            index_file = _modern_frontend_dist_dir() / "index.html"
            if index_file.is_file():
                return FileResponse(index_file, headers=NO_CACHE_HEADERS)
        return RedirectResponse(url="/app")

    @app.get("/app")
    def app_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/user")
    def app_user_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/reviewer")
    def app_reviewer_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/customer")
    def app_customer_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/login")
    def app_login_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/signup")
    def app_signup_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/verify-email")
    def app_verify_email_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/forgot-password")
    def app_forgot_password_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/app/reset-password")
    def app_reset_password_shell() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE_HEADERS)

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    def _world_cover_image(world_version_id: Optional[str]) -> str:
        service = getattr(app.state, "illustration_service", None)
        if service is None or not world_version_id:
            return ""
        return service.world_cover_url(world_version_id=str(world_version_id))

    def _session_cover_image(session_id: str, world_version_id: Optional[str]) -> str:
        service = getattr(app.state, "illustration_service", None)
        if service is None or not session_id:
            return ""
        return service.session_cover_url(session_id=session_id) or _world_cover_image(world_version_id)

    def _session_atmosphere_image(session_id: str) -> str:
        service = getattr(app.state, "illustration_service", None)
        if service is None or not session_id:
            return ""
        return service.latest_chapter_hero_url(session_id=session_id)

    def _session_media_payload(session_id: str, world_version_id: Optional[str]) -> Dict[str, str]:
        return {
            "coverImage": _session_cover_image(session_id, world_version_id),
            "atmosphereImage": _session_atmosphere_image(session_id),
        }

    def _decorate_session_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
        world_version_id = str(summary.get("world_version_id") or "")
        return {
            **summary,
            **_session_media_payload(str(summary.get("session_id") or ""), world_version_id),
        }

    def _decorate_world_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
        world_version_id = str(summary.get("latest_version") or "")
        return {
            **summary,
            "coverImage": _world_cover_image(world_version_id),
        }

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
        return {"worlds": [_decorate_world_summary(item) for item in app.state.repository.list_worlds()]}

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
        return {"worlds": [_decorate_world_summary(item) for item in app.state.repository.list_worlds()]}

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
        runtime_bundle = app.state.repository.get_runtime_bundle(next(item["latest_version"] for item in app.state.repository.list_worlds() if item["world_id"] == payload.world_id))
        app.state.session_service._prepare_longform_state(
            runtime=runtime_bundle,
            state=initial_state,
            longform_setup=payload.longform_setup,
        )

        session_record = app.state.repository.create_session(
            payload.world_id,
            initial_state,
            player_profile=payload.player_profile,
            metadata={"reader_id": payload.player_profile.get("reader_id"), "longform_setup_present": bool(payload.longform_setup), **payload.metadata},
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
        app.state.illustration_service.ensure_session_cover(
            session_id=session_record.session_id,
            reader_id=payload.player_profile.get("reader_id"),
            world_version_id=str(session_record.metadata.get("world_version_id") or ""),
        )
        app.state.illustration_service.ensure_world_cover(
            world_version_id=str(session_record.metadata.get("world_version_id") or ""),
        )
        world_version_id = str(session_record.metadata.get("world_version_id") or "")
        return {
            "session_id": session_record.session_id,
            "reader_id": payload.player_profile.get("reader_id"),
            "world_version_id": world_version_id,
            "current_state": session_record.current_state.to_dict(),
            "paywall": access,
            "steering_checkpoint": dict(initial_state.storyline_checkpoint or {}),
            **_session_media_payload(session_record.session_id, world_version_id),
        }

    @app.get("/v1/sessions")
    def list_sessions(request: Request, world_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = reader_identity_account_id(reader_identity(request))
        if not account_id:
            return {"sessions": []}
        return {
            "sessions": [
                _decorate_session_summary(item)
                for item in app.state.repository.list_sessions(world_id=world_id, reader_id=account_id)
            ]
        }

    @app.get("/v1/sessions/{session_id}")
    def get_session(session_id: str, request: Request) -> Dict[str, Any]:
        try:
            session_record = ensure_reader_session_access(request, session_id=session_id)
            latest_step = app.state.repository.get_latest_step(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        session_payload = session_record.to_dict()
        world_version_id = str(session_record.metadata.get("world_version_id") or "")
        session_payload.update(_session_media_payload(session_id, world_version_id))
        return {
            "session": session_payload,
            "latest_step": latest_step.to_dict() if latest_step else None,
            "world_version_id": world_version_id,
            "paywall": app.state.billing_service.access_check(session_id, reader_id=session_record.metadata.get("reader_id")),
            "entitlements_snapshot": session_record.metadata.get("entitlements_snapshot", {}),
            "intent_prefill": app.state.intent_prefill_service.build(session_record, latest_step).to_dict(),
            **_session_media_payload(session_id, world_version_id),
        }

    @app.delete("/v1/sessions/{session_id}")
    def delete_session(session_id: str, request: Request) -> Dict[str, Any]:
        try:
            session_record = ensure_reader_session_access(request, session_id=session_id)
            deleted = app.state.repository.delete_session(session_id)
            account_id = (
                str(session_record.metadata.get("account_id") or "").strip()
                or str(session_record.metadata.get("reader_id") or session_record.player_profile.get("reader_id") or "").strip()
                or None
            )
            if account_id:
                app.state.analytics_service.track(
                    "session_deleted",
                    reader_id=account_id,
                    session_id=session_id,
                    world_id=session_record.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                    payload_json={"account_id": account_id},
                )
            return deleted
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
        request: Request,
        debug: bool = False,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            session_record = ensure_reader_session_access(request, session_id=session_id)
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
                "continuity_contract": build_reader_continuity_contract(
                    status=blocked_status,
                    session_id=session_id,
                    paywall=access,
                ),
            }

        state_before = NarrativeState.from_dict(session_record.current_state.to_dict())
        runtime_bundle = app.state.repository.get_runtime_bundle(session_record.metadata.get("world_version_id"))
        app.state.session_service._prepare_longform_state(runtime=runtime_bundle, state=state_before)
        state_before.player_intent = app.state.intent_parser.parse(
            payload.player_input,
            overrides=payload.intent_override,
        )
        steering_checkpoint = {}
        if payload.steering_directive:
            from ..longform import apply_steering_directive

            steering_directive = dict(payload.steering_directive or {})
            steering_directive.setdefault("current_user_intent", payload.player_input)
            steering_result = apply_steering_directive(
                state_before,
                steering_directive,
                world=world_record.world,
            )
            steering_checkpoint = dict(steering_result.get("replan_checkpoint") or {})

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
        if result.get("status") == "ok" and isinstance(result.get("reader_view"), dict):
            sanitized_reader_view, reader_visible_language_debug = sanitize_reader_visible_payload(dict(result["reader_view"] or {}))
            result["reader_view"] = sanitized_reader_view
            if isinstance(result.get("rendered_scene"), dict):
                rendered_debug = dict((result["rendered_scene"].get("debug") or {}))
                rendered_debug["reader_visible_language_debug"] = reader_visible_language_debug
                result["rendered_scene"] = {
                    **dict(result["rendered_scene"] or {}),
                    "debug": rendered_debug,
                }

        chosen_event = EventAtom.from_dict(result["chosen_event"]) if result.get("chosen_event") else None
        state_after = (
            NarrativeState.from_dict(result["updated_state"])
            if result.get("updated_state")
            else session_record.current_state
        )
        chapter_task = dict((result.get("chapter_plan") or {}).get("chapter_task") or {})
        coverage_context = {
            "selected_event_ids": list((result.get("chapter_plan") or {}).get("selected_event_ids", [])),
            "scene_beats": list(result.get("scene_beats") or []),
            "chapter_task": chapter_task,
        }
        if result.get("status") == "ok" and isinstance(result.get("reader_view"), dict):
            repaired_reader_view, state_after, long_route_quality_debug = apply_long_route_quality_controls(
                dict(result.get("reader_view") or {}),
                state_before=state_before,
                state_after=state_after,
                coverage_context=coverage_context,
            )
            result["reader_view"] = repaired_reader_view
            result["updated_state"] = state_after.to_dict()
            if isinstance(result.get("rendered_scene"), dict):
                rendered_debug = dict((result["rendered_scene"].get("debug") or {}))
                rendered_debug["long_route_quality_controls"] = long_route_quality_debug
                result["rendered_scene"] = {
                    **dict(result["rendered_scene"] or {}),
                    "debug": rendered_debug,
                }
        body = str((result.get("reader_view") or {}).get("body") or "")
        lint_report = lint_chapter_draft(body) if body else {}
        quality_bundle = None
        target_chapters = int(getattr(getattr(runtime_bundle.worldpack, "series_plan", None), "total_chapter_target", 0) or 100)
        if result["status"] == "ok":
            quality_bundle = evaluate_persisted_chapter(
                chapter_id="chapter_%s_%s" % (session_id, state_after.chapter_index),
                world_version_id=session_record.metadata.get("world_version_id"),
                session_id=session_id,
                body=body,
                paragraphs=body.split("\n\n"),
                dialogue_count=int(lint_report.get("dialogue_count", 0)),
                action_count=int(lint_report.get("action_count", 0)),
                detail_count=int(lint_report.get("detail_count", 0)),
                character_fidelity_score=max(
                    [item["components"].get("character_fidelity", 0.0) for item in result.get("scored_candidates", [])],
                    default=0.0,
                ),
                state_after=state_after,
                ending_ready=bool((result.get("chapter_plan") or {}).get("ending_ready")),
                chapter_title=(result.get("reader_view") or {}).get("chapter_title"),
                recap=(result.get("reader_view") or {}).get("recap"),
                relationship_hints=list((result.get("reader_view") or {}).get("relationship_hints") or []),
                choices=list((result.get("reader_view") or {}).get("choices") or []),
                paywall_required=bool(access["required"]),
                coverage_context=coverage_context,
                target_words=app.state.session_service._effective_target_words(
                    chapter_task.get("target_words"),
                    chapter_index=int(state_after.chapter_index or 0),
                    story_phase=str(state_after.story_phase or ""),
                ),
                min_target_words=app.state.session_service._effective_min_target_words(
                    runtime_bundle,
                    chapter_index=int(state_after.chapter_index or 0),
                    story_phase=str(state_after.story_phase or ""),
                ),
                chapter_index=int(state_after.chapter_index or 0),
                target_chapters=target_chapters,
                story_phase=str(state_after.story_phase or ""),
                rolling_quality_window=list((state_before.metadata or {}).get("quality_contract_window", [])),
                enforcement_scope="session_api_generation",
            )
            grounding_check = build_grounding_check(
                scenario_id="reader_continue",
                text=body,
                source_surface="reader",
                world_version_id=session_record.metadata.get("world_version_id"),
                session_id=session_id,
                chapter_id="chapter_%s_%s" % (session_id, state_after.chapter_index),
                coverage_context=coverage_context,
                state_after=state_after,
                worldpack_payload=runtime_bundle.worldpack.to_dict() if hasattr(runtime_bundle.worldpack, "to_dict") else None,
            )
            quality_bundle = enforce_grounding_quality_gate(
                quality_bundle,
                grounding_check=grounding_check,
                source_surface="reader",
            )
            worldpack_payload = runtime_bundle.worldpack.to_dict() if hasattr(runtime_bundle.worldpack, "to_dict") else None
            quality_bundle = enforce_generation_hard_constraints(
                quality_bundle,
                reader_view=dict(result.get("reader_view") or {}),
                grounding_check=grounding_check,
                source_surface="reader",
                target_chapters=target_chapters,
                worldpack_payload=worldpack_payload,
                repair_report=long_route_quality_debug,
            )
            from ..longform import record_replan_debt

            record_replan_debt(
                state_after,
                chapter_index=int(state_after.chapter_index or 0),
                issue_codes=[issue.issue_code for issue in quality_bundle["report"].issues],
            )
            if not quality_bundle["quality_gate"]["ok"]:
                app.state.analytics_service.track(
                    "chapter_quality_guard_failed",
                    reader_id=reader_id,
                    account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                    session_id=session_id,
                    world_id=world_record.world.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                    chapter_index=state_after.chapter_index,
                    access_tier=access.get("access_tier"),
                    payload_json={
                        "surface": "session_api_generation",
                        "quality_gate": quality_bundle["quality_gate"],
                    },
                )
                app.state.observability_service.record_runtime_receipt(
                    surface="session_api",
                    action="step_session",
                    response_status="quality_guard_failed",
                    world_id=world_record.world.world_id,
                    world_version_id=session_record.metadata.get("world_version_id"),
                    session_id=session_id,
                    account_id=app.state.billing_service.resolve_account_id(reader_id=reader_id),
                    reader_id=reader_id,
                    candidate_batch=result.get("candidate_batch"),
                    rendered_scene=result.get("rendered_scene"),
                    reader_view=None,
                    estimated_cost=0.0,
                    runtime_latency_ms=runtime_latency_ms,
                )
                base_response = {
                    "status": "quality_guard_failed",
                    "code": quality_bundle["quality_gate"]["code"],
                    "quality_gate": quality_bundle["quality_gate"],
                    "world_version_id": session_record.metadata.get("world_version_id"),
                    "reader_view": None,
                    "updated_state_summary": None,
                    "replay_preview": None,
                    "paywall": access,
                    "steering_checkpoint": steering_checkpoint or dict(state_after.storyline_checkpoint or {}),
                    "replan_checkpoint": dict(state_after.replan_checkpoint or {}),
                    "continuity_contract": build_reader_continuity_contract(
                        status="quality_guard_failed",
                        session_id=session_id,
                        paywall=access,
                        quality_gate=quality_bundle["quality_gate"],
                    ),
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
                        }
                    )
                return base_response
            state_after.metadata = {
                **dict(state_after.metadata or {}),
                "quality_contract_window": list(quality_bundle["quality_gate"].get("quality_contract_window") or []),
            }
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
        step_record.metadata["steering_directive"] = dict(payload.steering_directive or {})
        step_record.metadata["steering_checkpoint"] = steering_checkpoint
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
            app.state.illustration_service.ensure_chapter_hero(
                session_id=session_id,
                reader_id=reader_id,
                world_version_id=str(session_record.metadata.get("world_version_id") or ""),
                chapter_index=int(step_record.step_index or 0),
                rendered_scene=dict(result.get("rendered_scene") or {}),
            )
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
            "steering_checkpoint": steering_checkpoint or dict(state_after.storyline_checkpoint or {}),
            "replan_checkpoint": dict(state_after.replan_checkpoint or {}),
            "continuity_contract": build_reader_continuity_contract(
                status=str(result["status"]),
                session_id=session_id,
                paywall=paywall,
            ),
            **_session_media_payload(session_id, str(session_record.metadata.get("world_version_id") or "")),
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
    def replay_session(
        session_id: str,
        request: Request,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        limit: Optional[int] = None,
        latest: bool = False,
    ) -> Dict[str, Any]:
        try:
            ensure_reader_session_access(request, session_id=session_id)
            return app.state.repository.get_replay(
                session_id,
                start_chapter=start_chapter,
                end_chapter=end_chapter,
                limit=limit,
                latest=latest,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/v1/sessions/{session_id}/prefill")
    def session_prefill(session_id: str, request: Request) -> Dict[str, Any]:
        try:
            session_record = ensure_reader_session_access(request, session_id=session_id)
            latest_step = app.state.repository.get_latest_step(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return app.state.intent_prefill_service.build(session_record, latest_step).to_dict()

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def modern_frontend_shell(frontend_path: str) -> FileResponse:
        if not _modern_frontend_enabled():
            raise HTTPException(status_code=404, detail="Not Found")
        static_file = _frontend_static_file(frontend_path)
        if static_file is not None:
            return FileResponse(static_file, headers=NO_CACHE_HEADERS)
        if _is_modern_frontend_route(frontend_path):
            index_file = _modern_frontend_dist_dir() / "index.html"
            if index_file.is_file():
                return FileResponse(index_file, headers=NO_CACHE_HEADERS)
        raise HTTPException(status_code=404, detail="Not Found")

    return app
