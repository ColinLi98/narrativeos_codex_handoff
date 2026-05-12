const fs = require("fs");
const http = require("http");
const path = require("path");

const STORYBOOK_READY_TIMEOUT_MS = 300000;

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

function readJsonFile(targetPath) {
  return JSON.parse(fs.readFileSync(targetPath, "utf8"));
}

function writeJsonFile(targetPath, payload) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, JSON.stringify(payload, null, 2));
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
          const payload = JSON.parse(data);
          if (Number(response.statusCode || 0) >= 400) {
            reject(new Error(`HTTP ${response.statusCode} ${path}: ${JSON.stringify(payload)}`));
            return;
          }
          resolve(payload);
        } catch (_error) {
          reject(new Error(`Failed to parse JSON from ${path}: ${data}`));
        }
      });
    });
    request.on("error", reject);
    request.end();
  });
}

async function openTarget(chromePort, url) {
  return httpJson({
    method: "PUT",
    port: chromePort,
    path: `/json/new?${encodeURIComponent(url)}`,
  });
}

async function postSeedLogin(apiUrl, seed) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    signal: controller.signal,
    body: JSON.stringify({
      identifier: seed.auth_actor_id || seed.account_id,
      password: seed.auth_password,
    }),
  });
  clearTimeout(timer);
  const payload = await response.json();
  if (!response.ok || Number(payload.code || 0) !== 200 || !payload.data?.token) {
    throw new Error(`seed_reader_login_failed:${response.status}:${JSON.stringify(payload)}`);
  }
  return payload.data;
}

async function loginViaFrontendApi(url, seed) {
  if (url !== "http://127.0.0.1:8000") {
    try {
      return await postSeedLogin("http://127.0.0.1:8000", seed);
    } catch (_directError) {
      return postSeedLogin(url, seed);
    }
  }
  try {
    return await postSeedLogin(url, seed);
  } catch (error) {
    if (url === "http://127.0.0.1:8000") throw error;
    return postSeedLogin("http://127.0.0.1:8000", seed);
  }
}

async function connectToTarget(page) {
  if (!page?.webSocketDebuggerUrl) throw new Error("Chrome target is missing a websocket debugger URL");
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
    }
  };

  ws.onclose = () => {
    for (const { reject } of pending.values()) {
      reject(new Error("Chrome target websocket closed"));
    }
    pending.clear();
  };

  await new Promise((resolve) => {
    ws.onopen = resolve;
  });

  const send = (method, params = {}, timeoutMs = 60000) =>
    new Promise((resolve, reject) => {
      const current = ++id;
      const timer = setTimeout(() => {
        pending.delete(current);
        reject(new Error(`Timed out waiting for Chrome command ${method}`));
      }, timeoutMs);
      pending.set(current, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
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

  return { ws, send, evaluate, consoleErrors };
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(evaluate, label, expression, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function setValue(evaluate, selector, value) {
  return evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error('Missing selector: ' + ${JSON.stringify(selector)});
    const nextValue = ${JSON.stringify(value)};
    const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    if (descriptor && typeof descriptor.set === 'function') {
      descriptor.set.call(el, nextValue);
    } else {
      el.value = nextValue;
    }
    el.focus();
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: nextValue }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    if (el.value !== nextValue) throw new Error('Failed to set selector value: ' + ${JSON.stringify(selector)});
    return el.value;
  })()`);
}

async function clickByText(evaluate, selector, label) {
  return evaluate(`(() => {
    const button = Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find((item) => item.textContent.trim() === ${JSON.stringify(label)});
    if (!button) throw new Error('Missing button: ' + ${JSON.stringify(label)});
    button.click();
    return true;
  })()`);
}

async function captureScreenshot(send, targetPath) {
  const result = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, Buffer.from(result.data, "base64"));
  return targetPath;
}

function targetWindowFor(chapterIndex) {
  if (chapterIndex >= 1 && chapterIndex <= 40) return "early";
  if (chapterIndex >= 220 && chapterIndex <= 300) return "middle";
  if (chapterIndex >= 460 && chapterIndex <= 500) return "ending";
  return "recent";
}

async function ensureLoggedIn(evaluate, seed) {
  await waitFor(
    evaluate,
    "Quantum story page or auth recovery",
    `document.querySelector('#reader-v2-storybook-title') || document.body.innerText.includes('登录后继续阅读')`,
    STORYBOOK_READY_TIMEOUT_MS
  );
  const needsLogin = await evaluate(`document.body.innerText.includes('登录后继续阅读')`);
  if (!needsLogin) {
    await waitFor(
      evaluate,
      "authenticated Quantum Storybook",
      `document.querySelector('#reader-v2-storybook-title') && (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length > 400`,
      STORYBOOK_READY_TIMEOUT_MS
    );
    return;
  }
  await clickByText(evaluate, "button", "登录后继续");
  await waitFor(evaluate, "auth modal", `document.querySelector('#quantum-auth-identifier') && document.querySelector('#quantum-auth-password')`, 15000);
  await setValue(evaluate, "#quantum-auth-identifier", seed.auth_actor_id || seed.account_id);
  await setValue(evaluate, "#quantum-auth-password", seed.auth_password);
  await clickByText(evaluate, "button", "即刻降临");
  await waitFor(evaluate, "stored Quantum auth token", `Boolean(localStorage.getItem('qi_token'))`, 15000);
  await evaluate(`location.reload()`);
  await waitFor(
    evaluate,
    "authenticated Quantum Storybook",
    `document.querySelector('#reader-v2-storybook-title') && (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length > 400`,
    STORYBOOK_READY_TIMEOUT_MS
  );
}

async function seedBrowserAuth(evaluate, authPayload) {
  await evaluate(`(() => {
    localStorage.setItem('qi_token', ${JSON.stringify(authPayload.token)});
    localStorage.setItem('qi_refresh', ${JSON.stringify(authPayload.refreshToken || '')});
    window.dispatchEvent(new Event('qi-auth-changed'));
    return true;
  })()`);
}

async function seedBrowserAuthBeforeNavigation(send, authPayload) {
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `
      (() => {
        try {
          localStorage.setItem('qi_token', ${JSON.stringify(authPayload.token)});
          localStorage.setItem('qi_refresh', ${JSON.stringify(authPayload.refreshToken || '')});
        } catch (_error) {}
      })();
    `,
  });
}

async function selectStorybookChapter(evaluate, chapterIndex) {
  const windowKey = targetWindowFor(chapterIndex);
  await evaluate(`(() => {
    const tab = document.querySelector('[data-reader-storybook-window="${windowKey}"]');
    if (!tab) throw new Error('Missing storybook window tab: ${windowKey}');
    if (tab.disabled) throw new Error('Disabled storybook window tab: ${windowKey}');
    tab.click();
    return true;
  })()`);
  await waitFor(
    evaluate,
    `storybook window ${windowKey}`,
    `document.querySelector('[data-reader-storybook-window="${windowKey}"]') && document.querySelector('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card')`,
    15000
  );
  await evaluate(`(() => {
    const cards = Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card'));
    const card = cards.find((item) => (item.innerText || '').includes('Chapter ${Number(chapterIndex)}'));
    if (!card) throw new Error('Missing trajectory card for chapter ${Number(chapterIndex)}');
    card.click();
    return true;
  })()`);
  await waitFor(
    evaluate,
    `storybook chapter ${chapterIndex}`,
    `(() => {
      const active = document.querySelector('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card.is-active');
      return Boolean(active && (active.innerText || '').includes('Chapter ${Number(chapterIndex)}') && (document.querySelector('#reader-v2-storybook-title')?.innerText || '').trim().length > 0);
    })()`,
    15000
  );
}

async function chapterSnapshot(evaluate) {
  return evaluate(`(() => {
    const quote = (document.querySelector('#reader-v2-storybook-quote')?.innerText || '').trim();
    const beats = Array.from(document.querySelectorAll('#reader-v2-storybook-beats .reader-shell-v2__beat-copy')).map((item) => item.innerText.trim()).filter(Boolean);
    const activeCard = document.querySelector('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card.is-active');
    return {
      title: (document.querySelector('#reader-v2-storybook-title')?.innerText || '').trim(),
      prose_length: (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length,
      quote,
      quote_length: quote.length,
      quote_placeholder: quote.includes('这里会显示') || quote.includes('未记录'),
      beat_count: beats.length,
      active_card_text: activeCard?.innerText || '',
      url: location.href,
    };
  })()`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = String(args.url || "http://127.0.0.1:3000").replace(/\/$/, "");
  const chromePort = Number(args["chrome-port"] || 9225);
  const seedFile = args["seed-file"];
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  const screenshotDir = args["screenshot-dir"];
  if (!seedFile || !resultFile || !failureArtifactFile || !screenshotDir) {
    throw new Error("Usage: node verify_reader_storybook_500_quantum.js --url <frontend-url> --seed-file <json> --result-file <json> --failure-artifact-file <json> --screenshot-dir <dir> [--chrome-port <port>]");
  }

  const seed = readJsonFile(seedFile);
  const firstSession = seed.world_summaries?.[0]?.session_id;
  if (!firstSession) throw new Error("seed_missing_world_summaries");
  const authPayload = await loginViaFrontendApi(url, seed);

  const completedSteps = [];
  let currentStep = "bootstrap";
  let activePage = null;
  const allConsoleErrors = [];
  const mark = (step) => {
    currentStep = step;
  };
  const complete = (step) => {
    completedSteps.push(step);
  };

  try {
    mark("login");
    complete("login");

    const worldResults = [];
    for (const [worldIndex, worldSummary] of (seed.world_summaries || []).entries()) {
      mark(`open:${worldSummary.world_id}`);
      const storyUrl = `${url}/story?session=${encodeURIComponent(worldSummary.session_id)}&reader_verify=${worldIndex + 1}`;
      const target = await openTarget(chromePort, "about:blank");
      activePage = await connectToTarget(target);
      const { ws, send, evaluate, consoleErrors } = activePage;
      await seedBrowserAuthBeforeNavigation(send, authPayload);
      await send("Page.navigate", { url: storyUrl });
      await waitFor(evaluate, `Quantum Story URL ${worldSummary.world_id}`, `location.href === ${JSON.stringify(storyUrl)}`, 15000);
      await ensureLoggedIn(evaluate, seed);
      const storyReadyExpression = `document.querySelector('#reader-v2-storybook-title') && (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length > 400`;
      try {
        await waitFor(
          evaluate,
          `Quantum Story session ${worldSummary.world_id}`,
          storyReadyExpression,
          STORYBOOK_READY_TIMEOUT_MS
        );
      } catch (error) {
        const retryUrl = `${storyUrl}&reader_verify_retry=1`;
        await send("Page.navigate", { url: retryUrl });
        await waitFor(evaluate, `Quantum Story retry URL ${worldSummary.world_id}`, `location.href === ${JSON.stringify(retryUrl)}`, 15000);
        await waitFor(
          evaluate,
          `Quantum Story session retry ${worldSummary.world_id}`,
          storyReadyExpression,
          STORYBOOK_READY_TIMEOUT_MS
        );
      }
      complete(`open:${worldSummary.world_id}`);

      const chapterResults = [];
      for (const chapterIndex of worldSummary.review_target_chapters || []) {
        mark(`chapter:${worldSummary.world_id}:${chapterIndex}`);
        await selectStorybookChapter(evaluate, Number(chapterIndex));
        const snapshot = await chapterSnapshot(evaluate);
        if (!snapshot.title) throw new Error(`reader_storybook_title_missing:${worldSummary.world_id}:${chapterIndex}`);
        if (snapshot.prose_length <= 400) throw new Error(`reader_storybook_prose_too_short:${worldSummary.world_id}:${chapterIndex}:${snapshot.prose_length}`);
        if (snapshot.quote_length < 8 || snapshot.quote_placeholder) throw new Error(`reader_storybook_quote_invalid:${worldSummary.world_id}:${chapterIndex}`);
        if (snapshot.beat_count < 1) throw new Error(`reader_storybook_beats_missing:${worldSummary.world_id}:${chapterIndex}`);
        if (!String(snapshot.active_card_text || "").includes(`Chapter ${Number(chapterIndex)}`)) {
          throw new Error(`reader_storybook_active_card_mismatch:${worldSummary.world_id}:${chapterIndex}`);
        }
        chapterResults.push({
          chapter_index: Number(chapterIndex),
          title: snapshot.title,
          prose_length: snapshot.prose_length,
          quote_length: snapshot.quote_length,
          beat_count: snapshot.beat_count,
        });
        complete(`chapter:${worldSummary.world_id}:${chapterIndex}`);
      }
      const screenshotPath = path.join(screenshotDir, `${worldSummary.world_id}.png`);
      await captureScreenshot(send, screenshotPath);
      allConsoleErrors.push(...consoleErrors.map((item) => ({ ...item, world_id: worldSummary.world_id })));
      await send("Page.close", {}, 5000).catch(() => {});
      ws.close();
      activePage = null;
      worldResults.push({
        world_id: worldSummary.world_id,
        session_id: worldSummary.session_id,
        reached_chapters: worldSummary.reached_chapters,
        sampled_chapter_count: chapterResults.length,
        screenshot_file: screenshotPath,
        chapters: chapterResults,
      });
    }

    if (allConsoleErrors.length) {
      throw new Error(`Quantum Storybook emitted ${allConsoleErrors.length} console error(s)`);
    }

    const reviewedCount = worldResults.reduce((total, item) => total + item.sampled_chapter_count, 0);
    const resultPayload = {
      status: "ok",
      schema_version: "reader_storybook_500_quantum_result/v1",
      app_url: url,
      seed_file: seedFile,
      target_count: (seed.world_summaries || []).reduce((total, item) => total + (item.review_target_chapters || []).length, 0),
      reviewed_count: reviewedCount,
      world_count: worldResults.length,
      worlds_reaching_500: (seed.world_summaries || []).filter((item) => Number(item.reached_chapters || 0) >= 500).length,
      completed_steps: completedSteps,
      console_errors: allConsoleErrors,
      world_results: worldResults,
      screenshot_dir: screenshotDir,
    };
    writeJsonFile(resultFile, resultPayload);
    console.log(JSON.stringify(resultPayload, null, 2));
  } catch (error) {
    const evaluate = activePage?.evaluate;
    const snapshot = evaluate ? await evaluate(`({
      title: document.title || '',
      url: location.href || '',
      body_text_excerpt: (document.body?.innerText || '').slice(0, 5000),
      storybook_title: document.querySelector('#reader-v2-storybook-title')?.innerText || '',
      storybook_prose_length: (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length,
      trajectory_text: Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card')).map((item) => item.innerText),
    })`).catch((snapshotError) => ({ snapshot_error: snapshotError.message || String(snapshotError) })) : { snapshot_error: "no_active_chrome_target" };
    const failurePayload = {
      status: "error",
      app_url: url,
      seed_file: seedFile,
      completed_steps: completedSteps,
      failed_step: currentStep,
      error_message: error && error.message ? error.message : String(error),
      snapshot,
      console_errors: allConsoleErrors.concat(activePage?.consoleErrors || []),
    };
    writeJsonFile(failureArtifactFile, failurePayload);
    writeJsonFile(resultFile, failurePayload);
    throw error;
  } finally {
    if (activePage?.ws) activePage.ws.close();
  }
}

main().catch((error) => {
  console.error("READER_STORYBOOK_500_QUANTUM_ERROR");
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
