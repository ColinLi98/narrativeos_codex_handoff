from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from src.narrativeos.providers import InlineJSONLLMBackend


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_deepseek_renderer_shadow_eval.py"


def _load_script_module():
    spec = spec_from_file_location("deepseek_renderer_shadow_eval", SCRIPT_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shadow_eval_builds_issue_delta_summary_for_target_codes():
    module = _load_script_module()
    summary = module.build_issue_delta_summary(
        baseline={
            "worlds": [
                {
                    "world_id": "jade_court_romance",
                    "route_longevity": 3,
                    "pass_rate": 0.667,
                    "top_issue_categories": [
                        {"issue_code": "Q04", "count": 2},
                        {"issue_code": "Q05", "count": 1},
                    ],
                }
            ]
        },
        current={
            "worlds": [
                {
                    "world_id": "jade_court_romance",
                    "route_longevity": 4,
                    "pass_rate": 1.0,
                    "top_issue_categories": [
                        {"issue_code": "Q03", "count": 1},
                        {"issue_code": "Q05", "count": 0},
                    ],
                }
            ]
        },
        target_worlds=["jade_court_romance"],
    )

    aggregate = summary["aggregate"]
    assert aggregate["Q04"]["count_delta"] == -2
    assert aggregate["Q05"]["count_delta"] == -1
    assert aggregate["Q03"]["count_delta"] == 1
    assert summary["world_deltas"][0]["after_pass_rate"] == 1.0


def test_shadow_eval_receipt_metrics_track_fallback_and_length_retry():
    module = _load_script_module()
    receipts = [
        {
            "world_id": "jade_court_romance",
            "renderer_selected_provider": "deepseek",
            "fallback_used": False,
            "renderer_attempt_count": 1,
            "renderer_latency_ms": 1200.0,
        },
        {
            "world_id": "jade_court_romance",
            "renderer_selected_provider": "deepseek",
            "fallback_used": True,
            "renderer_fallback_reason": "invalid_llm_payload",
            "renderer_attempt_count": 2,
            "llm_payload_gate": {"ok": False},
            "renderer_latency_ms": 2400.0,
        },
        {
            "world_id": "synthetic_min_pack",
            "renderer_selected_provider": "local_rule_based",
            "fallback_used": True,
            "renderer_fallback_reason": "llm_backend_error",
            "renderer_attempt_count": 1,
        },
    ]

    metrics = module.build_receipt_metrics(
        receipts=receipts,
        target_worlds=["jade_court_romance", "synthetic_min_pack"],
    )

    assert metrics["global"]["receipt_count"] == 3
    assert metrics["global"]["deepseek_selected_count"] == 2
    assert metrics["global"]["fallback_rate"] == 0.667
    assert metrics["global"]["length_retry_rate"] == 0.333
    assert metrics["by_world"]["jade_court_romance"]["length_retry_rate"] == 0.5
    assert metrics["global"]["renderer_fallback_reasons"]["invalid_llm_payload"] == 1


def test_shadow_eval_provider_routing_keeps_candidate_static():
    module = _load_script_module()
    backend = InlineJSONLLMBackend({"concise_summary": "", "interactive_scene": "", "premium_prose": ""})
    routing = module.build_shadow_provider_routing(backend)

    candidate_decision = routing.resolve_track(track="candidate", surface="shadow_eval")
    renderer_decision = routing.resolve_track(track="renderer", surface="shadow_eval")

    assert routing.candidate_backend is None
    assert routing.renderer_backend is backend
    assert candidate_decision["enabled"] is False
    assert candidate_decision["fallback_only"] is True
    assert renderer_decision["enabled"] is True


def test_shadow_eval_combined_report_writes_json_and_markdown(tmp_path):
    module = _load_script_module()
    model_report = {
        "model": "deepseek-v4-flash",
        "receipt_metrics": {
            "global": {
                "receipt_count": 2,
                "deepseek_selected_count": 2,
                "fallback_rate": 0.0,
                "length_retry_rate": 0.0,
                "renderer_latency": {"avg_latency_ms": 1000.0},
            },
            "by_world": {"jade_court_romance": {"receipt_count": 2, "fallback_rate": 0.0, "length_retry_rate": 0.0}},
        },
        "issue_delta_summary": {
            "aggregate": {
                "Q03": {"before_count": 0, "after_count": 0, "count_delta": 0, "before_rate": 0.0, "after_rate": 0.0, "rate_delta": 0.0},
                "Q04": {"before_count": 2, "after_count": 1, "count_delta": -1, "before_rate": 0.667, "after_rate": 0.25, "rate_delta": -0.417},
                "Q05": {"before_count": 1, "after_count": 0, "count_delta": -1, "before_rate": 0.333, "after_rate": 0.0, "rate_delta": -0.333},
                "Q09": {"before_count": 0, "after_count": 0, "count_delta": 0, "before_rate": 0.0, "after_rate": 0.0, "rate_delta": 0.0},
            }
        },
    }

    report = module.build_combined_report(
        model_reports=[model_report],
        target_worlds=["jade_court_romance"],
        max_chapters=6,
        output_dir=tmp_path,
    )

    assert report["recommendation"] == "eligible_for_canary_review_after_human_sample"
    assert (tmp_path / "deepseek_v4_renderer_shadow_eval.json").exists()
    assert (tmp_path / "deepseek_v4_renderer_shadow_eval.md").read_text(encoding="utf-8").startswith("# DeepSeek")


def test_shadow_eval_fails_fast_without_api_key(monkeypatch, tmp_path):
    module = _load_script_module()
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="DEEPSEEK_API_KEY"):
        module.main(["--output-dir", str(tmp_path)])
