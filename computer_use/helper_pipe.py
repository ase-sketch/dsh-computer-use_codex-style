"""Length-prefixed JSON-RPC named pipe (SKY_CUA_NATIVE_PIPE)."""

from __future__ import annotations

import json
import os
import struct
from typing import Any

PIPE_ENV = "SKY_CUA_NATIVE_PIPE"
MAX_OUTBOUND_FRAME_BYTES = 8 * 1024 * 1024
MAX_INBOUND_FRAME_BYTES = 64 * 1024 * 1024
REVERSE_APPROVAL_METHOD = "requestComputerUseApproval"


def encode_pipe_frame(req_id: int, method: str, params: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> bytes:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "request",
        "params": {"method": method, "params": params or {}, "codexTurnMetadata": meta or {}},
    }
    blob = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(blob) > MAX_OUTBOUND_FRAME_BYTES:
        raise ValueError(f"native pipe outbound frame exceeds 8 MiB ({len(blob)} bytes)")
    return struct.pack("<I", len(blob)) + blob


def decode_pipe_frame(buffer: bytes) -> tuple[dict[str, Any] | None, bytes]:
    if len(buffer) < 4:
        return None, buffer
    (length,) = struct.unpack_from("<I", buffer, 0)
    if length > MAX_INBOUND_FRAME_BYTES:
        raise ValueError(f"native pipe inbound frame exceeds 64 MiB ({length} bytes)")
    if len(buffer) < 4 + length:
        return None, buffer
    payload = json.loads(buffer[4 : 4 + length].decode("utf-8"))
    return payload, buffer[4 + length :]


def list_computer_use_pipes() -> list[str]:
    try:
        names = os.listdir(r"\\.\pipe")
    except OSError:
        return []
    hits = [name for name in names if "computer-use" in name.lower() or "codex-computer" in name.lower()]
    return [r"\\.\pipe\\" + name for name in hits]


def wait_for_pipe(timeout: float = 8) -> str | None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        pipes = list_computer_use_pipes()
        if pipes:
            return pipes[-1]
        time.sleep(0.2)
    return None


def pipe_path_from_env() -> str | None:
    raw = (os.environ.get("COMPUTER_USE_PIPE") or os.environ.get(PIPE_ENV) or "").strip()
    if raw in {"", "0", "false", "1", "true"}:
        return None
    if raw.startswith("\\\\.\\pipe\\") or raw.startswith("\\\\?\\pipe\\"):
        return raw
    if raw.startswith("codex-computer-use"):
        return r"\\.\pipe\\" + raw
    return raw if "pipe" in raw.lower() else None
