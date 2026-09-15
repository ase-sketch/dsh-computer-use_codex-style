from __future__ import annotations

from typing import Any

from computer_use.args import optional_str, require_text, window_from_spec
from computer_use.data_url import decode_data_url
from computer_use.approval import ApprovalGate
from computer_use.errors import DesktopUnavailable
from computer_use.helper_client import HelperClient
from computer_use.helper_protocol import APPROVED_APP_META_KEY, click_params, scroll_params
from computer_use.models import ActionRecord, AppInfo, Observation, WindowRef
from computer_use.png import solid_png
from computer_use.tree_format import parse_tree_nodes


def window_dict(spec: dict[str, object]) -> dict[str, Any]:
    hinted = window_from_spec(spec)
    if hinted is None:
        raise TypeError("window.app must be a non-empty string and window.id must be an integer >= 0")
    return hinted.to_dict()


def app_from_helper(raw: dict[str, Any]) -> AppInfo:
    windows = [
        WindowRef(app=str(item.get("app") or raw.get("id") or ""), id=int(item.get("id") or 0), title=str(item.get("title") or ""))
        for item in (raw.get("windows") or [])
        if isinstance(item, dict)
    ]
    count = raw.get("useCount")
    return AppInfo(
        id=str(raw.get("id") or ""),
        display_name=str(raw.get("displayName") or raw.get("id") or ""),
        is_running=bool(raw.get("isRunning", True)),
        windows=windows,
        last_used_date=str(raw["lastUsedDate"]) if raw.get("lastUsedDate") else None,
        use_count=int(count) if isinstance(count, int) else None,
    )


class OfficialHelperDesktop:
    """Live backend that is the local Codex helper, not a ctypes reimplementation."""

    def __init__(self, client: HelperClient | None = None, approval: ApprovalGate | None = None) -> None:
        self.client = client or HelperClient()
        self.approval = approval or ApprovalGate()
        self.actions: list[ActionRecord] = []

    def list_apps(self) -> list[AppInfo]:
        result = self._rpc("list_apps", {})
        return [app_from_helper(item) for item in result if isinstance(item, dict)]

    def list_windows(self) -> list[WindowRef]:
        result = self._rpc("list_windows", {})
        if not isinstance(result, list):
            return [window for app in self.list_apps() for window in app.windows]
        return [
            WindowRef(app=str(item.get("app") or ""), id=int(item.get("id") or 0), title=str(item.get("title") or ""))
            for item in result
            if isinstance(item, dict)
        ]

    def get_window(self, spec: dict[str, object]) -> WindowRef:
        raw = self._rpc("get_window", window_dict(spec) if "id" not in spec else {"id": spec.get("id"), "app": spec.get("app")})
        if not isinstance(raw, dict):
            raise DesktopUnavailable("helper did not return a window")
        return WindowRef(app=str(raw.get("app") or ""), id=int(raw.get("id") or 0), title=str(raw.get("title") or ""))

    def launch_app(self, spec: dict[str, object]) -> ActionRecord:
        self._rpc("launch_app", {"app": require_text(spec, "app")})
        return self._store("launch_app", {"app": spec.get("app")})

    def activate_window(self, spec: dict[str, object]) -> ActionRecord:
        window = window_dict(spec)
        self._rpc("activate_window", {"window": window})
        return self._store("activate_window", {"window": window})

    def observe(self, spec: dict[str, object]) -> Observation:
        window = window_dict(spec)
        include_shot = spec.get("include_screenshot", True) is not False
        include_text = spec.get("include_text", False) is True
        state = self._rpc("get_window_state", {"window": window, "include_screenshot": include_shot, "include_text": include_text})
        if not isinstance(state, dict):
            raise DesktopUnavailable("helper did not return window state")
        return observation_from_state(state, include_shot, include_text)

    def click(self, spec: dict[str, object]) -> ActionRecord:
        method, params = click_params(window_dict(spec), spec)
        self._rpc(method, params)
        return self._store(method, dict(spec))

    def type_text(self, spec: dict[str, object]) -> ActionRecord:
        self._rpc("type_text", {"window": window_dict(spec), "text": require_text(spec, "text")})
        return self._store("type_text", {"text": spec.get("text")})

    def press_key(self, spec: dict[str, object]) -> ActionRecord:
        self._rpc("press_key", {"window": window_dict(spec), "key": require_text(spec, "key")})
        return self._store("press_key", {"key": spec.get("key")})

    def scroll(self, spec: dict[str, object]) -> ActionRecord:
        method, params = scroll_params(window_dict(spec), spec)
        self._rpc(method, params)
        return self._store(method, params)

    def scroll_element(self, spec: dict[str, object]) -> ActionRecord:
        method, params = scroll_params(window_dict(spec), spec)
        self._rpc(method, params)
        return self._store(method, params)

    def diagnostic_state(self) -> Any:
        return self._rpc("diagnostic_state", {})

    def start_audio_recording(self, spec: dict[str, object] | None = None) -> Any:
        return self._rpc("start_audio_recording", spec or {})

    def stop_audio_recording(self, spec: dict[str, object] | None = None) -> Any:
        return self._rpc("stop_audio_recording", spec or {})

    def drag(self, spec: dict[str, object]) -> ActionRecord:
        params = {"window": window_dict(spec), "from_x": spec.get("from_x"), "from_y": spec.get("from_y"), "to_x": spec.get("to_x"), "to_y": spec.get("to_y")}
        self._rpc("drag", params)
        return self._store("drag", params)

    def set_value(self, spec: dict[str, object]) -> ActionRecord:
        params = {"window": window_dict(spec), "element_index": spec.get("element_index"), "value": spec.get("value")}
        self._rpc("set_value", params)
        return self._store("set_value", params)

    def perform_secondary_action(self, spec: dict[str, object]) -> ActionRecord:
        params = {"window": window_dict(spec), "element_index": spec.get("element_index"), "action": spec.get("action")}
        self._rpc("perform_secondary_action", params)
        return self._store("perform_secondary_action", params)

    def close(self) -> None:
        self.client.close()

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        result = self.client.request(method, params)
        if isinstance(result, dict) and "approvalRequest" in result:
            raw = result["approvalRequest"]
            if not isinstance(raw, dict):
                raise DesktopUnavailable("invalid approvalRequest")
            request = self.approval.from_helper(raw)
            self.approval.ensure(request.app, request.display_name)
            return self.client.request(method, params, extra_meta={APPROVED_APP_META_KEY: request.app})
        return result

    def end_turn(self, session_id: str = "local", turn_id: str = "turn") -> dict[str, Any]:
        from computer_use.turn import signal_turn_ended, turn_ended_payload

        try:
            self.client.request("end_turn", {})
        except DesktopUnavailable:
            pass
        signal_turn_ended(session_id)
        self.close()
        return turn_ended_payload(session_id, turn_id)

    def _store(self, kind: str, payload: dict[str, Any]) -> ActionRecord:
        record = ActionRecord(kind, payload)
        self.actions.append(record)
        return record


def observation_from_state(state: dict[str, Any], include_shot: bool, include_text: bool) -> Observation:
    raw_window = state.get("window") if isinstance(state.get("window"), dict) else {}
    window = WindowRef(app=str(raw_window.get("app") or ""), id=int(raw_window.get("id") or 0), title=str(raw_window.get("title") or ""))
    shots = state.get("screenshots") if isinstance(state.get("screenshots"), list) else []
    png, mime, origin_x, origin_y, width, height, shot_id = solid_png(), "image/png", 0, 0, 0, 0, "screenshot-0"
    if include_shot and shots and isinstance(shots[0], dict):
        png, mime = decode_data_url(str(shots[0].get("url") or ""))
        origin_x = int(shots[0].get("originX") or 0)
        origin_y = int(shots[0].get("originY") or 0)
        width = int(shots[0].get("width") or 0)
        height = int(shots[0].get("height") or 0)
        shot_id = str(shots[0].get("id") or "screenshot-0")
    acc = state.get("accessibility") if isinstance(state.get("accessibility"), dict) else None
    tree_text = str((acc or {}).get("tree") or "")
    nodes = parse_tree_nodes(tree_text) if include_text else []
    return Observation(
        screenshot=png,
        mime_type=mime,
        tree=nodes,
        window=window,
        tree_text=tree_text,
        focused_element=str((acc or {}).get("focused_element") or ""),
        selected_text=str((acc or {}).get("selected_text") or ""),
        include_screenshot=include_shot,
        include_text=include_text,
        screenshot_id=shot_id,
        origin_x=origin_x,
        origin_y=origin_y,
        width=width,
        height=height,
    )
