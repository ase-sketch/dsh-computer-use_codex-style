from __future__ import annotations

import ctypes
from ctypes import wintypes

from dataclasses import dataclass

from computer_use.errors import DesktopUnavailable
from computer_use.png import encode_png
from computer_use.wgc import MonitorFrame, clamp_crop, crop_window_from_monitor
from computer_use.win_dpi import enable_thread_dpi_awareness, window_dpi

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 2
MONITOR_DEFAULTTONEAREST = 2


@dataclass
class CaptureFrame:
    png: bytes
    origin_x: int
    origin_y: int
    width: int
    height: int
    dpi: int = 96
    mime_type: str = "image/png"


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise DesktopUnavailable("GetWindowRect failed")
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        raise DesktopUnavailable("window has invalid bounds or is not visible")
    return int(rect.left), int(rect.top), width, height


def _header(width: int, height: int) -> BITMAPINFO:
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    return info


def _bgra_to_rgba(pixels: bytes, width: int, height: int) -> bytes:
    buf = bytearray(pixels)
    for i in range(0, width * height * 4, 4):
        buf[i], buf[i + 2] = buf[i + 2], buf[i]
        buf[i + 3] = 255
    return bytes(buf)


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def _rgba(mem: int, bitmap: int, width: int, height: int) -> bytes:
    info = _header(width, height)
    pixels = ctypes.create_string_buffer(width * height * 4)
    got = gdi32.GetDIBits(mem, bitmap, 0, height, pixels, ctypes.byref(info), 0)
    if got == 0:
        raise DesktopUnavailable("GetDIBits failed")
    return _bgra_to_rgba(pixels.raw, width, height)


def _pixels(mem: int, bitmap: int, width: int, height: int) -> bytes:
    return encode_png(width, height, _rgba(mem, bitmap, width, height))


def crop_rgba(rgba: bytes, src_w: int, src_h: int, left: int, top: int, width: int, height: int) -> bytes:
    left, top, width, height = clamp_crop(left, top, width, height, src_w, src_h)
    stride = src_w * 4
    out = bytearray(width * height * 4)
    for row in range(height):
        src = (top + row) * stride + left * 4
        dst = row * width * 4
        out[dst : dst + width * 4] = rgba[src : src + width * 4]
    return bytes(out)


def monitor_frame_for_hwnd(hwnd: int) -> MonitorFrame:
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        left, top, width, height = window_rect(hwnd)
        return MonitorFrame(left, top, width, height)
    rect = info.rcMonitor
    return MonitorFrame(int(rect.left), int(rect.top), int(rect.right - rect.left), int(rect.bottom - rect.top))


def _blit_screen(left: int, top: int, width: int, height: int) -> bytes:
    screen = user32.GetDC(0)
    if not screen:
        raise DesktopUnavailable("GetDC(0) failed")
    mem = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    prev = gdi32.SelectObject(mem, bitmap)
    try:
        if not gdi32.BitBlt(mem, 0, 0, width, height, screen, left, top, SRCCOPY):
            raise DesktopUnavailable("monitor capture failed")
        return _rgba(mem, bitmap, width, height)
    finally:
        gdi32.SelectObject(mem, prev)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, screen)


def _print_window(hwnd: int, width: int, height: int) -> bytes:
    hdc = user32.GetDC(hwnd)
    if not hdc:
        raise DesktopUnavailable("GetDC failed")
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    prev = gdi32.SelectObject(mem, bitmap)
    try:
        printed = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
        if not printed and not gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, SRCCOPY):
            raise DesktopUnavailable("window capture failed")
        return _rgba(mem, bitmap, width, height)
    finally:
        gdi32.SelectObject(mem, prev)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


def _hide_cursor() -> None:
    user32.ShowCursor(False)


def _show_cursor() -> None:
    user32.ShowCursor(True)


GW_OWNER = 4
GW_ENABLEDPOPUP = 6
GW_HWNDNEXT = 2
GA_ROOT = 2
DWMWA_CLOAKED = 14


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _cloaked(hwnd: int) -> bool:
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        value = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), 4) == 0:
            return bool(value.value)
    except Exception:
        return False
    return False


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


SPACE_WINDOW = "window"
SPACE_MENU = "menu"
SPACE_TOOLTIP = "tooltip"
SPACE_OVERLAY = "overlay"
SPACE_POPUP = "popup"


def window_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value or ""


def monitor_device(hwnd: int) -> str:
    try:
        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return info.szDevice
    except Exception:
        return ""
    return ""


def space_identity(hwnd: int, *, space: str, snapshot: str = "") -> dict:
    """Official space identity: windowID, displayName, processKey, display, snapshot."""
    from computer_use.policy import hwnd_pid, process_aumid, process_name_for_pid

    pid = hwnd_pid(hwnd)
    aumid = process_aumid(pid)
    exe = process_name_for_pid(pid)
    key = f"aumid:{aumid}" if aumid else f"exe:{exe}:{pid}"
    title = ""
    try:
        size = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(size + 2)
        user32.GetWindowTextW(hwnd, buf, size + 2)
        title = buf.value or ""
    except Exception:
        title = ""
    try:
        left, top, width, height = window_rect(hwnd)
        bounds = {"x": left, "y": top, "width": width, "height": height}
    except DesktopUnavailable:
        left = top = width = height = 0
        bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
    dpi = window_dpi(hwnd)
    return {
        "space": space,
        "windowID": hwnd,
        "displayName": title or exe,
        "processKey": key,
        "app": exe,
        "identity": f"{key}|{hwnd}",
        "display": monitor_device(hwnd),
        "snapshot": snapshot,
        "revision": 0,
        "originX": left,
        "originY": top,
        "width": width,
        "height": height,
        "nativeWidth": width,
        "nativeHeight": height,
        "bounds": bounds,
        "dpi": dpi,
    }


def classify_screenshot_space(hwnd: int, overlay: set[int] | None = None) -> str:
    """Official space identity: window / menu / tooltip / overlay / popup."""
    if overlay and hwnd in overlay:
        return SPACE_OVERLAY
    cls = window_class_name(hwnd)
    lowered = cls.lower()
    if cls == "#32768":
        return SPACE_MENU
    if lowered in {"tooltips_class32", "tooltip", "msctls_hotkey32"} or "tooltip" in lowered:
        return SPACE_TOOLTIP
    if cls == "#32770":
        return SPACE_POPUP
    style = int(user32.GetWindowLongW(hwnd, -16) or 0)
    ex = int(user32.GetWindowLongW(hwnd, -20) or 0)
    if ex & 0x00000080 and style & 0x80000000:  # WS_EX_TOOLWINDOW | WS_POPUP
        return SPACE_POPUP
    if style & 0x80000000:
        return SPACE_POPUP
    return SPACE_WINDOW


def screenshot_spaces(hwnd: int) -> list[tuple[int, str]]:
    """Related z-order windows tagged with official space kinds. Overlay is typed but not captured."""
    if not hwnd:
        return []
    overlay: set[int] = set()
    try:
        from computer_use.overlay_win import overlay_hwnds

        overlay = set(overlay_hwnds())
    except Exception:
        overlay = set()
    try:
        target_rect = window_rect(hwnd)
    except DesktopUnavailable:
        return []
    target_pid = _pid(hwnd)
    root = int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
    found: list[tuple[int, str]] = []
    seen: set[int] = set()
    popup = int(user32.GetWindow(hwnd, GW_ENABLEDPOPUP) or 0)
    if popup and popup != hwnd and user32.IsWindowVisible(popup) and not _cloaked(popup) and popup not in overlay:
        found.append((popup, classify_screenshot_space(popup, overlay)))
        seen.add(popup)
    cur = int(user32.GetTopWindow(0) or 0)
    hops = 0
    while cur and hops < 512:
        hops += 1
        handle = int(cur)
        cur = int(user32.GetWindow(cur, GW_HWNDNEXT) or 0)
        if handle == hwnd or handle in seen:
            continue
        if handle in overlay:
            continue
        if not user32.IsWindowVisible(handle) or _cloaked(handle):
            continue
        try:
            rect = window_rect(handle)
        except DesktopUnavailable:
            continue
        owner = int(user32.GetWindow(handle, GW_OWNER) or 0)
        ancestor = int(user32.GetAncestor(handle, GA_ROOT) or 0)
        related = owner == hwnd or ancestor == root or ancestor == hwnd
        same_proc = _pid(handle) == target_pid and _rects_overlap(rect, target_rect)
        if not (related or same_proc):
            continue
        found.append((handle, classify_screenshot_space(handle, overlay)))
        seen.add(handle)
    return found


def screenshot_space_hwnds(hwnd: int) -> list[int]:
    return [handle for handle, _kind in screenshot_spaces(hwnd)]


def transient_hwnds(hwnd: int) -> list[int]:
    """Owned popups/menus plus overlapping related z-order windows (higher zIndex)."""
    return screenshot_space_hwnds(hwnd)


def capture_hwnd(hwnd: int, timeout_ms: int = 800) -> CaptureFrame:
    """Official helper: WGC FramePool JPEG, no cursor, no yellow border. Fallbacks: DXGI, GDI."""
    enable_thread_dpi_awareness()
    try:
        from computer_use.overlay_win import exclude_overlay_from_capture

        exclude_overlay_from_capture()
    except Exception:
        pass
    try:
        from computer_use.wgc_winrt import capture_hwnd_wgc

        return capture_hwnd_wgc(hwnd, timeout_ms=timeout_ms)
    except Exception:
        pass
    try:
        from computer_use.wgc_d3d import capture_hwnd_d3d

        return capture_hwnd_d3d(hwnd)
    except Exception:
        pass
    left, top, width, height = window_rect(hwnd)
    dpi = window_dpi(hwnd)
    monitor = monitor_frame_for_hwnd(hwnd)
    _hide_cursor()
    try:
        try:
            rgba = _blit_screen(monitor.origin_x, monitor.origin_y, monitor.width, monitor.height)
            crop_x, crop_y, crop_w, crop_h = crop_window_from_monitor(monitor, left, top, width, height)
            png = encode_png(crop_w, crop_h, crop_rgba(rgba, monitor.width, monitor.height, crop_x, crop_y, crop_w, crop_h))
            return CaptureFrame(png, left, top, crop_w, crop_h, dpi)
        except DesktopUnavailable:
            png = encode_png(width, height, _print_window(hwnd, width, height))
            return CaptureFrame(png, left, top, width, height, dpi)
    finally:
        _show_cursor()
