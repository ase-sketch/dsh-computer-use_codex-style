from __future__ import annotations

import unittest
from pathlib import Path

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop


class OfficialMissingToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = ToolExecutor(ComputerUse(FakeDesktop()))
        self.tab = self.ex.execute("tab_new", {"url": "https://example.com/"})["result"]
        self.tid = self.tab["id"]

    def _call(self, tool: str, **kwargs):
        payload = self.ex.execute(tool, kwargs)
        self.assertEqual(payload["name"], tool)
        result = payload["result"]
        self.assertTrue(result, msg=tool)
        return result

    def test_browsers_get_default_for_url(self) -> None:
        default = self._call("browser_get_default")
        self.assertIn(default["type"], {"iab", "extension", "cdp"})
        got = self._call("browser_get", id="iab")
        self.assertEqual(got["type"], "iab")
        suited = self._call("browser_get_for_url", url="https://example.com/")
        self.assertIn(suited["type"], {"iab", "extension", "cdp"})

    def test_ax_get_drag_select_text(self) -> None:
        state = self._call("tab_ax_get", tab_id=self.tid, mode="state")
        self.assertFalse(state["emitted"])
        # AX-17: official grammar (bare index, TAB indent).
        self.assertIn("2 link More information", state["tree"])
        self.assertNotIn("[2]", state["tree"])
        self.assertIn("More information", state["tree"])
        drag = self._call("tab_ax_drag", tab_id=self.tid, **{"from": [10, 20], "to": [80, 90]})
        self.assertEqual(drag["action"], "ax.drag")
        self.assertEqual(drag["from"], [10, 20])
        self.assertEqual(drag["to"], [80, 90])
        selected = self._call("tab_ax_select_text", tab_id=self.tid, element_index=3, text="Search")
        self.assertEqual(selected["text"], "Search")

    def test_locator_check_select_and_query(self) -> None:
        box = self._call("tab_pw_get_by_role", tab_id=self.tid, role="checkbox", name="Agree")
        checked = self._call("tab_pw_check", locator_id=box["locator_id"])
        self.assertTrue(checked["checked"])
        unchecked = self._call("tab_pw_uncheck", locator_id=box["locator_id"])
        self.assertFalse(unchecked["checked"])
        again = self._call("tab_pw_set_checked", locator_id=box["locator_id"], checked=True)
        self.assertTrue(again["checked"])
        combo = self._call("tab_pw_get_by_role", tab_id=self.tid, role="combobox")
        option = self._call("tab_pw_select_option", locator_id=combo["locator_id"], value="red")
        self.assertEqual(option["value"], "red")
        loc = self._call("tab_pw_locator", tab_id=self.tid, selector="a")
        self._call("tab_pw_dblclick", locator_id=loc["locator_id"])
        self._call("tab_pw_press", locator_id=loc["locator_id"], key="Enter")
        self._call("tab_pw_type", locator_id=loc["locator_id"], text="x")
        self._call("tab_pw_press_sequentially", locator_id=loc["locator_id"], text="yz")
        nested = self._call("tab_pw_nested_locator", locator_id=loc["locator_id"], selector="span")
        self.assertEqual(nested["kind"], "nested")
        other = self._call("tab_pw_locator", tab_id=self.tid, selector="h1")
        self._call("tab_pw_and", locator_id=loc["locator_id"], other_id=other["locator_id"])
        self._call("tab_pw_or", locator_id=loc["locator_id"], other_id=other["locator_id"])
        self._call("tab_pw_filter", locator_id=loc["locator_id"], hasText="More")
        all_loc = self._call("tab_pw_all", locator_id=loc["locator_id"])
        self.assertGreaterEqual(all_loc["count"], 1)
        texts = self._call("tab_pw_all_text_contents", locator_id=loc["locator_id"])
        self.assertTrue(texts["texts"])
        attrs = self._call("tab_pw_get_attribute", locator_id=loc["locator_id"], name="selector")
        self.assertTrue(attrs["value"])
        content = self._call("tab_pw_text_content", locator_id=loc["locator_id"])
        self.assertIsNotNone(content["text"])
        self.assertTrue(self._call("tab_pw_is_visible", locator_id=loc["locator_id"])["visible"])
        self.assertTrue(self._call("tab_pw_is_enabled", locator_id=loc["locator_id"])["enabled"])
        waited = self._call("tab_pw_wait_for", locator_id=loc["locator_id"], state="visible")
        self.assertTrue(waited["ok"])
        eval_all = self._call("tab_pw_evaluate_all", locator_id=loc["locator_id"])
        self.assertGreaterEqual(eval_all["count"], 1)

    def test_dialogs_logs_docs_filechooser_history_download_cua(self) -> None:
        for kind in ("alert", "confirm", "prompt", "beforeunload"):
            injected = self._call("tab_inject_dialog", tab_id=self.tid, type=kind, message=kind)
            self.assertEqual(injected["dialog"]["type"], kind)
            shown = self.ex.execute("tab_get_js_dialog", {"tab_id": self.tid})["result"]["dialog"]
            self.assertEqual(shown["type"], kind)
            if kind == "alert":
                self._call("tab_alert_dismiss", tab_id=self.tid)
            elif kind == "confirm":
                self._call("tab_confirm_accept", tab_id=self.tid)
            elif kind == "prompt":
                self._call("tab_prompt_accept", tab_id=self.tid, text="ok")
            else:
                self._call("tab_beforeunload_dismiss", tab_id=self.tid)
            cleared = self.ex.execute("tab_get_js_dialog", {"tab_id": self.tid})["result"]["dialog"]
            self.assertIsNone(cleared)
        logs = self._call("tab_dev_logs", tab_id=self.tid, filter="dialog")
        self.assertTrue(logs["logs"])
        docs = self._call("documentation_get", name="SKILL")
        self.assertTrue(docs["found"])
        self.assertIn("Computer Use", docs["text"])
        self.ex.execute("tab_pw_set_files", {"tab_id": self.tid, "files": ["a.png", "b.png"], "multiple": True})
        multiple = self._call("tab_pw_file_chooser_is_multiple", tab_id=self.tid)
        self.assertTrue(multiple["isMultiple"])
        hist = self.ex.execute("browser_history", {"queries": ["example"], "from": "2020-01-01", "to": "2099-01-01", "limit": 5})["result"]
        self.assertTrue(hist["entries"])
        self.assertIn("example.com", str(hist["entries"][0]["url"]))
        media = self.ex.execute("tab_dom_download_media", {"tab_id": self.tid, "node_id": 2})["result"]
        path = self.ex.execute("tab_pw_download_path", {"tab_id": self.tid})["result"]["path"]
        self.assertTrue(Path(path).is_file())
        self.assertGreater(Path(path).stat().st_size, 0)
        ctx = self.ex.execute(
            "browser_get_tab_context",
            {"providerTabId": self.tab["providerTabId"], "title": "Example Domain", "url": "https://example.com/"},
        )["result"]
        self.assertFalse(ctx["claimed"])
        self.assertIn("text", ctx)
        cua = self._call("tab_cua_click", tab_id=self.tid, x=40, y=80)
        self.assertEqual(cua["x"], 40)
        self.assertEqual(cua["y"], 80)


if __name__ == "__main__":
    unittest.main()
