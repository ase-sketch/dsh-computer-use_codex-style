from __future__ import annotations

import unittest

from computer_use.browser_mentions import parse_tab_mention
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop


class IabExtensionPlaywrightExtraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = ToolExecutor(ComputerUse(FakeDesktop()))

    def test_iab_visibility_and_tab_list(self) -> None:
        hidden = self.executor.execute("browser_get_visible", {})["result"]
        self.assertFalse(hidden["visible"])
        tab = self.executor.execute("tab_new", {"url": "https://example.com/", "browser": "iab"})["result"]
        self.assertEqual(tab["backend"], "iab")
        self.assertFalse(tab["visible"])
        self.executor.execute("browser_set_visible", {"visible": True})
        self.assertTrue(self.executor.execute("browser_get_visible", {})["result"]["visible"])
        listed = self.executor.execute("tab_list", {})["result"]
        self.assertEqual(listed[0]["providerTabId"], tab["providerTabId"])

    def test_extension_claim_fail_closed(self) -> None:
        tab = self.executor.execute("tab_new", {"url": "https://example.com/", "browser": "chrome"})["result"]
        self.assertEqual(tab["backend"], "extension")
        ok = self.executor.execute(
            "browser_claim_tab",
            {"providerTabId": tab["providerTabId"], "title": "Example Domain", "url": "https://example.com/"},
        )["result"]
        self.assertTrue(ok["claimed"])
        bad = self.executor.execute(
            "browser_claim_tab",
            {"providerTabId": tab["providerTabId"], "title": "stale", "url": "https://example.com/"},
        )["result"]
        self.assertTrue(bad["unavailable"])

    def test_tab_mention_iab_and_extension(self) -> None:
        tab = self.executor.execute("tab_new", {"url": "https://example.com/", "browser": "iab"})["result"]
        iab = (
            "plugin://browser@openai-bundled?mention=tab-v1"
            f"&browserId=sess-iab&tabId={tab['providerTabId']}"
            "&title=Example%20Domain&url=https%3A%2F%2Fexample.com%2F"
        )
        parsed = parse_tab_mention(iab)
        self.assertEqual(parsed["family"], "iab")
        resolved = self.executor.execute("tab_mention_resolve", {"link": iab})["result"]
        self.assertFalse(resolved.get("unavailable"))
        ext_tab = self.executor.execute("tab_new", {"url": "https://example.com/", "browser": "extension"})["result"]
        chrome = (
            "plugin://chrome@openai-bundled?mention=tab-v1&source=extension"
            f"&browserId=ext-local&tabId={ext_tab['providerTabId']}"
            "&title=Example%20Domain&url=https%3A%2F%2Fexample.com%2F"
        )
        self.assertEqual(parse_tab_mention(chrome)["family"], "extension")
        claimed = self.executor.execute("tab_mention_resolve", {"link": chrome})["result"]
        self.assertTrue(claimed.get("claimed"))

    def test_playwright_corners(self) -> None:
        tab = self.executor.execute("tab_new", {"url": "https://example.com/"})["result"]
        tid = tab["id"]
        frame = self.executor.execute("tab_pw_frame_locator", {"tab_id": tid, "selector": "iframe#app"})["result"]
        self.assertEqual(frame["kind"], "frame")
        loc = self.executor.execute("tab_pw_locator", {"tab_id": tid, "selector": "a"})["result"]
        nth = self.executor.execute("tab_pw_nth", {"locator_id": loc["locator_id"], "index": 0})["result"]
        self.assertEqual(nth["nth"], 0)
        nav = self.executor.execute(
            "tab_pw_expect_navigation",
            {"tab_id": tid, "action": {"name": "tab_goto", "arguments": {"tab_id": tid, "url": "https://example.com/"}}},
        )["result"]
        self.assertTrue(nav["ok"])
        download = self.executor.execute("tab_pw_wait_for_event", {"tab_id": tid, "event": "download"})["result"]
        self.assertEqual(download["event"], "download")
        info = self.executor.execute("tab_pw_element_info", {"tab_id": tid, "x": 40, "y": 40})["result"]
        self.assertTrue(info["elements"])
        shot = self.executor.execute("tab_pw_element_screenshot", {"tab_id": tid, "x": 40, "y": 40})["result"]
        self.assertGreater(shot["screenshot_bytes"], 0)
        ph = self.executor.execute("tab_pw_get_by_placeholder", {"tab_id": tid, "text": "Search"})["result"]
        self.assertEqual(ph["kind"], "placeholder")


if __name__ == "__main__":
    unittest.main()
