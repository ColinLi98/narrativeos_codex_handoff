#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${NARRATIVEOS_PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv311/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv311/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:${FRONTEND_PORT}}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
CHROME_PORT="${CHROME_PORT:-9225}"
CHROME_USER_DIR="${CHROME_USER_DIR:-/tmp/narrativeos-chrome-reader-storybook-500}"
CHROME_APP="${CHROME_APP:-/Applications/Google Chrome.app}"
CHROME_BIN="${CHROME_BIN:-}"
CHROME_EXTRA_ARGS="${CHROME_EXTRA_ARGS:-}"
CI_HEADLESS="${CI_HEADLESS:-${CI:-}}"
REUSE_BACKEND="${REUSE_BACKEND:-0}"
REUSE_SEEDED_DB="${REUSE_SEEDED_DB:-1}"
TARGET_CHAPTERS="${TARGET_CHAPTERS:-500}"
MIN_TARGET_CHAPTERS="${MIN_TARGET_CHAPTERS:-500}"
MAX_ATTEMPTS_PER_CHAPTER="${MAX_ATTEMPTS_PER_CHAPTER:-4}"

ARTIFACT_PREFIX="${ARTIFACT_PREFIX:-reader_storybook_500_20260425}"
DB_FILE="${DB_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}.db}"
SEED_FILE="${SEED_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_seed.json}"
RESULT_FILE="${RESULT_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_result.json}"
FAILURE_ARTIFACT_FILE="${FAILURE_ARTIFACT_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_failure_snapshot.json}"
SCREENSHOT_DIR="${SCREENSHOT_DIR:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_screenshots}"
AUDIT_FILE="${AUDIT_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_redundancy_audit.json}"
AUDIT_MARKDOWN_FILE="${AUDIT_MARKDOWN_FILE:-${ROOT_DIR}/artifacts/${ARTIFACT_PREFIX}_redundancy_audit.md}"
SERVER_LOG="${SERVER_LOG:-/tmp/reader_storybook_500_backend.log}"
FRONTEND_LOG="${FRONTEND_LOG:-/tmp/reader_storybook_500_frontend.log}"
CHROME_LOG="${CHROME_LOG:-/tmp/reader_storybook_500_chrome.log}"
SERVER_PID=""
FRONTEND_PID=""
CHROME_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
    wait "${FRONTEND_PID}" 2>/dev/null || true
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

mkdir -p "${ROOT_DIR}/artifacts" "${SCREENSHOT_DIR}"
if [[ "${REUSE_SEEDED_DB}" != "1" || ! -f "${DB_FILE}" || ! -f "${SEED_FILE}" ]]; then
  rm -f "${DB_FILE}" "${SEED_FILE}"
fi
rm -f "${RESULT_FILE}" "${FAILURE_ARTIFACT_FILE}" "${AUDIT_FILE}" "${AUDIT_MARKDOWN_FILE}"
rm -rf "${SCREENSHOT_DIR}" "${CHROME_USER_DIR}"
mkdir -p "${SCREENSHOT_DIR}"
rm -f "${SERVER_LOG}" "${FRONTEND_LOG}" "${CHROME_LOG}"

DATABASE_URL="sqlite:///${DB_FILE}"

if [[ -f "${DB_FILE}" && -f "${SEED_FILE}" ]]; then
  echo "Reusing seeded 500-chapter Reader Storybook replay data at ${DB_FILE}."
else
  echo "Seeding 500-chapter Reader Storybook replay data..."
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/seed_reader_storybook_long_route_smoke.py" \
    --database-url "${DATABASE_URL}" \
    --output "${SEED_FILE}" \
    --world-ids all \
    --target-chapters "${TARGET_CHAPTERS}" \
    --min-target-chapters "${MIN_TARGET_CHAPTERS}" \
    --max-attempts-per-chapter "${MAX_ATTEMPTS_PER_CHAPTER}" >/dev/null
fi

if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  if [[ "${REUSE_BACKEND}" != "1" ]]; then
    echo "Backend port ${BACKEND_PORT} is already in use. Stop the existing backend or set REUSE_BACKEND=1 if it already points at ${DB_FILE}." >&2
    exit 1
  fi
  echo "Reusing existing backend at ${BACKEND_URL}."
else
  echo "Starting NarrativeOS backend on fixed default port ${BACKEND_PORT}..."
  (
    cd "${ROOT_DIR}"
    export DATABASE_URL
    exec "${PYTHON_BIN}" -m uvicorn src.narrativeos.api:app --host 127.0.0.1 --port "${BACKEND_PORT}"
  ) >"${SERVER_LOG}" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 45); do
    if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "Backend failed to start. Server log:" >&2
  cat "${SERVER_LOG}" >&2 || true
  exit 1
fi

if curl -sf "${FRONTEND_URL}" >/dev/null 2>&1; then
  echo "Reusing existing Quantum frontend at ${FRONTEND_URL}."
else
  echo "Starting Quantum frontend on fixed default port ${FRONTEND_PORT}..."
  (
    cd "${ROOT_DIR}/Kimi_Agent_设计系统加载/app"
    export NARRATIVEOS_API_ORIGIN="${BACKEND_URL}"
    exec npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
  ) >"${FRONTEND_LOG}" 2>&1 &
  FRONTEND_PID="$!"
  for _ in $(seq 1 45); do
    if curl -sf "${FRONTEND_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -sf "${FRONTEND_URL}" >/dev/null 2>&1; then
  echo "Quantum frontend failed to start. Frontend log:" >&2
  cat "${FRONTEND_LOG}" >&2 || true
  exit 1
fi

if ! CHROME_BIN_RESOLVED="$(find_chrome_bin)"; then
  echo "Unable to locate a Chrome/Chromium binary. Set CHROME_BIN or install Google Chrome." >&2
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

echo "Verifying 500-chapter Storybook in Quantum frontend on ${FRONTEND_URL}..."
node "${ROOT_DIR}/scripts/verify_reader_storybook_500_quantum.js" \
  --url "${FRONTEND_URL}" \
  --seed-file "${SEED_FILE}" \
  --result-file "${RESULT_FILE}" \
  --failure-artifact-file "${FAILURE_ARTIFACT_FILE}" \
  --screenshot-dir "${SCREENSHOT_DIR}" \
  --chrome-port "${CHROME_PORT}"

echo "Writing human-perceived redundancy audit samples..."
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/audit_reader_storybook_500_redundancy.py" \
  --database-url "${DATABASE_URL}" \
  --seed-file "${SEED_FILE}" \
  --output "${AUDIT_FILE}" \
  --markdown-output "${AUDIT_MARKDOWN_FILE}" >/dev/null

echo "Reader Storybook 500 verification passed."
