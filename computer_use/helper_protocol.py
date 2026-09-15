"""Stdio JSON-line protocol recovered from WindowsHelperTransport + helper EXE."""

from __future__ import annotations

import json
from typing import Any

BUDGET_HEADER = "x-oai-cua-request-budget-ms"
APPROVED_APP_META_KEY = "x-oai-cua-approved-app"
TURN_METADATA_KEY = "x-codex-turn-metadata"
TURN_ENDED_MESSAGE = (
    "Computer Use is no longer available in this turn because the turn has ended. "
    "Do not call further Computer Use tools in this turn."
)
TURN_ENDED_EVENT_PREFIX = "Local\\CodexComputerUseTurnEnded-"
ESCAPE_ERROR = (
    "Computer Use was stopped by the user with the physical Escape key. "
    "Stop your work, do not call further Computer Use tools in this turn, "
    "and send a final message noting that the user stopped Computer Use."
)


def encode_request(
    req_id: int,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_ms: int = 15000,
    extra_meta: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {"id": req_id, "method": method, "params": params or {}}
    meta: dict[str, Any] = {BUDGET_HEADER: timeout_ms}
    if extra_meta:
        meta.update(extra_meta)
    payload["meta"] = meta
    return json.dumps(payload, ensure_ascii=False) + "\n"


def turn_metadata(session_id: str | None, turn_id: str | None, conversation_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if session_id:
        body["session_id"] = session_id
        body["sessionId"] = session_id
    if turn_id:
        body["turn_id"] = turn_id
        body["turnId"] = turn_id
    if conversation_id:
        body["conversation_id"] = conversation_id
        body["conversationId"] = conversation_id
    return {TURN_METADATA_KEY: body} if body else {}


def scroll_method(spec: dict[str, object]) -> str:
    if spec.get("element_index") is not None:
        return "scroll_element"
    return "scroll"


def scroll_params(window: dict[str, Any], spec: dict[str, object]) -> tuple[str, dict[str, Any]]:
    method = scroll_method(spec)
    if method == "scroll_element":
        return method, {
            "window": window,
            "element_index": spec.get("element_index"),
            "direction": spec.get("direction") or "down",
            "pages": spec.get("pages") or 1,
        }
    params: dict[str, Any] = {
        "window": window,
        "x": spec.get("x"),
        "y": spec.get("y"),
        "scrollX": spec.get("scrollX"),
        "scrollY": spec.get("scrollY"),
    }
    if spec.get("screenshotId") is not None:
        params["screenshotId"] = spec["screenshotId"]
    return method, params


def decode_response(line: str) -> dict[str, Any]:
    return json.loads(line)


def helper_click_method(spec: dict[str, object]) -> str:
    if spec.get("element_index") is not None or spec.get("elementIndex") is not None or spec.get("element") is not None:
        return "click_element"
    return "click"


def click_params(window: dict[str, Any], spec: dict[str, object]) -> tuple[str, dict[str, Any]]:
    method = helper_click_method(spec)
    if method == "click_element":
        return method, {
            "window": window,
            "element_index": spec.get("element_index", spec.get("elementIndex", spec.get("element"))),
            "click_count": spec.get("click_count", 1),
            "mouse_button": spec.get("mouse_button", "left"),
        }
    params: dict[str, Any] = {
        "window": window,
        "x": spec.get("x"),
        "y": spec.get("y"),
        "click_count": spec.get("click_count", 1),
        "mouse_button": spec.get("mouse_button", "left"),
    }
    if spec.get("screenshotId") is not None:
        params["screenshotId"] = spec["screenshotId"]
    return method, params
