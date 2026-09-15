"""D3D11 monitor capture via COM (DXGI Output Duplication).

Official helper uses WinRT WGC (IGraphicsCaptureItemInterop.CreateForMonitor +
Direct3D11CaptureFramePool.CreateFreeThreaded, cursor off, no border) then crops
the window. This module talks to the same D3D11/DXGI stack through COM vtables.
If duplication is unavailable (session 0, no WDDM output), callers fall back to GDI.
"""

from __future__ import annotations

import ctypes
from ctypes import HRESULT, POINTER, byref, c_uint, c_void_p, wintypes

from computer_use.errors import DesktopUnavailable
from computer_use.png import encode_png
from computer_use.wgc import MonitorFrame, crop_window_from_monitor
from computer_use.win_capture import crop_rgba, monitor_frame_for_hwnd, window_rect
from computer_use.win_dpi import window_dpi

d3d11 = ctypes.WinDLL("d3d11")
dxgi = ctypes.WinDLL("dxgi")
user32 = ctypes.WinDLL("user32", use_last_error=True)

D3D11_SDK_VERSION = 7
D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
DXGI_FORMAT_B8G8R8A8_UNORM = 87
DXGI_ERROR_WAIT_TIMEOUT = 0x887A0027
DXGI_ERROR_ACCESS_LOST = 0x887A0026
MONITOR_DEFAULTTONEAREST = 2


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8).from_buffer_copy(data4))


IID_IDXGIDevice = _guid("{54EC77FA-1377-44E6-8C32-88FD5F44C84C}")
IID_IDXGIAdapter = _guid("{2411E7E1-12AC-4CCF-BD14-9798E8534DC0}")
IID_IDXGIOutput1 = _guid("{00CDDEA8-939B-4B83-A340-A685226666CC}")
IID_ID3D11Texture2D = _guid("{6F15AAF2-D208-4E89-9AB4-489535D34F9C}")
IID_IGraphicsCaptureItemInterop = _guid("{3628E81B-3CAC-4C60-B7F4-23CE0E0C3356}")

WGC_INTEROP_IID = IID_IGraphicsCaptureItemInterop


class DXGI_OUTDUPL_DESC(ctypes.Structure):
    _fields_ = [
        ("ModeDesc", ctypes.c_byte * 48),
        ("Rotation", c_uint),
        ("DesktopImageInSystemMemory", wintypes.BOOL),
    ]


class D3D11_TEXTURE2D_DESC(ctypes.Structure):
    _fields_ = [
        ("Width", c_uint),
        ("Height", c_uint),
        ("MipLevels", c_uint),
        ("ArraySize", c_uint),
        ("Format", c_uint),
        ("SampleCount", c_uint),
        ("SampleQuality", c_uint),
        ("Usage", c_uint),
        ("BindFlags", c_uint),
        ("CPUAccessFlags", c_uint),
        ("MiscFlags", c_uint),
    ]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [("pData", c_void_p), ("RowPitch", c_uint), ("DepthPitch", c_uint)]


class DXGI_OUTDUPL_FRAME_INFO(ctypes.Structure):
    _fields_ = [("LastPresentTime", ctypes.c_int64), ("LastMouseUpdateTime", ctypes.c_int64), ("AccumulatedFrames", c_uint), ("RectsCoalesced", wintypes.BOOL), ("ProtectedContentMaskedOut", wintypes.BOOL), ("PointerPosition", ctypes.c_byte * 12), ("TotalMetadataBufferSize", c_uint), ("PointerShapeBufferSize", c_uint)]


def _vtbl(obj: c_void_p) -> c_void_p:
    return ctypes.cast(obj, POINTER(c_void_p))[0]


def _call(obj: c_void_p, index: int, restype, *argtypes):
    vtbl = ctypes.cast(_vtbl(obj), POINTER(c_void_p))
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(vtbl[index])


def _release(obj: c_void_p | None) -> None:
    if not obj:
        return
    _call(obj, 2, ctypes.c_ulong)(obj)


def _qi(obj: c_void_p, iid: GUID) -> c_void_p:
    out = c_void_p()
    hr = _call(obj, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(obj, byref(iid), byref(out))
    if hr != 0 or not out.value:
        raise DesktopUnavailable(f"QueryInterface failed 0x{hr & 0xFFFFFFFF:08X}")
    return out


def wgc_interop_available() -> bool:
    """True when IGraphicsCaptureItemInterop can be activated (Win10 1803+)."""
    try:
        combase = ctypes.WinDLL("combase")
        inspectable = c_void_p()
        # RoGetActivationFactory is enough to prove WinRT Graphics Capture exists.
        name = "Windows.Graphics.Capture.GraphicsCaptureItem"
        hstring = c_void_p()
        WindowsCreateString = getattr(combase, "WindowsCreateString", None)
        RoGetActivationFactory = getattr(combase, "RoGetActivationFactory", None)
        if WindowsCreateString is None or RoGetActivationFactory is None:
            return False
        WindowsCreateString.argtypes = [wintypes.LPCWSTR, c_uint, POINTER(c_void_p)]
        WindowsCreateString.restype = HRESULT
        hr = WindowsCreateString(name, len(name), byref(hstring))
        if hr != 0:
            return False
        iid = IID_IGraphicsCaptureItemInterop
        hr = RoGetActivationFactory(hstring, byref(iid), byref(inspectable))
        combase.WindowsDeleteString(hstring)
        if inspectable:
            _release(inspectable)
        return hr == 0
    except OSError:
        return False


def capture_monitor_d3d(hwnd: int) -> tuple[bytes, MonitorFrame]:
    """Acquire one desktop frame with DXGI Output Duplication (D3D11 COM, no cursor blit)."""
    device = c_void_p()
    context = c_void_p()
    d3d11.D3D11CreateDevice.restype = HRESULT
    hr = d3d11.D3D11CreateDevice(
        None,
        D3D_DRIVER_TYPE_HARDWARE,
        None,
        D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        None,
        0,
        D3D11_SDK_VERSION,
        byref(device),
        None,
        byref(context),
    )
    if hr != 0 or not device:
        raise DesktopUnavailable(f"D3D11CreateDevice failed 0x{hr & 0xFFFFFFFF:08X}")
    dxgi_device = None
    adapter = None
    output = None
    output1 = None
    dup = None
    staging = None
    try:
        dxgi_device = _qi(device, IID_IDXGIDevice)
        adapter = c_void_p()
        # IDXGIDevice::GetAdapter index 7 on some layouts; use GetParent via Query
        hr = _call(dxgi_device, 7, HRESULT, POINTER(GUID), POINTER(c_void_p))(dxgi_device, byref(IID_IDXGIAdapter), byref(adapter))
        if hr != 0:
            raise DesktopUnavailable("IDXGIDevice.GetAdapter failed")
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        output = _find_output(adapter, monitor)
        output1 = _qi(output, IID_IDXGIOutput1)
        dup = c_void_p()
        hr = _call(output1, 22, HRESULT, c_void_p, POINTER(c_void_p))(output1, device, byref(dup))
        if hr != 0 or not dup:
            raise DesktopUnavailable("DuplicateOutput failed")
        frame_info = DXGI_OUTDUPL_FRAME_INFO()
        resource = c_void_p()
        hr = _call(dup, 8, HRESULT, c_uint, POINTER(DXGI_OUTDUPL_FRAME_INFO), POINTER(c_void_p))(
            dup, 200, byref(frame_info), byref(resource)
        )
        if hr in (DXGI_ERROR_WAIT_TIMEOUT, DXGI_ERROR_ACCESS_LOST) or hr != 0:
            raise DesktopUnavailable("AcquireNextFrame failed")
        texture = _qi(resource, IID_ID3D11Texture2D)
        _release(resource)
        desc = D3D11_TEXTURE2D_DESC()
        _call(texture, 10, None, POINTER(D3D11_TEXTURE2D_DESC))(texture, byref(desc))
        desc.Usage = D3D11_USAGE_STAGING
        desc.BindFlags = 0
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ
        desc.MiscFlags = 0
        staging = c_void_p()
        hr = _call(device, 5, HRESULT, POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p))(
            device, byref(desc), None, byref(staging)
        )
        if hr != 0:
            _release(texture)
            raise DesktopUnavailable("CreateTexture2D staging failed")
        _call(context, 47, None, c_void_p, c_void_p)(context, staging, texture)  # CopyResource
        mapped = D3D11_MAPPED_SUBRESOURCE()
        hr = _call(context, 14, HRESULT, c_void_p, c_uint, c_uint, c_uint, POINTER(D3D11_MAPPED_SUBRESOURCE))(
            context, staging, 0, 1, 0, byref(mapped)
        )
        _release(texture)
        if hr != 0:
            raise DesktopUnavailable("Map staging failed")
        width, height = int(desc.Width), int(desc.Height)
        pitch = int(mapped.RowPitch)
        src = ctypes.string_at(mapped.pData, pitch * height)
        _call(context, 15, None, c_void_p, c_uint)(context, staging, 0)  # Unmap
        _call(dup, 14, HRESULT)(dup)  # ReleaseFrame
        rgba = _bgra_rows_to_rgba(src, width, height, pitch)
        frame = monitor_frame_for_hwnd(hwnd)
        # Duplication size is the output desktop; prefer that as the monitor bitmap.
        monitor = MonitorFrame(frame.origin_x, frame.origin_y, width, height)
        return rgba, monitor
    finally:
        for obj in (staging, dup, output1, output, adapter, dxgi_device, context, device):
            _release(obj)


class DXGI_OUTPUT_DESC(ctypes.Structure):
    _fields_ = [
        ("DeviceName", wintypes.WCHAR * 32),
        ("DesktopCoordinates", wintypes.RECT),
        ("AttachedToDesktop", wintypes.BOOL),
        ("Rotation", c_uint),
        ("Monitor", wintypes.HMONITOR),
    ]


def _find_output(adapter: c_void_p, hmonitor: int) -> c_void_p:
    index = 0
    first = None
    while True:
        output = c_void_p()
        hr = _call(adapter, 7, HRESULT, c_uint, POINTER(c_void_p))(adapter, index, byref(output))
        if hr != 0:
            if first:
                return first
            raise DesktopUnavailable("DXGI output matching monitor not found")
        if first is None:
            first = output
        desc = DXGI_OUTPUT_DESC()
        _call(output, 7, HRESULT, POINTER(DXGI_OUTPUT_DESC))(output, byref(desc))
        if not hmonitor or int(desc.Monitor) == int(hmonitor):
            return output
        index += 1


def _bgra_rows_to_rgba(src: bytes, width: int, height: int, pitch: int) -> bytes:
    out = bytearray(width * height * 4)
    for y in range(height):
        row = src[y * pitch : y * pitch + width * 4]
        for x in range(width):
            b, g, r, a = row[x * 4 : x * 4 + 4]
            o = (y * width + x) * 4
            out[o : o + 4] = bytes((r, g, b, a))
    return bytes(out)


def capture_hwnd_d3d(hwnd: int):
    """Official crop policy on a D3D11 monitor frame. Returns CaptureFrame-compatible tuple."""
    from computer_use.win_capture import CaptureFrame

    rgba, monitor = capture_monitor_d3d(hwnd)
    left, top, width, height = window_rect(hwnd)
    crop_x, crop_y, crop_w, crop_h = crop_window_from_monitor(monitor, left, top, width, height)
    png = encode_png(crop_w, crop_h, crop_rgba(rgba, monitor.width, monitor.height, crop_x, crop_y, crop_w, crop_h))
    return CaptureFrame(png, left, top, crop_w, crop_h, window_dpi(hwnd))
