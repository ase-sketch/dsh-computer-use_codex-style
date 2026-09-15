from __future__ import annotations

import os
import subprocess
from typing import Any

from computer_use.errors import DesktopUnavailable
from computer_use.helper_locate import helper_env, locate_helper
from computer_use.helper_pipe import PIPE_ENV, decode_pipe_frame, encode_pipe_frame, pipe_path_from_env, wait_for_pipe
from computer_use.helper_protocol import decode_response, encode_request, turn_metadata


class HelperClient:
    """Spawn local codex-computer-use.exe and speak its JSON-line protocol."""

    def __init__(
        self,
        exe: str | None = None,
        timeout_ms: int = 20000,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        self.exe = exe
        self.timeout_ms = timeout_ms
        self.session_id = session_id
        self.turn_id = turn_id
        self._proc: subprocess.Popen[str] | None = None
        self._pipe: str | None = None
        self._next_id = 1

    def ensure(self) -> None:
        pipe = pipe_path_from_env()
        if pipe:
            self._pipe = pipe
            return
        if self._proc is not None and self._proc.poll() is None:
            return
        path = self.exe or (str(locate_helper()) if locate_helper() else "")
        if not path:
            raise DesktopUnavailable("codex-computer-use.exe not found")
        env = helper_env()
        spawn_pipe = env.get(PIPE_ENV, "").strip().lower() in {"1", "true", "yes"}
        self._proc = subprocess.Popen(
            [path, "--parent-pid", str(os.getpid())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # The helper speaks UTF-8; the Windows default (gbk here) decodes
            # non-ASCII app names/titles as a UnicodeDecodeError.
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if spawn_pipe:
            found = wait_for_pipe(8)
            if found:
                self._pipe = found
                return

    def request(self, method: str, params: dict[str, Any] | None = None, extra_meta: dict[str, Any] | None = None) -> Any:
        self.ensure()
        if self._pipe:
            return self._request_pipe(method, params, extra_meta)
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise DesktopUnavailable("helper stdin/stdout unavailable")
        req_id = self._next_id
        self._next_id += 1
        meta = dict(turn_metadata(self.session_id, self.turn_id))
        if extra_meta:
            meta.update(extra_meta)
        proc.stdin.write(encode_request(req_id, method, params, self.timeout_ms, meta or None))
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            err = proc.stderr.read() if proc.stderr else ""
            raise DesktopUnavailable((err or "").strip() or "helper exited without a result")
        payload = decode_response(line)
        if payload.get("ok"):
            return payload.get("result")
        if payload.get("approvalRequest"):
            return {"approvalRequest": payload["approvalRequest"]}
        raise DesktopUnavailable(str(payload.get("error") or "helper request failed"))

    def _request_pipe(self, method: str, params: dict[str, Any] | None, extra_meta: dict[str, Any] | None) -> Any:
        import time

        meta = dict(turn_metadata(self.session_id, self.turn_id))
        if extra_meta:
            meta.update(extra_meta)
        req_id = self._next_id
        self._next_id += 1
        frame = encode_pipe_frame(req_id, method, params, meta)
        assert self._pipe is not None
        with open(self._pipe, "r+b", buffering=0) as handle:
            handle.write(frame)
            buf = b""
            deadline = time.time() + self.timeout_ms / 1000
            while time.time() < deadline:
                chunk = handle.read(65536)
                if chunk:
                    buf += chunk
                message, buf = decode_pipe_frame(buf)
                if message is None:
                    continue
                if message.get("ok") or "result" in message:
                    return message.get("result")
                if message.get("approvalRequest"):
                    return {"approvalRequest": message["approvalRequest"]}
                err = message.get("error") or (message.get("params") or {}).get("error")
                raise DesktopUnavailable(str(err or "pipe request failed"))
        raise DesktopUnavailable("named pipe request timed out")

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(encode_request(self._next_id, "close", {}))
                proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.kill()
            proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
