#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env.local ]]; then
  set -a
  source ./.env.local
  set +a
fi

if [[ -f .env ]]; then
  set -a
  source ./.env
  set +a
fi

PYTHON_BIN="./.venv311/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="./.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"

if curl -sf "http://${APP_HOST}:${APP_PORT}/health" >/dev/null 2>&1; then
  echo "app_already_running:http://${APP_HOST}:${APP_PORT}"
  exit 0
fi

"$PYTHON_BIN" scripts/check_database_env.py --format text

exec "$PYTHON_BIN" -m uvicorn src.narrativeos.api:app --host "${APP_HOST}" --port "${APP_PORT}"
