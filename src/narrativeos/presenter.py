from __future__ import annotations

from typing import List, Sequence

from .models import ChapterPlan, NarrativeState, NarrativeViewModel, RenderedScene, SceneBeat, WorldBible
from .relationship_graph import summarize_relationship_changes
from .sanitizer import sanitize_lines, sanitize_text


def _display_name(state: NarrativeState, actor_id: str) -> str:
    character = state.characters.get(actor_id)
    return character.name if character else actor_id.replace("_", " ")


def _relationship_hints(
    state_before: NarrativeState,
    state_after: NarrativeState,
    scene_beats: Sequence[SceneBeat],
) -> List[str]:
    hints: List[str] = []
    for beat in scene_beats:
        for delta in beat.event.trust_deltas:
            source = _display_name(state_before, delta.source)
            target = _display_name(state_before, delta.target)
            if delta.delta > 0:
                hints.append(f"{source}对{target}多了一点信任。")
            elif delta.delta < 0:
                hints.append(f"{source}对{target}起了新的疑心。")
        for delta in beat.event.debt_deltas[:2]:
            source = _display_name(state_before, str(delta.get("source", "")))
            target = _display_name(state_before, str(delta.get("target", "")))
            debt_type = str(delta.get("debt_type", "亏欠"))
            if source and target:
                hints.append(f"{source}对{target}又添了一笔{debt_type}。")
    hints.extend(summarize_relationship_changes(state_before, state_after))
    return list(dict.fromkeys(sanitize_lines(hints)))[:3]


def _reader_choices(scene_beats: Sequence[SceneBeat]) -> List[str]:
    prompts: List[str] = []
    contextual_choices: List[str] = []
    for beat in scene_beats[-2:]:
        for affordance in beat.event.agency_affordances[:2]:
            prompts.append(
                {
                    "honesty": "当面把真正的心意挑明，赌这一回会不会把关系彻底推到明处。",
                    "selfhood": "先替自己争一条退不回去的路，哪怕眼前的人会因此失望。",
                    "loyalty": "先护住眼前最重要的人，把更重的后果暂时揽到自己身上。",
                    "romance": "顺着那点靠近的冲动往前一步，看对方会不会真的接住你。",
                    "sacrifice": "把代价先揽到自己这一边，让别人暂时看不见裂口落在哪里。",
                    "curiosity": "把真相再往深处追一步，宁可先把场面彻底搅乱。",
                    "ambition": "趁局势还没封死之前抢一条上行的口子，不再只做被推着走的人。",
                    "mutual_truth": "把那句一直没说透的话彻底说完，看看这层关系还能不能活下来。",
                    "public_confession": "在众人面前承认真正的代价，让局势一下子失去回头路。",
                    "release_control": "把那种控制一切的手松开一次，看看关系会不会因此换一种走法。",
                }.get(affordance, "顺着此刻的局势先退半步，再找一个更稳的开口。")
            )
        contextual_choices.extend(
            {
                "truth_trial": [
                    "继续逼近真相，不再替任何人把难听的话咽回去。",
                    "先把场面稳住，再换个更隐蔽的角度试探对方知道多少。",
                ],
                "false_peace": [
                    "顺着表面的平静把这场戏演完，暗地里另找证据。",
                    "干脆把这层虚假的平静撕开，看看谁会先露底。",
                ],
                "temptation": [
                    "先顺着诱惑往前探一步，看代价会先落到谁身上。",
                    "硬把那点动摇压回去，免得它在更坏的时候反咬回来。",
                ],
                "mask_crack": [
                    "趁面具裂开时把心里话挑明，不再给自己留遮掩的台阶。",
                    "先把裂口遮住，等局势过去以后再慢慢追问。",
                ],
                "confession_window": [
                    "抓住这个窗口把最重的一句说完，哪怕接下来会彻底翻脸。",
                    "先试探对方能承受到哪一步，再决定要不要说透。",
                ],
            }.get(beat.event.scene_function, [])
        )
    deduped = list(dict.fromkeys(prompts))
    for option in contextual_choices:
        if option not in deduped:
            deduped.append(option)
    for fallback in [
        "先把眼前这一步走稳，再决定要不要把真相彻底翻出来。",
        "宁可把关系逼到边缘，也要看看这条路到底通向哪里。",
        "先退半步守住分寸，换一个不那么伤人的开口方式。",
    ]:
        if fallback not in deduped:
            deduped.append(fallback)
    return deduped[:3]


def present_scene_for_reader(
    world: WorldBible,
    state_before: NarrativeState,
    state_after: NarrativeState,
    chapter_plan: ChapterPlan,
    scene_beats: Sequence[SceneBeat],
    rendered_scene: RenderedScene,
) -> NarrativeViewModel:
    recap_lines = []
    for previous_title in state_before.timeline[-2:]:
        recap_lines.append(previous_title)
    recap = sanitize_text("前情提要：" + "；".join(recap_lines)) if recap_lines else "故事刚刚开始。"

    scene_card = {
        "title": sanitize_text(rendered_scene.story_title or chapter_plan.scene_intent.label),
        "summary": sanitize_text(rendered_scene.chapter_summary or rendered_scene.image_caption),
        "quote": sanitize_text(rendered_scene.pull_quote),
        "palette_hint": sanitize_text(rendered_scene.palette_hint or ",".join(world.creator_controls.theme_targets[:2])),
        "story_beats": sanitize_lines(rendered_scene.story_beats),
        "visual_details": sanitize_lines(rendered_scene.visual_details),
    }

    return NarrativeViewModel(
        chapter_title=sanitize_text(rendered_scene.story_title or chapter_plan.scene_intent.label),
        chapter_index=state_after.chapter_index,
        recap=recap,
        body=sanitize_text(rendered_scene.premium_prose),
        scene_card=scene_card,
        choices=_reader_choices(scene_beats),
        relationship_hints=_relationship_hints(state_before, state_after, scene_beats),
        can_continue=state_after.story_phase != "aftermath",
    )
