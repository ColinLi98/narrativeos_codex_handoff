from __future__ import annotations

from ..models import NarrativeState, SceneBeat, WorldBible
from .voice import response_profile_for_actor, voice_profile_for_actor


def _actor_name(state: NarrativeState, actor_id: str) -> str:
    character = state.characters.get(actor_id)
    return character.name if character else actor_id.replace("_", " ")


def _line_from_profile(lines: list[str], fallback: str | list[str], *, index: int = 0) -> str:
    if lines:
        return lines[index % len(lines)]
    if isinstance(fallback, list):
        return fallback[index % len(fallback)] if fallback else ""
    return fallback


def _attach_reaction(counterpart: str, reaction: str) -> str:
    if reaction.startswith(("他", "她", counterpart)):
        return reaction
    return f"{counterpart}{reaction}"


def _dialogue_seed(state_before: NarrativeState, beat: SceneBeat, *, extra: int = 0) -> int:
    event = beat.event
    event_id = str(getattr(event, "event_id", "") or "")
    scene_function = str(getattr(event, "scene_function", "") or "")
    dramatic_job = str(getattr(beat, "dramatic_job", "") or "")
    actor_seed = ":".join(str(actor_id) for actor_id in getattr(event, "actors", []) or [])
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    beat_index = int(getattr(beat, "beat_index", 0) or 0)
    raw_seed = f"{event_id}:{scene_function}:{dramatic_job}:{actor_seed}"
    return sum(ord(char) for char in raw_seed) + chapter_index * 41 + beat_index * 17 + int(extra)


def _frame_variant(frames: dict[str, list[str]], beat_key: str, *, index: int) -> str:
    variants = frames.get(beat_key) or frames.get("pressure") or []
    return variants[index % len(variants)] if variants else "{speaker}低声道：“{line}”"


def _scene_label(scene_function: str) -> str:
    labels = {
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
    return labels.get(scene_function, scene_function.replace("_", " "))


def _chapter_line_variant(line: str, state_before: NarrativeState, beat: SceneBeat, *, role: str, index: int) -> str:
    scene_label = _scene_label(str(getattr(beat.event, "scene_function", "") or ""))
    location = str(getattr(beat.event, "location", "") or "这里")
    marker_pool = ["案角", "门影", "杯沿", "窗纸", "衣袖", "灯芯", "阶前风", "纸页声"]
    marker = marker_pool[index % len(marker_pool)]
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    if chapter_index < 12:
        return line
    if "半句" in line or "说完整" in line:
        variants = [
            f"把后半句也放到{marker}旁，别再留给沉默替你收。",
            f"这一步{scene_label}已经露出来了，别只把最轻的那层递给我。",
            f"既然走到{location}了，就把真正会疼的那句也说出来。",
            f"别让{marker}都替你认了，你自己却还退在半步外。",
            f"我听的不是开头，是你肯不肯把后果一起交出来。",
        ]
        return variants[index % len(variants)]
    if "局势" in line or "认下" in line or "算在我头上" in line or "不再推" in line:
        variants = [
            f"这回我先接住{marker}边那层后果，别的难看也不往外推。",
            f"{scene_label}已经压到眼前，我就从这一步开始自己承担。",
            f"我把这句放在{location}里，后面的账也由我亲手补上。",
            f"该疼的地方我不躲了，先从{marker}旁这一句算起。",
            f"这一步我不再借别人收场，剩下的也该我自己走完。",
        ]
        return variants[index % len(variants)]
    if "案角纸页都响了" in line or "不往回收" in line:
        variants = [
            f"{marker}都已经响了，我就不再把这句话退回去。",
            f"风声把{scene_label}推到这里，我也该把话落实。",
            f"既然{location}都听见了，我不会再把它装成玩笑。",
            f"这一下已经照到{marker}上，我就不往暗处藏了。",
        ]
        return variants[index % len(variants)]
    return line


def _repeated_dialogue_closer(speaker: str, counterpart: str, *, index: int) -> str:
    variants = [
        "两人都知道，话已经绕不过刚才留下的那层意思了。",
        f"{speaker}没有再把目光移开，{counterpart}也没有替这句真话找台阶。",
        f"{counterpart}把沉默压住时，{speaker}终于明白后半句已经不能再拖到下一次。",
        f"那一下停顿落在两人之间，比任何圆场都更像一次逼近。",
        f"{speaker}和{counterpart}都听见了同一层余波，只是谁也没再把它说轻。",
        f"{counterpart}先收住呼吸，{speaker}便知道这一次不能再用上一句回答接过去。",
        f"桌沿那点轻响替两人停了半拍，随后谁都没有把后果推回沉默里。",
        f"{speaker}把半步退路收回来时，{counterpart}眼里的迟疑也换了方向。",
        f"这一次留在两人之间的不是圆场，而是下一句必须换法说出的压力。",
    ]
    return variants[index % len(variants)]


def compose_late_longform_compact_exchange(
    world: WorldBible,
    state_before: NarrativeState,
    beat: SceneBeat,
    *,
    repeated: bool,
    variant_offset: int = 0,
) -> str:
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        seed = _dialogue_seed(state_before, beat, extra=variant_offset)
        lines = [
            "这回我不再绕开，先把后果接住。",
            "我换一种做法，不让旧话再拖长。",
            "这一步我往前走，剩下的也照实认。",
            "别让沉默替我收场，我自己开口。",
        ]
        actions = [
            f"{actor_name}按住案角，停了一息才低声道：“{lines[seed % len(lines)]}”",
            f"{actor_name}把袖口收紧，抬眼道：“{lines[(seed + 1) % len(lines)]}”",
            f"{actor_name}往前半步，声音压稳：“{lines[(seed + 2) % len(lines)]}”",
        ]
        return actions[seed % len(actions)]

    speaker_id = beat.event.actors[0]
    counterpart_id = beat.event.actors[1]
    speaker = _actor_name(state_before, speaker_id)
    counterpart = _actor_name(state_before, counterpart_id)
    speaker_voice = voice_profile_for_actor(world, state_before, speaker_id)
    counterpart_response = response_profile_for_actor(world, state_before, counterpart_id)
    beat_key = beat.dramatic_job
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    seed = _dialogue_seed(state_before, beat, extra=variant_offset + chapter_index * 3)
    marker_pool = ["案角", "门影", "杯沿", "窗纸", "衣袖", "灯芯", "阶前风", "纸页声", "门框", "桌沿"]
    marker = marker_pool[seed % len(marker_pool)]
    location = str(getattr(beat.event, "location", "") or "这里")
    scene_label = _scene_label(str(getattr(beat.event, "scene_function", "") or ""))
    speaker_line = _line_from_profile(
        getattr(speaker_voice, {
            "entry": "opening_style",
            "pressure": "pressure_style",
            "pivot": "pivot_style",
            "aftermath": "aftermath_style",
            "echo": "echo_style",
        }.get(beat_key, "pressure_style")),
        beat.event.title,
        index=seed + 3,
    )
    reply = _line_from_profile(
        counterpart_response.reply_lines.get(beat_key, []),
        "那就把后果说实。",
        index=seed + 11,
    )
    followup = _line_from_profile(
        speaker_voice.signature_replies,
        "我现在往前走，不再把这句留给沉默。",
        index=seed + 19,
    )
    speaker_line = _chapter_line_variant(speaker_line, state_before, beat, role="speaker", index=seed + 5)
    reply = _chapter_line_variant(reply, state_before, beat, role="reply", index=seed + 7)
    followup = _chapter_line_variant(followup, state_before, beat, role="followup", index=seed + 13)
    counter_closers = [
        f"那就别退，先从{marker}旁这一句开始。",
        f"我听见了，也会看你接下来怎么做。",
        f"{scene_label}已经在眼前，你别再把它说轻。",
        f"{location}都听见了，这次别只留下半步。",
        f"把这句放稳，后面的账才有地方落。",
    ]
    action_frames = [
        f"{speaker}按住{marker}，抬眼看向{counterpart}：“{speaker_line}”",
        f"{speaker}把手从{marker}边收回，往前半步：“{speaker_line}”",
        f"{speaker}停在{location}的灯影里，声音压低：“{speaker_line}”",
        f"{speaker}握紧袖口，没有退开：“{speaker_line}”",
    ]
    response_frames = [
        f"{counterpart}没有替他圆场：“{reply}”",
        f"{counterpart}把视线压回去：“{reply}”",
        f"{counterpart}看着{marker}，回得很短：“{reply}”",
        f"{counterpart}往前一步，声音更稳：“{reply}”",
    ]
    follow_frames = [
        f"{speaker}点了一下头：“{followup}”",
        f"{speaker}把呼吸压稳：“{followup}”",
        f"{speaker}没有再借沉默避开：“{followup}”",
        f"{speaker}把掌心贴上桌沿：“{followup}”",
    ]
    close_frames = [
        f"{counterpart}停了半息：“{counter_closers[(seed + 1) % len(counter_closers)]}”",
        f"{counterpart}收住脚步：“{counter_closers[(seed + 2) % len(counter_closers)]}”",
        f"{counterpart}把路让出半寸：“{counter_closers[(seed + 3) % len(counter_closers)]}”",
        f"{counterpart}看着他：“{counter_closers[(seed + 4) % len(counter_closers)]}”",
    ]
    frame_window = chapter_index // 20 + int(variant_offset)
    parts = [
        action_frames[(seed + frame_window) % len(action_frames)],
        response_frames[(seed // 3 + frame_window) % len(response_frames)],
        follow_frames[(seed // 5 + frame_window) % len(follow_frames)],
        close_frames[(seed // 7 + frame_window) % len(close_frames)],
    ]
    if repeated:
        parts.append(_repeated_dialogue_closer(speaker, counterpart, index=seed + 5))
    return " ".join(parts)


def compose_dialogue(world: WorldBible, state_before: NarrativeState, beat: SceneBeat, *, repeated: bool) -> str:
    seed = _dialogue_seed(state_before, beat)
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        reflections = (
            [
                "我先把这句话留在这里，等下一次开口时，再看看它会不会逼得人没有退路。",
                "这一回我先把话落稳，后面的路再难，也不能只靠退让走完。",
                "如果这一步已经照到眼前，我就不能再把它塞回心里。",
            ]
            if not repeated
            else [
                "这句心里话已经绕不回去了，真要再装作没发生，反而更显得心虚。",
                "不能再照上一回的沉默走了，换一种说法，才算真的往前。",
                "我先把这一步认清，后面的代价不能总留给下一次。",
            ]
        )
        reflection = reflections[seed % len(reflections)]
        action_frames = [
            f"{actor_name}没有立刻把心思遮回去，只让那口气在胸口多压了一瞬。",
            f"{actor_name}把指尖从衣袖里收回来，像先按住了一个快要出口的退路。",
            f"{actor_name}偏头看向灯影外那一点空处，呼吸比方才慢了半拍。",
        ]
        return " ".join(
            [
                action_frames[(seed // 5) % len(action_frames)],
                f"{actor_name}低声道：“{reflection}”",
            ]
        )

    speaker_id = beat.event.actors[0]
    counterpart_id = beat.event.actors[1]
    if speaker_id == counterpart_id:
        actor_name = _actor_name(state_before, speaker_id)
        self_lines = [
            "真正难的不是看见这一层心思，而是看见以后还得继续往前走。",
            "这一步既然已经露出来，就不能再靠同一个借口绕回去。",
            "我要换一种走法，否则说再多也只是把旧账拖长。",
        ]
        action_lines = [
            f"{actor_name}抬眼看向空下来的那一处，像是在替自己把那句真话一点点逼出来。",
            f"{actor_name}把手按在桌沿上，听见那点细响以后才慢慢开口。",
            f"{actor_name}没有往后退，只让目光从灯影边缘重新落回眼前。",
        ]
        return " ".join(
            [
                action_lines[(seed // 3) % len(action_lines)],
                f"{actor_name}低声道：“{self_lines[seed % len(self_lines)]}”",
            ]
        )
    speaker = _actor_name(state_before, speaker_id)
    counterpart = _actor_name(state_before, counterpart_id)

    speaker_voice = voice_profile_for_actor(world, state_before, speaker_id)
    counterpart_response = response_profile_for_actor(world, state_before, counterpart_id)

    beat_key = beat.dramatic_job
    beat_index = getattr(beat, "beat_index", 0)
    event_seed = sum(ord(char) for char in str(getattr(beat.event, "event_id", "") or ""))
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    variant_index = _dialogue_seed(state_before, beat, extra=event_seed + beat_index)
    speaker_line = _line_from_profile(
        getattr(speaker_voice, {
            "entry": "opening_style",
            "pressure": "pressure_style",
            "pivot": "pivot_style",
            "aftermath": "aftermath_style",
            "echo": "echo_style",
        }.get(beat_key, "pressure_style")),
        beat.event.title,
        index=variant_index + 3,
    )
    reaction = _line_from_profile(
        counterpart_response.reaction_lines.get(beat_key, []),
        "他没有立刻回话，只让沉默先压了一层上来。",
        index=variant_index + 11,
    )
    reply = _line_from_profile(
        counterpart_response.reply_lines.get(beat_key, []),
        "你总得先把心里的话说完整。",
        index=variant_index + 19,
    )
    followup = _line_from_profile(
        speaker_voice.signature_replies,
        {
            "entry": [
                "我先把这句话放在这里，剩下的路我自己认。",
                "这句既然已经落下，我就不想再把它装回沉默里。",
                "先把这层意思摆在明处，后面的难看我自己接。",
            ],
            "pressure": [
                "真要走到这里，我也不想再把心里话硬压回去。",
                "逼到这一刻，我宁可把难听的话说实，也不想再退半步。",
                "这次我不想再借沉默给自己留退路了。",
            ],
            "pivot": [
                "既然已经到了这一步，我不打算再退回原来的样子。",
                "真话既然已经碰到了嘴边，我就不想再让它缩回去。",
                "事情拧到这里，我再装稳，反而更像认输。",
            ],
            "aftermath": [
                "这句先记在这里，后面的代价我会自己来接。",
                "话既然落了地，我就不打算再让别人替我收残局。",
                "这一回我先认，余下那点难堪我自己扛。",
            ],
            "echo": [
                "等下一次再开口时，我会把更完整的话带回来。",
                "下一次再见时，我不会只剩半句真话。",
                "这层意思先留在这里，后面我会把它说得更完整。",
            ],
        }.get(beat_key, ["这条路到了这里，已经不能再装作没发生。"]),
        index=variant_index + 29,
    )
    speaker_line = _chapter_line_variant(
        speaker_line,
        state_before,
        beat,
        role="speaker",
        index=variant_index + chapter_index // 13,
    )
    reply = _chapter_line_variant(
        reply,
        state_before,
        beat,
        role="reply",
        index=variant_index + chapter_index // 17 + 5,
    )
    followup = _chapter_line_variant(
        followup,
        state_before,
        beat,
        role="followup",
        index=variant_index + chapter_index // 19 + 11,
    )

    opener_frames = {
        "entry": [
            "{speaker}看了{counterpart}一眼，低声道：“{line}”",
            "{speaker}先把目光落到{counterpart}袖边，才开口：“{line}”",
            "{speaker}停在门影旁，没有寒暄，只把话递过去：“{line}”",
            "{speaker}把指节从案边收回，声音压稳：“{line}”",
        ],
        "pressure": [
            "{speaker}把声音压得更低，对{counterpart}说道：“{line}”",
            "{speaker}没有退开，顺着那点停顿逼近一句：“{line}”",
            "{speaker}盯住{counterpart}的眼神，把话落得很慢：“{line}”",
            "{speaker}先按住呼吸，再把最难听的一句送出来：“{line}”",
        ],
        "pivot": [
            "{speaker}终于抬眼迎上{counterpart}的视线：“{line}”",
            "{speaker}往前半步，像把岔口也一起推到明处：“{line}”",
            "{speaker}没有再接旧话，直接换了方向：“{line}”",
            "{speaker}把原本要咽回去的那句改成了选择：“{line}”",
        ],
        "aftermath": [
            "{speaker}隔了半息，才又对{counterpart}开口：“{line}”",
            "{speaker}听见余声落下，才把后果接上：“{line}”",
            "{speaker}没有替自己收场，只低声补了一句：“{line}”",
            "{speaker}把气息压稳以后，终于认下这句：“{line}”",
        ],
        "echo": [
            "临散前，{speaker}还是朝{counterpart}补了一句：“{line}”",
            "{speaker}走出半步又停住，回身道：“{line}”",
            "{speaker}没有让余音自己散掉，反而重新开口：“{line}”",
            "{speaker}在门边停住，把回声换成一句实话：“{line}”",
        ],
    }
    opener = _frame_variant(opener_frames, beat_key, index=variant_index + chapter_index // 20).format(
        speaker=speaker,
        counterpart=counterpart,
        line=speaker_line,
    )
    response = _attach_reaction(counterpart, reaction)
    close_frames = {
        "entry": [
            "{counterpart}最后只回了一句：“{line}”",
            "{counterpart}没有马上接近，只把话压在原处：“{line}”",
            "{counterpart}看了看门外，才把回答落下来：“{line}”",
            "{counterpart}把沉默收紧，回得很短：“{line}”",
        ],
        "pressure": [
            "{counterpart}把话压得很低，只往前送了一句：“{line}”",
            "{counterpart}没有让步，反而把后果点明：“{line}”",
            "{counterpart}顺着那点停顿反问回来：“{line}”",
            "{counterpart}把声音放得更稳：“{line}”",
        ],
        "pivot": [
            "{counterpart}这才把最重的那句回了出来：“{line}”",
            "{counterpart}看清了岔口，回答也不再绕弯：“{line}”",
            "{counterpart}没有接旧路，只把选择推回来：“{line}”",
            "{counterpart}把视线停住，终于回道：“{line}”",
        ],
        "aftermath": [
            "{counterpart}沉了沉气，仍旧把话落得很实：“{line}”",
            "{counterpart}没有替余波找台阶，只说：“{line}”",
            "{counterpart}隔着半息静气，把残局重新推回眼前：“{line}”",
            "{counterpart}终于抬眼，回答里没有半点圆场：“{line}”",
        ],
        "echo": [
            "{counterpart}临收声前，只留下了一句：“{line}”",
            "{counterpart}没有让回声空过去，反而接了一句：“{line}”",
            "{counterpart}在门边停了停，把余音压成回答：“{line}”",
            "{counterpart}最后看了{speaker}一眼：“{line}”",
        ],
    }
    follow_frames = {
        "entry": [
            "{speaker}指尖缓了一缓，又补了一句：“{line}”",
            "{speaker}没有把这句收回去，反而往前添了一层：“{line}”",
            "{speaker}听完那句回答，才把退路也放下：“{line}”",
            "{speaker}让门边那点静停了一瞬，继续道：“{line}”",
        ],
        "pressure": [
            "{speaker}像是终于不想再退，顺势把后半句也压了出来：“{line}”",
            "{speaker}没有借沉默避开，只把话换得更实：“{line}”",
            "{speaker}把掌心从桌沿松开，接得很快：“{line}”",
            "{speaker}迎着那句反问，终于把后半步也走出来：“{line}”",
        ],
        "pivot": [
            "{speaker}没有就此收住，反而把更难听的一句也补到了明处：“{line}”",
            "{speaker}顺着转向往前压了一句：“{line}”",
            "{speaker}像是终于认清岔口，补得很轻：“{line}”",
            "{speaker}没有回到旧说法，只换了一句更硬的：“{line}”",
        ],
        "aftermath": [
            "{speaker}临到收声前仍没退，只轻轻接了一句：“{line}”",
            "{speaker}没有替自己圆回来，只把代价认得更清：“{line}”",
            "{speaker}把余波接在掌心里，慢慢道：“{line}”",
            "{speaker}看着{counterpart}，终于把残局往自己身上收：“{line}”",
        ],
        "echo": [
            "{speaker}走出半步又停住，回身补了一句：“{line}”",
            "{speaker}没有让回声空着，低声道：“{line}”",
            "{speaker}在门外那点风里停了停，又说：“{line}”",
            "{speaker}把最后一点余音接回来：“{line}”",
        ],
    }
    close = _frame_variant(close_frames, beat_key, index=variant_index // 3 + chapter_index // 25).format(
        speaker=speaker,
        counterpart=counterpart,
        line=reply,
    )
    follow = _frame_variant(follow_frames, beat_key, index=variant_index // 5 + chapter_index // 30).format(
        speaker=speaker,
        counterpart=counterpart,
        line=followup,
    )
    if chapter_index >= 20:
        return compose_late_longform_compact_exchange(
            world,
            state_before,
            beat,
            repeated=repeated,
            variant_offset=variant_index,
        )
    if repeated:
        return " ".join([opener, response, close, follow, _repeated_dialogue_closer(speaker, counterpart, index=variant_index)])
    return " ".join([opener, response, close, follow])
