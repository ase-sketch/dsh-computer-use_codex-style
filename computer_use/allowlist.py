"""Persist Always-allow app ids like Codex Computer Use settings."""

from __future__ import annotations

import json
from pathlib import Path

ALLOW_FILE = Path.home() / ".codex" / "computer-use-allow.json"


def load_always(path: Path | None = None) -> set[str]:
    file = path or ALLOW_FILE
    if not file.is_file():
        return set()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    apps = data.get("always_allowed_app_ids") if isinstance(data, dict) else None
    if not isinstance(apps, list):
        return set()
    return {str(item).lower() for item in apps if str(item).strip()}


def save_always(apps: set[str], path: Path | None = None) -> None:
    file = path or ALLOW_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"always_allowed_app_ids": sorted(apps)}
    file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
