from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_SCHEMA_VERSION = (
    "reader_storybook_title_homogenization_history/v1"
)
READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_FILENAME = (
    "reader_storybook_long_route_smoke_history.json"
)
READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT = 20
READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD = 3
TITLE_HOMOGENIZATION_WARNING_KIND = "title_homogenization_non_blocking"


def reader_storybook_title_homogenization_history_path(base_dir: Path) -> Path:
    return Path(base_dir) / "artifacts" / READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_FILENAME


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pair_key(non_jade_world_id: str, jade_world_id: str) -> Tuple[str, str]:
    return (str(non_jade_world_id or "").strip(), str(jade_world_id or "").strip())


def _normalize_world_ids(items: Any) -> List[str]:
    normalized: List[str] = []
    for item in list(items or []):
        candidate = str(item or "").strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_cross_pack_distinctness_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "non_jade_world_id": str(item.get("non_jade_world_id") or "").strip(),
        "jade_world_id": str(item.get("jade_world_id") or "").strip(),
        "title_similarity": round(_safe_float(item.get("title_similarity")), 3),
        "quote_similarity": round(_safe_float(item.get("quote_similarity")), 3),
        "passes_min_difference": bool(item.get("passes_min_difference", False)),
    }


def _normalize_warning_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "non_jade_world_id": str(item.get("non_jade_world_id") or "").strip(),
        "jade_world_id": str(item.get("jade_world_id") or "").strip(),
        "title_similarity": round(_safe_float(item.get("title_similarity")), 3),
        "quote_similarity": round(_safe_float(item.get("quote_similarity")), 3),
        "warning_kind": str(item.get("warning_kind") or TITLE_HOMOGENIZATION_WARNING_KIND).strip(),
        "message": str(item.get("message") or "").strip(),
    }


def build_reader_storybook_title_homogenization_history_entry(
    *,
    generated_at: str,
    world_ids: List[str],
    cross_pack_distinctness: List[Dict[str, Any]],
    title_homogenization_warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "generated_at": str(generated_at or "").strip(),
        "world_ids": _normalize_world_ids(world_ids),
        "cross_pack_distinctness": [
            normalized
            for normalized in (
                _normalize_cross_pack_distinctness_item(dict(item or {}))
                for item in list(cross_pack_distinctness or [])
            )
            if normalized["non_jade_world_id"] and normalized["jade_world_id"]
        ],
        "title_homogenization_warnings": [
            normalized
            for normalized in (
                _normalize_warning_item(dict(item or {}))
                for item in list(title_homogenization_warnings or [])
            )
            if normalized["non_jade_world_id"] and normalized["jade_world_id"]
        ],
    }


def normalize_reader_storybook_title_homogenization_history(
    payload: Optional[Dict[str, Any]],
    *,
    history_limit: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT,
    promotion_threshold: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
) -> Dict[str, Any]:
    entries = []
    for item in list(dict(payload or {}).get("entries") or []):
        normalized = build_reader_storybook_title_homogenization_history_entry(
            generated_at=str(dict(item or {}).get("generated_at") or "").strip(),
            world_ids=list(dict(item or {}).get("world_ids") or []),
            cross_pack_distinctness=list(dict(item or {}).get("cross_pack_distinctness") or []),
            title_homogenization_warnings=list(
                dict(item or {}).get("title_homogenization_warnings") or []
            ),
        )
        if normalized["generated_at"]:
            entries.append(normalized)
    entries.sort(key=lambda item: item["generated_at"], reverse=True)
    limit = max(1, int(history_limit or READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT))
    entries = entries[:limit]
    return {
        "schema_version": READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_SCHEMA_VERSION,
        "available": bool(entries),
        "history_limit": limit,
        "promotion_threshold": max(
            1, int(promotion_threshold or READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD)
        ),
        "entry_count": len(entries),
        "latest_generated_at": entries[0]["generated_at"] if entries else None,
        "entries": entries,
    }


def append_reader_storybook_title_homogenization_history_entry(
    history_payload: Optional[Dict[str, Any]],
    entry: Dict[str, Any],
    *,
    history_limit: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT,
    promotion_threshold: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
) -> Dict[str, Any]:
    normalized = normalize_reader_storybook_title_homogenization_history(
        history_payload,
        history_limit=history_limit,
        promotion_threshold=promotion_threshold,
    )
    new_entry = build_reader_storybook_title_homogenization_history_entry(
        generated_at=str(entry.get("generated_at") or "").strip(),
        world_ids=list(entry.get("world_ids") or []),
        cross_pack_distinctness=list(entry.get("cross_pack_distinctness") or []),
        title_homogenization_warnings=list(entry.get("title_homogenization_warnings") or []),
    )
    entries = [new_entry, *list(normalized.get("entries") or [])] if new_entry["generated_at"] else list(
        normalized.get("entries") or []
    )
    return normalize_reader_storybook_title_homogenization_history(
        {"entries": entries},
        history_limit=history_limit,
        promotion_threshold=promotion_threshold,
    )


def load_reader_storybook_title_homogenization_history(
    *,
    path: Optional[Path] = None,
    base_dir: Optional[Path] = None,
    history_limit: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_HISTORY_LIMIT,
    promotion_threshold: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
) -> Dict[str, Any]:
    resolved_path = path or reader_storybook_title_homogenization_history_path(
        base_dir or Path(__file__).resolve().parents[3]
    )
    if not resolved_path.exists():
        return normalize_reader_storybook_title_homogenization_history(
            {},
            history_limit=history_limit,
            promotion_threshold=promotion_threshold,
        )
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return normalize_reader_storybook_title_homogenization_history(
        payload,
        history_limit=history_limit,
        promotion_threshold=promotion_threshold,
    )


def _entry_includes_pair(entry: Dict[str, Any], pair: Tuple[str, str]) -> bool:
    world_ids = set(_normalize_world_ids(entry.get("world_ids") or []))
    return pair[0] in world_ids and pair[1] in world_ids


def _warning_for_pair(entry: Dict[str, Any], pair: Tuple[str, str]) -> Optional[Dict[str, Any]]:
    for item in list(entry.get("title_homogenization_warnings") or []):
        if _pair_key(item.get("non_jade_world_id"), item.get("jade_world_id")) == pair:
            return dict(item)
    return None


def _comparison_for_pair(entry: Dict[str, Any], pair: Tuple[str, str]) -> Optional[Dict[str, Any]]:
    for item in list(entry.get("cross_pack_distinctness") or []):
        if _pair_key(item.get("non_jade_world_id"), item.get("jade_world_id")) == pair:
            return dict(item)
    return None


def build_reader_storybook_title_homogenization_trend(
    history_payload: Optional[Dict[str, Any]],
    *,
    promotion_threshold: int = READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD,
) -> Dict[str, Any]:
    normalized_history = normalize_reader_storybook_title_homogenization_history(
        history_payload,
        promotion_threshold=promotion_threshold,
    )
    entries = list(normalized_history.get("entries") or [])
    pair_keys = set()
    for entry in entries:
        for item in list(entry.get("cross_pack_distinctness") or []):
            pair_keys.add(_pair_key(item.get("non_jade_world_id"), item.get("jade_world_id")))
        for item in list(entry.get("title_homogenization_warnings") or []):
            pair_keys.add(_pair_key(item.get("non_jade_world_id"), item.get("jade_world_id")))

    pair_trends = []
    threshold = max(
        1, int(promotion_threshold or normalized_history.get("promotion_threshold") or READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD)
    )
    for non_jade_world_id, jade_world_id in sorted(pair_keys):
        consecutive_warning_count = 0
        eligible_run_count = 0
        latest_warning: Optional[Dict[str, Any]] = None
        latest_warning_at: Optional[str] = None
        latest_comparison: Optional[Dict[str, Any]] = None
        latest_comparison_at: Optional[str] = None
        for entry in entries:
            comparison = _comparison_for_pair(entry, (non_jade_world_id, jade_world_id))
            if comparison and latest_comparison is None:
                latest_comparison = comparison
                latest_comparison_at = str(entry.get("generated_at") or "")
            if not _entry_includes_pair(entry, (non_jade_world_id, jade_world_id)):
                continue
            eligible_run_count += 1
            warning = _warning_for_pair(entry, (non_jade_world_id, jade_world_id))
            if warning:
                consecutive_warning_count += 1
                if latest_warning is None:
                    latest_warning = warning
                    latest_warning_at = str(entry.get("generated_at") or "")
                continue
            break
        promoted = consecutive_warning_count >= threshold and consecutive_warning_count > 0
        pair_trends.append(
            {
                "non_jade_world_id": non_jade_world_id,
                "jade_world_id": jade_world_id,
                "eligible_run_count": eligible_run_count,
                "consecutive_warning_count": consecutive_warning_count,
                "latest_seen_at": latest_warning_at,
                "latest_warning_kind": (
                    str(latest_warning.get("warning_kind") or "") if latest_warning else ""
                ),
                "latest_title_similarity": round(
                    _safe_float((latest_comparison or {}).get("title_similarity")), 3
                ),
                "latest_quote_similarity": round(
                    _safe_float((latest_comparison or {}).get("quote_similarity")), 3
                ),
                "trend_status": (
                    "promoted" if promoted else ("watch" if consecutive_warning_count > 0 else "clear")
                ),
                "promoted_to_release_review": promoted,
            }
        )

    promoted_pairs = [
        dict(item)
        for item in pair_trends
        if bool(item.get("promoted_to_release_review", False))
    ]
    if not entries:
        trend_status = "no_history"
        trend_reason = "no_reader_storybook_smoke_history"
    elif promoted_pairs:
        trend_status = "promoted_pairs_present"
        trend_reason = "title_homogenization_promotion_threshold_met"
    elif any(int(item.get("consecutive_warning_count", 0) or 0) > 0 for item in pair_trends):
        trend_status = "watch"
        trend_reason = "title_homogenization_warning_streak_below_threshold"
    else:
        trend_status = "clear"
        trend_reason = "no_active_title_homogenization_warning_streaks"
    return {
        "available": bool(entries),
        "entry_count": int(normalized_history.get("entry_count", 0) or 0),
        "latest_generated_at": normalized_history.get("latest_generated_at"),
        "threshold": threshold,
        "trend_status": trend_status,
        "trend_reason": trend_reason,
        "promoted_pair_count": len(promoted_pairs),
        "promoted_pairs": promoted_pairs,
        "pair_trends": pair_trends,
    }


def summarize_reader_storybook_title_homogenization_history(
    history_payload: Optional[Dict[str, Any]],
    trend_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_history = normalize_reader_storybook_title_homogenization_history(history_payload)
    trend = dict(
        trend_payload
        or build_reader_storybook_title_homogenization_trend(normalized_history)
    )
    return {
        "available": bool(normalized_history.get("available", False)),
        "entry_count": int(normalized_history.get("entry_count", 0) or 0),
        "latest_generated_at": normalized_history.get("latest_generated_at"),
        "threshold": int(trend.get("threshold", READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD) or READER_STORYBOOK_TITLE_HOMOGENIZATION_PROMOTION_THRESHOLD),
        "trend_status": str(trend.get("trend_status") or ""),
        "trend_reason": str(trend.get("trend_reason") or ""),
        "promoted_pair_count": int(trend.get("promoted_pair_count", 0) or 0),
    }


def promoted_reader_storybook_title_homogenization_pairs_for_world(
    trend_payload: Optional[Dict[str, Any]],
    *,
    world_id: str,
) -> List[Dict[str, Any]]:
    normalized_world_id = str(world_id or "").strip()
    if not normalized_world_id:
        return []
    return [
        dict(item)
        for item in list(dict(trend_payload or {}).get("promoted_pairs") or [])
        if str(item.get("non_jade_world_id") or "").strip() == normalized_world_id
    ]
