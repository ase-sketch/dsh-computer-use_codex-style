"""Esc-to-cancel recovered from helper interruption + JS transport.

Helper writes `cache/computer-use/interrupts/{session}/{turn}` and JS rejects
with the physical Escape message. WH_MOUSE_LL watches overlay; we also hook
VK_ESCAPE so the same turn stop works without the official overlay process.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from computer_use.errors import TurnInterrupted
from computer_use.helper_protocol import TURN_ENDED_MESSAGE
from computer_use.input_monitor import InputMonitor, injected_key, injected_mouse

ESCAPE_MESSAGE = (
    "Computer Use was stopped by the user with the physical Escape key. "
    "Stop your work, do not call further Computer Use tools in this turn, "
    "and send a final message noting that the user stopped Computer Use."
)


def interrupt_path(codex_home: str, session_id: str, turn_id: str) -> Path:
    safe = lambda value: "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return Path(codex_home) / "cache" / "computer-use" / "interrupts" / safe(session_id) / safe(turn_id)


def signal_turn_ended(session_id: str, turn_id: str) -> None:
    """Official Local\\CodexComputerUseTurnEnded-* named event."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        safe = lambda value: "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:80]
        for name in (
            f"Local\\CodexComputerUseTurnEnded-{safe(session_id)}-{safe(turn_id)}",
            f"Local\\DshComputerUseTurnEnded-{safe(turn_id)}",
        ):
            handle = kernel32.CreateEventW(None, True, False, name)
            if handle:
                kernel32.SetEvent(handle)
    except Exception:
        return


def raise_if_interrupted(path: Path | None) -> None:
    if path is not None and path.exists():
        raise TurnInterrupted(ESCAPE_MESSAGE)


class InterruptFlag:
    def __init__(self) -> None:
        self.stopped = False
        self.ended = False
        self.path: Path | None = None
        self.session_id: str = "dsh"
        self.turn_id: str = "turn"
        self.exit_on_trip: bool = False
        self.input_monitor = InputMonitor()

    def trip(self) -> None:
        self.stopped = True
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(b"")
        signal_turn_ended(self.session_id, self.turn_id)
        try:
            from computer_use.overlay_win import hide_banner

            hide_banner()
        except Exception:
            pass
        if self.exit_on_trip:
            os._exit(130)

    def end_turn(self) -> None:
        self.ended = True
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(b"ended")

    def check(self) -> None:
        if self.ended:
            raise TurnInterrupted(TURN_ENDED_MESSAGE)
        if self.stopped:
            raise TurnInterrupted(ESCAPE_MESSAGE)
        raise_if_interrupted(self.path)


WM_APP_ARM = 0x8001
WM_APP_DISARM = 0x8002


class EscapeHook:
    """LL hooks only while overlay is visible. A standing WH_KEYBOARD_LL makes Windows
    hide the pointer on every key (Delete included) until the mouse moves."""

    def __init__(self, flag: InterruptFlag, overlay: object | None = None) -> None:
        self.flag = flag
        self.overlay = overlay
        self._hook = 0
        self._mouse_hook = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._thread_id = 0
        self._armed = False

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="cu-esc", daemon=True)
        self._thread.start()

    def arm(self) -> None:
        self._armed = True
        if os.name == "nt" and self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_APP_ARM, 0, 0)

    def disarm(self) -> None:
        self._armed = False
        if os.name == "nt" and self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_APP_DISARM, 0, 0)

    def stop(self) -> None:
        self._stop.set()
        if os.name == "nt" and self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.CallNextHookEx.restype = LRESULT
        WH_KEYBOARD_LL = 13
        WH_MOUSE_LL = 14
        WM_KEYDOWN = 0x0100
        WM_MOUSEMOVE = 0x0200
        VK_ESCAPE = 0x1B

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt_x", wintypes.LONG),
                ("pt_y", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        monitor = getattr(self.flag, "input_monitor", None)

        def proc(ncode: int, wparam: int, lparam: int) -> int:
            if ncode >= 0 and self._armed and int(wparam) == WM_KEYDOWN:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not injected_key(int(info.flags)):
                    if info.vkCode == VK_ESCAPE:
                        self.flag.trip()
                    elif monitor is not None:
                        monitor.mark_user_input("keyboard")
            return int(user32.CallNextHookEx(self._hook, ncode, wparam, lparam))

        def mouse_proc(ncode: int, wparam: int, lparam: int) -> int:
            if ncode >= 0 and self._armed and int(wparam) in {WM_MOUSEMOVE, 0x0201, 0x0204, 0x0207}:
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not injected_mouse(int(info.flags)) and monitor is not None:
                    if not monitor.is_synthetic():
                        monitor.mark_user_input("pointer")
            return int(user32.CallNextHookEx(self._mouse_hook, ncode, wparam, lparam))

        cb = HOOKPROC(proc)
        mouse_cb = HOOKPROC(mouse_proc)

        def install():
            if not self._hook:
                self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, cb, None, 0)
            if not self._mouse_hook:
                self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_cb, None, 0)

        def uninstall():
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = 0
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
                self._mouse_hook = 0

        if self._armed:
            install()
        msg = wintypes.MSG()
        while not self._stop.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if int(msg.message) == WM_APP_ARM:
                install()
                continue
            if int(msg.message) == WM_APP_DISARM:
                uninstall()
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        uninstall()
        _ = (cb, mouse_cb)
