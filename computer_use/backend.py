from __future__ import annotations

from typing import Protocol

from computer_use.models import ActionRecord, AppInfo, Observation, WindowRef


class DesktopBackend(Protocol):
    def list_apps(self) -> list[AppInfo]:
        ...

    def list_windows(self) -> list[WindowRef]:
        ...

    def get_window(self, spec: dict[str, object]) -> WindowRef:
        ...

    def launch_app(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def observe(self, spec: dict[str, object]) -> Observation:
        ...

    def click(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def type_text(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def press_key(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def scroll(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def drag(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def set_value(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def perform_secondary_action(self, spec: dict[str, object]) -> ActionRecord:
        ...

    def activate_window(self, spec: dict[str, object]) -> ActionRecord:
        ...
