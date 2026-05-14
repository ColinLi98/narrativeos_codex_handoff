from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_CONTENT_QUALITY_CONTRACTS_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "content_quality_contracts.json"
)

DEFAULT_GENERATION_HARD_CONSTRAINTS: Dict[str, Any] = {
    "config_version": "generation_hard_constraints_v1",
    "repair_policy": "repair_once_then_fail_closed",
    "universal_rules": {
        "schema_complete": {
            "issue_code": "Q10",
            "action": "block",
            "summary": "Reader chapter payload must include non-empty title, body, and branch choices.",
        },
        "broken_slot": {
            "issue_code": "Q10",
            "action": "block",
            "summary": "Template slot fragments cannot reach persisted reader prose.",
        },
        "engineering_leak": {
            "issue_code": "Q01",
            "action": "block",
            "summary": "Reader-visible prose cannot expose engine fields, ids, or route notation.",
        },
        "meta_narration_leak": {
            "issue_code": "Q02",
            "action": "block",
            "summary": "Reader-visible prose cannot explain chapter construction or planning intent.",
        },
        "grounding_failed": {
            "issue_code": "Q07",
            "action": "block",
            "summary": "Failed grounding cannot be persisted as a passed quality result.",
        },
        "premature_terminal": {
            "issue_code": "Q09",
            "action": "block",
            "summary": "Premature terminal chapters are blocked before the configured route runway.",
        },
        "stock_refrain_budget": {
            "issue_code": "Q03",
            "action": "block",
            "summary": "Known long-route refrain phrases must stay under deterministic budgets.",
        },
        "choice_text_budget": {
            "issue_code": "Q08",
            "action": "block",
            "summary": "Branch choices must remain non-empty and distinct within the current chapter.",
        },
    },
    "base_thresholds": {
        "min_choice_count": 2,
        "min_body_text_units": 80,
        "stock_refrain_current_max": 2,
        "choice_text_current_max": 1,
    },
    "genre_profiles": {
        "mystery": {
            "aliases": ["urban_mystery", "detective", "suspense"],
            "threshold_overrides": {"stock_refrain_current_max": 2},
        },
        "romance": {
            "aliases": ["romance", "relationship"],
            "threshold_overrides": {"choice_text_current_max": 1},
        },
        "fantasy": {
            "aliases": ["fantasy", "xianxia", "wuxia"],
            "threshold_overrides": {},
        },
        "realist": {
            "aliases": ["realist", "contemporary", "slice_of_life"],
            "threshold_overrides": {},
        },
        "light_novel": {
            "aliases": ["light_novel", "web_serial"],
            "threshold_overrides": {"min_choice_count": 2},
        },
    },
    "length_profiles": {
        "long_route_30": {
            "min_chapters": 30,
            "threshold_overrides": {"stock_refrain_current_max": 2},
        },
        "long_route_50": {
            "min_chapters": 50,
            "threshold_overrides": {"stock_refrain_current_max": 2},
        },
    },
}

DEFAULT_CONTENT_QUALITY_CONTRACTS: Dict[str, Any] = {
    "config_version": "content_quality_contracts_v1",
    "rolling_window_size": 5,
    "full_chain_enforcement": True,
    "generation_hard_constraints": DEFAULT_GENERATION_HARD_CONSTRAINTS,
    "bands": {
        "100": {
            "enabled": True,
            "diagnostic_enabled": True,
            "gate_enforced": True,
            "thresholds": {
                "repetition_score_max": 0.20,
                "exposition_ratio_max": 0.52,
                "concrete_detail_density_min": 0.04,
                "dialogue_plus_action_ratio_min": 0.42,
                "late_window_hook_quality_min": 0.85,
                "q09_pre_end_max": 0.08,
            },
            "windows": {
                "early": {
                    "start": 1,
                    "end": 10,
                    "q03_q04_combined_breach_share_max": 0.45,
                },
                "mid": {
                    "start": 30,
                    "end": 60,
                    "repetition_breach_rate_max": 0.30,
                    "exposition_breach_rate_max": 0.30,
                    "detail_breach_rate_max": 0.35,
                },
                "late": {
                    "start": 80,
                    "end": 100,
                    "q09_breach_rate_max": 0.08,
                    "detail_breach_rate_max": 0.35,
                    "premature_terminal_forbidden": True,
                },
            },
            "enforcement_policy": {
                "Q03": "rewrite",
                "Q04": "rewrite",
                "Q05": "rewrite",
                "Q09_pre_end": "block",
                "rolling_repeat_escalation": "block",
                "rolling_exposition_escalation": "block",
            },
        },
        "200": {
            "enabled": False,
            "diagnostic_enabled": True,
            "gate_enforced": False,
            "thresholds": {
                "repetition_score_max": 0.18,
                "exposition_ratio_max": 0.50,
                "concrete_detail_density_min": 0.045,
                "dialogue_plus_action_ratio_min": 0.46,
                "late_window_hook_quality_min": 0.86,
                "q09_pre_end_max": 0.10,
            },
            "windows": {
                "early": {
                    "start": 1,
                    "end": 20,
                    "q03_q04_combined_breach_share_max": 0.40,
                },
                "mid": {
                    "start": 60,
                    "end": 140,
                    "repetition_breach_rate_max": 0.28,
                    "exposition_breach_rate_max": 0.28,
                    "detail_breach_rate_max": 0.32,
                },
                "late": {
                    "start": 160,
                    "end": 200,
                    "q09_breach_rate_max": 0.12,
                    "detail_breach_rate_max": 0.32,
                    "premature_terminal_forbidden": True,
                },
            },
            "enforcement_policy": {
                "Q03": "rewrite",
                "Q04": "rewrite",
                "Q05": "rewrite",
                "Q09_pre_end": "block",
                "rolling_repeat_escalation": "block",
                "rolling_exposition_escalation": "block",
            },
        },
        "250": {
            "enabled": False,
            "diagnostic_enabled": False,
            "gate_enforced": False,
            "thresholds": {
                "repetition_score_max": 0.20,
                "exposition_ratio_max": 0.52,
                "concrete_detail_density_min": 0.04,
                "dialogue_plus_action_ratio_min": 0.42,
                "late_window_hook_quality_min": 0.85,
                "q09_pre_end_max": 0.08,
            },
            "windows": {
                "early": {"start": 1, "end": 10, "q03_q04_combined_breach_share_max": 0.45},
                "mid": {"start": 30, "end": 60, "repetition_breach_rate_max": 0.30, "exposition_breach_rate_max": 0.30, "detail_breach_rate_max": 0.35},
                "late": {"start": 80, "end": 100, "q09_breach_rate_max": 0.08, "detail_breach_rate_max": 0.35, "premature_terminal_forbidden": True},
            },
            "enforcement_policy": {
                "Q03": "rewrite",
                "Q04": "rewrite",
                "Q05": "rewrite",
                "Q09_pre_end": "block",
                "rolling_repeat_escalation": "block",
                "rolling_exposition_escalation": "block",
            },
        },
        "500": {
            "enabled": False,
            "diagnostic_enabled": False,
            "gate_enforced": False,
            "thresholds": {
                "repetition_score_max": 0.20,
                "exposition_ratio_max": 0.52,
                "concrete_detail_density_min": 0.04,
                "dialogue_plus_action_ratio_min": 0.42,
                "late_window_hook_quality_min": 0.85,
                "q09_pre_end_max": 0.08,
            },
            "windows": {
                "early": {"start": 1, "end": 10, "q03_q04_combined_breach_share_max": 0.45},
                "mid": {"start": 30, "end": 60, "repetition_breach_rate_max": 0.30, "exposition_breach_rate_max": 0.30, "detail_breach_rate_max": 0.35},
                "late": {"start": 80, "end": 100, "q09_breach_rate_max": 0.08, "detail_breach_rate_max": 0.35, "premature_terminal_forbidden": True},
            },
            "enforcement_policy": {
                "Q03": "rewrite",
                "Q04": "rewrite",
                "Q05": "rewrite",
                "Q09_pre_end": "block",
                "rolling_repeat_escalation": "block",
                "rolling_exposition_escalation": "block",
            },
        },
        "1000": {
            "enabled": False,
            "diagnostic_enabled": False,
            "gate_enforced": False,
            "thresholds": {
                "repetition_score_max": 0.20,
                "exposition_ratio_max": 0.52,
                "concrete_detail_density_min": 0.04,
                "dialogue_plus_action_ratio_min": 0.42,
                "late_window_hook_quality_min": 0.85,
                "q09_pre_end_max": 0.08,
            },
            "windows": {
                "early": {"start": 1, "end": 10, "q03_q04_combined_breach_share_max": 0.45},
                "mid": {"start": 30, "end": 60, "repetition_breach_rate_max": 0.30, "exposition_breach_rate_max": 0.30, "detail_breach_rate_max": 0.35},
                "late": {"start": 80, "end": 100, "q09_breach_rate_max": 0.08, "detail_breach_rate_max": 0.35, "premature_terminal_forbidden": True},
            },
            "enforcement_policy": {
                "Q03": "rewrite",
                "Q04": "rewrite",
                "Q05": "rewrite",
                "Q09_pre_end": "block",
                "rolling_repeat_escalation": "block",
                "rolling_exposition_escalation": "block",
            },
        },
    },
}

SCENE_QUALITY_CONTRACT_KEYS = (
    "variation_axes",
    "detail_anchor_types",
    "dialogue_pressure",
    "continuation_obligation",
)
CHAPTER_TASK_QUALITY_CONTRACT_KEYS = (
    "delayed_payoff_window",
    "continuation_pressure_required",
    "max_exposition_ratio",
    "min_dialogue_action_ratio",
    "min_detail_density",
)
ISSUE_CONTRACT_PRIORITY = ("Q09", "Q05", "Q04", "Q03")
CONTRACT_CHECK_TO_ISSUE_CODE = {
    "repetition_score_cap": "Q03",
    "rolling_window_repeat_breach": "Q03",
    "event_coverage_gap_breach": "Q03",
    "beat_coverage_gap_breach": "Q03",
    "exposition_ratio_cap": "Q04",
    "dialogue_action_floor": "Q04",
    "rolling_window_exposition_breach": "Q04",
    "detail_density_floor": "Q05",
    "mid_window_detail_breach": "Q05",
    "late_window_detail_breach": "Q05",
    "continuation_pressure_floor": "Q09",
    "premature_terminal_forbidden": "Q09",
    "late_window_q09_breach": "Q09",
    "q09_pre_end": "Q09",
}
ISSUE_ASSET_TARGETS: Dict[str, Dict[str, str]] = {
    "Q03": {
        "asset_type": "scene_blueprint",
        "asset_label": "场景蓝图",
        "validation_panel": "compare",
        "validation_panel_label": "Compare",
    },
    "Q04": {
        "asset_type": "scene_blueprint",
        "asset_label": "场景蓝图",
        "validation_panel": "compare",
        "validation_panel_label": "Compare",
    },
    "Q05": {
        "asset_type": "scene_blueprint",
        "asset_label": "场景蓝图",
        "validation_panel": "compare",
        "validation_panel_label": "Compare",
    },
    "Q09": {
        "asset_type": "chapter_task",
        "asset_label": "章节任务",
        "validation_panel": "task_linking",
        "validation_panel_label": "Task Linking",
    },
}


def _deep_copy_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def load_content_quality_contracts(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_CONTENT_QUALITY_CONTRACTS_PATH
    payload = _deep_copy_json(DEFAULT_CONTENT_QUALITY_CONTRACTS)
    if config_path.exists():
        try:
            file_payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return payload
        if isinstance(file_payload, dict):
            payload.update({key: value for key, value in file_payload.items() if key != "bands"})
            if isinstance(file_payload.get("bands"), dict):
                payload["bands"] = {
                    str(key): dict(value or {})
                    for key, value in dict(file_payload.get("bands") or {}).items()
                }
    return payload


def content_quality_band_for_chapters(target_chapters: int) -> Optional[str]:
    chapter_count = max(0, int(target_chapters or 0))
    if chapter_count >= 1000:
        return "1000"
    if chapter_count >= 500:
        return "500"
    if chapter_count >= 250:
        return "250"
    if chapter_count >= 200:
        return "200"
    if chapter_count >= 100:
        return "100"
    return None


def resolve_content_quality_contract(
    *,
    target_chapters: int,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contracts = dict(config or load_content_quality_contracts())
    band = content_quality_band_for_chapters(target_chapters)
    band_payload = dict((contracts.get("bands") or {}).get(str(band), {}) or {})
    return {
        "config_version": str(contracts.get("config_version") or ""),
        "rolling_window_size": int(contracts.get("rolling_window_size", 5) or 5),
        "band": band,
        "enabled": bool(band_payload.get("enabled", False)) if band else False,
        "diagnostic_enabled": bool(band_payload.get("diagnostic_enabled", band_payload.get("enabled", False))) if band else False,
        "gate_enforced": bool(band_payload.get("gate_enforced", band_payload.get("enabled", False))) if band else False,
        "thresholds": dict(band_payload.get("thresholds") or {}),
        "windows": dict(band_payload.get("windows") or {}),
        "enforcement_policy": dict(band_payload.get("enforcement_policy") or {}),
        "full_chain_enforcement": bool(contracts.get("full_chain_enforcement", True)),
    }


def issue_asset_target(issue_code: str) -> Dict[str, str]:
    return dict(ISSUE_ASSET_TARGETS.get(str(issue_code or ""), {}))


def contract_issue_codes_from_failed_checks(failed_checks: Sequence[str]) -> List[str]:
    ordered: List[str] = []
    for check_name in list(failed_checks or []):
        issue_code = CONTRACT_CHECK_TO_ISSUE_CODE.get(str(check_name or ""))
        if issue_code and issue_code not in ordered:
            ordered.append(issue_code)
    return ordered


def is_quality_contract_applicable(worldpack_payload: Dict[str, Any], *, config: Optional[Dict[str, Any]] = None) -> bool:
    metadata = dict(worldpack_payload.get("metadata") or {})
    benchmark_enabled = bool(metadata.get("benchmark_enabled", metadata.get("catalog_role", "published") == "published"))
    target_chapters = int(
        ((worldpack_payload.get("series_plan") or {}).get("total_chapter_target"))
        or (((metadata.get("author_brief") or {}).get("target_total_chapters")) or 0)
        or 0
    )
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    return benchmark_enabled and target_chapters >= 100 and bool(
        contract.get("enabled", False) or contract.get("diagnostic_enabled", False)
    )


def _scene_dialogue_pressure(scene_function: str) -> str:
    high = {"truth_trial", "humiliation", "debt_exchange", "karma_ripening", "vow_payment"}
    medium = {"temptation", "mask_crack", "misrecognition", "confession_window"}
    normalized = str(scene_function or "")
    if normalized in high:
        return "high"
    if normalized in medium:
        return "medium"
    return "low"


def build_scene_quality_contract(
    *,
    scene_function: str,
    phase_support: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    normalized = str(scene_function or "")
    variation_axes = ["voice", "movement", "location_object", "consequence"]
    if normalized in {"misrecognition", "truth_trial", "confession_window"}:
        variation_axes.append("information_reveal")
    detail_anchor_types = ["object", "sound", "body_motion"]
    if normalized in {"false_peace", "temptation", "misrecognition"}:
        detail_anchor_types.append("ambient_signal")
    return {
        "variation_axes": variation_axes,
        "detail_anchor_types": detail_anchor_types,
        "dialogue_pressure": _scene_dialogue_pressure(normalized),
        "continuation_obligation": bool(phase_support or True),
    }


def build_chapter_task_quality_contract(
    *,
    duty_type: str,
    target_chapters: int,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    thresholds = dict(contract.get("thresholds") or {})
    delayed_payoff_window = {"min_chapters": 3, "max_chapters": 10}
    if duty_type == "resolve_promise":
        delayed_payoff_window = {"min_chapters": 1, "max_chapters": 4}
    elif duty_type == "deliver_climax":
        delayed_payoff_window = {"min_chapters": 1, "max_chapters": 5}
    elif duty_type == "pace_breath":
        delayed_payoff_window = {"min_chapters": 2, "max_chapters": 6}
    return {
        "delayed_payoff_window": delayed_payoff_window,
        "continuation_pressure_required": True,
        "max_exposition_ratio": float(thresholds.get("exposition_ratio_max", 0.52) or 0.52),
        "min_dialogue_action_ratio": float(thresholds.get("dialogue_plus_action_ratio_min", 0.42) or 0.42),
        "min_detail_density": float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04),
    }


def ensure_scene_quality_contract(scene_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(scene_payload or {})
    quality_contract = dict(payload.get("quality_contract") or {})
    if not quality_contract:
        quality_contract = build_scene_quality_contract(
            scene_function=str(payload.get("scene_function") or ""),
            phase_support=list(payload.get("phase_support") or []),
        )
    payload["quality_contract"] = quality_contract
    return payload


def ensure_chapter_task_quality_contract(
    task_payload: Dict[str, Any],
    *,
    target_chapters: int,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(task_payload or {})
    quality_contract = dict(payload.get("quality_contract") or {})
    if not quality_contract:
        quality_contract = build_chapter_task_quality_contract(
            duty_type=str(payload.get("duty_type") or ""),
            target_chapters=target_chapters,
            config=config,
        )
    payload["quality_contract"] = quality_contract
    return payload


def asset_quality_contract_coverage(
    worldpack_payload: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = dict(worldpack_payload.get("metadata") or {})
    target_chapters = int(
        ((worldpack_payload.get("series_plan") or {}).get("total_chapter_target"))
        or (((metadata.get("author_brief") or {}).get("target_total_chapters")) or 0)
        or 0
    )
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    applicable = is_quality_contract_applicable(worldpack_payload, config=config)
    scene_blueprints = [dict(item) for item in list(worldpack_payload.get("scene_blueprints") or [])]
    chapter_tasks = [
        dict(task)
        for arc in list(worldpack_payload.get("arc_plans") or [])
        for task in list(dict(arc or {}).get("chapter_tasks") or [])
    ]
    missing_scene_ids = [
        str(item.get("scene_id") or "")
        for item in scene_blueprints
        if any(key not in dict(item.get("quality_contract") or {}) for key in SCENE_QUALITY_CONTRACT_KEYS)
    ]
    missing_task_ids = [
        str(item.get("chapter_task_id") or "")
        for item in chapter_tasks
        if any(key not in dict(item.get("quality_contract") or {}) for key in CHAPTER_TASK_QUALITY_CONTRACT_KEYS)
    ]
    characters = [
        dict(item or {})
        for item in list(worldpack_payload.get("characters") or [])
        if str(dict(item or {}).get("character_id") or "").strip()
    ]
    character_ids = [str(item.get("character_id") or "") for item in characters]
    voice_profiles = dict(worldpack_payload.get("voice_profiles") or {})
    missing_voice_profile_character_ids = []
    for character in characters:
        character_id = str(character.get("character_id") or "").strip()
        role_key = str(character.get("role") or "").strip()
        if character_id in voice_profiles or (role_key and role_key in voice_profiles):
            continue
        if role_key and role_key not in {"lead", "counterpart"}:
            continue
        missing_voice_profile_character_ids.append(character_id)
    locations = [str(item).strip() for item in list((worldpack_payload.get("world_bible") or {}).get("locations") or []) if str(item).strip()]
    sensory_policies = dict(worldpack_payload.get("sensory_grounding_policies") or {})
    covered_locations = {
        str(location).strip()
        for policy in sensory_policies.values()
        for location in dict(policy or {}).get("location_slots", {})
        if str(location).strip()
    }
    missing_sensory_locations = [location for location in locations if location not in covered_locations]
    has_dialogue_realism_policy = bool(worldpack_payload.get("dialogue_realism_policy"))
    has_scene_realization_contracts = bool(worldpack_payload.get("scene_realization_contracts"))
    failed_checks: List[str] = []
    if applicable and missing_scene_ids:
        failed_checks.append("scene_blueprint_quality_contract_missing")
    if applicable and missing_task_ids:
        failed_checks.append("chapter_task_quality_contract_missing")
    if applicable and missing_voice_profile_character_ids:
        failed_checks.append("voice_profile_character_coverage_missing")
    if applicable and missing_sensory_locations:
        failed_checks.append("sensory_grounding_location_coverage_missing")
    if applicable and not has_dialogue_realism_policy:
        failed_checks.append("dialogue_realism_policy_missing")
    if applicable and not has_scene_realization_contracts:
        failed_checks.append("scene_realization_contracts_missing")
    return {
        "applicable": applicable,
        "band": contract.get("band"),
        "config_version": contract.get("config_version"),
        "diagnostic_enabled": bool(contract.get("diagnostic_enabled", False)),
        "gate_enforced": bool(contract.get("gate_enforced", False)),
        "ok": not failed_checks,
        "failed_checks": failed_checks,
        "scene_blueprint_count": len(scene_blueprints),
        "chapter_task_count": len(chapter_tasks),
        "scene_blueprint_quality_contract_coverage": len(scene_blueprints) - len(missing_scene_ids),
        "chapter_task_quality_contract_coverage": len(chapter_tasks) - len(missing_task_ids),
        "missing_scene_ids": missing_scene_ids,
        "missing_chapter_task_ids": missing_task_ids,
        "missing_voice_profile_character_ids": missing_voice_profile_character_ids,
        "missing_sensory_locations": missing_sensory_locations,
        "has_dialogue_realism_policy": has_dialogue_realism_policy,
        "has_scene_realization_contracts": has_scene_realization_contracts,
    }


def _window_label_for_chapter(chapter_index: int, windows: Dict[str, Any]) -> str:
    chapter = int(chapter_index or 0)
    for label in ("early", "mid", "late"):
        window = dict(windows.get(label) or {})
        start = int(window.get("start", 0) or 0)
        end = int(window.get("end", 0) or 0)
        if start and end and start <= chapter <= end:
            return label
    return "general"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _issue_codes_from_report(report: Any) -> List[str]:
    return [
        str(item.get("issue_code") or "")
        for item in list([issue.to_dict() for issue in list(report.issues or [])] if getattr(report, "issues", None) is not None else [])
        if str(item.get("issue_code") or "")
    ]


def diagnostic_issue_codes_for_chapter_payload(
    payload: Dict[str, Any],
    *,
    target_chapters: int,
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    if not (contract.get("enabled") or contract.get("diagnostic_enabled")):
        return []
    thresholds = dict(contract.get("thresholds") or {})
    windows = dict(contract.get("windows") or {})
    chapter_id = str(payload.get("chapter_id") or "")
    suffix = chapter_id.rsplit("_", 1)[-1]
    chapter_index = int(suffix) if suffix.isdigit() else 0
    issue_codes = {str(item.get("issue_code") or "") for item in list(payload.get("issues") or []) if str(item.get("issue_code") or "")}
    lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
    failed_checks: List[str] = []
    repetition_score = _safe_float(lint_metrics.get("repetition_score"))
    exposition_ratio = _safe_float(lint_metrics.get("exposition_ratio"))
    detail_density = _safe_float(lint_metrics.get("concrete_detail_density"))
    dialogue_ratio = _safe_float(lint_metrics.get("dialogue_plus_action_ratio"))
    hook_quality = _safe_float(((payload.get("scores") or {}).get("hook_quality")))
    repetition_bundle = dict(lint_metrics.get("repetition_signal_bundle") or {})
    if repetition_score > float(thresholds.get("repetition_score_max", 0.20) or 0.20):
        failed_checks.append("repetition_score_cap")
    if float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42:
        failed_checks.append("event_coverage_gap_breach")
    if float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35:
        failed_checks.append("beat_coverage_gap_breach")
    if exposition_ratio > float(thresholds.get("exposition_ratio_max", 0.52) or 0.52):
        failed_checks.append("exposition_ratio_cap")
    if detail_density < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
        failed_checks.append("detail_density_floor")
    if dialogue_ratio < float(thresholds.get("dialogue_plus_action_ratio_min", 0.42) or 0.42):
        failed_checks.append("dialogue_action_floor")
    if chapter_index < int(target_chapters * 0.96 or 0) and "Q09" in issue_codes:
        failed_checks.append("q09_pre_end")
    current_window_label = _window_label_for_chapter(chapter_index, windows)
    mid = dict(windows.get("mid") or {})
    late = dict(windows.get("late") or {})
    if current_window_label == "mid" and detail_density < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
        failed_checks.append("mid_window_detail_breach")
    if current_window_label == "late":
        if "Q09" in issue_codes:
            failed_checks.append("late_window_q09_breach")
        if detail_density < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
            failed_checks.append("late_window_detail_breach")
        if hook_quality < float(thresholds.get("late_window_hook_quality_min", 0.85) or 0.85):
            failed_checks.append("continuation_pressure_floor")
    return contract_issue_codes_from_failed_checks(failed_checks)


def next_quality_contract_window(
    rolling_quality_window: Sequence[Dict[str, Any]],
    *,
    chapter_index: int,
    decision: str,
    issue_codes: Sequence[str],
    repetition_score: float,
    exposition_ratio: float,
    concrete_detail_density: float,
    dialogue_plus_action_ratio: float,
    hook_quality: float,
    scene_function: str,
    chapter_task_id: str,
    window_size: int,
) -> List[Dict[str, Any]]:
    entries = [dict(item or {}) for item in rolling_quality_window][-max(0, int(window_size or 0)) :]
    entries.append(
        {
            "chapter_index": int(chapter_index or 0),
            "decision": str(decision or ""),
            "issue_codes": [str(item) for item in issue_codes if str(item)],
            "repetition_score": round(_safe_float(repetition_score), 3),
            "exposition_ratio": round(_safe_float(exposition_ratio), 3),
            "concrete_detail_density": round(_safe_float(concrete_detail_density), 3),
            "dialogue_plus_action_ratio": round(_safe_float(dialogue_plus_action_ratio), 3),
            "hook_quality": round(_safe_float(hook_quality), 3),
            "scene_function": str(scene_function or ""),
            "chapter_task_id": str(chapter_task_id or ""),
        }
    )
    return entries[-max(1, int(window_size or 1)) :]


def resolve_scene_quality_contract_from_coverage(coverage_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(coverage_context or {})
    scene_beats = list(payload.get("scene_beats") or [])
    for beat in scene_beats:
        scene_payload = dict(beat or {})
        if dict(scene_payload.get("quality_contract") or {}):
            return dict(scene_payload.get("quality_contract") or {})
    return {}


def resolve_scene_function_from_coverage(coverage_context: Optional[Dict[str, Any]]) -> str:
    payload = dict(coverage_context or {})
    scene_beats = list(payload.get("scene_beats") or [])
    for beat in scene_beats:
        event = dict(dict(beat or {}).get("event") or {})
        if str(event.get("scene_function") or ""):
            return str(event.get("scene_function") or "")
    return str(payload.get("scene_function") or "")


def resolve_chapter_task_quality_contract_from_coverage(coverage_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(coverage_context or {})
    chapter_task = dict(payload.get("chapter_task") or {})
    return dict(chapter_task.get("quality_contract") or {})


def evaluate_chapter_quality_contract(
    *,
    report: Any,
    chapter_index: int,
    target_chapters: int,
    story_phase: str,
    scene_quality_contract: Optional[Dict[str, Any]] = None,
    chapter_task_quality_contract: Optional[Dict[str, Any]] = None,
    rolling_quality_window: Optional[Sequence[Dict[str, Any]]] = None,
    scene_function: str = "",
    chapter_task_id: str = "",
    ending_ready: bool = False,
    enforcement_scope: str = "persisted_chapter",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    thresholds = dict(contract.get("thresholds") or {})
    windows = dict(contract.get("windows") or {})
    if not contract.get("enabled"):
        return {
            "enabled": False,
            "ok": True,
            "contract_checks": [],
            "contract_thresholds": {"config_version": contract.get("config_version"), "band": contract.get("band")},
            "failed_contract_checks": [],
            "primary_issue_group": "",
            "primary_asset_target": {},
            "window_breach_kind": "",
            "enforcement_scope": enforcement_scope,
            "quality_contract_window": list(rolling_quality_window or []),
        }

    lint_metrics = dict((report.hard_validator_results or {}).get("lint_metrics") or {})
    issue_codes = _issue_codes_from_report(report)
    repetition_score = _safe_float(lint_metrics.get("repetition_score"))
    exposition_ratio = _safe_float(lint_metrics.get("exposition_ratio"))
    detail_density = _safe_float(lint_metrics.get("concrete_detail_density"))
    dialogue_ratio = _safe_float(lint_metrics.get("dialogue_plus_action_ratio"))
    hook_quality = _safe_float(getattr(getattr(report, "scores", None), "hook_quality", 0.0))
    decision = str((getattr(report, "decision", None) or {}).decision if getattr(report, "decision", None) else "")
    chapter_task_contract = dict(chapter_task_quality_contract or {})
    window_size = int(contract.get("rolling_window_size", 5) or 5)
    quality_window = next_quality_contract_window(
        list(rolling_quality_window or []),
        chapter_index=chapter_index,
        decision=decision,
        issue_codes=issue_codes,
        repetition_score=repetition_score,
        exposition_ratio=exposition_ratio,
        concrete_detail_density=detail_density,
        dialogue_plus_action_ratio=dialogue_ratio,
        hook_quality=hook_quality,
        scene_function=str(scene_function or ""),
        chapter_task_id=str(chapter_task_id or ""),
        window_size=window_size,
    )
    current_window_label = _window_label_for_chapter(chapter_index, windows)
    repetition_cap = float(thresholds.get("repetition_score_max", 0.20) or 0.20)
    exposition_cap = float(chapter_task_contract.get("max_exposition_ratio", thresholds.get("exposition_ratio_max", 0.52)) or 0.52)
    detail_floor = float(chapter_task_contract.get("min_detail_density", thresholds.get("concrete_detail_density_min", 0.04)) or 0.04)
    dialogue_floor = float(chapter_task_contract.get("min_dialogue_action_ratio", thresholds.get("dialogue_plus_action_ratio_min", 0.42)) or 0.42)
    continuation_required = bool(chapter_task_contract.get("continuation_pressure_required", False) or dict(scene_quality_contract or {}).get("continuation_obligation", False))
    hook_floor = float(thresholds.get("late_window_hook_quality_min", 0.85) or 0.85)
    completion_ratio = round(int(chapter_index or 0) / float(max(1, int(target_chapters or 1))), 3)
    late_window = dict(windows.get("late") or {})
    late_window_entries = [
        item
        for item in quality_window
        if int(item.get("chapter_index", 0) or 0) >= int(late_window.get("start", target_chapters + 1) or target_chapters + 1)
    ]
    late_q09_rate = (
        sum(1 for item in late_window_entries if "Q09" in list(item.get("issue_codes") or []))
        / float(max(1, len(late_window_entries)))
        if late_window_entries
        else 0.0
    )
    recent_entries = quality_window[-2:]
    rolling_repeat_breach = len(recent_entries) == 2 and all(
        _safe_float(item.get("repetition_score")) > repetition_cap or "Q03" in list(item.get("issue_codes") or [])
        for item in recent_entries
    )
    rolling_exposition_breach = len(recent_entries) == 2 and all(
        _safe_float(item.get("exposition_ratio")) > exposition_cap or "Q04" in list(item.get("issue_codes") or [])
        for item in recent_entries
    )
    contract_checks = [
        {
            "name": "repetition_score_cap",
            "ok": repetition_score <= repetition_cap,
            "actual": round(repetition_score, 3),
            "threshold": round(repetition_cap, 3),
            "issue_code": "Q03",
            "window_label": current_window_label,
        },
        {
            "name": "exposition_ratio_cap",
            "ok": exposition_ratio <= exposition_cap,
            "actual": round(exposition_ratio, 3),
            "threshold": round(exposition_cap, 3),
            "issue_code": "Q04",
            "window_label": current_window_label,
        },
        {
            "name": "detail_density_floor",
            "ok": detail_density >= detail_floor,
            "actual": round(detail_density, 3),
            "threshold": round(detail_floor, 3),
            "issue_code": "Q05",
            "window_label": current_window_label,
        },
        {
            "name": "dialogue_action_floor",
            "ok": dialogue_ratio >= dialogue_floor,
            "actual": round(dialogue_ratio, 3),
            "threshold": round(dialogue_floor, 3),
            "issue_code": "Q04",
            "window_label": current_window_label,
        },
        {
            "name": "continuation_pressure_floor",
            "ok": (not continuation_required) or current_window_label != "late" or hook_quality >= hook_floor,
            "actual": round(hook_quality, 3),
            "threshold": round(hook_floor, 3),
            "issue_code": "Q09",
            "window_label": current_window_label,
            "applicable": continuation_required and current_window_label == "late",
        },
        {
            "name": "premature_terminal_forbidden",
            "ok": not ending_ready or completion_ratio >= 0.96,
            "actual": bool(ending_ready),
            "threshold": False,
            "issue_code": "Q09",
            "window_label": current_window_label,
        },
        {
            "name": "rolling_window_repeat_breach",
            "ok": not rolling_repeat_breach,
            "actual": rolling_repeat_breach,
            "threshold": False,
            "issue_code": "Q03",
            "window_label": current_window_label,
        },
        {
            "name": "rolling_window_exposition_breach",
            "ok": not rolling_exposition_breach,
            "actual": rolling_exposition_breach,
            "threshold": False,
            "issue_code": "Q04",
            "window_label": current_window_label,
        },
        {
            "name": "late_window_q09_breach",
            "ok": current_window_label != "late" or late_q09_rate <= float(late_window.get("q09_breach_rate_max", thresholds.get("q09_pre_end_max", 0.08)) or 0.08),
            "actual": round(late_q09_rate, 3),
            "threshold": round(float(late_window.get("q09_breach_rate_max", thresholds.get("q09_pre_end_max", 0.08)) or 0.08), 3),
            "issue_code": "Q09",
            "window_label": current_window_label,
        },
    ]
    failed_contract_checks = [item for item in contract_checks if not item.get("ok", True)]
    failed_issue_codes = [
        str(item.get("issue_code") or "")
        for item in failed_contract_checks
        if str(item.get("issue_code") or "")
    ]
    primary_issue_group = next((issue_code for issue_code in ISSUE_CONTRACT_PRIORITY if issue_code in failed_issue_codes), "")
    if not primary_issue_group:
        primary_issue_group = next((issue_code for issue_code in ISSUE_CONTRACT_PRIORITY if issue_code in issue_codes), "")
    primary_asset_target = issue_asset_target(primary_issue_group)
    window_breach_kind = str(failed_contract_checks[0].get("name") or "") if failed_contract_checks else ""
    return {
        "enabled": True,
        "ok": not failed_contract_checks,
        "contract_checks": contract_checks,
        "contract_thresholds": {
            "config_version": contract.get("config_version"),
            "band": contract.get("band"),
            "thresholds": thresholds,
            "windows": windows,
        },
        "failed_contract_checks": [str(item.get("name") or "") for item in failed_contract_checks],
        "primary_issue_group": primary_issue_group,
        "primary_asset_target": primary_asset_target,
        "window_breach_kind": window_breach_kind,
        "blocking_dimension": primary_issue_group,
        "enforcement_scope": enforcement_scope,
        "quality_contract_window": quality_window,
        "completion_ratio": completion_ratio,
    }


def content_quality_window_metrics(
    *,
    chapter_report_payloads: Sequence[Dict[str, Any]],
    world_metrics: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    diagnostic_issue_code_resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    metrics = dict(world_metrics or {})
    target_chapters = int(metrics.get("target_chapters", 0) or 0)
    contract = resolve_content_quality_contract(target_chapters=target_chapters, config=config)
    if not (contract.get("enabled") or contract.get("diagnostic_enabled")):
        return {
            "enabled": False,
            "gate_enforced": False,
            "diagnostic_enabled": False,
            "band": contract.get("band"),
            "config_version": contract.get("config_version"),
            "early_window_q03_q04_share": 0.0,
            "mid_window_repeat_breach_rate": 0.0,
            "mid_window_exposition_breach_rate": 0.0,
            "mid_window_detail_breach_rate": 0.0,
            "late_window_q09_breach_rate": 0.0,
            "late_window_detail_breach_rate": 0.0,
            "contract_failed_chapters": [],
        }
    thresholds = dict(contract.get("thresholds") or {})
    windows = dict(contract.get("windows") or {})
    early = dict(windows.get("early") or {})
    mid = dict(windows.get("mid") or {})
    late = dict(windows.get("late") or {})
    early_payloads = []
    mid_payloads = []
    late_payloads = []
    failed_chapters = []
    contract_issue_surface_counts = {"Q03": 0, "Q04": 0, "Q05": 0, "Q09": 0}
    for payload in list(chapter_report_payloads or []):
        chapter_id = str(payload.get("chapter_id") or "")
        suffix = chapter_id.rsplit("_", 1)[-1]
        chapter_index = int(suffix) if suffix.isdigit() else 0
        issue_codes = {str(item.get("issue_code") or "") for item in list(payload.get("issues") or []) if str(item.get("issue_code") or "")}
        lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
        repetition_score = _safe_float(lint_metrics.get("repetition_score"))
        exposition_ratio = _safe_float(lint_metrics.get("exposition_ratio"))
        hook_quality = _safe_float(((payload.get("scores") or {}).get("hook_quality")))
        decision = str(dict(payload.get("decision") or {}).get("decision") or "")
        current_window_label = _window_label_for_chapter(chapter_index, windows)
        if int(early.get("start", 0) or 0) <= chapter_index <= int(early.get("end", 0) or -1):
            early_payloads.append(payload)
        if int(mid.get("start", 0) or 0) <= chapter_index <= int(mid.get("end", 0) or -1):
            mid_payloads.append(payload)
        if int(late.get("start", 0) or 0) <= chapter_index <= int(late.get("end", 0) or -1):
            late_payloads.append(payload)
        failed_names = []
        if repetition_score > float(thresholds.get("repetition_score_max", 0.20) or 0.20):
            failed_names.append("repetition_score_cap")
        if exposition_ratio > float(thresholds.get("exposition_ratio_max", 0.52) or 0.52):
            failed_names.append("exposition_ratio_cap")
        if _safe_float(lint_metrics.get("concrete_detail_density")) < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
            failed_names.append("detail_density_floor")
        if _safe_float(lint_metrics.get("dialogue_plus_action_ratio")) < float(thresholds.get("dialogue_plus_action_ratio_min", 0.42) or 0.42):
            failed_names.append("dialogue_action_floor")
        if current_window_label == "mid" and _safe_float(lint_metrics.get("concrete_detail_density")) < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
            failed_names.append("mid_window_detail_breach")
        if chapter_index < int(target_chapters * 0.96 or 0) and "Q09" in issue_codes:
            failed_names.append("q09_pre_end")
        if chapter_index >= int(late.get("start", target_chapters + 1) or target_chapters + 1) and hook_quality < float(thresholds.get("late_window_hook_quality_min", 0.85) or 0.85):
            failed_names.append("continuation_pressure_floor")
        if current_window_label == "late" and _safe_float(lint_metrics.get("concrete_detail_density")) < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04):
            failed_names.append("late_window_detail_breach")
        if failed_names:
            failed_chapters.append({"chapter_id": chapter_id, "chapter_index": chapter_index, "failed_checks": failed_names, "decision": decision})
        diagnostic_issue_codes = (
            diagnostic_issue_code_resolver(payload, target_chapters=target_chapters)
            if diagnostic_issue_code_resolver is not None
            else diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=target_chapters, config=config)
        )
        for issue_code in diagnostic_issue_codes:
            if issue_code in contract_issue_surface_counts:
                contract_issue_surface_counts[issue_code] += 1
    early_breach = sum(
        1
        for payload in early_payloads
        if {"Q03", "Q04"} & {str(item.get("issue_code") or "") for item in list(payload.get("issues") or [])}
    )
    mid_repeat = sum(
        1
        for payload in mid_payloads
        if _safe_float(dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {}).get("repetition_score")) > float(thresholds.get("repetition_score_max", 0.20) or 0.20)
    )
    mid_exposition = sum(
        1
        for payload in mid_payloads
        if _safe_float(dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {}).get("exposition_ratio")) > float(thresholds.get("exposition_ratio_max", 0.52) or 0.52)
    )
    mid_detail = sum(
        1
        for payload in mid_payloads
        if _safe_float(dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {}).get("concrete_detail_density")) < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04)
    )
    late_q09 = sum(
        1
        for payload in late_payloads
        if "Q09" in {str(item.get("issue_code") or "") for item in list(payload.get("issues") or [])}
    )
    late_detail = sum(
        1
        for payload in late_payloads
        if _safe_float(dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {}).get("concrete_detail_density")) < float(thresholds.get("concrete_detail_density_min", 0.04) or 0.04)
    )
    return {
        "enabled": True,
        "gate_enforced": bool(contract.get("gate_enforced", False)),
        "diagnostic_enabled": bool(contract.get("diagnostic_enabled", False)),
        "band": contract.get("band"),
        "config_version": contract.get("config_version"),
        "early_window_q03_q04_share": round(early_breach / float(max(1, len(early_payloads))), 3),
        "mid_window_repeat_breach_rate": round(mid_repeat / float(max(1, len(mid_payloads))), 3),
        "mid_window_exposition_breach_rate": round(mid_exposition / float(max(1, len(mid_payloads))), 3),
        "mid_window_detail_breach_rate": round(mid_detail / float(max(1, len(mid_payloads))), 3),
        "late_window_q09_breach_rate": round(late_q09 / float(max(1, len(late_payloads))), 3),
        "late_window_detail_breach_rate": round(late_detail / float(max(1, len(late_payloads))), 3),
        "contract_failed_chapters": failed_chapters,
        "contract_issue_surface_counts": contract_issue_surface_counts,
        "contract_issue_surface_rates": {
            issue_code: round(count / float(max(1, len(list(chapter_report_payloads or [])))), 3)
            for issue_code, count in contract_issue_surface_counts.items()
        },
        "thresholds": {
            "early_window_q03_q04_share_max": float(early.get("q03_q04_combined_breach_share_max", 0.45) or 0.45),
            "mid_window_repeat_breach_rate_max": float(mid.get("repetition_breach_rate_max", 0.30) or 0.30),
            "mid_window_exposition_breach_rate_max": float(mid.get("exposition_breach_rate_max", 0.30) or 0.30),
            "mid_window_detail_breach_rate_max": float(mid.get("detail_breach_rate_max", 0.35) or 0.35),
            "late_window_q09_breach_rate_max": float(late.get("q09_breach_rate_max", thresholds.get("q09_pre_end_max", 0.08)) or 0.08),
            "late_window_detail_breach_rate_max": float(late.get("detail_breach_rate_max", 0.35) or 0.35),
        },
    }
