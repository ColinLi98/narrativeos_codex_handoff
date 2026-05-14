#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8012}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
echo "quantum ops URL state smoke: backend=${BACKEND_PORT} frontend=${FRONTEND_PORT}"
