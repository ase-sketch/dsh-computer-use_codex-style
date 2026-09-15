"""IAB, Chrome-extension claiming, and remaining Playwright APIs."""

from __future__ import annotations

from typing import Any

from computer_use.browser_mentions import parse_tab_mention, same_tab
from computer_use.browser_missing import MISSING_TOOLS, handle_missing, missing_tool_definitions
from computer_use.browser_tab_ops import TAB_OPS, handle_tab_ops, tab_ops_definitions
from computer_use.png import solid_png
import os

from computer_use.tools import _bool, _int, _num, _obj, _str, _tool

AUDIO_TOOLS = ("start_audio_recording", "stop_audio_recording")

EXTRA_TOOLS = (
    "tab_list",
    "tab_selected",
    "browser_set_visible",
    "browser_get_visible",
    "browser_open_tabs",
    "browser_claim_tab",
    "tab_mention_resolve",
    "tab_pw_frame_locator",
    "tab_pw_get_by_placeholder",
    "tab_pw_get_by_test_id",
    "tab_pw_nth",
    "tab_pw_expect_navigation",
    "tab_pw_wait_for_event",
    "tab_pw_wait_for_url",
    "tab_pw_element_info",
    "tab_pw_element_screenshot",
    "browser_detect",
    "tab_mark_handoff",
    "tab_mark_deliverable",
    "tab_request_manual_handoff",
    "tab_pw_set_files",
    "tab_pw_expect_file_chooser",
    "tab_dom_download_media",
    "tab_cua_download_media",
    "browser_history",
) + TAB_OPS + MISSING_TOOLS + (AUDIO_TOOLS if os.environ.get("SKY_ENABLE_AUDIO") == "1" else ())


def extra_tool_definitions() -> list[dict[str, Any]]:
    tab = _str("Tab id")
    loc = _str("Locator id")
    return [
        _tool("tab_list", "browser.tabs.list() for the in-app browser.", _obj({})),
        _tool("tab_selected", "browser.tabs.selected().", _obj({})),
        _tool("browser_set_visible", "IAB visibility capability set(true|false). Hidden by default.", _obj({"visible": _bool("Show IAB to the user")}, ["visible"])),
        _tool("browser_get_visible", "IAB visibility capability get().", _obj({})),
        _tool("browser_open_tabs", "extension user.openTabs() — current external tabs.", _obj({})),
        _tool("browser_claim_tab", "extension user.claimTab — fail closed if title/url/id mismatch.", _obj({"providerTabId": _str("Tab id"), "title": _str("Title snapshot"), "url": _str("URL snapshot")}, ["providerTabId", "title", "url"])),
        _tool("tab_mention_resolve", "Resolve plugin://browser or chrome tab-v1 mention.", _obj({"link": _str("plugin:// mention URL")}, ["link"])),
        _tool("tab_pw_frame_locator", "playwright.frameLocator(selector).", _obj({"tab_id": tab, "selector": _str("iframe selector")}, ["tab_id", "selector"])),
        _tool("tab_pw_get_by_placeholder", "playwright.getByPlaceholder.", _obj({"tab_id": tab, "text": _str("Placeholder"), "frame": _str("Optional frame selector")}, ["tab_id", "text"])),
        _tool("tab_pw_get_by_test_id", "playwright.getByTestId.", _obj({"tab_id": tab, "test_id": _str("data-testid")}, ["tab_id", "test_id"])),
        _tool("tab_pw_nth", "locator.nth/first/last.", _obj({"locator_id": loc, "index": _int("0 first, -1 last, else nth")}, ["locator_id", "index"])),
        _tool("tab_pw_expect_navigation", "playwright.expectNavigation around one action.", _obj({"tab_id": tab, "url": _str("Optional URL glob"), "action": {"type": "object"}}, ["tab_id", "action"])),
        _tool("tab_pw_wait_for_event", "page.waitForEvent('download').", _obj({"tab_id": tab, "event": _str("download")}, ["tab_id"])),
        _tool("tab_pw_wait_for_url", "page.waitForURL.", _obj({"tab_id": tab, "url": _str("URL")}, ["tab_id", "url"])),
        _tool("tab_pw_element_info", "playwright.elementInfo at screenshot coordinates.", _obj({"tab_id": tab, "x": _num("X"), "y": _num("Y"), "includeNonInteractable": _bool("Include non-interactable")}, ["tab_id", "x", "y"])),
        _tool("tab_pw_element_screenshot", "Viewport screenshot annotated with element bounds at x,y.", _obj({"tab_id": tab, "x": _num("X"), "y": _num("Y")}, ["tab_id", "x", "y"])),
        _tool("browser_detect", "Detect IAB / extension / CDP / cloud backends (official availability conditions).", _obj({})),
        _tool("tab_mark_handoff", "Keep this tab for a later turn (Cloud/session handoff).", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_mark_deliverable", "Keep this tab as a deliverable after the turn.", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_request_manual_handoff", "Request manual user control of a Cloud Browser tab.", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_pw_expect_file_chooser", "page.waitForEvent('filechooser').", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_pw_set_files", "fileChooser.setFiles(paths).", _obj({"tab_id": tab, "files": {"type": "array", "items": {"type": "string"}}, "multiple": _bool("Allow multiple")}, ["tab_id", "files"])),
        _tool("tab_dom_download_media", "dom_cua.downloadMedia by node_id.", _obj({"tab_id": tab, "node_id": _int("DOM node id"), "timeoutMs": _int("Timeout")}, ["tab_id", "node_id"])),
        _tool("tab_cua_download_media", "cua.downloadMedia at viewport coordinates.", _obj({"tab_id": tab, "x": _num("X"), "y": _num("Y"), "timeoutMs": _int("Timeout")}, ["tab_id", "x", "y"])),
        *(
            [
                _tool("start_audio_recording", "Helper start_audio_recording (computer-audio approval).", _obj({})),
                _tool("stop_audio_recording", "Helper stop_audio_recording.", _obj({})),
            ]
            if os.environ.get("SKY_ENABLE_AUDIO") == "1"
            else []
        ),
        _tool(
            "browser_history",
            "browser.history() — do not call speculatively.",
            _obj(
                {
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "limit": _int("Max entries"),
                    "from": _str("Lower bound ISO timestamp"),
                    "to": _str("Upper bound ISO timestamp"),
                }
            ),
        ),
    ] + tab_ops_definitions() + missing_tool_definitions()


def handle_extra(surface: Any, name: str, spec: dict[str, object]) -> Any:
    if name in TAB_OPS:
        return handle_tab_ops(surface, name, spec)
    if name in MISSING_TOOLS:
        return handle_missing(surface, name, spec)
    browser = surface.browser
    if name == "tab_list":
        lister = getattr(browser, "tabs_list", None)
        return lister() if callable(lister) else []
    if name == "tab_selected":
        selected = getattr(browser, "selected_tab", None)
        return selected() if callable(selected) else None
    if name == "browser_set_visible":
        setter = getattr(browser, "set_visible", None)
        if callable(setter):
            setter(spec.get("visible") is True)
        return {"visible": spec.get("visible") is True, "backend": "iab"}
    if name == "browser_get_visible":
        return {"visible": bool(getattr(browser, "visible", False)), "backend": "iab"}
    if name == "tab_mention_resolve":
        return _resolve_mention(surface, str(spec.get("link") or ""))
    if name == "browser_detect":
        from computer_use.detect import detect_backends

        hub = getattr(surface, "hub", None)
        session = getattr(browser, "session_id", "sess-iab")
        detected = detect_backends(hub, str(session))
        if hub and getattr(hub, "tabs", None):
            detected["extension"]["openTabs"] = hub.tabs
        return detected
    if name == "browser_open_tabs":
        hub = getattr(surface, "hub", None)
        if hub and hub.tabs:
            return {"tabs": hub.tabs, "type": "extension", "connected": hub.connected, "loginState": True}
        lister = getattr(browser, "tabs_list", None)
        tabs = lister() if callable(lister) else []
        return {"tabs": [item for item in tabs if item.get("backend") == "extension"], "type": "extension", "connected": False}
    if name == "browser_claim_tab":
        hub = getattr(surface, "hub", None)
        if hub and hub.connected:
            return hub.claim(str(spec.get("providerTabId") or ""), str(spec.get("title") or ""), str(spec.get("url") or ""))
        claim = getattr(browser, "claim_tab", None)
        if not callable(claim):
            return {"unavailable": True}
        return claim(str(spec.get("providerTabId") or ""), str(spec.get("title") or ""), str(spec.get("url") or ""))
    if name in {"tab_mark_handoff", "tab_mark_deliverable", "tab_request_manual_handoff"}:
        kind = "manual" if "manual" in name else ("deliverable" if "deliverable" in name else "handoff")
        marker = getattr(browser, "mark_handoff", None)
        if callable(marker):
            return marker(str(spec.get("tab_id") or ""), kind)
        return {"ok": True, "kind": kind}
    if name in {"tab_pw_set_files", "tab_pw_expect_file_chooser"}:
        setter = getattr(browser, "set_files", None)
        files = spec.get("files") if isinstance(spec.get("files"), list) else []
        if name == "tab_pw_expect_file_chooser":
            return {"event": "filechooser", "isMultiple": False}
        if callable(setter):
            return setter(str(spec.get("tab_id") or ""), [str(item) for item in files], spec.get("multiple") is True)
        if surface.pw.page is not None:
            with surface.pw.page.expect_file_chooser(timeout=8000) as pending:
                chooser = pending.value
            chooser.set_files(files)
            return {"ok": True, "backend": "playwright", "files": files}
        return {"ok": True, "files": files, "backend": "fake"}
    if name in {"tab_dom_download_media", "tab_cua_download_media"}:
        down = getattr(browser, "download_media", None)
        node = spec.get("node_id")
        if callable(down):
            return down(str(spec.get("tab_id") or ""), None if node is None else int(node), spec.get("x"), spec.get("y"))
        return {"ok": True, "action": "downloadMedia"}
    if name == "start_audio_recording":
        start = getattr(browser, "start_audio", None)
        helper = getattr(getattr(surface, "driver", None), "backend", None)
        rpc = getattr(helper, "_rpc", None)
        if callable(rpc):
            return rpc("start_audio_recording", spec)
        return start() if callable(start) else {"ok": True, "recording": True}
    if name == "stop_audio_recording":
        stop = getattr(browser, "stop_audio", None)
        helper = getattr(getattr(surface, "driver", None), "backend", None)
        rpc = getattr(helper, "_rpc", None)
        if callable(rpc):
            return rpc("stop_audio_recording", spec)
        return stop() if callable(stop) else {"ok": True, "recording": False}
    if name == "browser_history":
        queries = spec.get("queries") if isinstance(spec.get("queries"), list) else None
        qnames = [str(item) for item in queries] if queries else None
        getter = getattr(browser, "history_query", None)
        start, end = str(spec.get("from") or ""), str(spec.get("to") or "")
        hub = getattr(surface, "hub", None)
        if hub and getattr(hub, "connected", False) and getattr(hub, "server", None):
            result = hub.command(
                "history",
                {"query": " ".join(qnames or []), "limit": int(spec.get("limit") or 20), "from": start, "to": end},
            )
            if isinstance(result, dict) and isinstance(result.get("entries"), list):
                return {"entries": result["entries"], "backend": "extension"}
        if callable(getter):
            entries = list(getter(qnames, int(spec.get("limit") or 20), start, end))
        else:
            entries = []
        if type(browser).__name__ != "FakeBrowser":
            from computer_use.chrome_history import read_history

            seen = {str(item.get("url") or "") for item in entries}
            for row in read_history(qnames, int(spec.get("limit") or 20), start, end):
                if row["url"] not in seen:
                    entries.append(row)
        return {"entries": entries[: max(int(spec.get("limit") or 20), 1)]}
    return _playwright_extra(surface, name, spec)


def _resolve_mention(surface: Any, link: str) -> dict[str, Any]:
    mention = parse_tab_mention(link)
    browsers = surface.browser.list_browsers()
    family = mention["family"]
    browser_id = mention["browser_id"]
    matched = None
    for item in browsers:
        meta = item.get("metadata") or {}
        if family == "iab" and item.get("type") == "iab" and str(meta.get("codexSessionId") or "") == str(browser_id or ""):
            matched = item
        if family == "extension" and item.get("type") == "extension" and str(meta.get("extensionInstanceId") or "") == str(browser_id or ""):
            matched = item
    if matched is None:
        return {"unavailable": True, "reason": "browser mention no longer exists", "mention": mention}
    lister = getattr(surface.browser, "tabs_list", None)
    tabs = lister() if callable(lister) else []
    for info in tabs:
        if same_tab(info, mention):
            if family == "extension":
                return surface.browser.claim_tab(str(info.get("providerTabId") or ""), str(info.get("title") or ""), str(info.get("url") or ""))
            return {"id": info.get("id"), "unavailable": False, "type": "iab", "mention": mention}
    return {"unavailable": True, "reason": "tab mention no longer matches", "mention": mention}


def _playwright_extra(surface: Any, name: str, spec: dict[str, object]) -> Any:
    tab_id = str(spec.get("tab_id") or "")
    if name == "tab_pw_frame_locator":
        loc = surface.pw.put(tab_id, "css", "html", frame=str(spec.get("selector") or "iframe"))
        return {"locator_id": loc.id, "frame": loc.frame, "kind": "frame"}
    if name == "tab_pw_get_by_placeholder":
        loc = surface.pw.put(tab_id, "placeholder", str(spec.get("text") or ""), frame=str(spec.get("frame") or "") or None)
        return {"locator_id": loc.id, "kind": loc.kind, "query": loc.query}
    if name == "tab_pw_get_by_test_id":
        loc = surface.pw.put(tab_id, "testid", str(spec.get("test_id") or ""))
        return {"locator_id": loc.id, "kind": loc.kind, "query": loc.query}
    if name == "tab_pw_nth":
        src = surface.pw.get(str(spec.get("locator_id") or ""))
        loc = surface.pw.put(src.tab_id, src.kind, src.query, name=src.name, exact=src.exact, frame=src.frame, nth=int(spec["index"]))
        return {"locator_id": loc.id, "nth": loc.nth}
    if name == "tab_pw_expect_navigation":
        action = spec.get("action") if isinstance(spec.get("action"), dict) else {}
        if surface.pw.page is not None:
            kwargs: dict[str, Any] = {"timeout": 8000}
            if spec.get("url"):
                kwargs["url"] = str(spec.get("url"))
            with surface.pw.page.expect_navigation(**kwargs):
                if action:
                    surface.dispatch(str(action.get("name") or ""), dict(action.get("arguments") or {}))
        elif action:
            surface.dispatch(str(action.get("name") or ""), dict(action.get("arguments") or {}))
        return {"ok": True, "backend": "playwright" if surface.pw.page is not None else "fake"}
    if name == "tab_pw_wait_for_event":
        if surface.pw.page is not None and str(spec.get("event") or "download") == "download":
            try:
                with surface.pw.page.expect_download(timeout=1000) as pending:
                    pass
                download = pending.value
                return {"event": "download", "suggested_filename": download.suggested_filename, "backend": "playwright"}
            except Exception:
                return {"event": "download", "pending": True, "backend": "playwright"}
        tab = surface.browser.tab(tab_id) if hasattr(surface.browser, "tab") else None
        return {"event": spec.get("event") or "download", "suggested_filename": "download.bin", "url": getattr(tab, "url", ""), "backend": "fake"}
    if name == "tab_pw_wait_for_url":
        url = str(spec.get("url") or "")
        if surface.pw.page is not None:
            surface.pw.page.wait_for_url(url, timeout=8000)
            return {"ok": True, "url": surface.pw.page.url, "backend": "playwright"}
        return {"ok": True, "url": url, "backend": "fake"}
    if name in {"tab_pw_element_info", "tab_pw_element_screenshot"}:
        return _element_probe(surface, spec, name)
    return None


def _element_probe(surface: Any, spec: dict[str, object], name: str) -> dict[str, Any]:
    x, y = float(spec["x"]), float(spec["y"])
    info: list[dict[str, Any]] = []
    if surface.pw.page is not None:
        info = surface.pw.page.evaluate(
            """([x, y]) => {
              const el = document.elementFromPoint(x, y);
              if (!el) return [];
              const r = el.getBoundingClientRect();
              return [{tag: el.tagName.toLowerCase(), name: (el.innerText||el.getAttribute('aria-label')||'').slice(0,80),
                       x: r.x, y: r.y, width: r.width, height: r.height, interactable: !!(el.onclick || el.href || el.tagName==='INPUT' || el.tagName==='BUTTON' || el.tagName==='A')}];
            }""",
            [x, y],
        )
        shot = surface.pw.page.screenshot(type="png") if name.endswith("screenshot") else b""
    else:
        tab_id = str(spec.get("tab_id") or "")
        tab = surface.browser.tab(tab_id)
        for node in getattr(tab, "dom", []):
            info.append({"tag": node.get("tag"), "name": node.get("name"), "selector": node.get("selector"), "interactable": True})
        shot = solid_png() if name.endswith("screenshot") else b""
        info = info[:3]
    payload: dict[str, Any] = {"x": x, "y": y, "elements": info, "backend": "playwright" if surface.pw.page is not None else "fake"}
    if name.endswith("screenshot"):
        import base64

        payload["screenshot_bytes"] = len(shot)
        payload["screenshot_base64"] = base64.b64encode(shot).decode("ascii") if shot else ""
    return payload
