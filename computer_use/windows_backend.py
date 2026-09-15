from __future__ import annotations

import os
import subprocess

from computer_use.args import optional_float, optional_int, optional_str, require_text, window_from_spec
from computer_use.errors import DesktopUnavailable
from computer_use.models import ActionRecord, AppInfo, Observation, UINode, WindowRef
from computer_use.tree_format import focused_line, format_accessibility
from computer_use.win_capture import CaptureFrame, capture_hwnd, is_minimized, window_rect
from computer_use.validate import COORDINATE_GEOMETRY_UNAVAILABLE, outside_viewport_error, point_in_viewport
from computer_use.user_assist import merge_usage, read_user_assist
from computer_use.wgc import scaled_size
from computer_use.win_dpi import dpi_scale, logical_to_physical, window_dpi
from computer_use.win_enum import enum_windows, list_apps_from_windows, user32
from computer_use.win_input import drag_points, move_click, press_chord, scroll_at, type_unicode, wait_ms
from computer_use.win_tree import dump_accessibility


def _frame_mime(frame) -> str:
    explicit = getattr(frame, "mime_type", None)
    if explicit:
        return str(explicit)
    data = getattr(frame, "png", b"") or b""
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


class WindowsDesktop:
    """Live Windows backend: UIA tree + screenshot + SendInput."""

    def __init__(self) -> None:
        self.actions: list[ActionRecord] = []
        self._nodes: list[UINode] = []
        self._window: WindowRef | None = None
        self._shots: dict[str, tuple] = {}
        self._next_shot = 0
        self._last_viewport: tuple | None = None

    def list_windows(self) -> list[WindowRef]:
        return enum_windows()

    def list_apps(self) -> list[AppInfo]:
        apps = list_apps_from_windows(self.list_windows())
        merge_usage(apps, read_user_assist())
        return apps

    def get_window(self, spec: dict[str, object]) -> WindowRef:
        return self._resolve_window(spec)

    def launch_app(self, spec: dict[str, object]) -> ActionRecord:
        app = require_text(spec, "app")
        try:
            os.startfile(app)  # type: ignore[attr-defined]
        except OSError:
            subprocess.Popen(app, shell=False)
        return self._store(ActionRecord("launch_app", {"app": app}))

    def activate_window(self, spec: dict[str, object]) -> ActionRecord:
        window = self._resolve_window(spec)
        user32.ShowWindow(window.id, 9)
        user32.SetForegroundWindow(window.id)
        self._window = window
        return self._store(ActionRecord("activate_window", {"window": window.to_dict()}))

    def observe(self, spec: dict[str, object]) -> Observation:
        include_shot = spec.get("include_screenshot", True) is not False
        include_text = spec.get("include_text", False) is True
        window = self._resolve_window(spec)
        if is_minimized(window.id):
            raise DesktopUnavailable(
                "window is minimized; call activate_window, refresh with get_window, then retry get_window_state"
            )
        timeout_ms = optional_int(spec, "max_duration_ms") or 800
        try:
            from computer_use.overlay_win import exclude_overlay_from_capture

            exclude_overlay_from_capture()
        except Exception:
            pass
        if include_shot:
            frame = capture_hwnd(window.id, timeout_ms=timeout_ms)
        else:
            left, top, width, height = window_rect(window.id)
            frame = CaptureFrame(b"", left, top, width, height, window_dpi(window.id), "image/jpeg")
        dpi = int(getattr(frame, "dpi", 96) or 96)
        scale = dpi_scale(dpi)
        logical_w, logical_h = scaled_size(frame.width, frame.height, dpi)
        origin = (float(frame.origin_x), float(frame.origin_y))
        nodes: list[UINode] = []
        tree_text = ""
        focused = ""
        selected_text = ""
        selected_elements: list[str] = []
        document_text = ""
        if include_text:
            try:
                dumped = dump_accessibility(window.id, window.title or "", origin=origin, scale=scale)
                nodes = dumped.nodes
                focused = dumped.focused or focused_line(nodes[0] if nodes else None)
                selected_text = dumped.selected_text
                selected_elements = list(dumped.selected_elements)
                document_text = dumped.document_text
                tree_text = format_accessibility(
                    nodes,
                    window.title or "",
                    window.app or "",
                    focused=focused,
                    selected_text=selected_text,
                    selected_elements=selected_elements,
                    document_text=document_text,
                )
            except Exception:
                nodes = []
                tree_text = ""
                focused = ""
        self._nodes = nodes
        self._window = window
        shot_id = f"screenshot-{self._next_shot}"
        self._next_shot += 1
        extra_screenshots: list[dict] = []
        if include_shot:
            self._shots[shot_id] = (frame.origin_x, frame.origin_y, logical_w, logical_h, scale)
            try:
                from computer_use.win_capture import screenshot_spaces

                spaces = screenshot_spaces(window.id)
                n = len(spaces)
                for i, (extra_hwnd, space_kind) in enumerate(spaces):
                    extra = capture_hwnd(extra_hwnd, timeout_ms=min(timeout_ms, 400))
                    extra_dpi = int(getattr(extra, "dpi", 96) or 96)
                    extra_scale = dpi_scale(extra_dpi)
                    ew, eh = scaled_size(extra.width, extra.height, extra_dpi)
                    eid = f"screenshot-{self._next_shot}"
                    self._next_shot += 1
                    self._shots[eid] = (extra.origin_x, extra.origin_y, ew, eh, extra_scale)
                    extra_bytes = extra.png
                    extra_mime = extra.mime_type if getattr(extra, "mime_type", None) else _frame_mime(extra)
                    import base64
                    from computer_use.win_capture import space_identity

                    record = space_identity(extra_hwnd, space=space_kind, snapshot=eid)
                    record.update(
                        {
                            "id": eid,
                            "zIndex": n - i,
                            "url": f"data:{extra_mime};base64,{base64.b64encode(extra_bytes).decode('ascii')}",
                            "originX": extra.origin_x,
                            "originY": extra.origin_y,
                            "width": ew,
                            "height": eh,
                            "nativeWidth": extra.width,
                            "nativeHeight": extra.height,
                            "space": space_kind,
                            "snapshot": eid,
                        }
                    )
                    extra_screenshots.append(record)
            except Exception:
                extra_screenshots = []
        self._last_viewport = (frame.origin_x, frame.origin_y, logical_w, logical_h, scale)
        space_meta: dict = {}
        if include_shot:
            try:
                from computer_use.win_capture import space_identity

                space_meta = space_identity(window.id, space="window", snapshot=shot_id)
            except Exception:
                space_meta = {}
        return Observation(
            screenshot=frame.png,
            mime_type=_frame_mime(frame),
            tree=nodes,
            window=window,
            tree_text=tree_text,
            focused_element=focused,
            selected_text=selected_text,
            selected_elements=selected_elements,
            document_text=document_text,
            include_screenshot=include_shot,
            include_text=include_text,
            screenshot_id=shot_id,
            origin_x=frame.origin_x,
            origin_y=frame.origin_y,
            width=logical_w,
            height=logical_h,
            native_width=frame.width,
            native_height=frame.height,
            dpi=int(getattr(frame, "dpi", 96) or 96),
            cache_diagnostics=self._cache_diagnostics(),
            extra_screenshots=extra_screenshots,
            space_meta=space_meta,
        )

    def click(self, spec: dict[str, object]) -> ActionRecord:
        record = self._click_record(spec)
        move_click(float(record.payload["x"]), float(record.payload["y"]), str(record.payload["mouse_button"]), int(record.payload["click_count"]))
        return self._store(record)

    def type_text(self, spec: dict[str, object]) -> ActionRecord:
        text = require_text(spec, "text")
        type_unicode(text)
        return self._store(ActionRecord("type_text", {"text": text}))

    def press_key(self, spec: dict[str, object]) -> ActionRecord:
        key = require_text(spec, "key")
        press_chord(key)
        return self._store(ActionRecord("press_key", {"key": key}))

    def scroll(self, spec: dict[str, object]) -> ActionRecord:
        if spec.get("element_index") is not None and spec.get("direction"):
            return self.scroll_element(spec)
        payload = self._scroll_live(spec)
        scroll_at(float(payload["x"]), float(payload["y"]), float(payload.get("scrollX") or 0), float(payload.get("scrollY") or 0))
        return self._store(ActionRecord("scroll", payload))

    def scroll_element(self, spec: dict[str, object]) -> ActionRecord:
        from computer_use.validate import scroll_element_args

        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        direction, pages = scroll_element_args(spec)
        node = self._node(index)
        origin_x, origin_y, _w, _h, scale = self._viewport(spec)
        applied = False
        if self._window is not None:
            try:
                from computer_use.win_uia import apply_scroll_pages

                apply_scroll_pages(self._window.id, index, direction, pages, origin=(origin_x, origin_y), scale=scale)
                applied = True
            except OSError as exc:
                if "no longer matches the cached runtime ID" in str(exc) or "no longer exposes" in str(exc):
                    raise
                applied = False
            except Exception:
                applied = False
        if not applied:
            lx, ly = node.bounds.center
            px, py = logical_to_physical(lx, ly, origin_x, origin_y, scale)
            delta = 600 * pages
            sx, sy = 0.0, 0.0
            if direction == "up":
                sy = -delta
            elif direction == "down":
                sy = delta
            elif direction == "left":
                sx = -delta
            else:
                sx = delta
            scroll_at(px, py, sx, sy)
        return self._store(
            ActionRecord(
                "scroll_element",
                {"element_index": index, "direction": direction, "pages": pages, "bounds": node.bounds.to_dict()},
            )
        )

    def drag(self, spec: dict[str, object]) -> ActionRecord:
        from_x = optional_float(spec, "from_x")
        from_y = optional_float(spec, "from_y")
        to_x = optional_float(spec, "to_x")
        to_y = optional_float(spec, "to_y")
        if None in (from_x, from_y, to_x, to_y):
            raise TypeError("drag requires from_x, from_y, to_x, to_y")
        origin_x, origin_y, width, height, scale = self._viewport(spec)
        for px, py in ((from_x, from_y), (to_x, to_y)):
            if not point_in_viewport(px, py, 0, 0, width, height):
                raise ValueError(outside_viewport_error(px, py, origin_x, origin_y, width, height))
        x1, y1 = logical_to_physical(from_x, from_y, origin_x, origin_y, scale)
        x2, y2 = logical_to_physical(to_x, to_y, origin_x, origin_y, scale)
        drag_points(x1, y1, x2, y2)
        return self._store(
            ActionRecord(
                "drag",
                {"from_x": x1, "from_y": y1, "to_x": x2, "to_y": y2, "logical_from_x": from_x, "logical_from_y": from_y, "logical_to_x": to_x, "logical_to_y": to_y},
            )
        )

    def set_value(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        value = require_text(spec, "value")
        node = self._node(index)
        origin_x, origin_y, _w, _h, scale = self._viewport(spec)
        applied = False
        if self._window is not None:
            try:
                from computer_use.win_uia import apply_value

                apply_value(self._window.id, index, value, origin=(origin_x, origin_y), scale=scale)
                applied = True
            except TypeError:
                raise
            except OSError as exc:
                if "no longer matches the cached runtime ID" in str(exc) or "not settable" in str(exc):
                    raise
                applied = False
            except Exception:
                applied = False
        if not applied:
            lx, ly = node.bounds.center
            px, py = logical_to_physical(lx, ly, origin_x, origin_y, scale)
            move_click(px, py, "left", 1)
            type_unicode(value)
        return self._store(ActionRecord("set_value", {"element_index": index, "value": value, "bounds": node.bounds.to_dict()}))

    def perform_secondary_action(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        if index is None:
            raise TypeError("element_index is required")
        action = require_text(spec, "action")
        node = self._node(index)
        if not node.actions:
            raise KeyError(f"element {index} has no cached secondary actions for {action}")
        if self._window is not None:
            origin_x, origin_y, _w, _h, scale = self._viewport(spec)
            try:
                from computer_use.win_uia import apply_secondary_action

                apply_secondary_action(self._window.id, index, action, origin=(origin_x, origin_y), scale=scale)
            except (OSError, KeyError, TypeError):
                raise
            except Exception:
                pass
        return self._store(ActionRecord("perform_secondary_action", {"element_index": index, "action": action, "bounds": node.bounds.to_dict()}))

    def wait(self, spec: dict[str, object]) -> ActionRecord:
        duration = optional_int(spec, "duration_ms") or 500
        wait_ms(duration)
        return self._store(ActionRecord("wait", {"duration_ms": duration}))

    def _resolve_window(self, spec: dict[str, object]) -> WindowRef:
        hinted = window_from_spec(spec)
        windows = self.list_windows()
        if hinted is not None:
            matched = self._match(windows, hinted)
            if matched is not None:
                return matched
        if not windows:
            raise DesktopUnavailable("no targetable windows")
        return windows[0]

    def _match(self, windows: list[WindowRef], hinted: WindowRef) -> WindowRef | None:
        for window in windows:
            if hinted.id and window.id == hinted.id:
                return window
            if hinted.app.lower() in (window.app.lower(), window.title.lower()):
                return window
        needle = hinted.app.lower()
        for window in windows:
            if needle in window.app.lower() or needle in window.title.lower():
                return window
        return None

    def _click_record(self, spec: dict[str, object]) -> ActionRecord:
        index = optional_int(spec, "element_index")
        button = optional_str(spec, "mouse_button") or "left"
        count = optional_int(spec, "click_count") or 1
        if index is not None:
            node = self._node(index)
            if node.bounds.width <= 0 and node.bounds.height <= 0:
                raise KeyError(f"element {index} has no cached bounds")
            lx, ly = node.bounds.center
            origin_x, origin_y, _w, _h, scale = self._viewport(spec)
            px, py = logical_to_physical(lx, ly, origin_x, origin_y, scale)
            return ActionRecord(
                str(spec.get("helper_method") or "click_element"),
                {
                    "element_index": index,
                    "bounds": node.bounds.to_dict(),
                    "x": px,
                    "y": py,
                    "logical_x": lx,
                    "logical_y": ly,
                    "mouse_button": button,
                    "click_count": count,
                },
            )
        x = optional_float(spec, "x")
        y = optional_float(spec, "y")
        if x is None or y is None:
            raise TypeError("click requires either element_index or finite x and y coordinates")
        origin_x, origin_y, width, height, scale = self._viewport(spec)
        if not point_in_viewport(x, y, 0, 0, width, height):
            raise ValueError(outside_viewport_error(x, y, origin_x, origin_y, width, height))
        px, py = logical_to_physical(x, y, origin_x, origin_y, scale)
        return ActionRecord(
            "click",
            {"x": px, "y": py, "logical_x": x, "logical_y": y, "mouse_button": button, "click_count": count},
        )

    def _scroll_live(self, spec: dict[str, object]) -> dict[str, object]:
        index = optional_int(spec, "element_index")
        origin_x, origin_y, width, height, scale = self._viewport(spec)
        if index is not None:
            node = self._node(index)
            lx, ly = node.bounds.center
            px, py = logical_to_physical(lx, ly, origin_x, origin_y, scale)
            return {
                "element_index": index,
                "bounds": node.bounds.to_dict(),
                "x": px,
                "y": py,
                "logical_x": lx,
                "logical_y": ly,
                "scrollX": optional_float(spec, "scrollX") or 0,
                "scrollY": optional_float(spec, "scrollY") or 600,
            }
        x = optional_float(spec, "x") or 0
        y = optional_float(spec, "y") or 0
        if not point_in_viewport(x, y, 0, 0, width, height):
            raise ValueError(outside_viewport_error(x, y, origin_x, origin_y, width, height))
        px, py = logical_to_physical(x, y, origin_x, origin_y, scale)
        return {
            "x": px,
            "y": py,
            "logical_x": x,
            "logical_y": y,
            "scrollX": optional_float(spec, "scrollX") or 0,
            "scrollY": optional_float(spec, "scrollY") or 0,
        }

    def _viewport(self, spec: dict[str, object]) -> tuple[float, float, float, float, float]:
        shot = optional_str(spec, "screenshotId")
        if shot is not None:
            cached = self._shots.get(shot)
            if cached is None:
                raise KeyError(f"unknown screenshotId {shot}")
            if len(cached) == 4:
                ox, oy, w, h = cached
                return float(ox), float(oy), float(w), float(h), 1.0
            ox, oy, w, h, scale = cached
            return float(ox), float(oy), float(w), float(h), float(scale)
        last = getattr(self, "_last_viewport", None)
        if last is not None:
            ox, oy, w, h, scale = last
            return float(ox), float(oy), float(w), float(h), float(scale)
        raise DesktopUnavailable(COORDINATE_GEOMETRY_UNAVAILABLE)

    def _node(self, index: int) -> UINode:
        for node in self._nodes:
            if node.index == index:
                return node
        raise KeyError(f"element {index} has no cached bounds")

    def diagnostic_state(self) -> dict[str, object]:
        payload = self._cache_diagnostics()
        window = self._window
        hwnd = int(window.id) if window is not None else 0
        payload["appId"] = window.app if window is not None else ""
        payload["rootHwnd"] = hwnd
        try:
            from computer_use.notify_config import feature_status

            payload["feature_status"] = feature_status()
            payload["notify"] = True
        except Exception:
            payload["notify"] = True
        try:
            from computer_use.policy import hwnd_pid, process_aumid

            pid = hwnd_pid(hwnd)
            payload["processId"] = pid
            payload["inputHwnd"] = int(user32.GetForegroundWindow() or 0)
            payload["aumid"] = process_aumid(pid)
        except Exception:
            payload.setdefault("processId", 0)
            payload.setdefault("inputHwnd", 0)
        if window is not None:
            try:
                left, top, width, height = window_rect(hwnd)
                payload["bounds"] = {"x": left, "y": top, "width": width, "height": height}
            except Exception:
                pass
        return payload

    def _cache_diagnostics(self) -> dict[str, object]:
        try:
            from computer_use.win_uia import cache_diagnostics

            payload = dict(cache_diagnostics())
        except Exception:
            payload = {}
        if self._window is not None:
            payload.setdefault("appId", self._window.app)
            payload.setdefault("rootHwnd", self._window.id)
        try:
            from computer_use.wgc_winrt import cached_session_count, last_capture_invalidation

            payload["captureCachedSessionCount"] = cached_session_count()
            reason = last_capture_invalidation()
            if reason:
                payload["lastCaptureInvalidationReason"] = reason
        except Exception:
            payload.setdefault("captureCachedSessionCount", payload.get("captureCachedSessionCount") or 0)
        return payload

    def _store(self, record: ActionRecord) -> ActionRecord:
        self.actions.append(record)
        return record
