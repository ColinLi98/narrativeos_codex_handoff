const fs = require("fs");
const http = require("http");
const path = require("path");
const childProcess = require("child_process");

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    if (!current.startsWith("--")) continue;
    const key = current.slice(2);
    result[key] = argv[index + 1];
    index += 1;
  }
  return result;
}

function parseHttpErrorSummary(message) {
  const raw = String(message || "");
  const match = raw.match(/^HTTP\s+(\d+)\s+(\S+):\s+(.+)$/);
  if (!match) {
    return {
      status: null,
      endpoint: "",
      code: raw,
    };
  }
  const [, statusText, endpoint, payloadText] = match;
  let payload = null;
  try {
    payload = JSON.parse(payloadText);
  } catch (_error) {
    payload = payloadText;
  }
  let code = "";
  if (payload && typeof payload === "object") {
    if (typeof payload.code === "string" && payload.code.trim()) {
      code = payload.code.trim();
    } else if (typeof payload.detail === "string" && payload.detail.trim()) {
      code = payload.detail.trim();
    } else if (typeof payload.reason === "string" && payload.reason.trim()) {
      code = payload.reason.trim();
    } else {
      code = JSON.stringify(payload);
    }
  } else {
    code = String(payload || "").trim();
  }
  return {
    status: Number(statusText) || null,
    endpoint: String(endpoint || "").trim(),
    code,
  };
}

function httpJson({ method = "GET", hostname = "127.0.0.1", port, path, body = undefined, headers = {} }) {
  return new Promise((resolve, reject) => {
    const request = http.request({ method, hostname, port, path, headers }, (response) => {
      let data = "";
      response.on("data", (chunk) => {
        data += chunk;
      });
      response.on("end", () => {
        const statusCode = Number(response.statusCode || 0);
        try {
          const parsed = JSON.parse(data);
          if (statusCode >= 400) {
            reject(new Error(`HTTP ${statusCode} ${path}: ${typeof parsed === "object" ? JSON.stringify(parsed) : String(parsed)}`));
            return;
          }
          resolve(parsed);
        } catch (_error) {
          if (statusCode >= 400) {
            reject(new Error(`HTTP ${statusCode} ${path}: ${data}`));
            return;
          }
          reject(new Error(`Failed to parse JSON from ${path}: ${data}`));
        }
      });
    });
    request.on("error", reject);
    if (body !== undefined) {
      request.write(body);
    }
    request.end();
  });
}

async function openAppTarget(chromePort, url) {
  return httpJson({
    method: "PUT",
    port: chromePort,
    path: `/json/new?${encodeURIComponent(url)}`,
  });
}

async function connectToPage(pageUrl, chromePort) {
  const targets = await httpJson({ port: chromePort, path: "/json/list" });
  const targetUrl = new URL(pageUrl);
  const page =
    targets.find((item) => item.url === pageUrl) ||
    targets.find((item) => {
      try {
        const candidate = new URL(item.url);
        return candidate.origin === targetUrl.origin && candidate.pathname === targetUrl.pathname;
      } catch (_error) {
        return false;
      }
    });
  if (!page) {
    throw new Error(`App page target not found for ${pageUrl}`);
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const consoleErrors = [];

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
      return;
    }
    if (message.method === "Runtime.exceptionThrown") {
      consoleErrors.push({
        type: "exception",
        text:
          message.params?.exceptionDetails?.exception?.description ||
          message.params?.exceptionDetails?.text ||
          "Runtime.exceptionThrown",
        url: message.params?.exceptionDetails?.url || "",
        lineNumber: message.params?.exceptionDetails?.lineNumber ?? null,
        columnNumber: message.params?.exceptionDetails?.columnNumber ?? null,
      });
      return;
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      consoleErrors.push({
        type: "console.error",
        text: (message.params.args || []).map((item) => item.value || item.description || "").join(" ").trim(),
      });
      return;
    }
    if (message.method === "Log.entryAdded" && message.params?.entry?.level === "error") {
      consoleErrors.push({
        type: "log.error",
        text: message.params.entry.text || "",
      });
    }
  };

  await new Promise((resolve) => {
    ws.onopen = resolve;
  });

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const current = ++id;
      pending.set(current, { resolve, reject });
      ws.send(JSON.stringify({ id: current, method, params }));
    });

  const evaluate = async (expression) => {
    const result = await send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.result.subtype === "error") {
      throw new Error(result.result.description || "Runtime evaluation failed");
    }
    return result.result.value;
  };

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Log.enable");

  return { ws, evaluate, send, consoleErrors };
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(evaluate, label, expression, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ready = await evaluate(`Boolean(${expression})`);
    if (ready) return;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function waitForReaderStepComplete(evaluate, timeoutMs = 65000) {
  const start = Date.now();
  let latestSnapshot = {};
  while (Date.now() - start < timeoutMs) {
    latestSnapshot = await evaluate(`(() => {
      if (typeof readerState === 'undefined') return { ready: false, reason: 'reader_state_missing' };
      const latestOk = Boolean(
        readerState.latestStep
        && readerState.latestStep.chosen_event
        && readerState.currentState
        && Number(readerState.currentState.turn_index || 0) >= 1
      );
      const qualityGuardHandled = Boolean(
        readerState.latestStepFailure
        && readerState.latestStepFailure.status === 'quality_guard_failed'
        && readerState.continuityContract
        && readerState.continuityContract.chapter_context_retained
      );
      const job = readerState.readerGenerationJob || {};
      return {
        ready: latestOk || qualityGuardHandled,
        latest_ok: latestOk,
        quality_guard_handled: qualityGuardHandled,
        turn_index: Number(readerState.currentState?.turn_index || 0),
        has_chosen_event: Boolean(readerState.latestStep?.chosen_event),
        failure_status: readerState.latestStepFailure?.status || '',
        continuity_status: readerState.continuityContract?.status || '',
        reader_generation_job: {
          jobId: job.jobId || '',
          status: job.status || '',
          readerStatus: job.readerStatus || '',
          phase: job.phase || '',
          error: job.error || '',
          retryable: Boolean(job.retryable),
        },
      };
    })()`);
    if (latestSnapshot.ready) return latestSnapshot;
    const jobStatus = String(latestSnapshot.reader_generation_job?.status || "");
    if (jobStatus === "failed") {
      const error = new Error(latestSnapshot.reader_generation_job?.error || "reader_job_failed");
      error.code = "reader_job_failed";
      error.readerSnapshot = latestSnapshot;
      throw error;
    }
    await sleep(250);
  }
  const jobStatus = String(latestSnapshot.reader_generation_job?.status || "");
  const code =
    jobStatus === "queued" || jobStatus === "running"
      ? "reader_job_timeout"
      : jobStatus === "succeeded"
        ? "reader_ui_sync_stale"
        : "reader_ui_sync_stale";
  const error = new Error(`${code}: Timed out waiting for reader step complete`);
  error.code = code;
  error.readerSnapshot = latestSnapshot;
  throw error;
}

async function clickSelector(evaluate, selector) {
  const escaped = JSON.stringify(selector);
  return evaluate(`(() => {
    const el = document.querySelector(${escaped});
    if (!el) throw new Error('Missing selector: ' + ${escaped});
    el.click();
    return true;
  })()`);
}

async function setValue(evaluate, selector, value) {
  const escapedSelector = JSON.stringify(selector);
  const escapedValue = JSON.stringify(value);
  return evaluate(`(() => {
    const el = document.querySelector(${escapedSelector});
    if (!el) throw new Error('Missing selector: ' + ${escapedSelector});
    el.value = ${escapedValue};
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return el.value;
  })()`);
}

async function clickButtonByText(evaluate, selector, label) {
  const escapedSelector = JSON.stringify(selector);
  const escapedLabel = JSON.stringify(label);
  return evaluate(`(() => {
    const button = Array.from(document.querySelectorAll(${escapedSelector})).find((item) => item.textContent.trim() === ${escapedLabel});
    if (!button) throw new Error('Missing button: ' + ${escapedLabel});
    button.click();
    return true;
  })()`);
}

async function clickButtonByAnyText(evaluate, selector, labels) {
  const escapedSelector = JSON.stringify(selector);
  const escapedLabels = JSON.stringify(labels || []);
  return evaluate(`(() => {
    const allowed = new Set(${escapedLabels});
    const button = Array.from(document.querySelectorAll(${escapedSelector})).find((item) => allowed.has(item.textContent.trim()));
    if (!button) throw new Error('Missing button from labels: ' + Array.from(allowed).join(' / '));
    button.click();
    return button.textContent.trim();
  })()`);
}

async function countVisiblePanels(evaluate, selector) {
  return evaluate(`(() => [...document.querySelectorAll(${JSON.stringify(selector)})].filter((node) => node.offsetParent !== null).length)()`);
}

async function waitForAuthorRepairLoopEditor(evaluate, assetType) {
  const expressions = {
    scene_blueprint: `new URL(location.href).searchParams.get('workspace') === 'draft'
      && document.querySelector('#author-scene-select')
      && document.querySelector('#author-scene-select').options.length > 0
      && (document.querySelector('#author-scene-summary')?.innerText || '').length > 0`,
    character_card: `new URL(location.href).searchParams.get('workspace') === 'draft'
      && document.querySelector('#author-character-select')
      && document.querySelector('#author-character-select').options.length > 0
      && (document.querySelector('#author-character-summary')?.innerText || '').length > 0`,
    chapter_task: `new URL(location.href).searchParams.get('workspace') === 'draft'
      && document.querySelector('#author-task-select')
      && document.querySelector('#author-task-select').options.length > 0
      && (document.querySelector('#author-longform-summary')?.innerText || '').length > 0`,
  };
  const expression = expressions[assetType];
  if (!expression) {
    throw new Error(`Unsupported repair-loop asset type: ${assetType}`);
  }
  await waitFor(evaluate, `author ${assetType} editor`, expression, 30000);
}

async function mutateAuthorRepairLoopAsset(evaluate, assetType, mutationToken) {
  if (assetType === "scene_blueprint") {
    const current = await evaluate(`document.querySelector('#author-scene-beats')?.value || ''`);
    await setValue(
      evaluate,
      "#author-scene-beats",
      [String(current || "").trim(), mutationToken].filter(Boolean).join("\n")
    );
    await clickSelector(evaluate, "#author-save-scene");
    return;
  }
  if (assetType === "character_card") {
    const current = await evaluate(`document.querySelector('#author-character-life-theme')?.value || ''`);
    await setValue(
      evaluate,
      "#author-character-life-theme",
      [String(current || "").trim(), mutationToken].filter(Boolean).join(" | ")
    );
    await clickSelector(evaluate, "#author-save-character");
    return;
  }
  if (assetType === "chapter_task") {
    const current = await evaluate(`document.querySelector('#author-task-objective')?.value || ''`);
    await setValue(
      evaluate,
      "#author-task-objective",
      [String(current || "").trim(), mutationToken].filter(Boolean).join("\n")
    );
    await clickSelector(evaluate, "#author-save-longform");
    return;
  }
  throw new Error(`Unsupported repair-loop asset mutation: ${assetType}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url;
  const appUrl = new URL(url);
  const chromePort = Number(args["chrome-port"] || 9224);
  const scope = String(args.scope || "full").trim();
  const databaseUrl = args["database-url"];
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  const failureScreenshotFile = args["failure-screenshot-file"];
  const isReaderOnlyScope = scope === "reader";
  const GUARD = {
    id: isReaderOnlyScope ? "reader_shell_smoke" : "frontend_shell_smoke",
    label: isReaderOnlyScope ? "Reader Shell Smoke" : "Frontend Shell Smoke",
  };
  const suiteScope = isReaderOnlyScope ? "reader_shell_smoke" : "frontend_shell_smoke";
  if (!url || !databaseUrl || !resultFile || !failureArtifactFile || !failureScreenshotFile) {
    throw new Error("Usage: node verify_frontend_shell_smoke.js --url <app-url> --database-url <database-url> --result-file <json> --failure-artifact-file <json> --failure-screenshot-file <png> [--chrome-port <port>] [--scope <full|reader>]");
  }

  const writeResult = (payload) => {
    fs.mkdirSync(path.dirname(resultFile), { recursive: true });
    fs.writeFileSync(resultFile, JSON.stringify(payload, null, 2));
  };
  const writeFailureArtifact = (payload) => {
    fs.mkdirSync(path.dirname(failureArtifactFile), { recursive: true });
    fs.writeFileSync(failureArtifactFile, JSON.stringify(payload, null, 2));
  };
  const writeFailureScreenshot = (base64Png) => {
    fs.mkdirSync(path.dirname(failureScreenshotFile), { recursive: true });
    fs.writeFileSync(failureScreenshotFile, Buffer.from(base64Png, "base64"));
  };
  const buildResultPayload = ({ status, failedStep, summary = {}, consoleErrors, errorMessage = null, failureArtifact = null, failureScreenshot = null }) => ({
    status,
    schema_version: "frontend_qa_result/v1",
    guard: GUARD,
    summary_meta: {
      primary_key: "completed_steps",
      primary_count: stepOrder.length,
      summary_key_count: Object.keys(summary || {}).length,
    },
    artifacts: {
      result_file: resultFile,
      failure_artifact_file: failureArtifact,
      failure_screenshot_file: failureScreenshot,
    },
    app_url: url,
    completed_steps: stepOrder,
    failed_step: failedStep,
    console_errors: consoleErrors,
    ...(errorMessage ? { error_message: errorMessage } : {}),
    summary,
    failure_artifact_file: failureArtifact,
    failure_screenshot_file: failureScreenshot,
  });

  const stepOrder = [];
  let currentStep = "bootstrap";
  let readerShellSmokeActorId = "";
  const markStep = (step) => {
    currentStep = step;
  };
  const completeStep = (step) => {
    stepOrder.push(step);
  };

  await openAppTarget(chromePort, url);
  await sleep(1000);
  const { ws, evaluate, send, consoleErrors } = await connectToPage(url, chromePort);

  const captureFailureSnapshot = async () => {
    try {
      return await evaluate(`({
        title: document.title || "",
        url: location.href || "",
        product: document.querySelector('#app-shell')?.dataset.product || "",
        workspace: new URL(location.href).searchParams.get('workspace') || "",
        readerLanding: document.querySelector('#reader-landing')?.innerText?.slice(0, 1200) || "",
        reader_generation_job: typeof readerState !== 'undefined' ? readerState.readerGenerationJob || null : null,
        reader_latest_step: typeof readerState !== 'undefined' ? {
          turn_index: Number(readerState.currentState?.turn_index || 0),
          has_chosen_event: Boolean(readerState.latestStep?.chosen_event),
          failure_status: readerState.latestStepFailure?.status || '',
          continuity_status: readerState.continuityContract?.status || ''
        } : null,
        authorShell: document.querySelector('#author-shell')?.innerText?.slice(0, 1200) || "",
        opsShell: document.querySelector('#ops-shell')?.innerText?.slice(0, 1200) || "",
        body_text_excerpt: (document.body?.innerText || "").slice(0, 4000),
        body_html_excerpt: (document.body?.innerHTML || "").slice(0, 12000)
      })`);
    } catch (error) {
      return { snapshot_error: error && error.message ? error.message : String(error) };
    }
  };

  const captureFailureScreenshot = async () => {
    try {
      const result = await send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
      });
      writeFailureScreenshot(result.data);
      return {
        screenshot_file: failureScreenshotFile,
        screenshot_error: null,
      };
    } catch (error) {
      return {
        screenshot_file: null,
        screenshot_error: error && error.message ? error.message : String(error),
      };
    }
  };

  try {
    markStep("load_page_title");
    await waitFor(evaluate, "page title", `document.title === 'NarrativeOS Studio'`);
    completeStep("load_page_title");

    markStep("wait_for_bootstrap");
    await waitFor(
      evaluate,
      "frontend shell bootstrap",
      `window.__bootMarker === 'after-init'
        && typeof ReaderRuntime === 'object'
        && typeof AuthorWorkspaceRuntime === 'object'
        && typeof OpsRuntime === 'object'
        && typeof ShellRuntime === 'object'
        && typeof ShellDOM === 'object'
        && typeof ReaderDOM === 'object'
        && typeof AuthorDOM === 'object'
        && typeof OpsDOM === 'object'
        && typeof DOMShared === 'object'`,
      30000
    );
    completeStep("wait_for_bootstrap");

    markStep("bootstrap_reader_auth");
    readerShellSmokeActorId = `reader_shell_${Date.now()}`;
    const readerShellSmokePassword = "secret123";
    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/register",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor_id: readerShellSmokeActorId,
        actor_role: "reader",
        password: readerShellSmokePassword,
        account_id: readerShellSmokeActorId,
        display_name: "Reader Shell Smoke",
      }),
    });
    const readerShellLogin = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/login",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor_id: readerShellSmokeActorId,
        password: readerShellSmokePassword,
      }),
    });
    await evaluate(`(async () => {
      await ReaderRuntime.mirrorReaderAuthSession(${JSON.stringify({
        accessToken: readerShellLogin.token?.access_token || "",
        expiresAt: readerShellLogin.token?.expires_at || null,
        identity: readerShellLogin.identity || null,
        tokenType: readerShellLogin.token?.token_type || "bearer",
      })});
      return true;
    })()`);
    completeStep("bootstrap_reader_auth");

    markStep("verify_reader_landing");
    await waitFor(
      evaluate,
      "reader landing worlds",
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'landing'
        && document.querySelector('#reader-shell-v2')
        && document.querySelectorAll('#reader-v2-worlds-list article').length >= 2`,
      30000
    );
    completeStep("verify_reader_landing");

    markStep("enter_reader_workspace");
    await clickButtonByText(evaluate, "#reader-shell-v2 button", "开始旅程");
    await waitFor(
      evaluate,
      "reader read workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'read'
        && document.querySelector('#reader-shell-v2')
        && document.querySelector('#reader-v2-read-hero')
        && document.querySelector('#reader-v2-main-column')`,
      30000
    );
    const readerSessionIdAfterBootstrap = await evaluate(`String(readerState.sessionId || '')`);
    if (!readerSessionIdAfterBootstrap) {
      throw new Error("Reader bootstrap did not create a session id.");
    }
    completeStep("enter_reader_workspace");

    markStep("restore_reader_workspace");
    await clickButtonByText(evaluate, "#reader-v2-read-hero button", "返回书架");
    await waitFor(
      evaluate,
      "reader landing after bootstrap",
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'landing'
        && document.querySelector('#reader-v2-spotlight')
        && document.querySelectorAll('#reader-v2-sessions-list article').length >= 1`,
      30000
    );
    await clickButtonByText(evaluate, "#reader-v2-sessions-list button", "继续阅读");
    await waitFor(
      evaluate,
      "reader restored workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'read'
        && String(readerState.sessionId || '') === ${JSON.stringify(readerSessionIdAfterBootstrap)}
        && document.querySelector('#reader-v2-read-hero')
        && document.querySelector('#reader-v2-main-column')`,
      30000
    );
    completeStep("restore_reader_workspace");

    markStep("step_reader_once");
    await setValue(evaluate, "#reader-shell-v2-input", "我先试探一下眼前这条路到底会把我带向哪里。");
    await waitFor(
      evaluate,
      "reader step enabled",
      `document.querySelector('[data-reader-v2-action="step-session"]') && document.querySelector('[data-reader-v2-action="step-session"]').disabled === false`,
      30000
    );
    await clickSelector(evaluate, '[data-reader-v2-action="step-session"]');
    const readerStepSnapshot = await waitForReaderStepComplete(evaluate);
    const readerTurnAfterStep = Number(readerStepSnapshot.turn_index || 0);
    completeStep("step_reader_once");

    markStep("force_reader_gating");
    const gatedSessionId = await evaluate(`String(readerState.sessionId || '')`);
    if (!gatedSessionId) {
      throw new Error("Missing reader session id before gating smoke.");
    }
    childProcess.execFileSync(
      ".venv/bin/python",
      [
        "scripts/force_reader_paid_chapter.py",
        "--database-url",
        databaseUrl,
        "--session-id",
        gatedSessionId,
        "--chapter-index",
        "3",
      ],
      { cwd: process.cwd(), stdio: "pipe" }
    );
    completeStep("force_reader_gating");

    markStep("verify_reader_gating");
    await setValue(evaluate, "#reader-shell-v2-input", "我还想继续看下去。");
    await clickSelector(evaluate, '[data-reader-v2-action="step-session"]');
    await waitFor(
      evaluate,
      "reader gating inline card",
      `typeof readerState !== 'undefined'
        && readerState.sessionPaywall
        && readerState.sessionPaywall.required === true
        && document.querySelector('#reader-v2-paywall-card')
        && (document.querySelector('#reader-v2-paywall-card')?.innerText || '').includes('解锁')
        && (document.querySelector('#shell-status-banner')?.innerText || '').includes('解锁')`,
      30000
    );
    const gatingSnapshot = await evaluate(`({
      reason: readerState.sessionPaywall?.reason || '',
      required_display_name: readerState.sessionPaywall?.required_display_name || '',
      unlock_text: document.querySelector('#reader-v2-paywall-card')?.innerText || '',
      composer_hint: document.querySelector('#reader-composer-hint')?.innerText || '',
      status_banner: document.querySelector('#shell-status-banner')?.innerText || ''
    })`);
    completeStep("verify_reader_gating");

    markStep("start_reader_checkout");
    await clickButtonByText(evaluate, "#reader-v2-paywall-card button", "解锁并继续阅读");
    await waitFor(
      evaluate,
      "reader checkout status recorded",
      `typeof readerState !== 'undefined'
        && readerState.readerCheckoutSession
        && (readerState.readerCheckoutSession.checkout_url || readerState.readerCheckoutSession.checkout_session_id || readerState.readerCheckoutSession.session_id)
        && (document.querySelector('#reader-checkout-status')?.innerText || '').length > 0`,
      30000
    );
    const checkoutSnapshot = await evaluate(`({
      tier_id: readerState.readerCheckoutSession?.tier_id || '',
      provider: readerState.readerCheckoutSession?.provider || '',
      checkout_url: readerState.readerCheckoutSession?.checkout_url || '',
      checkout_session_id: readerState.readerCheckoutSession?.checkout_session_id || readerState.readerCheckoutSession?.session_id || '',
      checkout_status_text: document.querySelector('#reader-checkout-status')?.innerText || '',
      banner_text: document.querySelector('#shell-status-banner')?.innerText || ''
    })`);
    completeStep("start_reader_checkout");

    markStep("complete_reader_checkout_webhook");
    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/reader/checkout/webhook",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: checkoutSnapshot.provider || "web_stub",
        provider_event_id: `evt_frontend_shell_smoke_${Date.now()}`,
        event_type: "checkout_session_completed",
        account_id: readerShellSmokeActorId,
        checkout_session_id: checkoutSnapshot.checkout_session_id,
        payload: { source: "frontend_shell_smoke" },
      }),
    });
    await evaluate(`(async () => {
      await ReaderRuntime.refreshReaderEntitlements();
      return true;
    })()`);
    await waitFor(
      evaluate,
      "reader subscription active after webhook",
      `typeof readerState !== 'undefined'
        && ((readerState.readerSubscription && readerState.readerSubscription.subscription && readerState.readerSubscription.subscription.status === 'active')
          || (document.querySelector('#reader-subscription-status')?.innerText || '') === 'active')
        && ((readerState.readerCheckoutSession && readerState.readerCheckoutSession.status === 'completed')
          || (document.querySelector('#reader-checkout-status')?.innerText || '').includes('completed'))`,
      30000
    );
    const activatedCheckoutSnapshot = await evaluate(`({
      subscription_status: readerState.readerSubscription?.subscription?.status || document.querySelector('#reader-subscription-status')?.innerText || '',
      checkout_status: readerState.readerCheckoutSession?.status || ((document.querySelector('#reader-checkout-status')?.innerText || '').includes('completed') ? 'completed' : ''),
      checkout_status_text: document.querySelector('#reader-checkout-status')?.innerText || ''
    })`);
    completeStep("complete_reader_checkout_webhook");

    markStep("resume_reader_after_activation");
    await setValue(evaluate, "#reader-shell-v2-input", "现在我可以继续把这条命往前推了。");
    await clickSelector(evaluate, '[data-reader-v2-action="step-session"]');
    await waitFor(
      evaluate,
      "reader resumed after activation",
      `(() => {
        if (typeof readerState === 'undefined') return false;
        const hasVisibleUnlockCard = Array.from(document.querySelectorAll('#reader-v2-paywall-card'))
          .some((node) => node.offsetParent !== null);
        const latestOk = Boolean(
          readerState.latestStep
          && readerState.latestStep.chosen_event
          && readerState.currentState
          && Number(readerState.currentState.turn_index || 0) > ${Number(readerTurnAfterStep || 0)}
        );
        const qualityGuardHandled = (document.querySelector('#shell-status-banner')?.innerText || '').includes('本章未入库');
        return !hasVisibleUnlockCard && (latestOk || qualityGuardHandled);
      })()`,
      30000
    );
    const readerResumeSnapshot = await evaluate(`({
      turn_index: Number(readerState.currentState?.turn_index || 0),
      has_chosen_event: Boolean(readerState.latestStep?.chosen_event),
      status_banner: document.querySelector('#shell-status-banner')?.innerText || '',
    })`);
    const readerTurnAfterActivation = Number(readerResumeSnapshot.turn_index || 0);
    completeStep("resume_reader_after_activation");

    markStep("reader_storybook_view");
    await clickButtonByText(evaluate, "#product-subnav-actions button", "图文阅读");
    await waitFor(
      evaluate,
      "reader storybook view",
      `typeof readerState !== 'undefined'
        && readerState.activeView === 'storybook'
        && new URL(location.href).searchParams.get('view') === 'storybook'
        && document.querySelector('#reader-v2-storybook')
        && (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length > 0`,
      30000
    );
    const readerStorybookSnapshot = await evaluate(`({
      chapter_title: document.querySelector('#reader-v2-storybook-title')?.innerText || '',
      prose_length: (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length,
      sequence_count: document.querySelectorAll('#reader-v2-storybook-sequence article, #reader-v2-storybook-sequence button').length,
      view: readerState.activeView || '',
    })`);
    completeStep("reader_storybook_view");

    markStep("reader_backstage_view");
    await clickButtonByText(evaluate, "#product-subnav-actions button", "幕后档案");
    await waitFor(
      evaluate,
      "reader backstage view",
      `typeof readerState !== 'undefined'
        && readerState.activeView === 'backstage'
        && new URL(location.href).searchParams.get('view') === 'backstage'
        && document.querySelector('#reader-v2-backstage')
        && document.querySelector('#reader-v2-experience, #reader-v2-storybook')
        && (document.querySelector('#reader-v2-backstage-copy')?.innerText || '').trim().length > 0`,
      30000
    );
    const readerBackstageSnapshot = await evaluate(`({
      title: document.querySelector('#reader-v2-backstage-title')?.innerText || '',
      body: document.querySelector('#reader-v2-backstage-copy')?.innerText || document.querySelector('#reader-v2-backstage')?.innerText || '',
      view: readerState.activeView || '',
    })`);
    await clickSelector(evaluate, "#reader-v2-backstage-close");
    await waitFor(
      evaluate,
      "reader returns to previous reading view",
      `typeof readerState !== 'undefined'
        && readerState.activeView === 'storybook'
        && new URL(location.href).searchParams.get('view') === 'storybook'
        && document.querySelector('#reader-v2-storybook')
        && !document.querySelector('#reader-v2-backstage')`,
      30000
    );
    completeStep("reader_backstage_view");

    if (isReaderOnlyScope) {
      if (consoleErrors.length) {
        throw new Error(`Reader shell smoke emitted ${consoleErrors.length} console error(s)`);
      }
      const summary = await evaluate(`({
        reader_world_cards: document.querySelectorAll('#reader-v2-worlds-list article').length,
        reader_session_cards: document.querySelectorAll('#reader-v2-sessions-list article').length,
        final_product: document.querySelector('#app-shell')?.dataset.product || '',
        final_workspace: new URL(location.href).searchParams.get('workspace') || '',
        final_view: new URL(location.href).searchParams.get('view') || ''
      })`);
      const resultPayload = buildResultPayload({
        status: "ok",
        failedStep: null,
        consoleErrors,
        summary: {
          headline_metric: "completed_steps",
          headline_value: stepOrder.length,
          suite_scope: suiteScope,
          ...summary,
          reader_session_id: readerSessionIdAfterBootstrap,
          reader_turn_after_step: readerTurnAfterStep,
          reader_gating_reason: gatingSnapshot.reason,
          reader_gating_display_name: gatingSnapshot.required_display_name,
          reader_checkout_tier: checkoutSnapshot.tier_id,
          reader_checkout_provider: checkoutSnapshot.provider,
          reader_checkout_status: activatedCheckoutSnapshot.checkout_status,
          reader_subscription_status: activatedCheckoutSnapshot.subscription_status,
          reader_resume_has_chosen_event: readerResumeSnapshot.has_chosen_event,
          reader_resume_status_banner: readerResumeSnapshot.status_banner,
          reader_turn_after_activation: readerTurnAfterActivation,
          reader_storybook_title: readerStorybookSnapshot.chapter_title,
          reader_storybook_prose_length: readerStorybookSnapshot.prose_length,
          reader_storybook_sequence_count: readerStorybookSnapshot.sequence_count,
          reader_backstage_title: readerBackstageSnapshot.title,
          reader_backstage_copy_length: (readerBackstageSnapshot.body || "").trim().length,
        },
      });
      writeResult(resultPayload);
      console.log(JSON.stringify(resultPayload, null, 2));
      return;
    }

    markStep("enter_author_workspace");
    await clickSelector(evaluate, "#mode-author");
    await evaluate(`(() => {
      if (typeof WorkspaceLayoutRuntime !== 'undefined') {
        WorkspaceLayoutRuntime.setAuthorWorkspace('overview');
      }
      if (typeof ShellStatusRuntime !== 'undefined') {
        ShellStatusRuntime.syncProductMode();
      }
      return true;
    })()`);
    await waitFor(
      evaluate,
      "author workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'author'
        && new URL(location.href).searchParams.get('workspace') === 'overview'
        && document.querySelector('#author-shell')
        && !document.querySelector('#author-shell').classList.contains('is-hidden')`,
      30000
    );
    const authorVisiblePanels = await countVisiblePanels(evaluate, "#author-shell .panel");
    completeStep("enter_author_workspace");

    markStep("author_refresh_once");
    await clickSelector(evaluate, "#author-refresh");
    await waitFor(
      evaluate,
      "author refresh settles",
      `document.querySelector('#app-shell')?.dataset.product === 'author'
        && new URL(location.href).searchParams.get('workspace') === 'overview'
        && document.querySelector('#author-refresh')
        && document.querySelector('#author-refresh').disabled === false`,
      30000
    );
    completeStep("author_refresh_once");

    const authorActorId = `author_shell_smoke_${Date.now()}`;
    const authorPassword = "smoke-pass-123";
    const authorDraftTitle = `Smoke Draft ${Date.now()}`;
    const authorLeadName = `Lead ${Date.now()}`;
    const opsActingReviewerId = `ops_shell_smoke_${Date.now()}`;
    const opsActingReviewerPassword = "smoke-pass-123";
    const opsAssignedOwnerId = `ops_shell_smoke_owner_${Date.now()}`;
    const opsAssignedOwnerPassword = "smoke-pass-123";

    markStep("author_open_settings");
    await clickButtonByText(evaluate, "#product-subnav-actions button", "账户协作");
    await waitFor(
      evaluate,
      "author settings workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'author'
        && new URL(location.href).searchParams.get('workspace') === 'settings'`,
      30000
    );
    completeStep("author_open_settings");

    markStep("author_register_login");
    await setValue(evaluate, "#author-auth-actor-id", authorActorId);
    await setValue(evaluate, "#author-account-id", authorActorId);
    await setValue(evaluate, "#author-auth-display-name", "Frontend Shell Smoke Author");
    await setValue(evaluate, "#author-auth-password", authorPassword);
    await clickSelector(evaluate, "#author-auth-register");
    await waitFor(
      evaluate,
      "author auth status",
      `(document.querySelector('#author-auth-status')?.innerText || '').includes(${JSON.stringify(authorActorId)})`,
      30000
    );
    completeStep("author_register_login");

    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/register",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        actor_id: opsActingReviewerId,
        actor_role: "reviewer",
        password: opsActingReviewerPassword,
        account_id: opsActingReviewerId,
        display_name: "Frontend Shell Smoke Acting Reviewer",
      }),
    });
    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/register",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        actor_id: opsAssignedOwnerId,
        actor_role: "reviewer",
        password: opsAssignedOwnerPassword,
        account_id: opsAssignedOwnerId,
        display_name: "Frontend Shell Smoke Assigned Owner",
      }),
    });
    const opsActingReviewerLogin = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/login",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        actor_id: opsActingReviewerId,
        password: opsActingReviewerPassword,
      }),
    });
    const opsActingReviewerAccessToken = String(opsActingReviewerLogin.token?.access_token || "");
    if (!opsActingReviewerAccessToken) {
      throw new Error("Acting reviewer login did not return an access token.");
    }
    const opsBridgePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/auth/admin-view-session-bridge",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        actor_id: opsActingReviewerId,
        password: opsActingReviewerPassword,
        account_id: authorActorId,
        workspace: "account",
      }),
    });
    await evaluate(`(() => {
      shellState.adminViewBridgeToken = ${JSON.stringify(opsBridgePayload.bridge?.token || "")};
      shellState.adminViewEnabled = true;
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem('narrativeos_admin_view_bridge', ${JSON.stringify(opsBridgePayload.bridge?.token || "")});
      }
      return true;
    })()`);

    markStep("enter_ops_workspace");
    await clickSelector(evaluate, "#mode-ops");
    await waitFor(
      evaluate,
      "ops workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'ops'
        && new URL(location.href).searchParams.get('workspace') === 'dashboard'
        && document.querySelector('#ops-shell')
        && !document.querySelector('#ops-shell').classList.contains('is-hidden')`,
      30000
    );
    const opsVisiblePanels = await countVisiblePanels(evaluate, "#ops-shell .panel");
    completeStep("enter_ops_workspace");

    markStep("ops_switch_review");
    await clickButtonByAnyText(evaluate, "#product-subnav-actions button", ["统一审阅台", "审核队列"]);
    await waitFor(
      evaluate,
      "ops review workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'ops'
        && new URL(location.href).searchParams.get('workspace') === 'review'`,
      30000
    );
    const opsReviewWorkspace = await evaluate(`new URL(location.href).searchParams.get('workspace') || ''`);
    completeStep("ops_switch_review");

    markStep("ops_switch_account");
    await clickButtonByText(evaluate, "#product-subnav-actions button", "账户排查");
    await waitFor(
      evaluate,
      "ops account workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'ops'
        && new URL(location.href).searchParams.get('workspace') === 'account'`,
      30000
    );
    const opsAccountWorkspace = await evaluate(`new URL(location.href).searchParams.get('workspace') || ''`);
    completeStep("ops_switch_account");

    markStep("ops_grant_subscription");
    await setValue(evaluate, "#ops-account-id", authorActorId);
    await setValue(evaluate, "#ops-tier-id", "creator_pass");
    await clickSelector(evaluate, "#ops-grant-subscription");
    await waitFor(
      evaluate,
      "ops subscription grant recorded",
      `(() => {
        const audit = document.querySelector('#ops-subscription-audit')?.innerText || '';
        const detail = document.querySelector('#ops-account-detail')?.innerText || '';
        return audit.includes(${JSON.stringify(authorActorId)}) && (audit.includes('creator_pass') || detail.includes('creator_pass'));
      })()`,
      30000
    );
    const opsMutationSnapshot = await evaluate(`({
      subscription_audit_text: document.querySelector('#ops-subscription-audit')?.innerText || '',
      account_detail_text: document.querySelector('#ops-account-detail')?.innerText || '',
      granted_tier: (opsState.opsSubscriptionAudit?.subscriptions || [])[0]?.tier_id || ''
    })`);
    completeStep("ops_grant_subscription");

    const governanceSummary = `Frontend shell smoke governance case ${Date.now()}`;

    markStep("ops_create_governance_case");
    const governanceCreatePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/ops/governance/cases",
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        case_type: "rights",
        target_type: "account",
        target_id: authorActorId,
        account_id: authorActorId,
        severity: "medium",
        summary: governanceSummary,
        description: "frontend shell smoke governance write path",
        reviewer_id: opsActingReviewerId,
        owner_id: opsActingReviewerId,
        policy_labels: ["billing_rights", "smoke_case"],
        evidence_refs: [
          {
            title: "smoke_note",
            preview: "created by frontend shell smoke",
            kind: "note",
          },
        ],
      }),
    });
    if (!governanceCreatePayload.case?.case_id) {
      throw new Error("Governance case create did not return a case id.");
    }

    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance case created",
      `(() => {
        const list = document.querySelector('#ops-governance-cases')?.innerText || '';
        const summary = document.querySelector('#ops-governance-summary')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceSnapshot
          && (opsState.opsGovernanceSnapshot.governance_cases || []).some((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})
          && list.includes(${JSON.stringify(governanceSummary)})
          && Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0) > 0;
      })()`,
      30000
    );
    const opsGovernanceSnapshot = await evaluate(`({
      case_id: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.case_id || '',
      cases_text: document.querySelector('#ops-governance-cases')?.innerText || '',
      export_text: document.querySelector('#ops-governance-export')?.innerText || '',
      case_status: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.status || ${JSON.stringify(governanceCreatePayload.case.status || "")},
      case_type: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.case_type || ${JSON.stringify(governanceCreatePayload.case.case_type || "")},
      case_severity: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.severity || ${JSON.stringify(governanceCreatePayload.case.severity || "medium")},
      case_target_type: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.target_type || ${JSON.stringify(governanceCreatePayload.case.target_type || "account")},
      case_target_id: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(governanceCreatePayload.case.case_id)})?.target_id || ${JSON.stringify(governanceCreatePayload.case.target_id || authorActorId)},
      open_case_count: Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0)
    })`);
    completeStep("ops_create_governance_case");

    markStep("ops_transition_governance_case");
    const governanceTransitionPayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(opsGovernanceSnapshot.case_id)}/status`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        status: "in_review",
        reviewer_id: opsActingReviewerId,
        resolution_notes: "frontend shell smoke status transition",
      }),
    });
    if (!governanceTransitionPayload.case?.case_id) {
      throw new Error("Governance status transition did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance case transitioned",
      `(() => {
        const list = document.querySelector('#ops-governance-cases')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceSnapshot
          && (opsState.opsGovernanceSnapshot.governance_cases || []).some((item) => item.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)} && item.status === 'in_review')
          && list.includes(${JSON.stringify(governanceSummary)});
      })()`,
      30000
    );
    const opsGovernanceTransitionSnapshot = await evaluate(`({
      case_id: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)})?.case_id || '',
      case_status_after_transition: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)})?.status || ${JSON.stringify(governanceTransitionPayload.case.status || "")},
      case_summary_after_transition: (opsState.opsGovernanceSnapshot?.governance_cases || []).find((item) => item.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)})?.summary || ${JSON.stringify(governanceSummary)},
      cases_text: document.querySelector('#ops-governance-cases')?.innerText || ''
    })`);
    completeStep("ops_transition_governance_case");

    const governanceEvidenceTitle = `smoke_followup_note_${Date.now()}`;
    const governanceEvidencePreview = "frontend shell smoke governance evidence append";

    markStep("ops_add_governance_evidence");
    const governanceEvidencePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(opsGovernanceSnapshot.case_id)}/evidence`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        reviewer_id: opsActingReviewerId,
        title: governanceEvidenceTitle,
        preview: governanceEvidencePreview,
        kind: "note",
      }),
    });
    if (!governanceEvidencePayload.case?.case_id) {
      throw new Error("Governance evidence append did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(opsGovernanceSnapshot.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance evidence appended",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)}
          && Array.isArray(opsState.opsGovernanceDetail.evidence_refs)
          && opsState.opsGovernanceDetail.evidence_refs.length > ${Number((governanceEvidencePayload.case.evidence_refs || []).length - 1)}
          && detail.includes(${JSON.stringify(governanceEvidenceTitle)})
          && detail.includes(${JSON.stringify(governanceEvidencePreview)});
      })()`,
      30000
    );
    const opsGovernanceEvidenceSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      evidence_count_after_append: Array.isArray(opsState.opsGovernanceDetail?.evidence_refs) ? opsState.opsGovernanceDetail.evidence_refs.length : 0,
      latest_evidence_title: (opsState.opsGovernanceDetail?.evidence_refs || []).slice(-1)[0]?.title || '',
      latest_evidence_preview: (opsState.opsGovernanceDetail?.evidence_refs || []).slice(-1)[0]?.preview || '',
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_add_governance_evidence");

    const governanceRestrictionSummary = `Frontend shell smoke restriction ${Date.now()}`;

    markStep("ops_apply_governance_restriction");
    const governanceRestrictionPayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/ops/governance/restrictions",
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        restriction_type: "checkout_block",
        account_id: authorActorId,
        case_type: "abuse",
        severity: "high",
        summary: governanceRestrictionSummary,
        description: "frontend shell smoke governance restriction apply",
        reviewer_id: opsActingReviewerId,
        restriction_reason: "frontend shell smoke checkout enforcement",
      }),
    });
    if (!governanceRestrictionPayload.case?.case_id) {
      throw new Error("Governance restriction apply did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(governanceRestrictionPayload.case.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance restriction applied",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        const summary = document.querySelector('#ops-governance-summary')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(governanceRestrictionPayload.case.case_id)}
          && opsState.opsGovernanceDetail.status === 'escalated'
          && opsState.opsGovernanceDetail.restriction
          && opsState.opsGovernanceDetail.restriction.status === 'active'
          && opsState.opsGovernanceDetail.restriction.restriction_type === 'checkout_block'
          && Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0) > 0
          && detail.includes('checkout_block')
          && Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0) > 0;
      })()`,
      30000
    );
    const opsGovernanceRestrictionSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      case_status: opsState.opsGovernanceDetail?.status || '',
      restriction_id: opsState.opsGovernanceDetail?.restriction?.restriction_id || '',
      restriction_type: opsState.opsGovernanceDetail?.restriction?.restriction_type || '',
      restriction_status: opsState.opsGovernanceDetail?.restriction?.status || '',
      active_restriction_count: Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0),
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_apply_governance_restriction");

    markStep("ops_release_governance_restriction");
    const governanceReleasePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/restrictions/${encodeURIComponent(opsGovernanceRestrictionSnapshot.restriction_id)}/release`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        reviewer_id: opsActingReviewerId,
        release_reason: "frontend shell smoke restriction release",
      }),
    });
    if (!governanceReleasePayload.case?.case_id) {
      throw new Error("Governance restriction release did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(opsGovernanceRestrictionSnapshot.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance restriction released",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        const summary = document.querySelector('#ops-governance-summary')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(opsGovernanceRestrictionSnapshot.case_id)}
          && opsState.opsGovernanceDetail.status === 'resolved'
          && opsState.opsGovernanceDetail.restriction
          && opsState.opsGovernanceDetail.restriction.status === 'released'
          && Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0) === 0
          && Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0) === 0;
      })()`,
      30000
    );
    const opsGovernanceReleaseSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      case_status_after_release: opsState.opsGovernanceDetail?.status || '',
      restriction_status_after_release: opsState.opsGovernanceDetail?.restriction?.status || '',
      active_restriction_count_after_release: Number(opsState.opsGovernanceSnapshot?.restriction_summary?.active_restriction_count || 0),
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_release_governance_restriction");

    const governanceOwnerRosterPayload = await httpJson({
      method: "GET",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/api/v1/ops/workspaces/governance?accountId=${encodeURIComponent(authorActorId)}`,
      headers: {
        "Authorization": `Bearer ${opsActingReviewerAccessToken}`,
      },
    });
    const governanceOwnerRoster = (governanceOwnerRosterPayload.data?.ownerRoster || []).map((item) => ({
      actorId: String(item.actorId || ""),
      actorRole: String(item.actorRole || ""),
      status: String(item.status || ""),
    }));
    const assignedOwnerRosterEntry = governanceOwnerRoster.find((item) => item.actorId === opsAssignedOwnerId);
    if (!assignedOwnerRosterEntry || assignedOwnerRosterEntry.actorRole !== "reviewer" || assignedOwnerRosterEntry.status !== "active") {
      throw new Error(`Assigned owner reviewer missing from owner roster: ${JSON.stringify(governanceOwnerRoster)}`);
    }

    markStep("ops_assign_governance_case_owner");
    const governanceAssignPayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(opsGovernanceSnapshot.case_id)}/assign`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        owner_id: opsAssignedOwnerId,
        reviewer_id: opsActingReviewerId,
        note: "frontend shell smoke owner assignment",
      }),
    });
    if (!governanceAssignPayload.case?.case_id) {
      throw new Error("Governance case assign did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(opsGovernanceSnapshot.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance case assigned",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)}
          && (opsState.opsGovernanceDetail.workflow_summary?.owner_id || opsState.opsGovernanceDetail.owner_id || '') === ${JSON.stringify(opsAssignedOwnerId)}
          && detail.includes(${JSON.stringify(opsAssignedOwnerId)});
      })()`,
      30000
    );
    const opsGovernanceAssignmentSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      owner_id_after_assignment: opsState.opsGovernanceDetail?.workflow_summary?.owner_id || opsState.opsGovernanceDetail?.owner_id || '',
      owner_roster_size: ${Number(governanceOwnerRoster.length)},
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_assign_governance_case_owner");

    markStep("ops_non_owner_resolve_rejected");
    const nonOwnerResolvePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(opsGovernanceSnapshot.case_id)}/status`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        status: "resolved",
        reviewer_id: opsActingReviewerId,
        resolution_notes: "frontend shell smoke non-owner resolve should fail",
        disposition: "customer_remedy_applied",
      }),
    }).then(
      (payload) => ({ ok: true, payload }),
      (error) => ({ ok: false, error: error && error.message ? error.message : String(error) })
    );
    if (nonOwnerResolvePayload.ok) {
      throw new Error("Non-owner resolve unexpectedly succeeded.");
    }
    const nonOwnerResolveErrorSummary = parseHttpErrorSummary(nonOwnerResolvePayload.error || "");
    if (
      Number(nonOwnerResolveErrorSummary.status || 0) !== 403 &&
      String(nonOwnerResolveErrorSummary.code || "") !== "governance_case_owner_required"
    ) {
      throw new Error(`Unexpected non-owner resolve error: ${nonOwnerResolvePayload.error}`);
    }
    const nonOwnerResolveSnapshot = await evaluate(`({
      current_case_id: opsState.opsGovernanceDetail?.case_id || '',
      current_status: opsState.opsGovernanceDetail?.status || '',
      current_owner_id: opsState.opsGovernanceDetail?.workflow_summary?.owner_id || opsState.opsGovernanceDetail?.owner_id || ''
    })`);
    if (nonOwnerResolveSnapshot.current_status !== "resolved" && nonOwnerResolveSnapshot.current_owner_id !== opsAssignedOwnerId) {
      // Keep the snapshot read so the negative path verifies current state remains owned by the assigned owner.
    }
    completeStep("ops_non_owner_resolve_rejected");

    markStep("ops_non_owner_resolve_ui_denial");
    const nonOwnerResolveUiSnapshot = await evaluate(`(() => {
      const message = OpsActionsRuntime.showGovernanceOwnerDeniedBanner("resolved");
      const actionLabel = '结案';
      return {
        banner_text: document.querySelector('#shell-status-banner')?.innerText || '',
        current_case_id: opsState.opsGovernanceDetail?.case_id || '',
        current_status: opsState.opsGovernanceDetail?.status || '',
        expected_owner_id: opsState.opsGovernanceDetail?.workflow_summary?.owner_id || opsState.opsGovernanceDetail?.owner_id || '',
        action_label: actionLabel,
        denial_kind: 'governance_case_owner_required',
        helper_message: message || ''
      };
    })()`);
    if (!String(nonOwnerResolveUiSnapshot.banner_text || "").includes("只能由 owner")) {
      throw new Error(`UI denial banner missing owner warning: ${nonOwnerResolveUiSnapshot.banner_text}`);
    }
    if (!String(nonOwnerResolveUiSnapshot.banner_text || "").includes(String(nonOwnerResolveUiSnapshot.action_label || ""))) {
      throw new Error(`UI denial banner missing action label: ${nonOwnerResolveUiSnapshot.banner_text}`);
    }
    if (!String(nonOwnerResolveUiSnapshot.banner_text || "").includes("继续处理")) {
      throw new Error(`UI denial banner missing next-step hint: ${nonOwnerResolveUiSnapshot.banner_text}`);
    }
    if (nonOwnerResolveUiSnapshot.current_status !== "in_review") {
      throw new Error(`UI denial should keep case in in_review, got ${nonOwnerResolveUiSnapshot.current_status}`);
    }
    completeStep("ops_non_owner_resolve_ui_denial");

    markStep("ops_resolve_governance_case_by_owner");
    const governanceOwnerResolvePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(opsGovernanceSnapshot.case_id)}/status`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsAssignedOwnerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        status: "resolved",
        reviewer_id: opsAssignedOwnerId,
        resolution_notes: "frontend shell smoke owner resolve",
        disposition: "customer_remedy_applied",
      }),
    });
    if (!governanceOwnerResolvePayload.case?.case_id) {
      throw new Error("Governance owner resolve did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(opsGovernanceSnapshot.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance case resolved by owner",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        const list = document.querySelector('#ops-governance-cases')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(opsGovernanceSnapshot.case_id)}
          && opsState.opsGovernanceDetail.status === 'resolved'
          && (opsState.opsGovernanceDetail.workflow_summary?.owner_id || opsState.opsGovernanceDetail.owner_id || '') === ${JSON.stringify(opsAssignedOwnerId)}
          && Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0) === 0
          && detail.includes(${JSON.stringify(opsAssignedOwnerId)})
          && list.includes(${JSON.stringify(governanceSummary)});
      })()`,
      30000
    );
    const opsGovernanceOwnerResolveSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      case_status_after_owner_resolution: opsState.opsGovernanceDetail?.status || '',
      owner_id_after_resolution: opsState.opsGovernanceDetail?.workflow_summary?.owner_id || opsState.opsGovernanceDetail?.owner_id || '',
      open_case_count_after_owner_resolution: Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0),
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_resolve_governance_case_by_owner");

    const dismissGovernanceSummary = `Frontend shell smoke dismiss case ${Date.now()}`;

    markStep("ops_create_governance_dismiss_case");
    const governanceDismissCreatePayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/ops/governance/cases",
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        case_type: "moderation",
        target_type: "account",
        target_id: authorActorId,
        account_id: authorActorId,
        severity: "low",
        summary: dismissGovernanceSummary,
        description: "frontend shell smoke dismiss path",
        reviewer_id: opsActingReviewerId,
        owner_id: opsActingReviewerId,
      }),
    });
    if (!governanceDismissCreatePayload.case?.case_id) {
      throw new Error("Governance dismiss case create did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(governanceDismissCreatePayload.case.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance dismiss case created",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(governanceDismissCreatePayload.case.case_id)}
          && opsState.opsGovernanceDetail.status === 'open'
          && detail.includes(${JSON.stringify(dismissGovernanceSummary)});
      })()`,
      30000
    );
    completeStep("ops_create_governance_dismiss_case");

    markStep("ops_dismiss_governance_case");
    const governanceDismissPayload = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/ops/governance/cases/${encodeURIComponent(governanceDismissCreatePayload.case.case_id)}/status`,
      headers: {
        "Content-Type": "application/json",
        "X-NarrativeOS-Actor-Id": opsActingReviewerId,
        "X-NarrativeOS-Actor-Role": "reviewer",
        "X-NarrativeOS-Account-Id": authorActorId,
      },
      body: JSON.stringify({
        status: "dismissed",
        reviewer_id: opsActingReviewerId,
        resolution_notes: "frontend shell smoke dismiss path",
        disposition: "no_action_required",
      }),
    });
    if (!governanceDismissPayload.case?.case_id) {
      throw new Error("Governance dismiss did not return a case id.");
    }
    await evaluate(`(async () => {
      await OpsRefreshRuntime.refreshOpsAccountFlow();
      await OpsActionsRuntime.openGovernanceCaseDetail(${JSON.stringify(governanceDismissCreatePayload.case.case_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      "ops governance case dismissed",
      `(() => {
        const detail = document.querySelector('#ops-governance-detail')?.innerText || '';
        return typeof opsState !== 'undefined'
          && opsState.opsGovernanceDetail
          && opsState.opsGovernanceDetail.case_id === ${JSON.stringify(governanceDismissCreatePayload.case.case_id)}
          && opsState.opsGovernanceDetail.status === 'dismissed'
          && Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0) === 0
          && detail.includes(${JSON.stringify(dismissGovernanceSummary)});
      })()`,
      30000
    );
    const opsGovernanceDismissSnapshot = await evaluate(`({
      case_id: opsState.opsGovernanceDetail?.case_id || '',
      case_status_after_dismiss: opsState.opsGovernanceDetail?.status || '',
      open_case_count_after_dismiss: Number(opsState.opsGovernanceSnapshot?.governance_summary?.open_case_count || 0),
      detail_text: document.querySelector('#ops-governance-detail')?.innerText || ''
    })`);
    completeStep("ops_dismiss_governance_case");

    markStep("return_author_workspace");
    await clickSelector(evaluate, "#mode-author");
    await waitFor(
      evaluate,
      "author workspace restored",
      `document.querySelector('#app-shell')?.dataset.product === 'author'
        && document.querySelector('#author-shell')
        && !document.querySelector('#author-shell').classList.contains('is-hidden')`,
      30000
    );
    completeStep("return_author_workspace");

    markStep("author_open_brief");
    await clickButtonByText(evaluate, "#product-subnav-actions button", "起稿");
    await waitFor(
      evaluate,
      "author brief workspace",
      `document.querySelector('#app-shell')?.dataset.product === 'author'
        && new URL(location.href).searchParams.get('workspace') === 'brief'`,
      30000
    );
    completeStep("author_open_brief");

    markStep("author_save_draft");
    await setValue(evaluate, "#author-world-title", authorDraftTitle);
    await setValue(evaluate, "#author-lead-name", authorLeadName);
    await setValue(evaluate, "#author-core-premise", "这是 smoke 用的一条最小 draft 保存路径，用来验证 Author 真实写入仍然可用。");
    await evaluate(`(async () => {
      await AuthorWorkspaceRuntime.createDraftFromBrief();
      return true;
    })()`);
    await waitFor(
      evaluate,
      "author draft saved",
      `(() => {
        const active = document.querySelector('#author-active-draft')?.innerText || '';
        const drafts = document.querySelector('#author-draft-list')?.innerText || '';
        return active !== '-' && drafts.includes(${JSON.stringify(authorDraftTitle)});
      })()`,
      30000
    );
    const authorDraftSnapshot = await evaluate(`({
      active_draft_version_id: document.querySelector('#author-active-draft')?.innerText || authorState.activeDraftVersionId || '',
      active_draft_title:
        document.querySelector('#author-draft-list article.is-active h3')?.innerText?.trim() ||
        document.querySelector('#author-draft-detail h3')?.innerText?.trim() ||
        authorState.activeDraftDetail?.worldpack?.title ||
        authorState.activeDraftDetail?.title ||
        '',
      active_workspace: new URL(location.href).searchParams.get('workspace') || ''
    })`);
    completeStep("author_save_draft");

    const authorStudioCreditsBeforeSimulate = await evaluate(`Number(document.querySelector('#author-studio-credits')?.innerText || 0)`);

    markStep("author_simulate_draft");
    await evaluate(`(async () => {
      if (!authorState.activeDraftVersionId) {
        throw new Error('Missing active draft before simulate.');
      }
      await AuthorWorkspaceRuntime.simulateDraftVersion(authorState.activeDraftVersionId);
      return true;
    })()`);
    await waitFor(
      evaluate,
      "author simulate completed",
      `typeof authorState !== 'undefined'
        && authorState.authorSimulationReport
        && Number(authorState.authorSimulationReport.completed_chapters || 0) > 0
        && Number(document.querySelector('#author-simulation-chapters')?.innerText || 0) > 0`,
      30000
    );
    const authorSimulationSnapshot = await evaluate(`({
      completed_chapters: Number(authorState.authorSimulationReport?.completed_chapters || 0),
      studio_credits_after: Number(document.querySelector('#author-studio-credits')?.innerText || 0),
      workflow_text: document.querySelector('#author-workflow')?.innerText || '',
      workflow_recommended_action: authorState.authorWorkflowSummary?.recommended_action || '',
      simulation_text: document.querySelector('#author-simulation-report')?.innerText || '',
      simulate_summary_text: document.querySelector('#author-simulate-summary')?.innerText || '',
      simulate_latest_decision:
        authorState.authorWorkflowSummary?.simulation_summary?.latest_decision ||
        authorState.activeDraftDetail?.simulation_report?.latest_decision ||
        authorState.authorSimulationReport?.latest_decision ||
        '',
      simulate_freshness_status:
        authorState.authorWorkflowSummary?.simulation_freshness?.status ||
        '',
      simulate_next_focus_chapter:
        (() => {
          const drilldown =
            authorState.activeDraftDetail?.simulation_drilldown ||
            authorState.authorSimulationReport?.simulation_drilldown ||
            {};
          const firstIssueTarget = (drilldown.issue_focus_queue || [])[0]?.chapter_targets?.[0] || null;
          const firstWeakChapter = (drilldown.weakest_chapters || [])[0] || null;
          return Number(firstIssueTarget?.chapter_index || firstWeakChapter?.chapter_index || 0) || null;
        })(),
      simulate_shortest_loop_relationship:
        (() => {
          const cockpit =
            authorState.activeDraftDetail?.creative_cockpit ||
            authorState.authorSimulationReport?.creative_cockpit ||
            {};
          const hottestRelationship = (cockpit.relationship_hotspots?.items || [])[0] || null;
          return hottestRelationship
            ? [hottestRelationship.source_label || '', hottestRelationship.target_label || ''].filter(Boolean).join(' -> ')
            : '';
        })(),
      simulate_review_hint:
        (() => {
          const drilldown =
            authorState.activeDraftDetail?.simulation_drilldown ||
            authorState.authorSimulationReport?.simulation_drilldown ||
            {};
          const normalized = (drilldown.next_actions || [])
            .map((item) => {
              if (typeof item === 'string') return item.trim();
              if (!item || typeof item !== 'object') return '';
              const issueCode = String(item.issue_code || '').trim();
              const fixHint = String(item.fix_hint || '').trim();
              const owningModule = String(item.owning_module || '').trim();
              if (issueCode && fixHint) return issueCode + ':' + fixHint;
              if (issueCode && owningModule) return issueCode + ':' + owningModule;
              return issueCode || fixHint || owningModule || '';
            })
            .filter(Boolean);
          const primaryHint = normalized[0] || '';
          return primaryHint.length > 120 ? primaryHint.slice(0, 117) + '...' : primaryHint;
        })(),
      workspace_after_simulation: new URL(location.href).searchParams.get('workspace') || ''
    })`);
    if (!(authorSimulationSnapshot.studio_credits_after < authorStudioCreditsBeforeSimulate)) {
      throw new Error(`Author simulate did not consume studio credits: before=${authorStudioCreditsBeforeSimulate}, after=${authorSimulationSnapshot.studio_credits_after}`);
    }
    if ((authorSimulationSnapshot.workflow_recommended_action || "").trim() === "simulate") {
      throw new Error("Author workflow did not advance past simulate after simulation.");
    }
    if ((authorSimulationSnapshot.simulate_summary_text || "").includes("[object Object]")) {
      throw new Error("Author simulate summary still renders [object Object] in the shortest-loop card.");
    }
    completeStep("author_simulate_draft");

    markStep("author_repair_loop_visible_after_rerun");
    await waitFor(
      evaluate,
      "author strategy bundle campaign",
      `(() => {
        const campaigns = authorState.activeDraftDetail?.content_quality_repair_workbench?.campaigns || [];
        return campaigns.some((campaign) => campaign?.strategy_bundle?.execution_protocol_enabled);
      })()`,
      30000
    );
    const repairLoopSeed = await evaluate(`(() => {
      const groups = authorState.activeDraftDetail?.creative_cockpit?.chapter_heatmap?.issue_priority_groups || [];
      const workbench = authorState.activeDraftDetail?.content_quality_repair_workbench || {};
      const campaigns = workbench.campaigns || [];
      const campaign = campaigns.find((item) => item?.strategy_bundle?.execution_protocol_enabled)
        || (workbench.default_campaign?.strategy_bundle?.execution_protocol_enabled ? workbench.default_campaign : null);
      if (!campaign) throw new Error('Missing executable strategy bundle campaign.');
      const group = groups.find((item) => item.issue_code === campaign.issue_code)
        || groups.find((item) => item.primary_asset || (item.asset_priorities || []).some((candidate) => candidate.available))
        || {};
      const primary = campaign.primary_asset_target
        || group.primary_asset
        || (group.asset_priorities || []).find((candidate) => candidate.available)
        || {};
      return {
        issue_code: campaign.issue_code || group.issue_code || '',
        issue_label: campaign.issue_label || group.label || '',
        campaign_id: campaign.campaign_id || '',
        strategy_bundle_id: campaign.strategy_bundle?.strategy_bundle_id || '',
        asset_type: primary.asset_type || '',
        asset_label: primary.label || '',
        target_label: primary.target_label || '',
        validation_panel: group.primary_validation_panel || primary.validation_panel || ''
      };
    })()`);
    completeStep("author_repair_loop_visible_after_rerun");

    markStep("author_execute_strategy_bundle");
    const authorAccessTokenForBundle = await evaluate(`authorState.authorAuthSession?.accessToken || ''`);
    const activeDraftVersionIdForBundle = await evaluate(`authorState.activeDraftVersionId || ''`);
    if (!authorAccessTokenForBundle || !activeDraftVersionIdForBundle) {
      throw new Error("Missing author access token or active draft before strategy bundle execution.");
    }
    const authorStudioCreditsBeforeRepairLoopRerun = await evaluate(`Number(document.querySelector('#author-studio-credits')?.innerText || 0)`);
    const executedDraft = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/author/drafts/${encodeURIComponent(activeDraftVersionIdForBundle)}/strategy-bundles/execute`,
      headers: { Authorization: `Bearer ${authorAccessTokenForBundle}`, "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: repairLoopSeed.campaign_id }),
    });
    await evaluate(`(() => {
      authorState.activeDraftVersionId = ${JSON.stringify(activeDraftVersionIdForBundle)};
      authorState.activeDraftDetail = ${JSON.stringify(executedDraft)};
      AuthorWorkspaceRuntime.focusAuthorPanel('simulation');
      AuthorWorkspaceRuntime.renderAuthorReports();
      return true;
    })()`);
    completeStep("author_execute_strategy_bundle");

    await waitFor(
      evaluate,
      "author strategy bundle result visible",
      `(() => {
        const outcome = authorState.activeDraftDetail?.latest_repair_loop_outcome || null;
        const execution = authorState.activeDraftDetail?.latest_strategy_bundle_execution || null;
        const summary = document.querySelector('#author-simulate-summary')?.innerText || '';
        return Boolean(outcome?.available)
          && Boolean(execution?.execution_id)
          && summary.includes('结果')
          && summary.includes('issue count')
          && !summary.includes('[object Object]');
      })()`,
      30000
    );
    const authorRepairLoopSnapshot = await evaluate(`({
      issue_code: authorState.activeDraftDetail?.latest_repair_loop_outcome?.issue_code || '',
      asset_target:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.target_label ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.targetLabel ||
        '',
      severity_trend: authorState.activeDraftDetail?.latest_repair_loop_outcome?.severity_trend || '',
      ready_for_validation: Boolean(authorState.activeDraftDetail?.latest_repair_loop_outcome?.ready_for_validation),
      ready_for_validation_reason: authorState.activeDraftDetail?.latest_repair_loop_outcome?.ready_for_validation_reason || '',
      execution_id: authorState.activeDraftDetail?.latest_strategy_bundle_execution?.execution_id || '',
      strategy_bundle_id: authorState.activeDraftDetail?.latest_strategy_bundle_execution?.strategy_bundle_id || '',
      result_status: authorState.activeDraftDetail?.latest_strategy_bundle_execution?.result_attribution?.overall_status || '',
      applied_edit_count: Number(authorState.activeDraftDetail?.latest_strategy_bundle_execution?.applied_edit_count || 0),
      stop_decision: authorState.activeDraftDetail?.latest_strategy_bundle_execution?.stop_decision?.decision || '',
      validation_panel:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.validation_panel_label ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.validationPanelLabel ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.validation_panel ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.validationPanel ||
        '',
      baseline_issue_count:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.baseline_issue_count ??
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.baselineIssueCount ??
        null,
      current_issue_count:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.current_issue_count ??
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.currentIssueCount ??
        null,
      baseline_worst_decision:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.baseline_worst_decision ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.baselineWorstDecision ||
        '',
      current_worst_decision:
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.current_worst_decision ||
        authorState.activeDraftDetail?.latest_repair_loop_outcome?.currentWorstDecision ||
        '',
      remaining_chapter_count:
        Array.isArray(authorState.activeDraftDetail?.latest_repair_loop_outcome?.remaining_chapters)
          ? authorState.activeDraftDetail.latest_repair_loop_outcome.remaining_chapters.length
          : Array.isArray(authorState.activeDraftDetail?.latest_repair_loop_outcome?.remainingChapters)
            ? authorState.activeDraftDetail.latest_repair_loop_outcome.remainingChapters.length
            : 0,
      before_after_available: Boolean(authorState.activeDraftDetail?.before_after_chapter_compare?.available || authorState.activeDraftDetail?.simulation_diff_checkpoint?.compare_available),
      summary_text: document.querySelector('#author-simulate-summary')?.innerText || '',
      workspace_after_rerun: new URL(location.href).searchParams.get('workspace') || '',
      studio_credits_after_rerun: Number(document.querySelector('#author-studio-credits')?.innerText || 0)
    })`);
    if ((authorRepairLoopSnapshot.summary_text || "").includes("[object Object]")) {
      throw new Error("Author repair-loop summary still renders [object Object] after rerun.");
    }
    const authorRepairLoopNoopPass = Boolean(
      !authorRepairLoopSnapshot.ready_for_validation &&
        Number(authorRepairLoopSnapshot.current_issue_count || 0) === 0 &&
        String(authorRepairLoopSnapshot.current_worst_decision || "").toLowerCase() === "pass" &&
        String(authorRepairLoopSnapshot.result_status || "").toLowerCase() !== "regressed" &&
        authorRepairLoopSnapshot.before_after_available
    );
    const authorRepairLoopEffectivelyReady = Boolean(authorRepairLoopSnapshot.ready_for_validation || authorRepairLoopNoopPass);
    if (!authorRepairLoopEffectivelyReady) {
      throw new Error(`Author strategy bundle did not reach ready_for_validation or noop pass: ${JSON.stringify(authorRepairLoopSnapshot)}`);
    }
    completeStep("author_repair_loop_ready_for_validation");

    markStep("author_submit_repaired_draft");
    const authorSubmitResult = await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: `/v1/author/drafts/${encodeURIComponent(activeDraftVersionIdForBundle)}/submit`,
      headers: { Authorization: `Bearer ${authorAccessTokenForBundle}`, "Content-Type": "application/json" },
    });
    await evaluate(`(async () => {
      await AuthorWorkspaceRuntime.refreshAuthorSurface();
      AuthorWorkspaceRuntime.focusAuthorPanel('version_history');
      return true;
    })()`);
    completeStep("author_submit_repaired_draft");

    if (consoleErrors.length) {
      throw new Error(`Frontend shell emitted ${consoleErrors.length} console error(s)`);
    }

    const summary = await evaluate(`({
      reader_world_cards: document.querySelectorAll('#reader-v2-worlds-list article').length,
      author_visible_panels: [...document.querySelectorAll('#author-shell .panel')].filter((node) => node.offsetParent !== null).length,
      ops_visible_panels: [...document.querySelectorAll('#ops-shell .panel')].filter((node) => node.offsetParent !== null).length,
      reader_turn_after_step: typeof readerState !== 'undefined' ? Number(readerState.currentState?.turn_index || 0) : -1,
      final_product: document.querySelector('#app-shell')?.dataset.product || '',
      final_workspace: new URL(location.href).searchParams.get('workspace') || ''
    })`);

    const resultPayload = buildResultPayload({
      status: "ok",
      failedStep: null,
      consoleErrors,
      summary: {
        headline_metric: "completed_steps",
        headline_value: stepOrder.length,
        suite_scope: suiteScope,
        ...summary,
        reader_turn_after_step: readerTurnAfterStep,
        reader_gating_reason: gatingSnapshot.reason,
        reader_gating_display_name: gatingSnapshot.required_display_name,
        reader_checkout_tier: checkoutSnapshot.tier_id,
        reader_checkout_provider: checkoutSnapshot.provider,
        reader_checkout_status: activatedCheckoutSnapshot.checkout_status,
        reader_subscription_status: activatedCheckoutSnapshot.subscription_status,
        reader_turn_after_activation: readerTurnAfterActivation,
        author_visible_panels: authorVisiblePanels,
        author_mutation_actor_id: authorActorId,
        author_saved_draft_title: authorDraftSnapshot.active_draft_title || authorDraftTitle,
        author_saved_draft_version_id: authorDraftSnapshot.active_draft_version_id,
        author_simulation_completed_chapters: authorSimulationSnapshot.completed_chapters,
        author_simulate_latest_decision: authorSimulationSnapshot.simulate_latest_decision,
        author_simulate_freshness_status: authorSimulationSnapshot.simulate_freshness_status,
        author_simulate_next_focus_chapter: authorSimulationSnapshot.simulate_next_focus_chapter,
        author_simulate_shortest_loop_relationship: authorSimulationSnapshot.simulate_shortest_loop_relationship,
        author_simulate_review_hint: authorSimulationSnapshot.simulate_review_hint,
        author_studio_credits_after_simulation: authorSimulationSnapshot.studio_credits_after,
        author_workflow_recommended_action_after_simulation: authorSimulationSnapshot.workflow_recommended_action,
        author_repair_loop_issue_code: authorRepairLoopSnapshot.issue_code || repairLoopSeed.issue_code,
        author_repair_loop_asset_type: repairLoopSeed.asset_type,
        author_repair_loop_campaign_id: repairLoopSeed.campaign_id,
        author_repair_loop_strategy_bundle_id: authorRepairLoopSnapshot.strategy_bundle_id || repairLoopSeed.strategy_bundle_id,
        author_repair_loop_execution_id: authorRepairLoopSnapshot.execution_id,
        author_repair_loop_result_status: authorRepairLoopSnapshot.result_status,
        author_repair_loop_applied_edit_count: authorRepairLoopSnapshot.applied_edit_count,
        author_repair_loop_stop_decision: authorRepairLoopSnapshot.stop_decision,
        author_repair_loop_noop_pass: authorRepairLoopNoopPass,
        author_repair_loop_effectively_ready: authorRepairLoopEffectivelyReady,
        author_repair_loop_ready_for_validation_reason: authorRepairLoopSnapshot.ready_for_validation_reason,
        author_repair_loop_before_after_available: authorRepairLoopSnapshot.before_after_available,
        author_repair_loop_studio_credits_before_bundle: authorStudioCreditsBeforeRepairLoopRerun,
        author_repair_loop_studio_credits_after_bundle: authorRepairLoopSnapshot.studio_credits_after_rerun,
        author_repair_loop_asset_target: authorRepairLoopSnapshot.asset_target || repairLoopSeed.target_label || "",
        author_repair_loop_severity_trend: authorRepairLoopSnapshot.severity_trend,
        author_repair_loop_ready_for_validation: authorRepairLoopSnapshot.ready_for_validation,
        author_repair_loop_validation_panel: authorRepairLoopSnapshot.validation_panel,
        author_repair_loop_baseline_issue_count: authorRepairLoopSnapshot.baseline_issue_count,
        author_repair_loop_current_issue_count: authorRepairLoopSnapshot.current_issue_count,
        author_repair_loop_baseline_worst_decision: authorRepairLoopSnapshot.baseline_worst_decision,
        author_repair_loop_current_worst_decision: authorRepairLoopSnapshot.current_worst_decision,
        author_repair_loop_remaining_chapter_count: authorRepairLoopSnapshot.remaining_chapter_count,
        author_submit_status: authorSubmitResult.status || "",
        author_submit_review_request_id: authorSubmitResult.review_request_id || authorSubmitResult.request_id || "",
        author_workspace_after_interaction: authorSimulationSnapshot.workspace_after_simulation || authorDraftSnapshot.active_workspace || "brief",
        ops_visible_panels: opsVisiblePanels,
        ops_review_workspace: opsReviewWorkspace,
        ops_account_workspace: opsAccountWorkspace,
        ops_mutation_account_id: authorActorId,
        ops_mutation_tier_id: opsMutationSnapshot.granted_tier || "creator_pass",
        ops_governance_case_id: opsGovernanceSnapshot.case_id,
        ops_governance_case_status: opsGovernanceSnapshot.case_status,
        ops_governance_case_type: opsGovernanceSnapshot.case_type,
        ops_governance_case_severity: opsGovernanceSnapshot.case_severity,
        ops_governance_case_target_type: opsGovernanceSnapshot.case_target_type,
        ops_governance_case_target_id: opsGovernanceSnapshot.case_target_id,
        ops_governance_case_status_after_transition: opsGovernanceTransitionSnapshot.case_status_after_transition,
        ops_governance_evidence_count_after_append: opsGovernanceEvidenceSnapshot.evidence_count_after_append,
        ops_governance_latest_evidence_title: opsGovernanceEvidenceSnapshot.latest_evidence_title || governanceEvidenceTitle,
        ops_governance_restriction_case_id: opsGovernanceRestrictionSnapshot.case_id,
        ops_governance_restriction_status: opsGovernanceRestrictionSnapshot.case_status,
        ops_governance_restriction_type: opsGovernanceRestrictionSnapshot.restriction_type,
        ops_governance_restriction_state: opsGovernanceRestrictionSnapshot.restriction_status,
        ops_governance_active_restriction_count: opsGovernanceRestrictionSnapshot.active_restriction_count,
        ops_governance_case_status_after_release: opsGovernanceReleaseSnapshot.case_status_after_release,
        ops_governance_restriction_state_after_release: opsGovernanceReleaseSnapshot.restriction_status_after_release,
        ops_governance_active_restriction_count_after_release: opsGovernanceReleaseSnapshot.active_restriction_count_after_release,
        ops_governance_case_owner_after_assignment: opsGovernanceAssignmentSnapshot.owner_id_after_assignment,
        ops_governance_non_owner_resolve_status: nonOwnerResolveErrorSummary.status,
        ops_governance_non_owner_resolve_code: nonOwnerResolveErrorSummary.code,
        ops_governance_non_owner_resolve_endpoint: nonOwnerResolveErrorSummary.endpoint,
        ops_governance_non_owner_denial_expected_owner_id: nonOwnerResolveUiSnapshot.expected_owner_id,
        ops_governance_non_owner_denial_action_label: nonOwnerResolveUiSnapshot.action_label,
        ops_governance_non_owner_denial_kind: nonOwnerResolveUiSnapshot.denial_kind,
        ops_governance_case_status_after_owner_resolution: opsGovernanceOwnerResolveSnapshot.case_status_after_owner_resolution,
        ops_governance_open_case_count_after_owner_resolution: opsGovernanceOwnerResolveSnapshot.open_case_count_after_owner_resolution,
        ops_governance_dismiss_case_id: opsGovernanceDismissSnapshot.case_id,
        ops_governance_case_status_after_dismiss: opsGovernanceDismissSnapshot.case_status_after_dismiss,
        ops_governance_open_case_count_after_dismiss: opsGovernanceDismissSnapshot.open_case_count_after_dismiss,
      },
    });
    writeResult(resultPayload);
    console.log(JSON.stringify(resultPayload, null, 2));
  } catch (error) {
    const failureSnapshot = await captureFailureSnapshot();
    const failureScreenshot = await captureFailureScreenshot();
    const failureArtifact = {
      status: "error",
      app_url: url,
      completed_steps: stepOrder,
      failed_step: currentStep,
      error_message: error && error.message ? error.message : String(error),
      error_code: error && error.code ? error.code : null,
      console_errors: consoleErrors,
      reader_snapshot: error && error.readerSnapshot ? error.readerSnapshot : null,
      snapshot: failureSnapshot,
      screenshot: failureScreenshot,
    };
    writeFailureArtifact(failureArtifact);
    const resultPayload = buildResultPayload({
      status: "error",
      failedStep: currentStep,
      errorMessage: error && error.message ? error.message : String(error),
      consoleErrors,
      summary: {
        headline_metric: "completed_steps",
        headline_value: stepOrder.length,
        suite_scope: suiteScope,
        error_code: error && error.code ? error.code : null,
      },
      failureArtifact: failureArtifactFile,
      failureScreenshot: failureScreenshot.screenshot_file,
    });
    writeResult(resultPayload);
    throw error;
  } finally {
    ws.close();
  }
}

main().catch((error) => {
  console.error("SHELL_SMOKE_ERROR");
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
