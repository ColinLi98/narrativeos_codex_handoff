from pathlib import Path
import json
import subprocess
import sys

from src.narrativeos.schemas import validate_payload


ROOT = Path(__file__).resolve().parents[1]


def test_quality_eval_sample_fixture_schema():
    for bucket in ["normal", "boundary", "adversarial"]:
        for path in sorted((ROOT / "tests" / "fixtures" / "quality_eval" / bucket).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate_payload(payload, "quality_eval_sample.schema.json")


def test_grounding_eval_harness_outputs_artifacts(tmp_path: Path):
    script = ROOT / "scripts" / "run_grounding_eval.py"
    result = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)
    assert result.returncode == 0
    runs = sorted((ROOT / "artifacts" / "quality_eval").glob("grounding_eval_*"))
    assert runs
    latest = runs[-1]
    assert (latest / "summary.json").exists()
    assert (latest / "summary.md").exists()
    assert (latest / "failed_samples.json").exists()
    summary = json.loads((latest / "summary.json").read_text(encoding="utf-8"))
    validate_payload(summary, "quality_eval_run.schema.json")


def test_quality_eval_harness_outputs_failed_samples(tmp_path: Path):
    script = ROOT / "scripts" / "run_quality_eval.py"
    result = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)
    assert result.returncode == 0
    runs = sorted((ROOT / "artifacts" / "quality_eval").glob("quality_eval_*"))
    assert runs
    latest = runs[-1]
    failed = json.loads((latest / "failed_samples.json").read_text(encoding="utf-8"))
    assert isinstance(failed, list)
    assert (latest / "metrics.json").exists()
