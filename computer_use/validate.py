from __future__ import annotations

from typing import Any


def require_state_flags(spec: dict[str, object]) -> tuple[bool, bool]:
    include_shot = spec.get("include_screenshot", True) is not False
    include_text = spec.get("include_text", False) is True
    if not include_shot and not include_text:
        raise TypeError("get_window_state must request include_text, include_screenshot, or both")
    return include_shot, include_text


def finite_round(value: object, name: str) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a finite number")
    number = float(value)
    if number != number:
        raise TypeError(f"{name} must be a finite number")
    return int(round(number))


def click_count(spec: dict[str, object]) -> int:
    raw = spec.get("click_count", 1)
    count = finite_round(raw if raw is not None else 1, "click_count")
    if count < 1:
        raise TypeError("click_count must be >= 1")
    return count


def element_index(spec: dict[str, object]) -> int | None:
    for key in ("element_index", "elementIndex", "element"):
        if key in spec and spec[key] is not None:
            value = spec[key]
            if isinstance(value, str) and value.strip() != "":
                value = int(value)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise TypeError("element_index must be an integer >= 0")
            return value
    return None


def point_in_viewport(x: float, y: float, origin_x: float, origin_y: float, width: float, height: float) -> bool:
    return origin_x <= x < origin_x + width and origin_y <= y < origin_y + height


def _debug_f64(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return f"{number:.1f}"
    return str(number)


def _display_f64(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


COORDINATE_GEOMETRY_UNAVAILABLE = "coordinate input geometry is unavailable"
WINDOW_BOUNDS_UNAVAILABLE_COORD = "window bounds unavailable for coordinate input"
NO_SCREENSHOT_TARGETS_FOR = "no screenshot targets found for "
WINDOW_BOUNDS_UNAVAILABLE_FOR = "window bounds unavailable for "


def no_screenshot_targets_error(window: object) -> str:
    return f"{NO_SCREENSHOT_TARGETS_FOR}{window}"


def screenshot_targets_missing(screenshot_id: str, window: object) -> str:
    return f"{screenshot_id} no screenshot targets found for {window}"


def window_bounds_unavailable_error(window: object) -> str:
    return f"{WINDOW_BOUNDS_UNAVAILABLE_FOR}{window}"


def outside_viewport_error(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
) -> str:
    """Official helper: point (x, y) is outside viewport { originX, originY, width, height }."""
    return (
        f"point ({_debug_f64(x)}, {_debug_f64(y)}) is outside viewport "
        f"{{ originX: {_display_f64(origin_x)}, originY: {_display_f64(origin_y)}, "
        f"width: {_display_f64(width)}, height: {_display_f64(height)} }}"
    )


def secondary_action(name: str) -> str:
    aliases = {
        "raise": "Raise",
        "scroll up": "Scroll Up",
        "scroll down": "Scroll Down",
        "scroll left": "Scroll Left",
        "scroll right": "Scroll Right",
        "expand": "Expand",
        "collapse": "Collapse",
    }
    key = name.strip().lower()
    return aliases.get(key, name.strip())


SCROLL_DIRECTIONS = ("up", "down", "left", "right")


def scroll_element_args(spec: dict[str, object]) -> tuple[str, int]:
    """Official helper scroll_element: direction + pages (finite > 0)."""
    raw = spec.get("direction")
    direction = str(raw or "").strip().lower()
    if direction not in SCROLL_DIRECTIONS:
        raise TypeError(f"unsupported scroll direction: {raw}")
    pages = spec.get("pages", 1)
    if isinstance(pages, bool) or not isinstance(pages, (int, float)):
        raise TypeError("pages must be a finite number > 0")
    value = float(pages)
    if value != value or value <= 0:
        raise TypeError("pages must be a finite number > 0")
    return direction, int(round(value))


def screenshot_meta(spec: dict[str, Any], origin_x: int, origin_y: int, width: int, height: int) -> dict[str, Any]:
    return {
        "id": spec.get("id") or "screenshot-0",
        "zIndex": int(spec.get("zIndex") or 0),
        "originX": origin_x,
        "originY": origin_y,
        "width": width,
        "height": height,
    }
