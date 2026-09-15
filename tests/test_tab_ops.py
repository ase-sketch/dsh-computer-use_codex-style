from __future__ import annotations

import unittest
from pathlib import Path

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop


class TabOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = ToolExecutor(ComputerUse(FakeDesktop()))
        self.tab = self.ex.execute("tab_new", {"url": "https://example.com/"})["result"]
        self.tid = self.tab["id"]

    def test_navigation_dialog_clipboard_cua(self) -> None:
        self.ex.execute("tab_goto", {"tab_id": self.tid, "url": "https://example.com/more"})
        back = self.ex.execute("tab_back", {"tab_id": self.tid})["result"]
        self.assertEqual(back["action"], "back")
        fwd = self.ex.execute("tab_forward", {"tab_id": self.tid})["result"]
        self.assertEqual(fwd["action"], "forward")
        self.assertEqual(self.ex.execute("tab_reload", {"tab_id": self.tid})["result"]["action"], "reload")
        self.assertEqual(self.ex.execute("tab_title", {"tab_id": self.tid})["result"]["title"], "Example Domain")
        self.ex.execute("tab_clipboard_write_text", {"tab_id": self.tid, "text": "hello"})
        self.assertEqual(self.ex.execute("tab_clipboard_read_text", {"tab_id": self.tid})["result"]["text"], "hello")
        click = self.ex.execute("tab_cua_click", {"tab_id": self.tid, "x": 12, "y": 34})["result"]
        self.assertEqual(click["action"], "cua.click")
        drag = self.ex.execute("tab_cua_drag", {"tab_id": self.tid, "path": [{"x": 1, "y": 1}, {"x": 8, "y": 8}]})["result"]
        self.assertEqual(drag["action"], "cua.drag")
        dialog = self.ex.execute("tab_get_js_dialog", {"tab_id": self.tid})["result"]
        self.assertIsNone(dialog["dialog"])
        closed = self.ex.execute("tab_close", {"tab_id": self.tid})["result"]
        self.assertEqual(closed["closed"], self.tid)

    def test_content_context_capabilities_assets_mcp(self) -> None:
        tid = self.tid
        exported = self.ex.execute("tab_content_export", {"tab_id": tid})["result"]
        self.assertTrue(exported["path"].endswith(".txt"))
        gsuite = self.ex.execute("tab_content_export_gsuite", {"tab_id": tid, "type": "md"})["result"]
        self.assertTrue(gsuite["path"].endswith(".md"))
        yt = self.ex.execute("tab_content_export_youtube", {"tab_id": tid})["result"]
        self.assertIn("YouTube", Path(yt["path"]).read_text(encoding="utf-8"))
        bg = self.ex.execute("tabs_content", {"urls": ["https://example.com/"], "contentType": "text"})["result"]
        self.assertIn("Example Domain", bg["results"][0]["content"])
        ctx = self.ex.execute(
            "browser_get_tab_context",
            {"providerTabId": self.tab["providerTabId"], "title": "Example Domain", "url": "https://example.com/"},
        )["result"]
        self.assertFalse(ctx.get("claimed"))
        self.assertEqual(ctx["kind"], "text")
        self.ex.execute("browser_name_session", {"name": "demo"})
        caps = self.ex.execute("browser_capabilities_list", {})["result"]["capabilities"]
        self.assertTrue(any(item["id"] == "visibility" for item in caps))
        tcaps = self.ex.execute("tab_capabilities_list", {"tab_id": tid})["result"]["capabilities"]
        self.assertTrue(any(item["id"] == "webmcp" for item in tcaps))
        mcp = self.ex.execute("tab_webmcp_fetch_tools", {"tab_id": tid})["result"]
        self.assertEqual(mcp["tools"], [])
        assets = self.ex.execute("tab_page_assets_list", {"tab_id": tid})["result"]
        self.assertEqual(assets["summary"]["totalCount"], 1)
        bundle = self.ex.execute("tab_page_assets_bundle", {"tab_id": tid, "inventoryId": assets["id"]})["result"]
        self.assertTrue(bundle["manifestPath"])
        bot = self.ex.execute("browser_bot_detection", {})["result"]
        self.assertEqual(bot["id"], "botDetection")
        loc = self.ex.execute("tab_pw_locator", {"tab_id": tid, "selector": "a"})["result"]
        media = self.ex.execute("tab_pw_download_media", {"locator_id": loc["locator_id"]})["result"]
        self.assertEqual(media["action"], "downloadMedia")
        path = self.ex.execute("tab_pw_download_path", {"tab_id": tid})["result"]
        self.assertTrue(path["path"])
        self.ex.execute("tab_pw_wait_for_timeout", {"timeoutMs": 5})


if __name__ == "__main__":
    unittest.main()
