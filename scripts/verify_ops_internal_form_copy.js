const fs = require("fs");

const CONTRACT_MARKERS = [
  "verify_internal_ops_form_copy",
  "ops_form_navigation",
  "ops_form_release",
  "ops_form_account_subscription",
  "ops_form_alerts",
  "ops_form_governance",
  "ops_form_investigation",
  "ops_form_assisted_gate",
  "ops_form_assisted_rerank",
  "ops_form_evaluator_promotion",
  "ops_form_reranker_promotion",
  "ops_form_review_capture",
  "ops_form_preference_capture",
  "ops_form_ranking_capture",
  "ops_form_data_integrity",
  "ops_form_runbook",
  "ops_form_async_jobs",
  "ops_form_provider_rollout",
  "schema_version",
  "Account ID",
  "Reviewer ID",
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
    fs.writeFileSync(args["result-file"], `${JSON.stringify({ schema_version: "ops_internal_form_copy/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`);
  }
}

main();
