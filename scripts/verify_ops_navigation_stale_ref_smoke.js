const fs = require("fs");
const http = require("http");
const path = require("path");

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

function httpJson({ method = "GET", hostname = "127.0.0.1", port, path }) {
  return new Promise((resolve, reject) => {
    const request = http.request({ method, hostname, port, path }, (response) => {
      let data = "";
      response.on("data", (chunk) => {
        data += chunk;
      });
      response.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch (_error) {
          reject(new Error(`Failed to parse JSON from ${path}: ${data}`));
        }
      });
    });
    request.on("error", reject);
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
  const page = targets.find((item) => item.url === pageUrl);
  if (!page) {
    throw new Error(`App page target not found for ${pageUrl}`);
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
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
  return { ws, evaluate };
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

async function clickFollowUpAction(evaluate, label) {
  const escapedLabel = JSON.stringify(label);
  return evaluate(`(() => {
    const button = Array.from(document.querySelectorAll('#ops-navigation-actions button')).find((item) => item.textContent.trim() === ${escapedLabel});
    if (!button) throw new Error('Missing follow-up action: ' + ${escapedLabel});
    button.click();
    return true;
  })()`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url;
  const chromePort = Number(args["chrome-port"] || 9223);
  const seedFile = args["seed-file"];
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  const failureScreenshotFile = args["failure-screenshot-file"];
  if (!url || !seedFile || !resultFile || !failureArtifactFile || !failureScreenshotFile) {
    throw new Error("Usage: node verify_ops_navigation_stale_ref_smoke.js --url <app-url> --seed-file <json> --result-file <json> --failure-artifact-file <json> --failure-screenshot-file <png> [--chrome-port <port>]");
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
  const stepOrder = [];
  let currentStep = "bootstrap";
  const markStep = (step) => {
    currentStep = step;
  };
  const completeStep = (step) => {
    stepOrder.push(step);
  };

  const seed = JSON.parse(fs.readFileSync(seedFile, "utf8"));
  await openAppTarget(chromePort, url);
  await sleep(1000);
  const { ws, evaluate } = await connectToPage(url, chromePort);
  const captureFailureScreenshot = async () => {
    try {
      const targets = await httpJson({ port: chromePort, path: "/json/list" });
      const page = targets.find((item) => item.url === url);
      if (!page) {
        return { screenshot_error: `App page target not found for ${url}` };
      }
      const pageWs = new WebSocket(page.webSocketDebuggerUrl);
      let pageId = 0;
      const pending = new Map();
      pageWs.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.id && pending.has(message.id)) {
          const { resolve, reject } = pending.get(message.id);
          pending.delete(message.id);
          if (message.error) reject(new Error(message.error.message));
          else resolve(message.result);
        }
      };
      await new Promise((resolve) => {
        pageWs.onopen = resolve;
      });
      const send = (method, params = {}) =>
        new Promise((resolve, reject) => {
          const current = ++pageId;
          pending.set(current, { resolve, reject });
          pageWs.send(JSON.stringify({ id: current, method, params }));
        });
      await send("Page.enable");
      const result = await send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
      });
      pageWs.close();
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
  const captureFailureSnapshot = async () => {
    try {
      return await evaluate(`({
        title: document.title || "",
        url: location.href || "",
        mode: {
          opsActive: document.querySelector('#mode-ops')?.classList.contains('is-active') || false
        },
        navInputs: {
          account: document.querySelector('#ops-nav-account-id')?.value || "",
          world: document.querySelector('#ops-nav-world-id')?.value || "",
          caseId: document.querySelector('#ops-nav-case-id')?.value || "",
          alertId: document.querySelector('#ops-nav-alert-id')?.value || ""
        },
        panels: {
          navigationSummary: document.querySelector('#ops-navigation-summary')?.innerText || "",
          navigationActions: document.querySelector('#ops-navigation-actions')?.innerText || "",
          accountSummary: document.querySelector('#ops-account-workspace-summary')?.innerText || "",
          alertSummary: document.querySelector('#ops-alert-summary')?.innerText || "",
          governanceDetail: document.querySelector('#ops-governance-detail')?.innerText || "",
          investigationSummary: document.querySelector('#ops-investigation-summary')?.innerText || "",
          releaseSummary: document.querySelector('#ops-release-workspace-summary')?.innerText || ""
        },
        body_text_excerpt: (document.body?.innerText || "").slice(0, 4000),
        body_html_excerpt: (document.body?.innerHTML || "").slice(0, 12000)
      })`);
    } catch (error) {
      return {
        snapshot_error: error && error.message ? error.message : String(error),
      };
    }
  };

  try {
    markStep("load_page_title");
    await waitFor(evaluate, "page title", `document.title === 'NarrativeOS Studio'`);
    completeStep("load_page_title");
    markStep("wait_for_app_bootstrap");
    await waitFor(
      evaluate,
      "ops app bootstrap",
      `typeof appState !== 'undefined'
        && typeof refreshOpsSurface === 'function'
        && typeof runDataIntegrityRepair === 'function'
        && document.querySelector('#mode-ops')
        && document.querySelector('#ops-sync-navigation')`,
      30000
    );
    completeStep("wait_for_app_bootstrap");
    markStep("enter_ops_mode");
    await clickSelector(evaluate, "#mode-ops");
    await waitFor(
      evaluate,
      "ops mode active",
      `typeof appState !== 'undefined'
        && appState.activeProduct === 'ops'
        && document.querySelector('#ops-nav-account-id')`,
      30000
    );
    completeStep("enter_ops_mode");

    markStep("seed_navigation_context");
    await setValue(evaluate, "#ops-nav-account-id", seed.account_id);
    await setValue(evaluate, "#ops-nav-world-id", seed.world_id);
    await setValue(evaluate, "#ops-nav-case-id", seed.case_id);
    await setValue(evaluate, "#ops-nav-alert-id", seed.stale_alert_id);
    await clickSelector(evaluate, "#ops-sync-navigation");
    completeStep("seed_navigation_context");

    markStep("detect_stale_warning");
    await waitFor(
      evaluate,
      "stale alert warning",
      `appState.opsNavigationModel && (appState.opsNavigationModel.context_warnings || []).some((item) => item.startsWith('stale_alert_ref:'))`
    , 30000);
    completeStep("detect_stale_warning");
    markStep("detect_remediation_actions");
    await waitFor(
      evaluate,
      "remediation actions",
      `(() => {
        const text = document.querySelector('#ops-navigation-actions')?.innerText || '';
        return text.includes('Clear Stale Refs') && text.includes('Re-sync From Valid Context');
      })()`,
      30000
    );
    completeStep("detect_remediation_actions");

    markStep("resync_from_valid_context");
    await clickFollowUpAction(evaluate, "Re-sync From Valid Context");
    await waitFor(
      evaluate,
      "stale refs cleared after resync",
      `appState.opsNavigationModel && Object.keys(appState.opsNavigationModel.linked_context?.stale_refs || {}).length === 0`
    , 30000);
    await waitFor(
      evaluate,
      "resynced control plane values",
      `document.querySelector('#ops-nav-account-id')?.value === ${JSON.stringify(seed.account_id)}
        && document.querySelector('#ops-nav-world-id')?.value === ${JSON.stringify(seed.world_id)}
        && document.querySelector('#ops-nav-case-id')?.value === ${JSON.stringify(seed.case_id)}
        && document.querySelector('#ops-nav-alert-id')?.value === ''
        && document.querySelector('#ops-account-id')?.value === ${JSON.stringify(seed.account_id)}
        && document.querySelector('#ops-release-world-id')?.value === ${JSON.stringify(seed.world_id)}
        && document.querySelector('#ops-governance-case-id')?.value === ${JSON.stringify(seed.case_id)}`
    , 30000);
    completeStep("resync_from_valid_context");

    const resyncSnapshot = await evaluate(`({
      warnings: appState.opsNavigationModel.context_warnings || [],
      followUpText: document.querySelector('#ops-navigation-actions')?.innerText || '',
      nav: {
        account: document.querySelector('#ops-nav-account-id')?.value || '',
        world: document.querySelector('#ops-nav-world-id')?.value || '',
        caseId: document.querySelector('#ops-nav-case-id')?.value || '',
        alertId: document.querySelector('#ops-nav-alert-id')?.value || ''
      }
    })`);

    markStep("reinject_stale_alert");
    await setValue(evaluate, "#ops-nav-alert-id", seed.stale_alert_id);
    await clickSelector(evaluate, "#ops-sync-navigation");
    await waitFor(
      evaluate,
      "stale alert warning restored",
      `appState.opsNavigationModel && (appState.opsNavigationModel.context_warnings || []).some((item) => item.startsWith('stale_alert_ref:'))`
    , 30000);
    completeStep("reinject_stale_alert");

    markStep("clear_stale_refs");
    await clickFollowUpAction(evaluate, "Clear Stale Refs");
    await waitFor(
      evaluate,
      "stale refs cleared after clear action",
      `appState.opsNavigationModel && Object.keys(appState.opsNavigationModel.linked_context?.stale_refs || {}).length === 0`
    , 30000);
    await waitFor(
      evaluate,
      "alert input cleared after clear action",
      `document.querySelector('#ops-nav-alert-id')?.value === ''`
    );
    completeStep("clear_stale_refs");

    const clearSnapshot = await evaluate(`({
      warnings: appState.opsNavigationModel.context_warnings || [],
      staleRefs: appState.opsNavigationModel.linked_context?.stale_refs || {},
      nav: {
        account: document.querySelector('#ops-nav-account-id')?.value || '',
        world: document.querySelector('#ops-nav-world-id')?.value || '',
        caseId: document.querySelector('#ops-nav-case-id')?.value || '',
        alertId: document.querySelector('#ops-nav-alert-id')?.value || ''
      }
    })`);

    console.log(
      JSON.stringify(
        {
          status: "ok",
          app_url: url,
          seed,
          completed_steps: stepOrder,
          failed_step: null,
          resyncSnapshot,
          clearSnapshot,
        },
        null,
        2
      )
    );
    const resultPayload = {
      status: "ok",
      app_url: url,
      seed,
      completed_steps: stepOrder,
      failed_step: null,
      failure_artifact_file: null,
      failure_screenshot_file: null,
      resyncSnapshot,
      clearSnapshot,
    };
    writeResult(resultPayload);
    console.log(JSON.stringify(resultPayload, null, 2));
  } catch (error) {
    const failureSnapshot = await captureFailureSnapshot();
    const failureScreenshot = await captureFailureScreenshot();
    const failureArtifact = {
      status: "error",
      app_url: url,
      seed,
      completed_steps: stepOrder,
      failed_step: currentStep,
      error_message: error && error.message ? error.message : String(error),
      snapshot: failureSnapshot,
      screenshot: failureScreenshot,
    };
    writeFailureArtifact(failureArtifact);
    const resultPayload = {
      status: "error",
      app_url: url,
      seed,
      completed_steps: stepOrder,
      failed_step: currentStep,
      error_message: error && error.message ? error.message : String(error),
      failure_artifact_file: failureArtifactFile,
      failure_screenshot_file: failureScreenshot.screenshot_file,
    };
    writeResult(resultPayload);
    throw error;
  } finally {
    ws.close();
  }
}

main().catch((error) => {
  console.error("OPS_NAVIGATION_STALE_REF_SMOKE_ERROR");
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
