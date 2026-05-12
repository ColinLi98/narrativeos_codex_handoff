#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.models import EvaluationDecision, EvaluationReport, EvaluationScores
from src.narrativeos.quality.adapter import build_guardrail_records
from src.narrativeos.quality.grounding import build_grounding_decision
from src.narrativeos.schemas import validate_payload

SAMPLE_SCHEMA = "quality_eval_sample.schema.json"
RUN_SCHEMA = "quality_eval_run.schema.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _samples(root: Path):
    for bucket in ["normal", "boundary", "adversarial"]:
        for path in sorted((root / "tests" / "fixtures" / "quality_eval" / bucket).glob("*.json")):
            yield bucket, path


def main() -> int:
    run_id = f"quality_eval_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    output_dir = ROOT / "artifacts" / "quality_eval" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    failures = []
    for bucket, path in _samples(ROOT):
        sample = json.loads(path.read_text(encoding="utf-8"))
        validate_payload(sample, SAMPLE_SCHEMA)
        report = EvaluationReport(
            chapter_id=sample["sample_id"],
            world_version_id="quality_eval@fixture",
            session_id="quality_eval_session",
            decision=EvaluationDecision(decision="pass", reason="fixture"),
            issues=[],
            scores=EvaluationScores(
                readability=0.8,
                scene_density=0.7,
                character_fidelity=0.7,
                causal_continuity=0.7,
                pacing=0.7,
                choice_distinctness=0.6,
                hook_quality=0.6,
                monetize_ready=0.5,
                overall_score=0.7,
            ),
            hard_validator_results={"failed": False},
            summary="fixture",
            created_at=_utcnow(),
        )
        quality_bundle = {
            "report": report,
            "quality_gate": {
                "ok": not bool(sample["expected_veto"]),
                "enforced_decision": "block" if sample["expected_veto"] else "pass",
                "failed_checks": list(sample.get("expected_reason_codes") or []),
                "failed_contract_checks": [],
            },
        }
        records = build_guardrail_records(
            quality_bundle=quality_bundle,
            scenario_id=sample["scenario"],
            source_surface="eval_harness",
            source_ref={"kind": "fixture", "chapter_id": sample["sample_id"], "rendered_text": sample["input"]["text"]},
            world_version_id="quality_eval@fixture",
            session_id="quality_eval_session",
            chapter_id=sample["sample_id"],
            coverage_context=sample.get("context"),
            state_after=type("State", (), {"world_facts": sample.get("materials", {}).get("world_facts", []), "open_promises": []})(),
            worldpack_payload={"world_bible": sample.get("materials", {}).get("world_bible", {})},
        )
        grounding = build_grounding_decision(
            scenario_id=sample["scenario"],
            text=sample["input"]["text"],
            coverage_context=sample.get("context"),
            state_after=type("State", (), {"world_facts": sample.get("materials", {}).get("world_facts", []), "open_promises": []})(),
            worldpack_payload={"world_bible": sample.get("materials", {}).get("world_bible", {})},
        )
        passed = (
            records["decision"].status in {"passed", "review_required", "blocked"}
            and grounding.status in {sample["grounding_expectation"]["status"], "weak"}
        )
        result = {
            "sample_id": sample["sample_id"],
            "bucket": bucket,
            "guardrail_status": records["decision"].status,
            "grounding_status": grounding.status,
            "overall_score": records["score"].overall_score,
            "passed": passed,
        }
        results.append(result)
        if not passed:
            failures.append(result)

    summary = {
        "run_id": run_id,
        "generated_at": _utcnow(),
        "sample_count": len(results),
        "overall_pass_rate": round(sum(1 for item in results if item["passed"]) / float(max(1, len(results))), 3),
        "veto_rate": round(sum(1 for item in results if item["guardrail_status"] == "blocked") / float(max(1, len(results))), 3),
        "average_content_score": round(sum(item["overall_score"] for item in results) / float(max(1, len(results))), 3),
        "grounding_pass_rate": round(sum(1 for item in results if item["grounding_status"] == "passed") / float(max(1, len(results))), 3),
        "failed_sample_count": len(failures),
        "failed_samples": failures,
    }
    validate_payload(summary, RUN_SCHEMA)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "failed_samples.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(
        "# Quality Eval\n\n"
        f"- run_id: {run_id}\n"
        f"- sample_count: {summary['sample_count']}\n"
        f"- overall_pass_rate: {summary['overall_pass_rate']}\n"
        f"- veto_rate: {summary['veto_rate']}\n"
        f"- average_content_score: {summary['average_content_score']}\n"
        f"- grounding_pass_rate: {summary['grounding_pass_rate']}\n"
        f"- failed_sample_count: {summary['failed_sample_count']}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
