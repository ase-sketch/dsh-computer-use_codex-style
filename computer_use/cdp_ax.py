"""Flatten Chrome CDP Accessibility.getFullAXTree into Codex-style indexed AX text."""

from __future__ import annotations

from typing import Any


def _value(node: dict[str, Any], key: str) -> str:
    raw = node.get(key)
    if isinstance(raw, dict):
        return str(raw.get("value") or "")
    return str(raw or "")


def flatten_cdp_ax(payload: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    by_id = {str(item.get("nodeId")): item for item in nodes if isinstance(item, dict)}
    roots = [item for item in nodes if isinstance(item, dict) and not item.get("parentId")]
    if not roots and nodes:
        roots = [nodes[0]]
    flat: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], depth: int) -> None:
        role = _value(node, "role") or "generic"
        name = _value(node, "name")
        ignored = node.get("ignored") is True
        if not ignored:
            flat.append(
                {
                    "index": len(flat),
                    "role": role,
                    "name": name,
                    "depth": depth,
                    "backendDOMNodeId": node.get("backendDOMNodeId"),
                    "nodeId": node.get("nodeId"),
                }
            )
        for child in node.get("childIds") or []:
            nxt = by_id.get(str(child))
            if isinstance(nxt, dict):
                walk(nxt, depth + 1)

    for root in roots:
        walk(root, 0)
    return flat


def ax_text(nodes: list[dict[str, Any]], title: str, url: str) -> str:
    lines = [f"Title: {title}", f"URL: {url}"]
    for node in nodes:
        indent = "  " * int(node.get("depth") or 0)
        lines.append(f'{indent}[{node["index"]}] {node["role"]} "{node["name"]}"')
    return "\n".join(lines)
