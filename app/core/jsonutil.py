"""JSON helpers that avoid scientific notation in float output."""

from __future__ import annotations

import json
import re
from typing import Any

_FLOAT_TOKEN = re.compile(r'"__f__:(-?\d+(?:\.\d+)?)__"')


def _format_float(value: float) -> str:
    if value != value:  # NaN
        return "0"
    if value == 0:
        return "0"
    text = format(value, ".12f").rstrip("0").rstrip(".")
    return text or "0"


def _mark_floats(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return f"__f__:{_format_float(value)}__"
    if isinstance(value, dict):
        return {key: _mark_floats(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mark_floats(item) for item in value]
    return value


def dumps_plain(value: Any) -> str:
    """Serialize JSON with decimal floats (never 8e-05 style)."""
    encoded = json.dumps(_mark_floats(value), separators=(",", ":"), ensure_ascii=False)
    return _FLOAT_TOKEN.sub(r"\1", encoded)
