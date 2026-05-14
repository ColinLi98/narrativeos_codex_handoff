from __future__ import annotations

import re
from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any, Dict, List

from .core.contracts import style_pack_from_world
from .core.linter import lint_chapter_draft, story_text_unit_count
from .core.writer import build_scene_plan, write_chapter_draft
from .models import ChapterPlan, EventAtom, NarrativeState, RenderedScene, SceneBeat, SceneIntent, SceneRenderSpec, WorldBible
from .prompts import get_prompt_text, render_scene_user_prompt
from .providers import LLMBackend, backend_debug_info
from .scene_functions import is_terminal_scene_function


GENERIC_TAG_LABELS = {
    "duty": "责任与牵引",
    "ambition": "前途与求胜",
    "reputation": "名声与体面",
    "love": "情意与靠近",
    "selfhood": "自我与抉择",
    "truth": "真相与揭露",
    "reform": "改写旧秩序",
    "sacrifice": "必须付出的代价",
    "destiny": "命运的去向",
    "suspense": "悬疑与压迫",
    "xianxia": "修行与誓愿",
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

SCENE_CARD_MARKERS = [
    "门影",
    "案角",
    "灯芯",
    "窗纸",
    "杯沿",
    "衣袖",
    "阶前风",
    "纸页声",
    "檐下光",
    "桌沿冷响",
]

SCENE_CARD_PRESSURES = [
    "把没说完的话压到明处",
    "逼人物换一种动作承认",
    "让旧账落回当前选择",
    "把退路收窄成当面回应",
    "让沉默不再能替人圆场",
    "把关系债推到下一步之前",
]

CHAPTER_TITLE_PRESSURES = {
    "false_peace": ["静处起波", "暗潮照面", "退路收窄", "平静失衡"],
    "temptation": ["试探加深", "半句成债", "退路被问", "分寸松动"],
    "truth_trial": ["真相抵近", "旧证上桌", "隐情照面", "追问落地"],
    "mask_crack": ["裂口显形", "伪装松开", "遮掩失手", "旧面具裂开"],
    "confession_window": ["真话临窗", "窗口未合", "迟话上桌", "坦白逼近"],
    "debt_exchange": ["旧账回潮", "亏欠落座", "债口重开", "后果换手"],
    "karma_ripening": ["因果回响", "旧种成熟", "回声逼近", "前因追身"],
    "humiliation": ["难堪上场", "体面受审", "众目压身", "羞意落地"],
    "vow_payment": ["誓言偿付", "旧誓索价", "承诺见血", "代价临门"],
    "misrecognition": ["误认加深", "错看成局", "半信成伤", "误会转向"],
    "mercy_vs_control": ["庇护成锁", "控制露面", "温情施压", "退路被握"],
}

CHAPTER_TITLE_FALLBACK_PRESSURES = ["选择收紧", "后果照面", "关系转向", "真话逼近", "旧事回潮"]

CHAPTER_TITLE_FRAMES = [
    "{anchor}里的{pressure}",
    "{marker}照出{pressure}",
    "{actors}被{pressure}追上",
    "{anchor}把{pressure}推近",
    "{pressure}落到{anchor}",
    "{marker}旁的{pressure}",
]


def _render_spec_length_bounds(render_spec: SceneRenderSpec) -> tuple[int, int]:
    target = int(render_spec.target_word_count or 2000)
    minimum = int(render_spec.min_target_word_count or max(200, target - 200))
    maximum = int(render_spec.max_target_word_count or max(target, target + 200))
    return minimum, maximum


RENDERED_SCENE_REQUIRED_KEYS = {"concise_summary", "interactive_scene", "premium_prose"}


def _payload_missing_required_keys(payload: Dict[str, Any]) -> List[str]:
    return sorted(key for key in RENDERED_SCENE_REQUIRED_KEYS if key not in payload)


def _event_actor_boundary_violations(
    text: str,
    state_before: NarrativeState,
    scene_beats: List[SceneBeat],
) -> List[str]:
    allowed_actor_ids = {
        str(actor_id)
        for beat in scene_beats
        for actor_id in list(beat.event.actors or [])
        if str(actor_id)
    }
    violations: List[str] = []
    for actor_id, character in state_before.characters.items():
        if actor_id in allowed_actor_ids:
            continue
        name = str(getattr(character, "name", "") or "").strip()
        if len(name) >= 2 and name in text:
            violations.append(name)
    return sorted(dict.fromkeys(violations))


def _render_scene_payload_gate(
    payload: Dict[str, Any],
    *,
    state_before: NarrativeState,
    scene_beats: List[SceneBeat],
    minimum: int,
    maximum: int,
) -> Dict[str, Any]:
    missing_keys = _payload_missing_required_keys(payload)
    if missing_keys:
        return {
            "ok": False,
            "fallback_reason": "invalid_llm_payload",
            "missing_required_keys": missing_keys,
            "grounding_issues": [],
            "length_gate": None,
        }

    premium_prose = str(payload.get("premium_prose") or "")
    lint_report = lint_chapter_draft(premium_prose)
    prose_units = int(lint_report.get("text_unit_count") or story_text_unit_count(premium_prose))
    meta_leaks = list(lint_report.get("meta_leaks") or [])
    disallowed_latin_hits = list(lint_report.get("disallowed_latin_token_hits") or [])
    actor_violations = _event_actor_boundary_violations(
        premium_prose,
        state_before,
        scene_beats,
    )
    grounding_issues: List[Dict[str, Any]] = []
    if meta_leaks:
        grounding_issues.append(
            {
                "issue": "forbidden_engineering_or_meta_leak",
                "evidence": meta_leaks[:5],
            }
        )
    if disallowed_latin_hits:
        grounding_issues.append(
            {
                "issue": "disallowed_latin_token",
                "evidence": [dict(item) for item in disallowed_latin_hits[:5]],
            }
        )
    if actor_violations:
        grounding_issues.append(
            {
                "issue": "event_actor_boundary_violation",
                "evidence": actor_violations,
            }
        )
    length_ok = minimum <= prose_units <= maximum
    fallback_reason = None
    if grounding_issues:
        fallback_reason = "llm_grounding_gate_failed"
    elif not length_ok:
        fallback_reason = "llm_length_gate_failed"
    return {
        "ok": not grounding_issues and length_ok,
        "fallback_reason": fallback_reason,
        "missing_required_keys": [],
        "grounding_issues": grounding_issues,
        "length_gate": {
            "observed_units": prose_units,
            "min_target_word_count": minimum,
            "max_target_word_count": maximum,
            "ok": length_ok,
        },
        "lint_metrics": {
            "text_unit_count": prose_units,
            "dialogue_count": lint_report.get("dialogue_count"),
            "action_count": lint_report.get("action_count"),
            "detail_count": lint_report.get("detail_count"),
            "meta_leak_count": len(meta_leaks),
            "disallowed_latin_token_count": len(disallowed_latin_hits),
        },
    }


def _length_retry_user_prompt(user_prompt: str, gate: Dict[str, Any], *, minimum: int, maximum: int) -> str:
    length_gate = dict(gate.get("length_gate") or {})
    observed = int(length_gate.get("observed_units") or 0)
    return (
        f"{user_prompt}\n\n"
        "Renderer retry instruction: the previous premium_prose failed the length gate "
        f"with {observed} text units. Rewrite the full JSON response so premium_prose is "
        f"between {minimum} and {maximum} Chinese text units, while preserving the same event, "
        "actor boundary, facts, and continuation pressure. Output JSON only."
    )


class Renderer(ABC):
    @abstractmethod
    def render(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        event: EventAtom,
    ) -> RenderedScene:
        raise NotImplementedError

    def render_scene(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        chapter_plan: ChapterPlan,
        scene_beats: List[SceneBeat],
        render_spec: SceneRenderSpec,
    ) -> RenderedScene:
        if not scene_beats:
            raise ValueError("scene_beats must not be empty")
        return self.render(world, state_before, state_after, scene_beats[-1].event)


def _style_labels(world: WorldBible) -> Dict[str, str]:
    style_pack = style_pack_from_world(world)
    labels = dict(GENERIC_TAG_LABELS)
    labels.update(style_pack.tag_labels)
    labels.update(style_pack.goal_labels)
    return labels


def _tag_labels(world: WorldBible, tags: List[str]) -> str:
    labels = _style_labels(world)
    readable = [labels.get(tag, str(tag).replace("_", " ")) for tag in tags[:3]]
    return "、".join(readable) if readable else "命运的轻微偏转"


def _scene_label(scene_function: str) -> str:
    return SCENE_FUNCTION_LABELS.get(scene_function, scene_function.replace("_", " "))


def _scene_card_seed(state_after: NarrativeState, event: EventAtom, *, offset: int = 0) -> int:
    raw = f"{event.event_id}:{event.scene_function}:{event.location}:{state_after.chapter_index}:{offset}"
    return sum(ord(char) for char in raw) + int(state_after.chapter_index or 0) * 37


def _clean_title_fragment(value: str, *, fallback: str = "", max_chars: int = 10) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[A-Za-z][A-Za-z0-9_-]*", "", text)
    text = re.sub(r"\s*·\s*\d+\s*$", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.strip(" ·:：/|_-，。；;、")
    text = re.sub(r"^[，、]+|[，、]+$", "", text)
    if not text:
        text = fallback
    return str(text or "")[:max_chars]


def _actor_names_for_event(state: NarrativeState, event: EventAtom) -> str:
    names = []
    for actor_id in event.actors[:2]:
        character = state.characters.get(actor_id)
        names.append(character.name if character else actor_id.replace("_", " "))
    return "、".join(name for name in names if name) or "众人"


def _reader_chapter_title(
    world: WorldBible,
    state_before: NarrativeState,
    state_after: NarrativeState,
    chapter_plan: ChapterPlan,
    scene_beats: List[SceneBeat],
) -> str:
    event = scene_beats[-1].event
    chapter_index = int(state_after.chapter_index or chapter_plan.chapter_index or 0)
    seed = _scene_card_seed(state_after, event, offset=70)
    pressure_pool = CHAPTER_TITLE_PRESSURES.get(event.scene_function) or CHAPTER_TITLE_FALLBACK_PRESSURES
    pressure = pressure_pool[seed % len(pressure_pool)]
    marker = SCENE_CARD_MARKERS[_scene_card_seed(state_after, event, offset=71) % len(SCENE_CARD_MARKERS)]
    location = _clean_title_fragment(event.location, max_chars=8)
    event_anchor = _clean_title_fragment(event.title, fallback=chapter_plan.scene_intent.label, max_chars=8)
    anchor = location or event_anchor or marker
    actors = _actor_names_for_event(state_before, event)
    frame = CHAPTER_TITLE_FRAMES[_scene_card_seed(state_after, event, offset=72) % len(CHAPTER_TITLE_FRAMES)]
    title_tail = frame.format(anchor=anchor, marker=marker, actors=actors, pressure=pressure)
    if not title_tail or title_tail == pressure:
        title_tail = f"{_tag_labels(world, event.tags[:1] or ['destiny'])}里的{pressure}"
    title_tail = _clean_title_fragment(title_tail, fallback=pressure, max_chars=16)
    return f"第 {chapter_index} 章 · {title_tail}"


def _chapter_summary(world: WorldBible, state_before: NarrativeState, state_after: NarrativeState, event: EventAtom) -> str:
    scene_label = _scene_label(event.scene_function)
    location = event.location or "场面"
    actors = _actor_names_for_event(state_before, event)
    tags = _tag_labels(world, event.tags[:2] or ["destiny"])
    marker = SCENE_CARD_MARKERS[_scene_card_seed(state_after, event, offset=1) % len(SCENE_CARD_MARKERS)]
    pressure = SCENE_CARD_PRESSURES[_scene_card_seed(state_after, event, offset=2) % len(SCENE_CARD_PRESSURES)]
    variants = [
        f"{location}里的{marker}把{scene_label}推向{actors}，{tags}不再只是背景。",
        f"{actors}在{location}接住{scene_label}，{marker}先把后果照清。",
        f"{scene_label}沿着{location}的{marker}收紧，{pressure}。",
        f"{location}这一章把{tags}压进{marker}和人物动作里，{scene_label}换了方向。",
        f"{marker}先动了一下，{actors}被迫把{scene_label}从旧说法里拆出来。",
    ]
    return variants[_scene_card_seed(state_after, event, offset=3) % len(variants)]


def _reader_pull_quote(body: str, state_after: NarrativeState, scene_beats: List[SceneBeat]) -> str:
    candidates = [
        item.strip()
        for item in re.findall(r"“([^”]{6,42})”", body or "")
        if item.strip() and not item.strip().startswith("这里会显示")
    ]
    if candidates:
        event = scene_beats[-1].event
        chosen = candidates[_scene_card_seed(state_after, event, offset=4) % len(candidates)]
        return f"“{chosen}”"
    last_event = scene_beats[-1].event
    fallback = last_event.title if len(last_event.title) <= 24 else last_event.summary[:24]
    return f"“{fallback}”"


def _reader_story_beats(world: WorldBible, state_before: NarrativeState, state_after: NarrativeState, scene_beats: List[SceneBeat]) -> List[str]:
    beats: List[str] = []
    for index, beat in enumerate(scene_beats):
        event = beat.event
        scene_label = _scene_label(event.scene_function)
        location = event.location or "场面"
        marker = SCENE_CARD_MARKERS[_scene_card_seed(state_after, event, offset=10 + index) % len(SCENE_CARD_MARKERS)]
        pressure = SCENE_CARD_PRESSURES[_scene_card_seed(state_after, event, offset=20 + index) % len(SCENE_CARD_PRESSURES)]
        actor_names = _actor_names_for_event(state_before, event)
        raw_label = str(beat.beat_label or event.title or scene_label)
        if "：" in raw_label:
            raw_label = raw_label.split("：", 1)[-1].strip()
        raw_label = raw_label.strip(" ·:：/|_-")
        variants = [
            f"{location}的{marker}把{scene_label}落到{actor_names}的动作里。",
            f"{raw_label[:18]}不再只是旧事，{marker}{pressure}。",
            f"{actor_names}围着{marker}重新接住{scene_label}，场面转向下一层。",
            f"{scene_label}从{location}的{marker}露出，逼人物把后半句说实。",
            f"{marker}和{location}里的细响一起改变{scene_label}的方向。",
        ]
        beats.append(variants[_scene_card_seed(state_after, event, offset=30 + index) % len(variants)])
    return beats


class TemplateRenderer(Renderer):
    def render(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        event: EventAtom,
    ) -> RenderedScene:
        beat = SceneBeat(
            beat_index=1,
            event=event,
            beat_label=event.title,
            dramatic_job=event.scene_function,
            tension_after=state_after.tension,
        )
        chapter_plan = ChapterPlan(
            chapter_index=state_after.chapter_index,
            story_phase=state_after.story_phase,
            scene_intent=SceneIntent(
                intent_id=event.scene_function,
                label=event.title,
                description=event.summary,
                preferred_scene_functions=[event.scene_function],
                preferred_tags=list(event.tags),
            ),
            beat_target=1,
            beat_count=1,
            ending_ready=is_terminal_scene_function(event.scene_function, event.metadata),
            selected_event_ids=[event.event_id],
        )
        render_spec = SceneRenderSpec(
            prose_mode="novel_lush",
            viewpoint_character=event.actors[0] if event.actors else "",
            target_word_count=int(state_after.word_budget or state_before.word_budget or 2000),
            dialogue_density=0.35,
            sensory_motifs=list(event.tags[:2]),
            emotional_pivot=event.scene_function,
            ending_cadence="lingering",
            min_target_word_count=max(200, int(state_after.word_budget or state_before.word_budget or 2000) - 200),
            max_target_word_count=max(int(state_after.word_budget or state_before.word_budget or 2000), int(state_after.word_budget or state_before.word_budget or 2000) + 200),
            must_include_beats=[event.title],
        )
        return self.render_scene(world, state_before, state_after, chapter_plan, [beat], render_spec)

    def render_scene(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        chapter_plan: ChapterPlan,
        scene_beats: List[SceneBeat],
        render_spec: SceneRenderSpec,
    ) -> RenderedScene:
        render_started = perf_counter()
        last_event = scene_beats[-1].event
        scene_plan = build_scene_plan(
            world=world,
            state_before=state_before,
            chapter_label=chapter_plan.scene_intent.label,
            scene_goal=chapter_plan.scene_intent.description,
            scene_beats=scene_beats,
            ending_hook=last_event.summary.rstrip("。"),
        )
        draft_started = perf_counter()
        draft = write_chapter_draft(
            world=world,
            state_before=state_before,
            scene_plan=scene_plan,
            scene_beats=scene_beats,
            render_spec=render_spec,
        )
        draft_elapsed_ms = round((perf_counter() - draft_started) * 1000.0, 3)
        lint_started = perf_counter()
        lint_report = lint_chapter_draft(draft.body)
        lint_elapsed_ms = round((perf_counter() - lint_started) * 1000.0, 3)
        body = lint_report["cleaned_text"]
        style_pack = style_pack_from_world(world)
        hook_templates = style_pack.hook_templates or ["这场话虽然停住了，可真正的余波还在后面等着。"]
        title = _reader_chapter_title(world, state_before, state_after, chapter_plan, scene_beats)
        summary = _chapter_summary(world, state_before, state_after, last_event)
        quote = _reader_pull_quote(body, state_after, scene_beats)
        return RenderedScene(
            event_id=last_event.event_id,
            concise_summary="%s。%s" % (last_event.summary.rstrip("。"), hook_templates[0]),
            interactive_scene="\n\n".join(body.split("\n\n")[:3]),
            premium_prose=body,
            story_title=title,
            chapter_summary=summary,
            pull_quote=quote,
            story_beats=_reader_story_beats(world, state_before, state_after, scene_beats),
            visual_details=[
                "地点：%s" % (scene_beats[0].event.location or "未指定"),
                "情绪：%s" % _tag_labels(world, last_event.tags[:2] or ["destiny"]),
                "张力：%.2f" % state_after.tension,
            ],
            visual_prompt="地点：%s；人物：%s；关键词：%s" % (
                last_event.location or "未指定",
                "、".join(
                    state_before.characters[actor_id].name if actor_id in state_before.characters else actor_id
                    for actor_id in last_event.actors
                ) or "众人",
                _tag_labels(world, last_event.tags or ["destiny"]),
            ),
            image_caption=summary,
            image_motif=last_event.scene_function,
            palette_hint=(world.creator_controls.theme_targets[0] if world.creator_controls.theme_targets else "narrative"),
            debug={
                "renderer": "template",
                "scene_plan": scene_plan.to_dict(),
                "draft_metadata": dict(draft.metadata),
                "timing_ms": {
                    "write_draft": draft_elapsed_ms,
                    "post_repair_lint": lint_elapsed_ms,
                    "total_render_scene": round((perf_counter() - render_started) * 1000.0, 3),
                },
                "lint_report": {
                    key: value
                    for key, value in lint_report.items()
                    if key != "cleaned_text"
                },
            },
        )


class LLMRenderer(Renderer):
    def __init__(self, backend: LLMBackend, fallback_renderer: Renderer, *, length_retry_attempts: int = 1) -> None:
        self.backend = backend
        self.fallback_renderer = fallback_renderer
        self.length_retry_attempts = max(0, int(length_retry_attempts))

    def _rendered_scene_from_payload(
        self,
        payload: Dict[str, Any],
        *,
        event: EventAtom,
        fallback_title: str,
        render_spec: SceneRenderSpec | None = None,
        gate: Dict[str, Any] | None = None,
        renderer_attempt_count: int = 1,
    ) -> RenderedScene:
        debug = {
            "renderer": "llm",
            "raw_payload": payload,
            "backend_routing": backend_debug_info(self.backend),
            "renderer_attempt_count": renderer_attempt_count,
        }
        if render_spec is not None:
            debug["render_spec"] = render_spec.to_dict()
        if gate is not None:
            debug["llm_payload_gate"] = dict(gate)
        return RenderedScene(
            event_id=event.event_id,
            concise_summary=str(payload["concise_summary"]),
            interactive_scene=str(payload["interactive_scene"]),
            premium_prose=str(payload["premium_prose"]),
            story_title=str(payload.get("story_title", fallback_title)),
            chapter_summary=str(payload.get("chapter_summary", payload["concise_summary"])),
            pull_quote=str(payload.get("pull_quote", "")),
            story_beats=list(payload.get("story_beats", [])),
            visual_details=list(payload.get("visual_details", [])),
            visual_prompt=str(payload.get("visual_prompt", "")),
            image_caption=str(payload.get("image_caption", payload["concise_summary"])),
            image_motif=str(payload.get("image_motif", event.scene_function)),
            palette_hint=str(payload.get("palette_hint", "")),
            debug=debug,
        )

    def render(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        event: EventAtom,
    ) -> RenderedScene:
        system_prompt = get_prompt_text("renderer")
        user_prompt = render_scene_user_prompt(
            world=world,
            state_before=state_before,
            state_after=state_after,
            event=event,
        )
        try:
            payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:
            fallback = self.fallback_renderer.render(world, state_before, state_after, event)
            fallback.debug["renderer_fallback_reason"] = "llm_backend_error"
            fallback.debug["renderer"] = "llm_fallback_template"
            fallback.debug["raw_payload"] = {"error": str(exc)}
            fallback.debug["backend_routing"] = backend_debug_info(self.backend)
            return fallback
        if isinstance(payload, dict):
            if not _payload_missing_required_keys(payload):
                return self._rendered_scene_from_payload(payload, event=event, fallback_title=event.title)
        fallback = self.fallback_renderer.render(world, state_before, state_after, event)
        fallback.debug["renderer_fallback_reason"] = "invalid_llm_payload"
        fallback.debug["renderer"] = "llm_fallback_template"
        fallback.debug["raw_payload"] = payload if isinstance(payload, dict) else {"payload": payload}
        fallback.debug["backend_routing"] = backend_debug_info(self.backend)
        return fallback

    def render_scene(
        self,
        world: WorldBible,
        state_before: NarrativeState,
        state_after: NarrativeState,
        chapter_plan: ChapterPlan,
        scene_beats: List[SceneBeat],
        render_spec: SceneRenderSpec,
    ) -> RenderedScene:
        if not scene_beats:
            raise ValueError("scene_beats must not be empty")
        system_prompt = get_prompt_text("renderer")
        user_prompt = render_scene_user_prompt(
            world=world,
            state_before=state_before,
            state_after=state_after,
            event=scene_beats[-1].event,
            chapter_plan=chapter_plan,
            scene_beats=scene_beats,
            render_spec=render_spec,
        )
        minimum, maximum = _render_spec_length_bounds(render_spec)
        last_payload: Any = None
        last_gate: Dict[str, Any] = {}
        attempts = self.length_retry_attempts + 1
        attempted_count = 0
        for attempt_index in range(attempts):
            attempted_count = attempt_index + 1
            active_user_prompt = (
                user_prompt
                if attempt_index == 0
                else _length_retry_user_prompt(user_prompt, last_gate, minimum=minimum, maximum=maximum)
            )
            try:
                payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=active_user_prompt)
            except Exception as exc:
                fallback = self.fallback_renderer.render_scene(world, state_before, state_after, chapter_plan, scene_beats, render_spec)
                fallback.debug["renderer_fallback_reason"] = "llm_backend_error"
                fallback.debug["renderer"] = "llm_fallback_template"
                fallback.debug["raw_payload"] = {"error": str(exc)}
                fallback.debug["backend_routing"] = backend_debug_info(self.backend)
                fallback.debug["renderer_attempt_count"] = attempted_count
                return fallback
            last_payload = payload
            if not isinstance(payload, dict):
                break
            gate = _render_scene_payload_gate(
                payload,
                state_before=state_before,
                scene_beats=scene_beats,
                minimum=minimum,
                maximum=maximum,
            )
            last_gate = gate
            if gate.get("ok"):
                return self._rendered_scene_from_payload(
                    payload,
                    event=scene_beats[-1].event,
                    fallback_title=chapter_plan.scene_intent.label,
                    render_spec=render_spec,
                    gate=gate,
                    renderer_attempt_count=attempted_count,
                )
            if gate.get("fallback_reason") == "llm_length_gate_failed" and attempt_index < attempts - 1:
                continue
            fallback = self.fallback_renderer.render_scene(world, state_before, state_after, chapter_plan, scene_beats, render_spec)
            fallback.debug["renderer_fallback_reason"] = str(gate.get("fallback_reason") or "invalid_llm_payload")
            fallback.debug["renderer"] = "llm_fallback_template"
            fallback.debug["raw_payload"] = payload
            fallback.debug["backend_routing"] = backend_debug_info(self.backend)
            fallback.debug["llm_payload_gate"] = gate
            fallback.debug["renderer_attempt_count"] = attempted_count
            if gate.get("length_gate"):
                fallback.debug["llm_length_gate"] = dict(gate.get("length_gate") or {})
            return fallback
        fallback = self.fallback_renderer.render_scene(world, state_before, state_after, chapter_plan, scene_beats, render_spec)
        fallback.debug["renderer_fallback_reason"] = "invalid_llm_payload"
        fallback.debug["renderer"] = "llm_fallback_template"
        fallback.debug["raw_payload"] = last_payload if isinstance(last_payload, dict) else {"payload": last_payload}
        fallback.debug["backend_routing"] = backend_debug_info(self.backend)
        fallback.debug["llm_payload_gate"] = last_gate
        fallback.debug["renderer_attempt_count"] = attempted_count
        return fallback
