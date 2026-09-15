"""Official --system-cursor-manager child process.

Parent never calls SetSystemCursor. The child suppresses OEM cursors while the
overlay is visible, then always restores the user's scheme (SPI_SETCURSORS) on
restore, shutdown, parent death, or atexit.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from typing import Any

EVENT_SUPPRESS = "Local\\DshComputerUse-CursorSuppress"
EVENT_RESTORE = "Local\\DshComputerUse-CursorRestore"
EVENT_SHUTDOWN = "Local\\DshComputerUse-CursorShutdown"
EVENT_READY = "Local\\DshComputerUse-CursorReady"
EVENT_ACK = "Local\\DshComputerUse-CursorAck"
READY_TIMEOUT_MS = 5000
ACK_TIMEOUT_MS = 2000
SHUTDOWN_TIMEOUT_MS = 3000
MANAGER_NOT_READY = "system cursor manager did not become ready"
MANAGER_DID_NOT_EXIT = "system cursor manager did not exit after shutdown"
RESTORE_FAILED = "failed to restore system cursor after "

SPI_SETCURSORS = 0x0057
_OCR_IDS = (32512, 32513, 32514, 32515, 32516, 32631, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650, 32651)

_child: subprocess.Popen | None = None
_handles: dict[str, int] = {}


def _user32():
    import ctypes
    from ctypes import wintypes

    dll = ctypes.WinDLL("user32", use_last_error=True)
    dll.CreateCursor.restype = wintypes.HANDLE
    dll.CopyIcon.argtypes = [wintypes.HANDLE]
    dll.CopyIcon.restype = wintypes.HANDLE
    dll.SetSystemCursor.argtypes = [wintypes.HANDLE, ctypes.c_uint]
    dll.SetSystemCursor.restype = wintypes.BOOL
    dll.DestroyCursor.argtypes = [wintypes.HANDLE]
    dll.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    dll.SystemParametersInfoW.restype = wintypes.BOOL
    return dll


def _kernel32():
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def restore_cursor_scheme() -> bool:
    try:
        return bool(_user32().SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0))
    except Exception:
        return False


def _blank_and_set() -> None:
    user32 = _user32()
    and_mask = bytes([0xFF] * 128)
    xor_mask = bytes([0x00] * 128)
    blank = user32.CreateCursor(None, 0, 0, 32, 32, and_mask, xor_mask)
    if not blank:
        return
    try:
        for ocr in _OCR_IDS:
            copy = user32.CopyIcon(blank)
            if copy:
                user32.SetSystemCursor(copy, ocr)
    finally:
        user32.DestroyCursor(blank)


def _open_event(name: str, create: bool) -> int:
    import ctypes

    k32 = _kernel32()
    if create:
        handle = k32.CreateEventW(None, True, False, name)  # manual-reset
    else:
        handle = k32.OpenEventW(0x001F0003, False, name)
    return int(handle or 0)


def _pulse(handle: int) -> None:
    k32 = _kernel32()
    k32.SetEvent(handle)
    time.sleep(0.01)
    k32.ResetEvent(handle)


def _wait(handle: int, timeout_ms: int) -> bool:
    return int(_kernel32().WaitForSingleObject(handle, int(timeout_ms))) == 0


def run_manager(*, parent_pid: int = 0) -> int:
    """Child entry: --system-cursor-manager."""
    atexit.register(restore_cursor_scheme)
    suppress = _open_event(EVENT_SUPPRESS, True)
    restore = _open_event(EVENT_RESTORE, True)
    shutdown = _open_event(EVENT_SHUTDOWN, True)
    ready = _open_event(EVENT_READY, True)
    ack = _open_event(EVENT_ACK, True)
    if not all((suppress, restore, shutdown, ready, ack)):
        restore_cursor_scheme()
        return 1
    parent = 0
    if parent_pid:
        parent = int(_kernel32().OpenProcess(0x00100000, False, int(parent_pid)) or 0)
    _kernel32().SetEvent(ready)
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    k32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
    k32.WaitForMultipleObjects.restype = wintypes.DWORD
    handles = [suppress, restore, shutdown]
    if parent:
        handles.append(parent)
    array = (wintypes.HANDLE * len(handles))(*handles)
    hidden = False
    try:
        while True:
            idx = int(k32.WaitForMultipleObjects(len(handles), array, False, 0xFFFFFFFF))
            if idx == 0:  # suppress
                _kernel32().ResetEvent(suppress)
                _blank_and_set()
                hidden = True
                _pulse(ack)
            elif idx == 1:  # restore
                _kernel32().ResetEvent(restore)
                if not restore_cursor_scheme() and hidden:
                    raise OSError(RESTORE_FAILED + "restore")
                hidden = False
                _pulse(ack)
            else:  # shutdown or parent died
                break
    finally:
        restore_cursor_scheme()
        hidden = False
        _pulse(ack)
        for handle in (suppress, restore, shutdown, ready, ack, parent):
            if handle:
                _kernel32().CloseHandle(handle)
    return 0


def start_manager() -> None:
    """Parent: spawn --system-cursor-manager and wait for ready."""
    global _child, _handles
    if os.name != "nt":
        return
    if "pytest" in sys.modules:
        return
    if _child is not None and _child.poll() is None:
        return
    _handles = {
        "suppress": _open_event(EVENT_SUPPRESS, True),
        "restore": _open_event(EVENT_RESTORE, True),
        "shutdown": _open_event(EVENT_SHUTDOWN, True),
        "ready": _open_event(EVENT_READY, True),
        "ack": _open_event(EVENT_ACK, True),
    }
    cmd = [sys.executable, "-m", "computer_use", "--system-cursor-manager", "--parent-pid", str(os.getpid())]
    try:
        _child = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0),
        )
    except OSError:
        _child = None
        return
    if not _wait(_handles["ready"], READY_TIMEOUT_MS):
        shutdown_manager()
        raise OSError(MANAGER_NOT_READY)


def suppress_system_cursor() -> None:
    if os.name != "nt":
        return
    try:
        start_manager()
    except OSError:
        return
    if not _handles.get("suppress"):
        return
    _kernel32().ResetEvent(_handles["ack"])
    _kernel32().SetEvent(_handles["suppress"])
    _wait(_handles["ack"], ACK_TIMEOUT_MS)


def restore_system_cursor() -> None:
    restore_cursor_scheme()
    if not _handles.get("restore"):
        return
    _kernel32().ResetEvent(_handles["ack"])
    _kernel32().SetEvent(_handles["restore"])
    _wait(_handles["ack"], ACK_TIMEOUT_MS)


def shutdown_manager() -> None:
    global _child, _handles
    restore_cursor_scheme()
    if _handles.get("shutdown"):
        _kernel32().SetEvent(_handles["shutdown"])
    child = _child
    _child = None
    if child is not None:
        try:
            child.wait(timeout=SHUTDOWN_TIMEOUT_MS / 1000)
        except Exception:
            try:
                child.kill()
            except Exception:
                pass
            # Official: system cursor manager did not exit after shutdown
    for handle in _handles.values():
        if handle:
            try:
                _kernel32().CloseHandle(handle)
            except Exception:
                pass
    _handles = {}


def manager_status() -> dict[str, Any]:
    return {
        "running": _child is not None and _child.poll() is None,
        "pid": _child.pid if _child is not None else None,
    }
