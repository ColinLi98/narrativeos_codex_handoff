const fs = require("fs");

const CONTRACT_MARKERS = [
  "inject_internal_ops_account_data",
  "verify_internal_ops_account_cards",
  "ops_account_subscription_audit",
  "ops_account_subscription_timeline",
  "ops_account_workspace_timeline",
  "ops_account_support_issues",
  "ops_account_alert_feed",
  "ops_account_alert_detail",
  "ops_account_governance_summary",
  "ops_account_governance_cases",
  "ops_account_governance_detail",
  "ops_account_audit_breakdown",
  "ops_account_audit_trail",
  "schema_version",
  "subscriptions:",
  "Audit Breakdown",
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
    fs.writeFileSync(args["result-file"], `${JSON.stringify({ schema_version: "ops_internal_account_copy/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`);
  }
}

main();
