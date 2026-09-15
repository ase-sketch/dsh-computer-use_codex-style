from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from computer_use.models import Bounds, UINode, WindowRef
from computer_use.png import solid_png
from computer_use.win_capture import CaptureFrame
from computer_use.win_tree import dump_tree
from computer_use.errors import DesktopUnavailable
from computer_use.windows_backend import WindowsDesktop


class DumpTreeTests(unittest.TestCase):
    def _proc(self, stdout: str | None, returncode: int = 0, hang: bool = False) -> SimpleNamespace:
        state = {"n": 0}

        def communicate(timeout=None):
            state["n"] += 1
            if hang and state["n"] == 1:
                raise subprocess.TimeoutExpired("powershell", timeout or 2)
            return stdout, ""

        return SimpleNamespace(pid=4242, returncode=returncode, communicate=communicate, kill=lambda: None)

    def test_uia_failure_falls_back_without_powershell(self) -> None:
        with patch("computer_use.win_uia.dump_tree", side_effect=RuntimeError("skip uia")), patch(
            "computer_use.win_tree.subprocess.Popen"
        ) as popen:
            nodes = dump_tree(1, "微信")
        popen.assert_not_called()
        self.assertEqual(nodes[0].name, "微信")
        self.assertEqual(nodes[0].role, "window")

    def test_empty_tree_falls_back(self) -> None:
        with patch("computer_use.win_uia.dump_tree", side_effect=RuntimeError("skip uia")):
            nodes = dump_tree(2, "微信")
        self.assertEqual(len(nodes), 1)

    def test_uia_nodes_pass_through(self) -> None:
        node = UINode(0, "Window", "微信", Bounds(0, 0, 10, 10))
        with patch("computer_use.win_uia.dump_tree", return_value=[node]), patch(
            "computer_use.win_tree.subprocess.Popen"
        ) as popen:
            nodes = dump_tree(4, "ignored")
        popen.assert_not_called()
        self.assertEqual(nodes[0].role, "Window")
        self.assertEqual(nodes[0].name, "微信")


class ObserveParityTests(unittest.TestCase):
    def test_default_get_window_state_does_not_dump_uia(self) -> None:
        desktop = WindowsDesktop()
        desktop.list_windows = lambda: [WindowRef("Weixin.exe", 6163426, "微信")]  # type: ignore[method-assign]
        frame = CaptureFrame(solid_png(), 31, 169, 902, 636)
        with patch("computer_use.windows_backend.is_minimized", return_value=False), patch(
            "computer_use.windows_backend.capture_hwnd", return_value=frame
        ), patch("computer_use.windows_backend.dump_accessibility") as dump:
            observation = desktop.observe({"window": {"app": "Weixin.exe", "id": 6163426, "title": "微信"}})
        dump.assert_not_called()
        self.assertTrue(observation.include_screenshot)
        self.assertFalse(observation.include_text)
        self.assertTrue(observation.screenshot.startswith(b"\x89PNG"))

    def test_include_text_survives_dump_tree_crash(self) -> None:
        desktop = WindowsDesktop()
        desktop.list_windows = lambda: [WindowRef("Weixin.exe", 6163426, "微信")]  # type: ignore[method-assign]
        frame = CaptureFrame(solid_png(), 31, 169, 902, 636)
        with patch("computer_use.windows_backend.is_minimized", return_value=False), patch(
            "computer_use.windows_backend.capture_hwnd", return_value=frame
        ), patch("computer_use.windows_backend.dump_accessibility", side_effect=AttributeError("'NoneType' object has no attribute 'strip'")):
            observation = desktop.observe(
                {"window": {"app": "Weixin.exe", "id": 6163426, "title": "微信"}, "include_text": True}
            )
        self.assertTrue(observation.include_screenshot)
        self.assertEqual(observation.tree, [])

    def test_click_uses_window_relative_logical_pixels(self) -> None:
        desktop = WindowsDesktop()
        desktop.list_windows = lambda: [WindowRef("Weixin.exe", 6163426, "微信")]  # type: ignore[method-assign]
        frame = CaptureFrame(solid_png(), 100, 200, 1500, 900, dpi=144)
        with patch("computer_use.windows_backend.is_minimized", return_value=False), patch(
            "computer_use.windows_backend.capture_hwnd", return_value=frame
        ):
            observation = desktop.observe({"window": {"app": "Weixin.exe", "id": 6163426, "title": "微信"}})
        self.assertEqual(observation.width, 1000)
        self.assertEqual(observation.height, 600)
        self.assertEqual(observation.native_width, 1500)
        self.assertEqual(observation.native_height, 900)
        shot = observation.to_dict()["screenshots"][0]
        self.assertEqual(shot["width"], 1000)
        self.assertEqual(shot["nativeWidth"], 1500)
        self.assertEqual(shot["logicalWidth"], 1000)
        with patch("computer_use.windows_backend.move_click") as click:
            desktop.click({"x": 10, "y": 20})
        click.assert_called_once()
        self.assertAlmostEqual(click.call_args[0][0], 115.0)
        self.assertAlmostEqual(click.call_args[0][1], 230.0)

    def test_minimized_uses_official_refresh_string(self) -> None:
        desktop = WindowsDesktop()
        desktop.list_windows = lambda: [WindowRef("Weixin.exe", 6163426, "微信")]  # type: ignore[method-assign]
        with patch("computer_use.windows_backend.is_minimized", return_value=True):
            with self.assertRaises(DesktopUnavailable) as raised:
                desktop.observe({"window": {"app": "Weixin.exe", "id": 6163426, "title": "微信"}})
        self.assertIn("refresh with get_window, then retry get_window_state", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

