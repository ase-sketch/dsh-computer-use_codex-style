from __future__ import annotations

import unittest

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.surfaces import tools_for_surface


class RemainingEdgeToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = ToolExecutor(ComputerUse(FakeDesktop()))
        self.tab = self.ex.execute("tab_new", {"url": "https://example.com/"})["result"]
        self.tid = self.tab["id"]

    def test_secondary_first_last_capabilities_nested_evaluate(self) -> None:
        names = {item["function"]["name"] for item in tools_for_surface("all")}
        for required in (
            "tab_ax_perform_secondary_action",
            "tab_pw_first",
            "tab_pw_last",
            "tab_pw_locator_evaluate",
            "browser_capabilities_get",
            "tab_capabilities_get",
        ):
            self.assertIn(required, names)
        secondary = self.ex.execute(
            "tab_ax_perform_secondary_action",
            {"tab_id": self.tid, "element_index": 2, "action": "Expand"},
        )["result"]
        self.assertEqual(secondary["action"], "Expand")
        loc = self.ex.execute("tab_pw_locator", {"tab_id": self.tid, "selector": "a"})["result"]
        first = self.ex.execute("tab_pw_first", {"locator_id": loc["locator_id"]})["result"]
        self.assertEqual(first["nth"], 0)
        last = self.ex.execute("tab_pw_last", {"locator_id": loc["locator_id"]})["result"]
        self.assertEqual(last["nth"], -1)
        nested = self.ex.execute(
            "tab_pw_get_by_role",
            {"locator_id": loc["locator_id"], "role": "link", "name": "More"},
        )["result"]
        self.assertEqual(nested["parent"], loc["locator_id"])
        evaluated = self.ex.execute(
            "tab_pw_locator_evaluate",
            {"locator_id": loc["locator_id"], "expression": "el => el.tagName"},
        )["result"]
        self.assertIsNotNone(evaluated["value"])
        vis = self.ex.execute("browser_capabilities_get", {"id": "visibility"})["result"]
        self.assertTrue(vis["found"])
        self.assertIn("get", vis["methods"])
        webmcp = self.ex.execute("tab_capabilities_get", {"tab_id": self.tid, "id": "webmcp"})["result"]
        self.assertTrue(webmcp["found"])
        logs_schema = next(item for item in tools_for_surface("all") if item["function"]["name"] == "tab_dev_logs")
        self.assertIn("levels", logs_schema["function"]["parameters"]["properties"])
        docs = self.ex.execute("documentation_get", {"name": "recovered-helper"})["result"]
        self.assertTrue(docs["found"])


if __name__ == "__main__":
    unittest.main()
