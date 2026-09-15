"""UserAssist usage counts recovered from helper app_catalog.rs / user-assist.json."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

USERASSIST_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


@dataclass
class Usage:
    use_count: int
    last_used: str | None = None


def rot13(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:
            out.append(chr((code - 65 + 13) % 26 + 65))
        elif 97 <= code <= 122:
            out.append(chr((code - 97 + 13) % 26 + 97))
        else:
            out.append(char)
    return "".join(out)


def parse_count_blob(blob: bytes) -> Usage:
    from datetime import timedelta

    count = 0
    last_used = None
    if len(blob) >= 8:
        count = struct.unpack_from("<I", blob, 4)[0]
    if len(blob) >= 72:
        filetime = struct.unpack_from("<Q", blob, 60)[0]
        if filetime:
            last_used = (FILETIME_EPOCH + timedelta(microseconds=filetime / 10)).isoformat()
    return Usage(use_count=int(count), last_used=last_used)


def exe_key(path: str) -> str:
    name = path.replace("/", "\\").rsplit("\\", 1)[-1]
    return name.lower()


def merge_usage(apps: Iterable[object], usage: dict[str, Usage]) -> None:
    for app in apps:
        key = exe_key(str(getattr(app, "id", "")))
        hit = usage.get(key)
        if hit is None:
            continue
        app.use_count = hit.use_count
        app.last_used_date = hit.last_used


def read_user_assist() -> dict[str, Usage]:
    try:
        import winreg
    except ImportError:
        return {}
    found: dict[str, Usage] = {}
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, USERASSIST_ROOT)
    except OSError:
        return {}
    index = 0
    while True:
        try:
            guid = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            count_key = winreg.OpenKey(root, guid + r"\Count")
        except OSError:
            continue
        value_index = 0
        while True:
            try:
                name, data, _typ = winreg.EnumValue(count_key, value_index)
            except OSError:
                break
            value_index += 1
            decoded = rot13(name)
            key = exe_key(decoded)
            if isinstance(data, bytes):
                found[key] = parse_count_blob(data)
    return found
