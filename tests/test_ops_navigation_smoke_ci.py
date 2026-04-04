from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_ops_navigation_smoke_scripts_exist_and_are_parseable():
    run_script = ROOT / "scripts" / "run_ops_navigation_stale_ref_smoke.sh"
    seed_script = ROOT / "scripts" / "seed_ops_navigation_stale_ref_smoke.py"
    verify_script = ROOT / "scripts" / "verify_ops_navigation_stale_ref_smoke.js"
    summary_script = ROOT / "scripts" / "write_ops_navigation_stale_ref_step_summary.py"

    assert run_script.exists()
    assert seed_script.exists()
    assert verify_script.exists()
    assert summary_script.exists()

    run_text = run_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")
    summary_text = summary_script.read_text(encoding="utf-8")

    assert "CI_HEADLESS" in run_text
    assert "CHROME_BIN" in run_text
    assert "ops_navigation_stale_ref_smoke_result.json" in run_text
    assert "ops_navigation_stale_ref_smoke_failure_snapshot.json" in run_text
    assert "ops_navigation_stale_ref_smoke_failure.png" in run_text
    assert "--result-file" in run_text
    assert "--failure-artifact-file" in run_text
    assert "--failure-screenshot-file" in run_text
    assert "failed_step" in verify_text
    assert "completed_steps" in verify_text
    assert "body_html_excerpt" in verify_text
    assert "captureScreenshot" in verify_text
    assert "resyncSnapshot" in verify_text
    assert "clearSnapshot" in verify_text
    assert "Ops Navigation Stale-Ref Smoke" in summary_text
    assert "failed_step" in summary_text
    assert "Failure Snapshot" in summary_text
    assert "Failure screenshot" in summary_text


def test_ops_navigation_smoke_workflow_wires_headless_runner_and_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "ops-navigation-stale-ref-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert payload["name"] == "ops-navigation-stale-ref-smoke"
    smoke_job = payload["jobs"]["smoke"]
    steps = smoke_job["steps"]

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    run_step = next(step for step in steps if step.get("name") == "Run ops navigation stale-ref smoke")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_ops_navigation_stale_ref_smoke.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish stale-ref smoke summary")
    summary_run = summary_step["run"]
    assert summary_step["if"] == "always()"
    assert "write_ops_navigation_stale_ref_step_summary.py" in summary_run
    assert "ops_navigation_stale_ref_smoke_result.json" in summary_run
    assert "ops_navigation_stale_ref_smoke_failure_snapshot.json" in summary_run
    assert "$GITHUB_STEP_SUMMARY" in summary_run

    artifact_step = next(step for step in steps if step.get("name") == "Upload stale-ref smoke artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/ops_navigation_stale_ref_smoke_seed.json" in artifact_path
    assert "artifacts/ops_navigation_stale_ref_smoke_result.json" in artifact_path
    assert "artifacts/ops_navigation_stale_ref_smoke_failure_snapshot.json" in artifact_path
    assert "artifacts/ops_navigation_stale_ref_smoke_failure.png" in artifact_path
    assert "/tmp/ops_navigation_stale_ref_smoke_server.log" in artifact_path
    assert "/tmp/ops_navigation_stale_ref_smoke_chrome.log" in artifact_path
