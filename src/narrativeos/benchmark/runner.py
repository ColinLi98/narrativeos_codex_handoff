from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

from ..models import EvaluationReport
from ..repository import SQLAlchemyRepository
from ..worldpacks.registry import FileSystemWorldRegistry
from .reporting import (
    assign_diagnostic_ranks,
    benchmark_delta_report,
    build_dimension_scores,
    build_issue_mix,
    build_issue_summary,
    build_long_route_diagnostics,
    build_long_route_summary,
    build_route_diagnostics,
    build_weakest_pack_diagnostic,
    rank_strongest_packs,
    rank_top_failing_packs,
    rank_weakest_packs,
    render_benchmark_markdown,
)


BENCHMARK_PACKS = [item["world_id"] for item in FileSystemWorldRegistry().list_benchmark_worldpacks()]


def _resolve_world_ids(worldpack: str | Sequence[str]) -> List[str]:
    if isinstance(worldpack, str):
        if worldpack == "all":
            return [item["world_id"] for item in FileSystemWorldRegistry().list_benchmark_worldpacks()]
        return [worldpack]
    return list(worldpack)


def run_benchmark(
    *,
    repository: SQLAlchemyRepository,
    golden_dir: Path,
    worldpack: str | Sequence[str] = "all",
    baseline: Dict[str, object] | None = None,
    world_version_overrides: Dict[str, str] | None = None,
    simulation_runner: Callable[[str, str], Dict[str, object]] | None = None,
    max_chapters: int = 6,
    min_end_turn_override: int | None = None,
) -> Dict[str, object]:
    registry = FileSystemWorldRegistry()
    world_version_overrides = world_version_overrides or {}
    if simulation_runner is None:
        from ..services.authoring import AuthoringService

        authoring = AuthoringService(repository, registry=registry)
        simulation_runner = lambda world_id, world_version_id: authoring.run_simulation_for_world_version(  # noqa: E731
            world_version_id,
            include_cross_pack=False,
            max_chapters=max_chapters,
            min_end_turn_override=min_end_turn_override,
        )
    worlds = []
    chapter_reports_by_world: Dict[str, List[Dict[str, object]]] = {}
    pack_payload_by_world: Dict[str, Dict[str, object]] = {}
    for world_id in _resolve_world_ids(worldpack):
        override_world_version_id = world_version_overrides.get(world_id)
        if override_world_version_id:
            world_version_id = override_world_version_id
        else:
            world_card = registry.get_published_world(world_id)
            world_version_id = world_card["world_version_id"]
        runtime = repository.get_runtime_bundle(world_version_id)
        pack_payload = runtime.worldpack.to_dict()
        pack_payload_by_world[world_id] = pack_payload
        style_pack = dict(pack_payload.get("narrative_style_pack", {}))
        dialogue = dict(style_pack.get("dialogue", {}))
        voice_profiles = dict(pack_payload.get("voice_profiles") or dialogue.get("voice_profiles", {}))
        action_policies = dict(pack_payload.get("emotion_action_policies", {}))
        default_action_policy = next(iter(action_policies.values()), style_pack.get("emotion_actions", {}))
        action_map = dict(default_action_policy.get("action_map", {}))
        report = simulation_runner(world_id, world_version_id)
        chapter_reports = [EvaluationReport.from_dict(item) for item in report.get("chapter_evaluations", [])]
        chapter_reports_by_world[world_id] = [item.to_dict() for item in chapter_reports]
        evaluation = report.get("evaluation_summary", {})
        issue_mix = build_issue_mix(
            [issue.to_dict() for chapter_report in chapter_reports for issue in chapter_report.issues]
        )
        route_diagnostics = build_route_diagnostics(
            [float(item.scores.overall_score) for item in chapter_reports],
            completed_chapters=int(report.get("completed_chapters", 0)),
            target_chapters=max_chapters,
        )
        long_route_diagnostics = build_long_route_diagnostics(
            chapter_report_payloads=chapter_reports_by_world[world_id],
            completed_chapters=int(report.get("completed_chapters", 0)),
            target_chapters=max_chapters,
            min_end_turn_target=int(report.get("min_end_turn_target", min_end_turn_override or 6)),
            stop_reason=str(report.get("stop_reason", "chapter_budget_reached")),
        )
        if chapter_reports:
            character_fidelity = sum(item.scores.character_fidelity for item in chapter_reports) / len(chapter_reports)
            causal_continuity = sum(item.scores.causal_continuity for item in chapter_reports) / len(chapter_reports)
            choice_distinctness = sum(item.scores.choice_distinctness for item in chapter_reports) / len(chapter_reports)
            prose_leak_rate = sum(item.hard_validator_results.get("lint_metrics", {}).get("engineering_leak_rate", 0.0) for item in chapter_reports) / len(chapter_reports)
            dialogue_ratio = sum(item.hard_validator_results.get("lint_metrics", {}).get("dialogue_plus_action_ratio", 0.0) for item in chapter_reports) / len(chapter_reports)
            scene_detail_density = sum(item.hard_validator_results.get("lint_metrics", {}).get("concrete_detail_density", 0.0) for item in chapter_reports) / len(chapter_reports)
        else:
            character_fidelity = causal_continuity = choice_distinctness = prose_leak_rate = dialogue_ratio = scene_detail_density = 0.0
        if voice_profiles:
            bluntness_values = [float(profile.get("bluntness", 0.5)) for profile in voice_profiles.values()]
            restraint_values = [float(profile.get("restraint", 0.5)) for profile in voice_profiles.values()]
            voice_separation_score = min(1.0, ((max(bluntness_values) - min(bluntness_values)) + (max(restraint_values) - min(restraint_values))) / 2.0)
        else:
            voice_separation_score = 0.0
        if action_map:
            action_buckets = [len(slot_map.get("entry", []) + slot_map.get("pressure", []) + slot_map.get("pivot", []) + slot_map.get("aftermath", []) + slot_map.get("echo", [])) for slot_map in action_map.values()]
            emotion_action_specificity = min(1.0, sum(action_buckets) / float(max(1, len(action_buckets) * 8)))
        else:
            emotion_action_specificity = 0.0
        world_metrics = {
            "world_id": world_id,
            "pass_rate": evaluation.get("pass_rate", 0.0),
            "rewrite_rate": evaluation.get("rewrite_rate", 0.0),
            "block_rate": evaluation.get("block_rate", 0.0),
            "character_fidelity": round(character_fidelity, 3),
            "causal_continuity": round(causal_continuity, 3),
            "choice_distinctness": round(choice_distinctness, 3),
            "prose_leak_rate": round(prose_leak_rate, 3),
            "route_longevity": report.get("completed_chapters", 0),
            "route_longevity_target": max_chapters,
            "dialogue_ratio": round(dialogue_ratio, 3),
            "scene_detail_density": round(scene_detail_density, 3),
            "voice_separation_score": round(voice_separation_score, 3),
            "emotion_action_specificity": round(emotion_action_specificity, 3),
            "cross_pack_pass_rate": evaluation.get("pass_rate", 0.0),
            "issue_mix": issue_mix,
            "long_route_quality": route_diagnostics["long_route_quality"],
            "mid_arc_drop": route_diagnostics["mid_arc_drop"],
            "dialogue_distinctness": round(voice_separation_score, 3),
            **long_route_diagnostics,
        }
        world_metrics["top_issue_categories"] = list(evaluation.get("top_issue_categories", []))
        world_metrics["dimension_scores"] = build_dimension_scores(world_metrics)
        world_metrics["issue_summary"] = build_issue_summary(
            top_issue_categories=world_metrics["top_issue_categories"],
            dimension_scores=world_metrics["dimension_scores"],
            route_longevity_target=max_chapters,
        )
        worlds.append(world_metrics)
    worlds = assign_diagnostic_ranks(worlds)
    cross_pack_pass_rate = sum(item["pass_rate"] for item in worlds) / float(max(1, len(worlds)))
    strongest_packs = rank_strongest_packs(worlds)
    weakest_packs = rank_weakest_packs(worlds)
    weakest_pack_diagnostics = [
        build_weakest_pack_diagnostic(
            world_metrics=next(item for item in worlds if item["world_id"] == pack["world_id"]),
            chapter_report_payloads=chapter_reports_by_world.get(pack["world_id"], []),
            pack_payload=pack_payload_by_world.get(pack["world_id"], {}),
        )
        for pack in weakest_packs
    ]
    summary = {
        "golden_dir": str(golden_dir),
        "benchmark_mode": "long_route" if max_chapters > 6 else "standard",
        "chapter_budget": max_chapters,
        "min_end_turn_override": min_end_turn_override,
        "worlds": worlds,
        "cross_pack_pass_rate": round(cross_pack_pass_rate, 3),
        "strongest_packs": strongest_packs,
        "weakest_packs": weakest_packs,
        "top_failing_packs": rank_top_failing_packs(worlds),
        "weakest_pack_diagnostics": weakest_pack_diagnostics,
    }
    if max_chapters > 6:
        summary["long_route_summary"] = build_long_route_summary(worlds)
    if baseline:
        summary["delta_summary"] = benchmark_delta_report(summary, baseline)
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NarrativeOS cross-pack benchmark and emit capability metrics.")
    parser.add_argument("--worldpack", default="all")
    parser.add_argument("--golden-dir", default="tests/golden_routes")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--baseline-file", default="tests/benchmark_baseline.json")
    parser.add_argument("--markdown-out", default=None)
    parser.add_argument("--max-chapters", type=int, default=6)
    parser.add_argument("--min-end-turn-override", type=int, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    baseline_path = Path(args.baseline_file)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    repository = SQLAlchemyRepository(database_url=args.database_url)
    summary = run_benchmark(
        repository=repository,
        golden_dir=Path(args.golden_dir),
        worldpack=args.worldpack,
        baseline=baseline,
        max_chapters=int(args.max_chapters),
        min_end_turn_override=int(args.min_end_turn_override) if args.min_end_turn_override is not None else None,
    )
    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_benchmark_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
