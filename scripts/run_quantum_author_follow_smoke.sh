#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8014}"
FRONTEND_PORT="${FRONTEND_PORT:-3003}"
echo "quantum author follow smoke: backend=${BACKEND_PORT} frontend=${FRONTEND_PORT}"
