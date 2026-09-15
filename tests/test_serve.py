from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from computer_use.images import detach_images
from computer_use.png import decode_png, downscale_png, encode_png, solid_png
from computer_use.rpc import ComputerUseServer, dsh_tool_list
from computer_use.runtime import make_executor

ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\n"
WINDOW = {"app": "notepad.exe", "id": 1, "title": "Untitled - Notepad"}


class ImageDetachTests(unittest.TestCase):
    def test_roundtrip_png_decode(self) -> None:
        png = solid_png(32, 16)
        width, height, rgba = decode_png(png)
        self.assertEqual((width, height), (32, 16))
        self.assertEqual(len(rgba), 32 * 16 * 4)
        self.assertEqual(encode_png(width, height, rgba)[:8], PNG)

    def test_downscale_long_edge(self) -> None:
        png = solid_png(200, 100)
        small = downscale_png(png, max_edge=50)
        width, height, _rgba = decode_png(small)
        self.assertEqual(width, 50)
        self.assertEqual(height, 25)

    def test_detach_strips_data_url_and_keeps_id(self) -> None:
        png = solid_png()
        payload = {
            "result": {
                "screenshots": [
                    {
                        "id": "screenshot-0",
                        "url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                        "width": 64,
                        "height": 48,
                    }
                ],
                "screenshot_base64": base64.b64encode(png).decode("ascii"),
            }
        }
        value, images = detach_images(payload)
        self.assertEqual(value["result"]["screenshots"][0]["id"], "screenshot-0")
        self.assertEqual(value["result"]["screenshots"][0]["url"], "")
        self.assertEqual(value["result"]["screenshot_base64"], "")
        self.assertGreaterEqual(len(images), 1)
        raw = base64.b64decode(images[0]["data"])
        self.assertTrue(raw.startswith(PNG))
        self.assertEqual(images[0]["mimeType"], "image/png")


class RpcServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ComputerUseServer(make_executor("fake"), surface="desktop", backend="fake")

    def test_health_does_not_require_codex(self) -> None:
        reply = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "health"})
        health = reply["result"]
        self.assertFalse(health["codexRequired"])
        self.assertEqual(health["resolved"], "fake")

    def test_interrupt_trips_flag(self) -> None:
        reply = self.server.handle({"jsonrpc": "2.0", "id": 9, "method": "interrupt"})
        self.assertTrue(reply["result"]["stopped"])
        self.assertTrue(self.server.executor.driver.interrupt.stopped)

    def test_windows_backend_uses_dsh_overlay_not_helper(self) -> None:
        from computer_use.rpc import backend_health

        health = backend_health("windows")
        self.assertEqual(health["resolved"], "windows")
        self.assertEqual(health["overlay"], "dsh")
        self.assertFalse(health["codexRequired"])
        live = backend_health("live")
        self.assertEqual(live["resolved"], "windows")
        self.assertEqual(live["overlay"], "dsh")

    def test_tools_include_window2_and_browser(self) -> None:
        computer = [item["name"] for item in dsh_tool_list("gated")]
        self.assertIn("list_windows", computer)
        self.assertIn("get_window_state", computer)
        self.assertIn("batch_actions", computer)
        self.assertNotIn("tab_goto", computer)
        self.assertNotIn("create_tab", computer)
        browser = [item["name"] for item in dsh_tool_list("browser")]
        self.assertIn("create_tab", browser)
        self.assertNotIn("list_windows", browser)
        self.assertNotIn("tab_new", browser)

    def test_get_window_state_returns_images_without_inline_bytes(self) -> None:
        reply = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "call",
                "params": {"name": "get_window_state", "arguments": {"window": WINDOW}},
            }
        )
        result = reply["result"]
        dumped = json.dumps(result["value"])
        self.assertNotIn("data:image", dumped)
        self.assertTrue(result["images"])
        raw = base64.b64decode(result["images"][0]["data"])
        self.assertTrue(raw.startswith(PNG))

    def test_list_windows_ok(self) -> None:
        reply = self.server.handle({"jsonrpc": "2.0", "id": 3, "method": "call", "params": {"name": "list_windows"}})
        windows = reply["result"]["value"]
        if isinstance(windows, dict):
            windows = windows.get("result") or windows
        self.assertEqual(windows[0]["id"], 1)

    def test_click_is_void_without_auto_screenshot(self) -> None:
        self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "call",
                "params": {"name": "get_window_state", "arguments": {"window": WINDOW}},
            }
        )
        reply = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "call",
                "params": {"name": "click", "arguments": {"window": WINDOW, "element_index": 1}},
            }
        )
        result = reply["result"]
        self.assertIsNone(result["value"])
        self.assertFalse(result.get("images"))


class ServeCliTests(unittest.TestCase):
    def test_stdio_health_and_shutdown(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "computer_use", "--backend", "fake", "--surface", "computer", "serve"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health"}) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}) + "\n")
        proc.stdin.close()
        out, err = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 0, err)
        lines = [json.loads(line) for line in out.splitlines() if line.strip()]
        self.assertEqual(lines[0]["result"]["resolved"], "fake")
        self.assertTrue(lines[1]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
