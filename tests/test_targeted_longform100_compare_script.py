from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_targeted_longform100_compare.py"


def _load_script_module():
    spec = spec_from_file_location("targeted_longform100_compare", SCRIPT_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_targeted_longform100_compare_script_builds_delta_summary():
    module = _load_script_module()
    summary = module.build_targeted_compare_summary(
        before={
            "worlds": [
                {
                    "world_id": "urban_mystery_lotus_lane",
                    "world_version_id": "urban_mystery_lotus_lane@0.1.0",
                    "pass_rate": 0.7,
                    "rewrite_rate": 0.3,
                    "block_rate": 0.0,
                    "diagnostic_rank": 2,
                    "diagnostic_score": 0.12,
                    "top_issue_categories": [{"issue_code": "Q03", "count": 12}, {"issue_code": "Q09", "count": 4}],
                    "continuation_calibration": {"q03": {"recommendation": "insufficient_coverage"}, "q09": {"recommendation": "insufficient_coverage"}, "sample_count": 0, "sample_gap": 8},
                }
            ]
        },
        after={
            "worlds": [
                {
                    "world_id": "urban_mystery_lotus_lane",
                    "world_version_id": "urban_mystery_lotus_lane@0.1.0",
                    "pass_rate": 0.8,
                    "rewrite_rate": 0.2,
                    "block_rate": 0.0,
                    "diagnostic_rank": 1,
                    "diagnostic_score": 0.09,
                    "top_issue_categories": [{"issue_code": "Q03", "count": 8}, {"issue_code": "Q09", "count": 2}],
                    "continuation_calibration": {"q03": {"recommendation": "hold"}, "q09": {"recommendation": "tighten"}, "sample_count": 8, "sample_gap": 0},
                }
            ]
        },
        supplementation={
            "world_summaries": [
                {
                    "world_version_id": "urban_mystery_lotus_lane@0.1.0",
                    "after_signal_summary": {"sample_count": 8, "negative_count": 2},
                }
            ]
        },
        target_worlds=["urban_mystery_lotus_lane"],
    )
    delta = summary["world_deltas"][0]
    assert delta["before_q03_count"] == 12
    assert delta["after_q03_count"] == 8
    assert delta["before_calibration"]["q03_recommendation"] == "insufficient_coverage"
    assert delta["after_calibration"]["q03_recommendation"] == "hold"
    assert delta["after_calibration"]["q09_recommendation"] == "tighten"
