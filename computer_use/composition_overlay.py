"""Windows.UI.Composition overlay — official display + cursor drawing-surface pipeline.

Display bar: DesktopWindowTarget + color sprite.
Cursor: ICompositorInterop graphics device → CreateDrawingSurface →
ICompositionDrawingSurfaceInterop BeginDraw/EndDraw (D2D path geometry, GDI fallback)
→ SurfaceBrush on a sprite parented by a motion visual (offset/rotation/scale).
"""

from __future__ import annotations

import ctypes
from ctypes import HRESULT, POINTER, byref, c_void_p, wintypes

from computer_use.errors import DesktopUnavailable
from computer_use.winrt_common import fn, guid, qi, release, ro_activate, ro_init, ro_init_sta

# Official rdata 0x133a48 — GPU path expression graph (P0–P6 halves).
PATH_OFFSET_EXPRESSION = (
    "motion.SegmentCount < 1.5 ? motion.SingleSegmentPoint : "
    "(motion.Progress < 0.5 ? motion.FirstHalfPoint : motion.SecondHalfPoint)"
)
FIRST_HALF_T = "Min(1.0,Max(0.0,motion.Progress*2.0))"
SECOND_HALF_T = "Min(1.0,Max(0.0,(motion.Progress-0.5)*2.0))"
SHIMMER_OFFSET_EXPRESSION = "Vector3(shimmer.StartX+shimmer.TravelX*shimmer.Progress,0.0,0.0)"
DEVICE_LOST_HRS = {
    0x887A0005,  # DXGI_ERROR_DEVICE_REMOVED
    0x887A0007,  # DXGI_ERROR_DEVICE_RESET
    0x887A0020,  # DXGI_ERROR_INVALID_CALL after loss
    0x8899000C,  # D2DERR_RECREATE_TARGET
    0x80000013,  # RO_E_CLOSED
}
ICompositionObject_StartAnimation = 9
ICompositionObject_StopAnimation = 10
ICompositor_CreateExpressionAnimation = 13
ICompositionDrawingSurfaceInterop_Resize = 5
IDWriteTextFormat_SetReadingDirection = 6
IDWriteTextLayout_GetMetrics = 60
IDWriteTextLayout1_SetCharacterSpacing = 69
IID_IDWriteTextLayout1 = guid("9064F615-80E6-424C-A9C6-5D24064CF836")
DWRITE_READING_DIRECTION_LTR = 0
DWRITE_READING_DIRECTION_RTL = 1
D2D1_FILL_ROUNDED_RECTANGLE = 19
D2D1_DRAW_LINE = 15


def _cubic_expr(t: str, a: str, b: str, c: str, d: str) -> str:
    omt = f"(1.0-({t}))"
    return (
        f"{omt}*{omt}*{omt}*{a}+3.0*{omt}*{omt}*({t})*{b}+3.0*{omt}*({t})*({t})*{c}+({t})*({t})*({t})*{d}"
    )


FIRST_HALF_POINT_EXPRESSION = _cubic_expr(FIRST_HALF_T, "motion.P0", "motion.P1", "motion.P2", "motion.P3")
SECOND_HALF_POINT_EXPRESSION = _cubic_expr(SECOND_HALF_T, "motion.P3", "motion.P4", "motion.P5", "motion.P6")
SINGLE_SEGMENT_POINT_EXPRESSION = "Lerp(motion.P0, motion.P6, motion.Progress)"


def is_device_lost(hr: int) -> bool:
    return (int(hr) & 0xFFFFFFFF) in DEVICE_LOST_HRS


def force_cursor_warp() -> bool:
    import os

    for key in ("DSH_CUA_CURSOR_FORCE_WARP", "CODEX_CUA_CURSOR_FORCE_WARP"):
        value = (os.environ.get(key) or "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
    return False

IID_ICompositor = guid("B403CA50-7F8C-4E83-985F-CC45060036D8")
IID_ICompositorDesktopInterop = guid("29E691FA-4567-4DCA-B319-D0F207EB6807")
IID_ICompositorInterop = guid("25297D5C-3AD4-4C9C-B5CF-E36A38512330")
IID_ICompositionTarget = guid("A1BEA8BA-D726-4663-8129-6B5E7927FFA6")
IID_ISpriteVisual = guid("08E05581-1AD1-4F97-9757-402D76E4233B")
IID_IVisual = guid("117E202D-A859-4C89-873B-C2AA566788E3")
IID_ICompositionGraphicsDevice = guid("FB22C6E1-8A33-48E2-9A8D-5B19C6F3B1C5")
IID_ICompositionDrawingSurfaceInterop = guid("FD04E6E3-FE0C-4C3C-AB19-A07601A57680")
IID_ID2D1Factory1 = guid("BB12D362-DAEE-4B9A-AA1D-14BA401CFA1F")
IID_ID2D1DeviceContext = guid("E8F7FE7A-191C-466D-AD95-975678BDA998")
IID_IDXGIDevice = guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C")
IID_IDXGISurface = guid("CAFCB56C-6AC3-4889-BF47-9E23BBD260EC")
IID_IDXGISurface1 = guid("4AE63092-6327-4C1B-80AE-BFE12EA32B86")

D3D11_SDK_VERSION = 7
D3D_DRIVER_TYPE_HARDWARE = 1
D3D_DRIVER_TYPE_WARP = 5
D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
DXGI_FORMAT_B8G8R8A8_UNORM = 87
DirectXPixelFormat_B8G8R8A8UIntNormalized = 87
DirectXAlphaMode_Premultiplied = 1
D2D1_FACTORY_TYPE_SINGLE_THREADED = 0
D2D1_FIGURE_BEGIN_FILLED = 0
D2D1_FIGURE_END_CLOSED = 1
CURSOR_GLYPH = 64
# ICompositor vtable (Windows 11): IInspectable 0-5, then an extra slot at 6.
# Empirically: CreateColorBrushWithColor=8, CreateContainerVisual=9,
# CreateSpriteVisual=22, CreateSurfaceBrush=23, CreateSurfaceBrushWithSurface=24.
ICompositor_CreateColorBrushWithColor = 8
ICompositor_CreateContainerVisual = 9
ICompositor_CreateSpriteVisual = 22
ICompositor_CreateSurfaceBrush = 23
ICompositor_CreateSurfaceBrushWithSurface = 24


class DispatcherQueueOptions(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("threadType", ctypes.c_int), ("apartmentType", ctypes.c_int)]


class Color(ctypes.Structure):
    _fields_ = [("A", ctypes.c_ubyte), ("R", ctypes.c_ubyte), ("G", ctypes.c_ubyte), ("B", ctypes.c_ubyte)]


class Vector2(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]


class Vector3(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float), ("Z", ctypes.c_float)]


class SizeF(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_float), ("Height", ctypes.c_float)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class D2D_COLOR_F(ctypes.Structure):
    _fields_ = [("r", ctypes.c_float), ("g", ctypes.c_float), ("b", ctypes.c_float), ("a", ctypes.c_float)]


class D2D_POINT_2F(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]


class D2D1_MATRIX_3X2_F(ctypes.Structure):
    _fields_ = [
        ("m11", ctypes.c_float),
        ("m12", ctypes.c_float),
        ("m21", ctypes.c_float),
        ("m22", ctypes.c_float),
        ("dx", ctypes.c_float),
        ("dy", ctypes.c_float),
    ]


class D2D1_ELLIPSE(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("radiusX", ctypes.c_float), ("radiusY", ctypes.c_float)]


class D2D_RECT_F(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_float),
        ("top", ctypes.c_float),
        ("right", ctypes.c_float),
        ("bottom", ctypes.c_float),
    ]


class D2D1_ROUNDED_RECT(ctypes.Structure):
    _fields_ = [("rect", D2D_RECT_F), ("radiusX", ctypes.c_float), ("radiusY", ctypes.c_float)]


class DWRITE_TEXT_METRICS(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_float),
        ("top", ctypes.c_float),
        ("width", ctypes.c_float),
        ("widthIncludingTrailingWhitespace", ctypes.c_float),
        ("height", ctypes.c_float),
        ("layoutWidth", ctypes.c_float),
        ("layoutHeight", ctypes.c_float),
        ("maxBidiReorderingDepth", ctypes.c_uint32),
        ("lineCount", ctypes.c_uint32),
    ]


class DWRITE_TEXT_RANGE(ctypes.Structure):
    _fields_ = [("startPosition", ctypes.c_uint32), ("length", ctypes.c_uint32)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


IID_IDWriteFactory = guid("B859EE5A-D838-4B5B-A2E8-1ADC7D93DB48")
IID_ICompositionObject = guid("BC261D84-1DA1-4D11-AB99-417D47E3D8DC")
DWRITE_FACTORY_TYPE_SHARED = 0
DWRITE_FONT_WEIGHT_SEMI_BOLD = 600
DWRITE_FONT_STYLE_NORMAL = 0
DWRITE_FONT_STRETCH_NORMAL = 5
ICompositor_CreatePropertySet = 18
ICompositor_CreateScalarKeyFrameAnimation = 20
ICompositor_CreateVector3KeyFrameAnimation = 26

_attached = False
_keep: list[c_void_p] = []
_cursor_visual = None
_motion_visual = None
_sprite_visual = None
_surface_interop = None
_press_interop = None
_idle_surface = None
_press_surface = None
_cursor_brush = None
_graphics_device = None
_compositor_obj = None
_d2d_factory = None
_cursor_origin = (0.0, 0.0)
_cursor_size = CURSOR_GLYPH
_press_drawn = False
_device_lost = False
_display_visual = None
_display_compositor = None
_motion_propset = None
_last_cursor_xy = (0.0, 0.0)
_last_cursor_pose: dict = {}
_path_objects: list[c_void_p] = []


def device_lost() -> bool:
    return _device_lost


def _mark_device_lost(hr: int | None = None) -> None:
    global _device_lost
    if hr is None or is_device_lost(hr):
        _device_lost = True


def _stop_named_animation(obj: c_void_p | None, name: str) -> None:
    if not obj:
        return
    try:
        from computer_use.winrt_common import delete_hstring, hstring

        key = hstring(name)
        fn(obj, ICompositionObject_StopAnimation, HRESULT, c_void_p)(obj, key)
        delete_hstring(key)
    except Exception:
        return


def _bind_expression(compositor: c_void_p, target: c_void_p, property_name: str, body: str, ref_name: str, ref_obj: c_void_p) -> c_void_p | None:
    from computer_use.winrt_common import delete_hstring, hstring

    expr = c_void_p()
    if fn(compositor, ICompositor_CreateExpressionAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(expr)) != 0:
        return None
    text = hstring(body)
    fn(expr, 17, HRESULT, c_void_p)(expr, text)
    delete_hstring(text)
    param = hstring(ref_name)
    fn(expr, 11, HRESULT, c_void_p, c_void_p)(expr, param, ref_obj)
    delete_hstring(param)
    key = hstring(property_name)
    fn(target, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(target, key, expr)
    delete_hstring(key)
    _keep.append(expr)
    return expr


def ensure_dispatcher_queue() -> None:
    core = ctypes.WinDLL("CoreMessaging")
    opts = DispatcherQueueOptions(ctypes.sizeof(DispatcherQueueOptions), 2, 2)  # CURRENT + STA
    controller = c_void_p()
    core.CreateDispatcherQueueController.argtypes = [DispatcherQueueOptions, POINTER(c_void_p)]
    core.CreateDispatcherQueueController.restype = HRESULT
    hr = core.CreateDispatcherQueueController(opts, byref(controller))
    if hr not in (0, 1) and controller.value is None:
        if hr & 0xFFFFFFFF not in {0x8000000A, 0x80000010}:
            raise DesktopUnavailable(f"CreateDispatcherQueueController 0x{hr & 0xFFFFFFFF:08X}")
    if controller:
        _keep.append(controller)


def _compositor() -> c_void_p:
    raw = ro_activate("Windows.UI.Composition.Compositor")
    try:
        compositor = qi(raw, IID_ICompositor)
        _keep.append(raw)
        return compositor
    except DesktopUnavailable:
        return raw


def _dwrite_factory() -> c_void_p:
    dwrite = ctypes.WinDLL("dwrite")
    factory = c_void_p()
    dwrite.DWriteCreateFactory.restype = HRESULT
    dwrite.DWriteCreateFactory.argtypes = [ctypes.c_uint, c_void_p, POINTER(c_void_p)]
    hr = dwrite.DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED, byref(IID_IDWriteFactory), byref(factory))
    if hr != 0 or not factory:
        raise DesktopUnavailable(f"DWriteCreateFactory 0x{hr & 0xFFFFFFFF:08X}")
    _keep.append(factory)
    return factory


def _gdi_status_text(hdc: int, width: int, height: int, text: str) -> None:
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32.SetBkMode(hdc, 1)
    gdi32.SetTextColor(hdc, 0x00101010)
    font = gdi32.CreateFontW(22, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
    old = gdi32.SelectObject(hdc, font)
    rect = wintypes.RECT(0, 0, int(width), int(height))
    user32.DrawTextW(hdc, text, -1, byref(rect), 0x0001 | 0x0004 | 0x0020)
    gdi32.SelectObject(hdc, old)
    gdi32.DeleteObject(font)


def _measure_layout(layout: c_void_p) -> float | None:
    try:
        metrics = DWRITE_TEXT_METRICS()
        hr = fn(layout, IDWriteTextLayout_GetMetrics, HRESULT, POINTER(DWRITE_TEXT_METRICS))(layout, byref(metrics))
        if hr == 0:
            return float(metrics.widthIncludingTrailingWhitespace or metrics.width)
    except Exception:
        return None
    return None


def _set_character_spacing(layout: c_void_p, length: int) -> None:
    try:
        layout1 = qi(layout, IID_IDWriteTextLayout1)
        rng = DWRITE_TEXT_RANGE(0, max(int(length), 1))
        fn(
            layout1,
            IDWriteTextLayout1_SetCharacterSpacing,
            HRESULT,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            DWRITE_TEXT_RANGE,
        )(layout1, ctypes.c_float(0.15), ctypes.c_float(0.15), ctypes.c_float(0.0), rng)
        if layout1 is not layout:
            release(layout1)
    except Exception:
        return


def _make_text_layout(dw: c_void_p, text: str, width: float, height: float, *, rtl: bool) -> tuple[c_void_p | None, c_void_p | None]:
    fmt = c_void_p()
    family = ctypes.c_wchar_p("Segoe UI")
    locale = ctypes.c_wchar_p("en-US")
    hr = fn(
        dw, 13, HRESULT, ctypes.c_wchar_p, c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_wchar_p, POINTER(c_void_p)
    )(dw, family, None, DWRITE_FONT_WEIGHT_SEMI_BOLD, DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL, 16.0, locale, byref(fmt))
    if hr != 0 or not fmt:
        return None, None
    fn(fmt, 3, HRESULT, ctypes.c_uint)(fmt, 0)  # leading
    fn(fmt, 4, HRESULT, ctypes.c_uint)(fmt, 2)  # paragraph center
    fn(fmt, IDWriteTextFormat_SetReadingDirection, HRESULT, ctypes.c_uint)(
        fmt, DWRITE_READING_DIRECTION_RTL if rtl else DWRITE_READING_DIRECTION_LTR
    )
    layout = c_void_p()
    body = ctypes.c_wchar_p(text)
    hr = fn(dw, 16, HRESULT, ctypes.c_wchar_p, ctypes.c_uint, c_void_p, ctypes.c_float, ctypes.c_float, POINTER(c_void_p))(
        dw, body, len(text), fmt, float(width), float(height), byref(layout)
    )
    if hr != 0 or not layout:
        return fmt, None
    _set_character_spacing(layout, len(text))
    return fmt, layout


def _fill_rounded(dc: c_void_p, left: float, top: float, right: float, bottom: float, radius: float, brush: c_void_p) -> None:
    rounded = D2D1_ROUNDED_RECT(D2D_RECT_F(left, top, right, bottom), radius, radius)
    fn(dc, D2D1_FILL_ROUNDED_RECTANGLE, None, POINTER(D2D1_ROUNDED_RECT), c_void_p)(dc, byref(rounded), brush)


def _create_graphics(compositor: c_void_p) -> tuple[c_void_p | None, c_void_p | None, c_void_p | None]:
    d3d, _ctx = _d3d_device()
    rendering = d3d
    try:
        rendering = _d2d_device(d3d)
    except DesktopUnavailable:
        rendering = d3d
    gfx_interop = qi(compositor, IID_ICompositorInterop)
    graphics = c_void_p()
    if fn(gfx_interop, 3, HRESULT, c_void_p, POINTER(c_void_p))(gfx_interop, rendering, byref(graphics)) != 0:
        return None, None, None
    return d3d, gfx_interop, graphics


def _create_drawing_surface(graphics: c_void_p, width: float, height: float) -> tuple[c_void_p | None, c_void_p | None]:
    surface = c_void_p()
    if fn(graphics, 6, HRESULT, SizeF, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
        graphics, SizeF(float(width), float(height)), DirectXPixelFormat_B8G8R8A8UIntNormalized, DirectXAlphaMode_Premultiplied, byref(surface)
    ) != 0:
        return None, None
    return surface, qi(surface, IID_ICompositionDrawingSurfaceInterop)


def _sprite_from_surface(compositor: c_void_p, surface: c_void_p, width: float, height: float, offset: Vector3 | None = None) -> c_void_p | None:
    brush = c_void_p()
    if fn(compositor, ICompositor_CreateSurfaceBrushWithSurface, HRESULT, c_void_p, POINTER(c_void_p))(compositor, surface, byref(brush)) != 0:
        return None
    fn(brush, 11, HRESULT, ctypes.c_int)(brush, 0)
    sprite = c_void_p()
    if fn(compositor, ICompositor_CreateSpriteVisual, HRESULT, POINTER(c_void_p))(compositor, byref(sprite)) != 0:
        return None
    fn(sprite, 7, HRESULT, c_void_p)(sprite, brush)
    visual = qi(sprite, IID_IVisual)
    fn(visual, 36, HRESULT, Vector2)(visual, Vector2(float(width), float(height)))
    if offset is not None:
        fn(visual, 21, HRESULT, Vector3)(visual, offset)
    _keep.extend([brush, sprite, visual])
    return visual


def _draw_status_text(compositor: c_void_p, children: c_void_p | None, width: int, height: int) -> None:
    """Official display chrome: status pill + cancel text + DirectWrite + shimmer."""
    if not children:
        return
    try:
        from computer_use.overlay import (
            ACCENT_HEX,
            BANNER,
            ESC_HINT,
            compute_pill_layout,
            is_rtl_locale,
            parse_hex_color,
            pick_ink_color,
        )

        accent = parse_hex_color(ACCENT_HEX) or (1.0, 0.769, 0.0, 1.0)
        ink = pick_ink_color(accent)
        rtl = is_rtl_locale()
        d3d, gfx_interop, graphics = _create_graphics(compositor)
        if not graphics:
            return
        surface, interop = _create_drawing_surface(graphics, float(width), float(height))
        if not surface or not interop:
            return
        painted = False
        offset = POINT(0, 0)
        dc_obj = c_void_p()
        hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_ID2D1DeviceContext)), POINTER(c_void_p), POINTER(POINT))(
            interop, None, byref(IID_ID2D1DeviceContext), byref(dc_obj), byref(offset)
        )
        if is_device_lost(hr):
            _mark_device_lost(hr)
            return
        layout_metrics = compute_pill_layout(width, height, BANNER, ESC_HINT)
        if hr == 0 and dc_obj:
            try:
                dw = _dwrite_factory()
                status_fmt, status_layout = _make_text_layout(dw, BANNER, layout_metrics["status_width"] + 8.0, layout_metrics["height"], rtl=rtl)
                cancel_fmt, cancel_layout = _make_text_layout(dw, ESC_HINT, layout_metrics["cancel_width"] + 8.0, layout_metrics["height"], rtl=rtl)
                measured_status = _measure_layout(status_layout) if status_layout else None
                measured_cancel = _measure_layout(cancel_layout) if cancel_layout else None
                layout_metrics = compute_pill_layout(
                    width,
                    height,
                    BANNER,
                    ESC_HINT,
                    status_width=measured_status,
                    cancel_width=measured_cancel,
                )
                dc = qi(dc_obj, IID_ID2D1DeviceContext)
                matrix = D2D1_MATRIX_3X2_F(1.0, 0.0, 0.0, 1.0, float(offset.x), float(offset.y))
                fn(dc, 30, None, POINTER(D2D1_MATRIX_3X2_F))(dc, byref(matrix))
                transparent = D2D_COLOR_F(0.0, 0.0, 0.0, 0.0)
                fn(dc, 47, None, POINTER(D2D_COLOR_F))(dc, byref(transparent))
                shadow = c_void_p()
                fill = c_void_p()
                stroke = c_void_p()
                text_brush = c_void_p()
                sep = c_void_p()
                shadow_color = D2D_COLOR_F(0.0, 0.0, 0.0, 0.18)
                fill_color = D2D_COLOR_F(accent[0], accent[1], accent[2], 1.0)
                stroke_color = D2D_COLOR_F(1.0, 1.0, 1.0, 0.35)
                ink_color = D2D_COLOR_F(ink[0], ink[1], ink[2], 1.0)
                sep_color = D2D_COLOR_F(ink[0], ink[1], ink[2], 0.35)
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(shadow_color), None, byref(shadow))
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(fill_color), None, byref(fill))
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(stroke_color), None, byref(stroke))
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(ink_color), None, byref(text_brush))
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(sep_color), None, byref(sep))
                px, py, pw, ph, rad = (
                    layout_metrics["x"],
                    layout_metrics["y"],
                    layout_metrics["width"],
                    layout_metrics["height"],
                    layout_metrics["radius"],
                )
                if shadow:
                    _fill_rounded(dc, px, py + 2.0, px + pw, py + ph + 2.0, rad, shadow)
                if fill:
                    _fill_rounded(dc, px, py, px + pw, py + ph, rad, fill)
                if sep:
                    x0 = D2D_POINT_2F(layout_metrics["separator_x"], py + 8.0)
                    x1 = D2D_POINT_2F(layout_metrics["separator_x"], py + ph - 8.0)
                    fn(dc, D2D1_DRAW_LINE, None, D2D_POINT_2F, D2D_POINT_2F, c_void_p, ctypes.c_float, c_void_p)(
                        dc, x0, x1, sep, ctypes.c_float(1.0), None
                    )
                if status_layout and text_brush:
                    origin = D2D_POINT_2F(layout_metrics["status_x"], py)
                    fn(dc, 28, None, D2D_POINT_2F, c_void_p, c_void_p, ctypes.c_uint)(dc, origin, status_layout, text_brush, 0)
                if cancel_layout and text_brush:
                    origin = D2D_POINT_2F(layout_metrics["cancel_x"], py)
                    fn(dc, 28, None, D2D_POINT_2F, c_void_p, c_void_p, ctypes.c_uint)(dc, origin, cancel_layout, text_brush, 0)
                for obj in (shadow, fill, stroke, text_brush, sep, dc):
                    release(obj)
                painted = True
                _keep.extend([dw, status_fmt, status_layout, cancel_fmt, cancel_layout])
            except OSError:
                painted = False
            finally:
                release(dc_obj)
                fn(interop, 4, HRESULT)(interop)
        if not painted:
            dxgi = c_void_p()
            offset = POINT(0, 0)
            hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_IDXGISurface)), POINTER(c_void_p), POINTER(POINT))(
                interop, None, byref(IID_IDXGISurface), byref(dxgi), byref(offset)
            )
            if is_device_lost(hr):
                _mark_device_lost(hr)
            if hr == 0 and dxgi:
                try:
                    surface1 = qi(dxgi, IID_IDXGISurface1)
                    hdc = wintypes.HDC()
                    if fn(surface1, 11, HRESULT, wintypes.BOOL, POINTER(wintypes.HDC))(surface1, True, byref(hdc)) == 0 and hdc:
                        from computer_use.overlay import BANNER as _B, ESC_HINT as _E

                        _gdi_status_text(int(hdc.value), width, height, f"{_B}    {_E}")
                        fn(surface1, 12, HRESULT, c_void_p)(surface1, None)
                        painted = True
                    if surface1 is not dxgi:
                        release(surface1)
                finally:
                    release(dxgi)
                    fn(interop, 4, HRESULT)(interop)
        if not painted:
            return
        text_visual = _sprite_from_surface(compositor, surface, float(width), float(height))
        if text_visual:
            _start_border_pulse(compositor, children, layout_metrics)
            fn(children, 8, HRESULT, c_void_p)(children, text_visual)
            _pulse_opacity(compositor, text_visual)
            _start_shimmer(compositor, children, layout_metrics)
        _keep.extend([d3d, gfx_interop, graphics, surface, interop])
    except Exception:
        return


def _start_shimmer(compositor: c_void_p, children: c_void_p, layout: dict[str, float]) -> None:
    """Official shimmer mask offset: Vector2(StartX + TravelX * shimmer.Progress, 0)."""
    try:
        from computer_use.winrt_common import delete_hstring, hstring

        strip_w = max(48.0, layout["width"] * 0.22)
        strip_h = layout["height"]
        d3d, gfx, graphics = _create_graphics(compositor)
        if not graphics:
            return
        surface, interop = _create_drawing_surface(graphics, strip_w, strip_h)
        if not surface or not interop:
            return
        offset = POINT(0, 0)
        dc_obj = c_void_p()
        hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_ID2D1DeviceContext)), POINTER(c_void_p), POINTER(POINT))(
            interop, None, byref(IID_ID2D1DeviceContext), byref(dc_obj), byref(offset)
        )
        if hr == 0 and dc_obj:
            try:
                dc = qi(dc_obj, IID_ID2D1DeviceContext)
                matrix = D2D1_MATRIX_3X2_F(1.0, 0.0, 0.0, 1.0, float(offset.x), float(offset.y))
                fn(dc, 30, None, POINTER(D2D1_MATRIX_3X2_F))(dc, byref(matrix))
                fn(dc, 47, None, POINTER(D2D_COLOR_F))(dc, byref(D2D_COLOR_F(0.0, 0.0, 0.0, 0.0)))
                highlight = D2D_COLOR_F(1.0, 1.0, 1.0, 0.28)
                brush = c_void_p()
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(highlight), None, byref(brush))
                _fill_rounded(dc, 0.0, 2.0, strip_w, strip_h - 2.0, (strip_h - 4.0) / 2.0, brush)
                release(brush)
                release(dc)
            finally:
                release(dc_obj)
                fn(interop, 4, HRESULT)(interop)
        visual = _sprite_from_surface(compositor, surface, strip_w, strip_h, Vector3(layout["x"], layout["y"], 0.0))
        if not visual:
            return
        fn(children, 8, HRESULT, c_void_p)(children, visual)
        propset = c_void_p()
        if fn(compositor, ICompositor_CreatePropertySet, HRESULT, POINTER(c_void_p))(compositor, byref(propset)) != 0:
            return
        _insert_scalar(propset, "Progress", 0.0)
        _insert_scalar(propset, "StartX", float(layout["x"] - strip_w))
        _insert_scalar(propset, "TravelX", float(layout["width"] + strip_w))
        vis_obj = qi(visual, IID_ICompositionObject)
        _bind_expression(compositor, vis_obj, "Offset", SHIMMER_OFFSET_EXPRESSION, "shimmer", propset)
        progress = c_void_p()
        fn(compositor, ICompositor_CreateScalarKeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(progress))
        fn(progress, 13, HRESULT, ctypes.c_int64)(progress, ctypes.c_int64(1_800_0000))
        fn(progress, 15, HRESULT, ctypes.c_int)(progress, 1)
        fn(progress, 21, HRESULT, ctypes.c_float, ctypes.c_float)(progress, ctypes.c_float(0.0), ctypes.c_float(0.0))
        fn(progress, 21, HRESULT, ctypes.c_float, ctypes.c_float)(progress, ctypes.c_float(1.0), ctypes.c_float(1.0))
        prop_obj = qi(propset, IID_ICompositionObject)
        key = hstring("Progress")
        fn(prop_obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(prop_obj, key, progress)
        delete_hstring(key)
        _keep.extend([d3d, gfx, graphics, surface, interop, propset, vis_obj, progress, prop_obj])
    except Exception:
        return


def _start_border_pulse(compositor: c_void_p, children: c_void_p, layout: dict[str, float]) -> None:
    try:
        grow = 5.0
        bw = layout["width"] + grow * 2.0
        bh = layout["height"] + grow * 2.0
        d3d, gfx, graphics = _create_graphics(compositor)
        if not graphics:
            return
        surface, interop = _create_drawing_surface(graphics, bw, bh)
        if not surface or not interop:
            return
        offset = POINT(0, 0)
        dc_obj = c_void_p()
        hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_ID2D1DeviceContext)), POINTER(c_void_p), POINTER(POINT))(
            interop, None, byref(IID_ID2D1DeviceContext), byref(dc_obj), byref(offset)
        )
        if hr == 0 and dc_obj:
            try:
                dc = qi(dc_obj, IID_ID2D1DeviceContext)
                matrix = D2D1_MATRIX_3X2_F(1.0, 0.0, 0.0, 1.0, float(offset.x), float(offset.y))
                fn(dc, 30, None, POINTER(D2D1_MATRIX_3X2_F))(dc, byref(matrix))
                fn(dc, 47, None, POINTER(D2D_COLOR_F))(dc, byref(D2D_COLOR_F(0.0, 0.0, 0.0, 0.0)))
                ring = D2D_COLOR_F(1.0, 1.0, 1.0, 0.45)
                brush = c_void_p()
                fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(ring), None, byref(brush))
                _fill_rounded(dc, 0.0, 0.0, bw, bh, bh / 2.0, brush)
                inner = D2D_COLOR_F(0.0, 0.0, 0.0, 0.0)
                # punch inner hole by skipping — ring is a larger fill behind the pill
                release(brush)
                release(dc)
            finally:
                release(dc_obj)
                fn(interop, 4, HRESULT)(interop)
        visual = _sprite_from_surface(
            compositor, surface, bw, bh, Vector3(layout["x"] - grow, layout["y"] - grow, 0.0)
        )
        if not visual:
            return
        fn(children, 8, HRESULT, c_void_p)(children, visual)
        fn(visual, 23, HRESULT, ctypes.c_float)(visual, ctypes.c_float(0.35))
        _pulse_opacity(compositor, visual)
        _keep.extend([d3d, gfx, graphics, surface, interop])
    except Exception:
        return


def _pulse_opacity(compositor: c_void_p, visual: c_void_p) -> None:
    """Official border/shimmer pulse: repeating scalar opacity animation."""
    try:
        anim = c_void_p()
        if fn(compositor, ICompositor_CreateScalarKeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(anim)) != 0:
            return
        span = ctypes.c_int64(1_200_0000)  # 1.2s in 100ns ticks
        fn(anim, 13, HRESULT, ctypes.c_int64)(anim, span)  # put_Duration
        fn(anim, 15, HRESULT, ctypes.c_int)(anim, 1)  # IterationBehavior Forever
        fn(anim, 21, HRESULT, ctypes.c_float, ctypes.c_float)(anim, ctypes.c_float(0.0), ctypes.c_float(1.0))
        fn(anim, 21, HRESULT, ctypes.c_float, ctypes.c_float)(anim, ctypes.c_float(0.5), ctypes.c_float(0.72))
        fn(anim, 21, HRESULT, ctypes.c_float, ctypes.c_float)(anim, ctypes.c_float(1.0), ctypes.c_float(1.0))
        obj = qi(visual, IID_ICompositionObject)
        key = None
        from computer_use.winrt_common import hstring, delete_hstring

        key = hstring("Opacity")
        fn(obj, 9, HRESULT, c_void_p, c_void_p)(obj, key, anim)
        delete_hstring(key)
        _keep.extend([anim, obj])
    except Exception:
        return


def attach_yellow_bar(hwnd: int, width: int, height: int = 44) -> bool:
    """Host a Composition DesktopWindowTarget on the overlay HWND (status pill)."""
    global _attached, _display_visual, _display_compositor
    if not hwnd:
        return False
    try:
        ro_init_sta()
        ensure_dispatcher_queue()
        compositor = _compositor()
        desktop = qi(compositor, IID_ICompositorDesktopInterop)
        target = c_void_p()
        hr = fn(desktop, 3, HRESULT, wintypes.HWND, wintypes.BOOL, POINTER(c_void_p))(desktop, hwnd, True, byref(target))
        if hr != 0 or not target:
            raise DesktopUnavailable(f"CreateDesktopWindowTarget 0x{hr & 0xFFFFFFFF:08X}")
        root = c_void_p()
        hr = fn(compositor, ICompositor_CreateContainerVisual, HRESULT, POINTER(c_void_p))(compositor, byref(root))
        if hr != 0:
            raise DesktopUnavailable("CreateContainerVisual failed")
        root_visual = qi(root, IID_IVisual)
        fn(root_visual, 36, HRESULT, Vector2)(root_visual, Vector2(float(width), float(height)))
        fn(root_visual, 21, HRESULT, Vector3)(root_visual, Vector3(0.0, 0.0, 0.0))
        fn(root_visual, 23, HRESULT, ctypes.c_float)(root_visual, ctypes.c_float(0.0))
        children = c_void_p()
        fn(root, 6, HRESULT, POINTER(c_void_p))(root, byref(children))
        _draw_status_text(compositor, children, width, height)
        composition_target = qi(target, IID_ICompositionTarget)
        fn(composition_target, 7, HRESULT, c_void_p)(composition_target, root)
        _keep.extend([compositor, desktop, target, root, root_visual, composition_target])
        if children:
            _keep.append(children)
        _display_visual = root_visual
        _display_compositor = compositor
        _attached = True
        return True
    except Exception:
        return False


def fade_display_overlay(target_opacity: float, *, duration_ms: int = 180) -> bool:
    """Official overlay enter/exit opacity animation."""
    visual = _display_visual
    compositor = _display_compositor or _compositor_obj
    if not visual or not compositor:
        try:
            if visual:
                fn(visual, 23, HRESULT, ctypes.c_float)(visual, ctypes.c_float(target_opacity))
                return True
        except Exception:
            return False
        return False
    try:
        anim = c_void_p()
        if fn(compositor, ICompositor_CreateScalarKeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(anim)) != 0:
            fn(visual, 23, HRESULT, ctypes.c_float)(visual, ctypes.c_float(target_opacity))
            return True
        ticks = ctypes.c_int64(max(int(duration_ms), 1) * 10_000)
        fn(anim, 13, HRESULT, ctypes.c_int64)(anim, ticks)
        start = 0.0 if target_opacity >= 0.5 else 1.0
        fn(anim, 21, HRESULT, ctypes.c_float, ctypes.c_float)(anim, ctypes.c_float(0.0), ctypes.c_float(start))
        fn(anim, 21, HRESULT, ctypes.c_float, ctypes.c_float)(anim, ctypes.c_float(1.0), ctypes.c_float(target_opacity))
        obj = qi(visual, IID_ICompositionObject)
        from computer_use.winrt_common import delete_hstring, hstring

        key = hstring("Opacity")
        fn(obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(obj, key, anim)
        delete_hstring(key)
        _keep.extend([anim, obj])
        return True
    except Exception:
        try:
            fn(visual, 23, HRESULT, ctypes.c_float)(visual, ctypes.c_float(target_opacity))
        except Exception:
            return False
        return False


def composition_attached() -> bool:
    return _attached


def _d3d_device() -> tuple[c_void_p, c_void_p]:
    d3d11 = ctypes.WinDLL("d3d11")
    device = c_void_p()
    context = c_void_p()
    d3d11.D3D11CreateDevice.restype = HRESULT
    drivers = (D3D_DRIVER_TYPE_WARP,) if force_cursor_warp() else (D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP)
    for driver in drivers:
        hr = d3d11.D3D11CreateDevice(
            None, driver, None, D3D11_CREATE_DEVICE_BGRA_SUPPORT, None, 0, D3D11_SDK_VERSION, byref(device), None, byref(context)
        )
        if hr == 0 and device:
            return device, context
    raise DesktopUnavailable("D3D11CreateDevice failed")


def _d2d_factory() -> c_void_p:
    global _d2d_factory
    if _d2d_factory:
        return _d2d_factory
    d2d1 = ctypes.WinDLL("d2d1")
    factory = c_void_p()
    d2d1.D2D1CreateFactory.restype = HRESULT
    d2d1.D2D1CreateFactory.argtypes = [ctypes.c_uint, c_void_p, c_void_p, POINTER(c_void_p)]
    hr = d2d1.D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, byref(IID_ID2D1Factory1), None, byref(factory))
    if hr != 0 or not factory:
        raise DesktopUnavailable(f"D2D1CreateFactory 0x{hr & 0xFFFFFFFF:08X}")
    _d2d_factory = factory
    _keep.append(factory)
    return factory


def _d2d_device(d3d: c_void_p) -> c_void_p:
    dxgi = qi(d3d, IID_IDXGIDevice)
    factory = _d2d_factory()
    device = c_void_p()
    hr = fn(factory, 19, HRESULT, c_void_p, POINTER(c_void_p))(factory, dxgi, byref(device))
    if hr != 0 or not device:
        raise DesktopUnavailable(f"ID2D1Factory1.CreateDevice 0x{hr & 0xFFFFFFFF:08X}")
    _keep.extend([dxgi, device])
    return device


def _create_path(factory: c_void_p, points: list[tuple[float, float]]) -> c_void_p:
    geometry = c_void_p()
    hr = fn(factory, 10, HRESULT, POINTER(c_void_p))(factory, byref(geometry))  # CreatePathGeometry
    if hr != 0 or not geometry:
        raise DesktopUnavailable("CreatePathGeometry failed")
    sink = c_void_p()
    hr = fn(geometry, 17, HRESULT, POINTER(c_void_p))(geometry, byref(sink))  # Open
    if hr != 0 or not sink:
        release(geometry)
        raise DesktopUnavailable("open cursor path geometry failed")
    start = D2D_POINT_2F(points[0][0], points[0][1])
    fn(sink, 5, None, D2D_POINT_2F, ctypes.c_uint)(sink, start, D2D1_FIGURE_BEGIN_FILLED)
    for x, y in points[1:]:
        fn(sink, 10, None, D2D_POINT_2F)(sink, D2D_POINT_2F(x, y))  # AddLine
    fn(sink, 8, None, ctypes.c_uint)(sink, D2D1_FIGURE_END_CLOSED)
    fn(sink, 9, HRESULT)(sink)
    release(sink)
    return geometry


def _arrow_points(press: bool) -> list[tuple[float, float]]:
    scale = 0.86 if press else 1.0
    origin = (2.0, 2.0)
    raw = [(0, 0), (1, 21), (6, 16), (10, 26), (13, 25), (8, 14), (16, 14)]
    return [(origin[0] + x * scale, origin[1] + y * scale) for x, y in raw]


def _draw_cursor_d2d(dc: c_void_p, offset: POINT, press: bool) -> None:
    matrix = D2D1_MATRIX_3X2_F(1.0, 0.0, 0.0, 1.0, float(offset.x), float(offset.y))
    fn(dc, 30, None, POINTER(D2D1_MATRIX_3X2_F))(dc, byref(matrix))  # SetTransform
    transparent = D2D_COLOR_F(0.0, 0.0, 0.0, 0.0)
    fn(dc, 47, None, POINTER(D2D_COLOR_F))(dc, byref(transparent))  # Clear
    factory = _d2d_factory()
    fill_color = D2D_COLOR_F(0.12, 0.12, 0.12, 1.0) if press else D2D_COLOR_F(1.0, 1.0, 1.0, 1.0)
    stroke_color = D2D_COLOR_F(0.0, 0.0, 0.0, 1.0)
    fog_color = D2D_COLOR_F(0.0, 0.0, 0.0, 0.18 if press else 0.10)
    fill = c_void_p()
    stroke = c_void_p()
    fog = c_void_p()
    fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(fill_color), None, byref(fill))
    fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(stroke_color), None, byref(stroke))
    fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(fog_color), None, byref(fog))
    # Multi-radius fog stands in for official Gaussian blur bitmap when CreateEffect is unavailable.
    radii = (16.0, 13.0, 11.0) if not press else (18.0, 15.0, 14.0)
    alphas = (0.06, 0.08, 0.12) if not press else (0.08, 0.12, 0.18)
    for radius, alpha in zip(radii, alphas):
        layer = c_void_p()
        color = D2D_COLOR_F(0.0, 0.0, 0.0, alpha)
        fn(dc, 8, HRESULT, POINTER(D2D_COLOR_F), c_void_p, POINTER(c_void_p))(dc, byref(color), None, byref(layer))
        ellipse = D2D1_ELLIPSE(10.0, 12.0, radius, radius)
        if layer:
            fn(dc, 21, None, POINTER(D2D1_ELLIPSE), c_void_p)(dc, byref(ellipse), layer)
            release(layer)
    if fog:
        ellipse = D2D1_ELLIPSE(10.0, 12.0, 14.0 if press else 11.0, 14.0 if press else 11.0)
        fn(dc, 21, None, POINTER(D2D1_ELLIPSE), c_void_p)(dc, byref(ellipse), fog)  # FillEllipse
    geometry = _create_path(factory, _arrow_points(press))
    if fill:
        fn(dc, 23, None, c_void_p, c_void_p, c_void_p)(dc, geometry, fill, None)  # FillGeometry
    if stroke:
        fn(dc, 22, None, c_void_p, c_void_p, ctypes.c_float, c_void_p)(dc, geometry, stroke, ctypes.c_float(1.25), None)
    release(geometry)
    release(fill)
    release(stroke)
    release(fog)


def _draw_cursor_gdi(hdc: int, press: bool) -> None:
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class POINTL(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    rect = wintypes.RECT(0, 0, CURSOR_GLYPH, CURSOR_GLYPH)
    hollow = gdi32.GetStockObject(5)  # NULL_BRUSH
    user32.FillRect(hdc, byref(rect), hollow)
    fill_color = 0x00202020 if press else 0x00FFFFFF
    brush = gdi32.CreateSolidBrush(fill_color)
    pen = gdi32.CreatePen(0, 1, 0x00000000)
    old_brush = gdi32.SelectObject(hdc, brush)
    old_pen = gdi32.SelectObject(hdc, pen)
    pts = _arrow_points(press)
    arr = (POINTL * len(pts))(*[POINTL(int(x), int(y)) for x, y in pts])
    gdi32.Polygon(hdc, arr, len(pts))
    gdi32.SelectObject(hdc, old_brush)
    gdi32.SelectObject(hdc, old_pen)
    gdi32.DeleteObject(brush)
    gdi32.DeleteObject(pen)


def _begin_draw() -> tuple[c_void_p | None, POINT]:
    interop = _surface_interop
    if not interop:
        return None, POINT(0, 0)
    offset = POINT(0, 0)
    obj = c_void_p()
    hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_ID2D1DeviceContext)), POINTER(c_void_p), POINTER(POINT))(
        interop, None, byref(IID_ID2D1DeviceContext), byref(obj), byref(offset)
    )
    if is_device_lost(hr):
        _mark_device_lost(hr)
        return None, offset
    if hr == 0 and obj:
        return obj, offset
    obj = c_void_p()
    hr = fn(interop, 3, HRESULT, c_void_p, POINTER(type(IID_IDXGISurface)), POINTER(c_void_p), POINTER(POINT))(
        interop, None, byref(IID_IDXGISurface), byref(obj), byref(offset)
    )
    if is_device_lost(hr):
        _mark_device_lost(hr)
        return None, offset
    if hr == 0 and obj:
        return obj, offset
    return None, offset


def _end_draw() -> None:
    if _surface_interop:
        fn(_surface_interop, 4, HRESULT)(_surface_interop)


def _draw_into(interop: c_void_p | None, press: bool) -> bool:
    if not interop:
        return False
    saved = _surface_interop
    try:
        globals()["_surface_interop"] = interop
        return _draw_cursor_body(press)
    finally:
        globals()["_surface_interop"] = saved


def _draw_cursor_body(press: bool) -> bool:
    obj, offset = _begin_draw()
    if not obj:
        return False
    try:
        try:
            dc = qi(obj, IID_ID2D1DeviceContext)
            _draw_cursor_d2d(dc, offset, press)
            release(dc)
        except DesktopUnavailable:
            try:
                surface1 = qi(obj, IID_IDXGISurface1)
            except DesktopUnavailable:
                surface1 = obj
            hdc = wintypes.HDC()
            hr = fn(surface1, 11, HRESULT, wintypes.BOOL, POINTER(wintypes.HDC))(surface1, True, byref(hdc))
            if hr == 0 and hdc:
                _draw_cursor_gdi(int(hdc.value), press)
                fn(surface1, 12, HRESULT, c_void_p)(surface1, None)
            if surface1 is not obj:
                release(surface1)
        return True
    except Exception:
        return False
    finally:
        release(obj)
        _end_draw()


def draw_cursor_surface(press: bool = False) -> bool:
    """Official: begin cursor surface draw / end cursor surface draw."""
    global _press_drawn
    interop = _press_interop if press and _press_interop else _surface_interop
    ok = _draw_into(interop, press)
    if ok:
        _press_drawn = press
        swap_cursor_press(press)
    return ok


def swap_cursor_press(press: bool) -> None:
    """Official: replace cursor drawing surface for the pressed glyph."""
    global _press_drawn
    brush = _cursor_brush
    surface = _press_surface if press else _idle_surface
    if not brush or not surface:
        _draw_into(_press_interop if press else _surface_interop, press)
        return
    try:
        fn(brush, 13, HRESULT, c_void_p)(brush, surface)  # put_Surface
        _press_drawn = press
    except Exception:
        _draw_into(_press_interop if press else _surface_interop, press)
        _press_drawn = press


def _insert_scalar(propset: c_void_p, name: str, value: float) -> None:
    from computer_use.winrt_common import delete_hstring, hstring

    key = hstring(name)
    fn(propset, 10, HRESULT, c_void_p, ctypes.c_float)(propset, key, ctypes.c_float(value))
    delete_hstring(key)


def _insert_vector3(propset: c_void_p, name: str, vec: Vector3) -> None:
    from computer_use.winrt_common import delete_hstring, hstring

    key = hstring(name)
    fn(propset, 12, HRESULT, c_void_p, Vector3)(propset, key, vec)
    delete_hstring(key)


def animate_cursor_path(points: list, pose: dict | None = None) -> bool:
    """Official sampled motion: P0–P6 property set + cubic half expressions."""
    global _motion_propset, _last_cursor_xy, _last_cursor_pose
    if not points or not _motion_visual:
        return False
    pose = pose or {}
    compositor = _compositor_obj
    last = points[-1]
    _last_cursor_xy = (float(last[0]), float(last[1]))
    _last_cursor_pose = dict(pose)
    if not compositor:
        apply_cursor_pose(float(last[0]), float(last[1]), pose)
        return True
    from computer_use.overlay_cursor import resample_p0_p6, scoot_pose

    ox, oy = _cursor_origin
    samples = resample_p0_p6([(float(p[0]), float(p[1])) for p in points])
    segment_count = 1.0 if len(points) < 3 else 6.0
    stop_cursor_motion()
    try:
        from computer_use.winrt_common import delete_hstring, hstring

        propset = c_void_p()
        if fn(compositor, ICompositor_CreatePropertySet, HRESULT, POINTER(c_void_p))(compositor, byref(propset)) != 0:
            raise DesktopUnavailable("CreatePropertySet")
        for i, point in enumerate(samples):
            _insert_vector3(propset, f"P{i}", Vector3(float(point[0]) - ox, float(point[1]) - oy, 0.0))
        _insert_vector3(propset, "SingleSegmentPoint", Vector3(float(samples[0][0]) - ox, float(samples[0][1]) - oy, 0.0))
        _insert_vector3(propset, "FirstHalfPoint", Vector3(float(samples[0][0]) - ox, float(samples[0][1]) - oy, 0.0))
        _insert_vector3(propset, "SecondHalfPoint", Vector3(float(samples[-1][0]) - ox, float(samples[-1][1]) - oy, 0.0))
        _insert_scalar(propset, "Progress", 0.0)
        _insert_scalar(propset, "SegmentCount", segment_count)
        prop_obj = qi(propset, IID_ICompositionObject)
        _bind_expression(compositor, prop_obj, "SingleSegmentPoint", SINGLE_SEGMENT_POINT_EXPRESSION, "motion", propset)
        _bind_expression(compositor, prop_obj, "FirstHalfPoint", FIRST_HALF_POINT_EXPRESSION, "motion", propset)
        _bind_expression(compositor, prop_obj, "SecondHalfPoint", SECOND_HALF_POINT_EXPRESSION, "motion", propset)
        motion_obj = qi(_motion_visual, IID_ICompositionObject)
        _bind_expression(compositor, motion_obj, "Offset", PATH_OFFSET_EXPRESSION, "motion", propset)
        ticks = ctypes.c_int64(max(12, len(points)) * 120_000)
        progress = c_void_p()
        fn(compositor, ICompositor_CreateScalarKeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(progress))
        fn(progress, 13, HRESULT, ctypes.c_int64)(progress, ticks)
        fn(progress, 21, HRESULT, ctypes.c_float, ctypes.c_float)(progress, ctypes.c_float(0.0), ctypes.c_float(0.0))
        fn(progress, 21, HRESULT, ctypes.c_float, ctypes.c_float)(progress, ctypes.c_float(1.0), ctypes.c_float(1.0))
        prog_name = hstring("Progress")
        fn(prop_obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(prop_obj, prog_name, progress)
        delete_hstring(prog_name)
        first = points[0]
        start_pose = scoot_pose(float(samples[1][0]) - float(samples[0][0]), float(samples[1][1]) - float(samples[0][1]))
        start_rot = float(start_pose.get("baseRotationDegrees") or 0) + float(start_pose.get("scootTiltDegrees") or 0)
        end_rot = float(pose.get("baseRotationDegrees") or 0) + float(pose.get("scootTiltDegrees") or 0)
        rot = c_void_p()
        if fn(compositor, ICompositor_CreateScalarKeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(rot)) == 0:
            fn(rot, 13, HRESULT, ctypes.c_int64)(rot, ticks)
            fn(rot, 21, HRESULT, ctypes.c_float, ctypes.c_float)(rot, ctypes.c_float(0.0), ctypes.c_float(start_rot))
            fn(rot, 21, HRESULT, ctypes.c_float, ctypes.c_float)(rot, ctypes.c_float(1.0), ctypes.c_float(end_rot))
            rot_name = hstring("RotationAngleInDegrees")
            fn(motion_obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(motion_obj, rot_name, rot)
            delete_hstring(rot_name)
            _keep.append(rot)
        if _sprite_visual:
            scale_anim = c_void_p()
            if fn(compositor, ICompositor_CreateVector3KeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(scale_anim)) == 0:
                fn(scale_anim, 13, HRESULT, ctypes.c_int64)(scale_anim, ticks)
                start_scale = Vector3(float(start_pose.get("scaleX") or 1.0), float(start_pose.get("scaleY") or 1.0), 1.0)
                end_scale = Vector3(float(pose.get("scaleX") or 1.0), float(pose.get("scaleY") or 1.0), 1.0)
                fn(scale_anim, 21, HRESULT, ctypes.c_float, Vector3)(scale_anim, ctypes.c_float(0.0), start_scale)
                fn(scale_anim, 21, HRESULT, ctypes.c_float, Vector3)(scale_anim, ctypes.c_float(1.0), end_scale)
                sprite_obj = qi(_sprite_visual, IID_ICompositionObject)
                scale_name = hstring("Scale")
                fn(sprite_obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(sprite_obj, scale_name, scale_anim)
                delete_hstring(scale_name)
                _keep.extend([scale_anim, sprite_obj])
        _motion_propset = propset
        _keep.extend([propset, motion_obj, progress, prop_obj])
        _ = first
        return True
    except Exception:
        try:
            anim = c_void_p()
            if fn(compositor, ICompositor_CreateVector3KeyFrameAnimation, HRESULT, POINTER(c_void_p))(compositor, byref(anim)) != 0:
                apply_cursor_pose(float(last[0]), float(last[1]), pose)
                return True
            ticks = ctypes.c_int64(max(12, len(points)) * 120_000)
            fn(anim, 13, HRESULT, ctypes.c_int64)(anim, ticks)
            n = max(len(points) - 1, 1)
            for i, point in enumerate(points):
                t = i / float(n)
                vec = Vector3(float(point[0]) - ox, float(point[1]) - oy, 0.0)
                fn(anim, 21, HRESULT, ctypes.c_float, Vector3)(anim, ctypes.c_float(t), vec)
            obj = qi(_motion_visual, IID_ICompositionObject)
            from computer_use.winrt_common import delete_hstring, hstring

            key = hstring("Offset")
            fn(obj, ICompositionObject_StartAnimation, HRESULT, c_void_p, c_void_p)(obj, key, anim)
            delete_hstring(key)
            _keep.extend([anim, obj])
            return True
        except Exception:
            apply_cursor_pose(float(last[0]), float(last[1]), pose)
            return False


def stop_cursor_motion() -> None:
    """Official: stop active cursor motion animation (also while destroying)."""
    motion = _motion_visual
    sprite = _sprite_visual
    propset = _motion_propset
    try:
        if motion:
            obj = qi(motion, IID_ICompositionObject)
            for name in ("Offset", "RotationAngleInDegrees", "Scale", "Opacity"):
                _stop_named_animation(obj, name)
        if sprite:
            obj = qi(sprite, IID_ICompositionObject)
            for name in ("Scale", "RotationAngleInDegrees", "Offset"):
                _stop_named_animation(obj, name)
        if propset:
            obj = qi(propset, IID_ICompositionObject)
            for name in ("Progress", "FirstHalfPoint", "SecondHalfPoint", "SingleSegmentPoint"):
                _stop_named_animation(obj, name)
        if motion and _last_cursor_xy:
            apply_cursor_pose(_last_cursor_xy[0], _last_cursor_xy[1], _last_cursor_pose)
    except Exception:
        return


def recreate_after_device_loss() -> None:
    """Official: cursor overlay rendering failed after likely device loss."""
    global _attached, _surface_interop, _press_interop, _motion_visual, _cursor_visual
    global _idle_surface, _press_surface, _cursor_brush, _graphics_device, _compositor_obj, _press_drawn
    global _display_visual, _display_compositor, _motion_propset, _sprite_visual, _device_lost, _d2d_factory
    try:
        stop_cursor_motion()
    except Exception:
        pass
    _attached = False
    _surface_interop = None
    _press_interop = None
    _motion_visual = None
    _cursor_visual = None
    _sprite_visual = None
    _idle_surface = None
    _press_surface = None
    _cursor_brush = None
    _graphics_device = None
    _compositor_obj = None
    _display_visual = None
    _display_compositor = None
    _motion_propset = None
    _d2d_factory = None
    _press_drawn = False
    _device_lost = False


def attach_cursor_stage(hwnd: int, width: int, height: int, origin: tuple[float, float] = (0.0, 0.0), glyph: int = CURSOR_GLYPH) -> bool:
    """Full-desktop cursor overlay: drawing surface + motion visual + sprite."""
    global _cursor_visual, _motion_visual, _sprite_visual, _surface_interop, _cursor_origin, _cursor_size, _attached
    global _idle_surface, _press_surface, _cursor_brush, _press_interop, _graphics_device, _compositor_obj, _press_drawn
    global _device_lost
    if not hwnd:
        return False
    try:
        ro_init_sta()
        ensure_dispatcher_queue()
        compositor = _compositor()
        desktop = qi(compositor, IID_ICompositorDesktopInterop)
        target = c_void_p()
        hr = fn(desktop, 3, HRESULT, wintypes.HWND, wintypes.BOOL, POINTER(c_void_p))(desktop, hwnd, True, byref(target))
        if hr != 0 or not target:
            return False
        d3d, ctx = _d3d_device()
        rendering = d3d
        try:
            rendering = _d2d_device(d3d)
        except DesktopUnavailable:
            rendering = d3d
        interop = qi(compositor, IID_ICompositorInterop)
        graphics = c_void_p()
        hr = fn(interop, 3, HRESULT, c_void_p, POINTER(c_void_p))(interop, rendering, byref(graphics))
        if hr != 0 or not graphics:
            return False
        surface = c_void_p()
        hr = fn(graphics, 6, HRESULT, SizeF, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
            graphics, SizeF(float(glyph), float(glyph)), DirectXPixelFormat_B8G8R8A8UIntNormalized, DirectXAlphaMode_Premultiplied, byref(surface)
        )
        if hr != 0 or not surface:
            return False
        press_surface = c_void_p()
        fn(graphics, 6, HRESULT, SizeF, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
            graphics, SizeF(float(glyph), float(glyph)), DirectXPixelFormat_B8G8R8A8UIntNormalized, DirectXAlphaMode_Premultiplied, byref(press_surface)
        )
        surface_interop = qi(surface, IID_ICompositionDrawingSurfaceInterop)
        press_interop = qi(press_surface, IID_ICompositionDrawingSurfaceInterop) if press_surface else None
        brush = c_void_p()
        hr = fn(compositor, ICompositor_CreateSurfaceBrushWithSurface, HRESULT, c_void_p, POINTER(c_void_p))(compositor, surface, byref(brush))
        if hr != 0 or not brush:
            return False
        fn(brush, 11, HRESULT, ctypes.c_int)(brush, 0)  # put_Stretch = None
        root = c_void_p()
        if fn(compositor, ICompositor_CreateContainerVisual, HRESULT, POINTER(c_void_p))(compositor, byref(root)) != 0:
            return False
        motion = c_void_p()
        if fn(compositor, ICompositor_CreateContainerVisual, HRESULT, POINTER(c_void_p))(compositor, byref(motion)) != 0:
            return False
        sprite = c_void_p()
        if fn(compositor, ICompositor_CreateSpriteVisual, HRESULT, POINTER(c_void_p))(compositor, byref(sprite)) != 0:
            return False
        fn(sprite, 7, HRESULT, c_void_p)(sprite, brush)
        root_visual = qi(root, IID_IVisual)
        motion_visual = qi(motion, IID_IVisual)
        sprite_visual = qi(sprite, IID_IVisual)
        fn(root_visual, 36, HRESULT, Vector2)(root_visual, Vector2(float(width), float(height)))
        fn(motion_visual, 36, HRESULT, Vector2)(motion_visual, Vector2(float(glyph), float(glyph)))
        fn(sprite_visual, 36, HRESULT, Vector2)(sprite_visual, Vector2(float(glyph), float(glyph)))
        fn(sprite_visual, 13, HRESULT, Vector3)(sprite_visual, Vector3(2.0, 2.0, 0.0))  # put_CenterPoint hotspot
        fn(motion_visual, 13, HRESULT, Vector3)(motion_visual, Vector3(2.0, 2.0, 0.0))
        fn(motion_visual, 30, HRESULT, ctypes.c_float)(motion_visual, ctypes.c_float(0.0))
        fn(motion_visual, 34, HRESULT, Vector3)(motion_visual, Vector3(1.0, 1.0, 1.0))
        fn(sprite_visual, 30, HRESULT, ctypes.c_float)(sprite_visual, ctypes.c_float(0.0))
        fn(sprite_visual, 34, HRESULT, Vector3)(sprite_visual, Vector3(1.0, 1.0, 1.0))
        fn(sprite_visual, 23, HRESULT, ctypes.c_float)(sprite_visual, ctypes.c_float(1.0))
        motion_children = c_void_p()
        fn(motion, 6, HRESULT, POINTER(c_void_p))(motion, byref(motion_children))
        if motion_children:
            fn(motion_children, 8, HRESULT, c_void_p)(motion_children, sprite_visual)
        root_children = c_void_p()
        fn(root, 6, HRESULT, POINTER(c_void_p))(root, byref(root_children))
        if root_children:
            fn(root_children, 8, HRESULT, c_void_p)(root_children, motion_visual)
        composition_target = qi(target, IID_ICompositionTarget)
        fn(composition_target, 7, HRESULT, c_void_p)(composition_target, root)
        _keep.extend(
            [compositor, desktop, target, d3d, ctx, interop, graphics, surface, surface_interop, brush, root, motion, sprite, root_visual, motion_visual, sprite_visual, composition_target]
        )
        if press_surface:
            _keep.append(press_surface)
        if press_interop:
            _keep.append(press_interop)
        if motion_children:
            _keep.append(motion_children)
        if root_children:
            _keep.append(root_children)
        _surface_interop = surface_interop
        _press_interop = press_interop
        _idle_surface = surface
        _press_surface = press_surface or surface
        _cursor_brush = brush
        _graphics_device = graphics
        _compositor_obj = compositor
        _motion_visual = motion_visual
        _sprite_visual = sprite_visual
        _cursor_visual = motion_visual
        _cursor_origin = (float(origin[0]), float(origin[1]))
        _cursor_size = glyph
        _draw_into(_surface_interop, False)
        if _press_interop:
            _draw_into(_press_interop, True)
        _press_drawn = False
        _attached = True
        _device_lost = False
        return True
    except Exception:
        return False


def attach_cursor_visual(hwnd: int, size: int = 48) -> bool:
    """Back-compat: small HWND sprite. Prefer attach_cursor_stage."""
    return attach_cursor_stage(hwnd, size, size, origin=(0.0, 0.0), glyph=size)


def apply_cursor_pose(x: float, y: float, pose: dict) -> None:
    """Official: position/rotate/scale cursor motion visual; stretch axis on sprite."""
    global _last_cursor_xy, _last_cursor_pose
    visual = _motion_visual or _cursor_visual
    if not visual:
        return
    try:
        ox, oy = _cursor_origin
        fn(visual, 21, HRESULT, Vector3)(visual, Vector3(float(x) - ox, float(y) - oy, 0.0))
        rot = float(pose.get("baseRotationDegrees") or 0) + float(pose.get("scootTiltDegrees") or 0)
        fn(visual, 30, HRESULT, ctypes.c_float)(visual, ctypes.c_float(rot))
        sx = float(pose.get("scaleX") or 1.0)
        sy = float(pose.get("scaleY") or 1.0)
        stretch = float(pose.get("stretchAxisDegrees") or 0)
        sprite = _sprite_visual
        if sprite:
            fn(sprite, 30, HRESULT, ctypes.c_float)(sprite, ctypes.c_float(stretch))
            fn(sprite, 34, HRESULT, Vector3)(sprite, Vector3(sx, sy, 1.0))
        else:
            fn(visual, 34, HRESULT, Vector3)(visual, Vector3(sx, sy, 1.0))
        fn(visual, 23, HRESULT, ctypes.c_float)(visual, ctypes.c_float(float(pose.get("compositeOpacity") or 1.0)))
        want_press = sx < 0.95 or bool(pose.get("press"))
        if want_press != _press_drawn:
            draw_cursor_surface(want_press)
        _last_cursor_xy = (float(x), float(y))
        _last_cursor_pose = dict(pose)
    except Exception:
        return


def replace_cursor_drawing_surface(glyph: int | None = None) -> bool:
    """Official: create replacement cursor drawing surface / swap cursor drawing surface."""
    global _idle_surface, _press_surface, _surface_interop, _press_interop, _cursor_size, _press_drawn
    graphics = _graphics_device
    compositor = _compositor_obj
    brush = _cursor_brush
    size = int(glyph or _cursor_size or CURSOR_GLYPH)
    if not graphics or not compositor or not brush:
        return False
    try:
        idle, idle_interop = _create_drawing_surface(graphics, float(size), float(size))
        if not idle or not idle_interop:
            return False
        press, press_interop = _create_drawing_surface(graphics, float(size), float(size))
        _idle_surface = idle
        _surface_interop = idle_interop
        if press:
            _press_surface = press
            _press_interop = press_interop
        _cursor_size = size
        fn(brush, 13, HRESULT, c_void_p)(brush, idle)
        _draw_into(idle_interop, False)
        if press_interop:
            _draw_into(press_interop, True)
        _press_drawn = False
        _keep.extend([idle, idle_interop])
        if press:
            _keep.extend([press, press_interop])
        return True
    except Exception:
        _mark_device_lost()
        return False


def resize_cursor_surfaces(glyph: int) -> bool:
    """Official: resize cursor sprite / motion visual for target DPI."""
    global _cursor_size
    size = max(int(glyph), 16)
    interop = _surface_interop
    if interop:
        try:
            hr = fn(interop, ICompositionDrawingSurfaceInterop_Resize, HRESULT, SIZE)(interop, SIZE(size, size))
            if is_device_lost(hr):
                _mark_device_lost(hr)
                return False
            if hr == 0:
                if _press_interop:
                    fn(_press_interop, ICompositionDrawingSurfaceInterop_Resize, HRESULT, SIZE)(_press_interop, SIZE(size, size))
                _cursor_size = size
                if _motion_visual:
                    fn(_motion_visual, 36, HRESULT, Vector2)(_motion_visual, Vector2(float(size), float(size)))
                if _sprite_visual:
                    fn(_sprite_visual, 36, HRESULT, Vector2)(_sprite_visual, Vector2(float(size), float(size)))
                _draw_into(_surface_interop, False)
                if _press_interop:
                    _draw_into(_press_interop, True)
                return True
        except Exception:
            pass
    return replace_cursor_drawing_surface(size)


def cursor_stage_attached() -> bool:
    return _motion_visual is not None and _surface_interop is not None
