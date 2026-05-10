from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATHS = (
    ROOT_DIR / ".env.local",
    ROOT_DIR / ".env",
)

_DEFAULT_ENV_LOADED = False


def _parse_env_line(raw_line: str) -> Optional[tuple[str, str]]:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export "):].strip()
    key, value = line.split("=", 1)
    normalized_key = key.strip()
    if not normalized_key:
        return None
    normalized_value = value.strip().strip('"').strip("'")
    return normalized_key, normalized_value


def load_local_env(
    *,
    env_paths: Optional[Iterable[Path]] = None,
    override_existing: bool = False,
) -> Dict[str, str]:
    global _DEFAULT_ENV_LOADED

    using_default_paths = env_paths is None
    if using_default_paths and _DEFAULT_ENV_LOADED and not override_existing:
        return {}

    resolved_paths = list(env_paths or DEFAULT_ENV_PATHS)
    loaded: Dict[str, str] = {}
    for path in resolved_paths:
        if not Path(path).exists():
            continue
        for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            if override_existing or key not in os.environ:
                os.environ[key] = value
                loaded[key] = value

    if using_default_paths and not override_existing:
        _DEFAULT_ENV_LOADED = True
    return loaded


def describe_env_sources(*, env_paths: Optional[Iterable[Path]] = None) -> List[str]:
    return [str(path) for path in list(env_paths or DEFAULT_ENV_PATHS)]
