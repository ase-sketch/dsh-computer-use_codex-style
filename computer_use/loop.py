from __future__ import annotations

from typing import Any, Iterable, Mapping

from computer_use.executor import ToolExecutor


def latest_observation(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    extra = payload.get("observation")
    if isinstance(extra, Mapping) and ("screenshots" in extra or "tree" in extra):
        return dict(extra)
    result = payload.get("result")
    if isinstance(result, Mapping) and "state" in result and isinstance(result["state"], Mapping):
        result = result["state"]
    if not isinstance(result, Mapping):
        return None
    if "window" in result and "screenshots" in result and "accessibility" in result:
        return dict(result)
    if "tree" in result and "screenshot_bytes" in result:
        return dict(result)
    observation = result.get("observation")
    if isinstance(observation, Mapping):
        return dict(observation)
    return None


def run_tool_sequence(
    executor: ToolExecutor,
    calls: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply a sequence of {name, arguments} tool calls and keep the latest window state."""
    results: list[dict[str, Any]] = []
    observation: dict[str, Any] | None = None
    for call in calls:
        payload = executor.execute_call(call)
        results.append(payload)
        found = latest_observation(payload)
        if found is not None:
            observation = found
    if observation is None:
        raise RuntimeError("tool sequence produced no observation")
    return {"results": results, "observation": observation}
