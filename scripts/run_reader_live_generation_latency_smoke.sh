#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_APP_URL="${PUBLIC_APP_URL:-https://pilot.lixidol.com}"
API_ORIGIN="${API_ORIGIN:-${PUBLIC_APP_URL}}"
ARTIFACT_DIR="${ARTIFACT_DIR:-${ROOT_DIR}/artifacts/reader_live_generation_latency/latest}"
RESULT_FILE="${RESULT_FILE:-${ARTIFACT_DIR}/summary.json}"
FAILURE_ARTIFACT_FILE="${FAILURE_ARTIFACT_FILE:-${ARTIFACT_DIR}/failure.json}"

mkdir -p "${ARTIFACT_DIR}"
rm -f "${RESULT_FILE}" "${FAILURE_ARTIFACT_FILE}"

echo "Running Reader live-generation latency smoke against ${API_ORIGIN}..."
node "${ROOT_DIR}/scripts/verify_reader_live_generation_latency_smoke.cjs" \
  --public-app-url "${PUBLIC_APP_URL}" \
  --api-origin "${API_ORIGIN}" \
  --result-file "${RESULT_FILE}" \
  --failure-artifact-file "${FAILURE_ARTIFACT_FILE}"

echo "Reader live-generation latency smoke passed."
