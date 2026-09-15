from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from computer_use.cdp_http import list_tabs

EDGE = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe"
)
EDGE_ALT = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"


def edge_exe() -> Path | None:
    for path in (EDGE, EDGE_ALT):
        if path.is_file():
            return path
    return None


def wait_cdp(port: int, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if list_tabs(port=port, timeout=0.4):
            return True
        time.sleep(0.25)
    return False


def launch_edge(port: int, user_data: Path) -> subprocess.Popen[str]:
    exe = edge_exe()
    if exe is None:
        raise FileNotFoundError("msedge.exe not found")
    user_data.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            str(exe),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data}",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if not wait_cdp(port):
        proc.kill()
        raise TimeoutError(f"CDP did not come up on {port}")
    return proc
