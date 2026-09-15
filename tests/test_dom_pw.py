from __future__ import annotations

import unittest

from computer_use.browser_api import BrowserSurface
from computer_use.fake_backend import FakeDesktop
from computer_use.executor import ToolExecutor
from computer_use.driver import ComputerUse


class DomCuaAndPlaywrightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = ToolExecutor(ComputerUse(FakeDesktop()))

    def test_dom_cua_full_set(self) -> None:
        tab = self.executor.execute("tab_new", {"url": "https://example.com/"})["result"]
        tid = tab["id"]
        dom = self.executor.execute("tab_dom_get_visible_dom", {"tab_id": tid})["result"]
        self.assertGreaterEqual(len(dom["nodes"]), 1)
        node_id = int(dom["nodes"][2]["node_id"])
        click = self.executor.execute("tab_dom_click", {"tab_id": tid, "node_id": node_id})["result"]
        self.assertEqual(click["action"], "dom_cua.click")
        dbl = self.executor.execute("tab_dom_double_click", {"tab_id": tid, "node_id": node_id})["result"]
        self.assertEqual(dbl["action"], "dom_cua.double_click")
        typed = self.executor.execute("tab_dom_type", {"tab_id": tid, "text": "hi"})["result"]
        self.assertEqual(typed["text"], "hi")
        keys = self.executor.execute("tab_dom_keypress", {"tab_id": tid, "keys": ["Enter"]})["result"]
        self.assertEqual(keys["keys"], ["Enter"])
        scrolled = self.executor.execute("tab_dom_scroll", {"tab_id": tid, "scroll_x": 0, "scroll_y": 400})["result"]
        self.assertEqual(scrolled["scroll_y"], 400)

    def test_playwright_locators_on_fake(self) -> None:
        tab = self.executor.execute("tab_new", {"url": "https://example.com/"})["result"]
        tid = tab["id"]
        loc = self.executor.execute("tab_pw_get_by_role", {"tab_id": tid, "role": "link", "name": "More"})["result"]
        count = self.executor.execute("tab_pw_count", {"locator_id": loc["locator_id"]})["result"]
        self.assertGreaterEqual(count["count"], 1)
        text = self.executor.execute("tab_pw_inner_text", {"locator_id": loc["locator_id"]})["result"]
        self.assertIn("More", str(text.get("text")))
        css = self.executor.execute("tab_pw_locator", {"tab_id": tid, "selector": "input#q"})["result"]
        filled = self.executor.execute("tab_pw_fill", {"locator_id": css["locator_id"], "value": "openai"})["result"]
        self.assertTrue(filled.get("ok") or filled.get("action"))


if __name__ == "__main__":
    unittest.main()
