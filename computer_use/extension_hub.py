"""Local bridge for the Chrome/Edge tab-claim extension (login-state tabs)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from computer_use.extension_transport import (
    TRANSPORT_HTTP,
    TRANSPORT_PIPE,
    PipeListener,
    pipe_name,
    resolve_transport,
)


class ExtensionHub:
    def __init__(self, transport: str | None = None) -> None:
        self.connected = False
        self.instance_id = ""
        self.family = "chrome"
        self.tabs: list[dict[str, Any]] = []
        self.pending: list[dict[str, Any]] = []
        self.results: dict[str, Any] = {}
        #: BR-21: page events forwarded by the extension (webmcp_changed, ...).
        self.page_events: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port = 8765
        # BR-19: the official family (native-messaging frames over the
        # codex-browser-use pipe) is the default; HTTP polling is the opt-in
        # fallback selected with COMPUTER_USE_EXTENSION_TRANSPORT=http.
        self.transport = resolve_transport(transport)
        self.listener: PipeListener | None = None
        self.serving = False

    def ingest(self, message: dict[str, Any]) -> None:
        with self.lock:
            kind = message.get("type")
            if kind == "hello":
                self.connected = True
                self.instance_id = str(message.get("instanceId") or self.instance_id)
                self.family = str(message.get("family") or self.family)
                tabs = message.get("tabs")
                if isinstance(tabs, list):
                    self.tabs = [item for item in tabs if isinstance(item, dict)]
            elif kind == "result":
                self.results[str(message.get("id") or "")] = message.get("result")
            elif kind == "page_event":
                event = message.get("event")
                if isinstance(event, dict):
                    self.page_events.append(event)

    def command(self, op: str, payload: dict[str, Any] | None = None, timeout: float = 8) -> Any:
        cmd_id = uuid.uuid4().hex
        body = {"id": cmd_id, "op": op, **(payload or {})}
        with self.lock:
            self.pending.append(body)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if cmd_id in self.results:
                    return self.results.pop(cmd_id)
            time.sleep(0.05)
        return {"error": "timeout waiting for extension"}

    def diagnose(self) -> dict[str, Any]:
        """BR-19: the official diagnostic layering. A missing extension is not a
        dead session; the model must be able to tell them apart
        (docs/browser-troubleshooting.md, docs/chrome-troubleshooting.md).

        The manifest half is the verbatim official check
        (scripts/check-native-host-manifest.js): a missing manifest and a
        missing extension produce different sentences.
        """
        from computer_use import browser_errors
        from computer_use.extension_transport import (
            EXTENSION_HOST_NAME,
            diagnose_manifest,
            manifest_path,
        )

        manifest: dict[str, Any] | None = None
        path = manifest_path()
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, dict):
                manifest = loaded
        status = diagnose_manifest(manifest, host_name=EXTENSION_HOST_NAME)
        report: dict[str, Any] = {
            "transport": self.transport,
            "endpoint": self.endpoint(),
            "manifestPath": status.get("manifestPath"),
            "manifestCorrect": bool(status.get("correct")),
            "manifestProblem": status.get("problem"),
        }
        if not self.connected:
            report.update(
                {
                    "connected": False,
                    "family": self.family,
                    "message": browser_errors.EXTENSION_COMMUNICATION_FAILED,
                }
            )
            return report
        report.update(
            {
                "connected": True,
                "instanceId": self.instance_id,
                "family": self.family,
                "tabCount": len(self.tabs),
            }
        )
        return report

    def take_page_events(self) -> list[dict[str, Any]]:
        """BR-21: drain the extension page events (official takePageEvents)."""
        with self.lock:
            events = list(self.page_events)
            self.page_events.clear()
            return events

    def pop_pending(self) -> list[dict[str, Any]]:
        with self.lock:
            commands = list(self.pending)
            self.pending.clear()
            return commands

    def claim(self, provider_tab_id: str, title: str, url: str, instance_id: str = "") -> dict[str, Any]:
        """BR-12: the match also honours metadata.extensionInstanceId so two
        profiles with an identically titled tab cannot cross-claim."""
        match = None
        for tab in self.tabs:
            if instance_id and str(tab.get("extensionInstanceId") or "") != str(instance_id):
                continue
            if (
                str(tab.get("providerTabId") or tab.get("id") or "") == provider_tab_id
                and str(tab.get("title") or "") == title
                and str(tab.get("url") or "") == url
            ):
                match = tab
                break
        if match is None:
            return {"claimed": False, "unavailable": True, "reason": "tab mention no longer matches"}
        if not self.serving:
            return {
                "id": provider_tab_id,
                "claimed": True,
                "unavailable": False,
                "type": "extension",
                "loginState": True,
                "title": title,
                "url": url,
            }
        result = self.command("claim", {"tabId": provider_tab_id})
        if result.get("error"):
            return {"claimed": False, "unavailable": True, "reason": str(result.get("error"))}
        return {
            "id": provider_tab_id,
            "claimed": True,
            "unavailable": False,
            "type": "extension",
            "loginState": True,
            "title": title,
            "url": url,
        }

    def get_context(self, provider_tab_id: str, title: str, url: str) -> dict[str, Any]:
        match = None
        for tab in self.tabs:
            if (
                str(tab.get("providerTabId") or tab.get("id") or "") == provider_tab_id
                and str(tab.get("title") or "") == title
                and str(tab.get("url") or "") == url
            ):
                match = tab
                break
        if match is None:
            return {"unavailable": True, "claimed": False}
        if not self.serving:
            text = str(match.get("text") or match.get("preview") or "")
            return {
                "kind": "text",
                "title": title,
                "url": url,
                "text": text[:8000],
                "truncated": len(text) > 8000,
                "claimed": False,
                "loginState": True,
            }
        result = self.command("context", {"tabId": provider_tab_id})
        if isinstance(result, dict) and not result.get("error"):
            result["claimed"] = False
            return result
        return {"unavailable": True, "claimed": False, "reason": str((result or {}).get("error") or "")}

    def endpoint(self) -> str:
        if self.transport == TRANSPORT_PIPE:
            return self.listener.name if self.listener else pipe_name()
        return f"http://127.0.0.1:{self.port}"

    def start(self, port: int = 8765, pipe_name_override: str | None = None) -> str:
        """BR-19: open the extension channel and return the endpoint in use.

        The default is the official transport family -- native-messaging frames
        over the codex-browser-use named pipe (PipeListener). Setting
        COMPUTER_USE_EXTENSION_TRANSPORT=http selects the legacy HTTP polling
        server. On a platform where the pipe cannot be created we fall through
        to HTTP instead of leaving the extension with no channel at all.
        """
        if self.transport == TRANSPORT_PIPE:
            self.listener = PipeListener(
                name=pipe_name_override, on_message=self.ingest, outbox=self.pop_pending
            )
            if self.listener.start():
                self.serving = True
                self.port = 0
                return self.listener.name
            self.listener = None
        return self._start_http(port)

    def _start_http(self, port: int = 8765) -> str:
        hub = self
        self.port = port

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8") or "{}")
                return data if isinstance(data, dict) else {}

            def _write(self, code: int, payload: dict[str, Any]) -> None:
                blob = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path == "/health":
                    self._write(200, {"ok": True, "connected": hub.connected})
                    return
                if path == "/pending":
                    self._write(200, {"commands": hub.pop_pending()})
                    return
                self._write(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if urlparse(self.path).path != "/ingest":
                    self._write(404, {"error": "not found"})
                    return
                hub.ingest(self._read_json())
                self._write(200, {"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.serving = True
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server = None
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self.serving = False
