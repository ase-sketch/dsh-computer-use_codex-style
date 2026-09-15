//! Optional DSH status pill + drawing-surface cursor. Parent never calls SetSystemCursor.

pub mod motion;

use std::collections::HashMap;
use std::os::windows::process::CommandExt;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU32, AtomicU64, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use windows::core::{w, Interface, HSTRING};
use windows::Foundation::{Size, TimeSpan};
use windows::Graphics::DirectX::{DirectXAlphaMode, DirectXPixelFormat};
use windows::UI::Composition::Desktop::DesktopWindowTarget;
use windows::UI::Composition::{
    AnimationIterationBehavior, AnimationStopBehavior, CompositionBrush, CompositionDrawingSurface,
    CompositionEasingFunction, CompositionGraphicsDevice, CompositionLinearGradientBrush,
    CompositionMappingMode, CompositionPropertySet, CompositionStretch, CompositionSurfaceBrush,
    Compositor, ContainerVisual, ScalarKeyFrameAnimation, SpriteVisual, Visual,
};
use windows::UI::Color;
use windows::Win32::Foundation::{
    COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WAIT_OBJECT_0, WPARAM,
};
use windows::Win32::Globalization::GetUserDefaultUILanguage;
use windows::Win32::Graphics::Direct2D::Common::{
    D2D1_ALPHA_MODE_IGNORE, D2D1_COLOR_F, D2D1_PIXEL_FORMAT, D2D_RECT_F,
};
use windows::Win32::Graphics::Direct2D::{
    D2D1CreateFactory, ID2D1DCRenderTarget, ID2D1Device, ID2D1DeviceContext, ID2D1Factory,
    ID2D1Factory1, D2D1_FACTORY_TYPE_SINGLE_THREADED,
    D2D1_FEATURE_LEVEL_DEFAULT, D2D1_RENDER_TARGET_PROPERTIES, D2D1_RENDER_TARGET_TYPE_DEFAULT,
    D2D1_RENDER_TARGET_USAGE_GDI_COMPATIBLE, D2D1_ROUNDED_RECT, D2D1_DRAW_TEXT_OPTIONS_NONE,
};
use windows::Win32::Graphics::Direct3D::{
    D3D_DRIVER_TYPE, D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP, D3D_FEATURE_LEVEL,
};
use windows::Win32::Graphics::Direct3D11::{
    D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_SDK_VERSION, D3D11CreateDevice, ID3D11Device,
    ID3D11DeviceContext,
};
use windows::Win32::Graphics::DirectWrite::{
    DWriteCreateFactory, IDWriteFactory, IDWriteTextFormat, IDWriteTextLayout, IDWriteTextLayout1,
    DWRITE_FACTORY_TYPE_SHARED, DWRITE_FONT_STRETCH_NORMAL, DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_WEIGHT,
    DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_WEIGHT_SEMI_BOLD, DWRITE_PARAGRAPH_ALIGNMENT_CENTER,
    DWRITE_READING_DIRECTION_LEFT_TO_RIGHT, DWRITE_READING_DIRECTION_RIGHT_TO_LEFT,
    DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_TEXT_METRICS,
    DWRITE_TEXT_RANGE,
};
use windows::Win32::Graphics::Dwm::DwmFlush;
use windows::Win32::Graphics::Dxgi::Common::DXGI_FORMAT_B8G8R8A8_UNORM;
use windows::Win32::Graphics::Dxgi::{
    IDXGIDevice, DXGI_ERROR_DEVICE_REMOVED, DXGI_ERROR_DEVICE_RESET,
};
use windows::Win32::Graphics::Gdi::{
    BeginPaint, CreateCompatibleDC, CreateDIBSection, CreatePen, CreateSolidBrush, DeleteDC,
    DeleteObject, DrawTextW, Ellipse, EndPaint, FillRect, GdiFlush, GetDC, InvalidateRect,
    MonitorFromPoint, Polygon, ReleaseDC, SelectObject, SetBkMode, SetTextColor, BITMAPINFO,
    BITMAPINFOHEADER, BLENDFUNCTION, DIB_RGB_COLORS, DT_CENTER, DT_SINGLELINE, DT_VCENTER,
    HBRUSH, HDC, HGDIOBJ, MONITOR_DEFAULTTONEAREST, PAINTSTRUCT, PS_SOLID, TRANSPARENT,
    AC_SRC_ALPHA, AC_SRC_OVER,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::Foundation::GetLastError;
use windows::Win32::System::Threading::{
    CreateEventW, CreateMutexW, GetCurrentProcessId, GetCurrentThreadId, OpenProcess, ResetEvent,
    SetEvent, TerminateProcess, WaitForSingleObject, PROCESS_QUERY_LIMITED_INFORMATION,
    PROCESS_SYNCHRONIZE, PROCESS_TERMINATE,
};
use windows::Win32::System::WinRT::Composition::{
    ICompositionDrawingSurfaceInterop, ICompositorDesktopInterop, ICompositorInterop,
};
use windows::Win32::UI::Accessibility::{SetWinEventHook, UnhookWinEvent, HWINEVENTHOOK};
use windows::Win32::UI::HiDpi::{
    GetDpiForMonitor, GetDpiForSystem, GetDpiForWindow, SetThreadDpiAwarenessContext,
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, MDT_EFFECTIVE_DPI,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetClientRect, GetCursorPos,
    SetCursorPos,
    GetSystemMetrics, MsgWaitForMultipleObjects, PeekMessageW, PostThreadMessageW, RegisterClassW,
    EnumWindows, GetClassNameW, GetWindowDisplayAffinity, GetWindowRect, GetWindowThreadProcessId,
    IsWindowVisible,
    SetLayeredWindowAttributes, SetWindowDisplayAffinity, SetWindowPos, SetWindowTextW, ShowWindow,
    UpdateLayeredWindow, ULW_ALPHA,
    SystemParametersInfoW, TranslateMessage,
    EVENT_SYSTEM_FOREGROUND, HWND_TOPMOST, LWA_ALPHA, LWA_COLORKEY, MSG, PM_REMOVE, QS_ALLINPUT,
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SWP_HIDEWINDOW,
    SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SPI_SETCURSORS, SWP_SHOWWINDOW, SW_HIDE,
    SW_SHOWNOACTIVATE,
    SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS, WDA_EXCLUDEFROMCAPTURE, WINEVENT_OUTOFCONTEXT, WM_CLOSE,
    WM_DESTROY, WM_DISPLAYCHANGE, WM_DPICHANGED, WM_NULL, WM_PAINT, WM_POWERBROADCAST, WNDCLASSW,
    WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP,
};
use windows_numerics::{Matrix3x2, Vector2, Vector3};

pub const BANNER: &str = "DeepSeek Harness is using your computer";
pub const ESC_HINT: &str = "Esc to cancel";
pub const CLASS_NAME: &str = "DshComputerUseCursorOverlay";
pub const CURSOR_CLASS: &str = "DshComputerUseCursorOverlayPointer";
pub const EDGE_CLASS: &str = "DshComputerUseCursorOverlayEdge";
pub const ACCESSIBLE_NAME: &str = "dsh-computer-use-status-pill";
/// Official `accentColor` default (helper .rdata RVA 0x132FC0). The constructor
/// fallback is `rgb(1, 105, 204)` = `#0169CC`, i.e. the same hue family.
pub const ACCENT_HEX: &str = "#339cff";
/// Official window titles for the two full-virtual-desktop overlay windows
/// (Ghidra 14004791d:258 / :266). Shape of the name is preserved; branding is DSH's.
pub const BANNER_WINDOW_TITLE: &str = "DeepSeek Harness Display Overlay";
pub const CURSOR_WINDOW_TITLE: &str = "DeepSeek Harness Cursor Overlay";

/// `CreateWindowExW` needs a NUL-terminated wide string; `w!` only accepts literals.
fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}
pub const BAR_HEIGHT: i32 = 52;
/// Official pill content height (`fVar53 = scale * 48.0`, 140057dbb:446-490).
pub const PILL_CONTENT_HEIGHT: f32 = 48.0;
/// Official padding between the content box and the pill edge (`scale * 18.0`).
pub const PILL_PAD: f32 = 18.0;
/// Official inner content padding (`scale * 16.0`, the leading `2 * 16 * s` term).
pub const PILL_CONTENT_PAD: f32 = 16.0;
/// Official separator block: `12*s` gap + `4*s` dot + `12*s` gap.
pub const PILL_SEPARATOR: f32 = 28.0;
/// Official top of the pill **content** is `56 * scale`; the root box adds the
/// `18 * scale` padding above it (`offset display overlay pill root` uses
/// `56*s - 18*s`, `140057dbb:460-461`), so the root origin sits 18*s higher
/// (VIS-14).
pub const PILL_ROOT_MARGIN_Y: f32 = 56.0 - PILL_PAD;
/// Fallback sprite size for the GDI path. Live geometry comes from
/// cursor_metrics(): official round(dpi * 1.3125), i.e. 126 px at 96 DPI.
pub const CURSOR_SIZE: i32 = 126;

/// Official rdata 0x139406: Vector2(StartX + TravelX * shimmer.Progress, 0.0)
pub const SHIMMER_OFFSET_EXPRESSION: &str = "Vector2(StartX + TravelX * shimmer.Progress, 0.0)";
/// Official rdata GPU path expression graph (P0–P6 halves).
pub const PATH_OFFSET_EXPRESSION: &str = concat!(
    "motion.SegmentCount < 1.5 ? motion.SingleSegmentPoint : ",
    "(motion.Progress < 0.5 ? motion.FirstHalfPoint : motion.SecondHalfPoint)"
);
// The official DirectComposition expressions carry the same math and are kept in
// `assets`-adjacent form below for traceability. The live implementation evaluates
// the identical cubic + spring model in Rust (`overlay::motion`) and drives the
// sprite per frame, so these expression strings are documentation, not code.
#[allow(dead_code)]
const FIRST_HALF_T: &str = "Min(1.0,Max(0.0,motion.Progress*2.0))";
#[allow(dead_code)]
const SECOND_HALF_T: &str = "Min(1.0,Max(0.0,(motion.Progress-0.5)*2.0))";
/// Official stub form; the real path uses the expanded cubic polynomial.
#[allow(dead_code)]
const SINGLE_SEGMENT_POINT_EXPRESSION: &str = "Lerp(motion.P0, motion.P6, motion.Progress)";

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;
const DXGI_ERROR_INVALID_CALL_AFTER_LOSS: u32 = 0x887A_0020;
const D2DERR_RECREATE_TARGET: u32 = 0x8899_000C;
const RO_E_CLOSED: u32 = 0x8000_0013;
/// Official expression-animation constants, retained as documentation: the live
/// path samples `overlay::motion` instead.
#[allow(dead_code)]
const MAGIC_MOVE_STEPS: i32 = 12;
#[allow(dead_code)]
const P0_P6_COUNT: usize = 7;
const POSITION_TIMEOUT: Duration = Duration::from_millis(400);
/// Official rdata 0x134a29 packed beside paste CTRLV / user input was detected.
pub const FAILED_POSITION_CURSOR_FOR: &str = "failed to position cursor for ";
/// Official rdata 0x134a49.
pub const OVERLAY_ERROR_SEP: &str = " overlay: ";
const SEND_CURSOR_OVERLAY_COMMAND: &str = "send cursor overlay command";
const WAKE_CURSOR_OVERLAY_THREAD: &str = "wake cursor overlay thread";
const CURSOR_OVERLAY_INACTIVE: &str = "cursor overlay is no longer active";
const CURSOR_OVERLAY_INIT: &str = "cursor overlay thread exited before initialization";
const STALE_OWNER: &str = "cleaned up stale cursor overlay owner";
const STALE_WAIT: &str = "timed out waiting for stale cursor overlay process ";
const STALE_EXIT: &str = " to exit";
const ERROR_ALREADY_EXISTS: u32 = 183;
const CURSOR_OVERLAY_LOCK: &str = "cursor overlay state lock poisoned";
const CURSOR_OVERLAY_THREAD_FAILED: &str = "cursor overlay thread failed: ";
const CREATE_WINDOW_FAILED: &str = "CreateWindowExW failed";
#[allow(dead_code)]
const APPLY_CURSOR_MOTION: &str = "apply cursor motion";
const RAISE_BEFORE_POSITION: &str = "raise cursor overlay before cursor position";
const SETCURSORPOS_INITIAL: &str = "SetCursorPos initial overlay cursor position";
#[allow(dead_code)]
const START_SAMPLED_MOTION: &str = "start sampled cursor motion animation";
const POST_OVERLAY_SHUTDOWN: &str = "failed to post cursor overlay shutdown";
const SUPPRESS_RETRY: &str = "system cursor suppress was not acknowledged; restarting cursor manager ";
/// How long the cursor-manager child gets to acknowledge a suppress request.
const SUPPRESS_TIMEOUT: Duration = Duration::from_millis(400);
/// Official `schedule system cursor re-suppression`: the system cursors can be restored
/// behind our back (another process calling `SystemParametersInfo`), which would put the
/// real pointer back on screen next to the fake one.
const SUPPRESS_EVERY: Duration = Duration::from_secs(1);

static HANDLE: OnceLock<OverlayHandle> = OnceLock::new();
static MANAGER: Mutex<Option<std::process::Child>> = Mutex::new(None);
static THREAD_FAILED: Mutex<Option<String>> = Mutex::new(None);
static VISIBLE: AtomicBool = AtomicBool::new(false);
static FORCE_HIDDEN: AtomicBool = AtomicBool::new(false);
static DISPLAY_COMPOSITION: AtomicBool = AtomicBool::new(false);
static CURSOR_STAGE: AtomicBool = AtomicBool::new(false);
static READY: AtomicBool = AtomicBool::new(false);
/// Whether the cursor-manager child acknowledged the last suppress request. Diagnostics
/// only: the value the tests read to tell "one pointer" from "two pointers".
static SUPPRESSED: AtomicBool = AtomicBool::new(false);
static SUPPRESS_FAILURES: AtomicU64 = AtomicU64::new(0);
/// Suppress requests issued, and how many of them came from the re-suppression timer
/// rather than a fresh `show()`. The split is what makes "suppression survives another
/// process restoring the cursors" testable without racing the transient state.
static SUPPRESS_REQUESTS: AtomicU64 = AtomicU64::new(0);
static SUPPRESS_REASSERTS: AtomicU64 = AtomicU64::new(0);
static THREAD_ID: AtomicU32 = AtomicU32::new(0);
/// True between `mask_for_capture()` and `unmask_after_capture()`: the pill is
/// hidden in the compositor while a screenshot is being taken.
static CAPTURE_MASKED: AtomicBool = AtomicBool::new(false);
/// Watchdog deadline for the mask. A mask that is never lifted would hide the pill
/// for the operator forever, which is the exact symptom this mechanism exists to
/// avoid, so the pump lifts it on its own.
static CAPTURE_MASK_DEADLINE: Mutex<Option<Instant>> = Mutex::new(None);
static CAPTURE_MASK_COUNT: AtomicU64 = AtomicU64::new(0);
/// Upper bound for one masked capture. A WGC frame pool answers in well under a
/// second; five seconds is far past "stuck" and far below "the operator notices".
const CAPTURE_MASK_MAX_MS: u64 = 5000;

/// How the pill is kept out of the screenshots the model reads.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum CaptureExclusion {
    /// Hide the pill in the compositor for the duration of a capture (default). The
    /// operator keeps seeing the pill, the model never sees it, and no window
    /// affinity is involved.
    Mask,
    /// `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` on the pill window -- the
    /// official-style exclusion. On some Windows/DWM/GPU combinations the DWM stops
    /// presenting the DirectComposition content *on screen* as well, so the operator
    /// sees the fake cursor and no pill at all while every API reports `visible=true`
    /// (reproduced 2026-09-15 on a 2560x1440 @150% desktop). Opt-in for that reason.
    Wda,
    /// No exclusion: the pill also shows up in the model's screenshots.
    Off,
}

/// Parse the `DSH_CU_OVERLAY_CAPTURE_EXCLUSION` value. Pure, so it is testable
/// without a desktop session; `capture_exclusion()` owns the environment lookup.
fn parse_capture_exclusion(value: Option<&str>) -> CaptureExclusion {
    match value.map(|raw| raw.trim().to_ascii_lowercase()).as_deref() {
        Some("wda") => CaptureExclusion::Wda,
        Some("off") | Some("none") | Some("0") | Some("false") => CaptureExclusion::Off,
        // Anything else -- including an unset variable and a typo -- lands on the
        // default that keeps the pill on screen.
        _ => CaptureExclusion::Mask,
    }
}

pub fn capture_exclusion() -> CaptureExclusion {
    // The diagnostic override wins: it exists so a capture-based probe can read the
    // pill's own pixels (see parity/pill-reshow.mjs).
    if std::env::var("DSH_CU_OVERLAY_CAPTURABLE").is_ok() {
        return CaptureExclusion::Off;
    }
    parse_capture_exclusion(
        std::env::var("DSH_CU_OVERLAY_CAPTURE_EXCLUSION")
            .ok()
            .as_deref(),
    )
}

type OverlayReply = Sender<Result<(), String>>;

enum Cmd {
    Show { reply: Option<OverlayReply> },
    Hide { reply: Option<OverlayReply> },
    Raise,
    Recreate,
    CaptureMask { on: bool, reply: Option<OverlayReply> },
    Cursor {
        x: f32,
        y: f32,
        press: bool,
        reply: Option<OverlayReply>,
    },
    Quit { reply: Option<OverlayReply> },
}

struct OverlayHandle {
    tx: Sender<Cmd>,
    hwnds: std::sync::Arc<Mutex<Vec<isize>>>,
}

struct Ui {
    hwnd: HWND,
    cursor: HWND,
    edge_left: HWND,
    edge_right: HWND,
    visible: bool,
    snapped: bool,
    device_lost: bool,
    /// A hide happened since the last show. Hiding the overlay windows with SW_HIDE /
    /// HWND_BOTTOM drops the layered surface (ULW) and the composition content (DComp),
    /// and the window stays blank when it is shown again: the visible/topmost/painted
    /// state looks perfect while nothing reaches the screen. The official helper never
    /// meets this because it is per-turn and builds fresh windows; this helper is reused
    /// across turns, so the next show rebuilds instead of trusting the stale window.
    hidden_since_show: bool,
    last_recreate: Instant,
    display: Option<DisplayHold>,
    cursor_stage: Option<CursorHold>,
    cursor_x: f32,
    cursor_y: f32,
    /// True once a model action has positioned the fake cursor. Until then the
    /// sprite is seeded from the real system cursor so the first appearance is
    /// not a jump from (0, 0).
    cursor_seeded: bool,
    /// Active cursor motion (official `src/overlay/cursor/motion.rs` model).
    cursor_motion: Option<Motion>,
    /// When the pressed sprite should be released (`schedule cursor press release`).
    cursor_press_until: Option<Instant>,
    /// Active `Scale` transition (VIS-04).
    press_anim: Option<PressAnim>,
    /// Last `Scale` value painted, so a steady press holds 0.7.
    press_scale_last: f32,
    /// Monitor DPI used for the current sprite (VIS-05).
    cursor_dpi: u32,
    /// Wall-clock deadline of the exit fade; the windows hide when it passes
    /// (official waits for the opacity animation to flush, `14004b03c:57-73`).
    fade_deadline: Option<Instant>,
    /// Last `(left, top, sprite, scale_key)` pushed, so a parked cursor does not
    /// re-issue a synchronous `SetWindowPos` on every animation frame
    /// (VIS-01/VIS-30). The scale key forces a repaint when only `Scale` moves.
    last_place: Option<(i32, i32, i32, i32)>,
    /// Frames already painted by the active motion.
    cursor_tick: u32,
    /// When the system cursors are re-blanked next (official `schedule system cursor
    /// re-suppression`), while the overlay stays visible.
    next_suppress: Instant,
}

/// A cursor move in flight: the sampled keyframes plus per-frame timing.
struct Motion {
    from: (f32, f32),
    to: (f32, f32),
    frames: Vec<motion::Frame>,
    /// Pump wake interval while the move runs: `T / (n - 1)`.
    frame_ms: u64,
    /// The official `SetDuration(T)` of the animation, in milliseconds.
    duration_ms: u64,
    /// Wall-clock start of the animation: progress is derived from elapsed time,
    /// exactly like the compositor does, instead of from a frame counter.
    start: Instant,
    /// Index of the last painted sample, so a frame is not repainted every tick.
    painted: usize,
}

/// One `Scale` transition in flight (VIS-04). The official attaches a single
/// 550 ms keyframe to `Scale`; the missing start keyframe means the compositor
/// interpolates from the visual's current value, so the animation is anchored to
/// wherever the previous transition left off.
#[derive(Clone, Copy)]
struct PressAnim {
    start: Instant,
    from: f32,
    to: f32,
}

/// Fallback pump wake interval. The live interval is per-move: the official lays
/// its sampled keyframes out across the whole computed duration `T` (VIS-08).
const CURSOR_FRAME_MS: u64 = 16;
/// Bound on how many queued messages one pump iteration drains, so a message
/// storm cannot make the overlay thread unresponsive.
const MAX_MESSAGES_PER_ITERATION: u32 = 1024;
/// Official `set cursor scale animation duration`: 5 500 000 ticks = **550 ms**
/// (14004f796, `all_functions.c:65229-65273`).
const CURSOR_PRESS_MS: u64 = 550;
/// Official pressed `Scale` keyframe value (`0x12972c` = 0.7).
const CURSOR_PRESS_SCALE: f32 = 0.7;
/// Official overlay opacity duration: `iVar5 = 5000000` ticks = **500 ms**
/// (`140056c79:17-40`), entry and exit alike.
const FADE_MS: i64 = 500;
/// `cubic-bezier(0.22, 1.0, 0.36, 1.0)` (Material decelerate) on the fade.
const FADE_EASE: (f32, f32, f32, f32) = (0.22, 1.0, 0.36, 1.0);
/// Official border pulse duration: `iVar49 = 30000000` ticks = **3000 ms**
/// (`140057dbb:323-325`).
const PULSE_MS: i64 = 3000;
/// `cubic-bezier(0.4, 0.0, 0.2, 1.0)` (Material standard), `140057dbb:311-346`.
const PULSE_EASE: (f32, f32, f32, f32) = (0.4, 0.0, 0.2, 1.0);
/// Official size/offset breath duration: 30 000 000 ticks = **3000 ms**
/// (`140057dbb:351-385`).
const EDGE_BREATH_MS: i64 = 3000;
/// Official shimmer duration (`create text shimmer`): **2000 ms** (`140057dbb:1441-1482`).
const SHIMMER_MS: i64 = 2000;

struct DisplayHold {
    _controller: windows::System::DispatcherQueueController,
    compositor: Compositor,
    _target: DesktopWindowTarget,
    root: ContainerVisual,
    _graphics: Option<GraphicsHold>,
    _shimmer: Option<CompositionPropertySet>,
    _display_fade: Option<ContainerVisual>,
    _edge_fade: Option<ContainerVisual>,
    edge_left: Option<SpriteVisual>,
    edge_right: Option<SpriteVisual>,
}

struct CursorHold {
    compositor: Compositor,
    _target: DesktopWindowTarget,
    _root: ContainerVisual,
    motion: ContainerVisual,
    sprite: SpriteVisual,
    brush: CompositionSurfaceBrush,
    idle: CompositionDrawingSurface,
    press: CompositionDrawingSurface,
    idle_interop: ICompositionDrawingSurfaceInterop,
    press_interop: ICompositionDrawingSurfaceInterop,
    _graphics: GraphicsHold,
    motion_propset: Option<CompositionPropertySet>,
    origin: Vector2,
    press_drawn: bool,
    last_xy: (f32, f32),
    last_pose: CursorPose,
}

struct GraphicsHold {
    _d3d: ID3D11Device,
    _d2d: Option<ID2D1Device>,
    factory: ID2D1Factory1,
    graphics: CompositionGraphicsDevice,
}

#[derive(Clone, Copy, Debug)]
struct PillLayout {
    /// Root box (content + `18*s` on every side).
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    /// Accent body: the official attaches the rounded rectangle to the **content**
    /// visual at the content size (`140057dbb:513,576-581`), so the visible pill is
    /// `48*s` tall inside an `84*s` root, not the whole root (VIS-13).
    body_x: f32,
    body_y: f32,
    body_w: f32,
    body_h: f32,
    radius: f32,
    status_x: f32,
    cancel_x: f32,
    status_width: f32,
    cancel_width: f32,
    separator_x: f32,
}

#[derive(Clone, Copy, Debug, Default)]
struct CursorPose {
    base_rotation_degrees: f32,
    scoot_tilt_degrees: f32,
    stretch_axis_degrees: f32,
    scale_x: f32,
    scale_y: f32,
    composite_opacity: f32,
    press: f32,
}

fn handle() -> &'static OverlayHandle {
    HANDLE.get_or_init(|| {
        let (tx, rx) = mpsc::channel();
        let hwnds = std::sync::Arc::new(Mutex::new(Vec::new()));
        let hwnd_thread = hwnds.clone();
        if let Err(err) = thread::Builder::new()
            .name("cu-overlay".into())
            .spawn(move || ui_loop(rx, hwnd_thread))
        {
            if let Ok(mut slot) = THREAD_FAILED.lock() {
                *slot = Some(err.to_string());
            }
        }
        OverlayHandle { tx, hwnds }
    })
}

pub fn hwnds() -> Vec<isize> {
    HANDLE
        .get()
        .and_then(|h| h.hwnds.lock().ok().map(|g| g.clone()))
        .unwrap_or_default()
}

/// Handles of the *display* overlays only (status pill / shimmer), never the
/// cursor window. Anything that hides or excludes overlay windows from a
/// screenshot must use this, or the model loses sight of its own pointer.
pub fn display_hwnds() -> Vec<isize> {
    hwnds().into_iter().filter(|id| !is_cursor_overlay(*id)).collect()
}

pub fn visible() -> bool {
    VISIBLE.load(Ordering::SeqCst)
}

/// Live overlay diagnostics, exposed through `diagnostic_state`. A test can then
/// know exactly where the fake cursor is drawn and whether each overlay window is
/// currently excluded from capture, instead of guessing from pixels.
pub fn diagnostics() -> serde_json::Value {
    let mut windows = Vec::new();
    for id in hwnds() {
        let hwnd = HWND(id as *mut core::ffi::c_void);
        let mut affinity = 0u32;
        let ok = unsafe { GetWindowDisplayAffinity(hwnd, &mut affinity) }.is_ok();
        let mut rect = RECT::default();
        let have_rect = unsafe { GetWindowRect(hwnd, &mut rect) }.is_ok();
        windows.push(serde_json::json!({
            "hwnd": id,
            "class": overlay_class_name(hwnd),
            "visible": unsafe { IsWindowVisible(hwnd).as_bool() },
            "displayAffinity": if ok { affinity } else { 0 },
            "excludedFromCapture": affinity == WDA_EXCLUDEFROMCAPTURE.0,
            "rect": if have_rect {
                serde_json::json!([rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top])
            } else {
                serde_json::Value::Null
            },
        }));
    }
    let mut value = serde_json::json!({
        "visible": visible(),
        "displayComposition": DISPLAY_COMPOSITION.load(Ordering::SeqCst),
        "cursorStage": CURSOR_STAGE.load(Ordering::SeqCst),
        "pressActive": PRESS_ACTIVE.load(Ordering::SeqCst),

        "cursorScreenX": CURSOR_POS.0.load(Ordering::SeqCst),
        "cursorScreenY": CURSOR_POS.1.load(Ordering::SeqCst),
        "lastInputScreenX": LAST_INPUT.0.load(Ordering::SeqCst),
        "lastInputScreenY": LAST_INPUT.1.load(Ordering::SeqCst),
        "motionActive": MOTION_ACTIVE.load(Ordering::SeqCst),
        "motionTick": MOTION_TICK.load(Ordering::SeqCst),
        "motionFrames": MOTION_FRAMES.load(Ordering::SeqCst),
        "motionTargetX": MOTION_TARGET.0.load(Ordering::SeqCst),
        "motionTargetY": MOTION_TARGET.1.load(Ordering::SeqCst),
        "pumpIters": PUMP_ITERS.load(Ordering::SeqCst),
        "pumpMsgs": PUMP_MSGS.load(Ordering::SeqCst),
        "pumpAnim": PUMP_ANIM.load(Ordering::SeqCst),
        "pumpPill": PUMP_PILL.load(Ordering::SeqCst),
        "pill": {
            "builds": PILL_BUILDS.load(Ordering::SeqCst),
            "buildFails": PILL_BUILD_FAILS.load(Ordering::SeqCst),
            "pushes": PILL_PUSHES.load(Ordering::SeqCst),
            "pushFails": PILL_PUSH_FAILS.load(Ordering::SeqCst),
            "paintCalls": PILL_PAINT_CALLS.load(Ordering::SeqCst),
        },
        "messages": msg_histogram(),
        "recreates": RECREATES.load(Ordering::SeqCst),
        "displayStep": DISPLAY_STEP.lock().map(|g| g.clone()).unwrap_or_default(),
        "pillLayout": PILL_LAYOUT_INFO.lock().map(|g| g.clone()).unwrap_or_default(),
        "pillSprite": PILL_SPRITE
            .lock()
            .ok()
            .and_then(|g| {
                g.as_ref().map(|s| {
                    format!(
                        "{}x{} at {},{} scale={:.3} bytes={}",
                        s.layout.width.round(),
                        s.layout.height.round(),
                        s.layout.x.round(),
                        s.layout.y.round(),
                        s.scale,
                        s.pixels.len()
                    )
                })
            })
            .unwrap_or_default(),
        "cmdLastMs": CMD_LAST_MS.load(Ordering::SeqCst),
        "cmdMaxMs": CMD_MAX_MS.load(Ordering::SeqCst),
        "cmdTotal": CMD_TOTAL.load(Ordering::SeqCst),
        "commands": cmd_histogram(),
        "foregroundTotal": FG_TOTAL.load(Ordering::SeqCst),
        "foregrounds": fg_histogram(),
        "drainLastMs": DRAIN_LAST_MS.load(Ordering::SeqCst),
        "drainMaxMs": DRAIN_MAX_MS.load(Ordering::SeqCst),
        "branchLastMs": BRANCH_LAST_MS.load(Ordering::SeqCst),
        "branchMaxMs": BRANCH_MAX_MS.load(Ordering::SeqCst),
        // The two values that decide how many pointers the operator sees: a visible
        // fake cursor with an un-suppressed system pointer is the "two cursors" bug.
        "systemCursorSuppressed": SUPPRESSED.load(Ordering::SeqCst),
        "systemCursorFailures": SUPPRESS_FAILURES.load(Ordering::SeqCst),
        "systemCursorRequests": SUPPRESS_REQUESTS.load(Ordering::SeqCst),
        "systemCursorReasserts": SUPPRESS_REASSERTS.load(Ordering::SeqCst),
        "cursorManagerAlive": manager_alive(),
        "windows": windows,
    });
    // Inserted after the literal: the `json!` macro expands recursively and the
    // object is already at the crate default recursion limit.
    if let Some(object) = value.as_object_mut() {
        object.insert(
            "cursorPressScale".to_string(),
            serde_json::json!(f32::from_bits(CURSOR_PRESS_SCALE_BITS.load(Ordering::SeqCst))),
        );
        object.insert("cursorDpi".to_string(), serde_json::json!(CURSOR_DPI.load(Ordering::SeqCst)));
        // The size the operator actually sees: the official DPI geometry times the
        // DSH-only scale knob. Surfaced so a smaller pointer can be confirmed from
        // computer_use_health without measuring the screen.
        object.insert("cursorScale".to_string(), serde_json::json!(cursor_scale()));
        object.insert("workerVisible".to_string(), serde_json::json!(WORKER_VISIBLE.load(Ordering::Relaxed)));
        object.insert(
            "pillLastAlpha".to_string(),
            serde_json::json!(f32::from_bits(PILL_LAST_ALPHA_BITS.load(Ordering::Relaxed))),
        );
        // How the pill is being kept out of the model's screenshots, and whether a
        // capture mask is up right now. A stuck `captureMasked` is the one way this
        // design could hide the pill from the operator, so it must be readable.
        object.insert(
            "captureExclusion".to_string(),
            serde_json::json!(match capture_exclusion() {
                CaptureExclusion::Mask => "mask",
                CaptureExclusion::Wda => "wda",
                CaptureExclusion::Off => "off",
            }),
        );
        object.insert("captureMasked".to_string(), serde_json::json!(CAPTURE_MASKED.load(Ordering::SeqCst)));
        object.insert(
            "captureMaskCount".to_string(),
            serde_json::json!(CAPTURE_MASK_COUNT.load(Ordering::SeqCst)),
        );
        let (sprite_px, hotspot_px) = cursor_metrics(unsafe { GetDpiForSystem() });
        object.insert("cursorSpritePx".to_string(), serde_json::json!(sprite_px));
        object.insert("cursorHotspotPx".to_string(), serde_json::json!(hotspot_px));
        object.insert(
            "motionDurationMs".to_string(),
            serde_json::json!(MOTION_DURATION_MS.load(Ordering::SeqCst)),
        );
        object.insert("motionFrameMs".to_string(), serde_json::json!(MOTION_FRAME_MS.load(Ordering::SeqCst)));
        object.insert("motionLastMs".to_string(), serde_json::json!(MOTION_LAST_MS.load(Ordering::SeqCst)));
        object.insert(
            "motionElapsedMs".to_string(),
            serde_json::json!(MOTION_START
                .lock()
                .ok()
                .and_then(|slot| *slot)
                .map(|start| start.elapsed().as_millis() as u64)
                .unwrap_or(0)),
        );
        object.insert(
            "cursorRasterizations".to_string(),
            serde_json::json!(CURSOR_RASTERIZATIONS.load(Ordering::SeqCst)),
        );
    }
    value
}

/// Last position the fake cursor was placed at, in physical screen pixels.
static CURSOR_POS: (AtomicI32, AtomicI32) = (AtomicI32::new(0), AtomicI32::new(0));
/// Last physical screen point an action targeted.
static LAST_INPUT: (AtomicI32, AtomicI32) = (AtomicI32::new(0), AtomicI32::new(0));
static PRESS_ACTIVE: AtomicBool = AtomicBool::new(false);
/// True while the cursor window is driven by UpdateLayeredWindow (per-pixel
/// alpha). Flips to false for good if that ever fails, which restores the
/// colour-keyed GDI sprite.
static CURSOR_LAYERED: AtomicBool = AtomicBool::new(true);
/// Monitor DPI driving the current sprite (VIS-05).
static CURSOR_DPI: AtomicU32 = AtomicU32::new(96);
/// Current cursor `Scale`, as `f32` bits, for diagnostics/tests (VIS-04).
static CURSOR_PRESS_SCALE_BITS: AtomicU32 = AtomicU32::new(0x3F80_0000);
/// Synthetic cursor size multiplier as f32 bits (0x3F80_0000 = 1.0 = the official
/// size). DSH-only knob: the overlay is driven by the display DPI alone and never
/// consults the Windows cursor-size setting, so shrinking the pointer cannot change
/// the local desktop configuration (and that configuration cannot change it here).
static CURSOR_SCALE_BITS: AtomicU32 = AtomicU32::new(0x3F80_0000);
/// Cursor sprite rasterisations, so a per-frame re-raster is detectable (VIS-30).
static CURSOR_RASTERIZATIONS: AtomicU64 = AtomicU64::new(0);
/// Set when a D2D/Composition draw reports a lost device: the official rebuilds
/// the whole overlay and retries (`recreate cursor overlay window`, VIS-25).
static DEVICE_LOST: AtomicBool = AtomicBool::new(false);
/// Exit-fade state for the UpdateLayeredWindow pill: `(start, from, to)` (VIS-20).
static PILL_FADE: Mutex<Option<(Instant, f32, f32)>> = Mutex::new(None);

// --- Pump / motion instrumentation -------------------------------------------
// A cosmetic cursor that never arrives is indistinguishable from a capture bug
// without counters, so the message pump and the motion state are both exposed
// through diagnostics().
static PUMP_ITERS: AtomicU64 = AtomicU64::new(0);
static PUMP_MSGS: AtomicU64 = AtomicU64::new(0);
static PUMP_ANIM: AtomicU64 = AtomicU64::new(0);
static PUMP_PILL: AtomicU64 = AtomicU64::new(0);
/// Pill render counters: build / push attempts and successes.
static PILL_BUILDS: AtomicU64 = AtomicU64::new(0);
static PILL_BUILD_FAILS: AtomicU64 = AtomicU64::new(0);
static PILL_PUSHES: AtomicU64 = AtomicU64::new(0);
/// The alpha of the most recent layered push, as f32 bits. A window that is visible,
/// topmost and painted can still be blank when the pushed alpha is ~0, and nothing else
/// in the API surface distinguishes those two states.
static PILL_LAST_ALPHA_BITS: AtomicU32 = AtomicU32::new(0);
/// The overlay worker's own `ui.visible` (the parent's VISIBLE flag is set before the
/// Show command is even consumed, so it cannot answer "did apply_show run"?
static WORKER_VISIBLE: AtomicBool = AtomicBool::new(false);
static PILL_PUSH_FAILS: AtomicU64 = AtomicU64::new(0);
static PILL_PAINT_CALLS: AtomicU64 = AtomicU64::new(0);
static MOTION_ACTIVE: AtomicBool = AtomicBool::new(false);
static MOTION_TICK: AtomicI32 = AtomicI32::new(-1);
static MOTION_FRAMES: AtomicI32 = AtomicI32::new(0);
static MOTION_TARGET: (AtomicI32, AtomicI32) = (AtomicI32::new(0), AtomicI32::new(0));
/// Planned total duration of the active move, in milliseconds (VIS-08), and the
/// per-frame interval the pump should use.
static MOTION_DURATION_MS: AtomicU64 = AtomicU64::new(0);
static MOTION_FRAME_MS: AtomicU64 = AtomicU64::new(0);
static MOTION_START: Mutex<Option<Instant>> = Mutex::new(None);
/// Wall-clock milliseconds the last completed motion actually took.
static MOTION_LAST_MS: AtomicU64 = AtomicU64::new(0);
/// Message-id histogram for the overlay pump. A message storm starves the
/// cursor animation, and this is how the offending id gets identified.
static MSG_HIST: Mutex<Option<HashMap<u32, u64>>> = Mutex::new(None);
/// Overlay teardown/rebuild count. `recreate` is expensive, so a pump that takes
/// that branch every iteration looks frozen; this counter proves it either way.
static RECREATES: AtomicU64 = AtomicU64::new(0);
/// Last completed step of attach_display, plus the pill layout it computed. The
/// status pill is a DirectComposition visual tree, so when it does not appear on
/// screen there is nothing in the API surface that says why.
static DISPLAY_STEP: Mutex<String> = Mutex::new(String::new());
static PILL_LAYOUT_INFO: Mutex<String> = Mutex::new(String::new());

fn note_display_step(step: &str) {
    if let Ok(mut slot) = DISPLAY_STEP.lock() {
        *slot = step.to_string();
    }
}
/// Command-drain timing and volume. A pump stuck inside command handling can
/// look identical to a pump that never runs, so both halves are timed.
static CMD_LAST_MS: AtomicU64 = AtomicU64::new(0);
static CMD_MAX_MS: AtomicU64 = AtomicU64::new(0);
static CMD_TOTAL: AtomicU64 = AtomicU64::new(0);
static CMD_HIST: Mutex<Option<HashMap<&'static str, u64>>> = Mutex::new(None);
/// Which windows actually raise EVENT_SYSTEM_FOREGROUND. A foreground storm both
/// starves the pump and invalidates observations, so the offending window has to
/// be identifiable rather than guessed at.
static FG_HIST: Mutex<Option<HashMap<String, u64>>> = Mutex::new(None);
static FG_TOTAL: AtomicU64 = AtomicU64::new(0);

/// True when the window belongs to this process, so its foreground events are
/// our own overlay and must not be treated as external activity.
fn process_owns_window(hwnd: HWND) -> bool {
    let mut pid = 0u32;
    unsafe {
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
    }
    pid != 0 && pid == std::process::id()
}

fn note_foreground(hwnd: HWND) {
    FG_TOTAL.fetch_add(1, Ordering::Relaxed);
    let mut buf = [0u16; 256];
    let n = unsafe { GetClassNameW(hwnd, &mut buf) };
    let class = if n > 0 {
        String::from_utf16_lossy(&buf[..n as usize])
    } else {
        "<no class>".to_string()
    };
    let mut pid = 0u32;
    unsafe {
        windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId(hwnd, Some(&mut pid));
    }
    let key = format!("{}#{}", class, pid);
    if let Ok(mut slot) = FG_HIST.lock() {
        let hist = slot.get_or_insert_with(HashMap::new);
        *hist.entry(key).or_insert(0) += 1;
    }
}

fn fg_histogram() -> Vec<serde_json::Value> {
    let Ok(slot) = FG_HIST.lock() else { return Vec::new() };
    let Some(hist) = slot.as_ref() else { return Vec::new() };
    let mut rows: Vec<(String, u64)> = hist.iter().map(|(k, v)| (k.clone(), *v)).collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1));
    rows.truncate(6);
    rows.into_iter()
        .map(|(key, count)| serde_json::json!({ "window": key, "count": count }))
        .collect()
}

fn note_cmd(kind: &'static str) {
    CMD_TOTAL.fetch_add(1, Ordering::Relaxed);
    if let Ok(mut slot) = CMD_HIST.lock() {
        let hist = slot.get_or_insert_with(HashMap::new);
        *hist.entry(kind).or_insert(0) += 1;
    }
}

fn cmd_histogram() -> Vec<serde_json::Value> {
    let Ok(slot) = CMD_HIST.lock() else { return Vec::new() };
    let Some(hist) = slot.as_ref() else { return Vec::new() };
    let mut rows: Vec<(&'static str, u64)> = hist.iter().map(|(k, v)| (*k, *v)).collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1));
    rows.truncate(8);
    rows.into_iter()
        .map(|(kind, count)| serde_json::json!({ "kind": kind, "count": count }))
        .collect()
}
/// Milliseconds the pump spent draining messages in the most recent iteration.
static DRAIN_LAST_MS: AtomicU64 = AtomicU64::new(0);
static DRAIN_MAX_MS: AtomicU64 = AtomicU64::new(0);
/// Milliseconds the pump spent in the animation/wait branch of the most recent
/// iteration.
static BRANCH_LAST_MS: AtomicU64 = AtomicU64::new(0);
static BRANCH_MAX_MS: AtomicU64 = AtomicU64::new(0);

fn note_msg(id: u32) {
    if let Ok(mut slot) = MSG_HIST.lock() {
        let hist = slot.get_or_insert_with(HashMap::new);
        *hist.entry(id).or_insert(0) += 1;
    }
}

fn msg_histogram() -> Vec<serde_json::Value> {
    let Ok(slot) = MSG_HIST.lock() else { return Vec::new() };
    let Some(hist) = slot.as_ref() else { return Vec::new() };
    let mut rows: Vec<(u32, u64)> = hist.iter().map(|(k, v)| (*k, *v)).collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1));
    rows.truncate(8);
    rows.into_iter()
        .map(|(id, count)| serde_json::json!({ "id": id, "count": count }))
        .collect()
}

pub fn exclude_from_capture(hwnd: isize) -> bool {
    if hwnd == 0 {
        return false;
    }
    unsafe {
        SetWindowDisplayAffinity(HWND(hwnd as *mut core::ffi::c_void), WDA_EXCLUDEFROMCAPTURE).is_ok()
    }
}

/// Hide the *display* overlay from capture, and only the display overlay.
///
/// The cursor overlay must stay capturable: it is the model's own pointer, so the
/// model has to see where it pointed in the screenshots it reads. Official
/// (Ghidra 14004791d:292) excludes the display overlay only. Excluding every
/// window in `hwnds()` here silently re-breaks that on every observe, because
/// `hwnds()` also carries the cursor window.
pub fn exclude_overlay_from_capture() -> bool {
    // Only the affinity mode brands the window; the default (Mask) hides the pill for
    // the duration of one capture and leaves the window alone. Without this guard the
    // affinity was applied on *every* observe, which outlives the screenshot: on a
    // desktop where the DWM then stops presenting the DirectComposition content, the
    // operator lost the pill for the rest of the session (observed 2026-09-15).
    if capture_exclusion() != CaptureExclusion::Wda {
        return true;
    }
    let mut all = true;
    for id in hwnds() {
        if is_cursor_overlay(id) {
            continue;
        }
        all &= exclude_from_capture(id);
    }
    all
}

/// True when the window handle belongs to the cursor overlay, identified by
/// window class so it also matches a leftover window from another process.
fn is_cursor_overlay(id: isize) -> bool {
    if id == 0 {
        return false;
    }
    let class = overlay_class_name(HWND(id as *mut core::ffi::c_void));
    class == CURSOR_CLASS || class == "CodexComputerUseCursorOverlayPointer"
}

pub fn show() {
    FORCE_HIDDEN.store(false, Ordering::SeqCst);
    let suppressed = ensure_system_cursor_suppressed();
    SUPPRESSED.store(suppressed, Ordering::SeqCst);
    if !suppressed {
        SUPPRESS_FAILURES.fetch_add(1, Ordering::SeqCst);
    }
    VISIBLE.store(true, Ordering::SeqCst);
    crate::interrupt::arm();
    let _ = handle();
    let _ = post(Cmd::Show { reply: None });
}

/// Start (or restart) the cursor-manager child and blank the system pointer until the
/// child acknowledges it.
///
/// One retry, because the first child of a generation can exit on a stale shut-down
/// signal (see `spawn_system_cursor_manager`) and a silently un-suppressed overlay is
/// exactly the "two pointers on the desktop" the operator saw.
fn ensure_system_cursor_suppressed() -> bool {
    ensure_events();
    for attempt in 0..2 {
        let _ = spawn_system_cursor_manager();
        if suppress_system_cursors(SUPPRESS_TIMEOUT) {
            return true;
        }
        eprintln!("{SUPPRESS_RETRY}{attempt}");
        reap_manager();
    }
    false
}

/// Ask the cursor-manager child to blank every system cursor and wait for its ack.
///
/// The acknowledgement is what makes "exactly one pointer is on screen" observable.
/// Without it a manager that never started left the fake cursor drawn beside the
/// still-visible system pointer while `show()` reported success either way.
fn suppress_system_cursors(timeout: Duration) -> bool {
    SUPPRESS_REQUESTS.fetch_add(1, Ordering::SeqCst);
    // Manual-reset and shared with the child: clear it first, or an acknowledgement
    // from an earlier generation makes a dead manager look healthy.
    reset_manager_event(w!("Local\\DshComputerUse-CursorAck"));
    signal_event(true);
    wait_manager_event(w!("Local\\DshComputerUse-CursorAck"), timeout)
}

/// Drop the manager slot when the child has exited, so the next spawn starts a fresh
/// generation instead of reporting the corpse as a live manager.
fn reap_manager() {
    if let Ok(mut slot) = MANAGER.lock() {
        if let Some(mut child) = slot.take() {
            if child.try_wait().ok().flatten().is_none() {
                *slot = Some(child);
            }
        }
    }
}

fn manager_alive() -> bool {
    MANAGER
        .lock()
        .map(|mut slot| match slot.as_mut() {
            Some(child) => child.try_wait().ok().flatten().is_none(),
            None => false,
        })
        .unwrap_or(false)
}

pub fn hide() {
    FORCE_HIDDEN.store(true, Ordering::SeqCst);
    signal_event(false);
    SUPPRESSED.store(false, Ordering::SeqCst);
    VISIBLE.store(false, Ordering::SeqCst);
    if HANDLE.get().is_some() {
        let _ = post(Cmd::Hide { reply: None });
    }
    force_hide_overlay_windows();
    stop_system_cursor_manager();
    restore_system_cursors();
    if !overlay_windows_visible() {
        crate::interrupt::disarm();
    }
}

/// Hide the pill for the duration of one screenshot so the model never reads its own
/// status pill back, while the operator keeps seeing it. Returns true when a mask was
/// requested; the caller must lift it with `unmask_after_capture()`.
pub fn mask_for_capture() -> bool {
    if capture_exclusion() != CaptureExclusion::Mask {
        return false;
    }
    // Nothing on screen, nothing to hide: masking would only risk a stuck mask.
    if !VISIBLE.load(Ordering::SeqCst) {
        return false;
    }
    if wait_cmd(|reply| Cmd::CaptureMask { on: true, reply: Some(reply) }).is_err() {
        // No overlay thread, or it is wedged. Skipping the mask can only make a
        // screenshot contain the pill; it can never hide the pill from the operator.
        return false;
    }
    true
}

/// Lift the mask requested by `mask_for_capture()`.
///
/// Called on every capture, including the ones that never masked (the overlay was hidden,
/// the affinity mode is in force, the mask command timed out). The no-op guard keeps those
/// captures from issuing a command that would cancel a running fade animation or re-write
/// the root opacity for no reason, while still lifting a mask that the worker did apply
/// even though the caller never saw the reply.
pub fn unmask_after_capture() {
    if !CAPTURE_MASKED.load(Ordering::SeqCst) {
        return;
    }
    let _ = wait_cmd(|reply| Cmd::CaptureMask { on: false, reply: Some(reply) });
}

fn restore_system_cursors() {
    unsafe {
        let _ = SystemParametersInfoW(SPI_SETCURSORS, 0, None, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0));
    }
}

unsafe extern "system" fn destroy_overlay_enum(hwnd: HWND, _lparam: LPARAM) -> windows::core::BOOL {
    let class = {
        let mut buf = [0u16; 256];
        let n = windows::Win32::UI::WindowsAndMessaging::GetClassNameW(hwnd, &mut buf);
        if n <= 0 {
            return windows::core::BOOL(1);
        }
        String::from_utf16_lossy(&buf[..n as usize])
    };
    if class == CLASS_NAME
        || class == CURSOR_CLASS
        || class == "CodexComputerUseCursorOverlay"
        || class == EDGE_CLASS
        || class == "CodexComputerUseCursorOverlayPointer"
    {
        let _ = ShowWindow(hwnd, SW_HIDE);
        let _ = SetWindowPos(
            hwnd,
            Some(windows::Win32::UI::WindowsAndMessaging::HWND_BOTTOM),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_HIDEWINDOW,
        );
    }
    windows::core::BOOL(1)
}

fn force_hide_overlay_windows() {
    unsafe {
        let _ = EnumWindows(Some(destroy_overlay_enum), LPARAM(0));
    }
}

fn overlay_class_name(hwnd: HWND) -> String {
    let mut buf = [0u16; 256];
    let n = unsafe { windows::Win32::UI::WindowsAndMessaging::GetClassNameW(hwnd, &mut buf) };
    if n <= 0 {
        return String::new();
    }
    String::from_utf16_lossy(&buf[..n as usize])
}

fn is_overlay_class(class: &str) -> bool {
    class == CLASS_NAME
        || class == CURSOR_CLASS
        || class == EDGE_CLASS
        || class == "CodexComputerUseCursorOverlay"
        || class == "CodexComputerUseCursorOverlayPointer"
}

unsafe extern "system" fn collect_stale_overlay_pid(hwnd: HWND, lparam: LPARAM) -> windows::core::BOOL {
    if !is_overlay_class(&overlay_class_name(hwnd)) {
        return windows::core::BOOL(1);
    }
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid)) };
    let me = unsafe { GetCurrentProcessId() };
    if pid != 0 && pid != me {
        let pids = &mut *(lparam.0 as *mut Vec<u32>);
        if !pids.contains(&pid) {
            pids.push(pid);
        }
    }
    windows::core::BOOL(1)
}

/// Official overlay/mod.rs: wait for a leftover helper that still owns the
/// named mutex / overlay HWND, then hide those windows before creating ours.
fn reclaim_stale_overlay() {
    let mut pids = Vec::new();
    unsafe {
        let _ = EnumWindows(Some(collect_stale_overlay_pid), LPARAM(&mut pids as *mut Vec<u32> as isize));
    }
    for pid in pids {
        unsafe {
            let access = PROCESS_SYNCHRONIZE | PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION;
            let Ok(proc) = OpenProcess(access, false, pid) else {
                continue;
            };
            let wr = WaitForSingleObject(proc, 3000);
            if wr == windows::Win32::Foundation::WAIT_TIMEOUT {
                eprintln!("{STALE_WAIT}{pid}{STALE_EXIT}");
                let _ = TerminateProcess(proc, 1);
            } else {
                eprintln!("{STALE_OWNER}");
            }
        }
    }
    force_hide_overlay_windows();
}

fn claim_overlay_mutex() {
    unsafe {
        let Ok(mutex) = CreateMutexW(None, true, w!("Local\\DshComputerUseCursorOverlay")) else {
            return;
        };
        if GetLastError().0 == ERROR_ALREADY_EXISTS {
            let wr = WaitForSingleObject(mutex, 3000);
            if wr == windows::Win32::Foundation::WAIT_TIMEOUT {
                eprintln!("{STALE_WAIT}0{STALE_EXIT}");
            } else {
                eprintln!("{STALE_OWNER}");
            }
        }
    }
}

fn overlay_windows_visible() -> bool {
    let mut found = false;
    unsafe {
        let _ = EnumWindows(
            Some(overlay_visible_enum),
            LPARAM(&mut found as *mut bool as isize),
        );
    }
    found
}

unsafe extern "system" fn overlay_visible_enum(hwnd: HWND, lparam: LPARAM) -> windows::core::BOOL {
    let class = {
        let mut buf = [0u16; 256];
        let n = windows::Win32::UI::WindowsAndMessaging::GetClassNameW(hwnd, &mut buf);
        if n <= 0 {
            return windows::core::BOOL(1);
        }
        String::from_utf16_lossy(&buf[..n as usize])
    };
    if class == CLASS_NAME
        || class == CURSOR_CLASS
        || class == EDGE_CLASS
        || class == "CodexComputerUseCursorOverlay"
        || class == "CodexComputerUseCursorOverlayPointer"
    {
        if IsWindowVisible(hwnd).as_bool() {
            let flag = &mut *(lparam.0 as *mut bool);
            *flag = true;
            return windows::core::BOOL(0);
        }
    }
    windows::core::BOOL(1)
}

fn force_destroy_overlay_windows() {
    force_hide_overlay_windows();
}

pub fn shutdown_overlay() -> Result<(), String> {
    if HANDLE.get().is_none() {
        return Ok(());
    }
    post(Cmd::Quit { reply: None }).map_err(|_| POST_OVERLAY_SHUTDOWN.to_string())
}

/// Official rdata 0x134a29/0x134a49: `failed to position cursor for {action} overlay: {err}`.
pub fn position_error(action: &str, err: &str) -> String {
    format!("{FAILED_POSITION_CURSOR_FOR}{action}{OVERLAY_ERROR_SEP}{err}")
}

pub fn move_cursor(x: f32, y: f32, press: bool) -> Result<(), String> {
    ensure_overlay()?;
    wait_cmd(|reply| Cmd::Show { reply: Some(reply) })?;
    wait_cmd(|reply| Cmd::Cursor {
        x,
        y,
        press,
        reply: Some(reply),
    })
}

pub fn position_for(action: &str, x: f32, y: f32, press: bool) -> Result<(), String> {
    move_cursor(x, y, press).map_err(|err| position_error(action, &err))
}

fn overlay_thread_error() -> Result<(), String> {
    match THREAD_FAILED.lock() {
        Ok(slot) => {
            if let Some(err) = slot.as_ref() {
                Err(format!("{CURSOR_OVERLAY_THREAD_FAILED}{err}"))
            } else {
                Ok(())
            }
        }
        Err(_) => Err(CURSOR_OVERLAY_LOCK.to_string()),
    }
}

fn ensure_overlay() -> Result<(), String> {
    let _ = handle();
    overlay_thread_error()?;
    let deadline = Instant::now() + Duration::from_secs(2);
    while !READY.load(Ordering::SeqCst) {
        overlay_thread_error()?;
        if Instant::now() >= deadline {
            return Err(CURSOR_OVERLAY_INIT.to_string());
        }
        thread::sleep(Duration::from_millis(5));
    }
    overlay_thread_error()
}

fn wake_overlay_thread() {
    let tid = THREAD_ID.load(Ordering::SeqCst);
    if tid != 0 {
        if unsafe { PostThreadMessageW(tid, WM_NULL, WPARAM(0), LPARAM(0)) }.is_err() {
            eprintln!("{WAKE_CURSOR_OVERLAY_THREAD}");
        }
    }
}

fn post(cmd: Cmd) -> Result<(), String> {
    let handle = HANDLE
        .get()
        .ok_or_else(|| CURSOR_OVERLAY_INIT.to_string())?;
    handle
        .tx
        .send(cmd)
        .map_err(|_| SEND_CURSOR_OVERLAY_COMMAND.to_string())?;
    wake_overlay_thread();
    Ok(())
}

fn wait_cmd(make: impl FnOnce(OverlayReply) -> Cmd) -> Result<(), String> {
    let (tx, rx) = mpsc::channel();
    post(make(tx))?;
    match rx.recv_timeout(POSITION_TIMEOUT) {
        Ok(result) => result,
        Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => {
            Err(CURSOR_OVERLAY_INACTIVE.to_string())
        }
    }
}

fn send_reply(slot: Option<OverlayReply>, result: Result<(), String>) {
    if let Some(tx) = slot {
        let _ = tx.send(result);
    }
}

pub fn stop_system_cursor_manager() {
    signal_event(false);
    if let Ok(mut slot) = MANAGER.lock() {
        if let Some(mut child) = slot.take() {
            // Let the child restore the cursors itself, then kill it and *clear* the
            // shut-down signal. A manual-reset event left signalled kills the next
            // child on startup, which is how suppression was lost after the first
            // hide and the operator ended up with two pointers on screen.
            set_manager_event(w!("Local\\DshComputerUse-CursorShutdown"));
            thread::sleep(Duration::from_millis(60));
            let _ = child.kill();
            let _ = child.wait();
            reset_manager_event(w!("Local\\DshComputerUse-CursorShutdown"));
        }
    }
    restore_system_cursors();
    SUPPRESSED.store(false, Ordering::SeqCst);
}

pub fn spawn_system_cursor_manager() -> Result<(), String> {
    let mut slot = MANAGER.lock().map_err(|_| "cursor manager lock".to_string())?;
    if let Some(child) = slot.as_mut() {
        if child.try_wait().ok().flatten().is_none() {
            return Ok(());
        }
    }
    ensure_events();
    // A manual-reset shut-down event stays signalled: `CreateEventW` on the existing
    // object hands the new child a signalled event, `run_system_cursor_manager` takes
    // that branch immediately, restores the cursors and exits without ever
    // suppressing. Clear it (and any stale restore request) before every generation.
    reset_manager_event(w!("Local\\DshComputerUse-CursorShutdown"));
    reset_manager_event(w!("Local\\DshComputerUse-CursorRestore"));
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let child = Command::new(exe)
        .arg("--system-cursor-manager")
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB)
        .spawn()
        .map_err(|e| e.to_string())?;
    *slot = Some(child);
    Ok(())
}

/// Open (creating when absent) one of the named cursor-manager events.
///
/// `windows::Win32::Foundation::HANDLE` has no `Drop`, so nothing closes these
/// handles; that is deliberate. A named kernel object lives only while some handle
/// refers to it, so keeping one handle per event open for the whole process is what
/// lets the parent set a request before the freshly spawned child has opened the
/// object: a signal set on an object with no handles is silently dropped.
fn manager_event(name: windows::core::PCWSTR) -> windows::Win32::Foundation::HANDLE {
    unsafe { CreateEventW(None, true, false, name).unwrap_or_default() }
}

fn set_manager_event(name: windows::core::PCWSTR) {
    let handle = manager_event(name);
    if !handle.0.is_null() {
        unsafe {
            let _ = SetEvent(handle);
        }
    }
}

fn reset_manager_event(name: windows::core::PCWSTR) {
    let handle = manager_event(name);
    if !handle.0.is_null() {
        unsafe {
            let _ = ResetEvent(handle);
        }
    }
}

fn wait_manager_event(name: windows::core::PCWSTR, timeout: Duration) -> bool {
    let handle = manager_event(name);
    if handle.0.is_null() {
        return false;
    }
    unsafe { WaitForSingleObject(handle, timeout.as_millis() as u32) == WAIT_OBJECT_0 }
}

fn ensure_events() {
    for name in [
        w!("Local\\DshComputerUse-CursorSuppress"),
        w!("Local\\DshComputerUse-CursorRestore"),
        w!("Local\\DshComputerUse-CursorShutdown"),
        w!("Local\\DshComputerUse-CursorReady"),
        w!("Local\\DshComputerUse-CursorAck"),
    ] {
        let _ = manager_event(name);
    }
}

fn signal_event(suppress: bool) {
    let name = if suppress {
        w!("Local\\DshComputerUse-CursorSuppress")
    } else {
        w!("Local\\DshComputerUse-CursorRestore")
    };
    set_manager_event(name);
}

fn cubic_expr(t: &str, a: &str, b: &str, c: &str, d: &str) -> String {
    let omt = format!("(1.0-({t}))");
    format!("{omt}*{omt}*{omt}*{a}+3.0*{omt}*{omt}*({t})*{b}+3.0*{omt}*({t})*({t})*{c}+({t})*({t})*({t})*{d}")
}

fn first_half_point_expression() -> String {
    cubic_expr(FIRST_HALF_T, "motion.P0", "motion.P1", "motion.P2", "motion.P3")
}

fn second_half_point_expression() -> String {
    cubic_expr(SECOND_HALF_T, "motion.P3", "motion.P4", "motion.P5", "motion.P6")
}

fn ticks_100ns(ms: i64) -> TimeSpan {
    TimeSpan {
        Duration: ms.max(1) * 10_000,
    }
}

fn parse_hex_color(text: &str) -> Option<(f32, f32, f32, f32)> {
    let raw = text.trim();
    if raw.len() != 7 || !raw.starts_with('#') {
        return None;
    }
    let red = u8::from_str_radix(&raw[1..3], 16).ok()?;
    let green = u8::from_str_radix(&raw[3..5], 16).ok()?;
    let blue = u8::from_str_radix(&raw[5..7], 16).ok()?;
    Some((red as f32 / 255.0, green as f32 / 255.0, blue as f32 / 255.0, 1.0))
}

fn srgb_to_linear(channel: f32) -> f32 {
    if channel <= 0.03928 {
        channel / 12.92
    } else {
        ((channel + 0.055) / 1.055).powf(2.4)
    }
}

fn relative_luminance(red: f32, green: f32, blue: f32) -> f32 {
    0.2126 * srgb_to_linear(red) + 0.7152 * srgb_to_linear(green) + 0.0722 * srgb_to_linear(blue)
}

fn contrast_ratio(fg: (f32, f32, f32), bg: (f32, f32, f32)) -> f32 {
    let light = relative_luminance(fg.0, fg.1, fg.2).max(relative_luminance(bg.0, bg.1, bg.2));
    let dark = relative_luminance(fg.0, fg.1, fg.2).min(relative_luminance(bg.0, bg.1, bg.2));
    (light + 0.05) / (dark + 0.05)
}

/// sRGB -> linear with the official 0.04045 knee and [0,1] clamp
/// (`FUN_140052c4b`), used by the Oklab step below. The WCAG ratio above keeps
/// its own 0.03928 knee, which is the behaviour the report finds the official
/// 4.5/4.8 thresholds consistent with.
fn srgb_to_linear_official(channel: f32) -> f32 {
    let c = channel.clamp(0.0, 1.0);
    if c > 0.04045 {
        ((c + 0.055) / 1.055).powf(2.4)
    } else {
        c / 12.92
    }
}

/// linear -> sRGB with the official 0.0031308 knee (`FUN_140052bfb`).
fn linear_to_srgb_official(channel: f32) -> f32 {
    let c = channel.clamp(0.0, 1.0);
    if c <= 0.003_130_8 {
        c * 12.92
    } else {
        1.055 * c.powf(1.0 / 2.4) - 0.055
    }
}

/// sRGB -> Oklab, exactly the matrix in `FUN_140052755`.
fn srgb_to_oklab(red: f32, green: f32, blue: f32) -> (f32, f32, f32) {
    let r = srgb_to_linear_official(red);
    let g = srgb_to_linear_official(green);
    let b = srgb_to_linear_official(blue);
    let l = (0.412_221_46 * r + 0.536_332_55 * g + 0.051_445_995 * b).cbrt();
    let m = (0.211_903_5 * r + 0.680_699_5 * g + 0.107_396_96 * b).cbrt();
    let s = (0.088_302_46 * r + 0.281_718_85 * g + 0.629_978_7 * b).cbrt();
    (
        0.210_454_26 * l + 0.793_617_8 * m - 0.004_072_047 * s,
        1.977_998_5 * l - 2.428_592_2 * m + 0.450_593_7 * s,
        0.025_904_037 * l + 0.782_771_77 * m - 0.808_675_77 * s,
    )
}

/// Oklab -> linear RGB (`FUN_140052aa5`).
fn oklab_to_linear(lightness: f32, a: f32, b: f32) -> (f32, f32, f32) {
    let l = (lightness + 0.396_337_78 * a + 0.215_803_76 * b).powi(3);
    let m = (lightness - 0.105_561_346 * a - 0.063_854_17 * b).powi(3);
    let s = (lightness - 0.089_484_18 * a - 1.291_485_5 * b).powi(3);
    (
        4.076_741_7 * l - 3.307_711_6 * m + 0.230_969_94 * s,
        -1.268_438 * l + 2.609_757_4 * m - 0.341_319_38 * s,
        -0.004_196_086_4 * l - 0.703_418_6 * m + 1.707_614_7 * s,
    )
}

/// Oklab -> sRGB with the official chroma clipping of `FUN_1400528e3`: when the
/// linear RGB leaves [0, 1], the a/b channels are scaled down by a 20-step binary
/// search and the lightness is preserved.
fn oklab_to_srgb(lightness: f32, a: f32, b: f32) -> (f32, f32, f32) {
    let in_gamut = |rgb: (f32, f32, f32)| {
        [rgb.0, rgb.1, rgb.2].iter().all(|c| (-1e-6..=1.000_001).contains(c))
    };
    let mut rgb = oklab_to_linear(lightness, a, b);
    if !in_gamut(rgb) {
        let mut lo = 0.0f32;
        let mut hi = 1.0f32;
        for _ in 0..20 {
            let mid = (lo + hi) * 0.5;
            if in_gamut(oklab_to_linear(lightness, a * mid, b * mid)) {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        rgb = oklab_to_linear(lightness, a * lo, b * lo);
    }
    (
        linear_to_srgb_official(rgb.0),
        linear_to_srgb_official(rgb.1),
        linear_to_srgb_official(rgb.2),
    )
}

/// Official darken step (`FUN_14005202a:66998-67031`): move 0.3 down the Oklab
/// **lightness** axis, then binary-search the lightest tone inside that 0.3 window
/// that still clears 4.8 against white. The step is subtractive on lightness, not
/// a multiplicative RGB factor. If even the full -0.3 does not clear 4.8, the
/// official keeps the undarkened accent (the `pfVar4` fallback).
fn darken_accent_subtractive(accent: (f32, f32, f32)) -> (f32, f32, f32) {
    let white = (1.0, 1.0, 1.0);
    let (lightness, a, b) = srgb_to_oklab(accent.0, accent.1, accent.2);
    let lo0 = (lightness - 0.3).max(0.0);
    if contrast_ratio(oklab_to_srgb(lo0, a, b), white) < 4.8 {
        return accent;
    }
    let mut lo = lo0;
    let mut hi = lightness;
    for _ in 0..20 {
        let mid = (lo + hi) * 0.5;
        if contrast_ratio(oklab_to_srgb(mid, a, b), white) >= 4.8 {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    oklab_to_srgb(lo, a, b)
}

/// Official `src/overlay/color.rs` (Ghidra `FUN_14005202a`, panic xref lines
/// 24/25/26): pick a legible ink colour for accent-coloured surfaces.
///
/// 1. black wins when its contrast against the accent is >= 4.5
/// 2. otherwise white wins when its contrast is >= 4.8
/// 3. otherwise the accent is darkened by 0.3 on the Oklab lightness axis and a
///    20-step binary search inside that window clears 4.8 against white
fn pick_ink_color(accent: (f32, f32, f32, f32)) -> (f32, f32, f32, f32) {
    let bg = (accent.0, accent.1, accent.2);
    let black = (0.05, 0.05, 0.05);
    if contrast_ratio(black, bg) >= 4.5 {
        return (black.0, black.1, black.2, 1.0);
    }
    let white = (1.0, 1.0, 1.0);
    if contrast_ratio(white, bg) >= 4.8 {
        return (1.0, 1.0, 1.0, 1.0);
    }
    // Neither candidate is legible: the official darkens the accent by moving 0.3
    // down the Oklab lightness axis and binary-searching the lightest tone in that
    // window that still clears 4.8 against white (FUN_14005202a:66998-67031).
    let (r, g, b) = darken_accent_subtractive(bg);
    (r, g, b, 1.0)
}

/// Official shadow derivation for the pill (Ghidra `FUN_14005202a` tail):
/// `r' = (1 - r) * 0.644 + r`, `g' = g * 0.51`, `b' = b * 0.51`.
/// The red channel is lifted rather than scaled, which is what produces the
/// characteristic warm grey drop shadow under the accent pill.
pub fn shadow_color(accent: (f32, f32, f32, f32)) -> (f32, f32, f32, f32) {
    (
        (1.0 - accent.0) * 0.644 + accent.0,
        accent.1 * 0.51,
        accent.2 * 0.51,
        1.0,
    )
}

fn estimate_text_width(text: &str, font_size: f32) -> f32 {
    (text.len() as f32 * font_size * 0.54).max(8.0)
}

fn compute_pill_layout(
    desktop_w: f32,
    _desktop_h: f32,
    status: &str,
    cancel: &str,
    dpi: f32,
    status_width: Option<f32>,
    cancel_width: Option<f32>,
    rtl: bool,
) -> PillLayout {
    let scale = dpi.max(0.5);
    // Official pill stack (`140057dbb:404-494`): root = content + `18*s` on every
    // side, content (the accent body) is `48*s` tall, the text sits `16*s` inside the
    // content, and the separator block is `12*s + 4*s + 12*s` wide (VIS-13).
    let pad = PILL_PAD * scale;
    let content_pad = PILL_CONTENT_PAD * scale;
    let body_h = PILL_CONTENT_HEIGHT * scale;
    let height = body_h + 2.0 * pad;
    // Official text runs are capped at 920*s and 360*s (VIS-15).
    let status_w = status_width
        .unwrap_or_else(|| estimate_text_width(status, 16.0 * scale))
        .min(920.0 * scale);
    let cancel_w = cancel_width
        .unwrap_or_else(|| estimate_text_width(cancel, 16.0 * scale))
        .min(360.0 * scale);
    let mut body_w = 2.0 * content_pad + status_w + PILL_SEPARATOR * scale + cancel_w;
    body_w = body_w.min(((desktop_w * 0.92) - 2.0 * pad).max(120.0));
    let width = body_w + 2.0 * pad;
    let x = ((desktop_w - width) / 2.0).max(0.0);
    let y = PILL_ROOT_MARGIN_Y * scale;
    let body_x = x + pad;
    let body_y = y + pad;
    // Official layout has an RTL branch (`140057dbb:432-441`): in a right-to-left
    // locale the status run is laid out first, so the segments swap sides (VIS-22).
    // The divider is the middle of the fixed `28 * s` separator block, which is what
    // makes the two runs `12 * s` apart on either side of the `4 * s` dot.
    let half_separator = PILL_SEPARATOR * scale * 0.5;
    let (status_x, separator_x, cancel_x) = if rtl {
        let status_x = body_x + body_w - content_pad - status_w;
        (status_x, status_x - half_separator, status_x - PILL_SEPARATOR * scale - cancel_w)
    } else {
        let status_x = body_x + content_pad;
        (
            status_x,
            status_x + status_w + half_separator,
            status_x + status_w + PILL_SEPARATOR * scale,
        )
    };
    PillLayout {
        x,
        y,
        width,
        height,
        body_x,
        body_y,
        body_w,
        body_h,
        radius: body_h / 2.0,
        status_x,
        cancel_x,
        status_width: status_w,
        cancel_width: cancel_w,
        separator_x,
    }
}

fn is_rtl_locale() -> bool {
    let lang = unsafe { GetUserDefaultUILanguage() } as u32;
    let primary = lang & 0x3FF;
    matches!(primary, 0x01 | 0x0D | 0x20 | 0x29 | 0x5C)
}

/// Official fallback when the localisable `accentColor` string cannot be parsed.
pub const ACCENT_FALLBACK: (f32, f32, f32, f32) = (1.0 / 255.0, 105.0 / 255.0, 204.0 / 255.0, 1.0);

fn accent_color() -> (f32, f32, f32, f32) {
    parse_hex_color(ACCENT_HEX).unwrap_or(ACCENT_FALLBACK)
}

fn ui_color(r: f32, g: f32, b: f32, a: f32) -> Color {
    Color {
        A: (a * 255.0).round().clamp(0.0, 255.0) as u8,
        R: (r * 255.0).round().clamp(0.0, 255.0) as u8,
        G: (g * 255.0).round().clamp(0.0, 255.0) as u8,
        B: (b * 255.0).round().clamp(0.0, 255.0) as u8,
    }
}

fn d2d_color(r: f32, g: f32, b: f32, a: f32) -> D2D1_COLOR_F {
    D2D1_COLOR_F { r, g, b, a }
}

fn is_device_lost(err: &windows::core::Error) -> bool {
    let hr = err.code().0 as u32;
    hr == DXGI_ERROR_DEVICE_REMOVED.0 as u32
        || hr == DXGI_ERROR_DEVICE_RESET.0 as u32
        || hr == DXGI_ERROR_INVALID_CALL_AFTER_LOSS
        || hr == D2DERR_RECREATE_TARGET
        || hr == RO_E_CLOSED
}

/// Official cursor glyph: 13 normalised points (26 floats) taken from the helper
/// .rdata, y pointing down, spanning x in [-0.024, 0.983] and y in [-0.025, 1.029].
pub const CURSOR_GLYPH_POINTS: [(f32, f32); 13] = [
    (0.005_99, 0.158_64),
    (-0.023_64, 0.064_56),
    (0.061_69, -0.024_74),
    (0.151_58, 0.006_27),
    (0.876_34, 0.256_52),
    (0.975_94, 0.290_96),
    (0.983_40, 0.435_47),
    (0.887_94, 0.480_95),
    (0.593_43, 0.621_08),
    (0.459_55, 0.929_25),
    (0.416_11, 1.029_25),
    (0.278_01, 1.021_46),
    (0.245_10, 0.917_17),
];

/// Official DPI scaling: the sprite is a `round(dpi * 1.3125)` square (126 px at
/// 96 DPI) and the glyph is drawn at `round(dpi / 96 * 58.5)` px. The hotspot is
/// the same `58.5 * dpi/96` value, so the window is placed at
/// `target - hotspot` to land the glyph tip exactly on the point.
///
/// `scale` is the DSH-only multiplier (1.0 = the official size). Applying it to both the
/// sprite and the hotspot keeps the glyph tip exactly on the requested point.
pub fn cursor_metrics_scaled(dpi: u32, scale: f32) -> (i32, f32) {
    let dpi = dpi.max(96) as f32;
    let scale = if scale.is_finite() { scale.clamp(0.3, 2.0) } else { 1.0 };
    let sprite = (dpi * 1.312_5 * scale).round() as i32;
    let glyph = (dpi / 96.0 * 58.5 * scale).round();
    (sprite.max(16), glyph.max(8.0))
}

/// Live geometry: the official formula times the process-wide sprite scale.
pub fn cursor_metrics(dpi: u32) -> (i32, f32) {
    cursor_metrics_scaled(dpi, cursor_scale())
}

/// Set the process-wide sprite scale (1.0 = official). Out-of-range values are clamped.
pub fn set_cursor_scale(scale: f32) {
    let clamped = if scale.is_finite() { scale.clamp(0.3, 2.0) } else { 1.0 };
    CURSOR_SCALE_BITS.store(clamped.to_bits(), Ordering::SeqCst);
}

/// The process-wide sprite scale.
pub fn cursor_scale() -> f32 {
    f32::from_bits(CURSOR_SCALE_BITS.load(Ordering::SeqCst))
}

/// Glyph outline in sprite-local pixels, offset so the glyph tip sits at the
/// hotspot. `scale` is the animated `Scale` factor (VIS-04): the official presses
/// to 0.7 over 550 ms rather than swapping in a 0.86-sized sprite.
fn arrow_points(glyph: f32, scale: f32) -> Vec<(f32, f32)> {
    let size = glyph * scale;
    // The glyph is normalised over roughly one unit; treat the hotspot as the
    // glyph-box origin so the tip lands on the target coordinate.
    CURSOR_GLYPH_POINTS
        .iter()
        .map(|(x, y)| (x * size, y * size))
        .collect()
}

fn publish_hwnds(slot: &std::sync::Arc<Mutex<Vec<isize>>>, banner: HWND, cursor: HWND) {
    publish_hwnds4(slot, banner, cursor, HWND::default(), HWND::default());
}

fn publish_hwnds4(
    slot: &std::sync::Arc<Mutex<Vec<isize>>>,
    banner: HWND,
    cursor: HWND,
    edge_l: HWND,
    edge_r: HWND,
) {
    if let Ok(mut guard) = slot.lock() {
        *guard = [banner.0 as isize, cursor.0 as isize, edge_l.0 as isize, edge_r.0 as isize]
            .into_iter()
            .filter(|id| *id != 0)
            .collect();
    }
}

fn ui_loop(rx: mpsc::Receiver<Cmd>, hwnd_slot: std::sync::Arc<Mutex<Vec<isize>>>) {
    unsafe {
        THREAD_ID.store(GetCurrentThreadId(), Ordering::SeqCst);
        // Official overlay thread saves and restores the thread DPI awareness
        // context around its message pump (`all_functions.c:60533-60535`, VIS-06),
        // so a host with a different process-level mode still gets the per-monitor
        // geometry the sprite metrics assume.
        let previous_dpi_context = SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        let _ = windows::Win32::System::WinRT::RoInitialize(
            windows::Win32::System::WinRT::RO_INIT_SINGLETHREADED,
        );
        let _ = windows::Win32::System::Com::CoInitializeEx(
            None,
            windows::Win32::System::Com::COINIT_APARTMENTTHREADED,
        );
        reclaim_stale_overlay();
        claim_overlay_mutex();
        register_class();
        let hwnd = create_banner().unwrap_or_default();
        let cursor = create_cursor_window().unwrap_or_default();
        publish_hwnds4(&hwnd_slot, hwnd, cursor, HWND::default(), HWND::default());
        let hook: HWINEVENTHOOK = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            Some(on_foreground),
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        );
        let mut pt = POINT::default();
        let _ = GetCursorPos(&mut pt);
        if SetCursorPos(pt.x, pt.y).is_err() {
            eprintln!("{SETCURSORPOS_INITIAL}");
        }
        let mut ui = Ui {
            hwnd,
            cursor,
            edge_left: HWND::default(),
            edge_right: HWND::default(),
            visible: false,
            snapped: false,
            device_lost: false,
            hidden_since_show: false,
            last_recreate: Instant::now() - Duration::from_secs(1),
            display: if hwnd.0.is_null() || !dcomp_overlay_enabled() {
                None
            } else {
                attach_display(hwnd)
            },
            cursor_stage: None,
            cursor_x: pt.x as f32,
            cursor_y: pt.y as f32,
            cursor_seeded: false,
            cursor_motion: None,
            cursor_press_until: None,
            press_anim: None,
            press_scale_last: 1.0,
            cursor_dpi: GetDpiForSystem().max(96),
            fade_deadline: None,
            last_place: None,
            cursor_tick: 0,
            next_suppress: Instant::now(),
        };
        DISPLAY_COMPOSITION.store(ui.display.is_some(), Ordering::SeqCst);
        CURSOR_STAGE.store(ui.cursor_stage.is_some(), Ordering::SeqCst);
        READY.store(true, Ordering::SeqCst);
        loop {
            PUMP_ITERS.fetch_add(1, Ordering::Relaxed);
            let iter_start = Instant::now();
            let cmd_start = Instant::now();
            while let Ok(cmd) = rx.try_recv() {
                match cmd {
                    Cmd::Show { reply } => {
                        note_cmd("Show");
                        if FORCE_HIDDEN.load(Ordering::SeqCst) {
                            apply_hide(&mut ui);
                        } else {
                            if ui.hidden_since_show {
                                // Never re-show the window a hide blanked (see
                                // `hidden_since_show`): rebuild it first, then show.
                                rebuild_overlay(&mut ui, &hwnd_slot);
                                ui.hidden_since_show = false;
                            }
                            apply_show(&mut ui);
                        }
                        send_reply(reply, Ok(()));
                    }
                    Cmd::Hide { reply } => {
                        note_cmd("Hide");
                        apply_hide(&mut ui);
                        send_reply(reply, Ok(()));
                    }
                    Cmd::Raise => {
                        note_cmd("Raise");
                        if !FORCE_HIDDEN.load(Ordering::SeqCst) && ui.visible {
                            raise_overlay(&ui);
                        }
                    }
                    Cmd::Recreate => {
                        note_cmd("Recreate");
                        recreate(&mut ui, &hwnd_slot);
                    }
                    Cmd::CaptureMask { on, reply } => {
                        note_cmd("CaptureMask");
                        let result = set_capture_mask(&mut ui, on);
                        if on {
                            // The mask only helps if the compositor has committed the
                            // transparent frame: the capture reads the composed desktop,
                            // not our visual tree.
                            let _ = DwmFlush();
                        }
                        send_reply(reply, result);
                    }
                    Cmd::Cursor { x, y, press, reply } => {
                        note_cmd("Cursor");
                        let result = if FORCE_HIDDEN.load(Ordering::SeqCst) {
                            apply_hide(&mut ui);
                            Ok(())
                        } else {
                            play_cursor(&mut ui, x, y, press)
                        };
                        send_reply(reply, result);
                    }
                    Cmd::Quit { reply } => {
                        note_cmd("Quit");
                        stop_cursor_motion(&mut ui);
                        ui.display = None;
                        ui.cursor_stage = None;
                        DISPLAY_COMPOSITION.store(false, Ordering::SeqCst);
                        CURSOR_STAGE.store(false, Ordering::SeqCst);
                        if !ui.hwnd.0.is_null() {
                            let _ = DestroyWindow(ui.hwnd);
                        }
                        if !ui.cursor.0.is_null() {
                            let _ = DestroyWindow(ui.cursor);
                        }
                        let _ = UnhookWinEvent(hook);
                        send_reply(reply, Ok(()));
                        READY.store(false, Ordering::SeqCst);
                        THREAD_ID.store(0, Ordering::SeqCst);
                        // Restore the DPI context the host thread had on entry.
                        SetThreadDpiAwarenessContext(previous_dpi_context);
                        return;
                    }
                }
            }
            // Drain the queue before animating. Stepping the motion only in the
            // else-branch let a message storm starve the animation, which is how the
            // cosmetic cursor ended up crawling at roughly one frame per second
            // instead of arriving in ~0.3 s.
            let cmd_ms = cmd_start.elapsed().as_millis() as u64;
            CMD_LAST_MS.store(cmd_ms, Ordering::Relaxed);
            CMD_MAX_MS.fetch_max(cmd_ms, Ordering::Relaxed);
            let drain_start = Instant::now();
            let mut msg = MSG::default();
            let mut drained = 0u32;
            while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                PUMP_MSGS.fetch_add(1, Ordering::Relaxed);
                note_msg(msg.message);
                if msg.message == WM_PAINT && msg.hwnd == ui.hwnd && ui.display.is_some() {
                    let mut ps = PAINTSTRUCT::default();
                    let _ = BeginPaint(ui.hwnd, &mut ps);
                    let _ = EndPaint(ui.hwnd, &ps);
                } else if msg.message != WM_NULL {
                    let _ = TranslateMessage(&msg);
                    DispatchMessageW(&msg);
                }
                drained += 1;
                if drained >= MAX_MESSAGES_PER_ITERATION {
                    break;
                }
            }
            let drain_ms = drain_start.elapsed().as_millis() as u64;
            DRAIN_LAST_MS.store(drain_ms, Ordering::Relaxed);
            DRAIN_MAX_MS.fetch_max(drain_ms, Ordering::Relaxed);
            // Watchdog: a mask that is never lifted would hide the pill from the
            // operator for good, which is the very symptom this mechanism exists to
            // avoid. The pump therefore lifts an expired mask itself.
            if CAPTURE_MASKED.load(Ordering::SeqCst) {
                let expired = CAPTURE_MASK_DEADLINE
                    .lock()
                    .ok()
                    .and_then(|slot| *slot)
                    .map(|deadline| Instant::now() >= deadline)
                    .unwrap_or(false);
                if expired {
                    let _ = set_capture_mask(&mut ui, false);
                }
            }
            let branch_start = Instant::now();
            // The exit animation has to finish before the windows go away; the
            // official waits on the composition batch (`start display overlay exit
            // animation`), the ULW fallback waits on the fade deadline (VIS-20).
            if let Some(deadline) = ui.fade_deadline {
                if Instant::now() >= deadline {
                    ui.fade_deadline = None;
                    finish_hide(&mut ui);
                } else {
                    let _ = pill_fade_step(&ui);
                    let _ = MsgWaitForMultipleObjects(None, false, 5, QS_ALLINPUT);
                }
            }
            if DEVICE_LOST.swap(false, Ordering::SeqCst) {
                ui.device_lost = true;
            }
            if ui.device_lost {
                ui.device_lost = false;
                recreate(&mut ui, &hwnd_slot);
            } else if ui.cursor_motion.is_some()
                || ui.cursor_press_until.is_some()
                || ui.press_anim.is_some()
            {
                // Each frame is `T / (n - 1)` apart: the official spreads its
                // sampled keyframes across the computed duration (VIS-08).
                PUMP_ANIM.fetch_add(1, Ordering::Relaxed);
                let frame_wait = ui
                    .cursor_motion
                    .as_ref()
                    .map(|motion| motion.frame_ms as u32)
                    .unwrap_or(CURSOR_FRAME_MS as u32)
                    .max(1);
                let _ = step_cursor_motion(&mut ui);
                let _ = step_press(&mut ui);
                let _ = MsgWaitForMultipleObjects(None, false, frame_wait, QS_ALLINPUT);
            } else if pill_pulse_step(&ui) {
                // Official 3 s border pulse, redrawn at its own cadence.
                PUMP_PILL.fetch_add(1, Ordering::Relaxed);
                let _ = MsgWaitForMultipleObjects(None, false, PILL_FRAME_MS, QS_ALLINPUT);
            } else {
                // Official `schedule system cursor re-suppression`: another process can
                // restore the system cursors while the overlay is up, which puts the real
                // pointer back next to the fake one. Re-assert it on a slow timer, and
                // restart a manager that died in the meantime.
                if ui.visible
                    && !FORCE_HIDDEN.load(Ordering::SeqCst)
                    && Instant::now() >= ui.next_suppress
                {
                    SUPPRESS_REASSERTS.fetch_add(1, Ordering::SeqCst);
                    let ok = ensure_system_cursor_suppressed();
                    SUPPRESSED.store(ok, Ordering::SeqCst);
                    if !ok {
                        SUPPRESS_FAILURES.fetch_add(1, Ordering::SeqCst);
                    }
                    ui.next_suppress = Instant::now() + SUPPRESS_EVERY;
                }
                let _ = MsgWaitForMultipleObjects(None, false, 10, QS_ALLINPUT);
            }
            let branch_ms = branch_start.elapsed().as_millis() as u64;
            BRANCH_LAST_MS.store(branch_ms, Ordering::Relaxed);
            BRANCH_MAX_MS.fetch_max(branch_ms, Ordering::Relaxed);
            let elapsed = iter_start.elapsed().as_millis() as u64;
            if elapsed > 5_000 {
                eprintln!("overlay pump iteration took {elapsed} ms (drained={drained})");
            }
        }
    }
}

fn register_class() {
    unsafe {
        let module = GetModuleHandleW(None).unwrap_or_default();
        let class = WNDCLASSW {
            lpfnWndProc: Some(wndproc),
            hInstance: windows::Win32::Foundation::HINSTANCE(module.0),
            hbrBackground: HBRUSH::default(),
            lpszClassName: w!("DshComputerUseCursorOverlay"),
            ..Default::default()
        };
        let _ = RegisterClassW(&class);
        let cursor = WNDCLASSW {
            lpfnWndProc: Some(cursor_wndproc),
            hInstance: windows::Win32::Foundation::HINSTANCE(module.0),
            hbrBackground: HBRUSH::default(),
            lpszClassName: w!("DshComputerUseCursorOverlayPointer"),
            ..Default::default()
        };
        let _ = RegisterClassW(&cursor);
        // Official registers exactly ONE class (`CodexComputerUseCursorOverlay`)
        // and creates both overlay windows from it (VIS-12). `EDGE_CLASS` is no
        // longer registered here; it survives only in the reclaim predicates so a
        // leftover window from an older build is still cleaned up.
    }
}

fn virtual_desktop() -> (i32, i32, i32, i32) {
    unsafe {
        (
            GetSystemMetrics(SM_XVIRTUALSCREEN),
            GetSystemMetrics(SM_YVIRTUALSCREEN),
            GetSystemMetrics(SM_CXVIRTUALSCREEN).max(GetSystemMetrics(
                windows::Win32::UI::WindowsAndMessaging::SM_CXSCREEN,
            )),
            GetSystemMetrics(SM_CYVIRTUALSCREEN).max(GetSystemMetrics(
                windows::Win32::UI::WindowsAndMessaging::SM_CYSCREEN,
            )),
        )
    }
}

#[allow(dead_code)]
fn bar_height_for(hwnd: HWND) -> i32 {
    let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96);
    ((BAR_HEIGHT as f64) * dpi as f64 / 96.0).round() as i32
}

fn dpi_scale(hwnd: HWND) -> f32 {
    unsafe { GetDpiForWindow(hwnd) }.max(96) as f32 / 96.0
}

/// System DPI scale, for the overlay paths that have no HWND at hand.
fn dpi_scale_global() -> f32 {
    unsafe { GetDpiForSystem() }.max(96) as f32 / 96.0
}

/// Official DPI source (VIS-05, `FUN_14004fd49:19-48`): the DPI of the **monitor
/// under the target point**, not the system DPI. On a mixed-DPI desktop the system
/// DPI puts the sprite at the wrong size and offsets the hotspot by
/// `58.5 * (d_sys - d_mon) / 96` px. Falls back to `GetDpiForSystem`, floor 96.
fn dpi_for_point(x: f32, y: f32) -> u32 {
    let point = POINT {
        x: x.round() as i32,
        y: y.round() as i32,
    };
    let monitor = unsafe { MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST) };
    if !monitor.0.is_null() {
        let mut dpi_x = 0u32;
        let mut dpi_y = 0u32;
        if unsafe { GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y) }.is_ok()
            && dpi_x > 0
        {
            return dpi_x.max(96);
        }
    }
    unsafe { GetDpiForSystem() }.max(96)
}

/// `Scale` of an in-flight press transition at `now`. The official animation has a
/// single keyframe at progress 1.0 and no easing function, so the compositor
/// interpolates linearly from the value the visual already had.
fn press_scale_at(anim: &PressAnim, now: Instant) -> (f32, bool) {
    let elapsed = now.duration_since(anim.start).as_millis() as f32;
    let t = (elapsed / CURSOR_PRESS_MS as f32).clamp(0.0, 1.0);
    (anim.from + (anim.to - anim.from) * t, t >= 1.0)
}

/// Official sky `CreateWindowExW(0x80800A8)`: TOPMOST|TRANSPARENT|TOOLWINDOW|LAYERED|NOACTIVATE.
/// DirectComposition overlay style.
///
/// `WS_EX_NOREDIRECTIONBITMAP` is required here: the pill exists only as a composited
/// visual tree, and without it the window keeps a redirection surface that it never
/// paints, which shows up as an opaque black full-desktop rectangle.
///
/// It is deliberately NOT `WS_EX_LAYERED` with `SetLayeredWindowAttributes`: that
/// switches the window to the layered presentation path, and the DirectComposition
/// content is then never composited at all. That is why the status pill was invisible
/// on screen even though every overlay API reported `visible=true`.
fn overlay_ex_style() -> windows::Win32::UI::WindowsAndMessaging::WINDOW_EX_STYLE {
    WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT
}

fn apply_overlay_layered(hwnd: HWND, alpha: u8) -> windows::core::Result<()> {
    unsafe { SetLayeredWindowAttributes(hwnd, COLORREF(0), alpha, LWA_COLORKEY | LWA_ALPHA) }
}

fn create_banner() -> windows::core::Result<HWND> {
    unsafe {
        let (vx, vy, vw, vh) = virtual_desktop();
        let module = GetModuleHandleW(None)?;
        // Bind the wide title so it outlives the call (CreateWindowExW copies it).
        let title = wide(BANNER_WINDOW_TITLE);
        let hwnd = CreateWindowExW(
            overlay_ex_style(),
            w!("DshComputerUseCursorOverlay"),
            windows::core::PCWSTR(title.as_ptr()),
            WS_POPUP,
            vx,
            vy,
            vw,
            vh,
            None,
            None,
            Some(windows::Win32::Foundation::HINSTANCE(module.0)),
            None,
        )?;
        // No SetLayeredWindowAttributes: see overlay_ex_style().
        // Official overlay/mod.rs: only the DISPLAY overlay is excluded from capture
        // (context string "exclude display overlay from capture"). The status pill is
        // for the human, so it must not appear in the model's own screenshots.
        // DSH_CU_OVERLAY_CAPTURABLE=1 keeps it capturable for diagnostics: the
        // affinity cannot be lifted from another process, so only the helper can.
        // The default is NOT to touch the affinity at all: see CaptureExclusion.
        if capture_exclusion() == CaptureExclusion::Wda {
            let _ = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
        }
        // Official `set overlay accessible window name` (literal
        // `codex-computer-use-status-pill`); DSH keeps its own string. Windows
        // falls back to the window text for the UIA name when no provider
        // overrides it, so this is both the title and the accessible name (VIS-21).
        let accessible = wide(ACCESSIBLE_NAME);
        let _ = SetWindowTextW(hwnd, windows::core::PCWSTR(accessible.as_ptr()));
        Ok(hwnd)
    }
}

fn create_cursor_window() -> windows::core::Result<HWND> {
    unsafe {
        let module = GetModuleHandleW(None)?;
        let title = wide(CURSOR_WINDOW_TITLE);
        // Official geometry: a round(dpi * 1.3125) square sprite (126 px at 96 DPI).
        let (sprite, _) = cursor_metrics(GetDpiForSystem());
        let hwnd = CreateWindowExW(
            WS_EX_TOPMOST
                | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE
                | WS_EX_LAYERED
                | WS_EX_TRANSPARENT,
            w!("DshComputerUseCursorOverlayPointer"),
            windows::core::PCWSTR(title.as_ptr()),
            WS_POPUP,
            0,
            0,
            sprite,
            sprite,
            None,
            None,
            Some(windows::Win32::Foundation::HINSTANCE(module.0)),
            None,
        )?;
        // No SetLayeredWindowAttributes here on purpose: the cursor sprite is pushed
        // with UpdateLayeredWindow so it gets real per-pixel alpha (the official
        // DirectComposition look). A colour key can only fake transparency, which
        // rendered the accent glow as an opaque dark disc.
        if !CURSOR_LAYERED.load(Ordering::SeqCst) {
            let _ = apply_overlay_layered(hwnd, 255);
        }
        // IMPORTANT: the cursor overlay is deliberately NOT excluded from capture.
        // The fake cursor is the model's own pointer: the model must be able to see
        // where it is pointing in the screenshots it reads. Official behavior
        // (Ghidra 14004791d:292) applies WDA_EXCLUDEFROMCAPTURE to the display
        // overlay only.
        Ok(hwnd)
    }
}

fn apply_show(ui: &mut Ui) {
    ui.visible = true;
    WORKER_VISIBLE.store(true, Ordering::Relaxed);
    // show() already suppressed the pointer; only schedule the next re-assertion.
    ui.next_suppress = Instant::now() + SUPPRESS_EVERY;
    let (vx, vy, vw, vh) = virtual_desktop();
    unsafe {
        // SWP_NOACTIVATE everywhere: an overlay that activates itself makes this
        // process the foreground owner, which re-raises EVENT_SYSTEM_FOREGROUND and
        // feeds the pump an endless Raise storm (and invalidates observations).
        if ui.display.is_some() {
            let _ = SetWindowPos(
                ui.hwnd,
                Some(HWND_TOPMOST),
                vx,
                vy,
                vw,
                vh,
                SWP_SHOWWINDOW | SWP_NOACTIVATE,
            );
        }
        let _ = ShowWindow(ui.hwnd, SW_SHOWNOACTIVATE);
        if !ui.edge_left.0.is_null() {
            let _ = ShowWindow(ui.edge_left, SW_HIDE);
        }
        if !ui.edge_right.0.is_null() {
            let _ = ShowWindow(ui.edge_right, SW_HIDE);
        }
        // The pill owns its own position and size through UpdateLayeredWindow, so the
        // window is only raised and shown here.
        if ui.display.is_none() {
            let _ = SetWindowPos(
                ui.hwnd,
                Some(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE,
            );
        }
        let _ = InvalidateRect(Some(ui.hwnd), None, true);
        // The model must not see the pill in its own screenshots. The default keeps the
        // pill on screen and hides it only for the duration of a capture (see
        // mask_for_capture / CaptureExclusion::Mask); the affinity is opt-in because it
        // blanks the DirectComposition content on screen on some machines.
        if capture_exclusion() == CaptureExclusion::Wda {
            let _ = SetWindowDisplayAffinity(ui.hwnd, WDA_EXCLUDEFROMCAPTURE);
        }
        if !ui.cursor.0.is_null() {
            if ui.cursor_stage.is_some() {
                let _ = SetWindowPos(
                    ui.cursor,
                    Some(HWND_TOPMOST),
                    vx,
                    vy,
                    vw,
                    vh,
                    SWP_SHOWWINDOW | SWP_NOACTIVATE,
                );
            }
            let _ = ShowWindow(ui.cursor, SW_SHOWNOACTIVATE);
            // No capture exclusion here on purpose — see create_cursor_window().
        }
        let mut pt = POINT::default();
        if GetCursorPos(&mut pt).is_ok() {
            if SetCursorPos(pt.x, pt.y).is_err() {
                eprintln!("{SETCURSORPOS_INITIAL}");
            }
            // Seed the sprite from the real cursor only before the model has ever
            // moved it. Re-seeding on every show() teleports the fake cursor to
            // wherever the human parked their mouse, so a post-action screenshot
            // no longer shows where the model pointed (FIX-1 regression).
            if !ui.cursor_seeded {
                ui.cursor_x = pt.x as f32;
                ui.cursor_y = pt.y as f32;
            }
        }
        let _ = place_cursor(ui, ui.cursor_x, ui.cursor_y, ui.press_scale_last);
    }
    use_pill_renderer(ui);
    if let Some(display) = ui.display.as_ref() {
        // Set the base opacity as well: the pill must be visible even if the fade
        // animation never runs, and the visual tree starts at opacity 0.
        let _ = display.root.SetOpacity(1.0);
        let _ = fade_visual(&display.compositor, &display.root, 1.0, FADE_MS);
        display.set_edge_activity(false);
    }
}

fn apply_hide(ui: &mut Ui) {
    ui.visible = false;
    ui.hidden_since_show = true;
    // The pill is leaving the screen anyway: drop any capture mask so the watchdog
    // deadline cannot fire against a later, unrelated show().
    CAPTURE_MASKED.store(false, Ordering::SeqCst);
    if let Ok(mut slot) = CAPTURE_MASK_DEADLINE.lock() {
        *slot = None;
    }
    WORKER_VISIBLE.store(false, Ordering::Relaxed);
    ui.snapped = false;
    stop_cursor_motion(ui);
    stop_pill_pulse();
    // Official exit: a 500 ms opacity animation to 0 with
    // `cubic-bezier(0.22, 1.0, 0.36, 1.0)`, and the windows go away once it has
    // flushed (VIS-20).
    start_pill_fade(0.0);
    if let Some(display) = ui.display.as_ref() {
        let _ = fade_visual(&display.compositor, &display.root, 0.0, FADE_MS);
    }
    if ui.hwnd.0.is_null() {
        finish_hide(ui);
        return;
    }
    if ui.display.is_none() {
        // Start the layered fade immediately so the transition is real even when
        // the composition path is unavailable.
        let _ = paint_pill(ui.hwnd, 1.0);
    }
    ui.fade_deadline = Some(Instant::now() + Duration::from_millis(FADE_MS as u64));
}

/// Hide (`on`) or restore the pill's own pixels without touching the window. The pill is
/// a DirectComposition visual tree, so its root opacity can be dropped for the duration of
/// one capture; the ULW fallback pushes a fully transparent frame instead. Neither path
/// touches the cursor window: the model's own pointer must stay in its screenshots.
fn set_capture_mask(ui: &mut Ui, on: bool) -> Result<(), String> {
    if on {
        CAPTURE_MASKED.store(true, Ordering::SeqCst);
        CAPTURE_MASK_COUNT.fetch_add(1, Ordering::SeqCst);
        if let Ok(mut slot) = CAPTURE_MASK_DEADLINE.lock() {
            *slot = Some(Instant::now() + Duration::from_millis(CAPTURE_MASK_MAX_MS));
        }
    } else {
        CAPTURE_MASKED.store(false, Ordering::SeqCst);
        if let Ok(mut slot) = CAPTURE_MASK_DEADLINE.lock() {
            *slot = None;
        }
    }
    let alpha = if on || !ui.visible { 0.0 } else { 1.0 };
    match ui.display.as_ref() {
        Some(display) => {
            // A running fade animation owns `Opacity`; dropping the animation first is
            // what makes the value stick for the frame that is about to be captured.
            let _ = display.root.StopAnimation(&HSTRING::from("Opacity"));
            let _ = display.root.SetOpacity(alpha);
        }
        None => {
            if !ui.hwnd.0.is_null() {
                let _ = paint_pill(ui.hwnd, alpha);
            }
        }
    }
    Ok(())
}

/// Drop the overlay windows once the exit animation has flushed.
fn finish_hide(ui: &mut Ui) {
    ui.fade_deadline = None;
    clear_pill_fade();
    unsafe {
        let _ = ShowWindow(ui.hwnd, SW_HIDE);
        let _ = SetWindowPos(
            ui.hwnd,
            Some(HWND_TOPMOST),
            0,
            0,
            0,
            0,
            SWP_HIDEWINDOW | SWP_NOSIZE | SWP_NOMOVE,
        );
        if !ui.cursor.0.is_null() {
            let _ = ShowWindow(ui.cursor, SW_HIDE);
        }
        if !ui.edge_left.0.is_null() {
            let _ = ShowWindow(ui.edge_left, SW_HIDE);
        }
        if !ui.edge_right.0.is_null() {
            let _ = ShowWindow(ui.edge_right, SW_HIDE);
        }
    }
    ui.last_place = None;
}

fn recreate(ui: &mut Ui, hwnd_slot: &std::sync::Arc<Mutex<Vec<isize>>>) {
    let now = Instant::now();
    if now.duration_since(ui.last_recreate) < Duration::from_millis(450) {
        return;
    }
    ui.last_recreate = now;
    rebuild_overlay(ui, hwnd_slot);
}

/// Destroy and rebuild the overlay windows, re-attaching the composition display.
/// Split out of `recreate` so the show-after-hide path can force it: that window can
/// never render again, so the 450 ms device-lost throttle must not apply to it.
fn rebuild_overlay(ui: &mut Ui, hwnd_slot: &std::sync::Arc<Mutex<Vec<isize>>>) {
    RECREATES.fetch_add(1, Ordering::Relaxed);
    stop_cursor_motion(ui);
    ui.display = None;
    ui.cursor_stage = None;
    DISPLAY_COMPOSITION.store(false, Ordering::SeqCst);
    CURSOR_STAGE.store(false, Ordering::SeqCst);
    ui.device_lost = false;
    unsafe {
        if !ui.hwnd.0.is_null() {
            let _ = DestroyWindow(ui.hwnd);
        }
        if !ui.cursor.0.is_null() {
            let _ = DestroyWindow(ui.cursor);
        }
        if !ui.edge_left.0.is_null() {
            let _ = DestroyWindow(ui.edge_left);
        }
        if !ui.edge_right.0.is_null() {
            let _ = DestroyWindow(ui.edge_right);
        }
    }
    ui.hwnd = HWND::default();
    ui.cursor = HWND::default();
    ui.edge_left = HWND::default();
    ui.edge_right = HWND::default();
    publish_hwnds(hwnd_slot, ui.hwnd, ui.cursor);
    if let Ok(hwnd) = create_banner() {
        ui.hwnd = hwnd;
        ui.cursor = create_cursor_window().unwrap_or_default();
        ui.edge_left = HWND::default();
        ui.edge_right = HWND::default();
        publish_hwnds4(hwnd_slot, ui.hwnd, ui.cursor, HWND::default(), HWND::default());
        // Same renderer choice as the initial setup: a rebuild must not silently switch a
        // host that asked for the layered fallback onto the composition path.
        ui.display = if dcomp_overlay_enabled() { attach_display(hwnd) } else { None };
        ui.cursor_stage = None;
        DISPLAY_COMPOSITION.store(ui.display.is_some(), Ordering::SeqCst);
        CURSOR_STAGE.store(ui.cursor_stage.is_some(), Ordering::SeqCst);
        if ui.visible {
            apply_show(ui);
            // Official re-suppresses the system cursor immediately after a display
            // or DPI change (`failed to re-suppress system cursor after display
            // change`, `all_functions.c:60424-60505`), instead of waiting for the
            // periodic timer to come round (VIS-28).
            let ok = ensure_system_cursor_suppressed();
            SUPPRESSED.store(ok, Ordering::SeqCst);
            if !ok {
                SUPPRESS_FAILURES.fetch_add(1, Ordering::SeqCst);
            }
            ui.next_suppress = Instant::now() + SUPPRESS_EVERY;
        }
    }
}

/// Paint the cursor sprite at a physical position with a `Scale` factor.
fn place_cursor(ui: &mut Ui, x: f32, y: f32, scale: f32) -> Result<(), String> {
    if ui.cursor.0.is_null() {
        return Err(CREATE_WINDOW_FAILED.to_string());
    }
    if !ui.hwnd.0.is_null() {
        unsafe {
            let _ = SetWindowPos(
                ui.hwnd,
                Some(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW | SWP_NOACTIVATE,
            );
        }
    }
    // No capture exclusion on the cursor overlay on purpose — see create_cursor_window().
    // Official placement: the window origin is the hotspot, so the glyph tip lands
    // on the requested point: origin = target - round(dpi/96 * 58.5). The DPI comes
    // from the monitor under the target, not from the system (VIS-05).
    let dpi = dpi_for_point(x, y);
    ui.cursor_dpi = dpi;
    let (sprite, hotspot) = cursor_metrics(dpi);
    let left = (x as i32) - hotspot.round() as i32;
    let top = (y as i32) - hotspot.round() as i32;
    let scale_key = (scale * 1000.0).round() as i32;
    let target = (left, top, sprite, scale_key);
    CURSOR_DPI.store(dpi, Ordering::SeqCst);
    CURSOR_PRESS_SCALE_BITS.store(scale.to_bits(), Ordering::SeqCst);
    // Only touch the window manager when the placement or the sprite scale changed;
    // the official only re-rasterises on a position/DPI change (VIS-01/VIS-30).
    if ui.last_place != Some(target) {
        unsafe {
            SetWindowPos(
                ui.cursor,
                Some(HWND_TOPMOST),
                left,
                top,
                sprite,
                sprite,
                SWP_SHOWWINDOW | SWP_NOACTIVATE,
            )
            .map_err(|err| format!("{RAISE_BEFORE_POSITION}: {err}"))?;
            let _ = ShowWindow(ui.cursor, SW_SHOWNOACTIVATE);
            let _ = InvalidateRect(Some(ui.cursor), None, true);
        }
        ui.last_place = Some(target);
    }
    // Record the drawn position so diagnostics can report exactly where the fake
    // cursor is, which is what makes cursor-visibility checks unambiguous.
    CURSOR_POS.0.store(x as i32, Ordering::SeqCst);
    CURSOR_POS.1.store(y as i32, Ordering::SeqCst);
    Ok(())
}

#[allow(dead_code)]
fn scoot_pose(dx: f32, dy: f32, press: bool) -> CursorPose {
    // The official squash is applied to the visual as a vertical scale while the
    // motion is fast. The magnitude is carried by the motion frames; the pose
    // keeps the direction so a debug render can tilt along the travel axis.
    let axis = if dx == 0.0 && dy == 0.0 {
        0.0
    } else {
        dy.atan2(dx).to_degrees()
    };
    CursorPose {
        stretch_axis_degrees: axis,
        scale_x: 1.0,
        scale_y: 1.0,
        composite_opacity: 1.0,
        press: if press { 1.0 } else { 0.0 },
        ..Default::default()
    }
}

/// Drop any motion in flight (official `stop active cursor motion animation`).
fn stop_cursor_motion(ui: &mut Ui) {
    ui.cursor_motion = None;
    ui.cursor_tick = 0;
    ui.press_anim = None;
    ui.cursor_press_until = None;
    ui.press_scale_last = 1.0;
    PRESS_ACTIVE.store(false, Ordering::SeqCst);
}

/// Advance an in-flight motion by one 60 Hz frame. Returns true when the motion
/// is still running, so the UI loop knows to keep waking up.
fn step_cursor_motion(ui: &mut Ui) -> bool {
    release_press_if_due(ui);
    // Copy what this frame needs so the mutable borrow of the motion ends before
    // place_cursor borrows the whole UI again.
    // The official animation is driven by the compositor's clock: the sampled
    // keyframes sit on a `SetDuration(T)` timeline, so wall-clock progress picks
    // the sample. Advancing one frame per pump tick with a sleep per tick made the
    // real duration `T + n * per-frame overhead`, which flattened every move back
    // to roughly the same length (VIS-08).
    let (frame, to, finished) = {
        let Some(motion) = ui.cursor_motion.as_mut() else { return false };
        let count = motion.frames.len();
        if count == 0 {
            (None, motion.to, true)
        } else {
            let elapsed = motion.start.elapsed().as_millis() as u64;
            let done = elapsed >= motion.duration_ms;
            let progress = (elapsed as f32 / motion.duration_ms.max(1) as f32).clamp(0.0, 1.0);
            let index = ((progress * count.saturating_sub(1) as f32).round() as usize)
                .min(count - 1);
            if done {
                motion.painted = count - 1;
                (Some(motion.frames[count - 1]), motion.to, true)
            } else if index == motion.painted {
                (None, motion.to, false)
            } else {
                motion.painted = index;
                (Some(motion.frames[index]), motion.to, false)
            }
        }
    };
    if finished {
        ui.cursor_x = to.0;
        ui.cursor_y = to.1;
        ui.cursor_motion = None;
        ui.cursor_tick = 0;
        // Diagnostics only: `motionLastMs` vs `motionDurationMs` is the pair that
        // tells a correct time-based replay from a frame-counted one. Never log here:
        // stderr is piped and unread by the parity drivers.
        if let Ok(slot) = MOTION_START.lock() {
            if let Some(start) = *slot {
                MOTION_LAST_MS.store(start.elapsed().as_millis() as u64, Ordering::SeqCst);
            }
        }
        // The last frame is not exactly the destination; land the sprite on the
        // target so a post-move screenshot shows the cursor where the model asked.
        let scale = ui.press_scale_last;
        let _ = place_cursor(ui, to.0, to.1, scale);
        MOTION_ACTIVE.store(false, Ordering::SeqCst);
        return false;
    }
    let Some(frame) = frame else { return false };
    ui.cursor_tick += 1;
    MOTION_TICK.store(ui.cursor_tick as i32, Ordering::SeqCst);
    let (x, y) = frame.point;
    let scale = ui.press_scale_last;
    let _ = place_cursor(ui, x, y, scale);
    ui.cursor_x = x;
    ui.cursor_y = y;
    CURSOR_POS.0.store(x as i32, Ordering::SeqCst);
    CURSOR_POS.1.store(y as i32, Ordering::SeqCst);
    true
}

/// Advance the press `Scale` transition and repaint the sprite while it runs.
fn step_press(ui: &mut Ui) -> bool {
    let Some(anim) = ui.press_anim else { return false };
    let (scale, done) = press_scale_at(&anim, Instant::now());
    let changed = (scale - ui.press_scale_last).abs() > 0.0005;
    ui.press_scale_last = scale;
    if done {
        ui.press_anim = None;
    }
    if changed || done {
        let (x, y) = (ui.cursor_x, ui.cursor_y);
        let _ = place_cursor(ui, x, y, ui.press_scale_last);
    }
    !done
}

/// `schedule cursor press release`: drop the pressed sprite once its window has
/// elapsed so the cursor visually springs back.
fn release_press_if_due(ui: &mut Ui) {
    if let Some(until) = ui.cursor_press_until {
        if Instant::now() >= until {
            ui.cursor_press_until = None;
            PRESS_ACTIVE.store(false, Ordering::SeqCst);
            // The official release is a second 550 ms `Scale` transition back to
            // 1.0 (`release cursor pressed state`); it starts from wherever the
            // press transition got to, so a fast double click interpolates cleanly.
            ui.press_anim = Some(PressAnim {
                start: Instant::now(),
                from: ui.press_scale_last,
                to: 1.0,
            });
        }
    }
}

/// Official ordering: the system cursor is moved to the destination *before* the
/// cosmetic animation starts, so input never waits on the animation.
fn play_cursor(ui: &mut Ui, x: f32, y: f32, press: bool) -> Result<(), String> {
    if ui.cursor.0.is_null() {
        return Err(CREATE_WINDOW_FAILED.to_string());
    }
    if FORCE_HIDDEN.load(Ordering::SeqCst) {
        apply_hide(ui);
        return Ok(());
    }
    let from = (ui.cursor_x, ui.cursor_y);
    let to = (x, y);
    ui.cursor_seeded = true;
    // Diagnostics: the requested destination, not an animation frame.
    LAST_INPUT.0.store(x as i32, Ordering::SeqCst);
    LAST_INPUT.1.store(y as i32, Ordering::SeqCst);
    let plan = motion::plan(from, to);
    // Press state: the official starts a 550 ms `Scale` transition to 0.7 and
    // schedules the release that starts the reverse transition (VIS-04).
    let now = Instant::now();
    if press {
        ui.press_anim = Some(PressAnim {
            start: now,
            from: ui.press_scale_last,
            to: CURSOR_PRESS_SCALE,
        });
        ui.cursor_press_until = Some(now + Duration::from_millis(CURSOR_PRESS_MS));
        PRESS_ACTIVE.store(true, Ordering::SeqCst);
    } else if ui.press_scale_last < 1.0 && ui.press_anim.is_none() && ui.cursor_press_until.is_none() {
        // A plain move after a click still has to release the pressed scale.
        ui.press_anim = Some(PressAnim { start: now, from: ui.press_scale_last, to: 1.0 });
    }
    if plan.kind == motion::MoveKind::Snap {
        place_cursor(ui, x, y, ui.press_scale_last)?;
        ui.snapped = true;
        ui.cursor_x = x;
        ui.cursor_y = y;
        ui.cursor_motion = None;
        ui.cursor_tick = 0;
        // A snap that interrupts an in-flight move must also clear the flag, or
        // `motionActive` stays stuck true and the pump animates forever.
        MOTION_ACTIVE.store(false, Ordering::SeqCst);
        return Ok(());
    }
    ui.snapped = false;
    ui.cursor_tick = 0;
    let frames = motion::keyframes(&plan);
    // The official lays its sampled keyframes across the whole computed duration
    // (`SetDuration(T)`), so the interval is `T / (n - 1)`, not a fixed 16 ms
    // (VIS-08).
    let frame_ms = motion::frame_interval_ms(&plan, frames.len()).max(1);
    let duration_ms = (plan.duration_s * 1000.0).round().max(1.0) as u64;
    MOTION_TARGET.0.store(x as i32, Ordering::SeqCst);
    MOTION_TARGET.1.store(y as i32, Ordering::SeqCst);
    MOTION_FRAMES.store(frames.len() as i32, Ordering::SeqCst);
    MOTION_TICK.store(0, Ordering::SeqCst);
    MOTION_ACTIVE.store(true, Ordering::SeqCst);
    MOTION_DURATION_MS.store(duration_ms, Ordering::SeqCst);
    MOTION_FRAME_MS.store(frame_ms, Ordering::SeqCst);
    if let Ok(mut slot) = MOTION_START.lock() {
        *slot = Some(Instant::now());
    }
    ui.cursor_motion = Some(Motion {
        from,
        to,
        frames,
        frame_ms,
        duration_ms,
        start: Instant::now(),
        painted: usize::MAX,
    });
    // First frame paints immediately so there is no visible dead time.
    let _ = step_cursor_motion(ui);
    Ok(())
}

unsafe extern "system" fn on_foreground(
    _hook: HWINEVENTHOOK,
    _event: u32,
    _hwnd: HWND,
    _id_object: i32,
    _id_child: i32,
    _thread: u32,
    _timestamp: u32,
) {
    if !VISIBLE.load(Ordering::SeqCst) || FORCE_HIDDEN.load(Ordering::SeqCst) {
        return;
    }
    // Ignore this process's own windows. The overlay is topmost and re-shown on
    // every action, so counting its own foreground events creates a self-feeding
    // Raise storm that starves the pump.
    if _hwnd.0.is_null() || process_owns_window(_hwnd) {
        return;
    }
    note_foreground(_hwnd);
    if let Some(handle) = HANDLE.get() {
        let _ = handle.tx.send(Cmd::Raise);
        wake_overlay_thread();
    }
}

fn raise_overlay(ui: &Ui) {
    unsafe {
        if !ui.hwnd.0.is_null() {
            let _ = SetWindowPos(
                ui.hwnd,
                Some(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE,
            );
        }
        if !ui.cursor.0.is_null() {
            let _ = SetWindowPos(
                ui.cursor,
                Some(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE,
            );
        }
    }
}

fn ensure_dispatcher() -> Option<windows::System::DispatcherQueueController> {
    let opts = windows::Win32::System::WinRT::DispatcherQueueOptions {
        dwSize: std::mem::size_of::<windows::Win32::System::WinRT::DispatcherQueueOptions>() as u32,
        threadType: windows::Win32::System::WinRT::DQTYPE_THREAD_CURRENT,
        apartmentType: windows::Win32::System::WinRT::DQTAT_COM_STA,
    };
    unsafe { windows::Win32::System::WinRT::CreateDispatcherQueueController(opts).ok() }
}

fn d3d_device() -> windows::core::Result<(ID3D11Device, ID3D11DeviceContext)> {
    // Official `CODEX_CUA_CURSOR_FORCE_WARP`; DSH keeps the same switch under its own
    // prefix plus the official name, so a broken driver can be forced onto WARP
    // (VIS-26).
    let force_warp = std::env::var("DSH_CU_FORCE_WARP").is_ok()
        || std::env::var("CODEX_CUA_CURSOR_FORCE_WARP").is_ok();
    let drivers: &[D3D_DRIVER_TYPE] = if force_warp {
        &[D3D_DRIVER_TYPE_WARP]
    } else {
        &[D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP]
    };
    let mut last = windows::core::Error::from(windows::core::HRESULT(0x8000_4005_u32 as i32));
    for driver in drivers {
        let mut device = None;
        let mut context = None;
        let hr = unsafe {
            D3D11CreateDevice(
                None,
                *driver,
                Default::default(),
                D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                None::<&[D3D_FEATURE_LEVEL]>,
                D3D11_SDK_VERSION,
                Some(&mut device),
                None,
                Some(&mut context),
            )
        };
        match (hr, device, context) {
            (Ok(()), Some(device), Some(context)) => return Ok((device, context)),
            (Err(err), _, _) => last = err,
            _ => {}
        }
    }
    Err(last)
}

fn create_graphics(compositor: &Compositor) -> Option<GraphicsHold> {
    let (d3d, _ctx) = d3d_device().ok()?;
    let factory: ID2D1Factory1 =
        unsafe { D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, None).ok()? };
    let d2d = unsafe {
        d3d.cast::<IDXGIDevice>()
            .ok()
            .and_then(|dxgi| factory.CreateDevice(&dxgi).ok())
    };
    let interop: ICompositorInterop = compositor.cast().ok()?;
    let graphics = unsafe {
        if let Some(d2d) = d2d.as_ref() {
            interop.CreateGraphicsDevice(d2d).ok()
        } else {
            None
        }
        .or_else(|| interop.CreateGraphicsDevice(&d3d).ok())?
    };
    Some(GraphicsHold {
        _d3d: d3d,
        _d2d: d2d,
        factory,
        graphics,
    })
}

fn create_drawing_surface(
    graphics: &CompositionGraphicsDevice,
    width: f32,
    height: f32,
) -> Option<(CompositionDrawingSurface, ICompositionDrawingSurfaceInterop)> {
    let surface = graphics
        .CreateDrawingSurface(
            Size {
                Width: width.max(1.0),
                Height: height.max(1.0),
            },
            DirectXPixelFormat::B8G8R8A8UIntNormalized,
            DirectXAlphaMode::Premultiplied,
        )
        .ok()?;
    let interop: ICompositionDrawingSurfaceInterop = surface.cast().ok()?;
    Some((surface, interop))
}

fn begin_d2d(
    interop: &ICompositionDrawingSurfaceInterop,
) -> Result<(ID2D1DeviceContext, POINT), Option<windows::core::Error>> {
    let mut offset = POINT::default();
    match unsafe { interop.BeginDraw::<ID2D1DeviceContext>(None, &mut offset) } {
        Ok(dc) => Ok((dc, offset)),
        Err(err) => {
            // VIS-25: a lost device has to reach the pump, which rebuilds the whole
            // overlay and retries (`retry cursor overlay rendering operation after
            // recreate`). Before this the `ui.device_lost` branch was dead code.
            if is_device_lost(&err) {
                DEVICE_LOST.store(true, Ordering::SeqCst);
            }
            Err(Some(err))
        }
    }
}

fn apply_draw_offset(dc: &ID2D1DeviceContext, offset: POINT) {
    let matrix = Matrix3x2 {
        M11: 1.0,
        M12: 0.0,
        M21: 0.0,
        M22: 1.0,
        M31: offset.x as f32,
        M32: offset.y as f32,
    };
    unsafe { dc.SetTransform(&matrix) };
}

fn sprite_from_surface(
    compositor: &Compositor,
    surface: &CompositionDrawingSurface,
    width: f32,
    height: f32,
    offset: Vector3,
) -> Option<SpriteVisual> {
    let brush = compositor.CreateSurfaceBrushWithSurface(surface).ok()?;
    let _ = brush.SetStretch(CompositionStretch::None);
    let sprite = compositor.CreateSpriteVisual().ok()?;
    sprite.SetBrush(&brush).ok()?;
    sprite.SetSize(Vector2::new(width, height)).ok()?;
    sprite.SetOffset(offset).ok()?;
    Some(sprite)
}

fn dwrite_factory() -> Option<IDWriteFactory> {
    unsafe { DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED).ok() }
}

fn make_text_layout(
    dwrite: &IDWriteFactory,
    text: &str,
    width: f32,
    height: f32,
    rtl: bool,
    weight: DWRITE_FONT_WEIGHT,
) -> Option<IDWriteTextLayout> {
    let format: IDWriteTextFormat = unsafe {
        dwrite
            .CreateTextFormat(
                w!("Segoe UI"),
                None,
                weight,
                DWRITE_FONT_STYLE_NORMAL,
                DWRITE_FONT_STRETCH_NORMAL,
                16.0,
                w!("en-US"),
            )
            .ok()?
    };
    unsafe {
        let _ = format.SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
        let _ = format.SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
        let _ = format.SetReadingDirection(if rtl {
            DWRITE_READING_DIRECTION_RIGHT_TO_LEFT
        } else {
            DWRITE_READING_DIRECTION_LEFT_TO_RIGHT
        });
    }
    let wide: Vec<u16> = text.encode_utf16().collect();
    let layout = unsafe { dwrite.CreateTextLayout(&wide, &format, width.max(8.0), height.max(8.0)).ok()? };
    if let Ok(layout1) = layout.cast::<IDWriteTextLayout1>() {
        let _ = unsafe {
            layout1.SetCharacterSpacing(
                0.15,
                0.15,
                0.0,
                DWRITE_TEXT_RANGE {
                    startPosition: 0,
                    length: wide.len().max(1) as u32,
                },
            )
        };
    }
    Some(layout)
}

fn measure_layout(layout: &IDWriteTextLayout) -> Option<f32> {
    let mut metrics = DWRITE_TEXT_METRICS::default();
    unsafe { layout.GetMetrics(&mut metrics) }.ok()?;
    let width = if metrics.widthIncludingTrailingWhitespace > 0.0 {
        metrics.widthIncludingTrailingWhitespace
    } else {
        metrics.width
    };
    Some(width)
}

fn draw_text_on_surface(
    interop: &ICompositionDrawingSurfaceInterop,
    layout: &IDWriteTextLayout,
    ink: (f32, f32, f32, f32),
) -> Result<bool, ()> {
    let (dc, offset) = match begin_d2d(interop) {
        Ok(pair) => pair,
        Err(Some(err)) if is_device_lost(&err) => return Err(()),
        Err(_) => return Ok(false),
    };
    apply_draw_offset(&dc, offset);
    let clear = d2d_color(0.0, 0.0, 0.0, 0.0);
    unsafe { dc.Clear(Some(&clear)) };
    if let Ok(brush) = unsafe { dc.CreateSolidColorBrush(&d2d_color(ink.0, ink.1, ink.2, ink.3), None) } {
        unsafe {
            dc.DrawTextLayout(
                Vector2::new(0.0, 0.0),
                layout,
                &brush,
                D2D1_DRAW_TEXT_OPTIONS_NONE,
            )
        };
    }
    drop(dc);
    unsafe { interop.EndDraw() }.map_err(|_| ())?;
    Ok(true)
}

fn fill_rounded_surface(
    interop: &ICompositionDrawingSurfaceInterop,
    width: f32,
    height: f32,
    radius: f32,
    color: (f32, f32, f32, f32),
    inset: f32,
) -> Result<bool, ()> {
    let (dc, offset) = match begin_d2d(interop) {
        Ok(pair) => pair,
        Err(Some(err)) if is_device_lost(&err) => return Err(()),
        Err(_) => return Ok(false),
    };
    apply_draw_offset(&dc, offset);
    let clear = d2d_color(0.0, 0.0, 0.0, 0.0);
    unsafe { dc.Clear(Some(&clear)) };
    if let Ok(brush) = unsafe { dc.CreateSolidColorBrush(&d2d_color(color.0, color.1, color.2, color.3), None) }
    {
        let rounded = D2D1_ROUNDED_RECT {
            rect: D2D_RECT_F {
                left: 0.0,
                top: inset,
                right: width,
                bottom: height - inset,
            },
            radiusX: radius,
            radiusY: radius,
        };
        unsafe { dc.FillRoundedRectangle(&rounded, &brush) };
    }
    drop(dc);
    unsafe { interop.EndDraw() }.map_err(|_| ())?;
    Ok(true)
}

/// `cubic-bezier(x1, y1, x2, y2)` evaluated at `x` in `[0, 1]`, the same curve
/// the official hands to `CompositionEasingFunction`. Used for the fades and the
/// layered fallback's border pulse (VIS-18/VIS-20).
fn cubic_bezier(ease: (f32, f32, f32, f32), x: f32) -> f32 {
    let x = x.clamp(0.0, 1.0);
    let (x1, y1, x2, y2) = ease;
    let bezier = |a: f32, b: f32, t: f32| {
        let omt = 1.0 - t;
        3.0 * omt * omt * t * a + 3.0 * omt * t * t * b + t * t * t
    };
    // Invert x(t) by bisection: the control points are monotone in [0, 1].
    let mut lo = 0.0f32;
    let mut hi = 1.0f32;
    let mut t = x;
    for _ in 0..24 {
        let current = bezier(x1, x2, t);
        if (current - x).abs() < 1e-5 {
            break;
        }
        if current < x {
            lo = t;
        } else {
            hi = t;
        }
        t = (lo + hi) * 0.5;
    }
    bezier(y1, y2, t)
}

/// Start the layered-pill opacity fade toward `target`, continuing from wherever
/// the previous fade left off.
fn start_pill_fade(target: f32) {
    if let Ok(mut slot) = PILL_FADE.lock() {
        let from = slot.as_ref().map(|(start, from, to)| fade_alpha(*from, *to, *start)).unwrap_or(1.0);
        *slot = Some((Instant::now(), from, target));
    }
}

fn clear_pill_fade() {
    if let Ok(mut slot) = PILL_FADE.lock() {
        *slot = None;
    }
}

/// `cubic-bezier(FADE_EASE)` interpolation of the active layered-pill fade.
fn fade_alpha(from: f32, to: f32, start: Instant) -> f32 {
    let elapsed = start.elapsed().as_millis() as f32;
    let t = (elapsed / FADE_MS as f32).clamp(0.0, 1.0);
    from + (to - from) * cubic_bezier(FADE_EASE, t)
}

fn current_fade_alpha() -> f32 {
    match PILL_FADE.lock().ok().and_then(|slot| *slot) {
        Some((start, from, to)) => fade_alpha(from, to, start),
        None => 1.0,
    }
}

/// Build the official `cubic-bezier` easing for a scalar animation.
fn scalar_easing(compositor: &Compositor, ease: (f32, f32, f32, f32)) -> Option<CompositionEasingFunction> {
    compositor
        .CreateCubicBezierEasingFunction(
            Vector2::new(ease.0, ease.1),
            Vector2::new(ease.2, ease.3),
        )
        .ok()?
        .cast()
        .ok()
}

/// WinRT attaches easing per keyframe (`InsertKeyFrameWithEasingFunction`); the
/// official creates the easing function and hands it to each keyframe it inserts.
fn insert_scalar_keyframe(
    anim: &ScalarKeyFrameAnimation,
    progress: f32,
    value: f32,
    easing: Option<&CompositionEasingFunction>,
) -> windows::core::Result<()> {
    match easing {
        Some(easing) => anim.InsertKeyFrameWithEasingFunction(progress, value, easing),
        None => anim.InsertKeyFrame(progress, value),
    }
}

fn fade_visual(compositor: &Compositor, visual: &ContainerVisual, target: f32, duration_ms: i64) -> windows::core::Result<()> {
    let anim = compositor.CreateScalarKeyFrameAnimation()?;
    anim.SetDuration(ticks_100ns(duration_ms))?;
    anim.SetStopBehavior(AnimationStopBehavior::SetToFinalValue)?;
    // Official entrance/exit easing: `create overlay opacity easing` with
    // `cubic-bezier(0.22, 1.0, 0.36, 1.0)` (`140056c79:17-40`).
    let easing = scalar_easing(compositor, FADE_EASE);
    let start = if target >= 0.5 { 0.0 } else { 1.0 };
    insert_scalar_keyframe(&anim, 0.0, start, easing.as_ref())?;
    insert_scalar_keyframe(&anim, 1.0, target, easing.as_ref())?;
    visual.StartAnimation(&HSTRING::from("Opacity"), &anim)
}

/// Official border pulse (Ghidra `140057dbb:330-353`): a scalar keyframe
/// animation on `Opacity` with keyframes `0.5 -> 1.0` and `1.0 -> 0.76`,
/// repeating forever. The 0.76 value is shared with the pill constant pool.
pub const BORDER_PULSE_LOW: f32 = 0.76;
/// Official border thickness factor (`16 * scale`).
pub const BORDER_THICKNESS_FACTOR: f32 = 16.0;
/// Official inner border thickness factor.
pub const BORDER_INNER_FACTOR: f32 = 0.88;

fn pulse_opacity(compositor: &Compositor, visual: &Visual) -> windows::core::Result<()> {
    let anim = compositor.CreateScalarKeyFrameAnimation()?;
    // Official duration is 30000000 ticks = 3000 ms (`140057dbb:323-325`), not 1.2 s.
    anim.SetDuration(ticks_100ns(PULSE_MS))?;
    anim.SetIterationBehavior(AnimationIterationBehavior::Forever)?;
    let easing = scalar_easing(compositor, PULSE_EASE);
    // Official keyframes: full opacity at the halfway point, 0.76 at the end. There
    // is deliberately no keyframe at 0.0 -- the animation starts from the visual's
    // current opacity (`140057dbb:337-340`).
    insert_scalar_keyframe(&anim, 0.5, 1.0, easing.as_ref())?;
    insert_scalar_keyframe(&anim, 1.0, BORDER_PULSE_LOW, easing.as_ref())?;
    visual.StartAnimation(&HSTRING::from("Opacity"), &anim)
}

fn linear_edge_brush(
    compositor: &Compositor,
    start: Vector2,
    end: Vector2,
) -> Option<CompositionLinearGradientBrush> {
    let gradient = compositor.CreateLinearGradientBrush().ok()?;
    let _ = gradient.SetMappingMode(CompositionMappingMode::Absolute);
    let _ = gradient.SetStartPoint(start);
    let _ = gradient.SetEndPoint(end);
    let stops = gradient.ColorStops().ok()?;
    let accent = accent_color();
    let solid = ui_color(accent.0, accent.1, accent.2, 0.82);
    let clear = ui_color(accent.0, accent.1, accent.2, 0.0);
    let _ = stops.Append(&compositor.CreateColorGradientStopWithOffsetAndColor(0.0, solid).ok()?);
    let _ = stops.Append(&compositor.CreateColorGradientStopWithOffsetAndColor(1.0, clear).ok()?);
    Some(gradient)
}

fn insert_gradient_visual(
    compositor: &Compositor,
    children: &windows::UI::Composition::VisualCollection,
    brush: &CompositionLinearGradientBrush,
    size: Vector2,
    offset: Vector3,
) -> Option<SpriteVisual> {
    let visual = compositor.CreateSpriteVisual().ok()?;
    let _ = visual.SetSize(size);
    let _ = visual.SetOffset(offset);
    let as_brush: CompositionBrush = brush.cast().ok()?;
    let _ = visual.SetBrush(&as_brush);
    let _ = children.InsertAtTop(&visual);
    Some(visual)
}

fn attach_edge_glow(
    compositor: &Compositor,
    children: &windows::UI::Composition::VisualCollection,
    width: f32,
    height: f32,
) -> (Option<ContainerVisual>, Option<SpriteVisual>, Option<SpriteVisual>) {
    let strip = (width * 0.018).clamp(18.0, 36.0);
    let edge_root = match compositor.CreateContainerVisual() {
        Ok(root) => root,
        Err(_) => return (None, None, None),
    };
    let _ = edge_root.SetSize(Vector2::new(width, height));
    let Ok(edge_children) = edge_root.Children() else {
        return (None, None, None);
    };
    let left = linear_edge_brush(compositor, Vector2::new(0.0, 0.0), Vector2::new(strip, 0.0)).and_then(|brush| {
        insert_gradient_visual(
            compositor,
            &edge_children,
            &brush,
            Vector2::new(strip, height),
            Vector3::new(0.0, 0.0, 0.0),
        )
    });
    let right = linear_edge_brush(compositor, Vector2::new(strip, 0.0), Vector2::new(0.0, 0.0)).and_then(|brush| {
        insert_gradient_visual(
            compositor,
            &edge_children,
            &brush,
            Vector2::new(strip, height),
            Vector3::new(width - strip, 0.0, 0.0),
        )
    });
    if let Some(visual) = left.as_ref() {
        let _ = start_edge_breath(compositor, visual, strip, height, 0.0, false);
    }
    if let Some(visual) = right.as_ref() {
        let _ = start_edge_breath(compositor, visual, strip, height, width - strip, false);
    }
    let _ = children.InsertAtBottom(&edge_root);
    (Some(edge_root), left, right)
}

/// Official `src/overlay` vocabulary: the animating edge strips are the overlay
/// border, and they carry three coordinated loops — a **size breath**, an
/// **offset breath** and an **opacity pulse** (`create border size breath
/// animation` / `create border offset breath animation` /
/// `create border pulse animation`, each `SetIterationBehavior(Forever)`).
fn start_edge_breath(
    compositor: &Compositor,
    visual: &SpriteVisual,
    strip: f32,
    height: f32,
    x: f32,
    acting: bool,
) -> windows::core::Result<()> {
    let as_visual: Visual = visual.cast()?;
    let _ = acting;
    // Official border pulse keyframes are 1.0 -> BORDER_PULSE_LOW (0.76) over a
    // 3000 ms cycle; there is no separate acting cadence in the binary
    // (`140057dbb:311-346`, VIS-18).
    let (lo, hi) = (BORDER_PULSE_LOW, 1.0);
    let opacity = compositor.CreateScalarKeyFrameAnimation()?;
    opacity.SetDuration(ticks_100ns(EDGE_BREATH_MS))?;
    opacity.SetIterationBehavior(AnimationIterationBehavior::Forever)?;
    let easing = scalar_easing(compositor, PULSE_EASE);
    insert_scalar_keyframe(&opacity, 0.0, lo, easing.as_ref())?;
    insert_scalar_keyframe(&opacity, 0.5, hi, easing.as_ref())?;
    insert_scalar_keyframe(&opacity, 1.0, lo, easing.as_ref())?;
    as_visual.StartAnimation(&HSTRING::from("Opacity"), &opacity)?;
    // Official border thickness is `16 * scale` (the `* 0.88` inner factor is
    // applied to the geometry, VIS-19). The previous code scaled by `dpi/96` twice.
    let grow = BORDER_THICKNESS_FACTOR * dpi_scale_global();
    let size = compositor.CreateVector2KeyFrameAnimation()?;
    size.SetDuration(ticks_100ns(EDGE_BREATH_MS))?;
    size.SetIterationBehavior(AnimationIterationBehavior::Forever)?;
    size.InsertKeyFrame(0.0, Vector2::new(strip, height))?;
    size.InsertKeyFrame(0.5, Vector2::new(strip + grow, height))?;
    size.InsertKeyFrame(1.0, Vector2::new(strip, height))?;
    as_visual.StartAnimation(&HSTRING::from("Size"), &size)?;
    let offset = compositor.CreateVector3KeyFrameAnimation()?;
    offset.SetDuration(ticks_100ns(EDGE_BREATH_MS))?;
    offset.SetIterationBehavior(AnimationIterationBehavior::Forever)?;
    // Official offset breath: `x -> x - 16*s` and back, both edges, both 3000 ms.
    let inset = if x <= 1.0 { 0.0 } else { grow };
    offset.InsertKeyFrame(0.0, Vector3::new(x, 0.0, 0.0))?;
    offset.InsertKeyFrame(0.5, Vector3::new(x - inset, 0.0, 0.0))?;
    offset.InsertKeyFrame(1.0, Vector3::new(x, 0.0, 0.0))?;
    as_visual.StartAnimation(&HSTRING::from("Offset"), &offset)?;
    Ok(())
}

impl DisplayHold {
    fn set_edge_activity(&self, acting: bool) {
        let size = self.root.Size().unwrap_or(Vector2::new(0.0, 0.0));
        let strip = (size.X * 0.018).clamp(18.0, 36.0);
        if let Some(left) = self.edge_left.as_ref() {
            let _ = start_edge_breath(&self.compositor, left, strip, size.Y, 0.0, acting);
        }
        if let Some(right) = self.edge_right.as_ref() {
            let _ = start_edge_breath(&self.compositor, right, strip, size.Y, size.X - strip, acting);
        }
    }
}

fn attach_display(hwnd: HWND) -> Option<DisplayHold> {
    note_display_step("dispatcher");
    let controller = ensure_dispatcher()?;
    note_display_step("compositor");
    let compositor = Compositor::new().ok()?;
    note_display_step("desktop-interop");
    let desktop: ICompositorDesktopInterop = compositor.cast().ok()?;
    note_display_step("desktop-target");
    let target = unsafe { desktop.CreateDesktopWindowTarget(hwnd, true).ok()? };
    note_display_step("target-ok");
    let mut rect = RECT::default();
    let _ = unsafe { GetClientRect(hwnd, &mut rect) };
    let width = (rect.right - rect.left).max(1) as f32;
    let height = (rect.bottom - rect.top).max(BAR_HEIGHT) as f32;
    let root = compositor.CreateContainerVisual().ok()?;
    root.SetSize(Vector2::new(width, height)).ok()?;
    root.SetOffset(Vector3::new(0.0, 0.0, 0.0)).ok()?;
    root.SetOpacity(0.0).ok()?;
    let children = root.Children().ok()?;
    let graphics = create_graphics(&compositor);
    let (edge_fade, edge_left, edge_right) = attach_edge_glow(&compositor, &children, width, height);
    let dpi = dpi_scale(hwnd);
    let rtl = is_rtl_locale();
    let dwrite = dwrite_factory();
    let mut layout = compute_pill_layout(width, height, BANNER, ESC_HINT, dpi, None, None, rtl);
    if let Some(dwrite) = dwrite.as_ref() {
        let status = make_text_layout(dwrite, BANNER, layout.status_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_SEMI_BOLD);
        let cancel = make_text_layout(dwrite, ESC_HINT, layout.cancel_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_NORMAL);
        layout = compute_pill_layout(
            width,
            height,
            BANNER,
            ESC_HINT,
            dpi,
            status.as_ref().and_then(measure_layout),
            cancel.as_ref().and_then(measure_layout),
            rtl,
        );
        let _ = (status, cancel);
    }
    let accent = accent_color();
    let ink = pick_ink_color(accent);
    let shadow = shadow_color(accent);
    // Official pill stack: the accent shape, a warm-grey drop shadow derived from
    // the accent, and the text surfaces on top. The shadow layer is offset a
    // couple of DIP and inset vertically so it reads as a soft cast rather than a
    // second pill.
    let shadow_inset = 3.0 * dpi;
    let shadow_offset = 2.5 * dpi;
    let shadow_root = compositor.CreateContainerVisual().ok()?;
    shadow_root
        .SetSize(Vector2::new(layout.width, layout.height))
        .ok()?;
    shadow_root
        .SetOffset(Vector3::new(layout.x + shadow_offset, layout.y + shadow_offset, 0.0))
        .ok()?;
    if let Ok(shadow_children) = shadow_root.Children() {
        if let Ok(geometry) = compositor.CreateRoundedRectangleGeometry() {
            let _ = geometry.SetSize(Vector2::new(layout.body_w, layout.body_h - shadow_inset));
            let _ = geometry.SetOffset(Vector2::new(
                layout.body_x - layout.x,
                layout.body_y - layout.y,
            ));
            let _ = geometry.SetCornerRadius(Vector2::new(layout.radius, layout.radius));
            if let Ok(brush) = compositor.CreateColorBrushWithColor(ui_color(shadow.0, shadow.1, shadow.2, 0.45)) {
                if let Ok(shape) = compositor.CreateSpriteShapeWithGeometry(&geometry) {
                    let _ = shape.SetFillBrush(&brush);
                    if let Ok(visual) = compositor.CreateShapeVisual() {
                        let _ = visual.SetSize(Vector2::new(layout.width, layout.height - shadow_inset));
                        if let Ok(shapes) = visual.Shapes() {
                            let _ = shapes.Append(&shape);
                        }
                        let _ = shadow_children.InsertAtTop(&visual);
                        let _ = children.InsertAtTop(&shadow_root);
                    }
                }
            }
        }
    }
    let pill_root = compositor.CreateContainerVisual().ok()?;
    pill_root
        .SetSize(Vector2::new(layout.width, layout.height))
        .ok()?;
    pill_root
        .SetOffset(Vector3::new(layout.x, layout.y, 0.0))
        .ok()?;
    let pill_children = pill_root.Children().ok()?;
    // Official: the accent rounded rectangle is attached to the pill **content** at
    // the content size (`140057dbb:513,576-581`), i.e. inset by `18*s` inside the
    // root and `48*s` tall. The clip matches so the shimmer cannot bleed out.
    let rounded = compositor.CreateRoundedRectangleGeometry().ok()?;
    rounded.SetSize(Vector2::new(layout.body_w, layout.body_h)).ok()?;
    rounded
        .SetOffset(Vector2::new(layout.body_x - layout.x, layout.body_y - layout.y))
        .ok()?;
    rounded
        .SetCornerRadius(Vector2::new(layout.radius, layout.radius))
        .ok()?;
    if let Ok(clip) = compositor.CreateGeometricClipWithGeometry(&rounded) {
        let _ = pill_root.SetClip(&clip);
    }
    if let Ok(fill) = compositor.CreateColorBrushWithColor(ui_color(accent.0, accent.1, accent.2, 1.0)) {
        if let Ok(shape) = compositor.CreateSpriteShapeWithGeometry(&rounded) {
            let _ = shape.SetFillBrush(&fill);
            if let Ok(shape_visual) = compositor.CreateShapeVisual() {
                let _ = shape_visual.SetSize(Vector2::new(layout.width, layout.height));
                if let Ok(shapes) = shape_visual.Shapes() {
                    let _ = shapes.Append(&shape);
                }
                let _ = pill_children.InsertAtTop(&shape_visual);
            }
        }
    }
    attach_shimmer(&compositor, &pill_children, &layout, accent);
    if let (Some(graphics), Some(dwrite)) = (graphics.as_ref(), dwrite.as_ref()) {
        if let Some(status_layout) =
            make_text_layout(dwrite, BANNER, layout.status_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_SEMI_BOLD)
        {
            if let Some((surface, interop)) =
                create_drawing_surface(&graphics.graphics, layout.status_width + 8.0, layout.height)
            {
                if draw_text_on_surface(&interop, &status_layout, ink).ok() == Some(true) {
                    if let Some(visual) = sprite_from_surface(
                        &compositor,
                        &surface,
                        layout.status_width + 8.0,
                        layout.height,
                        Vector3::new(layout.status_x - layout.x, 0.0, 0.0),
                    ) {
                        let _ = pill_children.InsertAtTop(&visual);
                    }
                }
            }
        }
        if let Some(cancel_layout) =
            make_text_layout(dwrite, ESC_HINT, layout.cancel_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_NORMAL)
        {
            if let Some((surface, interop)) =
                create_drawing_surface(&graphics.graphics, layout.cancel_width + 8.0, layout.height)
            {
                if draw_text_on_surface(&interop, &cancel_layout, ink).ok() == Some(true) {
                    if let Some(visual) = sprite_from_surface(
                        &compositor,
                        &surface,
                        layout.cancel_width + 8.0,
                        layout.height,
                        Vector3::new(layout.cancel_x - layout.x, 0.0, 0.0),
                    ) {
                        let _ = pill_children.InsertAtTop(&visual);
                    }
                }
            }
        }
    }
    let _ = children.InsertAtTop(&pill_root);
    note_display_step("pill-built");
    // Diagnostic self-test: a bright square at a known screen position proves whether
    // DirectComposition presents on this machine at all. Without it, a missing pill
    // cannot be told apart from a mis-sized visual tree.
    if std::env::var("DSH_CU_OVERLAY_SELFTEST").is_ok() {
        if let Ok(brush) = compositor.CreateColorBrushWithColor(ui_color(1.0, 0.0, 0.0, 1.0)) {
            if let Ok(visual) = compositor.CreateSpriteVisual() {
                let _ = visual.SetBrush(&brush);
                let _ = visual.SetSize(Vector2::new(240.0, 240.0));
                let _ = visual.SetOffset(Vector3::new(100.0, 100.0, 0.0));
                let _ = children.InsertAtTop(&visual);
            }
        }
    }
    let _ = target.SetRoot(&root);
    if let Ok(mut slot) = PILL_LAYOUT_INFO.lock() {
        *slot = format!(
            "client={}x{} layout=({},{},{},{}) body=({},{},{},{}) statusW={} cancelW={}",
            width, height, layout.x, layout.y, layout.width, layout.height,
            layout.body_x, layout.body_y, layout.body_w, layout.body_h,
            layout.status_width, layout.cancel_width
        );
    }
    note_display_step("root-set");
    let _ = root.SetOpacity(0.0);
    Some(DisplayHold {
        _controller: controller,
        compositor,
        _target: target,
        root,
        _graphics: graphics,
        _shimmer: None,
        _display_fade: None,
        _edge_fade: edge_fade,
        edge_left,
        edge_right,
    })
}

/// Official `create text shimmer` / `create shimmer mask gradient` /
/// `create shimmer gradient mask` / `start shimmer animation`.
///
/// A masked accent band sweeps across the status text. The band is an accent
/// brush masked by a gradient and clipped to the pill, and the sweep is an
/// offset keyframe on the band visual — the same displacement as the official
/// `Vector2(StartX + TravelX * shimmer.Progress, 0.0)`, without depending on
/// expression-animation support.
fn attach_shimmer(
    compositor: &Compositor,
    pill_children: &windows::UI::Composition::VisualCollection,
    layout: &PillLayout,
    accent: (f32, f32, f32, f32),
) {
    let band = (layout.status_width * 1.1).max(48.0);
    let Ok(mask_brush) = compositor.CreateMaskBrush() else { return };
    let Ok(gradient) = compositor.CreateLinearGradientBrush() else { return };
    let _ = gradient.SetMappingMode(CompositionMappingMode::Absolute);
    let _ = gradient.SetStartPoint(Vector2::new(0.0, 0.0));
    let _ = gradient.SetEndPoint(Vector2::new(band, 0.0));
    if let Ok(stops) = gradient.ColorStops() {
        if let Ok(clear) = compositor.CreateColorGradientStopWithOffsetAndColor(0.0, ui_color(1.0, 1.0, 1.0, 0.0)) {
            let _ = stops.Append(&clear);
        }
        if let Ok(solid) = compositor.CreateColorGradientStopWithOffsetAndColor(0.35, ui_color(1.0, 1.0, 1.0, 1.0)) {
            let _ = stops.Append(&solid);
        }
        if let Ok(fade) = compositor.CreateColorGradientStopWithOffsetAndColor(1.0, ui_color(1.0, 1.0, 1.0, 0.0)) {
            let _ = stops.Append(&fade);
        }
    }
    let Ok(source_brush) =
        compositor.CreateColorBrushWithColor(ui_color(accent.0, accent.1, accent.2, 0.55))
    else {
        return;
    };
    let _ = mask_brush.SetSource(&source_brush);
    let _ = mask_brush.SetMask(&gradient);

    let Ok(shape) = compositor.CreateSpriteShape() else { return };
    let _ = shape.SetFillBrush(&mask_brush);
    let Ok(visual) = compositor.CreateShapeVisual() else { return };
    let _ = visual.SetSize(Vector2::new(layout.status_width + 8.0, layout.body_h));
    if let Ok(shapes) = visual.Shapes() {
        let _ = shapes.Append(&shape);
    }
    // Clip the sweep to the status text run so it never bleeds out of the pill.
    if let Ok(geometry) = compositor.CreateRoundedRectangleGeometry() {
        let _ = geometry.SetSize(Vector2::new(layout.status_width + 8.0, layout.body_h));
        let _ = geometry.SetCornerRadius(Vector2::new(layout.radius, layout.radius));
        if let Ok(clip) = compositor.CreateGeometricClipWithGeometry(&geometry) {
            let _ = visual.SetClip(&clip);
        }
    }
    let _ = visual.SetOffset(Vector3::new(
        layout.status_x - layout.x,
        layout.body_y - layout.y,
        0.0,
    ));
    // Sweep the band across the text forever.
    if let Ok(offset) = compositor.CreateVector3KeyFrameAnimation() {
        let travel = layout.status_width + 8.0 + band;
        let _ = offset.SetDuration(ticks_100ns(SHIMMER_MS));
        let _ = offset.SetIterationBehavior(AnimationIterationBehavior::Forever);
        let _ = offset.InsertKeyFrame(0.0, Vector3::new(-band, 0.0, 0.0));
        let _ = offset.InsertKeyFrame(1.0, Vector3::new(travel, 0.0, 0.0));
        let _ = visual.StartAnimation(&HSTRING::from("Offset"), &offset);
    }
    let _ = pill_children.InsertAtTop(&visual);
}

unsafe extern "system" fn cursor_wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_PAINT => {
            if CURSOR_STAGE.load(Ordering::SeqCst) {
                let mut ps = PAINTSTRUCT::default();
                let _ = BeginPaint(hwnd, &mut ps);
                let _ = EndPaint(hwnd, &ps);
            } else {
                paint_cursor(hwnd);
            }
            LRESULT(0)
        }
        WM_CLOSE => LRESULT(0),
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}

/// Official cursor raster: fill `rgba(0.03,0.03,0.03,1)` (#080808), stroke
/// `rgba(1,1,1,0.8)` at width `2 * scale`, plus an accent-coloured blurred halo
/// (ellipse radius `28 * scale`, blur `16 * scale`) offset to `(a-3s, a-2s)`.
///
/// The GDI fallback cannot blur, so the halo is drawn as a few concentric
/// accent rings that fade outward — visually equivalent at cursor size and
/// available on every machine.
fn draw_cursor_gdi(hdc: HDC, scale_factor: f32) {
    unsafe {
        // VIS-05: the sprite follows the monitor under the cursor, not the system.
        let dpi = CURSOR_DPI.load(Ordering::SeqCst).max(96);
        let scale = dpi as f32 / 96.0;
        let (sprite, glyph) = cursor_metrics(dpi);
        // Halo first so the glyph reads on top of it.
        let accent = accent_color();
        // `glyph` is already the DPI-scaled hotspot from cursor_metrics, so `scale`
        // must not be applied to it a second time: that double scale pushed the glow
        // out of the sprite and clipped the arrow.
        let a: f32 = (glyph + 9.0 * scale).round();
        let centre = ((a - 3.0 * scale).round() as i32, (a - 2.0 * scale).round() as i32);
        let halo_r = 28.0 * scale;
        for ring in 0..3 {
            let radius = halo_r * (1.0 - ring as f32 * 0.3);
            let alpha = 0.28 / (ring as f32 + 1.0);
            let colour = rgb_ref(accent, alpha);
            let brush = CreateSolidBrush(colour);
            let pen = CreatePen(PS_SOLID, 1, colour);
            let old_brush = SelectObject(hdc, HGDIOBJ(brush.0));
            let old_pen = SelectObject(hdc, HGDIOBJ(pen.0));
            let _ = Ellipse(
                hdc,
                centre.0 - radius as i32,
                centre.1 - radius as i32,
                centre.0 + radius as i32,
                centre.1 + radius as i32,
            );
            SelectObject(hdc, old_pen);
            SelectObject(hdc, old_brush);
            let _ = DeleteObject(HGDIOBJ(brush.0));
            let _ = DeleteObject(HGDIOBJ(pen.0));
        }
        // Glyph. The sprite is positioned at `target - hotspot`, so the glyph box
        // origin has to be the hotspot for the tip to land on the target point.
        let pts = arrow_points(glyph, scale_factor);
        let win_pts: Vec<POINT> = pts
            .iter()
            .map(|(x, y)| POINT {
                x: (x + glyph).round() as i32,
                y: (y + glyph).round() as i32,
            })
            .collect();
        // #080808 fill, white 0.8-alpha 2*scale stroke.
        let fill = CreateSolidBrush(COLORREF(0x0008_0808));
        let stroke = CreatePen(PS_SOLID, (2.0 * scale).round().max(1.0) as i32, rgb_ref((1.0, 1.0, 1.0, 1.0), 0.8));
        let old_brush = SelectObject(hdc, HGDIOBJ(fill.0));
        let old_pen = SelectObject(hdc, HGDIOBJ(stroke.0));
        let _ = Polygon(hdc, &win_pts);
        SelectObject(hdc, old_pen);
        SelectObject(hdc, old_brush);
        let _ = DeleteObject(HGDIOBJ(fill.0));
        let _ = DeleteObject(HGDIOBJ(stroke.0));
        let _ = sprite;
    }
}

/// `COLORREF` is `0x00BBGGRR`; `alpha` is blended against black because the GDI
/// cursor window has no per-pixel alpha.
fn rgb_ref(rgba: (f32, f32, f32, f32), alpha: f32) -> COLORREF {
    let a = (rgba.3 * alpha).clamp(0.0, 1.0);
    let channel = |v: f32| (v * a * 255.0).round().clamp(0.0, 255.0) as u32;
    COLORREF(channel(rgba.2) << 16 | channel(rgba.1) << 8 | channel(rgba.0))
}

/// Cached cursor sprite keyed by `(sprite px, Scale bits)`; the raster is only
/// rebuilt when the DPI or the animated `Scale` changes (VIS-30).
static CURSOR_SPRITE_CACHE: Mutex<Option<(i32, u32, Arc<Vec<u8>>)>> = Mutex::new(None);

fn cached_cursor_sprite(sprite: i32, glyph: f32, scale: f32, scale_factor: f32) -> Arc<Vec<u8>> {
    // Quantise the scale: the press animates continuously, and each raster costs a
    // few milliseconds, so 0.02 steps keep the whole 550 ms transition at a handful
    // of rasters instead of sixty.
    let key = (scale_factor * 50.0).round().to_bits();
    if let Ok(mut guard) = CURSOR_SPRITE_CACHE.lock() {
        let stale = match guard.as_ref() {
            Some((cached_sprite, cached_key, _)) => *cached_sprite != sprite || *cached_key != key,
            None => true,
        };
        if stale {
            CURSOR_RASTERIZATIONS.fetch_add(1, Ordering::Relaxed);
            let accent = accent_color();
            let pixels = rasterize_cursor(sprite, glyph, scale, scale_factor, accent, 2.0 * scale);
            *guard = Some((sprite, key, Arc::new(pixels)));
        }
        if let Some((_, _, pixels)) = guard.as_ref() {
            return pixels.clone();
        }
    }
    Arc::new(vec![0u8; (sprite.max(1) as usize).pow(2) * 4])
}

/// Inside test plus distance to the nearest edge, both in sprite pixels.
fn point_in_polygon(points: &[(f32, f32)], x: f32, y: f32) -> (bool, f32) {
    let mut inside = false;
    let mut nearest = f32::MAX;
    let count = points.len();
    for index in 0..count {
        let (x0, y0) = points[index];
        let (x1, y1) = points[(index + 1) % count];
        if (y0 > y) != (y1 > y) {
            let t = (y - y0) / (y1 - y0);
            if x < x0 + t * (x1 - x0) {
                inside = !inside;
            }
        }
        let dx = x1 - x0;
        let dy = y1 - y0;
        let len2 = dx * dx + dy * dy;
        let u = if len2 > 0.0 {
            (((x - x0) * dx + (y - y0) * dy) / len2).clamp(0.0, 1.0)
        } else {
            0.0
        };
        let ex = x - (x0 + u * dx);
        let ey = y - (y0 + u * dy);
        let distance = (ex * ex + ey * ey).sqrt();
        if distance < nearest {
            nearest = distance;
        }
    }
    (inside, nearest)
}

/// Separable Gaussian blur over an `f32` mask of `width x height`, edges clamped.
fn gaussian_blur(mask: &mut [f32], width: usize, height: usize, sigma: f32) {
    if sigma <= 0.0 || width == 0 || height == 0 {
        return;
    }
    let radius = (sigma * 3.0).ceil().max(1.0) as usize;
    let mut kernel = Vec::with_capacity(radius + 1);
    let mut total = 0.0f32;
    for i in 0..=radius {
        let weight = (-((i * i) as f32) / (2.0 * sigma * sigma)).exp();
        kernel.push(weight);
        total += if i == 0 { weight } else { 2.0 * weight };
    }
    for weight in kernel.iter_mut() {
        *weight /= total;
    }
    let mut temp = vec![0.0f32; width * height];
    for y in 0..height {
        for x in 0..width {
            let mut acc = kernel[0] * mask[y * width + x];
            for k in 1..=radius {
                let left = x.saturating_sub(k);
                let right = (x + k).min(width - 1);
                acc += kernel[k] * (mask[y * width + left] + mask[y * width + right]);
            }
            temp[y * width + x] = acc;
        }
    }
    for y in 0..height {
        for x in 0..width {
            let mut acc = kernel[0] * temp[y * width + x];
            for k in 1..=radius {
                let up = y.saturating_sub(k);
                let down = (y + k).min(height - 1);
                acc += kernel[k] * (temp[up * width + x] + temp[down * width + x]);
            }
            mask[y * width + x] = acc;
        }
    }
}

/// Rasterise the official cursor: a 13-point glyph filled `#080808` and stroked
/// `rgba(1,1,1,0.8)` at `2*s`, over an accent ellipse of radius `28*s` blurred by
/// `16*s`, offset to `(a - 3s, a - 2s)`.
///
/// VIS-02/VIS-03: the GDI version could do neither antialiasing (`Polygon` is hard
/// edged) nor blur (three concentric rings), so this supersamples the outline 4x4
/// and convolves the halo with a real Gaussian. Returns premultiplied BGRA.
pub fn rasterize_cursor(
    sprite: i32,
    glyph: f32,
    scale: f32,
    glyph_scale: f32,
    accent: (f32, f32, f32, f32),
    stroke_px: f32,
) -> Vec<u8> {
    let n = sprite.max(1) as usize;
    let mut out = vec![0u8; n * n * 4];
    if n == 0 {
        return out;
    }
    let points: Vec<(f32, f32)> = CURSOR_GLYPH_POINTS
        .iter()
        .map(|(x, y)| (x * glyph * glyph_scale + glyph, y * glyph * glyph_scale + glyph))
        .collect();
    let a = glyph + 9.0 * scale;
    let cx = a - 3.0 * scale;
    let cy = a - 2.0 * scale;
    let halo_r = (28.0 * scale).max(1.0);
    let sigma = (16.0 * scale).max(0.5);
    const SS: usize = 4;
    let inv = 1.0 / (SS * SS) as f32;
    let mut mask = vec![0.0f32; n * n];
    for y in 0..n {
        for x in 0..n {
            let mut acc = 0.0f32;
            for sy in 0..SS {
                for sx in 0..SS {
                    let px = x as f32 + (sx as f32 + 0.5) / SS as f32;
                    let py = y as f32 + (sy as f32 + 0.5) / SS as f32;
                    let dx = px - cx;
                    let dy = py - cy;
                    if dx * dx + dy * dy <= halo_r * halo_r {
                        acc += 1.0;
                    }
                }
            }
            mask[y * n + x] = acc * inv;
        }
    }
    gaussian_blur(&mut mask, n, n, sigma);
    let half_stroke = (stroke_px * 0.5).max(0.5);
    let fill = (0x08 as f32 / 255.0, 0x08 as f32 / 255.0, 0x08 as f32 / 255.0);
    // Only the glyph's bounding box needs the outline distance test; the rest of the
    // sprite is halo (or empty) and would just burn supersamples.
    let pad = half_stroke + 1.0;
    let mut min_x = n as f32;
    let mut max_x = 0.0f32;
    let mut min_y = n as f32;
    let mut max_y = 0.0f32;
    for point in &points {
        if point.0 < min_x {
            min_x = point.0;
        }
        if point.0 > max_x {
            max_x = point.0;
        }
        if point.1 < min_y {
            min_y = point.1;
        }
        if point.1 > max_y {
            max_y = point.1;
        }
    }
    let x0 = ((min_x - pad).max(0.0) as usize).min(n - 1);
    let x1 = ((max_x + pad).min(n as f32 - 1.0) as usize).max(x0);
    let y0 = ((min_y - pad).max(0.0) as usize).min(n - 1);
    let y1 = ((max_y + pad).min(n as f32 - 1.0) as usize).max(y0);
    for y in y0..=y1 {
        for x in x0..=x1 {
            let mut inside = 0.0f32;
            let mut border = 0.0f32;
            for sy in 0..SS {
                for sx in 0..SS {
                    let px = x as f32 + (sx as f32 + 0.5) / SS as f32;
                    let py = y as f32 + (sy as f32 + 0.5) / SS as f32;
                    let (is_in, distance) = point_in_polygon(&points, px, py);
                    if is_in {
                        inside += 1.0;
                    }
                    if distance <= half_stroke {
                        border += 1.0;
                    }
                }
            }
            let cover_fill = (inside * inv).clamp(0.0, 1.0);
            let cover_stroke = (border * inv * 0.8).clamp(0.0, 1.0);
            let mut alpha = 0.42 * mask[y * n + x];
            let mut r = accent.0;
            let mut g = accent.1;
            let mut b = accent.2;
            r = fill.0 * cover_fill + r * (1.0 - cover_fill);
            g = fill.1 * cover_fill + g * (1.0 - cover_fill);
            b = fill.2 * cover_fill + b * (1.0 - cover_fill);
            alpha = cover_fill + alpha * (1.0 - cover_fill);
            r = cover_stroke + r * (1.0 - cover_stroke);
            g = cover_stroke + g * (1.0 - cover_stroke);
            b = cover_stroke + b * (1.0 - cover_stroke);
            alpha = cover_stroke + alpha * (1.0 - cover_stroke);
            let i = (y * n + x) * 4;
            out[i] = (b * alpha * 255.0).round().clamp(0.0, 255.0) as u8;
            out[i + 1] = (g * alpha * 255.0).round().clamp(0.0, 255.0) as u8;
            out[i + 2] = (r * alpha * 255.0).round().clamp(0.0, 255.0) as u8;
            out[i + 3] = (alpha * 255.0).round().clamp(0.0, 255.0) as u8;
        }
    }
    out
}
fn paint_cursor(hwnd: HWND) {
    // The pressed `Scale` factor is animated over 550 ms (VIS-04); the UI loop
    // advances it and schedules the reverse transition (`schedule cursor press
    // release` / `release cursor pressed state`).
    let scale_factor = f32::from_bits(CURSOR_PRESS_SCALE_BITS.load(Ordering::SeqCst));
    unsafe {
        let mut ps = PAINTSTRUCT::default();
        let hdc = BeginPaint(hwnd, &mut ps);
        if CURSOR_LAYERED.load(Ordering::SeqCst) && !update_layered_cursor(hwnd, scale_factor) {
            // UpdateLayeredWindow is unavailable: fall back to the colour-keyed sprite.
            CURSOR_LAYERED.store(false, Ordering::SeqCst);
            let _ = apply_overlay_layered(hwnd, 255);
        }
        if !CURSOR_LAYERED.load(Ordering::SeqCst) {
            draw_cursor_gdi(hdc, scale_factor);
        }
        let _ = EndPaint(hwnd, &ps);
    }
}

/// Push the cached, antialiased, genuinely blurred cursor sprite to the layered
/// window.
///
/// Returns false when the layered path is unavailable, so the caller can fall back.
fn update_layered_cursor(hwnd: HWND, scale_factor: f32) -> bool {
    unsafe {
        let dpi = CURSOR_DPI.load(Ordering::SeqCst).max(96);
        let (sprite, glyph) = cursor_metrics(dpi);
        let scale = dpi as f32 / 96.0;
        // The raster only changes when the DPI or the animated `Scale` changes, so
        // it is cached: the official does not re-rasterise on a pure move either
        // (`FUN_14004fe10:30-37` short-circuits when `(x, y, dpi)` are unchanged).
        let pixels = cached_cursor_sprite(sprite, glyph, scale, scale_factor);
        let mut info = BITMAPINFO::default();
        info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        info.bmiHeader.biWidth = sprite;
        info.bmiHeader.biHeight = -sprite;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = 0;

        let mut out_bits: *mut core::ffi::c_void = std::ptr::null_mut();
        let Ok(out_dib) = CreateDIBSection(None, &info, DIB_RGB_COLORS, &mut out_bits, None, 0)
        else {
            return false;
        };
        let out_dc = CreateCompatibleDC(None);
        let prev_out = SelectObject(out_dc, HGDIOBJ(out_dib.0));
        let out_px = std::slice::from_raw_parts_mut(out_bits as *mut u8, pixels.len());
        out_px.copy_from_slice(&pixels);
        let _ = GdiFlush();

        let mut rect = RECT::default();
        let _ = GetWindowRect(hwnd, &mut rect);
        let dst = POINT {
            x: rect.left,
            y: rect.top,
        };
        let size = SIZE {
            cx: sprite,
            cy: sprite,
        };
        let src = POINT { x: 0, y: 0 };
        let blend = BLENDFUNCTION {
            BlendOp: AC_SRC_OVER as u8,
            BlendFlags: 0,
            SourceConstantAlpha: 255,
            AlphaFormat: AC_SRC_ALPHA as u8,
        };
        let screen = GetDC(None);
        let ok = UpdateLayeredWindow(
            hwnd,
            Some(screen),
            Some(&dst),
            Some(&size),
            Some(out_dc),
            Some(&src),
            COLORREF(0),
            Some(&blend),
            ULW_ALPHA,
        )
        .is_ok();
        ReleaseDC(None, screen);

        SelectObject(out_dc, prev_out);
        let _ = DeleteObject(HGDIOBJ(out_dib.0));
        let _ = DeleteDC(out_dc);
        let _ = GdiFlush();
        ok
    }
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_PAINT => {
            if DISPLAY_COMPOSITION.load(Ordering::SeqCst) {
                let mut ps = PAINTSTRUCT::default();
                let _ = BeginPaint(hwnd, &mut ps);
                let _ = EndPaint(hwnd, &ps);
            } else {
                paint(hwnd);
            }
            LRESULT(0)
        }
        WM_DISPLAYCHANGE | WM_DPICHANGED => {
            if let Some(handle) = HANDLE.get() {
                let _ = handle.tx.send(Cmd::Recreate);
                wake_overlay_thread();
            }
            LRESULT(0)
        }
        WM_POWERBROADCAST => {
            let wp = wparam.0 as u32;
            if wp == 0x0006 || wp == 0x0007 || wp == 0x0012 {
                if let Some(handle) = HANDLE.get() {
                    let _ = handle.tx.send(Cmd::Recreate);
                    wake_overlay_thread();
                }
            }
            LRESULT(0)
        }
        WM_CLOSE => {
            unsafe {
                let _ = ShowWindow(hwnd, SW_HIDE);
            };
            LRESULT(0)
        }
        WM_DESTROY => LRESULT(0),
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}

// ---------------------------------------------------------------------------
// Status pill, rendered with UpdateLayeredWindow.
//
// The official helper builds the pill as a DirectComposition visual tree. That path
// is still available behind DSH_CU_DCOMP_OVERLAY=1, but it does not present here at
// all: the visual tree is built correctly (diagnostics report every step plus the
// layout) and yet a plain red sprite visual at a fixed offset is likewise absent from
// a desktop capture, so the pill stayed invisible while every overlay API reported it
// as shown. UpdateLayeredWindow does present on this machine, so the pill is rendered
// into a premultiplied BGRA sprite and pushed the same way the cursor is. Geometry,
// palette, contrast rules and the border pulse are unchanged.
// ---------------------------------------------------------------------------

struct PillSprite {
    layout: PillLayout,
    /// Premultiplied BGRA for `(layout.width + 2*pad) x (layout.height + 2*pad)`.
    pixels: Vec<u8>,
    scale: f32,
    /// Transparent padding around the pill so the blurred shadow is not clipped
    /// (VIS-16).
    pad: i32,
}

static PILL_SPRITE: Mutex<Option<PillSprite>> = Mutex::new(None);
static PILL_PULSE_START: Mutex<Option<Instant>> = Mutex::new(None);
static PILL_LAST_PUSH: Mutex<Option<Instant>> = Mutex::new(None);
/// Pill animation cadence (~30 Hz is plenty for a two-keyframe opacity pulse).
const PILL_FRAME_MS: u32 = 33;

/// The status pill prefers DirectComposition, which is the official architecture
/// (shimmer, edge glow, compositor-driven pulse). DSH_CU_ULW_OVERLAY=1 forces the
/// UpdateLayeredWindow fallback so it can be exercised on demand; it is also used
/// automatically whenever attaching the composition display fails.
fn dcomp_overlay_enabled() -> bool {
    std::env::var("DSH_CU_ULW_OVERLAY").is_err()
}

fn inside_rounded_rect(x: f32, y: f32, w: f32, h: f32, r: f32) -> bool {
    if x < 0.0 || y < 0.0 || x >= w || y >= h {
        return false;
    }
    let r = r.min(w / 2.0).min(h / 2.0).max(0.0);
    let cx = x.clamp(r, (w - r).max(r));
    let cy = y.clamp(r, (h - r).max(r));
    let dx = x - cx;
    let dy = y - cy;
    dx * dx + dy * dy <= r * r
}

/// Grayscale coverage of both text runs, drawn white on black at the official sizes
/// so the sprite can composite the ink colour with proper antialiasing.
fn pill_text_coverage(
    layout: &PillLayout,
    width: i32,
    height: i32,
    scale: f32,
    rtl: bool,
) -> Option<Vec<u8>> {
    let dwrite = dwrite_factory()?;
    let status = make_text_layout(&dwrite, BANNER, layout.status_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_SEMI_BOLD)?;
    let cancel = make_text_layout(&dwrite, ESC_HINT, layout.cancel_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_NORMAL)?;
    unsafe {
        let mut info = BITMAPINFO::default();
        info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        info.bmiHeader.biWidth = width;
        info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = 0;
        let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
        let dib = CreateDIBSection(None, &info, DIB_RGB_COLORS, &mut bits, None, 0).ok()?;
        let dc = CreateCompatibleDC(None);
        let prev = SelectObject(dc, HGDIOBJ(dib.0));
        let drawn = draw_pill_text(dc, width, height, layout, scale, &status, &cancel);
        let _ = GdiFlush();
        let coverage = if drawn {
            let raw = std::slice::from_raw_parts(bits as *const u8, (width * height * 4) as usize);
            let mut out = vec![0u8; (width * height) as usize];
            for i in 0..(width * height) as usize {
                let o = i * 4;
                out[i] = raw[o].max(raw[o + 1]).max(raw[o + 2]);
            }
            Some(out)
        } else {
            None
        };
        SelectObject(dc, prev);
        let _ = DeleteObject(HGDIOBJ(dib.0));
        let _ = DeleteDC(dc);
        coverage
    }
}

/// White text on black through Direct2D, so the mask is a clean coverage map.
fn draw_pill_text(
    hdc: HDC,
    width: i32,
    height: i32,
    layout: &PillLayout,
    scale: f32,
    status: &IDWriteTextLayout,
    cancel: &IDWriteTextLayout,
) -> bool {
    unsafe {
        let factory: ID2D1Factory =
            match D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, None) {
                Ok(factory) => factory,
                Err(_) => return false,
            };
        let props = D2D1_RENDER_TARGET_PROPERTIES {
            r#type: D2D1_RENDER_TARGET_TYPE_DEFAULT,
            pixelFormat: D2D1_PIXEL_FORMAT {
                format: DXGI_FORMAT_B8G8R8A8_UNORM,
                alphaMode: D2D1_ALPHA_MODE_IGNORE,
            },
            dpiX: 0.0,
            dpiY: 0.0,
            usage: D2D1_RENDER_TARGET_USAGE_GDI_COMPATIBLE,
            minLevel: D2D1_FEATURE_LEVEL_DEFAULT,
        };
        let Ok(target) = factory.CreateDCRenderTarget(&props) else {
            return false;
        };
        let rect = RECT {
            left: 0,
            top: 0,
            right: width,
            bottom: height,
        };
        if target.BindDC(hdc, &rect).is_err() {
            return false;
        }
        let Ok(brush) = target.CreateSolidColorBrush(
            &d2d_color(1.0, 1.0, 1.0, 1.0),
            None,
        ) else {
            return false;
        };
        target.BeginDraw();
        target.Clear(Some(&d2d_color(0.0, 0.0, 0.0, 1.0)));
        let _ = scale;
        let mut run = |layout: &IDWriteTextLayout, left: f32| {
            let _ = target.DrawTextLayout(
                Vector2::new(left, 0.0),
                layout,
                &brush,
                D2D1_DRAW_TEXT_OPTIONS_NONE,
            );
        };
        run(status, layout.status_x - layout.x);
        run(cancel, layout.cancel_x - layout.x);
        target.EndDraw(None, None).is_ok()
    }
}

/// Build the pill sprite once per DPI: body, drop shadow, separator and ink text.
fn build_pill_sprite(scale: f32) -> Option<PillSprite> {
    let (vx, _vy, vw, _vh) = virtual_desktop();
    let _ = vx;
    let desktop_w = vw as f32;
    let dwrite = dwrite_factory();
    let rtl = is_rtl_locale();
    let mut layout = compute_pill_layout(desktop_w, 0.0, BANNER, ESC_HINT, scale, None, None, rtl);
    if let Some(dwrite) = dwrite.as_ref() {
        let status = make_text_layout(dwrite, BANNER, layout.status_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_SEMI_BOLD);
        let cancel = make_text_layout(dwrite, ESC_HINT, layout.cancel_width + 8.0, layout.height, rtl, DWRITE_FONT_WEIGHT_NORMAL);
        layout = compute_pill_layout(
            desktop_w,
            0.0,
            BANNER,
            ESC_HINT,
            scale,
            status.as_ref().and_then(measure_layout),
            cancel.as_ref().and_then(measure_layout),
            rtl,
        );
    }
    let width = layout.width.round().max(1.0) as i32;
    let height = layout.height.round().max(1.0) as i32;
    let coverage = pill_text_coverage(&layout, width, height, scale, rtl);
    let accent = accent_color();
    let ink = pick_ink_color(accent);
    let shadow = shadow_color(accent);
    // The separator is a darkened accent, not the cast-shadow colour (which is warm
    // grey and reads as a pink line against the pill).
    let separator = (accent.0 * 0.45, accent.1 * 0.45, accent.2 * 0.45, 1.0);
    // Official pill stack: a warm-grey drop shadow derived from the accent, offset a
    // couple of DIP and inset vertically so it reads as a soft cast.
    let shadow_offset = 2.5 * scale;
    let shadow_inset = 3.0 * scale;
    let radius = layout.radius;
    let separator_x = layout.separator_x - layout.x;
    // The accent body is the content box inside the root, not the whole root
    // (`140057dbb:513,576-581`), so it is drawn at the body offset/size.
    let body_x = layout.body_x - layout.x;
    let body_y = layout.body_y - layout.y;
    let w = layout.body_w;
    let h = layout.body_h;
    // Official pill shadow is a real `CompositionShadow` (VIS-16). The layered
    // fallback cannot ask the compositor for one, so the silhouette is convolved
    // with the same separable Gaussian the cursor halo uses. That needs transparent
    // padding around the pill, so the sprite is larger than the layout box and is
    // pushed `pad` pixels up and to the left.
    let blur = (12.0 * scale).max(1.0);
    let pad = (shadow_offset + blur * 2.0).ceil().max(1.0) as i32;
    let padded_w = width + pad * 2;
    let padded_h = height + pad * 2;
    let mut shadow_mask = vec![0.0f32; (padded_w * padded_h) as usize];
    for y in 0..padded_h {
        for x in 0..padded_w {
            let fx = x as f32 + 0.5 - pad as f32;
            let fy = y as f32 + 0.5 - pad as f32;
            shadow_mask[(y * padded_w + x) as usize] = if inside_rounded_rect(
                fx - body_x - shadow_offset,
                fy - body_y - shadow_offset,
                w,
                h - shadow_inset,
                radius,
            ) {
                1.0
            } else {
                0.0
            };
        }
    }
    gaussian_blur(&mut shadow_mask, padded_w as usize, padded_h as usize, blur);
    let mut pixels = vec![0u8; (padded_w * padded_h * 4) as usize];
    for y in 0..padded_h {
        for x in 0..padded_w {
            let fx = x as f32 + 0.5 - pad as f32;
            let fy = y as f32 + 0.5 - pad as f32;
            let inside_body = inside_rounded_rect(fx - body_x, fy - body_y, w, h, radius);
            let (mut r, mut g, mut b, mut a) = if inside_body {
                (accent.0, accent.1, accent.2, 1.0f32)
            } else {
                let shadow_alpha = 0.45 * shadow_mask[(y * padded_w + x) as usize];
                (shadow.0, shadow.1, shadow.2, shadow_alpha)
            };
            if inside_body {
                // Official separator is a `4 * s` dot centred on the divider.
                if (fx - separator_x).abs() <= 2.0 * scale {
                    r = separator.0;
                    g = separator.1;
                    b = separator.2;
                }
                if let Some(cov) = coverage.as_ref() {
                    let cx = (x - pad).clamp(0, width - 1);
                    let cy = (y - pad).clamp(0, height - 1);
                    let alpha = cov[(cy * width + cx) as usize] as f32 / 255.0;
                    if alpha > 0.0 {
                        r = ink.0 * alpha + r * (1.0 - alpha);
                        g = ink.1 * alpha + g * (1.0 - alpha);
                        b = ink.2 * alpha + b * (1.0 - alpha);
                    }
                }
            }
            let o = ((y * padded_w + x) * 4) as usize;
            pixels[o] = (b * a * 255.0).round().clamp(0.0, 255.0) as u8;
            pixels[o + 1] = (g * a * 255.0).round().clamp(0.0, 255.0) as u8;
            pixels[o + 2] = (r * a * 255.0).round().clamp(0.0, 255.0) as u8;
            pixels[o + 3] = (a * 255.0).round().clamp(0.0, 255.0) as u8;
        }
    }
    Some(PillSprite {
        layout,
        pixels,
        scale,
        pad,
    })
}

/// Push a premultiplied BGRA buffer as the window's layered content.
fn push_layered_bgra(
    hwnd: HWND,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
    pixels: &[u8],
    alpha: f32,
) -> bool {
    unsafe {
        let mut info = BITMAPINFO::default();
        info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        info.bmiHeader.biWidth = width;
        info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = 0;
        let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
        let Ok(dib) = CreateDIBSection(None, &info, DIB_RGB_COLORS, &mut bits, None, 0) else {
            return false;
        };
        let dc = CreateCompatibleDC(None);
        let prev = SelectObject(dc, HGDIOBJ(dib.0));
        let out = std::slice::from_raw_parts_mut(bits as *mut u8, pixels.len());
        let alpha = alpha.clamp(0.0, 1.0);
        if alpha >= 0.999 {
            out.copy_from_slice(pixels);
        } else {
            for (dst, src) in out.iter_mut().zip(pixels.iter()) {
                *dst = (*src as f32 * alpha).round().clamp(0.0, 255.0) as u8;
            }
        }
        let _ = GdiFlush();
        let dst = POINT { x, y };
        let size = SIZE {
            cx: width,
            cy: height,
        };
        let src = POINT { x: 0, y: 0 };
        let blend = BLENDFUNCTION {
            BlendOp: AC_SRC_OVER as u8,
            BlendFlags: 0,
            SourceConstantAlpha: 255,
            AlphaFormat: AC_SRC_ALPHA as u8,
        };
        let screen = GetDC(None);
        let ok = UpdateLayeredWindow(
            hwnd,
            Some(screen),
            Some(&dst),
            Some(&size),
            Some(dc),
            Some(&src),
            COLORREF(0),
            Some(&blend),
            ULW_ALPHA,
        )
        .is_ok();
        ReleaseDC(None, screen);
        SelectObject(dc, prev);
        let _ = DeleteObject(HGDIOBJ(dib.0));
        let _ = DeleteDC(dc);
        ok
    }
}

/// Official border pulse: full opacity for the first half of a **3000 ms** cycle,
/// then `cubic-bezier(0.4, 0, 0.2, 1)` down to `BORDER_PULSE_LOW` (`140057dbb:311-346`).
fn pill_pulse_alpha(start: Instant) -> f32 {
    let t = (start.elapsed().as_millis() % PULSE_MS as u128) as f32 / PULSE_MS as f32;
    if t < 0.5 {
        1.0
    } else {
        1.0 - (1.0 - BORDER_PULSE_LOW) * cubic_bezier(PULSE_EASE, (t - 0.5) / 0.5)
    }
}

fn paint_pill(hwnd: HWND, alpha: f32) -> bool {
    if hwnd.0.is_null() {
        return false;
    }
    let scale = dpi_scale_global();
    let mut guard = match PILL_SPRITE.lock() {
        Ok(guard) => guard,
        Err(_) => return false,
    };
    PILL_PAINT_CALLS.fetch_add(1, Ordering::Relaxed);
    let stale = guard.as_ref().map(|s| (s.scale - scale).abs() > 0.001).unwrap_or(true);
    if stale {
        PILL_BUILDS.fetch_add(1, Ordering::Relaxed);
        *guard = build_pill_sprite(scale);
        if guard.is_none() {
            PILL_BUILD_FAILS.fetch_add(1, Ordering::Relaxed);
        }
    }
    let Some(sprite) = guard.as_ref() else {
        return false;
    };
    // The sprite carries `pad` pixels of transparent margin for the blurred shadow,
    // so it is pushed that much up and to the left to keep the body where the layout
    // puts it (VIS-16).
    let width = sprite.layout.width.round().max(1.0) as i32 + sprite.pad * 2;
    let height = sprite.layout.height.round().max(1.0) as i32 + sprite.pad * 2;
    PILL_PUSHES.fetch_add(1, Ordering::Relaxed);
    PILL_LAST_ALPHA_BITS.store(alpha.to_bits(), Ordering::Relaxed);
    let ok = push_layered_bgra(
        hwnd,
        sprite.layout.x.round() as i32 - sprite.pad,
        sprite.layout.y.round() as i32 - sprite.pad,
        width,
        height,
        &sprite.pixels,
        alpha,
    );
    if !ok {
        PILL_PUSH_FAILS.fetch_add(1, Ordering::Relaxed);
    }
    ok
}

/// Push a pulse frame when one is due. Returns true while the pill is animating so
/// the pump keeps waking up.
fn pill_pulse_step(ui: &Ui) -> bool {
    if !ui.visible || ui.display.is_some() || ui.hwnd.0.is_null() {
        return false;
    }
    let start = match PILL_PULSE_START.lock().ok().and_then(|g| *g) {
        Some(start) => start,
        None => return false,
    };
    let now = Instant::now();
    match PILL_LAST_PUSH.lock() {
        Ok(mut last) => {
            if let Some(previous) = *last {
                if now.duration_since(previous) < Duration::from_millis(PILL_FRAME_MS as u64) {
                    return true;
                }
            }
            *last = Some(now);
        }
        Err(_) => return false,
    }
    let _ = paint_pill(ui.hwnd, pill_pulse_alpha(start) * current_fade_alpha());
    true
}

/// Push exit-fade frames for the layered pill; returns true while fading.
fn pill_fade_step(ui: &Ui) -> bool {
    if ui.display.is_some() || ui.hwnd.0.is_null() {
        return false;
    }
    let Ok(mut last) = PILL_LAST_PUSH.lock() else { return false };
    let now = Instant::now();
    if let Some(previous) = *last {
        if now.duration_since(previous) < Duration::from_millis(PILL_FRAME_MS as u64) {
            return true;
        }
    }
    *last = Some(now);
    drop(last);
    let _ = paint_pill(ui.hwnd, current_fade_alpha());
    true
}

/// The two pill backends are mutually exclusive: when the composition display
/// attached, the pill lives in the DComp visual tree and the layered sprite must not
/// also be pushed (that would double-draw and it is the tree the DComp path owns);
/// otherwise the layered sprite is the only thing that can put pixels on screen.
fn layered_pill_selected(display_present: bool) -> bool {
    !display_present
}

/// Show the pill: push the first frame and start the pulse, or hand over to the
/// DirectComposition path when it is explicitly enabled.
fn use_pill_renderer(ui: &Ui) {
    if !layered_pill_selected(ui.display.is_some()) {
        return;
    }
    let _ = paint_pill(ui.hwnd, 1.0);
    start_pill_pulse();
}

fn start_pill_pulse() {
    if let Ok(mut slot) = PILL_PULSE_START.lock() {
        *slot = Some(Instant::now());
    }
    if let Ok(mut slot) = PILL_LAST_PUSH.lock() {
        *slot = None;
    }
}

fn stop_pill_pulse() {
    if let Ok(mut slot) = PILL_PULSE_START.lock() {
        *slot = None;
    }
}

fn paint(hwnd: HWND) {
    unsafe {
        let mut ps = PAINTSTRUCT::default();
        let hdc = BeginPaint(hwnd, &mut ps);
        let mut rect = RECT::default();
        let _ = GetClientRect(hwnd, &mut rect);
        // The pill is an UpdateLayeredWindow sprite; the GDI drawing below is only a
        // last-resort fallback for machines where that fails.
        if paint_pill(hwnd, 1.0) {
            let _ = EndPaint(hwnd, &ps);
            return;
        }
        if paint_directwrite(hdc, &rect).is_none() {
            let mut bar = RECT {
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
            };
            if bar.bottom - bar.top > BAR_HEIGHT * 2 {
                bar.bottom = bar.top + BAR_HEIGHT;
            }
            let yellow = CreateSolidBrush(COLORREF(0x00C4FF));
            FillRect(hdc, &bar, yellow);
            let _ = DeleteObject(HGDIOBJ(yellow.0));
            SetBkMode(hdc, TRANSPARENT);
            SetTextColor(hdc, COLORREF(0));
            let text = format!("{BANNER}  ·  {ESC_HINT}");
            let mut wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
            DrawTextW(hdc, &mut wide, &mut bar, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
        let _ = EndPaint(hwnd, &ps);
    }
}

fn paint_directwrite(hdc: HDC, rect: &RECT) -> Option<()> {
    unsafe {
        let factory: ID2D1Factory = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, None).ok()?;
        let props = D2D1_RENDER_TARGET_PROPERTIES {
            r#type: D2D1_RENDER_TARGET_TYPE_DEFAULT,
            pixelFormat: D2D1_PIXEL_FORMAT {
                format: DXGI_FORMAT_B8G8R8A8_UNORM,
                alphaMode: D2D1_ALPHA_MODE_IGNORE,
            },
            dpiX: 0.0,
            dpiY: 0.0,
            usage: D2D1_RENDER_TARGET_USAGE_GDI_COMPATIBLE,
            minLevel: D2D1_FEATURE_LEVEL_DEFAULT,
        };
        let target: ID2D1DCRenderTarget = factory.CreateDCRenderTarget(&props).ok()?;
        target.BindDC(hdc, rect).ok()?;
        let dwrite: IDWriteFactory = DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED).ok()?;
        let format: IDWriteTextFormat = dwrite
            .CreateTextFormat(
                w!("Segoe UI"),
                None,
                DWRITE_FONT_WEIGHT_SEMI_BOLD,
                DWRITE_FONT_STYLE_NORMAL,
                DWRITE_FONT_STRETCH_NORMAL,
                16.0,
                w!("en-US"),
            )
            .ok()?;
        let _ = format.SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
        let _ = format.SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
        let text: Vec<u16> = format!("{BANNER}  ·  {ESC_HINT}").encode_utf16().collect();
        let layout_rect = D2D_RECT_F {
            left: rect.left as f32,
            top: rect.top as f32,
            right: rect.right as f32,
            bottom: rect.bottom as f32,
        };
        target.BeginDraw();
        let yellow = D2D1_COLOR_F {
            r: 1.0,
            g: 196.0 / 255.0,
            b: 0.0,
            a: 1.0,
        };
        target.Clear(Some(&yellow));
        if let Ok(brush) = target.CreateSolidColorBrush(
            &D2D1_COLOR_F {
                r: 0.05,
                g: 0.05,
                b: 0.05,
                a: 1.0,
            },
            None,
        ) {
            let _ = target.DrawText(
                &text,
                &format,
                &layout_rect,
                &brush,
                Default::default(),
                Default::default(),
            );
        }
        target.EndDraw(None, None).ok()?;
        Some(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shimmer_expression_matches_rdata() {
        assert_eq!(
            SHIMMER_OFFSET_EXPRESSION,
            "Vector2(StartX + TravelX * shimmer.Progress, 0.0)"
        );
        assert!(PATH_OFFSET_EXPRESSION.contains("SingleSegmentPoint"));
        assert!(PATH_OFFSET_EXPRESSION.contains("FirstHalfPoint"));
        assert!(first_half_point_expression().contains("motion.P0"));
        assert!(second_half_point_expression().contains("motion.P6"));
    }

    #[test]
    fn pill_layout_is_centered() {
        let layout = compute_pill_layout(1920.0, 1080.0, BANNER, ESC_HINT, 1.0, None, None, false);
        assert!(layout.x > 200.0);
        assert!(layout.x + layout.width < 1920.0);
        assert!(((layout.x + layout.width / 2.0) - 960.0).abs() < 1.0);
        // Official root height is 2 * 18 + 48 = 84 DIP at 100% scale, and the top
        // margin is 56 DIP (VIS-13/VIS-14).
        assert!((layout.height - 84.0).abs() < 0.01, "height {}", layout.height);
        // Root top = official content top (56) minus the 18 DIP root padding; the
        // accent body itself still starts at 56.
        assert!((layout.y - 38.0).abs() < 0.01, "root margin {}", layout.y);
        assert!((layout.body_y - 56.0).abs() < 0.01, "body top {}", layout.body_y);
        assert!(layout.separator_x > layout.status_x);
        assert!(BANNER.contains("DeepSeek Harness"));
        assert!(!BANNER.contains("ChatGPT"));
        assert!(!BANNER.contains("Codex"));
        assert_eq!(SETCURSORPOS_INITIAL, "SetCursorPos initial overlay cursor position");
    }

    #[test]
    fn default_accent_is_the_official_blue() {
        assert_eq!(ACCENT_HEX, "#339cff");
        let color = accent_color();
        assert!((color.0 - 0x33 as f32 / 255.0).abs() < 1e-6);
        assert!((color.1 - 0x9c as f32 / 255.0).abs() < 1e-6);
        assert!((color.2 - 0xff as f32 / 255.0).abs() < 1e-6);
        // Unparseable accent falls back to rgb(1, 105, 204).
        assert_eq!(parse_hex_color("nope"), None);
        assert!((ACCENT_FALLBACK.0 - 1.0 / 255.0).abs() < 1e-9);
    }

    #[test]
    fn oklab_round_trips_srgb() {
        for text in ["#339cff", "#767676", "#123456", "#ffffff", "#000000", "#ee1111"] {
            let c = parse_hex_color(text).unwrap();
            let (l, a, b) = srgb_to_oklab(c.0, c.1, c.2);
            let back = oklab_to_srgb(l, a, b);
            assert!(
                (back.0 - c.0).abs() < 1e-5 && (back.1 - c.1).abs() < 1e-5 && (back.2 - c.2).abs() < 1e-5,
                "{text}: {back:?} vs {c:?}"
            );
        }
    }

    #[test]
    fn darken_uses_the_official_oklab_lightness_step() {
        // #ee1111 reaches the darken branch (black 4.40 < 4.5, white 4.47 < 4.8)
        // and is chromatic, so the subtractive Oklab step and the multiplicative
        // search it replaced disagree. Expected values are an independent reference
        // implementation of FUN_14005202a with the FUN_140052755 / FUN_1400528e3
        // matrices.
        let accent = parse_hex_color("#ee1111").unwrap();
        let bg = (accent.0, accent.1, accent.2);
        assert!(contrast_ratio((0.05, 0.05, 0.05), bg) < 4.5, "must not hit the black branch");
        assert!(contrast_ratio((1.0, 1.0, 1.0), bg) < 4.8, "must not hit the white branch");
        let (r, g, b) = darken_accent_subtractive(bg);
        assert!((r - 0.9028).abs() < 2e-3, "r {r}");
        assert!(g < 1e-4, "the official step drives green to zero, got {g}");
        assert!((b - 0.0293).abs() < 2e-3, "b {b}");
        assert!(contrast_ratio((r, g, b), (1.0, 1.0, 1.0)) >= 4.8 - 1e-3);
        // The branch is actually wired into pick_ink_color.
        let ink = pick_ink_color(accent);
        assert!((ink.0 - r).abs() < 1e-5 && (ink.1 - g).abs() < 1e-5 && (ink.2 - b).abs() < 1e-5, "{ink:?}");
        // The old multiplicative search kept green at ~0.064, a visibly different
        // tone; this pins that the subtractive step is what ships.
        let mut lo = 0.0f32;
        let mut hi = 1.0f32;
        for _ in 0..20 {
            let mid = (lo + hi) * 0.5;
            let c = (bg.0 * mid, bg.1 * mid, bg.2 * mid);
            if contrast_ratio(c, (1.0, 1.0, 1.0)) >= 4.8 {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let old_g = bg.1 * lo;
        assert!(g < old_g - 0.02, "subtractive {g} must differ from the multiplicative {old_g}");
    }

    #[test]
    fn ink_prefers_dark_on_light_accents() {
        // Amber: black clears 4.5, so the ink is the dark tone.
        let amber = parse_hex_color("#FFC400").unwrap();
        let ink = pick_ink_color(amber);
        assert!(ink.0 < 0.2 && ink.1 < 0.2 && ink.2 < 0.2, "expected dark ink, got {ink:?}");
    }

    #[test]
    fn ink_darkens_an_accent_that_no_candidate_can_carry() {
        // #339cff: white only reaches ~2.7, so the algorithm must darken the
        // accent until it clears 4.8 against white.
        let blue = parse_hex_color("#339cff").unwrap();
        let ink = pick_ink_color(blue);
        assert!(ink.0 < blue.0 && ink.1 < blue.1 && ink.2 < blue.2, "expected darkening, got {ink:?}");
        let white = (1.0, 1.0, 1.0);
        assert!(
            contrast_ratio((ink.0, ink.1, ink.2), white) >= 4.8 - 1e-3,
            "ink must clear 4.8 against white"
        );
    }

    #[test]
    fn cursor_metrics_match_the_official_formulas() {
        // 96 DPI: 126 px sprite, 58.5 -> 59 px hotspot.
        let (sprite, glyph) = cursor_metrics_scaled(96, 1.0);
        assert_eq!(sprite, 126);
        assert!((glyph - 59.0).abs() < 0.5, "hotspot {glyph}");
        // 192 DPI doubles it.
        let (sprite2, glyph2) = cursor_metrics_scaled(192, 1.0);
        assert_eq!(sprite2, 252);
        assert!((glyph2 - 117.0).abs() < 0.5, "hotspot {glyph2}");
        // Never below the 96 DPI floor.
        assert_eq!(cursor_metrics_scaled(0, 1.0), cursor_metrics_scaled(96, 1.0));
    }

    #[test]
    fn the_cursor_scale_knob_shrinks_sprite_and_hotspot_together() {
        // A 150% desktop: 189 -> 132 px sprite and 88 -> 61 px hotspot, so the tip still
        // lands on the target and the pointer is a third smaller.
        let (sprite, glyph) = cursor_metrics_scaled(144, 0.7);
        assert_eq!(sprite, 132);
        assert!((glyph - 61.0).abs() < 0.5, "hotspot {glyph}");
        // The process-wide knob round-trips and clamps.
        assert!((cursor_scale() - 1.0).abs() < 1e-6, "the default stays official");
        set_cursor_scale(0.7);
        assert!((cursor_scale() - 0.7).abs() < 1e-6);
        set_cursor_scale(9.0);
        assert!((cursor_scale() - 2.0).abs() < 1e-6, "clamped");
        set_cursor_scale(1.0);
    }

    #[test]
    fn glyph_has_the_official_point_count_and_unit_span() {
        assert_eq!(CURSOR_GLYPH_POINTS.len(), 13);
        let min_x = CURSOR_GLYPH_POINTS.iter().fold(f32::MAX, |a, p| a.min(p.0));
        let max_x = CURSOR_GLYPH_POINTS.iter().fold(f32::MIN, |a, p| a.max(p.0));
        let max_y = CURSOR_GLYPH_POINTS.iter().fold(f32::MIN, |a, p| a.max(p.1));
        assert!(min_x > -0.05 && max_x < 1.0, "x span {min_x}..{max_x}");
        assert!(max_y > 1.0 && max_y < 1.05, "y span max {max_y}");
    }

    #[test]
    fn pressed_sprite_is_smaller_than_idle() {
        let idle = arrow_points(20.0, 1.0);
        let pressed = arrow_points(20.0, CURSOR_PRESS_SCALE);
        let span = |pts: &[(f32, f32)]| {
            let max_x = pts.iter().fold(f32::MIN, |a, p| a.max(p.0));
            let min_x = pts.iter().fold(f32::MAX, |a, p| a.min(p.0));
            max_x - min_x
        };
        assert!(span(&pressed) < span(&idle), "pressed sprite must be compact");
    }

    #[test]
    fn border_pulse_matches_the_official_constants() {
        // Ghidra 140057dbb: InsertKeyFrame(0.5 -> 1.0), InsertKeyFrame(1.0 -> 0.76).
        assert!((BORDER_PULSE_LOW - 0.76).abs() < 1e-6);
        assert!((BORDER_THICKNESS_FACTOR - 16.0).abs() < 1e-6);
        assert!((BORDER_INNER_FACTOR - 0.88).abs() < 1e-6);
    }

    // --- VIS-04/VIS-13/VIS-14/VIS-18/VIS-19/VIS-20/VIS-27 contract guards. ---

    #[test]
    fn press_animation_matches_the_official_scale_timing() {
        // `FUN_14004f796`: one Scale keyframe, 550 ms, value 0.7.
        assert_eq!(CURSOR_PRESS_MS, 550);
        assert!((CURSOR_PRESS_SCALE - 0.7).abs() < 1e-6);
        let anim = PressAnim { start: Instant::now(), from: 1.0, to: CURSOR_PRESS_SCALE };
        let at = |ms: u64| press_scale_at(&anim, anim.start + Duration::from_millis(ms));
        assert!((at(0).0 - 1.0).abs() < 1e-3);
        assert!(!at(0).1);
        let (mid, done) = at(275);
        assert!((mid - 0.85).abs() < 0.01, "mid scale {mid}");
        assert!(!done);
        let (end, done) = at(550);
        assert!((end - CURSOR_PRESS_SCALE).abs() < 1e-6, "end scale {end}");
        assert!(done);
        // A release that interrupts mid-press starts from the current value.
        let release = PressAnim { start: anim.start + Duration::from_millis(275), from: mid, to: 1.0 };
        let (back, done) = press_scale_at(&release, release.start + Duration::from_millis(550));
        assert!((back - 1.0).abs() < 1e-6, "release end {back}");
        assert!(done);
    }

    #[test]
    fn official_animation_durations_are_the_binary_constants() {
        assert_eq!(FADE_MS, 500);
        assert_eq!(PULSE_MS, 3000);
        assert_eq!(EDGE_BREATH_MS, 3000);
        assert_eq!(SHIMMER_MS, 2000);
        assert_eq!(SUPPRESS_EVERY, Duration::from_secs(1));
        assert!((FADE_EASE.0 - 0.22).abs() < 1e-6 && (FADE_EASE.2 - 0.36).abs() < 1e-6);
        assert!((PULSE_EASE.0 - 0.4).abs() < 1e-6 && (PULSE_EASE.2 - 0.2).abs() < 1e-6);
    }

    #[test]
    fn cubic_bezier_matches_the_material_easings() {
        for ease in [FADE_EASE, PULSE_EASE] {
            assert!(cubic_bezier(ease, 0.0).abs() < 1e-3);
            assert!((cubic_bezier(ease, 1.0) - 1.0).abs() < 1e-3);
        }
        // Both official curves are ease-out: at the halfway point they are already
        // well past half way, which is exactly what the old linear ramps lacked.
        let half = cubic_bezier(FADE_EASE, 0.5);
        assert!(half > 0.75, "fade ease-out value {half}");
        // `cubic-bezier(0.4, 0, 0.2, 1)` is front-loaded: x = 0.5 lands past half
        // way up the curve, which is what makes the pulse read as a breathe.
        let pulse_half = cubic_bezier(PULSE_EASE, 0.5);
        assert!(pulse_half > 0.75 && pulse_half < 0.80, "pulse ease value {pulse_half}");
        assert!(cubic_bezier(PULSE_EASE, 0.25) < cubic_bezier(FADE_EASE, 0.25));
    }

    #[test]
    fn pill_pulse_uses_the_3000ms_cycle_and_its_easing() {
        let start = Instant::now() - Duration::from_millis(2400);
        // 0.8 of the way into a 3000 ms cycle: inside the falling half.
        let value = pill_pulse_alpha(start);
        assert!(value > BORDER_PULSE_LOW && value < 1.0, "pulse {value}");
        let fresh = Instant::now();
        assert!((pill_pulse_alpha(fresh) - 1.0).abs() < 1e-6);
        // 1.2 s in would still be the flat first half; the old 1.2 s cycle would
        // already have wrapped.
        let early = Instant::now() - Duration::from_millis(1200);
        assert!((pill_pulse_alpha(early) - 1.0).abs() < 1e-6);
    }

    #[test]
    fn pill_geometry_matches_the_official_48_56_18_layout() {
        let layout = compute_pill_layout(1920.0, 1080.0, BANNER, ESC_HINT, 2.0, Some(400.0), Some(200.0), false);
        // Root height = 48*s + 2*18*s, top margin 56*s.
        assert!((layout.height - 168.0).abs() < 0.01, "height {}", layout.height);
        assert!((layout.y - 76.0).abs() < 0.01, "root margin {}", layout.y);
        assert!((layout.body_y - 112.0).abs() < 0.01, "body top {}", layout.body_y);
        assert!((layout.body_h - 96.0).abs() < 0.01, "body height {}", layout.body_h);
        // Width = 2*(18+16)*s + statusW + 28*s + cancelW.
        let expected = 2.0 * 34.0 * 2.0 + 400.0 + 28.0 * 2.0 + 200.0;
        assert!((layout.width - expected).abs() < 0.01, "width {} vs {expected}", layout.width);
        assert!((layout.status_x - (layout.x + 68.0)).abs() < 0.01);
        assert!((layout.radius - layout.body_h / 2.0).abs() < 0.01);
        assert!(layout.separator_x > layout.status_x + 400.0 - 1.0);
    }

    /// Mirrors the accent predicate `parity/pill-crop.ps1` uses, applied to the
    /// premultiplied BGRA sprite instead of a screenshot.
    fn sprite_accent(pixels: &[u8], width: usize, x: usize, y: usize) -> bool {
        let offset = (y * width + x) * 4;
        (pixels[offset] as i32 - pixels[offset + 2] as i32) > 150 && pixels[offset] > 180
    }

    #[test]
    fn capture_exclusion_defaults_to_the_on_screen_safe_mask() {
        // The affinity blanks the DirectComposition content on screen on some
        // machines, so the default must never be the affinity; only an explicit
        // "wda" opts into it, and an unknown value must not silently opt in.
        assert_eq!(parse_capture_exclusion(None), CaptureExclusion::Mask);
        assert_eq!(parse_capture_exclusion(Some("")), CaptureExclusion::Mask);
        assert_eq!(parse_capture_exclusion(Some("mask")), CaptureExclusion::Mask);
        assert_eq!(parse_capture_exclusion(Some("nonsense")), CaptureExclusion::Mask);
        assert_eq!(parse_capture_exclusion(Some(" WDA ")), CaptureExclusion::Wda);
        assert_eq!(parse_capture_exclusion(Some("wda")), CaptureExclusion::Wda);
        assert_eq!(parse_capture_exclusion(Some("off")), CaptureExclusion::Off);
        assert_eq!(parse_capture_exclusion(Some("none")), CaptureExclusion::Off);
        assert_eq!(parse_capture_exclusion(Some("false")), CaptureExclusion::Off);
    }

    #[test]
    fn capture_mask_watchdog_is_short_enough_to_be_invisible_to_the_operator() {
        assert!(CAPTURE_MASK_MAX_MS >= 1000);
        assert!(CAPTURE_MASK_MAX_MS <= 10_000);
    }

    #[test]
    fn layered_pill_path_is_selected_without_a_composition_display() {
        // The layered sprite is the only backend that can draw when the composition
        // display did not attach; when it did, the DComp tree owns the pixels. A
        // regression here is exactly "the pill is never drawn on one of the paths".
        assert!(layered_pill_selected(false));
        assert!(!layered_pill_selected(true));
    }

    #[test]
    fn pill_sprite_body_sits_where_paint_pill_pushes_it() {
        // Guards the class of bug that took the pill off screen: the sprite gained
        // transparent padding for the soft shadow, and `paint_pill` compensates by
        // pushing at `(x - pad, y - pad)`. If either half drifts, the accent body
        // lands somewhere else and the desktop pixel gates see nothing.
        let Some(sprite) = build_pill_sprite(1.0) else {
            return;
        };
        let pad = sprite.pad as usize;
        let root_w = sprite.layout.width.round() as usize;
        let root_h = sprite.layout.height.round() as usize;
        let body_w = sprite.layout.body_w.round() as usize;
        let body_h = sprite.layout.body_h.round() as usize;
        let sprite_w = root_w + pad * 2;
        let sprite_h = root_h + pad * 2;
        assert_eq!(sprite.pixels.len(), sprite_w * sprite_h * 4, "sprite buffer size");
        // The accent body is the content box inside the root (VIS-13), so it starts
        // `18*s` in from the root origin, which `paint_pill` places at the layout.
        let inset = (sprite.layout.body_x - sprite.layout.x).round() as usize;
        let body_top = pad + inset;
        let count = (pad + inset..pad + inset + body_w)
            .flat_map(|x| (body_top..body_top + body_h).map(move |y| (x, y)))
            .filter(|(x, y)| sprite_accent(&sprite.pixels, sprite_w, *x, *y))
            .count();
        assert!(count > 500, "accent body pixels in the sprite = {count}");
        let first_accent_row = (0..sprite_h).find(|y| {
            (0..sprite_w).any(|x| sprite_accent(&sprite.pixels, sprite_w, x, *y))
        });
        assert_eq!(first_accent_row, Some(body_top), "accent body top edge moved");
        let first_accent_col = (0..sprite_w).find(|x| {
            (0..sprite_h).any(|y| sprite_accent(&sprite.pixels, sprite_w, *x, y))
        });
        assert_eq!(first_accent_col, Some(pad + inset), "accent body left edge moved");
    }

    #[test]
    fn pill_sprite_carries_a_soft_shadow() {
        // VIS-16: the shadow must be a blurred silhouette with a padded margin, not
        // a second hard-edged pill.
        let Some(sprite) = build_pill_sprite(1.0) else {
            return;
        };
        assert!(sprite.pad >= 1);
        let pad = sprite.pad as usize;
        let root_w = sprite.layout.width.round() as usize;
        let w = root_w + pad * 2;
        let body_w = sprite.layout.body_w.round() as usize;
        let body_h = sprite.layout.body_h.round() as usize;
        let inset = (sprite.layout.body_x - sprite.layout.x).round() as usize;
        let body_bottom = pad + inset + body_h;
        // Directly under the body's bottom edge the shadow is present...
        let sample = |x: usize, y: usize| sprite.pixels[(y * w + x) * 4 + 3];
        let under = sample(pad + inset + body_w / 2, body_bottom + 2);
        assert!(under > 0, "shadow missing under the pill");
        let outer = sample(pad + inset + body_w / 2, (body_bottom + pad - 1).min(w - 1));
        assert!(outer < under, "shadow must fade outward: {outer} vs {under}");
    }

    #[test]
    fn rtl_locale_swaps_the_pill_segments() {
        // Official RTL branch (`140057dbb:432-441`): the status run is laid out
        // first, so in a right-to-left locale it sits to the right of the divider.
        let ltr = compute_pill_layout(1920.0, 1080.0, BANNER, ESC_HINT, 1.0, Some(300.0), Some(150.0), false);
        let rtl = compute_pill_layout(1920.0, 1080.0, BANNER, ESC_HINT, 1.0, Some(300.0), Some(150.0), true);
        assert!(ltr.status_x < ltr.cancel_x, "ltr {} {}", ltr.status_x, ltr.cancel_x);
        assert!(rtl.status_x > rtl.cancel_x, "rtl {} {}", rtl.status_x, rtl.cancel_x);
        assert!((ltr.width - rtl.width).abs() < 1e-4);
        // The divider always sits between the two runs, 14 * s from each.
        assert!(rtl.cancel_x + 150.0 < rtl.separator_x && rtl.separator_x < rtl.status_x);
        assert!(ltr.status_x + 300.0 < ltr.separator_x && ltr.separator_x < ltr.cancel_x);
        assert!((ltr.separator_x - (ltr.status_x + 300.0 + 14.0)).abs() < 1e-3);
    }

    #[test]
    fn cursor_dpi_source_is_the_monitor_under_the_point() {
        // The helper has to compile the per-monitor lookup in; a pure unit test can
        // only assert the floor/fallback path, which the wrapper keeps at 96.
        assert!(dpi_for_point(0.0, 0.0) >= 96);
    }

    #[test]
    fn cursor_raster_is_antialiased_and_blurred() {
        let pixels = rasterize_cursor(126, 59.0, 1.0, 1.0, (0.2, 0.61, 1.0, 1.0), 2.0);
        assert_eq!(pixels.len(), 126 * 126 * 4);
        // VIS-02: supersampling leaves partially covered pixels along the outline.
        // A GDI `Polygon` raster has none.
        let partial = pixels.chunks(4).filter(|p| p[3] > 8 && p[3] < 247).count();
        assert!(partial > 50, "antialiased edge pixels = {partial}");
        // VIS-03: the blurred halo reaches well past the 28*s ellipse, so a pixel
        // 30 px out from its centre still carries a faint accent wash.
        let n = 126usize;
        let centre = (65usize, 66usize);
        let far = pixels[((centre.1 + 30) * n + (centre.0 + 30)) * 4 + 3];
        assert!(far > 0, "blurred halo missing at 30 px off centre");
        // The glyph itself is still an opaque fill: the bounding-box restriction must
        // not have clipped the arrow away.
        let opaque = pixels.chunks(4).filter(|p| p[3] > 250).count();
        assert!(opaque > 400, "opaque glyph pixels = {opaque}");
    }

    #[test]
    fn gaussian_blur_turns_a_hard_edge_into_a_ramp() {
        let n = 32usize;
        let mut mask = vec![0.0f32; n * n];
        for y in 0..n {
            for x in 0..16 {
                mask[y * n + x] = 1.0;
            }
        }
        gaussian_blur(&mut mask, n, n, 4.0);
        let row: Vec<f32> = (0..n).map(|x| mask[10 * n + x]).collect();
        let partial = row.iter().filter(|v| **v > 0.02 && **v < 0.98).count();
        assert!(partial >= 8, "blur transition width {partial}");
        for pair in row.windows(2) {
            assert!(pair[1] <= pair[0] + 1e-4, "blur must be monotone: {pair:?}");
        }
    }

    #[test]
    fn shadow_uses_the_official_coefficients() {
        let accent = (0.2f32, 0.9f32, 0.4f32, 1.0);
        let shadow = shadow_color(accent);
        assert!((shadow.0 - ((1.0 - 0.2) * 0.644 + 0.2)).abs() < 1e-6);
        assert!((shadow.1 - 0.9 * 0.51).abs() < 1e-6);
        assert!((shadow.2 - 0.4 * 0.51).abs() < 1e-6);
    }

    #[test]
    fn position_error_matches_rdata() {
        assert_eq!(FAILED_POSITION_CURSOR_FOR, "failed to position cursor for ");
        assert_eq!(OVERLAY_ERROR_SEP, " overlay: ");
        assert_eq!(
            position_error("click", "send cursor overlay command"),
            "failed to position cursor for click overlay: send cursor overlay command"
        );
        assert_eq!(
            position_error("scroll", CREATE_WINDOW_FAILED),
            "failed to position cursor for scroll overlay: CreateWindowExW failed"
        );
        assert_eq!(
            position_error("drag", CURSOR_OVERLAY_INACTIVE),
            "failed to position cursor for drag overlay: cursor overlay is no longer active"
        );
        assert!(BANNER.contains("DeepSeek Harness"));
    }
}
