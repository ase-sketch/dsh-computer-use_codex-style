from __future__ import annotations

import base64


def decode_data_url(url: str) -> tuple[bytes, str]:
    if not url.startswith("data:"):
        raise ValueError("expected a data URL")
    header, _, data = url.partition(",")
    mime = "image/png"
    if header.startswith("data:") and ";" in header:
        mime = header[5:].split(";", 1)[0] or mime
    return base64.b64decode(data), mime
