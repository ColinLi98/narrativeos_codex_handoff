#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULT_FILE="${ROOT_DIR}/artifacts/ops_internal_account_copy_result.json"
FAILURE_ARTIFACT_FILE="${ROOT_DIR}/artifacts/ops_internal_account_copy_failure_snapshot.json"
FAILURE_SCREENSHOT_FILE="${ROOT_DIR}/artifacts/ops_internal_account_copy_failure.png"

mkdir -p "${ROOT_DIR}/artifacts"
rm -f "${RESULT_FILE}" "${FAILURE_ARTIFACT_FILE}" "${FAILURE_SCREENSHOT_FILE}"

node "${ROOT_DIR}/scripts/verify_ops_internal_account_copy.js" \
  --result-file "${RESULT_FILE}" \
  --failure-artifact-file "${FAILURE_ARTIFACT_FILE}" \
  --failure-screenshot-file "${FAILURE_SCREENSHOT_FILE}"
