from __future__ import annotations

import re

from ..models import NarrativeState, SceneBeat, WorldBible
from .contracts import style_pack_from_world
from .dialogue import compose_dialogue
from .emotion_actions import compose_emotion_action
from .sensory_grounding import scene_atmosphere, scene_detail

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


def _variant_index(beat: SceneBeat, *, chapter_index: int = 0, modulo: int) -> int:
    if modulo <= 0:
        return 0
    event_id = str(getattr(beat.event, "event_id", "") or "")
    scene_function = str(getattr(beat.event, "scene_function", "") or "")
    dramatic_job = str(getattr(beat, "dramatic_job", "") or "")
    event_seed = sum(ord(char) for char in f"{event_id}:{scene_function}:{dramatic_job}")
    chapter_seed = max(0, int(chapter_index))
    beat_seed = max(0, int(getattr(beat, "beat_index", 0)))
    chapter_band_seed = max(0, chapter_seed // 40)
    return (event_seed + chapter_seed * 7 + chapter_band_seed * 23 + beat_seed * 13) % modulo


def _opening_detail(beat: SceneBeat, *, chapter_index: int = 0) -> str:
    location = beat.event.location or "眼前这一处"
    scene_function = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    variants = [
        f"{location}边的门、窗、灯影和衣袖摩擦出的细响并没有停，连案角那页纸和茶气都把这一步{scene_function}的分量压得更清。",
        f"风从{location}外掠过檐角，带得阶前、窗边和衣角都起了一层轻微的动静，连灯下那点影子都把场面拢得更紧。",
        f"{location}里的光、影、纸页和回声并没有安静下来，反而一层层把这句还没说透的话托到了更近的地方。",
        f"{location}里先露出来的是器物边缘那点冷光，随后才是袖口、鞋底和门缝里细碎的响动，把{scene_function}压出新的方向。",
        f"{location}的空气被一声轻响分开，桌沿、窗纸和灯芯各自晃了一下，让这一步{scene_function}不再只靠一句话撑着。",
        f"{location}旁的阴影退了半寸，杯沿、水痕和衣摆上的尘色反倒更清，像在替场面换一层更具体的证词。",
        f"最先变重的不是人声，而是{location}里那点冷风、旧木味和纸页摩擦声，把{scene_function}从心里推回了眼前。",
        f"{location}边有人轻轻挪了一步，鞋底擦过地面的声响拖得很短，却足够让灯影和门框把后果照得更近。",
        f"{location}里的细节没有再混成一团：茶气往上浮，窗缝发冷，案角那道浅痕也把这一步{scene_function}分出新的棱角。",
    ]
    return variants[_variant_index(beat, chapter_index=chapter_index, modulo=len(variants))]


def _event_anchor(beat: SceneBeat, *, chapter_index: int = 0) -> str:
    raw_title = str(getattr(beat.event, "title", "") or "").strip()
    if "·" in raw_title:
        raw_title = raw_title.split("·", 1)[1].strip()
    raw_title = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", raw_title).strip(" ·:：/|_-")
    raw_label = str(getattr(beat, "beat_label", "") or "").strip()
    if "·" in raw_label:
        raw_label = raw_label.split("·", 1)[-1].strip()
    if "：" in raw_label:
        raw_label = raw_label.split("：", 1)[1].strip()
    raw_label = raw_label.lstrip("·- ")
    raw_label = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", raw_label).strip(" ·:：/|_-")
    raw_title = raw_title.lstrip("·- ")
    if not raw_title:
        return ""
    location = beat.event.location or "眼前这一处"
    scene_function = SCENE_FUNCTION_LABELS.get(beat.event.scene_function, beat.event.scene_function.replace("_", " "))
    dramatic_job = str(getattr(beat, "dramatic_job", "") or "pressure")
    job_phrase = {
        "entry": "先把局势推到台面上的",
        "pressure": "把最难回避的那句逼近眼前的",
        "pivot": "让场面开始真正转向的",
        "aftermath": "在收声以后仍旧压着人心的",
        "echo": "顺着回声继续追上来的",
    }.get(dramatic_job, "真正压上来的")
    anchor_focus = raw_label or raw_title
    if any(fragment in anchor_focus for fragment in ["真正要转向", "这一拍留下来的余波"]):
        anchor_focus = raw_title
    if anchor_focus == location:
        anchor_focus = scene_function
    physical_markers = [
        "案角",
        "门影",
        "窗纸",
        "杯沿",
        "衣袖",
        "灯芯",
        "阶前风",
        "纸页声",
    ]
    marker = physical_markers[_variant_index(beat, chapter_index=chapter_index, modulo=len(physical_markers))]
    variants = [
        f"{location}里的{marker}先动了一下，{job_phrase}{scene_function}便不再像上一回那样散开。",
        f"{raw_title}并不算大，可一落进{location}，{job_phrase}那层余波就已经没法再轻轻带过去。",
        f"{marker}边那点停顿把{anchor_focus}换成了更具体的动作，连{location}的回声都跟着偏了方向。",
        f"{location}里的动静先围住{scene_function}，{job_phrase}压力没有抬高声量，却把退路压窄了半寸。",
        f"{raw_title}落下时，{location}里的灯影和脚步都停了一瞬，像是替{job_phrase}后果先留出位置。",
        f"{anchor_focus}没有被一句话带过去，反而顺着{location}里的纸页声和门缝冷意，把{scene_function}推向另一层代价。",
        f"{job_phrase}不是一句重话，而是{marker}、脚步和呼吸一起把{scene_function}推到了人物眼前。",
        f"{location}先把人钉在原处，随后才轮到{marker}旁的回声慢慢收紧，让这一拍换了走法。",
    ]
    return variants[_variant_index(beat, chapter_index=chapter_index, modulo=len(variants))]


def realize_scene_opening(
    world: WorldBible,
    beat: SceneBeat,
    chapter_goal: str,
    conflict_axis: str,
    *,
    chapter_index: int = 0,
) -> str:
    style_pack = style_pack_from_world(world)
    opening = style_pack.scene_realization.scene_openings.get(beat.event.scene_function, [])
    if opening:
        chosen = opening[_variant_index(beat, chapter_index=chapter_index, modulo=len(opening))]
    else:
        fallback_openings = [
            f"{chapter_goal}。{scene_atmosphere(world, beat, chapter_index=chapter_index)}",
            f"{scene_atmosphere(world, beat, chapter_index=chapter_index)} {chapter_goal}在这一刻终于逼近了明处。",
            f"{chapter_goal}被轻轻推开了一道口子，{scene_atmosphere(world, beat, chapter_index=chapter_index)}",
            f"{scene_atmosphere(world, beat, chapter_index=chapter_index)} {chapter_goal}没有沿着上一回的路走，反而从场面里另一处细响开始收紧。",
            f"{chapter_goal}先落在眼前的器物、脚步和回声里，随后才变成谁也绕不开的一句真话。",
            f"{scene_atmosphere(world, beat, chapter_index=chapter_index)} 这一回先改变的不是声量，而是{chapter_goal}压住人物动作的方式。",
        ]
        chosen = fallback_openings[_variant_index(beat, chapter_index=chapter_index, modulo=len(fallback_openings))]
    pressure_variants = style_pack.scene_realization.scene_pressures.get(beat.event.scene_function, [])
    pressure = (
        pressure_variants[_variant_index(beat, chapter_index=chapter_index, modulo=len(pressure_variants))]
        if pressure_variants
        else ""
    )
    suffixes = [
        f"压下来的先是{conflict_axis}，紧跟着便是人物再也躲不开的那一点心意。",
        f"先被推到眼前的是{conflict_axis}，随后才是那层更难承认的真心。",
        f"{conflict_axis}先落在场面上，真正迟一步追上来的，却是人心里更难藏的那句真话。",
        f"{conflict_axis}没有再停成抽象的难题，而是落到谁先移步、谁先开口、谁先认账的细处。",
        f"这一次先变紧的是{conflict_axis}背后的动作顺序，人物每退半步都会把后果推得更近。",
        f"{conflict_axis}被灯影和脚步分成了新的岔口，谁也没法再用上一回的沉默把它遮住。",
        f"真正压住人的不是同一句解释，而是{conflict_axis}在此刻换了形状，逼人物用新的动作接住它。",
    ]
    opening_detail = _opening_detail(beat, chapter_index=chapter_index)
    return " ".join(
        [
            chosen,
            pressure,
            suffixes[_variant_index(beat, chapter_index=chapter_index, modulo=len(suffixes))],
            opening_detail,
        ]
    )


def realize_beat(world: WorldBible, state_before: NarrativeState, beat: SceneBeat, *, repeated: bool) -> str:
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    longform_compact = chapter_index >= 20
    fragments = {
        "emotion": compose_emotion_action(world, state_before, beat, repeated=repeated),
        "dialogue": compose_dialogue(world, state_before, beat, repeated=repeated),
        "detail": scene_detail(world, beat, repeated=repeated, chapter_index=chapter_index),
    }
    orders = (
        [
            ["dialogue", "emotion", "detail"],
            ["dialogue", "detail", "emotion"],
            ["emotion", "dialogue", "detail"],
        ]
        if longform_compact
        else [
            ["emotion", "dialogue", "detail"],
            ["detail", "emotion", "dialogue"],
            ["dialogue", "emotion", "detail"],
        ]
    )
    order = orders[_variant_index(beat, chapter_index=chapter_index, modulo=len(orders))]
    anchor = _event_anchor(beat, chapter_index=chapter_index)
    if longform_compact and _variant_index(beat, chapter_index=chapter_index, modulo=3) != 0:
        anchor = ""
    body = " ".join([fragments[key] for key in order if fragments.get(key)])
    if anchor:
        return " ".join([anchor, body]).strip()
    return body


def realize_hook(world: WorldBible, ending_hook: str, scene_function: str, *, chapter_index: int = 0) -> str:
    style_pack = style_pack_from_world(world)
    hook = style_pack.scene_realization.scene_hooks.get(scene_function, [])
    if hook:
        chapter_seed = int(chapter_index)
        seed = sum(ord(char) for char in f"{scene_function}:{ending_hook}") + chapter_seed * 5 + (chapter_seed // 40) * 11
        return hook[seed % len(hook)]
    variants = [
        f"等人声慢慢静下去时，留下来的并不是哪一句话更重，而是{ending_hook}。那一点没说尽的情绪已经追到下一次开口之前。",
        f"场面虽然先停住了，可真正留下来的还是{ending_hook}。下一次再见时，这句余波不会自己散掉。",
        f"话音落下去以后，最先追上来的仍是{ending_hook}。真正难收的那点情绪已经压到下一章门口。",
        f"灯影和脚步都慢下来以后，真正没有退开的仍是{ending_hook}。下一次开口前，它会先换一种方式逼近。",
        f"人声收住时，{ending_hook}没有跟着收住，只从门边、案角和未完的动作里继续往前压。",
        f"这一场先停在这里，可{ending_hook}已经换成了更具体的余波，等下一次见面时不会再按原样回来。",
        f"最后静下来的不是心思，而是场面里那点声音；{ending_hook}仍旧留在人物还没做完的动作里。",
    ]
    chapter_seed = int(chapter_index)
    seed = sum(ord(char) for char in f"{scene_function}:{ending_hook}") + chapter_seed * 5 + (chapter_seed // 40) * 11
    return variants[seed % len(variants)]
