from __future__ import annotations

import struct
import unittest

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.helper_pipe import decode_pipe_frame, encode_pipe_frame
from computer_use.surfaces import tools_for_surface


class CdpDownloadChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = ToolExecutor(ComputerUse(FakeDesktop()))
        self.tab = self.ex.execute("tab_new", {"url": "https://example.com/"})["result"]
        self.tid = self.tab["id"]

    def test_cdp_send_read_events_and_browser_id(self) -> None:
        names = {item["function"]["name"] for item in tools_for_surface("all")}
        for required in (
            "tab_cdp_send",
            "tab_cdp_read_events",
            "tab_pw_download_suggested_filename",
            "tab_pw_download_url",
            "tab_pw_download_cancel",
            "tab_pw_download_failure",
            "browser_id",
        ):
            self.assertIn(required, names)
        sent = self.ex.execute("tab_cdp_send", {"tab_id": self.tid, "method": "Runtime.enable", "params": {}})["result"]
        self.assertEqual(sent["result"]["method"], "Runtime.enable")
        events = self.ex.execute("tab_cdp_read_events", {"tab_id": self.tid, "afterSequence": 0})["result"]["events"]
        self.assertGreaterEqual(len(events), 1)
        ident = self.ex.execute("browser_id", {})["result"]
        self.assertEqual(ident["browserId"], "iab")

    def test_download_object_and_locator_chain(self) -> None:
        self.ex.execute("tab_dom_download_media", {"tab_id": self.tid, "node_id": 2})
        name = self.ex.execute("tab_pw_download_suggested_filename", {"tab_id": self.tid})["result"]
        self.assertTrue(name["suggestedFilename"])
        url = self.ex.execute("tab_pw_download_url", {"tab_id": self.tid})["result"]
        self.assertIn("example.com", url["url"])
        self.assertIsNone(self.ex.execute("tab_pw_download_failure", {"tab_id": self.tid})["result"]["failure"])
        cancelled = self.ex.execute("tab_pw_download_cancel", {"tab_id": self.tid})["result"]
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(self.ex.execute("tab_pw_download_failure", {"tab_id": self.tid})["result"]["failure"], "cancelled")
        role = self.ex.execute("tab_pw_get_by_role", {"tab_id": self.tid, "role": "link"})["result"]
        chained = self.ex.execute("tab_pw_get_by_text", {"locator_id": role["locator_id"], "text": "More"})["result"]
        self.assertEqual(len(chained["chain"]), 2)
        self.assertEqual(chained["chain"][0]["kind"], "role")
        self.assertEqual(chained["chain"][1]["kind"], "text")
        logs = self.ex.execute("tab_dev_logs", {"tab_id": self.tid, "url": "example.com"})["result"]["logs"]
        self.assertTrue(logs)
        docs = self.ex.execute("documentation_get", {"name": "accessibility"})["result"]
        self.assertTrue(docs["found"])

    def test_named_pipe_frames(self) -> None:
        frame = encode_pipe_frame(7, "list_apps", {}, {"session_id": "s"})
        self.assertGreaterEqual(len(frame), 8)
        (length,) = struct.unpack_from("<I", frame, 0)
        self.assertEqual(length, len(frame) - 4)
        message, rest = decode_pipe_frame(frame)
        self.assertEqual(rest, b"")
        self.assertEqual(message["jsonrpc"], "2.0")
        self.assertEqual(message["params"]["method"], "list_apps")
        self.assertEqual(message["id"], 7)


if __name__ == "__main__":
    unittest.main()
