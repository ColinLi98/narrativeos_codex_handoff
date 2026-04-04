// Ops refresh orchestration extracted from app.js.

function currentOpsNavigationContext() {
  return {
    account_id: (els.opsNavAccountId?.value || "").trim() || "",
    world_id: (els.opsNavWorldId?.value || "").trim() || "",
    case_id: (els.opsNavCaseId?.value || "").trim() || "",
    alert_id: (els.opsNavAlertId?.value || "").trim() || "",
  };
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
  return token === undefined || token === null || token === appState.opsRefreshRequestId;
}

function syncOpsNavigationContext(prefill = {}, options = {}) {
  const preserveExisting = Boolean(options.preserveExisting);
  if ([prefill.account_id, prefill.world_id, prefill.case_id, prefill.alert_id].some(Boolean)) {
    appState.opsNavigationPinned = true;
  }
  const merged = {
    account_id: prefill.account_id ?? currentOpsNavigationContext().account_id,
    world_id: prefill.world_id ?? currentOpsNavigationContext().world_id,
    case_id: prefill.case_id ?? currentOpsNavigationContext().case_id,
    alert_id: prefill.alert_id ?? currentOpsNavigationContext().alert_id,
    world_version_id: prefill.world_version_id,
  };
  if (els.opsNavAccountId && (!preserveExisting || !els.opsNavAccountId.value.trim() || prefill.account_id !== undefined)) {
    els.opsNavAccountId.value = merged.account_id || "";
  }
  if (els.opsNavWorldId && (!preserveExisting || !els.opsNavWorldId.value.trim() || prefill.world_id !== undefined)) {
    els.opsNavWorldId.value = merged.world_id || "";
  }
  if (els.opsNavCaseId && (!preserveExisting || !els.opsNavCaseId.value.trim() || prefill.case_id !== undefined)) {
    els.opsNavCaseId.value = merged.case_id || "";
  }
  if (els.opsNavAlertId && (!preserveExisting || !els.opsNavAlertId.value.trim() || prefill.alert_id !== undefined)) {
    els.opsNavAlertId.value = merged.alert_id || "";
  }
  if (els.opsAccountId && (merged.account_id || prefill.account_id !== undefined)) {
    els.opsAccountId.value = merged.account_id || "";
  }
  if (
    els.opsAlertAccountId &&
    (merged.account_id || prefill.account_id !== undefined) &&
    (!preserveExisting || !els.opsAlertAccountId.value.trim() || prefill.account_id !== undefined)
  ) {
    els.opsAlertAccountId.value = merged.account_id || "";
  }
  if (
    els.opsInvestigationAccountId &&
    (merged.account_id || prefill.account_id !== undefined) &&
    (!preserveExisting || !els.opsInvestigationAccountId.value.trim() || prefill.account_id !== undefined)
  ) {
    els.opsInvestigationAccountId.value = merged.account_id || "";
  }
  if (merged.world_id || prefill.world_id !== undefined) {
    appState.selectedOpsWorldId = merged.world_id || null;
    if (els.opsReleaseWorldId && (!preserveExisting || !els.opsReleaseWorldId.value.trim() || prefill.world_id !== undefined)) {
      els.opsReleaseWorldId.value = merged.world_id || "";
    }
  }
  if (els.opsGovernanceCaseId && (merged.case_id || prefill.case_id !== undefined)) {
    els.opsGovernanceCaseId.value = merged.case_id || "";
  }
  if (els.opsInvestigationCaseId && (merged.case_id || prefill.case_id !== undefined)) {
    els.opsInvestigationCaseId.value = merged.case_id || "";
  }
  if (els.opsInvestigationWorldVersionId && (merged.world_version_id || prefill.world_version_id !== undefined)) {
    els.opsInvestigationWorldVersionId.value = merged.world_version_id || "";
  }
  if (merged.alert_id || prefill.alert_id !== undefined) {
    appState.selectedOpsAlertId = merged.alert_id || null;
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
      appState.opsNavigationModel = null;
    }
    return;
  }
  const payload = await api(`/v1/ops/navigation-model?${params.toString()}`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  appState.opsNavigationModel = payload;
  syncOpsNavigationContext(appState.opsNavigationModel.active_context || {}, { preserveExisting: false });
}

async function refreshOpsSubscriptionAudit(options = {}) {
  const token = options.token;
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  if (!accountId) {
    if (isActiveOpsRefresh(token)) {
      appState.opsSubscriptionAudit = null;
      appState.opsAccountWorkspace = null;
      appState.opsGovernanceSnapshot = null;
      appState.opsGovernanceExport = null;
      appState.opsGovernanceDetail = null;
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
  appState.opsSubscriptionAudit = {
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
  appState.opsAccountDetail = accountDetail;
  appState.opsGovernanceSnapshot = governanceSnapshot;
  appState.opsGovernanceExport = governanceExport;
  if (
    appState.opsGovernanceDetail &&
    !(governanceSnapshot.governance_cases || []).some((item) => item.case_id === appState.opsGovernanceDetail.case_id)
  ) {
    appState.opsGovernanceDetail = null;
  }
}
async function refreshOpsAccountWorkspace(options = {}) {
  const token = options.token;
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  if (!accountId) {
    if (isActiveOpsRefresh(token)) {
      appState.opsAccountWorkspace = null;
    }
    return;
  }
  const payload = await api(`/v1/ops/accounts/${encodeURIComponent(accountId)}/workspace?limit=12`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  appState.opsAccountWorkspace = payload;
}
async function refreshOpsReleaseWorkspace(options = {}) {
  const token = options.token;
  const worldId =
    (els.opsReleaseWorldId?.value || "").trim() ||
    appState.selectedOpsWorldId ||
    appState.opsWorldStatuses?.[0]?.world_id ||
    "";
  if (!worldId) {
    if (isActiveOpsRefresh(token)) {
      appState.opsReleaseWorkspace = null;
    }
    return;
  }
  appState.selectedOpsWorldId = worldId;
  if (els.opsReleaseWorldId) {
    els.opsReleaseWorldId.value = worldId;
  }
  const payload = await api(`/v1/ops/worlds/${encodeURIComponent(worldId)}/release-workspace?limit=12`);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  appState.opsReleaseWorkspace = payload;
}
function shouldRefreshOpsNavigationModel() {
  return appState.opsNavigationPinned || Object.values(currentOpsNavigationContext()).some(Boolean);
}
function shouldRefreshOpsInvestigation() {
  if (appState.opsInvestigationPinned) {
    return true;
  }
  const worldVersionId = (els.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (els.opsInvestigationCaseId?.value || "").trim();
  return Boolean(worldVersionId || caseId);
}
function currentOpsAlertFilters() {
  return {
    accountId: (els.opsAlertAccountId?.value || "").trim() || "",
    statusFilter: els.opsAlertStatusFilter?.value || "actionable",
    severity: els.opsAlertSeverityFilter?.value || "",
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
  appState.opsAlertsFeed = feed;
  const alerts = feed?.alerts || [];
  if (!alerts.length) {
    appState.selectedOpsAlertId = null;
    appState.opsAlertDetail = null;
    return;
  }
  const selectedId = appState.selectedOpsAlertId && alerts.find((item) => item.alert_id === appState.selectedOpsAlertId)
    ? appState.selectedOpsAlertId
    : alerts[0].alert_id;
  appState.selectedOpsAlertId = selectedId;
  const detail = await api(
    `/v1/ops/alerts/${encodeURIComponent(selectedId)}${
      filters.accountId ? `?account_id=${encodeURIComponent(filters.accountId)}` : ""
    }`
  );
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  appState.opsAlertDetail = detail;
}

async function loadOpsReviewReleaseScope(token) {
  const [queuePayload, worldPayload] = await Promise.all([
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
  appState.opsReviewQueue = queuePayload.reviews || [];
  appState.opsWorldStatuses = statuses;
  appState.opsWorldHistories = histories;
  if (!appState.selectedOpsWorldId && statuses.length) {
    appState.selectedOpsWorldId = statuses[0].world_id;
  }
  await refreshOpsReleaseWorkspace({ token });
}
async function loadOpsRuntimeScope(activeOpsAccountId, token) {
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
    providerRouting,
    providerRollout,
    providerRuntimeMetrics,
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
    api("/v1/ops/provider-routing"),
    api("/v1/ops/provider-rollout"),
    api(`/v1/ops/provider-runtime-metrics?account_id=${encodeURIComponent(activeOpsAccountId)}&limit=24`),
  ]);
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  appState.opsMeters = meterPayload.meters || [];
  appState.opsSchemaLifecycle = schemaLifecycle;
  appState.opsDataIntegrity = dataIntegrity;
  appState.opsDeploymentHealthGate = deploymentHealthGate;
  appState.opsPreflightVerification = preflightVerification;
  appState.opsDeploymentRunbook = deploymentRunbook;
  appState.opsIncidentPlaybook = incidentPlaybook;
  appState.opsRuntimeIncidentSnapshot = runtimeIncidentSnapshot;
  appState.opsRuntimeReceipts = receiptsPayload.runtime_receipts || [];
  appState.opsProviderRouting = providerRouting;
  appState.opsProviderRollout = providerRollout;
  appState.opsProviderRuntimeMetrics = providerRuntimeMetrics;
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
  appState.opsAsyncJobSummary = asyncJobsPayload.summary || null;
  appState.opsAsyncJobs = asyncJobsPayload.jobs || [];
  appState.opsAsyncJobBootReconcile = bootReconcile;
  appState.opsAsyncJobIncidents = incidents;
  appState.opsAsyncJobArtifactRetention = artifactRetention;
  appState.opsAsyncJobOperatorHistory = operatorHistory;
  appState.opsAsyncJobHandoffBundle = handoffBundle;
  appState.opsAsyncJobRemoteShipping = remoteShipping;
  appState.opsAsyncJobHandoffSla = handoffSla;
  appState.opsAsyncJobAdapterValidation = adapterValidation;
  appState.opsAsyncJobAdapterHealthProbe = adapterHealthProbe;
  appState.opsAsyncJobNotificationReceipts = notificationReceipts;
  appState.opsAsyncNotificationRetryQueue = retryQueue;
  appState.opsAsyncNotificationDeadLetterQueue = deadLetterQueue;
  appState.opsAsyncRetryOutcomeDashboard = retryOutcomeDashboard;
  appState.opsAsyncRetryPolicies = retryPolicies;
}
async function loadOpsAccountScope(activeOpsAccountId, token) {
  if (els.opsAccountId && !els.opsAccountId.value.trim()) {
    els.opsAccountId.value = activeOpsAccountId;
  }
  await Promise.all([
    refreshOpsSubscriptionAudit({ token }),
    refreshOpsAccountWorkspace({ token }),
  ]);
}
async function loadOpsAlertsScope(activeOpsAccountId, token) {
  if (els.opsAlertAccountId && !els.opsAlertAccountId.value.trim()) {
    els.opsAlertAccountId.value = activeOpsAccountId;
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
    api("/v1/ops/cross-pack-quality"),
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
  appState.opsEvalMetrics = evalMetrics;
  appState.opsCrossPackQuality = crossPackQuality;
  appState.opsLearnedDashboard = learnedDashboard;
  appState.opsLearnedImpact = learnedImpact;
  appState.opsLearnedCadence = learnedCadence;
  appState.opsLearnedAssistedGate = learnedAssistedGate;
  appState.opsLearnedAssistedRerank = learnedAssistedRerank;
  appState.opsLearnedReviewQuality = learnedReviewQuality;
  appState.opsPreferenceSamples = preferenceSamples.preference_samples || [];
  appState.opsRankingSamples = rankingSamples.ranking_samples || [];
  appState.opsLearnedEvidence = {
    evaluator: evaluatorEvidence,
    reranker: rerankerEvidence,
  };
  appState.opsLearnedCompare = learnedCompare;
  appState.opsLearnedRollout = learnedRollout;
  appState.opsLearnedDataOps = learnedDataOps;
  appState.opsLearnedPromotion = learnedPromotion;
  appState.opsLearnedRerankerPromotion = learnedRerankerPromotion;
  const latestTrainingJob = latestAsyncJob("learned_training");
  if (latestTrainingJob) {
    appState.opsLearnedTrainingResult = { job: latestTrainingJob };
  }
}
async function loadOpsNavigationScope(activeOpsAccountId, token) {
  if (els.opsNavAccountId && !els.opsNavAccountId.value.trim() && appState.opsNavigationPinned) {
    els.opsNavAccountId.value = activeOpsAccountId;
  }
  if (els.opsNavWorldId && !els.opsNavWorldId.value.trim() && appState.selectedOpsWorldId && appState.opsNavigationPinned) {
    els.opsNavWorldId.value = appState.selectedOpsWorldId;
  }
  if (!shouldRefreshOpsNavigationModel()) {
    if (isActiveOpsRefresh(token)) {
      appState.opsNavigationModel = null;
    }
    return;
  }
  try {
    await refreshOpsNavigationModel({ token });
  } catch (error) {
    if (isActiveOpsRefresh(token)) {
      appState.opsNavigationModel = null;
    }
  }
}
async function loadOpsInvestigationScope(activeOpsAccountId, token) {
  if (!shouldRefreshOpsInvestigation()) {
    return;
  }
  if (els.opsInvestigationAccountId && !els.opsInvestigationAccountId.value.trim() && appState.opsInvestigationPinned) {
    els.opsInvestigationAccountId.value = activeOpsAccountId;
  }
  try {
    await runOpsInvestigation({ skipRender: true, silent: true, token });
  } catch (error) {
    if (isActiveOpsRefresh(token)) {
      appState.opsInvestigationBundle = null;
    }
  }
}
async function refreshOpsSurface(options = {}) {
  const preserveLastActionImpact = Boolean(options.preserveLastActionImpact);
  const scopes = normalizeOpsRefreshScopes(options.scopes);
  const token = ++appState.opsRefreshRequestId;
  const activeOpsAccountId = els.opsAccountId?.value.trim() || activeReaderId();
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
    appState.opsLearnedTrainingResult = latestTrainingJob ? { job: latestTrainingJob } : null;
  }
  if (scopes.includes("learned")) {
    appState.opsLearnedDetail = null;
  }
  if (scopes.includes("review_release")) {
    appState.opsReviewCaptureTarget = null;
  }
  if (!preserveLastActionImpact) {
    appState.opsLastActionImpact = null;
  }
  renderOpsSurface();
}
async function refreshOpsAccountFlow(options = {}) {
  await refreshOpsSurface({ ...options, scopes: ["account", "alerts", "navigation"] });
}
async function refreshOpsReleaseFlow(options = {}) {
  const scopes = ["review_release", "navigation"];
  if (appState.opsInvestigationPinned) {
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
