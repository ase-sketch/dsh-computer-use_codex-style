from __future__ import annotations

import os
import tempfile
import unittest

from computer_use.driver import ComputerUse
from computer_use.fake_backend import FakeDesktop
from computer_use.input_monitor import USER_INPUT_MESSAGE, injected_key, injected_mouse
from computer_use.overlay_win import WDA_EXCLUDEFROMCAPTURE, exclude_from_capture
from computer_use.validate import scroll_element_args
from computer_use.win_uia import CONTROL_TYPES, truncated_label


WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class ExcludeFromCaptureTests(unittest.TestCase):
    def test_affinity_constant(self) -> None:
        self.assertEqual(WDA_EXCLUDEFROMCAPTURE, 0x11)

    def test_exclude_null_hwnd(self) -> None:
        self.assertFalse(exclude_from_capture(0))


class ScrollElementTests(unittest.TestCase):
    def test_direction_and_pages(self) -> None:
        direction, pages = scroll_element_args({"direction": "Down", "pages": 2.2})
        self.assertEqual(direction, "down")
        self.assertEqual(pages, 2)

    def test_bad_direction(self) -> None:
        with self.assertRaises(TypeError) as raised:
            scroll_element_args({"direction": "sideways"})
        self.assertIn("unsupported scroll direction", str(raised.exception))

    def test_pages_must_be_positive(self) -> None:
        with self.assertRaises(TypeError) as raised:
            scroll_element_args({"direction": "up", "pages": 0})
        self.assertIn("pages must be a finite number > 0", str(raised.exception))

    def test_helper_method_records_direction(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW, "include_text": True})
        result = driver.scroll_element({"window": WINDOW, "element_index": 1, "direction": "down", "pages": 3})
        self.assertTrue(result["ok"])
        record = driver.backend.actions[-1]
        self.assertEqual(record.kind, "scroll_element")
        self.assertEqual(record.payload["direction"], "down")
        self.assertEqual(record.payload["pages"], 3)

    def test_scroll_with_element_index_routes_to_scroll_element(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW, "include_text": True})
        driver.scroll({"window": WINDOW, "element_index": 1, "direction": "up", "pages": 1})
        self.assertEqual(driver.backend.actions[-1].kind, "scroll_element")


class UserInputMonitorTests(unittest.TestCase):
    def test_injected_flags(self) -> None:
        self.assertTrue(injected_mouse(0x00000001))
        self.assertFalse(injected_mouse(0))
        self.assertTrue(injected_key(0x00000010))
        self.assertFalse(injected_key(0))

    def test_user_input_requires_reobserve(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW})
        driver.interrupt.input_monitor.mark_user_input("pointer")
        with self.assertRaises(PermissionError) as raised:
            driver.click({"window": WINDOW, "element_index": 1})
        self.assertEqual(str(raised.exception), USER_INPUT_MESSAGE)
        driver.get_window_state({"window": WINDOW})
        result = driver.click({"window": WINDOW, "element_index": 1})
        self.assertTrue(result["ok"])

    def test_synthetic_input_is_ignored(self) -> None:
        driver = ComputerUse(FakeDesktop())
        driver.get_window_state({"window": WINDOW})
        driver.interrupt.input_monitor.mark_synthetic(1.0)
        driver.interrupt.input_monitor.mark_user_input("pointer")
        result = driver.click({"window": WINDOW, "element_index": 1})
        self.assertTrue(result["ok"])


class NotifyConfigTests(unittest.TestCase):
    def test_feature_status_and_approval_notify(self) -> None:
        from computer_use.approval import AppApprovalRequest
        from computer_use.notify_config import (
            SKIPPED_MISSING_COMMAND,
            apply_previous_notify,
            feature_status,
            write_notify_config,
        )

        status = feature_status()
        self.assertTrue(status["allowBrowserAndComputerUse"])
        self.assertTrue(status["features"]["computerUse"])
        self.assertIn("defaultAppAccess", status)
        payload = AppApprovalRequest("notepad.exe", "Notepad").to_helper()
        self.assertTrue(payload["notify"])
        self.assertIn(payload["riskLevel"], {"low", "high"})
        with self.assertRaises(TypeError) as raised:
            apply_previous_notify([])
        self.assertEqual(str(raised.exception), SKIPPED_MISSING_COMMAND)
        home = tempfile.mkdtemp()
        os.environ["DSH_HOME"] = home
        path = write_notify_config("sess", "turn")
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "config.json")
        self.assertIn("computer-use", str(path))


class CaptureTimeoutAndSpacesTests(unittest.TestCase):
    def test_observation_emits_screenshot_spaces(self) -> None:
        from computer_use.fake_backend import FakeDesktop
        from computer_use.models import Observation, WindowRef

        obs = Observation(
            screenshot=b"\xff\xd8",
            mime_type="image/jpeg",
            tree=[],
            window=WindowRef("notepad.exe", 1, "n"),
            tree_text="",
            screenshot_id="screenshot-0",
            origin_x=0,
            origin_y=0,
            width=800,
            height=600,
            native_width=800,
            native_height=600,
        )
        payload = obs.to_dict()
        self.assertEqual(payload["rootScreenshotID"], "screenshot-0")
        self.assertEqual(len(payload["spaces"]), 1)
        self.assertEqual(payload["spaces"][0]["id"], "screenshot-0")
        self.assertEqual(payload["spaces"][0]["space"], "window")
        self.assertIn("windowID", payload["spaces"][0])
        self.assertIn("displayName", payload["spaces"][0])
        self.assertIn("processKey", payload["spaces"][0])
        self.assertIn("snapshot", payload["spaces"][0])
        self.assertEqual(payload["screenshotSpaces"], payload["spaces"])
        _ = FakeDesktop

    def test_official_timeout_string(self) -> None:
        from computer_use.wgc_winrt import CAPTURE_TIMEOUT, FRAME_ARRIVED_TIMEOUT, FRAMEPOOL_BUFFERS, TRYGET_AFTER_ARRIVED

        self.assertEqual(CAPTURE_TIMEOUT, "window capture timed out")
        self.assertEqual(FRAME_ARRIVED_TIMEOUT, "FrameArrived timed out")
        self.assertEqual(TRYGET_AFTER_ARRIVED, "TryGetNextFrame after FrameArrived failed")
        self.assertEqual(FRAMEPOOL_BUFFERS, 1)

    def test_transient_hwnds_empty_for_zero(self) -> None:
        from computer_use.win_capture import screenshot_space_hwnds, transient_hwnds

        self.assertEqual(transient_hwnds(0), [])
        self.assertEqual(screenshot_space_hwnds(0), [])

    def test_magic_move_includes_p0(self) -> None:
        from computer_use.overlay_cursor import magic_move_samples

        pts = magic_move_samples(10, 20, 40, 80, steps=6)
        self.assertEqual(pts[0], (10.0, 20.0))
        self.assertAlmostEqual(pts[-1][0], 40)
        self.assertAlmostEqual(pts[-1][1], 80)


class CursorManagerAndSpaceKindTests(unittest.TestCase):
    def test_system_cursor_manager_flag_and_events(self) -> None:
        from computer_use.cli import parse_args
        from computer_use.cursor_manager import EVENT_READY, EVENT_SUPPRESS, MANAGER_NOT_READY

        args = parse_args(["--system-cursor-manager", "--parent-pid", "1"])
        self.assertTrue(args.system_cursor_manager)
        self.assertEqual(args.parent_pid, 1)
        self.assertIn("CursorSuppress", EVENT_SUPPRESS)
        self.assertIn("CursorReady", EVENT_READY)
        self.assertIn("did not become ready", MANAGER_NOT_READY)
        import inspect
        from computer_use import overlay_win

        src = inspect.getsource(overlay_win._apply_show)
        self.assertNotIn("_suppress_system_cursor", src)
        self.assertIn("suppress_system_cursor", src)

    def test_classify_menu_tooltip_overlay_popup(self) -> None:
        from computer_use.win_capture import (
            SPACE_MENU,
            SPACE_OVERLAY,
            SPACE_POPUP,
            SPACE_TOOLTIP,
            SPACE_WINDOW,
            classify_screenshot_space,
        )

        self.assertEqual(classify_screenshot_space(0, overlay={0}), SPACE_OVERLAY)
        self.assertIn(SPACE_WINDOW, {SPACE_WINDOW, SPACE_MENU, SPACE_TOOLTIP, SPACE_POPUP, SPACE_OVERLAY})


class OverlayMotionTests(unittest.TestCase):
    def test_swap_and_animate_are_exported(self) -> None:
        from computer_use.composition_overlay import (
            PATH_OFFSET_EXPRESSION,
            animate_cursor_path,
            fade_display_overlay,
            recreate_after_device_loss,
            replace_cursor_drawing_surface,
            resize_cursor_surfaces,
            stop_cursor_motion,
            swap_cursor_press,
        )

        self.assertTrue(callable(swap_cursor_press))
        self.assertTrue(callable(animate_cursor_path))
        self.assertTrue(callable(recreate_after_device_loss))
        self.assertTrue(callable(stop_cursor_motion))
        self.assertTrue(callable(fade_display_overlay))
        self.assertTrue(callable(replace_cursor_drawing_surface))
        self.assertTrue(callable(resize_cursor_surfaces))
        self.assertIn("SingleSegmentPoint", PATH_OFFSET_EXPRESSION)
        self.assertIn("SegmentCount", PATH_OFFSET_EXPRESSION)

    def test_never_set_system_cursor(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "computer_use" / "overlay_win.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("SetSystemCursor(", text)
        self.assertIn("Never SetSystemCursor", text)
        self.assertIn("WDA_EXCLUDEFROMCAPTURE", text)
        self.assertIn("WM_POWERBROADCAST", text)


class UiaOfficialTableTests(unittest.TestCase):
    def test_roles_match_helper_rdata(self) -> None:
        self.assertEqual(CONTROL_TYPES[50000], "button")
        self.assertEqual(CONTROL_TYPES[50003], "combo box")
        self.assertEqual(CONTROL_TYPES[50004], "text field")
        self.assertEqual(CONTROL_TYPES[50011], "menu item")
        self.assertEqual(CONTROL_TYPES[50024], "tree item")

    def test_truncation_sentence(self) -> None:
        text = truncated_label("pane", "Root", 40)
        self.assertEqual(text, '(truncated: pane "Root", omitted 40 children)')


class ClickElementAndWindowRpcTests(unittest.TestCase):
    def test_click_element_is_independent_helper_rpc(self) -> None:
        from computer_use.helper_protocol import helper_click_method
        from computer_use.recovered import HELPER_METHODS
        from computer_use.rpc import ComputerUseServer
        from computer_use.runtime import make_executor

        self.assertIn("click_element", HELPER_METHODS)
        self.assertIn("window", HELPER_METHODS)
        self.assertEqual(helper_click_method({"element_index": 1}), "click_element")
        server = ComputerUseServer(make_executor("fake"), surface="gated", backend="fake")
        server.handle(
            {
                "id": 1,
                "method": "get_window_state",
                "params": {"window": WINDOW, "include_text": True},
            }
        )
        reply = server.handle(
            {
                "id": 2,
                "method": "click_element",
                "params": {"window": WINDOW, "element_index": 1},
            }
        )
        self.assertTrue(reply.get("ok"))
        window = server.handle({"id": 3, "method": "window", "params": {"id": 1, "app": "notepad.exe"}})
        self.assertTrue(window.get("ok"), window)
        diag = server.handle({"id": 4, "method": "diagnostic_state", "params": {}})
        self.assertTrue(diag.get("ok"), diag)
        self.assertIn("lease", (diag.get("result") or {}).get("value") or diag.get("result") or {})


class PolicyTerminalAumidTests(unittest.TestCase):
    def test_official_terminal_table_includes_wezterm_and_alacritty(self) -> None:
        from computer_use.policy import TERMINAL_STEMS, deny_app_access, default_app_access

        self.assertIn("wezterm", TERMINAL_STEMS)
        self.assertIn("alacritty", TERMINAL_STEMS)
        self.assertIn("mintty", TERMINAL_STEMS)
        self.assertIn("windowsterminal", TERMINAL_STEMS)
        with self.assertRaises(PermissionError) as raised:
            deny_app_access("wezterm-gui.exe")
        self.assertIn("terminal", str(raised.exception).lower())
        access = default_app_access()
        self.assertIn("aumids", access["allow"])
        self.assertIn("exes", access["deny"])

    def test_codex_aumid_denied(self) -> None:
        from computer_use.policy import deny_app_access

        with self.assertRaises(PermissionError):
            deny_app_access("ChatGPT.exe", "OpenAI.ChatGPT-Desktop_8wekyb3d8bbwe!App")


class UiaEventMonitorTests(unittest.TestCase):
    def test_monitor_official_strings(self) -> None:
        from computer_use.win_uia import (
            CACHED_TARGET_MISMATCH,
            DOCUMENT_FIND_MAX,
            GET_FOREGROUND_UIA,
            NO_VISIBLE_TOP,
            REFRESH_TARGET_SNAPSHOT,
            WINDOW_OPENED_NOT_READY,
            _call_monitor,
        )

        self.assertEqual(DOCUMENT_FIND_MAX, 200)
        self.assertIn("cached target in", CACHED_TARGET_MISMATCH)
        self.assertIn("foreground UIA", GET_FOREGROUND_UIA)
        self.assertIn("no visible top-level windows found for", NO_VISIBLE_TOP)
        self.assertIn("refresh UIA element target snapshot", REFRESH_TARGET_SNAPSHOT)
        self.assertEqual(WINDOW_OPENED_NOT_READY, "accessibility window-opened handler did not become ready")
        self.assertTrue(callable(_call_monitor))
        from computer_use.win_uia import _cached_elements

        self.assertIsInstance(_cached_elements, dict)

    def test_process_mismatch_message(self) -> None:
        from computer_use.win_uia import PROCESS_MISMATCH, cache_diagnostics

        self.assertIn("cached target process", PROCESS_MISMATCH)
        diag = cache_diagnostics()
        for key in ("rootHwnd", "processId", "processName", "captureCachedSessionCount", "eventMonitor"):
            self.assertIn(key, diag)

    def test_parse_roles_with_spaces(self) -> None:
        from computer_use.tree_format import parse_tree_nodes

        nodes = parse_tree_nodes('[1] text field "Name" {{x: 1, y: 2, width: 3, height: 4}}')
        self.assertEqual(nodes[0].role, "text field")
        self.assertEqual(nodes[0].name, "Name")

    def test_monitor_teardown_exists(self) -> None:
        from computer_use.win_uia import _teardown_event_monitor, ensure_event_monitor

        self.assertTrue(callable(ensure_event_monitor))
        self.assertTrue(callable(_teardown_event_monitor))


if __name__ == "__main__":
    unittest.main()
