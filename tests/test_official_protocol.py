from __future__ import annotations

import unittest

from computer_use.helper_protocol import APPROVED_APP_META_KEY
from computer_use.rpc import ComputerUseServer
from computer_use.runtime import make_executor

WINDOW = {"app": "notepad.exe", "id": 1}


class OfficialTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ComputerUseServer(make_executor("fake"), surface="gated", backend="fake")

    def test_official_json_line_ok_result(self) -> None:
        reply = self.server.handle({"id": 1, "method": "list_windows", "params": {}, "meta": {"x-oai-cua-request-budget-ms": 10000}})
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["id"], 1)
        payload = reply["result"]
        windows = payload["value"] if isinstance(payload, dict) else payload
        self.assertEqual(windows[0]["id"], 1)

    def test_launch_app_returns_approval_request(self) -> None:
        live = ComputerUseServer(make_executor("fake"), surface="gated", backend="windows")
        reply = live.handle({"id": 2, "method": "launch_app", "params": {"app": "mspaint.exe"}, "meta": {}})
        self.assertFalse(reply["ok"])
        self.assertIn("approvalRequest", reply)
        self.assertEqual(reply["approvalRequest"]["app"], "mspaint.exe")
        self.assertIn("displayName", reply["approvalRequest"])

    def test_click_requires_approval_then_retry(self) -> None:
        live = ComputerUseServer(make_executor("fake"), surface="gated", backend="windows")
        denied = live.handle({"id": 4, "method": "click", "params": {"window": WINDOW, "element_index": 1}, "meta": {}})
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["approvalRequest"]["app"], "notepad.exe")
        live.handle(
            {
                "id": 4,
                "method": "get_window_state",
                "params": {"window": WINDOW},
                "meta": {APPROVED_APP_META_KEY: "notepad.exe"},
            }
        )
        reply = live.handle(
            {
                "id": 5,
                "method": "click",
                "params": {"window": WINDOW, "element_index": 1},
                "meta": {APPROVED_APP_META_KEY: "notepad.exe"},
            }
        )
        self.assertTrue(reply["ok"], reply)

    def test_interrupt_marker_file_stops_turn(self) -> None:
        import os
        import tempfile

        from computer_use.interrupt import interrupt_path

        home = tempfile.mkdtemp()
        marker = interrupt_path(home, "conv-1", "turn-1")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"")
        os.environ["DSH_HOME"] = home
        reply = self.server.handle(
            {
                "id": 6,
                "method": "list_windows",
                "params": {},
                "meta": {"conversationId": "conv-1", "turnId": "turn-1"},
            }
        )
        self.assertFalse(reply["ok"])
        self.assertIn("Escape", str(reply.get("error") or ""))

    def test_diagnostic_state_and_window_rpc(self) -> None:
        diag = self.server.handle({"id": 7, "method": "diagnostic_state", "params": {}})
        self.assertTrue(diag.get("ok") or "backend" in (diag.get("result") or diag))
        win = self.server.handle({"id": 8, "method": "window", "params": {"id": 1, "app": "notepad.exe"}})
        self.assertTrue(win.get("ok") or win.get("jsonrpc") == "2.0")


if __name__ == "__main__":
    unittest.main()
