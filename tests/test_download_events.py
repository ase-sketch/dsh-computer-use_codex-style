from __future__ import annotations

import http.server
import threading
import unittest
from pathlib import Path

from computer_use.driver import ComputerUse
from computer_use.executor import ToolExecutor
from computer_use.fake_backend import FakeDesktop
from computer_use.helper_pipe import decode_pipe_frame, encode_pipe_frame, list_computer_use_pipes


class DownloadEventTests(unittest.TestCase):
    def test_fake_download_object_fields(self) -> None:
        ex = ToolExecutor(ComputerUse(FakeDesktop()))
        tab = ex.execute("tab_new", {"url": "https://example.com/"})["result"]
        media = ex.execute("tab_dom_download_media", {"tab_id": tab["id"], "node_id": 2})["result"]
        path = Path(str(media["download"]["path"]))
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 0)
        self.assertEqual(
            ex.execute("tab_pw_download_suggested_filename", {"tab_id": tab["id"]})["result"]["suggestedFilename"],
            media["download"]["suggestedFilename"],
        )
        self.assertIn("example.com", ex.execute("tab_pw_download_url", {"tab_id": tab["id"]})["result"]["url"])
        self.assertIsNone(ex.execute("tab_pw_download_failure", {"tab_id": tab["id"]})["result"]["failure"])
        self.assertEqual(ex.execute("tab_pw_download_path", {"tab_id": tab["id"]})["result"]["path"], str(path))

    def test_pipe_discover_is_list(self) -> None:
        pipes = list_computer_use_pipes()
        self.assertIsInstance(pipes, list)
        frame = encode_pipe_frame(1, "list_apps", {})
        msg, rest = decode_pipe_frame(frame)
        self.assertEqual(rest, b"")
        self.assertEqual(msg["params"]["method"], "list_apps")

    def test_live_cdp_attachment_download(self) -> None:
        import tempfile
        from computer_use.cdp_browser import CdpBrowser
        from computer_use.cdp_launch import edge_exe, launch_edge
        from computer_use.png import solid_png

        if edge_exe() is None:
            self.skipTest("msedge.exe not found")
        root = Path(tempfile.mkdtemp()) / "dl"
        root.mkdir()
        payload = b"hello-download-bytes"
        (root / "hello.bin").write_bytes(payload)
        (root / "index.html").write_text(
            '<html><body><a id="dl" href="/hello.bin" download="hello.bin">get</a></body></html>',
            encoding="utf-8",
        )

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, *_args) -> None:
                return None

            def end_headers(self) -> None:
                if self.path.endswith(".bin"):
                    self.send_header("Content-Disposition", 'attachment; filename="hello.bin"')
                super().end_headers()

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        page = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
        proc = None
        browser = None
        try:
            proc = launch_edge(9336, Path(tempfile.mkdtemp()) / "edge-dl")
            browser = CdpBrowser(port=9336)
            tab = browser.new_tab(page)
            result = browser.download_media(tab.id, node_id=1)
            path = Path(str(result["download"]["path"]))
            self.assertTrue(path.is_file(), msg=str(result))
            self.assertGreater(path.stat().st_size, 0)
            self.assertTrue(result["download"].get("suggestedFilename"))
            self.assertTrue(result["download"].get("url"))
            from computer_use.browser_api import BrowserSurface

            surface = BrowserSurface(browser)
            stored = surface.dispatch("tab_pw_download_path", {"tab_id": tab.id})
            self.assertEqual(stored.get("path"), str(path))
            self.assertEqual(surface.dispatch("tab_pw_download_suggested_filename", {"tab_id": tab.id}).get("suggestedFilename"), result["download"]["suggestedFilename"])
        except (FileNotFoundError, TimeoutError, OSError, RuntimeError) as exc:
            self.skipTest(str(exc))
        finally:
            httpd.shutdown()
            if browser is not None:
                browser.close()
            if proc is not None:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
