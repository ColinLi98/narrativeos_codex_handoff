const fs = require("fs");

const CONTRACT_MARKERS = [
  "inject_internal_ops_populated_data",
  "verify_internal_ops_populated_cards",
  "ops_populated_review_queue",
  "ops_populated_world_status",
  "ops_populated_runtime_snapshot",
  "ops_populated_provider_routing",
  "ops_populated_provider_rollout",
  "ops_populated_provider_runtime_metrics",
  "ops_populated_investigation_summary",
  "ops_populated_investigation_evidence",
  "ops_populated_eval_metrics",
  "ops_populated_cross_pack_quality",
  "schema_version",
  "publish gate:",
  "Provider Routing Policy",
  "Continuation Drill-down",
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
    fs.writeFileSync(args["result-file"], `${JSON.stringify({ schema_version: "ops_internal_populated_copy/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`);
  }
}

main();
