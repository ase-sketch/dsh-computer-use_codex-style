from __future__ import annotations

import json
import unittest

from computer_use.data_url import decode_data_url
from computer_use.helper_backend import app_from_helper, observation_from_state
from computer_use.helper_locate import locate_codex_cli, locate_helper
from computer_use.helper_protocol import click_params, encode_request, helper_click_method
from computer_use.png import solid_png
from computer_use.tree_format import parse_tree_nodes


class HelperProtocolTests(unittest.TestCase):
    def test_encode_request_is_json_line(self) -> None:
        line = encode_request(3, "list_apps", {})
        self.assertTrue(line.endswith("\n"))
        payload = json.loads(line)
        self.assertEqual(payload["id"], 3)
        self.assertEqual(payload["method"], "list_apps")
        self.assertIn("x-oai-cua-request-budget-ms", payload["meta"])

    def test_click_element_mapping(self) -> None:
        self.assertEqual(helper_click_method({"element_index": 4}), "click_element")
        method, params = click_params({"app": "MSEdge", "id": 1}, {"element_index": 4, "click_count": 2})
        self.assertEqual(method, "click_element")
        self.assertEqual(params["element_index"], 4)
        self.assertEqual(params["click_count"], 2)
        method, params = click_params({"app": "MSEdge", "id": 1}, {"x": 10, "y": 20, "screenshotId": "screenshot-0"})
        self.assertEqual(method, "click")
        self.assertEqual(params["screenshotId"], "screenshot-0")

    def test_observation_from_helper_state(self) -> None:
        png = solid_png()
        import base64

        url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        state = {
            "window": {"app": "MSEdge", "id": 9, "title": "Edge"},
            "screenshots": [{"id": "screenshot-3", "zIndex": 0, "url": url, "originX": 10, "originY": 20, "width": 64, "height": 48}],
            "accessibility": {"tree": '[1] Button "OK" {{x: 1, y: 2, width: 3, height: 4}}'},
        }
        obs = observation_from_state(state, True, True).to_dict()
        self.assertEqual(obs["window"]["app"], "MSEdge")
        self.assertEqual(obs["screenshots"][0]["id"], "screenshot-3")
        self.assertEqual(obs["tree"][0]["name"], "OK")
        raw, mime = decode_data_url(url)
        self.assertEqual(mime, "image/png")
        self.assertTrue(raw.startswith(b"\x89PNG"))

    def test_app_catalog_fields(self) -> None:
        app = app_from_helper(
            {
                "id": "MSEdge",
                "displayName": "Microsoft Edge",
                "isRunning": True,
                "lastUsedDate": "2026-09-10",
                "useCount": 4,
                "windows": [{"app": "MSEdge", "id": 1, "title": "a"}],
            }
        ).to_dict()
        self.assertEqual(app["useCount"], 4)
        self.assertEqual(app["lastUsedDate"], "2026-09-10")

    def test_parse_tree_and_locate_helper(self) -> None:
        nodes = parse_tree_nodes('[0] Window "X" {{x: 0, y: 0, width: 8, height: 8}}\n  [1] Edit "Y" {{x: 1, y: 1, width: 2, height: 2}}')
        self.assertEqual(nodes[1].name, "Y")
        self.assertEqual(nodes[1].depth, 1)
        # The DSH native helper is the preferred target; the official
        # codex-computer-use.exe is only the fallback when it is absent.
        helper = locate_helper()
        self.assertTrue(
            helper is None or helper.name in {"dsh-computer-use.exe", "codex-computer-use.exe"},
            f"unexpected helper target: {helper}",
        )
        if helper is not None and helper.name == "dsh-computer-use.exe":
            # The DSH helper must actually be the release binary we build.
            self.assertIn("helper-rs", str(helper))
        cli = locate_codex_cli()
        self.assertTrue(cli is None or cli.name == "codex.exe")


class HelperApprovalRetryTests(unittest.TestCase):
    def test_retries_with_approved_app_meta(self) -> None:
        from computer_use.helper_backend import OfficialHelperDesktop
        from computer_use.helper_protocol import APPROVED_APP_META_KEY

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def request(self, method, params=None, extra_meta=None):
                self.calls.append(extra_meta)
                if extra_meta and extra_meta.get(APPROVED_APP_META_KEY):
                    return [{"id": "MSEdge", "displayName": "Edge", "windows": []}]
                return {"approvalRequest": {"app": "MSEdge", "displayName": "Edge", "allowPersistentApproval": True}}

            def close(self) -> None:
                return None

        client = FakeClient()
        apps = OfficialHelperDesktop(client=client).list_apps()
        self.assertEqual(apps[0].id, "MSEdge")
        self.assertEqual(client.calls[1][APPROVED_APP_META_KEY], "MSEdge")


class HelperLiveTests(unittest.TestCase):
    def test_official_helper_list_apps(self) -> None:
        from computer_use.errors import DesktopUnavailable
        from computer_use.helper_client import HelperClient
        from computer_use.helper_locate import locate_codex_cli, locate_helper

        if locate_helper() is None or locate_codex_cli() is None:
            self.skipTest("official helper or CODEX_CLI_PATH missing")
        client = HelperClient(timeout_ms=25000)
        try:
            result = client.request("list_apps", {})
        except DesktopUnavailable as exc:
            self.skipTest(str(exc))
        finally:
            client.close()
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)
        self.assertIn("id", result[0])
        self.assertIn("windows", result[0])


if __name__ == "__main__":
    unittest.main()
