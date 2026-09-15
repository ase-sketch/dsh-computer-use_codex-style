from __future__ import annotations

import unittest

from computer_use.jpeg_wic import encode_jpeg_rgba
from computer_use.png import decode_png, solid_png
from computer_use.wgc_winrt import wgc_framepool_available


class JpegWgcTests(unittest.TestCase):
    def test_gdiplus_jpeg_magic(self) -> None:
        width, height, rgba = decode_png(solid_png(24, 12))
        jpeg = encode_jpeg_rgba(width, height, rgba)
        self.assertTrue(jpeg.startswith(b"\xff\xd8\xff"))
        self.assertGreater(len(jpeg), 32)

    def test_wgc_framepool_factory_probe(self) -> None:
        self.assertIsInstance(wgc_framepool_available(), bool)

    def test_cached_session_count_starts_non_negative(self) -> None:
        from computer_use.wgc_winrt import FRAMEPOOL_BUFFERS, cached_session_count

        self.assertEqual(FRAMEPOOL_BUFFERS, 1)
        self.assertGreaterEqual(cached_session_count(), 0)

    def test_winrt_software_bitmap_encoder(self) -> None:
        from computer_use.jpeg_winrt import encode_jpeg_rgba as winrt

        width, height, rgba = decode_png(solid_png(16, 8))
        jpeg = winrt(width, height, rgba)
        self.assertTrue(jpeg.startswith(b"\xff\xd8\xff"))


if __name__ == "__main__":
    unittest.main()
