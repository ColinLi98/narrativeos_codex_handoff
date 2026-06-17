from pathlib import Path

import yaml

from src.narrativeos.quality.config import (
    QualityConfigError,
    QualityConfigPaths,
    load_quality_config_bundle,
)


def test_quality_config_bundle_loads_default_configs():
    bundle = load_quality_config_bundle()

    assert bundle["scenarios"]["config_version"] == "quality_scenarios_v1"
    assert bundle["risk_tiers"]["config_version"] == "quality_risk_tiers_v1"
    assert bundle["rules"]["config_version"] == "quality_rules_v1"
    assert bundle["content_rubrics"]["config_version"] == "content_rubrics_v1"
    assert bundle["review_policies"]["config_version"] == "quality_review_policies_v1"
    assert bundle["review_policies"]["policy_map"]["qp_reader_continue_v1"].scenario_id == "reader_continue"


def test_quality_config_bundle_rejects_missing_required_keys(tmp_path: Path):
    config_dir = tmp_path / "quality"
    config_dir.mkdir()
    (config_dir / "scenarios.yaml").write_text(
        "config_version: x\nscenarios:\n  - scenario_id: reader_continue\n    surface: reader\n    description: desc\n    default_risk_tier: L1\n    quality_policy_id: missing_policy\n",
        encoding="utf-8",
    )
    (config_dir / "risk_tiers.yaml").write_text(
        "config_version: x\nrisk_tiers:\n  - risk_tier: L1\n    label: low\n    description: desc\n    requires_human_review: false\n    blocks_on_veto_only: true\n",
        encoding="utf-8",
    )
    (config_dir / "rules.yaml").write_text(
        "config_version: x\nrules:\n  - rule_id: rule_1\n    rule_type: validator\n    severity: high\n    blocking: true\n    config_ref: config\n    reason_code: reason\n",
        encoding="utf-8",
    )
    (config_dir / "content_rubrics.yaml").write_text(
        "config_version: x\nrubrics: {default: {rubric_version: v1, overall_scale: {min: 1, max: 5}, dimensions: {correctness: {min: 1, max: 5}}, veto_reason_codes: []}}\n",
        encoding="utf-8",
    )
    (config_dir / "review_policies.yaml").write_text("config_version: x\npolicies: []\n", encoding="utf-8")

    try:
        load_quality_config_bundle(QualityConfigPaths(config_dir=config_dir))
    except QualityConfigError as exc:
        assert "quality_scenario_missing_policy" in str(exc)
    else:
        raise AssertionError("invalid config bundle should raise")


def test_quality_config_bundle_rejects_invalid_risk_tier(tmp_path: Path):
    config_dir = tmp_path / "quality"
    config_dir.mkdir()
    (config_dir / "scenarios.yaml").write_text(
        yaml.safe_dump(
            {
                "config_version": "test",
                "scenarios": [
                    {
                        "scenario_id": "reader_continue",
                        "surface": "reader",
                        "description": "desc",
                        "default_risk_tier": "L9",
                        "quality_policy_id": "qp_reader_continue_v1",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "risk_tiers.yaml").write_text(
        yaml.safe_dump(
            {
                "config_version": "test",
                "risk_tiers": [
                    {
                        "risk_tier": "L1",
                        "label": "low",
                        "description": "desc",
                        "requires_human_review": False,
                        "blocks_on_veto_only": True,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "rules.yaml").write_text(
        yaml.safe_dump(
            {
                "config_version": "test",
                "rules": [
                    {
                        "rule_id": "rule_1",
                        "rule_type": "validator",
                        "severity": "high",
                        "blocking": True,
                        "config_ref": "config",
                        "reason_code": "reason",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "content_rubrics.yaml").write_text(
        yaml.safe_dump(
            {
                "config_version": "test",
                "rubrics": {
                    "default": {
                        "rubric_version": "v1",
                        "overall_scale": {"min": 1, "max": 5},
                        "dimensions": {"correctness": {"min": 1, "max": 5}},
                        "veto_reason_codes": [],
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "review_policies.yaml").write_text(
        yaml.safe_dump(
            {
                "config_version": "test",
                "policies": [
                    {
                        "policy_id": "qp_reader_continue_v1",
                        "version": "v1",
                        "scenario_id": "reader_continue",
                        "risk_tier": "L1",
                        "rule_ids": ["rule_1"],
                        "mode": "observe",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    try:
        load_quality_config_bundle(QualityConfigPaths(config_dir=config_dir))
    except QualityConfigError as exc:
        assert "quality_scenario_risk_tier_invalid" in str(exc)
    else:
        raise AssertionError("invalid scenario risk tier should raise")
