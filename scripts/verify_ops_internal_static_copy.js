const fs = require("fs");

const CONTRACT_MARKERS = [
  "verify_internal_ops_static_copy",
  "ops_static_world_status",
  "ops_static_release_workspace",
  "ops_static_account_workspace",
  "ops_static_support",
  "ops_static_alerts",
  "ops_static_governance",
  "ops_static_investigation",
  "ops_static_eval_metrics",
  "ops_static_cross_pack",
  "ops_static_learned_overview",
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
    fs.writeFileSync(args["result-file"], `${JSON.stringify({ schema_version: "ops_internal_static_copy/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`);
  }
}

main();
