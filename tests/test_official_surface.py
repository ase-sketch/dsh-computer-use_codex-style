from __future__ import annotations

import ctypes
import json
import struct
import unittest

from computer_use.browser_official import OFFICIAL_COMMANDS, resolve_official
from computer_use.helper_pipe import (
    MAX_INBOUND_FRAME_BYTES,
    decode_pipe_frame,
    encode_pipe_frame,
)
from computer_use.overlay_cursor import (
    cubic_bezier,
    magic_move_samples,
    p0_p6_samples,
    resample_p0_p6,
    sampled_poses,
    scoot_pose,
    step_cursor,
)
from computer_use.pipe_server import handle_pipe_payload
from computer_use.browser_api import BrowserSurface
from computer_use.surfaces import tools_for_surface


class OfficialBrowserCommandTests(unittest.TestCase):
    def test_official_command_count(self) -> None:
        self.assertGreaterEqual(len(OFFICIAL_COMMANDS), 56)
        self.assertEqual(resolve_official("create_tab"), "tab_new")
        self.assertEqual(resolve_official("cua_click"), "tab_cua_click")
        # BR-13: browser_user_claim_tab keeps its own official wire shape and is
        # dispatched by BrowserSurface (it no longer collapses onto browser_claim_tab).
        self.assertEqual(resolve_official("browser_user_claim_tab"), "browser_user_claim_tab")

    def test_browser_surface_registers_official_names(self) -> None:
        names = [item["function"]["name"] for item in tools_for_surface("browser")]
        self.assertIn("create_tab", names)
        self.assertNotIn("tab_new", names)
        self.assertIn("playwright_locator_fill", names)
        self.assertIn("browser_setup", names)
        self.assertNotIn("list_windows", names)
        self.assertNotIn("start_audio_recording", names)

    def test_browser_setup_rejects_invalid_environment(self) -> None:
        surface = BrowserSurface()
        with self.assertRaises(ValueError):
            surface.setup("desktop")
        ok = surface.setup("codex-app")
        self.assertEqual(ok["environment"], "codex-app")
        self.assertEqual(ok["disabledMemberIds"], [])
        training = surface.setup("training")
        self.assertIn("browser_user_claim_tab", training["disabledMemberIds"])
        with self.assertRaises(PermissionError):
            surface.dispatch("browser_user_claim_tab", {"providerTabId": "1", "title": "t", "url": "https://x"})


class NativePipeFrameTests(unittest.TestCase):
    def test_roundtrip_jsonrpc_envelope(self) -> None:
        frame = encode_pipe_frame(3, "list_windows", {})
        self.assertEqual(frame[:4], struct.pack("<I", len(frame) - 4))
        payload, rest = decode_pipe_frame(frame)
        self.assertEqual(rest, b"")
        self.assertEqual(payload["jsonrpc"], "2.0")
        self.assertEqual(payload["params"]["method"], "list_windows")

    def test_inbound_oversize_rejected(self) -> None:
        huge = struct.pack("<I", MAX_INBOUND_FRAME_BYTES + 1) + b"x"
        with self.assertRaises(ValueError):
            decode_pipe_frame(huge)

    def test_handle_request_envelope(self) -> None:
        calls = []

        def dispatch(name, params):
            calls.append((name, params))
            return {"ok": True}

        payload = json.loads(encode_pipe_frame(1, "click", {"x": 1})[4:])
        raw = handle_pipe_payload(payload, dispatch)
        body = json.loads(raw[4:])
        self.assertEqual(calls[0][0], "click")
        self.assertEqual(body["result"]["ok"], True)


class OverlayCursorTests(unittest.TestCase):
    def test_scoot_pose_fields(self) -> None:
        pose = scoot_pose(40, 0, press=True)
        self.assertIn("scootTiltDegrees", pose)
        self.assertIn("baseRotationDegrees", pose)
        self.assertLess(pose["scaleX"], 1.0)

    def test_step_cursor_moves_toward_target(self) -> None:
        x, y, pose = step_cursor(0, 0, 100, 0)
        self.assertGreater(x, 0)
        self.assertLess(x, 100)
        self.assertIn("stretchAxisDegrees", pose)

    def test_magic_move_samples_end_at_target(self) -> None:
        points = magic_move_samples(0, 0, 100, 40, steps=8)
        self.assertEqual(len(points), 9)
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertAlmostEqual(points[-1][0], 100)
        self.assertAlmostEqual(points[-1][1], 40)

    def test_sampled_poses_press_only_on_last(self) -> None:
        frames = sampled_poses(0, 0, 80, 0, press=True, steps=6)
        self.assertTrue(all(frame[2]["press"] == 0.0 for frame in frames[:-1]))
        self.assertEqual(frames[-1][2]["press"], 1.0)
        self.assertLess(frames[-1][2]["scaleX"], 1.0)

    def test_p0_p6_and_cubic_bezier(self) -> None:
        pts = p0_p6_samples(0, 0, 100, 0)
        self.assertEqual(len(pts), 7)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertAlmostEqual(pts[-1][0], 100)
        mid = cubic_bezier(pts[0], pts[1], pts[2], pts[3], 0.5)
        self.assertGreater(mid[0], 0)
        self.assertLess(mid[0], 100)
        padded = resample_p0_p6([(1.0, 2.0)])
        self.assertEqual(len(padded), 7)
        self.assertEqual(padded[-1], (1.0, 2.0))


class OverlayOfficialChromeTests(unittest.TestCase):
    def test_banner_branding_and_accessible_name(self) -> None:
        from computer_use.overlay import ACCESSIBLE_NAME, BANNER, ESC_HINT, OverlayStrings, parse_hex_color, pick_ink_color

        self.assertEqual(ESC_HINT, "Esc to cancel")
        self.assertIn("DeepSeek Harness", BANNER)
        self.assertNotIn("Codex", BANNER)
        self.assertNotIn("ChatGPT", BANNER)
        self.assertEqual(ACCESSIBLE_NAME, "dsh-computer-use-status-pill")
        self.assertNotIn("codex", ACCESSIBLE_NAME)
        strings = OverlayStrings()
        self.assertEqual(strings.using_computer, BANNER)
        self.assertEqual(strings.esc_to_cancel, ESC_HINT)
        color = parse_hex_color("#FFC400")
        self.assertIsNotNone(color)
        self.assertAlmostEqual(color[0], 1.0)
        self.assertIsNone(parse_hex_color("ffc400"))
        ink = pick_ink_color(color)
        self.assertLess(ink[0], 0.2)

    def test_pill_layout_is_centered(self) -> None:
        from computer_use.overlay import BANNER, ESC_HINT, compute_pill_layout

        layout = compute_pill_layout(1920, 1080, BANNER, ESC_HINT)
        self.assertGreater(layout["x"], 200)
        self.assertLess(layout["x"] + layout["width"], 1920)
        self.assertAlmostEqual(layout["x"] + layout["width"] / 2.0, 960, delta=1.0)
        self.assertEqual(layout["height"], 36)
        self.assertGreater(layout["separator_x"], layout["status_x"])

    def test_path_expression_matches_rdata(self) -> None:
        from computer_use.composition_overlay import (
            FIRST_HALF_POINT_EXPRESSION,
            PATH_OFFSET_EXPRESSION,
            SECOND_HALF_POINT_EXPRESSION,
            SHIMMER_OFFSET_EXPRESSION,
            is_device_lost,
            stop_cursor_motion,
        )

        self.assertIn("SingleSegmentPoint", PATH_OFFSET_EXPRESSION)
        self.assertIn("FirstHalfPoint", PATH_OFFSET_EXPRESSION)
        self.assertIn("SecondHalfPoint", PATH_OFFSET_EXPRESSION)
        self.assertIn("motion.P0", FIRST_HALF_POINT_EXPRESSION)
        self.assertIn("3.0*", FIRST_HALF_POINT_EXPRESSION)
        self.assertIn("motion.P6", SECOND_HALF_POINT_EXPRESSION)
        self.assertIn("shimmer.TravelX", SHIMMER_OFFSET_EXPRESSION)
        self.assertTrue(is_device_lost(0x887A0005))
        # COM HRESULT as signed int32. Official code is 0x887A0005; subagent test typo was -2004320251.
        self.assertEqual(ctypes.c_int32(0x887A0005).value, -2005270523)
        self.assertTrue(is_device_lost(-2005270523))
        self.assertFalse(is_device_lost(-2004320251))
        self.assertFalse(is_device_lost(0))
        self.assertTrue(callable(stop_cursor_motion))

    def test_force_warp_env(self) -> None:
        import os

        from computer_use.composition_overlay import force_cursor_warp

        os.environ.pop("DSH_CUA_CURSOR_FORCE_WARP", None)
        os.environ.pop("CODEX_CUA_CURSOR_FORCE_WARP", None)
        self.assertFalse(force_cursor_warp())
        os.environ["DSH_CUA_CURSOR_FORCE_WARP"] = "true"
        try:
            self.assertTrue(force_cursor_warp())
        finally:
            os.environ.pop("DSH_CUA_CURSOR_FORCE_WARP", None)


if __name__ == "__main__":
    unittest.main()
