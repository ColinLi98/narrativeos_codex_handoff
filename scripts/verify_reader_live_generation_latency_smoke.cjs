#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const DEFAULT_TOTAL_TIMEOUT_MS = Number(process.env.READER_LIVE_GENERATION_TOTAL_TIMEOUT_MS || 420000);
const DEFAULT_RESUME_TIMEOUT_MS = Number(process.env.READER_LIVE_GENERATION_RESUME_TIMEOUT_MS || 360000);
const DEFAULT_LATENCY_BUDGET_MS = Number(process.env.READER_LIVE_GENERATION_BUDGET_MS || 300000);

let globalRequestHeaders = {};

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`);
}

function safeUrl(value) {
  try {
    const parsed = new URL(String(value));
    const segments = parsed.pathname.split("/");
    const safeSegments = segments.map((segment, index) => {
      const previous = segments[index - 1] || "";
      if (previous === "session") return ":session";
      if (previous === "jobs") return ":job";
      return segment;
    });
    const params = new URLSearchParams(parsed.search);
    for (const key of Array.from(params.keys())) {
      if (/node|session|job|account|token/i.test(key)) {
        params.set(key, `:${key}`);
      }
    }
    const query = params.toString();
    return `${safeSegments.join("/")}${query ? `?${query}` : ""}`;
  } catch (_) {
    return sanitizeText(value);
  }
}

function sanitizeText(value) {
  return String(value || "")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "reader_account_redacted")
    .replace(/\/session\/[^/?\s"]+/g, "/session/:session")
    .replace(/\/jobs\/[^/?\s"]+/g, "/jobs/:job")
    .replace(/nodeId=[^&\s"]+/g, "nodeId=:node")
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi, "id_redacted");
}

function sanitizeForArtifact(value, keyHint = "") {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") {
    if (/url/i.test(keyHint)) return safeUrl(value);
    if (/session/i.test(keyHint)) return redactedRef(value, "reader_session");
    if (/job/i.test(keyHint)) return redactedRef(value, "reader_job");
    if (/account|email|user/i.test(keyHint)) return redactedRef(value, "reader_account");
    if (/token|secret|cookie|authorization|password/i.test(keyHint)) return "[redacted]";
    return sanitizeText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForArtifact(item, keyHint));
  }
  if (typeof value === "object") {
    const clean = {};
    for (const [key, item] of Object.entries(value)) {
      clean[key] = sanitizeForArtifact(item, key);
    }
    return clean;
  }
  return value;
}

function assert(condition, message, detail) {
  if (!condition) {
    const safeDetail = sanitizeForArtifact(detail);
    const error = new Error(`${message}${detail === undefined ? "" : ` :: ${JSON.stringify(safeDetail)}`}`);
    error.detail = safeDetail;
    throw error;
  }
}

function data(payload) {
  if (payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "data")) {
    return payload.data;
  }
  return payload;
}

function redactedRef(value, prefix) {
  const raw = String(value || "");
  if (!raw) return `${prefix}_missing`;
  let hash = 0;
  for (const ch of raw) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return `${prefix}_${hash.toString(16).padStart(8, "0")}`;
}

async function requestJson(url, options = {}) {
  const method = options.method || "GET";
  const timeoutMs = Number(options.timeoutMs || 45000);
  const expectedStatuses = options.expectedStatuses || [200];
  const apiErrors = options.apiErrors || [];
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method,
      headers: {
        ...(globalRequestHeaders || {}),
        ...(options.headers || {}),
      },
      body: options.body,
      signal: controller.signal,
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch (_) {
      payload = { raw: text.slice(0, 2000) };
    }
    const elapsedMs = Date.now() - started;
    if (!expectedStatuses.includes(response.status)) {
      const errorPayload = { url: safeUrl(url), method, status: response.status, elapsed_ms: elapsedMs, payload: sanitizeForArtifact(payload) };
      apiErrors.push(errorPayload);
      throw new Error(`HTTP ${response.status} ${method} ${safeUrl(url)}: ${JSON.stringify(errorPayload.payload)}`);
    }
    return { status: response.status, payload, elapsedMs };
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutPayload = { url: safeUrl(url), method, timeout_ms: timeoutMs };
      apiErrors.push(timeoutPayload);
      throw new Error(`request_timeout:${method}:${safeUrl(url)}`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function postJson(url, payload, options = {}) {
  return requestJson(url, {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: JSON.stringify(payload),
  });
}

async function registerQuantum(apiOrigin, apiErrors) {
  const unique = `live_reader_${Date.now()}`;
  const email = `${unique}@example.com`;
  const response = await postJson(
    new URL("/api/v1/auth/register", apiOrigin).toString(),
    {
      username: unique,
      email,
      password: "secret123",
      displayName: unique,
    },
    { apiErrors, timeoutMs: 90000 }
  );
  const auth = data(response.payload);
  assert(auth && auth.token, "Quantum registration did not return a token", auth);
  return { email, username: unique, token: auth.token };
}

function collectVisibleText(value, acc = []) {
  if (typeof value === "string") {
    if (value.trim()) acc.push(value);
    return acc;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectVisibleText(item, acc);
    return acc;
  }
  if (value && typeof value === "object") {
    for (const item of Object.values(value)) collectVisibleText(item, acc);
  }
  return acc;
}

function countOccurrences(text, phrase) {
  if (!phrase) return 0;
  let count = 0;
  let cursor = 0;
  while (cursor <= text.length) {
    const found = text.indexOf(phrase, cursor);
    if (found < 0) break;
    count += 1;
    cursor = found + phrase.length;
  }
  return count;
}

function auditReaderProjection({ publicAppUrl, apiOrigin, sessionId, nodes, choices }) {
  const sampledNodes = Array.isArray(nodes) ? nodes.slice(0, 3) : [];
  const visibleTexts = [];
  for (const node of sampledNodes) {
    collectVisibleText(node.content, visibleTexts);
    collectVisibleText(node.quote, visibleTexts);
    collectVisibleText(node.beats, visibleTexts);
    collectVisibleText(node.sceneCard, visibleTexts);
  }
  for (const choice of Array.isArray(choices) ? choices : []) {
    collectVisibleText(choice.text, visibleTexts);
    collectVisibleText(choice.description, visibleTexts);
    collectVisibleText(choice.preview, visibleTexts);
  }
  const allVisibleText = visibleTexts.join("\n");
  const phraseBudgets = {
    "眼前这一处": 1,
    "这一处": 2,
    "真话窗口": 2,
    "把每一步都接住": 1,
    "真正要转向的那句终于逼到眼前": 1,
    "被压回去的": 1,
    "顺着此刻": 1,
  };
  const violations = [];
  const repeatedPhrases = {};
  for (const [phrase, maxCount] of Object.entries(phraseBudgets)) {
    const count = countOccurrences(allVisibleText, phrase);
    if (count > 0) repeatedPhrases[phrase] = count;
    if (count > maxCount) {
      violations.push({ issue_code: "Q03", kind: "stock_refrain_budget", detail: { phrase, count, max_count: maxCount } });
    }
  }
  return {
    schema_version: "reader_live_generation_projection_sample/v1",
    ready: sampledNodes.length > 0 && violations.length === 0,
    status: sampledNodes.length > 0 && violations.length === 0 ? "passed" : "blocked",
    public_app_url: publicAppUrl,
    api_origin: apiOrigin,
    session_ref: redactedRef(sessionId, "reader_session"),
    sample_node_count: sampledNodes.length,
    sample_choice_count: Array.isArray(choices) ? choices.length : 0,
    scanned_text_chars: allVisibleText.length,
    repeated_phrases: repeatedPhrases,
    violation_count: violations.length,
    violations,
  };
}

async function waitReaderGenerationJob(apiOrigin, job, { headers, apiErrors, totalTimeoutMs, resumeTimeoutMs }) {
  let current = job;
  const started = Date.now();
  const attempts = [];
  for (let attempt = 0; Date.now() - started < totalTimeoutMs; attempt += 1) {
    attempts.push({
      attempt,
      status: current && current.status,
      reader_status: current && current.readerStatus,
      attempt_count: current && current.attemptCount,
    });
    if (current.status === "succeeded") {
      return { job: current, totalMs: Date.now() - started, attempts };
    }
    if (current.status === "failed") {
      throw new Error(`Reader live-generation job failed: ${JSON.stringify(sanitizeForArtifact(current))}`);
    }
    if (current.status === "queued" || current.retryable === true || current.leaseStatus === "expired") {
      const resumed = await postJson(new URL(`/v1/reader/jobs/${current.jobId}/resume`, apiOrigin).toString(), {}, {
        headers,
        apiErrors,
        timeoutMs: resumeTimeoutMs,
      });
      current = resumed.payload && resumed.payload.job ? resumed.payload.job : resumed.payload;
      continue;
    }
    await new Promise((resolve) => setTimeout(resolve, Math.max(1000, Math.min(5000, Number(current.pollAfterMs || 1000)))));
    const response = await requestJson(new URL(`/v1/reader/jobs/${current.jobId}`, apiOrigin).toString(), {
      headers,
      apiErrors,
      timeoutMs: 90000,
    });
    current = response.payload && response.payload.job ? response.payload.job : response.payload;
  }
  throw new Error(`Reader live-generation job timed out: ${JSON.stringify(sanitizeForArtifact(current))}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const publicAppUrl = args["public-app-url"] || args.url || "https://pilot.lixidol.com";
  const apiOrigin = args["api-origin"] || publicAppUrl;
  const resultFile = args["result-file"];
  const failureArtifactFile = args["failure-artifact-file"];
  assert(resultFile && failureArtifactFile, "Usage: verify_reader_live_generation_latency_smoke.cjs --public-app-url <url> --api-origin <url> --result-file <json> --failure-artifact-file <json>");

  const vercelProtectionBypass = String(process.env.VERCEL_PROTECTION_BYPASS || "").trim();
  globalRequestHeaders = vercelProtectionBypass ? { "x-vercel-protection-bypass": vercelProtectionBypass } : {};
  const apiErrors = [];
  const completedSteps = [];
  let currentStep = "bootstrap";
  const startedAt = new Date().toISOString();
  const smokeStarted = Date.now();

  const fail = (error) => {
    const failure = {
      schema_version: "reader_live_generation_latency_smoke/v1",
      status: "failed",
      ready: false,
      public_app_url: publicAppUrl,
      api_origin: apiOrigin,
      failed_step: currentStep,
      error: sanitizeText(error.message || String(error)),
      completed_steps: completedSteps,
      api_errors: sanitizeForArtifact(apiErrors),
      started_at: startedAt,
      finished_at: new Date().toISOString(),
    };
    writeJson(failureArtifactFile, failure);
    throw error;
  };

  try {
    currentStep = "health";
    const health = await requestJson(new URL("/health", apiOrigin).toString(), { apiErrors, timeoutMs: 90000 });
    assert(health.payload && health.payload.status === "ok", "Health did not return ok", health.payload);
    completedSteps.push("health");

    currentStep = "register_reader";
    const reader = await registerQuantum(apiOrigin, apiErrors);
    const readerHeaders = { Authorization: `Bearer ${reader.token}` };
    completedSteps.push("register_reader");

    currentStep = "public_catalog";
    const worksResponse = await requestJson(new URL("/api/v1/story/import/public-works", apiOrigin).toString(), {
      headers: readerHeaders,
      apiErrors,
      timeoutMs: 90000,
    });
    const works = data(worksResponse.payload);
    assert(Array.isArray(works) && works.length > 0, "Public catalog returned no works", worksResponse.payload);
    const selectedWork = works.find((work) => work.worldId === "jade_court_exam") || works[0];
    completedSteps.push("public_catalog");

    currentStep = "start_deferred_session";
    const launchResponse = await postJson(
      new URL("/api/v1/story/import/start", apiOrigin).toString(),
      { targetType: "world", targetId: selectedWork.worldId || selectedWork.id, deferBootstrap: true },
      { headers: readerHeaders, apiErrors, timeoutMs: 90000 }
    );
    const launch = data(launchResponse.payload);
    assert(launch && launch.sessionId, "Deferred story import did not return session", launchResponse.payload);
    assert(!launch.generationJob, "Live latency smoke must not run import bootstrap generation", launch);
    completedSteps.push("start_deferred_session");

    currentStep = "enqueue_live_reader_continue";
    const enqueueStarted = Date.now();
    const continued = await postJson(
      new URL("/v1/reader/continue", apiOrigin).toString(),
      {
        session_id: launch.sessionId,
        account_id: reader.email,
        freeform_intent: "继续推进这一章。",
      },
      { headers: readerHeaders, apiErrors, expectedStatuses: [200, 402], timeoutMs: 120000 }
    );
    const continueEnqueueMs = continued.elapsedMs;
    assert(continued.status === 200, "Reader continue did not enqueue live generation", continued.payload);
    const continuedPayload = data(continued.payload);
    assert(continuedPayload && continuedPayload.job, "Reader continue did not return a generation job", continued.payload);
    completedSteps.push("enqueue_live_reader_continue");

    currentStep = "resume_live_reader_generation";
    const waited = await waitReaderGenerationJob(apiOrigin, continuedPayload.job, {
      headers: readerHeaders,
      apiErrors,
      totalTimeoutMs: DEFAULT_TOTAL_TIMEOUT_MS,
      resumeTimeoutMs: DEFAULT_RESUME_TIMEOUT_MS,
    });
    const generationTotalMs = Date.now() - enqueueStarted;
    const readerStatus = waited.job.readerStatus || (waited.job.result && waited.job.result.reader_status);
    assert(readerStatus === "ok", "Reader live-generation did not finish with ok reader status", waited.job);
    completedSteps.push("resume_live_reader_generation");

    currentStep = "reader_projection";
    const nodesResponse = await requestJson(
      new URL(`/api/v1/story/session/${encodeURIComponent(launch.sessionId)}/nodes?limit=3`, apiOrigin).toString(),
      { headers: readerHeaders, apiErrors, timeoutMs: 90000 }
    );
    const nodes = data(nodesResponse.payload);
    assert(Array.isArray(nodes) && nodes.length > 0, "Reader nodes projection did not return generated chapter", nodesResponse.payload);
    const currentNode = nodes[nodes.length - 1];
    const choicesResponse = await requestJson(
      new URL(`/api/v1/story/session/${encodeURIComponent(launch.sessionId)}/choices?nodeId=${encodeURIComponent(currentNode.id)}`, apiOrigin).toString(),
      { headers: readerHeaders, apiErrors, timeoutMs: 90000 }
    );
    const choices = data(choicesResponse.payload);
    const projectionSample = auditReaderProjection({
      publicAppUrl,
      apiOrigin,
      sessionId: launch.sessionId,
      nodes,
      choices: Array.isArray(choices) ? choices : [],
    });
    assert(projectionSample.ready === true, "Reader live-generation projection sample failed", projectionSample);
    completedSteps.push("reader_projection");

    currentStep = "latency_budget";
    const withinBudget = generationTotalMs <= DEFAULT_LATENCY_BUDGET_MS;
    const result = {
      schema_version: "reader_live_generation_latency_smoke/v1",
      status: withinBudget ? "passed" : "blocked",
      ready: withinBudget,
      public_app_url: publicAppUrl,
      api_origin: apiOrigin,
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      completed_steps: completedSteps,
      refs: {
        reader_account: redactedRef(reader.email, "reader_account"),
        reader_session: redactedRef(launch.sessionId, "reader_session"),
        reader_job: redactedRef(continuedPayload.job.jobId, "reader_job"),
      },
      latency: {
        health_ms: health.elapsedMs,
        continue_enqueue_ms: continueEnqueueMs,
        generation_total_ms: generationTotalMs,
        job_wait_ms: waited.totalMs,
        latency_budget_ms: DEFAULT_LATENCY_BUDGET_MS,
        within_budget: withinBudget,
      },
      job: {
        operation: waited.job.operation,
        status: waited.job.status,
        reader_status: readerStatus,
        attempt_count: waited.job.attemptCount,
        created_at: waited.job.createdAt,
        started_at: waited.job.startedAt,
        finished_at: waited.job.finishedAt,
      },
      projection_sample: projectionSample,
      api_error_count: apiErrors.length,
      api_errors: sanitizeForArtifact(apiErrors),
      total_smoke_ms: Date.now() - smokeStarted,
    };
    writeJson(resultFile, result);
    assert(withinBudget, "Reader live-generation exceeded latency budget", result.latency);
  } catch (error) {
    fail(error);
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
