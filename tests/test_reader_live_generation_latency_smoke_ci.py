from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_reader_live_generation_latency_smoke_scripts_are_wired_and_parseable():
    run_script = ROOT / "scripts" / "run_reader_live_generation_latency_smoke.sh"
    verify_script = ROOT / "scripts" / "verify_reader_live_generation_latency_smoke.cjs"

    assert run_script.exists()
    assert verify_script.exists()

    run_text = run_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")

    assert "artifacts/reader_live_generation_latency/latest" in run_text
    assert "verify_reader_live_generation_latency_smoke.cjs" in run_text
    assert "/v1/reader/continue" in verify_text
    assert "/v1/reader/jobs/${current.jobId}/resume" in verify_text
    assert "deferBootstrap: true" in verify_text
    assert "remote_product_smoke_lightweight" not in verify_text
    assert "playwright" not in verify_text.lower()
    assert "chromium" not in verify_text.lower()
    assert "latency_budget_ms" in verify_text

    subprocess.run(["node", "--check", str(verify_script)], cwd=ROOT, check=True)


def test_reader_live_generation_latency_workflow_is_scheduled_and_separate_from_deploy_smoke():
    workflow_path = ROOT / ".github" / "workflows" / "reader-live-generation-latency-smoke.yml"
    assert workflow_path.exists()

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert workflow["name"] == "reader-live-generation-latency-smoke"
    assert "schedule" in workflow[True]
    assert workflow[True]["schedule"][0]["cron"] == "17 */6 * * *"
    assert "workflow_dispatch" in workflow[True]

    job = workflow["jobs"]["smoke"]
    steps = job["steps"]
    run_step = next(step for step in steps if step.get("name") == "Run Reader live-generation latency smoke")
    assert "bash scripts/run_reader_live_generation_latency_smoke.sh" in run_step["run"]
    assert run_step["env"]["PUBLIC_APP_URL"]
    assert run_step["env"]["READER_LIVE_GENERATION_BUDGET_MS"]

    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "run_vercel_remote_product_smoke.sh" not in workflow_text
    assert "remote_product_smoke_lightweight" not in workflow_text

    product_run_path = ROOT / "scripts" / "run_vercel_remote_product_smoke.sh"
    product_verify_path = ROOT / "scripts" / "verify_vercel_remote_product_smoke.cjs"
    if product_run_path.exists() and product_verify_path.exists():
        product_run_script = product_run_path.read_text(encoding="utf-8")
        product_verify_script = product_verify_path.read_text(encoding="utf-8")
        assert "run_reader_live_generation_latency_smoke.sh" not in product_run_script
        assert "verify_reader_live_generation_latency_smoke.cjs" not in product_verify_script
        assert "remote_product_smoke_lightweight" in product_verify_script
