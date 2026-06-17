from __future__ import annotations

import copy
import hashlib
import json
import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence, Set
from urllib import error as urlerror
from urllib import request as urlrequest

from .canon import hard_constraint_errors
from .models import CandidateBatch, EventAtom, NarrativeState, WorldBible
from .prompts import get_prompt_text, render_candidate_user_prompt
from .schemas import validate_payload


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

    def __init__(self, event_pool: Sequence[EventAtom]) -> None:
        self.event_pool = [EventAtom.from_dict(event.to_dict()) for event in event_pool]
        self._seen_cache_keys: Set[str] = set()

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
        phase_functions = list(
            self._CONTINUATION_FUNCTIONS_BY_PHASE.get(
                state.story_phase,
                self._CONTINUATION_FUNCTIONS_BY_PHASE["midpoint"],
            )
        )
        recent = [
            str(scene_function)
            for scene_function in state.recent_scene_functions[-2:]
        ]
        preferred = [scene_function for scene_function in phase_functions if scene_function not in recent]
        return preferred or phase_functions

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
        if state.chapter_index >= state.min_end_turn or len(state.open_promises) >= 3:
            return []
        holders = list(dict.fromkeys(list(actors[:2]) or list(actors[:1])))
        if not holders:
            return []
        return [
            {
                "promise_id": f"{event_id}__promise",
                "description": "这一步逼出来的话，迟早要在后面的章节里被真正认下。",
                "opened_at_turn": state.turn_index,
                "due_by_turn": state.turn_index + 2,
                "holders": holders,
                "fulfillment_modes": ["truth", "choice", "confession"],
                "status": "open",
                "stakes": "medium",
                "tags": [scene_function, "story_thread"],
            }
        ]

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

    def _continuation_blueprint(
        self,
        base_event: EventAtom,
        *,
        scene_function: str,
        index: int,
    ) -> Optional[Dict[str, Any]]:
        blueprints = [
            dict(item)
            for item in list((base_event.metadata or {}).get("continuation_blueprints") or [])
            if isinstance(item, dict)
        ]
        if not blueprints:
            return None
        matching = [
            item
            for item in blueprints
            if str(item.get("scene_function") or "") == scene_function
        ]
        if not matching:
            return None
        return dict(matching[index % len(matching)])

    def _continuation_base_priority(self, base_event: EventAtom, state: NarrativeState) -> tuple[int, int, int]:
        blueprints = [
            dict(item)
            for item in list((base_event.metadata or {}).get("continuation_blueprints") or [])
            if isinstance(item, dict)
        ]
        open_promise_ids = {str(promise.promise_id) for promise in state.open_promises}
        duty_type = str((state.current_chapter_task or {}).get("duty_type") or "")
        closes_open_promise = any(
            str(promise_id) in open_promise_ids
            for blueprint in blueprints
            for promise_id in list(blueprint.get("promises_close") or [])
        ) or any(str(promise.promise_id) in open_promise_ids for promise in base_event.promises_open)
        phase_matches = any(
            not list(blueprint.get("phase_allowlist") or [])
            or state.story_phase in {str(item) for item in list(blueprint.get("phase_allowlist") or [])}
            for blueprint in blueprints
        )
        duty_matches = any(
            not list(blueprint.get("duty_allowlist") or [])
            or (duty_type and duty_type in {str(item) for item in list(blueprint.get("duty_allowlist") or [])})
            for blueprint in blueprints
        )
        return (
            0 if closes_open_promise else 1,
            0 if phase_matches else 1,
            0 if duty_matches else 1,
        )

    def _continuation_promises_close(
        self,
        *,
        state: NarrativeState,
        base_event: EventAtom,
        blueprint: Optional[Dict[str, Any]],
    ) -> List[str]:
        open_promise_ids = {str(promise.promise_id) for promise in state.open_promises}
        explicit_close_ids = list(blueprint.get("promises_close") or []) if blueprint else []
        if explicit_close_ids:
            return [
                str(promise_id)
                for promise_id in explicit_close_ids
                if str(promise_id) in open_promise_ids
            ]
        return [
            str(promise.promise_id)
            for promise in base_event.promises_open
            if str(promise.promise_id) in open_promise_ids
        ]

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
        blueprint = self._continuation_blueprint(base_event, scene_function=scene_function, index=index)
        blueprint_tags = list(blueprint.get("tags") or []) if blueprint else []
        tags = list(
            dict.fromkeys(
                list(blueprint_tags)
                + list(base_event.tags)
                + list((world.creator_controls.theme_targets or [])[:2])
                + [scene_function]
            )
        )
        actors = list(blueprint.get("actors") or base_event.actors) if blueprint else list(base_event.actors)
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
                **({"continuation_blueprint_id": str(blueprint.get("blueprint_id"))} if blueprint and blueprint.get("blueprint_id") else {}),
            }
        )
        world_locations = list(world.locations or [])
        rotated_location = (
            str(blueprint.get("location"))
            if blueprint and blueprint.get("location")
            else (world_locations[index % len(world_locations)] if world_locations else base_event.location)
        )
        payload.update(
            {
                "event_id": variant_id,
                "title": str(blueprint.get("title")) if blueprint and blueprint.get("title") else self._continuation_title(scene_function, rotated_location, index=index),
                "summary": str(blueprint.get("summary")) if blueprint and blueprint.get("summary") else self._continuation_summary(
                    scene_function=scene_function,
                    location=rotated_location,
                    world=world,
                    tags=tags,
                ),
                "actors": actors,
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
                    actors=actors,
                ),
                "promises_close": self._continuation_promises_close(
                    state=state,
                    base_event=base_event,
                    blueprint=blueprint,
                ),
                "rating_ceiling": state.rating_ceiling or world.creator_controls.darkness_ceiling or base_event.rating_ceiling,
                "tension_delta": self._SCENE_FUNCTION_TENSION.get(scene_function, max(0.08, float(base_event.tension_delta))),
                "theme_impacts": {
                    theme: 0.06
                    for theme in list((world.creator_controls.theme_targets or world.themes)[:3]) or list(tags[:2])
                },
                "agency_affordances": list(
                    dict.fromkeys(
                        list(base_event.agency_affordances)
                        + list(blueprint.get("agency_affordances") or [] if blueprint else [])
                        + list(tags[:2])
                        + ["continue_story"]
                    )
                ),
                "karmic_seed_creations": self._continuation_seeds(
                    event_id=variant_id,
                    scene_function=scene_function,
                    actors=actors,
                    tags=tags,
                ),
                "karmic_seed_resolutions": [],
                "location": rotated_location,
                "convergence_key": base_event.convergence_key or f"continuation::{scene_function}",
                "metadata": metadata,
            }
        )
        return EventAtom.from_dict(payload)

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
        prioritized_pool = [
            base_event
            for _original_index, base_event in sorted(
                enumerate(self.event_pool),
                key=lambda item: (*self._continuation_base_priority(item[1], state), item[0]),
            )
        ]
        for base_index, base_event in enumerate(prioritized_pool):
            for function_index, scene_function in enumerate(scene_functions):
                variant = self._continuation_variant(
                    base_event,
                    state=state,
                    world=world,
                    scene_function=scene_function,
                    index=(base_index * len(scene_functions)) + function_index,
                )
                if variant.event_id in event_ids or variant.event_id in state.visited_event_ids:
                    continue
                event_ids.add(variant.event_id)
                variants.append(variant)
                if len(variants) >= limit:
                    return variants
        return variants

    def _cache_key(
        self,
        state: NarrativeState,
        world: WorldBible,
        *,
        depth: int,
        min_candidates: int,
        max_candidates: int,
    ) -> str:
        payload = {
            "world_id": world.world_id,
            "state_id": state.state_id,
            "turn_index": state.turn_index,
            "chapter_index": state.chapter_index,
            "story_phase": state.story_phase,
            "visited_event_ids": list(state.visited_event_ids),
            "min_end_turn": state.min_end_turn,
            "depth": depth,
            "min_candidates": min_candidates,
            "max_candidates": max_candidates,
            "event_pool_ids": [event.event_id for event in self.event_pool],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

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
            world,
            depth=depth,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        cache_hit = cache_key in self._seen_cache_keys
        self._seen_cache_keys.add(cache_key)
        raw_candidates = [
            EventAtom.from_dict(event.to_dict())
            for event in self.event_pool
            if event.event_id not in state.visited_event_ids
        ][:max_candidates]

        legal_candidates: List[EventAtom] = []
        illegal_candidate_reasons: Dict[str, List[str]] = {}
        for candidate in raw_candidates:
            reasons = hard_constraint_errors(state, candidate, world=world)
            if reasons:
                illegal_candidate_reasons[candidate.event_id] = reasons
            else:
                legal_candidates.append(candidate)

        continuation_candidates: List[EventAtom] = []
        longform_mode = bool(state.metadata.get("longform_plan_enabled"))
        continuation_mode = "longform" if longform_mode else (
            "long_route" if state.min_end_turn >= self._LONG_ROUTE_CONTINUATION_MIN_END_TURN else "off"
        )
        if (
            continuation_mode != "off"
            and len(legal_candidates) < min_candidates
        ):
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
                reasons = hard_constraint_errors(state, candidate, world=world)
                if reasons:
                    illegal_candidate_reasons[candidate.event_id] = reasons
                else:
                    legal_candidates.append(candidate)

        return CandidateBatch(
            raw_candidates=raw_candidates,
            legal_candidates=legal_candidates,
            illegal_candidate_reasons=illegal_candidate_reasons,
            debug={
                "provider": "static",
                "depth": depth,
                "raw_count": len(raw_candidates),
                "legal_count": len(legal_candidates),
                "min_candidates_requested": min_candidates,
                "cache_hit": cache_hit,
                "cache_key": cache_key,
                "continuation_mode": continuation_mode,
                "continuation_candidate_count": len(continuation_candidates),
            },
        )


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
        if provider_name == "openai" and os.getenv("OPENAI_API_KEY"):
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
