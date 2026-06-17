from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.contracts import (
    DialogueRealismPolicy,
    EmotionActionPolicy,
    ResponseCadenceProfile,
    SceneRealizationContract,
    SensoryGroundingPolicy,
    VoiceProfile,
    WorldNarrativeStylePack,
)
from ..models import CharacterState, CreatorControls, EventAtom, NarrativeState, WorldBible, WorldRecord
from ..scene_functions import normalize_scene_function
from .models import RuntimeBundle, SceneBlueprint, WorldPack, WorldVersion
from .validator import validate_worldpack_payload


BASE_DIR = Path(__file__).resolve().parents[3]
WORLDPACK_DIR = BASE_DIR / "examples" / "worldpacks"

SCENE_FUNCTION_LABELS = {
    "false_peace": "表面平静",
    "temptation": "试探与诱惑",
    "truth_trial": "真相逼近",
    "mask_crack": "面具裂口",
    "confession_window": "真话窗口",
    "debt_exchange": "旧账回潮",
    "karma_ripening": "因果回响",
    "humiliation": "难堪代价",
    "vow_payment": "誓言偿付",
    "misrecognition": "误解升级",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _ensure_variants(values: List[str], fallbacks: List[str], *, min_count: int = 5) -> List[str]:
    enriched = [str(item).strip() for item in values if str(item).strip()]
    for item in fallbacks:
        candidate = str(item).strip()
        if candidate and candidate not in enriched:
            enriched.append(candidate)
        if len(enriched) >= min_count:
            break
    return enriched[:max(min_count, len(enriched))]


def _voice_line_fallbacks(profile_key: str, field: str, voice: Dict[str, Any]) -> List[str]:
    sharper = float(voice.get("bluntness", 0.5)) >= 0.58
    restrained = float(voice.get("restraint", 0.5)) >= 0.62
    if field == "opening_style":
        return [
            "我先把杯沿按住，再把这句话放到明处。",
            "门边风一过，我就不想再躲了。",
            "案角纸页都响了，我不往回收。",
            "这句我先认，不再装稳。",
            "窗边那一下轻响过后，我不想再把真话按回去。",
        ] if not sharper else [
            "别绕，把这句话摁在桌上说。",
            "再装也没用了，我现在就要听见。",
            "裂口已经亮出来了，别指望我替你遮。",
            "你要是还退，我就继续追。",
            "这一步我不替你绕开。",
        ]
    if field == "pressure_style":
        return [
            "你要我认，我可以认，但别逼我再往后躲。",
            "事情已经压到这里，我不拿体面挡了。",
            "真话到嘴边了，我不想再咽回去。",
            "再退一步，代价只会换个地方落下。",
            "我可以先认，但不会再拿解释收场。",
        ] if not sharper else [
            "我不怕难听，只怕你又把退路藏回沉默里。",
            "再往后躲，这件事只会继续裂。",
            "你要往前走，就别指望我替你吞后果。",
            "我可以听你认错，但不会替你把场面讲圆。",
            "这层代价你今天得自己接。",
        ]
    if field == "pivot_style":
        return [
            "真正难的不是选路，是认自己已经偏过去了。",
            "这一步迈出去，就装不回去了。",
            "我不是不怕失去，只是不想再靠回避把人推远。",
            "现在追上来的不是解释，是后果。",
            "再装稳，伤口只会换个地方继续裂。",
        ] if not sharper else [
            "再绕半步，这事只会更坏。",
            "我可以听真话，但不会替谁缝裂口。",
            "事情拧到这里，继续装稳更像认输。",
            "你不肯转身，后果就顺着下一章追上来。",
            "我不会再让你拿慢半拍的解释拖过去。",
        ]
    if field == "aftermath_style":
        return [
            "话先落在这里，后面的亏欠我自己接。",
            "这句既然说出来，余下的难看也该我担。",
            "场面虽然停住了，可这事不会散掉。",
            "我先把这一层留在这里，回头还得自己认账。",
            "这句停住以后，谁也装不回刚才那副样子。",
        ] if not sharper else [
            "我先记着，回头你还是得把后半句带回来。",
            "这句先放在这里，迟早还得回来算清。",
            "我不替你收场，等你真肯认的时候再来补完。",
            "先停在这里，不代表这件事过去了。",
            "你今天不接，下一次它还是会追上来。",
        ]
    if field == "echo_style":
        return [
            "等下一次再开口时，我不会只带着半句真话回来。",
            "这一回先停在这里，可真正追上来的还在后面。",
            "下次再见时，这句话不会还只是个影子。",
            "这层没说尽的话已经压到下一章门口了。",
            "等人散开以后，最先回来的还是这句后劲。",
        ] if not sharper else [
            "下次见我时，别再只带着更圆的借口。",
            "这一回先收住，可下一次你还是得把真相带过来。",
            "等风声再追上来时，我不会让你再躲回原位。",
            "我先放你走一步，但后半句你迟早得自己补回来。",
            "这点余波不会自己散掉。",
        ]
    if field == "signature_replies":
        return [
            "我先把这句认下，剩下的我不会再推给局势。",
            "这层后果先算在我头上，别再让我装作没看见。",
            "该认的我会认，但我不想再靠沉默收场。",
            "我先把这一步接住，后面那层难看也该由我自己担。",
            "这次我不往回收了，真要疼也该先疼在明处。",
        ] if not sharper else [
            "我可以先不走，但你别指望我继续替你圆这层假平静。",
            "既然你肯开口，就别只给我半句真话。",
            "你最好现在就把话说透，别逼我下一次追得更深。",
            "今天这层后果你得自己接，别再让我替你圆场。",
            "这句如果还说不透，我下一次只会追得更紧。",
        ]
    return []


def _response_line_fallbacks(field: str, beat_key: str, *, sharper: bool) -> List[str]:
    if field == "reaction_lines":
        defaults = {
            "entry": [
                "他没有立刻接话，只把那点迟疑先压在眼底。",
                "她先收住了动作，反倒把场里的试探衬得更紧。",
                "谁都没急着开口，空气却已经先替这句真话让出了位置。",
                "灯下那一点冷光先晃了一下，谁都知道真正难说的那句已经逼近了。",
                "手边的纸页轻轻一响，像在替谁把下一句更重的话推到明处。",
            ],
            "pressure": [
                "呼吸和目光都顿了一下，像谁先动一下就会先露底。",
                "指尖轻轻一停，细小的响动反而把场面压得更紧。",
                "他先把那口气压回去半寸，结果连沉默都显得更重。",
                "衣角擦过桌沿的轻响很短，却把场里的退路一下子磨薄了。",
                "门边那点风声掠过去以后，连停顿都像在替人认错。",
            ],
            "pivot": [
                "这才抬起眼来，像终于不打算再给自己留余地。",
                "她开口时语气并不高，可每个字都落在最难回避的地方。",
                "那一下极轻的停顿，把还能周旋的局面一下子压成了选择。",
                "杯沿上的冷光一闪，连下一句该落到谁身上都跟着清楚了。",
                "对面的人没再补台阶，场面就这样硬生生拧到了更难退的一侧。",
            ],
            "aftermath": [
                "到收声的时候，反而比刚才更轻，也更沉。",
                "谁都没有继续逼，可那层不肯退的意思还停在原处。",
                "话停下以后，真正压人的反而是留在场里的余波。",
                "灯影没动，可桌边那层静像把后面的代价一起拖了出来。",
                "谁都先收了声，可衣袖、纸页和呼吸都还在替这句真话回响。",
            ],
            "echo": [
                "没再追着补话，可那点未尽之意还挂在场里。",
                "她先收了声，留下来的却是更明确的一层边界。",
                "等静下来以后，最先回来的还是那句没有说尽的话。",
                "下一次见面时，最先追上来的不会是解释，而是这层没认完的后果。",
                "人先散开了，可窗边那点回声还把后半句留在原地。",
            ],
        }
        return defaults.get(beat_key, defaults["pressure"])
    defaults = {
        "entry": [
            "这句话既然已经出口，就别再往回收了。",
            "既然都走到这里了，我不想再把这句收回去。",
            "你既然肯开口，就别只给我半句。",
            "这一步已经迈出来了，别再拿更轻的话压回去。",
            "既然都照出来了，就别再装作没看见。",
        ],
        "pressure": [
            "你总得先替自己承认一次。",
            "我不是不肯认，只是不想再拿沉默糊弄过去。",
            "你要真想往前走，就别再把退路藏在这后面。",
            "我可以听你认，但不会替你把后果讲圆。",
            "再躲一步，后面的账也只会换个地方继续追上来。",
        ],
        "pivot": [
            "再退半步，也只是让伤口换个地方继续裂。",
            "既然已经走到这里，我就不想再装作什么都没看见。",
            "我可以听真话，但不会再替谁把后果吞回去。",
            "这句真停在这里，下一次只会更难收。",
            "别再靠一句解释往后拖了。",
        ],
        "aftermath": [
            "这句先放在这里，后面的我会自己来认。",
            "这事不会就这样过去。",
            "回头你还是得自己把后半句带回来。",
            "这层账先记在这里，回头还是得有人自己来结。",
            "场面先停住了，可后面的难看不会自己消失。",
        ],
        "echo": [
            "下次再来时，别只带着更圆的借口。",
            "等下一次再说时，我会把真正该说的带过来。",
            "下一回再见，我要听的是你的真话，不是更顺耳的解释。",
            "下一次见面时，最先追上来的还是你今天没认完的那句。",
            "这点余波不会自己散掉，别想让它停在这一章外面。",
        ],
    }
    variants = defaults.get(beat_key, defaults["pressure"])
    return variants if not sharper else list(reversed(variants))


def _sensory_fallbacks(location: str, slot: str) -> List[str]:
    if slot == "atmosphere":
        return [
            f"{location}里的风、灯影、门缝和衣角摩擦出的细响贴得很近，像先把每个人心里的迟疑照到了明处。",
            f"{location}并不安静，连窗边的风声、案角的冷光和地上的回声都像在替场里的那句话压紧边界。",
            f"{location}里先变的不是声量，而是门、窗、灯、纸和影子一起把那层没说透的情绪压出了形状。",
            f"{location}里的空气带着潮意和旧气味，连脚边那一下轻响都像在替人把退路越收越窄。",
            f"{location}先静了一瞬，可灯、风、窗纸和衣袖边的响动没有停，反而把最难说的那句推得更近。",
        ]
    if slot == "detail":
        return [
            f"{location}里的灯影、窗纸、门框、案角和衣袖摩擦声都变得分外清楚，把场里的犹疑照得更薄。",
            f"{location}边上的细响、冷光、茶气、脚步和停顿一层层压上来，让人更难把这句话绕开。",
            f"连{location}里最轻的一点回声、纸页响动、风过门缝的凉意和衣摆扫过地面的声音，都像在替这场对峙补上更细的纹理。",
            f"{location}里那点雨味、灰尘、灯火和门边木纹一起贴上来，连呼吸都像有了能摸到的重量。",
            f"窗边那道冷光落到杯沿和纸页上，衣角、脚步、风声和香气全都把场面压得更近。",
        ]
    return [
        f"越到后面，{location}里最轻的一点灯响、风声和衣料摩擦反而把没说尽的话压得更重。",
        f"等沉默拖长以后，{location}里的回声、纸页轻响和门边冷气像把余波一遍遍推回场中心。",
        f"{location}没有立刻静下来，反而让那点没认下的心思顺着窗影和脚步声更难散掉。",
        f"人虽然收声了，可{location}里的灯、门、窗和案角都还替这层后劲留着痕。",
        f"这一层余波没有自己散掉，反而让{location}里的每一点细响都变成提醒。",
    ]


def _scene_opening_fallbacks(worldpack: WorldPack, scene_function: str) -> List[str]:
    label = SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))
    title = worldpack.title
    markers = ["门影", "案角", "窗纸", "灯芯", "杯沿"]
    return [
        f"{title}里的{markers[0]}先把这一步{label}照到人物手边，局势从动作里收紧。",
        f"{markers[1]}那点轻响落下后，{title}的{label}不再靠解释推进，而是逼人物当面回应。",
        f"{markers[2]}和衣袖同时一动，{label}便从旧说法里滑出来，压住下一句真话。",
        f"{title}里的脚步回响先响了一下，{markers[3]}把退路照得更窄。",
        f"压到眼前的不是同一层解释，而是{markers[4]}、风声和停顿一起换出的{label}。",
    ]


def _scene_hook_fallbacks(worldpack: WorldPack, scene_function: str) -> List[str]:
    label = SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))
    return [
        f"{label}先停在这处细响里，下一次回来时要追问的是谁还敢把后半句藏住。",
        f"话先落下去了，可留下来的不是余波本身，而是下一步必须换法承担的后果。",
        f"等下一次再开口时，人物要面对的会是这一步{label}改变过的距离。",
        f"这句先压在这里，案角、门影和关系债已经把下一章的退路收窄。",
        f"{label}没有真的停住，它只从声音里退开，换到人物还没做完的动作里。",
    ]


def _enrich_worldpack_assets(worldpack: WorldPack) -> WorldPack:
    voice_payloads = {key: dict(value or {}) for key, value in (worldpack.voice_profiles or {}).items()}
    if voice_payloads:
        ordered_keys = sorted(voice_payloads, key=lambda key: (float(voice_payloads[key].get("directness", 0.5)), key))
        count = max(1, len(ordered_keys) - 1)
        for index, key in enumerate(ordered_keys):
            payload = voice_payloads[key]
            anchor = index / float(count) if count else 0.0
            target_directness = _clamp(0.18 + 0.74 * anchor)
            target_bluntness = _clamp(0.02 + 0.96 * anchor)
            target_restraint = _clamp(0.99 - 0.92 * anchor)
            target_rank_awareness = _clamp(0.86 - 0.5 * anchor)
            payload["directness"] = round((float(payload.get("directness", 0.5)) * 0.15) + (target_directness * 0.85), 3)
            payload["bluntness"] = round((float(payload.get("bluntness", 0.5)) * 0.1) + (target_bluntness * 0.9), 3)
            payload["restraint"] = round((float(payload.get("restraint", 0.5)) * 0.1) + (target_restraint * 0.9), 3)
            payload["social_rank_awareness"] = round((float(payload.get("social_rank_awareness", 0.5)) * 0.2) + (target_rank_awareness * 0.8), 3)
            payload["opening_style"] = _ensure_variants(payload.get("opening_style", []), _voice_line_fallbacks(key, "opening_style", payload), min_count=6)
            payload["pressure_style"] = _ensure_variants(payload.get("pressure_style", []), _voice_line_fallbacks(key, "pressure_style", payload), min_count=6)
            payload["pivot_style"] = _ensure_variants(payload.get("pivot_style", []), _voice_line_fallbacks(key, "pivot_style", payload), min_count=6)
            payload["aftermath_style"] = _ensure_variants(payload.get("aftermath_style", []), _voice_line_fallbacks(key, "aftermath_style", payload), min_count=6)
            payload["echo_style"] = _ensure_variants(payload.get("echo_style", []), _voice_line_fallbacks(key, "echo_style", payload), min_count=6)
            payload["signature_replies"] = _ensure_variants(payload.get("signature_replies", []), _voice_line_fallbacks(key, "signature_replies", payload), min_count=6)
        worldpack.voice_profiles = voice_payloads

    response_payloads = {key: dict(value or {}) for key, value in (worldpack.response_cadence_profiles or {}).items()}
    for key, payload in response_payloads.items():
        sharper = float(voice_payloads.get(key, {}).get("bluntness", 0.5)) >= 0.58
        reaction_lines = {slot: list(values) for slot, values in (payload.get("reaction_lines") or {}).items()}
        reply_lines = {slot: list(values) for slot, values in (payload.get("reply_lines") or {}).items()}
        for beat_key in ["entry", "pressure", "pivot", "aftermath", "echo"]:
            reaction_lines[beat_key] = _ensure_variants(reaction_lines.get(beat_key, []), _response_line_fallbacks("reaction_lines", beat_key, sharper=sharper), min_count=6)
            reply_lines[beat_key] = _ensure_variants(reply_lines.get(beat_key, []), _response_line_fallbacks("reply_lines", beat_key, sharper=sharper), min_count=6)
        payload["reaction_lines"] = reaction_lines
        payload["reply_lines"] = reply_lines
    worldpack.response_cadence_profiles = response_payloads

    pressure_styles = {key: dict(value or {}) for key, value in (worldpack.pressure_response_styles or {}).items()}
    if voice_payloads and set(pressure_styles.keys()) != set(voice_payloads.keys()):
        existing = list(pressure_styles.values()) or [{"style_id": "default"}]
        normalized_styles: Dict[str, Dict[str, Any]] = {}
        for index, key in enumerate(voice_payloads.keys()):
            base = dict(existing[min(index, len(existing) - 1)])
            base.setdefault("under_pressure", "先稳住气息，再把更难听的话说得更实。")
            base.setdefault("when_cornered", "不再绕路，直接把最重的那句摆到明处。")
            base.setdefault("when_softening", "语气先松下来，但边界不往回撤。")
            base.setdefault("when_deflecting", "把心里的真正顾虑挪开半寸，却不再装作没发生。")
            normalized_styles[key] = base
        pressure_styles = normalized_styles
    worldpack.pressure_response_styles = pressure_styles

    sensory_payload = dict((worldpack.sensory_grounding_policies or {}).get("default") or {})
    location_slots = {key: {slot: list(values) for slot, values in value.items()} for key, value in (sensory_payload.get("location_slots") or {}).items()}
    for location, slot_map in location_slots.items():
        for slot in ["atmosphere", "detail", "repeat_detail"]:
            slot_map[slot] = _ensure_variants(slot_map.get(slot, []), _sensory_fallbacks(location, slot), min_count=6)
    generic_slots = {key: list(values) for key, values in (sensory_payload.get("generic_slots") or {}).items()}
    for slot in ["atmosphere", "detail", "repeat_detail"]:
        generic_slots[slot] = _ensure_variants(generic_slots.get(slot, []), _sensory_fallbacks(worldpack.title, slot), min_count=6)
    if sensory_payload:
        sensory_payload["location_slots"] = location_slots
        sensory_payload["generic_slots"] = generic_slots
        worldpack.sensory_grounding_policies = {"default": sensory_payload, **{key: value for key, value in (worldpack.sensory_grounding_policies or {}).items() if key != "default"}}

    scene_payload = dict((worldpack.scene_realization_contracts or {}).get("default") or {})
    scene_openings = {key: list(values) for key, values in (scene_payload.get("scene_openings") or {}).items()}
    scene_hooks = {key: list(values) for key, values in (scene_payload.get("scene_hooks") or {}).items()}
    scene_functions = {normalize_scene_function(scene.scene_function) for scene in worldpack.scene_blueprints}
    for scene_function in sorted(scene_functions):
        scene_openings[scene_function] = _ensure_variants(scene_openings.get(scene_function, []), _scene_opening_fallbacks(worldpack, scene_function), min_count=5)
        scene_hooks[scene_function] = _ensure_variants(scene_hooks.get(scene_function, []), _scene_hook_fallbacks(worldpack, scene_function), min_count=5)
    if scene_payload or scene_functions:
        scene_payload["scene_openings"] = scene_openings
        scene_payload["scene_hooks"] = scene_hooks
        scene_payload.setdefault("contract_id", f"{worldpack.world_id}_scene_realization")
        worldpack.scene_realization_contracts = {"default": scene_payload, **{key: value for key, value in (worldpack.scene_realization_contracts or {}).items() if key != "default"}}
    return worldpack


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _enrich_runtime_event_atoms_with_scene_contracts(worldpack: WorldPack, event_atoms: List[EventAtom]) -> List[EventAtom]:
    blueprint_map = {scene.scene_id: scene for scene in worldpack.scene_blueprints}
    function_map: Dict[str, List[Any]] = {}
    for scene in worldpack.scene_blueprints:
        function_map.setdefault(normalize_scene_function(scene.scene_function), []).append(scene)

    for event in event_atoms:
        metadata = dict(event.metadata or {})
        scene_id = str(metadata.get("scene_blueprint_id") or "").strip()
        blueprint = blueprint_map.get(scene_id)
        if blueprint is None:
            matches = function_map.get(normalize_scene_function(event.scene_function), [])
            if len(matches) == 1:
                blueprint = matches[0]
        if blueprint is None:
            continue
        if blueprint.quality_contract:
            metadata["scene_quality_contract"] = dict(blueprint.quality_contract)
        metadata.setdefault("scene_blueprint_id", blueprint.scene_id)
        event.metadata = metadata
    return event_atoms


def _is_empty_style_pack(style_pack: WorldNarrativeStylePack) -> bool:
    payload = style_pack.to_dict()
    return not any(
        payload[key]
        for key in ("goal_labels", "tag_labels")
    ) and not any(
        payload[section]
        for section in ("dialogue", "emotion_actions", "sensory_grounding", "scene_realization")
        if payload[section] != WorldNarrativeStylePack().to_dict()[section]
    )


def _style_pack_from_assets(worldpack: WorldPack) -> WorldNarrativeStylePack:
    if not any(
        [
            worldpack.dialogue_realism_policy,
            worldpack.voice_profiles,
            worldpack.response_cadence_profiles,
            worldpack.pressure_response_styles,
            worldpack.emotion_action_policies,
            worldpack.sensory_grounding_policies,
            worldpack.scene_realization_contracts,
        ]
    ):
        return WorldNarrativeStylePack()
    return WorldNarrativeStylePack(
        style_pack_id=worldpack.narrative_style_pack.style_pack_id or "default",
        tonal_lexicon=list(worldpack.narrative_style_pack.tonal_lexicon),
        thematic_axis_labels=dict(worldpack.narrative_style_pack.thematic_axis_labels),
        hook_templates=list(worldpack.narrative_style_pack.hook_templates),
        goal_labels=dict(worldpack.narrative_style_pack.goal_labels),
        tag_labels=dict(worldpack.narrative_style_pack.tag_labels),
        dialogue=DialogueRealismPolicy.from_dict(
            {
                **dict(worldpack.dialogue_realism_policy or {}),
                "voice_profiles": worldpack.voice_profiles,
                "response_profiles": worldpack.response_cadence_profiles,
                "pressure_styles": worldpack.pressure_response_styles,
            }
        ),
        emotion_actions=EmotionActionPolicy.from_dict(
            next(iter(worldpack.emotion_action_policies.values()), {})
        ),
        sensory_grounding=SensoryGroundingPolicy.from_dict(
            next(iter(worldpack.sensory_grounding_policies.values()), {})
        ),
        scene_realization=SceneRealizationContract.from_dict(
            next(iter(worldpack.scene_realization_contracts.values()), {})
        ),
    )


def _default_style_pack(worldpack: WorldPack) -> WorldNarrativeStylePack:
    voice_profiles = {}
    response_profiles = {}
    action_map: Dict[str, Dict[str, List[str]]] = {}
    location_slots: Dict[str, Dict[str, List[str]]] = {}
    for character in worldpack.characters:
        cadence = "cool" if "冷" in "".join(character.speech_traits) else "measured"
        directness = 0.72 if any(token in "".join(character.speech_traits) for token in ["直", "逼", "冷"]) else 0.48
        restraint = 0.72 if any(token in "".join(character.speech_traits) for token in ["克制", "体面", "迟疑"]) else 0.52
        voice_profiles[character.character_id] = VoiceProfile(
            cadence=cadence,
            directness=directness,
            bluntness=0.62 if "逼问" in "".join(character.action_traits) else 0.4,
            restraint=restraint,
            social_rank_awareness=0.8 if character.role in {"matriarch", "heir", "lead"} else 0.45,
            opening_style=["我知道这句话一旦说出来，就再也没法装作没发生。"],
            pressure_style=["事到这里，再躲下去也只会让事情更难收。"],
            pivot_style=["真正难的不是选哪条路，而是承认自己早就偏了过去。"],
            aftermath_style=["话停在这里，可谁都知道，后面的代价还没真正追上来。"],
            echo_style=["等下一次再开口时，谁也不可能还是刚才那个人。"],
        )
        response_profiles[character.character_id] = ResponseCadenceProfile(
            reaction_tempo="measured",
            reaction_lines={
                "entry": ["他没有立刻接话，只是把那句意思在心里又过了一遍。"],
                "pressure": ["听到这里，手上的细小动作先停住了。"],
                "pivot": ["这才抬起眼来，像终于不打算再替谁留余地。"],
                "aftermath": ["到收声的时候，反而比刚才更轻，也更沉。"],
                "echo": ["没有再追问，可沉默已经替下一次相见留了一道裂口。"],
            },
            reply_lines={
                "entry": ["这句话既然已经出口，就别再往回收了。"],
                "pressure": ["你总得先替自己承认一次。"],
                "pivot": ["再退半步，也只是让伤口换个地方继续裂。"],
                "aftermath": ["这事不会就这样过去。"],
                "echo": ["下次再来时，就别只带着半句真话。"],
            },
        )

    for blueprint in worldpack.scene_blueprints:
        action_map[normalize_scene_function(blueprint.scene_function)] = {
            "entry": ["动作不算大，可场里的气已经先压紧了。"],
            "pressure": ["连最细小的停顿都带上了掂量，像谁先多动一下，谁就会先露底。"],
            "pivot": ["那一点极轻的改口和停顿，让场面从还能周旋，变成了不得不选边。"],
            "aftermath": ["说出口的话停了，可每个人散开时都比来时更沉。"],
            "echo": ["越到后面，越能听见那些没说尽的话慢慢回身索账。"],
            "repeat": ["动作并不大，可谁都知道事情已经换了味道。"],
        }

    for location in worldpack.world_bible.get("locations", []) or []:
        location_slots[location] = {
            "atmosphere": [f"{location}里并不安静，连空气都像在替谁压住一口没说完的话。"],
            "detail": [f"{location}里的光线和器物都像偏向了更难退开的那一边。"],
            "repeat_detail": [f"{location}里最轻的一点动静，反而把场面的情绪压得更清。"],
        }

    return WorldNarrativeStylePack(
        dialogue=DialogueRealismPolicy(
            turn_pattern=["speaker", "reaction", "reply"],
            minimum_exchanges=1,
            voice_profiles=voice_profiles,
            response_profiles=response_profiles,
            pressure_styles={},
        ),
        emotion_actions=EmotionActionPolicy(action_map=action_map),
        sensory_grounding=SensoryGroundingPolicy(
            location_slots=location_slots,
            generic_slots={
                "atmosphere": ["场里并不安静，连空气都像在替谁压住一口没说完的话。"],
                "detail": ["细小的声响和光线变化，把场里的情绪压得更清了一层。"],
                "repeat_detail": ["越到后面，越能听见那些没说尽的话在场里慢慢回身。"],
            },
        ),
        scene_realization=SceneRealizationContract(
            scene_openings={normalize_scene_function(scene.scene_function): [f"{scene.scene_id} 这一类场面最先压下来的，是还没人肯说破的那一点心事。"] for scene in worldpack.scene_blueprints},
            scene_hooks={normalize_scene_function(scene.scene_function): [f"等这场话停下来时，真正要追上来的往往是{scene.scene_id}留下来的余波。"] for scene in worldpack.scene_blueprints},
            scene_pressures={},
        ),
        goal_labels={},
        tag_labels={genre: genre.replace("_", " ") for genre in worldpack.manifest.genres},
    )


def runtime_bundle_from_worldpack_data(bundle: Dict[str, Any]) -> RuntimeBundle:
    payload = dict(bundle.get("worldpack", bundle))
    worldpack = WorldPack.from_dict(payload)
    worldpack = _enrich_worldpack_assets(worldpack)
    asset_style_pack = _style_pack_from_assets(worldpack)
    if not _is_empty_style_pack(asset_style_pack):
        worldpack.narrative_style_pack = asset_style_pack
    elif _is_empty_style_pack(worldpack.narrative_style_pack):
        worldpack.narrative_style_pack = _default_style_pack(worldpack)
    if worldpack.runtime_world_bible and worldpack.runtime_initial_state and worldpack.runtime_event_atoms:
        runtime_world = dict(worldpack.runtime_world_bible)
        runtime_world.setdefault("creator_controls", {})
        runtime_world["creator_controls"].setdefault("metadata", {})
        runtime_world["creator_controls"]["metadata"]["narrative_style_pack"] = worldpack.narrative_style_pack.to_dict()
        runtime_world["creator_controls"]["metadata"]["series_storyline_contract"] = dict(worldpack.series_storyline_contract or {})
        runtime_world["creator_controls"]["metadata"]["character_memory_profiles"] = {key: dict(value) for key, value in (worldpack.character_memory_profiles or {}).items()}
        runtime_world["creator_controls"]["metadata"]["steering_guardrails"] = dict(worldpack.steering_guardrails or {})
        world = WorldBible.from_dict(runtime_world)
        initial_state = NarrativeState.from_dict(worldpack.runtime_initial_state)
        event_atoms = [EventAtom.from_dict(item) for item in worldpack.runtime_event_atoms]
        event_atoms = _enrich_runtime_event_atoms_with_scene_contracts(worldpack, event_atoms)
        return RuntimeBundle(
            world_version_id=bundle.get("world_version_id", "%s@%s" % (worldpack.world_id, worldpack.version)),
            worldpack=worldpack,
            world_record=WorldRecord(world=world, event_atoms=event_atoms, metadata={"worldpack": worldpack.to_dict()}),
            initial_state=initial_state,
            event_atoms=event_atoms,
            player_inputs=list(worldpack.runtime_player_inputs or []),
        )
    return synthesize_runtime_bundle(worldpack)


def _character_state_from_profile(profile: Dict[str, Any]) -> CharacterState:
    return CharacterState.from_dict(
        {
            "name": profile["display_name"],
            "role": profile.get("role", "lead"),
            "public_goals": [profile["destiny_contract"].get("life_theme", "")]
            if profile["destiny_contract"].get("life_theme")
            else [],
            "hidden_goals": list(profile["vow_profile"].get("vows", [])),
            "constraints": [],
            "beliefs_true": [],
            "beliefs_false": [],
            "emotions": {"suspicion": 0.3, "hope": 0.3},
            "trust": {},
            "poisons": profile["poison_vector"],
            "vows": profile["vow_profile"],
            "wound": profile["wound_profile"],
            "awakening": profile["awakening_profile"],
            "destiny": {
                "life_theme": profile["destiny_contract"].get("life_theme", ""),
                "inescapable_nodes": list(profile["destiny_contract"].get("inescapable_nodes", [])),
                "fated_relations": list(profile["destiny_contract"].get("fated_relations", [])),
                "forbidden_escape": [profile["destiny_contract"].get("forbidden_escape", "")] if profile["destiny_contract"].get("forbidden_escape") else [],
                "endgame_shapes": list(profile["destiny_contract"].get("endgame_shapes", [])),
            },
            "debts": [],
            "karmic_seeds": [],
        }
    )


def _synthesize_event_from_blueprint(
    worldpack: WorldPack,
    blueprint: SceneBlueprint,
    beat_index: int,
    actor_ids: List[str],
) -> Dict[str, Any]:
    beat_text = blueprint.beats_template[beat_index]
    event_id = "%s__%s__%s" % (worldpack.world_id, blueprint.scene_id, beat_index)
    seed_id = "%s__seed" % event_id
    is_last = beat_index == len(blueprint.beats_template) - 1
    world_locations = list(worldpack.world_bible.get("locations", []))
    location = world_locations[beat_index % len(world_locations)] if world_locations else "%s·%s" % (worldpack.title, blueprint.scene_id)
    promise_id = "%s__promise" % blueprint.scene_id
    return {
        "event_id": event_id,
        "title": "%s · %s" % (blueprint.scene_id, beat_text),
        "summary": "%s 中，%s 让人物进一步卷入 %s。" % (worldpack.title, beat_text, blueprint.scene_function),
        "location": location,
        "actors": actor_ids,
        "scene_function": normalize_scene_function(blueprint.scene_function),
        "tags": list(dict.fromkeys((worldpack.manifest.genres[:2] + blueprint.vow_tests[:1] + blueprint.wound_triggers[:1]) or ["fate", "choice"])),
        "preconditions_all": [] if beat_index == 0 else ["%s__step_%s" % (blueprint.scene_id, beat_index - 1)],
        "forbidden_if_any": [],
        "world_fact_deltas_add": ["%s__step_%s" % (blueprint.scene_id, beat_index)],
        "world_fact_deltas_remove": [],
        "belief_updates": {},
        "trust_deltas": [],
        "emotion_deltas": [],
        "promises_open": [
            {
                "promise_id": promise_id,
                "description": "%s 迟早要被说清楚。" % beat_text,
                "opened_at_turn": 0,
                "due_by_turn": 3,
                "holders": list(dict.fromkeys(actor_ids[:2] or actor_ids[:1])),
                "fulfillment_modes": ["truth", "choice", "confession"],
                "status": "open",
                "stakes": "medium",
                "tags": [normalize_scene_function(blueprint.scene_function), "story_thread"],
            }
        ] if beat_index == 0 and not is_last else [],
        "promises_close": [],
        "tension_delta": 0.08 if not is_last else 0.04,
        "theme_impacts": {genre: 0.06 for genre in worldpack.manifest.genres[:2]},
        "agency_affordances": list(dict.fromkeys(blueprint.vow_tests[:1] + blueprint.wound_triggers[:1] + ["selfhood"])),
        "rating_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
        "temptation_vector": {
            "greed": 0.04 if blueprint.scene_function == "temptation" else 0.0,
            "anger": 0.06 if blueprint.scene_function in {"truth_trial", "humiliation"} else 0.0,
            "delusion": 0.08 if blueprint.scene_function == "misrecognition" else 0.02,
            "pride": 0.06 if blueprint.scene_function in {"mask_crack", "false_peace"} else 0.03,
            "doubt": 0.08 if blueprint.scene_function in {"temptation", "misrecognition"} else 0.03,
        },
        "vow_tests": list(blueprint.vow_tests),
        "wound_triggers": list(blueprint.wound_triggers),
        "debt_deltas": [
            {
                "source": actor_ids[0],
                "target": actor_ids[1] if len(actor_ids) > 1 else actor_ids[0],
                "debt_type": "scene_aftertaste",
                "magnitude": 0.12,
                "obligation": 0.05,
                "note": beat_text,
            }
        ],
        "karmic_seed_creations": [
            {
                "seed_id": seed_id,
                "source_event_id": event_id,
                "actor": actor_ids[0],
                "target": actor_ids[1] if len(actor_ids) > 1 else None,
                "seed_type": blueprint.scene_function,
                "charge": 0.36,
                "tags": list(dict.fromkeys(blueprint.vow_tests[:1] + blueprint.wound_triggers[:1] + worldpack.manifest.genres[:2])),
                "created_at_turn": 0,
                "ripening_conditions": [normalize_scene_function(blueprint.scene_function), "truth_trial", "karma_ripening"],
                "earliest_turn": 2,
                "latest_turn": 8,
                "status": "dormant",
                "transformable_by": ["mutual_truth", "vow_payment", "public_witness"],
            }
        ],
        "karmic_seed_resolutions": [],
        "awakening_affordances": ["mutual_truth"] if blueprint.scene_function in {"truth_trial", "confession_window"} else [],
        "concealment_level": 0.55 if blueprint.scene_function in {"temptation", "misrecognition", "false_peace"} else 0.12,
        "consequence_delay_hint": 2,
        "metadata": {
            "scene_blueprint_id": blueprint.scene_id,
            "generated_from_worldpack": True,
            **({"continuation_blueprints": [dict(item) for item in blueprint.continuation_blueprints]} if blueprint.continuation_blueprints else {}),
            **({"terminal": True, "endgame_shape": "awakening", "required_fate_pressure": 0.4, "required_inescapable_nodes": list(profile for profile in blueprint.vow_tests[:1]), "ending_gate": blueprint.ending_gate or {"min_turn": 6, "required_scene_functions": [normalize_scene_function(blueprint.scene_function)], "required_closed_promises": [], "required_tension_min": 0.35}} if is_last and blueprint.ending_gate else {}),
        },
    }


def synthesize_runtime_bundle(worldpack: WorldPack) -> RuntimeBundle:
    worldpack = _enrich_worldpack_assets(worldpack)
    asset_style_pack = _style_pack_from_assets(worldpack)
    if not _is_empty_style_pack(asset_style_pack):
        worldpack.narrative_style_pack = asset_style_pack
    elif _is_empty_style_pack(worldpack.narrative_style_pack):
        worldpack.narrative_style_pack = _default_style_pack(worldpack)
    character_ids = [profile.character_id for profile in worldpack.characters]
    characters = {profile.character_id: _character_state_from_profile(profile.to_dict()) for profile in worldpack.characters}
    for source_id in characters:
        characters[source_id].trust = {
            target_id: 0.55
            for target_id in character_ids
            if target_id != source_id
        }
    world = WorldBible.from_dict(
        {
            "world_id": worldpack.world_id,
            "title": worldpack.title,
            "source_type": "worldpack",
            "themes": list(dict.fromkeys(worldpack.manifest.genres + ["fate", "selfhood"]))[:5],
            "canon_anchors": [worldpack.world_bible.get("premise", worldpack.title)] + list(worldpack.world_bible.get("canon_rules", [])),
            "forbidden_moves": list(worldpack.world_bible.get("forbidden_moves", [])),
            "characters": character_ids,
            "locations": list(worldpack.world_bible.get("locations", [])) or [worldpack.title, "长廊", "回廊", "门前"],
            "creator_controls": {
                "merge_policy": "allow_dag_with_scars",
                "darkness_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
                "theme_targets": list(worldpack.manifest.genres[:3]),
                "payoff_style": "beta_worldpack",
                "metadata": {
                    "narrative_style_pack": worldpack.narrative_style_pack.to_dict(),
                    "series_storyline_contract": dict(worldpack.series_storyline_contract or {}),
                    "character_memory_profiles": {key: dict(value) for key, value in (worldpack.character_memory_profiles or {}).items()},
                    "steering_guardrails": dict(worldpack.steering_guardrails or {}),
                },
            },
        }
    )
    relationship_graph = []
    if len(character_ids) >= 2:
        for source_id in character_ids:
            for target_id in character_ids:
                if source_id == target_id:
                    continue
                relationship_graph.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "attachment": 0.28,
                        "resentment": 0.08,
                        "shame": 0.05,
                        "obligation": 0.12,
                        "projection": 0.15,
                        "possession": 0.06,
                        "gratitude": 0.12,
                        "fear": 0.2,
                        "debts": [],
                        "notes": ["synthetic_worldpack_edge"],
                    }
                )
    initial_state = NarrativeState.from_dict(
        {
            "state_id": "%s__state_0001" % worldpack.world_id,
            "world_id": worldpack.world_id,
            "turn_index": 0,
            "story_phase": "setup",
            "chapter_index": 0,
            "min_end_turn": 6,
            "fate_pressure": 0.18,
            "karmic_weather": {"suspicion": 0.18, "grief": 0.06, "temptation": 0.22, "shame": 0.11, "mercy": 0.09},
            "unresolved_debts": [],
            "world_facts": [worldpack.world_bible.get("premise", worldpack.title)],
            "timeline": [],
            "characters": {key: value.to_dict() for key, value in characters.items()},
            "relationship_graph": relationship_graph,
            "open_promises": [],
            "tension": 0.34,
            "themes": {genre: 0.45 for genre in worldpack.manifest.genres[:4]},
            "player_intent": {"curiosity": 0.55, "selfhood": 0.55, "honesty": 0.4},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13" if "13" in worldpack.manifest.risk_rating else "PG",
            "metadata": {"source_type": "synthesized_worldpack"},
        }
    )
    event_atoms: List[EventAtom] = []
    for blueprint in worldpack.scene_blueprints:
        actor_ids = [
            (
                role
                if role in character_ids
                else next(
                    (
                        profile.character_id
                        for profile in worldpack.characters
                        if profile.role == role
                    ),
                    character_ids[0],
                )
            )
            for role in blueprint.required_roles
        ] or character_ids[:1]
        for index in range(len(blueprint.beats_template)):
            event_atoms.append(EventAtom.from_dict(_synthesize_event_from_blueprint(worldpack, blueprint, index, actor_ids)))
    event_atoms = _enrich_runtime_event_atoms_with_scene_contracts(worldpack, event_atoms)
    return RuntimeBundle(
        world_version_id="%s@%s" % (worldpack.world_id, worldpack.version),
        worldpack=worldpack,
        world_record=WorldRecord(world=world, event_atoms=event_atoms, metadata={"synthesized": True}),
        initial_state=initial_state,
        event_atoms=event_atoms,
        player_inputs=[{"raw_input": "先看看这条命会把我带去哪里。", "intent_vector": {"curiosity": 0.7, "selfhood": 0.5}}],
    )


class FileSystemWorldRegistry:
    def __init__(self, worldpack_dir: Optional[Path] = None) -> None:
        self.worldpack_dir = worldpack_dir or WORLDPACK_DIR

    def _world_card_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(payload.get("metadata", {}))
        catalog_role = str(metadata.get("catalog_role", "published") or "published")
        benchmark_enabled = bool(metadata.get("benchmark_enabled", catalog_role == "published"))
        return {
            "world_id": payload["world_id"],
            "title": payload["title"],
            "world_version_id": "%s@%s" % (payload["world_id"], payload.get("version", "1.0.0")),
            "status": "published",
            "manifest": payload.get("manifest", {}),
            "metadata": metadata,
            "catalog_role": catalog_role,
            "benchmark_enabled": benchmark_enabled,
            "worldpack": payload,
        }

    def list_worldpacks(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for path in sorted(self.worldpack_dir.glob("*.json")):
            if not path.is_file():
                continue
            payload = _load_json(path)
            results.append(self._world_card_from_payload(payload))
        return results

    def list_benchmark_worldpacks(self) -> List[Dict[str, Any]]:
        return [
            item
            for item in self.list_worldpacks()
            if item.get("catalog_role") == "published" and bool(item.get("benchmark_enabled", True))
        ]

    def validate_worldpack(self, worldpack: Dict[str, Any]) -> Dict[str, Any]:
        return validate_worldpack_payload(worldpack)

    def get_published_world(self, world_id: str) -> Dict[str, Any]:
        for path in self.worldpack_dir.glob("*.json"):
            payload = _load_json(path)
            if payload.get("world_id") == world_id:
                return self._world_card_from_payload(payload)
        raise KeyError("unknown_world:%s" % world_id)

    def get_world_version(self, world_version_id: str) -> Dict[str, Any]:
        world_id = world_version_id.split("@", 1)[0]
        published = self.get_published_world(world_id)
        return {
            "world_version_id": world_version_id,
            "world_id": published["world_id"],
            "status": "published",
            "worldpack": published["worldpack"],
        }

    def get_runtime_bundle(self, world_version_id: str) -> RuntimeBundle:
        return runtime_bundle_from_worldpack_data(self.get_world_version(world_version_id))
