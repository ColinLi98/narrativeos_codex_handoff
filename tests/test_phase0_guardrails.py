import subprocess
from pathlib import Path


def test_nested_agents_exist_for_core_worldpacks_and_web():
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "AGENTS.md",
        root / "src" / "narrativeos" / "core" / "AGENTS.md",
        root / "src" / "narrativeos" / "worldpacks" / "AGENTS.md",
        root / "src" / "narrativeos" / "web" / "AGENTS.md",
    ]
    for path in required:
        assert path.exists(), f"missing guardrail file: {path}"


def test_phase0_guardrail_script_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["bash", "scripts/run_phase0_guardrails.sh"],
        cwd=root,
        check=True,
    )
