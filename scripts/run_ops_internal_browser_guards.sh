#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_APP_PORT="${BASE_APP_PORT:-8025}"
BASE_CHROME_PORT="${BASE_CHROME_PORT:-9250}"

APP_PORT="${BASE_APP_PORT}" CHROME_PORT="${BASE_CHROME_PORT}" "${ROOT_DIR}/scripts/run_ops_internal_snapshot_check.sh"
APP_PORT="$((BASE_APP_PORT + 1))" CHROME_PORT="$((BASE_CHROME_PORT + 1))" "${ROOT_DIR}/scripts/run_ops_internal_form_copy_check.sh"
APP_PORT="$((BASE_APP_PORT + 2))" CHROME_PORT="$((BASE_CHROME_PORT + 2))" "${ROOT_DIR}/scripts/run_ops_internal_static_copy_check.sh"
APP_PORT="$((BASE_APP_PORT + 3))" CHROME_PORT="$((BASE_CHROME_PORT + 3))" "${ROOT_DIR}/scripts/run_ops_internal_populated_copy_check.sh"
APP_PORT="$((BASE_APP_PORT + 4))" CHROME_PORT="$((BASE_CHROME_PORT + 4))" "${ROOT_DIR}/scripts/run_ops_internal_account_copy_check.sh"
