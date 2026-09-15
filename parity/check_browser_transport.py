"""Gate: BR-19 extension transport identity + framing match the official package.

Every identity constant is re-read from the packaged bundle
(scripts/extension-ids.json, scripts/check-native-host-manifest.js,
scripts/browser-service.mjs) and compared with computer_use/extension_transport.py.
The native-messaging frame codec and the manifest diagnostics are then exercised.

The gate deliberately asserts the *documented gap* too: the module must state
that the official payload envelope is not in the package. Flipping the shipped
default without that note fails here.

Usage:  python parity/check_browser_transport.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: official fa(): win32 "\\\\\\.\\pipe\\codex-browser-use" else "/tmp/codex-browser-use".
PIPE_RE = re.compile(r'win32"\?"(\\+\.\\+pipe\\+codex-browser-use)"')

#: static prefixes of the official diagnostic templates, by source file.
MANIFEST_SCRIPT_PREFIXES = (
    "Windows native host registry key does not exist: ",
    "Native host manifest does not exist: ",
    "manifest name does not match ",
    "allowed_origins does not include ",
    "registry manifest path does not match checked manifest path",
    "Native host diagnostics are unavailable until a runtime identity is configured.",
    "Unsupported platform for native host manifest check: ",
)
DIAGNOSTICS_SCRIPT_PREFIXES = (
    "No generated diagnostics are available for browser family ",
)


def official_root() -> Path | None:
    hits = sorted(glob.glob(os.path.expanduser("~/.codex/plugins/cache/openai-bundled/browser/*")))
    return Path(hits[-1]) if hits else None


def decode_js_string(raw: str) -> str:
    return re.sub(r"\\(.)", r"\1", raw)


def main() -> int:
    from computer_use import extension_transport as t
    from computer_use.extension_hub import ExtensionHub

    failures: list[str] = []
    root = official_root()
    if root is None:
        print("SKIP official browser package not found")
        return 0
    service = (root / "scripts" / "browser-service.mjs").read_text(
        encoding="utf-8", errors="replace"
    )
    manifest_script = (root / "scripts" / "check-native-host-manifest.js").read_text(
        encoding="utf-8", errors="replace"
    )
    diagnostics_script = (root / "scripts" / "chromium-browser-diagnostics.mjs").read_text(
        encoding="utf-8", errors="replace"
    )
    ids = json.loads((root / "scripts" / "extension-ids.json").read_text(encoding="utf-8"))

    # --- pipe name ---------------------------------------------------------
    match = PIPE_RE.search(service)
    official_win = decode_js_string(match.group(1)) if match else None
    win_ok = official_win == t.PIPE_NAME_WIN32
    print(f"  [{'OK ' if win_ok else 'FAIL'}] pipe win32: {official_win!r}")
    if not win_ok:
        failures.append(f"PIPE_NAME_WIN32 is {t.PIPE_NAME_WIN32!r}, official {official_win!r}")
    posix_ok = "/tmp/codex-browser-use" in service and t.PIPE_NAME_POSIX == "/tmp/codex-browser-use"
    print(f"  [{'OK ' if posix_ok else 'FAIL'}] pipe posix: {t.PIPE_NAME_POSIX!r}")
    if not posix_ok:
        failures.append("PIPE_NAME_POSIX does not match the official /tmp path")

    # --- identity ----------------------------------------------------------
    identity = [
        ("EXTENSION_HOST_NAME", t.EXTENSION_HOST_NAME, ids.get("extensionHostName")),
        ("WINDOWS_MANIFEST_DIRECTORY", t.WINDOWS_MANIFEST_DIRECTORY,
         (ids.get("windowsNativeMessaging") or {}).get("manifestDirectory")),
        ("WINDOWS_NATIVE_MESSAGING_REGISTRY_ROOT", t.WINDOWS_NATIVE_MESSAGING_REGISTRY_ROOT,
         (ids.get("windowsNativeMessaging") or {}).get("registryRoot")),
        ("EXTENSION_IDS", list(t.EXTENSION_IDS), ids.get("extensionIds")),
    ]
    for name, ours, official in identity:
        marker = "OK " if ours == official else "FAIL"
        print(f"  [{marker}] {name} = {ours!r}")
        if ours != official:
            failures.append(f"{name} is {ours!r}, official {official!r}")
    for family, entry in [(item.get("browserFamily"), item.get("storeExtensionId"))
                          for item in ids.get("browserExtensions", [])]:
        ours = t.STORE_EXTENSION_IDS.get(str(family))
        if ours != entry:
            failures.append(f"STORE_EXTENSION_IDS[{family!r}] is {ours!r}, official {entry!r}")
    print(f"  [OK ] STORE_EXTENSION_IDS covers {len(t.STORE_EXTENSION_IDS)} families")

    # --- diagnostics -------------------------------------------------------
    missing = [prefix for prefix in MANIFEST_SCRIPT_PREFIXES if prefix not in manifest_script]
    missing += [prefix for prefix in DIAGNOSTICS_SCRIPT_PREFIXES if prefix not in diagnostics_script]
    print(f"  [{'OK ' if not missing else 'FAIL'}] official diagnostic sentences extracted")
    for prefix in missing:
        failures.append(f"official diagnostic prefix missing from the package: {prefix!r}")
    ours_map = {
        "Windows native host registry key does not exist: ": t.PROBLEM_REGISTRY_KEY_MISSING,
        "Native host manifest does not exist: ": t.PROBLEM_MANIFEST_MISSING,
        "manifest name does not match ": t.PROBLEM_NAME_MISMATCH,
        "allowed_origins does not include ": t.PROBLEM_ORIGINS_MISSING,
        "registry manifest path does not match checked manifest path": t.PROBLEM_REGISTRY_PATH_MISMATCH,
        "Native host diagnostics are unavailable until a runtime identity is configured.": t.PROBLEM_NO_IDENTITY,
        "Unsupported platform for native host manifest check: ": t.PROBLEM_UNSUPPORTED_PLATFORM,
        "No generated diagnostics are available for browser family ": t.PROBLEM_UNKNOWN_FAMILY,
    }
    for prefix, ours in ours_map.items():
        if not ours.startswith(prefix):
            failures.append(f"our diagnostic text does not start with {prefix!r}: {ours!r}")
    print("  [OK ] our diagnostic templates start with the official prefixes")

    # --- framing -----------------------------------------------------------
    frame = t.encode_native_frame({"a": 1})
    framing_ok = frame == b'\x07\x00\x00\x00{"a":1}'
    print(f"  [{'OK ' if framing_ok else 'FAIL'}] native frame = 4-byte LE length + JSON")
    if not framing_ok:
        failures.append(f"frame header is {frame[:8]!r}")
    message, rest = t.decode_native_frame(frame + b"tail")
    if message != {"a": 1} or rest != b"tail":
        failures.append("decode_native_frame did not round-trip")
    else:
        print("  [OK ] decode_native_frame round-trips and preserves the tail")
    oversized = b"\xff\xff\xff\xff" + b"x" * 16
    try:
        t.decode_native_frame(oversized)
    except ValueError:
        print("  [OK ] frames over the 1 MiB host limit are rejected")
    else:
        failures.append("decode_native_frame accepted a frame over the 1 MiB limit")

    # --- manifest ----------------------------------------------------------
    document = t.manifest_document("C:/host/host.exe")
    origins_ok = document["allowed_origins"] == [f"chrome-extension://{i}/" for i in t.EXTENSION_IDS]
    print(f"  [{'OK ' if origins_ok and document['type'] == 'stdio' else 'FAIL'}] "
          f"manifest type=stdio origins={len(document['allowed_origins'])}")
    if not origins_ok or document["type"] != "stdio":
        failures.append("manifest_document does not match the official shape")
    with tempfile.TemporaryDirectory() as tmp:
        location = t.manifest_path(home=tmp, platform="win32")
        missing_report = t.diagnose_manifest(None, home=tmp, platform="win32")
        if not str(missing_report.get("problem", "")).startswith("Native host manifest does not exist: "):
            failures.append("diagnose_manifest(missing) does not emit the official sentence")
        else:
            print("  [OK ] missing manifest emits the official sentence")
        wrong = t.diagnose_manifest(
            {"name": "org.example.other", "allowed_origins": []},
            home=tmp,
            platform="win32",
        )
        problem = str(wrong.get("problem") or "")
        if "manifest name does not match" not in problem or "allowed_origins does not include" not in problem:
            failures.append(f"diagnose_manifest(mismatch) problem is {problem!r}")
        else:
            print("  [OK ] manifest mismatch emits name + origins problems")
        correct = t.diagnose_manifest(
            {"name": t.EXTENSION_HOST_NAME, "allowed_origins": t.allowed_origins()},
            home=tmp,
            platform="win32",
        )
        if not correct.get("correct"):
            failures.append(f"a correct manifest was rejected: {correct}")
        else:
            print("  [OK ] a correct manifest is accepted")

    # --- transport selection ----------------------------------------------
    selection_ok = (t.resolve_transport("pipe") == t.TRANSPORT_PIPE
                    and t.resolve_transport("http") == t.TRANSPORT_HTTP
                    and t.resolve_transport("nonsense") == t.DEFAULT_TRANSPORT)
    print(f"  [{'OK ' if selection_ok else 'FAIL'}] transport is configurable (pipe/http)")
    if not selection_ok:
        failures.append("resolve_transport does not honour COMPUTER_USE_EXTENSION_TRANSPORT")
    if ExtensionHub().transport != t.resolve_transport():
        failures.append("ExtensionHub does not follow the selected transport")
    else:
        print(f"  [OK ] ExtensionHub default transport = {ExtensionHub().transport!r}")
    if not (hasattr(t, "PipeListener") and hasattr(t, "PipeClient")):
        failures.append("the official-family pipe transport is not implemented")
    else:
        print("  [OK ] PipeListener + PipeClient exist for the official family")

    # --- documented gap ----------------------------------------------------
    doc = t.__doc__ or ""
    gap_ok = "not in the package" in doc and "payload" in doc.lower()
    print(f"  [{'OK ' if gap_ok else 'FAIL'}] the unknown official payload envelope is documented")
    if not gap_ok:
        failures.append("extension_transport does not document the missing official payload envelope")

    for line in failures:
        print("FAIL " + line)
    print("browser transport: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
