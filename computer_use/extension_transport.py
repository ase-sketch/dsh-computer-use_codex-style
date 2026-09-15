r"""BR-19: the extension transport is the official native-messaging family.

Evidence (packaged bundle
~/.codex/plugins/cache/openai-bundled/browser/26.903.61454/):

* named pipe -- browser-service.mjs @241933:
  fa = e => e === "win32" ? "\\\\.\\pipe\\codex-browser-use" : "/tmp/codex-browser-use"
* native host identity -- scripts/extension-ids.json:
  "extensionHostName": "com.openai.codexextension",
  "windowsNativeMessaging": { "manifestDirectory": "AppData/Local/OpenAI/extension",
                              "registryRoot": "HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts" }
* extension ids -- scripts/extension-ids.json:
  chrome/brave/opera/vivaldi "hehggadaopoacecdllhhajmbjkdcmajg",
  edge "odlomjlbamekndcpllcnffbgeohgkmjh";
  allowed origins are chrome-extension://<id>/ (scripts/check-native-host-manifest.js:202)
* manifest problems -- scripts/check-native-host-manifest.js:134-150,270-290
* instance identity -- browser-service.mjs @226692:
  BROWSER_USE_PREFERRED_EXTENSION_INSTANCE_ID / BROWSER_USE_PREFERRED_WINDOW_ID
* diagnostics -- scripts/check-native-host-manifest.js, chromium-browser-diagnostics.mjs

Frame format: Chrome native messaging = 4-byte little-endian length prefix +
UTF-8 JSON. Limits from the Chrome contract: host -> browser 1 MiB,
browser -> host 64 MiB.

Verified vs. inferred (honest boundary):

* verified in the package: the pipe name, the host name, the manifest location
  and registry root, the two extension ids, the allowed-origin shape, the
  diagnostic sentences, and the 4-byte length-prefixed frame (the shape Chrome
  mandates and the one our existing native_host.py already used).
* NOT in the package: the official *extension* source, so the payload schema of
  the native-messaging messages cannot be reproduced. DSH keeps its own
  hello/pending/result payloads over the official framing and pipe. This module
  therefore delivers the same transport *family*, not byte-compatible frames
  with the OpenAI extension.

Default transport (deliberate, evidence-driven): HTTP polling stays the default
because the official *native-messaging payload envelope* is not in the package
(there is no extension source), and DSH's shipped extension still polls HTTP.
Selecting the official family is one environment variable away
(COMPUTER_USE_EXTENSION_TRANSPORT=pipe); flipping the default is recommended
only once the official envelope is known. The gap and the migration plan are
recorded in analysis/deep-dive/_fixes-browser-final.md.
"""

from __future__ import annotations

import json
import os
import struct
import threading
from pathlib import Path
from typing import Any, Callable

# --- Official identity ------------------------------------------------------

PIPE_NAME_WIN32 = "\\\\.\\pipe\\codex-browser-use"
PIPE_NAME_POSIX = "/tmp/codex-browser-use"

EXTENSION_HOST_NAME = "com.openai.codexextension"
WINDOWS_MANIFEST_DIRECTORY = "AppData/Local/OpenAI/extension"
WINDOWS_NATIVE_MESSAGING_REGISTRY_ROOT = r"HKCU\Software\Google\Chrome\NativeMessagingHosts"

#: scripts/extension-ids.json "extensionIds".
EXTENSION_IDS = (
    "hehggadaopoacecdllhhajmbjkdcmajg",
    "odlomjlbamekndcpllcnffbgeohgkmjh",
)
#: scripts/extension-ids.json per-family "storeExtensionId".
STORE_EXTENSION_IDS = {
    "chrome": "hehggadaopoacecdllhhajmbjkdcmajg",
    "brave": "hehggadaopoacecdllhhajmbjkdcmajg",
    "opera": "hehggadaopoacecdllhhajmbjkdcmajg",
    "vivaldi": "hehggadaopoacecdllhhajmbjkdcmajg",
    "edge": "odlomjlbamekndcpllcnffbgeohgkmjh",
}
#: Official mac/linux manifest directories (chromium-browser-diagnostics.mjs).
MACOS_MANIFEST_DIRECTORY = "Library/Application Support/Google/Chrome/NativeMessagingHosts"
LINUX_MANIFEST_DIRECTORY = ".config/google-chrome/NativeMessagingHosts"

#: Native messaging frame limits (Chrome contract).
NATIVE_MESSAGING_MAX_FROM_HOST = 1024 * 1024
NATIVE_MESSAGING_MAX_TO_HOST = 64 * 1024 * 1024

#: Transport selection.
TRANSPORT_PIPE = "pipe"
TRANSPORT_HTTP = "http"
TRANSPORTS = (TRANSPORT_PIPE, TRANSPORT_HTTP)
#: The official transport family is TRANSPORT_PIPE. The default stays HTTP
#: because the official payload envelope is unknown (no extension source) and
#: changing the pipe under a shipped HTTP-polling extension would break it
#: without a verified counterpart. See the module docstring.
DEFAULT_TRANSPORT = TRANSPORT_HTTP
ENV_TRANSPORT = "COMPUTER_USE_EXTENSION_TRANSPORT"
ENV_PIPE_NAME = "COMPUTER_USE_EXTENSION_PIPE"

#: Official instance identity env (browser-service.mjs @226692).
ENV_PREFERRED_INSTANCE_ID = "BROWSER_USE_PREFERRED_EXTENSION_INSTANCE_ID"
ENV_PREFERRED_WINDOW_ID = "BROWSER_USE_PREFERRED_WINDOW_ID"

#: Official diagnostic sentences (verbatim).
PROBLEM_REGISTRY_KEY_MISSING = "Windows native host registry key does not exist: {key}"
PROBLEM_MANIFEST_MISSING = "Native host manifest does not exist: {path}"
PROBLEM_NAME_MISMATCH = "manifest name does not match {host}"
PROBLEM_ORIGINS_MISSING = "allowed_origins does not include {origins}"
PROBLEM_REGISTRY_PATH_MISMATCH = "registry manifest path does not match checked manifest path"
PROBLEM_MANIFEST_UNREADABLE = "Could not read native host manifest {path}: {error}"
PROBLEM_NO_IDENTITY = (
    "Native host diagnostics are unavailable until a runtime identity is configured."
)
PROBLEM_UNKNOWN_FAMILY = "No generated diagnostics are available for browser family {family}."
PROBLEM_UNSUPPORTED_PLATFORM = (
    "Unsupported platform for native host manifest check: {platform}."
)


def pipe_name(platform: str | None = None) -> str:
    """Official fa(platform) @241933, with a DSH override for tests/deployments."""
    override = (os.environ.get(ENV_PIPE_NAME) or "").strip()
    if override:
        return override
    system = platform or ("win32" if os.name == "nt" else "linux")
    return PIPE_NAME_WIN32 if system == "win32" else PIPE_NAME_POSIX


def transport_override() -> str:
    return (os.environ.get(ENV_TRANSPORT) or "").strip().lower()


def resolve_transport(value: str | None = None) -> str:
    """COMPUTER_USE_EXTENSION_TRANSPORT, defaulting to the official family."""
    chosen = (value if value is not None else transport_override()).strip().lower()
    if chosen not in TRANSPORTS:
        return DEFAULT_TRANSPORT
    return chosen


def preferred_instance_id() -> str:
    return (os.environ.get(ENV_PREFERRED_INSTANCE_ID) or "").strip()


def preferred_window_id() -> int | None:
    raw = (os.environ.get(ENV_PREFERRED_WINDOW_ID) or "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


# --- Native messaging framing ----------------------------------------------


def encode_native_frame(message: Any) -> bytes:
    blob = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(blob)) + blob


def decode_native_frame(buffer: bytes) -> tuple[Any | None, bytes]:
    """(message, rest). Returns (None, buffer) while the frame is incomplete."""
    if len(buffer) < 4:
        return None, buffer
    (length,) = struct.unpack("<I", buffer[:4])
    if length > NATIVE_MESSAGING_MAX_FROM_HOST:
        raise ValueError(
            "native messaging frame exceeds the 1 MiB host -> browser limit"
        )
    if len(buffer) < 4 + length:
        return None, buffer
    payload = buffer[4 : 4 + length]
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid native messaging frame: {error}") from error
    return message, buffer[4 + length :]


# --- Manifest ---------------------------------------------------------------


def manifest_directory(platform: str | None = None) -> str:
    system = platform or ("win32" if os.name == "nt" else "linux")
    if system == "win32":
        return WINDOWS_MANIFEST_DIRECTORY
    if system == "darwin":
        return MACOS_MANIFEST_DIRECTORY
    return LINUX_MANIFEST_DIRECTORY


def manifest_path(home: str | os.PathLike[str] | None = None,
                  platform: str | None = None,
                  host_name: str = EXTENSION_HOST_NAME) -> Path:
    """Official getDefaultWindowsManifestPath / resolveLinuxNativeMessagingManifestPath."""
    root = Path(home) if home else Path.home()
    return root.joinpath(*manifest_directory(platform).split("/")).joinpath(
        f"{host_name}.json"
    )


def allowed_origins(extension_ids: tuple[str, ...] = EXTENSION_IDS) -> list[str]:
    """Official: expectedOrigins = ids.map(id => chrome-extension://<id>/) @check-native-host-manifest.js:202."""
    return [f"chrome-extension://{extension_id}/" for extension_id in extension_ids]


def manifest_document(host_path: str, extension_ids: tuple[str, ...] = EXTENSION_IDS,
                      host_name: str = EXTENSION_HOST_NAME) -> dict[str, Any]:
    """The native-host manifest Chrome expects (official shape, DSH host path)."""
    return {
        "name": host_name,
        "description": "DeepSeek Harness browser tab bridge",
        "path": str(host_path),
        "type": "stdio",
        "allowed_origins": allowed_origins(extension_ids),
    }


def diagnose_manifest(
    manifest: dict[str, Any] | None = None,
    *,
    home: str | os.PathLike[str] | None = None,
    platform: str | None = None,
    host_name: str = EXTENSION_HOST_NAME,
    extension_ids: tuple[str, ...] = EXTENSION_IDS,
    registry_key_exists: bool | None = None,
    registry_manifest_path: str | None = None,
) -> dict[str, Any]:
    """Official getNativeHostManifestStatus (check-native-host-manifest.js:200-290).

    Returns the same fields the official script prints, including the verbatim
    problem sentence when the manifest is not correct.
    """
    system = platform or ("win32" if os.name == "nt" else "linux")
    if system not in {"win32", "darwin", "linux"}:
        return {"correct": False, "problem": PROBLEM_UNSUPPORTED_PLATFORM.format(platform=system)}
    expected_origins = allowed_origins(extension_ids)
    location = manifest_path(home, platform=system, host_name=host_name)
    problems: list[str] = []
    if system == "win32" and registry_key_exists is False:
        problems.append(
            PROBLEM_REGISTRY_KEY_MISSING.format(
                key=f"{WINDOWS_NATIVE_MESSAGING_REGISTRY_ROOT}\\{host_name}"
            )
        )
    if manifest is None:
        problems.append(PROBLEM_MANIFEST_MISSING.format(path=str(location)))
        return {
            "correct": False,
            "manifestPath": str(location),
            "expectedHostName": host_name,
            "expectedExtensionIds": list(extension_ids),
            "expectedOrigins": expected_origins,
            "exists": False,
            "problem": "; ".join(problems),
        }
    name_matches = manifest.get("name") == host_name
    origins = manifest.get("allowed_origins")
    allowed = list(origins) if isinstance(origins, list) else []
    missing = [origin for origin in expected_origins if origin not in allowed]
    registry_matches = registry_manifest_path is None or str(location) == str(registry_manifest_path)
    if not name_matches:
        problems.append(PROBLEM_NAME_MISMATCH.format(host=host_name))
    if missing:
        problems.append(PROBLEM_ORIGINS_MISSING.format(origins=", ".join(missing)))
    if not registry_matches:
        problems.append(PROBLEM_REGISTRY_PATH_MISMATCH)
    return {
        "correct": not problems,
        "manifestPath": str(location),
        "expectedHostName": host_name,
        "actualHostName": manifest.get("name"),
        "expectedExtensionIds": list(extension_ids),
        "expectedOrigins": expected_origins,
        "allowedOrigins": allowed,
        "exists": True,
        "problem": "; ".join(problems) if problems else None,
    }


# --- Windows named pipe -----------------------------------------------------


_TYPED_KERNEL32: Any = None
_INVALID_HANDLE: int = -1


def _kernel32() -> Any:
    """kernel32 with explicit signatures.

    ctypes defaults restype to c_int, which truncates a 64-bit HANDLE and makes
    every later WriteFile/ReadFile fail; the pipe client hit exactly that.
    """
    global _TYPED_KERNEL32, _INVALID_HANDLE
    if _TYPED_KERNEL32 is not None:
        return _TYPED_KERNEL32
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel32.ConnectNamedPipe.restype = wintypes.BOOL
    kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.PeekNamedPipe.restype = wintypes.BOOL
    kernel32.PeekNamedPipe.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _INVALID_HANDLE = ctypes.c_void_p(-1).value
    _TYPED_KERNEL32 = kernel32
    return kernel32


def _handle_ok(handle: Any) -> bool:
    return handle not in (0, None) and handle != _INVALID_HANDLE


class PipeListener:
    """The official side of the channel: listen on the named pipe, speak native frames.

    Only one client at a time (like the official host). Windows only; on other
    platforms start() reports False and the caller falls back to HTTP.
    """

    def __init__(self, name: str | None = None,
                 on_message: Callable[[dict[str, Any]], None] | None = None,
                 outbox: Callable[[], list[dict[str, Any]]] | None = None) -> None:
        self.name = name or pipe_name()
        self.on_message = on_message
        self.outbox = outbox
        self.connected = False
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        if os.name != "nt":
            return False
        worker = threading.Thread(target=self._run, name="cu-extension-pipe", daemon=True)
        self.thread = worker
        worker.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        try:
            kernel32 = _kernel32()
            PIPE_ACCESS_DUPLEX = 0x00000003
            PIPE_TYPE_BYTE = 0x00000000
            PIPE_READMODE_BYTE = 0x00000000
            PIPE_WAIT = 0x00000000
            handle = kernel32.CreateNamedPipeW(
                self.name,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                1,
                NATIVE_MESSAGING_MAX_TO_HOST,
                NATIVE_MESSAGING_MAX_FROM_HOST,
                0,
                None,
            )
            if not _handle_ok(handle):
                return
            if not kernel32.ConnectNamedPipe(handle, None):
                # ERROR_PIPE_CONNECTED (535) means a client connected between
                # CreateNamedPipeW and ConnectNamedPipe -- a success, not a
                # failure. Treating it as failure closed the pipe under the
                # client and broke WriteFile (observed race).
                if ctypes.get_last_error() != 535:
                    kernel32.CloseHandle(handle)
                    return
            self.connected = True
            buffer = b""
            read_buffer = ctypes.create_string_buffer(65536)
            read = wintypes.DWORD()
            while not self._stop.is_set():
                ok = kernel32.ReadFile(handle, read_buffer, 65536, ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                buffer += read_buffer.raw[: read.value]
                while True:
                    try:
                        message, buffer = decode_native_frame(buffer)
                    except ValueError:
                        buffer = b""
                        break
                    if message is None:
                        break
                    if self.on_message is not None and isinstance(message, dict):
                        self.on_message(message)
                    for reply in (self.outbox() if self.outbox else []):
                        frame = encode_native_frame(reply)
                        written = wintypes.DWORD()
                        kernel32.WriteFile(handle, frame, len(frame), ctypes.byref(written), None)
            kernel32.CloseHandle(handle)
        except Exception:
            pass
        finally:
            self.connected = False


class PipeClient:
    """The native-host side: connect to the service pipe and speak native frames."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or pipe_name()
        self.handle: Any = None

    def connect(self) -> bool:
        if os.name != "nt":
            return False
        import ctypes

        kernel32 = _kernel32()
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        handle = kernel32.CreateFileW(
            self.name,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if not _handle_ok(handle):
            return False
        self.handle = handle
        return True

    def send(self, message: Any) -> bool:
        if self.handle is None:
            return False
        import ctypes
        from ctypes import wintypes

        kernel32 = _kernel32()
        frame = encode_native_frame(message)
        written = wintypes.DWORD()
        return bool(kernel32.WriteFile(self.handle, frame, len(frame), ctypes.byref(written), None))

    def pending_bytes(self) -> int:
        if self.handle is None:
            return 0
        import ctypes
        from ctypes import wintypes

        kernel32 = _kernel32()
        available = wintypes.DWORD()
        ok = kernel32.PeekNamedPipe(
            self.handle, None, 0, None, ctypes.byref(available), None
        )
        return int(available.value) if ok else 0

    def poll(self, timeout: float = 0.0, interval: float = 0.01) -> list[Any]:
        """Drain whatever the service sent, waiting up to timeout seconds."""
        import ctypes
        import time as _time
        from ctypes import wintypes

        if self.handle is None:
            return []
        kernel32 = _kernel32()
        deadline = _time.time() + max(0.0, timeout)
        buffer = b""
        read_buffer = ctypes.create_string_buffer(65536)
        read = wintypes.DWORD()
        messages: list[Any] = []
        while True:
            if self.pending_bytes() == 0:
                if _time.time() >= deadline:
                    break
                _time.sleep(interval)
                continue
            ok = kernel32.ReadFile(
                self.handle, read_buffer, 65536, ctypes.byref(read), None
            )
            if not ok or read.value == 0:
                break
            buffer += read_buffer.raw[: read.value]
            while True:
                try:
                    message, buffer = decode_native_frame(buffer)
                except ValueError:
                    buffer = b""
                    break
                if message is None:
                    break
                messages.append(message)
        return messages

    def close(self) -> None:
        if self.handle is None:
            return
        try:
            _kernel32().CloseHandle(self.handle)
        finally:
            self.handle = None


__all__ = [
    "DEFAULT_TRANSPORT",
    "ENV_PIPE_NAME",
    "ENV_PREFERRED_INSTANCE_ID",
    "ENV_PREFERRED_WINDOW_ID",
    "ENV_TRANSPORT",
    "EXTENSION_HOST_NAME",
    "EXTENSION_IDS",
    "MACOS_MANIFEST_DIRECTORY",
    "NATIVE_MESSAGING_MAX_FROM_HOST",
    "NATIVE_MESSAGING_MAX_TO_HOST",
    "PIPE_NAME_POSIX",
    "PIPE_NAME_WIN32",
    "PROBLEM_MANIFEST_MISSING",
    "PROBLEM_MANIFEST_UNREADABLE",
    "PROBLEM_NAME_MISMATCH",
    "PROBLEM_NO_IDENTITY",
    "PROBLEM_ORIGINS_MISSING",
    "PROBLEM_REGISTRY_KEY_MISSING",
    "PROBLEM_REGISTRY_PATH_MISMATCH",
    "PROBLEM_UNKNOWN_FAMILY",
    "PROBLEM_UNSUPPORTED_PLATFORM",
    "PipeClient",
    "PipeListener",
    "STORE_EXTENSION_IDS",
    "TRANSPORT_HTTP",
    "TRANSPORT_PIPE",
    "TRANSPORTS",
    "WINDOWS_MANIFEST_DIRECTORY",
    "WINDOWS_NATIVE_MESSAGING_REGISTRY_ROOT",
    "allowed_origins",
    "decode_native_frame",
    "diagnose_manifest",
    "encode_native_frame",
    "manifest_directory",
    "manifest_document",
    "manifest_path",
    "pipe_name",
    "preferred_instance_id",
    "preferred_window_id",
    "resolve_transport",
    "transport_override",
]
