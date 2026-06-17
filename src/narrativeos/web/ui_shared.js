// UI and transport helpers shared across shell, reader, author, and ops runtimes.

var UIShared = (() => {
  const dom = ShellDOM;
  class ApiError extends Error {
    constructor({ status, message, detail = null, code = null, actionHint = null, retryable = false, source = "api" }) {
      super(message || "请求失败");
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
      this.code = code;
      this.action_hint = actionHint;
      this.retryable = retryable;
      this.source = source;
    }
  }

  function safeText(value, fallback = "-") {
    if (value === undefined || value === null || value === "") return fallback;
    return String(value);
  }

  const DISPLAY_REPLACEMENTS = [
    [/Reader Workspace/g, "阅读区域"],
    [/Author Workspace/g, "创作区域"],
    [/Ops Workspace/g, "运营区域"],
    [/Review Queue/g, "审核队列"],
    [/Release Workspace/g, "发布台"],
    [/Content Release Workspace/g, "内容发布台"],
    [/Dashboard/g, "总览"],
    [/Account Investigation/g, "账户排查"],
    [/Alerts & Governance/g, "告警治理"],
    [/Learned Dashboard/g, "学习层总览"],
    [/Learned Impact/g, "学习层影响"],
    [/Learned Cadence/g, "学习层节奏"],
    [/Learned Data Ops/g, "学习数据运营"],
    [/Shadow Candidate Compare/g, "影子候选对照"],
    [/Evaluator Promotion Gate/g, "评估器晋升门"],
    [/Reranker Promotion Gate/g, "重排器晋升门"],
    [/Human Review Coverage/g, "人工审阅覆盖"],
    [/Review Backlog/g, "审核待办"],
    [/Quick Capture Review/g, "快速补录审阅"],
    [/Last Action Impact/g, "最近动作影响"],
    [/Review History/g, "审核历史"],
    [/Issue Focus Queue/g, "问题队列"],
    [/Issue \/ Module Drill-down/g, "问题 / 模块拆解"],
    [/Weakest Chapters/g, "重点问题章节"],
    [/Chapter Drill-down/g, "章节拆解"],
    [/Longform Plan Status/g, "长篇规划状态"],
    [/Promise Ledger Summary/g, "承诺账本摘要"],
    [/Selected Promise/g, "当前承诺"],
    [/Open Promises/g, "未收回承诺"],
    [/Recently Closed/g, "最近回收"],
    [/Collaboration Summary/g, "协作摘要"],
    [/Assignee Queues/g, "处理人队列"],
    [/Draft Watchers/g, "关注人"],
    [/Latest Notifications/g, "最新通知"],
    [/Reviewer Inbox Summary/g, "审阅收件箱摘要"],
    [/Inbox by Draft/g, "按草稿查看收件箱"],
    [/Continuity Work Card/g, "连续性工作卡"],
    [/Compare Work Card/g, "对照工作卡"],
    [/Chapter Task Work Card/g, "章节任务工作卡"],
    [/Simulation freshness/g, "诊断新鲜度"],
    [/\bthread_assigned\b/g, "分配给我"],
    [/\bthread_mentioned\b/g, "提到我"],
    [/\bthread_updated\b/g, "线程更新"],
    [/\bapproval_requested\b/g, "收到审阅请求"],
    [/\bapproval_decision\b/g, "审阅结果"],
    [/\badvance_plot\b/g, "推进主线"],
    [/\badvance_relationship\b/g, "推进关系"],
    [/\bresolve_promise\b/g, "回收承诺"],
    [/\bexpand_world\b/g, "扩展世界"],
    [/\bpace_breath\b/g, "节奏缓冲"],
    [/\bdeliver_climax\b/g, "交付高潮"],
    [/\bplan_payoff\b/g, "计划回收"],
    [/\bresolved_intentional\b/g, "已刻意收束"],
    [/\baccepted_tradeoff\b/g, "接受折中"],
    [/\bneeds_rewrite\b/g, "需要重写"],
    [/\bintentional\b/g, "刻意保留"],
    [/\bwatch\b/g, "持续关注"],
    [/\bdefer\b/g, "暂缓处理"],
    [/\bescalate\b/g, "升级处理"],
    [/\brequested\b/g, "已发起"],
    [/\bsubmitted\b/g, "已提交"],
    [/\bapproved\b/g, "已通过"],
    [/\bresolved\b/g, "已解决"],
    [/\bdismissed\b/g, "已关闭"],
    [/\bescalated\b/g, "已升级"],
    [/\bpublished\b/g, "已发布"],
    [/\brolled_back\b/g, "已回滚"],
    [/\bpending\b/g, "待处理"],
    [/\bactive\b/g, "处理中"],
    [/\bunread\b/g, "未读"],
    [/\bopen\b/g, "待处理"],
    [/\bnone\b/g, "无"],
    [/\byes\b/g, "是"],
    [/\bno\b/g, "否"],
    [/\bdraft\b/g, "草稿"],
    [/\brevision\b/g, "版本"],
    [/\bdiff\b/g, "差异"],
    [/\bcompare\b/g, "对照"],
    [/\bsimulation\b/g, "诊断"],
    [/\bcheckpoint\b/g, "检查点"],
    [/\btask\b/g, "任务"],
    [/\bpromise\b/g, "承诺"],
    [/\bworkflow\b/g, "工作流"],
    [/\bworld_version\b/g, "世界版本"],
    [/\bworld\b/g, "世界"],
    [/\baccount\b/g, "账户"],
    [/\breviewer\b/g, "审阅人"],
    [/\bapproval\b/g, "审阅"],
    [/\bprovider\b/g, "通道"],
    [/\bstatus\b/g, "状态"],
    [/\bsummary\b/g, "摘要"],
    [/\bnext action\b/gi, "下一步动作"],
  ];

  function localizeDisplayText(value) {
    if (value === undefined || value === null) return "";
    let text = String(value);
    for (const [pattern, replacement] of DISPLAY_REPLACEMENTS) {
      text = text.replace(pattern, replacement);
    }
    return text;
  }

  function clearStatusBanner() {
    if (!dom.shellStatusBanner) return;
    dom.shellStatusBanner.textContent = "";
    dom.shellStatusBanner.className = "status-banner is-hidden";
  }

  function sanitizePublicMessage(message, kind = "info") {
    const text = String(message || "");
    if (shellState?.debug) return text;
    const engineeringPattern = /TypeError|ReferenceError|SyntaxError|is not a function|HTTP \d{3}|Traceback|stack trace|actor_id|session_id|world_id|provider|token|JSON|checkout_session_id/i;
    if (!engineeringPattern.test(text)) return text;
    if (kind === "error") return "页面正在更新，请刷新后重试。";
    if (kind === "warning") return "当前操作暂时不可用，请稍后重试。";
    return "页面信息已更新。";
  }

  function showStatusBanner(message, kind = "info") {
    if (!dom.shellStatusBanner) return;
    const safeMessage = sanitizePublicMessage(message, kind);
    dom.shellStatusBanner.textContent = safeMessage;
    dom.shellStatusBanner.className = `status-banner status-banner--${kind}`;
    if (dom.shellLiveRegion) {
      dom.shellLiveRegion.textContent = safeMessage;
    }
  }

  function emitToast(message, kind = "info") {
    if (!dom.shellToastStack) return;
    const toast = document.createElement("div");
    toast.className = `toast toast--${kind}`;
    toast.textContent = sanitizePublicMessage(message, kind);
    dom.shellToastStack.appendChild(toast);
    window.setTimeout(() => {
      toast.classList.add("toast--leaving");
      window.setTimeout(() => toast.remove(), 220);
    }, 2800);
  }

  function reportUiMessage(message, kind = "info") {
    showStatusBanner(message, kind);
    emitToast(message, kind);
  }

  function installNonBlockingAlerts() {
    if (typeof window === "undefined" || window.__narrativeosAlertWrapped) return;
    window.alert = (message) => {
      reportUiMessage(String(message), "error");
    };
    window.__narrativeosAlertWrapped = true;
  }

  function normalizeApiResponseText(text) {
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (_error) {
      return text;
    }
  }

  async function api(path, options = {}) {
    const hasExplicitAuthorization = Boolean(options.headers && Object.keys(options.headers).some((key) => key.toLowerCase() === "authorization"));
    const isBridgeResolve = path.startsWith("/v1/auth/admin-view-bridge/resolve");
    const shouldAttachAdminBridge =
      Boolean(shellState.activeProduct === "ops" && shellState.adminViewBridgeToken) &&
      path.startsWith("/v1/ops");
    const shouldAttachAuthorToken =
      !shouldAttachAdminBridge &&
      !isBridgeResolve &&
      Boolean(authorState.authorAuthSession?.accessToken) &&
      (
        path.startsWith("/v1/author") ||
        path.startsWith("/v1/ops") ||
        (path.startsWith("/v1/auth") && !path.startsWith("/v1/auth/login") && !path.startsWith("/v1/auth/register"))
      );
    const shouldAttachReaderToken =
      !hasExplicitAuthorization &&
      !isBridgeResolve &&
      Boolean(readerState.readerAuthSession?.accessToken) &&
      (
        path.startsWith("/v1/reader") ||
        path.startsWith("/v1/sessions") ||
        (path.startsWith("/v1/auth") && !path.startsWith("/v1/auth/login") && !path.startsWith("/v1/auth/register"))
      );
    const response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(shouldAttachAdminBridge ? { "X-NarrativeOS-Admin-Bridge": shellState.adminViewBridgeToken } : {}),
        ...(shouldAttachAuthorToken ? { Authorization: `Bearer ${authorState.authorAuthSession.accessToken}` } : {}),
        ...(shouldAttachReaderToken ? { Authorization: `Bearer ${readerState.readerAuthSession.accessToken}` } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });
    if (!response.ok) {
      const raw = await response.text();
      const payload = normalizeApiResponseText(raw);
      const detailPayload =
        typeof payload === "object" && payload !== null
          ? payload.detail !== undefined
            ? payload.detail
            : payload.message !== undefined
              ? payload.message
              : payload
          : raw || response.statusText || "请求失败";
      const detail =
        typeof detailPayload === "string"
          ? detailPayload
          : JSON.stringify(detailPayload);
      throw new ApiError({
        status: response.status,
        message: detail,
        detail: payload,
        code: typeof payload === "object" && payload !== null ? payload.code || null : null,
        actionHint: typeof payload === "object" && payload !== null ? payload.action_hint || null : null,
        retryable: typeof payload === "object" && payload !== null ? Boolean(payload.retryable) : response.status >= 500,
        source: path,
      });
    }
    const raw = await response.text();
    const payload = normalizeApiResponseText(raw);
    return payload && typeof payload === "object" ? payload : {};
  }

  function parseErrorDetail(error) {
    if (error?.detail && typeof error.detail === "object") {
      return error.detail;
    }
    try {
      return JSON.parse(error.message);
    } catch (_error) {
      return null;
    }
  }

  function describeAuthError(error, fallbackMessage = "当前操作暂时不可用，请稍后重试。") {
    const detail = parseErrorDetail(error) || {};
    const code = String(detail.code || "").trim();
    const reason = String(detail.reason || "").trim();
    if (detail.account_created && detail.can_retry_send) {
      return "账号已经创建，但验证邮件暂时没有发出。你可以稍后重新发送验证邮件。";
    }
    if (code === "auth_email_unverified") {
      return "你的邮箱还未验证。请先验证邮箱，再登录；如果没收到邮件，可以重新发送验证邮件。";
    }
    if (code === "auth_register_delivery_failed" || code === "auth_verification_delivery_failed" || code === "auth_password_reset_delivery_failed") {
      if (reason === "test_mode_external_recipient_blocked") {
        return "当前邮件系统仍处于测试模式，只能向测试邮箱发送邮件。请先使用 Resend 测试邮箱，或等发件域验证完成后再试。";
      }
      if (reason === "domain_not_verified") {
        return "发件域还没有完成验证，暂时不能向真实邮箱发送邮件。请先完成发件域验证后再试。";
      }
      if (reason === "provider_not_configured") {
        return "邮件服务配置还没有完成，暂时无法发送邮件。";
      }
      if (reason === "provider_network_error") {
        return "邮件服务暂时不可用，请稍后重试。";
      }
      if (reason === "provider_rejected") {
        return "邮件服务拒绝了这次发送请求，请检查发件配置后重试。";
      }
      if (reason === "db_write_failed" || reason === "token_issue_failed") {
        return "账户信息已收到，但系统暂时没能完成邮件流程，请稍后重试。";
      }
    }
    if (code === "auth_verification_invalid" && reason === "verification_resend_cooldown") {
      return detail.next_allowed_at
        ? `验证邮件刚发出不久，请在 ${formatTimestamp(detail.next_allowed_at)} 之后再试。`
        : "验证邮件刚发出不久，请稍等再试。";
    }
    if (code === "auth_verification_token_invalid") {
      if (reason === "auth_flow_token_consumed") {
        return "这个验证链接已经用过了。";
      }
      if (reason === "auth_flow_token_superseded") {
        return "这个验证链接已经被新的邮件替换了，请使用最新一封邮件里的链接。";
      }
      if (reason === "auth_flow_token_expired") {
        return "这个验证链接已经过期，请重新发送验证邮件。";
      }
    }
    if (code === "auth_password_reset_token_invalid") {
      if (reason === "auth_flow_token_consumed") {
        return "这个重置链接已经用过了，请重新申请一次密码重置。";
      }
      if (reason === "auth_flow_token_superseded") {
        return "这个重置链接已经被新的邮件替换了，请使用最新一封邮件里的链接。";
      }
      if (reason === "auth_flow_token_expired") {
        return "这个重置链接已经过期，请重新申请一次密码重置。";
      }
    }
    if (code === "auth_login_failed" && reason === "invalid_credentials") {
      return "邮箱或密码不正确。";
    }
    if (code === "auth_identity_missing" || (code === "auth_token_missing" && reason.includes("unknown_auth_identity"))) {
      return "这个账号不存在。";
    }
    return fallbackMessage;
  }

  function setBusy(button, busyLabel) {
    const previous = button.textContent;
    button.disabled = true;
    button.textContent = busyLabel;
    return () => {
      button.disabled = false;
      button.textContent = previous;
    };
  }

  function clearNode(node, emptyText = "") {
    node.innerHTML = "";
    if (emptyText) {
      node.classList.add("empty-state");
      node.textContent = localizeDisplayText(emptyText);
    } else {
      node.classList.remove("empty-state");
    }
  }

  function createListCard({ title, score = "", body = "", active = false }) {
    const card = document.createElement("article");
    card.className = "list-card";
    if (active) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${localizeDisplayText(title)}</h3>
        <span class="list-card-score">${localizeDisplayText(score)}</span>
      </div>
      <p class="list-card-body">${localizeDisplayText(body)}</p>
    `;
    return card;
  }

  function formatTimestamp(value) {
    if (!value) return "未知时间";
    try {
      return new Date(value).toLocaleString("zh-CN");
    } catch (_error) {
      return value;
    }
  }

  function downloadJsonFile(filename, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  function downloadTextFile(filename, content, contentType = "text/plain") {
    const blob = new Blob([String(content || "")], { type: contentType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  function downloadBase64File(filename, base64Content, contentType = "application/octet-stream") {
    const binary = atob(String(base64Content || ""));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    const blob = new Blob([bytes], { type: contentType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  function formatPercent(value) {
    return `${(Number(value || 0) * 100).toFixed(0)}%`;
  }

  function parseIssueCodes(value) {
    return String(value || "")
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function parseTagList(value) {
    return String(value || "")
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function parseMaybeJson(value) {
    if (typeof value !== "string") return value;
    try {
      return JSON.parse(value);
    } catch (_error) {
      return value;
    }
  }

  return {
    ApiError,
    safeText,
    clearStatusBanner,
    sanitizePublicMessage,
    showStatusBanner,
    emitToast,
    reportUiMessage,
    installNonBlockingAlerts,
    normalizeApiResponseText,
    api,
    parseErrorDetail,
    describeAuthError,
    setBusy,
    clearNode,
    localizeDisplayText,
    createListCard,
    formatTimestamp,
    downloadJsonFile,
    downloadTextFile,
    downloadBase64File,
    formatPercent,
    parseIssueCodes,
    parseTagList,
    parseMaybeJson,
  };
})();
