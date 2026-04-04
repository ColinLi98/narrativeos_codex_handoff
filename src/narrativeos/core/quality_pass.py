from __future__ import annotations

import re
from typing import List, Sequence

from ..models import ChapterDraft, NarrativeState, SceneBeat, ScenePlan, WorldBible
from .dialogue import compose_dialogue
from .emotion_actions import compose_emotion_action
from .linter import lint_chapter_draft
from .scene_realizer import realize_hook
from .sensory_grounding import scene_atmosphere, scene_detail


ACTION_MARKERS = ["抬", "落", "偏", "按", "推", "站", "看", "握", "停", "拢"]
DETAIL_MARKERS = ["灯", "袖", "茶", "风", "窗", "案", "影", "香", "光", "声", "纸"]
DETAIL_DENSITY_FLOOR = 1.0 / 180.0


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _actor_name(state_before: NarrativeState, actor_id: str) -> str:
    character = state_before.characters.get(actor_id)
    return character.name if character else actor_id.replace("_", " ")


def _rebuild_draft(paragraphs: Sequence[str], metadata: dict[str, object]) -> ChapterDraft:
    cleaned = [paragraph.strip() for paragraph in paragraphs if paragraph and paragraph.strip()]
    body = "\n\n".join(cleaned)
    return ChapterDraft(
        body=body,
        paragraphs=cleaned,
        dialogue_count=body.count("“"),
        action_count=sum(body.count(marker) for marker in ACTION_MARKERS),
        detail_count=sum(body.count(marker) for marker in DETAIL_MARKERS),
        metadata=metadata,
    )


def _beat_variation_paragraph(world: WorldBible, state_before: NarrativeState, beat: SceneBeat) -> str:
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        return " ".join(
            [
                scene_atmosphere(world, beat),
                f"{actor_name}把目光压回眼前那一点光影里，像是先替自己把最难认的那句话按住。",
                scene_detail(world, beat, repeated=True),
            ]
        )
    return " ".join(
        [
            scene_atmosphere(world, beat),
            compose_emotion_action(world, beat, repeated=True),
            scene_detail(world, beat, repeated=True),
            compose_dialogue(world, state_before, beat, repeated=True),
        ]
    )


def _dialogue_pressure_paragraph(world: WorldBible, state_before: NarrativeState, beat: SceneBeat) -> str:
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        return " ".join(
            [
                scene_atmosphere(world, beat),
                f"{actor_name}低声道：“我先把这句话逼到明处，不再让它只在心里兜圈。”",
                scene_detail(world, beat, repeated=True),
            ]
        )
    return " ".join(
        [
            compose_dialogue(world, state_before, beat, repeated=False),
            compose_emotion_action(world, beat, repeated=False),
        ]
    )


def _detail_reinforcement_paragraph(world: WorldBible, beat: SceneBeat) -> str:
    location = beat.event.location or "眼前这一处"
    return " ".join(
        [
            scene_atmosphere(world, beat),
            scene_detail(world, beat, repeated=False),
            f"{location}里的风、门边回下来的轻响和衣角擦过去的细碎动静，一下子把人心里那点迟疑照得更清。",
        ]
    )


def _dialogic_opening_suffix(state_before: NarrativeState, beat: SceneBeat) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    return f"{actor_name}心里先有了一句没出口的话：“真要走到这里，我也不能再装作什么都没发生。”"


def _strong_hook_line(world: WorldBible, scene_plan: ScenePlan, scene_beats: Sequence[SceneBeat]) -> str:
    hook = realize_hook(world, scene_plan.ending_hook, scene_beats[-1].event.scene_function).strip()
    if any(token in hook for token in ["下一次", "还会", "还没", "追上来", "未说尽"]):
        return hook
    return f"{hook.rstrip('。')}。下一次开口前，真正追上来的那一句话还没有散。"


def repair_chapter_draft(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_plan: ScenePlan,
    scene_beats: Sequence[SceneBeat],
    draft: ChapterDraft,
) -> ChapterDraft:
    if not scene_beats or not draft.paragraphs:
        return draft
    paragraphs = list(draft.paragraphs)
    metadata = dict(draft.metadata)
    remediation_actions: List[str] = list(metadata.get("quality_pass_actions", []))

    seen: set[str] = set()
    for index, paragraph in enumerate(paragraphs[1 : 1 + len(scene_beats)], start=1):
        normalized = _normalize(paragraph)
        if normalized in seen:
            paragraphs[index] = _beat_variation_paragraph(world, state_before, scene_beats[index - 1])
            remediation_actions.append(f"q03_repetition_variation:{index}")
        seen.add(_normalize(paragraphs[index]))

    repaired = _rebuild_draft(paragraphs, metadata)
    lint_report = lint_chapter_draft(repaired.body)

    if float(lint_report.get("repetition_score", 0.0)) > 0.16 and len(scene_beats) >= 2:
        target_index = min(len(scene_beats), 2)
        variation = _beat_variation_paragraph(world, state_before, scene_beats[target_index - 1])
        if target_index < len(paragraphs):
            paragraphs[target_index] = variation
        else:
            paragraphs.append(variation)
        remediation_actions.append("q03_repetition_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if (
        float(lint_report.get("exposition_ratio", 0.0)) > 0.44
        or repaired.dialogue_count < 2
        or len(repaired.body) < 650
    ):
        insert_at = 2 if len(paragraphs) > 2 else len(paragraphs)
        paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        remediation_actions.append("q04_exposition_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if (
        float(lint_report.get("concrete_detail_density", 0.0)) < DETAIL_DENSITY_FLOOR
        or repaired.detail_count < 2
    ):
        target_index = max(1, len(paragraphs) - 2)
        paragraphs[target_index] = " ".join(
            [
                paragraphs[target_index].rstrip(),
                _detail_reinforcement_paragraph(world, scene_beats[-1]),
            ]
        ).strip()
        remediation_actions.append("q05_detail_inline")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    strong_hook = _strong_hook_line(world, scene_plan, scene_beats)
    current_tail = paragraphs[-1] if paragraphs else ""
    current_tail_has_hook = any(token in current_tail for token in ["下一次", "还会", "还没", "追上来", "未说尽"])
    if not current_tail_has_hook:
        if float(lint_report.get("exposition_ratio", 0.0)) > 0.44 or len(paragraphs) < 3:
            paragraphs.append(strong_hook)
            remediation_actions.append("q09_hook_append")
        else:
            paragraphs[-1] = strong_hook
            remediation_actions.append("q09_hook_replace")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if float(lint_report.get("exposition_ratio", 0.0)) > 0.44 and paragraphs:
        paragraphs[0] = " ".join(
            [
                paragraphs[0].rstrip(),
                _dialogic_opening_suffix(state_before, scene_beats[0]),
            ]
        ).strip()
        remediation_actions.append("q04_opening_dialogic")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if float(lint_report.get("repetition_score", 0.0)) > 0.16:
        seen.clear()
        deduped: List[str] = []
        for index, paragraph in enumerate(paragraphs):
            normalized = _normalize(paragraph)
            if normalized in seen:
                if 0 < index <= len(scene_beats):
                    paragraph = _beat_variation_paragraph(world, state_before, scene_beats[index - 1])
                elif index == len(paragraphs) - 1:
                    paragraph = strong_hook
                else:
                    paragraph = _detail_reinforcement_paragraph(world, scene_beats[min(index - 1, len(scene_beats) - 1)])
                remediation_actions.append(f"q03_post_insert_variation:{index}")
            deduped.append(paragraph)
            seen.add(_normalize(paragraph))
        repaired = _rebuild_draft(deduped, metadata)

    repaired.metadata["quality_pass_actions"] = remediation_actions
    repaired.metadata["quality_pass_applied"] = bool(remediation_actions)
    return repaired
