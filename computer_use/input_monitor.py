"""Official input monitor: human input invalidates the last get_window_state.

Escape still ends the turn. Injected SendInput is ignored (LLMHF_INJECTED /
LLKHF_INJECTED). Accidental mouse-move no longer kills the turn — it requires
another observe, matching:

  user input was detected in this window; call get_window_state before continuing
"""

from __future__ import annotations

import threading
import time
from typing import Any

USER_INPUT_MESSAGE = (
    "user input was detected in this window; call get_window_state before continuing"
)
MONITOR_UNAVAILABLE = "user input monitor unavailable; guarded input cannot continue"

LLMHF_INJECTED = 0x00000001
LLKHF_INJECTED = 0x00000010


class InputMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.dirty = False
        self.reason = ""
        self.available = True
        self.synthetic_until = 0.0
        self.generation = 0

    def mark_synthetic(self, seconds: float = 0.25) -> None:
        with self._lock:
            self.synthetic_until = time.monotonic() + max(seconds, 0.0)

    def is_synthetic(self) -> bool:
        with self._lock:
            return time.monotonic() <= self.synthetic_until

    def mark_user_input(self, reason: str = "pointer") -> None:
        if self.is_synthetic():
            return
        with self._lock:
            self.dirty = True
            self.reason = reason
            self.generation += 1

    def clear(self) -> None:
        with self._lock:
            self.dirty = False
            self.reason = ""

    def require_clean(self, action: str) -> None:
        if not self.available:
            raise PermissionError(MONITOR_UNAVAILABLE)
        with self._lock:
            dirty = self.dirty
        if dirty:
            raise PermissionError(USER_INPUT_MESSAGE if action != "guard" else USER_INPUT_MESSAGE)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "dirty": self.dirty,
                "reason": self.reason,
                "available": self.available,
                "generation": self.generation,
            }


def injected_mouse(flags: int) -> bool:
    return bool(int(flags) & LLMHF_INJECTED)


def injected_key(flags: int) -> bool:
    return bool(int(flags) & LLKHF_INJECTED)
