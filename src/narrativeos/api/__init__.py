from __future__ import annotations

from typing import Any

from ..runtime_env import load_local_env
from .app_factory import create_app


_DEFAULT_APP = None


def _default_app():
    global _DEFAULT_APP
    if _DEFAULT_APP is None:
        load_local_env()
        _DEFAULT_APP = create_app()
    return _DEFAULT_APP


def __getattr__(name: str) -> Any:
    if name == "app":
        return _default_app()
    raise AttributeError(name)


__all__ = ["app", "create_app"]
