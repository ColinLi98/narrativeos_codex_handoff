from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import LONGFORM_DUTY_TYPES, ChapterPlan, EventAtom, NarrativeState, PromiseLedgerEntry, WorldBible


DEFAULT_LONGFORM_WORD_BUDGET = 2000
ROLLING_RECAP_LIMIT = 8
LONGFORM_PLAN_KEY = "longform_plan"
LONGFORM_PROGRESS_KEY = "longform_progression"
STORYLINE_CONTRACT_KEY = "series_storyline_contract"
CHARACTER_MEMORY_PROFILES_KEY = "character_memory_profiles"
STEERING_GUARDRAILS_KEY = "steering_guardrails"
MEMORY_COMPRESSION_POLICY_KEY = "memory_compression_policy"
LONGFORM_100_GATE_THRESHOLDS = {
    "pass_rate_min": 0.6,
    "block_rate_max": 0.0,
    "character_drift_rate_max": 0.15,
    "promise_unresolved_rate_max": 0.55,
    "arc_task_repeat_rate_max": 0.65,
    "q09_incidence_rate_max": 0.1,
    "mid_arc_pass_rate_min": 0.55,
    "continuity_signal_chapters_min": 12,
    "mid_arc_signal_completion_ratio_min": 0.33,
    "premature_ending_trigger_rate_max": 0.0,
    "volume_climax_spacing_error_max": 0.35,
}
DEFAULT_MEMORY_COMPRESSION_POLICY = {
    "rolling_recap_limit": 8,
    "active_arc_memory_limit": 12,
    "archive_retrieval_limit": 12,
    "archive_retention_limit": 160,
    "series_archive_prune_margin_chapters": 40,
    "volume_snapshot_every_n_chapters": 1,
    "promote_memory_on_reference_count": 2,
    "volume_context_window": 2,
    "series_snapshot_every_n_volumes": 2,
    "series_snapshot_limit": 3,
    "series_ending_activation_window_chapters": 30,
    "series_terminal_min_completion_ratio": 0.96,
    "timeline_retention_limit": 240,
    "continuation_fact_retention_limit": 120,
    "continuation_visit_retention_limit": 120,
}


def _normalize_storyline_contract(
    contract: Optional[Dict[str, Any]],
    *,
    series_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(contract or {})
    plan = dict(series_plan or {})
    core_storyline = str(payload.get("core_storyline") or plan.get("title") or "").strip()
    protected_themes = [
        str(item).strip()
        for item in (payload.get("protected_themes") or [plan.get("theme_statement")] if plan.get("theme_statement") else [])
        if str(item).strip()
    ]
    milestone_candidates = list(payload.get("milestones") or [])
    milestones = [
        {
            "milestone_id": str(item.get("milestone_id") or f"milestone_{index + 1}"),
            "label": str(item.get("label") or item.get("goal") or f"Milestone {index + 1}"),
            "target_chapter": int(item.get("target_chapter", 0) or 0),
            "status": str(item.get("status") or "planned"),
        }
        for index, item in enumerate(milestone_candidates)
    ]
    return {
        "core_storyline": core_storyline,
        "protected_themes": protected_themes,
        "no_early_ending": bool(payload.get("no_early_ending", True)),
        "milestones": milestones,
        "conflict_policy": str(payload.get("conflict_policy") or "reconcile_and_carry_forward"),
        "storyline_summary": str(payload.get("storyline_summary") or core_storyline),
    }


def _default_character_memory_profile(character_id: str, state: NarrativeState) -> Dict[str, Any]:
    character = state.characters.get(character_id)
    return {
        "structured_memory": {
            "relationship_history": [],
            "promises": [],
            "secrets": [],
            "scars": [str(character.wound.core_wound)] if character else [],
            "faction": "",
            "taboos": [],
            "goals": list(character.public_goals[:2]) if character else [],
        },
        "free_text_memory": [],
        "pending_memory_patches": [],
        "adopted_memory_patches": [],
    }


def _normalize_character_memory_profiles(
    profiles: Optional[Dict[str, Any]],
    *,
    state: NarrativeState,
) -> Dict[str, Dict[str, Any]]:
    payload = dict(profiles or {})
    normalized: Dict[str, Dict[str, Any]] = {}
    for character_id in set(list(state.characters.keys()) + [str(key) for key in payload.keys()]):
        entry = dict(payload.get(character_id) or {})
        baseline = _default_character_memory_profile(character_id, state)
        structured = dict(baseline.get("structured_memory", {}))
        structured.update(dict(entry.get("structured_memory") or {}))
        normalized[str(character_id)] = {
            "structured_memory": structured,
            "free_text_memory": [str(item) for item in entry.get("free_text_memory", baseline.get("free_text_memory", [])) if str(item)],
            "pending_memory_patches": [dict(item) for item in entry.get("pending_memory_patches", baseline.get("pending_memory_patches", []))],
            "adopted_memory_patches": [dict(item) for item in entry.get("adopted_memory_patches", baseline.get("adopted_memory_patches", []))],
        }
    return normalized


def _normalize_steering_guardrails(guardrails: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(guardrails or {})
    return {
        "replan_future_only": bool(payload.get("replan_future_only", True)),
        "no_past_rewrite": bool(payload.get("no_past_rewrite", True)),
        "conflict_policy": str(payload.get("conflict_policy") or "reconcile_and_carry_forward"),
        "no_early_ending": bool(payload.get("no_early_ending", True)),
    }


def configure_interactive_longform_runtime(
    state: NarrativeState,
    *,
    series_storyline_contract: Optional[Dict[str, Any]] = None,
    character_memory_profiles: Optional[Dict[str, Any]] = None,
    steering_guardrails: Optional[Dict[str, Any]] = None,
) -> NarrativeState:
    storyline_contract = _normalize_storyline_contract(series_storyline_contract)
    memory_profiles = _normalize_character_memory_profiles(character_memory_profiles, state=state)
    guardrails = _normalize_steering_guardrails(steering_guardrails)
    state.metadata[STORYLINE_CONTRACT_KEY] = dict(storyline_contract)
    state.metadata[CHARACTER_MEMORY_PROFILES_KEY] = {key: dict(value) for key, value in memory_profiles.items()}
    state.metadata[STEERING_GUARDRAILS_KEY] = dict(guardrails)
    state.storyline_checkpoint = {
        "core_storyline": storyline_contract.get("core_storyline", ""),
        "protected_themes": list(storyline_contract.get("protected_themes", [])),
        "milestone_count": len(storyline_contract.get("milestones", [])),
        "last_updated_chapter": int(state.chapter_index or 0),
        "latest_steering_summary": "",
        "latest_steering_type": "",
    }
    state.character_memory_runtime = {key: dict(value) for key, value in memory_profiles.items()}
    state.replan_checkpoint = {
        "status": "idle",
        "chapter_index": int(state.chapter_index or 0),
        "summary": "",
        "future_only": bool(guardrails.get("replan_future_only", True)),
    }
    if guardrails.get("no_early_ending", True):
        state.metadata["series_terminal_ready"] = False
    return state


def _interactive_contracts_from_state(state: NarrativeState) -> Dict[str, Any]:
    metadata = dict(state.metadata or {})
    return {
        "series_storyline_contract": dict(state.storyline_checkpoint or metadata.get(STORYLINE_CONTRACT_KEY) or {}),
        "character_memory_profiles": dict(state.character_memory_runtime or metadata.get(CHARACTER_MEMORY_PROFILES_KEY) or {}),
        "steering_guardrails": dict(metadata.get(STEERING_GUARDRAILS_KEY) or {}),
    }


def _steering_intent_overrides(summary: str, impacted_characters: List[str], steering_type: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    lowered = summary.lower()
    if any(keyword in summary for keyword in ["感情", "关系", "爱", "真心"]) or steering_type == "mild_steer":
        weights["romance"] = max(weights.get("romance", 0.0), 0.7)
        weights["loyalty"] = max(weights.get("loyalty", 0.0), 0.45)
    if any(keyword in summary for keyword in ["真相", "坦白", "秘密"]) or "truth" in lowered:
        weights["honesty"] = max(weights.get("honesty", 0.0), 0.75)
        weights["selfhood"] = max(weights.get("selfhood", 0.0), 0.45)
    if any(keyword in summary for keyword in ["选择", "命运", "代价", "后果"]) or steering_type == "arc_steer":
        weights["risk"] = max(weights.get("risk", 0.0), 0.5)
        weights["duty"] = max(weights.get("duty", 0.0), 0.45)
    if impacted_characters:
        weights["curiosity"] = max(weights.get("curiosity", 0.0), 0.55)
    return weights


def apply_steering_directive(
    state: NarrativeState,
    steering_directive: Optional[Dict[str, Any]],
    *,
    world: Optional[WorldBible] = None,
) -> Dict[str, Any]:
    directive = dict(steering_directive or {})
    if not directive:
        return {"applied": False}
    summary = str(
        directive.get("current_user_intent")
        or directive.get("summary")
        or directive.get("arc_goal_shift")
        or directive.get("memory_patch_note")
        or "reader_steering"
    ).strip()
    impacted_characters = [
        str(item).strip()
        for item in (
            directive.get("impacted_character_ids")
            or directive.get("affected_characters")
            or []
        )
        if str(item).strip()
    ]
    if not impacted_characters and state.characters:
        impacted_characters = list(state.characters.keys())[:2]
    steering_type = str(
        directive.get("steering_type")
        or ("memory_steer" if directive.get("memory_patch_note") or directive.get("character_memory_patch") else ("arc_steer" if directive.get("affected_arc_id") or directive.get("arc_goal_shift") else "mild_steer"))
    )
    steering_id = str(directive.get("steering_id") or f"steer::{state.world_id}::{int(state.chapter_index or 0) + 1}::{len(state.steering_ledger) + 1}")
    intent_overrides = dict(directive.get("intent_override") or {})
    intent_overrides.update(_steering_intent_overrides(summary, impacted_characters, steering_type))
    if intent_overrides:
        state.player_intent = {**dict(state.player_intent or {}), **intent_overrides}
    entry = {
        "steering_id": steering_id,
        "chapter_index": int(state.chapter_index or 0) + 1,
        "steering_type": steering_type,
        "summary": summary,
        "impacted_character_ids": impacted_characters,
        "affected_arc_id": str(directive.get("affected_arc_id") or state.current_arc_id or ""),
        "memory_patch_note": str(directive.get("memory_patch_note") or ""),
        "intent_override": intent_overrides,
    }
    state.steering_ledger = [dict(item) for item in state.steering_ledger] + [entry]
    state.metadata["payoff_pressure"] = round(min(1.0, float(state.metadata.get("payoff_pressure", 0.0) or 0.0) + 0.08), 3)
    state.metadata["recent_cross_pressure"] = True
    cross_threads = list(state.metadata.get("cross_pressure_threads", []))
    cross_threads.append(
        {
            "thread_id": steering_id,
            "status": "open",
            "summary": summary,
            "steering_type": steering_type,
            "opened_at_chapter": int(state.chapter_index or 0),
            "impacted_characters": impacted_characters,
        }
    )
    state.metadata["cross_pressure_threads"] = cross_threads[-12:]
    if directive.get("memory_patch_note") or directive.get("character_memory_patch"):
        memory_note = str(directive.get("memory_patch_note") or directive.get("character_memory_patch") or summary).strip()
        for character_id in impacted_characters:
            runtime_entry = dict(state.character_memory_runtime.get(character_id) or _default_character_memory_profile(character_id, state))
            pending = list(runtime_entry.get("pending_memory_patches", []))
            pending.append(
                {
                    "patch_id": f"{steering_id}::{character_id}",
                    "note": memory_note,
                    "chapter_index": int(state.chapter_index or 0) + 1,
                    "status": "pending",
                }
            )
            runtime_entry["pending_memory_patches"] = pending[-10:]
            state.character_memory_runtime[character_id] = runtime_entry
    if steering_type in {"arc_steer", "memory_steer"}:
        chapter_task = dict(state.current_chapter_task or {})
        if chapter_task:
            chapter_task["objective"] = f"{chapter_task.get('objective', '推进当前章节。')} 用户引导：{summary}"
            chapter_task["promise_actions"] = list(dict.fromkeys(list(chapter_task.get("promise_actions", [])) + ["maintain_continuity", "replan_future_arc"]))
            state.current_chapter_task = chapter_task
    state.storyline_checkpoint = {
        **dict(state.storyline_checkpoint or {}),
        "latest_steering_type": steering_type,
        "latest_steering_summary": summary,
        "last_updated_chapter": int(state.chapter_index or 0) + 1,
    }
    guardrails = dict(_interactive_contracts_from_state(state).get("steering_guardrails") or {})
    state.replan_checkpoint = {
        "status": "triggered" if steering_type in {"arc_steer", "memory_steer"} else "soft",
        "summary": summary,
        "steering_id": steering_id,
        "steering_type": steering_type,
        "future_only": bool(guardrails.get("replan_future_only", True)),
        "chapter_index": int(state.chapter_index or 0) + 1,
        "affected_arc_id": str(directive.get("affected_arc_id") or state.current_arc_id or ""),
    }
    _record_replan_event(
        state,
        mode="strong" if steering_type in {"arc_steer", "memory_steer"} else "soft",
        reason=f"steering::{steering_type}",
        chapter_index=int(state.chapter_index or 0) + 1,
        volume_id=state.current_volume_id,
        arc_id=state.current_arc_id,
    )
    memory_unit = {
        "memory_id": f"steering::{steering_id}",
        "memory_type": "steering_directive",
        "scope": state.current_arc_id or state.current_volume_id or state.current_series_id or "series",
        "entity_refs": {
            "character": impacted_characters,
            "arc": [state.current_arc_id] if state.current_arc_id else [],
            "volume": [state.current_volume_id] if state.current_volume_id else [],
        },
        "summary": summary,
        "importance": 0.85,
        "created_chapter": int(state.chapter_index or 0) + 1,
        "last_referenced_chapter": int(state.chapter_index or 0) + 1,
        "resolution_status": "active",
    }
    state.active_arc_memory = [dict(item) for item in state.active_arc_memory] + [memory_unit]
    return {"applied": True, "entry": entry, "replan_checkpoint": dict(state.replan_checkpoint)}


def longform_min_end_turn_floor(total_target_chapters: int) -> int:
    target = max(1, int(total_target_chapters))
    return max(12, min(target, int(round(target * float(LONGFORM_100_GATE_THRESHOLDS["mid_arc_signal_completion_ratio_min"])))))


def _longform_plan_from_state(state: NarrativeState, world: Optional[WorldBible] = None) -> Dict[str, Any]:
    metadata = dict(state.metadata or {})
    plan = dict(metadata.get(LONGFORM_PLAN_KEY) or {})
    if plan.get("series_plan"):
        return {
            "series_plan": dict(plan.get("series_plan") or {}),
            "volume_plans": [dict(item) for item in plan.get("volume_plans", [])],
            "arc_plans": [dict(item) for item in plan.get("arc_plans", [])],
            "chapter_budget_policy": dict(plan.get("chapter_budget_policy") or {}),
        }
    if world is None:
        return {}
    world_plan = dict((world.creator_controls.metadata or {}).get(LONGFORM_PLAN_KEY) or {})
    if not world_plan:
        return {}
    return {
        "series_plan": dict(world_plan.get("series_plan") or {}),
        "volume_plans": [dict(item) for item in world_plan.get("volume_plans", [])],
        "arc_plans": [dict(item) for item in world_plan.get("arc_plans", [])],
        "chapter_budget_policy": dict(world_plan.get("chapter_budget_policy") or {}),
    }


def configure_longform_runtime(
    state: NarrativeState,
    *,
    series_plan: Dict[str, Any],
    volume_plans: List[Dict[str, Any]],
    arc_plans: List[Dict[str, Any]],
    chapter_budget_policy: Dict[str, Any],
    memory_compression_policy: Optional[Dict[str, Any]] = None,
    world: Optional[WorldBible] = None,
) -> NarrativeState:
    state.metadata[LONGFORM_PLAN_KEY] = {
        "series_plan": dict(series_plan or {}),
        "volume_plans": [dict(item) for item in volume_plans or []],
        "arc_plans": [dict(item) for item in arc_plans or []],
        "chapter_budget_policy": dict(chapter_budget_policy or {}),
    }
    state.metadata[MEMORY_COMPRESSION_POLICY_KEY] = {
        **dict(DEFAULT_MEMORY_COMPRESSION_POLICY),
        **dict(memory_compression_policy or {}),
    }
    state.metadata["longform_plan_enabled"] = bool(series_plan)
    total_target_chapters = int(series_plan.get("total_chapter_target", 0) or 0)
    if total_target_chapters:
        min_turn_floor = longform_min_end_turn_floor(total_target_chapters)
        state.min_end_turn = max(int(state.min_end_turn), min_turn_floor)
        state.metadata["longform_min_end_turn_floor"] = min_turn_floor
    if chapter_budget_policy:
        state.word_budget = int(chapter_budget_policy.get("default_target_words") or state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET)
    if world is not None:
        sync_longform_progression(state, world)
    return state


def _memory_compression_policy(state: NarrativeState, world: Optional[WorldBible] = None) -> Dict[str, Any]:
    metadata = dict(state.metadata or {})
    policy = dict(metadata.get(MEMORY_COMPRESSION_POLICY_KEY) or {})
    if not policy and world is not None:
        world_policy = dict((world.creator_controls.metadata or {}).get(MEMORY_COMPRESSION_POLICY_KEY) or {})
        policy = world_policy
    return {**dict(DEFAULT_MEMORY_COMPRESSION_POLICY), **policy}


def _record_replan_event(
    state: NarrativeState,
    *,
    mode: str,
    reason: str,
    chapter_index: int,
    volume_id: Optional[str],
    arc_id: Optional[str],
) -> None:
    entry = {
        "mode": mode,
        "reason": reason,
        "chapter_index": int(chapter_index),
        "volume_id": volume_id,
        "arc_id": arc_id,
    }
    state.replan_history = [dict(item) for item in state.replan_history] + [entry]
    metrics = dict(state.replan_stability_metrics or {})
    metrics["total_replans"] = int(metrics.get("total_replans", 0) or 0) + 1
    counter_key = f"{mode}_replans"
    metrics[counter_key] = int(metrics.get(counter_key, 0) or 0) + 1
    state.replan_stability_metrics = metrics


def active_replan_debt(state: NarrativeState) -> Dict[str, Any]:
    payload = dict((state.metadata or {}).get("replan_debt") or {})
    active_until = int(payload.get("active_until_chapter", 0) or 0)
    chapter_index = int(state.chapter_index or 0)
    if active_until and chapter_index <= active_until:
        return payload
    return {}


def record_replan_debt(
    state: NarrativeState,
    *,
    chapter_index: int,
    issue_codes: Sequence[str],
) -> None:
    normalized_issue_codes = [str(item) for item in issue_codes if str(item)]
    if not {"Q07", "Q09"} & set(normalized_issue_codes):
        return
    recent_steering = [
        dict(item)
        for item in list(state.steering_ledger or [])
        if int(chapter_index) - int(dict(item).get("chapter_index", 0) or 0) <= 10
    ]
    if not recent_steering:
        return
    existing = dict((state.metadata or {}).get("replan_debt") or {})
    intensity = int(existing.get("intensity", 0) or 0) + 1
    state.metadata["replan_debt"] = {
        "status": "active",
        "issue_codes": sorted(set(list(existing.get("issue_codes") or []) + normalized_issue_codes)),
        "last_trigger_chapter": int(chapter_index),
        "active_until_chapter": max(int(existing.get("active_until_chapter", 0) or 0), int(chapter_index) + 10),
        "intensity": min(3, intensity),
        "latest_steering_id": str(recent_steering[-1].get("steering_id") or ""),
        "latest_steering_type": str(recent_steering[-1].get("steering_type") or ""),
        "reason": "interactive_window_q07_q09_rise",
    }


def _snapshot_volume_memory(
    state: NarrativeState,
    *,
    volume_id: str,
    chapter_index: int,
) -> None:
    if not volume_id:
        return
    existing = [dict(item) for item in state.volume_memory_snapshots]
    if any(str(item.get("volume_id") or "") == volume_id for item in existing):
        return
    snapshot = {
        "snapshot_id": f"volume::{volume_id}::{chapter_index}",
        "volume_id": volume_id,
        "completed_at_chapter": int(chapter_index),
        "rolling_recap": [dict(item) for item in state.rolling_recap[-3:]],
        "active_unresolved_promise_ids": [promise.promise_id for promise in state.open_promises],
        "character_memory_refs": sorted(
            [
                character_id
                for character_id, payload in (state.character_memory_runtime or {}).items()
                if dict(payload or {}).get("adopted_memory_patches")
            ]
        ),
        "storyline_checkpoint": dict(state.storyline_checkpoint or {}),
    }
    state.volume_memory_snapshots = existing + [snapshot]
    state.volume_storyline_checkpoint = {
        "last_completed_volume_id": volume_id,
        "last_completed_at_chapter": int(chapter_index),
        "snapshot_id": snapshot["snapshot_id"],
    }


def _snapshot_completed_volume_if_needed(state: NarrativeState) -> None:
    progression = dict((state.metadata or {}).get(LONGFORM_PROGRESS_KEY) or {})
    volume_id = str(progression.get("volume_id") or state.current_volume_id or "")
    if not volume_id:
        return
    volume_chapter_index = int(progression.get("volume_chapter_index", 0) or 0)
    volume_target_chapters = int(progression.get("volume_target_chapters", 0) or 0)
    series_chapter_index = int(progression.get("series_chapter_index", state.chapter_index or 0) or 0)
    series_target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    volume_completed = volume_target_chapters > 0 and volume_chapter_index >= volume_target_chapters
    series_completed = series_target_chapters > 0 and series_chapter_index >= series_target_chapters
    if volume_completed or series_completed:
        _snapshot_volume_memory(
            state,
            volume_id=volume_id,
            chapter_index=series_chapter_index or int(state.chapter_index or 0),
        )


def _snapshot_series_memory_if_needed(state: NarrativeState) -> None:
    policy = _memory_compression_policy(state)
    every_n_volumes = max(1, int(policy.get("series_snapshot_every_n_volumes", 2) or 2))
    snapshot_limit = max(1, int(policy.get("series_snapshot_limit", 3) or 3))
    volume_snapshots = [dict(item) for item in state.volume_memory_snapshots]
    if not volume_snapshots:
        return
    latest_volume_ids = [
        str(item.get("volume_id") or "")
        for item in volume_snapshots
        if str(item.get("volume_id") or "")
    ]
    completed_volume_count = len(latest_volume_ids)
    if completed_volume_count < every_n_volumes:
        return
    latest_completed_volume_id = latest_volume_ids[-1]
    existing = [dict(item) for item in state.series_memory_snapshots]
    if any(str(item.get("latest_completed_volume_id") or "") == latest_completed_volume_id for item in existing):
        return
    if completed_volume_count % every_n_volumes != 0 and not bool((state.metadata or {}).get("series_terminal_ready")):
        return
    chunk = volume_snapshots[-every_n_volumes:]
    chapter_index = int(chunk[-1].get("completed_at_chapter", state.chapter_index) or state.chapter_index or 0)
    unresolved_ids = sorted(
        {
            str(promise_id)
            for item in chunk
            for promise_id in item.get("active_unresolved_promise_ids", [])
            if str(promise_id)
        }
    )
    character_refs = sorted(
        {
            str(character_id)
            for item in chunk
            for character_id in item.get("character_memory_refs", [])
            if str(character_id)
        }
    )
    snapshot = {
        "snapshot_id": f"series::{state.current_series_id or state.world_id}::{latest_completed_volume_id}::{chapter_index}",
        "completed_volume_ids": [str(item.get("volume_id") or "") for item in chunk if str(item.get("volume_id") or "")],
        "latest_completed_volume_id": latest_completed_volume_id,
        "completed_at_chapter": chapter_index,
        "volume_snapshot_refs": [str(item.get("snapshot_id") or "") for item in chunk if str(item.get("snapshot_id") or "")],
        "distilled_recap": [
            str(((item.get("rolling_recap") or [{}])[-1] or {}).get("summary") or "")
            for item in chunk
            if ((item.get("rolling_recap") or [{}])[-1] or {}).get("summary")
        ][:every_n_volumes],
        "active_unresolved_promise_ids": unresolved_ids,
        "character_memory_refs": character_refs,
        "storyline_checkpoint": dict(state.storyline_checkpoint or {}),
    }
    state.series_memory_snapshots = (existing + [snapshot])[-snapshot_limit:]


def _prune_series_archive_memory_if_needed(state: NarrativeState) -> None:
    policy = _memory_compression_policy(state)
    retention_limit = max(1, int(policy.get("archive_retention_limit", 160) or 160))
    prune_margin = max(0, int(policy.get("series_archive_prune_margin_chapters", 40) or 40))
    archive = [dict(item) for item in state.archive_memory]
    latest_series_snapshot = dict((state.series_memory_snapshots or [{}])[-1] or {})
    if not latest_series_snapshot and len(archive) <= retention_limit:
        return
    cutoff = max(0, int(latest_series_snapshot.get("completed_at_chapter", 0) or 0) - prune_margin)
    retained = [
        item
        for item in archive
        if cutoff <= 0
        or int(item.get("last_referenced_chapter", 0) or 0) > cutoff
        or float(item.get("importance", 0.0) or 0.0) >= 0.85
        or str(item.get("resolution_status", "") or "") == "active"
    ]
    if len(retained) > retention_limit:
        retained = sorted(
            retained,
            key=lambda item: (
                float(item.get("importance", 0.0) or 0.0),
                int(item.get("last_referenced_chapter", 0) or 0),
            ),
            reverse=True,
        )[:retention_limit]
    state.archive_memory = retained


def _prune_series_state_history_if_needed(state: NarrativeState) -> None:
    policy = _memory_compression_policy(state)
    timeline_limit = max(1, int(policy.get("timeline_retention_limit", 240) or 240))
    continuation_fact_limit = max(1, int(policy.get("continuation_fact_retention_limit", 120) or 120))
    continuation_visit_limit = max(1, int(policy.get("continuation_visit_retention_limit", 120) or 120))
    if len(state.timeline) > timeline_limit:
        state.timeline = list(state.timeline[-timeline_limit:])

    sticky_facts = [fact for fact in state.world_facts if not str(fact).startswith("continuation::")]
    continuation_facts = [fact for fact in state.world_facts if str(fact).startswith("continuation::")]
    if len(continuation_facts) > continuation_fact_limit:
        continuation_facts = continuation_facts[-continuation_fact_limit:]
    state.world_facts = sticky_facts + continuation_facts

    sticky_event_ids = [event_id for event_id in state.visited_event_ids if "__continuation__" not in str(event_id)]
    continuation_event_ids = [event_id for event_id in state.visited_event_ids if "__continuation__" in str(event_id)]
    if len(continuation_event_ids) > continuation_visit_limit:
        continuation_event_ids = continuation_event_ids[-continuation_visit_limit:]
    state.visited_event_ids = sticky_event_ids + continuation_event_ids


def _update_series_ending_checkpoint(state: NarrativeState) -> None:
    progression = dict((state.metadata or {}).get(LONGFORM_PROGRESS_KEY) or {})
    target_chapters = int(progression.get("series_target_chapters", 0) or 0)
    current_chapters = int(progression.get("series_chapter_index", state.chapter_index or 0) or state.chapter_index or 0)
    if target_chapters <= 0:
        return
    policy = _memory_compression_policy(state)
    activation_window = max(10, int(policy.get("series_ending_activation_window_chapters", 30) or 30))
    min_completion_ratio = float(policy.get("series_terminal_min_completion_ratio", 0.96) or 0.96)
    chapters_remaining = max(0, target_chapters - current_chapters)
    completion_ratio = current_chapters / float(max(1, target_chapters))
    in_final_window = chapters_remaining <= activation_window
    terminal_ready = bool(
        completion_ratio >= min_completion_ratio
        and in_final_window
        and int(progression.get("volume_chapter_index", 0) or 0) >= int(progression.get("volume_target_chapters", 0) or 0)
    )
    state.metadata["series_terminal_ready"] = terminal_ready
    state.series_ending_checkpoint = {
        "target_chapters": target_chapters,
        "current_chapters": current_chapters,
        "chapters_remaining": chapters_remaining,
        "completion_ratio": round(completion_ratio, 3),
        "activation_window_chapters": activation_window,
        "terminal_min_completion_ratio": min_completion_ratio,
        "status": "ready" if terminal_ready else ("final_window" if in_final_window else "early_locked"),
        "terminal_ready": terminal_ready,
        "current_volume_id": progression.get("volume_id") or state.current_volume_id,
        "current_arc_id": progression.get("arc_id") or state.current_arc_id,
        "series_id": progression.get("series_id") or state.current_series_id,
    }


def _fallback_duty_type(state: NarrativeState, world: WorldBible) -> str:
    duty_cycle = list((world.creator_controls.metadata or {}).get("longform_duty_cycle", []))
    if duty_cycle:
        duty_type = duty_cycle[(max(0, state.chapter_index)) % len(duty_cycle)]
    else:
        duty_type = {
            "setup": "advance_plot",
            "early_rising": "advance_relationship",
            "midpoint": "expand_world",
            "crisis": "resolve_promise",
            "climax": "deliver_climax",
            "aftermath": "pace_breath",
        }.get(state.story_phase, "advance_plot")
    if duty_type not in LONGFORM_DUTY_TYPES:
        duty_type = "advance_plot"
    return duty_type


def _select_volume_for_chapter(volume_plans: List[Dict[str, Any]], chapter_number: int) -> tuple[Dict[str, Any], int]:
    cumulative = 0
    ordered_volumes = sorted(volume_plans, key=lambda item: int(item.get("order", 0)))
    current_volume = ordered_volumes[-1]
    current_index = chapter_number
    for volume in ordered_volumes:
        target_chapters = max(1, int(volume.get("target_chapters", 1)))
        if chapter_number <= cumulative + target_chapters:
            current_volume = volume
            current_index = chapter_number - cumulative
            break
        cumulative += target_chapters
    return current_volume, current_index


def _select_arc_for_chapter(
    arc_plans: List[Dict[str, Any]],
    *,
    volume_id: str,
    chapter_number_in_volume: int,
) -> tuple[Optional[Dict[str, Any]], int]:
    volume_arcs = sorted(
        [dict(item) for item in arc_plans if item.get("volume_id") == volume_id],
        key=lambda item: int(item.get("order", 0)),
    )
    if not volume_arcs:
        return None, chapter_number_in_volume
    cumulative = 0
    current_arc = volume_arcs[-1]
    current_index = chapter_number_in_volume
    for arc in volume_arcs:
        target_chapters = max(1, int(arc.get("target_chapters", 1)))
        if chapter_number_in_volume <= cumulative + target_chapters:
            current_arc = arc
            current_index = chapter_number_in_volume - cumulative
            break
        cumulative += target_chapters
    return current_arc, current_index


def _plan_promise_catalog(plan: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    series_plan = dict(plan.get("series_plan") or {})
    for item in list(series_plan.get("series_promises") or []):
        promise_id = str(dict(item or {}).get("promise_id") or "")
        if promise_id:
            catalog[promise_id] = dict(item or {})
    for volume in list(plan.get("volume_plans") or []):
        for item in list(dict(volume or {}).get("volume_promises") or []):
            promise_id = str(dict(item or {}).get("promise_id") or "")
            if promise_id:
                catalog[promise_id] = dict(item or {})
    for arc in list(plan.get("arc_plans") or []):
        for item in list(dict(arc or {}).get("arc_promises") or []):
            promise_id = str(dict(item or {}).get("promise_id") or "")
            if promise_id:
                catalog[promise_id] = dict(item or {})
    return catalog


def _instantiate_plan_promise(
    promise: Dict[str, Any],
    *,
    current_chapter: int,
) -> PromiseLedgerEntry:
    source_level = str(promise.get("source_level") or "arc")
    base_horizon = {
        "series": 12,
        "volume": 8,
        "arc": 4,
    }.get(source_level, 4)
    configured_due = int(promise.get("due_by_chapter", 0) or 0)
    due_by_turn = current_chapter + max(2, min(max(2, configured_due), base_horizon))
    return PromiseLedgerEntry(
        promise_id=str(promise.get("promise_id") or f"promise::{current_chapter}"),
        description=str(promise.get("description") or promise.get("label") or ""),
        opened_at_turn=current_chapter,
        due_by_turn=due_by_turn,
        holders=[str(item) for item in list(promise.get("holders") or []) if str(item)],
        fulfillment_modes=["truth", "choice", "confession"],
        status="open",
        stakes=str(promise.get("stakes") or "medium"),
        tags=[source_level, "longform_plan", "runway_seed"],
    )


def _ensure_longform_promise_runway(
    state: NarrativeState,
    *,
    chapter_task: Dict[str, Any],
    plan: Dict[str, Any],
    chapter_number: int,
    total_target_chapters: int,
) -> None:
    if total_target_chapters < 100:
        return
    if chapter_number >= max(1, int(total_target_chapters * 0.8)):
        return
    if bool(chapter_task.get("bridge_only")) and not list(chapter_task.get("promise_targets") or []):
        return
    open_ids = {str(promise.promise_id) for promise in state.open_promises if str(getattr(promise, "status", "")) == "open"}
    closed_ids = {str(item) for item in list((state.metadata or {}).get("closed_promise_ids", []) or []) if str(item)}
    catalog = _plan_promise_catalog(plan)
    desired_targets = [
        str(item)
        for item in list(chapter_task.get("promise_targets") or [])
        if str(item) and str(item) in catalog
    ]
    queue: List[str] = []
    for promise_id in desired_targets:
        if promise_id not in queue:
            queue.append(promise_id)
    if not queue:
        for promise_id in catalog:
            if promise_id not in queue:
                queue.append(promise_id)
    appended = False
    for promise_id in queue:
        if promise_id in open_ids or promise_id in closed_ids:
            continue
        state.open_promises.append(_instantiate_plan_promise(catalog.get(promise_id, {"promise_id": promise_id}), current_chapter=chapter_number))
        open_ids.add(promise_id)
        appended = True
        if len(open_ids) >= 2:
            break
    if appended:
        state.metadata["longform_last_runway_refresh_chapter"] = chapter_number


def _fallback_task(
    state: NarrativeState,
    *,
    chapter_number: int,
    objective_prefix: str,
    volume_id: Optional[str],
    arc_id: Optional[str],
    allow_terminal: bool,
    notes: str,
    world: WorldBible,
) -> Dict[str, Any]:
    duty_type = _fallback_duty_type(state, world)
    return {
        "chapter_task_id": f"{arc_id or volume_id or state.world_id}::chapter_{chapter_number}",
        "objective": f"{objective_prefix}{duty_type}",
        "duty_type": duty_type,
        "target_words": int(state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET),
        "reveal_budget": 1,
        "promise_actions": ["maintain_continuity"],
        "promise_targets": [],
        "allow_terminal": allow_terminal,
        "bridge_only": True,
        "notes": notes,
    }


def sync_longform_progression(state: NarrativeState, world: WorldBible) -> Dict[str, Any]:
    plan = _longform_plan_from_state(state, world)
    series_plan = dict(plan.get("series_plan") or {})
    volume_plans = [dict(item) for item in plan.get("volume_plans", [])]
    arc_plans = [dict(item) for item in plan.get("arc_plans", [])]
    chapter_budget_policy = dict(plan.get("chapter_budget_policy") or {})
    chapter_number = max(1, int(state.chapter_index or 0))
    if not series_plan or not volume_plans:
        fallback_task = _fallback_task(
            state,
            chapter_number=chapter_number,
            objective_prefix=f"{state.story_phase} 阶段默认执行 ",
            volume_id=state.current_volume_id,
            arc_id=state.current_arc_id,
            allow_terminal=False,
            notes="auto_fallback_longform_task",
            world=world,
        )
        state.current_chapter_task = dict(fallback_task)
        state.metadata[LONGFORM_PROGRESS_KEY] = {
            "series_chapter_index": chapter_number,
            "used_fallback": True,
        }
        return dict(state.metadata[LONGFORM_PROGRESS_KEY])

    total_target_chapters = max(1, int(series_plan.get("total_chapter_target", len(volume_plans))))
    if chapter_budget_policy:
        state.word_budget = int(chapter_budget_policy.get("default_target_words") or state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET)
    previous_volume_id = state.current_volume_id
    previous_arc_id = state.current_arc_id
    current_volume, chapter_number_in_volume = _select_volume_for_chapter(volume_plans, chapter_number)
    current_arc, chapter_number_in_arc = _select_arc_for_chapter(
        arc_plans,
        volume_id=str(current_volume.get("volume_id", "")),
        chapter_number_in_volume=chapter_number_in_volume,
    )
    is_final_chapter = chapter_number >= total_target_chapters
    chapter_tasks = list((current_arc or {}).get("chapter_tasks", []))
    if chapter_tasks:
        template = dict(chapter_tasks[(max(0, chapter_number_in_arc - 1)) % len(chapter_tasks)])
        chapter_task = {
            "chapter_task_id": str(template.get("chapter_task_id") or f"{(current_arc or {}).get('arc_id') or current_volume.get('volume_id')}::chapter_{chapter_number}"),
            "objective": str(template.get("objective") or ""),
            "duty_type": str(template.get("duty_type") or _fallback_duty_type(state, world)),
            "target_words": int(template.get("target_words") or state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET),
            "reveal_budget": int(template.get("reveal_budget", chapter_budget_policy.get("default_reveal_budget", 1) if chapter_budget_policy else 1)),
            "promise_actions": list(template.get("promise_actions", [])),
            "promise_targets": list(template.get("promise_targets", [])),
            "allow_terminal": bool(template.get("allow_terminal", False) and is_final_chapter),
            "bridge_only": bool(template.get("bridge_only", False)),
            "notes": str(template.get("notes") or "planned_longform_task"),
        }
        used_fallback = False
    else:
        chapter_task = _fallback_task(
            state,
            chapter_number=chapter_number,
            objective_prefix=f"{current_arc.get('title', '当前弧线')} 默认执行 " if current_arc else "当前章节默认执行 ",
            volume_id=str(current_volume.get("volume_id") or ""),
            arc_id=str((current_arc or {}).get("arc_id") or ""),
            allow_terminal=is_final_chapter,
            notes="auto_fallback_arc_task",
            world=world,
        )
        used_fallback = True
    state.current_series_id = str(series_plan.get("series_id") or state.current_series_id or "")
    state.current_volume_id = str(current_volume.get("volume_id") or state.current_volume_id or "")
    state.current_arc_id = str((current_arc or {}).get("arc_id") or state.current_arc_id or "")
    state.current_chapter_task = dict(chapter_task)
    state.word_budget = int(chapter_task.get("target_words") or state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET)
    _ensure_longform_promise_runway(
        state,
        chapter_task=chapter_task,
        plan=plan,
        chapter_number=chapter_number,
        total_target_chapters=total_target_chapters,
    )
    if previous_volume_id and previous_volume_id != state.current_volume_id:
        _snapshot_volume_memory(
            state,
            volume_id=str(previous_volume_id),
            chapter_index=max(0, chapter_number - 1),
        )
        _record_replan_event(
            state,
            mode="strong",
            reason="volume_boundary",
            chapter_index=chapter_number,
            volume_id=state.current_volume_id,
            arc_id=state.current_arc_id,
        )
    elif previous_arc_id and previous_arc_id != state.current_arc_id:
        _record_replan_event(
            state,
            mode="soft",
            reason="arc_boundary",
            chapter_index=chapter_number,
            volume_id=state.current_volume_id,
            arc_id=state.current_arc_id,
        )
    progression = {
        "series_id": state.current_series_id,
        "series_chapter_index": chapter_number,
        "series_target_chapters": total_target_chapters,
        "volume_id": state.current_volume_id,
        "volume_order": int(current_volume.get("order", 1)),
        "volume_title": str(current_volume.get("title") or ""),
        "volume_chapter_index": chapter_number_in_volume,
        "volume_target_chapters": int(current_volume.get("target_chapters", 1)),
        "arc_id": state.current_arc_id,
        "arc_order": int((current_arc or {}).get("order", 1)),
        "arc_title": str((current_arc or {}).get("title") or ""),
        "arc_chapter_index": chapter_number_in_arc,
        "arc_target_chapters": int((current_arc or {}).get("target_chapters", 1)),
        "task_sequence_index": chapter_number_in_arc,
        "is_final_chapter": is_final_chapter,
        "used_fallback": used_fallback,
        "chapter_task": dict(chapter_task),
    }
    state.metadata[LONGFORM_PROGRESS_KEY] = dict(progression)
    return progression


def default_chapter_task(state: NarrativeState, world: WorldBible) -> Dict[str, Any]:
    sync_longform_progression(state, world)
    return dict(state.current_chapter_task or {})


def build_longform_context_pack(state: NarrativeState) -> Dict[str, Any]:
    def _rank(memory: Dict[str, Any]) -> tuple[float, int]:
        return (
            float(memory.get("importance", 0.0)),
            int(memory.get("last_referenced_chapter", 0)),
        )

    policy = _memory_compression_policy(state)
    canonical = sorted([dict(item) for item in state.canonical_memory], key=_rank, reverse=True)[:8]
    active_arc = sorted([dict(item) for item in state.active_arc_memory], key=_rank, reverse=True)[: int(policy.get("active_arc_memory_limit", 12) or 12)]
    rolling_recap = sorted([dict(item) for item in state.rolling_recap], key=_rank, reverse=True)[: int(policy.get("rolling_recap_limit", 8) or 8)]
    archive = sorted([dict(item) for item in state.archive_memory], key=_rank, reverse=True)[: int(policy.get("archive_retrieval_limit", 12) or 12)]
    promise_ledger = [promise.to_dict() for promise in state.open_promises]
    interactive_contracts = _interactive_contracts_from_state(state)
    volume_context_window = max(1, int(policy.get("volume_context_window", 2) or 2))
    series_snapshot_limit = max(1, int(policy.get("series_snapshot_limit", 3) or 3))
    return {
        "current_series_id": state.current_series_id,
        "current_volume_id": state.current_volume_id,
        "current_arc_id": state.current_arc_id,
        "current_chapter_task": dict(state.current_chapter_task or {}),
        "progression": dict((state.metadata or {}).get(LONGFORM_PROGRESS_KEY) or {}),
        "word_budget": int(state.word_budget or DEFAULT_LONGFORM_WORD_BUDGET),
        "canonical_memory": canonical,
        "active_arc_memory": active_arc,
        "promise_ledger": promise_ledger,
        "rolling_recap": rolling_recap,
        "archive_memory": archive,
        "volume_memory_snapshots": [dict(item) for item in state.volume_memory_snapshots[-volume_context_window:]],
        "series_memory_snapshots": [dict(item) for item in state.series_memory_snapshots[-series_snapshot_limit:]],
        "steering_ledger": [dict(item) for item in state.steering_ledger[-8:]],
        "storyline_checkpoint": dict(state.storyline_checkpoint or {}),
        "volume_storyline_checkpoint": dict(state.volume_storyline_checkpoint or {}),
        "series_ending_checkpoint": dict(state.series_ending_checkpoint or {}),
        "character_memory_runtime": dict(state.character_memory_runtime or {}),
        "replan_checkpoint": dict(state.replan_checkpoint or {}),
        "replan_history": [dict(item) for item in state.replan_history[-12:]],
        "replan_stability_metrics": dict(state.replan_stability_metrics or {}),
        "series_storyline_contract": dict(interactive_contracts.get("series_storyline_contract") or {}),
        "steering_guardrails": dict(interactive_contracts.get("steering_guardrails") or {}),
    }


def longform_terminal_allowed(state: NarrativeState, chapter_task: Dict[str, Any], event: EventAtom) -> bool:
    if not (state.current_series_id or state.current_volume_id or state.current_arc_id or chapter_task):
        return True
    plan = _longform_plan_from_state(state)
    series_plan = dict(plan.get("series_plan") or {})
    total_target_chapters = int(series_plan.get("total_chapter_target", 0) or 0)
    if bool(chapter_task.get("allow_terminal")):
        if total_target_chapters and int(state.chapter_index or 0) < total_target_chapters:
            return False
        return True
    if total_target_chapters and int(state.chapter_index or 0) < total_target_chapters:
        return False
    return bool((state.metadata or {}).get("series_terminal_ready"))


def evaluate_longform_gate(
    *,
    target_chapters: int,
    completed_chapters: int,
    pass_rate: float,
    block_rate: float,
    stop_reason: str = "",
    completion_ratio: Optional[float] = None,
    mid_arc_pass_rate: Optional[float] = None,
    q09_incidence_rate: float = 0.0,
    character_drift_rate: float,
    promise_unresolved_rate: float,
    arc_task_repeat_rate: float,
    premature_ending_trigger_rate: float,
    volume_climax_spacing_error: float,
) -> Dict[str, Any]:
    applicable = int(target_chapters) >= 100
    resolved_completion_ratio = (
        float(completion_ratio)
        if completion_ratio is not None
        else (int(completed_chapters) / float(max(1, int(target_chapters))))
    )
    continuity_signal_ready = int(completed_chapters) >= int(LONGFORM_100_GATE_THRESHOLDS["continuity_signal_chapters_min"])
    mid_arc_signal_ratio = float(LONGFORM_100_GATE_THRESHOLDS["mid_arc_signal_completion_ratio_min"])
    mid_arc_window_reached = resolved_completion_ratio >= mid_arc_signal_ratio

    def _check(
        name: str,
        *,
        passed: bool,
        actual: Any,
        target: Any,
        blocking: bool = True,
        deferred: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "name": name,
            "passed": passed,
            "actual": actual,
            "target": target,
            "blocking": blocking,
            "deferred": deferred,
            "reason": reason,
        }

    checks = [
        _check(
            "completed_chapters",
            passed=int(completed_chapters) >= int(target_chapters),
            actual=int(completed_chapters),
            target=int(target_chapters),
        ),
        _check(
            "completion_ratio",
            passed=resolved_completion_ratio >= 1.0,
            actual=round(resolved_completion_ratio, 3),
            target=1.0,
        ),
        _check(
            "stop_reason",
            passed=(int(completed_chapters) >= int(target_chapters)) or str(stop_reason or "") == "chapter_budget_reached",
            actual=str(stop_reason or "unknown"),
            target="chapter_budget_reached",
        ),
        _check(
            "mid_arc_window_reached",
            passed=mid_arc_window_reached,
            actual=round(resolved_completion_ratio, 3),
            target=mid_arc_signal_ratio,
        ),
        _check(
            "pass_rate",
            passed=float(pass_rate) >= float(LONGFORM_100_GATE_THRESHOLDS["pass_rate_min"]),
            actual=round(float(pass_rate), 3),
            target=float(LONGFORM_100_GATE_THRESHOLDS["pass_rate_min"]),
            blocking=False,
        ),
        _check(
            "block_rate",
            passed=float(block_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["block_rate_max"]),
            actual=round(float(block_rate), 3),
            target=float(LONGFORM_100_GATE_THRESHOLDS["block_rate_max"]),
            blocking=False,
        ),
        _check(
            "q09_incidence_rate",
            passed=float(q09_incidence_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["q09_incidence_rate_max"]),
            actual=round(float(q09_incidence_rate), 3),
            target=float(LONGFORM_100_GATE_THRESHOLDS["q09_incidence_rate_max"]),
            blocking=False,
        ),
        _check(
            "mid_arc_pass_rate",
            passed=(float(mid_arc_pass_rate or 0.0) >= float(LONGFORM_100_GATE_THRESHOLDS["mid_arc_pass_rate_min"])) if mid_arc_window_reached else True,
            actual=(round(float(mid_arc_pass_rate or 0.0), 3) if mid_arc_window_reached else None),
            target=float(LONGFORM_100_GATE_THRESHOLDS["mid_arc_pass_rate_min"]),
            blocking=False,
            deferred=not mid_arc_window_reached,
            reason=None if mid_arc_window_reached else "mid_arc_window_not_reached",
        ),
        _check(
            "character_drift_rate",
            passed=(float(character_drift_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["character_drift_rate_max"])) if continuity_signal_ready else True,
            actual=(round(float(character_drift_rate), 3) if continuity_signal_ready else None),
            target=float(LONGFORM_100_GATE_THRESHOLDS["character_drift_rate_max"]),
            blocking=False,
            deferred=not continuity_signal_ready,
            reason=None if continuity_signal_ready else "continuity_signal_not_ready",
        ),
        _check(
            "promise_unresolved_rate",
            passed=(float(promise_unresolved_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["promise_unresolved_rate_max"])) if continuity_signal_ready else True,
            actual=(round(float(promise_unresolved_rate), 3) if continuity_signal_ready else None),
            target=float(LONGFORM_100_GATE_THRESHOLDS["promise_unresolved_rate_max"]),
            blocking=False,
            deferred=not continuity_signal_ready,
            reason=None if continuity_signal_ready else "continuity_signal_not_ready",
        ),
        _check(
            "arc_task_repeat_rate",
            passed=(float(arc_task_repeat_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["arc_task_repeat_rate_max"])) if continuity_signal_ready else True,
            actual=(round(float(arc_task_repeat_rate), 3) if continuity_signal_ready else None),
            target=float(LONGFORM_100_GATE_THRESHOLDS["arc_task_repeat_rate_max"]),
            blocking=False,
            deferred=not continuity_signal_ready,
            reason=None if continuity_signal_ready else "continuity_signal_not_ready",
        ),
        _check(
            "premature_ending_trigger_rate",
            passed=float(premature_ending_trigger_rate) <= float(LONGFORM_100_GATE_THRESHOLDS["premature_ending_trigger_rate_max"]),
            actual=round(float(premature_ending_trigger_rate), 3),
            target=float(LONGFORM_100_GATE_THRESHOLDS["premature_ending_trigger_rate_max"]),
            blocking=False,
        ),
        _check(
            "volume_climax_spacing_error",
            passed=float(volume_climax_spacing_error) <= float(LONGFORM_100_GATE_THRESHOLDS["volume_climax_spacing_error_max"]),
            actual=round(float(volume_climax_spacing_error), 3),
            target=float(LONGFORM_100_GATE_THRESHOLDS["volume_climax_spacing_error_max"]),
            blocking=False,
        ),
    ]
    failed_checks = [item["name"] for item in checks if item["blocking"] and not item["passed"]]
    warning_checks = [item["name"] for item in checks if (not item["blocking"]) and (not item["passed"]) and (not item["deferred"])]
    passed = applicable and not failed_checks
    return {
        "mode": "longform_100",
        "applicable": applicable,
        "passed": passed,
        "status": "pass" if passed else ("block" if applicable else "not_applicable"),
        "failed_checks": failed_checks,
        "warning_checks": warning_checks,
        "checks": checks,
        "target_chapters": int(target_chapters),
        "calibrated_thresholds": dict(LONGFORM_100_GATE_THRESHOLDS),
    }


def calibrate_longform_thresholds(worlds: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _quantiles(values: List[float]) -> Dict[str, float]:
        ordered = sorted(float(value) for value in values)
        if not ordered:
            return {"min": 0.0, "p50": 0.0, "p75": 0.0, "max": 0.0}
        def _pick(ratio: float) -> float:
            index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
            return round(ordered[index], 3)
        return {
            "min": round(ordered[0], 3),
            "p50": _pick(0.5),
            "p75": _pick(0.75),
            "max": round(ordered[-1], 3),
        }

    metrics = {
        "completion_ratio": _quantiles([float(item.get("completion_ratio", 0.0) or 0.0) for item in worlds]),
        "mid_arc_pass_rate": _quantiles([float(item.get("mid_arc_pass_rate", 0.0) or 0.0) for item in worlds]),
        "q09_incidence_rate": _quantiles([float(item.get("q09_incidence_rate", 0.0) or 0.0) for item in worlds]),
        "character_drift_rate": _quantiles([float(item.get("character_drift_rate", 0.0) or 0.0) for item in worlds]),
        "promise_unresolved_rate": _quantiles([float(item.get("promise_unresolved_rate", 0.0) or 0.0) for item in worlds]),
        "arc_task_repeat_rate": _quantiles([float(item.get("arc_task_repeat_rate", 0.0) or 0.0) for item in worlds]),
    }
    notes = []
    if metrics["completion_ratio"]["max"] < float(LONGFORM_100_GATE_THRESHOLDS["mid_arc_signal_completion_ratio_min"]):
        notes.append("route_survival_failure_dominates_before_mid_arc")
    if metrics["q09_incidence_rate"]["max"] <= float(LONGFORM_100_GATE_THRESHOLDS["q09_incidence_rate_max"]):
        notes.append("q09_not_primary_blocker_in_current_baseline")
    if metrics["arc_task_repeat_rate"]["p75"] > float(LONGFORM_100_GATE_THRESHOLDS["arc_task_repeat_rate_max"]):
        notes.append("arc_task_repeat_is_high_but_secondary_until_routes_last_longer")
    return {
        "observed_metrics": metrics,
        "recommended_thresholds": dict(LONGFORM_100_GATE_THRESHOLDS),
        "notes": notes,
    }


def archive_longform_chapter(
    state: NarrativeState,
    *,
    chapter_plan: ChapterPlan,
    chosen_event: EventAtom,
    rendered_body: str,
) -> NarrativeState:
    chapter_number = int(state.chapter_index or 0)
    policy = _memory_compression_policy(state)
    chapter_task = dict(chapter_plan.chapter_task or {})
    duty_type = str(chapter_task.get("duty_type") or "")
    if duty_type:
        recent_duty_types = [str(item) for item in list((state.metadata or {}).get("recent_duty_types") or []) if str(item)]
        recent_duty_types.append(duty_type)
        state.metadata["recent_duty_types"] = recent_duty_types[-4:]
    chapter_task_id = str(chapter_task.get("chapter_task_id") or "")
    if chapter_task_id:
        recent_task_ids = [str(item) for item in list((state.metadata or {}).get("recent_chapter_task_ids") or []) if str(item)]
        recent_task_ids.append(chapter_task_id)
        state.metadata["recent_chapter_task_ids"] = recent_task_ids[-4:]
    summary = (rendered_body or "").strip().replace("\n", " ")
    if len(summary) > 240:
        summary = summary[:237] + "..."
    memory_unit = {
        "memory_id": f"recap::{state.world_id}::{chapter_number}",
        "memory_type": "chapter_recap",
        "scope": state.current_arc_id or state.current_volume_id or state.current_series_id or "chapter",
        "entity_refs": {
            "character": list(chosen_event.actors or []),
            "arc": [state.current_arc_id] if state.current_arc_id else [],
            "volume": [state.current_volume_id] if state.current_volume_id else [],
        },
        "summary": summary or chosen_event.summary or chosen_event.title,
        "importance": 0.6,
        "created_chapter": chapter_number,
        "last_referenced_chapter": chapter_number,
        "resolution_status": "active",
    }
    recap_limit = int(policy.get("rolling_recap_limit", ROLLING_RECAP_LIMIT) or ROLLING_RECAP_LIMIT)
    state.rolling_recap = [dict(item) for item in state.rolling_recap] + [memory_unit]
    if len(state.rolling_recap) > recap_limit:
        overflow = state.rolling_recap[:-recap_limit]
        state.archive_memory = [dict(item) for item in state.archive_memory] + overflow
        state.rolling_recap = state.rolling_recap[-recap_limit:]
    state.active_arc_memory = [dict(item) for item in state.active_arc_memory if item.get("memory_id") != memory_unit["memory_id"]]
    state.active_arc_memory.append(
        {
            **memory_unit,
            "memory_id": f"active::{state.world_id}::{chapter_number}",
            "memory_type": "arc_delta",
            "importance": 0.75,
        }
    )
    active_limit = int(policy.get("active_arc_memory_limit", 12) or 12)
    if len(state.active_arc_memory) > active_limit:
        overflow = state.active_arc_memory[:-active_limit]
        state.archive_memory = [dict(item) for item in state.archive_memory] + overflow
        state.active_arc_memory = state.active_arc_memory[-active_limit:]
    adopted_any = False
    for character_id, payload in list((state.character_memory_runtime or {}).items()):
        runtime_entry = dict(payload or {})
        pending = [dict(item) for item in runtime_entry.get("pending_memory_patches", [])]
        adopted = [dict(item) for item in runtime_entry.get("adopted_memory_patches", [])]
        next_pending = []
        for patch in pending:
            if character_id in (chosen_event.actors or []):
                adopted.append({**patch, "status": "adopted", "adopted_at_chapter": chapter_number})
                adopted_any = True
            else:
                next_pending.append(patch)
        runtime_entry["pending_memory_patches"] = next_pending[-10:]
        runtime_entry["adopted_memory_patches"] = adopted[-10:]
        state.character_memory_runtime[character_id] = runtime_entry
    if adopted_any:
        state.storyline_checkpoint = {
            **dict(state.storyline_checkpoint or {}),
            "memory_patch_adopted_at_chapter": chapter_number,
        }
    # Snapshot the just-finished volume on its terminal chapter as well as on
    # later boundary transitions so the final volume is not missed.
    _snapshot_completed_volume_if_needed(state)
    _update_series_ending_checkpoint(state)
    _snapshot_series_memory_if_needed(state)
    _prune_series_archive_memory_if_needed(state)
    _prune_series_state_history_if_needed(state)
    snapshot_every = int(policy.get("volume_snapshot_every_n_chapters", 1) or 1)
    if state.current_volume_id and snapshot_every > 0 and chapter_number % snapshot_every == 0:
        state.volume_storyline_checkpoint = {
            **dict(state.volume_storyline_checkpoint or {}),
            "last_seen_volume_id": state.current_volume_id,
            "last_seen_at_chapter": chapter_number,
        }
    return state
