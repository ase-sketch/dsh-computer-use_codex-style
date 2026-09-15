"""Cross-step harness state: window handles, screenshot cache, AX prev, notes."""

from __future__ import annotations

from typing import Any

from computer_use.compact import present_observation


class CuaSession:
    def __init__(self) -> None:
        self.apps: list[dict[str, Any]] = []
        self.target_app: dict[str, Any] | None = None
        self.target_window: dict[str, Any] | None = None
        self.state: dict[str, Any] | None = None
        self.reasoning: list[str] = []
        self.screenshot_cache: dict[str, str] = {}
        self.prev_ax_tree: str | None = None
        self.tab_id: str | None = None

    def note(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self.reasoning.append(cleaned)

    def remember_shot(self, observation: dict[str, Any]) -> None:
        for shot in observation.get("screenshots") or []:
            if isinstance(shot, dict) and shot.get("id") and shot.get("url"):
                self.screenshot_cache[str(shot["id"])] = str(shot["url"])
        acc = observation.get("accessibility")
        if isinstance(acc, dict) and isinstance(acc.get("tree"), str) and not acc.get("diff"):
            self.prev_ax_tree = acc["tree"]

    def present(self, observation: dict[str, Any], emit_image: bool = False, disable_diff: bool = True) -> dict[str, Any]:
        shown = present_observation(
            observation,
            emit_image=emit_image,
            prev_tree=None if disable_diff else self.prev_ax_tree,
            disable_diff=disable_diff,
        )
        self.remember_shot(observation)
        self.state = shown
        return shown

    def snapshot(self) -> dict[str, Any]:
        return {
            "apps": self.apps,
            "target_app": self.target_app,
            "target_window": self.target_window,
            "tab_id": self.tab_id,
            "reasoning": list(self.reasoning),
            "screenshot_ids": list(self.screenshot_cache),
            "has_prev_ax": self.prev_ax_tree is not None,
        }
