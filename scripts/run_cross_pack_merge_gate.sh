#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BENCHMARK_JSON="${BENCHMARK_JSON:-artifacts/cross_pack_merge_gate.json}"
BENCHMARK_MD="${BENCHMARK_MD:-artifacts/cross_pack_merge_gate.md}"
MERGE_GATE_MD="${MERGE_GATE_MD:-artifacts/cross_pack_merge_gate_summary.md}"
DATABASE_URL="${DATABASE_URL:-sqlite:///narrativeos_beta.db}"
BASELINE_FILE="${BASELINE_FILE:-tests/benchmark_baseline.json}"
PR_BODY_FILE="${PR_BODY_FILE:-}"

. .venv/bin/activate

python -m src.narrativeos.benchmark.runner \
  --worldpack all \
  --golden-dir tests/golden_routes \
  --baseline-file "$BASELINE_FILE" \
  --database-url "$DATABASE_URL" \
  --markdown-out "$BENCHMARK_MD" \
  > "$BENCHMARK_JSON"

MERGE_ARGS=(
  --benchmark-file "$BENCHMARK_JSON"
  --summary-out "$MERGE_GATE_MD"
)

if [[ -n "$PR_BODY_FILE" ]]; then
  MERGE_ARGS+=(--pr-body-file "$PR_BODY_FILE" --require-pr-evidence)
fi

python -m src.narrativeos.benchmark.merge_gate "${MERGE_ARGS[@]}"
