from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

from computer_use.errors import DesktopUnavailable
from computer_use.models import AppInfo, WindowRef

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _exe_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return f"pid-{pid}"
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return f"pid-{pid}"
        return Path(buf.value).name or buf.value
    finally:
        kernel32.CloseHandle(handle)


def _is_target(hwnd: int) -> bool:
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.GetWindow(hwnd, 4):  # GW_OWNER
        return False
    return bool(_window_title(hwnd))


def enum_windows() -> list[WindowRef]:
    found: list[WindowRef] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if _is_target(hwnd):
            app = _exe_name(_pid(hwnd))
            found.append(WindowRef(app=app, id=int(hwnd), title=_window_title(hwnd)))
        return True

    if not user32.EnumWindows(WNDENUMPROC(callback), 0):
        raise DesktopUnavailable("EnumWindows failed")
    return found


def list_apps_from_windows(windows: list[WindowRef]) -> list[AppInfo]:
    grouped: dict[str, AppInfo] = {}
    for window in windows:
        app = grouped.get(window.app)
        if app is None:
            app = AppInfo(id=window.app, display_name=window.app, is_running=True)
            grouped[window.app] = app
        app.windows.append(window)
    return list(grouped.values())
