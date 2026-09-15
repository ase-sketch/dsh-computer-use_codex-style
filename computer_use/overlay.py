"""Cursor + banner overlay recovered from helper overlay/* and display strings."""

from __future__ import annotations

from dataclasses import dataclass, field

BANNER = "DeepSeek Harness is using your computer"
ESC_HINT = "Esc to cancel"
CLASS_NAME = "DshComputerUseCursorOverlay"
ACCESSIBLE_NAME = "dsh-computer-use-status-pill"
ACCENT_HEX = "#FFC400"
BAR_HEIGHT = 52
PILL_HEIGHT = 36
PILL_MARGIN_Y = 8


@dataclass
class OverlayStrings:
    """serde ComputerUseOverlayStrings: usingComputer / escToCancel / accent / locale / ltr|rtl."""

    using_computer: str = BANNER
    esc_to_cancel: str = ESC_HINT
    accent_color: str = ACCENT_HEX
    locale: str = "en"
    reading: str = "ltr"


def parse_hex_color(text: str) -> tuple[float, float, float, float] | None:
    """Official src/overlay/color.rs: parse #RRGGBB (panic lines 24–26)."""
    raw = (text or "").strip()
    if len(raw) != 7 or raw[0] != "#":
        return None
    try:
        red = int(raw[1:3], 16)
        green = int(raw[3:5], 16)
        blue = int(raw[5:7], 16)
    except ValueError:
        return None
    return red / 255.0, green / 255.0, blue / 255.0, 1.0


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(red: float, green: float, blue: float) -> float:
    return 0.2126 * _srgb_to_linear(red) + 0.7152 * _srgb_to_linear(green) + 0.0722 * _srgb_to_linear(blue)


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    light = max(relative_luminance(*fg), relative_luminance(*bg))
    dark = min(relative_luminance(*fg), relative_luminance(*bg))
    return (light + 0.05) / (dark + 0.05)


def pick_ink_color(accent: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """WCAG 4.5:1 text vs pill fill (official color.rs contrast search)."""
    bg = (accent[0], accent[1], accent[2])
    black = (0.05, 0.05, 0.05)
    white = (1.0, 1.0, 1.0)
    if contrast_ratio(black, bg) >= 4.5:
        return (0.05, 0.05, 0.05, 1.0)
    return (1.0, 1.0, 1.0, 1.0)


def estimate_text_width(text: str, *, font_size: float = 16.0) -> float:
    return max(8.0, len(text) * font_size * 0.54)


def compute_pill_layout(
    desktop_w: float,
    desktop_h: float,
    status: str = BANNER,
    cancel: str = ESC_HINT,
    *,
    dpi: float = 1.0,
    status_width: float | None = None,
    cancel_width: float | None = None,
) -> dict[str, float]:
    """Official: compute display overlay status pill layout (centered top)."""
    scale = max(float(dpi), 0.5)
    pad_x = 18.0 * scale
    gap = 14.0 * scale
    height = PILL_HEIGHT * scale
    status_w = float(status_width) if status_width is not None else estimate_text_width(status, font_size=16.0 * scale)
    cancel_w = float(cancel_width) if cancel_width is not None else estimate_text_width(cancel, font_size=16.0 * scale)
    width = pad_x + status_w + gap + 1.0 * scale + gap + cancel_w + pad_x
    max_w = max(120.0, float(desktop_w) * 0.92)
    width = min(width, max_w)
    x = max(0.0, (float(desktop_w) - width) / 2.0)
    y = PILL_MARGIN_Y * scale
    status_x = x + pad_x
    cancel_x = x + width - pad_x - cancel_w
    separator_x = (status_x + status_w + cancel_x) / 2.0
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "radius": height / 2.0,
        "status_x": status_x,
        "cancel_x": cancel_x,
        "status_width": status_w,
        "cancel_width": cancel_w,
        "separator_x": separator_x,
        "bar_height": BAR_HEIGHT * scale,
        "desktop_w": float(desktop_w),
        "desktop_h": float(desktop_h),
    }


def is_rtl_locale() -> bool:
    try:
        import ctypes

        lang = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        primary = lang & 0x3FF
        return primary in {0x01, 0x0D, 0x20, 0x29, 0x5C}
    except Exception:
        return False


@dataclass
class OverlayEvent:
    kind: str
    x: float | None = None
    y: float | None = None
    text: str | None = None


@dataclass
class OverlaySession:
    enabled: bool = False
    events: list[OverlayEvent] = field(default_factory=list)
    visible: bool = False
    cursor_x: float = 0.0
    cursor_y: float = 0.0
    synthetic_until: float = 0.0
    _snapped: bool = False

    def show(self, x: float | None = None, y: float | None = None, *, press: bool = False) -> None:
        if not self.enabled:
            return
        self.visible = True
        self.events.append(OverlayEvent("show_banner", text=f"{BANNER} · {ESC_HINT}"))
        try:
            from computer_use.overlay_win import show_banner

            show_banner()
        except Exception:
            pass
        hook = getattr(self, "esc_hook", None)
        if hook is not None:
            try:
                hook.arm()
            except Exception:
                pass
        if x is not None and y is not None:
            self.move_cursor(x, y, press=press)

    def move_cursor(self, x: float, y: float, *, press: bool = False) -> None:
        if not self.enabled:
            return
        import time

        self.synthetic_until = time.monotonic() + 0.25
        self.events.append(OverlayEvent("move_cursor", x=x, y=y))
        try:
            from computer_use.overlay_cursor import sampled_poses, scoot_pose
            from computer_use.overlay_win import move_software_cursor

            tx, ty = float(x), float(y)
            if not self._snapped:
                pose = scoot_pose(0.0, 0.0, press=press)
                move_software_cursor(tx, ty, pose, samples=[], press=press)
                self._snapped = True
            else:
                frames = sampled_poses(self.cursor_x, self.cursor_y, tx, ty, press=press)
                samples = [(sx, sy) for sx, sy, _pose in frames]
                pose = frames[-1][2] if frames else scoot_pose(tx - self.cursor_x, ty - self.cursor_y, press=press)
                move_software_cursor(tx, ty, pose, samples=samples, press=press)
            self.cursor_x, self.cursor_y = tx, ty
        except Exception:
            self.cursor_x, self.cursor_y = float(x), float(y)

    def hide(self) -> None:
        if not self.enabled and not self.visible:
            return
        self.visible = False
        self._snapped = False
        self.events.append(OverlayEvent("hide"))
        try:
            from computer_use.overlay_win import hide_banner

            hide_banner()
            from computer_use.overlay_win import hide_software_cursor

            hide_software_cursor()
        except Exception:
            pass
        hook = getattr(self, "esc_hook", None)
        if hook is not None:
            try:
                hook.disarm()
            except Exception:
                pass
