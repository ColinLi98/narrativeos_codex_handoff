// Ops refresh orchestration extracted from app.js.

var OpsRefreshRuntime = (() => {
  const dom = OpsDOM;
  const { api } = UIShared;
  const { latestAsyncJob } = OpsAccessors;

function resolveActiveReaderId() {
  if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.activeReaderId === "function") {
    return ReaderRuntime.activeReaderId();
  }
  return readerState.readerId || "";
}

function currentOpsNavigationContext() {
  return {
    account_id: (dom.opsNavAccountId?.value || "").trim() || "",
    world_id: (dom.opsNavWorldId?.value || "").trim() || "",
    case_id: (dom.opsNavCaseId?.value || "").trim() || "",
    alert_id: (dom.opsNavAlertId?.value || "").trim() || "",
  };
}

function dedupeOpsReviewItems(items) {
  const seen = new Set();
  return (items || []).filter((item) => {
    const reviewItemId = String(item?.review_item_id || "").trim();
    if (!reviewItemId || seen.has(reviewItemId)) {
      return false;
    }
    seen.add(reviewItemId);
    return true;
  });
}

function normalizeLegacyReviewQueueItems(reviews) {
  return (reviews || []).map((review) => {
    const worldVersionId = String(review?.asset_id || review?.world_version_id || "").trim();
    if (!worldVersionId) {
      return null;
    }
    return {
      review_item_id: `ops_review::world_version_review::${worldVersionId}`,
      source_type: "world_version_review",
      source_id: worldVersionId,
      queue: "content_release",
      status: review?.status || "new",
      severity: "medium",
      headline: `${worldVersionId} · 发布审阅`,
      summary: review?.notes || review?.status || "",
      recommended_action: "review_candidate",
      account_id: null,
      world_id: null,
      world_version_id: worldVersionId,
      linked_entities: [],
      allowed_actions: ["assign_to_me", "mark_in_review", "approve", "needs_changes", "block"],
      due_at: review?.updated_at || null,
      sla_bucket: "backlog",
      owner_id: null,
      reviewer_id: review?.reviewer_id || null,
    };
  }).filter(Boolean);
}

function normalizeOpsReviewHubPayload(reviewHubPayload, queuePayload) {
  const reviewHub = reviewHubPayload || {};
  const directItems = Array.isArray(reviewHub.items) ? reviewHub.items : [];
  const triageItems = Object.values(reviewHub.triage?.by_queue || {}).flat();
  const legacyItems = normalizeLegacyReviewQueueItems(queuePayload?.reviews || []);
  const normalizedItems = dedupeOpsReviewItems(
    directItems.length ? directItems : [...triageItems, ...legacyItems]
  );
  return {
    ...reviewHub,
    items: normalizedItems,
  };
}

function buildCrossPackQualityUrl(options = {}) {
  const strategyBundleId = String(
    options.strategyBundleId !== undefined
      ? options.strategyBundleId
      : (dom.opsCrossPackStrategyBundleId?.value || "")
  ).trim();
  const weakestLimit = String(
    options.weakestLimit !== undefined
      ? options.weakestLimit
      : (dom.opsCrossPackWeakestLimit?.value || "")
  ).trim();
  const shouldValidate =
    options.validateStrategyBundle !== undefined
      ? Boolean(options.validateStrategyBundle)
      : Boolean(dom.opsCrossPackValidateStrategyBundle?.checked);
  const params = new URLSearchParams();
  if (shouldValidate) {
    params.set("validate_strategy_bundle", "true");
  }
  if (strategyBundleId) params.set("strategy_bundle_id", strategyBundleId);
  if (weakestLimit) params.set("weakest_limit", weakestLimit);
  return `/v1/ops/cross-pack-quality${params.toString() ? `?${params.toString()}` : ""}`;
}

async function refreshOpsCrossPackQuality(options = {}) {
  const token = options.token;
  const payload = await api(buildCrossPackQualityUrl(options));
  if (!isActiveOpsRefresh(token)) {
    return payload;
  }
  opsState.opsCrossPackQuality = payload;
  return payload;
}

const OPS_REFRESH_SCOPE_ALL = [
  "review_release",
  "runtime",
  "jobs",
  "account",
  "alerts",
  "learned",
  "navigation",
  "investigation",
];

function normalizeOpsRefreshScopes(scopes) {
  if (!Array.isArray(scopes) || !scopes.length) {
    return [...OPS_REFRESH_SCOPE_ALL];
  }
  if (scopes.includes("all")) {
    return [...OPS_REFRESH_SCOPE_ALL];
  }
  return [...new Set(scopes)];
}

function isActiveOpsRefresh(token) {
  return token === undefined || token === null || token === opsState.opsRefreshRequestId;
}

function syncOpsNavigationContext(prefill = {}, options = {}) {
  const preserveExisting = Boolean(options.preserveExisting);
  if ([prefill.account_id, prefill.world_id, prefill.case_id, prefill.alert_id].some(Boolean)) {
    opsState.opsNavigationPinned = true;
  }
  const merged = {
    account_id: prefill.account_id ?? currentOpsNavigationContext().account_id,
    world_id: prefill.world_id ?? currentOpsNavigationContext().world_id,
    case_id: prefill.case_id ?? currentOpsNavigationContext().case_id,
    alert_id: prefill.alert_id ?? currentOpsNavigationContext().alert_id,
    world_version_id: prefill.world_version_id,
  };
  if (dom.opsNavAccountId && (!preserveExisting || !dom.opsNavAccountId.value.trim() || prefill.account_id !== undefined)) {
    dom.opsNavAccountId.value = merged.account_id || "";
  }
  if (dom.opsNavWorldId && (!preserveExisting || !dom.opsNavWorldId.value.trim() || prefill.world_id !== undefined)) {
    dom.opsNavWorldId.value = merged.world_id || "";
  }
  if (dom.opsNavCaseId && (!preserveExisting || !dom.opsNavCaseId.value.trim() || prefill.case_id !== undefined)) {
    dom.opsNavCaseId.value = merged.case_id || "";
  }
  if (dom.opsNavAlertId && (!preserveExisting || !dom.opsNavAlertId.value.trim() || prefill.alert_id !== undefined)) {
    dom.opsNavAlertId.value = merged.alert_id || "";
  }
  if (dom.opsAccountId && (merged.account_id || prefill.account_id !== undefined)) {
    dom.opsAccountId.value = merged.account_id || "";
  }
  if (
    dom.opsAlertAccountId &&
    (merged.account_id || prefill.account_id !== undefined) &&
    (!preserveExisting || !dom.opsAlertAccountId.value.trim() || prefill.account_id !== undefined)
  ) {
    dom.opsAlertAccountId.value = merged.account_id || "";
  }
  if (
    dom.opsInvestigationAccountId &&
    (merged.account_id || prefill.account_id !== undefined) &&
    (!preserveExisting || !dom.opsInvestigationAccountId.value.trim() || prefill.account_id !== undefined)
  ) {
    dom.opsInvestigationAccountId.value = merged.account_id || "";
  }
  if (merged.world_id || prefill.world_id !== undefined) {
    opsState.selectedOpsWorldId = merged.world_id || null;
    if (dom.opsReleaseWorldId && (!preserveExisting || !dom.opsReleaseWorldId.value.trim() || prefill.world_id !== undefined)) {
      dom.opsReleaseWorldId.value = merged.world_id || "";
    }
  }
  if (dom.opsGovernanceCaseId && (merged.case_id || prefill.case_id !== undefined)) {
    dom.opsGovernanceCaseId.value = merged.case_id || "";
  }
  if (dom.opsInvestigationCaseId && (merged.case_id || prefill.case_id !== undefined)) {
    dom.opsInvestigationCaseId.value = merged.case_id || "";
  }
  if (dom.opsInvestigationWorldVersionId && (merged.world_version_id || prefill.world_version_id !== undefined)) {
    dom.opsInvestigationWorldVersionId.value = merged.world_version_id || "";
  }
  if (merged.alert_id || prefill.alert_id !== undefined) {
    opsState.selectedOpsAlertId = merged.alert_id || null;
  }
}

async function refreshOpsNavigationModel(options = {}) {
  const token = options.token;
  const context = currentOpsNavigationContext();
  const params = new URLSearchParams();
  if (context.account_id) params.set("account_id", context.account_id);
  if (context.world_id) params.set("world_id", context.world_id);
  if (context.case_id) params.set("case_id", context.case_id);
  if (context.alert_id) params.set("alert_id", context.alert_id);
  if (![context.account_id, context.world_id, context.case_id, context.alert_id].some(Boolean)) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsNavigationModel = null;
    }
    return;
  }
  const payload = await api(`/v1/ops/navigation-model?${params.toString()}`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsNavigationModel = payload;
  syncOpsNavigationContext(opsState.opsNavigationModel.active_context || {}, { preserveExisting: false });
}

async function refreshOpsSubscriptionAudit(options = {}) {
  const token = options.token;
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  if (!accountId) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsSubscriptionAudit = null;
      opsState.opsAccountWorkspace = null;
      opsState.opsGovernanceSnapshot = null;
      opsState.opsGovernanceExport = null;
      opsState.opsGovernanceDetail = null;
    }
    return;
  }
  const [subscriptionPayload, entitlementPayload, eventPayload, governanceSnapshot, governanceExport] = await Promise.all([
    api(`/v1/ops/subscriptions?account_id=${encodeURIComponent(accountId)}`),
    api(`/v1/ops/entitlements?account_id=${encodeURIComponent(accountId)}`),
    api(`/v1/ops/monetization-events?account_id=${encodeURIComponent(accountId)}`),
    api(`/v1/ops/accounts/${encodeURIComponent(accountId)}/governance`),
    api(`/v1/ops/export/governance-audit?account_id=${encodeURIComponent(accountId)}`),
  ]);
  const accountDetail = await api(`/v1/ops/accounts/${encodeURIComponent(accountId)}`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsSubscriptionAudit = {
    account_id: accountId,
    subscriptions: subscriptionPayload.subscriptions || [],
    entitlements: entitlementPayload.entitlements || [],
    wallets: entitlementPayload.wallets || {},
    recent_checkout_sessions: accountDetail.recent_checkout_sessions || [],
    checkout_session: accountDetail.checkout_session || null,
    lifecycle_history_summary: accountDetail.lifecycle_history_summary || {},
    tiers: entitlementPayload.tiers || [],
    entitlement_matrix: entitlementPayload.entitlement_matrix || {},
    config_version: entitlementPayload.config_version || "-",
    audit_summary: entitlementPayload.audit_summary || {},
    audit_timeline: entitlementPayload.audit_timeline || [],
    audit_trail: entitlementPayload.audit_trail || [],
    audit_breakdown: entitlementPayload.audit_breakdown || {},
    timeline_cursor: entitlementPayload.timeline_cursor || {},
    revoke_candidates: entitlementPayload.revoke_candidates || [],
    events: eventPayload.events || [],
  };
  opsState.opsAccountDetail = accountDetail;
  opsState.opsGovernanceSnapshot = governanceSnapshot;
  opsState.opsGovernanceExport = governanceExport;
  if (
    opsState.opsGovernanceDetail &&
    !(governanceSnapshot.governance_cases || []).some((item) => item.case_id === opsState.opsGovernanceDetail.case_id)
  ) {
    opsState.opsGovernanceDetail = null;
  }
}
async function refreshOpsAccountWorkspace(options = {}) {
  const token = options.token;
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  if (!accountId) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsAccountWorkspace = null;
    }
    return;
  }
  const payload = await api(`/v1/ops/accounts/${encodeURIComponent(accountId)}/workspace?limit=12`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsAccountWorkspace = payload;
}
async function refreshOpsReleaseWorkspace(options = {}) {
  const token = options.token;
  const worldId =
    (dom.opsReleaseWorldId?.value || "").trim() ||
    opsState.selectedOpsWorldId ||
    opsState.opsWorldStatuses?.[0]?.world_id ||
    "";
  if (!worldId) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsReleaseWorkspace = null;
    }
    return;
  }
  opsState.selectedOpsWorldId = worldId;
  if (dom.opsReleaseWorldId) {
    dom.opsReleaseWorldId.value = worldId;
  }
  const payload = await api(`/v1/ops/worlds/${encodeURIComponent(worldId)}/release-workspace?limit=12`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsReleaseWorkspace = payload;
}
function shouldRefreshOpsNavigationModel() {
  return opsState.opsNavigationPinned || Object.values(currentOpsNavigationContext()).some(Boolean);
}
function shouldRefreshOpsInvestigation() {
  if (opsState.opsInvestigationPinned) {
    return true;
  }
  const worldVersionId = (dom.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (dom.opsInvestigationCaseId?.value || "").trim();
  return Boolean(worldVersionId || caseId);
}
function currentOpsAlertFilters() {
  return {
    accountId: (dom.opsAlertAccountId?.value || "").trim() || "",
    statusFilter: dom.opsAlertStatusFilter?.value || "actionable",
    severity: dom.opsAlertSeverityFilter?.value || "",
  };
}
async function refreshOpsAlerts(options = {}) {
  const token = options.token;
  const filters = currentOpsAlertFilters();
  const params = new URLSearchParams();
  if (filters.accountId) params.set("account_id", filters.accountId);
  if (filters.statusFilter) params.set("status_filter", filters.statusFilter);
  if (filters.severity) params.set("severity", filters.severity);
  params.set("limit", String(options.limit || 25));
  const feed = await api(`/v1/ops/alerts?${params.toString()}`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsAlertsFeed = feed;
  const alerts = feed?.alerts || [];
  if (!alerts.length) {
    opsState.selectedOpsAlertId = null;
    opsState.opsAlertDetail = null;
    return;
  }
  const selectedId = opsState.selectedOpsAlertId && alerts.find((item) => item.alert_id === opsState.selectedOpsAlertId)
    ? opsState.selectedOpsAlertId
    : alerts[0].alert_id;
  opsState.selectedOpsAlertId = selectedId;
  const detail = await api(
    `/v1/ops/alerts/${encodeURIComponent(selectedId)}${
      filters.accountId ? `?account_id=${encodeURIComponent(filters.accountId)}` : ""
    }`
  );
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsAlertDetail = detail;
}

async function loadOpsReviewReleaseScope(token) {
  const [reviewHubPayload, queuePayload, worldPayload] = await Promise.all([
    api("/v1/ops/review-hub?limit=80"),
    api("/v1/ops/review-queue"),
    api("/v1/library/worlds"),
  ]);
  const worlds = (worldPayload.worlds || []).slice(0, 5);
  const [statuses, histories] = await Promise.all([
    Promise.all(worlds.map((world) => api(`/v1/ops/worlds/${world.world_id}/status`))),
    Promise.all(worlds.map((world) => api(`/v1/ops/worlds/${world.world_id}/history`))),
  ]);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsReviewHub = normalizeOpsReviewHubPayload(reviewHubPayload, queuePayload);
  opsState.opsReviewQueue = queuePayload.reviews || [];
  opsState.opsWorldStatuses = statuses;
  opsState.opsWorldHistories = histories;
  const reviewItems = opsState.opsReviewHub.items || [];
  if (reviewItems.length) {
    const selectedId = reviewItems.some((item) => item.review_item_id === opsState.opsSelectedReviewItemId)
      ? opsState.opsSelectedReviewItemId
      : reviewItems[0].review_item_id;
    opsState.opsSelectedReviewItemId = selectedId;
    try {
      opsState.opsSelectedReviewItemDetail = await api(`/v1/ops/review-items/${encodeURIComponent(selectedId)}`);
      try {
        opsState.opsSelectedReviewWorkDetail = await api(`/v1/ops/review-items/${encodeURIComponent(selectedId)}/work`);
      } catch (_error) {
        opsState.opsSelectedReviewWorkDetail = null;
      }
      const reviewItem = opsState.opsSelectedReviewItemDetail?.review_item || null;
      const traceId =
        reviewItem?.source_payload?.trace_summary?.trace_id ||
        (reviewItem?.linked_entities || []).find((entity) => entity.kind === "trace")?.id ||
        null;
      if (traceId) {
        opsState.opsSelectedQualityTraceId = traceId;
        try {
          opsState.opsQualityTraceDetail = await api(`/v1/ops/quality/traces/${encodeURIComponent(traceId)}`);
        } catch (_error) {
          opsState.opsQualityTraceDetail = null;
        }
      } else {
        opsState.opsSelectedQualityTraceId = null;
        opsState.opsQualityTraceDetail = null;
      }
    } catch (_error) {
      opsState.opsSelectedReviewItemDetail = null;
      opsState.opsSelectedReviewWorkDetail = null;
      opsState.opsSelectedQualityTraceId = null;
      opsState.opsQualityTraceDetail = null;
    }
  } else {
    opsState.opsSelectedReviewItemId = null;
    opsState.opsSelectedReviewItemDetail = null;
    opsState.opsSelectedReviewWorkDetail = null;
    opsState.opsSelectedQualityTraceId = null;
    opsState.opsQualityTraceDetail = null;
  }
  if (!opsState.selectedOpsWorldId && statuses.length) {
    opsState.selectedOpsWorldId = statuses[0].world_id;
  }
  if (shellState.opsWorkspace === "release") {
    await refreshOpsReleaseWorkspace({ token });
  } else if (isActiveOpsRefresh(token)) {
    opsState.opsReleaseWorkspace = null;
  }
}
async function loadOpsRuntimeScope(activeOpsAccountId, token) {
  if (!activeOpsAccountId && !shellState.debug) {
    if (!isActiveOpsRefresh(token)) {
      return;
    }
    opsState.opsMeters = [];
    opsState.opsSchemaLifecycle = null;
    opsState.opsDataIntegrity = null;
    opsState.opsDeploymentHealthGate = null;
    opsState.opsPreflightVerification = null;
    opsState.opsDeploymentRunbook = null;
    opsState.opsIncidentPlaybook = null;
    opsState.opsRuntimeIncidentSnapshot = null;
    opsState.opsRuntimeReceipts = [];
    opsState.opsQualitySummary = null;
    opsState.opsQualityEvents = [];
    opsState.opsQualityTraceDetail = null;
    opsState.opsProviderRouting = null;
    opsState.opsProviderRollout = null;
    opsState.opsProviderRuntimeMetrics = null;
    opsState.opsStoryBootstrapWorldSummary = [];
    opsState.opsStoryBootstrapWorldDetail = null;
    opsState.opsCommercializationSummary = null;
    opsState.opsProductionSignoffDetail = null;
    return;
  }
  const [
    meterPayload,
    schemaLifecycle,
    dataIntegrity,
    deploymentHealthGate,
    preflightVerification,
    deploymentRunbook,
    incidentPlaybook,
    runtimeIncidentSnapshot,
    receiptsPayload,
    qualitySummary,
    qualityEvents,
    qualityTraceDetail,
    providerRouting,
    providerRollout,
    providerRuntimeMetrics,
    storyBootstrapWorldSummary,
    commercializationSummary,
  ] = await Promise.all([
    api("/v1/ops/meters"),
    api("/v1/ops/schema-lifecycle"),
    api("/v1/ops/data-integrity?limit=12"),
    api(`/v1/ops/deployment-health-gate?account_id=${encodeURIComponent(activeOpsAccountId)}`),
    api(`/v1/ops/preflight-verification-bundle?account_id=${encodeURIComponent(activeOpsAccountId)}`),
    api("/v1/ops/deployment-runbook"),
    api(`/v1/ops/incident-playbook?account_id=${encodeURIComponent(activeOpsAccountId)}`),
    api(`/v1/ops/runtime-incident-snapshot?account_id=${encodeURIComponent(activeOpsAccountId)}`),
    api(`/v1/ops/runtime-receipts?account_id=${encodeURIComponent(activeOpsAccountId)}&limit=20`),
    api(`/v1/ops/quality/summary?account_id=${encodeURIComponent(activeOpsAccountId)}&limit=20`),
    api(`/v1/ops/quality/events?account_id=${encodeURIComponent(activeOpsAccountId)}&limit=20`),
    opsState.opsSelectedQualityTraceId
      ? api(`/v1/ops/quality/traces/${encodeURIComponent(opsState.opsSelectedQualityTraceId)}`)
      : Promise.resolve(null),
    api("/v1/ops/provider-routing"),
    api("/v1/ops/provider-rollout"),
    api(`/v1/ops/provider-runtime-metrics?account_id=${encodeURIComponent(activeOpsAccountId)}&limit=24`),
    api("/v1/ops/story-bootstrap-world-summary?limit=12"),
    api("/v1/ops/commercialization-summary?limit=25"),
  ]);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsMeters = meterPayload.meters || [];
  opsState.opsSchemaLifecycle = schemaLifecycle;
  opsState.opsDataIntegrity = dataIntegrity;
  opsState.opsDeploymentHealthGate = deploymentHealthGate;
  opsState.opsPreflightVerification = preflightVerification;
  opsState.opsDeploymentRunbook = deploymentRunbook;
  opsState.opsIncidentPlaybook = incidentPlaybook;
  opsState.opsRuntimeIncidentSnapshot = runtimeIncidentSnapshot;
  opsState.opsRuntimeReceipts = receiptsPayload.runtime_receipts || [];
  opsState.opsQualitySummary = qualitySummary;
  opsState.opsQualityEvents = qualityEvents.events || [];
  opsState.opsQualityTraceDetail = qualityTraceDetail;
  opsState.opsProviderRouting = providerRouting;
  opsState.opsProviderRollout = providerRollout;
  opsState.opsProviderRuntimeMetrics = providerRuntimeMetrics;
  opsState.opsStoryBootstrapWorldSummary = storyBootstrapWorldSummary.worlds || [];
  opsState.opsCommercializationSummary = commercializationSummary;
  const summaryWorldIds = new Set((opsState.opsStoryBootstrapWorldSummary || []).map((item) => item.worldId));
  const selectedBootstrapWorldId = summaryWorldIds.has(opsState.selectedOpsWorldId)
    ? opsState.selectedOpsWorldId
    : (opsState.opsStoryBootstrapWorldSummary?.[0]?.worldId || null);
  if (selectedBootstrapWorldId) {
    opsState.selectedOpsWorldId = selectedBootstrapWorldId;
    try {
      opsState.opsStoryBootstrapWorldDetail = await api(
        `/v1/ops/story-bootstrap-world-summary/worlds/${encodeURIComponent(selectedBootstrapWorldId)}?limit=12`
      );
    } catch (_error) {
      opsState.opsStoryBootstrapWorldDetail = null;
    }
  } else {
    opsState.opsStoryBootstrapWorldDetail = null;
  }
  const currentSignoffId = commercializationSummary?.production_signoff?.signoff_id || "";
  if (currentSignoffId) {
    try {
      opsState.opsProductionSignoffDetail = await api(`/v1/ops/production-signoff/${encodeURIComponent(currentSignoffId)}`);
    } catch (_error) {
      opsState.opsProductionSignoffDetail = null;
    }
  } else {
    opsState.opsProductionSignoffDetail = null;
  }
}
async function loadOpsJobsScope(token) {
  const [
    asyncJobsPayload,
    bootReconcile,
    incidents,
    artifactRetention,
    operatorHistory,
    handoffBundle,
    remoteShipping,
    handoffSla,
    adapterValidation,
    adapterHealthProbe,
    notificationReceipts,
    retryQueue,
    deadLetterQueue,
    retryOutcomeDashboard,
    retryPolicies,
  ] = await Promise.all([
    api("/v1/ops/jobs?limit=12"),
    api("/v1/ops/jobs/boot-reconcile"),
    api("/v1/ops/jobs/incidents?limit=12&stale_after_minutes=15"),
    api("/v1/ops/jobs/artifact-retention?limit=12"),
    api("/v1/ops/jobs/operator-history?limit=20"),
    api("/v1/ops/jobs/handoff-bundle?limit=12"),
    api("/v1/ops/jobs/remote-shipping?limit=12"),
    api("/v1/ops/jobs/handoff-sla?limit=12&sla_minutes=240"),
    api("/v1/ops/jobs/adapter-config-validation"),
    api("/v1/ops/jobs/adapter-health-probe"),
    api("/v1/ops/jobs/notification-delivery-receipts?limit=12"),
    api("/v1/ops/jobs/notification-retry-queue?limit=12"),
    api("/v1/ops/jobs/notification-dead-letter-queue?limit=12"),
    api("/v1/ops/jobs/retry-outcome-dashboard?limit=12"),
    api("/v1/ops/jobs/retry-policies"),
  ]);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsAsyncJobSummary = asyncJobsPayload.summary || null;
  opsState.opsAsyncJobs = asyncJobsPayload.jobs || [];
  opsState.opsAsyncJobBootReconcile = bootReconcile;
  opsState.opsAsyncJobIncidents = incidents;
  opsState.opsAsyncJobArtifactRetention = artifactRetention;
  opsState.opsAsyncJobOperatorHistory = operatorHistory;
  opsState.opsAsyncJobHandoffBundle = handoffBundle;
  opsState.opsAsyncJobRemoteShipping = remoteShipping;
  opsState.opsAsyncJobHandoffSla = handoffSla;
  opsState.opsAsyncJobAdapterValidation = adapterValidation;
  opsState.opsAsyncJobAdapterHealthProbe = adapterHealthProbe;
  opsState.opsAsyncJobNotificationReceipts = notificationReceipts;
  opsState.opsAsyncNotificationRetryQueue = retryQueue;
  opsState.opsAsyncNotificationDeadLetterQueue = deadLetterQueue;
  opsState.opsAsyncRetryOutcomeDashboard = retryOutcomeDashboard;
  opsState.opsAsyncRetryPolicies = retryPolicies;
}
async function loadOpsAccountScope(activeOpsAccountId, token) {
  if (!activeOpsAccountId) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsSubscriptionAudit = null;
      opsState.opsAccountWorkspace = null;
    }
    return;
  }
  if (dom.opsAccountId && !dom.opsAccountId.value.trim()) {
    dom.opsAccountId.value = activeOpsAccountId;
  }
  await Promise.all([
    refreshOpsSubscriptionAudit({ token }),
    refreshOpsAccountWorkspace({ token }),
  ]);
}
async function loadOpsAlertsScope(activeOpsAccountId, token) {
  if (dom.opsAlertAccountId && !dom.opsAlertAccountId.value.trim()) {
    dom.opsAlertAccountId.value = activeOpsAccountId;
  }
  await refreshOpsAlerts({ token });
}
async function loadOpsLearnedScope(token) {
  const [
    evalMetrics,
    crossPackQuality,
    learnedDashboard,
    learnedImpact,
    learnedCadence,
    learnedAssistedGate,
    learnedAssistedRerank,
    learnedReviewQuality,
    preferenceSamples,
    rankingSamples,
    evaluatorEvidence,
    rerankerEvidence,
    learnedCompare,
    learnedRollout,
    learnedDataOps,
    learnedPromotion,
    learnedRerankerPromotion,
  ] = await Promise.all([
    api("/v1/ops/eval-metrics"),
    refreshOpsCrossPackQuality({ token }),
    api("/v1/ops/learned-dashboard"),
    api("/v1/ops/learned-impact"),
    api("/v1/ops/learned-cadence"),
    api("/v1/ops/learned-assisted-gate"),
    api("/v1/ops/learned-assisted-rerank"),
    api("/v1/ops/learned-review-quality"),
    api("/v1/ops/preference-samples?limit=12"),
    api("/v1/ops/ranking-samples?limit=12"),
    api("/v1/ops/learned-promotion-evidence?track=evaluator"),
    api("/v1/ops/learned-promotion-evidence?track=reranker"),
    api("/v1/ops/learned-compare"),
    api("/v1/ops/learned-rollout"),
    api("/v1/ops/learned-data-ops"),
    api("/v1/ops/learned-promotion"),
    api("/v1/ops/learned-reranker-promotion"),
  ]);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsEvalMetrics = evalMetrics;
  opsState.opsCrossPackQuality = crossPackQuality;
  opsState.opsLearnedDashboard = learnedDashboard;
  opsState.opsLearnedImpact = learnedImpact;
  opsState.opsLearnedCadence = learnedCadence;
  opsState.opsLearnedAssistedGate = learnedAssistedGate;
  opsState.opsLearnedAssistedRerank = learnedAssistedRerank;
  opsState.opsLearnedReviewQuality = learnedReviewQuality;
  opsState.opsPreferenceSamples = preferenceSamples.preference_samples || [];
  opsState.opsRankingSamples = rankingSamples.ranking_samples || [];
  opsState.opsLearnedEvidence = {
    evaluator: evaluatorEvidence,
    reranker: rerankerEvidence,
  };
  opsState.opsLearnedCompare = learnedCompare;
  opsState.opsLearnedRollout = learnedRollout;
  opsState.opsLearnedDataOps = learnedDataOps;
  opsState.opsLearnedPromotion = learnedPromotion;
  opsState.opsLearnedRerankerPromotion = learnedRerankerPromotion;
  const latestTrainingJob = latestAsyncJob("learned_training");
  if (latestTrainingJob) {
    opsState.opsLearnedTrainingResult = { job: latestTrainingJob };
  }
}
async function loadOpsNavigationScope(activeOpsAccountId, token) {
  if (dom.opsNavAccountId && !dom.opsNavAccountId.value.trim() && opsState.opsNavigationPinned) {
    dom.opsNavAccountId.value = activeOpsAccountId;
  }
  if (dom.opsNavWorldId && !dom.opsNavWorldId.value.trim() && opsState.selectedOpsWorldId && opsState.opsNavigationPinned) {
    dom.opsNavWorldId.value = opsState.selectedOpsWorldId;
  }
  if (!shouldRefreshOpsNavigationModel()) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsNavigationModel = null;
    }
    return;
  }
  try {
    await refreshOpsNavigationModel({ token });
  } catch (error) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsNavigationModel = null;
    }
  }
}
async function loadOpsInvestigationScope(activeOpsAccountId, token) {
  if (!shouldRefreshOpsInvestigation()) {
    return;
  }
  if (dom.opsInvestigationAccountId && !dom.opsInvestigationAccountId.value.trim() && opsState.opsInvestigationPinned) {
    dom.opsInvestigationAccountId.value = activeOpsAccountId;
  }
  try {
    await OpsActionsRuntime.runOpsInvestigation({ skipRender: true, silent: true, token });
  } catch (error) {
    if (isActiveOpsRefresh(token)) {
      opsState.opsInvestigationBundle = null;
    }
  }
}
async function refreshOpsSurface(options = {}) {
  const preserveLastActionImpact = Boolean(options.preserveLastActionImpact);
  const scopes = normalizeOpsRefreshScopes(options.scopes);
  const token = ++opsState.opsRefreshRequestId;
  const activeOpsAccountId = dom.opsAccountId?.value.trim() || "";
  const tasks = [];
  if (scopes.includes("review_release")) {
    tasks.push(loadOpsReviewReleaseScope(token));
  }
  if (scopes.includes("runtime")) {
    tasks.push(loadOpsRuntimeScope(activeOpsAccountId, token));
  }
  if (scopes.includes("jobs")) {
    tasks.push(loadOpsJobsScope(token));
  }
  if (scopes.includes("account")) {
    tasks.push(loadOpsAccountScope(activeOpsAccountId, token));
  }
  if (scopes.includes("alerts")) {
    tasks.push(loadOpsAlertsScope(activeOpsAccountId, token));
  }
  if (scopes.includes("learned")) {
    tasks.push(loadOpsLearnedScope(token));
  }
  if (scopes.includes("navigation")) {
    tasks.push(loadOpsNavigationScope(activeOpsAccountId, token));
  }
  if (scopes.includes("investigation")) {
    tasks.push(loadOpsInvestigationScope(activeOpsAccountId, token));
  }
  await Promise.all(tasks);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  if (scopes.includes("jobs") || scopes.includes("learned")) {
    const latestTrainingJob = latestAsyncJob("learned_training");
    opsState.opsLearnedTrainingResult = latestTrainingJob ? { job: latestTrainingJob } : null;
  }
  if (scopes.includes("learned")) {
    opsState.opsLearnedDetail = null;
  }
  if (scopes.includes("review_release")) {
    opsState.opsReviewCaptureTarget = null;
  }
  if (!preserveLastActionImpact) {
    opsState.opsLastActionImpact = null;
  }
  OpsRenderRuntime.renderOpsSurface();
}
async function refreshOpsAccountFlow(options = {}) {
  await refreshOpsSurface({ ...options, scopes: ["account", "alerts", "navigation"] });
}
async function refreshOpsReleaseFlow(options = {}) {
  const scopes = ["review_release", "navigation"];
  if (opsState.opsInvestigationPinned) {
    scopes.push("investigation");
  }
  await refreshOpsSurface({ ...options, scopes });
}
async function refreshOpsJobsFlow(options = {}) {
  await refreshOpsSurface({ ...options, scopes: ["jobs", "runtime", "navigation"] });
}
async function refreshOpsLearnedFlow(options = {}) {
  await refreshOpsSurface({ ...options, scopes: ["jobs", "learned", "navigation"] });
}

  return {
    currentOpsNavigationContext,
    OPS_REFRESH_SCOPE_ALL,
    normalizeOpsRefreshScopes,
    syncOpsNavigationContext,
    refreshOpsReleaseWorkspace,
    refreshOpsAlerts,
    refreshOpsSurface,
    refreshOpsAccountFlow,
    refreshOpsReleaseFlow,
    refreshOpsJobsFlow,
    refreshOpsLearnedFlow,
    refreshOpsCrossPackQuality,
    buildCrossPackQualityUrl
  };
})();
