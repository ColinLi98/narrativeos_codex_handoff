from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..worldpacks.models import WorldVersion


LONGFORM_CAPABILITY_BAND_ORDER = ("100", "250", "500", "1000")
DEFAULT_LONGFORM_CAPABILITY_PROFILES = {
    "quick_brief_max_target_chapters": 100,
    "structured_longform_bands": ["250", "500", "1000"],
    "bands": {
        "100": {"min_characters": 8, "min_scene_blueprints": 8, "min_locations": 6, "min_scene_family_count": 6, "min_distinct_role_pairs": 6},
        "250": {"min_characters": 12, "min_scene_blueprints": 12, "min_locations": 8, "min_scene_family_count": 8, "min_distinct_role_pairs": 8},
        "500": {"min_characters": 16, "min_scene_blueprints": 16, "min_locations": 12, "min_scene_family_count": 10, "min_distinct_role_pairs": 10},
        "1000": {"min_characters": 24, "min_scene_blueprints": 24, "min_locations": 16, "min_scene_family_count": 12, "min_distinct_role_pairs": 12},
    },
}


def load_longform_capability_profiles(base_dir: Path) -> Dict[str, Any]:
    config_path = base_dir / "configs" / "longform_capability_profiles.json"
    payload: Dict[str, Any] = json.loads(json.dumps(DEFAULT_LONGFORM_CAPABILITY_PROFILES))
    if config_path.exists():
        try:
            file_payload = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(file_payload, dict):
                payload.update({key: value for key, value in file_payload.items() if key != "bands"})
                if isinstance(file_payload.get("bands"), dict):
                    payload["bands"] = {
                        str(key): {
                            "min_characters": int(dict(value or {}).get("min_characters", 0) or 0),
                            "min_scene_blueprints": int(dict(value or {}).get("min_scene_blueprints", 0) or 0),
                            "min_locations": int(dict(value or {}).get("min_locations", 0) or 0),
                            "min_scene_family_count": int(dict(value or {}).get("min_scene_family_count", 0) or 0),
                            "min_distinct_role_pairs": int(dict(value or {}).get("min_distinct_role_pairs", 0) or 0),
                        }
                        for key, value in dict(file_payload.get("bands") or {}).items()
                    }
        except Exception:
            payload = json.loads(json.dumps(DEFAULT_LONGFORM_CAPABILITY_PROFILES))
    return payload


def target_band_for_chapters(target_total_chapters: int) -> str:
    normalized = max(1, int(target_total_chapters or 0))
    if normalized >= 1000:
        return "1000"
    if normalized >= 500:
        return "500"
    if normalized >= 250:
        return "250"
    return "100"


def band_rank(band: Optional[str]) -> int:
    normalized = str(band or "").strip()
    if normalized not in LONGFORM_CAPABILITY_BAND_ORDER:
        return -1
    return LONGFORM_CAPABILITY_BAND_ORDER.index(normalized)


def band_minimums(profiles: Dict[str, Any], band: str) -> Dict[str, int]:
    bands = dict(profiles.get("bands") or {})
    defaults = dict(DEFAULT_LONGFORM_CAPABILITY_PROFILES["bands"])
    source = dict(bands.get(str(band), {}) or defaults.get(str(band), {}) or {})
    return {
        "min_characters": int(source.get("min_characters", 0) or 0),
        "min_scene_blueprints": int(source.get("min_scene_blueprints", 0) or 0),
        "min_locations": int(source.get("min_locations", 0) or 0),
        "min_scene_family_count": int(source.get("min_scene_family_count", 0) or 0),
        "min_distinct_role_pairs": int(source.get("min_distinct_role_pairs", 0) or 0),
    }


def quick_brief_max_target_chapters(profiles: Dict[str, Any]) -> int:
    return max(100, int(profiles.get("quick_brief_max_target_chapters", 100) or 100))


def longform_entry_mode(metadata: Dict[str, Any]) -> str:
    stored = str(metadata.get("entry_mode") or "").strip()
    if stored:
        return stored
    if metadata.get("generated_from_brief"):
        return "quick_brief"
    return "structured_longform"


def longform_structure_counts(worldpack_payload: Dict[str, Any]) -> Dict[str, int]:
    scene_functions = {
        str((item or {}).get("scene_function") or "").strip()
        for item in list(worldpack_payload.get("scene_blueprints") or [])
        if str((item or {}).get("scene_function") or "").strip()
    }
    role_pairs = {
        " / ".join(sorted([str(role).strip() for role in list((item or {}).get("required_roles") or []) if str(role).strip()]))
        for item in list(worldpack_payload.get("scene_blueprints") or [])
        if len([str(role).strip() for role in list((item or {}).get("required_roles") or []) if str(role).strip()]) >= 2
    }
    return {
        "character_count": len(list(worldpack_payload.get("characters") or [])),
        "scene_blueprint_count": len(list(worldpack_payload.get("scene_blueprints") or [])),
        "location_count": len(list((worldpack_payload.get("world_bible") or {}).get("locations") or [])),
        "scene_family_count": len(scene_functions),
        "distinct_role_pair_count": len(role_pairs),
    }


def supported_target_band(*, counts: Dict[str, int], entry_mode: str, profiles: Dict[str, Any]) -> Optional[str]:
    highest: Optional[str] = None
    for band in LONGFORM_CAPABILITY_BAND_ORDER:
        minimums = band_minimums(profiles, band)
        if (
            counts["character_count"] >= minimums["min_characters"]
            and counts["scene_blueprint_count"] >= minimums["min_scene_blueprints"]
            and counts["location_count"] >= minimums["min_locations"]
            and counts["scene_family_count"] >= minimums["min_scene_family_count"]
            and counts["distinct_role_pair_count"] >= minimums["min_distinct_role_pairs"]
        ):
            highest = band
    if highest is None:
        return None
    if entry_mode == "quick_brief" and band_rank(highest) > band_rank("100"):
        return "100"
    return highest


def extract_open_promises_from_issue(issue: Dict[str, Any]) -> Optional[int]:
    for evidence in list(issue.get("evidence") or []):
        text = str(evidence or "")
        if text.startswith("open_promises="):
            try:
                return int(text.split("=", 1)[1])
            except ValueError:
                return None
    return None


def latest_longform_runway_guard(
    repository: SQLAlchemyPlatformRepository,
    version: WorldVersion,
    *,
    target_total_chapters: int,
) -> Optional[Dict[str, Any]]:
    if target_total_chapters < 100:
        return None
    works = repository.list_author_works(account_id=version.author_id, world_version_id=version.world_version_id, limit=20)
    if not works:
        return None
    active_work = next((item for item in works if item.get("is_active_line")), None) or works[0]
    revisions = repository.list_author_work_revisions(work_id=active_work["work_id"], limit=20)
    blocked_revision = next((item for item in revisions if item.get("revision_type") == "quality_guard_blocked"), None)
    if not blocked_revision:
        return None
    snapshot = dict(blocked_revision.get("snapshot_json") or {})
    quality_gate = dict(snapshot.get("quality_gate") or {})
    issues = [dict(item or {}) for item in list(quality_gate.get("issues") or [])]
    issue_codes = {str(item.get("issue_code") or "").strip() for item in issues if str(item.get("issue_code") or "").strip()}
    if "Q09" not in issue_codes:
        return None
    chapter_index = int(snapshot.get("chapter_index") or 0)
    if chapter_index <= 0 or chapter_index >= int(target_total_chapters * 0.8):
        return None
    open_promises = None
    for issue in issues:
        open_promises = extract_open_promises_from_issue(issue)
        if open_promises is not None:
            break
    if open_promises is None or open_promises > 0:
        return None
    return {
        "key": "longform_structure_exhaustion",
        "severity": "high",
        "message": f"当前长线在第 {chapter_index} 章附近出现续航耗空信号：开放 promises 已归零，继续盲跑更容易触发节奏塌陷。",
        "chapter_index": chapter_index,
        "work_id": active_work.get("work_id"),
        "pacing": dict(quality_gate.get("scores") or {}).get("pacing"),
        "issue_codes": sorted(issue_codes),
        "recommended_actions": [
            "bootstrap_structured_longform",
            "expand_character_and_scene_lattice",
            "rebuild_promise_lattice",
        ],
    }


def build_longform_500_product_readiness(
    *,
    claim_safe_band: Optional[str],
    longform_readiness: Dict[str, Any],
    simulation_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claim_band = str(claim_safe_band or "").strip()
    structural_status = str(dict(longform_readiness or {}).get("status") or "")
    report = dict(simulation_report or {})
    cross_pack = dict(report.get("cross_pack_summary") or report)
    signoff = dict(cross_pack.get("longform_500_signoff") or {})
    interactive_signoff = dict(cross_pack.get("longform_500_interactive_signoff") or {})
    human_closeout = dict(cross_pack.get("longform_500_human_review_closeout") or {})
    review_sample_coverage = dict(cross_pack.get("review_sample_coverage_500") or {})
    weakest_program = dict(cross_pack.get("weakest_pack_polish_program") or {})
    hard_summary = dict(cross_pack.get("generation_hard_constraint_summary") or {})
    scene_card_audit = dict(hard_summary.get("scene_card_visible_text_audit") or {})
    runtime_profile = dict(cross_pack.get("benchmark_runtime_profile") or {})
    replay_projection = dict(cross_pack.get("reader_replay_projection_summary") or {})
    reader_storybook = dict(cross_pack.get("reader_storybook_500_verification") or {})

    blockers: List[Dict[str, Any]] = []
    if not claim_band or band_rank(claim_band) < band_rank("500"):
        blockers.append({"key": "longform_500_structure_not_claimed", "severity": "high"})
    if structural_status != "ready":
        blockers.append({"key": "longform_structure_not_ready", "severity": "high", "status": structural_status})
    if not bool(signoff.get("ready", False)):
        blockers.append({"key": "longform_500_static_signoff_missing", "severity": "high"})
    if not bool(interactive_signoff.get("ready", False)):
        blockers.append({"key": "longform_500_interactive_signoff_missing", "severity": "medium"})
    human_closeout_ready = bool(human_closeout.get("ready", False) or review_sample_coverage.get("human_closeout_ready", False))
    if not human_closeout_ready:
        blockers.append({"key": "longform_500_human_review_closeout_missing", "severity": "high"})
    if not weakest_program or str(weakest_program.get("status") or "") != "stop_ready":
        blockers.append(
            {
                "key": "longform_500_weakest_stop_ready_missing",
                "severity": "high",
                "status": str(weakest_program.get("status") or "missing"),
                "continue_worlds": list(weakest_program.get("continue_worlds") or []),
            }
        )
    if int(hard_summary.get("chapter_count", 0) or 0) < 500 or int(hard_summary.get("hard_fail_count", 0) or 0) > 0:
        blockers.append(
            {
                "key": "longform_500_hard_constraint_evidence_missing",
                "severity": "high",
                "chapter_count": int(hard_summary.get("chapter_count", 0) or 0),
                "hard_fail_count": int(hard_summary.get("hard_fail_count", 0) or 0),
            }
        )
    scene_card_violation_count = int(scene_card_audit.get("violation_count", 0) or 0)
    if "scene_card_visible_text_audit" not in hard_summary or scene_card_violation_count > 0:
        blockers.append(
            {
                "key": "longform_500_scene_card_visible_text_evidence_missing",
                "severity": "high",
                "violation_count": scene_card_violation_count,
            }
        )
    replay_ready = bool(replay_projection.get("ready", False) or reader_storybook.get("ready", False))
    if not replay_ready:
        blockers.append({"key": "reader_500_replay_projection_evidence_missing", "severity": "medium"})
    if not runtime_profile:
        blockers.append({"key": "longform_500_runtime_profile_missing", "severity": "medium"})

    ready = not blockers
    return {
        "schema_version": "longform_500_product_readiness/v1",
        "target_band": "500",
        "status": "ready" if ready else "watch",
        "ready": ready,
        "claim_safe_band": claim_band or None,
        "product_ready_band": "500" if ready else None,
        "blockers": blockers,
        "evidence": {
            "static_signoff_ready": bool(signoff.get("ready", False)),
            "interactive_signoff_ready": bool(interactive_signoff.get("ready", False)),
            "human_closeout_ready": human_closeout_ready,
            "weakest_pack_stop_ready": str(weakest_program.get("status") or "") == "stop_ready",
            "weakest_pack_continue_worlds": list(weakest_program.get("continue_worlds") or []),
            "hard_constraint_chapter_count": int(hard_summary.get("chapter_count", 0) or 0),
            "hard_constraint_fail_count": int(hard_summary.get("hard_fail_count", 0) or 0),
            "scene_card_visible_text_audit_present": "scene_card_visible_text_audit" in hard_summary,
            "scene_card_visible_text_violation_count": scene_card_violation_count,
            "reader_replay_projection_ready": replay_ready,
            "runtime_profile_present": bool(runtime_profile),
        },
        "recommended_actions": [] if ready else ["run_longform_500_product_readiness_bundle"],
    }


def build_longform_capability_payload(
    *,
    base_dir: Path,
    repository: SQLAlchemyPlatformRepository,
    worldpack_payload: Dict[str, Any],
    version: Optional[WorldVersion] = None,
) -> Dict[str, Any]:
    profiles = load_longform_capability_profiles(base_dir)
    metadata = dict(worldpack_payload.get("metadata") or {})
    brief = dict(metadata.get("author_brief") or {})
    requested_target_chapters = max(
        1,
        int(
            metadata.get("requested_target_chapters")
            or brief.get("target_total_chapters")
            or ((worldpack_payload.get("series_plan") or {}).get("total_chapter_target") or 100)
        ),
    )
    requested_band = target_band_for_chapters(requested_target_chapters)
    entry_mode_value = longform_entry_mode(metadata)
    counts = longform_structure_counts(worldpack_payload)
    supported_band_value = supported_target_band(counts=counts, entry_mode=entry_mode_value, profiles=profiles)
    requires_structured = (
        requested_target_chapters > quick_brief_max_target_chapters(profiles)
        and entry_mode_value != "structured_longform"
    )
    readiness_status = "ready"
    blockers: List[Dict[str, Any]] = []
    minimums = band_minimums(profiles, requested_band)
    if requires_structured:
        readiness_status = "blocked"
        blockers.append(
            {
                "key": "structured_longform_required",
                "severity": "high",
                "message": f"当前入口是 quick brief，只能直接承诺到 {quick_brief_max_target_chapters(profiles)} 章；若要继续走 {requested_band} 章，需要先进入结构化长篇蓝图。",
            }
        )
    deficits = []
    if counts["character_count"] < minimums["min_characters"]:
        deficits.append(f"角色 {counts['character_count']}/{minimums['min_characters']}")
    if counts["scene_blueprint_count"] < minimums["min_scene_blueprints"]:
        deficits.append(f"场景 {counts['scene_blueprint_count']}/{minimums['min_scene_blueprints']}")
    if counts["location_count"] < minimums["min_locations"]:
        deficits.append(f"地点 {counts['location_count']}/{minimums['min_locations']}")
    if counts["scene_family_count"] < minimums["min_scene_family_count"]:
        deficits.append(f"scene family {counts['scene_family_count']}/{minimums['min_scene_family_count']}")
    if counts["distinct_role_pair_count"] < minimums["min_distinct_role_pairs"]:
        deficits.append(f"role pairs {counts['distinct_role_pair_count']}/{minimums['min_distinct_role_pairs']}")
    if deficits:
        if readiness_status == "ready":
            readiness_status = "needs_enrichment"
        blockers.append(
            {
                "key": "longform_structure_minimums",
                "severity": "high" if requested_band != "100" else "medium",
                "message": f"{requested_band} 章能力的最小骨架还不够：{' / '.join(deficits)}。",
            }
        )
    runway_guard = latest_longform_runway_guard(repository, version, target_total_chapters=requested_target_chapters) if version is not None else None
    if runway_guard:
        readiness_status = "blocked"
        blockers.append(runway_guard)
    recommended_actions: List[str] = []
    if requires_structured:
        recommended_actions.append("bootstrap_structured_longform")
    elif deficits:
        recommended_actions.append("expand_longform_structure")
    if runway_guard:
        recommended_actions.append("repair_longform_runway")
    if not recommended_actions:
        recommended_actions.append("continue_authoring")
    longform_readiness = {
        "band": requested_band,
        "status": readiness_status,
        "blockers": blockers,
        "recommended_actions": recommended_actions,
        "minimums": minimums,
    }
    product_readiness_500 = build_longform_500_product_readiness(
        claim_safe_band=supported_band_value,
        longform_readiness=longform_readiness,
        simulation_report=dict(getattr(version, "simulation_report_json", {}) or {}) if version is not None else {},
    )
    return {
        "entry_mode": entry_mode_value,
        "requested_target_chapters": requested_target_chapters,
        "requested_target_band": requested_band,
        "supported_target_band": supported_band_value,
        "claim_safe_band": supported_band_value,
        "product_ready_band": product_readiness_500.get("product_ready_band"),
        "requires_structured_longform": requires_structured,
        "structure_counts": counts,
        "longform_readiness": longform_readiness,
        "longform_500_product_readiness": product_readiness_500,
    }


def sync_longform_capability_metadata(
    *,
    base_dir: Path,
    repository: SQLAlchemyPlatformRepository,
    worldpack_payload: Dict[str, Any],
    version: Optional[WorldVersion] = None,
) -> Dict[str, Any]:
    metadata = dict(worldpack_payload.get("metadata") or {})
    capability = build_longform_capability_payload(
        base_dir=base_dir,
        repository=repository,
        worldpack_payload=worldpack_payload,
        version=version,
    )
    metadata["requested_target_chapters"] = capability["requested_target_chapters"]
    metadata["entry_mode"] = capability["entry_mode"]
    metadata["capability_band_supported"] = capability["supported_target_band"]
    metadata["requires_structured_longform"] = capability["requires_structured_longform"]
    metadata["claim_safe_band"] = capability["claim_safe_band"]
    metadata["product_ready_band"] = capability["product_ready_band"]
    metadata["longform_readiness"] = dict(capability["longform_readiness"])
    metadata["longform_500_product_readiness"] = dict(capability["longform_500_product_readiness"])
    worldpack_payload["metadata"] = metadata
    return capability
