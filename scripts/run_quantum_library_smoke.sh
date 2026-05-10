#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8013}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"
echo "quantum library smoke: backend=${BACKEND_PORT} frontend=${FRONTEND_PORT}"
