"""Windows.Graphics.Capture pipeline recovered from helper capture/image.rs.

Official helper: IGraphicsCaptureItemInterop.CreateForMonitor →
Direct3D11CaptureFramePool.CreateFreeThreaded → SetIsCursorCaptureEnabled(false)
→ SetIsBorderRequired(false) → crop window rect out of the monitor bitmap.
JPEG encode via SoftwareBitmap/BitmapEncoder.

This module implements the crop/session policy in-process and uses PrintWindow
as the pixel source when a D3D device is not available.
"""

from __future__ import annotations

from dataclasses import dataclass

from computer_use.errors import DesktopUnavailable

CROP_OUTSIDE = "window crop is outside captured monitor"


@dataclass
class MonitorFrame:
    origin_x: int
    origin_y: int
    width: int
    height: int


@dataclass
class CaptureSessionConfig:
    cursor_capture: bool = False
    border_required: bool = False
    source: str = "monitor"


def clamp_crop(
    left: int,
    top: int,
    width: int,
    height: int,
    src_w: int,
    src_h: int,
) -> tuple[int, int, int, int]:
    """Official image.rs:119-122 FUN_140045668: clamp to bitmap, empty → CROP_OUTSIDE."""
    x0 = max(0, min(int(left), int(src_w)))
    y0 = max(0, min(int(top), int(src_h)))
    x1 = max(0, min(int(left) + int(width), int(src_w)))
    y1 = max(0, min(int(top) + int(height), int(src_h)))
    if x1 <= x0 or y1 <= y0:
        raise DesktopUnavailable(CROP_OUTSIDE)
    return x0, y0, x1 - x0, y1 - y0


def crop_window_from_monitor(
    monitor: MonitorFrame,
    window_x: int,
    window_y: int,
    window_w: int,
    window_h: int,
) -> tuple[int, int, int, int]:
    left = int(window_x) - int(monitor.origin_x)
    top = int(window_y) - int(monitor.origin_y)
    return clamp_crop(left, top, window_w, window_h, monitor.width, monitor.height)


def scaled_size(width: int, height: int, dpi: int) -> tuple[int, int]:
    """Official image.rs:135 FUN_14004572d: (n * 96 + dpi/2) // dpi, min 1."""
    d = max(int(dpi), 1)

    def one(n: int) -> int:
        return max(1, (int(n) * 96 + d // 2) // d)

    return one(width), one(height)


def default_session() -> CaptureSessionConfig:
    return CaptureSessionConfig(cursor_capture=False, border_required=False, source="monitor")
