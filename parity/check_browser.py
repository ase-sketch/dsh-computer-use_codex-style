"""Browser surface static gate (legacy name, extended in the 2026 deep dive).

Checks the catalog, the dispatch surface, the security-layer call sites and the
response-meta sets. Read-only; no desktop interaction. Exits 1 on any failure.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from computer_use.browser_meta import MUTATING_COMMANDS, READ_ONLY_COMMANDS  # noqa: E402
from computer_use.browser_official import (  # noqa: E402
    AX_ACTION_MEMBERS,
    OFFICIAL_COMMANDS,
    official_tool_definitions,
)
from computer_use.browser_schemas import COMMAND_SCHEMAS  # noqa: E402


def _flat(tool: dict) -> dict:
    function = tool.get("function")
    return function if isinstance(function, dict) else tool


def main() -> int:
    failures: list[str] = []
    ts = official_tool_definitions()
    d = {_flat(tool)["name"]: _flat(tool) for tool in ts}
    print("tool count:", len(ts))
    print("schemas defined:", len(COMMAND_SCHEMAS))
    print("navigate_tab_url present:", "navigate_tab_url" in d)
    if "navigate_tab_url" not in d:
        failures.append("navigate_tab_url is not advertised")
    print("create_tab props:", sorted(d["create_tab"]["parameters"]["properties"]))
    print("create_tab required:", d["create_tab"]["parameters"].get("required"))
    print("tab_ax_action required:", d["tab_ax_action"]["parameters"].get("required"))
    print("tab_ax_get_state props:", sorted(d["tab_ax_get_state"]["parameters"]["properties"]))
    print("mark_tab status enum:", d["mark_tab"]["parameters"]["properties"]["status"].get("enum"))
    print("pw_locator_click required:", d["playwright_locator_click"]["parameters"].get("required"))
    print("all flat:", all("name" in _flat(t) and "parameters" in _flat(t) for t in ts))

    dead = sorted(set(COMMAND_SCHEMAS) - {"browser_setup"} - set(OFFICIAL_COMMANDS))
    print("dead schemas:", dead)
    if dead:
        failures.append(f"schemas without a command: {dead}")
    print(f"JJ/YJ sets: {len(MUTATING_COMMANDS)}/{len(READ_ONLY_COMMANDS)}")
    if (len(MUTATING_COMMANDS), len(READ_ONLY_COMMANDS)) != (28, 15):
        failures.append("response-meta sets drifted from 28/15")
    print("tab_ax_action members:", len(AX_ACTION_MEMBERS))

    consent_calls = 0
    for path in (ROOT / "computer_use").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"consent_for", "remember_origin"}:
                    consent_calls += 1
    print("consent call sites:", consent_calls)
    if consent_calls == 0:
        failures.append("the consent layer has no call sites")

    for line in failures:
        print("FAIL " + line)
    print("browser gate: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
