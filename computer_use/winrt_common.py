"""Shared WinRT/COM helpers for WGC, JPEG, and Composition."""

from __future__ import annotations

import time
from ctypes import HRESULT, POINTER, byref, c_int, c_void_p, wintypes
import ctypes

from computer_use.errors import DesktopUnavailable

combase = ctypes.WinDLL("combase")
ole32 = ctypes.oledll.ole32
RO_INIT_MULTITHREADED = 1
RO_INIT_SINGLETHREADED = 0
COINIT_APARTMENTTHREADED = 0x2
IID_IAsyncInfo = None  # filled below


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8).from_buffer_copy(data4))


IID_IAsyncInfo = guid("00000036-0000-0000-C000-000000000046")
IID_IBufferByteAccess = guid("905A0FEF-BC53-11DF-8C49-001E4FC686DA")


def vtbl(obj: c_void_p):
    return ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))


def fn(obj: c_void_p, index: int, restype, *argtypes):
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl(obj)[index])


def release(obj: c_void_p | None) -> None:
    if obj:
        fn(obj, 2, ctypes.c_ulong)(obj)


def qi(obj: c_void_p, iid: GUID) -> c_void_p:
    out = c_void_p()
    hr = fn(obj, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(obj, byref(iid), byref(out))
    if hr != 0 or not out:
        raise DesktopUnavailable(f"QI 0x{hr & 0xFFFFFFFF:08X}")
    return out


def hstring(text: str) -> c_void_p:
    hs = c_void_p()
    combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, POINTER(c_void_p)]
    combase.WindowsCreateString.restype = HRESULT
    hr = combase.WindowsCreateString(text, len(text), byref(hs))
    if hr != 0:
        raise DesktopUnavailable("WindowsCreateString failed")
    return hs


def delete_hstring(hs: c_void_p | None) -> None:
    if hs:
        combase.WindowsDeleteString(hs)


def ro_init() -> None:
    combase.RoInitialize.argtypes = [ctypes.c_uint]
    combase.RoInitialize.restype = HRESULT
    combase.RoInitialize(RO_INIT_MULTITHREADED)
    ole32.CoInitializeEx(None, 0)


def ro_init_sta() -> None:
    """Overlay UI thread: official compositor/DWrite want STA + single-threaded RoInit."""
    combase.RoInitialize.argtypes = [ctypes.c_uint]
    combase.RoInitialize.restype = HRESULT
    combase.RoInitialize(RO_INIT_SINGLETHREADED)
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)


def ro_factory(runtime_class: str, iid: GUID) -> c_void_p:
    hs = hstring(runtime_class)
    factory = c_void_p()
    combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
    combase.RoGetActivationFactory.restype = HRESULT
    hr = combase.RoGetActivationFactory(hs, byref(iid), byref(factory))
    delete_hstring(hs)
    if hr != 0 or not factory:
        raise DesktopUnavailable(f"RoGetActivationFactory({runtime_class}) 0x{hr & 0xFFFFFFFF:08X}")
    return factory


def ro_activate(runtime_class: str) -> c_void_p:
    hs = hstring(runtime_class)
    instance = c_void_p()
    combase.RoActivateInstance.argtypes = [c_void_p, POINTER(c_void_p)]
    combase.RoActivateInstance.restype = HRESULT
    hr = combase.RoActivateInstance(hs, byref(instance))
    delete_hstring(hs)
    if hr != 0 or not instance:
        raise DesktopUnavailable(f"RoActivateInstance({runtime_class}) 0x{hr & 0xFFFFFFFF:08X}")
    return instance


def await_operation(op: c_void_p, timeout: float = 5.0) -> c_void_p:
    info = qi(op, IID_IAsyncInfo)
    deadline = time.time() + timeout
    status = c_int()
    while time.time() < deadline:
        hr = fn(info, 7, HRESULT, POINTER(c_int))(info, byref(status))
        if hr == 0 and int(status.value) == 1:
            result = c_void_p()
            get = fn(op, 8, HRESULT, POINTER(c_void_p))
            try:
                hr = get(op, byref(result))
            except OSError:
                return c_void_p()
            if hr != 0:
                raise DesktopUnavailable(f"GetResults 0x{hr & 0xFFFFFFFF:08X}")
            return result
        if hr == 0 and int(status.value) >= 2:
            err = HRESULT()
            fn(info, 8, HRESULT, POINTER(HRESULT))(info, byref(err))
            raise DesktopUnavailable(f"async failed status={status.value} 0x{int(err.value) & 0xFFFFFFFF:08X}")
        time.sleep(0.01)
    raise DesktopUnavailable("WinRT async timed out")
