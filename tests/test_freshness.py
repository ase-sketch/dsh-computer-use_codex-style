from __future__ import annotations

import time
import unittest

from computer_use.driver import ComputerUse
from computer_use.fake_backend import FakeDesktop
from computer_use.policy import deny_allowed_apps
from computer_use.rpc import ComputerUseServer
from computer_use.runtime import make_executor
from computer_use.surfaces import tools_for_surface

WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class FreshnessTests(unittest.TestCase):
    def test_click_without_observe_is_rejected(self) -> None:
        driver = ComputerUse(FakeDesktop())
        with self.assertRaises(PermissionError) as raised:
            driver.click({"window": WINDOW, "element_index": 1})
        self.assertIn("get_window_state", str(raised.exception))

    def test_click_after_fresh_observe_ok(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW})
        result = driver.click({"window": WINDOW, "element_index": 1})
        self.assertTrue(result["ok"])

    def test_expired_observation_is_rejected(self) -> None:
        driver = ComputerUse(FakeDesktop(), ttl_ms=1)
        driver.get_window_state({"window": WINDOW})
        time.sleep(0.02)
        with self.assertRaises(PermissionError) as raised:
            driver.click({"window": WINDOW, "element_index": 1})
        self.assertIn("expired", str(raised.exception))

    def test_wrong_window_is_rejected(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW})
        with self.assertRaises(PermissionError) as raised:
            driver.click({"window": {"app": "notepad.exe", "id": 99}, "element_index": 1})
        self.assertIn("window id", str(raised.exception))

    def test_ttl_zero_disables_only_time_expiry(self) -> None:
        # TC-21: official ttl_ms=0 removes the time window, not the requirement
        # to observe first (helper-rs state.rs require_window_use still runs).
        driver = ComputerUse(FakeDesktop(), ttl_ms=0)
        with self.assertRaises(PermissionError):
            driver.click({"window": WINDOW, "element_index": 1})
        driver.get_window_state({"window": WINDOW})
        time.sleep(0.02)
        self.assertTrue(driver.click({"window": WINDOW, "element_index": 1})["ok"])

    def test_stale_screenshot_id_rejected(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW, "include_screenshot": True})
        with self.assertRaises(PermissionError) as raised:
            driver.click({"window": WINDOW, "x": 10, "y": 10, "screenshotId": "screenshot-old"})
        self.assertIn("screenshotId", str(raised.exception))


class AllowedAppsTests(unittest.TestCase):
    def test_empty_allowlist_is_unrestricted(self) -> None:
        deny_allowed_apps("notepad.exe", [])
        deny_allowed_apps("notepad.exe", None)

    def test_allowlist_blocks_other_apps(self) -> None:
        driver = ComputerUse(FakeDesktop(), allowed_apps=["chrome.exe"])
        with self.assertRaises(PermissionError) as raised:
            driver.get_window_state({"window": WINDOW})
        self.assertIn("allowedApps", str(raised.exception))

    def test_allowlist_matches_basename(self) -> None:
        driver = ComputerUse(FakeDesktop(), allowed_apps=["notepad.exe"])
        driver.get_window_state({"window": WINDOW})
        driver.click({"window": WINDOW, "element_index": 1})

    def test_launch_app_honors_allowlist(self) -> None:
        driver = ComputerUse(FakeDesktop(), allowed_apps=["notepad.exe"])
        with self.assertRaises(PermissionError):
            driver.launch_app({"app": "mspaint.exe"})


class GatedSurfaceTests(unittest.TestCase):
    def test_gated_has_window2_not_browser(self) -> None:
        names = [item["function"]["name"] for item in tools_for_surface("gated")]
        self.assertIn("get_window_state", names)
        self.assertIn("batch_actions", names)
        self.assertNotIn("tab_goto", names)

    def test_rpc_click_without_observe_errors(self) -> None:
        server = ComputerUseServer(make_executor("fake"), surface="gated", backend="fake")
        reply = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "call",
                "params": {"name": "click", "arguments": {"window": WINDOW, "element_index": 1}},
            }
        )
        self.assertIn("get_window_state", reply["error"]["message"])
        health = server.handle({"jsonrpc": "2.0", "id": 2, "method": "health"})["result"]
        # TC-21: the default is now the official "no time expiry" (0), not 15 s.
        self.assertEqual(health["ttlMs"], 0)


if __name__ == "__main__":
    unittest.main()
