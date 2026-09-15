r"""Chrome native messaging host: stdio native frames <-> the browser service.

BR-19. The extension side always speaks Chrome native messaging (4-byte
little-endian length prefix + UTF-8 JSON; see computer_use/extension_transport).
This process is the native host Chrome spawns: by default it bridges those
frames to the service listening on the official named pipe
(\\.\pipe\codex-browser-use); with COMPUTER_USE_EXTENSION_TRANSPORT=http it
falls back to running the legacy HTTP polling hub in-process so the extension
still gets an answer.
"""

from __future__ import annotations

import json
import struct
import sys

from computer_use.extension_transport import (
    NATIVE_MESSAGING_MAX_FROM_HOST,
    TRANSPORT_HTTP,
    PipeClient,
    encode_native_frame,
    resolve_transport,
)


def _read() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if not raw:
        return None
    (length,) = struct.unpack("<I", raw)
    if length > NATIVE_MESSAGING_MAX_FROM_HOST:
        raise ValueError("native messaging frame exceeds the 1 MiB host limit")
    payload = sys.stdin.buffer.read(length)
    message = json.loads(payload.decode("utf-8"))
    return message if isinstance(message, dict) else None


def _write(message: dict) -> None:
    sys.stdout.buffer.write(encode_native_frame(message))
    sys.stdout.buffer.flush()


def main() -> None:
    transport = resolve_transport()
    client: PipeClient | None = None
    hub = None
    if transport != TRANSPORT_HTTP:
        candidate = PipeClient()
        if candidate.connect():
            client = candidate
    if client is None:
        from computer_use.extension_hub import ExtensionHub

        hub = ExtensionHub(transport=TRANSPORT_HTTP)
        try:
            hub.start(8765)
        except OSError:
            pass
    while True:
        message = _read()
        if message is None:
            break
        if client is not None:
            client.send(message)
            for reply in client.poll(timeout=0.05):
                _write(reply)
        else:
            hub.ingest(message)
            _write({"ok": True, "commands": hub.pop_pending(), "connected": True})
    if client is not None:
        client.close()


if __name__ == "__main__":
    main()
