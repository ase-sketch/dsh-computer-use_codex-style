"""Detach screenshot bytes from tool JSON so DSH can admit ImageBlocks."""

from __future__ import annotations

import base64
from typing import Any

from computer_use.data_url import decode_data_url
from computer_use.png import downscale_png

IMAGE_KEYS = ("url", "image_url", "screenshot_base64", "data")


def _from_data_url(url: str) -> tuple[bytes, str] | None:
    if not isinstance(url, str) or not url.startswith("data:image"):
        return None
    try:
        data, mime = decode_data_url(url)
    except ValueError:
        return None
    if not data:
        return None
    return data, mime or "image/png"


def _from_b64(blob: str, mime: str = "image/png") -> tuple[bytes, str] | None:
    if not isinstance(blob, str) or len(blob) < 32:
        return None
    try:
        data = base64.b64decode(blob, validate=False)
    except (ValueError, TypeError):
        return None
    if not data.startswith(b"\x89PNG") and not data[:2] in (b"\xff\xd8", b"RI"):
        if not data:
            return None
    return data, mime


def _harvest_dict(node: dict[str, Any]) -> tuple[bytes, str] | None:
    mime = str(node.get("mimeType") or node.get("screenshot_mime") or "image/png")
    for key in IMAGE_KEYS:
        value = node.get(key)
        if not isinstance(value, str):
            continue
        if value.startswith("data:image"):
            found = _from_data_url(value)
            if found:
                return found
        if key in ("screenshot_base64", "data") and len(value) > 32 and "data:" not in value[:16]:
            found = _from_b64(value, mime)
            if found:
                return found
    return None


def _strip_payloads(node: dict[str, Any]) -> dict[str, Any]:
    out = dict(node)
    if isinstance(out.get("url"), str) and out["url"].startswith("data:image"):
        out["url"] = ""
        out["emitted"] = True
    if isinstance(out.get("image_url"), str) and str(out["image_url"]).startswith("data:image"):
        out.pop("image_url", None)
    if isinstance(out.get("screenshot_base64"), str) and out["screenshot_base64"]:
        out["screenshot_base64"] = ""
    if out.get("type") in ("input_image", "image") and isinstance(out.get("data"), str):
        out["data"] = ""
    return out


#: 0 = official behaviour: ship the screenshot unscaled (decision D-E). A positive value
#: is a DSH opt-in downscale that trades image detail for vision tokens.
def detach_images(payload: Any, *, max_edge: int = 0) -> tuple[Any, list[dict[str, str]]]:
    """Return (json_without_bytes, images[{mimeType,data,name}])."""
    images: list[dict[str, str]] = []

    def walk(node: Any, hint: str = "screenshot") -> Any:
        if isinstance(node, list):
            return [walk(item, hint) for item in node]
        if not isinstance(node, dict):
            return node
        child_lists = any(isinstance(node.get(key), list) and node.get(key) for key in ("screenshots", "images"))
        harvested = None if child_lists else _harvest_dict(node)
        walked = {key: walk(value, str(key)) for key, value in node.items()}
        cleaned = _strip_payloads(walked)
        if harvested is not None:
            data, mime = harvested
            if mime == "image/png":
                data = downscale_png(data, max_edge)
            name = str(node.get("id") or node.get("name") or hint)
            if not name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                name = f"{name}.png"
            images.append(
                {
                    "mimeType": mime if mime.startswith("image/") else "image/png",
                    "data": base64.b64encode(data).decode("ascii"),
                    "name": name.replace("\\", "_").replace("/", "_"),
                }
            )
        return cleaned

    return walk(payload), images
