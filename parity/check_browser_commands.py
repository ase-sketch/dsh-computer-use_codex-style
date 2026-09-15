"""Gate: the DSH browser catalog matches the official 94 agent commands.

Read-only. Extracted from `scripts/browser-service.mjs` (`commandType:()=>IDENT`
with the IDENT string resolved). Also checks the two response-meta sets (`JJ`
mutating 28 / `YJ` read-only 15) and that every defined payload schema belongs to
a registered command (BR-01 / BR-02 / BR-21).

Usage:  python parity/check_browser_commands.py
"""

from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OFFICIAL_GLOBS = [
    os.path.expanduser("~/.codex/plugins/cache/openai-bundled/browser/*/scripts/browser-service.mjs"),
]


def official_service_path() -> Path | None:
    for pattern in OFFICIAL_GLOBS:
        hits = sorted(glob.glob(pattern))
        if hits:
            return Path(hits[-1])
    return None


def official_commands(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    idents = set(re.findall(r"commandType:\(\)=>([A-Za-z0-9_$]+)", text))
    names: set[str] = set()
    for ident in idents:
        match = re.search(
            r"(?<![A-Za-z0-9_$])" + re.escape(ident) + r"\s*[=:]\s*\"([a-z0-9_]+)\"",
            text,
        )
        if match:
            names.add(match.group(1))
    return names


def main() -> int:
    from computer_use.browser_meta import MUTATING_COMMANDS, READ_ONLY_COMMANDS
    from computer_use.browser_official import AX_ACTION_MEMBERS, OFFICIAL_COMMANDS
    from computer_use.browser_schemas import COMMAND_SCHEMAS

    failures: list[str] = []
    path = official_service_path()
    if path is None:
        print("SKIP official browser-service.mjs not found")
    else:
        official = official_commands(path)
        ours = set(OFFICIAL_COMMANDS) - {"browser_setup"}
        print(f"official commands: {len(official)}   dsh: {len(ours)} (excluding browser_setup)")
        missing = sorted(official - ours)
        extra = sorted(ours - official)
        print(f"missing: {missing}")
        print(f"extra:   {extra}")
        if len(official) != 94:
            failures.append(f"official command count is {len(official)}, expected 94")
        if missing:
            failures.append(f"missing official commands: {missing}")
        if extra:
            failures.append(f"unexpected DSH commands: {extra}")

    dead = sorted(set(COMMAND_SCHEMAS) - {"browser_setup"} - set(OFFICIAL_COMMANDS))
    print(f"schemas: {len(COMMAND_SCHEMAS)}   dead schemas: {dead}")
    if dead:
        failures.append(f"schemas without a registered command: {dead}")

    print(
        "mutating set: " + str(len(MUTATING_COMMANDS)) + "   read-only set: " + str(len(READ_ONLY_COMMANDS))
    )
    if len(MUTATING_COMMANDS) != 28:
        failures.append(f"JJ mutating set has {len(MUTATING_COMMANDS)} members, expected 28")
    if len(READ_ONLY_COMMANDS) != 15:
        failures.append(f"YJ read-only set has {len(READ_ONLY_COMMANDS)} members, expected 15")

    print(f"tab_ax_action members: {len(AX_ACTION_MEMBERS)}")
    if len(AX_ACTION_MEMBERS) != 8:
        failures.append("tab_ax_action union must have 8 members")
    if "navigate_tab_url" not in OFFICIAL_COMMANDS:
        failures.append("navigate_tab_url is not registered")

    for line in failures:
        print("FAIL " + line)
    print("browser command catalog: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
