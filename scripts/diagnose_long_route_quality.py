from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.long_route_quality import DEFAULT_READER_CHOICE, STOCK_REFRAIN_REPLACEMENTS
from src.narrativeos.repetition_detector import repetition_signal_bundle
from src.narrativeos.repository import SQLAlchemyRepository


def _text(step: Any) -> str:
    reader_view = getattr(step, "reader_view", None)
    return str(getattr(reader_view, "body", "") or "")


def _choices(step: Any) -> List[str]:
    reader_view = getattr(step, "reader_view", None)
    return [str(item) for item in list(getattr(reader_view, "choices", []) or []) if str(item).strip()]


def _phrase_counts(texts: Iterable[str]) -> Dict[str, int]:
    joined = "\n".join(str(item or "") for item in texts)
    counts = {phrase: joined.count(phrase) for phrase in STOCK_REFRAIN_REPLACEMENTS}
    counts[DEFAULT_READER_CHOICE] = joined.count(DEFAULT_READER_CHOICE)
    return {key: value for key, value in counts.items() if value}


def build_session_quality_diagnostic(repository: SQLAlchemyRepository, *, session_id: str) -> Dict[str, Any]:
    steps = repository.list_steps(session_id)
    bodies = [_text(step) for step in steps]
    choices = [choice for step in steps for choice in _choices(step)]
    events = repository.list_quality_events(session_id=session_id, limit=max(100, len(steps) + 10))
    grounding_counts = Counter(str((event.get("payload") or {}).get("grounding_status") or "unknown") for event in events)
    hard_results = [dict((event.get("payload") or {}).get("hard_constraint_result") or {}) for event in events]
    hard_fail_count = sum(1 for result in hard_results if result and not result.get("ok", True))
    hard_violation_counts: Counter[str] = Counter()
    repair_attempt_count = 0
    repair_success_count = 0
    for result in hard_results:
        if not result:
            continue
        repair_attempt_count += int(result.get("repair_attempts", 0) or 0)
        if result.get("repair_success"):
            repair_success_count += 1
        for rule_id in list(result.get("failed_checks") or []):
            hard_violation_counts[str(rule_id)] += 1
    choice_counts = Counter(choices)
    repetition_bundle = repetition_signal_bundle(bodies)
    return {
        "session_id": session_id,
        "chapter_count": len(steps),
        "chapter_indexes": [int(getattr(step, "step_index", 0) or 0) for step in steps],
        "broken_slot_hits": sum(body.count("被压回去的 、") + body.count("的 、") for body in bodies),
        "phrase_counts": _phrase_counts(bodies + choices),
        "top_repeated_choices": [
            {"text": text, "count": count}
            for text, count in choice_counts.most_common(10)
            if count > 1
        ],
        "grounding_status_counts": dict(grounding_counts),
        "hard_constraint_summary": {
            "event_count": len(hard_results),
            "hard_fail_count": hard_fail_count,
            "repair_attempt_count": repair_attempt_count,
            "repair_success_count": repair_success_count,
            "violation_counts": dict(hard_violation_counts),
        },
        "repetition_signal_bundle": repetition_bundle,
    }


def _markdown(payload: Dict[str, Any]) -> str:
    phrase_lines = [
        f"- `{phrase}`: {count}"
        for phrase, count in sorted(dict(payload.get("phrase_counts") or {}).items(), key=lambda item: (-int(item[1]), item[0]))
    ] or ["- none"]
    choice_lines = [
        f"- {item['count']}x `{item['text']}`"
        for item in list(payload.get("top_repeated_choices") or [])
    ] or ["- none"]
    repetition = dict(payload.get("repetition_signal_bundle") or {})
    hard_summary = dict(payload.get("hard_constraint_summary") or {})
    return "\n".join(
        [
            "# Lane A Long-Route Q03 / Grounding Diagnostic",
            "",
            f"- session_id: `{payload.get('session_id')}`",
            f"- chapters: {payload.get('chapter_count')}",
            f"- chapter range: {min(payload.get('chapter_indexes') or [0])}..{max(payload.get('chapter_indexes') or [0])}",
            f"- broken slot hits: {payload.get('broken_slot_hits')}",
            f"- grounding status counts: {payload.get('grounding_status_counts')}",
            f"- hard constraint summary: {hard_summary}",
            f"- suspicious refrain count: {repetition.get('suspicious_refrain_count')}",
            f"- overall repetition pressure: {repetition.get('overall_repetition_pressure')}",
            "",
            "## Phrase Counts",
            *phrase_lines,
            "",
            "## Repeated Choices",
            *choice_lines,
            "",
            "## Repetition Bundle",
            f"- lexical: {repetition.get('lexical_repetition_score')}",
            f"- ngram: {repetition.get('n_gram_repetition_score')}",
            f"- beat structure: {repetition.get('beat_structure_repetition_score')}",
            f"- examples: {repetition.get('suspicious_refrain_examples')}",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose long-route Q03 and grounding status for a persisted Reader session.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--markdown-out")
    args = parser.parse_args()
    repository = SQLAlchemyRepository(database_url=str(args.database_url))
    payload = build_session_quality_diagnostic(repository, session_id=str(args.session_id))
    markdown = _markdown(payload)
    if args.markdown_out:
        path = Path(args.markdown_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
