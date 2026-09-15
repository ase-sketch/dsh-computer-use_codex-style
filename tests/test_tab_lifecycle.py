from __future__ import annotations

import unittest

from computer_use.browser_lifecycle import TabLifecycle
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop


class TabLifecycleUnitTests(unittest.TestCase):
    def test_unmarked_created_tabs_close_and_claimed_ones_release(self) -> None:
        life = TabLifecycle()
        life.record_created("tab-a")
        life.record_created("tab-b")
        life.record_acquired("user-1")
        life.record_acquired("user-2")
        life.record_marked("tab-b")
        life.record_marked("user-2")
        outcome = life.end_turn()
        self.assertEqual(outcome["closed"], ["tab-a"])
        self.assertEqual(outcome["released"], ["user-1"])

    def test_needs_reclaim_until_acquired(self) -> None:
        life = TabLifecycle()
        self.assertTrue(life.needs_reclaim("7"))
        life.record_acquired("7")
        self.assertFalse(life.needs_reclaim("7"))
        self.assertFalse(life.needs_reclaim(""))


class TabReaperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = ToolExecutor(ComputerUse(FakeDesktop()))
        self.surface = self.ex.browser

    def test_end_turn_closes_only_unmarked_created_tabs(self) -> None:
        a = self.surface.dispatch("tab_new", {"url": "https://example.com/a"})
        b = self.surface.dispatch("tab_new", {"url": "https://example.com/b"})
        kept = self.surface.dispatch("tab_new", {"url": "https://example.com/c"})
        self.surface.dispatch("mark_tab", {"tab_id": kept["id"], "status": "deliverable"})
        outcome = self.surface.end_turn()
        self.assertIn(a["id"], outcome["closed"])
        self.assertIn(b["id"], outcome["closed"])
        self.assertNotIn(kept["id"], outcome["closed"])
        remaining = [tab["id"] for tab in self.surface.browser.tabs_list()]
        self.assertEqual(remaining, [kept["id"]])

    def test_turn_end_command_is_routable(self) -> None:
        self.surface.dispatch("tab_new", {"url": "https://example.com/a"})
        outcome = self.surface.dispatch("browser_turn_end", {})
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["closed"], ["tab-1"])


if __name__ == "__main__":
    unittest.main()
