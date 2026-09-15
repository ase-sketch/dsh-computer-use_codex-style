"""Chrome DevTools HTTP discovery (official tab capability type=cdp)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def list_tabs(host: str = "127.0.0.1", port: int = 9222, timeout: float = 0.8) -> list[dict[str, Any]]:
    url = f"http://{host}:{port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    tabs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {None, "page", "tab"}:
            continue
        tabs.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "type": "cdp",
                "webSocketDebuggerUrl": item.get("webSocketDebuggerUrl"),
            }
        )
    return tabs
