from __future__ import annotations

from typing import Any

from computer_use.browser_api import browser_tool_definitions
from computer_use.browser_official import official_tool_definitions
from computer_use.mac_api import mac_tool_definitions
from computer_use.tools import _obj, _str, _tool, tool_definitions


def harness_tool_definitions() -> list[dict[str, Any]]:
    return [
        _tool(
            "batch_actions",
            "Run several UI actions then one refresh (browser AX batch or computer two-cell refresh).",
            _obj(
                {
                    "actions": {"type": "array", "items": {"type": "object"}, "description": "{name, arguments} calls"},
                    "then": _str("tab_ax_write or get_window_state"),
                    "tab_id": _str("Tab id when then=tab_ax_write"),
                    "refresh_args": {"type": "object"},
                },
                ["actions"],
            ),
        ),
        _tool("session_note", "Append cross-step internal harness notes (not user-visible).", _obj({"text": _str("Note")}, ["text"])),
        _tool("session_state", "Return persisted handles, screenshot ids, and reasoning notes.", _obj({})),
        _tool(
            "end_turn",
            "End the Computer Use turn (official Interrupt/Stop: helper end_turn + Local\\CodexComputerUseTurnEnded-*).",
            _obj({"session_id": _str("Codex session id"), "turn_id": _str("Codex turn id")}),
        ),
        _tool("diagnostic_state", "Helper diagnostic_state: backend, DPI, overlay, lease, approved apps.", _obj({})),
    ]


def tools_for_surface(surface: str, disabled: list[str] | None = None) -> list[dict[str, Any]]:
    if surface == "computer":
        return tool_definitions()
    if surface == "gated":
        return tool_definitions() + harness_tool_definitions()
    if surface == "mac":
        return tool_definitions() + mac_tool_definitions()
    if surface == "browser":
        return official_tool_definitions(disabled)
    if surface == "desktop":
        return tool_definitions() + harness_tool_definitions()
    if surface == "all":
        return tool_definitions() + mac_tool_definitions() + browser_tool_definitions() + harness_tool_definitions()
    raise KeyError(surface)
