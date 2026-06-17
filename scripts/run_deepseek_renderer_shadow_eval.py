from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.benchmark.runner import run_benchmark
from src.narrativeos.providers import LLMBackend, build_llm_backend_from_env
from src.narrativeos.rendering import TemplateRenderer
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.observability import ObservabilityService
from src.narrativeos.services.provider_routing import ProviderRoutingService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


TARGET_ISSUE_CODES = ("Q03", "Q04", "Q05", "Q09")
DEFAULT_WEAKEST_PACKS = (
    "jade_court_romance",
    "synthetic_min_pack",
    "urban_mystery_lotus_lane",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rate(count: int, total: int) -> float:
    return round(float(count) / float(max(1, int(total or 0))), 3)


def _percentile(values: Sequence[float], quantile: float) -> Optional[float]:
    cleaned = sorted(float(value) for value in values)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return round(cleaned[0], 3)
    rank = max(0.0, min(1.0, quantile)) * float(len(cleaned) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(cleaned) - 1)
    fraction = rank - lower
    return round(cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction, 3)


def _latency_summary(values: Sequence[Any]) -> Dict[str, Any]:
    cleaned: List[float] = []
    for value in values:
        try:
            if value is not None:
                cleaned.append(float(value))
        except (TypeError, ValueError):
            continue
    if not cleaned:
        return {
            "count": 0,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
            "max_latency_ms": None,
        }
    return {
        "count": len(cleaned),
        "avg_latency_ms": round(sum(cleaned) / float(len(cleaned)), 3),
        "p95_latency_ms": _percentile(cleaned, 0.95),
        "max_latency_ms": round(max(cleaned), 3),
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _world_lookup(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("world_id") or ""): dict(item)
        for item in list(summary.get("worlds") or [])
        if str(item.get("world_id") or "").strip()
    }


def _issue_counts(world: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {code: 0 for code in TARGET_ISSUE_CODES}
    sources = list(world.get("top_issue_categories") or world.get("issue_mix") or [])
    for item in sources:
        code = str(dict(item).get("issue_code") or "")
        if code in counts:
            counts[code] += _safe_int(dict(item).get("count"))
    return counts


def _chapter_count(world: Dict[str, Any]) -> int:
    return max(
        1,
        _safe_int(world.get("route_longevity"))
        or _safe_int(world.get("completed_chapters"))
        or _safe_int(world.get("route_longevity_target"))
        or _safe_int(world.get("chapter_budget")),
    )


def build_issue_delta_summary(
    *,
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    target_worlds: Sequence[str],
) -> Dict[str, Any]:
    current_worlds = _world_lookup(current)
    baseline_worlds = _world_lookup(baseline)
    world_deltas: List[Dict[str, Any]] = []
    aggregate_before = {code: 0 for code in TARGET_ISSUE_CODES}
    aggregate_after = {code: 0 for code in TARGET_ISSUE_CODES}
    aggregate_before_chapters = 0
    aggregate_after_chapters = 0
    for world_id in target_worlds:
        before_world = baseline_worlds.get(world_id, {})
        after_world = current_worlds.get(world_id, {})
        before_counts = _issue_counts(before_world)
        after_counts = _issue_counts(after_world)
        before_chapters = _chapter_count(before_world)
        after_chapters = _chapter_count(after_world)
        aggregate_before_chapters += before_chapters
        aggregate_after_chapters += after_chapters
        issue_deltas: Dict[str, Dict[str, Any]] = {}
        for code in TARGET_ISSUE_CODES:
            before_count = before_counts.get(code, 0)
            after_count = after_counts.get(code, 0)
            aggregate_before[code] += before_count
            aggregate_after[code] += after_count
            before_rate = _rate(before_count, before_chapters)
            after_rate = _rate(after_count, after_chapters)
            issue_deltas[code] = {
                "before_count": before_count,
                "after_count": after_count,
                "count_delta": after_count - before_count,
                "before_rate": before_rate,
                "after_rate": after_rate,
                "rate_delta": round(after_rate - before_rate, 3),
            }
        world_deltas.append(
            {
                "world_id": world_id,
                "before_completed_chapters": before_chapters,
                "after_completed_chapters": after_chapters,
                "before_pass_rate": before_world.get("pass_rate"),
                "after_pass_rate": after_world.get("pass_rate"),
                "before_completion_ratio": before_world.get("completion_ratio"),
                "after_completion_ratio": after_world.get("completion_ratio"),
                "before_stop_reason": before_world.get("stop_reason"),
                "after_stop_reason": after_world.get("stop_reason"),
                "issue_deltas": issue_deltas,
            }
        )
    aggregate = {}
    for code in TARGET_ISSUE_CODES:
        before_rate = _rate(aggregate_before[code], aggregate_before_chapters)
        after_rate = _rate(aggregate_after[code], aggregate_after_chapters)
        aggregate[code] = {
            "before_count": aggregate_before[code],
            "after_count": aggregate_after[code],
            "count_delta": aggregate_after[code] - aggregate_before[code],
            "before_rate": before_rate,
            "after_rate": after_rate,
            "rate_delta": round(after_rate - before_rate, 3),
        }
    return {
        "issue_codes": list(TARGET_ISSUE_CODES),
        "target_worlds": list(target_worlds),
        "aggregate": aggregate,
        "world_deltas": world_deltas,
    }


def _summarize_receipt_subset(receipts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    receipt_count = len(receipts)
    fallback_count = sum(1 for item in receipts if item.get("fallback_used"))
    length_retry_count = sum(
        1
        for item in receipts
        if bool(item.get("renderer_length_retry_used")) or _safe_int(item.get("renderer_attempt_count")) > 1
    )
    renderer_attempt_total = sum(_safe_int(item.get("renderer_attempt_count")) for item in receipts)
    selected_renderer_providers = Counter(str(item.get("renderer_selected_provider") or "unknown") for item in receipts)
    fallback_reasons = Counter(
        str(item.get("renderer_fallback_reason") or "none")
        for item in receipts
        if item.get("fallback_used") or item.get("renderer_fallback_reason")
    )
    backend_errors = Counter(
        str(item.get("renderer_backend_error") or item.get("backend_error") or "none")
        for item in receipts
        if item.get("renderer_backend_error") or item.get("backend_error")
    )
    return {
        "receipt_count": receipt_count,
        "deepseek_selected_count": selected_renderer_providers.get("deepseek", 0),
        "fallback_count": fallback_count,
        "fallback_rate": _rate(fallback_count, receipt_count),
        "length_retry_count": length_retry_count,
        "length_retry_rate": _rate(length_retry_count, receipt_count),
        "avg_renderer_attempt_count": round(float(renderer_attempt_total) / float(max(1, receipt_count)), 3),
        "selected_renderer_providers": dict(sorted(selected_renderer_providers.items())),
        "renderer_fallback_reasons": dict(sorted(fallback_reasons.items())),
        "renderer_backend_errors": dict(sorted(backend_errors.items())),
        "renderer_latency": _latency_summary([item.get("renderer_latency_ms") for item in receipts]),
    }


def build_receipt_metrics(
    *,
    receipts: Sequence[Dict[str, Any]],
    target_worlds: Sequence[str],
) -> Dict[str, Any]:
    filtered = [
        dict(item)
        for item in receipts
        if not target_worlds or str(item.get("world_id") or "") in set(target_worlds)
    ]
    return {
        "global": _summarize_receipt_subset(filtered),
        "by_world": {
            world_id: _summarize_receipt_subset(
                [item for item in filtered if str(item.get("world_id") or "") == world_id]
            )
            for world_id in target_worlds
        },
    }


def build_shadow_provider_routing(renderer_backend: LLMBackend) -> ProviderRoutingService:
    return ProviderRoutingService(
        candidate_backend=None,
        renderer_backend=renderer_backend,
        fallback_renderer=TemplateRenderer(),
    )


@contextmanager
def _temporary_env(overrides: Dict[str, str]) -> Iterator[None]:
    sentinel = object()
    previous: Dict[str, Any] = {key: os.environ.get(key, sentinel) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)


def _model_slug(model: str) -> str:
    return str(model).replace("/", "_").replace(":", "_")


def _build_markdown_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# DeepSeek V4 Renderer Shadow Eval",
        "",
        "- generated_at: %s" % summary.get("generated_at"),
        "- target_worlds: %s" % ", ".join(summary.get("target_worlds") or []),
        "- max_chapters: %s" % summary.get("max_chapters"),
        "- rollback_point: remove `deepseek` from renderer provider order",
        "- recommendation: %s" % summary.get("recommendation"),
        "",
    ]
    for model_report in summary.get("model_reports", []):
        metrics = dict(dict(model_report.get("receipt_metrics") or {}).get("global") or {})
        lines.extend(
            [
                "## %s" % model_report.get("model"),
                "",
                "- receipts: %s" % metrics.get("receipt_count", 0),
                "- deepseek_selected_count: %s" % metrics.get("deepseek_selected_count", 0),
                "- fallback_rate: %.3f" % float(metrics.get("fallback_rate", 0.0) or 0.0),
                "- length_retry_rate: %.3f" % float(metrics.get("length_retry_rate", 0.0) or 0.0),
                "- renderer_latency_avg_ms: %s" % dict(metrics.get("renderer_latency") or {}).get("avg_latency_ms"),
                "",
                "### Q03/Q04/Q05/Q09 Aggregate Deltas",
                "",
            ]
        )
        aggregate = dict(dict(model_report.get("issue_delta_summary") or {}).get("aggregate") or {})
        for code in TARGET_ISSUE_CODES:
            item = dict(aggregate.get(code) or {})
            lines.append(
                "- %s: count %s -> %s (%+d), rate %.3f -> %.3f (%+.3f)"
                % (
                    code,
                    item.get("before_count", 0),
                    item.get("after_count", 0),
                    int(item.get("count_delta", 0) or 0),
                    float(item.get("before_rate", 0.0) or 0.0),
                    float(item.get("after_rate", 0.0) or 0.0),
                    float(item.get("rate_delta", 0.0) or 0.0),
                )
            )
        lines.extend(["", "### Per World", ""])
        for world in dict(model_report.get("receipt_metrics") or {}).get("by_world", {}):
            world_metrics = dict(dict(model_report.get("receipt_metrics") or {}).get("by_world", {}).get(world) or {})
            lines.append(
                "- %s: fallback %.3f, length_retry %.3f, receipts %s"
                % (
                    world,
                    float(world_metrics.get("fallback_rate", 0.0) or 0.0),
                    float(world_metrics.get("length_retry_rate", 0.0) or 0.0),
                    world_metrics.get("receipt_count", 0),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _recommendation(model_reports: Sequence[Dict[str, Any]]) -> str:
    if not model_reports:
        return "rollback_renderer_order_no_eval"
    for report in model_reports:
        metrics = dict(dict(report.get("receipt_metrics") or {}).get("global") or {})
        if int(metrics.get("receipt_count", 0) or 0) <= 0:
            return "rollback_renderer_order_no_receipts"
        if int(metrics.get("deepseek_selected_count", 0) or 0) <= 0:
            return "rollback_renderer_order_deepseek_not_selected"
    if any(
        float(dict(dict(report.get("receipt_metrics") or {}).get("global") or {}).get("fallback_rate", 0.0) or 0.0) > 0.2
        or float(dict(dict(report.get("receipt_metrics") or {}).get("global") or {}).get("length_retry_rate", 0.0) or 0.0) > 0.2
        for report in model_reports
    ):
        return "stay_shadow_high_fallback_or_length_retry"
    for report in model_reports:
        aggregate = dict(dict(report.get("issue_delta_summary") or {}).get("aggregate") or {})
        if any(int(dict(aggregate.get(code) or {}).get("count_delta", 0) or 0) > 0 for code in TARGET_ISSUE_CODES):
            return "stay_shadow_target_issue_regression"
    return "eligible_for_canary_review_after_human_sample"


def _compact_model_report(report: Dict[str, Any]) -> Dict[str, Any]:
    benchmark = dict(report.get("benchmark_summary") or {})
    return {
        "model": report.get("model"),
        "generated_at": report.get("generated_at"),
        "target_worlds": list(report.get("target_worlds") or []),
        "max_chapters": report.get("max_chapters"),
        "artifact_path": report.get("artifact_path"),
        "database_url": report.get("database_url"),
        "golden_dir": report.get("golden_dir"),
        "receipt_metrics": dict(report.get("receipt_metrics") or {}),
        "issue_delta_summary": dict(report.get("issue_delta_summary") or {}),
        "benchmark_digest": {
            "benchmark_mode": benchmark.get("benchmark_mode"),
            "acceptance_profile": benchmark.get("acceptance_profile"),
            "chapter_budget": benchmark.get("chapter_budget"),
            "cross_pack_pass_rate": benchmark.get("cross_pack_pass_rate"),
            "weakest_packs": list(benchmark.get("weakest_packs") or []),
            "strongest_packs": list(benchmark.get("strongest_packs") or []),
            "phase_a_quality_gate": dict(benchmark.get("phase_a_quality_gate") or {}),
        },
    }


def run_model_eval(
    *,
    model: str,
    target_worlds: Sequence[str],
    baseline: Dict[str, Any],
    output_dir: Path,
    max_chapters: int,
    acceptance_profile: str,
    benchmark_mode: Optional[str],
    renderer_max_attempts: int,
) -> Dict[str, Any]:
    model_dir = output_dir / _model_slug(model)
    model_dir.mkdir(parents=True, exist_ok=True)
    database_url = "sqlite:///%s" % (model_dir / "shadow_eval.sqlite3")
    repository = SQLAlchemyRepository(database_url=database_url)
    registry = FileSystemWorldRegistry()
    observability = ObservabilityService(repository)

    env_overrides = {
        "NARRATIVEOS_DEEPSEEK_MODEL": model,
        "NARRATIVEOS_LLM_RENDERER_PROVIDER_ORDER": "deepseek,local",
        "NARRATIVEOS_LLM_RENDERER_CACHE_ENABLED": "false",
        "NARRATIVEOS_LLM_RENDERER_MAX_ATTEMPTS": str(max(1, int(renderer_max_attempts or 1))),
        "NARRATIVEOS_LLM_CANDIDATE_PROVIDER_ORDER": "local",
    }
    with _temporary_env(env_overrides):
        renderer_backend = build_llm_backend_from_env(scope="renderer")
        if renderer_backend is None:
            raise RuntimeError("renderer backend did not initialize; check DEEPSEEK_API_KEY and provider order")
        provider_routing = build_shadow_provider_routing(renderer_backend)
        authoring = AuthoringService(
            repository,
            registry=registry,
            provider_routing_service=provider_routing,
            observability_service=observability,
        )

        def simulation_runner(_world_id: str, world_version_id: str) -> Dict[str, Any]:
            return authoring.run_simulation_for_world_version(
                world_version_id,
                include_cross_pack=False,
                max_chapters=max_chapters,
            )

        benchmark_summary = run_benchmark(
            repository=repository,
            golden_dir=model_dir / "goldens",
            worldpack=list(target_worlds),
            baseline=baseline,
            simulation_runner=simulation_runner,
            benchmark_mode=benchmark_mode,
            max_chapters=max_chapters,
            acceptance_profile=acceptance_profile,
            fast_gate_weakest_limit=len(target_worlds),
        )

    receipts = observability.list_runtime_receipts(limit=max(500, max_chapters * len(target_worlds) * 4))
    if not receipts:
        raise RuntimeError("shadow eval produced no runtime receipts for %s" % model)
    receipt_metrics = build_receipt_metrics(receipts=receipts, target_worlds=target_worlds)
    if int(dict(receipt_metrics["global"]).get("deepseek_selected_count", 0) or 0) <= 0:
        raise RuntimeError("DeepSeek was not selected as renderer for %s" % model)

    model_report = {
        "model": model,
        "generated_at": _utcnow(),
        "target_worlds": list(target_worlds),
        "max_chapters": max_chapters,
        "database_url": database_url,
        "golden_dir": str(model_dir / "goldens"),
        "benchmark_summary": benchmark_summary,
        "issue_delta_summary": build_issue_delta_summary(
            current=benchmark_summary,
            baseline=baseline,
            target_worlds=target_worlds,
        ),
        "receipt_metrics": receipt_metrics,
        "provider_runtime_metrics": observability.provider_runtime_metrics(limit=max(500, len(receipts) * 2)),
    }
    json_path = model_dir / "shadow_eval_summary.json"
    model_report["artifact_path"] = str(json_path)
    _write_json(json_path, model_report)
    return model_report


def build_combined_report(
    *,
    model_reports: Sequence[Dict[str, Any]],
    target_worlds: Sequence[str],
    max_chapters: int,
    output_dir: Path,
) -> Dict[str, Any]:
    recommendation = _recommendation(model_reports)
    compact_reports = [_compact_model_report(dict(item)) for item in model_reports]
    report = {
        "generated_at": _utcnow(),
        "target_worlds": list(target_worlds),
        "max_chapters": max_chapters,
        "model_reports": compact_reports,
        "comparison": {
            str(item.get("model")): {
                "fallback_rate": dict(dict(item.get("receipt_metrics") or {}).get("global") or {}).get("fallback_rate"),
                "length_retry_rate": dict(dict(item.get("receipt_metrics") or {}).get("global") or {}).get("length_retry_rate"),
                "deepseek_selected_count": dict(dict(item.get("receipt_metrics") or {}).get("global") or {}).get("deepseek_selected_count"),
                "q_deltas": dict(dict(item.get("issue_delta_summary") or {}).get("aggregate") or {}),
            }
            for item in model_reports
        },
        "recommendation": recommendation,
        "rollback_point": "remove deepseek from NARRATIVEOS_LLM_RENDERER_PROVIDER_ORDER",
    }
    json_path = output_dir / "deepseek_v4_renderer_shadow_eval.json"
    markdown_path = output_dir / "deepseek_v4_renderer_shadow_eval.md"
    report["artifact_paths"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
    _write_json(json_path, report)
    markdown_path.write_text(_build_markdown_report(report), encoding="utf-8")
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run DeepSeek V4 renderer shadow eval on weakest packs.")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--worldpack", action="append", default=[])
    parser.add_argument("--baseline-file", default="tests/benchmark_baseline.json")
    parser.add_argument("--max-chapters", type=int, default=6)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--acceptance-profile", choices=["fast", "nightly", "full"], default="fast")
    parser.add_argument("--benchmark-mode", default=None)
    parser.add_argument("--renderer-max-attempts", type=int, default=1)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is required and must be supplied via the shell environment")

    models = [str(item).strip() for item in args.model if str(item).strip()] or [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    target_worlds = [str(item).strip() for item in args.worldpack if str(item).strip()] or list(DEFAULT_WEAKEST_PACKS)
    baseline_path = Path(args.baseline_file)
    baseline = _load_json(baseline_path) if baseline_path.exists() else {}
    run_root = Path(args.output_dir) / (args.run_id or _run_id())
    run_root.mkdir(parents=True, exist_ok=True)

    model_reports = [
        run_model_eval(
            model=model,
            target_worlds=target_worlds,
            baseline=baseline,
            output_dir=run_root,
            max_chapters=int(args.max_chapters),
            acceptance_profile=str(args.acceptance_profile),
            benchmark_mode=str(args.benchmark_mode) if args.benchmark_mode else None,
            renderer_max_attempts=int(args.renderer_max_attempts),
        )
        for model in models
    ]
    combined = build_combined_report(
        model_reports=model_reports,
        target_worlds=target_worlds,
        max_chapters=int(args.max_chapters),
        output_dir=run_root,
    )
    print(json.dumps(combined, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
