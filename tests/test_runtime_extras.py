from __future__ import annotations

import struct
import unittest

from computer_use.approval import ApprovalDenied, ApprovalGate, AppApprovalRequest
from computer_use.driver import ComputerUse
from computer_use.errors import TurnInterrupted
from computer_use.fake_backend import FakeDesktop
from computer_use.interrupt import ESCAPE_MESSAGE, InterruptFlag
from computer_use.models import AppInfo
from computer_use.overlay import BANNER, ESC_HINT, OverlaySession
from computer_use.user_assist import Usage, merge_usage, parse_count_blob, rot13
from computer_use.wgc import MonitorFrame, crop_window_from_monitor, default_session

WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class RuntimeExtrasTests(unittest.TestCase):
    def test_wgc_monitor_crop_and_session_flags(self) -> None:
        session = default_session()
        self.assertFalse(session.cursor_capture)
        self.assertFalse(session.border_required)
        self.assertEqual(session.source, "monitor")
        crop = crop_window_from_monitor(MonitorFrame(0, 0, 1920, 1080), 100, 200, 800, 600)
        self.assertEqual(crop, (100, 200, 800, 600))
        clamped = crop_window_from_monitor(MonitorFrame(0, 0, 100, 100), 0, 0, 800, 600)
        self.assertEqual(clamped, (0, 0, 100, 100))
        with self.assertRaises(Exception):
            crop_window_from_monitor(MonitorFrame(0, 0, 100, 100), 400, 400, 50, 50)

    def test_user_assist_rot13_and_merge(self) -> None:
        self.assertEqual(rot13(rot13("notepad.exe")), "notepad.exe")
        blob = bytearray(72)
        struct.pack_into("<I", blob, 4, 12)
        struct.pack_into("<Q", blob, 60, 132000000000000000)
        usage = parse_count_blob(bytes(blob))
        self.assertEqual(usage.use_count, 12)
        self.assertTrue(usage.last_used)
        apps = [AppInfo("notepad.exe", "Notepad")]
        merge_usage(apps, {"notepad.exe": Usage(7, "2026-01-01T00:00:00+00:00")})
        self.assertEqual(apps[0].to_dict()["useCount"], 7)
        self.assertEqual(apps[0].to_dict()["lastUsedDate"], "2026-01-01T00:00:00+00:00")

    def test_approval_elicitation(self) -> None:
        seen: list[str] = []

        def reject(request: AppApprovalRequest) -> dict[str, object]:
            seen.append(request.message())
            return {"action": "reject"}

        gate = ApprovalGate(elicitation=reject)
        driver = ComputerUse(FakeDesktop(), approval=gate)
        driver.get_window_state({"window": WINDOW})
        with self.assertRaises(ApprovalDenied):
            driver.click({"window": WINDOW, "element_index": 1})
        self.assertTrue(seen[0].startswith("Allow DeepSeek Harness to use"))
        accept = ApprovalGate()
        allowed = ComputerUse(FakeDesktop(), approval=accept)
        allowed.get_window_state({"window": WINDOW})
        allowed.click({"window": WINDOW, "element_index": 1})
        self.assertIn("notepad.exe", accept.always | accept.session)

    def test_escape_hook_does_not_install_until_overlay_shows(self) -> None:
        from computer_use.interrupt import EscapeHook

        flag = InterruptFlag()
        hook = EscapeHook(flag)
        hook.start()
        import time

        time.sleep(0.05)
        self.assertEqual(hook._hook, 0)
        self.assertEqual(hook._mouse_hook, 0)
        hook.stop()

    def test_escape_interrupt(self) -> None:
        flag = InterruptFlag()
        driver = ComputerUse(FakeDesktop(), interrupt=flag)
        flag.trip()
        with self.assertRaises(TurnInterrupted) as raised:
            driver.click({"window": WINDOW, "x": 10, "y": 10})
        self.assertEqual(str(raised.exception), ESCAPE_MESSAGE)

    def test_overlay_banner_and_cursor(self) -> None:
        overlay = OverlaySession(enabled=True)
        driver = ComputerUse(FakeDesktop(), overlay=overlay)
        driver.get_window_state({"window": WINDOW, "include_screenshot": True})
        driver.click({"window": WINDOW, "x": 40, "y": 80, "screenshotId": "screenshot-0"})
        kinds = [event.kind for event in overlay.events]
        self.assertIn("show_banner", kinds)
        self.assertIn("move_cursor", kinds)
        self.assertIn(BANNER, overlay.events[0].text or "")
        self.assertIn(ESC_HINT, overlay.events[0].text or "")
        self.assertNotIn("ChatGPT", overlay.events[0].text or "")
        self.assertNotIn("Codex", overlay.events[0].text or "")
        overlay.hide()


if __name__ == "__main__":
    unittest.main()
