// Ops runtime handlers extracted from app.js so shell orchestration stays thin.

var OpsRuntime = (() => {
  const dom = OpsDOM;
  const {
    api,
    setBusy,
    parseIssueCodes
  } = UIShared;
  const {
    currentOpsNavigationContext,
    syncOpsNavigationContext,
    refreshOpsReleaseWorkspace,
    refreshOpsCrossPackQuality,
    refreshOpsAlerts,
    refreshOpsSurface,
    refreshOpsReleaseFlow,
    refreshOpsLearnedFlow
  } = OpsRefreshRuntime;
  const { renderOpsSurface } = OpsRenderRuntime;
  const {
    submitPromotionDecision,
    submitRerankerPromotionDecision,
    submitProviderRollout,
    runDataIntegrityRepair,
    submitAssistedGateConfig,
    submitAssistedRerankConfig,
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
    grantOpsSubscription,
    changeOpsSubscriptionState,
    grantOpsWallet,
    debitOpsWallet,
    reconcileOpsSubscription,
    retryOpsSubscriptionPayment,
    replayOpsBillingEvent,
    updateSelectedOpsAlertStatus,
    openSelectedOpsAlertInvestigation,
    followOpsNavigationRecommendation,
    runOpsInvestigation,
    exportOpsInvestigationTrace,
    revokeOpsEntitlement
  } = OpsActionsRuntime;

  let opsEventsBound = false;
  let opsRuntimeInitialized = false;

async function submitOpsReviewCapture() {
  if (!opsState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节。");
    return;
  }
  const reviewerId = dom.opsReviewerId?.value.trim() || "ops_web";
  const issueCodes = parseIssueCodes(dom.opsReviewIssueCodes?.value || "");
  if (!reviewerId || !issueCodes.length) {
    alert("请至少填写 reviewer_id 和 issue codes。");
    return;
  }
  const restore = setBusy(dom.opsSubmitReviewCapture, "提交中…");
  try {
    const result = await api("/v1/ops/review-samples", {
      method: "POST",
      body: JSON.stringify({
        chapter_id: opsState.opsReviewCaptureTarget.chapter_id,
        world_id: opsState.opsReviewCaptureTarget.world_id,
        world_version_id: opsState.opsReviewCaptureTarget.world_version_id,
        session_id: opsState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        score_overall: Number(dom.opsReviewScore?.value || 0.65),
        issue_codes: issueCodes,
        freeform_notes: dom.opsReviewNotes?.value || "",
        would_continue: Boolean(dom.opsReviewWouldContinue?.checked),
        would_pay: Boolean(dom.opsReviewWouldPay?.checked),
      }),
    });
    opsState.opsLastActionImpact = result.impact_receipt || null;
    opsState.opsReviewCaptureTarget = null;
    if (dom.opsReviewNotes) dom.opsReviewNotes.value = "";
    if (dom.opsReviewIssueCodes) dom.opsReviewIssueCodes.value = "";
    await refreshOpsSurface({ preserveLastActionImpact: true });
  } catch (error) {
    alert(`提交 Human Review 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsPreferenceCapture() {
  if (!opsState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 preference 的上下文。");
    return;
  }
  const reviewerId = dom.opsReviewerId?.value.trim() || "ops_web";
  const leftRevisionId = dom.opsPreferenceLeftRevisionId?.value.trim() || "";
  const rightRevisionId = dom.opsPreferenceRightRevisionId?.value.trim() || "";
  const preferredRevisionId = dom.opsPreferencePreferredRevisionId?.value.trim() || "";
  if (!reviewerId || !leftRevisionId || !rightRevisionId || !preferredRevisionId) {
    alert("请填写 reviewer_id、left/right revision id 和 preferred revision id。");
    return;
  }
  const restore = setBusy(dom.opsSubmitPreferenceCapture, "提交中…");
  try {
    await api("/v1/ops/preference-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: opsState.opsReviewCaptureTarget.world_id,
        world_version_id: opsState.opsReviewCaptureTarget.world_version_id,
        chapter_id: opsState.opsReviewCaptureTarget.chapter_id,
        session_id: opsState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        left_revision_id: leftRevisionId,
        right_revision_id: rightRevisionId,
        preferred_revision_id: preferredRevisionId,
        freeform_notes: dom.opsPreferenceNotes?.value || "",
        linked_issue_codes: parseIssueCodes(dom.opsReviewIssueCodes?.value || ""),
        preference_strength: dom.opsPreferenceStrength?.value || "medium",
      }),
    });
    if (dom.opsPreferenceNotes) dom.opsPreferenceNotes.value = "";
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Preference 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsRankingCapture() {
  if (!opsState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 ranking 的上下文。");
    return;
  }
  const reviewerId = dom.opsReviewerId?.value.trim() || "ops_web";
  const rankedRevisionIds = (dom.opsRankingRevisionIds?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!reviewerId || rankedRevisionIds.length < 2) {
    alert("请填写 reviewer_id，且 ranked revision ids 至少包含两个。");
    return;
  }
  const restore = setBusy(dom.opsSubmitRankingCapture, "提交中…");
  try {
    await api("/v1/ops/ranking-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: opsState.opsReviewCaptureTarget.world_id,
        world_version_id: opsState.opsReviewCaptureTarget.world_version_id,
        chapter_id: opsState.opsReviewCaptureTarget.chapter_id,
        session_id: opsState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        ranked_revision_ids: rankedRevisionIds,
        freeform_notes: dom.opsRankingNotes?.value || "",
        linked_issue_codes: parseIssueCodes(dom.opsReviewIssueCodes?.value || ""),
      }),
    });
    if (dom.opsRankingNotes) dom.opsRankingNotes.value = "";
    if (dom.opsRankingRevisionIds) dom.opsRankingRevisionIds.value = "";
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Ranking 失败：${error.message}`);
  } finally {
    restore();
  }
}

function bindOpsEvents() {
  if (opsEventsBound) return;
  opsEventsBound = true;

  dom.opsAccountId?.addEventListener("change", () => {
    if (dom.opsInvestigationAccountId && !dom.opsInvestigationAccountId.value.trim()) {
      dom.opsInvestigationAccountId.value = dom.opsAccountId.value.trim();
    }
    if (dom.opsAlertAccountId && !dom.opsAlertAccountId.value.trim()) {
      dom.opsAlertAccountId.value = dom.opsAccountId.value.trim();
    }
    if (dom.opsNavAccountId && !dom.opsNavAccountId.value.trim()) {
      dom.opsNavAccountId.value = dom.opsAccountId.value.trim();
    }
  });
  dom.opsAlertAccountId?.addEventListener("change", async () => {
    if (dom.opsNavAccountId && !dom.opsNavAccountId.value.trim()) {
      dom.opsNavAccountId.value = dom.opsAlertAccountId.value.trim();
    }
    await refreshOpsAlerts();
    renderOpsSurface();
  });
  dom.opsAlertStatusFilter?.addEventListener("change", async () => {
    await refreshOpsAlerts();
    renderOpsSurface();
  });
  dom.opsAlertSeverityFilter?.addEventListener("change", async () => {
    await refreshOpsAlerts();
    renderOpsSurface();
  });
  dom.opsRefresh?.addEventListener("click", refreshOpsSurface);
  dom.opsRefreshCrossPackQuality?.addEventListener("click", async () => {
    try {
      await refreshOpsCrossPackQuality({
        validateStrategyBundle: Boolean(dom.opsCrossPackValidateStrategyBundle?.checked),
        strategyBundleId: (dom.opsCrossPackStrategyBundleId?.value || "").trim(),
        weakestLimit: (dom.opsCrossPackWeakestLimit?.value || "").trim() || "3",
      });
      renderOpsSurface();
    } catch (error) {
      alert(`刷新策略包验证失败：${error.message}`);
    }
  });
  dom.opsSyncNavigation?.addEventListener("click", async () => {
    try {
      syncOpsNavigationContext(currentOpsNavigationContext(), { preserveExisting: false });
      await refreshOpsSurface({ scopes: ["account", "review_release", "alerts", "navigation"] });
    } catch (error) {
      alert(`同步 Ops context 失败：${error.message}`);
    }
  });
  dom.opsFollowRecommendation?.addEventListener("click", async () => {
    try {
      await followOpsNavigationRecommendation();
    } catch (error) {
      alert(`执行推荐升级路径失败：${error.message}`);
    }
  });
  dom.opsNavAccountId?.addEventListener("change", () => {
    if (dom.opsAccountId) {
      dom.opsAccountId.value = dom.opsNavAccountId.value.trim();
    }
  });
  dom.opsNavWorldId?.addEventListener("change", () => {
    opsState.selectedOpsWorldId = (dom.opsNavWorldId?.value || "").trim() || null;
    if (dom.opsReleaseWorldId) {
      dom.opsReleaseWorldId.value = dom.opsNavWorldId.value.trim();
    }
  });
  dom.opsNavCaseId?.addEventListener("change", () => {
    if (dom.opsGovernanceCaseId) {
      dom.opsGovernanceCaseId.value = dom.opsNavCaseId.value.trim();
    }
  });
  dom.opsRefreshReleaseWorkspace?.addEventListener("click", async () => {
    try {
      await refreshOpsReleaseWorkspace();
      renderOpsSurface();
    } catch (error) {
      alert(`刷新 release workspace 失败：${error.message}`);
    }
  });
  dom.opsReleaseWorldId?.addEventListener("change", async () => {
    opsState.selectedOpsWorldId = (dom.opsReleaseWorldId?.value || "").trim() || null;
    if (dom.opsNavWorldId) {
      dom.opsNavWorldId.value = dom.opsReleaseWorldId.value.trim();
    }
    await refreshOpsReleaseWorkspace();
    renderOpsSurface();
  });
  dom.opsCreateRuntimeBackup?.addEventListener("click", createRuntimeBackup);
  dom.opsRestoreRuntimeBackup?.addEventListener("click", restoreRuntimeBackup);
  dom.opsRunRecoveryDrill?.addEventListener("click", runRecoveryDrill);
  dom.opsRequestRuntimeRestore?.addEventListener("click", requestRuntimeRestore);
  dom.opsApproveRuntimeRestore?.addEventListener("click", approveRuntimeRestore);
  dom.opsRevokeRuntimeRestore?.addEventListener("click", revokeRuntimeRestore);
  dom.opsExecuteRuntimeRestore?.addEventListener("click", executeRuntimeRestore);
  dom.opsRunDataIntegrityDryRun?.addEventListener("click", () => runDataIntegrityRepair(false));
  dom.opsApplyDataIntegrityRepair?.addEventListener("click", () => runDataIntegrityRepair(true));
  dom.opsRetryAsyncJob?.addEventListener("click", retryAsyncJob);
  dom.opsResumeAsyncJob?.addEventListener("click", resumeAsyncJob);
  dom.opsRecoverAsyncJobs?.addEventListener("click", recoverAsyncJobIncidents);
  dom.opsEnforceAsyncRetention?.addEventListener("click", enforceAsyncJobRetention);
  dom.opsRunColdStartDrill?.addEventListener("click", runColdStartRecoveryDrill);
  dom.opsExportHandoffBundle?.addEventListener("click", exportAsyncJobHandoffBundle);
  dom.opsAcknowledgeAsyncJob?.addEventListener("click", acknowledgeAsyncJob);
  dom.opsShipRemoteArtifacts?.addEventListener("click", shipRemoteArtifacts);
  dom.opsEscalateHandoffSla?.addEventListener("click", escalateHandoffSla);
  dom.opsEnqueueNotificationRetry?.addEventListener("click", enqueueNotificationRetry);
  dom.opsProcessNotificationRetry?.addEventListener("click", processNotificationRetry);
  dom.opsGrantSubscription?.addEventListener("click", grantOpsSubscription);
  dom.opsChangeSubscriptionState?.addEventListener("click", changeOpsSubscriptionState);
  dom.opsGrantWallet?.addEventListener("click", grantOpsWallet);
  dom.opsDebitWallet?.addEventListener("click", debitOpsWallet);
  dom.opsRevokeEntitlement?.addEventListener("click", revokeOpsEntitlement);
  dom.opsReconcileSubscription?.addEventListener("click", reconcileOpsSubscription);
  dom.opsRetrySubscriptionPayment?.addEventListener("click", retryOpsSubscriptionPayment);
  dom.opsReplayBillingEvent?.addEventListener("click", replayOpsBillingEvent);
  dom.opsRefreshAlerts?.addEventListener("click", async () => {
    try {
      await refreshOpsAlerts();
      renderOpsSurface();
    } catch (error) {
      alert(`刷新 alerts 失败：${error.message}`);
    }
  });
  dom.opsAcknowledgeAlert?.addEventListener("click", async () => {
    try {
      await updateSelectedOpsAlertStatus("acknowledged");
    } catch (error) {
      alert(`ack alert 失败：${error.message}`);
    }
  });
  dom.opsResolveAlert?.addEventListener("click", async () => {
    try {
      await updateSelectedOpsAlertStatus("resolved");
    } catch (error) {
      alert(`resolve alert 失败：${error.message}`);
    }
  });
  dom.opsProviderCandidateCanary?.addEventListener("click", () => submitProviderRollout("candidate", "canary"));
  dom.opsProviderCandidateActivate?.addEventListener("click", () => submitProviderRollout("candidate", "activate"));
  dom.opsProviderCandidateRollback?.addEventListener("click", () => submitProviderRollout("candidate", "rollback"));
  dom.opsProviderRendererCanary?.addEventListener("click", () => submitProviderRollout("renderer", "canary"));
  dom.opsProviderRendererActivate?.addEventListener("click", () => submitProviderRollout("renderer", "activate"));
  dom.opsProviderRendererRollback?.addEventListener("click", () => submitProviderRollout("renderer", "rollback"));
  dom.opsOpenAlertInvestigation?.addEventListener("click", async () => {
    try {
      await openSelectedOpsAlertInvestigation();
    } catch (error) {
      alert(`打开 alert investigation 失败：${error.message}`);
    }
  });
  dom.opsRunInvestigation?.addEventListener("click", async () => {
    try {
      await runOpsInvestigation();
    } catch (error) {
      alert(`运行统一排查失败：${error.message}`);
    }
  });
  dom.opsExportInvestigationTrace?.addEventListener("click", async () => {
    try {
      await exportOpsInvestigationTrace();
    } catch (error) {
      alert(`导出 investigation trace 失败：${error.message}`);
    }
  });
  dom.opsCreateGovernanceCase?.addEventListener("click", createGovernanceCase);
  dom.opsAssignGovernanceCase?.addEventListener("click", assignGovernanceCase);
  dom.opsAddGovernanceEvidence?.addEventListener("click", addGovernanceEvidence);
  dom.opsUpdateGovernanceCase?.addEventListener("click", updateGovernanceCaseStatus);
  dom.opsApplyGovernanceRestriction?.addEventListener("click", applyGovernanceRestriction);
  dom.opsReleaseGovernanceRestriction?.addEventListener("click", releaseGovernanceRestriction);
  dom.opsExportGovernanceAudit?.addEventListener("click", refreshGovernanceAuditExport);
  dom.opsSubmitReviewCapture?.addEventListener("click", submitOpsReviewCapture);
  dom.opsSubmitPreferenceCapture?.addEventListener("click", submitOpsPreferenceCapture);
  dom.opsSubmitRankingCapture?.addEventListener("click", submitOpsRankingCapture);
  dom.opsApprovePromotion?.addEventListener("click", () => submitPromotionDecision("approve"));
  dom.opsRevokePromotion?.addEventListener("click", () => submitPromotionDecision("revoke"));
  dom.opsApproveRerankerPromotion?.addEventListener("click", () => submitRerankerPromotionDecision("approve"));
  dom.opsRevokeRerankerPromotion?.addEventListener("click", () => submitRerankerPromotionDecision("revoke"));
  dom.opsSetAssistedShadow?.addEventListener("click", () => submitAssistedGateConfig("shadow_only", true));
  dom.opsSetAssistedActive?.addEventListener("click", () => submitAssistedGateConfig("assisted_gate", true));
  dom.opsDisableAssistedGate?.addEventListener("click", () => submitAssistedGateConfig("shadow_only", false));
  dom.opsSetAssistedRerankShadow?.addEventListener("click", () => submitAssistedRerankConfig("shadow_only", true));
  dom.opsSetAssistedRerankActive?.addEventListener("click", () => submitAssistedRerankConfig("assisted_rerank", true));
  dom.opsDisableAssistedRerank?.addEventListener("click", () => submitAssistedRerankConfig("shadow_only", false));
  dom.opsRunEvaluatorTraining?.addEventListener("click", () => runLearnedTraining(["evaluator"]));
  dom.opsRunRerankerTraining?.addEventListener("click", () => runLearnedTraining(["reranker"]));
  dom.opsRunBothTraining?.addEventListener("click", () => runLearnedTraining(["evaluator", "reranker"]));
}

function initializeOpsRuntime() {
  if (opsRuntimeInitialized) return;
  opsRuntimeInitialized = true;
  bindOpsEvents();
}

  return {
    bindOpsEvents,
    initializeOpsRuntime,
    submitOpsReviewCapture,
    submitOpsPreferenceCapture,
    submitOpsRankingCapture
  };
})();
