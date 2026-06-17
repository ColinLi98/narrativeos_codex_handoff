// Shell status orchestration extracted from app.js.

var ShellStatusRuntime = (() => {
  const shellDom = ShellDOM;
  const readerDom = ReaderDOM;
  const { reportUiMessage, clearNode, createListCard } = UIShared;
  const { tierLabel, accessReasonLabel, worldUnlockLabel } = ReaderAccessors;
  const REVIEWER_ROLES = new Set(["reviewer", "ops", "admin"]);
  const CUSTOMER_ROLES = new Set(["customer", "reviewer", "ops", "admin"]);
  const ROLE_PROFILES = {
    guest: {
      label: "访客",
      surfaces: ["阅读", "创作"],
      summary: "可以先浏览世界与创作台，登录后再把权限和身份固定下来。",
      nextStep: "先登录一个账号，系统会按后台分配的权限打开对应能力。",
    },
    reader: {
      label: "阅读账号",
      surfaces: ["阅读"],
      summary: "当前账号只有阅读能力，不会展开创作和审阅收件箱。",
      nextStep: "如需创作或审阅，请联系管理员调整账号权限。",
    },
    author: {
      label: "普通用户",
      surfaces: ["阅读", "创作"],
      summary: "可以继续阅读、创建草稿、修改人物和场景，但不会看到可审阅内容。",
      nextStep: "推荐进入创作台继续起稿或修稿。",
    },
    customer: {
      label: "客户账号",
      surfaces: ["客户"],
      summary: "当前账号进入客户工作台，查看套餐、限额、生命周期和后续商业报告。",
      nextStep: "推荐先确认当前 plan、限额和续费状态。",
    },
    reviewer: {
      label: "审阅者",
      surfaces: ["阅读", "创作", "客户", "审阅"],
      summary: "会展开 reviewer inbox、待审稿件与快速审批动作。",
      nextStep: "推荐直接进入账户协作查看可审阅内容。",
    },
    ops: {
      label: "运营审阅",
      surfaces: ["阅读", "创作", "客户", "审阅", "运营"],
      summary: "除了审阅内容，还可以切到运营视图处理治理、发布和告警。",
      nextStep: "可先查看 reviewer inbox，再根据需要切运营台。",
    },
    admin: {
      label: "管理员",
      surfaces: ["阅读", "创作", "客户", "审阅", "运营"],
      summary: "拥有完整的审阅和运营视图，会同时展开 reviewer 内容与 ops 入口。",
      nextStep: "先确认待审内容，再进入运营台处理跨域动作。",
    },
  };

  function appAccessAuthenticated() {
    return Boolean(authorState.authorAuthSession?.identity || authorState.authorAuthSession?.accessToken);
  }

  function authPageActive() {
    return Boolean(shellState.authPage);
  }

  function currentShellIdentity() {
    return authorState.authorAuthSession?.identity || null;
  }

  function currentShellRole() {
    return String(currentShellIdentity()?.actor_role || "").trim() || "guest";
  }

  function currentShellRoleProfile() {
    return ROLE_PROFILES[currentShellRole()] || ROLE_PROFILES.guest;
  }

  function reviewerContentEnabled() {
    return REVIEWER_ROLES.has(currentShellRole());
  }

  function customerViewEnabled() {
    return CUSTOMER_ROLES.has(currentShellRole());
  }

  function renderShellSessionSummary() {
    const identity = currentShellIdentity();
    const profile = currentShellRoleProfile();
    shellDom.shellSessionSummary?.classList.toggle("is-hidden", !identity);
    if (shellDom.shellSessionCopy) {
      shellDom.shellSessionCopy.textContent = identity
        ? `${identity.display_name || identity.actor_id || identity.account_id || "-"} · ${profile.label} · 可进入 ${profile.surfaces.join(" / ")}`
        : "登录后，这里会显示当前账号与权限。";
    }
  }

  function hasPrivilegedOpsIdentity() {
    return reviewerContentEnabled();
  }

  function opsViewEnabled() {
    return Boolean(shellState.debug || shellState.adminViewEnabled || hasPrivilegedOpsIdentity());
  }

  function renderShellAuthStage() {
    clearNode(shellDom.shellAuthStatus);
    const identity = currentShellIdentity();
    const role = currentShellRole();
    const profile = currentShellRoleProfile();
    const displayName = identity?.display_name || identity?.actor_id || identity?.account_id || "未登录";
    const actorId = identity?.actor_id || identity?.account_id || "";

    shellDom.appShell.dataset.role = role;
    shellDom.appShell.dataset.reviewer = reviewerContentEnabled() ? "on" : "off";
    shellDom.appShell.dataset.authenticated = appAccessAuthenticated() ? "on" : "off";
    shellDom.shellAuthStage?.classList.toggle("is-authenticated", Boolean(identity));

    if (shellDom.shellAuthHeadline) {
      if (!identity && shellState.authPage === "signup") {
        shellDom.shellAuthHeadline.textContent = "用邮箱注册 NarrativeOS。";
      } else if (!identity && shellState.authPage === "login") {
        shellDom.shellAuthHeadline.textContent = "用邮箱登录 NarrativeOS。";
      } else {
        shellDom.shellAuthHeadline.textContent = identity
          ? `${displayName}，当前是${profile.label}工作区。`
          : "登录后，进入你的工作区。";
      }
    }
    if (shellDom.shellAuthCopy) {
      if (!identity && shellState.authPage === "signup") {
        shellDom.shellAuthCopy.textContent = "邮箱注册会先发送验证邮件。验证完成后，你就可以正常登录、继续阅读和使用后续账号能力。";
      } else if (!identity && shellState.authPage === "login") {
        shellDom.shellAuthCopy.textContent = "如果你的邮箱还没验证，系统会明确提示你先完成验证，并提供重新发送验证邮件的入口。";
      } else {
        shellDom.shellAuthCopy.textContent = identity
          ? `${profile.summary} ${profile.nextStep}`
          : "新注册账号默认是普通用户。审阅权限由管理员在后台分配，拥有权限的账号登录后会自动看到可审阅内容。";
      }
    }
    if (shellDom.shellAuthRoleSummary) {
      shellDom.shellAuthRoleSummary.textContent = identity
        ? `当前账号：${profile.label}。可进入 ${profile.surfaces.join(" / ")}。`
        : "注册会默认创建普通用户账号；如果管理员后续赋予审阅权限，登录时会自动进入对应能力。";
    }
    if (shellDom.shellAuthActorId && !shellDom.shellAuthActorId.value.trim() && actorId) {
      shellDom.shellAuthActorId.value = actorId;
    }
    if (shellDom.shellAuthDisplayName && !shellDom.shellAuthDisplayName.value.trim() && identity?.display_name) {
      shellDom.shellAuthDisplayName.value = identity.display_name;
    }

    shellDom.shellAuthStatus.appendChild(
      createListCard({
        title: identity ? `${displayName} · 已登录` : "尚未登录",
        score: identity ? profile.label : "等待身份",
        body:
          `账号 ${actorId || "-"}\n` +
          `角色 ${profile.label}\n` +
          `可进入 ${(profile.surfaces || []).join(" / ") || "-"}\n` +
          `审阅内容 ${reviewerContentEnabled() ? "已开启" : "未开启"}\n` +
          `${identity ? `下一步 ${profile.nextStep}` : "下一步 填写账号和密码后登录，或直接注册一个新账号。"}`
      })
    );
    renderShellSessionSummary();
  }

  function syncViewMode() {
    shellDom.appShell.dataset.view = readerState.activeView;
    if (readerState.activeView !== "backstage") {
      shellState.lastReaderView = readerState.activeView;
    }
    readerDom.viewExperience?.classList.toggle("is-active", readerState.activeView === "experience");
    readerDom.viewStorybook?.classList.toggle("is-active", readerState.activeView === "storybook");
    readerDom.viewBackstage?.classList.toggle("is-active", readerState.activeView === "backstage");
    readerDom.experienceView.classList.toggle("is-hidden", readerState.activeView !== "experience");
    readerDom.storybookView.classList.toggle("is-hidden", readerState.activeView !== "storybook");
    readerDom.backstageView.classList.toggle("is-hidden", readerState.activeView !== "backstage");
    if (shellState.activeProduct === "reader") {
      RouteSyncRuntime.syncShellRoute();
    }
  }

  function syncProductMode() {
    WorkspaceLayoutRuntime.initializeGuidedWorkspaces();
    const authenticated = appAccessAuthenticated();
    const routeAuthPage = authPageActive();
    if (!opsViewEnabled() && shellState.activeProduct === "ops") {
      shellState.activeProduct = "reader";
      shellState.opsWorkspace = "dashboard";
    }
    if (!customerViewEnabled() && shellState.activeProduct === "customer" && authenticated) {
      shellState.activeProduct = reviewerContentEnabled() ? "author" : "reader";
      shellState.customerWorkspace = "overview";
    }
    if (currentShellRole() === "customer" && shellState.activeProduct === "author") {
      shellState.activeProduct = "customer";
    }
    if (currentShellRole() === "customer" && shellState.activeProduct === "ops") {
      shellState.activeProduct = "customer";
      shellState.opsWorkspace = "dashboard";
    }
    if (!authenticated) {
      if (!["reader", "author"].includes(shellState.activeProduct)) {
        shellState.activeProduct = "reader";
      }
      const hasActiveReaderFlow = Boolean(
        readerState.sessionId ||
        shellState.pendingSessionId ||
        readerState.activeAuthoredWorkPreview ||
        readerState.pendingCheckoutStatus
      );
      if (shellState.activeProduct === "reader" && !hasActiveReaderFlow) {
        shellState.readerWorkspace = "landing";
      }
    }
    shellDom.appShell.dataset.product = shellState.activeProduct;
    shellDom.appShell.dataset.authPage = routeAuthPage ? "on" : "off";
    shellDom.appShell.dataset.debug = shellState.debug ? "on" : "off";
    shellDom.appShell.dataset.adminView = opsViewEnabled() ? "on" : "off";
    shellDom.appShell.dataset.reviewer = reviewerContentEnabled() ? "on" : "off";
    shellDom.appShell.dataset.authenticated = authenticated ? "on" : "off";
    shellDom.appShell.dataset.readerWorkspace = shellState.readerWorkspace || "";
    shellDom.appShell.dataset.authorWorkspace = shellState.authorWorkspace || "";
    shellDom.appShell.dataset.customerWorkspace = shellState.customerWorkspace || "";
    shellDom.appShell.dataset.opsWorkspace = shellState.opsWorkspace || "";
    shellDom.modeReader.classList.toggle("is-active", shellState.activeProduct === "reader");
    shellDom.modeAuthor.classList.toggle("is-active", shellState.activeProduct === "author");
    shellDom.modeCustomer?.classList.toggle("is-active", shellState.activeProduct === "customer");
    shellDom.modeOps.classList.toggle("is-active", shellState.activeProduct === "ops");
    shellDom.modeReader?.classList.toggle("is-hidden", routeAuthPage);
    shellDom.modeAuthor?.classList.toggle("is-hidden", routeAuthPage || currentShellRole() === "customer");
    shellDom.modeCustomer?.classList.toggle("is-hidden", routeAuthPage || !customerViewEnabled());
    shellDom.modeOps?.classList.toggle("is-hidden", routeAuthPage || !opsViewEnabled());
    const readerLandingActive = shellState.activeProduct === "reader" && shellState.readerWorkspace !== "read";
    const readerReadActive = shellState.activeProduct === "reader" && shellState.readerWorkspace === "read";
    readerDom.readerLanding?.classList.toggle("is-hidden", !readerLandingActive);
    readerDom.featuredWorld?.classList.toggle("is-hidden", shellState.activeProduct !== "reader");
    shellDom.readerShellV2?.classList.toggle("is-hidden", !readerReadActive);
    shellDom.readerShell.classList.toggle("is-hidden", !readerReadActive);
    shellDom.authorShell.classList.toggle("is-hidden", shellState.activeProduct !== "author");
    shellDom.customerShell.classList.toggle("is-hidden", shellState.activeProduct !== "customer");
    shellDom.opsShell.classList.toggle("is-hidden", shellState.activeProduct !== "ops");
    shellDom.shellAuthStage?.classList.toggle("is-hidden", routeAuthPage || readerReadActive);
    shellDom.authRouteStage?.classList.toggle("is-hidden", !routeAuthPage);
    document.querySelectorAll(".internal-only").forEach((node) => {
      node.classList.toggle("is-hidden", !shellState.debug);
    });
    if (readerDom.readerDebugTools) {
      readerDom.readerDebugTools.classList.toggle("is-hidden", !shellState.debug);
    }
    if (readerDom.readerIdInput) {
      readerDom.readerIdInput.classList.toggle("is-hidden", !shellState.debug);
      readerDom.readerIdInput.previousElementSibling?.classList.toggle("is-hidden", !shellState.debug);
    }
    readerDom.readerEntitlementList?.classList.toggle("is-hidden", !shellState.debug && !readerState.readerEntitlements.length);
    readerDom.readerMembershipOffers?.classList.toggle(
      "is-hidden",
      !shellState.debug && !readerState.readerCheckoutSession && !readerState.sessionPaywall?.quote && !readerState.latestStep?.paywall?.quote
    );
    readerDom.readerCheckoutStatus?.classList.toggle("is-hidden", !shellState.debug && !readerState.readerCheckoutSession);
    if (shellDom.shellDebugToggle) {
      shellDom.shellDebugToggle.classList.toggle("is-hidden", !shellState.debug);
      shellDom.shellDebugToggle.classList.toggle("is-active", shellState.debug);
      shellDom.shellDebugToggle.setAttribute("aria-pressed", shellState.debug ? "true" : "false");
      shellDom.shellDebugToggle.textContent = shellState.debug ? "内部模式已开启" : "内部模式";
    }
    if (shellDom.shellProductStatus) {
      shellDom.shellProductStatus.textContent = !authenticated
        ? "未登录"
        : shellState.activeProduct === "reader"
          ? "阅读"
          : shellState.activeProduct === "author"
            ? "创作"
            : shellState.activeProduct === "customer"
              ? "客户"
              : "运营";
    }
    if (shellDom.shellContextCopy) {
      shellDom.shellContextCopy.textContent =
        !authenticated
          ? shellState.activeProduct === "author"
            ? "你可以先浏览创作台和填写 Brief；需要固定身份、邮箱能力或协作能力时，再登录账号。"
            : "先注册或登录，再按账号权限进入阅读、创作或审阅工作区。"
          : shellState.activeProduct === "reader"
            ? "先进入书架，再开始一段故事；需要时再切换阅读视图。"
            : shellState.activeProduct === "author"
              ? "创作台会按当前阶段组织功能，只展示此刻需要的能力。"
              : shellState.activeProduct === "customer"
                ? "客户工作台聚焦套餐、限额、生命周期与后续商业报告，不暴露运营原始面板。"
                : "运营台仅供内部人员使用，用于审核、发布、治理与排查。";
    }
    renderShellAuthStage();
    WorkspaceLayoutRuntime.syncWorkspaceStacks();
    WorkspaceLayoutRuntime.renderProductSubnav();
    syncViewMode();
    RouteSyncRuntime.syncShellRoute();
  }

  function updateStatus() {
    if (readerState.activeAuthoredWorkPreview) {
      const activeWork = readerState.activeAuthoredWorkPreview;
      const chapterCount = Number(activeWork.chapter_count || (activeWork.chapters || []).length || 0);
      const targetCount = Number(activeWork.target_chapter_count || 0);
      readerDom.worldStatus.textContent = "已加载";
      readerDom.sessionStatus.textContent = "作品阅读";
      readerDom.turnStatus.textContent = chapterCount ? String(chapterCount) : "-";
      if (shellDom.shellReaderId) {
        shellDom.shellReaderId.textContent =
          authorState.authorAuthSession?.identity?.display_name ||
          authorState.authorAuthSession?.identity?.account_id ||
          readerState.readerAuthSession?.identity?.display_name ||
          readerState.readerAuthSession?.identity?.account_id ||
          readerState.readerId ||
          "游客";
      }
      readerDom.worldVersionStatus.textContent = activeWork.world_version_id || "-";
      readerDom.accessTierStatus.textContent = "作者作品";
      readerDom.quoteStatus.textContent = "无需解锁";
      readerDom.worldId.textContent = "作者作品";
      readerDom.sessionId.textContent = `章节 ${chapterCount}/${targetCount || "-"}`;
      readerDom.previewRoute.disabled = true;
      readerDom.stepSession.disabled = true;
      readerDom.factCount.textContent = "0";
      readerDom.promiseCount.textContent = "0";
      readerDom.tensionValue.textContent = "0.00";
      readerDom.sceneWindow.textContent = "-";
      if (readerDom.readerWorldUnlockStatus) {
        readerDom.readerWorldUnlockStatus.textContent = "作者自有";
      }
      if (readerDom.readerEntitlementReason) {
        readerDom.readerEntitlementReason.textContent = "无需解锁";
      }
      if (readerDom.readerAccessNote) {
        readerDom.readerAccessNote.textContent = "当前是你自己的作品只读预览。若要继续生成、改写或修稿，请回创作台处理。";
      }
      if (readerDom.readerComposerHint) {
        readerDom.readerComposerHint.textContent = "这是你的作品只读预览。这里不会推进读者会话，返回创作台后再继续生成或编辑。";
      }
      if (readerDom.readerLandingSummary) {
        const authoredCount = Number(readerState.authoredWorkLibrary?.length || 0);
        const activeReader =
          authorState.authorAuthSession?.identity?.display_name ||
          authorState.authorAuthSession?.identity?.account_id ||
          readerState.readerAuthSession?.identity?.display_name ||
          readerState.readerAuthSession?.identity?.account_id ||
          readerState.readerId ||
          "游客";
        readerDom.readerLandingSummary.textContent = `${activeWork.title || "我的作品"} · ${activeReader} · 有 ${authoredCount} 部作品可读 · 当前作品已展开`;
      }
      return;
    }
    readerDom.worldStatus.textContent = readerState.worldId ? "已加载" : "未加载";
    readerDom.sessionStatus.textContent = readerState.sessionId ? "运行中" : "未创建";
    readerDom.turnStatus.textContent = readerState.currentState ? String(readerState.currentState.turn_index) : "-";
    if (shellDom.shellReaderId) {
      shellDom.shellReaderId.textContent =
        readerState.readerAuthSession?.identity?.display_name ||
        readerState.readerAuthSession?.identity?.account_id ||
        readerState.readerId ||
        "游客";
    }
    readerDom.worldVersionStatus.textContent = readerState.worldVersionId || "-";
    const activePaywall = readerState.latestStep?.paywall || readerState.sessionPaywall || {};
    const activeContinuityContract = readerState.continuityContract || {};
    const creditEntitlement = readerState.readerEntitlements.find((item) => item.entitlement_type === "credits" && item.status === "active");
    readerDom.accessTierStatus.textContent = activePaywall.access_tier || "试读";
    readerDom.quoteStatus.textContent = activePaywall.quote ? `¥${Number(activePaywall.quote).toFixed(2)}` : "¥0.00";
    readerDom.worldId.textContent = readerState.sessionId ? "已经开始" : "尚未启程";
    readerDom.sessionId.textContent = readerState.currentBundle
      ? (readerState.currentBundle.world_bible.creator_controls?.theme_targets || readerState.currentBundle.world_bible.themes || [])
          .slice(0, 3)
          .join(" / ") || "未设定"
      : "-";
    const hasPlayerInput = Boolean(readerDom.playerInput?.value.trim());
    readerDom.previewRoute.disabled = !readerState.currentState || !readerState.currentBundle || !hasPlayerInput;
    readerDom.stepSession.disabled = !readerState.sessionId || !hasPlayerInput;

    if (readerState.currentState) {
      readerDom.factCount.textContent = String(readerState.currentState.world_facts.length);
      readerDom.promiseCount.textContent = String(readerState.currentState.open_promises.length);
      readerDom.tensionValue.textContent = Number(readerState.currentState.tension).toFixed(2);
      readerDom.sceneWindow.textContent =
        readerState.currentState.recent_scene_functions.length > 0
          ? readerState.currentState.recent_scene_functions.join(" / ")
          : "-";
    } else {
      readerDom.factCount.textContent = "0";
      readerDom.promiseCount.textContent = "0";
      readerDom.tensionValue.textContent = "0.00";
      readerDom.sceneWindow.textContent = "-";
    }
    if (readerDom.readerCreditBalance) {
      readerDom.readerCreditBalance.textContent = creditEntitlement ? String(Number(creditEntitlement.balance || 0).toFixed(0)) : "-";
    }
    if (readerDom.readerWorldUnlockStatus) {
      readerDom.readerWorldUnlockStatus.textContent = worldUnlockLabel(activePaywall);
    }
    if (readerDom.readerEntitlementReason) {
      readerDom.readerEntitlementReason.textContent = accessReasonLabel(activePaywall.reason);
    }
    if (readerDom.readerAccessNote) {
      if (activeContinuityContract.status === "quality_guard_failed") {
        readerDom.readerAccessNote.textContent = activeContinuityContract.message || "当前章节未入库，但阅读位置已保留，可以直接重试当前章。";
      } else if (shellState.debug) {
        readerDom.readerAccessNote.textContent = "调试模式已开启：你可以刷新权益、授予测试额度或直接发起 checkout。";
      } else if (activePaywall.quote) {
        readerDom.readerAccessNote.textContent = `当前继续价格为 ¥${Number(activePaywall.quote).toFixed(2)}；需要时可直接在阅读流程中解锁。`;
      } else {
        readerDom.readerAccessNote.textContent = "默认只展示当前访问状态；真正需要解锁时，会在阅读流程中直接提示。";
      }
    }
    readerDom.readerMembershipOffers?.classList.toggle(
      "is-hidden",
      !shellState.debug && !readerState.readerCheckoutSession && !activePaywall.quote
    );
    readerDom.readerCheckoutStatus?.classList.toggle("is-hidden", !shellState.debug && !readerState.readerCheckoutSession);
    if (readerDom.readerComposerHint) {
      if (!readerState.currentBundle) {
        readerDom.readerComposerHint.textContent = "先从书架挑一个世界，系统才能准备好这一段命运。";
      } else if (activeContinuityContract.status === "quality_guard_failed") {
        readerDom.readerComposerHint.textContent = activeContinuityContract.message || "本章未入库，但当前 session、视图和上一章内容都已保留；可直接重试当前章。";
      } else if (activePaywall.required) {
        const tierText = activePaywall.required_display_name || tierLabel(activePaywall.tier_id) || "更高访问权限";
        readerDom.readerComposerHint.textContent = `继续前你需要先解锁：当前被 ${accessReasonLabel(activePaywall.reason)} 拦住，推荐用 ${tierText} 继续。`;
      } else if (!readerState.sessionId) {
        readerDom.readerComposerHint.textContent = "当前还在浏览世界。点“从这个世界开始”进入第一幕后，才能预览或推进。";
      } else if (!hasPlayerInput) {
        readerDom.readerComposerHint.textContent = "写下一句你现在真正想做的事，就能先看分岔，再决定是否推进。";
      } else {
        readerDom.readerComposerHint.textContent = "现在可以先看命运分岔，再决定要不要推进这一幕。";
      }
    }
    if (readerDom.readerLandingSummary) {
      const worldText = readerState.currentBundle?.label || "还没挑世界";
      const sessionText = readerState.sessionLibrary?.length
        ? `有 ${readerState.sessionLibrary.length} 段旅程可续读`
        : "还没有可续读旅程";
      const loadedText = readerState.worldId ? "当前世界已就绪" : "当前世界未装载";
      const activeReader =
        readerState.readerAuthSession?.identity?.display_name ||
        readerState.readerAuthSession?.identity?.account_id ||
        readerState.readerId ||
        "游客";
      readerDom.readerLandingSummary.textContent = `${worldText} · ${activeReader} · ${sessionText} · ${loadedText}`;
    }
  }

  function toggleDebugMode(force = null) {
    shellState.debug = force === null ? !shellState.debug : Boolean(force);
    syncProductMode();
    if (shellState.debug) {
      reportUiMessage("已进入调试模式：内部测试权益与调试控制已展开。", "success");
    } else {
      reportUiMessage("已关闭调试模式：界面已回到客户可见路径。", "info");
    }
  }

  return {
    appAccessAuthenticated,
    currentShellRoleProfile,
    reviewerContentEnabled,
    syncViewMode,
    syncProductMode,
    updateStatus,
    toggleDebugMode,
  };
})();
