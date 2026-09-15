"""Which official guidance instructions reach the model, and how?

The previous version of this script was tautological: its haystack included
`helper-rs/assets/prompts/guidance.md`, which is byte-identical to the needle
(`analysis/official-guidance.md`), so `gaps` was ALWAYS zero and the "92/92 covered"
claim it produced was meaningless (see analysis/deep-dive/10-GAP-REGISTER.md V1).

This version separates the two delivery layers and never puts the official needle
text into the haystack:

* ALWAYS-ON  - what the model reads on every request (the DSH header).
* ON-DEMAND  - the reference documents shipped with the skill, which the model can
               read when it needs them (the official design: SKILL.md points at docs).

An instruction counts as covered when its keywords appear in EITHER layer. The layers
are reported separately, because "reachable only by reading a reference" is a weaker
guarantee than "always in context" and the difference must stay visible.

Run after changing any prompt text:  python parity/check_guidance_coverage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "helper-rs" / "assets" / "prompts"
SKILL = ROOT / "skills" / "computer-use"

#: Vocabulary only the official node_repl transport uses. Decision D1 replaces these with
#: first-class tools, so their absence is expected rather than a gap. Compared in lower
#: case -- the previous version mixed "globalThis" with a lower-cased line and so never
#: matched it.
REPLACED_BY_D1 = (
    "node_repl",
    "noderepl",
    "globalthis",
    "regularexpression",
    "regexp",
)

STOP_WORDS = frozenset(
    """
    a an the and or of to in on for with by is are be as it its this that these those
    if when then than so not no do does did done use used using call calls called
    you your yours we our ours they them their he she his her i me my
    can cannot could should would may might must will shall
    from into out up down over under about across after before during
    at by for from per via
    same other another each every any all some most more less least
    have has had having get gets got make makes made take takes taken
    state states stated only also just very still even well back
    """.split()
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def always_on() -> str:
    """The section the plugin injects into the system prompt on every request."""
    return read(ASSETS / "dsh-header.md")


def on_demand() -> str:
    """Everything the model can read from the skill bundle (references + skill body)."""
    parts = [read(SKILL / "SKILL.md")]
    for name in ("dsh-header.md", "guidance.md", "api.md", "confirmations.md"):
        parts.append(read(SKILL / "references" / name))
    return "\n".join(p for p in parts if p)


def keywords(line: str) -> list[str]:
    text = re.sub(r"^[-*\d.\s]+", "", line.strip())
    if any(marker in text.lower() for marker in REPLACED_BY_D1):
        return []
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_.\-]{2,}", text)
    out: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in STOP_WORDS or lowered in out:
            continue
        out.append(lowered)
    return out


def main() -> int:
    official_path = ROOT / "analysis" / "official-guidance.md"
    if not official_path.is_file():
        print(f"missing {official_path}", file=sys.stderr)
        return 2
    official = official_path.read_text(encoding="utf-8")
    hot = always_on().lower()
    cold = on_demand().lower()
    if official.strip() and official.strip() in hot:
        print("needle text found inside the always-on haystack: the check would be tautological",
              file=sys.stderr)
        return 2

    checked = replaced = 0
    always_covered = 0
    reference_only: list[tuple[str, list[str]]] = []
    gaps: list[tuple[str, list[str]]] = []
    for raw in official.splitlines():
        line = raw.strip()
        if len(line) < 30 or line.startswith("```") or line.startswith("|"):
            continue
        if any(marker in line.lower() for marker in REPLACED_BY_D1):
            replaced += 1
            continue
        words = keywords(line)
        if len(words) < 3:
            continue
        checked += 1
        missing_hot = [w for w in words if w not in hot]
        if not missing_hot:
            always_covered += 1
            continue
        missing_cold = [w for w in missing_hot if w not in cold]
        if missing_cold:
            gaps.append((line[:110], missing_cold))
        else:
            reference_only.append((line[:110], missing_hot))

    print(f"instructions checked          : {checked}")
    print(f"covered by always-on           : {always_covered}")
    print(f"reachable via skill references : {len(reference_only)}")
    print(f"NOT reachable anywhere         : {len(gaps)}")
    print(f"replaced by D1 (node_repl)     : {replaced}")
    print(f"always-on chars                : {len(hot)}")
    if reference_only and "-v" in sys.argv:
        print("--- only in references (informational) ---")
        for line, absent in reference_only:
            print(f"  - {line}")
    if gaps:
        print("--- instructions missing from every layer ---")
        for line, absent in gaps:
            print(f"  - {line}")
            print(f"      missing: {', '.join(absent[:8])}")
    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
