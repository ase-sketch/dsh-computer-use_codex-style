from __future__ import annotations

import unittest

from computer_use.win_dpi import dpi_scale, enable_thread_dpi_awareness, logical_to_physical, physical_size_to_logical, physical_to_logical
from computer_use.win_input import virtual_abs


class DpiMathTests(unittest.TestCase):
    def test_150_percent_is_two_thirds_unaware_bug(self) -> None:
        self.assertAlmostEqual(dpi_scale(144), 1.5)
        self.assertAlmostEqual(96 / 144, 2 / 3)

    def test_virtual_abs_center_of_2560(self) -> None:
        x, y = virtual_abs(1280, 720, 0, 0, 2560, 1440)
        self.assertEqual(x, int(1280 * 65535 / 2559))
        self.assertEqual(y, int(720 * 65535 / 1439))

    def test_virtual_abs_origin(self) -> None:
        x, y = virtual_abs(0, 0, 0, 0, 2560, 1440)
        self.assertEqual((x, y), (0, 0))

    def test_logical_to_physical_150_percent(self) -> None:
        px, py = logical_to_physical(10, 20, 100, 200, 1.5)
        self.assertEqual((px, py), (115.0, 230.0))
        lx, ly = physical_to_logical(115, 230, 100, 200, 1.5)
        self.assertEqual((lx, ly), (10.0, 20.0))
        self.assertEqual(physical_size_to_logical(1500, 900, 1.5), (1000, 600))

    def test_thread_dpi_helper_is_callable(self) -> None:
        self.assertTrue(callable(enable_thread_dpi_awareness))


if __name__ == "__main__":
    unittest.main()
