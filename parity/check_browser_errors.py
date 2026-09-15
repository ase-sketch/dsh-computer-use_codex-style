"""Gate: the browser failure strings match the official bundle byte-for-byte.

BR-15. Every constant in `computer_use/browser_errors.py` is checked against the
official `browser-service.mjs` (and `docs/chrome-troubleshooting.md` for the
extension communication sentence).

Usage:  python parity/check_browser_errors.py
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def official_root() -> Path | None:
    hits = sorted(glob.glob(os.path.expanduser("~/.codex/plugins/cache/openai-bundled/browser/*")))
    return Path(hits[-1]) if hits else None


def main() -> int:
    from computer_use import browser_errors as e

    exact = [
        "EXTENSION_UNAVAILABLE",
        "IAB_UNAVAILABLE",
        "CDP_UNAVAILABLE",
        "NO_HISTORY_BACK",
        "NO_HISTORY_FORWARD",
        "URL_REQUIRED",
        "URL_TAB_ID_REQUIRED",
        "CLOSE_TAB_ID_REQUIRED",
        "BACK_TAB_ID_REQUIRED",
        "EXPECTED_POSITIVE_INTEGER",
        "ELEMENT_NOT_CONNECTED",
        "FRAME_NO_BOUNDING_BOX",
        "WEBMCP_REGISTRATION_STALE",
    ]
    fragments = {
        "CLOUD_TAKEOVER_UNSUPPORTED": [
            "This ChatGPT client does not support cloud browser takeover.",
            "Do not claim the handoff succeeded.",
        ],
        "EXTENSION_UI_BLOCKING": [
            "is blocking automation because another extension UI is open on this page.",
        ],
        "EXTENSION_UPDATE_REQUIRED": [
            "Please update the ChatGPT extension in",
            "to the latest version to continue.",
        ],
    }

    root = official_root()
    if root is None:
        print("SKIP official browser package not found")
        return 0
    service = (root / "scripts" / "browser-service.mjs").read_text(encoding="utf-8", errors="replace")
    docs = ""
    trouble = root / "docs" / "chrome-troubleshooting.md"
    if trouble.is_file():
        docs = trouble.read_text(encoding="utf-8", errors="replace")

    failures: list[str] = []
    for name in exact:
        value = getattr(e, name)
        if value not in service:
            failures.append(f"{name} not found verbatim in browser-service.mjs")
        else:
            print(f"  [OK ] {name}")
    for name, parts in fragments.items():
        value = getattr(e, name)
        missing = [part for part in parts if part not in service]
        if missing:
            failures.append(f"{name} fragments missing from browser-service.mjs: {missing}")
        else:
            print(f"  [OK ] {name}")
    if e.EXTENSION_COMMUNICATION_FAILED in service or e.EXTENSION_COMMUNICATION_FAILED in docs:
        print("  [OK ] EXTENSION_COMMUNICATION_FAILED")
    else:
        failures.append("EXTENSION_COMMUNICATION_FAILED not found in the official package")

    for line in failures:
        print("FAIL " + line)
    print("browser error strings: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
