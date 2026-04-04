// Ops action handlers extracted from app.js.

function opsGovernanceHeaders() {
  const reviewerId = els.opsGovernanceReviewerId?.value.trim() || "ops_web";
  return {
    "X-NarrativeOS-Actor-Id": reviewerId,
    "X-NarrativeOS-Actor-Role": "reviewer",
    ...(els.opsAccountId?.value.trim() ? { "X-NarrativeOS-Account-Id": els.opsAccountId.value.trim() } : {}),
  };
}

function opsRestoreHeaders(actorId, actorRole) {
  return {
    "X-NarrativeOS-Actor-Id": actorId,
    "X-NarrativeOS-Actor-Role": actorRole,
  };
}


async function submitPromotionDecision(action) {
  const reviewerId = els.opsPromotionReviewerId?.value.trim() || "ops_web";
  const reason = els.opsPromotionReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 promotion reviewer_id 和 reason。");
    return;
  }
  const button = action === "approve" ? els.opsApprovePromotion : els.opsRevokePromotion;
  const restore = setBusy(button, action === "approve" ? "批准中…" : "撤销中…");
  try {
    appState.opsLearnedPromotion = await api(
      action === "approve" ? "/v1/ops/learned-promotion/approve" : "/v1/ops/learned-promotion/revoke",
      {
        method: "POST",
        body: JSON.stringify({
          reviewer_id: reviewerId,
          reason,
        }),
      }
    );
    appState.opsLastActionImpact = null;
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`更新 promotion 状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitRerankerPromotionDecision(action) {
  const reviewerId = els.opsRerankerPromotionReviewerId?.value.trim() || "ops_web";
  const reason = els.opsRerankerPromotionReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 reranker promotion reviewer_id 和 reason。");
    return;
  }
  const button = action === "approve" ? els.opsApproveRerankerPromotion : els.opsRevokeRerankerPromotion;
  const restore = setBusy(button, action === "approve" ? "批准中…" : "撤销中…");
  try {
    appState.opsLearnedRerankerPromotion = await api(
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
    appState.opsLastActionImpact = null;
    await refreshOpsJobsFlow();
  } catch (error) {
    alert(`更新 reranker promotion 状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitProviderRollout(track, action) {
  const reviewerId = els.opsProviderRolloutReviewerId?.value.trim() || "ops_web";
  const reason = els.opsProviderRolloutReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 provider rollout reviewer_id 和 reason。");
    return;
  }
  const bucketPercentage = Number(els.opsProviderRolloutBucket?.value || 0);
  const worldAllowlist = (els.opsProviderRolloutWorldAllowlist?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  let button = els.opsProviderCandidateCanary;
  if (track === "candidate" && action === "activate") button = els.opsProviderCandidateActivate;
  if (track === "candidate" && action === "rollback") button = els.opsProviderCandidateRollback;
  if (track === "renderer" && action === "canary") button = els.opsProviderRendererCanary;
  if (track === "renderer" && action === "activate") button = els.opsProviderRendererActivate;
  if (track === "renderer" && action === "rollback") button = els.opsProviderRendererRollback;
  const restore = setBusy(button, action === "rollback" ? "回滚中…" : "保存中…");
  try {
    appState.opsProviderRollout = await api(`/v1/ops/provider-rollout/${encodeURIComponent(track)}/${encodeURIComponent(action)}`, {
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
  const rawActions = (els.opsDataIntegrityActions?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const button = apply ? els.opsApplyDataIntegrityRepair : els.opsRunDataIntegrityDryRun;
  const restore = setBusy(button, apply ? "修复中…" : "扫描中…");
  try {
    appState.opsDataIntegrityRepair = await api("/v1/ops/data-integrity/repair", {
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
  const reviewerId = els.opsAssistedGateReviewerId?.value.trim() || "ops_web";
  const reason = els.opsAssistedGateReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 assisted gate reviewer_id 和 reason。");
    return;
  }
  const button = enabled
    ? (mode === "assisted_gate" ? els.opsSetAssistedActive : els.opsSetAssistedShadow)
    : els.opsDisableAssistedGate;
  const restore = setBusy(button, enabled ? "保存中…" : "关闭中…");
  try {
    appState.opsLearnedAssistedGate = await api("/v1/ops/learned-assisted-gate/configure", {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
        enabled,
        mode,
        bucket_percentage: Number(els.opsAssistedGateBucket?.value || 0),
        confidence_threshold: Number(els.opsAssistedGateConfidence?.value || 0.9),
        min_example_count: 3,
        min_high_confidence_blocks: 2,
        required_block_share: 0.5,
        world_allowlist: (els.opsAssistedGateWorldAllowlist?.value || "")
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
  const reviewerId = els.opsAssistedRerankReviewerId?.value.trim() || "ops_web";
  const reason = els.opsAssistedRerankReason?.value.trim() || "";
  if (!reviewerId || !reason) {
    alert("请填写 assisted rerank reviewer_id 和 reason。");
    return;
  }
  const button = enabled
    ? (mode === "assisted_rerank" ? els.opsSetAssistedRerankActive : els.opsSetAssistedRerankShadow)
    : els.opsDisableAssistedRerank;
  const restore = setBusy(button, enabled ? "保存中…" : "关闭中…");
  try {
    appState.opsLearnedAssistedRerank = await api("/v1/ops/learned-assisted-rerank/configure", {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        reason,
        enabled,
        mode,
        bucket_percentage: Number(els.opsAssistedRerankBucket?.value || 0),
        confidence_threshold: Number(els.opsAssistedRerankConfidence?.value || 0.65),
        candidate_window: Number(els.opsAssistedRerankCandidateWindow?.value || 3),
        max_score_gap: Number(els.opsAssistedRerankMaxScoreGap?.value || 0.08),
        world_allowlist: (els.opsAssistedRerankWorldAllowlist?.value || "")
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
      ? (els.opsPromotionReviewerId?.value.trim() || "ops_web")
      : (els.opsRerankerPromotionReviewerId?.value.trim() || "ops_web");
  const reason =
    track === "evaluator"
      ? (els.opsPromotionReason?.value.trim() || "")
      : (els.opsRerankerPromotionReason?.value.trim() || "");
  if (!reviewerId || !reason) {
    alert("请先填写对应 track 的 reviewer_id 和 reason。");
    return;
  }
  const endpoint =
    action === "activate"
      ? `/v1/ops/learned-rollout/${encodeURIComponent(track)}/activate`
      : `/v1/ops/learned-rollout/${encodeURIComponent(track)}/rollback`;
  try {
    appState.opsLearnedRollout = await api(endpoint, {
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
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const targetType = els.opsGovernanceTargetType?.value || "account";
  const targetId = (els.opsGovernanceTargetId?.value || "").trim() || (targetType === "account" ? accountId : "");
  const summary = (els.opsGovernanceSummaryInput?.value || "").trim();
  const reviewerId = (els.opsGovernanceReviewerId?.value || "ops_web").trim();
  if (!targetId || !summary) {
    alert("请填写 governance case 的 target_id 和 summary。");
    return;
  }
  const restore = setBusy(els.opsCreateGovernanceCase, "创建中…");
  try {
    const payload = await api("/v1/ops/governance/cases", {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        case_type: els.opsGovernanceCaseType?.value || "rights",
        target_type: targetType,
        target_id: targetId,
        account_id: accountId || undefined,
        world_version_id: targetType === "world_version" ? targetId : undefined,
        session_id: targetType === "session" ? targetId : undefined,
        entitlement_id: targetType === "entitlement" ? targetId : undefined,
        severity: els.opsGovernanceSeverity?.value || "medium",
        summary,
        description: (els.opsGovernanceNotes?.value || "").trim() || undefined,
        reviewer_id: reviewerId,
        owner_id: (els.opsGovernanceOwnerId?.value || "").trim() || reviewerId,
        due_at: (els.opsGovernanceDueAt?.value || "").trim() || undefined,
        disposition: (els.opsGovernanceDisposition?.value || "").trim() || undefined,
        policy_labels: parseTagList(els.opsGovernancePolicyLabels?.value || ""),
        evidence_refs: (els.opsGovernanceEvidencePreview?.value || "").trim()
          ? [
              {
                title: (els.opsGovernanceEvidenceTitle?.value || "").trim() || "manual_note",
                preview: (els.opsGovernanceEvidencePreview?.value || "").trim(),
                kind: "note",
              },
            ]
          : [],
      }),
    });
    if (els.opsGovernanceCaseId) els.opsGovernanceCaseId.value = payload.case?.case_id || "";
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
  const caseId = (els.opsGovernanceCaseId?.value || "").trim();
  if (!caseId) {
    alert("先选择或填写一个 governance case id。");
    return;
  }
  const restore = setBusy(els.opsUpdateGovernanceCase, "更新中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/status`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        status: els.opsGovernanceStatus?.value || "in_review",
        reviewer_id: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        resolution_notes: (els.opsGovernanceNotes?.value || "").trim() || undefined,
        disposition: (els.opsGovernanceDisposition?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsJobsFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    alert(`更新 governance case 状态失败：${error.message}`);
  } finally {
    restore();
  }
}

async function applyGovernanceRestriction() {
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const reviewerId = (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web";
  const summary = (els.opsGovernanceSummaryInput?.value || "").trim();
  if (!accountId || !summary) {
    alert("请填写 account_id 和 restriction summary。");
    return;
  }
  const restore = setBusy(els.opsApplyGovernanceRestriction, "施加中…");
  try {
    const payload = await api("/v1/ops/governance/restrictions", {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        restriction_type: els.opsGovernanceRestrictionType?.value || "account_hold",
        account_id: accountId,
        case_type: els.opsGovernanceCaseType?.value || "abuse",
        severity: els.opsGovernanceSeverity?.value || "high",
        summary,
        description: (els.opsGovernanceNotes?.value || "").trim() || undefined,
        reviewer_id: reviewerId,
        expires_at: (els.opsGovernanceRestrictionExpiresAt?.value || "").trim() || undefined,
        restriction_reason: (els.opsGovernanceNotes?.value || "").trim() || summary,
      }),
    });
    await refreshOpsLearnedFlow();
    if (payload.case?.case_id) {
      if (els.opsGovernanceCaseId) els.opsGovernanceCaseId.value = payload.case.case_id;
      await openGovernanceCaseDetail(payload.case.case_id);
    }
  } catch (error) {
    alert(`施加 restriction 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function releaseGovernanceRestriction() {
  const restrictionId = (els.opsGovernanceCaseId?.value || "").trim();
  if (!restrictionId) {
    alert("先在 Case ID 中填入 restriction_id。");
    return;
  }
  const restore = setBusy(els.opsReleaseGovernanceRestriction, "释放中…");
  try {
    const payload = await api(`/v1/ops/governance/restrictions/${encodeURIComponent(restrictionId)}/release`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        reviewer_id: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        release_reason: (els.opsGovernanceNotes?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsJobsFlow();
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
  const caseId = (els.opsGovernanceCaseId?.value || "").trim();
  const ownerId = (els.opsGovernanceOwnerId?.value || "").trim();
  if (!caseId || !ownerId) {
    alert("先填写 case id 和 owner id。");
    return;
  }
  const restore = setBusy(els.opsAssignGovernanceCase, "分配中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/assign`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        owner_id: ownerId,
        reviewer_id: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        due_at: (els.opsGovernanceDueAt?.value || "").trim() || undefined,
        note: (els.opsGovernanceNotes?.value || "").trim() || undefined,
      }),
    });
    await refreshOpsJobsFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    alert(`分配 governance case 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function addGovernanceEvidence() {
  const caseId = (els.opsGovernanceCaseId?.value || "").trim();
  const preview = (els.opsGovernanceEvidencePreview?.value || "").trim();
  if (!caseId || !preview) {
    alert("先填写 case id 和 evidence preview。");
    return;
  }
  const restore = setBusy(els.opsAddGovernanceEvidence, "记录中…");
  try {
    await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}/evidence`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        reviewer_id: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        title: (els.opsGovernanceEvidenceTitle?.value || "").trim() || "manual_note",
        preview,
        kind: "note",
      }),
    });
    await refreshOpsLearnedFlow();
    await openGovernanceCaseDetail(caseId);
  } catch (error) {
    alert(`添加 governance evidence 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function refreshGovernanceAuditExport() {
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  if (!accountId) return;
  try {
    appState.opsGovernanceExport = await api(`/v1/ops/export/governance-audit?account_id=${encodeURIComponent(accountId)}`);
    renderOpsSurface();
  } catch (error) {
    alert(`刷新治理导出失败：${error.message}`);
  }
}

async function createRuntimeBackup() {
  const restore = setBusy(els.opsCreateRuntimeBackup, "备份中…");
  try {
    const payload = await api("/v1/ops/jobs/runtime-backups", {
      method: "POST",
      body: JSON.stringify({
        label: (els.opsBackupLabel?.value || "").trim() || undefined,
        requested_by: (els.opsRestoreRequesterId?.value || "ops_web").trim() || "ops_web",
        account_id: els.opsAccountId?.value.trim() || activeReaderId(),
      }),
    });
    await refreshOpsJobsFlow();
    const latestBackupJob = payload.job?.job_id
      ? appState.opsAsyncJobs.find((item) => item.job_id === payload.job.job_id)
      : latestAsyncJob("runtime_backup");
    if (els.opsRestorePath && latestBackupJob?.result_summary?.backup_path) {
      els.opsRestorePath.value = latestBackupJob.result_summary.backup_path;
    }
  } catch (error) {
    alert(`创建 runtime backup 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function restoreRuntimeBackup() {
  const backupPath = (els.opsRestorePath?.value || "").trim();
  if (!backupPath) {
    alert("请先填写 backup path。");
    return;
  }
  const restore = setBusy(els.opsRestoreRuntimeBackup, "恢复中…");
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
  const backupPath = (els.opsRestorePath?.value || "").trim() || undefined;
  const restore = setBusy(els.opsRunRecoveryDrill, "演练中…");
  try {
    const payload = await api("/v1/ops/recovery-drill", {
      method: "POST",
      body: JSON.stringify({
        backup_path: backupPath,
      }),
    });
    appState.opsRecoveryDrillResult = payload.recovery_drill || null;
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`执行 recovery drill 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function requestRuntimeRestore() {
  const backupPath = (els.opsRestorePath?.value || "").trim();
  const requestedBy = (els.opsRestoreRequesterId?.value || "").trim() || "ops_web";
  const reason = (els.opsRestoreReason?.value || "").trim();
  if (!backupPath || !reason) {
    alert("请填写 restore backup path 和 restore reason。");
    return;
  }
  const restore = setBusy(els.opsRequestRuntimeRestore, "请求中…");
  try {
    const payload = await api("/v1/ops/runtime-restore/request", {
      method: "POST",
      headers: opsRestoreHeaders(requestedBy, "ops"),
      body: JSON.stringify({
        backup_path: backupPath,
        reason,
      }),
    });
    if (els.opsRestoreRequestId && payload.restore_request?.request_id) {
      els.opsRestoreRequestId.value = payload.restore_request.request_id;
    }
    await refreshOpsSurface({ scopes: ["runtime"] });
  } catch (error) {
    alert(`创建 restore request 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function approveRuntimeRestore() {
  const requestId = (els.opsRestoreRequestId?.value || "").trim();
  const approverId = (els.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  const reason = (els.opsRestoreReason?.value || "").trim();
  if (!requestId || !reason) {
    alert("请填写 restore request id 和 restore reason。");
    return;
  }
  const restore = setBusy(els.opsApproveRuntimeRestore, "批准中…");
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
  const requestId = (els.opsRestoreRequestId?.value || "").trim();
  const reviewerId = (els.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  const reason = (els.opsRestoreReason?.value || "").trim();
  if (!requestId || !reason) {
    alert("请填写 restore request id 和 restore reason。");
    return;
  }
  const restore = setBusy(els.opsRevokeRuntimeRestore, "撤销中…");
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
  const requestId = (els.opsRestoreRequestId?.value || "").trim();
  const executorId = (els.opsRestoreApproverId?.value || "").trim() || "ops_approver";
  if (!requestId) {
    alert("请填写 restore request id。");
    return;
  }
  const restore = setBusy(els.opsExecuteRuntimeRestore, "执行中…");
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
  const jobId = (els.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(els.opsRetryAsyncJob, "重试中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const jobId = (els.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(els.opsResumeAsyncJob, "恢复中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/resume`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const restore = setBusy(els.opsRecoverAsyncJobs, "恢复中…");
  try {
    await api("/v1/ops/jobs/recover-incidents", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const restore = setBusy(els.opsEnforceAsyncRetention, "清理中…");
  try {
    const payload = await api("/v1/ops/jobs/enforce-retention", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const restore = setBusy(els.opsRunColdStartDrill, "演练中…");
  try {
    const payload = await api("/v1/ops/jobs/cold-start-drill", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const restore = setBusy(els.opsExportHandoffBundle, "导出中…");
  try {
    const payload = await api("/v1/ops/jobs/handoff-bundle/export", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        limit: 20,
      }),
    });
    appState.opsAsyncJobHandoffBundle = payload;
    renderOpsSurface();
    alert(`Handoff bundle 已导出：${payload.export_path || "-"}`);
  } catch (error) {
    alert(`导出 handoff bundle 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function acknowledgeAsyncJob() {
  const jobId = (els.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(els.opsAcknowledgeAsyncJob, "确认中…");
  try {
    await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        note: (els.opsAsyncJobNote?.value || "").trim() || undefined,
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
  const jobId = (els.opsAsyncJobId?.value || "").trim();
  if (!jobId) {
    alert("请先填写 async job id。");
    return;
  }
  const restore = setBusy(els.opsShipRemoteArtifacts, "运输中…");
  try {
    const payload = await api(`/v1/ops/jobs/${encodeURIComponent(jobId)}/ship-remote`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const restore = setBusy(els.opsEscalateHandoffSla, "升级中…");
  try {
    const payload = await api("/v1/ops/jobs/handoff-sla/escalate", {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  const receiptId = (els.opsNotificationReceiptId?.value || "").trim();
  if (!receiptId) {
    alert("请先填写 notification receipt id。");
    return;
  }
  const restore = setBusy(els.opsEnqueueNotificationRetry, "入队中…");
  try {
    const payload = await api("/v1/ops/jobs/notification-retry-queue/enqueue", {
      method: "POST",
      body: JSON.stringify({
        event_id: Number(receiptId),
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
        note: (els.opsAsyncJobNote?.value || "").trim() || undefined,
      }),
    });
    if (els.opsNotificationReceiptId) {
      els.opsNotificationReceiptId.value = payload.retry?.retry_id || receiptId;
    }
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`入队 notification retry 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function processNotificationRetry() {
  const retryId = (els.opsNotificationReceiptId?.value || "").trim();
  if (!retryId) {
    alert("请先填写 notification retry id。");
    return;
  }
  const restore = setBusy(els.opsProcessNotificationRetry, "处理中…");
  try {
    await api(`/v1/ops/jobs/notification-retry-queue/${encodeURIComponent(retryId)}/process`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
      ? els.opsRunBothTraining
      : tracks[0] === "evaluator"
        ? els.opsRunEvaluatorTraining
        : els.opsRunRerankerTraining;
  const restore = setBusy(button, "运行中…");
  try {
    appState.opsLearnedTrainingResult = await api("/v1/ops/jobs/learned-training", {
      method: "POST",
      body: JSON.stringify({
        tracks,
        requested_by: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
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
  appState.opsGovernanceDetail = await api(`/v1/ops/governance/cases/${encodeURIComponent(caseId)}`, {
    headers: opsGovernanceHeaders(),
  });
  applyGovernanceCasePrefill({
    case_id: appState.opsGovernanceDetail.case_id,
    case_type: appState.opsGovernanceDetail.case_type,
    target_type: appState.opsGovernanceDetail.target_type,
    target_id: appState.opsGovernanceDetail.target_id,
    severity: appState.opsGovernanceDetail.severity,
    reviewer_id: appState.opsGovernanceDetail.reviewer_id,
    owner_id: appState.opsGovernanceDetail.workflow_summary?.owner_id || appState.opsGovernanceDetail.owner_id,
    summary: appState.opsGovernanceDetail.summary,
    description: appState.opsGovernanceDetail.resolution_notes || appState.opsGovernanceDetail.description,
    status: appState.opsGovernanceDetail.status,
    account_id: appState.opsGovernanceDetail.account_id,
    due_at: appState.opsGovernanceDetail.workflow_summary?.due_at || appState.opsGovernanceDetail.due_at,
    disposition: appState.opsGovernanceDetail.workflow_summary?.disposition || appState.opsGovernanceDetail.disposition,
    policy_labels: appState.opsGovernanceDetail.workflow_summary?.policy_labels || appState.opsGovernanceDetail.policy_labels || [],
  });
  renderOpsSurface();
}

async function escalateSupportIssue(issue) {
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  if (!accountId || !issue?.issue_id) {
    alert("缺少 account_id 或 support issue id。");
    return;
  }
  const restore = setBusy(els.opsCreateGovernanceCase, "升级中…");
  try {
    const payload = await api(`/v1/ops/accounts/${encodeURIComponent(accountId)}/governance/escalate-support`, {
      method: "POST",
      headers: opsGovernanceHeaders(),
      body: JSON.stringify({
        issue_id: issue.issue_id,
        reviewer_id: (els.opsGovernanceReviewerId?.value || "ops_web").trim() || "ops_web",
      }),
    });
    appState.opsGovernanceDetail = payload.case || null;
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
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const tierId = els.opsTierId?.value || "play_pass";
  const restore = setBusy(els.opsGrantSubscription, "授予中…");
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
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const status = els.opsSubscriptionStatus?.value || "active";
  const current = appState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可更新。");
    return;
  }
  const restore = setBusy(els.opsChangeSubscriptionState, "更新中…");
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
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const walletType = els.opsWalletType?.value || "story_credits";
  const amount = Number(els.opsWalletAmount?.value || 10);
  const restore = setBusy(els.opsGrantWallet, "充值中…");
  try {
    await api("/v1/ops/wallets/grant", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        wallet_type: walletType,
        amount,
        tier_id: els.opsTierId?.value || null,
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
  const accountId = els.opsAccountId?.value.trim() || activeReaderId();
  const walletType = els.opsWalletType?.value || "story_credits";
  const amount = Number(els.opsWalletAmount?.value || 10);
  const restore = setBusy(els.opsDebitWallet, "扣减中…");
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
  const current = appState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可 reconcile。");
    return;
  }
  try {
    await api(`/v1/ops/subscriptions/${encodeURIComponent(current.subscription_id)}/reconcile`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: els.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`reconcile subscription 失败：${error.message}`);
  }
}

async function retryOpsSubscriptionPayment() {
  const current = appState.opsSubscriptionAudit?.subscriptions?.[0];
  if (!current?.subscription_id) {
    alert("当前 account 还没有 subscription 可 retry。");
    return;
  }
  try {
    await api(`/v1/ops/subscriptions/${encodeURIComponent(current.subscription_id)}/retry-payment`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: els.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`retry subscription 失败：${error.message}`);
  }
}

async function replayOpsBillingEvent() {
  const eventId = (els.opsBillingEventId?.value || "").trim();
  if (!eventId) {
    alert("先填写 billing event id。");
    return;
  }
  try {
    await api(`/v1/ops/billing-events/${encodeURIComponent(eventId)}/replay`, {
      method: "POST",
      body: JSON.stringify({
        requested_by: els.opsReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsAccountFlow();
  } catch (error) {
    alert(`replay billing event 失败：${error.message}`);
  }
}

async function updateSelectedOpsAlertStatus(status) {
  if (!appState.selectedOpsAlertId) {
    alert("先选择一条 alert。");
    return;
  }
  const reviewerId = els.opsGovernanceReviewerId?.value.trim() || "ops_web";
  const accountId = currentOpsAlertFilters().accountId || appState.opsAlertDetail?.alert?.account_id || undefined;
  await api(`/v1/ops/alerts/${encodeURIComponent(appState.selectedOpsAlertId)}/status`, {
    method: "POST",
    body: JSON.stringify({
      account_id: accountId,
      status,
      reviewer_id: reviewerId,
      note: els.opsAlertNote?.value.trim() || null,
    }),
  });
  await refreshOpsAlerts();
  renderOpsSurface();
}

async function openSelectedOpsAlertInvestigation() {
  const investigationRef =
    appState.opsAlertDetail?.alert?.investigation_ref ||
    appState.opsAlertDetail?.investigation_bundle?.filters ||
    {};
  if (!investigationRef.account_id && !investigationRef.world_version_id && !investigationRef.case_id) {
    alert("当前 alert 没有 investigation ref。");
    return;
  }
  if (els.opsInvestigationAccountId) {
    els.opsInvestigationAccountId.value = investigationRef.account_id || "";
  }
  if (els.opsInvestigationWorldVersionId) {
    els.opsInvestigationWorldVersionId.value = investigationRef.world_version_id || "";
  }
  if (els.opsInvestigationCaseId) {
    els.opsInvestigationCaseId.value = investigationRef.case_id || "";
  }
  await runOpsInvestigation();
  els.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runOpsWorkspaceAction(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  if (!action) return;
  if (prefill.account_id && els.opsAccountId) {
    els.opsAccountId.value = prefill.account_id;
  }
  if (action.handler === "grant_wallet") {
    if (els.opsWalletType && prefill.wallet_type) els.opsWalletType.value = prefill.wallet_type;
    if (els.opsWalletAmount && prefill.amount !== undefined) els.opsWalletAmount.value = String(prefill.amount);
    await grantOpsWallet();
    return;
  }
  if (action.handler === "grant_subscription") {
    if (els.opsTierId && prefill.tier_id) els.opsTierId.value = prefill.tier_id;
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
    if (els.opsInvestigationAccountId) els.opsInvestigationAccountId.value = prefill.account_id || els.opsAccountId?.value || "";
    if (els.opsInvestigationWorldVersionId) els.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    if (els.opsInvestigationCaseId) els.opsInvestigationCaseId.value = prefill.case_id || "";
    await runOpsInvestigation();
    els.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (action.handler === "open_governance_case") {
    if (prefill.account_id && els.opsAccountId) els.opsAccountId.value = prefill.account_id;
    if (prefill.case_id && els.opsGovernanceCaseId) els.opsGovernanceCaseId.value = prefill.case_id;
    if (prefill.case_id) {
      await openGovernanceCaseDetail(prefill.case_id);
      els.opsGovernanceDetail?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }
  if (action.handler === "open_alert_feed") {
    if (els.opsAlertAccountId) els.opsAlertAccountId.value = prefill.account_id || els.opsAccountId?.value || "";
    await refreshOpsAlerts();
    renderOpsSurface();
    els.opsAlertSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
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
      body: JSON.stringify({ reviewer_id: els.opsGovernanceReviewerId?.value.trim() || "ops_web" }),
    });
    await refreshOpsReleaseFlow();
    return;
  }
  if (action.handler === "rollback_world") {
    const worldId = prefill.world_id || appState.selectedOpsWorldId;
    const targetWorldVersionId = prefill.target_world_version_id;
    if (!worldId || !targetWorldVersionId) {
      alert("当前 action 缺少 rollback 目标。");
      return;
    }
    await api(`/v1/ops/worlds/${encodeURIComponent(worldId)}/rollback`, {
      method: "POST",
      body: JSON.stringify({
        target_world_version_id: targetWorldVersionId,
        reviewer_id: els.opsGovernanceReviewerId?.value.trim() || "ops_web",
      }),
    });
    await refreshOpsReleaseFlow();
    return;
  }
  if (action.handler === "run_release_investigation") {
    if (els.opsInvestigationWorldVersionId) {
      els.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    }
    if (els.opsInvestigationAccountId) {
      els.opsInvestigationAccountId.value = "";
    }
    if (els.opsInvestigationCaseId) {
      els.opsInvestigationCaseId.value = "";
    }
    await runOpsInvestigation();
    els.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (action.handler === "inspect_publish_blocker") {
    els.opsReleaseWorkspaceDetails?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function applyOpsNavigationStaleRefCleanup(staleRefs = {}) {
  if (staleRefs.alert) {
    if (els.opsNavAlertId) els.opsNavAlertId.value = "";
    if (appState.selectedOpsAlertId === staleRefs.alert.ref_id) {
      appState.selectedOpsAlertId = null;
    }
    appState.opsAlertDetail = null;
  }
  if (staleRefs.case) {
    if (els.opsNavCaseId) els.opsNavCaseId.value = "";
    if (els.opsGovernanceCaseId) els.opsGovernanceCaseId.value = "";
    if (els.opsInvestigationCaseId) els.opsInvestigationCaseId.value = "";
    appState.opsGovernanceDetail = null;
  }
  if (staleRefs.world) {
    if (els.opsNavWorldId) els.opsNavWorldId.value = "";
    if (els.opsReleaseWorldId) els.opsReleaseWorldId.value = "";
    if (appState.selectedOpsWorldId === staleRefs.world.ref_id) {
      appState.selectedOpsWorldId = null;
    }
    appState.opsReleaseWorkspace = null;
  }
  if (staleRefs.world_version) {
    if (els.opsInvestigationWorldVersionId) els.opsInvestigationWorldVersionId.value = "";
    if (appState.opsInvestigationBundle?.filters?.world_version_id === staleRefs.world_version.ref_id) {
      appState.opsInvestigationBundle = null;
    }
  }
}

async function clearOpsNavigationStaleRefs(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  const staleRefs = { ...(prefill.stale_refs || appState.opsNavigationModel?.linked_context?.stale_refs || {}) };
  applyOpsNavigationStaleRefCleanup(staleRefs);
  await refreshOpsSurface({
    scopes: ["account", "review_release", "alerts", "navigation", "investigation"],
    preserveLastActionImpact: true,
  });
}

async function resyncOpsNavigationContext(action) {
  const prefill = { ...((action && action.prefill) || {}) };
  const staleRefs = { ...(prefill.stale_refs || appState.opsNavigationModel?.linked_context?.stale_refs || {}) };
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
    if (prefill.account_id && els.opsAccountId) {
      els.opsAccountId.value = prefill.account_id;
    }
    await refreshOpsAccountFlow();
    els.opsAccountWorkspaceSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "release_workspace") {
    if (prefill.world_id && els.opsReleaseWorldId) {
      els.opsReleaseWorldId.value = prefill.world_id;
    }
    appState.selectedOpsWorldId = prefill.world_id || appState.selectedOpsWorldId;
    await refreshOpsReleaseWorkspace();
    renderOpsSurface();
    els.opsReleaseWorkspaceSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "governance_case") {
    if (prefill.case_id) {
      await openGovernanceCaseDetail(prefill.case_id);
      els.opsGovernanceDetail?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }
  if (target.target_id === "alert_detail") {
    if (prefill.account_id && els.opsAlertAccountId) {
      els.opsAlertAccountId.value = prefill.account_id;
    }
    if (prefill.alert_id) {
      appState.selectedOpsAlertId = prefill.alert_id;
    }
    await refreshOpsAlerts();
    renderOpsSurface();
    els.opsAlertSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (target.target_id === "investigation") {
    if (els.opsInvestigationAccountId) els.opsInvestigationAccountId.value = prefill.account_id || "";
    if (els.opsInvestigationWorldVersionId) els.opsInvestigationWorldVersionId.value = prefill.world_version_id || "";
    if (els.opsInvestigationCaseId) els.opsInvestigationCaseId.value = prefill.case_id || "";
    await runOpsInvestigation();
    els.opsInvestigationSummary?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function followOpsNavigationRecommendation() {
  const model = appState.opsNavigationModel;
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
  const accountId = (els.opsInvestigationAccountId?.value || "").trim() || (els.opsAccountId?.value || "").trim();
  const worldVersionId = (els.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (els.opsInvestigationCaseId?.value || "").trim();
  if (!accountId && !worldVersionId && !caseId) {
    alert("请至少填写 account_id、world_version_id 或 case_id。");
    return;
  }
  if (!options.silent) {
    appState.opsInvestigationPinned = true;
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
  appState.opsInvestigationBundle = payload;
  if (!options.skipRender) {
    renderOpsSurface();
  }
}

async function exportOpsInvestigationTrace() {
  const accountId = (els.opsInvestigationAccountId?.value || "").trim() || (els.opsAccountId?.value || "").trim();
  const worldVersionId = (els.opsInvestigationWorldVersionId?.value || "").trim();
  const caseId = (els.opsInvestigationCaseId?.value || "").trim();
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  if (worldVersionId) params.set("world_version_id", worldVersionId);
  if (caseId) params.set("case_id", caseId);
  params.set("limit", "100");
  if (!accountId && !worldVersionId && !caseId) {
    alert("请至少填写 account_id、world_version_id 或 case_id。");
    return;
  }
  appState.opsInvestigationBundle = await api(`/v1/ops/export/investigation-trace?${params.toString()}`);
  downloadJsonFile(
    `investigation-trace-${caseId || worldVersionId || accountId || "export"}.json`,
    appState.opsInvestigationBundle
  );
  renderOpsSurface();
}

async function revokeOpsEntitlement() {
  const entitlementId = els.opsEntitlementId?.value.trim();
  const reason = els.opsEntitlementReason?.value.trim() || "manual_entitlement_revoke";
  if (!entitlementId) {
    alert("请先填写要撤销的 entitlement_id。");
    return;
  }
  const restore = setBusy(els.opsRevokeEntitlement, "撤销中…");
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
