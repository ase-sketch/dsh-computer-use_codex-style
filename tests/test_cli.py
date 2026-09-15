from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "computer_use", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class CliTests(unittest.TestCase):
    def test_tools_lists_window2_methods(self) -> None:
        completed = run_cli("tools")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        names = [item["function"]["name"] for item in payload["tools"]]
        self.assertEqual(
            names,
            [
                "list_windows",
                "get_window",
                "list_apps",
                "launch_app",
                "get_window_state",
                "click",
                "press_key",
                "type_text",
                "scroll",
                "scroll_element",
                "set_value",
                "drag",
                "perform_secondary_action",
                "activate_window",
            ],
        )

    def test_call_list_apps_returns_catalog_array(self) -> None:
        completed = run_cli("call", "list_apps")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        apps = payload["result"]
        self.assertIsInstance(apps, list)
        self.assertEqual(apps[0]["id"], "notepad.exe")

    def test_prompt_prints_official_skill(self) -> None:
        completed = run_cli("prompt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("# Computer Use", completed.stdout)
        self.assertIn("window2", completed.stdout)


if __name__ == "__main__":
    unittest.main()
