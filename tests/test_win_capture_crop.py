from __future__ import annotations

import unittest

from computer_use.errors import DesktopUnavailable
from computer_use.wgc import MonitorFrame, clamp_crop, crop_window_from_monitor, scaled_size
from computer_use.win_capture import crop_rgba


class MonitorCropTests(unittest.TestCase):
    def test_crop_window_from_monitor(self) -> None:
        monitor = MonitorFrame(0, 0, 2560, 1440)
        left, top, width, height = crop_window_from_monitor(monitor, 100, 200, 800, 600)
        self.assertEqual((left, top, width, height), (100, 200, 800, 600))

    def test_crop_rgba_takes_window_tile(self) -> None:
        # 2x2 pixels, crop the bottom-right pixel
        src = bytes([
            1, 0, 0, 255, 2, 0, 0, 255,
            3, 0, 0, 255, 4, 0, 0, 255,
        ])
        out = crop_rgba(src, 2, 2, 1, 1, 1, 1)
        self.assertEqual(list(out), [4, 0, 0, 255])

    def test_crop_straddle_clamps(self) -> None:
        monitor = MonitorFrame(0, 0, 100, 100)
        left, top, width, height = crop_window_from_monitor(monitor, -10, 0, 50, 50)
        self.assertEqual((left, top, width, height), (0, 0, 40, 50))
        self.assertEqual(clamp_crop(0, 0, 800, 600, 100, 100), (0, 0, 100, 100))

    def test_crop_completely_outside_fails(self) -> None:
        monitor = MonitorFrame(0, 0, 100, 100)
        with self.assertRaises(DesktopUnavailable):
            crop_window_from_monitor(monitor, 200, 0, 50, 50)

    def test_scaled_size_144dpi(self) -> None:
        self.assertEqual(scaled_size(1500, 900, 144), (1000, 600))
        self.assertEqual(scaled_size(96, 96, 96), (96, 96))


if __name__ == "__main__":
    unittest.main()
