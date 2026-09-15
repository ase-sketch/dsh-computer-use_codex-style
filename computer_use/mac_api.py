"""macOS window API (sky.window) recovered from sky-window-api.md.

target=mac: app string, get_app_state, paste/select_text, scroll by direction,
default do not steal focus (AXPress-style). On Windows this maps onto window2
without activate_window unless steal_focus is true.
"""

from __future__ import annotations

from typing import Any

from computer_use.driver import ComputerUse
from computer_use.tools import _obj, _str, _int, _tool


MAC_TOOLS = (
    "get_app_state",
    "paste",
    "select_text",
)


def mac_tool_definitions() -> list[dict[str, Any]]:
    app = _str("App id, display name, or process name from list_apps()")
    return [
        _tool(
            "get_app_state",
            "Capture screenshot + accessibility text for an app window (mac window API). Maps to get_window_state.",
            _obj({"app": app, "disableDiff": {"type": "boolean", "description": "Return a full tree instead of a diff."}}, ["app"]),
        ),
        _tool(
            "paste",
            "Paste content into the app focus, then restore the previous clipboard (mac window API).",
            _obj({"app": app, "text": _str("Content to paste"), "format": {"type": "string", "enum": ["text", "md", "html"]}}, ["app", "text"]),
        ),
        _tool(
            "select_text",
            "Select matching text in an indexed editable element (mac window API).",
            _obj(
                {
                    "app": app,
                    "element_index": _int("Element index from get_app_state"),
                    "text": _str("Text to locate"),
                    "prefix": _str("Disambiguating prefix"),
                    "suffix": _str("Disambiguating suffix"),
                    "selection_type": {"type": "string", "enum": ["text", "cursor_before", "cursor_after"]},
                },
                ["app", "element_index", "text"],
            ),
        ),
    ]


class MacSurface:
    def __init__(self, driver: ComputerUse, steal_focus: bool = False) -> None:
        self.driver = driver
        self.steal_focus = steal_focus
        self.background_clicks = 0

    def resolve(self, app: str) -> dict[str, Any]:
        needle = app.lower()
        for item in self.driver.list_apps():
            blob = f"{item.get('id', '')} {item.get('displayName', '')}".lower()
            if needle in blob:
                windows = list(item.get("windows") or [])
                if windows:
                    return windows[0]
        windows = self.driver.list_windows()
        if windows:
            return windows[0]
        raise LookupError(f"no window for app {app}")

    def bind(self, spec: dict[str, object]) -> dict[str, object]:
        payload = dict(spec)
        if "window" not in payload:
            app = str(spec.get("app") or "")
            payload["window"] = self.resolve(app)
        if self.steal_focus:
            self.driver.activate_window({"window": payload["window"]})
        else:
            self.background_clicks += 1
        return payload

    def get_app_state(self, spec: dict[str, object]) -> dict[str, Any]:
        window = self.resolve(str(spec.get("app") or ""))
        return self.driver.get_window_state(
            {"window": window, "include_screenshot": True, "include_text": True}
        )

    def click(self, spec: dict[str, object]) -> dict[str, Any]:
        return self.driver.click(self.bind(spec))

    def paste(self, spec: dict[str, object]) -> dict[str, Any]:
        return self.driver.paste(self.bind(spec))

    def select_text(self, spec: dict[str, object]) -> dict[str, Any]:
        return self.driver.select_text(self.bind(spec))
