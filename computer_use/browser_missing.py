"""Remaining official api.json methods as named tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from computer_use.tools import _bool, _int, _obj, _str, _tool

MISSING_TOOLS = (
    "browser_get",
    "browser_get_default",
    "browser_get_for_url",
    "tab_ax_get",
    "tab_ax_drag",
    "tab_ax_select_text",
    "tab_pw_check",
    "tab_pw_uncheck",
    "tab_pw_set_checked",
    "tab_pw_dblclick",
    "tab_pw_press",
    "tab_pw_press_sequentially",
    "tab_pw_type",
    "tab_pw_select_option",
    "tab_pw_filter",
    "tab_pw_and",
    "tab_pw_or",
    "tab_pw_nested_locator",
    "tab_pw_all",
    "tab_pw_all_text_contents",
    "tab_pw_evaluate_all",
    "tab_pw_get_attribute",
    "tab_pw_text_content",
    "tab_pw_is_visible",
    "tab_pw_is_enabled",
    "tab_pw_wait_for",
    "tab_pw_file_chooser_is_multiple",
    "tab_alert_dismiss",
    "tab_confirm_accept",
    "tab_confirm_dismiss",
    "tab_prompt_accept",
    "tab_prompt_dismiss",
    "tab_beforeunload_dismiss",
    "tab_dev_logs",
    "documentation_get",
    "tab_inject_dialog",
    "tab_ax_perform_secondary_action",
    "tab_pw_first",
    "tab_pw_last",
    "tab_pw_locator_evaluate",
    "browser_capabilities_get",
    "tab_capabilities_get",
    "tab_cdp_send",
    "tab_cdp_read_events",
    "tab_pw_download_suggested_filename",
    "tab_pw_download_url",
    "tab_pw_download_cancel",
    "tab_pw_download_failure",
    "browser_id",
)


def missing_tool_definitions() -> list[dict[str, Any]]:
    tab = _str("Tab id")
    loc = _str("Locator id")
    return [
        _tool("browser_get", "Browsers.get(id) by id or client type.", _obj({"id": _str("iab|extension|cdp|browser id")}, ["id"])),
        _tool("browser_get_default", "Browsers.getDefault().", _obj({})),
        _tool("browser_get_for_url", "Browsers.getForUrl(url).", _obj({"url": _str("URL")}, ["url"])),
        _tool(
            "tab_ax_get",
            "ax.get(mode?, options?) — accessibility state string without emitting (prefer write() to display).",
            _obj({"tab_id": tab, "mode": _str("state"), "disableDiffing": _bool("Full tree instead of diff")}, ["tab_id"]),
        ),
        _tool(
            "tab_ax_drag",
            "ax.drag(from: AXPoint, to: AXPoint) — viewport coordinates.",
            _obj(
                {
                    "tab_id": tab,
                    "from": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "to": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "from_x": {"type": "number"},
                    "from_y": {"type": "number"},
                    "to_x": {"type": "number"},
                    "to_y": {"type": "number"},
                },
                ["tab_id"],
            ),
        ),
        _tool("tab_ax_select_text", "ax.selectText inside an indexed element.", _obj({"tab_id": tab, "element_index": _int("AX index"), "text": _str("Text"), "prefix": _str("Disambiguating prefix"), "suffix": _str("Disambiguating suffix"), "selectionType": _str("text|cursor_before|cursor_after")}, ["tab_id", "element_index", "text"])),
        _tool("tab_ax_perform_secondary_action", "ax.performSecondaryAction(elementIndex, action).", _obj({"tab_id": tab, "element_index": _int("AX index"), "action": _str("Expand|Collapse|...")}, ["tab_id", "element_index", "action"])),
        _tool("tab_pw_first", "locator.first.", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_last", "locator.last.", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_locator_evaluate", "locator.evaluate(fn) on the first match.", _obj({"locator_id": loc, "expression": _str("JS function body or expression")}, ["locator_id"])),
        _tool("browser_capabilities_get", "browser.capabilities.get(id).", _obj({"id": _str("visibility|botDetection")}, ["id"])),
        _tool("tab_capabilities_get", "tab.capabilities.get(id).", _obj({"tab_id": tab, "id": _str("cdp|pageAssets|webmcp")}, ["tab_id", "id"])),
        _tool("tab_pw_check", "locator.check().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_uncheck", "locator.uncheck().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_set_checked", "locator.setChecked(checked).", _obj({"locator_id": loc, "checked": _bool("Checked")}, ["locator_id", "checked"])),
        _tool("tab_pw_dblclick", "locator.dblclick().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_press", "locator.press(key).", _obj({"locator_id": loc, "key": _str("Key")}, ["locator_id", "key"])),
        _tool("tab_pw_press_sequentially", "locator.pressSequentially(text).", _obj({"locator_id": loc, "text": _str("Text")}, ["locator_id", "text"])),
        _tool("tab_pw_type", "locator.type(text) without clearing.", _obj({"locator_id": loc, "text": _str("Text")}, ["locator_id", "text"])),
        _tool("tab_pw_select_option", "locator.selectOption(value).", _obj({"locator_id": loc, "value": _str("Option")}, ["locator_id", "value"])),
        _tool("tab_pw_filter", "locator.filter({hasText}).", _obj({"locator_id": loc, "hasText": _str("Text")}, ["locator_id"])),
        _tool("tab_pw_and", "locator.and(other).", _obj({"locator_id": loc, "other_id": _str("Other locator")}, ["locator_id", "other_id"])),
        _tool("tab_pw_or", "locator.or(other).", _obj({"locator_id": loc, "other_id": _str("Other locator")}, ["locator_id", "other_id"])),
        _tool("tab_pw_nested_locator", "locator.locator(selector).", _obj({"locator_id": loc, "selector": _str("Child CSS")}, ["locator_id", "selector"])),
        _tool("tab_pw_all", "locator.all() — list of locators.", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_all_text_contents", "locator.allTextContents().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_evaluate_all", "locator.evaluateAll(fn).", _obj({"locator_id": loc, "expression": _str("JS")}, ["locator_id"])),
        _tool("tab_pw_get_attribute", "locator.getAttribute(name).", _obj({"locator_id": loc, "name": _str("Attribute")}, ["locator_id", "name"])),
        _tool("tab_pw_text_content", "locator.textContent().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_is_visible", "locator.isVisible().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_is_enabled", "locator.isEnabled().", _obj({"locator_id": loc}, ["locator_id"])),
        _tool("tab_pw_wait_for", "locator.waitFor(state).", _obj({"locator_id": loc, "state": _str("visible|hidden|attached")}, ["locator_id"])),
        _tool("tab_pw_file_chooser_is_multiple", "fileChooser.isMultiple().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_alert_dismiss", "AlertDialog.dismiss().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_confirm_accept", "ConfirmDialog.accept().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_confirm_dismiss", "ConfirmDialog.dismiss().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_prompt_accept", "PromptDialog.accept(text).", _obj({"tab_id": tab, "text": _str("Prompt text")}, ["tab_id"])),
        _tool("tab_prompt_dismiss", "PromptDialog.dismiss().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_beforeunload_dismiss", "BeforeUnloadDialog.dismiss().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool(
            "tab_dev_logs",
            "tab.dev.logs().",
            _obj(
                {
                    "tab_id": tab,
                    "filter": _str("Substring"),
                    "limit": _int("Max"),
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "debug|info|log|warn|error|warning"},
                    "url": _str("Substring filter on log url"),
                },
                ["tab_id"],
            ),
        ),
        _tool("documentation_get", "Documentation.get(name) packaged docs.", _obj({"name": _str("extensionless relative path")}, ["name"])),
        _tool("tab_inject_dialog", "Test/helper: inject a JS dialog of a given type.", _obj({"tab_id": tab, "type": _str("alert|confirm|prompt|beforeunload"), "message": _str("Message")}, ["tab_id", "type"])),
        _tool("tab_cdp_send", "tab.capabilities.get('cdp').send(method, params).", _obj({"tab_id": tab, "method": _str("CDP method"), "params": {"type": "object"}}, ["tab_id", "method"])),
        _tool(
            "tab_cdp_read_events",
            "tab.capabilities.get('cdp').readEvents({afterSequence, methods, timeoutMs}).",
            _obj(
                {
                    "tab_id": tab,
                    "afterSequence": _int("Return events after this sequence"),
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "timeoutMs": _int("Wait for more events"),
                },
                ["tab_id"],
            ),
        ),
        _tool("tab_pw_download_suggested_filename", "download.suggestedFilename().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_pw_download_url", "download.url().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_pw_download_cancel", "download.cancel().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("tab_pw_download_failure", "download.failure().", _obj({"tab_id": tab}, ["tab_id"])),
        _tool("browser_id", "Browser.browserId property.", _obj({"id": _str("Optional browser id to inspect")})),
    ]


def handle_missing(surface: Any, name: str, spec: dict[str, object]) -> Any:
    browser = surface.browser
    tab_id = str(spec.get("tab_id") or "")
    if name == "browser_get":
        getter = getattr(browser, "get_browser", None)
        if callable(getter):
            return getter(str(spec.get("id") or ""))
        for item in browser.list_browsers():
            if item.get("id") == spec.get("id") or item.get("type") == spec.get("id"):
                return item
        raise KeyError(spec.get("id"))
    if name == "browser_get_default":
        getter = getattr(browser, "get_default_browser", None)
        if callable(getter):
            return getter()
        browsers = browser.list_browsers()
        return next((item for item in browsers if item.get("type") == "iab"), browsers[0])
    if name == "browser_get_for_url":
        getter = getattr(browser, "get_browser_for_url", None)
        if callable(getter):
            return getter(str(spec.get("url") or ""))
        return handle_missing(surface, "browser_get_default", {})
    if name == "tab_ax_get":
        getter = getattr(browser, "ax_get_state", None)
        disable = spec.get("disableDiffing", True) is not False
        if callable(getter):
            return getter(tab_id, str(spec.get("mode") or "state"), disable)
        write = getattr(browser, "ax_write", None)
        if callable(write):
            raw = write(tab_id, str(spec.get("mode") or "state"), disable)
            tree = ""
            if isinstance(raw, dict):
                acc = raw.get("accessibility") if isinstance(raw.get("accessibility"), dict) else {}
                tree = str(acc.get("tree") or raw.get("tree_text") or "")
            return {"tree": tree, "emitted": False, "mode": spec.get("mode") or "state"}
        return {"tree": "", "emitted": False}
    if name == "tab_ax_drag":
        from_pt = spec.get("from") if isinstance(spec.get("from"), list) else None
        to_pt = spec.get("to") if isinstance(spec.get("to"), list) else None
        fx = float(from_pt[0]) if from_pt else float(spec.get("from_x") or 0)
        fy = float(from_pt[1]) if from_pt else float(spec.get("from_y") or 0)
        tx = float(to_pt[0]) if to_pt else float(spec.get("to_x") or 0)
        ty = float(to_pt[1]) if to_pt else float(spec.get("to_y") or 0)
        dragger = getattr(browser, "ax_drag_points", None)
        if callable(dragger):
            return dragger(tab_id, fx, fy, tx, ty)
        return browser.cua_drag(tab_id, [{"x": fx, "y": fy}, {"x": tx, "y": ty}])
    if name == "tab_ax_select_text":
        return browser.ax_select_text(tab_id, int(spec["element_index"]), str(spec.get("text") or ""))
    if name == "tab_ax_perform_secondary_action":
        fn = getattr(browser, "ax_perform_secondary", None)
        if callable(fn):
            return fn(tab_id, int(spec["element_index"]), str(spec.get("action") or ""))
        return {"ok": True, "action": spec.get("action"), "element_index": spec.get("element_index")}
    if name == "browser_capabilities_get":
        return _capability("browser", str(spec.get("id") or ""), surface)
    if name == "tab_capabilities_get":
        return _capability("tab", str(spec.get("id") or ""), surface, tab_id)
    if name in {"tab_pw_first", "tab_pw_last"}:
        src = surface.pw.get(str(spec.get("locator_id") or ""))
        loc = surface.pw.put(src.tab_id, src.kind, src.query, name=src.name, exact=src.exact, frame=src.frame, nth=0 if name.endswith("first") else -1)
        return {"locator_id": loc.id, "nth": loc.nth, "kind": "first" if loc.nth == 0 else "last"}
    if name == "tab_pw_locator_evaluate":
        loc = surface.pw.get(str(spec.get("locator_id") or ""))
        hits = []
        matcher = getattr(browser, "pw_match", None)
        if callable(matcher):
            hits = matcher(loc.tab_id, loc.kind, loc.query, loc.name)
        handle = surface.pw.resolve(loc)
        if handle is not None:
            first = handle.first if hasattr(handle, "first") else handle
            value = first.evaluate(str(spec.get("expression") or "el => el.tagName"))
            return {"value": value, "backend": "playwright"}
        return {"value": hits[0] if hits else None, "backend": "fake"}
    if name == "tab_inject_dialog":
        return browser.inject_dialog(tab_id, str(spec.get("type") or "alert"), str(spec.get("message") or "hello"))
    if name == "tab_dev_logs":
        levels = spec.get("levels") if isinstance(spec.get("levels"), list) else None
        try:
            logs = browser.tab_logs(tab_id, levels, str(spec.get("filter") or ""), int(spec.get("limit") or 50), str(spec.get("url") or ""))
        except TypeError:
            logs = browser.tab_logs(tab_id, levels, str(spec.get("filter") or ""), int(spec.get("limit") or 50))
        return {"logs": logs}
    if name == "documentation_get":
        return _documentation_get(str(spec.get("name") or ""))
    if name == "tab_cdp_send":
        sender = getattr(browser, "cdp_send", None)
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        if callable(sender):
            return sender(tab_id, str(spec.get("method") or ""), params)
        conn = getattr(getattr(browser, "tab", lambda _: None)(tab_id), "conn", None)
        if conn is not None:
            return {"result": conn.call(str(spec.get("method") or "Runtime.evaluate"), params), "backend": "cdp-ws"}
        return {"error": "no cdp"}
    if name == "tab_cdp_read_events":
        reader = getattr(browser, "cdp_read_events", None)
        methods = spec.get("methods") if isinstance(spec.get("methods"), list) else None
        after = int(spec.get("afterSequence") or 0)
        timeout = int(spec.get("timeoutMs") or 0)
        if callable(reader):
            try:
                return {"events": reader(tab_id, after, methods, timeout)}
            except TypeError:
                return {"events": reader(tab_id, after, methods)}
        conn = getattr(getattr(browser, "tab", lambda _: None)(tab_id), "conn", None)
        if conn is not None:
            return {"events": conn.read_events(after, [str(item) for item in methods] if methods else None, timeout)}
        return {"events": []}
    if name.startswith("tab_pw_download_"):
        return _download_object(browser, name, tab_id, getattr(surface, "pw", None))
    if name == "browser_id":
        ident = str(spec.get("id") or getattr(browser, "default_browser_id", "") or "iab")
        getter = getattr(browser, "get_browser", None)
        info = getter(ident) if callable(getter) else {"id": ident, "type": ident}
        return {"browserId": info.get("id") or ident, "type": info.get("type"), "metadata": info.get("metadata")}
    if name.startswith("tab_alert_") or name.startswith("tab_confirm_") or name.startswith("tab_prompt_") or name.startswith("tab_beforeunload_"):
        return _typed_dialog(browser, name, spec, tab_id)
    if name.startswith("tab_pw_"):
        return _locator_missing(surface, name, spec)
    return None


def _capability(scope: str, cap_id: str, surface: Any, tab_id: str = "") -> dict[str, Any]:
    browser_caps = {
        "visibility": {"id": "visibility", "description": "Show/hide IAB", "methods": ["get", "set"]},
        "botDetection": {"id": "botDetection", "description": "Bot-detection hints", "methods": ["get"]},
    }
    tab_caps = {
        "cdp": {"id": "cdp", "description": "Raw CDP send/readEvents", "methods": ["send", "readEvents"]},
        "pageAssets": {"id": "pageAssets", "description": "Asset inventory and bundle", "methods": ["list", "bundle"]},
        "webmcp": {"id": "webmcp", "description": "Page-defined tools", "methods": ["fetchTools", "call"]},
    }
    table = browser_caps if scope == "browser" else tab_caps
    cap = table.get(cap_id)
    if cap is None:
        return {"id": cap_id, "found": False}
    extra: dict[str, Any] = {}
    if cap_id == "visibility":
        extra["visible"] = bool(getattr(surface.browser, "visible", False))
    if cap_id == "botDetection":
        extra.update(getattr(surface.browser, "bot_detection", {}))
    if cap_id == "webmcp" and tab_id:
        fetch = getattr(surface.browser, "webmcp_fetch", None)
        extra["tools"] = fetch(tab_id) if callable(fetch) else {"tools": []}
    if cap_id == "pageAssets" and tab_id:
        lister = getattr(surface.browser, "page_assets_list", None)
        extra["inventory"] = lister(tab_id) if callable(lister) else {}
    return {**cap, "found": True, "scope": scope, **extra}


def _download_object(browser: Any, name: str, tab_id: str, pw: Any = None) -> dict[str, Any]:
    last = None
    if pw is not None:
        getter_pw = getattr(pw, "last_download", None)
        if callable(getter_pw):
            last = getter_pw()
    if last is None:
        getter = getattr(browser, "last_download", None)
        if callable(getter):
            last = getter(tab_id)
        else:
            downloads = getattr(browser.tab(tab_id), "downloads", [])
            last = downloads[-1] if downloads else None
    if name == "tab_pw_download_cancel":
        if pw is not None and getattr(pw, "downloads", None):
            return pw.cancel_last()
        cancel = getattr(browser, "cancel_download", None)
        if callable(cancel):
            return cancel(tab_id)
        if isinstance(last, dict):
            last["cancelled"] = True
            last["failure"] = "cancelled"
            return {"cancelled": True}
        return {"cancelled": False, "error": "no download"}
    if last is None:
        return {"value": None, "error": "no download"}
    if name.endswith("suggested_filename"):
        return {"suggestedFilename": last.get("suggestedFilename") or last.get("filename")}
    if name.endswith("download_url"):
        return {"url": last.get("url")}
    if name.endswith("failure"):
        handle = last.get("handle") if isinstance(last, dict) else None
        if handle is not None:
            try:
                failed = handle.failure()
                last["failure"] = failed
            except Exception:
                pass
        return {"failure": last.get("failure")}
    if name.endswith("path") or name == "tab_pw_download_path":
        stored = last.get("path")
        if stored and Path(str(stored)).is_file() and Path(str(stored)).stat().st_size > 0:
            return {"path": str(stored)}
        handle = last.get("handle")
        if handle is not None:
            try:
                saved = handle.path()
                if saved:
                    last["path"] = str(saved)
                    return {"path": str(saved)}
            except Exception:
                pass
        return {"path": last.get("path")}
    return last


def _documentation_get(name: str) -> dict[str, Any]:
    stem = name.replace("\\", "/").split("/")[-1]
    if stem.endswith(".md"):
        stem = stem[:-3]
    roots = [Path(__file__).with_name("prompts"), Path(__file__).resolve().parents[1] / "docs"]
    bundled = Path.home() / ".codex" / "plugins" / "cache" / "openai-bundled"
    if bundled.is_dir():
        roots.extend(bundled.glob("browser/*/docs"))
        roots.extend(bundled.glob("computer-use/*/docs"))
    sky = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "OpenAI" / "Codex" / "runtimes"
    if sky.is_dir():
        roots.extend(sky.glob("**/node_modules/@oai/sky/docs"))
    path = None
    for root in roots:
        candidate = root / f"{stem}.md"
        if candidate.is_file():
            path = candidate
            break
        matches = list(root.glob(f"*{stem}*.md")) if root.is_dir() else []
        if matches:
            path = matches[0]
            break
    if path is None or not path.is_file():
        return {"name": name, "found": False, "text": ""}
    text = path.read_text(encoding="utf-8")
    return {"name": stem, "found": True, "path": path.name, "text": text, "bytes": len(text)}


def _typed_dialog(browser: Any, name: str, spec: dict[str, object], tab_id: str) -> dict[str, Any]:
    mapping = {
        "tab_alert_dismiss": ("alert", False),
        "tab_confirm_accept": ("confirm", True),
        "tab_confirm_dismiss": ("confirm", False),
        "tab_prompt_accept": ("prompt", True),
        "tab_prompt_dismiss": ("prompt", False),
        "tab_beforeunload_dismiss": ("beforeunload", False),
    }
    kind, accept = mapping[name]
    return browser.handle_dialog(tab_id, accept, str(spec.get("text") or ""), expect=kind)


def _locator_missing(surface: Any, name: str, spec: dict[str, object]) -> Any:
    browser = surface.browser
    if name == "tab_pw_file_chooser_is_multiple":
        tab = browser.tab(str(spec.get("tab_id") or ""))
        return {"isMultiple": bool(getattr(tab, "file_chooser_multiple", False))}
    locator_id = str(spec.get("locator_id") or "")
    loc = surface.pw.get(locator_id)
    hits = []
    chain = getattr(loc, "chain", None)
    chained = getattr(browser, "pw_match_chain", None)
    matcher = getattr(browser, "pw_match", None)
    if chain and callable(chained):
        hits = chained(loc.tab_id, chain)
    elif callable(matcher):
        hits = matcher(loc.tab_id, loc.kind, loc.query, loc.name)
    handle = surface.pw.resolve(loc)
    if handle is not None:
        return _pw_live_missing(name, handle, spec, loc, hits)
    tab_id = loc.tab_id
    node = hits[0] if hits else None
    node_id = int(node["node_id"]) if node else None
    if name == "tab_pw_check" and node_id is not None:
        return browser.set_checked(tab_id, node_id, True)
    if name == "tab_pw_uncheck" and node_id is not None:
        return browser.set_checked(tab_id, node_id, False)
    if name == "tab_pw_set_checked" and node_id is not None:
        return browser.set_checked(tab_id, node_id, spec.get("checked") is not False)
    if name == "tab_pw_dblclick" and node_id is not None:
        return browser.dom_double_click(tab_id, node_id)
    if name == "tab_pw_press":
        return browser.dom_keypress(tab_id, [str(spec.get("key") or "Enter")])
    if name in {"tab_pw_press_sequentially", "tab_pw_type"}:
        return browser.dom_type(tab_id, str(spec.get("text") or ""))
    if name == "tab_pw_select_option" and node_id is not None:
        return browser.select_option(tab_id, node_id, str(spec.get("value") or ""))
    if name == "tab_pw_filter":
        child = surface.pw.put(tab_id, loc.kind, loc.query, name=str(spec.get("hasText") or loc.name or ""), frame=loc.frame)
        return {"locator_id": child.id, "kind": "filter", "hasText": spec.get("hasText")}
    if name in {"tab_pw_and", "tab_pw_or"}:
        other = surface.pw.get(str(spec.get("other_id") or ""))
        child = surface.pw.put(tab_id, loc.kind, loc.query + "|" + other.query, name=loc.name, frame=loc.frame)
        return {"locator_id": child.id, "kind": name.split("_")[-1], "left": loc.id, "right": other.id}
    if name == "tab_pw_nested_locator":
        child = surface.pw.put(tab_id, "css", str(spec.get("selector") or ""), frame=loc.frame)
        return {"locator_id": child.id, "parent": loc.id, "kind": "nested"}
    if name == "tab_pw_all":
        ids = []
        for index, _hit in enumerate(hits):
            child = surface.pw.put(tab_id, loc.kind, loc.query, name=loc.name, nth=index)
            ids.append(child.id)
        return {"locators": ids, "count": len(ids)}
    if name == "tab_pw_all_text_contents":
        return {"texts": [str(item.get("name") or "") for item in hits]}
    if name == "tab_pw_evaluate_all":
        return {"value": [item.get("selector") for item in hits], "count": len(hits)}
    if name == "tab_pw_get_attribute":
        attr = str(spec.get("name") or "")
        value = None if not node else node.get(attr, node.get("selector"))
        return {"name": attr, "value": value}
    if name == "tab_pw_text_content":
        return {"text": None if not node else str(node.get("name") or "")}
    if name == "tab_pw_is_visible":
        return {"visible": bool(hits)}
    if name == "tab_pw_is_enabled":
        return {"enabled": bool(hits) and (not node or node.get("disabled") is not True)}
    if name == "tab_pw_wait_for":
        return {"ok": True, "state": spec.get("state") or "visible", "matched": bool(hits)}
    return {"ok": True, "locator_id": loc.id}


def _pw_live_missing(name: str, handle: Any, spec: dict[str, object], loc: Any, hits: list) -> Any:
    first = handle.first if hasattr(handle, "first") else handle
    if name == "tab_pw_check":
        first.check()
        return {"ok": True, "checked": True, "backend": "playwright"}
    if name == "tab_pw_uncheck":
        first.uncheck()
        return {"ok": True, "checked": False, "backend": "playwright"}
    if name == "tab_pw_set_checked":
        first.set_checked(spec.get("checked") is not False)
        return {"ok": True, "checked": spec.get("checked") is not False, "backend": "playwright"}
    if name == "tab_pw_dblclick":
        first.dblclick()
        return {"ok": True, "action": "locator.dblclick", "backend": "playwright"}
    if name == "tab_pw_press":
        first.press(str(spec.get("key") or "Enter"))
        return {"ok": True, "backend": "playwright"}
    if name == "tab_pw_press_sequentially":
        first.press_sequentially(str(spec.get("text") or ""))
        return {"ok": True, "backend": "playwright"}
    if name == "tab_pw_type":
        first.type(str(spec.get("text") or ""))
        return {"ok": True, "backend": "playwright"}
    if name == "tab_pw_select_option":
        first.select_option(str(spec.get("value") or ""))
        return {"ok": True, "value": spec.get("value"), "backend": "playwright"}
    if name == "tab_pw_get_attribute":
        return {"name": spec.get("name"), "value": first.get_attribute(str(spec.get("name") or "")), "backend": "playwright"}
    if name == "tab_pw_text_content":
        return {"text": first.text_content(), "backend": "playwright"}
    if name == "tab_pw_is_visible":
        return {"visible": first.is_visible(), "backend": "playwright"}
    if name == "tab_pw_is_enabled":
        return {"enabled": first.is_enabled(), "backend": "playwright"}
    if name == "tab_pw_wait_for":
        first.wait_for(state=str(spec.get("state") or "visible"))
        return {"ok": True, "backend": "playwright"}
    if name == "tab_pw_all_text_contents":
        return {"texts": handle.all_text_contents(), "backend": "playwright"}
    if name == "tab_pw_all":
        return {"count": handle.count(), "backend": "playwright"}
    return {"ok": True, "locator_id": loc.id, "backend": "playwright"}
