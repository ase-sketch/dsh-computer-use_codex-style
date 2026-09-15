"""Read Chromium History sqlite (Chrome/Edge) without the extension."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEBKIT_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def _profiles() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return [
        local / "Google" / "Chrome" / "User Data" / "Default" / "History",
        local / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
    ]


def webkit_to_iso(value: int) -> str:
    seconds = int(value) / 1_000_000
    stamp = WEBKIT_EPOCH.timestamp() + seconds
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def read_history(queries: list[str] | None = None, limit: int = 20, start: str = "", end: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for src in _profiles():
        if not src.is_file():
            continue
        tmp = Path(tempfile.gettempdir()) / f"cu-history-{src.parent.parent.name}.db"
        try:
            shutil.copy2(src, tmp)
        except OSError:
            continue
        try:
            conn = sqlite3.connect(str(tmp))
            cur = conn.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 500")
            for url, title, visited in cur.fetchall():
                iso = webkit_to_iso(int(visited or 0))
                rows.append({"url": str(url or ""), "title": str(title or ""), "dateVisited": iso})
            conn.close()
        except sqlite3.Error:
            continue
    if queries:
        needles = [item.lower() for item in queries]
        rows = [row for row in rows if any(n in row["url"].lower() or n in row["title"].lower() for n in needles)]
    if start:
        rows = [row for row in rows if row["dateVisited"] >= start]
    if end:
        rows = [row for row in rows if row["dateVisited"] <= end]
    return rows[: max(int(limit), 1)]
