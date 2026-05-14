from __future__ import annotations

from ..models import SceneBeat, WorldBible
from .contracts import style_pack_from_world

DETAIL_MARKERS = [
    "灯", "袖", "茶", "风", "门", "阶", "檐", "影", "衣", "案", "纸", "雨", "香", "窗", "灯影",
    "栏", "栏杆", "杯", "杯沿", "门框", "木板", "纸页", "桌沿", "桌角", "器物", "石径", "叶影",
    "扫描台", "蓝线", "红灯", "防潮盒", "钝印", "胶痕", "签章", "声纹", "画稿", "盐壳", "录音笔", "话筒",
    "石砖", "空杯", "窗纸", "木栏", "地板", "檐角", "冷光", "回声", "香灰", "笔架", "卷面", "号板",
    "墨迹", "鞋底", "手背", "发梢", "灰尘", "水痕", "潮气", "湿气", "衣摆", "袖口",
]
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
}


def _pick_line(lines: list[str], index: int) -> str:
    return lines[index % len(lines)] if lines else ""


def _detail_marker_count(text: str) -> int:
    return sum(str(text or "").count(marker) for marker in DETAIL_MARKERS)


def _beat_seed(beat: SceneBeat, *, chapter_index: int = 0, extra: int = 0) -> int:
    event_id = str(getattr(beat.event, "event_id", "") or "")
    title = str(getattr(beat.event, "title", "") or "")
    scene_function = str(getattr(beat.event, "scene_function", "") or "")
    beat_index = int(getattr(beat, "beat_index", 0) or 0)
    return sum(ord(char) for char in f"{event_id}:{title}:{scene_function}") + beat_index * 17 + int(chapter_index) * 31 + int(extra)


def _scene_quality_contract(beat: SceneBeat) -> dict[str, object]:
    metadata = dict(getattr(beat.event, "metadata", {}) or {})
    return dict(metadata.get("scene_quality_contract") or {})


def _keyword_anchors(text: str) -> dict[str, list[str]]:
    normalized = str(text or "")
    anchors = {
        "object": [],
        "sound": [],
        "body_motion": [],
        "ambient_signal": [],
        "object_state": [],
    }
    keyword_map = {
        "档": {"object": ["防潮盒", "扫描台", "空白页"], "sound": ["锁扣声", "提示音"], "object_state": ["胶痕", "潮痕", "签章"]},
        "录音": {"object": ["录音带", "声纹图", "纸签"], "sound": ["磁带轻响", "回放底噪"], "object_state": ["水渍", "卷边"]},
        "签": {"object": ["签字页", "签章", "纸页"], "object_state": ["折痕", "焦痕", "墨迹"]},
        "考": {"object": ["号板", "卷面", "笔架"], "sound": ["落笔声", "木板轻响"], "ambient_signal": ["汗气", "墨香"]},
        "卷": {"object": ["卷面", "朱批", "笔架"], "sound": ["落笔声", "翻卷声"], "object_state": ["墨迹", "折角"]},
        "庭": {"object": ["廊柱", "石阶", "花枝"], "sound": ["帘钩声", "玉佩轻响"], "ambient_signal": ["香灰", "冷光"]},
        "殿": {"object": ["灯座", "玉阶", "香炉"], "sound": ["钟声", "衣袂轻响"], "ambient_signal": ["檀香", "冷雾"], "object_state": ["裂纹"]},
        "山门": {"object": ["山门石阶", "剑穗", "符纸"], "sound": ["钟磬声", "衣袂声"], "ambient_signal": ["云气", "霜意"]},
        "镜湖": {"object": ["湖面碎光", "灯座", "石栏"], "sound": ["水声", "风过铃声"], "ambient_signal": ["水雾", "月色"]},
        "花": {"object": ["花枝", "石径", "湿叶"], "sound": ["叶响", "鞋底轻擦声"], "ambient_signal": ["湿气", "灯色"]},
        "窗": {"object": ["窗纸", "杯沿", "门框"], "sound": ["窗缝风声", "杯沿轻响"], "ambient_signal": ["冷光"]},
        "港": {"object": ["栏杆", "船绳", "石板"], "sound": ["浪声", "缆绳摩擦声"], "ambient_signal": ["水气", "盐味"], "object_state": ["盐壳"]},
        "潮": {"object": ["防潮盒", "盐壳", "水线"], "sound": ["浪声", "水滴声"], "ambient_signal": ["潮气", "盐味"], "object_state": ["潮痕"]},
        "巷": {"object": ["雨棚", "旧门牌", "监控探头"], "sound": ["电流声", "鞋底水声"], "ambient_signal": ["霓虹冷光", "潮墙气"]},
        "莲": {"object": ["莲纹砖", "雨伞骨", "玻璃柜"], "sound": ["雨棚滴水", "路灯电流"], "ambient_signal": ["湿雾", "油烟冷味"]},
    }
    for keyword, typed_values in keyword_map.items():
        if keyword not in normalized:
            continue
        for anchor_type, values in typed_values.items():
            anchors[anchor_type].extend(str(value) for value in values)
    return anchors


def _location_anchor_pool(location: str, scene_function: str, anchor_type: str) -> list[str]:
    normalized_location = str(location or "")
    scene_label = SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))
    base = {
        "object": ["杯沿", "门框", "纸页", "桌沿", "案角", "栏杆", "灯座", "石阶", "防潮盒", "雨棚"],
        "sound": ["回声", "轻响", "翻页声", "风声", "脚步声", "器物碰响", "落笔声", "水滴声", "钟声", "电流声"],
        "body_motion": ["指节", "衣袖", "呼吸", "脚步", "发梢", "肩背", "掌心", "手背", "衣摆", "眼睫"],
        "ambient_signal": ["灯影", "冷光", "潮气", "香气", "灰尘", "湿意", "檀香", "云气", "盐味", "霓虹冷光"],
        "object_state": ["折痕", "磨痕", "裂口", "水痕", "胶痕", "潮痕", "盐壳", "卷边", "钝印", "裂纹"],
    }
    keyword_anchors = _keyword_anchors(f"{normalized_location} {scene_label}")
    specific = list(keyword_anchors.get(anchor_type) or [])
    generic = list(base.get(anchor_type) or [])
    merged = specific + (generic[:4] if specific else generic)
    deduped: list[str] = []
    for value in merged:
        candidate = str(value).strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _pick_anchor(pool: list[str], *, seed: int, fallback: str) -> str:
    if not pool:
        return fallback
    return pool[seed % len(pool)]


def _detail_enrichment_tail(location: str, scene_function: str, *, variant_index: int) -> str:
    label = SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))
    variants = [
        f"{location}边的窗、门、灯影、衣袖和案角纸页一起压上来，连茶气、脚步声和桌边那一下轻响都把这一步{label}里的分寸照得更清。",
        f"风从{location}外掠过门檐，带得窗边、阶前、衣角和桌面都起了一层轻微的动静，连灯下那点影子、香气和纸页翻动都把这场{label}压得更近。",
        f"{location}里的灯、纸、窗、袖影、门缝和回声并没有安静下来，反而在风声、脚步和桌沿碰响里一点点把这一步{label}的重量托了出来。",
        f"{location}里那点雨味、灰尘、灯火和门边冷气一起贴上来，连衣摆扫过地面的动静都像替这一步{label}把后劲拖长了一寸。",
        f"越靠近{location}里面，窗纸、杯沿、门框、灯影和衣袖摩擦出的细响越清，像所有东西都在替这一步{label}记账。",
    ]
    return variants[variant_index % len(variants)]


def _dynamic_detail_tail(beat: SceneBeat, *, chapter_index: int = 0, variant_index: int = 0) -> str:
    location = beat.event.location or "眼前这一处"
    scene_function = beat.event.scene_function
    label = SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))
    contract = _scene_quality_contract(beat)
    anchor_types = list(contract.get("detail_anchor_types") or ["object", "sound", "body_motion", "ambient_signal"])
    if "object" not in anchor_types:
        anchor_types.insert(0, "object")
    if "sound" not in anchor_types:
        anchor_types.append("sound")
    if "body_motion" not in anchor_types:
        anchor_types.append("body_motion")
    if "ambient_signal" not in anchor_types:
        anchor_types.append("ambient_signal")
    seed = _beat_seed(beat, chapter_index=chapter_index, extra=variant_index)

    object_pool = _location_anchor_pool(location, scene_function, "object") + list(_keyword_anchors(f"{beat.event.title} {beat.event.summary}").get("object") or [])
    sound_pool = _location_anchor_pool(location, scene_function, "sound") + list(_keyword_anchors(f"{beat.event.title} {beat.event.summary}").get("sound") or [])
    body_pool = _location_anchor_pool(location, scene_function, "body_motion")
    ambient_pool = _location_anchor_pool(location, scene_function, "ambient_signal")
    state_pool = _location_anchor_pool(location, scene_function, "object_state") + list(_keyword_anchors(f"{beat.event.title} {beat.event.summary}").get("object_state") or [])

    object_a = _pick_anchor(object_pool, seed=seed, fallback="杯沿")
    object_b = _pick_anchor(object_pool, seed=seed + 3, fallback="门框")
    sound = _pick_anchor(sound_pool, seed=seed + 5, fallback="回声")
    body = _pick_anchor(body_pool, seed=seed + 7, fallback="指节")
    ambient = _pick_anchor(ambient_pool, seed=seed + 11, fallback="灯影")
    state = _pick_anchor(state_pool, seed=seed + 13, fallback="折痕")

    variants = [
        f"{location}里{ambient}贴着{object_a}、{object_b}和{body}一起逼近，连{sound}都把这一步{label}压成了摸得着的重量，连{state}也被灯下那层冷意照了出来。",
        f"{location}边的{object_a}、{object_b}和{body}先撞出一点细响，{ambient}顺着门边压回来，让{sound}把这一步{label}真正钉在了{state}还没散开的那一层上。",
        f"越往{location}里面走，{ambient}就越贴着{object_a}、{object_b}和{body}不放，连{sound}和{state}都开始替这一步{label}留下具体的痕。",
        f"{location}里先显出来的不是谁的脸色，而是{object_a}、{object_b}、{body}和{ambient}一起把{sound}压得更清，连{state}都像在替这一步{label}记账。",
    ]
    return variants[(seed + len(anchor_types)) % len(variants)]


def scene_atmosphere(world: WorldBible, beat: SceneBeat, *, chapter_index: int = 0) -> str:
    style_pack = style_pack_from_world(world)
    location = beat.event.location or "generic"
    beat_index = getattr(beat, "beat_index", 0)
    event_seed = sum(ord(char) for char in str(getattr(beat.event, "event_id", "") or ""))
    variant_index = beat_index + event_seed + int(chapter_index) * 3
    slots = style_pack.sensory_grounding.location_slots.get(location, {})
    atmosphere = slots.get("atmosphere", [])
    if atmosphere:
        return _pick_line(atmosphere, variant_index)
    generic = style_pack.sensory_grounding.generic_slots.get("atmosphere", [])
    if generic:
        return _pick_line(generic, variant_index)
    return f"{location}里并不安静，连空气都像在替谁压住一口没说完的话。"


def scene_detail(world: WorldBible, beat: SceneBeat, *, repeated: bool, chapter_index: int = 0) -> str:
    style_pack = style_pack_from_world(world)
    location = beat.event.location or "generic"
    beat_index = getattr(beat, "beat_index", 0)
    event_seed = sum(ord(char) for char in str(getattr(beat.event, "event_id", "") or ""))
    variant_index = beat_index + event_seed + int(chapter_index) * 3
    slots = style_pack.sensory_grounding.location_slots.get(location, {})
    key = "repeat_detail" if repeated else "detail"
    details = slots.get(key, [])
    generic = style_pack.sensory_grounding.generic_slots.get(key, [])
    if details:
        chosen = _pick_line(details, variant_index)
    elif generic:
        chosen = _pick_line(generic, variant_index)
    else:
        chosen = "灯影和衣角的轻微动静都被这一场沉默压得更清。"
    location = beat.event.location or "眼前这一处"
    extras: list[str] = []
    if not repeated or _detail_marker_count(chosen) < 8:
        extras.append(_detail_enrichment_tail(location, beat.event.scene_function, variant_index=variant_index))
    if not repeated or _detail_marker_count(chosen) < 10:
        extras.append(_dynamic_detail_tail(beat, chapter_index=chapter_index, variant_index=variant_index))
    if extras:
        chosen = " ".join([chosen.rstrip(), *extras]).strip()
    return chosen
