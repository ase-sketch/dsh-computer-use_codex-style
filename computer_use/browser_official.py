"""Official browser-service.mjs 57 agent commands as aliases onto existing tab_* tools."""

from __future__ import annotations

from typing import Any

from computer_use.tools import _bool, _obj, _str, _tool

# Names extracted from O("...", ...) registrations in browser-service.mjs.
OFFICIAL_COMMANDS = (
    "browser_setup",
    "create_tab",
    "close_tab",
    "get_tab",
    "list_tabs",
    "mark_tab",
    "name_session",
    "selected_tab",
    "navigate_tab_back",
    "navigate_tab_forward",
    "navigate_tab_reload",
    "tab_ax_get_state",
    "tab_ax_action",
    "tab_screenshot",
    "cua_click",
    "cua_double_click",
    "cua_drag",
    "cua_keypress",
    "cua_move",
    "cua_scroll",
    "cua_type",
    "dom_cua_get_visible_dom",
    "dom_cua_click",
    "dom_cua_double_click",
    "dom_cua_keypress",
    "dom_cua_scroll",
    "dom_cua_type",
    "playwright_locator_click",
    "playwright_locator_dblclick",
    "playwright_locator_count",
    "playwright_locator_is_enabled",
    "playwright_locator_is_visible",
    "playwright_locator_press",
    "playwright_locator_fill",
    "playwright_locator_get_attribute",
    "playwright_locator_inner_text",
    "playwright_locator_all_text_contents",
    "playwright_locator_press_sequentially",
    "playwright_locator_set_checked",
    "playwright_locator_text_content",
    "playwright_locator_read_all",
    "playwright_locator_wait_for",
    "playwright_dom_snapshot",
    "playwright_download_path",
    "playwright_wait_for_download",
    "playwright_wait_for_file_chooser",
    "playwright_wait_for_load_state",
    "playwright_wait_for_url",
    "playwright_file_chooser_set_files",
    "browser_user_claim_tab",
    "browser_user_get_tab_context",
    "browser_user_history",
    "browser_user_open_tabs",
    "tab_content_export_youtube_transcript",
    "tab_dev_logs",
    "tab_get_js_dialog",
    "tab_handle_js_dialog",
    # Commands that were missing from the catalog entirely, so the official
    # API member that maps to them was unusable (most importantly Tab.goto ->
    # navigate_tab_url). Payload shapes live in browser_schemas.py.
    "navigate_tab_url",
    "tab_manual_handoff_request",
    "tabs_content",
    "tab_content_export",
    "tab_content_export_gsuite",
    "tab_clipboard_read_text",
    "tab_clipboard_write_text",
    "tab_cdp_call",
    "tab_cdp_events",
    "tab_page_assets_list",
    "tab_bot_detection_report",
    "webmcp_list_tools",
    "webmcp_invoke_tool",
    "list_browsers",
    "get_browser",
    "get_default_browser",
    "get_browser_for_url",
    "get_documentation",
    "get_browser_documentation",
    # BR-01: the 18 official commands the catalog was missing. Seven of them
    # already had a real payload schema in browser_schemas.py but were never
    # registered, so the model could not see them at all (BR-02).
    "browser_management_call",
    "browser_management_get_audit_trail",
    "browser_viewport_set",
    "browser_viewport_reset",
    "browser_visibility_get",
    "browser_visibility_set",
    "cua_download_media",
    "dom_cua_download_media",
    "playwright_element_info",
    "playwright_element_screenshot",
    "playwright_evaluate",
    "playwright_locator_download_media",
    "playwright_locator_select_option",
    "playwright_wait_for_timeout",
    "runtime_config",
    "tab_browser_auth_handoff",
    "tab_clipboard_read",
    "tab_clipboard_write",
    "tab_page_assets_bundle",
)

#: Official `tab_ax_action.action.type` union members (04:215-220).
AX_ACTION_MEMBERS = (
    "click",
    "drag",
    "perform_secondary_action",
    "press_key",
    "scroll",
    "select_text",
    "set_value",
    "type_text",
)

#: Official direction aliases for the scroll member (u/d/l/r).
AX_SCROLL_DIRECTIONS = {
    "u": "up",
    "d": "down",
    "l": "left",
    "r": "right",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}


ALIASES: dict[str, str] = {
    "create_tab": "tab_new",
    "close_tab": "tab_close",
    "get_tab": "tab_get",
    "list_tabs": "tab_list",
    "name_session": "browser_name_session",
    "selected_tab": "tab_selected",
    "navigate_tab_back": "tab_back",
    "navigate_tab_forward": "tab_forward",
    "navigate_tab_reload": "tab_reload",
    "tab_ax_get_state": "tab_ax_write",
    "cua_click": "tab_cua_click",
    "cua_double_click": "tab_cua_double_click",
    "cua_drag": "tab_cua_drag",
    "cua_keypress": "tab_cua_keypress",
    "cua_move": "tab_cua_move",
    "cua_scroll": "tab_cua_scroll",
    "cua_type": "tab_cua_type",
    "dom_cua_get_visible_dom": "tab_dom_get_visible_dom",
    "dom_cua_click": "tab_dom_click",
    "dom_cua_double_click": "tab_dom_double_click",
    "dom_cua_keypress": "tab_dom_keypress",
    "dom_cua_scroll": "tab_dom_scroll",
    "dom_cua_type": "tab_dom_type",
    "playwright_locator_click": "tab_pw_click",
    "playwright_locator_dblclick": "tab_pw_dblclick",
    "playwright_locator_count": "tab_pw_count",
    "playwright_locator_is_enabled": "tab_pw_is_enabled",
    "playwright_locator_is_visible": "tab_pw_is_visible",
    "playwright_locator_press": "tab_pw_press",
    "playwright_locator_fill": "tab_pw_fill",
    "playwright_locator_get_attribute": "tab_pw_get_attribute",
    "playwright_locator_inner_text": "tab_pw_inner_text",
    "playwright_locator_all_text_contents": "tab_pw_all_text_contents",
    "playwright_locator_press_sequentially": "tab_pw_press_sequentially",
    "playwright_locator_set_checked": "tab_pw_set_checked",
    "playwright_locator_text_content": "tab_pw_text_content",
    "playwright_locator_read_all": "tab_pw_all",
    "playwright_locator_wait_for": "tab_pw_wait_for",
    "playwright_dom_snapshot": "tab_pw_dom_snapshot",
    "playwright_download_path": "tab_pw_download_path",
    "playwright_wait_for_download": "tab_pw_wait_for_event",
    "playwright_wait_for_file_chooser": "tab_pw_expect_file_chooser",
    "playwright_wait_for_load_state": "tab_pw_wait_for_load_state",
    "playwright_wait_for_url": "tab_pw_wait_for_url",
    "playwright_file_chooser_set_files": "tab_pw_set_files",
    "browser_user_get_tab_context": "browser_get_tab_context",
    "browser_user_history": "browser_history",
    "browser_user_open_tabs": "browser_open_tabs",
    "tab_content_export_youtube_transcript": "tab_content_export_youtube",
    # BR-01: the missing commands whose implementation already existed.
    "browser_visibility_get": "browser_get_visible",
    "browser_visibility_set": "browser_set_visible",
    "cua_download_media": "tab_cua_download_media",
    "dom_cua_download_media": "tab_dom_download_media",
    "playwright_locator_download_media": "tab_pw_download_media",
    "playwright_element_info": "tab_pw_element_info",
    "playwright_element_screenshot": "tab_pw_element_screenshot",
    "playwright_evaluate": "tab_pw_evaluate",
    "playwright_locator_select_option": "tab_pw_select_option",
    "playwright_wait_for_timeout": "tab_pw_wait_for_timeout",
    "tab_clipboard_read": "tab_clipboard_read",
    "tab_clipboard_write": "tab_clipboard_write",
    "tab_page_assets_bundle": "tab_page_assets_bundle",
    # Registered official commands that had no route at all (KeyError).
    "tab_manual_handoff_request": "tab_request_manual_handoff",
    "tab_cdp_call": "tab_cdp_send",
    "tab_cdp_events": "tab_cdp_read_events",
    "webmcp_list_tools": "tab_webmcp_fetch_tools",
    "webmcp_invoke_tool": "tab_webmcp_call",
    "list_browsers": "browser_list",
    "get_browser": "browser_get",
    "get_default_browser": "browser_get_default",
    "get_browser_for_url": "browser_get_for_url",
    "get_documentation": "documentation_get",
}

assert len(set(OFFICIAL_COMMANDS)) == len(OFFICIAL_COMMANDS)


def ax_action_kind(spec: dict[str, object]) -> str:
    """The tab_ax_action.action.type discriminator, tolerating a flat spec."""
    action = spec.get("action")
    if isinstance(action, dict):
        return str(action.get("type") or "")
    if isinstance(action, str):
        return action
    return str(spec.get("type") or "")


def ax_action_payload(spec: dict[str, object]) -> dict[str, object]:
    action = spec.get("action")
    if isinstance(action, dict):
        return action
    return spec


def dialog_is_dismiss(spec: dict[str, object]) -> bool:
    """BR-05: official discriminates on action; accept: false is the legacy
    DSH spelling and is kept only for backward compatibility."""
    if spec.get("accept") is False:
        return True
    return str(spec.get("action") or "").strip().lower() == "dismiss"


def resolve_official(name: str, spec: dict[str, object] | None = None) -> str:
    data = spec or {}
    if name == "mark_tab":
        # BR-03: deliverable and handoff are *different* official marks.
        status = str(data.get("status") or "")
        return "tab_mark_deliverable" if status == "deliverable" else "tab_mark_handoff"
    if name == "tab_handle_js_dialog":
        # BR-05: {action: dismiss} used to be executed as accept.
        return "tab_dialog_dismiss" if dialog_is_dismiss(data) else "tab_dialog_accept"
    return ALIASES.get(name, name)


#: Official content enum -> the DSH mode spelling.
AX_GET_STATE_MODES = {
    "axState": "state",
    "screenshot": "screenshot",
    "axStateAndScreenshot": "both",
    "state": "state",
    "both": "both",
}


def rewrite_spec(name: str, spec: dict[str, object]) -> dict[str, object]:
    payload = dict(spec)
    if name == "tab_ax_get_state":
        # BR-06: content used to be dropped on the floor, so every request for a
        # screenshot returned AX text. Official maps it onto the payload.
        content = str(payload.get("content") or "axState")
        payload["mode"] = AX_GET_STATE_MODES.get(content, "state")
        payload.pop("content", None)
        # Official default returns a diff; DSH forced a full tree (BR-06).
        payload.setdefault("disableDiffing", False)
    if name == "playwright_wait_for_download":
        payload.setdefault("event", "download")
    if name == "playwright_evaluate":
        payload.setdefault("expression", str(payload.get("script") or ""))
    if name == "playwright_locator_select_option":
        selections = payload.get("selections")
        if isinstance(selections, list) and selections:
            payload.setdefault("value", selections[0])
    if name == "tab_handle_js_dialog":
        # BR-05: translate the official fields onto the DSH dialog tool. The
        # accept/dismiss routing happens in resolve_official.
        payload["accept"] = not dialog_is_dismiss(payload)
        if payload.get("prompt_text") is not None:
            payload.setdefault("text", payload.get("prompt_text"))
    return payload


POLICY_DISABLED = {
    "codex-app": (),
    "training": ("browser_user_claim_tab", "browser_claim_tab", "browser_user_history", "tab_request_manual_handoff"),
    "cloud": ("browser_user_claim_tab", "browser_claim_tab"),
}


def official_tool_definitions(disabled: list[str] | None = None) -> list[dict[str, Any]]:
    """Advertise every official browser command with its real payload shape.

    Previously each alias declared a single *required* `tab_id`, which made
    `create_tab`, `list_tabs`, `name_session`, `tab_ax_action` and every
    `playwright_locator_*` unusable: the model could not express the parameters
    the command needs. Schemas now come from `browser_schemas.schema_for`.
    """
    from computer_use.browser_schemas import schema_for

    skip = set(disabled or [])
    tools = [
        _tool(
            "browser_setup",
            "Official browser-service setup. environment must be codex-app, training, or cloud. Call before any other browser command.",
            _obj(
                {
                    "environment": _str("codex-app | training | cloud"),
                    "undocumentedApiMembers": _bool("Expose undocumented API members"),
                    "excludedDocumentation": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Documentation entries to withhold",
                    },
                },
                ["environment"],
            ),
        )
    ]
    for name in OFFICIAL_COMMANDS:
        if name == "browser_setup" or name in skip or ALIASES.get(name, name) in skip:
            continue
        description, properties, required = schema_for(name)
        mapped = resolve_official(name)
        tools.append(
            _tool(
                name,
                f"{description} (maps to {mapped}).",
                _obj(properties, required),
            )
        )
    # Keep the engine-wide OpenAI function envelope here; the DSH boundary
    # (`rpc.dsh_tool_list`) flattens it into MCP shape. Emitting a different shape
    # from this one surface would break every consumer that walks "function".
    return tools
