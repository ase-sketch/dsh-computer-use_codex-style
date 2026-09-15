from __future__ import annotations

import unittest

from computer_use.driver import ComputerUse
from computer_use.fake_backend import FakeDesktop
from computer_use.keys import virtual_keys
from computer_use.recovered import CLICK_ELEMENT, STATE_FLAG_ERROR
from computer_use.validate import (
    COORDINATE_GEOMETRY_UNAVAILABLE,
    NO_SCREENSHOT_TARGETS_FOR,
    WINDOW_BOUNDS_UNAVAILABLE_COORD,
    WINDOW_BOUNDS_UNAVAILABLE_FOR,
    outside_viewport_error,
    screenshot_targets_missing,
    secondary_action,
    window_bounds_unavailable_error,
)
from computer_use.win_capture import PW_RENDERFULLCONTENT, capture_hwnd

WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class HelperBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeDesktop()
        self.driver = ComputerUse(self.backend)

    def test_get_window_state_requires_a_channel(self) -> None:
        with self.assertRaises(TypeError) as raised:
            self.driver.get_window_state(
                {"window": WINDOW, "include_screenshot": False, "include_text": False}
            )
        self.assertIn("include_text, include_screenshot, or both", str(raised.exception))
        self.assertEqual(str(raised.exception), STATE_FLAG_ERROR)

    def test_click_element_uses_cached_bounds(self) -> None:
        state = self.driver.get_window_state({"window": WINDOW, "include_text": True})
        node = state["tree"][1]
        result = self.driver.click({"window": WINDOW, "element_index": str(node["index"])})
        self.assertEqual(result["action"]["kind"], CLICK_ELEMENT)
        self.assertEqual(result["action"]["bounds"], node["bounds"])
        self.assertEqual(result["action"]["click_count"], 1)

    def test_screenshot_id_and_viewport(self) -> None:
        state = self.driver.get_window_state({"window": WINDOW, "include_screenshot": True})
        shot = state["screenshots"][0]
        self.assertEqual(shot["originX"], 0)
        self.assertEqual(shot["originY"], 0)
        self.assertEqual(shot["width"], 800)
        self.assertEqual(shot["height"], 600)
        with self.assertRaises(PermissionError):
            self.driver.click({"window": WINDOW, "x": 10, "y": 10, "screenshotId": "missing"})
        with self.assertRaises(ValueError) as raised:
            self.driver.click({"window": WINDOW, "x": 9000, "y": 10, "screenshotId": shot["id"]})
        message = str(raised.exception)
        self.assertEqual(
            message,
            "point (9000.0, 10.0) is outside viewport { originX: 0, originY: 0, width: 800, height: 600 }",
        )
        self.assertIn("originX:", message)
        self.assertIn("originY:", message)
        self.assertIn("width:", message)
        self.assertIn("height:", message)
        self.driver.click({"window": WINDOW, "x": 12.6, "y": 40.2, "screenshotId": shot["id"]})
        self.assertEqual(self.backend.actions[-1].payload["x"], 13)
        self.assertEqual(self.backend.actions[-1].payload["y"], 40)

    def test_outside_viewport_error_includes_origin_and_height(self) -> None:
        self.assertEqual(
            outside_viewport_error(886.0, 715.0, 486, 135, 735, 647),
            "point (886.0, 715.0) is outside viewport { originX: 486, originY: 135, width: 735, height: 647 }",
        )

    def test_coordinate_geometry_unavailable_strings(self) -> None:
        self.assertEqual(COORDINATE_GEOMETRY_UNAVAILABLE, "coordinate input geometry is unavailable")
        self.assertEqual(WINDOW_BOUNDS_UNAVAILABLE_COORD, "window bounds unavailable for coordinate input")
        self.assertEqual(NO_SCREENSHOT_TARGETS_FOR, "no screenshot targets found for ")
        self.assertEqual(WINDOW_BOUNDS_UNAVAILABLE_FOR, "window bounds unavailable for ")
        self.assertEqual(
            screenshot_targets_missing("screenshot-0", "Window { app: \"app\", id: 1, title: \"t\" }"),
            "screenshot-0 no screenshot targets found for Window { app: \"app\", id: 1, title: \"t\" }",
        )
        self.assertEqual(
            window_bounds_unavailable_error("Window { app: \"app\", id: 1, title: \"t\" }"),
            "window bounds unavailable for Window { app: \"app\", id: 1, title: \"t\" }",
        )

    def test_click_count_and_key_aliases(self) -> None:
        self.driver.get_window_state({"window": WINDOW})
        with self.assertRaises(TypeError):
            self.driver.click({"window": WINDOW, "x": 1, "y": 1, "click_count": 0})
        self.assertEqual(virtual_keys("Control_L+a"), [0x11, ord("A")])
        self.assertEqual(virtual_keys("Ctrl+Return"), [0x11, 0x0D])
        self.assertEqual(virtual_keys("KP_0"), [0x60])
        self.driver.press_key({"window": WINDOW, "key": "Control_L+Shift_L+period"})
        self.assertEqual(self.backend.actions[-1].payload["key"], "Control_L+Shift_L+period")

    def test_secondary_action_aliases(self) -> None:
        self.assertEqual(secondary_action("scroll down"), "Scroll Down")
        self.driver.get_window_state({"window": WINDOW})
        self.driver.perform_secondary_action({"window": WINDOW, "element_index": 2, "action": "expand"})
        self.assertEqual(self.backend.actions[-1].payload["action"], "Expand")

    def test_printwindow_flag_is_wired(self) -> None:
        self.assertEqual(PW_RENDERFULLCONTENT, 2)
        self.assertTrue(callable(capture_hwnd))


if __name__ == "__main__":
    unittest.main()
