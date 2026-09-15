"""JPEG encode via GDI+ (same container the helper emits from WIC BitmapEncoder)."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_void_p, wintypes

from computer_use.errors import DesktopUnavailable

gdiplus = ctypes.WinDLL("gdiplus")
ole32 = ctypes.oledll.ole32

PixelFormat32bppARGB = 0x26200A
EncoderQuality = _guid = None  # filled below


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def make_guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8).from_buffer_copy(data4))


EncoderQuality = make_guid("{1D5BE4B5-FA4A-452D-9CDD-5DB35105E7EB}")


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", c_void_p),
        ("SuppressBackgroundThread", ctypes.c_int),
        ("SuppressExternalCodecs", ctypes.c_int),
    ]


class EncoderParameter(ctypes.Structure):
    _fields_ = [
        ("Guid", GUID),
        ("NumberOfValues", wintypes.ULONG),
        ("Type", wintypes.ULONG),
        ("Value", c_void_p),
    ]


class EncoderParameters(ctypes.Structure):
    _fields_ = [("Count", wintypes.UINT), ("Parameter", EncoderParameter * 1)]


class ImageCodecInfo(ctypes.Structure):
    _fields_ = [
        ("Clsid", GUID),
        ("FormatID", GUID),
        ("CodecName", wintypes.LPWSTR),
        ("DllName", wintypes.LPWSTR),
        ("FormatDescription", wintypes.LPWSTR),
        ("FilenameExtension", wintypes.LPWSTR),
        ("MimeType", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("Version", wintypes.DWORD),
        ("SigCount", wintypes.DWORD),
        ("SigSize", wintypes.DWORD),
        ("SigPattern", ctypes.c_void_p),
        ("SigMask", ctypes.c_void_p),
    ]


_token = ctypes.c_ulong()
_started = False


def _startup() -> None:
    global _started
    if _started:
        return
    inp = GdiplusStartupInput(1, None, 0, 0)
    status = gdiplus.GdiplusStartup(byref(_token), byref(inp), None)
    if status != 0:
        raise DesktopUnavailable(f"GdiplusStartup {status}")
    _started = True


def _jpeg_clsid() -> GUID:
    num = wintypes.UINT()
    size = wintypes.UINT()
    gdiplus.GdipGetImageEncodersSize(byref(num), byref(size))
    buf = ctypes.create_string_buffer(size.value)
    gdiplus.GdipGetImageEncoders(num, size, buf)
    count = int(num.value)
    array = ctypes.cast(buf, POINTER(ImageCodecInfo * count)).contents
    for i in range(count):
        mime = array[i].MimeType or ""
        if "jpeg" in mime.lower() or "jpg" in mime.lower():
            return array[i].Clsid
    raise DesktopUnavailable("JPEG encoder not installed")


#: Official JPEG quality 0.8 -> 80 (parity/official-constants.json capture.jpegQuality).
def encode_jpeg_bgra(width: int, height: int, bgra: bytes, quality: int = 80) -> bytes:
    """BGRA top-down → JPEG bytes."""
    _startup()
    stride = width * 4
    if len(bgra) < stride * height:
        raise ValueError("bgra length")
    # GDI+ ARGB is BGRA in memory on little-endian
    scan = (ctypes.c_ubyte * len(bgra)).from_buffer_copy(bgra)
    bitmap = c_void_p()
    status = gdiplus.GdipCreateBitmapFromScan0(width, height, stride, PixelFormat32bppARGB, scan, byref(bitmap))
    if status != 0:
        raise DesktopUnavailable(f"GdipCreateBitmapFromScan0 {status}")
    stream = c_void_p()
    hr = ole32.CreateStreamOnHGlobal(None, True, byref(stream))
    if hr != 0:
        gdiplus.GdipDisposeImage(bitmap)
        raise DesktopUnavailable("CreateStreamOnHGlobal failed")
    clsid = _jpeg_clsid()
    gdiplus.GdipSaveImageToStream.restype = ctypes.c_int
    status = gdiplus.GdipSaveImageToStream(bitmap, stream, byref(clsid), None)
    gdiplus.GdipDisposeImage(bitmap)
    if status != 0:
        raise DesktopUnavailable(f"GdipSaveImageToStream {status}")
    return _istream_bytes(stream)


def encode_jpeg_rgba(width: int, height: int, rgba: bytes, quality: int = 80) -> bytes:
    bgra = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        bgra[i] = rgba[i + 2]
        bgra[i + 1] = rgba[i + 1]
        bgra[i + 2] = rgba[i]
        bgra[i + 3] = rgba[i + 3]
    return encode_jpeg_bgra(width, height, bytes(bgra), quality)


def _istream_bytes(stream: c_void_p) -> bytes:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hglobal = wintypes.HGLOBAL()
    ole32.GetHGlobalFromStream.argtypes = [c_void_p, POINTER(wintypes.HGLOBAL)]
    ole32.GetHGlobalFromStream.restype = ctypes.HRESULT
    hr = ole32.GetHGlobalFromStream(stream, byref(hglobal))
    if hr != 0:
        raise DesktopUnavailable("GetHGlobalFromStream failed")
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    size = int(kernel32.GlobalSize(hglobal))
    ptr = kernel32.GlobalLock(hglobal)
    try:
        data = ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(hglobal)
    vtbl = ctypes.cast(ctypes.cast(stream, POINTER(c_void_p))[0], POINTER(c_void_p))
    ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])(stream)
    if not data[:2] == b"\xff\xd8":
        raise DesktopUnavailable("GDI+ did not produce JPEG")
    return data
