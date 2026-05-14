const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");

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

function pickSummary(summary) {
  return {
    author_register_login: summary.author_mutation_actor_id || "",
    grant_author_creator_access: summary.author_studio_credits_after_simulation !== undefined,
    author_create_draft_from_brief: summary.author_saved_draft_version_id || "",
    author_simulate_draft: summary.author_simulation_completed_chapters || 0,
    author_repair_loop_visible_after_rerun: Boolean(summary.author_repair_loop_visible_after_rerun || summary.author_repair_loop_issue_code),
    author_repair_loop_issue_code: summary.author_repair_loop_issue_code || "",
    author_repair_loop_summary_text: [
      summary.author_repair_loop_asset_target || "",
      summary.author_repair_loop_validation_panel || "",
      summary.author_repair_loop_severity_trend || "",
    ]
      .filter(Boolean)
      .join(" / "),
    author_repair_loop_ready_for_validation: Boolean(summary.author_repair_loop_ready_for_validation),
    author_repair_loop_noop_pass: Boolean(summary.author_repair_loop_noop_pass),
    author_repair_loop_effectively_ready: Boolean(summary.author_repair_loop_effectively_ready),
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const resultFile = args["result-file"] || path.join(process.cwd(), "artifacts", "author_repair_loop_smoke_result.json");
  const delegateResultFile = `${resultFile}.frontend_shell_tmp.json`;
  const frontendVerifier = path.join(__dirname, "verify_frontend_shell_smoke.js");
  const forwarded = [];
  for (const [key, value] of Object.entries(args)) {
    if (key === "result-file") continue;
    forwarded.push(`--${key}`, value);
  }
  const child = childProcess.spawnSync(
    process.execPath,
    [frontendVerifier, "--scope", "author", "--result-file", delegateResultFile, ...forwarded],
    { stdio: "inherit" },
  );
  if (child.status !== 0) {
    process.exit(child.status || 1);
  }
  const delegatePayload = JSON.parse(fs.readFileSync(delegateResultFile, "utf8"));
  const summary = delegatePayload.summary || {};
  const repairSummary = pickSummary(summary);
  const payload = {
    schema_version: "author_repair_loop_smoke/v1",
    status: "ok",
    summary: repairSummary,
    source_schema_version: delegatePayload.schema_version || "",
    source_result_file: delegateResultFile,
  };
  fs.writeFileSync(resultFile, `${JSON.stringify(payload, null, 2)}\n`);
}

main();
