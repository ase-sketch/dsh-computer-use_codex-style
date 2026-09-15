from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Bounds:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class UINode:
    index: int
    role: str
    name: str
    bounds: Bounds
    value: str = ""
    depth: int = 0
    actions: list[str] = field(default_factory=list)
    automation_id: str = ""
    description: str = ""
    states: list[str] = field(default_factory=list)
    focused: bool = False
    runtime_id: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "index": self.index,
            "role": self.role,
            "name": self.name,
            "label": self.name,
            "bounds": self.bounds.to_dict(),
            "value": self.value,
            "actions": list(self.actions),
        }
        if self.automation_id:
            payload["automationId"] = self.automation_id
        if self.description:
            payload["description"] = self.description
        if self.states:
            payload["states"] = list(self.states)
        if self.focused:
            payload["focused"] = True
        return payload


@dataclass
class WindowRef:
    app: str
    id: int
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {"app": self.app, "id": self.id}
        if self.title:
            data["title"] = self.title
        return data


@dataclass
class AppInfo:
    id: str
    display_name: str
    is_running: bool = True
    windows: list[WindowRef] = field(default_factory=list)
    last_used_date: str | None = None
    use_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "displayName": self.display_name,
            "isRunning": self.is_running,
            "windows": [window.to_dict() for window in self.windows],
        }
        if self.last_used_date is not None:
            payload["lastUsedDate"] = self.last_used_date
        if self.use_count is not None:
            payload["useCount"] = self.use_count
        return payload


@dataclass
class ActionRecord:
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.payload}


@dataclass
class Observation:
    screenshot: bytes
    mime_type: str
    tree: list[UINode]
    window: WindowRef
    tree_text: str
    focused_element: str = ""
    selected_text: str = ""
    selected_elements: list[str] = field(default_factory=list)
    document_text: str = ""
    include_screenshot: bool = True
    include_text: bool = False
    screenshot_id: str = "screenshot-0"
    origin_x: int = 0
    origin_y: int = 0
    width: int = 0
    height: int = 0
    native_width: int = 0
    native_height: int = 0
    dpi: int = 96
    cache_diagnostics: dict[str, Any] = field(default_factory=dict)
    extra_screenshots: list[dict[str, Any]] = field(default_factory=list)
    space_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        encoded = base64.b64encode(self.screenshot).decode("ascii")
        screenshots: list[dict[str, Any]] = []
        if self.include_screenshot:
            native_w = self.native_width or self.width
            native_h = self.native_height or self.height
            screenshots = [
                {
                    "id": self.screenshot_id,
                    "zIndex": 0,
                    "url": f"data:{self.mime_type};base64,{encoded}",
                    "originX": self.origin_x,
                    "originY": self.origin_y,
                    "width": self.width,
                    "height": self.height,
                    "nativeWidth": native_w,
                    "nativeHeight": native_h,
                    "logicalWidth": self.width,
                    "logicalHeight": self.height,
                    "dpi": self.dpi,
                    "scale": round(self.dpi / 96.0, 4),
                    "space": "window",
                    "windowID": self.window.id,
                    "displayName": self.window.title,
                    "processKey": f"exe:{self.window.app}:{self.window.id}",
                    "app": self.window.app,
                    "identity": f"exe:{self.window.app}:{self.window.id}|{self.window.id}",
                    "display": "",
                    "snapshot": self.screenshot_id,
                }
            ]
            for extra in self.extra_screenshots:
                screenshots.append(dict(extra))
            if self.space_meta and screenshots:
                identity_keys = (
                    "space",
                    "windowID",
                    "displayName",
                    "processKey",
                    "app",
                    "identity",
                    "display",
                    "snapshot",
                    "revision",
                )
                screenshots[0].update({k: v for k, v in self.space_meta.items() if k in identity_keys})
        accessibility = None
        if self.include_text:
            accessibility = {
                "tree": self.tree_text,
                "focused_element": self.focused_element,
                "selected_text": self.selected_text,
                "selected_elements": list(self.selected_elements),
                "document_text": self.document_text,
            }
        payload: dict[str, Any] = {
            "window": self.window.to_dict(),
            "screenshots": screenshots,
            "accessibility": accessibility,
            "screenshot_mime": self.mime_type,
            "screenshot_bytes": len(self.screenshot) if self.include_screenshot else 0,
            "screenshot_base64": encoded if self.include_screenshot else "",
            "tree": [node.to_dict() for node in self.tree] if self.include_text else [],
        }
        if self.cache_diagnostics:
            payload["cacheDiagnostics"] = dict(self.cache_diagnostics)
        if screenshots:
            spaces = [
                {
                    "id": shot.get("id"),
                    "zIndex": shot.get("zIndex", 0),
                    "originX": shot.get("originX"),
                    "originY": shot.get("originY"),
                    "width": shot.get("width"),
                    "height": shot.get("height"),
                    "nativeWidth": shot.get("nativeWidth"),
                    "nativeHeight": shot.get("nativeHeight"),
                    "space": shot.get("space") or "window",
                    "windowID": shot.get("windowID"),
                    "displayName": shot.get("displayName"),
                    "processKey": shot.get("processKey"),
                    "app": shot.get("app"),
                    "identity": shot.get("identity"),
                    "display": shot.get("display"),
                    "snapshot": shot.get("snapshot") or shot.get("id"),
                    "bounds": shot.get("bounds"),
                }
                for shot in screenshots
            ]
            payload["spaces"] = spaces
            payload["screenshotSpaces"] = spaces
            payload["rootScreenshotID"] = self.screenshot_id
        return payload
