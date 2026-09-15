"""JPEG via WinRT SoftwareBitmap + BitmapEncoder (helper capture/image.rs)."""

from __future__ import annotations

import ctypes
from ctypes import HRESULT, POINTER, byref, c_uint, c_void_p, wintypes

from computer_use.errors import DesktopUnavailable
from computer_use.official_constants import official_capture_value
from computer_use.wgc import clamp_crop
from computer_use.winrt_common import (
    IID_IBufferByteAccess,
    await_operation,
    delete_hstring,
    fn,
    guid,
    hstring,
    qi,
    release,
    ro_activate,
    ro_factory,
    ro_init,
)

IID_IBufferFactory = guid("71AF914D-C10F-484B-BC50-14BC623B3A27")
IID_ISoftwareBitmapStatics = guid("DF0385DB-672F-4A9D-806E-C2442F343E86")
IID_IBitmapEncoderStatics = guid("A74356A7-A4E4-4EB9-8E40-564DE7E1CCB2")
IID_IBitmapEncoderWithSoftwareBitmap = guid("686CD241-4330-4C77-ACE4-0334968B1768")
IID_IDataReaderFactory = guid("D7527847-57DA-4E15-914C-06806699A098")
IID_IBitmapTypedValueFactory = guid("92DBB599-CE13-46BB-9545-CB3A3F63EB8B")
IID_IPropertyValueStatics = guid("629BDBC8-D932-4FF4-96B9-8D96C5C1E858")
BitmapPixelFormat_Bgra8 = 87
BitmapAlphaMode_Straight = 1
PropertyType_Single = 8
UNEXPECTED_PIXEL = "captured bitmap has unexpected pixel format: "


#: Official PropertyValue::CreateSingle(0.8f) (parity/official-constants.json ->
#: capture.jpegQuality). Read from the single source when it is present.
JPEG_QUALITY = float(official_capture_value("jpegQuality", 0.8))


class BitmapBounds(ctypes.Structure):
    _fields_ = [("X", c_uint), ("Y", c_uint), ("Width", c_uint), ("Height", c_uint)]


def encode_jpeg_from_surface(
    surface,
    *,
    quality: float = JPEG_QUALITY,
    bounds: tuple[int, int, int, int] | None = None,
    scaled: tuple[int, int] | None = None,
) -> bytes:
    """Official: SoftwareBitmap.CreateCopyFromSurfaceAsync + ImageQuality JPEG."""
    ro_init()
    statics = ro_factory("Windows.Graphics.Imaging.SoftwareBitmap", IID_ISoftwareBitmapStatics)
    op = c_void_p()
    hr = fn(statics, 11, HRESULT, c_void_p, POINTER(c_void_p))(statics, surface, byref(op))
    if hr != 0 or not op:
        raise DesktopUnavailable(f"CreateCopyFromSurfaceAsync 0x{hr & 0xFFFFFFFF:08X}")
    bitmap = await_operation(op)
    if not getattr(bitmap, "value", bitmap):
        raise DesktopUnavailable("CreateCopyFromSurfaceAsync returned empty bitmap")
    _require_bgra8(bitmap)
    # Official image.rs: full-surface copy, then CPU crop, then JPEG (ScaledWidth/Height).
    if bounds is not None:
        pw, ph = _bitmap_size(bitmap)
        crop = clamp_crop(bounds[0], bounds[1], bounds[2], bounds[3], pw, ph)
        bgra = _software_bitmap_bgra(bitmap)
        from computer_use.win_capture import crop_rgba

        tiled = crop_rgba(bgra, pw, ph, crop[0], crop[1], crop[2], crop[3])
        cropped = _bitmap_from_bgra(crop[2], crop[3], tiled)
        return _encode_software_bitmap(cropped, quality=quality, bounds=None, scaled=scaled)
    return _encode_software_bitmap(bitmap, quality=quality, bounds=None, scaled=scaled)


def _bitmap_from_bgra(width: int, height: int, bgra: bytes) -> c_void_p:
    stride = width * 4
    buffer_factory = ro_factory("Windows.Storage.Streams.Buffer", IID_IBufferFactory)
    ibuffer = c_void_p()
    hr = fn(buffer_factory, 6, HRESULT, c_uint, POINTER(c_void_p))(buffer_factory, stride * height, byref(ibuffer))
    if hr != 0:
        raise DesktopUnavailable("Buffer.Create failed")
    access = qi(ibuffer, IID_IBufferByteAccess)
    ptr = c_void_p()
    hr = fn(access, 3, HRESULT, POINTER(c_void_p))(access, byref(ptr))
    if hr != 0:
        raise DesktopUnavailable("IBufferByteAccess.Buffer failed")
    ctypes.memmove(ptr, bgra, stride * height)
    fn(ibuffer, 8, HRESULT, c_uint)(ibuffer, stride * height)
    statics = ro_factory("Windows.Graphics.Imaging.SoftwareBitmap", IID_ISoftwareBitmapStatics)
    bitmap = c_void_p()
    hr = fn(statics, 9, HRESULT, c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
        statics, ibuffer, BitmapPixelFormat_Bgra8, width, height, byref(bitmap)
    )
    if hr != 0 or not bitmap:
        raise DesktopUnavailable(f"CreateCopyFromBuffer 0x{hr & 0xFFFFFFFF:08X}")
    return bitmap


def _software_bitmap_bgra(bitmap: c_void_p) -> bytes:
    width, height = _bitmap_size(bitmap)
    stride = width * 4
    buffer_factory = ro_factory("Windows.Storage.Streams.Buffer", IID_IBufferFactory)
    ibuffer = c_void_p()
    hr = fn(buffer_factory, 6, HRESULT, c_uint, POINTER(c_void_p))(buffer_factory, stride * height, byref(ibuffer))
    if hr != 0:
        raise DesktopUnavailable("Buffer.Create failed")
    fn(ibuffer, 8, HRESULT, c_uint)(ibuffer, stride * height)
    # ISoftwareBitmap.CopyToBuffer is slot 16 on the default interface.
    hr = fn(bitmap, 16, HRESULT, c_void_p)(bitmap, ibuffer)
    if hr != 0:
        raise DesktopUnavailable(f"SoftwareBitmap.CopyToBuffer 0x{hr & 0xFFFFFFFF:08X}")
    access = qi(ibuffer, IID_IBufferByteAccess)
    ptr = c_void_p()
    hr = fn(access, 3, HRESULT, POINTER(c_void_p))(access, byref(ptr))
    if hr != 0:
        raise DesktopUnavailable("IBufferByteAccess.Buffer failed")
    return ctypes.string_at(ptr, stride * height)


def encode_jpeg_bgra(width: int, height: int, bgra: bytes, quality: float = JPEG_QUALITY) -> bytes:
    if width < 1 or height < 1:
        raise ValueError("jpeg size")
    stride = width * 4
    if len(bgra) < stride * height:
        raise ValueError("bgra length")
    ro_init()
    buffer_factory = ro_factory("Windows.Storage.Streams.Buffer", IID_IBufferFactory)
    ibuffer = c_void_p()
    hr = fn(buffer_factory, 6, HRESULT, c_uint, POINTER(c_void_p))(buffer_factory, stride * height, byref(ibuffer))
    if hr != 0:
        raise DesktopUnavailable("Buffer.Create failed")
    access = qi(ibuffer, IID_IBufferByteAccess)
    ptr = c_void_p()
    hr = fn(access, 3, HRESULT, POINTER(c_void_p))(access, byref(ptr))
    if hr != 0:
        raise DesktopUnavailable("IBufferByteAccess.Buffer failed")
    ctypes.memmove(ptr, bgra, stride * height)
    fn(ibuffer, 8, HRESULT, c_uint)(ibuffer, stride * height)
    statics = ro_factory("Windows.Graphics.Imaging.SoftwareBitmap", IID_ISoftwareBitmapStatics)
    bitmap = c_void_p()
    hr = fn(statics, 9, HRESULT, c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
        statics, ibuffer, BitmapPixelFormat_Bgra8, width, height, byref(bitmap)
    )
    if hr != 0 or not bitmap:
        raise DesktopUnavailable(f"CreateCopyFromBuffer 0x{hr & 0xFFFFFFFF:08X}")
    return _encode_software_bitmap(bitmap, quality=quality)


def _encode_software_bitmap(
    bitmap: c_void_p,
    *,
    quality: float = JPEG_QUALITY,
    bounds: tuple[int, int, int, int] | None = None,
    scaled: tuple[int, int] | None = None,
) -> bytes:
    stream = ro_activate("Windows.Storage.Streams.InMemoryRandomAccessStream")
    enc_statics = ro_factory("Windows.Graphics.Imaging.BitmapEncoder", IID_IBitmapEncoderStatics)
    jpeg_id = guid("00000000-0000-0000-0000-000000000000")
    hr = fn(enc_statics, 7, HRESULT, POINTER(type(jpeg_id)))(enc_statics, byref(jpeg_id))
    if hr != 0:
        raise DesktopUnavailable("get_JpegEncoderId failed")
    op = c_void_p()
    hr = fn(enc_statics, 13, HRESULT, type(jpeg_id), c_void_p, POINTER(c_void_p))(enc_statics, jpeg_id, stream, byref(op))
    if hr != 0:
        raise DesktopUnavailable(f"BitmapEncoder.CreateAsync 0x{hr & 0xFFFFFFFF:08X}")
    encoder = await_operation(op)
    with_bmp = qi(encoder, IID_IBitmapEncoderWithSoftwareBitmap)
    hr = fn(with_bmp, 6, HRESULT, c_void_p)(with_bmp, bitmap)
    if hr != 0:
        raise DesktopUnavailable("SetSoftwareBitmap failed")
    if bounds is not None or scaled is not None:
        transform = c_void_p()
        if fn(encoder, 15, HRESULT, POINTER(c_void_p))(encoder, byref(transform)) != 0 or not transform:
            raise DesktopUnavailable("BitmapEncoder.BitmapTransform failed")
        if bounds is not None:
            box = BitmapBounds(int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3]))
            if fn(transform, 17, HRESULT, BitmapBounds)(transform, box) != 0:
                raise DesktopUnavailable("BitmapEncoder.BitmapTransform failed")
        if scaled is not None:
            # IBitmapTransform put_ScaledWidth=7 put_ScaledHeight=9 (official image.rs)
            if fn(transform, 7, HRESULT, c_uint)(transform, int(scaled[0])) != 0:
                raise DesktopUnavailable("BitmapEncoder.BitmapTransform failed")
            if fn(transform, 9, HRESULT, c_uint)(transform, int(scaled[1])) != 0:
                raise DesktopUnavailable("BitmapEncoder.BitmapTransform failed")
        release(transform)
    _apply_image_quality(encoder, quality)
    flush = c_void_p()
    hr = fn(encoder, 19, HRESULT, POINTER(c_void_p))(encoder, byref(flush))
    if hr != 0:
        raise DesktopUnavailable("FlushAsync failed")
    await_operation(flush)
    return _read_jpeg_stream(stream)


def _require_bgra8(bitmap: c_void_p) -> None:
    fmt = ctypes.c_int()
    alpha = ctypes.c_int()
    if fn(bitmap, 6, HRESULT, POINTER(ctypes.c_int))(bitmap, byref(fmt)) != 0:
        raise DesktopUnavailable("SoftwareBitmap.PixelWidth failed")  # size/format probe
    fn(bitmap, 7, HRESULT, POINTER(ctypes.c_int))(bitmap, byref(alpha))
    if int(fmt.value) != BitmapPixelFormat_Bgra8 or (int(alpha.value) not in (0, BitmapAlphaMode_Straight)):
        raise DesktopUnavailable(f"{UNEXPECTED_PIXEL}{int(fmt.value)}")


def _bitmap_size(bitmap: c_void_p) -> tuple[int, int]:
    width = c_uint()
    height = c_uint()
    if fn(bitmap, 8, HRESULT, POINTER(c_uint))(bitmap, byref(width)) != 0:
        raise DesktopUnavailable("SoftwareBitmap.PixelWidth failed")
    if fn(bitmap, 9, HRESULT, POINTER(c_uint))(bitmap, byref(height)) != 0:
        raise DesktopUnavailable("SoftwareBitmap.PixelHeight failed")
    return int(width.value), int(height.value)


def _apply_image_quality(encoder: c_void_p, quality: float) -> None:
    try:
        pv = ro_factory("Windows.Foundation.PropertyValue", IID_IPropertyValueStatics)
        boxed = c_void_p()
        if fn(pv, 14, HRESULT, ctypes.c_float, POINTER(c_void_p))(pv, ctypes.c_float(quality), byref(boxed)) != 0:
            return
        tvf = ro_factory("Windows.Graphics.Imaging.BitmapTypedValue", IID_IBitmapTypedValueFactory)
        typed = c_void_p()
        if fn(tvf, 6, HRESULT, c_void_p, ctypes.c_int, POINTER(c_void_p))(tvf, boxed, PropertyType_Single, byref(typed)) != 0:
            return
        propset = ro_activate("Windows.Graphics.Imaging.BitmapPropertySet")
        key = hstring("ImageQuality")
        replaced = ctypes.c_bool()
        fn(propset, 11, HRESULT, c_void_p, c_void_p, POINTER(ctypes.c_bool))(propset, key, typed, byref(replaced))
        delete_hstring(key)
        props = c_void_p()
        if fn(encoder, 7, HRESULT, POINTER(c_void_p))(encoder, byref(props)) != 0 or not props:
            return
        op = c_void_p()
        if fn(props, 6, HRESULT, c_void_p, POINTER(c_void_p))(props, propset, byref(op)) == 0 and op:
            await_operation(op)
    except Exception:
        return


def _read_jpeg_stream(stream: c_void_p) -> bytes:
    fn(stream, 11, HRESULT, ctypes.c_uint64)(stream, 0)
    input_stream = c_void_p()
    hr = fn(stream, 8, HRESULT, ctypes.c_uint64, POINTER(c_void_p))(stream, 0, byref(input_stream))
    if hr != 0:
        raise DesktopUnavailable("GetInputStreamAt failed")
    reader_factory = ro_factory("Windows.Storage.Streams.DataReader", IID_IDataReaderFactory)
    reader = c_void_p()
    hr = fn(reader_factory, 6, HRESULT, c_void_p, POINTER(c_void_p))(reader_factory, input_stream, byref(reader))
    size = ctypes.c_uint64()
    fn(stream, 6, HRESULT, POINTER(ctypes.c_uint64))(stream, byref(size))
    load = c_void_p()
    hr = fn(reader, 29, HRESULT, c_uint, POINTER(c_void_p))(reader, int(size.value), byref(load))
    if hr == 0 and load:
        try:
            await_operation(load)
        except DesktopUnavailable:
            pass
    buf = (ctypes.c_ubyte * max(int(size.value), 1))()
    fn(reader, 14, HRESULT, c_uint, ctypes.c_void_p)(reader, int(size.value), buf)
    data = bytes(buf)
    release(reader)
    release(input_stream)
    if not data.startswith(b"\xff\xd8"):
        raise DesktopUnavailable("WinRT BitmapEncoder did not produce JPEG")
    return data


def encode_jpeg_rgba(width: int, height: int, rgba: bytes, quality: float = JPEG_QUALITY) -> bytes:
    bgra = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        bgra[i] = rgba[i + 2]
        bgra[i + 1] = rgba[i + 1]
        bgra[i + 2] = rgba[i]
        bgra[i + 3] = rgba[i + 3]
    return encode_jpeg_bgra(width, height, bytes(bgra), quality)
