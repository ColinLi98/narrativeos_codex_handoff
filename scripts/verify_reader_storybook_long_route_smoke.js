const fs = require("fs");
const http = require("http");
const path = require("path");

const READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_SCHEMA_VERSION =
  "reader_storybook_title_homogenization_history/v1";
const READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT = 20;
const READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD = 3;
const TITLE_HOMOGENIZATION_WARNING_KIND = "title_homogenization_non_blocking";

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

function readJsonFile(targetPath) {
  if (!targetPath || !fs.existsSync(targetPath)) return {};
  try {
    return JSON.parse(fs.readFileSync(targetPath, "utf8"));
  } catch (_error) {
    return {};
  }
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

  return { ws, send, evaluate, consoleErrors };
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

function normalizeSignatureText(value) {
  return String(value || "")
    .replace(/第\s*\d+\s*章/g, " ")
    .replace(/[^\w\u4e00-\u9fff]+/g, "")
    .toLowerCase();
}

function bigramSet(value) {
  const normalized = normalizeSignatureText(value);
  if (!normalized) return new Set();
  if (normalized.length < 2) return new Set([normalized]);
  const grams = new Set();
  for (let index = 0; index < normalized.length - 1; index += 1) {
    grams.add(normalized.slice(index, index + 2));
  }
  return grams;
}

function jaccardSimilarity(left, right) {
  if (!left.size || !right.size) return 0;
  let intersection = 0;
  for (const item of left) {
    if (right.has(item)) intersection += 1;
  }
  return intersection / (left.size + right.size - intersection);
}

function normalizeHistoryEntry(entry) {
  return {
    generated_at: String(entry?.generated_at || "").trim(),
    world_ids: Array.from(
      new Set((entry?.world_ids || []).map((item) => String(item || "").trim()).filter(Boolean))
    ),
    cross_pack_distinctness: (entry?.cross_pack_distinctness || [])
      .map((item) => ({
        non_jade_world_id: String(item?.non_jade_world_id || "").trim(),
        jade_world_id: String(item?.jade_world_id || "").trim(),
        title_similarity: Number(Number(item?.title_similarity || 0).toFixed(3)),
        quote_similarity: Number(Number(item?.quote_similarity || 0).toFixed(3)),
        passes_min_difference: Boolean(item?.passes_min_difference),
      }))
      .filter((item) => item.non_jade_world_id && item.jade_world_id),
    title_homogenization_warnings: (entry?.title_homogenization_warnings || [])
      .map((item) => ({
        non_jade_world_id: String(item?.non_jade_world_id || "").trim(),
        jade_world_id: String(item?.jade_world_id || "").trim(),
        title_similarity: Number(Number(item?.title_similarity || 0).toFixed(3)),
        quote_similarity: Number(Number(item?.quote_similarity || 0).toFixed(3)),
        warning_kind: String(item?.warning_kind || TITLE_HOMOGENIZATION_WARNING_KIND).trim(),
        message: String(item?.message || "").trim(),
      }))
      .filter((item) => item.non_jade_world_id && item.jade_world_id),
  };
}

function normalizeHistoryPayload(payload) {
  const entries = (payload?.entries || [])
    .map((item) => normalizeHistoryEntry(item))
    .filter((item) => item.generated_at)
    .sort((left, right) => String(right.generated_at || "").localeCompare(String(left.generated_at || "")))
    .slice(0, READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT);
  return {
    schema_version: READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_SCHEMA_VERSION,
    available: entries.length > 0,
    history_limit: READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT,
    promotion_threshold: READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
    entry_count: entries.length,
    latest_generated_at: entries[0]?.generated_at || null,
    entries,
  };
}

function appendHistoryEntry(historyPayload, entry) {
  return normalizeHistoryPayload({
    entries: [normalizeHistoryEntry(entry), ...((historyPayload?.entries || []).map((item) => normalizeHistoryEntry(item)))]
      .filter((item) => item.generated_at),
  });
}

function historyEntryIncludesPair(entry, pair) {
  const worldIds = new Set((entry?.world_ids || []).map((item) => String(item || "").trim()));
  return worldIds.has(pair.non_jade_world_id) && worldIds.has(pair.jade_world_id);
}

function historyEntryWarningForPair(entry, pair) {
  return (entry?.title_homogenization_warnings || []).find(
    (item) =>
      item.non_jade_world_id === pair.non_jade_world_id &&
      item.jade_world_id === pair.jade_world_id &&
      item.warning_kind === TITLE_HOMOGENIZATION_WARNING_KIND
  ) || null;
}

function historyEntryDistinctnessForPair(entry, pair) {
  return (entry?.cross_pack_distinctness || []).find(
    (item) =>
      item.non_jade_world_id === pair.non_jade_world_id &&
      item.jade_world_id === pair.jade_world_id
  ) || null;
}

function buildTitleHomogenizationTrend(historyPayload) {
  const normalizedHistory = normalizeHistoryPayload(historyPayload);
  const pairMap = new Map();
  for (const entry of normalizedHistory.entries) {
    for (const item of entry.cross_pack_distinctness || []) {
      pairMap.set(`${item.non_jade_world_id}::${item.jade_world_id}`, {
        non_jade_world_id: item.non_jade_world_id,
        jade_world_id: item.jade_world_id,
      });
    }
    for (const item of entry.title_homogenization_warnings || []) {
      pairMap.set(`${item.non_jade_world_id}::${item.jade_world_id}`, {
        non_jade_world_id: item.non_jade_world_id,
        jade_world_id: item.jade_world_id,
      });
    }
  }
  const pairTrends = [];
  for (const pair of Array.from(pairMap.values()).sort((left, right) => `${left.non_jade_world_id}:${left.jade_world_id}`.localeCompare(`${right.non_jade_world_id}:${right.jade_world_id}`))) {
    let consecutiveWarningCount = 0;
    let eligibleRunCount = 0;
    let latestSeenAt = null;
    let latestDistinctness = null;
    for (const entry of normalizedHistory.entries) {
      const distinctness = historyEntryDistinctnessForPair(entry, pair);
      if (!latestDistinctness && distinctness) {
        latestDistinctness = distinctness;
      }
      if (!historyEntryIncludesPair(entry, pair)) {
        continue;
      }
      eligibleRunCount += 1;
      const warning = historyEntryWarningForPair(entry, pair);
      if (warning) {
        consecutiveWarningCount += 1;
        if (!latestSeenAt) {
          latestSeenAt = entry.generated_at || null;
        }
        continue;
      }
      break;
    }
    const promotedToReleaseReview =
      consecutiveWarningCount >= READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD;
    pairTrends.push({
      non_jade_world_id: pair.non_jade_world_id,
      jade_world_id: pair.jade_world_id,
      eligible_run_count: eligibleRunCount,
      consecutive_warning_count: consecutiveWarningCount,
      latest_seen_at: latestSeenAt,
      latest_title_similarity: Number(Number(latestDistinctness?.title_similarity || 0).toFixed(3)),
      latest_quote_similarity: Number(Number(latestDistinctness?.quote_similarity || 0).toFixed(3)),
      trend_status: promotedToReleaseReview
        ? "promoted"
        : consecutiveWarningCount > 0
          ? "watch"
          : "clear",
      promoted_to_release_review: promotedToReleaseReview,
    });
  }
  const promotedPairs = pairTrends.filter((item) => item.promoted_to_release_review);
  let trendStatus = "no_history";
  let trendReason = "no_reader_storybook_smoke_history";
  if (normalizedHistory.entry_count > 0) {
    if (promotedPairs.length) {
      trendStatus = "promoted_pairs_present";
      trendReason = "title_homogenization_promotion_threshold_met";
    } else if (pairTrends.some((item) => item.consecutive_warning_count > 0)) {
      trendStatus = "watch";
      trendReason = "title_homogenization_warning_streak_below_threshold";
    } else {
      trendStatus = "clear";
      trendReason = "no_active_title_homogenization_warning_streaks";
    }
  }
  return {
    available: normalizedHistory.entry_count > 0,
    entry_count: normalizedHistory.entry_count,
    latest_generated_at: normalizedHistory.latest_generated_at,
    threshold: READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
    trend_status: trendStatus,
    trend_reason: trendReason,
    promoted_pair_count: promotedPairs.length,
    promoted_pairs: promotedPairs,
    pair_trends: pairTrends,
  };
}

function summarizeTitleHomogenizationHistory(historyPayload, trendPayload) {
  const normalizedHistory = normalizeHistoryPayload(historyPayload);
  const trend = trendPayload || buildTitleHomogenizationTrend(normalizedHistory);
  return {
    available: normalizedHistory.entry_count > 0,
    entry_count: normalizedHistory.entry_count,
    latest_generated_at: normalizedHistory.latest_generated_at,
    threshold: READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
    trend_status: trend.trend_status,
    trend_reason: trend.trend_reason,
    promoted_pair_count: trend.promoted_pair_count || 0,
  };
}

function crossPackDistinctnessComparisons(worldSummaries) {
  const jadeSummaries = (worldSummaries || []).filter((item) => String(item.world_id || "").startsWith("jade_court_"));
  const nonJadeSummaries = (worldSummaries || []).filter((item) => !String(item.world_id || "").startsWith("jade_court_"));
  const comparisons = [];
  for (const nonJade of nonJadeSummaries) {
    for (const jade of jadeSummaries) {
      const titleSimilarity = jaccardSimilarity(
        bigramSet((nonJade.sampled_titles || []).join(" ")),
        bigramSet((jade.sampled_titles || []).join(" "))
      );
      const quoteSimilarity = jaccardSimilarity(
        bigramSet((nonJade.sampled_quotes || []).join(" ")),
        bigramSet((jade.sampled_quotes || []).join(" "))
      );
      comparisons.push({
        non_jade_world_id: nonJade.world_id,
        jade_world_id: jade.world_id,
        title_similarity: Number(titleSimilarity.toFixed(3)),
        quote_similarity: Number(quoteSimilarity.toFixed(3)),
        passes_min_difference: !(titleSimilarity >= 0.75 && quoteSimilarity >= 0.35),
      });
    }
  }
  return comparisons;
}

function titleHomogenizationWarnings(distinctnessComparisons) {
  return (distinctnessComparisons || [])
    .filter((item) => item.title_similarity >= 0.95 && item.quote_similarity < 0.35)
    .map((item) => ({
      non_jade_world_id: item.non_jade_world_id,
      jade_world_id: item.jade_world_id,
      title_similarity: item.title_similarity,
      quote_similarity: item.quote_similarity,
      warning_kind: "title_homogenization_non_blocking",
      message: "sampled titles are highly similar across packs, but quote-token overlap remains below the blocking threshold.",
    }));
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

async function clickTrajectoryCard(evaluate, visibleIndex) {
  return evaluate(`(() => {
    const cards = Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card'));
    const card = cards[${Number(visibleIndex)}];
    if (!card) throw new Error('Missing trajectory card at visible index ${Number(visibleIndex)}');
    card.click();
    return {
      title: card.querySelector('strong')?.innerText || '',
      action: card.dataset.readerV2Action || '',
    };
  })()`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url;
  const chromePort = Number(args["chrome-port"] || 9225);
  const seedFile = args["seed-file"];
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  const failureScreenshotFile = args["failure-screenshot-file"];
  const storybookScreenshotFile = args["storybook-screenshot-file"];
  const historyFile = args["history-file"];
  if (!url || !seedFile || !resultFile || !failureArtifactFile || !failureScreenshotFile || !storybookScreenshotFile || !historyFile) {
    throw new Error(
      "Usage: node verify_reader_storybook_long_route_smoke.js --url <app-url> --seed-file <json> --result-file <json> --failure-artifact-file <json> --failure-screenshot-file <png> --storybook-screenshot-file <png> --history-file <json> [--chrome-port <port>]"
    );
  }

  const writeResult = (payload) => {
    fs.mkdirSync(path.dirname(resultFile), { recursive: true });
    fs.writeFileSync(resultFile, JSON.stringify(payload, null, 2));
  };
  const writeFailureArtifact = (payload) => {
    fs.mkdirSync(path.dirname(failureArtifactFile), { recursive: true });
    fs.writeFileSync(failureArtifactFile, JSON.stringify(payload, null, 2));
  };
  const writePng = (targetPath, base64Png) => {
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, Buffer.from(base64Png, "base64"));
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
  const { ws, send, evaluate, consoleErrors } = await connectToPage(url, chromePort);

  const captureFailureSnapshot = async () => {
    try {
      return await evaluate(`({
        title: document.title || '',
        url: location.href || '',
        session_id: String(readerState?.sessionId || ''),
        active_view: readerState?.activeView || '',
        selected_replay_index: Number(readerState?.selectedReplayIndex ?? -1),
        storybook_title: document.querySelector('#reader-v2-storybook-title')?.innerText || '',
        storybook_quote: document.querySelector('#reader-v2-storybook-quote')?.innerText || '',
        storybook_beats: Array.from(document.querySelectorAll('#reader-v2-storybook-beats .reader-shell-v2__beat-copy')).map((node) => node.innerText.trim()),
        trajectory_titles: Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card strong')).map((node) => node.innerText.trim()),
        body_text_excerpt: (document.body?.innerText || '').slice(0, 4000),
        body_html_excerpt: (document.body?.innerHTML || '').slice(0, 12000)
      })`);
    } catch (error) {
      return { snapshot_error: error && error.message ? error.message : String(error) };
    }
  };

  const captureScreenshot = async (targetPath) => {
    const result = await send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
    });
    writePng(targetPath, result.data);
    return targetPath;
  };

  async function captureWorldStorybook(worldSummary) {
    markStep(`restore_seeded_session:${worldSummary.world_id}`);
    await evaluate(`(async () => {
      await ReaderRuntime.restoreSession(${JSON.stringify(worldSummary.session_id)});
      return true;
    })()`);
    await waitFor(
      evaluate,
      `reader restored seeded session ${worldSummary.world_id}`,
      `String(readerState.sessionId || '') === ${JSON.stringify(worldSummary.session_id)}
        && new URL(location.href).searchParams.get('workspace') === 'read'
        && document.querySelector('#reader-v2-read-hero')`,
      30000
    );
    completeStep(`restore_seeded_session:${worldSummary.world_id}`);

    markStep(`open_storybook:${worldSummary.world_id}`);
    await clickButtonByText(evaluate, "#product-subnav-actions button", "图文阅读");
    await waitFor(
      evaluate,
      `reader storybook long route view ${worldSummary.world_id}`,
      `readerState.activeView === 'storybook'
        && new URL(location.href).searchParams.get('view') === 'storybook'
        && document.querySelector('#reader-v2-storybook')
        && (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length > 400`,
      30000
    );
    completeStep(`open_storybook:${worldSummary.world_id}`);

    markStep(`verify_trajectory_window:${worldSummary.world_id}`);
    const trajectorySnapshot = await evaluate(`(() => {
      const cards = Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card'));
      return {
        count: cards.length,
        active_count: cards.filter((card) => card.classList.contains('is-active')).length,
        titles: cards.map((card) => card.querySelector('strong')?.innerText || ''),
        actions: cards.map((card) => card.dataset.readerV2Action || ''),
      };
    })()`);
    const expectedVisibleCount = Math.min(Number(worldSummary.reached_chapters || 0), 6);
    if (Number(trajectorySnapshot.count || 0) < Math.max(3, expectedVisibleCount)) {
      throw new Error(
        `reader_storybook_trajectory_too_short: world=${worldSummary.world_id} count=${trajectorySnapshot.count} expected=${Math.max(3, expectedVisibleCount)}`
      );
    }
    if (Number(trajectorySnapshot.active_count || 0) !== 1) {
      throw new Error(`reader_storybook_active_trajectory_count_invalid: world=${worldSummary.world_id} count=${trajectorySnapshot.active_count}`);
    }
    completeStep(`verify_trajectory_window:${worldSummary.world_id}`);

    markStep(`sample_storybook_chapters:${worldSummary.world_id}`);
    const samplePlan = await evaluate(`(() => {
      const cards = Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card'));
      const indexes = Array.from(new Set([0, Math.max(0, Math.floor((cards.length - 1) / 2)), Math.max(0, cards.length - 1)]));
      return indexes.map((visibleIndex) => ({
        visible_index: visibleIndex,
        title: cards[visibleIndex]?.querySelector('strong')?.innerText || '',
        action: cards[visibleIndex]?.dataset.readerV2Action || '',
      }));
    })()`);

    const sampledChapters = [];
    for (const sample of samplePlan) {
      const clicked = await clickTrajectoryCard(evaluate, sample.visible_index);
      await waitFor(
        evaluate,
        `storybook sample ${worldSummary.world_id}:${sample.visible_index}`,
        `(() => {
          const cards = Array.from(document.querySelectorAll('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card'));
          const card = cards[${Number(sample.visible_index)}];
          return Boolean(card && card.classList.contains('is-active') && (document.querySelector('#reader-v2-storybook-title')?.innerText || '').trim().length > 0);
        })()`,
        30000
      );
      const chapterSnapshot = await evaluate(`(() => {
        const nonEmptyBeats = Array.from(document.querySelectorAll('#reader-v2-storybook-beats .reader-shell-v2__beat-item:not(.reader-shell-v2__beat-item--empty)'));
        const activeCard = document.querySelector('#reader-v2-storybook-sequence .reader-shell-v2__trajectory-card.is-active');
        const quote = (document.querySelector('#reader-v2-storybook-quote')?.innerText || '').trim();
        const beatTexts = nonEmptyBeats.map((item) => item.querySelector('.reader-shell-v2__beat-copy')?.innerText.trim() || '').filter(Boolean);
        return {
          chapter_title: (document.querySelector('#reader-v2-storybook-title')?.innerText || '').trim(),
          quote,
          quote_length: quote.length,
          quote_placeholder: quote.includes('这里会显示') || quote.includes('章节引句'),
          beat_count: beatTexts.length,
          prose_length: (document.querySelector('#reader-v2-storybook-prose')?.innerText || '').trim().length,
          active_trajectory_title: activeCard?.querySelector('strong')?.innerText || '',
          selected_replay_index: Number(readerState.selectedReplayIndex ?? -1),
        };
      })()`);
      if (chapterSnapshot.quote_length < 8 || chapterSnapshot.quote_placeholder) {
        throw new Error(
          `reader_storybook_quote_unstable: world=${worldSummary.world_id} visible_index=${sample.visible_index} quote_length=${chapterSnapshot.quote_length}`
        );
      }
      if (chapterSnapshot.beat_count < 1) {
        throw new Error(`reader_storybook_beats_missing: world=${worldSummary.world_id} visible_index=${sample.visible_index}`);
      }
      if (chapterSnapshot.prose_length < 400) {
        throw new Error(`reader_storybook_prose_too_short: world=${worldSummary.world_id} visible_index=${sample.visible_index}`);
      }
      sampledChapters.push({
        visible_index: sample.visible_index,
        requested_title: sample.title,
        clicked_action: clicked.action,
        chapter_title: chapterSnapshot.chapter_title,
        quote_text: chapterSnapshot.quote,
        quote_length: chapterSnapshot.quote_length,
        beat_count: chapterSnapshot.beat_count,
        prose_length: chapterSnapshot.prose_length,
        active_trajectory_title: chapterSnapshot.active_trajectory_title,
        selected_replay_index: chapterSnapshot.selected_replay_index,
      });
    }
    completeStep(`sample_storybook_chapters:${worldSummary.world_id}`);

    markStep(`return_to_landing:${worldSummary.world_id}`);
    await clickButtonByText(evaluate, "#reader-v2-read-hero button", "返回书架");
    await waitFor(
      evaluate,
      `reader returns to landing ${worldSummary.world_id}`,
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'landing'`,
      30000
    );
    completeStep(`return_to_landing:${worldSummary.world_id}`);

    return {
      world_id: worldSummary.world_id,
      session_id: worldSummary.session_id,
      visible_trajectory_count: trajectorySnapshot.count,
      sampled_chapter_count: sampledChapters.length,
      sampled_quotes: sampledChapters.map((item) => item.quote_text),
      sampled_quote_lengths: sampledChapters.map((item) => item.quote_length),
      sampled_beat_counts: sampledChapters.map((item) => item.beat_count),
      sampled_titles: sampledChapters.map((item) => item.chapter_title),
      latest_title: sampledChapters[sampledChapters.length - 1]?.chapter_title || "",
    };
  }

  try {
    markStep("load_page_title");
    await waitFor(evaluate, "page title", `document.title === 'NarrativeOS Studio'`);
    completeStep("load_page_title");

    markStep("wait_for_bootstrap");
    await waitFor(
      evaluate,
      "reader app bootstrap",
      `typeof ReaderRuntime === 'object'
        && typeof ShellRuntime === 'object'
        && document.querySelector('#reader-shell-v2')
        && document.querySelector('#app-shell')?.dataset.product === 'reader'`,
      30000
    );
    completeStep("wait_for_bootstrap");

    markStep("login_reader_identity");
    await waitFor(
      evaluate,
      "shell auth stage",
      `document.querySelector('#shell-auth-actor-id')
        && document.querySelector('#shell-auth-login')
        && document.querySelector('#app-shell')?.dataset.authenticated === 'off'`,
      30000
    );
    await setValue(evaluate, "#shell-auth-actor-id", seed.auth_actor_id || seed.account_id);
    await setValue(evaluate, "#shell-auth-password", seed.auth_password);
    await clickButtonByText(evaluate, "#shell-auth-stage button", "登录");
    await waitFor(
      evaluate,
      "reader authenticated shell",
      `document.querySelector('#app-shell')?.dataset.authenticated === 'on'
        && document.querySelector('#reader-shell-v2')
        && document.querySelector('#shell-auth-stage')?.offsetParent === null`,
      30000
    );
    completeStep("login_reader_identity");

    markStep("verify_seeded_session_on_landing");
    await waitFor(
      evaluate,
      "reader seeded session visible",
      `document.querySelector('#app-shell')?.dataset.product === 'reader'
        && new URL(location.href).searchParams.get('workspace') === 'landing'
        && document.querySelector('#reader-shell-v2')`,
      30000
    );
    completeStep("verify_seeded_session_on_landing");

    const worldSummaries = [];
    for (const worldSummary of seed.world_summaries || []) {
      worldSummaries.push(await captureWorldStorybook(worldSummary));
    }
    const distinctnessComparisons = crossPackDistinctnessComparisons(worldSummaries);
    const titleWarnings = titleHomogenizationWarnings(distinctnessComparisons);
    const generatedAt = new Date().toISOString();
    const historyPayload = appendHistoryEntry(readJsonFile(historyFile), {
      generated_at: generatedAt,
      world_ids: seed.world_ids || [],
      cross_pack_distinctness: distinctnessComparisons,
      title_homogenization_warnings: titleWarnings,
    });
    writeJsonFile(historyFile, historyPayload);
    const titleHomogenizationTrend = buildTitleHomogenizationTrend(historyPayload);
    const titleHomogenizationHistorySummary = summarizeTitleHomogenizationHistory(
      historyPayload,
      titleHomogenizationTrend
    );
    const promotedPairs = titleHomogenizationTrend.promoted_pairs || [];
    const failedDistinctness = distinctnessComparisons.filter((item) => !item.passes_min_difference);
    if (failedDistinctness.length) {
      throw new Error(
        `reader_storybook_cross_pack_distinctness_failed: ${JSON.stringify(failedDistinctness)}`
      );
    }

    markStep("capture_storybook_screenshot");
    const screenshotPath = await captureScreenshot(storybookScreenshotFile);
    completeStep("capture_storybook_screenshot");

    if (consoleErrors.length) {
      throw new Error(`Reader storybook long-route smoke emitted ${consoleErrors.length} console error(s)`);
    }

    const summaryPayload = {
      suite_scope: "reader_storybook_long_route_smoke",
      reader_seed_world_ids: seed.world_ids,
      reader_seed_target_chapters: seed.target_chapters,
      reader_seed_min_target_chapters: seed.min_target_chapters,
      reader_seed_reached_chapters: (seed.world_summaries || []).map((item) => item.reached_chapters),
      reader_seed_quality_guard_retry_count: (seed.world_summaries || []).map((item) => item.quality_guard_retry_count),
      reader_seed_quote_coverage_rate: (seed.world_summaries || []).map((item) => item.quote_coverage_rate),
      reader_seed_beats_coverage_rate: (seed.world_summaries || []).map((item) => item.beats_coverage_rate),
      reader_storybook_world_summaries: worldSummaries,
      reader_storybook_cross_pack_distinctness: distinctnessComparisons,
      reader_storybook_title_homogenization_warnings: titleWarnings,
      reader_storybook_title_homogenization_warning_count: titleWarnings.length,
      reader_storybook_title_homogenization_history_summary: titleHomogenizationHistorySummary,
      reader_storybook_title_homogenization_trend: titleHomogenizationTrend,
      reader_storybook_title_homogenization_promoted_pairs: promotedPairs,
      reader_storybook_visible_trajectory_count: worldSummaries.map((item) => item.visible_trajectory_count),
      reader_storybook_sampled_chapter_count: worldSummaries.map((item) => item.sampled_chapter_count),
      reader_storybook_sampled_quote_lengths: worldSummaries.map((item) => item.sampled_quote_lengths),
      reader_storybook_sampled_beat_counts: worldSummaries.map((item) => item.sampled_beat_counts),
      reader_storybook_sampled_titles: worldSummaries.map((item) => item.sampled_titles),
      reader_storybook_latest_title: worldSummaries.map((item) => item.latest_title),
      reader_storybook_screenshot_file: screenshotPath,
    };
    const resultPayload = {
      status: "ok",
      schema_version: "frontend_qa_result/v1",
      guard: {
        id: "reader_storybook_long_route_smoke",
        label: "Reader Storybook Long-Route Smoke",
      },
      summary_meta: {
        primary_key: "completed_steps",
        primary_count: stepOrder.length,
        summary_key_count: Object.keys(summaryPayload).length,
      },
      artifacts: {
        result_file: resultFile,
        failure_artifact_file: null,
        failure_screenshot_file: null,
        storybook_screenshot_file: screenshotPath,
        seed_file: seedFile,
        history_file: historyFile,
      },
      app_url: url,
      completed_steps: stepOrder,
      failed_step: null,
      console_errors: consoleErrors,
      summary: summaryPayload,
      failure_artifact_file: null,
      failure_screenshot_file: null,
    };
    writeResult(resultPayload);
    console.log(JSON.stringify(resultPayload, null, 2));
  } catch (error) {
    const failureSnapshot = await captureFailureSnapshot();
    const failureScreenshotPath = await captureScreenshot(failureScreenshotFile).catch((captureError) => {
      return captureError && captureError.message ? captureError.message : String(captureError);
    });
    const failureArtifact = {
      status: "error",
      app_url: url,
      seed,
      completed_steps: stepOrder,
      failed_step: currentStep,
      error_message: error && error.message ? error.message : String(error),
      snapshot: failureSnapshot,
      failure_screenshot_file:
        typeof failureScreenshotPath === "string" && failureScreenshotPath.endsWith(".png")
          ? failureScreenshotPath
          : null,
      failure_screenshot_error:
        typeof failureScreenshotPath === "string" && !failureScreenshotPath.endsWith(".png")
          ? failureScreenshotPath
          : null,
    };
    writeFailureArtifact(failureArtifact);
    const resultPayload = {
      status: "error",
      schema_version: "frontend_qa_result/v1",
      guard: {
        id: "reader_storybook_long_route_smoke",
        label: "Reader Storybook Long-Route Smoke",
      },
      app_url: url,
      completed_steps: stepOrder,
      failed_step: currentStep,
      console_errors: consoleErrors,
      error_message: error && error.message ? error.message : String(error),
      failure_artifact_file: failureArtifactFile,
      failure_screenshot_file:
        typeof failureScreenshotPath === "string" && failureScreenshotPath.endsWith(".png")
          ? failureScreenshotPath
          : null,
    };
    writeResult(resultPayload);
    throw error;
  } finally {
    ws.close();
  }
}

main().catch((error) => {
  console.error("READER_STORYBOOK_LONG_ROUTE_SMOKE_ERROR");
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
