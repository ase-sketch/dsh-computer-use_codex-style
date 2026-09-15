from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from computer_use.executor import ToolExecutor
from computer_use.loop import latest_observation

PROMPTS = Path(__file__).with_name("prompts")
PROMPT_FILES = (
    "SKILL.md",
    "guidance.md",
    "confirmations.md",
    "api.md",
    "harness.md",
    "sky-window-api.md",
    "browser-accessibility.md",
    "browser-api-use.md",
    "browser-visibility.md",
    "tab-mentions-iab.md",
    "tab-claiming-chrome.md",
)


def system_prompt() -> str:
    chunks = [(PROMPTS / name).read_text(encoding="utf-8") for name in PROMPT_FILES]
    return "\n\n".join(chunks)


class SkyHarness:
    """Official initialize + two-cell observe/act loop over window2 tools."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor
        self.apps: list[dict[str, Any]] = []
        self.target_app: dict[str, Any] | None = None
        self.target_window: dict[str, Any] | None = None
        self.state: dict[str, Any] | None = None

    def initialize(self, app_id: str, title_hint: str | None = None) -> dict[str, Any]:
        self.apps = list(self.executor.execute("list_apps", {})["result"])
        app = self._find_app(app_id)
        if app is None:
            self.executor.execute("launch_app", {"app": app_id})
            self.apps = list(self.executor.execute("list_apps", {})["result"])
            app = self._find_app(app_id)
        if app is None:
            raise LookupError(f"Target app was not returned by list_apps: {app_id}")
        self.target_app = app
        windows = list(app.get("windows") or [])
        if not windows:
            self.executor.execute("launch_app", {"app": app["id"]})
            self.apps = list(self.executor.execute("list_apps", {})["result"])
            self.target_app = self._find_app(app["id"])
            windows = list((self.target_app or {}).get("windows") or [])
        if title_hint:
            windows = [w for w in windows if str(w.get("title") or "") == title_hint]
        if len(windows) != 1:
            raise RuntimeError(f"Expected exactly one target window for {app_id}; found {len(windows)}")
        self.target_window = self.executor.execute("get_window", {"id": windows[0]["id"], "app": windows[0]["app"]})["result"]
        self.executor.execute("activate_window", {"window": self.target_window})
        self.state = self.observe()
        return self.state

    def observe(self, include_screenshot: bool = True, include_text: bool = False) -> dict[str, Any]:
        if self.target_window is None:
            raise RuntimeError("initialize a target window first")
        payload = self.executor.execute(
            "get_window_state",
            {
                "window": self.target_window,
                "include_screenshot": include_screenshot,
                "include_text": include_text,
            },
        )
        self.state = payload["result"]
        self.target_window = self.state["window"]
        return self.state

    def act_and_refresh(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self.target_window is None or self.state is None:
            raise RuntimeError("observe before acting")
        args = dict(arguments)
        args.setdefault("window", self.state["window"])
        if "x" in args or "y" in args or "from_x" in args:
            shots = self.state.get("screenshots") or []
            if shots and "screenshotId" not in args:
                args["screenshotId"] = shots[0]["id"]
        action = self.executor.execute(name, args)
        self.state = self.observe(include_screenshot=True, include_text=True)
        return {"action": action, "state": self.state}

    def _find_app(self, app_id: str) -> dict[str, Any] | None:
        needle = app_id.lower()
        for app in self.apps:
            blob = f"{app.get('id', '')} {app.get('displayName', '')}".lower()
            if needle in blob:
                return app
        return None


def run_official_sequence(executor: ToolExecutor, app_id: str, calls: list[Mapping[str, Any]]) -> dict[str, Any]:
    harness = SkyHarness(executor)
    harness.initialize(app_id)
    results = [{"name": "initialize", "result": harness.state}]
    for call in calls:
        name = str(call.get("name"))
        args = dict(call.get("arguments") or {})
        if name == "get_window_state":
            state = harness.observe(bool(args.get("include_screenshot", True)), bool(args.get("include_text", False)))
            results.append({"name": name, "result": state})
        else:
            results.append({"name": name, "result": harness.act_and_refresh(name, args)})
    observation = latest_observation({"result": harness.state}) or harness.state
    return {"results": results, "observation": observation, "window": harness.target_window}
