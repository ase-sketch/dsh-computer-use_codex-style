from __future__ import annotations

import unittest

from computer_use.driver import ComputerUse
from computer_use.fake_backend import FakeDesktop

PNG = b"\x89PNG\r\n\x1a\n"
WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class FakeDesktopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeDesktop()
        self.driver = ComputerUse(self.backend)

    def test_get_window_state_default_is_screenshot_without_tree(self) -> None:
        state = self.driver.get_window_state({"window": WINDOW})
        self.assertIsNone(state["accessibility"])
        self.assertGreater(state["screenshot_bytes"], 0)
        self.assertTrue(state["screenshots"][0]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(state["tree"], [])

    def test_include_text_returns_png_and_indexed_tree(self) -> None:
        state = self.driver.get_window_state(
            {"window": WINDOW, "include_screenshot": True, "include_text": True}
        )
        raw = __import__("base64").b64decode(state["screenshot_base64"])
        self.assertTrue(raw.startswith(PNG))
        self.assertIsNotNone(state["accessibility"])
        # AX-17: official grammar is a bare index with TAB indentation, no brackets.
        self.assertIn("1 Edit Text Editor", state["accessibility"]["tree"])
        self.assertNotIn("[1]", state["accessibility"]["tree"])
        node = state["tree"][1]
        self.assertEqual(node["role"], "Edit")
        self.assertEqual(node["name"], "Text Editor")
        self.assertEqual(node["label"], "Text Editor")
        for key in ("x", "y", "width", "height"):
            self.assertIn(key, node["bounds"])

    def test_click_by_index_records_resolved_bounds(self) -> None:
        state = self.driver.get_window_state({"window": WINDOW, "include_text": True})
        node = state["tree"][1]
        result = self.driver.click({"window": WINDOW, "element_index": node["index"]})
        self.assertEqual(result["action"]["element_index"], node["index"])
        self.assertEqual(result["action"]["bounds"], node["bounds"])
        self.assertEqual(self.backend.actions[-1].payload["bounds"], node["bounds"])

    def test_window2_actions_are_recorded(self) -> None:
        state = self.driver.get_window_state({"window": WINDOW, "include_screenshot": True})
        shot = state["screenshots"][0]["id"]
        self.driver.click({"window": WINDOW, "x": 40, "y": 80, "screenshotId": shot})
        self.driver.type_text({"window": WINDOW, "text": "hello"})
        self.driver.press_key({"window": WINDOW, "key": "Return"})
        self.driver.scroll({"window": WINDOW, "x": 40, "y": 80, "scrollX": 0, "scrollY": 600, "screenshotId": shot})
        self.driver.drag({"window": WINDOW, "from_x": 10, "from_y": 10, "to_x": 40, "to_y": 50, "screenshotId": shot})
        self.driver.set_value({"window": WINDOW, "element_index": 1, "value": "set"})
        self.driver.perform_secondary_action({"window": WINDOW, "element_index": 2, "action": "Invoke"})
        self.driver.activate_window({"window": WINDOW})
        kinds = [record.kind for record in self.backend.actions]
        self.assertEqual(
            kinds,
            ["click", "type_text", "press_key", "scroll", "drag", "set_value", "perform_secondary_action", "activate_window"],
        )
        self.assertEqual(shot, "screenshot-0")

    def test_list_apps_and_windows_return_fake_catalog(self) -> None:
        apps = self.driver.list_apps()
        windows = self.driver.list_windows()
        self.assertEqual(apps[0]["id"], "notepad.exe")
        self.assertEqual(apps[0]["displayName"], "Notepad")
        self.assertEqual(windows[0]["id"], 1)
        self.assertEqual(windows[0]["app"], "notepad.exe")


if __name__ == "__main__":
    unittest.main()
