from __future__ import annotations

import unittest

from computer_use.compact import present_observation, tree_diff
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.surfaces import tools_for_surface

WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class HarnessSurfaceTests(unittest.TestCase):
    def test_compact_strips_pixels_keeps_id(self) -> None:
        driver = ComputerUse(FakeDesktop())
        raw = driver.get_window_state({"window": WINDOW, "include_screenshot": True, "include_text": True})
        shown = present_observation(raw, emit_image=False)
        self.assertEqual(shown["screenshot_base64"], "")
        self.assertFalse(shown["screenshots"][0]["emitted"])
        self.assertIn("id", shown["screenshots"][0])
        self.assertGreater(shown["screenshot_bytes"], 0)

    def test_tree_diff_and_session_notes(self) -> None:
        self.assertEqual(tree_diff("a\nb", "a\nb"), "no accessibility-tree change")
        self.assertIn("added/changed:", tree_diff("a", "a\nb"))
        executor = ToolExecutor(ComputerUse(FakeDesktop()), steal_focus=False)
        executor.execute("session_note", {"text": "prefer AX indexes over pixels"})
        snap = executor.execute("session_state", {})["result"]
        self.assertIn("prefer AX", snap["reasoning"][0])

    def test_mac_background_click_skips_activate(self) -> None:
        backend = FakeDesktop()
        executor = ToolExecutor(ComputerUse(backend), steal_focus=False, compact=False)
        executor.execute("get_app_state", {"app": "notepad.exe"})
        executor.execute("click", {"app": "notepad.exe", "element_index": 1})
        kinds = [item.kind for item in backend.actions]
        self.assertNotIn("activate_window", kinds)
        self.assertGreaterEqual(executor.mac.background_clicks, 1)
        executor.execute("paste", {"app": "notepad.exe", "text": "hello"})
        self.assertEqual(backend.actions[-1].kind, "paste")

    def test_browser_ax_dom_and_batch(self) -> None:
        executor = ToolExecutor(ComputerUse(FakeDesktop()))
        tab = executor.execute("tab_new", {"url": "https://example.com/"})["result"]
        ax = executor.execute("tab_ax_write", {"tab_id": tab["id"], "mode": "state"})["result"]
        self.assertIn("Example Domain", ax["accessibility"]["tree"])
        click = executor.execute("tab_ax_click", {"tab_id": tab["id"], "element_index": 2})["result"]
        self.assertEqual(click["name"], "More information")
        dom = executor.execute("tab_dom_snapshot", {"tab_id": tab["id"]})["result"]
        self.assertEqual(dom["nodes"][2]["selector"], "input#q")
        batch = executor.execute(
            "batch_actions",
            {
                "tab_id": tab["id"],
                "then": "tab_ax_write",
                "actions": [
                    {"name": "tab_ax_set_value", "arguments": {"tab_id": tab["id"], "element_index": 3, "value": "openai"}},
                    {"name": "tab_ax_click", "arguments": {"tab_id": tab["id"], "element_index": 2}},
                ],
            },
        )["result"]
        self.assertEqual(batch["batched"], 2)
        self.assertIsNotNone(batch["refresh"])

    def test_all_surface_tool_names(self) -> None:
        names = [item["function"]["name"] for item in tools_for_surface("all")]
        for required in (
            "get_window_state",
            "get_app_state",
            "tab_ax_write",
            "tab_dom_snapshot",
            "tab_dom_type",
            "tab_pw_locator",
            "tab_pw_get_by_role",
            "tab_mention_resolve",
            "browser_claim_tab",
            "tab_pw_frame_locator",
            "tab_pw_element_screenshot",
            "browser_get_default",
            "tab_pw_check",
            "tab_dev_logs",
            "documentation_get",
            "tab_alert_dismiss",
            "batch_actions",
            "paste",
            "end_turn",
        ):
            self.assertIn(required, names)

    def test_emit_image_channel_and_allowlist(self) -> None:
        from pathlib import Path
        import tempfile

        from computer_use.allowlist import load_always
        from computer_use.approval import ApprovalGate
        from computer_use.cdp_ax import ax_text, flatten_cdp_ax
        from computer_use.helper_protocol import APPROVED_APP_META_KEY, encode_request

        raw = ComputerUse(FakeDesktop()).get_window_state({"window": WINDOW, "include_screenshot": True})
        shown = present_observation(raw, emit_image=True)
        self.assertTrue(shown["images"])
        self.assertEqual(shown["images"][0]["type"], "input_image")
        self.assertIn("image_url", shown["images"][0])
        line = encode_request(1, "click", {}, extra_meta={APPROVED_APP_META_KEY: "MSEdge"})
        self.assertIn(APPROVED_APP_META_KEY, line)
        folder = Path(tempfile.mkdtemp())
        path = folder / "allow.json"
        gate = ApprovalGate.from_disk(path=path)
        gate.ensure("MSEdge", "Microsoft Edge")
        self.assertIn("msedge", load_always(path))
        self.assertIn("msedge", gate.always)
        cdp = {
            "nodes": [
                {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2"]},
                {"nodeId": "2", "parentId": "1", "role": {"value": "link"}, "name": {"value": "More"}, "childIds": []},
            ]
        }
        flat = flatten_cdp_ax(cdp)
        self.assertEqual(flat[1]["role"], "link")
        self.assertIn("[1] link", ax_text(flat, "Example", "https://example.com/"))
        browsers = ToolExecutor(ComputerUse(FakeDesktop())).execute("browser_list", {})["result"]
        types = {item["type"] for item in browsers}
        self.assertIn("iab", types)
        self.assertIn("cdp", types)
        self.assertIn("extension", types)


if __name__ == "__main__":
    unittest.main()
