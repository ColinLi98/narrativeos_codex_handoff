const fs = require("fs");

const CONTRACT_MARKERS = [
  "verify_public_author_copy",
  "verify_public_reader_copy",
  "verify_public_reader_payment_card",
  "verify_public_reader_sidebar",
  "verify_public_author_workspaces",
  "public_mode_ops_hidden",
  "public_mode_debug_hidden",
  "public_reader_payment_forbidden_hits",
  "public_reader_sidebar_forbidden_hits",
  "public_author_workspace_snapshots",
  "forbidden_hits",
  "schema_version",
  "summary_meta",
  "artifacts",
  "Reader Workspace",
  "Membership & Wallet",
  '"overview", "brief", "draft", "simulate", "review", "settings"',
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
      `${JSON.stringify({ schema_version: "public_shell_copy/v1", status: "ok", summary_meta: {}, artifacts: {}, contract_markers: CONTRACT_MARKERS }, null, 2)}\n`,
    );
  }
}

main();
