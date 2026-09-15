"""Gate: BR-21 browser notifications match the official hook.

The wrapper template, the two WebMCP sentences, the page-event discriminant and
the tab lifecycle events are re-extracted from the packaged browser-service.mjs
and compared with computer_use/browser_meta.py. The hook is then exercised end
to end, including through BrowserSurface.end_turn().

Usage:  python parity/check_browser_notifications.py
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FENCE = chr(96) * 3

#: evidence offsets the module docstring must cite (documentation gate).
REQUIRED_EVIDENCE = ("@1143565", "@679616", "@241933", "@1125570")


def official_root() -> Path | None:
    hits = sorted(glob.glob(os.path.expanduser("~/.codex/plugins/cache/openai-bundled/browser/*")))
    return Path(hits[-1]) if hits else None


def main() -> int:
    from computer_use import browser_meta as m
    from computer_use.browser_fake import FakeBrowser
    from computer_use.browser_api import BrowserSurface

    failures: list[str] = []
    root = official_root()
    if root is None:
        print("SKIP official browser package not found")
        return 0
    service = (root / "scripts" / "browser-service.mjs").read_text(
        encoding="utf-8", errors="replace"
    )

    # --- official template -------------------------------------------------
    wrapper_ok = ("Browser notifications:\n\n" in service
                  and "Browser notifications:" == m.BROWSER_NOTIFICATIONS_HEADER)
    print(f"  [{'OK ' if wrapper_ok else 'FAIL'}] official qB() wrapper template")
    if not wrapper_ok:
        failures.append("BROWSER_NOTIFICATIONS_HEADER does not match the official wrapper")
    ours = m.format_browser_notifications(["A", "B"])
    expected = "Browser notifications:\n\nA\n\nB\n"
    print(f"  [{'OK ' if ours == expected else 'FAIL'}] format_browser_notifications(['A','B'])")
    if ours != expected:
        failures.append(f"notification wrapper is {ours!r}, expected {expected!r}")
    if m.format_browser_notifications([]) != "":
        failures.append("an empty notification list must produce the empty string")
    else:
        print("  [OK ] an empty list produces the empty string")

    # --- sentences + discriminant -----------------------------------------
    available_prefix = "WebMCP tools are available in tab "
    gone_prefix = "WebMCP tools are no longer available in tab "
    for prefix, ours_text in ((available_prefix, m.WEBMCP_TOOLS_AVAILABLE),
                              (gone_prefix, m.WEBMCP_TOOLS_GONE)):
        ok = prefix in service and ours_text.startswith(prefix)
        print(f"  [{'OK ' if ok else 'FAIL'}] official sentence {prefix!r}")
        if not ok:
            failures.append(f"sentence {prefix!r} is not verbatim")
    discriminant_ok = ('type:"webmcp_changed",version:1' in service
                       and m.WEBMCP_CHANGED == "webmcp_changed"
                       and m.WEBMCP_CHANGED_VERSION == 1)
    print(f"  [{'OK ' if discriminant_ok else 'FAIL'}] official webmcp_changed discriminant")
    if not discriminant_ok:
        failures.append("WEBMCP_CHANGED / WEBMCP_CHANGED_VERSION drift from the official")
    events_ok = ('type:"tab_acquired"' in service and 'origin:"agent"' in service
                 and "sY=[_k]" in service and "takeEvents" in service
                 and "takePageEvents" in service)
    print(f"  [{'OK ' if events_ok else 'FAIL'}] official lifecycle events + contributor drain")
    if not events_ok:
        failures.append("the official tab lifecycle events / contributor drain are missing")

    # --- behavior ----------------------------------------------------------
    tools = [{"name": "x", "pageUrl": "https://page.test"}]
    tool_block = "\n".join(
        [available_prefix + "3:", "", FENCE + "json", '[{"name":"x"}]', FENCE]
    )
    first = m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "external"}],
        list_tools=lambda tab_id: tools,
    )
    expected_first = "Browser notifications:\n\n" + tool_block + "\n"
    print(f"  [{'OK ' if first == expected_first else 'FAIL'}] external acquire produces the block")
    if first != expected_first:
        failures.append(f"acquired-tab notification is {first!r}")
    cache: dict[int, str] = {}
    m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "external"}],
        list_tools=lambda tab_id: tools, cache=cache,
    )
    if not cache:
        failures.append("the per-tab WebMCP cache was not written")
    again = m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "external"}],
        list_tools=lambda tab_id: tools, cache=cache,
    )
    if again != "":
        failures.append("an unchanged tool list must not notify again")
    else:
        print("  [OK ] unchanged tools notify only once (official n === o branch)")
    gone = m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "external"}],
        list_tools=lambda tab_id: [], cache=cache,
    )
    if gone != "Browser notifications:\n\n" + gone_prefix + "3.\n":
        failures.append(f"a vanished tool list produced {gone!r}")
    else:
        print("  [OK ] a vanished tool list emits the official gone sentence")
    agent = m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "agent"}],
        list_tools=lambda tab_id: tools,
    )
    if agent != "":
        failures.append("an agent-origin acquisition must not notify")
    else:
        print("  [OK ] agent-origin acquisition stays silent (official origin filter)")
    disabled_cache: dict[int, str] = {1: "x"}
    disabled = m.take_browser_notifications(
        [], [{"type": "tab_acquired", "tabId": "3", "origin": "external"}],
        webmcp_enabled=False, list_tools=lambda tab_id: tools, cache=disabled_cache,
    )
    if disabled != "" or disabled_cache:
        failures.append("webmcp_enabled=False must clear the cache and stay silent")
    else:
        print("  [OK ] webmcp_enabled=False clears the cache (official yk())")

    # --- surface wiring ----------------------------------------------------
    surface = BrowserSurface(browser=FakeBrowser())
    tab = surface.dispatch("tab_new", {"url": "https://example.com/"})
    surface.browser.webmcp_fetch = lambda tab_id: [{"name": "tool-a"}]  # type: ignore[attr-defined]
    surface.lifecycle.record_acquired(str(tab["id"]), "external")
    outcome = surface.end_turn()
    has_notifications = bool(outcome.get("browserNotifications"))
    print(f"  [{'OK ' if has_notifications else 'FAIL'}] end_turn() carries browserNotifications")
    if not has_notifications:
        failures.append("BrowserSurface.end_turn() dropped the notification content item")
    empty = BrowserSurface(browser=FakeBrowser())
    empty.dispatch("tab_new", {"url": "https://example.com/"})
    outcome2 = empty.end_turn()
    if "browserNotifications" in outcome2:
        failures.append("end_turn() must omit the content item when there is nothing")
    else:
        print("  [OK ] end_turn() omits the content item when empty")
    drained = surface.dispatch("browser_notifications", {})
    if not isinstance(drained, dict) or "notifications" not in drained:
        failures.append("the browser_notifications command is not routable")
    else:
        print("  [OK ] the browser_notifications command is routable")

    # --- documentation gate ------------------------------------------------
    doc = m.__doc__ or ""
    missing = [offset for offset in REQUIRED_EVIDENCE if offset not in doc]
    print(f"  [{'OK ' if not missing else 'FAIL'}] official evidence offsets cited")
    if missing:
        failures.append(f"browser_meta docstring lost the evidence offsets: {missing}")

    for line in failures:
        print("FAIL " + line)
    print("browser notifications: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
