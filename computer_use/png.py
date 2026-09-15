"""Minimal PNG encoder (RGBA8). No third-party image libs."""

from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    if width < 1 or height < 1:
        raise ValueError("png size must be positive")
    stride = width * 4
    if len(rgba) != stride * height:
        raise ValueError("rgba length does not match size")
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgba[y * stride : (y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def solid_png(
    width: int = 64,
    height: int = 48,
    color: tuple[int, int, int, int] = (36, 52, 86, 255),
) -> bytes:
    return encode_png(width, height, bytes(color) * (width * height))


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Decode 8-bit RGB/RGBA PNGs produced by encode_png (filter 0)."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos = 8
    width = height = 0
    color = 6
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit, color, *_rest = struct.unpack(">IIBBBBB", chunk)
            if bit != 8 or color not in (2, 6) or width < 1 or height < 1:
                raise ValueError("unsupported PNG")
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    channels = 4 if color == 6 else 3
    stride = width * channels
    rgba = bytearray()
    index = 0
    for _y in range(height):
        filt = raw[index]
        index += 1
        row = raw[index : index + stride]
        index += stride
        if filt != 0 or len(row) != stride:
            raise ValueError("filtered or truncated PNG")
        if color == 6:
            rgba.extend(row)
        else:
            for x in range(0, stride, 3):
                rgba.extend(row[x : x + 3] + b"\xff")
    return width, height, bytes(rgba)


def scale_rgba(width: int, height: int, rgba: bytes, max_edge: int) -> tuple[int, int, bytes]:
    if max_edge < 1 or max(width, height) <= max_edge:
        return width, height, rgba
    scale = max_edge / float(max(width, height))
    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))
    out = bytearray(new_w * new_h * 4)
    for y in range(new_h):
        src_y = min(height - 1, y * height // new_h)
        for x in range(new_w):
            src_x = min(width - 1, x * width // new_w)
            src = (src_y * width + src_x) * 4
            dst = (y * new_w + x) * 4
            out[dst : dst + 4] = rgba[src : src + 4]
    return new_w, new_h, bytes(out)


def downscale_png(data: bytes, max_edge: int = 0) -> bytes:
    try:
        width, height, rgba = decode_png(data)
    except (ValueError, struct.error, zlib.error):
        return data
    new_w, new_h, scaled = scale_rgba(width, height, rgba, max_edge)
    if new_w == width and new_h == height:
        return data
    return encode_png(new_w, new_h, scaled)
