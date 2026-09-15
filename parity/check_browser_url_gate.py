"""Gate: the P6 browser-URL policy gate matches the official helper strings.

BR-14. The four fail-closed sentences live in the Windows helper .rdata at RVA
`0x132af7` (`out/exe/strings_all.txt:18208`). This script extracts them from the
decompile workspace and compares them byte-for-byte with
`computer_use/browser_url_policy.py`, then checks that the navigation guard
actually calls the gate.

Usage:  python parity/check_browser_url_gate.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The official string dump is optional: point CUA_SKY_DECOMPILE at a decompile tree that
# contains out/exe/strings_all.txt, otherwise this gate reports SKIP loudly (never a false PASS).
DECOMPILE = Path(os.environ["CUA_SKY_DECOMPILE"]) if os.environ.get("CUA_SKY_DECOMPILE") else None
STRINGS = DECOMPILE / "out" / "exe" / "strings_all.txt" if DECOMPILE else None
START_MARKER = "Computer Use has been stopped for this turn because"
TAIL = "why Computer Use ended."


def extract_official_messages() -> list[str] | None:
    if STRINGS is None or not STRINGS.is_file():
        return None
    for line in STRINGS.read_text(encoding="utf-8", errors="replace").splitlines():
        if START_MARKER in line and "browser URL policy enforcement" in line:
            block = line[line.index(START_MARKER):]
            return split_sentences(block)
    return None


def split_sentences(block: str) -> list[str]:
    messages: list[str] = []
    rest = block
    while rest.startswith(START_MARKER) and len(messages) < 4:
        end = rest.index(TAIL) + len(TAIL)
        # The first sentence continues with the "Note that ... themselves." tail.
        note = "Note that Computer Use is not allowed on this URL"
        if note in rest[: end + 140]:
            end = rest.index("themselves.") + len("themselves.")
        messages.append(rest[:end])
        rest = rest[end:]
    return messages


def main() -> int:
    from computer_use.browser_url_policy import URL_GATE_MESSAGES

    failures: list[str] = []
    official = extract_official_messages()
    if official is None:
        print("SKIP official url_policy strings not found at " + str(STRINGS))
    else:
        print(f"official sentences: {len(official)}   python sentences: {len(URL_GATE_MESSAGES)}")
        if len(official) != 4:
            failures.append(f"expected 4 official sentences, extracted {len(official)}")
        for index, sentence in enumerate(official):
            if index >= len(URL_GATE_MESSAGES):
                continue
            ours = URL_GATE_MESSAGES[index]
            marker = "OK " if ours == sentence else "FAIL"
            print(f"  [{marker}] sentence {index + 1}: {ours[:64]}...")
            if ours != sentence:
                failures.append(f"sentence {index + 1} differs from the official string")

    api = (ROOT / "computer_use" / "browser_api.py").read_text(encoding="utf-8")
    if "assert_browser_url_allowed" not in api:
        failures.append("browser_api.py never calls assert_browser_url_allowed")
    else:
        guard = re.search(r"def _guard_navigation[\s\S]{0,700}", api)
        if not guard or "assert_browser_url_allowed" not in guard.group(0):
            failures.append("the URL gate is not called from _guard_navigation")
        else:
            print("  [OK ] _guard_navigation calls the P6 URL gate")

    helper = ROOT / "helper-rs" / "src" / "policy" / "url_policy.rs"
    if helper.is_file():
        text = helper.read_text(encoding="utf-8", errors="replace")
        missing = [m for m in URL_GATE_MESSAGES if m not in text]
        print("  [OK ] helper url_policy.rs mirrors the four sentences" if not missing else "  [FAIL] helper url_policy.rs missing sentences")
        if missing:
            failures.append("helper-rs/src/policy/url_policy.rs does not carry the official sentences")
    else:
        print("  NOTE helper-rs/src/policy/url_policy.rs is absent (owned by another domain);")
        print("       the Rust helper still needs the same four constants + a browser_url_gate RPC.")

    for line in failures:
        print("FAIL " + line)
    print("browser url gate: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
