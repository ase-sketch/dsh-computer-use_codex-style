"""Best-effort UIA dump. Live path is in-process IUIAutomation only."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from computer_use.models import Bounds, UINode
from computer_use.win_capture import window_rect
from computer_use.win_dpi import physical_size_to_logical, physical_to_logical

SCRIPT = Path(__file__).with_name("win_tree.ps1")
UIA_TIMEOUT_SEC = 2


def _parse_nodes(raw: str) -> list[UINode]:
    data = json.loads(raw or "[]")
    if isinstance(data, dict):
        data = [data]
    nodes: list[UINode] = []
    for item in data:
        nodes.append(
            UINode(
                index=int(item["index"]),
                role=str(item.get("role") or "unknown"),
                name=str(item.get("name") or ""),
                bounds=Bounds(
                    float(item.get("x") or 0),
                    float(item.get("y") or 0),
                    float(item.get("width") or 0),
                    float(item.get("height") or 0),
                ),
                value=str(item.get("value") or ""),
                depth=int(item.get("depth") or 0),
            )
        )
    return nodes


def _kill_tree(pid: int) -> None:
    if os.name != "nt" or not pid:
        return
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        timeout=5,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def dump_tree(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> list[UINode]:
    """In-process IUIAutomation only (official accessibility.rs)."""
    try:
        from computer_use.win_uia import dump_tree as uia_dump

        return uia_dump(hwnd, title, origin, scale)
    except Exception:
        return _fallback_node(hwnd, title, origin, scale)


def dump_accessibility(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0):
    try:
        from computer_use.win_uia import dump_accessibility as uia_dump

        return uia_dump(hwnd, title, origin, scale)
    except Exception:
        from computer_use.win_uia import AccessibilityDump
        from computer_use.tree_format import focused_line

        nodes = _fallback_node(hwnd, title, origin, scale)
        return AccessibilityDump(nodes=nodes, focused=focused_line(nodes[0] if nodes else None))


def _dump_tree_powershell(hwnd: int, title: str) -> list[UINode]:
    """Unused live path. Kept as a last-resort helper, never called by dump_tree."""
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-Hwnd",
                str(hwnd),
            ],
            **kwargs,
        )
    except OSError:
        return _fallback_node(hwnd, title)
    try:
        stdout, _stderr = proc.communicate(timeout=UIA_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            proc.communicate(timeout=3)
        except Exception:
            proc.kill()
        return _fallback_node(hwnd, title)
    stdout = stdout if isinstance(stdout, str) else ""
    if proc.returncode != 0 or not stdout.strip():
        return _fallback_node(hwnd, title)
    try:
        nodes = _parse_nodes(stdout.strip())
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _fallback_node(hwnd, title)
    return nodes or _fallback_node(hwnd, title)


def _fallback_node(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> list[UINode]:
    try:
        left, top, width, height = window_rect(hwnd)
    except Exception:
        left, top, width, height = 0, 0, 1, 1
    scale = scale if scale > 0.01 else 1.0
    ox, oy = origin
    lx, ly = physical_to_logical(left, top, ox, oy, scale)
    lw, lh = physical_size_to_logical(width, height, scale)
    return [UINode(0, "window", title or str(hwnd), Bounds(lx, ly, float(lw), float(lh)))]
