const fs = require("fs");
const http = require("http");
const path = require("path");

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    if (!current.startsWith("--")) continue;
    result[current.slice(2)] = argv[index + 1];
    index += 1;
  }
  return result;
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
    if (body !== undefined) request.write(body);
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
  if (!page) throw new Error(`App page target not found for ${pageUrl}`);
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
      consoleErrors.push({ type: "log.error", text: message.params.entry.text || "" });
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

async function waitFor(evaluate, label, expression, timeoutMs = 30000) {
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

async function setChecked(evaluate, selector, checked) {
  const escapedSelector = JSON.stringify(selector);
  return evaluate(`(() => {
    const el = document.querySelector(${escapedSelector});
    if (!el) throw new Error('Missing selector: ' + ${escapedSelector});
    el.checked = ${checked ? "true" : "false"};
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return el.checked;
  })()`);
}

async function setViewport(send, { width, height, mobile = false }) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
}

async function captureScreenshotToFile(send, screenshotFile) {
  const result = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  fs.mkdirSync(path.dirname(screenshotFile), { recursive: true });
  fs.writeFileSync(screenshotFile, Buffer.from(result.data, "base64"));
  return {
    screenshot_file: screenshotFile,
    screenshot_bytes: Buffer.byteLength(result.data, "base64"),
  };
}

async function collectStudioQaSnapshot(evaluate) {
  return evaluate(`(() => {
    const text = document.querySelector('#agent-studio-shell')?.innerText || '';
    const visible = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return false;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    };
    const scrollWidth = Math.max(
      document.documentElement?.scrollWidth || 0,
      document.body?.scrollWidth || 0
    );
    const viewportWidth = window.innerWidth || document.documentElement?.clientWidth || 0;
    return {
      reader_body_length: (document.querySelector('#agent-studio-reader-body')?.innerText || '').trim().length,
      director_visible: visible('.agent-studio-director'),
      branch_map_visible: visible('#agent-studio-branches'),
      quality_visible: visible('#agent-studio-quality'),
      quality_labels: Array.from(document.querySelectorAll('#agent-studio-quality .agent-studio-quality-item span')).map((item) => item.innerText.trim()),
      workbench_visible: visible('#agent-studio-workbench'),
      visible_q_code: /Q03|Q04|Q05|Q09/.test(text),
      empty_shell: text.trim().length < 200,
      horizontal_overflow_width: Math.max(0, scrollWidth - viewportWidth),
      viewport_width: viewportWidth,
      viewport_height: window.innerHeight || document.documentElement?.clientHeight || 0,
    };
  })()`);
}

async function collectDesktopStickyDirectorSnapshot(evaluate) {
  await evaluate(`(() => {
    const target = document.querySelector('.agent-studio-choice-section') || document.querySelector('.agent-studio-rail');
    target?.scrollIntoView({ block: 'start' });
    return true;
  })()`);
  await sleep(250);
  return evaluate(`(() => {
    const director = document.querySelector('.agent-studio-director');
    const style = director ? window.getComputedStyle(director) : null;
    const rect = director ? director.getBoundingClientRect() : null;
    const visibleInViewport = Boolean(
      rect &&
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.top < window.innerHeight &&
      rect.right > 0 &&
      rect.left < window.innerWidth
    );
    const directorRectTop = rect ? Number(rect.top) : null;
    const stickyDirector =
      Number(window.scrollY || 0) > 0 &&
      style?.position === 'sticky' &&
      visibleInViewport &&
      Number.isFinite(directorRectTop) &&
      directorRectTop >= 0 &&
      directorRectTop <= 32;
    return {
      scroll_y: Number(window.scrollY || 0),
      viewport_height: Number(window.innerHeight || 0),
      director_position: style?.position || '',
      director_top_style: style?.top || '',
      director_rect_top: directorRectTop,
      director_rect_bottom: rect ? Number(rect.bottom) : null,
      director_visible_in_viewport: visibleInViewport,
      desktop_sticky_director: stickyDirector,
    };
  })()`);
}

async function collectMobileChoiceScrollSnapshot(evaluate) {
  return evaluate(`(() => {
    const choiceGrid = document.querySelector('.agent-studio-choice-grid');
    const director = document.querySelector('.agent-studio-director');
    const choiceStyle = choiceGrid ? window.getComputedStyle(choiceGrid) : null;
    const choiceRect = choiceGrid ? choiceGrid.getBoundingClientRect() : null;
    const directorRect = director ? director.getBoundingClientRect() : null;
    const viewportHeight = Number(window.innerHeight || 0);
    const maxAllowedHeight = Math.min(380, viewportHeight * 0.45);
    const clientHeight = Number(choiceGrid?.clientHeight || 0);
    const scrollHeight = Number(choiceGrid?.scrollHeight || 0);
    const overflowY = choiceStyle?.overflowY || '';
    const boundedScroll =
      Boolean(choiceGrid) &&
      clientHeight > 0 &&
      clientHeight <= maxAllowedHeight + 2 &&
      ['auto', 'scroll'].includes(overflowY) &&
      (choiceStyle?.maxHeight || '') !== 'none';
    return {
      viewport_height: viewportHeight,
      mobile_choice_client_height: clientHeight,
      mobile_choice_scroll_height: scrollHeight,
      mobile_choice_overflow_y: overflowY,
      mobile_choice_max_height: choiceStyle?.maxHeight || '',
      mobile_choice_max_allowed_height: maxAllowedHeight,
      mobile_choice_rect_top: choiceRect ? Number(choiceRect.top) : null,
      mobile_choice_rect_bottom: choiceRect ? Number(choiceRect.bottom) : null,
      mobile_director_rect_top: directorRect ? Number(directorRect.top) : null,
      mobile_choice_bounded_scroll: boundedScroll,
    };
  })()`);
}

async function readGenerationWaitCopy(evaluate) {
  return evaluate(`(() => {
    const status = authorState.agentStudio?.generationStatus || {};
    return {
      kind: status.kind || '',
      message: status.message || '',
      detail: status.detail || '',
      startedAt: status.startedAt || '',
      visible_text: document.querySelector('#agent-studio-generation-status')?.innerText || ''
    };
  })()`);
}

function markdownCell(value) {
  return String(value ?? "")
    .replaceAll("|", "\\|")
    .replaceAll("\r", " ")
    .replaceAll("\n", " ");
}

function checklistRow(viewport, check, passed, evidence, reviewerNote = "") {
  return {
    viewport,
    check,
    status: passed ? "auto_pass" : "blocking_failure",
    evidence,
    reviewer_note: reviewerNote,
  };
}

function manualReviewRow(viewport, check, evidence, reviewerNote) {
  return {
    viewport,
    check,
    status: "manual_review",
    evidence,
    reviewer_note: reviewerNote,
  };
}

function buildVisualReviewChecklist({
  desktopQaSnapshot,
  mobileQaSnapshot,
  desktopScreenshot,
  mobileScreenshot,
  exportSnapshot,
  expectedQualityLabels,
  desktopStickyDirectorSnapshot,
  mobileChoiceScrollSnapshot,
}) {
  const desktopQualityLabelsPresent = expectedQualityLabels.every((label) => desktopQaSnapshot.quality_labels.includes(label));
  const mobileQualityLabelsPresent = expectedQualityLabels.every((label) => mobileQaSnapshot.quality_labels.includes(label));
  return [
    checklistRow("desktop", "Reader body present", desktopQaSnapshot.reader_body_length >= 80, `${desktopQaSnapshot.reader_body_length} chars`),
    checklistRow("desktop", "Director panel visible", desktopQaSnapshot.director_visible, String(desktopQaSnapshot.director_visible)),
    checklistRow(
      "desktop",
      "Desktop sticky director",
      Boolean(desktopStickyDirectorSnapshot?.desktop_sticky_director),
      `position=${desktopStickyDirectorSnapshot?.director_position || "-"}, top=${desktopStickyDirectorSnapshot?.director_rect_top ?? "-"}, scrollY=${desktopStickyDirectorSnapshot?.scroll_y ?? "-"}`
    ),
    checklistRow("desktop", "Branch map visible", desktopQaSnapshot.branch_map_visible, String(desktopQaSnapshot.branch_map_visible)),
    checklistRow("desktop", "Quality labels visible", desktopQualityLabelsPresent, desktopQaSnapshot.quality_labels.join(", ")),
    manualReviewRow(
      "desktop",
      "Three-column workbench review",
      desktopScreenshot.screenshot_file,
      "Confirm the layout feels balanced, content does not overlap, and the reader remains the primary focus."
    ),
    checklistRow("mobile", "No horizontal overflow", mobileQaSnapshot.horizontal_overflow_width <= 2, `${mobileQaSnapshot.horizontal_overflow_width}px overflow`),
    checklistRow("mobile", "Reader body present", mobileQaSnapshot.reader_body_length >= 80, `${mobileQaSnapshot.reader_body_length} chars`),
    checklistRow("mobile", "Director panel visible", mobileQaSnapshot.director_visible, String(mobileQaSnapshot.director_visible)),
    checklistRow(
      "mobile",
      "Mobile choice bounded scroll",
      Boolean(mobileChoiceScrollSnapshot?.mobile_choice_bounded_scroll),
      `client=${mobileChoiceScrollSnapshot?.mobile_choice_client_height ?? "-"}, scroll=${mobileChoiceScrollSnapshot?.mobile_choice_scroll_height ?? "-"}, overflowY=${mobileChoiceScrollSnapshot?.mobile_choice_overflow_y || "-"}`
    ),
    checklistRow("mobile", "Branch map visible", mobileQaSnapshot.branch_map_visible, String(mobileQaSnapshot.branch_map_visible)),
    checklistRow("mobile", "Quality labels visible", mobileQualityLabelsPresent, mobileQaSnapshot.quality_labels.join(", ")),
    manualReviewRow(
      "mobile",
      "Stacked workbench review",
      mobileScreenshot.screenshot_file,
      "Confirm the stacked layout is readable, controls are reachable, and no text is clipped."
    ),
    checklistRow(
      "shared",
      "No visible quality codes",
      !desktopQaSnapshot.visible_q_code && !mobileQaSnapshot.visible_q_code && !exportSnapshot.visible_q_code,
      `desktop=${desktopQaSnapshot.visible_q_code}, mobile=${mobileQaSnapshot.visible_q_code}, export=${exportSnapshot.visible_q_code}`
    ),
    checklistRow(
      "shared",
      "No empty shell",
      !desktopQaSnapshot.empty_shell && !mobileQaSnapshot.empty_shell,
      `desktop=${desktopQaSnapshot.empty_shell}, mobile=${mobileQaSnapshot.empty_shell}`
    ),
    checklistRow(
      "shared",
      "Screenshots captured",
      Number(desktopScreenshot.screenshot_bytes || 0) > 0 && Number(mobileScreenshot.screenshot_bytes || 0) > 0,
      `desktop=${desktopScreenshot.screenshot_bytes || 0} bytes, mobile=${mobileScreenshot.screenshot_bytes || 0} bytes`
    ),
  ];
}

function summarizeVisualReview(checklist) {
  return {
    visual_review_total: checklist.length,
    visual_review_auto_pass: checklist.filter((item) => item.status === "auto_pass").length,
    visual_review_manual_review: checklist.filter((item) => item.status === "manual_review").length,
    visual_review_blocking_failures: checklist.filter((item) => item.status === "blocking_failure").length,
  };
}

function writeVisualReviewMarkdown(visualReviewFile, checklist, summary, { desktopScreenshotFile, mobileScreenshotFile }) {
  const lines = [
    "# Agent Studio Visual Review",
    "",
    `- Desktop screenshot: \`${desktopScreenshotFile}\``,
    `- Mobile screenshot: \`${mobileScreenshotFile}\``,
    `- Auto pass: \`${summary.visual_review_auto_pass}\``,
    `- Manual review: \`${summary.visual_review_manual_review}\``,
    `- Blocking failures: \`${summary.visual_review_blocking_failures}\``,
    "",
    "| Viewport | Check | Status | Evidence | Reviewer note |",
    "| --- | --- | --- | --- | --- |",
  ];
  for (const item of checklist) {
    lines.push(
      `| ${markdownCell(item.viewport)} | ${markdownCell(item.check)} | ${markdownCell(item.status)} | ${markdownCell(item.evidence)} | ${markdownCell(item.reviewer_note)} |`
    );
  }
  lines.push("");
  fs.mkdirSync(path.dirname(visualReviewFile), { recursive: true });
  fs.writeFileSync(visualReviewFile, lines.join("\n"), "utf8");
}

async function buildAuthHeaders(hostname, port, actorId, actorRole, password) {
  await httpJson({
    method: "POST",
    hostname,
    port,
    path: "/v1/auth/register",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actor_id: actorId,
      actor_role: actorRole,
      password,
      account_id: actorId,
    }),
  });
  const login = await httpJson({
    method: "POST",
    hostname,
    port,
    path: "/v1/auth/login",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor_id: actorId, password }),
  });
  return { Authorization: `Bearer ${login.token.access_token}`, "Content-Type": "application/json" };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url;
  const appUrl = new URL(url);
  const chromePort = Number(args["chrome-port"] || 9238);
  const databaseUrl = args["database-url"];
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  const failureScreenshotFile = args["failure-screenshot-file"];
  const desktopScreenshotFile = args["desktop-screenshot-file"];
  const mobileScreenshotFile = args["mobile-screenshot-file"];
  const visualReviewFile = args["visual-review-file"];
  const GUARD = { id: "agent_studio_smoke", label: "Agent Studio Smoke" };
  if (!url || !databaseUrl || !resultFile || !failureArtifactFile || !failureScreenshotFile || !desktopScreenshotFile || !mobileScreenshotFile || !visualReviewFile) {
    throw new Error("Usage: node verify_agent_studio_smoke.js --url <app-url> --database-url <database-url> --result-file <json> --failure-artifact-file <json> --failure-screenshot-file <png> --desktop-screenshot-file <png> --mobile-screenshot-file <png> --visual-review-file <md> [--chrome-port <port>]");
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
  const buildResultPayload = ({ status, failedStep = null, summary = {}, consoleErrors = [], errorMessage = null, failureArtifact = null, failureScreenshot = null, visualReviewChecklist = [] }) => ({
    status,
    schema_version: "agent_studio_smoke/v1",
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
      desktop_screenshot_file: desktopScreenshotFile,
      mobile_screenshot_file: mobileScreenshotFile,
      visual_review_file: visualReviewFile,
    },
    app_url: url,
    completed_steps: stepOrder,
    failed_step: failedStep,
    console_errors: consoleErrors,
    ...(errorMessage ? { error_message: errorMessage } : {}),
    visual_review_checklist: visualReviewChecklist,
    summary,
    failure_artifact_file: failureArtifact,
    failure_screenshot_file: failureScreenshot,
  });

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
        studio_text: document.querySelector('#agent-studio-shell')?.innerText?.slice(0, 3000) || "",
        active_work_id: typeof authorState !== 'undefined' ? authorState.activeWorkId || "" : "",
        chapter_count: typeof authorState !== 'undefined' ? Number(authorState.activeWorkDetail?.chapter_count || 0) : 0,
        route_count: typeof authorState !== 'undefined' ? Number(authorState.activeWorkDetail?.branch_family?.length || 0) : 0,
        generation_status: document.querySelector('#agent-studio-generation-status')?.innerText || "",
        body_text_excerpt: (document.body?.innerText || "").slice(0, 4000)
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
      return { screenshot_file: failureScreenshotFile, screenshot_error: null };
    } catch (error) {
      return { screenshot_file: null, screenshot_error: error && error.message ? error.message : String(error) };
    }
  };

  try {
    await setViewport(send, { width: 1440, height: 1000 });
    const authorActorId = `agent_studio_${Date.now()}`;
    const authorPassword = "secret123";
    const reviewerHeaders = await buildAuthHeaders(appUrl.hostname, Number(appUrl.port || 80), `agent_studio_reviewer_${Date.now()}`, "reviewer", authorPassword);

    markStep("load_page_title");
    await waitFor(evaluate, "page title", `document.title === 'NarrativeOS Studio'`);
    completeStep("load_page_title");

    markStep("wait_for_agent_studio_bootstrap");
    await waitFor(
      evaluate,
      "Agent Studio bootstrap",
      `window.__bootMarker === 'after-init'
        && document.querySelector('#app-shell')?.dataset.product === 'author'
        && new URL(location.href).searchParams.get('workspace') === 'studio'
        && typeof AuthorWorkspaceRuntime === 'object'
        && typeof AgentStudioRuntime === 'object'
        && document.querySelector('#agent-studio-shell')
        && !document.querySelector('#agent-studio-shell')?.innerText.includes('Q03')`,
      30000
    );
    completeStep("wait_for_agent_studio_bootstrap");

    markStep("author_register_login");
    await setValue(evaluate, "#author-auth-actor-id", authorActorId);
    await setValue(evaluate, "#author-auth-display-name", "Agent Studio Smoke");
    await setValue(evaluate, "#author-auth-password", authorPassword);
    await setValue(evaluate, "#author-auth-role", "author");
    await clickSelector(evaluate, "#author-auth-register");
    await waitFor(
      evaluate,
      "author session established",
      `Boolean(authorState.authorAuthSession?.accessToken)
        && (document.querySelector('#author-account-id')?.value || '') === ${JSON.stringify(authorActorId)}`,
      30000
    );
    completeStep("author_register_login");

    markStep("grant_author_creator_access");
    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/ops/subscriptions/grant",
      headers: reviewerHeaders,
      body: JSON.stringify({
        account_id: authorActorId,
        tier_id: "creator_pass",
        provider: "ops_manual",
        status: "active",
      }),
    });
    await httpJson({
      method: "POST",
      hostname: appUrl.hostname,
      port: Number(appUrl.port || 80),
      path: "/v1/ops/wallets/grant",
      headers: reviewerHeaders,
      body: JSON.stringify({
        account_id: authorActorId,
        wallet_type: "studio_credits",
        amount: 10,
      }),
    });
    await evaluate(`(async () => {
      await AuthorWorkspaceRuntime.refreshAuthorSurface();
      WorkspaceLayoutRuntime.setAuthorWorkspace('studio');
      ShellStatusRuntime.syncProductMode();
      AgentStudioRuntime.refreshStudio();
      return true;
    })()`);
    await waitFor(
      evaluate,
      "author credits and Studio visible",
      `Number(document.querySelector('#author-studio-credits')?.innerText || 0) >= 10
        && new URL(location.href).searchParams.get('workspace') === 'studio'
        && document.querySelector('#agent-studio-start')`,
      30000
    );
    completeStep("grant_author_creator_access");

    markStep("agent_studio_startup");
    const storyTitle = `雾港协作 ${Date.now()}`;
    await setValue(evaluate, "#agent-studio-title", storyTitle);
    await setValue(evaluate, "#agent-studio-genre", "urban_mystery");
    await setValue(evaluate, "#agent-studio-length", "short");
    await setValue(evaluate, "#agent-studio-reader-goal", "慢热悬疑");
    await setChecked(evaluate, "#agent-studio-remix", true);
    await clickSelector(evaluate, "#agent-studio-start-button");
    await waitFor(
      evaluate,
      "Studio startup wait copy",
      `authorState.agentStudio?.generationStatus?.message === '第一章生成中'
        && authorState.agentStudio?.generationStatus?.detail === '正在建立作品设定、人物冲突和章节正文，可能需要一两分钟。'
        && (document.querySelector('#agent-studio-generation-status')?.innerText || '').includes('第一章生成中')`,
      5000
    );
    const startupWaitCopy = await readGenerationWaitCopy(evaluate);
    await waitFor(
      evaluate,
      "first Studio chapter",
      `Boolean(authorState.activeWorkId)
        && Number(authorState.activeWorkDetail?.chapter_count || 0) >= 1
        && !document.querySelector('#agent-studio-workbench')?.classList.contains('is-hidden')
        && (document.querySelector('#agent-studio-reader-body')?.innerText || '').length > 80`,
      180000
    );
    const startupSnapshot = await evaluate(`({
      work_id: authorState.activeWorkId || '',
      chapter_count: Number(authorState.activeWorkDetail?.chapter_count || 0),
      route_count: Number(authorState.activeWorkDetail?.branch_family?.length || 0),
      visible_q_code: /Q03|Q04|Q05|Q09/.test(document.querySelector('#agent-studio-shell')?.innerText || ''),
      reader_title: document.querySelector('#agent-studio-reader-title')?.innerText || ''
    })`);
    if (startupSnapshot.visible_q_code) {
      throw new Error("Agent Studio exposed internal quality code in visible copy.");
    }
    const desktopQaSnapshot = await collectStudioQaSnapshot(evaluate);
    const expectedQualityLabels = ["重复感", "场景细节", "节奏", "结尾风险"];
    if (desktopQaSnapshot.reader_body_length < 80) {
      throw new Error("Agent Studio desktop reader body was blank or too short.");
    }
    if (!desktopQaSnapshot.director_visible || !desktopQaSnapshot.branch_map_visible || !desktopQaSnapshot.quality_visible) {
      throw new Error("Agent Studio desktop workbench is missing director, branch map, or quality status.");
    }
    if (!expectedQualityLabels.every((label) => desktopQaSnapshot.quality_labels.includes(label))) {
      throw new Error(`Agent Studio quality labels missing in desktop viewport: ${desktopQaSnapshot.quality_labels.join(",")}`);
    }
    if (desktopQaSnapshot.visible_q_code || desktopQaSnapshot.empty_shell) {
      throw new Error("Agent Studio desktop screenshot target exposed Q-code or rendered an empty shell.");
    }
    await setViewport(send, { width: 1440, height: 1000 });
    await evaluate(`document.querySelector('#agent-studio-workbench')?.scrollIntoView({ block: 'start' }); true`);
    await sleep(250);
    const desktopScreenshot = await captureScreenshotToFile(send, desktopScreenshotFile);
    completeStep("agent_studio_startup");

    markStep("agent_studio_sticky_director_regression");
    const desktopStickyDirectorSnapshot = await collectDesktopStickyDirectorSnapshot(evaluate);
    if (!desktopStickyDirectorSnapshot.desktop_sticky_director) {
      throw new Error(`Agent Studio sticky director regression: ${JSON.stringify(desktopStickyDirectorSnapshot)}`);
    }
    await evaluate(`document.querySelector('#agent-studio-workbench')?.scrollIntoView({ block: 'start' }); true`);
    await sleep(250);
    completeStep("agent_studio_sticky_director_check");

    markStep("agent_studio_director_continue");
    await setValue(evaluate, "#agent-studio-director-intent", "增加感情张力，但不要揭晓真相。");
    await clickSelector(evaluate, "#agent-studio-generate");
    await waitFor(
      evaluate,
      "Studio continuation wait copy",
      `authorState.agentStudio?.generationStatus?.message === '续写中'
        && authorState.agentStudio?.generationStatus?.detail === '正在沿导演意图推进下一章，完成后会自动跳到新章节。'
        && (document.querySelector('#agent-studio-generation-status')?.innerText || '').includes('续写中')`,
      5000
    );
    const continuationWaitCopy = await readGenerationWaitCopy(evaluate);
    await waitFor(
      evaluate,
      "Studio director continuation",
      `Number(authorState.activeWorkDetail?.chapter_count || 0) >= 2
        && (document.querySelector('#agent-studio-generation-status')?.innerText || '').includes('章已完成')
        && (document.querySelector('#agent-studio-reader-body')?.innerText || '').length > 80`,
      180000
    );
    const continueSnapshot = await evaluate(`({
      work_id: authorState.activeWorkId || '',
      chapter_count: Number(authorState.activeWorkDetail?.chapter_count || 0),
      route_count: Number(authorState.activeWorkDetail?.branch_family?.length || 0),
      choice_card_count: document.querySelectorAll('#agent-studio-choice-cards .agent-studio-choice-card').length,
      generation_status: document.querySelector('#agent-studio-generation-status')?.innerText || ''
    })`);
    completeStep("agent_studio_director_continue");

    markStep("agent_studio_create_branch");
    const routeCountBeforeBranch = Number(continueSnapshot.route_count || 0);
    await setValue(evaluate, "#agent-studio-director-intent", "从这里开启一条路线：主角提前摊牌，但继续隐藏真正证据。");
    await clickSelector(evaluate, "#agent-studio-create-branch");
    await waitFor(
      evaluate,
      "Studio branch wait copy",
      `authorState.agentStudio?.generationStatus?.message === '新路线创建中'
        && authorState.agentStudio?.generationStatus?.detail === '正在从当前章节保存分支。'
        && (document.querySelector('#agent-studio-generation-status')?.innerText || '').includes('新路线创建中')`,
      5000
    );
    const branchWaitCopy = await readGenerationWaitCopy(evaluate);
    await waitFor(
      evaluate,
      "Studio branch created",
      `Number(authorState.activeWorkDetail?.branch_family?.length || 0) > ${routeCountBeforeBranch}
        && (document.querySelector('#agent-studio-generation-status')?.innerText || '').includes('新路线已创建')
        && document.querySelectorAll('#agent-studio-branches .agent-studio-route-card').length > ${routeCountBeforeBranch}`,
      60000
    );
    const branchSnapshot = await evaluate(`({
      work_id: authorState.activeWorkId || '',
      chapter_count: Number(authorState.activeWorkDetail?.chapter_count || 0),
      route_count: Number(authorState.activeWorkDetail?.branch_family?.length || 0),
      branch_text: document.querySelector('#agent-studio-branches')?.innerText || '',
      active_route_label: document.querySelector('#agent-studio-route-select option:checked')?.innerText || ''
    })`);
    completeStep("agent_studio_create_branch");

    markStep("agent_studio_export_nosbook");
    await clickSelector(evaluate, "#agent-studio-export");
    await waitFor(
      evaluate,
      "Studio nosbook export",
      `authorState.agentStudio?.lastNosbookExport?.payload?.schema_version === 'nosbook/v1'
        && authorState.agentStudio?.lastNosbookExport?.contentType === 'application/vnd.narrativeos.nosbook+json'
        && Array.isArray(authorState.agentStudio?.lastNosbookExport?.payload?.chapters)
        && authorState.agentStudio.lastNosbookExport.payload.chapters.length >= 1
        && Array.isArray(authorState.agentStudio.lastNosbookExport.payload.branch_map)
        && authorState.agentStudio.lastNosbookExport.payload.branch_map.length >= 2`,
      30000
    );
    const exportSnapshot = await evaluate(`(() => {
      const exportPayload = authorState.agentStudio.lastNosbookExport.payload;
      return {
        filename: authorState.agentStudio.lastNosbookExport.filename || '',
        content_type: authorState.agentStudio.lastNosbookExport.contentType || '',
        schema_version: exportPayload.schema_version || '',
        chapter_count: Array.isArray(exportPayload.chapters) ? exportPayload.chapters.length : 0,
        branch_map_count: Array.isArray(exportPayload.branch_map) ? exportPayload.branch_map.length : 0,
        choice_history_count: Array.isArray(exportPayload.choice_history) ? exportPayload.choice_history.length : 0,
        quality_summary_keys: Object.keys(exportPayload.quality_summary || {}),
        export_route_name: exportPayload.export_route?.route_name || '',
        visible_q_code: /Q03|Q04|Q05|Q09/.test(document.querySelector('#agent-studio-shell')?.innerText || '')
      };
    })()`);
    if (exportSnapshot.visible_q_code) {
      throw new Error("Agent Studio exposed internal quality code after export.");
    }
    if (exportSnapshot.choice_history_count < 1) {
      throw new Error("Agent Studio export did not include choice history.");
    }
    await setViewport(send, { width: 390, height: 844, mobile: true });
    await evaluate(`document.querySelector('#agent-studio-workbench')?.scrollIntoView({ block: 'start' }); true`);
    await sleep(500);
    const mobileQaSnapshot = await collectStudioQaSnapshot(evaluate);
    if (mobileQaSnapshot.reader_body_length < 80) {
      throw new Error("Agent Studio mobile reader body was blank or too short.");
    }
    if (!mobileQaSnapshot.director_visible || !mobileQaSnapshot.branch_map_visible || !mobileQaSnapshot.quality_visible) {
      throw new Error("Agent Studio mobile workbench is missing director, branch map, or quality status.");
    }
    if (!expectedQualityLabels.every((label) => mobileQaSnapshot.quality_labels.includes(label))) {
      throw new Error(`Agent Studio quality labels missing in mobile viewport: ${mobileQaSnapshot.quality_labels.join(",")}`);
    }
    if (mobileQaSnapshot.visible_q_code || mobileQaSnapshot.empty_shell) {
      throw new Error("Agent Studio mobile screenshot target exposed Q-code or rendered an empty shell.");
    }
    if (mobileQaSnapshot.horizontal_overflow_width > 2) {
      throw new Error(`Agent Studio mobile viewport has horizontal overflow: ${mobileQaSnapshot.horizontal_overflow_width}px`);
    }

    markStep("agent_studio_mobile_choice_scroll_regression");
    const mobileChoiceScrollSnapshot = await collectMobileChoiceScrollSnapshot(evaluate);
    if (!mobileChoiceScrollSnapshot.mobile_choice_bounded_scroll) {
      throw new Error(`Agent Studio mobile choice scroll regression: ${JSON.stringify(mobileChoiceScrollSnapshot)}`);
    }
    completeStep("agent_studio_mobile_choice_scroll_check");
    markStep("agent_studio_export_nosbook");

    const mobileScreenshot = await captureScreenshotToFile(send, mobileScreenshotFile);
    await setViewport(send, { width: 1440, height: 1000 });
    const visualReviewChecklist = buildVisualReviewChecklist({
      desktopQaSnapshot,
      mobileQaSnapshot,
      desktopScreenshot,
      mobileScreenshot,
      exportSnapshot,
      expectedQualityLabels,
      desktopStickyDirectorSnapshot,
      mobileChoiceScrollSnapshot,
    });
    const visualReviewSummary = summarizeVisualReview(visualReviewChecklist);
    writeVisualReviewMarkdown(visualReviewFile, visualReviewChecklist, visualReviewSummary, {
      desktopScreenshotFile: desktopScreenshot.screenshot_file,
      mobileScreenshotFile: mobileScreenshot.screenshot_file,
    });
    if (visualReviewSummary.visual_review_blocking_failures > 0) {
      throw new Error(`Agent Studio visual review objective checks failed: ${visualReviewSummary.visual_review_blocking_failures}`);
    }
    completeStep("agent_studio_export_nosbook");

    const resultPayload = buildResultPayload({
      status: "ok",
      consoleErrors,
      visualReviewChecklist,
      summary: {
        headline_metric: "agent_studio_chapters_exported",
        headline_value: exportSnapshot.chapter_count,
        suite_scope: "agent_studio_smoke",
        author_actor_id: authorActorId,
        work_id: exportSnapshot.work_id || branchSnapshot.work_id || continueSnapshot.work_id || startupSnapshot.work_id,
        startup_chapter_count: startupSnapshot.chapter_count,
        chapter_count_after_continue: continueSnapshot.chapter_count,
        route_count_after_branch: branchSnapshot.route_count,
        nosbook_schema_version: exportSnapshot.schema_version,
        nosbook_content_type: exportSnapshot.content_type,
        nosbook_chapter_count: exportSnapshot.chapter_count,
        nosbook_branch_map_count: exportSnapshot.branch_map_count,
        nosbook_choice_history_count: exportSnapshot.choice_history_count,
        nosbook_quality_summary_keys: exportSnapshot.quality_summary_keys,
        visible_q_code: exportSnapshot.visible_q_code,
        desktop_screenshot_file: desktopScreenshot.screenshot_file,
        mobile_screenshot_file: mobileScreenshot.screenshot_file,
        mobile_overflow_width: mobileQaSnapshot.horizontal_overflow_width,
        desktop_sticky_director: desktopStickyDirectorSnapshot.desktop_sticky_director,
        desktop_director_top_after_scroll: desktopStickyDirectorSnapshot.director_rect_top,
        mobile_choice_bounded_scroll: mobileChoiceScrollSnapshot.mobile_choice_bounded_scroll,
        mobile_choice_client_height: mobileChoiceScrollSnapshot.mobile_choice_client_height,
        mobile_choice_scroll_height: mobileChoiceScrollSnapshot.mobile_choice_scroll_height,
        mobile_choice_overflow_y: mobileChoiceScrollSnapshot.mobile_choice_overflow_y,
        generation_wait_copy: {
          startup: startupWaitCopy,
          continuation: continuationWaitCopy,
          branch: branchWaitCopy,
        },
        desktop_reader_body_length: desktopQaSnapshot.reader_body_length,
        mobile_reader_body_length: mobileQaSnapshot.reader_body_length,
        mobile_director_visible: mobileQaSnapshot.director_visible,
        mobile_branch_map_visible: mobileQaSnapshot.branch_map_visible,
        mobile_quality_labels: mobileQaSnapshot.quality_labels,
        visual_review_file: visualReviewFile,
        visual_review_total: visualReviewSummary.visual_review_total,
        visual_review_auto_pass: visualReviewSummary.visual_review_auto_pass,
        visual_review_manual_review: visualReviewSummary.visual_review_manual_review,
        visual_review_blocking_failures: visualReviewSummary.visual_review_blocking_failures,
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
      console_errors: consoleErrors,
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
        suite_scope: "agent_studio_smoke",
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
  console.error("AGENT_STUDIO_SMOKE_ERROR");
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
