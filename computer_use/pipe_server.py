"""Named-pipe server: 4-byte LE length + JSON-RPC 2.0, matching NativePipeTransport."""

from __future__ import annotations

import json
import os
import struct
import threading
from typing import Any, Callable

from computer_use.helper_pipe import (
    MAX_INBOUND_FRAME_BYTES,
    MAX_OUTBOUND_FRAME_BYTES,
    REVERSE_APPROVAL_METHOD,
    decode_pipe_frame,
    encode_pipe_frame,
)

PIPE_NAME_DEFAULT = r"\\.\pipe\dsh-computer-use"


def default_pipe_name() -> str:
    override = (os.environ.get("COMPUTER_USE_PIPE") or "").strip()
    if override.startswith("\\\\.\\pipe\\"):
        return override
    return PIPE_NAME_DEFAULT + "-" + str(os.getpid())


def encode_result(req_id: Any, result: Any) -> bytes:
    blob = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, default=str).encode("utf-8")
    if len(blob) > MAX_OUTBOUND_FRAME_BYTES:
        raise ValueError("native pipe outbound frame exceeds 8 MiB")
    return struct.pack("<I", len(blob)) + blob


def encode_error(req_id: Any, message: str, code: int = -32000) -> bytes:
    blob = json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}).encode("utf-8")
    return struct.pack("<I", len(blob)) + blob


def handle_pipe_payload(payload: dict[str, Any], dispatch: Callable[[str, dict[str, Any]], Any]) -> bytes:
    req_id = payload.get("id")
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if method == "request":
        inner = str(params.get("method") or "")
        inner_params = params.get("params") if isinstance(params.get("params"), dict) else {}
        try:
            result = dispatch(inner, inner_params)
            return encode_result(req_id, result)
        except Exception as exc:
            return encode_error(req_id, str(exc))
    if method == REVERSE_APPROVAL_METHOD:
        return encode_result(req_id, {"action": "accept"})
    try:
        result = dispatch(method, params)
        return encode_result(req_id, result)
    except Exception as exc:
        return encode_error(req_id, str(exc))


def start_pipe_thread(dispatch: Callable[[str, dict[str, Any]], Any], name: str | None = None) -> str | None:
    if os.name != "nt":
        return None
    pipe_name = name or default_pipe_name()

    def _run() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PIPE_ACCESS_DUPLEX = 0x00000003
            PIPE_TYPE_BYTE = 0x00000000
            PIPE_READMODE_BYTE = 0x00000000
            PIPE_WAIT = 0x00000000
            handle = kernel32.CreateNamedPipeW(
                pipe_name,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                1,
                MAX_OUTBOUND_FRAME_BYTES,
                MAX_INBOUND_FRAME_BYTES,
                0,
                None,
            )
            if handle in (0, wintypes.HANDLE(-1).value if False else -1):
                return
            if not kernel32.ConnectNamedPipe(handle, None):
                kernel32.CloseHandle(handle)
                return
            buf = b""
            read_buf = ctypes.create_string_buffer(65536)
            read = wintypes.DWORD()
            while True:
                ok = kernel32.ReadFile(handle, read_buf, 65536, ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                buf += read_buf.raw[: read.value]
                while True:
                    try:
                        payload, buf = decode_pipe_frame(buf)
                    except ValueError:
                        break
                    if payload is None:
                        break
                    frame = handle_pipe_payload(payload, dispatch)
                    written = wintypes.DWORD()
                    kernel32.WriteFile(handle, frame, len(frame), ctypes.byref(written), None)
            kernel32.CloseHandle(handle)
        except Exception:
            return

    threading.Thread(target=_run, name="cu-pipe", daemon=True).start()
    return pipe_name
