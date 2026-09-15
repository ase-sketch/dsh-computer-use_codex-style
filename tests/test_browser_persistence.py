from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from computer_use import browser_persistence as p
from computer_use.browser_api import BrowserSurface
from computer_use.browser_checks import BrowserSecurityPolicy
from computer_use.browser_fake import FakeBrowser


class OfficialTokenTests(unittest.TestCase):
    def test_sections_and_values_are_the_official_tokens(self) -> None:
        self.assertEqual(p.APPROVAL_MODE, "approval_mode")
        self.assertEqual(p.HISTORY_APPROVAL_MODE, "history_approval_mode")
        self.assertEqual(p.IAB_HISTORY_APPROVAL_MODE, "iab_history_approval_mode")
        self.assertEqual(p.NEVER_ASK, "never_ask")
        self.assertEqual(p.DISABLED, "disabled")
        self.assertEqual(p.ORIGINS, "origins")
        self.assertEqual(p.FULL_CDP, "full_cdp")
        self.assertEqual(p.DOWNLOADS, "downloads")
        self.assertEqual(p.UPLOADS, "uploads")
        self.assertEqual(p.ALLOWED, "allowed")
        self.assertEqual(p.DENIED, "denied")
        self.assertEqual(p.TURN_GRANT_TTL_MS, 300_000)

    def test_zw_section_mapping(self) -> None:
        self.assertEqual(p.section_for("origin"), p.ORIGINS)
        self.assertEqual(p.section_for("fileTransfer", transfer_kind="download"), p.DOWNLOADS)
        self.assertEqual(p.section_for("fileTransfer", transfer_kind="upload"), p.UPLOADS)
        self.assertEqual(p.section_for("fullCdp"), p.FULL_CDP)
        self.assertIsNone(p.section_for("other"))

    def test_check_to_section_mapping(self) -> None:
        self.assertEqual(p.section_for_check("browser-origin-access"), p.ORIGINS)
        self.assertEqual(p.section_for_check("file-download"), p.DOWNLOADS)
        self.assertEqual(p.section_for_check("file-upload"), p.UPLOADS)
        self.assertEqual(p.section_for_check("full-cdp"), p.FULL_CDP)
        # webmcp / precheck have no official persisted resource.
        self.assertIsNone(p.section_for_check("webmcp-tool-call"))
        self.assertIsNone(p.section_for_check("automated-safety-precheck"))

    def test_history_mode_mapping(self) -> None:
        self.assertEqual(p.history_section(iab=False), "history_approval_mode")
        self.assertEqual(p.history_section(iab=True), "iab_history_approval_mode")
        self.assertEqual(p.history_decision_for("never_ask"), "approve")
        self.assertEqual(p.history_decision_for("disabled"), "deny")
        self.assertEqual(p.history_decision_for(None), "always_ask")


class StoreTests(unittest.TestCase):
    def test_pj_moves_the_key_between_the_lists(self) -> None:
        store = p.PersistedConsentStore()
        store.record(p.ORIGINS, "https://a.test", "approve")
        self.assertEqual(store.decision(p.ORIGINS, "https://a.test"), "approve")
        store.record(p.ORIGINS, "https://a.test", "deny")
        self.assertEqual(store.decision(p.ORIGINS, "https://a.test"), "deny")
        bucket = store.mode(p.ORIGINS)
        self.assertEqual(bucket[p.ALLOWED], [])

    def test_wildcard_origin_is_escaped(self) -> None:
        store = p.PersistedConsentStore()
        store.record(p.ORIGINS, "https://*.test", "approve")
        self.assertEqual(store.decision(p.ORIGINS, "https://*.test"), "approve")
        self.assertIn("\\*", json.dumps(store.to_document()))

    def test_session_scope_needs_a_conversation_id(self) -> None:
        store = p.PersistedConsentStore()
        self.assertFalse(store.record(p.ORIGINS, "https://a.test", "approve", scope="session"))
        self.assertTrue(
            store.record(
                p.ORIGINS, "https://a.test", "approve", scope="session", conversation_id="c1"
            )
        )
        self.assertEqual(
            store.decision(p.ORIGINS, "https://a.test", scope="session", conversation_id="c1"),
            "approve",
        )

    def test_never_ask_origin_writes_approval_mode(self) -> None:
        store = p.PersistedConsentStore()
        store.record_never_ask_origin()
        self.assertEqual(store.mode(p.APPROVAL_MODE), p.NEVER_ASK)

    def test_history_never_ask_is_global_only(self) -> None:
        store = p.PersistedConsentStore()
        self.assertFalse(store.record_history("approve", scope="session", conversation_id="c"))
        self.assertFalse(store.record_history("deny", scope="global"))
        self.assertTrue(store.record_history("approve", scope="global"))
        self.assertEqual(store.history_decision(), "approve")

    def test_disk_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            store = p.PersistedConsentStore(path=path)
            store.record(p.ORIGINS, "https://persist.test", "approve")
            store.record(p.DOWNLOADS, "https://files.test", "deny")
            self.assertTrue(store.save())
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            reloaded = p.PersistedConsentStore.load(path)
            self.assertEqual(reloaded.decision(p.ORIGINS, "https://persist.test"), "approve")
            self.assertEqual(reloaded.decision(p.DOWNLOADS, "https://files.test"), "deny")

    def test_in_memory_store_never_touches_disk(self) -> None:
        store = p.PersistedConsentStore()
        self.assertFalse(store.save())
        self.assertIsNone(store.path)


class PolicyPersistenceTests(unittest.TestCase):
    def test_persisted_approval_is_not_asked_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            first = BrowserSecurityPolicy.from_disk(path)
            first.gate(
                "browser-origin-access",
                "https://y.test",
                approver=lambda request: "always",
                origin="https://y.test",
            )
            asks: list[int] = []
            second = BrowserSecurityPolicy.from_disk(path)
            second.gate(
                "browser-origin-access",
                "https://y.test",
                approver=lambda request: asks.append(1) or "deny",
                origin="https://y.test",
            )
            self.assertEqual(asks, [])

    def test_persisted_denial_fails_closed(self) -> None:
        from computer_use.browser_security import BrowserUseSecurityError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            # Official lJ(): a decline persists at the conversation scope, so a
            # conversation id is required (Vw(conversationId)).
            first = BrowserSecurityPolicy.from_disk(path, conversation_id="conv-x")
            with self.assertRaises(BrowserUseSecurityError):
                first.gate(
                    "browser-origin-access",
                    "https://nope.test",
                    approver=lambda request: "deny",
                    origin="https://nope.test",
                )
            asks: list[int] = []
            second = BrowserSecurityPolicy.from_disk(path, conversation_id="conv-x")
            with self.assertRaises(BrowserUseSecurityError) as raised:
                second.gate(
                    "browser-origin-access",
                    "https://nope.test",
                    approver=lambda request: asks.append(1) or "approve",
                    origin="https://nope.test",
                )
            self.assertEqual(raised.exception.reason, "persisted_user_denied")
            self.assertEqual(asks, [])

    def test_never_token_writes_the_official_never_ask_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            policy = BrowserSecurityPolicy.from_disk(path)
            policy.gate(
                "browser-origin-access",
                "https://z.test",
                approver=lambda request: "never",
                origin="https://z.test",
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["global"][p.APPROVAL_MODE], p.NEVER_ASK)

    def test_never_ask_marker_auto_approves_a_fresh_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "never.json"
            marker = p.PersistedConsentStore(path=path)
            marker.record_never_ask_origin()
            marker.save()
            asks: list[int] = []
            policy = BrowserSecurityPolicy.from_disk(path)
            policy.gate(
                "browser-origin-access",
                "https://brand-new.test",
                approver=lambda request: asks.append(1) or "deny",
                origin="https://brand-new.test",
            )
            self.assertEqual(asks, [])

    def test_conversation_denial_beats_a_global_allow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "precedence.json"
            store = p.PersistedConsentStore(path=path)
            store.record(p.ORIGINS, "https://x.test", "approve", scope="global")
            store.record(
                p.ORIGINS, "https://x.test", "deny", scope="session", conversation_id="conv-1"
            )
            store.save()
            policy = BrowserSecurityPolicy.from_disk(path, conversation_id="conv-1")
            self.assertEqual(
                policy.persisted_decision("browser-origin-access", "https://x.test"), "deny"
            )

    def test_never_ask_mode_key_matches_yb(self) -> None:
        self.assertEqual(p.never_ask_mode_key("browser-origin-access"), p.APPROVAL_MODE)
        self.assertEqual(p.never_ask_mode_key("file-download"), p.DOWNLOAD_APPROVAL_MODE)
        self.assertEqual(p.never_ask_mode_key("file-upload"), p.UPLOAD_APPROVAL_MODE)
        self.assertIsNone(p.never_ask_mode_key("full-cdp"))

    def test_persisted_history_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            policy = BrowserSecurityPolicy.from_disk(path)
            policy.gate(
                "browser-history-read",
                "browsing_history",
                approver=lambda request: "always",
            )
            restored = BrowserSecurityPolicy.from_disk(path)
            asks: list[int] = []
            restored.gate(
                "browser-history-read",
                "browsing_history",
                approver=lambda request: asks.append(1) or "deny",
            )
            self.assertEqual(asks, [])


class TurnGrantTests(unittest.TestCase):
    def test_turn_grant_expires_and_is_turn_scoped(self) -> None:
        grants = p.TurnGrants(ttl_ms=50)
        grants.grant("c1", "t1", "https://a.test")
        self.assertTrue(grants.active("c1", "t1", "https://a.test"))
        self.assertFalse(grants.active("c1", "t2", "https://a.test"))
        # The turn/origin mismatch clears the entry.
        self.assertFalse(grants.active("c1", "t1", "https://a.test"))
        grants.grant("c1", "t1", "https://a.test")
        import time

        time.sleep(0.08)
        self.assertFalse(grants.active("c1", "t1", "https://a.test"))

    def test_surface_turn_grant_skips_the_second_ask(self) -> None:
        surface = BrowserSurface(browser=FakeBrowser())
        surface.set_turn_context("conv-1", "turn-1")
        asks: list[int] = []
        surface.approvals = lambda request: asks.append(1) or "approve"
        surface.security_policy.gate(
            "browser-origin-access",
            "https://turn.test",
            approver=surface.approvals,
            origin="https://turn.test",
        )
        surface.security_policy.granted = lambda *args, **kwargs: False  # type: ignore[assignment]
        outcome = surface.security_policy.gate(
            "browser-origin-access",
            "https://turn.test",
            approver=surface.approvals,
            origin="https://turn.test",
        )
        self.assertEqual(outcome, "granted-turn")
        self.assertEqual(len(asks), 1)


class SurfacePersistenceTests(unittest.TestCase):
    def test_surface_persists_an_always_grant_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "consent.json")
            surface = BrowserSurface(browser=FakeBrowser(), consent_path=path)
            surface.approvals = lambda request: "always"
            tab = surface.dispatch("tab_new", {"url": "https://persist.test/"})
            surface.dispatch("navigate_tab_url", {"tab_id": tab["id"], "url": "https://persist.test/"})
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertIn("persist.test", json.dumps(document))
            self.assertEqual(surface.security_policy.persisted_decision(
                "browser-origin-access", "https://persist.test"
            ), "approve")

    def test_enable_persistence_returns_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "consent.json")
            surface = BrowserSurface(browser=FakeBrowser())
            self.assertEqual(surface.enable_persistence(path), path)
            self.assertIsNotNone(surface.security_policy.store)
            self.assertEqual(surface.security_policy.store.path, Path(path))
            self.assertEqual(surface.enable_persistence(), path)


if __name__ == "__main__":
    unittest.main()
