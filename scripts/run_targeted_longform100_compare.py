from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.benchmark.runner import run_benchmark
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService


DEFAULT_WEAKEST_THREE = [
    "xianxia_forgotten_vow",
    "urban_mystery_lotus_lane",
    "jade_court_exam",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_summary(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_worlds(args) -> List[str]:
    explicit = [str(item).strip() for item in list(args.world_id or []) if str(item).strip()]
    if explicit:
        return explicit
    if args.source_summary:
        payload = _load_summary(Path(args.source_summary))
        weakest = [str(item.get("world_id") or "").strip() for item in list(payload.get("weakest_packs") or [])[:3] if str(item.get("world_id") or "").strip()]
        if weakest:
            return weakest
    return list(DEFAULT_WEAKEST_THREE)


def _world_lookup(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("world_id") or ""): dict(item)
        for item in list(summary.get("worlds") or [])
        if str(item.get("world_id") or "").strip()
    }


def _calibration_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    calibration = dict(payload.get("continuation_calibration") or {})
    q03 = dict(calibration.get("q03") or {})
    q09 = dict(calibration.get("q09") or {})
    return {
        "coverage_status": calibration.get("coverage_status"),
        "sample_count": calibration.get("sample_count"),
        "sample_gap": calibration.get("sample_gap"),
        "q03_primary_metric": q03.get("primary_metric"),
        "q03_primary_correlation": q03.get("primary_correlation"),
        "q03_recommendation": q03.get("recommendation"),
        "q09_primary_metric": q09.get("primary_metric"),
        "q09_primary_correlation": q09.get("primary_correlation"),
        "q09_recommendation": q09.get("recommendation"),
    }


def build_targeted_compare_summary(
    *,
    before: Dict[str, Any],
    after: Dict[str, Any],
    supplementation: Dict[str, Any],
    target_worlds: Sequence[str],
) -> Dict[str, Any]:
    before_worlds = _world_lookup(before)
    after_worlds = _world_lookup(after)
    by_version_summary = {
        str(item.get("world_version_id") or ""): dict(item)
        for item in list(supplementation.get("world_summaries") or [])
        if str(item.get("world_version_id") or "").strip()
    }
    deltas: List[Dict[str, Any]] = []
    for world_id in target_worlds:
        before_item = before_worlds.get(world_id, {})
        after_item = after_worlds.get(world_id, {})
        supplement = by_version_summary.get(str(after_item.get("world_version_id") or ""), {})
        before_issue_map = {str(item.get("issue_code") or ""): int(item.get("count", 0) or 0) for item in list(before_item.get("top_issue_categories") or [])}
        after_issue_map = {str(item.get("issue_code") or ""): int(item.get("count", 0) or 0) for item in list(after_item.get("top_issue_categories") or [])}
        deltas.append(
            {
                "world_id": world_id,
                "world_version_id": after_item.get("world_version_id") or before_item.get("world_version_id"),
                "before_pass_rate": before_item.get("pass_rate"),
                "after_pass_rate": after_item.get("pass_rate"),
                "before_rewrite_rate": before_item.get("rewrite_rate"),
                "after_rewrite_rate": after_item.get("rewrite_rate"),
                "before_block_rate": before_item.get("block_rate"),
                "after_block_rate": after_item.get("block_rate"),
                "before_q03_count": before_issue_map.get("Q03", 0),
                "after_q03_count": after_issue_map.get("Q03", 0),
                "before_q09_count": before_issue_map.get("Q09", 0),
                "after_q09_count": after_issue_map.get("Q09", 0),
                "before_diagnostic_rank": before_item.get("diagnostic_rank"),
                "after_diagnostic_rank": after_item.get("diagnostic_rank"),
                "before_diagnostic_score": before_item.get("diagnostic_score"),
                "after_diagnostic_score": after_item.get("diagnostic_score"),
                "before_calibration": _calibration_digest(before_item),
                "after_calibration": _calibration_digest(after_item),
                "supplementation": supplement,
            }
        )
    return {
        "generated_at": _utcnow(),
        "target_worlds": list(target_worlds),
        "before_summary_path": None,
        "after_summary_path": None,
        "supplementation": supplementation,
        "world_deltas": deltas,
    }


def _render_compare_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Targeted Longform 100 Compare",
        "",
        "- generated_at: %s" % (summary.get("generated_at") or "-"),
        "- target_worlds: %s" % (", ".join(summary.get("target_worlds", [])) or "-"),
        "",
        "## World Deltas",
    ]
    for item in summary.get("world_deltas", []):
        lines.extend(
            [
                "- %s" % item.get("world_id", "-"),
                "  pass %.3f -> %.3f · rewrite %.3f -> %.3f · block %.3f -> %.3f"
                % (
                    float(item.get("before_pass_rate", 0.0) or 0.0),
                    float(item.get("after_pass_rate", 0.0) or 0.0),
                    float(item.get("before_rewrite_rate", 0.0) or 0.0),
                    float(item.get("after_rewrite_rate", 0.0) or 0.0),
                    float(item.get("before_block_rate", 0.0) or 0.0),
                    float(item.get("after_block_rate", 0.0) or 0.0),
                ),
                "  q03 %s -> %s · q09 %s -> %s"
                % (
                    item.get("before_q03_count", 0),
                    item.get("after_q03_count", 0),
                    item.get("before_q09_count", 0),
                    item.get("after_q09_count", 0),
                ),
                "  calibration q03 %s -> %s · q09 %s -> %s"
                % (
                    dict(item.get("before_calibration") or {}).get("q03_recommendation", "-"),
                    dict(item.get("after_calibration") or {}).get("q03_recommendation", "-"),
                    dict(item.get("before_calibration") or {}).get("q09_recommendation", "-"),
                    dict(item.get("after_calibration") or {}).get("q09_recommendation", "-"),
                ),
                "  continuation samples %s -> %s"
                % (
                    dict(item.get("before_calibration") or {}).get("sample_count", 0),
                    dict(item.get("after_calibration") or {}).get("sample_count", 0),
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run weakest-three longform_100 compare with real continuation supplementation.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-summary", default=None)
    parser.add_argument("--world-id", action="append", default=[])
    parser.add_argument("--baseline-file", default="tests/benchmark_baseline.json")
    parser.add_argument("--sample-target-per-version", type=int, default=8)
    parser.add_argument("--negative-target-per-version", type=int, default=2)
    parser.add_argument("--chapters-per-session", type=int, default=2)
    parser.add_argument("--max-sessions-per-version", type=int, default=12)
    args = parser.parse_args(list(argv) if argv is not None else None)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repository = SQLAlchemyRepository(database_url=args.database_url)
    training_signal = TrainingSignalService(repository)
    target_worlds = _target_worlds(args)
    baseline_path = Path(args.baseline_file)
    baseline = _load_summary(baseline_path) if baseline_path.exists() else None

    before = run_benchmark(
        repository=repository,
        golden_dir=output_dir / "before_goldens",
        worldpack=target_worlds,
        baseline=baseline,
        benchmark_mode="longform_100",
        max_chapters=100,
    )
    world_version_ids = [str(item.get("world_version_id") or "") for item in list(before.get("worlds") or []) if str(item.get("world_version_id") or "").strip()]
    supplementation = training_signal.supplement_real_continuation_samples(
        world_version_ids=world_version_ids,
        target_sample_count_per_version=int(args.sample_target_per_version),
        target_negative_samples=int(args.negative_target_per_version),
        chapters_per_session=int(args.chapters_per_session),
        max_sessions_per_version=int(args.max_sessions_per_version),
        reader_id_prefix="targeted_longform100",
    )
    after = run_benchmark(
        repository=repository,
        golden_dir=output_dir / "after_goldens",
        worldpack=target_worlds,
        baseline=baseline,
        benchmark_mode="longform_100",
        max_chapters=100,
    )
    compare = build_targeted_compare_summary(
        before=before,
        after=after,
        supplementation=supplementation,
        target_worlds=target_worlds,
    )

    before_path = output_dir / "targeted_longform100_before.json"
    after_path = output_dir / "targeted_longform100_after.json"
    compare_path = output_dir / "targeted_longform100_compare.json"
    markdown_path = output_dir / "targeted_longform100_compare.md"

    before_path.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    after_path.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    compare["before_summary_path"] = str(before_path)
    compare["after_summary_path"] = str(after_path)
    compare_path.write_text(json.dumps(compare, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_compare_markdown(compare), encoding="utf-8")
    print(json.dumps(compare, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
