// Reader UI runtime extracted from app.js to keep Reader flows isolated from shell, Author, and Ops logic.

var ReaderRuntime = (() => {
  const shellDom = ShellDOM;
  const readerDom = ReaderDOM;
  const CHECKOUT_CONTEXT_STORAGE_KEY = "narrativeos_reader_checkout_context";
  const CHECKOUT_CONTEXT_MAX_AGE_MS = 1000 * 60 * 60 * 12;
  const {
    api,
    reportUiMessage,
    setBusy,
    clearNode,
    formatTimestamp,
    describeAuthError,
    parseErrorDetail
  } = UIShared;
  const {
    tierLabel,
    accessReasonLabel,
    worldUnlockLabel
  } = ReaderAccessors;

function activeReaderId() {
  return (
    readerState.readerAuthSession?.identity?.account_id ||
    readerDom.readerIdInput?.value.trim() ||
    readerState.readerId ||
    "reader_demo"
  );
}

function activeAuthoredWorkAccountId() {
  return (
    authorState.authorAuthSession?.identity?.account_id ||
    authorState.authorAuthSession?.identity?.actor_id ||
    ""
  );
}

function clearAuthoredWorkPreview() {
  readerState.activeAuthoredWorkPreview = null;
  readerState.worldId = readerState.currentBundle?.world_bible?.world_id || null;
}

function persistReaderAuthSession() {
  if (typeof window === "undefined") return;
  if (readerState.readerAuthSession?.accessToken || (readerState.readerAuthSession?.cookieBacked && readerState.readerAuthSession?.identity)) {
    window.localStorage.setItem("narrativeos_reader_auth", JSON.stringify(readerState.readerAuthSession));
  } else {
    window.localStorage.removeItem("narrativeos_reader_auth");
  }
}

function restoreReaderAuthSession() {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem("narrativeos_reader_auth");
    if (!raw) {
      if (readerState.readerAuthSession?.identity) return;
      readerState.readerAuthSession = null;
      return;
    }
    readerState.readerAuthSession = JSON.parse(raw);
  } catch (_error) {
    readerState.readerAuthSession = null;
  }
}

function persistPendingCheckoutContext(context) {
  readerState.pendingCheckoutContext = context || null;
  if (typeof window === "undefined") return;
  if (readerState.pendingCheckoutContext) {
    window.localStorage.setItem(CHECKOUT_CONTEXT_STORAGE_KEY, JSON.stringify(readerState.pendingCheckoutContext));
  } else {
    window.localStorage.removeItem(CHECKOUT_CONTEXT_STORAGE_KEY);
  }
}

function restorePendingCheckoutContext() {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(CHECKOUT_CONTEXT_STORAGE_KEY);
    const payload = raw ? JSON.parse(raw) : null;
    const createdAt = Number(payload?.createdAt || 0);
    if (!payload || !createdAt || (Date.now() - createdAt) > CHECKOUT_CONTEXT_MAX_AGE_MS) {
      persistPendingCheckoutContext(null);
      return;
    }
    readerState.pendingCheckoutContext = payload;
    if (!readerState.readerAuthSession?.identity?.account_id && payload.accountId) {
      readerState.readerId = payload.accountId;
      if (readerDom.readerIdInput) {
        readerDom.readerIdInput.value = payload.accountId;
      }
    }
    if (!readerState.readerAuthSession?.identity?.actor_id && payload.readerActorId && readerDom.readerAuthActorId) {
      readerDom.readerAuthActorId.value = payload.readerActorId;
    }
  } catch (_error) {
    persistPendingCheckoutContext(null);
  }
}

function applyCheckoutContext(context) {
  if (!context) return;
  if (context.accountId && !readerState.readerAuthSession?.identity?.account_id) {
    readerState.readerId = context.accountId;
    if (readerDom.readerIdInput) {
      readerDom.readerIdInput.value = context.accountId;
    }
  }
  if (context.worldId) {
    readerState.worldId = context.worldId;
  }
  if (context.readerWorkspace && shellState.activeProduct === "reader") {
    shellState.readerWorkspace = context.readerWorkspace;
  }
  if (context.activeView) {
    readerState.activeView = context.activeView;
  }
}

function renderReaderAuthStatus() {
  clearNode(readerDom.readerAuthStatus);
  const session = readerState.readerAuthSession;
  if (!session?.identity) {
    clearNode(readerDom.readerAuthStatus, "登录后，这里会显示当前账号信息与会员状态。");
    return;
  }
  const card = document.createElement("article");
  card.className = "list-card";
  card.innerHTML = `
    <div class="list-card-head">
      <h3>${session.identity.display_name || session.identity.actor_id || "-"}</h3>
      <span class="list-card-score">已登录</span>
    </div>
    <p class="list-card-body">账号 ${session.identity.account_id || "-"}\n显示名称 ${session.identity.display_name || session.identity.actor_id || "-"}\n邮箱验证 ${session.identity.email_verified ? "已验证" : (session.identity.verification_required ? "待验证" : "不适用")}\n登录有效期 ${session.expiresAt || session.identity.expires_at || "-"}</p>
  `;
  readerDom.readerAuthStatus.appendChild(card);
}

async function mirrorReaderAuthSession(session) {
  readerState.readerAuthSession = session
    ? {
        accessToken: session.accessToken,
        expiresAt: session.expiresAt,
        identity: session.identity ? { ...session.identity } : null,
        tokenType: session.tokenType || "bearer",
        cookieBacked: Boolean(session.cookieBacked || (!session.accessToken && session.identity)),
      }
    : null;
  persistReaderAuthSession();
  if (readerState.readerAuthSession?.identity?.account_id) {
    readerState.readerId = readerState.readerAuthSession.identity.account_id;
    if (readerDom.readerIdInput) {
      readerDom.readerIdInput.value = readerState.readerAuthSession.identity.account_id;
    }
  }
  if (!readerState.readerAuthSession) {
    readerState.readerEntitlements = [];
    renderReaderAuthStatus();
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.syncProductMode();
      ShellStatusRuntime.updateStatus();
    }
    return;
  }
  renderReaderAuthStatus();
  try {
    await refreshReaderEntitlements();
  } catch (_error) {
    // If reader entitlements fail to refresh, keep the mirrored session so shell gating still works.
  }
}

async function hydrateReaderAuthSession() {
  const existingSession = readerState.readerAuthSession;
  if (!existingSession?.accessToken && !existingSession?.cookieBacked && !existingSession?.identity) {
    readerState.readerAuthSession = null;
    persistReaderAuthSession();
    renderReaderAuthStatus();
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
    readerState.readerAuthSession = {
      ...existingSession,
      accessToken: existingSession?.accessToken || null,
      identity: payload.identity,
      expiresAt: payload.identity?.expires_at || existingSession?.expiresAt || null,
      tokenType: existingSession?.tokenType || "bearer",
      cookieBacked: !existingSession?.accessToken,
    };
    persistReaderAuthSession();
  } catch (_error) {
    readerState.readerAuthSession = null;
    persistReaderAuthSession();
  }
  if (readerState.readerAuthSession?.identity?.account_id) {
    readerState.readerId = readerState.readerAuthSession.identity.account_id;
    if (readerDom.readerIdInput) {
      readerDom.readerIdInput.value = readerState.readerAuthSession.identity.account_id;
    }
  }
  renderReaderAuthStatus();
  if (typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.syncProductMode();
    ShellStatusRuntime.updateStatus();
  }
}

async function registerReaderAuthIdentity() {
  const actorId = (readerDom.readerAuthActorId?.value || "").trim();
  const password = (readerDom.readerAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    reportUiMessage("请先填写邮箱和密码。", "warning");
    return;
  }
  try {
    await api("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        actor_id: actorId,
        actor_role: "reader",
        password,
        account_id: actorId,
        display_name: (readerDom.readerAuthDisplayName?.value || "").trim() || null,
      }),
    });
    reportUiMessage("注册已提交。请先检查验证邮件，完成验证后再登录。", "success");
  } catch (error) {
    reportUiMessage(describeAuthError(error, "注册暂时失败，请稍后重试。"), "error");
  }
}

async function loginReaderAuthIdentity() {
  const actorId = (readerDom.readerAuthActorId?.value || "").trim();
  const password = (readerDom.readerAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    reportUiMessage("请先填写邮箱和密码。", "warning");
    return;
  }
  try {
    const payload = await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        actor_id: actorId,
        password,
      }),
    });
    readerState.readerAuthSession = {
      accessToken: payload.token?.access_token,
      expiresAt: payload.token?.expires_at,
      identity: payload.identity,
      tokenType: payload.token?.token_type || "bearer",
    };
    persistReaderAuthSession();
    if (payload.identity?.account_id) {
      readerState.readerId = payload.identity.account_id;
      if (readerDom.readerIdInput) {
        readerDom.readerIdInput.value = payload.identity.account_id;
      }
    }
    renderReaderAuthStatus();
    await refreshReaderEntitlements();
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.syncProductMode();
      ShellStatusRuntime.updateStatus();
    }
  } catch (error) {
    const detail = parseErrorDetail(error) || {};
    const kind = detail.code === "auth_email_unverified" ? "warning" : "error";
    reportUiMessage(describeAuthError(error, "登录暂时失败，请稍后重试。"), kind);
  }
}

async function logoutReaderAuthIdentity() {
  if (!readerState.readerAuthSession?.accessToken) {
    readerState.readerAuthSession = null;
    persistReaderAuthSession();
    renderReaderAuthStatus();
    return;
  }
  try {
    await api("/v1/auth/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${readerState.readerAuthSession.accessToken}` },
    });
  } catch (_error) {
    // Clear local state even if remote revoke fails.
  }
  readerState.readerAuthSession = null;
  persistReaderAuthSession();
  renderReaderAuthStatus();
  if (typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.syncProductMode();
    ShellStatusRuntime.updateStatus();
  }
}

async function requestReaderEmailVerification() {
  const actorId = (readerDom.readerAuthActorId?.value || "").trim() || readerState.readerAuthSession?.identity?.actor_id;
  if (!actorId) {
    reportUiMessage("请先填写邮箱。", "warning");
    return;
  }
  try {
    const payload = await api("/v1/auth/verification/request", {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId }),
    });
    if (payload.identity) {
      readerState.readerAuthSession = readerState.readerAuthSession
        ? { ...readerState.readerAuthSession, identity: { ...readerState.readerAuthSession.identity, ...payload.identity } }
        : readerState.readerAuthSession;
      persistReaderAuthSession();
      renderReaderAuthStatus();
    }
    reportUiMessage("验证邮件已发送，请检查邮箱。", "success");
  } catch (error) {
    const detail = parseErrorDetail(error) || {};
    const kind = detail.reason === "verification_resend_cooldown" ? "warning" : "error";
    reportUiMessage(describeAuthError(error, "验证邮件暂时发送失败，请稍后重试。"), kind);
  }
}

async function requestReaderPasswordReset() {
  const actorId = (readerDom.readerAuthActorId?.value || "").trim() || readerState.readerAuthSession?.identity?.actor_id;
  if (!actorId) {
    reportUiMessage("请先填写邮箱。", "warning");
    return;
  }
  try {
    await api("/v1/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId }),
    });
    reportUiMessage("密码重置邮件已发送，请检查邮箱。", "success");
  } catch (error) {
    reportUiMessage(describeAuthError(error, "密码重置邮件暂时发送失败，请稍后重试。"), "error");
  }
}

async function refreshReaderEntitlements() {
  const readerId = activeReaderId();
  readerState.readerId = readerId;
  if (readerDom.readerIdInput) {
    readerDom.readerIdInput.value = readerId;
  }
  const shouldFetchEntitlements =
    shellState.debug ||
    Boolean(readerState.sessionPaywall?.quote) ||
    Boolean(readerState.latestStep?.paywall?.quote) ||
    Boolean(readerState.readerCheckoutSession) ||
    readerState.continuityContract?.status === "quality_guard_failed";
  if (!shouldFetchEntitlements) {
    readerState.readerSubscription = null;
    readerState.readerEntitlements = [];
    clearNode(readerDom.readerEntitlementList, "进入故事后，这里会显示当前会员权益与剩余点数。");
    clearNode(readerDom.readerMembershipOffers, shellState.debug ? "内部模式下会显示会员方案与支付调试入口。" : "真正需要解锁时，会在阅读流程中直接提示。");
    clearNode(readerDom.readerCheckoutStatus, shellState.debug ? "内部模式下会显示最近一次支付调试结果。" : "当前没有需要展示的支付状态。");
    updateStatus();
    return;
  }

  let payload;
  let subscriptionPayload;
  try {
    [payload, subscriptionPayload] = await Promise.all([
      api(`/v1/reader/entitlements?account_id=${encodeURIComponent(readerId)}${readerState.worldId ? `&world_id=${encodeURIComponent(readerState.worldId)}` : ""}`),
      api(`/v1/reader/subscription?account_id=${encodeURIComponent(readerId)}`),
    ]);
  } catch (error) {
    readerState.readerSubscription = null;
    readerState.readerEntitlements = [];
    clearNode(readerDom.readerEntitlementList, "暂时无法刷新会员权益；阅读主链路仍可继续。");
    clearNode(readerDom.readerMembershipOffers, "订阅与钱包详情暂时不可用；如遇到解锁阻塞，会在当前章节内直接提示。");
    clearNode(readerDom.readerCheckoutStatus, "最近一次支付状态暂时不可用。");
    updateStatus();
    reportUiMessage(`访问状态刷新失败：${error.message}`, shellState.debug ? "error" : "warning");
    return;
  }
  readerState.readerSubscription = subscriptionPayload;
  readerState.readerEntitlements = payload.entitlements || [];
  readerState.readerCheckoutSession =
    payload.checkout_session ||
    payload.latest_checkout_session ||
    payload.recent_checkout_sessions?.[0] ||
    readerState.readerCheckoutSession ||
    null;
  const credits = payload.wallets?.story_credits || readerState.readerEntitlements.find((item) => item.entitlement_type === "credits" && item.status === "active");
  const subscriber = subscriptionPayload.subscription || payload.subscription || readerState.readerEntitlements.find((item) => item.entitlement_type === "subscriber" && item.status === "active");
  const worldPass = readerState.readerEntitlements.find((item) => item.entitlement_type === "world_pass" && item.status === "active");
  const effectiveTier = subscriptionPayload.effective_tier || payload.effective_tier || subscriber?.tier_id || null;
  const emailVerified = Boolean(subscriptionPayload.email_verified);
  readerDom.readerEntitlementType.textContent = subscriber
    ? subscriber.tier_id || "subscriber"
    : worldPass
      ? "world_pass"
      : credits
        ? credits.wallet_type || "credits"
        : "trial";
  if (readerDom.readerSubscriptionStatus) {
    readerDom.readerSubscriptionStatus.textContent = subscriber?.status || "inactive";
  }
  readerDom.readerCreditBalance.textContent = credits ? String(Number(credits.balance || 0).toFixed(0)) : "-";
  const activePaywall = readerState.latestStep?.paywall || readerState.sessionPaywall || {};
  if (readerDom.readerWorldUnlockStatus) {
    readerDom.readerWorldUnlockStatus.textContent = worldUnlockLabel(activePaywall);
  }
  if (readerDom.readerEntitlementReason) {
    readerDom.readerEntitlementReason.textContent = accessReasonLabel(activePaywall.reason || subscriber?.reason || worldPass?.reason || credits?.reason || "trial_chapter");
  }
  clearNode(readerDom.readerEntitlementList);
  if (!readerState.readerEntitlements.length) {
    clearNode(readerDom.readerEntitlementList, "这里会显示当前会员权益与剩余点数。");
  } else {
    readerState.readerEntitlements.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.wallet_type || item.tier_id || item.entitlement_type}</h3>
          <span class="list-card-score">${item.status}</span>
        </div>
        <p class="list-card-body">适用范围 ${item.world_id ? "当前世界" : "全站"}\n剩余额度 ${item.balance ?? "-"}\n访问原因 ${accessReasonLabel(item.reason)}\n到期时间 ${item.expires_at || "-"}</p>
      `;
      readerDom.readerEntitlementList.appendChild(card);
    });
  }
  if (payload.subscription) {
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${effectiveTier ? tierLabel(effectiveTier) : (payload.subscription.tier_id || "subscription")}</h3>
        <span class="list-card-score">${payload.subscription.status || "-"}</span>
      </div>
      <p class="list-card-body">价格 ${payload.subscription.price_usd_monthly ? `$${payload.subscription.price_usd_monthly}/月` : "-"}\n当前状态 ${payload.subscription.status || "-"}\n有效会员 ${effectiveTier ? tierLabel(effectiveTier) : "-"}\n周期结束 ${payload.subscription.period_end || "-"}\n说明 ${payload.subscription.lifecycle_reason || "-"}\n建议动作 ${payload.recommended_action || "-"}\n邮箱验证 ${emailVerified ? "已验证" : "待验证"}</p>
    `;
    readerDom.readerEntitlementList.prepend(card);
  }
  if (readerDom.readerAccessNote && !emailVerified && (subscriptionPayload.email_address || "").includes("@")) {
    readerDom.readerAccessNote.textContent = "当前账号邮箱尚未验证。建议先完成邮箱验证，再继续真实支付与跨端恢复。";
  }
  clearNode(readerDom.readerMembershipOffers);
  const tiers = subscriptionPayload.tiers || [];
  const providerStatus = subscriptionPayload.checkout_provider_status || payload.checkout_provider_status || {};
  if (!tiers.length) {
    clearNode(readerDom.readerMembershipOffers, "这里会显示可选会员方案与解锁入口。");
  } else {
    if (shellState.debug && providerStatus.provider === "stripe" && providerStatus.configured === false) {
      const note = document.createElement("article");
      note.className = "list-card";
      note.innerHTML = `
        <div class="list-card-head">
          <h3>支付配置未完成</h3>
          <span class="list-card-score">内部提示</span>
        </div>
        <p class="list-card-body">当前支付通道尚未配置完成，需先补齐价格映射、密钥与回调配置，再进行真实订阅调试。</p>
      `;
      readerDom.readerMembershipOffers.appendChild(note);
    }
    tiers.forEach((tier) => {
      const card = document.createElement("article");
      card.className = "list-card";
      if (subscriber?.tier_id === tier.tier_id) {
        card.classList.add("is-selected");
      }
      const buttonLabel = subscriber?.tier_id === tier.tier_id ? "当前方案" : `开始 ${tier.tier_id}`;
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${tierLabel(tier.tier_id)}</h3>
          <span class="list-card-score">$${Number(tier.price_usd_monthly || 0).toFixed(0)}/month</span>
        </div>
        <p class="list-card-body">${tier.description || "-"}\n阅读权益 ${tier.reader_access ? "可用" : "不可用"}\n创作权益 ${tier.author_access || "无"}\n每月故事点数 ${tier.monthly_story_credits ?? 0}\n每月创作点数 ${tier.monthly_studio_credits ?? 0}\n附加能力 ${(tier.capabilities ? Object.entries(tier.capabilities).filter(([, value]) => value).map(([key]) => key).join(" / ") : "-") || "-"}</p>
        <div class="composer-actions">
          <button class="ghost-action reader-tier-checkout">${buttonLabel}</button>
        </div>
      `;
      const button = card.querySelector(".reader-tier-checkout");
      if (subscriber?.tier_id === tier.tier_id) {
        button.disabled = true;
      } else {
        button.addEventListener("click", () => startReaderCheckout(tier.tier_id));
      }
      readerDom.readerMembershipOffers.appendChild(card);
    });
  }
  clearNode(readerDom.readerCheckoutStatus);
  if (!readerState.readerCheckoutSession) {
    clearNode(readerDom.readerCheckoutStatus, "这里会显示最近一次支付状态。");
  } else {
    const checkout = readerState.readerCheckoutSession;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${tierLabel(checkout.tier_id)}</h3>
        <span class="list-card-score">${checkout.status || "-"}</span>
      </div>
      <p class="list-card-body">支付状态 ${checkout.status || "-"}\n有效截止 ${checkout.expires_at || "-"}\n解锁方案 ${tierLabel(checkout.tier_id) || "-"}</p>
    `;
    readerDom.readerCheckoutStatus.appendChild(card);
  }
  if (payload.lifecycle_history_summary?.latest_events?.length) {
    payload.lifecycle_history_summary.latest_events.slice(0, 4).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.event_type || "-"}</h3>
          <span class="list-card-score">${item.status || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n状态 ${item.status || "-"}\n支付说明 ${item.reason || item.provider || "-"}</p>
      `;
      readerDom.readerCheckoutStatus.appendChild(card);
    });
  }
}

function clearPendingCheckoutReturn() {
  readerState.pendingCheckoutSessionId = null;
  readerState.pendingCheckoutStatus = null;
  persistPendingCheckoutContext(null);
}

async function completePendingCheckoutReturn() {
  const checkoutStatus = readerState.pendingCheckoutStatus;
  const checkoutSessionId = readerState.pendingCheckoutSessionId;
  const checkoutContext = readerState.pendingCheckoutContext;
  if (!checkoutStatus) {
    return;
  }
  if (checkoutStatus === "cancel") {
    applyCheckoutContext(checkoutContext);
    if (checkoutContext?.sessionId) {
      shellState.pendingSessionId = checkoutContext.sessionId;
      shellState.readerWorkspace = checkoutContext.readerWorkspace || "read";
    }
    clearPendingCheckoutReturn();
    syncProductMode();
    reportUiMessage("你刚刚取消了支付；当前账号与阅读进度都已保留。", "warning");
    return;
  }
  if (checkoutStatus !== "success") {
    clearPendingCheckoutReturn();
    syncProductMode();
    return;
  }
  if (!checkoutSessionId) {
    clearPendingCheckoutReturn();
    syncProductMode();
    reportUiMessage("支付结果同步信息不完整，暂时无法自动更新会员状态。", "warning");
    return;
  }
  try {
    applyCheckoutContext(checkoutContext);
    const payload = await api(`/v1/reader/checkout/${encodeURIComponent(checkoutSessionId)}/complete`, {
      method: "POST",
      body: JSON.stringify({
        account_id:
          readerState.readerAuthSession?.identity?.account_id ||
          checkoutContext?.accountId ||
          undefined,
        reader_id:
          readerState.readerAuthSession?.identity?.actor_id ||
          checkoutContext?.readerActorId ||
          undefined,
      }),
    });
    if (payload.account_id) {
      readerState.readerId = payload.account_id;
      if (readerDom.readerIdInput) {
        readerDom.readerIdInput.value = payload.account_id;
      }
      if (!readerState.readerAuthSession?.identity?.actor_id && readerDom.readerAuthActorId) {
        readerDom.readerAuthActorId.value = checkoutContext?.readerActorId || payload.account_id;
      }
    }
    if (checkoutContext?.sessionId) {
      shellState.pendingSessionId = checkoutContext.sessionId;
      shellState.readerWorkspace = checkoutContext.readerWorkspace || "read";
    }
    if (checkoutContext?.activeView) {
      readerState.activeView = checkoutContext.activeView;
    }
    readerState.readerCheckoutSession = payload.checkout || readerState.readerCheckoutSession;
    clearPendingCheckoutReturn();
    await refreshReaderEntitlements();
    syncProductMode();
    reportUiMessage(
      checkoutContext?.sessionId
        ? "支付已完成，当前会员状态已同步，并已准备回到你刚才那段故事。"
        : "支付已完成，当前会员状态与点数已经同步。",
      "success"
    );
  } catch (error) {
    clearPendingCheckoutReturn();
    syncProductMode();
    reportUiMessage(`支付结果同步失败：${error.message}`, "warning");
  }
}

async function startReaderCheckout(tierId = "play_pass") {
  const accountId = activeReaderId();
  const restore = setBusy(readerDom.readerStartCheckout, "创建中…");
  try {
    const payload = await api("/v1/reader/checkout/start", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        tier_id: tierId,
        reader_id: readerState.readerAuthSession?.identity?.actor_id || accountId,
      }),
    });
    readerState.readerCheckoutSession = payload.checkout;
    persistPendingCheckoutContext({
      createdAt: Date.now(),
      accountId,
      readerActorId: readerState.readerAuthSession?.identity?.actor_id || accountId,
      displayName: readerState.readerAuthSession?.identity?.display_name || readerState.readerAuthSession?.identity?.actor_id || accountId,
      checkoutSessionId: payload.checkout?.checkout_session_id || payload.checkout?.session_id || null,
      tierId,
      worldId: readerState.worldId,
      sessionId: readerState.sessionId,
      readerWorkspace: shellState.readerWorkspace,
      activeView: readerState.activeView,
    });
    renderLatestStep();
    await refreshReaderEntitlements();
    updateStatus();
    syncProductMode();
    if (payload.checkout?.provider === "stripe" && payload.checkout?.checkout_url) {
      window.open(payload.checkout.checkout_url, "_blank", "noopener,noreferrer");
    }
    reportUiMessage(`已创建 ${tierLabel(tierId)} 的支付请求，系统会在当前阅读路径里继续追踪状态。`, "success");
  } catch (error) {
    if (error?.detail?.code === "email_verification_required_for_billing") {
      reportUiMessage("当前账号还没完成邮箱验证。先点“发送验证邮件”，完成验证后再继续支付。", "warning");
      return;
    }
    reportUiMessage(`创建支付请求失败：${error.message}`, "error");
  } finally {
    restore();
  }
}

async function openReaderCustomerPortal() {
  const accountId = activeReaderId();
  try {
    const payload = await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/portal`, {
      method: "POST",
      body: JSON.stringify({ return_url: `${window.location.origin}/app` }),
    });
    if (payload.portal?.portal_url) {
      window.open(payload.portal.portal_url, "_blank", "noopener,noreferrer");
    }
    reportUiMessage("已打开订阅管理入口。", "success");
  } catch (error) {
    reportUiMessage(`打开订阅管理失败：${error.message}`, "error");
  }
}

async function retryReaderSubscriptionPayment() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/retry-payment`, { method: "POST" });
    await refreshReaderEntitlements();
    reportUiMessage("已发起支付重试。", "success");
  } catch (error) {
    reportUiMessage(`重试支付失败：${error.message}`, "error");
  }
}

function currentReaderQualityTraceId() {
  return (
    readerState.latestStep?.quality_trace_id ||
    readerState.latestStep?.chapter_view?.quality_trace_id ||
    readerState.latestStepFailure?.quality_trace_id ||
    null
  );
}

async function submitReaderQualityFeedback(feedback) {
  const traceId = currentReaderQualityTraceId();
  if (!traceId) {
    reportUiMessage("当前章节还没有可关联的质量 trace，暂时不能提交反馈。", "warning");
    return;
  }
  try {
    await api("/v1/reader/quality-feedback", {
      method: "POST",
      body: JSON.stringify({
        trace_id: traceId,
        feedback,
        reason_code: readerDom.readerQualityFeedbackReason?.value || null,
        note: readerDom.readerQualityFeedbackNote?.value.trim() || null,
      }),
    });
    reportUiMessage("反馈已提交，运营面板中的 trace detail 会看到这条记录。", "success");
  } catch (error) {
    reportUiMessage(`提交反馈失败：${error.message}`, "error");
  }
}

async function renewReaderSubscription() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/renew`, { method: "POST" });
    await refreshReaderEntitlements();
    reportUiMessage("订阅续费请求已提交。", "success");
  } catch (error) {
    reportUiMessage(`续费失败：${error.message}`, "error");
  }
}

async function cancelReaderSubscription() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/cancel`, { method: "POST" });
    await refreshReaderEntitlements();
    reportUiMessage("订阅已标记为到期取消。", "success");
  } catch (error) {
    reportUiMessage(`取消订阅失败：${error.message}`, "error");
  }
}

async function grantReaderEntitlement() {
  const readerId = activeReaderId();
  const entitlementType = readerDom.grantEntitlementType?.value || "credits";
  const payload = {
    reader_id: readerId,
    entitlement_type: entitlementType === "story_credits" ? "credits" : entitlementType,
  };
  if (entitlementType === "story_credits") {
    payload.wallet_type = "story_credits";
    payload.balance = Number(readerDom.grantEntitlementBalance?.value || 3);
  }
  if (entitlementType === "world_pass" && readerState.worldId) {
    payload.world_id = readerState.worldId;
  }
  try {
    await api("/v1/reader/entitlements/grant", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshReaderEntitlements();
    updateStatus();
    reportUiMessage("测试 entitlement 已授予。", "success");
  } catch (error) {
    reportUiMessage(`授予测试 entitlement 失败：${error.message}`, "error");
  }
}

function buildReaderPrologue() {
  if (!readerState.currentBundle) return null;
  const meta = worldDisplayMeta(readerState.currentBundle);
  const suggested = readerState.currentBundle.player_inputs?.[0]?.raw_input || "我想先看看这条命会把我带去哪里。";
  return {
    chapterTitle: `${readerState.currentBundle.label} · 序章`,
    recap: `世界已经就位，但真正的章节还没落笔。先确认这条命的气味、代价和入口，再写下你的第一句心意。`,
    body:
      `${readerState.currentBundle.description || "这是一个还未真正展开的世界。"}\n\n` +
      `此刻最重要的不是立刻做很多选择，而是先把第一步说清楚。这个世界更偏向 ${meta.mood}，适合从“${suggested}”这样的心意起笔。`,
    relationshipHints: [meta.hook, "先写一句心意，再看命运分岔。"],
    chapterIndex: 0,
  };
}

function recordReaderContinuityDiagnostic(key) {
  if (!key) return;
  const current = Number(readerState.continuityDiagnostics?.[key] || 0);
  readerState.continuityDiagnostics = {
    ...(readerState.continuityDiagnostics || {}),
    [key]: current + 1,
  };
}

function activeReaderQualityFailure() {
  if (readerState.continuityContract?.status === "quality_guard_failed" && readerState.latestStepFailure) {
    return readerState.latestStepFailure;
  }
  return null;
}

function activeReaderPaywall() {
  const latest = readerState.latestStep?.paywall || null;
  if (latest?.required) return latest;
  if (readerState.sessionPaywall?.required) return readerState.sessionPaywall;
  return null;
}

function buildReaderQualityGuardCard(stepFailure, options = {}) {
  if (!stepFailure || stepFailure.status !== "quality_guard_failed") return null;
  const card = document.createElement("section");
  const gate = stepFailure.quality_gate || {};
  const issues = (gate.issues || []).map((item) => item.issue_code).filter(Boolean);
  const contract = stepFailure.continuity_contract || {};
  card.className = `chapter-unlock-card chapter-unlock-card--quality${options.variant ? ` chapter-unlock-card--${options.variant}` : ""}`;
  card.innerHTML = `
    <p class="chapter-unlock-kicker">这一章先没有入库</p>
    <h3 class="chapter-unlock-title">当前阅读位置已保留，可以直接重试当前章。</h3>
    <p class="chapter-unlock-body">
      ${contract.message || gate.summary || "系统保留了当前 session、视图和上一章内容，方便你直接继续尝试。"}
    </p>
    <div class="chapter-unlock-meta">
      <span>当前文本：${Number(gate.actual_text_units || 0)}/${Number(gate.required_text_units || 0) || "-"}</span>
      <span>主要问题：${issues.join(" / ") || gate.enforced_decision || "rewrite"}</span>
      <span>推荐动作：重试当前章</span>
    </div>
    <div class="chapter-unlock-actions">
      <button class="primary-action chapter-quality-retry" type="button">重试当前章</button>
      <button class="ghost-action chapter-quality-return" type="button">返回上一章视图</button>
    </div>
  `;
  card.querySelector(".chapter-quality-retry")?.addEventListener("click", async () => {
    if (!readerDom.playerInput.value.trim()) {
      readerDom.playerInput.value = readerState.intentPrefill?.suggested_prefill || "我想再试一次。";
    }
    await stepSession();
  });
  card.querySelector(".chapter-quality-return")?.addEventListener("click", () => {
    readerState.activeView = "storybook";
    syncViewMode();
    renderStorybook();
  });
  return card;
}

function buildReaderUnlockCard(paywall, options = {}) {
  if (!paywall?.required) return null;
  const card = document.createElement("section");
  const tierText = paywall.required_display_name || (paywall.tier_id ? tierLabel(paywall.tier_id) : "继续阅读权益");
  const quoteText = paywall.quote !== undefined && paywall.quote !== null
    ? `¥${Number(paywall.quote).toFixed(2)}`
    : "按当前方案解锁";
  const balanceText = paywall.balance !== null && paywall.balance !== undefined
    ? `${Number(paywall.balance).toFixed(0)} 故事点数`
    : "暂无可用故事点数";
  const capabilityText = paywall.required_capability ? `需要 ${paywall.required_capability}` : "需要继续阅读权限";
  card.className = `chapter-unlock-card${options.variant ? ` chapter-unlock-card--${options.variant}` : ""}`;
  card.innerHTML = `
    <p class="chapter-unlock-kicker">这一章先停在这里</p>
    <h3 class="chapter-unlock-title">${accessReasonLabel(paywall.reason)}，继续前需要先解锁。</h3>
    <p class="chapter-unlock-body">
      ${capabilityText}。推荐通过 ${tierText} 继续，当前参考价格 ${quoteText}。
      解锁后，你会直接回到这一章后面的那条命运线，而不是重新开始。
    </p>
    <div class="chapter-unlock-meta">
      <span>当前世界：${worldUnlockLabel(paywall)}</span>
      <span>账户余额：${balanceText}</span>
      <span>推荐动作：解锁后继续阅读</span>
    </div>
    <div class="chapter-unlock-actions">
      <button class="primary-action chapter-unlock-checkout" type="button">解锁并继续阅读</button>
    </div>
  `;
  card.querySelector(".chapter-unlock-checkout")?.addEventListener("click", () => {
    startReaderCheckout(paywall.suggested_checkout_tier || paywall.tier_id || "play_pass");
  });
  return card;
}

function renderIntentPrefill() {
  let prefilled = false;
  if (!readerState.intentPrefill) {
    readerDom.currentPressureText.textContent = "故事还没真正卷起来。";
    readerDom.lastIntentText.textContent = "-";
    readerDom.suggestedPrefillText.textContent = "我想先看看这条命会把我带去哪里。";
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.updateStatus();
    }
    return;
  }
  readerDom.currentPressureText.textContent = readerState.intentPrefill.current_pressure || "上一章留下的余波还没散。";
  readerDom.lastIntentText.textContent = readerState.intentPrefill.last_player_intent || "-";
  readerDom.suggestedPrefillText.textContent = readerState.intentPrefill.suggested_prefill || "";
  if (!readerDom.playerInput.value.trim()) {
    readerDom.playerInput.value = readerState.intentPrefill.suggested_prefill || "";
    prefilled = Boolean(readerDom.playerInput.value.trim());
  }
  if (prefilled && typeof ShellStatusRuntime !== "undefined") {
    ShellStatusRuntime.updateStatus();
  }
}

function worldDisplayMeta(example) {
  const localizedLabel = String(example.label || "")
    .replace("Duty Route", "职责线")
    .replace("Romance Route", "情感线");
  if (example.example_id === "romance") {
    return {
      label: localizedLabel,
      mood: "爱 / 自我 / 迟疑",
      hook: "更适合试探、坦白和关系拉扯。",
    };
  }
  return {
    label: localizedLabel,
    mood: "职责 / 名誉 / 自我",
    hook: "更适合承诺、权衡和命运抉择。",
  };
}

function firstImageUrl(...values) {
  return values
    .map((value) => String(value || "").trim())
    .find((value) => value.startsWith("/") || value.startsWith("http://") || value.startsWith("https://")) || "";
}

function escapeImageAttr(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function mergeReaderSessionMedia(payload = {}) {
  const sessionPayload = payload.session || {};
  readerState.sessionMedia = {
    coverImage: firstImageUrl(
      payload.coverImage,
      sessionPayload.coverImage,
      readerState.sessionMedia?.coverImage
    ),
    atmosphereImage: firstImageUrl(
      payload.atmosphereImage,
      sessionPayload.atmosphereImage,
      readerState.sessionMedia?.atmosphereImage
    ),
  };
}

function resetReaderSessionMedia() {
  readerState.sessionMedia = { coverImage: "", atmosphereImage: "" };
}

function activeSessionSummary() {
  return (readerState.sessionLibrary || []).find((item) => item.session_id === readerState.sessionId) || null;
}

function activeReaderCoverImage() {
  const activeSession = activeSessionSummary();
  return firstImageUrl(
    readerState.sessionMedia?.coverImage,
    activeSession?.coverImage,
    readerState.latestStep?.coverImage
  );
}

function activeReaderAtmosphereImage() {
  return firstImageUrl(
    readerState.sessionMedia?.atmosphereImage,
    readerState.latestStep?.atmosphereImage,
    activeSessionSummary()?.atmosphereImage,
    activeReaderCoverImage()
  );
}

function cardImageMarkup(imageUrl, altText) {
  const safeUrl = firstImageUrl(imageUrl);
  if (!safeUrl) return "";
  return `
    <div class="reader-card-media">
      <img src="${escapeImageAttr(safeUrl)}" alt="${escapeImageAttr(altText)}" loading="lazy" decoding="async" />
    </div>
  `;
}

function cssImageUrl(imageUrl) {
  return String(imageUrl || "").replace(/["\\\n\r]/g, "");
}

function setStoryHeroImage(imageUrl) {
  if (!readerDom.storyHero) return;
  const safeUrl = firstImageUrl(imageUrl);
  readerDom.storyHero.classList.toggle("story-hero--with-image", Boolean(safeUrl));
  readerDom.storyHero.style.backgroundImage = safeUrl
    ? `linear-gradient(180deg, rgba(18, 16, 14, 0.12), rgba(18, 16, 14, 0.72)), url("${cssImageUrl(safeUrl)}")`
    : "";
}

function renderWorldGallery() {
  clearNode(readerDom.worldGallery);
  for (const example of readerState.examples) {
    const meta = worldDisplayMeta(example);
    const shelfWorld = readerState.shelfWorlds.find((item) => item.world_id === example.world_id);
    const accessState = shelfWorld?.access_state || "trial";
    const riskRating = shelfWorld?.risk_rating || "PG-13";
    const coverImage = firstImageUrl(shelfWorld?.coverImage, example.coverImage);
    const card = document.createElement("article");
    card.className = "world-card";
    card.dataset.exampleId = example.example_id;
    if (readerState.currentBundle?.example_id === example.example_id) {
      card.classList.add("is-selected");
    }
    card.innerHTML = `
      ${cardImageMarkup(coverImage, meta.label || example.label)}
      <p class="world-card-kicker">${accessState === "trial" ? "可先试读" : "可直接进入"}</p>
      <h3 class="world-card-title">${meta.label || example.label}</h3>
      <p class="world-card-body">${example.description}</p>
      <dl class="world-card-facts">
        <div>
          <dt>主题气味</dt>
          <dd>${meta.mood}</dd>
        </div>
        <div>
          <dt>适合玩法</dt>
          <dd>${meta.hook}</dd>
        </div>
        <div>
          <dt>访问层级</dt>
          <dd>${riskRating} / ${accessState}</dd>
        </div>
      </dl>
      <div class="world-card-meta">
        <span>当前推荐入口</span>
        <span>${readerState.currentBundle?.example_id === example.example_id ? "已选中" : "可切入"}</span>
      </div>
      <div class="world-card-actions">
        <button class="ghost-action world-card-preview">浏览这个世界</button>
        <button class="primary-action world-card-start">进入世界</button>
      </div>
    `;
    card.querySelector(".world-card-preview").addEventListener("click", async () => {
      await loadExampleBundle(example.example_id);
    });
    card.querySelector(".world-card-start").addEventListener("click", async (event) => {
      await loadExampleBundle(example.example_id);
      await bootstrapWorld(event.currentTarget);
    });
    readerDom.worldGallery.appendChild(card);
  }
}

function renderSessionLibrary() {
  clearNode(readerDom.sessionLibrary);
  if (!readerState.sessionLibrary.length) {
    clearNode(readerDom.sessionLibrary, "你还没有在这个世界里留下脚印。开始一段新旅程吧。");
    return;
  }

  for (const session of readerState.sessionLibrary) {
    const card = document.createElement("article");
    card.className = "session-card";
    if (readerState.sessionId === session.session_id) {
      card.classList.add("is-selected");
    }
    const coverImage = firstImageUrl(
      session.coverImage,
      readerState.sessionId === session.session_id ? readerState.sessionMedia?.coverImage : ""
    );
    card.innerHTML = `
      ${cardImageMarkup(coverImage, session.last_chapter_title || session.last_event_title || "旅程封面")}
      <p class="session-card-kicker">${readerState.sessionId === session.session_id ? "当前旅程" : "可安全续读"}</p>
      <h3 class="session-card-title">${session.last_chapter_title || session.last_event_title || "刚刚开始"}</h3>
      <p class="session-card-body">
        停在第 ${session.current_turn_index} 幕。${formatTimestamp(session.created_at)} 留下这段旅程，现在可以直接回到那一幕继续读。
      </p>
      <div class="session-card-meta">
        <span>最近章节：${session.last_chapter_title || session.last_event_title || "等待第一幕"}</span>
        <span>${session.last_chapter_title || session.last_event_title ? "继续最安全" : "等待第一幕"}</span>
      </div>
      <div class="session-card-actions">
        <button class="primary-action session-card-open">继续阅读</button>
      </div>
      <div class="session-card-utility">
        <button class="ghost-action session-card-delete">移出书架</button>
      </div>
    `;
    card.querySelector(".session-card-open").addEventListener("click", async (event) => {
      await restoreSession(session.session_id, event.currentTarget);
    });
    card.querySelector(".session-card-delete").addEventListener("click", async () => {
      await deleteSession(session.session_id);
    });
    readerDom.sessionLibrary.appendChild(card);
  }
}

function renderAuthoredWorkLibrary() {
  clearNode(readerDom.readerAuthoredWorkLibrary);
  const authoredAccountId = activeAuthoredWorkAccountId();
  if (!authoredAccountId) {
    clearNode(readerDom.readerAuthoredWorkLibrary, "登录作者账号后，这里会显示你自己创作的作品。");
    return;
  }
  if (!readerState.authoredWorkLibrary.length) {
    clearNode(readerDom.readerAuthoredWorkLibrary, "你还没有生成可阅读的作品稿。先去创作台初始化作品稿并生成至少一章。");
    return;
  }

  for (const work of readerState.authoredWorkLibrary) {
    const card = document.createElement("article");
    card.className = "session-card";
    if (readerState.activeAuthoredWorkPreview?.work_id === work.work_id) {
      card.classList.add("is-selected");
    }
    const chapterCount = Number(work.chapter_count || 0);
    const targetChapters = Number(work.target_chapter_count || 0);
    card.innerHTML = `
      ${cardImageMarkup(work.coverImage, work.title || work.work_id || "作品封面")}
      <p class="session-card-kicker">${chapterCount > 0 ? "我的作品" : "等待正文"}</p>
      <h3 class="session-card-title">${work.title || work.work_id}</h3>
      <p class="session-card-body">
        ${work.status || "draft"} · 章节 ${chapterCount}/${targetChapters || "-"}。
        ${chapterCount > 0 ? "可以直接按阅读视角查看已生成章节。" : "还没有可阅读正文，先去创作台生成章节。"}
      </p>
      <div class="session-card-meta">
        <span>${chapterCount > 0 ? "像读者一样阅读" : "先生成章节"}</span>
        <span>${work.world_version_id || work.work_id}</span>
      </div>
      <div class="session-card-actions">
        <button class="primary-action authored-work-open"${chapterCount > 0 ? "" : " disabled"}>${chapterCount > 0 ? "像读者一样阅读" : "还未生成正文"}</button>
      </div>
      <div class="session-card-utility">
        <button class="ghost-action authored-work-edit">回创作台</button>
        <button class="ghost-action authored-work-delete">删除作品</button>
      </div>
    `;
    card.querySelector(".authored-work-open")?.addEventListener("click", async () => {
      await openAuthoredWorkPreview(work.work_id);
    });
    card.querySelector(".authored-work-edit")?.addEventListener("click", async () => {
      shellState.activeProduct = "author";
      authorState.activeDraftVersionId = work.world_version_id || authorState.activeDraftVersionId;
      ShellStatusRuntime.syncProductMode();
      await AuthorWorkspaceRuntime.refreshAuthorSurface();
    });
    card.querySelector(".authored-work-delete")?.addEventListener("click", async () => {
      await deleteAuthoredWork(work.work_id, work.title || work.work_id);
    });
    readerDom.readerAuthoredWorkLibrary.appendChild(card);
  }
}

function renderSuggestedInputs() {
  clearNode(readerDom.suggestedInputs);
  if (!readerState.currentBundle) return;
  for (const item of readerState.currentBundle.player_inputs) {
    const fragment = readerDom.suggestionTemplate.content.cloneNode(true);
    const button = fragment.querySelector("button");
    button.textContent = item.raw_input;
    button.addEventListener("click", () => {
      readerDom.playerInput.value = item.raw_input;
      readerState.selectedIntentOverride = item.intent_vector || null;
      updateStatus();
    });
    readerDom.suggestedInputs.appendChild(fragment);
  }
}

async function refreshAuthoredWorkLibrary() {
  const authoredAccountId = activeAuthoredWorkAccountId();
  if (!authoredAccountId) {
    readerState.authoredWorkLibrary = [];
    renderAuthoredWorkLibrary();
    return;
  }
  try {
    const payload = await api(`/v1/author/works?account_id=${encodeURIComponent(authoredAccountId)}`);
    readerState.authoredWorkLibrary = payload.works || [];
  } catch (_error) {
    readerState.authoredWorkLibrary = [];
  }
  renderAuthoredWorkLibrary();
}

async function openAuthoredWorkPreview(workId) {
  if (!workId) return;
  const payload = await api(`/v1/author/works/${encodeURIComponent(workId)}`);
  readerState.activeAuthoredWorkPreview = payload;
  readerState.worldId = null;
  readerState.sessionId = null;
  readerState.currentState = null;
  readerState.latestStep = null;
  readerState.latestStepFailure = null;
  readerState.continuityContract = null;
  readerState.latestPreview = null;
  readerState.replay = null;
  readerState.selectedReplayIndex = null;
  readerState.activeView = "experience";
  readerState.worldVersionId = payload.world_version_id || null;
  setReaderWorkspace("read", { silent: true });
  renderAuthoredWorkLibrary();
  updateBundleSummary();
  updateStatus();
  renderLatestStep();
  renderReplay();
  renderRoutePreview();
  syncProductMode();
  readerDom.storyFeed?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteAuthoredWork(workId, title = "") {
  if (!workId) return;
  const workLabel = String(title || "这部作品").trim() || "这部作品";
  const confirmed = window.confirm(`删除后《${workLabel}》及其平行宇宙会一起移除，已生成章节也会被删除，确定继续吗？`);
  if (!confirmed) return;
  try {
    const deleted = await api(`/v1/author/works/${encodeURIComponent(workId)}`, { method: "DELETE" });
    const deletedIds = new Set((deleted.deleted_work_ids || []).map((item) => String(item)));
    if (readerState.activeAuthoredWorkPreview && deletedIds.has(String(readerState.activeAuthoredWorkPreview.work_id || ""))) {
      clearAuthoredWorkPreview();
      readerState.worldVersionId = null;
      readerState.sessionId = null;
      readerState.currentState = null;
      readerState.latestStep = null;
      readerState.latestPreview = null;
      readerState.replay = null;
      resetReaderSessionMedia();
      readerState.selectedReplayIndex = null;
      readerState.activeView = "experience";
      setReaderWorkspace("landing", { silent: true });
      renderRoutePreview();
      renderLatestStep();
      renderReplay();
    }
    readerState.authoredWorkLibrary = readerState.authoredWorkLibrary.filter(
      (item) => !deletedIds.has(String(item.work_id || ""))
    );
    renderAuthoredWorkLibrary();
    await refreshAuthoredWorkLibrary();
    updateStatus();
    syncProductMode();
    reportUiMessage(`已删除《${workLabel}》及其 ${deleted.deleted_work_count || 1} 条命运线。`, "success");
  } catch (error) {
    reportUiMessage(`删除作品失败：${error.message}`, "error");
  }
}

function renderRoutePreview() {
  if (!readerState.latestPreview?.routes?.length) {
    clearNode(readerDom.routePreview, "还没有看到命运分岔。先开始一段旅程，再点“看看接下来”。");
    return;
  }
  clearNode(readerDom.routePreview);
  const ranks = ["最有可能", "另一种走向", "隐秘支线"];
  const routes = readerState.latestPreview.routes.slice(0, 3);
  routes.forEach((route, index) => {
    const leadEvent = route.events?.[0];
    const line = document.createElement("div");
    line.className = "route-line";
    line.innerHTML = `
      <span class="route-rank">${ranks[index] || "可能的命运"}</span>
      <strong>${leadEvent?.title || route.event_ids.join(" → ")}</strong>
      <span class="list-card-score">命运热度 ${route.total_score.toFixed(3)}</span>
      <p class="list-card-body">${leadEvent?.summary || route.explanation || "这一条走向还没有更细的叙事说明。"}\n${index === 0 ? "最值得先看的，是它会把你立刻推向哪里。" : "这是一条备选走向，用来帮助你判断这一幕还能怎样偏转。"}</p>
    `;
    readerDom.routePreview.appendChild(line);
  });
  for (let index = routes.length; index < 3; index += 1) {
    const line = document.createElement("div");
    line.className = "route-line route-line--placeholder";
    line.innerHTML = `
      <span class="route-rank">${ranks[index]}</span>
      <strong>暂时没有更稳妥的备选走向</strong>
      <span class="list-card-score">等待新的心意</span>
      <p class="list-card-body">等你把下一句心意写得更明确，系统才会展开更多足够可信的命运分岔。</p>
    `;
    readerDom.routePreview.appendChild(line);
  }
}

function spotlightPreviewResult() {
  if (!readerDom.routePreviewPanel) return;
  readerDom.routePreviewPanel.classList.remove("is-highlighted");
  void readerDom.routePreviewPanel.offsetWidth;
  readerDom.routePreviewPanel.classList.add("is-highlighted");
  readerDom.routePreviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    readerDom.routePreviewPanel?.classList.remove("is-highlighted");
  }, 1400);
}

function spotlightChapter() {
  if (!readerDom.chapterPanel) return;
  readerDom.chapterPanel.classList.remove("is-highlighted");
  void readerDom.chapterPanel.offsetWidth;
  readerDom.chapterPanel.classList.add("is-highlighted");
  readerDom.chapterPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    readerDom.chapterPanel?.classList.remove("is-highlighted");
  }, 1400);
}

function renderCards(target, items, formatter, emptyText) {
  clearNode(target);
  if (!items.length) {
    clearNode(target, emptyText);
    return;
  }
  target.classList.remove("empty-state");
  for (const item of items) {
    const fragment = readerDom.listCardTemplate.content.cloneNode(true);
    const title = fragment.querySelector("h3");
    const score = fragment.querySelector(".list-card-score");
    const body = fragment.querySelector(".list-card-body");
    const formatted = formatter(item);
    title.textContent = formatted.title;
    score.textContent = formatted.score;
    body.textContent = formatted.body;
    if (formatted.active) {
      fragment.querySelector(".list-card").classList.add("is-active");
    }
    target.appendChild(fragment);
  }
}

function setTone(tone) {
  readerState.activeTone = tone;
  for (const pill of readerDom.tonePills) {
    pill.classList.toggle("is-active", pill.dataset.tone === tone);
  }
  renderStorybook();
  renderStoryFeed();
}

function getStorySource() {
  if (readerState.selectedReplayIndex !== null && readerState.replay?.event_trace?.[readerState.selectedReplayIndex]) {
    return {
      event: readerState.replay.event_trace[readerState.selectedReplayIndex],
      rendered: readerState.replay.rendered_scenes?.[readerState.selectedReplayIndex] || null,
      reader_view: readerState.replay.reader_views?.[readerState.selectedReplayIndex] || null,
      index: readerState.selectedReplayIndex,
    };
  }
  if (readerState.latestStep?.chosen_event) {
    return {
      event: readerState.latestStep.chosen_event,
      rendered: readerState.latestStep.rendered_scene,
      reader_view: readerState.latestStep.reader_view || null,
      index: null,
    };
  }
  return null;
}

function renderStorybook() {
  const source = getStorySource();
  const prologue = !source && readerState.sessionId ? buildReaderPrologue() : null;
  const activePaywall = activeReaderPaywall();
  const activeQualityFailure = activeReaderQualityFailure();
  if (!source && !prologue) {
    setStoryHeroImage("");
    readerDom.storyHero.dataset.motif = "";
    readerDom.storyTitle.textContent = "画面会在这里展开";
    readerDom.storyCaption.textContent = "推进一幕之后，这里会变成一张带情绪和光影的故事画面。";
    if (readerDom.storyRecap) {
      readerDom.storyRecap.textContent = "当你进入章节后，这里会先把上一章到这一章之间真正重要的变化说清楚。";
    }
    readerDom.storyQuote.textContent = "当故事开始流动，这里会出现一句最能代表这一幕的引句。";
    readerDom.storyPrompt.textContent = "-";
    readerDom.storyMotif.textContent = "-";
    clearNode(readerDom.storyBeats, "这里会显示这一幕最值得抓住的三个节拍。");
    clearNode(readerDom.storyDetails, "这里会显示画面中的气味、动作和情绪提示。");
    readerDom.storyProse.textContent = "这里会显示图文版本对应的正文。";
    clearNode(readerDom.storySequence, "故事累积起来后，这里会变成一条可以回看的章节画卷。");
    return;
  }

  if (prologue) {
    const meta = worldDisplayMeta(readerState.currentBundle);
    setStoryHeroImage(activeReaderCoverImage());
    readerDom.storyHero.dataset.motif = readerState.currentBundle.example_id === "romance" ? "temptation" : "discovery";
    readerDom.storyTitle.textContent = prologue.chapterTitle;
    readerDom.storyCaption.textContent = readerState.currentBundle.description || "这是旅程真正开写之前的入口页。";
    if (readerDom.storyRecap) {
      readerDom.storyRecap.textContent = prologue.recap;
    }
    readerDom.storyQuote.textContent = readerState.currentBundle.player_inputs?.[0]?.raw_input || "先写下你真正想做的第一件事。";
    readerDom.storyPrompt.textContent = meta.hook;
    readerDom.storyMotif.textContent = meta.mood;
    clearNode(readerDom.storyBeats);
    ["先判断是否继续旧旅程", "再决定从哪个世界起笔", "最后写下第一句心意"].forEach((beat) => {
      const node = document.createElement("span");
      node.className = "story-beat";
      node.textContent = beat;
      readerDom.storyBeats.appendChild(node);
    });
    clearNode(readerDom.storyDetails);
    [meta.mood, "序章态", "等待第一幕"].forEach((detail) => {
      const node = document.createElement("span");
      node.className = "story-detail";
      node.textContent = detail;
      readerDom.storyDetails.appendChild(node);
    });
    readerDom.storyProse.textContent = prologue.body;
    readerDom.storyProse.parentElement?.querySelector(".chapter-unlock-card--storybook")?.remove();
    if (activePaywall) {
      const card = buildReaderUnlockCard(activePaywall, { variant: "storybook" });
      if (card) {
        readerDom.storyProse.parentElement?.appendChild(card);
      }
    } else if (activeQualityFailure) {
      const card = buildReaderQualityGuardCard(activeQualityFailure, { variant: "storybook" });
      if (card) {
        readerDom.storyProse.parentElement?.appendChild(card);
      }
    }
    clearNode(readerDom.storySequence, "真正推进之后，这里会变成一条按章节回看的时间线。");
    return;
  }

  const rendered = source.rendered || {};
  const readerView = source.reader_view || {};
  const sceneCard = readerView.scene_card || {};
  setStoryHeroImage(activeReaderAtmosphereImage());
  readerDom.storyHero.dataset.motif = rendered.image_motif || source.event.scene_function || "";
  readerDom.storyTitle.textContent = readerView.chapter_title || rendered.story_title || source.event.title || "当前剧情";
  readerDom.storyCaption.textContent = readerView.recap || rendered.chapter_summary || rendered.image_caption || source.event.summary || "暂无说明。";
  if (readerDom.storyRecap) {
    readerDom.storyRecap.textContent = readerView.recap || rendered.chapter_summary || source.event.summary || "这一章还没有可用的 recap。";
  }
  readerDom.storyQuote.textContent = sceneCard.quote || rendered.pull_quote || "这一幕还没有留下自己的引句。";
  readerDom.storyPrompt.textContent = sceneCard.summary || rendered.visual_prompt || "暂无 visual prompt";
  readerDom.storyMotif.textContent = sceneCard.palette_hint || rendered.image_motif || source.event.scene_function || "-";
  clearNode(readerDom.storyBeats);
  const beatItems = sceneCard.story_beats || rendered.story_beats || [];
  if (beatItems.length) {
    beatItems.forEach((beat) => {
      const node = document.createElement("span");
      node.className = "story-beat";
      node.textContent = beat;
      readerDom.storyBeats.appendChild(node);
    });
  } else {
    clearNode(readerDom.storyBeats, "这里会显示这一幕最值得抓住的三个节拍。");
  }
  clearNode(readerDom.storyDetails);
  const detailItems = sceneCard.visual_details || rendered.visual_details || [];
  if (detailItems.length) {
    detailItems.forEach((detail) => {
      const node = document.createElement("span");
      node.className = "story-detail";
      node.textContent = detail;
      readerDom.storyDetails.appendChild(node);
    });
  } else {
    clearNode(readerDom.storyDetails, "这里会显示画面中的气味、动作和情绪提示。");
  }
  readerDom.storyProse.textContent =
    readerView.body ||
    rendered[readerState.activeTone] ||
    rendered.premium_prose ||
    source.event.summary ||
    "暂无正文。";
  readerDom.storyProse.parentElement?.querySelector(".chapter-unlock-card--storybook")?.remove();
  if (activePaywall) {
    const card = buildReaderUnlockCard(activePaywall, { variant: "storybook" });
    if (card) {
      readerDom.storyProse.parentElement?.appendChild(card);
    }
  } else if (activeQualityFailure) {
    const card = buildReaderQualityGuardCard(activeQualityFailure, { variant: "storybook" });
    if (card) {
      readerDom.storyProse.parentElement?.appendChild(card);
    }
  }

  clearNode(readerDom.storySequence);
  if (!readerState.replay?.event_trace?.length) {
    clearNode(readerDom.storySequence, "故事累积起来后，这里会变成一条可以回看的章节画卷。");
    return;
  }

  readerState.replay.event_trace.forEach((event, index) => {
    const renderedScene = readerState.replay.rendered_scenes?.[index] || {};
    const readerView = readerState.replay.reader_views?.[index] || {};
    const card = document.createElement("article");
    card.className = "story-sequence-card";
    if (index === readerState.selectedReplayIndex) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <h3>Turn ${index + 1} · ${readerView.chapter_title || renderedScene.story_title || event.title}</h3>
      <p class="list-card-body">${readerView.recap || renderedScene.chapter_summary || renderedScene.image_caption || event.summary}</p>
    `;
    card.addEventListener("click", () => {
      readerState.selectedReplayIndex = index;
      renderReplay();
      renderStorybook();
    });
    readerDom.storySequence.appendChild(card);
  });
}

function renderLatestStep() {
  if (readerState.activeAuthoredWorkPreview) {
    const activeWork = readerState.activeAuthoredWorkPreview;
    const chapters = activeWork.chapters || [];
    const latestChapter = chapters[chapters.length - 1] || null;
    readerDom.chosenEventTitle.textContent = activeWork.title || "我的作品";
    readerDom.bestRoute.textContent = chapters.length
      ? `这是你的作品只读预览，当前已生成 ${chapters.length} 章。你可以像读者一样顺序查看，再回创作台继续修改。`
      : "这份作品稿还没有可阅读章节。";
    clearNode(readerDom.scoredCandidates, "作者作品只读预览不提供路线比较。");
    clearNode(readerDom.criticTrace, "作者作品只读预览不显示候选诊断轨迹。");
    readerDom.lastEventTitle.textContent = latestChapter?.chapter_title || "-";
    readerDom.paywallBanner.classList.add("is-hidden");
    renderStorybook();
    renderStoryFeed();
    renderIntentPrefill();
    return;
  }
  if (!readerState.latestStep) {
    const prologue = readerState.sessionId ? buildReaderPrologue() : null;
    const qualityFailure = activeReaderQualityFailure();
    readerDom.chosenEventTitle.textContent = prologue?.chapterTitle || "故事还没开始";
    readerDom.bestRoute.textContent = qualityFailure
      ? (readerState.continuityContract?.message || "本章未入库，但当前 session 和上一章内容都还保留着，可以直接重试。")
      : prologue
        ? "旅程已经启动，但第一章还等你写下第一句心意。先判断这条命往哪边偏，再决定要不要真的踏出去。"
        : "当你写下一句心意，系统会在这里接住它。";
    clearNode(readerDom.storyFeed, "载入 world 并执行一步后，这里会按时间顺序出现连续章节。");
    clearNode(readerDom.scoredCandidates, "幕后会在这里比较不同走向。");
    clearNode(readerDom.criticTrace, "幕后会在这里解释为什么这条线更成立。");
    readerDom.lastEventTitle.textContent = prologue?.chapterTitle || "-";
    readerDom.paywallBanner.classList.add("is-hidden");
    renderStorybook();
    renderStoryFeed();
    renderIntentPrefill();
    return;
  }

  const readerView = readerState.latestStep.reader_view || {};
  readerDom.chosenEventTitle.textContent = readerView.chapter_title || readerState.latestStep.chosen_event.title;
  readerDom.lastEventTitle.textContent = readerView.chapter_title || readerState.latestStep.chosen_event.title;
  readerDom.bestRoute.textContent = readerState.latestStep.routes?.length
    ? (() => {
        const routeEvents = readerState.latestStep.routes[0].events || [];
        const titles = routeEvents.map((event) => event.title).filter(Boolean);
        if (!titles.length) return "主线已经开始往下一处更难退开的命运口子靠近。";
        if (titles.length === 1) return `接下来更可能逼近的是：${titles[0]}。`;
        return `接下来更可能先逼近“${titles[0]}”，随后余波会把你带向“${titles[1]}”。`;
      })()
    : readerView.recap || "此刻还没有新的主线判断。";

  const batch = readerState.latestStep.candidate_batch || { raw_candidates: [], legal_candidates: [], debug: {} };
  readerDom.candidateSummary.textContent =
    batch.raw_candidates?.length
      ? `系统刚才比对了 ${batch.raw_candidates.length} 种可能，留下 ${batch.legal_candidates.length} 条真正说得通的走向。`
      : "幕后会在这里比较不同走向。";

  renderCards(
    readerDom.scoredCandidates,
    readerState.latestStep.scored_candidates || [],
    (item) => ({
      title: item.event.title,
      score: `匹配度 ${item.total_score.toFixed(3)}`,
      body:
        `${item.explanation}\n` +
        (item.critic_decisions?.length
          ? item.critic_decisions
              .map((decision) => `${decision.critic_name}: ${decision.verdict} · ${decision.reasons.join(" / ")}`)
              .join("\n")
          : "这一条线没有额外诊断备注。"),
    }),
    "幕后会在这里比较不同走向。"
  );

  renderCards(
    readerDom.criticTrace,
    readerState.latestStep.critic_trace || [],
    (item) => ({
      title: item.event_id,
      score: `修正 ${Number(item.critic_penalty || 0).toFixed(3)}`,
      body:
        (item.critic_decisions || [])
          .map((decision) => `${decision.critic_name}: ${decision.verdict} · ${decision.reasons.join(" / ")}`)
          .join("\n") || "这一步没有额外诊断。",
    }),
    "幕后会在这里解释为什么这条线更成立。"
  );

  readerDom.paywallBanner.classList.add("is-hidden");
  if (readerDom.paywallBannerCheckout) {
    readerDom.paywallBannerCheckout.onclick = null;
  }
  for (const pill of readerDom.tonePills) {
    pill.classList.toggle("is-active", pill.dataset.tone === readerState.activeTone);
  }
  renderStorybook();
  renderStoryFeed();
  renderIntentPrefill();
}

function renderStoryFeed() {
  const activePaywall = activeReaderPaywall();
  const activeQualityFailure = activeReaderQualityFailure();
  const chapters = [];
  if (readerState.activeAuthoredWorkPreview?.chapters?.length) {
    readerState.activeAuthoredWorkPreview.chapters.forEach((chapter) => {
      const issueCodes = (chapter.latest_diagnostic_summary || {}).issue_codes || [];
      const chapterTask = chapter.chapter_task || {};
      chapters.push({
        chapterTitle: chapter.chapter_title,
        recap: chapter.summary,
        body: chapter.body,
        relationshipHints: [
          chapterTask.duty_type ? `任务 ${chapterTask.duty_type}` : "",
          ...issueCodes.slice(0, 2),
        ].filter(Boolean),
        chapterIndex: chapter.chapter_index || 0,
      });
    });
  } else if (readerState.replay?.reader_views?.length) {
    readerState.replay.reader_views.forEach((readerView, index) => {
      chapters.push({
        chapterTitle: readerView.chapter_title,
        recap: readerView.recap,
        body: readerView.body,
        relationshipHints: readerView.relationship_hints || [],
        chapterIndex: readerView.chapter_index || index + 1,
      });
    });
  } else if (readerState.latestStep?.reader_view) {
    chapters.push({
      chapterTitle: readerState.latestStep.reader_view.chapter_title,
      recap: readerState.latestStep.reader_view.recap,
      body: readerState.latestStep.reader_view.body,
      relationshipHints: readerState.latestStep.reader_view.relationship_hints || [],
      chapterIndex: readerState.latestStep.reader_view.chapter_index || 1,
    });
  } else if (readerState.sessionId) {
    const prologue = buildReaderPrologue();
    if (prologue) {
      chapters.push(prologue);
    }
  }

  clearNode(readerDom.storyFeed);
  if (!chapters.length) {
    clearNode(readerDom.storyFeed, "载入 world 并执行一步后，这里会按时间顺序出现连续章节。");
    return;
  }

  chapters.forEach((chapter, index) => {
    const card = document.createElement("article");
    card.className = "story-feed-card";
    if (index === chapters.length - 1) {
      card.classList.add("is-active");
    }
    const chapterLabel = Number(chapter.chapterIndex || 0) > 0 ? `第 ${chapter.chapterIndex} 章` : "序章";
    card.innerHTML = `
      <div class="story-feed-head">
        <p class="panel-label">${chapterLabel}</p>
        <h3>${chapter.chapterTitle}</h3>
      </div>
      <p class="story-feed-recap">${chapter.recap || ""}</p>
      <div class="story-feed-body">${chapter.body || ""}</div>
      ${chapter.relationshipHints.length ? `<div class="story-feed-hints">${chapter.relationshipHints.map((hint) => `<span>${hint}</span>`).join("")}</div>` : ""}
    `;
    if (index === chapters.length - 1 && activePaywall) {
      const unlockCard = buildReaderUnlockCard(activePaywall, { variant: "feed" });
      if (unlockCard) {
        card.appendChild(unlockCard);
      }
    } else if (index === chapters.length - 1 && activeQualityFailure) {
      const qualityCard = buildReaderQualityGuardCard(activeQualityFailure, { variant: "feed" });
      if (qualityCard) {
        card.appendChild(qualityCard);
      }
    }
    readerDom.storyFeed.appendChild(card);
  });
}

function renderReplay() {
  if (!readerState.replay?.event_trace?.length) {
    clearNode(readerDom.replayTimeline, "推进几幕之后，这里会变成一条可回看的章节轨迹。");
    renderStorybook();
    return;
  }
  renderCards(
    readerDom.replayTimeline,
    readerState.replay.event_trace.map((event, index) => ({
      event,
      index,
      promises: readerState.replay.promise_ledger_snapshots[index] || [],
      readerView: readerState.replay.reader_views?.[index] || {},
    })),
    ({ event, index, promises, readerView }) => ({
      title: `Turn ${index + 1} · ${readerView.chapter_title || event.title}`,
      score: event.scene_function || "",
      body:
        `${readerView.recap || event.summary}\n` +
        `未解牵挂: ${promises.length}\n` +
        `Tags: ${(event.tags || []).join(", ")}`,
      active: index === readerState.selectedReplayIndex,
    }),
    "推进几幕之后，这里会变成一条可回看的章节轨迹。"
  );
  renderStorybook();
}

function updateBundleSummary() {
  if (readerState.activeAuthoredWorkPreview) {
    const activeWork = readerState.activeAuthoredWorkPreview;
    const chapterCount = Number(activeWork.chapter_count || (activeWork.chapters || []).length || 0);
    const targetCount = Number(activeWork.target_chapter_count || 0);
    readerDom.worldTitle.textContent = `我的作品 · ${activeWork.title || activeWork.work_id || "未命名作品"}`;
    readerDom.worldDescription.textContent = "这里展示的是你自己创作出的章节正文，可按读者视角连续阅读，不会推进读者会话。";
    readerDom.featuredWorldTitle.textContent = activeWork.title || "我的作品";
    readerDom.featuredWorldCopy.textContent = "把已生成章节摊开读一遍，检查情绪、节奏和关系推进，再回创作台继续修改。";
    readerDom.featuredWorldMood.textContent = `${chapterCount}/${targetCount || "-"} 章`;
    readerDom.featuredWorldHook.textContent = activeWork.status || "draft";
    if (readerDom.readerFeaturedStart) {
      readerDom.readerFeaturedStart.disabled = true;
    }
    return;
  }
  if (!readerState.currentBundle) {
    readerDom.worldTitle.textContent = "选择一个世界";
    readerDom.worldDescription.textContent = "先挑一个世界，再开始一段新的命运旅程。";
    readerDom.featuredWorldTitle.textContent = "先挑一个世界，再开始一段新的命运旅程。";
    readerDom.featuredWorldCopy.textContent = "你会在这里看到这个世界的主命题、情绪底色，以及这一轮旅程最适合怎样推进。";
    readerDom.featuredWorldMood.textContent = "-";
    readerDom.featuredWorldHook.textContent = "-";
    if (readerDom.readerFeaturedStart) {
      readerDom.readerFeaturedStart.disabled = true;
    }
    return;
  }
  const meta = worldDisplayMeta(readerState.currentBundle);
    readerDom.worldTitle.textContent = meta.label || readerState.currentBundle.label;
    readerDom.worldDescription.textContent = readerState.currentBundle.description;
    readerDom.featuredWorldTitle.textContent = meta.label || readerState.currentBundle.label;
  readerDom.featuredWorldCopy.textContent = readerState.currentBundle.description;
  readerDom.featuredWorldMood.textContent = meta.mood;
  readerDom.featuredWorldHook.textContent = meta.hook;
  if (readerDom.readerFeaturedStart) {
    readerDom.readerFeaturedStart.disabled = false;
  }
}

async function loadExampleBundle(exampleId) {
  readerState.currentBundle = await api(`/v1/examples/${exampleId}`);
  const localizedMeta = worldDisplayMeta(readerState.currentBundle);
  if (localizedMeta.label) {
    readerState.currentBundle.label = localizedMeta.label;
  }
  readerState.worldId = readerState.currentBundle.world_bible.world_id;
  readerState.selectedIntentOverride = null;
  if (!readerState.sessionId) {
    setReaderWorkspace("landing", { silent: true });
  }
  updateBundleSummary();
  renderWorldGallery();
  renderSuggestedInputs();
  await refreshSessionLibrary();
  await refreshReaderEntitlements();
  updateStatus();
}

async function refreshExamples() {
  const payload = await api("/v1/examples");
  readerState.examples = payload.examples;
  const shelfPayload = await api("/v1/library/worlds");
  readerState.shelfWorlds = shelfPayload.worlds;
  const selected = readerState.examples.find((item) => item.example_id === "demo") || readerState.examples[0];
  if (selected) {
    await loadExampleBundle(selected.example_id);
  }
  await refreshAuthoredWorkLibrary();
  syncProductMode();
}

async function refreshSessionLibrary() {
  if (readerState.activeAuthoredWorkPreview) {
    renderSessionLibrary();
    return;
  }
  if (!readerState.currentBundle) {
    readerState.sessionLibrary = [];
    renderSessionLibrary();
    return;
  }
  if (!readerState.readerAuthSession?.accessToken && !(readerState.readerAuthSession?.cookieBacked && readerState.readerAuthSession?.identity)) {
    readerState.sessionLibrary = [];
    renderSessionLibrary();
    return;
  }
  const payload = await api(`/v1/sessions?world_id=${encodeURIComponent(readerState.currentBundle.world_bible.world_id)}`);
  readerState.sessionLibrary = payload.sessions;
  const activeSession = activeSessionSummary();
  if (activeSession) {
    mergeReaderSessionMedia(activeSession);
  }
  renderSessionLibrary();
}

async function bootstrapWorld(triggerButton = null) {
  if (!readerState.currentBundle) return;
  const restore = triggerButton ? setBusy(triggerButton, "进入中…") : () => {};
  try {
    readerState.activeAuthoredWorkPreview = null;
    const worldPayload = {
      world_bible: readerState.currentBundle.world_bible,
      event_atoms: readerState.currentBundle.event_atoms,
      metadata: { source: "frontend_bootstrap" },
    };
    const worldResult = await api("/v1/worlds", {
      method: "POST",
      body: JSON.stringify(worldPayload),
    });
    const sessionResult = await api("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        world_id: worldResult.world_id,
        initial_state: readerState.currentBundle.initial_state,
        player_profile: { surface: "app", reader_id: activeReaderId() },
        metadata: { reader_id: activeReaderId() },
      }),
    });

    readerState.worldId = worldResult.world_id;
    readerState.worldVersionId = sessionResult.world_version_id || null;
    readerState.sessionPaywall = sessionResult.paywall || null;
    readerState.sessionId = sessionResult.session_id;
    resetReaderSessionMedia();
    mergeReaderSessionMedia(sessionResult);
    readerState.currentState = sessionResult.current_state;
    readerState.intentPrefill = {
      last_player_intent: "",
      current_pressure: "故事刚刚开始。",
      suggested_prefill: "我想先试探眼前这条路到底会把我带到哪一边。",
    };
    readerState.latestStep = null;
    readerState.latestStepFailure = null;
    readerState.continuityContract = null;
    readerState.latestPreview = null;
    readerState.replay = null;
    readerState.selectedReplayIndex = null;
    setReaderWorkspace("read", { silent: true });

    await refreshSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderRoutePreview();
    renderLatestStep();
    renderReplay();
    syncProductMode();
    reportUiMessage("旅程已经开始，接下来可以先阅读当前章，再写下一句心意。", "success");
  } catch (error) {
    reportUiMessage(`开始旅程失败：${error.message}`, "error");
  } finally {
    restore();
  }
}

async function restoreSession(sessionId, triggerButton = null) {
  if (!sessionId) return;
  const restore = triggerButton ? setBusy(triggerButton, "回到这一幕…") : () => {};
  try {
    readerState.activeAuthoredWorkPreview = null;
    const sessionPayload = await api(`/v1/sessions/${sessionId}`);
    const replayPayload = await api(`/v1/sessions/${sessionId}/replay`);
    const matchingExample = readerState.examples.find((item) => item.world_id === sessionPayload.session.world_id);
    if (matchingExample && readerState.currentBundle?.example_id !== matchingExample.example_id) {
      readerState.currentBundle = await api(`/v1/examples/${matchingExample.example_id}`);
      updateBundleSummary();
      renderWorldGallery();
      renderSuggestedInputs();
    }
    readerState.sessionId = sessionId;
    resetReaderSessionMedia();
    mergeReaderSessionMedia(sessionPayload);
    readerState.currentState = sessionPayload.session.current_state;
    readerState.sessionPaywall = sessionPayload.paywall || null;
    readerState.latestStep = sessionPayload.latest_step;
    readerState.latestStepFailure = null;
    readerState.continuityContract = null;
    readerState.replay = replayPayload;
    readerState.worldId = sessionPayload.session.world_id;
    readerState.worldVersionId = sessionPayload.world_version_id || sessionPayload.session.metadata?.world_version_id || null;
    readerState.readerId = sessionPayload.session.metadata?.reader_id || readerState.readerId;
    readerState.intentPrefill = sessionPayload.intent_prefill || (await api(`/v1/sessions/${sessionId}/prefill`));
    readerState.selectedReplayIndex = replayPayload.event_trace.length
      ? replayPayload.event_trace.length - 1
      : null;
    readerState.activeView = "experience";
    setReaderWorkspace("read", { silent: true });
    shellState.pendingSessionId = null;
    recordReaderContinuityDiagnostic("restore_success_count");
    renderSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderLatestStep();
    renderReplay();
    syncProductMode();
    spotlightChapter();
  } catch (error) {
    reportUiMessage(`继续旅程失败：${error.message}`, "error");
  } finally {
    restore();
  }
}

async function deleteSession(sessionId) {
  if (!sessionId) return;
  const confirmed = window.confirm("删除后这段旅程会从书架中移除，确定继续吗？");
  if (!confirmed) return;
  try {
    await api(`/v1/sessions/${sessionId}`, { method: "DELETE" });
    if (readerState.sessionId === sessionId) {
      readerState.sessionId = null;
      readerState.currentState = null;
      readerState.latestStep = null;
      readerState.latestStepFailure = null;
      readerState.continuityContract = null;
      readerState.latestPreview = null;
      readerState.replay = null;
      resetReaderSessionMedia();
      readerState.selectedReplayIndex = null;
      readerState.activeView = "experience";
      setReaderWorkspace("landing", { silent: true });
      renderRoutePreview();
      renderLatestStep();
      renderReplay();
    }
    await refreshSessionLibrary();
    updateStatus();
    syncProductMode();
  } catch (error) {
    reportUiMessage(`删除失败：${error.message}`, "error");
  }
}

async function previewRoute() {
  if (!readerState.currentBundle || !readerState.currentState) return;
  const restore = setBusy(readerDom.previewRoute, "预览中…");
  try {
    const previewState =
      typeof structuredClone === "function"
        ? structuredClone(readerState.currentState)
        : JSON.parse(JSON.stringify(readerState.currentState));
    if (readerState.selectedIntentOverride) {
      previewState.player_intent = readerState.selectedIntentOverride;
    }
    readerState.latestPreview = await api("/v1/routes/preview", {
      method: "POST",
      body: JSON.stringify({
        world: readerState.currentBundle.world_bible,
        state: previewState,
        candidate_events: readerState.currentBundle.event_atoms,
        beam_width: 3,
        depth: 2,
      }),
    });
    renderRoutePreview();
    spotlightPreviewResult();
  } catch (error) {
    reportUiMessage(`没能看到下一步：${error.message}`, "error");
  } finally {
    restore();
  }
}

async function stepSession() {
  if (!readerState.sessionId) return;
  const playerInput = readerDom.playerInput.value.trim();
  if (!playerInput) {
    reportUiMessage("先写下一句你现在真正想做的事。", "warning");
    return;
  }
  const restore = setBusy(readerDom.stepSession, "执行中…");
  try {
    const previousContinuityStatus = String(readerState.continuityContract?.status || "");
    const stepPath = `/v1/sessions/${readerState.sessionId}/step${shellState.debug ? "?debug=true" : ""}`;
    const stepResult = await api(stepPath, {
      method: "POST",
      body: JSON.stringify({
        player_input: playerInput,
        intent_override: readerState.selectedIntentOverride,
        beam_width: 3,
        depth: 2,
        metadata: { reader_id: activeReaderId() },
      }),
    });
    mergeReaderSessionMedia(stepResult);
    readerState.continuityContract = stepResult.continuity_contract || null;
    if (stepResult.code === "chapter_quality_guard_failed" || stepResult.status === "quality_guard_failed") {
      readerState.latestStepFailure = stepResult;
      readerState.sessionPaywall = stepResult.paywall || readerState.sessionPaywall;
      setReaderWorkspace("read", { silent: true });
      recordReaderContinuityDiagnostic("quality_guard_context_retained_count");
      if (previousContinuityStatus === "payment_required") {
        recordReaderContinuityDiagnostic("post_checkout_resume_success_count");
      }
      await refreshReaderEntitlements();
      updateStatus();
      renderLatestStep();
      renderReplay();
      renderStorybook();
      renderStoryFeed();
      reportUiMessage(
        stepResult.continuity_contract?.message ||
          `本章未入库：${Number((stepResult.quality_gate || {}).actual_text_units || 0)}/${Number((stepResult.quality_gate || {}).required_text_units || 0) || "-"} 字。`,
        "warning"
      );
      return;
    }
    if (stepResult.status && stepResult.status !== "ok") {
      readerState.latestStepFailure = null;
      readerState.sessionPaywall = stepResult.paywall || readerState.sessionPaywall;
      setReaderWorkspace("read", { silent: true });
      if (stepResult.status === "payment_required") {
        recordReaderContinuityDiagnostic("paywall_resume_ready_count");
      }
      await refreshReaderEntitlements();
      updateStatus();
      renderLatestStep();
      renderReplay();
      reportUiMessage(
        stepResult.continuity_contract?.message || `继续前需要先解锁：${accessReasonLabel(stepResult.paywall?.reason)}。`,
        "warning"
      );
      return;
    }
    readerState.latestStep = stepResult;
    readerState.latestStepFailure = null;
    readerState.currentState = readerState.latestStep.updated_state;
    readerState.worldVersionId = readerState.latestStep.world_version_id || readerState.worldVersionId;
    readerState.sessionPaywall = readerState.latestStep.paywall || readerState.sessionPaywall;
    if (previousContinuityStatus === "payment_required") {
      recordReaderContinuityDiagnostic("post_checkout_resume_success_count");
    }
    readerState.replay = await api(`/v1/sessions/${readerState.sessionId}/replay`);
    readerState.intentPrefill = await api(`/v1/sessions/${readerState.sessionId}/prefill`);
    readerState.selectedReplayIndex = readerState.replay.event_trace.length
      ? readerState.replay.event_trace.length - 1
      : null;
    await refreshSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderLatestStep();
    renderReplay();
    reportUiMessage("这一幕已经推进，新的章节和回放都已更新。", "success");
  } catch (error) {
    reportUiMessage(`这一幕没能推进：${error.message}`, "error");
  } finally {
    restore();
  }
}

function resetOutput() {
  readerState.latestStep = null;
  readerState.latestStepFailure = null;
  readerState.continuityContract = null;
  readerState.latestPreview = null;
  readerState.replay = null;
  readerState.intentPrefill = null;
  readerState.selectedReplayIndex = null;
  readerDom.playerInput.value = "";
  renderRoutePreview();
  renderLatestStep();
  renderReplay();
  clearStatusBanner();
}

async function bootstrapHealth() {
  try {
    const payload = await api("/health", { headers: {} });
    shellDom.apiStatus.textContent = payload.status === "ok" ? "在线" : "异常";
  } catch (error) {
    shellDom.apiStatus.textContent = "离线";
  }
}
let readerEventsBound = false;
let readerRuntimeInitialized = false;

function bindReaderEvents() {
  if (readerEventsBound) return;
  readerEventsBound = true;
  readerDom.previewRoute?.addEventListener("click", previewRoute);
  readerDom.stepSession?.addEventListener("click", stepSession);
  readerDom.resetOutput?.addEventListener("click", resetOutput);
  readerDom.playerInput?.addEventListener("input", () => {
    readerState.selectedIntentOverride = null;
    updateStatus();
  });
  readerDom.viewExperience?.addEventListener("click", () => {
    readerState.activeView = "experience";
    syncViewMode();
  });
  readerDom.viewStorybook?.addEventListener("click", () => {
    readerState.activeView = "storybook";
    syncViewMode();
    renderStorybook();
  });
  readerDom.viewBackstage?.addEventListener("click", () => {
    readerState.activeView = "backstage";
    syncViewMode();
  });
  readerDom.readerJumpSessions?.addEventListener("click", () => {
    readerDom.sessionLibrary?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  readerDom.readerJumpWorlds?.addEventListener("click", () => {
    readerDom.worldGallery?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  readerDom.readerJumpAuthoredWorks?.addEventListener("click", () => {
    readerDom.readerAuthoredWorkLibrary?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  readerDom.readerStartCurrentWorld?.addEventListener("click", async (event) => {
    try {
      if (!readerState.currentBundle) {
        await refreshExamples();
      }
      await bootstrapWorld(event.currentTarget);
    } catch (error) {
      reportUiMessage(`开始新旅程失败：${error.message}`, "error");
    }
  });
  readerDom.readerFeaturedStart?.addEventListener("click", async (event) => {
    try {
      await bootstrapWorld(event.currentTarget);
    } catch (error) {
      reportUiMessage(`开始新旅程失败：${error.message}`, "error");
    }
  });
  readerDom.readerReturnLanding?.addEventListener("click", () => {
    clearAuthoredWorkPreview();
    setReaderWorkspace("landing");
    updateBundleSummary();
    renderSessionLibrary();
    renderAuthoredWorkLibrary();
    renderLatestStep();
  });
  readerDom.readerBackstageClose?.addEventListener("click", () => {
    readerState.activeView = shellState.lastReaderView || "experience";
    syncViewMode();
  });
  readerDom.readerRefreshEntitlements?.addEventListener("click", refreshReaderEntitlements);
  readerDom.readerAuthRegister?.addEventListener("click", registerReaderAuthIdentity);
  readerDom.readerAuthLogin?.addEventListener("click", loginReaderAuthIdentity);
  readerDom.readerAuthLogout?.addEventListener("click", logoutReaderAuthIdentity);
  readerDom.readerAuthRequestVerification?.addEventListener("click", requestReaderEmailVerification);
  readerDom.readerAuthRequestPasswordReset?.addEventListener("click", requestReaderPasswordReset);
  readerDom.readerGrantEntitlement?.addEventListener("click", grantReaderEntitlement);
  readerDom.readerStartCheckout?.addEventListener("click", () => startReaderCheckout());
  readerDom.readerManageSubscription?.addEventListener("click", openReaderCustomerPortal);
  readerDom.readerRetryPayment?.addEventListener("click", retryReaderSubscriptionPayment);
  readerDom.readerRenewSubscription?.addEventListener("click", renewReaderSubscription);
  readerDom.readerCancelSubscription?.addEventListener("click", cancelReaderSubscription);
  readerDom.readerQualityFeedbackPositive?.addEventListener("click", () => submitReaderQualityFeedback("thumbs_up"));
  readerDom.readerQualityFeedbackNegative?.addEventListener("click", () => submitReaderQualityFeedback("thumbs_down"));
  readerDom.readerIdInput?.addEventListener("change", refreshReaderEntitlements);

  for (const pill of readerDom.tonePills) {
    pill.addEventListener("click", () => setTone(pill.dataset.tone));
  }
}

function initializeReaderRuntime() {
  if (readerRuntimeInitialized) return;
  readerRuntimeInitialized = true;

  bindReaderEvents();
  restoreReaderAuthSession();
  restorePendingCheckoutContext();
  renderReaderAuthStatus();
  hydrateReaderAuthSession();

  bootstrapHealth();
  if (readerDom.readerIdInput) {
    readerDom.readerIdInput.value = readerDom.readerIdInput.value || readerState.readerId;
  }
  updateStatus();
  renderLatestStep();
  renderRoutePreview();
  renderReplay();
  renderIntentPrefill();
  refreshExamples().then(async () => {
    if (readerState.pendingCheckoutStatus) {
      await completePendingCheckoutReturn();
    }
    if (shellState.pendingSessionId) {
      await restoreSession(shellState.pendingSessionId);
    }
  }).catch((error) => {
    reportUiMessage(`初始化示例书架失败：${error.message}`, "error");
  });
}

  return {
    activeReaderId,
    mirrorReaderAuthSession,
    refreshReaderEntitlements,
    completePendingCheckoutReturn,
    startReaderCheckout,
    openReaderCustomerPortal,
    registerReaderAuthIdentity,
    loginReaderAuthIdentity,
    requestReaderEmailVerification,
    requestReaderPasswordReset,
    hydrateReaderAuthSession,
    logoutReaderAuthIdentity,
    retryReaderSubscriptionPayment,
    renewReaderSubscription,
    cancelReaderSubscription,
    grantReaderEntitlement,
    renderIntentPrefill,
    worldDisplayMeta,
    renderWorldGallery,
    renderSessionLibrary,
    renderSuggestedInputs,
    renderRoutePreview,
    spotlightPreviewResult,
    spotlightChapter,
    setTone,
    getStorySource,
    renderStorybook,
    renderLatestStep,
    renderStoryFeed,
    renderReplay,
    updateBundleSummary,
    loadExampleBundle,
    refreshAuthoredWorkLibrary,
    openAuthoredWorkPreview,
    refreshExamples,
    refreshSessionLibrary,
    bootstrapWorld,
    restoreSession,
    deleteSession,
    previewRoute,
    stepSession,
    resetOutput,
    bootstrapHealth,
    bindReaderEvents,
    initializeReaderRuntime,
  };
})();
