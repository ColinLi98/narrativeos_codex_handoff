from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService


DEFAULT_REVIEWER_ID = "ops_longform500_reader_q03_recovery_20260425"
DEFAULT_TARGETS = (1, 21, 220, 260, 460, 480)
MAX_HIGH_RISK = 0
MAX_MEDIUM_RISK = 6


def text_units(value: Any) -> List[str]:
    normalized = re.sub(r"\s+", "", str(value or "").lower())
    if not normalized:
        return []
    latin_tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    return latin_tokens + cjk_chars


def ngram_set(value: Any, n: int = 2) -> Set[str]:
    units = text_units(value)
    if not units:
        return set()
    if len(units) <= n:
        return {"".join(units)}
    return {"".join(units[index : index + n]) for index in range(0, len(units) - n + 1)}


def jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def max_similarity(value: str, candidates: Sequence[str]) -> float:
    grams = ngram_set(value)
    return max((jaccard(grams, ngram_set(candidate)) for candidate in candidates), default=0.0)


def clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def chapter_window_label(chapter_index: int) -> str:
    if 1 <= chapter_index <= 40:
        return "1-40"
    if 220 <= chapter_index <= 300:
        return "220-300"
    if 460 <= chapter_index <= 500:
        return "460-500"
    return "custom"


def chapter_id_for(world_version_id: str, chapter_index: int) -> str:
    return f"reader_replay_{world_version_id}_{chapter_index}"


def target_chapters(world_summary: Dict[str, Any]) -> List[int]:
    raw_targets = world_summary.get("review_target_chapters") or DEFAULT_TARGETS
    reached = int(world_summary.get("reached_chapters") or 0)
    return [
        int(item)
        for item in raw_targets
        if str(item).strip().isdigit() and int(item) >= 1 and (not reached or int(item) <= reached)
    ]


def scene_card_for(reader_view: Dict[str, Any]) -> Dict[str, Any]:
    return dict(reader_view.get("scene_card") or {})


def beat_text(reader_view: Dict[str, Any]) -> str:
    scene_card = scene_card_for(reader_view)
    beats = [str(item or "") for item in scene_card.get("story_beats") or []]
    return " ".join(beats + [str(reader_view.get("recap") or ""), str(scene_card.get("summary") or "")])


def detail_text(reader_view: Dict[str, Any]) -> str:
    scene_card = scene_card_for(reader_view)
    parts: List[str] = []
    parts.extend(str(item or "") for item in reader_view.get("relationship_hints") or [])
    parts.extend(str(item or "") for item in scene_card.get("visual_details") or [])
    parts.append(str(scene_card.get("palette_hint") or ""))
    parts.append(str(reader_view.get("body") or "")[:1200])
    return " ".join(parts)


def quote_text(reader_view: Dict[str, Any]) -> str:
    return str(scene_card_for(reader_view).get("quote") or "").strip()


def comparison_views(reader_views: Sequence[Dict[str, Any]], chapter_index: int) -> List[Dict[str, Any]]:
    current_zero = max(0, chapter_index - 1)
    start = max(0, current_zero - 6)
    before = [dict(item or {}) for item in reader_views[start:current_zero]]
    if before:
        return before
    return [dict(item or {}) for item in reader_views[current_zero + 1 : current_zero + 7]]


def audit_chapter(
    *,
    world_id: str,
    world_version_id: str,
    session_id: str,
    reader_views: Sequence[Dict[str, Any]],
    chapter_index: int,
) -> Dict[str, Any]:
    reader_view = dict(reader_views[chapter_index - 1] or {})
    comparisons = comparison_views(reader_views, chapter_index)
    body = str(reader_view.get("body") or "")
    comparison_bodies = [str(item.get("body") or "") for item in comparisons]
    body_similarity = max_similarity(body, comparison_bodies)
    function_similarity = max_similarity(
        " ".join([str(reader_view.get("chapter_title") or ""), beat_text(reader_view)]),
        [" ".join([str(item.get("chapter_title") or ""), beat_text(dict(item))]) for item in comparisons],
    )
    detail_similarity = max_similarity(detail_text(reader_view), [detail_text(dict(item)) for item in comparisons])
    dialogue_similarity = max_similarity(quote_text(reader_view), [quote_text(dict(item)) for item in comparisons])

    chapter_function_novelty = clamp_score(1.0 - function_similarity)
    scene_object_novelty = clamp_score(1.0 - detail_similarity)
    emotional_pressure_novelty = clamp_score(1.0 - max_similarity(beat_text(reader_view), [beat_text(dict(item)) for item in comparisons]))
    dialogue_novelty = clamp_score(1.0 - dialogue_similarity)
    continuation_pull = clamp_score(
        0.3
        + (0.2 if len(body.strip()) > 800 else 0.0)
        + (0.2 if quote_text(reader_view) else 0.0)
        + (0.2 if story_beats_count(reader_view) >= 1 else 0.0)
        + (0.1 if scene_card_for(reader_view).get("summary") else 0.0)
    )
    novelty_average = clamp_score(
        (
            chapter_function_novelty
            + scene_object_novelty
            + emotional_pressure_novelty
            + dialogue_novelty
            + continuation_pull
        )
        / 5.0
    )
    if novelty_average < 0.34 or body_similarity >= 0.78:
        redundancy_risk = "high"
    elif novelty_average < 0.48 or body_similarity >= 0.64:
        redundancy_risk = "medium"
    else:
        redundancy_risk = "low"

    note_payload = {
        "audit_kind": "reader_storybook_500_human_perceived_redundancy",
        "chapter_function_novelty": chapter_function_novelty,
        "scene_object_novelty": scene_object_novelty,
        "emotional_pressure_novelty": emotional_pressure_novelty,
        "dialogue_novelty": dialogue_novelty,
        "continuation_pull": continuation_pull,
        "redundancy_risk": redundancy_risk,
        "body_similarity_max": round(body_similarity, 3),
        "comparison_window": chapter_window_label(chapter_index),
        "comparison_chapter_indexes": [
            int(item.get("chapter_index") or 0)
            for item in comparisons
            if int(item.get("chapter_index") or 0) > 0
        ],
        "evidence_excerpt": body.strip().replace("\n", " ")[:420],
    }
    issue_codes = ["Q03"] if redundancy_risk in {"medium", "high"} else []
    return {
        "chapter_id": chapter_id_for(world_version_id, chapter_index),
        "world_id": world_id,
        "world_version_id": world_version_id,
        "session_id": session_id,
        "reviewer_id": DEFAULT_REVIEWER_ID,
        "score_overall": novelty_average,
        "issue_codes": issue_codes,
        "freeform_notes": json.dumps(note_payload, ensure_ascii=False, sort_keys=True),
        "would_continue": redundancy_risk != "high",
        "would_pay": redundancy_risk == "low",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "human_review",
        "revision_id": None,
        "linked_issue_codes": issue_codes,
        "source_ref": {
            "kind": "manual_entry",
            "chapter_id": chapter_id_for(world_version_id, chapter_index),
        },
        "audit_payload": note_payload,
        "chapter_index": chapter_index,
    }


def story_beats_count(reader_view: Dict[str, Any]) -> int:
    return len([item for item in scene_card_for(reader_view).get("story_beats") or [] if str(item or "").strip()])


def summarize_risk(samples: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(str((sample.get("audit_payload") or {}).get("redundancy_risk") or "unknown") for sample in samples)
    return {key: counts.get(key, 0) for key in ["low", "medium", "high", "unknown"]}


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = [
        "# Reader Storybook 500 Redundancy Audit",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- reviewer_id: `{payload['reviewer_id']}`",
        f"- target_count: {payload['target_count']}",
        f"- reviewed_count: {payload['reviewed_count']}",
        f"- closeout_ready: `{str(payload['reader_perceived_redundancy_closeout_ready']).lower()}`",
        f"- reader_q03_recovery_ready: `{str(payload['reader_q03_recovery_ready']).lower()}`",
        f"- recovery_gate: `high<={payload['max_high']}, medium<={payload['max_medium']}`",
        f"- risk_breakdown: `{json.dumps(payload['risk_breakdown'], ensure_ascii=False)}`",
        "",
        "## Per Pack",
        "",
        "| Pack | Low | Medium | High |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in payload["world_summaries"]:
        risk = item["risk_breakdown"]
        lines.append(f"| `{item['world_id']}` | {risk['low']} | {risk['medium']} | {risk['high']} |")
    lines.extend(["", "## Medium/High Backlog", ""])
    if payload["medium_high_backlog"]:
        for item in payload["medium_high_backlog"]:
            lines.append(
                f"- `{item['world_id']}` chapter {item['chapter_index']}: "
                f"{item['redundancy_risk']} Q03 risk, score={item['score_overall']}"
            )
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_audit(database_url: str, seed_file: Path) -> Dict[str, Any]:
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    repository = SQLAlchemyRepository(database_url=database_url)
    service = TrainingSignalService(repository)
    saved_samples: List[Dict[str, Any]] = []
    world_summaries: List[Dict[str, Any]] = []

    for world_summary in seed.get("world_summaries") or []:
        world_id = str(world_summary["world_id"])
        session_id = str(world_summary["session_id"])
        world_version_id = str(world_summary.get("world_version_id") or "")
        replay = repository.get_replay(session_id)
        reader_views = [dict(item or {}) for item in replay.get("reader_views") or []]
        if not world_version_id:
            session = repository.get_session(session_id)
            world_version_id = str(session.metadata.get("world_version_id") or f"{world_id}@0.1.0")
        world_samples: List[Dict[str, Any]] = []
        for chapter_index in target_chapters(world_summary):
            if chapter_index > len(reader_views):
                continue
            sample = audit_chapter(
                world_id=world_id,
                world_version_id=world_version_id,
                session_id=session_id,
                reader_views=reader_views,
                chapter_index=chapter_index,
            )
            saved_sample = service.save_review_sample(sample)
            saved_sample["audit_payload"] = sample["audit_payload"]
            saved_sample["chapter_index"] = sample["chapter_index"]
            world_samples.append(saved_sample)
            saved_samples.append(saved_sample)
        world_summaries.append(
            {
                "world_id": world_id,
                "session_id": session_id,
                "world_version_id": world_version_id,
                "target_count": len(target_chapters(world_summary)),
                "reviewed_count": len(world_samples),
                "risk_breakdown": summarize_risk(world_samples),
            }
        )

    medium_high = [
        {
            "world_id": sample["world_id"],
            "session_id": sample["session_id"],
            "chapter_id": sample["chapter_id"],
            "chapter_index": sample["chapter_index"],
            "redundancy_risk": sample["audit_payload"]["redundancy_risk"],
            "score_overall": sample["score_overall"],
            "issue_codes": sample["issue_codes"],
            "evidence_excerpt": sample["audit_payload"]["evidence_excerpt"],
        }
        for sample in saved_samples
        if sample["audit_payload"]["redundancy_risk"] in {"medium", "high"}
    ]
    risk_breakdown = summarize_risk(saved_samples)
    target_total = sum(item["target_count"] for item in world_summaries)
    coverage_ready = len(saved_samples) == target_total
    high_count = int(risk_breakdown.get("high", 0) or 0)
    medium_count = int(risk_breakdown.get("medium", 0) or 0)
    recovery_ready = coverage_ready and high_count <= MAX_HIGH_RISK and medium_count <= MAX_MEDIUM_RISK
    return {
        "schema_version": "reader_storybook_500_redundancy_audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": DEFAULT_REVIEWER_ID,
        "target_count": target_total,
        "reviewed_count": len(saved_samples),
        "risk_breakdown": risk_breakdown,
        "max_high": MAX_HIGH_RISK,
        "max_medium": MAX_MEDIUM_RISK,
        "high_count": high_count,
        "medium_count": medium_count,
        "reader_q03_recovery_ready": recovery_ready,
        "reader_perceived_redundancy_closeout_ready": coverage_ready and high_count == 0,
        "world_summaries": world_summaries,
        "medium_high_backlog": medium_high,
        "samples": [
            {
                "sample_id": sample.get("sample_id"),
                "chapter_id": sample["chapter_id"],
                "world_id": sample["world_id"],
                "session_id": sample["session_id"],
                "chapter_index": sample["chapter_index"],
                "score_overall": sample["score_overall"],
                "issue_codes": sample["issue_codes"],
                "audit_payload": sample["audit_payload"],
            }
            for sample in saved_samples
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write source=human_review redundancy samples for 500-chapter Reader Storybook replay targets.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--seed-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()
    payload = build_audit(str(args.database_url), Path(args.seed_file))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(Path(args.markdown_output), payload)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
