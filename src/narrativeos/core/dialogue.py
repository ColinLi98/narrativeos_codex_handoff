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


def compose_dialogue(world: WorldBible, state_before: NarrativeState, beat: SceneBeat, *, repeated: bool) -> str:
    if len(beat.event.actors) < 2:
        actor_name = _actor_name(state_before, beat.event.actors[0]) if beat.event.actors else "那人"
        reflection = (
            "我先把这句话留在这里，等下一次开口时，再看看它会不会逼得人没有退路。"
            if not repeated
            else "这句心里话已经绕不回去了，真要再装作没发生，反而更显得心虚。"
        )
        return " ".join(
            [
                f"{actor_name}没有立刻把心思遮回去，只让那口气在胸口多压了一瞬。",
                f"{actor_name}低声道：“{reflection}”",
            ]
        )

    speaker_id = beat.event.actors[0]
    counterpart_id = beat.event.actors[1]
    if speaker_id == counterpart_id:
        actor_name = _actor_name(state_before, speaker_id)
        return " ".join(
            [
                f"{actor_name}抬眼看向空下来的那一处，像是在替自己把那句真话一点点逼出来。",
                f"{actor_name}低声道：“真正难的不是看见这一层心思，而是看见以后还得继续往前走。”",
            ]
        )
    speaker = _actor_name(state_before, speaker_id)
    counterpart = _actor_name(state_before, counterpart_id)

    speaker_voice = voice_profile_for_actor(world, state_before, speaker_id)
    counterpart_response = response_profile_for_actor(world, state_before, counterpart_id)

    beat_key = beat.dramatic_job
    beat_index = getattr(beat, "beat_index", 0)
    variant_index = beat_index + int(getattr(state_before, "chapter_index", 0))
    speaker_line = _line_from_profile(
        getattr(speaker_voice, {
            "entry": "opening_style",
            "pressure": "pressure_style",
            "pivot": "pivot_style",
            "aftermath": "aftermath_style",
            "echo": "echo_style",
        }.get(beat_key, "pressure_style")),
        beat.event.title,
        index=variant_index,
    )
    reaction = _line_from_profile(
        counterpart_response.reaction_lines.get(beat_key, []),
        "他没有立刻回话，只让沉默先压了一层上来。",
        index=variant_index,
    )
    reply = _line_from_profile(
        counterpart_response.reply_lines.get(beat_key, []),
        "你总得先把心里的话说完整。",
        index=variant_index,
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
        index=variant_index,
    )

    opener = {
        "entry": f"{speaker}看了{counterpart}一眼，低声道：“{speaker_line}”",
        "pressure": f"{speaker}把声音压得更低，对{counterpart}说道：“{speaker_line}”",
        "pivot": f"{speaker}终于抬眼迎上{counterpart}的视线：“{speaker_line}”",
        "aftermath": f"{speaker}隔了半息，才又对{counterpart}开口：“{speaker_line}”",
        "echo": f"临散前，{speaker}还是朝{counterpart}补了一句：“{speaker_line}”",
    }.get(beat_key, f"{speaker}看了{counterpart}一眼，低声道：“{speaker_line}”")
    response = _attach_reaction(counterpart, reaction)
    close = {
        "entry": f"{counterpart}最后只回了一句：“{reply}”",
        "pressure": f"{counterpart}把话压得很低，只往前送了一句：“{reply}”",
        "pivot": f"{counterpart}这才把最重的那句回了出来：“{reply}”",
        "aftermath": f"{counterpart}沉了沉气，仍旧把话落得很实：“{reply}”",
        "echo": f"{counterpart}临收声前，只留下了一句：“{reply}”",
    }.get(beat_key, f"{counterpart}最后只回了一句：“{reply}”")
    follow = {
        "entry": f"{speaker}指尖缓了一缓，又补了一句：“{followup}”",
        "pressure": f"{speaker}像是终于不想再退，顺势把后半句也压了出来：“{followup}”",
        "pivot": f"{speaker}没有就此收住，反而把更难听的一句也补到了明处：“{followup}”",
        "aftermath": f"{speaker}临到收声前仍没退，只轻轻接了一句：“{followup}”",
        "echo": f"{speaker}走出半步又停住，回身补了一句：“{followup}”",
    }.get(beat_key, f"{speaker}指尖缓了一缓，又补了一句：“{followup}”")
    if repeated:
        return " ".join([opener, response, close, follow, "两人都知道，话已经绕不过刚才留下的那层意思了。"])
    return " ".join([opener, response, close, follow])
