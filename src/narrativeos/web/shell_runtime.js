// Shell runtime extracted from app.js so the shell owns startup and event binding.

var ShellRuntime = (() => {
  const dom = ShellDOM;
  const {
    reportUiMessage,
    installNonBlockingAlerts,
    api,
    parseErrorDetail,
    describeAuthError,
  } = UIShared;

  let shellRuntimeInitialized = false;
  const authRouteState = {
    lastEmail: "",
    verifyStatus: "idle",
    verifyMessage: "",
    handledVerifyToken: null,
    resetStatus: "idle",
    resetMessage: "",
  };

  function requireRuntimeFunction(name, fn) {
    if (typeof fn !== "function") {
      throw new TypeError(`${name} is not a function`);
    }
    return fn;
  }

  function looksLikeEmail(value) {
    return String(value || "").includes("@");
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function currentAuthPage() {
    return shellState.authPage || null;
  }

  function currentAuthQuery() {
    if (typeof window === "undefined") return new URLSearchParams();
    return new URLSearchParams(window.location.search);
  }

  function currentAuthFlow() {
    return String(currentAuthQuery().get("flow") || "").trim();
  }

  function rememberAuthEmail(email) {
    const normalized = String(email || "").trim();
    if (!normalized) return;
    authRouteState.lastEmail = normalized;
    if (dom.shellAuthActorId) {
      dom.shellAuthActorId.value = normalized;
    }
    if (ReaderDOM.readerAuthActorId) {
      ReaderDOM.readerAuthActorId.value = normalized;
    }
  }

  function authRouteEmail() {
    const queryEmail = String(currentAuthQuery().get("email") || "").trim();
    return queryEmail || authRouteState.lastEmail || dom.shellAuthActorId?.value.trim() || "";
  }

  function authLink(label, href, variant = "ghost-action") {
    return `<a class="${variant}" href="${href}">${label}</a>`;
  }

  function authRouteCard(title, body, actions = "", extra = "") {
    return `
      <article class="auth-route-card">
        <div class="panel-head">
          <h3>${escapeHtml(title)}</h3>
        </div>
        <p>${escapeHtml(body)}</p>
        ${extra}
        ${actions ? `<div class="auth-route-inline-actions">${actions}</div>` : ""}
      </article>
    `;
  }

  function setStoredAuthorSession(payload) {
    authorState.authorAuthSession = {
      accessToken: payload.token?.access_token,
      expiresAt: payload.token?.expires_at,
      identity: payload.identity,
      tokenType: payload.token?.token_type || "bearer",
    };
    if (typeof window !== "undefined") {
      window.localStorage.setItem("narrativeos_author_auth", JSON.stringify(authorState.authorAuthSession));
    }
  }

  async function submitAuthRouteSignup() {
    const email = String(dom.authRouteContent?.querySelector("#auth-route-signup-email")?.value || "").trim();
    const password = String(dom.authRouteContent?.querySelector("#auth-route-signup-password")?.value || "").trim();
    const displayName = String(dom.authRouteContent?.querySelector("#auth-route-signup-display-name")?.value || "").trim();
    if (!email || !password) {
      reportUiMessage("请先填写邮箱和密码。", "warning");
      return;
    }
    await api("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        actor_id: email,
        actor_role: "author",
        password,
        account_id: email,
        display_name: displayName || null,
      }),
    });
    rememberAuthEmail(email);
    reportUiMessage("注册已提交。请先检查验证邮件，再回来登录。", "success");
    if (typeof window !== "undefined") {
      window.location.assign(`/app/verify-email?email=${encodeURIComponent(email)}`);
    }
  }

  async function submitAuthRouteLogin() {
    const email = String(dom.authRouteContent?.querySelector("#auth-route-login-email")?.value || "").trim();
    const password = String(dom.authRouteContent?.querySelector("#auth-route-login-password")?.value || "").trim();
    if (!email || !password) {
      reportUiMessage("请先填写邮箱和密码。", "warning");
      return;
    }
    const payload = await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        actor_id: email,
        password,
      }),
    });
    rememberAuthEmail(email);
    setStoredAuthorSession(payload);
    if (typeof window !== "undefined") {
      window.location.replace("/app");
    }
  }

  async function submitAuthRouteVerificationRequest() {
    const email = String(dom.authRouteContent?.querySelector("#auth-route-verify-email-input")?.value || "").trim();
    if (!email) {
      reportUiMessage("请先填写邮箱。", "warning");
      return;
    }
    const payload = await api("/v1/auth/verification/request", {
      method: "POST",
      body: JSON.stringify({ actor_id: email }),
    });
    rememberAuthEmail(email);
    authRouteState.verifyStatus = "resent";
    authRouteState.verifyMessage = payload.status === "already_verified"
      ? "这个邮箱已经验证完成，现在可以直接登录。"
      : "验证邮件已经重新发送，请检查邮箱。";
    renderAuthRouteStage();
  }

  async function submitAuthRouteForgotPassword() {
    const email = String(dom.authRouteContent?.querySelector("#auth-route-forgot-email")?.value || "").trim();
    if (!email) {
      reportUiMessage("请先填写邮箱。", "warning");
      return;
    }
    await api("/v1/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ actor_id: email }),
    });
    rememberAuthEmail(email);
    authRouteState.resetStatus = "requested";
    authRouteState.resetMessage = "密码重置邮件已经发出，请检查邮箱。";
    renderAuthRouteStage();
  }

  async function submitAuthRouteResetPassword() {
    const token = String(currentAuthQuery().get("token") || "").trim();
    const password = String(dom.authRouteContent?.querySelector("#auth-route-reset-password-input")?.value || "").trim();
    if (!token) {
      authRouteState.resetStatus = "error";
      authRouteState.resetMessage = "重置链接缺少必要信息，请重新申请一次密码重置。";
      renderAuthRouteStage();
      return;
    }
    if (!password) {
      reportUiMessage("请先输入新密码。", "warning");
      return;
    }
    await api("/v1/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: password }),
    });
    authRouteState.resetStatus = "success";
    authRouteState.resetMessage = "密码已经更新完成，现在可以用新密码登录。";
    renderAuthRouteStage();
  }

  async function resolveVerifyEmailTokenIfPresent() {
    const token = String(currentAuthQuery().get("token") || "").trim();
    if (!token || authRouteState.handledVerifyToken === token || currentAuthPage() !== "verify-email") {
      return;
    }
    authRouteState.handledVerifyToken = token;
    authRouteState.verifyStatus = "pending";
    authRouteState.verifyMessage = "正在验证你的邮箱，请稍候。";
    renderAuthRouteStage();
    try {
      const flow = currentAuthFlow();
      const payload = await api(flow === "email-change" ? "/v1/auth/email-change/confirm" : "/v1/auth/verification/confirm", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      rememberAuthEmail(payload.identity?.email_address || payload.identity?.account_id || payload.identity?.actor_id || "");
      authRouteState.verifyStatus = "success";
      authRouteState.verifyMessage = flow === "email-change"
        ? "新邮箱已经确认完成。旧邮箱现在已经失效，请使用新邮箱重新登录。"
        : "邮箱已经验证完成，现在可以登录了。";
    } catch (error) {
      authRouteState.verifyStatus = "error";
      authRouteState.verifyMessage = describeAuthError(
        error,
        currentAuthFlow() === "email-change"
          ? "这个邮箱变更链接现在不可用，请回到账户页重新发起一次邮箱迁移。"
          : "这个验证链接现在不可用，请重新发送一封验证邮件。"
      );
    }
    renderAuthRouteStage();
  }

  function bindAuthRouteStageEvents() {
    if (!dom.authRouteContent) return;
    dom.authRouteContent.querySelector("#auth-route-signup-submit")?.addEventListener("click", async () => {
      try {
        await submitAuthRouteSignup();
      } catch (error) {
        reportUiMessage(describeAuthError(error, "注册暂时失败，请稍后重试。"), "error");
      }
    });
    dom.authRouteContent.querySelector("#auth-route-login-submit")?.addEventListener("click", async () => {
      try {
        await submitAuthRouteLogin();
      } catch (error) {
        const detail = parseErrorDetail(error) || {};
        reportUiMessage(describeAuthError(error, "登录暂时失败，请稍后重试。"), detail.code === "auth_email_unverified" ? "warning" : "error");
      }
    });
    dom.authRouteContent.querySelector("#auth-route-verify-submit")?.addEventListener("click", async () => {
      try {
        await submitAuthRouteVerificationRequest();
      } catch (error) {
        const detail = parseErrorDetail(error) || {};
        reportUiMessage(describeAuthError(error, "验证邮件暂时发送失败，请稍后重试。"), detail.reason === "verification_resend_cooldown" ? "warning" : "error");
      }
    });
    dom.authRouteContent.querySelector("#auth-route-forgot-submit")?.addEventListener("click", async () => {
      try {
        await submitAuthRouteForgotPassword();
      } catch (error) {
        reportUiMessage(describeAuthError(error, "密码重置邮件暂时发送失败，请稍后重试。"), "error");
      }
    });
    dom.authRouteContent.querySelector("#auth-route-reset-submit")?.addEventListener("click", async () => {
      try {
        await submitAuthRouteResetPassword();
      } catch (error) {
        reportUiMessage(describeAuthError(error, "重置密码暂时失败，请稍后重试。"), "error");
      }
    });
  }

  function renderAuthRouteStage() {
    if (!dom.authRouteContent) return;
    const page = currentAuthPage();
    const email = escapeHtml(authRouteEmail());
    const tokenPresent = Boolean(currentAuthQuery().get("token"));
    const flow = currentAuthFlow();
    let html = "";
    if (page === "signup") {
      html = authRouteCard(
        "创建邮箱账号",
        "注册后系统会先发送验证邮件。验证完成后，再回到登录页进入你的工作区。",
        `${authLink("去登录", "/app/login")} ${authLink("验证邮箱帮助", "/app/verify-email")}`,
        `
          <div class="auth-route-inputs">
            <label class="input-label" for="auth-route-signup-email">邮箱</label>
            <input id="auth-route-signup-email" class="field-input" type="email" value="${email}" placeholder="name@example.com" />
            <label class="input-label" for="auth-route-signup-display-name">显示名称</label>
            <input id="auth-route-signup-display-name" class="field-input" type="text" placeholder="可选" />
            <label class="input-label" for="auth-route-signup-password">密码</label>
            <input id="auth-route-signup-password" class="field-input" type="password" placeholder="输入密码" />
          </div>
          <div class="auth-route-inline-actions">
            <button id="auth-route-signup-submit" class="primary-action" type="button">注册并发送验证邮件</button>
          </div>
        `
      );
    } else if (page === "login") {
      html = authRouteCard(
        "邮箱登录",
        "如果你的邮箱还没验证，系统会直接告诉你下一步该做什么，不会再把邮件问题显示成服务器错误。",
        `${authLink("去注册", "/app/signup")} ${authLink("忘记密码", "/app/forgot-password")} ${authLink("重新发送验证邮件", "/app/verify-email")}`,
        `
          <div class="auth-route-inputs">
            <label class="input-label" for="auth-route-login-email">邮箱</label>
            <input id="auth-route-login-email" class="field-input" type="email" value="${email}" placeholder="name@example.com" />
            <label class="input-label" for="auth-route-login-password">密码</label>
            <input id="auth-route-login-password" class="field-input" type="password" placeholder="输入密码" />
          </div>
          <div class="auth-route-inline-actions">
            <button id="auth-route-login-submit" class="primary-action" type="button">登录</button>
          </div>
        `
      );
    } else if (page === "verify-email") {
      const isEmailChangeFlow = flow === "email-change";
      const message = authRouteState.verifyMessage || (
        tokenPresent
          ? (isEmailChangeFlow ? "正在确认你的新邮箱，请稍候。" : "正在等待验证结果。")
          : (isEmailChangeFlow ? "这个页面用于确认账户邮箱迁移，请从发往新邮箱的确认链接进入。" : "如果你还没收到验证邮件，可以在这里重新发送。")
      );
      html = authRouteCard(
        authRouteState.verifyStatus === "success" ? (isEmailChangeFlow ? "新邮箱已确认" : "邮箱已验证") : (isEmailChangeFlow ? "确认新邮箱" : "验证邮箱"),
        message,
        authRouteState.verifyStatus === "success"
          ? `${authLink("去登录", "/app/login", "primary-action")}`
          : `${authLink("去登录", "/app/login")} ${authLink("去注册", "/app/signup")}`,
        authRouteState.verifyStatus === "success" || isEmailChangeFlow
          ? ""
          : `
            <div class="auth-route-inputs">
              <label class="input-label" for="auth-route-verify-email-input">邮箱</label>
              <input id="auth-route-verify-email-input" class="field-input" type="email" value="${email}" placeholder="name@example.com" />
            </div>
            <div class="auth-route-inline-actions">
              <button id="auth-route-verify-submit" class="primary-action" type="button">重新发送验证邮件</button>
            </div>
          `
      );
    } else if (page === "forgot-password") {
      html = authRouteCard(
        "忘记密码",
        authRouteState.resetStatus === "requested" ? authRouteState.resetMessage : "输入你的邮箱，系统会发送一封密码重置邮件。",
        `${authLink("去登录", "/app/login")} ${authLink("重新发送验证邮件", "/app/verify-email")}`,
        `
          <div class="auth-route-inputs">
            <label class="input-label" for="auth-route-forgot-email">邮箱</label>
            <input id="auth-route-forgot-email" class="field-input" type="email" value="${email}" placeholder="name@example.com" />
          </div>
          <div class="auth-route-inline-actions">
            <button id="auth-route-forgot-submit" class="primary-action" type="button">发送重置邮件</button>
          </div>
        `
      );
    } else if (page === "reset-password") {
      const body = authRouteState.resetMessage || (tokenPresent ? "输入新密码，完成这次密码重置。" : "这个页面缺少重置链接信息，请重新申请一次密码重置。");
      html = authRouteCard(
        authRouteState.resetStatus === "success" ? "密码已重置" : "重置密码",
        body,
        authRouteState.resetStatus === "success"
          ? `${authLink("去登录", "/app/login", "primary-action")}`
          : `${authLink("重新申请密码重置", "/app/forgot-password")} ${authLink("去登录", "/app/login")}`,
        authRouteState.resetStatus === "success"
          ? ""
          : `
            <div class="auth-route-inputs">
              <label class="input-label" for="auth-route-reset-password-input">新密码</label>
              <input id="auth-route-reset-password-input" class="field-input" type="password" placeholder="输入新密码" />
            </div>
            <div class="auth-route-inline-actions">
              <button id="auth-route-reset-submit" class="primary-action" type="button">更新密码</button>
            </div>
          `
      );
    }
    dom.authRouteContent.innerHTML = html;
    bindAuthRouteStageEvents();
  }

  function syncShellAuthFormIntoAuthorAuthForm() {
    if (AuthorDOM.authorAuthActorId) {
      AuthorDOM.authorAuthActorId.value = dom.shellAuthActorId?.value.trim() || "";
    }
    if (AuthorDOM.authorAuthDisplayName) {
      AuthorDOM.authorAuthDisplayName.value = dom.shellAuthDisplayName?.value.trim() || "";
    }
    if (AuthorDOM.authorAuthPassword) {
      AuthorDOM.authorAuthPassword.value = dom.shellAuthPassword?.value || "";
    }
    if (AuthorDOM.authorAuthRole) {
      AuthorDOM.authorAuthRole.value = "author";
    }
    if (AuthorDOM.authorAccountId && !AuthorDOM.authorAccountId.value.trim()) {
      AuthorDOM.authorAccountId.value = dom.shellAuthActorId?.value.trim() || "";
    }
  }

  function seedReviewerWorkbenchFromSession() {
    const actorId = String(authorState.authorAuthSession?.identity?.actor_id || "").trim();
    const actorRole = String(authorState.authorAuthSession?.identity?.actor_role || "").trim();
    if (!actorId || !["reviewer", "ops", "admin"].includes(actorRole)) return;
    if (AuthorDOM.authorInboxReviewerId && !AuthorDOM.authorInboxReviewerId.value.trim()) {
      AuthorDOM.authorInboxReviewerId.value = actorId;
    }
    if (AuthorDOM.authorApprovalReviewer && !AuthorDOM.authorApprovalReviewer.value.trim()) {
      AuthorDOM.authorApprovalReviewer.value = actorId;
    }
  }

  function shouldResumeStartupOpsRoute(actorRole = "") {
    return ["reviewer", "ops", "admin"].includes(String(actorRole || "").trim()) && shellState.startupRouteProduct === "ops";
  }

  async function bootstrapShellAuthFromCookie() {
    if (authorState.authorAuthSession?.identity) {
      return true;
    }
    const hasBootstrapCandidate = Boolean(
      authorState.authorAuthSession?.accessToken
      || authorState.authorAuthSession?.cookieBacked
      || authorState.authorAuthSession?.identity
      || readerState.readerAuthSession?.accessToken
      || readerState.readerAuthSession?.cookieBacked
      || readerState.readerAuthSession?.identity
    );
    if (!hasBootstrapCandidate) {
      return false;
    }
    try {
      const payload = await api("/v1/auth/me");
      if (!payload?.identity) {
        return false;
      }
      authorState.authorAuthSession = {
        accessToken: null,
        expiresAt: payload.identity?.expires_at || null,
        identity: payload.identity,
        tokenType: "bearer",
        cookieBacked: true,
      };
      if (typeof persistAuthorAuthSession === "function") {
        persistAuthorAuthSession();
      }
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function finalizeShellAuthSuccess() {
    const actorRole = String(authorState.authorAuthSession?.identity?.actor_role || "").trim();
    seedReviewerWorkbenchFromSession();
    if (actorRole === "author") {
      shellState.activeProduct = "author";
      if (!shellState.authorWorkspace || shellState.authorWorkspace === "settings") {
        shellState.authorWorkspace = "overview";
      }
      await refreshAuthorSurface();
    } else if (actorRole === "customer") {
      shellState.activeProduct = "customer";
      shellState.customerWorkspace = "overview";
      await refreshCustomerSurface();
    } else if (["reviewer", "ops", "admin"].includes(actorRole)) {
      if (shouldResumeStartupOpsRoute(actorRole)) {
        shellState.activeProduct = "ops";
        if (shellState.startupRouteWorkspace) {
          shellState.opsWorkspace = shellState.startupRouteWorkspace;
        }
        await refreshOpsReleaseFlow();
      } else {
        shellState.activeProduct = "author";
        shellState.authorWorkspace = "settings";
        await refreshAuthorSurface();
      }
    } else {
      shellState.activeProduct = "reader";
      shellState.readerWorkspace = "landing";
    }
    if (dom.shellAuthPassword) {
      dom.shellAuthPassword.value = "";
    }
    syncProductMode();
    updateStatus();
  }

  async function registerFromShellAuth() {
    const actorId = String(dom.shellAuthActorId?.value || "").trim();
    if (looksLikeEmail(actorId)) {
      await api("/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          actor_id: actorId,
          actor_role: "author",
          password: String(dom.shellAuthPassword?.value || ""),
          account_id: actorId,
          display_name: String(dom.shellAuthDisplayName?.value || "").trim() || null,
        }),
      });
      rememberAuthEmail(actorId);
      reportUiMessage("注册已提交。请先检查验证邮件，再回来登录。", "success");
      if (typeof window !== "undefined") {
        window.location.assign(`/app/verify-email?email=${encodeURIComponent(actorId)}`);
      }
      return;
    }
    syncShellAuthFormIntoAuthorAuthForm();
    await registerAuthorAuthIdentity();
    await finalizeShellAuthSuccess();
  }

  async function loginFromShellAuth() {
    syncShellAuthFormIntoAuthorAuthForm();
    await loginAuthorAuthIdentity();
    await finalizeShellAuthSuccess();
  }

  async function logoutFromShellAuth() {
    await logoutAuthorAuthIdentity();
    if (dom.shellAuthPassword) {
      dom.shellAuthPassword.value = "";
    }
    syncProductMode();
    updateStatus();
  }

  async function resolveAdminViewBridgeIfPresent() {
    if (!shellState.adminViewBridgeToken) {
      shellState.adminViewEnabled = ["reviewer", "ops", "admin"].includes(
        String(authorState.authorAuthSession?.identity?.actor_role || "").trim()
      );
      return;
    }
    try {
      const payload = await api("/v1/auth/admin-view-bridge/resolve", {
        method: "POST",
        body: JSON.stringify({ token: shellState.adminViewBridgeToken }),
      });
      shellState.adminViewEnabled = Boolean(payload.authorized);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("narrativeos_admin_view_bridge", shellState.adminViewBridgeToken);
      }
      const context = payload.context || {};
      if (shellState.activeProduct === "ops" && typeof syncOpsNavigationContext === "function") {
        syncOpsNavigationContext(
          {
            account_id: context.account_id,
            world_id: context.world_id,
            world_version_id: context.world_version_id,
            case_id: context.case_id,
            alert_id: context.alert_id,
          },
          { preserveExisting: false }
        );
        if (context.workspace) {
          shellState.opsWorkspace = context.workspace;
        }
      }
    } catch (error) {
      shellState.adminViewEnabled = false;
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem("narrativeos_admin_view_bridge");
      }
      if (shellState.activeProduct === "ops") {
        shellState.activeProduct = authorState.authorAuthSession?.identity ? "author" : "reader";
      }
      const detail = parseErrorDetail(error);
      if (detail?.code === "admin_view_bridge_forbidden") {
        reportUiMessage("当前登录身份没有管理员视图权限，需要 reviewer / ops / admin 账号。", "warning");
      } else {
        reportUiMessage(`管理员视图校验失败：${error.message}`, "error");
      }
    } finally {
      if (!shellState.adminViewEnabled) {
        shellState.adminViewBridgeToken = null;
      }
    }
  }

  async function initializeShellRuntime() {
    if (shellRuntimeInitialized) return;
    shellRuntimeInitialized = true;

    if (typeof window !== "undefined") {
      window.__bootMarker = "before-bindings";
    }

    try {
      dom.modeReader?.addEventListener("click", () => {
        shellState.activeProduct = "reader";
        syncProductMode();
      });
      dom.modeAuthor?.addEventListener("click", async () => {
        shellState.activeProduct = "author";
        syncProductMode();
        try {
          await refreshAuthorSurface();
        } catch (error) {
          reportUiMessage(`作者工作台刷新失败：${error.message}`, "error");
        }
      });
      dom.modeCustomer?.addEventListener("click", async () => {
        shellState.activeProduct = "customer";
        syncProductMode();
        try {
          await refreshCustomerSurface();
        } catch (error) {
          reportUiMessage(`客户工作台刷新失败：${error.message}`, "error");
        }
      });
      dom.modeOps?.addEventListener("click", async () => {
        shellState.activeProduct = "ops";
        syncProductMode();
        try {
          await refreshOpsReleaseFlow();
        } catch (error) {
          reportUiMessage(`运营工作台刷新失败：${error.message}`, "error");
        }
      });
      dom.shellDebugToggle?.addEventListener("click", () => toggleDebugMode());
      dom.shellAuthRegister?.addEventListener("click", async () => {
        try {
          await registerFromShellAuth();
        } catch (error) {
          reportUiMessage(describeAuthError(error, "注册暂时失败，请稍后重试。"), "error");
        }
      });
      dom.shellAuthLogin?.addEventListener("click", async () => {
        try {
          await loginFromShellAuth();
        } catch (error) {
          const detail = parseErrorDetail(error) || {};
          reportUiMessage(describeAuthError(error, "登录暂时失败，请稍后重试。"), detail.code === "auth_email_unverified" ? "warning" : "error");
        }
      });
      dom.shellAuthLogout?.addEventListener("click", async () => {
        try {
          await logoutFromShellAuth();
        } catch (error) {
          reportUiMessage(`统一退出失败：${error.message}`, "error");
        }
      });
      dom.shellSessionLogout?.addEventListener("click", async () => {
        try {
          await logoutFromShellAuth();
        } catch (error) {
          reportUiMessage(`统一退出失败：${error.message}`, "error");
        }
      });
    } catch (error) {
      console.error("listener bootstrap failed", error);
    }

    if (typeof window !== "undefined") {
      window.__bootMarker = "after-bindings";
    }

    hydrateShellRoute();
    if (typeof restoreAuthorAuthSession === "function") {
      restoreAuthorAuthSession();
    }
    await bootstrapShellAuthFromCookie();
    installNonBlockingAlerts();
    installScrollWorkspaceBridge();
    try {
      requireRuntimeFunction("initializeReaderRuntime", initializeReaderRuntime)();
      requireRuntimeFunction("initializeAuthorWorkspaceRuntime", initializeAuthorWorkspaceRuntime)();
      requireRuntimeFunction("initializeAgentStudioRuntime", initializeAgentStudioRuntime)();
      requireRuntimeFunction("initializeCustomerWorkspaceRuntime", initializeCustomerWorkspaceRuntime)();
      requireRuntimeFunction("initializeOpsRuntime", initializeOpsRuntime)();
    } catch (error) {
      console.error("runtime bootstrap failed", error);
      reportUiMessage(`前端启动失败：${error.message}`, "error");
      return;
    }
    try {
      await hydrateAuthorAuthSession();
    } catch (error) {
      console.error("author auth bootstrap failed", error);
    }
    try {
      await resolveAdminViewBridgeIfPresent();
    } catch (error) {
      console.error("admin view bridge bootstrap failed", error);
    }
    syncProductMode();
    syncViewMode();
    renderAuthRouteStage();
    if (shellState.authPage === "verify-email") {
      resolveVerifyEmailTokenIfPresent().catch((error) => {
        reportUiMessage(describeAuthError(error, "邮箱验证暂时失败，请稍后重试。"), "error");
      });
    }
    if (shellState.authPage) {
      updateStatus();
      return;
    }
    if (shellState.activeProduct === "author") {
      refreshAuthorSurface().catch((error) => {
        reportUiMessage(`作者工作台初始化失败：${error.message}`, "error");
      });
    }
    if (shellState.activeProduct === "customer") {
      refreshCustomerSurface().catch((error) => {
        reportUiMessage(`客户工作台初始化失败：${error.message}`, "error");
      });
    }
    if (shellState.activeProduct === "ops") {
      refreshOpsReleaseFlow().catch((error) => {
        reportUiMessage(`运营工作台初始化失败：${error.message}`, "error");
      });
    }

    if (typeof window !== "undefined") {
      window.__bootMarker = "after-init";
    }
  }

  return { initializeShellRuntime };
})();

ShellRuntime.initializeShellRuntime();
