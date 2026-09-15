"""Official browser command payload schemas (recovered from browser-service.mjs zod).

The generic fallback used to advertise every official command with a single *required*
`tab_id`, which made most of them unusable: `create_tab`, `list_tabs`, `name_session`,
`tab_ax_action`, every `playwright_locator_*` and friends need different parameters.
This module carries the real payload shapes for the high-traffic commands and a
permissive schema for the rest.
"""

from __future__ import annotations

from typing import Any

from computer_use.tools import _bool, _int, _num, _obj, _str


def _arr(desc: str, items: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "array", "items": items or {}, "description": desc}


def _point(desc: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2,
        "description": desc,
    }


def _ax_action_union() -> dict[str, Any]:
    """BR-04: the real 8-member official discriminated union."""
    def member(kind: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"type": {"const": kind}, **properties},
            "required": ["type", *required],
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "description": "One of: click, drag, perform_secondary_action, press_key, scroll, "
                       "select_text, set_value, type_text.",
        "oneOf": [
            member("click", {
                "target": {"oneOf": [
                    {"type": "integer", "description": "AX element index"},
                    _point("Viewport [x, y]"),
                ]},
                "mouse_button": {"type": "string", "enum": ["left", "right", "middle"]},
                "click_count": _int("Click count"),
            }, ["target"]),
            member("drag", {"from": _point("Start"), "to": _point("End")}, ["from", "to"]),
            member("perform_secondary_action", {
                "element_index": _int("AX index"),
                "action": _str("Raise|Expand|Collapse|Scroll Up|Scroll Down|Scroll Left|Scroll Right"),
            }, ["element_index", "action"]),
            member("press_key", {"key": _str("Key chord, e.g. Return")}, ["key"]),
            member("scroll", {
                "target": {"type": "integer", "description": "AX element index"},
                "direction": {"type": "string", "enum": ["up", "down", "left", "right", "u", "d", "l", "r"]},
                "pages": _num("Pages to scroll"),
            }, ["target", "direction"]),
            member("select_text", {
                "element_index": _int("AX index"),
                "text": _str("Text to select"),
                "prefix": _str("Disambiguating prefix"),
                "suffix": _str("Disambiguating suffix"),
                "selection_type": {"type": "string", "enum": ["text", "cursor_before", "cursor_after"]},
            }, ["element_index", "text"]),
            member("set_value", {"element_index": _int("AX index"), "value": _str("Value")},
                   ["element_index", "value"]),
            member("type_text", {"text": _str("Text")}, ["text"]),
        ],
    }


TAB_ID = _str("Tab id from list_tabs / create_tab / get_tab")
URL = _str("Absolute http(s) URL to navigate to")

# Tab and session management.
TAB_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "create_tab": (
        "Create a new tab and return its id.",
        {"tab_id": TAB_ID, "url": URL, "visible": _bool("Show the browser window (in-app browser only)"),
         "session_name": _str("Short emoji-prefixed task name for the browser session")},
        [],
    ),
    "get_tab": (
        "Return the tab bound to tab_id, checking expected_url when supplied.",
        {"tab_id": TAB_ID, "expected_url": _str("Fail when the tab is not on this URL")},
        ["tab_id"],
    ),
    "close_tab": ("Close a tab.", {"tab_id": TAB_ID}, ["tab_id"]),
    "list_tabs": (
        "List tabs known to the selected browser.",
        {"browser_id": _str("Browser id from list_browsers / the setup result")},
        [],
    ),
    "selected_tab": (
        "Return the currently selected tab id, when the browser exposes one.",
        {"browser_id": _str("Browser id")},
        [],
    ),
    "mark_tab": (
        "Mark a tab as a deliverable or as a manual handoff.",
        {"tab_id": TAB_ID, "status": {"type": "string", "enum": ["handoff", "deliverable"],
                                      "description": "Mark kind"}},
        ["tab_id", "status"],
    ),
    "name_session": (
        "Name the current browser session.",
        {"name": _str("Session name, e.g. \"\U0001f50e Task\""), "browser_id": _str("Browser id")},
        ["name"],
    ),
    "tab_manual_handoff_request": (
        "Ask the user to take over a tab manually.",
        {"tab_id": TAB_ID},
        ["tab_id"],
    ),
    "navigate_tab_url": (
        "Navigate a tab to a URL after the URL policy check.",
        {"tab_id": TAB_ID, "url": URL},
        ["tab_id", "url"],
    ),
    "navigate_tab_back": ("Go back in a tab.", {"tab_id": TAB_ID}, ["tab_id"]),
    "navigate_tab_forward": ("Go forward in a tab.", {"tab_id": TAB_ID}, ["tab_id"]),
    "navigate_tab_reload": ("Reload a tab.", {"tab_id": TAB_ID}, ["tab_id"]),
}

# Accessibility and screenshots.
AX_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "tab_ax_get_state": (
        "Read a tab accessibility state, a screenshot, or both.",
        {
            "tab_id": TAB_ID,
            "content": {"type": "string", "enum": ["axState", "screenshot", "axStateAndScreenshot"],
                        "description": "What to capture; defaults to axState"},
            "disable_diffing": _bool("Return a full accessibility tree instead of a diff"),
        },
        ["tab_id"],
    ),
    "tab_ax_action": (
        "Perform one accessibility action in a tab.",
        {
            "tab_id": TAB_ID,
            "action": _ax_action_union(),
        },
        ["tab_id", "action"],
    ),
    "tab_screenshot": (
        "Capture a tab screenshot, optionally cropped.",
        {"tab_id": TAB_ID, "fullPage": _bool("Capture the full page"), "cropX": _num("Crop X"),
         "cropY": _num("Crop Y"), "cropWidth": _num("Crop width"), "cropHeight": _num("Crop height")},
        ["tab_id"],
    ),
}

# Coordinate input inside a tab.
CUA_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "cua_click": ("Click at tab viewport coordinates.",
                  {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y"), "button": _int("0 left, 1 middle, 2 right"),
                   "keys": _arr("Modifier keys held during the click", {"type": "string"})},
                  ["tab_id", "x", "y"]),
    "cua_double_click": ("Double-click at tab viewport coordinates.",
                         {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y"),
                          "keys": _arr("Modifier keys", {"type": "string"})},
                         ["tab_id", "x", "y"]),
    "cua_move": ("Move the pointer to tab viewport coordinates.",
                 {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y"),
                  "keys": _arr("Modifier keys", {"type": "string"})},
                 ["tab_id", "x", "y"]),
    "cua_drag": ("Drag along a path inside a tab.",
                 {"tab_id": TAB_ID,
                  "path": _arr("Path points", {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}}),
                  "keys": _arr("Modifier keys", {"type": "string"})},
                 ["tab_id", "path"]),
    "cua_keypress": ("Press keys in a tab.",
                     {"tab_id": TAB_ID, "keys": _arr("Key names", {"type": "string"})},
                     ["tab_id", "keys"]),
    "cua_scroll": ("Scroll at tab viewport coordinates.",
                   {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y"), "scroll_x": _num("Horizontal delta"),
                    "scroll_y": _num("Vertical delta"), "keys": _arr("Modifier keys", {"type": "string"})},
                   ["tab_id", "x", "y", "scroll_x", "scroll_y"]),
    "cua_type": ("Type literal text into a tab.", {"tab_id": TAB_ID, "text": _str("Text")}, ["tab_id", "text"]),
    "cua_download_media": (
        "Download media at tab viewport coordinates.",
        {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y"), "timeout_ms": _int("Timeout in milliseconds")},
        ["tab_id", "x", "y"],
    ),
}

# DOM fallback and Playwright locators.
DOM_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "dom_cua_get_visible_dom": ("Return the visible DOM with node ids.", {"tab_id": TAB_ID}, ["tab_id"]),
    "dom_cua_click": ("Click a DOM node id.", {"tab_id": TAB_ID, "node_id": _str("Node id")}, ["tab_id", "node_id"]),
    "dom_cua_double_click": ("Double-click a DOM node id.",
                             {"tab_id": TAB_ID, "node_id": _str("Node id")}, ["tab_id", "node_id"]),
    "dom_cua_keypress": ("Press keys through the DOM path.",
                         {"tab_id": TAB_ID, "keys": _arr("Key names", {"type": "string"})}, ["tab_id", "keys"]),
    "dom_cua_scroll": ("Scroll through the DOM path.",
                       {"tab_id": TAB_ID, "scroll_x": _num("Horizontal delta"), "scroll_y": _num("Vertical delta"),
                        "node_id": _str("Optional node id")}, ["tab_id", "scroll_x", "scroll_y"]),
    "dom_cua_type": ("Type through the DOM path.", {"tab_id": TAB_ID, "text": _str("Text")}, ["tab_id", "text"]),
    "dom_cua_download_media": (
        "Download media for a DOM node.",
        {"tab_id": TAB_ID, "node_id": _str("Node id"), "timeout_ms": _int("Timeout in milliseconds")},
        ["tab_id", "node_id"],
    ),
}

SELECTOR = _str("Playwright selector")
TIMEOUT = _int("Timeout in milliseconds")

PW_LOCATOR_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "playwright_locator_click": ("Click a locator.",
                                 {"tab_id": TAB_ID, "selector": SELECTOR,
                                  "button": {"type": "string", "enum": ["left", "right", "middle"]},
                                  "force": _bool("Skip actionability checks"), "timeout_ms": TIMEOUT},
                                 ["tab_id", "selector"]),
    "playwright_locator_dblclick": ("Double-click a locator.",
                                    {"tab_id": TAB_ID, "selector": SELECTOR, "force": _bool("Skip checks"),
                                     "timeout_ms": TIMEOUT}, ["tab_id", "selector"]),
    "playwright_locator_fill": ("Fill a locator.",
                                {"tab_id": TAB_ID, "selector": SELECTOR, "value": _str("Value"),
                                 "replace": _bool("Replace existing content")}, ["tab_id", "selector", "value"]),
    "playwright_locator_press": ("Press a key on a locator.",
                                 {"tab_id": TAB_ID, "selector": SELECTOR, "value": _str("Key")},
                                 ["tab_id", "selector", "value"]),
    "playwright_locator_press_sequentially": ("Type a string into a locator key by key.",
                                              {"tab_id": TAB_ID, "selector": SELECTOR, "value": _str("Text"),
                                               "timeout_ms": TIMEOUT}, ["tab_id", "selector", "value"]),
    "playwright_locator_count": ("Count matches for a locator.",
                                 {"tab_id": TAB_ID, "selector": SELECTOR}, ["tab_id", "selector"]),
    "playwright_locator_inner_text": ("Read the inner text of a locator.",
                                      {"tab_id": TAB_ID, "selector": SELECTOR, "timeout_ms": TIMEOUT},
                                      ["tab_id", "selector"]),
    "playwright_locator_text_content": ("Read textContent of a locator.",
                                        {"tab_id": TAB_ID, "selector": SELECTOR, "timeout_ms": TIMEOUT},
                                        ["tab_id", "selector"]),
    "playwright_locator_all_text_contents": ("Read all text contents for a locator.",
                                             {"tab_id": TAB_ID, "selector": SELECTOR}, ["tab_id", "selector"]),
    "playwright_locator_get_attribute": ("Read an attribute of a locator.",
                                         {"tab_id": TAB_ID, "selector": SELECTOR, "name": _str("Attribute name"),
                                          "timeout_ms": TIMEOUT}, ["tab_id", "selector", "name"]),
    "playwright_locator_is_visible": ("Report whether a locator is visible.",
                                      {"tab_id": TAB_ID, "selector": SELECTOR}, ["tab_id", "selector"]),
    "playwright_locator_is_enabled": ("Report whether a locator is enabled.",
                                      {"tab_id": TAB_ID, "selector": SELECTOR}, ["tab_id", "selector"]),
    "playwright_locator_set_checked": ("Check or uncheck a locator.",
                                       {"tab_id": TAB_ID, "selector": SELECTOR, "checked": _bool("Desired state"),
                                        "force": _bool("Skip checks"), "timeout_ms": TIMEOUT},
                                       ["tab_id", "selector", "checked"]),
    "playwright_locator_select_option": ("Select options in a locator.",
                                         {"tab_id": TAB_ID, "selector": SELECTOR,
                                          "selections": _arr("Option labels or values", {"type": "string"}),
                                          "timeout_ms": TIMEOUT}, ["tab_id", "selector", "selections"]),
    "playwright_locator_wait_for": ("Wait for a locator state.",
                                    {"tab_id": TAB_ID, "selector": SELECTOR,
                                     "state": {"type": "string", "enum": ["attached", "detached", "visible", "hidden"]},
                                     "timeout_ms": TIMEOUT}, ["tab_id", "selector"]),
    "playwright_locator_read_all": ("Read all matches with attributes and text.",
                                    {"tab_id": TAB_ID, "selector": SELECTOR, "relative_selector": _str("Relative selector"),
                                     "timeout_ms": TIMEOUT}, ["tab_id", "selector"]),
    "playwright_locator_download_media": ("Download media through a locator.",
                                          {"tab_id": TAB_ID, "selector": SELECTOR, "timeout_ms": TIMEOUT},
                                          ["tab_id", "selector"]),
    "playwright_element_screenshot": ("Viewport screenshot annotated with element bounds.",
                                      {"tab_id": TAB_ID, "x": _num("X"), "y": _num("Y")}, ["tab_id", "x", "y"]),
}

# Content, clipboard, dialogs and document reads.
MISC_COMMANDS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "tabs_content": ("Fetch page content for URLs.",
                     {"urls": _arr("URLs", {"type": "string"}),
                      "content_type": {"type": "string", "enum": ["html", "text", "domSnapshot"]},
                      "timeout_ms": TIMEOUT}, ["urls", "content_type"]),
    "tab_content_export": ("Export a tab to a file and return its path.", {"tab_id": TAB_ID}, ["tab_id"]),
    "tab_content_export_gsuite": ("Export a tab through GSuite formats.",
                                  {"tab_id": TAB_ID,
                                   "format": {"type": "string", "enum": ["pdf", "md", "xlsx", "csv", "docx", "pptx"]}},
                                  ["tab_id", "format"]),
    "tab_content_export_youtube_transcript": ("Export a YouTube transcript.", {"tab_id": TAB_ID}, ["tab_id"]),
    "tab_clipboard_read_text": ("Read the tab clipboard as text.", {"tab_id": TAB_ID}, ["tab_id"]),
    "tab_clipboard_write_text": ("Write text to the tab clipboard.",
                                 {"tab_id": TAB_ID, "text": _str("Text")}, ["tab_id", "text"]),
    "tab_dev_logs": ("Read tab console logs.",
                     {"tab_id": TAB_ID, "filter": _str("Substring filter"),
                      "levels": _arr("Levels", {"type": "string", "enum": ["debug", "info", "log", "warn", "error"]}),
                      "limit": _int("Maximum entries")}, ["tab_id"]),
    "tab_get_js_dialog": ("Read the pending JavaScript dialog, if any.", {"tab_id": TAB_ID}, ["tab_id"]),
    "tab_handle_js_dialog": ("Accept or dismiss a JavaScript dialog.",
                             {"tab_id": TAB_ID, "action": {"type": "string", "enum": ["accept", "dismiss"]},
                              "dialog_id": _str("Dialog id from tab_get_js_dialog"),
                              "prompt_text": _str("Text for a prompt dialog")}, ["tab_id", "action"]),
    "browser_user_open_tabs": ("List tabs the user already has open.", {}, []),
    # BR-13: the official wire command is `{tab_id}`; the fail-closed snapshot
    # match happens in the engine against openTabs(), so the schema matches the
    # implementation instead of forcing the caller to pass title/url.
    "browser_user_claim_tab": (
        "Claim a user tab returned by browser_user_open_tabs.",
        {"tab_id": TAB_ID, "browserId": _str("Optional extensionInstanceId to match")},
        ["tab_id"],
    ),
    "browser_user_get_tab_context": ("Read the user-visible context of a tab.",
                                     {"tab_id": TAB_ID, "expected_url": _str("Fail unless the tab is on this URL")},
                                     ["tab_id"]),
    "browser_user_history": ("Search the user browsing history.",
                             {"queries": _arr("Queries", {"type": "string"}), "limit": _int("Maximum entries"),
                              "from": _str("ISO start date"), "to": _str("ISO end date")}, ["queries"]),
    "browser_visibility_get": ("Report whether the browser window is visible.", {}, []),
    "browser_visibility_set": ("Show or hide the browser window.", {"visible": _bool("Desired visibility")}, ["visible"]),
    "browser_viewport_set": ("Set the browser viewport size.",
                             {"width": _int("Width"), "height": _int("Height")}, ["width", "height"]),
    "browser_viewport_reset": ("Reset the browser viewport.", {}, []),
    "list_browsers": ("List available browsers.", {}, []),
    "get_browser": ("Select a browser by id.", {"id": _str("Browser id")}, ["id"]),
    "get_default_browser": ("Select the default browser.", {}, []),
    "get_browser_for_url": ("Select the browser that should open a URL.", {"url": URL}, ["url"]),
    "get_documentation": ("Read a browser documentation topic by name.", {"name": _str("Documentation name")}, ["name"]),
    "get_browser_documentation": ("Read the documentation for a browser.",
                                  {"browser_id": _str("Browser id")}, ["browser_id"]),
    "playwright_evaluate": ("Evaluate a script in the page.",
                            {"tab_id": TAB_ID, "selector": SELECTOR, "script": _str("Script body"),
                             "timeout_ms": TIMEOUT}, ["tab_id", "script"]),
    "playwright_dom_snapshot": ("Return a page DOM snapshot.", {"tab_id": TAB_ID}, ["tab_id"]),
    "playwright_wait_for_url": ("Wait for the tab URL.",
                                {"tab_id": TAB_ID, "url": URL,
                                 "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"]},
                                 "timeout_ms": TIMEOUT}, ["tab_id", "url"]),
    "playwright_wait_for_load_state": ("Wait for a load state.",
                                       {"tab_id": TAB_ID,
                                        "state": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"]},
                                        "timeout_ms": TIMEOUT}, ["tab_id"]),
    "playwright_wait_for_timeout": ("Wait for a fixed duration.",
                                    {"tab_id": TAB_ID, "timeout_ms": TIMEOUT}, ["tab_id", "timeout_ms"]),
    "playwright_wait_for_download": ("Wait for the next download and return its id.",
                                     {"tab_id": TAB_ID, "timeout_ms": TIMEOUT}, ["tab_id"]),
    "playwright_download_path": ("Return the saved path of a download.",
                                 {"tab_id": TAB_ID, "download_id": _str("Download id"), "timeout_ms": TIMEOUT},
                                 ["tab_id", "download_id"]),
    "playwright_wait_for_file_chooser": ("Wait for a file chooser.",
                                         {"tab_id": TAB_ID, "timeout_ms": TIMEOUT}, ["tab_id"]),
    "playwright_file_chooser_set_files": ("Answer a file chooser with paths.",
                                          {"tab_id": TAB_ID, "file_chooser_id": _str("File chooser id"),
                                           "files": _arr("Absolute paths", {"type": "string"}), "timeout_ms": TIMEOUT},
                                          ["tab_id", "file_chooser_id", "files"]),
    "tab_cdp_call": ("Send a raw CDP command.",
                     {"tab_id": TAB_ID, "method": _str("CDP method"), "params": {"type": "object", "additionalProperties": True},
                      "target": {"type": "object", "additionalProperties": True}, "timeout_ms": TIMEOUT},
                     ["tab_id", "method"]),
    "tab_cdp_events": ("Read buffered CDP events.",
                       {"tab_id": TAB_ID, "after_sequence": _int("Read after this sequence"), "limit": _int("Maximum events"),
                        "methods": _arr("CDP method filter", {"type": "string"})}, ["tab_id"]),
    "tab_page_assets_list": ("List page assets.", {"tab_id": TAB_ID}, ["tab_id"]),
    "tab_bot_detection_report": ("Report a bot-detection blocker.",
                                 {"tab_id": TAB_ID,
                                  "reason": {"type": "string", "enum": ["captcha_failed", "access_denied", "challenge_loop", "unexpected_bot_error"]}},
                                 ["tab_id", "reason"]),
    "webmcp_list_tools": ("List WebMCP tools on the page.", {"tab_id": TAB_ID}, ["tab_id"]),
    "webmcp_invoke_tool": ("Invoke a WebMCP tool.",
                           {"tab_id": TAB_ID, "tool_name": _str("Tool name"), "registration_id": _str("Registration id"),
                            "input": {"type": "object", "additionalProperties": True}, "timeout_ms": TIMEOUT},
                           ["tab_id", "tool_name", "registration_id", "input"]),
    "browser_management_call": (
        "Call browser management.{windows,tabs,tabGroups,bookmarks}.<method>.",
        {"area": {"type": "string", "enum": ["windows", "tabs", "tabGroups", "bookmarks"]},
         "method": _str("Method name"), "args": {"type": "object", "additionalProperties": True}},
        ["area", "method"],
    ),
    "browser_management_get_audit_trail": (
        "Return the management audit trail.",
        {},
        [],
    ),
    "runtime_config": (
        "Read or set browser runtime configuration.",
        {"display_truncate_max_chars": _int("Truncate tool output at this many characters")},
        [],
    ),
    "tab_browser_auth_handoff": (
        "Hand a sign-in flow over to the user (browserAuth.request).",
        {"tab_id": TAB_ID, "url": URL, "reason": _str("Why the handoff is needed")},
        ["tab_id", "url"],
    ),
}

COMMAND_SCHEMAS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    **TAB_COMMANDS,
    **AX_COMMANDS,
    **CUA_COMMANDS,
    **DOM_COMMANDS,
    **PW_LOCATOR_COMMANDS,
    **MISC_COMMANDS,
}


def schema_for(name: str) -> tuple[str, dict[str, Any], list[str]]:
    """Return (description, parameters, required) for an official browser command."""
    if name in COMMAND_SCHEMAS:
        return COMMAND_SCHEMAS[name]
    # Unknown command: keep it callable with whatever the backend accepts instead of
    # advertising a single required tab_id, which made these tools unusable.
    return (
        "Official browser-service command.",
        {"tab_id": TAB_ID, "browser_id": _str("Browser id"), "args": {"type": "object", "additionalProperties": True}},
        [],
    )


__all__ = ["COMMAND_SCHEMAS", "schema_for"]
