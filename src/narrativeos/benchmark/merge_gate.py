from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


REQUIRED_PR_FIELDS = (
    "Lane",
    "Phase",
    "Task",
    "Goal met",
    "Out-of-scope changes introduced",
    "Tests run",
    "Benchmark / eval run",
    "strongest pack delta",
    "weakest pack delta",
    "cross-pack pass-rate delta",
    "rollback point",
    "Does this move commercialization forward?",
    "Does this improve kernel/product/ops instead of just current-pack polish?",
    "Does this make weakest packs easier to diagnose or improve?",
)

PLACEHOLDER_VALUES = {
    "",
    "-",
    "tbd",
    "todo",
    "<fill>",
    "<task>",
    "<lane>",
    "<phase>",
    "<goal>",
    "yes/no",
}


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _field_value(pr_body: str, label: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}\s*:?\s*(.*)$", re.MULTILINE)
    match = pattern.search(pr_body)
    return match.group(1).strip() if match else ""


def validate_benchmark_report(report: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if "cross_pack_pass_rate" not in report:
        errors.append("missing_cross_pack_pass_rate")
    if not report.get("strongest_packs"):
        errors.append("missing_strongest_packs")
    if not report.get("weakest_packs"):
        errors.append("missing_weakest_packs")
    if report.get("top_failing_packs") != report.get("weakest_packs"):
        errors.append("top_failing_packs_not_aligned_with_weakest")
    delta_summary = dict(report.get("delta_summary", {}))
    if "cross_pack_pass_rate_delta" not in delta_summary:
        errors.append("missing_cross_pack_pass_rate_delta")
    if "ranking_changes" not in delta_summary:
        errors.append("missing_ranking_changes")
    if float(delta_summary.get("cross_pack_pass_rate_delta", 0.0)) < 0:
        errors.append("cross_pack_pass_rate_regressed")
    regressions = list(delta_summary.get("regressions", []))
    if regressions:
        errors.append("metric_regression_detected")
    return errors


def validate_pr_evidence(pr_body: str) -> List[str]:
    errors: List[str] = []
    for label in REQUIRED_PR_FIELDS:
        value = _field_value(pr_body, label)
        if not value:
            errors.append(f"missing_pr_field:{label}")
            continue
        if _normalized_text(value) in PLACEHOLDER_VALUES:
            errors.append(f"placeholder_pr_field:{label}")
    current_pack_polish = _normalized_text(
        _field_value(pr_body, "Does this improve kernel/product/ops instead of just current-pack polish?")
    )
    if current_pack_polish == "no":
        errors.append("current_pack_polish_only")
    return errors


def build_gate_summary(report: Dict[str, Any], *, benchmark_errors: Sequence[str], pr_errors: Sequence[str]) -> str:
    delta_summary = dict(report.get("delta_summary", {}))
    strongest = ", ".join(item.get("world_id", "-") for item in report.get("strongest_packs", [])) or "-"
    weakest = ", ".join(item.get("world_id", "-") for item in report.get("weakest_packs", [])) or "-"
    lines = [
        "## Cross-Pack Merge Gate",
        f"- cross_pack_pass_rate: {float(report.get('cross_pack_pass_rate', 0.0)):.3f}",
        f"- cross_pack_pass_rate_delta: {float(delta_summary.get('cross_pack_pass_rate_delta', 0.0)):+.3f}",
        f"- strongest packs: {strongest}",
        f"- weakest packs: {weakest}",
        f"- benchmark errors: {', '.join(benchmark_errors) if benchmark_errors else 'none'}",
        f"- PR evidence errors: {', '.join(pr_errors) if pr_errors else 'none'}",
    ]
    return "\n".join(lines) + "\n"


def run_merge_gate(
    *,
    benchmark_file: Path,
    pr_body_file: Path | None = None,
    require_pr_evidence: bool = False,
    summary_out: Path | None = None,
) -> Dict[str, Any]:
    report = _load_json(benchmark_file)
    benchmark_errors = validate_benchmark_report(report)
    pr_errors: List[str] = []
    if require_pr_evidence:
        if pr_body_file is None or not pr_body_file.exists():
            pr_errors.append("missing_pr_body_file")
        else:
            pr_errors = validate_pr_evidence(pr_body_file.read_text(encoding="utf-8"))
    summary = build_gate_summary(report, benchmark_errors=benchmark_errors, pr_errors=pr_errors)
    if summary_out is not None:
        summary_out.write_text(summary, encoding="utf-8")
    if benchmark_errors or pr_errors:
        raise SystemExit("\n".join(benchmark_errors + pr_errors))
    return {
        "benchmark_errors": benchmark_errors,
        "pr_errors": pr_errors,
        "summary": summary,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate cross-pack benchmark evidence for merge gating.")
    parser.add_argument("--benchmark-file", required=True)
    parser.add_argument("--pr-body-file", default=None)
    parser.add_argument("--summary-out", default=None)
    parser.add_argument("--require-pr-evidence", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_merge_gate(
        benchmark_file=Path(args.benchmark_file),
        pr_body_file=Path(args.pr_body_file) if args.pr_body_file else None,
        require_pr_evidence=bool(args.require_pr_evidence),
        summary_out=Path(args.summary_out) if args.summary_out else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
