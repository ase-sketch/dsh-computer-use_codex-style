from __future__ import annotations

from computer_use.args import optional_float, optional_int, optional_str, require_text, window_from_spec
from computer_use.models import ActionRecord, AppInfo, Bounds, Observation, UINode, WindowRef
from computer_use.png import solid_png
from computer_use.tree_format import focused_line, format_tree
from computer_use.validate import outside_viewport_error, point_in_viewport


def default_nodes() -> list[UINode]:
    return [
        UINode(0, "Window", "Untitled - Notepad", Bounds(0, 0, 800, 600), depth=0),
        UINode(1, "Edit", "Text Editor", Bounds(8, 40, 784, 540), depth=1, actions=["SetValue"]),
        UINode(2, "Button", "Save", Bounds(16, 8, 64, 24), depth=1, actions=["Invoke"]),
    ]


class FakeDesktop:
    """In-memory desktop used by tests and CLI dry-run. Never moves the pointer."""

    def __init__(self) -> None:
        window = WindowRef(app="notepad.exe", id=1, title="Untitled - Notepad")
        self.window = window
        self.apps = [AppInfo("notepad.exe", "Notepad", True, [window])]
        self.nodes = default_nodes()
        self.screenshot = solid_png()
        self.actions: list[ActionRecord] = []
        self.focused_index = 1
        self.screenshot_ids: set[str] = set()
        self.next_shot = 0

    def list_apps(self) -> list[AppInfo]:
        return list(self.apps)

    def list_windows(self) -> list[WindowRef]:
        return [window for app in self.apps for window in app.windows]

    def get_window(self, spec: dict[str, object]) -> WindowRef:
        ident = optional_int(spec, "id")
        for window in self.list_windows():
            if window.id == ident:
                self.window = window
                return window
        raise KeyError(f"window id {ident} was not found")

    def launch_app(self, spec: dict[str, object]) -> ActionRecord:
        app_id = require_text(spec, "app")
        existing = next((app for app in self.apps if app.id == app_id), None)
        if existing is None:
            window = WindowRef(app=app_id, id=len(self.list_windows()) + 1, title=app_id)
            self.apps.append(AppInfo(app_id, app_id, True, [window]))
            self.window = window
        elif not existing.windows:
            window = WindowRef(app=app_id, id=len(self.list_windows()) + 1, title=app_id)
            existing.windows.append(window)
            existing.is_running = True
            self.window = window
        return self._record("launch_app", {"app": app_id})

    def observe(self, spec: dict[str, object]) -> Observation:
        include_shot = spec.get("include_screenshot", True) is not False
        include_text = spec.get("include_text", False) is True
        window = window_from_spec(spec) or self.window
        if window is not None and window.id:
            try:
                window = self.get_window({"id": window.id, "app": window.app})
            except KeyError:
                window = self.window
        shot_id = f"screenshot-{self.next_shot}"
        self.next_shot += 1
        if include_shot:
            self.screenshot_ids.add(shot_id)
        focused = self._node(self.focused_index)
        return Observation(
            screenshot=self.screenshot,
            mime_type="image/png",
            tree=list(self.nodes),
            window=window or self.window,
            tree_text=format_tree(self.nodes, self.window.title, self.window.app),
            focused_element=focused_line(focused),
            selected_text=focused.value,
            include_screenshot=include_shot,
            include_text=include_text,
            screenshot_id=shot_id,
            origin_x=0,
            origin_y=0,
            width=800,
            height=600,
        )

    def click(self, spec: dict[str, object]) -> ActionRecord:
        self._require_shot(spec)
        index = optional_int(spec, "element_index")
        if index is not None:
            return self._click_index(index, spec)
        x = optional_float(spec, "x")
        y = optional_float(spec, "y")
        if x is None or y is None:
            raise TypeError("click requires either element_index or finite x and y coordinates")
        if not point_in_viewport(x, y, 0, 0, 800, 600):
            raise ValueError(outside_viewport_error(x, y, 0, 0, 800, 600))
        return self._record("click", {"x": x, "y": y, **self._click_meta(spec)})

    def type_text(self, spec: dict[str, object]) -> ActionRecord:
        text = require_text(spec, "text")
        node = self._node(self.focused_index)
        node.value += text
        return self._record("type_text", {"text": text, "element_index": node.index})

    def press_key(self, spec: dict[str, object]) -> ActionRecord:
        return self._record("press_key", {"key": require_text(spec, "key")})

    def scroll(self, spec: dict[str, object]) -> ActionRecord:
        self._require_shot(spec)
        payload = {
            "x": optional_float(spec, "x"),
            "y": optional_float(spec, "y"),
            "scrollX": optional_float(spec, "scrollX"),
            "scrollY": optional_float(spec, "scrollY"),
            "screenshotId": optional_str(spec, "screenshotId"),
        }
        if payload["x"] is None or payload["y"] is None:
            raise TypeError("scroll requires x, y, scrollX, scrollY")
        return self._record("scroll", payload)

    def scroll_element(self, spec: dict[str, object]) -> ActionRecord:
        from computer_use.validate import scroll_element_args

        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        direction, pages = scroll_element_args(spec)
        node = self._node(index)
        return self._record(
            "scroll_element",
            {"element_index": index, "direction": direction, "pages": pages, "bounds": node.bounds.to_dict()},
        )

    def drag(self, spec: dict[str, object]) -> ActionRecord:
        self._require_shot(spec)
        payload = {
            "from_x": optional_float(spec, "from_x"),
            "from_y": optional_float(spec, "from_y"),
            "to_x": optional_float(spec, "to_x"),
            "to_y": optional_float(spec, "to_y"),
        }
        if None in payload.values():
            raise TypeError("drag requires from_x, from_y, to_x, to_y")
        return self._record("drag", payload)

    def set_value(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        value = require_text(spec, "value")
        node = self._node(index)
        node.value = value
        self.focused_index = index
        return self._record("set_value", {"element_index": index, "value": value, "bounds": node.bounds.to_dict()})

    def perform_secondary_action(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        action = require_text(spec, "action")
        node = self._node(index)
        return self._record("perform_secondary_action", {"element_index": index, "action": action, "bounds": node.bounds.to_dict()})

    def paste(self, spec: dict[str, object]) -> ActionRecord:
        text = require_text(spec, "text")
        node = self._node(self.focused_index)
        node.value += text
        return self._record("paste", {"text": text, "format": optional_str(spec, "format") or "text", "element_index": node.index})

    def select_text(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        node = self._node(index)
        text = require_text(spec, "text")
        self.focused_index = index
        return self._record("select_text", {"element_index": index, "text": text, "value": node.value})

    def activate_window(self, spec: dict[str, object]) -> ActionRecord:
        window = window_from_spec(spec) or self.window
        if window and window.id:
            self.window = self.get_window({"id": window.id, "app": window.app})
        return self._record("activate_window", {"window": (window or self.window).to_dict()})

    def _require_shot(self, spec: dict[str, object]) -> None:
        shot = optional_str(spec, "screenshotId")
        if shot is not None and shot not in self.screenshot_ids:
            raise KeyError(f"unknown screenshotId {shot}")

    def _click_index(self, index: int, spec: dict[str, object]) -> ActionRecord:
        node = self._node(index)
        x, y = node.bounds.center
        self.focused_index = index
        return self._record(
            str(spec.get("helper_method") or "click_element"),
            {"element_index": index, "bounds": node.bounds.to_dict(), "x": x, "y": y, **self._click_meta(spec)},
        )

    def _click_meta(self, spec: dict[str, object]) -> dict[str, object]:
        return {"click_count": optional_int(spec, "click_count") or 1, "mouse_button": optional_str(spec, "mouse_button") or "left"}

    def _node(self, index: int) -> UINode:
        for node in self.nodes:
            if node.index == index:
                return node
        raise KeyError(f"unknown element_index {index}")

    def _record(self, kind: str, payload: dict[str, object]) -> ActionRecord:
        record = ActionRecord(kind, payload)
        self.actions.append(record)
        return record
