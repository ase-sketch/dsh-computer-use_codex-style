"""Minimal CDP JSON-RPC over WebSocket (Chrome DevTools Protocol)."""

from __future__ import annotations

import json
import time
from typing import Any

import websocket


class CdpConn:
    def __init__(self, url: str, timeout: float = 20) -> None:
        self.url = url
        self.ws = websocket.create_connection(url, timeout=timeout)
        self._id = 0
        self._seq = 0
        self.events: list[dict[str, Any]] = []

    def _take(self) -> dict[str, Any]:
        raw = self.ws.recv()
        msg = json.loads(raw)
        if msg.get("method"):
            self._seq += 1
            msg["_sequence"] = self._seq
            self.events.append(msg)
        return msg

    def read_events(self, after_sequence: int = 0, methods: list[str] | None = None, timeout_ms: int = 0) -> list[dict[str, Any]]:
        if timeout_ms > 0:
            deadline = time.time() + timeout_ms / 1000
            while time.time() < deadline:
                try:
                    self.ws.settimeout(max(0.05, deadline - time.time()))
                    self._take()
                except Exception:
                    break
        allowed = set(methods) if methods else None
        out = []
        for msg in self.events:
            seq = int(msg.get("_sequence") or 0)
            if seq <= after_sequence:
                continue
            name = str(msg.get("method") or "")
            if allowed is not None and name not in allowed:
                continue
            out.append({"sequence": seq, "method": name, "params": msg.get("params") or {}})
        return out

    def last_event(self, method: str) -> dict[str, Any] | None:
        for msg in reversed(self.events):
            if msg.get("method") == method:
                params = msg.get("params")
                return params if isinstance(params, dict) else {}
        return None

    def pop_event(self, method: str) -> dict[str, Any] | None:
        for index in range(len(self.events) - 1, -1, -1):
            if self.events[index].get("method") == method:
                msg = self.events.pop(index)
                params = msg.get("params")
                return params if isinstance(params, dict) else {}
        return None

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 20) -> dict[str, Any]:
        self._id += 1
        nid = self._id
        self.ws.send(json.dumps({"id": nid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.2, deadline - time.time()))
            msg = self._take()
            if msg.get("id") != nid:
                continue
            if msg.get("error"):
                raise RuntimeError(f"{method}: {msg['error']}")
            result = msg.get("result")
            return result if isinstance(result, dict) else {}
        raise TimeoutError(method)

    def wait_event(self, name: str, timeout: float = 20) -> dict[str, Any]:
        cached = self.last_event(name)
        if cached is not None:
            return cached
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.2, deadline - time.time()))
            msg = self._take()
            if msg.get("method") == name:
                params = msg.get("params")
                return params if isinstance(params, dict) else {}
        raise TimeoutError(name)

    def close(self) -> None:
        try:
            self.ws.close()
        except OSError:
            pass
