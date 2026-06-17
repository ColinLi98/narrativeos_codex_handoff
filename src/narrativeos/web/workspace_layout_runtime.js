// Shell workspace layout orchestration extracted from app.js.

var WorkspaceLayoutRuntime = (() => {
  const shellDom = ShellDOM;
  const readerDom = ReaderDOM;
  const { reportUiMessage, clearNode } = UIShared;

  function activeReaderShellRuntime() {
    return (typeof ReaderShellV2 === "object" && ReaderShellV2) || ReaderRuntime;
  }

  const AUTHOR_WORKSPACES = [
    { key: "studio", label: "Studio", description: "设定目标，阅读章节，用导演意图和路线选择推进作品。" },
    { key: "overview", label: "总览", description: "看当前草稿、当前阶段、阻塞与推荐动作。" },
    { key: "brief", label: "起稿", description: "定义题材、人物关系与故事起点。" },
    { key: "draft", label: "创作台", description: "编辑人物、场景、长篇规划与风格设定。" },
    { key: "simulate", label: "问题诊断", description: "查看校验、章节问题与连续性诊断结果。" },
    { key: "review", label: "送审", description: "查看最近修改、章节对照与送审证据。" },
    { key: "settings", label: "账户协作", description: "管理登录、通知与协作收件箱。" },
  ];

  const OPS_WORKSPACES = [
    { key: "dashboard", label: "总览", description: "跨域分诊，优先看未分派、阻塞与超时风险。" },
    { key: "review", label: "统一审阅台", description: "按内容发布、治理、运行与支持四条线统一审阅。" },
    { key: "account", label: "账户排查", description: "排查账户、权益、钱包、工单与调查。" },
    { key: "release", label: "发布台", description: "集中处理发布、清单、回滚与版本状态。" },
    { key: "alerts", label: "告警治理", description: "处理告警、治理个案与审计轨迹。" },
    { key: "infra", label: "模型与基础设施", description: "查看模型、任务、运行手册与观测数据。" },
  ];

  const CUSTOMER_WORKSPACES = [
    { key: "overview", label: "账户总览", description: "查看客户账户生命周期、套餐、限额和结算资料。" },
  ];

  const AUTHOR_WORKSPACE_PANEL_ORDER = {
    studio: [24],
    overview: [0, 1, 6, 5],
    brief: [4],
    draft: [13, 14, 15, 16, 17, 18, 20, 22, 23],
    simulate: [8, 7, 21],
    review: [9, 10, 11, 19],
    settings: [2, 3, 12],
  };

  const OPS_WORKSPACE_PANEL_ORDER = {
    dashboard: [0, 1],
    review: [2, 3, 15, 16],
    account: [5, 6, 7, 8, 11, 12],
    release: [4],
    alerts: [9, 10],
    infra: [13, 14, 17, 18, 19, 20, 21],
  };

  const CUSTOMER_WORKSPACE_PANEL_ORDER = {
    overview: [0, 1],
  };

  function createSubnavButton({ label, active = false, onClick }) {
    const button = document.createElement("button");
    button.className = `segment${active ? " is-active" : ""}`;
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", async () => {
      try {
        await onClick();
      } catch (error) {
        reportUiMessage(`切换工作区失败：${error.message}`, "error");
      }
    });
    return button;
  }

  function setReaderWorkspace(workspace, options = {}) {
    shellState.readerWorkspace = workspace;
    if (workspace === "landing") {
      readerState.activeView = "experience";
    }
    if (!options.silent) {
      ShellStatusRuntime.syncProductMode();
    }
  }

  function setAuthorWorkspace(workspace, options = {}) {
    shellState.authorWorkspace = workspace;
    if (!options.silent) {
      ShellStatusRuntime.syncProductMode();
    }
  }

  function setCustomerWorkspace(workspace, options = {}) {
    shellState.customerWorkspace = workspace;
    if (!options.silent) {
      ShellStatusRuntime.syncProductMode();
    }
  }

  function setOpsWorkspace(workspace, options = {}) {
    shellState.opsWorkspace = workspace;
    if (!options.silent) {
      ShellStatusRuntime.syncProductMode();
    }
  }

  function revealWorkspaceForNode(node) {
    const authorWorkspace = node?.closest?.(".product-workspace[data-product='author']");
    if (authorWorkspace) {
      setAuthorWorkspace(authorWorkspace.dataset.workspace, { silent: true });
    }
    const opsWorkspace = node?.closest?.(".product-workspace[data-product='ops']");
    if (opsWorkspace) {
      setOpsWorkspace(opsWorkspace.dataset.workspace, { silent: true });
    }
    const customerWorkspace = node?.closest?.(".product-workspace[data-product='customer']");
    if (customerWorkspace) {
      setCustomerWorkspace(customerWorkspace.dataset.workspace, { silent: true });
    }
  }

  function installScrollWorkspaceBridge() {
    if (typeof Element === "undefined" || Element.prototype.__narrativeosScrollWrapped) return;
    const nativeScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function patchedScrollIntoView(...args) {
      revealWorkspaceForNode(this);
      ShellStatusRuntime.syncProductMode();
      return nativeScrollIntoView.apply(this, args);
    };
    Element.prototype.__narrativeosScrollWrapped = true;
  }

  function buildGuidedWorkspaces(shellEl, product, groups, orderMap) {
    if (!shellEl || shellEl.dataset.guidedWorkspaces === "true") return;
    const stage = shellEl.querySelector(":scope > .stage");
    if (!stage) return;
    const panels = [...stage.children].filter((node) => node.matches("section.panel"));
    const stack = document.createElement("div");
    stack.className = "workspace-stack";
    stack.dataset.product = product;
    for (const group of groups) {
      const workspace = document.createElement("section");
      workspace.className = "product-workspace";
      workspace.dataset.product = product;
      workspace.dataset.workspace = group.key;
      for (const index of orderMap[group.key] || []) {
        const panel = panels[index];
        if (panel) {
          workspace.appendChild(panel);
        }
      }
      stack.appendChild(workspace);
    }
    stage.replaceWith(stack);
    shellEl.dataset.guidedWorkspaces = "true";
  }

  function initializeGuidedWorkspaces() {
    if (shellState.initializedGuidedWorkspaces) return;
    buildGuidedWorkspaces(shellDom.authorShell, "author", AUTHOR_WORKSPACES, AUTHOR_WORKSPACE_PANEL_ORDER);
    buildGuidedWorkspaces(shellDom.customerShell, "customer", CUSTOMER_WORKSPACES, CUSTOMER_WORKSPACE_PANEL_ORDER);
    buildGuidedWorkspaces(shellDom.opsShell, "ops", OPS_WORKSPACES, OPS_WORKSPACE_PANEL_ORDER);
    shellState.initializedGuidedWorkspaces = true;
  }

  function syncWorkspaceStacks() {
    document.querySelectorAll(".product-workspace").forEach((workspace) => {
      const product = workspace.dataset.product;
      const key = workspace.dataset.workspace;
      const active =
        (product === "author" && key === shellState.authorWorkspace) ||
        (product === "customer" && key === shellState.customerWorkspace) ||
        (product === "ops" && key === shellState.opsWorkspace);
      workspace.classList.toggle("is-hidden", !active);
    });
  }

  function renderProductSubnav() {
    if (!shellDom.productSubnavActions) return;
    clearNode(shellDom.productSubnavActions);
    let items = [];
    if (shellState.activeProduct === "reader") {
      shellDom.productSubnavLabel.textContent = "阅读区域";
      shellDom.productSubnavDescription.textContent = shellState.readerWorkspace === "read"
        ? "进入阅读后，可以在沉浸、图文与幕后之间切换，但默认只把故事本身放在正中央。"
        : "先从书架进入一段旅程，再决定从哪个世界开场。";
      if (shellState.readerWorkspace === "read" && (readerState.currentBundle || readerState.sessionId)) {
        items = [
          { label: "返回书架", active: false, onClick: () => setReaderWorkspace("landing") },
          { label: "沉浸阅读", active: readerState.activeView === "experience", onClick: () => { readerState.activeView = "experience"; ShellStatusRuntime.syncViewMode(); activeReaderShellRuntime()?.refresh?.(); } },
          { label: "图文阅读", active: readerState.activeView === "storybook", onClick: () => { readerState.activeView = "storybook"; ShellStatusRuntime.syncViewMode(); activeReaderShellRuntime()?.renderStorybook?.(); } },
          { label: "幕后档案", active: readerState.activeView === "backstage", onClick: () => { readerState.activeView = "backstage"; ShellStatusRuntime.syncViewMode(); activeReaderShellRuntime()?.renderBackstage?.(); } },
        ];
      } else {
        items = [
          { label: "继续上次旅程", active: false, onClick: () => readerDom.readerJumpSessions?.click() },
          { label: "浏览世界", active: false, onClick: () => readerDom.readerJumpWorlds?.click() },
          { label: "开始新旅程", active: false, onClick: () => readerDom.readerStartCurrentWorld?.click() },
        ];
      }
    } else if (shellState.activeProduct === "author") {
      shellDom.productSubnavLabel.textContent = "创作区域";
      const active = AUTHOR_WORKSPACES.find((item) => item.key === shellState.authorWorkspace);
      shellDom.productSubnavDescription.textContent = active?.description || "按作者工作流逐步展开。";
      items = AUTHOR_WORKSPACES.map((item) => ({
        label: item.label,
        active: shellState.authorWorkspace === item.key,
        onClick: async () => {
          setAuthorWorkspace(item.key, { silent: true });
          ShellStatusRuntime.syncProductMode();
          await AuthorWorkspaceRuntime.refreshAuthorSurface();
        },
      }));
    } else if (shellState.activeProduct === "customer") {
      shellDom.productSubnavLabel.textContent = "客户区域";
      const active = CUSTOMER_WORKSPACES.find((item) => item.key === shellState.customerWorkspace);
      shellDom.productSubnavDescription.textContent = active?.description || "按客户生命周期查看当前套餐、限额与结算资料。";
      items = CUSTOMER_WORKSPACES.map((item) => ({
        label: item.label,
        active: shellState.customerWorkspace === item.key,
        onClick: async () => {
          setCustomerWorkspace(item.key, { silent: true });
          ShellStatusRuntime.syncProductMode();
          await CustomerWorkspaceRuntime.refreshCustomerSurface();
        },
      }));
    } else {
      shellDom.productSubnavLabel.textContent = "运营区域";
      const active = OPS_WORKSPACES.find((item) => item.key === shellState.opsWorkspace);
      shellDom.productSubnavDescription.textContent = active?.description || "按运营任务进入对应工作区。";
      items = OPS_WORKSPACES.map((item) => ({
        label: item.label,
        active: shellState.opsWorkspace === item.key,
        onClick: async () => {
          setOpsWorkspace(item.key, { silent: true });
          ShellStatusRuntime.syncProductMode();
          if (item.key === "review") await OpsRefreshRuntime.refreshOpsReleaseFlow();
          if (item.key === "account") await OpsRefreshRuntime.refreshOpsAccountFlow();
          if (item.key === "alerts") await OpsRefreshRuntime.refreshOpsSurface({ scopes: ["alerts", "navigation"] });
          if (item.key === "infra") await OpsRefreshRuntime.refreshOpsSurface({ scopes: ["learned", "jobs", "runtime", "navigation"] });
        },
      }));
    }
    items.forEach((item) => shellDom.productSubnavActions.appendChild(createSubnavButton(item)));
  }

  return {
    AUTHOR_WORKSPACES,
    CUSTOMER_WORKSPACES,
    OPS_WORKSPACES,
    AUTHOR_WORKSPACE_PANEL_ORDER,
    OPS_WORKSPACE_PANEL_ORDER,
    createSubnavButton,
    setReaderWorkspace,
    setAuthorWorkspace,
    setCustomerWorkspace,
    setOpsWorkspace,
    revealWorkspaceForNode,
    installScrollWorkspaceBridge,
    buildGuidedWorkspaces,
    initializeGuidedWorkspaces,
    syncWorkspaceStacks,
    renderProductSubnav,
  };
})();
