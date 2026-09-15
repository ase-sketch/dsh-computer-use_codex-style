"""WinRT Windows.Graphics.Capture FramePool — official helper capture/image.rs.

CreateForMonitor → Direct3D11CaptureFramePool.CreateFreeThreaded (1 buffer) →
IsCursorCaptureEnabled=false → IsBorderRequired=false → StartCapture →
FrameArrived (or documented poll+timeout) → TryGetNextFrame → crop window → JPEG.

FramePool is cached per HMONITOR and Recreated when GraphicsCaptureItem.Size changes.
"""

from __future__ import annotations

import atexit
import ctypes
import threading
import time
from ctypes import HRESULT, POINTER, byref, c_int32, c_int64, c_uint, c_void_p, wintypes

from computer_use.errors import DesktopUnavailable
from computer_use.jpeg_wic import encode_jpeg_bgra as encode_jpeg_gdiplus
from computer_use.wgc import crop_window_from_monitor, scaled_size
from computer_use.win_capture import CaptureFrame, crop_rgba, monitor_frame_for_hwnd, window_rect
from computer_use.win_dpi import enable_thread_dpi_awareness, window_dpi

user32 = ctypes.WinDLL("user32", use_last_error=True)
d3d11 = ctypes.WinDLL("d3d11")
combase = ctypes.WinDLL("combase")
ole32 = ctypes.oledll.ole32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

RO_INIT_MULTITHREADED = 1
D3D11_SDK_VERSION = 7
D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
DXGI_FORMAT_B8G8R8A8_UNORM = 87
MONITOR_DEFAULTTONEAREST = 2
DirectXPixelFormat_B8G8R8A8UIntNormalized = 87
FRAMEPOOL_BUFFERS = 1
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258

CAPTURE_TIMEOUT = "window capture timed out"
FRAME_ARRIVED_TIMEOUT = "FrameArrived timed out"
TRYGET_AFTER_ARRIVED = "TryGetNextFrame after FrameArrived failed"
CACHE_FAILED = "computer-use cached capture session failed: "


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


class SizeInt32(ctypes.Structure):
    _fields_ = [("Width", c_int32), ("Height", c_int32)]


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


class D3D11_BOX(ctypes.Structure):
    _fields_ = [
        ("left", c_uint),
        ("top", c_uint),
        ("front", c_uint),
        ("right", c_uint),
        ("bottom", c_uint),
        ("back", c_uint),
    ]


IID_IGraphicsCaptureItemInterop = _guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")
IID_IGraphicsCaptureItem = _guid("79C3F95B-31F7-4EC2-A464-632EF5D30760")
IID_IDirect3D11CaptureFramePoolStatics2 = _guid("589B103F-6BBC-5DF5-A991-02E28B3B66D5")
IID_IDirect3D11CaptureFramePool = _guid("24EB6D22-1975-422E-82E7-780DBD8DDF24")
IID_IDirect3D11CaptureFrame = _guid("FA50C623-38DA-4B32-ACF3-FA9734AD800E")
IID_IGraphicsCaptureSession = _guid("814E42A9-F70F-4AD7-939B-FDDCC6EB880D")
IID_IGraphicsCaptureSession2 = _guid("2C39AE40-7D2E-5044-804E-8B6799D4CF9E")
IID_IGraphicsCaptureSession3 = _guid("F2CDD966-22AE-5EA1-9596-3A289344C3BE")
IID_IDirect3DDxgiInterfaceAccess = _guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")
IID_IDXGIDevice = _guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C")
IID_ID3D11Texture2D = _guid("6F15AAF2-D208-4E89-9AB4-489535D34F9C")
IID_IDXGISurface = _guid("CAFCB56C-6AC3-4889-BF47-9E23BBD260EC")
IID_IClosable = _guid("30D5A829-7FA4-4026-83BB-D75BAE4EA99E")
IID_IUnknown = _guid("00000000-0000-0000-C000-000000000046")
IID_IAgileObject = _guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")
D3D11_BIND_RENDER_TARGET = 0x20
D3D11_BIND_SHADER_RESOURCE = 0x8

RC_ITEM = "Windows.Graphics.Capture.GraphicsCaptureItem"
RC_POOL = "Windows.Graphics.Capture.Direct3D11CaptureFramePool"

_QI = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
_ADDREF = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
_RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
_INVOKE = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_void_p)


class _HandlerVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", _QI),
        ("AddRef", _ADDREF),
        ("Release", _RELEASE),
        ("Invoke", _INVOKE),
    ]


class _Handler(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(_HandlerVtbl)), ("refcnt", ctypes.c_ulong)]


def _vtbl(obj: c_void_p):
    return ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))


def _fn(obj: c_void_p, index: int, restype, *argtypes):
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(_vtbl(obj)[index])


def _release(obj: c_void_p | None) -> None:
    if obj:
        _fn(obj, 2, ctypes.c_ulong)(obj)


def _qi(obj: c_void_p, iid: GUID) -> c_void_p:
    out = c_void_p()
    hr = _fn(obj, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(obj, byref(iid), byref(out))
    if hr != 0 or not out:
        raise DesktopUnavailable(f"QI failed 0x{hr & 0xFFFFFFFF:08X}")
    return out


def _close_winrt(obj: c_void_p | None) -> None:
    if not obj:
        return
    try:
        closable = _qi(obj, IID_IClosable)
        _fn(closable, 6, HRESULT)(closable)
        _release(closable)
    except Exception:
        pass
    _release(obj)


def _hstring(text: str) -> c_void_p:
    hs = c_void_p()
    combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, POINTER(c_void_p)]
    combase.WindowsCreateString.restype = HRESULT
    hr = combase.WindowsCreateString(text, len(text), byref(hs))
    if hr != 0:
        raise DesktopUnavailable("WindowsCreateString failed")
    return hs


def _ro_factory(runtime_class: str, iid: GUID) -> c_void_p:
    hs = _hstring(runtime_class)
    factory = c_void_p()
    combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
    combase.RoGetActivationFactory.restype = HRESULT
    hr = combase.RoGetActivationFactory(hs, byref(iid), byref(factory))
    combase.WindowsDeleteString(hs)
    if hr != 0 or not factory:
        raise DesktopUnavailable(f"RoGetActivationFactory({runtime_class}) 0x{hr & 0xFFFFFFFF:08X}")
    return factory


def _ro_init() -> None:
    combase.RoInitialize.argtypes = [ctypes.c_uint]
    combase.RoInitialize.restype = HRESULT
    combase.RoInitialize(RO_INIT_MULTITHREADED)
    ole32.CoInitializeEx(None, 0x0)


def wgc_framepool_available() -> bool:
    try:
        _ro_init()
        factory = _ro_factory(RC_ITEM, IID_IGraphicsCaptureItemInterop)
        _release(factory)
        return True
    except Exception:
        return False


def _crop_d3d_surface(device: c_void_p, context: c_void_p, surface, crop_x: int, crop_y: int, crop_w: int, crop_h: int):
    """Copy a window rectangle out of the monitor texture, then wrap as IDirect3DSurface."""
    if crop_w < 1 or crop_h < 1:
        return None
    try:
        access = _qi(surface, IID_IDirect3DDxgiInterfaceAccess)
        src_tex = c_void_p()
        hr = _fn(access, 3, HRESULT, POINTER(GUID), POINTER(c_void_p))(access, byref(IID_ID3D11Texture2D), byref(src_tex))
        if hr != 0:
            return None
        desc = D3D11_TEXTURE2D_DESC()
        _fn(src_tex, 10, None, POINTER(D3D11_TEXTURE2D_DESC))(src_tex, byref(desc))
        desc.Width = int(crop_w)
        desc.Height = int(crop_h)
        desc.MipLevels = 1
        desc.ArraySize = 1
        desc.SampleCount = 1
        desc.SampleQuality = 0
        desc.Usage = 0
        desc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET
        desc.CPUAccessFlags = 0
        desc.MiscFlags = 0
        dst = c_void_p()
        hr = _fn(device, 5, HRESULT, POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p))(device, byref(desc), None, byref(dst))
        if hr != 0:
            return None
        box = D3D11_BOX(int(crop_x), int(crop_y), 0, int(crop_x + crop_w), int(crop_y + crop_h), 1)
        _fn(context, 46, None, c_void_p, c_uint, c_uint, c_uint, c_uint, c_void_p, c_uint, POINTER(D3D11_BOX))(
            context, dst, 0, 0, 0, 0, src_tex, 0, byref(box)
        )
        dxgi_surface = c_void_p()
        hr = _fn(dst, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(dst, byref(IID_IDXGISurface), byref(dxgi_surface))
        if hr != 0:
            return None
        winrt_surface = c_void_p()
        d3d11.CreateDirect3D11SurfaceFromDXGISurface.restype = HRESULT
        d3d11.CreateDirect3D11SurfaceFromDXGISurface.argtypes = [c_void_p, POINTER(c_void_p)]
        hr = d3d11.CreateDirect3D11SurfaceFromDXGISurface(dxgi_surface, byref(winrt_surface))
        if hr != 0 or not winrt_surface:
            return None
        return winrt_surface
    except Exception:
        return None


class _Arrived:
    """WinRT TypedEventHandler stand-in: IUnknown + IAgileObject + Invoke → SetEvent."""

    def __init__(self) -> None:
        self.event = kernel32.CreateEventW(None, True, False, None)
        self.ref = 1

        def qi(this, iid, out):
            out[0] = this
            self.ref += 1
            return 0

        def addref(this):
            self.ref += 1
            return self.ref

        def release(this):
            self.ref = max(self.ref - 1, 0)
            return self.ref

        def invoke(this, sender, args):
            kernel32.SetEvent(self.event)
            return 0

        self._qi = _QI(qi)
        self._addref = _ADDREF(addref)
        self._release = _RELEASE(release)
        self._invoke = _INVOKE(invoke)
        self.vtbl = _HandlerVtbl(self._qi, self._addref, self._release, self._invoke)
        self.obj = _Handler(ctypes.pointer(self.vtbl), 1)

    def pointer(self) -> c_void_p:
        return c_void_p(ctypes.addressof(self.obj))


class _CachedPool:
    def __init__(self) -> None:
        self.hmon = 0
        self.device = c_void_p()
        self.context = c_void_p()
        self.dxgi = c_void_p()
        self.winrt_device = c_void_p()
        self.item = c_void_p()
        self.pool = c_void_p()
        self.session = c_void_p()
        self.width = 0
        self.height = 0
        self.started = False
        self.token = c_int64(0)
        self.arrived: _Arrived | None = None
        self.poll_only = False

    def close(self) -> None:
        if self.pool and self.token.value and not self.poll_only:
            try:
                _fn(self.pool, 9, HRESULT, c_int64)(self.pool, self.token.value)
            except Exception:
                pass
        _close_winrt(self.session)
        _close_winrt(self.pool)
        _close_winrt(self.item)
        _release(self.winrt_device)
        _release(self.dxgi)
        _release(self.context)
        _release(self.device)
        if self.arrived and self.arrived.event:
            kernel32.CloseHandle(self.arrived.event)
        self.session = c_void_p()
        self.pool = c_void_p()
        self.item = c_void_p()
        self.started = False
        self.arrived = None

    def recreate(self, size: SizeInt32) -> None:
        hr = _fn(self.pool, 6, HRESULT, c_void_p, c_int32, c_int32, SizeInt32)(
            self.pool, self.winrt_device, DirectXPixelFormat_B8G8R8A8UIntNormalized, FRAMEPOOL_BUFFERS, size
        )
        if hr != 0:
            raise DesktopUnavailable("Direct3D11CaptureFramePool.Recreate failed")
        self.width = int(size.Width)
        self.height = int(size.Height)

    def try_get(self) -> c_void_p | None:
        nxt = c_void_p()
        hr = _fn(self.pool, 7, HRESULT, POINTER(c_void_p))(self.pool, byref(nxt))
        if hr == 0 and nxt:
            return nxt
        return None

    def _poll(self, timeout_ms: int) -> c_void_p | None:
        deadline = time.time() + max(int(timeout_ms), 1) / 1000.0
        while time.time() < deadline:
            nxt = self.try_get()
            if nxt:
                return nxt
            time.sleep(0.016)
        return None

    def wait_frame(self, timeout_ms: int) -> c_void_p:
        timeout_ms = max(int(timeout_ms), 50)
        nxt = self.try_get()
        if nxt:
            if self.arrived and self.arrived.event:
                kernel32.ResetEvent(self.arrived.event)
            return nxt
        if self.arrived and not self.poll_only:
            wait = kernel32.WaitForSingleObject(self.arrived.event, timeout_ms)
            if self.arrived.event:
                kernel32.ResetEvent(self.arrived.event)
            if wait == WAIT_TIMEOUT:
                nxt = self._poll(min(80, timeout_ms))
                if not nxt:
                    raise DesktopUnavailable(FRAME_ARRIVED_TIMEOUT)
                return nxt
            nxt = self.try_get() or self._poll(50)
            if not nxt:
                raise DesktopUnavailable(TRYGET_AFTER_ARRIVED)
            return nxt
        nxt = self._poll(timeout_ms)
        if not nxt:
            raise DesktopUnavailable(CAPTURE_TIMEOUT)
        return nxt


_CACHE_LOCK = threading.Lock()
_CACHE: dict[int, _CachedPool] = {}
_LAST_INVALIDATION = ""


def cached_session_count() -> int:
    return len(_CACHE)


def last_capture_invalidation() -> str:
    return _LAST_INVALIDATION


def invalidate_cached_sessions(reason: str = "device") -> None:
    global _LAST_INVALIDATION
    with _CACHE_LOCK:
        _LAST_INVALIDATION = reason
        for pool in list(_CACHE.values()):
            try:
                pool.close()
            except Exception:
                pass
        _CACHE.clear()


def _drop_pool(hmon: int, reason: str) -> None:
    global _LAST_INVALIDATION
    _LAST_INVALIDATION = reason
    pool = _CACHE.pop(int(hmon), None)
    if pool:
        try:
            pool.close()
        except Exception:
            pass


def _create_item(hwnd: int) -> tuple[c_void_p, SizeInt32, int]:
    interop = _ro_factory(RC_ITEM, IID_IGraphicsCaptureItemInterop)
    hmon = int(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0)
    item = c_void_p()
    hr = _fn(interop, 4, HRESULT, wintypes.HMONITOR, POINTER(GUID), POINTER(c_void_p))(
        interop, hmon, byref(IID_IGraphicsCaptureItem), byref(item)
    )
    _release(interop)
    if hr != 0 or not item:
        raise DesktopUnavailable(f"IGraphicsCaptureItemInterop.CreateForMonitor failed 0x{hr & 0xFFFFFFFF:08X}")
    size = SizeInt32()
    hr = _fn(item, 7, HRESULT, POINTER(SizeInt32))(item, byref(size))
    if hr != 0 or size.Width < 1 or size.Height < 1:
        _release(item)
        raise DesktopUnavailable("GraphicsCaptureItem.Size failed")
    return item, size, hmon


def _ensure_pool(hwnd: int) -> _CachedPool:
    item, size, hmon = _create_item(hwnd)
    cached = _CACHE.get(hmon)
    if cached is not None:
        try:
            if cached.width != int(size.Width) or cached.height != int(size.Height):
                cached.recreate(size)
            _release(item)
            return cached
        except Exception as exc:
            _drop_pool(hmon, f"{CACHE_FAILED}{exc}")
    pool = _new_pool(hwnd, item, size, hmon)
    _CACHE[hmon] = pool
    try:
        from computer_use.win_uia import note_capture_session

        note_capture_session()
    except Exception:
        pass
    return pool


def _new_pool(_hwnd: int, item: c_void_p, size: SizeInt32, hmon: int) -> _CachedPool:
    cached = _CachedPool()
    cached.hmon = hmon
    cached.item = item
    cached.width = int(size.Width)
    cached.height = int(size.Height)

    device = c_void_p()
    context = c_void_p()
    d3d11.D3D11CreateDevice.restype = HRESULT
    hr = d3d11.D3D11CreateDevice(
        None, D3D_DRIVER_TYPE_HARDWARE, None, D3D11_CREATE_DEVICE_BGRA_SUPPORT, None, 0, D3D11_SDK_VERSION, byref(device), None, byref(context)
    )
    if hr != 0 or not device:
        _release(item)
        raise DesktopUnavailable("D3D11CreateDevice failed")
    cached.device = device
    cached.context = context
    dxgi = c_void_p()
    hr = _fn(device, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(device, byref(IID_IDXGIDevice), byref(dxgi))
    if hr != 0:
        cached.close()
        raise DesktopUnavailable("cast D3D device to IDXGIDevice")
    cached.dxgi = dxgi
    winrt_device = c_void_p()
    d3d11.CreateDirect3D11DeviceFromDXGIDevice.restype = HRESULT
    d3d11.CreateDirect3D11DeviceFromDXGIDevice.argtypes = [c_void_p, POINTER(c_void_p)]
    hr = d3d11.CreateDirect3D11DeviceFromDXGIDevice(dxgi, byref(winrt_device))
    if hr != 0 or not winrt_device:
        cached.close()
        raise DesktopUnavailable("CreateDirect3D11DeviceFromDXGIDevice failed")
    cached.winrt_device = winrt_device

    statics = _ro_factory(RC_POOL, IID_IDirect3D11CaptureFramePoolStatics2)
    pool = c_void_p()
    hr = _fn(statics, 6, HRESULT, c_void_p, c_int32, c_int32, SizeInt32, POINTER(c_void_p))(
        statics, winrt_device, DirectXPixelFormat_B8G8R8A8UIntNormalized, FRAMEPOOL_BUFFERS, size, byref(pool)
    )
    _release(statics)
    if hr != 0 or not pool:
        cached.close()
        raise DesktopUnavailable("Direct3D11CaptureFramePool.CreateFreeThreaded failed")
    cached.pool = pool

    session = c_void_p()
    hr = _fn(pool, 10, HRESULT, c_void_p, POINTER(c_void_p))(pool, item, byref(session))
    if hr != 0 or not session:
        cached.close()
        raise DesktopUnavailable("CreateCaptureSession failed")
    cached.session = session

    try:
        sess2 = _qi(session, IID_IGraphicsCaptureSession2)
    except DesktopUnavailable:
        sess2 = None
    if sess2:
        # Official listing 14003e341: SetIsCursorCaptureEnabled(True).
        hr = _fn(sess2, 7, HRESULT, ctypes.c_ubyte)(sess2, 1)
        _release(sess2)
        if hr != 0:
            cached.close()
            raise DesktopUnavailable("SetIsCursorCaptureEnabled failed")
    try:
        sess3 = _qi(session, IID_IGraphicsCaptureSession3)
    except DesktopUnavailable:
        sess3 = None
    if sess3:
        hr = _fn(sess3, 7, HRESULT, ctypes.c_ubyte)(sess3, 0)
        _release(sess3)
        if hr != 0:
            cached.close()
            raise DesktopUnavailable("SetIsBorderRequired failed")

    arrived = _Arrived()
    token = c_int64(0)
    hr = _fn(pool, 8, HRESULT, c_void_p, POINTER(c_int64))(pool, arrived.pointer(), byref(token))
    if hr != 0:
        cached.poll_only = True
        kernel32.CloseHandle(arrived.event)
        arrived.event = 0
        cached.arrived = None
    else:
        cached.arrived = arrived
        cached.token = token

    hr = _fn(session, 6, HRESULT)(session)
    if hr != 0:
        cached.close()
        raise DesktopUnavailable("StartCapture failed")
    cached.started = True
    return cached


def capture_hwnd_wgc(hwnd: int, timeout_ms: int = 800) -> CaptureFrame:
    enable_thread_dpi_awareness()
    _ro_init()
    try:
        from computer_use.overlay_win import exclude_overlay_from_capture

        exclude_overlay_from_capture()
    except Exception:
        pass
    with _CACHE_LOCK:
        try:
            cached = _ensure_pool(hwnd)
        except DesktopUnavailable as exc:
            raise DesktopUnavailable(f"{CACHE_FAILED}{exc}") from exc
        frame = cached.wait_frame(timeout_ms)
        surface = c_void_p()
        hr = _fn(frame, 6, HRESULT, POINTER(c_void_p))(frame, byref(surface))
        if hr != 0 or not surface:
            _release(frame)
            raise DesktopUnavailable("Direct3D11CaptureFrame.Surface failed")
        left, top, win_w, win_h = window_rect(hwnd)
        mon = monitor_frame_for_hwnd(hwnd)
        crop_x, crop_y, crop_w, crop_h = crop_window_from_monitor(mon, left, top, win_w, win_h)
        dpi = window_dpi(hwnd)
        scaled = scaled_size(crop_w, crop_h, dpi)
        try:
            from computer_use.jpeg_winrt import encode_jpeg_from_surface

            jpeg = encode_jpeg_from_surface(surface, bounds=(crop_x, crop_y, crop_w, crop_h), scaled=scaled)
            _release(surface)
            _release(frame)
            return CaptureFrame(jpeg, left, top, crop_w, crop_h, dpi, "image/jpeg")
        except Exception:
            pass
        # Fallback only: GPU crop then JPEG (not the official order).
        cropped_surface = _crop_d3d_surface(cached.device, cached.context, surface, crop_x, crop_y, crop_w, crop_h)
        if cropped_surface is not None:
            try:
                from computer_use.jpeg_winrt import encode_jpeg_from_surface

                jpeg = encode_jpeg_from_surface(cropped_surface, bounds=None, scaled=scaled)
                _release(cropped_surface)
                _release(surface)
                _release(frame)
                return CaptureFrame(jpeg, left, top, crop_w, crop_h, dpi, "image/jpeg")
            except Exception:
                _release(cropped_surface)
        jpeg = _encode_staging(cached, surface, left, top, win_w, win_h, crop_x, crop_y, crop_w, crop_h, dpi)
        _release(surface)
        _release(frame)
        return jpeg


def _encode_staging(
    cached: _CachedPool,
    surface: c_void_p,
    left: int,
    top: int,
    win_w: int,
    win_h: int,
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    dpi: int,
) -> CaptureFrame:
    access = _qi(surface, IID_IDirect3DDxgiInterfaceAccess)
    texture = c_void_p()
    hr = _fn(access, 3, HRESULT, POINTER(GUID), POINTER(c_void_p))(access, byref(IID_ID3D11Texture2D), byref(texture))
    if hr != 0:
        raise DesktopUnavailable("GetInterface texture failed")
    desc = D3D11_TEXTURE2D_DESC()
    _fn(texture, 10, None, POINTER(D3D11_TEXTURE2D_DESC))(texture, byref(desc))
    desc.Usage = D3D11_USAGE_STAGING
    desc.BindFlags = 0
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ
    desc.MiscFlags = 0
    staging = c_void_p()
    hr = _fn(cached.device, 5, HRESULT, POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p))(
        cached.device, byref(desc), None, byref(staging)
    )
    if hr != 0:
        raise DesktopUnavailable("CreateTexture2D staging failed")
    _fn(cached.context, 47, None, c_void_p, c_void_p)(cached.context, staging, texture)
    mapped = D3D11_MAPPED_SUBRESOURCE()
    hr = _fn(cached.context, 14, HRESULT, c_void_p, c_uint, c_uint, c_uint, POINTER(D3D11_MAPPED_SUBRESOURCE))(
        cached.context, staging, 0, 1, 0, byref(mapped)
    )
    if hr != 0:
        raise DesktopUnavailable("Map staging failed")
    width, height = int(desc.Width), int(desc.Height)
    pitch = int(mapped.RowPitch)
    raw = ctypes.string_at(mapped.pData, pitch * height)
    _fn(cached.context, 15, None, c_void_p, c_uint)(cached.context, staging, 0)
    bgra = bytearray(width * height * 4)
    for y in range(height):
        row = raw[y * pitch : y * pitch + width * 4]
        bgra[y * width * 4 : (y + 1) * width * 4] = row
    from computer_use.wgc import clamp_crop

    tile_x, tile_y, tile_w, tile_h = clamp_crop(crop_x, crop_y, crop_w, crop_h, width, height)
    jpeg = _encode_jpeg(tile_w, tile_h, crop_rgba(bytes(bgra), width, height, tile_x, tile_y, tile_w, tile_h))
    return CaptureFrame(jpeg, left, top, tile_w, tile_h, dpi, "image/jpeg")


def _encode_jpeg(width: int, height: int, bgra: bytes) -> bytes:
    try:
        from computer_use.jpeg_winrt import encode_jpeg_bgra as encode_winrt

        return encode_winrt(width, height, bgra)
    except Exception:
        return encode_jpeg_gdiplus(width, height, bgra)


atexit.register(lambda: invalidate_cached_sessions("exit"))
