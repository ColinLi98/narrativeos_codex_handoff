from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from ..providers import (
    CandidateProvider,
    LLMBackend,
    LLMCandidateProvider,
    StaticCandidateProvider,
    build_llm_backend_from_env,
    build_llm_policy_from_env,
)
from ..rendering import LLMRenderer, Renderer, TemplateRenderer
from ..models import EventAtom
from .provider_rollout import ProviderRolloutService


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderRoutingService:
    def __init__(
        self,
        *,
        rollout_service: Optional[ProviderRolloutService] = None,
        candidate_backend: Optional[LLMBackend] = None,
        renderer_backend: Optional[LLMBackend] = None,
        fallback_renderer: Optional[Renderer] = None,
    ) -> None:
        self.rollout_service = rollout_service
        self.candidate_backend = candidate_backend
        self.renderer_backend = renderer_backend
        self.fallback_renderer = fallback_renderer or TemplateRenderer()
        self._renderer: Optional[Renderer] = None

    @classmethod
    def from_env(
        cls,
        *,
        rollout_service: Optional[ProviderRolloutService] = None,
        candidate_backend: Optional[LLMBackend] = None,
        renderer_backend: Optional[LLMBackend] = None,
        fallback_renderer: Optional[Renderer] = None,
        shared_backend: Optional[LLMBackend] = None,
    ) -> "ProviderRoutingService":
        return cls(
            rollout_service=rollout_service,
            candidate_backend=candidate_backend or shared_backend or build_llm_backend_from_env(scope="candidate"),
            renderer_backend=renderer_backend or shared_backend or build_llm_backend_from_env(scope="renderer"),
            fallback_renderer=fallback_renderer,
        )

    def resolve_track(
        self,
        *,
        track: str,
        surface: str,
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        backend_present = self.candidate_backend is not None if track == "candidate" else self.renderer_backend is not None
        if self.rollout_service is None:
            rollout_status = "active" if backend_present else "shadow"
            return {
                "track": track,
                "rollout_status": rollout_status,
                "managed": False,
                "backend_present": backend_present,
                "surface": surface,
                "account_id": account_id,
                "session_id": session_id,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "bucket_percentage": 0,
                "world_allowlist": [],
                "world_match": True,
                "canary_match": False,
                "enabled": backend_present,
                "fallback_only": not backend_present,
                "reviewer_id": None,
                "updated_at": None,
                "reason": None,
            }
        return self.rollout_service.resolve_track(
            track=track,
            backend_present=backend_present,
            surface=surface,
            account_id=account_id,
            session_id=session_id,
            world_id=world_id,
            world_version_id=world_version_id,
        )

    def _annotate_candidate_debug(self, provider: CandidateProvider, decision: Dict[str, Any]) -> CandidateProvider:
        parent = self

        class RolloutAwareCandidateProvider(CandidateProvider):
            def generate(self, state, world, *, depth=0, min_candidates=6, max_candidates=10):
                batch = provider.generate(state, world, depth=depth, min_candidates=min_candidates, max_candidates=max_candidates)
                batch.debug["provider_rollout"] = dict(decision)
                route = dict(batch.debug.get("backend_routing") or {})
                route.setdefault("provider_rollout", dict(decision))
                batch.debug["backend_routing"] = route
                return batch

        return RolloutAwareCandidateProvider()

    def _annotate_renderer(self, renderer: Renderer, decision: Dict[str, Any]) -> Renderer:
        class RolloutAwareRenderer(Renderer):
            def render(self, world, state_before, state_after, event):
                rendered = renderer.render(world, state_before, state_after, event)
                rendered.debug["provider_rollout"] = dict(decision)
                route = dict(rendered.debug.get("backend_routing") or {})
                route.setdefault("provider_rollout", dict(decision))
                rendered.debug["backend_routing"] = route
                return rendered

            def render_scene(self, world, state_before, state_after, chapter_plan, scene_beats, render_spec):
                rendered = renderer.render_scene(world, state_before, state_after, chapter_plan, scene_beats, render_spec)
                rendered.debug["provider_rollout"] = dict(decision)
                route = dict(rendered.debug.get("backend_routing") or {})
                route.setdefault("provider_rollout", dict(decision))
                rendered.debug["backend_routing"] = route
                return rendered

        return RolloutAwareRenderer()

    def build_candidate_provider(
        self,
        event_atoms: Sequence[EventAtom],
        *,
        surface: str = "unknown",
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        allow_llm: bool = True,
    ) -> CandidateProvider:
        static_provider = StaticCandidateProvider(event_atoms)
        decision = self.resolve_track(
            track="candidate",
            surface=surface,
            account_id=account_id,
            session_id=session_id,
            world_id=world_id,
            world_version_id=world_version_id,
        )
        if allow_llm and decision["enabled"] and self.candidate_backend is not None:
            delegate: CandidateProvider = LLMCandidateProvider(self.candidate_backend, static_provider)
        else:
            delegate = static_provider
        return self._annotate_candidate_debug(delegate, decision)

    def build_renderer(
        self,
        *,
        surface: str = "unknown",
        account_id: Optional[str] = None,
        session_id: Optional[str] = None,
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
    ) -> Renderer:
        decision = self.resolve_track(
            track="renderer",
            surface=surface,
            account_id=account_id,
            session_id=session_id,
            world_id=world_id,
            world_version_id=world_version_id,
        )
        if decision["enabled"] and self.renderer_backend is not None:
            if not isinstance(self._renderer, LLMRenderer) or getattr(self._renderer, "backend", None) is not self.renderer_backend:
                self._renderer = LLMRenderer(self.renderer_backend, self.fallback_renderer)
            delegate = self._renderer
        else:
            delegate = self.fallback_renderer
        return self._annotate_renderer(delegate, decision)

    def policy_summary(self) -> Dict[str, Any]:
        candidate_policy = build_llm_policy_from_env("candidate")
        renderer_policy = build_llm_policy_from_env("renderer")
        rollout_summary = (
            self.rollout_service.summary(
                candidate_backend_present=self.candidate_backend is not None,
                renderer_backend_present=self.renderer_backend is not None,
            )
            if self.rollout_service is not None
            else {
                "tracks": {
                    "candidate": {"rollout_status": "active" if self.candidate_backend is not None else "shadow"},
                    "renderer": {"rollout_status": "active" if self.renderer_backend is not None else "shadow"},
                },
                "active_tracks": ["candidate"] if self.candidate_backend is not None else [],
                "canary_tracks": [],
                "rolled_back_tracks": [],
                "recommended_next_action": "monitor_active_rollout" if (self.candidate_backend or self.renderer_backend) else "configure_provider_backend",
            }
        )
        return {
            "generated_at": _utcnow(),
            "candidate": {
                **candidate_policy,
                "backend_present": self.candidate_backend is not None,
                "fallback_chain": ["llm_routing", "static_candidate_provider"] if self.candidate_backend is not None else ["static_candidate_provider"],
                "rollout": rollout_summary["tracks"]["candidate"],
            },
            "renderer": {
                **renderer_policy,
                "backend_present": self.renderer_backend is not None,
                "fallback_chain": ["llm_renderer", "template_renderer"] if self.renderer_backend is not None else ["template_renderer"],
                "rollout": rollout_summary["tracks"]["renderer"],
            },
            "rollout_summary": rollout_summary,
        }
