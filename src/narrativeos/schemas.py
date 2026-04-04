from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jsonschema import Draft202012Validator, RefResolver


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "specs"


@lru_cache(maxsize=None)
def load_schema(name: str) -> Dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def get_validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    resolver = RefResolver(base_uri="%s/" % SCHEMA_DIR.resolve().as_uri(), referrer=schema)
    return Draft202012Validator(schema, resolver=resolver)


def validate_payload(payload: Dict[str, Any], schema_name: str) -> None:
    validator = get_validator(schema_name)
    validator.validate(payload)
