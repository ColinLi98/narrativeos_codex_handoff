from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.narrativeos.api import create_app
from src.narrativeos.longform import apply_steering_directive
from src.narrativeos.models import NarrativeState, StepRecord
from src.narrativeos.pipeline import plan_next_turn
from src.narrativeos.providers import StaticCandidateProvider
from src.narrativeos.rendering import TemplateRenderer
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


DEFAULT_ACCOUNT_ID = "reader_demo"
DEFAULT_READER_PASSWORD = "reader-smoke-pass-123"
DEFAULT_WORLD_IDS = ("jade_court_exam", "jade_court_romance", "urban_mystery_lotus_lane")
DEFAULT_TARGET_CHAPTERS = 30
DEFAULT_MIN_TARGET_CHAPTERS = 30
DEFAULT_MAX_ATTEMPTS_PER_CHAPTER = 4
DEFAULT_REVIEW_TARGET_CHAPTERS = (1, 21, 220, 260, 460, 480)


def build_longform_setup(target_chapters: int) -> Dict[str, Any]:
    return {
        "series_storyline_contract": {
            "core_storyline": f"主要关系、外部压力与未解承诺必须稳定推进到至少 {target_chapters} 章，不能中途仓促收尾。",
            "protected_themes": ["关系债", "代价", "未解承诺", "继续读压力"],
        },
        "steering_guardrails": {
            "no_early_ending": True,
        },
    }


def fallback_intent(chapter_target: int, retry_index: int) -> str:
    intents = [
        f"我想把第 {chapter_target} 章继续往前推，但不要让局势提前收尾。",
        f"先把第 {chapter_target} 章的动作和代价落地，再继续往下看。",
        f"这一章先保留关系压力和未解承诺，不要急着解释或回收。",
        f"先顺着局势继续推进，让余波和牵挂继续累积。",
    ]
    return intents[min(retry_index, len(intents) - 1)]


def retry_steering(chapter_target: int, retry_index: int) -> Dict[str, Any]:
    return {
        "steering_type": "mild_steer",
        "current_user_intent": fallback_intent(chapter_target, retry_index),
        "summary": f"第 {chapter_target} 章继续保留长路线张力，避免提前回收。",
    }


def benchmark_world_ids() -> List[str]:
    return [
        str(item["world_id"])
        for item in FileSystemWorldRegistry().list_benchmark_worldpacks()
        if str(item.get("world_id") or "").strip()
    ]


def resolve_world_ids(raw_world_ids: str) -> List[str]:
    requested = [item.strip() for item in str(raw_world_ids or "").split(",") if item.strip()]
    if not requested:
        return []
    resolved: List[str] = []
    for item in requested:
        if item.lower() == "all":
            resolved.extend(benchmark_world_ids())
            continue
        resolved.append(item)
    deduped: List[str] = []
    seen = set()
    for item in resolved:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def review_targets_for(target_chapters: int, requested_targets: Sequence[int]) -> List[int]:
    targets = [int(item) for item in requested_targets if int(item) >= 1 and int(item) <= int(target_chapters)]
    if targets:
        return sorted(set(targets))
    fallback = sorted({1, max(1, min(target_chapters, target_chapters // 2)), target_chapters})
    return [item for item in fallback if item >= 1 and item <= target_chapters]


def build_seed_payload(
    *,
    database_url: str,
    world_ids: List[str],
    target_chapters: int,
    min_target_chapters: int,
    max_attempts_per_chapter: int,
    review_target_chapters: Sequence[int] = DEFAULT_REVIEW_TARGET_CHAPTERS,
) -> Dict[str, Any]:
    repository = SQLAlchemyRepository(database_url=database_url)
    app = create_app(repository=repository)

    app.state.auth_service.register_identity(
        actor_id=DEFAULT_ACCOUNT_ID,
        actor_role="reader",
        password=DEFAULT_READER_PASSWORD,
        account_id=DEFAULT_ACCOUNT_ID,
        display_name="Reader Smoke",
    )

    app.state.billing_service.grant_entitlement(
        {
            "account_id": DEFAULT_ACCOUNT_ID,
            "reader_id": DEFAULT_ACCOUNT_ID,
            "entitlement_type": "play_pass",
            "provider": "smoke_seed",
            "status": "active",
        }
    )

    provider_routing_service = app.state.session_service.provider_routing
    world_summaries: List[Dict[str, Any]] = []

    for world_id in world_ids:
        session_payload = app.state.session_service.create_session(
            world_id,
            reader_id=DEFAULT_ACCOUNT_ID,
            longform_setup=build_longform_setup(target_chapters),
        )
        session_id = str(session_payload["session_id"])
        world_version_id = str(session_payload["world_version_id"])
        runtime = repository.get_runtime_bundle(world_version_id)
        state = NarrativeState.from_dict(repository.get_session(session_id).current_state.to_dict())
        access_snapshot = app.state.billing_service.access_check(
            session_id,
            reader_id=DEFAULT_ACCOUNT_ID,
            account_id=DEFAULT_ACCOUNT_ID,
        )

        chapter_attempt_log: List[Dict[str, Any]] = []
        successful_chapters = 0
        reroute_retry_count = 0
        quote_nonempty_count = 0
        beats_nonempty_count = 0
        sampled_quotes: List[Dict[str, Any]] = []

        while successful_chapters < target_chapters:
            chapter_target = successful_chapters + 1
            chapter_completed = False
            for attempt_index in range(max_attempts_per_chapter):
                state_before = NarrativeState.from_dict(state.to_dict())
                intent = fallback_intent(chapter_target, attempt_index)
                state_before.player_intent = app.state.session_service.intent_parser.parse(intent)
                if attempt_index > 0:
                    apply_steering_directive(
                        state_before,
                        retry_steering(chapter_target, attempt_index),
                        world=runtime.world_record.world,
                    )
                    reroute_retry_count += 1

                candidate_provider = (
                    provider_routing_service.build_candidate_provider(
                        runtime.event_atoms,
                        surface="reader",
                        account_id=DEFAULT_ACCOUNT_ID,
                        session_id=session_id,
                        world_id=runtime.worldpack.world_id,
                        world_version_id=runtime.world_version_id,
                    )
                    if provider_routing_service
                    else StaticCandidateProvider(runtime.event_atoms)
                )
                renderer = (
                    provider_routing_service.build_renderer(
                        surface="reader",
                        account_id=DEFAULT_ACCOUNT_ID,
                        session_id=session_id,
                        world_id=runtime.worldpack.world_id,
                        world_version_id=runtime.world_version_id,
                    )
                    if provider_routing_service
                    else TemplateRenderer()
                )
                result = plan_next_turn(
                    state_before,
                    world=runtime.world_record.world,
                    candidate_provider=candidate_provider,
                    renderer=renderer,
                    candidate_reranker=None,
                    debug=True,
                )
                status = str(result.get("status") or "ok")

                chapter_attempt_log.append(
                    {
                        "chapter_target": chapter_target,
                        "attempt": attempt_index + 1,
                        "status": status,
                        "intent": intent,
                        "chosen_event_title": dict(result.get("chosen_event") or {}).get("title"),
                    }
                )

                if status == "ok":
                    reader_view = dict(result.get("reader_view") or {})
                    scene_card = dict(reader_view.get("scene_card") or {})
                    quote_text = str(scene_card.get("quote") or "").strip()
                    beat_items = [str(item).strip() for item in list(scene_card.get("story_beats") or []) if str(item).strip()]
                    if quote_text:
                        quote_nonempty_count += 1
                    if beat_items:
                        beats_nonempty_count += 1
                    updated_state = NarrativeState.from_dict(result["updated_state"])
                    step_record = StepRecord.from_dict(
                        {
                            "session_id": session_id,
                            "step_index": int(updated_state.chapter_index or chapter_target),
                            "player_input": intent,
                            "intent_vector": dict(state_before.player_intent),
                            "candidate_batch": result["candidate_batch"],
                            "scored_candidates": result["scored_candidates"],
                            "routes": result["routes"],
                            "chosen_event": result["chosen_event"],
                            "chapter_plan": result["chapter_plan"],
                            "scene_beats": result["scene_beats"],
                            "scene_render_spec": result["scene_render_spec"],
                            "rendered_scene": result["rendered_scene"],
                            "reader_view": result["reader_view"],
                            "state_before": state_before.to_dict(),
                            "state_after": updated_state.to_dict(),
                            "critic_trace": result["critic_trace"],
                            "promise_ledger_snapshot": [promise.to_dict() for promise in updated_state.open_promises],
                            "metadata": {
                                "access_tier": access_snapshot.get("access_tier"),
                                "seed_mode": "reader_storybook_long_route_smoke",
                            },
                        }
                    )
                    repository.save_step(
                        step_record,
                        world_version_id=world_version_id,
                        entitlements_snapshot=access_snapshot,
                        cost_estimate=round(max(1, len(reader_view.get("body") or "")) / 1200.0, 3),
                    )
                    if len(sampled_quotes) < 3 or chapter_target in {1, min_target_chapters, target_chapters}:
                        sampled_quotes.append(
                            {
                                "chapter_index": int(reader_view.get("chapter_index") or chapter_target),
                                "chapter_title": str(reader_view.get("chapter_title") or ""),
                                "quote_length": len(quote_text),
                                "beat_count": len(beat_items),
                            }
                        )
                    state = updated_state
                    successful_chapters = int(updated_state.chapter_index or chapter_target)
                    chapter_completed = True
                    break

                if status in {"quality_guard_failed", "payment_required", "restricted"}:
                    continue

                raise RuntimeError(
                    f"reader_long_route_unexpected_status: world={world_id} chapter={chapter_target} attempt={attempt_index + 1} status={status}"
                )

            if not chapter_completed:
                raise RuntimeError(
                    "reader_long_route_seed_stalled: "
                    f"world={world_id} "
                    f"reached={successful_chapters} "
                    f"chapter_target={chapter_target} "
                    f"retries={max_attempts_per_chapter} "
                    f"log_tail={json.dumps(chapter_attempt_log[-8:], ensure_ascii=False)}"
                )

        replay_payload = repository.get_replay(session_id)
        reader_views = list(replay_payload.get("reader_views") or [])
        if len(reader_views) < min_target_chapters:
            raise RuntimeError(
                f"reader_long_route_seed_under_target: world={world_id} replay_views={len(reader_views)} min_target={min_target_chapters}"
            )

        latest_view = dict(reader_views[-1] or {}) if reader_views else {}
        review_targets = review_targets_for(target_chapters, review_target_chapters)
        visible_window = reader_views[-6:]
        visible_sample_indexes = sorted({0, max(0, len(visible_window) // 2), max(0, len(visible_window) - 1)})
        world_summaries.append(
            {
                "world_id": world_id,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "target_chapters": target_chapters,
                "min_target_chapters": min_target_chapters,
                "reached_chapters": len(reader_views),
                "quality_guard_retry_count": 0,
                "payment_resume_count": 0,
                "reroute_retry_count": reroute_retry_count,
                "quote_coverage_rate": round(quote_nonempty_count / max(1, len(reader_views)), 3),
                "beats_coverage_rate": round(beats_nonempty_count / max(1, len(reader_views)), 3),
                "latest_chapter_title": str(latest_view.get("chapter_title") or ""),
                "latest_chapter_index": int(latest_view.get("chapter_index") or len(reader_views)),
                "review_target_chapters": review_targets,
                "review_target_count": len(review_targets),
                "review_target_windows": {
                    "early": [item for item in review_targets if 1 <= item <= 40],
                    "middle": [item for item in review_targets if 220 <= item <= 300],
                    "ending": [item for item in review_targets if 460 <= item <= 500],
                },
                "visible_trajectory_chapter_indexes": [
                    int((item or {}).get("chapter_index") or 0) for item in visible_window
                ],
                "visible_trajectory_sample_indexes": visible_sample_indexes,
                "sampled_quotes": sampled_quotes[:6],
                "chapter_attempt_log_tail": chapter_attempt_log[-12:],
            }
        )

    return {
        "account_id": DEFAULT_ACCOUNT_ID,
        "reader_id": DEFAULT_ACCOUNT_ID,
        "auth_actor_id": DEFAULT_ACCOUNT_ID,
        "auth_password": DEFAULT_READER_PASSWORD,
        "world_ids": list(world_ids),
        "target_chapters": target_chapters,
        "min_target_chapters": min_target_chapters,
        "world_summaries": world_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a multi-chapter Reader session for long-route storybook smoke verification."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--world-ids", default=",".join(DEFAULT_WORLD_IDS))
    parser.add_argument("--target-chapters", type=int, default=DEFAULT_TARGET_CHAPTERS)
    parser.add_argument("--min-target-chapters", type=int, default=DEFAULT_MIN_TARGET_CHAPTERS)
    parser.add_argument("--max-attempts-per-chapter", type=int, default=DEFAULT_MAX_ATTEMPTS_PER_CHAPTER)
    parser.add_argument("--review-target-chapters", default=",".join(str(item) for item in DEFAULT_REVIEW_TARGET_CHAPTERS))
    args = parser.parse_args()
    world_ids = resolve_world_ids(str(args.world_ids or ""))
    if not world_ids:
        raise SystemExit("world_ids_required")
    review_target_chapters = [
        int(item.strip())
        for item in str(args.review_target_chapters or "").split(",")
        if item.strip()
    ]

    payload = build_seed_payload(
        database_url=args.database_url,
        world_ids=world_ids,
        target_chapters=int(args.target_chapters),
        min_target_chapters=int(args.min_target_chapters),
        max_attempts_per_chapter=int(args.max_attempts_per_chapter),
        review_target_chapters=review_target_chapters,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
