// Ops shared helpers extracted from app.js so Ops actions and renderers can share one boundary.

var OpsShared = (() => {
  const dom = OpsDOM;
  const {
    api,
    formatPercent
  } = UIShared;

const OPS_STATUS_LABELS = {
  open: "待处理",
  unread: "未读",
  active: "处理中",
  acknowledged: "已确认",
  resolved: "已解决",
  dismissed: "已关闭",
  escalated: "已升级",
  in_review: "审核中",
  approved: "已通过",
  published: "已发布",
  rolled_back: "已回滚",
  publish_blocked: "发布受阻",
  active_restriction: "限制生效中",
  released: "已释放",
  completed: "已完成",
  queued: "排队中",
  running: "运行中",
  failed: "失败",
  paused: "已暂停",
  canceled: "已取消",
  expired: "已过期",
  trialing: "试用中",
  shadow_only: "仅影子模式",
  assisted_gate: "辅助门控",
  assisted_rerank: "辅助重排",
  canary: "灰度中",
  activate: "全量启用",
  rollback: "回滚",
  pending: "待处理",
  invalid: "配置异常",
  valid: "配置正常",
};

const OPS_PROVIDER_LABELS = {
  stripe: "Stripe",
  web_stub: "网页支付测试",
  ops_manual: "运营手动",
  default: "默认通道",
  global: "全局",
  candidate: "候选链路",
  renderer: "渲染链路",
};

const OPS_TRACK_LABELS = {
  evaluator: "评估器",
  reranker: "重排器",
  candidate: "候选链路",
  renderer: "渲染链路",
};

const OPS_SCOPE_LABELS = {
  global: "全局",
  world: "世界",
  account: "账户",
  chapter: "章节",
};

const OPS_ACTION_MODE_LABELS = {
  execute: "执行",
  navigate: "跳转",
  prefill: "填充",
  open_detail: "打开详情",
};

const OPS_ISSUE_LABELS = {
  Q01: "Q01 工程泄漏",
  Q02: "Q02 元叙事泄漏",
  Q03: "Q03 重复",
  Q04: "Q04 解释过多",
  Q05: "Q05 场景细节不足",
  Q06: "Q06 人物不稳定",
  Q07: "Q07 因果断裂",
  Q08: "Q08 选项差异弱",
  Q09: "Q09 节奏失败 / 过早收束",
  Q10: "Q10 产品连续性失败",
};

const OPS_WORLD_LABELS = {
  jade_court_exam: "玉阙春闱（职责线）",
  jade_court_romance: "玉阙春闱（情感线）",
  urban_mystery_lotus_lane: "莲巷迷案",
  xianxia_forgotten_vow: "失誓仙途",
  synthetic_min_pack: "合成最小包",
};

function reviewStatusLabel(status) {
  return {
    submitted: "已提交审核",
    approved: "审核通过",
    published: "已发布",
    rolled_back: "已回滚",
    publish_blocked: "发布被阻止",
  }[status] || status;
}

function opsStatusLabel(status) {
  return OPS_STATUS_LABELS[String(status || "").trim()] || reviewStatusLabel(status) || status || "-";
}

function opsProviderLabel(provider) {
  return OPS_PROVIDER_LABELS[String(provider || "").trim()] || provider || "-";
}

function opsTrackLabel(track) {
  return OPS_TRACK_LABELS[String(track || "").trim()] || track || "-";
}

function opsScopeLabel(scope) {
  return OPS_SCOPE_LABELS[String(scope || "").trim()] || scope || "-";
}

function opsActionModeLabel(mode) {
  return OPS_ACTION_MODE_LABELS[String(mode || "").trim()] || mode || "-";
}

function opsIssueCodeLabel(issueCode) {
  return OPS_ISSUE_LABELS[String(issueCode || "").trim()] || issueCode || "-";
}

function opsIssueCodeList(issueCodes) {
  return (issueCodes || []).map((item) => opsIssueCodeLabel(item)).join(" / ") || "-";
}

function opsWorldLabel(worldId) {
  const raw = String(worldId || "").trim();
  if (!raw) return "-";
  if (OPS_WORLD_LABELS[raw]) return OPS_WORLD_LABELS[raw];
  if (raw.startsWith("smoke_draft_")) return "烟雾测试草稿";
  return raw;
}

function opsBooleanLabel(value) {
  return value ? "是" : "否";
}

function opsNumericValue(value, digits = 0) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return numeric.toFixed(digits);
}

function opsLatencyValue(value) {
  const numeric = opsNumericValue(value, 1);
  return numeric === "-" ? "-" : `${numeric}ms`;
}

function opsCostValue(value, digits = 3) {
  return opsNumericValue(value, digits);
}

function opsWorldList(worldIds) {
  return (worldIds || []).map((item) => opsWorldLabel(item)).join(" / ") || "-";
}

function opsTrackList(tracks) {
  return (tracks || []).map((item) => opsTrackLabel(item)).join(" / ") || "-";
}

function opsPreferredCandidateLabel(candidate) {
  if (!candidate || String(candidate).trim() === "neither") return "均不推荐";
  return opsTrackLabel(candidate);
}

function opsRolloutSummary(status, bucketMatch) {
  const statusLabel = opsStatusLabel(status || "-");
  if (bucketMatch === undefined || bucketMatch === null) return statusLabel;
  return `${statusLabel} · ${bucketMatch ? "命中分桶" : "未命中分桶"}`;
}

function opsTargetLabel(targetType, targetId) {
  return `${targetType || "-"}:${targetId || "-"}`;
}

function opsFieldLine(label, value) {
  return `${label} ${value === undefined || value === null || value === "" ? "-" : value}`;
}

function opsPairsLine(label, pairs, valueFormatter = (value) => value) {
  const text = Object.entries(pairs || {})
    .map(([key, value]) => `${valueFormatter(key)}=${value}`)
    .join(" / ");
  return opsFieldLine(label, text || "-");
}

function summarizeChecklistEvidence(evidence) {
  if (!evidence || typeof evidence !== "object") return "-";
  const parts = [];
  if (evidence.cross_pack_pass_rate !== undefined && evidence.cross_pack_pass_rate !== null) {
    parts.push(`跨包通过率 ${Number(evidence.cross_pack_pass_rate || 0).toFixed(3)}`);
  }
  if (evidence.cross_pack_pass_rate_delta !== undefined && evidence.cross_pack_pass_rate_delta !== null) {
    parts.push(`变化 ${Number(evidence.cross_pack_pass_rate_delta || 0).toFixed(3)}`);
  }
  if (evidence.block_rate !== undefined && evidence.block_rate !== null) {
    parts.push(`阻塞率 ${formatPercent(evidence.block_rate)}`);
  }
  if (evidence.max_prose_leak_rate !== undefined && evidence.max_prose_leak_rate !== null) {
    parts.push(`最高泄漏率 ${Number(evidence.max_prose_leak_rate || 0).toFixed(3)}`);
  }
  if (Array.isArray(evidence.top_failing_pack_ids) && evidence.top_failing_pack_ids.length) {
    parts.push(`薄弱世界 ${evidence.top_failing_pack_ids.map((item) => opsWorldLabel(item)).join(" / ")}`);
  }
  if (Array.isArray(evidence.regressions) && evidence.regressions.length) {
    parts.push(`回退项 ${evidence.regressions.join(" / ")}`);
  }
  if (Array.isArray(evidence.leaking_worlds) && evidence.leaking_worlds.length) {
    parts.push(`泄漏世界 ${evidence.leaking_worlds.map((item) => `${opsWorldLabel(item.world_id)}:${Number(item.prose_leak_rate || 0).toFixed(3)}`).join(" / ")}`);
  }
  if (evidence.latest_decision) {
    parts.push(`最近判断 ${opsStatusLabel(evidence.latest_decision)}`);
  }
  if (evidence.present !== undefined) {
    parts.push(`是否存在 ${opsBooleanLabel(evidence.present)}`);
  }
  if (evidence.completed_chapters !== undefined && evidence.completed_chapters !== null) {
    parts.push(`章节数 ${evidence.completed_chapters}`);
  }
  return parts.join(" · ") || JSON.stringify(evidence);
}

function applySupportPrefill(prefill = {}) {
  if (prefill.account_id && dom.opsAccountId) {
    dom.opsAccountId.value = prefill.account_id;
  }
  if (prefill.wallet_type && dom.opsWalletType) {
    dom.opsWalletType.value = prefill.wallet_type;
  }
  if (prefill.amount !== undefined && prefill.amount !== null && dom.opsWalletAmount) {
    dom.opsWalletAmount.value = String(prefill.amount);
  }
  if (prefill.tier_id && dom.opsTierId) {
    dom.opsTierId.value = prefill.tier_id;
  }
  if (prefill.subscription_status && dom.opsSubscriptionStatus) {
    dom.opsSubscriptionStatus.value = prefill.subscription_status;
  }
  if (prefill.entitlement_id && dom.opsEntitlementId) {
    dom.opsEntitlementId.value = prefill.entitlement_id;
  }
  if (prefill.entitlement_reason && dom.opsEntitlementReason) {
    dom.opsEntitlementReason.value = prefill.entitlement_reason;
  }
}

function applyGovernanceCasePrefill(prefill = {}) {
  if (prefill.account_id && dom.opsAccountId) {
    dom.opsAccountId.value = prefill.account_id;
  }
  if (prefill.case_id && dom.opsGovernanceCaseId) {
    dom.opsGovernanceCaseId.value = prefill.case_id;
  }
  if (prefill.case_type && dom.opsGovernanceCaseType) {
    dom.opsGovernanceCaseType.value = prefill.case_type;
  }
  if (prefill.target_type && dom.opsGovernanceTargetType) {
    dom.opsGovernanceTargetType.value = prefill.target_type;
  }
  if (prefill.target_id && dom.opsGovernanceTargetId) {
    dom.opsGovernanceTargetId.value = prefill.target_id;
  }
  if (prefill.severity && dom.opsGovernanceSeverity) {
    dom.opsGovernanceSeverity.value = prefill.severity;
  }
  if (prefill.reviewer_id && dom.opsGovernanceReviewerId) {
    dom.opsGovernanceReviewerId.value = prefill.reviewer_id;
  }
  if (prefill.owner_id && dom.opsGovernanceOwnerId) {
    dom.opsGovernanceOwnerId.value = prefill.owner_id;
  }
  if (prefill.summary && dom.opsGovernanceSummaryInput) {
    dom.opsGovernanceSummaryInput.value = prefill.summary;
  }
  if (prefill.description && dom.opsGovernanceNotes) {
    dom.opsGovernanceNotes.value = prefill.description;
  }
  if (prefill.status && dom.opsGovernanceStatus) {
    dom.opsGovernanceStatus.value = prefill.status;
  }
  if (prefill.due_at && dom.opsGovernanceDueAt) {
    dom.opsGovernanceDueAt.value = prefill.due_at;
  }
  if (prefill.disposition && dom.opsGovernanceDisposition) {
    dom.opsGovernanceDisposition.value = prefill.disposition;
  }
  if (prefill.policy_labels && dom.opsGovernancePolicyLabels) {
    dom.opsGovernancePolicyLabels.value = Array.isArray(prefill.policy_labels) ? prefill.policy_labels.join(", ") : String(prefill.policy_labels);
  }
}

async function openLearnedWorldDetail(worldId) {
  opsState.opsLearnedDetail = await api(`/v1/ops/learned-dashboard/worlds/${worldId}`);
  OpsRenderRuntime.renderOpsSurface(["learned"]);
}

async function openLearnedIssueDetail(issueCode) {
  opsState.opsLearnedDetail = await api(`/v1/ops/learned-dashboard/issues/${issueCode}`);
  OpsRenderRuntime.renderOpsSurface(["learned"]);
}

function selectReviewBacklogItem(item) {
  opsState.opsReviewCaptureTarget = item;
  if (dom.opsReviewIssueCodes) {
    dom.opsReviewIssueCodes.value = (item.issue_codes || []).join(",");
  }
  if (dom.opsReviewNotes) {
    dom.opsReviewNotes.value = item.summary || "";
  }
  if (dom.opsReviewScore) {
    dom.opsReviewScore.value = item.score_overall !== null && item.score_overall !== undefined
      ? Number(item.score_overall).toFixed(2)
      : "0.65";
  }
  if (dom.opsReviewWouldContinue) {
    dom.opsReviewWouldContinue.checked = item.decision !== "block";
  }
  if (dom.opsReviewWouldPay) {
    dom.opsReviewWouldPay.checked = item.decision === "pass";
  }
  if (dom.opsPreferenceNotes) {
    dom.opsPreferenceNotes.value = item.summary || "";
  }
  if (dom.opsRankingNotes) {
    dom.opsRankingNotes.value = item.summary || "";
  }
  OpsRenderRuntime.renderOpsSurface(["learned"]);
}

  return {
    reviewStatusLabel,
    opsStatusLabel,
    opsProviderLabel,
    opsTrackLabel,
    opsScopeLabel,
    opsActionModeLabel,
    opsIssueCodeLabel,
    opsIssueCodeList,
    opsWorldLabel,
    opsWorldList,
    opsTrackList,
    opsPreferredCandidateLabel,
    opsBooleanLabel,
    opsNumericValue,
    opsLatencyValue,
    opsCostValue,
    opsRolloutSummary,
    opsTargetLabel,
    opsFieldLine,
    opsPairsLine,
    summarizeChecklistEvidence,
    applySupportPrefill,
    applyGovernanceCasePrefill,
    openLearnedWorldDetail,
    openLearnedIssueDetail,
    selectReviewBacklogItem
  };
})();
