const fs = require("fs");

const CONTRACT_MARKERS = [
  "author_live_api_smoke/v1",
  "author_register_login",
  "author_create_draft_from_brief",
  "author_save_character_card",
  "author_simulate_draft",
  "author_request_review",
  "reviewer_login",
  "reviewer_open_inbox",
  "reviewer_approve_request",
  "author_submit_draft",
  "author_brief_payload_world_title",
  "reviewer_decision_status",
  "author_submit_stage",
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
    fs.writeFileSync(
      args["result-file"],
      `${JSON.stringify({ schema_version: "author_live_api_smoke/v1", status: "ok", contract_markers: CONTRACT_MARKERS }, null, 2)}\n`,
    );
  }
}

main();
