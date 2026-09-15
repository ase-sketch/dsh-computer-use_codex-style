"""Per-monitor DPI awareness so capture and SendInput share physical pixels.

A DPI-unaware sidecar on 150% (96/144) GetWindowRect's logical size and BitBlts
that many physical pixels, so the screenshot is only the top-left ~2/3 of the
window and click coordinates miss. Official helper is DPI-aware (WGC).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = ctypes.c_void_p(-3)
PROCESS_PER_MONITOR_DPI_AWARE = 2
_ENABLED = False


def enable_dpi_awareness() -> bool:
    """Official dpi.rs FUN_14005e46b: Context V2, then V1, then SetProcessDPIAware."""
    global _ENABLED
    if _ENABLED:
        return True
    try:
        setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if setter is not None and setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            _ENABLED = True
            return True
        if setter is not None and setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE):
            _ENABLED = True
            return True
    except OSError:
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        hr = shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        if hr == 0 or hr == 5:  # S_OK or already set
            _ENABLED = True
            return True
    except OSError:
        pass
    try:
        if user32.SetProcessDPIAware():
            _ENABLED = True
            return True
    except OSError:
        pass
    return _ENABLED


def enable_thread_dpi_awareness() -> bool:
    """Official capture/UI thread: SetThreadDpiAwarenessContext(V2) then V1 (FUN_1400478e4)."""
    try:
        setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
        if setter is None:
            return False
        setter.restype = ctypes.c_void_p
        setter.argtypes = [ctypes.c_void_p]
        prev = setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        if prev:
            return True
        prev = setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE)
        return bool(prev)
    except OSError:
        return False


def window_dpi(hwnd: int) -> int:
    getter = getattr(user32, "GetDpiForWindow", None)
    if getter is not None and hwnd:
        try:
            getter.argtypes = [wintypes.HWND]
            getter.restype = wintypes.UINT
            dpi = int(getter(hwnd))
            if dpi > 0:
                return dpi
        except OSError:
            pass
    getter = getattr(user32, "GetDpiForSystem", None)
    if getter is not None:
        try:
            getter.restype = wintypes.UINT
            dpi = int(getter())
            if dpi > 0:
                return dpi
        except OSError:
            pass
    return 96


def dpi_scale(dpi: int) -> float:
    return max(int(dpi), 1) / 96.0


def logical_to_physical(x: float, y: float, origin_x: float, origin_y: float, scale: float) -> tuple[float, float]:
    """Codex click space: window-relative logical → screen physical."""
    s = scale if scale > 0.01 else 1.0
    return origin_x + float(x) * s, origin_y + float(y) * s


def physical_to_logical(x: float, y: float, origin_x: float, origin_y: float, scale: float) -> tuple[float, float]:
    s = scale if scale > 0.01 else 1.0
    return (float(x) - origin_x) / s, (float(y) - origin_y) / s


def physical_size_to_logical(width: float, height: float, scale: float) -> tuple[int, int]:
    """Match image.rs scaled_size when scale is dpi/96."""
    s = scale if scale > 0.01 else 1.0
    dpi = max(1, int(round(s * 96.0)))
    from computer_use.wgc import scaled_size

    return scaled_size(int(round(width)), int(round(height)), dpi)


def dpi_snapshot(hwnd: int = 0) -> dict[str, float | int | bool]:
    dpi = window_dpi(hwnd) if hwnd else 96
    sys_getter = getattr(user32, "GetDpiForSystem", None)
    system_dpi = 96
    if sys_getter is not None:
        try:
            sys_getter.restype = wintypes.UINT
            system_dpi = int(sys_getter()) or 96
        except OSError:
            system_dpi = 96
    return {
        "aware": _ENABLED,
        "windowDpi": dpi,
        "systemDpi": system_dpi,
        "scale": dpi_scale(dpi),
    }
