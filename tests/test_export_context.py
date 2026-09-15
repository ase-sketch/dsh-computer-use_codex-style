from __future__ import annotations

import unittest

from computer_use.browser_export import gsuite_export_url, is_login_wall, parse_timedtext_xml
from computer_use.chrome_history import webkit_to_iso
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.extension_hub import ExtensionHub
from computer_use.fake_backend import FakeDesktop


class ExportContextTests(unittest.TestCase):
    def test_login_wall_detection(self) -> None:
        html = b"<!DOCTYPE html><html><body>Sign in to continue to Google</body></html>"
        self.assertTrue(is_login_wall(html, "text/html"))
        self.assertFalse(is_login_wall(b"%PDF-1.4 ...", "application/pdf"))

    def test_timedtext_and_webkit_time(self) -> None:
        xml = '<transcript><text start="0">Hello</text><text>world &amp; you</text></transcript>'
        self.assertEqual(parse_timedtext_xml(xml), "Hello\nworld & you")
        iso = webkit_to_iso(13300000000000000)
        self.assertTrue(iso.startswith("20"))

    def test_gsuite_export_urls(self) -> None:
        doc = gsuite_export_url("https://docs.google.com/document/d/abc123/edit", "pdf")
        self.assertEqual(doc, "https://docs.google.com/document/d/abc123/export?format=pdf")
        sheet = gsuite_export_url("https://docs.google.com/spreadsheets/d/xyz/edit#gid=0", "csv")
        self.assertIn("/spreadsheets/d/xyz/export?format=csv", sheet or "")

    def test_hub_context_without_claim(self) -> None:
        executor = ToolExecutor(ComputerUse(FakeDesktop()))
        hub = ExtensionHub()
        executor.browser.hub = hub
        hub.ingest(
            {
                "type": "hello",
                "instanceId": "i",
                "tabs": [
                    {
                        "providerTabId": "9",
                        "title": "Doc",
                        "url": "https://docs.google.com/document/d/abc/edit",
                        "text": "Logged-in document body " * 20,
                    }
                ],
            }
        )
        ctx = executor.execute(
            "browser_get_tab_context",
            {"providerTabId": "9", "title": "Doc", "url": "https://docs.google.com/document/d/abc/edit"},
        )["result"]
        self.assertFalse(ctx["claimed"])
        self.assertIn("Logged-in", ctx["text"])
        self.assertTrue(ctx["loginState"])

    def test_gsuite_export_records_export_url(self) -> None:
        executor = ToolExecutor(ComputerUse(FakeDesktop()))
        tab = executor.execute("tab_new", {"url": "https://docs.google.com/document/d/abc123/edit"})["result"]
        # fake goto may not parse google title; set via backend tab
        backend = executor.browser.browser
        backend.tab(tab["id"]).url = "https://docs.google.com/document/d/abc123/edit"
        exported = executor.execute("tab_content_export_gsuite", {"tab_id": tab["id"], "type": "pdf"})["result"]
        self.assertIn("export?format=pdf", str(exported.get("exportUrl") or exported.get("path")))
