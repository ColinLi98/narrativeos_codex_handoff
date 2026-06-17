#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

. .venv/bin/activate

required_agents=(
  "AGENTS.md"
  "src/narrativeos/core/AGENTS.md"
  "src/narrativeos/worldpacks/AGENTS.md"
  "src/narrativeos/web/AGENTS.md"
)

for path in "${required_agents[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing_required_agents:$path" >&2
    exit 1
  fi
done

required_pr_template_fields=(
  "- Goal met:"
  "- Out-of-scope changes introduced:"
  "- Does this move commercialization forward?:"
  "- Does this improve kernel/product/ops instead of just current-pack polish?:"
  "- Does this make weakest packs easier to diagnose or improve?:"
)

for field in "${required_pr_template_fields[@]}"; do
  if ! grep -Fq -- "$field" .github/pull_request_template.md; then
    echo "missing_pr_template_field:$field" >&2
    exit 1
  fi
done

if ! grep -q "artifacts/cross_pack_benchmark_summary.md" README.md; then
  echo "missing_benchmark_sample_reference_in_readme" >&2
  exit 1
fi

IMPORT_PATTERN="from \\.\\.worldpacks|from src\\.narrativeos\\.worldpacks|from narrativeos\\.worldpacks|import src\\.narrativeos\\.worldpacks|import narrativeos\\.worldpacks"
search_cmd() {
  if command -v rg >/dev/null 2>&1; then
    rg -n "$@"
  else
    grep -RInE "$@"
  fi
}

fixed_search_cmd() {
  if command -v rg >/dev/null 2>&1; then
    rg -n --fixed-strings "$@"
  else
    grep -RInF "$@"
  fi
}

if search_cmd "$IMPORT_PATTERN" src/narrativeos/core src/narrativeos/rendering.py >/dev/null; then
  echo "core_worldpacks_import_leak" >&2
  search_cmd "$IMPORT_PATTERN" src/narrativeos/core src/narrativeos/rendering.py >&2
  exit 1
fi

while IFS= read -r world_id; do
  if [[ -z "$world_id" ]]; then
    continue
  fi
  if fixed_search_cmd "$world_id" src/narrativeos/core src/narrativeos/rendering.py >/dev/null; then
    echo "core_pack_id_leak:$world_id" >&2
    fixed_search_cmd "$world_id" src/narrativeos/core src/narrativeos/rendering.py >&2
    exit 1
  fi
done < <(
  python - <<'PY'
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry

for item in FileSystemWorldRegistry().list_benchmark_worldpacks():
    print(item["world_id"])
PY
)

BENCHMARK_MD="${BENCHMARK_MD:-}"
BENCHMARK_BASELINE_MD="${BENCHMARK_BASELINE_MD:-tests/cross_pack_benchmark_summary.md}"
if [[ -z "$BENCHMARK_MD" ]]; then
  TMP_MD="$(mktemp)"
  TMP_JSON="$(mktemp)"
  python -m src.narrativeos.benchmark.runner \
    --worldpack all \
    --golden-dir tests/golden_routes \
    --baseline-file tests/benchmark_baseline.json \
    --database-url "${DATABASE_URL:-sqlite:///narrativeos_beta.db}" \
    --markdown-out "$TMP_MD" \
    > "$TMP_JSON"
  BENCHMARK_MD="$TMP_MD"
fi

if [[ ! -f "$BENCHMARK_BASELINE_MD" ]]; then
  echo "missing_benchmark_baseline_markdown:$BENCHMARK_BASELINE_MD" >&2
  exit 1
fi

normalize_benchmark_summary() {
  python - "$1" <<'PY'
import re
import sys

path = sys.argv[1]
section = ""
with open(path, "r", encoding="utf-8") as handle:
    for line in handle:
        if line.startswith("## ") or line.startswith("### "):
            section = line.strip()

        if line.startswith("- total wall ms:"):
            line = re.sub(r"(- total wall ms: )\d+(?:\.\d+)?", r"\1<ms>", line)
        elif line.startswith("- slowest worlds:"):
            line = "- slowest worlds: <runtime-order>\n"
        elif line.startswith("- stage totals:"):
            line = re.sub(r"\d+(?:\.\d+)?ms", "<ms>", line)
        elif line.startswith("- quality-pass stage actions:"):
            line = "- quality-pass stage actions: <actions>\n"
        elif line.startswith("- weakest packs evaluated:"):
            line = "- weakest packs evaluated: <worlds>\n"
        elif line.startswith("- watch worlds:"):
            line = "- watch worlds: <worlds>\n"
        elif line.startswith("- stop-ready worlds:"):
            line = "- stop-ready worlds: <worlds>\n"
        elif line.startswith("- continue worlds:"):
            line = "- continue worlds: <worlds>\n"
        elif line.startswith("- strongest packs changed:"):
            line = "- strongest packs changed: <ranking-delta>\n"
        elif line.startswith("- weakest packs changed:"):
            line = "- weakest packs changed: <ranking-delta>\n"
        elif line.startswith("- current strongest:"):
            line = "- current strongest: <worlds>\n"
        elif line.startswith("- current weakest:"):
            line = "- current weakest: <worlds>\n"
        elif section == "### Commercial Weakest-Pack Evidence" and re.match(r"^- [^:]+: long-route ", line):
            line = "- <world>: long-route <metrics>\n"
        elif section in {"## Strongest Packs", "## Weakest Packs"} and re.match(r"^- [^:]+: pass ", line):
            line = "- <world>: pass <metrics>\n"
        elif section == "## Weakest Packs" and line.startswith("  completion ratio:"):
            line = "  completion ratio: <metrics>\n"
        elif section == "## Weakest Packs" and line.startswith("  weakest dimensions:"):
            line = "  weakest dimensions: <dimensions>\n"
        elif section == "## Weakest Pack Diagnostics" and re.match(r"^- [^:]+: diagnostic rank ", line):
            line = "- <world>: diagnostic rank <metrics>\n"
        elif section == "## Weakest Pack Diagnostics" and line.startswith("  worst chapters:"):
            line = "  worst chapters: <chapters>\n"
        elif section == "## Weakest Pack Diagnostics" and line.startswith("  module / asset / policy:"):
            line = "  module / asset / policy: <target>\n"
        elif section == "## Weakest Pack Diagnostics" and line.startswith("  next fixes:"):
            line = "  next fixes: <fixes>\n"
        elif section == "## Weakest Pack Polish Program" and re.match(r"^- .+ \u00b7 ", line):
            line = "- <world>: <status> dimensions <dimensions>\n"
        sys.stdout.write(line)
PY
}

NORMALIZED_BASELINE_MD="$(mktemp)"
NORMALIZED_BENCHMARK_MD="$(mktemp)"
normalize_benchmark_summary "$BENCHMARK_BASELINE_MD" > "$NORMALIZED_BASELINE_MD"
normalize_benchmark_summary "$BENCHMARK_MD" > "$NORMALIZED_BENCHMARK_MD"
diff -u "$NORMALIZED_BASELINE_MD" "$NORMALIZED_BENCHMARK_MD"
