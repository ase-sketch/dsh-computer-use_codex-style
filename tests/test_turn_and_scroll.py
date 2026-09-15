from __future__ import annotations

import json
import unittest

from computer_use.driver import ComputerUse
from computer_use.errors import TurnInterrupted
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.helper_protocol import (
    TURN_ENDED_MESSAGE,
    TURN_METADATA_KEY,
    encode_request,
    scroll_method,
    scroll_params,
    turn_metadata,
)
from computer_use.cdp_http import list_tabs
from computer_use.cdp_ax import flatten_cdp_ax


WINDOW = {"app": "notepad.exe", "id": 1}


class TurnAndScrollTests(unittest.TestCase):
    def test_scroll_element_mapping(self) -> None:
        self.assertEqual(scroll_method({"element_index": 3}), "scroll_element")
        method, params = scroll_params({"app": "a", "id": 1}, {"element_index": 3, "direction": "up", "pages": 2})
        self.assertEqual(method, "scroll_element")
        self.assertEqual(params["pages"], 2)
        self.assertEqual(scroll_method({"x": 1, "y": 1}), "scroll")

    def test_turn_metadata_and_end_turn(self) -> None:
        meta = turn_metadata("sess-1", "turn-9")
        self.assertEqual(meta[TURN_METADATA_KEY]["sessionId"], "sess-1")
        line = encode_request(1, "list_apps", {}, extra_meta=meta)
        self.assertIn("x-codex-turn-metadata", line)
        self.assertIn("sess-1", line)
        executor = ToolExecutor(ComputerUse(FakeDesktop()))
        ended = executor.execute("end_turn", {"session_id": "sess-1", "turn_id": "turn-9"})["result"]
        self.assertTrue(ended["ended"])
        self.assertIn("TurnEnded", ended["event"])
        with self.assertRaises(TurnInterrupted) as raised:
            executor.execute("click", {"window": WINDOW, "element_index": 1})
        self.assertEqual(str(raised.exception), TURN_ENDED_MESSAGE)

    def test_cdp_http_returns_list(self) -> None:
        tabs = list_tabs(port=9, timeout=0.2)
        self.assertEqual(tabs, [])
        flat = flatten_cdp_ax({"nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "t"}, "childIds": []}]})
        self.assertEqual(flat[0]["role"], "RootWebArea")


if __name__ == "__main__":
    unittest.main()
