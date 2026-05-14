const fs = require("fs");

const CONTRACT_MARKERS = [
  "inject_internal_ops_snapshot_data",
  "verify_internal_ops_deep_cards",
  "ops_internal_runtime_receipts",
  "ops_internal_provider_runtime_metrics",
  "ops_internal_governance_export",
  "ops_internal_investigation_timeline",
  "ops_internal_learned_compare",
  "ops_internal_evaluator_promotion",
  "ops_internal_reranker_promotion",
  "ops_internal_learned_data_ops",
  "ops_internal_review_sample_backlog",
  "ops_internal_preference_samples",
  "ops_internal_ranking_samples",
  "ops_internal_pair_coverage_backlog",
  "ops_internal_review_capture_context",
  "ops_internal_last_action_impact",
  "schema_version",
  "Runtime Receipts",
  "Provider Runtime Metrics",
  "Evaluator Promotion Gate",
];

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    if (!current.startsWith("--")) continue;
    result[current.slice(2)] = argv[index + 1];
    index += 1;
  }
  return result;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["result-file"]) {
    fs.writeFileSync(args["result-file"], `${JSON.stringify({ schema_version: "ops_internal_snapshot/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`);
  }
}

main();
