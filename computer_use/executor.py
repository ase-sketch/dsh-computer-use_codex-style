from __future__ import annotations

from typing import Any, Mapping

from computer_use.browser_api import BROWSER_TOOLS, BrowserSurface
from computer_use.driver import ComputerUse
from computer_use.mac_api import MAC_TOOLS, MacSurface
from computer_use.session import CuaSession
from computer_use.tools import WINDOW2_TOOLS, tool_names

ALIASES = {
    "observe": "get_window_state",
    "type": "type_text",
    "keypress": "press_key",
    "click_element": "click",
    "window": "get_window",
}

HARNESS_TOOLS = ("batch_actions", "session_note", "session_state", "end_turn", "diagnostic_state")
VOID_COMPUTER = frozenset(
    {
        "click",
        "type_text",
        "press_key",
        "scroll",
        "scroll_element",
        "drag",
        "set_value",
        "perform_secondary_action",
        "activate_window",
        "launch_app",
    }
)


class ToolExecutor:
    """Dispatch computer / mac / browser / harness tool calls."""

    def __init__(
        self,
        driver: ComputerUse,
        *,
        compact: bool = True,
        steal_focus: bool = True,
        browser: BrowserSurface | None = None,
    ) -> None:
        self.driver = driver
        self.compact = compact
        self.mac = MacSurface(driver, steal_focus=steal_focus)
        self.browser = browser or BrowserSurface()
        self.session = CuaSession()
        self.tool_names = set(tool_names()) | set(MAC_TOOLS) | set(BROWSER_TOOLS) | set(HARNESS_TOOLS) | set(ALIASES)

    def execute(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if name not in self.tool_names:
            raise KeyError(f"unknown tool {name}")
        spec = dict(arguments or {})
        canonical = ALIASES.get(name, name)
        if canonical == "get_window_state" and name == "observe":
            spec.setdefault("include_screenshot", True)
            spec.setdefault("include_text", False)
        result = self._dispatch(canonical, spec)
        if canonical in VOID_COMPUTER:
            result = None
        return {"name": name, "canonical": canonical, "result": result, "observation": None}

    def execute_call(self, call: Mapping[str, Any]) -> dict[str, Any]:
        name = str(call.get("name") or call.get("tool") or "")
        arguments = call.get("arguments") or call.get("args") or {}
        if not isinstance(arguments, Mapping):
            raise TypeError("arguments must be an object")
        return self.execute(name, arguments)

    def _dispatch(self, name: str, spec: dict[str, object]) -> Any:
        if name in BROWSER_TOOLS:
            return self.browser.dispatch(name, spec)
        if name == "get_app_state":
            return self._observe(self.mac.get_app_state(spec), spec)
        if name == "paste":
            return self.mac.paste(spec)
        if name == "select_text":
            return self.mac.select_text(spec)
        if name == "batch_actions":
            return self._batch(spec)
        if name == "session_note":
            self.session.note(str(spec.get("text") or ""))
            return self.session.snapshot()
        if name == "session_state":
            return self.session.snapshot()
        if name == "end_turn":
            return self._end_turn(spec)
        if name == "diagnostic_state":
            payload = {
                "backend": type(self.driver.backend).__name__,
                "lease": self.driver.lease.snapshot(),
                "overlay": self.driver.overlay.enabled,
            }
            getter = getattr(self.driver.backend, "diagnostic_state", None)
            if callable(getter):
                try:
                    extra = getter()
                    if isinstance(extra, dict):
                        payload.update(extra)
                except Exception:
                    pass
            return payload
        return self._computer(name, spec)

    def _end_turn(self, spec: dict[str, object]) -> dict[str, Any]:
        from computer_use.turn import bind_interrupt, signal_turn_ended, turn_ended_payload

        session_id = str(spec.get("session_id") or "local")
        turn_id = str(spec.get("turn_id") or "turn")
        bind_interrupt(self.driver.interrupt, session_id, turn_id)
        self.driver.interrupt.end_turn()
        self.driver.overlay.hide()
        ended = getattr(self.driver.backend, "end_turn", None)
        if callable(ended):
            try:
                return ended(session_id, turn_id)
            except TypeError:
                return ended()
        closer = getattr(self.driver.backend, "close", None)
        if callable(closer):
            closer()
        signal_turn_ended(session_id)
        try:
            from computer_use.notify_config import write_notify_config

            write_notify_config(session_id, turn_id)
        except OSError:
            pass
        return turn_ended_payload(session_id, turn_id)

    def _computer(self, name: str, spec: dict[str, object]) -> Any:
        table = {
            "list_apps": lambda: self.driver.list_apps(),
            "list_windows": lambda: self.driver.list_windows(),
            "get_window": lambda: self.driver.get_window(spec),
            "launch_app": lambda: self.driver.launch_app(spec),
            "get_window_state": lambda: self._observe(self.driver.get_window_state(spec), spec),
            "click": lambda: self._maybe_mac_click(spec),
            "type_text": lambda: self.driver.type_text(spec),
            "press_key": lambda: self.driver.press_key(spec),
            "scroll": lambda: self.driver.scroll(spec),
            "scroll_element": lambda: self.driver.scroll_element(spec),
            "drag": lambda: self.driver.drag(spec),
            "set_value": lambda: self.driver.set_value(spec),
            "perform_secondary_action": lambda: self.driver.perform_secondary_action(spec),
            "activate_window": lambda: self.driver.activate_window(spec),
        }
        if name not in table:
            raise KeyError(f"unhandled tool {name}")
        return table[name]()

    def _maybe_mac_click(self, spec: dict[str, object]) -> Any:
        if spec.get("app") and not spec.get("window"):
            return self.mac.click(spec)
        return self.driver.click(spec)

    def _observe(self, raw: dict[str, Any], spec: dict[str, object]) -> dict[str, Any]:
        if not self.compact:
            self.session.remember_shot(raw)
            self.session.state = raw
            return raw
        emit = spec.get("emit_image") is True
        disable_diff = spec.get("disableDiff", spec.get("disableDiffing", True)) is not False
        return self.session.present(raw, emit_image=emit, disable_diff=disable_diff)

    def _batch(self, spec: dict[str, object]) -> dict[str, Any]:
        actions = spec.get("actions") or []
        if not isinstance(actions, list):
            raise TypeError("actions must be an array")
        results = [self.execute_call(item) for item in actions if isinstance(item, Mapping)]
        then = str(spec.get("then") or "")
        refresh = None
        if then == "tab_ax_write":
            refresh = self.execute("tab_ax_write", {"tab_id": spec.get("tab_id"), "mode": spec.get("mode") or "state"})
        elif then == "get_window_state":
            args = spec.get("refresh_args") if isinstance(spec.get("refresh_args"), dict) else {}
            refresh = self.execute("get_window_state", args)
        return {"batched": len(results), "results": results, "refresh": refresh}


def official_tool_names() -> tuple[str, ...]:
    return WINDOW2_TOOLS
