#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULT_FILE="${ROOT_DIR}/artifacts/author_live_api_smoke_result.json"
FAILURE_ARTIFACT_FILE="${ROOT_DIR}/artifacts/author_live_api_smoke_failure_snapshot.json"
FAILURE_SCREENSHOT_FILE="${ROOT_DIR}/artifacts/author_live_api_smoke_failure.png"
AUTHOR_CHROME_PORT="${AUTHOR_CHROME_PORT:-9240}"
REVIEWER_CHROME_PORT="${REVIEWER_CHROME_PORT:-9241}"
AUTHOR_APP_URL="${AUTHOR_APP_URL:-http://127.0.0.1:8020/app?product=author&debug=1}"
REVIEWER_APP_URL="${REVIEWER_APP_URL:-http://127.0.0.1:8020/app?product=author&debug=1}"

stop_existing_debug_port() {
  local port="$1"
  pkill -f "remote-debugging-port=${port}" >/dev/null 2>&1 || true
}

mkdir -p "${ROOT_DIR}/artifacts"
rm -f "${RESULT_FILE}" "${FAILURE_ARTIFACT_FILE}" "${FAILURE_SCREENSHOT_FILE}"
stop_existing_debug_port "${AUTHOR_CHROME_PORT}"
stop_existing_debug_port "${REVIEWER_CHROME_PORT}"

node "${ROOT_DIR}/scripts/verify_author_live_api_smoke.js" \
  --author-url "${AUTHOR_APP_URL}" \
  --reviewer-url "${REVIEWER_APP_URL}" \
  --result-file "${RESULT_FILE}" \
  --failure-artifact-file "${FAILURE_ARTIFACT_FILE}" \
  --failure-screenshot-file "${FAILURE_SCREENSHOT_FILE}" \
  --author-chrome-port "${AUTHOR_CHROME_PORT}" \
  --reviewer-chrome-port "${REVIEWER_CHROME_PORT}"
