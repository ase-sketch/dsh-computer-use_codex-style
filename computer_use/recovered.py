"""Constants recovered from the installed Codex Computer Use helper.

Source artifacts (read-only, not shipped):
- ~/.codex/plugins/cache/openai-bundled/computer-use/*/docs/api.md
- @oai/sky WindowsComputerUseClientBase
- bin/windows/codex-computer-use.exe method table
"""

HELPER_METHODS = (
    "window",
    "get_window_state",
    "list_apps",
    "launch_app",
    "list_windows",
    "get_window",
    "diagnostic_state",
    "activate_window",
    "perform_secondary_action",
    "set_value",
    "click_element",
    "scroll_element",
    "click",
    "drag",
    "scroll",
    "type_text",
    "press_key",
    "close",
    "end_turn",
)

STDIO_REQUEST_KEYS = ("id", "method", "params", "meta")
PIPE_FRAME_HEADER = "uint32le_jsonrpc"

OBSERVE_METHOD = "get_window_state"
OBSERVE_ALIASES = ("observe", "get_app_state")

TREE_WINDOW_PREFIX = 'Window: "'
FOCUSED_PREFIX = "The focused UI element is"
DOCUMENT_PREFIX = "Document text:"
SELECTED_PREFIX = "Selected text:"

HELPER_RUST_MODULES = (
    "src/accessibility.rs",
    "src/accessibility/monitor.rs",
    "src/capture/image.rs",
    "src/dpi.rs",
    "src/input/initial_cursor.rs",
    "src/input/interruption.rs",
    "src/overlay/mod.rs",
    "src/shell/app_catalog.rs",
)

CLICK_ELEMENT = "click_element"
SECONDARY_ACTIONS = (
    "Raise",
    "Scroll Up",
    "Scroll Down",
    "Scroll Left",
    "Scroll Right",
    "Expand",
    "Collapse",
)
STATE_FLAG_ERROR = "get_window_state must request include_text, include_screenshot, or both"
COORDINATE_GEOMETRY_UNAVAILABLE = "coordinate input geometry is unavailable"
WINDOW_BOUNDS_UNAVAILABLE_COORD = "window bounds unavailable for coordinate input"
NO_SCREENSHOT_TARGETS_FOR = "no screenshot targets found for "
WINDOW_BOUNDS_UNAVAILABLE_FOR = "window bounds unavailable for "
