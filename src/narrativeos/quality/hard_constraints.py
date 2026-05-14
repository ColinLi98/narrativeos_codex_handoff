from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

from ..content_quality_contracts import (
    DEFAULT_GENERATION_HARD_CONSTRAINTS,
    load_content_quality_contracts,
)
from ..long_route_quality import (
    DEFAULT_READER_CHOICE,
    STOCK_REFRAIN_REPLACEMENTS,
    clean_broken_reader_slots,
)
from ..meta_leak_detector import detect_meta_leaks
from ..prose_linter import story_text_unit_count
from .models import GroundingCheck


UNIVERSAL_RULE_IDS = tuple(DEFAULT_GENERATION_HARD_CONSTRAINTS["universal_rules"].keys())


def _deep_copy(payload: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(dict(payload or {}))


def _merge_hard_constraint_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    merged = _deep_copy(DEFAULT_GENERATION_HARD_CONSTRAINTS)
    payload = dict(raw or {})
    for key, value in payload.items():
        if key in {"universal_rules", "base_thresholds", "genre_profiles", "length_profiles"}:
            continue
        merged[key] = value
    for key in ("universal_rules", "base_thresholds", "genre_profiles", "length_profiles"):
        if isinstance(payload.get(key), dict):
            base = dict(merged.get(key) or {})
            for child_key, child_value in dict(payload.get(key) or {}).items():
                if isinstance(child_value, dict) and isinstance(base.get(child_key), dict):
                    base[child_key] = {**dict(base.get(child_key) or {}), **dict(child_value or {})}
                else:
                    base[child_key] = child_value
            merged[key] = base
    return merged


def load_generation_hard_constraints(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    contracts = dict(config or load_content_quality_contracts())
    raw = contracts.get("generation_hard_constraints")
    if raw is None and str(contracts.get("config_version") or "").startswith("generation_hard_constraints"):
        raw = contracts
    return _merge_hard_constraint_config(dict(raw or {}))


def _normalize_profile_token(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _worldpack_genre_candidates(worldpack_payload: Optional[Dict[str, Any]]) -> List[str]:
    payload = dict(worldpack_payload or {})
    metadata = dict(payload.get("metadata") or {})
    author_brief = dict(metadata.get("author_brief") or {})
    candidates = [
        author_brief.get("genre_preset"),
        metadata.get("genre_preset"),
        metadata.get("genre"),
        payload.get("genre"),
        payload.get("world_id"),
    ]
    style_pack = dict(payload.get("narrative_style_pack") or {})
    candidates.extend([style_pack.get("genre"), style_pack.get("tone")])
    return [_normalize_profile_token(str(item)) for item in candidates if str(item or "").strip()]


def _resolve_genre_profile_id(
    hard_config: Dict[str, Any],
    *,
    worldpack_payload: Optional[Dict[str, Any]] = None,
    genre_profile: Optional[str] = None,
) -> str:
    requested = _normalize_profile_token(str(genre_profile or ""))
    candidates = [requested] if requested else _worldpack_genre_candidates(worldpack_payload)
    profiles = dict(hard_config.get("genre_profiles") or {})
    alias_map: Dict[str, str] = {}
    for profile_id, profile in profiles.items():
        normalized_id = _normalize_profile_token(profile_id)
        alias_map[normalized_id] = normalized_id
        for alias in list(dict(profile or {}).get("aliases") or []):
            alias_map[_normalize_profile_token(str(alias))] = normalized_id
    for candidate in candidates:
        if candidate in alias_map:
            return alias_map[candidate]
    for candidate in candidates:
        for alias, profile_id in alias_map.items():
            if alias and (alias in candidate or candidate in alias):
                return profile_id
    return "base"


def _resolve_length_profile_id(hard_config: Dict[str, Any], *, target_chapters: int) -> str:
    chapter_count = int(target_chapters or 0)
    selected = ""
    selected_min = -1
    for profile_id, profile in dict(hard_config.get("length_profiles") or {}).items():
        min_chapters = int(dict(profile or {}).get("min_chapters", 0) or 0)
        if min_chapters <= chapter_count and min_chapters > selected_min:
            selected = str(profile_id)
            selected_min = min_chapters
    return selected or "short_route"


def resolve_generation_hard_constraint_profile(
    *,
    target_chapters: int = 0,
    worldpack_payload: Optional[Dict[str, Any]] = None,
    genre_profile: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    hard_config = load_generation_hard_constraints(config)
    universal_rules = dict(hard_config.get("universal_rules") or {})
    genre_profile_id = _resolve_genre_profile_id(hard_config, worldpack_payload=worldpack_payload, genre_profile=genre_profile)
    length_profile_id = _resolve_length_profile_id(hard_config, target_chapters=target_chapters)
    genre_payload = dict((hard_config.get("genre_profiles") or {}).get(genre_profile_id) or {})
    length_payload = dict((hard_config.get("length_profiles") or {}).get(length_profile_id) or {})

    thresholds = dict(hard_config.get("base_thresholds") or {})
    thresholds.update(dict(genre_payload.get("threshold_overrides") or {}))
    thresholds.update(dict(length_payload.get("threshold_overrides") or {}))

    disabled_rules = {str(item) for item in list(genre_payload.get("disabled_rules") or []) if str(item)}
    disabled_rules.update(str(item) for item in list(length_payload.get("disabled_rules") or []) if str(item))
    profile_warnings = []
    ignored_universal_disables = [rule_id for rule_id in UNIVERSAL_RULE_IDS if rule_id in disabled_rules]
    if ignored_universal_disables:
        profile_warnings.append(
            {
                "code": "universal_rules_cannot_be_disabled",
                "rule_ids": ignored_universal_disables,
            }
        )
    active_rules = [rule_id for rule_id in UNIVERSAL_RULE_IDS if rule_id in universal_rules]
    for rule_id in list(genre_payload.get("enabled_rules") or []) + list(length_payload.get("enabled_rules") or []):
        normalized = str(rule_id or "").strip()
        if normalized and normalized not in active_rules and normalized not in disabled_rules:
            active_rules.append(normalized)

    return {
        "config_version": str(hard_config.get("config_version") or ""),
        "profile_id": "%s:%s" % (genre_profile_id, length_profile_id),
        "genre_profile": genre_profile_id,
        "length_profile": length_profile_id,
        "repair_policy": str(hard_config.get("repair_policy") or "repair_once_then_fail_closed"),
        "universal_rules": universal_rules,
        "active_rules": active_rules,
        "thresholds": thresholds,
        "profile_warnings": profile_warnings,
    }


def build_generation_hard_constraint_prompt_contract(
    *,
    target_chapters: int = 0,
    worldpack_payload: Optional[Dict[str, Any]] = None,
    genre_profile: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = resolve_generation_hard_constraint_profile(
        target_chapters=target_chapters,
        worldpack_payload=worldpack_payload,
        genre_profile=genre_profile,
        config=config,
    )
    universal_rules = dict(profile.get("universal_rules") or {})
    return {
        "config_version": profile.get("config_version"),
        "profile_id": profile.get("profile_id"),
        "repair_policy": profile.get("repair_policy"),
        "hard_rules": [
            {
                "rule_id": rule_id,
                "issue_code": dict(universal_rules.get(rule_id) or {}).get("issue_code"),
                "action": dict(universal_rules.get(rule_id) or {}).get("action"),
                "summary": dict(universal_rules.get(rule_id) or {}).get("summary"),
            }
            for rule_id in list(profile.get("active_rules") or [])
            if rule_id in universal_rules
        ],
        "thresholds": dict(profile.get("thresholds") or {}),
    }


def _coerce_grounding_status(grounding_check: Any, quality_gate: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(grounding_check, GroundingCheck):
        return str(grounding_check.status or "")
    if isinstance(grounding_check, dict):
        return str(grounding_check.get("status") or "")
    return str(dict(quality_gate or {}).get("grounding_status") or "")


def _reader_field_texts(reader_view: Dict[str, Any]) -> Dict[str, str]:
    payload = dict(reader_view or {})
    fields = {
        "chapter_title": str(payload.get("chapter_title") or ""),
        "recap": str(payload.get("recap") or ""),
        "body": str(payload.get("body") or ""),
    }
    scene_card = dict(payload.get("scene_card") or {})
    for key in ("title", "summary", "quote", "pull_quote"):
        if key in scene_card:
            fields[f"scene_card.{key}"] = str(scene_card.get(key) or "")
    for key in ("story_beats", "beats", "visual_details"):
        for index, item in enumerate(list(scene_card.get(key) or []), start=1):
            fields[f"scene_card.{key}[{index}]"] = str(item or "")
    for index, item in enumerate(list(payload.get("relationship_hints") or []), start=1):
        fields[f"relationship_hints[{index}]"] = str(item or "")
    for index, item in enumerate(list(payload.get("choices") or []), start=1):
        fields[f"choices[{index}]"] = str(item or "")
    return fields


def _append_violation(
    violations: List[Dict[str, Any]],
    *,
    rule_id: str,
    issue_code: str,
    field: str = "",
    evidence: Optional[Dict[str, Any]] = None,
) -> None:
    violations.append(
        {
            "rule_id": rule_id,
            "issue_code": issue_code,
            "field": field,
            "evidence": dict(evidence or {}),
        }
    )


def _meta_hit_groups(text: str) -> Dict[str, List[str]]:
    hits = detect_meta_leaks(text)
    engineering = [hit for hit in hits if "_" in hit or "->" in hit or "event_id" in hit or "seed_id" in hit]
    meta = [hit for hit in hits if hit not in engineering]
    return {"engineering": engineering, "meta": meta}


def evaluate_reader_generation_hard_constraints(
    *,
    reader_view: Dict[str, Any],
    quality_gate: Optional[Dict[str, Any]] = None,
    grounding_check: Any = None,
    target_chapters: int = 0,
    worldpack_payload: Optional[Dict[str, Any]] = None,
    genre_profile: Optional[str] = None,
    repair_report: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = resolve_generation_hard_constraint_profile(
        target_chapters=target_chapters,
        worldpack_payload=worldpack_payload,
        genre_profile=genre_profile,
        config=config,
    )
    universal_rules = dict(profile.get("universal_rules") or {})
    thresholds = dict(profile.get("thresholds") or {})
    active_rules = set(str(item) for item in list(profile.get("active_rules") or []) if str(item))
    payload = dict(reader_view or {})
    quality_gate_payload = dict(quality_gate or {})
    violations: List[Dict[str, Any]] = []
    choices = [str(item or "") for item in list(payload.get("choices") or [])]
    non_empty_choices = [item for item in choices if item.strip()]

    if "schema_complete" in active_rules:
        min_choice_count = int(thresholds.get("min_choice_count", 2) or 2)
        min_body_text_units = int(thresholds.get("min_body_text_units", 80) or 80)
        if not str(payload.get("chapter_title") or "").strip():
            _append_violation(violations, rule_id="schema_complete", issue_code="Q10", field="chapter_title")
        body = str(payload.get("body") or "")
        if story_text_unit_count(body) < min_body_text_units:
            _append_violation(
                violations,
                rule_id="schema_complete",
                issue_code="Q10",
                field="body",
                evidence={"text_units": story_text_unit_count(body), "minimum": min_body_text_units},
            )
        if len(non_empty_choices) < min_choice_count:
            _append_violation(
                violations,
                rule_id="schema_complete",
                issue_code="Q10",
                field="choices",
                evidence={"choice_count": len(non_empty_choices), "minimum": min_choice_count},
            )
        for index, choice in enumerate(choices, start=1):
            if not choice.strip():
                _append_violation(violations, rule_id="schema_complete", issue_code="Q10", field=f"choices[{index}]")

    field_texts = _reader_field_texts(payload)
    if "broken_slot" in active_rules:
        for field, text in field_texts.items():
            cleaned, report = clean_broken_reader_slots(text)
            if cleaned != text.strip() or report.get("broken_slot_repaired"):
                _append_violation(
                    violations,
                    rule_id="broken_slot",
                    issue_code="Q10",
                    field=field,
                    evidence={"repairs": list(report.get("broken_slot_repairs") or [])},
                )

    if "engineering_leak" in active_rules or "meta_narration_leak" in active_rules:
        for field, text in field_texts.items():
            grouped = _meta_hit_groups(text)
            if "engineering_leak" in active_rules and grouped["engineering"]:
                _append_violation(
                    violations,
                    rule_id="engineering_leak",
                    issue_code="Q01",
                    field=field,
                    evidence={"patterns": grouped["engineering"]},
                )
            if "meta_narration_leak" in active_rules and grouped["meta"]:
                _append_violation(
                    violations,
                    rule_id="meta_narration_leak",
                    issue_code="Q02",
                    field=field,
                    evidence={"patterns": grouped["meta"]},
                )

    grounding_status = _coerce_grounding_status(grounding_check, quality_gate_payload)
    if "grounding_failed" in active_rules and grounding_status == "failed":
        _append_violation(
            violations,
            rule_id="grounding_failed",
            issue_code="Q07",
            field="grounding",
            evidence={"grounding_status": grounding_status},
        )

    failed_checks = {str(item) for item in list(quality_gate_payload.get("failed_checks") or []) if str(item)}
    failed_checks.update(str(item) for item in list(quality_gate_payload.get("failed_contract_checks") or []) if str(item))
    if "premature_terminal" in active_rules and failed_checks & {"q09_pre_end", "premature_terminal_forbidden"}:
        _append_violation(
            violations,
            rule_id="premature_terminal",
            issue_code="Q09",
            field="quality_gate",
            evidence={"failed_checks": sorted(failed_checks & {"q09_pre_end", "premature_terminal_forbidden"})},
        )

    joined_text = "\n".join(field_texts.values())
    if "stock_refrain_budget" in active_rules:
        max_current = int(thresholds.get("stock_refrain_current_max", 2) or 2)
        for phrase in STOCK_REFRAIN_REPLACEMENTS:
            if phrase == DEFAULT_READER_CHOICE:
                continue
            count = joined_text.count(phrase)
            if count > max_current:
                _append_violation(
                    violations,
                    rule_id="stock_refrain_budget",
                    issue_code="Q03",
                    field="reader_view",
                    evidence={"phrase": phrase, "count": count, "maximum": max_current},
                )

    if "choice_text_budget" in active_rules:
        max_choice_occurrences = int(thresholds.get("choice_text_current_max", 1) or 1)
        counts = Counter("".join(str(choice).split()) for choice in non_empty_choices)
        default_choice = "".join(DEFAULT_READER_CHOICE.split())
        for normalized_choice, count in counts.items():
            if not normalized_choice:
                continue
            if count > max_choice_occurrences or normalized_choice == default_choice:
                _append_violation(
                    violations,
                    rule_id="choice_text_budget",
                    issue_code="Q08",
                    field="choices",
                    evidence={"choice": normalized_choice, "count": count, "maximum": max_choice_occurrences},
                )

    unique_failed_checks = list(dict.fromkeys(str(item.get("rule_id") or "") for item in violations if str(item.get("rule_id") or "")))
    repair_actions = list(dict(repair_report or {}).get("actions") or [])
    repair_attempts = 1 if repair_actions else 0
    return {
        "ok": not violations,
        "config_version": profile.get("config_version"),
        "profile_id": profile.get("profile_id"),
        "genre_profile": profile.get("genre_profile"),
        "length_profile": profile.get("length_profile"),
        "repair_policy": profile.get("repair_policy"),
        "repair_attempts": repair_attempts,
        "repair_applied": bool(repair_actions),
        "repair_success": bool(repair_actions) and not violations,
        "failed_checks": unique_failed_checks,
        "violations": violations,
        "thresholds": thresholds,
        "profile_warnings": list(profile.get("profile_warnings") or []),
        "active_rules": list(profile.get("active_rules") or []),
    }


def enforce_generation_hard_constraints(
    quality_bundle: Dict[str, Any],
    *,
    reader_view: Dict[str, Any],
    grounding_check: Any = None,
    source_surface: str,
    target_chapters: int = 0,
    worldpack_payload: Optional[Dict[str, Any]] = None,
    repair_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bundle = dict(quality_bundle or {})
    quality_gate = dict(bundle.get("quality_gate") or {})
    result = evaluate_reader_generation_hard_constraints(
        reader_view=reader_view,
        quality_gate=quality_gate,
        grounding_check=grounding_check or bundle.get("grounding_check") or bundle.get("grounding_result"),
        target_chapters=target_chapters,
        worldpack_payload=worldpack_payload,
        repair_report=repair_report,
    )
    quality_gate["hard_constraint_result"] = result
    quality_gate.setdefault("code", "chapter_quality_guard_failed")
    if not result.get("ok", True):
        existing_failed = [str(item) for item in list(quality_gate.get("failed_checks") or []) if str(item)]
        for failed_check in list(result.get("failed_checks") or []):
            if failed_check not in existing_failed:
                existing_failed.append(str(failed_check))
        quality_gate["failed_checks"] = existing_failed
        quality_gate["ok"] = False
        quality_gate["enforced_decision"] = "block"
        quality_gate["summary"] = "章节未通过生成硬约束：%s" % " / ".join(existing_failed[:4])
        quality_gate["blocking_dimension"] = "hard_constraints"
        quality_gate["source_surface"] = str(source_surface or "")
    bundle["quality_gate"] = quality_gate
    return bundle


def summarize_generation_hard_constraints(
    chapter_report_payloads: Sequence[Dict[str, Any]],
    *,
    chapter_trace_payloads: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    reports = [dict(item or {}) for item in list(chapter_report_payloads or [])]
    traces = [dict(item or {}) for item in list(chapter_trace_payloads or [])]
    violation_counts: Counter[str] = Counter()
    field_violation_counts: Counter[str] = Counter()
    scene_card_rule_counts: Counter[str] = Counter()
    scene_card_issue_counts: Counter[str] = Counter()
    hard_fail_count = 0
    repair_attempt_count = 0
    repair_success_count = 0
    for payload in reports:
        quality_gate = dict(payload.get("quality_gate") or {})
        result = dict(quality_gate.get("hard_constraint_result") or payload.get("hard_constraint_result") or {})
        if result:
            repair_attempt_count += int(result.get("repair_attempts", 0) or 0)
            if result.get("repair_success"):
                repair_success_count += 1
            if not result.get("ok", True):
                hard_fail_count += 1
                for rule_id in list(result.get("failed_checks") or []):
                    violation_counts[str(rule_id)] += 1
                for violation in list(result.get("violations") or []):
                    field = str(dict(violation or {}).get("field") or "")
                    rule_id = str(dict(violation or {}).get("rule_id") or "")
                    issue_code = str(dict(violation or {}).get("issue_code") or "")
                    if field:
                        field_violation_counts[field] += 1
                    if field.startswith("scene_card."):
                        if rule_id:
                            scene_card_rule_counts[rule_id] += 1
                        if issue_code:
                            scene_card_issue_counts[issue_code] += 1
            continue
        hard = dict(payload.get("hard_validator_results") or {})
        decision = dict(payload.get("decision") or {})
        issues = [dict(item or {}) for item in list(payload.get("issues") or [])]
        hard_issue_codes = {
            str(item.get("issue_code") or "")
            for item in issues
            if str(item.get("severity") or "") == "high" and str(item.get("issue_code") or "") in {"Q01", "Q02", "Q09", "Q10"}
        }
        if bool(hard.get("failed")) or str(decision.get("reason") or "") == "hard_validator_failed" or hard_issue_codes:
            hard_fail_count += 1
            for issue_code in hard_issue_codes or {"hard_validator_failed"}:
                violation_counts[str(issue_code)] += 1
    for trace in traces:
        actions = list(trace.get("quality_pass_actions") or [])
        if actions:
            repair_attempt_count += 1
            if str(dict(trace.get("evaluation") or {}).get("decision") or "") == "pass":
                repair_success_count += 1
    chapter_count = len(reports)
    return {
        "schema_version": "generation_hard_constraint_summary/v1",
        "chapter_count": chapter_count,
        "hard_fail_count": hard_fail_count,
        "hard_fail_rate": round(hard_fail_count / float(max(1, chapter_count)), 3),
        "repair_attempt_count": repair_attempt_count,
        "repair_success_count": repair_success_count,
        "repair_success_rate": round(repair_success_count / float(max(1, repair_attempt_count)), 3),
        "violation_mix": [
            {"rule_id": rule_id, "count": count, "share": round(count / float(max(1, hard_fail_count)), 3)}
            for rule_id, count in sorted(violation_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "field_violation_mix": [
            {"field": field, "count": count, "share": round(count / float(max(1, hard_fail_count)), 3)}
            for field, count in sorted(field_violation_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "scene_card_visible_text_audit": {
            "schema_version": "scene_card_visible_text_audit/v1",
            "violation_count": sum(scene_card_rule_counts.values()),
            "failed_rule_mix": [
                {"rule_id": rule_id, "count": count}
                for rule_id, count in sorted(scene_card_rule_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "issue_mix": [
                {"issue_code": issue_code, "count": count}
                for issue_code, count in sorted(scene_card_issue_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        },
    }


def aggregate_generation_hard_constraint_summaries(worlds: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    summaries = [dict(world.get("generation_hard_constraint_summary") or {}) for world in list(worlds or [])]
    chapter_count = sum(int(item.get("chapter_count", 0) or 0) for item in summaries)
    hard_fail_count = sum(int(item.get("hard_fail_count", 0) or 0) for item in summaries)
    repair_attempt_count = sum(int(item.get("repair_attempt_count", 0) or 0) for item in summaries)
    repair_success_count = sum(int(item.get("repair_success_count", 0) or 0) for item in summaries)
    violation_counts: Counter[str] = Counter()
    field_violation_counts: Counter[str] = Counter()
    scene_card_rule_counts: Counter[str] = Counter()
    scene_card_issue_counts: Counter[str] = Counter()
    for summary in summaries:
        for item in list(summary.get("violation_mix") or []):
            violation_counts[str(item.get("rule_id") or "")] += int(item.get("count", 0) or 0)
        for item in list(summary.get("field_violation_mix") or []):
            field_violation_counts[str(item.get("field") or "")] += int(item.get("count", 0) or 0)
        audit = dict(summary.get("scene_card_visible_text_audit") or {})
        for item in list(audit.get("failed_rule_mix") or []):
            scene_card_rule_counts[str(item.get("rule_id") or "")] += int(item.get("count", 0) or 0)
        for item in list(audit.get("issue_mix") or []):
            scene_card_issue_counts[str(item.get("issue_code") or "")] += int(item.get("count", 0) or 0)
    return {
        "schema_version": "generation_hard_constraint_summary/v1",
        "world_count": len(summaries),
        "chapter_count": chapter_count,
        "hard_fail_count": hard_fail_count,
        "hard_fail_rate": round(hard_fail_count / float(max(1, chapter_count)), 3),
        "repair_attempt_count": repair_attempt_count,
        "repair_success_count": repair_success_count,
        "repair_success_rate": round(repair_success_count / float(max(1, repair_attempt_count)), 3),
        "violation_mix": [
            {"rule_id": rule_id, "count": count, "share": round(count / float(max(1, hard_fail_count)), 3)}
            for rule_id, count in sorted(violation_counts.items(), key=lambda item: (-item[1], item[0]))
            if rule_id
        ],
        "field_violation_mix": [
            {"field": field, "count": count, "share": round(count / float(max(1, hard_fail_count)), 3)}
            for field, count in sorted(field_violation_counts.items(), key=lambda item: (-item[1], item[0]))
            if field
        ],
        "scene_card_visible_text_audit": {
            "schema_version": "scene_card_visible_text_audit/v1",
            "violation_count": sum(scene_card_rule_counts.values()),
            "failed_rule_mix": [
                {"rule_id": rule_id, "count": count}
                for rule_id, count in sorted(scene_card_rule_counts.items(), key=lambda item: (-item[1], item[0]))
                if rule_id
            ],
            "issue_mix": [
                {"issue_code": issue_code, "count": count}
                for issue_code, count in sorted(scene_card_issue_counts.items(), key=lambda item: (-item[1], item[0]))
                if issue_code
            ],
        },
    }
