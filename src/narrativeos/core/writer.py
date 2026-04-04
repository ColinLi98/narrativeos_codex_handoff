from __future__ import annotations

from typing import List

from ..models import ChapterDraft, NarrativeState, SceneBeat, ScenePlan, SceneRenderSpec, WorldBible
from .quality_pass import repair_chapter_draft
from .scene_realizer import realize_beat, realize_hook, realize_scene_opening


AXIS_LABELS = {
    "duty": "责任与牵引",
    "ambition": "前途与求胜",
    "reputation": "名声与体面",
    "love": "情意与靠近",
    "selfhood": "自我与抉择",
    "truth": "真相与揭露",
    "reform": "改写旧秩序",
    "destiny": "命运的去向",
    "urban_mystery": "真相与羞耻",
    "xianxia": "誓愿与天命",
    "suspense": "悬疑与压迫",
    "synthetic": "试探与选择",
}


def build_scene_plan(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    chapter_label: str,
    scene_goal: str,
    scene_beats: List[SceneBeat],
    ending_hook: str,
) -> ScenePlan:
    raw_axes = [AXIS_LABELS.get(axis, axis.replace("_", " ")) for axis in (world.creator_controls.theme_targets or world.themes) if axis]
    conflict_axes = list(dict.fromkeys(raw_axes[:3] or ["命运", "真相"]))
    beats = []
    for beat in scene_beats:
        beats.append(
            {
                "function": beat.event.scene_function,
                "focus": beat.event.title,
            }
        )
    return ScenePlan(
        chapter_goal=chapter_label,
        scene_goal=scene_goal,
        conflict_axes=conflict_axes,
        beats=beats,
        ending_hook=ending_hook,
    )


def write_chapter_draft(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_plan: ScenePlan,
    scene_beats: List[SceneBeat],
    render_spec: SceneRenderSpec,
) -> ChapterDraft:
    if not scene_beats:
        return ChapterDraft(body="", paragraphs=[], dialogue_count=0, action_count=0, detail_count=0, metadata={})

    opening = realize_scene_opening(
        world,
        scene_beats[0],
        scene_plan.chapter_goal,
        scene_plan.conflict_axes[0] if scene_plan.conflict_axes else "局势",
    )
    paragraphs = [opening]
    previous_event_id = None
    for beat in scene_beats:
        paragraphs.append(
            realize_beat(
                world,
                state_before,
                beat,
                repeated=previous_event_id == beat.event.event_id,
            )
        )
        previous_event_id = beat.event.event_id
    if scene_plan.ending_hook:
        paragraphs.append(realize_hook(world, scene_plan.ending_hook, scene_beats[-1].event.scene_function))

    body = "\n\n".join(paragraphs)
    draft = ChapterDraft(
        body=body,
        paragraphs=paragraphs,
        dialogue_count=body.count("“"),
        action_count=sum(body.count(marker) for marker in ["抬", "落", "偏", "按", "推", "站", "看", "握", "停", "拢"]),
        detail_count=sum(body.count(marker) for marker in ["灯", "袖", "茶", "风", "窗", "案", "影", "香", "光", "声", "纸"]),
        metadata={
            "target_word_count": render_spec.target_word_count,
            "scene_goal": scene_plan.scene_goal,
            "beat_count": len(scene_beats),
        },
    )
    return repair_chapter_draft(
        world=world,
        state_before=state_before,
        scene_plan=scene_plan,
        scene_beats=scene_beats,
        draft=draft,
    )
