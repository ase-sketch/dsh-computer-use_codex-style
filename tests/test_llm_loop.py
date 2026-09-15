from __future__ import annotations

import unittest

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.harness import SkyHarness, system_prompt
from computer_use.loop import run_tool_sequence
from computer_use.policy import deny_press_key
from computer_use.tools import WINDOW2_TOOLS, tool_names

WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class OfficialWindow2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeDesktop()
        self.executor = ToolExecutor(ComputerUse(self.backend))

    def test_tool_table_is_window2(self) -> None:
        names = tool_names()
        self.assertEqual(tuple(names), WINDOW2_TOOLS)
        self.assertNotIn("observe", names)
        self.assertNotIn("wait", names)
        self.assertNotIn("type", names)

    def test_canned_get_window_state_click_type_refresh(self) -> None:
        first = self.executor.execute(
            "get_window_state",
            {"window": WINDOW, "include_screenshot": True, "include_text": True},
        )
        index = first["result"]["tree"][1]["index"]
        bounds = first["result"]["tree"][1]["bounds"]
        sequence = run_tool_sequence(
            self.executor,
            [
                {"name": "get_window_state", "arguments": {"window": WINDOW, "include_text": True, "include_screenshot": True}},
                {"name": "click", "arguments": {"window": WINDOW, "element_index": index}},
                {"name": "type_text", "arguments": {"window": WINDOW, "text": "hello from llm"}},
                {"name": "get_window_state", "arguments": {"window": WINDOW, "include_text": True, "include_screenshot": True}},
            ],
        )
        names = [item["name"] for item in sequence["results"]]
        self.assertEqual(names, ["get_window_state", "click", "type_text", "get_window_state"])
        click = sequence["results"][1]
        self.assertIsNone(click["result"])
        self.assertIsNone(click.get("observation"))
        observation = sequence["observation"]
        self.assertGreater(observation["screenshot_bytes"], 0)
        self.assertIsNotNone(observation["accessibility"])
        self.assertIn("hello from llm", observation["tree"][1]["value"])

    def test_harness_initialize_and_two_cell_loop(self) -> None:
        harness = SkyHarness(self.executor)
        state = harness.initialize("notepad.exe")
        self.assertIsNone(state["accessibility"])
        self.assertTrue(state["screenshots"])
        tree_state = harness.observe(include_screenshot=False, include_text=True)
        index = tree_state["tree"][1]["index"]
        refreshed = harness.act_and_refresh("click", {"element_index": index})
        self.assertIsNone(refreshed["action"]["result"])
        self.assertIsNotNone(refreshed["state"]["accessibility"])

    def test_system_prompt_includes_official_docs(self) -> None:
        prompt = system_prompt()
        self.assertIn("Use this skill to automate the UI of Microsoft Windows apps", prompt)
        self.assertIn("two-cell", prompt)
        self.assertIn("get_window_state", prompt)
        self.assertIn("Hand-Off Required", prompt)

    def test_win_key_is_denied(self) -> None:
        with self.assertRaises(PermissionError):
            deny_press_key("Win+r")
        self.executor.execute("get_window_state", {"window": WINDOW})
        with self.assertRaises(PermissionError):
            self.executor.execute("press_key", {"window": WINDOW, "key": "Meta+a"})


if __name__ == "__main__":
    unittest.main()
