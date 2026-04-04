from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_cross_pack_quality_workflow_sets_explicit_database_url_for_benchmark():
    workflow_path = ROOT / ".github" / "workflows" / "cross-pack-quality.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    quality_job = payload["jobs"]["quality"]
    steps = quality_job["steps"]

    benchmark_step = next(step for step in steps if step.get("name") == "Run cross-pack benchmark")
    benchmark_run = benchmark_step["run"]

    assert "--database-url sqlite:///narrativeos_beta.db" in benchmark_run


def test_cross_pack_quality_workflow_keeps_safe_summary_fallbacks():
    workflow_path = ROOT / ".github" / "workflows" / "cross-pack-quality.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    quality_job = payload["jobs"]["quality"]
    steps = quality_job["steps"]

    summary_step = next(step for step in steps if step.get("name") == "Publish benchmark summary")
    summary_run = summary_step["run"]

    assert "if [ -f benchmark-summary.md ]" in summary_run
    assert 'echo "benchmark-summary.md missing"' in summary_run
    assert "if [ -f merge-gate-summary.md ]" in summary_run
    assert 'echo "merge-gate-summary.md missing"' in summary_run
