from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from computer_use.cdp_ws import CdpConn


class FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.inbox: list[str] = []

    def send(self, data: str) -> None:
        self.sent.append(data)
        msg = json.loads(data)
        self.inbox.append(json.dumps({"id": msg["id"], "result": {"ok": True, "method": msg["method"]}}))

    def recv(self) -> str:
        if self.inbox:
            return self.inbox.pop(0)
        return json.dumps({"method": "Page.frameStartedLoading", "params": {}})

    def settimeout(self, _timeout: float) -> None:
        return None

    def close(self) -> None:
        return None


class CdpWsTests(unittest.TestCase):
    def test_call_matches_id_and_skips_events(self) -> None:
        fake = FakeWs()
        with patch("computer_use.cdp_ws.websocket.create_connection", return_value=fake):
            conn = CdpConn("ws://127.0.0.1:9334/devtools/page/x")
            result = conn.call("Page.enable")
        self.assertEqual(result["ok"], True)
        self.assertEqual(json.loads(fake.sent[0])["method"], "Page.enable")
        conn.close()

    def test_javascript_dialog_event_is_buffered(self) -> None:
        fake = FakeWs()

        def send(data: str) -> None:
            fake.sent.append(data)
            msg = json.loads(data)
            fake.inbox.append(
                json.dumps({"method": "Page.javascriptDialogOpening", "params": {"type": "alert", "message": "hi"}})
            )
            fake.inbox.append(json.dumps({"id": msg["id"], "result": {}}))

        fake.send = send  # type: ignore[method-assign]
        with patch("computer_use.cdp_ws.websocket.create_connection", return_value=fake):
            conn = CdpConn("ws://127.0.0.1:9334/devtools/page/x")
            conn.call("Page.enable")
            dialog = conn.last_event("Page.javascriptDialogOpening")
        self.assertEqual(dialog["message"], "hi")
        popped = conn.pop_event("Page.javascriptDialogOpening")
        self.assertEqual(popped["message"], "hi")
        self.assertIsNone(conn.last_event("Page.javascriptDialogOpening"))


if __name__ == "__main__":
    unittest.main()
