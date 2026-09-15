from __future__ import annotations

import unittest

from computer_use.detect import detect_backends
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.extension_hub import ExtensionHub
from computer_use.fake_backend import FakeDesktop
from computer_use.policy import deny_url


class ExtensionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = ToolExecutor(ComputerUse(FakeDesktop()))

    def test_detect_iab_extension_cloud(self) -> None:
        detected = self.executor.execute("browser_detect", {})["result"]
        self.assertTrue(detected["iab"]["available"])
        self.assertEqual(detected["iab"]["metadata"]["codexSessionId"], "sess-iab")
        self.assertFalse(detected["iab"]["visibilityDefault"])
        self.assertTrue(detected["cloud"]["available"])
        self.assertIn("extension", detected)

    def test_hub_login_state_claim(self) -> None:
        hub = ExtensionHub()
        self.executor.browser.hub = hub
        hub.ingest(
            {
                "type": "hello",
                "instanceId": "inst-1",
                "family": "chrome",
                "tabs": [
                    {
                        "providerTabId": "42",
                        "title": "Gmail",
                        "url": "https://mail.google.com/",
                        "backend": "extension",
                    }
                ],
            }
        )
        opened = self.executor.execute("browser_open_tabs", {})["result"]
        self.assertTrue(opened["loginState"])
        self.assertEqual(opened["tabs"][0]["title"], "Gmail")
        claimed = self.executor.execute(
            "browser_claim_tab",
            {"providerTabId": "42", "title": "Gmail", "url": "https://mail.google.com/"},
        )["result"]
        self.assertTrue(claimed["claimed"])
        self.assertTrue(claimed["loginState"])

    def test_url_policy_and_handoff_downloads_files_audio(self) -> None:
        with self.assertRaises(PermissionError):
            deny_url("javascript:alert(1)")
        tab = self.executor.execute("tab_new", {"url": "https://example.com/"})["result"]
        tid = tab["id"]
        handoff = self.executor.execute("tab_mark_handoff", {"tab_id": tid})["result"]
        self.assertTrue(handoff["handoff"])
        cloud = self.executor.execute("tab_request_manual_handoff", {"tab_id": tid})["result"]
        self.assertTrue(cloud["manual_handoff"])
        files = self.executor.execute("tab_pw_set_files", {"tab_id": tid, "files": ["C:/tmp/a.png"]})["result"]
        self.assertEqual(files["files"], ["C:/tmp/a.png"])
        chooser = self.executor.execute("tab_pw_expect_file_chooser", {"tab_id": tid})["result"]
        self.assertEqual(chooser["event"], "filechooser")
        media = self.executor.execute("tab_dom_download_media", {"tab_id": tid, "node_id": 2})["result"]
        self.assertEqual(media["action"], "downloadMedia")
        cua = self.executor.execute("tab_cua_download_media", {"tab_id": tid, "x": 10, "y": 10})["result"]
        self.assertIn("download", cua)
        # Audio tools are gated: `executor.tool_names` only carries them when the
        # deployment enables audio, so assert the gate rather than assuming the
        # tools always exist. When they do exist, drive the full cycle.
        if "start_audio_recording" in self.executor.tool_names:
            audio = self.executor.execute("start_audio_recording", {})["result"]
            self.assertTrue(audio["recording"])
            stopped = self.executor.execute("stop_audio_recording", {})["result"]
            self.assertFalse(stopped["recording"])
        else:
            with self.assertRaises(KeyError):
                self.executor.execute("start_audio_recording", {})


class ExtensionInstanceTests(unittest.TestCase):
    """BR-12: the claim must honour metadata.extensionInstanceId."""

    def test_claim_only_matches_the_requested_instance(self) -> None:
        hub = ExtensionHub()
        shared = {"providerTabId": "5", "title": "Same", "url": "https://same.test/"}
        hub.ingest(
            {
                "type": "hello",
                "instanceId": "inst-2",
                "family": "chrome",
                "tabs": [
                    {**shared, "extensionInstanceId": "inst-1"},
                    {**shared, "extensionInstanceId": "inst-2"},
                ],
            }
        )
        ok = hub.claim("5", "Same", "https://same.test/", instance_id="inst-2")
        self.assertTrue(ok["claimed"])
        refused = hub.claim("5", "Same", "https://same.test/", instance_id="inst-9")
        self.assertFalse(refused["claimed"])
        self.assertTrue(refused["unavailable"])

    def test_diagnose_reports_a_missing_extension(self) -> None:
        hub = ExtensionHub()
        report = hub.diagnose()
        self.assertFalse(report["connected"])
        self.assertIn("Cannot communicate with the ChatGPT browser extension", report["message"])


if __name__ == "__main__":
    unittest.main()
