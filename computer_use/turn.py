"""Official turn lifecycle: interrupt files + Local\\CodexComputerUseTurnEnded-*."""

from __future__ import annotations

import os
from pathlib import Path

from computer_use.helper_protocol import TURN_ENDED_EVENT_PREFIX, TURN_ENDED_MESSAGE
from computer_use.interrupt import interrupt_path


def bind_interrupt(flag, session_id: str, turn_id: str, codex_home: str | None = None) -> Path | None:
    home = codex_home or os.environ.get("CODEX_HOME")
    if not home:
        return None
    path = interrupt_path(home, session_id, turn_id)
    flag.path = path
    return path


def signal_turn_ended(session_id: str) -> str:
    name = TURN_ENDED_EVENT_PREFIX + "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateEventW(None, True, False, name)
        if handle:
            kernel32.SetEvent(handle)
            kernel32.CloseHandle(handle)
    return name


def turn_ended_payload(session_id: str, turn_id: str) -> dict[str, str]:
    return {
        "ended": True,
        "session_id": session_id,
        "turn_id": turn_id,
        "message": TURN_ENDED_MESSAGE,
        "event": TURN_ENDED_EVENT_PREFIX + session_id,
    }
