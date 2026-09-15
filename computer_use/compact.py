"""Model-facing compression recovered from Codex screenshot/AX guidance.

Official: prefer AX text over pixels; do not re-emit screenshots; tree may be a
diff; request screenshot and text together only when both are required.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_NODES = 1200
DEFAULT_MAX_DEPTH = 64


def tree_diff(previous: str, current: str) -> str:
    prev = set(previous.splitlines())
    cur = current.splitlines()
    added = [line for line in cur if line not in prev]
    removed = [line for line in previous.splitlines() if line not in set(cur)]
    parts = []
    if removed:
        parts.append("removed:")
        parts.extend(removed[:200])
    if added:
        parts.append("added/changed:")
        parts.extend(added[:400])
    if not parts:
        return "no accessibility-tree change"
    return "\n".join(parts)


def present_observation(
    obs: dict[str, Any],
    *,
    emit_image: bool = False,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    prev_tree: str | None = None,
    disable_diff: bool = True,
) -> dict[str, Any]:
    out = dict(obs)
    shots = []
    images: list[dict[str, Any]] = []
    for shot in out.get("screenshots") or []:
        if not isinstance(shot, dict):
            continue
        slim = {key: shot[key] for key in shot if key != "url"}
        slim["emitted"] = bool(emit_image)
        if emit_image and "url" in shot:
            slim["url"] = shot["url"]
            images.append({"type": "input_image", "image_url": shot["url"], "detail": "original"})
        shots.append(slim)
    out["screenshots"] = shots
    out["images"] = images
    if not emit_image:
        out["screenshot_base64"] = ""
    nodes = []
    for node in out.get("tree") or []:
        if not isinstance(node, dict):
            continue
        if int(node.get("depth") or 0) > max_depth:
            continue
        nodes.append(node)
        if len(nodes) >= max_nodes:
            break
    out["tree"] = nodes
    acc = out.get("accessibility")
    if isinstance(acc, dict) and isinstance(acc.get("tree"), str):
        acc = dict(acc)
        text = acc["tree"]
        if prev_tree and not disable_diff:
            acc["tree"] = tree_diff(prev_tree, text)
            acc["diff"] = True
        else:
            acc["tree"] = "\n".join(text.splitlines()[:max_nodes])
            acc["diff"] = False
        out["accessibility"] = acc
    return out
