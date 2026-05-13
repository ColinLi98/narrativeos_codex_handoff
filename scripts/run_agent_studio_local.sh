#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f ".env.local" ]; then
  # shellcheck disable=SC1091
  source ".env.local"
fi
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  source ".env"
fi

AGENT_STUDIO_LOCAL_DB="${AGENT_STUDIO_LOCAL_DB:-${ROOT_DIR}/narrativeos_agent_studio_local.db}"
DATABASE_URL="${DATABASE_URL:-sqlite:///${AGENT_STUDIO_LOCAL_DB}}"
export DATABASE_URL

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
AGENT_STUDIO_LOCAL_ACCOUNT_ID="${AGENT_STUDIO_LOCAL_ACCOUNT_ID:-agent_studio_user_demo}"
AGENT_STUDIO_URL="${AGENT_STUDIO_URL:-http://${APP_HOST}:${APP_PORT}/app?product=author&workspace=studio&debug=1&local_studio=1&account_id=${AGENT_STUDIO_LOCAL_ACCOUNT_ID}}"
AGENT_STUDIO_OPEN_BROWSER="${AGENT_STUDIO_OPEN_BROWSER:-1}"
AGENT_STUDIO_OPEN_TIMEOUT_SECONDS="${AGENT_STUDIO_OPEN_TIMEOUT_SECONDS:-90}"

open_agent_studio_url() {
  echo "agent_studio_frontend:${AGENT_STUDIO_URL}"
  if [ "${AGENT_STUDIO_OPEN_BROWSER}" = "0" ]; then
    return 0
  fi

  if command -v open >/dev/null 2>&1; then
    open "${AGENT_STUDIO_URL}" >/dev/null 2>&1 || true
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${AGENT_STUDIO_URL}" >/dev/null 2>&1 || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -m webbrowser "${AGENT_STUDIO_URL}" >/dev/null 2>&1 || true
  fi
}

wait_for_backend_and_open() {
  local deadline
  deadline=$((SECONDS + AGENT_STUDIO_OPEN_TIMEOUT_SECONDS))
  while [ "$SECONDS" -le "$deadline" ]; do
    if curl -sf "http://${APP_HOST}:${APP_PORT}/health" >/dev/null 2>&1; then
      open_agent_studio_url
      return 0
    fi
    sleep 1
  done
  echo "agent_studio_frontend_timeout:${AGENT_STUDIO_URL}" >&2
  return 0
}

if curl -sf "http://${APP_HOST}:${APP_PORT}/health" >/dev/null 2>&1; then
  open_agent_studio_url
  exit 0
fi

wait_for_backend_and_open &
exec bash scripts/run_backend_local.sh
