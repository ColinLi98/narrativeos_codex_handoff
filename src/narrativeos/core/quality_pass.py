from __future__ import annotations

import re
from typing import List, Sequence

from ..long_route_quality import clean_broken_reader_slots
from ..models import ChapterDraft, NarrativeState, SceneBeat, ScenePlan, SceneRenderSpec, WorldBible
from ..repetition_detector import repetition_signal_bundle
from .dialogue import compose_dialogue, compose_late_longform_compact_exchange
from .emotion_actions import compose_emotion_action
from .linter import lint_chapter_draft, story_text_unit_count
from .scene_realizer import realize_hook
from .sensory_grounding import scene_atmosphere, scene_detail


ACTION_MARKERS = ["抬", "落", "偏", "按", "推", "站", "看", "握", "停", "拢", "压", "掠", "碰", "擦", "收", "绷", "卷", "撞", "回", "拨", "绕", "贴", "拖"]
DETAIL_MARKERS = [
    "灯", "袖", "茶", "风", "窗", "案", "影", "香", "光", "声", "纸",
    "栏", "栏杆", "杯", "杯沿", "门框", "木板", "纸页", "桌沿", "桌角", "器物", "石径", "叶影",
    "扫描台", "蓝线", "红灯", "防潮盒", "钝印", "胶痕", "签章", "声纹", "画稿", "盐壳", "录音笔", "话筒",
    "石砖", "空杯", "窗纸", "木栏", "地板", "檐角", "冷光", "回声", "香灰", "笔架", "卷面", "号板",
    "墨迹", "鞋底", "手背", "发梢", "灰尘", "水痕", "潮气", "湿气", "衣摆", "袖口",
    "指节", "呼吸", "肩背", "掌心", "眼睫", "廊柱", "石阶", "花枝", "帘钩", "玉佩", "朱批", "折角",
    "灯座", "玉阶", "香炉", "钟声", "檀香", "冷雾", "山门", "剑穗", "符纸", "云气", "霜意",
    "湖面", "石栏", "水声", "水雾", "月色", "水线", "浪声", "水滴声", "盐味", "潮痕",
    "雨棚", "旧门牌", "雨伞骨", "监控探头", "电流声", "鞋底水声", "翻卷声", "霓虹", "湿雾", "油烟",
]
DETAIL_DENSITY_FLOOR = 1.0 / 180.0
CONTRACT_DETAIL_DENSITY_FLOOR = 0.04
LONGFORM_DETAIL_DENSITY_POLISH_TARGET = 0.085
LONGFORM_DETAIL_DENSITY_POLISH_FLOOR = 0.075
LONGFORM_STOP_READY_DIALOGUE_TARGET = 0.56
LONGFORM_STOP_READY_EXPOSITION_TARGET = 0.50
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?])")
CONTINUATION_HOOK_TOKENS = ["下一次", "还会", "追上来", "未说尽", "后面还有", "下一章", "还没有散"]
LONGFORM_SUSPICIOUS_REFRAIN_REPLACEMENTS = {
    "真话窗口": ("开口的缝隙", "能说实话的一刻", "那道短暂的缝"),
    "把每一步都接住": ("把眼前这一步稳住", "先接住当前的后果", "让下一步落在实处"),
    "别再漏掉": ("别让关键处滑开", "不能再放过这处", "把这处补实"),
    "真正要转向的那句终于逼到眼前": ("那句该说的话贴近眼前", "局面逼出必须回应的一句", "被拖住的回答到了近前"),
    "被压回去的": ("没说出口的", "被藏住的", "被按下去的"),
    "顺着此刻的局势先退半步，再找一个更稳的开口。": ("先稳住眼前的变化，再换一个更清楚的问法。", "先接住当前的后果，再追下一处空白。", "不急着后退，先把这处裂口看清楚。"),
}
SCENE_FUNCTION_LABELS = {
    "false_peace": "表面平静",
    "temptation": "试探",
    "truth_trial": "真相逼近",
    "mask_crack": "裂口",
    "confession_window": "真话窗口",
    "debt_exchange": "旧账回潮",
    "karma_ripening": "因果回响",
    "humiliation": "难堪代价",
    "vow_payment": "誓言偿付",
    "misrecognition": "误解升级",
    "mercy_vs_control": "庇护与控制",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _has_continuation_hook(text: str) -> bool:
    candidate = str(text or "")
    if any(token in candidate for token in CONTINUATION_HOOK_TOKENS):
        return True
    return bool(re.search(r"还没(?:有)?(?:说完|做完|追上|散尽)", candidate))


def _beat_seed(beat: SceneBeat, *, chapter_index: int = 0, extra: int = 0) -> int:
    event_id = str(getattr(beat.event, "event_id", "") or "")
    title = str(getattr(beat.event, "title", "") or "")
    scene_function = str(getattr(beat.event, "scene_function", "") or "")
    beat_index = int(getattr(beat, "beat_index", 0) or 0)
    return sum(ord(char) for char in f"{event_id}:{title}:{scene_function}") + beat_index * 19 + int(chapter_index) * 37 + int(extra)


def _char_ngrams(text: str, *, size: int = 8) -> set[str]:
    normalized = _normalize(text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[index : index + size] for index in range(0, len(normalized) - size + 1)}


def _sentence_similarity(left: str, right: str) -> float:
    left_grams = _char_ngrams(left)
    right_grams = _char_ngrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / float(max(1, len(left_grams | right_grams)))


def _scene_focus_label(beat: SceneBeat) -> str:
    title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or "").strip())
    beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or "").strip())
    if "·" in title:
        title = title.split("·", 1)[1].strip()
    if "·" in beat_label:
        beat_label = beat_label.split("·", 1)[-1].strip()
    if "：" in beat_label:
        beat_label = beat_label.split("：", 1)[1].strip()
    beat_label = beat_label.lstrip("·- ")
    title = title.lstrip("·- ")
    candidate = beat_label or title or SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    if len(candidate) > 12:
        return SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    return candidate


def _paragraph_similarity(left: str, right: str) -> float:
    return _sentence_similarity(left, right)


def _needs_paragraph_replacement(
    paragraph: str,
    previous_paragraphs: Sequence[str],
    *,
    beat: SceneBeat,
    paragraph_index: int,
    total_paragraph_count: int,
) -> bool:
    normalized = _normalize(paragraph)
    if total_paragraph_count >= 6 and paragraph_index < total_paragraph_count - 1 and len(normalized) < 32:
        return True
    if len(normalized) < 60 and len(previous_paragraphs) < 2:
        return False
    focus = _scene_focus_label(beat)
    if focus and len(focus) >= 4 and paragraph.count(focus) >= 3:
        return True
    if paragraph.count("这一步") >= 3:
        return True
    max_similarity = max((_paragraph_similarity(paragraph, prior) for prior in previous_paragraphs), default=0.0)
    if len(normalized) >= 180 and max_similarity >= 0.34:
        return True
    if len(normalized) >= 120 and max_similarity >= 0.42:
        return True
    return False


def _paragraph_replacement(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    paragraph_index: int,
    chapter_index: int,
    previous_paragraphs: Sequence[str],
    source_paragraph: str | None = None,
) -> str:
    candidates = [
        " ".join(
            [
                _dialogue_pressure_paragraph(world, state_before, beat),
                _action_pressure_paragraph(world, state_before, beat),
            ]
        ).strip(),
        " ".join(
            [
                _action_pressure_paragraph(world, state_before, beat),
                _detail_reinforcement_paragraph(
                    world,
                    beat,
                    chapter_index=chapter_index,
                    variant_seed=650 + paragraph_index,
                ),
            ]
        ).strip(),
        " ".join(
            [
                _dialogue_pressure_paragraph(world, state_before, beat),
                _detail_reinforcement_paragraph(
                    world,
                    beat,
                    chapter_index=chapter_index,
                    variant_seed=700 + paragraph_index,
                ),
            ]
        ).strip(),
        _beat_variation_paragraph(world, state_before, beat),
        _action_pressure_paragraph(world, state_before, beat),
        _dialogue_pressure_paragraph(world, state_before, beat),
    ]
    best = candidates[0]
    best_similarity = 1.0
    for candidate in candidates:
        similarity = max((_paragraph_similarity(candidate, prior) for prior in previous_paragraphs), default=0.0)
        if similarity < best_similarity:
            best = candidate
            best_similarity = similarity
    source_anchor = _source_anchor_for_beat(source_paragraph or "", beat)
    if source_anchor and source_anchor not in best:
        best = f"{source_anchor}没有被场面带过。 {best}"
    return best


def _replace_redundant_paragraphs_after_expansion(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    remediation_actions: List[str],
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    rewritten: List[str] = []
    for index, paragraph in enumerate(paragraphs):
        beat = _beat_for_paragraph(paragraph, scene_beats, fallback_index=index)
        if _needs_paragraph_replacement(
            paragraph,
            rewritten,
            beat=beat,
            paragraph_index=index,
            total_paragraph_count=len(paragraphs),
        ):
            paragraph = _paragraph_replacement(
                world=world,
                state_before=state_before,
                beat=beat,
                paragraph_index=index,
                chapter_index=chapter_index,
                previous_paragraphs=rewritten,
                source_paragraph=paragraph,
            )
            remediation_actions.append(f"q03_post_length_paragraph_replace:{index}")
        rewritten.append(paragraph)
    attempts = 0
    while attempts < 4:
        bundle = repetition_signal_bundle(rewritten)
        if float(bundle.get("overall_repetition_pressure", 0.0) or 0.0) < 0.38:
            break
        target_index = None
        for index, paragraph in enumerate(rewritten[:-1]):
            if len(_normalize(paragraph)) < 32:
                target_index = index
                break
        if target_index is None:
            top_pairs = list(bundle.get("top_repeated_paragraph_pairs") or [])
            if top_pairs and float(top_pairs[0].get("similarity", 0.0) or 0.0) >= 0.22:
                target_index = int(top_pairs[0].get("right_paragraph_index", 0) or 0)
        if target_index is None or target_index >= len(rewritten):
            break
        source_paragraph = rewritten[target_index]
        beat = _beat_for_paragraph(source_paragraph, scene_beats, fallback_index=target_index)
        rewritten[target_index] = _paragraph_replacement(
            world=world,
            state_before=state_before,
            beat=beat,
            paragraph_index=target_index + attempts + 100,
            chapter_index=chapter_index,
            previous_paragraphs=rewritten[:target_index],
            source_paragraph=source_paragraph,
        )
        remediation_actions.append(f"q03_bundle_target_replace:{target_index}")
        attempts += 1
    return rewritten


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


def _detail_density_snapshot(paragraphs: Sequence[str]) -> dict[str, float | int]:
    body = "\n\n".join(str(paragraph or "") for paragraph in paragraphs)
    detail_count = sum(body.count(marker) for marker in DETAIL_MARKERS)
    unit_count = story_text_unit_count(body)
    return {
        "detail_count": detail_count,
        "text_unit_count": unit_count,
        "concrete_detail_density": detail_count / float(max(1, unit_count)),
    }


def _beat_variation_paragraph(world: WorldBible, state_before: NarrativeState, beat: SceneBeat) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        return " ".join(
            [
                scene_atmosphere(world, beat, chapter_index=chapter_index),
                f"{actor_name}把目光压回眼前那一点光影里，像是先替自己把最难认的那句话按住。",
                scene_detail(world, beat, repeated=True, chapter_index=chapter_index),
            ]
        )
    return " ".join(
        [
            scene_atmosphere(world, beat, chapter_index=chapter_index),
            compose_emotion_action(world, state_before, beat, repeated=True),
            scene_detail(world, beat, repeated=True, chapter_index=chapter_index),
            compose_dialogue(world, state_before, beat, repeated=True),
        ]
    )


def _dialogue_pressure_paragraph(world: WorldBible, state_before: NarrativeState, beat: SceneBeat) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    seed = _beat_seed(beat, chapter_index=chapter_index)
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        lines = [
            "我先把这句话逼到明处，不再让它只在心里兜圈。",
            "这一回不能照旧绕开，我得换一种说法，也换一种做法。",
            "如果这一步已经露出来，我就不能再让它留给下一次。",
            "我先接住眼前这一下，后面的代价再一件件认。",
        ]
        return " ".join(
            [
                scene_atmosphere(world, beat, chapter_index=chapter_index),
                f"{actor_name}低声道：“{lines[seed % len(lines)]}”",
                scene_detail(world, beat, repeated=True, chapter_index=chapter_index),
            ]
        )
    return " ".join(
        [
            scene_atmosphere(world, beat, chapter_index=chapter_index),
            compose_dialogue(world, state_before, beat, repeated=True),
            compose_emotion_action(world, state_before, beat, repeated=False),
            scene_detail(world, beat, repeated=True, chapter_index=chapter_index),
        ]
    )


def _action_pressure_paragraph(world: WorldBible, state_before: NarrativeState, beat: SceneBeat) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    seed = _beat_seed(beat, chapter_index=chapter_index)
    location = beat.event.location or "眼前这一处"
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    scene_function = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    focus = _scene_focus_label(beat)
    detail = scene_detail(world, beat, repeated=False, chapter_index=chapter_index)
    actor_moves = [
        f"{actor_name}先抬手按住{location}边的门框，又偏头看了{counterpart}一眼，指节在案角那页纸上轻轻一擦，像把原本想退回去的话重新压到了明处。",
        f"{actor_name}没有先把话送出来，只把手背贴在{location}边的桌沿上，等{focus}真正逼到眼前，才把那口气慢慢压稳。",
        f"{actor_name}先把脚步收在{location}边那一线冷光里，视线却一直没从{counterpart}身上移开，像这一步只要退半寸就会把{focus}整个让出去。",
        f"{actor_name}抬手碰了一下{location}边的器物，任那点细响顺着桌沿和门影散开，像在替自己把{focus}硬生生摁到明处。",
    ]
    counterpart_moves = [
        f"{counterpart}没有立刻退，只把衣袖往回一收，脚步在阶前停了一瞬，目光却顺着灯影和窗边那道风重新掠回来，硬是把这一步{scene_function}往前推近了一层。",
        f"{counterpart}没有替场面找台阶，只把呼吸压得更稳，任{location}里的回声和冷光一层层逼近，像逼着{actor_name}把{focus}认得更彻底。",
        f"{counterpart}先抬眼盯住{actor_name}，连指尖碰到案角时那点轻响都没躲开，像要让这一步{scene_function}彻底失去还能装稳的样子。",
        f"{counterpart}并不急着开口，只把身形停在{location}边最亮的那一线，像等{actor_name}自己把{focus}送到再也收不回去的地方。",
    ]
    closers = [
        f"{actor_name}低声道：“这句我不再往回收了。”",
        f"{actor_name}终于把声音压实：“这一步我认，不再拿解释替自己留路。”",
        f"{actor_name}顺着那点停顿把话送了出来：“都已经走到这里，我没法再把{focus}装成没发生。”",
        f"{actor_name}盯着{counterpart}时只落下一句：“这一次我不让它停在半句。”",
    ]
    return " ".join(
        [
            scene_atmosphere(world, beat, chapter_index=chapter_index),
            detail,
            actor_moves[seed % len(actor_moves)],
            counterpart_moves[(seed // 3) % len(counterpart_moves)],
            closers[(seed // 7) % len(closers)],
        ]
    )


def _compact_action_dialogue_sentence(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    location = beat.event.location or "眼前这一处"
    focus = _scene_focus_label(beat) or SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    variants = [
        f"{actor_name}抬手按住{location}边的案角，指节收紧又松开，目光绕过灯影停在{counterpart}身上，低声道：“这一回我认。”",
        f"{counterpart}没有退，反而往前半步看住{actor_name}，袖口一拢又压住桌沿，声音很轻：“别再往回收。”",
        f"{actor_name}把脚步停稳，手背贴着{location}边那道冷光慢慢收紧，终于抬眼：“这句不能再留一半。”",
        f"{counterpart}偏头看了一眼门影，又把手里的纸页推回案上，低声道：“你若认，就现在认。”",
        f"{actor_name}把原先要重复的半句话咽下去，指尖在纸页边缘停住：“我换成行动给你看。”",
        f"{counterpart}垂眼看着案角那道划痕，没让沉默散开：“说到{focus}，就别只停在嘴上。”",
        f"{location}边的门影轻轻一晃，{actor_name}往前站稳半步：“旧账也好，后果也好，我现在接。”",
        f"{counterpart}把茶盏推开一点，杯沿碰出轻响：“那就从眼前这件事开始。”",
        f"{actor_name}没有再解释，只把手里的纸页翻到压痕最深处：“这里，我先补上。”",
        f"{counterpart}看了一眼窗下冷光，声音压得更低：“别让这层代价空过去。”",
    ]
    return variants[seed % len(variants)]


def _detail_reinforcement_paragraph(
    world: WorldBible,
    beat: SceneBeat,
    *,
    chapter_index: int = 0,
    variant_seed: int = 0,
) -> str:
    location = beat.event.location or "眼前这一处"
    scene_function = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    detail = scene_detail(world, beat, repeated=False, chapter_index=chapter_index)
    variants = [
        f"{location}里的风、门、窗、灯影和衣角摩擦出的细响并没有停，连案边那页纸、阶前那点回声和若有若无的香气都把这一步{scene_function}压得更近。",
        f"{location}边的杯沿、门框、纸页和鞋底擦出的轻响层层往回推，像把这一步{scene_function}里每一点迟疑都钉在了桌面、地砖和窗影上。",
        f"{location}里的尘、潮气、木纹、灯火和器物反光一起往人身上贴，连袖角扫过案边时带起的那点声响都让这一步{scene_function}更难装作没发生。",
        f"到了{location}里面，窗纸的冷光、桌沿的磨痕、门边的风和衣摆擦过地面的细响全挤到一起，让这一步{scene_function}不靠解释也能压出重量。",
        f"{location}边最先显出来的是器物、回声和人身上那点收不回去的动作，连案角、门框和空气里的细碎冷意都在替这一步{scene_function}留下更具体的痕。",
        f"{location}里的灯、纸、门影和脚步回响没有替谁遮掩，反而把这一步{scene_function}里每一点犹疑、停顿和后果都逼得更能摸到。",
    ]
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    return " ".join(
        [
            scene_atmosphere(world, beat, chapter_index=chapter_index),
            detail,
            variants[seed % len(variants)],
        ]
    )


def _coverage_gap_bridge_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    location = beat.event.location or "眼前这一处"
    title = _compact_title_anchor(_reader_visible_anchor(str(getattr(beat.event, "title", "") or "")), location=location)
    beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
    summary = _reader_visible_anchor(str(getattr(beat.event, "summary", "") or ""))
    summary = _compact_summary_anchor(summary, title=title, world_title=world.title)
    tags = [
        _reader_visible_anchor(str(item))
        for item in list(getattr(beat.event, "tags", []) or [])
        if _reader_visible_anchor(str(item))
    ]
    tag_anchor = _compact_anchor_line([tag[:42] for tag in tags[:2]])
    anchor_line = _compact_anchor_line(
        [
            _compact_label_anchor(beat_label, title=title),
            title,
            summary,
            _reader_visible_anchor(str(location)),
            "、".join(tags[:3]),
        ]
    )
    dramatic_job = str(getattr(beat, "dramatic_job", "") or "pressure")
    job_label = {
        "entry": "先把事情推到台面上的",
        "pressure": "往前逼近的",
        "pivot": "让局面转过去的",
        "aftermath": "在余波里继续追上来的",
        "echo": "隔一层声响又折回来的",
    }.get(dramatic_job, "最难躲开的")
    detail = scene_detail(world, beat, repeated=False, chapter_index=chapter_index)
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    anchor_subject = title or beat_label or summary or str(location)
    variants = [
        f"{anchor_line or anchor_subject}没有被场面轻轻带过。",
        f"{anchor_line or anchor_subject}压回{location}时，没有再被一句解释遮过去。",
        f"{anchor_line or anchor_subject}真正{job_label}不是旁白，而是当场压到两人面前。",
        f"{location}里的脚步和回声把{anchor_line or anchor_subject}压实，谁都没法再绕开。",
    ]
    bridge = variants[seed % len(variants)].strip()
    if anchor_line and anchor_line not in bridge:
        bridge = " ".join([anchor_line, bridge]).strip()
    anchor_echo = _compact_anchor_line([title, _compact_label_anchor(beat_label, title=title), summary])
    if anchor_echo and anchor_echo not in bridge:
        bridge = f"{bridge} {anchor_echo}没有只停在背景里。"
    if tag_anchor and tag_anchor not in bridge:
        bridge = f"{bridge} {tag_anchor}也被拉回场中。"
    pressure_lines = [
        f"{actor_name}抬手按住案角：“这句我认。” {counterpart}没有替他收场。",
        f"{counterpart}把沉默压住，逼得{actor_name}把退路看清。{actor_name}只回：“这次不能绕。”",
        f"{actor_name}的指节在{location}边停了停。{counterpart}看着他，没有给这层后果留下空白。",
        f"{location}里的门影一晃，{actor_name}把声音压稳：“我接住。” {counterpart}没有退。",
    ]
    detail_tail = f"案角、门框、纸页、杯沿和地板冷光都在{location}边停住。"
    return " ".join([bridge, detail, detail_tail, pressure_lines[(seed // 7) % len(pressure_lines)]]).strip()


def _multi_beat_coverage_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    clauses: List[str] = []
    for offset, beat in enumerate(scene_beats[:6]):
        location = beat.event.location or "眼前这一处"
        title = _compact_title_anchor(_reader_visible_anchor(str(getattr(beat.event, "title", "") or "")), location=location)
        beat_label = _compact_label_anchor(_reader_visible_anchor(str(getattr(beat, "beat_label", "") or "")), title=title)
        summary = _compact_summary_anchor(
            _reader_visible_anchor(str(getattr(beat.event, "summary", "") or "")),
            title=title,
            world_title=world.title,
        )
        tags = [
            _reader_visible_anchor(str(item))
            for item in list(getattr(beat.event, "tags", []) or [])
            if _reader_visible_anchor(str(item))
        ]
        anchor = _compact_anchor_line([beat_label, title, summary, _reader_visible_anchor(str(location)), *[tag[:42] for tag in tags[:1]]])
        if not anchor:
            anchor = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed + offset)
        action_tail = [
            f"{actor_name}把手按到桌沿，没让它从场面里滑过去",
            f"{actor_name}抬眼看住对面，像把这一层后果重新钉回眼前",
            f"{actor_name}停住脚步，让那点声响顺着门影落下来",
            f"{actor_name}压低呼吸，终于把这一步接到自己的动作上",
        ][seed % 4]
        clauses.append(f"{anchor}被{location}里的光和声重新逼近时，{action_tail}。")
    if not clauses:
        return ""
    last_beat = scene_beats[(variant_seed + chapter_index) % len(scene_beats)]
    actor_name = _actor_name(state_before, last_beat.event.actors[0]) if last_beat.event.actors else "那人"
    counterpart = _actor_name(state_before, last_beat.event.actors[1]) if len(last_beat.event.actors) > 1 else "对面那人"
    closers = [
        f"{counterpart}没有替{actor_name}收场，只低声道：“先把眼前这一步说实。”",
        f"{counterpart}把目光留在{actor_name}手边：“这处空白，现在补上。”",
        f"{actor_name}没有再后退，只把声音压低：“我按眼前的后果来。”",
        f"{counterpart}往前半步：“别让这一处从场面里滑开。”",
    ]
    return " ".join(
        [
            scene_atmosphere(world, last_beat, chapter_index=chapter_index),
            " ".join(clauses),
            closers[(variant_seed + chapter_index + len(clauses)) % len(closers)],
        ]
    ).strip()


def _coverage_gap_surface_paragraphs(
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
    max_count: int = 4,
) -> List[str]:
    paragraphs: List[str] = []
    for offset, beat in enumerate(list(scene_beats)[: max(1, int(max_count or 1))]):
        paragraphs.append(
            _coverage_gap_bridge_paragraph(
                world,
                state_before,
                beat,
                variant_seed=variant_seed + offset * 37,
                chapter_index=chapter_index,
            )
        )
    return paragraphs


def _coverage_anchor_echo_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    location = _reader_visible_anchor(str(getattr(beat.event, "location", "") or "")) or "眼前这一处"
    title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or ""))
    beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
    summary = _compact_summary_anchor(
        _reader_visible_anchor(str(getattr(beat.event, "summary", "") or "")),
        title=title,
        world_title=world.title,
    )
    scene_label = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    tags = [
        _reader_visible_anchor(str(item))
        for item in list(getattr(beat.event, "tags", []) or [])
        if _reader_visible_anchor(str(item))
    ]
    anchor_line = _compact_anchor_line(
        [
            _compact_label_anchor(beat_label, title=title),
            title,
            summary,
            location,
            scene_label,
            " ".join(tags[:3]),
        ]
    )
    if not anchor_line:
        anchor_line = title or beat_label or scene_label or location
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    pressure_lines = [
        f"{actor_name}抬手按住{location}边那道冷光：“这件事不能漏过去。” {counterpart}没有替他收场，只把那一层后果重新推回眼前。",
        f"{counterpart}把视线压在{actor_name}身上：“你先把它接住。” {actor_name}的指节贴着桌沿停住，像终于承认这一步不能从场面里滑走。",
        f"{actor_name}没有再让话绕开，只把脚步停在{location}最亮的地方：“我现在认。” {counterpart}听见这句后反而往前半步。",
    ]
    return " ".join(
        [
            f"{anchor_line}没有被余波遮过去。",
            scene_atmosphere(world, beat, chapter_index=chapter_index),
            scene_detail(world, beat, repeated=False, chapter_index=chapter_index),
            pressure_lines[seed % len(pressure_lines)],
        ]
    ).strip()


def _coverage_gap_target_beats(
    scene_beats: Sequence[SceneBeat],
    repetition_bundle: dict[str, object],
) -> List[SceneBeat]:
    if not scene_beats:
        return []
    targeted_event_ids: List[str] = []
    for item in list(repetition_bundle.get("coverage_gap_examples") or []):
        event_id = str((item or {}).get("event_id") or "").strip()
        if event_id:
            targeted_event_ids.append(event_id)

    selected: List[SceneBeat] = []
    seen_ids: set[str] = set()
    for event_id in targeted_event_ids:
        for beat in scene_beats:
            beat_event_id = str(getattr(beat.event, "event_id", "") or "").strip()
            if beat_event_id == event_id and beat_event_id not in seen_ids:
                selected.append(beat)
                seen_ids.add(beat_event_id)
                break

    if not selected:
        fallback_candidates = [
            scene_beats[0],
            scene_beats[min(1, len(scene_beats) - 1)],
            scene_beats[-1],
        ]
        for beat in fallback_candidates:
            beat_event_id = str(getattr(beat.event, "event_id", "") or "").strip()
            dedupe_key = beat_event_id or f"{beat.beat_index}:{beat.event.title}"
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            selected.append(beat)

    return selected[:3]


def _expanded_coverage_target_beats(
    scene_beats: Sequence[SceneBeat],
    repetition_bundle: dict[str, object],
    *,
    limit: int = 6,
) -> List[SceneBeat]:
    selected = list(_coverage_gap_target_beats(scene_beats, repetition_bundle))
    seen_ids = {
        str(getattr(beat.event, "event_id", "") or "") or f"{beat.beat_index}:{beat.event.title}"
        for beat in selected
    }
    for beat in scene_beats:
        dedupe_key = str(getattr(beat.event, "event_id", "") or "") or f"{beat.beat_index}:{beat.event.title}"
        if dedupe_key in seen_ids:
            continue
        selected.append(beat)
        seen_ids.add(dedupe_key)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _coverage_context_for_beats(scene_beats: Sequence[SceneBeat]) -> dict[str, object]:
    return {
        "selected_event_ids": [
            str(getattr(beat.event, "event_id", "") or "")
            for beat in scene_beats
            if str(getattr(beat.event, "event_id", "") or "").strip()
        ],
        "scene_beats": [beat.to_dict() if hasattr(beat, "to_dict") else beat for beat in scene_beats],
    }


def _coverage_repetition_bundle(
    paragraphs: Sequence[str],
    scene_beats: Sequence[SceneBeat],
) -> dict[str, object]:
    return dict(
        repetition_signal_bundle(
            paragraphs,
            coverage_context=_coverage_context_for_beats(scene_beats),
        )
    )


def _paragraph_anchor_score(paragraph: str, scene_beats: Sequence[SceneBeat]) -> int:
    score = 0
    for beat in scene_beats:
        title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or ""))
        summary = _reader_visible_anchor(re.sub(
            r"这一拍不再新增事件[^。！？!?]*[。！？!?]?",
            "",
            str(getattr(beat.event, "summary", "") or ""),
        ))
        beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
        if title and title in paragraph:
            score += 10
        if summary and summary in paragraph:
            score += 3
        if beat_label and beat_label in paragraph:
            score += 6
    return score


def _paragraph_contains_event_anchor(paragraph: str, scene_beats: Sequence[SceneBeat]) -> bool:
    for beat in scene_beats:
        title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or ""))
        beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
        summary = _reader_visible_anchor(re.sub(
            r"这一拍不再新增事件[^。！？!?]*[。！？!?]?",
            "",
            str(getattr(beat.event, "summary", "") or ""),
        ))
        summary = _compact_summary_anchor(summary, title=title)
        if title and title in paragraph:
            return True
        if beat_label and beat_label in paragraph:
            return True
        if summary and summary in paragraph:
            return True
    return False


def _reader_visible_anchor(anchor: str) -> str:
    anchor = str(anchor or "").strip()
    if not anchor:
        return ""
    anchor = re.sub(r"\b[a-zA-Z_][A-Za-z0-9_]*\b", " ", anchor)
    anchor = re.sub(r"\s+", " ", anchor)
    anchor = re.sub(r"(?:\s*[·:：/|_-]\s*){2,}", " · ", anchor)
    anchor = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", anchor)
    anchor = anchor.strip(" ·:：/|_-")
    latin_anchor_chars = set("abcdefghijklmnopqrstuvwxyz0123456789_:/\\- ")
    if all(char in latin_anchor_chars for char in anchor):
        return ""
    return anchor


def _compact_label_anchor(label: str, *, title: str = "") -> str:
    label = _reader_visible_anchor(label)
    title = _reader_visible_anchor(title)
    if not label:
        return ""
    label = re.sub(r"^(起势|逼近|转向|余波|回声)\s*[:：·-]\s*", "", label).strip()
    label = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", label).strip(" ·:：/|_-")
    generic_fragments = ["真正要转向", "这一拍留下来的余波", "把下一次公开代价推近"]
    if title and title in label:
        return title
    if any(fragment in label for fragment in generic_fragments) and title:
        return title
    return label


def _compact_title_anchor(title: str, *, location: str = "") -> str:
    title = _reader_visible_anchor(title)
    location = _reader_visible_anchor(location)
    if not title:
        return ""
    title = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", title).strip(" ·:：/|_-")
    parts = [part.strip(" ·:：/|_-") for part in re.split(r"\s*·\s*", title) if part.strip(" ·:：/|_-")]
    generic_fragments = ["真正要转向", "说出口后的余波", "这一拍留下来的余波"]
    if len(parts) > 1:
        meaningful_parts = [
            part
            for part in parts
            if part != location and not any(fragment in part for fragment in generic_fragments)
        ]
        if meaningful_parts:
            return meaningful_parts[0][:26]
    if location and title == location:
        return ""
    return title[:26]


def _compact_summary_anchor(summary: str, *, title: str = "", world_title: str = "") -> str:
    summary = _reader_visible_anchor(summary)
    title = _reader_visible_anchor(title)
    world_title = _reader_visible_anchor(world_title)
    if not summary:
        return ""
    summary = re.sub(r"这一拍不再新增事件[^。！？!?]*[。！？!?]?", "", summary).strip()
    summary = summary.replace("真正要转向的那句终于逼到眼前", " ").strip()
    summary = re.sub(r"刚才没说透的态度、代价和退路都被逼到明处[。！？!?]?", " ", summary).strip()
    if world_title:
        summary = summary.replace(f"{world_title} 中，", "").replace(f"{world_title}中，", "")
    if title:
        summary = summary.replace(title, "").strip(" ，。·")
    summary = re.sub(r"让人物进一步卷入[^。！？!?]*[。！？!?]?", "", summary).strip(" ，。·")
    summary = re.sub(r"\s+", " ", summary).strip()
    if summary in {"中", "中，", "中,"}:
        return ""
    if len(summary) > 24:
        summary = summary[:24]
    return summary


def _compact_anchor_line(parts: Sequence[str]) -> str:
    compacted: List[str] = []
    for raw_part in parts:
        part = _reader_visible_anchor(str(raw_part or ""))
        part = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", part).strip(" ·:：/|_-")
        if not part:
            continue
        if len(part) > 26:
            part = part[:26]
        if any(part == existing or part in existing or existing in part for existing in compacted):
            if not any(existing in part and len(part) < len(existing) for existing in compacted):
                continue
        compacted.append(part)
    return " ".join(compacted[:4]).strip()


def _source_anchor_for_beat(paragraph: str, beat: SceneBeat) -> str:
    title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or ""))
    beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
    summary = _reader_visible_anchor(re.sub(
        r"这一拍不再新增事件[^。！？!?]*[。！？!?]?",
        "",
        str(getattr(beat.event, "summary", "") or ""),
    ))
    summary = _compact_summary_anchor(summary, title=title)
    if title and title in paragraph:
        return title
    if beat_label and beat_label in paragraph:
        return beat_label
    if summary and summary in paragraph:
        return summary
    return ""


def _beat_for_paragraph(paragraph: str, scene_beats: Sequence[SceneBeat], *, fallback_index: int) -> SceneBeat:
    for beat in scene_beats:
        if _source_anchor_for_beat(paragraph, beat):
            return beat
    return scene_beats[min(fallback_index % len(scene_beats), len(scene_beats) - 1)]


def _missing_anchor_beats(paragraphs: Sequence[str], scene_beats: Sequence[SceneBeat]) -> List[SceneBeat]:
    body = "\n\n".join(paragraphs)
    missing: List[SceneBeat] = []
    for beat in scene_beats:
        title = _reader_visible_anchor(str(getattr(beat.event, "title", "") or ""))
        beat_label = _reader_visible_anchor(str(getattr(beat, "beat_label", "") or ""))
        anchors = [anchor for anchor in (title, beat_label) if anchor]
        if anchors and not any(anchor in body for anchor in anchors):
            missing.append(beat)
    return missing


def _trim_to_max_units(
    paragraphs: Sequence[str],
    *,
    min_target_word_count: int,
    max_target_word_count: int,
    scene_beats: Sequence[SceneBeat],
    remediation_actions: List[str],
    protected_indexes: set[int] | None = None,
) -> List[str]:
    trimmed = [paragraph for paragraph in paragraphs if paragraph and paragraph.strip()]
    protected = set(protected_indexes or set())
    if max_target_word_count <= 0:
        return trimmed
    while story_text_unit_count("\n\n".join(trimmed)) > max_target_word_count and len(trimmed) > 3:
        removable_indexes = [
            index
            for index, paragraph in enumerate(trimmed)
            if index not in {0, len(trimmed) - 1}
            and index not in protected
            and story_text_unit_count("\n\n".join(trimmed[:index] + trimmed[index + 1 :])) >= min_target_word_count
        ]
        if not removable_indexes:
            break
        unanchored_indexes = [
            index for index in removable_indexes if not _paragraph_contains_event_anchor(trimmed[index], scene_beats)
        ]
        candidate_indexes = unanchored_indexes or removable_indexes
        remove_index = max(
            candidate_indexes,
            key=lambda index: (
                1 if _is_exposition_paragraph(trimmed[index]) else 0,
                -_paragraph_anchor_score(trimmed[index], scene_beats),
                story_text_unit_count(trimmed[index]),
            ),
        )
        trimmed.pop(remove_index)
        protected = {
            index if index < remove_index else index - 1
            for index in protected
            if index != remove_index
        }
        remediation_actions.append(f"length_gate_trim:{remove_index}")
    return trimmed


def _drop_repeated_paragraphs_after_trim(
    paragraphs: Sequence[str],
    *,
    min_target_word_count: int,
    scene_beats: Sequence[SceneBeat],
    remediation_actions: List[str],
) -> List[str]:
    updated = [paragraph for paragraph in paragraphs if paragraph and paragraph.strip()]
    if not scene_beats:
        return updated
    for _ in range(2):
        bundle = _coverage_repetition_bundle(updated, scene_beats)
        repeated_pairs = [
            dict(item or {})
            for item in list(bundle.get("semantic_paragraph_similarity_pairs") or [])
            if float((item or {}).get("similarity", 0.0) or 0.0) >= 0.82
        ]
        repeated_pairs.extend(
            dict(item or {})
            for item in list(bundle.get("top_repeated_paragraph_pairs") or [])
            if float((item or {}).get("similarity", 0.0) or 0.0) >= 0.45
        )
        if not repeated_pairs:
            break
        removed = False
        for pair in repeated_pairs:
            right_index = int(pair.get("right_paragraph_index", -1) or -1)
            if right_index <= 0 or right_index >= len(updated) - 1:
                continue
            trial = updated[:right_index] + updated[right_index + 1 :]
            if story_text_unit_count("\n\n".join(trial)) < min_target_word_count:
                continue
            updated = trial
            remediation_actions.append(f"q03_final_repeated_paragraph_drop:{right_index}")
            removed = True
            break
        if not removed:
            break
    return updated


def _paragraph_detail_count(paragraph: str) -> int:
    return sum(str(paragraph or "").count(marker) for marker in DETAIL_MARKERS)


def _paragraph_action_count(paragraph: str) -> int:
    return sum(str(paragraph or "").count(marker) for marker in ACTION_MARKERS)


def _low_detail_replace_index(paragraphs: Sequence[str], scene_beats: Sequence[SceneBeat]) -> int | None:
    if not paragraphs:
        return None
    candidates = [
        index
        for index, paragraph in enumerate(paragraphs)
        if 0 < index < len(paragraphs) - 1
        and not _has_continuation_hook(paragraph)
    ]
    if not candidates:
        candidates = [
            index
            for index, paragraph in enumerate(paragraphs)
            if index != len(paragraphs) - 1
            and not _has_continuation_hook(paragraph)
        ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda index: (
            _paragraph_detail_count(paragraphs[index]),
            _paragraph_action_count(paragraphs[index]),
            _paragraph_anchor_score(paragraphs[index], scene_beats),
            -story_text_unit_count(paragraphs[index]),
        ),
    )


def _repair_detail_density_after_trim(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    target_density: float | None = None,
    min_detail_count: int = 12,
    max_attempts: int = 4,
    fast_scene_detail_only: bool = False,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    target_density = float(target_density if target_density is not None else CONTRACT_DETAIL_DENSITY_FLOOR + 0.006)
    attempt = 0
    while attempt < max_attempts:
        if fast_scene_detail_only:
            lint_report = _detail_density_snapshot(updated)
            current_units = int(lint_report.get("text_unit_count", 0) or 0)
        else:
            repaired = _rebuild_draft(updated, {})
            lint_report = lint_chapter_draft(repaired.body)
            current_units = story_text_unit_count(repaired.body)
        if (
            float(lint_report.get("concrete_detail_density", 0.0) or 0.0) >= target_density
            and int(lint_report.get("detail_count", 0) or 0) >= min_detail_count
            and current_units >= min_target_word_count
        ):
            break
        if fast_scene_detail_only:
            beat = scene_beats[min((chapter_index + attempt) % len(scene_beats), len(scene_beats) - 1)]
            bridge = _detail_density_relief_paragraph(
                world,
                state_before,
                beat,
                variant_seed=2600 + chapter_index + attempt,
                chapter_index=chapter_index,
            )
        else:
            repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
            target_beats = _coverage_gap_target_beats(scene_beats, repetition_bundle)
            beat = (
                target_beats[min(attempt % len(target_beats), len(target_beats) - 1)]
                if target_beats
                else scene_beats[min((attempt + chapter_index) % len(scene_beats), len(scene_beats) - 1)]
            )
            bridge = (
                _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=2620 + attempt,
                    chapter_index=chapter_index,
                )
                if target_beats
                else _detail_density_relief_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=2600 + attempt,
                    chapter_index=chapter_index,
                )
            )
        replacement = " ".join(
            [
                bridge,
                _detail_reinforcement_paragraph(
                    world,
                    beat,
                    chapter_index=chapter_index,
                    variant_seed=2650 + attempt,
                ),
            ]
        ).strip()
        replace_index = _low_detail_replace_index(updated, scene_beats)
        if current_units < min_target_word_count or replace_index is None:
            updated.insert(_hook_insert_index(updated), replacement)
            remediation_actions.append(f"q05_final_detail_density_insert:{attempt}")
        else:
            updated[replace_index] = replacement
            remediation_actions.append(f"q05_final_detail_density_replace:{replace_index}")
        if not fast_scene_detail_only:
            updated = _dedupe_repeated_sentences(
                updated,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
        repaired_after_update = _rebuild_draft(updated, {})
        if (
            story_text_unit_count(repaired_after_update.body) > max_target_word_count
            and story_text_unit_count(repaired_after_update.body) >= min_target_word_count
        ):
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
        attempt += 1
    if fast_scene_detail_only:
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
    return updated


def _needs_final_repetition_repair(lint_report: dict[str, object], repetition_bundle: dict[str, object]) -> bool:
    return (
        float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.20
        or float(repetition_bundle.get("overall_repetition_pressure", 0.0) or 0.0) >= 0.38
        or float(repetition_bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0) >= 0.65
        or float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
        or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
        or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        or int(repetition_bundle.get("overcovered_beat_count", 0) or 0) >= 2
    )


def _final_repetition_replace_index(
    paragraphs: Sequence[str],
    repetition_bundle: dict[str, object],
    scene_beats: Sequence[SceneBeat],
) -> int | None:
    pair_candidates = [
        int((item or {}).get("right_paragraph_index", -1) or -1)
        for item in list(repetition_bundle.get("semantic_paragraph_similarity_pairs") or [])
        if float((item or {}).get("similarity", 0.0) or 0.0) >= 0.60
    ]
    pair_candidates.extend(
        int((item or {}).get("right_paragraph_index", -1) or -1)
        for item in list(repetition_bundle.get("top_repeated_paragraph_pairs") or [])
        if float((item or {}).get("similarity", 0.0) or 0.0) >= 0.18
    )
    for index in pair_candidates:
        if 0 < index < len(paragraphs) - 1:
            return index
    candidates = [
        index
        for index, paragraph in enumerate(paragraphs)
        if 0 < index < len(paragraphs) - 1
        and not _has_continuation_hook(paragraph)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda index: (
            _paragraph_anchor_score(paragraphs[index], scene_beats),
            0 if _is_exposition_paragraph(paragraphs[index]) else 1,
            -story_text_unit_count(paragraphs[index]),
        ),
    )


def _repair_repetition_after_final_detail(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    max_attempts: int = 6,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    attempt = 0
    while attempt < max_attempts:
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        if not _needs_final_repetition_repair(lint_report, repetition_bundle):
            break
        target_beats = _expanded_coverage_target_beats(scene_beats, repetition_bundle)
        beat = target_beats[min(attempt % len(target_beats), len(target_beats) - 1)] if target_beats else scene_beats[min(attempt, len(scene_beats) - 1)]
        if (
            float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
            or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
            or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        ):
            replacement = _coverage_gap_bridge_paragraph(
                world,
                state_before,
                beat,
                variant_seed=2800 + attempt,
                chapter_index=chapter_index,
            )
        elif (
            float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.20
            or float(repetition_bundle.get("overall_repetition_pressure", 0.0) or 0.0) >= 0.38
        ):
            replacement = _lexical_repetition_relief_paragraph(
                world,
                state_before,
                beat,
                variant_seed=2800 + attempt,
                chapter_index=chapter_index,
            )
        else:
            replacement = _paragraph_replacement(
                world=world,
                state_before=state_before,
                beat=beat,
                paragraph_index=2800 + attempt,
                chapter_index=chapter_index,
                previous_paragraphs=updated,
                source_paragraph="",
            )
        replace_index = _final_repetition_replace_index(updated, repetition_bundle, scene_beats)
        if replace_index is None:
            updated.insert(_hook_insert_index(updated), replacement)
            remediation_actions.append(f"q03_final_repetition_insert:{attempt}")
        else:
            updated[replace_index] = replacement
            remediation_actions.append(f"q03_final_repetition_replace:{replace_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        updated = _drop_repeated_paragraphs_after_trim(
            updated,
            min_target_word_count=min_target_word_count,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
        attempt += 1
    return updated


def _repair_dialogue_action_after_final_detail(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    target_ratio = 0.46
    attempt = 0
    while attempt < 4:
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        if (
            float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= target_ratio
            and story_text_unit_count(repaired.body) >= min_target_word_count
        ):
            break
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        target_beats = _coverage_gap_target_beats(scene_beats, repetition_bundle)
        beat = (
            target_beats[min(attempt % len(target_beats), len(target_beats) - 1)]
            if target_beats
            else scene_beats[min((attempt + 1) % len(scene_beats), len(scene_beats) - 1)]
        )
        pressure = " ".join(
            [
                _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=3000 + attempt,
                    chapter_index=chapter_index,
                ),
                _action_pressure_paragraph(world, state_before, beat),
            ]
        ).strip()
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if 0 < index < len(updated) - 1
            and not _has_continuation_hook(paragraph)
        ]
        replace_index = min(
            candidates,
            key=lambda index: (
                _paragraph_action_count(updated[index]),
                0 if _is_exposition_paragraph(updated[index]) else 1,
                _paragraph_anchor_score(updated[index], scene_beats),
                -story_text_unit_count(updated[index]),
            ),
        ) if candidates else None
        if story_text_unit_count(repaired.body) < min_target_word_count or replace_index is None:
            updated.insert(_hook_insert_index(updated), pressure)
            remediation_actions.append(f"q04_final_dialogue_action_insert:{attempt}")
        else:
            updated[replace_index] = pressure
            remediation_actions.append(f"q04_final_dialogue_action_replace:{replace_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired_after_update = _rebuild_draft(updated, {})
        lint_after_update = lint_chapter_draft(repaired_after_update.body)
        if float(lint_after_update.get("dialogue_plus_action_ratio", 0.0) or 0.0) < target_ratio:
            stable_candidates = [
                index
                for index in range(0, max(0, len(updated) - 1))
                if not _has_continuation_hook(updated[index])
            ]
            inline_index = (
                max(
                    stable_candidates,
                    key=lambda index: (
                        _paragraph_anchor_score(updated[index], scene_beats),
                        -_paragraph_action_count(updated[index]),
                        -story_text_unit_count(updated[index]),
                    ),
                )
                if stable_candidates
                else None
            )
            if inline_index is None and replace_index is not None and replace_index < len(updated):
                inline_index = replace_index
            if inline_index is None:
                inline_index = _low_detail_replace_index(updated, scene_beats)
            if inline_index is not None:
                updated[inline_index] = " ".join(
                    [
                        updated[inline_index].rstrip(),
                        _compact_action_dialogue_sentence(
                            world,
                            state_before,
                            beat,
                            variant_seed=3100 + attempt,
                        ),
                    ]
                ).strip()
                remediation_actions.append(f"q04_final_compact_action_inline:{inline_index}")
                repaired_after_update = _rebuild_draft(updated, {})
                lint_after_update = lint_chapter_draft(repaired_after_update.body)
        if (
            story_text_unit_count(repaired_after_update.body) > max_target_word_count
            and story_text_unit_count(repaired_after_update.body) >= min_target_word_count
        ):
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
        attempt += 1
    return updated


def _repair_final_q04_micro(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    attempt = 0
    while attempt < 4:
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        current_units = story_text_unit_count(repaired.body)
        exposition_threshold = 0.48 if current_units >= 1800 else 0.44
        if (
            float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= 0.43
            and float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= exposition_threshold
            and current_units >= min_target_word_count
        ):
            break
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        target_beats = _coverage_gap_target_beats(scene_beats, repetition_bundle)
        beat = (
            target_beats[min(attempt % len(target_beats), len(target_beats) - 1)]
            if target_beats
            else scene_beats[min((chapter_index + attempt) % len(scene_beats), len(scene_beats) - 1)]
        )
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if index < len(updated) - 1
            and not _has_continuation_hook(paragraph)
        ]
        if not candidates:
            candidates = [0] if updated else []
        if not candidates:
            break
        target_index = max(
            candidates,
            key=lambda index: (
                1 if _is_exposition_paragraph(updated[index]) else 0,
                _paragraph_anchor_score(updated[index], scene_beats),
                -_paragraph_action_count(updated[index]),
            ),
        )
        updated[target_index] = " ".join(
            [
                updated[target_index].rstrip(),
                _compact_action_dialogue_sentence(
                    world,
                    state_before,
                    beat,
                    variant_seed=3300 + attempt + target_index * 13 + len(updated) * 17,
                ),
            ]
        ).strip()
        remediation_actions.append(f"q04_final_micro_inline:{target_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
        attempt += 1
    return updated


def _is_exposition_paragraph(paragraph: str) -> bool:
    return "：" not in paragraph and "“" not in paragraph


def _short_dialogue_turn(state_before: NarrativeState, beat: SceneBeat, *, variant_index: int = 0) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    variants = [
        f'{actor_name}压低声音：“这句我不再绕开。”',
        f'{counterpart}看着他：“那就把后果说实。”',
        f'{actor_name}停了半拍：“我知道这一步不能只靠解释。”',
        f'{counterpart}没有退：“别再把真话留一半。”',
    ]
    return variants[int(variant_index) % len(variants)]


def _dialogize_exposition_paragraphs(
    paragraphs: Sequence[str],
    *,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    attempts: int,
    remediation_actions: List[str],
) -> List[str]:
    updated = list(paragraphs)
    if not scene_beats:
        return updated
    for attempt in range(max(0, attempts)):
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if index != len(updated) - 1 and _is_exposition_paragraph(paragraph)
        ]
        if not candidates:
            break
        target_index = max(candidates, key=lambda index: story_text_unit_count(updated[index]))
        beat = scene_beats[min(target_index % len(scene_beats), len(scene_beats) - 1)]
        updated[target_index] = " ".join(
            [
                updated[target_index].rstrip(),
                _short_dialogue_turn(state_before, beat, variant_index=attempt + target_index),
            ]
        ).strip()
        remediation_actions.append(f"q04_final_exposition_dialogize:{target_index}")
    return updated


def _scrub_longform_suspicious_refrains(
    paragraphs: Sequence[str],
    *,
    chapter_index: int,
    remediation_actions: List[str],
) -> List[str]:
    updated: List[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        cleaned = str(paragraph or "")
        replaced_any = False
        for phrase, replacements in LONGFORM_SUSPICIOUS_REFRAIN_REPLACEMENTS.items():
            if phrase not in cleaned:
                continue
            replacement = replacements[(chapter_index + paragraph_index + len(updated)) % len(replacements)]
            cleaned = cleaned.replace(phrase, replacement)
            replaced_any = True
        if replaced_any:
            remediation_actions.append(f"q03_longform_refrain_scrub:{paragraph_index}")
        updated.append(cleaned)
    return updated


def _exposition_ratio_for_paragraphs(paragraphs: Sequence[str]) -> float:
    cleaned = [paragraph for paragraph in paragraphs if str(paragraph or "").strip()]
    if not cleaned:
        return 0.0
    return sum(1 for paragraph in cleaned if _is_exposition_paragraph(paragraph)) / float(len(cleaned))


def _dialogize_longform_exposition_surface(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    remediation_actions: List[str],
    target_ratio: float = LONGFORM_STOP_READY_EXPOSITION_TARGET,
    max_attempts: int = 8,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        if _exposition_ratio_for_paragraphs(updated) <= target_ratio:
            break
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if _is_exposition_paragraph(paragraph) and not _has_continuation_hook(paragraph)
        ]
        if not candidates:
            candidates = [index for index, paragraph in enumerate(updated) if _is_exposition_paragraph(paragraph)]
        if not candidates:
            break
        target_index = max(
            candidates,
            key=lambda index: (
                story_text_unit_count(updated[index]),
                _paragraph_anchor_score(updated[index], scene_beats),
            ),
        )
        beat = scene_beats[(chapter_index + target_index + attempt) % len(scene_beats)]
        updated[target_index] = " ".join(
            [
                updated[target_index].rstrip(),
                _compact_action_dialogue_sentence(
                    world,
                    state_before,
                    beat,
                    variant_seed=9700 + attempt + target_index * 31,
                ),
            ]
        ).strip()
        remediation_actions.append(f"q04_longform_surface_dialogize:{target_index}")
    return updated


def _dialogue_scene_replacement_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    return " ".join(
        [
            scene_detail(world, beat, repeated=False, chapter_index=chapter_index),
            compose_late_longform_compact_exchange(
                world,
                state_before,
                beat,
                repeated=True,
                variant_offset=variant_seed,
            ),
            _compact_action_dialogue_sentence(
                world,
                state_before,
                beat,
                variant_seed=variant_seed + 17,
            ),
        ]
    ).strip()


def _final_longform_q04_closeout(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    target_exposition_ratio: float = LONGFORM_STOP_READY_EXPOSITION_TARGET,
    target_dialogue_ratio: float = LONGFORM_STOP_READY_DIALOGUE_TARGET,
    max_attempts: int = 7,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = [paragraph for paragraph in paragraphs if str(paragraph or "").strip()]
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        lint_report = lint_chapter_draft("\n\n".join(updated))
        if (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= target_exposition_ratio
            and float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= target_dialogue_ratio
            and story_text_unit_count("\n\n".join(updated)) >= min_target_word_count
        ):
            break
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if 0 < index < len(updated) - 1
            and _is_exposition_paragraph(paragraph)
            and not _has_continuation_hook(paragraph)
        ]
        if not candidates:
            candidates = [
                index
                for index, paragraph in enumerate(updated)
                if 0 < index < len(updated) - 1 and not _has_continuation_hook(paragraph)
            ]
        if not candidates:
            break
        target_index = max(
            candidates,
            key=lambda index: (
                1 if _is_exposition_paragraph(updated[index]) else 0,
                story_text_unit_count(updated[index]),
                _paragraph_anchor_score(updated[index], scene_beats),
            ),
        )
        beat = _beat_for_paragraph(updated[target_index], scene_beats, fallback_index=target_index + attempt)
        replacement = _dialogue_scene_replacement_paragraph(
            world,
            state_before,
            beat,
            variant_seed=11400 + attempt * 41 + target_index,
            chapter_index=chapter_index,
        )
        updated[target_index] = replacement
        remediation_actions.append(f"q04_final_longform_closeout_replace:{target_index}")
        protected_indexes = {target_index}
        if story_text_unit_count("\n\n".join(updated)) < min_target_word_count:
            filler_beat = scene_beats[(chapter_index + attempt + 29) % len(scene_beats)]
            insert_index = _hook_insert_index(updated)
            updated.insert(
                insert_index,
                _dialogue_scene_replacement_paragraph(
                    world,
                    state_before,
                    filler_beat,
                    variant_seed=11480 + attempt,
                    chapter_index=chapter_index,
                ),
            )
            protected_indexes = {
                index + 1 if index >= insert_index else index
                for index in protected_indexes
            }
            protected_indexes.add(insert_index)
            remediation_actions.append(f"length_gate_q04_final_longform_closeout:{attempt}")
        updated = _scrub_longform_suspicious_refrains(
            updated,
            chapter_index=chapter_index + attempt,
            remediation_actions=remediation_actions,
        )
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
                protected_indexes=protected_indexes,
            )
    return updated


def _final_longform_surface_reconcile(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    max_attempts: int = 3,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = [paragraph for paragraph in paragraphs if str(paragraph or "").strip()]
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        lint_report = lint_chapter_draft("\n\n".join(updated))
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        q03_dirty = _longform_surface_q03_needs_repair(lint_report, repetition_bundle)
        q04_dirty = (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) > LONGFORM_STOP_READY_EXPOSITION_TARGET
            or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < LONGFORM_STOP_READY_DIALOGUE_TARGET
        )
        if (
            not q03_dirty
            and not q04_dirty
            and story_text_unit_count("\n\n".join(updated)) >= min_target_word_count
        ):
            break
        if q03_dirty:
            updated = _final_longform_q03_closeout(
                updated,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=2,
            )
        updated = _final_longform_q04_closeout(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=5,
        )
        lint_after_q04 = lint_chapter_draft("\n\n".join(updated))
        if (
            float(lint_after_q04.get("exposition_ratio", 0.0) or 0.0) > LONGFORM_STOP_READY_EXPOSITION_TARGET
            or float(lint_after_q04.get("dialogue_plus_action_ratio", 0.0) or 0.0) < LONGFORM_STOP_READY_DIALOGUE_TARGET
        ):
            beat = scene_beats[(chapter_index + attempt + 41) % len(scene_beats)]
            insert_index = _hook_insert_index(updated)
            updated.insert(
                insert_index,
                _dialogue_scene_replacement_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=11740 + attempt,
                    chapter_index=chapter_index,
                ),
            )
            remediation_actions.append(f"q04_final_surface_reconcile_insert:{attempt}")
            if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
                updated = _trim_to_max_units(
                    updated,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                    protected_indexes={insert_index},
                )
        remediation_actions.append(f"surface_final_longform_reconcile:{attempt}")
    return updated


def _force_longform_q04_paragraph_mix(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    remediation_actions: List[str],
    max_attempts: int = 3,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = [paragraph for paragraph in paragraphs if str(paragraph or "").strip()]
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        lint_report = lint_chapter_draft("\n\n".join(updated))
        if (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= LONGFORM_STOP_READY_EXPOSITION_TARGET
            and float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= LONGFORM_STOP_READY_DIALOGUE_TARGET
            and story_text_unit_count("\n\n".join(updated)) >= min_target_word_count
        ):
            break
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if index < len(updated) - 1 and _is_exposition_paragraph(paragraph)
        ]
        if not candidates:
            candidates = [
                index
                for index, paragraph in enumerate(updated)
                if index < len(updated) - 1 and "“" not in paragraph
            ]
        if not candidates:
            break
        target_index = max(candidates, key=lambda index: story_text_unit_count(updated[index]))
        beat = _beat_for_paragraph(updated[target_index], scene_beats, fallback_index=target_index + attempt)
        updated[target_index] = _dialogue_scene_replacement_paragraph(
            world,
            state_before,
            beat,
            variant_seed=11840 + attempt * 37 + target_index,
            chapter_index=chapter_index,
        )
        remediation_actions.append(f"q04_force_paragraph_mix_replace:{target_index}")
        if story_text_unit_count("\n\n".join(updated)) < min_target_word_count:
            filler_beat = scene_beats[(chapter_index + attempt + 47) % len(scene_beats)]
            updated.insert(
                _hook_insert_index(updated),
                _dialogue_scene_replacement_paragraph(
                    world,
                    state_before,
                    filler_beat,
                    variant_seed=11890 + attempt,
                    chapter_index=chapter_index,
                ),
            )
            remediation_actions.append(f"q04_force_paragraph_mix_refloor:{attempt}")
    return updated


def _inline_longform_detail_surface_topup(
    paragraphs: Sequence[str],
    *,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    remediation_actions: List[str],
    target_density: float = 0.065,
    max_attempts: int = 4,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        lint_report = lint_chapter_draft("\n\n".join(updated))
        if float(lint_report.get("concrete_detail_density", 0.0) or 0.0) >= target_density:
            break
        candidates = [
            index
            for index, paragraph in enumerate(updated)
            if index < len(updated) - 1 and not _has_continuation_hook(paragraph)
        ]
        if not candidates:
            candidates = list(range(0, max(0, len(updated) - 1)))
        if not candidates:
            break
        target_index = candidates[(chapter_index + attempt) % len(candidates)]
        beat = scene_beats[(chapter_index + target_index + attempt) % len(scene_beats)]
        location = beat.event.location or "眼前这一处"
        fragments = [
            f"{location}边的杯沿、门框、纸页、灯影和鞋底水声一起晃了一下。",
            f"窗纸冷光贴过桌沿，衣袖、指节、茶气和香灰都在那一瞬变得清楚。",
            f"门影压着木板轻响，杯底水痕、纸页折角和檐下风声没有散开。",
            f"灯芯短短一爆，案角、袖口、窗缝和地砖上的灰都被照得更近。",
        ]
        updated[target_index] = " ".join(
            [
                updated[target_index].rstrip(),
                fragments[(chapter_index + attempt + target_index) % len(fragments)],
            ]
        ).strip()
        remediation_actions.append(f"q05_longform_surface_inline_topup:{target_index}")
    return updated


def _longform_surface_q03_needs_repair(
    lint_report: dict[str, object],
    repetition_bundle: dict[str, object],
) -> bool:
    return (
        float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.20
        or float(repetition_bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0) >= 0.84
        or float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42
        or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35
        or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        or int(repetition_bundle.get("overcovered_beat_count", 0) or 0) >= 2
        or int(repetition_bundle.get("suspicious_refrain_count", 0) or 0) >= 2
    )


def _repair_longform_surface_issue_mix_guard(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    max_attempts: int = 5,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        updated = _scrub_longform_suspicious_refrains(
            updated,
            chapter_index=chapter_index,
            remediation_actions=remediation_actions,
        )
        updated = _dialogize_longform_exposition_surface(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
            max_attempts=4,
        )
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        q04_clean = float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= LONGFORM_STOP_READY_EXPOSITION_TARGET
        q03_clean = not _longform_surface_q03_needs_repair(lint_report, repetition_bundle)
        if q03_clean and q04_clean and story_text_unit_count(repaired.body) >= min_target_word_count:
            break

        coverage_pressure = (
            float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42
            or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35
            or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        )
        target_beats = (
            _expanded_coverage_target_beats(scene_beats, repetition_bundle, limit=6)
            if coverage_pressure
            else _coverage_gap_target_beats(scene_beats, repetition_bundle)
        )
        beat = (
            target_beats[min(attempt % len(target_beats), len(target_beats) - 1)]
            if target_beats
            else scene_beats[(chapter_index + attempt) % len(scene_beats)]
        )
        if coverage_pressure:
            replacement_paragraphs = (
                _coverage_gap_surface_paragraphs(
                    world,
                    state_before,
                    target_beats,
                    variant_seed=9800 + attempt * 43,
                    chapter_index=chapter_index,
                    max_count=4,
                )
                if len(target_beats) >= 2
                else [
                    _coverage_anchor_echo_paragraph(
                        world,
                        state_before,
                        beat,
                        variant_seed=9800 + attempt,
                        chapter_index=chapter_index,
                    )
                ]
            )
        else:
            lexical_pressure = (
                float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.20
                or float(repetition_bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0) >= 0.84
                or float(repetition_bundle.get("n_gram_repetition_score", 0.0) or 0.0) >= 0.18
                or int(repetition_bundle.get("suspicious_refrain_count", 0) or 0) >= 2
            )
            replacement_paragraphs = [
                (
                    _lexical_repetition_relief_paragraph(
                        world,
                        state_before,
                        beat,
                        variant_seed=9800 + attempt * 53,
                        chapter_index=chapter_index,
                    )
                    if lexical_pressure
                    else compose_late_longform_compact_exchange(
                        world,
                        state_before,
                        beat,
                        repeated=True,
                        variant_offset=9800 + attempt,
                    )
                )
            ]
        replacement_paragraphs = _scrub_longform_suspicious_refrains(
            replacement_paragraphs,
            chapter_index=chapter_index + attempt,
            remediation_actions=remediation_actions,
        )
        if len(replacement_paragraphs) > 1:
            replace_candidates = sorted(
                [
                    index
                    for index, paragraph in enumerate(updated)
                    if 0 < index < len(updated) - 1 and not _has_continuation_hook(paragraph)
                ],
                key=lambda index: (
                    _paragraph_anchor_score(updated[index], scene_beats),
                    0 if _is_exposition_paragraph(updated[index]) else 1,
                    -story_text_unit_count(updated[index]),
                ),
            )
            for offset, replacement in enumerate(replacement_paragraphs):
                if offset < len(replace_candidates):
                    replace_index = replace_candidates[offset]
                    updated[replace_index] = replacement
                    remediation_actions.append(f"q03_longform_surface_coverage_replace:{replace_index}")
                else:
                    insert_index = _hook_insert_index(updated)
                    updated.insert(insert_index, replacement)
                    remediation_actions.append(f"q03_longform_surface_coverage_insert:{attempt}:{offset}")
        else:
            replacement = replacement_paragraphs[0] if replacement_paragraphs else ""
            replace_index = _final_repetition_replace_index(updated, repetition_bundle, scene_beats)
            if replace_index is None:
                updated.insert(_hook_insert_index(updated), replacement)
                remediation_actions.append(f"q03_longform_surface_insert:{attempt}")
            else:
                updated[replace_index] = replacement
                remediation_actions.append(f"q03_longform_surface_replace:{replace_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
    updated = _dialogize_longform_exposition_surface(
        updated,
        world=world,
        state_before=state_before,
        scene_beats=scene_beats,
        remediation_actions=remediation_actions,
        max_attempts=6,
    )
    return updated


def _final_longform_q03_closeout(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    max_attempts: int = 4,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = [paragraph for paragraph in paragraphs if str(paragraph or "").strip()]
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for attempt in range(max(0, max_attempts)):
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(updated, scene_beats)
        if (
            not _longform_surface_q03_needs_repair(lint_report, repetition_bundle)
            and story_text_unit_count(repaired.body) >= min_target_word_count
        ):
            break
        coverage_pressure = (
            float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42
            or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35
            or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
            or int(repetition_bundle.get("overcovered_beat_count", 0) or 0) >= 2
        )
        target_beats = (
            _expanded_coverage_target_beats(scene_beats, repetition_bundle, limit=6)
            if coverage_pressure
            else _coverage_gap_target_beats(scene_beats, repetition_bundle)
        )
        beat = (
            target_beats[min(attempt % len(target_beats), len(target_beats) - 1)]
            if target_beats
            else scene_beats[(chapter_index + attempt) % len(scene_beats)]
        )
        semantic_pressure = float(repetition_bundle.get("semantic_paragraph_similarity_score", 0.0) or 0.0) >= 0.80
        if coverage_pressure:
            replacement = _coverage_anchor_echo_paragraph(
                world,
                state_before,
                beat,
                variant_seed=11200 + attempt * 47,
                chapter_index=chapter_index,
            )
        elif semantic_pressure:
            replacement = _semantic_repetition_breaker_paragraph(
                world,
                state_before,
                beat,
                variant_seed=11200 + attempt * 47,
                chapter_index=chapter_index,
            )
        else:
            replacement = _lexical_repetition_relief_paragraph(
                world,
                state_before,
                beat,
                variant_seed=11200 + attempt * 47,
                chapter_index=chapter_index,
            )
        replacement = _scrub_longform_suspicious_refrains(
            [replacement],
            chapter_index=chapter_index + attempt,
            remediation_actions=remediation_actions,
        )[0]
        replace_index = _final_repetition_replace_index(updated, repetition_bundle, scene_beats)
        if replace_index is None:
            candidates = [
                index
                for index, paragraph in enumerate(updated)
                if 0 < index < len(updated) - 1 and not _has_continuation_hook(paragraph)
            ]
            replace_index = max(
                candidates,
                key=lambda index: story_text_unit_count(updated[index]),
            ) if candidates else None
        if replace_index is None or story_text_unit_count(repaired.body) < min_target_word_count:
            updated.insert(_hook_insert_index(updated), replacement)
            remediation_actions.append(f"q03_final_longform_closeout_insert:{attempt}")
        else:
            updated[replace_index] = replacement
            remediation_actions.append(f"q03_final_longform_closeout_replace:{replace_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        updated = _drop_repeated_paragraphs_after_trim(
            updated,
            min_target_word_count=min_target_word_count,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
    return updated


def _repair_longform_stop_ready_dialogue_guard(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
    min_target_word_count: int,
    max_target_word_count: int,
    remediation_actions: List[str],
    target_ratio: float = LONGFORM_STOP_READY_DIALOGUE_TARGET,
    max_attempts: int = 3,
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    updated = list(paragraphs)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    used_replace_indexes: set[int] = set()
    for attempt in range(max(0, max_attempts)):
        repaired = _rebuild_draft(updated, {})
        lint_report = lint_chapter_draft(repaired.body)
        if (
            float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= target_ratio
            and story_text_unit_count(repaired.body) >= min_target_word_count
        ):
            break
        beat = scene_beats[(chapter_index + attempt) % len(scene_beats)]
        compact_exchange = compose_late_longform_compact_exchange(
            world,
            state_before,
            beat,
            repeated=True,
            variant_offset=9000 + attempt * 29,
        )
        candidate_indexes = [
            index
            for index, paragraph in enumerate(updated)
            if index not in used_replace_indexes
            and 0 < index < len(updated) - 1
            and not _has_continuation_hook(paragraph)
        ]
        if story_text_unit_count(repaired.body) < min_target_word_count or not candidate_indexes:
            updated.insert(_hook_insert_index(updated), compact_exchange)
            remediation_actions.append(f"q04_longform_stop_ready_dialogue_insert:{attempt}")
        else:
            replace_index = max(
                candidate_indexes,
                key=lambda index: (
                    1 if _is_exposition_paragraph(updated[index]) else 0,
                    1 if "“" not in updated[index] else 0,
                    -_paragraph_action_count(updated[index]),
                    story_text_unit_count(updated[index]),
                ),
            )
            updated[replace_index] = compact_exchange
            used_replace_indexes.add(replace_index)
            remediation_actions.append(f"q04_longform_stop_ready_dialogue_replace:{replace_index}")
        updated = _dedupe_repeated_sentences(
            updated,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        if story_text_unit_count("\n\n".join(updated)) > max_target_word_count:
            updated = _trim_to_max_units(
                updated,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
    return updated


def _sensory_variation_paragraph(
    world: WorldBible,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    location = beat.event.location or "眼前这一处"
    scene_function = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    event_seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    variants = [
        f"{location}里的光线有点发冷，边角却积着旧尘、潮气和说不清来源的细碎响动。连门边那一下轻轻回弹的动静，都把{scene_function}里该说破的东西照得更分明。",
        f"{location}没有立刻安静下来，反而能听见更琐碎的声响一层层往外浮。脚边拖过去的风、桌沿残着的水痕和空气里那点发苦的味道，把场面压出了新的棱角。",
        f"{location}里最先变得清楚的不是谁的脸色，而是那些平时容易被忽略的小东西。灯影偏了一寸，器物碰出一点轻响，连空气里那股淡淡的金属味都把心思逼得更近了。",
        f"{location}里的回声并不均匀，像有人故意把每一点门响、风声和纸页摩擦都留在了人心最不肯退的地方，让{scene_function}的后劲慢慢逼出来。",
        f"{location}的空气带着潮意，灯下那一圈暗影却反而更清。桌角、窗缝、鞋底擦过地面的轻响全被拖长了，像在替这一步{scene_function}添新的重量。",
        f"{location}里先变得具体起来的是门影、器物和人身上那点没收住的动作，连最轻的风声和桌沿回响都把{scene_function}往更硬的一侧推近。",
        f"{location}没有替谁掩住后劲，反而让灯火、冷气、纸页和脚步里那点细碎震动一起把{scene_function}照得更难回避。",
    ]
    return variants[event_seed % len(variants)]


def _lexical_repetition_relief_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    location = beat.event.location or "眼前这一处"
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    focus = _scene_focus_label(beat) or SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    variants = [
        f"{location}外忽然落下一串细响，檐水、竹帘、石缝、灯影、纸页和掌心里的凉意各自分开。{actor_name}把衣袖重新拢紧，低声道：“我听见了，也会照着做。”{counterpart}没有替他让路，只把目光停在门框旁那道冷光里。",
        f"远处更鼓短短一震，余音沿着砖缝、窗缝和案角散开，连杯沿上的雨痕、茶气和香灰都比方才清楚。{counterpart}看着{actor_name}：“别再把{focus}藏进半句话里。”{actor_name}点了一下头，脚步终于没有往后撤。",
        f"{location}边的铜扣轻轻一碰，暗纹、尘粒、木板、纸页和衣袖里的寒意同时露出来。{actor_name}先按住呼吸，再把声音压低：“这回我接住。”{counterpart}没有应得太快，只让桌沿那点停顿把后果钉实。",
        f"{location}里先响的是纸页被推开的声音，随后才是门缝里的风。{counterpart}抬手挡住灯影：“别用同一句话绕。”{actor_name}把掌心贴上桌沿，答得很慢：“那我换一种说法，也换一种做法。”",
        f"窗边那道冷光偏了一寸，照出杯底水痕和地砖缝里的灰。{actor_name}没有再从{focus}上退开，只把声音压低：“我现在往前走。”{counterpart}看着他，把那半步空出来。",
        f"{location}边的脚步忽然停住，衣袖擦过门框时带出一声很轻的响。{counterpart}问：“这次你要怎么接？”{actor_name}先看了一眼案角，才说：“不靠解释，靠我接下来的动作。”",
        f"灯芯短短一爆，纸页、杯沿和窗纸都跟着晃了一下。{actor_name}把原本要重复的那句话咽回去，改口道：“我先做给你看。”{counterpart}没有笑，只把路让出半寸。",
        f"{location}里的风声绕过桌角，带起一点茶气和旧木味。{counterpart}没有再逼问，只把目光落在{actor_name}手上；那只手终于离开原处，朝{focus}真正压来的方向伸过去。",
    ]
    return variants[seed % len(variants)]


def _semantic_repetition_breaker_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    location = beat.event.location or "眼前这一处"
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    focus = _scene_focus_label(beat) or SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    object_pool = [
        ("门轴", "杯底水痕", "纸页折角"),
        ("窗缝冷光", "鞋尖灰尘", "袖口暗纹"),
        ("桌沿旧痕", "灯座微响", "掌心凉意"),
        ("栏杆阴影", "木板细纹", "衣摆尘色"),
        ("器物边缘", "风里的潮味", "指节轻响"),
    ]
    first, second, third = object_pool[seed % len(object_pool)]
    variants = [
        f"{first}先响了一下，{second}和{third}随即把{location}分成了几块不一样的冷色。{actor_name}没有沿着上一句往下说，只抬手指向{focus}最难遮住的地方：“从这里重新算。” {counterpart}看了一眼那处细节，终于把脚步停稳。",
        f"{location}里忽然多出一层很轻的动静：{first}擦过影子，{second}压住回声，{third}把人的呼吸照得更近。{counterpart}问：“你现在要认哪一件？” {actor_name}没有复述旧话，只答：“认这一件，也认它后面会追来的账。”",
        f"{actor_name}把目光从{counterpart}脸上移开，转而看住{first}、{second}和{third}。那几处小东西让{focus}不再像一句解释，而像当场摆出来的证物；他低声道：“不用绕了，先从这处落笔。”",
        f"{location}没有再靠同一种停顿撑着。{first}把风声截短，{second}压住桌边那点反光，{third}让{counterpart}的沉默换了方向。{actor_name}往前半步：“我换一种做法，你看这一处。”",
    ]
    return variants[(seed // 5) % len(variants)]


def _detail_density_relief_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_seed: int = 0,
    chapter_index: int = 0,
) -> str:
    location = beat.event.location or "眼前这一处"
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_seed)
    variants = [
        f"{location}的灯影落在纸页、杯沿、门框、窗缝和案角上，雨痕、茶气、香灰、衣袖和木板纹路都清楚起来。{actor_name}抬手按住桌沿，低声道：“我不会再只说一半。”{counterpart}看着他，脚步没有退。",
        f"风从{location}边掠过去，檐下的雨、门后的影、阶前的纸页和杯沿的冷光一起晃了晃。{counterpart}把衣袖收回去，声音很轻：“那就照实往下走。”{actor_name}握紧掌心，终于点头。",
        f"{location}里那盏灯照着案角、门框、窗纸、器物和衣摆，连茶香、雨声、纸页摩擦和鞋底擦过木板的细响都没有散。{actor_name}偏头看向{counterpart}：“我接得住。”",
    ]
    return variants[seed % len(variants)]


def _dialogic_opening_suffix(state_before: NarrativeState, beat: SceneBeat) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    return f"{actor_name}心里先有了一句没出口的话：“真要走到这里，我也不能再装作什么都没发生。”"


def _strong_hook_line(
    world: WorldBible,
    scene_plan: ScenePlan,
    scene_beats: Sequence[SceneBeat],
    *,
    chapter_index: int = 0,
) -> str:
    hook = realize_hook(
        world,
        scene_plan.ending_hook,
        scene_beats[-1].event.scene_function,
        chapter_index=chapter_index,
    ).strip()
    if _has_continuation_hook(hook):
        return hook
    return f"{hook.rstrip('。')}。下一次开口前，真正追上来的那一句话还没有散。"


def _sentence_variation(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    variant_index: int,
    chapter_index: int = 0,
) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    location = beat.event.location or "眼前这一处"
    focus = _scene_focus_label(beat)
    detail_variants = [
        "纸页边缘",
        "门框冷光",
        "杯沿水痕",
        "窗纸阴影",
        "桌沿木纹",
        "衣袖摩擦声",
    ]
    detail = detail_variants[(int(variant_index) + int(chapter_index)) % len(detail_variants)]
    variants = [
        f"{actor_name}没有立刻把那句更重的话推出去，只先看了{counterpart}一眼，像在判断这一步究竟还能不能一起往前。",
        f"{location}里的声响并没有帮谁遮掩，反而把{actor_name}心里那点迟疑一点点逼到了明处。",
        f"{counterpart}并不急着替他收场，只把沉默稳稳压住，让那句本该被躲开的真话继续留在两人之间。",
        f"{actor_name}知道自己现在多退半步，后面就要拿更大的代价把这半步补回来。",
        f"{location}里最难受的不是风声，而是那句已经说到一半却不能再收回去的话。",
        f"{counterpart}抬眼时没有给他任何松动的余地，像是在提醒这一次谁都别想再只留一半真话。",
        f"{actor_name}先把{focus}压在喉间，像明明知道它已经到了嘴边，却还想替自己多留半寸退路。",
        f"{counterpart}没有替{actor_name}把这一步讲圆，只让{location}里的回声慢慢逼近，像逼人把{focus}认得更彻底。",
        f"{location}边最先绷紧的不是谁的语气，而是{actor_name}和{counterpart}都知道{focus}已经不能再只停在半句上。",
        f"{actor_name}抬眼时先碰上的是{counterpart}的沉默，那种不肯后退的静反倒把{focus}一步步推得更近。",
        f"{counterpart}把那点迟疑留在眼底，没有替谁遮过去，像故意让{focus}在{location}里自己长出更重的后劲。",
        f"{location}里的灯影、脚步和冷气都没替谁分担，反而把{focus}里最难认的那一层留在了每个人呼吸边上。",
        f"{actor_name}没有急着把后半句补齐，只让指尖在{location}边那一点冷意上停了停，像要先确认自己到底还敢不敢认{focus}。",
        f"{counterpart}把视线稳稳落在{actor_name}脸上，没有给场面多余的缓冲，像是非得逼着这一步{focus}在灯影底下见真章。",
        f"{location}边的门框、回声和那点没收住的呼吸一起压上来，像连{focus}都被逼得只能往更明处走。",
        f"{actor_name}把手停在{detail}旁，先看清自己还能退到哪里，才把{focus}里最难认的那一点慢慢放到桌面上。",
        f"{counterpart}没有加重语气，只把{detail}旁那点停顿留出来，逼得{actor_name}自己决定还要不要继续绕开{focus}。",
        f"{location}看似先静了一瞬，可真正不肯退开的，是{actor_name}和{counterpart}都知道{focus}已经回不到还能装作无事的那边。",
        f"{actor_name}听见那句追问以后没有立刻应声，只让目光沿着{location}边那一点冷光停住，像在承认{focus}迟早得由自己接回去。",
        f"{counterpart}先收住了动作，却没有把锋利也一起收回去，反而让{focus}顺着那点安静更慢、更硬地逼到眼前。",
    ]
    return variants[int(variant_index) % len(variants)]


def _dedupe_repeated_sentences(
    paragraphs: Sequence[str],
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_beats: Sequence[SceneBeat],
) -> List[str]:
    if not scene_beats:
        return list(paragraphs)
    seen_sentences: List[str] = []
    rewritten: List[str] = []
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    for paragraph_index, paragraph in enumerate(paragraphs):
        beat = scene_beats[min(paragraph_index % len(scene_beats), len(scene_beats) - 1)]
        segments = [segment.strip() for segment in SENTENCE_BOUNDARY_PATTERN.split(paragraph) if segment.strip()]
        updated_segments: List[str] = []
        for sentence_index, sentence in enumerate(segments):
            normalized = _normalize(sentence)
            similar_seen = any(_sentence_similarity(normalized, prior) >= 0.72 for prior in seen_sentences if len(prior) >= 14)
            if len(normalized) >= 14 and (normalized in seen_sentences or similar_seen):
                sentence = _sentence_variation(
                    world,
                    state_before,
                    beat,
                    variant_index=chapter_index * 31 + paragraph_index * 7 + sentence_index,
                    chapter_index=chapter_index,
                )
                normalized = _normalize(sentence)
            if normalized:
                seen_sentences.append(normalized)
            updated_segments.append(sentence)
        rewritten.append("".join(updated_segments).strip())
    return [paragraph for paragraph in rewritten if paragraph]


def _length_target_bounds(*, draft: ChapterDraft, render_spec: SceneRenderSpec | None) -> tuple[int, int, int]:
    target = int(
        (render_spec.target_word_count if render_spec is not None else 0)
        or draft.metadata.get("target_word_count")
        or 2000
    )
    minimum = int(
        (render_spec.min_target_word_count if render_spec is not None else 0)
        or draft.metadata.get("min_target_word_count")
        or max(200, target - 200)
    )
    maximum = int(
        (render_spec.max_target_word_count if render_spec is not None else 0)
        or draft.metadata.get("max_target_word_count")
        or max(target, target + 200)
    )
    if target >= 1800:
        minimum = max(minimum, 1840)
        maximum = max(maximum, minimum + 180)
    return target, minimum, maximum


def _hook_insert_index(paragraphs: Sequence[str]) -> int:
    if paragraphs and _has_continuation_hook(paragraphs[-1]):
        return max(0, len(paragraphs) - 1)
    return len(paragraphs)


def _expansion_reflection(state_before: NarrativeState, beat: SceneBeat, *, variant_index: int = 0) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    variants = [
        f"{actor_name}把手指压在案角，低声道：“这句一旦认下去，就不只落在我一个人身上。” {counterpart}没有躲开，只把那层沉默更稳地接住了。",
        f"{actor_name}抬眼时迟了半拍，像终于承认开口以后{counterpart}也得一起承担。{counterpart}只回了一句：“你既然明白，就别再把后果说轻。”",
        f"{actor_name}把那口气压回去，又慢慢吐出来：“我现在再往前一步，就不能只让我一个人算账。” {counterpart}听见这句后没有退，反而把目光压得更直。",
        f"{actor_name}看着{counterpart}时终于把最难受的那一点说出来：“这句话不会只停在今晚，后面每一次回头都会被它追上。” {counterpart}没有插话，只把这句留在两人中间。",
        f"{actor_name}忽然停住，像是终于想明白碰出真相以后，最难的是{counterpart}还愿不愿意站在同一边。{counterpart}低声道：“你先把真话放下，我再决定要不要跟上。”",
    ]
    return variants[int(variant_index) % len(variants)]


def _expansion_dialogue_variation(state_before: NarrativeState, beat: SceneBeat, *, variant_index: int = 0) -> str:
    actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
    counterpart = _actor_name(state_before, beat.event.actors[1]) if len(beat.event.actors) > 1 else "对面那人"
    variants = [
        f"{actor_name}低声道：“我不是非要把你拖进来，我只是知道现在再不把这句说出来，后面每一步都会更难走。” {counterpart}没有马上接，只把目光更稳地压了回来。",
        f"{counterpart}先问：“你现在才打算认，是因为终于想明白了，还是因为已经退不回去了？” {actor_name}把手指压在案角上，没有立刻躲开这句追问。",
        f"{actor_name}说：“我可以自己扛，但我不能再装作你和这件事毫无关系。” {counterpart}听完以后没有退，只让那层沉默更冷了一寸。",
        f"{counterpart}把声音压得很轻：“你要真想把话说完，就别只挑对自己有利的那一半。” {actor_name}听见这句时，呼吸明显慢了半拍。",
        f"{actor_name}问：“如果我现在把最难听的那句也认下来，你还会站在这里吗？” {counterpart}没有回答，可那一下抬眼已经比任何一句话都更重。",
    ]
    return variants[int(variant_index) % len(variants)]


def _length_expansion_paragraph(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    remaining_units: int,
    expansion_index: int,
) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    variant = (expansion_index + chapter_index) % 7
    if remaining_units >= 420:
        if variant == 0:
            blocks = [
                _action_pressure_paragraph(world, state_before, beat),
                _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
            ]
        elif variant == 1:
            blocks = [
                _coverage_gap_bridge_paragraph(world, state_before, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
                _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
            ]
        elif variant == 2:
            blocks = [
                scene_atmosphere(world, beat, chapter_index=chapter_index),
                compose_emotion_action(world, state_before, beat, repeated=False),
                _action_pressure_paragraph(world, state_before, beat),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
            ]
        elif variant == 3:
            blocks = [
                _dialogue_pressure_paragraph(world, state_before, beat),
                _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
            ]
        elif variant == 4:
            blocks = [
                _coverage_gap_bridge_paragraph(world, state_before, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                _action_pressure_paragraph(world, state_before, beat),
                _expansion_reflection(state_before, beat, variant_index=expansion_index + chapter_index),
            ]
        elif variant == 5:
            blocks = [
                _sensory_variation_paragraph(world, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
                _expansion_reflection(state_before, beat, variant_index=expansion_index + chapter_index),
            ]
        else:
            blocks = [
                compose_emotion_action(world, state_before, beat, repeated=False),
                _coverage_gap_bridge_paragraph(world, state_before, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
            ]
        return " ".join(item for item in blocks if item).strip()
    if remaining_units >= 220:
        if variant == 0:
            return " ".join(
                [
                    _action_pressure_paragraph(world, state_before, beat),
                    _expansion_reflection(state_before, beat, variant_index=expansion_index + chapter_index),
                ]
            ).strip()
        if variant == 1:
            return " ".join(
                [
                    _dialogue_pressure_paragraph(world, state_before, beat),
                    scene_detail(world, beat, repeated=True, chapter_index=chapter_index),
                    _expansion_reflection(state_before, beat, variant_index=expansion_index + chapter_index),
                ]
            ).strip()
        if variant == 2:
            return " ".join(
                [
                    _coverage_gap_bridge_paragraph(world, state_before, beat, chapter_index=chapter_index),
                    _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
                ]
            ).strip()
        if variant == 3:
            return " ".join(
                [
                    scene_atmosphere(world, beat, chapter_index=chapter_index),
                    compose_emotion_action(world, state_before, beat, repeated=False),
                    _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
                ]
            ).strip()
        if variant == 4:
            return " ".join(
                [
                    _sensory_variation_paragraph(world, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                    _action_pressure_paragraph(world, state_before, beat),
                ]
            ).strip()
        return " ".join(
            [
                scene_atmosphere(world, beat, chapter_index=chapter_index),
                _expansion_dialogue_variation(state_before, beat, variant_index=expansion_index + chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
            ]
        ).strip()
    if variant in {0, 2, 4}:
        return " ".join(
            [
                _sensory_variation_paragraph(world, beat, variant_seed=expansion_index, chapter_index=chapter_index),
                _detail_reinforcement_paragraph(world, beat, chapter_index=chapter_index, variant_seed=expansion_index),
            ]
        ).strip()
    return " ".join(
        [
            _dialogue_pressure_paragraph(world, state_before, beat),
            _sensory_variation_paragraph(world, beat, variant_seed=expansion_index, chapter_index=chapter_index),
        ]
    ).strip()


def repair_chapter_draft(
    *,
    world: WorldBible,
    state_before: NarrativeState,
    scene_plan: ScenePlan,
    scene_beats: Sequence[SceneBeat],
    draft: ChapterDraft,
    render_spec: SceneRenderSpec | None = None,
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
    target_word_count, min_target_word_count, max_target_word_count = _length_target_bounds(draft=draft, render_spec=render_spec)
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    state_metadata = dict(getattr(state_before, "metadata", {}) or {})
    simulation_budget = int(state_metadata.get("authoring_simulation_chapter_budget") or 0)
    simulation_quality_mode = str(state_metadata.get("authoring_simulation_quality_mode") or "")
    standard_authoring_simulation = 0 < simulation_budget <= 6 and simulation_quality_mode != "benchmark"
    if standard_authoring_simulation:
        target_word_count = min(target_word_count, 900)
        min_target_word_count = min(min_target_word_count, 700)
        max_target_word_count = min(max(max_target_word_count, min_target_word_count + 120), 1100)
    state_longform_mode = bool(
        not standard_authoring_simulation
        and (
            getattr(state_before, "current_series_id", None)
            or getattr(state_before, "current_volume_id", None)
            or getattr(state_before, "current_arc_id", None)
            or state_metadata.get("longform_plan_enabled")
            or chapter_index >= 20
        )
    )
    if state_longform_mode:
        target_word_count = max(target_word_count, 2000)
        min_target_word_count = max(min_target_word_count, 1840)
        max_target_word_count = max(max_target_word_count, min_target_word_count + 180, target_word_count + 120)
    longform_mode = min_target_word_count >= 1800 or state_longform_mode
    detail_polish_mode = state_longform_mode and chapter_index >= 20

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

    if float(lint_report.get("repetition_score", 0.0)) > 0.16 and scene_beats:
        insert_at = min(len(paragraphs), max(2, len(paragraphs) - 1))
        paragraphs.insert(
            insert_at,
            _sensory_variation_paragraph(
                world,
                scene_beats[min(1, len(scene_beats) - 1)],
                chapter_index=chapter_index,
            ),
        )
        remediation_actions.append("q03_sensory_variation")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats) if scene_beats else dict(lint_report.get("repetition_signal_bundle") or {})
    if longform_mode and scene_beats and (
        float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42
        or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35
        or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
    ):
        insert_at = min(len(paragraphs), max(2, len(paragraphs) // 2))
        for offset, beat in enumerate(_coverage_gap_target_beats(scene_beats, repetition_bundle)):
            paragraphs.insert(
                insert_at + offset,
                _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=offset,
                    chapter_index=chapter_index,
                ),
            )
        remediation_actions.append("q03_coverage_gap_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if (
        float(lint_report.get("exposition_ratio", 0.0)) > 0.44
        or repaired.dialogue_count < 2
        or story_text_unit_count(repaired.body) < min(650, min_target_word_count)
    ):
        insert_at = 2 if len(paragraphs) > 2 else len(paragraphs)
        paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        remediation_actions.append("q04_exposition_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if (
        float(lint_report.get("dialogue_plus_action_ratio", 0.0)) < 0.42
        or repaired.action_count < 8
        or draft.action_count < 2
    ):
        insert_at = min(len(paragraphs), max(2, len(paragraphs) - 1))
        paragraphs.insert(insert_at, _action_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        remediation_actions.append("q05_dialogue_action_balance")
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
                _detail_reinforcement_paragraph(world, scene_beats[-1], chapter_index=chapter_index),
            ]
        ).strip()
        remediation_actions.append("q05_detail_inline")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if longform_mode and scene_beats and (
        float(lint_report.get("exposition_ratio", 0.0)) > 0.40
        or float(lint_report.get("dialogue_plus_action_ratio", 0.0)) < 0.46
        or float(lint_report.get("concrete_detail_density", 0.0)) < DETAIL_DENSITY_FLOOR * 1.1
    ):
        insert_at = min(len(paragraphs), max(2, len(paragraphs) - 2))
        paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        paragraphs.insert(insert_at + 1, _detail_reinforcement_paragraph(world, scene_beats[-1], chapter_index=chapter_index))
        remediation_actions.append("q04_q05_scene_realization_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    if chapter_index <= 1 and float(lint_report.get("exposition_ratio", 0.0)) > 0.52 and len(scene_beats) >= 2:
        insert_at = min(len(paragraphs), max(2, len(paragraphs) - 1))
        paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, scene_beats[0]))
        paragraphs.insert(insert_at + 1, _action_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        remediation_actions.append("q04_reader_entry_pressure_boost")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    strong_hook = _strong_hook_line(world, scene_plan, scene_beats, chapter_index=chapter_index)
    current_tail = paragraphs[-1] if paragraphs else ""
    current_tail_has_hook = _has_continuation_hook(current_tail)
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
                    paragraph = _detail_reinforcement_paragraph(
                        world,
                        scene_beats[min(index - 1, len(scene_beats) - 1)],
                        chapter_index=chapter_index,
                        variant_seed=index,
                    )
                remediation_actions.append(f"q03_post_insert_variation:{index}")
            deduped.append(paragraph)
            seen.add(_normalize(paragraph))
        repaired = _rebuild_draft(deduped, metadata)

    paragraphs = list(repaired.paragraphs)
    current_units = story_text_unit_count(repaired.body)
    expansion_index = 0
    while current_units < min_target_word_count and scene_beats and expansion_index < 16:
        beat = scene_beats[expansion_index % len(scene_beats)]
        insert_at = _hook_insert_index(paragraphs)
        candidate_paragraph = _length_expansion_paragraph(
            world,
            state_before,
            beat,
            remaining_units=min_target_word_count - current_units,
            expansion_index=expansion_index,
        )
        seen_paragraphs = {_normalize(item) for item in paragraphs}
        retries = 0
        while _normalize(candidate_paragraph) in seen_paragraphs and retries < 6:
            retries += 1
            candidate_paragraph = _length_expansion_paragraph(
                world,
                state_before,
                beat,
                remaining_units=min_target_word_count - current_units,
                expansion_index=expansion_index + retries * len(scene_beats),
            )
        paragraphs.insert(insert_at, candidate_paragraph)
        remediation_actions.append(f"length_gate_expand:{expansion_index}")
        repaired = _rebuild_draft(paragraphs, metadata)
        current_units = story_text_unit_count(repaired.body)
        if current_units > max_target_word_count and current_units >= min_target_word_count:
            trial_paragraphs = list(paragraphs)
            trial_paragraphs.pop(insert_at)
            trial_repaired = _rebuild_draft(trial_paragraphs, metadata)
            if story_text_unit_count(trial_repaired.body) >= min_target_word_count:
                paragraphs = trial_paragraphs
                repaired = trial_repaired
                current_units = story_text_unit_count(repaired.body)
            else:
                paragraphs[insert_at] = _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=180,
                    expansion_index=expansion_index + 100,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
        expansion_index += 1

    longform_exposition_threshold = 0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44
    if (
        float(lint_report.get("exposition_ratio", 0.0)) > longform_exposition_threshold
        or float(lint_report.get("dialogue_plus_action_ratio", 0.0)) < 0.46
    ) and scene_beats:
        middle_beat = scene_beats[min(1, len(scene_beats) - 1)]
        closing_beat = scene_beats[-1]
        insert_at = max(2, len(paragraphs) - 1)
        paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, middle_beat))
        paragraphs.insert(insert_at + 1, _action_pressure_paragraph(world, state_before, closing_beat))
        remediation_actions.append("q04_longform_shape_guard")
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

    paragraphs = _dedupe_repeated_sentences(
        paragraphs,
        world=world,
        state_before=state_before,
        scene_beats=scene_beats,
    )
    paragraphs = _replace_redundant_paragraphs_after_expansion(
        paragraphs,
        world=world,
        state_before=state_before,
        scene_beats=scene_beats,
        remediation_actions=remediation_actions,
    )
    paragraphs = _dedupe_repeated_sentences(
        paragraphs,
        world=world,
        state_before=state_before,
        scene_beats=scene_beats,
    )
    repaired = _rebuild_draft(paragraphs, metadata)
    lint_report = lint_chapter_draft(repaired.body)

    if chapter_index <= 1 and float(lint_report.get("exposition_ratio", 0.0)) > 0.52 and paragraphs:
        if "“" not in paragraphs[0]:
            paragraphs[0] = " ".join(
                [
                    paragraphs[0].rstrip(),
                    _dialogic_opening_suffix(state_before, scene_beats[0]),
                ]
            ).strip()
            remediation_actions.append("q04_reader_entry_opening_dialogic")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
        if float(lint_report.get("exposition_ratio", 0.0)) > 0.52 and len(scene_beats) >= 2:
            insert_at = min(len(paragraphs), max(2, len(paragraphs) - 1))
            paragraphs.insert(insert_at, _dialogue_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
            remediation_actions.append("q04_reader_entry_retry")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

    if (
        float(lint_report.get("dialogue_plus_action_ratio", 0.0)) < 0.42
        or repaired.action_count < 8
    ) and scene_beats:
        insert_at = _hook_insert_index(paragraphs)
        paragraphs.insert(insert_at, _action_pressure_paragraph(world, state_before, scene_beats[min(1, len(scene_beats) - 1)]))
        remediation_actions.append("q05_post_length_action_balance")
        repaired = _rebuild_draft(paragraphs, metadata)

    paragraphs = _dedupe_repeated_sentences(
        repaired.paragraphs,
        world=world,
        state_before=state_before,
        scene_beats=scene_beats,
    )
    repaired = _rebuild_draft(paragraphs, metadata)
    lint_report = lint_chapter_draft(repaired.body)

    current_units = story_text_unit_count(repaired.body)
    if current_units < min_target_word_count and scene_beats:
        paragraphs = list(repaired.paragraphs)
        recovery_index = 0
        while current_units < min_target_word_count and recovery_index < 12:
            beat = scene_beats[recovery_index % len(scene_beats)]
            insert_at = _hook_insert_index(paragraphs)
            candidate_paragraph = _length_expansion_paragraph(
                world,
                state_before,
                beat,
                remaining_units=min_target_word_count - current_units,
                expansion_index=200 + recovery_index * max(1, len(scene_beats)),
            )
            seen_paragraphs = {_normalize(item) for item in paragraphs}
            retries = 0
            while _normalize(candidate_paragraph) in seen_paragraphs and retries < 6:
                retries += 1
                candidate_paragraph = _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=260 + recovery_index * max(1, len(scene_beats)) + retries,
                )
            paragraphs.insert(insert_at, candidate_paragraph)
            remediation_actions.append(f"length_gate_recover:{recovery_index}")
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            recovery_index += 1
        paragraphs = _dedupe_repeated_sentences(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        paragraphs = _replace_redundant_paragraphs_after_expansion(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)

    current_units = story_text_unit_count(repaired.body)
    if chapter_index <= 1 and current_units < 1000 and scene_beats:
        paragraphs = list(repaired.paragraphs)
        topup_index = 0
        while current_units < 1000 and topup_index < 3:
            beat = scene_beats[topup_index % len(scene_beats)]
            insert_at = _hook_insert_index(paragraphs)
            paragraphs.insert(
                insert_at,
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=1000 - current_units,
                    expansion_index=900 + topup_index * max(1, len(scene_beats)),
                ),
            )
            remediation_actions.append(f"q04_reader_entry_length_topup:{topup_index}")
            repaired = _rebuild_draft(paragraphs, metadata)
            paragraphs = _replace_redundant_paragraphs_after_expansion(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            topup_index += 1

    current_units = story_text_unit_count(repaired.body)
    if current_units < min_target_word_count and scene_beats:
        paragraphs = list(repaired.paragraphs)
        final_topup_index = 0
        while current_units < min_target_word_count and final_topup_index < 4:
            beat = scene_beats[(len(paragraphs) + final_topup_index) % len(scene_beats)]
            insert_at = _hook_insert_index(paragraphs)
            paragraphs.insert(
                insert_at,
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=1200 + final_topup_index * max(1, len(scene_beats)),
                ),
            )
            remediation_actions.append(f"length_gate_final_topup:{final_topup_index}")
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_topup_index += 1

    paragraphs = list(repaired.paragraphs)
    repaired = _rebuild_draft(paragraphs, metadata)
    lint_report = lint_chapter_draft(repaired.body)
    repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats) if scene_beats else dict(lint_report.get("repetition_signal_bundle") or {})

    coverage_needs_bridge = scene_beats and (
        float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.34
        or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.30
        or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
    )
    repetition_needs_repair = scene_beats and (
        float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.16
        or float(repetition_bundle.get("overall_repetition_pressure", 0.0) or 0.0) >= 0.42
    )

    if coverage_needs_bridge:
        insert_at = min(_hook_insert_index(paragraphs), max(2, len(paragraphs) // 2))
        for offset, beat in enumerate(_coverage_gap_target_beats(scene_beats, repetition_bundle)):
            paragraphs.insert(
                insert_at + offset,
                _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=500 + offset,
                    chapter_index=chapter_index,
                ),
        )
        remediation_actions.append("q03_final_coverage_bridge")
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        paragraphs = _replace_redundant_paragraphs_after_expansion(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats)
    elif repetition_needs_repair:
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        paragraphs = _replace_redundant_paragraphs_after_expansion(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats)

    q04_exposition_threshold = 0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44
    q04_attempt = 0
    while scene_beats and q04_attempt < 3 and (
        float(lint_report.get("exposition_ratio", 0.0) or 0.0) > q04_exposition_threshold
        or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.46
    ):
        middle_beat = scene_beats[min(q04_attempt % len(scene_beats), len(scene_beats) - 1)]
        closing_beat = scene_beats[min((q04_attempt + 1) % len(scene_beats), len(scene_beats) - 1)]
        insert_at = _hook_insert_index(paragraphs)
        paragraphs.insert(
            insert_at,
            _dialogue_pressure_paragraph(world, state_before, middle_beat),
        )
        paragraphs.insert(
            insert_at + 1,
            _action_pressure_paragraph(world, state_before, closing_beat),
        )
        remediation_actions.append(f"q04_final_dialogue_action_pressure:{q04_attempt}")
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        paragraphs = _replace_redundant_paragraphs_after_expansion(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)
        q04_attempt += 1

    if scene_beats:
        paragraphs = _dedupe_repeated_sentences(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        paragraphs = _replace_redundant_paragraphs_after_expansion(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        paragraphs = _trim_to_max_units(
            repaired.paragraphs,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        paragraphs = _dedupe_repeated_sentences(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)
        final_exposition_attempt = 0
        while (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) > 0.5
            and final_exposition_attempt < 3
        ):
            paragraphs = _dialogize_exposition_paragraphs(
                paragraphs,
                state_before=state_before,
                scene_beats=scene_beats,
                attempts=1,
                remediation_actions=remediation_actions,
            )
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_exposition_attempt += 1
        final_balance_attempt = 0
        while (
            float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            and final_balance_attempt < 2
        ):
            insert_at = _hook_insert_index(paragraphs)
            paragraphs.insert(
                insert_at,
                _action_pressure_paragraph(
                    world,
                    state_before,
                    scene_beats[min(final_balance_attempt, len(scene_beats) - 1)],
                ),
            )
            remediation_actions.append(f"q05_final_action_balance:{final_balance_attempt}")
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_balance_attempt += 1
        final_exposition_retry = 0
        while final_exposition_retry < 4:
            current_units = story_text_unit_count(repaired.body)
            exposition_threshold = 0.5 if current_units >= 1800 else 0.44
            if float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= exposition_threshold:
                break
            paragraphs = _dialogize_exposition_paragraphs(
                repaired.paragraphs,
                state_before=state_before,
                scene_beats=scene_beats,
                attempts=1,
                remediation_actions=remediation_actions,
            )
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_exposition_retry += 1

        missing_anchor_beats = _missing_anchor_beats(repaired.paragraphs, scene_beats) if not longform_mode else []
        if missing_anchor_beats:
            paragraphs = list(repaired.paragraphs)
            insert_at = _hook_insert_index(paragraphs)
            for offset, beat in enumerate(missing_anchor_beats[:3]):
                paragraphs.insert(
                    insert_at + offset,
                    _coverage_gap_bridge_paragraph(
                        world,
                        state_before,
                        beat,
                        variant_seed=1500 + offset,
                        chapter_index=chapter_index,
                    ),
                )
            remediation_actions.append("q03_final_missing_anchor_bridge")
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            still_missing_anchor_beats = _missing_anchor_beats(repaired.paragraphs, scene_beats)
            if still_missing_anchor_beats:
                paragraphs = list(repaired.paragraphs)
                for offset, beat in enumerate(still_missing_anchor_beats[:3]):
                    replacement = _coverage_gap_bridge_paragraph(
                        world,
                        state_before,
                        beat,
                        variant_seed=1600 + offset,
                        chapter_index=chapter_index,
                    )
                    candidate_indexes = [
                        index
                        for index, paragraph in enumerate(paragraphs)
                        if index != len(paragraphs) - 1
                        and not _paragraph_contains_event_anchor(paragraph, scene_beats)
                    ]
                    if candidate_indexes:
                        replace_index = max(candidate_indexes, key=lambda index: story_text_unit_count(paragraphs[index]))
                        paragraphs[replace_index] = replacement
                        remediation_actions.append(f"q03_final_missing_anchor_replace:{replace_index}")
                    else:
                        paragraphs.insert(_hook_insert_index(paragraphs), replacement)
                        remediation_actions.append("q03_final_missing_anchor_insert")
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)

        final_repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
        final_coverage_needs_bridge = (
            float(final_repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.5
            or int(final_repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        )
        if final_coverage_needs_bridge:
            paragraphs = list(repaired.paragraphs)
            used_replace_indexes: set[int] = set()
            for offset, beat in enumerate(_expanded_coverage_target_beats(scene_beats, final_repetition_bundle, limit=4)):
                bridge = _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=1800 + offset,
                    chapter_index=chapter_index,
                )
                candidate_indexes = [
                    index
                    for index, paragraph in enumerate(paragraphs)
                    if index not in used_replace_indexes
                    and 0 < index < len(paragraphs) - 1
                    and not _source_anchor_for_beat(paragraph, beat)
                ]
                if candidate_indexes:
                    replace_index = max(
                        candidate_indexes,
                        key=lambda index: (
                            story_text_unit_count(paragraphs[index]),
                            -_paragraph_anchor_score(paragraphs[index], scene_beats),
                        ),
                    )
                    paragraphs[replace_index] = bridge
                    used_replace_indexes.add(replace_index)
                    remediation_actions.append(f"q03_final_coverage_replace:{replace_index}")
                else:
                    paragraphs.insert(_hook_insert_index(paragraphs), bridge)
                    remediation_actions.append("q03_final_coverage_insert")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            paragraphs = _drop_repeated_paragraphs_after_trim(
                paragraphs,
                min_target_word_count=min_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            topup_index = 0
            while current_units < min_target_word_count and topup_index < 4:
                beat = scene_beats[topup_index % len(scene_beats)]
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=1800 + topup_index * max(1, len(scene_beats)),
                    ),
                )
                remediation_actions.append(f"q03_final_coverage_length_recover:{topup_index}")
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                topup_index += 1
            paragraphs = _trim_to_max_units(
                repaired.paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            paragraphs = _drop_repeated_paragraphs_after_trim(
                paragraphs,
                min_target_word_count=min_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

        coverage_retry = 0
        while coverage_retry < 2:
            retry_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            retry_needs_bridge = (
                float(retry_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.5
                or int(retry_bundle.get("uncovered_beat_count", 0) or 0) > 0
            )
            if not retry_needs_bridge:
                break
            target_beats = _coverage_gap_target_beats(scene_beats, retry_bundle)
            if not target_beats:
                break
            beat = target_beats[0]
            paragraphs = list(repaired.paragraphs)
            bridge = _coverage_gap_bridge_paragraph(
                world,
                state_before,
                beat,
                variant_seed=1900 + coverage_retry,
                chapter_index=chapter_index,
            )
            candidate_indexes = [
                index
                for index, paragraph in enumerate(paragraphs)
                if 0 < index < len(paragraphs) - 1
                and not _source_anchor_for_beat(paragraph, beat)
            ]
            if candidate_indexes:
                replace_index = max(
                    candidate_indexes,
                    key=lambda index: (
                        story_text_unit_count(paragraphs[index]),
                        -_paragraph_anchor_score(paragraphs[index], scene_beats),
                    ),
                )
                paragraphs[replace_index] = bridge
                remediation_actions.append(f"q03_final_coverage_retry_replace:{replace_index}")
            else:
                paragraphs.insert(_hook_insert_index(paragraphs), bridge)
                remediation_actions.append("q03_final_coverage_retry_insert")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            topup_index = 0
            while current_units < min_target_word_count and topup_index < 3:
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        scene_beats[topup_index % len(scene_beats)],
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=1950 + coverage_retry * 10 + topup_index,
                    ),
                )
                remediation_actions.append(f"q03_final_coverage_retry_length_recover:{topup_index}")
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                topup_index += 1
            paragraphs = _trim_to_max_units(
                repaired.paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            coverage_retry += 1

        final_exposition_after_coverage = 0
        while final_exposition_after_coverage < 3:
            current_units = story_text_unit_count(repaired.body)
            exposition_threshold = 0.5 if current_units >= 1800 else 0.44
            if float(lint_report.get("exposition_ratio", 0.0) or 0.0) <= exposition_threshold:
                break
            paragraphs = _dialogize_exposition_paragraphs(
                repaired.paragraphs,
                state_before=state_before,
                scene_beats=scene_beats,
                attempts=1,
                remediation_actions=remediation_actions,
            )
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_exposition_after_coverage += 1

        paragraphs = _drop_repeated_paragraphs_after_trim(
            repaired.paragraphs,
            min_target_word_count=min_target_word_count,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        if list(paragraphs) != list(repaired.paragraphs):
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
        final_repetition_retry = 0
        while (
            float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.2
            and final_repetition_retry < 2
        ):
            paragraphs = list(repaired.paragraphs)
            beat = scene_beats[min(final_repetition_retry, len(scene_beats) - 1)]
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _lexical_repetition_relief_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=2100 + final_repetition_retry,
                    chapter_index=chapter_index,
                ),
            )
            remediation_actions.append(f"q03_final_lexical_relief:{final_repetition_retry}")
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_repetition_retry += 1
        final_detail_retry = 0
        while (
            float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < CONTRACT_DETAIL_DENSITY_FLOOR
            and final_detail_retry < 2
        ):
            paragraphs = list(repaired.paragraphs)
            beat = scene_beats[min(final_detail_retry, len(scene_beats) - 1)]
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _detail_density_relief_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=2200 + final_detail_retry,
                    chapter_index=chapter_index,
                ),
            )
            remediation_actions.append(f"q05_final_detail_density_relief:{final_detail_retry}")
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            final_detail_retry += 1

        for _ in range(3):
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=5,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

            paragraphs = _repair_dialogue_action_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

        paragraphs = _repair_final_q04_micro(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

        paragraphs = _repair_repetition_after_final_detail(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

        paragraphs = _repair_final_q04_micro(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

        paragraphs = _repair_repetition_after_final_detail(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        lint_report = lint_chapter_draft(repaired.body)

        current_units = story_text_unit_count(repaired.body)
        final_length_recover = 0
        while current_units < min_target_word_count and final_length_recover < 4:
            beat = scene_beats[min(final_length_recover % len(scene_beats), len(scene_beats) - 1)]
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=3600 + final_length_recover,
                ),
            )
            remediation_actions.append(f"length_gate_post_final_recover:{final_length_recover}")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            current_units = story_text_unit_count(repaired.body)
            final_length_recover += 1
        if final_length_recover:
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

        current_units = story_text_unit_count(repaired.body)
        final_floor_recover = 0
        while current_units < min_target_word_count and final_floor_recover < 3:
            beat = scene_beats[(chapter_index + final_floor_recover) % len(scene_beats)]
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=4200 + final_floor_recover,
                ),
            )
            remediation_actions.append(f"length_gate_final_floor_recover:{final_floor_recover}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            current_units = story_text_unit_count(repaired.body)
            final_floor_recover += 1

        if final_floor_recover:
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            current_units = story_text_unit_count(repaired.body)
            final_floor_after_repetition = 0
            while current_units < min_target_word_count and final_floor_after_repetition < 2:
                beat = scene_beats[(chapter_index + final_floor_after_repetition + 1) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=4300 + final_floor_after_repetition,
                    ),
                )
                remediation_actions.append(
                    f"length_gate_final_floor_after_repetition:{final_floor_after_repetition}"
                )
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
                current_units = story_text_unit_count(repaired.body)
                final_floor_after_repetition += 1

        hard_coverage_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
        if (
            float(hard_coverage_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
            or float(hard_coverage_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
            or int(hard_coverage_bundle.get("uncovered_beat_count", 0) or 0) > 0
        ):
            paragraphs = list(repaired.paragraphs)
            insert_at = _hook_insert_index(paragraphs)
            used_replace_indexes: set[int] = set()
            for offset, beat in enumerate(_expanded_coverage_target_beats(scene_beats, hard_coverage_bundle, limit=5)):
                bridge = _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=4600 + offset,
                    chapter_index=chapter_index,
                )
                candidate_indexes = [
                    index
                    for index, paragraph in enumerate(paragraphs)
                    if index not in used_replace_indexes
                    and 0 < index < len(paragraphs) - 1
                    and not _source_anchor_for_beat(paragraph, beat)
                ]
                if candidate_indexes:
                    replace_index = min(
                        candidate_indexes,
                        key=lambda index: (
                            _paragraph_anchor_score(paragraphs[index], scene_beats),
                            0 if _is_exposition_paragraph(paragraphs[index]) else 1,
                            -story_text_unit_count(paragraphs[index]),
                        ),
                    )
                    paragraphs[replace_index] = bridge
                    used_replace_indexes.add(replace_index)
                    remediation_actions.append(f"q03_final_hard_coverage_replace:{replace_index}")
                else:
                    paragraphs.insert(insert_at + offset, bridge)
                    remediation_actions.append("q03_final_hard_coverage_insert")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

        if float(lint_report.get("exposition_ratio", 0.0) or 0.0) > 0.5:
            paragraphs = _repair_final_q04_micro(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

        post_q04_repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
        if _needs_final_repetition_repair(lint_report, post_q04_repetition_bundle):
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            remediation_actions.append("q03_post_q04_repetition_repair")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            current_units = story_text_unit_count(repaired.body)
            post_q04_floor_recover = 0
            while current_units < min_target_word_count and post_q04_floor_recover < 3:
                post_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
                target_beats = _expanded_coverage_target_beats(scene_beats, post_bundle)
                beat = (
                    target_beats[min(post_q04_floor_recover % len(target_beats), len(target_beats) - 1)]
                    if target_beats
                    else scene_beats[(chapter_index + post_q04_floor_recover) % len(scene_beats)]
                )
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=4700 + post_q04_floor_recover,
                    ),
                )
                remediation_actions.append(
                    f"length_gate_post_q04_repetition_recover:{post_q04_floor_recover}"
                )
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
                current_units = story_text_unit_count(repaired.body)
                post_q04_floor_recover += 1
            if float(lint_report.get("exposition_ratio", 0.0) or 0.0) > 0.5:
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)

    if scene_beats and longform_mode and len(scene_beats) >= 3:
        paragraphs = list(repaired.paragraphs)
        multi_beat_bridge = _multi_beat_coverage_paragraph(
            world,
            state_before,
            scene_beats,
            variant_seed=5000,
            chapter_index=chapter_index,
        )
        candidate_indexes = [
            index
            for index, paragraph in enumerate(paragraphs)
            if 0 < index < len(paragraphs) - 1
            and not _has_continuation_hook(paragraph)
        ]
        if candidate_indexes and multi_beat_bridge:
            replace_index = min(
                candidate_indexes,
                key=lambda index: (
                    _paragraph_anchor_score(paragraphs[index], scene_beats),
                    0 if _is_exposition_paragraph(paragraphs[index]) else 1,
                    -story_text_unit_count(paragraphs[index]),
                ),
            )
            paragraphs[replace_index] = multi_beat_bridge
            remediation_actions.append(f"q03_longform_multi_beat_coverage_replace:{replace_index}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)

    if scene_beats:
        final_sweep_attempt = 0
        while final_sweep_attempt < 3:
            paragraphs = list(repaired.paragraphs)
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats)
            current_units = story_text_unit_count(repaired.body)
            exposition_threshold = 0.5 if current_units >= 1800 else 0.44
            needs_q03 = _needs_final_repetition_repair(lint_report, repetition_bundle)
            needs_q04 = (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > exposition_threshold
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            )
            if not needs_q03 and not needs_q04:
                break
            if needs_q03:
                paragraphs = _repair_repetition_after_final_detail(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append(f"q03_final_sweep_repair:{final_sweep_attempt}")
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
                post_repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
                if (
                    float(post_repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
                    or float(post_repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
                    or int(post_repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
                    or int(post_repetition_bundle.get("overcovered_beat_count", 0) or 0) >= 2
                ):
                    paragraphs = list(repaired.paragraphs)
                    multi_beat_bridge = _multi_beat_coverage_paragraph(
                        world,
                        state_before,
                        scene_beats,
                        variant_seed=5400 + final_sweep_attempt,
                        chapter_index=chapter_index,
                    )
                    candidate_indexes = [
                        index
                        for index, paragraph in enumerate(paragraphs)
                        if 0 < index < len(paragraphs) - 1
                        and not _has_continuation_hook(paragraph)
                    ]
                    if candidate_indexes and multi_beat_bridge:
                        replace_index = min(
                            candidate_indexes,
                            key=lambda index: (
                                _paragraph_anchor_score(paragraphs[index], scene_beats),
                                0 if _is_exposition_paragraph(paragraphs[index]) else 1,
                                -story_text_unit_count(paragraphs[index]),
                            ),
                        )
                        paragraphs[replace_index] = multi_beat_bridge
                        remediation_actions.append(f"q03_final_sweep_multi_beat_replace:{replace_index}")
                        repaired = _rebuild_draft(paragraphs, metadata)
                        lint_report = lint_chapter_draft(repaired.body)
            if needs_q04:
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                paragraphs = _repair_dialogue_action_after_final_detail(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append(f"q04_final_sweep_repair:{final_sweep_attempt}")
                repaired = _rebuild_draft(paragraphs, metadata)
            paragraphs = _dedupe_repeated_sentences(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            if current_units < min_target_word_count:
                beat = scene_beats[(chapter_index + final_sweep_attempt) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=5200 + final_sweep_attempt,
                    ),
                )
                remediation_actions.append(f"length_gate_final_sweep_recover:{final_sweep_attempt}")
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
            final_sweep_attempt += 1

    if scene_beats:
        current_units = story_text_unit_count(repaired.body)
        final_contract_floor_recover = 0
        while current_units < min_target_word_count and final_contract_floor_recover < 4:
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            target_beats = _expanded_coverage_target_beats(scene_beats, repetition_bundle)
            beat = (
                target_beats[min(final_contract_floor_recover % len(target_beats), len(target_beats) - 1)]
                if target_beats
                else scene_beats[(chapter_index + final_contract_floor_recover) % len(scene_beats)]
            )
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=6200 + final_contract_floor_recover,
                ),
            )
            remediation_actions.append(f"length_gate_final_contract_floor:{final_contract_floor_recover}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_contract_floor_recover += 1
        if final_contract_floor_recover:
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            if (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            ):
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        lint_report = lint_chapter_draft(repaired.body)
        detail_density_target = (
            LONGFORM_DETAIL_DENSITY_POLISH_TARGET
            if detail_polish_mode
            else CONTRACT_DETAIL_DENSITY_FLOOR
        )
        min_detail_count_target = (
            max(12, int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR))
            if detail_polish_mode
            else 12
        )
        if float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < detail_density_target:
            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                target_density=detail_density_target,
                min_detail_count=min_detail_count_target,
                max_attempts=7 if detail_polish_mode else 4,
                fast_scene_detail_only=detail_polish_mode,
            )
            remediation_actions.append(
                "q05_final_longform_detail_density_polish"
                if detail_polish_mode
                else "q05_final_contract_detail_density_repair"
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            if _needs_final_repetition_repair(lint_report, repetition_bundle):
                paragraphs = _repair_repetition_after_final_detail(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append("q03_post_final_detail_density_repair")
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
            if (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            ):
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                paragraphs = _repair_dialogue_action_after_final_detail(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append("q04_post_final_detail_density_repair")
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_detail_length_recover = 0
            while current_units < min_target_word_count and final_detail_length_recover < 3:
                beat = scene_beats[(chapter_index + final_detail_length_recover) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=6600 + final_detail_length_recover,
                    ),
                )
                remediation_actions.append(f"length_gate_post_final_detail_density:{final_detail_length_recover}")
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                final_detail_length_recover += 1

    if scene_beats:
        current_units = story_text_unit_count(repaired.body)
        final_unconditional_floor = 0
        while current_units < min_target_word_count and final_unconditional_floor < 4:
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            target_beats = _expanded_coverage_target_beats(scene_beats, repetition_bundle)
            beat = (
                target_beats[min(final_unconditional_floor % len(target_beats), len(target_beats) - 1)]
                if target_beats
                else scene_beats[(chapter_index + final_unconditional_floor) % len(scene_beats)]
            )
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=7000 + final_unconditional_floor,
                ),
            )
            remediation_actions.append(f"length_gate_final_unconditional_floor:{final_unconditional_floor}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_unconditional_floor += 1
        lint_report = lint_chapter_draft(repaired.body)
        if (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
            or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
        ):
            paragraphs = _repair_final_q04_micro(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            paragraphs = _repair_dialogue_action_after_final_detail(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            remediation_actions.append("q04_post_final_unconditional_floor_repair")
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_q04_floor_recover = 0
            while current_units < min_target_word_count and final_q04_floor_recover < 3:
                beat = scene_beats[(chapter_index + final_q04_floor_recover + 1) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=7200 + final_q04_floor_recover,
                    ),
                )
                remediation_actions.append(f"length_gate_post_final_q04:{final_q04_floor_recover}")
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                final_q04_floor_recover += 1

    if scene_beats and detail_polish_mode:
        lint_report = lint_chapter_draft(repaired.body)
        if float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < LONGFORM_DETAIL_DENSITY_POLISH_FLOOR:
            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                min_detail_count=max(12, int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR)),
                max_attempts=5,
                fast_scene_detail_only=True,
            )
            remediation_actions.append("q05_final_longform_detail_density_floor")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            paragraphs = _trim_to_max_units(
                paragraphs,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            if _needs_final_repetition_repair(lint_report, repetition_bundle):
                paragraphs = _repair_repetition_after_final_detail(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append("q03_post_longform_detail_density_floor")
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
            if (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            ):
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                paragraphs = _repair_dialogue_action_after_final_detail(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append("q04_post_longform_detail_density_floor")
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats and not longform_mode:
        missing_anchor_beats = _missing_anchor_beats(repaired.paragraphs, scene_beats)
        if missing_anchor_beats:
            paragraphs = list(repaired.paragraphs)
            for offset, beat in enumerate(missing_anchor_beats[:3]):
                bridge = _coverage_gap_bridge_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=7800 + offset,
                    chapter_index=chapter_index,
                )
                over_budget = story_text_unit_count("\n\n".join(paragraphs + [bridge])) > max_target_word_count
                candidate_indexes = [
                    index
                    for index, paragraph in enumerate(paragraphs)
                    if index != len(paragraphs) - 1
                    and not _paragraph_contains_event_anchor(paragraph, scene_beats)
                ]
                if over_budget and candidate_indexes:
                    replace_index = max(
                        candidate_indexes,
                        key=lambda index: (
                            1 if _is_exposition_paragraph(paragraphs[index]) else 0,
                            story_text_unit_count(paragraphs[index]),
                        ),
                    )
                    paragraphs[replace_index] = bridge
                    remediation_actions.append(f"q03_final_anchor_restore_replace:{replace_index}")
                else:
                    paragraphs.insert(_hook_insert_index(paragraphs), bridge)
                    remediation_actions.append("q03_final_anchor_restore_insert")
            repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        paragraphs = list(repaired.paragraphs)
        tail = paragraphs[-1] if paragraphs else ""
        if not _has_continuation_hook(tail):
            if paragraphs:
                paragraphs[-1] = strong_hook
            else:
                paragraphs.append(strong_hook)
            remediation_actions.append("q09_final_hook_restore")
            repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        current_units = story_text_unit_count(repaired.body)
        final_post_polish_length_recover = 0
        while current_units < min_target_word_count and final_post_polish_length_recover < 4:
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            target_beats = _expanded_coverage_target_beats(scene_beats, repetition_bundle)
            beat = (
                target_beats[min(final_post_polish_length_recover % len(target_beats), len(target_beats) - 1)]
                if target_beats
                else scene_beats[(chapter_index + final_post_polish_length_recover) % len(scene_beats)]
            )
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=7600 + final_post_polish_length_recover,
                ),
            )
            remediation_actions.append(f"length_gate_post_detail_polish:{final_post_polish_length_recover}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_post_polish_length_recover += 1

    if scene_beats and story_text_unit_count(repaired.body) > max_target_word_count:
        paragraphs = _trim_to_max_units(
            repaired.paragraphs,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            scene_beats=scene_beats,
            remediation_actions=remediation_actions,
        )
        repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats and detail_polish_mode:
        for final_detail_topup in range(2):
            lint_report = lint_chapter_draft(repaired.body)
            if float(lint_report.get("concrete_detail_density", 0.0) or 0.0) >= 0.07:
                break
            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                min_detail_count=max(12, int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR)),
                max_attempts=4,
                fast_scene_detail_only=True,
            )
            remediation_actions.append(f"q05_final_longform_detail_density_topup:{final_detail_topup}")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            if _needs_final_repetition_repair(lint_report, repetition_bundle):
                paragraphs = _repair_repetition_after_final_detail(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append(f"q03_post_longform_detail_density_topup:{final_detail_topup}")
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
            if (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
            ):
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                paragraphs = _repair_dialogue_action_after_final_detail(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append(f"q04_post_longform_detail_density_topup:{final_detail_topup}")
                repaired = _rebuild_draft(paragraphs, metadata)
            if story_text_unit_count(repaired.body) > max_target_word_count:
                paragraphs = _trim_to_max_units(
                    repaired.paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        final_length_floor = 0
        current_units = story_text_unit_count(repaired.body)
        while current_units < min_target_word_count and final_length_floor < 4:
            beat = scene_beats[(chapter_index + final_length_floor) % len(scene_beats)]
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=8200 + final_length_floor,
                ),
            )
            remediation_actions.append(f"length_gate_final_post_topup_floor:{final_length_floor}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            if story_text_unit_count("\n\n".join(paragraphs)) > max_target_word_count:
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            final_length_floor += 1
        paragraphs = list(repaired.paragraphs)
        if paragraphs and not _has_continuation_hook(paragraphs[-1]):
            paragraphs[-1] = strong_hook
            remediation_actions.append("q09_final_post_topup_hook_restore")
            repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats:
        lint_report = lint_chapter_draft(repaired.body)
        repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
        if (
            float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
            or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
            or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        ):
            paragraphs = _repair_repetition_after_final_detail(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            remediation_actions.append("q03_final_post_topup_coverage_repair")
            repaired = _rebuild_draft(paragraphs, metadata)
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
            if (
                float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) >= 0.42
                or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) >= 0.35
                or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
            ):
                paragraphs = list(repaired.paragraphs)
                for offset, beat in enumerate(_coverage_gap_target_beats(scene_beats, repetition_bundle)[:2]):
                    paragraphs.insert(
                        _hook_insert_index(paragraphs),
                        _coverage_anchor_echo_paragraph(
                            world,
                            state_before,
                            beat,
                            variant_seed=8600 + offset,
                            chapter_index=chapter_index,
                        ),
                    )
                    remediation_actions.append(f"q03_final_anchor_echo_insert:{offset}")
                if story_text_unit_count("\n\n".join(paragraphs)) > max_target_word_count:
                    paragraphs = _trim_to_max_units(
                        paragraphs,
                        min_target_word_count=min_target_word_count,
                        max_target_word_count=max_target_word_count,
                        scene_beats=scene_beats,
                        remediation_actions=remediation_actions,
                    )
                repaired = _rebuild_draft(paragraphs, metadata)
                lint_report = lint_chapter_draft(repaired.body)
        if (
            float(lint_report.get("exposition_ratio", 0.0) or 0.0) > (0.5 if story_text_unit_count(repaired.body) >= 1800 else 0.44)
            or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.42
        ):
            paragraphs = _repair_final_q04_micro(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            paragraphs = _repair_dialogue_action_after_final_detail(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
            )
            remediation_actions.append("q04_final_post_topup_repair")
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            post_q04_length_floor = 0
            while current_units < min_target_word_count and post_q04_length_floor < 3:
                beat = scene_beats[(chapter_index + post_q04_length_floor + 1) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=8400 + post_q04_length_floor,
                    ),
                )
                remediation_actions.append(f"length_gate_post_final_q04_guard:{post_q04_length_floor}")
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                post_q04_length_floor += 1
            paragraphs = list(repaired.paragraphs)
            if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                paragraphs[-1] = strong_hook
                remediation_actions.append("q09_post_final_q04_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats and longform_mode:
        lint_report = lint_chapter_draft(repaired.body)
        if float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < LONGFORM_STOP_READY_DIALOGUE_TARGET:
            paragraphs = _repair_longform_stop_ready_dialogue_guard(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=5,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            length_recover = 0
            while current_units < min_target_word_count and length_recover < 2:
                beat = scene_beats[(chapter_index + length_recover) % len(scene_beats)]
                paragraphs = list(repaired.paragraphs)
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - current_units,
                        expansion_index=9000 + length_recover,
                    ),
                )
                remediation_actions.append(f"length_gate_post_stop_ready_dialogue:{length_recover}")
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                current_units = story_text_unit_count(repaired.body)
                length_recover += 1
            paragraphs = list(repaired.paragraphs)
            if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                paragraphs[-1] = strong_hook
                remediation_actions.append("q09_post_stop_ready_dialogue_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)
            if detail_polish_mode:
                lint_report = lint_chapter_draft(repaired.body)
                if float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < 0.07:
                    paragraphs = _repair_detail_density_after_trim(
                        repaired.paragraphs,
                        world=world,
                        state_before=state_before,
                        scene_beats=scene_beats,
                        min_target_word_count=min_target_word_count,
                        max_target_word_count=max_target_word_count,
                        remediation_actions=remediation_actions,
                        target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                        min_detail_count=max(
                            12,
                            int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR),
                        ),
                        max_attempts=4,
                        fast_scene_detail_only=False,
                    )
                    remediation_actions.append("q05_post_stop_ready_dialogue_detail_restore")
                    paragraphs = _dedupe_repeated_sentences(
                        paragraphs,
                        world=world,
                        state_before=state_before,
                        scene_beats=scene_beats,
                    )
                    paragraphs = _trim_to_max_units(
                        paragraphs,
                        min_target_word_count=min_target_word_count,
                        max_target_word_count=max_target_word_count,
                        scene_beats=scene_beats,
                        remediation_actions=remediation_actions,
                    )
                    repaired = _rebuild_draft(paragraphs, metadata)
                    lint_report = lint_chapter_draft(repaired.body)
                    if (
                        float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0)
                        < LONGFORM_STOP_READY_DIALOGUE_TARGET
                    ):
                        paragraphs = _repair_longform_stop_ready_dialogue_guard(
                            repaired.paragraphs,
                            world=world,
                            state_before=state_before,
                            scene_beats=scene_beats,
                            min_target_word_count=min_target_word_count,
                            max_target_word_count=max_target_word_count,
                            remediation_actions=remediation_actions,
                            max_attempts=2,
                        )
                        repaired = _rebuild_draft(paragraphs, metadata)

    if scene_beats and longform_mode:
        for balance_attempt in range(2):
            changed = False
            lint_report = lint_chapter_draft(repaired.body)
            repetition_bundle = dict(lint_report.get("repetition_signal_bundle") or {})
            if (
                _needs_final_repetition_repair(lint_report, repetition_bundle)
                or float(lint_report.get("repetition_score", 0.0) or 0.0) > 0.18
            ):
                paragraphs = _repair_repetition_after_final_detail(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=2,
                )
                remediation_actions.append(f"q03_final_stop_ready_balance:{balance_attempt}")
                repaired = _rebuild_draft(paragraphs, metadata)
                changed = True

            lint_report = lint_chapter_draft(repaired.body)
            if float(lint_report.get("exposition_ratio", 0.0) or 0.0) > 0.49:
                paragraphs = _repair_final_q04_micro(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                paragraphs = _repair_dialogue_action_after_final_detail(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                )
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
                remediation_actions.append(f"q04_final_stop_ready_balance:{balance_attempt}")
                repaired = _rebuild_draft(paragraphs, metadata)
                changed = True

            lint_report = lint_chapter_draft(repaired.body)
            if detail_polish_mode and float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < 0.07:
                paragraphs = _repair_detail_density_after_trim(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                    min_detail_count=max(
                        12,
                        int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR),
                    ),
                    max_attempts=5,
                    fast_scene_detail_only=False,
                )
                remediation_actions.append(f"q05_final_stop_ready_balance:{balance_attempt}")
                paragraphs = _dedupe_repeated_sentences(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                )
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                changed = True

            lint_report = lint_chapter_draft(repaired.body)
            if float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < LONGFORM_STOP_READY_DIALOGUE_TARGET:
                paragraphs = _repair_longform_stop_ready_dialogue_guard(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=3,
                )
                repaired = _rebuild_draft(paragraphs, metadata)
                changed = True

            if not changed:
                break

        lint_report = lint_chapter_draft(repaired.body)
        if (
            detail_polish_mode
            and float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < 0.065
            and float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0)
            >= LONGFORM_STOP_READY_DIALOGUE_TARGET + 0.03
        ):
            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                min_detail_count=max(
                    12,
                    int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR),
                ),
                max_attempts=3,
                fast_scene_detail_only=False,
            )
            remediation_actions.append("q05_final_stop_ready_buffered_topup")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            if story_text_unit_count("\n\n".join(paragraphs)) > max_target_word_count:
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
            repaired = _rebuild_draft(paragraphs, metadata)

        repetition_bundle = _coverage_repetition_bundle(repaired.paragraphs, scene_beats)
        if (
            float(repetition_bundle.get("event_coverage_gap_score", 0.0) or 0.0) > 0.42
            or float(repetition_bundle.get("beat_coverage_gap_score", 0.0) or 0.0) > 0.35
            or int(repetition_bundle.get("uncovered_beat_count", 0) or 0) > 0
        ):
            paragraphs = list(repaired.paragraphs)
            for offset, beat in enumerate(_coverage_gap_target_beats(scene_beats, repetition_bundle)[:2]):
                bridge = _coverage_anchor_echo_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=9400 + offset,
                    chapter_index=chapter_index,
                )
                replace_index = _final_repetition_replace_index(paragraphs, repetition_bundle, scene_beats)
                if replace_index is None:
                    paragraphs.insert(_hook_insert_index(paragraphs), bridge)
                    remediation_actions.append(f"q03_final_stop_ready_anchor_insert:{offset}")
                else:
                    paragraphs[replace_index] = bridge
                    remediation_actions.append(f"q03_final_stop_ready_anchor_replace:{replace_index}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            if story_text_unit_count("\n\n".join(paragraphs)) > max_target_word_count:
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
            repaired = _rebuild_draft(paragraphs, metadata)

        current_units = story_text_unit_count(repaired.body)
        length_recover = 0
        while current_units < min_target_word_count and length_recover < 2:
            beat = scene_beats[(chapter_index + length_recover) % len(scene_beats)]
            paragraphs = list(repaired.paragraphs)
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _length_expansion_paragraph(
                    world,
                    state_before,
                    beat,
                    remaining_units=min_target_word_count - current_units,
                    expansion_index=9300 + length_recover,
                ),
            )
            remediation_actions.append(f"length_gate_final_stop_ready_balance:{length_recover}")
            paragraphs = _dedupe_repeated_sentences(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
            )
            repaired = _rebuild_draft(paragraphs, metadata)
            current_units = story_text_unit_count(repaired.body)
            length_recover += 1
        paragraphs = list(repaired.paragraphs)
        if paragraphs and not _has_continuation_hook(paragraphs[-1]):
            paragraphs[-1] = strong_hook
            remediation_actions.append("q09_final_stop_ready_balance_hook_restore")
            repaired = _rebuild_draft(paragraphs, metadata)

        paragraphs = _repair_longform_surface_issue_mix_guard(
            repaired.paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=5,
        )
        repaired = _rebuild_draft(paragraphs, metadata)
        if story_text_unit_count(repaired.body) < min_target_word_count:
            paragraphs = list(repaired.paragraphs)
            recover_attempt = 0
            while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and recover_attempt < 2:
                beat = scene_beats[(chapter_index + recover_attempt) % len(scene_beats)]
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    compose_late_longform_compact_exchange(
                        world,
                        state_before,
                        beat,
                        repeated=True,
                        variant_offset=9900 + recover_attempt,
                    ),
                )
                remediation_actions.append(f"length_gate_longform_surface_guard:{recover_attempt}")
                recover_attempt += 1
            paragraphs = _repair_longform_surface_issue_mix_guard(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=2,
            )
            repaired = _rebuild_draft(paragraphs, metadata)

        lint_report = lint_chapter_draft(repaired.body)
        if detail_polish_mode and float(lint_report.get("concrete_detail_density", 0.0) or 0.0) < 0.065:
            paragraphs = _repair_detail_density_after_trim(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                target_density=LONGFORM_DETAIL_DENSITY_POLISH_TARGET,
                min_detail_count=max(
                    12,
                    int(story_text_unit_count(repaired.body) * LONGFORM_DETAIL_DENSITY_POLISH_FLOOR),
                ),
                max_attempts=4,
                fast_scene_detail_only=False,
            )
            remediation_actions.append("q05_after_longform_surface_guard")
            paragraphs = _dialogize_longform_exposition_surface(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
                max_attempts=4,
            )
            paragraphs = _scrub_longform_suspicious_refrains(
                paragraphs,
                chapter_index=chapter_index,
                remediation_actions=remediation_actions,
            )
            if story_text_unit_count("\n\n".join(paragraphs)) > max_target_word_count:
                paragraphs = _trim_to_max_units(
                    paragraphs,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                )
            paragraphs = _repair_longform_surface_issue_mix_guard(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=3,
            )
            paragraphs = _inline_longform_detail_surface_topup(
                paragraphs,
                state_before=state_before,
                scene_beats=scene_beats,
                remediation_actions=remediation_actions,
                target_density=0.065,
                max_attempts=4,
            )
            repaired = _rebuild_draft(paragraphs, metadata)

        if scene_beats and longform_mode:
            paragraphs = list(repaired.paragraphs)
            length_recover = 0
            while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and length_recover < 3:
                beat = scene_beats[(chapter_index + length_recover) % len(scene_beats)]
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _length_expansion_paragraph(
                        world,
                        state_before,
                        beat,
                        remaining_units=min_target_word_count - story_text_unit_count("\n\n".join(paragraphs)),
                        expansion_index=9950 + length_recover,
                    ),
                )
                remediation_actions.append(f"length_gate_final_longform_surface_floor:{length_recover}")
                length_recover += 1
            if length_recover:
                paragraphs = _repair_longform_surface_issue_mix_guard(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=2,
                )
                paragraphs = _inline_longform_detail_surface_topup(
                    paragraphs,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    remediation_actions=remediation_actions,
                    target_density=0.065,
                    max_attempts=3,
                )
                final_recover = 0
                while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and final_recover < 6:
                    beat = scene_beats[(chapter_index + final_recover + 7) % len(scene_beats)]
                    paragraphs.insert(
                        _hook_insert_index(paragraphs),
                        _length_expansion_paragraph(
                            world,
                            state_before,
                            beat,
                            remaining_units=min_target_word_count - story_text_unit_count("\n\n".join(paragraphs)),
                            expansion_index=9980 + final_recover,
                        ),
                    )
                    remediation_actions.append(f"length_gate_final_longform_surface_refloor:{final_recover}")
                    final_recover += 1
                if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                    paragraphs[-1] = strong_hook
                    remediation_actions.append("q09_final_longform_surface_floor_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)

        if scene_beats and longform_mode:
            paragraphs = list(repaired.paragraphs)
            lint_report = lint_chapter_draft("\n\n".join(paragraphs))
            repetition_bundle = _coverage_repetition_bundle(paragraphs, scene_beats)
            if (
                story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count
                or _longform_surface_q03_needs_repair(lint_report, repetition_bundle)
            ):
                paragraphs = _repair_longform_surface_issue_mix_guard(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=4,
                )
                final_guard_recover = 0
                while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and final_guard_recover < 6:
                    beat = scene_beats[(chapter_index + final_guard_recover + 13) % len(scene_beats)]
                    paragraphs.insert(
                        _hook_insert_index(paragraphs),
                        _length_expansion_paragraph(
                            world,
                            state_before,
                            beat,
                            remaining_units=min_target_word_count - story_text_unit_count("\n\n".join(paragraphs)),
                            expansion_index=10040 + final_guard_recover,
                        ),
                    )
                    remediation_actions.append(f"length_gate_final_longform_contract_refloor:{final_guard_recover}")
                    final_guard_recover += 1
                paragraphs = _scrub_longform_suspicious_refrains(
                    paragraphs,
                    chapter_index=chapter_index,
                    remediation_actions=remediation_actions,
                )
                if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                    paragraphs[-1] = strong_hook
                    remediation_actions.append("q09_final_longform_contract_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)

        if scene_beats and longform_mode and chapter_index >= 20:
            lint_report = lint_chapter_draft(repaired.body)
            if float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < 0.54:
                paragraphs = list(repaired.paragraphs)
                final_dialogue_inline = 0
                while final_dialogue_inline < 8:
                    lint_report = lint_chapter_draft("\n\n".join(paragraphs))
                    if float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) >= LONGFORM_STOP_READY_DIALOGUE_TARGET:
                        break
                    candidates = [
                        index
                        for index, paragraph in enumerate(paragraphs)
                        if index < len(paragraphs) - 1 and not _has_continuation_hook(paragraph)
                    ]
                    if not candidates:
                        candidates = list(range(0, max(0, len(paragraphs) - 1)))
                    if not candidates:
                        break
                    target_index = max(
                        candidates,
                        key=lambda index: (
                            1 if _is_exposition_paragraph(paragraphs[index]) else 0,
                            -_paragraph_action_count(paragraphs[index]),
                            _paragraph_anchor_score(paragraphs[index], scene_beats),
                            -story_text_unit_count(paragraphs[index]),
                        ),
                    )
                    beat = _beat_for_paragraph(paragraphs[target_index], scene_beats, fallback_index=target_index + final_dialogue_inline)
                    paragraphs[target_index] = " ".join(
                        [
                            paragraphs[target_index].rstrip(),
                            _compact_action_dialogue_sentence(
                                world,
                                state_before,
                                beat,
                                variant_seed=10120 + final_dialogue_inline + target_index * 19,
                            ),
                        ]
                    ).strip()
                    remediation_actions.append(f"q04_final_dialogue_inline:{target_index}")
                    final_dialogue_inline += 1
                final_dialogue_recover = 0
                while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and final_dialogue_recover < 4:
                    beat = scene_beats[(chapter_index + final_dialogue_recover + 17) % len(scene_beats)]
                    paragraphs.insert(
                        _hook_insert_index(paragraphs),
                        compose_late_longform_compact_exchange(
                            world,
                            state_before,
                            beat,
                            repeated=True,
                            variant_offset=10120 + final_dialogue_recover,
                        ),
                    )
                    remediation_actions.append(f"q04_final_dialogue_refloor:{final_dialogue_recover}")
                    final_dialogue_recover += 1
                paragraphs = _scrub_longform_suspicious_refrains(
                    paragraphs,
                    chapter_index=chapter_index,
                    remediation_actions=remediation_actions,
                )
                if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                    paragraphs[-1] = strong_hook
                    remediation_actions.append("q09_final_dialogue_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)

        if scene_beats and longform_mode and chapter_index >= 20:
            paragraphs = _final_longform_q03_closeout(
                repaired.paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=4,
            )
            final_refloor = 0
            while story_text_unit_count("\n\n".join(paragraphs)) < min_target_word_count and final_refloor < 3:
                beat = scene_beats[(chapter_index + final_refloor + 23) % len(scene_beats)]
                paragraphs.insert(
                    _hook_insert_index(paragraphs),
                    _lexical_repetition_relief_paragraph(
                        world,
                        state_before,
                        beat,
                        variant_seed=11320 + final_refloor,
                        chapter_index=chapter_index,
                    ),
                )
                remediation_actions.append(f"length_gate_final_longform_q03_closeout:{final_refloor}")
                paragraphs = _final_longform_q03_closeout(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=2,
                )
                final_refloor += 1
            paragraphs = _scrub_longform_suspicious_refrains(
                paragraphs,
                chapter_index=chapter_index,
                remediation_actions=remediation_actions,
            )
            if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                paragraphs[-1] = strong_hook
                remediation_actions.append("q09_final_longform_q03_closeout_hook_restore")
            repaired = _rebuild_draft(paragraphs, metadata)

        if scene_beats and longform_mode and chapter_index >= 20:
            lint_report = lint_chapter_draft(repaired.body)
            if (
                float(lint_report.get("exposition_ratio", 0.0) or 0.0) > LONGFORM_STOP_READY_EXPOSITION_TARGET
                or float(lint_report.get("dialogue_plus_action_ratio", 0.0) or 0.0) < LONGFORM_STOP_READY_DIALOGUE_TARGET
            ):
                paragraphs = _final_longform_q04_closeout(
                    repaired.paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=5,
                )
                paragraphs = _final_longform_q03_closeout(
                    paragraphs,
                    world=world,
                    state_before=state_before,
                    scene_beats=scene_beats,
                    min_target_word_count=min_target_word_count,
                    max_target_word_count=max_target_word_count,
                    remediation_actions=remediation_actions,
                    max_attempts=2,
                )
                if paragraphs and not _has_continuation_hook(paragraphs[-1]):
                    paragraphs[-1] = strong_hook
                    remediation_actions.append("q09_final_longform_q04_closeout_hook_restore")
                repaired = _rebuild_draft(paragraphs, metadata)

    cleaned_body, broken_slot_report = clean_broken_reader_slots(repaired.body)
    if broken_slot_report.get("broken_slot_repaired") or cleaned_body != repaired.body.strip():
        repaired = _rebuild_draft(
            [paragraph for paragraph in cleaned_body.split("\n\n") if paragraph.strip()],
            metadata,
        )
        remediation_actions.append("broken_slot_final_sanitize")

    if scene_beats and longform_mode and chapter_index >= 20:
        paragraphs = list(repaired.paragraphs)
        final_floor_attempt = 0
        while final_floor_attempt < 3:
            lint_report = lint_chapter_draft("\n\n".join(paragraphs))
            if (
                story_text_unit_count("\n\n".join(paragraphs)) >= min_target_word_count
                and float(lint_report.get("concrete_detail_density", 0.0) or 0.0) >= CONTRACT_DETAIL_DENSITY_FLOOR
            ):
                break
            beat = scene_beats[(chapter_index + final_floor_attempt + 31) % len(scene_beats)]
            paragraphs.insert(
                _hook_insert_index(paragraphs),
                _dialogue_scene_replacement_paragraph(
                    world,
                    state_before,
                    beat,
                    variant_seed=11600 + final_floor_attempt,
                    chapter_index=chapter_index,
                ),
            )
            remediation_actions.append(f"length_detail_final_longform_floor:{final_floor_attempt}")
            paragraphs = _final_longform_q04_closeout(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=2,
            )
            paragraphs = _final_longform_q03_closeout(
                paragraphs,
                world=world,
                state_before=state_before,
                scene_beats=scene_beats,
                min_target_word_count=min_target_word_count,
                max_target_word_count=max_target_word_count,
                remediation_actions=remediation_actions,
                max_attempts=2,
            )
            final_floor_attempt += 1
        if paragraphs and not _has_continuation_hook(paragraphs[-1]):
            paragraphs[-1] = strong_hook
            remediation_actions.append("q09_final_floor_hook_restore")
        paragraphs = _final_longform_surface_reconcile(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=3,
        )
        paragraphs = _force_longform_q04_paragraph_mix(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=3,
        )
        paragraphs = _final_longform_q03_closeout(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            max_target_word_count=max_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=3,
        )
        paragraphs = _force_longform_q04_paragraph_mix(
            paragraphs,
            world=world,
            state_before=state_before,
            scene_beats=scene_beats,
            min_target_word_count=min_target_word_count,
            remediation_actions=remediation_actions,
            max_attempts=2,
        )
        if paragraphs and not _has_continuation_hook(paragraphs[-1]):
            paragraphs[-1] = strong_hook
            remediation_actions.append("q09_final_surface_reconcile_hook_restore")
        repaired = _rebuild_draft(paragraphs, metadata)

    repaired.metadata["target_word_count"] = target_word_count
    repaired.metadata["min_target_word_count"] = min_target_word_count
    repaired.metadata["max_target_word_count"] = max_target_word_count
    repaired.metadata["text_unit_count"] = story_text_unit_count(repaired.body)
    repaired.metadata["quality_pass_actions"] = remediation_actions
    repaired.metadata["quality_pass_applied"] = bool(remediation_actions)
    return repaired
