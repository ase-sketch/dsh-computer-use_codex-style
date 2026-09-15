from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from computer_use.keys import virtual_keys

user32 = ctypes.WinDLL("user32", use_last_error=True)
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


def _send(inputs: list[INPUT]) -> None:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError("SendInput failed")


def virtual_abs(x: float, y: float, vx: int, vy: int, vw: int, vh: int) -> tuple[int, int]:
    span_x = max(int(vw) - 1, 1)
    span_y = max(int(vh) - 1, 1)
    return int((x - vx) * 65535 / span_x), int((y - vy) * 65535 / span_y)


def _abs_point(x: float, y: float) -> tuple[int, int]:
    vx = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    vy = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    vw = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)) or int(user32.GetSystemMetrics(0))
    vh = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)) or int(user32.GetSystemMetrics(1))
    return virtual_abs(x, y, vx, vy, vw, vh)


def _abs_flags(base: int) -> int:
    return base | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK


def move_click(x: float, y: float, button: str = "left", count: int = 1) -> None:
    ax, ay = _abs_point(x, y)
    flags = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "l": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "r": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        "m": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }[button]
    move = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(ax, ay, 0, _abs_flags(MOUSEEVENTF_MOVE), 0, 0)))
    for _ in range(max(count, 1)):
        down = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(ax, ay, 0, _abs_flags(flags[0]), 0, 0)))
        up = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(ax, ay, 0, _abs_flags(flags[1]), 0, 0)))
        _send([move, down, up])


def drag_points(x1: float, y1: float, x2: float, y2: float) -> None:
    a1x, a1y = _abs_point(x1, y1)
    a2x, a2y = _abs_point(x2, y2)
    move = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(a1x, a1y, 0, _abs_flags(MOUSEEVENTF_MOVE), 0, 0)))
    down = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(a1x, a1y, 0, _abs_flags(MOUSEEVENTF_LEFTDOWN), 0, 0)))
    to = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(a2x, a2y, 0, _abs_flags(MOUSEEVENTF_MOVE), 0, 0)))
    up = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(a2x, a2y, 0, _abs_flags(MOUSEEVENTF_LEFTUP), 0, 0)))
    _send([move, down, to, up])


def scroll_at(x: float, y: float, scroll_x: float, scroll_y: float) -> None:
    ax, ay = _abs_point(x, y)
    move = INPUT(INPUT_MOUSE, INPUTUNION(mi=MOUSEINPUT(ax, ay, 0, _abs_flags(MOUSEEVENTF_MOVE), 0, 0)))
    dy = int(-scroll_y) if scroll_y else int(scroll_x)
    wheel = INPUT(
        INPUT_MOUSE,
        INPUTUNION(mi=MOUSEINPUT(ax, ay, dy, _abs_flags(MOUSEEVENTF_WHEEL), 0, 0)),
    )
    _send([move, wheel])


def type_unicode(text: str) -> None:
    events: list[INPUT] = []
    for char in text:
        scan = ord(char)
        down = INPUT(INPUT_KEYBOARD, INPUTUNION(ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, 0)))
        up = INPUT(INPUT_KEYBOARD, INPUTUNION(ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
        events.extend([down, up])
    if events:
        _send(events)


def press_chord(key: str) -> None:
    vks = virtual_keys(key)
    downs = [INPUT(INPUT_KEYBOARD, INPUTUNION(ki=KEYBDINPUT(vk, 0, 0, 0, 0))) for vk in vks if vk]
    ups = [
        INPUT(INPUT_KEYBOARD, INPUTUNION(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)))
        for vk in reversed(vks)
        if vk
    ]
    _send(downs + ups)


def wait_ms(duration_ms: int) -> None:
    time.sleep(max(duration_ms, 0) / 1000.0)
