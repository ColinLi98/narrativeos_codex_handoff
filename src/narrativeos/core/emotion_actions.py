from __future__ import annotations

from ..models import NarrativeState, SceneBeat, WorldBible
from .contracts import PressureResponseStyle, style_pack_from_world


def _pick_line(lines: list[str], index: int) -> str:
    return lines[index % len(lines)] if lines else ""


def _actor_role(state: NarrativeState, actor_id: str) -> str:
    character = state.characters.get(actor_id)
    return character.role if character else ""


def _pressure_style_for_actor(
    world: WorldBible,
    state: NarrativeState,
    actor_id: str,
) -> PressureResponseStyle:
    style_pack = style_pack_from_world(world)
    if actor_id in style_pack.dialogue.pressure_styles:
        return style_pack.dialogue.pressure_styles[actor_id]
    role_key = _actor_role(state, actor_id)
    if role_key and role_key in style_pack.dialogue.pressure_styles:
        return style_pack.dialogue.pressure_styles[role_key]
    return PressureResponseStyle(
        under_pressure="先压住动作，再把真正难退的那一步慢慢逼近。",
        when_cornered="被逼到边上时，反而不再替自己留太多退路。",
        when_softening="语气先松下来，但心里的边界没有一起撤掉。",
        when_deflecting="想把真心挪开半寸，却又没法真的装作若无其事。",
    )


def _duty_focus(duty_type: str) -> str:
    return {
        "advance_plot": "局势和后果往前推近",
        "advance_relationship": "两人之间那点靠近与试探",
        "resolve_promise": "迟早要认下的旧账和真话",
        "expand_world": "眼前这一局背后的旧规矩与更大代价",
        "pace_breath": "表面缓下来、心里却没真正散掉的余波",
        "deliver_climax": "已经没法回头的那一步选择",
    }.get(duty_type, "这一步还没说透的心事")


def _pressure_phrase(style: PressureResponseStyle, job: str) -> str:
    mapping = {
        "entry": style.under_pressure,
        "pressure": style.when_cornered or style.under_pressure,
        "pivot": style.when_cornered or style.when_deflecting,
        "aftermath": style.when_softening or style.under_pressure,
        "echo": style.when_deflecting or style.when_softening,
    }
    return str(mapping.get(job) or style.under_pressure or "动作先稳住了，可真正难退的那一步并没有散。")


def _fallback_variants(
    *,
    duty_type: str,
    scene_function: str,
    job: str,
    pressure_phrase: str,
) -> list[str]:
    scene_label = scene_function.replace("_", " ")
    focus = _duty_focus(duty_type)
    return {
        "entry": [
            f"{pressure_phrase}，连{focus}都像先被拢到了这一步{scene_label}跟前。",
            f"最先绷紧的不是声量，而是{focus}；{pressure_phrase}",
            f"场面还没真动起来，{focus}却已经被这一步{scene_label}轻轻挑开了口子。",
        ],
        "pressure": [
            f"{pressure_phrase}，把{focus}一路压到了最难回避的位置。",
            f"真正逼人的不是哪句重话，而是{focus}在这一步{scene_label}里已经没法再往后撤。",
            f"{focus}被一点点推近，连最轻的停顿都像在替这一步{scene_label}加重分量。",
        ],
        "pivot": [
            f"{pressure_phrase}，场面便从还能周旋，变成了{focus}不得不选边。",
            f"最轻的一点改口，都把{focus}从暗处推到了明面上。",
            f"这一瞬真正拧紧的，是{focus}终于被这一步{scene_label}逼得不能再装稳。",
        ],
        "aftermath": [
            f"{pressure_phrase}，留下来的却是{focus}比刚才更沉了一层。",
            f"人虽然先收住了，{focus}却还停在原地，像迟早要回来索账。",
            f"话音落下后最压人的，反而是{focus}已经没法轻轻放回去了。",
        ],
        "echo": [
            f"{pressure_phrase}，等人声退下去时，真正追上来的还是{focus}。",
            f"越到后面，越能听见{focus}沿着这一步{scene_label}慢慢回身索账。",
            f"场面像是先静了，可{focus}还在更慢地逼近，没打算就这样散掉。",
        ],
    }.get(job, [f"{pressure_phrase}，{focus}已经被这一步{scene_label}推到了更近的地方。"])


def compose_emotion_action(world: WorldBible, state_before: NarrativeState, beat: SceneBeat, *, repeated: bool) -> str:
    style_pack = style_pack_from_world(world)
    scene_function = beat.event.scene_function
    job = beat.dramatic_job
    duty_type = str((state_before.current_chapter_task or {}).get("duty_type") or "")
    beat_index = getattr(beat, "beat_index", 0)
    event_seed = sum(ord(char) for char in str(getattr(beat.event, "event_id", "") or ""))
    chapter_index = int(getattr(state_before, "chapter_index", 0) or 0)
    variant_index = beat_index + event_seed + chapter_index * 5
    action_pool = style_pack.emotion_actions.action_map.get(scene_function, {})
    if repeated and action_pool.get("repeat"):
        return _pick_line(action_pool["repeat"], variant_index)
    if action_pool.get(job):
        return _pick_line(action_pool[job], variant_index)
    actor_id = beat.event.actors[0] if beat.event.actors else ""
    pressure_style = _pressure_style_for_actor(world, state_before, actor_id) if actor_id else PressureResponseStyle()
    duty_defaults = _fallback_variants(
        duty_type=duty_type,
        scene_function=scene_function,
        job=job,
        pressure_phrase=_pressure_phrase(pressure_style, job),
    )
    defaults = {
        "entry": [
            "桌上的器物轻轻一碰，谁都知道这一步已经走出去，很难再收回来。",
            "衣角和桌沿只轻轻擦了一下，场面里的分寸却已经开始变窄。",
            "谁也没有大动作，可气氛先一步绷紧，像一句话已经碰到嘴边。",
        ],
        "pressure": [
            "连抬眼、换气和指尖的细小停顿都带上了掂量，像谁先多动一下，谁就会先露底。",
            "呼吸和目光都慢了半拍，仿佛谁先把话挑明，谁就得先承担代价。",
            "细到指节收紧、肩背发沉的变化都压在场面上，让人再难装作无事。",
        ],
        "pivot": [
            "那一点极轻的停顿和改口，让场面从还能周旋，变成了不得不选边。",
            "不过一瞬的沉默，局势就从还可拖延，变成了谁都得给出站位。",
            "那一下看似轻微的收声，反而把最重的选择推到了明处。",
        ],
        "aftermath": [
            "说出口的那几句已经停了，可散开时每个人都比来时更沉。",
            "话音落下以后，谁也没立刻动，反倒让余下那层难堪更清楚了。",
            "真正压人的不是那几句话本身，而是它们停下以后还留在场里的回声。",
        ],
        "echo": [
            "越到最后，越能听见那些没说尽的话在场里慢慢回身索账。",
            "场面像是先静了，可没落地的那点情绪反而在更慢地逼近。",
            "人声退下去之后，留下来的不是轻松，而是更难绕开的回响。",
        ],
    }
    return _pick_line(duty_defaults or defaults.get(job, ["动作并不大，可局势已经变了味道。"]), variant_index)
