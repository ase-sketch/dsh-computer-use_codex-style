"""Official command classification and response-meta contribution (BR-21).

Recovered from `browser-service.mjs`:

* offsets 1135711 (`JJ`, the 28 mutating commands) and 1136707 (`YJ`, the 15
  read-only commands). `BB().recordCommand` only records on success; the last
  mutating command (or, for the cdp backend, the last read-only command) becomes
  `takeResponseMetaContribution()`.
* BR-21 notifications: the after-submitted-code hook `qB()` @1143565 returns
  `Browser notifications:\n\n` + the drained items joined by a blank line, or
  `""` when there is nothing; the sole contributor `sY=[_k]` @679616 lists the
  page-defined WebMCP tools; the page-event discriminant
  `zx={type:"webmcp_changed",version:1}` @241933; the tab lifecycle events
  `tab_created` / `tab_acquired` @1125570.
"""

from __future__ import annotations

import json
from typing import Any, Callable

#: `JJ` -- commands that change page or browser state (28).
MUTATING_COMMANDS = frozenset(
    {
        "close_tab",
        "cua_click",
        "cua_double_click",
        "cua_drag",
        "cua_keypress",
        "cua_move",
        "cua_scroll",
        "cua_type",
        "dom_cua_click",
        "dom_cua_double_click",
        "dom_cua_download_media",
        "dom_cua_keypress",
        "dom_cua_scroll",
        "dom_cua_type",
        "navigate_tab_back",
        "navigate_tab_forward",
        "navigate_tab_reload",
        "navigate_tab_url",
        "playwright_locator_click",
        "playwright_locator_dblclick",
        "playwright_locator_download_media",
        "playwright_locator_fill",
        "playwright_locator_press",
        "playwright_locator_press_sequentially",
        "playwright_locator_select_option",
        "playwright_locator_set_checked",
        "tab_ax_action",
        "tab_handle_js_dialog",
    }
)

#: `YJ` -- commands that only read (15).
READ_ONLY_COMMANDS = frozenset(
    {
        "dom_cua_get_visible_dom",
        "playwright_dom_snapshot",
        "playwright_evaluate",
        "playwright_locator_all_text_contents",
        "playwright_locator_count",
        "playwright_locator_get_attribute",
        "playwright_locator_inner_text",
        "playwright_locator_is_enabled",
        "playwright_locator_is_visible",
        "playwright_locator_read_all",
        "playwright_locator_text_content",
        "tab_ax_get_state",
        "tab_page_assets_list",
        "tab_screenshot",
        "webmcp_list_tools",
    }
)

#: The backend whose last read-only command also contributes meta.
CDP_BACKEND = "cdp"


def contributes_response_meta(name: str, *, backend: str = "") -> bool:
    if name in MUTATING_COMMANDS:
        return True
    return backend == CDP_BACKEND and name in READ_ONLY_COMMANDS


def response_meta_contribution(names: list[str], *, backend: str = "") -> dict[str, object] | None:
    """Official selection: the *last* mutating command, or the last read-only one
    for the cdp backend. Returns None when nothing qualifies (never called)."""
    for name in reversed(names):
        if contributes_response_meta(name, backend=backend):
            return {"commandType": name}
    return None



# --- Browser notifications (BR-21) -------------------------------------------

#: Official qB() wrapper (browser-service.mjs @1143565). The host appends this
#: as a response content item and omits it entirely when nothing was drained.
BROWSER_NOTIFICATIONS_HEADER = "Browser notifications:"
BROWSER_NOTIFICATIONS_PREFIX = BROWSER_NOTIFICATIONS_HEADER + "\n\n"

#: Official E7/A7 sentences.
WEBMCP_TOOLS_AVAILABLE = "WebMCP tools are available in tab {tab_id}:"
WEBMCP_TOOLS_GONE = "WebMCP tools are no longer available in tab {tab_id}."
WEBMCP_JSON_FENCE = "```json"

#: Official page-event discriminant (zx = {type:"webmcp_changed",version:1}).
WEBMCP_CHANGED = "webmcp_changed"
WEBMCP_CHANGED_VERSION = 1

#: Official tab lifecycle events (tabLifecycle.recordCreated/recordAcquired).
TAB_CREATED = "tab_created"
TAB_ACQUIRED = "tab_acquired"
AGENT_ORIGIN = "agent"
EXTERNAL_ORIGIN = "external"


def format_browser_notifications(items: list[str] | None) -> str:
    """Official qB(): header, blank line, items joined by a blank line, trailing LF.

    Returns "" (not an empty header) when there is nothing to report, which is
    exactly the official behaviour and why callers can use truthiness.
    """
    cleaned = [str(item) for item in (items or []) if item]
    if not cleaned:
        return ""
    return BROWSER_NOTIFICATIONS_PREFIX + "\n\n".join(cleaned) + "\n"


def webmcp_changed_tab_ids(page_events: list[dict[str, Any]] | None) -> list[int]:
    """Official Vx filter: type webmcp_changed, version 1, positive int tabId."""
    tab_ids: list[int] = []
    for event in page_events or []:
        if not isinstance(event, dict):
            continue
        if event.get("type") != WEBMCP_CHANGED:
            continue
        if event.get("version") != WEBMCP_CHANGED_VERSION:
            continue
        tab_id = event.get("tabId")
        if isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id <= 0:
            continue
        if tab_id not in tab_ids:
            tab_ids.append(tab_id)
    return tab_ids


def externally_acquired_tab_ids(lifecycle_events: list[dict[str, Any]] | None) -> list[Any]:
    """Official _k: only tab_acquired events with origin "external" qualify.

    Unlike the page-event filter (Vx), the official lifecycle branch adds
    o.tabId with no numeric check, so DSH's string tab ids ("tab-1") qualify too.
    """
    tab_ids: list[Any] = []
    for event in lifecycle_events or []:
        if not isinstance(event, dict) or event.get("type") != TAB_ACQUIRED:
            continue
        if str(event.get("origin") or "") != EXTERNAL_ORIGIN:
            continue
        tab_id = event.get("tabId")
        if tab_id is None or str(tab_id) == "":
            continue
        if tab_id not in tab_ids:
            tab_ids.append(tab_id)
    return tab_ids


def serialize_webmcp_tools(tools: list[dict[str, Any]] | None) -> str:
    """Official Kp(): JSON.stringify(tools.map(t => ({...t, pageUrl: undefined}))).

    pageUrl: undefined disappears in JSON, so it is simply dropped; each tool
    keeps its field order (Python dicts preserve insertion order, like JS).
    """
    normalized = [
        {key: value for key, value in tool.items() if key != "pageUrl"}
        for tool in (tools or [])
        if isinstance(tool, dict)
    ]
    return json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)


def webmcp_tools_block(tab_id: int | str, tools: list[dict[str, Any]]) -> str:
    """Official A7(t, r): the fenced JSON block listing the page-defined tools."""
    return "\n".join(
        [
            WEBMCP_TOOLS_AVAILABLE.format(tab_id=tab_id),
            "",
            WEBMCP_JSON_FENCE,
            serialize_webmcp_tools(tools),
            "```",
        ]
    )


def webmcp_notification(
    tab_id: int | str, tools: list[dict[str, Any]] | None, previous: str | None
) -> str:
    """Official E7(): the three-way available / unchanged / gone decision."""
    current = serialize_webmcp_tools(tools)
    if not tools:
        if previous is None or previous == current:
            return ""
        return WEBMCP_TOOLS_GONE.format(tab_id=tab_id)
    if previous == current:
        return ""
    return webmcp_tools_block(tab_id, tools)


def webmcp_notifications(
    page_events: list[dict[str, Any]] | None,
    lifecycle_events: list[dict[str, Any]] | None,
    *,
    list_tools: Callable[[Any], list[dict[str, Any]]] | None = None,
    cache: dict[Any, str] | None = None,
) -> list[str]:
    """Official sY[0] (_k): the WebMCP contributor."""
    tab_ids = webmcp_changed_tab_ids(page_events)
    for tab_id in externally_acquired_tab_ids(lifecycle_events):
        if tab_id not in tab_ids:
            tab_ids.append(tab_id)
    items: list[str] = []
    store = cache if cache is not None else {}
    for tab_id in tab_ids:
        tools: list[dict[str, Any]] = []
        if list_tools is not None:
            try:
                fetched = list_tools(tab_id)
            except Exception:
                fetched = []
            if isinstance(fetched, list):
                tools = [tool for tool in fetched if isinstance(tool, dict)]
        text = webmcp_notification(tab_id, tools, store.get(tab_id))
        store[tab_id] = serialize_webmcp_tools(tools)
        if text:
            items.append(text)
    return items


def take_browser_notifications(
    page_events: list[dict[str, Any]] | None,
    lifecycle_events: list[dict[str, Any]] | None,
    *,
    webmcp_enabled: bool = True,
    list_tools: Callable[[Any], list[dict[str, Any]]] | None = None,
    cache: dict[Any, str] | None = None,
    current_session_id: str = "",
) -> str:
    """Official qB(): the whole after-submitted-code notification hook.

    Drains the per-tab page events (version 1 and, when a session is known, the
    current session -- matchesCurrentSessionId) plus the tab lifecycle events,
    runs every contributor and returns the response content item ("" when
    empty).
    """
    store = cache if cache is not None else {}
    if not webmcp_enabled:
        # Official yk(r): disabling WebMCP clears the per-tab cache.
        store.clear()
        return ""
    filtered = [
        event
        for event in (page_events or [])
        if isinstance(event, dict)
        and event.get("version") == WEBMCP_CHANGED_VERSION
        and (not current_session_id or str(event.get("session_id") or "") == current_session_id)
    ]
    items = webmcp_notifications(
        filtered, lifecycle_events, list_tools=list_tools, cache=store
    )
    return format_browser_notifications(items)

__all__ = [
    "AGENT_ORIGIN",
    "BROWSER_NOTIFICATIONS_HEADER",
    "BROWSER_NOTIFICATIONS_PREFIX",
    "CDP_BACKEND",
    "EXTERNAL_ORIGIN",
    "MUTATING_COMMANDS",
    "READ_ONLY_COMMANDS",
    "TAB_ACQUIRED",
    "TAB_CREATED",
    "WEBMCP_CHANGED",
    "WEBMCP_CHANGED_VERSION",
    "WEBMCP_JSON_FENCE",
    "WEBMCP_TOOLS_AVAILABLE",
    "WEBMCP_TOOLS_GONE",
    "contributes_response_meta",
    "externally_acquired_tab_ids",
    "format_browser_notifications",
    "response_meta_contribution",
    "serialize_webmcp_tools",
    "take_browser_notifications",
    "webmcp_changed_tab_ids",
    "webmcp_notification",
    "webmcp_notifications",
    "webmcp_tools_block",
]
