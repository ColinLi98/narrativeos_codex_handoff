#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in "${ROOT_DIR}/.venv311/bin/python" "${ROOT_DIR}/.venv/bin/python" "$(command -v python3 || true)"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      PYTHON_BIN="${candidate}"
      break
    fi
  done
fi
if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Unable to locate python. Set PYTHON_BIN or create .venv311/.venv." >&2
  exit 1
fi

ARTIFACT_DIR="${ROOT_DIR}/artifacts"
DB_PATH="${COMMERCIAL_LONG_ROUTE_DB:-${ARTIFACT_DIR}/commercial_long_route_50.db}"
JSON_OUT="${COMMERCIAL_LONG_ROUTE_JSON:-${ARTIFACT_DIR}/commercial_long_route_50.json}"
MD_OUT="${COMMERCIAL_LONG_ROUTE_MD:-${ARTIFACT_DIR}/commercial_long_route_50.md}"

mkdir -p "${ARTIFACT_DIR}"
rm -f "${DB_PATH}" "${JSON_OUT}" "${MD_OUT}"

"${PYTHON_BIN}" -m src.narrativeos.benchmark.runner \
  --worldpack all \
  --database-url "sqlite:///${DB_PATH}" \
  --benchmark-mode long_route \
  --max-chapters 50 \
  --markdown-out "${MD_OUT}" > "${JSON_OUT}"

"${PYTHON_BIN}" - "${JSON_OUT}" <<'PY'
import json
import sys

path = sys.argv[1]
payload = json.load(open(path, encoding="utf-8"))
gate = payload.get("commercial_long_route_gate") or {}
if not gate.get("applicable"):
    raise SystemExit("commercial_long_route_gate_not_applicable")
if not gate.get("ok"):
    raise SystemExit("commercial_long_route_gate_blocked:%s" % ",".join(gate.get("failed_checks") or []))
print("commercial_long_route_50 passed: %s" % path)
PY
