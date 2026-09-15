from __future__ import annotations

import unittest

from computer_use import browser_meta as m
from computer_use.browser_api import BrowserSurface
from computer_use.browser_fake import FakeBrowser
from computer_use.browser_lifecycle import TabLifecycle

FENCE = chr(96) * 3
TOOL_BLOCK = "WebMCP tools are available in tab 3:\n\n" + FENCE + 'json\n[{"name":"x"}]\n' + FENCE


class FormatTests(unittest.TestCase):
    def test_empty_list_produces_the_empty_string(self) -> None:
        self.assertEqual(m.format_browser_notifications([]), "")
        self.assertEqual(m.format_browser_notifications(None), "")
        self.assertEqual(m.format_browser_notifications(["", None]), "")  # type: ignore[list-item]

    def test_items_are_joined_by_a_blank_line(self) -> None:
        self.assertEqual(
            m.format_browser_notifications(["A", "B"]),
            "Browser notifications:\n\nA\n\nB\n",
        )
        self.assertEqual(m.BROWSER_NOTIFICATIONS_HEADER, "Browser notifications:")


class FilterTests(unittest.TestCase):
    def test_webmcp_changed_filter_matches_the_official_vx(self) -> None:
        events = [
            {"type": "webmcp_changed", "version": 1, "tabId": 4},
            {"type": "webmcp_changed", "version": 2, "tabId": 5},
            {"type": "other", "version": 1, "tabId": 6},
            {"type": "webmcp_changed", "version": 1, "tabId": 0},
            {"type": "webmcp_changed", "version": 1, "tabId": "7"},
            {"type": "webmcp_changed", "version": 1, "tabId": 4},
        ]
        self.assertEqual(m.webmcp_changed_tab_ids(events), [4])

    def test_only_external_acquisitions_qualify(self) -> None:
        events = [
            {"type": "tab_created", "tabId": "tab-1", "origin": "agent"},
            {"type": "tab_acquired", "tabId": "tab-1", "origin": "agent"},
            {"type": "tab_acquired", "tabId": "tab-2", "origin": "external"},
            {"type": "tab_acquired", "tabId": "tab-3", "origin": "external"},
        ]
        self.assertEqual(m.externally_acquired_tab_ids(events), ["tab-2", "tab-3"])


class ContributorTests(unittest.TestCase):
    def test_available_block_and_unchanged_and_gone(self) -> None:
        tools = [{"name": "x", "pageUrl": "https://page.test"}]
        first = m.webmcp_notification("3", tools, None)
        self.assertEqual(first, TOOL_BLOCK)
        # pageUrl is dropped by the official Kp() serialization.
        self.assertNotIn("pageUrl", first)
        self.assertEqual(m.webmcp_notification("3", tools, m.serialize_webmcp_tools(tools)), "")
        self.assertEqual(
            m.webmcp_notification("3", [], m.serialize_webmcp_tools(tools)),
            "WebMCP tools are no longer available in tab 3.",
        )
        self.assertEqual(m.webmcp_notification("3", [], None), "")

    def test_notifications_drain_both_sources(self) -> None:
        items = m.webmcp_notifications(
            [{"type": "webmcp_changed", "version": 1, "tabId": 1}],
            [{"type": "tab_acquired", "tabId": "tab-2", "origin": "external"}],
            list_tools=lambda tab_id: [{"name": "t"}],
        )
        self.assertEqual(len(items), 2)
        self.assertIn("tab 1:", items[0])
        self.assertIn("tab tab-2:", items[1])

    def test_disabled_webmcp_clears_the_cache(self) -> None:
        cache: dict = {3: "stale"}
        text = m.take_browser_notifications(
            [],
            [{"type": "tab_acquired", "tabId": 3, "origin": "external"}],
            webmcp_enabled=False,
            list_tools=lambda tab_id: [{"name": "x"}],
            cache=cache,
        )
        self.assertEqual(text, "")
        self.assertEqual(cache, {})

    def test_session_filter_keeps_only_the_current_session(self) -> None:
        events = [
            {"type": "webmcp_changed", "version": 1, "tabId": 1, "session_id": "mine"},
            {"type": "webmcp_changed", "version": 1, "tabId": 2, "session_id": "other"},
        ]
        text = m.take_browser_notifications(
            events, [], list_tools=lambda tab_id: [{"name": "x"}], current_session_id="mine"
        )
        self.assertIn("tab 1:", text)
        self.assertNotIn("tab 2:", text)

    def test_tool_fetch_failure_is_not_fatal(self) -> None:
        def boom(tab_id: int) -> list:
            raise RuntimeError("no cdp")

        text = m.take_browser_notifications(
            [], [{"type": "tab_acquired", "tabId": 3, "origin": "external"}], list_tools=boom
        )
        self.assertEqual(text, "")


class LifecycleEventTests(unittest.TestCase):
    def test_lifecycle_records_official_events(self) -> None:
        life = TabLifecycle()
        life.record_created("tab-1")
        life.record_acquired("tab-2")
        life.record_acquired("tab-2")
        events = life.take_events()
        self.assertEqual(events[0], {"type": "tab_created", "tabId": "tab-1", "origin": "agent"})
        self.assertEqual(events[1], {"type": "tab_acquired", "tabId": "tab-2", "origin": "external"})
        self.assertEqual(len(events), 2)
        self.assertEqual(life.take_events(), [])

    def test_record_acquired_honours_an_explicit_origin(self) -> None:
        life = TabLifecycle()
        life.record_acquired("7", "agent")
        self.assertEqual(life.take_events()[0]["origin"], "agent")


class SurfaceNotificationTests(unittest.TestCase):
    def _surface(self) -> BrowserSurface:
        surface = BrowserSurface(browser=FakeBrowser())
        surface.browser.webmcp_fetch = lambda tab_id: [{"name": "tool-a"}]  # type: ignore[attr-defined]
        return surface

    def test_end_turn_carries_the_notification_item(self) -> None:
        surface = self._surface()
        tab = surface.dispatch("tab_new", {"url": "https://example.com/"})
        surface.lifecycle.record_acquired(str(tab["id"]), "external")
        outcome = surface.end_turn()
        self.assertIn("browserNotifications", outcome)
        self.assertIn("WebMCP tools are available in tab", outcome["browserNotifications"])

    def test_end_turn_omits_the_item_when_empty(self) -> None:
        surface = BrowserSurface(browser=FakeBrowser())
        surface.dispatch("tab_new", {"url": "https://example.com/"})
        self.assertNotIn("browserNotifications", surface.end_turn())

    def test_unchanged_tools_only_notify_once_across_turns(self) -> None:
        surface = self._surface()
        tab = surface.dispatch("tab_new", {"url": "https://example.com/"})
        surface.lifecycle.record_acquired(str(tab["id"]), "external")
        self.assertTrue(surface.end_turn().get("browserNotifications"))
        surface.lifecycle.record_acquired(str(tab["id"]), "external")
        self.assertNotIn("browserNotifications", surface.end_turn())

    def test_page_events_from_the_hub_are_drained(self) -> None:
        surface = self._surface()
        surface.hub.ingest(
            {
                "type": "page_event",
                "event": {"type": "webmcp_changed", "version": 1, "tabId": 5},
            }
        )
        text = surface.dispatch("browser_notifications", {})["notifications"]
        self.assertIn("tab 5:", text)
        # Drained: a second call has nothing.
        self.assertEqual(surface.dispatch("browser_notifications", {})["notifications"], "")

    def test_push_page_event_is_drained(self) -> None:
        surface = self._surface()
        surface.push_page_event({"type": "webmcp_changed", "version": 1, "tabId": 9})
        text = surface.dispatch("take_browser_notifications", {})["notifications"]
        self.assertIn("tab 9:", text)

    def test_turn_end_command_sets_the_turn_context(self) -> None:
        surface = self._surface()
        surface.dispatch("browser_turn_end", {"session_id": "conv", "turn_id": "turn-7"})
        self.assertEqual(surface.security_policy.conversation_id, "conv")
        self.assertEqual(surface.security_policy.turn_id, "turn-7")


if __name__ == "__main__":
    unittest.main()
