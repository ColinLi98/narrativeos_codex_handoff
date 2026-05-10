// Author workspace runtime extracted from app.js to keep Author flows isolated from shell and Reader.

var AuthorWorkspaceRuntime = (() => {
  const dom = AuthorDOM;
  const {
    api,
    parseErrorDetail,
    describeAuthError,
    setBusy,
    clearNode,
    createListCard,
    reportUiMessage,
    formatPercent,
    formatTimestamp,
    downloadJsonFile,
    parseMaybeJson
  } = UIShared;
  const {
    getActiveDraftWorldpack,
    getActiveRevisionHistory,
    getLatestDiffSummary,
    getDiffDrilldown,
    getSimulationDrilldown,
    getLongformDrilldown,
    getPromiseLedgerWorkbench,
    getPromiseStateWorkbench,
    getSeriesVolumeArcPromiseMapping,
    getChapterTaskSimulationLinking,
    getContinuityDiffWorkbench,
    getContinuityOverrideWorkbench,
    getSimulationDiffCheckpoint,
    selectedAuthorChapterMarker,
    selectedAuthorCompareMarker,
    alertAuthorGating
  } = AuthorAccessors;
  const {
    tierLabel,
    accessReasonLabel,
    gatingStatusLabel,
    gatingHint
  } = ReaderAccessors;
  const { refreshOpsSurface } = OpsRefreshRuntime;

function authorStageLabel(stage) {
  return {
    brief: "准备起稿",
    draft_created: "草稿已创建",
    validated: "校验通过",
    simulated: "诊断完成",
    revised_after_simulation: "修改后待重跑",
    ready_to_submit: "准备送审",
    submitted: "已提交审核",
  }[stage] || stage || "-";
}

function authorRecommendedActionLabel(actionId) {
  return {
    create_from_brief: "先整理灵感，再生成今天要打磨的草稿",
    copy_current_world: "先复制当前世界，建立可编辑草稿",
    bootstrap_quick_brief_enrich: "先补齐 100 章所需的长线骨架",
    bootstrap_structured_longform: "先进入结构化长篇蓝图，再谈更长长度",
    validate_draft: "先跑一次校验，找出当前阻塞",
    simulate_draft: "先跑一次诊断，看看重点问题章节和问题队列",
    submit_draft: "现在可以送审，交给审阅人",
    focus_longform: "先看长篇规划与 readiness 阻塞",
    focus_validation: "先看校验结果，确认当前阻塞",
    focus_simulation: "先看模拟结果，判断要改哪几章",
    focus_diff: "先看最近一次修改，确认这轮改了什么",
    focus_revision: "先看版本对照，确认修改方向",
    focus_version_history: "先看版本轨迹，确认这轮是否需要回退",
    focus_draft_detail: "先看当前草稿摘要，确认工作对象",
  }[actionId] || "先处理当前最重要的一步";
}

function authorRecommendedWorkspaceLabel(actionId) {
  return {
    create_from_brief: "起稿",
    copy_current_world: "总览",
    bootstrap_quick_brief_enrich: "创作台",
    bootstrap_structured_longform: "创作台",
    validate_draft: "总览",
    simulate_draft: "总览",
    submit_draft: "总览",
    focus_longform: "创作台",
    focus_validation: "问题诊断",
    focus_simulation: "问题诊断",
    focus_diff: "送审",
    focus_revision: "送审",
    focus_version_history: "送审",
    focus_draft_detail: "总览",
  }[actionId] || "总览";
}

function authorStageTone(status) {
  if (["done", "completed", "ready", "submitted", "approved"].includes(String(status || "").toLowerCase())) return "is-complete";
  if (["active", "current", "in_progress", "in-review", "in_review"].includes(String(status || "").toLowerCase())) return "is-active";
  if (["blocked", "error", "failed"].includes(String(status || "").toLowerCase())) return "is-blocked";
  return "is-pending";
}

const AUTHOR_DRAFT_SECTION_CONFIG = [
  { key: "assets", label: "人物设定", description: "角色卡和场景蓝图。" },
  { key: "longform", label: "长篇规划", description: "系列、分卷、弧线与承诺映射。" },
  { key: "repair", label: "修稿桥", description: "承诺、章节任务和连续性修稿桥。" },
  { key: "style", label: "风格控制", description: "风格、节奏、钩子与高级配置。" },
];

function authorNotice(message, kind = "warning") {
  reportUiMessage(String(message), kind);
}

function currentAuthorDraftSection() {
  return AUTHOR_DRAFT_SECTION_CONFIG.some((item) => item.key === authorState.authorDraftSection)
    ? authorState.authorDraftSection
    : "assets";
}

function setAuthorDraftSection(sectionKey, options = {}) {
  const nextSection = AUTHOR_DRAFT_SECTION_CONFIG.some((item) => item.key === sectionKey) ? sectionKey : "assets";
  authorState.authorDraftSection = nextSection;
  syncAuthorDraftSectionPanels();
  if (!options.silent) {
    renderAuthorDraftSectionNav();
  }
}

function syncAuthorDraftSectionPanels() {
  const activeSection = currentAuthorDraftSection();
  document.querySelectorAll("#author-shell [data-author-draft-section]").forEach((panel) => {
    const hidden = panel.dataset.authorDraftSection !== activeSection;
    panel.classList.toggle("is-hidden", hidden);
  });
}

function isAuthorSessionExpiringSoon(expiresAt) {
  const timestamp = Date.parse(String(expiresAt || ""));
  if (!Number.isFinite(timestamp)) return false;
  return timestamp > Date.now() && timestamp - Date.now() < 24 * 60 * 60 * 1000;
}

function createAuthorSummaryCard({ title, score, body, warning = "", actionLabel = "", onAction = null, primary = false }) {
  const card = createListCard({ title, score, body });
  card.classList.add("author-summary-card");
  if (warning) {
    card.classList.add("is-warning");
    const warningNode = document.createElement("p");
    warningNode.className = "author-summary-warning";
    warningNode.textContent = warning;
    card.appendChild(warningNode);
  }
  if (actionLabel && typeof onAction === "function") {
    const actions = document.createElement("div");
    actions.className = "composer-actions author-card-actions";
    const button = document.createElement("button");
    button.className = primary ? "primary-action" : "ghost-action";
    button.textContent = actionLabel;
    button.addEventListener("click", onAction);
    actions.appendChild(button);
    card.appendChild(actions);
  }
  return card;
}

function createAuthorWorkCard({ title, score, body, warning = "", active = false, actions = [] }) {
  const card = createListCard({ title, score, body });
  card.classList.add("author-work-card");
  if (active) {
    card.classList.add("is-active");
  }
  if (warning) {
    card.classList.add("is-warning");
    const warningNode = document.createElement("p");
    warningNode.className = "author-summary-warning";
    warningNode.textContent = warning;
    card.appendChild(warningNode);
  }
  if (actions.length) {
    const actionRow = document.createElement("div");
    actionRow.className = "composer-actions author-card-actions";
    actions.forEach((item) => {
      const button = document.createElement("button");
      button.className = item.primary ? "primary-action" : "ghost-action";
      button.textContent = item.label;
      button.addEventListener("click", item.onClick);
      actionRow.appendChild(button);
    });
    card.appendChild(actionRow);
  }
  return card;
}

function normalizeAuthorChoiceText(choice) {
  if (typeof choice === "string") {
    return choice.trim();
  }
  if (!choice || typeof choice !== "object") {
    return "";
  }
  return String(choice.label || choice.text || choice.title || "").trim();
}

function focusAuthorPanel(panelKey) {
  const mapping = {
    workflow: { node: dom.authorWorkflow, workspace: "overview" },
    draft_detail: { node: dom.authorDraftDetail, workspace: "overview" },
    auth_settings: { node: dom.authorAuthStatus, workspace: "settings" },
    notification_settings: { node: dom.authorNotificationPreferences, workspace: "settings" },
    steering: { node: dom.authorSteeringComposer, workspace: "simulate" },
    validation: { node: dom.authorValidationReport, workspace: "simulate" },
    simulation: { node: dom.authorSimulationReport, workspace: "simulate" },
    creative_cockpit: { node: dom.authorCreativeCockpit, workspace: "simulate" },
    character_editor: { node: dom.authorCharacterSelect, workspace: "draft", section: "assets" },
    scene_editor: { node: dom.authorSceneSelect, workspace: "draft", section: "assets" },
    task_editor: { node: dom.authorTaskSelect, workspace: "draft", section: "longform" },
    longform: { node: dom.authorLongformStatus, workspace: "draft", section: "longform" },
    task_linking: { node: dom.authorTaskSimulationLinking, workspace: "draft", section: "repair" },
    continuity: { node: dom.authorContinuityDiff, workspace: "draft", section: "repair" },
    diff: { node: dom.authorAssetDiff, workspace: "review" },
    compare: { node: dom.authorCompare, workspace: "review" },
    collaboration: { node: dom.authorCollaboration, workspace: "settings" },
    version_history: { node: dom.authorVersionHistory, workspace: "review" },
    brief: { node: dom.authorCorePremise, workspace: "brief" },
  };
  const target = mapping[panelKey];
  if (target?.workspace) {
    WorkspaceLayoutRuntime.setAuthorWorkspace(target.workspace, { silent: true });
    if (target.section) {
      setAuthorDraftSection(target.section, { silent: true });
    }
    ShellStatusRuntime.syncProductMode();
  }
  const node = target?.node?.closest(".panel") || target?.node;
  node?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildAuthorAdminViewUrl(workspace = "review") {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams();
  params.set("product", "ops");
  params.set("workspace", workspace);
  params.set("admin_view", "1");
  const accountId =
    activeAuthorActorId() ||
    dom.authorAccountId?.value.trim() ||
    authorState.activeDraftDetail?.worldpack?.manifest?.author_id ||
    "";
  const worldId = authorState.activeDraftDetail?.world_id || authorState.activeDraftDetail?.worldpack?.world_id || "";
  const worldVersionId = authorState.activeDraftVersionId || "";
  if (accountId) params.set("account_id", accountId);
  if (worldId) params.set("world_id", worldId);
  if (worldVersionId) params.set("world_version_id", worldVersionId);
  return `${window.location.pathname}?${params.toString()}`;
}

async function openAuthorAdminView(workspace = "review") {
  try {
    const bridgePayload = {
      workspace,
      account_id:
        activeAuthorActorId() ||
        dom.authorAccountId?.value.trim() ||
        authorState.activeDraftDetail?.worldpack?.manifest?.author_id ||
        null,
      world_id: authorState.activeDraftDetail?.world_id || authorState.activeDraftDetail?.worldpack?.world_id || null,
      world_version_id: authorState.activeDraftVersionId || null,
    };
    const hasPrivilegedSession = ["reviewer", "ops", "admin"].includes(
      String(authorState.authorAuthSession?.identity?.actor_role || "").trim()
    );
    let payload;
    if (hasPrivilegedSession && authorState.authorAuthSession?.accessToken) {
      payload = await api("/v1/auth/admin-view-bridge", {
        method: "POST",
        body: JSON.stringify(bridgePayload),
      });
    } else {
      const reviewerActorId = window.prompt("输入 reviewer / ops 账号 ID");
      if (!reviewerActorId) {
        authorNotice("已取消打开管理员视图。", "info");
        return;
      }
      const reviewerPassword = window.prompt("输入 reviewer / ops 密码");
      if (!reviewerPassword) {
        authorNotice("已取消打开管理员视图。", "info");
        return;
      }
      payload = await api("/v1/auth/admin-view-session-bridge", {
        method: "POST",
        body: JSON.stringify({
          ...bridgePayload,
          actor_id: reviewerActorId,
          password: reviewerPassword,
        }),
      });
    }
    const url = payload.url || buildAuthorAdminViewUrl(workspace);
    if (!url) return;
    const opened = window.open(url, "_blank", "noopener");
    if (!opened) {
      window.location.href = url;
    }
  } catch (error) {
    const detail = parseErrorDetail(error);
    if (detail?.code === "admin_view_bridge_forbidden") {
      authorNotice("当前登录身份没有管理员视图权限，需要 reviewer / ops / admin 账号。", "warning");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "打开管理员视图失败，请稍后再试。"), "error");
  }
}

function prefillAuthorCommentAnchor(anchorType, anchorKey) {
  if (dom.authorCommentAnchorType) {
    dom.authorCommentAnchorType.value = anchorType || "draft";
  }
  if (dom.authorCommentAnchorKey) {
    dom.authorCommentAnchorKey.value = anchorKey || "";
  }
  focusAuthorPanel("collaboration");
}

function activeAuthorAccountId() {
  return dom.authorAccountId?.value.trim() || authorState.authorAuthSession?.identity?.account_id || "";
}

function preferredAuthorDraftVersionId(drafts = []) {
  const preferredAccountId = String(
    authorState.authorAuthSession?.identity?.account_id ||
    dom.authorAccountId?.value.trim() ||
    ""
  ).trim();
  if (!Array.isArray(drafts) || !drafts.length) return null;
  const ownedDraft = preferredAccountId
    ? drafts.find((item) => String(item.author_id || "").trim() === preferredAccountId)
    : null;
  return (ownedDraft || drafts[0])?.world_version_id || null;
}

function currentDraftAuthorAccountId() {
  return (
    authorState.activeDraftDetail?.worldpack?.manifest?.author_id ||
    authorState.activeDraftDetail?.author_id ||
    dom.authorAccountId?.value.trim() ||
    ""
  ).trim();
}

function expectedDraftAuthorAccountId() {
  if (typeof window === "undefined") return currentDraftAuthorAccountId();
  const params = new URLSearchParams(window.location.search);
  return String(currentDraftAuthorAccountId() || params.get("account_id") || "").trim();
}

function primeAuthorIdentityInputs(preferredAccountId = "") {
  const normalized = String(preferredAccountId || "").trim();
  if (normalized && dom.authorAccountId) {
    dom.authorAccountId.value = normalized;
  }
  if (normalized && dom.authorAuthActorId && !dom.authorAuthActorId.value.trim()) {
    dom.authorAuthActorId.value = normalized;
  }
}

function handleAuthorWorkAccessError(error, actionLabel) {
  const detail = parseErrorDetail(error);
  const resolvedDetail = detail?.detail && typeof detail.detail === "object" ? detail.detail : detail;
  const expectedAccountId = expectedDraftAuthorAccountId();
  const currentAccountId = activeAuthorAccountId();
  if (resolvedDetail?.code === "author_entitlement_required") {
    alertAuthorGating(resolvedDetail, actionLabel);
    return true;
  }
  if (resolvedDetail?.code === "author_work_identity_required") {
    primeAuthorIdentityInputs(expectedAccountId || currentAccountId);
    focusAuthorPanel("auth_settings");
    authorNotice(
      `要${actionLabel}，请先在“账户协作”里登录作者账号 ${expectedAccountId || currentAccountId || "当前草稿对应账号"}。URL 里的 account_id 只用于定位，不代表已登录。`,
      "warning"
    );
    return true;
  }
  if (resolvedDetail?.code === "author_work_forbidden") {
    primeAuthorIdentityInputs(expectedAccountId);
    focusAuthorPanel("auth_settings");
    authorNotice(
      `当前登录账号 ${currentAccountId || "-"} 和这份 Draft 的作者账号 ${expectedAccountId || "-"} 不一致。请切换到正确账号后再${actionLabel}。`,
      "warning"
    );
    return true;
  }
  return false;
}

function formatAuthorQualityGateSummary(qualityGate) {
  const gate = qualityGate || {};
  const issues = Array.isArray(gate.issues) ? gate.issues : [];
  const issueCodes = Array.from(new Set(issues.map((item) => String(item?.issue_code || "").trim()).filter(Boolean)));
  const owningModules = Array.from(new Set((gate.owning_modules || []).map((item) => String(item || "").trim()).filter(Boolean)));
  const failedChecks = Array.from(new Set((gate.failed_checks || []).map((item) => String(item || "").trim()).filter(Boolean)));
  return [
    `gate ${gate.code || "chapter_quality_guard_failed"}`,
    `字数 ${Number(gate.actual_text_units || 0)} / ${Number(gate.required_text_units || 0) || "-"}`,
    `decision ${gate.decision || "-"} -> ${gate.enforced_decision || gate.decision || "-"}`,
    `issues ${issueCodes.join(" / ") || "-"}`,
    `模块 ${owningModules.join(" / ") || "-"}`,
    `失败项 ${failedChecks.join(" / ") || "-"}`,
  ].join("\n");
}

function handleAuthorWorkQualityGateError(error, actionLabel) {
  const detail = parseErrorDetail(error);
  const resolvedDetail = detail?.detail && typeof detail.detail === "object" ? detail.detail : detail;
  const qualityGate = resolvedDetail?.quality_gate;
  if (resolvedDetail?.code !== "chapter_quality_guard_failed" || !qualityGate) {
    return false;
  }
  authorState.authorWorkQualityGateFailure = {
    action_label: actionLabel,
    quality_gate: qualityGate,
  };
  if (actionLabel === "保存章节") {
    authorState.activeWorkSaveState = "blocked";
    refreshAuthorWorkEditorChrome();
  }
  renderAuthorReports();
  authorNotice(
    `${actionLabel}未通过章节硬约束：${Number(qualityGate.actual_text_units || 0)}/${Number(qualityGate.required_text_units || 0) || "-"} 字，${(qualityGate.issues || []).map((item) => item.issue_code).filter(Boolean).join(" / ") || qualityGate.enforced_decision || "rewrite"}`,
    "error"
  );
  return true;
}

function normalizedAuthorErrorDetail(error) {
  const detail = parseErrorDetail(error);
  return detail?.detail && typeof detail.detail === "object" ? detail.detail : detail;
}

function formatAuthorApiErrorMessage(error, fallbackMessage) {
  const detail = normalizedAuthorErrorDetail(error) || {};
  const code = String(detail.code || "").trim();
  const reason = String(detail.reason || "").trim();
  const status = Number(error?.status || 0);
  if (code === "auth_token_invalid" || code === "auth_token_missing" || status === 401) {
    return "作者登录已失效，请先在“账户协作”里重新登录。";
  }
  if (code === "author_work_identity_required") {
    return "当前还没有作者登录态。请先在“账户协作”里登录正确作者账号。";
  }
  if (code === "author_work_forbidden") {
    return "当前账号没有这份 Draft 的访问权限，请切换到正确作者账号后再试。";
  }
  if (code === "author_entitlement_required") {
    const requiredTier = detail.required_display_name || tierLabel(detail.required_tier) || "所需权益";
    return `当前不能继续这一步：${accessReasonLabel(detail.reason)}。需要 ${requiredTier}。`;
  }
  if (status === 404) {
    return "当前 Draft 或关联对象不存在，请刷新后重试。";
  }
  if (code === "chapter_quality_guard_failed") {
    return "章节硬约束未通过，请先修正文长、问题码和连续性后再试。";
  }
  if (code === "author_collaboration_forbidden" || status === 403) {
    return "当前账号暂时没有执行这个创作动作的权限。";
  }
  const detailMessage = [detail.message, detail.detail, reason]
    .find((value) => typeof value === "string" && value.trim() && !value.includes("{") && value !== code);
  if (detailMessage) {
    return `${fallbackMessage}：${detailMessage.trim()}`;
  }
  const rawMessage = String(error?.message || "").trim();
  if (rawMessage && rawMessage !== "[object Object]" && !rawMessage.startsWith("{")) {
    return `${fallbackMessage}：${rawMessage}`;
  }
  return fallbackMessage;
}

function shouldPromptAuthorLoginForDeepLink() {
  if (typeof window === "undefined" || shellState.activeProduct !== "author" || authorState.authorAuthSession?.accessToken) {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  return Boolean(params.get("draft_id") && params.get("account_id"));
}

function shouldPromptAuthorAccountSwitchForDeepLink(currentAccountId = "") {
  if (typeof window === "undefined" || shellState.activeProduct !== "author" || !authorState.authorAuthSession?.accessToken) {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  const draftId = params.get("draft_id") || "";
  const expectedAccountId = expectedDraftAuthorAccountId();
  const normalizedCurrent = String(currentAccountId || authorState.authorAuthSession?.identity?.account_id || "").trim();
  return Boolean(draftId && expectedAccountId && normalizedCurrent && expectedAccountId !== normalizedCurrent);
}

function authorDeepLinkResumeUrl(preferredAccountId = "") {
  if (typeof window === "undefined" || shellState.activeProduct !== "author") return "";
  const params = new URLSearchParams(window.location.search);
  const draftId = params.get("draft_id") || authorState.activeDraftVersionId || "";
  const deepLinkAccountId = expectedDraftAuthorAccountId();
  const sessionAccountId = String(authorState.authorAuthSession?.identity?.account_id || "").trim();
  const resolvedAccountId = String(preferredAccountId || sessionAccountId || "").trim();
  const hasAuthorSession = Boolean(authorState.authorAuthSession?.accessToken && sessionAccountId);
  if (!hasAuthorSession) {
    return "";
  }
  if (!draftId || !deepLinkAccountId || !resolvedAccountId || deepLinkAccountId !== resolvedAccountId) {
    return "";
  }
  const currentUrl = new URL(window.location.href);
  const isDeepLinkEntrySurface =
    currentUrl.pathname === "/app/user" ||
    (currentUrl.pathname === "/app" && currentUrl.searchParams.get("workspace") === "settings");
  if (!isDeepLinkEntrySurface) {
    return "";
  }
  const alreadyResolved =
    currentUrl.pathname === "/app" &&
    currentUrl.searchParams.get("product") === "author" &&
    currentUrl.searchParams.get("workspace") === "draft" &&
    currentUrl.searchParams.get("draft_id") === draftId &&
    currentUrl.searchParams.get("account_id") === resolvedAccountId;
  if (alreadyResolved) return "";
  const next = new URL(window.location.origin + "/app");
  next.searchParams.set("product", "author");
  next.searchParams.set("workspace", "draft");
  next.searchParams.set("draft_id", draftId);
  next.searchParams.set("account_id", resolvedAccountId);
  if (shellState.debug || currentUrl.searchParams.get("debug") === "1") {
    next.searchParams.set("debug", "1");
  }
  return next.toString();
}

function resumeAuthorDeepLinkIfPossible(preferredAccountId = "") {
  const resumeUrl = authorDeepLinkResumeUrl(preferredAccountId);
  if (!resumeUrl) return false;
  window.location.replace(resumeUrl);
  return true;
}

function ensureAuthorDeepLinkLoginPrompt() {
  if (!shouldPromptAuthorLoginForDeepLink()) return;
  const accountId = expectedDraftAuthorAccountId();
  primeAuthorIdentityInputs(accountId);
  if (shellState.authorWorkspace !== "settings") {
    WorkspaceLayoutRuntime.setAuthorWorkspace("settings", { silent: true });
    ShellStatusRuntime.syncProductMode();
    authorNotice(`登录这个作者后继续创作：${accountId || "当前草稿对应账号"}。`, "info");
  }
}

function clearMismatchedAuthorDeepLinkContext(currentAccountId = "") {
  const normalizedCurrent = String(currentAccountId || authorState.authorAuthSession?.identity?.account_id || "").trim();
  authorState.activeDraftVersionId = null;
  authorState.activeDraftDetail = null;
  authorState.authorValidationReport = null;
  authorState.authorSimulationReport = null;
  authorState.authorPreviousSimulationReport = null;
  authorState.authorWorks = [];
  authorState.activeWorkId = null;
  authorState.activeWorkDetail = null;
  authorState.activeWorkChapterIndex = null;
  authorState.activeWorkChapterDetail = null;
  authorState.activeWorkChapterDraft = null;
  authorState.activeWorkChapterDirty = false;
  authorState.activeWorkSaveState = "idle";
  authorState.authorWorkDiagnostics = null;
  authorState.authorWorkQualityGateFailure = null;
  authorState.pendingAuthorBranchSeed = null;
  if (dom.authorAccountId && normalizedCurrent) {
    dom.authorAccountId.value = normalizedCurrent;
  }
  if (dom.authorAuthActorId && !dom.authorAuthActorId.value.trim() && normalizedCurrent) {
    dom.authorAuthActorId.value = normalizedCurrent;
  }
  if (shellState.authorWorkspace !== "settings") {
    WorkspaceLayoutRuntime.setAuthorWorkspace("settings", { silent: true });
    ShellStatusRuntime.syncProductMode();
  }
  if (typeof RouteSyncRuntime !== "undefined" && typeof RouteSyncRuntime.syncShellRoute === "function") {
    RouteSyncRuntime.syncShellRoute();
  }
}

function ensureAuthorDeepLinkAccountSwitchPrompt(currentAccountId = "") {
  if (!shouldPromptAuthorAccountSwitchForDeepLink(currentAccountId)) return;
  const expectedAccountId = expectedDraftAuthorAccountId();
  clearMismatchedAuthorDeepLinkContext(currentAccountId);
  primeAuthorIdentityInputs(currentAccountId || expectedAccountId);
  authorNotice(
    `当前登录账号 ${currentAccountId || "-"} 和这条创作深链要求的作者账号 ${expectedAccountId || "-"} 不一致。错误深链参数已清除，当前登录会保留；如需继续该草稿，请切换到正确账号后重新打开。`,
    "warning"
  );
}

function normalizeAuthorDraftRouteAccount() {
  if (typeof window === "undefined" || shellState.activeProduct !== "author") return false;
  const expectedAccountId = currentDraftAuthorAccountId();
  if (!expectedAccountId) return false;
  const params = new URLSearchParams(window.location.search);
  const urlAccountId = String(params.get("account_id") || "").trim();
  let changed = false;
  if (dom.authorAccountId && dom.authorAccountId.value.trim() !== expectedAccountId) {
    dom.authorAccountId.value = expectedAccountId;
    changed = true;
  }
  if (dom.authorAuthActorId && !dom.authorAuthActorId.value.trim()) {
    dom.authorAuthActorId.value = expectedAccountId;
  }
  if (urlAccountId !== expectedAccountId) {
    changed = true;
  }
  if (changed && typeof RouteSyncRuntime !== "undefined" && typeof RouteSyncRuntime.syncShellRoute === "function") {
    RouteSyncRuntime.syncShellRoute();
  }
  return changed;
}

function authorWorkStatusLabel(status) {
  return {
    draft: "创作中",
    review_ready: "可送审",
    submitted: "已送审",
    approved: "已批准",
    needs_changes: "待修改",
  }[String(status || "").toLowerCase()] || status || "-";
}

function authorWorkStatusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["review_ready", "approved"].includes(normalized)) return "is-complete";
  if (["submitted"].includes(normalized)) return "is-active";
  if (["needs_changes"].includes(normalized)) return "is-blocked";
  return "is-pending";
}

function authorWorkNextAction(work) {
  if (!work) return "初始化作品稿";
  if (!Number(work.chapter_count || 0)) return "生成第一章";
  if (work.status === "review_ready") return "送审作品稿";
  if (work.status === "submitted") return "等待审阅结果";
  if (work.status === "needs_changes") return "修订后重跑诊断";
  return "生成下一章";
}

function buildAuthorWorkDraft(chapter) {
  if (!chapter) return null;
  return {
    chapter_index: Number(chapter.chapter_index || 0) || null,
    chapter_title: chapter.chapter_title || "",
    summary: chapter.summary || "",
    body: chapter.body || "",
  };
}

function activeAuthorWorkDraft() {
  return authorState.activeWorkChapterDraft || buildAuthorWorkDraft(authorState.activeWorkChapterDetail?.chapter || null);
}

function isAuthorWorkDraftDirty() {
  return Boolean(authorState.activeWorkChapterDirty);
}

function chapterDraftMatchesDetail(draft, chapter) {
  if (!draft || !chapter) return false;
  return (
    String(draft.chapter_title || "") === String(chapter.chapter_title || "") &&
    String(draft.summary || "") === String(chapter.summary || "") &&
    String(draft.body || "") === String(chapter.body || "")
  );
}

function syncAuthorWorkDraftFromDetail(chapterPayload, options = {}) {
  const chapter = chapterPayload?.chapter || null;
  if (!chapter) {
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    return;
  }
  const nextDraft = buildAuthorWorkDraft(chapter);
  const sameChapter = Number(authorState.activeWorkChapterDraft?.chapter_index || 0) === Number(nextDraft?.chapter_index || 0);
  if (options.preserveDirty && sameChapter && authorState.activeWorkChapterDirty) {
    return;
  }
  authorState.activeWorkChapterDraft = nextDraft;
  authorState.activeWorkChapterDirty = false;
  authorState.activeWorkSaveState = "idle";
}

function discardAuthorWorkDraft() {
  authorState.activeWorkChapterDirty = false;
  authorState.activeWorkSaveState = "idle";
  authorState.activeWorkChapterDraft = buildAuthorWorkDraft(authorState.activeWorkChapterDetail?.chapter || null);
}

function summarizeAuthorExecutionError(error) {
  const detail = parseErrorDetail(error);
  const resolved = detail?.detail && typeof detail.detail === "object" ? detail.detail : detail;
  const message =
    resolved?.message ||
    resolved?.detail ||
    resolved?.code ||
    (typeof error?.message === "string" ? error.message : "") ||
    "未知错误";
  return String(message || "未知错误").trim();
}

function clearAuthorBranchExecutionState(options = {}) {
  authorState.authorBranchExecutionState = null;
  if (options.silent) return;
  renderAuthorSteeringComposer();
  refreshAuthorWorkEditorChrome();
}

function setAuthorBranchExecutionState(nextState) {
  authorState.authorBranchExecutionState = {
    ...(authorState.authorBranchExecutionState || {}),
    ...nextState,
    updated_at: new Date().toISOString(),
  };
  renderAuthorSteeringComposer();
  refreshAuthorWorkEditorChrome();
}

function buildAuthorBranchExecutionPresentation() {
  const state = authorState.authorBranchExecutionState || null;
  if (!state) {
    return {
      title: "命运线执行状态",
      score: "尚未执行",
      body: "点击“带着引导重跑 Simulation”后，这里会明确显示创建分支成功 / 失败，以及当前分支已生成到第几章。",
      tone: "neutral",
      inlineText: "",
    };
  }
  const branchName = String(state.branchName || "平行宇宙").trim() || "平行宇宙";
  const forkAfterChapterIndex = Number(state.forkAfterChapterIndex || 0) || 0;
  const nextChapterIndex = Number(state.nextChapterIndex || (forkAfterChapterIndex > 0 ? forkAfterChapterIndex + 1 : 0)) || 0;
  const currentChapterCount = Number(state.currentChapterCount || 0) || 0;
  const errorMessage = String(state.errorMessage || state.message || "").trim();
  const currentRevision = state.currentRevision ? ` · ${state.currentRevision}` : "";
  switch (state.stage) {
    case "branch_pending":
      return {
        title: "命运线执行状态",
        score: "创建分支中",
        body: `正在从第 ${forkAfterChapterIndex || "-"} 章后创建新命运线。\n成功后会继续生成第 ${nextChapterIndex || "-"} 章，不会改写过去章节。`,
        tone: "running",
        inlineText: `正在从第 ${forkAfterChapterIndex || "-"} 章后创建新命运线。`,
      };
    case "generate_pending":
      return {
        title: "命运线执行状态",
        score: `正在生成第 ${nextChapterIndex || "-"} 章`,
        body: `创建分支成功 · ${branchName}\n分叉点：第 ${forkAfterChapterIndex || "-"} 章后\n当前分支停在第 ${currentChapterCount || forkAfterChapterIndex || "-"} 章，正在按本次引导生成第 ${nextChapterIndex || "-"} 章。`,
        tone: "running",
        inlineText: `已创建 ${branchName}，正在生成第 ${nextChapterIndex || "-"} 章。`,
      };
    case "generate_succeeded":
      return {
        title: "命运线执行状态",
        score: `已生成第 ${currentChapterCount || nextChapterIndex || "-"} 章`,
        body: `创建分支成功 · ${branchName}\n分叉点：第 ${forkAfterChapterIndex || "-"} 章后\n当前分支已生成到第 ${currentChapterCount || nextChapterIndex || "-"} 章${currentRevision}\n这条命运线后续会沿当前引导继续推进。`,
        tone: "success",
        inlineText: `已创建 ${branchName}，并生成第 ${currentChapterCount || nextChapterIndex || "-"} 章。`,
      };
    case "generate_failed":
      return {
        title: "命运线执行状态",
        score: "生成失败",
        body: `创建分支成功 · ${branchName}\n分叉点：第 ${forkAfterChapterIndex || "-"} 章后\n当前分支仍停在第 ${currentChapterCount || forkAfterChapterIndex || "-"} 章，未能生成第 ${nextChapterIndex || "-"} 章。\n错误：${errorMessage || "未知错误"}`,
        tone: "warning",
        inlineText: `已创建 ${branchName}，但第 ${nextChapterIndex || "-"} 章生成失败。`,
      };
    case "branch_create_failed":
      return {
        title: "命运线执行状态",
        score: "创建失败",
        body: `创建新命运线失败，当前仍停留在原命运线。\n计划分叉点：第 ${forkAfterChapterIndex || "-"} 章后 · 目标章节：第 ${nextChapterIndex || "-"} 章\n错误：${errorMessage || "未知错误"}`,
        tone: "danger",
        inlineText: `创建新命运线失败：${errorMessage || "未知错误"}`,
      };
    default:
      return {
        title: "命运线执行状态",
        score: "尚未执行",
        body: "点击“带着引导重跑 Simulation”后，这里会明确显示创建分支成功 / 失败，以及当前分支已生成到第几章。",
        tone: "neutral",
        inlineText: "",
      };
  }
}

function refreshAuthorWorkEditorChrome() {
  const stateNode = document.querySelector("#author-work-editor-state");
  const saveButton = document.querySelector("#author-save-work-chapter");
  const dirtyPill = document.querySelector("#author-work-dirty-pill");
  const chapterHeadline = document.querySelector("#author-work-editor-current-chapter");
  const chapter = authorState.activeWorkChapterDetail?.chapter || null;
  if (chapterHeadline) {
    chapterHeadline.textContent = chapter ? `第 ${chapter.chapter_index} 章` : "未选择章节";
  }
  const isDirty = Boolean(authorState.activeWorkChapterDirty);
  const saveState = authorState.activeWorkSaveState || "idle";
  const branchExecution = buildAuthorBranchExecutionPresentation();
  const baseTone =
    saveState === "blocked" ? "warning" : isDirty ? "warning" : saveState === "saved" ? "success" : "neutral";
  if (dirtyPill) {
    dirtyPill.textContent =
      saveState === "blocked" ? "未入库" : isDirty ? "未保存改动" : saveState === "saved" ? "已保存" : "已同步";
    dirtyPill.dataset.tone =
      saveState === "blocked" ? "warning" : isDirty ? "warning" : saveState === "saved" ? "success" : "neutral";
  }
  if (stateNode) {
    const baseText =
      saveState === "saving"
        ? "正在保存当前章节…"
        : saveState === "blocked"
          ? "未保存，未通过章节硬约束。先补足字数、场景动作或节奏问题，再重试。"
        : isDirty
          ? "当前章节有未保存改动，切章前会提示确认。"
          : saveState === "saved"
            ? "当前章节已保存，可以继续生成、诊断或送审。"
            : "当前章节与服务器已同步。";
    stateNode.textContent = branchExecution.inlineText ? `${baseText}\n${branchExecution.inlineText}` : baseText;
    stateNode.dataset.tone =
      saveState === "saving" || saveState === "blocked" || isDirty ? baseTone : branchExecution.tone || baseTone;
  }
  if (saveButton) {
    saveButton.disabled = !chapter || saveState === "saving" || !isDirty;
    saveButton.textContent = saveState === "saving" ? "保存中…" : "保存当前章节";
  }
}

function updateAuthorWorkDraftField(field, value) {
  const chapter = authorState.activeWorkChapterDetail?.chapter || null;
  if (!chapter) return;
  const currentDraft = activeAuthorWorkDraft() || buildAuthorWorkDraft(chapter);
  const nextDraft = {
    ...currentDraft,
    [field]: value,
  };
  authorState.activeWorkChapterDraft = nextDraft;
  authorState.activeWorkChapterDirty = !chapterDraftMatchesDetail(nextDraft, chapter);
  if (authorState.activeWorkChapterDirty) {
    authorState.activeWorkSaveState = "idle";
  }
  refreshAuthorWorkEditorChrome();
}

function confirmAuthorWorkDiscard(message) {
  if (!isAuthorWorkDraftDirty()) return true;
  return window.confirm(message || "当前章节还有未保存改动，确认放弃这些修改吗？");
}

function preferredAuthorWorkChapterIndex(chapters) {
  if (!Array.isArray(chapters) || !chapters.length) return null;
  if (chapters.some((item) => Number(item.chapter_index) === Number(authorState.activeWorkChapterIndex))) {
    return Number(authorState.activeWorkChapterIndex);
  }
  return Number(chapters[chapters.length - 1].chapter_index);
}

async function refreshAuthorWorks(accountId) {
  authorState.authorWorkQualityGateFailure = null;
  if (!authorState.activeDraftVersionId || !accountId) {
    authorState.authorWorks = [];
    authorState.activeWorkId = null;
    authorState.activeWorkDetail = null;
    authorState.activeWorkChapterIndex = null;
    authorState.activeWorkChapterDetail = null;
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    authorState.authorBranchExecutionState = null;
    authorState.authorWorkDiagnostics = null;
    authorState.authorWorkQualityGateFailure = null;
    return;
  }
  const payload = await api(
    `/v1/author/works?account_id=${encodeURIComponent(accountId)}&world_version_id=${encodeURIComponent(authorState.activeDraftVersionId)}`
  );
  authorState.authorWorks = payload.works || [];
  if (!authorState.authorWorks.length) {
    authorState.activeWorkId = null;
    authorState.activeWorkDetail = null;
    authorState.activeWorkChapterIndex = null;
    authorState.activeWorkChapterDetail = null;
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    authorState.authorBranchExecutionState = null;
    authorState.authorWorkDiagnostics = null;
    authorState.authorWorkQualityGateFailure = null;
    return;
  }
  if (!authorState.authorWorks.some((item) => item.work_id === authorState.activeWorkId)) {
    authorState.activeWorkId = (authorState.authorWorks.find((item) => item.is_active_line) || authorState.authorWorks[0]).work_id;
  }
  authorState.activeWorkDetail = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}`);
  authorState.authorWorkDiagnostics = authorState.activeWorkDetail?.diagnostics_summary || authorState.activeWorkDetail?.diagnostics_summary_json || null;
  const chapters = authorState.activeWorkDetail?.chapters || [];
  if (!chapters.length) {
    authorState.activeWorkChapterIndex = null;
    authorState.activeWorkChapterDetail = null;
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    return;
  }
  authorState.activeWorkChapterIndex = preferredAuthorWorkChapterIndex(chapters);
  authorState.activeWorkChapterDetail = await api(
    `/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/${encodeURIComponent(authorState.activeWorkChapterIndex)}`
  );
  syncAuthorWorkDraftFromDetail(authorState.activeWorkChapterDetail, { preserveDirty: true });
}

async function switchActiveAuthorWork(workId, options = {}) {
  const normalized = String(workId || "").trim();
  if (!normalized || normalized === authorState.activeWorkId) return;
  if (
    !options.force &&
    !confirmAuthorWorkDiscard("当前章节还有未保存改动，切换到另一条命运线会放弃这些本地修改。确认继续吗？")
  ) {
    return;
  }
  const activated = await api(`/v1/author/works/${encodeURIComponent(normalized)}/activate-line`, {
    method: "POST",
    body: JSON.stringify({
      account_id: activeAuthorAccountId() || null,
    }),
  });
  authorState.activeWorkId = activated.work_id || normalized;
  authorState.pendingAuthorBranchSeed = null;
  clearAuthorBranchExecutionState({ silent: true });
  await refreshAuthorWorks(activeAuthorAccountId());
  renderAuthorReports();
}

async function createAuthorWorkFromDraft() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  if (!confirmAuthorWorkDiscard("当前章节还有未保存改动，初始化或刷新作品稿会覆盖当前编辑器内容。确认继续吗？")) {
    return;
  }
  try {
    const payload = await api("/v1/author/works", {
      method: "POST",
      body: JSON.stringify({
        world_version_id: authorState.activeDraftVersionId,
        account_id: activeAuthorAccountId() || null,
      }),
    });
    authorState.activeWorkId = payload.work_id;
    authorState.authorWorkQualityGateFailure = null;
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    clearAuthorBranchExecutionState({ silent: true });
    await refreshAuthorWorks(activeAuthorAccountId());
    if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.refreshAuthoredWorkLibrary === "function") {
      ReaderRuntime.refreshAuthoredWorkLibrary().catch(() => {});
    }
    renderAuthorReports();
  } catch (error) {
    if (handleAuthorWorkAccessError(error, "初始化作品稿")) {
      return;
    }
    throw error;
  }
}

async function generateAuthorWork(mode) {
  if (!authorState.activeWorkId) {
    authorNotice("先初始化作品稿。");
    return null;
  }
  if (!confirmAuthorWorkDiscard("当前章节还有未保存改动。生成新章节前需要先保存，或确认放弃本地修改。确认继续吗？")) {
    return null;
  }
  try {
    const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/generate`, {
      method: "POST",
      body: JSON.stringify({
        mode,
        account_id: activeAuthorAccountId() || null,
      }),
    });
    authorState.activeWorkDetail = payload;
    authorState.authorWorkDiagnostics = payload?.diagnostics_summary || payload?.diagnostics_summary_json || null;
    authorState.authorWorkQualityGateFailure = null;
    const chapters = payload?.chapters || [];
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.activeWorkSaveState = "idle";
    if (chapters.length) {
      authorState.activeWorkChapterIndex = chapters[chapters.length - 1].chapter_index;
      authorState.activeWorkChapterDetail = await api(
        `/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/${encodeURIComponent(authorState.activeWorkChapterIndex)}`
      );
      syncAuthorWorkDraftFromDetail(authorState.activeWorkChapterDetail);
    }
    await refreshAuthorWorks(activeAuthorAccountId());
    if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.refreshAuthoredWorkLibrary === "function") {
      ReaderRuntime.refreshAuthoredWorkLibrary().catch(() => {});
    }
    renderAuthorReports();
    return payload;
  } catch (error) {
    if (handleAuthorWorkQualityGateError(error, "生成章节")) {
      return null;
    }
    if (handleAuthorWorkAccessError(error, "生成章节")) {
      return null;
    }
    throw error;
  }
}

async function loadAuthorWorkChapter(chapterIndex, options = {}) {
  if (!authorState.activeWorkId) return;
  const normalizedIndex = Number(chapterIndex || 0);
  if (!normalizedIndex) return;
  if (
    !options.force &&
    Number(authorState.activeWorkChapterIndex || 0) !== normalizedIndex &&
    !confirmAuthorWorkDiscard("当前章节还有未保存改动，确认切换到另一章并放弃这些修改吗？")
  ) {
    return;
  }
  try {
    authorState.activeWorkChapterIndex = normalizedIndex;
    authorState.activeWorkChapterDetail = await api(
      `/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/${encodeURIComponent(authorState.activeWorkChapterIndex)}`
    );
    syncAuthorWorkDraftFromDetail(authorState.activeWorkChapterDetail);
    renderAuthorReports();
  } catch (error) {
    if (handleAuthorWorkAccessError(error, "加载章节")) {
      return;
    }
    throw error;
  }
}

async function saveAuthorWorkChapter() {
  if (!authorState.activeWorkId || !authorState.activeWorkChapterIndex) {
    authorNotice("先选择一个章节。");
    return;
  }
  if (!isAuthorWorkDraftDirty()) {
    authorNotice("当前章节没有未保存改动。", "warning");
    return;
  }
  const draft = activeAuthorWorkDraft();
  if (!draft) {
    authorNotice("当前章节还没有可保存内容。", "warning");
    return;
  }
  authorState.activeWorkSaveState = "saving";
  refreshAuthorWorkEditorChrome();
  try {
    const payload = await api(
      `/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/${encodeURIComponent(authorState.activeWorkChapterIndex)}/edit`,
      {
        method: "POST",
        body: JSON.stringify({
          chapter_title: draft.chapter_title || null,
          body: draft.body || null,
          summary: draft.summary || null,
          account_id: activeAuthorAccountId() || null,
        }),
      }
    );
    authorState.activeWorkDetail = payload.work;
    authorState.activeWorkChapterDetail = { work: payload.work, chapter: payload.chapter };
    authorState.authorWorkDiagnostics = payload.work?.diagnostics_summary || payload.work?.diagnostics_summary_json || null;
    authorState.authorWorkQualityGateFailure = null;
    syncAuthorWorkDraftFromDetail(authorState.activeWorkChapterDetail);
    authorState.activeWorkSaveState = "saved";
    renderAuthorReports();
    authorNotice("当前章节已保存。", "success");
  } catch (error) {
    authorState.activeWorkSaveState = "idle";
    refreshAuthorWorkEditorChrome();
    if (handleAuthorWorkQualityGateError(error, "保存章节")) {
      return;
    }
    if (handleAuthorWorkAccessError(error, "保存章节")) {
      return;
    }
    throw error;
  }
}

async function runAuthorWorkDiagnostics() {
  if (!authorState.activeWorkId) {
    authorNotice("先初始化作品稿。");
    return;
  }
  if (isAuthorWorkDraftDirty()) {
    authorNotice("先保存当前章节，再运行作品诊断。", "warning");
    return;
  }
  try {
    const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/diagnostics/run`, {
      method: "POST",
      body: JSON.stringify({
        account_id: activeAuthorAccountId() || null,
      }),
    });
    authorState.activeWorkDetail = payload.work;
    authorState.authorWorkDiagnostics = payload.work?.diagnostics_summary || payload.work?.diagnostics_summary_json || null;
    await refreshAuthorWorks(activeAuthorAccountId());
    renderAuthorReports();
  } catch (error) {
    if (handleAuthorWorkAccessError(error, "运行作品诊断")) {
      return;
    }
    throw error;
  }
}

async function submitAuthorWorkForReview() {
  if (!authorState.activeWorkId) {
    authorNotice("先初始化作品稿。");
    return;
  }
  if (isAuthorWorkDraftDirty()) {
    authorNotice("先保存当前章节，再送审作品稿。", "warning");
    return;
  }
  try {
    const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/submit`, {
      method: "POST",
      body: JSON.stringify({
        account_id: activeAuthorAccountId() || null,
      }),
    });
    authorState.activeWorkDetail = payload;
    authorState.authorWorkDiagnostics = payload?.diagnostics_summary || payload?.diagnostics_summary_json || null;
    await refreshAuthorWorks(activeAuthorAccountId());
    renderAuthorReports();
  } catch (error) {
    if (handleAuthorWorkAccessError(error, "送审作品稿")) {
      return;
    }
    throw error;
  }
}

function jumpToAuthorChapter(chapterIndex, panelKey = "simulation") {
  const normalized = Math.max(1, Number(chapterIndex || 0));
  if (!normalized) return;
  authorState.selectedAuthorSimulationChapterIndex = normalized;
  authorState.selectedAuthorContinuityChapterIndex = normalized;
  renderAuthorReports();
  focusAuthorPanel(panelKey);
}

function activeAuthorReviewerId() {
  return (
    dom.authorInboxReviewerId?.value.trim() ||
    (authorSessionCanReview() ? authorState.authorAuthSession.identity.actor_id : "") ||
    dom.authorApprovalReviewer?.value.trim() ||
    ""
  );
}

function authorSessionCanReview() {
  return ["reviewer", "ops", "admin", "editor"].includes(
    String(authorState.authorAuthSession?.identity?.actor_role || "").trim()
  );
}

function hasAuthorAuthenticatedSession() {
  return Boolean(
    authorState.authorAuthSession?.accessToken ||
      (authorState.authorAuthSession?.cookieBacked && authorState.authorAuthSession?.identity)
  );
}

function syncReviewerWorkbenchDefaults() {
  const actorId = String(authorState.authorAuthSession?.identity?.actor_id || "").trim();
  if (!actorId || !authorSessionCanReview()) return;
  if (dom.authorInboxReviewerId && !dom.authorInboxReviewerId.value.trim()) {
    dom.authorInboxReviewerId.value = actorId;
  }
  if (dom.authorApprovalReviewer && !dom.authorApprovalReviewer.value.trim()) {
    dom.authorApprovalReviewer.value = actorId;
  }
}

async function syncReaderMirrorFromAuthorSession() {
  if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.mirrorReaderAuthSession === "function") {
    await ReaderRuntime.mirrorReaderAuthSession(authorState.authorAuthSession);
  }
}

function activeAuthorActorId(options = {}) {
  if (options.preferReviewer) {
    return activeAuthorReviewerId() || dom.authorAccountId?.value.trim() || "";
  }
  return authorState.authorAuthSession?.identity?.actor_id || dom.authorAccountId?.value.trim() || activeAuthorReviewerId() || "";
}

function activeAuthorActorRole(actorId = activeAuthorActorId()) {
  if (authorState.authorAuthSession?.identity?.actor_role) {
    return authorState.authorAuthSession.identity.actor_role;
  }
  const draftAuthorId = authorState.activeDraftDetail?.worldpack?.manifest?.author_id || "";
  return actorId && draftAuthorId && actorId === draftAuthorId ? "author" : "reviewer";
}

function currentAuthorInboxFilters() {
  return {
    reviewerId: activeAuthorReviewerId(),
    statusFilter: dom.authorInboxStatusFilter?.value || "all",
    worldVersionId: dom.authorInboxWorldVersionFilter?.value.trim() || "",
    notificationType: dom.authorInboxNotificationTypeFilter?.value || "",
    blockingOnly: Boolean(dom.authorInboxBlockingOnly?.checked),
    query: (dom.authorInboxSearch?.value || "").trim(),
  };
}

function authorCollaborationHeaders(options = {}) {
  void options;
  const token = String(authorState.authorAuthSession?.accessToken || "").trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function selectAuthorThread(threadId, worldVersionId = "") {
  authorState.selectedAuthorThreadId = threadId || null;
  if (worldVersionId && worldVersionId !== authorState.activeDraftVersionId) {
    authorState.activeDraftVersionId = worldVersionId;
    await refreshAuthorSurface();
    return;
  }
  renderAuthorReports();
  focusAuthorPanel("collaboration");
}

function mergeAuthorReviewerInbox(existing, nextPayload) {
  if (!existing) {
    return nextPayload;
  }
  const mergedNotifications = [...(existing.notifications || []), ...(nextPayload.notifications || [])];
  const seen = new Set();
  const uniqueNotifications = [];
  for (const item of mergedNotifications) {
    if (!item?.notification_id || seen.has(item.notification_id)) continue;
    seen.add(item.notification_id);
    uniqueNotifications.push(item);
  }
  return {
    ...existing,
    filters: nextPayload.filters || existing.filters,
    has_more: nextPayload.has_more,
    next_cursor: nextPayload.next_cursor,
    returned_count: uniqueNotifications.length,
    notifications: uniqueNotifications,
    unread_notifications: uniqueNotifications.filter((item) => item.status === "unread"),
  };
}

function syncAuthorNotificationPreferenceInputs() {
  const targetType = dom.authorNotificationPrefType?.value || "thread_assigned";
  const preferences = authorState.authorNotificationPreferences?.preferences || [];
  const selected = preferences.find((item) => item.notification_type === targetType);
  if (dom.authorNotificationPrefInApp) {
    dom.authorNotificationPrefInApp.checked = selected ? Boolean(selected.in_app_enabled) : true;
  }
  if (dom.authorNotificationPrefAsync) {
    dom.authorNotificationPrefAsync.checked = selected ? Boolean(selected.async_mirror_enabled) : true;
  }
  if (dom.authorNotificationPrefSink) {
    dom.authorNotificationPrefSink.value = selected?.async_sink_name || "default";
  }
  if (dom.authorNotificationPrefTarget) {
    dom.authorNotificationPrefTarget.value = selected?.delivery_target || "";
  }
}

function persistAuthorAuthSession() {
  if (typeof window === "undefined") return;
  if (authorState.authorAuthSession?.accessToken || (authorState.authorAuthSession?.cookieBacked && authorState.authorAuthSession?.identity)) {
    window.localStorage.setItem("narrativeos_author_auth", JSON.stringify(authorState.authorAuthSession));
  } else {
    window.localStorage.removeItem("narrativeos_author_auth");
  }
}

function clearAuthorAuthSessionLocal() {
  authorState.authorAuthSession = null;
  persistAuthorAuthSession();
  renderAuthorAuthStatus();
}

function restoreAuthorAuthSession() {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem("narrativeos_author_auth");
    if (!raw) {
      if (authorState.authorAuthSession?.identity) return;
      authorState.authorAuthSession = null;
      return;
    }
    authorState.authorAuthSession = JSON.parse(raw);
  } catch (_error) {
    authorState.authorAuthSession = null;
  }
}

function renderAuthorAuthStatus() {
  clearNode(dom.authorAuthStatus);
  const session = authorState.authorAuthSession;
  if (!session?.identity) {
    clearNode(dom.authorAuthStatus, "这里会显示当前账号信息与登录状态。");
    return;
  }
  dom.authorAuthStatus.appendChild(
    createListCard({
      title: `${session.identity.display_name || session.identity.actor_id || "-"} · 已登录`,
      score: "账号状态",
      body:
        `账号 ${session.identity.account_id || "-"}\n` +
        `显示名称 ${session.identity.display_name || "-"}\n` +
        `登录有效期 ${session.expiresAt || "-"}`
    })
  );
}

async function refreshAuthorReviewerInbox(options = {}) {
  const { reviewerId, statusFilter, worldVersionId, notificationType, blockingOnly, query: searchQuery } = currentAuthorInboxFilters();
  if (!hasAuthorAuthenticatedSession() || !authorSessionCanReview() || !reviewerId) {
    authorState.authorReviewerInbox = null;
    authorState.authorReviewerInboxNextCursor = null;
    authorState.authorReviewerInboxHasMore = false;
    return;
  }
  const params = new URLSearchParams();
  params.set("reviewer_id", reviewerId);
  params.set("limit", "12");
  params.set("status_filter", statusFilter);
  if (worldVersionId) {
    params.set("world_version_id", worldVersionId);
  }
  if (notificationType) {
    params.set("notification_type", notificationType);
  }
  if (blockingOnly) {
    params.set("blocking_only", "true");
  }
  if (searchQuery) {
    params.set("q", searchQuery);
  }
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const payload = await api(`/v1/author/reviewer-inbox?${params.toString()}`, {
    headers: authorCollaborationHeaders({ preferReviewer: true }),
  });
  authorState.authorReviewerInbox = options.append ? mergeAuthorReviewerInbox(authorState.authorReviewerInbox, payload) : payload;
  authorState.authorReviewerInboxNextCursor = payload.next_cursor || null;
  authorState.authorReviewerInboxHasMore = Boolean(payload.has_more);
  authorState.authorReviewerInboxSearch = searchQuery;
}

async function updateAuthorThreadStatusInline(threadId, status, options = {}) {
  const body = options.body || "";
  const actorId = options.actorId || activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/status`, {
    method: "POST",
    headers: authorCollaborationHeaders({
      actorId,
      actorRole: options.actorRole || activeAuthorActorRole(actorId),
    }),
    body: JSON.stringify({
      status,
      assignee_id: options.assigneeId === undefined ? undefined : options.assigneeId,
      actor_id: actorId,
      actor_role: options.actorRole || activeAuthorActorRole(actorId),
      body: body || undefined,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function updateAuthorNotificationStatus(notificationId, status) {
  if (!hasAuthorAuthenticatedSession()) {
    authorNotice("请先登录当前通知所属账号。", "warning");
    return;
  }
  await api(`/v1/author/notifications/${encodeURIComponent(notificationId)}/status`, {
    method: "POST",
    headers: authorCollaborationHeaders({ preferReviewer: true }),
    body: JSON.stringify({
      status,
      recipient_id: activeAuthorReviewerId(),
      limit: 12,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function bulkUpdateAuthorNotificationStatus(status) {
  if (!hasAuthorAuthenticatedSession()) {
    authorNotice("请先登录当前通知所属账号。", "warning");
    return;
  }
  const notificationIds = authorState.authorReviewerInboxVisibleNotificationIds || [];
  if (!notificationIds.length) {
    authorNotice("当前没有可批量处理的 notifications。");
    return;
  }
  await api("/v1/author/notifications/bulk-status", {
    method: "POST",
    headers: authorCollaborationHeaders({ preferReviewer: true }),
    body: JSON.stringify({
      notification_ids: notificationIds,
      recipient_id: activeAuthorReviewerId(),
      status,
      limit: 12,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function decideAuthorApprovalForWorld(worldVersionId, status, reviewerId, reason) {
  await api(`/v1/author/drafts/${encodeURIComponent(worldVersionId)}/approval/decision`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId: reviewerId || activeAuthorReviewerId(), actorRole: "reviewer" }),
    body: JSON.stringify({
      reviewer_id: reviewerId || activeAuthorReviewerId(),
      status,
      reason: reason || (status === "approved" ? "Reviewer inbox 快速批准。" : "Reviewer inbox 要求修改。"),
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function addAuthorThreadWatcher(threadId, watcherId = "") {
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/watchers`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId || actorId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function removeAuthorThreadWatcher(threadId, watcherId) {
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/watchers/${encodeURIComponent(watcherId)}/remove`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function replyToSelectedAuthorThread(threadId) {
  const body = (authorState.authorInlineReplyDraft || "").trim();
  if (!body) {
    authorNotice("先写回复内容。");
    return;
  }
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/reply`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
      body,
    }),
  });
  authorState.authorInlineReplyDraft = "";
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function addAuthorDraftWatcher() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const watcherId = (dom.authorDraftWatcherId?.value || "").trim() || activeAuthorActorId();
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${encodeURIComponent(authorState.activeDraftVersionId)}/watchers`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function removeAuthorDraftWatcher() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const watcherId = (dom.authorDraftWatcherId?.value || "").trim();
  if (!watcherId) {
    authorNotice("先填写 draft watcher id。");
    return;
  }
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${encodeURIComponent(authorState.activeDraftVersionId)}/watchers/${encodeURIComponent(watcherId)}/remove`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function refreshAuthorNotificationPreferences() {
  const actorId = activeAuthorActorId();
  if (!actorId || !hasAuthorAuthenticatedSession()) {
    authorState.authorNotificationPreferences = null;
    return;
  }
  authorState.authorNotificationPreferences = await api(
    `/v1/author/notification-preferences?actor_id=${encodeURIComponent(actorId)}`,
    {
      headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    }
  );
  syncAuthorNotificationPreferenceInputs();
}

async function saveAuthorNotificationPreference() {
  const actorId = activeAuthorActorId();
  if (!actorId || !hasAuthorAuthenticatedSession()) {
    authorNotice("请先登录要更新通知设置的账号。", "warning");
    return;
  }
  await api("/v1/author/notification-preferences", {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      notification_type: dom.authorNotificationPrefType?.value || "thread_assigned",
      in_app_enabled: Boolean(dom.authorNotificationPrefInApp?.checked),
      async_mirror_enabled: Boolean(dom.authorNotificationPrefAsync?.checked),
      async_sink_name: dom.authorNotificationPrefSink?.value || "default",
      delivery_target: (dom.authorNotificationPrefTarget?.value || "").trim() || null,
    }),
  });
  await refreshAuthorNotificationPreferences();
  renderAuthorReports();
}

async function registerAuthorAuthIdentity() {
  const actorId = (dom.authorAuthActorId?.value || "").trim() || activeAuthorActorId();
  const password = (dom.authorAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    authorNotice("请先填写 actor id 和 password。");
    return;
  }
  await api("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      actor_id: actorId,
      actor_role: dom.authorAuthRole?.value || "author",
      password,
      account_id: dom.authorAccountId?.value.trim() || actorId,
      display_name: (dom.authorAuthDisplayName?.value || "").trim() || null,
    }),
  });
  if (String(actorId).includes("@")) {
    authorNotice("注册已提交。请先检查验证邮件，完成验证后再登录。", "success");
    return;
  }
  await loginAuthorAuthIdentity();
}

async function loginAuthorAuthIdentity() {
  const actorId = (dom.authorAuthActorId?.value || "").trim() || activeAuthorActorId();
  const password = (dom.authorAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    authorNotice("请先填写 actor id 和 password。");
    return;
  }
  const payload = await api("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({
      actor_id: actorId,
      password,
    }),
  });
  authorState.authorAuthSession = {
    accessToken: payload.token?.access_token,
    expiresAt: payload.token?.expires_at,
    identity: payload.identity,
    tokenType: payload.token?.token_type || "bearer",
    cookieBacked: false,
  };
  persistAuthorAuthSession();
  await syncReaderMirrorFromAuthorSession();
  syncReviewerWorkbenchDefaults();
  if (dom.authorAccountId && payload.identity?.account_id) {
    dom.authorAccountId.value = payload.identity.account_id;
  }
  if (authorSessionCanReview()) {
    shellState.activeProduct = "author";
    shellState.authorWorkspace = "settings";
  }
  if (resumeAuthorDeepLinkIfPossible(payload.identity?.account_id || "")) {
    return;
  }
  renderAuthorAuthStatus();
  await refreshAuthorSurface();
  if (typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.syncProductMode();
    ShellStatusRuntime.updateStatus();
  }
  if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.refreshAuthoredWorkLibrary === "function") {
    ReaderRuntime.refreshAuthoredWorkLibrary().catch(() => {});
  }
}

async function hydrateAuthorAuthSession() {
  const existingSession = authorState.authorAuthSession;
  if (!existingSession?.accessToken && !existingSession?.cookieBacked && !existingSession?.identity) {
    clearAuthorAuthSessionLocal();
    await syncReaderMirrorFromAuthorSession();
    syncReviewerWorkbenchDefaults();
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.syncProductMode();
      ShellStatusRuntime.updateStatus();
    }
    return;
  }
  try {
    const payload = await api(
      "/v1/auth/me",
      existingSession?.accessToken
        ? { headers: { Authorization: `Bearer ${existingSession.accessToken}` } }
        : {}
    );
    authorState.authorAuthSession = {
      ...existingSession,
      accessToken: existingSession?.accessToken || null,
      identity: payload.identity,
      expiresAt: payload.identity?.expires_at || existingSession?.expiresAt || null,
      tokenType: existingSession?.tokenType || "bearer",
      cookieBacked: !existingSession?.accessToken,
    };
    persistAuthorAuthSession();
  } catch (error) {
    clearAuthorAuthSessionLocal();
  }
  if (dom.authorAccountId && authorState.authorAuthSession?.identity?.account_id) {
    dom.authorAccountId.value = authorState.authorAuthSession.identity.account_id;
  }
  if (
    shellState.startupRouteProduct === "ops" &&
    ["reviewer", "ops", "admin"].includes(String(authorState.authorAuthSession?.identity?.actor_role || "").trim())
  ) {
    shellState.activeProduct = "ops";
    if (shellState.startupRouteWorkspace) {
      shellState.opsWorkspace = shellState.startupRouteWorkspace;
    }
  }
  await syncReaderMirrorFromAuthorSession();
  syncReviewerWorkbenchDefaults();
  renderAuthorAuthStatus();
  if (typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.syncProductMode();
    ShellStatusRuntime.updateStatus();
  }
}

async function logoutAuthorAuthIdentity() {
  if (!authorState.authorAuthSession?.accessToken) {
    clearAuthorAuthSessionLocal();
    await syncReaderMirrorFromAuthorSession();
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.syncProductMode();
      ShellStatusRuntime.updateStatus();
    }
    return;
  }
  try {
    await api("/v1/auth/logout", { method: "POST" });
  } catch (_error) {
    // Even if logout fails remotely, clear local session for safety.
  }
  clearAuthorAuthSessionLocal();
  await syncReaderMirrorFromAuthorSession();
  if (typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.syncProductMode();
    ShellStatusRuntime.updateStatus();
  }
  if (typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.refreshAuthoredWorkLibrary === "function") {
    ReaderRuntime.refreshAuthoredWorkLibrary().catch(() => {});
  }
}

async function validateDraftVersion(worldVersionId) {
  const detail = await api(`/v1/author/drafts/${worldVersionId}`);
  const report = await api("/v1/author/drafts/validate", {
    method: "POST",
    body: JSON.stringify({
      worldpack: detail.worldpack,
      account_id: dom.authorAccountId?.value.trim() || "web_author",
    }),
  });
  authorState.activeDraftVersionId = worldVersionId;
  authorState.activeDraftDetail = detail;
  authorState.selectedAuthorRevisionIndex = null;
  authorState.authorValidationReport = report;
  authorState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  focusAuthorPanel("validation");
  return report;
}

async function simulateDraftVersion(worldVersionId, options = {}) {
  authorState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  authorState.authorPreviousSimulationReport = currentAuthorSimulationReport();
  const interactiveScenarios = Array.isArray(options.interactiveScenarios)
    ? options.interactiveScenarios.filter(Boolean)
    : [];
  const payload = {
    ...(options.accountId ? { account_id: options.accountId } : {}),
    ...(interactiveScenarios.length ? { interactive_scenarios: interactiveScenarios } : {}),
  };
  const report = await api(
    `/v1/author/drafts/${worldVersionId}/simulate`,
    Object.keys(payload).length
      ? { method: "POST", body: JSON.stringify(payload) }
      : { method: "POST" }
  );
  authorState.activeDraftVersionId = worldVersionId;
  authorState.authorSimulationReport = report;
  authorState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  authorState.selectedAuthorRevisionIndex = null;
  authorState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  await refreshOpsSurfaceIfVisible();
  focusAuthorPanel("simulation");
  return report;
}

function currentAuthorSimulationReport() {
  return authorState.activeDraftDetail?.simulation_report || authorState.authorSimulationReport || null;
}

function currentAuthorCreativeCockpit() {
  return currentAuthorSimulationReport()?.creative_cockpit || authorState.activeDraftDetail?.creative_cockpit || null;
}

function selectedMultiValues(selectNode) {
  return Array.from(selectNode?.selectedOptions || [])
    .map((option) => String(option.value || "").trim())
    .filter(Boolean);
}

function setMultiSelectValues(selectNode, values) {
  const selected = new Set((values || []).map((item) => String(item)));
  Array.from(selectNode?.options || []).forEach((option) => {
    option.selected = selected.has(String(option.value || ""));
  });
}

function openAuthorCharacterAsset(characterId) {
  const normalized = String(characterId || "").trim();
  const characters = getActiveDraftCharacters();
  const index = characters.findIndex((character) => String(character.character_id || "") === normalized);
  WorkspaceLayoutRuntime.setAuthorWorkspace("draft", { silent: true });
  setAuthorDraftSection("assets", { silent: true });
  ShellStatusRuntime.syncProductMode();
  if (!characters.length) {
    authorNotice("当前没有可编辑角色，已切到角色卡编辑区。");
    focusAuthorPanel("character_editor");
    return;
  }
  const fallbackIndex = index >= 0 ? index : 0;
  if (dom.authorCharacterSelect) {
    dom.authorCharacterSelect.value = String(fallbackIndex);
  }
  renderCharacterEditor();
  if (!normalized || index < 0) {
    authorNotice("当前热点没有对应到精确角色卡，已打开角色卡编辑区。");
  }
  focusAuthorPanel("character_editor");
}

function openAuthorSceneAsset({ sceneId = "", sceneFunction = "" } = {}) {
  const normalizedSceneId = String(sceneId || "").trim();
  const normalizedSceneFunction = String(sceneFunction || "").trim();
  const scenes = getActiveDraftScenes();
  const index = scenes.findIndex((scene) => {
    const currentSceneId = String(scene.scene_id || "");
    const currentSceneFunction = String(scene.scene_function || "");
    return (
      (normalizedSceneId && currentSceneId === normalizedSceneId) ||
      (!normalizedSceneId && normalizedSceneFunction && currentSceneFunction === normalizedSceneFunction)
    );
  });
  WorkspaceLayoutRuntime.setAuthorWorkspace("draft", { silent: true });
  setAuthorDraftSection("assets", { silent: true });
  ShellStatusRuntime.syncProductMode();
  if (!scenes.length) {
    authorNotice("当前没有可编辑场景，已切到场景蓝图编辑区。");
    focusAuthorPanel("scene_editor");
    return;
  }
  const fallbackIndex = index >= 0 ? index : 0;
  if (dom.authorSceneSelect) {
    dom.authorSceneSelect.value = String(fallbackIndex);
  }
  renderSceneEditor();
  if (index < 0) {
    authorNotice("当前热点没有对应到精确的 scene blueprint，已打开场景蓝图编辑区。");
  }
  focusAuthorPanel("scene_editor");
}

function openAuthorTaskAsset({ volumeId = "", arcId = "", taskId = "" } = {}) {
  const volumePlans = getActiveVolumePlans();
  const arcPlans = getActiveArcPlans();
  let targetArc = null;
  let targetVolume = null;
  let targetTaskId = String(taskId || "").trim();

  if (targetTaskId) {
    targetArc = arcPlans.find((arc) => (arc.chapter_tasks || []).some((task) => String(task.chapter_task_id || "") === targetTaskId)) || null;
  }
  if (!targetArc && arcId) {
    targetArc = arcPlans.find((arc) => String(arc.arc_id || "") === String(arcId)) || null;
  }
  if (!targetArc && volumeId) {
    targetArc = arcPlans.find((arc) => String(arc.volume_id || "") === String(volumeId)) || null;
  }
  targetVolume =
    volumePlans.find((volume) => String(volume.volume_id || "") === String(volumeId || targetArc?.volume_id || "")) ||
    volumePlans[0] ||
    null;
  if (!targetArc && targetVolume) {
    targetArc = arcPlans.find((arc) => String(arc.volume_id || "") === String(targetVolume.volume_id || "")) || null;
  }
  if (!targetTaskId && targetArc) {
    targetTaskId = String(((targetArc.chapter_tasks || [])[0] || {}).chapter_task_id || "");
  }
  authorState.selectedAuthorVolumeId = targetVolume?.volume_id || null;
  authorState.selectedAuthorArcId = targetArc?.arc_id || null;
  authorState.selectedAuthorTaskId = targetTaskId || null;
  if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
  if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
  WorkspaceLayoutRuntime.setAuthorWorkspace("draft", { silent: true });
  setAuthorDraftSection("longform", { silent: true });
  ShellStatusRuntime.syncProductMode();
  if (!targetVolume || !targetArc) {
    authorNotice("当前热点没有对应到精确的 chapter task，已切到长篇规划编辑区。");
    focusAuthorPanel("longform");
    return;
  }
  renderLongformWorkbench();
  focusAuthorPanel("task_editor");
}

function setAuthorRepairLoopHint(payload) {
  authorState.authorRepairLoopHint = payload ? { ...payload } : null;
}

function currentAuthorRepairLoopResult() {
  return authorState.activeDraftDetail?.latest_repair_loop_outcome || currentAuthorSimulationReport()?.latest_repair_loop_outcome || null;
}

async function refreshOpsSurfaceIfVisible() {
  if (shellState.activeProduct !== "ops") {
    return;
  }
  await refreshOpsSurface();
}

function normalizeAuthorRepairLoopState(payload) {
  if (!payload) return null;
  const targetedChapters = Array.isArray(payload.targetedChapters)
    ? payload.targetedChapters
    : Array.isArray(payload.targeted_chapters)
      ? payload.targeted_chapters
      : [];
  return {
    available: Boolean(payload.available),
    repairLoopRevisionId: payload.repairLoopRevisionId || payload.repair_loop_revision_id || "",
    issueCode: payload.issueCode || payload.issue_code || "",
    issueLabel: payload.issueLabel || payload.issue_label || payload.issueCode || payload.issue_code || "",
    assetType: payload.assetType || payload.asset_type || "",
    assetLabel: payload.assetLabel || payload.asset_label || "",
    targetLabel: payload.targetLabel || payload.target_label || "",
    validationPanel: payload.validationPanel || payload.validation_panel || "",
    validationPanelLabel: payload.validationPanelLabel || payload.validation_panel_label || "",
    validationReason: payload.validationReason || payload.validation_reason || "",
    chapterIndex: Number(payload.chapterIndex || payload.chapter_index || 0) || null,
    chapterTitle: payload.chapterTitle || payload.chapter_title || "",
    characterId: payload.characterId || payload.character_id || "",
    sceneId: payload.sceneId || payload.scene_id || "",
    sceneFunction: payload.sceneFunction || payload.scene_function || "",
    chapterTaskId: payload.chapterTaskId || payload.chapter_task_id || "",
    arcId: payload.arcId || payload.arc_id || "",
    volumeId: payload.volumeId || payload.volume_id || "",
    targetedChapters,
    baselineIssueCount: payload.baselineIssueCount ?? payload.baseline_issue_count ?? null,
    currentIssueCount: payload.currentIssueCount ?? payload.current_issue_count ?? null,
    baselineTargetedIssueCount: payload.baselineTargetedIssueCount ?? payload.baseline_targeted_issue_count ?? null,
    currentTargetedIssueCount: payload.currentTargetedIssueCount ?? payload.current_targeted_issue_count ?? null,
    countDelta: payload.countDelta ?? payload.count_delta ?? null,
    baselineWorstDecision: payload.baselineWorstDecision || payload.baseline_worst_decision || "",
    currentWorstDecision: payload.currentWorstDecision || payload.current_worst_decision || "",
    severityTrend: payload.severityTrend || payload.severity_trend || "",
    resolvedChapters: payload.resolvedChapters || payload.resolved_chapters || [],
    remainingChapters: payload.remainingChapters || payload.remaining_chapters || [],
    readyForValidation: Boolean(payload.readyForValidation ?? payload.ready_for_validation),
  };
}

function currentAuthorRepairLoopState() {
  const outcome = normalizeAuthorRepairLoopState(currentAuthorRepairLoopResult());
  const hint = normalizeAuthorRepairLoopState(authorState.authorRepairLoopHint);
  if (hint && !hint.available) {
    const sameLoop = Boolean(
      outcome?.available &&
      (
        (hint.repairLoopRevisionId && outcome.repairLoopRevisionId === hint.repairLoopRevisionId) ||
        (
          !hint.repairLoopRevisionId &&
          outcome.issueCode === hint.issueCode &&
          outcome.assetType === hint.assetType &&
          (outcome.targetLabel || "") === (hint.targetLabel || "")
        )
      )
    );
    return sameLoop ? outcome : hint;
  }
  if (outcome?.available) return outcome;
  return hint;
}

function buildAuthorRepairLoopHint(priority, issueGroup = null) {
  if (!priority) return null;
  const firstChapter = (issueGroup?.chapters || [])[0] || {};
  return {
    issueCode: issueGroup?.issue_code || "",
    issueLabel: issueGroup?.label || issueGroup?.issue_code || "",
    assetType: priority.asset_type || "",
    assetLabel: priority.label || "",
    targetLabel: priority.target_label || "",
    validationPanel: priority.validation_panel || issueGroup?.primary_validation_panel || "",
    validationPanelLabel: priority.validation_panel_label || issueGroup?.primary_validation_panel_label || "",
    validationReason: priority.validation_reason || "",
    chapterIndex: Number(priority.chapter_index || firstChapter.chapter_index || 0) || null,
    chapterTitle: priority.chapter_title || firstChapter.chapter_title || "",
    characterId: priority.character_id || (priority.character_ids || [])[0] || (firstChapter.related_character_ids || [])[0] || "",
    sceneId: priority.scene_id || firstChapter.scene_id || "",
    sceneFunction: priority.scene_function || firstChapter.scene_function || "",
    chapterTaskId: priority.chapter_task_id || firstChapter.chapter_task_id || "",
    arcId: priority.arc_id || firstChapter.arc_id || "",
    volumeId: priority.volume_id || firstChapter.volume_id || "",
    targetedChapters: (issueGroup?.chapters || []).map((chapter) => ({
      chapter_index: chapter.chapter_index,
      chapter_title: chapter.chapter_title || "",
    })),
  };
}

function openAuthorRepairLoopValidationPanel() {
  const hint = currentAuthorRepairLoopState();
  if (!hint?.validationPanel) {
    authorNotice("当前没有可返回的复核面板。");
    return;
  }
  if (hint.validationPanel === "compare") {
    if (hint.chapterIndex) {
      jumpToAuthorChapter(hint.chapterIndex, "compare");
    } else {
      focusAuthorPanel("compare");
    }
    return;
  }
  if (hint.validationPanel === "continuity") {
    if (hint.chapterIndex) {
      authorState.selectedAuthorContinuityChapterIndex = hint.chapterIndex;
      renderAuthorReports();
    }
    focusAuthorPanel("continuity");
    return;
  }
  if (hint.validationPanel === "task_linking") {
    if (hint.volumeId) authorState.selectedAuthorVolumeId = hint.volumeId;
    if (hint.arcId) authorState.selectedAuthorArcId = hint.arcId;
    if (hint.chapterTaskId) authorState.selectedAuthorTaskId = hint.chapterTaskId;
    renderAuthorReports();
    focusAuthorPanel("task_linking");
    return;
  }
  authorNotice("当前复核面板类型还没有接入。");
}

function createRepairLoopSummaryCard(expectedAssetType) {
  const loopState = currentAuthorRepairLoopState();
  if (!loopState || loopState.assetType !== expectedAssetType) return null;
  if (loopState.available) {
    return createAuthorSummaryCard({
      title: `${loopState.issueCode || "修稿回路"} 结果`,
      score: loopState.severityTrend || "-",
      body:
        `当前资产 ${loopState.assetLabel || loopState.assetType}${loopState.targetLabel ? ` -> ${loopState.targetLabel}` : ""}\n` +
        `issue count ${loopState.baselineIssueCount ?? loopState.baseline_issue_count ?? "-"} -> ${loopState.currentIssueCount ?? loopState.current_issue_count ?? "-"}\n` +
        `worst decision ${loopState.baselineWorstDecision ?? loopState.baseline_worst_decision ?? "-"} -> ${loopState.currentWorstDecision ?? loopState.current_worst_decision ?? "-"}\n` +
        `改完后回 ${loopState.validationPanelLabel || loopState.validation_panel_label || loopState.validationPanel || loopState.validation_panel || "-"} 复核\n` +
        `${loopState.validationReason || loopState.validation_reason || "回修稿桥确认问题是否消退。"}`,
      actionLabel: `${loopState.readyForValidation || loopState.ready_for_validation ? "去复核" : "先看结果"}`,
      onAction: openAuthorRepairLoopValidationPanel,
      primary: true,
    });
  }
  return createAuthorSummaryCard({
    title: `${loopState.issueCode || "修稿回路"} 复核提示`,
    score: loopState.validationPanelLabel || "-",
    body:
      `当前资产 ${loopState.assetLabel || loopState.assetType}${loopState.targetLabel ? ` -> ${loopState.targetLabel}` : ""}\n` +
      `热点章节 ${loopState.chapterIndex ? `#${loopState.chapterIndex} ${loopState.chapterTitle || ""}` : "-"}\n` +
      `改完后回 ${loopState.validationPanelLabel || loopState.validationPanel || "-"} 复核\n` +
      `${loopState.validationReason || "回修稿桥确认问题是否消退。"}`,
    actionLabel: `回${loopState.validationPanelLabel || loopState.validationPanel || "修稿桥"}复核`,
    onAction: openAuthorRepairLoopValidationPanel,
    primary: true,
  });
}

function buildDraftChangeContext(source, label, expectedAssetType = "") {
  const changeContext = { source, label };
  const loopState = currentAuthorRepairLoopState();
  if (!expectedAssetType || !loopState || loopState.assetType !== expectedAssetType) {
    return changeContext;
  }
  changeContext.repair_loop_context = {
    issue_code: loopState.issueCode || "",
    issue_label: loopState.issueLabel || loopState.issueCode || "",
    asset_type: loopState.assetType || "",
    asset_label: loopState.assetLabel || "",
    target_label: loopState.targetLabel || "",
    validation_panel: loopState.validationPanel || "",
    validation_panel_label: loopState.validationPanelLabel || "",
    validation_reason: loopState.validationReason || "",
    character_id: loopState.characterId || "",
    scene_id: loopState.sceneId || "",
    scene_function: loopState.sceneFunction || "",
    chapter_task_id: loopState.chapterTaskId || "",
    arc_id: loopState.arcId || "",
    volume_id: loopState.volumeId || "",
    chapter_index: loopState.chapterIndex || null,
    chapter_title: loopState.chapterTitle || "",
    targeted_chapters: loopState.targetedChapters || [],
  };
  return changeContext;
}

function syncAuthorRepairLoopHintFromDraft(draft, expectedAssetType) {
  const hint = normalizeAuthorRepairLoopState(authorState.authorRepairLoopHint);
  if (!hint || hint.assetType !== expectedAssetType) return;
  const revisions = Array.isArray(draft?.revision_history) ? draft.revision_history : [];
  const latestRevision = revisions[revisions.length - 1] || null;
  if (!latestRevision?.revision_id) return;
  setAuthorRepairLoopHint({
    ...hint,
    repairLoopRevisionId: latestRevision.revision_id,
  });
}

function openAuthorPriorityAsset(priority, issueGroup = null) {
  if (!priority || !priority.asset_type) {
    authorNotice("当前没有可打开的推荐资产。");
    return;
  }
  setAuthorRepairLoopHint(buildAuthorRepairLoopHint(priority, issueGroup));
  if (priority.asset_type === "scene_blueprint") {
    openAuthorSceneAsset({ sceneId: priority.scene_id, sceneFunction: priority.scene_function });
    return;
  }
  if (priority.asset_type === "chapter_task") {
    openAuthorTaskAsset({ volumeId: priority.volume_id, arcId: priority.arc_id, taskId: priority.chapter_task_id });
    return;
  }
  if (priority.asset_type === "character_card") {
    openAuthorCharacterAsset(priority.character_id || (priority.character_ids || [])[0] || "");
    return;
  }
  authorNotice("当前推荐资产类型还没有接入编辑器。");
}

function focusAuthorCreativeCockpit() {
  focusAuthorPanel("creative_cockpit");
}

function clearAuthorSteeringComposer() {
  if (dom.authorSteeringIntent) dom.authorSteeringIntent.value = "";
  if (dom.authorSteeringType) dom.authorSteeringType.value = "mild_steer";
  if (dom.authorSteeringMemoryPatch) dom.authorSteeringMemoryPatch.value = "";
  if (dom.authorSteeringArc) dom.authorSteeringArc.value = "";
  setMultiSelectValues(dom.authorSteeringCharacters, []);
  authorState.pendingAuthorBranchSeed = null;
}

function renderAuthorSteeringComposer() {
  if (!dom.authorSteeringComposer || !dom.authorSteeringStatus) return;
  const activeDraft = authorState.activeDraftDetail;
  const simulationReport = currentAuthorSimulationReport();
  const cockpit = currentAuthorCreativeCockpit() || {};
  const steeringTimeline = cockpit.steering_timeline || {};
  const relationshipHotspot = (cockpit.relationship_hotspots?.items || [])[0] || null;
  const characters = getActiveDraftCharacters();
  const arcs = getActiveArcPlans();
  const previousCharacterSelection = new Set(selectedMultiValues(dom.authorSteeringCharacters));
  const previousArcValue = dom.authorSteeringArc?.value || "";
  const defaultTriggerChapter = Math.max(1, Number(simulationReport?.completed_chapters || 0) + 1);
  const forkContext = resolveAuthorSteeringForkContext(defaultTriggerChapter);

  if (dom.authorSteeringCharacters) {
    dom.authorSteeringCharacters.innerHTML = "";
    characters.forEach((character) => {
      const option = document.createElement("option");
      option.value = String(character.character_id || "");
      option.textContent = character.display_name || character.character_id || "未命名角色";
      option.selected = previousCharacterSelection.has(option.value);
      dom.authorSteeringCharacters.appendChild(option);
    });
    dom.authorSteeringCharacters.disabled = !characters.length;
  }
  if (dom.authorSteeringArc) {
    dom.authorSteeringArc.innerHTML = "";
    const autoOption = document.createElement("option");
    autoOption.value = "";
    autoOption.textContent = "自动跟随当前弧线";
    dom.authorSteeringArc.appendChild(autoOption);
    arcs.forEach((arc) => {
      const option = document.createElement("option");
      option.value = String(arc.arc_id || "");
      option.textContent = arc.title || arc.arc_id || "未命名弧线";
      option.selected = option.value === previousArcValue;
      dom.authorSteeringArc.appendChild(option);
    });
    if (previousArcValue && Array.from(dom.authorSteeringArc.options).every((option) => option.value !== previousArcValue)) {
      dom.authorSteeringArc.value = "";
    }
    dom.authorSteeringArc.disabled = !activeDraft;
  }

  if (!activeDraft || !authorState.activeDraftVersionId) {
    if (dom.authorRunSteeredSimulation) dom.authorRunSteeredSimulation.disabled = true;
    if (dom.authorClearSteering) dom.authorClearSteering.disabled = true;
    clearNode(dom.authorSteeringStatus, "先选择一个 draft，再把一条剧情引导、一个记忆补丁或一个弧线偏移打进下一轮 simulation。");
    return;
  }

  if (dom.authorRunSteeredSimulation) dom.authorRunSteeredSimulation.disabled = false;
  if (dom.authorClearSteering) dom.authorClearSteering.disabled = false;
  clearNode(dom.authorSteeringStatus);
  const workScopedFork = Boolean(authorState.activeWorkId && forkContext.sourceChapterIndex);
  const contextCard = createListCard({
    title: "Steering Context",
    score: workScopedFork ? `第 ${forkContext.sourceChapterIndex} 章后分叉` : `第 ${forkContext.nextBranchStartChapterIndex} 章`,
    body:
      `${workScopedFork ? `当前分叉点以你选中的章节为准：第 ${forkContext.sourceChapterIndex} 章\n` : `默认触发章节 ${defaultTriggerChapter}\n`}` +
      `${authorState.activeWorkId ? `当前作品稿 ${authorState.activeWorkDetail?.branch_name || "主线"} · 当前分叉点章节 ${forkContext.sourceChapterIndex || "-"} · 新命运线会从第 ${forkContext.nextBranchStartChapterIndex} 章开始\n` : ""}` +
      `${authorState.activeWorkId ? "主线后续章节不会复制到新宇宙，过去只作为共享历史保留。\n" : ""}` +
      `已有 checkpoint ${steeringTimeline.checkpoint_count ?? 0} · replan ${steeringTimeline.replan_event_count ?? 0}\n` +
      `memory pending ${steeringTimeline.memory_patch_summary?.pending_count ?? 0} · adopted ${steeringTimeline.memory_patch_summary?.adopted_count ?? 0}\n` +
      `${relationshipHotspot ? `当前最紧绷关系 ${relationshipHotspot.source_label} -> ${relationshipHotspot.target_label} · ${relationshipHotspot.dominant_metric_label} ${Number(relationshipHotspot.dominant_metric_value || 0).toFixed(2)}` : "当前最紧绷关系 需要先跑一次 simulation 才会出现。"}`,
  });
  dom.authorSteeringStatus.appendChild(contextCard);
  if (authorState.activeWorkId) {
    const branchExecution = buildAuthorBranchExecutionPresentation();
    const executionCard = createListCard({
      title: branchExecution.title,
      score: branchExecution.score,
      body: branchExecution.body,
    });
    executionCard.classList.add("author-branch-status-card");
    executionCard.dataset.tone = branchExecution.tone || "neutral";
    dom.authorSteeringStatus.appendChild(executionCard);
  }
}

function buildAuthorSteeringScenario() {
  const summary = dom.authorSteeringIntent?.value.trim() || "";
  if (!summary) {
    authorNotice("先写一句你想让剧情偏过去的方向。");
    dom.authorSteeringIntent?.focus();
    return null;
  }
  const scenarioKind = dom.authorSteeringType?.value || "mild_steer";
  const impactedCharacterIds = selectedMultiValues(dom.authorSteeringCharacters);
  const memoryPatchNote = dom.authorSteeringMemoryPatch?.value.trim() || "";
  const affectedArcId = dom.authorSteeringArc?.value || "";
  return {
    scenario_kind: scenarioKind,
    label: summary,
    steering_directive: {
      current_user_intent: summary,
      summary,
      impacted_character_ids: impactedCharacterIds,
      ...(memoryPatchNote ? { memory_patch_note: memoryPatchNote } : {}),
      ...(affectedArcId ? { affected_arc_id: affectedArcId } : {}),
    },
  };
}

function resolveAuthorSteeringForkContext(defaultTriggerChapter = 1) {
  const explicitSeed = Number(authorState.pendingAuthorBranchSeed?.sourceChapterIndex || 0) || 0;
  if (explicitSeed > 0) {
    return {
      sourceChapterIndex: explicitSeed,
      nextBranchStartChapterIndex: explicitSeed + 1,
      source: "choice_seed",
    };
  }
  const selectedSimulationChapterIndex = Number(authorState.selectedAuthorSimulationChapterIndex || 0) || 0;
  if (shellState.authorWorkspace === "simulate" && selectedSimulationChapterIndex > 0) {
    return {
      sourceChapterIndex: selectedSimulationChapterIndex,
      nextBranchStartChapterIndex: selectedSimulationChapterIndex + 1,
      source: "selected_simulation_chapter",
    };
  }
  const fallbackChapterIndex = Math.max(0, Number(defaultTriggerChapter || 1) - 1);
  if (shellState.authorWorkspace === "simulate" && fallbackChapterIndex > 0) {
    return {
      sourceChapterIndex: fallbackChapterIndex,
      nextBranchStartChapterIndex: fallbackChapterIndex + 1,
      source: "default_trigger_previous_chapter",
    };
  }
  return {
    sourceChapterIndex: 0,
    nextBranchStartChapterIndex: Math.max(1, Number(defaultTriggerChapter || 1)),
    source: "missing_simulation_context",
  };
}

async function createAuthorWorkBranchFromSteering(scenario, forkContext = null) {
  if (!authorState.activeWorkId) return null;
  const resolvedForkContext = forkContext || resolveAuthorSteeringForkContext();
  const sourceChapterIndex = Number(resolvedForkContext?.sourceChapterIndex || 0) || 0;
  if (!sourceChapterIndex) return null;
  const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/branches`, {
    method: "POST",
    body: JSON.stringify({
      source_chapter_index: sourceChapterIndex,
      steering_directive: scenario?.steering_directive || {},
      choice_source: authorState.pendingAuthorBranchSeed?.choiceSourceLabel || null,
      account_id: activeAuthorAccountId() || null,
    }),
  });
  authorState.activeWorkId = payload.work_id;
  authorState.activeWorkChapterIndex = Number(payload.fork_after_chapter_index || sourceChapterIndex) || null;
  authorState.activeWorkChapterDetail = null;
  authorState.pendingAuthorBranchSeed = null;
  await refreshAuthorWorks(activeAuthorAccountId());
  return payload;
}

async function runSteeredSimulation() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const scenario = buildAuthorSteeringScenario();
  if (!scenario) return;
  const releaseBusy = dom.authorRunSteeredSimulation ? setBusy(dom.authorRunSteeredSimulation, "命运线处理中…") : null;
  try {
    const defaultTriggerChapter = Math.max(1, Number(currentAuthorSimulationReport()?.completed_chapters || 0) + 1);
    const forkContext = resolveAuthorSteeringForkContext(defaultTriggerChapter);
    if (authorState.activeWorkId) {
      if (!forkContext.sourceChapterIndex) {
        authorNotice("先在模拟报告里定位到当前章节，再创建新的命运线。", "warning");
        return;
      }
      setAuthorBranchExecutionState({
        stage: "branch_pending",
        workId: authorState.activeWorkId,
        branchName: authorState.activeWorkDetail?.branch_name || "主线",
        forkAfterChapterIndex: forkContext.sourceChapterIndex,
        nextChapterIndex: forkContext.nextBranchStartChapterIndex,
        currentChapterCount: Number(authorState.activeWorkDetail?.chapter_count || forkContext.sourceChapterIndex || 0) || 0,
        currentRevision: authorState.activeWorkDetail?.current_revision || null,
        errorMessage: "",
      });
      const branched = await createAuthorWorkBranchFromSteering(scenario, forkContext);
      if (branched?.work_id) {
        setAuthorBranchExecutionState({
          stage: "generate_pending",
          workId: branched.work_id,
          rootWorkId: branched.root_work_id || branched.work_id,
          branchName: branched.branch_name || "平行宇宙",
          forkAfterChapterIndex: Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) || 0,
          nextChapterIndex:
            Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) > 0
              ? Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) + 1
              : forkContext.nextBranchStartChapterIndex,
          currentChapterCount:
            Number(branched.chapter_count || branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) || 0,
          currentRevision: branched.current_revision || null,
          errorMessage: "",
        });
        const generated = await generateAuthorWork("next");
        if (!generated) {
          const fallbackChapterCount =
            Number(authorState.activeWorkDetail?.chapter_count || branched.chapter_count || forkContext.sourceChapterIndex || 0) || 0;
          const gateMessage = authorState.authorWorkQualityGateFailure?.message || "";
          setAuthorBranchExecutionState({
            stage: "generate_failed",
            workId: branched.work_id,
            rootWorkId: branched.root_work_id || branched.work_id,
            branchName: branched.branch_name || "平行宇宙",
            forkAfterChapterIndex: Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) || 0,
            nextChapterIndex:
              Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) > 0
                ? Number(branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) + 1
                : forkContext.nextBranchStartChapterIndex,
            currentChapterCount: fallbackChapterCount,
            currentRevision: authorState.activeWorkDetail?.current_revision || branched.current_revision || null,
            errorMessage: gateMessage || "生成链路没有返回新的章节结果，请检查上方错误提示。",
          });
          authorNotice("新命运线已创建，但下一章没有成功生成。页面内状态卡已保留失败原因。", "warning");
          return;
        }
        setAuthorBranchExecutionState({
          stage: "generate_succeeded",
          workId: generated.work_id || branched.work_id,
          rootWorkId: generated.root_work_id || branched.root_work_id || branched.work_id,
          branchName: generated.branch_name || branched.branch_name || "平行宇宙",
          forkAfterChapterIndex:
            Number(generated.fork_after_chapter_index || branched.fork_after_chapter_index || forkContext.sourceChapterIndex || 0) || 0,
          nextChapterIndex: Number(generated.chapter_count || forkContext.nextBranchStartChapterIndex || 0) || 0,
          currentChapterCount: Number(generated.chapter_count || 0) || 0,
          currentRevision: generated.current_revision || null,
          errorMessage: "",
        });
        WorkspaceLayoutRuntime.setAuthorWorkspace("draft", { silent: true });
        ShellStatusRuntime.syncProductMode();
        authorNotice(
          `已从第 ${branched.fork_after_chapter_index || forkContext.sourceChapterIndex} 章后创建${branched.branch_name || "平行宇宙"}，并生成第 ${generated.chapter_count || forkContext.nextBranchStartChapterIndex} 章。`,
          "success"
        );
        return;
      }
    }
    await simulateDraftVersion(authorState.activeDraftVersionId, {
      interactiveScenarios: [scenario],
      accountId: activeAuthorAccountId(),
    });
    authorNotice("已带着引导重跑 Simulation。", "success");
  } catch (error) {
    const defaultTriggerChapter = Math.max(1, Number(currentAuthorSimulationReport()?.completed_chapters || 0) + 1);
    const forkContext = resolveAuthorSteeringForkContext(defaultTriggerChapter);
    const previousState = authorState.authorBranchExecutionState || null;
    if (authorState.activeWorkId && forkContext.sourceChapterIndex) {
      setAuthorBranchExecutionState({
        stage: previousState?.stage === "generate_pending" ? "generate_failed" : "branch_create_failed",
        workId: previousState?.workId || authorState.activeWorkId,
        rootWorkId: previousState?.rootWorkId || authorState.activeWorkDetail?.root_work_id || authorState.activeWorkId,
        branchName: previousState?.branchName || authorState.activeWorkDetail?.branch_name || "平行宇宙",
        forkAfterChapterIndex: Number(previousState?.forkAfterChapterIndex || forkContext.sourceChapterIndex || 0) || 0,
        nextChapterIndex:
          Number(previousState?.nextChapterIndex || 0) ||
          (Number(previousState?.forkAfterChapterIndex || forkContext.sourceChapterIndex || 0) > 0
            ? Number(previousState?.forkAfterChapterIndex || forkContext.sourceChapterIndex || 0) + 1
            : forkContext.nextBranchStartChapterIndex),
        currentChapterCount:
          Number(previousState?.currentChapterCount || authorState.activeWorkDetail?.chapter_count || forkContext.sourceChapterIndex || 0) || 0,
        currentRevision: authorState.activeWorkDetail?.current_revision || previousState?.currentRevision || null,
        errorMessage: summarizeAuthorExecutionError(error),
      });
    }
    authorNotice(formatAuthorApiErrorMessage(error, "带着引导重跑 Simulation 失败，请稍后再试。"), "error");
  } finally {
    releaseBusy?.();
  }
}

function prefillAuthorSteeringFromChoice(choice, chapterDetail = null) {
  const chapterTask = chapterDetail?.chapter_task || chapterDetail?.chapter_task_json || {};
  const choiceText = normalizeAuthorChoiceText(choice);
  if (!choiceText) {
    authorNotice("当前选项没有可写入的引导文本。", "warning");
    return;
  }
  focusAuthorPanel("steering");
  if (dom.authorSteeringIntent) {
    dom.authorSteeringIntent.value = choiceText;
    dom.authorSteeringIntent.focus();
  }
  if (dom.authorSteeringType) {
    dom.authorSteeringType.value = "mild_steer";
  }
  if (dom.authorSteeringMemoryPatch) {
    dom.authorSteeringMemoryPatch.value = "";
  }
  if (dom.authorSteeringArc && chapterTask.arc_id) {
    dom.authorSteeringArc.value = String(chapterTask.arc_id);
  }
  authorState.pendingAuthorBranchSeed = {
    sourceChapterIndex: Number(chapterDetail?.chapter_index || authorState.activeWorkChapterIndex || 0) || 0,
    choiceSourceLabel: choiceText,
  };
  renderAuthorSteeringComposer();
  authorNotice("已把这个选项预填到剧情引导区。", "info");
}

async function submitDraftVersion(worldVersionId) {
  authorState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  const report = await api(
    `/v1/author/drafts/${worldVersionId}/submit?account_id=${encodeURIComponent(dom.authorAccountId?.value.trim() || "web_author")}`,
    { method: "POST" }
  );
  authorState.activeDraftVersionId = worldVersionId;
  authorState.authorValidationReport = report;
  authorState.selectedAuthorRevisionIndex = null;
  authorState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  await refreshOpsSurfaceIfVisible();
  focusAuthorPanel("version_history");
  return report;
}

async function createAuthorCommentThread() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const body = dom.authorCommentBody?.value.trim() || "";
  if (!body) {
    authorNotice("先写评论内容。");
    return;
  }
  const actorId = activeAuthorActorId();
  const created = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/comments`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      anchor_type: dom.authorCommentAnchorType?.value || "draft",
      anchor_key: dom.authorCommentAnchorKey?.value.trim() || authorState.activeDraftVersionId,
      severity: dom.authorCommentSeverity?.value || "normal",
      assignee_id: dom.authorCommentAssignee?.value.trim() || null,
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
      body,
    }),
  });
  authorState.selectedAuthorThreadId = created.thread?.thread_id || authorState.selectedAuthorThreadId;
  if (dom.authorCommentBody) dom.authorCommentBody.value = "";
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function requestAuthorApproval() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const reviewerId = dom.authorApprovalReviewer?.value.trim() || activeAuthorReviewerId();
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/approval/request`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      reviewer_id: reviewerId,
      reason: dom.authorApprovalReason?.value.trim() || "请求内部审批。",
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
    }),
  });
  if (dom.authorInboxReviewerId && reviewerId) {
    dom.authorInboxReviewerId.value = reviewerId;
  }
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function decideAuthorApproval(status) {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const reviewerId = dom.authorApprovalReviewer?.value.trim() || activeAuthorReviewerId();
  await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/approval/decision`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId: reviewerId, actorRole: "reviewer" }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      reviewer_id: reviewerId,
      status,
      reason: dom.authorApprovalReason?.value.trim() || (status === "approved" ? "批准送审。" : "需要修改。"),
    }),
  });
  if (dom.authorInboxReviewerId && reviewerId) {
    dom.authorInboxReviewerId.value = reviewerId;
  }
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function runAuthorWorkflowAction(actionId) {
  const draftId = authorState.authorWorkflowSummary?.world_version_id || authorState.activeDraftVersionId;
  if (actionId === "create_from_brief") {
    focusAuthorPanel("brief");
    const brief = buildAuthorBriefPayload();
    if (brief.world_title && brief.core_premise) {
      await createDraftFromBrief();
    }
    return;
  }
  if (actionId === "copy_current_world") {
    await createDraftFromCurrentWorld();
    return;
  }
  if (actionId === "bootstrap_quick_brief_enrich" && draftId) {
    await api(`/v1/author/drafts/${encodeURIComponent(draftId)}/longform-bootstrap`, {
      method: "POST",
      body: JSON.stringify({
        account_id: activeAuthorAccountId() || null,
        mode: "quick_brief_enrich",
        target_band: "100",
      }),
    });
    await refreshAuthorSurface();
    focusAuthorPanel("longform");
    return;
  }
  if (actionId === "bootstrap_structured_longform" && draftId) {
    await api(`/v1/author/drafts/${encodeURIComponent(draftId)}/longform-bootstrap`, {
      method: "POST",
      body: JSON.stringify({
        account_id: activeAuthorAccountId() || null,
        mode: "structured_longform",
        target_band: authorState.authorWorkflowSummary?.longform_readiness?.band || "250",
      }),
    });
    await refreshAuthorSurface();
    focusAuthorPanel("longform");
    return;
  }
  if (actionId === "validate_draft" && draftId) {
    await validateDraftVersion(draftId);
    return;
  }
  if (actionId === "simulate_draft" && draftId) {
    await simulateDraftVersion(draftId);
    return;
  }
  if (actionId === "submit_draft" && draftId) {
    await submitDraftVersion(draftId);
    return;
  }
  if (actionId === "focus_validation") {
    focusAuthorPanel("validation");
    return;
  }
  if (actionId === "focus_simulation") {
    focusAuthorPanel("simulation");
    return;
  }
  if (actionId === "focus_diff" || actionId === "focus_revision") {
    focusAuthorPanel("diff");
    return;
  }
  if (actionId === "focus_version_history") {
    focusAuthorPanel("version_history");
    return;
  }
  if (actionId === "focus_draft_detail") {
    focusAuthorPanel("draft_detail");
    return;
  }
  if (actionId === "focus_longform") {
    focusAuthorPanel("longform");
    return;
  }
}

function populateAuthorBriefForm(force = false) {
  const payload = authorState.authorBriefTemplate;
  if (!payload) return;
  const defaults = payload.defaults || {};
  const presets = payload.genre_presets || [];
  if (!dom.authorGenrePreset) return;
  if (!dom.authorGenrePreset.options.length) {
    dom.authorGenrePreset.innerHTML = presets
      .map((preset) => `<option value="${preset.id}">${preset.label}</option>`)
      .join("");
  }
  if (force || !String(dom.authorGenrePreset.value || "").trim()) {
    dom.authorGenrePreset.value = defaults.genre_preset || presets[0]?.id || "urban_mystery";
  }
  setAuthorBriefFieldValue(dom.authorWorldTitle, defaults.world_title, { force });
  setAuthorBriefFieldValue(dom.authorLeadName, defaults.lead_name, { force });
  setAuthorBriefFieldValue(dom.authorCounterpartName, defaults.counterpart_name, { force });
  setAuthorBriefFieldValue(dom.authorSupportingName, defaults.supporting_name, { force });
  setAuthorBriefFieldValue(dom.authorLifeTheme, defaults.life_theme, { force });
  setAuthorBriefFieldValue(dom.authorCorePremise, defaults.core_premise, { force });
  setAuthorBriefFieldValue(dom.authorLocations, defaults.locations, { force });
}

function setAuthorBriefFieldValue(node, value, options = {}) {
  if (!node) return;
  const nextValue = String(value || "");
  if (options.force || !String(node.value || "").trim()) {
    node.value = nextValue;
  }
}

function applyAuthorPresetDefaults() {
  const payload = authorState.authorBriefTemplate;
  if (!payload) return;
  const selected = dom.authorGenrePreset?.value;
  const defaults = payload.preset_defaults?.[selected];
  if (!defaults) return;
  // Genre presets should help fill blanks, not wipe the author's in-progress brief.
  setAuthorBriefFieldValue(dom.authorWorldTitle, defaults.world_title);
  setAuthorBriefFieldValue(dom.authorLeadName, defaults.lead_name);
  setAuthorBriefFieldValue(dom.authorCounterpartName, defaults.counterpart_name);
  setAuthorBriefFieldValue(dom.authorSupportingName, defaults.supporting_name);
  setAuthorBriefFieldValue(dom.authorLifeTheme, defaults.life_theme);
  setAuthorBriefFieldValue(dom.authorCorePremise, defaults.core_premise);
  setAuthorBriefFieldValue(dom.authorLocations, defaults.locations);
}

function buildAuthorBriefPayload() {
  return {
    genre_preset: dom.authorGenrePreset?.value || "urban_mystery",
    world_title: dom.authorWorldTitle?.value.trim() || "",
    lead_name: dom.authorLeadName?.value.trim() || "",
    counterpart_name: dom.authorCounterpartName?.value.trim() || "",
    supporting_name: dom.authorSupportingName?.value.trim() || "",
    life_theme: dom.authorLifeTheme?.value.trim() || "",
    core_premise: dom.authorCorePremise?.value.trim() || "",
    locations: dom.authorLocations?.value || "",
    author_id: dom.authorAccountId?.value.trim() || "web_author",
    account_id: dom.authorAccountId?.value.trim() || "web_author",
  };
}

function getActiveDraftCharacters() {
  return getActiveDraftWorldpack()?.characters || [];
}

function getActiveDraftScenes() {
  return getActiveDraftWorldpack()?.scene_blueprints || [];
}

function getActiveSeriesPlan() {
  return getActiveDraftWorldpack()?.series_plan || null;
}

function getActiveVolumePlans() {
  return getActiveDraftWorldpack()?.volume_plans || [];
}

function getActiveArcPlans() {
  return getActiveDraftWorldpack()?.arc_plans || [];
}

function applyDraftWorldpackMutation(mutator) {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !authorState.activeDraftDetail) return false;
  const nextWorldpack = structuredClone(activeWorldpack);
  mutator(nextWorldpack);
  authorState.activeDraftDetail = {
    ...authorState.activeDraftDetail,
    worldpack: nextWorldpack,
    worldpack_json: nextWorldpack,
  };
  return true;
}

function resequenceArcOrders(worldpack, volumeId) {
  const sameVolume = (worldpack.arc_plans || []).filter((item) => item.volume_id === volumeId);
  sameVolume.forEach((arc, index) => {
    arc.order = index + 1;
  });
}

function reorderArcWithinVolume(volumeId, draggedArcId, targetArcId) {
  if (!volumeId || !draggedArcId || !targetArcId || draggedArcId === targetArcId) return;
  const updated = applyDraftWorldpackMutation((worldpack) => {
    const sameVolume = (worldpack.arc_plans || []).filter((item) => item.volume_id === volumeId);
    const volumeOrder = new Map((worldpack.volume_plans || []).map((item, index) => [String(item.volume_id || ""), Number(item.order || index + 1)]));
    const fromIndex = sameVolume.findIndex((item) => item.arc_id === draggedArcId);
    const toIndex = sameVolume.findIndex((item) => item.arc_id === targetArcId);
    if (fromIndex < 0 || toIndex < 0) return;
    const [moved] = sameVolume.splice(fromIndex, 1);
    sameVolume.splice(toIndex, 0, moved);
    sameVolume.forEach((arc, index) => {
      arc.order = index + 1;
    });
    const replacedById = new Map(sameVolume.map((item) => [String(item.arc_id || ""), item]));
    worldpack.arc_plans = (worldpack.arc_plans || [])
      .map((item) => replacedById.get(String(item.arc_id || "")) || item)
      .sort((left, right) => {
      if (String(left.volume_id || "") !== String(right.volume_id || "")) {
        return Number(volumeOrder.get(String(left.volume_id || "")) || 0) - Number(volumeOrder.get(String(right.volume_id || "")) || 0);
      }
      return Number(left.order || 0) - Number(right.order || 0);
    });
  });
  if (!updated) return;
  authorState.selectedAuthorVolumeId = volumeId;
  authorState.selectedAuthorArcId = targetArcId;
  authorState.selectedAuthorTaskId = null;
  renderLongformWorkbench();
}

function reorderTaskWithinArc(arcId, draggedTaskId, targetTaskId) {
  if (!arcId || !draggedTaskId || !targetTaskId || draggedTaskId === targetTaskId) return;
  const updated = applyDraftWorldpackMutation((worldpack) => {
    const arc = (worldpack.arc_plans || []).find((item) => item.arc_id === arcId);
    if (!arc) return;
    const tasks = Array.isArray(arc.chapter_tasks) ? [...arc.chapter_tasks] : [];
    const fromIndex = tasks.findIndex((item) => item.chapter_task_id === draggedTaskId);
    const toIndex = tasks.findIndex((item) => item.chapter_task_id === targetTaskId);
    if (fromIndex < 0 || toIndex < 0) return;
    const [moved] = tasks.splice(fromIndex, 1);
    tasks.splice(toIndex, 0, moved);
    arc.chapter_tasks = tasks;
  });
  if (!updated) return;
  authorState.selectedAuthorArcId = arcId;
  authorState.selectedAuthorTaskId = targetTaskId;
  renderLongformWorkbench();
}

function moveTaskAcrossArcs(sourceArcId, targetArcId, draggedTaskId, targetTaskId = "") {
  if (!sourceArcId || !targetArcId || !draggedTaskId) return;
  const updated = applyDraftWorldpackMutation((worldpack) => {
    const arcPlans = worldpack.arc_plans || [];
    const sourceArc = arcPlans.find((item) => item.arc_id === sourceArcId);
    const targetArc = arcPlans.find((item) => item.arc_id === targetArcId);
    if (!sourceArc || !targetArc) return;
    const sourceTasks = Array.isArray(sourceArc.chapter_tasks) ? [...sourceArc.chapter_tasks] : [];
    const targetTasks = sourceArcId === targetArcId
      ? sourceTasks
      : (Array.isArray(targetArc.chapter_tasks) ? [...targetArc.chapter_tasks] : []);
    const fromIndex = sourceTasks.findIndex((item) => item.chapter_task_id === draggedTaskId);
    if (fromIndex < 0) return;
    const [moved] = sourceTasks.splice(fromIndex, 1);
    if (sourceArcId === targetArcId) {
      const toIndex = targetTasks.findIndex((item) => item.chapter_task_id === targetTaskId);
      if (toIndex < 0) return;
      targetTasks.splice(toIndex, 0, moved);
      sourceArc.chapter_tasks = targetTasks;
      sourceArc.target_chapters = targetTasks.length;
      return;
    }
    const toIndex = targetTaskId ? targetTasks.findIndex((item) => item.chapter_task_id === targetTaskId) : -1;
    if (toIndex >= 0) {
      targetTasks.splice(toIndex, 0, moved);
    } else {
      targetTasks.push(moved);
    }
    sourceArc.chapter_tasks = sourceTasks;
    targetArc.chapter_tasks = targetTasks;
    sourceArc.target_chapters = sourceTasks.length;
    targetArc.target_chapters = targetTasks.length;
  });
  if (!updated) return;
  authorState.selectedAuthorArcId = targetArcId;
  authorState.selectedAuthorTaskId = draggedTaskId;
  if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
  if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
  renderLongformWorkbench();
}

function selectedCharacterIndex() {
  return Math.max(0, Number(dom.authorCharacterSelect?.value || 0));
}

function selectedSceneIndex() {
  return Math.max(0, Number(dom.authorSceneSelect?.value || 0));
}

function appendAuthorCardGrid(node, cards) {
  clearNode(node);
  if (!cards.length) return;
  const grid = document.createElement("div");
  grid.className = "author-workspace-summary-grid";
  cards.forEach((card) => grid.appendChild(card));
  node.appendChild(grid);
}

function formatAuthorActionHints(items) {
  const normalized = (items || [])
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (!item || typeof item !== "object") return "";
      const issueCode = String(item.issue_code || "").trim();
      const owningModule = String(item.owning_module || "").trim();
      const fixHint = String(item.fix_hint || "").trim();
      if (issueCode && fixHint) return `${issueCode}:${fixHint}`;
      if (issueCode && owningModule) return `${issueCode}:${owningModule}`;
      if (issueCode) return issueCode;
      if (owningModule) return owningModule;
      return "";
    })
    .filter(Boolean);
  return normalized.join(" / ") || "-";
}

function renderAuthorDraftSectionNav() {
  if (!dom.authorDraftSectionNav) return;
  clearNode(dom.authorDraftSectionNav);
  AUTHOR_DRAFT_SECTION_CONFIG.forEach((section) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `segment${currentAuthorDraftSection() === section.key ? " is-active" : ""}`;
    button.textContent = section.label;
    button.title = section.description;
    button.addEventListener("click", () => {
      setAuthorDraftSection(section.key, { silent: false });
      if (shellState.authorWorkspace === "draft") {
        RouteSyncRuntime.syncShellRoute();
      }
    });
    dom.authorDraftSectionNav.appendChild(button);
  });
}

function renderAuthorDraftSectionSummary() {
  if (!dom.authorDraftSectionSummary) return;
  if (!authorState.activeDraftVersionId || !authorState.activeDraftDetail) {
    clearNode(dom.authorDraftSectionSummary, "选择一个 Draft 后，这里会显示当前子工作区的焦点、阻塞和下一步。");
    return;
  }
  const worldpack = getActiveDraftWorldpack() || {};
  const section = currentAuthorDraftSection();
  const workflow = authorState.authorWorkflowSummary || {};
  const latestDiff = getLatestDiffSummary();
  const taskLinks = getChapterTaskSimulationLinking().task_links || [];
  const continuity = getContinuityDiffWorkbench();
  const promises = getPromiseLedgerWorkbench();
  const selectedTaskLink =
    taskLinks.find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    taskLinks.find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    taskLinks[0] ||
    null;
  const selectedPromise =
    (getPromiseStateWorkbench().editable_promises || []).find((item) => item.promise_id === authorState.selectedAuthorPromiseId) ||
    (promises.open_promises || [])[0] ||
    null;
  const cardsBySection = {
    assets: [
      createAuthorSummaryCard({
        title: "当前资产对象",
        score: `${getActiveDraftCharacters().length} 角色 / ${getActiveDraftScenes().length} 场景`,
        body:
          `角色 ${(getActiveDraftCharacters()[selectedCharacterIndex()]?.display_name || getActiveDraftCharacters()[0]?.display_name || "-")}\n` +
          `场景 ${(getActiveDraftScenes()[selectedSceneIndex()]?.scene_id || getActiveDraftScenes()[0]?.scene_id || "-")}\n` +
          `最近改动 ${latestDiff.summary_text || "-"}\n` +
          `下一步 先修角色/场景，再去 Review 看 diff 证据。`,
        actionLabel: "查看送审证据",
        onAction: () => focusAuthorPanel("diff"),
        primary: true,
      }),
      createAuthorSummaryCard({
        title: "草稿状态",
        score: authorStageLabel(workflow.stage),
        body:
          `校验 ${workflow.validation_summary?.status || "-"}\n` +
          `模拟 ${workflow.simulation_summary?.latest_decision || "-"}\n` +
          `freshness ${workflow.simulation_freshness?.status || "-"}\n` +
          `blocker ${(workflow.blockers || [])[0]?.message || "当前没有 blocker"}`,
      }),
    ],
    longform: [
      createAuthorSummaryCard({
        title: "当前规划对象",
        score: getActiveSeriesPlan() ? "已建立" : "未建立",
        body:
          `series ${getActiveSeriesPlan()?.title || worldpack.title || "-"}\n` +
          `volume ${getActiveVolumePlans().find((item) => item.volume_id === authorState.selectedAuthorVolumeId)?.title || getActiveVolumePlans()[0]?.title || "-"}\n` +
          `arc ${getActiveArcPlans().find((item) => item.arc_id === authorState.selectedAuthorArcId)?.title || getActiveArcPlans()[0]?.title || "-"}\n` +
          `下一步 先确认卷/弧线，再把 promise mapping 对齐到当前计划。`,
        actionLabel: getActiveSeriesPlan() ? "查看承诺映射" : "生成长篇规划",
        onAction: () => focusAuthorPanel("longform"),
        primary: true,
      }),
      createAuthorSummaryCard({
        title: "计划桥接",
        score: `${(getSeriesVolumeArcPromiseMapping().mappings || []).length} mappings`,
        body:
          `mapped promises ${(getSeriesVolumeArcPromiseMapping().mappings || []).length}\n` +
          `task links ${taskLinks.length}\n` +
          `selected task ${selectedTaskLink?.chapter_task_id || "-"}\n` +
          `下一步 把规划对象连回 simulation 证据。`,
      }),
    ],
    repair: [
      createAuthorSummaryCard({
        title: "当前修稿对象",
        score: selectedTaskLink?.status || selectedPromise?.current_state || "待选择",
        body:
          `task ${selectedTaskLink?.chapter_task_id || "-"}\n` +
          `promise ${selectedPromise?.promise_id || "-"}\n` +
          `continuity ${(continuity.top_changed_chapters || [])[0]?.chapter_index ? `#${(continuity.top_changed_chapters || [])[0].chapter_index}` : "-"}\n` +
          `下一步 先标注 override / promise state，再回 Compare 看证据。`,
        actionLabel: "打开连续性对照",
        onAction: () => focusAuthorPanel("continuity"),
        primary: true,
      }),
      createAuthorSummaryCard({
        title: "修稿桥",
        score: `${(promises.open_promises || []).length} open promises`,
        body:
          `linked chapters ${selectedTaskLink?.linked_chapters?.length || 0}\n` +
          `compare chapters ${selectedTaskLink?.compare_chapters?.length || 0}\n` +
          `drift ${(continuity.promise_risks || []).length}\n` +
          `下一步 把当前问题从 simulation 拉回 Draft。`,
      }),
    ],
    style: [
      createAuthorSummaryCard({
        title: "风格窗口",
        score: `${(worldpack.narrative_style_pack?.tonal_lexicon || []).length} tokens`,
        body:
          `tone ${(worldpack.narrative_style_pack?.tonal_lexicon || []).slice(0, 3).join(" / ") || "-"}\n` +
          `hook ${(worldpack.narrative_style_pack?.hook_templates || []).slice(0, 2).join(" / ") || "-"}\n` +
          `turns ${worldpack.dialogue_realism_policy?.min_turns || 2}-${worldpack.dialogue_realism_policy?.max_turns || 3}\n` +
          `下一步 先调风格与节奏，再决定是否改 capability JSON。`,
        actionLabel: "查看最近修改",
        onAction: () => focusAuthorPanel("diff"),
        primary: true,
      }),
      createAuthorSummaryCard({
        title: "能力资产",
        score: `${Object.keys(worldpack.voice_profiles || {}).length} voices`,
        body:
          `voice ${Object.keys(worldpack.voice_profiles || {}).length}\n` +
          `action ${Object.keys(worldpack.emotion_action_policies || {}).length}\n` +
          `sensory ${Object.keys(worldpack.sensory_grounding_policies || {}).length}\n` +
          `scene ${Object.keys(worldpack.scene_realization_contracts || {}).length}`,
      }),
    ],
  };
  appendAuthorCardGrid(dom.authorDraftSectionSummary, cardsBySection[section] || []);
}

function renderAuthorSettingsSummary() {
  if (!dom.authorSettingsSummary) return;
  const preferences = authorState.authorNotificationPreferences?.preferences || [];
  const collaboration = authorState.authorCollaborationSummary || {};
  const authIdentity = authorState.authorAuthSession?.identity || null;
  const notificationTargets = preferences
    .map((item) => item.delivery_target || item.async_sink_name || "")
    .filter(Boolean)
    .slice(0, 3)
    .join(" / ") || "未配置外部投递";
  const cards = [
    createAuthorSummaryCard({
      title: "登录态",
      score: authIdentity?.actor_role || "未登录",
      body:
        `actor ${authIdentity?.actor_id || "-"}\n` +
        `account ${authIdentity?.account_id || "-"}\n` +
        `expires ${authorState.authorAuthSession?.expiresAt || "-"}\n` +
        `下一步 ${authIdentity ? "确认通知和协作" : "先建立作者身份"}`,
      warning: !authIdentity
        ? "当前没有登录态，通知与协作身份不会稳定同步。"
        : isAuthorSessionExpiringSoon(authorState.authorAuthSession?.expiresAt)
          ? "当前 token 即将过期，建议刷新会话。"
          : "",
      actionLabel: authIdentity ? "刷新会话" : "登录",
      onAction: () => focusAuthorPanel("auth_settings"),
      primary: true,
    }),
    createAuthorSummaryCard({
      title: "通知态",
      score: `${preferences.length} rules`,
      body:
        `in-app ${preferences.filter((item) => item.in_app_enabled).length}\n` +
        `async ${preferences.filter((item) => item.async_mirror_enabled).length}\n` +
        `targets ${notificationTargets}\n` +
        `下一步 ${preferences.length ? "检查是否覆盖当前 Draft" : "先建一条通知规则"}`,
      warning: !preferences.length
        ? "当前没有自定义通知规则，重要更新可能只能手动刷新看到。"
        : !preferences.some((item) => item.delivery_target || item.async_sink_name)
          ? "当前没有外部投递目标，异步提醒可能收不到。"
          : "",
      actionLabel: "打开通知设置",
      onAction: () => focusAuthorPanel("notification_settings"),
    }),
    createAuthorSummaryCard({
      title: "协作态",
      score: collaboration.recommended_next_action || "-",
      body:
        `open ${collaboration.open_thread_count ?? 0} · blocking ${collaboration.blocking_thread_count ?? 0}\n` +
        `approval ${(collaboration.approval_summary || {}).latest_status || "-"}\n` +
        `unread ${(collaboration.notification_summary || {}).unread_count ?? 0}\n` +
        `下一步 ${collaboration.recommended_next_action || "打开协作区"}`,
      warning:
        Number(collaboration.blocking_thread_count || 0) > 0
          ? `当前有 ${collaboration.blocking_thread_count} 个 blocker 线程待处理。`
          : Number((collaboration.notification_summary || {}).unread_count || 0) > 0
            ? `当前有 ${(collaboration.notification_summary || {}).unread_count || 0} 条未读协作通知。`
            : "",
      actionLabel: "打开协作区",
      onAction: () => focusAuthorPanel("collaboration"),
    }),
  ];
  appendAuthorCardGrid(dom.authorSettingsSummary, cards);
}

function renderAuthorSimulateSummary() {
  if (!dom.authorSimulateSummary) return;
  const simulationDrilldown = getSimulationDrilldown();
  const simulationReport = currentAuthorSimulationReport();
  const repairLoop = currentAuthorRepairLoopState();
  const creativeCockpit = currentAuthorCreativeCockpit() || {};
  const steeringTimeline = creativeCockpit.steering_timeline || {};
  const latestCheckpoint = [...(steeringTimeline.entries || [])].reverse().find((item) => item.entry_type === "checkpoint") || null;
  const latestReplan = [...(steeringTimeline.entries || [])].reverse().find((item) => item.entry_type === "replan") || null;
  const hottestRelationship = (creativeCockpit.relationship_hotspots?.items || [])[0] || null;
  const workflow = authorState.authorWorkflowSummary || {};
  const firstIssueTarget = (simulationDrilldown.issue_focus_queue || [])[0]?.chapter_targets?.[0] || null;
  const firstWeakChapter = (simulationDrilldown.weakest_chapters || [])[0] || null;
  if (!authorState.activeDraftVersionId) {
    clearNode(dom.authorSimulateSummary, "先选择并生成一个草稿，再看问题诊断的修稿驾驶舱。");
    return;
  }
  const cards = [
    ...(repairLoop?.available ? [createAuthorSummaryCard({
      title: `${repairLoop.issueLabel || repairLoop.issueCode || "Repair Loop"} 结果`,
      score: repairLoop.severityTrend || "-",
      body:
        `asset ${(repairLoop.assetLabel || repairLoop.assetType || "-")}${repairLoop.targetLabel ? ` -> ${repairLoop.targetLabel}` : ""}\n` +
        `issue count ${repairLoop.baselineIssueCount ?? "-"} -> ${repairLoop.currentIssueCount ?? "-"}\n` +
        `worst decision ${repairLoop.baselineWorstDecision || "-"} -> ${repairLoop.currentWorstDecision || "-"}\n` +
        `remaining ${(repairLoop.remainingChapters || []).map((item) => `${item.chapter_index}.${item.chapter_title || "-"}`).join(" / ") || "-"}\n` +
        `ready ${repairLoop.readyForValidation ? "yes" : "no"} · 回 ${repairLoop.validationPanelLabel || repairLoop.validationPanel || "-"}`,
      actionLabel: repairLoop.readyForValidation ? `去${repairLoop.validationPanelLabel || repairLoop.validationPanel || "复核"}` : "先看复核面板",
      onAction: () => {
        setAuthorRepairLoopHint(repairLoop);
        openAuthorRepairLoopValidationPanel();
      },
      primary: true,
    })] : []),
    createAuthorSummaryCard({
      title: "最新判断",
      score: workflow.simulation_summary?.latest_decision || "-",
      body:
        `freshness ${workflow.simulation_freshness?.status || "-"}\n` +
        `completed ${simulationReport?.completed_chapters || 0}\n` +
        `pass ${formatPercent(simulationReport?.evaluation_summary?.pass_rate)}\n` +
        `latest steer ${latestCheckpoint ? `${latestCheckpoint.title} @ ${latestCheckpoint.chapter_index}` : "-"}\n` +
        `下一步 ${firstIssueTarget ? "先跳到问题章节" : "先看重点问题章节"}`,
      actionLabel: firstIssueTarget ? `跳到第 ${firstIssueTarget.chapter_index} 章` : (latestCheckpoint ? `跳到第 ${latestCheckpoint.chapter_index} 章` : "查看重点问题章节"),
      onAction: () => {
        if (firstIssueTarget) {
          jumpToAuthorChapter(firstIssueTarget.chapter_index, "simulation");
          return;
        }
        if (latestCheckpoint?.chapter_index) {
          jumpToAuthorChapter(latestCheckpoint.chapter_index, "simulation");
          return;
        }
        if (firstWeakChapter) {
          jumpToAuthorChapter(firstWeakChapter.chapter_index, "simulation");
        }
      },
      primary: true,
    }),
    createAuthorSummaryCard({
      title: "Steering 回响",
      score: `${steeringTimeline.checkpoint_count ?? 0} 次`,
      body:
        `latest replan ${latestReplan?.summary || latestReplan?.title || "-"}\n` +
        `memory pending ${steeringTimeline.memory_patch_summary?.pending_count ?? 0} · adopted ${steeringTimeline.memory_patch_summary?.adopted_count ?? 0}\n` +
        `impacted ${(latestCheckpoint?.impacted_characters || []).join(" / ") || "-"}\n` +
        `next 先确认这次引导有没有把关系压到你想要的方向。`,
      actionLabel: latestCheckpoint?.chapter_index ? `查看第 ${latestCheckpoint.chapter_index} 章` : "打开创作驾驶舱",
      onAction: () => {
        if (latestCheckpoint?.chapter_index) {
          jumpToAuthorChapter(latestCheckpoint.chapter_index, "simulation");
          return;
        }
        focusAuthorCreativeCockpit();
      },
    }),
    createAuthorSummaryCard({
      title: "最短回路",
      score: hottestRelationship ? `${hottestRelationship.source_label} -> ${hottestRelationship.target_label}` : (firstWeakChapter?.chapter_index ? `#${firstWeakChapter.chapter_index}` : "待选择"),
      body:
        `weak chapter ${firstWeakChapter?.chapter_title || "-"}\n` +
        `relationship ${hottestRelationship ? `${hottestRelationship.dominant_metric_label} ${Number(hottestRelationship.dominant_metric_value || 0).toFixed(2)} · debt ${hottestRelationship.debt_count}` : "-"}\n` +
        `review ${formatAuthorActionHints((simulationDrilldown.next_actions || []).slice(0, 2))}\n` +
        `next 修完后再回章节对照和送审区留证据。`,
      actionLabel: "打开创作驾驶舱",
      onAction: focusAuthorCreativeCockpit,
    }),
  ];
  appendAuthorCardGrid(dom.authorSimulateSummary, cards);
}

function createAuthorCockpitPanel(title, score = "", description = "") {
  const panel = document.createElement("article");
  panel.className = "list-card author-cockpit-card";
  const head = document.createElement("div");
  head.className = "list-card-head";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const scoreNode = document.createElement("span");
  scoreNode.className = "list-card-score";
  scoreNode.textContent = score;
  head.append(heading, scoreNode);
  panel.appendChild(head);
  if (description) {
    const body = document.createElement("p");
    body.className = "list-card-body";
    body.textContent = description;
    panel.appendChild(body);
  }
  return panel;
}

let authorRelationshipNetworkMarkerCounter = 0;

function buildRelationshipNetworkSvg(network) {
  const width = 560;
  const height = 260;
  const nodeRadius = 26;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "author-relationship-network");
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const markerId = `author-network-arrow-${++authorRelationshipNetworkMarkerCounter}`;
  const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
  marker.setAttribute("id", markerId);
  marker.setAttribute("markerWidth", "10");
  marker.setAttribute("markerHeight", "10");
  marker.setAttribute("refX", "8");
  marker.setAttribute("refY", "3");
  marker.setAttribute("orient", "auto");
  const arrowPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arrowPath.setAttribute("d", "M0,0 L0,6 L9,3 z");
  arrowPath.setAttribute("fill", "rgba(45, 87, 211, 0.62)");
  marker.appendChild(arrowPath);
  defs.appendChild(marker);
  svg.appendChild(defs);

  const nodes = Array.isArray(network.nodes) ? network.nodes : [];
  const edges = Array.isArray(network.edges) ? network.edges.slice(0, 8) : [];
  const centerX = width / 2;
  const centerY = height / 2;
  const ringRadius = Math.max(92, Math.min(128, 76 + nodes.length * 8));
  const nodePositions = {};
  const directedEdgeKeys = new Set(
    edges
      .map((edge) => `${String(edge.source || "")}::${String(edge.target || "")}`)
      .filter((key) => key !== "::")
  );

  nodes.forEach((node, index) => {
    const angle = ((Math.PI * 2) / Math.max(1, nodes.length)) * index - Math.PI / 2;
    nodePositions[node.character_id] = {
      x: centerX + Math.cos(angle) * ringRadius,
      y: centerY + Math.sin(angle) * ringRadius,
    };
  });

  edges.forEach((edge) => {
    const source = nodePositions[edge.source];
    const target = nodePositions[edge.target];
    if (!source || !target) return;
    const deltaX = target.x - source.x;
    const deltaY = target.y - source.y;
    const distance = Math.hypot(deltaX, deltaY) || 1;
    const unitX = deltaX / distance;
    const unitY = deltaY / distance;
    const normalX = -unitY;
    const normalY = unitX;
    const reciprocalKey = `${String(edge.target || "")}::${String(edge.source || "")}`;
    const hasReciprocal = directedEdgeKeys.has(reciprocalKey) && reciprocalKey !== `${String(edge.source || "")}::${String(edge.target || "")}`;
    const curveDirection = hasReciprocal ? (String(edge.source || "") < String(edge.target || "") ? 1 : -1) : 0;
    const curveOffset = hasReciprocal ? Math.min(26, 12 + distance * 0.08) : 0;
    const startX = source.x + unitX * nodeRadius;
    const startY = source.y + unitY * nodeRadius;
    const endX = target.x - unitX * nodeRadius;
    const endY = target.y - unitY * nodeRadius;
    const controlX = (startX + endX) / 2 + normalX * curveOffset * curveDirection;
    const controlY = (startY + endY) / 2 + normalY * curveOffset * curveDirection;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", edge.conflict >= edge.intensity ? "rgba(165, 68, 47, 0.7)" : "rgba(45, 87, 211, 0.65)");
    path.setAttribute("stroke-width", String(1.5 + Math.min(3.5, Number(edge.dominant_metric_value || 0) * 4)));
    path.setAttribute("marker-end", `url(#${markerId})`);
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);

  });

  nodes.forEach((node) => {
    const position = nodePositions[node.character_id];
    if (!position) return;
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(position.x));
    circle.setAttribute("cy", String(position.y));
    circle.setAttribute("r", String(nodeRadius));
    circle.setAttribute("class", "author-relationship-network-node");
    svg.appendChild(circle);

    const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
    title.setAttribute("x", String(position.x));
    title.setAttribute("y", String(position.y - 2));
    title.setAttribute("text-anchor", "middle");
    title.setAttribute("class", "author-relationship-network-title");
    title.textContent = node.label;
    svg.appendChild(title);

    const subtitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
    subtitle.setAttribute("x", String(position.x));
    subtitle.setAttribute("y", String(position.y + 13));
    subtitle.setAttribute("text-anchor", "middle");
    subtitle.setAttribute("class", "author-relationship-network-subtitle");
    subtitle.textContent = node.role || node.character_id;
    svg.appendChild(subtitle);
  });

  return svg;
}

function relationshipStrengthLabel(value) {
  const normalized = Number(value || 0);
  if (normalized >= 0.6) return "强";
  if (normalized >= 0.35) return "中";
  return "轻";
}

function buildHeatmapIssueAggregation(chapters) {
  const counts = new Map();
  (chapters || []).forEach((chapter) => {
    const uniqueCodes = [...new Set((chapter.issue_codes || []).map((item) => String(item || "").trim()).filter(Boolean))];
    uniqueCodes.forEach((issueCode) => {
      counts.set(issueCode, (counts.get(issueCode) || 0) + 1);
    });
  });
  return [...counts.entries()]
    .map(([issueCode, count]) => ({ issueCode, count }))
    .sort((left, right) => right.count - left.count || left.issueCode.localeCompare(right.issueCode));
}

function authorSceneFunctionShortLabel(sceneFunction) {
  const normalized = String(sceneFunction || "").trim();
  return (
    {
      false_peace: "假平静",
      truth_trial: "真相试压",
      trust_test: "信任试探",
      temptation: "诱惑推进",
      reversal: "关系反转",
      discovery: "真相揭口",
      confession_window: "告白窗口",
      karma_ripening: "代价追上",
      setup: "开场搭建",
      unknown: "未标注场景",
    }[normalized] || normalized || "stable"
  );
}

function authorHeatmapDecisionLabel(decision) {
  return (
    {
      pass: "通过",
      rewrite: "重写",
      block: "阻断",
      stable: "稳定",
      watch: "关注",
      critical: "高危",
    }[String(decision || "").trim()] || String(decision || "-").trim() || "-"
  );
}

function appendHeatmapIssueBadgeRow(targetNode, chapter, issueAggregation) {
  const issueCodes = [...new Set((chapter.issue_codes || []).map((item) => String(item || "").trim()).filter(Boolean))];
  if (!issueCodes.length) return;
  const aggregationMap = new Map((issueAggregation || []).map((item) => [item.issueCode, Number(item.count || 0)]));
  const badgeRow = document.createElement("div");
  badgeRow.className = "author-heatmap-cell-badges";
  issueCodes.slice(0, 2).forEach((issueCode) => {
    const badge = document.createElement("span");
    badge.className = "author-heatmap-badge";
    const repeatCount = aggregationMap.get(issueCode) || 0;
    badge.textContent = repeatCount > 1 ? `${issueCode} ×${repeatCount}` : issueCode;
    badge.title = repeatCount > 1 ? `${issueCode} 在 ${(issueAggregation || []).find((item) => item.issueCode === issueCode)?.count || repeatCount} 个章节重复出现` : issueCode;
    badgeRow.appendChild(badge);
  });
  if (issueCodes.length > 2) {
    const overflowBadge = document.createElement("span");
    overflowBadge.className = "author-heatmap-badge is-overflow";
    overflowBadge.textContent = `+${issueCodes.length - 2}`;
    overflowBadge.title = issueCodes.slice(2).join(" / ");
    badgeRow.appendChild(overflowBadge);
  }
  targetNode.appendChild(badgeRow);
}

function renderAuthorCreativeCockpit() {
  if (!dom.authorCreativeCockpit) return;
  const cockpit = currentAuthorCreativeCockpit();
  clearNode(dom.authorCreativeCockpit);
  if (!cockpit?.available) {
    clearNode(dom.authorCreativeCockpit, "运行 simulation 后，这里会显示人物关系网、Steering 时间线、章节热图和长线结构快照。");
    return;
  }

  const relationshipNetwork = cockpit.relationship_network || {};
  const hotspots = cockpit.relationship_hotspots || {};
  const steeringTimeline = cockpit.steering_timeline || {};
  const chapterHeatmap = cockpit.chapter_heatmap || {};
  const issuePriorityGroups = chapterHeatmap.issue_priority_groups || [];
  const storyStructure = cockpit.story_structure_snapshot || {};

  const summaryGrid = document.createElement("div");
  summaryGrid.className = "author-workspace-summary-grid";
  summaryGrid.appendChild(
    createAuthorSummaryCard({
      title: "关系图谱",
      score: `${Math.min(5, (hotspots.items || []).length)} 条热点`,
      body:
        `当前最强关系 ${((hotspots.items || [])[0]?.dominant_metric_label || "-")} ${Number((hotspots.items || [])[0]?.dominant_metric_value || 0).toFixed(2)}\n` +
        `最重债务 ${Math.max(...((hotspots.items || []).map((item) => Number(item.debt_count || 0))), 0)}\n` +
        `下一步 先处理榜单第一条关系，再决定这次引导到底改到了谁。`,
      actionLabel: "回作品稿边栏",
      onAction: () => focusAuthorPanel("draft_detail"),
    })
  );
  summaryGrid.appendChild(
    createAuthorSummaryCard({
      title: "Steering 时间线",
      score: `${steeringTimeline.checkpoint_count ?? 0} 次`,
      body:
        `replans ${steeringTimeline.replan_event_count ?? 0}\n` +
        `memory pending ${steeringTimeline.memory_patch_summary?.pending_count ?? 0}\n` +
        `memory adopted ${steeringTimeline.memory_patch_summary?.adopted_count ?? 0}\n` +
        `next 看这轮引导有没有变成真正被吸收的记忆。`,
    })
  );
  summaryGrid.appendChild(
    createAuthorSummaryCard({
      title: "章节热图",
      score: `${(chapterHeatmap.chapters || []).length} 章`,
      body:
        `阻断 ${(chapterHeatmap.chapters || []).filter((item) => item.decision === "block").length}\n` +
        `重写 ${(chapterHeatmap.chapters || []).filter((item) => item.decision === "rewrite").length}\n` +
        `通过 ${(chapterHeatmap.chapters || []).filter((item) => item.decision === "pass").length}\n` +
        `issue groups ${issuePriorityGroups.map((item) => item.issue_code).join(" / ") || "-"}\n` +
        `next 先去最红的章节，再回 Draft 修素材。`,
    })
  );
  dom.authorCreativeCockpit.appendChild(summaryGrid);

  const impactPanel = createAuthorCockpitPanel(
    "关系影响榜单",
    `${Math.min(5, (hotspots.items || []).length)} 条`,
    "先看最值得处理的几组关系：是谁影响谁、当前主导指标是什么、为什么值得现在就处理。"
  );
  if ((hotspots.items || []).length) {
    (hotspots.items || []).slice(0, 5).forEach((edge, index) => {
      const row = document.createElement("div");
      row.className = "author-cockpit-row";
      const copy = document.createElement("p");
      copy.className = "author-cockpit-row-copy";
      copy.textContent =
        `${index + 1}. ${edge.source_label} -> ${edge.target_label}\n` +
        `主导关系 ${edge.dominant_metric_label} ${Number(edge.dominant_metric_value || 0).toFixed(2)} · ${relationshipStrengthLabel(edge.dominant_metric_value)}\n` +
        `冲突 ${Number(edge.conflict || 0).toFixed(2)} · 债务 ${edge.debt_count}\n` +
        `线索 ${(edge.notes_preview || []).join(" / ") || "暂无额外注记"}`;
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      const sourceButton = document.createElement("button");
      sourceButton.className = "ghost-action";
      sourceButton.textContent = `打开 ${edge.source_label}`;
      sourceButton.addEventListener("click", () => openAuthorCharacterAsset(edge.source));
      const targetButton = document.createElement("button");
      targetButton.className = "ghost-action";
      targetButton.textContent = `打开 ${edge.target_label}`;
      targetButton.addEventListener("click", () => openAuthorCharacterAsset(edge.target));
      actions.append(sourceButton, targetButton);
      row.append(copy, actions);
      impactPanel.appendChild(row);
    });
  }
  dom.authorCreativeCockpit.appendChild(impactPanel);

  const networkPanel = createAuthorCockpitPanel(
    "关系结构示意",
    `${Math.min(8, (relationshipNetwork.edges || []).length)} 条边`,
    "这只是辅助示意图。真正要处理哪条关系，请优先看上面的关系影响榜单。"
  );
  if (relationshipNetwork.available) {
    networkPanel.appendChild(buildRelationshipNetworkSvg(relationshipNetwork));
    const note = document.createElement("p");
    note.className = "author-cockpit-legend-item";
    note.textContent = "图上只保留最关键的几条关系边，边越粗代表当前强度越高。";
    networkPanel.appendChild(note);
  }
  dom.authorCreativeCockpit.appendChild(networkPanel);

  const hotspotsPanel = createAuthorCockpitPanel("关系热点详情", `${(hotspots.items || []).length} 条`, "需要更细的关系细节时，再看这里的完整说明和角色卡入口。");
  if ((hotspots.items || []).length) {
    (hotspots.items || []).forEach((edge) => {
      const row = document.createElement("div");
      row.className = "author-cockpit-row";
      const copy = document.createElement("p");
      copy.className = "author-cockpit-row-copy";
      copy.textContent = `${edge.source_label} -> ${edge.target_label}\n${edge.dominant_metric_label} ${Number(edge.dominant_metric_value || 0).toFixed(2)} · conflict ${Number(edge.conflict || 0).toFixed(2)} · debt ${edge.debt_count}\n${(edge.notes_preview || []).join(" / ") || "暂无额外注记"}`;
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      const sourceButton = document.createElement("button");
      sourceButton.className = "ghost-action";
      sourceButton.textContent = "源角色卡";
      sourceButton.addEventListener("click", () => openAuthorCharacterAsset(edge.source));
      const targetButton = document.createElement("button");
      targetButton.className = "ghost-action";
      targetButton.textContent = "目标角色卡";
      targetButton.addEventListener("click", () => openAuthorCharacterAsset(edge.target));
      actions.append(sourceButton, targetButton);
      row.append(copy, actions);
      hotspotsPanel.appendChild(row);
    });
  }
  dom.authorCreativeCockpit.appendChild(hotspotsPanel);

  const steeringPanel = createAuthorCockpitPanel("Steering 时间线", `${steeringTimeline.checkpoint_count ?? 0} checkpoints`, "每一条 steering 都应该能回到它真正改动的角色、场景或任务资产。");
  if ((steeringTimeline.entries || []).length) {
    (steeringTimeline.entries || []).forEach((entry) => {
      const row = document.createElement("div");
      row.className = "author-cockpit-row";
      const copy = document.createElement("p");
      copy.className = "author-cockpit-row-copy";
      copy.textContent = `第 ${entry.chapter_index || "-"} 章 · ${entry.title || entry.entry_type}\n${entry.summary || "-"}\n角色 ${(entry.impacted_characters || []).join(" / ") || "-"} · ${entry.status || "-"}\nscene ${entry.scene_id || entry.scene_function || "-"} · task ${entry.chapter_task_id || entry.arc_id || "-"}`;
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      if ((entry.impacted_character_ids || [])[0]) {
        const characterButton = document.createElement("button");
        characterButton.className = "ghost-action";
        characterButton.textContent = "角色卡";
        characterButton.addEventListener("click", () => openAuthorCharacterAsset(entry.impacted_character_ids[0]));
        actions.appendChild(characterButton);
      }
      if (entry.scene_id || entry.scene_function) {
        const sceneButton = document.createElement("button");
        sceneButton.className = "ghost-action";
        sceneButton.textContent = "场景蓝图";
        sceneButton.addEventListener("click", () => openAuthorSceneAsset({ sceneId: entry.scene_id, sceneFunction: entry.scene_function }));
        actions.appendChild(sceneButton);
      }
      if (entry.chapter_task_id || entry.arc_id || entry.volume_id) {
        const taskButton = document.createElement("button");
        taskButton.className = "ghost-action";
        taskButton.textContent = "章节任务";
        taskButton.addEventListener("click", () => openAuthorTaskAsset({ volumeId: entry.volume_id, arcId: entry.arc_id, taskId: entry.chapter_task_id }));
        actions.appendChild(taskButton);
      }
      const simulationButton = document.createElement("button");
      simulationButton.className = "ghost-action";
      simulationButton.textContent = "看 simulation";
      simulationButton.addEventListener("click", () => jumpToAuthorChapter(entry.chapter_index, "simulation"));
      actions.appendChild(simulationButton);
      row.append(copy, actions);
      steeringPanel.appendChild(row);
    });
  }
  dom.authorCreativeCockpit.appendChild(steeringPanel);

  const heatmapPanel = createAuthorCockpitPanel(
    "章节热图",
    `${(chapterHeatmap.chapters || []).length} 章`,
    "颜色越重，说明当前 simulation 越需要你优先处理这一章。点击任意章节会直接跳到对应模拟条目。"
  );
  const heatmapIssueAggregation = buildHeatmapIssueAggregation(chapterHeatmap.chapters || []);
  if (issuePriorityGroups.length) {
    const issuePriorityBlock = document.createElement("div");
    issuePriorityBlock.className = "author-issue-priority-grid";
    issuePriorityGroups.forEach((group) => {
      const row = document.createElement("div");
      row.className = "author-cockpit-row";
      const primary = group.primary_asset || {};
      const copy = document.createElement("p");
      copy.className = "author-cockpit-row-copy";
      copy.textContent =
        `${group.issue_code} · ${group.label || "-"}\n` +
        `涉及章节 ${group.chapter_count || 0} · 主修 ${primary.label || "-"}${primary.target_label ? ` -> ${primary.target_label}` : ""}\n` +
        `复核面板 ${group.primary_validation_panel_label || primary.validation_panel_label || "-"}\n` +
        `建议 ${group.fix_hint || "-"}\n` +
        `热点 ${(group.chapters || []).map((chapter) => `${chapter.chapter_index}. ${chapter.chapter_title || "-"}`).join(" / ") || "-"}`;
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      (group.asset_priorities || []).forEach((priority) => {
        const button = document.createElement("button");
        button.className =
          primary.asset_type === priority.asset_type && priority.available
            ? "primary-action"
            : "ghost-action";
        button.textContent = `${priority.priority}. ${priority.label}${priority.available ? "" : " (缺锚点)"}`;
        button.disabled = !priority.available;
        button.title = priority.reason || "";
        button.addEventListener("click", () => openAuthorPriorityAsset(priority, group));
        actions.appendChild(button);
      });
      if (primary.validation_panel) {
        const validationButton = document.createElement("button");
        validationButton.className = "ghost-action";
        validationButton.textContent = `复核 ${group.primary_validation_panel_label || primary.validation_panel}`;
        validationButton.addEventListener("click", () => {
          setAuthorRepairLoopHint(buildAuthorRepairLoopHint(primary, group));
          openAuthorRepairLoopValidationPanel();
        });
        actions.appendChild(validationButton);
      }
      const inspectButton = document.createElement("button");
      inspectButton.className = "ghost-action";
      inspectButton.textContent = "看首个热点章节";
      inspectButton.addEventListener("click", () => {
        if ((group.chapters || [])[0]?.chapter_index) {
          jumpToAuthorChapter(group.chapters[0].chapter_index, "simulation");
        }
      });
      actions.appendChild(inspectButton);
      row.append(copy, actions);
      issuePriorityBlock.appendChild(row);
    });
    heatmapPanel.appendChild(issuePriorityBlock);
  }
  if (heatmapIssueAggregation.length) {
    const heatmapBadgeSummary = document.createElement("div");
    heatmapBadgeSummary.className = "author-heatmap-summary-badges";
    heatmapIssueAggregation.slice(0, 4).forEach((item) => {
      const badge = document.createElement("span");
      badge.className = "author-heatmap-summary-badge";
      badge.textContent = `${item.issueCode} ×${item.count}`;
      heatmapBadgeSummary.appendChild(badge);
    });
    heatmapPanel.appendChild(heatmapBadgeSummary);
  }
  const heatmapGrid = document.createElement("div");
  heatmapGrid.className = "author-heatmap-grid";
  (chapterHeatmap.chapters || []).forEach((chapter) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `author-heatmap-cell is-${chapter.severity || "stable"}`;
    const title = document.createElement("strong");
    title.textContent = String(chapter.chapter_index || "-");
    const decision = document.createElement("span");
    decision.textContent = authorHeatmapDecisionLabel(chapter.decision || "-");
    const caption = document.createElement("small");
    caption.textContent = authorSceneFunctionShortLabel(chapter.scene_function || chapter.dominant_issue || "stable");
    button.append(title, decision);
    appendHeatmapIssueBadgeRow(button, chapter, heatmapIssueAggregation);
    button.appendChild(caption);
    button.addEventListener("click", () => {
      jumpToAuthorChapter(chapter.chapter_index, "simulation");
    });
    heatmapGrid.appendChild(button);
  });
  heatmapPanel.appendChild(heatmapGrid);
  const hotspotList = document.createElement("div");
  hotspotList.className = "author-cockpit-legend";
  (chapterHeatmap.chapters || [])
    .slice()
    .sort((left, right) => {
      const order = { critical: 0, watch: 1, stable: 2 };
      return (
        (order[left.severity || "stable"] - order[right.severity || "stable"]) ||
        Number(left.overall_score || 0) - Number(right.overall_score || 0)
      );
    })
    .slice(0, 4)
    .forEach((chapter) => {
      const row = document.createElement("div");
      row.className = "author-cockpit-row";
      const copy = document.createElement("p");
      copy.className = "author-cockpit-row-copy";
      copy.textContent = `第 ${chapter.chapter_index} 章 · ${chapter.chapter_title || "-"}\n${chapter.dominant_issue || authorSceneFunctionShortLabel(chapter.scene_function) || "stable"} · score ${Number(chapter.overall_score || 0).toFixed(3)}\nscene ${chapter.scene_id || authorSceneFunctionShortLabel(chapter.scene_function) || "-"} · task ${chapter.chapter_task_id || chapter.arc_id || "-"}`;
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      if (chapter.scene_id || chapter.scene_function) {
        const sceneButton = document.createElement("button");
        sceneButton.className = "ghost-action";
        sceneButton.textContent = "场景蓝图";
        sceneButton.addEventListener("click", () => openAuthorSceneAsset({ sceneId: chapter.scene_id, sceneFunction: chapter.scene_function }));
        actions.appendChild(sceneButton);
      }
      if (chapter.chapter_task_id || chapter.arc_id || chapter.volume_id) {
        const taskButton = document.createElement("button");
        taskButton.className = "ghost-action";
        taskButton.textContent = "章节任务";
        taskButton.addEventListener("click", () => openAuthorTaskAsset({ volumeId: chapter.volume_id, arcId: chapter.arc_id, taskId: chapter.chapter_task_id }));
        actions.appendChild(taskButton);
      }
      const simulationButton = document.createElement("button");
      simulationButton.className = "ghost-action";
      simulationButton.textContent = "看 simulation";
      simulationButton.addEventListener("click", () => jumpToAuthorChapter(chapter.chapter_index, "simulation"));
      actions.appendChild(simulationButton);
      row.append(copy, actions);
      hotspotList.appendChild(row);
    });
  heatmapPanel.appendChild(hotspotList);
  dom.authorCreativeCockpit.appendChild(heatmapPanel);

  const structurePanel = createAuthorCockpitPanel(
    "长线结构快照",
    `${storyStructure.volume_snapshot_count ?? 0} volume snapshots`,
    `series snapshots ${storyStructure.series_snapshot_count ?? 0}\nending ${(storyStructure.series_ending_checkpoint?.status || "-")} · ready ${storyStructure.series_ending_checkpoint?.terminal_ready ? "yes" : "no"}`
  );
  (storyStructure.volumes || []).forEach((volume) => {
    const row = document.createElement("div");
    row.className = "author-cockpit-row";
    const copy = document.createElement("p");
    copy.className = "author-cockpit-row-copy";
    copy.textContent = `${volume.title || volume.volume_id}\nchapters ${volume.simulated_chapter_count ?? 0}/${volume.target_chapters ?? 0} · snapshots ${volume.memory_snapshot_count ?? 0} · ${volume.status || "-"}`;
    const actions = document.createElement("div");
    actions.className = "composer-actions author-card-actions";
    if (volume.first_arc_id || volume.volume_id) {
      const taskButton = document.createElement("button");
      taskButton.className = "ghost-action";
      taskButton.textContent = "打开本卷任务";
      taskButton.addEventListener("click", () => openAuthorTaskAsset({ volumeId: volume.volume_id, arcId: volume.first_arc_id }));
      actions.appendChild(taskButton);
    }
    row.append(copy, actions);
    structurePanel.appendChild(row);
  });
  (storyStructure.arcs || []).forEach((arc) => {
    const row = document.createElement("div");
    row.className = "author-cockpit-row";
    const copy = document.createElement("p");
    copy.className = "author-cockpit-row-copy";
    copy.textContent = `${arc.title || arc.arc_id}\nchapters ${arc.simulated_chapter_count ?? 0}/${arc.target_chapters ?? 0} · ${arc.status || "-"}`;
    const actions = document.createElement("div");
    actions.className = "composer-actions author-card-actions";
    const taskButton = document.createElement("button");
    taskButton.className = "ghost-action";
    taskButton.textContent = "打开章节任务";
    taskButton.addEventListener("click", () => openAuthorTaskAsset({ volumeId: arc.volume_id, arcId: arc.arc_id, taskId: arc.first_task_id }));
    actions.appendChild(taskButton);
    row.append(copy, actions);
    structurePanel.appendChild(row);
  });
  dom.authorCreativeCockpit.appendChild(structurePanel);
}

function renderAuthorReviewSummary() {
  if (!dom.authorReviewSummary) return;
  if (!authorState.activeDraftVersionId) {
    clearNode(dom.authorReviewSummary, "选择一个草稿后，这里会显示当前版本的证据顺序与送审状态。");
    return;
  }
  const latestDiff = getLatestDiffSummary();
  const revisions = getActiveRevisionHistory();
  const compareWorkbench = getContinuityDiffWorkbench();
  const workflow = authorState.authorWorkflowSummary || {};
  const firstChanged = (compareWorkbench.top_changed_chapters || [])[0] || null;
  const cards = [
    createAuthorSummaryCard({
      title: "送审准备度",
      score: authorStageLabel(workflow.stage),
      body:
        `recommended ${workflow.recommended_action || "-"}\n` +
        `latest diff ${latestDiff.summary_text || "-"}\n` +
        `version history ${revisions.length}\n` +
        `下一步 ${workflow.stage === "ready_to_submit" ? "可以送审" : "先补齐证据"}`,
      actionLabel: workflow.stage === "ready_to_submit" ? "送审" : "看版本轨迹",
      onAction: () => {
        if (workflow.stage === "ready_to_submit" && authorState.activeDraftVersionId) {
          submitDraftVersion(authorState.activeDraftVersionId).catch((error) => {
            authorNotice(formatAuthorApiErrorMessage(error, "送审失败，请稍后再试。"), "error");
          });
          return;
        }
        focusAuthorPanel("version_history");
      },
      primary: true,
    }),
    createAuthorSummaryCard({
      title: "章节对照证据",
      score: firstChanged?.chapter_index ? `#${firstChanged.chapter_index}` : "待选择",
      body:
        `changed ${(compareWorkbench.top_changed_chapters || []).length}\n` +
        `current ${(firstChanged?.after_title || firstChanged?.chapter_title || "-")}\n` +
        `issue ${(firstChanged?.issue_codes || []).join(" / ") || "-"}\n` +
        `下一步 先确认最重要的修改前后章节。`,
      actionLabel: "打开章节对照",
      onAction: () => focusAuthorPanel("compare"),
    }),
    createAuthorSummaryCard({
      title: "版本证据栈",
      score: `${revisions.length} revisions`,
      body:
        `latest source ${revisions[0]?.change_context?.source || "-"}\n` +
        `latest label ${revisions[0]?.change_context?.label || "-"}\n` +
        `改写预览 ${authorState.authorCurrentRewritePatchExport ? "已准备" : "待生成"}\n` +
        `下一步 按最近修改 -> 章节对照 -> 版本轨迹的顺序检查。`,
    }),
  ];
  appendAuthorCardGrid(dom.authorReviewSummary, cards);
}

function renderAuthorDraftDetail() {
  clearNode(dom.authorDraftDetail);
  const worldpack = getActiveDraftWorldpack();
  if (!worldpack || !authorState.activeDraftVersionId) {
    clearNode(dom.authorDraftDetail, "选择一个草稿后，这里会显示当前定位、健康状态与诊断摘要。");
    return;
  }
  const validation = authorState.activeDraftDetail?.validation_report || authorState.authorValidationReport || {};
  const simulation = authorState.activeDraftDetail?.simulation_report || authorState.authorSimulationReport || {};
  const simulationDrilldown = getSimulationDrilldown();
  const latestDiff = getLatestDiffSummary();
  const stylePack = worldpack.narrative_style_pack || {};
  const detail = document.createElement("article");
  detail.className = "list-card author-detail-card";
  const diagnosis = simulation.cross_pack_summary?.worlds?.find((item) => item.world_id === authorState.activeDraftDetail?.world_id) || null;
  const weakestSummary = (diagnosis?.issue_summary?.weakest_dimensions || []).map((item) => `${item.name} ${Number(item.value || 0).toFixed(3)}`).join(" / ") || "暂无明显弱项";
  detail.innerHTML = `
    <div class="list-card-head">
      <h3>${worldpack.title || authorState.activeDraftDetail?.world_id || authorState.activeDraftVersionId}</h3>
      <span class="list-card-score">${authorState.activeDraftDetail?.status || "草稿中"}</span>
    </div>
    <div class="author-detail-grid">
      <section class="author-detail-section">
        <span>项目定位</span>
        <strong>${authorState.activeDraftDetail?.world_id || "-"}</strong>
        <p>${(worldpack.manifest?.genres || []).join(" / ") || "未标注题材"} · ${worldpack.manifest?.risk_rating || "未标注风险"}<br>${authorState.activeDraftVersionId}</p>
      </section>
      <section class="author-detail-section">
        <span>当前健康</span>
        <strong>校验 ${validation.ok ? "通过" : "待处理"}</strong>
        <p>问题 ${(validation.errors || []).length || 0} · 提醒 ${(validation.warnings || []).length || 0}<br>诊断 ${simulation.latest_decision || "-"} · 通过率 ${formatPercent(simulation.evaluation_summary?.pass_rate)}</p>
      </section>
      <section class="author-detail-section">
        <span>运行态</span>
        <strong>章节 ${simulationDrilldown.completed_chapters ?? simulation.completed_chapters ?? 0}</strong>
        <p>完成度 ${simulationDrilldown.completion_ratio !== undefined ? Number(simulationDrilldown.completion_ratio).toFixed(3) : "-"}<br>当前停止原因 ${simulationDrilldown.stop_reason || "-"}</p>
      </section>
      <section class="author-detail-section">
        <span>叙事风格</span>
        <strong>${(stylePack.tonal_lexicon || []).slice(0, 2).join(" / ") || "待补充"}</strong>
        <p>钩子 ${(stylePack.hook_templates || [])[0] || "-"}<br>对白轮次 ${worldpack.dialogue_realism_policy?.min_turns || 2}-${worldpack.dialogue_realism_policy?.max_turns || 3}</p>
      </section>
      <section class="author-detail-section author-detail-section--wide">
        <span>当前诊断</span>
        <strong>${diagnosis?.issue_summary?.dominant_issue || "暂无主导问题"}</strong>
        <p>薄弱项 ${weakestSummary}<br>建议处理 ${diagnosis?.issue_summary?.recommended_target || "-"}<br>最近修改 ${latestDiff.summary_text || "-"}</p>
      </section>
    </div>
  `;
  dom.authorDraftDetail.appendChild(detail);
  const workSummary = document.createElement("article");
  workSummary.className = "list-card";
  const activeWork = authorState.activeWorkDetail;
  const workDiag = authorState.authorWorkDiagnostics || {};
  workSummary.innerHTML = `
    <div class="list-card-head">
      <h3>作品稿</h3>
      <span class="list-card-score">${activeWork ? `${activeWork.chapter_count || 0}/${activeWork.target_chapter_count || 0}` : "未初始化"}</span>
    </div>
    <p class="list-card-body">${
      activeWork
        ? `状态 ${activeWork.status || "-"}\n章节 ${activeWork.chapter_count || 0}/${activeWork.target_chapter_count || 0}\n诊断 ${workDiag.latest_decision || "-"} · pass ${formatPercent((workDiag.evaluation_summary || {}).pass_rate)}`
        : "当前 draft 还没有作品稿。先在创作台里初始化作品稿，再逐章生成和编辑。"
    }</p>
  `;
  dom.authorDraftDetail.appendChild(workSummary);
  const readiness = authorState.activeDraftDetail?.longform_readiness || {};
  const quickBriefRunway = authorState.activeDraftDetail?.quick_brief_runway_summary || {};
  const promiseRunway = authorState.activeDraftDetail?.promise_runway_summary || {};
  const capabilitySummary = document.createElement("article");
  capabilitySummary.className = "list-card";
  capabilitySummary.innerHTML = `
    <div class="list-card-head">
      <h3>长线能力</h3>
      <span class="list-card-score">${authorState.activeDraftDetail?.claim_safe_band ? `${authorState.activeDraftDetail.claim_safe_band}章` : "未达安全承诺"}</span>
    </div>
    <p class="list-card-body">入口 ${authorState.activeDraftDetail?.entry_mode || "-"}\n目标 ${authorState.activeDraftDetail?.requested_target_chapters || "-"} 章 / ${authorState.activeDraftDetail?.requested_target_band || "-"} band\n当前支持 ${authorState.activeDraftDetail?.supported_target_band || "-"} · readiness ${readiness.status || "-"}\n结构 ${authorState.activeDraftDetail?.longform_structure_counts?.character_count || 0} 角色 / ${authorState.activeDraftDetail?.longform_structure_counts?.scene_blueprint_count || 0} 场景 / ${authorState.activeDraftDetail?.longform_structure_counts?.location_count || 0} 地点 / ${authorState.activeDraftDetail?.longform_structure_counts?.scene_family_count || 0} scene family / ${authorState.activeDraftDetail?.longform_structure_counts?.distinct_role_pair_count || 0} role pairs\nquick brief runway ${quickBriefRunway.status || "-"} · 缺口 ${(quickBriefRunway.gaps || []).join(" / ") || "-"}\npromise runway ${promiseRunway.runway_status || "-"} · open ${promiseRunway.open_count ?? 0} · overdue ${promiseRunway.overdue_count ?? 0}\nblockers ${(readiness.blockers || []).map((item) => item.message).join(" / ") || "-"}</p>
  `;
  dom.authorDraftDetail.appendChild(capabilitySummary);
  const actions = document.createElement("div");
  actions.className = "composer-actions author-card-actions";
  const openReviewButton = document.createElement("button");
  openReviewButton.className = "ghost-action";
  openReviewButton.textContent = "打开管理员审核视图";
  openReviewButton.addEventListener("click", () => openAuthorAdminView("review"));
  actions.appendChild(openReviewButton);
  const openAccountButton = document.createElement("button");
  openAccountButton.className = "ghost-action";
  openAccountButton.textContent = "打开管理员账户视图";
  openAccountButton.addEventListener("click", () => openAuthorAdminView("account"));
  actions.appendChild(openAccountButton);
  detail.appendChild(actions);
}

function renderAuthorWorkStudio() {
  clearNode(dom.authorDraftSectionSummary);
  const activeDraft = authorState.activeDraftDetail;
  if (!activeDraft || !authorState.activeDraftVersionId) {
    clearNode(dom.authorDraftSectionSummary, "先选择一个 draft，再初始化作品稿。");
    return;
  }
  const work = authorState.activeWorkDetail;
  const chapters = work?.chapters || [];
  const chapterPayload = authorState.activeWorkChapterDetail || null;
  const chapterDetail = chapterPayload?.chapter || null;
  const draftSection = AUTHOR_DRAFT_SECTION_CONFIG.find((item) => item.key === currentAuthorDraftSection()) || AUTHOR_DRAFT_SECTION_CONFIG[0];
  const diagnostics = authorState.authorWorkDiagnostics || work?.diagnostics_summary || work?.diagnostics_summary_json || {};
  const evaluationSummary = diagnostics.evaluation_summary || {};
  const chapterDiagnostics = chapterDetail?.latest_diagnostic_summary || {};
  const chapterTask = chapterDetail?.chapter_task || chapterDetail?.chapter_task_json || {};
  const chapterChoices = chapterDetail?.choices || chapterDetail?.choices_json || [];
  const creativeCockpit = activeDraft?.creative_cockpit || activeDraft?.simulation_report?.creative_cockpit || {};
  const relationshipHotspots = creativeCockpit.relationship_hotspots?.items || [];
  const currentDraft = activeAuthorWorkDraft();
  const nextAction = authorWorkNextAction(work);

  const shell = document.createElement("section");
  shell.className = "author-editor-shell";

  const hero = document.createElement("article");
  hero.className = "author-editor-hero";
  const heroHead = document.createElement("div");
  heroHead.className = "author-editor-hero-head";
  const heroTitle = document.createElement("div");
  heroTitle.innerHTML = `
    <p class="author-editor-kicker">作品稿主工作区</p>
    <h3>${work ? work.title || "当前作品稿" : "初始化你的第一部作品稿"}</h3>
    <p class="panel-copy">${
      work
        ? `当前 Draft ${authorState.activeDraftVersionId || "-"} · 创作配置层 ${draftSection.label} · 下一步 ${nextAction}。`
        : `世界设定和长篇规划已经准备好，这里会成为你每天真正写作、修稿和送审的入口。`
    }</p>
  `;
  heroHead.appendChild(heroTitle);
  if ((work?.branch_family || []).length > 1) {
    const branchSwitcher = document.createElement("div");
    branchSwitcher.className = "composer-actions author-card-actions";
    (work.branch_family || []).forEach((branch) => {
      const button = document.createElement("button");
      button.className = branch.work_id === work.work_id ? "primary-action" : "ghost-action";
      button.textContent = branch.branch_kind === "mainline" ? "主线" : branch.branch_name || "平行宇宙";
      button.title = branch.branch_origin_label
        ? `${branch.branch_origin_label}\n从第 ${branch.fork_after_chapter_index || 0} 章后分叉`
        : `从第 ${branch.fork_after_chapter_index || 0} 章后分叉`;
      button.addEventListener("click", async () => {
        try {
          await switchActiveAuthorWork(branch.work_id);
        } catch (error) {
          authorNotice(formatAuthorApiErrorMessage(error, "切换命运线失败，请稍后再试。"), "error");
        }
      });
      branchSwitcher.appendChild(button);
    });
    heroTitle.appendChild(branchSwitcher);
  }
  const heroStatus = document.createElement("div");
  heroStatus.className = "author-editor-hero-status";
  [
    { label: "作品状态", value: work ? authorWorkStatusLabel(work.status) : "未初始化", tone: authorWorkStatusTone(work?.status) },
    { label: "章节进度", value: work ? `${work.chapter_count || 0}/${work.target_chapter_count || 0}` : "0/0", tone: "is-pending" },
    { label: "当前诊断", value: diagnostics.latest_decision || "-", tone: diagnostics.latest_decision === "pass" ? "is-complete" : "is-pending" },
    { label: "当前章节", value: chapterDetail ? `第 ${chapterDetail.chapter_index} 章` : "未选择", tone: chapterDetail ? "is-active" : "is-pending" },
  ].forEach((item) => {
    const chip = document.createElement("div");
    chip.className = `author-editor-status-chip ${item.tone || "is-pending"}`;
    chip.innerHTML = `<span>${item.label}</span><strong>${item.value}</strong>`;
    heroStatus.appendChild(chip);
  });
  heroHead.appendChild(heroStatus);
  hero.appendChild(heroHead);

  const actionBar = document.createElement("div");
  actionBar.className = "author-editor-actions";
  const createButton = document.createElement("button");
  createButton.className = work ? "ghost-action" : "primary-action";
  createButton.textContent = work ? "刷新作品稿" : "初始化作品稿";
  createButton.addEventListener("click", async () => {
    try {
      await createAuthorWorkFromDraft();
    } catch (error) {
      authorNotice(formatAuthorApiErrorMessage(error, "初始化作品稿失败，请稍后再试。"), "error");
    }
  });
  actionBar.appendChild(createButton);
  if (work) {
    [
      ["生成第一章", "first", chapters.length ? "ghost-action" : "ghost-action"],
      ["生成下一章", "next", "primary-action"],
      ["生成当前弧线", "arc", "ghost-action"],
    ].forEach(([label, mode, className]) => {
      const button = document.createElement("button");
      button.className = className;
      button.textContent = label;
      button.addEventListener("click", async () => {
        try {
          await generateAuthorWork(mode);
        } catch (error) {
          authorNotice(formatAuthorApiErrorMessage(error, "生成章节失败，请稍后再试。"), "error");
        }
      });
      actionBar.appendChild(button);
    });
    const diagnosticsButton = document.createElement("button");
    diagnosticsButton.className = "ghost-action";
    diagnosticsButton.textContent = "运行作品诊断";
    diagnosticsButton.addEventListener("click", async () => {
      try {
        await runAuthorWorkDiagnostics();
      } catch (error) {
        authorNotice(formatAuthorApiErrorMessage(error, "运行作品诊断失败，请稍后再试。"), "error");
      }
    });
    actionBar.appendChild(diagnosticsButton);
    const submitButton = document.createElement("button");
    submitButton.className = work?.status === "review_ready" ? "primary-action" : "ghost-action";
    submitButton.textContent = "送审作品稿";
    submitButton.disabled = work?.status !== "review_ready";
    submitButton.title = work?.status === "review_ready" ? "" : "先把 block_rate 降到 0，再送审作品稿。";
    submitButton.addEventListener("click", async () => {
      try {
        await submitAuthorWorkForReview();
      } catch (error) {
        authorNotice(formatAuthorApiErrorMessage(error, "送审作品稿失败，请稍后再试。"), "error");
      }
    });
    actionBar.appendChild(submitButton);
  }
  hero.appendChild(actionBar);
  shell.appendChild(hero);

  if (authorState.authorWorkQualityGateFailure?.quality_gate) {
    const gateFailure = authorState.authorWorkQualityGateFailure;
    shell.appendChild(
      createListCard({
        title: "章节硬约束未通过",
        score: gateFailure.action_label || "未入库",
        body: formatAuthorQualityGateSummary(gateFailure.quality_gate),
        active: true,
      })
    );
  }

  if (!work) {
    const emptyState = document.createElement("article");
    emptyState.className = "author-editor-empty";
    emptyState.innerHTML = `
      <h4>先初始化作品稿，再开始逐章创作。</h4>
      <p>当前 draft 的世界设定、角色卡和长篇规划都会作为创作配置层保留在下方；正文会在这里成为主工作对象。</p>
    `;
    if (currentDraftAuthorAccountId()) {
      const loginHint = document.createElement("p");
      loginHint.textContent = `这份 Draft 属于作者账号 ${currentDraftAuthorAccountId()}。若初始化失败，请先在“账户协作”里登录这个账号。`;
      emptyState.appendChild(loginHint);
    }
    shell.appendChild(emptyState);
    dom.authorDraftSectionSummary.appendChild(shell);
    return;
  }

  const grid = document.createElement("div");
  grid.className = "author-editor-grid";

  const rail = document.createElement("aside");
  rail.className = "author-editor-panel author-editor-rail";
  const railHead = document.createElement("div");
  railHead.className = "author-editor-panel-head";
  railHead.innerHTML = `
    <div>
      <p class="author-editor-kicker">章节导航</p>
      <h4>作品元信息与章节列表</h4>
    </div>
  `;
  rail.appendChild(railHead);
  const railMeta = document.createElement("div");
  railMeta.className = "author-editor-meta-list";
  [
    ["世界版本", work.world_version_id || "-"],
    ["创作配置层", draftSection.label],
    ["最新修订", work.latest_revision?.revision_type || "-"],
    ["最近更新", formatTimestamp(work.updated_at)],
  ].forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "author-editor-meta-row";
    row.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    railMeta.appendChild(row);
  });
  rail.appendChild(railMeta);
  const chapterList = document.createElement("div");
  chapterList.className = "author-chapter-rail";
  chapters.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `author-chapter-row${Number(item.chapter_index) === Number(authorState.activeWorkChapterIndex) ? " is-active" : ""}`;
    button.addEventListener("click", async () => {
      try {
        await loadAuthorWorkChapter(item.chapter_index);
      } catch (error) {
        authorNotice(formatAuthorApiErrorMessage(error, "加载章节失败，请稍后再试。"), "error");
      }
    });
    const titleBlock = document.createElement("div");
    titleBlock.className = "author-chapter-row-copy";
    const eyebrow = document.createElement("span");
    eyebrow.className = "author-chapter-row-index";
    eyebrow.textContent = `第 ${item.chapter_index} 章`;
    const title = document.createElement("strong");
    title.textContent = item.chapter_title || `第 ${item.chapter_index} 章`;
    const meta = document.createElement("span");
    meta.className = "author-chapter-row-meta";
    meta.textContent = `${item.status || "-"} · ${item.source_type || "-"}`;
    titleBlock.append(eyebrow, title, meta);
    button.appendChild(titleBlock);
    chapterList.appendChild(button);
  });
  if (!chapters.length) {
    const empty = document.createElement("p");
    empty.className = "author-editor-empty-copy";
    empty.textContent = "还没有正文章节。先生成第一章。";
    chapterList.appendChild(empty);
  }
  rail.appendChild(chapterList);
  grid.appendChild(rail);

  const editor = document.createElement("section");
  editor.className = "author-editor-panel author-editor-main";
  const editorHead = document.createElement("div");
  editorHead.className = "author-editor-panel-head";
  editorHead.innerHTML = `
    <div>
      <p class="author-editor-kicker">章节正文</p>
      <h4 id="author-work-editor-current-chapter">${chapterDetail ? `第 ${chapterDetail.chapter_index} 章` : "未选择章节"}</h4>
    </div>
  `;
  const headerMeta = document.createElement("div");
  headerMeta.className = "author-editor-inline-meta";
  const statusPill = document.createElement("span");
  statusPill.className = "author-editor-pill";
  statusPill.textContent = chapterDetail?.status || "未生成";
  const dirtyPill = document.createElement("span");
  dirtyPill.id = "author-work-dirty-pill";
  dirtyPill.className = "author-editor-pill";
  headerMeta.append(statusPill, dirtyPill);
  editorHead.appendChild(headerMeta);
  editor.appendChild(editorHead);

  const statusLine = document.createElement("p");
  statusLine.id = "author-work-editor-state";
  statusLine.className = "author-editor-state";
  editor.appendChild(statusLine);

  if (!chapterDetail) {
    const empty = document.createElement("div");
    empty.className = "author-editor-empty";
    empty.innerHTML = `
      <h4>还没有可编辑的章节。</h4>
      <p>先生成第一章或下一章，作品正文会在这里展开。</p>
    `;
    editor.appendChild(empty);
  } else {
    const form = document.createElement("div");
    form.className = "author-editor-form";

    const titleLabel = document.createElement("label");
    titleLabel.className = "input-label";
    titleLabel.htmlFor = "author-work-chapter-title";
    titleLabel.textContent = "章节标题";
    const titleInput = document.createElement("input");
    titleInput.id = "author-work-chapter-title";
    titleInput.className = "field-input";
    titleInput.type = "text";
    titleInput.value = currentDraft?.chapter_title || "";
    titleInput.placeholder = "例如：第 3 章 · 风把门缝吹开";
    titleInput.addEventListener("input", (event) => {
      updateAuthorWorkDraftField("chapter_title", event.target.value);
    });

    const summaryLabel = document.createElement("label");
    summaryLabel.className = "input-label";
    summaryLabel.htmlFor = "author-work-chapter-summary";
    summaryLabel.textContent = "章节摘要";
    const summaryInput = document.createElement("textarea");
    summaryInput.id = "author-work-chapter-summary";
    summaryInput.rows = 4;
    summaryInput.placeholder = "记录这一章的摘要、修订意图或你想保留的关键线索。";
    summaryInput.value = currentDraft?.summary || "";
    summaryInput.addEventListener("input", (event) => {
      updateAuthorWorkDraftField("summary", event.target.value);
    });

    const bodyLabel = document.createElement("label");
    bodyLabel.className = "input-label";
    bodyLabel.htmlFor = "author-work-chapter-body";
    bodyLabel.textContent = "正文";
    const bodyInput = document.createElement("textarea");
    bodyInput.id = "author-work-chapter-body";
    bodyInput.className = "author-work-body-input";
    bodyInput.rows = 22;
    bodyInput.placeholder = "这里是作者真正逐章打磨的正文。";
    bodyInput.value = currentDraft?.body || "";
    bodyInput.addEventListener("input", (event) => {
      updateAuthorWorkDraftField("body", event.target.value);
    });

    const editorActions = document.createElement("div");
    editorActions.className = "author-editor-main-actions";
    const saveButton = document.createElement("button");
    saveButton.id = "author-save-work-chapter";
    saveButton.className = "primary-action";
    saveButton.textContent = "保存当前章节";
    saveButton.addEventListener("click", async () => {
      try {
        await saveAuthorWorkChapter();
      } catch (error) {
        authorState.activeWorkSaveState = "idle";
        refreshAuthorWorkEditorChrome();
        authorNotice(formatAuthorApiErrorMessage(error, "保存章节失败，请稍后再试。"), "error");
      }
    });
    editorActions.appendChild(saveButton);
    form.append(titleLabel, titleInput, summaryLabel, summaryInput, bodyLabel, bodyInput, editorActions);
    editor.appendChild(form);
  }
  grid.appendChild(editor);

  const sidecar = document.createElement("aside");
  sidecar.className = "author-editor-panel author-editor-sidecar";
  const sidecarHead = document.createElement("div");
  sidecarHead.className = "author-editor-panel-head";
  sidecarHead.innerHTML = `
    <div>
      <p class="author-editor-kicker">章节辅助</p>
      <h4>诊断、任务与连续性</h4>
    </div>
  `;
  sidecar.appendChild(sidecarHead);
  const sidecarSections = [
    {
      title: "当前章任务",
      body: Object.keys(chapterTask).length
        ? [
            chapterTask.task_id ? `任务 ${chapterTask.task_id}` : "",
            chapterTask.duty ? `职责 ${chapterTask.duty}` : "",
            chapterTask.objective ? `目标 ${chapterTask.objective}` : "",
            chapterTask.promise_actions?.length ? `promises ${chapterTask.promise_actions.join(" / ")}` : "",
          ].filter(Boolean).join("\n")
        : "当前章节还没有任务上下文，生成章节后会在这里显示 chapter task。",
    },
    {
      title: "当前章诊断",
      body: chapterDiagnostics.issue_count || chapterDiagnostics.decision
        ? `decision ${chapterDiagnostics.decision || "-"}\nissues ${chapterDiagnostics.issue_count || 0}\nissue codes ${(chapterDiagnostics.issue_codes || []).join(" / ") || "-"}\nnext ${chapterDiagnostics.recommended_action || "-"}`
        : "当前章节还没有诊断摘要。运行作品诊断后，这里会显示章节级判断。",
    },
    {
      title: "作品级诊断",
      body:
        `latest ${diagnostics.latest_decision || "-"}\n` +
        `pass ${formatPercent(evaluationSummary.pass_rate)}\n` +
        `rewrite ${formatPercent(evaluationSummary.rewrite_rate)}\n` +
        `block ${formatPercent(evaluationSummary.block_rate)}\n` +
        `next ${(diagnostics.next_actions || []).join(" / ") || "-"}`,
    },
  ];
  sidecarSections.forEach((section) => {
    const card = document.createElement("section");
    card.className = "author-editor-sidecard";
    const title = document.createElement("h5");
    title.textContent = section.title;
    const body = document.createElement("p");
    body.textContent = section.body;
    card.append(title, body);
    sidecar.appendChild(card);
  });

  const choiceCard = document.createElement("section");
  choiceCard.className = "author-editor-sidecard";
  const choiceTitle = document.createElement("h5");
  choiceTitle.textContent = "Choices 参考";
  choiceCard.appendChild(choiceTitle);
  if (chapterChoices.length) {
    const choiceList = document.createElement("div");
    choiceList.className = "author-choice-list";
    chapterChoices.forEach((choice, index) => {
      const item = document.createElement("div");
      item.className = "author-choice-item";
      const label = document.createElement("strong");
      label.textContent = `选项 ${index + 1}`;
      const copy = document.createElement("p");
      copy.textContent = normalizeAuthorChoiceText(choice) || JSON.stringify(choice);
      const actions = document.createElement("div");
      actions.className = "composer-actions author-card-actions";
      const prefillButton = document.createElement("button");
      prefillButton.className = "ghost-action";
      prefillButton.textContent = "用这个选项预填引导";
      prefillButton.addEventListener("click", () => {
        prefillAuthorSteeringFromChoice(choice, chapterDetail);
      });
      actions.appendChild(prefillButton);
      item.append(label, copy, actions);
      choiceList.appendChild(item);
    });
    choiceCard.appendChild(choiceList);
  } else {
    const empty = document.createElement("p");
    empty.textContent = "当前章节还没有 choices 参考。先生成章节或运行诊断，再把其中一个选项转成 steering。";
    choiceCard.appendChild(empty);
  }
  sidecar.appendChild(choiceCard);

  const relationshipCard = document.createElement("section");
  relationshipCard.className = "author-editor-sidecard";
  const relationshipTitle = document.createElement("h5");
  relationshipTitle.textContent = "关系快照";
  relationshipCard.appendChild(relationshipTitle);
  const relationshipBody = document.createElement("p");
  relationshipBody.textContent = relationshipHotspots.length
    ? relationshipHotspots
        .slice(0, 3)
        .map(
          (edge) =>
            `${edge.source_label} -> ${edge.target_label}\n${edge.dominant_metric_label} ${Number(edge.dominant_metric_value || 0).toFixed(2)} · debt ${edge.debt_count}`
        )
        .join("\n\n")
    : "先跑一次 simulation，这里会显示当前最紧绷的三条关系和债务方向。";
  relationshipCard.appendChild(relationshipBody);
  const relationshipActions = document.createElement("div");
  relationshipActions.className = "composer-actions author-card-actions";
  const cockpitButton = document.createElement("button");
  cockpitButton.className = "ghost-action";
  cockpitButton.textContent = "打开创作驾驶舱";
  cockpitButton.addEventListener("click", focusAuthorCreativeCockpit);
  relationshipActions.appendChild(cockpitButton);
  relationshipCard.appendChild(relationshipActions);
  sidecar.appendChild(relationshipCard);
  grid.appendChild(sidecar);

  shell.appendChild(grid);
  const readingPreviewPanel = document.createElement("section");
  readingPreviewPanel.className = "author-editor-panel author-reading-preview-panel";
  const readingPreviewHead = document.createElement("div");
  readingPreviewHead.className = "author-editor-panel-head";
  readingPreviewHead.innerHTML = `
    <div>
      <p class="author-editor-kicker">作品阅读预览</p>
      <h4>用阅读视角查看当前作品稿</h4>
    </div>
  `;
  readingPreviewPanel.appendChild(readingPreviewHead);
  const readingPreviewCopy = document.createElement("p");
  readingPreviewCopy.className = "panel-copy author-reading-preview-copy";
  readingPreviewCopy.textContent = work && chapterDetail
    ? "这里会把当前选中章节按阅读卡片方式展开。左侧切章，右侧编辑；阅读预览只看标题和正文，不把章节摘要混进正文流。"
    : "初始化作品稿并至少生成一章后，这里会以阅读卡片方式展示正文。";
  readingPreviewPanel.appendChild(readingPreviewCopy);
  if (work && chapterDetail) {
    const readingFeed = document.createElement("div");
    readingFeed.className = "story-feed author-reading-preview-feed";
    const card = document.createElement("article");
    card.className = "story-feed-card is-active";
    const header = document.createElement("div");
    header.className = "story-feed-head";
    const heading = document.createElement("h3");
    heading.textContent = chapterDetail.chapter_title || `第 ${chapterDetail.chapter_index} 章`;
    const meta = document.createElement("p");
    meta.className = "author-reading-preview-meta";
    meta.textContent = `第 ${chapterDetail.chapter_index} 章 · ${chapterDetail.source_type || "generated"} · ${(chapterDiagnostics.issue_codes || []).join(" / ") || "暂无显式问题"}`;
    header.append(heading, meta);
    card.appendChild(header);
    const body = document.createElement("div");
    body.className = "story-feed-body";
    body.textContent = chapterDetail.body || "这一章还没有正文。";
    card.appendChild(body);
    const hintItems = [];
    if ((chapterDetail.chapter_task || chapterTask).duty_type) {
      hintItems.push(`任务 ${(chapterDetail.chapter_task || chapterTask).duty_type}`);
    }
    (chapterDetail.choices || chapterChoices || []).slice(0, 2).forEach((choice, index) => {
      hintItems.push(`选项${index + 1} ${normalizeAuthorChoiceText(choice)}`.trim());
    });
    if (hintItems.length) {
      const hints = document.createElement("div");
      hints.className = "story-feed-hints";
      hintItems.forEach((item) => {
        const pill = document.createElement("span");
        pill.textContent = item;
        hints.appendChild(pill);
      });
      card.appendChild(hints);
    }
    const actions = document.createElement("div");
    actions.className = "composer-actions author-card-actions";
    const editButton = document.createElement("button");
    editButton.className = "ghost-action";
    editButton.textContent = "回到正文编辑";
    editButton.addEventListener("click", () => {
      document.querySelector("#author-work-editor-current-chapter")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    actions.appendChild(editButton);
    card.appendChild(actions);
    readingFeed.appendChild(card);
    readingPreviewPanel.appendChild(readingFeed);
  } else {
    const empty = document.createElement("div");
    empty.className = "author-editor-empty";
    empty.innerHTML = `
      <h4>还没有可阅读的章节。</h4>
      <p>先初始化作品稿并生成至少一章，阅读预览会在这里按连续章节的方式展开。</p>
    `;
    readingPreviewPanel.appendChild(empty);
  }
  shell.appendChild(readingPreviewPanel);
  dom.authorDraftSectionSummary.appendChild(shell);
  refreshAuthorWorkEditorChrome();
}

function renderCharacterEditor() {
  const characters = getActiveDraftCharacters();
  if (!dom.authorCharacterSelect) return;
  if (!characters.length) {
    dom.authorCharacterSelect.innerHTML = "";
    dom.authorCharacterName.value = "";
    dom.authorCharacterRole.value = "";
    dom.authorCharacterLifeTheme.value = "";
    dom.authorCharacterCoreWound.value = "";
    dom.authorCharacterPublicSelf.value = "";
    dom.authorCharacterShadowDesire.value = "";
    dom.authorCharacterVows.value = "";
    if (dom.authorCharacterSummary) {
      clearNode(dom.authorCharacterSummary, "选择角色后，这里会先显示当前角色摘要。");
    }
    return;
  }
  dom.authorCharacterSelect.innerHTML = characters
    .map((character, index) => `<option value="${index}">${character.display_name || character.character_id}</option>`)
    .join("");
  const character = characters[Math.min(selectedCharacterIndex(), characters.length - 1)];
  dom.authorCharacterSelect.value = String(Math.min(selectedCharacterIndex(), characters.length - 1));
  dom.authorCharacterName.value = character.display_name || "";
  dom.authorCharacterRole.value = character.role || "";
  dom.authorCharacterLifeTheme.value = character.destiny_contract?.life_theme || "";
  dom.authorCharacterCoreWound.value = character.wound_profile?.core_wound || "";
  dom.authorCharacterPublicSelf.value = character.wound_profile?.public_self || "";
  dom.authorCharacterShadowDesire.value = character.wound_profile?.shadow_desire || "";
  dom.authorCharacterVows.value = (character.vow_profile?.vows || []).join("\n");
  if (dom.authorCharacterSummary) {
    const cards = [];
    const repairLoopCard = createRepairLoopSummaryCard("character_card");
    if (repairLoopCard) {
      cards.push(repairLoopCard);
    }
    cards.push(createAuthorSummaryCard({
        title: character.display_name || character.character_id || "当前角色",
        score: character.role || "-",
        body:
          `命题 ${character.destiny_contract?.life_theme || "-"}\n` +
          `创伤 ${character.wound_profile?.core_wound || "-"}\n` +
          `表面自我 ${character.wound_profile?.public_self || "-"}\n` +
          `誓约 ${(character.vow_profile?.vows || []).slice(0, 2).join(" / ") || "-"}`,
      }));
    appendAuthorCardGrid(dom.authorCharacterSummary, cards);
  }
}

function renderSceneEditor() {
  const scenes = getActiveDraftScenes();
  if (!dom.authorSceneSelect) return;
  if (!scenes.length) {
    dom.authorSceneSelect.innerHTML = "";
    dom.authorSceneId.value = "";
    dom.authorSceneFunction.value = "";
    dom.authorSceneRequiredRoles.value = "";
    dom.authorSceneBeats.value = "";
    if (dom.authorSceneSummary) {
      clearNode(dom.authorSceneSummary, "选择场景后，这里会先显示当前场景摘要。");
    }
    return;
  }
  dom.authorSceneSelect.innerHTML = scenes
    .map((scene, index) => `<option value="${index}">${scene.scene_id || `scene_${index + 1}`}</option>`)
    .join("");
  const scene = scenes[Math.min(selectedSceneIndex(), scenes.length - 1)];
  dom.authorSceneSelect.value = String(Math.min(selectedSceneIndex(), scenes.length - 1));
  dom.authorSceneId.value = scene.scene_id || "";
  dom.authorSceneFunction.value = scene.scene_function || "";
  dom.authorSceneRequiredRoles.value = (scene.required_roles || []).join("\n");
  dom.authorSceneBeats.value = (scene.beats_template || []).join("\n");
  if (dom.authorSceneSummary) {
    const cards = [];
    const repairLoopCard = createRepairLoopSummaryCard("scene_blueprint");
    if (repairLoopCard) {
      cards.push(repairLoopCard);
    }
    cards.push(createAuthorSummaryCard({
        title: scene.scene_id || `scene_${Math.min(selectedSceneIndex(), scenes.length - 1) + 1}`,
        score: scene.scene_function || "-",
        body:
          `必要角色 ${(scene.required_roles || []).join(" / ") || "-"}\n` +
          `beats ${(scene.beats_template || []).slice(0, 3).join(" / ") || "-"}\n` +
          `下一步 改完场景蓝图后去 Review 看 diff。`,
      }));
    appendAuthorCardGrid(dom.authorSceneSummary, cards);
  }
}

function renderLongformWorkbench() {
  if (!dom.authorLongformStatus) return;
  const worldpack = getActiveDraftWorldpack();
  const detail = authorState.activeDraftDetail || {};
  const seriesPlan = getActiveSeriesPlan();
  const volumePlans = getActiveVolumePlans();
  const arcPlans = getActiveArcPlans();
  if (!worldpack || !authorState.activeDraftVersionId) {
    clearNode(dom.authorLongformStatus, "选择一个草稿后，这里会显示当前长篇规划。");
    if (dom.authorLongformSummary) {
      clearNode(dom.authorLongformSummary, "这里会先显示当前规划对象、计划来源和建议下一步。");
    }
    if (dom.authorArcBoard) clearNode(dom.authorArcBoard, "这里会显示按分卷组织的弧线看板。");
    if (dom.authorTaskBoard) clearNode(dom.authorTaskBoard, "这里会显示当前弧线下可拖拽排序的章节任务。");
    if (dom.authorVolumeSelect) dom.authorVolumeSelect.innerHTML = "";
    if (dom.authorArcSelect) dom.authorArcSelect.innerHTML = "";
    if (dom.authorTaskSelect) dom.authorTaskSelect.innerHTML = "";
    if (dom.authorTaskId) dom.authorTaskId.value = "";
    if (dom.authorTaskDuty) dom.authorTaskDuty.value = "advance_plot";
    if (dom.authorTaskObjective) dom.authorTaskObjective.value = "";
    if (dom.authorTaskTargetWords) dom.authorTaskTargetWords.value = "";
    if (dom.authorTaskRevealBudget) dom.authorTaskRevealBudget.value = "";
    if (dom.authorTaskPromiseActions) dom.authorTaskPromiseActions.value = "";
    if (dom.authorTaskPromiseTargets) dom.authorTaskPromiseTargets.value = "";
    if (dom.authorTaskAllowTerminal) dom.authorTaskAllowTerminal.checked = false;
    if (dom.authorTaskBulkState) dom.authorTaskBulkState.value = "";
    if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
    if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
    if (dom.authorArcTaskPreview) dom.authorArcTaskPreview.value = "";
    return;
  }
  const snapshot = detail.simulation_report?.longform_plan_snapshot || {};
  const planSource = snapshot.plan_source || (seriesPlan ? "worldpack" : "missing");
  if (!seriesPlan || !volumePlans.length || !arcPlans.length) {
    if (dom.authorLongformSummary) {
      appendAuthorCardGrid(dom.authorLongformSummary, [
        createAuthorSummaryCard({
          title: "长篇规划尚未建立",
          score: planSource,
          body:
            `当前草稿 ${worldpack.title || authorState.activeDraftVersionId}\n` +
            `计划来源 ${planSource}\n` +
            `下一步 先生成长篇规划，再进入分卷、弧线和章节任务编辑。`,
          actionLabel: "生成长篇规划",
          onAction: () => {
            if (dom.authorBootstrapLongform) dom.authorBootstrapLongform.click();
          },
          primary: true,
        }),
      ]);
    }
    clearNode(
      dom.authorLongformStatus,
      `当前草稿还没有建立长篇规划。\n计划来源：${planSource}\n点击“生成长篇规划”后即可进入系列、分卷与弧线编辑。`
    );
    if (dom.authorSeriesTitle) dom.authorSeriesTitle.value = worldpack.title || "";
    if (dom.authorSeriesTheme) dom.authorSeriesTheme.value = worldpack.metadata?.author_brief?.life_theme || "";
    if (dom.authorSeriesTotalVolumes) dom.authorSeriesTotalVolumes.value = "";
    if (dom.authorSeriesTotalChapters) dom.authorSeriesTotalChapters.value = "";
    if (dom.authorSeriesTargetWords) dom.authorSeriesTargetWords.value = "";
    if (dom.authorStorylineContract) dom.authorStorylineContract.value = "";
    if (dom.authorCharacterMemoryProfiles) dom.authorCharacterMemoryProfiles.value = "";
    if (dom.authorSteeringGuardrails) dom.authorSteeringGuardrails.value = "";
    if (dom.authorArcBoard) clearNode(dom.authorArcBoard, "当前草稿还没有建立长篇规划。");
    if (dom.authorTaskBoard) clearNode(dom.authorTaskBoard, "当前草稿还没有建立长篇规划。");
    if (dom.authorVolumeSelect) dom.authorVolumeSelect.innerHTML = "";
    if (dom.authorVolumeTitle) dom.authorVolumeTitle.value = "";
    if (dom.authorVolumeGoal) dom.authorVolumeGoal.value = "";
    if (dom.authorVolumeTargetChapters) dom.authorVolumeTargetChapters.value = "";
    if (dom.authorVolumeClimax) dom.authorVolumeClimax.value = "";
    if (dom.authorVolumeEndState) dom.authorVolumeEndState.value = "";
    if (dom.authorArcSelect) dom.authorArcSelect.innerHTML = "";
    if (dom.authorTaskSelect) dom.authorTaskSelect.innerHTML = "";
    if (dom.authorTaskId) dom.authorTaskId.value = "";
    if (dom.authorTaskDuty) dom.authorTaskDuty.value = "advance_plot";
    if (dom.authorTaskObjective) dom.authorTaskObjective.value = "";
    if (dom.authorTaskTargetWords) dom.authorTaskTargetWords.value = "";
    if (dom.authorTaskRevealBudget) dom.authorTaskRevealBudget.value = "";
    if (dom.authorTaskPromiseActions) dom.authorTaskPromiseActions.value = "";
    if (dom.authorTaskPromiseTargets) dom.authorTaskPromiseTargets.value = "";
    if (dom.authorTaskAllowTerminal) dom.authorTaskAllowTerminal.checked = false;
    if (dom.authorTaskBulkState) dom.authorTaskBulkState.value = "";
    if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
    if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
    if (dom.authorArcTitle) dom.authorArcTitle.value = "";
    if (dom.authorArcGoal) dom.authorArcGoal.value = "";
    if (dom.authorArcConflict) dom.authorArcConflict.value = "";
    if (dom.authorArcTargetChapters) dom.authorArcTargetChapters.value = "";
    if (dom.authorArcRevealBudget) dom.authorArcRevealBudget.value = "";
    if (dom.authorArcPayoffTargets) dom.authorArcPayoffTargets.value = "";
    if (dom.authorArcCompletionConditions) dom.authorArcCompletionConditions.value = "";
    if (dom.authorArcTaskPreview) dom.authorArcTaskPreview.value = "";
    return;
  }

  if (dom.authorLongformSummary) {
    const selectedVolume =
      volumePlans.find((item) => item.volume_id === authorState.selectedAuthorVolumeId) ||
      volumePlans[0] ||
      null;
    const selectedArc =
      arcPlans.find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
      arcPlans[0] ||
      null;
    const selectedTask =
      (selectedArc?.chapter_tasks || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
      selectedArc?.chapter_tasks?.[0] ||
      null;
    const cards = [];
    const repairLoopCard = createRepairLoopSummaryCard("chapter_task");
    if (repairLoopCard) {
      cards.push(repairLoopCard);
    }
    cards.push(createAuthorSummaryCard({
        title: seriesPlan.title || worldpack.title || "当前系列",
        score: `${volumePlans.length} 卷 / ${arcPlans.length} 弧线`,
        body:
          `主题 ${seriesPlan.theme_statement || worldpack.metadata?.author_brief?.life_theme || "-"}\n` +
          `分卷 ${selectedVolume?.title || "-"}\n` +
          `弧线 ${selectedArc?.title || "-"}\n` +
          `下一步 先确认当前分卷和弧线，再细化章节任务。`,
      }));
    cards.push(createAuthorSummaryCard({
        title: "当前章节任务",
        score: selectedTask?.duty_type || "待选择",
        body:
          `任务 ${selectedTask?.chapter_task_id || "-"}\n` +
          `目标 ${selectedTask?.objective || "-"}\n` +
          `关联承诺 ${(selectedTask?.promise_targets || []).join(" / ") || "-"}\n` +
          `下一步 把当前章节任务连回承诺映射与修稿桥。`,
      }));
    appendAuthorCardGrid(dom.authorLongformSummary, cards);
  }

  clearNode(dom.authorLongformStatus);
  const statusCard = createListCard({
    title: "长篇规划状态",
    score: planSource,
    body:
      `系列 ${seriesPlan.series_id || "-"} · 标题 ${seriesPlan.title || "-"}\n` +
      `分卷 ${volumePlans.length}/${seriesPlan.total_volume_target || "-"} · 弧线 ${arcPlans.length}\n` +
      `章节 ${seriesPlan.total_chapter_target || "-"} · 字数 ${seriesPlan.target_word_count || "-"}\n` +
      `当前阶段 ${worldpack.metadata?.longform_program_stage || "-"}`
  });
  dom.authorLongformStatus.appendChild(statusCard);

  if (!authorState.selectedAuthorVolumeId || !volumePlans.some((item) => item.volume_id === authorState.selectedAuthorVolumeId)) {
    authorState.selectedAuthorVolumeId = volumePlans[0]?.volume_id || null;
  }
  const selectedVolume = volumePlans.find((item) => item.volume_id === authorState.selectedAuthorVolumeId) || volumePlans[0];
  const arcsForVolume = arcPlans
    .filter((item) => item.volume_id === selectedVolume?.volume_id)
    .sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
  if (!authorState.selectedAuthorArcId || !arcsForVolume.some((item) => item.arc_id === authorState.selectedAuthorArcId)) {
    authorState.selectedAuthorArcId = arcsForVolume[0]?.arc_id || null;
  }
  const selectedArc = arcsForVolume.find((item) => item.arc_id === authorState.selectedAuthorArcId) || arcsForVolume[0];
  const selectedTasks = Array.isArray(selectedArc?.chapter_tasks) ? selectedArc.chapter_tasks : [];
  if (!authorState.selectedAuthorTaskId || !selectedTasks.some((item) => item.chapter_task_id === authorState.selectedAuthorTaskId)) {
    authorState.selectedAuthorTaskId = selectedTasks[0]?.chapter_task_id || null;
  }
  const selectedTask = selectedTasks.find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) || selectedTasks[0];

  if (dom.authorSeriesTitle) dom.authorSeriesTitle.value = seriesPlan.title || "";
  if (dom.authorSeriesTheme) dom.authorSeriesTheme.value = seriesPlan.theme_statement || "";
  if (dom.authorSeriesTotalVolumes) dom.authorSeriesTotalVolumes.value = String(Number(seriesPlan.total_volume_target || volumePlans.length || 1));
  if (dom.authorSeriesTotalChapters) dom.authorSeriesTotalChapters.value = String(Number(seriesPlan.total_chapter_target || 0));
  if (dom.authorSeriesTargetWords) dom.authorSeriesTargetWords.value = String(Number(seriesPlan.target_word_count || 0));
  if (dom.authorStorylineContract) {
    dom.authorStorylineContract.value = JSON.stringify(worldpack.series_storyline_contract || {}, null, 2);
  }
  if (dom.authorCharacterMemoryProfiles) {
    dom.authorCharacterMemoryProfiles.value = JSON.stringify(worldpack.character_memory_profiles || {}, null, 2);
  }
  if (dom.authorSteeringGuardrails) {
    dom.authorSteeringGuardrails.value = JSON.stringify(worldpack.steering_guardrails || {}, null, 2);
  }

  if (dom.authorVolumeSelect) {
    dom.authorVolumeSelect.innerHTML = volumePlans
      .map((volume) => `<option value="${volume.volume_id}">#${volume.order || "-"} · ${volume.title || volume.volume_id}</option>`)
      .join("");
    dom.authorVolumeSelect.value = selectedVolume?.volume_id || "";
  }
  if (selectedVolume) {
    if (dom.authorVolumeTitle) dom.authorVolumeTitle.value = selectedVolume.title || "";
    if (dom.authorVolumeGoal) dom.authorVolumeGoal.value = selectedVolume.goal || "";
    if (dom.authorVolumeTargetChapters) dom.authorVolumeTargetChapters.value = String(Number(selectedVolume.target_chapters || 1));
    if (dom.authorVolumeClimax) dom.authorVolumeClimax.value = selectedVolume.climax_definition || "";
    if (dom.authorVolumeEndState) dom.authorVolumeEndState.value = selectedVolume.end_state || "";
  }

  if (dom.authorArcSelect) {
    dom.authorArcSelect.innerHTML = arcsForVolume
      .map((arc) => `<option value="${arc.arc_id}">#${arc.order || "-"} · ${arc.title || arc.arc_id}</option>`)
      .join("");
    dom.authorArcSelect.value = selectedArc?.arc_id || "";
  }
  if (selectedArc) {
    if (dom.authorArcTitle) dom.authorArcTitle.value = selectedArc.title || "";
    if (dom.authorArcGoal) dom.authorArcGoal.value = selectedArc.goal || "";
    if (dom.authorArcConflict) dom.authorArcConflict.value = selectedArc.conflict || "";
    if (dom.authorArcTargetChapters) dom.authorArcTargetChapters.value = String(Number(selectedArc.target_chapters || 1));
    if (dom.authorArcRevealBudget) dom.authorArcRevealBudget.value = String(Number(selectedArc.reveal_budget || 0));
    if (dom.authorArcPayoffTargets) dom.authorArcPayoffTargets.value = (selectedArc.payoff_targets || []).join("\n");
    if (dom.authorArcCompletionConditions) dom.authorArcCompletionConditions.value = (selectedArc.completion_conditions || []).join("\n");
    if (dom.authorArcTaskPreview) {
      dom.authorArcTaskPreview.value = (selectedArc.chapter_tasks || [])
        .map((task, index) => `${index + 1}. ${task.duty_type || "-"} · ${task.objective || "-"} · words ${task.target_words || "-"}`)
        .join("\n");
    }
  } else if (dom.authorArcTaskPreview) {
    dom.authorArcTaskPreview.value = "";
  }
  if (dom.authorArcBoard) {
    clearNode(dom.authorArcBoard);
    const groupedByVolume = volumePlans.map((volume) => ({
      volume,
      arcs: arcPlans
        .filter((arc) => arc.volume_id === volume.volume_id)
        .sort((left, right) => Number(left.order || 0) - Number(right.order || 0)),
    }));
    groupedByVolume.forEach(({ volume, arcs }) => {
      const card = createListCard({
        title: `${volume.title || volume.volume_id}`,
        score: `${arcs.length} arcs · 可拖拽重排`,
        body:
          `目标章节 ${volume.target_chapters || "-"} · 当前卷目标 ${volume.goal || "-"}`
      });
      const list = document.createElement("div");
      list.className = "list-stack";
      arcs.forEach((arc) => {
        const arcCard = createListCard({
          title: `${arc.arc_id === selectedArc?.arc_id ? ">> " : ""}#${arc.order || "-"} ${arc.title || arc.arc_id}`,
          score: `${(arc.chapter_tasks || []).length} tasks`,
          body:
            `${arc.goal || "-"}\nchapters ${arc.target_chapters || "-"} · reveal ${arc.reveal_budget || "-"} · conflict ${arc.conflict || "-"}`
        });
        arcCard.draggable = true;
        arcCard.addEventListener("click", () => {
          authorState.selectedAuthorVolumeId = volume.volume_id;
          authorState.selectedAuthorArcId = arc.arc_id;
          authorState.selectedAuthorTaskId = arc.chapter_tasks?.[0]?.chapter_task_id || null;
          renderLongformWorkbench();
        });
        arcCard.addEventListener("dragstart", (event) => {
          authorState.draggingAuthorArcId = arc.arc_id;
          event.dataTransfer?.setData("text/plain", arc.arc_id);
          event.dataTransfer.effectAllowed = "move";
        });
        arcCard.addEventListener("dragover", (event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
        });
        arcCard.addEventListener("drop", (event) => {
          event.preventDefault();
          const draggedArcId = authorState.draggingAuthorArcId || event.dataTransfer?.getData("text/plain") || "";
          reorderArcWithinVolume(volume.volume_id, draggedArcId, arc.arc_id);
          authorState.draggingAuthorArcId = null;
        });
        arcCard.addEventListener("dragend", () => {
          authorState.draggingAuthorArcId = null;
        });
        list.appendChild(arcCard);
      });
      card.appendChild(list);
      dom.authorArcBoard.appendChild(card);
    });
  }
  if (dom.authorTaskSelect) {
    dom.authorTaskSelect.innerHTML = selectedTasks
      .map((task, index) => `<option value="${task.chapter_task_id}">#${index + 1} · ${task.duty_type || "-"} · ${task.chapter_task_id}</option>`)
      .join("");
    dom.authorTaskSelect.value = selectedTask?.chapter_task_id || "";
  }
  if (dom.authorTaskBoard) {
    clearNode(dom.authorTaskBoard);
    if (!arcsForVolume.length) {
      clearNode(dom.authorTaskBoard, "当前 arc 还没有 chapter tasks。");
    } else {
      arcsForVolume.forEach((arc) => {
        const arcTasks = Array.isArray(arc.chapter_tasks) ? arc.chapter_tasks : [];
        const arcCard = createListCard({
          title: `${arc.arc_id === selectedArc?.arc_id ? ">> " : ""}${arc.title || arc.arc_id}`,
          score: `${arcTasks.length} tasks`,
          body: `${arc.goal || "-"}\nchapters ${arc.target_chapters || "-"} · reveal ${arc.reveal_budget || "-"}`
        });
        const taskList = document.createElement("div");
        taskList.className = "list-stack";
        taskList.addEventListener("dragover", (event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
        });
        taskList.addEventListener("drop", (event) => {
          event.preventDefault();
          const draggedTaskId = authorState.draggingAuthorTaskId || event.dataTransfer?.getData("text/plain") || "";
          moveTaskAcrossArcs(authorState.selectedAuthorArcId || arc.arc_id, arc.arc_id, draggedTaskId);
          authorState.draggingAuthorTaskId = null;
        });
        arcTasks.forEach((task, index) => {
          const taskCard = createListCard({
            title: `${task.chapter_task_id === selectedTask?.chapter_task_id ? ">> " : ""}#${index + 1} ${task.duty_type || "-"}`,
            score: `${task.target_words || "-"} words`,
            body:
              `${task.objective || "-"}\nreveal ${task.reveal_budget || 0} · actions ${(task.promise_actions || []).join(" / ") || "-"}\ntargets ${(task.promise_targets || []).join(" / ") || "-"}${task.allow_terminal ? "\nterminal allowed" : ""}`
          });
          taskCard.draggable = true;
          taskCard.addEventListener("click", () => {
            authorState.selectedAuthorArcId = arc.arc_id;
            authorState.selectedAuthorTaskId = task.chapter_task_id;
            if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
            if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
            renderLongformWorkbench();
          });
          taskCard.addEventListener("dragstart", (event) => {
            authorState.draggingAuthorTaskId = task.chapter_task_id;
            authorState.selectedAuthorArcId = arc.arc_id;
            event.dataTransfer?.setData("text/plain", task.chapter_task_id);
            event.dataTransfer.effectAllowed = "move";
          });
          taskCard.addEventListener("dragover", (event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
          });
          taskCard.addEventListener("drop", (event) => {
            event.preventDefault();
            const draggedTaskId = authorState.draggingAuthorTaskId || event.dataTransfer?.getData("text/plain") || "";
            moveTaskAcrossArcs(authorState.selectedAuthorArcId || arc.arc_id, arc.arc_id, draggedTaskId, task.chapter_task_id);
            authorState.draggingAuthorTaskId = null;
          });
          taskCard.addEventListener("dragend", () => {
            authorState.draggingAuthorTaskId = null;
          });
          taskList.appendChild(taskCard);
        });
        arcCard.appendChild(taskList);
        dom.authorTaskBoard.appendChild(arcCard);
      });
    }
  }
  if (selectedTask) {
    if (dom.authorTaskId) dom.authorTaskId.value = selectedTask.chapter_task_id || "";
    if (dom.authorTaskDuty) dom.authorTaskDuty.value = selectedTask.duty_type || "advance_plot";
    if (dom.authorTaskObjective) dom.authorTaskObjective.value = selectedTask.objective || "";
    if (dom.authorTaskTargetWords) dom.authorTaskTargetWords.value = String(Number(selectedTask.target_words || 2000));
    if (dom.authorTaskRevealBudget) dom.authorTaskRevealBudget.value = String(Number(selectedTask.reveal_budget || 0));
    if (dom.authorTaskPromiseActions) dom.authorTaskPromiseActions.value = (selectedTask.promise_actions || []).join("\n");
    if (dom.authorTaskPromiseTargets) dom.authorTaskPromiseTargets.value = (selectedTask.promise_targets || []).join("\n");
    if (dom.authorTaskAllowTerminal) dom.authorTaskAllowTerminal.checked = Boolean(selectedTask.allow_terminal);
  } else {
    if (dom.authorTaskId) dom.authorTaskId.value = "";
    if (dom.authorTaskDuty) dom.authorTaskDuty.value = "advance_plot";
    if (dom.authorTaskObjective) dom.authorTaskObjective.value = "";
    if (dom.authorTaskTargetWords) dom.authorTaskTargetWords.value = "";
    if (dom.authorTaskRevealBudget) dom.authorTaskRevealBudget.value = "";
    if (dom.authorTaskPromiseActions) dom.authorTaskPromiseActions.value = "";
    if (dom.authorTaskPromiseTargets) dom.authorTaskPromiseTargets.value = "";
    if (dom.authorTaskAllowTerminal) dom.authorTaskAllowTerminal.checked = false;
  }
  renderSeriesVolumeArcPromiseMapping();
  renderChapterTaskSimulationLinking();
}

function renderPromiseLedgerWorkbench() {
  if (!dom.authorPromiseLedger) return;
  clearNode(dom.authorPromiseLedger);
  const ledger = getPromiseLedgerWorkbench();
  const promiseState = getPromiseStateWorkbench();
  if (!ledger.available) {
    clearNode(dom.authorPromiseLedger, "运行 simulation 后，这里会显示 open / overdue / closed promises。");
    if (dom.authorPromiseSelect) dom.authorPromiseSelect.innerHTML = "";
    if (dom.authorPromiseState) dom.authorPromiseState.value = "";
    if (dom.authorPromiseNotes) dom.authorPromiseNotes.value = "";
    return;
  }
  const editablePromises = Array.isArray(promiseState.editable_promises) ? promiseState.editable_promises : [];
  if (!authorState.selectedAuthorPromiseId || !editablePromises.some((item) => item.promise_id === authorState.selectedAuthorPromiseId)) {
    authorState.selectedAuthorPromiseId = editablePromises[0]?.promise_id || ledger.open_promises?.[0]?.promise_id || null;
  }
  const selectedPromise =
    editablePromises.find((item) => item.promise_id === authorState.selectedAuthorPromiseId) ||
    (ledger.open_promises || []).find((item) => item.promise_id === authorState.selectedAuthorPromiseId) ||
    editablePromises[0] ||
    (ledger.open_promises || [])[0];
  if (dom.authorPromiseSelect) {
    dom.authorPromiseSelect.innerHTML = editablePromises
      .map(
        (item) =>
          `<option value="${item.promise_id}">${item.promise_id} · ${item.editor_state || item.status || "open"} · ${item.description || item.promise_id}</option>`
      )
      .join("");
    dom.authorPromiseSelect.value = selectedPromise?.promise_id || "";
  }
  if (dom.authorPromiseState) {
    dom.authorPromiseState.innerHTML = [`<option value="">未标注</option>`, ...(promiseState.state_options || []).map((item) => `<option value="${item}">${item}</option>`)].join("");
    dom.authorPromiseState.value = selectedPromise?.editor_state || "";
  }
  if (dom.authorPromiseNotes) {
    dom.authorPromiseNotes.value = selectedPromise?.editor_notes || "";
  }
  dom.authorPromiseLedger.appendChild(
    createListCard({
      title: "Promise Ledger Summary",
      score: ledger.status || "-",
      body:
        `open ${ledger.open_count ?? 0} · overdue ${ledger.overdue_count ?? 0} · closed ${ledger.closed_count ?? 0}\n` +
        `editor overrides ${promiseState.override_count ?? 0}\n` +
        `next actions ${(ledger.next_actions || []).join(" / ") || "-"}`
    })
  );
  if (selectedPromise) {
    dom.authorPromiseLedger.appendChild(
      createListCard({
        title: "Selected Promise",
        score: selectedPromise.editor_state || selectedPromise.status || "-",
        body:
          `${selectedPromise.promise_id}\n${selectedPromise.description || "-"}\n` +
          `holders ${(selectedPromise.holders || []).join(" / ") || "-"} · stakes ${selectedPromise.stakes || "-"}\n` +
          `chapters ${selectedPromise.first_seen_chapter ?? "-"} -> ${selectedPromise.last_seen_chapter ?? "-"}${selectedPromise.is_overdue ? " · overdue" : ""}\n` +
          `notes ${selectedPromise.editor_notes || "-"}`
      })
    );
  }
  if ((ledger.open_promises || []).length) {
    dom.authorPromiseLedger.appendChild(
      createListCard({
        title: "Open Promises",
        score: `${ledger.open_promises.length} open`,
        body:
          `${(ledger.open_promises || []).map((item) => `${selectedAuthorChapterMarker(item.last_seen_chapter)}${item.promise_id}\n${item.description || "-"}\nholders ${(item.holders || []).join(" / ") || "-"} · stakes ${item.stakes || "-"} · due ${item.due_by_turn ?? "-"}${item.is_overdue ? " · overdue" : ""}\nchapters ${item.first_seen_chapter ?? "-"} -> ${item.last_seen_chapter ?? "-"}`).join("\n\n")}`
      })
    );
    const firstPromise = ledger.open_promises[0];
    if (firstPromise?.anchor?.anchor_key) {
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      const jumpButton = document.createElement("button");
      jumpButton.className = "ghost-action";
      jumpButton.textContent = "跳到首个 Promise 章节";
      jumpButton.addEventListener("click", () => {
        jumpToAuthorChapter(firstPromise.anchor.anchor_key, "simulation");
      });
      actions.appendChild(jumpButton);
      const button = document.createElement("button");
      button.className = "ghost-action";
      button.textContent = "评论首个 Promise";
      button.addEventListener("click", () => {
        prefillAuthorCommentAnchor(firstPromise.anchor.anchor_type || "simulation", String(firstPromise.anchor.anchor_key));
      });
      actions.appendChild(button);
      dom.authorPromiseLedger.appendChild(actions);
    }
  } else {
    dom.authorPromiseLedger.appendChild(
      createListCard({
        title: "Open Promises",
        score: "0",
        body: "当前 simulation 没有未结 promise。"
      })
    );
  }
  if ((ledger.recently_closed_ids || []).length) {
    dom.authorPromiseLedger.appendChild(
      createListCard({
        title: "Recently Closed",
        score: `${ledger.recently_closed_ids.length} ids`,
        body: (ledger.recently_closed_ids || []).join("\n")
      })
    );
  }
}

function renderSeriesVolumeArcPromiseMapping() {
  if (!dom.authorPromiseMapping) return;
  clearNode(dom.authorPromiseMapping);
  const mapping = getSeriesVolumeArcPromiseMapping();
  if (!mapping.available) {
    clearNode(dom.authorPromiseMapping, "运行 simulation 后，这里会显示 series / volume / arc 对 promises 的映射。");
    return;
  }
  const seriesSummary = mapping.series_summary || {};
  const volumes = Array.isArray(mapping.volumes) ? mapping.volumes : [];
  const arcs = Array.isArray(mapping.arcs) ? mapping.arcs : [];
  const selectedVolume = volumes.find((item) => item.volume_id === authorState.selectedAuthorVolumeId) || volumes[0];
  const selectedArc =
    arcs.find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    arcs.find((item) => item.volume_id === selectedVolume?.volume_id) ||
    arcs[0];

  dom.authorPromiseMapping.appendChild(
    createListCard({
      title: "Series Promise Map",
      score: `${seriesSummary.mapped_promises?.length || 0} promises`,
      body:
        `series ${seriesSummary.title || seriesSummary.series_id || "-"}\n` +
        `simulated chapters ${seriesSummary.simulated_chapter_count ?? 0}/${seriesSummary.target_chapters ?? "-"}\n` +
        `open ${seriesSummary.open_promise_ids?.length ?? 0} · closed ${seriesSummary.closed_promise_ids?.length ?? 0}\n` +
        `next actions ${(mapping.next_actions || []).join(" / ") || "-"}`
    })
  );

  if (selectedVolume) {
    dom.authorPromiseMapping.appendChild(
      createListCard({
        title: "Selected Volume Promise Map",
        score: `${selectedVolume.mapped_promises?.length || 0} promises`,
        body:
          `${selectedVolume.title || selectedVolume.volume_id}\n` +
          `chapters ${selectedVolume.first_simulation_chapter ?? "-"} -> ${selectedVolume.last_simulation_chapter ?? "-"} · simulated ${selectedVolume.simulated_chapter_count ?? 0}\n` +
          `open ${selectedVolume.open_promise_ids?.length ?? 0} · closed ${selectedVolume.closed_promise_ids?.length ?? 0}\n` +
          `arcs ${(selectedVolume.arc_ids || []).join(" / ") || "-"}`
      })
    );
  }

  if (selectedArc) {
    dom.authorPromiseMapping.appendChild(
      createListCard({
        title: "Selected Arc Promise Map",
        score: `${selectedArc.mapped_promises?.length || 0} promises`,
        body:
          `${selectedArc.title || selectedArc.arc_id}\n` +
          `goal ${selectedArc.goal || "-"}\n` +
          `chapters ${selectedArc.first_simulation_chapter ?? "-"} -> ${selectedArc.last_simulation_chapter ?? "-"} · simulated ${selectedArc.simulated_chapter_count ?? 0}\n` +
          `open ${selectedArc.open_promise_ids?.length ?? 0} · closed ${selectedArc.closed_promise_ids?.length ?? 0}`
      })
    );
    dom.authorPromiseMapping.appendChild(
      createListCard({
        title: "Arc Mapped Promises",
        score: `${selectedArc.mapped_promises?.length || 0} items`,
        body:
          `${(selectedArc.mapped_promises || [])
            .map(
              (item) =>
                `${item.promise_id}\n${item.description || "-"}\nstatus ${item.status || "-"} · editor ${item.editor_state || "-"} · holders ${(item.holders || []).join(" / ") || "-"} · chapters ${item.first_seen_chapter ?? "-"} -> ${item.last_seen_chapter ?? "-"}${item.is_overdue ? " · overdue" : ""}`
            )
            .join("\n\n") || "当前 arc 还没有映射到 promises。"}`
      })
    );
    const firstPromise = (selectedArc.mapped_promises || [])[0];
    if (firstPromise?.anchor?.anchor_key) {
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      const jumpPromise = document.createElement("button");
      jumpPromise.className = "ghost-action";
      jumpPromise.textContent = "跳到当前 Arc 的首个 Promise";
      jumpPromise.addEventListener("click", () => {
        jumpToAuthorChapter(firstPromise.anchor.anchor_key, "simulation");
      });
      actions.appendChild(jumpPromise);
      const commentPromise = document.createElement("button");
      commentPromise.className = "ghost-action";
      commentPromise.textContent = "评论当前 Arc 的首个 Promise";
      commentPromise.addEventListener("click", () => {
        prefillAuthorCommentAnchor(firstPromise.anchor.anchor_type || "simulation", String(firstPromise.anchor.anchor_key));
      });
      actions.appendChild(commentPromise);
      dom.authorPromiseMapping.appendChild(actions);
    }
  }
}

function renderChapterTaskSimulationLinking() {
  if (!dom.authorTaskSimulationLinking) return;
  clearNode(dom.authorTaskSimulationLinking);
  const linking = getChapterTaskSimulationLinking();
  if (!linking.available) {
    clearNode(dom.authorTaskSimulationLinking, "运行 simulation 后，这里会显示当前 chapter task 对应的章节链接和 promise 影响。");
    if (dom.authorTaskBulkState) dom.authorTaskBulkState.value = "";
    if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
    if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
    return;
  }
  const taskLinks = Array.isArray(linking.task_links) ? linking.task_links : [];
  const selectedLink =
    taskLinks.find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    taskLinks.find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    taskLinks[0];
  if (dom.authorTaskBulkState && !dom.authorTaskBulkState.value) {
    dom.authorTaskBulkState.value = "";
  }
  if (dom.authorTaskBulkIssues && !dom.authorTaskBulkIssues.value) {
    dom.authorTaskBulkIssues.value = (selectedLink?.compare_summary?.issue_codes_added || []).join("\n");
  }

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Task Linking Summary",
      score: `${linking.linked_task_count ?? 0} linked`,
      body:
        `linked ${linking.linked_task_count ?? 0} · planned only ${linking.planned_only_task_count ?? 0}\n` +
        `next actions ${(linking.next_actions || []).join(" / ") || "-"}`
    })
  );

  if (!selectedLink) {
    dom.authorTaskSimulationLinking.appendChild(
      createListCard({
        title: "Selected Task",
        score: "missing",
        body: "当前没有可用的 chapter task linking。"
      })
    );
    return;
  }

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Selected Task",
      score: selectedLink.status || "-",
      body:
        `${selectedLink.chapter_task_id}\n` +
        `${selectedLink.duty_type || "-"} · ${selectedLink.arc_title || selectedLink.arc_id || "-"}\n` +
        `objective ${selectedLink.objective || "-"}\n` +
        `simulated chapters ${selectedLink.simulated_chapter_count ?? 0} · compared ${selectedLink.compare_summary?.compared_chapter_count ?? 0} · promises ${(selectedLink.mapped_promises || []).length}\n` +
        `actions ${(selectedLink.promise_actions || []).join(" / ") || "-"}\n` +
        `targets ${(selectedLink.promise_targets || []).join(" / ") || "-"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Task Compare Diff",
      score: selectedLink.compare_available ? "available" : "missing",
      body:
        `compared chapters ${selectedLink.compare_summary?.compared_chapter_count ?? 0}\n` +
        `avg score delta ${Number(selectedLink.compare_summary?.average_score_delta || 0).toFixed(3)}\n` +
        `issues + ${(selectedLink.compare_summary?.issue_codes_added || []).join("/") || "-"} · - ${(selectedLink.compare_summary?.issue_codes_removed || []).join("/") || "-"}\n` +
        `strongest compare chapter ${selectedLink.compare_summary?.strongest_compare_chapter_index || "-"} · delta ${Number(selectedLink.compare_summary?.strongest_compare_delta || 0).toFixed(3)}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
        title: "Linked Simulation Chapters",
        score: `${selectedLink.linked_chapters?.length || 0} chapters`,
        body:
          `${(selectedLink.linked_chapters || [])
          .map(
            (item) =>
              `${selectedAuthorChapterMarker(item.chapter_index)}${item.chapter_index}. ${item.chapter_title || item.chapter_id || "-"}\n${item.scene_function || "-"} · decision ${item.decision || "-"} · score ${Number(item.overall_score || 0).toFixed(3)}\nissues ${(item.issue_codes || []).join("/") || "-"} · open ${(item.open_promise_ids || []).join("/") || "-"} · closed ${(item.closed_promise_ids || []).join("/") || "-"}`
          )
          .join("\n\n") || "当前 task 还没有链接到 simulation chapters。"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Mapped Promises",
      score: `${selectedLink.mapped_promises?.length || 0} promises`,
        body:
          `${(selectedLink.mapped_promises || [])
          .map(
            (item) =>
              `${item.promise_id}\n${item.description || "-"}\nstatus ${item.status || "-"} · editor ${item.editor_state || "-"} · holders ${(item.holders || []).join(" / ") || "-"} · chapters ${item.first_seen_chapter ?? "-"} -> ${item.last_seen_chapter ?? "-"}`
          )
          .join("\n\n") || "当前 task 还没有观测到 promise 映射。"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Planned Promise Targets",
      score: `${selectedLink.planned_promises?.length || 0} targets`,
      body:
        `${(selectedLink.planned_promises || [])
          .map(
            (item) =>
              `${item.promise_id}\n${item.description || "-"}\nstatus ${item.status || "-"} · editor ${item.editor_state || "-"} · chapters ${item.first_seen_chapter ?? "-"} -> ${item.last_seen_chapter ?? "-"}`
          )
          .join("\n\n") || "当前 task 还没有显式 promise targets。"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Planned vs Observed Promise Drift",
      score: selectedLink.promise_drift?.status || "-",
      body:
        `coverage ${Number(selectedLink.promise_drift?.coverage_ratio || 0).toFixed(3)}\n` +
        `planned ${selectedLink.promise_drift?.planned_target_count ?? 0} · observed ${selectedLink.promise_drift?.observed_target_count ?? 0} · matched ${selectedLink.promise_drift?.matched_target_count ?? 0}\n` +
        `planned only ${(selectedLink.promise_drift?.planned_only_ids || []).join(" / ") || "-"}\n` +
        `observed only ${(selectedLink.promise_drift?.observed_only_ids || []).join(" / ") || "-"}\n` +
        `recommended ${(selectedLink.promise_drift?.recommended_actions || []).join(" / ") || "-"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Drift Remediation Suggestions",
      score: `${selectedLink.remediation_suggestions?.length || 0} suggestions`,
      body:
        `${(selectedLink.remediation_suggestions || [])
          .map((item) => `${item.action}\n${item.summary || "-"}\n${item.details || "-"}`)
          .join("\n\n") || "当前 task 暂无额外 remediation suggestions。"}`
    })
  );

  dom.authorTaskSimulationLinking.appendChild(
    createListCard({
      title: "Task Compare Chapters",
      score: `${selectedLink.compare_chapters?.length || 0} chapters`,
      body:
        `${(selectedLink.compare_chapters || [])
          .map(
            (item) =>
              `${selectedAuthorCompareMarker(item.chapter_index)}${item.chapter_index}. ${item.before_title || "-"} -> ${item.after_title || "-"}\nscore delta ${Number(item.overall_score_delta || 0).toFixed(3)} · issues + ${(item.issue_codes_added || []).join("/") || "-"} · - ${(item.issue_codes_removed || []).join("/") || "-"}`
          )
          .join("\n\n") || "当前 task 还没有可用的 compare diff。"}`
    })
  );

  const actions = document.createElement("div");
  actions.className = "composer-actions";
  if (selectedLink.rewrite_workflow?.available) {
    const rewriteButton = document.createElement("button");
    rewriteButton.className = "ghost-action";
    rewriteButton.textContent = "Apply Compare to Rewrite";
    rewriteButton.addEventListener("click", applySelectedTaskRewritePrefill);
    actions.appendChild(rewriteButton);
  }
  const firstChapter = (selectedLink.linked_chapters || [])[0];
  const firstCompareChapter = (selectedLink.compare_chapters || [])[0];
  if (firstCompareChapter?.chapter_index) {
    const jumpCompare = document.createElement("button");
    jumpCompare.className = "ghost-action";
    jumpCompare.textContent = "跳到当前 Task 的章节对照";
    jumpCompare.addEventListener("click", () => {
      jumpToAuthorChapter(firstCompareChapter.chapter_index, "compare");
    });
    actions.appendChild(jumpCompare);
  }
  if (firstChapter?.anchor?.anchor_key) {
    const jumpChapter = document.createElement("button");
    jumpChapter.className = "ghost-action";
    jumpChapter.textContent = "跳到当前 Task 的首个章节";
    jumpChapter.addEventListener("click", () => {
      jumpToAuthorChapter(firstChapter.anchor.anchor_key, "simulation");
    });
    actions.appendChild(jumpChapter);
    const commentChapter = document.createElement("button");
    commentChapter.className = "ghost-action";
    commentChapter.textContent = "评论当前 Task 的首个章节";
    commentChapter.addEventListener("click", () => {
      prefillAuthorCommentAnchor(firstChapter.anchor.anchor_type || "simulation", String(firstChapter.anchor.anchor_key));
    });
    actions.appendChild(commentChapter);
  }
  const firstPromise = (selectedLink.mapped_promises || [])[0];
  if (firstPromise?.anchor?.anchor_key) {
    const commentPromise = document.createElement("button");
    commentPromise.className = "ghost-action";
    commentPromise.textContent = "评论当前 Task 的首个 Promise";
    commentPromise.addEventListener("click", () => {
      prefillAuthorCommentAnchor(firstPromise.anchor.anchor_type || "simulation", String(firstPromise.anchor.anchor_key));
    });
    actions.appendChild(commentPromise);
  }
  if (actions.childNodes.length) {
    dom.authorTaskSimulationLinking.appendChild(actions);
  }
}

function renderRewritePatchPreview() {
  if (!dom.authorRewritePatchPreview) return;
  clearNode(dom.authorRewritePatchPreview);
  const linking = getChapterTaskSimulationLinking();
  const selectedLink =
    (linking.task_links || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    (linking.task_links || []).find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    null;
  if (!selectedLink?.rewrite_workflow?.available) {
    authorState.authorCurrentRewritePatchExport = null;
    clearNode(dom.authorRewritePatchPreview, "当前 task 还没有可预览的 rewrite patch。");
    return;
  }
  const workflow = selectedLink.rewrite_workflow;
  const currentObjective = String(dom.authorTaskObjective?.value || "");
  const currentTargets = splitPromiseTargetList(dom.authorTaskPromiseTargets?.value || "");
  const currentBulkState = String(dom.authorTaskBulkState?.value || "");
  const currentIssueScope = splitPromiseTargetList(dom.authorTaskBulkIssues?.value || "");
  const currentBulkNotes = String(dom.authorTaskBulkNotes?.value || "");
  const currentPatch = {
    objective: currentObjective,
    promise_targets: currentTargets,
    bulk_override_state: currentBulkState,
    issue_scope: currentIssueScope,
    bulk_notes: currentBulkNotes,
  };
  const patchLines = [];
  if (currentObjective !== String(workflow.suggested_task_objective || "")) {
    patchLines.push(`objective\nFROM: ${currentObjective || "-"}\nTO: ${workflow.suggested_task_objective || "-"}`);
  }
  if (JSON.stringify(currentTargets) !== JSON.stringify(workflow.suggested_promise_targets || [])) {
    patchLines.push(`promise_targets\nFROM: ${currentTargets.join(" / ") || "-"}\nTO: ${(workflow.suggested_promise_targets || []).join(" / ") || "-"}`);
  }
  if (currentBulkState !== String(workflow.suggested_override_state || "")) {
    patchLines.push(`bulk_override_state\nFROM: ${currentBulkState || "-"}\nTO: ${workflow.suggested_override_state || "-"}`);
  }
  if (JSON.stringify(currentIssueScope) !== JSON.stringify(workflow.issue_scope || [])) {
    patchLines.push(`issue_scope\nFROM: ${currentIssueScope.join(" / ") || "-"}\nTO: ${(workflow.issue_scope || []).join(" / ") || "-"}`);
  }
  if (currentBulkNotes !== String(workflow.suggested_bulk_notes || "")) {
    patchLines.push(`bulk_notes\nFROM: ${currentBulkNotes || "-"}\nTO: ${workflow.suggested_bulk_notes || "-"}`);
  }
  dom.authorRewritePatchPreview.appendChild(
    createListCard({
      title: "Rewrite Patch Preview",
      score: patchLines.length ? `${patchLines.length} changes` : "in sync",
      body:
        `target chapter ${workflow.rewrite_target_chapter_index || "-"}\n` +
        `issue scope ${(workflow.issue_scope || []).join(" / ") || "-"}\n` +
        `next ${(workflow.next_actions || []).join(" / ") || "-"}\n\n` +
        `${patchLines.join("\n\n") || "当前表单值已经和 rewrite suggestion 对齐。"}`
    })
  );
  authorState.authorCurrentRewritePatchExport = {
    task_id: selectedLink.chapter_task_id,
    arc_id: selectedLink.arc_id,
    volume_id: selectedLink.volume_id,
    rewrite_target_chapter_index: workflow.rewrite_target_chapter_index || null,
    issue_scope: workflow.issue_scope || [],
    current_patch: currentPatch,
    suggested_patch: {
      objective: workflow.suggested_task_objective || "",
      promise_targets: workflow.suggested_promise_targets || [],
      bulk_override_state: workflow.suggested_override_state || "",
      issue_scope: workflow.issue_scope || [],
      bulk_notes: workflow.suggested_bulk_notes || "",
    },
    patch_lines: patchLines,
    next_actions: workflow.next_actions || [],
  };
}

function renderSimulationDiffCheckpoint() {
  if (!dom.authorSimulationDiffCheckpoint) return;
  clearNode(dom.authorSimulationDiffCheckpoint);
  const checkpoint = getSimulationDiffCheckpoint();
  if (!checkpoint.available) {
    clearNode(dom.authorSimulationDiffCheckpoint, "这里会显示最近一次 rewrite revision 是否已经产出 simulation diff checkpoint。");
    return;
  }
  dom.authorSimulationDiffCheckpoint.appendChild(
    createListCard({
      title: "Simulation Diff Checkpoint",
      score: checkpoint.status || "-",
      body:
        `latest revision ${checkpoint.latest_revision_id || "-"} · ${checkpoint.latest_revision_source || "-"}\n` +
        `summary ${checkpoint.latest_revision_summary || "-"}\n` +
        `last simulated ${checkpoint.last_simulated_revision_id || "-"} · freshness ${checkpoint.simulation_freshness?.status || "-"}\n` +
        `suggested action ${checkpoint.suggested_action || "-"} · auto suggest ${checkpoint.auto_resimulate_suggested ? "yes" : "no"}\n` +
        `compare available ${checkpoint.compare_available ? "yes" : "no"} · top changed ${checkpoint.top_changed_chapter_count ?? 0}\n` +
        `next ${(checkpoint.next_actions || []).join(" / ") || "-"}`
    })
  );
}

function exportRewritePatchPreview() {
  const payload = authorState.authorCurrentRewritePatchExport || null;
  if (!payload) {
    authorNotice("当前没有可导出的 rewrite patch。");
    return;
  }
  const suffix = payload.task_id ? String(payload.task_id).replace(/[^a-zA-Z0-9_.-]+/g, "_") : "rewrite_patch";
  downloadJsonFile(`rewrite_patch_${suffix}.json`, payload);
}

async function runCheckpointAwareResimulate() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const checkpoint = getSimulationDiffCheckpoint();
  if (!checkpoint.available) {
    authorNotice("当前没有可用的 simulation diff checkpoint。");
    return;
  }
  if (!checkpoint.auto_resimulate_suggested && checkpoint.suggested_action !== "simulate_draft") {
    authorNotice("当前 checkpoint 不建议自动重跑 simulation。");
    return;
  }
  try {
    await simulateDraftVersion(authorState.activeDraftVersionId);
  } catch (error) {
    authorNotice(formatAuthorApiErrorMessage(error, "Run Suggested Re-simulate 失败，请稍后再试。"), "error");
  }
}

function splitSelectedTaskPromiseTargets() {
  if (!dom.authorTaskPromiseTargets) return;
  const targets = splitPromiseTargetList(dom.authorTaskPromiseTargets.value || "");
  dom.authorTaskPromiseTargets.value = targets.join("\n");
}

function mergeObservedPromisesIntoTargets() {
  const linking = getChapterTaskSimulationLinking();
  const selectedLink =
    (linking.task_links || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    (linking.task_links || []).find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    null;
  if (!selectedLink || !dom.authorTaskPromiseTargets) {
    authorNotice("当前没有可合并的 observed promises。");
    return;
  }
  const merged = Array.from(
    new Set([
      ...splitPromiseTargetList(dom.authorTaskPromiseTargets.value || ""),
      ...((selectedLink.mapped_promises || []).map((item) => String(item.promise_id || "")).filter(Boolean)),
    ])
  );
  dom.authorTaskPromiseTargets.value = merged.join("\n");
}

function applySelectedTaskRewritePrefill() {
  const linking = getChapterTaskSimulationLinking();
  const selectedLink =
    (linking.task_links || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    (linking.task_links || []).find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    null;
  if (!selectedLink?.rewrite_workflow?.available) {
    authorNotice("当前 task 还没有可应用的 rewrite prefill。");
    return;
  }
  const workflow = selectedLink.rewrite_workflow;
  if (dom.authorTaskObjective) {
    dom.authorTaskObjective.value = workflow.suggested_task_objective || dom.authorTaskObjective.value || "";
  }
  if (dom.authorTaskPromiseTargets) {
    dom.authorTaskPromiseTargets.value = (workflow.suggested_promise_targets || []).join("\n");
  }
  if (dom.authorTaskBulkState) {
    dom.authorTaskBulkState.value = workflow.suggested_override_state || "";
  }
  if (dom.authorTaskBulkIssues) {
    dom.authorTaskBulkIssues.value = (workflow.issue_scope || []).join("\n");
  }
  if (dom.authorTaskBulkNotes) {
    dom.authorTaskBulkNotes.value = workflow.suggested_bulk_notes || "";
  }
  if (workflow.rewrite_target_chapter_index) {
    jumpToAuthorChapter(workflow.rewrite_target_chapter_index, "compare");
  } else {
    focusAuthorPanel("longform");
  }
}

async function bulkApplyTaskToSimulation() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const linking = getChapterTaskSimulationLinking();
  const selectedLink =
    (linking.task_links || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
    (linking.task_links || []).find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
    null;
  if (!selectedLink) {
    authorNotice("当前没有可批量应用的 task linking。");
    return;
  }
  const chapterIndices = Array.from(
    new Set(
      (selectedLink.compare_chapters || [])
        .map((item) => Number(item.chapter_index || 0))
        .concat((selectedLink.linked_chapters || []).map((item) => Number(item.chapter_index || 0)))
        .filter((item) => item > 0)
    )
  );
  if (!chapterIndices.length) {
    authorNotice("当前 task 还没有 linked chapters。");
    return;
  }
  try {
    await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/task-bulk-apply`, {
      method: "POST",
      body: JSON.stringify({
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        chapter_indices: chapterIndices,
        override_state: dom.authorTaskBulkState?.value || "",
        notes: dom.authorTaskBulkNotes?.value || "",
        issue_scope: parseMultilineList(dom.authorTaskBulkIssues?.value || ""),
        chapter_task_id: selectedLink.chapter_task_id,
        arc_id: selectedLink.arc_id,
        volume_id: selectedLink.volume_id,
      }),
    });
    if (chapterIndices[0]) {
      authorState.selectedAuthorContinuityChapterIndex = chapterIndices[0];
    }
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    await refreshAuthorSurface();
    focusAuthorPanel("compare");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "批量应用 Task -> Simulation");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "批量应用 Task -> Simulation 失败，请稍后再试。"), "error");
  }
}

function renderContinuityDiffWorkbench() {
  if (!dom.authorContinuityDiff) return;
  clearNode(dom.authorContinuityDiff);
  const workbench = getContinuityDiffWorkbench();
  const overrideWorkbench = getContinuityOverrideWorkbench();
  if (!workbench.available) {
    clearNode(dom.authorContinuityDiff, "完成 simulation 或 revision compare 后，这里会显示 continuity drift 和 before-after diff。");
    if (dom.authorContinuityChapterSelect) dom.authorContinuityChapterSelect.innerHTML = "";
    if (dom.authorContinuityOverrideState) dom.authorContinuityOverrideState.value = "";
    if (dom.authorContinuityIssueScope) dom.authorContinuityIssueScope.value = "";
    if (dom.authorContinuityOverrideNotes) dom.authorContinuityOverrideNotes.value = "";
    return;
  }
  const candidateChapters = Array.isArray(overrideWorkbench.candidate_chapters) ? overrideWorkbench.candidate_chapters : [];
  if (!authorState.selectedAuthorContinuityChapterIndex || !candidateChapters.some((item) => Number(item.chapter_index || 0) === Number(authorState.selectedAuthorContinuityChapterIndex || 0))) {
    authorState.selectedAuthorContinuityChapterIndex = candidateChapters[0]?.chapter_index || (workbench.top_changed_chapters || [])[0]?.chapter_index || null;
  }
  const selectedContinuity =
    candidateChapters.find((item) => Number(item.chapter_index || 0) === Number(authorState.selectedAuthorContinuityChapterIndex || 0)) ||
    (workbench.top_changed_chapters || []).find((item) => Number(item.chapter_index || 0) === Number(authorState.selectedAuthorContinuityChapterIndex || 0)) ||
    candidateChapters[0] ||
    (workbench.top_changed_chapters || [])[0];
  if (dom.authorContinuityChapterSelect) {
    dom.authorContinuityChapterSelect.innerHTML = candidateChapters
      .map((item) => `<option value="${item.chapter_index}">#${item.chapter_index} · ${item.override_state || item.source || "compare"} · ${item.chapter_title || item.after_title || item.before_title || "-"}</option>`)
      .join("");
    dom.authorContinuityChapterSelect.value = selectedContinuity?.chapter_index ? String(selectedContinuity.chapter_index) : "";
  }
  if (dom.authorContinuityOverrideState) {
    dom.authorContinuityOverrideState.innerHTML = [`<option value="">未标注</option>`, ...(overrideWorkbench.state_options || []).map((item) => `<option value="${item}">${item}</option>`)].join("");
    dom.authorContinuityOverrideState.value = selectedContinuity?.override_state || "";
  }
  if (dom.authorContinuityIssueScope) {
    dom.authorContinuityIssueScope.value = (selectedContinuity?.override_issue_scope || selectedContinuity?.issue_codes || []).join("\n");
  }
  if (dom.authorContinuityOverrideNotes) {
    dom.authorContinuityOverrideNotes.value = selectedContinuity?.override_notes || "";
  }
  dom.authorContinuityDiff.appendChild(
    createListCard({
      title: "Continuity Summary",
      score: workbench.simulation_freshness?.status || "-",
      body:
        `drifting characters ${(workbench.drifting_characters || []).length}\n` +
        `causal breaks ${(workbench.causal_breaks || []).length}\n` +
        `promise risks ${(workbench.promise_risks || []).length}\n` +
        `changed chapters ${(workbench.top_changed_chapters || []).length}\n` +
        `override count ${overrideWorkbench.override_count ?? 0}\n` +
        `next actions ${(workbench.next_actions || []).join(" / ") || "-"}`
    })
  );
  if (selectedContinuity) {
    dom.authorContinuityDiff.appendChild(
      createListCard({
        title: "Selected Continuity Chapter",
        score: selectedContinuity.override_state || selectedContinuity.source || "-",
        body:
          `${selectedContinuity.chapter_index}. ${selectedContinuity.chapter_title || selectedContinuity.after_title || selectedContinuity.before_title || "-"}\n` +
          `scene ${selectedContinuity.scene_function || "-"} · issues ${(selectedContinuity.issue_codes || []).join("/") || "-"}\n` +
          `override scope ${(selectedContinuity.override_issue_scope || []).join("/") || "-"}\n` +
          `notes ${selectedContinuity.override_notes || "-"}`
      })
    );
  }
  dom.authorContinuityDiff.appendChild(
    createListCard({
      title: "Top Changed Chapters",
      score: `${(workbench.top_changed_chapters || []).length} chapters`,
      body:
        `${(workbench.top_changed_chapters || []).map((item) => `${selectedAuthorCompareMarker(item.chapter_index)}${item.chapter_index}. ${item.before_title || "-"} -> ${item.after_title || "-"}\nscore ${Number(item.overall_score_delta || 0).toFixed(3)} · issues + ${(item.issue_codes_added || []).join("/") || "-"} · - ${(item.issue_codes_removed || []).join("/") || "-"}\noverride ${item.override_state || "-"} · notes ${item.override_notes || "-"}`).join("\n\n") || "-"}`
    })
  );
  if ((workbench.top_changed_chapters || [])[0]?.chapter_index) {
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const jumpButton = document.createElement("button");
    jumpButton.className = "ghost-action";
    jumpButton.textContent = "跳到首个 Diff 章节";
    jumpButton.addEventListener("click", () => {
      jumpToAuthorChapter(workbench.top_changed_chapters[0].chapter_index, "compare");
    });
    actions.appendChild(jumpButton);
    const button = document.createElement("button");
    button.className = "ghost-action";
    button.textContent = "评论首个 Diff 章节";
    button.addEventListener("click", () => {
      prefillAuthorCommentAnchor("simulation", String(workbench.top_changed_chapters[0].chapter_index));
    });
    actions.appendChild(button);
    dom.authorContinuityDiff.appendChild(actions);
  }
  if ((workbench.drifting_characters || []).length) {
    dom.authorContinuityDiff.appendChild(
      createListCard({
        title: "Character Drift",
        score: `${workbench.drifting_characters.length} hits`,
        body:
          `${(workbench.drifting_characters || []).map((item) => `${selectedAuthorCompareMarker(item.chapter_index)}${item.chapter_index}. ${item.chapter_title || "-"} · ${item.scene_function || "-"}\nissues ${(item.issue_codes || []).join("/") || "-"} · override ${item.override_state || "-"}`).join("\n\n")}`
      })
    );
  }
  if ((workbench.causal_breaks || []).length || (workbench.promise_risks || []).length) {
    dom.authorContinuityDiff.appendChild(
      createListCard({
        title: "Causal / Promise Risks",
        score: `${(workbench.causal_breaks || []).length + (workbench.promise_risks || []).length} items`,
        body:
          `${(workbench.causal_breaks || []).map((item) => `${selectedAuthorCompareMarker(item.chapter_index)}causal ${item.chapter_index}. ${item.chapter_title || "-"} · ${(item.issue_codes || []).join("/") || "-"} · ${item.override_state || "-"}`).join("\n") || "-"}` +
          `\n\n` +
          `${(workbench.promise_risks || []).map((item) => `${selectedAuthorCompareMarker(item.chapter_index)}promise ${item.chapter_index}. ${item.chapter_title || "-"} · ${(item.issue_codes || []).join("/") || "-"} · ${item.override_state || "-"}`).join("\n") || "-"}`
      })
    );
  }
}

function parseMultilineList(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitPromiseTargetList(value) {
  const seen = new Set();
  const results = [];
  String(value || "")
    .split("\n")
    .flatMap((line) => line.split(/[;,，/+|]+/))
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      if (seen.has(item)) return;
      seen.add(item);
      results.push(item);
    });
  return results;
}

const LONGFORM_DUTY_CYCLE = [
  "advance_plot",
  "advance_relationship",
  "expand_world",
  "resolve_promise",
  "pace_breath",
  "deliver_climax",
];

function normalizeLongformArcTasks(arc, chapterBudgetPolicy) {
  const targetChapters = Math.max(1, Number(arc.target_chapters || 1));
  const existing = Array.isArray(arc.chapter_tasks) ? arc.chapter_tasks : [];
  const baseWords = Math.max(500, Number(chapterBudgetPolicy?.default_target_words || 2000));
  const revealBudget = Math.max(0, Number(chapterBudgetPolicy?.default_reveal_budget || 1));
  const tasks = [];
  for (let index = 0; index < targetChapters; index += 1) {
    const previous = existing[index] || {};
    const dutyType =
      previous.duty_type ||
      LONGFORM_DUTY_CYCLE[index % LONGFORM_DUTY_CYCLE.length];
    tasks.push({
      chapter_task_id: previous.chapter_task_id || `${arc.arc_id}::task_${index + 1}`,
      objective: previous.objective || `以 ${dutyType} 为主职责推进当前弧线。`,
      duty_type: dutyType,
      target_words: Math.max(500, Number(previous.target_words || baseWords)),
      reveal_budget: Math.max(0, Number(previous.reveal_budget ?? revealBudget)),
      promise_actions: Array.isArray(previous.promise_actions) && previous.promise_actions.length
        ? previous.promise_actions
        : ["maintain_continuity"],
      promise_targets: Array.isArray(previous.promise_targets) ? previous.promise_targets : [],
      allow_terminal: Boolean(previous.allow_terminal),
      notes: previous.notes || "author_workbench_normalized_task",
    });
  }
  return tasks;
}

function formatMultilineList(values) {
  return (values || []).join("\n");
}

function parseLabelMap(value) {
  const result = {};
  for (const rawLine of String(value || "").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const separatorIndex = line.includes(":") ? line.indexOf(":") : line.indexOf("=");
    if (separatorIndex <= 0) continue;
    const key = line.slice(0, separatorIndex).trim();
    const label = line.slice(separatorIndex + 1).trim();
    if (key && label) {
      result[key] = label;
    }
  }
  return result;
}

function formatLabelMap(value) {
  return Object.entries(value || {})
    .map(([key, label]) => `${key}: ${label}`)
    .join("\n");
}

function parseSceneHooks(value) {
  const hooks = {};
  for (const rawLine of String(value || "").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const separatorIndex = line.includes(":") ? line.indexOf(":") : line.indexOf("=");
    if (separatorIndex <= 0) continue;
    const sceneFunction = line.slice(0, separatorIndex).trim();
    const hook = line.slice(separatorIndex + 1).trim();
    if (!sceneFunction || !hook) continue;
    hooks[sceneFunction] = hooks[sceneFunction] || [];
    hooks[sceneFunction].push(hook);
  }
  return hooks;
}

function formatSceneHooks(value) {
  const lines = [];
  Object.entries(value || {}).forEach(([sceneFunction, hooks]) => {
    (hooks || []).forEach((hook) => {
      if (hook) {
        lines.push(`${sceneFunction}: ${hook}`);
      }
    });
  });
  return lines.join("\n");
}

function renderStylePacingHookControls() {
  const worldpack = getActiveDraftWorldpack() || {};
  const stylePack = worldpack.narrative_style_pack || {};
  const dialoguePolicy = worldpack.dialogue_realism_policy || stylePack.dialogue || {};
  const sceneContracts = worldpack.scene_realization_contracts || {};
  const defaultSceneContract = Object.values(sceneContracts)[0] || stylePack.scene_realization || {};
  const thematicLabels = stylePack.thematic_axis_labels || {};

  if (dom.authorStyleLexicon) {
    dom.authorStyleLexicon.value = formatMultilineList(stylePack.tonal_lexicon || []);
  }
  if (dom.authorThemeLabels) {
    dom.authorThemeLabels.value = formatLabelMap(thematicLabels);
  }
  if (dom.authorHookTemplates) {
    dom.authorHookTemplates.value = formatMultilineList(stylePack.hook_templates || []);
  }
  if (dom.authorPacingRequireTurnTaking) {
    dom.authorPacingRequireTurnTaking.checked = Boolean(dialoguePolicy.require_turn_taking ?? true);
  }
  if (dom.authorPacingRequireCounterReaction) {
    dom.authorPacingRequireCounterReaction.checked = Boolean(dialoguePolicy.require_counter_reaction ?? true);
  }
  if (dom.authorPacingMinTurns) {
    dom.authorPacingMinTurns.value = String(Number(dialoguePolicy.min_turns || 2));
  }
  if (dom.authorPacingMaxTurns) {
    dom.authorPacingMaxTurns.value = String(Number(dialoguePolicy.max_turns || 3));
  }
  if (dom.authorPacingMinimumExchanges) {
    dom.authorPacingMinimumExchanges.value = String(Number(dialoguePolicy.minimum_exchanges || 1));
  }
  if (dom.authorPacingTurnPattern) {
    dom.authorPacingTurnPattern.value = formatMultilineList(dialoguePolicy.turn_pattern || ["speaker", "reaction", "reply"]);
  }
  if (dom.authorSceneHooks) {
    dom.authorSceneHooks.value = formatSceneHooks(defaultSceneContract.scene_hooks || {});
  }
  if (dom.authorStyleSummary) {
    appendAuthorCardGrid(dom.authorStyleSummary, [
      createAuthorSummaryCard({
        title: "风格窗口",
        score: `${(stylePack.tonal_lexicon || []).length} 词`,
        body:
          `tone ${(stylePack.tonal_lexicon || []).slice(0, 3).join(" / ") || "-"}\n` +
          `hooks ${(stylePack.hook_templates || []).slice(0, 2).join(" / ") || "-"}\n` +
          `turns ${dialoguePolicy.min_turns || 2}-${dialoguePolicy.max_turns || 3}\n` +
          `scene hooks ${Object.keys(defaultSceneContract.scene_hooks || {}).length}`,
      }),
      createAuthorSummaryCard({
        title: "能力资产",
        score: `${Object.keys(worldpack.voice_profiles || {}).length} voices`,
        body:
          `voice ${Object.keys(worldpack.voice_profiles || {}).length}\n` +
          `action ${Object.keys(worldpack.emotion_action_policies || {}).length}\n` +
          `sensory ${Object.keys(worldpack.sensory_grounding_policies || {}).length}\n` +
          `scene ${Object.keys(worldpack.scene_realization_contracts || {}).length}`,
      }),
    ]);
  }
}

function applyStylePacingHookControls(worldpack) {
  worldpack.narrative_style_pack = worldpack.narrative_style_pack || {};
  const stylePack = worldpack.narrative_style_pack;
  const thematicLabels = parseLabelMap(dom.authorThemeLabels?.value || "");
  stylePack.tonal_lexicon = parseMultilineList(dom.authorStyleLexicon?.value || "");
  stylePack.thematic_axis_labels = thematicLabels;
  stylePack.hook_templates = parseMultilineList(dom.authorHookTemplates?.value || "");
  stylePack.tag_labels = {
    ...(stylePack.tag_labels || {}),
    ...thematicLabels,
  };

  worldpack.dialogue_realism_policy = worldpack.dialogue_realism_policy || {};
  const minTurns = Math.max(1, Number(dom.authorPacingMinTurns?.value || 2));
  const maxTurns = Math.max(minTurns, Number(dom.authorPacingMaxTurns?.value || 3));
  worldpack.dialogue_realism_policy.require_turn_taking = Boolean(dom.authorPacingRequireTurnTaking?.checked);
  worldpack.dialogue_realism_policy.require_counter_reaction = Boolean(dom.authorPacingRequireCounterReaction?.checked);
  worldpack.dialogue_realism_policy.min_turns = minTurns;
  worldpack.dialogue_realism_policy.max_turns = maxTurns;
  worldpack.dialogue_realism_policy.minimum_exchanges = Math.max(1, Number(dom.authorPacingMinimumExchanges?.value || 1));
  worldpack.dialogue_realism_policy.turn_pattern = parseMultilineList(dom.authorPacingTurnPattern?.value || "") || ["speaker", "reaction", "reply"];

  const defaultContractKey = Object.keys(worldpack.scene_realization_contracts || {})[0] || "default";
  worldpack.scene_realization_contracts = worldpack.scene_realization_contracts || {};
  worldpack.scene_realization_contracts[defaultContractKey] = {
    ...(worldpack.scene_realization_contracts[defaultContractKey] || {}),
    scene_hooks: parseSceneHooks(dom.authorSceneHooks?.value || ""),
  };
}

function buildSimulationDiffSummary(previousReport, currentReport) {
  if (!previousReport || !currentReport) return "";
  const previous = previousReport.evaluation_summary || {};
  const current = currentReport.evaluation_summary || {};
  const parts = [];
  for (const key of ["pass_rate", "rewrite_rate", "block_rate"]) {
    const delta = Number(current[key] || 0) - Number(previous[key] || 0);
    if (delta !== 0) {
      parts.push(`${key}: ${delta >= 0 ? "+" : ""}${delta.toFixed(3)}`);
    }
  }
  return parts.join("\n");
}

function renderAuthorRevisionPanels() {
  clearNode(dom.authorAssetDiff);
  clearNode(dom.authorVersionHistory);
  const revisions = getActiveRevisionHistory();
  const diffDrilldown = getDiffDrilldown();
  const revisionEntries = diffDrilldown.revisions || [];
  const latestDiff = getLatestDiffSummary();
  if (!revisions.length) {
    clearNode(dom.authorAssetDiff, "保存角色、场景或能力配置后，这里会显示结构化 diff 摘要。");
    clearNode(dom.authorVersionHistory, "这里会显示最近几次 revision 与对应的修改来源。");
    return;
  }

  const selectedIndex = Math.max(0, Math.min(authorState.selectedAuthorRevisionIndex ?? revisions.length - 1, revisions.length - 1));
  authorState.selectedAuthorRevisionIndex = selectedIndex;
  const selectedRevision = revisions[selectedIndex];
  const selectedEntry = revisionEntries[selectedIndex] || {};
  const previousEntry = selectedIndex > 0 ? revisionEntries[selectedIndex - 1] || {} : {};
  const diffPayload = selectedEntry.diff_summary || (selectedIndex === revisions.length - 1 ? latestDiff : {
    changed_sections: selectedRevision.changed_sections || [],
    summary_text: selectedRevision.summary || "",
    character_changes: [],
    scene_changes: [],
    capability_changes: [],
  });

  dom.authorAssetDiff.appendChild(
    createListCard({
      title: selectedRevision.label || "最近一次修改",
      score: selectedRevision.source || "-",
      body:
        `summary: ${diffPayload.summary_text || selectedRevision.summary || "-"}\n` +
        `compare: ${previousEntry.snapshot_summary || "初始版本"} -> ${selectedEntry.snapshot_summary || "-"}\n` +
        `changed_sections: ${(diffPayload.changed_sections || []).join(" / ") || "-"}\n\n` +
        `section counts: sections ${diffDrilldown.section_change_counts?.sections ?? 0} · characters ${diffDrilldown.section_change_counts?.characters ?? 0} · scenes ${diffDrilldown.section_change_counts?.scenes ?? 0} · capabilities ${diffDrilldown.section_change_counts?.capabilities ?? 0}\n` +
        `simulation freshness: ${diffDrilldown.simulation_freshness?.status || "-"}\n` +
        `recommended next: ${(diffDrilldown.recommended_next_actions || []).join(" / ") || "-"}\n\n` +
        `${(diffPayload.character_changes || []).length ? `角色改动:\n${diffPayload.character_changes.map((item) => `${item.character_id}: ${(item.changed_fields || []).join(", ")}`).join("\n")}` : "角色改动: -"}\n\n` +
        `${(diffPayload.scene_changes || []).length ? `场景改动:\n${diffPayload.scene_changes.map((item) => `${item.scene_id}: ${(item.changed_fields || []).join(", ")}`).join("\n")}` : "场景改动: -"}\n\n` +
        `${(diffPayload.capability_changes || []).length ? `能力改动:\n${diffPayload.capability_changes.join("\n")}` : "能力改动: -"}\n\n` +
        `${selectedEntry.simulation_delta && Object.keys(selectedEntry.simulation_delta).length ? `simulation_delta:\n${Object.entries(selectedEntry.simulation_delta).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join("\n")}` : "simulation_delta: -"}`
    })
  );
  const diffActions = document.createElement("div");
  diffActions.className = "composer-actions";
  const commentCurrentDiff = document.createElement("button");
  commentCurrentDiff.className = "ghost-action";
  commentCurrentDiff.textContent = "评论当前 Diff";
  commentCurrentDiff.addEventListener("click", () => {
    prefillAuthorCommentAnchor("draft", selectedRevision.revision_id || authorState.activeDraftVersionId || "");
  });
  diffActions.appendChild(commentCurrentDiff);
  dom.authorAssetDiff.appendChild(diffActions);

  revisions.slice().reverse().forEach((revision, reverseIndex) => {
      const actualIndex = revisions.length - 1 - reverseIndex;
      const revisionEntry = revisionEntries[actualIndex] || {};
      const card = document.createElement("article");
      card.className = "list-card";
      if (actualIndex === selectedIndex) {
        card.classList.add("is-active");
      }
      const snapshot = revision.worldpack_snapshot || {};
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${revision.label || revision.source || "revision"}</h3>
          <span class="list-card-score">${revision.source || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(revision.created_at)}\n${revision.summary || "-"}\n${revisionEntry.snapshot_summary || `${snapshot.title || snapshot.world_id || "-"} · 角色 ${(snapshot.characters || []).length || 0} · 场景 ${(snapshot.scene_blueprints || []).length || 0}`}\nchanged ${(revisionEntry.diff_summary?.changed_sections || revision.changed_sections || []).join(" / ") || "-"}</p>
      `;
      card.addEventListener("click", () => {
        authorState.selectedAuthorRevisionIndex = actualIndex;
        renderAuthorRevisionPanels();
      });
      dom.authorVersionHistory.appendChild(card);
    });
}

function renderAuthorCompare() {
  clearNode(dom.authorCompare);
  const detail = authorState.activeDraftDetail || {};
  const revisionCompare = detail.revision_compare || {};
  const chapterCompare = detail.before_after_chapter_compare || {};
  if (!revisionCompare.available && !chapterCompare.available) {
    clearNode(dom.authorCompare, "这里会显示 revision compare 与 before-after chapter compare。");
    return;
  }
  if (revisionCompare.available) {
    const card = createListCard({
      title: "Revision Compare",
      score: `${revisionCompare.before_revision_id || "-"} -> ${revisionCompare.after_revision_id || "-"}`,
      body:
        `before ${revisionCompare.before_label || "-"}\nafter ${revisionCompare.after_label || "-"}\nsummary ${revisionCompare.after_summary || "-"}\nchanged ${(revisionCompare.after_diff_summary?.changed_sections || []).join(" / ") || "-"}\nsection counts before ${revisionCompare.section_counts?.before_changed_sections ?? 0} · after ${revisionCompare.section_counts?.after_changed_sections ?? 0}\nsimulation freshness ${revisionCompare.simulation_freshness?.status || "-"}\nsimulation delta ${(revisionCompare.simulation_delta && Object.keys(revisionCompare.simulation_delta).length) ? Object.entries(revisionCompare.simulation_delta).map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`).join(" / ") : "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const button = document.createElement("button");
    button.className = "ghost-action";
    button.textContent = "评论当前 Diff";
    button.addEventListener("click", () => {
      prefillAuthorCommentAnchor("draft", revisionCompare.after_revision_id || authorState.activeDraftVersionId || "");
    });
    actions.appendChild(button);
    card.appendChild(actions);
    dom.authorCompare.appendChild(card);
  }
  if (chapterCompare.available) {
    const topChanged = chapterCompare.top_changed_chapters || [];
    const selectedCompare =
      (chapterCompare.chapter_compare_map || {})[String(authorState.selectedAuthorContinuityChapterIndex || "")] || null;
    const card = createListCard({
      title: "Before / After Chapter Compare",
      score: `${topChanged.length} 章`,
      body:
        `${topChanged.map((item) => `${selectedAuthorCompareMarker(item.chapter_index)}${item.chapter_index}. ${item.before_title || "-"} -> ${item.after_title || "-"}\n${item.before_decision || "-"} -> ${item.after_decision || "-"} · score delta ${Number(item.overall_score_delta || 0).toFixed(3)}\nissues + ${(item.issue_codes_added || []).join("/") || "-"} · - ${(item.issue_codes_removed || []).join("/") || "-"}\nsignals ${(item.signal_deltas || {}) ? Object.entries(item.signal_deltas).map(([key, value]) => `${key}=${Number(value || 0).toFixed(3)}`).join(" / ") : "-"}\nBEFORE: ${item.before_excerpt || "-"}\nAFTER: ${item.after_excerpt || "-"}`).join("\n\n") || "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const firstTarget = topChanged[0];
    if (firstTarget) {
      const jumpButton = document.createElement("button");
      jumpButton.className = "ghost-action";
      jumpButton.textContent = "跳到首个章节对照";
      jumpButton.addEventListener("click", () => {
        jumpToAuthorChapter(firstTarget.chapter_index, "compare");
      });
      actions.appendChild(jumpButton);
      const button = document.createElement("button");
      button.className = "ghost-action";
      button.textContent = "评论首个章节对照";
      button.addEventListener("click", () => {
        prefillAuthorCommentAnchor("simulation", String(firstTarget.chapter_index));
      });
      actions.appendChild(button);
    }
    card.appendChild(actions);
    dom.authorCompare.appendChild(card);
    if (selectedCompare) {
      dom.authorCompare.appendChild(
        createListCard({
          title: "Selected Chapter Compare",
          score: `#${selectedCompare.chapter_index}`,
          body:
            `${selectedCompare.before_title || "-"} -> ${selectedCompare.after_title || "-"}\n` +
            `${selectedCompare.before_decision || "-"} -> ${selectedCompare.after_decision || "-"} · score delta ${Number(selectedCompare.overall_score_delta || 0).toFixed(3)}\n` +
            `issues + ${(selectedCompare.issue_codes_added || []).join("/") || "-"} · - ${(selectedCompare.issue_codes_removed || []).join("/") || "-"}\n` +
            `signals ${(selectedCompare.signal_deltas || {}) ? Object.entries(selectedCompare.signal_deltas).map(([key, value]) => `${key}=${Number(value || 0).toFixed(3)}`).join(" / ") : "-"}\n\n` +
            `BEFORE:\n${selectedCompare.before_excerpt || "-"}\n\nAFTER:\n${selectedCompare.after_excerpt || "-"}`
        })
      );
    }
  }
}

function renderAuthorCollaboration() {
  clearNode(dom.authorCollaboration);
  clearNode(dom.authorReviewerInbox);
  clearNode(dom.authorNotificationPreferences);
  authorState.authorReviewerInboxVisibleNotificationIds = [];
  const summary = authorState.authorCollaborationSummary || {};
  if (!authorState.activeDraftVersionId) {
    clearNode(dom.authorCollaboration, "这里会显示 anchored comments、blocking threads 与审批状态。");
    clearNode(dom.authorReviewerInbox, "这里会显示 reviewer inbox、notifications 与待处理 approval。");
    return;
  }
  const approval = summary.approval_summary || {};
  const notificationSummary = summary.notification_summary || {};
  const draftWatcherSummary = summary.draft_watcher_summary || {};
  const canReview = authorSessionCanReview();
  const reviewerId = activeAuthorReviewerId();
  const inbox = authorState.authorReviewerInbox || {};
  if (dom.authorReviewerGateNote) {
    dom.authorReviewerGateNote.textContent = canReview
      ? `当前账号具备审阅权限，${reviewerId || "当前 reviewer"} 的待审内容会在下面展开。`
      : "拥有审阅者权限的账号登录后，这里会展开可审阅内容与 reviewer inbox。";
  }
  const threads = summary.threads || [];
  const selectedThread =
    threads.find((item) => item.thread_id === authorState.selectedAuthorThreadId) ||
    threads[0] ||
    null;
  const card = createListCard({
    title: "Collaboration Summary",
    score: summary.recommended_next_action || "-",
    body:
      `open ${summary.open_thread_count ?? 0} · blocking ${summary.blocking_thread_count ?? 0}\napproval ${approval.latest_status || "-"}\nnotifications unread ${notificationSummary.unread_count ?? 0} / total ${notificationSummary.notification_count ?? 0}\nqueue ${(summary.queue_summary?.status_counts && Object.entries(summary.queue_summary.status_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nthreads by anchor ${(summary.threads_by_anchor || []).map((item) => `${item.anchor_type}:${item.anchor_key}=${item.thread_count}`).join(" / ") || "-"}`
  });
  dom.authorCollaboration.appendChild(card);
  if ((summary.assignee_queues || []).length) {
    dom.authorCollaboration.appendChild(
      createListCard({
        title: "Assignee Queues",
        score: `${summary.assignee_queues.length} queues`,
        body:
          `${summary.assignee_queues.map((item) => `${item.assignee_id} · open ${item.open_count} · blocking ${item.blocking_count} · total ${item.thread_count}`).join("\n") || "-"}`
      })
    );
  }
  if ((draftWatcherSummary.watcher_ids || []).length) {
    dom.authorCollaboration.appendChild(
      createListCard({
        title: "Draft Watchers",
        score: `${draftWatcherSummary.watcher_count ?? 0} watchers`,
        body:
          `explicit ${draftWatcherSummary.explicit_watcher_count ?? 0}\nwatchers ${(draftWatcherSummary.watcher_ids || []).join(" / ") || "-"}`
      })
    );
  }
  if (selectedThread) {
    const selectedCard = document.createElement("article");
    selectedCard.className = "list-card is-active";
    selectedCard.innerHTML = `
      <div class="list-card-head">
        <h3>Thread Detail · ${selectedThread.anchor_type}:${selectedThread.anchor_key}</h3>
        <span class="list-card-score">${selectedThread.status || "-"} / ${selectedThread.severity || "-"}</span>
      </div>
      <p class="list-card-body">thread ${selectedThread.thread_id}\nassignee ${selectedThread.assignee_id || "-"} · created_by ${selectedThread.created_by || "-"}\nwatchers ${(selectedThread.watcher_ids || []).join(" / ") || "-"}\nnotifications ${selectedThread.unread_notification_count ?? 0} unread / ${selectedThread.notification_count ?? 0}\nlatest ${selectedThread.latest_message_actor_id || "-"} · ${selectedThread.latest_message_at || "-"}</p>
    `;
    const selectedActions = document.createElement("div");
    selectedActions.className = "composer-actions";
    const toggleWatchButton = document.createElement("button");
    toggleWatchButton.className = "ghost-action";
    const currentActorId = activeAuthorActorId();
    const isWatching = (selectedThread.watcher_ids || []).includes(currentActorId);
    toggleWatchButton.textContent = isWatching ? "Unwatch" : "Watch";
    toggleWatchButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (isWatching) {
        await removeAuthorThreadWatcher(selectedThread.thread_id, currentActorId);
      } else {
        await addAuthorThreadWatcher(selectedThread.thread_id, currentActorId);
      }
    });
    selectedActions.appendChild(toggleWatchButton);
    if (canReview && reviewerId && selectedThread.assignee_id !== reviewerId) {
      const assignReviewerButton = document.createElement("button");
      assignReviewerButton.className = "ghost-action";
      assignReviewerButton.textContent = "Assign Reviewer";
      assignReviewerButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        await updateAuthorThreadStatusInline(selectedThread.thread_id, selectedThread.status || "open", {
          assigneeId: reviewerId,
          body: `指派给 ${reviewerId}。`,
        });
      });
      selectedActions.appendChild(assignReviewerButton);
    }
    const toggleStatusButton = document.createElement("button");
    toggleStatusButton.className = "ghost-action";
    toggleStatusButton.textContent = selectedThread.status === "open" ? "Resolve" : "Reopen";
    toggleStatusButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(selectedThread.thread_id, selectedThread.status === "open" ? "resolved" : "open", {
        assigneeId: selectedThread.assignee_id || undefined,
        body: selectedThread.status === "open" ? "Inline thread detail 标记为已处理。" : "Inline thread detail 重新打开。",
      });
    });
    selectedActions.appendChild(toggleStatusButton);
    selectedCard.appendChild(selectedActions);

    (selectedThread.messages || []).forEach((message) => {
      selectedCard.appendChild(
        createListCard({
          title: `${message.actor_id || "-"} · ${message.actor_role || "-"}`,
          score: message.created_at || "-",
          body:
            `${message.body || "-"}\nmentions ${(message.mentioned_actor_ids || []).join(" / ") || "-"}`
        })
      );
    });

    const replyBox = document.createElement("div");
    replyBox.className = "list-card";
    const replyTitle = document.createElement("div");
    replyTitle.className = "list-card-head";
    replyTitle.innerHTML = `<h3>Reply Inline</h3><span class="list-card-score">${activeAuthorActorId()} / ${activeAuthorActorRole()}</span>`;
    replyBox.appendChild(replyTitle);
    const replyInput = document.createElement("textarea");
    replyInput.rows = 4;
    replyInput.placeholder = "输入 thread 回复，可继续用 @mention。";
    replyInput.value = authorState.authorInlineReplyDraft || "";
    replyInput.addEventListener("input", () => {
      authorState.authorInlineReplyDraft = replyInput.value;
    });
    replyBox.appendChild(replyInput);
    const replyActions = document.createElement("div");
    replyActions.className = "composer-actions";
    const replyButton = document.createElement("button");
    replyButton.className = "ghost-action";
    replyButton.textContent = "Send Reply";
    replyButton.addEventListener("click", async () => {
      await replyToSelectedAuthorThread(selectedThread.thread_id);
    });
    replyActions.appendChild(replyButton);
    replyBox.appendChild(replyActions);
    selectedCard.appendChild(replyBox);
    dom.authorCollaboration.appendChild(selectedCard);
  }
  if ((notificationSummary.latest_notifications || []).length) {
    dom.authorCollaboration.appendChild(
      createListCard({
        title: "Latest Notifications",
        score: `${notificationSummary.unread_count ?? 0} unread`,
        body:
          `${(notificationSummary.latest_notifications || []).map((item) => `${item.recipient_id} · ${item.notification_type} · ${item.status}\n${item.title}\n${item.body || "-"}`).join("\n\n") || "-"}`
      })
    );
  }
  threads.slice(0, 8).forEach((thread) => {
    const threadCard = createListCard({
      title: `${thread.anchor_type}:${thread.anchor_key}`,
      score: `${thread.status || "-"} / ${thread.severity || "-"}`,
      body:
        `assignee ${thread.assignee_id || "-"} · created_by ${thread.created_by || "-"}\nparticipants ${(thread.participant_ids || []).join(" / ") || "-"}\nmentions ${(thread.mentioned_actor_ids || []).join(" / ") || "-"}\nnotifications ${thread.unread_notification_count ?? 0} unread / ${thread.notification_count ?? 0}\nlatest ${thread.latest_message_preview || "-"}`
      ,
      active: authorState.selectedAuthorThreadId === thread.thread_id
    });
    threadCard.addEventListener("click", async () => {
      await selectAuthorThread(thread.thread_id, thread.world_version_id);
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const focusButton = document.createElement("button");
    focusButton.className = "ghost-action";
    focusButton.textContent = "定位 Anchor";
    focusButton.addEventListener("click", (event) => {
      event.stopPropagation();
      prefillAuthorCommentAnchor(thread.anchor_type, thread.anchor_key);
    });
    actions.appendChild(focusButton);
    if (canReview && reviewerId && thread.assignee_id !== reviewerId) {
      const assignButton = document.createElement("button");
      assignButton.className = "ghost-action";
      assignButton.textContent = "指派给 Reviewer";
      assignButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        await updateAuthorThreadStatusInline(thread.thread_id, thread.status || "open", {
          assigneeId: reviewerId,
          body: `指派给 ${reviewerId}。`,
        });
      });
      actions.appendChild(assignButton);
    }
    const statusButton = document.createElement("button");
    statusButton.className = "ghost-action";
    statusButton.textContent = thread.status === "open" ? "标记 Resolved" : "重新打开";
    statusButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(thread.thread_id, thread.status === "open" ? "resolved" : "open", {
        assigneeId: thread.assignee_id || undefined,
        body: thread.status === "open" ? "Reviewer inbox 已处理。" : "重新打开继续跟进。",
      });
    });
    actions.appendChild(statusButton);
    threadCard.appendChild(actions);
    dom.authorCollaboration.appendChild(threadCard);
  });

  if (!canReview || !reviewerId) {
    clearNode(dom.authorReviewerInbox, "当前账号没有审阅权限；普通用户只保留创作与送审发起路径。");
    return;
  }

  if (dom.authorLoadMoreReviewerInbox) {
    dom.authorLoadMoreReviewerInbox.disabled = !authorState.authorReviewerInboxHasMore;
    dom.authorLoadMoreReviewerInbox.textContent = authorState.authorReviewerInboxHasMore ? "Load More" : "No More Results";
  }

  dom.authorReviewerInbox.appendChild(
    createListCard({
      title: "Reviewer Inbox Summary",
      score: inbox.recommended_next_action || "-",
      body:
        `reviewer ${reviewerId}\nassigned ${inbox.queue_summary?.assigned_open_thread_count ?? 0} · blocking ${inbox.queue_summary?.blocking_assigned_thread_count ?? 0}\npending approvals ${inbox.queue_summary?.pending_approval_count ?? 0}\nunread notifications ${inbox.queue_summary?.unread_notification_count ?? 0}\nreturned ${inbox.returned_count ?? (inbox.notifications || []).length} · more ${inbox.has_more ? "yes" : "no"}\nstatus ${(inbox.queue_summary?.status_counts && Object.entries(inbox.queue_summary.status_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\ntypes ${(inbox.queue_summary?.notification_type_counts && Object.entries(inbox.queue_summary.notification_type_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}`
    })
  );

  if ((inbox.world_version_queues || []).length) {
    dom.authorReviewerInbox.appendChild(
      createListCard({
        title: "Inbox by Draft",
        score: `${inbox.world_version_queues.length} drafts`,
        body:
          `${(inbox.world_version_queues || []).map((item) => `${item.world_version_id} · unread ${item.unread_count} · total ${item.notification_count}`).join("\n") || "-"}`
      })
    );
  }

  (inbox.pending_approvals || []).slice(0, 4).forEach((approvalItem) => {
    const approvalCard = createListCard({
      title: `Approval ${approvalItem.world_version_id}`,
      score: approvalItem.status || "requested",
      body:
        `reviewer ${approvalItem.reviewer_id || "-"}\nrevision ${approvalItem.revision_id || "-"}\nreason ${approvalItem.reason || "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const approveButton = document.createElement("button");
    approveButton.className = "ghost-action";
    approveButton.textContent = "批准";
    approveButton.addEventListener("click", async () => {
      await decideAuthorApprovalForWorld(approvalItem.world_version_id, "approved", reviewerId, "Reviewer inbox 快速批准。");
    });
    actions.appendChild(approveButton);
    const changesButton = document.createElement("button");
    changesButton.className = "ghost-action";
    changesButton.textContent = "要求修改";
    changesButton.addEventListener("click", async () => {
      await decideAuthorApprovalForWorld(approvalItem.world_version_id, "changes_requested", reviewerId, "Reviewer inbox 要求修改。");
    });
    actions.appendChild(changesButton);
    approvalCard.appendChild(actions);
    dom.authorReviewerInbox.appendChild(approvalCard);
  });

  const visibleNotifications = (inbox.notifications || []).slice(0, 8);
  authorState.authorReviewerInboxVisibleNotificationIds = visibleNotifications.map((item) => item.notification_id).filter(Boolean);
  visibleNotifications.forEach((notification) => {
    const notificationCard = createListCard({
      title: notification.title || notification.notification_type || "Notification",
      score: `${notification.status || "-"} / ${notification.recipient_role || "-"}`,
      body:
        `type ${notification.notification_type || "-"} · world ${notification.world_version_id || "-"}\nactor ${notification.actor_id || "-"} · recipient ${notification.recipient_id || "-"}\nanchor ${notification.anchor_type || "-"}:${notification.anchor_key || "-"}\n${notification.body || "-"}`
    });
    notificationCard.addEventListener("click", async () => {
      if (notification.thread_id) {
        await selectAuthorThread(notification.thread_id, notification.world_version_id || "");
      }
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const readButton = document.createElement("button");
    readButton.className = "ghost-action";
    readButton.textContent = "标记已读";
    readButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorNotificationStatus(notification.notification_id, "read");
    });
    actions.appendChild(readButton);
    const archiveButton = document.createElement("button");
    archiveButton.className = "ghost-action";
    archiveButton.textContent = "归档";
    archiveButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorNotificationStatus(notification.notification_id, "archived");
    });
    actions.appendChild(archiveButton);
    if (notification.anchor_type && notification.anchor_key) {
      const focusButton = document.createElement("button");
      focusButton.className = "ghost-action";
      focusButton.textContent = "跳到线程";
      focusButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        if (notification.thread_id) {
          await selectAuthorThread(notification.thread_id, notification.world_version_id || "");
        }
        prefillAuthorCommentAnchor(notification.anchor_type, notification.anchor_key);
      });
      actions.appendChild(focusButton);
    }
    notificationCard.appendChild(actions);
    dom.authorReviewerInbox.appendChild(notificationCard);
  });

  (inbox.blocking_assigned_threads || []).slice(0, 4).forEach((thread) => {
    const blockingCard = createListCard({
      title: `Blocking ${thread.anchor_type}:${thread.anchor_key}`,
      score: thread.severity || "blocker",
      body:
        `thread ${thread.thread_id}\nlatest ${thread.latest_message_preview || "-"}\nstatus ${thread.status || "-"} · assignee ${thread.assignee_id || "-"}`
    });
    blockingCard.addEventListener("click", async () => {
      await selectAuthorThread(thread.thread_id, thread.world_version_id);
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const resolveButton = document.createElement("button");
    resolveButton.className = "ghost-action";
    resolveButton.textContent = "处理完成";
    resolveButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(thread.thread_id, "resolved", {
        actorId: reviewerId,
        assigneeId: reviewerId,
        body: "Reviewer inbox 标记为已处理。",
      });
    });
    actions.appendChild(resolveButton);
    blockingCard.appendChild(actions);
    dom.authorReviewerInbox.appendChild(blockingCard);
  });

  const preferences = authorState.authorNotificationPreferences?.preferences || [];
  if (!preferences.length) {
    clearNode(dom.authorNotificationPreferences, "这里会显示当前 actor 的 notification preferences。");
  } else {
    dom.authorNotificationPreferences.appendChild(
      createListCard({
        title: `Notification Preferences · ${authorState.authorNotificationPreferences?.actor_id || activeAuthorActorId()}`,
        score: `${preferences.length} types`,
        body:
          `${preferences.map((item) => `${item.notification_type} · in-app ${item.in_app_enabled ? "on" : "off"} · async ${item.async_mirror_enabled ? "on" : "off"} · sink ${item.async_sink_name || "default"} · target ${item.delivery_target || "-"}${item.is_default ? " · default" : ""}`).join("\n") || "-"}`
      })
    );
  }
}

function renderAuthorDrafts() {
  clearNode(dom.authorDraftList);
  if (!authorState.authorDrafts.length) {
    clearNode(dom.authorDraftList, "还没有 draft。先把当前世界保存为 Draft。");
    return;
  }
  const simulateAccess = authorState.authorAccessSnapshot?.actions?.simulate || null;
  const submitAccess = authorState.authorAccessSnapshot?.actions?.submit_draft || null;
  const validateAccess = authorState.authorAccessSnapshot?.actions?.validate_draft || null;
  authorState.authorDrafts.forEach((draft) => {
    const card = document.createElement("article");
    card.className = "list-card";
    if (draft.world_version_id === authorState.activeDraftVersionId) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${draft.title || draft.world_id}</h3>
        <span class="list-card-score">${draft.status}</span>
      </div>
      <p class="list-card-body">版本 ${draft.version || draft.world_version_id} · 风险 ${draft.risk_rating || "未定"}</p>
      <div class="composer-actions">
        <button class="ghost-action draft-validate">校验</button>
        <button class="ghost-action draft-simulate">模拟</button>
        <button class="primary-action draft-submit">送审</button>
      </div>
    `;
    card.querySelector(".draft-validate").addEventListener("click", () => {
      (async () => {
        try {
          await validateDraftVersion(draft.world_version_id);
        } catch (error) {
          const detail = parseErrorDetail(error);
          await refreshAuthorSurface();
        if (detail?.code === "author_entitlement_required") {
          alertAuthorGating(detail, "校验 Draft");
          return;
        }
          authorNotice(formatAuthorApiErrorMessage(error, "校验失败，请稍后再试。"), "error");
        }
      })();
    });
    card.querySelector(".draft-simulate").addEventListener("click", async () => {
      try {
        await simulateDraftVersion(draft.world_version_id);
      } catch (error) {
        const detail = parseErrorDetail(error);
        await refreshAuthorSurface();
        if (detail?.code === "author_entitlement_required") {
          authorNotice(`当前不能模拟：${accessReasonLabel(detail.reason)}。需要 ${detail.required_display_name || tierLabel(detail.required_tier)}，当前 ${detail.wallet_type || "-"} 余额 ${Number(detail.balance || 0).toFixed(0)}。`);
          return;
        }
        authorNotice(formatAuthorApiErrorMessage(error, "模拟失败，请稍后再试。"), "error");
      }
    });
    if (simulateAccess && !simulateAccess.allowed) {
      const button = card.querySelector(".draft-simulate");
      button.disabled = true;
      button.title = gatingHint(simulateAccess);
    }
    if (validateAccess && !validateAccess.allowed) {
      const button = card.querySelector(".draft-validate");
      button.disabled = true;
      button.title = gatingHint(validateAccess);
    }
    card.querySelector(".draft-submit").addEventListener("click", async () => {
      try {
        await submitDraftVersion(draft.world_version_id);
      } catch (error) {
        const detail = parseErrorDetail(error);
        await refreshAuthorSurface();
        if (detail?.code === "author_entitlement_required") {
          alertAuthorGating(detail, "提交送审");
          return;
        }
        authorNotice(formatAuthorApiErrorMessage(error, "送审失败，请稍后再试。"), "error");
      }
    });
    if (submitAccess && !submitAccess.allowed) {
      const button = card.querySelector(".draft-submit");
      button.disabled = true;
      button.title = gatingHint(submitAccess);
    }
    card.addEventListener("click", async () => {
      authorState.activeDraftVersionId = draft.world_version_id;
      authorState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
      authorState.selectedAuthorRevisionIndex = null;
      renderAuthorDrafts();
      renderAuthorReports();
    });
    dom.authorDraftList.appendChild(card);
  });
}

function renderAuthorWorkflow() {
  clearNode(dom.authorWorkflow);
  const workflow = authorState.authorWorkflowSummary;
  if (!workflow) {
    clearNode(dom.authorWorkflow, "这里会显示 brief -> draft -> simulate -> revise -> submit 的当前阶段与建议动作。");
    return;
  }
  const primaryAction = (workflow.cta_actions || []).find((item) => item.primary) || (workflow.cta_actions || [])[0] || null;
  const blockers = workflow.blockers || [];
  const readiness = workflow.longform_readiness || {};
  const promiseRunway = workflow.promise_runway_summary || {};
  const card = document.createElement("article");
  card.className = "list-card author-workflow-card";
  card.innerHTML = `
    <div class="author-workflow-kicker">推荐下一步</div>
    <div class="author-workflow-head">
      <div>
        <h3>${authorRecommendedActionLabel(primaryAction?.action_id || workflow.recommended_action)}</h3>
        <p>${workflow.draft_title || "当前 Draft"} · ${authorStageLabel(workflow.stage)} · 推荐入口 ${authorRecommendedWorkspaceLabel(primaryAction?.action_id || workflow.recommended_action)} · 当前口径 ${workflow.claim_safe_band ? `${workflow.claim_safe_band}章` : "未达安全承诺"}</p>
      </div>
      <span class="list-card-score">${authorStageLabel(workflow.stage)}</span>
    </div>
    <div class="author-workflow-grid">
      <div class="author-workflow-metric">
        <span>推荐动作</span>
        <strong>${primaryAction?.label || workflow.recommended_action || "-"}</strong>
      </div>
      <div class="author-workflow-metric">
        <span>校验</span>
        <strong>${workflow.validation_summary?.status || "-"}</strong>
        <p>errors ${workflow.validation_summary?.error_count ?? 0} · warnings ${workflow.validation_summary?.warning_count ?? 0}</p>
      </div>
      <div class="author-workflow-metric">
        <span>模拟</span>
        <strong>${workflow.simulation_summary?.latest_decision || "-"}</strong>
        <p>pass ${formatPercent(workflow.simulation_summary?.pass_rate)} · rewrite ${formatPercent(workflow.simulation_summary?.rewrite_rate)} · block ${formatPercent(workflow.simulation_summary?.block_rate)}</p>
      </div>
      <div class="author-workflow-metric">
        <span>当前阻塞</span>
        <strong>${blockers.length ? `${blockers.length} 项` : "无 blocker"}</strong>
        <p>${blockers[0]?.message || "可以继续往下一阶段推进。"}</p>
      </div>
      <div class="author-workflow-metric">
        <span>长线能力</span>
        <strong>${workflow.entry_mode === "structured_longform" ? "结构化长篇" : "Quick Brief"}</strong>
        <p>目标 ${workflow.requested_target_band || "-"} · 当前支持 ${workflow.supported_target_band || "-"} · readiness ${readiness.status || "-"}</p>
      </div>
    </div>
    <div class="author-stage-track">
      ${(workflow.stages || []).map((item) => `<span class="author-stage-pill ${authorStageTone(item.status)}">${item.label}</span>`).join("") || '<span class="author-stage-pill is-pending">等待工作流</span>'}
    </div>
    <div class="author-workflow-notes">
      <p><strong>Draft</strong> ${workflow.world_version_id || "-"}</p>
      <p><strong>Simulation freshness</strong> ${workflow.simulation_freshness?.status || "-"}</p>
      <p><strong>Longform readiness</strong> ${readiness.status || "-"} · 目标 ${workflow.requested_target_chapters || "-"} 章 · 结构 ${workflow.longform_structure_counts?.character_count || 0} 角色 / ${workflow.longform_structure_counts?.scene_blueprint_count || 0} 场景 / ${workflow.longform_structure_counts?.location_count || 0} 地点 / ${workflow.longform_structure_counts?.scene_family_count || 0} scene family / ${workflow.longform_structure_counts?.distinct_role_pair_count || 0} role pairs</p>
      <p><strong>Promise runway</strong> ${promiseRunway.runway_status || "-"} · open ${promiseRunway.open_count ?? 0} · overdue ${promiseRunway.overdue_count ?? 0} · chapters since new ${promiseRunway.chapters_since_last_new_promise ?? "-"}</p>
      <p><strong>下一步说明</strong> ${primaryAction?.reason || blockers[0]?.message || "继续当前阶段的推荐动作。"}</p>
    </div>
  `;
  dom.authorWorkflow.appendChild(card);
  if ((workflow.cta_actions || []).length) {
    const actions = document.createElement("div");
    actions.className = "composer-actions author-workflow-actions";
    workflow.cta_actions.forEach((item) => {
      const button = document.createElement("button");
      button.className = item.primary ? "primary-action" : "ghost-action";
      button.textContent = item.label || item.action_id;
      button.disabled = item.enabled === false;
      if (item.reason) {
        button.title = item.reason;
      }
      button.addEventListener("click", async () => {
        try {
          await runAuthorWorkflowAction(item.action_id);
        } catch (error) {
          authorNotice(formatAuthorApiErrorMessage(error, "执行工作流动作失败，请稍后再试。"), "error");
        }
      });
      actions.appendChild(button);
    });
    dom.authorWorkflow.appendChild(actions);
  }
}

function renderAuthorGuidedFocus() {
  clearNode(dom.authorGuidedFocus);
  const workflow = authorState.authorWorkflowSummary;
  const primaryAction = (workflow?.cta_actions || []).find((item) => item.primary) || (workflow?.cta_actions || [])[0] || null;
  const titleNode = dom.authorStageTitle;
  const copyNode = dom.authorStageCopy;
  const currentWorkspace = shellState.authorWorkspace || "overview";
  if (currentWorkspace === "settings") {
    if (titleNode) {
      titleNode.textContent = "先确认身份，再决定通知和协作怎么流动";
    }
    if (copyNode) {
      copyNode.textContent = "Settings 只做三件事：确认当前登录态、确认通知投递、确认协作与审批的处理入口。";
    }
    const preferences = authorState.authorNotificationPreferences?.preferences || [];
    const collaboration = authorState.authorCollaborationSummary || {};
    const authIdentity = authorState.authorAuthSession?.identity || null;
    const notificationTargets = preferences
      .map((item) => item.delivery_target || item.async_sink_name || "")
      .filter(Boolean)
      .slice(0, 3)
      .join(" / ") || "未配置外部投递";
    const authWarning = !authIdentity
      ? "当前还没有登录态，作者通知和协作身份都不会稳定同步。"
      : isAuthorSessionExpiringSoon(authorState.authorAuthSession?.expiresAt)
        ? "当前 token 即将过期，建议尽快刷新会话。"
        : "";
    const notificationWarning = !preferences.length
      ? "当前没有自定义通知规则，重要更新可能只能靠手动刷新看到。"
      : !preferences.some((item) => item.delivery_target || item.async_sink_name)
        ? "当前没有外部投递目标，异步提醒可能收不到。"
        : "";
    const collaborationWarning =
      Number(collaboration.blocking_thread_count || 0) > 0
        ? `当前有 ${collaboration.blocking_thread_count} 个 blocker 线程待处理。`
        : Number((collaboration.notification_summary || {}).unread_count || 0) > 0
          ? `当前有 ${(collaboration.notification_summary || {}).unread_count || 0} 条未读协作通知。`
          : "";
    const settingsGrid = document.createElement("div");
    settingsGrid.className = "author-settings-summary-grid";
    const cards = [
      createAuthorSummaryCard({
        title: "登录态",
        score: authIdentity?.actor_role || "未登录",
        body:
          `actor ${authIdentity?.actor_id || "-"}\n` +
          `display ${authIdentity?.display_name || "-"}\n` +
          `expires ${authorState.authorAuthSession?.expiresAt || "-"}\n` +
          `next ${authIdentity ? "继续协作设置" : "先建立作者身份"}`,
        warning: authWarning,
        actionLabel: authIdentity ? "刷新会话" : "登录配置",
        onAction: () => focusAuthorPanel("auth_settings"),
        primary: true,
      }),
      createAuthorSummaryCard({
        title: "通知态",
        score: `${preferences.length} rules`,
        body:
          `in-app on ${preferences.filter((item) => item.in_app_enabled).length}\n` +
          `async on ${preferences.filter((item) => item.async_mirror_enabled).length}\n` +
          `targets ${notificationTargets}\n` +
          `next ${preferences.length ? "确认规则是否覆盖当前 Draft" : "先建一条通知规则"}`,
        warning: notificationWarning,
        actionLabel: "打开通知设置",
        onAction: () => focusAuthorPanel("notification_settings"),
      }),
      createAuthorSummaryCard({
        title: "协作态",
        score: collaboration.recommended_next_action || "-",
        body:
          `open ${collaboration.open_thread_count ?? 0} · blocking ${collaboration.blocking_thread_count ?? 0}\n` +
          `approval ${(collaboration.approval_summary || {}).latest_status || "-"}\n` +
          `notifications unread ${(collaboration.notification_summary || {}).unread_count ?? 0}\n` +
          `next ${collaboration.recommended_next_action || "打开协作区"}`,
        warning: collaborationWarning,
        actionLabel: "打开协作区",
        onAction: () => focusAuthorPanel("collaboration"),
      }),
    ];
    cards.forEach((card) => settingsGrid.appendChild(card));
    const actions = document.createElement("div");
    actions.className = "composer-actions author-guided-actions";
    [
      { label: "看登录态", panel: "auth_settings", primary: true },
      { label: "看通知态", panel: "notification_settings" },
      { label: "看协作态", panel: "collaboration" },
    ].forEach((item) => {
      const button = document.createElement("button");
      button.className = item.primary ? "primary-action" : "ghost-action";
      button.textContent = item.label;
      button.addEventListener("click", () => focusAuthorPanel(item.panel));
      actions.appendChild(button);
    });
    dom.authorGuidedFocus.appendChild(settingsGrid);
    dom.authorGuidedFocus.appendChild(actions);
    return;
  }
  if (currentWorkspace === "simulate") {
    const drilldown = getSimulationDrilldown();
    const linking = getChapterTaskSimulationLinking();
    const continuity = getContinuityDiffWorkbench();
    const firstIssueTarget = (drilldown.issue_focus_queue || [])[0]?.chapter_targets?.[0] || null;
    const firstWeakChapter = (drilldown.weakest_chapters || [])[0] || null;
    const taskLinks = Array.isArray(linking.task_links) ? linking.task_links : [];
    const selectedTaskLink =
      taskLinks.find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) ||
      taskLinks.find((item) => item.arc_id === authorState.selectedAuthorArcId) ||
      taskLinks[0] ||
      null;
    const selectedContinuity =
      (continuity.top_changed_chapters || [])[0] ||
      (continuity.drifting_characters || [])[0] ||
      (continuity.promise_risks || [])[0] ||
      null;
    const selectedCompareChapter = selectedTaskLink?.compare_chapters?.[0] || selectedContinuity || firstWeakChapter || null;
    if (titleNode) {
      titleNode.textContent = "先处理最急的问题章节，再决定回哪一段继续改";
    }
    if (copyNode) {
      copyNode.textContent = "Simulate 页最重要的是把 issue queue 和 weakest chapters 直接连回编辑动作，而不是让作者先读完整份报告。";
    }
    const card = document.createElement("article");
    card.className = "list-card author-guided-focus-card";
    card.innerHTML = `
      <div class="author-guided-kicker">Simulate 导航</div>
      <h3>${firstIssueTarget ? `先看第 ${firstIssueTarget.chapter_index} 章的问题章节` : "先看最弱章节与 issue queue"}</h3>
      <p>${firstIssueTarget ? `${firstIssueTarget.chapter_title || "-"} · ${firstIssueTarget.scene_function || "-"} / ${firstIssueTarget.decision || "-"}` : "当前没有 issue focus queue，可以先从 weakest chapters 入手。"} </p>
      <div class="author-guided-meta">
        <span>Issue Queue ${(drilldown.issue_focus_queue || []).length} 项</span>
        <span>Weakest ${(drilldown.weakest_chapters || []).length} 章</span>
        <span>Chapter Breakdown ${(drilldown.chapter_breakdown || []).length} 章</span>
      </div>
    `;
    const actions = document.createElement("div");
    actions.className = "composer-actions author-guided-actions";
    if (firstIssueTarget) {
      const jumpIssue = document.createElement("button");
      jumpIssue.className = "primary-action";
      jumpIssue.textContent = "跳到问题章节";
      jumpIssue.addEventListener("click", () => jumpToAuthorChapter(firstIssueTarget.chapter_index, "simulation"));
      const commentIssue = document.createElement("button");
      commentIssue.className = "ghost-action";
      commentIssue.textContent = "评论这个问题章节";
      commentIssue.addEventListener("click", () => prefillAuthorCommentAnchor("simulation", String(firstIssueTarget.chapter_index)));
      actions.appendChild(jumpIssue);
      actions.appendChild(commentIssue);
    }
    if (firstWeakChapter) {
      const jumpWeak = document.createElement("button");
      jumpWeak.className = actions.childElementCount ? "ghost-action" : "primary-action";
      jumpWeak.textContent = "查看最弱章节";
      jumpWeak.addEventListener("click", () => jumpToAuthorChapter(firstWeakChapter.chapter_index, "simulation"));
      actions.appendChild(jumpWeak);
    }
    const openDraft = document.createElement("button");
    openDraft.className = "ghost-action";
    openDraft.textContent = "回 Draft Workbench";
    openDraft.addEventListener("click", () => focusAuthorPanel("longform"));
    actions.appendChild(openDraft);
    dom.authorGuidedFocus.appendChild(card);
    const workGrid = document.createElement("div");
    workGrid.className = "author-simulate-work-grid";
    const taskCard = createAuthorWorkCard({
      title: "Chapter Task Work Card",
      score: selectedTaskLink?.status || (selectedTaskLink ? "linked" : "未链接"),
      body:
        `${selectedTaskLink ? `${selectedTaskLink.chapter_task_id}\n当前对象 ${selectedTaskLink.duty_type || "-"} · ${selectedTaskLink.objective || "-"}\n当前问题 ${(selectedTaskLink.compare_summary?.issue_codes_added || []).join("/") || (selectedTaskLink.compare_summary?.issue_codes_removed || []).join("/") || "暂无明显 diff issue"}\n下一步 先回 Task Linking 或 Longform Workbench 修改任务与 promise。` : "当前还没有 chapter task linking。\n当前问题 simulation 还没把 chapter task 显式连到章节。\n下一步 先回 Longform Workbench 查看当前 arc/task。"}`
      ,
      warning: selectedTaskLink ? "" : "当前还没有 task linking，先回 Draft 侧建立或确认 chapter task。",
      active: Boolean(selectedTaskLink && authorState.selectedAuthorTaskId && selectedTaskLink.chapter_task_id === authorState.selectedAuthorTaskId),
      actions: [
        ...(selectedTaskLink ? [{
          label: "打开 Task Linking",
          primary: true,
          onClick: () => {
            authorState.selectedAuthorTaskId = selectedTaskLink.chapter_task_id;
            renderAuthorReports();
            focusAuthorPanel("task_linking");
          },
        }] : []),
        ...(selectedTaskLink?.linked_chapters?.[0]?.chapter_index ? [{
          label: "跳到 Task 章节",
          onClick: () => {
            jumpToAuthorChapter(selectedTaskLink.linked_chapters[0].chapter_index, "simulation");
          },
        }] : []),
        {
          label: "回 Longform Workbench",
          primary: !selectedTaskLink,
          onClick: () => focusAuthorPanel("longform"),
        },
      ]
    });
    workGrid.appendChild(taskCard);

    const continuityCard = createAuthorWorkCard({
      title: "Continuity Work Card",
      score: selectedContinuity?.override_state || selectedContinuity?.source || "待检查",
      body:
        `${selectedContinuity ? `${selectedContinuity.chapter_index}. ${selectedContinuity.chapter_title || selectedContinuity.after_title || selectedContinuity.before_title || "-"}\n当前问题 ${(selectedContinuity.issue_codes || []).join("/") || "暂无 issue"} · override ${selectedContinuity.override_state || "-"}\n下一步 先打开 Continuity Diff，确认 override 和 issue scope。` : "当前没有 continuity drift。\n当前问题 暂无可直接处理的 continuity 项。\n下一步 可先从 top changed chapters 或 weakest chapter 进入 Compare。"}`
      ,
      warning: selectedContinuity ? "" : "当前没有 continuity drift 命中，可从 Compare 或 Weakest Chapters 先找目标。",
      active: Boolean(selectedContinuity?.chapter_index && Number(authorState.selectedAuthorContinuityChapterIndex || 0) === Number(selectedContinuity.chapter_index)),
      actions: [
        ...(selectedContinuity?.chapter_index ? [{
          label: "打开 Continuity Diff",
          primary: true,
          onClick: () => {
            authorState.selectedAuthorContinuityChapterIndex = selectedContinuity.chapter_index;
            renderAuthorReports();
            focusAuthorPanel("continuity");
          },
        }, {
          label: "评论这个 Diff",
          onClick: () => {
            prefillAuthorCommentAnchor("simulation", String(selectedContinuity.chapter_index));
          },
        }] : []),
      ]
    });
    workGrid.appendChild(continuityCard);

    const compareCard = createAuthorWorkCard({
      title: "Compare Work Card",
      score: selectedCompareChapter?.chapter_index ? `#${selectedCompareChapter.chapter_index}` : "待选择",
      body:
        `${selectedCompareChapter ? `${selectedCompareChapter.chapter_index}. ${selectedCompareChapter.after_title || selectedCompareChapter.chapter_title || selectedCompareChapter.before_title || "-"}\n当前问题 ${(selectedCompareChapter.issue_codes || selectedCompareChapter.issue_codes_added || []).join("/") || "-"} · scene ${selectedCompareChapter.scene_function || "-"}\n下一步 先打开 Compare 看 before-after，再决定是否去 Review 留证据。` : "当前没有可直接对照的章节。\n当前问题 还没有 compare target。\n下一步 先从 Weakest Chapters 或 Continuity Diff 选一个章节。"}`
      ,
      warning: selectedCompareChapter ? "" : "当前还没有稳定的 compare 目标章节。",
      active: Boolean(selectedCompareChapter?.chapter_index && Number(authorState.selectedAuthorContinuityChapterIndex || 0) === Number(selectedCompareChapter.chapter_index)),
      actions: [
        ...(selectedCompareChapter?.chapter_index ? [{
          label: "打开 Compare",
          primary: true,
          onClick: () => {
            authorState.selectedAuthorContinuityChapterIndex = selectedCompareChapter.chapter_index;
            renderAuthorReports();
            jumpToAuthorChapter(selectedCompareChapter.chapter_index, "compare");
          },
        }] : []),
        {
          label: "去 Review 提交证据",
          onClick: () => focusAuthorPanel("diff"),
        },
      ]
    });
    workGrid.appendChild(compareCard);

    dom.authorGuidedFocus.appendChild(workGrid);
    dom.authorGuidedFocus.appendChild(actions);
    return;
  }
  if (!workflow) {
    const hasActiveDraft = Boolean(authorState.activeDraftVersionId);
    if (titleNode) {
      titleNode.textContent = hasActiveDraft ? "先围绕当前 Draft 进入工作状态" : "先定题材，再生成今天要打磨的 Draft";
    }
    if (copyNode) {
      copyNode.textContent = hasActiveDraft
        ? "当前已经有可工作的 Draft。先看摘要，再决定这轮是继续打磨素材，还是直接进入 Simulate。"
        : "如果你还没有工作中的 Draft，就先写 Brief；如果已经有世界设定，可以直接复制当前世界进入作者工作流。";
    }
    const card = document.createElement("article");
    card.className = "list-card author-guided-focus-card";
    card.innerHTML = hasActiveDraft ? `
      <div class="author-guided-kicker">推荐下一步</div>
      <h3>先确认当前 Draft 的健康状态，再决定往哪一段继续推进</h3>
      <p>你已经有一个可工作的 Draft。现在最值当的两件事，是先看当前 Draft 摘要，或者直接进入 Simulate 看 weakest chapters。</p>
      <div class="author-guided-meta">
        <span>当前 Draft ${authorState.activeDraftVersionId}</span>
        <span>适合回流作者重新进入工作状态</span>
      </div>
    ` : `
      <div class="author-guided-kicker">推荐下一步</div>
      <h3>先建立一个可工作的 Draft</h3>
      <p>作者首页只做两件事：确认今天要处理哪一个 Draft，以及决定下一步是写 Brief 还是继续打磨。</p>
      <div class="author-guided-meta">
        <span>如果没有 Draft：先去 Brief</span>
        <span>如果已有世界：直接复制当前世界</span>
      </div>
    `;
    const actions = document.createElement("div");
    actions.className = "composer-actions author-guided-actions";
    if (hasActiveDraft) {
      const detailButton = document.createElement("button");
      detailButton.className = "primary-action";
      detailButton.textContent = "查看 Draft 摘要";
      detailButton.addEventListener("click", () => focusAuthorPanel("draft_detail"));
      const simulateButton = document.createElement("button");
      simulateButton.className = "ghost-action";
      simulateButton.textContent = "打开 Simulate";
      simulateButton.addEventListener("click", () => focusAuthorPanel("simulation"));
      actions.appendChild(detailButton);
      actions.appendChild(simulateButton);
    } else {
      const briefButton = document.createElement("button");
      briefButton.className = "primary-action";
      briefButton.textContent = "打开 Brief";
      briefButton.addEventListener("click", () => focusAuthorPanel("brief"));
      const copyButton = document.createElement("button");
      copyButton.className = "ghost-action";
      copyButton.textContent = "复制当前世界";
      copyButton.addEventListener("click", async () => {
        await createDraftFromCurrentWorld();
      });
      actions.appendChild(briefButton);
      actions.appendChild(copyButton);
    }
    dom.authorGuidedFocus.appendChild(card);
    dom.authorGuidedFocus.appendChild(actions);
    return;
  }
  if (titleNode) {
    titleNode.textContent = workflow.draft_title || "围绕当前 Draft 推进下一阶段";
  }
  if (copyNode) {
    copyNode.textContent = `${authorStageLabel(workflow.stage)} · 推荐动作 ${primaryAction?.label || workflow.recommended_action || "-"}。先处理这一件事，再进入其他深层编辑器。`;
  }
  const blockers = workflow.blockers || [];
  const readiness = workflow.longform_readiness || {};
  const card = document.createElement("article");
  card.className = "list-card author-guided-focus-card";
  card.innerHTML = `
    <div class="author-guided-kicker">推荐下一步</div>
    <h3>${authorRecommendedActionLabel(primaryAction?.action_id || workflow.recommended_action)}</h3>
    <p>${workflow.draft_title || "当前 Draft"} · 当前阶段 ${authorStageLabel(workflow.stage)}。${blockers.length ? `当前 blocker：${blockers[0].message}` : "当前没有 blocker，可以直接推进。"} </p>
    <div class="author-guided-meta">
      <span>推荐入口 ${authorRecommendedWorkspaceLabel(primaryAction?.action_id || workflow.recommended_action)}</span>
      <span>长线 ${workflow.entry_mode === "structured_longform" ? "结构化" : "Quick Brief"} / ${readiness.status || "-"}</span>
      <span>Validation ${workflow.validation_summary?.status || "-"}</span>
      <span>Simulation ${workflow.simulation_summary?.latest_decision || "-"}</span>
    </div>
  `;
  dom.authorGuidedFocus.appendChild(card);
  if (primaryAction) {
    const actions = document.createElement("div");
    actions.className = "composer-actions author-guided-actions";
    const button = document.createElement("button");
    button.className = primaryAction.primary === false ? "ghost-action" : "primary-action";
    button.textContent = primaryAction.label || primaryAction.action_id;
    button.disabled = primaryAction.enabled === false;
    button.title = primaryAction.reason || "";
    button.addEventListener("click", async () => {
      await runAuthorWorkflowAction(primaryAction.action_id);
    });
    actions.appendChild(button);
    if (authorState.activeDraftVersionId) {
      const secondary = document.createElement("button");
      secondary.className = "ghost-action";
      secondary.textContent = "查看当前 Draft 摘要";
      secondary.addEventListener("click", () => focusAuthorPanel("draft_detail"));
      actions.appendChild(secondary);
    }
    dom.authorGuidedFocus.appendChild(actions);
  }
}

function renderAuthorReports() {
  renderAuthorAuthStatus();
  renderAuthorSettingsSummary();
  const currentSimulationReport = currentAuthorSimulationReport();
  dom.authorActiveDraft.textContent = authorState.activeDraftVersionId || "-";
  dom.authorValidationStatus.textContent = authorState.authorValidationReport?.status || (authorState.authorValidationReport?.ok ? "ok" : "未运行");
  dom.authorSimulationChapters.textContent = String(currentSimulationReport?.completed_chapters || 0);
  const saveDraftAccess = authorState.authorAccessSnapshot?.actions?.save_draft || null;
  const briefAccess = authorState.authorAccessSnapshot?.actions?.draft_from_brief || null;
  const simulateAccess = authorState.authorAccessSnapshot?.actions?.simulate || null;
  if (dom.authorBriefAccess) {
    dom.authorBriefAccess.textContent = gatingStatusLabel(briefAccess);
    dom.authorBriefAccess.title = gatingHint(briefAccess);
  }
  if (dom.authorSimulateAccess) {
    dom.authorSimulateAccess.textContent = gatingStatusLabel(simulateAccess);
    dom.authorSimulateAccess.title = gatingHint(simulateAccess);
  }
  if (dom.authorCreateDraftFromBrief) {
    dom.authorCreateDraftFromBrief.disabled = Boolean(briefAccess && !briefAccess.allowed);
    dom.authorCreateDraftFromBrief.title = gatingHint(briefAccess);
  }
  if (dom.authorCreateDraft) {
    dom.authorCreateDraft.disabled = Boolean(saveDraftAccess && !saveDraftAccess.allowed);
    dom.authorCreateDraft.title = gatingHint(saveDraftAccess);
  }
  renderAuthorDraftSectionNav();
  renderAuthorDraftSectionSummary();
  syncAuthorDraftSectionPanels();
  renderAuthorSteeringComposer();
  renderAuthorGuidedFocus();
  renderAuthorWorkflow();
  renderAuthorDraftDetail();
  renderAuthorWorkStudio();
  renderAuthorSimulateSummary();
  renderAuthorReviewSummary();
  renderAuthorRevisionPanels();
  renderAuthorCompare();
  renderAuthorCollaboration();
  clearNode(dom.authorValidationReport);
  const validationPayload = authorState.authorValidationReport || authorState.activeDraftDetail?.validation_report || null;
  const validationDrilldown = authorState.authorValidationReport?.validation_drilldown || authorState.activeDraftDetail?.validation_drilldown || {};
  if (validationPayload) {
    const node = document.createElement("article");
    node.className = "list-card";
    const validation = validationPayload;
    node.innerHTML = `
      <div class="list-card-head">
        <h3>Validation / Submit 结果</h3>
        <span class="list-card-score">${validation.status || (validation.ok ? "ok" : "pending")}</span>
      </div>
      <p class="list-card-body">ok: ${validation.ok ? "true" : "false"}\nerrors: ${(validation.errors || []).length || 0}\nwarnings: ${(validation.warnings || []).length || 0}\n\nblockers:\n${(validationDrilldown.blockers || []).map((item) => `${item.category} · ${item.severity}\n${item.message}\n建议：${item.recommended_action}`).join("\n\n") || (validation.errors || []).join("\n") || "-"}\n\nwarnings:\n${(validationDrilldown.warning_groups || []).map((item) => `${item.category} · ${item.message}\n建议：${item.recommended_action}`).join("\n\n") || (validation.warnings || []).join("\n") || "-"}\n\nnext actions:\n${(validationDrilldown.next_actions || []).join("\n") || "-"}</p>
    `;
    dom.authorValidationReport.appendChild(node);
  } else {
    clearNode(dom.authorValidationReport, "选择一个 draft 后，这里会显示 validation report。");
  }
  clearNode(dom.authorSimulationReport);
  const simulationReport = currentSimulationReport;
  const simulationDrilldown = getSimulationDrilldown();
  if (simulationReport) {
    const topIssues = simulationReport.evaluation_summary?.top_issue_categories || [];
    const failingPacks = simulationReport.top_failing_packs || opsState.opsCrossPackQuality?.top_failing_packs || [];
    const metricDeltas = simulationReport.metric_deltas || {};
    const deltaSummary = simulationReport.cross_pack_summary?.delta_summary || opsState.opsCrossPackQuality?.delta_summary || {};
    const currentDiagnosis = simulationReport.cross_pack_summary?.worlds?.find(
      (item) => item.world_id === authorState.activeDraftDetail?.world_id
    );
    const diffSummary = buildSimulationDiffSummary(authorState.authorPreviousSimulationReport, simulationReport);

    dom.authorSimulationReport.appendChild(
      createListCard({
        title: "Simulation 概览",
        score: simulationReport.ok ? "ok" : "warn",
        body:
          `完成章节 ${simulationReport.completed_chapters || 0} / ${simulationDrilldown.chapter_budget || simulationReport.chapter_budget || "-"} · latest ${simulationReport.latest_decision || "-"}\n` +
          `completion ${simulationDrilldown.completion_ratio !== undefined ? Number(simulationDrilldown.completion_ratio).toFixed(3) : "-"} · stop ${simulationDrilldown.stop_reason || simulationReport.stop_reason || "-"}\n` +
          `pass ${formatPercent(simulationReport.evaluation_summary?.pass_rate)} · rewrite ${formatPercent(simulationReport.evaluation_summary?.rewrite_rate)} · block ${formatPercent(simulationReport.evaluation_summary?.block_rate)}\n` +
          `${currentDiagnosis ? `当前 Draft 诊断：${currentDiagnosis.issue_summary?.dominant_issue || "-"} · ${(currentDiagnosis.issue_summary?.weakest_dimensions || []).map((item) => `${item.name}=${Number(item.value || 0).toFixed(3)}`).join(" / ") || "-"}` : "当前 Draft 诊断：-"}\n` +
          `${Object.keys(metricDeltas).length ? `指标 delta：${Object.entries(metricDeltas).map(([key, value]) => `${key}=${Number(value).toFixed(3)}`).join(" / ")}` : "指标 delta：-"}\n` +
          `${diffSummary ? `与上次 simulation 对比：\n${diffSummary}` : "与上次 simulation 对比：-"}\n` +
          `${typeof deltaSummary.cross_pack_pass_rate_delta === "number" ? `cross-pack pass rate delta: ${deltaSummary.cross_pack_pass_rate_delta >= 0 ? "+" : ""}${deltaSummary.cross_pack_pass_rate_delta.toFixed(3)}` : "cross-pack pass rate delta: -"}`
      })
    );

    dom.authorSimulationReport.appendChild(
      createListCard({
        title: "Issue / Module Drill-down",
        score: `${(simulationDrilldown.issue_histogram || []).length} 类`,
        body:
          `${(simulationDrilldown.issue_histogram || []).length ? `issue histogram:\n${simulationDrilldown.issue_histogram.map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module || "-"}`).join("\n")}` : "issue histogram: -"}\n\n` +
          `${(simulationDrilldown.module_histogram || []).length ? `module histogram:\n${simulationDrilldown.module_histogram.map((item) => `${item.owning_module} · ${item.count} · ${(item.issue_codes || []).join("/") || "-"}`).join("\n")}` : "module histogram: -"}\n\n` +
          `${Object.keys(simulationDrilldown.decision_histogram || {}).length ? `decision histogram:\n${Object.entries(simulationDrilldown.decision_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "decision histogram: -"}\n\n` +
          `${Object.keys(simulationDrilldown.story_phase_histogram || {}).length ? `story phases:\n${Object.entries(simulationDrilldown.story_phase_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "story phases: -"}\n\n` +
          `${Object.keys(simulationDrilldown.scene_function_histogram || {}).length ? `scene functions:\n${Object.entries(simulationDrilldown.scene_function_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "scene functions: -"}\n\n` +
          `${(simulationDrilldown.next_actions || topIssues || []).length ? `next actions:\n${(simulationDrilldown.next_actions || topIssues || []).map((item, index) => `${index + 1}. ${item.issue_code} -> ${item.owning_module}\n建议：${item.fix_hint}`).join("\n\n")}` : "next actions: -"}\n\n` +
          `${simulationDrilldown.quality_pass_summary?.action_histogram?.length ? `quality pass:\nchapters touched ${simulationDrilldown.quality_pass_summary.chapters_touched}\n${simulationDrilldown.quality_pass_summary.action_histogram.map((item) => `${item.action}: ${item.count}`).join("\n")}` : "quality pass: -"}`
      })
    );

    dom.authorSimulationReport.appendChild(
      createListCard({
        title: "Issue Focus Queue",
        score: `${(simulationDrilldown.issue_focus_queue || []).length} 项`,
        body:
          `${(simulationDrilldown.issue_focus_queue || []).map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module || "-"}\n建议：${item.fix_hint || "-"}\n章节：${(item.chapter_targets || []).map((chapter) => `${chapter.chapter_index}.${chapter.chapter_title}(${chapter.scene_function || "-"}/${chapter.decision || "-"})`).join(" / ") || "-"}`).join("\n\n") || "暂无 issue focus queue。"}`
      })
    );
    if ((simulationDrilldown.issue_focus_queue || [])[0]?.chapter_targets?.[0]) {
      const queueActions = document.createElement("div");
      queueActions.className = "composer-actions author-simulate-actions";
      const firstTarget = simulationDrilldown.issue_focus_queue[0].chapter_targets[0];
      const openButton = document.createElement("button");
      openButton.className = "primary-action";
      openButton.textContent = "跳到问题章节";
      openButton.addEventListener("click", () => {
        jumpToAuthorChapter(firstTarget.chapter_index, "simulation");
      });
      const commentButton = document.createElement("button");
      commentButton.className = "ghost-action";
      commentButton.textContent = "评论首个问题章节";
      commentButton.addEventListener("click", () => {
        prefillAuthorCommentAnchor("simulation", String(firstTarget.chapter_index));
      });
      const draftButton = document.createElement("button");
      draftButton.className = "ghost-action";
      draftButton.textContent = "回 Draft Workbench";
      draftButton.addEventListener("click", () => {
        focusAuthorPanel("longform");
      });
      queueActions.appendChild(openButton);
      queueActions.appendChild(commentButton);
      queueActions.appendChild(draftButton);
      dom.authorSimulationReport.appendChild(queueActions);
    }

    dom.authorSimulationReport.appendChild(
      createListCard({
        title: "Weakest Chapters",
        score: `${(simulationDrilldown.weakest_chapters || []).length} 章`,
        body:
          `${(simulationDrilldown.weakest_chapters || []).map((item) => `${item.chapter_index}. ${item.chapter_title || item.chapter_id}\n${item.decision} · score ${Number(item.overall_score || 0).toFixed(3)} · scene ${item.scene_function || "-"}\nissues ${(item.issue_codes || []).join(" / ") || "-"}\nsignals rep ${Number(item.signal_snapshot?.repetition_score || 0).toFixed(3)} · expo ${Number(item.signal_snapshot?.exposition_ratio || 0).toFixed(3)} · hook ${Number(item.signal_snapshot?.hook_quality || 0).toFixed(3)} · detail ${Number(item.signal_snapshot?.concrete_detail_density || 0).toFixed(3)}\nquality pass ${(item.quality_pass_actions || []).join(" / ") || "-"}`).join("\n\n") || "暂无章节级弱项。"}`
      })
    );
    if ((simulationDrilldown.weakest_chapters || [])[0]) {
      const weakestActions = document.createElement("div");
      weakestActions.className = "composer-actions author-simulate-actions";
      const firstWeak = simulationDrilldown.weakest_chapters[0];
      const reviewButton = document.createElement("button");
      reviewButton.className = "primary-action";
      reviewButton.textContent = `查看第 ${firstWeak.chapter_index} 章`;
      reviewButton.addEventListener("click", () => {
        jumpToAuthorChapter(firstWeak.chapter_index, "simulation");
      });
      const compareButton = document.createElement("button");
      compareButton.className = "ghost-action";
      compareButton.textContent = "去 Review 对照";
      compareButton.addEventListener("click", () => {
        jumpToAuthorChapter(firstWeak.chapter_index, "compare");
      });
      const draftButton = document.createElement("button");
      draftButton.className = "ghost-action";
      draftButton.textContent = "回 Draft 调整素材";
      draftButton.addEventListener("click", () => {
        focusAuthorPanel("longform");
      });
      weakestActions.appendChild(reviewButton);
      weakestActions.appendChild(compareButton);
      weakestActions.appendChild(draftButton);
      dom.authorSimulationReport.appendChild(weakestActions);
    }

    dom.authorSimulationReport.appendChild(
      createListCard({
        title: "Chapter Drill-down",
        score: `${(simulationDrilldown.chapter_breakdown || []).length} 章`,
        body:
          `${(simulationDrilldown.chapter_breakdown || []).map((item) => `${item.chapter_index}. ${item.chapter_title || item.chapter_id}\n${item.decision} · score ${Number(item.overall_score || 0).toFixed(3)} · scene ${item.scene_function || "-"}\nissues ${(item.issue_codes || []).join(" / ") || "-"}\nchoices ${(item.choices_preview || []).join(" / ") || "-"}\nquality pass ${(item.quality_pass_actions || []).join(" / ") || "-"}\ncritic signals ${item.critic_signal_count ?? 0}`).join("\n\n") || "暂无 chapter breakdown。"}`
      })
    );
  } else {
    clearNode(dom.authorSimulationReport, "运行 simulation 后，这里会显示 route length、reader leak 与 cost estimate。");
  }
  renderAuthorCreativeCockpit();
  const worldpack = getActiveDraftWorldpack() || {};
  const stylePack = worldpack.narrative_style_pack || {};
  const dialogueBundle = {
    dialogue_realism_policy: worldpack.dialogue_realism_policy || {},
    voice_profiles: worldpack.voice_profiles || stylePack.dialogue?.voice_profiles || {},
    response_cadence_profiles: worldpack.response_cadence_profiles || stylePack.dialogue?.response_profiles || {},
    pressure_response_styles: worldpack.pressure_response_styles || stylePack.dialogue?.pressure_styles || {},
  };
  dom.authorVoiceEditor.value = JSON.stringify(dialogueBundle, null, 2);
  dom.authorActionEditor.value = JSON.stringify(
    worldpack.emotion_action_policies || { default: stylePack.emotion_actions || {} },
    null,
    2
  );
  dom.authorSensoryEditor.value = JSON.stringify(
    worldpack.sensory_grounding_policies || { default: stylePack.sensory_grounding || {} },
    null,
    2
  );
  dom.authorSceneEditor.value = JSON.stringify(
    worldpack.scene_realization_contracts || { default: stylePack.scene_realization || {} },
    null,
    2
  );
  renderStylePacingHookControls();
  renderCharacterEditor();
  renderSceneEditor();
}

async function refreshAuthorSurface() {
  await hydrateAuthorAuthSession();
  const authenticatedAuthorAccountIdValue = String(authorState.authorAuthSession?.identity?.account_id || "").trim();
  const allowAuthorDraftRequests = hasAuthorAuthenticatedSession();
  let activeAuthorAccountIdValue =
    dom.authorAccountId?.value.trim() ||
    authenticatedAuthorAccountIdValue ||
    "";
  if (dom.authorAccountId && !dom.authorAccountId.value.trim() && activeAuthorAccountIdValue) {
    dom.authorAccountId.value = activeAuthorAccountIdValue;
  }
  if (resumeAuthorDeepLinkIfPossible(authenticatedAuthorAccountIdValue)) {
    return;
  }
  ensureAuthorDeepLinkLoginPrompt();
  ensureAuthorDeepLinkAccountSwitchPrompt(authenticatedAuthorAccountIdValue);
  const allowAuthorAccessRequests = allowAuthorDraftRequests;
  const allowReviewerInboxRequests = authorSessionCanReview();
  const showAuthorSettings = shellState.authorWorkspace === "settings";
  const showAuthorReview = shellState.authorWorkspace === "review";
  if (!authorState.authorBriefTemplate) {
    try {
      authorState.authorBriefTemplate = await api("/v1/author/brief-template");
      populateAuthorBriefForm();
    } catch (error) {
      console.warn("brief template unavailable", error);
    }
  }
  if (allowAuthorDraftRequests) {
    const payload = await api("/v1/author/drafts");
    authorState.authorDrafts = payload.drafts;
    if (!authorState.activeDraftVersionId && authorState.authorDrafts.length) {
      authorState.activeDraftVersionId = preferredAuthorDraftVersionId(authorState.authorDrafts);
    }
    if (authorState.activeDraftVersionId) {
      try {
        authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
      } catch (_error) {
        authorState.activeDraftDetail = null;
        authorState.activeDraftVersionId = null;
      }
    } else {
      authorState.activeDraftDetail = null;
    }
  } else {
    authorState.authorDrafts = [];
    authorState.activeDraftDetail = null;
  }
  normalizeAuthorDraftRouteAccount();
  activeAuthorAccountIdValue =
    dom.authorAccountId?.value.trim() ||
    String(authorState.authorAuthSession?.identity?.account_id || "").trim() ||
    "";
  if (resumeAuthorDeepLinkIfPossible(String(authorState.authorAuthSession?.identity?.account_id || "").trim())) {
    return;
  }
  ensureAuthorDeepLinkLoginPrompt();
  ensureAuthorDeepLinkAccountSwitchPrompt(String(authorState.authorAuthSession?.identity?.account_id || "").trim());
  if (allowAuthorDraftRequests) {
    try {
      await refreshAuthorWorks(activeAuthorAccountIdValue);
    } catch (_error) {
      authorState.authorWorks = [];
      authorState.activeWorkId = null;
      authorState.activeWorkDetail = null;
      authorState.activeWorkChapterIndex = null;
      authorState.activeWorkChapterDetail = null;
      authorState.authorWorkDiagnostics = null;
    }
  } else {
    authorState.authorWorks = [];
    authorState.activeWorkId = null;
    authorState.activeWorkDetail = null;
    authorState.activeWorkChapterIndex = null;
    authorState.activeWorkChapterDetail = null;
    authorState.activeWorkChapterDraft = null;
    authorState.activeWorkChapterDirty = false;
    authorState.authorWorkDiagnostics = null;
    authorState.authorWorkQualityGateFailure = null;
  }
  if (authorState.activeDraftVersionId && allowAuthorDraftRequests) {
    try {
      authorState.authorCollaborationSummary = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/collaboration`);
      const availableThreadIds = new Set((authorState.authorCollaborationSummary?.threads || []).map((item) => item.thread_id));
      if (authorState.selectedAuthorThreadId && !availableThreadIds.has(authorState.selectedAuthorThreadId)) {
        authorState.selectedAuthorThreadId = null;
      }
      if (!authorState.selectedAuthorThreadId && availableThreadIds.size) {
        authorState.selectedAuthorThreadId = Array.from(availableThreadIds)[0];
      }
    } catch (error) {
      authorState.authorCollaborationSummary = null;
      authorState.selectedAuthorThreadId = null;
    }
  } else {
    authorState.authorCollaborationSummary = null;
    authorState.selectedAuthorThreadId = null;
  }
  if (dom.authorApprovalReviewer?.value.trim() && !dom.authorInboxReviewerId?.value.trim()) {
    dom.authorInboxReviewerId.value = dom.authorApprovalReviewer.value.trim();
  }
  if (showAuthorSettings && allowReviewerInboxRequests) {
    try {
      await refreshAuthorReviewerInbox();
    } catch (error) {
      authorState.authorReviewerInbox = null;
      authorState.authorReviewerInboxNextCursor = null;
      authorState.authorReviewerInboxHasMore = false;
    }
  } else {
    authorState.authorReviewerInbox = null;
    authorState.authorReviewerInboxNextCursor = null;
    authorState.authorReviewerInboxHasMore = false;
  }
  if (showAuthorSettings) {
    try {
      await refreshAuthorNotificationPreferences();
    } catch (error) {
      authorState.authorNotificationPreferences = null;
    }
  } else {
    authorState.authorNotificationPreferences = null;
  }
  if (activeAuthorAccountIdValue && allowAuthorAccessRequests) {
    try {
      authorState.authorAccessSnapshot = await api(
        `/v1/author/access?account_id=${encodeURIComponent(activeAuthorAccountIdValue)}${
          authorState.activeDraftVersionId ? `&world_version_id=${encodeURIComponent(authorState.activeDraftVersionId)}` : ""
        }`
      );
    } catch (error) {
      authorState.authorAccessSnapshot = null;
    }
  } else {
    authorState.authorAccessSnapshot = null;
  }
  if (activeAuthorAccountIdValue && allowAuthorAccessRequests) {
    try {
      const query = new URLSearchParams();
      query.set("account_id", activeAuthorAccountIdValue);
      if (authorState.activeDraftVersionId) {
        query.set("world_version_id", authorState.activeDraftVersionId);
      }
      authorState.authorWorkflowSummary = await api(`/v1/author/workflow?${query.toString()}`);
      if (!authorState.activeDraftVersionId && authorState.authorWorkflowSummary?.world_version_id) {
        authorState.activeDraftVersionId = authorState.authorWorkflowSummary.world_version_id;
        authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
      }
    } catch (error) {
      authorState.authorWorkflowSummary = null;
    }
  } else {
    authorState.authorWorkflowSummary = null;
  }
  if (activeAuthorAccountIdValue && allowAuthorAccessRequests && !showAuthorReview) {
    try {
      const entitlements = await api(`/v1/reader/entitlements?account_id=${encodeURIComponent(activeAuthorAccountIdValue)}`);
      dom.authorStudioCredits.textContent = String(Number(entitlements.wallets?.studio_credits?.balance || 0).toFixed(0));
      if (dom.authorTier) {
        dom.authorTier.textContent = tierLabel(entitlements.subscription?.tier_id) || entitlements.subscription?.tier_id || "-";
      }
    } catch (error) {
      dom.authorStudioCredits.textContent = "-";
      if (dom.authorTier) {
        dom.authorTier.textContent = "-";
      }
    }
  } else {
    dom.authorStudioCredits.textContent = "-";
    if (dom.authorTier) {
      dom.authorTier.textContent = "-";
    }
  }
  renderAuthorDrafts();
  renderAuthorReports();
}

async function createDraftFromCurrentWorld() {
  if (!readerState.worldId) {
    authorNotice("先选择一个世界。");
    return;
  }
  try {
    const detail = await api(`/v1/library/worlds/${readerState.worldId}`);
    const pack = detail.worldpack;
    pack.version = `${pack.version}-draft-${Date.now()}`;
    pack.manifest.author_id = dom.authorAccountId?.value.trim() || "web_author";
    const draft = await api("/v1/author/drafts", {
      method: "POST",
      body: JSON.stringify({
        worldpack: pack,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "manual_update", label: "从当前世界复制" },
      }),
    });
    authorState.activeDraftVersionId = draft.world_version_id;
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report;
    authorState.authorSimulationReport = null;
    await refreshAuthorSurface();
    await refreshOpsSurfaceIfVisible();
    if (draft.requires_structured_longform) {
      focusAuthorPanel("longform");
      authorNotice(
        `当前 quick brief 只会直接承诺到 100 章；这份 Draft 目标是 ${draft.requested_target_band || draft.requested_target_chapters || ">100"}，需要先进入结构化长篇蓝图补齐 readiness。`,
        "warning"
      );
      return;
    }
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "创建 Draft");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "创建 Draft 失败，请稍后再试。"), "error");
  }
}

async function createDraftFromBrief() {
  const brief = buildAuthorBriefPayload();
  if (!brief.world_title || !brief.core_premise) {
    authorNotice("请至少填写世界标题和故事 brief。");
    return;
  }
  try {
    const draft = await api("/v1/author/drafts/from-brief", {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    authorState.activeDraftVersionId = draft.world_version_id;
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report;
    authorState.authorSimulationReport = null;
    await refreshAuthorSurface();
    await refreshOpsSurfaceIfVisible();
    if (draft.requires_structured_longform) {
      focusAuthorPanel("longform");
      authorNotice(
        `当前 quick brief 只会直接承诺到 100 章；这份 Draft 目标是 ${draft.requested_target_band || draft.requested_target_chapters || ">100"}，需要先进入结构化长篇蓝图补齐 readiness。`,
        "warning"
      );
      return;
    }
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      authorNotice(`当前不能创建 Draft：${accessReasonLabel(detail.reason)}。需要 ${detail.required_display_name || tierLabel(detail.required_tier)}，当前 ${detail.wallet_type || "-"} 余额 ${Number(detail.balance || 0).toFixed(0)}。`);
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "生成 Draft 失败，请稍后再试。"), "error");
  }
}

async function saveCapabilityAssets() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  worldpack.narrative_style_pack = worldpack.narrative_style_pack || {};
  try {
    const dialogueBundle = JSON.parse(dom.authorVoiceEditor.value || "{}");
    worldpack.dialogue_realism_policy = dialogueBundle.dialogue_realism_policy || {};
    worldpack.voice_profiles = dialogueBundle.voice_profiles || {};
    worldpack.response_cadence_profiles = dialogueBundle.response_cadence_profiles || {};
    worldpack.pressure_response_styles = dialogueBundle.pressure_response_styles || {};
    worldpack.emotion_action_policies = JSON.parse(dom.authorActionEditor.value || "{}");
    worldpack.sensory_grounding_policies = JSON.parse(dom.authorSensoryEditor.value || "{}");
    worldpack.scene_realization_contracts = JSON.parse(dom.authorSceneEditor.value || "{}");
    worldpack.narrative_style_pack.dialogue = {
      ...worldpack.dialogue_realism_policy,
      voice_profiles: worldpack.voice_profiles,
      response_profiles: worldpack.response_cadence_profiles,
      pressure_styles: worldpack.pressure_response_styles,
    };
    applyStylePacingHookControls(worldpack);
    worldpack.narrative_style_pack.emotion_actions = Object.values(worldpack.emotion_action_policies)[0] || {};
    worldpack.narrative_style_pack.sensory_grounding = Object.values(worldpack.sensory_grounding_policies)[0] || {};
    worldpack.narrative_style_pack.scene_realization = Object.values(worldpack.scene_realization_contracts)[0] || {};
  } catch (error) {
    authorNotice("能力配置 JSON 解析失败，请检查格式。", "error");
    return;
  }
  try {
    const draft = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "capability_editor", label: "保存能力配置" },
      }),
    });
    authorState.activeDraftVersionId = draft.world_version_id || authorState.activeDraftVersionId;
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report || authorState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    await refreshOpsSurfaceIfVisible();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存能力配置");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存能力配置失败，请稍后再试。"), "error");
  }
}

async function saveCharacterCard() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  const characters = worldpack.characters || [];
  if (!characters.length) {
    authorNotice("当前 draft 没有可编辑角色。");
    return;
  }
  const index = Math.min(selectedCharacterIndex(), characters.length - 1);
  const character = characters[index];
  character.display_name = dom.authorCharacterName.value.trim();
  character.role = dom.authorCharacterRole.value.trim() || character.role;
  character.destiny_contract = character.destiny_contract || {};
  character.destiny_contract.life_theme = dom.authorCharacterLifeTheme.value.trim();
  character.wound_profile = character.wound_profile || {};
  character.wound_profile.core_wound = dom.authorCharacterCoreWound.value.trim();
  character.wound_profile.public_self = dom.authorCharacterPublicSelf.value.trim();
  character.wound_profile.shadow_desire = dom.authorCharacterShadowDesire.value.trim();
  character.vow_profile = character.vow_profile || {};
  character.vow_profile.vows = dom.authorCharacterVows.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

  try {
    const draft = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        change_context: buildDraftChangeContext("character_editor", "保存角色卡", "character_card"),
      }),
    });
    syncAuthorRepairLoopHintFromDraft(draft, "character_card");
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report || authorState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存角色卡");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存角色卡失败，请稍后再试。"), "error");
  }
}

async function saveSceneBlueprint() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  const scenes = worldpack.scene_blueprints || [];
  if (!scenes.length) {
    authorNotice("当前 draft 没有可编辑场景。");
    return;
  }
  const index = Math.min(selectedSceneIndex(), scenes.length - 1);
  const scene = scenes[index];
  scene.scene_id = dom.authorSceneId.value.trim() || scene.scene_id;
  scene.scene_function = dom.authorSceneFunction.value.trim() || scene.scene_function;
  scene.required_roles = dom.authorSceneRequiredRoles.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  scene.beats_template = dom.authorSceneBeats.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

  try {
    const draft = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        change_context: buildDraftChangeContext("scene_editor", "保存场景蓝图", "scene_blueprint"),
      }),
    });
    syncAuthorRepairLoopHintFromDraft(draft, "scene_blueprint");
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report || authorState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存场景蓝图");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存场景蓝图失败，请稍后再试。"), "error");
  }
}

async function bootstrapLongformWorkbench() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  try {
    const draft = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/longform-bootstrap`, {
      method: "POST",
      body: JSON.stringify({
        account_id: dom.authorAccountId?.value.trim() || "web_author",
      }),
    });
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report || authorState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "生成 Longform Plan");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "生成 Longform Plan 失败，请稍后再试。"), "error");
  }
}

async function saveLongformWorkbench() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  if (!activeWorldpack.series_plan || !(activeWorldpack.volume_plans || []).length || !(activeWorldpack.arc_plans || []).length) {
    authorNotice("当前 draft 还没有 longform plan，请先点击 “生成 Longform Plan”。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  const volumePlans = worldpack.volume_plans || [];
  const arcPlans = worldpack.arc_plans || [];
  const selectedVolume = volumePlans.find((item) => item.volume_id === authorState.selectedAuthorVolumeId) || volumePlans[0];
  const selectedArc = arcPlans.find((item) => item.arc_id === authorState.selectedAuthorArcId) || arcPlans.find((item) => item.volume_id === selectedVolume?.volume_id);
  worldpack.series_plan = worldpack.series_plan || {};
  worldpack.series_plan.title = dom.authorSeriesTitle?.value.trim() || worldpack.series_plan.title;
  worldpack.series_plan.theme_statement = dom.authorSeriesTheme?.value.trim() || "";
  worldpack.series_plan.total_volume_target = Math.max(volumePlans.length || 1, Number(dom.authorSeriesTotalVolumes?.value || worldpack.series_plan.total_volume_target || volumePlans.length || 1));
  worldpack.series_plan.total_chapter_target = Math.max(
    (volumePlans || []).reduce((sum, item) => sum + Math.max(1, Number(item.target_chapters || 1)), 0),
    Number(dom.authorSeriesTotalChapters?.value || worldpack.series_plan.total_chapter_target || 1)
  );
  worldpack.series_plan.target_word_count = Math.max(1000, Number(dom.authorSeriesTargetWords?.value || worldpack.series_plan.target_word_count || 1000));
  try {
    worldpack.series_storyline_contract = JSON.parse(dom.authorStorylineContract?.value || "{}");
    worldpack.character_memory_profiles = JSON.parse(dom.authorCharacterMemoryProfiles?.value || "{}");
    worldpack.steering_guardrails = JSON.parse(dom.authorSteeringGuardrails?.value || "{}");
  } catch (error) {
    authorNotice("Longform contract JSON 解析失败，请检查 Storyline / Character Memory / Guardrails。", "error");
    return;
  }
  if (selectedVolume) {
    selectedVolume.title = dom.authorVolumeTitle?.value.trim() || selectedVolume.title;
    selectedVolume.goal = dom.authorVolumeGoal?.value.trim() || "";
    selectedVolume.target_chapters = Math.max(1, Number(dom.authorVolumeTargetChapters?.value || selectedVolume.target_chapters || 1));
    selectedVolume.climax_definition = dom.authorVolumeClimax?.value.trim() || "";
    selectedVolume.end_state = dom.authorVolumeEndState?.value.trim() || "";
  }
  if (selectedArc) {
    selectedArc.title = dom.authorArcTitle?.value.trim() || selectedArc.title;
    selectedArc.goal = dom.authorArcGoal?.value.trim() || "";
    selectedArc.conflict = dom.authorArcConflict?.value.trim() || "";
    selectedArc.target_chapters = Math.max(1, Number(dom.authorArcTargetChapters?.value || selectedArc.target_chapters || 1));
    selectedArc.reveal_budget = Math.max(0, Number(dom.authorArcRevealBudget?.value || selectedArc.reveal_budget || 0));
    selectedArc.payoff_targets = parseMultilineList(dom.authorArcPayoffTargets?.value || "");
    selectedArc.completion_conditions = parseMultilineList(dom.authorArcCompletionConditions?.value || "");
    selectedArc.chapter_tasks = normalizeLongformArcTasks(selectedArc, worldpack.chapter_budget_policy || {});
    const selectedTask = selectedArc.chapter_tasks.find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) || selectedArc.chapter_tasks[0];
    if (selectedTask) {
      selectedTask.duty_type = dom.authorTaskDuty?.value || selectedTask.duty_type;
      selectedTask.objective = dom.authorTaskObjective?.value.trim() || "";
      selectedTask.target_words = Math.max(500, Number(dom.authorTaskTargetWords?.value || selectedTask.target_words || 2000));
      selectedTask.reveal_budget = Math.max(0, Number(dom.authorTaskRevealBudget?.value || selectedTask.reveal_budget || 0));
      selectedTask.promise_actions = parseMultilineList(dom.authorTaskPromiseActions?.value || "");
      selectedTask.promise_targets = parseMultilineList(dom.authorTaskPromiseTargets?.value || "");
      selectedTask.allow_terminal = Boolean(dom.authorTaskAllowTerminal?.checked);
    }
  }

  try {
    const draft = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        change_context: buildDraftChangeContext("longform_editor", "保存长篇规划", "chapter_task"),
      }),
    });
    syncAuthorRepairLoopHintFromDraft(draft, "chapter_task");
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    authorState.selectedAuthorRevisionIndex = null;
    authorState.authorValidationReport = draft.validation_report || authorState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存长篇规划");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存长篇规划失败，请稍后再试。"), "error");
  }
}

async function savePromiseStateWorkbench() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const promiseId = authorState.selectedAuthorPromiseId || dom.authorPromiseSelect?.value || "";
  if (!promiseId) {
    authorNotice("先选择一条 Promise。");
    return;
  }
  const mapping = getSeriesVolumeArcPromiseMapping();
  const taskLinking = getChapterTaskSimulationLinking();
  const selectedArc = (mapping.arcs || []).find((item) => item.arc_id === authorState.selectedAuthorArcId) || null;
  const selectedTask =
    (taskLinking.task_links || []).find((item) => item.chapter_task_id === authorState.selectedAuthorTaskId) || null;
  const selectedPromise =
    (getPromiseStateWorkbench().editable_promises || []).find((item) => item.promise_id === promiseId) || null;
  try {
    await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/promise-state`, {
      method: "POST",
      body: JSON.stringify({
        promise_id: promiseId,
        editor_state: dom.authorPromiseState?.value || "",
        notes: dom.authorPromiseNotes?.value || "",
        chapter_index: Number(selectedPromise?.last_seen_chapter || selectedPromise?.first_seen_chapter || 0) || null,
        chapter_task_id: selectedTask?.chapter_task_id || null,
        arc_id: selectedArc?.arc_id || selectedTask?.arc_id || null,
        volume_id: authorState.selectedAuthorVolumeId || selectedTask?.volume_id || null,
        account_id: dom.authorAccountId?.value.trim() || "web_author",
      }),
    });
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    await refreshAuthorSurface();
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存 Promise 状态");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存 Promise 状态失败，请稍后再试。"), "error");
  }
}

async function saveContinuityOverrideWorkbench() {
  if (!authorState.activeDraftVersionId) {
    authorNotice("先选择一个 draft。");
    return;
  }
  const chapterIndex = Number(authorState.selectedAuthorContinuityChapterIndex || dom.authorContinuityChapterSelect?.value || 0);
  if (!chapterIndex) {
    authorNotice("先选择一个 continuity chapter。");
    return;
  }
  const continuityCandidate =
    (getContinuityOverrideWorkbench().candidate_chapters || []).find((item) => Number(item.chapter_index || 0) === chapterIndex) || null;
  const selectedTask =
    (getChapterTaskSimulationLinking().task_links || []).find((item) =>
      (item.linked_chapters || []).some((chapter) => Number(chapter.chapter_index || 0) === chapterIndex)
    ) || null;
  try {
    await api(`/v1/author/drafts/${authorState.activeDraftVersionId}/continuity-override`, {
      method: "POST",
      body: JSON.stringify({
        account_id: dom.authorAccountId?.value.trim() || "web_author",
        chapter_index: chapterIndex,
        override_state: dom.authorContinuityOverrideState?.value || "",
        notes: dom.authorContinuityOverrideNotes?.value || "",
        issue_scope: parseMultilineList(dom.authorContinuityIssueScope?.value || ""),
        chapter_task_id: selectedTask?.chapter_task_id || continuityCandidate?.chapter_task_id || null,
        arc_id: selectedTask?.arc_id || continuityCandidate?.arc_id || null,
        volume_id: selectedTask?.volume_id || continuityCandidate?.volume_id || null,
      }),
    });
    authorState.activeDraftDetail = await api(`/v1/author/drafts/${authorState.activeDraftVersionId}`);
    await refreshAuthorSurface();
    focusAuthorPanel("compare");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存 Continuity Override");
      return;
    }
    authorNotice(formatAuthorApiErrorMessage(error, "保存 Continuity Override 失败，请稍后再试。"), "error");
  }
}

function jumpToSelectedCompareChapter() {
  const chapterIndex = Number(authorState.selectedAuthorContinuityChapterIndex || dom.authorContinuityChapterSelect?.value || 0);
  if (!chapterIndex) {
    authorNotice("当前没有可跳转的章节对照。");
    return;
  }
  jumpToAuthorChapter(chapterIndex, "compare");
}

function commentSelectedContinuityChapter() {
  const chapterIndex = Number(authorState.selectedAuthorContinuityChapterIndex || dom.authorContinuityChapterSelect?.value || 0);
  if (!chapterIndex) {
    authorNotice("当前没有可评论的章节。");
    return;
  }
  prefillAuthorCommentAnchor("simulation", String(chapterIndex));
}

function jumpToSelectedPromiseChapter() {
  const selectedPromise =
    (getPromiseStateWorkbench().editable_promises || []).find((item) => item.promise_id === authorState.selectedAuthorPromiseId) || null;
  const chapterIndex = Number(selectedPromise?.last_seen_chapter || selectedPromise?.first_seen_chapter || 0);
  if (!chapterIndex) {
    authorNotice("当前 Promise 还没有可跳转的 simulation chapter。");
    return;
  }
  jumpToAuthorChapter(chapterIndex, "simulation");
}

function commentSelectedPromise() {
  const selectedPromise =
    (getPromiseStateWorkbench().editable_promises || []).find((item) => item.promise_id === authorState.selectedAuthorPromiseId) || null;
  if (!selectedPromise?.anchor?.anchor_key) {
    authorNotice("当前 Promise 还没有可评论的 anchor。");
    return;
  }
  prefillAuthorCommentAnchor(selectedPromise.anchor.anchor_type || "simulation", String(selectedPromise.anchor.anchor_key));
}

let authorWorkspaceEventsBound = false;
let authorWorkspaceInitialized = false;

function bindAuthorWorkspaceEvents() {
  if (authorWorkspaceEventsBound) return;
  authorWorkspaceEventsBound = true;

  dom.authorGenrePreset?.addEventListener("change", applyAuthorPresetDefaults);
  dom.authorCharacterSelect?.addEventListener("change", renderCharacterEditor);
  dom.authorSceneSelect?.addEventListener("change", renderSceneEditor);
  dom.authorVolumeSelect?.addEventListener("change", () => {
    authorState.selectedAuthorVolumeId = dom.authorVolumeSelect.value || null;
    authorState.selectedAuthorArcId = null;
    renderLongformWorkbench();
  });
  dom.authorArcSelect?.addEventListener("change", () => {
    authorState.selectedAuthorArcId = dom.authorArcSelect.value || null;
    authorState.selectedAuthorTaskId = null;
    if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
    if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
    renderLongformWorkbench();
  });
  dom.authorTaskSelect?.addEventListener("change", () => {
    authorState.selectedAuthorTaskId = dom.authorTaskSelect.value || null;
    if (dom.authorTaskBulkIssues) dom.authorTaskBulkIssues.value = "";
    if (dom.authorTaskBulkNotes) dom.authorTaskBulkNotes.value = "";
    renderLongformWorkbench();
  });
  dom.authorTaskSplitTargets?.addEventListener("click", splitSelectedTaskPromiseTargets);
  dom.authorTaskMergeObserved?.addEventListener("click", mergeObservedPromisesIntoTargets);
  dom.authorTaskApplyRewrite?.addEventListener("click", applySelectedTaskRewritePrefill);
  dom.authorExportRewritePatch?.addEventListener("click", exportRewritePatchPreview);
  dom.authorPromiseSelect?.addEventListener("change", () => {
    authorState.selectedAuthorPromiseId = dom.authorPromiseSelect.value || null;
    renderPromiseLedgerWorkbench();
  });
  dom.authorContinuityChapterSelect?.addEventListener("change", () => {
    authorState.selectedAuthorContinuityChapterIndex = Number(dom.authorContinuityChapterSelect.value || 0) || null;
    renderContinuityDiffWorkbench();
    renderAuthorCompare();
  });
  dom.authorCreateDraft?.addEventListener("click", createDraftFromCurrentWorld);
  dom.authorCreateDraftFromBrief?.addEventListener("click", createDraftFromBrief);
  dom.authorRefresh?.addEventListener("click", async () => {
    if (!confirmAuthorWorkDiscard("当前章节还有未保存改动，刷新创作台会重新拉取服务器数据。确认继续吗？")) {
      return;
    }
    if (isAuthorWorkDraftDirty()) {
      discardAuthorWorkDraft();
    }
    await refreshAuthorSurface();
  });
  window.addEventListener("beforeunload", (event) => {
    if (!isAuthorWorkDraftDirty()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  dom.authorAuthRegister?.addEventListener("click", async () => {
    try {
      await registerAuthorAuthIdentity();
    } catch (error) {
      authorNotice(describeAuthError(error, "注册暂时失败，请稍后重试。"), "error");
    }
  });
  dom.authorAuthLogin?.addEventListener("click", async () => {
    try {
      await loginAuthorAuthIdentity();
    } catch (error) {
      const detail = parseErrorDetail(error) || {};
      authorNotice(describeAuthError(error, "登录暂时失败，请稍后重试。"), detail.code === "auth_email_unverified" ? "warning" : "error");
    }
  });
  dom.authorAuthLogout?.addEventListener("click", logoutAuthorAuthIdentity);
  dom.authorSaveStyleControls?.addEventListener("click", saveCapabilityAssets);
  dom.authorSaveCharacter?.addEventListener("click", saveCharacterCard);
  dom.authorSaveScene?.addEventListener("click", saveSceneBlueprint);
  dom.authorBootstrapLongform?.addEventListener("click", bootstrapLongformWorkbench);
  dom.authorSaveLongform?.addEventListener("click", saveLongformWorkbench);
  dom.authorSavePromiseState?.addEventListener("click", savePromiseStateWorkbench);
  dom.authorJumpPromiseChapter?.addEventListener("click", jumpToSelectedPromiseChapter);
  dom.authorCommentPromise?.addEventListener("click", commentSelectedPromise);
  dom.authorSaveContinuityOverride?.addEventListener("click", saveContinuityOverrideWorkbench);
  dom.authorJumpCompareChapter?.addEventListener("click", jumpToSelectedCompareChapter);
  dom.authorCommentContinuity?.addEventListener("click", commentSelectedContinuityChapter);
  dom.authorTaskBulkApply?.addEventListener("click", bulkApplyTaskToSimulation);
  dom.authorRunCheckpointResimulate?.addEventListener("click", runCheckpointAwareResimulate);
  dom.authorRunSteeredSimulation?.addEventListener("click", runSteeredSimulation);
  dom.authorClearSteering?.addEventListener("click", () => {
    clearAuthorSteeringComposer();
    renderAuthorSteeringComposer();
  });
  dom.authorSaveCapabilities?.addEventListener("click", saveCapabilityAssets);
  dom.authorRefreshReviewerInbox?.addEventListener("click", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorSearchReviewerInbox?.addEventListener("click", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorLoadMoreReviewerInbox?.addEventListener("click", async () => {
    if (!authorState.authorReviewerInboxNextCursor) return;
    await refreshAuthorReviewerInbox({ append: true, cursor: authorState.authorReviewerInboxNextCursor });
    renderAuthorReports();
  });
  dom.authorInboxReviewerId?.addEventListener("change", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorInboxStatusFilter?.addEventListener("change", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorInboxWorldVersionFilter?.addEventListener("change", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorInboxNotificationTypeFilter?.addEventListener("change", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorInboxBlockingOnly?.addEventListener("change", async () => {
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorInboxSearch?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    await refreshAuthorReviewerInbox();
    renderAuthorReports();
  });
  dom.authorBulkReadVisible?.addEventListener("click", async () => {
    await bulkUpdateAuthorNotificationStatus("read");
  });
  dom.authorBulkArchiveVisible?.addEventListener("click", async () => {
    await bulkUpdateAuthorNotificationStatus("archived");
  });
  dom.authorAddDraftWatcher?.addEventListener("click", addAuthorDraftWatcher);
  dom.authorRemoveDraftWatcher?.addEventListener("click", removeAuthorDraftWatcher);
  dom.authorRefreshNotificationPreferences?.addEventListener("click", async () => {
    await refreshAuthorNotificationPreferences();
    renderAuthorReports();
  });
  dom.authorSaveNotificationPreference?.addEventListener("click", saveAuthorNotificationPreference);
  dom.authorNotificationPrefType?.addEventListener("change", () => {
    syncAuthorNotificationPreferenceInputs();
  });
  dom.authorAccountId?.addEventListener("change", () => {
    if (dom.authorAuthActorId && !dom.authorAuthActorId.value.trim()) {
      dom.authorAuthActorId.value = dom.authorAccountId.value.trim();
    }
  });
  dom.authorApprovalReviewer?.addEventListener("change", () => {
    if (dom.authorInboxReviewerId && !dom.authorInboxReviewerId.value.trim()) {
      dom.authorInboxReviewerId.value = dom.authorApprovalReviewer.value.trim();
    }
  });
  dom.authorCreateCommentThread?.addEventListener("click", createAuthorCommentThread);
  dom.authorRequestApproval?.addEventListener("click", requestAuthorApproval);
  dom.authorApproveDraft?.addEventListener("click", () => decideAuthorApproval("approved"));
  dom.authorRequestChanges?.addEventListener("click", () => decideAuthorApproval("changes_requested"));
}

function initializeAuthorWorkspaceRuntime() {
  if (authorWorkspaceInitialized) return;
  authorWorkspaceInitialized = true;
  bindAuthorWorkspaceEvents();
  restoreAuthorAuthSession();
  renderAuthorAuthStatus();
}



  return {
    authorStageLabel,
    focusAuthorPanel,
    prefillAuthorCommentAnchor,
    jumpToAuthorChapter,
    activeAuthorReviewerId,
    activeAuthorActorId,
    activeAuthorActorRole,
    currentAuthorInboxFilters,
    authorCollaborationHeaders,
    selectAuthorThread,
    mergeAuthorReviewerInbox,
    syncAuthorNotificationPreferenceInputs,
    persistAuthorAuthSession,
    restoreAuthorAuthSession,
    renderAuthorAuthStatus,
    refreshAuthorReviewerInbox,
    updateAuthorThreadStatusInline,
    updateAuthorNotificationStatus,
    bulkUpdateAuthorNotificationStatus,
    decideAuthorApprovalForWorld,
    addAuthorThreadWatcher,
    removeAuthorThreadWatcher,
    replyToSelectedAuthorThread,
    addAuthorDraftWatcher,
    removeAuthorDraftWatcher,
    refreshAuthorNotificationPreferences,
    saveAuthorNotificationPreference,
    registerAuthorAuthIdentity,
    loginAuthorAuthIdentity,
    hydrateAuthorAuthSession,
    logoutAuthorAuthIdentity,
    validateDraftVersion,
    simulateDraftVersion,
    submitDraftVersion,
    createAuthorCommentThread,
    requestAuthorApproval,
    decideAuthorApproval,
    runAuthorWorkflowAction,
    populateAuthorBriefForm,
    applyAuthorPresetDefaults,
    buildAuthorBriefPayload,
    getActiveDraftCharacters,
    getActiveDraftScenes,
    getActiveSeriesPlan,
    getActiveVolumePlans,
    getActiveArcPlans,
    applyDraftWorldpackMutation,
    resequenceArcOrders,
    reorderArcWithinVolume,
    reorderTaskWithinArc,
    moveTaskAcrossArcs,
    selectedCharacterIndex,
    selectedSceneIndex,
    renderAuthorDraftDetail,
    renderCharacterEditor,
    renderSceneEditor,
    renderLongformWorkbench,
    renderPromiseLedgerWorkbench,
    renderSeriesVolumeArcPromiseMapping,
    renderChapterTaskSimulationLinking,
    renderRewritePatchPreview,
    renderSimulationDiffCheckpoint,
    exportRewritePatchPreview,
    runCheckpointAwareResimulate,
    splitSelectedTaskPromiseTargets,
    mergeObservedPromisesIntoTargets,
    applySelectedTaskRewritePrefill,
    bulkApplyTaskToSimulation,
    openAuthorCharacterAsset,
    openAuthorSceneAsset,
    openAuthorTaskAsset,
    openAuthorPriorityAsset,
    runSteeredSimulation,
    prefillAuthorSteeringFromChoice,
    renderContinuityDiffWorkbench,
    parseMultilineList,
    splitPromiseTargetList,
    normalizeLongformArcTasks,
    formatMultilineList,
    parseLabelMap,
    formatLabelMap,
    parseSceneHooks,
    formatSceneHooks,
    renderStylePacingHookControls,
    applyStylePacingHookControls,
    buildSimulationDiffSummary,
    renderAuthorRevisionPanels,
    renderAuthorSteeringComposer,
    renderAuthorCreativeCockpit,
    renderAuthorDrafts,
    renderAuthorWorkflow,
    renderAuthorReports,
    renderAuthorCompare,
    renderAuthorCollaboration,
    refreshAuthorSurface,
    createDraftFromCurrentWorld,
    createDraftFromBrief,
    bindAuthorWorkspaceEvents,
    initializeAuthorWorkspaceRuntime,
    saveCapabilityAssets,
    saveCharacterCard,
    saveSceneBlueprint,
    bootstrapLongformWorkbench,
    saveLongformWorkbench,
    savePromiseStateWorkbench,
    saveContinuityOverrideWorkbench,
    jumpToSelectedCompareChapter,
    commentSelectedContinuityChapter,
    jumpToSelectedPromiseChapter,
    commentSelectedPromise
  };
})();
