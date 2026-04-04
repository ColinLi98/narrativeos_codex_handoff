from __future__ import annotations

from ..models import NarrativeState, WorldBible
from .contracts import ResponseCadenceProfile, VoiceProfile, style_pack_from_world


def _actor_role(state: NarrativeState, actor_id: str) -> str:
    character = state.characters.get(actor_id)
    return character.role if character else ""


def voice_profile_for_actor(world: WorldBible, state: NarrativeState, actor_id: str) -> VoiceProfile:
    style_pack = style_pack_from_world(world)
    if actor_id in style_pack.dialogue.voice_profiles:
        return style_pack.dialogue.voice_profiles[actor_id]
    role_key = _actor_role(state, actor_id)
    if role_key and role_key in style_pack.dialogue.voice_profiles:
        return style_pack.dialogue.voice_profiles[role_key]
    return VoiceProfile(
        cadence="measured",
        directness=0.45,
        bluntness=0.45,
        restraint=0.55,
        social_rank_awareness=0.5,
        opening_style=["先把那口气压住，再慢慢把话送出去。"],
        pressure_style=["被逼到这里时，语气反而更稳，却也更难退。"],
        pivot_style=["真正拧动场面的往往不是大声，而是终于不再绕开。"],
        aftermath_style=["话停下时，沉默却还留在原地。"],
        echo_style=["等人散去时，那句没说尽的话才真正追上来。"],
    )


def response_profile_for_actor(world: WorldBible, state: NarrativeState, actor_id: str) -> ResponseCadenceProfile:
    style_pack = style_pack_from_world(world)
    if actor_id in style_pack.dialogue.response_profiles:
        return style_pack.dialogue.response_profiles[actor_id]
    role_key = _actor_role(state, actor_id)
    if role_key and role_key in style_pack.dialogue.response_profiles:
        return style_pack.dialogue.response_profiles[role_key]
    return ResponseCadenceProfile(
        reaction_tempo="measured",
        reaction_lines={
            "entry": ["没有立刻接话，只把那句意思在心里又过了一遍。"],
            "pressure": ["听到这里，手上的细小动作反而先停住了。"],
            "pivot": ["这才抬起眼来，像终于不打算再替谁留余地。"],
            "aftermath": ["到了收声的时候，反而比刚才更轻，也更沉。"],
            "echo": ["没有再追问，可沉默已经替下一次相见留了一道裂口。"],
        },
        reply_lines={
            "entry": ["我不是来听安稳话的。"],
            "pressure": ["你总得先替自己承认一次。"],
            "pivot": ["再退半步，也只是让伤口换个地方继续裂。"],
            "aftermath": ["这事不会就这样过去。"],
            "echo": ["下次再来，就别只带着半句真话。"],
        },
    )
