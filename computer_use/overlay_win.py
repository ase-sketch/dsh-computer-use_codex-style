"""Topmost DSH control banner + Composition cursor stage. UI thread only."""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes
from typing import Any

from computer_use.overlay import ACCESSIBLE_NAME, BANNER, BAR_HEIGHT, CLASS_NAME, ESC_HINT
from computer_use.overlay_cursor import scoot_pose

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOREDIRECTIONBITMAP = 0x00200000
HWND_TOPMOST = -1
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
LWA_ALPHA = 0x02
WM_PAINT = 0x000F
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
SW_HIDE = 0
SW_SHOW = 5
WHITE_BRUSH = 0
DT_CENTER = 0x0001
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
WDA_EXCLUDEFROMCAPTURE = 0x00000011
WM_DISPLAYCHANGE = 0x007E
WM_DPICHANGED = 0x02E0
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMECRITICAL = 0x0006
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = LRESULT


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


_hwnd = 0
_atom = 0
_cursor_atom = 0
_wndproc_ref: Any = None
_cursor_wndproc_ref: Any = None
_cmds: queue.Queue[object] = queue.Queue()
_cursor_hwnd = 0
CURSOR_CLASS = CLASS_NAME + "Pointer"
CURSOR_SIZE = 64
_ready = threading.Event()
_started = False
_cursor_hidden = False
_mutex = 0
_winevent_hook = 0
_winevent_proc = None
_TEXT = f"{BANNER}  ·  {ESC_HINT}"
_last_recreate = 0.0
_cursor_stage = False
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, ctypes.c_long, ctypes.c_long, wintypes.DWORD, wintypes.DWORD
)


def overlay_hwnds() -> list[int]:
    return [int(h) for h in (_hwnd, _cursor_hwnd) if h]


def exclude_overlay_from_capture() -> bool:
    """Re-apply official exclude immediately before WGC StartCapture."""
    ok = True
    for hwnd in overlay_hwnds():
        if not exclude_from_capture(hwnd):
            ok = False
    return ok


def exclude_from_capture(hwnd: int) -> bool:
    """Official: exclude display overlay from capture (WDA_EXCLUDEFROMCAPTURE)."""
    if not hwnd:
        return False
    try:
        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            return True
    except Exception:
        return False
    return False


def _virtual_desktop() -> tuple[int, int, int, int]:
    return (
        int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(0)),
        int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(1)),
    )


_overlay_visible = False


def _on_foreground(hwineventhook, event, hwnd, id_object, id_child, thread, timestamp):
    if not _overlay_visible:
        return
    if _hwnd:
        user32.SetWindowPos(_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
    if _cursor_hwnd:
        user32.SetWindowPos(_cursor_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)


def _install_win_event_hook() -> None:
    global _winevent_hook, _winevent_proc
    if _winevent_hook:
        return
    _winevent_proc = WINEVENTPROC(_on_foreground)
    _winevent_hook = user32.SetWinEventHook(
        EVENT_SYSTEM_FOREGROUND,
        EVENT_SYSTEM_FOREGROUND,
        None,
        _winevent_proc,
        0,
        0,
        WINEVENT_OUTOFCONTEXT,
    )


def _ensure_mutex() -> None:
    global _mutex
    if _mutex:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex = kernel32.CreateMutexW(None, False, "Local\\DshComputerUseCursorOverlay")


def _suppress_system_cursor(hide: bool) -> None:
    """Thread-local hide only. Never SetSystemCursor — that replaces the user's scheme machine-wide."""
    global _cursor_hidden
    if hide and not _cursor_hidden:
        while user32.ShowCursor(False) >= 0:
            pass
        _cursor_hidden = True
    elif not hide and _cursor_hidden:
        while user32.ShowCursor(True) < 0:
            pass
        _cursor_hidden = False


def _paint(hwnd: int) -> None:
    ps = PAINTSTRUCT()
    hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
    try:
        from computer_use.composition_overlay import composition_attached

        if composition_attached():
            return
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        yellow = gdi32.CreateSolidBrush(0x00C4FF)
        user32.FillRect(hdc, ctypes.byref(rect), yellow)
        gdi32.DeleteObject(yellow)
        gdi32.SetBkMode(hdc, 1)
        gdi32.SetTextColor(hdc, 0x000000)
        user32.DrawTextW(hdc, _TEXT, -1, ctypes.byref(rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
    except Exception:
        pass
    finally:
        user32.EndPaint(hwnd, ctypes.byref(ps))


def _wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    if msg == WM_PAINT:
        _paint(hwnd)
        return 0
    if msg in (WM_DISPLAYCHANGE, WM_DPICHANGED):
        _cmds.put("recreate")
        return 0
    if msg == WM_POWERBROADCAST and int(wparam) in {
        PBT_APMRESUMECRITICAL,
        PBT_APMRESUMESUSPEND,
        PBT_APMRESUMEAUTOMATIC,
    }:
        _cmds.put("recreate")
        return 0
    if msg == WM_CLOSE:
        user32.ShowWindow(hwnd, SW_HIDE)
        return 0
    if msg == WM_DESTROY:
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _cursor_wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    if msg == WM_PAINT:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0
    if msg == WM_DESTROY:
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register_class(name: str, proc, atom_holder: str) -> None:
    global _atom, _cursor_atom, _wndproc_ref, _cursor_wndproc_ref
    current = _atom if atom_holder == "banner" else _cursor_atom
    if current:
        return
    wrapped = WNDPROC(proc)
    if atom_holder == "banner":
        _wndproc_ref = wrapped
    else:
        _cursor_wndproc_ref = wrapped
    cls = WNDCLASSW()
    cls.lpfnWndProc = wrapped
    cls.hInstance = ctypes.WinDLL("kernel32").GetModuleHandleW(None)
    cls.hbrBackground = gdi32.GetStockObject(WHITE_BRUSH) if atom_holder == "banner" else 0
    cls.lpszClassName = name
    atom = user32.RegisterClassW(ctypes.byref(cls))
    if not atom:
        err = ctypes.get_last_error()
        if err != 1410:
            raise OSError(err, "RegisterClassW failed")
        atom = 1
    if atom_holder == "banner":
        _atom = atom
    else:
        _cursor_atom = atom


def _ensure_class() -> None:
    _register_class(CLASS_NAME, _wndproc, "banner")
    _register_class(CURSOR_CLASS, _cursor_wndproc, "cursor")


def _create_window() -> int:
    vx, vy, vw, _vh = _virtual_desktop()
    ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_NOREDIRECTIONBITMAP | WS_EX_TRANSPARENT
    hwnd = user32.CreateWindowExW(
        ex,
        CLASS_NAME,
        ACCESSIBLE_NAME,
        WS_POPUP,
        vx,
        vy,
        vw,
        BAR_HEIGHT,
        None,
        None,
        ctypes.WinDLL("kernel32").GetModuleHandleW(None),
        None,
    )
    if hwnd:
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        exclude_from_capture(int(hwnd))
    return int(hwnd or 0)


def _create_cursor_window() -> int:
    vx, vy, vw, vh = _virtual_desktop()
    ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOREDIRECTIONBITMAP
    hwnd = user32.CreateWindowExW(
        ex,
        CURSOR_CLASS,
        "dsh-cursor",
        WS_POPUP,
        vx,
        vy,
        vw,
        vh,
        None,
        None,
        ctypes.WinDLL("kernel32").GetModuleHandleW(None),
        None,
    )
    if hwnd:
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        exclude_from_capture(int(hwnd))
    return int(hwnd or 0)


def _apply_show() -> None:
    global _overlay_visible
    _overlay_visible = True
    hwnd = _hwnd
    if not hwnd:
        return
    vx, vy, vw, _vh = _virtual_desktop()
    user32.SetWindowPos(hwnd, HWND_TOPMOST, vx, vy, vw, BAR_HEIGHT, SWP_SHOWWINDOW)
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.InvalidateRect(hwnd, None, True)
    exclude_from_capture(int(hwnd))
    try:
        from computer_use.composition_overlay import fade_display_overlay

        fade_display_overlay(1.0)
    except Exception:
        pass
    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        try:
            from computer_use.overlay_cursor import scoot_pose

            _place_cursor(float(pt.x), float(pt.y), scoot_pose(0.0, 0.0), press=False)
        except Exception:
            pass
    if _cursor_hwnd:
        vx, vy, vw, vh = _virtual_desktop()
        user32.SetWindowPos(_cursor_hwnd, HWND_TOPMOST, vx, vy, vw, vh, SWP_SHOWWINDOW)
        user32.ShowWindow(_cursor_hwnd, SW_SHOW)
        exclude_from_capture(int(_cursor_hwnd))
    from computer_use.cursor_manager import suppress_system_cursor

    suppress_system_cursor()


def _apply_hide() -> None:
    global _overlay_visible
    _overlay_visible = False
    hwnd = _hwnd
    if not hwnd:
        return
    faded = False
    try:
        from computer_use.composition_overlay import fade_display_overlay, stop_cursor_motion

        stop_cursor_motion()
        faded = bool(fade_display_overlay(0.0))
        if faded:
            ctypes.windll.kernel32.Sleep(180)
    except Exception:
        faded = False
    if not faded:
        for alpha in (200, 140, 80, 0):
            user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
            ctypes.windll.kernel32.Sleep(25)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    user32.ShowWindow(hwnd, SW_HIDE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_HIDEWINDOW | SWP_NOSIZE | SWP_NOMOVE)
    _apply_cursor_hide()
    from computer_use.cursor_manager import restore_system_cursor

    restore_system_cursor()


def _place_cursor(x: float, y: float, pose: dict, press: bool = False) -> None:
    if _hwnd:
        user32.SetWindowPos(_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
    if not _cursor_hwnd:
        return
    user32.SetWindowPos(_cursor_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
    user32.ShowWindow(_cursor_hwnd, SW_SHOW)
    try:
        from computer_use.composition_overlay import apply_cursor_pose, draw_cursor_surface

        tagged = dict(pose)
        tagged["press"] = 1.0 if press else float(pose.get("press") or 0.0)
        apply_cursor_pose(x, y, tagged)
        if press:
            draw_cursor_surface(True)
    except Exception:
        if not _cursor_stage:
            user32.SetWindowPos(_cursor_hwnd, HWND_TOPMOST, int(x) - 2, int(y) - 2, CURSOR_SIZE, CURSOR_SIZE, SWP_SHOWWINDOW)


def _play_cursor(op: tuple) -> None:
    x = float(op[1])
    y = float(op[2])
    pose = op[3] if len(op) > 3 and isinstance(op[3], dict) else {}
    samples = op[4] if len(op) > 4 and isinstance(op[4], list) else []
    press = bool(op[5]) if len(op) > 5 else False
    path = samples or [(x, y)]
    if _cursor_stage:
        try:
            from computer_use.composition_overlay import animate_cursor_path, swap_cursor_press

            if animate_cursor_path(path, pose):
                if press:
                    swap_cursor_press(True)
                    ctypes.windll.kernel32.Sleep(90)
                    swap_cursor_press(False)
                return
        except Exception:
            pass
    prev_x, prev_y = path[0]
    for i, point in enumerate(path):
        sx, sy = float(point[0]), float(point[1])
        last = i == len(path) - 1
        step_pose = pose if last else scoot_pose(sx - prev_x, sy - prev_y, press=False)
        _place_cursor(sx, sy, step_pose, press=press and last)
        prev_x, prev_y = sx, sy
        if not last:
            ctypes.windll.kernel32.Sleep(8)
    if press:
        ctypes.windll.kernel32.Sleep(90)
        _place_cursor(x, y, scoot_pose(0.0, 0.0, press=False), press=False)
        try:
            from computer_use.composition_overlay import swap_cursor_press

            swap_cursor_press(False)
        except Exception:
            pass


def _apply_cursor_hide() -> None:
    if _cursor_hwnd:
        user32.ShowWindow(_cursor_hwnd, SW_HIDE)


def _recreate_overlays() -> None:
    """Official: destroy + recreate overlay windows after display change / device loss."""
    global _hwnd, _cursor_hwnd, _cursor_stage, _last_recreate
    import time

    now = time.monotonic()
    if now - _last_recreate < 0.45:
        return
    _last_recreate = now
    try:
        from computer_use.composition_overlay import recreate_after_device_loss, stop_cursor_motion

        stop_cursor_motion()
        recreate_after_device_loss()
    except Exception:
        pass
    if _cursor_hwnd:
        user32.DestroyWindow(_cursor_hwnd)
        _cursor_hwnd = 0
    if _hwnd:
        user32.DestroyWindow(_hwnd)
        _hwnd = 0
    _hwnd = _create_window()
    _cursor_hwnd = _create_cursor_window()
    vx, vy, vw, vh = _virtual_desktop()
    try:
        from computer_use.composition_overlay import attach_yellow_bar

        attach_yellow_bar(_hwnd, vw, BAR_HEIGHT)
    except Exception:
        pass
    if _cursor_hwnd:
        try:
            from computer_use.composition_overlay import attach_cursor_stage

            _cursor_stage = bool(attach_cursor_stage(_cursor_hwnd, vw, vh, origin=(float(vx), float(vy))))
        except Exception:
            _cursor_stage = False
    try:
        from computer_use.composition_overlay import draw_cursor_surface

        draw_cursor_surface(False)
    except Exception:
        pass
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmFlush()
    except Exception:
        pass
    if _overlay_visible:
        _apply_show()


def _ui_loop() -> None:
    global _hwnd, _cursor_hwnd, _cursor_stage
    _ensure_mutex()
    _ensure_class()
    _hwnd = _create_window()
    _cursor_hwnd = _create_cursor_window()
    _install_win_event_hook()
    _ready.set()
    vx, vy, vw, vh = _virtual_desktop()
    try:
        from computer_use.composition_overlay import attach_yellow_bar

        attach_yellow_bar(_hwnd, vw, BAR_HEIGHT)
    except Exception:
        pass
    if _cursor_hwnd:
        try:
            from computer_use.composition_overlay import attach_cursor_stage

            _cursor_stage = bool(attach_cursor_stage(_cursor_hwnd, vw, vh, origin=(float(vx), float(vy))))
        except Exception:
            _cursor_stage = False
    msg = wintypes.MSG()
    while True:
        while True:
            try:
                op = _cmds.get_nowait()
            except queue.Empty:
                break
            if op == "show":
                _apply_show()
            elif op == "hide":
                _apply_hide()
            elif op == "recreate":
                _recreate_overlays()
            elif isinstance(op, tuple) and op and op[0] == "cursor":
                _play_cursor(op)
            elif op == "cursor-hide":
                _apply_cursor_hide()
            elif op == "quit":
                try:
                    from computer_use.composition_overlay import stop_cursor_motion

                    stop_cursor_motion()
                except Exception:
                    pass
                if _cursor_hwnd:
                    user32.DestroyWindow(_cursor_hwnd)
                    _cursor_hwnd = 0
                if _hwnd:
                    user32.DestroyWindow(_hwnd)
                    _hwnd = 0
                return
        if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        else:
            try:
                from computer_use.composition_overlay import device_lost

                if device_lost():
                    _cmds.put("recreate")
            except Exception:
                pass
            ctypes.windll.kernel32.Sleep(10)


def _ensure_ui() -> None:
    global _started
    if os_name() != "nt":
        return
    if _started:
        return
    _started = True
    threading.Thread(target=_ui_loop, name="cu-overlay", daemon=True).start()
    _ready.wait(timeout=2)


def show_banner() -> None:
    if os_name() != "nt":
        return
    _ensure_ui()
    _cmds.put("show")


def hide_banner() -> None:
    if os_name() != "nt":
        return
    _cmds.put("hide")


def move_software_cursor(
    x: float,
    y: float,
    pose: dict | None = None,
    samples: list | None = None,
    press: bool = False,
) -> None:
    if os_name() != "nt":
        return
    _ensure_ui()
    _cmds.put(("cursor", float(x), float(y), pose or {}, list(samples or []), bool(press)))


def hide_software_cursor() -> None:
    if os_name() != "nt":
        return
    _cmds.put("cursor-hide")


def os_name() -> str:
    import os

    return os.name
