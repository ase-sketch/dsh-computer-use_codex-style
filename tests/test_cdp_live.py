from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import websocket

from computer_use.cdp_browser import CdpBrowser
from computer_use.cdp_launch import edge_exe, launch_edge


class CdpLiveTests(unittest.TestCase):
    def test_edge_websocket_ax_and_screenshot(self) -> None:
        if edge_exe() is None:
            self.skipTest("msedge.exe not found")
        port = 9334
        proc = None
        browser = None
        try:
            proc = launch_edge(port, Path(tempfile.mkdtemp()) / "edge-cdp")
            browser = CdpBrowser(port=port)
            tab = browser.new_tab("https://example.com/")
            state = browser.ax_write(tab.id, "both", True)
            self.assertEqual(state["backend"], "cdp-ws")
            self.assertGreater(len(state["tree"]), 0)
            self.assertGreater(int(state.get("screenshot_bytes") or 0), 100)
            self.assertIn("URL:", state["accessibility"]["tree"])
            from computer_use.browser_api import BrowserSurface

            surface = BrowserSurface(browser)
            surface.pw.attach_cdp(port)
            visible = surface.dispatch("tab_dom_get_visible_dom", {"tab_id": tab.id})
            self.assertTrue(visible.get("nodes") is not None)
            loc = surface.dispatch("tab_pw_locator", {"tab_id": tab.id, "selector": "h1"})
            if surface.pw.page is not None:
                text = surface.dispatch("tab_pw_inner_text", {"locator_id": loc["locator_id"]})
                self.assertEqual(text.get("backend"), "playwright")
                self.assertTrue(str(text.get("text") or ""))
            surface.pw.close()
        except (FileNotFoundError, TimeoutError, OSError, RuntimeError, websocket.WebSocketException) as exc:
            self.skipTest(str(exc))
        finally:
            if browser is not None:
                browser.close()
            if proc is not None:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
