from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .core.contracts import style_pack_from_world
from .core.linter import lint_chapter_draft
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
            target_word_count=900,
            dialogue_density=0.35,
            sensory_motifs=list(event.tags[:2]),
            emotional_pivot=event.scene_function,
            ending_cadence="lingering",
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
        last_event = scene_beats[-1].event
        scene_plan = build_scene_plan(
            world=world,
            state_before=state_before,
            chapter_label=chapter_plan.scene_intent.label,
            scene_goal=chapter_plan.scene_intent.description,
            scene_beats=scene_beats,
            ending_hook=last_event.summary.rstrip("。"),
        )
        draft = write_chapter_draft(
            world=world,
            state_before=state_before,
            scene_plan=scene_plan,
            scene_beats=scene_beats,
            render_spec=render_spec,
        )
        lint_report = lint_chapter_draft(draft.body)
        body = lint_report["cleaned_text"]
        style_pack = style_pack_from_world(world)
        hook_templates = style_pack.hook_templates or ["这场话虽然停住了，可真正的余波还在后面等着。"]
        title = "第 %s 章 · %s" % (state_after.chapter_index, chapter_plan.scene_intent.label)
        summary = "这一步围绕 %s 继续收紧。" % _tag_labels(world, last_event.tags[:2] or ["destiny"])
        quote = "“%s”" % (last_event.title if len(last_event.title) <= 24 else last_event.summary[:24])
        return RenderedScene(
            event_id=last_event.event_id,
            concise_summary="%s。%s" % (last_event.summary.rstrip("。"), hook_templates[0]),
            interactive_scene="\n\n".join(body.split("\n\n")[:3]),
            premium_prose=body,
            story_title=title,
            chapter_summary=summary,
            pull_quote=quote,
            story_beats=[beat.event.title for beat in scene_beats],
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
                "lint_report": {
                    key: value
                    for key, value in lint_report.items()
                    if key != "cleaned_text"
                },
            },
        )


class LLMRenderer(Renderer):
    def __init__(self, backend: LLMBackend, fallback_renderer: Renderer) -> None:
        self.backend = backend
        self.fallback_renderer = fallback_renderer

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
            required = {"concise_summary", "interactive_scene", "premium_prose"}
            if required.issubset(payload.keys()):
                return RenderedScene(
                    event_id=event.event_id,
                    concise_summary=str(payload["concise_summary"]),
                    interactive_scene=str(payload["interactive_scene"]),
                    premium_prose=str(payload["premium_prose"]),
                    story_title=str(payload.get("story_title", event.title)),
                    chapter_summary=str(payload.get("chapter_summary", payload["concise_summary"])),
                    pull_quote=str(payload.get("pull_quote", "")),
                    story_beats=list(payload.get("story_beats", [])),
                    visual_details=list(payload.get("visual_details", [])),
                    visual_prompt=str(payload.get("visual_prompt", "")),
                    image_caption=str(payload.get("image_caption", payload["concise_summary"])),
                    image_motif=str(payload.get("image_motif", event.scene_function)),
                    palette_hint=str(payload.get("palette_hint", "")),
                    debug={"renderer": "llm", "raw_payload": payload, "backend_routing": backend_debug_info(self.backend)},
                )
        fallback = self.fallback_renderer.render(world, state_before, state_after, event)
        fallback.debug["renderer_fallback_reason"] = "invalid_llm_payload"
        fallback.debug["renderer"] = "llm_fallback_template"
        fallback.debug["raw_payload"] = payload if isinstance(payload, dict) else {"payload": payload}
        fallback.debug["backend_routing"] = backend_debug_info(self.backend)
        return fallback
