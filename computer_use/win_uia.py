"""In-process IUIAutomation — official accessibility.rs + accessibility/monitor.rs."""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import HRESULT, POINTER, byref, c_void_p, wintypes
from dataclasses import dataclass, field

from computer_use.models import Bounds, UINode
from computer_use.recovered import SECONDARY_ACTIONS
from computer_use.win_capture import window_rect
from computer_use.win_dpi import physical_to_logical, physical_size_to_logical

ole32 = ctypes.oledll.ole32
ole32_raw = ctypes.windll.ole32
oleaut32 = ctypes.WinDLL("oleaut32")
oleaut32.SysAllocString.argtypes = [wintypes.LPCWSTR]
oleaut32.SysAllocString.restype = wintypes.LPWSTR
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
user32.IsChild.restype = wintypes.BOOL
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.UnhookWinEvent.restype = wintypes.BOOL
ole32_raw.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
ole32_raw.CoInitializeEx.restype = HRESULT
ole32_raw.CoUninitialize.argtypes = []

CLSID_CUIAutomation = "{FF48DBA4-60EF-4201-AA87-54103EEF594E}"
IID_IUIAutomation = "{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}"
TreeScope_Element = 0x1
TreeScope_Subtree = 0x7
AutomationElementMode_Full = 1
UIA_MAX_NODES = 250
DOCUMENT_FIND_MAX = 200
MAX_DEPTH = 32
CHILD_LIMIT = 48
ELEMENT_ID_MAX = 2**31 - 1
COINIT_MULTITHREADED = 0x0
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = ctypes.c_long(0x80010106).value
INTEGRITY_MESSAGE = (
    "Accessibility is limited because the target window has higher Windows integrity "
    "than the Computer Use helper."
)
SKIP_TITLES = {
    "Backstop Window",
    "Default IME",
    "Input Occlusion Window",
    "MSCTFIME UI",
    "Program Manager",
    "Taskbar",
}

PROP_RUNTIME_ID = 30000
PROP_BOUNDING_RECT = 30001
PROP_PROCESS_ID = 30002
PROP_CONTROL_TYPE = 30003
PROP_LOCALIZED_CONTROL_TYPE = 30004
PROP_NAME = 30005
PROP_HAS_KEYBOARD_FOCUS = 30008
PROP_IS_ENABLED = 30010
PROP_AUTOMATION_ID = 30011
PROP_CLASS_NAME = 30012
PROP_HELP_TEXT = 30013
PROP_NATIVE_WINDOW_HANDLE = 30020
PROP_IS_OFFSCREEN = 30022
PROP_VALUE = 30045
PROP_EXPAND_STATE = 30070
PROP_TOGGLE_STATE = 30086

# Official dump cache (FUN_1400129b1) plus ClassName/IsOffscreen extras.
DUMP_CACHE_PROPERTIES = (
    PROP_RUNTIME_ID,
    PROP_BOUNDING_RECT,
    PROP_PROCESS_ID,
    PROP_CONTROL_TYPE,
    PROP_LOCALIZED_CONTROL_TYPE,
    PROP_NAME,
    PROP_HAS_KEYBOARD_FOCUS,
    PROP_IS_ENABLED,
    PROP_AUTOMATION_ID,
    PROP_HELP_TEXT,
    PROP_NATIVE_WINDOW_HANDLE,
    PROP_CLASS_NAME,
    PROP_IS_OFFSCREEN,
)
# Official event cache: ControlType, Name, NativeWindowHandle, ProcessId.
EVENT_CACHE_PROPERTIES = (
    PROP_CONTROL_TYPE,
    PROP_NAME,
    PROP_NATIVE_WINDOW_HANDLE,
    PROP_PROCESS_ID,
)
CACHE_PROPERTIES = DUMP_CACHE_PROPERTIES

PATTERN_INVOKE = 10000
PATTERN_SELECTION = 10001
PATTERN_VALUE = 10002
PATTERN_RANGE = 10003
PATTERN_SCROLL = 10004
PATTERN_EXPAND = 10005
PATTERN_WINDOW = 10009
PATTERN_SELECTION_ITEM = 10010
PATTERN_TEXT = 10014
PATTERN_TOGGLE = 10015
PATTERN_SCROLL_ITEM = 10017
PATTERN_LEGACY = 10018
DUMP_CACHE_PATTERNS = (
    PATTERN_SELECTION,
    PATTERN_VALUE,
    PATTERN_RANGE,
    PATTERN_SCROLL,
    PATTERN_EXPAND,
    PATTERN_WINDOW,
    PATTERN_SELECTION_ITEM,
    PATTERN_TEXT,
    PATTERN_TOGGLE,
    PATTERN_INVOKE,
    PATTERN_SCROLL_ITEM,
    PATTERN_LEGACY,
)
EVENT_CACHE_PATTERNS: tuple[int, ...] = ()
CACHE_PATTERNS = DUMP_CACHE_PATTERNS

UIA_MenuOpenedEventId = 20003
UIA_MenuClosedEventId = 20007
UIA_Text_TextSelectionChangedEventId = 20014
UIA_Text_TextChangedEventId = 20015
UIA_Window_WindowOpenedEventId = 20016
UIA_Window_WindowClosedEventId = 20017
AUTOMATION_EVENTS = (
    UIA_Window_WindowOpenedEventId,
    UIA_MenuOpenedEventId,
    UIA_Text_TextSelectionChangedEventId,
    UIA_Text_TextChangedEventId,
    UIA_MenuClosedEventId,
    UIA_Window_WindowClosedEventId,
)

CONTROL_TYPES = {
    50000: "button",
    50001: "calendar",
    50002: "checkbox",
    50003: "combo box",
    50004: "text field",
    50005: "hyperlink",
    50006: "image",
    50007: "list item",
    50008: "list",
    50009: "menu",
    50010: "menu bar",
    50011: "menu item",
    50012: "progress bar",
    50013: "radio button",
    50014: "scroll bar",
    50015: "slider",
    50016: "spinner",
    50017: "status bar",
    50018: "tab",
    50019: "tab item",
    50020: "text",
    50021: "toolbar",
    50022: "tooltip",
    50023: "tree",
    50024: "tree item",
    50025: "custom",
    50026: "group",
    50027: "thumb",
    50028: "data grid",
    50029: "data item",
    50030: "document",
    50031: "split button",
    50032: "window",
    50033: "pane",
    50034: "header",
    50035: "header item",
    50036: "table",
    50037: "title bar",
    50038: "separator",
    50039: "semantic zoom",
    50040: "app bar",
}

RUNTIME_ID_MISMATCH = "no longer matches the cached runtime ID"
PROCESS_MISMATCH = "no longer belongs to the cached target process"
CACHED_TARGET_MISMATCH = "no longer matches the cached target in"
NO_CACHED_BOUNDS = "has no cached bounds"
NO_CACHED_SECONDARY = "has no cached secondary actions for"
SECONDARY_EXPECTED = "unsupported secondary action: {action}; expected Raise, Scroll Up, Scroll Down, Scroll Left, Scroll Right, Expand, or Collapse"
CREATE_UIA = "create UIAutomation"
CREATE_UIA_CACHE = "create UIA cache request"
CREATE_UIA_EVENT_CACHE = "create UIA event cache request"
GET_UIA_ROOT = "get UIA root element"
GET_FOREGROUND_UIA = "get foreground UIA element"
NO_FOREGROUND = "no foreground window is active"
NO_VISIBLE_TOP = "no visible top-level windows found for "
GET_APP_UIA = "get app UIA element"
SNAPSHOT_APP_UIA = "snapshot app UIA element"
REFRESH_TARGET_WINDOW = "refresh UIA element target window"
REFRESH_TARGET_SNAPSHOT = "refresh UIA element target snapshot"
INIT_COM_UIA = "initialize COM for UI Automation"
MONITOR_DID_NOT_START = "accessibility monitor did not start"
WINDOW_OPENED_NOT_READY = "accessibility window-opened handler did not become ready"
ID_SPACE_EXHAUSTED = "accessibility element ID space exhausted"
SCROLL_GONE = "element no longer exposes ScrollPattern"
EXPAND_GONE = "element no longer exposes ExpandCollapsePattern"
NOT_SETTABLE = "Cannot set a value for an element that is not settable"
TOOLHELP_FAILED = "CreateToolhelp32Snapshot failed"
IID_IUnknown_TXT = "{00000000-0000-0000-C000-000000000046}"
IID_FOCUS_HANDLER_TXT = "{C270F6B5-5C69-4290-9759-7A5E4253B52A}"
IID_STRUCTURE_HANDLER_TXT = "{E81D1B4E-11C5-42F8-9754-E7036C79F054}"
IID_EVENT_HANDLER_TXT = "{146C3C17-F12E-4E22-8C27-F894B9B79C69}"

TRUNCATED_PREFIX = "(truncated: "
TRUNCATED_OMITTED = ", omitted "
TRUNCATED_SUFFIX = " children)"

_runtime_ids: dict[int, tuple[int, ...]] = {}
_cached_actions: dict[int, list[str]] = {}
_cached_elements: dict[int, c_void_p] = {}
_cached_hwnd = 0
_cached_pid = 0
_cached_process_name = ""
_snapshot_revision = 0
_accessibility_revision = 0
_snapshot_count = 0
_capture_session_count = 0
_last_invalidation = ""
_element_id_space = 0
_targeted_dirty = False
_rev_lock = threading.Lock()
_window_opened_ready = threading.Event()

_event_keep: list[object] = []
_monitor_hwnd = 0
_monitor_factory = c_void_p()
_monitor_desktop = c_void_p()
_monitor_dump_cache = c_void_p()
_monitor_event_cache = c_void_p()
_monitor_walker = c_void_p()
_monitor_focus_ptr = c_void_p()
_monitor_struct_ptr = c_void_p()
_monitor_event_ptrs: list[c_void_p] = []
_monitor_winevent = 0
_monitor_winevent_fg = 0
_monitor_winevent_proc = None
_monitor_thread: threading.Thread | None = None
_monitor_jobs: queue.Queue = queue.Queue()
_monitor_ready = threading.Event()
_monitor_started = False
_monitor_failed = ""

ScrollAmount_LargeDecrement = 0
ScrollAmount_SmallDecrement = 1
ScrollAmount_NoAmount = 2
ScrollAmount_LargeIncrement = 3
ScrollAmount_SmallIncrement = 4
ExpandCollapseState_Collapsed = 0
ExpandCollapseState_Expanded = 1
ExpandCollapseState_PartiallyExpanded = 2
ExpandCollapseState_LeafNode = 3
TH32CS_SNAPPROCESS = 0x2
GA_ROOT = 2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32.PeekMessageW.argtypes = [POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(MSG)]
user32.DispatchMessageW.argtypes = [POINTER(MSG)]


@dataclass
class AccessibilityDump:
    nodes: list[UINode]
    focused: str = ""
    selected_text: str = ""
    document_text: str = ""
    selected_elements: list[str] = field(default_factory=list)
    snapshot_revision: int = 0
    accessibility_revision: int = 0
    snapshot_count: int = 0
    omitted: int = 0
    last_invalidation: str = ""
    process_id: int = 0
    runtime_ids: dict[int, tuple[int, ...]] = field(default_factory=dict)
    truncation: str = ""
    elements: list = field(default_factory=list, repr=False)


@dataclass
class _Job:
    op: str
    args: tuple
    done: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: BaseException | None = None


def truncated_label(role: str, name: str, omitted: int) -> str:
    return f'{TRUNCATED_PREFIX}{role} "{name}"{TRUNCATED_OMITTED}{omitted}{TRUNCATED_SUFFIX}'


def _guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8).from_buffer_copy(data4))


def _vtbl(obj: c_void_p):
    return ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))


def _fn(obj: c_void_p, index: int, restype, *argtypes):
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(_vtbl(obj)[index])


def _release(obj: c_void_p | None) -> None:
    if obj:
        _fn(obj, 2, ctypes.c_ulong)(obj)


def _bstr(obj: c_void_p, index: int) -> str:
    bstr = wintypes.LPWSTR()
    hr = _fn(obj, index, HRESULT, POINTER(wintypes.LPWSTR))(obj, byref(bstr))
    if hr != 0 or not bstr:
        return ""
    try:
        return ctypes.wstring_at(bstr) or ""
    finally:
        oleaut32.SysFreeString(bstr)


def _bool_prop(el: c_void_p, index: int) -> bool:
    flag = wintypes.BOOL()
    hr = _fn(el, index, HRESULT, POINTER(wintypes.BOOL))(el, byref(flag))
    return hr == 0 and bool(flag.value)


def integrity_rid(pid: int) -> int | None:
    TOKEN_QUERY = 0x0008
    TokenIntegrityLevel = 25
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, byref(token)):
            return None
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, TokenIntegrityLevel, None, 0, byref(size))
        if size.value == 0:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, TokenIntegrityLevel, buf, size, byref(size)):
            return None
        ptr = ctypes.cast(buf, POINTER(c_void_p)).contents
        advapi32.GetSidSubAuthorityCount.restype = POINTER(ctypes.c_ubyte)
        count_ptr = advapi32.GetSidSubAuthorityCount(ptr)
        if not count_ptr or count_ptr[0] == 0:
            return None
        last = count_ptr[0] - 1
        advapi32.GetSidSubAuthority.restype = POINTER(wintypes.DWORD)
        rid_ptr = advapi32.GetSidSubAuthority(ptr, last)
        return int(rid_ptr[0]) if rid_ptr else None
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(handle)


def integrity_blocked(hwnd: int) -> str | None:
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    theirs = integrity_rid(int(pid.value))
    ours = integrity_rid(int(kernel32.GetCurrentProcessId()))
    if theirs is None or ours is None:
        return None
    if theirs > ours:
        return INTEGRITY_MESSAGE
    return None


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    try:
        return window_rect(hwnd)
    except Exception:
        return 0, 0, 1, 1


def _logical_bounds(rect: wintypes.RECT, origin: tuple[float, float], scale: float) -> Bounds:
    scale = scale if scale > 0.01 else 1.0
    ox, oy = origin
    x, y = physical_to_logical(float(rect.left), float(rect.top), ox, oy, scale)
    w, h = physical_size_to_logical(float(rect.right - rect.left), float(rect.bottom - rect.top), scale)
    return Bounds(x, y, float(w), float(h))


def _fallback(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> list[UINode]:
    left, top, width, height = _rect(hwnd)
    scale = scale if scale > 0.01 else 1.0
    ox, oy = origin
    lx, ly = physical_to_logical(left, top, ox, oy, scale)
    lw, lh = physical_size_to_logical(width, height, scale)
    return [UINode(0, "window", title or str(hwnd), Bounds(lx, ly, float(lw), float(lh)))]


def _pattern(el: c_void_p, pattern_id: int) -> c_void_p | None:
    """GetCurrentPattern=16/18, GetCachedPattern=17/19 (IUnknown layouts)."""
    for index in (16, 17, 18, 19):
        pat = c_void_p()
        if _fn(el, index, HRESULT, ctypes.c_int, POINTER(c_void_p))(el, pattern_id, byref(pat)) == 0 and pat:
            return pat
    return None


def _has_pattern(el: c_void_p, pattern_id: int) -> bool:
    pat = _pattern(el, pattern_id)
    if not pat:
        return False
    _release(pat)
    return True


def _value_of(el: c_void_p) -> str:
    pattern = _pattern(el, PATTERN_VALUE)
    if not pattern:
        return ""
    try:
        return _bstr(pattern, 4)  # IUIAutomationValuePattern.get_CurrentValue
    finally:
        _release(pattern)


def _text_range_text(pattern: c_void_p, getter_index: int) -> str:
    rng = c_void_p()
    if _fn(pattern, getter_index, HRESULT, POINTER(c_void_p))(pattern, byref(rng)) != 0 or not rng:
        return ""
    try:
        bstr = wintypes.LPWSTR()
        if _fn(rng, 12, HRESULT, ctypes.c_int, POINTER(wintypes.LPWSTR))(rng, -1, byref(bstr)) == 0 and bstr:
            try:
                return ctypes.wstring_at(bstr) or ""
            finally:
                oleaut32.SysFreeString(bstr)
        return ""
    finally:
        _release(rng)


def _selection_text(el: c_void_p) -> str:
    pattern = _pattern(el, PATTERN_TEXT)
    if not pattern:
        return ""
    try:
        arr = c_void_p()
        if _fn(pattern, 5, HRESULT, POINTER(c_void_p))(pattern, byref(arr)) != 0 or not arr:
            return _text_range_text(pattern, 7)
        try:
            length = ctypes.c_int()
            _fn(arr, 3, HRESULT, POINTER(ctypes.c_int))(arr, byref(length))
            chunks: list[str] = []
            for i in range(min(int(length.value), 8)):
                rng = c_void_p()
                if _fn(arr, 4, HRESULT, ctypes.c_int, POINTER(c_void_p))(arr, i, byref(rng)) != 0 or not rng:
                    continue
                bstr = wintypes.LPWSTR()
                if _fn(rng, 12, HRESULT, ctypes.c_int, POINTER(wintypes.LPWSTR))(rng, -1, byref(bstr)) == 0 and bstr:
                    try:
                        chunk = ctypes.wstring_at(bstr) or ""
                        if chunk:
                            chunks.append(chunk)
                    finally:
                        oleaut32.SysFreeString(bstr)
                _release(rng)
            return "\n".join(chunks) or _text_range_text(pattern, 7)
        finally:
            _release(arr)
    finally:
        _release(pattern)


def _document_text(el: c_void_p) -> str:
    pattern = _pattern(el, PATTERN_TEXT)
    if not pattern:
        return ""
    try:
        text = _text_range_text(pattern, 7)
        return text[:32_000] if len(text) > 32_000 else text
    finally:
        _release(pattern)


def _expand_state(el: c_void_p) -> int | None:
    pat = _pattern(el, PATTERN_EXPAND)
    if not pat:
        return None
    try:
        state = ctypes.c_int()
        if _fn(pat, 5, HRESULT, POINTER(ctypes.c_int))(pat, byref(state)) == 0:
            return int(state.value)
        return None
    finally:
        _release(pat)


def _toggle_state(el: c_void_p) -> int | None:
    pat = _pattern(el, PATTERN_TOGGLE)
    if not pat:
        return None
    try:
        state = ctypes.c_int()
        if _fn(pat, 4, HRESULT, POINTER(ctypes.c_int))(pat, byref(state)) == 0:
            return int(state.value)
        return None
    finally:
        _release(pat)


def _scrollable(el: c_void_p) -> tuple[bool, bool]:
    pat = _pattern(el, PATTERN_SCROLL)
    if not pat:
        return False, False
    try:
        h = wintypes.BOOL()
        v = wintypes.BOOL()
        hz = _fn(pat, 9, HRESULT, POINTER(wintypes.BOOL))(pat, byref(h)) == 0 and bool(h.value)
        vt = _fn(pat, 10, HRESULT, POINTER(wintypes.BOOL))(pat, byref(v)) == 0 and bool(v.value)
        return hz, vt
    finally:
        _release(pat)


def _value_readonly(el: c_void_p) -> bool | None:
    pat = _pattern(el, PATTERN_VALUE)
    if not pat:
        return None
    try:
        flag = wintypes.BOOL()
        if _fn(pat, 5, HRESULT, POINTER(wintypes.BOOL))(pat, byref(flag)) == 0:
            return bool(flag.value)
        return None
    finally:
        _release(pat)


def _secondary_actions(el: c_void_p) -> list[str]:
    actions: list[str] = []
    if _has_pattern(el, PATTERN_INVOKE) or _has_pattern(el, PATTERN_WINDOW):
        actions.append("Raise")
    hz, vt = _scrollable(el)
    if vt or _has_pattern(el, PATTERN_SCROLL):
        if vt or not hz:
            actions.extend(["Scroll Up", "Scroll Down"])
        if hz:
            actions.extend(["Scroll Left", "Scroll Right"])
    expand = _expand_state(el)
    if expand is not None or _has_pattern(el, PATTERN_EXPAND):
        if expand in (None, ExpandCollapseState_Collapsed, ExpandCollapseState_PartiallyExpanded):
            actions.append("Expand")
        if expand in (None, ExpandCollapseState_Expanded, ExpandCollapseState_PartiallyExpanded):
            actions.append("Collapse")
    out: list[str] = []
    for name in SECONDARY_ACTIONS:
        if name in actions and name not in out:
            out.append(name)
    return out


def _states(el: c_void_p) -> list[str]:
    flags: list[str] = []
    if _has_pattern(el, PATTERN_SELECTION_ITEM):
        flags.append("selectable")
        pat = _pattern(el, PATTERN_SELECTION_ITEM)
        if pat:
            selected = wintypes.BOOL()
            if _fn(pat, 6, HRESULT, POINTER(wintypes.BOOL))(pat, byref(selected)) == 0 and selected.value:
                flags.append("selected")
            _release(pat)
    if not _bool_prop(el, 28):
        flags.append("disabled")
    expand = _expand_state(el)
    if expand == ExpandCollapseState_Collapsed:
        flags.append("collapsed")
    elif expand == ExpandCollapseState_Expanded:
        flags.append("expanded")
    elif expand == ExpandCollapseState_PartiallyExpanded:
        flags.append("partially expanded")
    readonly = _value_readonly(el)
    has_range = _has_pattern(el, PATTERN_RANGE)
    if has_range:
        flags.append("settable, float")
    elif readonly is False:
        flags.append("settable, string")
    toggle = _toggle_state(el)
    if toggle == 0:
        flags.append("off")
    elif toggle == 1:
        flags.append("on")
    elif toggle == 2:
        flags.append("indeterminate")
    return flags


def _element_rect(el: c_void_p) -> wintypes.RECT:
    rect = wintypes.RECT()
    for index in (42, 43):
        tmp = wintypes.RECT()
        if _fn(el, index, HRESULT, POINTER(wintypes.RECT))(el, byref(tmp)) == 0:
            rect = tmp
            if tmp.right != tmp.left or tmp.bottom != tmp.top:
                return tmp
    return rect


def _role_of(el: c_void_p) -> str:
    """AX-21: the official prints the localized control type verbatim.

    It keeps the capitalised "SplitButton" and even a trailing space (Word's
    AutoSave switch reads "切换关闭 "). DSH used to strip + lowercase here, which
    is the rich profile in helper-rs/src/uia.rs:1873; the Python engine is the
    official-syntax implementation, so it keeps the raw spelling. The
    CONTROL_TYPES fallback stays lower-case because that table is DSH's own.
    """
    localized = _bstr(el, 22)
    if localized.strip():
        return localized
    ctype = wintypes.INT()
    _fn(el, 21, HRESULT, POINTER(wintypes.INT))(el, byref(ctype))
    return CONTROL_TYPES.get(int(ctype.value), "custom")


def _element_node(el: c_void_p, index: int, depth: int, origin: tuple[float, float], scale: float) -> UINode:
    name = _bstr(el, 23)
    role = _role_of(el)
    bounds = _logical_bounds(_element_rect(el), origin, scale)
    value = _value_of(el)
    actions = _secondary_actions(el)
    automation_id = _bstr(el, 29)
    description = _bstr(el, 31)
    focused = _bool_prop(el, 26)
    return UINode(
        index=index,
        role=role,
        name=name,
        bounds=bounds,
        value=value,
        depth=depth,
        actions=actions,
        automation_id=automation_id,
        description=description,
        states=_states(el),
        focused=focused,
    )


def _normalize(walker: c_void_p, el: c_void_p, cache: c_void_p | None) -> c_void_p:
    normalized = c_void_p()
    if cache:
        hr = _fn(walker, 14, HRESULT, c_void_p, c_void_p, POINTER(c_void_p))(walker, el, cache, byref(normalized))
    else:
        hr = _fn(walker, 8, HRESULT, c_void_p, POINTER(c_void_p))(walker, el, byref(normalized))
    if hr == 0 and normalized:
        _release(el)
        return normalized
    return el


def _first_child(walker: c_void_p, el: c_void_p, cache: c_void_p | None) -> c_void_p | None:
    child = c_void_p()
    if cache:
        hr = _fn(walker, 10, HRESULT, c_void_p, c_void_p, POINTER(c_void_p))(walker, el, cache, byref(child))
    else:
        hr = _fn(walker, 4, HRESULT, c_void_p, POINTER(c_void_p))(walker, el, byref(child))
    return child if hr == 0 and child else None


def _next_sibling(walker: c_void_p, el: c_void_p, cache: c_void_p | None) -> c_void_p | None:
    nxt = c_void_p()
    if cache:
        hr = _fn(walker, 12, HRESULT, c_void_p, c_void_p, POINTER(c_void_p))(walker, el, cache, byref(nxt))
    else:
        hr = _fn(walker, 6, HRESULT, c_void_p, POINTER(c_void_p))(walker, el, byref(nxt))
    return nxt if hr == 0 and nxt else None


class SAFEARRAYBOUND(ctypes.Structure):
    _fields_ = [("cElements", wintypes.ULONG), ("lLbound", ctypes.c_long)]


class SAFEARRAY(ctypes.Structure):
    _fields_ = [
        ("cDims", wintypes.USHORT),
        ("fFeatures", wintypes.USHORT),
        ("cbElements", wintypes.ULONG),
        ("cLocks", wintypes.ULONG),
        ("pvData", c_void_p),
        ("rgsabound", SAFEARRAYBOUND * 1),
    ]


def _runtime_id(el: c_void_p) -> tuple[int, ...]:
    ptr = c_void_p()
    if _fn(el, 4, HRESULT, POINTER(c_void_p))(el, byref(ptr)) != 0 or not ptr:
        return ()
    try:
        sa = ctypes.cast(ptr, POINTER(SAFEARRAY)).contents
        n = int(sa.rgsabound[0].cElements)
        if sa.cbElements == 4 and sa.pvData and n > 0:
            data = ctypes.cast(sa.pvData, POINTER(ctypes.c_int))
            return tuple(int(data[i]) for i in range(min(n, 16)))
        return ()
    except Exception:
        return ()
    finally:
        try:
            oleaut32.SafeArrayDestroy(ptr)
        except Exception:
            pass


def invalidate_accessibility(reason: str = "structure") -> None:
    global _accessibility_revision, _last_invalidation, _targeted_dirty
    with _rev_lock:
        _accessibility_revision += 1
        _last_invalidation = reason
        _targeted_dirty = True


def cache_diagnostics() -> dict[str, object]:
    with _rev_lock:
        return {
            "snapshotRevision": _snapshot_revision,
            "accessibilityRevision": _accessibility_revision,
            "accessibilitySnapshotCount": _snapshot_count,
            "captureCachedSessionCount": _capture_session_count,
            "lastCaptureInvalidationReason": _last_invalidation,
            "rootHwnd": _cached_hwnd,
            "processId": _cached_pid,
            "processName": _cached_process_name,
            "cachedElements": len(_runtime_ids),
            "eventMonitor": bool(_monitor_started and _monitor_factory),
            "inputHwnd": (_foreground_hwnds() or [0])[0],
        }


def note_capture_session() -> None:
    global _capture_session_count
    _capture_session_count += 1


def _guid_eq(left: GUID, right: GUID) -> bool:
    return (
        left.Data1 == right.Data1
        and left.Data2 == right.Data2
        and left.Data3 == right.Data3
        and bytes(left.Data4) == bytes(right.Data4)
    )


def _process_id(el: c_void_p) -> int:
    pid = ctypes.c_int()
    if _fn(el, 20, HRESULT, POINTER(ctypes.c_int))(el, byref(pid)) == 0:
        return int(pid.value)
    return 0


def _toolhelp_name(pid: int) -> str | None:
    if not pid:
        return None
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        raise OSError(TOOLHELP_FAILED)
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [ctypes.c_void_p, POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        if not kernel32.Process32FirstW(snap, byref(entry)):
            return None
        while True:
            if int(entry.th32ProcessID) == int(pid):
                return entry.szExeFile
            if not kernel32.Process32NextW(snap, byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snap)


def _process_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        name = _toolhelp_name(pid)
        if name:
            return True
    except OSError:
        pass
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _process_name(pid: int) -> str:
    try:
        name = _toolhelp_name(pid)
        if name:
            return name
    except OSError:
        pass
    if not pid:
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        getter = getattr(kernel32, "QueryFullProcessImageNameW", None)
        if getter is None:
            return ""
        getter.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, POINTER(wintypes.DWORD)]
        getter.restype = wintypes.BOOL
        if getter(handle, 0, buf, byref(size)):
            path = buf.value.replace("\\", "/")
            return path.rsplit("/", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


class _ComSink:
    """IUnknown + one Invoke slot for UIA event handlers."""

    def __init__(self, iid_text: str, invoke_restype, *invoke_argtypes):
        self.iid = _guid(iid_text)
        self.unknown = _guid(IID_IUnknown_TXT)
        self.refs = 1

        def qi(this, riid, out):
            if not riid or not out:
                return 0x80070057
            asked = riid.contents
            if _guid_eq(asked, self.unknown) or _guid_eq(asked, self.iid):
                out[0] = this
                self.refs += 1
                return 0
            out[0] = None
            return 0x80004002

        def addref(_this):
            self.refs += 1
            return self.refs

        def release(_this):
            self.refs = max(self.refs - 1, 0)
            return self.refs

        self._qi = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))(qi)
        self._add = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(addref)
        self._rel = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(release)
        self._invoke_cb = None
        self._invoke_fn = invoke_restype
        self._invoke_args = invoke_argtypes

        class Vtbl(ctypes.Structure):
            _fields_ = [
                ("QueryInterface", type(self._qi)),
                ("AddRef", type(self._add)),
                ("Release", type(self._rel)),
                ("Invoke", ctypes.WINFUNCTYPE(invoke_restype, c_void_p, *invoke_argtypes)),
            ]

        class Obj(ctypes.Structure):
            _fields_ = [("lpVtbl", POINTER(Vtbl))]

        self._Vtbl = Vtbl
        self._Obj = Obj
        self.vtbl = None
        self.obj = None

    def bind(self, python_invoke) -> c_void_p:
        wrapped = ctypes.WINFUNCTYPE(self._invoke_fn, c_void_p, *self._invoke_args)(python_invoke)
        self._invoke_cb = wrapped
        self.vtbl = self._Vtbl(self._qi, self._add, self._rel, wrapped)
        self.obj = self._Obj(ctypes.pointer(self.vtbl))
        return ctypes.cast(ctypes.pointer(self.obj), c_void_p)


def _pump() -> None:
    msg = MSG()
    while user32.PeekMessageW(byref(msg), None, 0, 0, 1):
        user32.TranslateMessage(byref(msg))
        user32.DispatchMessageW(byref(msg))


def _fill_cache(factory: c_void_p, cache: c_void_p, properties: tuple[int, ...], patterns: tuple[int, ...], scope: int) -> None:
    for prop in properties:
        _fn(cache, 3, HRESULT, ctypes.c_int)(cache, prop)
    for pattern in patterns:
        _fn(cache, 4, HRESULT, ctypes.c_int)(cache, pattern)
    _fn(cache, 7, HRESULT, ctypes.c_int)(cache, scope)
    cond = c_void_p()
    if _fn(factory, 18, HRESULT, POINTER(c_void_p))(factory, byref(cond)) == 0 and cond:
        _fn(cache, 9, HRESULT, c_void_p)(cache, cond)
        _release(cond)
    _fn(cache, 11, HRESULT, ctypes.c_int)(cache, AutomationElementMode_Full)


def _create_factory() -> c_void_p:
    factory = c_void_p()
    try:
        hr = ole32.CoCreateInstance(
            byref(_guid(CLSID_CUIAutomation)),
            None,
            1,
            byref(_guid(IID_IUIAutomation)),
            byref(factory),
        )
    except OSError as exc:
        raise OSError(CREATE_UIA) from exc
    if hr != 0 or not factory:
        raise OSError(CREATE_UIA)
    return factory


def _create_cache(factory: c_void_p, properties: tuple[int, ...], patterns: tuple[int, ...], scope: int, label: str) -> c_void_p:
    cache = c_void_p()
    hr = _fn(factory, 20, HRESULT, POINTER(c_void_p))(factory, byref(cache))
    if hr != 0 or not cache:
        raise OSError(label)
    _fill_cache(factory, cache, properties, patterns, scope)
    return cache


def _same(factory: c_void_p, a: c_void_p | None, b: c_void_p | None) -> bool:
    if not a or not b:
        return False
    same = wintypes.BOOL()
    hr = _fn(factory, 3, HRESULT, c_void_p, c_void_p, POINTER(wintypes.BOOL))(factory, a, b, byref(same))
    return hr == 0 and bool(same.value)


def _element_from_handle(factory: c_void_p, hwnd: int, cache: c_void_p | None) -> c_void_p | None:
    root = c_void_p()
    if cache:
        hr = _fn(factory, 10, HRESULT, wintypes.HWND, c_void_p, POINTER(c_void_p))(factory, hwnd, cache, byref(root))
    else:
        hr = _fn(factory, 6, HRESULT, wintypes.HWND, POINTER(c_void_p))(factory, hwnd, byref(root))
    return root if hr == 0 and root else None


def _focused_element(factory: c_void_p, cache: c_void_p | None) -> c_void_p | None:
    focused = c_void_p()
    if cache:
        hr = _fn(factory, 12, HRESULT, c_void_p, POINTER(c_void_p))(factory, cache, byref(focused))
    else:
        hr = _fn(factory, 8, HRESULT, POINTER(c_void_p))(factory, byref(focused))
    if hr != 0 or not focused:
        return None
    return focused


def _window_title(hwnd: int) -> str:
    size = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(size + 2)
    user32.GetWindowTextW(hwnd, buf, size + 2)
    return buf.value or ""


def _skip_chrome_hwnd(hwnd: int) -> bool:
    return _window_title(hwnd) in SKIP_TITLES


def _foreground_hwnds() -> list[int]:
    fg = int(user32.GetForegroundWindow() or 0)
    if not fg:
        return []
    root = int(user32.GetAncestor(fg, GA_ROOT) or fg)
    out: list[int] = []
    for handle in (fg, root):
        if handle and handle not in out and not _skip_chrome_hwnd(handle):
            out.append(handle)
    return out


def _visible_toplevel_hwnds(wanted: int) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(h, _lp):
        handle = int(h)
        if not user32.IsWindowVisible(h) or _skip_chrome_hwnd(handle):
            return True
        found.append(handle)
        return True

    user32.EnumWindows(_enum, 0)
    if wanted and wanted in found:
        return [wanted] + [h for h in found if h != wanted]
    return found


def _teardown_monitor_objects() -> None:
    global _monitor_hwnd, _monitor_factory, _monitor_desktop, _monitor_dump_cache, _monitor_event_cache
    global _monitor_walker, _monitor_focus_ptr, _monitor_struct_ptr, _monitor_event_ptrs
    global _monitor_winevent, _monitor_winevent_fg, _monitor_winevent_proc, _monitor_started
    try:
        if _monitor_factory:
            _fn(_monitor_factory, 41, HRESULT)(_monitor_factory)
    except Exception:
        pass
    if _monitor_winevent:
        try:
            user32.UnhookWinEvent(_monitor_winevent)
        except Exception:
            pass
        _monitor_winevent = 0
    if _monitor_winevent_fg:
        try:
            user32.UnhookWinEvent(_monitor_winevent_fg)
        except Exception:
            pass
        _monitor_winevent_fg = 0
    _monitor_winevent_proc = None
    _release(_monitor_desktop)
    _release(_monitor_walker)
    _release(_monitor_dump_cache)
    _release(_monitor_event_cache)
    _release(_monitor_factory)
    _monitor_desktop = c_void_p()
    _monitor_walker = c_void_p()
    _monitor_dump_cache = c_void_p()
    _monitor_event_cache = c_void_p()
    _monitor_factory = c_void_p()
    _monitor_focus_ptr = c_void_p()
    _monitor_struct_ptr = c_void_p()
    _monitor_event_ptrs = []
    _monitor_hwnd = 0
    _monitor_started = False
    _window_opened_ready.clear()
    _clear_element_cache()


def _install_handlers(factory: c_void_p, desktop: c_void_p, event_cache: c_void_p) -> None:
    global _monitor_focus_ptr, _monitor_struct_ptr, _monitor_event_ptrs, _monitor_winevent, _monitor_winevent_fg, _monitor_winevent_proc

    def on_focus(this, sender):
        invalidate_accessibility("focus")
        return 0

    def on_structure(this, sender, change_type, runtime_id):
        invalidate_accessibility("structure")
        return 0

    def on_event(this, sender, event_id):
        names = {
            UIA_Window_WindowOpenedEventId: "window-opened",
            UIA_Window_WindowClosedEventId: "window-closed",
            UIA_MenuOpenedEventId: "menu-opened",
            UIA_MenuClosedEventId: "menu-closed",
            UIA_Text_TextChangedEventId: "text",
            UIA_Text_TextSelectionChangedEventId: "text-selection",
        }
        invalidate_accessibility(names.get(int(event_id), "event"))
        return 0

    focus_sink = _ComSink(IID_FOCUS_HANDLER_TXT, HRESULT, c_void_p)
    struct_sink = _ComSink(IID_STRUCTURE_HANDLER_TXT, HRESULT, c_void_p, ctypes.c_int, c_void_p)
    event_sink = _ComSink(IID_EVENT_HANDLER_TXT, HRESULT, c_void_p, ctypes.c_int)
    focus_ptr = focus_sink.bind(on_focus)
    struct_ptr = struct_sink.bind(on_structure)
    event_ptr = event_sink.bind(on_event)
    _fn(factory, 39, HRESULT, c_void_p, c_void_p)(factory, event_cache, focus_ptr)
    if desktop:
        _fn(factory, 37, HRESULT, c_void_p, ctypes.c_int, c_void_p, c_void_p)(
            factory, desktop, TreeScope_Subtree, event_cache, struct_ptr
        )
        opened = False
        for event_id in AUTOMATION_EVENTS:
            try:
                hr = _fn(factory, 32, HRESULT, ctypes.c_int, c_void_p, ctypes.c_int, c_void_p, c_void_p)(
                    factory, event_id, desktop, TreeScope_Subtree, event_cache, event_ptr
                )
                if hr == 0 and event_id == UIA_Window_WindowOpenedEventId:
                    opened = True
            except Exception:
                continue
        if opened:
            _window_opened_ready.set()
    _monitor_focus_ptr = focus_ptr
    _monitor_struct_ptr = struct_ptr
    _monitor_event_ptrs = [event_ptr]
    _event_keep.extend([focus_sink, struct_sink, event_sink, focus_ptr, struct_ptr, event_ptr])

    EVENT_SYSTEM_FOREGROUND = 0x0003
    EVENT_OBJECT_HIERARCHYCHANGED = 0x8004
    EVENT_OBJECT_FOCUS = 0x8005
    WINEVENT_OUTOFCONTEXT = 0x0000
    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, ctypes.c_long, ctypes.c_long, wintypes.DWORD, wintypes.DWORD
    )

    def _on_win_event(hook, event, ehwnd, id_object, id_child, thread, timestamp):
        target = _monitor_hwnd
        if int(event) == EVENT_SYSTEM_FOREGROUND:
            invalidate_accessibility("foreground")
            return
        if ehwnd and target and (int(ehwnd) == int(target) or user32.IsChild(target, ehwnd)):
            invalidate_accessibility("winevent")

    _monitor_winevent_proc = WINEVENTPROC(_on_win_event)
    _monitor_winevent = user32.SetWinEventHook(
        EVENT_OBJECT_HIERARCHYCHANGED, EVENT_OBJECT_FOCUS, None, _monitor_winevent_proc, 0, 0, WINEVENT_OUTOFCONTEXT
    )
    _monitor_winevent_fg = user32.SetWinEventHook(
        EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, _monitor_winevent_proc, 0, 0, WINEVENT_OUTOFCONTEXT
    )
    _event_keep.append(_monitor_winevent_proc)


def _setup_monitor() -> None:
    global _monitor_factory, _monitor_desktop, _monitor_dump_cache, _monitor_event_cache, _monitor_walker, _monitor_started, _monitor_failed
    factory = _create_factory()
    dump_cache = _create_cache(factory, DUMP_CACHE_PROPERTIES, DUMP_CACHE_PATTERNS, TreeScope_Subtree, CREATE_UIA_CACHE)
    event_cache = _create_cache(factory, EVENT_CACHE_PROPERTIES, EVENT_CACHE_PATTERNS, TreeScope_Element, CREATE_UIA_EVENT_CACHE)
    desktop = c_void_p()
    hr = _fn(factory, 5, HRESULT, POINTER(c_void_p))(factory, byref(desktop))
    if hr != 0 or not desktop:
        desktop = c_void_p()
    walker = c_void_p()
    _fn(factory, 14, HRESULT, POINTER(c_void_p))(factory, byref(walker))
    _monitor_factory = factory
    _monitor_dump_cache = dump_cache
    _monitor_event_cache = event_cache
    _monitor_desktop = desktop
    _monitor_walker = walker
    _window_opened_ready.clear()
    _install_handlers(factory, desktop, event_cache)
    if not _window_opened_ready.wait(2):
        raise OSError(WINDOW_OPENED_NOT_READY)
    _monitor_started = True
    _monitor_failed = ""


def _monitor_loop() -> None:
    global _monitor_failed, _monitor_started
    hr = ole32_raw.CoInitializeEx(None, COINIT_MULTITHREADED)
    if hr < 0 and hr != RPC_E_CHANGED_MODE:
        _monitor_failed = INIT_COM_UIA
        _monitor_ready.set()
        return
    try:
        try:
            _setup_monitor()
        except Exception as exc:
            _monitor_failed = str(exc) or MONITOR_DID_NOT_START
        _monitor_ready.set()
        while True:
            try:
                job: _Job = _monitor_jobs.get(timeout=0.05)
            except queue.Empty:
                _pump()
                continue
            if job.op == "stop":
                job.done.set()
                break
            try:
                job.result = _dispatch(job.op, job.args)
            except BaseException as exc:
                job.error = exc
            job.done.set()
            _pump()
    finally:
        _teardown_monitor_objects()
        ole32_raw.CoUninitialize()


def _ensure_monitor() -> None:
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        if _monitor_failed:
            raise OSError(_monitor_failed)
        return
    _monitor_ready.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, name="computer-use-uia-monitor", daemon=True)
    _monitor_thread.start()
    if not _monitor_ready.wait(5):
        raise OSError(MONITOR_DID_NOT_START)
    if _monitor_failed and not _monitor_factory:
        raise OSError(_monitor_failed)


def _call_monitor(op: str, *args, timeout: float = 8.0):
    send = {
        "set_value": "send set value request to accessibility monitor",
        "secondary": "send secondary action request to accessibility monitor",
        "scroll": "send element target request to accessibility monitor",
        "dump": "request accessibility app window refresh",
    }.get(op, "")
    wait = {
        "set_value": "wait for accessibility set value",
        "secondary": "wait for accessibility secondary action",
        "scroll": "wait for accessibility element target",
        "dump": "computer-use accessibility refresh failed: ",
    }.get(op, f"computer-use accessibility {op} failed: ")
    _ = send
    _ensure_monitor()
    job = _Job(op=op, args=args)
    _monitor_jobs.put(job)
    if not job.done.wait(timeout):
        raise OSError(f"{wait}timeout")
    if job.error is not None:
        raise job.error
    return job.result


def _teardown_event_monitor() -> None:
    global _monitor_thread
    thread = _monitor_thread
    if thread is not None and thread.is_alive():
        job = _Job(op="stop", args=())
        _monitor_jobs.put(job)
        job.done.wait(2)
        thread.join(timeout=2)
    alive = thread is not None and thread.is_alive()
    _monitor_thread = None
    _monitor_ready.clear()
    if not alive:
        _teardown_monitor_objects()


def ensure_event_monitor(hwnd: int, factory: c_void_p | None = None, root: c_void_p | None = None, cache: c_void_p | None = None) -> None:
    """Official accessibility/monitor.rs: long-lived MTA factory + dump/event caches."""
    global _monitor_hwnd
    if not hwnd:
        return
    try:
        _ensure_monitor()
        _monitor_hwnd = int(hwnd)
    except Exception:
        return


def _alloc_ids(count: int) -> None:
    global _element_id_space
    if _element_id_space >= ELEMENT_ID_MAX or count > ELEMENT_ID_MAX - _element_id_space:
        raise OSError(ID_SPACE_EXHAUSTED)
    _element_id_space += count


class _Session:
    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.factory = _monitor_factory
        self.root = c_void_p()
        self.walker = _monitor_walker
        self.cache = _monitor_dump_cache
        self.focused = c_void_p()
        self._owned: list[c_void_p] = []

    def open(self, label: str = GET_APP_UIA) -> bool:
        if not self.factory:
            return False
        if not self.walker:
            walker = c_void_p()
            if _fn(self.factory, 14, HRESULT, POINTER(c_void_p))(self.factory, byref(walker)) != 0 or not walker:
                return False
            self.walker = walker
            self._owned.append(walker)
        candidates = [self.hwnd]
        for handle in _foreground_hwnds():
            if handle not in candidates:
                candidates.append(handle)
        root = None
        for handle in candidates:
            root = _element_from_handle(self.factory, handle, self.cache)
            if root:
                self.hwnd = handle
                break
        if not root:
            visible = _visible_toplevel_hwnds(self.hwnd)
            if not visible:
                raise OSError(f"{NO_VISIBLE_TOP}{self.hwnd}")
            for handle in visible:
                root = _element_from_handle(self.factory, handle, self.cache)
                if root:
                    self.hwnd = handle
                    break
        if not root:
            return False
        self.root = _normalize(self.walker, root, self.cache)
        focused = _focused_element(self.factory, self.cache)
        if focused:
            self.focused = focused
        else:
            for handle in _foreground_hwnds():
                el = _element_from_handle(self.factory, handle, self.cache)
                if el:
                    self.focused = el
                    break
        return True

    def close(self) -> None:
        for obj in self._owned:
            _release(obj)
        _release(self.focused)
        _release(self.root)
        self.focused = c_void_p()
        self.root = c_void_p()
        self._owned = []

    def walk(self, origin: tuple[float, float], scale: float) -> AccessibilityDump:
        nodes: list[UINode] = []
        focused_node: UINode | None = None
        selected_text = ""
        document_text = ""
        selected_elements: list[str] = []
        truncation = ""
        walk_els: list[c_void_p] = []

        def visit(el: c_void_p, depth: int, path: set[tuple[int, ...]]) -> str | None:
            nonlocal focused_node, selected_text, document_text, truncation
            if len(nodes) >= UIA_MAX_NODES:
                truncation = truncation or "child_limit"
                return "limit"
            name = _bstr(el, 23)
            if depth > 0 and name in SKIP_TITLES:
                return None
            rid = _runtime_id(el)
            if rid and rid in path:
                truncation = truncation or "cycle"
                return "cycle"
            if depth > MAX_DEPTH:
                truncation = truncation or "max_depth"
                return "max_depth"
            node = _element_node(el, len(nodes), depth, origin, scale)
            if self.focused and (_same(self.factory, el, self.focused) or node.focused):
                node.focused = True
                focused_node = node
                selected_text = selected_text or _selection_text(el)
                document_text = document_text or _document_text(el)
            if "selected" in node.states:
                selected_elements.append(f'[{node.index}] {node.role} "{node.name}"')
            if not document_text and node.role.strip().lower() == "document":
                document_text = _document_text(el) or node.value
            node.runtime_id = rid
            nodes.append(node)
            _fn(el, 1, ctypes.c_ulong)(el)
            walk_els.append(c_void_p(el.value))
            if len(nodes) >= UIA_MAX_NODES:
                return "limit"
            nested = set(path)
            if rid:
                nested.add(rid)
            child = _first_child(self.walker, el, self.cache)
            skipped = 0
            seen_children = 0
            while child:
                child = _normalize(self.walker, child, self.cache)
                seen_children += 1
                child_cap = DOCUMENT_FIND_MAX if node.role.strip().lower() == "document" else CHILD_LIMIT
                if len(nodes) >= UIA_MAX_NODES or seen_children > child_cap:
                    skipped += 1
                    truncation = truncation or "child_limit"
                    nxt = _next_sibling(self.walker, child, self.cache)
                    _release(child)
                    child = nxt
                    continue
                visit(child, depth + 1, nested)
                nxt = _next_sibling(self.walker, child, self.cache)
                _release(child)
                child = nxt
            if skipped:
                cut = nodes[-1] if nodes else None
                label = truncated_label(cut.role if cut else "element", cut.name if cut else "", skipped)
                nodes.append(UINode(len(nodes), "text", label, Bounds(0, 0, 0, 0), depth=depth + 1))
            return None

        visit(self.root, 0, set())
        from computer_use.tree_format import focused_line

        return AccessibilityDump(
            nodes=nodes,
            focused=focused_line(focused_node or (nodes[0] if nodes else None)),
            selected_text=selected_text,
            document_text=document_text,
            selected_elements=selected_elements,
            omitted=sum(1 for n in nodes if n.name.startswith(TRUNCATED_PREFIX)),
            runtime_ids={n.index: n.runtime_id for n in nodes if n.runtime_id},
            truncation=truncation,
            elements=walk_els,
        )

    def element_at(self, index: int, origin: tuple[float, float], scale: float) -> c_void_p | None:
        cached = _cached_elements.get(index)
        if cached:
            try:
                live = cached
                if self.cache:
                    updated = c_void_p()
                    hr = _fn(cached, 9, HRESULT, c_void_p, POINTER(c_void_p))(cached, self.cache, byref(updated))
                    if hr == 0 and updated:
                        _release(cached)
                        _cached_elements[index] = updated
                        live = updated
                want_cached = _runtime_ids.get(index, ())
                if want_cached and _runtime_id(live) and _runtime_id(live) != want_cached:
                    raise OSError(f"element {index} {CACHED_TARGET_MISMATCH} {self.hwnd}")
                pid = _process_id(live)
                if _cached_pid and pid and pid != _cached_pid:
                    raise OSError(f"element {index} {PROCESS_MISMATCH}")
                _fn(live, 1, ctypes.c_ulong)(live)
                return live
            except OSError:
                raise
            except Exception as exc:
                raise OSError(f"element {index} {CACHED_TARGET_MISMATCH} {self.hwnd}") from exc
        if _cached_elements:
            raise OSError(f"element {index} {RUNTIME_ID_MISMATCH}")
        found = c_void_p()
        counter = [0]
        want = _runtime_ids.get(index, ())

        def visit(el: c_void_p, depth: int, path: set[tuple[int, ...]]) -> bool:
            name = _bstr(el, 23)
            if depth > 0 and name in SKIP_TITLES:
                return False
            rid = _runtime_id(el)
            if rid and rid in path:
                return False
            if want and rid == want:
                found.value = el.value
                _fn(el, 1, ctypes.c_ulong)(el)
                return True
            if not want and counter[0] == index:
                found.value = el.value
                _fn(el, 1, ctypes.c_ulong)(el)
                return True
            counter[0] += 1
            nested = set(path)
            if rid:
                nested.add(rid)
            child = _first_child(self.walker, el, self.cache)
            seen_children = 0
            while child:
                child = _normalize(self.walker, child, self.cache)
                seen_children += 1
                if seen_children > CHILD_LIMIT or depth >= MAX_DEPTH:
                    nxt = _next_sibling(self.walker, child, self.cache)
                    _release(child)
                    child = nxt
                    continue
                if visit(child, depth + 1, nested):
                    _release(child)
                    return True
                nxt = _next_sibling(self.walker, child, self.cache)
                _release(child)
                child = nxt
            return False

        visit(self.root, 0, set())
        if want and not found.value:
            raise OSError(f"element {index} {RUNTIME_ID_MISMATCH}")
        if found.value:
            pid = _process_id(found)
            if _cached_pid and pid and pid != _cached_pid:
                _release(found)
                raise OSError(f"element {index} {PROCESS_MISMATCH}")
            if _cached_pid and not _process_alive(_cached_pid):
                _release(found)
                raise OSError(f"element {index} {PROCESS_MISMATCH}")
            if want and _runtime_id(found) and _runtime_id(found) != want:
                _release(found)
                raise OSError(f"element {index} {CACHED_TARGET_MISMATCH} {self.hwnd}")
            if self.hwnd and _cached_hwnd and int(self.hwnd) != int(_cached_hwnd) and not _same(self.factory, found, self.root):
                _release(found)
                raise OSError(f"window {self.hwnd} does not match {_cached_hwnd}")
        return found if found.value else None


def _clear_element_cache() -> None:
    global _cached_elements
    for el in _cached_elements.values():
        _release(el)
    _cached_elements = {}


def _remember_dump(hwnd: int, dumped: AccessibilityDump, session: _Session) -> None:
    global _runtime_ids, _cached_actions, _cached_hwnd, _snapshot_revision, _snapshot_count
    global _cached_pid, _cached_process_name, _targeted_dirty, _monitor_hwnd
    _alloc_ids(max(len(dumped.nodes), 1))
    _clear_element_cache()
    for i, el in enumerate(dumped.elements):
        if el:
            _cached_elements[i] = el
    dumped.elements = []
    _runtime_ids = dict(dumped.runtime_ids)
    _cached_actions = {n.index: list(n.actions) for n in dumped.nodes}
    _cached_hwnd = hwnd
    _monitor_hwnd = hwnd
    _snapshot_revision += 1
    _snapshot_count += 1
    dumped.snapshot_revision = _snapshot_revision
    dumped.accessibility_revision = _accessibility_revision
    dumped.snapshot_count = _snapshot_count
    dumped.last_invalidation = _last_invalidation
    _cached_pid = _process_id(session.root) if session.root else 0
    _cached_process_name = _process_name(_cached_pid)
    dumped.process_id = _cached_pid
    with _rev_lock:
        _targeted_dirty = False


def _dump_on_monitor(hwnd: int, title: str, origin: tuple[float, float], scale: float, targeted: bool) -> AccessibilityDump:
    session = _Session(hwnd)
    label = REFRESH_TARGET_WINDOW if targeted else GET_APP_UIA
    try:
        if not session.open(label):
            if targeted:
                raise OSError(f"computer-use accessibility targeted refresh failed: {REFRESH_TARGET_WINDOW}")
            return AccessibilityDump(nodes=_fallback(hwnd, title, origin, scale))
        if targeted and session.root and session.cache:
            updated = c_void_p()
            hr = _fn(session.root, 9, HRESULT, c_void_p, POINTER(c_void_p))(session.root, session.cache, byref(updated))
            if hr != 0 or not updated:
                raise OSError(f"computer-use accessibility targeted refresh failed: {REFRESH_TARGET_SNAPSHOT}")
            _release(session.root)
            session.root = updated
        dumped = session.walk(origin, scale)
        if not dumped.nodes:
            if targeted:
                raise OSError(f"computer-use accessibility targeted window refresh failed: {REFRESH_TARGET_SNAPSHOT}")
            return AccessibilityDump(nodes=_fallback(hwnd, title, origin, scale))
        _remember_dump(hwnd, dumped, session)
        return dumped
    finally:
        session.close()


def _dispatch(op: str, args: tuple):
    if op == "dump":
        hwnd, title, origin, scale = args
        targeted = False
        with _rev_lock:
            dirty = _targeted_dirty and _cached_hwnd == hwnd and bool(_runtime_ids)
        if dirty:
            try:
                return _dump_on_monitor(hwnd, title, origin, scale, True)
            except OSError:
                pass
        return _dump_on_monitor(hwnd, title, origin, scale, targeted)
    if op == "set_value":
        return _apply_value_on_monitor(*args)
    if op == "scroll":
        return _apply_scroll_on_monitor(*args)
    if op == "secondary":
        return _apply_secondary_on_monitor(*args)
    raise OSError(f"unsupported monitor op {op}")


def dump_accessibility(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> AccessibilityDump:
    blocked = integrity_blocked(hwnd)
    if blocked:
        left, top, width, height = _rect(hwnd)
        lx, ly = physical_to_logical(left, top, origin[0], origin[1], scale)
        lw, lh = physical_size_to_logical(width, height, scale)
        node = UINode(0, "window", blocked, Bounds(lx, ly, float(lw), float(lh)))
        from computer_use.tree_format import focused_line

        return AccessibilityDump(nodes=[node], focused=focused_line(node))
    if not hwnd:
        dumped = AccessibilityDump(nodes=_fallback(hwnd, title, origin, scale))
        from computer_use.tree_format import focused_line

        dumped.focused = focused_line(dumped.nodes[0] if dumped.nodes else None)
        return dumped
    try:
        dumped = _call_monitor("dump", hwnd, title, origin, scale)
        if isinstance(dumped, AccessibilityDump) and dumped.nodes:
            return dumped
    except Exception:
        pass
    return AccessibilityDump(nodes=_fallback(hwnd, title, origin, scale))


def _apply_scroll_on_monitor(hwnd: int, index: int, direction: str, pages: int, origin: tuple[float, float], scale: float) -> None:
    amounts = {
        "up": (ScrollAmount_NoAmount, ScrollAmount_LargeDecrement),
        "down": (ScrollAmount_NoAmount, ScrollAmount_LargeIncrement),
        "left": (ScrollAmount_LargeDecrement, ScrollAmount_NoAmount),
        "right": (ScrollAmount_LargeIncrement, ScrollAmount_NoAmount),
    }[direction]
    session = _Session(hwnd)
    try:
        if not session.open():
            raise OSError(CREATE_UIA)
        el = session.element_at(index, origin, scale)
        if not el:
            raise KeyError(f"element {index} {NO_CACHED_BOUNDS}")
        try:
            pat = _pattern(el, PATTERN_SCROLL)
            if not pat:
                raise OSError(SCROLL_GONE)
            hr = 0
            for _ in range(max(pages, 1)):
                hr = _fn(pat, 3, HRESULT, ctypes.c_int, ctypes.c_int)(pat, amounts[0], amounts[1])
                if hr != 0:
                    break
            _release(pat)
            if hr != 0:
                raise OSError(SCROLL_GONE)
        finally:
            _release(el)
    finally:
        session.close()


def apply_scroll_pages(hwnd: int, index: int, direction: str, pages: int, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> None:
    _call_monitor("scroll", hwnd, index, direction, pages, origin, scale)


def dump_tree(hwnd: int, title: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> list[UINode]:
    """ControlViewWalker + cache request + NormalizeElement + Invoke/Value/Toggle/Scroll patterns."""
    return dump_accessibility(hwnd, title, origin, scale).nodes


def _apply_value_on_monitor(hwnd: int, index: int, value: str, origin: tuple[float, float], scale: float) -> None:
    session = _Session(hwnd)
    try:
        if not session.open():
            raise OSError(CREATE_UIA)
        el = session.element_at(index, origin, scale)
        if not el:
            raise KeyError(f"element {index} {NO_CACHED_BOUNDS}")
        _fn(el, 3, HRESULT)(el)  # SetFocus — focus element before setting value
        readonly = _value_readonly(el)
        if readonly is True:
            _release(el)
            raise TypeError(NOT_SETTABLE)
        pat = _pattern(el, PATTERN_VALUE)
        if pat:
            bstr = oleaut32.SysAllocString(value)
            hr = _fn(pat, 3, HRESULT, wintypes.LPWSTR)(pat, bstr)
            oleaut32.SysFreeString(bstr)
            _release(pat)
            _release(el)
            if hr != 0:
                raise OSError("set UIA value")
            return
        rng = _pattern(el, PATTERN_RANGE)
        if rng:
            try:
                number = float(value)
            except ValueError as exc:
                _release(rng)
                _release(el)
                raise TypeError(f"range value must be a number: {value}") from exc
            hr = _fn(rng, 3, HRESULT, ctypes.c_double)(rng, ctypes.c_double(number))
            _release(rng)
            _release(el)
            if hr != 0:
                raise OSError("set UIA range value")
            return
        _release(el)
        raise TypeError(NOT_SETTABLE)
    finally:
        session.close()


def apply_value(hwnd: int, index: int, value: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> None:
    _call_monitor("set_value", hwnd, index, value, origin, scale)


def _apply_secondary_on_monitor(hwnd: int, index: int, action: str, origin: tuple[float, float], scale: float) -> None:
    session = _Session(hwnd)
    try:
        if not session.open():
            raise OSError(CREATE_UIA)
        el = session.element_at(index, origin, scale)
        if not el:
            raise KeyError(f"element {index} {NO_CACHED_BOUNDS}")
        key = action.strip().lower()
        try:
            available = _secondary_actions(el)
            cached = _cached_actions.get(index)
            if cached is not None and not cached:
                raise KeyError(f"element {index} {NO_CACHED_SECONDARY} {action}")
            names = {name.lower(): name for name in SECONDARY_ACTIONS}
            if key not in names:
                raise KeyError(SECONDARY_EXPECTED.format(action=action))
            live = {item.lower() for item in available}
            if key not in live:
                listed = ", ".join(available) if available else ", ".join(cached or [])
                raise OSError(f"secondary action '{action}' is not available for element {index}; available actions: {listed}")
            if key == "raise":
                _fn(el, 3, HRESULT)(el)
                inv = _pattern(el, PATTERN_INVOKE)
                if inv:
                    _fn(inv, 3, HRESULT)(inv)
                    _release(inv)
                return
            if key in {"scroll up", "scroll down", "scroll left", "scroll right"}:
                pat = _pattern(el, PATTERN_SCROLL)
                if not pat:
                    raise OSError(SCROLL_GONE)
                amounts = {
                    "scroll up": (ScrollAmount_NoAmount, ScrollAmount_LargeDecrement),
                    "scroll down": (ScrollAmount_NoAmount, ScrollAmount_LargeIncrement),
                    "scroll left": (ScrollAmount_LargeDecrement, ScrollAmount_NoAmount),
                    "scroll right": (ScrollAmount_LargeIncrement, ScrollAmount_NoAmount),
                }[key]
                hr = _fn(pat, 3, HRESULT, ctypes.c_int, ctypes.c_int)(pat, amounts[0], amounts[1])
                _release(pat)
                if hr != 0:
                    raise OSError("perform UIA secondary action")
                return
            if key in {"expand", "collapse"}:
                pat = _pattern(el, PATTERN_EXPAND)
                if not pat:
                    raise OSError(EXPAND_GONE)
                hr = _fn(pat, 3 if key == "expand" else 4, HRESULT)(pat)
                _release(pat)
                if hr != 0:
                    raise OSError("perform UIA secondary action")
                return
            raise KeyError(SECONDARY_EXPECTED.format(action=action))
        finally:
            _release(el)
    finally:
        session.close()


def apply_secondary_action(hwnd: int, index: int, action: str, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> None:
    _call_monitor("secondary", hwnd, index, action, origin, scale)
