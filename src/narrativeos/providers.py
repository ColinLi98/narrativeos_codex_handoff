from __future__ import annotations

import copy
import hashlib
import json
import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest

from .canon import effective_rating_ceiling, hard_constraint_errors
from .models import CandidateBatch, EventAtom, NarrativeState, WorldBible
from .prompts import get_prompt_text, render_candidate_user_prompt
from .schemas import validate_payload
from .scene_functions import normalize_scene_function


class LLMBackend(ABC):
    @abstractmethod
    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        raise NotImplementedError


class ProviderExecutionError(RuntimeError):
    def __init__(self, provider_id: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.retryable = retryable


def _truthy_env(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _backend_name(backend: Any) -> str:
    return str(getattr(backend, "provider_id", backend.__class__.__name__.lower()))


def _deep_find_debug(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        for value in payload.values():
            found = _deep_find_debug(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _deep_find_debug(value, key)
            if found is not None:
                return found
    return None


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, ProviderExecutionError):
        return bool(exc.retryable)
    return isinstance(exc, (TimeoutError, ConnectionError, urlerror.URLError, urlerror.HTTPError))


def _normalized_route_debug(debug: Dict[str, Any], *, provider: str) -> Dict[str, Any]:
    normalized = dict(debug)
    selected_provider = _deep_find_debug(normalized, "selected_provider") or normalized.get("provider") or provider
    attempts = list(normalized.get("attempts", []))
    attempt_count = normalized.get("attempt_count")
    if attempt_count is None and attempts:
        attempt_count = sum(int(_deep_find_debug(item, "attempt_count") or 1) for item in attempts)
    if attempt_count is None:
        attempt_count = 1
    backend_error = (
        normalized.get("backend_error")
        or normalized.get("terminal_error")
        or _deep_find_debug(normalized, "backend_error")
        or _deep_find_debug(normalized, "terminal_error")
    )
    if backend_error is None:
        errors = normalized.get("errors")
        if isinstance(errors, list) and errors:
            backend_error = errors[-1].get("error")
    normalized.setdefault("provider", normalized.get("provider") or provider)
    normalized.setdefault("selected_provider", selected_provider)
    normalized.setdefault("fallback_used", bool(_deep_find_debug(normalized, "fallback_used")) if _deep_find_debug(normalized, "fallback_used") is not None else False)
    normalized.setdefault("attempt_count", int(attempt_count))
    normalized.setdefault("cache_hit", _deep_find_debug(normalized, "cache_hit"))
    normalized.setdefault("budget_blocked", bool(_deep_find_debug(normalized, "budget_blocked")) if _deep_find_debug(normalized, "budget_blocked") is not None else False)
    normalized.setdefault("backend_error", backend_error)
    latency_ms = normalized.get("latency_ms")
    if latency_ms is None and attempts:
        latency_ms = round(
            sum(float(_deep_find_debug(item, "latency_ms") or 0.0) for item in attempts),
            3,
        )
    if latency_ms is not None:
        normalized["latency_ms"] = round(float(latency_ms), 3)
    budget_estimate = normalized.get("budget_estimate") or _deep_find_debug(normalized, "budget_estimate")
    if isinstance(budget_estimate, dict):
        normalized["budget_estimate"] = dict(budget_estimate)
        normalized.setdefault("prompt_chars", budget_estimate.get("prompt_chars"))
        normalized.setdefault("estimated_tokens", budget_estimate.get("estimated_tokens"))
        normalized.setdefault("estimated_request_cost_usd", budget_estimate.get("estimated_cost_usd"))
    return normalized


def backend_debug_info(backend: Any) -> Dict[str, Any]:
    debug = getattr(backend, "last_route_debug", None)
    if isinstance(debug, dict):
        return _normalized_route_debug(debug, provider=_backend_name(backend))
    provider = _backend_name(backend)
    return {
        "provider": provider,
        "selected_provider": provider,
        "fallback_used": False,
        "attempt_count": 1,
        "cache_hit": None,
        "budget_blocked": False,
        "backend_error": None,
        "latency_ms": None,
        "budget_estimate": None,
        "prompt_chars": None,
        "estimated_tokens": None,
        "estimated_request_cost_usd": None,
    }


def _env_value(scope: Optional[str], suffix: str) -> Optional[str]:
    scope = str(scope or "").strip().lower()
    names: List[str] = []
    if scope:
        names.append(f"NARRATIVEOS_LLM_{scope.upper()}_{suffix}")
    names.append(f"NARRATIVEOS_LLM_{suffix}")
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def build_llm_policy_from_env(scope: Optional[str] = None) -> Dict[str, Any]:
    provider_order_raw = _env_value(scope, "PROVIDER_ORDER")
    routing_enabled = _truthy_env(_env_value(scope, "ROUTING_ENABLED"))
    max_attempts = int(_env_value(scope, "MAX_ATTEMPTS") or "2")
    cache_enabled = _truthy_env(_env_value(scope, "CACHE_ENABLED"))
    cache_max_entries = int(_env_value(scope, "CACHE_MAX_ENTRIES") or "128")
    max_prompt_chars_raw = _env_value(scope, "MAX_PROMPT_CHARS")
    max_estimated_cost_raw = _env_value(scope, "MAX_ESTIMATED_COST_USD")
    estimated_cost_per_1k_chars = float(_env_value(scope, "ESTIMATED_COST_PER_1K_CHARS") or "0.002")
    enabled = bool(provider_order_raw or routing_enabled)
    provider_order = [
        item.strip().lower()
        for item in (provider_order_raw.split(",") if provider_order_raw else ["openai", "anthropic", "local"])
        if item.strip()
    ] if enabled else []
    return {
        "scope": scope or "shared",
        "enabled": enabled,
        "routing_enabled": routing_enabled,
        "provider_order": provider_order,
        "retry_policy": {
            "max_attempts": max_attempts,
        },
        "cache_policy": {
            "enabled": cache_enabled,
            "max_entries": cache_max_entries,
        },
        "budget_policy": {
            "max_prompt_chars": int(max_prompt_chars_raw) if max_prompt_chars_raw else None,
            "max_estimated_cost_usd": float(max_estimated_cost_raw) if max_estimated_cost_raw else None,
            "estimated_cost_per_1k_chars": estimated_cost_per_1k_chars,
        },
    }


def estimate_request_budget(system_prompt: str, user_prompt: str, *, cost_per_1k_chars: float) -> Dict[str, float]:
    prompt_chars = float(len(system_prompt) + len(user_prompt))
    estimated_tokens = max(1.0, round(prompt_chars / 4.0, 3))
    estimated_cost_usd = round((prompt_chars / 1000.0) * float(cost_per_1k_chars), 6)
    return {
        "prompt_chars": prompt_chars,
        "estimated_tokens": estimated_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


class CandidateProvider(ABC):
    @abstractmethod
    def generate(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        depth: int = 0,
        min_candidates: int = 6,
        max_candidates: int = 10,
    ) -> CandidateBatch:
        raise NotImplementedError


class RuntimePromptCache:
    def __init__(self, *, max_entries: int = 128) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._entries:
            return None
        value = self._entries.pop(key)
        self._entries[key] = value
        return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        if key in self._entries:
            self._entries.pop(key)
        self._entries[key] = copy.deepcopy(value)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


class BudgetedLLMBackend(LLMBackend):
    def __init__(
        self,
        backend: LLMBackend,
        *,
        max_prompt_chars: Optional[int] = None,
        max_estimated_cost_usd: Optional[float] = None,
        estimated_cost_per_1k_chars: float = 0.002,
    ) -> None:
        self.backend = backend
        self.provider_id = _backend_name(backend)
        self.max_prompt_chars = int(max_prompt_chars) if max_prompt_chars is not None else None
        self.max_estimated_cost_usd = float(max_estimated_cost_usd) if max_estimated_cost_usd is not None else None
        self.estimated_cost_per_1k_chars = float(estimated_cost_per_1k_chars)
        self.last_route_debug: Dict[str, Any] = {}

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        estimate = estimate_request_budget(
            system_prompt,
            user_prompt,
            cost_per_1k_chars=self.estimated_cost_per_1k_chars,
        )
        if self.max_prompt_chars is not None and int(estimate["prompt_chars"]) > self.max_prompt_chars:
            self.last_route_debug = {
                "provider": self.provider_id,
                "budget_blocked": True,
                "budget_reason": "prompt_chars_exceeded",
                "budget_estimate": estimate,
                "max_prompt_chars": self.max_prompt_chars,
                "max_estimated_cost_usd": self.max_estimated_cost_usd,
                "latency_ms": 0.0,
            }
            raise ProviderExecutionError(
                self.provider_id,
                "prompt_chars_exceeded",
                retryable=False,
            )
        if self.max_estimated_cost_usd is not None and float(estimate["estimated_cost_usd"]) > self.max_estimated_cost_usd:
            self.last_route_debug = {
                "provider": self.provider_id,
                "budget_blocked": True,
                "budget_reason": "estimated_cost_exceeded",
                "budget_estimate": estimate,
                "max_prompt_chars": self.max_prompt_chars,
                "max_estimated_cost_usd": self.max_estimated_cost_usd,
                "latency_ms": 0.0,
            }
            raise ProviderExecutionError(
                self.provider_id,
                "estimated_cost_exceeded",
                retryable=False,
            )
        started = perf_counter()
        payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        latency_ms = round((perf_counter() - started) * 1000.0, 3)
        self.last_route_debug = {
            "provider": self.provider_id,
            "budget_blocked": False,
            "budget_estimate": estimate,
            "max_prompt_chars": self.max_prompt_chars,
            "max_estimated_cost_usd": self.max_estimated_cost_usd,
            "latency_ms": latency_ms,
            "delegate": backend_debug_info(self.backend),
        }
        return payload


class CachedLLMBackend(LLMBackend):
    def __init__(
        self,
        backend: LLMBackend,
        *,
        cache: Optional[RuntimePromptCache] = None,
        max_entries: int = 128,
    ) -> None:
        self.backend = backend
        self.provider_id = _backend_name(backend)
        self.cache = cache or RuntimePromptCache(max_entries=max_entries)
        self.last_route_debug: Dict[str, Any] = {}

    def _cache_key(self, *, system_prompt: str, user_prompt: str) -> str:
        digest = hashlib.sha256(
            f"{self.provider_id}\0{system_prompt}\0{user_prompt}".encode("utf-8")
        ).hexdigest()
        return digest

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        started = perf_counter()
        cache_key = self._cache_key(system_prompt=system_prompt, user_prompt=user_prompt)
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.last_route_debug = {
                "provider": self.provider_id,
                "cache_hit": True,
                "cache_key": cache_key[:12],
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
                "delegate": backend_debug_info(self.backend),
            }
            return cached
        payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        self.cache.set(cache_key, payload)
        self.last_route_debug = {
            "provider": self.provider_id,
            "cache_hit": False,
            "cache_key": cache_key[:12],
            "latency_ms": round((perf_counter() - started) * 1000.0, 3),
            "delegate": backend_debug_info(self.backend),
        }
        return payload


class RetryingLLMBackend(LLMBackend):
    def __init__(
        self,
        backend: LLMBackend,
        *,
        provider_id: Optional[str] = None,
        max_attempts: int = 2,
    ) -> None:
        self.backend = backend
        self.provider_id = provider_id or _backend_name(backend)
        self.max_attempts = max(1, int(max_attempts))
        self.last_route_debug: Dict[str, Any] = {}

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        errors: List[Dict[str, Any]] = []
        total_started = perf_counter()
        for attempt in range(1, self.max_attempts + 1):
            attempt_started = perf_counter()
            try:
                payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
                attempt_latency_ms = round((perf_counter() - attempt_started) * 1000.0, 3)
                self.last_route_debug = {
                    "provider": self.provider_id,
                    "selected_provider": _backend_name(self.backend),
                    "attempt_count": attempt,
                    "succeeded": True,
                    "latency_ms": round((perf_counter() - total_started) * 1000.0, 3),
                    "errors": errors,
                    "attempts": [
                        *errors,
                        {
                            "attempt": attempt,
                            "provider": _backend_name(self.backend),
                            "latency_ms": attempt_latency_ms,
                            "succeeded": True,
                        },
                    ],
                    "delegate": backend_debug_info(self.backend),
                }
                return payload
            except Exception as exc:
                retryable = _is_retryable_exception(exc)
                attempt_latency_ms = round((perf_counter() - attempt_started) * 1000.0, 3)
                errors.append(
                    {
                        "attempt": attempt,
                        "provider": _backend_name(self.backend),
                        "error": str(exc),
                        "retryable": retryable,
                        "latency_ms": attempt_latency_ms,
                    }
                )
                if attempt >= self.max_attempts or not retryable:
                    self.last_route_debug = {
                        "provider": self.provider_id,
                        "selected_provider": _backend_name(self.backend),
                        "attempt_count": attempt,
                        "succeeded": False,
                        "latency_ms": round((perf_counter() - total_started) * 1000.0, 3),
                        "errors": errors,
                        "attempts": errors,
                        "backend_error": str(exc),
                        "delegate": backend_debug_info(self.backend),
                    }
                    raise ProviderExecutionError(self.provider_id, str(exc), retryable=retryable) from exc
        raise RuntimeError("unreachable_retry_backend_state")


class RoutingLLMBackend(LLMBackend):
    def __init__(
        self,
        backends: Sequence[LLMBackend],
        *,
        provider_ids: Optional[Sequence[str]] = None,
        max_attempts_per_backend: int = 2,
    ) -> None:
        if not backends:
            raise ValueError("routing_backends_required")
        self.routes: List[RetryingLLMBackend] = []
        provider_ids = list(provider_ids or [])
        for index, backend in enumerate(backends):
            provider_id = provider_ids[index] if index < len(provider_ids) else _backend_name(backend)
            if isinstance(backend, RetryingLLMBackend):
                self.routes.append(backend)
            else:
                self.routes.append(
                    RetryingLLMBackend(
                        backend,
                        provider_id=provider_id,
                        max_attempts=max_attempts_per_backend,
                    )
                )
        self.provider_id = "routing"
        self.last_route_debug: Dict[str, Any] = {}

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        attempts: List[Dict[str, Any]] = []
        total_started = perf_counter()
        for index, backend in enumerate(self.routes):
            try:
                payload = backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
                route_debug = backend_debug_info(backend)
                attempts.append(route_debug)
                self.last_route_debug = {
                    "provider": "routing",
                    "selected_provider": backend.provider_id,
                    "fallback_used": index > 0,
                    "attempt_count": int(route_debug.get("attempt_count") or 1),
                    "cache_hit": route_debug.get("cache_hit"),
                    "budget_blocked": bool(route_debug.get("budget_blocked")),
                    "backend_error": route_debug.get("backend_error"),
                    "latency_ms": round((perf_counter() - total_started) * 1000.0, 3),
                    "budget_estimate": route_debug.get("budget_estimate"),
                    "attempts": attempts,
                    "succeeded": True,
                }
                return payload
            except Exception as exc:
                route_debug = backend_debug_info(backend)
                route_debug["terminal_error"] = str(exc)
                attempts.append(route_debug)
                continue
        self.last_route_debug = {
            "provider": "routing",
            "selected_provider": None,
            "fallback_used": True,
            "attempt_count": sum(int(item.get("attempt_count") or 1) for item in attempts) if attempts else 0,
            "cache_hit": _deep_find_debug(attempts, "cache_hit"),
            "budget_blocked": bool(_deep_find_debug(attempts, "budget_blocked")) if _deep_find_debug(attempts, "budget_blocked") is not None else False,
            "backend_error": attempts[-1].get("terminal_error") if attempts else "all_llm_providers_failed",
            "latency_ms": round((perf_counter() - total_started) * 1000.0, 3),
            "budget_estimate": _deep_find_debug(attempts, "budget_estimate"),
            "attempts": attempts,
            "succeeded": False,
        }
        raise RuntimeError("all_llm_providers_failed")


class StaticCandidateProvider(CandidateProvider):
    _LONG_ROUTE_CONTINUATION_MIN_END_TURN = 10
    _DUTY_FUNCTION_PRIORITIES: Dict[str, List[str]] = {
        "advance_plot": ["false_peace", "truth_trial", "debt_exchange", "temptation"],
        "advance_relationship": ["temptation", "misrecognition", "confession_window", "truth_trial"],
        "resolve_promise": ["debt_exchange", "confession_window", "truth_trial", "karma_ripening"],
        "expand_world": ["false_peace", "truth_trial", "karma_ripening", "debt_exchange"],
        "pace_breath": ["confession_window", "false_peace", "misrecognition", "temptation"],
        "deliver_climax": ["karma_ripening", "truth_trial", "humiliation", "debt_exchange"],
    }

    def __init__(self, event_pool: Sequence[EventAtom]) -> None:
        self.event_pool = [EventAtom.from_dict(event.to_dict()) for event in event_pool]
        self._batch_cache = RuntimePromptCache(max_entries=256)
        self._continuation_template_cache = RuntimePromptCache(max_entries=256)

    _CONTINUATION_FUNCTIONS_BY_PHASE: Dict[str, List[str]] = {
        "setup": ["false_peace", "temptation", "confession_window"],
        "early_rising": ["temptation", "truth_trial", "misrecognition"],
        "midpoint": ["truth_trial", "misrecognition", "debt_exchange"],
        "crisis": ["debt_exchange", "karma_ripening", "humiliation"],
        "climax": ["karma_ripening", "truth_trial", "confession_window"],
        "aftermath": ["confession_window", "debt_exchange", "false_peace"],
    }

    _SCENE_FUNCTION_LABELS: Dict[str, str] = {
        "false_peace": "表面平静先裂开了一道口",
        "temptation": "看似能两全的路又靠近了一步",
        "truth_trial": "那句迟早要说破的话终于逼到眼前",
        "misrecognition": "误会没有散，反而换了更难受的形状",
        "debt_exchange": "旧账开始以更具体的方式回来索还",
        "karma_ripening": "前面埋下的因果终于开始回潮",
        "humiliation": "最难堪的代价被推到了场面上",
        "confession_window": "终于出现了一个不得不说真话的窗口",
    }

    _SCENE_FUNCTION_TENSION: Dict[str, float] = {
        "false_peace": 0.08,
        "temptation": 0.12,
        "truth_trial": 0.15,
        "misrecognition": 0.12,
        "debt_exchange": 0.16,
        "karma_ripening": 0.18,
        "humiliation": 0.16,
        "confession_window": 0.11,
    }

    _TAG_LABELS: Dict[str, str] = {
        "urban_mystery": "真相与羞耻",
        "romance": "情意与靠近",
        "love": "情意与靠近",
        "secrecy": "藏着没说的真心",
        "truth": "真相与揭露",
        "suspense": "悬疑与压迫",
        "xianxia": "誓愿与天命",
        "destiny": "命运的去向",
        "synthetic": "试探与选择",
        "benchmark": "试探与回声",
        "court_drama": "门楣与体面",
        "fate": "命运与牵引",
        "selfhood": "自我与抉择",
        "reputation": "名声与体面",
        "duty": "责任与牵引",
    }

    def _continuation_functions(self, state: NarrativeState) -> List[str]:
        duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
        duty_functions = list(self._DUTY_FUNCTION_PRIORITIES.get(duty_type, []))
        phase_functions = list(
            self._CONTINUATION_FUNCTIONS_BY_PHASE.get(
                state.story_phase,
                self._CONTINUATION_FUNCTIONS_BY_PHASE["midpoint"],
            )
        )
        combined = list(dict.fromkeys(duty_functions + phase_functions))
        recent = [
            str(scene_function)
            for scene_function in state.recent_scene_functions[-3:]
        ]
        preferred = [scene_function for scene_function in combined if scene_function not in recent]
        if preferred:
            rotation = max(0, int(state.chapter_index)) % len(preferred)
            return preferred[rotation:] + preferred[:rotation]
        rotation = max(0, int(state.chapter_index)) % len(combined) if combined else 0
        return combined[rotation:] + combined[:rotation] if combined else phase_functions

    def _continuation_title(self, scene_function: str, location: str, *, index: int) -> str:
        base = self._SCENE_FUNCTION_LABELS.get(scene_function, "局势又往前推了一步")
        suffix = f"{location}" if location else "局势里"
        return f"{base} · {suffix} · {index + 1}"

    def _continuation_summary(
        self,
        *,
        scene_function: str,
        location: str,
        world: WorldBible,
        tags: Sequence[str],
    ) -> str:
        focus = "、".join(
            self._TAG_LABELS.get(tag, str(tag).replace("_", " "))
            for tag in (list(tags[:2]) or list((world.creator_controls.theme_targets or world.themes)[:2]) or ["真相", "代价"])
        )
        place = location or world.title
        return f"{place}里，被压回去的{focus}并没有散，局势被继续推向{self._SCENE_FUNCTION_LABELS.get(scene_function, '更难回头的一步')}。"

    def _continuation_promises(
        self,
        *,
        state: NarrativeState,
        event_id: str,
        scene_function: str,
        actors: Sequence[str],
    ) -> List[Dict[str, Any]]:
        promise_actions = set(str(item) for item in list((state.current_chapter_task or {}).get("promise_actions") or []))
        promise_targets = [str(item) for item in list((state.current_chapter_task or {}).get("promise_targets") or []) if str(item)]
        progression = dict((state.metadata or {}).get("longform_progression") or {})
        target_chapters = int(progression.get("series_target_chapters", 0) or 0)
        protected_runway = target_chapters and int(state.chapter_index or 0) < int(target_chapters * 0.96)
        if (
            (state.chapter_index >= state.min_end_turn and not protected_runway)
            or (len(state.open_promises) >= 3 and "open_follow_on_promise" not in promise_actions)
        ):
            return []
        holders = list(dict.fromkeys(list(actors[:2]) or list(actors[:1])))
        if not holders:
            return []
        promise_id = f"{event_id}__promise"
        description = "这一步逼出来的话，迟早要在后面的章节里被真正认下。"
        existing_promise_ids = {str(promise.promise_id) for promise in state.open_promises if str(getattr(promise, "promise_id", ""))}
        if promise_targets:
            preferred_promise_id = promise_targets[0]
            if preferred_promise_id not in existing_promise_ids:
                promise_id = preferred_promise_id
                description = f"{preferred_promise_id} 这条线索/承诺必须在后续章节继续追上来。"
            else:
                promise_id = f"{event_id}__follow_on_promise"
                description = f"{preferred_promise_id} 还没收住，需要在后续章节再打开一条新的追问。"
        return [
            {
                "promise_id": promise_id,
                "description": description,
                "opened_at_turn": state.turn_index,
                "due_by_turn": state.turn_index + 2,
                "holders": holders,
                "fulfillment_modes": ["truth", "choice", "confession"],
                "status": "open",
                "stakes": "medium",
                "tags": [scene_function, "story_thread", "runway"],
            }
        ]

    def _continuation_promises_close(
        self,
        *,
        state: NarrativeState,
        scene_function: str,
        actors: Sequence[str],
    ) -> List[str]:
        duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
        promise_actions = set(str(item) for item in list((state.current_chapter_task or {}).get("promise_actions") or []))
        actor_set = {str(actor) for actor in actors if str(actor)}
        overdue = [
            promise
            for promise in state.open_promises
            if promise.status == "open" and int(promise.due_by_turn or 0) <= int(state.turn_index or 0)
        ]
        if not overdue:
            overdue = [promise for promise in state.open_promises if promise.status == "open"]
        if not overdue:
            return []
        close_budget = 0
        if duty_type in {"resolve_promise", "deliver_climax"}:
            close_budget = 2
        elif duty_type in {"pace_breath", "advance_relationship", "expand_world"} and (
            len(state.open_promises) >= 5
            or "advance_payoff" in promise_actions
            or "close_arc_loop" in promise_actions
        ):
            close_budget = 1
        if scene_function in {"debt_exchange", "karma_ripening", "confession_window", "truth_trial"}:
            close_budget = max(close_budget, 1)
        if close_budget <= 0:
            return []

        def sort_key(promise):
            holder_overlap = bool(actor_set & set(promise.holders))
            stakes = str(promise.stakes or "")
            return (
                0 if holder_overlap else 1,
                0 if stakes not in {"low", "medium"} else 1,
                int(promise.opened_at_turn or 0),
                int(promise.due_by_turn or 0),
                promise.promise_id,
            )

        selected = []
        for promise in sorted(overdue, key=sort_key):
            if promise.promise_id not in selected:
                selected.append(promise.promise_id)
            if len(selected) >= close_budget:
                break
        progression = dict((state.metadata or {}).get("longform_progression") or {})
        target_chapters = int(progression.get("series_target_chapters", 0) or 0)
        protected_runway = target_chapters and int(state.chapter_index or 0) < int(target_chapters * 0.8)
        if protected_runway and (len(state.open_promises) - len(selected)) <= 0:
            while selected and (len(state.open_promises) - len(selected)) <= 0:
                selected.pop()
        return selected

    def _continuation_seeds(
        self,
        *,
        event_id: str,
        scene_function: str,
        actors: Sequence[str],
        tags: Sequence[str],
    ) -> List[Dict[str, Any]]:
        actor = actors[0] if actors else None
        if actor is None:
            return []
        target = actors[1] if len(actors) > 1 else None
        return [
            {
                "seed_id": f"{event_id}__seed",
                "source_event_id": event_id,
                "actor": actor,
                "target": target,
                "seed_type": scene_function,
                "charge": 0.32,
                "tags": list(dict.fromkeys(list(tags[:2]) + [scene_function, "continuation"])),
                "created_at_turn": 0,
                "ripening_conditions": [scene_function, "truth_trial", "karma_ripening"],
                "earliest_turn": 2,
                "latest_turn": 8,
                "status": "dormant",
                "transformable_by": ["mutual_truth", "vow_payment", "public_witness"],
            }
        ]

    def _continuation_blueprint_templates(
        self,
        base_event: EventAtom,
        *,
        state: NarrativeState,
        world: WorldBible,
        scene_functions: Sequence[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        raw_blueprints = list((base_event.metadata or {}).get("continuation_blueprints") or [])
        if limit <= 0 or not raw_blueprints:
            return []
        base_payload = base_event.to_dict()
        templates: List[Dict[str, Any]] = []
        fallback_functions = list(scene_functions) or [base_event.scene_function]
        current_duty = str((state.current_chapter_task or {}).get("duty_type") or "")
        current_phase = str(state.story_phase or "")
        for blueprint_index, raw in enumerate(raw_blueprints):
            payload = dict(raw or {})
            duty_allowlist = {str(item) for item in list(payload.get("duty_allowlist") or []) if str(item)}
            duty_denylist = {str(item) for item in list(payload.get("duty_denylist") or []) if str(item)}
            phase_allowlist = {str(item) for item in list(payload.get("phase_allowlist") or []) if str(item)}
            phase_denylist = {str(item) for item in list(payload.get("phase_denylist") or []) if str(item)}
            if duty_allowlist and current_duty not in duty_allowlist:
                continue
            if duty_denylist and current_duty in duty_denylist:
                continue
            if phase_allowlist and current_phase not in phase_allowlist:
                continue
            if phase_denylist and current_phase in phase_denylist:
                continue
            scene_function = normalize_scene_function(
                str(payload.get("scene_function") or fallback_functions[blueprint_index % len(fallback_functions)])
            )
            tags = list(
                dict.fromkeys(
                    list(base_event.tags)
                    + list(payload.get("tags") or [])
                    + list((world.creator_controls.theme_targets or [])[:2])
                    + [scene_function]
                )
            )
            metadata = dict(base_event.metadata or {})
            metadata.pop("continuation_blueprints", None)
            metadata.update(
                {
                    "continuation_variant": True,
                    "base_event_id": base_event.event_id,
                    "continuation_phase": payload.get("phase") or "",
                    "continuation_blueprint_id": str(payload.get("blueprint_id") or f"{base_event.event_id}::{scene_function}::{blueprint_index}"),
                    "generated_from_static_pool": True,
                }
            )
            if payload.get("next_continuation_blueprints"):
                metadata["continuation_blueprints"] = list(payload.get("next_continuation_blueprints") or [])
            if payload.get("scene_quality_contract"):
                metadata["scene_quality_contract"] = dict(payload.get("scene_quality_contract") or {})
            if payload.get("scene_blueprint_id"):
                metadata["scene_blueprint_id"] = str(payload.get("scene_blueprint_id") or "")
            location = str(payload.get("location") or base_event.location or (world.locations[blueprint_index % len(world.locations)] if world.locations else ""))
            templates.append(
                {
                    "base_event_id": base_event.event_id,
                    "index": blueprint_index,
                    "actors": list(payload.get("actors") or base_event.actors),
                    "title": str(payload.get("title") or self._continuation_title(scene_function, location, index=blueprint_index)),
                    "summary": str(
                        payload.get("summary")
                        or self._continuation_summary(
                            scene_function=scene_function,
                            location=location,
                            world=world,
                            tags=tags,
                        )
                    ),
                    "scene_function": scene_function,
                    "tags": tags,
                    "belief_updates": dict(payload.get("belief_updates") or base_payload.get("belief_updates") or {}),
                    "trust_deltas": list(payload.get("trust_deltas") or base_payload.get("trust_deltas") or []),
                    "emotion_deltas": list(payload.get("emotion_deltas") or base_payload.get("emotion_deltas") or []),
                        "rating_ceiling": str(payload.get("rating_ceiling") or base_event.rating_ceiling or world.creator_controls.darkness_ceiling or "PG13"),
                        "tension_delta": float(payload.get("tension_delta") or self._SCENE_FUNCTION_TENSION.get(scene_function, max(0.08, float(base_event.tension_delta)))),
                    "theme_impacts": dict(
                        payload.get("theme_impacts")
                        or {theme: 0.06 for theme in list((world.creator_controls.theme_targets or world.themes)[:3]) or list(tags[:2])}
                    ),
                        "agency_affordances": list(
                            dict.fromkeys(
                                list(payload.get("agency_affordances") or base_event.agency_affordances)
                                + list(tags[:2])
                                + ["continue_story"]
                            )
                        ),
                        "promises_close": list(
                            dict.fromkeys(
                                list(payload.get("promises_close") or [])
                                + self._continuation_promises_close(
                                    state=state,
                                    scene_function=scene_function,
                                    actors=list(payload.get("actors") or base_event.actors),
                                )
                            )
                        ),
                        "location": location,
                        "convergence_key": str(payload.get("convergence_key") or base_event.convergence_key or f"continuation::{scene_function}"),
                        "metadata": metadata,
                    }
                )
            if len(templates) >= limit:
                break
        return templates

    def _continuation_variant(
        self,
        base_event: EventAtom,
        *,
        state: NarrativeState,
        world: WorldBible,
        scene_function: str,
        index: int,
    ) -> EventAtom:
        payload = base_event.to_dict()
        variant_id = f"{base_event.event_id}__continuation__{state.chapter_index + 1}_{index}_{scene_function}"
        tags = list(dict.fromkeys(list(base_event.tags) + list((world.creator_controls.theme_targets or [])[:2]) + [scene_function]))
        metadata = dict(payload.get("metadata", {}))
        for key in (
            "terminal",
            "endgame_shape",
            "ending_gate",
            "required_fate_pressure",
            "required_inescapable_nodes",
        ):
            metadata.pop(key, None)
        metadata.update(
            {
                "continuation_variant": True,
                "base_event_id": base_event.event_id,
                "continuation_phase": state.story_phase,
                "generated_from_static_pool": True,
            }
        )
        world_locations = list(world.locations or [])
        rotated_location = world_locations[index % len(world_locations)] if world_locations else base_event.location
        payload.update(
            {
                "event_id": variant_id,
                "title": self._continuation_title(scene_function, rotated_location, index=index),
                "summary": self._continuation_summary(
                    scene_function=scene_function,
                    location=rotated_location,
                    world=world,
                    tags=tags,
                ),
                "scene_function": scene_function,
                "tags": tags,
                "preconditions_all": [],
                "forbidden_if_any": [],
                "world_fact_deltas_add": [f"continuation::{state.chapter_index + 1}::{scene_function}::{index}"],
                "world_fact_deltas_remove": [],
                "promises_open": self._continuation_promises(
                    state=state,
                    event_id=variant_id,
                    scene_function=scene_function,
                    actors=base_event.actors,
                ),
                "promises_close": [],
                "rating_ceiling": state.rating_ceiling or world.creator_controls.darkness_ceiling or base_event.rating_ceiling,
                "tension_delta": self._SCENE_FUNCTION_TENSION.get(scene_function, max(0.08, float(base_event.tension_delta))),
                "theme_impacts": {
                    theme: 0.06
                    for theme in list((world.creator_controls.theme_targets or world.themes)[:3]) or list(tags[:2])
                },
                "agency_affordances": list(dict.fromkeys(list(base_event.agency_affordances) + list(tags[:2]) + ["continue_story"])),
                "karmic_seed_creations": self._continuation_seeds(
                    event_id=variant_id,
                    scene_function=scene_function,
                    actors=base_event.actors,
                    tags=tags,
                ),
                "karmic_seed_resolutions": [],
                "location": rotated_location,
                "convergence_key": base_event.convergence_key or f"continuation::{scene_function}",
                "metadata": metadata,
            }
        )
        return EventAtom.from_dict(payload)

    def _continuation_template_cache_key(
        self,
        *,
        state: NarrativeState,
        world: WorldBible,
        scene_functions: Sequence[str],
        limit: int,
    ) -> str:
        payload = {
            "world_id": world.world_id,
            "story_phase": state.story_phase,
            "duty_type": str((state.current_chapter_task or {}).get("duty_type") or ""),
            "scene_functions": list(scene_functions),
            "limit": int(limit),
            "rating_ceiling": state.rating_ceiling or world.creator_controls.darkness_ceiling,
            "theme_targets": list(world.creator_controls.theme_targets or world.themes),
            "locations": list(world.locations or []),
            "event_pool_ids": [event.event_id for event in self.event_pool],
            "event_pool_continuation_blueprints": {
                event.event_id: list((event.metadata or {}).get("continuation_blueprints") or [])
                for event in self.event_pool
                if (event.metadata or {}).get("continuation_blueprints")
            },
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _continuation_variant_templates(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        scene_functions: Sequence[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if limit <= 0 or not self.event_pool:
            return []
        cache_key = self._continuation_template_cache_key(
            state=state,
            world=world,
            scene_functions=scene_functions,
            limit=limit,
        )
        cached = self._continuation_template_cache.get(cache_key)
        if isinstance(cached, list):
            return [dict(item) for item in cached]
        templates: List[Dict[str, Any]] = []
        for base_index, base_event in enumerate(self.event_pool):
            blueprint_templates = self._continuation_blueprint_templates(
                base_event,
                state=state,
                world=world,
                scene_functions=scene_functions,
                limit=max(0, limit - len(templates)),
            )
            if blueprint_templates:
                templates.extend(blueprint_templates)
                if len(templates) >= limit:
                    self._continuation_template_cache.set(cache_key, templates)
                    return [dict(item) for item in templates]
                continue
            base_payload = base_event.to_dict()
            for function_index, scene_function in enumerate(scene_functions):
                index = (base_index * len(scene_functions)) + function_index
                tags = list(dict.fromkeys(list(base_event.tags) + list((world.creator_controls.theme_targets or [])[:2]) + [scene_function]))
                metadata = dict(base_payload.get("metadata", {}))
                for key in (
                    "terminal",
                    "endgame_shape",
                    "ending_gate",
                    "required_fate_pressure",
                    "required_inescapable_nodes",
                ):
                    metadata.pop(key, None)
                metadata.update(
                    {
                        "continuation_variant": True,
                        "base_event_id": base_event.event_id,
                        "continuation_phase": state.story_phase,
                        "generated_from_static_pool": True,
                    }
                )
                world_locations = list(world.locations or [])
                rotated_location = world_locations[index % len(world_locations)] if world_locations else base_event.location
                templates.append(
                    {
                        "base_event_id": base_event.event_id,
                        "index": index,
                        "actors": list(base_event.actors),
                        "title": self._continuation_title(scene_function, rotated_location, index=index),
                        "summary": self._continuation_summary(
                            scene_function=scene_function,
                            location=rotated_location,
                            world=world,
                            tags=tags,
                        ),
                        "scene_function": scene_function,
                        "tags": tags,
                        "belief_updates": dict(base_payload.get("belief_updates", {})),
                        "trust_deltas": list(base_payload.get("trust_deltas", [])),
                        "emotion_deltas": list(base_payload.get("emotion_deltas", [])),
                        "rating_ceiling": state.rating_ceiling or world.creator_controls.darkness_ceiling or base_event.rating_ceiling,
                        "tension_delta": self._SCENE_FUNCTION_TENSION.get(scene_function, max(0.08, float(base_event.tension_delta))),
                        "theme_impacts": {
                            theme: 0.06
                            for theme in list((world.creator_controls.theme_targets or world.themes)[:3]) or list(tags[:2])
                        },
                        "agency_affordances": list(dict.fromkeys(list(base_event.agency_affordances) + list(tags[:2]) + ["continue_story"])),
                        "promises_close": self._continuation_promises_close(
                            state=state,
                            scene_function=scene_function,
                            actors=list(base_event.actors),
                        ),
                        "location": rotated_location,
                        "convergence_key": base_event.convergence_key or f"continuation::{scene_function}",
                        "metadata": metadata,
                    }
                )
                if len(templates) >= limit:
                    self._continuation_template_cache.set(cache_key, templates)
                    return [dict(item) for item in templates]
        self._continuation_template_cache.set(cache_key, templates)
        return [dict(item) for item in templates]

    def _continuation_candidates(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        existing_event_ids: Sequence[str],
        limit: int,
    ) -> List[EventAtom]:
        if limit <= 0 or not self.event_pool:
            return []
        event_ids = set(existing_event_ids)
        scene_functions = self._continuation_functions(state)
        variants: List[EventAtom] = []
        templates = self._continuation_variant_templates(
            state,
            world,
            scene_functions=scene_functions,
            limit=limit,
        )
        visited_event_ids = set(str(event_id) for event_id in state.visited_event_ids)
        for template in templates:
            variant_id = f"{template['base_event_id']}__continuation__{state.chapter_index + 1}_{template['index']}_{template['scene_function']}"
            if variant_id in event_ids or variant_id in visited_event_ids:
                continue
            payload = {
                "event_id": variant_id,
                "title": template["title"],
                "summary": template["summary"],
                "location": template["location"],
                "actors": list(template["actors"]),
                "scene_function": template["scene_function"],
                "tags": list(template["tags"]),
                "preconditions_all": [],
                "forbidden_if_any": [],
                "world_fact_deltas_add": [f"continuation::{state.chapter_index + 1}::{template['scene_function']}::{template['index']}"],
                "world_fact_deltas_remove": [],
                "belief_updates": dict(template["belief_updates"]),
                "trust_deltas": list(template["trust_deltas"]),
                "emotion_deltas": list(template["emotion_deltas"]),
                "promises_open": self._continuation_promises(
                    state=state,
                    event_id=variant_id,
                    scene_function=str(template["scene_function"]),
                    actors=list(template["actors"]),
                ),
                "promises_close": list(template.get("promises_close") or self._continuation_promises_close(
                    state=state,
                    scene_function=str(template["scene_function"]),
                    actors=list(template["actors"]),
                )),
                "rating_ceiling": template["rating_ceiling"],
                "tension_delta": template["tension_delta"],
                "theme_impacts": dict(template["theme_impacts"]),
                "agency_affordances": list(template["agency_affordances"]),
                "karmic_seed_creations": self._continuation_seeds(
                    event_id=variant_id,
                    scene_function=str(template["scene_function"]),
                    actors=list(template["actors"]),
                    tags=list(template["tags"]),
                ),
                "karmic_seed_resolutions": [],
                "convergence_key": template["convergence_key"],
                "metadata": dict(template["metadata"]),
            }
            variant = EventAtom.from_dict(payload)
            event_ids.add(variant.event_id)
            variants.append(variant)
            if len(variants) >= limit:
                return variants
        return variants

    def _should_use_longform_continuations(self, state: NarrativeState) -> bool:
        if bool((state.metadata or {}).get("longform_plan_enabled")):
            return True
        if (state.metadata or {}).get("longform_plan", {}):
            return True
        return state.min_end_turn >= self._LONG_ROUTE_CONTINUATION_MIN_END_TURN

    def _cache_key(
        self,
        state: NarrativeState,
        *,
        world: WorldBible,
        depth: int,
        min_candidates: int,
        max_candidates: int,
    ) -> str:
        payload = {
            "world_id": world.world_id,
            "depth": int(depth),
            "min_candidates": int(min_candidates),
            "max_candidates": int(max_candidates),
            "story_phase": state.story_phase,
            "chapter_index": int(state.chapter_index or 0),
            "min_end_turn": int(state.min_end_turn or 0),
            "current_series_id": state.current_series_id,
            "current_volume_id": state.current_volume_id,
            "current_arc_id": state.current_arc_id,
            "current_chapter_task": dict(state.current_chapter_task or {}),
            "recent_scene_functions": list(state.recent_scene_functions[-4:]),
            "world_facts": list(state.world_facts),
            "visited_event_ids": list(state.visited_event_ids),
            "open_promise_ids": sorted(promise.promise_id for promise in state.open_promises),
            "closed_promise_ids": list((state.metadata or {}).get("closed_promise_ids", [])),
            "scene_history": list((state.metadata or {}).get("scene_history", [])),
            "diagnostics_mode": (state.metadata or {}).get("longform_diagnostics_mode"),
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def generate(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        depth: int = 0,
        min_candidates: int = 6,
        max_candidates: int = 10,
    ) -> CandidateBatch:
        cache_key = self._cache_key(
            state,
            world=world,
            depth=depth,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        cached_payload = self._batch_cache.get(cache_key)
        if isinstance(cached_payload, dict):
            cached_batch = CandidateBatch.from_dict(cached_payload)
            cached_batch.debug["cache_hit"] = True
            cached_batch.debug["cache_key"] = cache_key[:12]
            return cached_batch

        visited_event_ids = set(str(event_id) for event_id in state.visited_event_ids)
        raw_candidates = [
            event
            for event in self.event_pool
            if event.event_id not in visited_event_ids
        ][:max_candidates]

        constraint_context = {
            "facts": set(state.world_facts),
            "state_character_ids": set(state.characters.keys()),
            "world_character_ids": {
                (
                    str(item)
                    if isinstance(item, str)
                    else str(getattr(item, "character_id", "") or "")
                )
                for item in list(world.characters or [])
                if (
                    (isinstance(item, str) and str(item))
                    or getattr(item, "character_id", None)
                )
            },
            "ceiling": effective_rating_ceiling(state, world=world),
            "existing_promise_ids": {promise.promise_id for promise in state.open_promises},
            "closed_promise_ids": set(state.metadata.get("closed_promise_ids", [])),
            "recent_scene_window": [normalize_scene_function(scene_function) for scene_function in state.recent_scene_functions[-2:]],
            "scene_history": set(state.metadata.get("scene_history", [])),
            "forbidden_moves": list(world.forbidden_moves),
        }

        legal_candidates: List[EventAtom] = []
        illegal_candidate_reasons: Dict[str, List[str]] = {}
        for candidate in raw_candidates:
            reasons = hard_constraint_errors(state, candidate, world=world, context=constraint_context)
            if reasons:
                illegal_candidate_reasons[candidate.event_id] = reasons
            else:
                legal_candidates.append(candidate)

        continuation_candidates: List[EventAtom] = []
        if self._should_use_longform_continuations(state) and len(legal_candidates) < min_candidates:
            continuation_limit = max(
                1,
                int(min_candidates - len(legal_candidates)),
                int(max_candidates - len(raw_candidates)),
            )
            continuation_candidates = self._continuation_candidates(
                state,
                world,
                existing_event_ids=[event.event_id for event in raw_candidates],
                limit=continuation_limit,
            )
            for candidate in continuation_candidates:
                raw_candidates.append(candidate)
                reasons = hard_constraint_errors(state, candidate, world=world, context=constraint_context)
                if reasons:
                    illegal_candidate_reasons[candidate.event_id] = reasons
                else:
                    legal_candidates.append(candidate)

        batch = CandidateBatch(
            raw_candidates=raw_candidates,
            legal_candidates=legal_candidates,
            illegal_candidate_reasons=illegal_candidate_reasons,
            debug={
                "provider": "static",
                "depth": depth,
                "raw_count": len(raw_candidates),
                "legal_count": len(legal_candidates),
                "min_candidates_requested": min_candidates,
                "continuation_candidate_count": len(continuation_candidates),
                "continuation_mode": "longform" if self._should_use_longform_continuations(state) else "standard",
                "cache_hit": False,
                "cache_key": cache_key[:12],
            },
        )
        self._batch_cache.set(cache_key, batch.to_dict())
        return batch


class LLMCandidateProvider(CandidateProvider):
    def __init__(
        self,
        backend: LLMBackend,
        fallback_provider: StaticCandidateProvider,
    ) -> None:
        self.backend = backend
        self.fallback_provider = fallback_provider

    def _parse_payload(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("candidate_events"), list):
                return [item for item in payload["candidate_events"] if isinstance(item, dict)]
            if isinstance(payload.get("candidates"), list):
                return [item for item in payload["candidates"] if isinstance(item, dict)]
        return []

    def generate(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        depth: int = 0,
        min_candidates: int = 6,
        max_candidates: int = 10,
    ) -> CandidateBatch:
        system_prompt = get_prompt_text("planner")
        user_prompt = render_candidate_user_prompt(
            world=world,
            state=state,
            depth=depth,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        backend_error: Optional[str] = None
        try:
            payload = self.backend.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
            raw_items = self._parse_payload(payload)
        except Exception as exc:
            payload = {"candidate_events": []}
            raw_items = []
            backend_error = str(exc)

        valid_candidates: List[EventAtom] = []
        invalid_payloads: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in raw_items:
            try:
                validate_payload(item, "event_atom.schema.json")
                candidate = EventAtom.from_dict(item)
            except Exception as exc:  # pragma: no cover - exercised in tests via fake backend
                invalid_payloads.append({"payload": item, "error": str(exc)})
                continue
            if candidate.event_id in seen_ids:
                invalid_payloads.append({"payload": item, "error": "duplicate_event_id"})
                continue
            seen_ids.add(candidate.event_id)
            candidate.metadata.setdefault("provider_source", "llm")
            valid_candidates.append(candidate)

        fallback_batch = self.fallback_provider.generate(
            state,
            world,
            depth=depth,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        fallback_by_id = {event.event_id: event for event in fallback_batch.raw_candidates}

        raw_candidates = list(valid_candidates)
        for event in fallback_batch.raw_candidates:
            if len(raw_candidates) >= max_candidates:
                break
            if event.event_id in {candidate.event_id for candidate in raw_candidates}:
                continue
            event_copy = EventAtom.from_dict(event.to_dict())
            event_copy.metadata.setdefault("provider_source", "fallback_static")
            raw_candidates.append(event_copy)

        if len(raw_candidates) < min_candidates:
            for event in fallback_batch.raw_candidates:
                if event.event_id in {candidate.event_id for candidate in raw_candidates}:
                    continue
                raw_candidates.append(EventAtom.from_dict(event.to_dict()))
                if len(raw_candidates) >= min_candidates:
                    break

        legal_candidates: List[EventAtom] = []
        illegal_candidate_reasons: Dict[str, List[str]] = {}
        for candidate in raw_candidates:
            reasons = hard_constraint_errors(state, candidate, world=world)
            if reasons:
                illegal_candidate_reasons[candidate.event_id] = reasons
            else:
                legal_candidates.append(candidate)

        backend_routing = backend_debug_info(self.backend)
        backend_routing["fallback_used"] = bool(
            backend_routing.get("fallback_used")
            or backend_error
            or any(event.metadata.get("provider_source") != "llm" for event in raw_candidates)
        )
        backend_routing.setdefault("selected_provider", backend_routing.get("provider"))
        backend_routing.setdefault("attempt_count", int(backend_routing.get("attempt_count") or 1))
        backend_routing.setdefault("cache_hit", backend_routing.get("cache_hit"))
        backend_routing.setdefault("budget_blocked", bool(backend_routing.get("budget_blocked")))
        backend_routing.setdefault("backend_error", backend_error or backend_routing.get("backend_error"))

        return CandidateBatch(
            raw_candidates=raw_candidates,
            legal_candidates=legal_candidates,
            illegal_candidate_reasons=illegal_candidate_reasons,
            debug={
                "provider": "llm",
                "backend_routing": backend_routing,
                "depth": depth,
                "llm_raw_count": len(raw_items),
                "llm_valid_count": len(valid_candidates),
                "invalid_payloads": invalid_payloads,
                "backend_error": backend_error,
                "fallback_raw_count": len(fallback_batch.raw_candidates),
                "fallback_legal_count": len(fallback_batch.legal_candidates),
                "backfilled_event_ids": [
                    event.event_id
                    for event in raw_candidates
                    if event.event_id in fallback_by_id and event.metadata.get("provider_source") != "llm"
                ],
            },
        )


class InlineJSONLLMBackend(LLMBackend):
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.provider_id = "inline_json"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        _ = system_prompt
        _ = user_prompt
        if isinstance(self.payload, str):
            return json.loads(self.payload)
        return self.payload


class LocalRuleBasedProvider(LLMBackend):
    def __init__(self, payload: Optional[Any] = None) -> None:
        self.payload = payload or {"candidate_events": []}
        self.provider_id = "local_rule_based"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        _ = system_prompt
        _ = user_prompt
        return self.payload


class DeepSeekProvider(LLMBackend):
    RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("NARRATIVEOS_DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = (base_url or os.getenv("NARRATIVEOS_DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.timeout_seconds = float(timeout_seconds or os.getenv("NARRATIVEOS_DEEPSEEK_TIMEOUT_SECONDS", "90"))
        self.max_tokens = int(max_tokens or os.getenv("NARRATIVEOS_DEEPSEEK_MAX_TOKENS", "4096"))
        self.provider_id = "deepseek"
        self.last_route_debug: Dict[str, Any] = {}

    def _request_body(self, *, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": self.max_tokens,
            "stream": False,
        }

    def _parse_message_content(self, content: str) -> Any:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeekProvider")
        body = self._request_body(system_prompt=system_prompt, user_prompt=user_prompt)
        started = perf_counter()
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw_response = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
            retryable = int(exc.code) in self.RETRYABLE_HTTP_STATUS
            self.last_route_debug = {
                "provider": self.provider_id,
                "selected_provider": self.provider_id,
                "model": self.model,
                "succeeded": False,
                "backend_error": f"deepseek_http_{exc.code}",
                "http_status": int(exc.code),
                "retryable": retryable,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
            }
            raise ProviderExecutionError(
                self.provider_id,
                f"deepseek_http_{exc.code}: {error_body}",
                retryable=retryable,
            ) from exc
        except (TimeoutError, urlerror.URLError) as exc:
            self.last_route_debug = {
                "provider": self.provider_id,
                "selected_provider": self.provider_id,
                "model": self.model,
                "succeeded": False,
                "backend_error": str(exc),
                "retryable": True,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
            }
            raise ProviderExecutionError(self.provider_id, str(exc), retryable=True) from exc

        try:
            response_payload = json.loads(raw_response)
            choice = (response_payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            parsed_payload = self._parse_message_content(content) if content else response_payload
        except Exception as exc:
            self.last_route_debug = {
                "provider": self.provider_id,
                "selected_provider": self.provider_id,
                "model": self.model,
                "succeeded": False,
                "backend_error": "deepseek_invalid_json",
                "retryable": True,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
            }
            raise ProviderExecutionError(self.provider_id, f"deepseek_invalid_json: {exc}", retryable=True) from exc

        usage = dict(response_payload.get("usage") or {})
        self.last_route_debug = {
            "provider": self.provider_id,
            "selected_provider": self.provider_id,
            "model": self.model,
            "returned_model": response_payload.get("model"),
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "usage": usage,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cache_hit": bool(usage.get("prompt_cache_hit_tokens")),
            "succeeded": True,
            "latency_ms": round((perf_counter() - started) * 1000.0, 3),
        }
        return parsed_payload


class OpenAIProvider(LLMBackend):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5") -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.provider_id = "openai"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIProvider")
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            "text": {"format": {"type": "json_object"}},
        }
        req = urlrequest.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlrequest.urlopen(req) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        text_output = "".join(
            item.get("text", "")
            for output in payload.get("output", [])
            for item in output.get("content", [])
            if item.get("type") in {"output_text", "text"}
        )
        return json.loads(text_output) if text_output else payload


class AnthropicProvider(LLMBackend):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5") -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.provider_id = "anthropic"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> Any:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for AnthropicProvider")
        body = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 1800,
        }
        req = urlrequest.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        with urlrequest.urlopen(req) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        text_output = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        return json.loads(text_output) if text_output else payload


def build_llm_backend_from_env(scope: Optional[str] = None) -> Optional[LLMBackend]:
    policy = build_llm_policy_from_env(scope)
    if not policy["enabled"]:
        return None

    provider_order = list(policy["provider_order"])
    max_attempts = int(policy["retry_policy"]["max_attempts"])
    cache_enabled = bool(policy["cache_policy"]["enabled"])
    cache_max_entries = int(policy["cache_policy"]["max_entries"])
    max_prompt_chars = policy["budget_policy"]["max_prompt_chars"]
    max_estimated_cost = policy["budget_policy"]["max_estimated_cost_usd"]
    estimated_cost_per_1k_chars = float(policy["budget_policy"]["estimated_cost_per_1k_chars"])
    backends: List[LLMBackend] = []
    provider_ids: List[str] = []
    for provider_name in provider_order:
        if provider_name == "deepseek" and os.getenv("DEEPSEEK_API_KEY"):
            backends.append(DeepSeekProvider(model=os.getenv("NARRATIVEOS_DEEPSEEK_MODEL", "deepseek-v4-flash")))
            provider_ids.append("deepseek")
        elif provider_name == "openai" and os.getenv("OPENAI_API_KEY"):
            backends.append(OpenAIProvider(model=os.getenv("NARRATIVEOS_OPENAI_MODEL", "gpt-5")))
            provider_ids.append("openai")
        elif provider_name == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
            backends.append(AnthropicProvider(model=os.getenv("NARRATIVEOS_ANTHROPIC_MODEL", "claude-sonnet-4-5")))
            provider_ids.append("anthropic")
        elif provider_name == "local":
            backends.append(LocalRuleBasedProvider())
            provider_ids.append("local")
    if not backends:
        return None
    if len(backends) == 1:
        backend: LLMBackend = RetryingLLMBackend(backends[0], provider_id=provider_ids[0], max_attempts=max_attempts)
    else:
        backend = RoutingLLMBackend(backends, provider_ids=provider_ids, max_attempts_per_backend=max_attempts)
    if max_prompt_chars is not None or max_estimated_cost is not None:
        backend = BudgetedLLMBackend(
            backend,
            max_prompt_chars=max_prompt_chars,
            max_estimated_cost_usd=max_estimated_cost,
            estimated_cost_per_1k_chars=estimated_cost_per_1k_chars,
        )
    if cache_enabled:
        backend = CachedLLMBackend(backend, max_entries=cache_max_entries)
    return backend
