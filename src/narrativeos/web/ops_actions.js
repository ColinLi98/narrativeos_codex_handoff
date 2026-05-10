// Ops action handlers extracted from app.js.

var OpsActionsRuntime = (() => {
  const dom = OpsDOM;
  const { api, setBusy, downloadJsonFile, parseTagList, reportUiMessage, parseErrorDetail } = UIShared;
  const { applySupportPrefill, applyGovernanceCasePrefill } = OpsShared;
  const {
    syncOpsNavigationContext,
    refreshOpsSurface,
    refreshOpsAccountFlow,
    refreshOpsReleaseFlow,
    refreshOpsJobsFlow,
    refreshOpsLearnedFlow,
    refreshOpsCrossPackQuality,
    refreshOpsReleaseWorkspace,
    refreshOpsAlerts
  } = OpsRefreshRuntime;

function resolveActiveReaderId() {
  if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.activeReaderId === "function") {
    return ReaderRuntime.activeReaderId();
  }
  return readerState.readerId || "";
}

function opsActiveReviewerId() {
  return (
    dom.opsReviewerId?.value.trim() ||
    dom.opsGovernanceReviewerId?.value.trim() ||
    authorState.authorAuthSession?.identity?.actor_id ||
    "ops_web"
  );
}

function opsGovernanceHeaders() {
  const reviewerId = dom.opsGovernanceReviewerId?.value.trim() || "ops_web";
  return {
    "X-NarrativeOS-Actor-Id": reviewerId,
    "X-NarrativeOS-Actor-Role": "reviewer",
    ...(dom.opsAccountId?.value.trim() ? { "X-NarrativeOS-Account-Id": dom.opsAccountId.value.trim() } : {}),
  };
}

function opsRestoreHeaders(actorId, actorRole) {
  return {
    "X-NarrativeOS-Actor-Id": actorId,
    "X-NarrativeOS-Actor-Role": actorRole,
  };
}

function governanceStatusLabel(status) {
  return {
    in_review: "进入复核",
    escalated: "升级处理",
    resolved: "结案",
    dismissed: "驳回结案",
    open: "重新打开",
  }[String(status || "")] || String(status || "更新");
}

function governanceOwnerDenialMessage(error, targetStatus) {
  const raw = String(error?.message || "");
  const parsed = parseErrorDetail(error);
  const detailText =
    typeof parsed === "string"
      ? parsed
      : parsed && typeof parsed.detail === "string"
        ? parsed.detail
        : "";
  if (!raw.includes("governance_case_owner_required") && !detailText.includes("governance_case_owner_required")) {
    return null;
  }
  const ownerId =
    opsState.opsGovernanceDetail?.workflow_summary?.owner_id ||
    opsState.opsGovernanceDetail?.owner_id ||
    dom.opsGovernanceOwnerId?.value.trim() ||
    "当前 owner";
  return `当前 case 只能由 owner ${ownerId} 执行“${governanceStatusLabel(targetStatus)}”。请先改派 owner，或让 owner 继续处理。`;
}

function showGovernanceOwnerDeniedBanner(targetStatus) {
  const ownerId =
    opsState.opsGovernanceDetail?.workflow_summary?.owner_id ||
    opsState.opsGovernanceDetail?.owner_id ||
    dom.opsGovernanceOwnerId?.value.trim() ||
    "当前 owner";
  const message = `当前 case 只能由 owner ${ownerId} 执行“${governanceStatusLabel(targetStatus)}”。请先改派 owner，或让 owner 继续处理。`;
  reportUiMessage(message, "warning");
  return message;
}

async function loadSelectedOpsReviewItem(reviewItemId) {
  opsState.opsSelectedReviewItemId = reviewItemId;
  opsState.opsSelectedReviewItemDetail = await api(`/v1/ops/review-items/${encodeURIComponent(reviewItemId)}`);
  try {
    opsState.opsSelectedReviewWorkDetail = await api(`/v1/ops/review-items/${encodeURIComponent(reviewItemId)}/work`);
  } catch (_error) {
    opsState.opsSelectedReviewWorkDetail = null;
  }
  const reviewItem = opsState.opsSelectedReviewItemDetail?.review_item || null;
  const traceId =
    reviewItem?.source_payload?.trace_summary?.trace_id ||
    (reviewItem?.linked_entities || []).find((entity) => entity.kind === "trace")?.id ||
    null;
  if (traceId) {
    await loadOpsQualityTraceDetail(traceId);
  } else {
    opsState.opsSelectedQualityTraceId = null;
    opsState.opsQualityTraceDetail = null;
  }
}

async function loadOpsQualityTraceDetail(traceId) {
  const normalizedTraceId = String(traceId || "").trim();
  if (!normalizedTraceId) {
    opsState.opsSelectedQualityTraceId = null;
    opsState.opsQualityTraceDetail = null;
    return null;
  }
  opsState.opsSelectedQualityTraceId = normalizedTraceId;
  opsState.opsQualityTraceDetail = await api(`/v1/ops/quality/traces/${encodeURIComponent(normalizedTraceId)}`);
  return opsState.opsQualityTraceDetail;
}

async function assignOpsReviewItem(reviewItemId, ownerId) {
  await api(`/v1/ops/review-items/${encodeURIComponent(reviewItemId)}/assign`, {
    method: "POST",
    body: JSON.stringify({
      owner_id: ownerId,
      reviewer_id: opsActiveReviewerId(),
    }),
  });
  await refreshOpsReleaseFlow();
}

async function updateOpsReviewItemStatus(reviewItemId, status) {
  await api(`/v1/ops/review-items/${encodeURIComponent(reviewItemId)}/status`, {
    method: "POST",
    body: JSON.stringify({
      status,
      reviewer_id: opsActiveReviewerId(),
    }),
  });
  await refreshOpsReleaseFlow();
}

async function decideOpsReviewItem(reviewItemId, decision) {
  await api(`/v1/ops/review-items/${encodeURIComponent(reviewItemId)}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      reviewer_id: opsActiveReviewerId(),
    }),
  });
  await refreshOpsReleaseFlow();
}

async function runOpsReviewHubAction(reviewItem, actionId) {
  const item = reviewItem || opsState.opsSelectedReviewItemDetail?.review_item || null;
  if (!item) {
    alert("请先选择一个统一审阅项。");
    return;
  }
  if (actionId === "assign_to_me") {
    await assignOpsReviewItem(item.review_item_id, opsActiveReviewerId());
    return;
  }
  if (actionId === "mark_triaged") {
    await updateOpsReviewItemStatus(item.review_item_id, "triaged");
    return;
  }
  if (actionId === "mark_in_review") {
    await updateOpsReviewItemStatus(item.review_item_id, "in_review");
    return;
  }
  if (actionId === "resolve") {
    await decideOpsReviewItem(item.review_item_id, "resolve");
    return;
  }
  if (actionId === "dismiss") {
    await decideOpsReviewItem(item.review_item_id, "dismiss");
    return;
  }
  if (actionId === "approve") {
    await decideOpsReviewItem(item.review_item_id, "approve");
    return;
  }
  if (actionId === "needs_changes") {
    await decideOpsReviewItem(item.review_item_id, "needs_changes");
    return;
  }
  if (actionId === "block") {
    await decideOpsReviewItem(item.review_item_id, "block");
    return;
  }
  if (actionId === "open_release_workspace") {
    syncOpsNavigationContext(
      {
        world_id: item.world_id || undefined,
        world_version_id: item.world_version_id || undefined,
        account_id: item.account_id || undefined,
      },
      { preserveExisting: false }
    );
    shellState.activeProduct = "ops";
    shellState.opsWorkspace = "release";
    await refreshOpsReleaseFlow();
    ShellStatusRuntime.syncProductMode();
    return;
  }
  if (actionId === "open_account_workspace") {
    syncOpsNavigationContext(
      {
        account_id: item.account_id || undefined,
        world_id: item.world_id || undefined,
        world_version_id: item.world_version_id || undefined,
      },
      { preserveExisting: false }
    );
    shellState.activeProduct = "ops";
    shellState.opsWorkspace = "account";
    await refreshOpsAccountFlow();
    ShellStatusRuntime.syncProductMode();
    return;
  }
  if (actionId === "open_governance_case") {
    const caseLink = (item.linked_entities || []).find((entity) => entity.kind === "case");
    syncOpsNavigationContext(
      {
        account_id: item.account_id || undefined,
        case_id: caseLink?.id || undefined,
        world_id: item.world_id || undefined,
        world_version_id: item.world_version_id || undefined,
      },
      { preserveExisting: false }
    );
    shellState.activeProduct = "ops";
    shellState.opsWorkspace = "alerts";
    await refreshOpsSurface({ scopes: ["alerts", "account", "navigation"], preserveLastActionImpact: true });
    ShellStatusRuntime.syncProductMode();
    return;
  }
  if (actionId === "open_investigation") {
    syncOpsNavigationContext(
      {
        account_id: item.account_id || undefined,
        world_id: item.world_id || undefined,
        world_version_id: item.world_version_id || undefined,
      },
      { preserveExisting: false }
    );
    if (dom.opsInvestigationAccountId && item.account_id) dom.opsInvestigationAccountId.value = item.account_id;
    if (dom.opsInvestigationWorldVersionId && item.world_version_id) dom.opsInvestigationWorldVersionId.value = item.world_version_id;
    shellState.activeProduct = "ops";
    shellState.opsWorkspace = "account";
    await runOpsInvestigation({ silent: true });
    await refreshOpsAccountFlow({ preserveLastActionImpact: true });
    ShellStatusRuntime.syncProductMode();
    return;
  }
  if (actionId === "escalate_to_governance") {
    applySupportPrefill({
      account_id: item.account_id || undefined,
      world_version_id: item.world_version_id || undefined,
    });
    shellState.activeProduct = "ops";
    shellState.opsWorkspace = "alerts";
    await refreshOpsSurface({ scopes: ["alerts", "account", "navigation"], preserveLastActionImpact: true });
    ShellStatusRuntime.syncProductMode();
  }
}


async function submitPromotionDecision(action) {
  const reviewerId = dom.opsPromotionReviewerId?.value.trim() || "ops_web";
  const reason = dom.opsPromotionReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 promotion reviewer_id 和 reason。");
    return;
  }
  const button = action === "approve" ? dom.opsApprovePromotion : dom.opsRevokePromotion;
  const restore = setBusy(button, action === "approve" ? "批准中…" : "撤销中…");
  try {
    opsState.opsLearnedPromotion = await api(
      action === "approve" ? "/v1/ops/learned-promotion/approve" : "/v1/ops/learned-promotion/revoke",
      {
        method: "POST",
        body: JSON.stringify({
          reviewer_id: reviewerId,
          reason,
        }),
      }
    );
    opsState.opsLastActionImpact = null;
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`更新 promotion 状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitRerankerPromotionDecision(action) {
  const reviewerId = dom.opsRerankerPromotionReviewerId?.value.trim() || "ops_web";
  const reason = dom.opsRerankerPromotionReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 reranker promotion reviewer_id 和 reason。");
    return;
  }
  const button = action === "approve" ? dom.opsApproveRerankerPromotion : dom.opsRevokeRerankerPromotion;
  const restore = setBusy(button, action === "approve" ? "批准中…" : "撤销中…");
  try {
    opsState.opsLearnedRerankerPromotion = await api(
      action === "approve"
        ? "/v1/ops/learned-reranker-promotion/approve"
        : "/v1/ops/learned-reranker-promotion/revoke",
      {
        method: "POST",
        body: JSON.stringify({
          reviewer_id: reviewerId,
          reason,
        }),
      }
    );
    opsState.opsLastActionImpact = null;
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`更新 reranker promotion 状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitProviderRollout(track, action) {
  const reviewerId = dom.opsProviderRolloutReviewerId?.value.trim() || "ops_web";
  const reason = dom.opsProviderRolloutReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 provider rollout reviewer_id 和 reason。");
    return;
  }
  const bucketPercentage = Number(dom.opsProviderRolloutBucket?.value || 0);
  const worldAllowlist = (dom.opsProviderRolloutWorldAllowlist?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  let button = dom.opsProviderCandidateCanary;
  if (track === "candidate" && action === "activate") button = dom.opsProviderCandidateActivate;
  if (track === "candidate" && action === "rollback") button = dom.opsProviderCandidateRollback;
  if (track === "renderer" && action === "canary") button = dom.opsProviderRendererCanary;
  if (track === "renderer" && action === "activate") button = dom.opsProviderRendererActivate;
  if (track === "renderer" && action === "rollback") button = dom.opsProviderRendererRollback;
  const restore = setBusy(button, action === "rollback" ? "回滚中…" : "保存中…");
  try {
    opsState.opsProviderRollout = await api(`/v1/ops/provider-rollout/${encodeURIComponent(track)}/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
        bucket_percentage: bucketPercentage,
        world_allowlist: worldAllowlist,
      }),
    });
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`更新 provider rollout 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function runDataIntegrityRepair(apply) {
  const rawActions = (dom.opsDataIntegrityActions?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const button = apply ? dom.opsApplyDataIntegrityRepair : dom.opsRunDataIntegrityDryRun;
  const restore = setBusy(button, apply ? "修复中…" : "扫描中…");
  try {
    opsState.opsDataIntegrityRepair = await api("/v1/ops/data-integrity/repair", {
      method: "POST",
      body: JSON.stringify({
        apply,
        actions: rawActions,
        limit: 20,
      }),
    });
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`执行 data integrity repair 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitAssistedGateConfig(mode, enabled) {
  const reviewerId = dom.opsAssistedGateReviewerId?.value.trim() || "ops_web";
  const reason = dom.opsAssistedGateReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 assisted gate reviewer_id 和 reason。");
    return;
  }
  const button = enabled
    ? (mode === "assisted_gate" ? dom.opsSetAssistedActive : dom.opsSetAssistedShadow)
    : dom.opsDisableAssistedGate;
  const restore = setBusy(button, enabled ? "保存中…" : "关闭中…");
  try {
    opsState.opsLearnedAssistedGate = await api("/v1/ops/learned-assisted-gate/configure", {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
        enabled,
        mode,
        bucket_percentage: Number(dom.opsAssistedGateBucket?.value || 0),
        confidence_threshold: Number(dom.opsAssistedGateConfidence?.value || 0.9),
        min_example_count: 3,
        min_high_confidence_blocks: 2,
        required_block_share: 0.5,
        world_allowlist: (dom.opsAssistedGateWorldAllowlist?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`更新 assisted gate experiment 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitAssistedRerankConfig(mode, enabled) {
  const reviewerId = dom.opsAssistedRerankReviewerId?.value.trim() || "ops_web";
  const reason = dom.opsAssistedRerankReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 assisted rerank reviewer_id 和 reason。");
    return;
  }
  const button = enabled
    ? (mode === "assisted_rerank" ? dom.opsSetAssistedRerankActive : dom.opsSetAssistedRerankShadow)
    : dom.opsDisableAssistedRerank;
  const restore = setBusy(button, enabled ? "保存中…" : "关闭中…");
  try {
    opsState.opsLearnedAssistedRerank = await api("/v1/ops/learned-assisted-rerank/configure", {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
        enabled,
        mode,
        bucket_percentage: Number(dom.opsAssistedRerankBucket?.value || 0),
        confidence_threshold: Number(dom.opsAssistedRerankConfidence?.value || 0.65),
        candidate_window: Number(dom.opsAssistedRerankCandidateWindow?.value || 3),
        max_score_gap: Number(dom.opsAssistedRerankMaxScoreGap?.value || 0.08),
        world_allowlist: (dom.opsAssistedRerankWorldAllowlist?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`更新 assisted rerank experiment 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitLearnedRollout(track, action) {
  const reviewerId =
    track === "evaluator"
      ? (dom.opsPromotionReviewerId?.value.trim() || "ops_web")
      : (dom.opsRerankerPromotionReviewerId?.value.trim() || "ops_web");
  const reason =
    track === "evaluator"
      ? (dom.opsPromotionReason?.value.trim() || "")
      : (dom.opsRerankerPromotionReason?.value.trim() || "");
  if (!reviewerId || !reason) {
    alert("请先填写对应 track 的 reviewer_id 和 reason。");
    return;
  }
  const endpoint =
    action === "activate"
      ? `/v1/ops/learned-rollout/${encodeURIComponent(track)}/activate`
      : `/v1/ops/learned-rollout/${encodeURIComponent(track)}/rollback`;
  try {
    opsState.opsLearnedRollout = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
      }),
    });
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`更新 learned rollout 失败：${error.message}`);
  }
}

async function createGovernanceCase() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const targetType = dom.opsGovernanceTargetType?.value || "account";
  const targetId = (dom.opsGovernanceTargetId?.value || "").trim() || (targetType === "account" ? accountId : "");
  const summary = (dom.opsGovernanceSummaryInput?.value || "").trim();
  const reviewerId = (dom.opsGovernanceReviewerId?.value || "ops_web").trim();
  if (!targetId || !summary) {
    alert("请填写 governance case 的 target_id 和 summary。");
    return;
  }
  const restore = setBusy(dom.opsCreateGovernanceCase, "创建中…");
  try {
    const payload = await api("/v1/ops/governance/cases", {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        case_type: dom.opsGovernanceCaseType?.value || "rights",
        target_type: targetType,
        target_id: targetId,
        account_id: accountId || undefined,
        world_version_id: targetType === "world_version" ? targetId : undefined,
        session_id: targetType === "session" ? targetId : undefined,
        entitlement_id: targetType === "entitlement" ? targetId : undefined,
        severity: dom.opsGovernanceSeverity?.value || "medium",
        summary,
        description: (dom.opsGovernanceNotes?.value || "").trim() || undefined,
        reviewer_id: reviewerId,
        owner_id: (dom.opsGovernanceOwnerId?.value || "").trim() || reviewerId,
        due_at: (dom.opsGovernanceDueAt?.value || "").trim() || undefined,
        disposition: (dom.opsGovernanceDisposition?.value || "").trim() || undefined,
        policy_labels: parseTagList(dom.opsGovernancePolicyLabels?.value || ""),
        evidence_refs: (dom.opsGovernanceEvidencePreview?.value || "").trim()
          ? [
              {
                title: (dom.opsGovernanceEvidenceTitle?.value || "").trim() || "manual_note",
                preview: (dom.opsGovernanceEvidencePreview?.value || "").trim(),
                kind: "note",
              },
            ]
          : [],
      }),
    });
    if (dom.opsGovernanceCaseId) dom.opsGovernanceCaseId.value = payload.case?.case_id || "";
    await refreshOpsAccountFlow();
    await refreshOpsJobsFlow();
    if (payload.case?.case_id) {
      await openGovernanceCaseDetail(payload.case.case_id);
    }
  } catch (error) {
    alert(`创建 governance case 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function updateGovernanceCaseStatus() {
  const caseId = (dom.opsGovernanceCaseId?.value || "").trim();
  const targetStatus = dom.opsGovernanceStatus?.value || "in_review";
  if (!caseId) {
    alert("先选择或填写一个 governance case id。");
    return;
  }
  const restore = setBusy(dom.opsUpdateGovernanceCase, "更新中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/status`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        status: targetStatus,
        reviewer_id: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        resolution_notes: (dom.opsGovernanceNotes?.value || "").trim() || undefined,
        disposition: (dom.opsGovernanceDisposition?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsAccountFlow();
    await refreshOpsJobsFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    const ownerDeniedMessage = governanceOwnerDenialMessage(error, targetStatus);
    if (ownerDeniedMessage) {
      showGovernanceOwnerDeniedBanner(targetStatus);
    } else {
      alert(`更新 governance case 状态失败：${error.message}`);
    }
  } finally {
    restore();
  }
}

async function applyGovernanceRestriction() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const reviewerId = (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web";
  const summary = (dom.opsGovernanceSummaryInput?.value || "").trim();
  if (!accountId || !summary) {
    alert("请填写 account_id 和 restriction summary。");
    return;
  }
  const restore = setBusy(dom.opsApplyGovernanceRestriction, "施加中…");
  try {
    const payload = await api("/v1/ops/governance/restrictions", {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        restriction_type: dom.opsGovernanceRestrictionType?.value || "account_hold",
        account_id: accountId,
        case_type: dom.opsGovernanceCaseType?.value || "abuse",
        severity: dom.opsGovernanceSeverity?.value || "high",
        summary,
        description: (dom.opsGovernanceNotes?.value || "").trim() || undefined,
        reviewer_id: reviewerId,
        expires_at: (dom.opsGovernanceRestrictionExpiresAt?.value || "").trim() || undefined,
        restriction_reason: (dom.opsGovernanceNotes?.value || "").trim() || summary,
      }),
    });
    await refreshOpsAccountFlow();
    if (payload.case?.case_id) {
      if (dom.opsGovernanceCaseId) dom.opsGovernanceCaseId.value = payload.case.case_id;
      await openGovernanceCaseDetail(payload.case.case_id);
    }
  } catch (error) {
    alert(`施加 restriction 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function releaseGovernanceRestriction() {
  const restrictionId = (dom.opsGovernanceCaseId?.value || "").trim();
  if (!restrictionId) {
    alert("先在 Case ID 中填入 restriction_id。");
    return;
  }
  const restore = setBusy(dom.opsReleaseGovernanceRestriction, "释放中…");
  try {
    const payload = await api(`/v1/ops/governance/restrictions/${encodeURIComponent(restrictionId)}/release`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        reviewer_id: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        release_reason: (dom.opsGovernanceNotes?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsAccountFlow();
    if (payload.case?.case_id) {
      await openGovernanceCaseDetail(payload.case.case_id);
    }
  } catch (error) {
    alert(`释放 restriction 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function assignGovernanceCase() {
  const caseId = (dom.opsGovernanceCaseId?.value || "").trim();
  const ownerId = (dom.opsGovernanceOwnerId?.value || "").trim();
  if (!caseId || !ownerId) {
    alert("先填写 case id 和 owner id。");
    return;
  }
  const restore = setBusy(dom.opsAssignGovernanceCase, "分配中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/assign`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        owner_id: ownerId,
        reviewer_id: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        due_at: (dom.opsGovernanceDueAt?.value || "").trim() || undefined,
        note: (dom.opsGovernanceNotes?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsAccountFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    alert(`分配 governance case 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function addGovernanceEvidence() {
  const caseId = (dom.opsGovernanceCaseId?.value || "").trim();
  const preview = (dom.opsGovernanceEvidencePreview?.value || "").trim();
  if (!caseId || !preview) {
    alert("先填写 case id 和 evidence preview。");
    return;
  }
  const restore = setBusy(dom.opsAddGovernanceEvidence, "记录中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/evidence`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        reviewer_id: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        title: (dom.opsGovernanceEvidenceTitle?.value || "").trim() || "manual_note",
        preview,
        kind: "note",
      }),
    });
    await refreshOpsAccountFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    alert(`添加 governance evidence 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function refreshGovernanceAuditExport() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  if (!accountId) return;
  try {
    opsState.opsGovernanceExport = await api(`/v1/ops/export/governance-audit?account_id=${encodeURIComponent(accountId)}`);
    OpsRenderRuntime.renderOpsSurface();
  } catch (error) {
    alert(`刷新治理导出失败：${error.message}`);
  }
}

async function createRuntimeBackup() {
  const restore = setBusy(dom.opsCreateRuntimeBackup, "备份中…");
  try {
    const payload = await api("/v1/ops/jobs/runtime-backups", {
      method: "POST",
      body: JSON.stringify({
        label: (dom.opsBackupLabel?.value || "").trim() || undefined,
        requested_by: (dom.opsRestoreRequesterId?.value || "ops_web").trim() || "ops_web",
        account_id: dom.opsAccountId?.value.trim() || resolveActiveReaderId(),
      }),
    });
    await refreshOpsJobsFlow();
    const latestBackupJob = payload.job?.job_id
      ? opsState.opsAsyncJobs.find((item) => item.job_id === payload.job.job_id)
      : latestAsyncJob("runtime_backup");
    if (dom.opsRestorePath && latestBackupJob?.result_summary?.backup_path) {
      dom.opsRestorePath.value = latestBackupJob.result_summary.backup_path;
    }
  } catch (error) {
    alert(`创建 runtime backup 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function restoreRuntimeBackup() {
  const backupPath = (dom.opsRestorePath?.value || "").trim();
  if (!backupPath) {
    alert("请先填写 backup path。");
    return;
  }
  const restore = setBusy(dom.opsRestoreRuntimeBackup, "恢复中…");
  try {
    await api("/v1/ops/runtime-restore", {
      method: "POST",
      body: JSON.stringify({
        backup_path: backupPath,
      }),
    });
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`恢复 runtime backup 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function runRecoveryDrill() {
  const backupPath = (dom.opsRestorePath?.value || "").trim() || undefined;
  const restore = setBusy(dom.opsRunRecoveryDrill, "演练中…");
  try {
    const payload = await api("/v1/ops/recovery-drill", {
      method: "POST",
      body: JSON.stringify({
        backup_path: backupPath,
      }),
    });
    opsState.opsRecoveryDrillResult = payload.recovery_drill || null;
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`执行 recovery drill 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function requestRuntimeRestore() {
  const backupPath = (dom.opsRestorePath?.value || "").trim();
  const requestedBy = (dom.opsRestoreRequesterId?.value || "").trim() || "ops_web";
  const reason = (dom.opsRestoreReason?.value || "").trim();
  if (!backupPath || !reason) {
    alert("请填写 restore backup path 和 restore reason。");
    return;
  }
  const restore = setBusy(dom.opsRequestRuntimeRestore, "请求中…");
  try {
    const payload = await api("/v1/ops/runtime-restore/request", {
      method: "POST",
      headers: opsRestoreHeaders(requestedBy, "ops"),
      body: JSON.stringify({
        backup_path: backupPath,
        reason,
      }),
    });
    if (dom.opsRestoreRequestId && payload.restore_request?.request_id) {
      dom.opsRestoreRequestId.value = payload.restore_request.request_id;
    }
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`创建 restore request 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function approveRuntimeRestore() {
  const requestId = (dom.opsRestoreRequestId?.value || "").trim();
  const approverId = (dom.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  const reason = (dom.opsRestoreReason?.value || "").trim();
  if (!requestId || !reason) {
    alert("请填写 restore request id 和 restore reason。");
    return;
  }
  const restore = setBusy(dom.opsApproveRuntimeRestore, "批准中…");
  try {
    await api(`/v1/ops/runtime-restore/${encodeURIComponent(requestId)}/approve`, {
      method: "POST",
      headers: opsRestoreHeaders(approverId, "admin"),
      body: JSON.stringify({
        reason,
      }),
    });
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`批准 restore request 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function revokeRuntimeRestore() {
  const requestId = (dom.opsRestoreRequestId?.value || "").trim();
  const reviewerId = (dom.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  const reason = (dom.opsRestoreReason?.value || "").trim();
  if (!requestId || !reason) {
    alert("请填写 restore request id 和 restore reason。");
    return;
  }
  const restore = setBusy(dom.opsRevokeRuntimeRestore, "撤销中…");
  try {
    await api(`/v1/ops/runtime-restore/${encodeURIComponent(requestId)}/revoke`, {
      method: "POST",
      headers: opsRestoreHeaders(reviewerId, "admin"),
      body: JSON.stringify({
        reason,
      }),
    });
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`撤销 restore request 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function executeRuntimeRestore() {
  const requestId = (dom.opsRestoreRequestId?.value || "").trim();
  const executorId = (dom.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  if (!requestId) {
    alert("请填写 restore request id。");
    return;
  }
  const restore = setBusy(dom.opsExecuteRuntimeRestore, "执行中…");
  try {
    await api("/v1/ops/jobs/runtime-restores", {
      method: "POST",
      headers: opsRestoreHeaders(executorId, "admin"),
      body: JSON.stringify({
        request_id: requestId,
      }),
    });
    await refreshOpsSurface({ scopes: ["runtime", "jobs"] });
  } catch (error) {
    alert(`执行 approved restore 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function retryAsyncJob() {
  const jobId = (dom.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(dom.opsRetryAsyncJob, "重试中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
      }),
    });
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`重试 async job 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function resumeAsyncJob() {
  const jobId = (dom.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(dom.opsResumeAsyncJob, "恢复中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/resume`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        stale_after_minutes: 15,
      }),
    });
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`恢复 async job 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function recoverAsyncJobIncidents() {
  const restore = setBusy(dom.opsRecoverAsyncJobs, "恢复中…");
  try {
    await api("/v1/ops/jobs/recover-incidents", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        stale_after_minutes: 15,
        limit: 10,
      }),
    });
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`批量恢复 async jobs 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function enforceAsyncJobRetention() {
  const restore = setBusy(dom.opsEnforceAsyncRetention, "清理中…");
  try {
    const payload = await api("/v1/ops/jobs/enforce-retention", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        dry_run: false,
        limit: 20,
      }),
    });
    await refreshOpsJobsFlow();
    alert(`Retention enforcement 完成：清理 ${payload.cleaned_job_count || 0} 个 jobs，移除 ${payload.removed_item_count || 0} 个 artifacts。`);
  } catch (error) {
    alert(`执行 retention enforcement 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function runColdStartRecoveryDrill() {
  const restore = setBusy(dom.opsRunColdStartDrill, "演练中…");
  try {
    const payload = await api("/v1/ops/jobs/cold-start-drill", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        stale_after_minutes: 15,
        limit: 20,
      }),
    });
    await refreshOpsJobsFlow();
    alert(`Cold-start drill 完成：would_reconcile=${payload.would_reconcile_count || 0}，would_recover=${payload.would_recover_count || 0}。`);
  } catch (error) {
    alert(`执行 cold-start drill 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function exportAsyncJobHandoffBundle() {
  const restore = setBusy(dom.opsExportHandoffBundle, "导出中…");
  try {
    const payload = await api("/v1/ops/jobs/handoff-bundle/export", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        limit: 20,
      }),
    });
    opsState.opsAsyncJobHandoffBundle = payload;
    OpsRenderRuntime.renderOpsSurface();
    alert(`Handoff bundle 已导出：${payload.export_path || "-"}`);
  } catch (error) {
    alert(`导出 handoff bundle 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function acknowledgeAsyncJob() {
  const jobId = (dom.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(dom.opsAcknowledgeAsyncJob, "确认中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        note: (dom.opsAsyncJobNote?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`确认 async job 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function shipRemoteArtifacts() {
  const jobId = (dom.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(dom.opsShipRemoteArtifacts, "运输中…");
  try {
    const payload = await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/ship-remote`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        dry_run: false,
      }),
    });
    await refreshOpsJobsFlow();
    alert(`Remote shipping 完成：${payload.shipped_item_count || 0} 个 items -> ${payload.remote_dir || "-"}`);
  } catch (error) {
    alert(`执行 remote artifact shipping 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function escalateHandoffSla() {
  const restore = setBusy(dom.opsEscalateHandoffSla, "升级中…");
  try {
    const payload = await api("/v1/ops/jobs/handoff-sla/escalate", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        sla_minutes: 240,
        limit: 20,
        dry_run: false,
      }),
    });
    await refreshOpsLearnedFlow();
    alert(`Handoff SLA escalation 完成：${payload.escalated_count || 0} 个 jobs 已升级。`);
  } catch (error) {
    alert(`执行 handoff SLA escalation 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function enqueueNotificationRetry() {
  const receiptId = (dom.opsNotificationReceiptId?.value || "").trim();
  if (!receiptId) {
    alert("请先填写 notification receipt id。");
    return;
  }
  const restore = setBusy(dom.opsEnqueueNotificationRetry, "入队中…");
  try {
    const payload = await api("/v1/ops/jobs/notification-retry-queue/enqueue", {
      method: "POST",
      body: JSON.stringify({
        event_id: Number(receiptId),
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        note: (dom.opsAsyncJobNote?.value || "").trim() || undefined,
      }),
    });
    if (dom.opsNotificationReceiptId) {
      dom.opsNotificationReceiptId.value = payload.retry?.retry_id || receiptId;
    }
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`入队 notification retry 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function processNotificationRetry() {
  const retryId = (dom.opsNotificationReceiptId?.value || "").trim();
  if (!retryId) {
    alert("请先填写 notification retry id。");
    return;
  }
  const restore = setBusy(dom.opsProcessNotificationRetry, "处理中…");
  try {
    await api(`/v1/ops/jobs/notification-retry-queue/${encodeURIComponent(retryId)}/process`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        dry_run: false,
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`处理 notification retry 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function runLearnedTraining(tracks) {
  const button =
    tracks.length === 2
      ? dom.opsRunBothTraining
      : tracks[0] === "evaluator"
        ? dom.opsRunEvaluatorTraining
        : dom.opsRunRerankerTraining;
  const restore = setBusy(button, "运行中…");
  try {
    opsState.opsLearnedTrainingResult = await api("/v1/ops/jobs/learned-training", {
      method: "POST",
      body: JSON.stringify({
        tracks,
        requested_by: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`运行 learned training 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function openGovernanceCaseDetail(caseId) {
  if (!caseId) return;
  opsState.opsGovernanceDetail = await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}`, {
    headers: opsGovernanceHeaders(),
  });
  applyGovernanceCasePrefill({
    case_id: opsState.opsGovernanceDetail.case_id,
    case_type: opsState.opsGovernanceDetail.case_type,
    target_type: opsState.opsGovernanceDetail.target_type,
    target_id: opsState.opsGovernanceDetail.target_id,
    severity: opsState.opsGovernanceDetail.severity,
    reviewer_id: opsState.opsGovernanceDetail.reviewer_id,
    owner_id: opsState.opsGovernanceDetail.workflow_summary?.owner_id || opsState.opsGovernanceDetail.owner_id,
    summary: opsState.opsGovernanceDetail.summary,
    description: opsState.opsGovernanceDetail.resolution_notes || opsState.opsGovernanceDetail.description,
    status: opsState.opsGovernanceDetail.status,
    account_id: opsState.opsGovernanceDetail.account_id,
    due_at: opsState.opsGovernanceDetail.workflow_summary?.due_at || opsState.opsGovernanceDetail.due_at,
    disposition: opsState.opsGovernanceDetail.workflow_summary?.disposition || opsState.opsGovernanceDetail.disposition,
    policy_labels: opsState.opsGovernanceDetail.workflow_summary?.policy_labels || opsState.opsGovernanceDetail.policy_labels || [],
  });
  OpsRenderRuntime.renderOpsSurface();
}

async function escalateSupportIssue(issue) {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  if (!accountId || !issue?.issue_id) {
    alert("缺少 account_id 或 support issue id。");
    return;
  }
  const restore = setBusy(dom.opsCreateGovernanceCase, "升级中…");
  try {
    const payload = await api(`/v1/ops/accounts/${encodeURIComponent(accountId)}/governance/escalate-support`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        issue_id: issue.issue_id,
        reviewer_id: (dom.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
      }),
    });
    opsState.opsGovernanceDetail = payload.case || null;
    await refreshOpsAccountFlow();
    if (payload.case?.case_id) {
      await openGovernanceCaseDetail(payload.case.case_id);
    }
  } catch (error) {
    alert(`升级 support issue 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function grantOpsSubscription() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const tierId = dom.opsTierId?.value || "play_pass";
  const restore = setBusy(dom.opsGrantSubscription, "授予中…");
  try {
    await api("/v1/ops/subscriptions/grant", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        tier_id: tierId,
        provider: "ops_manual",
        status: "active",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`授予会员失败：${error.message}`);
  } finally {
    restore();
  }
}

async function changeOpsSubscriptionState() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const status = dom.opsSubscriptionStatus?.value || "active";
  const current = opsState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可更新。");
    return;
  }
  const restore = setBusy(dom.opsChangeSubscriptionState, "更新中…");
  try {
    await api("/v1/ops/subscriptions/state", {
      method: "POST",
      body: JSON.stringify({
        subscription_id: current.subscription_id,
        status,
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`更新订阅状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function grantOpsWallet() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const walletType = dom.opsWalletType?.value || "story_credits";
  const amount = Number(dom.opsWalletAmount?.value || 10);
  const restore = setBusy(dom.opsGrantWallet, "充值中…");
  try {
    await api("/v1/ops/wallets/grant", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        wallet_type: walletType,
        amount,
        tier_id: dom.opsTierId?.value || null,
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`充值钱包失败：${error.message}`);
  } finally {
    restore();
  }
}

async function debitOpsWallet() {
  const accountId = dom.opsAccountId?.value.trim() || resolveActiveReaderId();
  const walletType = dom.opsWalletType?.value || "story_credits";
  const amount = Number(dom.opsWalletAmount?.value || 10);
  const restore = setBusy(dom.opsDebitWallet, "扣减中…");
  try {
    await api("/v1/ops/wallets/debit", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        wallet_type: walletType,
        amount,
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`扣减钱包失败：${error.message}`);
  } finally {
    restore();
  }
}

async function reconcileOpsSubscription() {
  const current = opsState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可 reconcile。");
    return;
  }
  try {
    await api(`/v1/ops/subscriptions/${encodeURIComponent(current.subscription_id)}/reconcile`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: dom.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`reconcile subscription 失败：${error.message}`);
  }
}

async function retryOpsSubscriptionPayment() {
  const current = opsState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可 retry。");
    return;
  }
  try {
    await api(`/v1/ops/subscriptions/${encodeURIComponent(current.subscription_id)}/retry-payment`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: dom.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`retry subscription 失败：${error.message}`);
  }
}

async function replayOpsBillingEvent() {
  const eventId = (dom.opsBillingEventId?.value || "").trim();
  if (!eventId) {
    alert("先填写 billing event id。");
    return;
  }
  try {
    await api(`/v1/ops/billing-events/${encodeURIComponent(eventId)}/replay`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: dom.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`replay billing event 失败：${error.message}`);
  }
}

async function updateSelectedOpsAlertStatus(status) {
  if (!opsState.selectedOpsAlertId) {
    alert("先选择一条 alert。");
    return;
  }
  const reviewerId = dom.opsGovernanceReviewerId?.value.trim() || "ops_web";
  const accountId = currentOpsAlertFilters().accountId || opsState.opsAlertDetail?.alert?.account_id || undefined;
  await api(`/v1/ops/alerts/${encodeURIComponent(opsState.selectedOpsAlertId)}/status`, {
    method: "POST",
    body: JSON.stringify({
      account_id: accountId,
      status,
      reviewer_id: reviewerId,
      note: dom.opsAlertNote?.value.trim() || null,
    }),
  });
  await refreshOpsAlerts();
  OpsRenderRuntime.renderOpsSurface();
}

async function openSelectedOpsAlertInvestigation() {
  const investigationRef =
    opsState.opsAlertDetail?.alert?.investigation_ref ||
    opsState.opsAlertDetail?.investigation_bundle?.filters ||
    {};
  if (!investigationRef.account_id && !investigationRef.world_version_id && !investigationRef.case_id) {
    alert("当前 alert 没有 investigation ref。");
    return;
  }
  if (dom.opsInvestigationAccountId) {
    dom.opsInvestigationAccountId.value = investigationRef.account_id || "";
  }
  if (dom.opsInvestigationWorldVersionId) {
    dom.opsInvestigationWorldVersionId.value = investigationRef.world_version_id || "";
  }
  if (dom.opsInvestigationCaseId) {
    dom.opsInvestigationCaseId.value = investigationRef.case_id || "";
  }
  await runOpsInvestigation();
  dom.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runOpsWorkspaceAction(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  if (!action) return;
  if (prefill.account_id && dom.opsAccountId) {
    dom.opsAccountId.value = prefill.account_id;
  }
  if (action.handler === "grant_wallet") {
    if (dom.opsWalletType && prefill.wallet_type) dom.opsWalletType.value = prefill.wallet_type;
    if (dom.opsWalletAmount && prefill.amount !== undefined) dom.opsWalletAmount.value = String(prefill.amount);
    await grantOpsWallet();
    return;
  }
  if (action.handler === "grant_subscription") {
    if (dom.opsTierId && prefill.tier_id) dom.opsTierId.value = prefill.tier_id;
    await grantOpsSubscription();
    return;
  }
  if (action.handler === "retry_subscription_payment") {
    await retryOpsSubscriptionPayment();
    return;
  }
  if (action.handler === "reconcile_subscription") {
    await reconcileOpsSubscription();
    return;
  }
  if (action.handler === "run_investigation") {
    if (dom.opsInvestigationAccountId) dom.opsInvestigationAccountId.value = prefill.account_id || dom.opsAccountId?.value || "";
    if (dom.opsInvestigationWorldVersionId) dom.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    if (dom.opsInvestigationCaseId) dom.opsInvestigationCaseId.value = prefill.case_id || "";
    await runOpsInvestigation();
    dom.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (action.handler === "open_governance_case") {
    if (prefill.account_id && dom.opsAccountId) dom.opsAccountId.value = prefill.account_id;
    if (prefill.case_id && dom.opsGovernanceCaseId) dom.opsGovernanceCaseId.value = prefill.case_id;
    if (prefill.case_id) {
      await openGovernanceCaseDetail(prefill.case_id);
      dom.opsGovernanceDetail?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }
  if (action.handler === "open_alert_feed") {
    if (dom.opsAlertAccountId) dom.opsAlertAccountId.value = prefill.account_id || dom.opsAccountId?.value || "";
    await refreshOpsAlerts();
    OpsRenderRuntime.renderOpsSurface();
    dom.opsAlertSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function runOpsReleaseWorkspaceAction(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  if (!action) return;
  if (action.handler === "publish_world_version") {
    const worldVersionId = prefill.world_version_id;
    if (!worldVersionId) {
      alert("当前 action 缺少 world_version_id。");
      return;
    }
    await api(`/v1/ops/world-versions/${encodeURIComponent(worldVersionId)}/publish`, {
      method: "POST",
      body: JSON.stringify({ reviewer_id: dom.opsGovernanceReviewerId?.value.trim() || "ops_web" }),
    });
    await refreshOpsReleaseFlow();
    return;
  }
  if (action.handler === "rollback_world") {
    const worldId = prefill.world_id || opsState.selectedOpsWorldId;
    const targetWorldVersionId = prefill.target_world_version_id;
    if (!worldId || !targetWorldVersionId) {
      alert("当前 action 缺少 rollback 目标。");
      return;
    }
    await api(`/v1/ops/worlds/${encodeURIComponent(worldId)}/rollback`, {
      method: "POST",
      body: JSON.stringify({
        target_world_version_id: targetWorldVersionId,
        reviewer_id: dom.opsGovernanceReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsReleaseFlow();
    return;
  }
  if (action.handler === "run_release_investigation") {
    if (dom.opsInvestigationAccountId) {
      dom.opsInvestigationAccountId.value = prefill.account_id || "";
    }
    if (dom.opsInvestigationWorldVersionId) {
      dom.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    }
    if (dom.opsInvestigationCaseId) {
      dom.opsInvestigationCaseId.value = "";
    }
    await runOpsInvestigation();
    dom.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (action.handler === "inspect_publish_blocker") {
    opsState.selectedOpsReleaseBlockerKey = prefill.blocker_key || null;
    opsState.selectedOpsReleaseBlockerCheckKey = prefill.check_key || null;
    OpsRenderRuntime.renderOpsSurface();
    highlightOpsReleaseWorkspaceTarget();
    return;
  }
  if (action.handler === "inspect_strategy_bundle_batch_validation" || action.handler === "inspect_cross_pack_quality") {
    if (dom.opsCrossPackValidateStrategyBundle) {
      dom.opsCrossPackValidateStrategyBundle.checked = Boolean(prefill.validate_strategy_bundle);
    }
    if (dom.opsCrossPackStrategyBundleId) {
      dom.opsCrossPackStrategyBundleId.value = prefill.strategy_bundle_id || "";
    }
    if (dom.opsCrossPackWeakestLimit && prefill.weakest_limit) {
      dom.opsCrossPackWeakestLimit.value = String(prefill.weakest_limit);
    }
    await refreshOpsCrossPackQuality({
      validateStrategyBundle: Boolean(prefill.validate_strategy_bundle),
      strategyBundleId: prefill.strategy_bundle_id || "",
      weakestLimit: prefill.weakest_limit || dom.opsCrossPackWeakestLimit?.value || "3",
    });
    OpsRenderRuntime.renderOpsSurface();
    dom.opsCrossPackQuality?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function applyOpsNavigationStaleRefCleanup(staleRefs = {}) {
  if (staleRefs.alert) {
    if (dom.opsNavAlertId) dom.opsNavAlertId.value = "";
    if (opsState.selectedOpsAlertId === staleRefs.alert.ref_id) {
      opsState.selectedOpsAlertId = null;
    }
    opsState.opsAlertDetail = null;
  }
  if (staleRefs.case) {
    if (dom.opsNavCaseId) dom.opsNavCaseId.value = "";
    if (dom.opsGovernanceCaseId) dom.opsGovernanceCaseId.value = "";
    if (dom.opsInvestigationCaseId) dom.opsInvestigationCaseId.value = "";
    opsState.opsGovernanceDetail = null;
  }
  if (staleRefs.world) {
    if (dom.opsNavWorldId) dom.opsNavWorldId.value = "";
    if (dom.opsReleaseWorldId) dom.opsReleaseWorldId.value = "";
    if (opsState.selectedOpsWorldId === staleRefs.world.ref_id) {
      opsState.selectedOpsWorldId = null;
    }
    opsState.opsReleaseWorkspace = null;
  }
  if (staleRefs.world_version) {
    if (dom.opsInvestigationWorldVersionId) dom.opsInvestigationWorldVersionId.value = "";
    if (opsState.opsInvestigationBundle?.filters?.world_version_id === staleRefs.world_version.ref_id) {
      opsState.opsInvestigationBundle = null;
    }
  }
}

async function clearOpsNavigationStaleRefs(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  const staleRefs = { ...(prefill.stale_refs || opsState.opsNavigationModel?.linked_context?.stale_refs || {}) };
  applyOpsNavigationStaleRefCleanup(staleRefs);
  await refreshOpsSurface({
    scopes: ["account", "review_release", "alerts", "navigation", "investigation"],
    preserveLastActionImpact: true,
  });
}

async function resyncOpsNavigationContext(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  const staleRefs = { ...(prefill.stale_refs || opsState.opsNavigationModel?.linked_context?.stale_refs || {}) };
  applyOpsNavigationStaleRefCleanup(staleRefs);
  syncOpsNavigationContext(
    {
      account_id: prefill.account_id ?? null,
      world_id: prefill.world_id ?? null,
      case_id: prefill.case_id ?? null,
      alert_id: prefill.alert_id ?? null,
      world_version_id: prefill.world_version_id ?? null,
    },
    { preserveExisting: false }
  );
  await refreshOpsSurface({
    scopes: ["account", "review_release", "alerts", "navigation", "investigation"],
    preserveLastActionImpact: true,
  });
}

async function runOpsNavigationFollowUpAction(action) {
  if (!action) return;
  if (action.source_surface === "navigation_model") {
    if (action.handler === "clear_stale_refs") {
      await clearOpsNavigationStaleRefs(action);
      return;
    }
    if (action.handler === "resync_navigation_context") {
      await resyncOpsNavigationContext(action);
      return;
    }
  }
  if (action.source_surface === "release_workspace") {
    await runOpsReleaseWorkspaceAction(action);
    return;
  }
  if (action.source_surface === "account_workspace") {
    await runOpsWorkspaceAction(action);
    return;
  }
  await runOpsNavigationTarget({
    target_id: action.handler === "open_governance_case" ? "governance_case" : "investigation",
    prefill: action.prefill || {},
  });
}

async function runOpsNavigationTarget(target) {
  const prefill = { ...((target && target.prefill) || {}) };
  if (!target) return;
  syncOpsNavigationContext(prefill, { preserveExisting: false });
  if (target.target_id === "account_workspace") {
    if (prefill.account_id && dom.opsAccountId) {
      dom.opsAccountId.value = prefill.account_id;
    }
    await refreshOpsAccountFlow();
    dom.opsAccountWorkspaceSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "release_workspace") {
    if (prefill.world_id && dom.opsReleaseWorldId) {
      dom.opsReleaseWorldId.value = prefill.world_id;
    }
    opsState.selectedOpsWorldId = prefill.world_id || opsState.selectedOpsWorldId;
    await refreshOpsReleaseWorkspace();
    OpsRenderRuntime.renderOpsSurface();
    dom.opsReleaseWorkspaceSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "governance_case") {
    if (prefill.case_id) {
      await openGovernanceCaseDetail(prefill.case_id);
      dom.opsGovernanceDetail?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }
  if (target.target_id === "alert_detail") {
    if (prefill.account_id && dom.opsAlertAccountId) {
      dom.opsAlertAccountId.value = prefill.account_id;
    }
    if (prefill.alert_id) {
      opsState.selectedOpsAlertId = prefill.alert_id;
    }
    await refreshOpsAlerts();
    OpsRenderRuntime.renderOpsSurface();
    dom.opsAlertSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "investigation") {
    if (dom.opsInvestigationAccountId) dom.opsInvestigationAccountId.value = prefill.account_id || "";
    if (dom.opsInvestigationWorldVersionId) dom.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    if (dom.opsInvestigationCaseId) dom.opsInvestigationCaseId.value = prefill.case_id || "";
    await runOpsInvestigation();
    dom.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function followOpsNavigationRecommendation() {
  const model = opsState.opsNavigationModel;
  if (!model?.escalation_summary?.recommended_target) {
    alert("当前没有推荐的 escalation target。");
    return;
  }
  const target = (model.navigation_targets || []).find(
    (item) => item.target_id === model.escalation_summary.recommended_target
  );
  if (!target) {
    alert("当前推荐目标无法定位。");
    return;
  }
  await runOpsNavigationTarget(target);
}

async function runOpsInvestigation(options = {}) {
  const token = options.token;
  const accountId = (dom.opsInvestigationAccountId?.value || "").trim() || (dom.opsAccountId?.value || "").trim();
  const worldVersionId = (dom.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (dom.opsInvestigationCaseId?.value || "").trim();
  if (!accountId && !worldVersionId && !caseId) {
    alert("请至少填写 account_id、world_version_id 或 case_id。");
    return;
  }
  if (!options.silent) {
    opsState.opsInvestigationPinned = true;
  }
  const params = new URLSearchParams();
  if (worldVersionId) params.set("world_version_id", worldVersionId);
  if (caseId) params.set("case_id", caseId);
  params.set("limit", "50");
  let payload;
  if (caseId) {
    payload = await api(`/v1/ops/investigations/cases/${encodeURIComponent(caseId)}?${params.toString()}`);
  } else if (worldVersionId && !accountId) {
    payload = await api(`/v1/ops/investigations/world-versions/${encodeURIComponent(worldVersionId)}?limit=50`);
  } else {
    payload = await api(`/v1/ops/investigations/accounts/${encodeURIComponent(accountId)}?${params.toString()}`);
  }
  if (!isActiveOpsRefresh(token)) {
    return;
  }
  opsState.opsInvestigationBundle = payload;
  if (!options.skipRender) {
    OpsRenderRuntime.renderOpsSurface();
  }
}

async function exportOpsInvestigationTrace() {
  const accountId = (dom.opsInvestigationAccountId?.value || "").trim() || (dom.opsAccountId?.value || "").trim();
  const worldVersionId = (dom.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (dom.opsInvestigationCaseId?.value || "").trim();
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  if (worldVersionId) params.set("world_version_id", worldVersionId);
  if (caseId) params.set("case_id", caseId);
  params.set("limit", "100");
  if (!accountId && !worldVersionId && !caseId) {
    alert("请至少填写 account_id、world_version_id 或 case_id。");
    return;
  }
  opsState.opsInvestigationBundle = await api(`/v1/ops/export/investigation-trace?${params.toString()}`);
  downloadJsonFile(
    `investigation-trace-${caseId || worldVersionId || accountId || "export"}.json`,
    opsState.opsInvestigationBundle
  );
  OpsRenderRuntime.renderOpsSurface();
}

async function revokeOpsEntitlement() {
  const entitlementId = dom.opsEntitlementId?.value.trim();
  const reason = dom.opsEntitlementReason?.value.trim() || "manual_entitlement_revoke";
  if (!entitlementId) {
    alert("请先填写要撤销的 entitlement_id。");
    return;
  }
  const restore = setBusy(dom.opsRevokeEntitlement, "撤销中…");
  try {
    await api("/v1/ops/entitlements/revoke", {
      method: "POST",
      body: JSON.stringify({
        entitlement_id: entitlementId,
        reason,
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`撤销权益失败：${error.message}`);
  } finally {
    restore();
  }
}

  return {
    opsGovernanceHeaders,
    opsRestoreHeaders,
    showGovernanceOwnerDeniedBanner,
    submitPromotionDecision,
    submitRerankerPromotionDecision,
    submitProviderRollout,
    runDataIntegrityRepair,
    submitAssistedGateConfig,
    submitAssistedRerankConfig,
    submitLearnedRollout,
    createGovernanceCase,
    updateGovernanceCaseStatus,
    applyGovernanceRestriction,
    releaseGovernanceRestriction,
    assignGovernanceCase,
    addGovernanceEvidence,
    refreshGovernanceAuditExport,
    createRuntimeBackup,
    restoreRuntimeBackup,
    runRecoveryDrill,
    requestRuntimeRestore,
    approveRuntimeRestore,
    revokeRuntimeRestore,
    executeRuntimeRestore,
    retryAsyncJob,
    resumeAsyncJob,
    recoverAsyncJobIncidents,
    enforceAsyncJobRetention,
    runColdStartRecoveryDrill,
    exportAsyncJobHandoffBundle,
    acknowledgeAsyncJob,
    shipRemoteArtifacts,
    escalateHandoffSla,
    enqueueNotificationRetry,
    processNotificationRetry,
    runLearnedTraining,
    openGovernanceCaseDetail,
    escalateSupportIssue,
    grantOpsSubscription,
    changeOpsSubscriptionState,
    grantOpsWallet,
    debitOpsWallet,
    reconcileOpsSubscription,
    retryOpsSubscriptionPayment,
    replayOpsBillingEvent,
    updateSelectedOpsAlertStatus,
    openSelectedOpsAlertInvestigation,
    runOpsWorkspaceAction,
    runOpsReleaseWorkspaceAction,
    applyOpsNavigationStaleRefCleanup,
    clearOpsNavigationStaleRefs,
    resyncOpsNavigationContext,
    runOpsNavigationFollowUpAction,
    runOpsNavigationTarget,
    followOpsNavigationRecommendation,
    runOpsInvestigation,
    exportOpsInvestigationTrace,
    revokeOpsEntitlement,
    loadOpsQualityTraceDetail,
    loadSelectedOpsReviewItem,
    runOpsReviewHubAction
  };
})();
function highlightOpsReleaseWorkspaceTarget() {
  const blockerKey = opsState.selectedOpsReleaseBlockerKey;
  const checkKey = opsState.selectedOpsReleaseBlockerCheckKey;
  if (!blockerKey) {
    dom.opsReleaseWorkspaceDetails?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  const selector = checkKey
    ? `[data-release-blocker-key="${blockerKey}"][data-release-blocker-check-key="${checkKey}"]`
    : `[data-release-blocker-key="${blockerKey}"]`;
  const target = dom.opsReleaseWorkspaceDetails?.querySelector(selector) || dom.opsReleaseWorkspaceDetails;
  target?.classList?.remove("is-highlighted");
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
  target?.classList?.add("is-highlighted");
  if (typeof window !== "undefined") {
    window.setTimeout(() => {
      target?.classList?.remove("is-highlighted");
    }, 1400);
  }
}
