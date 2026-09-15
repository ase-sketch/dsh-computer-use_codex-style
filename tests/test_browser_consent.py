from __future__ import annotations

import ast
import unittest
from pathlib import Path

from computer_use.browser_checks import BrowserSecurityPolicy
from computer_use.browser_security import BrowserUseSecurityError
from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop

ROOT = Path(__file__).resolve().parents[1]

#: BR-08: every one of these used to be dead code (definition + __all__ only).
ENTRY_POINTS = (
    "consent_for",
    "origin_consent",
    "history_consent",
    "upload_consent",
    "download_consent",
    "full_cdp_consent",
    "assert_origin_allowed",
    "assert_upload_allowed",
    "assert_download_allowed",
    "assert_full_cdp_allowed",
    "assert_page_asset_download_allowed",
    "remember_origin",
)


class BrowserConsentTests(unittest.TestCase):
    def test_every_security_entry_point_has_a_call_site(self) -> None:
        called: set[str] = set()
        for path in (ROOT / "computer_use").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in ENTRY_POINTS:
                    called.add(name)
        missing = sorted(set(ENTRY_POINTS) - called)
        self.assertEqual(missing, [], f"security entry points with no call site: {missing}")

    def test_denial_generates_official_consent_then_fails_closed(self) -> None:
        asks = []

        def approver(request):
            asks.append(request)
            return "deny"

        policy = BrowserSecurityPolicy()
        with self.assertRaises(BrowserUseSecurityError) as raised:
            policy.gate(
                "browser-origin-access",
                "https://x.test",
                approver=approver,
                origin="https://x.test",
            )
        self.assertEqual(raised.exception.reason, "user_declined")
        self.assertEqual(asks[0].message, "Allow DeepSeek Harness to access https://x.test?")
        self.assertEqual(asks[0].tool_name, "access_browser_origin")
        self.assertIn("access_browser_origin", asks[0].to_elicitation()["tool_name"])

    def test_approval_grants_and_is_not_asked_again(self) -> None:
        asks = []

        def approver(request):
            asks.append(request)
            return "approve"

        policy = BrowserSecurityPolicy()
        policy.gate(
            "browser-origin-access", "https://y.test", approver=approver, origin="https://y.test"
        )
        policy.assert_origin_allowed("https://y.test")
        policy.gate(
            "browser-origin-access", "https://y.test", approver=approver, origin="https://y.test"
        )
        self.assertEqual(len(asks), 1)
        decisions = {(entry["check"], entry["key"]): entry["decision"] for entry in policy.audit}
        self.assertEqual(decisions[("browser-origin-access", "https://y.test")], "approved")

    def test_default_ask_without_approver_records_and_proceeds(self) -> None:
        policy = BrowserSecurityPolicy()
        self.assertEqual(policy.gate("browser-history-read", "browsing_history"), "recorded")
        self.assertTrue(policy.granted("browser-history-read", "browsing_history"))

    def test_deny_default_fails_closed(self) -> None:
        policy = BrowserSecurityPolicy(default_decision="deny")
        with self.assertRaises(BrowserUseSecurityError):
            policy.gate("browser-history-read", "browsing_history")

    def test_disabled_for_local_testing_bypasses(self) -> None:
        policy = BrowserSecurityPolicy(mode="disabled-for-local-testing")
        self.assertEqual(
            policy.gate(
                "browser-origin-access", "https://z.test", origin="https://z.test"
            ),
            "bypassed",
        )

    def test_gaas_precheck_denial_is_guardian_denied(self) -> None:
        policy = BrowserSecurityPolicy(mode="gaas-browser-environment")
        self.assertTrue(policy.precheck_required)
        with self.assertRaises(BrowserUseSecurityError) as raised:
            policy.gate(
                "automated-safety-precheck",
                "tab_ax_get_state",
                approver=lambda request: "deny",
                tool="tab_ax_get_state",
            )
        self.assertEqual(raised.exception.reason, "guardian_denied")

    def test_always_grant_survives_session_export(self) -> None:
        # BR-17: `always` grants are persisted by the host; `session` ones are not.
        policy = BrowserSecurityPolicy()
        policy.gate(
            "file-download",
            "https://d.test/f.zip",
            approver=lambda request: "always",
            url="https://d.test/f.zip",
        )
        always = policy.export_grants(include_session=False)
        self.assertEqual(always["file-download"]["https://d.test/f.zip"], "always")
        restored = BrowserSecurityPolicy()
        restored.import_grants(always)
        self.assertTrue(restored.granted("file-download", "https://d.test/f.zip"))

    def test_surface_dispatch_is_gated(self) -> None:
        ex = ToolExecutor(ComputerUse(FakeDesktop()))
        surface = ex.browser
        surface.approvals = lambda request: "deny"
        tab = surface.dispatch("tab_new", {"url": "https://example.com/"})
        with self.assertRaises(BrowserUseSecurityError):
            surface.dispatch("tab_ax_get_state", {"tab_id": tab["id"]})

    def test_gaas_precheck_fires_on_dispatch(self) -> None:
        ex = ToolExecutor(ComputerUse(FakeDesktop()))
        surface = ex.browser
        surface.security_policy.mode = "gaas-browser-environment"
        surface.approvals = lambda request: "deny"
        with self.assertRaises(BrowserUseSecurityError):
            surface.dispatch("browser_list", {})


if __name__ == "__main__":
    unittest.main()
