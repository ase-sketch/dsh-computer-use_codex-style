"""Read parity/official-constants.json so the Python engine stops drifting (CW-10).

The Rust helper wires the same file through `include_str!` plus a compile-time
assert. This module is the Python half: read the value when the file is present,
and otherwise fall back to the same literal (never to a value that contradicts it).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        path = Path(__file__).resolve().parents[1] / "parity" / "official-constants.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _CACHE = data if isinstance(data, dict) else {}
    return _CACHE


def official_capture_value(key: str, default: Any) -> Any:
    capture = load().get("capture")
    if isinstance(capture, dict) and key in capture:
        return capture[key]
    return default


def jpeg_quality() -> float:
    return float(official_capture_value("jpegQuality", 0.8))


def cursor_capture() -> bool:
    return bool(official_capture_value("cursorCapture", True))


def frame_pool_buffers() -> int:
    return int(official_capture_value("framePoolBuffers", 1))


__all__ = ["cursor_capture", "frame_pool_buffers", "jpeg_quality", "load", "official_capture_value"]
