"""Backend factory shared by CLI one-shot calls and the sidecar RPC."""

from __future__ import annotations

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop


def make_executor(
    backend_name: str,
    steal_focus: bool = True,
    # TC-21: official has no time-based observation expiry (helper-rs main.rs:115
    # sets helper.ttl_ms = 0); freshness is identity + bounds + human-input based.
    ttl_ms: int = 0,
    allowed_apps: list[str] | None = None,
) -> ToolExecutor:
    kwargs = {"ttl_ms": ttl_ms, "allowed_apps": allowed_apps}

    def wrap(backend) -> ToolExecutor:
        return ToolExecutor(ComputerUse(backend, **kwargs), steal_focus=steal_focus)

    if backend_name == "fake":
        return wrap(FakeDesktop())
    if backend_name == "helper":
        from computer_use.helper_backend import OfficialHelperDesktop

        return wrap(OfficialHelperDesktop())
    if backend_name in ("live", "windows"):
        from computer_use.windows_backend import WindowsDesktop

        driver = ComputerUse(WindowsDesktop(), **kwargs)
        driver.overlay.enabled = True
        return ToolExecutor(driver, steal_focus=steal_focus)
    return wrap(FakeDesktop())
