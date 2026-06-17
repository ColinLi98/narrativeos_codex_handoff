from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from math import sqrt
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..runtime_env import load_local_env
from ..eval.scorers import LONGFORM_SOFT_ISSUE_THRESHOLDS
from ..eval.validators import LONGFORM_Q03_SIGNAL_THRESHOLDS
from ..long_route_quality import repair_reader_view_for_display
from ..models import (
    CandidateBatch,
    ChapterPlan,
    EvaluationReport,
    EventAtom,
    NarrativeState,
    NarrativeViewModel,
    PromiseLedgerEntry,
    RenderedScene,
    RouteCandidate,
    SceneBeat,
    SceneRenderSpec,
    ScoredCandidate,
    SessionRecord,
    StepRecord,
    WorldRecord,
)
from ..worldpacks.models import RuntimeBundle, WorldPack, WorldVersion
from ..worldpacks.registry import FileSystemWorldRegistry, runtime_bundle_from_worldpack_data
from .db import (
    AuditLogRow,
    AnalyticsEventRow,
    AuthorProjectGraphRow,
    AuthDeliveryAttemptRow,
    AuthIdentityRow,
    AuthIdentityProfileRow,
    AuthFlowTokenRow,
    AuthTokenRow,
    AuthorApprovalRecordRow,
    AuthorCommentMessageRow,
    AuthorCommentThreadRow,
    AuthorDraftWatcherRow,
    AuthorNotificationRow,
    AuthorNotificationPreferenceRow,
    AuthorThreadWatcherRow,
    AuthorWorkChapterRow,
    AuthorWorkRevisionRow,
    AuthorWorkRow,
    BillingCheckoutSessionRow,
    BillingProfileRow,
    BillingLifecycleEventRow,
    BillingRetryAttemptRow,
    BillableEventRow,
    CampaignChannelTargetRow,
    CampaignProofBundleRow,
    CampaignReviewSubmissionRow,
    CampaignRow,
    ChapterRow,
    ChurnRiskFlagRow,
    ContentQualityScoreRow,
    CreditBalanceRow,
    CustomerSuccessSnapshotRow,
    First30DayValueSummaryRow,
    First7DayOutcomeRow,
    GoLiveReadyAccountRow,
    GoLiveDayCheckpointRow,
    GoLiveDayRunRow,
    LaunchWaveStatusRow,
    LaunchWeekGuardRunRow,
    LibraryFollowRow,
    LibraryStatsCubeRow,
    LibraryWorkFavoriteRow,
    CustomerAuditExportRow,
    CustomerAccountRow,
    DataDeletionRequestRow,
    DataRetentionPolicyRow,
    DisputeRow,
    DunningEventRow,
    DunningRunRow,
    ExpansionCandidateRow,
    EntitlementRow,
    InvoicePreviewRow,
    InvoiceIssuanceRow,
    ManualAdjustmentRow,
    GeneratedMediaAssetRow,
    OpsReviewItemRow,
    OverageFlagRow,
    OpsConfigRow,
    PlanRow,
    ProductionCustomerAcceptanceRecordRow,
    ProductionCutoverWindowRow,
    ProductionLaunchEventRow,
    ProductionPostmortemRecordRow,
    ProductionPreflightCheckRow,
    ProductionPreflightRunRow,
    ProductionSignoffEvidenceRow,
    ProductionSignoffItemRow,
    ProductionSignoffRow,
    PartnerCapabilityRow,
    PartnerHealthCheckRow,
    PartnerRow,
    PaymentRetryAttemptRow,
    PaymentTransactionRow,
    PilotToPaidReadinessScoreRow,
    PilotConversionTrackRow,
    ProviderWebhookEventRow,
    CreditNoteRow,
    ProviderSubscriptionRow,
    GroundingCheckRow,
    QualityFeedbackItemRow,
    QualityEventRow,
    QualityPolicyRow,
    RefundRequestRow,
    ReviewRecordRow,
    ReviewCaseRow,
    RenewalTrackerRow,
    RouteChoiceRow,
    SessionRow,
    SoulProfilePreferenceRow,
    ShowcaseWorkCommentRow,
    ShowcaseWorkLikeRow,
    ShowcaseWorkViewRow,
    StorySessionBookmarkRow,
    StorySessionShareTokenRow,
    ShowcaseWorkTipRow,
    SubscriptionRow,
    SupportCaseRow,
    SettlementItemRow,
    SettlementRunRow,
    UsageLedgerRow,
    UsageMeterRow,
    FirstCustomerSuccessPackRow,
    WorldRow,
    WorldVersionRow,
    create_platform_session_local,
    utcnow_iso,
)

load_local_env()


LEAN_REPLAY_SCHEMA_VERSION = "chapter_replay_plan/v2"
FULL_STEP_RECORD_ENV = "NARRATIVEOS_STORE_FULL_STEP_RECORD"
DATABASE_FAILOVER_SQLITE_ENV = "NARRATIVEOS_DATABASE_FAILOVER_SQLITE"
DATABASE_FAILOVER_SQLITE_URL_ENV = "NARRATIVEOS_DATABASE_FAILOVER_SQLITE_URL"


def _store_full_step_record_enabled() -> bool:
    return str(os.environ.get(FULL_STEP_RECORD_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return str(os.environ.get(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_postgres_database_url(database_url: str) -> bool:
    return str(database_url or "").strip().lower().startswith(("postgres://", "postgresql://"))


def _serverless_sqlite_failover_url() -> str:
    configured = str(os.environ.get(DATABASE_FAILOVER_SQLITE_URL_ENV, "") or "").strip()
    return configured or "sqlite:////tmp/narrativeos_beta.db"


def _bounded_list(values: List[Any], *, limit: int, tail: bool = True) -> List[Any]:
    items = list(values or [])
    if limit <= 0 or len(items) <= limit:
        return items
    return items[-limit:] if tail else items[:limit]


def _compact_state_for_replay(state: NarrativeState) -> Dict[str, Any]:
    """Keep replay/deviation state while dropping long-route memory blobs."""
    state_id = str(getattr(state, "state_id", "") or "")
    compacted_state_id = state_id if len(state_id) <= 128 else f"{state.world_id}:{state.turn_index}:{state.chapter_index}"
    return {
        "state_id": compacted_state_id,
        "world_id": state.world_id,
        "turn_index": int(state.turn_index),
        "story_phase": state.story_phase,
        "chapter_index": int(state.chapter_index),
        "min_end_turn": int(state.min_end_turn),
        "fate_pressure": float(state.fate_pressure),
        "karmic_weather": dict(state.karmic_weather),
        "unresolved_debts": _bounded_list(list(state.unresolved_debts), limit=24),
        "world_facts": _bounded_list(list(state.world_facts), limit=24),
        "timeline": _bounded_list(list(state.timeline), limit=24),
        "characters": {},
        "relationship_graph": [],
        "open_promises": _bounded_list([promise.to_dict() for promise in state.open_promises], limit=32),
        "tension": float(state.tension),
        "themes": dict(state.themes),
        "player_intent": dict(state.player_intent),
        "recent_scene_functions": _bounded_list(list(state.recent_scene_functions), limit=16),
        "visited_event_ids": _bounded_list(list(state.visited_event_ids), limit=160),
        "route_fingerprint": _bounded_list(list(state.route_fingerprint), limit=160),
        "rating_ceiling": state.rating_ceiling,
        "current_series_id": state.current_series_id,
        "current_volume_id": state.current_volume_id,
        "current_arc_id": state.current_arc_id,
        "current_chapter_task": dict(state.current_chapter_task or {}),
        "word_budget": int(state.word_budget),
        "metadata": {
            "compacted_for_replay": True,
            "source_state_id": state_id[:256],
            "open_promise_count": len(state.open_promises),
            "route_fingerprint_count": len(state.route_fingerprint),
            "visited_event_count": len(state.visited_event_ids),
        },
    }


def _lean_rendered_scene_payload(step_record: StepRecord) -> Optional[Dict[str, Any]]:
    if step_record.rendered_scene is not None:
        payload = step_record.rendered_scene.to_dict()
    elif step_record.reader_view is not None:
        scene_card = dict(step_record.reader_view.scene_card or {})
        payload = {
            "event_id": step_record.chosen_event.event_id if step_record.chosen_event else "",
            "concise_summary": str(scene_card.get("summary") or step_record.reader_view.recap or ""),
            "interactive_scene": "",
            "premium_prose": step_record.reader_view.body,
            "story_title": step_record.reader_view.chapter_title,
            "chapter_summary": step_record.reader_view.recap,
            "pull_quote": str(scene_card.get("quote") or scene_card.get("pull_quote") or ""),
            "story_beats": list(scene_card.get("story_beats") or scene_card.get("beats") or []),
            "visual_details": list(scene_card.get("visual_details") or []),
            "debug": {},
        }
    else:
        return None
    debug = dict(payload.get("debug") or {})
    payload["debug"] = {
        key: debug[key]
        for key in ["backend_routing", "backend_error", "renderer", "template_fallback"]
        if key in debug
    }
    return payload


def _lean_step_replay_payload(step_record: StepRecord) -> Dict[str, Any]:
    rendered_scene = _lean_rendered_scene_payload(step_record)
    return {
        "schema_version": LEAN_REPLAY_SCHEMA_VERSION,
        "session_id": step_record.session_id,
        "step_index": int(step_record.step_index),
        "player_input": step_record.player_input,
        "intent_vector": dict(step_record.intent_vector),
        "candidate_batch_debug": dict(step_record.candidate_batch.debug or {}),
        "chosen_event": step_record.chosen_event.to_dict() if step_record.chosen_event else None,
        "chapter_plan": step_record.chapter_plan.to_dict() if step_record.chapter_plan else None,
        "scene_beats": [beat.to_dict() for beat in step_record.scene_beats],
        "scene_render_spec": step_record.scene_render_spec.to_dict() if step_record.scene_render_spec else None,
        "rendered_scene": rendered_scene,
        "reader_view": step_record.reader_view.to_dict() if step_record.reader_view else None,
        "state_before": _compact_state_for_replay(step_record.state_before),
        "state_after": _compact_state_for_replay(step_record.state_after),
        "critic_trace": [dict(item) for item in _bounded_list(step_record.critic_trace, limit=24)],
        "promise_ledger_snapshot": _bounded_list(
            [promise.to_dict() for promise in step_record.promise_ledger_snapshot],
            limit=32,
        ),
        "created_at": step_record.created_at,
        "metadata": {"storage_mode": "lean_replay", **dict(step_record.metadata or {})},
    }


def _chapter_plan_json_for_step(step_record: StepRecord) -> Dict[str, Any]:
    if _store_full_step_record_enabled():
        return {
            "schema_version": "chapter_full_step_record/v1",
            "storage_mode": "full_step_record",
            "step_record": step_record.to_dict(),
            "chapter_plan": step_record.chapter_plan.to_dict() if step_record.chapter_plan else None,
        }
    replay = _lean_step_replay_payload(step_record)
    return {
        "schema_version": LEAN_REPLAY_SCHEMA_VERSION,
        "storage_mode": "lean_replay",
        "replay": replay,
        "chapter_plan": replay.get("chapter_plan"),
    }


def _replay_payload_from_plan(plan_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    plan = dict(plan_json or {})
    if isinstance(plan.get("replay"), dict):
        return dict(plan["replay"])
    if isinstance(plan.get("step_record"), dict):
        payload = dict(plan["step_record"])
        payload.setdefault("schema_version", "chapter_full_step_record/v1")
        return payload
    return {}


def _safe_state_from_payload(payload: Dict[str, Any], *, session_id: str, step_index: int) -> NarrativeState:
    state_payload = dict(payload or {})
    state_payload.setdefault("state_id", f"{session_id}:{step_index}")
    state_payload.setdefault("world_id", "")
    state_payload.setdefault("turn_index", step_index)
    state_payload.setdefault("story_phase", "setup")
    state_payload.setdefault("chapter_index", step_index)
    state_payload.setdefault("min_end_turn", 8)
    state_payload.setdefault("fate_pressure", 0.0)
    state_payload.setdefault("karmic_weather", {})
    state_payload.setdefault("unresolved_debts", [])
    state_payload.setdefault("world_facts", [])
    state_payload.setdefault("timeline", [])
    state_payload.setdefault("characters", {})
    state_payload.setdefault("relationship_graph", [])
    state_payload.setdefault("open_promises", [])
    state_payload.setdefault("tension", 0.0)
    state_payload.setdefault("themes", {})
    state_payload.setdefault("player_intent", {})
    state_payload.setdefault("recent_scene_functions", [])
    state_payload.setdefault("visited_event_ids", [])
    state_payload.setdefault("route_fingerprint", [])
    state_payload.setdefault("rating_ceiling", "R")
    return NarrativeState.from_dict(state_payload)


def _step_record_from_replay_payload(payload: Dict[str, Any]) -> Optional[StepRecord]:
    if not payload:
        return None
    session_id = str(payload.get("session_id") or "")
    step_index = int(payload.get("step_index") or payload.get("chapter_index") or 0)
    if not session_id or step_index <= 0:
        return None
    return StepRecord(
        session_id=session_id,
        step_index=step_index,
        player_input=str(payload.get("player_input") or ""),
        intent_vector={key: float(value) for key, value in dict(payload.get("intent_vector") or {}).items()},
        candidate_batch=CandidateBatch(
            raw_candidates=[],
            legal_candidates=[],
            illegal_candidate_reasons={},
            debug=dict(payload.get("candidate_batch_debug") or {}),
        ),
        scored_candidates=[],
        routes=[],
        chosen_event=EventAtom.from_dict(payload["chosen_event"]) if payload.get("chosen_event") else None,
        chapter_plan=ChapterPlan.from_dict(payload["chapter_plan"]) if payload.get("chapter_plan") else None,
        scene_beats=[SceneBeat.from_dict(item) for item in list(payload.get("scene_beats") or [])],
        scene_render_spec=SceneRenderSpec.from_dict(payload["scene_render_spec"]) if payload.get("scene_render_spec") else None,
        rendered_scene=RenderedScene.from_dict(payload["rendered_scene"]) if payload.get("rendered_scene") else None,
        reader_view=NarrativeViewModel.from_dict(payload["reader_view"]) if payload.get("reader_view") else None,
        state_before=_safe_state_from_payload(dict(payload.get("state_before") or {}), session_id=session_id, step_index=max(0, step_index - 1)),
        state_after=_safe_state_from_payload(dict(payload.get("state_after") or {}), session_id=session_id, step_index=step_index),
        critic_trace=[dict(item) for item in list(payload.get("critic_trace") or [])],
        promise_ledger_snapshot=[
            PromiseLedgerEntry.from_dict(item)
            for item in list(payload.get("promise_ledger_snapshot") or [])
        ],
        created_at=str(payload.get("created_at") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )


def _default_database_url() -> str:
    configured = str(os.getenv("DATABASE_URL", "") or "").strip()
    if configured:
        return configured
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/narrativeos_beta.db"
    return "sqlite:///narrativeos_beta.db"


DEFAULT_DATABASE_URL = _default_database_url()
CONTINUATION_STALE_WINDOW_HOURS = 24
CONTINUATION_TARGET_SAMPLES_PER_WORLD = 12
CONTINUATION_TARGET_SAMPLES_PER_VERSION = 8
CONTINUATION_TARGET_NEGATIVE_SAMPLES = 2


def _ops_review_item_payload(row: OpsReviewItemRow) -> Dict[str, Any]:
    return {
        "review_item_id": row.review_item_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "queue": row.queue,
        "status": row.status,
        "severity": row.severity,
        "priority": row.priority,
        "owner_id": row.owner_id,
        "reviewer_id": row.reviewer_id,
        "account_id": row.account_id,
        "world_id": row.world_id,
        "world_version_id": row.world_version_id,
        "headline": row.headline,
        "summary": row.summary,
        "recommended_action": row.recommended_action,
        "due_at": row.due_at,
        "sla_bucket": row.sla_bucket,
        "allowed_actions": list(row.allowed_actions_json or []),
        "linked_entities": list(row.linked_entities_json or []),
        "source_updated_at": row.source_updated_at,
        "last_synced_at": row.last_synced_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _quality_policy_payload(row: QualityPolicyRow) -> Dict[str, Any]:
    return {
        "policy_id": row.policy_id,
        "version": row.version,
        "scenario_id": row.scenario_id,
        "risk_tier": row.risk_tier,
        "mode": row.mode,
        "rule_ids": list(row.rule_ids_json or []),
        "policy_payload": dict(row.policy_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _ops_config_payload(row: OpsConfigRow) -> Dict[str, Any]:
    return {
        "ops_config_id": row.ops_config_id,
        "config_type": row.config_type,
        "scope_key": row.scope_key,
        "status": row.status,
        "config_payload": dict(row.config_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _plan_payload(row: PlanRow) -> Dict[str, Any]:
    return {
        "plan_id": row.plan_id,
        "display_name": row.display_name,
        "subscription_tier": row.subscription_tier,
        "monthly_price_usd": row.monthly_price_usd,
        "status": row.status,
        "seat_limit": row.seat_limit,
        "workspace_limit": row.workspace_limit,
        "campaign_limit": row.campaign_limit,
        "plan_payload": dict(row.plan_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _customer_account_payload(row: CustomerAccountRow) -> Dict[str, Any]:
    return {
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "display_name": row.display_name,
        "status": row.status,
        "plan_id": row.plan_id,
        "seat_limit": row.seat_limit,
        "workspace_limit": row.workspace_limit,
        "campaign_limit": row.campaign_limit,
        "seat_count": row.seat_count,
        "workspace_count": row.workspace_count,
        "campaign_count": row.campaign_count,
        "renewal_due_at": row.renewal_due_at,
        "metadata_json": dict(row.metadata_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _billing_profile_payload(row: BillingProfileRow) -> Dict[str, Any]:
    return {
        "billing_profile_id": row.billing_profile_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "provider": row.provider,
        "provider_customer_ref": row.provider_customer_ref,
        "invoice_email": row.invoice_email,
        "legal_name": row.legal_name,
        "billing_country": row.billing_country,
        "tax_status": row.tax_status,
        "status": row.status,
        "profile_payload_json": dict(row.profile_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _usage_ledger_payload(row: UsageLedgerRow) -> Dict[str, Any]:
    return {
        "usage_ledger_id": row.usage_ledger_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "plan_id": row.plan_id,
        "status": row.status,
        "billing_period_start": row.billing_period_start,
        "billing_period_end": row.billing_period_end,
        "presented_count": row.presented_count,
        "handoff_count": row.handoff_count,
        "conversion_count": row.conversion_count,
        "subtotal_amount_usd": row.subtotal_amount_usd,
        "disputed_amount_usd": row.disputed_amount_usd,
        "credited_amount_usd": row.credited_amount_usd,
        "reversed_amount_usd": row.reversed_amount_usd,
        "ledger_payload_json": dict(row.ledger_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _billable_event_payload(row: BillableEventRow) -> Dict[str, Any]:
    return {
        "billable_event_id": row.billable_event_id,
        "usage_ledger_id": row.usage_ledger_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "plan_id": row.plan_id,
        "billable_metric": row.billable_metric,
        "status": row.status,
        "trace_id": row.trace_id,
        "quality_event_id": row.quality_event_id,
        "runtime_receipt_event_id": row.runtime_receipt_event_id,
        "feedback_item_id": row.feedback_item_id,
        "source_surface": row.source_surface,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "quantity": row.quantity,
        "unit_price_usd": row.unit_price_usd,
        "amount_usd": row.amount_usd,
        "reason_codes_json": list(row.reason_codes_json or []),
        "event_payload_json": dict(row.event_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _invoice_preview_payload(row: InvoicePreviewRow) -> Dict[str, Any]:
    return {
        "invoice_preview_id": row.invoice_preview_id,
        "usage_ledger_id": row.usage_ledger_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "plan_id": row.plan_id,
        "status": row.status,
        "billing_period_start": row.billing_period_start,
        "billing_period_end": row.billing_period_end,
        "subtotal_amount_usd": row.subtotal_amount_usd,
        "credits_applied_usd": row.credits_applied_usd,
        "disputed_amount_usd": row.disputed_amount_usd,
        "credited_amount_usd": row.credited_amount_usd,
        "reversed_amount_usd": row.reversed_amount_usd,
        "total_due_usd": row.total_due_usd,
        "line_items_json": list(row.line_items_json or []),
        "summary_json": dict(row.summary_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _credit_balance_payload(row: CreditBalanceRow) -> Dict[str, Any]:
    return {
        "credit_balance_id": row.credit_balance_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "balance_type": row.balance_type,
        "amount_usd": row.amount_usd,
        "source_ref_json": dict(row.source_ref_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _overage_flag_payload(row: OverageFlagRow) -> Dict[str, Any]:
    return {
        "overage_flag_id": row.overage_flag_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "plan_id": row.plan_id,
        "metric_type": row.metric_type,
        "status": row.status,
        "observed_units": row.observed_units,
        "included_units": row.included_units,
        "overage_units": row.overage_units,
        "flag_payload_json": dict(row.flag_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _campaign_payload(row: CampaignRow) -> Dict[str, Any]:
    return {
        "campaign_id": row.campaign_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "title": row.title,
        "target_icp_vertical": row.target_icp_vertical,
        "cta_text": row.cta_text,
        "disclosure_text": row.disclosure_text,
        "activation_status": row.activation_status,
        "selected_channels_json": list(row.selected_channels_json or []),
        "selected_partner_refs_json": list(row.selected_partner_refs_json or []),
        "primary_review_case_id": row.primary_review_case_id,
        "latest_submission_id": row.latest_submission_id,
        "campaign_payload_json": dict(row.campaign_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _campaign_proof_bundle_payload(row: CampaignProofBundleRow) -> Dict[str, Any]:
    return {
        "proof_bundle_id": row.proof_bundle_id,
        "campaign_id": row.campaign_id,
        "bundle_label": row.bundle_label,
        "proof_points_json": list(row.proof_points_json or []),
        "source_urls_json": list(row.source_urls_json or []),
        "artifact_refs_json": list(row.artifact_refs_json or []),
        "bundle_payload_json": dict(row.bundle_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _campaign_channel_target_payload(row: CampaignChannelTargetRow) -> Dict[str, Any]:
    return {
        "channel_target_id": row.channel_target_id,
        "campaign_id": row.campaign_id,
        "channel_name": row.channel_name,
        "partner_ref": row.partner_ref,
        "priority": row.priority,
        "readiness_status": row.readiness_status,
        "target_payload_json": dict(row.target_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _campaign_review_submission_payload(row: CampaignReviewSubmissionRow) -> Dict[str, Any]:
    return {
        "submission_id": row.submission_id,
        "campaign_id": row.campaign_id,
        "review_case_id": row.review_case_id,
        "status": row.status,
        "submitted_by": row.submitted_by,
        "reviewer_id": row.reviewer_id,
        "decision_note": row.decision_note,
        "submitted_at": row.submitted_at,
        "decided_at": row.decided_at,
        "submission_payload_json": dict(row.submission_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _partner_payload(row: PartnerRow) -> Dict[str, Any]:
    return {
        "partner_id": row.partner_id,
        "name": row.name,
        "lifecycle_status": row.lifecycle_status,
        "sla_status": row.sla_status,
        "receipt_capability": row.receipt_capability,
        "disclosure_readiness": row.disclosure_readiness,
        "billing_readiness": row.billing_readiness,
        "allowlisted_channels_json": list(row.allowlisted_channels_json or []),
        "primary_endpoint_url": row.primary_endpoint_url,
        "endpoint_health_status": row.endpoint_health_status,
        "partner_payload_json": dict(row.partner_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _partner_capability_payload(row: PartnerCapabilityRow) -> Dict[str, Any]:
    return {
        "partner_capability_id": row.partner_capability_id,
        "partner_id": row.partner_id,
        "capability_type": row.capability_type,
        "status": row.status,
        "capability_value": row.capability_value,
        "capability_payload_json": dict(row.capability_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _partner_health_check_payload(row: PartnerHealthCheckRow) -> Dict[str, Any]:
    return {
        "health_check_id": row.health_check_id,
        "partner_id": row.partner_id,
        "endpoint_url": row.endpoint_url,
        "status": row.status,
        "status_code": row.status_code,
        "response_time_ms": row.response_time_ms,
        "checked_at": row.checked_at,
        "health_payload_json": dict(row.health_payload_json or {}),
        "created_at": row.created_at,
    }


def _dispute_payload(row: DisputeRow) -> Dict[str, Any]:
    return {
        "dispute_id": row.dispute_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "campaign_id": row.campaign_id,
        "invoice_preview_id": row.invoice_preview_id,
        "billable_event_id": row.billable_event_id,
        "quality_event_id": row.quality_event_id,
        "trace_id": row.trace_id,
        "dispute_reason_code": row.dispute_reason_code,
        "note": row.note,
        "status": row.status,
        "requested_amount_usd": row.requested_amount_usd,
        "resolved_amount_usd": row.resolved_amount_usd,
        "requested_by": row.requested_by,
        "reviewer_id": row.reviewer_id,
        "resolution_note": row.resolution_note,
        "dispute_payload_json": dict(row.dispute_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _refund_request_payload(row: RefundRequestRow) -> Dict[str, Any]:
    return {
        "refund_request_id": row.refund_request_id,
        "dispute_id": row.dispute_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "invoice_preview_id": row.invoice_preview_id,
        "billable_event_id": row.billable_event_id,
        "trace_id": row.trace_id,
        "status": row.status,
        "requested_amount_usd": row.requested_amount_usd,
        "approved_amount_usd": row.approved_amount_usd,
        "requested_by": row.requested_by,
        "reviewer_id": row.reviewer_id,
        "refund_payload_json": dict(row.refund_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _settlement_run_payload(row: SettlementRunRow) -> Dict[str, Any]:
    return {
        "settlement_run_id": row.settlement_run_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "billing_period_start": row.billing_period_start,
        "billing_period_end": row.billing_period_end,
        "status": row.status,
        "subtotal_amount_usd": row.subtotal_amount_usd,
        "disputed_amount_usd": row.disputed_amount_usd,
        "credited_amount_usd": row.credited_amount_usd,
        "reversed_amount_usd": row.reversed_amount_usd,
        "refunded_amount_usd": row.refunded_amount_usd,
        "net_amount_usd": row.net_amount_usd,
        "run_payload_json": dict(row.run_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _settlement_item_payload(row: SettlementItemRow) -> Dict[str, Any]:
    return {
        "settlement_item_id": row.settlement_item_id,
        "settlement_run_id": row.settlement_run_id,
        "billable_event_id": row.billable_event_id,
        "invoice_preview_id": row.invoice_preview_id,
        "dispute_id": row.dispute_id,
        "refund_request_id": row.refund_request_id,
        "status": row.status,
        "amount_usd": row.amount_usd,
        "item_payload_json": dict(row.item_payload_json or {}),
        "created_at": row.created_at,
    }


def _support_case_payload(row: SupportCaseRow) -> Dict[str, Any]:
    return {
        "support_case_id": row.support_case_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "campaign_id": row.campaign_id,
        "invoice_preview_id": row.invoice_preview_id,
        "billable_event_id": row.billable_event_id,
        "quality_event_id": row.quality_event_id,
        "trace_id": row.trace_id,
        "case_type": row.case_type,
        "subject": row.subject,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "requested_by": row.requested_by,
        "owner_id": row.owner_id,
        "resolution_note": row.resolution_note,
        "support_payload_json": dict(row.support_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _manual_adjustment_payload(row: ManualAdjustmentRow) -> Dict[str, Any]:
    return {
        "adjustment_id": row.adjustment_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "dispute_id": row.dispute_id,
        "refund_request_id": row.refund_request_id,
        "invoice_preview_id": row.invoice_preview_id,
        "billable_event_id": row.billable_event_id,
        "adjustment_type": row.adjustment_type,
        "amount_usd": row.amount_usd,
        "status": row.status,
        "requested_by": row.requested_by,
        "reviewer_id": row.reviewer_id,
        "adjustment_payload_json": dict(row.adjustment_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _audit_log_payload(row: AuditLogRow) -> Dict[str, Any]:
    return {
        "audit_log_id": row.audit_log_id,
        "actor_id": row.actor_id,
        "actor_role": row.actor_role,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "action_type": row.action_type,
        "source_surface": row.source_surface,
        "customer_visible_payload_json": dict(row.customer_visible_payload_json or {}),
        "internal_payload_json": dict(row.internal_payload_json or {}),
        "created_at": row.created_at,
    }


def _customer_audit_export_payload(row: CustomerAuditExportRow) -> Dict[str, Any]:
    return {
        "audit_export_id": row.audit_export_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "requested_by": row.requested_by,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "export_payload_json": dict(row.export_payload_json or {}),
        "created_at": row.created_at,
    }


def _data_retention_policy_payload(row: DataRetentionPolicyRow) -> Dict[str, Any]:
    return {
        "retention_policy_id": row.retention_policy_id,
        "scope": row.scope,
        "retention_days": row.retention_days,
        "deletion_mode": row.deletion_mode,
        "status": row.status,
        "policy_payload_json": dict(row.policy_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _data_deletion_request_payload(row: DataDeletionRequestRow) -> Dict[str, Any]:
    return {
        "deletion_request_id": row.deletion_request_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "requested_by": row.requested_by,
        "scope": row.scope,
        "status": row.status,
        "requested_payload_json": dict(row.requested_payload_json or {}),
        "affected_object_counts_json": dict(row.affected_object_counts_json or {}),
        "resolution_note": row.resolution_note,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _invoice_issuance_payload(row: InvoiceIssuanceRow) -> Dict[str, Any]:
    return {
        "invoice_id": row.invoice_id,
        "invoice_preview_id": row.invoice_preview_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "provider": row.provider,
        "provider_invoice_ref": row.provider_invoice_ref,
        "provider_customer_ref": row.provider_customer_ref,
        "status": row.status,
        "currency": row.currency,
        "subtotal_amount_usd": row.subtotal_amount_usd,
        "total_due_usd": row.total_due_usd,
        "hosted_invoice_url": row.hosted_invoice_url,
        "invoice_pdf_url": row.invoice_pdf_url,
        "issued_at": row.issued_at,
        "paid_at": row.paid_at,
        "voided_at": row.voided_at,
        "invoice_payload_json": dict(row.invoice_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _payment_transaction_payload(row: PaymentTransactionRow) -> Dict[str, Any]:
    return {
        "payment_transaction_id": row.payment_transaction_id,
        "invoice_id": row.invoice_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "provider": row.provider,
        "provider_transaction_ref": row.provider_transaction_ref,
        "transaction_type": row.transaction_type,
        "status": row.status,
        "amount_usd": row.amount_usd,
        "currency": row.currency,
        "trace_id": row.trace_id,
        "transaction_payload_json": dict(row.transaction_payload_json or {}),
        "occurred_at": row.occurred_at,
        "created_at": row.created_at,
    }


def _provider_webhook_event_payload(row: ProviderWebhookEventRow) -> Dict[str, Any]:
    return {
        "provider_webhook_event_id": row.provider_webhook_event_id,
        "provider": row.provider,
        "provider_event_id": row.provider_event_id,
        "event_type": row.event_type,
        "status": row.status,
        "invoice_id": row.invoice_id,
        "account_id": row.account_id,
        "payload_json": dict(row.payload_json or {}),
        "processing_result_json": dict(row.processing_result_json or {}),
        "created_at": row.created_at,
        "processed_at": row.processed_at,
    }


def _credit_note_payload(row: CreditNoteRow) -> Dict[str, Any]:
    return {
        "credit_note_id": row.credit_note_id,
        "invoice_id": row.invoice_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "provider": row.provider,
        "provider_credit_note_ref": row.provider_credit_note_ref,
        "status": row.status,
        "amount_usd": row.amount_usd,
        "reason": row.reason,
        "credit_payload_json": dict(row.credit_payload_json or {}),
        "created_at": row.created_at,
    }


def _payment_retry_attempt_payload(row: PaymentRetryAttemptRow) -> Dict[str, Any]:
    return {
        "payment_retry_attempt_id": row.payment_retry_attempt_id,
        "invoice_id": row.invoice_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "provider": row.provider,
        "status": row.status,
        "retry_reason": row.retry_reason,
        "attempt_count": row.attempt_count,
        "next_retry_at": row.next_retry_at,
        "retry_payload_json": dict(row.retry_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _dunning_event_payload(row: DunningEventRow) -> Dict[str, Any]:
    return {
        "dunning_event_id": row.dunning_event_id,
        "invoice_id": row.invoice_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "status": row.status,
        "step": row.step,
        "event_payload_json": dict(row.event_payload_json or {}),
        "created_at": row.created_at,
    }


def _renewal_tracker_payload(row: RenewalTrackerRow) -> Dict[str, Any]:
    return {
        "renewal_tracker_id": row.renewal_tracker_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "status": row.status,
        "renewal_due_at": row.renewal_due_at,
        "tracker_payload_json": dict(row.tracker_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _dunning_run_payload(row: DunningRunRow) -> Dict[str, Any]:
    return {
        "dunning_run_id": row.dunning_run_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "invoice_id": row.invoice_id,
        "status": row.status,
        "current_step": row.current_step,
        "dunning_payload_json": dict(row.dunning_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _pilot_conversion_track_payload(row: PilotConversionTrackRow) -> Dict[str, Any]:
    return {
        "pilot_conversion_track_id": row.pilot_conversion_track_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "status": row.status,
        "track_payload_json": dict(row.track_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _expansion_candidate_payload(row: ExpansionCandidateRow) -> Dict[str, Any]:
    return {
        "expansion_candidate_id": row.expansion_candidate_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "status": row.status,
        "trigger_type": row.trigger_type,
        "candidate_payload_json": dict(row.candidate_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _churn_risk_flag_payload(row: ChurnRiskFlagRow) -> Dict[str, Any]:
    return {
        "churn_risk_flag_id": row.churn_risk_flag_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "status": row.status,
        "risk_level": row.risk_level,
        "flag_payload_json": dict(row.flag_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_signoff_payload(row: ProductionSignoffRow) -> Dict[str, Any]:
    return {
        "signoff_id": row.signoff_id,
        "launch_label": row.launch_label,
        "status": row.status,
        "source_go_live_checklist_id": row.source_go_live_checklist_id,
        "source_manual_signoff_bundle_id": row.source_manual_signoff_bundle_id,
        "rollup_summary_json": dict(row.rollup_summary_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_signoff_item_payload(row: ProductionSignoffItemRow) -> Dict[str, Any]:
    return {
        "signoff_item_id": row.signoff_item_id,
        "signoff_id": row.signoff_id,
        "item_code": row.item_code,
        "category": row.category,
        "label": row.label,
        "owner_role": row.owner_role,
        "owner_actor_id": row.owner_actor_id,
        "due_at": row.due_at,
        "status": row.status,
        "decision_note": row.decision_note,
        "approved_at": row.approved_at,
        "evidence_count": int(row.evidence_count or 0),
        "item_payload_json": dict(row.item_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_signoff_evidence_payload(row: ProductionSignoffEvidenceRow) -> Dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "signoff_id": row.signoff_id,
        "signoff_item_id": row.signoff_item_id,
        "evidence_type": row.evidence_type,
        "source_ref_json": dict(row.source_ref_json or {}),
        "summary": row.summary,
        "customer_safe": bool(row.customer_safe),
        "payload_json": dict(row.payload_json or {}),
        "created_at": row.created_at,
    }


def _production_cutover_window_payload(row: ProductionCutoverWindowRow) -> Dict[str, Any]:
    return {
        "cutover_window_id": row.cutover_window_id,
        "signoff_id": row.signoff_id,
        "launch_wave": row.launch_wave,
        "target_environment": row.target_environment,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "rollback_owner_role": row.rollback_owner_role,
        "status": row.status,
        "cutover_payload_json": dict(row.cutover_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_customer_acceptance_record_payload(row: ProductionCustomerAcceptanceRecordRow) -> Dict[str, Any]:
    return {
        "acceptance_record_id": row.acceptance_record_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "signoff_id": row.signoff_id,
        "launch_wave": row.launch_wave,
        "status": row.status,
        "readiness_summary_json": dict(row.readiness_summary_json or {}),
        "acceptance_payload_json": dict(row.acceptance_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _go_live_ready_account_payload(row: GoLiveReadyAccountRow) -> Dict[str, Any]:
    return {
        "go_live_ready_account_id": row.go_live_ready_account_id,
        "customer_account_id": row.customer_account_id,
        "account_id": row.account_id,
        "acceptance_record_id": row.acceptance_record_id,
        "launch_wave": row.launch_wave,
        "status": row.status,
        "readiness_payload_json": dict(row.readiness_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _launch_wave_status_payload(row: LaunchWaveStatusRow) -> Dict[str, Any]:
    return {
        "launch_wave_status_id": row.launch_wave_status_id,
        "launch_wave": row.launch_wave,
        "status": row.status,
        "target_environment": row.target_environment,
        "wave_payload_json": dict(row.wave_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_preflight_run_payload(row: ProductionPreflightRunRow) -> Dict[str, Any]:
    return {
        "preflight_run_id": row.preflight_run_id,
        "signoff_id": row.signoff_id,
        "launch_wave": row.launch_wave,
        "target_environment": row.target_environment,
        "status": row.status,
        "go_no_go": row.go_no_go,
        "hard_fail_count": int(row.hard_fail_count or 0),
        "soft_fail_count": int(row.soft_fail_count or 0),
        "run_payload_json": dict(row.run_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_preflight_check_payload(row: ProductionPreflightCheckRow) -> Dict[str, Any]:
    return {
        "preflight_check_id": row.preflight_check_id,
        "preflight_run_id": row.preflight_run_id,
        "check_key": row.check_key,
        "linked_signoff_item_code": row.linked_signoff_item_code,
        "owner_role": row.owner_role,
        "status": row.status,
        "summary": row.summary,
        "evidence_ref": row.evidence_ref,
        "payload_json": dict(row.payload_json or {}),
        "created_at": row.created_at,
    }


def _first_7_day_outcome_payload(row: First7DayOutcomeRow) -> Dict[str, Any]:
    return {
        "first_7_day_outcome_id": row.first_7_day_outcome_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "launch_wave": row.launch_wave,
        "launch_anchor_at": row.launch_anchor_at,
        "outcome_payload_json": dict(row.outcome_payload_json or {}),
        "generated_at": row.generated_at,
    }


def _first_30_day_value_summary_payload(row: First30DayValueSummaryRow) -> Dict[str, Any]:
    return {
        "first_30_day_value_summary_id": row.first_30_day_value_summary_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "launch_wave": row.launch_wave,
        "launch_anchor_at": row.launch_anchor_at,
        "provisional": bool(row.provisional),
        "summary_payload_json": dict(row.summary_payload_json or {}),
        "generated_at": row.generated_at,
    }


def _pilot_to_paid_readiness_score_payload(row: PilotToPaidReadinessScoreRow) -> Dict[str, Any]:
    return {
        "pilot_to_paid_readiness_score_id": row.pilot_to_paid_readiness_score_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "launch_wave": row.launch_wave,
        "launch_anchor_at": row.launch_anchor_at,
        "score": float(row.score or 0.0),
        "band": row.band,
        "score_payload_json": dict(row.score_payload_json or {}),
        "generated_at": row.generated_at,
    }


def _customer_success_snapshot_payload(row: CustomerSuccessSnapshotRow) -> Dict[str, Any]:
    return {
        "customer_success_snapshot_id": row.customer_success_snapshot_id,
        "account_id": row.account_id,
        "customer_account_id": row.customer_account_id,
        "launch_wave": row.launch_wave,
        "launch_anchor_at": row.launch_anchor_at,
        "snapshot_payload_json": dict(row.snapshot_payload_json or {}),
        "generated_at": row.generated_at,
    }


def _library_stats_cube_payload(row: LibraryStatsCubeRow) -> Dict[str, Any]:
    return {
        "library_stats_cube_id": row.library_stats_cube_id,
        "account_id": row.account_id,
        "semantic_version": row.semantic_version,
        "snapshot_payload_json": dict(row.snapshot_payload_json or {}),
        "source_breakdown_json": dict(row.source_breakdown_json or {}),
        "source_updated_at": row.source_updated_at,
        "invalidated_at": row.invalidated_at,
        "last_invalidated_event_name": row.last_invalidated_event_name,
        "last_invalidated_event_at": row.last_invalidated_event_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _production_launch_event_payload(row: ProductionLaunchEventRow) -> Dict[str, Any]:
    return {
        "launch_event_id": row.launch_event_id,
        "launch_wave": row.launch_wave,
        "account_id": row.account_id,
        "event_category": row.event_category,
        "event_type": row.event_type,
        "phase": row.phase,
        "severity": row.severity,
        "related_object_type": row.related_object_type,
        "related_object_id": row.related_object_id,
        "occurred_at": row.occurred_at,
        "event_payload_json": dict(row.event_payload_json or {}),
        "created_at": row.created_at,
    }


def _production_postmortem_record_payload(row: ProductionPostmortemRecordRow) -> Dict[str, Any]:
    return {
        "postmortem_record_id": row.postmortem_record_id,
        "launch_wave": row.launch_wave,
        "account_id": row.account_id,
        "status": row.status,
        "summary_json": dict(row.summary_json or {}),
        "generated_at": row.generated_at,
    }


def _go_live_day_run_payload(row: GoLiveDayRunRow) -> Dict[str, Any]:
    return {
        "go_live_day_run_id": row.go_live_day_run_id,
        "signoff_id": row.signoff_id,
        "launch_wave": row.launch_wave,
        "account_id": row.account_id,
        "status": row.status,
        "activation_state_before": row.activation_state_before,
        "activation_state_after": row.activation_state_after,
        "report_payload_json": dict(row.report_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _go_live_day_checkpoint_payload(row: GoLiveDayCheckpointRow) -> Dict[str, Any]:
    return {
        "go_live_day_checkpoint_id": row.go_live_day_checkpoint_id,
        "go_live_day_run_id": row.go_live_day_run_id,
        "checkpoint_key": row.checkpoint_key,
        "status": row.status,
        "summary": row.summary,
        "evidence_ref": row.evidence_ref,
        "rollback_recommendation": row.rollback_recommendation,
        "checkpoint_payload_json": dict(row.checkpoint_payload_json or {}),
        "created_at": row.created_at,
    }


def _launch_week_guard_run_payload(row: LaunchWeekGuardRunRow) -> Dict[str, Any]:
    return {
        "launch_week_guard_run_id": row.launch_week_guard_run_id,
        "launch_wave": row.launch_wave,
        "account_id": row.account_id,
        "status": row.status,
        "replication_readiness": row.replication_readiness,
        "summary_json": dict(row.summary_json or {}),
        "generated_at": row.generated_at,
    }


def _first_customer_success_pack_payload(row: FirstCustomerSuccessPackRow) -> Dict[str, Any]:
    return {
        "first_customer_success_pack_id": row.first_customer_success_pack_id,
        "launch_wave": row.launch_wave,
        "account_id": row.account_id,
        "status": row.status,
        "pack_payload_json": dict(row.pack_payload_json or {}),
        "generated_at": row.generated_at,
    }


def _quality_event_payload(row: QualityEventRow) -> Dict[str, Any]:
    return {
        "event_id": row.event_id,
        "trace_id": row.trace_id,
        "event_type": row.event_type,
        "source_surface": row.source_surface,
        "status": row.status,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "source_ref": dict(row.source_ref_json or {}),
        "payload": dict(row.payload_json or {}),
        "created_at": row.created_at,
    }


def _content_quality_score_payload(row: ContentQualityScoreRow) -> Dict[str, Any]:
    return {
        "score_id": row.score_id,
        "trace_id": row.trace_id,
        "source_surface": row.source_surface,
        "status": row.status,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "chapter_id": row.chapter_id,
        "rubric_version": row.rubric_version,
        "overall_score": float(row.overall_score or 0.0),
        "veto": bool(row.veto),
        "dimension_scores": dict(row.dimension_scores_json or {}),
        "reason_codes": list(row.reason_codes_json or []),
        "evidence_refs": list(row.evidence_refs_json or []),
        "score_payload": dict(row.score_payload_json or {}),
        "created_at": row.created_at,
    }


def _review_case_payload(row: ReviewCaseRow) -> Dict[str, Any]:
    return {
        "case_id": row.case_id,
        "trace_id": row.trace_id,
        "case_type": row.case_type,
        "status": row.status,
        "owner_id": row.owner_id,
        "source_surface": row.source_surface,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "score_id": row.score_id,
        "source_ref": dict(row.source_ref_json or {}),
        "reason_codes": list(row.reason_codes_json or []),
        "evidence_refs": list(row.evidence_refs_json or []),
        "case_payload": dict(row.case_payload_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _quality_feedback_item_payload(row: QualityFeedbackItemRow) -> Dict[str, Any]:
    return {
        "feedback_item_id": row.feedback_item_id,
        "trace_id": row.trace_id,
        "source_event_id": row.source_event_id,
        "feedback_type": row.feedback_type,
        "signal": row.signal,
        "source_surface": row.source_surface,
        "account_id": row.account_id,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "chapter_id": row.chapter_id,
        "source_ref": dict(row.source_ref_json or {}),
        "payload": dict(row.payload_json or {}),
        "created_at": row.created_at,
    }


def _grounding_check_payload(row: GroundingCheckRow) -> Dict[str, Any]:
    return {
        "grounding_check_id": row.grounding_check_id,
        "trace_id": row.trace_id,
        "status": row.status,
        "confidence": float(row.confidence or 0.0),
        "source_surface": row.source_surface,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "chapter_id": row.chapter_id,
        "evidence_refs": list(row.evidence_refs_json or []),
        "unsupported_claims": list(row.unsupported_claims_json or []),
        "reason_codes": list(row.reason_codes_json or []),
        "summary": row.summary,
        "created_at": row.created_at,
    }


def _author_work_payload(row: AuthorWorkRow) -> Dict[str, Any]:
    root_work_id = row.root_work_id or row.work_id
    branch_id = row.branch_id or row.work_id
    branch_kind = row.branch_kind or ("mainline" if root_work_id == row.work_id else "parallel_universe")
    branch_name = row.branch_name or ("主线" if root_work_id == row.work_id else "平行宇宙")
    if row.is_active_line is None:
        is_active_line = bool(root_work_id == row.work_id)
    else:
        is_active_line = bool(row.is_active_line)
    return {
        "work_id": row.work_id,
        "world_version_id": row.world_version_id,
        "account_id": row.account_id,
        "title": row.title,
        "status": row.status,
        "current_revision": row.current_revision,
        "chapter_count": row.chapter_count,
        "target_chapter_count": row.target_chapter_count,
        "branch_id": branch_id,
        "root_work_id": root_work_id,
        "parent_work_id": row.parent_work_id,
        "branch_name": branch_name,
        "branch_kind": branch_kind,
        "branch_origin_label": row.branch_origin_label,
        "fork_after_chapter_index": int(row.fork_after_chapter_index or 0),
        "is_active_line": is_active_line,
        "narrative_state_json": dict(row.narrative_state_json or {}),
        "diagnostics_summary_json": dict(row.diagnostics_summary_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _author_work_chapter_payload(row: AuthorWorkChapterRow) -> Dict[str, Any]:
    return {
        "chapter_record_id": row.chapter_record_id,
        "work_id": row.work_id,
        "chapter_index": row.chapter_index,
        "chapter_title": row.chapter_title,
        "body": row.body,
        "status": row.status,
        "source_type": row.source_type,
        "summary": row.summary,
        "diagnostic_summary_json": dict(row.diagnostic_summary_json or {}),
        "chapter_task_json": dict(row.chapter_task_json or {}),
        "choices_json": list(row.choices_json or []),
        "state_snapshot_json": dict(row.state_snapshot_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _route_choice_payload(row: RouteChoiceRow) -> Dict[str, Any]:
    return {
        "choice_event_id": int(row.choice_event_id),
        "session_id": row.session_id,
        "chapter_id": row.chapter_id,
        "choice_id": row.choice_id,
        "selected_at": row.selected_at,
        "payload_json": dict(row.payload_json or {}),
    }


def _author_work_revision_payload(row: AuthorWorkRevisionRow) -> Dict[str, Any]:
    return {
        "revision_id": row.revision_id,
        "work_id": row.work_id,
        "revision_type": row.revision_type,
        "summary": row.summary,
        "snapshot_json": dict(row.snapshot_json or {}),
        "created_at": row.created_at,
    }


def _soul_profile_preference_payload(row: SoulProfilePreferenceRow) -> Dict[str, Any]:
    return {
        "actor_id": row.actor_id,
        "account_id": row.account_id,
        "genres": list(row.genres_json or []),
        "styles": list(row.styles_json or []),
        "privacy_mode": row.privacy_mode,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _library_work_favorite_payload(row: LibraryWorkFavoriteRow) -> Dict[str, Any]:
    return {
        "favorite_id": row.favorite_id,
        "account_id": row.account_id,
        "work_id": row.work_id,
        "work_kind": row.work_kind,
        "title_snapshot": row.title_snapshot,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _library_follow_payload(row: LibraryFollowRow) -> Dict[str, Any]:
    return {
        "follow_id": row.follow_id,
        "account_id": row.account_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _showcase_work_view_payload(row: ShowcaseWorkViewRow) -> Dict[str, Any]:
    return {
        "showcase_view_id": row.showcase_view_id,
        "world_id": row.world_id,
        "world_version_id": row.world_version_id,
        "account_id": row.account_id,
        "viewer_key": row.viewer_key,
        "event_type": row.event_type,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _generated_media_asset_payload(row: GeneratedMediaAssetRow) -> Dict[str, Any]:
    return {
        "asset_id": row.asset_id,
        "asset_kind": row.asset_kind,
        "owner_scope": row.owner_scope,
        "owner_id": row.owner_id,
        "world_id": row.world_id,
        "world_version_id": row.world_version_id,
        "session_id": row.session_id,
        "chapter_index": row.chapter_index,
        "reader_id": row.reader_id,
        "storage_bucket": row.storage_bucket,
        "storage_key": row.storage_key,
        "mime_type": row.mime_type,
        "width": row.width,
        "height": row.height,
        "visibility": row.visibility,
        "generation_status": row.generation_status,
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "source_fingerprint": row.source_fingerprint,
        "prompt_trace_json": dict(row.prompt_trace_json or {}),
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _author_project_graph_payload(row: AuthorProjectGraphRow) -> Dict[str, Any]:
    return {
        "project_id": row.project_id,
        "world_version_id": row.world_version_id,
        "account_id": row.account_id,
        "engine": row.engine,
        "enabled_rule_ids": list(row.enabled_rule_ids_json or []),
        "nodes": list(row.nodes_json or []),
        "connections": list(row.connections_json or []),
        "metadata_json": dict(row.metadata_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pearson_correlation(points: List[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / float(len(xs))
    mean_y = sum(ys) / float(len(ys))
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = sqrt(denom_x * denom_y)
    if denominator == 0.0:
        return 0.0
    return round(numerator / denominator, 3)


def _continuation_recommended_action(
    *,
    sample_count: int,
    positive_count: int,
    negative_count: int,
    target_sample_count: int,
) -> str:
    if sample_count == 0:
        return "collect_first_reader_sessions"
    if negative_count < CONTINUATION_TARGET_NEGATIVE_SAMPLES:
        return "collect_more_abandonment_or_stale_tail_samples"
    if positive_count == 0:
        return "collect_more_successful_continue_sessions"
    if sample_count < target_sample_count:
        return "collect_more_mixed_reader_sessions"
    return "coverage_sufficient"


def _correlation_lookup(entries: List[Dict[str, Any]], metric: str) -> Optional[float]:
    for item in entries:
        if str(item.get("metric") or "") == metric:
            return float(item.get("correlation", 0.0) or 0.0)
    return None


def _calibration_recommendation(*, sample_gap: int, correlation: Optional[float], positive_direction: bool) -> str:
    if sample_gap > 0 or correlation is None:
        return "insufficient_coverage"
    if positive_direction:
        return "tighten" if correlation >= 0.15 else "hold"
    return "tighten" if correlation <= -0.15 else "hold"


def _build_q03_q09_calibration_summary(
    correlations: List[Dict[str, Any]],
    signal_summary: Dict[str, Any],
) -> Dict[str, Any]:
    sample_count = int(signal_summary.get("sample_count", 0) or 0)
    sample_gap = int(signal_summary.get("sample_gap", 0) or 0)
    coverage_status = "sufficient" if sample_gap <= 0 and sample_count > 0 else "insufficient_coverage"
    q03_primary_metric = None
    q03_primary_correlation = None
    for metric_name in [
        "semantic_paragraph_similarity_score",
        "event_coverage_gap_score",
        "beat_coverage_gap_score",
        "uncovered_event_count",
        "uncovered_beat_count",
        "overcovered_beat_count",
        "q03_present",
        "paragraph_similarity_score",
        "beat_structure_repetition_score",
        "lexical_repetition_score",
        "n_gram_repetition_score",
    ]:
        correlation = _correlation_lookup(correlations, metric_name)
        if correlation is None:
            continue
        if q03_primary_metric is None or abs(correlation) > abs(float(q03_primary_correlation or 0.0)):
            q03_primary_metric = metric_name
            q03_primary_correlation = correlation
    q09_primary_metric = None
    q09_primary_correlation = None
    for metric_name in ["q09_present", "pacing", "hook_quality"]:
        correlation = _correlation_lookup(correlations, metric_name)
        if correlation is None:
            continue
        if q09_primary_metric is None or abs(correlation) > abs(float(q09_primary_correlation or 0.0)):
            q09_primary_metric = metric_name
            q09_primary_correlation = correlation
    return {
        "coverage_status": coverage_status,
        "sample_count": sample_count,
        "sample_gap": sample_gap,
        "q03": {
            "current_thresholds": dict(LONGFORM_Q03_SIGNAL_THRESHOLDS),
            "primary_metric": q03_primary_metric,
            "primary_correlation": q03_primary_correlation,
            "recommendation": _calibration_recommendation(
                sample_gap=sample_gap,
                correlation=q03_primary_correlation,
                positive_direction=False,
            ),
        },
        "q09": {
            "current_thresholds": {
                "pacing_threshold": float(LONGFORM_SOFT_ISSUE_THRESHOLDS["q09_pacing_threshold"]),
                "hook_threshold": float(LONGFORM_SOFT_ISSUE_THRESHOLDS["q09_hook_threshold"]),
            },
            "primary_metric": q09_primary_metric,
            "primary_correlation": q09_primary_correlation,
            "recommendation": _calibration_recommendation(
                sample_gap=sample_gap,
                correlation=q09_primary_correlation,
                positive_direction=True if q09_primary_metric in {"pacing", "hook_quality"} else False,
            ),
        },
    }


class SQLAlchemyPlatformRepository:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        self.database_url = database_url
        self.database_failover_reason = ""
        try:
            self.engine, self.SessionLocal = create_platform_session_local(database_url)
        except SQLAlchemyError as exc:
            if not (_is_postgres_database_url(database_url) and _env_enabled(DATABASE_FAILOVER_SQLITE_ENV)):
                raise
            failover_url = _serverless_sqlite_failover_url()
            self.database_url = failover_url
            self.database_failover_reason = exc.__class__.__name__
            print(
                "NarrativeOS database failover enabled: Postgres connection failed; using serverless SQLite fallback.",
                flush=True,
            )
            self.engine, self.SessionLocal = create_platform_session_local(failover_url)
        self.registry = FileSystemWorldRegistry()
        self._bootstrap_builtin_worldpacks()

    def _bootstrap_builtin_worldpacks(self) -> None:
        for world_card in self.registry.list_worldpacks():
            worldpack = WorldPack.from_dict(world_card["worldpack"])
            world_version = WorldVersion.from_worldpack(
                worldpack=worldpack,
                world_version_id=world_card["world_version_id"],
                status="published",
            )
            self.save_world_version(world_version, publish=True)

    # World / world version
    def save_world_version(self, world_version: WorldVersion, *, publish: bool = False) -> WorldVersion:
        now = utcnow_iso()
        with self.SessionLocal() as session:
            world_row = session.get(WorldRow, world_version.world_id)
            if world_row is None:
                world_row = WorldRow(
                    world_id=world_version.world_id,
                    latest_version=world_version.world_version_id if publish else None,
                    title=world_version.worldpack_json.get("title", world_version.world_id),
                    status="published" if publish else world_version.status,
                    created_at=now,
                    updated_at=now,
                )
                session.add(world_row)
            else:
                world_row.title = world_version.worldpack_json.get("title", world_version.world_id)
                world_row.status = "published" if publish else world_row.status
                if publish:
                    world_row.latest_version = world_version.world_version_id
                world_row.updated_at = now

            row = session.get(WorldVersionRow, world_version.world_version_id)
            if row is None:
                row = WorldVersionRow(
                    world_version_id=world_version.world_version_id,
                    world_id=world_version.world_id,
                    version=world_version.version,
                    author_id=world_version.author_id,
                    status="published" if publish else world_version.status,
                    risk_rating=world_version.risk_rating,
                    manifest_json=world_version.manifest_json,
                    worldpack_json=world_version.worldpack_json,
                    validation_report_json=world_version.validation_report_json,
                    simulation_report_json=world_version.simulation_report_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.version = world_version.version
                row.author_id = world_version.author_id
                row.status = "published" if publish else world_version.status
                row.risk_rating = world_version.risk_rating
                row.manifest_json = world_version.manifest_json
                row.worldpack_json = world_version.worldpack_json
                row.validation_report_json = world_version.validation_report_json
                row.simulation_report_json = world_version.simulation_report_json
                row.updated_at = now
            session.commit()
        world_version.status = "published" if publish else world_version.status
        return world_version

    def get_world_version(self, world_version_id: str) -> WorldVersion:
        with self.SessionLocal() as session:
            row = session.get(WorldVersionRow, world_version_id)
            if row is None:
                raise KeyError("unknown_world_version:%s" % world_version_id)
            return WorldVersion(
                world_version_id=row.world_version_id,
                world_id=row.world_id,
                version=row.version,
                author_id=row.author_id,
                status=row.status,
                risk_rating=row.risk_rating or "",
                manifest_json=dict(row.manifest_json or {}),
                worldpack_json=dict(row.worldpack_json or {}),
                validation_report_json=dict(row.validation_report_json or {}),
                simulation_report_json=dict(row.simulation_report_json or {}),
            )

    def list_world_versions(self, world_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(WorldVersionRow).order_by(desc(WorldVersionRow.updated_at))
            if world_id is not None:
                stmt = stmt.where(WorldVersionRow.world_id == world_id)
            if status is not None:
                stmt = stmt.where(WorldVersionRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "world_version_id": row.world_version_id,
                    "world_id": row.world_id,
                    "version": row.version,
                    "author_id": row.author_id,
                    "status": row.status,
                    "risk_rating": row.risk_rating,
                    "title": (row.worldpack_json or {}).get("title", row.world_id),
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def list_worlds(self) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            rows = session.execute(select(WorldRow).order_by(desc(WorldRow.updated_at))).scalars()
            worlds = []
            for row in rows:
                latest_worldpack = {}
                if row.latest_version:
                    try:
                        latest_worldpack = self.get_world_version(row.latest_version).worldpack_json
                    except KeyError:
                        latest_worldpack = {}
                latest_metadata = dict(latest_worldpack.get("metadata") or {})
                worlds.append(
                    {
                        "world_id": row.world_id,
                        "title": row.title,
                        "status": row.status,
                        "latest_version": row.latest_version,
                        "genres": list((latest_worldpack.get("manifest") or {}).get("genres", [])),
                        "risk_rating": (latest_worldpack.get("manifest") or {}).get("risk_rating"),
                        "trial_available": ((latest_worldpack.get("manifest") or {}).get("monetization_policy") or {}).get("trial_chapters", 0) > 0,
                        "access_state": "trial",
                        "catalog_role": latest_metadata.get("catalog_role"),
                        "public_catalog_visible": latest_metadata.get("public_catalog_visible"),
                        "claim_safe_band": latest_metadata.get("claim_safe_band"),
                        "product_ready_band": latest_metadata.get("product_ready_band"),
                        "longform_500_product_readiness": dict(latest_metadata.get("longform_500_product_readiness") or {}),
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                )
            return worlds

    # Author works
    def save_author_work(self, work: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        work_id = str(work.get("work_id") or f"work_{uuid4().hex[:12]}")
        root_work_id = str(work.get("root_work_id") or work_id)
        payload = {
            "work_id": work_id,
            "world_version_id": str(work["world_version_id"]),
            "account_id": str(work["account_id"]),
            "title": str(work.get("title") or work["world_version_id"]),
            "status": str(work.get("status") or "draft"),
            "current_revision": work.get("current_revision"),
            "chapter_count": int(work.get("chapter_count", 0) or 0),
            "target_chapter_count": int(work.get("target_chapter_count", 0) or 0),
            "branch_id": str(work.get("branch_id") or work_id),
            "root_work_id": root_work_id,
            "parent_work_id": str(work.get("parent_work_id") or "") or None,
            "branch_name": str(work.get("branch_name") or ("主线" if root_work_id == work_id else "平行宇宙")),
            "branch_kind": str(work.get("branch_kind") or ("mainline" if root_work_id == work_id else "parallel_universe")),
            "branch_origin_label": str(work.get("branch_origin_label") or "") or None,
            "fork_after_chapter_index": int(work.get("fork_after_chapter_index", 0) or 0),
            "is_active_line": 1 if bool(work.get("is_active_line", root_work_id == work_id)) else 0,
            "narrative_state_json": dict(work.get("narrative_state_json") or {}),
            "diagnostics_summary_json": dict(work.get("diagnostics_summary_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthorWorkRow, payload["work_id"])
            if row is None:
                row = AuthorWorkRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.world_version_id = payload["world_version_id"]
                row.account_id = payload["account_id"]
                row.title = payload["title"]
                row.status = payload["status"]
                row.current_revision = payload["current_revision"]
                row.chapter_count = payload["chapter_count"]
                row.target_chapter_count = payload["target_chapter_count"]
                row.branch_id = payload["branch_id"]
                row.root_work_id = payload["root_work_id"]
                row.parent_work_id = payload["parent_work_id"]
                row.branch_name = payload["branch_name"]
                row.branch_kind = payload["branch_kind"]
                row.branch_origin_label = payload["branch_origin_label"]
                row.fork_after_chapter_index = payload["fork_after_chapter_index"]
                row.is_active_line = payload["is_active_line"]
                row.narrative_state_json = payload["narrative_state_json"]
                row.diagnostics_summary_json = payload["diagnostics_summary_json"]
                row.updated_at = now
            session.commit()
            return _author_work_payload(row)

    def get_author_work(self, work_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthorWorkRow, work_id)
            if row is None:
                raise KeyError(f"unknown_author_work:{work_id}")
            return _author_work_payload(row)

    def list_author_works(
        self,
        *,
        account_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        root_work_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorWorkRow).order_by(desc(AuthorWorkRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(AuthorWorkRow.account_id == account_id)
            if world_version_id is not None:
                stmt = stmt.where(AuthorWorkRow.world_version_id == world_version_id)
            if root_work_id is not None:
                stmt = stmt.where(AuthorWorkRow.root_work_id == root_work_id)
            if status is not None:
                stmt = stmt.where(AuthorWorkRow.status == status)
            rows = session.execute(stmt.limit(limit)).scalars().all()
            return [_author_work_payload(row) for row in rows]

    def set_author_work_active_line(self, *, root_work_id: str, active_work_id: str) -> None:
        with self.SessionLocal() as session:
            rows = session.execute(
                select(AuthorWorkRow).where(AuthorWorkRow.root_work_id == root_work_id)
            ).scalars().all()
            for row in rows:
                row.is_active_line = 1 if row.work_id == active_work_id else 0
                row.updated_at = utcnow_iso()
            session.commit()

    def delete_author_work_family(self, *, root_work_id: str) -> Dict[str, Any]:
        normalized_root_work_id = str(root_work_id or "").strip()
        if not normalized_root_work_id:
            raise KeyError("unknown_author_work_family:")
        with self.SessionLocal() as session:
            work_rows = session.execute(
                select(AuthorWorkRow).where(
                    or_(
                        AuthorWorkRow.root_work_id == normalized_root_work_id,
                        AuthorWorkRow.work_id == normalized_root_work_id,
                    )
                )
            ).scalars().all()
            if not work_rows:
                raise KeyError(f"unknown_author_work_family:{normalized_root_work_id}")
            work_ids = [str(row.work_id) for row in work_rows]
            chapter_rows = session.execute(
                select(AuthorWorkChapterRow).where(AuthorWorkChapterRow.work_id.in_(work_ids))
            ).scalars().all()
            revision_rows = session.execute(
                select(AuthorWorkRevisionRow).where(AuthorWorkRevisionRow.work_id.in_(work_ids))
            ).scalars().all()
            for row in chapter_rows:
                session.delete(row)
            for row in revision_rows:
                session.delete(row)
            deleted_titles = []
            for row in work_rows:
                if row.title and row.title not in deleted_titles:
                    deleted_titles.append(row.title)
                session.delete(row)
            session.commit()
        return {
            "root_work_id": normalized_root_work_id,
            "deleted_work_ids": work_ids,
            "deleted_work_count": len(work_ids),
            "deleted_chapter_count": len(chapter_rows),
            "deleted_revision_count": len(revision_rows),
            "deleted_titles": deleted_titles,
        }

    def save_author_work_chapter(self, chapter: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "chapter_record_id": str(chapter.get("chapter_record_id") or f"workchapter_{uuid4().hex[:12]}"),
            "work_id": str(chapter["work_id"]),
            "chapter_index": int(chapter["chapter_index"]),
            "chapter_title": str(chapter.get("chapter_title") or f"第 {int(chapter['chapter_index'])} 章"),
            "body": str(chapter.get("body") or ""),
            "status": str(chapter.get("status") or "generated"),
            "source_type": str(chapter.get("source_type") or "generated"),
            "summary": chapter.get("summary"),
            "diagnostic_summary_json": dict(chapter.get("diagnostic_summary_json") or {}),
            "chapter_task_json": dict(chapter.get("chapter_task_json") or {}),
            "choices_json": list(chapter.get("choices_json") or []),
            "state_snapshot_json": dict(chapter.get("state_snapshot_json") or {}),
        }
        with self.SessionLocal() as session:
            stmt = select(AuthorWorkChapterRow).where(
                AuthorWorkChapterRow.work_id == payload["work_id"],
                AuthorWorkChapterRow.chapter_index == payload["chapter_index"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = AuthorWorkChapterRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.chapter_title = payload["chapter_title"]
                row.body = payload["body"]
                row.status = payload["status"]
                row.source_type = payload["source_type"]
                row.summary = payload["summary"]
                row.diagnostic_summary_json = payload["diagnostic_summary_json"]
                row.chapter_task_json = payload["chapter_task_json"]
                row.choices_json = payload["choices_json"]
                row.state_snapshot_json = payload["state_snapshot_json"]
                row.updated_at = now
            session.commit()
            return _author_work_chapter_payload(row)

    def get_author_work_chapter(self, *, work_id: str, chapter_index: int) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(AuthorWorkChapterRow).where(
                AuthorWorkChapterRow.work_id == work_id,
                AuthorWorkChapterRow.chapter_index == chapter_index,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                raise KeyError(f"unknown_author_work_chapter:{work_id}:{chapter_index}")
            return _author_work_chapter_payload(row)

    def list_author_work_chapters(self, *, work_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = (
                select(AuthorWorkChapterRow)
                .where(AuthorWorkChapterRow.work_id == work_id)
                .order_by(AuthorWorkChapterRow.chapter_index.asc())
            )
            rows = session.execute(stmt).scalars().all()
            return [_author_work_chapter_payload(row) for row in rows]

    def save_author_work_revision(self, revision: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "revision_id": str(revision.get("revision_id") or f"workrev_{uuid4().hex[:12]}"),
            "work_id": str(revision["work_id"]),
            "revision_type": str(revision.get("revision_type") or "update"),
            "summary": revision.get("summary"),
            "snapshot_json": dict(revision.get("snapshot_json") or {}),
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorWorkRevisionRow, payload["revision_id"])
            if row is None:
                row = AuthorWorkRevisionRow(created_at=now, **payload)
                session.add(row)
            else:
                row.work_id = payload["work_id"]
                row.revision_type = payload["revision_type"]
                row.summary = payload["summary"]
                row.snapshot_json = payload["snapshot_json"]
            session.commit()
            return _author_work_revision_payload(row)

    def list_author_work_revisions(self, *, work_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = (
                select(AuthorWorkRevisionRow)
                .where(AuthorWorkRevisionRow.work_id == work_id)
                .order_by(desc(AuthorWorkRevisionRow.created_at))
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [_author_work_revision_payload(row) for row in rows]

    # Ops review hub
    def save_ops_review_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        review_item_id = str(item.get("review_item_id") or f"ops_review_{uuid4().hex[:12]}")
        payload = {
            "review_item_id": review_item_id,
            "source_type": str(item["source_type"]),
            "source_id": str(item["source_id"]),
            "queue": str(item.get("queue") or "triage"),
            "status": str(item.get("status") or "new"),
            "severity": str(item.get("severity") or "medium"),
            "priority": int(item.get("priority", 100) or 100),
            "owner_id": item.get("owner_id"),
            "reviewer_id": item.get("reviewer_id"),
            "account_id": item.get("account_id"),
            "world_id": item.get("world_id"),
            "world_version_id": item.get("world_version_id"),
            "headline": str(item.get("headline") or item.get("source_id") or review_item_id),
            "summary": item.get("summary"),
            "recommended_action": item.get("recommended_action"),
            "due_at": item.get("due_at"),
            "sla_bucket": item.get("sla_bucket"),
            "allowed_actions_json": list(item.get("allowed_actions") or []),
            "linked_entities_json": list(item.get("linked_entities") or []),
            "source_updated_at": item.get("source_updated_at"),
            "last_synced_at": item.get("last_synced_at") or now,
        }
        with self.SessionLocal() as session:
            row = session.get(OpsReviewItemRow, payload["review_item_id"])
            if row is None:
                row = OpsReviewItemRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.source_type = payload["source_type"]
                row.source_id = payload["source_id"]
                row.queue = payload["queue"]
                row.status = payload["status"]
                row.severity = payload["severity"]
                row.priority = payload["priority"]
                row.owner_id = payload["owner_id"]
                row.reviewer_id = payload["reviewer_id"]
                row.account_id = payload["account_id"]
                row.world_id = payload["world_id"]
                row.world_version_id = payload["world_version_id"]
                row.headline = payload["headline"]
                row.summary = payload["summary"]
                row.recommended_action = payload["recommended_action"]
                row.due_at = payload["due_at"]
                row.sla_bucket = payload["sla_bucket"]
                row.allowed_actions_json = payload["allowed_actions_json"]
                row.linked_entities_json = payload["linked_entities_json"]
                row.source_updated_at = payload["source_updated_at"]
                row.last_synced_at = payload["last_synced_at"]
                row.updated_at = now
            session.commit()
            return _ops_review_item_payload(row)

    def upsert_ops_review_item_by_source(self, item: Dict[str, Any]) -> Dict[str, Any]:
        source_type = str(item["source_type"])
        source_id = str(item["source_id"])
        with self.SessionLocal() as session:
            stmt = (
                select(OpsReviewItemRow)
                .where(OpsReviewItemRow.source_type == source_type)
                .where(OpsReviewItemRow.source_id == source_id)
            )
            row = session.execute(stmt).scalar_one_or_none()
            review_item_id = row.review_item_id if row is not None else item.get("review_item_id")
        return self.save_ops_review_item({**item, "review_item_id": review_item_id})

    def get_ops_review_item(self, review_item_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(OpsReviewItemRow, review_item_id)
            if row is None:
                raise KeyError(f"unknown_ops_review_item:{review_item_id}")
            return _ops_review_item_payload(row)

    def list_ops_review_items(
        self,
        *,
        queue: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        severity: Optional[str] = None,
        source_type: Optional[str] = None,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(OpsReviewItemRow)
            if queue is not None:
                stmt = stmt.where(OpsReviewItemRow.queue == queue)
            if status is not None:
                stmt = stmt.where(OpsReviewItemRow.status == status)
            if owner_id is not None:
                stmt = stmt.where(OpsReviewItemRow.owner_id == owner_id)
            if severity is not None:
                stmt = stmt.where(OpsReviewItemRow.severity == severity)
            if source_type is not None:
                stmt = stmt.where(OpsReviewItemRow.source_type == source_type)
            if account_id is not None:
                stmt = stmt.where(OpsReviewItemRow.account_id == account_id)
            if world_id is not None:
                stmt = stmt.where(OpsReviewItemRow.world_id == world_id)
            if world_version_id is not None:
                stmt = stmt.where(OpsReviewItemRow.world_version_id == world_version_id)
            stmt = stmt.order_by(OpsReviewItemRow.priority.asc(), desc(OpsReviewItemRow.updated_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_ops_review_item_payload(row) for row in rows]

    def save_quality_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "policy_id": str(policy.get("policy_id") or f"quality_policy_{uuid4().hex[:12]}"),
            "version": str(policy.get("version") or "v1"),
            "scenario_id": str(policy.get("scenario_id") or ""),
            "risk_tier": str(policy.get("risk_tier") or ""),
            "mode": str(policy.get("mode") or "observe"),
            "rule_ids_json": [str(item) for item in list(policy.get("rule_ids") or []) if str(item)],
            "policy_payload_json": dict(policy.get("policy_payload") or policy.get("metadata") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(QualityPolicyRow, payload["policy_id"])
            if row is None:
                row = QualityPolicyRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.version = payload["version"]
                row.scenario_id = payload["scenario_id"]
                row.risk_tier = payload["risk_tier"]
                row.mode = payload["mode"]
                row.rule_ids_json = payload["rule_ids_json"]
                row.policy_payload_json = payload["policy_payload_json"]
                row.updated_at = now
            session.commit()
            return _quality_policy_payload(row)

    def list_quality_policies(
        self,
        *,
        scenario_id: Optional[str] = None,
        risk_tier: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(QualityPolicyRow)
            if scenario_id is not None:
                stmt = stmt.where(QualityPolicyRow.scenario_id == scenario_id)
            if risk_tier is not None:
                stmt = stmt.where(QualityPolicyRow.risk_tier == risk_tier)
            stmt = stmt.order_by(desc(QualityPolicyRow.updated_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_quality_policy_payload(row) for row in rows]

    def save_ops_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "ops_config_id": str(config.get("ops_config_id") or f"ops_config_{uuid4().hex[:12]}"),
            "config_type": str(config.get("config_type") or ""),
            "scope_key": str(config.get("scope_key") or "").strip() or None,
            "status": str(config.get("status") or "active"),
            "config_payload_json": dict(config.get("config_payload") or config.get("metadata") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(OpsConfigRow, payload["ops_config_id"])
            if row is None:
                row = OpsConfigRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.config_type = payload["config_type"]
                row.scope_key = payload["scope_key"]
                row.status = payload["status"]
                row.config_payload_json = payload["config_payload_json"]
                row.updated_at = now
            session.commit()
            return _ops_config_payload(row)

    def list_ops_configs(
        self,
        *,
        config_type: Optional[str] = None,
        scope_key: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(OpsConfigRow)
            if config_type is not None:
                stmt = stmt.where(OpsConfigRow.config_type == config_type)
            if scope_key is not None:
                stmt = stmt.where(OpsConfigRow.scope_key == scope_key)
            if status is not None:
                stmt = stmt.where(OpsConfigRow.status == status)
            stmt = stmt.order_by(desc(OpsConfigRow.updated_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_ops_config_payload(row) for row in rows]

    def save_quality_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "event_id": str(event.get("event_id") or f"quality_event_{uuid4().hex[:12]}"),
            "trace_id": str(event.get("trace_id") or ""),
            "event_type": str(event.get("event_type") or ""),
            "source_surface": str(event.get("source_surface") or ""),
            "status": event.get("status"),
            "world_version_id": event.get("world_version_id"),
            "session_id": event.get("session_id"),
            "source_ref_json": dict(event.get("source_ref") or {}),
            "payload_json": dict(event.get("payload") or {}),
            "created_at": str(event.get("created_at") or utcnow_iso()),
        }
        with self.SessionLocal() as session:
            row = session.get(QualityEventRow, payload["event_id"])
            if row is None:
                row = QualityEventRow(**payload)
                session.add(row)
            else:
                row.trace_id = payload["trace_id"]
                row.event_type = payload["event_type"]
                row.source_surface = payload["source_surface"]
                row.status = payload["status"]
                row.world_version_id = payload["world_version_id"]
                row.session_id = payload["session_id"]
                row.source_ref_json = payload["source_ref_json"]
                row.payload_json = payload["payload_json"]
                row.created_at = payload["created_at"]
            session.commit()
            return _quality_event_payload(row)

    def list_quality_events(
        self,
        *,
        trace_id: Optional[str] = None,
        source_surface: Optional[str] = None,
        status: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(QualityEventRow)
            if trace_id is not None:
                stmt = stmt.where(QualityEventRow.trace_id == trace_id)
            if source_surface is not None:
                stmt = stmt.where(QualityEventRow.source_surface == source_surface)
            if status is not None:
                stmt = stmt.where(QualityEventRow.status == status)
            if world_version_id is not None:
                stmt = stmt.where(QualityEventRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(QualityEventRow.session_id == session_id)
            stmt = stmt.order_by(desc(QualityEventRow.created_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_quality_event_payload(row) for row in rows]

    def save_content_quality_score(self, score: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "score_id": str(score.get("score_id") or f"quality_score_{uuid4().hex[:12]}"),
            "trace_id": score.get("trace_id"),
            "source_surface": str(score.get("source_surface") or ""),
            "status": score.get("status"),
            "world_version_id": score.get("world_version_id"),
            "session_id": score.get("session_id"),
            "chapter_id": score.get("chapter_id"),
            "rubric_version": str(score.get("rubric_version") or ""),
            "overall_score": float(score.get("overall_score", 0.0) or 0.0),
            "veto": bool(score.get("veto", False)),
            "dimension_scores_json": dict(score.get("dimension_scores") or {}),
            "reason_codes_json": [str(item) for item in list(score.get("reason_codes") or []) if str(item)],
            "evidence_refs_json": [dict(item or {}) for item in list(score.get("evidence_refs") or [])],
            "score_payload_json": dict(score.get("score_payload") or score.get("metadata") or {}),
            "created_at": str(score.get("created_at") or utcnow_iso()),
        }
        with self.SessionLocal() as session:
            row = session.get(ContentQualityScoreRow, payload["score_id"])
            if row is None:
                row = ContentQualityScoreRow(**payload)
                session.add(row)
            else:
                row.trace_id = payload["trace_id"]
                row.source_surface = payload["source_surface"]
                row.status = payload["status"]
                row.world_version_id = payload["world_version_id"]
                row.session_id = payload["session_id"]
                row.chapter_id = payload["chapter_id"]
                row.rubric_version = payload["rubric_version"]
                row.overall_score = payload["overall_score"]
                row.veto = payload["veto"]
                row.dimension_scores_json = payload["dimension_scores_json"]
                row.reason_codes_json = payload["reason_codes_json"]
                row.evidence_refs_json = payload["evidence_refs_json"]
                row.score_payload_json = payload["score_payload_json"]
                row.created_at = payload["created_at"]
            session.commit()
            return _content_quality_score_payload(row)

    def get_content_quality_score(self, score_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ContentQualityScoreRow, score_id)
            if row is None:
                raise KeyError(f"unknown_content_quality_score:{score_id}")
            return _content_quality_score_payload(row)

    def list_content_quality_scores(
        self,
        *,
        trace_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ContentQualityScoreRow)
            if trace_id is not None:
                stmt = stmt.where(ContentQualityScoreRow.trace_id == trace_id)
            if world_version_id is not None:
                stmt = stmt.where(ContentQualityScoreRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(ContentQualityScoreRow.session_id == session_id)
            if chapter_id is not None:
                stmt = stmt.where(ContentQualityScoreRow.chapter_id == chapter_id)
            stmt = stmt.order_by(desc(ContentQualityScoreRow.created_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_content_quality_score_payload(row) for row in rows]

    def save_review_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "case_id": str(case.get("case_id") or f"review_case_{uuid4().hex[:12]}"),
            "trace_id": case.get("trace_id"),
            "case_type": str(case.get("case_type") or ""),
            "status": str(case.get("status") or "open"),
            "owner_id": case.get("owner_id"),
            "source_surface": case.get("source_surface"),
            "world_version_id": case.get("world_version_id"),
            "session_id": case.get("session_id"),
            "score_id": case.get("score_id"),
            "source_ref_json": dict(case.get("source_ref") or {}),
            "reason_codes_json": [str(item) for item in list(case.get("reason_codes") or []) if str(item)],
            "evidence_refs_json": [dict(item or {}) for item in list(case.get("evidence_refs") or [])],
            "case_payload_json": dict(case.get("case_payload") or case.get("metadata") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ReviewCaseRow, payload["case_id"])
            if row is None:
                row = ReviewCaseRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.trace_id = payload["trace_id"]
                row.case_type = payload["case_type"]
                row.status = payload["status"]
                row.owner_id = payload["owner_id"]
                row.source_surface = payload["source_surface"]
                row.world_version_id = payload["world_version_id"]
                row.session_id = payload["session_id"]
                row.score_id = payload["score_id"]
                row.source_ref_json = payload["source_ref_json"]
                row.reason_codes_json = payload["reason_codes_json"]
                row.evidence_refs_json = payload["evidence_refs_json"]
                row.case_payload_json = payload["case_payload_json"]
                row.updated_at = now
            session.commit()
            return _review_case_payload(row)

    def get_review_case(self, case_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ReviewCaseRow, case_id)
            if row is None:
                raise KeyError(f"unknown_review_case:{case_id}")
            return _review_case_payload(row)

    def list_review_cases(
        self,
        *,
        status: Optional[str] = None,
        case_type: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ReviewCaseRow)
            if status is not None:
                stmt = stmt.where(ReviewCaseRow.status == status)
            if case_type is not None:
                stmt = stmt.where(ReviewCaseRow.case_type == case_type)
            if world_version_id is not None:
                stmt = stmt.where(ReviewCaseRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(ReviewCaseRow.session_id == session_id)
            if trace_id is not None:
                stmt = stmt.where(ReviewCaseRow.trace_id == trace_id)
            stmt = stmt.order_by(desc(ReviewCaseRow.updated_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_review_case_payload(row) for row in rows]

    def update_review_case_status(
        self,
        case_id: str,
        *,
        status: str,
        owner_id: Optional[str] = None,
        reason_codes: Optional[List[str]] = None,
        evidence_refs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ReviewCaseRow, case_id)
            if row is None:
                raise KeyError(f"unknown_review_case:{case_id}")
            row.status = str(status)
            if owner_id is not None:
                row.owner_id = owner_id
            if reason_codes is not None:
                row.reason_codes_json = [str(item) for item in reason_codes if str(item)]
            if evidence_refs is not None:
                row.evidence_refs_json = [dict(item or {}) for item in evidence_refs]
            row.updated_at = utcnow_iso()
            session.commit()
            return _review_case_payload(row)

    def save_quality_feedback_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "feedback_item_id": str(item.get("feedback_item_id") or f"quality_feedback_{uuid4().hex[:12]}"),
            "trace_id": item.get("trace_id"),
            "source_event_id": item.get("source_event_id"),
            "feedback_type": str(item.get("feedback_type") or ""),
            "signal": str(item.get("signal") or ""),
            "source_surface": str(item.get("source_surface") or ""),
            "account_id": item.get("account_id"),
            "world_version_id": item.get("world_version_id"),
            "session_id": item.get("session_id"),
            "chapter_id": item.get("chapter_id"),
            "source_ref_json": dict(item.get("source_ref") or {}),
            "payload_json": dict(item.get("payload") or {}),
            "created_at": str(item.get("created_at") or utcnow_iso()),
        }
        with self.SessionLocal() as session:
            row = session.get(QualityFeedbackItemRow, payload["feedback_item_id"])
            if row is None:
                row = QualityFeedbackItemRow(**payload)
                session.add(row)
            else:
                row.trace_id = payload["trace_id"]
                row.source_event_id = payload["source_event_id"]
                row.feedback_type = payload["feedback_type"]
                row.signal = payload["signal"]
                row.source_surface = payload["source_surface"]
                row.account_id = payload["account_id"]
                row.world_version_id = payload["world_version_id"]
                row.session_id = payload["session_id"]
                row.chapter_id = payload["chapter_id"]
                row.source_ref_json = payload["source_ref_json"]
                row.payload_json = payload["payload_json"]
                row.created_at = payload["created_at"]
            session.commit()
            return _quality_feedback_item_payload(row)

    def list_quality_feedback_items(
        self,
        *,
        trace_id: Optional[str] = None,
        account_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        feedback_type: Optional[str] = None,
        signal: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(QualityFeedbackItemRow)
            if trace_id is not None:
                stmt = stmt.where(QualityFeedbackItemRow.trace_id == trace_id)
            if account_id is not None:
                stmt = stmt.where(QualityFeedbackItemRow.account_id == account_id)
            if world_version_id is not None:
                stmt = stmt.where(QualityFeedbackItemRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(QualityFeedbackItemRow.session_id == session_id)
            if chapter_id is not None:
                stmt = stmt.where(QualityFeedbackItemRow.chapter_id == chapter_id)
            if feedback_type is not None:
                stmt = stmt.where(QualityFeedbackItemRow.feedback_type == feedback_type)
            if signal is not None:
                stmt = stmt.where(QualityFeedbackItemRow.signal == signal)
            stmt = stmt.order_by(desc(QualityFeedbackItemRow.created_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_quality_feedback_item_payload(row) for row in rows]

    def save_grounding_check(self, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "grounding_check_id": str(item.get("grounding_check_id") or f"grounding_check_{uuid4().hex[:12]}"),
            "trace_id": item.get("trace_id"),
            "status": str(item.get("status") or ""),
            "confidence": float(item.get("confidence", 0.0) or 0.0),
            "source_surface": str(item.get("source_surface") or ""),
            "world_version_id": item.get("world_version_id"),
            "session_id": item.get("session_id"),
            "chapter_id": item.get("chapter_id"),
            "evidence_refs_json": [dict(entry or {}) for entry in list(item.get("evidence_refs") or [])],
            "unsupported_claims_json": [str(entry) for entry in list(item.get("unsupported_claims") or []) if str(entry)],
            "reason_codes_json": [str(entry) for entry in list(item.get("reason_codes") or []) if str(entry)],
            "summary": str(item.get("summary") or ""),
            "created_at": str(item.get("created_at") or utcnow_iso()),
        }
        with self.SessionLocal() as session:
            row = session.get(GroundingCheckRow, payload["grounding_check_id"])
            if row is None:
                row = GroundingCheckRow(**payload)
                session.add(row)
            else:
                row.trace_id = payload["trace_id"]
                row.status = payload["status"]
                row.confidence = payload["confidence"]
                row.source_surface = payload["source_surface"]
                row.world_version_id = payload["world_version_id"]
                row.session_id = payload["session_id"]
                row.chapter_id = payload["chapter_id"]
                row.evidence_refs_json = payload["evidence_refs_json"]
                row.unsupported_claims_json = payload["unsupported_claims_json"]
                row.reason_codes_json = payload["reason_codes_json"]
                row.summary = payload["summary"]
                row.created_at = payload["created_at"]
            session.commit()
            return _grounding_check_payload(row)

    def list_grounding_checks(
        self,
        *,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(GroundingCheckRow)
            if trace_id is not None:
                stmt = stmt.where(GroundingCheckRow.trace_id == trace_id)
            if status is not None:
                stmt = stmt.where(GroundingCheckRow.status == status)
            if world_version_id is not None:
                stmt = stmt.where(GroundingCheckRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(GroundingCheckRow.session_id == session_id)
            if chapter_id is not None:
                stmt = stmt.where(GroundingCheckRow.chapter_id == chapter_id)
            stmt = stmt.order_by(desc(GroundingCheckRow.created_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_grounding_check_payload(row) for row in rows]

    def get_world(self, world_id: str) -> WorldRecord:
        with self.SessionLocal() as session:
            row = session.get(WorldRow, world_id)
            if row is None or not row.latest_version:
                raise KeyError("unknown_world:%s" % world_id)
        runtime = self.get_runtime_bundle(row.latest_version)
        return runtime.world_record

    def get_runtime_bundle(self, world_version_id: str) -> RuntimeBundle:
        version = self.get_world_version(world_version_id)
        try:
            return self.registry.get_runtime_bundle(world_version_id)
        except KeyError:
            return runtime_bundle_from_worldpack_data(
                {
                    "world_version_id": world_version_id,
                    "world_id": version.world_id,
                    "status": version.status,
                    "worldpack": version.worldpack_json,
                }
            )

    def create_world(self, world_record: WorldRecord) -> WorldRecord:
        worldpack = WorldPack.from_dict(self.registry.get_published_world(world_record.world.world_id)["worldpack"]) if any(card["world_id"] == world_record.world.world_id for card in self.registry.list_worldpacks()) else None
        if worldpack is None:
            from ..worldpacks.models import worldpack_from_world_record

            worldpack = worldpack_from_world_record(world_record, initial_state=NarrativeState.from_dict({"state_id": "%s__bootstrap" % world_record.world.world_id, "world_id": world_record.world.world_id, "turn_index": 0, "story_phase": "setup", "chapter_index": 0, "min_end_turn": 8, "fate_pressure": 0.1, "karmic_weather": {}, "unresolved_debts": [], "world_facts": [], "timeline": [], "characters": {}, "relationship_graph": [], "open_promises": [], "tension": 0.0, "themes": {}, "player_intent": {}, "recent_scene_functions": [], "visited_event_ids": [], "route_fingerprint": [], "rating_ceiling": "PG13"}))
        world_version = WorldVersion.from_worldpack(
            worldpack=worldpack,
            world_version_id="%s@%s" % (worldpack.world_id, worldpack.version),
            status="published",
        )
        self.save_world_version(world_version, publish=True)
        return world_record

    # Sessions / chapters
    def create_session_record(
        self,
        *,
        world_version_id: str,
        initial_state: NarrativeState,
        reader_id: Optional[str] = None,
        player_profile: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        entitlements_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        world_version = self.get_world_version(world_version_id)
        record = SessionRecord(
            session_id=session_id or "session_%s" % uuid4().hex[:12],
            world_id=world_version.world_id,
            player_profile=dict(player_profile or {}),
            initial_state=initial_state,
            current_state=initial_state,
            created_at=utcnow_iso(),
            metadata={"world_version_id": world_version_id, **dict(metadata or {})},
        )
        with self.SessionLocal() as session:
            session.add(
                SessionRow(
                    session_id=record.session_id,
                    reader_id=reader_id,
                    world_version_id=world_version_id,
                    status="active",
                    chapter_index=initial_state.chapter_index,
                    story_phase=initial_state.story_phase,
                    narrative_state_json=record.current_state.to_dict(),
                    entitlements_snapshot_json=dict(entitlements_snapshot or {}),
                    created_at=record.created_at,
                    updated_at=record.created_at,
                )
            )
            session.commit()
        return record

    def create_session(
        self,
        world_id: str,
        initial_state: NarrativeState,
        *,
        player_profile: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        world_card = next((card for card in self.list_worlds() if card["world_id"] == world_id), None)
        if world_card is None:
            raise KeyError("unknown_world:%s" % world_id)
        return self.create_session_record(
            world_version_id=world_card["latest_version"],
            initial_state=initial_state,
            reader_id=str((player_profile or {}).get("reader_id") or "").strip() or None,
            player_profile=player_profile,
            session_id=session_id,
            metadata=metadata,
        )

    def get_session(self, session_id: str) -> SessionRecord:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            world_version = self.get_world_version(row.world_version_id)
            current_state = NarrativeState.from_dict(dict(row.narrative_state_json))
            return SessionRecord(
                session_id=row.session_id,
                world_id=world_version.world_id,
                player_profile={"reader_id": row.reader_id} if row.reader_id else {},
                initial_state=current_state,
                current_state=current_state,
                created_at=row.created_at,
                metadata={
                    "world_version_id": row.world_version_id,
                    "reader_id": row.reader_id,
                    "entitlements_snapshot": dict(row.entitlements_snapshot_json or {}),
                },
            )

    def update_session_entitlements_snapshot(self, session_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            row.entitlements_snapshot_json = dict(snapshot or {})
            row.updated_at = utcnow_iso()
            session.commit()
            return dict(row.entitlements_snapshot_json or {})

    def claim_guest_session(self, session_id: str, *, reader_id: str) -> Dict[str, Any]:
        normalized_reader_id = str(reader_id or "").strip()
        if not normalized_reader_id:
            raise ValueError("reader_id_required")
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            current_reader_id = str(row.reader_id or "").strip()
            if current_reader_id == normalized_reader_id:
                return {
                    "session_id": row.session_id,
                    "reader_id": current_reader_id,
                    "world_version_id": row.world_version_id,
                    "status": "already_owned",
                }
            if current_reader_id:
                return {
                    "session_id": row.session_id,
                    "reader_id": current_reader_id,
                    "world_version_id": row.world_version_id,
                    "status": "conflict",
                }

            result = session.execute(
                update(SessionRow)
                .where(
                    SessionRow.session_id == session_id,
                    or_(SessionRow.reader_id.is_(None), SessionRow.reader_id == ""),
                )
                .values(reader_id=normalized_reader_id, updated_at=now)
            )
            if int(result.rowcount or 0) == 1:
                session.commit()
                return {
                    "session_id": session_id,
                    "reader_id": normalized_reader_id,
                    "world_version_id": row.world_version_id,
                    "status": "claimed",
                }

            session.rollback()
            refreshed = session.get(SessionRow, session_id)
            if refreshed is None:
                raise KeyError("unknown_session:%s" % session_id)
            refreshed_reader_id = str(refreshed.reader_id or "").strip()
            if refreshed_reader_id == normalized_reader_id:
                return {
                    "session_id": refreshed.session_id,
                    "reader_id": refreshed_reader_id,
                    "world_version_id": refreshed.world_version_id,
                    "status": "already_owned",
                }
            return {
                "session_id": refreshed.session_id,
                "reader_id": refreshed_reader_id,
                "world_version_id": refreshed.world_version_id,
                "status": "conflict",
            }

    def list_sessions(self, world_id: Optional[str] = None, reader_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SessionRow).order_by(desc(SessionRow.updated_at))
            if reader_id is not None:
                stmt = stmt.where(SessionRow.reader_id == str(reader_id or "").strip())
            rows = session.execute(stmt).scalars()
            results = []
            for row in rows:
                world_version = self.get_world_version(row.world_version_id)
                if world_id is not None and world_version.world_id != world_id:
                    continue
                latest_step = self.get_latest_step(row.session_id)
                results.append(
                    {
                        "session_id": row.session_id,
                        "world_id": world_version.world_id,
                        "world_version_id": row.world_version_id,
                        "created_at": row.created_at,
                        "current_turn_index": row.chapter_index,
                        "last_event_title": latest_step.chosen_event.title if latest_step and latest_step.chosen_event else None,
                        "last_chapter_title": latest_step.reader_view.chapter_title if latest_step and latest_step.reader_view else None,
                    }
                )
            return results

    def save_step(self, step_record: StepRecord, *, world_version_id: Optional[str] = None, entitlements_snapshot: Optional[Dict[str, Any]] = None, cost_estimate: Optional[float] = None) -> StepRecord:
        created_at = step_record.created_at or utcnow_iso()
        step_record.created_at = created_at
        with self.SessionLocal() as session:
            session_row = session.get(SessionRow, step_record.session_id)
            if session_row is None:
                raise KeyError("unknown_session:%s" % step_record.session_id)
            chapter_id = "chapter_%s_%s" % (step_record.session_id, step_record.step_index)
            try:
                session.add(
                    ChapterRow(
                        chapter_id=chapter_id,
                        session_id=step_record.session_id,
                        world_version_id=world_version_id or session_row.world_version_id,
                        chapter_index=step_record.step_index,
                        plan_json=_chapter_plan_json_for_step(step_record),
                        rendered_body=step_record.reader_view.body if step_record.reader_view else (step_record.rendered_scene.premium_prose if step_record.rendered_scene else ""),
                        choices_json=step_record.reader_view.choices if step_record.reader_view else [],
                        cost_estimate=cost_estimate,
                        review_flags_json={"critic_trace": step_record.critic_trace},
                        created_at=created_at,
                    )
                )
                session_row.chapter_index = step_record.state_after.chapter_index
                session_row.story_phase = step_record.state_after.story_phase
                session_row.narrative_state_json = step_record.state_after.to_dict()
                session_row.entitlements_snapshot_json = dict(entitlements_snapshot or (session_row.entitlements_snapshot_json or {}))
                session_row.updated_at = created_at
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.get(ChapterRow, chapter_id)
                if existing is None:
                    raise
                payload = dict(existing.plan_json or {})
                if payload.get("step_record"):
                    return StepRecord.from_dict(payload["step_record"])
                replay_payload = _replay_payload_from_plan(payload)
                replay_step = _step_record_from_replay_payload(replay_payload)
                if replay_step is not None:
                    return replay_step
                return step_record
        return step_record

    def save_evaluation_report(self, chapter_id: str, report: EvaluationReport) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ChapterRow, chapter_id)
            if row is None:
                raise KeyError("unknown_chapter:%s" % chapter_id)
            payload = dict(row.review_flags_json or {})
            payload["evaluation_report"] = report.to_dict()
            row.review_flags_json = payload
            session.commit()
        return report.to_dict()

    def save_route_choice(
        self,
        *,
        session_id: str,
        chapter_id: str,
        choice_id: str,
        payload_json: Optional[Dict[str, Any]] = None,
        selected_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "session_id": str(session_id),
            "chapter_id": str(chapter_id),
            "choice_id": str(choice_id or "director_intent"),
            "selected_at": selected_at or utcnow_iso(),
            "payload_json": dict(payload_json or {}),
        }
        with self.SessionLocal() as session:
            row = RouteChoiceRow(**payload)
            session.add(row)
            session.commit()
            return _route_choice_payload(row)

    def list_route_choices(
        self,
        *,
        session_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(RouteChoiceRow).order_by(RouteChoiceRow.selected_at.asc(), RouteChoiceRow.choice_event_id.asc())
            if session_id is not None:
                stmt = stmt.where(RouteChoiceRow.session_id == session_id)
            if chapter_id is not None:
                stmt = stmt.where(RouteChoiceRow.chapter_id == chapter_id)
            rows = session.execute(stmt.limit(max(1, min(500, int(limit or 100))))).scalars().all()
            return [_route_choice_payload(row) for row in rows]

    def get_evaluation_report(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ChapterRow, chapter_id)
            if row is None:
                raise KeyError("unknown_chapter:%s" % chapter_id)
            payload = dict(row.review_flags_json or {})
            return payload.get("evaluation_report")

    def list_evaluation_reports(
        self,
        *,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ChapterRow).order_by(desc(ChapterRow.created_at))
            if world_version_id is not None:
                stmt = stmt.where(ChapterRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(ChapterRow.session_id == session_id)
            rows = session.execute(stmt).scalars()
            reports = []
            for row in rows:
                payload = dict(row.review_flags_json or {})
                if payload.get("evaluation_report"):
                    reports.append(payload["evaluation_report"])
            return reports

    def list_steps(self, session_id: str) -> List[StepRecord]:
        with self.SessionLocal() as session:
            rows = session.execute(
                select(ChapterRow).where(ChapterRow.session_id == session_id).order_by(ChapterRow.chapter_index.asc())
            ).scalars()
            results = []
            for row in rows:
                plan = dict(row.plan_json or {})
                if plan.get("step_record"):
                    step_record = StepRecord.from_dict(plan["step_record"])
                else:
                    replay_payload = _replay_payload_from_plan(plan)
                    step_record = _step_record_from_replay_payload(replay_payload)
                if step_record is not None:
                    results.append(step_record)
            return results

    def count_story_chapters(self, session_id: str) -> int:
        with self.SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(ChapterRow).where(ChapterRow.session_id == session_id)
                ).scalar()
                or 0
            )

    def list_story_chapter_payloads(
        self,
        session_id: str,
        *,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        limit: Optional[int] = None,
        latest: bool = False,
    ) -> List[Dict[str, Any]]:
        start_value = int(start_chapter) if start_chapter is not None else None
        end_value = int(end_chapter) if end_chapter is not None else None
        limit_value = max(1, min(500, int(limit))) if limit is not None else None
        use_latest_order = bool(latest and limit_value is not None and start_value is None and end_value is None)
        with self.SessionLocal() as session:
            dialect_name = getattr(getattr(session, "bind", None), "dialect", None)
            if getattr(dialect_name, "name", "") == "sqlite":
                def _coerce_json(value: Any, fallback: Any) -> Any:
                    if value is None or value == "":
                        return fallback
                    if isinstance(value, (dict, list)):
                        return value
                    if isinstance(value, str):
                        try:
                            return json.loads(value)
                        except json.JSONDecodeError:
                            return fallback
                    return fallback

                def _json_mapping(value: Any) -> Dict[str, Any]:
                    payload = _coerce_json(value, {})
                    return dict(payload) if isinstance(payload, dict) else {}

                def _json_list(value: Any) -> List[Any]:
                    payload = _coerce_json(value, [])
                    return list(payload) if isinstance(payload, list) else []

                stmt = select(
                    ChapterRow.chapter_id,
                    ChapterRow.session_id,
                    ChapterRow.world_version_id,
                    ChapterRow.chapter_index,
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.reader_view"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.reader_view"),
                    ).label("reader_view_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.state_before"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.state_before"),
                    ).label("state_before_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.state_after"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.state_after"),
                    ).label("state_after_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.scene_beats"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.scene_beats"),
                    ).label("scene_beats_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.critic_trace"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.critic_trace"),
                    ).label("critic_trace_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.chosen_event"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.chosen_event"),
                    ).label("chosen_event_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.rendered_scene"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.rendered_scene"),
                    ).label("rendered_scene_json"),
                    func.coalesce(
                        func.json_extract(ChapterRow.plan_json, "$.replay.promise_ledger_snapshot"),
                        func.json_extract(ChapterRow.plan_json, "$.step_record.promise_ledger_snapshot"),
                    ).label("promise_ledger_json"),
                    ChapterRow.rendered_body,
                    ChapterRow.choices_json,
                    ChapterRow.created_at,
                ).where(ChapterRow.session_id == session_id)
                if start_value is not None:
                    stmt = stmt.where(ChapterRow.chapter_index >= start_value)
                if end_value is not None:
                    stmt = stmt.where(ChapterRow.chapter_index <= end_value)
                stmt = stmt.order_by(ChapterRow.chapter_index.desc() if use_latest_order else ChapterRow.chapter_index.asc())
                if limit_value is not None:
                    stmt = stmt.limit(limit_value)
                rows = list(session.execute(stmt).all())
                if use_latest_order:
                    rows.reverse()
                results: List[Dict[str, Any]] = []
                for row in rows:
                    reader_view = _json_mapping(row.reader_view_json)
                    if row.rendered_body and not reader_view.get("body"):
                        reader_view["body"] = row.rendered_body
                    choices = _coerce_json(row.choices_json, []) if isinstance(row.choices_json, str) else row.choices_json
                    if choices and not reader_view.get("choices"):
                        reader_view["choices"] = list(choices or [])
                    reader_view.setdefault("chapter_index", row.chapter_index)
                    reader_view.setdefault("chapter_title", f"第 {row.chapter_index} 章")
                    reader_view = repair_reader_view_for_display(reader_view)
                    results.append(
                        {
                            "chapter_id": row.chapter_id,
                            "session_id": row.session_id,
                            "world_version_id": row.world_version_id,
                            "chapter_index": row.chapter_index,
                            "reader_view": reader_view,
                            "state_before": _json_mapping(row.state_before_json),
                            "state_after": _json_mapping(row.state_after_json),
                            "scene_beats": _json_list(row.scene_beats_json),
                            "critic_trace": _json_list(row.critic_trace_json),
                            "chosen_event": _json_mapping(row.chosen_event_json),
                            "rendered_scene": _json_mapping(row.rendered_scene_json),
                            "promise_ledger_snapshot": _json_list(row.promise_ledger_json),
                            "created_at": row.created_at,
                        }
                    )
                return results

            stmt = select(ChapterRow).where(ChapterRow.session_id == session_id)
            if start_value is not None:
                stmt = stmt.where(ChapterRow.chapter_index >= start_value)
            if end_value is not None:
                stmt = stmt.where(ChapterRow.chapter_index <= end_value)
            stmt = stmt.order_by(ChapterRow.chapter_index.desc() if use_latest_order else ChapterRow.chapter_index.asc())
            if limit_value is not None:
                stmt = stmt.limit(limit_value)
            rows = list(session.execute(stmt).scalars())
            if use_latest_order:
                rows.reverse()
            results: List[Dict[str, Any]] = []
            for row in rows:
                replay_payload = _replay_payload_from_plan(dict(row.plan_json or {}))
                step_record = replay_payload
                reader_view = dict(step_record.get("reader_view") or {})
                if row.rendered_body and not reader_view.get("body"):
                    reader_view["body"] = row.rendered_body
                if row.choices_json and not reader_view.get("choices"):
                    reader_view["choices"] = list(row.choices_json or [])
                reader_view.setdefault("chapter_index", row.chapter_index)
                reader_view.setdefault("chapter_title", f"第 {row.chapter_index} 章")
                reader_view = repair_reader_view_for_display(reader_view)
                results.append(
                    {
                        "chapter_id": row.chapter_id,
                        "session_id": row.session_id,
                        "world_version_id": row.world_version_id,
                        "chapter_index": row.chapter_index,
                        "reader_view": reader_view,
                        "state_before": dict(step_record.get("state_before") or {}),
                        "state_after": dict(step_record.get("state_after") or {}),
                        "scene_beats": list(step_record.get("scene_beats") or []),
                        "critic_trace": step_record.get("critic_trace") or {},
                        "chosen_event": dict(step_record.get("chosen_event") or {}),
                        "rendered_scene": dict(step_record.get("rendered_scene") or {}),
                        "promise_ledger_snapshot": list(step_record.get("promise_ledger_snapshot") or []),
                        "created_at": row.created_at,
                    }
                )
            return results

    def get_latest_step(self, session_id: str) -> Optional[StepRecord]:
        with self.SessionLocal() as session:
            row = session.execute(
                select(ChapterRow)
                .where(ChapterRow.session_id == session_id)
                .order_by(ChapterRow.chapter_index.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            plan = dict(row.plan_json or {})
            if plan.get("step_record"):
                return StepRecord.from_dict(plan["step_record"])
            replay_payload = _replay_payload_from_plan(plan)
            return _step_record_from_replay_payload(replay_payload)

    def get_replay(
        self,
        session_id: str,
        *,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        limit: Optional[int] = None,
        latest: bool = False,
    ) -> Dict[str, Any]:
        session_record = self.get_session(session_id)
        chapter_payloads = self.list_story_chapter_payloads(
            session_id,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            limit=limit,
            latest=latest,
        )
        evaluation_reports = self.list_evaluation_reports(session_id=session_id)
        event_trace = [dict(item.get("chosen_event") or {}) for item in chapter_payloads if item.get("chosen_event")]
        reader_views = [dict(item.get("reader_view") or {}) for item in chapter_payloads if item.get("reader_view")]
        state_snapshots = [session_record.initial_state.to_dict()] + [
            dict(item.get("state_after") or {}) for item in chapter_payloads if item.get("state_after")
        ]
        return {
            "session": session_record.to_dict(),
            "full_timeline": [str(event.get("title") or "") for event in event_trace if event.get("title")],
            "event_trace": event_trace,
            "reader_views": reader_views,
            "critic_trace": [item.get("critic_trace") or [] for item in chapter_payloads],
            "state_snapshots": state_snapshots,
            "promise_ledger_snapshots": [list(item.get("promise_ledger_snapshot") or []) for item in chapter_payloads],
            "rendered_scenes": [dict(item.get("rendered_scene") or {}) for item in chapter_payloads if item.get("rendered_scene")],
            "evaluation_reports": evaluation_reports,
            "replay_projection": {
                "schema_version": "reader_replay_projection/v1",
                "is_windowed": any(value is not None for value in [start_chapter, end_chapter, limit]) or bool(latest),
                "start_chapter": start_chapter,
                "end_chapter": end_chapter,
                "limit": limit,
                "latest": bool(latest),
                "returned_chapters": len(chapter_payloads),
                "total_chapters": self.count_story_chapters(session_id),
                "first_chapter": int(chapter_payloads[0]["chapter_index"]) if chapter_payloads else None,
                "last_chapter": int(chapter_payloads[-1]["chapter_index"]) if chapter_payloads else None,
            },
        }

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                raise KeyError("unknown_session:%s" % session_id)
            chapter_rows = session.execute(select(ChapterRow).where(ChapterRow.session_id == session_id)).scalars()
            deleted_steps = 0
            for chapter in chapter_rows:
                session.delete(chapter)
                deleted_steps += 1
            session.delete(row)
            session.commit()
        return {"session_id": session_id, "deleted_steps": deleted_steps}

    # Review / publish / rollback
    def save_review_record(self, review: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "review_id": review.get("review_id") or "review_%s" % uuid4().hex[:12],
            "asset_type": review["asset_type"],
            "asset_id": review["asset_id"],
            "status": review["status"],
            "reviewer_id": review.get("reviewer_id"),
            "risk_rating": review.get("risk_rating"),
            "notes": review.get("notes"),
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(ReviewRecordRow, payload["review_id"])
            if row is None:
                row = ReviewRecordRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.asset_type = payload["asset_type"]
                row.asset_id = payload["asset_id"]
                row.status = payload["status"]
                row.reviewer_id = payload["reviewer_id"]
                row.risk_rating = payload["risk_rating"]
                row.notes = payload["notes"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def save_author_comment_thread(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "thread_id": thread.get("thread_id") or "athread_%s" % uuid4().hex[:12],
            "world_version_id": thread["world_version_id"],
            "revision_id": thread.get("revision_id"),
            "anchor_type": thread["anchor_type"],
            "anchor_key": thread["anchor_key"],
            "status": thread.get("status", "open"),
            "severity": thread.get("severity", "normal"),
            "assignee_id": thread.get("assignee_id"),
            "created_by": thread["created_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentThreadRow, payload["thread_id"])
            if row is None:
                row = AuthorCommentThreadRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.world_version_id = payload["world_version_id"]
                row.revision_id = payload["revision_id"]
                row.anchor_type = payload["anchor_type"]
                row.anchor_key = payload["anchor_key"]
                row.status = payload["status"]
                row.severity = payload["severity"]
                row.assignee_id = payload["assignee_id"]
                row.created_by = payload["created_by"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def list_author_comment_threads(
        self,
        *,
        world_version_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        status: Optional[str] = None,
        anchor_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorCommentThreadRow).order_by(desc(AuthorCommentThreadRow.updated_at))
            if world_version_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.world_version_id == world_version_id)
            if revision_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.revision_id == revision_id)
            if status is not None:
                stmt = stmt.where(AuthorCommentThreadRow.status == status)
            if anchor_type is not None:
                stmt = stmt.where(AuthorCommentThreadRow.anchor_type == anchor_type)
            if assignee_id is not None:
                stmt = stmt.where(AuthorCommentThreadRow.assignee_id == assignee_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "thread_id": row.thread_id,
                    "world_version_id": row.world_version_id,
                    "revision_id": row.revision_id,
                    "anchor_type": row.anchor_type,
                    "anchor_key": row.anchor_key,
                    "status": row.status,
                    "severity": row.severity,
                    "assignee_id": row.assignee_id,
                    "created_by": row.created_by,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def get_author_comment_thread(self, thread_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentThreadRow, thread_id)
            if row is None:
                raise KeyError("unknown_author_comment_thread:%s" % thread_id)
            return {
                "thread_id": row.thread_id,
                "world_version_id": row.world_version_id,
                "revision_id": row.revision_id,
                "anchor_type": row.anchor_type,
                "anchor_key": row.anchor_key,
                "status": row.status,
                "severity": row.severity,
                "assignee_id": row.assignee_id,
                "created_by": row.created_by,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_author_comment_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "message_id": message.get("message_id") or "acomment_%s" % uuid4().hex[:12],
            "thread_id": message["thread_id"],
            "actor_id": message["actor_id"],
            "actor_role": message["actor_role"],
            "body": message["body"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorCommentMessageRow, payload["message_id"])
            if row is None:
                row = AuthorCommentMessageRow(created_at=now, **payload)
                session.add(row)
            else:
                row.thread_id = payload["thread_id"]
                row.actor_id = payload["actor_id"]
                row.actor_role = payload["actor_role"]
                row.body = payload["body"]
            thread_row = session.get(AuthorCommentThreadRow, payload["thread_id"])
            if thread_row is not None:
                thread_row.updated_at = now
            session.commit()
        payload["created_at"] = now
        return payload

    def list_author_comment_messages(self, *, thread_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = (
                select(AuthorCommentMessageRow)
                .where(AuthorCommentMessageRow.thread_id == thread_id)
                .order_by(AuthorCommentMessageRow.created_at.asc())
            )
            rows = session.execute(stmt).scalars()
            return [
                {
                    "message_id": row.message_id,
                    "thread_id": row.thread_id,
                    "actor_id": row.actor_id,
                    "actor_role": row.actor_role,
                    "body": row.body,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def save_author_approval_record(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "approval_id": approval.get("approval_id") or "approval_%s" % uuid4().hex[:12],
            "world_version_id": approval["world_version_id"],
            "revision_id": approval.get("revision_id"),
            "status": approval["status"],
            "reviewer_id": approval["reviewer_id"],
            "reason": approval["reason"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(AuthorApprovalRecordRow, payload["approval_id"])
            if row is None:
                row = AuthorApprovalRecordRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.world_version_id = payload["world_version_id"]
                row.revision_id = payload["revision_id"]
                row.status = payload["status"]
                row.reviewer_id = payload["reviewer_id"]
                row.reason = payload["reason"]
                row.updated_at = now
            session.commit()
        payload["created_at"] = now
        payload["updated_at"] = now
        return payload

    def list_author_approval_records(
        self,
        *,
        world_version_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorApprovalRecordRow).order_by(desc(AuthorApprovalRecordRow.updated_at))
            if world_version_id is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.world_version_id == world_version_id)
            if revision_id is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.revision_id == revision_id)
            if status is not None:
                stmt = stmt.where(AuthorApprovalRecordRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "approval_id": row.approval_id,
                    "world_version_id": row.world_version_id,
                    "revision_id": row.revision_id,
                    "status": row.status,
                    "reviewer_id": row.reviewer_id,
                    "reason": row.reason,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_author_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "notification_id": notification.get("notification_id") or "anotify_%s" % uuid4().hex[:12],
            "world_version_id": notification["world_version_id"],
            "thread_id": notification.get("thread_id"),
            "approval_id": notification.get("approval_id"),
            "recipient_id": notification["recipient_id"],
            "recipient_role": notification.get("recipient_role", "reviewer"),
            "notification_type": notification["notification_type"],
            "status": notification.get("status", "unread"),
            "actor_id": notification.get("actor_id"),
            "actor_role": notification.get("actor_role"),
            "title": notification["title"],
            "body": notification["body"],
            "anchor_type": notification.get("anchor_type"),
            "anchor_key": notification.get("anchor_key"),
            "metadata_json": dict(notification.get("metadata_json") or {}),
            "read_at": notification.get("read_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthorNotificationRow, payload["notification_id"])
            if row is None:
                row = AuthorNotificationRow(created_at=now, updated_at=now, **payload)
                session.add(row)
                created_at = now
            else:
                row.world_version_id = payload["world_version_id"]
                row.thread_id = payload["thread_id"]
                row.approval_id = payload["approval_id"]
                row.recipient_id = payload["recipient_id"]
                row.recipient_role = payload["recipient_role"]
                row.notification_type = payload["notification_type"]
                row.status = payload["status"]
                row.actor_id = payload["actor_id"]
                row.actor_role = payload["actor_role"]
                row.title = payload["title"]
                row.body = payload["body"]
                row.anchor_type = payload["anchor_type"]
                row.anchor_key = payload["anchor_key"]
                row.metadata_json = payload["metadata_json"]
                row.read_at = payload["read_at"]
                row.updated_at = now
                created_at = row.created_at
            session.commit()
        payload["created_at"] = created_at
        payload["updated_at"] = now
        return payload

    def save_author_thread_watcher(self, watcher: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.list_author_thread_watchers(
            thread_id=watcher["thread_id"],
            watcher_id=watcher["watcher_id"],
        )
        if existing:
            return existing[0]
        payload = {
            "watcher_record_id": watcher.get("watcher_record_id") or "awatcher_%s" % uuid4().hex[:12],
            "thread_id": watcher["thread_id"],
            "watcher_id": watcher["watcher_id"],
            "added_by": watcher["added_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            session.add(AuthorThreadWatcherRow(created_at=now, **payload))
            session.commit()
        payload["created_at"] = now
        return payload

    def save_author_draft_watcher(self, watcher: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.list_author_draft_watchers(
            world_version_id=watcher["world_version_id"],
            watcher_id=watcher["watcher_id"],
        )
        if existing:
            return existing[0]
        payload = {
            "watcher_record_id": watcher.get("watcher_record_id") or "adwatcher_%s" % uuid4().hex[:12],
            "world_version_id": watcher["world_version_id"],
            "watcher_id": watcher["watcher_id"],
            "added_by": watcher["added_by"],
        }
        now = utcnow_iso()
        with self.SessionLocal() as session:
            session.add(AuthorDraftWatcherRow(created_at=now, **payload))
            session.commit()
        payload["created_at"] = now
        return payload

    def list_author_thread_watchers(
        self,
        *,
        thread_id: Optional[str] = None,
        watcher_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorThreadWatcherRow).order_by(AuthorThreadWatcherRow.created_at.asc())
            if thread_id is not None:
                stmt = stmt.where(AuthorThreadWatcherRow.thread_id == thread_id)
            if watcher_id is not None:
                stmt = stmt.where(AuthorThreadWatcherRow.watcher_id == watcher_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "watcher_record_id": row.watcher_record_id,
                    "thread_id": row.thread_id,
                    "watcher_id": row.watcher_id,
                    "added_by": row.added_by,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def delete_author_thread_watcher(self, *, thread_id: str, watcher_id: str) -> Dict[str, Any]:
        removed = {"thread_id": thread_id, "watcher_id": watcher_id, "deleted": False}
        with self.SessionLocal() as session:
            rows = session.execute(
                select(AuthorThreadWatcherRow).where(
                    AuthorThreadWatcherRow.thread_id == thread_id,
                    AuthorThreadWatcherRow.watcher_id == watcher_id,
                )
            ).scalars().all()
            for row in rows:
                removed["deleted"] = True
                removed["watcher_record_id"] = row.watcher_record_id
                removed["created_at"] = row.created_at
                session.delete(row)
            session.commit()
        return removed

    def list_author_draft_watchers(
        self,
        *,
        world_version_id: Optional[str] = None,
        watcher_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorDraftWatcherRow).order_by(AuthorDraftWatcherRow.created_at.asc())
            if world_version_id is not None:
                stmt = stmt.where(AuthorDraftWatcherRow.world_version_id == world_version_id)
            if watcher_id is not None:
                stmt = stmt.where(AuthorDraftWatcherRow.watcher_id == watcher_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "watcher_record_id": row.watcher_record_id,
                    "world_version_id": row.world_version_id,
                    "watcher_id": row.watcher_id,
                    "added_by": row.added_by,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def delete_author_draft_watcher(self, *, world_version_id: str, watcher_id: str) -> Dict[str, Any]:
        removed = {"world_version_id": world_version_id, "watcher_id": watcher_id, "deleted": False}
        with self.SessionLocal() as session:
            rows = session.execute(
                select(AuthorDraftWatcherRow).where(
                    AuthorDraftWatcherRow.world_version_id == world_version_id,
                    AuthorDraftWatcherRow.watcher_id == watcher_id,
                )
            ).scalars().all()
            for row in rows:
                removed["deleted"] = True
                removed["watcher_record_id"] = row.watcher_record_id
                removed["created_at"] = row.created_at
                session.delete(row)
            session.commit()
        return removed

    def get_author_notification(self, notification_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthorNotificationRow, notification_id)
            if row is None:
                raise KeyError("unknown_author_notification:%s" % notification_id)
            return {
                "notification_id": row.notification_id,
                "world_version_id": row.world_version_id,
                "thread_id": row.thread_id,
                "approval_id": row.approval_id,
                "recipient_id": row.recipient_id,
                "recipient_role": row.recipient_role,
                "notification_type": row.notification_type,
                "status": row.status,
                "actor_id": row.actor_id,
                "actor_role": row.actor_role,
                "title": row.title,
                "body": row.body,
                "anchor_type": row.anchor_type,
                "anchor_key": row.anchor_key,
                "metadata_json": dict(row.metadata_json or {}),
                "read_at": row.read_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def list_author_notifications(
        self,
        *,
        recipient_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        status: Optional[str] = None,
        notification_type: Optional[str] = None,
        cursor_updated_at: Optional[str] = None,
        cursor_notification_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationRow).order_by(desc(AuthorNotificationRow.updated_at), desc(AuthorNotificationRow.notification_id))
            if recipient_id is not None:
                stmt = stmt.where(AuthorNotificationRow.recipient_id == recipient_id)
            if world_version_id is not None:
                stmt = stmt.where(AuthorNotificationRow.world_version_id == world_version_id)
            if thread_id is not None:
                stmt = stmt.where(AuthorNotificationRow.thread_id == thread_id)
            if approval_id is not None:
                stmt = stmt.where(AuthorNotificationRow.approval_id == approval_id)
            if status is not None:
                stmt = stmt.where(AuthorNotificationRow.status == status)
            if notification_type is not None:
                stmt = stmt.where(AuthorNotificationRow.notification_type == notification_type)
            rows = session.execute(stmt).scalars()
            items = [
                {
                    "notification_id": row.notification_id,
                    "world_version_id": row.world_version_id,
                    "thread_id": row.thread_id,
                    "approval_id": row.approval_id,
                    "recipient_id": row.recipient_id,
                    "recipient_role": row.recipient_role,
                    "notification_type": row.notification_type,
                    "status": row.status,
                    "actor_id": row.actor_id,
                    "actor_role": row.actor_role,
                    "title": row.title,
                    "body": row.body,
                    "anchor_type": row.anchor_type,
                    "anchor_key": row.anchor_key,
                    "metadata_json": dict(row.metadata_json or {}),
                    "read_at": row.read_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]
        if cursor_updated_at is not None and cursor_notification_id is not None:
            filtered = []
            for item in items:
                updated_at = str(item.get("updated_at") or "")
                notification_id_value = str(item.get("notification_id") or "")
                if updated_at < cursor_updated_at:
                    filtered.append(item)
                elif updated_at == cursor_updated_at and notification_id_value < cursor_notification_id:
                    filtered.append(item)
            items = filtered
        if limit is not None:
            items = items[:limit]
        return items

    def save_author_notification_preference(self, preference: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "preference_id": preference.get("preference_id") or "apref_%s" % uuid4().hex[:12],
            "actor_id": preference["actor_id"],
            "notification_type": preference["notification_type"],
            "in_app_enabled": "true" if preference.get("in_app_enabled", True) else "false",
            "async_mirror_enabled": "true" if preference.get("async_mirror_enabled", True) else "false",
            "async_sink_name": preference.get("async_sink_name"),
            "delivery_target": preference.get("delivery_target"),
        }
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationPreferenceRow).where(
                AuthorNotificationPreferenceRow.actor_id == payload["actor_id"],
                AuthorNotificationPreferenceRow.notification_type == payload["notification_type"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = AuthorNotificationPreferenceRow(updated_at=now, **payload)
                session.add(row)
            else:
                row.in_app_enabled = payload["in_app_enabled"]
                row.async_mirror_enabled = payload["async_mirror_enabled"]
                row.async_sink_name = payload["async_sink_name"]
                row.delivery_target = payload["delivery_target"]
                row.updated_at = now
                payload["preference_id"] = row.preference_id
            session.commit()
        return {
            **payload,
            "in_app_enabled": payload["in_app_enabled"] == "true",
            "async_mirror_enabled": payload["async_mirror_enabled"] == "true",
            "updated_at": now,
        }

    def list_author_notification_preferences(
        self,
        *,
        actor_id: Optional[str] = None,
        notification_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthorNotificationPreferenceRow).order_by(
                AuthorNotificationPreferenceRow.actor_id.asc(),
                AuthorNotificationPreferenceRow.notification_type.asc(),
            )
            if actor_id is not None:
                stmt = stmt.where(AuthorNotificationPreferenceRow.actor_id == actor_id)
            if notification_type is not None:
                stmt = stmt.where(AuthorNotificationPreferenceRow.notification_type == notification_type)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "preference_id": row.preference_id,
                    "actor_id": row.actor_id,
                    "notification_type": row.notification_type,
                    "in_app_enabled": row.in_app_enabled == "true",
                    "async_mirror_enabled": row.async_mirror_enabled == "true",
                    "async_sink_name": row.async_sink_name,
                    "delivery_target": row.delivery_target,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_showcase_work_like(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "showcase_like_id": payload.get("showcase_like_id") or "showlike_%s" % uuid4().hex[:12],
            "world_id": payload["world_id"],
            "world_version_id": payload["world_version_id"],
            "account_id": payload["account_id"],
            "actor_id": payload.get("actor_id"),
        }
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkLikeRow).where(
                ShowcaseWorkLikeRow.world_id == record["world_id"],
                ShowcaseWorkLikeRow.account_id == record["account_id"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = ShowcaseWorkLikeRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.world_version_id = record["world_version_id"]
                row.actor_id = record["actor_id"]
                row.updated_at = now
                record["showcase_like_id"] = row.showcase_like_id
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def list_showcase_work_likes(
        self,
        *,
        world_id: Optional[str] = None,
        world_ids: Optional[List[str]] = None,
        account_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkLikeRow).order_by(desc(ShowcaseWorkLikeRow.updated_at))
            if world_id is not None:
                stmt = stmt.where(ShowcaseWorkLikeRow.world_id == world_id)
            if world_ids:
                stmt = stmt.where(ShowcaseWorkLikeRow.world_id.in_(world_ids))
            if account_id is not None:
                stmt = stmt.where(ShowcaseWorkLikeRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "showcase_like_id": row.showcase_like_id,
                    "world_id": row.world_id,
                    "world_version_id": row.world_version_id,
                    "account_id": row.account_id,
                    "actor_id": row.actor_id,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def delete_showcase_work_like(self, *, world_id: str, account_id: str) -> Dict[str, Any]:
        deleted = False
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkLikeRow).where(
                ShowcaseWorkLikeRow.world_id == world_id,
                ShowcaseWorkLikeRow.account_id == account_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is not None:
                session.execute(
                    delete(ShowcaseWorkLikeRow).where(
                        ShowcaseWorkLikeRow.showcase_like_id == row.showcase_like_id,
                    )
                )
                deleted = True
            session.commit()
        return {
            "world_id": world_id,
            "account_id": account_id,
            "deleted": deleted,
        }

    def showcase_work_like_counts(self, *, world_ids: List[str]) -> Dict[str, int]:
        items = self.list_showcase_work_likes(world_ids=world_ids)
        counts: Dict[str, int] = {}
        for item in items:
            key = str(item.get("world_id") or "")
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    def save_showcase_work_comment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "showcase_comment_id": payload.get("showcase_comment_id") or "showcomment_%s" % uuid4().hex[:12],
            "world_id": payload["world_id"],
            "world_version_id": payload["world_version_id"],
            "account_id": payload["account_id"],
            "actor_id": payload.get("actor_id"),
            "author_name": payload["author_name"],
            "content": payload["content"],
            "status": payload.get("status", "published"),
        }
        with self.SessionLocal() as session:
            row = ShowcaseWorkCommentRow(created_at=now, updated_at=now, **record)
            session.add(row)
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def list_showcase_work_comments(
        self,
        *,
        world_id: Optional[str] = None,
        world_ids: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkCommentRow).order_by(desc(ShowcaseWorkCommentRow.created_at))
            if world_id is not None:
                stmt = stmt.where(ShowcaseWorkCommentRow.world_id == world_id)
            if world_ids:
                stmt = stmt.where(ShowcaseWorkCommentRow.world_id.in_(world_ids))
            if status is not None:
                stmt = stmt.where(ShowcaseWorkCommentRow.status == status)
            if offset:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "showcase_comment_id": row.showcase_comment_id,
                    "world_id": row.world_id,
                    "world_version_id": row.world_version_id,
                    "account_id": row.account_id,
                    "actor_id": row.actor_id,
                    "author_name": row.author_name,
                    "content": row.content,
                    "status": row.status,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def showcase_work_comment_counts(self, *, world_ids: List[str], status: str = "published") -> Dict[str, int]:
        items = self.list_showcase_work_comments(world_ids=world_ids, status=status)
        counts: Dict[str, int] = {}
        for item in items:
            key = str(item.get("world_id") or "")
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    def save_showcase_work_tip(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "showcase_tip_id": payload.get("showcase_tip_id") or "showtip_%s" % uuid4().hex[:12],
            "world_id": payload["world_id"],
            "world_version_id": payload["world_version_id"],
            "account_id": payload["account_id"],
            "actor_id": payload.get("actor_id"),
            "amount": int(payload["amount"]),
            "wallet_type": payload.get("wallet_type", "story_credits"),
            "balance_after": float(payload["balance_after"]),
        }
        with self.SessionLocal() as session:
            row = ShowcaseWorkTipRow(created_at=now, updated_at=now, **record)
            session.add(row)
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def list_showcase_work_tips(
        self,
        *,
        world_id: Optional[str] = None,
        world_ids: Optional[List[str]] = None,
        account_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkTipRow).order_by(desc(ShowcaseWorkTipRow.created_at))
            if world_id is not None:
                stmt = stmt.where(ShowcaseWorkTipRow.world_id == world_id)
            if world_ids:
                stmt = stmt.where(ShowcaseWorkTipRow.world_id.in_(world_ids))
            if account_id is not None:
                stmt = stmt.where(ShowcaseWorkTipRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "showcase_tip_id": row.showcase_tip_id,
                    "world_id": row.world_id,
                    "world_version_id": row.world_version_id,
                    "account_id": row.account_id,
                    "actor_id": row.actor_id,
                    "amount": row.amount,
                    "wallet_type": row.wallet_type,
                    "balance_after": row.balance_after,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def showcase_work_tip_totals(self, *, world_ids: List[str]) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for item in self.list_showcase_work_tips(world_ids=world_ids):
            key = str(item.get("world_id") or "")
            if not key:
                continue
            totals[key] = totals.get(key, 0) + int(item.get("amount") or 0)
        return totals

    def save_showcase_work_view(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "showcase_view_id": payload.get("showcase_view_id") or "showview_%s" % uuid4().hex[:12],
            "world_id": payload["world_id"],
            "world_version_id": payload["world_version_id"],
            "account_id": payload.get("account_id"),
            "viewer_key": payload["viewer_key"],
            "event_type": payload.get("event_type", "view"),
        }
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkViewRow).where(
                ShowcaseWorkViewRow.world_id == record["world_id"],
                ShowcaseWorkViewRow.viewer_key == record["viewer_key"],
                ShowcaseWorkViewRow.event_type == record["event_type"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = ShowcaseWorkViewRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.world_version_id = record["world_version_id"]
                row.account_id = record["account_id"]
                row.updated_at = now
                record["showcase_view_id"] = row.showcase_view_id
            session.commit()
            return _showcase_work_view_payload(row)

    def list_showcase_work_views(
        self,
        *,
        world_id: Optional[str] = None,
        world_ids: Optional[List[str]] = None,
        account_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ShowcaseWorkViewRow).order_by(desc(ShowcaseWorkViewRow.updated_at))
            if world_id is not None:
                stmt = stmt.where(ShowcaseWorkViewRow.world_id == world_id)
            if world_ids:
                stmt = stmt.where(ShowcaseWorkViewRow.world_id.in_(world_ids))
            if account_id is not None:
                stmt = stmt.where(ShowcaseWorkViewRow.account_id == account_id)
            if event_type is not None:
                stmt = stmt.where(ShowcaseWorkViewRow.event_type == event_type)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [_showcase_work_view_payload(row) for row in rows]

    def showcase_work_view_counts(self, *, world_ids: List[str], event_type: str = "view") -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self.list_showcase_work_views(world_ids=world_ids, event_type=event_type):
            key = str(item.get("world_id") or "")
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    def save_library_work_favorite(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "favorite_id": payload.get("favorite_id") or "libfav_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "work_id": payload["work_id"],
            "work_kind": payload["work_kind"],
            "title_snapshot": payload.get("title_snapshot"),
        }
        with self.SessionLocal() as session:
            stmt = select(LibraryWorkFavoriteRow).where(
                LibraryWorkFavoriteRow.account_id == record["account_id"],
                LibraryWorkFavoriteRow.work_id == record["work_id"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = LibraryWorkFavoriteRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.work_kind = record["work_kind"]
                row.title_snapshot = record["title_snapshot"]
                row.updated_at = now
                record["favorite_id"] = row.favorite_id
            session.commit()
            return _library_work_favorite_payload(row)

    def list_library_work_favorites(
        self,
        *,
        account_id: Optional[str] = None,
        work_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(LibraryWorkFavoriteRow).order_by(desc(LibraryWorkFavoriteRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(LibraryWorkFavoriteRow.account_id == account_id)
            if work_id is not None:
                stmt = stmt.where(LibraryWorkFavoriteRow.work_id == work_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [_library_work_favorite_payload(row) for row in rows]

    def delete_library_work_favorite(self, *, account_id: str, work_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(LibraryWorkFavoriteRow).where(
                LibraryWorkFavoriteRow.account_id == account_id,
                LibraryWorkFavoriteRow.work_id == work_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return {
                    "favorite_id": None,
                    "account_id": account_id,
                    "work_id": work_id,
                    "deleted": False,
                }
            payload = _library_work_favorite_payload(row)
            session.delete(row)
            session.commit()
            return {
                **payload,
                "deleted": True,
            }

    def save_library_follow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "follow_id": payload.get("follow_id") or "libfollow_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "target_type": payload["target_type"],
            "target_id": payload["target_id"],
        }
        with self.SessionLocal() as session:
            stmt = select(LibraryFollowRow).where(
                LibraryFollowRow.account_id == record["account_id"],
                LibraryFollowRow.target_type == record["target_type"],
                LibraryFollowRow.target_id == record["target_id"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = LibraryFollowRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.updated_at = now
                record["follow_id"] = row.follow_id
            session.commit()
            return _library_follow_payload(row)

    def list_library_follows(
        self,
        *,
        account_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(LibraryFollowRow).order_by(desc(LibraryFollowRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(LibraryFollowRow.account_id == account_id)
            if target_type is not None:
                stmt = stmt.where(LibraryFollowRow.target_type == target_type)
            if target_id is not None:
                stmt = stmt.where(LibraryFollowRow.target_id == target_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [_library_follow_payload(row) for row in rows]

    def delete_library_follow(self, *, account_id: str, target_type: str, target_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(LibraryFollowRow).where(
                LibraryFollowRow.account_id == account_id,
                LibraryFollowRow.target_type == target_type,
                LibraryFollowRow.target_id == target_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return {
                    "follow_id": None,
                    "account_id": account_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "deleted": False,
                }
            payload = _library_follow_payload(row)
            session.delete(row)
            session.commit()
            return {
                **payload,
                "deleted": True,
            }

    def save_generated_media_asset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "asset_id": str(payload.get("asset_id") or "media_%s" % uuid4().hex[:12]),
            "asset_kind": str(payload["asset_kind"]),
            "owner_scope": str(payload["owner_scope"]),
            "owner_id": str(payload["owner_id"]),
            "world_id": str(payload.get("world_id") or "") or None,
            "world_version_id": str(payload.get("world_version_id") or "") or None,
            "session_id": str(payload.get("session_id") or "") or None,
            "chapter_index": int(payload["chapter_index"]) if payload.get("chapter_index") is not None else None,
            "reader_id": str(payload.get("reader_id") or "") or None,
            "storage_bucket": str(payload.get("storage_bucket") or "") or None,
            "storage_key": str(payload.get("storage_key") or "") or None,
            "mime_type": str(payload.get("mime_type") or "") or None,
            "width": int(payload["width"]) if payload.get("width") is not None else None,
            "height": int(payload["height"]) if payload.get("height") is not None else None,
            "visibility": str(payload.get("visibility") or "private"),
            "generation_status": str(payload.get("generation_status") or "queued"),
            "model_name": str(payload.get("model_name") or "") or None,
            "prompt_version": str(payload.get("prompt_version") or "") or None,
            "source_fingerprint": str(payload.get("source_fingerprint") or "") or None,
            "prompt_trace_json": dict(payload.get("prompt_trace_json") or {}),
            "error": str(payload.get("error") or "") or None,
        }
        with self.SessionLocal() as session:
            row = session.get(GeneratedMediaAssetRow, record["asset_id"])
            if row is None:
                row = GeneratedMediaAssetRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.asset_kind = record["asset_kind"]
                row.owner_scope = record["owner_scope"]
                row.owner_id = record["owner_id"]
                row.world_id = record["world_id"]
                row.world_version_id = record["world_version_id"]
                row.session_id = record["session_id"]
                row.chapter_index = record["chapter_index"]
                row.reader_id = record["reader_id"]
                row.storage_bucket = record["storage_bucket"]
                row.storage_key = record["storage_key"]
                row.mime_type = record["mime_type"]
                row.width = record["width"]
                row.height = record["height"]
                row.visibility = record["visibility"]
                row.generation_status = record["generation_status"]
                row.model_name = record["model_name"]
                row.prompt_version = record["prompt_version"]
                row.source_fingerprint = record["source_fingerprint"]
                row.prompt_trace_json = record["prompt_trace_json"]
                row.error = record["error"]
                row.updated_at = now
            session.commit()
            return _generated_media_asset_payload(row)

    def get_generated_media_asset(self, asset_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(GeneratedMediaAssetRow, asset_id)
            if row is None:
                raise KeyError("unknown_generated_media_asset:%s" % asset_id)
            return _generated_media_asset_payload(row)

    def list_generated_media_assets(
        self,
        *,
        asset_kind: Optional[str] = None,
        owner_scope: Optional[str] = None,
        owner_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        session_id: Optional[str] = None,
        generation_status: Optional[str] = None,
        source_fingerprint: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(GeneratedMediaAssetRow).order_by(desc(GeneratedMediaAssetRow.updated_at))
            if asset_kind is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.asset_kind == asset_kind)
            if owner_scope is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.owner_scope == owner_scope)
            if owner_id is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.owner_id == owner_id)
            if world_version_id is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.world_version_id == world_version_id)
            if session_id is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.session_id == session_id)
            if generation_status is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.generation_status == generation_status)
            if source_fingerprint is not None:
                stmt = stmt.where(GeneratedMediaAssetRow.source_fingerprint == source_fingerprint)
            stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_generated_media_asset_payload(row) for row in rows]

    def latest_generated_media_asset(
        self,
        *,
        asset_kind: str,
        owner_scope: str,
        owner_id: str,
        generation_status: Optional[str] = "succeeded",
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        items = self.list_generated_media_assets(
            asset_kind=asset_kind,
            owner_scope=owner_scope,
            owner_id=owner_id,
            generation_status=generation_status,
            limit=1,
        )
        if items:
            return items[0]
        if default is ...:
            raise KeyError(
                "unknown_generated_media_asset_latest:%s:%s:%s" % (asset_kind, owner_scope, owner_id)
            )
        return default

    def save_author_project_graph(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "project_id": str(payload.get("project_id") or payload["world_version_id"]),
            "world_version_id": str(payload["world_version_id"]),
            "account_id": str(payload["account_id"]),
            "engine": str(payload.get("engine") or "balanced"),
            "enabled_rule_ids_json": [str(item) for item in list(payload.get("enabled_rule_ids") or []) if str(item).strip()],
            "nodes_json": list(payload.get("nodes") or []),
            "connections_json": list(payload.get("connections") or []),
            "metadata_json": dict(payload.get("metadata_json") or {}),
        }
        with self.SessionLocal() as session:
            stmt = select(AuthorProjectGraphRow).where(AuthorProjectGraphRow.project_id == record["project_id"])
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = AuthorProjectGraphRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.world_version_id = record["world_version_id"]
                row.account_id = record["account_id"]
                row.engine = record["engine"]
                row.enabled_rule_ids_json = record["enabled_rule_ids_json"]
                row.nodes_json = record["nodes_json"]
                row.connections_json = record["connections_json"]
                row.metadata_json = record["metadata_json"]
                row.updated_at = now
            session.commit()
            return _author_project_graph_payload(row)

    def get_author_project_graph(
        self,
        project_id: str,
        *,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(AuthorProjectGraphRow, project_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_author_project_graph:%s" % project_id)
                return default
            return _author_project_graph_payload(row)

    def save_story_session_bookmark(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "bookmark_id": payload.get("bookmark_id") or "storybookmark_%s" % uuid4().hex[:12],
            "session_id": payload["session_id"],
            "account_id": payload["account_id"],
            "node_id": payload["node_id"],
        }
        with self.SessionLocal() as session:
            stmt = select(StorySessionBookmarkRow).where(
                StorySessionBookmarkRow.session_id == record["session_id"],
                StorySessionBookmarkRow.account_id == record["account_id"],
                StorySessionBookmarkRow.node_id == record["node_id"],
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = StorySessionBookmarkRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                record["bookmark_id"] = row.bookmark_id
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def delete_story_session_bookmark(
        self,
        *,
        session_id: str,
        account_id: str,
        node_id: str,
    ) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(StorySessionBookmarkRow).where(
                StorySessionBookmarkRow.session_id == session_id,
                StorySessionBookmarkRow.account_id == account_id,
                StorySessionBookmarkRow.node_id == node_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return {
                    "bookmark_id": None,
                    "session_id": session_id,
                    "account_id": account_id,
                    "node_id": node_id,
                    "deleted": False,
                }
            payload = {
                "bookmark_id": row.bookmark_id,
                "session_id": row.session_id,
                "account_id": row.account_id,
                "node_id": row.node_id,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "deleted": True,
            }
            session.delete(row)
            session.commit()
            return payload

    def list_story_session_bookmarks(
        self,
        *,
        session_id: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(StorySessionBookmarkRow).order_by(desc(StorySessionBookmarkRow.updated_at))
            if session_id is not None:
                stmt = stmt.where(StorySessionBookmarkRow.session_id == session_id)
            if account_id is not None:
                stmt = stmt.where(StorySessionBookmarkRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "bookmark_id": row.bookmark_id,
                    "session_id": row.session_id,
                    "account_id": row.account_id,
                    "node_id": row.node_id,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_story_session_share_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        now_dt = datetime.now(timezone.utc)

        def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            normalized = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        record = {
            "share_token": payload.get("share_token") or "storyshare_%s" % uuid4().hex[:16],
            "session_id": payload["session_id"],
            "account_id": payload["account_id"],
            "node_id": payload["node_id"],
            "sharer_name": payload["sharer_name"],
            "status": payload.get("status", "active"),
            "expires_at": payload.get("expires_at"),
            "revoked_at": payload.get("revoked_at"),
        }
        with self.SessionLocal() as session:
            stmt = (
                select(StorySessionShareTokenRow)
                .where(
                StorySessionShareTokenRow.session_id == record["session_id"],
                StorySessionShareTokenRow.account_id == record["account_id"],
                StorySessionShareTokenRow.node_id == record["node_id"],
            )
                .order_by(desc(StorySessionShareTokenRow.created_at))
            )
            rows = list(session.execute(stmt).scalars())
            row = None
            for candidate in rows:
                expires_at = _parse_timestamp(candidate.expires_at)
                if candidate.status == "active" and (expires_at is None or expires_at > now_dt):
                    row = candidate
                    break
            if row is None:
                row = StorySessionShareTokenRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                record["share_token"] = row.share_token
                record["status"] = row.status
                record["expires_at"] = row.expires_at
                record["revoked_at"] = row.revoked_at
                row.sharer_name = record["sharer_name"]
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def get_story_session_share_token(self, share_token: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(StorySessionShareTokenRow, share_token)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_story_session_share_token")
                return default
            return {
                "share_token": row.share_token,
                "session_id": row.session_id,
                "account_id": row.account_id,
                "node_id": row.node_id,
                "sharer_name": row.sharer_name,
                "status": row.status,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def revoke_story_session_share_token(self, share_token: str) -> Dict[str, Any]:
        now = utcnow_iso()
        with self.SessionLocal() as session:
            row = session.get(StorySessionShareTokenRow, share_token)
            if row is None:
                raise KeyError("unknown_story_session_share_token")
            if row.status != "revoked":
                row.status = "revoked"
                row.revoked_at = now
                row.updated_at = now
                session.commit()
            return {
                "share_token": row.share_token,
                "session_id": row.session_id,
                "account_id": row.account_id,
                "node_id": row.node_id,
                "sharer_name": row.sharer_name,
                "status": row.status,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_auth_identity(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "actor_id": identity["actor_id"],
            "account_id": identity.get("account_id"),
            "actor_role": identity["actor_role"],
            "display_name": identity.get("display_name"),
            "password_hash": identity["password_hash"],
            "password_salt": identity["password_salt"],
            "status": identity.get("status", "active"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityRow, payload["actor_id"])
            if row is None:
                row = AuthIdentityRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.actor_role = payload["actor_role"]
                row.display_name = payload["display_name"]
                row.password_hash = payload["password_hash"]
                row.password_salt = payload["password_salt"]
                row.status = payload["status"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "created_at": now,
            "updated_at": now,
        }

    def get_auth_identity(self, actor_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityRow, actor_id)
            if row is None:
                raise KeyError("unknown_auth_identity:%s" % actor_id)
            return {
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "display_name": row.display_name,
                "password_hash": row.password_hash,
                "password_salt": row.password_salt,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def get_auth_identity_by_account_id(
        self,
        account_id: str,
        *,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = (
                select(AuthIdentityRow)
                .where(AuthIdentityRow.account_id == account_id)
                .order_by(desc(AuthIdentityRow.updated_at))
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_auth_identity_for_account:%s" % account_id)
                return default
            return {
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "display_name": row.display_name,
                "password_hash": row.password_hash,
                "password_salt": row.password_salt,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def list_auth_identities(
        self,
        *,
        actor_roles: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthIdentityRow)
            if actor_roles:
                stmt = stmt.where(AuthIdentityRow.actor_role.in_([str(item) for item in actor_roles if str(item).strip()]))
            if status is not None:
                stmt = stmt.where(AuthIdentityRow.status == status)
            stmt = stmt.order_by(AuthIdentityRow.display_name.asc(), AuthIdentityRow.actor_id.asc()).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "actor_id": row.actor_id,
                    "account_id": row.account_id,
                    "actor_role": row.actor_role,
                    "display_name": row.display_name,
                    "status": row.status,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_auth_token(self, token: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "token_id": token.get("token_id") or "token_%s" % uuid4().hex[:12],
            "actor_id": token["actor_id"],
            "account_id": token.get("account_id"),
            "actor_role": token["actor_role"],
            "token_hash": token["token_hash"],
            "status": token.get("status", "active"),
            "expires_at": token.get("expires_at"),
            "last_used_at": token.get("last_used_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthTokenRow, payload["token_id"])
            if row is None:
                row = AuthTokenRow(created_at=now, **payload)
                session.add(row)
            else:
                row.actor_id = payload["actor_id"]
                row.account_id = payload["account_id"]
                row.actor_role = payload["actor_role"]
                row.token_hash = payload["token_hash"]
                row.status = payload["status"]
                row.expires_at = payload["expires_at"]
                row.last_used_at = payload["last_used_at"]
            session.commit()
        return {
            **payload,
            "created_at": now,
        }

    def get_auth_token_by_hash(self, token_hash: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(AuthTokenRow).where(AuthTokenRow.token_hash == token_hash)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                raise KeyError("unknown_auth_token")
            return {
                "token_id": row.token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "token_hash": row.token_hash,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "last_used_at": row.last_used_at,
            }

    def update_auth_token(self, token_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthTokenRow, token_id)
            if row is None:
                raise KeyError("unknown_auth_token:%s" % token_id)
            for key in ["status", "expires_at", "last_used_at", "account_id", "actor_role"]:
                if key in updates:
                    setattr(row, key, updates[key])
            session.commit()
            return {
                "token_id": row.token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "actor_role": row.actor_role,
                "token_hash": row.token_hash,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "last_used_at": row.last_used_at,
            }

    def save_soul_profile_preferences(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "actor_id": str(payload["actor_id"]),
            "account_id": str(payload.get("account_id") or "") or None,
            "genres_json": [str(item) for item in list(payload.get("genres") or []) if str(item).strip()],
            "styles_json": [str(item) for item in list(payload.get("styles") or []) if str(item).strip()],
            "privacy_mode": str(payload.get("privacy_mode") or "followers").strip() or "followers",
        }
        with self.SessionLocal() as session:
            row = session.get(SoulProfilePreferenceRow, record["actor_id"])
            if row is None:
                row = SoulProfilePreferenceRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.account_id = record["account_id"]
                row.genres_json = record["genres_json"]
                row.styles_json = record["styles_json"]
                row.privacy_mode = record["privacy_mode"]
                row.updated_at = now
            session.commit()
            return _soul_profile_preference_payload(row)

    def get_soul_profile_preferences(
        self,
        actor_id: str,
        *,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(SoulProfilePreferenceRow, actor_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_soul_profile_preferences:%s" % actor_id)
                return default
            return _soul_profile_preference_payload(row)

    def save_auth_identity_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "actor_id": profile["actor_id"],
            "account_id": profile.get("account_id"),
            "email_address": profile.get("email_address"),
            "pending_email_address": profile.get("pending_email_address"),
            "avatar_url": profile.get("avatar_url"),
            "email_verified": "true" if profile.get("email_verified") else "false",
            "verification_required": "true" if profile.get("verification_required") else "false",
            "verification_sent_at": profile.get("verification_sent_at"),
            "verified_at": profile.get("verified_at"),
            "password_reset_sent_at": profile.get("password_reset_sent_at"),
            "pending_email_change_requested_at": profile.get("pending_email_change_requested_at"),
            "email_change_last_sent_at": profile.get("email_change_last_sent_at"),
            "ui_preferences_json": dict(profile.get("ui_preferences_json") or {}) or None,
            "deactivated_at": profile.get("deactivated_at"),
            "deactivated_by": profile.get("deactivated_by"),
            "deactivation_reason": profile.get("deactivation_reason"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityProfileRow, payload["actor_id"])
            if row is None:
                row = AuthIdentityProfileRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.email_address = payload["email_address"]
                row.pending_email_address = payload["pending_email_address"]
                row.avatar_url = payload["avatar_url"]
                row.email_verified = payload["email_verified"]
                row.verification_required = payload["verification_required"]
                row.verification_sent_at = payload["verification_sent_at"]
                row.verified_at = payload["verified_at"]
                row.password_reset_sent_at = payload["password_reset_sent_at"]
                row.pending_email_change_requested_at = payload["pending_email_change_requested_at"]
                row.email_change_last_sent_at = payload["email_change_last_sent_at"]
                row.ui_preferences_json = payload["ui_preferences_json"]
                row.deactivated_at = payload["deactivated_at"]
                row.deactivated_by = payload["deactivated_by"]
                row.deactivation_reason = payload["deactivation_reason"]
                row.updated_at = now
            session.commit()
        return {
            "actor_id": payload["actor_id"],
            "account_id": payload["account_id"],
            "email_address": payload["email_address"],
            "pending_email_address": payload["pending_email_address"],
            "avatar_url": payload["avatar_url"],
            "email_verified": payload["email_verified"] == "true",
            "verification_required": payload["verification_required"] == "true",
            "verification_sent_at": payload["verification_sent_at"],
            "verified_at": payload["verified_at"],
            "password_reset_sent_at": payload["password_reset_sent_at"],
            "pending_email_change_requested_at": payload["pending_email_change_requested_at"],
            "email_change_last_sent_at": payload["email_change_last_sent_at"],
            "ui_preferences_json": dict(payload["ui_preferences_json"] or {}),
            "deactivated_at": payload["deactivated_at"],
            "deactivated_by": payload["deactivated_by"],
            "deactivation_reason": payload["deactivation_reason"],
            "created_at": now,
            "updated_at": now,
        }

    def get_auth_identity_profile_by_email_address(
        self,
        email_address: str,
        *,
        pending: bool = False,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        normalized_email = str(email_address or "").strip().lower()
        with self.SessionLocal() as session:
            stmt = select(AuthIdentityProfileRow)
            if pending:
                stmt = stmt.where(AuthIdentityProfileRow.pending_email_address == normalized_email)
            else:
                stmt = stmt.where(AuthIdentityProfileRow.email_address == normalized_email)
            stmt = stmt.order_by(desc(AuthIdentityProfileRow.updated_at)).limit(1)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_auth_identity_profile_for_email:%s" % normalized_email)
                return default
            return {
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "email_address": row.email_address,
                "pending_email_address": row.pending_email_address,
                "avatar_url": row.avatar_url,
                "email_verified": row.email_verified == "true",
                "verification_required": row.verification_required == "true",
                "verification_sent_at": row.verification_sent_at,
                "verified_at": row.verified_at,
                "password_reset_sent_at": row.password_reset_sent_at,
                "pending_email_change_requested_at": row.pending_email_change_requested_at,
                "email_change_last_sent_at": row.email_change_last_sent_at,
                "ui_preferences_json": dict(row.ui_preferences_json or {}),
                "deactivated_at": row.deactivated_at,
                "deactivated_by": row.deactivated_by,
                "deactivation_reason": row.deactivation_reason,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def get_auth_identity_profile(self, actor_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(AuthIdentityProfileRow, actor_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_auth_identity_profile:%s" % actor_id)
                return default
            return {
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "email_address": row.email_address,
                "pending_email_address": row.pending_email_address,
                "avatar_url": row.avatar_url,
                "email_verified": row.email_verified == "true",
                "verification_required": row.verification_required == "true",
                "verification_sent_at": row.verification_sent_at,
                "verified_at": row.verified_at,
                "password_reset_sent_at": row.password_reset_sent_at,
                "pending_email_change_requested_at": row.pending_email_change_requested_at,
                "email_change_last_sent_at": row.email_change_last_sent_at,
                "ui_preferences_json": dict(row.ui_preferences_json or {}),
                "deactivated_at": row.deactivated_at,
                "deactivated_by": row.deactivated_by,
                "deactivation_reason": row.deactivation_reason,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_auth_flow_token(self, token: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "flow_token_id": token.get("flow_token_id") or "flow_%s" % uuid4().hex[:12],
            "actor_id": token["actor_id"],
            "account_id": token.get("account_id"),
            "flow_type": token["flow_type"],
            "token_hash": token["token_hash"],
            "status": token.get("status", "active"),
            "payload_json": dict(token.get("payload_json") or {}),
            "expires_at": token.get("expires_at"),
            "consumed_at": token.get("consumed_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthFlowTokenRow, payload["flow_token_id"])
            if row is None:
                row = AuthFlowTokenRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.actor_id = payload["actor_id"]
                row.account_id = payload["account_id"]
                row.flow_type = payload["flow_type"]
                row.token_hash = payload["token_hash"]
                row.status = payload["status"]
                row.payload_json = payload["payload_json"]
                row.expires_at = payload["expires_at"]
                row.consumed_at = payload["consumed_at"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "created_at": now,
            "updated_at": now,
        }

    def get_auth_flow_token_by_hash(
        self,
        token_hash: str,
        *,
        flow_type: Optional[str] = None,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuthFlowTokenRow).where(AuthFlowTokenRow.token_hash == token_hash)
            if flow_type is not None:
                stmt = stmt.where(AuthFlowTokenRow.flow_type == flow_type)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_auth_flow_token")
                return default
            return {
                "flow_token_id": row.flow_token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "flow_type": row.flow_type,
                "token_hash": row.token_hash,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "expires_at": row.expires_at,
                "consumed_at": row.consumed_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def update_auth_flow_token(self, flow_token_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(AuthFlowTokenRow, flow_token_id)
            if row is None:
                raise KeyError("unknown_auth_flow_token:%s" % flow_token_id)
            for key in ["status", "payload_json", "expires_at", "consumed_at", "account_id"]:
                if key in updates:
                    value = updates[key]
                    if key == "payload_json" and value is not None:
                        value = dict(value)
                    setattr(row, key, value)
            row.updated_at = utcnow_iso()
            session.commit()
            return {
                "flow_token_id": row.flow_token_id,
                "actor_id": row.actor_id,
                "account_id": row.account_id,
                "flow_type": row.flow_type,
                "token_hash": row.token_hash,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "expires_at": row.expires_at,
                "consumed_at": row.consumed_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def update_auth_flow_tokens_for_actor(
        self,
        *,
        actor_id: str,
        flow_type: str,
        updates: Dict[str, Any],
        statuses: Optional[List[str]] = None,
        exclude_flow_token_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_actor_id = str(actor_id or "").strip()
        normalized_flow_type = str(flow_type or "").strip()
        if not normalized_actor_id or not normalized_flow_type:
            return []
        selected_statuses = [str(item).strip() for item in list(statuses or ["active"]) if str(item).strip()]
        with self.SessionLocal() as session:
            stmt = select(AuthFlowTokenRow).where(
                AuthFlowTokenRow.actor_id == normalized_actor_id,
                AuthFlowTokenRow.flow_type == normalized_flow_type,
            )
            if selected_statuses:
                stmt = stmt.where(AuthFlowTokenRow.status.in_(selected_statuses))
            if exclude_flow_token_id:
                stmt = stmt.where(AuthFlowTokenRow.flow_token_id != str(exclude_flow_token_id))
            rows = session.execute(stmt).scalars().all()
            updated_rows: List[Dict[str, Any]] = []
            for row in rows:
                for key in ["status", "payload_json", "expires_at", "consumed_at", "account_id"]:
                    if key in updates:
                        value = updates[key]
                        if key == "payload_json" and value is not None:
                            value = dict(value)
                        setattr(row, key, value)
                row.updated_at = utcnow_iso()
                updated_rows.append(
                    {
                        "flow_token_id": row.flow_token_id,
                        "actor_id": row.actor_id,
                        "account_id": row.account_id,
                        "flow_type": row.flow_type,
                        "token_hash": row.token_hash,
                        "status": row.status,
                        "payload_json": dict(row.payload_json or {}),
                        "expires_at": row.expires_at,
                        "consumed_at": row.consumed_at,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                )
            session.commit()
            return updated_rows

    def revoke_auth_tokens_for_actor(self, actor_id: str, *, reason: str = "security_reset") -> List[Dict[str, Any]]:
        now = utcnow_iso()
        with self.SessionLocal() as session:
            stmt = select(AuthTokenRow).where(AuthTokenRow.actor_id == actor_id, AuthTokenRow.status == "active")
            rows = session.execute(stmt).scalars().all()
            revoked: List[Dict[str, Any]] = []
            for row in rows:
                row.status = "revoked"
                row.last_used_at = now
                revoked.append(
                    {
                        "token_id": row.token_id,
                        "actor_id": row.actor_id,
                        "account_id": row.account_id,
                        "actor_role": row.actor_role,
                        "status": row.status,
                        "revoked_reason": reason,
                        "expires_at": row.expires_at,
                        "last_used_at": row.last_used_at,
                    }
                )
            session.commit()
            return revoked

    def save_auth_delivery_attempt(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "attempt_id": attempt.get("attempt_id") or "attempt_%s" % uuid4().hex[:12],
            "actor_id": attempt.get("actor_id"),
            "account_id": attempt.get("account_id"),
            "flow_type": attempt["flow_type"],
            "provider": attempt["provider"],
            "email_mode": attempt["email_mode"],
            "sender_email": attempt.get("sender_email"),
            "recipient_email": attempt["recipient_email"],
            "status": attempt["status"],
            "provider_message_id": attempt.get("provider_message_id"),
            "error_code": attempt.get("error_code"),
            "error_reason": attempt.get("error_reason"),
            "retryable": "true" if attempt.get("retryable") else "false",
            "metadata_json": dict(attempt.get("metadata_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(AuthDeliveryAttemptRow, payload["attempt_id"])
            if row is None:
                row = AuthDeliveryAttemptRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.actor_id = payload["actor_id"]
                row.account_id = payload["account_id"]
                row.flow_type = payload["flow_type"]
                row.provider = payload["provider"]
                row.email_mode = payload["email_mode"]
                row.sender_email = payload["sender_email"]
                row.recipient_email = payload["recipient_email"]
                row.status = payload["status"]
                row.provider_message_id = payload["provider_message_id"]
                row.error_code = payload["error_code"]
                row.error_reason = payload["error_reason"]
                row.retryable = payload["retryable"]
                row.metadata_json = payload["metadata_json"]
                row.updated_at = now
            session.commit()
        return {
            "attempt_id": payload["attempt_id"],
            "actor_id": payload["actor_id"],
            "account_id": payload["account_id"],
            "flow_type": payload["flow_type"],
            "provider": payload["provider"],
            "email_mode": payload["email_mode"],
            "sender_email": payload["sender_email"],
            "recipient_email": payload["recipient_email"],
            "status": payload["status"],
            "provider_message_id": payload["provider_message_id"],
            "error_code": payload["error_code"],
            "error_reason": payload["error_reason"],
            "retryable": payload["retryable"] == "true",
            "metadata_json": payload["metadata_json"],
            "created_at": now,
            "updated_at": now,
        }

    def save_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "plan_id": plan["plan_id"],
            "display_name": plan["display_name"],
            "subscription_tier": plan["subscription_tier"],
            "monthly_price_usd": float(plan.get("monthly_price_usd") or 0.0),
            "status": plan.get("status", "active"),
            "seat_limit": int(plan.get("seat_limit") or 0),
            "workspace_limit": int(plan.get("workspace_limit") or 0),
            "campaign_limit": int(plan.get("campaign_limit") or 0),
            "plan_payload_json": dict(plan.get("plan_payload") or plan.get("plan_payload_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(PlanRow, payload["plan_id"])
            if row is None:
                row = PlanRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.display_name = payload["display_name"]
                row.subscription_tier = payload["subscription_tier"]
                row.monthly_price_usd = payload["monthly_price_usd"]
                row.status = payload["status"]
                row.seat_limit = payload["seat_limit"]
                row.workspace_limit = payload["workspace_limit"]
                row.campaign_limit = payload["campaign_limit"]
                row.plan_payload_json = payload["plan_payload_json"]
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _plan_payload(row)

    def list_plans(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PlanRow).order_by(PlanRow.plan_id.asc())
            if status is not None:
                stmt = stmt.where(PlanRow.status == status)
            rows = session.execute(stmt).scalars()
            return [_plan_payload(row) for row in rows]

    def get_plan(self, plan_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(PlanRow, plan_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_plan:%s" % plan_id)
                return default
            return _plan_payload(row)

    def save_customer_account(self, customer_account: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "customer_account_id": customer_account.get("customer_account_id") or "cust_%s" % uuid4().hex[:12],
            "account_id": customer_account["account_id"],
            "display_name": customer_account.get("display_name"),
            "status": customer_account.get("status", "trial"),
            "plan_id": customer_account["plan_id"],
            "seat_limit": int(customer_account.get("seat_limit") or 0),
            "workspace_limit": int(customer_account.get("workspace_limit") or 0),
            "campaign_limit": int(customer_account.get("campaign_limit") or 0),
            "seat_count": int(customer_account.get("seat_count") or 0),
            "workspace_count": int(customer_account.get("workspace_count") or 0),
            "campaign_count": int(customer_account.get("campaign_count") or 0),
            "renewal_due_at": customer_account.get("renewal_due_at"),
            "metadata_json": dict(customer_account.get("metadata_json") or customer_account.get("metadata") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CustomerAccountRow, payload["customer_account_id"])
            if row is None:
                row = CustomerAccountRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.display_name = payload["display_name"]
                row.status = payload["status"]
                row.plan_id = payload["plan_id"]
                row.seat_limit = payload["seat_limit"]
                row.workspace_limit = payload["workspace_limit"]
                row.campaign_limit = payload["campaign_limit"]
                row.seat_count = payload["seat_count"]
                row.workspace_count = payload["workspace_count"]
                row.campaign_count = payload["campaign_count"]
                row.renewal_due_at = payload["renewal_due_at"]
                row.metadata_json = payload["metadata_json"]
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _customer_account_payload(row)

    def get_customer_account(self, customer_account_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(CustomerAccountRow, customer_account_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_customer_account:%s" % customer_account_id)
                return default
            return _customer_account_payload(row)

    def get_customer_account_by_account_id(
        self,
        account_id: str,
        *,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CustomerAccountRow).where(CustomerAccountRow.account_id == account_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_customer_account_for_account:%s" % account_id)
                return default
            return _customer_account_payload(row)

    def list_customer_accounts(
        self,
        *,
        status: Optional[str] = None,
        plan_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CustomerAccountRow).order_by(desc(CustomerAccountRow.updated_at))
            if status is not None:
                stmt = stmt.where(CustomerAccountRow.status == status)
            if plan_id is not None:
                stmt = stmt.where(CustomerAccountRow.plan_id == plan_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [_customer_account_payload(row) for row in rows]

    def save_billing_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "billing_profile_id": profile.get("billing_profile_id") or "billing_profile_%s" % uuid4().hex[:12],
            "customer_account_id": profile["customer_account_id"],
            "account_id": profile["account_id"],
            "provider": profile.get("provider", "internal_preview"),
            "provider_customer_ref": profile.get("provider_customer_ref"),
            "invoice_email": profile.get("invoice_email"),
            "legal_name": profile.get("legal_name"),
            "billing_country": profile.get("billing_country"),
            "tax_status": profile.get("tax_status"),
            "status": profile.get("status", "active"),
            "profile_payload_json": dict(profile.get("profile_payload_json") or profile.get("profile_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingProfileRow, payload["billing_profile_id"])
            if row is None:
                row = BillingProfileRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.customer_account_id = payload["customer_account_id"]
                row.account_id = payload["account_id"]
                row.provider = payload["provider"]
                row.provider_customer_ref = payload["provider_customer_ref"]
                row.invoice_email = payload["invoice_email"]
                row.legal_name = payload["legal_name"]
                row.billing_country = payload["billing_country"]
                row.tax_status = payload["tax_status"]
                row.status = payload["status"]
                row.profile_payload_json = payload["profile_payload_json"]
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _billing_profile_payload(row)

    def list_billing_profiles(
        self,
        *,
        customer_account_id: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingProfileRow).order_by(desc(BillingProfileRow.updated_at))
            if customer_account_id is not None:
                stmt = stmt.where(BillingProfileRow.customer_account_id == customer_account_id)
            if account_id is not None:
                stmt = stmt.where(BillingProfileRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(BillingProfileRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [_billing_profile_payload(row) for row in rows]

    def get_billing_profile(self, billing_profile_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(BillingProfileRow, billing_profile_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_billing_profile:%s" % billing_profile_id)
                return default
            return _billing_profile_payload(row)

    def save_usage_ledger(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "usage_ledger_id": payload.get("usage_ledger_id") or "usage_ledger_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "plan_id": payload.get("plan_id"),
            "status": payload.get("status", "open"),
            "billing_period_start": payload["billing_period_start"],
            "billing_period_end": payload["billing_period_end"],
            "presented_count": int(payload.get("presented_count") or 0),
            "handoff_count": int(payload.get("handoff_count") or 0),
            "conversion_count": int(payload.get("conversion_count") or 0),
            "subtotal_amount_usd": float(payload.get("subtotal_amount_usd") or 0.0),
            "disputed_amount_usd": float(payload.get("disputed_amount_usd") or 0.0),
            "credited_amount_usd": float(payload.get("credited_amount_usd") or 0.0),
            "reversed_amount_usd": float(payload.get("reversed_amount_usd") or 0.0),
            "ledger_payload_json": dict(payload.get("ledger_payload_json") or payload.get("ledger_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(UsageLedgerRow, record["usage_ledger_id"])
            if row is None:
                row = UsageLedgerRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _usage_ledger_payload(row)

    def list_usage_ledgers(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(UsageLedgerRow).order_by(desc(UsageLedgerRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(UsageLedgerRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(UsageLedgerRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(UsageLedgerRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_usage_ledger_payload(row) for row in rows]

    def get_usage_ledger(self, usage_ledger_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(UsageLedgerRow, usage_ledger_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_usage_ledger:%s" % usage_ledger_id)
                return default
            return _usage_ledger_payload(row)

    def save_billable_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "billable_event_id": payload.get("billable_event_id") or "billable_event_%s" % uuid4().hex[:12],
            "usage_ledger_id": payload.get("usage_ledger_id"),
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "plan_id": payload.get("plan_id"),
            "billable_metric": payload["billable_metric"],
            "status": payload.get("status", "recorded"),
            "trace_id": payload.get("trace_id"),
            "quality_event_id": payload.get("quality_event_id"),
            "runtime_receipt_event_id": payload.get("runtime_receipt_event_id"),
            "feedback_item_id": payload.get("feedback_item_id"),
            "source_surface": payload.get("source_surface"),
            "world_version_id": payload.get("world_version_id"),
            "session_id": payload.get("session_id"),
            "quantity": float(payload.get("quantity") or 0.0),
            "unit_price_usd": float(payload.get("unit_price_usd") or 0.0),
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "reason_codes_json": list(payload.get("reason_codes_json") or payload.get("reason_codes") or []),
            "event_payload_json": dict(payload.get("event_payload_json") or payload.get("event_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(BillableEventRow, record["billable_event_id"])
            if row is None:
                row = BillableEventRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _billable_event_payload(row)

    def list_billable_events(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        billable_metric: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillableEventRow).order_by(desc(BillableEventRow.created_at))
            if account_id is not None:
                stmt = stmt.where(BillableEventRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(BillableEventRow.customer_account_id == customer_account_id)
            if trace_id is not None:
                stmt = stmt.where(BillableEventRow.trace_id == trace_id)
            if billable_metric is not None:
                stmt = stmt.where(BillableEventRow.billable_metric == billable_metric)
            if status is not None:
                stmt = stmt.where(BillableEventRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_billable_event_payload(row) for row in rows]

    def get_billable_event(self, billable_event_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(BillableEventRow, billable_event_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_billable_event:%s" % billable_event_id)
                return default
            return _billable_event_payload(row)

    def update_billable_event_status(self, billable_event_id: str, *, status: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(BillableEventRow, billable_event_id)
            if row is None:
                raise KeyError("unknown_billable_event:%s" % billable_event_id)
            row.status = status
            row.updated_at = utcnow_iso()
            session.commit()
            session.refresh(row)
            return _billable_event_payload(row)

    def save_invoice_preview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "invoice_preview_id": payload.get("invoice_preview_id") or "invoice_preview_%s" % uuid4().hex[:12],
            "usage_ledger_id": payload.get("usage_ledger_id"),
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "plan_id": payload.get("plan_id"),
            "status": payload.get("status", "draft"),
            "billing_period_start": payload["billing_period_start"],
            "billing_period_end": payload["billing_period_end"],
            "subtotal_amount_usd": float(payload.get("subtotal_amount_usd") or 0.0),
            "credits_applied_usd": float(payload.get("credits_applied_usd") or 0.0),
            "disputed_amount_usd": float(payload.get("disputed_amount_usd") or 0.0),
            "credited_amount_usd": float(payload.get("credited_amount_usd") or 0.0),
            "reversed_amount_usd": float(payload.get("reversed_amount_usd") or 0.0),
            "total_due_usd": float(payload.get("total_due_usd") or 0.0),
            "line_items_json": list(payload.get("line_items_json") or payload.get("line_items") or []),
            "summary_json": dict(payload.get("summary_json") or payload.get("summary") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(InvoicePreviewRow, record["invoice_preview_id"])
            if row is None:
                row = InvoicePreviewRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _invoice_preview_payload(row)

    def list_invoice_previews(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(InvoicePreviewRow).order_by(desc(InvoicePreviewRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(InvoicePreviewRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(InvoicePreviewRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(InvoicePreviewRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_invoice_preview_payload(row) for row in rows]

    def get_invoice_preview(self, invoice_preview_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(InvoicePreviewRow, invoice_preview_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_invoice_preview:%s" % invoice_preview_id)
                return default
            return _invoice_preview_payload(row)

    def save_credit_balance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "credit_balance_id": payload.get("credit_balance_id") or "credit_balance_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "balance_type": payload["balance_type"],
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "source_ref_json": dict(payload.get("source_ref_json") or payload.get("source_ref") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CreditBalanceRow, record["credit_balance_id"])
            if row is None:
                row = CreditBalanceRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _credit_balance_payload(row)

    def list_credit_balances(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        balance_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CreditBalanceRow).order_by(desc(CreditBalanceRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(CreditBalanceRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(CreditBalanceRow.customer_account_id == customer_account_id)
            if balance_type is not None:
                stmt = stmt.where(CreditBalanceRow.balance_type == balance_type)
            rows = session.execute(stmt).scalars().all()
            return [_credit_balance_payload(row) for row in rows]

    def save_overage_flag(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "overage_flag_id": payload.get("overage_flag_id") or "overage_flag_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "plan_id": payload.get("plan_id"),
            "metric_type": payload["metric_type"],
            "status": payload.get("status", "active"),
            "observed_units": float(payload.get("observed_units") or 0.0),
            "included_units": float(payload.get("included_units") or 0.0),
            "overage_units": float(payload.get("overage_units") or 0.0),
            "flag_payload_json": dict(payload.get("flag_payload_json") or payload.get("flag_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(OverageFlagRow, record["overage_flag_id"])
            if row is None:
                row = OverageFlagRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _overage_flag_payload(row)

    def list_overage_flags(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(OverageFlagRow).order_by(desc(OverageFlagRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(OverageFlagRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(OverageFlagRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(OverageFlagRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_overage_flag_payload(row) for row in rows]

    def save_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "campaign_id": payload.get("campaign_id") or "campaign_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "title": payload["title"],
            "target_icp_vertical": payload["target_icp_vertical"],
            "cta_text": payload["cta_text"],
            "disclosure_text": payload["disclosure_text"],
            "activation_status": payload.get("activation_status", "draft"),
            "selected_channels_json": list(payload.get("selected_channels_json") or payload.get("selected_channels") or []),
            "selected_partner_refs_json": list(payload.get("selected_partner_refs_json") or payload.get("selected_partner_refs") or []),
            "primary_review_case_id": payload.get("primary_review_case_id"),
            "latest_submission_id": payload.get("latest_submission_id"),
            "campaign_payload_json": dict(payload.get("campaign_payload_json") or payload.get("campaign_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CampaignRow, record["campaign_id"])
            if row is None:
                row = CampaignRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _campaign_payload(row)

    def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(CampaignRow, campaign_id)
            if row is None:
                raise KeyError("unknown_campaign:%s" % campaign_id)
            return _campaign_payload(row)

    def list_campaigns(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        activation_status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CampaignRow).order_by(desc(CampaignRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(CampaignRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(CampaignRow.customer_account_id == customer_account_id)
            if activation_status is not None:
                stmt = stmt.where(CampaignRow.activation_status == activation_status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_campaign_payload(row) for row in rows]

    def save_campaign_proof_bundle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "proof_bundle_id": payload.get("proof_bundle_id") or "campaign_proof_%s" % uuid4().hex[:12],
            "campaign_id": payload["campaign_id"],
            "bundle_label": payload.get("bundle_label", "default"),
            "proof_points_json": list(payload.get("proof_points_json") or payload.get("proof_points") or []),
            "source_urls_json": list(payload.get("source_urls_json") or payload.get("source_urls") or []),
            "artifact_refs_json": list(payload.get("artifact_refs_json") or payload.get("artifact_refs") or []),
            "bundle_payload_json": dict(payload.get("bundle_payload_json") or payload.get("bundle_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CampaignProofBundleRow, record["proof_bundle_id"])
            if row is None:
                row = CampaignProofBundleRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _campaign_proof_bundle_payload(row)

    def replace_campaign_proof_bundles(self, *, campaign_id: str, bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            session.execute(delete(CampaignProofBundleRow).where(CampaignProofBundleRow.campaign_id == campaign_id))
            session.commit()
        saved: List[Dict[str, Any]] = []
        for bundle in bundles:
            saved.append(self.save_campaign_proof_bundle({**bundle, "campaign_id": campaign_id}))
        return saved

    def list_campaign_proof_bundles(self, *, campaign_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CampaignProofBundleRow).where(CampaignProofBundleRow.campaign_id == campaign_id).order_by(desc(CampaignProofBundleRow.updated_at))
            rows = session.execute(stmt).scalars().all()
            return [_campaign_proof_bundle_payload(row) for row in rows]

    def save_campaign_channel_target(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "channel_target_id": payload.get("channel_target_id") or "channel_target_%s" % uuid4().hex[:12],
            "campaign_id": payload["campaign_id"],
            "channel_name": payload["channel_name"],
            "partner_ref": payload.get("partner_ref"),
            "priority": int(payload.get("priority") or 0),
            "readiness_status": payload.get("readiness_status", "selected"),
            "target_payload_json": dict(payload.get("target_payload_json") or payload.get("target_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CampaignChannelTargetRow, record["channel_target_id"])
            if row is None:
                row = CampaignChannelTargetRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _campaign_channel_target_payload(row)

    def replace_campaign_channel_targets(self, *, campaign_id: str, targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            session.execute(delete(CampaignChannelTargetRow).where(CampaignChannelTargetRow.campaign_id == campaign_id))
            session.commit()
        saved: List[Dict[str, Any]] = []
        for target in targets:
            saved.append(self.save_campaign_channel_target({**target, "campaign_id": campaign_id}))
        return saved

    def list_campaign_channel_targets(self, *, campaign_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CampaignChannelTargetRow).where(CampaignChannelTargetRow.campaign_id == campaign_id).order_by(CampaignChannelTargetRow.priority.asc(), CampaignChannelTargetRow.updated_at.desc())
            rows = session.execute(stmt).scalars().all()
            return [_campaign_channel_target_payload(row) for row in rows]

    def save_campaign_review_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "submission_id": payload.get("submission_id") or "campaign_submission_%s" % uuid4().hex[:12],
            "campaign_id": payload["campaign_id"],
            "review_case_id": payload.get("review_case_id"),
            "status": payload.get("status", "submitted"),
            "submitted_by": payload["submitted_by"],
            "reviewer_id": payload.get("reviewer_id"),
            "decision_note": payload.get("decision_note"),
            "submitted_at": payload.get("submitted_at") or now,
            "decided_at": payload.get("decided_at"),
            "submission_payload_json": dict(payload.get("submission_payload_json") or payload.get("submission_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(CampaignReviewSubmissionRow, record["submission_id"])
            if row is None:
                row = CampaignReviewSubmissionRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _campaign_review_submission_payload(row)

    def get_campaign_review_submission(self, submission_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(CampaignReviewSubmissionRow, submission_id)
            if row is None:
                raise KeyError("unknown_campaign_review_submission:%s" % submission_id)
            return _campaign_review_submission_payload(row)

    def list_campaign_review_submissions(
        self,
        *,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
        review_case_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CampaignReviewSubmissionRow).order_by(desc(CampaignReviewSubmissionRow.updated_at))
            if campaign_id is not None:
                stmt = stmt.where(CampaignReviewSubmissionRow.campaign_id == campaign_id)
            if status is not None:
                stmt = stmt.where(CampaignReviewSubmissionRow.status == status)
            if review_case_id is not None:
                stmt = stmt.where(CampaignReviewSubmissionRow.review_case_id == review_case_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_campaign_review_submission_payload(row) for row in rows]

    def save_partner(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "partner_id": payload.get("partner_id") or "partner_%s" % uuid4().hex[:12],
            "name": payload["name"],
            "lifecycle_status": payload.get("lifecycle_status", "discovered"),
            "sla_status": payload.get("sla_status", "unknown"),
            "receipt_capability": payload.get("receipt_capability", "unknown"),
            "disclosure_readiness": payload.get("disclosure_readiness", "unknown"),
            "billing_readiness": payload.get("billing_readiness", "unknown"),
            "allowlisted_channels_json": list(payload.get("allowlisted_channels_json") or payload.get("allowlisted_channels") or []),
            "primary_endpoint_url": payload.get("primary_endpoint_url"),
            "endpoint_health_status": payload.get("endpoint_health_status", "unknown"),
            "partner_payload_json": dict(payload.get("partner_payload_json") or payload.get("partner_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(PartnerRow, record["partner_id"])
            if row is None:
                row = PartnerRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _partner_payload(row)

    def get_partner(self, partner_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(PartnerRow, partner_id)
            if row is None:
                raise KeyError("unknown_partner:%s" % partner_id)
            return _partner_payload(row)

    def list_partners(
        self,
        *,
        lifecycle_status: Optional[str] = None,
        endpoint_health_status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PartnerRow).order_by(desc(PartnerRow.updated_at))
            if lifecycle_status is not None:
                stmt = stmt.where(PartnerRow.lifecycle_status == lifecycle_status)
            if endpoint_health_status is not None:
                stmt = stmt.where(PartnerRow.endpoint_health_status == endpoint_health_status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_partner_payload(row) for row in rows]

    def save_partner_capability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "partner_capability_id": payload.get("partner_capability_id") or "partner_capability_%s" % uuid4().hex[:12],
            "partner_id": payload["partner_id"],
            "capability_type": payload["capability_type"],
            "status": payload.get("status", "unknown"),
            "capability_value": payload.get("capability_value"),
            "capability_payload_json": dict(payload.get("capability_payload_json") or payload.get("capability_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(PartnerCapabilityRow, record["partner_capability_id"])
            if row is None:
                row = PartnerCapabilityRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _partner_capability_payload(row)

    def replace_partner_capabilities(self, *, partner_id: str, capabilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            session.execute(delete(PartnerCapabilityRow).where(PartnerCapabilityRow.partner_id == partner_id))
            session.commit()
        saved: List[Dict[str, Any]] = []
        for capability in capabilities:
            saved.append(self.save_partner_capability({**capability, "partner_id": partner_id}))
        return saved

    def list_partner_capabilities(self, *, partner_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PartnerCapabilityRow).where(PartnerCapabilityRow.partner_id == partner_id).order_by(desc(PartnerCapabilityRow.updated_at))
            rows = session.execute(stmt).scalars().all()
            return [_partner_capability_payload(row) for row in rows]

    def save_partner_health_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "health_check_id": payload.get("health_check_id") or "partner_health_%s" % uuid4().hex[:12],
            "partner_id": payload["partner_id"],
            "endpoint_url": payload.get("endpoint_url"),
            "status": payload.get("status", "unknown"),
            "status_code": payload.get("status_code"),
            "response_time_ms": payload.get("response_time_ms"),
            "checked_at": payload.get("checked_at") or now,
            "health_payload_json": dict(payload.get("health_payload_json") or payload.get("health_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(PartnerHealthCheckRow, record["health_check_id"])
            if row is None:
                row = PartnerHealthCheckRow(created_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _partner_health_check_payload(row)

    def list_partner_health_checks(self, *, partner_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PartnerHealthCheckRow).where(PartnerHealthCheckRow.partner_id == partner_id).order_by(desc(PartnerHealthCheckRow.checked_at))
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_partner_health_check_payload(row) for row in rows]

    def save_dispute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "dispute_id": payload.get("dispute_id") or "dispute_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "campaign_id": payload.get("campaign_id"),
            "invoice_preview_id": payload.get("invoice_preview_id"),
            "billable_event_id": payload.get("billable_event_id"),
            "quality_event_id": payload.get("quality_event_id"),
            "trace_id": payload.get("trace_id"),
            "dispute_reason_code": payload["dispute_reason_code"],
            "note": payload.get("note"),
            "status": payload.get("status", "open"),
            "requested_amount_usd": float(payload.get("requested_amount_usd") or 0.0),
            "resolved_amount_usd": float(payload.get("resolved_amount_usd") or 0.0),
            "requested_by": payload["requested_by"],
            "reviewer_id": payload.get("reviewer_id"),
            "resolution_note": payload.get("resolution_note"),
            "dispute_payload_json": dict(payload.get("dispute_payload_json") or payload.get("dispute_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(DisputeRow, record["dispute_id"])
            if row is None:
                row = DisputeRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _dispute_payload(row)

    def get_dispute(self, dispute_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(DisputeRow, dispute_id)
            if row is None:
                raise KeyError("unknown_dispute:%s" % dispute_id)
            return _dispute_payload(row)

    def list_disputes(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(DisputeRow).order_by(desc(DisputeRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(DisputeRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(DisputeRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(DisputeRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_dispute_payload(row) for row in rows]

    def save_refund_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "refund_request_id": payload.get("refund_request_id") or "refund_%s" % uuid4().hex[:12],
            "dispute_id": payload.get("dispute_id"),
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "invoice_preview_id": payload.get("invoice_preview_id"),
            "billable_event_id": payload.get("billable_event_id"),
            "trace_id": payload.get("trace_id"),
            "status": payload.get("status", "requested"),
            "requested_amount_usd": float(payload.get("requested_amount_usd") or 0.0),
            "approved_amount_usd": float(payload.get("approved_amount_usd") or 0.0),
            "requested_by": payload["requested_by"],
            "reviewer_id": payload.get("reviewer_id"),
            "refund_payload_json": dict(payload.get("refund_payload_json") or payload.get("refund_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(RefundRequestRow, record["refund_request_id"])
            if row is None:
                row = RefundRequestRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _refund_request_payload(row)

    def list_refund_requests(
        self,
        *,
        account_id: Optional[str] = None,
        dispute_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(RefundRequestRow).order_by(desc(RefundRequestRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(RefundRequestRow.account_id == account_id)
            if dispute_id is not None:
                stmt = stmt.where(RefundRequestRow.dispute_id == dispute_id)
            if status is not None:
                stmt = stmt.where(RefundRequestRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_refund_request_payload(row) for row in rows]

    def save_settlement_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "settlement_run_id": payload.get("settlement_run_id") or "settlement_run_%s" % uuid4().hex[:12],
            "customer_account_id": payload.get("customer_account_id"),
            "account_id": payload.get("account_id"),
            "billing_period_start": payload.get("billing_period_start"),
            "billing_period_end": payload.get("billing_period_end"),
            "status": payload.get("status", "draft"),
            "subtotal_amount_usd": float(payload.get("subtotal_amount_usd") or 0.0),
            "disputed_amount_usd": float(payload.get("disputed_amount_usd") or 0.0),
            "credited_amount_usd": float(payload.get("credited_amount_usd") or 0.0),
            "reversed_amount_usd": float(payload.get("reversed_amount_usd") or 0.0),
            "refunded_amount_usd": float(payload.get("refunded_amount_usd") or 0.0),
            "net_amount_usd": float(payload.get("net_amount_usd") or 0.0),
            "run_payload_json": dict(payload.get("run_payload_json") or payload.get("run_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(SettlementRunRow, record["settlement_run_id"])
            if row is None:
                row = SettlementRunRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _settlement_run_payload(row)

    def list_settlement_runs(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SettlementRunRow).order_by(desc(SettlementRunRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(SettlementRunRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(SettlementRunRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_settlement_run_payload(row) for row in rows]

    def save_settlement_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "settlement_item_id": payload.get("settlement_item_id") or "settlement_item_%s" % uuid4().hex[:12],
            "settlement_run_id": payload["settlement_run_id"],
            "billable_event_id": payload.get("billable_event_id"),
            "invoice_preview_id": payload.get("invoice_preview_id"),
            "dispute_id": payload.get("dispute_id"),
            "refund_request_id": payload.get("refund_request_id"),
            "status": payload.get("status", "approved"),
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "item_payload_json": dict(payload.get("item_payload_json") or payload.get("item_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(SettlementItemRow, record["settlement_item_id"])
            if row is None:
                row = SettlementItemRow(created_at=utcnow_iso(), **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _settlement_item_payload(row)

    def list_settlement_items(self, *, settlement_run_id: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SettlementItemRow).where(SettlementItemRow.settlement_run_id == settlement_run_id).order_by(desc(SettlementItemRow.created_at))
            rows = session.execute(stmt).scalars().all()
            return [_settlement_item_payload(row) for row in rows]

    def save_support_case(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "support_case_id": payload.get("support_case_id") or "support_case_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "campaign_id": payload.get("campaign_id"),
            "invoice_preview_id": payload.get("invoice_preview_id"),
            "billable_event_id": payload.get("billable_event_id"),
            "quality_event_id": payload.get("quality_event_id"),
            "trace_id": payload.get("trace_id"),
            "case_type": payload.get("case_type", "general"),
            "subject": payload["subject"],
            "description": payload["description"],
            "status": payload.get("status", "open"),
            "priority": payload.get("priority", "medium"),
            "requested_by": payload["requested_by"],
            "owner_id": payload.get("owner_id"),
            "resolution_note": payload.get("resolution_note"),
            "support_payload_json": dict(payload.get("support_payload_json") or payload.get("support_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(SupportCaseRow, record["support_case_id"])
            if row is None:
                row = SupportCaseRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _support_case_payload(row)

    def get_support_case(self, support_case_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SupportCaseRow, support_case_id)
            if row is None:
                raise KeyError("unknown_support_case:%s" % support_case_id)
            return _support_case_payload(row)

    def list_support_cases(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SupportCaseRow).order_by(desc(SupportCaseRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(SupportCaseRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(SupportCaseRow.status == status)
            if owner_id is not None:
                stmt = stmt.where(SupportCaseRow.owner_id == owner_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_support_case_payload(row) for row in rows]

    def save_manual_adjustment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "adjustment_id": payload.get("adjustment_id") or "adjustment_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "dispute_id": payload.get("dispute_id"),
            "refund_request_id": payload.get("refund_request_id"),
            "invoice_preview_id": payload.get("invoice_preview_id"),
            "billable_event_id": payload.get("billable_event_id"),
            "adjustment_type": payload["adjustment_type"],
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "status": payload.get("status", "applied"),
            "requested_by": payload["requested_by"],
            "reviewer_id": payload.get("reviewer_id"),
            "adjustment_payload_json": dict(payload.get("adjustment_payload_json") or payload.get("adjustment_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ManualAdjustmentRow, record["adjustment_id"])
            if row is None:
                row = ManualAdjustmentRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _manual_adjustment_payload(row)

    def list_manual_adjustments(
        self,
        *,
        account_id: Optional[str] = None,
        dispute_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ManualAdjustmentRow).order_by(desc(ManualAdjustmentRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(ManualAdjustmentRow.account_id == account_id)
            if dispute_id is not None:
                stmt = stmt.where(ManualAdjustmentRow.dispute_id == dispute_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_manual_adjustment_payload(row) for row in rows]

    def save_audit_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "audit_log_id": payload.get("audit_log_id") or "audit_%s" % uuid4().hex[:12],
            "actor_id": payload["actor_id"],
            "actor_role": payload["actor_role"],
            "account_id": payload.get("account_id"),
            "customer_account_id": payload.get("customer_account_id"),
            "object_type": payload["object_type"],
            "object_id": payload["object_id"],
            "action_type": payload["action_type"],
            "source_surface": payload.get("source_surface", "system"),
            "customer_visible_payload_json": dict(payload.get("customer_visible_payload_json") or payload.get("customer_visible_payload") or {}),
            "internal_payload_json": dict(payload.get("internal_payload_json") or payload.get("internal_payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(AuditLogRow, record["audit_log_id"])
            if row is None:
                row = AuditLogRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _audit_log_payload(row)

    def list_audit_logs(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AuditLogRow).order_by(desc(AuditLogRow.created_at))
            if account_id is not None:
                stmt = stmt.where(AuditLogRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(AuditLogRow.customer_account_id == customer_account_id)
            if actor_id is not None:
                stmt = stmt.where(AuditLogRow.actor_id == actor_id)
            if object_type is not None:
                stmt = stmt.where(AuditLogRow.object_type == object_type)
            if object_id is not None:
                stmt = stmt.where(AuditLogRow.object_id == object_id)
            if action_type is not None:
                stmt = stmt.where(AuditLogRow.action_type == action_type)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_audit_log_payload(row) for row in rows]

    def save_customer_audit_export(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "audit_export_id": payload.get("audit_export_id") or "audit_export_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "requested_by": payload["requested_by"],
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "export_payload_json": dict(payload.get("export_payload_json") or payload.get("export_payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(CustomerAuditExportRow, record["audit_export_id"])
            if row is None:
                row = CustomerAuditExportRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _customer_audit_export_payload(row)

    def save_data_retention_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "retention_policy_id": payload.get("retention_policy_id") or "retention_policy_%s" % uuid4().hex[:12],
            "scope": payload["scope"],
            "retention_days": int(payload.get("retention_days") or 0),
            "deletion_mode": payload.get("deletion_mode", "manual_request"),
            "status": payload.get("status", "active"),
            "policy_payload_json": dict(payload.get("policy_payload_json") or payload.get("policy_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(DataRetentionPolicyRow, record["retention_policy_id"])
            if row is None:
                row = DataRetentionPolicyRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _data_retention_policy_payload(row)

    def list_data_retention_policies(self, *, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(DataRetentionPolicyRow).order_by(DataRetentionPolicyRow.scope.asc(), DataRetentionPolicyRow.updated_at.desc())
            if scope is not None:
                stmt = stmt.where(DataRetentionPolicyRow.scope == scope)
            rows = session.execute(stmt).scalars().all()
            return [_data_retention_policy_payload(row) for row in rows]

    def save_data_deletion_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "deletion_request_id": payload.get("deletion_request_id") or "deletion_request_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "requested_by": payload["requested_by"],
            "scope": payload["scope"],
            "status": payload.get("status", "requested"),
            "requested_payload_json": dict(payload.get("requested_payload_json") or payload.get("requested_payload") or {}),
            "affected_object_counts_json": dict(payload.get("affected_object_counts_json") or payload.get("affected_object_counts") or {}),
            "resolution_note": payload.get("resolution_note"),
        }
        with self.SessionLocal() as session:
            row = session.get(DataDeletionRequestRow, record["deletion_request_id"])
            if row is None:
                row = DataDeletionRequestRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _data_deletion_request_payload(row)

    def list_data_deletion_requests(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(DataDeletionRequestRow).order_by(desc(DataDeletionRequestRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(DataDeletionRequestRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(DataDeletionRequestRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(DataDeletionRequestRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_data_deletion_request_payload(row) for row in rows]

    def save_invoice_issuance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "invoice_id": payload.get("invoice_id") or "invoice_%s" % uuid4().hex[:12],
            "invoice_preview_id": payload["invoice_preview_id"],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "provider": payload["provider"],
            "provider_invoice_ref": payload.get("provider_invoice_ref"),
            "provider_customer_ref": payload.get("provider_customer_ref"),
            "status": payload.get("status", "draft"),
            "currency": payload.get("currency", "USD"),
            "subtotal_amount_usd": float(payload.get("subtotal_amount_usd") or 0.0),
            "total_due_usd": float(payload.get("total_due_usd") or 0.0),
            "hosted_invoice_url": payload.get("hosted_invoice_url"),
            "invoice_pdf_url": payload.get("invoice_pdf_url"),
            "issued_at": payload.get("issued_at"),
            "paid_at": payload.get("paid_at"),
            "voided_at": payload.get("voided_at"),
            "invoice_payload_json": dict(payload.get("invoice_payload_json") or payload.get("invoice_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(InvoiceIssuanceRow, record["invoice_id"])
            if row is None:
                row = InvoiceIssuanceRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _invoice_issuance_payload(row)

    def get_invoice_issuance(self, invoice_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(InvoiceIssuanceRow, invoice_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_invoice:%s" % invoice_id)
                return default
            return _invoice_issuance_payload(row)

    def get_invoice_issuance_by_provider_ref(self, provider_invoice_ref: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(InvoiceIssuanceRow).where(InvoiceIssuanceRow.provider_invoice_ref == provider_invoice_ref)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_invoice_provider_ref:%s" % provider_invoice_ref)
                return default
            return _invoice_issuance_payload(row)

    def list_invoice_issuances(
        self,
        *,
        account_id: Optional[str] = None,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(InvoiceIssuanceRow).order_by(desc(InvoiceIssuanceRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(InvoiceIssuanceRow.account_id == account_id)
            if customer_account_id is not None:
                stmt = stmt.where(InvoiceIssuanceRow.customer_account_id == customer_account_id)
            if status is not None:
                stmt = stmt.where(InvoiceIssuanceRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_invoice_issuance_payload(row) for row in rows]

    def save_payment_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "payment_transaction_id": payload.get("payment_transaction_id") or "payment_tx_%s" % uuid4().hex[:12],
            "invoice_id": payload.get("invoice_id"),
            "customer_account_id": payload.get("customer_account_id"),
            "account_id": payload["account_id"],
            "provider": payload["provider"],
            "provider_transaction_ref": payload.get("provider_transaction_ref"),
            "transaction_type": payload.get("transaction_type", "payment"),
            "status": payload.get("status", "pending"),
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "currency": payload.get("currency", "USD"),
            "trace_id": payload.get("trace_id"),
            "transaction_payload_json": dict(payload.get("transaction_payload_json") or payload.get("transaction_payload") or {}),
            "occurred_at": payload.get("occurred_at") or utcnow_iso(),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(PaymentTransactionRow, record["payment_transaction_id"])
            if row is None:
                row = PaymentTransactionRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _payment_transaction_payload(row)

    def list_payment_transactions(
        self,
        *,
        account_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PaymentTransactionRow).order_by(desc(PaymentTransactionRow.occurred_at))
            if account_id is not None:
                stmt = stmt.where(PaymentTransactionRow.account_id == account_id)
            if invoice_id is not None:
                stmt = stmt.where(PaymentTransactionRow.invoice_id == invoice_id)
            if transaction_type is not None:
                stmt = stmt.where(PaymentTransactionRow.transaction_type == transaction_type)
            if status is not None:
                stmt = stmt.where(PaymentTransactionRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_payment_transaction_payload(row) for row in rows]

    def save_provider_webhook_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "provider_webhook_event_id": payload.get("provider_webhook_event_id") or "provider_webhook_%s" % uuid4().hex[:12],
            "provider": payload["provider"],
            "provider_event_id": payload["provider_event_id"],
            "event_type": payload["event_type"],
            "status": payload.get("status", "received"),
            "invoice_id": payload.get("invoice_id"),
            "account_id": payload.get("account_id"),
            "payload_json": dict(payload.get("payload_json") or payload.get("payload") or {}),
            "processing_result_json": dict(payload.get("processing_result_json") or payload.get("processing_result") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
            "processed_at": payload.get("processed_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(ProviderWebhookEventRow, record["provider_webhook_event_id"])
            if row is None:
                row = ProviderWebhookEventRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _provider_webhook_event_payload(row)

    def get_provider_webhook_event(self, provider_webhook_event_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(ProviderWebhookEventRow, provider_webhook_event_id)
            if row is None:
                raise KeyError("unknown_provider_webhook_event:%s" % provider_webhook_event_id)
            return _provider_webhook_event_payload(row)

    def get_provider_webhook_event_by_provider_ref(self, provider: str, provider_event_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProviderWebhookEventRow).where(
                ProviderWebhookEventRow.provider == provider,
                ProviderWebhookEventRow.provider_event_id == provider_event_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_provider_webhook_event_ref")
                return default
            return _provider_webhook_event_payload(row)

    def list_provider_webhook_events(
        self,
        *,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProviderWebhookEventRow).order_by(desc(ProviderWebhookEventRow.created_at))
            if provider is not None:
                stmt = stmt.where(ProviderWebhookEventRow.provider == provider)
            if status is not None:
                stmt = stmt.where(ProviderWebhookEventRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_provider_webhook_event_payload(row) for row in rows]

    def save_credit_note(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "credit_note_id": payload.get("credit_note_id") or "credit_note_%s" % uuid4().hex[:12],
            "invoice_id": payload["invoice_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "account_id": payload["account_id"],
            "provider": payload["provider"],
            "provider_credit_note_ref": payload.get("provider_credit_note_ref"),
            "status": payload.get("status", "issued"),
            "amount_usd": float(payload.get("amount_usd") or 0.0),
            "reason": payload.get("reason"),
            "credit_payload_json": dict(payload.get("credit_payload_json") or payload.get("credit_payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(CreditNoteRow, record["credit_note_id"])
            if row is None:
                row = CreditNoteRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _credit_note_payload(row)

    def list_credit_notes(self, *, invoice_id: Optional[str] = None, account_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CreditNoteRow).order_by(desc(CreditNoteRow.created_at))
            if invoice_id is not None:
                stmt = stmt.where(CreditNoteRow.invoice_id == invoice_id)
            if account_id is not None:
                stmt = stmt.where(CreditNoteRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_credit_note_payload(row) for row in rows]

    def save_payment_retry_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "payment_retry_attempt_id": payload.get("payment_retry_attempt_id") or "payment_retry_%s" % uuid4().hex[:12],
            "invoice_id": payload.get("invoice_id"),
            "customer_account_id": payload.get("customer_account_id"),
            "account_id": payload["account_id"],
            "provider": payload["provider"],
            "status": payload.get("status", "planned"),
            "retry_reason": payload.get("retry_reason"),
            "attempt_count": int(payload.get("attempt_count") or 1),
            "next_retry_at": payload.get("next_retry_at"),
            "retry_payload_json": dict(payload.get("retry_payload_json") or payload.get("retry_payload") or {}),
            "created_at": payload.get("created_at") or now,
            "updated_at": payload.get("updated_at") or now,
        }
        with self.SessionLocal() as session:
            row = session.get(PaymentRetryAttemptRow, record["payment_retry_attempt_id"])
            if row is None:
                row = PaymentRetryAttemptRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _payment_retry_attempt_payload(row)

    def list_payment_retry_attempts(self, *, invoice_id: Optional[str] = None, account_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PaymentRetryAttemptRow).order_by(desc(PaymentRetryAttemptRow.updated_at))
            if invoice_id is not None:
                stmt = stmt.where(PaymentRetryAttemptRow.invoice_id == invoice_id)
            if account_id is not None:
                stmt = stmt.where(PaymentRetryAttemptRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_payment_retry_attempt_payload(row) for row in rows]

    def save_dunning_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "dunning_event_id": payload.get("dunning_event_id") or "dunning_%s" % uuid4().hex[:12],
            "invoice_id": payload.get("invoice_id"),
            "customer_account_id": payload.get("customer_account_id"),
            "account_id": payload["account_id"],
            "status": payload.get("status", "scheduled"),
            "step": payload["step"],
            "event_payload_json": dict(payload.get("event_payload_json") or payload.get("event_payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(DunningEventRow, record["dunning_event_id"])
            if row is None:
                row = DunningEventRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _dunning_event_payload(row)

    def list_dunning_events(self, *, invoice_id: Optional[str] = None, account_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(DunningEventRow).order_by(desc(DunningEventRow.created_at))
            if invoice_id is not None:
                stmt = stmt.where(DunningEventRow.invoice_id == invoice_id)
            if account_id is not None:
                stmt = stmt.where(DunningEventRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_dunning_event_payload(row) for row in rows]

    def save_renewal_tracker(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "renewal_tracker_id": payload.get("renewal_tracker_id") or "renewal_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "status": payload.get("status", "stable"),
            "renewal_due_at": payload.get("renewal_due_at"),
            "tracker_payload_json": dict(payload.get("tracker_payload_json") or payload.get("tracker_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(RenewalTrackerRow, record["renewal_tracker_id"])
            if row is None:
                row = RenewalTrackerRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _renewal_tracker_payload(row)

    def list_renewal_trackers(self, *, account_id: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(RenewalTrackerRow).order_by(desc(RenewalTrackerRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(RenewalTrackerRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(RenewalTrackerRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_renewal_tracker_payload(row) for row in rows]

    def save_dunning_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "dunning_run_id": payload.get("dunning_run_id") or "dunning_run_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "invoice_id": payload.get("invoice_id"),
            "status": payload.get("status", "open"),
            "current_step": payload.get("current_step", "initial_notice"),
            "dunning_payload_json": dict(payload.get("dunning_payload_json") or payload.get("dunning_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(DunningRunRow, record["dunning_run_id"])
            if row is None:
                row = DunningRunRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _dunning_run_payload(row)

    def list_dunning_runs(self, *, account_id: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(DunningRunRow).order_by(desc(DunningRunRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(DunningRunRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(DunningRunRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_dunning_run_payload(row) for row in rows]

    def save_pilot_conversion_track(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "pilot_conversion_track_id": payload.get("pilot_conversion_track_id") or "pilot_conversion_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "status": payload.get("status", "watch"),
            "track_payload_json": dict(payload.get("track_payload_json") or payload.get("track_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(PilotConversionTrackRow, record["pilot_conversion_track_id"])
            if row is None:
                row = PilotConversionTrackRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _pilot_conversion_track_payload(row)

    def list_pilot_conversion_tracks(self, *, account_id: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PilotConversionTrackRow).order_by(desc(PilotConversionTrackRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(PilotConversionTrackRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(PilotConversionTrackRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_pilot_conversion_track_payload(row) for row in rows]

    def save_expansion_candidate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "expansion_candidate_id": payload.get("expansion_candidate_id") or "expansion_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "status": payload.get("status", "watch"),
            "trigger_type": payload["trigger_type"],
            "candidate_payload_json": dict(payload.get("candidate_payload_json") or payload.get("candidate_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ExpansionCandidateRow, record["expansion_candidate_id"])
            if row is None:
                row = ExpansionCandidateRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _expansion_candidate_payload(row)

    def list_expansion_candidates(self, *, account_id: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ExpansionCandidateRow).order_by(desc(ExpansionCandidateRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(ExpansionCandidateRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(ExpansionCandidateRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_expansion_candidate_payload(row) for row in rows]

    def save_churn_risk_flag(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "churn_risk_flag_id": payload.get("churn_risk_flag_id") or "churn_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "status": payload.get("status", "watch"),
            "risk_level": payload.get("risk_level", "medium"),
            "flag_payload_json": dict(payload.get("flag_payload_json") or payload.get("flag_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ChurnRiskFlagRow, record["churn_risk_flag_id"])
            if row is None:
                row = ChurnRiskFlagRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _churn_risk_flag_payload(row)

    def list_churn_risk_flags(self, *, account_id: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ChurnRiskFlagRow).order_by(desc(ChurnRiskFlagRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(ChurnRiskFlagRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(ChurnRiskFlagRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_churn_risk_flag_payload(row) for row in rows]

    def save_production_signoff(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "signoff_id": payload.get("signoff_id") or "production_signoff_%s" % uuid4().hex[:12],
            "launch_label": payload["launch_label"],
            "status": payload.get("status", "draft"),
            "source_go_live_checklist_id": payload.get("source_go_live_checklist_id"),
            "source_manual_signoff_bundle_id": payload.get("source_manual_signoff_bundle_id"),
            "rollup_summary_json": dict(payload.get("rollup_summary_json") or payload.get("rollup_summary") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionSignoffRow, record["signoff_id"])
            if row is None:
                row = ProductionSignoffRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _production_signoff_payload(row)

    def get_production_signoff(self, signoff_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ProductionSignoffRow, signoff_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_production_signoff:%s" % signoff_id)
                return default
            return _production_signoff_payload(row)

    def list_production_signoffs(
        self,
        *,
        status: Optional[str] = None,
        launch_label: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionSignoffRow).order_by(desc(ProductionSignoffRow.updated_at))
            if status is not None:
                stmt = stmt.where(ProductionSignoffRow.status == status)
            if launch_label is not None:
                stmt = stmt.where(ProductionSignoffRow.launch_label == launch_label)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_signoff_payload(row) for row in rows]

    def save_production_signoff_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "signoff_item_id": payload.get("signoff_item_id") or "production_signoff_item_%s" % uuid4().hex[:12],
            "signoff_id": payload["signoff_id"],
            "item_code": payload["item_code"],
            "category": payload["category"],
            "label": payload["label"],
            "owner_role": payload["owner_role"],
            "owner_actor_id": payload.get("owner_actor_id"),
            "due_at": payload.get("due_at"),
            "status": payload.get("status", "pending"),
            "decision_note": payload.get("decision_note"),
            "approved_at": payload.get("approved_at"),
            "evidence_count": int(payload.get("evidence_count") or 0),
            "item_payload_json": dict(payload.get("item_payload_json") or payload.get("item_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionSignoffItemRow, record["signoff_item_id"])
            if row is None:
                row = ProductionSignoffItemRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _production_signoff_item_payload(row)

    def get_production_signoff_item(self, signoff_item_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ProductionSignoffItemRow, signoff_item_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_production_signoff_item:%s" % signoff_item_id)
                return default
            return _production_signoff_item_payload(row)

    def list_production_signoff_items(
        self,
        *,
        signoff_id: Optional[str] = None,
        status: Optional[str] = None,
        owner_role: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionSignoffItemRow).order_by(ProductionSignoffItemRow.due_at.asc(), ProductionSignoffItemRow.created_at.asc())
            if signoff_id is not None:
                stmt = stmt.where(ProductionSignoffItemRow.signoff_id == signoff_id)
            if status is not None:
                stmt = stmt.where(ProductionSignoffItemRow.status == status)
            if owner_role is not None:
                stmt = stmt.where(ProductionSignoffItemRow.owner_role == owner_role)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_signoff_item_payload(row) for row in rows]

    def save_production_signoff_evidence(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "evidence_id": payload.get("evidence_id") or "production_signoff_evidence_%s" % uuid4().hex[:12],
            "signoff_id": payload["signoff_id"],
            "signoff_item_id": payload["signoff_item_id"],
            "evidence_type": payload["evidence_type"],
            "source_ref_json": dict(payload.get("source_ref_json") or payload.get("source_ref") or {}),
            "summary": payload.get("summary"),
            "customer_safe": bool(payload.get("customer_safe", False)),
            "payload_json": dict(payload.get("payload_json") or payload.get("payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionSignoffEvidenceRow, record["evidence_id"])
            if row is None:
                row = ProductionSignoffEvidenceRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _production_signoff_evidence_payload(row)

    def list_production_signoff_evidence(
        self,
        *,
        signoff_id: Optional[str] = None,
        signoff_item_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionSignoffEvidenceRow).order_by(desc(ProductionSignoffEvidenceRow.created_at))
            if signoff_id is not None:
                stmt = stmt.where(ProductionSignoffEvidenceRow.signoff_id == signoff_id)
            if signoff_item_id is not None:
                stmt = stmt.where(ProductionSignoffEvidenceRow.signoff_item_id == signoff_item_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_signoff_evidence_payload(row) for row in rows]

    def save_production_cutover_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "cutover_window_id": payload.get("cutover_window_id") or "production_cutover_window_%s" % uuid4().hex[:12],
            "signoff_id": payload["signoff_id"],
            "launch_wave": payload["launch_wave"],
            "target_environment": payload["target_environment"],
            "starts_at": payload.get("starts_at"),
            "ends_at": payload.get("ends_at"),
            "rollback_owner_role": payload.get("rollback_owner_role"),
            "status": payload.get("status", "planned"),
            "cutover_payload_json": dict(payload.get("cutover_payload_json") or payload.get("cutover_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionCutoverWindowRow, record["cutover_window_id"])
            if row is None:
                row = ProductionCutoverWindowRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _production_cutover_window_payload(row)

    def list_production_cutover_windows(
        self,
        *,
        signoff_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionCutoverWindowRow).order_by(ProductionCutoverWindowRow.starts_at.asc(), ProductionCutoverWindowRow.created_at.asc())
            if signoff_id is not None:
                stmt = stmt.where(ProductionCutoverWindowRow.signoff_id == signoff_id)
            if status is not None:
                stmt = stmt.where(ProductionCutoverWindowRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_cutover_window_payload(row) for row in rows]

    def save_production_customer_acceptance_record(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "acceptance_record_id": payload.get("acceptance_record_id") or "production_acceptance_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "signoff_id": payload.get("signoff_id"),
            "launch_wave": payload["launch_wave"],
            "status": payload.get("status", "draft"),
            "readiness_summary_json": dict(payload.get("readiness_summary_json") or payload.get("readiness_summary") or {}),
            "acceptance_payload_json": dict(payload.get("acceptance_payload_json") or payload.get("acceptance_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionCustomerAcceptanceRecordRow, record["acceptance_record_id"])
            if row is None:
                row = ProductionCustomerAcceptanceRecordRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _production_customer_acceptance_record_payload(row)

    def get_production_customer_acceptance_record(self, acceptance_record_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ProductionCustomerAcceptanceRecordRow, acceptance_record_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_production_customer_acceptance_record:%s" % acceptance_record_id)
                return default
            return _production_customer_acceptance_record_payload(row)

    def list_production_customer_acceptance_records(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionCustomerAcceptanceRecordRow).order_by(desc(ProductionCustomerAcceptanceRecordRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(ProductionCustomerAcceptanceRecordRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(ProductionCustomerAcceptanceRecordRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(ProductionCustomerAcceptanceRecordRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_customer_acceptance_record_payload(row) for row in rows]

    def save_go_live_ready_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "go_live_ready_account_id": payload.get("go_live_ready_account_id") or "go_live_ready_%s" % uuid4().hex[:12],
            "customer_account_id": payload["customer_account_id"],
            "account_id": payload["account_id"],
            "acceptance_record_id": payload["acceptance_record_id"],
            "launch_wave": payload["launch_wave"],
            "status": payload.get("status", "candidate"),
            "readiness_payload_json": dict(payload.get("readiness_payload_json") or payload.get("readiness_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(GoLiveReadyAccountRow, record["go_live_ready_account_id"])
            if row is None:
                row = GoLiveReadyAccountRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _go_live_ready_account_payload(row)

    def list_go_live_ready_accounts(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(GoLiveReadyAccountRow).order_by(desc(GoLiveReadyAccountRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(GoLiveReadyAccountRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(GoLiveReadyAccountRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(GoLiveReadyAccountRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_go_live_ready_account_payload(row) for row in rows]

    def save_launch_wave_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "launch_wave_status_id": payload.get("launch_wave_status_id") or "launch_wave_%s" % uuid4().hex[:12],
            "launch_wave": payload["launch_wave"],
            "status": payload.get("status", "planned"),
            "target_environment": payload.get("target_environment", "production"),
            "wave_payload_json": dict(payload.get("wave_payload_json") or payload.get("wave_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(LaunchWaveStatusRow, record["launch_wave_status_id"])
            if row is None:
                row = LaunchWaveStatusRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _launch_wave_status_payload(row)

    def list_launch_wave_statuses(
        self,
        *,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(LaunchWaveStatusRow).order_by(desc(LaunchWaveStatusRow.updated_at))
            if launch_wave is not None:
                stmt = stmt.where(LaunchWaveStatusRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(LaunchWaveStatusRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_launch_wave_status_payload(row) for row in rows]

    def save_production_preflight_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "preflight_run_id": payload.get("preflight_run_id") or "production_preflight_run_%s" % uuid4().hex[:12],
            "signoff_id": payload.get("signoff_id"),
            "launch_wave": payload["launch_wave"],
            "target_environment": payload.get("target_environment", "production"),
            "status": payload.get("status", "running"),
            "go_no_go": payload.get("go_no_go", "manual_review"),
            "hard_fail_count": int(payload.get("hard_fail_count") or 0),
            "soft_fail_count": int(payload.get("soft_fail_count") or 0),
            "run_payload_json": dict(payload.get("run_payload_json") or payload.get("run_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionPreflightRunRow, record["preflight_run_id"])
            if row is None:
                row = ProductionPreflightRunRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _production_preflight_run_payload(row)

    def get_production_preflight_run(self, preflight_run_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(ProductionPreflightRunRow, preflight_run_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_production_preflight_run:%s" % preflight_run_id)
                return default
            return _production_preflight_run_payload(row)

    def list_production_preflight_runs(
        self,
        *,
        signoff_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionPreflightRunRow).order_by(desc(ProductionPreflightRunRow.updated_at))
            if signoff_id is not None:
                stmt = stmt.where(ProductionPreflightRunRow.signoff_id == signoff_id)
            if launch_wave is not None:
                stmt = stmt.where(ProductionPreflightRunRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(ProductionPreflightRunRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_preflight_run_payload(row) for row in rows]

    def save_production_preflight_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "preflight_check_id": payload.get("preflight_check_id") or "production_preflight_check_%s" % uuid4().hex[:12],
            "preflight_run_id": payload["preflight_run_id"],
            "check_key": payload["check_key"],
            "linked_signoff_item_code": payload.get("linked_signoff_item_code"),
            "owner_role": payload["owner_role"],
            "status": payload.get("status", "passed"),
            "summary": payload.get("summary"),
            "evidence_ref": payload.get("evidence_ref"),
            "payload_json": dict(payload.get("payload_json") or payload.get("payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionPreflightCheckRow, record["preflight_check_id"])
            if row is None:
                row = ProductionPreflightCheckRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _production_preflight_check_payload(row)

    def list_production_preflight_checks(
        self,
        *,
        preflight_run_id: Optional[str] = None,
        linked_signoff_item_code: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionPreflightCheckRow).order_by(ProductionPreflightCheckRow.created_at.asc())
            if preflight_run_id is not None:
                stmt = stmt.where(ProductionPreflightCheckRow.preflight_run_id == preflight_run_id)
            if linked_signoff_item_code is not None:
                stmt = stmt.where(ProductionPreflightCheckRow.linked_signoff_item_code == linked_signoff_item_code)
            if status is not None:
                stmt = stmt.where(ProductionPreflightCheckRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_preflight_check_payload(row) for row in rows]

    def save_first_7_day_outcome(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "first_7_day_outcome_id": payload.get("first_7_day_outcome_id") or "first_7_day_outcome_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "launch_wave": payload["launch_wave"],
            "launch_anchor_at": payload.get("launch_anchor_at"),
            "outcome_payload_json": dict(payload.get("outcome_payload_json") or payload.get("outcome_payload") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(First7DayOutcomeRow, record["first_7_day_outcome_id"])
            if row is None:
                row = First7DayOutcomeRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _first_7_day_outcome_payload(row)

    def list_first_7_day_outcomes(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(First7DayOutcomeRow).order_by(desc(First7DayOutcomeRow.generated_at))
            if account_id is not None:
                stmt = stmt.where(First7DayOutcomeRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(First7DayOutcomeRow.launch_wave == launch_wave)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_first_7_day_outcome_payload(row) for row in rows]

    def save_first_30_day_value_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "first_30_day_value_summary_id": payload.get("first_30_day_value_summary_id") or "first_30_day_value_summary_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "launch_wave": payload["launch_wave"],
            "launch_anchor_at": payload.get("launch_anchor_at"),
            "provisional": bool(payload.get("provisional", True)),
            "summary_payload_json": dict(payload.get("summary_payload_json") or payload.get("summary_payload") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(First30DayValueSummaryRow, record["first_30_day_value_summary_id"])
            if row is None:
                row = First30DayValueSummaryRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _first_30_day_value_summary_payload(row)

    def list_first_30_day_value_summaries(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(First30DayValueSummaryRow).order_by(desc(First30DayValueSummaryRow.generated_at))
            if account_id is not None:
                stmt = stmt.where(First30DayValueSummaryRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(First30DayValueSummaryRow.launch_wave == launch_wave)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_first_30_day_value_summary_payload(row) for row in rows]

    def save_pilot_to_paid_readiness_score(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "pilot_to_paid_readiness_score_id": payload.get("pilot_to_paid_readiness_score_id") or "pilot_to_paid_readiness_score_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "launch_wave": payload["launch_wave"],
            "launch_anchor_at": payload.get("launch_anchor_at"),
            "score": float(payload.get("score") or 0.0),
            "band": payload.get("band", "watch"),
            "score_payload_json": dict(payload.get("score_payload_json") or payload.get("score_payload") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(PilotToPaidReadinessScoreRow, record["pilot_to_paid_readiness_score_id"])
            if row is None:
                row = PilotToPaidReadinessScoreRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _pilot_to_paid_readiness_score_payload(row)

    def list_pilot_to_paid_readiness_scores(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(PilotToPaidReadinessScoreRow).order_by(desc(PilotToPaidReadinessScoreRow.generated_at))
            if account_id is not None:
                stmt = stmt.where(PilotToPaidReadinessScoreRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(PilotToPaidReadinessScoreRow.launch_wave == launch_wave)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_pilot_to_paid_readiness_score_payload(row) for row in rows]

    def save_customer_success_snapshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "customer_success_snapshot_id": payload.get("customer_success_snapshot_id") or "customer_success_snapshot_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "customer_account_id": payload.get("customer_account_id"),
            "launch_wave": payload["launch_wave"],
            "launch_anchor_at": payload.get("launch_anchor_at"),
            "snapshot_payload_json": dict(payload.get("snapshot_payload_json") or payload.get("snapshot_payload") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(CustomerSuccessSnapshotRow, record["customer_success_snapshot_id"])
            if row is None:
                row = CustomerSuccessSnapshotRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _customer_success_snapshot_payload(row)

    def list_customer_success_snapshots(
        self,
        *,
        account_id: Optional[str] = None,
        launch_wave: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(CustomerSuccessSnapshotRow).order_by(desc(CustomerSuccessSnapshotRow.generated_at))
            if account_id is not None:
                stmt = stmt.where(CustomerSuccessSnapshotRow.account_id == account_id)
            if launch_wave is not None:
                stmt = stmt.where(CustomerSuccessSnapshotRow.launch_wave == launch_wave)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_customer_success_snapshot_payload(row) for row in rows]

    def save_library_stats_cube(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "library_stats_cube_id": payload.get("library_stats_cube_id") or "library_stats_cube_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "semantic_version": str(payload.get("semantic_version") or "library_stats_semantic/v2"),
            "snapshot_payload_json": dict(payload.get("snapshot_payload_json") or payload.get("snapshot_payload") or {}),
            "source_breakdown_json": dict(payload.get("source_breakdown_json") or payload.get("source_breakdown") or {}),
            "source_updated_at": payload.get("source_updated_at") or now,
            "invalidated_at": payload.get("invalidated_at"),
            "last_invalidated_event_name": payload.get("last_invalidated_event_name"),
            "last_invalidated_event_at": payload.get("last_invalidated_event_at"),
            "created_at": payload.get("created_at") or now,
            "updated_at": now,
        }
        with self.SessionLocal() as session:
            stmt = select(LibraryStatsCubeRow).where(LibraryStatsCubeRow.account_id == record["account_id"])
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = LibraryStatsCubeRow(**record)
                session.add(row)
            else:
                row.semantic_version = record["semantic_version"]
                row.snapshot_payload_json = record["snapshot_payload_json"]
                row.source_breakdown_json = record["source_breakdown_json"]
                row.source_updated_at = record["source_updated_at"]
                row.invalidated_at = record["invalidated_at"]
                row.last_invalidated_event_name = record["last_invalidated_event_name"]
                row.last_invalidated_event_at = record["last_invalidated_event_at"]
                row.updated_at = record["updated_at"]
                record["library_stats_cube_id"] = row.library_stats_cube_id
            session.commit()
            session.refresh(row)
            return _library_stats_cube_payload(row)

    def invalidate_library_stats_cube(
        self,
        *,
        account_id: str,
        event_name: str,
        occurred_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "library_stats_cube_id": "library_stats_cube_%s" % uuid4().hex[:12],
            "account_id": account_id,
            "semantic_version": "library_stats_semantic/v2",
            "snapshot_payload_json": {},
            "source_breakdown_json": {},
            "source_updated_at": occurred_at or now,
            "invalidated_at": now,
            "last_invalidated_event_name": str(event_name or "").strip() or None,
            "last_invalidated_event_at": occurred_at or now,
            "created_at": now,
            "updated_at": now,
        }
        with self.SessionLocal() as session:
            stmt = select(LibraryStatsCubeRow).where(LibraryStatsCubeRow.account_id == account_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                row = LibraryStatsCubeRow(**record)
                session.add(row)
            else:
                row.invalidated_at = record["invalidated_at"]
                row.last_invalidated_event_name = record["last_invalidated_event_name"]
                row.last_invalidated_event_at = record["last_invalidated_event_at"]
                row.updated_at = record["updated_at"]
                record["library_stats_cube_id"] = row.library_stats_cube_id
            session.commit()
            session.refresh(row)
            return _library_stats_cube_payload(row)

    def get_library_stats_cube(self, account_id: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            stmt = select(LibraryStatsCubeRow).where(LibraryStatsCubeRow.account_id == account_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is not None:
                    return default
                raise KeyError("unknown_library_stats_cube:%s" % account_id)
            return _library_stats_cube_payload(row)

    def list_library_stats_cubes(
        self,
        *,
        account_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(LibraryStatsCubeRow).order_by(desc(LibraryStatsCubeRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(LibraryStatsCubeRow.account_id == account_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_library_stats_cube_payload(row) for row in rows]

    def save_production_launch_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "launch_event_id": payload.get("launch_event_id") or "production_launch_event_%s" % uuid4().hex[:12],
            "launch_wave": payload["launch_wave"],
            "account_id": payload.get("account_id"),
            "event_category": payload["event_category"],
            "event_type": payload["event_type"],
            "phase": payload["phase"],
            "severity": payload.get("severity", "info"),
            "related_object_type": payload.get("related_object_type"),
            "related_object_id": payload.get("related_object_id"),
            "occurred_at": payload.get("occurred_at") or now,
            "event_payload_json": dict(payload.get("event_payload_json") or payload.get("event_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionLaunchEventRow, record["launch_event_id"])
            if row is None:
                row = ProductionLaunchEventRow(created_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _production_launch_event_payload(row)

    def list_production_launch_events(
        self,
        *,
        launch_wave: Optional[str] = None,
        account_id: Optional[str] = None,
        phase: Optional[str] = None,
        severity: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionLaunchEventRow).order_by(ProductionLaunchEventRow.occurred_at.asc(), ProductionLaunchEventRow.created_at.asc())
            if launch_wave is not None:
                stmt = stmt.where(ProductionLaunchEventRow.launch_wave == launch_wave)
            if account_id is not None:
                stmt = stmt.where(ProductionLaunchEventRow.account_id == account_id)
            if phase is not None:
                stmt = stmt.where(ProductionLaunchEventRow.phase == phase)
            if severity is not None:
                stmt = stmt.where(ProductionLaunchEventRow.severity == severity)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_launch_event_payload(row) for row in rows]

    def save_production_postmortem_record(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "postmortem_record_id": payload.get("postmortem_record_id") or "production_postmortem_record_%s" % uuid4().hex[:12],
            "launch_wave": payload["launch_wave"],
            "account_id": payload.get("account_id"),
            "status": payload.get("status", "draft"),
            "summary_json": dict(payload.get("summary_json") or payload.get("summary") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(ProductionPostmortemRecordRow, record["postmortem_record_id"])
            if row is None:
                row = ProductionPostmortemRecordRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _production_postmortem_record_payload(row)

    def list_production_postmortem_records(
        self,
        *,
        launch_wave: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProductionPostmortemRecordRow).order_by(desc(ProductionPostmortemRecordRow.generated_at))
            if launch_wave is not None:
                stmt = stmt.where(ProductionPostmortemRecordRow.launch_wave == launch_wave)
            if account_id is not None:
                stmt = stmt.where(ProductionPostmortemRecordRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(ProductionPostmortemRecordRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_production_postmortem_record_payload(row) for row in rows]

    def save_go_live_day_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "go_live_day_run_id": payload.get("go_live_day_run_id") or "go_live_day_run_%s" % uuid4().hex[:12],
            "signoff_id": payload.get("signoff_id"),
            "launch_wave": payload["launch_wave"],
            "account_id": payload.get("account_id"),
            "status": payload.get("status", "running"),
            "activation_state_before": payload.get("activation_state_before"),
            "activation_state_after": payload.get("activation_state_after"),
            "report_payload_json": dict(payload.get("report_payload_json") or payload.get("report_payload") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(GoLiveDayRunRow, record["go_live_day_run_id"])
            if row is None:
                row = GoLiveDayRunRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _go_live_day_run_payload(row)

    def get_go_live_day_run(self, go_live_day_run_id: str, *, default: Optional[Dict[str, Any]] = ...) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            row = session.get(GoLiveDayRunRow, go_live_day_run_id)
            if row is None:
                if default is ...:
                    raise KeyError("unknown_go_live_day_run:%s" % go_live_day_run_id)
                return default
            return _go_live_day_run_payload(row)

    def list_go_live_day_runs(
        self,
        *,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(GoLiveDayRunRow).order_by(desc(GoLiveDayRunRow.updated_at))
            if launch_wave is not None:
                stmt = stmt.where(GoLiveDayRunRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(GoLiveDayRunRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_go_live_day_run_payload(row) for row in rows]

    def save_go_live_day_checkpoint(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "go_live_day_checkpoint_id": payload.get("go_live_day_checkpoint_id") or "go_live_day_checkpoint_%s" % uuid4().hex[:12],
            "go_live_day_run_id": payload["go_live_day_run_id"],
            "checkpoint_key": payload["checkpoint_key"],
            "status": payload.get("status", "passed"),
            "summary": payload.get("summary"),
            "evidence_ref": payload.get("evidence_ref"),
            "rollback_recommendation": payload.get("rollback_recommendation"),
            "checkpoint_payload_json": dict(payload.get("checkpoint_payload_json") or payload.get("checkpoint_payload") or {}),
            "created_at": payload.get("created_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(GoLiveDayCheckpointRow, record["go_live_day_checkpoint_id"])
            if row is None:
                row = GoLiveDayCheckpointRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _go_live_day_checkpoint_payload(row)

    def list_go_live_day_checkpoints(
        self,
        *,
        go_live_day_run_id: Optional[str] = None,
        checkpoint_key: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(GoLiveDayCheckpointRow).order_by(GoLiveDayCheckpointRow.created_at.asc())
            if go_live_day_run_id is not None:
                stmt = stmt.where(GoLiveDayCheckpointRow.go_live_day_run_id == go_live_day_run_id)
            if checkpoint_key is not None:
                stmt = stmt.where(GoLiveDayCheckpointRow.checkpoint_key == checkpoint_key)
            if status is not None:
                stmt = stmt.where(GoLiveDayCheckpointRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_go_live_day_checkpoint_payload(row) for row in rows]

    def save_launch_week_guard_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "launch_week_guard_run_id": payload.get("launch_week_guard_run_id") or "launch_week_guard_run_%s" % uuid4().hex[:12],
            "launch_wave": payload["launch_wave"],
            "account_id": payload.get("account_id"),
            "status": payload.get("status", "not_ready"),
            "replication_readiness": payload.get("replication_readiness", "not_ready"),
            "summary_json": dict(payload.get("summary_json") or payload.get("summary") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(LaunchWeekGuardRunRow, record["launch_week_guard_run_id"])
            if row is None:
                row = LaunchWeekGuardRunRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _launch_week_guard_run_payload(row)

    def list_launch_week_guard_runs(
        self,
        *,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(LaunchWeekGuardRunRow).order_by(desc(LaunchWeekGuardRunRow.generated_at))
            if launch_wave is not None:
                stmt = stmt.where(LaunchWeekGuardRunRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(LaunchWeekGuardRunRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_launch_week_guard_run_payload(row) for row in rows]

    def save_first_customer_success_pack(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "first_customer_success_pack_id": payload.get("first_customer_success_pack_id") or "first_customer_success_pack_%s" % uuid4().hex[:12],
            "launch_wave": payload["launch_wave"],
            "account_id": payload.get("account_id"),
            "status": payload.get("status", "not_ready"),
            "pack_payload_json": dict(payload.get("pack_payload_json") or payload.get("pack_payload") or {}),
            "generated_at": payload.get("generated_at") or utcnow_iso(),
        }
        with self.SessionLocal() as session:
            row = session.get(FirstCustomerSuccessPackRow, record["first_customer_success_pack_id"])
            if row is None:
                row = FirstCustomerSuccessPackRow(**record)
                session.add(row)
            else:
                for key, value in record.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _first_customer_success_pack_payload(row)

    def list_first_customer_success_packs(
        self,
        *,
        launch_wave: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(FirstCustomerSuccessPackRow).order_by(desc(FirstCustomerSuccessPackRow.generated_at))
            if launch_wave is not None:
                stmt = stmt.where(FirstCustomerSuccessPackRow.launch_wave == launch_wave)
            if status is not None:
                stmt = stmt.where(FirstCustomerSuccessPackRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_first_customer_success_pack_payload(row) for row in rows]

    def save_provider_subscription(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "provider_subscription_id": subscription.get("provider_subscription_id") or "psub_%s" % uuid4().hex[:12],
            "account_id": subscription["account_id"],
            "tier_id": subscription["tier_id"],
            "provider": subscription["provider"],
            "provider_ref": subscription.get("provider_ref"),
            "provider_customer_id": subscription.get("provider_customer_id"),
            "provider_checkout_session_id": subscription.get("provider_checkout_session_id"),
            "provider_order_id": subscription.get("provider_order_id"),
            "environment": subscription.get("environment", "test"),
            "verification_status": subscription.get("verification_status", "pending"),
            "last_verified_at": subscription.get("last_verified_at"),
            "status": subscription.get("status", "trialing"),
            "period_start": subscription.get("period_start"),
            "period_end": subscription.get("period_end"),
            "cancel_at_period_end": "true" if subscription.get("cancel_at_period_end") else "false",
            "latest_event_id": subscription.get("latest_event_id"),
            "payload_json": dict(subscription.get("payload_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(ProviderSubscriptionRow, payload["provider_subscription_id"])
            if row is None:
                row = ProviderSubscriptionRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.tier_id = payload["tier_id"]
                row.provider = payload["provider"]
                row.provider_ref = payload["provider_ref"]
                row.provider_customer_id = payload["provider_customer_id"]
                row.provider_checkout_session_id = payload["provider_checkout_session_id"]
                row.provider_order_id = payload["provider_order_id"]
                row.environment = payload["environment"]
                row.verification_status = payload["verification_status"]
                row.last_verified_at = payload["last_verified_at"]
                row.status = payload["status"]
                row.period_start = payload["period_start"]
                row.period_end = payload["period_end"]
                row.cancel_at_period_end = payload["cancel_at_period_end"]
                row.latest_event_id = payload["latest_event_id"]
                row.payload_json = payload["payload_json"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "cancel_at_period_end": payload["cancel_at_period_end"] == "true",
            "created_at": now,
            "updated_at": now,
        }

    def list_provider_subscriptions(
        self,
        *,
        account_id: Optional[str] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProviderSubscriptionRow).order_by(desc(ProviderSubscriptionRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(ProviderSubscriptionRow.account_id == account_id)
            if provider is not None:
                stmt = stmt.where(ProviderSubscriptionRow.provider == provider)
            if status is not None:
                stmt = stmt.where(ProviderSubscriptionRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "provider_subscription_id": row.provider_subscription_id,
                    "account_id": row.account_id,
                    "tier_id": row.tier_id,
                    "provider": row.provider,
                    "provider_ref": row.provider_ref,
                    "provider_customer_id": row.provider_customer_id,
                    "provider_checkout_session_id": row.provider_checkout_session_id,
                    "provider_order_id": row.provider_order_id,
                    "environment": row.environment,
                    "verification_status": row.verification_status,
                    "last_verified_at": row.last_verified_at,
                    "status": row.status,
                    "period_start": row.period_start,
                    "period_end": row.period_end,
                    "cancel_at_period_end": row.cancel_at_period_end == "true",
                    "latest_event_id": row.latest_event_id,
                    "payload_json": dict(row.payload_json or {}),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def get_provider_subscription_by_ref(
        self,
        *,
        provider: str,
        provider_ref: Optional[str] = None,
        provider_checkout_session_id: Optional[str] = None,
        provider_order_id: Optional[str] = None,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ProviderSubscriptionRow).where(ProviderSubscriptionRow.provider == provider)
            if provider_ref:
                stmt = stmt.where(ProviderSubscriptionRow.provider_ref == provider_ref)
            elif provider_checkout_session_id:
                stmt = stmt.where(ProviderSubscriptionRow.provider_checkout_session_id == provider_checkout_session_id)
            elif provider_order_id:
                stmt = stmt.where(ProviderSubscriptionRow.provider_order_id == provider_order_id)
            else:
                if default is ...:
                    raise KeyError("provider_subscription_lookup_key_required")
                return default
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_provider_subscription")
                return default
            return {
                "provider_subscription_id": row.provider_subscription_id,
                "account_id": row.account_id,
                "tier_id": row.tier_id,
                "provider": row.provider,
                "provider_ref": row.provider_ref,
                "provider_customer_id": row.provider_customer_id,
                "provider_checkout_session_id": row.provider_checkout_session_id,
                "provider_order_id": row.provider_order_id,
                "environment": row.environment,
                "verification_status": row.verification_status,
                "last_verified_at": row.last_verified_at,
                "status": row.status,
                "period_start": row.period_start,
                "period_end": row.period_end,
                "cancel_at_period_end": row.cancel_at_period_end == "true",
                "latest_event_id": row.latest_event_id,
                "payload_json": dict(row.payload_json or {}),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_billing_checkout_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "checkout_session_id": payload.get("checkout_session_id") or "bcheckout_%s" % uuid4().hex[:12],
            "account_id": payload["account_id"],
            "checkout_kind": payload.get("checkout_kind", "subscription"),
            "tier_id": payload["tier_id"],
            "package_id": payload.get("package_id"),
            "provider": payload["provider"],
            "provider_ref": payload.get("provider_ref"),
            "subscription_id": payload.get("subscription_id"),
            "status": payload.get("status", "created"),
            "checkout_url": payload.get("checkout_url"),
            "idempotency_key": payload["idempotency_key"],
            "expires_at": payload.get("expires_at"),
            "fulfilled_at": payload.get("fulfilled_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingCheckoutSessionRow, record["checkout_session_id"])
            if row is None:
                row = BillingCheckoutSessionRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.account_id = record["account_id"]
                row.checkout_kind = record["checkout_kind"]
                row.tier_id = record["tier_id"]
                row.package_id = record["package_id"]
                row.provider = record["provider"]
                row.provider_ref = record["provider_ref"]
                row.subscription_id = record["subscription_id"]
                row.status = record["status"]
                row.checkout_url = record["checkout_url"]
                row.idempotency_key = record["idempotency_key"]
                row.expires_at = record["expires_at"]
                row.fulfilled_at = record["fulfilled_at"]
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def get_billing_checkout_session(self, checkout_session_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(BillingCheckoutSessionRow, checkout_session_id)
            if row is None:
                raise KeyError("unknown_billing_checkout_session:%s" % checkout_session_id)
            return {
                "checkout_session_id": row.checkout_session_id,
                "account_id": row.account_id,
                "checkout_kind": row.checkout_kind,
                "tier_id": row.tier_id,
                "package_id": row.package_id,
                "provider": row.provider,
                "provider_ref": row.provider_ref,
                "subscription_id": row.subscription_id,
                "status": row.status,
                "checkout_url": row.checkout_url,
                "idempotency_key": row.idempotency_key,
                "expires_at": row.expires_at,
                "fulfilled_at": row.fulfilled_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def list_billing_checkout_sessions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingCheckoutSessionRow).order_by(desc(BillingCheckoutSessionRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.status == status)
            if provider is not None:
                stmt = stmt.where(BillingCheckoutSessionRow.provider == provider)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "checkout_session_id": row.checkout_session_id,
                    "account_id": row.account_id,
                    "checkout_kind": row.checkout_kind,
                    "tier_id": row.tier_id,
                    "package_id": row.package_id,
                    "provider": row.provider,
                    "provider_ref": row.provider_ref,
                    "subscription_id": row.subscription_id,
                    "status": row.status,
                    "checkout_url": row.checkout_url,
                    "idempotency_key": row.idempotency_key,
                    "expires_at": row.expires_at,
                    "fulfilled_at": row.fulfilled_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def latest_billing_checkout_session(self, *, account_id: str) -> Optional[Dict[str, Any]]:
        sessions = self.list_billing_checkout_sessions(account_id=account_id, limit=1)
        return sessions[0] if sessions else None

    def save_billing_lifecycle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_billing_lifecycle_event_by_provider_ref(
            provider=payload["provider"],
            provider_event_id=payload["provider_event_id"],
            default=None,
        )
        if existing is not None:
            payload = {
                **existing,
                **payload,
                "event_id": existing["event_id"],
            }
        now = utcnow_iso()
        record = {
            "event_id": payload.get("event_id") or "bevent_%s" % uuid4().hex[:12],
            "event_type": payload["event_type"],
            "provider": payload["provider"],
            "provider_event_id": payload["provider_event_id"],
            "account_id": payload.get("account_id"),
            "subscription_id": payload.get("subscription_id"),
            "checkout_session_id": payload.get("checkout_session_id"),
            "status": payload.get("status", "received"),
            "payload_json": dict(payload.get("payload_json") or {}),
            "processing_result": dict(payload.get("processing_result") or {}) if payload.get("processing_result") is not None else None,
            "occurred_at": payload.get("occurred_at") or now,
            "processed_at": payload.get("processed_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingLifecycleEventRow, record["event_id"])
            if row is None:
                row = BillingLifecycleEventRow(**record)
                session.add(row)
            else:
                row.event_type = record["event_type"]
                row.provider = record["provider"]
                row.provider_event_id = record["provider_event_id"]
                row.account_id = record["account_id"]
                row.subscription_id = record["subscription_id"]
                row.checkout_session_id = record["checkout_session_id"]
                row.status = record["status"]
                row.payload_json = record["payload_json"]
                row.processing_result = record["processing_result"]
                row.occurred_at = record["occurred_at"]
                row.processed_at = record["processed_at"]
            session.commit()
        return record

    def get_billing_lifecycle_event_by_provider_ref(
        self,
        *,
        provider: str,
        provider_event_id: str,
        default: Optional[Dict[str, Any]] = ...,
    ) -> Optional[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingLifecycleEventRow).where(
                BillingLifecycleEventRow.provider == provider,
                BillingLifecycleEventRow.provider_event_id == provider_event_id,
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                if default is ...:
                    raise KeyError("unknown_billing_lifecycle_event:%s:%s" % (provider, provider_event_id))
                return default
            return {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "provider": row.provider,
                "provider_event_id": row.provider_event_id,
                "account_id": row.account_id,
                "subscription_id": row.subscription_id,
                "checkout_session_id": row.checkout_session_id,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                "occurred_at": row.occurred_at,
                "processed_at": row.processed_at,
            }

    def list_billing_lifecycle_events(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        checkout_session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingLifecycleEventRow).order_by(desc(BillingLifecycleEventRow.occurred_at))
            if account_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.account_id == account_id)
            if subscription_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.subscription_id == subscription_id)
            if checkout_session_id is not None:
                stmt = stmt.where(BillingLifecycleEventRow.checkout_session_id == checkout_session_id)
            if event_type is not None:
                stmt = stmt.where(BillingLifecycleEventRow.event_type == event_type)
            if status is not None:
                stmt = stmt.where(BillingLifecycleEventRow.status == status)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "provider": row.provider,
                    "provider_event_id": row.provider_event_id,
                    "account_id": row.account_id,
                    "subscription_id": row.subscription_id,
                    "checkout_session_id": row.checkout_session_id,
                    "status": row.status,
                    "payload_json": dict(row.payload_json or {}),
                    "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                    "occurred_at": row.occurred_at,
                    "processed_at": row.processed_at,
                }
                for row in rows
            ]

    def get_billing_lifecycle_event(self, event_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(BillingLifecycleEventRow, event_id)
            if row is None:
                raise KeyError("unknown_billing_lifecycle_event:%s" % event_id)
            return {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "provider": row.provider,
                "provider_event_id": row.provider_event_id,
                "account_id": row.account_id,
                "subscription_id": row.subscription_id,
                "checkout_session_id": row.checkout_session_id,
                "status": row.status,
                "payload_json": dict(row.payload_json or {}),
                "processing_result": dict(row.processing_result or {}) if row.processing_result is not None else None,
                "occurred_at": row.occurred_at,
                "processed_at": row.processed_at,
            }

    def save_billing_retry_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        record = {
            "retry_attempt_id": payload.get("retry_attempt_id") or "bretry_%s" % uuid4().hex[:12],
            "account_id": payload.get("account_id"),
            "subscription_id": payload.get("subscription_id"),
            "checkout_session_id": payload.get("checkout_session_id"),
            "source_event_id": payload.get("source_event_id"),
            "status": payload.get("status", "planned"),
            "retry_reason": payload.get("retry_reason"),
            "attempt_count": int(payload.get("attempt_count") or 1),
            "next_retry_at": payload.get("next_retry_at"),
            "payload_json": dict(payload.get("payload_json") or {}),
        }
        with self.SessionLocal() as session:
            row = session.get(BillingRetryAttemptRow, record["retry_attempt_id"])
            if row is None:
                row = BillingRetryAttemptRow(created_at=now, updated_at=now, **record)
                session.add(row)
            else:
                row.account_id = record["account_id"]
                row.subscription_id = record["subscription_id"]
                row.checkout_session_id = record["checkout_session_id"]
                row.source_event_id = record["source_event_id"]
                row.status = record["status"]
                row.retry_reason = record["retry_reason"]
                row.attempt_count = record["attempt_count"]
                row.next_retry_at = record["next_retry_at"]
                row.payload_json = record["payload_json"]
                row.updated_at = now
            session.commit()
        return {
            **record,
            "created_at": now,
            "updated_at": now,
        }

    def list_billing_retry_attempts(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(BillingRetryAttemptRow).order_by(desc(BillingRetryAttemptRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.account_id == account_id)
            if subscription_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.subscription_id == subscription_id)
            if source_event_id is not None:
                stmt = stmt.where(BillingRetryAttemptRow.source_event_id == source_event_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "retry_attempt_id": row.retry_attempt_id,
                    "account_id": row.account_id,
                    "subscription_id": row.subscription_id,
                    "checkout_session_id": row.checkout_session_id,
                    "source_event_id": row.source_event_id,
                    "status": row.status,
                    "retry_reason": row.retry_reason,
                    "attempt_count": row.attempt_count,
                    "next_retry_at": row.next_retry_at,
                    "payload_json": dict(row.payload_json or {}),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def latest_billing_retry_attempt(
        self,
        *,
        account_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        attempts = self.list_billing_retry_attempts(
            account_id=account_id,
            subscription_id=subscription_id,
            limit=1,
        )
        return attempts[0] if attempts else None

    def list_review_records(
        self,
        *,
        status: Optional[str] = None,
        asset_type: Optional[str] = None,
        asset_id: Optional[str] = None,
        asset_ids: Optional[List[str]] = None,
        reviewer_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(ReviewRecordRow).order_by(desc(ReviewRecordRow.updated_at))
            if status is not None:
                stmt = stmt.where(ReviewRecordRow.status == status)
            if asset_type is not None:
                stmt = stmt.where(ReviewRecordRow.asset_type == asset_type)
            if asset_id is not None:
                stmt = stmt.where(ReviewRecordRow.asset_id == asset_id)
            if asset_ids:
                stmt = stmt.where(ReviewRecordRow.asset_id.in_(asset_ids))
            if reviewer_id is not None:
                stmt = stmt.where(ReviewRecordRow.reviewer_id == reviewer_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "review_id": row.review_id,
                    "asset_type": row.asset_type,
                    "asset_id": row.asset_id,
                    "status": row.status,
                    "reviewer_id": row.reviewer_id,
                    "risk_rating": row.risk_rating,
                    "notes": row.notes,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def publish_world_version(self, world_version_id: str, *, reviewer_id: Optional[str] = None) -> Dict[str, Any]:
        world_version = self.get_world_version(world_version_id)
        world_version.status = "published"
        self.save_world_version(world_version, publish=True)
        return {"world_version_id": world_version_id, "status": "published", "reviewer_id": reviewer_id}

    def rollback_world(self, world_id: str, target_world_version_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            world_row = session.get(WorldRow, world_id)
            if world_row is None:
                raise KeyError("unknown_world:%s" % world_id)
            previous_version = world_row.latest_version
            world_row.latest_version = target_world_version_id
            world_row.updated_at = utcnow_iso()
            target_row = session.get(WorldVersionRow, target_world_version_id)
            if target_row is None:
                raise KeyError("unknown_world_version:%s" % target_world_version_id)
            target_row.status = "published"
            target_row.updated_at = utcnow_iso()
            session.commit()
        return {
            "world_id": world_id,
            "latest_version": target_world_version_id,
            "previous_version": previous_version,
            "status": "rolled_back",
        }

    # Entitlements / billing / meters / analytics
    def list_entitlements(
        self,
        reader_id: Optional[str] = None,
        *,
        account_id: Optional[str] = None,
        world_id: Optional[str] = None,
        wallet_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(EntitlementRow).order_by(desc(EntitlementRow.created_at))
            if account_id is not None:
                stmt = stmt.where(EntitlementRow.account_id == account_id)
            elif reader_id is not None:
                stmt = stmt.where(EntitlementRow.reader_id == reader_id)
            else:
                raise ValueError("reader_id_or_account_id_required")
            if world_id is not None:
                stmt = stmt.where((EntitlementRow.world_id == world_id) | (EntitlementRow.world_id.is_(None)))
            if wallet_type is not None:
                stmt = stmt.where(EntitlementRow.wallet_type == wallet_type)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "entitlement_id": row.entitlement_id,
                    "account_id": row.account_id,
                    "reader_id": row.reader_id,
                    "world_id": row.world_id,
                    "entitlement_type": row.entitlement_type,
                    "wallet_type": row.wallet_type,
                    "tier_id": row.tier_id,
                    "status": row.status,
                    "balance": row.balance,
                    "expires_at": row.expires_at,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def save_entitlement(self, entitlement: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "entitlement_id": entitlement.get("entitlement_id") or "entitlement_%s" % uuid4().hex[:12],
            "account_id": entitlement.get("account_id") or entitlement.get("reader_id"),
            "reader_id": entitlement.get("reader_id") or entitlement.get("account_id"),
            "world_id": entitlement.get("world_id"),
            "entitlement_type": entitlement["entitlement_type"],
            "wallet_type": entitlement.get("wallet_type"),
            "tier_id": entitlement.get("tier_id"),
            "status": entitlement.get("status", "active"),
            "balance": entitlement.get("balance"),
            "expires_at": entitlement.get("expires_at"),
        }
        with self.SessionLocal() as session:
            row = session.get(EntitlementRow, payload["entitlement_id"])
            if row is None:
                session.add(EntitlementRow(created_at=utcnow_iso(), **payload))
            else:
                row.account_id = payload["account_id"]
                row.reader_id = payload["reader_id"]
                row.world_id = payload["world_id"]
                row.entitlement_type = payload["entitlement_type"]
                row.wallet_type = payload["wallet_type"]
                row.tier_id = payload["tier_id"]
                row.status = payload["status"]
                row.balance = payload["balance"]
                row.expires_at = payload["expires_at"]
            session.commit()
        return payload

    def get_entitlement(self, entitlement_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(EntitlementRow, entitlement_id)
            if row is None:
                raise KeyError("unknown_entitlement:%s" % entitlement_id)
            return {
                "entitlement_id": row.entitlement_id,
                "account_id": row.account_id,
                "reader_id": row.reader_id,
                "world_id": row.world_id,
                "entitlement_type": row.entitlement_type,
                "wallet_type": row.wallet_type,
                "tier_id": row.tier_id,
                "status": row.status,
                "balance": row.balance,
                "expires_at": row.expires_at,
                "created_at": row.created_at,
            }

    def list_subscriptions(
        self,
        *,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(SubscriptionRow).order_by(desc(SubscriptionRow.updated_at))
            if account_id is not None:
                stmt = stmt.where(SubscriptionRow.account_id == account_id)
            if status is not None:
                stmt = stmt.where(SubscriptionRow.status == status)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "subscription_id": row.subscription_id,
                    "account_id": row.account_id,
                    "tier_id": row.tier_id,
                    "provider": row.provider,
                    "provider_ref": row.provider_ref,
                    "status": row.status,
                    "period_start": row.period_start,
                    "period_end": row.period_end,
                    "cancel_at_period_end": row.cancel_at_period_end == "true",
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def save_subscription(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow_iso()
        payload = {
            "subscription_id": subscription.get("subscription_id") or "subscription_%s" % uuid4().hex[:12],
            "account_id": subscription["account_id"],
            "tier_id": subscription["tier_id"],
            "provider": subscription.get("provider", "web_stub"),
            "provider_ref": subscription.get("provider_ref"),
            "status": subscription.get("status", "trialing"),
            "period_start": subscription.get("period_start"),
            "period_end": subscription.get("period_end"),
            "cancel_at_period_end": "true" if subscription.get("cancel_at_period_end") else "false",
        }
        with self.SessionLocal() as session:
            row = session.get(SubscriptionRow, payload["subscription_id"])
            if row is None:
                row = SubscriptionRow(created_at=now, updated_at=now, **payload)
                session.add(row)
            else:
                row.account_id = payload["account_id"]
                row.tier_id = payload["tier_id"]
                row.provider = payload["provider"]
                row.provider_ref = payload["provider_ref"]
                row.status = payload["status"]
                row.period_start = payload["period_start"]
                row.period_end = payload["period_end"]
                row.cancel_at_period_end = payload["cancel_at_period_end"]
                row.updated_at = now
            session.commit()
        return {
            **payload,
            "cancel_at_period_end": payload["cancel_at_period_end"] == "true",
            "created_at": now,
            "updated_at": now,
        }

    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = session.get(SubscriptionRow, subscription_id)
            if row is None:
                raise KeyError("unknown_subscription:%s" % subscription_id)
            return {
                "subscription_id": row.subscription_id,
                "account_id": row.account_id,
                "tier_id": row.tier_id,
                "provider": row.provider,
                "provider_ref": row.provider_ref,
                "status": row.status,
                "period_start": row.period_start,
                "period_end": row.period_end,
                "cancel_at_period_end": row.cancel_at_period_end == "true",
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def get_active_subscription_for_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        subscriptions = self.list_subscriptions(account_id=account_id)
        return next(
            (
                item
                for item in subscriptions
                if item["status"] in {"trialing", "active"}
            ),
            None,
        )

    def create_usage_meter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "meter_id": payload.get("meter_id") or "meter_%s" % uuid4().hex[:12],
            "account_id": payload.get("account_id"),
            "reader_id": payload.get("reader_id"),
            "session_id": payload.get("session_id"),
            "chapter_id": payload.get("chapter_id"),
            "world_version_id": payload.get("world_version_id"),
            "action_type": payload["action_type"],
            "usage_units": float(payload.get("usage_units", 0.0)),
            "estimated_cost": float(payload.get("estimated_cost", 0.0)),
            "wallet_type": payload.get("wallet_type"),
            "subscription_tier": payload.get("subscription_tier"),
            "provider": payload.get("provider"),
            "model_policy_version": payload.get("model_policy_version"),
        }
        with self.SessionLocal() as session:
            session.add(UsageMeterRow(created_at=utcnow_iso(), **record))
            session.commit()
        return record

    def list_usage_meters(
        self,
        *,
        reader_id: Optional[str] = None,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(UsageMeterRow).order_by(desc(UsageMeterRow.created_at))
            if account_id is not None:
                stmt = stmt.where(UsageMeterRow.account_id == account_id)
            if reader_id is not None:
                stmt = stmt.where(UsageMeterRow.reader_id == reader_id)
            if session_id is not None:
                stmt = stmt.where(UsageMeterRow.session_id == session_id)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "meter_id": row.meter_id,
                    "account_id": row.account_id,
                    "reader_id": row.reader_id,
                    "session_id": row.session_id,
                    "chapter_id": row.chapter_id,
                    "world_version_id": row.world_version_id,
                    "action_type": row.action_type,
                    "usage_units": row.usage_units,
                    "estimated_cost": row.estimated_cost,
                    "wallet_type": row.wallet_type,
                    "subscription_tier": row.subscription_tier,
                    "provider": row.provider,
                    "model_policy_version": row.model_policy_version,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def aggregate_eval_metrics(
        self,
        *,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_version_ids: Optional[List[str]] = None
        if world_version_id is not None:
            selected_version_ids = [world_version_id]
        elif world_id is not None:
            selected_version_ids = [item["world_version_id"] for item in self.list_world_versions(world_id=world_id)]

        report_payloads: List[Dict[str, Any]] = []
        if selected_version_ids is None:
            report_payloads = self.list_evaluation_reports()
        else:
            for version_id in selected_version_ids:
                report_payloads.extend(self.list_evaluation_reports(world_version_id=version_id))
        reports = [EvaluationReport.from_dict(item) for item in report_payloads]
        if not reports:
            return {
                "pass_rate": 0.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "top_issue_categories": [],
                "per_world_pack_quality_trend": [],
                "online_continuation_correlation": 0.0,
                "continuation_signal_summary": {
                    "sample_count": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "censored_count": 0,
                    "continuation_rate": 0.0,
                    "stale_window_hours": CONTINUATION_STALE_WINDOW_HOURS,
                },
                "quality_signal_correlations": [],
                "q03_q09_calibration": {
                    "coverage_status": "insufficient_coverage",
                    "sample_count": 0,
                    "sample_gap": CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                    "q03": {
                        "current_thresholds": dict(LONGFORM_Q03_SIGNAL_THRESHOLDS),
                        "primary_metric": None,
                        "primary_correlation": None,
                        "recommendation": "insufficient_coverage",
                    },
                    "q09": {
                        "current_thresholds": {
                            "pacing_threshold": float(LONGFORM_SOFT_ISSUE_THRESHOLDS["q09_pacing_threshold"]),
                            "hook_threshold": float(LONGFORM_SOFT_ISSUE_THRESHOLDS["q09_hook_threshold"]),
                        },
                        "primary_metric": None,
                        "primary_correlation": None,
                        "recommendation": "insufficient_coverage",
                    },
                },
                "continuation_world_details": [],
                "continuation_version_details": [],
                "continuation_sample_accumulation": {
                    "target_sample_count_per_world": CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                    "target_sample_count_per_version": CONTINUATION_TARGET_SAMPLES_PER_VERSION,
                    "target_negative_samples": CONTINUATION_TARGET_NEGATIVE_SAMPLES,
                    "worlds_below_target_count": 0,
                    "versions_below_target_count": 0,
                    "prioritized_worlds": [],
                    "prioritized_versions": [],
                },
            }
        from ..eval.reporting import aggregate_reports

        aggregate = aggregate_reports(reports)
        with self.SessionLocal() as session:
            stmt = select(AnalyticsEventRow).where(AnalyticsEventRow.event_name.in_(["continue_story", "chapter_rendered"]))
            if selected_version_ids is not None:
                stmt = stmt.where(AnalyticsEventRow.world_version_id.in_(selected_version_ids))
            analytics_rows = session.execute(stmt).scalars()
            continue_events = [row for row in analytics_rows if row.event_name == "continue_story"]
            chapter_stmt = (
                select(ChapterRow, SessionRow)
                .join(SessionRow, ChapterRow.session_id == SessionRow.session_id)
                .order_by(ChapterRow.session_id.asc(), ChapterRow.chapter_index.asc())
            )
            if selected_version_ids is not None:
                chapter_stmt = chapter_stmt.where(ChapterRow.world_version_id.in_(selected_version_ids))
            chapter_rows = session.execute(chapter_stmt).all()
        average_score = sum(report.scores.overall_score for report in reports) / float(max(1, len(reports)))
        aggregate["per_world_pack_quality_trend"] = [
            {
                "world_version_id": world_version_id or (world_id or "all"),
                "avg_score": round(average_score, 3),
            }
        ]
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=CONTINUATION_STALE_WINDOW_HOURS)
        grouped_chapters: Dict[str, List[Dict[str, Any]]] = {}
        world_id_cache: Dict[str, str] = {}
        for chapter_row, session_row in chapter_rows:
            payload = dict(chapter_row.review_flags_json or {})
            report_payload = payload.get("evaluation_report")
            if not report_payload:
                continue
            report = EvaluationReport.from_dict(report_payload)
            version_id = chapter_row.world_version_id
            if version_id not in world_id_cache:
                world_id_cache[version_id] = self.get_world_version(version_id).world_id
            grouped_chapters.setdefault(chapter_row.session_id, []).append(
                {
                    "chapter_id": report.chapter_id,
                    "chapter_index": int(chapter_row.chapter_index),
                    "session_id": chapter_row.session_id,
                    "world_version_id": version_id,
                    "world_id": world_id_cache[version_id],
                    "report": report,
                    "session_updated_at": session_row.updated_at,
                    "session_status": session_row.status,
                }
            )

        continuation_samples: List[Dict[str, Any]] = []
        censored_count = 0
        censored_world_counts: Dict[str, int] = {}
        censored_version_counts: Dict[str, int] = {}
        for session_id, items in grouped_chapters.items():
            ordered = sorted(items, key=lambda item: int(item["chapter_index"]))
            for index, item in enumerate(ordered):
                continued_label: Optional[int]
                signal_source: str
                if index < len(ordered) - 1:
                    continued_label = 1
                    signal_source = "observed_next_chapter"
                else:
                    session_updated_at = _parse_timestamp(item.get("session_updated_at"))
                    session_status = str(item.get("session_status") or "active")
                    if session_status != "active" or session_updated_at <= stale_cutoff:
                        continued_label = 0
                        signal_source = "stale_session_tail"
                    else:
                        censored_count += 1
                        censored_world_counts[item["world_id"]] = censored_world_counts.get(item["world_id"], 0) + 1
                        censored_version_counts[item["world_version_id"]] = censored_version_counts.get(item["world_version_id"], 0) + 1
                        continue
                report = item["report"]
                issue_codes = {issue.issue_code for issue in report.issues}
                continuation_samples.append(
                    {
                        "session_id": session_id,
                        "chapter_id": item["chapter_id"],
                        "chapter_index": int(item["chapter_index"]),
                        "world_version_id": item["world_version_id"],
                        "world_id": item["world_id"],
                        "continued": continued_label,
                        "signal_source": signal_source,
                        "overall_score": float(report.scores.overall_score),
                        "readability": float(report.scores.readability),
                        "scene_density": float(report.scores.scene_density),
                        "character_fidelity": float(report.scores.character_fidelity),
                        "causal_continuity": float(report.scores.causal_continuity),
                        "pacing": float(report.scores.pacing),
                        "choice_distinctness": float(report.scores.choice_distinctness),
                        "hook_quality": float(report.scores.hook_quality),
                        "monetize_ready": float(report.scores.monetize_ready),
                        "issue_count": float(len(report.issues)),
                        "q03_present": 1.0 if "Q03" in issue_codes else 0.0,
                        "q04_present": 1.0 if "Q04" in issue_codes else 0.0,
                        "q05_present": 1.0 if "Q05" in issue_codes else 0.0,
                        "q09_present": 1.0 if "Q09" in issue_codes else 0.0,
                        "lexical_repetition_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("lexical_repetition_score", 0.0) or 0.0
                        ),
                        "semantic_paragraph_similarity_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("semantic_paragraph_similarity_score", 0.0) or 0.0
                        ),
                        "paragraph_similarity_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("paragraph_similarity_score", 0.0) or 0.0
                        ),
                        "n_gram_repetition_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("n_gram_repetition_score", 0.0) or 0.0
                        ),
                        "beat_structure_repetition_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("beat_structure_repetition_score", 0.0) or 0.0
                        ),
                        "event_coverage_gap_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("event_coverage_gap_score", 0.0) or 0.0
                        ),
                        "beat_coverage_gap_score": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("beat_coverage_gap_score", 0.0) or 0.0
                        ),
                        "uncovered_event_count": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("uncovered_event_count", 0.0) or 0.0
                        ),
                        "uncovered_beat_count": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("uncovered_beat_count", 0.0) or 0.0
                        ),
                        "overcovered_beat_count": float(
                            dict(report.hard_validator_results.get("lint_metrics") or {}).get("overcovered_beat_count", 0.0) or 0.0
                        ),
                    }
                )

        metric_names = [
            "overall_score",
            "readability",
            "scene_density",
            "character_fidelity",
            "causal_continuity",
            "pacing",
            "choice_distinctness",
            "hook_quality",
            "monetize_ready",
            "issue_count",
            "q03_present",
            "q04_present",
            "q05_present",
            "q09_present",
            "lexical_repetition_score",
            "semantic_paragraph_similarity_score",
            "paragraph_similarity_score",
            "n_gram_repetition_score",
            "beat_structure_repetition_score",
            "event_coverage_gap_score",
            "beat_coverage_gap_score",
            "uncovered_event_count",
            "uncovered_beat_count",
            "overcovered_beat_count",
        ]
        def _build_correlation_entries(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            correlations: List[Dict[str, Any]] = []
            for metric_name in metric_names:
                points = [
                    (float(item[metric_name]), float(item["continued"]))
                    for item in samples
                ]
                metric_values = [float(item[metric_name]) for item in samples]
                correlations.append(
                    {
                        "metric": metric_name,
                        "correlation": _pearson_correlation(points),
                        "sample_count": len(points),
                        "mean_metric": round(sum(metric_values) / float(max(1, len(metric_values))), 3) if metric_values else 0.0,
                        "positive_direction": metric_name not in {
                            "issue_count",
                            "q03_present",
                            "q04_present",
                            "q05_present",
                            "q09_present",
                            "lexical_repetition_score",
                            "semantic_paragraph_similarity_score",
                            "paragraph_similarity_score",
                            "n_gram_repetition_score",
                            "beat_structure_repetition_score",
                            "event_coverage_gap_score",
                            "beat_coverage_gap_score",
                            "uncovered_event_count",
                            "uncovered_beat_count",
                            "overcovered_beat_count",
                        },
                    }
                )
            correlations.sort(key=lambda item: (-abs(float(item["correlation"])), item["metric"]))
            return correlations

        def _build_signal_summary(
            samples: List[Dict[str, Any]],
            *,
            censored: int,
            target_sample_count: Optional[int] = None,
        ) -> Dict[str, Any]:
            positive = sum(1 for item in samples if int(item["continued"]) == 1)
            negative = sum(1 for item in samples if int(item["continued"]) == 0)
            sample_count = len(samples)
            continuation_rate = round(
                positive / float(max(1, sample_count)),
                3,
            )
            summary = {
                "sample_count": sample_count,
                "positive_count": positive,
                "negative_count": negative,
                "censored_count": censored,
                "continuation_rate": continuation_rate,
                "stale_window_hours": CONTINUATION_STALE_WINDOW_HOURS,
            }
            if target_sample_count is not None:
                summary["target_sample_count"] = target_sample_count
                summary["sample_gap"] = max(0, int(target_sample_count) - int(sample_count))
                summary["recommended_action"] = _continuation_recommended_action(
                    sample_count=sample_count,
                    positive_count=positive,
                    negative_count=negative,
                    target_sample_count=int(target_sample_count),
                )
            return summary

        correlations = _build_correlation_entries(continuation_samples)
        overall_correlation = next((item["correlation"] for item in correlations if item["metric"] == "overall_score"), 0.0)
        aggregate["online_continuation_correlation"] = overall_correlation
        aggregate_target_sample_count = (
            CONTINUATION_TARGET_SAMPLES_PER_VERSION
            if selected_version_ids is not None and len(selected_version_ids) == 1
            else CONTINUATION_TARGET_SAMPLES_PER_WORLD
        )
        aggregate["continuation_signal_summary"] = {
            **_build_signal_summary(
                continuation_samples,
                censored=censored_count,
                target_sample_count=aggregate_target_sample_count,
            ),
            "observed_continue_events": len(continue_events),
        }
        aggregate["quality_signal_correlations"] = correlations
        aggregate["q03_q09_calibration"] = _build_q03_q09_calibration_summary(
            correlations,
            aggregate["continuation_signal_summary"],
        )
        world_samples: Dict[str, List[Dict[str, Any]]] = {}
        version_samples: Dict[str, List[Dict[str, Any]]] = {}
        for item in continuation_samples:
            world_samples.setdefault(item["world_id"], []).append(item)
            version_samples.setdefault(item["world_version_id"], []).append(item)

        world_details: List[Dict[str, Any]] = []
        for current_world_id, samples in world_samples.items():
            world_correlations = _build_correlation_entries(samples)
            world_details.append(
                {
                    "world_id": current_world_id,
                    "world_version_ids": sorted({item["world_version_id"] for item in samples}),
                    "online_continuation_correlation": next(
                        (item["correlation"] for item in world_correlations if item["metric"] == "overall_score"),
                        0.0,
                    ),
                    "top_correlations": world_correlations[:3],
                    "quality_signal_correlations": world_correlations,
                    "q03_q09_calibration": _build_q03_q09_calibration_summary(
                        world_correlations,
                        _build_signal_summary(
                            samples,
                            censored=censored_world_counts.get(current_world_id, 0),
                            target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                        ),
                    ),
                    **_build_signal_summary(
                        samples,
                        censored=censored_world_counts.get(current_world_id, 0),
                        target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_WORLD,
                    ),
                }
            )
        world_details.sort(
            key=lambda item: (
                item.get("recommended_action") == "coverage_sufficient",
                int(item.get("sample_gap", 0)),
                str(item.get("world_id")),
            )
        )

        version_details: List[Dict[str, Any]] = []
        for current_world_version_id, samples in version_samples.items():
            version_correlations = _build_correlation_entries(samples)
            version_details.append(
                {
                    "world_version_id": current_world_version_id,
                    "world_id": samples[0]["world_id"] if samples else "",
                    "online_continuation_correlation": next(
                        (item["correlation"] for item in version_correlations if item["metric"] == "overall_score"),
                        0.0,
                    ),
                    "top_correlations": version_correlations[:3],
                    "quality_signal_correlations": version_correlations,
                    "q03_q09_calibration": _build_q03_q09_calibration_summary(
                        version_correlations,
                        _build_signal_summary(
                            samples,
                            censored=censored_version_counts.get(current_world_version_id, 0),
                            target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_VERSION,
                        ),
                    ),
                    **_build_signal_summary(
                        samples,
                        censored=censored_version_counts.get(current_world_version_id, 0),
                        target_sample_count=CONTINUATION_TARGET_SAMPLES_PER_VERSION,
                    ),
                }
            )
        version_details.sort(
            key=lambda item: (
                item.get("recommended_action") == "coverage_sufficient",
                int(item.get("sample_gap", 0)),
                str(item.get("world_version_id")),
            )
        )

        aggregate["continuation_world_details"] = world_details
        aggregate["continuation_version_details"] = version_details
        aggregate["continuation_sample_accumulation"] = {
            "target_sample_count_per_world": CONTINUATION_TARGET_SAMPLES_PER_WORLD,
            "target_sample_count_per_version": CONTINUATION_TARGET_SAMPLES_PER_VERSION,
            "target_negative_samples": CONTINUATION_TARGET_NEGATIVE_SAMPLES,
            "worlds_below_target_count": sum(1 for item in world_details if int(item.get("sample_gap", 0)) > 0),
            "versions_below_target_count": sum(1 for item in version_details if int(item.get("sample_gap", 0)) > 0),
            "prioritized_worlds": [item for item in world_details if item.get("recommended_action") != "coverage_sufficient"][:5],
            "prioritized_versions": [item for item in version_details if item.get("recommended_action") != "coverage_sufficient"][:8],
        }
        return aggregate

    def record_analytics_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.SessionLocal() as session:
            row = AnalyticsEventRow(
                event_name=payload["event_name"],
                reader_id=payload.get("reader_id"),
                session_id=payload.get("session_id"),
                world_version_id=payload.get("world_version_id"),
                payload_json=dict(payload.get("payload_json", {})),
                occurred_at=payload.get("occurred_at", utcnow_iso()),
            )
            session.add(row)
            session.commit()
            return {
                "event_id": row.event_id,
                "event_name": row.event_name,
                "reader_id": row.reader_id,
                "session_id": row.session_id,
                "world_version_id": row.world_version_id,
                "payload_json": dict(row.payload_json or {}),
                "occurred_at": row.occurred_at,
            }

    def list_analytics_events(
        self,
        *,
        event_names: Optional[List[str]] = None,
        reader_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        world_version_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            stmt = select(AnalyticsEventRow).order_by(desc(AnalyticsEventRow.occurred_at))
            if event_names:
                stmt = stmt.where(AnalyticsEventRow.event_name.in_(event_names))
            if reader_id is not None:
                stmt = stmt.where(AnalyticsEventRow.reader_id == reader_id)
            if session_id is not None:
                stmt = stmt.where(AnalyticsEventRow.session_id == session_id)
            if world_version_id is not None:
                stmt = stmt.where(AnalyticsEventRow.world_version_id == world_version_id)
            if world_version_ids:
                stmt = stmt.where(AnalyticsEventRow.world_version_id.in_(world_version_ids))
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars()
            return [
                {
                    "event_id": row.event_id,
                    "event_name": row.event_name,
                    "reader_id": row.reader_id,
                    "session_id": row.session_id,
                    "world_version_id": row.world_version_id,
                    "payload_json": dict(row.payload_json or {}),
                    "occurred_at": row.occurred_at,
                }
                for row in rows
            ]
