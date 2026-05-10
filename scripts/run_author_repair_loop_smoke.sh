#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
SMOKE_DB="${ROOT_DIR}/artifacts/author_repair_loop_smoke.db"
RESULT_FILE="${ROOT_DIR}/artifacts/author_repair_loop_smoke_result.json"
FAILURE_ARTIFACT_FILE="${ROOT_DIR}/artifacts/author_repair_loop_smoke_failure_snapshot.json"
FAILURE_SCREENSHOT_FILE="${ROOT_DIR}/artifacts/author_repair_loop_smoke_failure.png"
APP_PORT="${APP_PORT:-8019}"
APP_URL="${APP_URL:-http://127.0.0.1:${APP_PORT}/app?product=author&debug=1}"
CHROME_PORT="${CHROME_PORT:-9239}"
CHROME_USER_DIR="${CHROME_USER_DIR:-/tmp/narrativeos-chrome-author-repair-loop}"
CHROME_APP="${CHROME_APP:-/Applications/Google Chrome.app}"
CHROME_BIN="${CHROME_BIN:-}"
CHROME_EXTRA_ARGS="${CHROME_EXTRA_ARGS:-}"
CI_HEADLESS="${CI_HEADLESS:-${CI:-}}"
SERVER_LOG="${SERVER_LOG:-/tmp/author_repair_loop_smoke_server.log}"
CHROME_LOG="${CHROME_LOG:-/tmp/author_repair_loop_smoke_chrome.log}"
SERVER_PID=""
CHROME_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${CHROME_PID}" ]] && kill -0 "${CHROME_PID}" >/dev/null 2>&1; then
    kill "${CHROME_PID}" >/dev/null 2>&1 || true
    wait "${CHROME_PID}" 2>/dev/null || true
  fi
  pkill -f "remote-debugging-port=${CHROME_PORT}.*${CHROME_USER_DIR}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

find_chrome_bin() {
  if [[ -n "${CHROME_BIN}" ]] && [[ -x "${CHROME_BIN}" ]]; then
    printf '%s\n' "${CHROME_BIN}"
    return 0
  fi
  if [[ -d "${CHROME_APP}" ]] && [[ -x "${CHROME_APP}/Contents/MacOS/Google Chrome" ]]; then
    printf '%s\n' "${CHROME_APP}/Contents/MacOS/Google Chrome"
    return 0
  fi
  for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      command -v "${candidate}"
      return 0
    fi
  done
  return 1
}

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Missing virtualenv python: ${VENV_PYTHON}" >&2
  exit 1
fi

if ! CHROME_BIN_RESOLVED="$(find_chrome_bin)"; then
  echo "Unable to locate a Chrome/Chromium binary. Set CHROME_BIN or install Google Chrome." >&2
  exit 1
fi

mkdir -p "${ROOT_DIR}/artifacts"
rm -f "${SMOKE_DB}" "${RESULT_FILE}" "${FAILURE_ARTIFACT_FILE}" "${FAILURE_SCREENSHOT_FILE}"
rm -rf "${CHROME_USER_DIR}"
rm -f "${SERVER_LOG}" "${CHROME_LOG}"

DATABASE_URL="sqlite:///${SMOKE_DB}"

echo "Starting NarrativeOS API on port ${APP_PORT}..."
(
  cd "${ROOT_DIR}"
  export DATABASE_URL
  exec "${VENV_PYTHON}" -m uvicorn src.narrativeos.api:app --host 127.0.0.1 --port "${APP_PORT}"
) >"${SERVER_LOG}" 2>&1 &
SERVER_PID="$!"

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
  echo "API failed to start. Server log:" >&2
  cat "${SERVER_LOG}" >&2
  exit 1
fi

echo "Launching Chrome with remote debugging on port ${CHROME_PORT}..."
if [[ -n "${CI_HEADLESS}" && "${CI_HEADLESS}" != "0" && "${CI_HEADLESS}" != "false" ]]; then
  "${CHROME_BIN_RESOLVED}" \
    --headless=new \
    --disable-gpu \
    --no-sandbox \
    --no-first-run \
    --no-default-browser-check \
    --remote-debugging-port="${CHROME_PORT}" \
    --user-data-dir="${CHROME_USER_DIR}" \
    ${CHROME_EXTRA_ARGS} \
    about:blank >"${CHROME_LOG}" 2>&1 &
  CHROME_PID="$!"
else
  if [[ "${CHROME_BIN_RESOLVED}" == *"/Contents/MacOS/Google Chrome" ]]; then
    open -na "${CHROME_APP}" --args \
      --remote-debugging-port="${CHROME_PORT}" \
      --user-data-dir="${CHROME_USER_DIR}" \
      ${CHROME_EXTRA_ARGS} \
      about:blank
  else
    "${CHROME_BIN_RESOLVED}" \
      --remote-debugging-port="${CHROME_PORT}" \
      --user-data-dir="${CHROME_USER_DIR}" \
      ${CHROME_EXTRA_ARGS} \
      about:blank >"${CHROME_LOG}" 2>&1 &
    CHROME_PID="$!"
  fi
fi

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${CHROME_PORT}/json/version" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf "http://127.0.0.1:${CHROME_PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome remote debugging did not start." >&2
  [[ -f "${CHROME_LOG}" ]] && cat "${CHROME_LOG}" >&2
  exit 1
fi

echo "Running Author repair loop smoke verification..."
node "${ROOT_DIR}/scripts/verify_author_repair_loop_smoke.js" \
  --url "${APP_URL}" \
  --database-url "${DATABASE_URL}" \
  --result-file "${RESULT_FILE}" \
  --failure-artifact-file "${FAILURE_ARTIFACT_FILE}" \
  --failure-screenshot-file "${FAILURE_SCREENSHOT_FILE}" \
  --chrome-port "${CHROME_PORT}"

echo "Author repair loop smoke passed."
