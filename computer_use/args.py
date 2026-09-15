from __future__ import annotations

from typing import Any

from computer_use.models import WindowRef


def as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"{name} must be an integer")
    if isinstance(value, str) and value.strip() == "":
        raise TypeError(f"{name} must be an integer")
    number = int(float(value))
    if number < 0:
        raise TypeError(f"{name} must be >= 0")
    return number


def as_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"{name} must be a finite number")
    number = float(value)
    if number != number:  # NaN
        raise TypeError(f"{name} must be a finite number")
    return number


def optional_int(spec: dict[str, object], key: str) -> int | None:
    if key not in spec or spec[key] is None:
        return None
    return as_int(spec[key], key)


def optional_float(spec: dict[str, object], key: str) -> float | None:
    if key not in spec or spec[key] is None:
        return None
    return as_float(spec[key], key)


def optional_str(spec: dict[str, object], key: str) -> str | None:
    value = spec.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def window_from_spec(spec: dict[str, object]) -> WindowRef | None:
    raw = spec.get("window")
    if isinstance(raw, dict):
        app = str(raw.get("app") or spec.get("app") or "").strip()
        ident = raw.get("id", 0)
        title = str(raw.get("title") or "")
        if not app:
            return None
        return WindowRef(app=app, id=as_int(ident, "window.id"), title=title)
    app = optional_str(spec, "app")
    if app is None:
        return None
    return WindowRef(app=app, id=0, title="")


def require_text(spec: dict[str, object], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or value == "":
        raise TypeError(f"{key} is required")
    return value


def payload_bounds(bounds: Any) -> dict[str, float]:
    return bounds.to_dict()
