// Shell route synchronization extracted from app.js.

var RouteSyncRuntime = (() => {
  const readerDom = ReaderDOM;
  const authorDom = AuthorDOM;
  const opsDom = OpsDOM;

  function shellPathProfile() {
    if (typeof window === "undefined") return {};
    const path = window.location.pathname.replace(/\/+$/, "");
    if (path === "/app/login") {
      return {
        shell_kind: "auth",
        auth_page: "login",
      };
    }
    if (path === "/app/signup") {
      return {
        shell_kind: "auth",
        auth_page: "signup",
      };
    }
    if (path === "/app/verify-email") {
      return {
        shell_kind: "auth",
        auth_page: "verify-email",
      };
    }
    if (path === "/app/forgot-password") {
      return {
        shell_kind: "auth",
        auth_page: "forgot-password",
      };
    }
    if (path === "/app/reset-password") {
      return {
        shell_kind: "auth",
        auth_page: "reset-password",
      };
    }
    if (path === "/app/user") {
      return {
        product: "author",
        workspace: "draft",
        shell_kind: "user",
      };
    }
    if (path === "/app/reviewer") {
      return {
        product: "ops",
        workspace: "review",
        shell_kind: "reviewer",
      };
    }
    if (path === "/app/customer") {
      return {
        product: "customer",
        workspace: "overview",
        shell_kind: "customer",
      };
    }
    return {
      shell_kind: "shared",
    };
  }

  function currentProductWorkspace() {
    if (shellState.activeProduct === "author") return shellState.authorWorkspace;
    if (shellState.activeProduct === "customer") return shellState.customerWorkspace;
    if (shellState.activeProduct === "ops") return shellState.opsWorkspace;
    return shellState.readerWorkspace;
  }

  function resolveActiveAccountId() {
    if (shellState.activeProduct === "reader") {
      return typeof ReaderRuntime !== "undefined" && typeof ReaderRuntime.activeReaderId === "function"
        ? ReaderRuntime.activeReaderId()
        : (readerDom.readerIdInput?.value || "").trim();
    }
    if (shellState.activeProduct === "author") {
      return (authorDom.authorAccountId?.value || "").trim();
    }
    if (shellState.activeProduct === "customer") {
      return String(authorState.authorAuthSession?.identity?.account_id || authorState.authorAuthSession?.identity?.actor_id || "").trim();
    }
    return (opsDom.opsAccountId?.value || "").trim();
  }

  function syncShellRoute() {
    if (typeof window === "undefined") return;
    if (shellState.authPage) return;
    const params = new URLSearchParams();
    params.set("product", shellState.activeProduct);
    params.set("workspace", currentProductWorkspace());
    if (shellState.activeProduct === "reader" && shellState.readerWorkspace === "read") {
      params.set("view", readerState.activeView);
    }
    if (shellState.activeProduct === "ops") {
      const opsWorldId = (opsDom.opsNavWorldId?.value || opsDom.opsReleaseWorldId?.value || "").trim();
      const opsCaseId = (opsDom.opsNavCaseId?.value || opsDom.opsGovernanceCaseId?.value || "").trim();
      const opsAlertId = (opsDom.opsNavAlertId?.value || "").trim();
      const opsWorldVersionId = (opsDom.opsInvestigationWorldVersionId?.value || "").trim();
      if (opsWorldId) params.set("world_id", opsWorldId);
      if (opsCaseId) params.set("case_id", opsCaseId);
      if (opsAlertId) params.set("alert_id", opsAlertId);
      if (opsWorldVersionId) params.set("world_version_id", opsWorldVersionId);
    } else if (shellState.activeProduct === "reader" && readerState.worldId) {
      params.set("world_id", readerState.worldId);
    }
    if (readerState.sessionId) params.set("session_id", readerState.sessionId);
    if (authorState.activeDraftVersionId) params.set("draft_id", authorState.activeDraftVersionId);
    const accountId = resolveActiveAccountId();
    if (accountId) params.set("account_id", accountId);
    if (shellState.debug) params.set("debug", "1");
    if (shellState.adminViewEnabled) params.set("admin_view", "1");
    const query = params.toString();
    const url = `${window.location.pathname}${query ? `?${query}` : ""}`;
    window.history.replaceState({}, "", url);
  }

  function hydrateShellRoute() {
    if (typeof window === "undefined") return;
    const pathProfile = shellPathProfile();
    const params = new URLSearchParams(window.location.search);
    const product = params.get("product");
    const workspace = params.get("workspace");
    const view = params.get("view");
    const debug = params.get("debug");
    const adminView = params.get("admin_view");
    const adminViewBridge = params.get("admin_view_bridge");
    const checkoutStatus = params.get("checkout");
    const checkoutSessionId = params.get("checkout_session_id") || (checkoutStatus ? params.get("session_id") : null);
    shellState.authPage = pathProfile.auth_page || null;
    const requestedProduct = pathProfile.product || (product && ["reader", "author", "customer", "ops"].includes(product) ? product : null);
    const requestedWorkspace = pathProfile.workspace || workspace || null;
    if (requestedProduct) {
      shellState.startupRouteProduct = requestedProduct;
    }
    if (requestedWorkspace) {
      shellState.startupRouteWorkspace = requestedWorkspace;
    }
    if (pathProfile.product) {
      shellState.activeProduct = pathProfile.product;
    } else if (product && ["reader", "author", "customer", "ops"].includes(product)) {
      shellState.activeProduct = product;
    }
    if (pathProfile.workspace) {
      if (shellState.activeProduct === "reader") shellState.readerWorkspace = pathProfile.workspace;
      if (shellState.activeProduct === "author") shellState.authorWorkspace = pathProfile.workspace;
      if (shellState.activeProduct === "customer") shellState.customerWorkspace = pathProfile.workspace;
      if (shellState.activeProduct === "ops") shellState.opsWorkspace = pathProfile.workspace;
    } else if (workspace) {
      if (shellState.activeProduct === "reader") shellState.readerWorkspace = workspace;
      if (shellState.activeProduct === "author") shellState.authorWorkspace = workspace;
      if (shellState.activeProduct === "customer") shellState.customerWorkspace = workspace;
      if (shellState.activeProduct === "ops") shellState.opsWorkspace = workspace;
    }
    if (view && ["experience", "storybook", "backstage"].includes(view)) {
      readerState.activeView = view;
    }
    shellState.debug = debug === "1" || debug === "true";
    shellState.adminViewEnabled = adminView === "1" || adminView === "true";
    shellState.adminViewBridgeToken =
      (adminViewBridge ? String(adminViewBridge) : "") ||
      (shellState.activeProduct === "ops" && typeof window !== "undefined"
        ? window.sessionStorage.getItem("narrativeos_admin_view_bridge") || null
        : null);
    if (params.get("draft_id")) {
      authorState.activeDraftVersionId = params.get("draft_id");
    }
    if (params.get("world_id")) {
      const worldId = params.get("world_id");
      if (shellState.activeProduct === "ops") {
        opsState.selectedOpsWorldId = worldId;
        if (opsDom.opsNavWorldId) opsDom.opsNavWorldId.value = worldId;
        if (opsDom.opsReleaseWorldId) opsDom.opsReleaseWorldId.value = worldId;
      } else if (shellState.activeProduct === "reader") {
        readerState.worldId = worldId;
      }
    }
    if (shellState.activeProduct === "ops" && params.get("case_id")) {
      const caseId = params.get("case_id");
      if (opsDom.opsNavCaseId) opsDom.opsNavCaseId.value = caseId;
      if (opsDom.opsGovernanceCaseId) opsDom.opsGovernanceCaseId.value = caseId;
      if (opsDom.opsInvestigationCaseId) opsDom.opsInvestigationCaseId.value = caseId;
    }
    if (shellState.activeProduct === "ops" && params.get("alert_id")) {
      const alertId = params.get("alert_id");
      opsState.selectedOpsAlertId = alertId;
      if (opsDom.opsNavAlertId) opsDom.opsNavAlertId.value = alertId;
    }
    if (shellState.activeProduct === "ops" && params.get("world_version_id")) {
      const worldVersionId = params.get("world_version_id");
      if (opsDom.opsInvestigationWorldVersionId) opsDom.opsInvestigationWorldVersionId.value = worldVersionId;
    }
    if (checkoutStatus) {
      readerState.pendingCheckoutStatus = checkoutStatus;
      readerState.pendingCheckoutSessionId = checkoutSessionId;
      shellState.activeProduct = "reader";
    } else if (params.get("session_id")) {
      shellState.pendingSessionId = params.get("session_id");
      shellState.readerWorkspace = "read";
    }
    if (params.get("account_id")) {
      const accountId = params.get("account_id");
      if (readerDom.readerIdInput) readerDom.readerIdInput.value = accountId;
      if (authorDom.authorAccountId && shellState.activeProduct === "author") authorDom.authorAccountId.value = accountId;
      if (opsDom.opsAccountId && shellState.activeProduct === "ops") opsDom.opsAccountId.value = accountId;
    }
  }

  return {
    currentProductWorkspace,
    syncShellRoute,
    hydrateShellRoute,
  };
})();
